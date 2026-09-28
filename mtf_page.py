from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from flask import Blueprint, jsonify, render_template_string, request
from breeze_core import (
    COMPANY_NAMES_CACHE,
    FROM_DATE,
    LOGIN_URL,
    NAVBAR_HTML,
    extract_order_seq,
    get_breeze_client,
    get_or_set_cache,
    get_short_token,
    normalize_product_category,
    parse_date,
    resolve_single_stock_name,
    to_dec,
)

mtf_bp = Blueprint("mtf", __name__)

MTF_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MTF Audit</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; }
    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: #f8fafc; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; }
  </style>
</head>
<body class="bg-slate-100 text-slate-800 antialiased h-screen w-screen overflow-hidden flex flex-col">
  """ + NAVBAR_HTML + """
  <div class="h-9 bg-white border-b border-slate-200 px-4 flex items-center justify-between shrink-0 text-xs">
    <span class="text-slate-600 font-bold">EasyMargin Position Audit</span>
    <div class="flex items-center gap-2">
      <span class="text-slate-400 font-medium">Interest:</span>
      <select id="selectInterestRate" onchange="onRateChange()" class="bg-white border border-slate-300 rounded px-1.5 py-0.5 font-bold text-indigo-700">
        <option value="9.69" selected>9.69%</option>
        <option value="10.99">10.99%</option>
        <option value="17.99">17.99%</option>
        <option value="custom">Custom</option>
      </select>
      <input type="number" id="customInterestInput" step="0.1" value="9.69" oninput="onRateChange()" 
        class="hidden w-14 text-right border border-indigo-300 rounded px-1 py-0.5 font-bold text-indigo-800">
    </div>
  </div>

  <div class="flex-1 flex overflow-hidden">
    <aside class="w-72 bg-white border-r border-slate-200 flex flex-col h-full shrink-0">
      <div class="p-2.5 border-b border-slate-200 bg-slate-50">
        <input type="text" id="searchStock" oninput="renderStockList()" placeholder="Filter symbol or company..." 
          class="w-full bg-white border border-slate-300 rounded px-2.5 py-1 text-xs text-slate-800 focus:outline-none focus:border-indigo-500">
      </div>
      <div class="p-1.5 border-b border-slate-200">
        <button onclick="selectStock('ALL')" id="tab-ALL" class="stock-tab w-full text-left p-2 rounded flex items-center justify-between text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
          <span>All Scrips</span>
          <span id="badge-all-count" class="text-[10px] px-1.5 py-0.2 rounded bg-indigo-200 text-indigo-800 font-bold">0</span>
        </button>
      </div>
      <div id="stockListContainer" class="flex-1 overflow-y-auto p-1.5 space-y-1"></div>
    </aside>

    <main class="flex-1 flex flex-col h-full bg-slate-50 min-w-0 overflow-hidden">
      <div class="p-3 bg-white border-b border-slate-200 grid grid-cols-12 gap-2.5 shrink-0">
        <div class="col-span-5 bg-slate-50 border border-slate-200 rounded p-2.5">
          <div class="text-[10px] font-bold text-slate-400 uppercase mb-1.5">Capital & Debt</div>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="bg-white rounded p-1.5 border border-slate-200">
              <div class="text-[9px] uppercase text-slate-400">Total Purchase</div>
              <div class="text-xs font-bold text-slate-900 mt-0.5" id="kpiTradeValue">₹0.00</div>
              <div class="text-[9px] text-slate-400" id="kpiTotalQuantity">0 shares</div>
            </div>
            <div class="bg-blue-50/60 rounded p-1.5 border border-blue-100">
              <div class="text-[9px] uppercase text-blue-600">Margin Deployed</div>
              <div class="text-xs font-bold text-blue-800 mt-0.5" id="kpiMarginAmount">₹0.00</div>
              <div class="text-[9px] font-semibold text-blue-600" id="kpiMarginRatio">0.0%</div>
            </div>
            <div class="bg-indigo-50/60 rounded p-1.5 border border-indigo-100">
              <div class="text-[9px] uppercase text-indigo-600">MTF Debt</div>
              <div class="text-xs font-bold text-indigo-900 mt-0.5" id="kpiMtfPayable">₹0.00</div>
              <div class="text-[9px] font-semibold text-indigo-600" id="kpiFundedRatio">0.0%</div>
            </div>
            <div class="bg-white rounded p-1.5 border border-slate-200">
              <div class="text-[9px] uppercase text-slate-400">Market Value</div>
              <div class="text-xs font-bold text-slate-900 mt-0.5" id="kpiMarketValue">₹0.00</div>
              <div class="text-[10px] font-bold" id="kpiPnl">P&L: ₹0.00</div>
            </div>
          </div>
        </div>

        <div class="col-span-4 bg-slate-50 border border-slate-200 rounded p-2.5">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[10px] font-bold text-slate-400 uppercase">Realized</span>
            <span class="text-[10px] font-bold text-slate-500" id="kpiRealizedCount">0 lots</span>
          </div>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="bg-white rounded p-1.5 border border-slate-200">
              <div class="text-[9px] uppercase text-slate-400">Gross Gain</div>
              <div class="text-xs font-bold mt-0.5" id="kpiRealizedGross">₹0.00</div>
            </div>
            <div class="bg-rose-50/60 rounded p-1.5 border border-rose-100">
              <div class="text-[9px] uppercase text-rose-600">Interest</div>
              <div class="text-xs font-bold text-rose-700 mt-0.5" id="kpiRealizedInterest">₹0.00</div>
            </div>
            <div class="bg-amber-50/60 rounded p-1.5 border border-amber-100">
              <div class="text-[9px] uppercase text-amber-700">Brok + Taxes</div>
              <div class="text-xs font-bold text-amber-800 mt-0.5" id="kpiRealizedCharges">₹0.00</div>
            </div>
            <div class="bg-emerald-50 rounded p-1.5 border border-emerald-200">
              <div class="text-[9px] uppercase font-bold text-emerald-800">Net Realized</div>
              <div class="text-xs font-black mt-0.5" id="kpiRealizedNet">₹0.00</div>
              <div class="text-[9px] font-semibold text-emerald-700" id="kpiRealizedRoi">0.00%</div>
            </div>
          </div>
        </div>

        <div class="col-span-3 bg-slate-50 border border-slate-200 rounded p-2.5 flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-[10px] uppercase font-bold text-slate-400">Interest Summary</span>
              <span class="text-xs font-bold text-rose-700" id="kpiTotalInterestEver">₹0.00</span>
            </div>
            <div class="space-y-1 text-xs">
              <div class="flex justify-between items-center bg-white px-2 py-0.5 rounded border border-slate-200">
                <span class="text-slate-400 text-[10px]">Realized:</span>
                <span class="font-bold text-slate-800 text-[11px]" id="kpiInterestRealizedSub">₹0.00</span>
              </div>
              <div class="flex justify-between items-center bg-white px-2 py-0.5 rounded border border-slate-200">
                <span class="text-rose-600 text-[10px]">Accrued:</span>
                <span class="font-bold text-rose-700 text-[11px]" id="kpiInterestUnrealized">₹0.00</span>
              </div>
            </div>
          </div>
          <div class="bg-rose-100/50 rounded p-1 border border-rose-200 flex justify-between items-center text-xs">
            <span class="text-[9px] uppercase font-bold text-rose-800">Burn</span>
            <span class="text-xs font-bold text-rose-900" id="kpiDailyRate">₹0.00 / day</span>
          </div>
        </div>
      </div>

      <div class="px-4 py-2 bg-white border-b border-slate-200 flex items-center justify-between shrink-0">
        <div>
          <h2 class="text-xs font-bold text-slate-800 uppercase leading-tight" id="currentViewTitle">All Positions</h2>
          <div class="text-[10px] text-slate-400 font-medium truncate max-w-[280px]" id="currentViewSubtitle">All MTF Scrips</div>
        </div>
        <div class="flex gap-1.5 text-xs">
          <button onclick="switchView('ACTIVE_LOTS')" id="btnTabLots" class="px-2.5 py-0.5 font-semibold rounded bg-slate-900 text-white">
            Active Lots (<span id="tabCountLots">0</span>)
          </button>
          <button onclick="switchView('REALIZED_EXITS')" id="btnTabRealized" class="px-2.5 py-0.5 font-semibold rounded bg-slate-100 text-slate-600 hover:bg-slate-200">
            Realized FIFO (<span id="tabCountRealized">0</span>)
          </button>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto p-3 space-y-3">
        <div id="viewActiveLots" class="bg-white border border-slate-200 rounded shadow-xs overflow-hidden">
          <table class="w-full text-left border-collapse text-xs">
            <thead class="bg-slate-100 border-b border-slate-200 font-semibold text-slate-600">
              <tr>
                <th class="py-2 px-3 th-stock">Stock</th>
                <th class="py-2 px-3">Settlement</th>
                <th class="py-2 px-3">Expiry</th>
                <th class="py-2 px-3 text-right">Qty</th>
                <th class="py-2 px-3 text-right">Buy Price</th>
                <th class="py-2 px-3 text-right">Purchase Value</th>
                <th class="py-2 px-3 text-right text-blue-800 bg-blue-50/40 border-l border-blue-100">Margin</th>
                <th class="py-2 px-3 text-right font-bold text-indigo-900 bg-indigo-50/50">Debt</th>
                <th class="py-2 px-3 text-right">LTP</th>
                <th class="py-2 px-3 text-right">Market Value</th>
                <th class="py-2 px-3 text-right font-bold border-l border-slate-200">P&L</th>
              </tr>
            </thead>
            <tbody id="activeLotsTableBody" class="divide-y divide-slate-100 text-slate-700"></tbody>
          </table>
        </div>

        <div id="viewRealizedExits" class="hidden bg-white border border-slate-200 rounded shadow-xs overflow-hidden">
          <table class="w-full text-left border-collapse text-xs">
            <thead class="bg-slate-100 border-b border-slate-200 font-semibold text-slate-600">
              <tr>
                <th class="py-2 px-3 th-stock">Stock</th>
                <th class="py-2 px-3 text-right">Shares</th>
                <th class="py-2 px-3 text-right">Buy Price</th>
                <th class="py-2 px-3 text-right">Sell Price</th>
                <th class="py-2 px-3 text-center">Dates</th>
                <th class="py-2 px-3 text-center">Days</th>
                <th class="py-2 px-3 text-right text-slate-800">Gross Gain</th>
                <th class="py-2 px-3 text-right text-rose-700 bg-rose-50/40 font-bold">Interest</th>
                <th class="py-2 px-3 text-right text-amber-800">Charges</th>
                <th class="py-2 px-3 text-right font-bold text-emerald-700 bg-emerald-50/50">Net Profit</th>
              </tr>
            </thead>
            <tbody id="realizedTableBody" class="divide-y divide-slate-100 text-slate-700"></tbody>
          </table>
        </div>
      </div>
    </main>
  </div>

  <script>
    let POSITIONS = {};
    let RAW_TRADES = [];
    let SUMMARY = {};
    let COMPANY_NAMES = {};
    const TODAY_STR = new Date().toISOString().slice(0, 10);
    let currentFilter = 'ALL';
    let currentView = 'ACTIVE_LOTS';
    let interestRateAnnual = 9.69;
    let isPolling = false;

    function getSortedTrades(trades) {
      return [...trades].sort((a, b) => {
        const dateA = new Date(a.date).getTime();
        const dateB = new Date(b.date).getTime();
        if (dateA !== dateB) return dateA - dateB;

        const seqA = a.order_seq !== undefined ? a.order_seq : -1;
        const seqB = b.order_seq !== undefined ? b.order_seq : -1;
        if (seqA !== -1 && seqB !== -1 && seqA !== seqB) return seqA - seqB;
        if (a.raw_index !== undefined && b.raw_index !== undefined && a.raw_index !== b.raw_index) {
          return b.raw_index - a.raw_index;
        }
        if (a.type !== b.type) return a.type === 'BUY' ? -1 : 1;
        return 0;
      });
    }

    async function loadData(force = false) {
      if (isPolling) return;
      isPolling = true;
      try {
        const url = force ? '/api/mtf?force=1' : '/api/mtf';
        const res = await fetch(url);
        const payload = await res.json();
        if (evaluateSessionError(payload)) return;

        const d = payload.data || {};
        POSITIONS = d.positions || {};
        RAW_TRADES = d.trades || [];
        SUMMARY = d.summary || {};
        COMPANY_NAMES = d.company_names || {};
        renderAll();

        const syncEl = document.getElementById('syncStatusLabel');
        if (syncEl) syncEl.innerText = new Date().toLocaleTimeString();
      } catch (e) {
        console.error("Fetch failed:", e);
      } finally {
        isPolling = false;
      }
    }

    function refreshData(force = true) {
      loadData(force);
    }

    function onRateChange() {
      const sel = document.getElementById('selectInterestRate').value;
      const inp = document.getElementById('customInterestInput');
      if (sel === 'custom') {
        inp.classList.remove('hidden');
        interestRateAnnual = parseFloat(inp.value) || 9.69;
      } else {
        inp.classList.add('hidden');
        interestRateAnnual = parseFloat(sel);
      }
      renderAll();
    }

    function switchView(view) {
      currentView = view;
      const btnLots = document.getElementById('btnTabLots');
      const btnRealized = document.getElementById('btnTabRealized');
      const viewLots = document.getElementById('viewActiveLots');
      const viewRealized = document.getElementById('viewRealizedExits');
      if (view === 'ACTIVE_LOTS') {
        btnLots.className = 'px-2.5 py-0.5 font-semibold rounded bg-slate-900 text-white';
        btnRealized.className = 'px-2.5 py-0.5 font-semibold rounded bg-slate-100 text-slate-600 hover:bg-slate-200';
        viewLots.classList.remove('hidden');
        viewRealized.classList.add('hidden');
      } else {
        btnRealized.className = 'px-2.5 py-0.5 font-semibold rounded bg-slate-900 text-white';
        btnLots.className = 'px-2.5 py-0.5 font-semibold rounded bg-slate-100 text-slate-600 hover:bg-slate-200';
        viewRealized.classList.remove('hidden');
        viewLots.classList.add('hidden');
      }
    }

    function selectStock(sym) {
      currentFilter = sym;
      document.querySelectorAll('.stock-tab').forEach(el => {
        el.classList.remove('bg-indigo-50', 'text-indigo-700', 'border-indigo-200');
        el.classList.add('text-slate-600', 'border-transparent');
      });
      const activeBtn = document.getElementById('tab-' + sym);
      if (activeBtn) {
        activeBtn.classList.add('bg-indigo-50', 'text-indigo-700', 'border-indigo-200');
        activeBtn.classList.remove('border-transparent');
      }
      renderAll();
    }

    function renderStockList() {
      const q = (document.getElementById('searchStock').value || '').toUpperCase().trim();
      const container = document.getElementById('stockListContainer');
      const stocks = Object.keys(POSITIONS).sort();
      document.getElementById('badge-all-count').innerText = stocks.length;
      container.innerHTML = stocks
        .filter(s => {
          const compName = (POSITIONS[s]?.company_name || COMPANY_NAMES[s] || '').toUpperCase();
          return s.includes(q) || compName.includes(q);
        })
        .map(sym => {
          const item = POSITIONS[sym];
          const isSelected = currentFilter === sym;
          const isSettled = item.total_quantity === 0;
          const compName = item.company_name || COMPANY_NAMES[sym] || sym;
          return `
            <button onclick="selectStock('${sym}')" id="tab-${sym}" 
              class="stock-tab w-full text-left p-2 rounded border flex items-center justify-between text-xs ${
                isSelected ? 'bg-indigo-50 text-indigo-700 border-indigo-200 font-semibold' : 'border-transparent text-slate-700 hover:bg-slate-50'
              }">
              <div class="min-w-0 pr-2">
                <div class="font-bold text-slate-900 flex items-center gap-1">
                  <span>${sym}</span>
                  ${isSettled ? '<span class="text-[9px] px-1 rounded bg-slate-100 text-slate-400 border border-slate-200">0</span>' : ''}
                </div>
                <div class="text-[10px] text-slate-400 truncate">${compName}</div>
                <div class="text-[10px] ${isSettled ? 'text-slate-400' : 'text-slate-600'}">Qty: ${item.total_quantity.toLocaleString()}</div>
              </div>
              <div class="text-right font-bold text-indigo-700 shrink-0">
                ${isSettled ? 'Settled' : '₹' + item.total_mtf_payable.toLocaleString('en-IN', {maximumFractionDigits: 0})}
              </div>
            </button>
          `;
        }).join('');
    }

    function computeRealizedTrades() {
      const mtfOnlyTrades = RAW_TRADES.filter(t => t.product === 'MTF');
      const sorted = getSortedTrades(mtfOnlyTrades);
      const openLots = {};
      const closed = [];
      for (const t of sorted) {
        const sym = t.stock;
        if (!openLots[sym]) openLots[sym] = [];
        if (t.type === 'BUY') {
          openLots[sym].push({
            date: t.date,
            qty: t.quantity,
            rem: t.quantity,
            price: t.price,
            brok: t.brokerage,
            taxes: t.taxes,
            companyName: t.companyName || COMPANY_NAMES[sym] || sym
          });
        } else {
          let sellQty = t.quantity;
          for (let i = 0; i < openLots[sym].length && sellQty > 0; i++) {
            const lot = openLots[sym][i];
            const take = Math.min(lot.rem, sellQty);
            if (take > 0) {
              lot.rem -= take;
              sellQty -= take;
              const buyVal = take * lot.price;
              const sellVal = take * t.price;
              const grossGain = sellVal - buyVal;
              const days = Math.max(1, Math.round((new Date(t.date) - new Date(lot.date)) / (1000 * 3600 * 24)));
              const marginRatio = (POSITIONS[sym]?.margin_pct || 25) / 100.0;
              const debtAmount = buyVal * (1.0 - marginRatio);
              const interest = (debtAmount * (interestRateAnnual / 100.0) * days) / 365.0;
              const actualCharges = (lot.brok + lot.taxes) * (take / lot.qty) + (t.brokerage + t.taxes) * (take / t.quantity);
              const netProfit = grossGain - interest - actualCharges;
              closed.push({
                stock: sym,
                companyName: lot.companyName,
                shares: take,
                buyPrice: lot.price,
                sellPrice: t.price,
                buyDate: lot.date,
                sellDate: t.date,
                days: days,
                buyVal: buyVal,
                grossGain: grossGain,
                interest: interest,
                charges: actualCharges,
                netProfit: netProfit
              });
            }
          }
          openLots[sym] = openLots[sym].filter(l => l.rem > 0);
        }
      }
      return closed;
    }

    function computeUnrealizedInterest(targetStock) {
      const mtfOnlyTrades = RAW_TRADES.filter(t => t.product === 'MTF');
      const sorted = getSortedTrades(mtfOnlyTrades);
      const openLots = {};
      for (const t of sorted) {
        const sym = t.stock;
        if (!openLots[sym]) openLots[sym] = [];
        if (t.type === 'BUY') {
          openLots[sym].push({
            date: t.date,
            qty: t.quantity,
            rem: t.quantity,
            price: t.price
          });
        } else {
          let sellQty = t.quantity;
          for (let i = 0; i < openLots[sym].length && sellQty > 0; i++) {
            const lot = openLots[sym][i];
            const take = Math.min(lot.rem, sellQty);
            if (take > 0) {
              lot.rem -= take;
              sellQty -= take;
            }
          }
          openLots[sym] = openLots[sym].filter(l => l.rem > 0);
        }
      }

      let totalAccrued = 0;
      const todayDate = new Date(TODAY_STR);
      for (const sym in openLots) {
        if (targetStock !== 'ALL' && sym !== targetStock) continue;
        const marginRatio = (POSITIONS[sym]?.margin_pct || 25) / 100.0;
        const fundedRatio = 1.0 - marginRatio;
        for (const lot of openLots[sym]) {
          if (lot.rem > 0) {
            const buyDate = new Date(lot.date);
            const daysActive = Math.max(1, Math.round((todayDate - buyDate) / (1000 * 3600 * 24)));
            const lotDebt = (lot.rem * lot.price) * fundedRatio;
            const interest = (lotDebt * (interestRateAnnual / 100.0) * daysActive) / 365.0;
            totalAccrued += interest;
          }
        }
      }
      return totalAccrued;
    }

    function renderAll() {
      renderStockList();
      const isAll = currentFilter === 'ALL';
      document.querySelectorAll('.th-stock').forEach(el => {
        if (isAll) el.classList.remove('hidden');
        else el.classList.add('hidden');
      });

      let activeQty = 0, activeCost = 0, activeMargin = 0, activeDebt = 0, activeMktVal = 0, activePnl = 0;
      let displayLots = [];

      if (currentFilter === 'ALL') {
        activeQty = SUMMARY.active_qty || 0;
        activeCost = SUMMARY.active_cost || 0;
        activeMargin = SUMMARY.active_margin || 0;
        activeDebt = SUMMARY.active_debt || 0;
        activeMktVal = SUMMARY.active_mkt_val || 0;
        activePnl = SUMMARY.active_pnl || 0;
        Object.values(POSITIONS).forEach(item => {
          item.lots.forEach(l => {
            displayLots.push({ ...l, stock: item.stock, companyName: item.company_name });
          });
        });
      } else if (POSITIONS[currentFilter]) {
        const item = POSITIONS[currentFilter];
        activeQty = item.total_quantity;
        activeCost = item.total_trade_value;
        activeMargin = item.total_margin;
        activeDebt = item.total_mtf_payable;
        activeMktVal = item.total_market_value;
        activePnl = item.total_pnl;
        displayLots = item.lots.map(l => ({ ...l, stock: item.stock, companyName: item.company_name }));
      }

      const marginRatio = activeCost > 0 ? (activeMargin / activeCost * 100).toFixed(1) : '0.0';
      const fundedRatio = activeCost > 0 ? (activeDebt / activeCost * 100).toFixed(1) : '0.0';
      const dailyInterest = (activeDebt * (interestRateAnnual / 100.0)) / 365.0;

      const realizedAll = computeRealizedTrades();
      const filteredRealized = currentFilter === 'ALL' ? realizedAll : realizedAll.filter(t => t.stock === currentFilter);
      
      const totalRealizedGross = filteredRealized.reduce((sum, t) => sum + t.grossGain, 0);
      const totalInterestRealized = filteredRealized.reduce((sum, t) => sum + t.interest, 0);
      const totalRealizedCharges = filteredRealized.reduce((sum, t) => sum + t.charges, 0);
      const totalRealizedNet = filteredRealized.reduce((sum, t) => sum + t.netProfit, 0);
      const totalRealizedOutlay = filteredRealized.reduce((sum, t) => sum + t.buyVal, 0);
      const realizedRoi = totalRealizedOutlay > 0 ? (totalRealizedNet / totalRealizedOutlay * 100).toFixed(2) : '0.00';

      const totalInterestUnrealized = computeUnrealizedInterest(currentFilter);
      const totalInterestEver = totalInterestRealized + totalInterestUnrealized;

      document.getElementById('kpiTradeValue').innerText = '₹' + activeCost.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('kpiTotalQuantity').innerText = activeQty.toLocaleString() + ' shares';
      document.getElementById('kpiMarginAmount').innerText = '₹' + activeMargin.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('kpiMarginRatio').innerText = marginRatio + '%';
      document.getElementById('kpiMtfPayable').innerText = '₹' + activeDebt.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('kpiFundedRatio').innerText = fundedRatio + '%';
      document.getElementById('kpiMarketValue').innerText = '₹' + activeMktVal.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      
      const pnlEl = document.getElementById('kpiPnl');
      pnlEl.innerText = 'P&L: ' + (activePnl >= 0 ? '+₹' : '-₹') + Math.abs(activePnl).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      pnlEl.className = 'text-[10px] font-bold ' + (activePnl >= 0 ? 'text-emerald-700' : 'text-rose-700');

      document.getElementById('kpiRealizedCount').innerText = filteredRealized.length + ' lots';
      const grossEl = document.getElementById('kpiRealizedGross');
      grossEl.innerText = (totalRealizedGross >= 0 ? '+₹' : '-₹') + Math.abs(totalRealizedGross).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      grossEl.className = 'text-xs font-bold mt-0.5 ' + (totalRealizedGross >= 0 ? 'text-emerald-700' : 'text-rose-700');
      document.getElementById('kpiRealizedInterest').innerText = '-₹' + totalInterestRealized.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('kpiRealizedCharges').innerText = '-₹' + totalRealizedCharges.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      
      const netEl = document.getElementById('kpiRealizedNet');
      netEl.innerText = (totalRealizedNet >= 0 ? '+₹' : '-₹') + Math.abs(totalRealizedNet).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      netEl.className = 'text-xs font-black mt-0.5 ' + (totalRealizedNet >= 0 ? 'text-emerald-800' : 'text-rose-800');
      document.getElementById('kpiRealizedRoi').innerText = (totalRealizedNet >= 0 ? '+' : '') + realizedRoi + '% ROI';
      document.getElementById('kpiRealizedRoi').className = 'text-[9px] font-semibold ' + (totalRealizedNet >= 0 ? 'text-emerald-700' : 'text-rose-700');

      document.getElementById('kpiTotalInterestEver').innerText = '₹' + totalInterestEver.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('kpiInterestRealizedSub').innerText = '₹' + totalInterestRealized.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('kpiInterestUnrealized').innerText = '₹' + totalInterestUnrealized.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('kpiDailyRate').innerText = '₹' + dailyInterest.toFixed(2) + ' / day';

      document.getElementById('currentViewTitle').innerText = currentFilter === 'ALL' ? 'All Positions' : currentFilter;
      document.getElementById('currentViewSubtitle').innerText = currentFilter === 'ALL' ? 'All MTF Scrips' : (COMPANY_NAMES[currentFilter] || currentFilter);
      document.getElementById('tabCountLots').innerText = displayLots.length;
      document.getElementById('tabCountRealized').innerText = filteredRealized.length;

      const tbodyLots = document.getElementById('activeLotsTableBody');
      const showStock = currentFilter === 'ALL';

      if (displayLots.length === 0) {
        tbodyLots.innerHTML = `<tr><td colspan="${showStock ? 11 : 10}" class="text-center py-6 text-slate-400">No active lots</td></tr>`;
      } else {
        tbodyLots.innerHTML = displayLots.map(l => {
          const isPos = l.pnl >= 0;
          return `
            <tr class="hover:bg-slate-50 border-b border-slate-100">
              ${showStock ? `
                <td class="py-2 px-3">
                  <div class="font-bold text-slate-900">${l.stock}</div>
                  <div class="text-[10px] text-slate-400 truncate max-w-[140px]">${l.companyName || ''}</div>
                </td>
              ` : ''}
              <td class="py-2 px-3 font-mono text-[11px] text-slate-500">${l.settlement_id}</td>
              <td class="py-2 px-3 text-slate-600 font-medium">${l.mtf_expiry_date}</td>
              <td class="py-2 px-3 text-right font-bold text-slate-800">${l.quantity.toLocaleString()}</td>
              <td class="py-2 px-3 text-right font-medium text-slate-700">₹${l.average_price.toFixed(2)}</td>
              <td class="py-2 px-3 text-right font-medium text-slate-900">₹${l.trade_value.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
              <td class="py-2 px-3 text-right font-bold text-blue-700 bg-blue-50/40 border-l border-blue-100">
                ₹${l.margin_amount.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
              </td>
              <td class="py-2 px-3 text-right font-bold text-indigo-900 bg-indigo-50/50">
                ₹${l.mtf_payable.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
              </td>
              <td class="py-2 px-3 text-right font-semibold text-slate-800">₹${l.ltp.toFixed(2)}</td>
              <td class="py-2 px-3 text-right font-medium text-slate-800">₹${l.market_value.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
              <td class="py-2 px-3 text-right font-bold border-l border-slate-200 ${isPos ? 'text-emerald-700' : 'text-rose-700'}">
                ${isPos ? '+' : ''}₹${l.pnl.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
              </td>
            </tr>
          `;
        }).join('');
      }

      const tbodyRealized = document.getElementById('realizedTableBody');
      if (filteredRealized.length === 0) {
        tbodyRealized.innerHTML = `<tr><td colspan="${showStock ? 10 : 9}" class="text-center py-6 text-slate-400">No realized records</td></tr>`;
      } else {
        tbodyRealized.innerHTML = filteredRealized.map(t => {
          const isNetPos = t.netProfit >= 0;
          return `
            <tr class="hover:bg-slate-50 border-b border-slate-100">
              ${showStock ? `
                <td class="py-2 px-3">
                  <div class="font-bold text-slate-800">${t.stock}</div>
                  <div class="text-[10px] text-slate-400 truncate max-w-[140px]">${t.companyName || ''}</div>
                </td>
              ` : ''}
              <td class="py-2 px-3 text-right font-semibold">${t.shares.toLocaleString()}</td>
              <td class="py-2 px-3 text-right text-slate-600">₹${t.buyPrice.toFixed(2)}</td>
              <td class="py-2 px-3 text-right text-slate-800 font-medium">₹${t.sellPrice.toFixed(2)}</td>
              <td class="py-2 px-3 text-center text-slate-500 whitespace-nowrap font-mono text-[11px]">${t.buyDate} → ${t.sellDate}</td>
              <td class="py-2 px-3 text-center font-medium text-indigo-700">${t.days}d</td>
              <td class="py-2 px-3 text-right font-medium ${t.grossGain >= 0 ? 'text-emerald-700' : 'text-rose-700'}">
                ${t.grossGain >= 0 ? '+' : ''}₹${t.grossGain.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
              </td>
              <td class="py-2 px-3 text-right font-bold text-rose-600 bg-rose-50/30">
                -₹${t.interest.toFixed(2)}
              </td>
              <td class="py-2 px-3 text-right text-amber-700">
                -₹${t.charges.toFixed(2)}
              </td>
              <td class="py-2 px-3 text-right font-bold bg-emerald-50/40 border-l border-emerald-100 ${isNetPos ? 'text-emerald-700' : 'text-rose-700'}">
                ${isNetPos ? '+' : ''}₹${t.netProfit.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
              </td>
            </tr>
          `;
        }).join('');
      }
    }

    window.addEventListener('DOMContentLoaded', () => {
      loadData(false);
      // Auto-poll every 10 seconds in the background
      setInterval(() => loadData(false), 10000);
    });
  </script>
</body>
</html>
"""

def fetch_mtf_data():
    breeze, is_auth = get_breeze_client()
    if not is_auth or not breeze:
        return {"error": "SESSION_EXPIRED", "login_url": LOGIN_URL}

    positions_raw = []
    try:
        pos_resp = breeze.get_portfolio_positions()
        if pos_resp and pos_resp.get("Status") in [401, 500]:
            return {"error": "SESSION_EXPIRED", "login_url": LOGIN_URL}
        if pos_resp and pos_resp.get("Status") == 200 and isinstance(pos_resp.get("Success"), list):
            positions_raw = pos_resp.get("Success", [])
    except Exception as e:
        print(f"[-] Positions error: {e}")
        return {"error": "SESSION_EXPIRED", "login_url": LOGIN_URL}

    stock_positions = {}
    total_active_qty = Decimal("0")
    total_active_cost = Decimal("0")
    total_active_margin = Decimal("0")
    total_active_debt = Decimal("0")
    total_active_mkt_val = Decimal("0")
    total_active_pnl = Decimal("0")

    all_mtf_codes = set()

    for p in positions_raw:
        p_type = str(p.get("product_type") or "").strip().upper()
        if p_type not in ["EASYMARGIN", "MARGIN", "MTF"]:
            continue
        sym = str(p.get("stock_code") or "UNKNOWN").strip().upper()
        qty = to_dec(p.get("quantity"))
        avg_price = to_dec(p.get("average_price"))
        margin_amount = to_dec(p.get("margin_amount"))
        mtf_payable = to_dec(p.get("mtf_net_amount_payable"))
        ltp = to_dec(p.get("ltp"))
        pnl = to_dec(p.get("pnl"))
        trade_val = qty * avg_price
        mkt_val = qty * ltp

        if qty <= Decimal("0"):
            continue

        all_mtf_codes.add(sym)

        lot = {
            "settlement_id": str(p.get("settlement_id") or "-"),
            "mtf_expiry_date": str(p.get("mtf_expiry_date") or "-"),
            "quantity": float(qty),
            "average_price": float(avg_price),
            "trade_value": float(trade_val),
            "margin_amount": float(margin_amount),
            "mtf_payable": float(mtf_payable),
            "ltp": float(ltp),
            "market_value": float(mkt_val),
            "pnl": float(pnl),
            "funded_pct": float((mtf_payable / trade_val * Decimal("100")).quantize(Decimal("0.1"))) if trade_val > 0 else 0.0,
            "margin_pct": float((margin_amount / trade_val * Decimal("100")).quantize(Decimal("0.1"))) if trade_val > 0 else 0.0
        }

        if sym not in stock_positions:
            stock_positions[sym] = {
                "stock": sym,
                "lots": [],
                "total_quantity": Decimal("0"),
                "total_trade_value": Decimal("0"),
                "total_margin": Decimal("0"),
                "total_mtf_payable": Decimal("0"),
                "total_market_value": Decimal("0"),
                "total_pnl": Decimal("0"),
                "ltp": float(ltp)
            }
        stock_positions[sym]["lots"].append(lot)
        stock_positions[sym]["total_quantity"] += qty
        stock_positions[sym]["total_trade_value"] += trade_val
        stock_positions[sym]["total_margin"] += margin_amount
        stock_positions[sym]["total_mtf_payable"] += mtf_payable
        stock_positions[sym]["total_market_value"] += mkt_val
        stock_positions[sym]["total_pnl"] += pnl

        total_active_qty += qty
        total_active_cost += trade_val
        total_active_margin += margin_amount
        total_active_debt += mtf_payable
        total_active_mkt_val += mkt_val
        total_active_pnl += pnl

    trades_raw = []
    to_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def fetch_exchange_trades(ex):
        try:
            return breeze.get_trade_list(
                from_date=FROM_DATE,
                to_date=to_date,
                exchange_code=ex,
                product_type=""
            ), ex
        except Exception as e:
            print(f"[-] MTF Trade book error ({ex}): {e}")
            return None, ex

    with ThreadPoolExecutor(max_workers=2) as executor:
        for res, ex in executor.map(fetch_exchange_trades, ["NSE", "BSE"]):
            if res and res.get("Success") and isinstance(res.get("Success"), list):
                for idx, r in enumerate(res.get("Success")):
                    raw_prod = str(r.get("product_type") or "").strip()
                    p_cat = normalize_product_category(raw_prod)
                    code = str(r.get("stock_code") or "UNKNOWN").strip().upper()
                    action = str(r.get("action") or "").strip().upper()
                    side = "SELL" if "SELL" in action or action == "S" else "BUY"
                    qty = to_dec(r.get("quantity"))
                    tot_amt = to_dec(r.get("average_cost"))
                    if qty > Decimal("0") and tot_amt > Decimal("0"):
                        price = (tot_amt / qty).quantize(Decimal("0.01"))
                    else:
                        price = to_dec(r.get("execution_price") or r.get("price") or r.get("ltp"))
                        tot_amt = qty * price
                    brokerage = to_dec(r.get("brokerage_amount"))
                    taxes = to_dec(r.get("total_taxes"))
                    dt = parse_date(r.get("trade_date") or r.get("order_date"))
                    order_id = str(r.get("order_id") or "")
                    order_seq = extract_order_seq(order_id)

                    if qty > Decimal("0") and price > Decimal("0"):
                        all_mtf_codes.add(code)
                        trades_raw.append({
                            "raw_index": idx,
                            "date": dt,
                            "stock": code,
                            "type": side,
                            "quantity": float(qty),
                            "price": float(price),
                            "tradeAmount": float(tot_amt),
                            "brokerage": float(brokerage),
                            "taxes": float(taxes),
                            "product": p_cat,
                            "order_id": order_id,
                            "order_seq": order_seq,
                            "exchange_code": ex
                        })

                        if p_cat == "MTF" and code not in stock_positions:
                            stock_positions[code] = {
                                "stock": code,
                                "lots": [],
                                "total_quantity": Decimal("0"),
                                "total_trade_value": Decimal("0"),
                                "total_margin": Decimal("0"),
                                "total_mtf_payable": Decimal("0"),
                                "total_market_value": Decimal("0"),
                                "total_pnl": Decimal("0"),
                                "ltp": float(price)
                            }

    missing_names = [c for c in all_mtf_codes if c and c not in COMPANY_NAMES_CACHE]
    if missing_names:
        with ThreadPoolExecutor(max_workers=6) as executor:
            executor.map(lambda c: resolve_single_stock_name(breeze, c), missing_names)

    for t in trades_raw:
        t["companyName"] = COMPANY_NAMES_CACHE.get(t["stock"], t["stock"])

    serialized_positions = {}
    for sym, d in stock_positions.items():
        avg_cost = (d["total_trade_value"] / d["total_quantity"]).quantize(Decimal("0.01")) if d["total_quantity"] > 0 else Decimal("0")
        margin_pct = (d["total_margin"] / d["total_trade_value"] * Decimal("100")).quantize(Decimal("0.1")) if d["total_trade_value"] > 0 else Decimal("0")
        funded_pct = (d["total_mtf_payable"] / d["total_trade_value"] * Decimal("100")).quantize(Decimal("0.1")) if d["total_trade_value"] > 0 else Decimal("0")
        serialized_positions[sym] = {
            "stock": sym,
            "company_name": COMPANY_NAMES_CACHE.get(sym, sym),
            "lots": d["lots"],
            "total_quantity": float(d["total_quantity"]),
            "total_trade_value": float(d["total_trade_value"]),
            "total_margin": float(d["total_margin"]),
            "total_mtf_payable": float(d["total_mtf_payable"]),
            "total_market_value": float(d["total_market_value"]),
            "total_pnl": float(d["total_pnl"]),
            "avg_cost": float(avg_cost),
            "margin_pct": float(margin_pct),
            "funded_pct": float(funded_pct),
            "ltp": d["ltp"]
        }

    summary_totals = {
        "active_qty": float(total_active_qty),
        "active_cost": float(total_active_cost),
        "active_margin": float(total_active_margin),
        "active_debt": float(total_active_debt),
        "active_mkt_val": float(total_active_mkt_val),
        "active_pnl": float(total_active_pnl),
        "effective_margin_pct": float((total_active_margin / total_active_cost * Decimal("100")).quantize(Decimal("0.1"))) if total_active_cost > 0 else 0.0,
        "effective_funded_pct": float((total_active_debt / total_active_cost * Decimal("100")).quantize(Decimal("0.1"))) if total_active_cost > 0 else 0.0
    }

    return {
        "data": {
            "positions": serialized_positions,
            "trades": trades_raw,
            "summary": summary_totals,
            "company_names": COMPANY_NAMES_CACHE
        }
    }

@mtf_bp.route("/mtf")
def view_mtf():
    return render_template_string(MTF_PAGE_HTML, active_page="mtf")

@mtf_bp.route("/api/mtf")
def api_mtf():
    force = request.args.get("force") == "1"
    data = get_or_set_cache("mtf_audit_data", 8, fetch_mtf_data, force_refresh=force)
    return jsonify(data)