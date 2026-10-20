import os
import json
import time
import requests
import concurrent.futures
from flask import Blueprint, render_template, jsonify, request

dashboard2_bp = Blueprint("dashboard2", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SECTOR_PATH = os.path.join(BASE_DIR, "dashboard", "sectors.json")


class StrictOISpurtsEngine:

    def __init__(self, sector_file_path: str = DEFAULT_SECTOR_PATH):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
        }
        self.symbol_meta = {}
        self.symbol_meta_raw = {}
        self._load_sector_mappings(sector_file_path)
        self._init_session()

    def _init_session(self):
        try:
            self.session.get(
                "https://www.nseindia.com", headers=self.headers, timeout=8
            )
        except Exception as e:
            print(f"Session init notice: {e}")

    def _load_sector_mappings(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.symbol_meta_raw = data
            for sector, codes in data.items():
                if isinstance(codes, list):
                    for code in codes:
                        sym = code.upper().strip()
                        self.symbol_meta[sym] = {"sector": sector, "industry": sector}
        except Exception as e:
            print(f"Error loading sectors file ({path}): {e}")

    def _fetch_json(self, url: str) -> dict:
        try:
            res = self.session.get(url, headers=self.headers, timeout=8)
            if res.status_code in (401, 403):
                self._init_session()
                res = self.session.get(url, headers=self.headers, timeout=8)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
        return {}

    def fetch_symbol_chart(self, symbol: str) -> list:
        chart_sym = symbol if symbol.endswith("EQN") else f"{symbol}EQN"
        url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getSymbolChartData&symbol={chart_sym}&days=1D"
        data = self._fetch_json(url)
        points = []
        try:
            grapth_data = data.get("grapthData", [])
            if grapth_data:
                stride = max(1, len(grapth_data) // 150)
                points = [
                    round(float(pt[1]), 2)
                    for pt in grapth_data[::stride]
                    if len(pt) > 1 and pt[1] is not None
                ]
        except Exception:
            pass
        return points

    def fetch_symbol_detail(self, symbol: str) -> dict:
        clean_sym = symbol.replace("EQN", "")
        url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getSymbolData&marketType=N&series=EQ&symbol={clean_sym}"
        data = self._fetch_json(url)
        try:
            eq_resp = data.get("equityResponse", [{}])[0]
            ob = eq_resp.get("orderBook", {})
            ti = eq_resp.get("tradeInfo", {})
            pi = eq_resp.get("priceInfo", {})
            return {
                "symbol": clean_sym,
                "orderBook": {
                    "bids": [
                        {
                            "price": ob.get(f"buyPrice{i}", 0),
                            "qty": ob.get(f"buyQuantity{i}", 0),
                        }
                        for i in range(1, 6)
                    ],
                    "asks": [
                        {
                            "price": ob.get(f"sellPrice{i}", 0),
                            "qty": ob.get(f"sellQuantity{i}", 0),
                        }
                        for i in range(1, 6)
                    ],
                    "totalBuyQty": ob.get("totalBuyQuantity", 0),
                    "totalSellQty": ob.get("totalSellQuantity", 0),
                    "perBuyQty": ob.get("perBuyQty", 50),
                    "perSellQty": ob.get("perSellQty", 50),
                },
                "deliveryPct": ti.get("deliveryToTradedQuantity", 0),
                "totalTradedValue": ti.get("totalTradedValue", 0),
                "totalTradedVolume": ti.get("totalTradedVolume", 0),
                "yearHigh": pi.get("yearHigh", 0),
                "yearLow": pi.get("yearLow", 0),
                "dayHigh": pi.get("intraDayHighLow", {}).get("max", 0),
                "dayLow": pi.get("intraDayHighLow", {}).get("min", 0),
            }
        except Exception:
            return {}

    @staticmethod
    def calculate_technical_indicators(
        points: list, fallback_pchange: float = 0.0
    ) -> dict:
        if not points or len(points) < 15:
            base_rsi = round(min(max(50.0 + (fallback_pchange * 4.2), 15.0), 88.0), 1)
            macd_est = round(fallback_pchange * 0.45, 2)
            return {
                "rsi": base_rsi,
                "macd": macd_est,
                "macd_signal": "BUY" if macd_est >= 0 else "SELL",
            }

        gains, losses = [], []
        for i in range(1, len(points)):
            change = points[i] - points[i - 1]
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))

        period = min(14, len(gains))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = round(100.0 - (100.0 / (1.0 + rs)), 1)

        def ema(series, span):
            k = 2.0 / (span + 1.0)
            val = series[0]
            for pt in series[1:]:
                val = (pt * k) + (val * (1.0 - k))
            return val

        if len(points) >= 26:
            ema12 = ema(points, 12)
            ema26 = ema(points, 26)
            macd_line = round(ema12 - ema26, 2)
        else:
            macd_line = round(points[-1] - points[0], 2)

        return {
            "rsi": rsi,
            "macd": macd_line,
            "macd_signal": "BUY" if macd_line >= 0 else "SELL",
        }

    def fetch_processed_stocks(self) -> tuple[list, dict, dict]:
        url_nifty500 = "https://www.nseindia.com/api/NextApi/apiClient/marketWatchApi?functionName=getIndicesData&symbol=NIFTY%20500"
        url_oi = "https://www.nseindia.com/api/live-analysis-oi-spurts-underlyings"

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            fut_nifty = pool.submit(self._fetch_json, url_nifty500)
            fut_oi = pool.submit(self._fetch_json, url_oi)
            nifty_resp = fut_nifty.result()
            oi_resp = fut_oi.result()

        oi_items = oi_resp.get("data", [])
        stocks_raw = nifty_resp.get("data", {}).get("data", [])
        equity_map = {
            item.get("symbol", "").upper().strip(): item
            for item in stocks_raw
            if item.get("symbol")
        }

        processed = []
        sector_totals = {}
        ignored = {
            "NIFTY",
            "BANKNIFTY",
            "FINNIFTY",
            "MIDCPNIFTY",
            "NIFTYNXT50",
            "NIFTYFPI",
        }

        for oi_item in oi_items:
            sym = oi_item.get("symbol", "").upper().strip()
            if not sym or sym in ignored:
                continue

            eq_item = equity_map.get(sym, {})
            ltp = float(eq_item.get("lastPrice") or oi_item.get("underlyingValue", 0.0))
            if ltp == 0.0:
                continue

            open_p = float(eq_item.get("open") or ltp)
            high = float(eq_item.get("dayHigh") or ltp)
            low = float(eq_item.get("dayLow") or ltp)
            year_high = float(eq_item.get("yearHigh") or high)
            year_low = float(eq_item.get("yearLow") or low)
            prev_close = float(eq_item.get("previousClose") or open_p)
            vol = int(eq_item.get("totalTradedVolume") or oi_item.get("volume", 0))

            pchange = float(
                eq_item.get("pChange")
                or (
                    round(((ltp - prev_close) / prev_close) * 100, 2)
                    if prev_close
                    else 0.0
                )
            )

            meta = self.symbol_meta.get(
                sym, {"sector": "Others", "industry": "F&O Stock"}
            )
            sec = meta["sector"]
            ind = meta["industry"]

            if sec not in sector_totals:
                sector_totals[sec] = {"sum": 0.0, "count": 0}
            sector_totals[sec]["sum"] += pchange
            sector_totals[sec]["count"] += 1

            latest_oi = int(oi_item.get("latestOI", 0))
            delta_oi = int(oi_item.get("changeInOI", 0))
            pchange_oi = float(oi_item.get("avgInOI", 0.0))

            if pchange > 0 and delta_oi > 0:
                buildup = "LONG BUILD-UP"
            elif pchange < 0 and delta_oi > 0:
                buildup = "SHORT BUILD-UP"
            elif pchange > 0 and delta_oi < 0:
                buildup = "SHORT COVERING"
            elif pchange < 0 and delta_oi < 0:
                buildup = "LONG UNWINDING"
            else:
                buildup = "NEUTRAL"

            tech = self.calculate_technical_indicators([], pchange)
            company_name = eq_item.get("companyName") or sym

            processed.append(
                {
                    "symbol": sym,
                    "companyName": company_name,
                    "sector": sec,
                    "industry": ind,
                    "direction": "BULLISH" if pchange >= 0 else "BEARISH",
                    "ltp": ltp,
                    "change": round(ltp - prev_close, 2),
                    "pchange": pchange,
                    "dayHigh": high,
                    "dayLow": low,
                    "yearHigh": year_high,
                    "yearLow": year_low,
                    "derivatives": {
                        "open_interest": latest_oi,
                        "delta_oi": delta_oi,
                        "oi_change_pct": pchange_oi,
                        "buildup": buildup,
                    },
                    "technicals": tech,
                    "chartPoints": [],
                }
            )

        sector_rail = []
        for sec, d in sector_totals.items():
            avg_chg = round(d["sum"] / d["count"], 2) if d["count"] > 0 else 0.0
            sector_rail.append(
                {"sector": sec, "avg_change_pct": avg_chg, "count": d["count"]}
            )
        sector_rail.sort(key=lambda x: x["avg_change_pct"], reverse=True)

        breadth = {
            "bullish_count": len([s for s in processed if s["direction"] == "BULLISH"]),
            "bearish_count": len([s for s in processed if s["direction"] == "BEARISH"]),
            "total": len(processed),
        }

        return processed, sector_rail, breadth

    def fetch_market_snapshot(self) -> dict:
        processed, sector_rail, breadth = self.fetch_processed_stocks()
        if not processed:
            return {
                "breadth": {"bullish_count": 0, "bearish_count": 0, "total": 0},
                "sector_rail": [],
                "top_bullish": [],
                "top_bearish": [],
            }

        bulls = sorted(
            [s for s in processed if s["direction"] == "BULLISH"],
            key=lambda x: x["pchange"],
            reverse=True,
        )[:20]
        bears = sorted(
            [s for s in processed if s["direction"] == "BEARISH"],
            key=lambda x: x["pchange"],
        )[:20]

        top_symbols = [s["symbol"] for s in bulls[:3]] + [
            s["symbol"] for s in bears[:3]
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures = {
                pool.submit(self.fetch_symbol_chart, sym): sym for sym in top_symbols
            }
            chart_map = {}
            for fut in concurrent.futures.as_completed(futures):
                sym = futures[fut]
                chart_map[sym] = fut.result()

        for s in bulls[:3] + bears[:3]:
            pts = chart_map.get(s["symbol"], [])
            s["chartPoints"] = pts
            if pts:
                s["technicals"] = self.calculate_technical_indicators(pts, s["pchange"])

        return {
            "breadth": breadth,
            "sector_rail": sector_rail,
            "top_bullish": bulls,
            "top_bearish": bears,
        }


engine = StrictOISpurtsEngine(sector_file_path=DEFAULT_SECTOR_PATH)


# --- BLUEPRINT ROUTES ---


@dashboard2_bp.route("/dashboard2")
def view_dashboard2():
    # Renders templates/index.html (Flask looks inside the templates/ folder)
    return render_template("index.html", active_page="dashboard2")


@dashboard2_bp.route("/api/market", methods=["GET"])
def get_market_data():
    return jsonify(engine.fetch_market_snapshot())


@dashboard2_bp.route("/api/symbol/chart", methods=["GET"])
def get_symbol_chart():
    symbol = request.args.get("symbol", "").upper().strip()
    points = engine.fetch_symbol_chart(symbol)
    tech = engine.calculate_technical_indicators(points)
    return jsonify(
        {"symbol": symbol, "points": points, "count": len(points), "technicals": tech}
    )


@dashboard2_bp.route("/api/symbol/detail", methods=["GET"])
def get_symbol_detail():
    symbol = request.args.get("symbol", "").upper().strip()
    detail = engine.fetch_symbol_detail(symbol)
    return jsonify(detail)
