from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from flask import Blueprint, jsonify, render_template_string, request
from breeze_core import (
    COMPANY_NAMES_CACHE,
    FROM_DATE,
    LOGIN_URL,
    NAVBAR_HTML,
    extract_order_seq,
    get_breeze_client,
    get_or_set_cache,
    normalize_product_category,
    parse_date,
    parse_num,
    resolve_single_stock_name,
)

delivery_bp = Blueprint("delivery", __name__)

DELIVERY_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Unified Stock & Delivery Ledger</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; }
    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: #f8fafc; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
    .spin { animation: spin 0.7s linear infinite; }
    @keyframes spin { 100% { transform: rotate(360deg); } }
  </style>
</head>
<body class="bg-slate-100 text-slate-800 antialiased h-screen w-screen overflow-hidden flex flex-col">
  """ + NAVBAR_HTML + """
  
  <div class="flex-1 flex overflow-hidden relative">
    
    <!-- LEFT SIDEBAR: STOCKS LIST -->
    <aside class="w-80 bg-white border-r border-slate-200 flex flex-col h-full shrink-0 z-10 shadow-xs">
      
      <!-- PORTFOLIO SUMMARY KPI HEADER -->
      <div class="p-3.5 bg-slate-900 text-white border-b border-slate-800">
        <div class="flex justify-between items-center mb-1">
          <span class="text-[10px] font-bold uppercase tracking-wider text-teal-400 flex items-center gap-1">
            <span class="material-icons text-xs">account_balance</span> Total Position Value
          </span>
          <span id="headerPnlBadge" class="text-xs px-2 py-0.5 rounded font-black bg-emerald-500/20 text-emerald-300">
            +0.00%
          </span>
        </div>
        <div class="text-2xl font-black tracking-tight" id="portfolioCurrentVal">₹0.00</div>
        
        <div class="grid grid-cols-2 gap-2 mt-2.5 pt-2 border-t border-slate-800 text-[11px]">
          <div>
            <div class="text-slate-400">Total Invested</div>
            <div class="font-bold text-slate-200" id="portfolioInvestedVal">₹0.00</div>
          </div>
          <div class="text-right">
            <div class="text-slate-400">Unrealized P&L</div>
            <div class="font-bold text-emerald-400" id="portfolioTotalPnl">+₹0.00</div>
          </div>
        </div>
      </div>

      <!-- SEARCH & SORT CONTROLS -->
      <div class="p-2.5 border-b border-slate-200 bg-white space-y-2">
        <div class="relative">
          <span class="material-icons absolute left-2 top-2 text-slate-400 text-sm">search</span>
          <input type="text" id="searchStock" oninput="renderStockList()" placeholder="Filter symbol or company..." 
            class="w-full bg-slate-50 border border-slate-200 rounded pl-7 pr-2.5 py-1 text-xs text-slate-800 focus:outline-none focus:border-teal-500 font-semibold">
        </div>

        <div class="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
          <div class="flex items-center gap-1 font-semibold">
            <span>Sort:</span>
            <select id="sortParamSelect" onchange="changeSortParam()" class="bg-slate-50 border border-slate-200 rounded px-1.5 py-0.5 text-slate-700 font-bold focus:outline-none focus:border-teal-500">
              <option value="company_name" selected>Name (A-Z)</option>
              <option value="stock_code">Symbol</option>
              <option value="total_current">Current Value</option>
              <option value="quantity">Total Qty</option>
              <option value="pnl">P&L (₹)</option>
              <option value="pnl_pct">P&L (%)</option>
            </select>
          </div> 
          <button id="sortOrderBtn" onclick="toggleSortOrder()" class="flex items-center gap-0.5 px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 font-bold text-slate-700 transition">
            <span id="sortOrderIcon" class="material-icons text-xs">arrow_downward</span>
            <span id="sortOrderLabel">A → Z</span>
          </button>
        </div>
      </div>
      
      <!-- ALL STOCKS BUTTON -->
      <div class="p-1.5 border-b border-slate-200">
        <button onclick="selectStock('ALL')" id="tab-ALL" class="stock-tab w-full text-left p-2 rounded flex items-center justify-between text-xs font-semibold bg-teal-50 text-teal-800 border border-teal-200">
          <span class="font-black flex items-center gap-1.5">
            <span class="material-icons text-xs text-teal-600">domain</span> All Positions
          </span>
          <span id="badge-all-count" class="text-[10px] px-1.5 py-0.2 rounded bg-teal-200 text-teal-900 font-bold">0</span>
        </button>
      </div>

      <!-- STOCKS SCROLL LIST -->
      <div id="stockListContainer" class="flex-1 overflow-y-auto p-1.5 space-y-1"></div>

      <!-- FOOTER REFRESH -->
      <div class="p-2 border-t border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-500 flex justify-between items-center">
        <span>Position Ledger</span>
        <button onclick="refreshData(true)" title="Sync Data" class="flex items-center gap-1 px-2 py-1 hover:bg-slate-200 rounded text-slate-700 transition">
          <span id="refreshIcon" class="material-icons text-xs">sync</span> Refresh
        </button>
      </div>
    </aside>

    <!-- MAIN WORKSPACE -->
    <main class="flex-1 flex flex-col h-full bg-slate-50 min-w-0 relative">
      
      <!-- TOP STATUS BAR -->
      <div class="p-3 bg-white border-b border-slate-200 flex items-center justify-between shrink-0 shadow-xs flex-wrap gap-2">
        <div class="flex items-center gap-3">
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-base font-extrabold text-slate-900 leading-tight" id="selectedStockTitle">All Scrips</h2>
              <span class="text-[10px] px-1.5 py-0.2 rounded font-bold bg-teal-100 text-teal-800 border border-teal-200">
                COMPLETE TRADE HISTORY
              </span>
            </div>
            <div class="text-[11px] text-slate-400 font-medium truncate max-w-[320px]" id="selectedStockSubtitle">Cash Delivery, MTF, and MTF-to-Demat fills with running average</div>
          </div>
        </div>

        <!-- SUMMARY STATS TILES -->
        <div class="flex items-center gap-2 flex-wrap">
          <!-- DEMAT COUNT BADGE -->
          <div class="bg-teal-50 border border-teal-200 px-2.5 py-1 rounded text-right">
            <div class="text-[9px] uppercase font-bold text-teal-600">Demat Qty</div>
            <div class="text-xs font-black text-teal-900" id="summaryDematQty">0</div>
          </div>

          <!-- MTF COUNT BADGE -->
          <div class="bg-amber-50 border border-amber-200 px-2.5 py-1 rounded text-right">
            <div class="text-[9px] uppercase font-bold text-amber-600">MTF Qty</div>
            <div class="text-xs font-black text-amber-900" id="summaryMtfQty">0</div>
          </div>

          <!-- INTRADAY COUNT BADGE -->
          <div class="bg-indigo-50 border border-indigo-200 px-2.5 py-1 rounded text-right">
            <div class="text-[9px] uppercase font-bold text-indigo-600">Intraday Trades</div>
            <div class="text-xs font-black text-indigo-900" id="summaryIntradayCount">0</div>
          </div>

          <div class="bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-right">
            <div class="text-[9px] uppercase font-bold text-slate-600">Total Qty</div>
            <div class="text-xs font-black text-slate-900" id="summaryTotalQty">0</div>
          </div>
          <div class="bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-right">
            <div class="text-[9px] uppercase font-bold text-slate-400">Avg Cost</div>
            <div class="text-xs font-bold text-slate-800" id="summaryAvgPrice">₹0.00</div>
          </div>
          <div class="bg-blue-50 border border-blue-200 px-2.5 py-1 rounded text-right">
            <div class="text-[9px] uppercase font-bold text-blue-500">Current Value</div>
            <div class="text-xs font-bold text-blue-700" id="summaryCurrentVal">₹0.00</div>
          </div>
          <div class="bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-right">
            <div class="text-[9px] uppercase font-bold text-slate-400">Total Invested</div>
            <div class="text-xs font-bold text-slate-800" id="summaryTotalInvested">₹0.00</div>
          </div>
        </div>
      </div>

      <!-- MAIN LEDGER TABLE CONTAINER -->
      <div class="flex-1 overflow-y-auto p-3 pb-24 space-y-4">
        <div class="bg-white border border-slate-200 rounded-lg shadow-xs overflow-hidden">
          <table class="w-full text-left border-collapse text-xs">
            <thead class="sticky top-0 bg-slate-100 border-b border-slate-200 z-10 font-semibold text-slate-600">
              <tr>
                <th class="py-2.5 px-3 w-8 text-center">
                  <input type="checkbox" id="selectAllLedger" onchange="toggleSelectAllLedger(this.checked)"
                    class="rounded border-slate-300 text-teal-600">
                </th>
                <th class="py-2.5 px-3">Date</th>
                <th class="py-2.5 px-3">Product / Channel</th>
                <th class="py-2.5 px-3 th-stock">Stock</th>
                <th class="py-2.5 px-3 text-center">Side</th>
                <th class="py-2.5 px-3 text-right">Qty</th>
                <th class="py-2.5 px-3 text-right">Price</th>
                <th class="py-2.5 px-3 text-right">Trade Amount</th>
                <th class="py-2.5 px-3 text-right bg-slate-50 text-slate-800 font-bold border-l border-slate-200">Running Qty</th>
                <th class="py-2.5 px-3 text-right bg-teal-50/50 text-teal-950 font-bold border-l border-teal-100">Running Avg</th>
              </tr>
            </thead>
            <tbody id="transactionsBody" class="divide-y divide-slate-100 text-slate-700"></tbody>
          </table>
        </div>
      </div>

      <!-- FOOTER STATS FOR SELECTED ROWS -->
      <div id="selectionStatsFooter" class="hidden absolute bottom-3 left-3 right-3 bg-slate-900 text-white rounded-lg shadow-xl border border-slate-800 p-2.5 z-30">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div class="text-xs font-bold text-slate-200">
            <span id="footerSelectedCount" class="text-teal-400 font-extrabold text-sm">0</span> Selected
          </div>
          <div class="flex items-center gap-2 text-xs flex-wrap" id="footerStatsContainer"></div>
          <button onclick="clearAllSelections()" class="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded border border-slate-700">Clear</button>
        </div>
      </div>
    </main>
  </div>

  <script>
    let STOCKS = [];
    let RAW_TRADES_LIST = [];
    let PROCESSED_LEDGER = [];
    let COMPANY_NAMES = {};
    let currentFilter = 'ALL';
    let currentSortParam = 'company_name';
    let isSortDesc = false;

    let selectedLedgerIndices = new Set();
    let isPolling = false;

    function renderProductBadge(badgeType) {
      if (badgeType === 'MTF_CONVERTED') {
        return `<span class="px-1.5 py-0.5 rounded text-[10px] font-black bg-purple-100 text-purple-800 border border-purple-200" title="MTF purchase converted to Demat Delivery">MTF → DEMAT</span>`;
      } else if (badgeType === 'INTRADAY') {
        return `<span class="px-1.5 py-0.5 rounded text-[10px] font-black bg-slate-100 text-slate-700 border border-slate-200">INTRADAY</span>`;
      } else if (badgeType === 'MTF') {
        return `<span class="px-1.5 py-0.5 rounded text-[10px] font-black bg-amber-100 text-amber-800 border border-amber-200">MTF MARGIN</span>`;
      }
      return `<span class="px-1.5 py-0.5 rounded text-[10px] font-black bg-teal-100 text-teal-800 border border-teal-200">CASH DELIVERY</span>`;
    }

    async function loadDeliveryData(force = false) {
      if (isPolling) return;
      isPolling = true;
      const refIcon = document.getElementById('refreshIcon');
      if (refIcon) refIcon.classList.add('spin');

      try {
        const url = '/api/delivery_data' + (force ? '?force=1' : '');
        const res = await fetch(url);
        const d = await res.json();

        RAW_TRADES_LIST = d.trades || [];
        COMPANY_NAMES = d.company_names || {};
        const ltpMap = d.ltp_map || {};

        recomputeRunningMetrics();

        const brokerMtf = d.mtf_positions || {};

        const byStock = {};
        PROCESSED_LEDGER.forEach(t => {
          if (!byStock[t.stock]) byStock[t.stock] = [];
          byStock[t.stock].push(t);
        });

        const allSymbols = new Set([
          ...Object.keys(brokerMtf),
          ...Object.keys(byStock)
        ]);

        const stocksAgg = [];
        allSymbols.forEach(sym => {
          const stockTrades = byStock[sym] || [];
          
          let finalQ = 0;
          let avgPrice = 0;

          if (stockTrades.length > 0) {
            const latest = stockTrades.reduce((prev, curr) => (curr.intraStockIndex > prev.intraStockIndex) ? curr : prev, stockTrades[0]);
            finalQ = latest.runningQty;
            avgPrice = latest.runningAvg;
          }

          const mtfQ = brokerMtf[sym]?.quantity || 0;
          const dematQ = Math.max(0, finalQ - mtfQ);
          const cmp = ltpMap[sym] || avgPrice;

          const isSettled = finalQ === 0;
          const invested = finalQ * avgPrice;
          const current = finalQ * cmp;
          const pnl = isSettled ? 0 : (current - invested);
          const pnlPct = invested > 0 ? (pnl / invested * 100) : 0;

          stocksAgg.push({
            stock_code: sym,
            company_name: COMPANY_NAMES[sym] || sym,
            quantity: finalQ,
            demat_qty: dematQ,
            mtf_qty: mtfQ,
            average_price: avgPrice,
            current_market_price: cmp,
            total_invested: invested,
            total_current: current,
            pnl: pnl,
            pnl_pct: pnlPct,
            is_settled: isSettled
          });
        });

        STOCKS = stocksAgg;

        updatePortfolioSummary();
        renderStockList();
        renderWorkspace();

        const syncEl = document.getElementById('syncStatusLabel');
        if (syncEl) syncEl.innerText = new Date().toLocaleTimeString();
      } catch (err) {
        console.error("Delivery fetch failed:", err);
      } finally {
        if (refIcon) refIcon.classList.remove('spin');
        isPolling = false;
      }
    }

    function refreshData(force = true) {
      loadDeliveryData(force);
    }

    function recomputeRunningMetrics() {
      const byStock = {};
      RAW_TRADES_LIST.forEach(t => {
        if (!byStock[t.stock]) byStock[t.stock] = [];
        byStock[t.stock].push(t);
      });

      const compiled = [];

      for (const sym in byStock) {
        const trades = byStock[sym];

        const dateGroups = {};
        trades.forEach(t => {
          if (!dateGroups[t.date]) dateGroups[t.date] = [];
          dateGroups[t.date].push(t);
        });

        const sortedDates = Object.keys(dateGroups).sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

        let currentQty = 0;
        let totalCostBasis = 0;
        let intraStockIndex = 0;

        for (const dt of sortedDates) {
          const dayTrades = dateGroups[dt];

          dayTrades.sort((a, b) => {
            if (a.type !== b.type) {
              return a.type === 'BUY' ? -1 : 1;
            }
            const seqA = a.order_seq !== undefined ? a.order_seq : -1;
            const seqB = b.order_seq !== undefined ? b.order_seq : -1;
            if (seqA !== -1 && seqB !== -1 && seqA !== seqB) return seqA - seqB;
            return String(a.order_id || '').localeCompare(String(b.order_id || ''));
          });

          for (const t of dayTrades) {
            const isBuy = t.type === 'BUY';
            const qty = Number(t.quantity) || 0;
            const price = Number(t.price) || 0;
            const tradeAmt = Number(t.tradeAmount) || (qty * price);

            if (isBuy) {
              currentQty += qty;
              totalCostBasis += tradeAmt;
            } else {
              const avgPrior = currentQty > 0 ? (totalCostBasis / currentQty) : 0;
              currentQty = Math.max(0, currentQty - qty);
              totalCostBasis = currentQty * avgPrior;
            }

            const runningAvg = currentQty > 0 ? (totalCostBasis / currentQty) : 0;

            compiled.push({
              ...t,
              intraStockIndex: intraStockIndex++,
              runningQty: currentQty,
              runningAvg: runningAvg
            });
          }
        }
      }

      PROCESSED_LEDGER = compiled;
    }

    function getDisplayLedger() {
      if (currentFilter !== 'ALL') {
        const filtered = PROCESSED_LEDGER.filter(t => t.stock === currentFilter);
        return filtered.sort((a, b) => {
          const dtA = new Date(a.date).getTime();
          const dtB = new Date(b.date).getTime();
          if (dtA !== dtB) return dtB - dtA;
          return (b.intraStockIndex || 0) - (a.intraStockIndex || 0);
        });
      } else {
        return [...PROCESSED_LEDGER].sort((a, b) => {
          const dtA = new Date(a.date).getTime();
          const dtB = new Date(b.date).getTime();
          if (dtA !== dtB) return dtB - dtA;
          if (a.stock !== b.stock) {
            return String(a.stock).localeCompare(String(b.stock));
          }
          return (b.intraStockIndex || 0) - (a.intraStockIndex || 0);
        });
      }
    }

    function updatePortfolioSummary() {
      let totInvested = 0, totCurrent = 0, totPnl = 0;
      STOCKS.forEach(s => {
        totInvested += Number(s.total_invested || 0);
        totCurrent += Number(s.total_current || 0);
        totPnl += Number(s.pnl || 0);
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
      if (currentSortParam === 'company_name' || currentSortParam === 'stock_code') {
        isSortDesc = false;
        document.getElementById('sortOrderIcon').innerText = 'arrow_downward';
        document.getElementById('sortOrderLabel').innerText = 'A → Z';
      } else {
        isSortDesc = true;
        document.getElementById('sortOrderIcon').innerText = 'arrow_downward';
        document.getElementById('sortOrderLabel').innerText = 'High → Low';
      }
      renderStockList();
    }

    function toggleSortOrder() {
      isSortDesc = !isSortDesc;
      const icon = document.getElementById('sortOrderIcon');
      const label = document.getElementById('sortOrderLabel');
      
      if (currentSortParam === 'company_name' || currentSortParam === 'stock_code') {
        if (isSortDesc) {
          icon.innerText = 'arrow_upward';
          label.innerText = 'Z → A';
        } else {
          icon.innerText = 'arrow_downward';
          label.innerText = 'A → Z';
        }
      } else {
        if (isSortDesc) {
          icon.innerText = 'arrow_downward';
          label.innerText = 'High → Low';
        } else {
          icon.innerText = 'arrow_upward';
          label.innerText = 'Low → High';
        }
      }
      renderStockList();
    }

    function selectStock(sym) {
      currentFilter = sym;
      document.querySelectorAll('.stock-tab').forEach(el => {
        el.classList.remove('bg-teal-50', 'text-teal-800', 'border-teal-200');
        el.classList.add('text-slate-600', 'border-transparent');
      });
      const activeBtn = document.getElementById('tab-' + sym);
      if (activeBtn) {
        activeBtn.classList.add('bg-teal-50', 'text-teal-800', 'border-teal-200');
        activeBtn.classList.remove('border-transparent');
      }
      renderWorkspace();
      updateSelectionStatsFooter();
    }

    function renderStockList() {
      const q = (document.getElementById('searchStock').value || '').toUpperCase().trim();
      const container = document.getElementById('stockListContainer');
      document.getElementById('badge-all-count').innerText = STOCKS.length;

      let list = [...STOCKS];
      if (q) {
        list = list.filter(s => {
          const name = (s.company_name || '').toUpperCase();
          return s.stock_code.includes(q) || name.includes(q);
        });
      }

      list.sort((a, b) => {
        let valA = a[currentSortParam];
        let valB = b[currentSortParam];
        if (currentSortParam === 'company_name' || currentSortParam === 'stock_code') {
          return isSortDesc ? String(valB).localeCompare(String(valA)) : String(valA).localeCompare(String(valB));
        }
        valA = Number(valA) || 0;
        valB = Number(valB) || 0;
        return isSortDesc ? (valB - valA) : (valA - valB);
      });

      if (list.length === 0) {
        container.innerHTML = `<div class="p-6 text-center text-slate-400 text-xs">No active positions found.</div>`;
        return;
      }

      // Sidebar items rendered cleanly without Demat/MTF badges
      container.innerHTML = list.map(s => {
        const sym = s.stock_code;
        const isSelected = currentFilter === sym;
        const isSettled = s.quantity === 0;
        const isProfit = (s.pnl || 0) >= 0;
        const holdingVal = Number(s.total_current || 0);

        return `
          <button onclick="selectStock('${sym}')" id="tab-${sym}" 
            class="stock-tab w-full text-left p-2.5 rounded-lg border flex flex-col gap-1 transition ${
              isSelected ? 'bg-teal-50 text-teal-800 border-teal-300 font-semibold shadow-2xs' : 'border-transparent text-slate-700 hover:bg-slate-50'
            }">
            <div class="flex justify-between items-start">
              <div class="min-w-0 pr-2">
                <div class="font-black text-slate-900 flex items-center gap-1.5 flex-wrap">
                  <span>${sym}</span>
                  ${isSettled ? `<span class="text-[9px] px-1 py-0.2 rounded font-bold bg-slate-100 text-slate-500 border border-slate-200">SETTLED</span>` : ''}
                </div>
                <div class="text-[10px] text-slate-400 truncate max-w-[150px]">${s.company_name}</div>
              </div>
              <div class="text-right shrink-0">
                <div class="font-bold text-slate-900">${isSettled ? '₹0.00' : '₹' + holdingVal.toLocaleString('en-IN', {maximumFractionDigits: 0})}</div>
                ${!isSettled ? `
                  <div class="text-[10px] font-bold ${isProfit ? 'text-emerald-600' : 'text-rose-600'}">
                    ${isProfit ? '+' : ''}${Number(s.pnl_pct || 0).toFixed(2)}%
                  </div>
                ` : `<div class="text-[10px] font-semibold text-slate-400">Closed</div>`}
              </div>
            </div>
            <div class="flex justify-between items-center text-[10px] text-slate-500 pt-0.5 border-t border-slate-100/80">
              <span>Total: <b class="text-slate-800">${s.quantity.toLocaleString()} shs</b></span>
              <span>Avg: ₹${Number(s.average_price || 0).toFixed(2)}</span>
            </div>
          </button>
        `;
      }).join('');
    }

    function renderWorkspace() {
      const title = document.getElementById('selectedStockTitle');
      const subtitle = document.getElementById('selectedStockSubtitle');

      title.innerText = currentFilter === 'ALL' ? 'All Positions' : currentFilter;
      subtitle.innerText = currentFilter === 'ALL' ? 'Complete execution history with MTF, Converted & Cash trades' : (COMPANY_NAMES[currentFilter] || currentFilter);

      const isAll = currentFilter === 'ALL';
      document.querySelectorAll('.th-stock').forEach(el => {
        if (isAll) el.classList.remove('hidden');
        else el.classList.add('hidden');
      });

      let relevantStocks = currentFilter === 'ALL' ? STOCKS : STOCKS.filter(s => s.stock_code === currentFilter);
      let totalQty = 0, totalInvested = 0, totalCurrent = 0, totalDematQty = 0, totalMtfQty = 0;

      relevantStocks.forEach(s => {
        totalQty += Number(s.quantity || 0);
        totalDematQty += Number(s.demat_qty || 0);
        totalMtfQty += Number(s.mtf_qty || 0);
        totalInvested += Number(s.total_invested || 0);
        totalCurrent += Number(s.total_current || 0);
      });

      // Calculate Intraday trade executions count for the current scope
      const relevantTrades = isAll ? PROCESSED_LEDGER : PROCESSED_LEDGER.filter(t => t.stock === currentFilter);
      const intradayCount = relevantTrades.filter(t => t.badgeType === 'INTRADAY').length;

      const avgPrice = totalQty > 0 ? (totalInvested / totalQty) : 0;

      // Update workspace header tiles
      document.getElementById('summaryDematQty').innerText = totalDematQty.toLocaleString('en-IN');
      document.getElementById('summaryMtfQty').innerText = totalMtfQty.toLocaleString('en-IN');
      document.getElementById('summaryIntradayCount').innerText = intradayCount.toLocaleString('en-IN');

      document.getElementById('summaryTotalQty').innerText = totalQty.toLocaleString('en-IN');
      document.getElementById('summaryAvgPrice').innerText = '₹' + avgPrice.toFixed(2);
      document.getElementById('summaryCurrentVal').innerText = '₹' + totalCurrent.toLocaleString('en-IN', {maximumFractionDigits: 2});
      document.getElementById('summaryTotalInvested').innerText = '₹' + totalInvested.toLocaleString('en-IN', {maximumFractionDigits: 2});

      renderLedgerTableRows();
      updateSelectionStatsFooter();
    }

    function renderLedgerTableRows() {
      const displayLedger = getDisplayLedger();
      const tbody = document.getElementById('transactionsBody');
      const showStock = currentFilter === 'ALL';

      if (displayLedger.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${showStock ? 10 : 9}" class="text-center py-8 text-slate-400">No trade records found.</td></tr>`;
        return;
      }

      tbody.innerHTML = displayLedger.map(t => {
        const isBuy = t.type === 'BUY';
        const isChecked = selectedLedgerIndices.has(t.originalIndex);

        return `
          <tr class="hover:bg-slate-50 border-b border-slate-100 ${isChecked ? 'bg-teal-50/40' : ''}">
            <td class="py-2.5 px-3 text-center">
              <input type="checkbox" onchange="toggleLedgerSelect(${t.originalIndex}, this.checked)" ${isChecked ? 'checked' : ''}
                class="rounded border-slate-300 text-teal-600">
            </td>
            <td class="py-2.5 px-3 text-slate-500 whitespace-nowrap font-mono text-[11px]">${t.date}</td>
            <td class="py-2.5 px-3 whitespace-nowrap">${renderProductBadge(t.badgeType)}</td>
            ${showStock ? `
              <td class="py-2.5 px-3">
                <div class="font-bold text-slate-900">${t.stock}</div>
                <div class="text-[10px] text-slate-400 truncate max-w-[140px]">${t.companyName || ''}</div>
              </td>
            ` : ''}
            <td class="py-2.5 px-3 text-center">
              <span class="px-1.5 py-0.2 rounded text-[10px] font-bold ${
                isBuy ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
              }">${t.type}</span>
            </td>
            <td class="py-2.5 px-3 text-right font-medium">${t.quantity.toLocaleString()}</td>
            <td class="py-2.5 px-3 text-right">₹${Number(t.price).toFixed(2)}</td>
            <td class="py-2.5 px-3 text-right text-slate-600 font-medium">₹${Number(t.tradeAmount).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
            <td class="py-2.5 px-3 text-right bg-slate-50 font-bold border-l border-slate-200">
              <span class="text-slate-900">${Number(t.runningQty).toLocaleString()}</span>
              <span class="text-[10px] ml-1 ${isBuy ? 'text-emerald-600 font-semibold' : 'text-rose-600 font-semibold'}">
                (${isBuy ? '+' : '-'}${t.quantity})
              </span>
            </td>
            <td class="py-2.5 px-3 text-right bg-teal-50/40 font-bold text-teal-950 border-l border-teal-100">
              ₹${Number(t.runningAvg || 0).toFixed(2)}
            </td>
          </tr>
        `;
      }).join('');
      updateMasterCheckboxState();
    }

    function toggleLedgerSelect(idx, checked) {
      if (checked) selectedLedgerIndices.add(idx);
      else selectedLedgerIndices.delete(idx);
      updateMasterCheckboxState();
      updateSelectionStatsFooter();
    }

    function toggleSelectAllLedger(checked) {
      const displayLedger = getDisplayLedger();
      displayLedger.forEach(t => {
        if (checked) selectedLedgerIndices.add(t.originalIndex);
        else selectedLedgerIndices.delete(t.originalIndex);
      });
      renderLedgerTableRows();
      updateSelectionStatsFooter();
    }

    function clearAllSelections() {
      selectedLedgerIndices.clear();
      renderLedgerTableRows();
      updateMasterCheckboxState();
      updateSelectionStatsFooter();
    }

    function updateMasterCheckboxState() {
      const masterLedger = document.getElementById('selectAllLedger');
      if (!masterLedger) return;
      const displayLedger = getDisplayLedger();
      masterLedger.checked = displayLedger.length > 0 && displayLedger.every(t => selectedLedgerIndices.has(t.originalIndex));
    }

    function updateSelectionStatsFooter() {
      const footer = document.getElementById('selectionStatsFooter');
      const container = document.getElementById('footerStatsContainer');
      const countEl = document.getElementById('footerSelectedCount');

      if (selectedLedgerIndices.size === 0) {
        footer.classList.add('hidden');
        return;
      }
      footer.classList.remove('hidden');
      countEl.innerText = selectedLedgerIndices.size;

      let totalQty = 0, totalAmt = 0, buyQty = 0, buyAmt = 0, sellQty = 0, sellAmt = 0;
      selectedLedgerIndices.forEach(idx => {
        const t = PROCESSED_LEDGER.find(item => item.originalIndex === idx);
        if (!t) return;
        totalQty += t.quantity;
        totalAmt += t.tradeAmount;
        if (t.type === 'BUY') {
          buyQty += t.quantity;
          buyAmt += t.tradeAmount;
        } else {
          sellQty += t.quantity;
          sellAmt += t.tradeAmount;
        }
      });
      const buyAvg = buyQty > 0 ? buyAmt / buyQty : 0;
      const sellAvg = sellQty > 0 ? sellAmt / sellQty : 0;

      container.innerHTML = `
        <div class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
          <span class="text-slate-400">Total Shares:</span> <span class="font-bold text-slate-200">${totalQty.toLocaleString()}</span>
        </div>
        <div class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
          <span class="text-slate-400">Volume Turnover:</span> <span class="font-bold text-teal-300">₹${totalAmt.toLocaleString('en-IN', {maximumFractionDigits: 2})}</span>
        </div>
        <div class="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/40">
          <span class="text-emerald-400">Buy Avg (${buyQty}):</span> <span class="font-bold text-emerald-300">₹${buyAvg.toFixed(2)}</span>
        </div>
        <div class="px-2 py-0.5 rounded bg-rose-950/60 border border-rose-800/40">
          <span class="text-rose-400">Sell Avg (${sellQty}):</span> <span class="font-bold text-rose-300">₹${sellAvg.toFixed(2)}</span>
        </div>
      `;
    }

    window.addEventListener('DOMContentLoaded', () => {
      loadDeliveryData(false);
      setInterval(() => loadDeliveryData(false), 10000);
    });
  </script>
</body>
</html>
"""

# --- BACKEND LOGIC & DATA PROCESSORS ---

def fetch_delivery_data():
    breeze, is_auth = get_breeze_client()
    if not is_auth or not breeze:
        return {"error": "SESSION_EXPIRED", "login_url": LOGIN_URL}

    to_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    def fetch_demat_holdings():
        try:
            return breeze.get_portfolio_holdings(exchange_code="NSE")
        except Exception as e:
            print(f"[-] Demat holdings error: {e}")
            return None

    def fetch_positions():
        try:
            return breeze.get_portfolio_positions()
        except Exception as e:
            print(f"[-] Positions error: {e}")
            return None

    def fetch_trades(ex):
        try:
            res = breeze.get_trade_list(
                from_date=FROM_DATE,
                to_date=to_date,
                exchange_code=ex,
                product_type=""
            )
            return ex, res
        except Exception as e:
            print(f"[-] Trade fetch error ({ex}): {e}")
            return ex, None

    raw_trades = []
    active_mtf_settlements = {}
    mtf_positions = {}
    demat_holdings = {}
    ltp_map = {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        f_demat = executor.submit(fetch_demat_holdings)
        f_pos = executor.submit(fetch_positions)
        f_trades = [executor.submit(fetch_trades, ex) for ex in ["NSE", "BSE"]]

        pos_resp = f_pos.result()
        if pos_resp and isinstance(pos_resp.get("Success"), list):
            for p in pos_resp["Success"]:
                p_type = str(p.get("product_type") or "").strip().upper()
                if p_type in ["EASYMARGIN", "MARGIN", "MTF"]:
                    sym = str(p.get("stock_code") or "").strip().upper()
                    q = float(parse_num(p.get("quantity") or 0))
                    avg_p = float(parse_num(p.get("average_price") or 0))
                    ltp = float(parse_num(p.get("ltp") or 0))
                    settle_id = str(p.get("settlement_id") or "").strip()

                    if ltp > 0:
                        ltp_map[sym] = ltp

                    if q > 0:
                        if sym not in active_mtf_settlements:
                            active_mtf_settlements[sym] = set()
                        if settle_id:
                            active_mtf_settlements[sym].add(settle_id)

                        if sym not in mtf_positions:
                            mtf_positions[sym] = {"quantity": 0, "average_price": avg_p}
                        mtf_positions[sym]["quantity"] += int(q)

        demat_resp = f_demat.result()
        if demat_resp and isinstance(demat_resp.get("Success"), list):
            for d in demat_resp["Success"]:
                sym = str(d.get("stock_code") or "").strip().upper()
                q = int(float(parse_num(d.get("quantity") or 0)))
                avg_p = float(parse_num(d.get("average_price") or d.get("holding_cost") or 0))
                cmp_p = float(parse_num(d.get("current_market_price") or d.get("ltp") or 0))
                if cmp_p > 0:
                    ltp_map[sym] = cmp_p
                if q > 0:
                    demat_holdings[sym] = {"quantity": q, "average_price": avg_p}

        for f in f_trades:
            ex, res = f.result()
            if res and isinstance(res.get("Success"), list):
                for item in res["Success"]:
                    item["_exchange"] = ex
                    raw_trades.append(item)

    unique_codes = list({
        str(r.get("stock_code") or "").strip().upper() for r in raw_trades if r.get("stock_code")
    } | set(ltp_map.keys()))
    missing = [c for c in unique_codes if c and c not in COMPANY_NAMES_CACHE]
    if missing:
        with ThreadPoolExecutor(max_workers=6) as executor:
            executor.map(lambda c: resolve_single_stock_name(breeze, c), missing)

    all_clean_trades = []
    trades_by_stock = {}

    for idx, r in enumerate(raw_trades):
        sym = str(r.get("stock_code") or "").strip().upper()
        if not sym:
            continue
        if sym not in trades_by_stock:
            trades_by_stock[sym] = []
        
        q = float(parse_num(r.get("quantity") or 0))
        tot_amt = float(parse_num(r.get("average_cost") or 0))
        price = round(tot_amt / q, 2) if (q > 0 and tot_amt > 0) else float(parse_num(r.get("price") or 0))
        raw_ptype = str(r.get("product_type") or "").strip().upper()
        action = str(r.get("action") or "").upper()
        side = "SELL" if "SELL" in action or action == "S" else "BUY"
        dt = parse_date(r.get("trade_date") or r.get("order_date"))
        order_id = str(r.get("order_id") or "")
        order_seq = extract_order_seq(order_id)
        settle_code = str(r.get("settlement_code") or "").strip()

        trades_by_stock[sym].append({
            "originalIndex": idx,
            "stock": sym,
            "companyName": COMPANY_NAMES_CACHE.get(sym, sym),
            "date": dt,
            "type": side,
            "quantity": int(q),
            "price": price,
            "tradeAmount": tot_amt if tot_amt > 0 else round(q * price, 2),
            "product": raw_ptype,
            "order_id": order_id,
            "order_seq": order_seq,
            "settlement_code": settle_code
        })

    for sym, s_trades in trades_by_stock.items():
        open_settles = active_mtf_settlements.get(sym, set())

        daily_buys = {}
        daily_sells = {}
        for t in s_trades:
            d = t["date"]
            if t["type"] == "BUY":
                daily_buys[d] = daily_buys.get(d, 0) + t["quantity"]
            else:
                daily_sells[d] = daily_sells.get(d, 0) + t["quantity"]

        for t in s_trades:
            raw_ptype = t["product"]
            side = t["type"]
            settle_code = t["settlement_code"]
            d = t["date"]

            is_same_day_round_trip = (daily_buys.get(d, 0) > 0 and daily_sells.get(d, 0) > 0 and 
                                     daily_buys[d] == daily_sells[d])

            badge = "DELIVERY"
            if raw_ptype in ["MARGIN", "EASYMARGIN", "MTF"]:
                if is_same_day_round_trip:
                    badge = "INTRADAY"
                elif settle_code in open_settles:
                    badge = "MTF"
                else:
                    badge = "MTF_CONVERTED" if side == "BUY" else "MTF"

            all_clean_trades.append({
                **t,
                "badgeType": badge
            })

    all_clean_trades.sort(key=lambda x: x["date"], reverse=True)

    return {
        "trades": all_clean_trades,
        "demat_holdings": demat_holdings,
        "mtf_positions": mtf_positions,
        "company_names": COMPANY_NAMES_CACHE,
        "ltp_map": ltp_map
    }

# --- ROUTES ---

@delivery_bp.route("/delivery")
def view_delivery():
    return render_template_string(DELIVERY_PAGE_HTML, active_page="delivery")

@delivery_bp.route("/api/delivery_data")
def api_delivery_data():
    force = request.args.get("force") == "1"
    data = get_or_set_cache("demat_delivery_data", 8, fetch_delivery_data, force_refresh=force)
    return jsonify(data)