from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, jsonify, render_template_string, request
from breeze_core import (
    COMPANY_NAMES_CACHE,
    NAVBAR_HTML,
    clear_memory_cache,
    get_breeze_client,
    get_short_token,
    parse_num,
    resolve_single_stock_name,
)

trade_bp = Blueprint("trade", __name__)

TRADE_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Trade Terminal - Holdings, Orders & GTT</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; }
    input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    .custom-scrollbar::-webkit-scrollbar { width: 5px; }
    .custom-scrollbar::-webkit-scrollbar-track { background: #f8fafc; }
    .custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
    .spin { animation: spin 0.7s linear infinite; }
    @keyframes spin { 100% { transform: rotate(360deg); } }
  </style>
</head>
<body class="bg-slate-100 text-slate-800 antialiased h-screen w-screen overflow-hidden flex flex-col">
  """ + NAVBAR_HTML + """
  
  <div class="flex-1 flex overflow-hidden">
    <!-- LEFT PANEL: PORTFOLIO HOLDINGS -->
    <aside class="w-80 md:w-[380px] bg-white border-r border-slate-200 flex flex-col h-full shrink-0 shadow-sm z-10">
      
      <!-- PORTFOLIO OVERVIEW CARD -->
      <div class="p-3.5 bg-slate-900 text-white border-b border-slate-800">
        <div class="flex justify-between items-center mb-1.5">
          <span class="text-[11px] font-bold uppercase tracking-wider text-slate-400">Total Portfolio Value</span>
          <span id="headerPnlBadge" class="text-xs px-2 py-0.5 rounded font-black bg-rose-500/20 text-rose-300">
            -0.00%
          </span>
        </div>
        <div class="text-2xl font-black tracking-tight" id="portfolioCurrentVal">₹0.00</div>
        
        <div class="grid grid-cols-3 gap-2 mt-3 pt-2.5 border-t border-slate-800 text-[11px]">
          <div>
            <div class="text-slate-400">Invested</div>
            <div class="font-bold text-slate-200" id="portfolioInvestedVal">₹0.00</div>
          </div>
          <div>
            <div class="text-slate-400">Floating P&L</div>
            <div class="font-bold text-rose-400" id="portfolioTotalPnl">-₹0.00</div>
          </div>
          <div>
            <div class="text-slate-400">Idle Cash</div>
            <div class="font-bold text-emerald-400" id="portfolioCashVal">₹0.00</div>
          </div>
        </div>
      </div>

      <!-- TITLE BAR -->
      <div class="px-3 py-2 border-b border-slate-200 bg-slate-50 flex items-center justify-between text-xs font-bold text-slate-700">
        <span class="flex items-center gap-1.5 text-blue-700">
          <span class="material-icons text-sm">pie_chart</span> Active Holdings
        </span>
        <span id="holdingsCountBadge" class="text-[10px] px-2 py-0.5 rounded-full font-bold bg-blue-100 text-blue-800">0</span>
      </div>

      <!-- SEARCH & SORT BAR -->
      <div class="p-2.5 border-b border-slate-200 bg-white space-y-2">
        <div class="relative">
          <span class="material-icons absolute left-2.5 top-2 text-slate-400 text-base">search</span>
          <input type="text" id="symbolSearchInput" onkeyup="filterList()" placeholder="Search ticker or company name..." 
            class="w-full bg-slate-50 border border-slate-200 rounded-lg pl-8 pr-2.5 py-1.5 text-xs text-slate-800 focus:outline-none focus:border-blue-500 font-semibold">
        </div>

        <!-- SORT CONTROLS -->
        <div class="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
          <div class="flex items-center gap-1 font-semibold">
            <span>Sort:</span>
            <select id="sortParamSelect" onchange="changeSortParam()" class="bg-slate-50 border border-slate-200 rounded px-1.5 py-0.5 text-slate-700 font-bold focus:outline-none focus:border-blue-500">
              <option value="total_current" selected>Market Value</option>
              <option value="pnl">P&L (₹)</option>
              <option value="pnl_pct">P&L (%)</option>
              <option value="quantity">Quantity</option>
              <option value="stock_code">Symbol (A-Z)</option>
              <option value="company_name">Company Name (A-Z)</option>
            </select>
          </div>

          <button id="sortOrderBtn" onclick="toggleSortOrder()" class="flex items-center gap-0.5 px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 font-bold text-slate-700 transition">
            <span id="sortOrderIcon" class="material-icons text-xs">arrow_downward</span>
            <span id="sortOrderLabel">High → Low</span>
          </button>
        </div>
      </div>

      <!-- LIST SCROLL CONTAINER -->
      <div id="sideListContainer" class="flex-1 overflow-y-auto p-2 space-y-1.5 custom-scrollbar"></div>

      <!-- FOOTER REFRESH BAR -->
      <div class="p-2 border-t border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-500 flex justify-between items-center">
        <span>Click holding to load terminal</span>
        <button onclick="refreshData(true)" title="Reload Portfolio" class="flex items-center gap-1 px-2 py-1 hover:bg-slate-200 rounded text-slate-700 transition">
          <span class="material-icons text-xs">sync</span> Refresh
        </button>
      </div>
    </aside>

    <!-- CENTER PANEL: ORDER PAD -->
    <main class="flex-1 flex flex-col items-center justify-center p-4 bg-slate-50 overflow-y-auto">
      <div class="w-full max-w-sm md:max-w-md bg-white rounded-xl shadow-lg border border-slate-200 flex flex-col overflow-hidden">
        
        <!-- HEADER -->
        <div class="p-4 border-b border-slate-100 bg-white">
          <div class="flex items-start justify-between">
            <div>
              <div class="flex items-center gap-2">
                <h2 id="modalStockSymbol" class="text-2xl font-black text-slate-900 tracking-tight">--</h2>
                <span id="holdingBadge" class="hidden text-[10px] px-2 py-0.5 rounded-full font-bold bg-amber-100 text-amber-800 border border-amber-200">
                  MTF PORTFOLIO
                </span>
              </div>
              <div id="modalCompanyName" class="text-xs text-slate-500 font-medium truncate max-w-[280px]">--</div>
              <div class="flex items-center gap-3 mt-1.5 text-xs font-semibold text-slate-500">
                <span>NSE: ₹<span id="nsePrice" class="text-slate-800 font-bold">0.00</span></span>
                <span id="nseChange" class="font-bold text-slate-500">0.00%</span>
              </div>
            </div>
            
            <button onclick="fetchQuote()" title="Refresh Live Quote" class="text-slate-400 hover:text-slate-700 p-1.5 rounded hover:bg-slate-100 transition">
              <span id="syncIcon" class="material-icons text-base">sync</span>
            </button>
          </div>

          <!-- ACTIVE HOLDING SUMMARY BANNER -->
          <div id="holdingMetaSummary" class="hidden mt-3 p-2.5 bg-slate-50 rounded-lg border border-slate-200 grid grid-cols-3 text-center text-xs">
            <div>
              <div class="text-[10px] text-slate-400 uppercase font-semibold">Total Shares</div>
              <div class="font-bold text-slate-800" id="metaHoldingQty">0</div>
            </div>
            <div>
              <div class="text-[10px] text-slate-400 uppercase font-semibold">Avg Cost</div>
              <div class="font-bold text-slate-800" id="metaHoldingAvg">₹0.00</div>
            </div>
            <div>
              <div class="text-[10px] text-slate-400 uppercase font-semibold">Current P&L</div>
              <div class="font-bold" id="metaHoldingPnl">₹0.00</div>
            </div>
          </div>
        </div>

        <!-- BUY / SELL BUTTONS -->
        <div class="flex border-b border-slate-200 text-xs font-bold">
          <button id="btnActionBuy" onclick="setAction('BUY')" class="flex-1 py-3 text-center border-b-2 border-emerald-500 text-emerald-600 transition">
            BUY MORE
          </button>
          <button id="btnActionSell" onclick="setAction('SELL')" class="flex-1 py-3 text-center border-b-2 border-transparent text-slate-400 hover:text-slate-600 transition">
            SELL / SQUARE-OFF
          </button>
        </div>

        <!-- FORM -->
        <div class="p-5 space-y-4">
          <div>
            <label class="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Product</label>
            <div class="flex items-center gap-2">
              <button id="prod-mtf" onclick="setProduct('mtf')" class="flex-1 py-1.5 rounded-lg border text-xs font-semibold bg-slate-900 border-slate-900 text-white transition">
                MTF (Pay Later)
              </button>
              <button id="prod-delivery" onclick="setProduct('delivery')" class="flex-1 py-1.5 rounded-lg border text-xs font-semibold border-slate-200 text-slate-600 hover:bg-slate-50 transition">
                Delivery (Cash)
              </button>
              <button id="prod-intraday" onclick="setProduct('intraday')" class="flex-1 py-1.5 rounded-lg border text-xs font-semibold border-slate-200 text-slate-600 hover:bg-slate-50 transition">
                Intraday
              </button>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <div class="flex items-center justify-between text-xs mb-1">
                <span class="font-bold text-slate-700">Quantity</span>
                <span class="text-[10px] font-semibold text-slate-500">
                  Holding: <span id="availQtyBadge" class="text-blue-600 font-bold">0</span>
                </span>
              </div>
              <input type="number" id="inputQty" value="1" min="1" oninput="recalcOrderRequirement()" 
                class="w-full border border-slate-300 rounded-lg p-2 text-right font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>

            <div>
              <div class="flex items-center justify-between text-xs mb-1">
                <span class="font-bold text-slate-700">Order Price</span>
                <select id="selectPriceType" onchange="onPriceTypeChange()" class="border border-slate-200 rounded px-1.5 py-0.5 text-[10px] font-semibold bg-slate-50 text-slate-700">
                  <option value="MARKET" selected>MARKET</option>
                  <option value="LIMIT">LIMIT</option>
                </select>
              </div>
              <input type="number" id="inputPrice" step="0.05" disabled placeholder="Market" oninput="recalcOrderRequirement()" 
                class="w-full border border-slate-300 rounded-lg p-2 text-right font-bold text-slate-400 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>
          </div>

          <div class="p-3 bg-slate-50 rounded-lg border border-slate-100 flex items-center justify-between text-xs">
            <div>
              <span class="text-slate-400">Order Value:</span>
              <div class="font-black text-sm text-slate-900" id="approxReq">₹0.00</div>
            </div>
            <div class="text-right">
              <span class="text-slate-400">Available Cash:</span>
              <div class="font-bold text-slate-700" id="userFundsSecondary">₹0.00</div>
            </div>
          </div>

          <button id="btnSubmitOrder" onclick="executeOrder()" class="w-full py-3 rounded-lg font-bold text-sm text-white bg-emerald-600 hover:bg-emerald-700 shadow transition active:scale-[0.98]">
            Submit Buy Order
          </button>

          <div id="orderStatusMsg" class="hidden text-center text-xs font-semibold py-2 px-3 rounded-lg transition"></div>
        </div>
      </div>
    </main>

    <!-- RIGHT PANEL: EXISTING ORDERS, TRIGGERS & GTT -->
    <aside class="w-80 md:w-96 bg-white border-l border-slate-200 flex flex-col h-full shrink-0 shadow-sm z-10">
      
      <div class="p-3.5 border-b border-slate-200 bg-slate-50">
        <div class="flex justify-between items-center mb-2">
          <div class="flex items-center gap-1.5">
            <span class="material-icons text-blue-600 text-base">alt_route</span>
            <span class="font-black text-xs text-slate-800 tracking-tight">Order Book & Triggers</span>
          </div>
          <span id="ordersCountBadge" class="text-[10px] px-2 py-0.5 rounded-full font-bold bg-blue-100 text-blue-700">0 Orders</span>
        </div>

        <div class="flex items-center gap-1 p-0.5 bg-slate-200 rounded text-[11px] font-bold">
          <button id="scopeStockBtn" onclick="setOrderScope('stock')" class="flex-1 py-1 rounded bg-white text-slate-900 shadow-xs transition">
            <span id="scopeStockName">--</span> Only
          </button>
          <button id="scopeAllBtn" onclick="setOrderScope('all')" class="flex-1 py-1 rounded text-slate-600 hover:text-slate-900 transition">
            All Scrips
          </button>
        </div>

        <div class="flex items-center gap-1 mt-2 text-[10px] font-bold">
          <button id="filterAllBtn" onclick="setOrderFilter('ALL')" class="px-2 py-0.5 rounded-full bg-slate-900 text-white transition">All</button>
          <button id="filterTriggerBtn" onclick="setOrderFilter('GTT')" class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200 transition">GTT / Triggers</button>
          <button id="filterPendingBtn" onclick="setOrderFilter('PENDING')" class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200 transition">Open / Pending</button>
          <button id="filterExecutedBtn" onclick="setOrderFilter('EXECUTED')" class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200 transition">Executed</button>
        </div>
      </div>

      <div id="stockOrdersContainer" class="flex-1 overflow-y-auto p-2.5 space-y-2 custom-scrollbar"></div>

      <div class="p-2 border-t border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-500 flex justify-between items-center">
        <span class="text-[10px] text-slate-400">Syncs GTT, SL, Day Orders</span>
        <button onclick="loadOrders()" title="Refresh Orders" class="flex items-center gap-1 px-2 py-1 hover:bg-slate-200 rounded text-slate-700 transition">
          <span class="material-icons text-xs">sync</span> Sync Orders
        </button>
      </div>
    </aside>

  </div>

  <script>
    let currentAction = 'BUY';
    let currentProduct = 'mtf';
    let selectedStock = '';
    let currentLTP = 0.00;
    let availableDeliveryQty = 0;
    let availableMtfQty = 0;
    let availableFunds = 0.00;

    let currentSortParam = 'total_current';
    let isSortDesc = true;

    let orderScope = 'stock';
    let orderFilter = 'ALL';

    let USER_HOLDINGS = [];
    let ALL_ORDERS = [];
    let isPolling = false;

    async function initOrderPad(force = false) {
      if (isPolling) return;
      isPolling = true;
      try {
        const res = await fetch('/api/trade_bootstrap' + (force ? '?force=1' : ''));
        const d = await res.json();

        availableFunds = Number(d.funds?.balance) || 0;
        const fmt = '₹' + availableFunds.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        document.getElementById('portfolioCashVal').innerText = fmt;
        document.getElementById('userFundsSecondary').innerText = fmt;

        USER_HOLDINGS = Array.isArray(d.holdings) ? d.holdings : [];
        updateHoldingsKPIs();

        ALL_ORDERS = Array.isArray(d.orders) ? d.orders : [];
        renderStockOrders();
        renderCurrentList();

        const syncEl = document.getElementById('syncStatusLabel');
        if (syncEl) syncEl.innerText = new Date().toLocaleTimeString();

        if (!selectedStock && USER_HOLDINGS.length > 0) {
          selectTradeStock(USER_HOLDINGS[0].stock_code);
        } else if (selectedStock) {
          updateSelectedStockDetails();
        }
      } catch (err) {
        console.error("Bootstrap fetch failed:", err);
      } finally {
        isPolling = false;
      }
    }

    function updateHoldingsKPIs() {
      document.getElementById('holdingsCountBadge').innerText = USER_HOLDINGS.length;

      let totInvested = 0, totCurrent = 0, totPnl = 0;
      USER_HOLDINGS.forEach(h => {
        totInvested += Number(h.total_invested || 0);
        totCurrent += Number(h.total_current || 0);
        totPnl += Number(h.pnl || 0);
      });

      document.getElementById('portfolioCurrentVal').innerText = '₹' + totCurrent.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('portfolioInvestedVal').innerText = '₹' + totInvested.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      
      const pnlEl = document.getElementById('portfolioTotalPnl');
      pnlEl.innerText = (totPnl >= 0 ? '+₹' : '-₹') + Math.abs(totPnl).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      pnlEl.className = 'font-bold ' + (totPnl >= 0 ? 'text-emerald-400' : 'text-rose-400');

      const totPnlPct = totInvested > 0 ? (totPnl / totInvested * 100) : 0;
      const badge = document.getElementById('headerPnlBadge');
      badge.innerText = (totPnlPct >= 0 ? '+' : '') + totPnlPct.toFixed(2) + '%';
      badge.className = 'text-xs px-2 py-0.5 rounded font-black ' + (totPnlPct >= 0 ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300');
    }

    function changeSortParam() {
      currentSortParam = document.getElementById('sortParamSelect').value;
      renderCurrentList();
    }

    function toggleSortOrder() {
      isSortDesc = !isSortDesc;
      const icon = document.getElementById('sortOrderIcon');
      const label = document.getElementById('sortOrderLabel');
      if (isSortDesc) {
        icon.innerText = 'arrow_downward';
        label.innerText = 'High → Low';
      } else {
        icon.innerText = 'arrow_upward';
        label.innerText = 'Low → High';
      }
      renderCurrentList();
    }

    function setOrderScope(scope) {
      orderScope = scope;
      const stockBtn = document.getElementById('scopeStockBtn');
      const allBtn = document.getElementById('scopeAllBtn');
      if (scope === 'stock') {
        stockBtn.className = 'flex-1 py-1 rounded bg-white text-slate-900 shadow-xs transition';
        allBtn.className = 'flex-1 py-1 rounded text-slate-600 hover:text-slate-900 transition';
      } else {
        allBtn.className = 'flex-1 py-1 rounded bg-white text-slate-900 shadow-xs transition';
        stockBtn.className = 'flex-1 py-1 rounded text-slate-600 hover:text-slate-900 transition';
      }
      renderStockOrders();
    }

    function setOrderFilter(filter) {
      orderFilter = filter;
      ['ALL', 'GTT', 'PENDING', 'EXECUTED'].forEach(f => {
        const btn = document.getElementById('filter' + f.charAt(0) + f.slice(1).toLowerCase() + 'Btn');
        if (btn) {
          if (f === filter) btn.className = 'px-2 py-0.5 rounded-full bg-slate-900 text-white transition';
          else btn.className = 'px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200 transition';
        }
      });
      renderStockOrders();
    }

    function renderCurrentList() {
      const q = document.getElementById('symbolSearchInput').value.trim().toUpperCase();
      const container = document.getElementById('sideListContainer');

      let list = [...USER_HOLDINGS];
      if (q) {
        list = list.filter(h => 
          (h.stock_code || '').toUpperCase().includes(q) || 
          (h.company_name || '').toUpperCase().includes(q)
        );
      }

      list.sort((a, b) => {
        let valA = a[currentSortParam];
        let valB = b[currentSortParam];
        if (currentSortParam === 'stock_code' || currentSortParam === 'company_name') {
          return isSortDesc ? String(valB).localeCompare(String(valA)) : String(valA).localeCompare(String(valB));
        }
        valA = Number(valA) || 0;
        valB = Number(valB) || 0;
        return isSortDesc ? (valB - valA) : (valA - valB);
      });

      if (list.length === 0) {
        container.innerHTML = `<div class="p-6 text-center text-xs text-slate-400">No holdings found matching "${q}".</div>`;
        return;
      }

      container.innerHTML = list.map(h => {
        const sym = h.stock_code;
        const compName = h.company_name || sym;
        const isSel = sym === selectedStock;
        const qty = Number(h.quantity) || 0;
        const avgPrice = Number(h.average_price) || 0;
        const ltp = Number(h.ltp) || 0;
        const pnl = Number(h.pnl) || 0;
        const pnlPct = Number(h.pnl_pct) || 0;
        const isProfit = pnl >= 0;
        const curVal = Number(h.total_current) || (qty * ltp);

        const stockOrders = ALL_ORDERS.filter(o => o.stock_code === sym);
        const triggersCount = stockOrders.filter(o => o.is_trigger).length;
        const pendingCount = stockOrders.filter(o => !o.is_trigger && (o.status || '').toLowerCase().includes('request')).length;

        return `
          <div onclick="selectTradeStock('${sym}')" 
            class="w-full text-left p-3 rounded-lg border text-xs cursor-pointer transition flex flex-col gap-1.5 ${
              isSel ? 'bg-blue-50 border-blue-400 shadow' : 'border-slate-200 bg-white hover:border-slate-300'
            }">
            <div class="flex justify-between items-start">
              <div class="min-w-0 pr-2">
                <div class="flex items-center gap-1.5 flex-wrap">
                  <span class="font-black text-sm text-slate-900">${sym}</span>
                  <span class="text-[9px] px-1.5 py-0.5 rounded font-bold bg-amber-100 text-amber-800">
                    MTF (${h.lots_count} lots)
                  </span>
                  ${triggersCount > 0 ? `<span class="text-[9px] px-1.5 py-0.2 rounded font-black bg-purple-100 text-purple-700">${triggersCount} GTT</span>` : ''}
                  ${pendingCount > 0 ? `<span class="text-[9px] px-1.5 py-0.2 rounded font-black bg-blue-100 text-blue-700 animate-pulse">${pendingCount} OPEN</span>` : ''}
                </div>
                <div class="text-[10px] text-slate-500 font-medium truncate mt-0.5 max-w-[200px]">${compName}</div>
              </div>
              <div class="text-right shrink-0">
                <span class="font-bold ${isProfit ? 'text-emerald-600' : 'text-rose-600'}">
                  ${isProfit ? '+' : ''}${pnlPct.toFixed(2)}%
                </span>
              </div>
            </div>

            <div class="flex justify-between items-center text-[11px] text-slate-500">
              <span>Qty: <b class="text-slate-800">${qty}</b> @ ₹${avgPrice.toFixed(2)}</span>
              <span>LTP: <b class="text-slate-900">₹${ltp.toFixed(2)}</b></span>
            </div>

            <div class="flex justify-between items-center pt-1 border-t border-slate-100 text-[10px]">
              <span class="text-slate-400">Val: <b class="text-slate-700">₹${curVal.toLocaleString('en-IN', {maximumFractionDigits: 0})}</b></span>
              <span class="font-bold ${isProfit ? 'text-emerald-600' : 'text-rose-600'}">
                P&L: ${isProfit ? '+₹' : '-₹'}${Math.abs(pnl).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
              </span>
            </div>
          </div>
        `;
      }).join('');
    }

    function renderStockOrders() {
      const container = document.getElementById('stockOrdersContainer');
      const countBadge = document.getElementById('ordersCountBadge');
      const scopeLabel = document.getElementById('scopeStockName');

      scopeLabel.innerText = selectedStock || '--';

      let list = [...ALL_ORDERS];

      if (orderScope === 'stock' && selectedStock) {
        list = list.filter(o => o.stock_code === selectedStock);
      }

      if (orderFilter === 'GTT') {
        list = list.filter(o => o.is_trigger);
      } else if (orderFilter === 'PENDING') {
        list = list.filter(o => !o.is_trigger && (o.status || '').toLowerCase().includes('request'));
      } else if (orderFilter === 'EXECUTED') {
        list = list.filter(o => (o.status || '').toLowerCase().includes('exec') || (o.status || '').toLowerCase().includes('complete'));
      }

      countBadge.innerText = `${list.length} Order${list.length === 1 ? '' : 's'}`;

      if (list.length === 0) {
        container.innerHTML = `
          <div class="p-6 text-center text-xs text-slate-400 flex flex-col items-center justify-center gap-1">
            <span class="material-icons text-slate-300 text-3xl">inbox</span>
            <span>No orders match this filter.</span>
          </div>
        `;
        return;
      }

      container.innerHTML = list.map(o => {
        const isBuy = (o.action || '').toUpperCase() === 'BUY';
        const st = (o.status || '').toLowerCase();
        
        let statusBadge = 'bg-slate-100 text-slate-600';
        if (st.includes('exec') || st.includes('complete')) statusBadge = 'bg-emerald-100 text-emerald-800';
        else if (st.includes('cancel') || st.includes('reject')) statusBadge = 'bg-rose-100 text-rose-800';
        else if (st.includes('request') || st.includes('ordered') || st.includes('pending')) statusBadge = 'bg-blue-100 text-blue-800 animate-pulse';

        return `
          <div class="p-3 rounded-xl border border-slate-200 bg-white hover:border-slate-300 shadow-2xs flex flex-col gap-1.5 transition">
            <div class="flex justify-between items-start text-xs">
              <div>
                <div class="flex items-center gap-1.5">
                  <span class="font-black text-slate-900">${o.stock_code}</span>
                  <span class="px-1.5 py-0.2 rounded font-black text-[10px] ${isBuy ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}">
                    ${o.action.toUpperCase()}
                  </span>
                  <span class="text-[9px] px-1.5 py-0.2 rounded font-bold ${o.is_trigger ? 'bg-purple-100 text-purple-700' : 'bg-slate-100 text-slate-600'}">
                    ${o.order_tag}
                  </span>
                </div>
                ${o.company_name ? `<div class="text-[10px] text-slate-400 font-medium truncate max-w-[180px]">${o.company_name}</div>` : ''}
              </div>
              <span class="text-[10px] px-2 py-0.5 rounded-full font-bold ${statusBadge}">
                ${o.status.toUpperCase()}
              </span>
            </div>

            <div class="flex justify-between items-center text-[11px] text-slate-600">
              <div>
                <span>Qty: <b class="text-slate-900">${o.quantity}</b></span>
                <span class="text-slate-400 mx-1">•</span>
                <span>Price: <b class="text-slate-900">₹${Number(o.price || 0).toFixed(2)}</b></span>
              </div>
              <span class="text-[10px] text-slate-400">${o.product}</span>
            </div>

            ${o.is_trigger ? `
              <div class="flex justify-between items-center px-2 py-1 bg-purple-50 rounded border border-purple-100 text-[10px] text-purple-800">
                <span class="font-bold flex items-center gap-1">
                  <span class="material-icons text-xs">gps_fixed</span> Trigger Price:
                </span>
                <span class="font-extrabold">₹${Number(o.trigger_price || 0).toFixed(2)}</span>
              </div>
            ` : ''}

            <div class="flex justify-between items-center text-[9px] text-slate-400 pt-1 border-t border-slate-50">
              <span>ID: ${o.order_id}</span>
              <span>${o.order_date || ''}</span>
            </div>
          </div>
        `;
      }).join('');
    }

    function filterList() {
      renderCurrentList();
    }

    function updateSelectedStockDetails() {
      if (!selectedStock) return;
      const holding = USER_HOLDINGS.find(h => h.stock_code === selectedStock);
      const badge = document.getElementById('holdingBadge');
      const meta = document.getElementById('holdingMetaSummary');
      const availBadge = document.getElementById('availQtyBadge');
      const compNameEl = document.getElementById('modalCompanyName');

      if (holding) {
        compNameEl.innerText = holding.company_name || selectedStock;
        badge.classList.remove('hidden');
        meta.classList.remove('hidden');
        document.getElementById('metaHoldingQty').innerText = holding.quantity;
        document.getElementById('metaHoldingAvg').innerText = '₹' + Number(holding.average_price || 0).toFixed(2);
        
        const pnlEl = document.getElementById('metaHoldingPnl');
        const pnl = Number(holding.pnl || 0);
        pnlEl.innerText = (pnl >= 0 ? '+₹' : '-₹') + Math.abs(pnl).toFixed(2);
        pnlEl.className = 'font-bold ' + (pnl >= 0 ? 'text-emerald-600' : 'text-rose-600');

        if (holding.ltp > 0 && currentLTP === 0) {
          currentLTP = Number(holding.ltp);
          document.getElementById('nsePrice').innerText = currentLTP.toFixed(2);
        }
        
        availableMtfQty = Number(holding.mtf_qty !== undefined ? holding.mtf_qty : holding.quantity);
        availableDeliveryQty = Number(holding.delivery_qty || 0);
        availBadge.innerText = holding.quantity.toLocaleString();
      }
    }

    async function selectTradeStock(sym) {
      if (!sym) return;
      selectedStock = sym;

      document.getElementById('modalStockSymbol').innerText = sym;
      const syncIcon = document.getElementById('syncIcon');
      if (syncIcon) syncIcon.classList.add('spin');

      const holding = USER_HOLDINGS.find(h => h.stock_code === sym);
      if (holding) {
        document.getElementById('inputQty').value = holding.quantity;
        setProduct('mtf');
      } else {
        document.getElementById('inputQty').value = 1;
        setProduct('delivery');
      }

      updateSelectedStockDetails();
      renderStockOrders();
      renderCurrentList();
      recalcOrderRequirement();

      try {
        await fetchQuote();
      } finally {
        if (syncIcon) syncIcon.classList.remove('spin');
      }
      recalcOrderRequirement();
    }

    async function fetchQuote() {
      if (!selectedStock) return;
      try {
        const res = await fetch(`/api/quote?stock_code=${selectedStock}`);
        const d = await res.json();
        currentLTP = Number(d.ltp) || 0.0;
        document.getElementById('nsePrice').innerText = currentLTP.toFixed(2);
        const changePct = Number(d.change_pct) || 0.0;
        const changeEl = document.getElementById('nseChange');
        changeEl.innerText = (changePct >= 0 ? '+' : '') + changePct.toFixed(2) + '%';
        changeEl.className = changePct >= 0 ? 'font-bold text-emerald-600' : 'font-bold text-rose-600';

        const priceType = document.getElementById('selectPriceType').value;
        const inpPrice = document.getElementById('inputPrice');
        if (priceType === 'LIMIT' && !inpPrice.value) {
          inpPrice.value = currentLTP.toFixed(2);
        }
      } catch (e) {
        console.error("Quote error:", e);
      }
    }

    function updateAvailableQtyUI() {
      const badge = document.getElementById('availQtyBadge');
      badge.innerText = currentProduct === 'mtf' ? availableMtfQty.toLocaleString() : availableDeliveryQty.toLocaleString();
    }

    function setAction(action) {
      currentAction = action;
      const btnBuy = document.getElementById('btnActionBuy');
      const btnSell = document.getElementById('btnActionSell');
      const submitBtn = document.getElementById('btnSubmitOrder');
      if (action === 'BUY') {
        btnBuy.className = 'flex-1 py-3 text-center border-b-2 border-emerald-500 text-emerald-600 font-bold transition';
        btnSell.className = 'flex-1 py-3 text-center border-b-2 border-transparent text-slate-400 hover:text-slate-600 font-bold transition';
        submitBtn.className = 'w-full py-3 rounded-lg font-bold text-sm text-white bg-emerald-600 hover:bg-emerald-700 shadow transition';
        submitBtn.innerText = 'Submit Buy Order';
      } else {
        btnSell.className = 'flex-1 py-3 text-center border-b-2 border-rose-500 text-rose-600 font-bold transition';
        btnBuy.className = 'flex-1 py-3 text-center border-b-2 border-transparent text-slate-400 hover:text-slate-600 font-bold transition';
        submitBtn.className = 'w-full py-3 rounded-lg font-bold text-sm text-white bg-rose-600 hover:bg-rose-700 shadow transition';
        submitBtn.innerText = 'Submit Sell / Square-off';
      }
      recalcOrderRequirement();
    }

    function setProduct(prod) {
      currentProduct = prod;
      ['mtf', 'delivery', 'intraday'].forEach(p => {
        const el = document.getElementById('prod-' + p);
        if (p === prod) {
          el.className = 'flex-1 py-1.5 rounded-lg border text-xs font-semibold bg-slate-900 border-slate-900 text-white transition';
        } else {
          el.className = 'flex-1 py-1.5 rounded-lg border text-xs font-semibold border-slate-200 text-slate-600 hover:bg-slate-50 transition';
        }
      });
      updateAvailableQtyUI();
      recalcOrderRequirement();
    }

    function onPriceTypeChange() {
      const type = document.getElementById('selectPriceType').value;
      const inp = document.getElementById('inputPrice');
      if (type === 'MARKET') {
        inp.disabled = true;
        inp.value = '';
        inp.placeholder = 'Market';
        inp.classList.add('bg-slate-50', 'text-slate-400');
      } else {
        inp.disabled = false;
        inp.placeholder = 'Limit';
        inp.value = currentLTP > 0 ? currentLTP.toFixed(2) : '';
        inp.classList.remove('bg-slate-50', 'text-slate-400');
      }
      recalcOrderRequirement();
    }

    function recalcOrderRequirement() {
      const qty = parseFloat(document.getElementById('inputQty').value) || 0;
      const priceType = document.getElementById('selectPriceType').value;
      let effectivePrice = currentLTP;
      if (priceType === 'LIMIT') {
        effectivePrice = parseFloat(document.getElementById('inputPrice').value) || currentLTP;
      }
      const rawTotal = qty * effectivePrice;
      document.getElementById('approxReq').innerText = '₹' + rawTotal.toLocaleString('en-IN', {
        minimumFractionDigits: 2, maximumFractionDigits: 2
      });
    }

    async function executeOrder() {
      const qty = parseInt(document.getElementById('inputQty').value);
      if (!qty || qty <= 0) return;
      const priceType = document.getElementById('selectPriceType').value;
      let price = 0;
      if (priceType === 'LIMIT') {
        price = parseFloat(document.getElementById('inputPrice').value) || 0;
        if (price <= 0) return;
      }
      const payload = {
        stock_code: selectedStock,
        action: currentAction.toLowerCase(),
        product: currentProduct,
        order_type: priceType.toLowerCase(),
        quantity: qty,
        price: price
      };

      const msgEl = document.getElementById('orderStatusMsg');
      msgEl.className = 'text-center text-xs font-semibold py-2 px-3 rounded-lg bg-blue-50 text-blue-700 border border-blue-200';
      msgEl.innerText = 'Submitting order to ICICI...';
      msgEl.classList.remove('hidden');

      try {
        const res = await fetch('/api/place_order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const d = await res.json();
        if (d.success) {
          msgEl.className = 'text-center text-xs font-semibold py-2 px-3 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200';
          msgEl.innerText = `Success: Order ID ${d.order_id || 'Submitted'}`;
          refreshData(true);
        } else {
          msgEl.className = 'text-center text-xs font-semibold py-2 px-3 rounded-lg bg-rose-50 text-rose-700 border border-rose-200';
          msgEl.innerText = `Failed: ${d.message || 'Rejected'}`;
        }
      } catch (err) {
        msgEl.className = 'text-center text-xs font-semibold py-2 px-3 rounded-lg bg-rose-50 text-rose-700 border border-rose-200';
        msgEl.innerText = 'Network error during submission.';
      }
    }

    async function refreshData(force = true) {
      const syncIcon = document.getElementById('syncIcon');
      if (syncIcon) syncIcon.classList.add('spin');
      try {
        await initOrderPad(force);
        await fetchQuote();
      } finally {
        if (syncIcon) syncIcon.classList.remove('spin');
      }
    }

    window.addEventListener('DOMContentLoaded', () => {
      initOrderPad(false);
      // Auto-poll bootstrap every 8 seconds
      setInterval(() => initOrderPad(false), 8000);
      // Auto-poll active quote every 4 seconds
      setInterval(() => fetchQuote(), 4000);
    });
  </script>
</body>
</html>
"""

# --- BACKEND HELPERS ---

def _get_funds_data(breeze):
    try:
        res = breeze.get_funds()
        if res and res.get("Success"):
            s = res["Success"]
            balance = float(s.get("allocated_equity") or s.get("total_bank_balance") or 0.0)
            return {"balance": balance}
    except Exception as e:
        print(f"[-] Funds error: {e}")
    return {"balance": 0.0}

def _get_holdings_data(breeze, positions_cached=None):
    consolidated = {}
    try:
        items = positions_cached
        if items is None:
            pos_res = breeze.get_portfolio_positions()
            items = pos_res.get("Success") if (pos_res and isinstance(pos_res, dict)) else []
        
        if isinstance(items, list):
            unique_codes = list({
                str(it.get("stock_code") or "").upper().strip()
                for it in items if it.get("stock_code")
            })

            missing_codes = [c for c in unique_codes if c not in COMPANY_NAMES_CACHE]
            if missing_codes:
                with ThreadPoolExecutor(max_workers=6) as executor:
                    executor.map(lambda c: resolve_single_stock_name(breeze, c), missing_codes)

            for it in items:
                sym = str(it.get("stock_code") or "").upper().strip()
                if not sym:
                    continue

                full_name = COMPANY_NAMES_CACHE.get(sym, sym)
                qty = float(parse_num(it.get("quantity") or 0))
                if qty <= 0:
                    continue

                avg_p = float(parse_num(it.get("average_price") or 0))
                ltp = float(parse_num(it.get("ltp") or 0))
                pnl = float(parse_num(it.get("pnl") or 0))
                p_type = str(it.get("product_type") or "").lower()

                invested_part = qty * avg_p
                current_part = qty * (ltp if ltp > 0 else avg_p)

                mtf_qty = qty if ("margin" in p_type or "mtf" in p_type) else 0
                deliv_qty = qty if ("margin" not in p_type and "mtf" not in p_type) else 0

                if sym not in consolidated:
                    consolidated[sym] = {
                        "stock_code": sym,
                        "company_name": full_name,
                        "quantity": qty,
                        "mtf_qty": mtf_qty,
                        "delivery_qty": deliv_qty,
                        "total_invested": invested_part,
                        "total_current": current_part,
                        "ltp": ltp,
                        "pnl": pnl,
                        "lots_count": 1
                    }
                else:
                    consolidated[sym]["quantity"] += qty
                    consolidated[sym]["mtf_qty"] += mtf_qty
                    consolidated[sym]["delivery_qty"] += deliv_qty
                    consolidated[sym]["total_invested"] += invested_part
                    consolidated[sym]["total_current"] += current_part
                    consolidated[sym]["pnl"] += pnl
                    consolidated[sym]["lots_count"] += 1
                    if ltp > 0:
                        consolidated[sym]["ltp"] = ltp
    except Exception as e:
        print(f"[-] Positions error: {e}")

    result = []
    for sym, data in consolidated.items():
        qty = data["quantity"]
        tot_inv = data["total_invested"]
        tot_cur = data["total_current"]
        avg_price = (tot_inv / qty) if qty > 0 else 0.0
        ltp = data["ltp"]
        pnl = data["pnl"]
        pnl_pct = (pnl / tot_inv * 100) if tot_inv > 0 else 0.0

        result.append({
            "stock_code": sym,
            "company_name": data["company_name"],
            "quantity": int(qty),
            "mtf_qty": int(data["mtf_qty"]),
            "delivery_qty": int(data["delivery_qty"]),
            "average_price": round(avg_price, 2),
            "ltp": round(ltp, 2),
            "total_invested": round(tot_inv, 2),
            "total_current": round(tot_cur, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "lots_count": data["lots_count"]
        })

    result.sort(key=lambda x: x["total_current"], reverse=True)
    return result

def _get_orders_data(breeze, positions_cached=None):
    orders_list = []
    try:
        order_res = breeze.get_order_list(exchange_code="NSE")
        items = order_res.get("Success") if (order_res and isinstance(order_res, dict)) else []
        if isinstance(items, list):
            for o in items:
                sym = str(o.get("stock_code") or "").upper().strip()
                if not sym:
                    continue

                full_name = COMPANY_NAMES_CACHE.get(sym, sym)
                stoploss = float(parse_num(o.get("stoploss") or o.get("trigger_price") or o.get("stoploss_trigger") or 0))
                o_type = str(o.get("order_type") or "Limit").strip()
                is_trigger = (stoploss > 0) or ("stoploss" in o_type.lower()) or ("sl" in o_type.lower()) or ("gtt" in o_type.lower())

                tag = "REGULAR"
                if is_trigger:
                    tag = "GTT / TRIGGER" if "gtt" in o_type.lower() else "SL-TRIGGER"

                orders_list.append({
                    "order_id": str(o.get("order_id") or ""),
                    "stock_code": sym,
                    "company_name": full_name,
                    "action": str(o.get("action") or "").upper(),
                    "product": str(o.get("product") or o.get("product_type") or "MTF"),
                    "order_type": o_type,
                    "quantity": int(float(parse_num(o.get("quantity") or 0))),
                    "price": float(parse_num(o.get("price") or 0)),
                    "trigger_price": stoploss,
                    "is_trigger": is_trigger,
                    "order_tag": tag,
                    "status": str(o.get("status") or o.get("order_status") or "Executed"),
                    "order_date": str(o.get("order_date") or o.get("order_time") or "")
                })
    except Exception as e:
        print(f"[-] Order list error: {e}")

    try:
        items = positions_cached
        if items is None:
            pos_res = breeze.get_portfolio_positions()
            items = pos_res.get("Success") if (pos_res and isinstance(pos_res, dict)) else []
        if isinstance(items, list):
            for it in items:
                sl_trig = float(parse_num(it.get("stoploss_trigger") or it.get("stoploss") or 0))
                if sl_trig > 0:
                    sym = str(it.get("stock_code") or "").upper().strip()
                    full_name = COMPANY_NAMES_CACHE.get(sym, sym)
                    orders_list.append({
                        "order_id": str(it.get("order_id") or "MTF-SL"),
                        "stock_code": sym,
                        "company_name": full_name,
                        "action": "SELL",
                        "product": "MTF",
                        "order_type": "SL-Trigger",
                        "quantity": int(float(parse_num(it.get("quantity") or 0))),
                        "price": sl_trig,
                        "trigger_price": sl_trig,
                        "is_trigger": True,
                        "order_tag": "MTF-TRIGGER",
                        "status": "Trigger Active",
                        "order_date": str(it.get("mtf_expiry_date") or "")
                    })
    except Exception as e:
        print(f"[-] Positions trigger scan error: {e}")

    return orders_list

# --- ROUTES ---

@trade_bp.route("/trade")
def view_trade():
    return render_template_string(TRADE_PAGE_HTML, active_page="trade", session_token_short=get_short_token())

@trade_bp.route("/api/trade_bootstrap")
def api_trade_bootstrap():
    breeze, is_auth = get_breeze_client()
    if not is_auth or not breeze:
        return jsonify({"funds": {"balance": 0.0}, "holdings": [], "orders": []})

    positions_cached = []
    try:
        pos_res = breeze.get_portfolio_positions()
        if pos_res and isinstance(pos_res, dict):
            positions_cached = pos_res.get("Success") or []
    except Exception as e:
        print(f"[-] Cached positions fetch error: {e}")

    with ThreadPoolExecutor(max_workers=3) as executor:
        f_funds = executor.submit(_get_funds_data, breeze)
        f_holdings = executor.submit(_get_holdings_data, breeze, positions_cached)
        f_orders = executor.submit(_get_orders_data, breeze, positions_cached)

        funds_data = f_funds.result()
        holdings_data = f_holdings.result()
        orders_data = f_orders.result()

    return jsonify({
        "funds": funds_data,
        "holdings": holdings_data,
        "orders": orders_data
    })

@trade_bp.route("/api/trade_holdings")
def api_trade_holdings():
    breeze, is_auth = get_breeze_client()
    if not is_auth or not breeze:
        return jsonify({"data": []})
    return jsonify({"data": _get_holdings_data(breeze)})

@trade_bp.route("/api/stock_orders")
def api_stock_orders():
    breeze, is_auth = get_breeze_client()
    if not is_auth or not breeze:
        return jsonify({"data": []})
    return jsonify({"data": _get_orders_data(breeze)})

@trade_bp.route("/api/funds")
def api_funds():
    breeze, is_auth = get_breeze_client()
    if not is_auth or not breeze:
        return jsonify({"balance": 0.0})
    return jsonify(_get_funds_data(breeze))

@trade_bp.route("/api/quote")
def api_quote():
    stock_code = request.args.get("stock_code", "").upper().strip()
    if not stock_code:
        return jsonify({"ltp": 0.0, "change_pct": 0.0})

    breeze, is_auth = get_breeze_client()
    if not is_auth or not breeze:
        return jsonify({"ltp": 0.0, "change_pct": 0.0})

    try:
        res = breeze.get_quotes(stock_code=stock_code, exchange_code="NSE", product_type="cash")
        if res and res.get("Success") and len(res["Success"]) > 0:
            q = res["Success"][0]
            ltp = float(parse_num(q.get("ltp") or 0.0))
            close = float(parse_num(q.get("close") or q.get("previous_close") or 0.0))
            pct = round(((ltp - close) / close * 100), 2) if close > 0 else 0.0
            return jsonify({"ltp": ltp, "change_pct": pct})
    except Exception as e:
        print(f"[-] Quote error: {e}")
    return jsonify({"ltp": 0.0, "change_pct": 0.0})

@trade_bp.route("/api/place_order", methods=["POST"])
def api_place_order():
    data = request.get_json() or {}
    stock_code = str(data.get("stock_code") or "").upper().strip()
    action = str(data.get("action") or "buy").lower().strip()
    prod_type = str(data.get("product") or "mtf").strip()
    order_type = str(data.get("order_type") or "market").lower().strip()
    qty = str(data.get("quantity") or "1").strip()
    price = str(data.get("price") or "0").strip()

    if not stock_code:
        return jsonify({"success": False, "message": "No stock code specified."})

    breeze_prod = "margin" if prod_type in ["intraday", "mtf"] else "cash"

    breeze, is_auth = get_breeze_client()
    if not is_auth or not breeze:
        return jsonify({"success": False, "message": "Session expired."})

    try:
        resp = breeze.place_order(
            stock_code=stock_code,
            exchange_code="NSE",
            product=breeze_prod,
            action=action,
            order_type=order_type,
            stoploss="0",
            quantity=qty,
            price=price if order_type == "limit" else "0",
            validity="day"
        )
        if resp and resp.get("Success"):
            order_id = resp["Success"].get("order_id", "SUBMITTED")
            # Invalidate memory cache so next poll gets fresh state
            clear_memory_cache()
            return jsonify({"success": True, "order_id": order_id})
        else:
            err = resp.get("Error") or resp.get("message") or "Exchange rejected"
            return jsonify({"success": False, "message": str(err)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})