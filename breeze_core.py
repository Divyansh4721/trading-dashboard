from datetime import datetime
from decimal import Decimal
import json
import os
import re
import threading
import time
import urllib.parse
from breeze_connect import BreezeConnect

API_KEY = "2Fx2264E513(068024w66b17)0Vc5B06"
API_SECRET = "25210k18!841=263a459G31e4@1=6852"
TOKEN_FILE = "breeze_session.json"
NAMES_CACHE_FILE = "company_names.json"
LOGIN_URL = f"https://api.icicidirect.com/apiuser/login?api_key={urllib.parse.quote(API_KEY)}"
FROM_DATE = "2025-01-01T06:00:00.000Z"

# -----------------
# PERSISTENT SESSION
# -----------------
def load_session_token():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                return json.load(f).get("session_token", "")
        except Exception:
            pass
    return "57140902"

SESSION_TOKEN = load_session_token()
breeze_instance = None
_current_token = None
_auth_lock = threading.Lock()

# -----------------
# PERSISTENT NAMES CACHE
# -----------------
def load_names_cache():
    if os.path.exists(NAMES_CACHE_FILE):
        try:
            with open(NAMES_CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

COMPANY_NAMES_CACHE = load_names_cache()
_names_lock = threading.Lock()

def save_names_cache():
    with _names_lock:
        try:
            with open(NAMES_CACHE_FILE, "w") as f:
                json.dump(COMPANY_NAMES_CACHE, f, indent=2)
        except Exception as e:
            print(f"[-] Names write error: {e}")

def resolve_single_stock_name(breeze, code):
    if not code:
        return code, ""
    code_clean = str(code).strip().upper()
    with _names_lock:
        if code_clean in COMPANY_NAMES_CACHE:
            return code_clean, COMPANY_NAMES_CACHE[code_clean]

    try:
        res = breeze.get_names(exchange_code="NSE", stock_code=code_clean)
        if isinstance(res, dict):
            c_name = res.get("company name") or res.get("company_name") or res.get("exchange_stock_code") or code_clean
            c_name = str(c_name).strip()
            with _names_lock:
                COMPANY_NAMES_CACHE[code_clean] = c_name
            save_names_cache()
            return code_clean, c_name
    except Exception as e:
        print(f"[-] get_names error for {code_clean}: {e}")

    with _names_lock:
        COMPANY_NAMES_CACHE[code_clean] = code_clean
    return code_clean, code_clean

# -----------------
# CLIENT SINGLETON
# -----------------
def get_breeze_client():
    global breeze_instance, _current_token, SESSION_TOKEN
    if not SESSION_TOKEN:
        return None, False

    with _auth_lock:
        if breeze_instance is not None and _current_token == SESSION_TOKEN:
            return breeze_instance, True

        try:
            breeze = BreezeConnect(api_key=API_KEY)
            breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)
            breeze_instance = breeze
            _current_token = SESSION_TOKEN
            return breeze, True
        except Exception as e:
            print(f"[-] Breeze auth error: {e}")
            breeze_instance = None
            _current_token = None
            return None, False

def save_session_token(token):
    global SESSION_TOKEN, breeze_instance, _current_token
    with _auth_lock:
        SESSION_TOKEN = str(token).strip()
        breeze_instance = None
        _current_token = None
        clear_memory_cache()
        try:
            with open(TOKEN_FILE, "w") as f:
                json.dump({
                    "session_token": SESSION_TOKEN,
                    "updated_at": datetime.utcnow().isoformat()
                }, f, indent=2)
        except Exception as e:
            print(f"[-] Token write error: {e}")

# -----------------
# SHORT-LIVED IN-MEMORY CACHE
# -----------------
_CACHE = {}
_cache_lock = threading.Lock()

def get_or_set_cache(key, ttl_seconds, fetch_fn, force_refresh=False):
    now = time.time()
    with _cache_lock:
        if not force_refresh and key in _CACHE:
            data, expiry = _CACHE[key]
            if now < expiry:
                return data

    new_data = fetch_fn()
    
    # Don't cache error states
    if isinstance(new_data, dict) and new_data.get("error") == "SESSION_EXPIRED":
        return new_data

    with _cache_lock:
        _CACHE[key] = (new_data, now + ttl_seconds)
    return new_data

def clear_memory_cache():
    with _cache_lock:
        _CACHE.clear()

def get_short_token():
    return (SESSION_TOKEN[:4] + "..." + SESSION_TOKEN[-3:]) if len(SESSION_TOKEN) > 6 else SESSION_TOKEN

def parse_num(val):
    if not val:
        return 0.0
    try:
        return float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0

def to_dec(val):
    if val is None or val == "":
        return Decimal("0")
    try:
        return Decimal(str(val).replace(",", "").strip())
    except Exception:
        return Decimal("0")

def parse_date(date_str):
    if not date_str:
        return ""
    date_str = str(date_str).strip()
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str[:11].strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return date_str[:10]

def normalize_product_category(raw_prod):
    p = str(raw_prod or "").strip().upper()
    if p in ["EASYMARGIN", "MARGIN", "MTF"]:
        return "MTF"
    elif p in ["A", "INTRADAY"]:
        return "INTRADAY"
    return "DELIVERY"

def extract_order_seq(order_id_str):
    if not order_id_str:
        return -1
    m = re.search(r"^\d{8}[A-Za-z]+(\d+)$", str(order_id_str).strip())
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return -1
    digits = ""
    for ch in reversed(str(order_id_str).strip()):
        if ch.isdigit():
            digits = ch + digits
        else:
            break
    if digits:
        try:
            return int(digits)
        except ValueError:
            return -1
    return -1

NAVBAR_HTML = """
<div id="sessionBanner" class="hidden bg-rose-600 text-white px-4 py-2 flex items-center justify-between z-50 text-xs font-semibold">
  <span>Session token expired. Re-authenticate.</span>
  <a href="/login" class="bg-white text-rose-700 px-3 py-0.5 rounded font-bold">Login</a>
</div>
<header class="h-11 bg-slate-900 text-white px-4 flex items-center justify-between shrink-0 border-b border-slate-800 z-40">
  <div class="flex items-center gap-4">
    <span class="font-black text-xs tracking-wider uppercase text-blue-400">Breeze Studio</span>
    <nav class="flex gap-2 text-xs">
      <a href="/holdings" class="px-3 py-1 rounded {% if active_page == 'holdings' %}bg-blue-600 text-white font-bold{% else %}text-slate-300 hover:bg-slate-800{% endif %}">
        Inventory
      </a>
      <a href="/mtf" class="px-3 py-1 rounded {% if active_page == 'mtf' %}bg-indigo-600 text-white font-bold{% else %}text-slate-300 hover:bg-slate-800{% endif %}">
        MTF Audit
      </a>
      <a href="/trade" class="px-3 py-1 rounded {% if active_page == 'trade' %}bg-emerald-600 text-white font-bold{% else %}text-slate-300 hover:bg-slate-800{% endif %}">
        Order Pad
      </a>
    </nav>
  </div>
  <div class="flex items-center gap-3 text-xs">
    <div class="flex items-center gap-1.5 text-[11px] text-slate-400">
      <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
      <span id="syncStatusLabel">Live</span>
    </div>
    <a href="/login" class="bg-slate-800 hover:bg-slate-700 text-slate-200 px-2 py-0.5 rounded border border-slate-700">Token</a>
    <button onclick="refreshData(true)" class="bg-slate-800 hover:bg-slate-700 text-slate-200 px-2 py-0.5 rounded border border-slate-700">Refresh</button>
    <button onclick="lockApp()" class="bg-rose-950/60 hover:bg-rose-900 border border-rose-800 text-rose-300 px-2 py-0.5 rounded" title="Lock App">Lock</button>
  </div>
</header>
<script>
  (function() {
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
      let [resource, config] = args;
      config = config || {};
      config.headers = config.headers || {};

      const savedPwd = localStorage.getItem('breeze_saved_pwd') || '';

      if (config.headers instanceof Headers) {
        config.headers.set('X-App-Password', savedPwd);
      } else if (Array.isArray(config.headers)) {
        config.headers.push(['X-App-Password', savedPwd]);
      } else {
        config.headers['X-App-Password'] = savedPwd;
      }

      const response = await originalFetch(resource, config);

      if (response.status === 401) {
        localStorage.removeItem('breeze_saved_pwd');
        window.location.href = '/unlock';
        return Promise.reject(new Error('Unauthorized - invalid app password'));
      }

      return response;
    };
  })();

  function lockApp() {
    localStorage.removeItem('breeze_saved_pwd');
    window.location.href = '/lock';
  }

  function evaluateSessionError(payload) {
    const banner = document.getElementById('sessionBanner');
    if (payload && payload.error === 'SESSION_EXPIRED') {
      if (banner) banner.classList.remove('hidden');
      return true;
    }
    if (banner) banner.classList.add('hidden');
    return false;
  }
</script>
"""