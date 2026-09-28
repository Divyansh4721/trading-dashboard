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
    get_short_token,
    normalize_product_category,
    parse_date,
    parse_num,
    resolve_single_stock_name,
)

holdings_bp = Blueprint("holdings", __name__)

HOLDINGS_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Holdings & Inventory</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; }
    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: #f8fafc; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; }
  </style>
</head>
<body class="bg-slate-100 text-slate-800 antialiased h-screen w-screen overflow-hidden flex flex-col">
  """ + NAVBAR_HTML + """
  <div class="flex-1 flex overflow-hidden relative">
    <aside class="w-72 bg-white border-r border-slate-200 flex flex-col h-full shrink-0">
      <div class="p-2.5 border-b border-slate-200 bg-slate-50">
        <input type="text" id="searchStock" oninput="renderStockList()" placeholder="Filter symbol or company..." 
          class="w-full bg-white border border-slate-300 rounded px-2.5 py-1 text-xs text-slate-800 focus:outline-none focus:border-blue-500">
      </div>
      
      <div class="p-1.5 border-b border-slate-200">
        <button onclick="selectStock('ALL')" id="tab-ALL" class="stock-tab w-full text-left p-2 rounded flex items-center justify-between text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
          <span>All Stocks</span>
          <span id="badge-all-count" class="text-[10px] px-1.5 py-0.2 rounded bg-blue-200 text-blue-800 font-bold">0</span>
        </button>
      </div>
      <div id="stockListContainer" class="flex-1 overflow-y-auto p-1.5 space-y-1"></div>
    </aside>

    <main class="flex-1 flex flex-col h-full bg-slate-50 min-w-0 relative">
      <div class="p-3 bg-white border-b border-slate-200 flex items-center justify-between shrink-0 shadow-xs">
        <div class="flex items-center gap-4">
          <div>
            <h2 class="text-base font-bold text-slate-900 leading-tight" id="selectedStockTitle">All Stocks</h2>
            <div class="text-[11px] text-slate-400 font-medium truncate max-w-[260px]" id="selectedStockSubtitle">All Portfolio Positions</div>
          </div>
          <div class="flex gap-1.5">
            <button onclick="switchView('LEDGER')" id="btnViewLedger" class="px-2.5 py-1 text-xs font-semibold rounded bg-slate-900 text-white">
              History
            </button>
            <button onclick="switchView('OPEN_LOTS')" id="btnViewOpenLots" class="px-2.5 py-1 text-xs font-semibold rounded bg-slate-100 text-slate-600 hover:bg-slate-200">
              Open Lots (<span id="openLotsCount">0</span>)
            </button>
          </div>
        </div>
        <div class="flex gap-3">
          <div class="bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-right">
            <div class="text-[9px] uppercase font-bold text-slate-400">Qty</div>
            <div class="text-xs font-bold text-slate-800" id="summaryOpenQty">0</div>
          </div>
          <div class="bg-blue-50 border border-blue-200 px-2.5 py-1 rounded text-right">
            <div class="text-[9px] uppercase font-bold text-blue-500">Avg</div>
            <div class="text-xs font-bold text-blue-700" id="summaryAvgPrice">₹0.00</div>
          </div>
          <div class="bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded text-right">
            <div class="text-[9px] uppercase font-bold text-emerald-600" id="summaryTargetLabel">Target (+2.5%)</div>
            <div class="text-xs font-bold text-emerald-700" id="summaryTargetSellPrice">₹0.00</div>
          </div>
          <div class="bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-right">
            <div class="text-[9px] uppercase font-bold text-slate-400">Deployed</div>
            <div class="text-xs font-bold text-slate-800" id="summaryTotalInvested">₹0.00</div>
          </div>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto p-3 pb-24 space-y-4">
        <div id="viewLedgerTable" class="bg-white border border-slate-200 rounded shadow-xs overflow-hidden">
          <table class="w-full text-left border-collapse text-xs">
            <thead class="sticky top-0 bg-slate-100 border-b border-slate-200 z-10 font-semibold text-slate-600">
              <tr>
                <th class="py-2 px-3 w-8 text-center">
                  <input type="checkbox" id="selectAllLedger" onchange="toggleSelectAllLedger(this.checked)"
                    class="rounded border-slate-300 text-blue-600">
                </th>
                <th class="py-2 px-3">Date</th>
                <th class="py-2 px-3">Product</th>
                <th class="py-2 px-3 th-stock">Stock</th>
                <th class="py-2 px-3 text-center">Side</th>
                <th class="py-2 px-3 text-right">Qty</th>
                <th class="py-2 px-3 text-right">Price</th>
                <th class="py-2 px-3 text-right">Amount</th>
                <th class="py-2 px-3 text-right bg-blue-50/50 text-blue-900 font-bold">Running Avg</th>
              </tr>
            </thead>
            <tbody id="transactionsBody" class="divide-y divide-slate-100 text-slate-700"></tbody>
          </table>
        </div>

        <div id="viewOpenLotsContainer" class="hidden space-y-4">
          <div class="bg-white border border-slate-200 rounded shadow-xs overflow-hidden">
            <div class="px-3 py-1.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
              <span class="text-xs font-bold text-slate-700">Open Lots</span>
            </div>
            <table class="w-full text-left border-collapse text-xs">
              <thead class="bg-slate-100 border-b border-slate-200 font-semibold text-slate-600">
                <tr>
                  <th class="py-2 px-3 w-8 text-center">
                    <input type="checkbox" id="selectAllOpenLots" onchange="toggleSelectAllOpenLots(this.checked)"
                      class="rounded border-slate-300 text-blue-600">
                  </th>
                  <th class="py-2 px-3">Product</th>
                  <th class="py-2 px-3 text-indigo-900 bg-indigo-50/50">Buy Price</th>
                  <th class="py-2 px-3 th-stock">Stock</th>
                  <th class="py-2 px-3 text-right font-bold text-indigo-700">Remaining Qty</th>
                  <th class="py-2 px-3 text-right text-slate-400">Original Qty</th>
                  <th class="py-2 px-3 text-right">Value</th>
                  <th class="py-2 px-3 text-right bg-emerald-50/70 border-l border-emerald-100">
                    <div class="flex items-center justify-end gap-1">
                      <span>Target Price (+</span>
                      <input type="number" id="targetMarginInput" step="0.05" min="0" value="2.5" oninput="onTargetMarginChange()"
                        class="w-12 text-right bg-white border border-emerald-300 rounded px-1 text-xs font-bold text-emerald-900">
                      <span>%)</span>
                    </div>
                  </th>
                  <th class="py-2 px-3">Date</th>
                  <th class="py-2 px-3 text-right">Share</th>
                </tr>
              </thead>
              <tbody id="openLotsBody" class="divide-y divide-slate-100 text-slate-700"></tbody>
            </table>
          </div>

          <div class="bg-white border border-slate-200 rounded shadow-xs overflow-hidden">
            <div class="px-3 py-1.5 bg-slate-100 border-b border-slate-200 flex items-center justify-between">
              <span class="text-xs font-bold text-slate-700">Exhausted Lots</span>
              <span id="exhaustedLotsBadge" class="text-[10px] px-1.5 py-0.2 rounded bg-slate-200 text-slate-700 font-bold">0</span>
            </div>
            <table class="w-full text-left border-collapse text-xs">
              <thead class="bg-slate-50 border-b border-slate-200 font-semibold text-slate-600">
                <tr>
                  <th class="py-2 px-3 w-8 text-center">
                    <input type="checkbox" id="selectAllExhausted" onchange="toggleSelectAllExhausted(this.checked)"
                      class="rounded border-slate-300 text-blue-600">
                  </th>
                  <th class="py-2 px-3">Product</th>
                  <th class="py-2 px-3 th-stock">Stock</th>
                  <th class="py-2 px-3 text-right">Qty</th>
                  <th class="py-2 px-3 text-right">Buy Price</th>
                  <th class="py-2 px-3 text-right font-semibold text-slate-800 bg-amber-50/50">Sell Price</th>
                  <th class="py-2 px-3 text-right font-bold border-l border-slate-200">P&L</th>
                  <th class="py-2 px-3">Date</th>
                </tr>
              </thead>
              <tbody id="exhaustedLotsBody" class="divide-y divide-slate-100 text-slate-700"></tbody>
            </table>
          </div>
        </div>
      </div>

      <div id="selectionStatsFooter" class="hidden absolute bottom-3 left-3 right-3 bg-slate-900 text-white rounded-lg shadow-xl border border-slate-800 p-2.5 z-30">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div class="text-xs font-bold text-slate-200">
            <span id="footerSelectedCount" class="text-blue-400 font-extrabold text-sm">0</span> Selected
          </div>
          <div class="flex items-center gap-2 text-xs flex-wrap" id="footerStatsContainer"></div>
          <button onclick="clearAllSelections()" class="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded border border-slate-700">Clear</button>
        </div>
      </div>
    </main>
  </div>

  <script>
    let RAW_TRADES = [];
    let LIVE_HOLDINGS = {};
    let COMPANY_NAMES = {};
    let LEDGER = [], OPEN_LOTS = [], EXHAUSTED_LOTS = [], CURRENT_HOLDINGS = {};
    let currentFilter = 'ALL';
    let currentView = 'LEDGER';
    let targetMarginPercent = 2.5;
    let selectedLedgerIndices = new Set();
    let selectedOpenLotIds = new Set();
    let selectedExhaustedIds = new Set();
    let isPolling = false;

    function renderProductBadge(prod) {
      const p = (prod || 'DELIVERY').toUpperCase();
      if (p === 'MTF') return `<span class="px-1 py-0.2 rounded text-[10px] font-bold bg-indigo-100 text-indigo-800 border border-indigo-200">MTF</span>`;
      if (p === 'INTRADAY') return `<span class="px-1 py-0.2 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">INTRADAY</span>`;
      return `<span class="px-1 py-0.2 rounded text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-300">DELIVERY</span>`;
    }

    function parseDateKey(dateStr) {
      if (!dateStr) return '';
      const s = String(dateStr).trim();
      const d = new Date(s);
      if (!isNaN(d.getTime())) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
      }
      return s.slice(0, 10);
    }

    function processLowestPriceFirst(trades, liveHoldingsMap = {}) {
      const stockDays = {};
      const allTradesNormalized = [];

      for (let idx = 0; idx < trades.length; idx++) {
        const t = trades[idx];
        const sym = String(t.stock || 'UNKNOWN').trim().toUpperCase();
        const dKey = parseDateKey(t.date);
        const qty = Number(t.quantity) || 0;
        const price = Number(t.price) || 0;
        const tradeAmount = Number(t.tradeAmount) || (qty * price);

        const record = {
          ...t,
          originalIndex: idx,
          stock: sym,
          companyName: t.companyName || COMPANY_NAMES[sym] || sym,
          dateKey: dKey,
          quantity: qty,
          price: price,
          tradeAmount: tradeAmount
        };

        allTradesNormalized.push(record);
        if (!stockDays[sym]) stockDays[sym] = {};
        if (!stockDays[sym][dKey]) stockDays[sym][dKey] = [];
        stockDays[sym][dKey].push(record);
      }

      const openLotsByStock = {};
      const allExhaustedLots = [];
      const ledger = [];

      for (const sym in stockDays) {
        openLotsByStock[sym] = [];
        const days = Object.keys(stockDays[sym]).sort();

        for (const day of days) {
          const dayTrades = stockDays[sym][day];
          const dayBuys = dayTrades.filter(t => t.type === 'BUY');
          const daySells = dayTrades.filter(t => t.type === 'SELL');

          const totBuyQty = dayBuys.reduce((sum, b) => sum + b.quantity, 0);
          const totSellQty = daySells.reduce((sum, s) => sum + s.quantity, 0);
          const intradayQty = Math.min(totBuyQty, totSellQty);

          let remIntradaySell = intradayQty;
          const intradayBuyLots = dayBuys.map(b => ({ ...b, remQty: b.quantity }));
          const intradaySellLots = daySells.map(s => ({ ...s, remQty: s.quantity }));

          for (const s of intradaySellLots) {
            let sellNeeded = Math.min(s.remQty, remIntradaySell);
            if (sellNeeded <= 0) continue;

            for (const b of intradayBuyLots) {
              if (sellNeeded <= 0) break;
              const take = Math.min(b.remQty, sellNeeded);
              if (take > 0) {
                b.remQty -= take;
                s.remQty -= take;
                sellNeeded -= take;
                remIntradaySell -= take;

                const costBasis = take * b.price;
                const revenue = take * s.price;
                const gain = revenue - costBasis;
                allExhaustedLots.push({
                  id: 'exh_intra_' + day + '_' + sym + '_' + b.originalIndex + '_' + s.originalIndex,
                  date: day,
                  stock: sym,
                  companyName: b.companyName,
                  product: s.product || 'INTRADAY',
                  buyPrice: b.price,
                  realizedSellPrice: s.price,
                  soldQty: take,
                  netGain: gain,
                  netGainPct: costBasis > 0 ? (gain / costBasis) * 100 : 0
                });
              }
            }
          }

          const netCarryBuy = totBuyQty - intradayQty;
          const netCarrySell = totSellQty - intradayQty;

          if (netCarryBuy > 0) {
            let remToAdd = netCarryBuy;
            for (const b of intradayBuyLots) {
              const take = Math.min(b.remQty, remToAdd);
              if (take > 0) {
                openLotsByStock[sym].push({
                  id: 'lot_' + day + '_' + sym + '_' + b.originalIndex,
                  date: b.date,
                  stock: sym,
                  companyName: b.companyName,
                  product: b.product || 'DELIVERY',
                  originalQty: take,
                  remainingQty: take,
                  buyPrice: b.price,
                  totalCost: take * b.price
                });
                b.remQty -= take;
                remToAdd -= take;
              }
            }
          }

          if (netCarrySell > 0) {
            let remToDeplete = netCarrySell;
            openLotsByStock[sym].sort((a, b) => a.buyPrice - b.buyPrice);

            for (const s of intradaySellLots) {
              let sellQtyAvail = Math.min(s.remQty, remToDeplete);
              if (sellQtyAvail <= 0) continue;

              for (const lot of openLotsByStock[sym]) {
                if (sellQtyAvail <= 0) break;
                const take = Math.min(lot.remainingQty, sellQtyAvail);
                if (take > 0) {
                  lot.remainingQty -= take;
                  sellQtyAvail -= take;
                  remToDeplete -= take;
                  s.remQty -= take;

                  const costBasis = take * lot.buyPrice;
                  const revenue = take * s.price;
                  const gain = revenue - costBasis;
                  allExhaustedLots.push({
                    id: 'exh_overnight_' + day + '_' + sym + '_' + lot.id,
                    date: day,
                    stock: sym,
                    companyName: lot.companyName,
                    product: s.product || 'DELIVERY',
                    buyPrice: lot.buyPrice,
                    realizedSellPrice: s.price,
                    soldQty: take,
                    netGain: gain,
                    netGainPct: costBasis > 0 ? (gain / costBasis) * 100 : 0
                  });
                }
              }
            }
            openLotsByStock[sym] = openLotsByStock[sym].filter(l => l.remainingQty > 0);
          }

          if (liveHoldingsMap && liveHoldingsMap[sym] !== undefined && liveHoldingsMap[sym] === 0) {
            if (day === days[days.length - 1]) {
              openLotsByStock[sym] = [];
            }
          }

          const currentLots = openLotsByStock[sym];
          const remQty = currentLots.reduce((acc, l) => acc + l.remainingQty, 0);
          const remCost = currentLots.reduce((acc, l) => acc + (l.remainingQty * l.buyPrice), 0);
          const runningAvg = remQty > 0 ? remCost / remQty : 0;

          for (const t of dayTrades) {
            ledger.push({
              ...t,
              runningAvg: runningAvg
            });
          }
        }
      }

      const allOpenLots = [];
      const perStockHoldings = {};

      for (const sym in openLotsByStock) {
        const active = openLotsByStock[sym].filter(l => l.remainingQty > 0);
        allOpenLots.push(...active);
        const holdingQty = active.reduce((acc, l) => acc + l.remainingQty, 0);
        const totalCost = active.reduce((acc, l) => acc + (l.remainingQty * l.buyPrice), 0);

        perStockHoldings[sym] = {
          holdingQty: holdingQty,
          totalCost: totalCost,
          avgPrice: holdingQty > 0 ? (totalCost / holdingQty) : 0,
          companyName: COMPANY_NAMES[sym] || sym,
          lots: active
        };
      }

      ledger.sort((a, b) => {
        const dateA = new Date(a.date).getTime();
        const dateB = new Date(b.date).getTime();
        if (dateA !== dateB) return dateB - dateA;
        return (b.order_seq || 0) - (a.order_seq || 0);
      });

      return { ledger, allOpenLots, allExhaustedLots, perStockHoldings };
    }

    async function loadData(force = false) {
      if (isPolling) return;
      isPolling = true;
      try {
        const url = force ? '/api/holdings?force=1' : '/api/holdings';
        const res = await fetch(url);
        const payload = await res.json();
        if (evaluateSessionError(payload)) return;

        RAW_TRADES = payload.data || [];
        LIVE_HOLDINGS = payload.live_holdings || {};
        COMPANY_NAMES = payload.company_names || {};

        const compiled = processLowestPriceFirst(RAW_TRADES, LIVE_HOLDINGS);
        LEDGER = compiled.ledger;
        OPEN_LOTS = compiled.allOpenLots;
        EXHAUSTED_LOTS = compiled.allExhaustedLots;
        CURRENT_HOLDINGS = compiled.perStockHoldings;

        renderStockList();
        renderWorkspace();

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

    function onTargetMarginChange() {
      const val = parseFloat(document.getElementById('targetMarginInput').value);
      targetMarginPercent = isNaN(val) ? 0 : val;
      renderWorkspace();
    }

    function switchView(view) {
      currentView = view;
      const btnLedger = document.getElementById('btnViewLedger');
      const btnLots = document.getElementById('btnViewOpenLots');
      const tableLedger = document.getElementById('viewLedgerTable');
      const containerLots = document.getElementById('viewOpenLotsContainer');
      if (view === 'LEDGER') {
        btnLedger.className = 'px-2.5 py-1 text-xs font-semibold rounded bg-slate-900 text-white';
        btnLots.className = 'px-2.5 py-1 text-xs font-semibold rounded bg-slate-100 text-slate-600 hover:bg-slate-200';
        tableLedger.classList.remove('hidden');
        containerLots.classList.add('hidden');
      } else {
        btnLots.className = 'px-2.5 py-1 text-xs font-semibold rounded bg-slate-900 text-white';
        btnLedger.className = 'px-2.5 py-1 text-xs font-semibold rounded bg-slate-100 text-slate-600 hover:bg-slate-200';
        containerLots.classList.remove('hidden');
        tableLedger.classList.add('hidden');
      }
      renderWorkspace();
      updateSelectionStatsFooter();
    }

    function selectStock(sym) {
      currentFilter = sym;
      document.querySelectorAll('.stock-tab').forEach(el => {
        el.classList.remove('bg-blue-50', 'text-blue-700', 'border-blue-200');
        el.classList.add('text-slate-600', 'border-transparent');
      });
      const activeBtn = document.getElementById('tab-' + sym);
      if (activeBtn) {
        activeBtn.classList.add('bg-blue-50', 'text-blue-700', 'border-blue-200');
        activeBtn.classList.remove('border-transparent');
      }
      renderWorkspace();
      updateSelectionStatsFooter();
    }

    function toggleTradeSelect(idx, checked) {
      if (checked) selectedLedgerIndices.add(idx);
      else selectedLedgerIndices.delete(idx);
      updateMasterCheckboxState();
      updateSelectionStatsFooter();
    }

    function toggleSelectAllLedger(checked) {
      const currentFiltered = currentFilter === 'ALL' ? LEDGER : LEDGER.filter(t => t.stock === currentFilter);
      currentFiltered.forEach(t => {
        if (checked) selectedLedgerIndices.add(t.originalIndex);
        else selectedLedgerIndices.delete(t.originalIndex);
      });
      renderLedgerTableRows();
      updateSelectionStatsFooter();
    }

    function toggleOpenLotSelect(id, checked) {
      if (checked) selectedOpenLotIds.add(id);
      else selectedOpenLotIds.delete(id);
      updateMasterCheckboxState();
      updateSelectionStatsFooter();
    }

    function toggleSelectAllOpenLots(checked) {
      const relevantLots = currentFilter === 'ALL' ? OPEN_LOTS : (CURRENT_HOLDINGS[currentFilter]?.lots || []);
      relevantLots.forEach(l => {
        if (checked) selectedOpenLotIds.add(l.id);
        else selectedOpenLotIds.delete(l.id);
      });
      renderOpenLotsRows();
      updateSelectionStatsFooter();
    }

    function toggleExhaustedSelect(id, checked) {
      if (checked) selectedExhaustedIds.add(id);
      else selectedExhaustedIds.delete(id);
      updateMasterCheckboxState();
      updateSelectionStatsFooter();
    }

    function toggleSelectAllExhausted(checked) {
      const relevantExhausted = currentFilter === 'ALL' ? EXHAUSTED_LOTS : EXHAUSTED_LOTS.filter(l => l.stock === currentFilter);
      relevantExhausted.forEach(l => {
        if (checked) selectedExhaustedIds.add(l.id);
        else selectedExhaustedIds.delete(l.id);
      });
      renderExhaustedLotsRows();
      updateSelectionStatsFooter();
    }

    function clearAllSelections() {
      if (currentView === 'LEDGER') {
        selectedLedgerIndices.clear();
        renderLedgerTableRows();
      } else {
        selectedOpenLotIds.clear();
        selectedExhaustedIds.clear();
        renderOpenLotsRows();
        renderExhaustedLotsRows();
      }
      updateMasterCheckboxState();
      updateSelectionStatsFooter();
    }

    function updateMasterCheckboxState() {
      if (currentView === 'LEDGER') {
        const master = document.getElementById('selectAllLedger');
        if (!master) return;
        const filtered = currentFilter === 'ALL' ? LEDGER : LEDGER.filter(t => t.stock === currentFilter);
        master.checked = filtered.length > 0 && filtered.every(t => selectedLedgerIndices.has(t.originalIndex));
      } else {
        const masterOpen = document.getElementById('selectAllOpenLots');
        if (masterOpen) {
          const relevantLots = currentFilter === 'ALL' ? OPEN_LOTS : (CURRENT_HOLDINGS[currentFilter]?.lots || []);
          masterOpen.checked = relevantLots.length > 0 && relevantLots.every(l => selectedOpenLotIds.has(l.id));
        }
        const masterExh = document.getElementById('selectAllExhausted');
        if (masterExh) {
          const relevantExhausted = currentFilter === 'ALL' ? EXHAUSTED_LOTS : EXHAUSTED_LOTS.filter(l => l.stock === currentFilter);
          masterExh.checked = relevantExhausted.length > 0 && relevantExhausted.every(l => selectedExhaustedIds.has(l.id));
        }
      }
    }

    function updateSelectionStatsFooter() {
      const footer = document.getElementById('selectionStatsFooter');
      const container = document.getElementById('footerStatsContainer');
      const countEl = document.getElementById('footerSelectedCount');

      if (currentView === 'LEDGER') {
        if (selectedLedgerIndices.size === 0) {
          footer.classList.add('hidden');
          return;
        }
        footer.classList.remove('hidden');
        countEl.innerText = selectedLedgerIndices.size;
        let totalRotated = 0, totalQty = 0, buyQty = 0, buyAmt = 0, sellQty = 0, sellAmt = 0;
        selectedLedgerIndices.forEach(idx => {
          const t = LEDGER.find(item => item.originalIndex === idx);
          if (!t) return;
          totalRotated += t.tradeAmount;
          totalQty += t.quantity;
          if (t.type === 'BUY') { buyQty += t.quantity; buyAmt += t.tradeAmount; }
          else { sellQty += t.quantity; sellAmt += t.tradeAmount; }
        });
        const buyAvg = buyQty > 0 ? buyAmt / buyQty : 0;
        const sellAvg = sellQty > 0 ? sellAmt / sellQty : 0;
        const netCash = sellAmt - buyAmt;
        container.innerHTML = `
          <div class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
            <span class="text-slate-400">Rotated:</span> <span class="font-bold text-amber-400">₹${totalRotated.toLocaleString('en-IN', {maximumFractionDigits: 2})}</span>
          </div>
          <div class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
            <span class="text-slate-400">Qty:</span> <span class="font-bold text-slate-200">${totalQty.toLocaleString()}</span>
          </div>
          <div class="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/40">
            <span class="text-emerald-400">Buy Avg:</span> <span class="font-bold text-emerald-300">₹${buyAvg.toFixed(2)}</span>
          </div>
          <div class="px-2 py-0.5 rounded bg-rose-950/60 border border-rose-800/40">
            <span class="text-rose-400">Sell Avg:</span> <span class="font-bold text-rose-300">₹${sellAvg.toFixed(2)}</span>
          </div>
          <div class="px-2 py-0.5 rounded bg-blue-950/60 border border-blue-800/40 font-bold ${netCash >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
            ${netCash >= 0 ? '+₹' : '-₹'}${Math.abs(netCash).toLocaleString('en-IN', {maximumFractionDigits: 2})}
          </div>
        `;
      } else {
        const hasOpenSelected = selectedOpenLotIds.size > 0;
        const hasExhSelected = selectedExhaustedIds.size > 0;
        if (!hasOpenSelected && !hasExhSelected) {
          footer.classList.add('hidden');
          return;
        }
        footer.classList.remove('hidden');
        if (hasOpenSelected) {
          countEl.innerText = selectedOpenLotIds.size;
          let totalQty = 0, totalVal = 0;
          selectedOpenLotIds.forEach(id => {
            const l = OPEN_LOTS.find(item => item.id === id);
            if (!l) return;
            totalQty += l.remainingQty;
            totalVal += (l.remainingQty * l.buyPrice);
          });
          const avgBuy = totalQty > 0 ? totalVal / totalQty : 0;
          const targetAvgSell = avgBuy * (1 + (targetMarginPercent / 100));
          const targetProfit = (totalVal * (1 + (targetMarginPercent / 100))) - totalVal;
          container.innerHTML = `
            <div class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
              <span class="text-slate-400">Qty:</span> <span class="font-bold text-slate-200">${totalQty.toLocaleString()}</span>
            </div>
            <div class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
              <span class="text-slate-400">Cost:</span> <span class="font-bold text-indigo-300">₹${totalVal.toLocaleString('en-IN', {maximumFractionDigits: 2})}</span>
            </div>
            <div class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
              <span class="text-slate-400">Avg:</span> <span class="font-bold text-blue-300">₹${avgBuy.toFixed(2)}</span>
            </div>
            <div class="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-700/50">
              <span class="text-emerald-400">Target:</span> <span class="font-bold text-emerald-300">₹${targetAvgSell.toFixed(2)}</span>
            </div>
            <div class="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-700/50">
              <span class="text-emerald-400">Profit:</span> <span class="font-bold text-emerald-300">+₹${targetProfit.toLocaleString('en-IN', {maximumFractionDigits: 2})}</span>
            </div>
          `;
        } else {
          countEl.innerText = selectedExhaustedIds.size;
          let totalQty = 0, totalGain = 0, totalBuyCost = 0, totalSellAmt = 0;
          selectedExhaustedIds.forEach(id => {
            const l = EXHAUSTED_LOTS.find(item => item.id === id);
            if (!l) return;
            totalQty += l.soldQty;
            totalGain += l.netGain;
            totalBuyCost += (l.soldQty * l.buyPrice);
            totalSellAmt += (l.soldQty * l.realizedSellPrice);
          });
          const avgBuyPrice = totalQty > 0 ? totalBuyCost / totalQty : 0;
          const avgSellPrice = totalQty > 0 ? totalSellAmt / totalQty : 0;
          container.innerHTML = `
            <div class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
              <span class="text-slate-400">Qty:</span> <span class="font-bold text-slate-200">${totalQty.toLocaleString()}</span>
            </div>
            <div class="px-2 py-0.5 rounded bg-indigo-950/60 border border-indigo-800/40">
              <span class="text-indigo-400">Buy Avg:</span> <span class="font-bold text-indigo-300">₹${avgBuyPrice.toFixed(2)}</span>
            </div>
            <div class="px-2 py-0.5 rounded bg-amber-950/60 border border-amber-800/40">
              <span class="text-amber-400">Sell Avg:</span> <span class="font-bold text-amber-300">₹${avgSellPrice.toFixed(2)}</span>
            </div>
            <div class="px-2 py-0.5 rounded border ${totalGain >= 0 ? 'bg-emerald-950/60 border-emerald-700/50 text-emerald-300' : 'bg-rose-950/60 border-rose-700/50 text-rose-300'} font-bold">
              P&L: ${totalGain >= 0 ? '+₹' : '-₹'}${Math.abs(totalGain).toLocaleString('en-IN', {maximumFractionDigits: 2})}
            </div>
          `;
        }
      }
    }

    function renderStockList() {
      const q = (document.getElementById('searchStock').value || '').toUpperCase().trim();
      const container = document.getElementById('stockListContainer');
      const stocks = Object.keys(CURRENT_HOLDINGS).sort();
      document.getElementById('badge-all-count').innerText = stocks.length;
      if (stocks.length === 0) {
        container.innerHTML = `<div class="p-3 text-center text-slate-400 text-xs">No records</div>`;
        return;
      }
      container.innerHTML = stocks
        .filter(s => {
          const compName = (CURRENT_HOLDINGS[s]?.companyName || '').toUpperCase();
          return s.includes(q) || compName.includes(q);
        })
        .map(sym => {
          const h = CURRENT_HOLDINGS[sym];
          const isSelected = currentFilter === sym;
          const isSettled = h.holdingQty === 0;
          return `
            <button onclick="selectStock('${sym}')" id="tab-${sym}" 
              class="stock-tab w-full text-left p-2 rounded border flex items-center justify-between text-xs ${
                isSelected ? 'bg-blue-50 text-blue-700 border-blue-200 font-semibold' : 'border-transparent text-slate-700 hover:bg-slate-50'
              }">
              <div class="min-w-0 pr-2">
                <div class="font-bold text-slate-900 flex items-center gap-1">
                  <span>${sym}</span>
                  ${isSettled ? '<span class="text-[9px] px-1 rounded bg-slate-100 text-slate-400 border border-slate-200">0</span>' : ''}
                </div>
                <div class="text-[10px] text-slate-400 truncate">${h.companyName}</div>
                <div class="text-[10px] ${isSettled ? 'text-slate-400' : 'text-slate-600'}">Qty: ${h.holdingQty.toLocaleString()}</div>
              </div>
              <div class="text-right font-semibold text-slate-800 shrink-0">
                ${isSettled ? '₹0.00' : '₹' + h.avgPrice.toFixed(2)}
              </div>
            </button>
          `;
        }).join('');
    }

    function renderLedgerTableRows() {
      const ledgerFiltered = currentFilter === 'ALL' ? LEDGER : LEDGER.filter(t => t.stock === currentFilter);
      const tbodyLedger = document.getElementById('transactionsBody');
      const showStock = currentFilter === 'ALL';

      if (ledgerFiltered.length === 0) {
        tbodyLedger.innerHTML = `<tr><td colspan="${showStock ? 9 : 8}" class="text-center py-8 text-slate-400">No records</td></tr>`;
        return;
      }
      tbodyLedger.innerHTML = ledgerFiltered.map(t => {
        const isBuy = t.type === 'BUY';
        const isChecked = selectedLedgerIndices.has(t.originalIndex);
        return `
          <tr class="hover:bg-slate-50 border-b border-slate-100 ${isChecked ? 'bg-blue-50/40' : ''}">
            <td class="py-2 px-3 text-center">
              <input type="checkbox" onchange="toggleTradeSelect(${t.originalIndex}, this.checked)" ${isChecked ? 'checked' : ''}
                class="rounded border-slate-300 text-blue-600">
            </td>
            <td class="py-2 px-3 text-slate-500 whitespace-nowrap font-mono text-[11px]">${t.date}</td>
            <td class="py-2 px-3 whitespace-nowrap">${renderProductBadge(t.product)}</td>
            ${showStock ? `
              <td class="py-2 px-3">
                <div class="font-bold text-slate-900">${t.stock}</div>
                <div class="text-[10px] text-slate-400 truncate max-w-[140px]">${t.companyName || ''}</div>
              </td>
            ` : ''}
            <td class="py-2 px-3 text-center">
              <span class="px-1.5 py-0.2 rounded text-[10px] font-bold ${
                isBuy ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
              }">${t.type}</span>
            </td>
            <td class="py-2 px-3 text-right font-medium">${t.quantity.toLocaleString()}</td>
            <td class="py-2 px-3 text-right">₹${t.price.toFixed(2)}</td>
            <td class="py-2 px-3 text-right text-slate-600">₹${t.tradeAmount.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
            <td class="py-2 px-3 text-right bg-blue-50/30 font-bold text-blue-700">₹${t.runningAvg.toFixed(2)}</td>
          </tr>
        `;
      }).join('');
      updateMasterCheckboxState();
    }

    function renderOpenLotsRows() {
      const relevantLots = currentFilter === 'ALL' ? [...OPEN_LOTS] : [...(CURRENT_HOLDINGS[currentFilter]?.lots || [])];
      relevantLots.sort((a, b) => a.buyPrice - b.buyPrice);
      let invested = 0;
      if (currentFilter === 'ALL') {
        Object.values(CURRENT_HOLDINGS).forEach(h => invested += h.totalCost);
      } else if (CURRENT_HOLDINGS[currentFilter]) {
        invested = CURRENT_HOLDINGS[currentFilter].totalCost;
      }
      const tbodyLots = document.getElementById('openLotsBody');
      const showStock = currentFilter === 'ALL';

      if (relevantLots.length === 0) {
        tbodyLots.innerHTML = `<tr><td colspan="${showStock ? 10 : 9}" class="text-center py-8 text-slate-400">No open lots</td></tr>`;
        return;
      }
      tbodyLots.innerHTML = relevantLots.map(l => {
        const val = l.remainingQty * l.buyPrice;
        const targetLotSell = l.buyPrice * (1 + (targetMarginPercent / 100));
        const share = invested > 0 ? ((val / invested) * 100).toFixed(1) : 0;
        const isChecked = selectedOpenLotIds.has(l.id);
        return `
          <tr class="hover:bg-slate-50 border-b border-slate-100 ${isChecked ? 'bg-blue-50/40' : ''}">
            <td class="py-2 px-3 text-center">
              <input type="checkbox" onchange="toggleOpenLotSelect('${l.id}', this.checked)" ${isChecked ? 'checked' : ''}
                class="rounded border-slate-300 text-blue-600">
            </td>
            <td class="py-2 px-3 whitespace-nowrap">${renderProductBadge(l.product)}</td>
            <td class="py-2 px-3 font-bold text-slate-900 bg-indigo-50/30">₹${l.buyPrice.toFixed(2)}</td>
            ${showStock ? `
              <td class="py-2 px-3">
                <div class="font-bold text-slate-800">${l.stock}</div>
                <div class="text-[10px] text-slate-400 truncate max-w-[140px]">${l.companyName || ''}</div>
              </td>
            ` : ''}
            <td class="py-2 px-3 text-right font-bold text-indigo-600">${l.remainingQty.toLocaleString()}</td>
            <td class="py-2 px-3 text-right text-slate-400">${l.originalQty.toLocaleString()}</td>
            <td class="py-2 px-3 text-right font-medium text-slate-700">₹${val.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
            <td class="py-2 px-3 text-right bg-emerald-50/30 font-bold text-emerald-700 border-l border-emerald-100">₹${targetLotSell.toFixed(2)}</td>
            <td class="py-2 px-3 text-slate-500 whitespace-nowrap font-mono text-[11px]">${l.date}</td>
            <td class="py-2 px-3 text-right text-slate-500">${share}%</td>
          </tr>
        `;
      }).join('');
      updateMasterCheckboxState();
    }

    function renderExhaustedLotsRows() {
      const relevantExhausted = currentFilter === 'ALL' ? [...EXHAUSTED_LOTS] : EXHAUSTED_LOTS.filter(l => l.stock === currentFilter);
      relevantExhausted.sort((a, b) => a.buyPrice - b.buyPrice);
      const tbodyExhausted = document.getElementById('exhaustedLotsBody');
      const showStock = currentFilter === 'ALL';

      if (relevantExhausted.length === 0) {
        tbodyExhausted.innerHTML = `<tr><td colspan="${showStock ? 8 : 7}" class="text-center py-6 text-slate-400">No exhausted records</td></tr>`;
        return;
      }
      tbodyExhausted.innerHTML = relevantExhausted.map(l => {
        const isChecked = selectedExhaustedIds.has(l.id);
        const isGainPositive = l.netGain >= 0;
        return `
          <tr class="hover:bg-slate-50 border-b border-slate-100 ${isChecked ? 'bg-blue-50/40' : ''}">
            <td class="py-2 px-3 text-center">
              <input type="checkbox" onchange="toggleExhaustedSelect('${l.id}', this.checked)" ${isChecked ? 'checked' : ''}
                class="rounded border-slate-300 text-blue-600">
            </td>
            <td class="py-2 px-3 whitespace-nowrap">${renderProductBadge(l.product)}</td>
            ${showStock ? `
              <td class="py-2 px-3">
                <div class="font-bold text-slate-800">${l.stock}</div>
                <div class="text-[10px] text-slate-400 truncate max-w-[140px]">${l.companyName || ''}</div>
              </td>
            ` : ''}
            <td class="py-2 px-3 text-right font-medium text-slate-700">${l.soldQty.toLocaleString()}</td>
            <td class="py-2 px-3 text-right font-bold text-slate-900">₹${l.buyPrice.toFixed(2)}</td>
            <td class="py-2 px-3 text-right font-bold text-amber-700 bg-amber-50/40 border-l border-amber-100">₹${l.realizedSellPrice.toFixed(2)}</td>
            <td class="py-2 px-3 text-right font-bold border-l border-slate-200 ${isGainPositive ? 'text-emerald-600' : 'text-rose-600'}">
              ${isGainPositive ? '+' : ''}₹${l.netGain.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
              <span class="text-[10px] block font-normal ${isGainPositive ? 'text-emerald-500' : 'text-rose-500'}">
                (${isGainPositive ? '+' : ''}${l.netGainPct.toFixed(2)}%)
              </span>
            </td>
            <td class="py-2 px-3 text-slate-500 whitespace-nowrap font-mono text-[11px]">${l.date}</td>
          </tr>
        `;
      }).join('');
      updateMasterCheckboxState();
    }

    function renderWorkspace() {
      const title = document.getElementById('selectedStockTitle');
      const subtitle = document.getElementById('selectedStockSubtitle');
      title.innerText = currentFilter === 'ALL' ? 'All Stocks' : currentFilter;
      subtitle.innerText = currentFilter === 'ALL' ? 'All Portfolio Positions' : (COMPANY_NAMES[currentFilter] || currentFilter);

      const isAll = currentFilter === 'ALL';
      document.querySelectorAll('.th-stock').forEach(el => {
        if (isAll) el.classList.remove('hidden');
        else el.classList.add('hidden');
      });

      let openQty = 0, avgPrice = 0, invested = 0;
      if (currentFilter === 'ALL') {
        Object.values(CURRENT_HOLDINGS).forEach(h => {
          openQty += h.holdingQty;
          invested += h.totalCost;
        });
        avgPrice = openQty > 0 ? invested / openQty : 0;
      } else if (CURRENT_HOLDINGS[currentFilter]) {
        const h = CURRENT_HOLDINGS[currentFilter];
        openQty = h.holdingQty;
        avgPrice = h.avgPrice;
        invested = h.totalCost;
      }
      const targetExitPrice = avgPrice > 0 ? (avgPrice * (1 + (targetMarginPercent / 100))) : 0;
      document.getElementById('summaryOpenQty').innerText = openQty.toLocaleString('en-IN');
      document.getElementById('summaryAvgPrice').innerText = '₹' + avgPrice.toFixed(2);
      document.getElementById('summaryTargetLabel').innerText = `Target (+${targetMarginPercent}%)`;
      document.getElementById('summaryTargetSellPrice').innerText = '₹' + targetExitPrice.toFixed(2);
      document.getElementById('summaryTotalInvested').innerText = '₹' + invested.toLocaleString('en-IN', { maximumFractionDigits: 2 });

      const relevantLots = currentFilter === 'ALL' ? [...OPEN_LOTS] : [...(CURRENT_HOLDINGS[currentFilter]?.lots || [])];
      const relevantExhausted = currentFilter === 'ALL' ? [...EXHAUSTED_LOTS] : EXHAUSTED_LOTS.filter(l => l.stock === currentFilter);

      document.getElementById('openLotsCount').innerText = relevantLots.length;
      document.getElementById('exhaustedLotsBadge').innerText = relevantExhausted.length;

      renderLedgerTableRows();
      renderOpenLotsRows();
      renderExhaustedLotsRows();
      updateSelectionStatsFooter();
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

def fetch_holdings_trades():
    breeze, is_auth = get_breeze_client()
    if not is_auth or not breeze:
        return {"error": "SESSION_EXPIRED", "login_url": LOGIN_URL}
    
    to_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    live_holdings = {}

    def fetch_positions():
        try:
            return breeze.get_portfolio_positions()
        except Exception as e:
            print(f"[-] Positions error: {e}")
            return None

    def fetch_exchange_trades(ex):
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

    # Parallelize Breeze requests
    raw_list = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        f_pos = executor.submit(fetch_positions)
        f_trades = [executor.submit(fetch_exchange_trades, ex) for ex in ["NSE", "BSE"]]

        pos_resp = f_pos.result()
        if pos_resp and isinstance(pos_resp.get("Success"), list):
            for p in pos_resp["Success"]:
                sym = str(p.get("stock_code") or "").strip().upper()
                q = parse_num(p.get("quantity"))
                live_holdings[sym] = live_holdings.get(sym, 0.0) + q

        for f in f_trades:
            ex, res = f.result()
            if res and isinstance(res.get("Success"), list):
                for item in res["Success"]:
                    item["_exchange"] = ex
                    raw_list.append(item)

    # Scrip name resolution (only for previously unseen codes)
    all_codes = list({
        str(r.get("stock_code") or r.get("stock_name") or "").strip().upper()
        for r in raw_list if (r.get("stock_code") or r.get("stock_name"))
    } | set(live_holdings.keys()))

    missing_names = [c for c in all_codes if c and c not in COMPANY_NAMES_CACHE]
    if missing_names:
        with ThreadPoolExecutor(max_workers=6) as executor:
            executor.map(lambda c: resolve_single_stock_name(breeze, c), missing_names)

    normalized = []
    for idx, r in enumerate(raw_list):
        stock_raw = str(r.get("stock_code") or r.get("stock_name") or "UNKNOWN").strip().upper()
        action = str(r.get("action") or "").strip().upper()
        side = "SELL" if "SELL" in action or action == "S" else "BUY"
        qty = parse_num(r.get("quantity"))
        total_amt = parse_num(r.get("average_cost"))
        
        if qty > 0 and total_amt > 0:
            price = round(total_amt / qty, 2)
        else:
            price = parse_num(r.get("execution_price") or r.get("price") or r.get("ltp"))
            total_amt = round(qty * price, 2)

        product_category = normalize_product_category(r.get("product_type"))
        dt = parse_date(r.get("trade_date") or r.get("order_date"))
        order_id = str(r.get("order_id") or "")
        order_seq = extract_order_seq(order_id)

        if qty > 0 and price > 0:
            normalized.append({
                "raw_index": idx,
                "date": dt,
                "stock": stock_raw,
                "companyName": COMPANY_NAMES_CACHE.get(stock_raw, stock_raw),
                "type": side,
                "quantity": qty,
                "price": price,
                "tradeAmount": total_amt,
                "product": product_category,
                "order_id": order_id,
                "order_seq": order_seq,
                "exchange_code": str(r.get("_exchange") or r.get("exchange_code") or "NSE")
            })

    return {
        "data": normalized, 
        "live_holdings": live_holdings,
        "company_names": COMPANY_NAMES_CACHE
    }

@holdings_bp.route("/holdings")
def view_holdings():
    return render_template_string(HOLDINGS_PAGE_HTML, active_page="holdings")

@holdings_bp.route("/api/holdings")
def api_holdings():
    force = request.args.get("force") == "1"
    # Micro-cache of 8 seconds to prevent hammering during polling
    data = get_or_set_cache("holdings_trades", 8, fetch_holdings_trades, force_refresh=force)
    return jsonify(data)