import os
import webbrowser
from flask import Flask, jsonify, redirect, render_template_string, request, session, url_for
from breeze_core import LOGIN_URL, get_breeze_client, save_session_token
from holdings_page import holdings_bp
from mtf_page import mtf_bp
from trade_page import trade_bp

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

# ==========================================
# MASTER PASSWORD: Set your password here
# ==========================================
APP_PASSWORD = "Divyansh@123"

# Register page blueprints
app.register_blueprint(holdings_bp)
app.register_blueprint(mtf_bp)
app.register_blueprint(trade_bp)

UNLOCK_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Breeze Studio - Authentication</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4">
  <div class="w-full max-w-sm bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl">
    <div class="flex flex-col items-center mb-6">
      <div class="w-12 h-12 bg-blue-600/10 border border-blue-500/20 text-blue-400 rounded-xl flex items-center justify-center mb-3">
        <span class="material-icons text-2xl">lock</span>
      </div>
      <h1 class="text-lg font-bold text-slate-100 tracking-tight">Terminal Locked</h1>
      <p class="text-xs text-slate-400 mt-1 text-center">Enter master password to access Breeze Studio.</p>
    </div>

    <form onsubmit="handleUnlock(event)" class="space-y-4">
      <div>
        <label class="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Master Password</label>
        <input type="password" id="inputPassword" placeholder="••••••••••••" autofocus required
          class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 transition">
      </div>

      <button type="submit" id="btnSubmit" class="w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-lg transition active:scale-[0.98]">
        Unlock Terminal
      </button>

      <div id="unlockError" class="hidden text-rose-400 text-xs text-center font-medium bg-rose-500/10 border border-rose-500/20 rounded p-2"></div>
    </form>
  </div>

  <script>
    const STORAGE_KEY = 'breeze_saved_pwd';

    window.addEventListener('DOMContentLoaded', async () => {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        document.getElementById('inputPassword').value = saved;
        document.getElementById('btnSubmit').innerText = 'Validating saved key...';
        await attemptAuth(saved);
      }
    });

    async function handleUnlock(e) {
      e.preventDefault();
      const pwd = document.getElementById('inputPassword').value.trim();
      await attemptAuth(pwd);
    }

    async function attemptAuth(password) {
      const errorDiv = document.getElementById('unlockError');
      const submitBtn = document.getElementById('btnSubmit');
      errorDiv.classList.add('hidden');

      try {
        const res = await fetch('/api/verify_app_password', {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'X-App-Password': password 
          },
          body: JSON.stringify({ password: password })
        });
        const data = await res.json();

        if (res.ok && data.success) {
          localStorage.setItem(STORAGE_KEY, password);
          window.location.href = '/holdings';
        } else {
          localStorage.removeItem(STORAGE_KEY);
          submitBtn.innerText = 'Unlock Terminal';
          errorDiv.innerText = data.message || 'Incorrect password.';
          errorDiv.classList.remove('hidden');
        }
      } catch (err) {
        localStorage.removeItem(STORAGE_KEY);
        submitBtn.innerText = 'Unlock Terminal';
        errorDiv.innerText = 'Verification failed. Try again.';
        errorDiv.classList.remove('hidden');
      }
    }
  </script>
</body>
</html>
"""

@app.before_request
def enforce_security():
    exempt_endpoints = {"unlock_page", "api_verify_app_password", "static"}
    if request.endpoint in exempt_endpoints:
        return

    client_password = request.headers.get("X-App-Password")

    if client_password:
        if client_password == APP_PASSWORD:
            session["app_authenticated"] = True
            return
        else:
            session.pop("app_authenticated", None)
            if request.path.startswith("/api/"):
                return jsonify({"error": "FORBIDDEN", "message": "Invalid credentials"}), 401
            return redirect(url_for("unlock_page"))

    if not session.get("app_authenticated"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "FORBIDDEN", "message": "Password authentication required"}), 401
        return redirect(url_for("unlock_page"))

@app.route("/unlock")
def unlock_page():
    return render_template_string(UNLOCK_PAGE_HTML)

@app.route("/api/verify_app_password", methods=["POST"])
def api_verify_app_password():
    body = request.get_json(silent=True) or {}
    pwd = body.get("password") or request.headers.get("X-App-Password") or ""

    if pwd == APP_PASSWORD:
        session["app_authenticated"] = True
        return jsonify({"success": True})
    
    session.pop("app_authenticated", None)
    return jsonify({"success": False, "message": "Access Denied: Incorrect Password"}), 401

@app.route("/lock")
def lock_terminal():
    session.pop("app_authenticated", None)
    return redirect(url_for("unlock_page"))

@app.route("/")
def root():
    return redirect(url_for("holdings.view_holdings"))

@app.route("/login")
def login_redirect():
    return redirect(LOGIN_URL)

@app.route("/get_token", methods=["GET", "POST"])
def get_token():
    token = request.args.get("apisession") or request.args.get("token") or request.args.get("session_token")
    if not token and request.form:
        token = request.form.get("apisession") or request.form.get("token") or request.form.get("session_token")
    if not token and request.is_json:
        body = request.get_json(silent=True) or {}
        token = body.get("apisession") or body.get("token") or body.get("session_token")
    if token:
        save_session_token(token)
        _, success = get_breeze_client()
        print(f"[✓] Token updated: {token} (Breeze Auth: {success})")
        return redirect(url_for("holdings.view_holdings"))
    return redirect(LOGIN_URL)

if __name__ == "__main__":
    port = 5000
    print(f"[*] Breeze Server running: http://127.0.0.1:{port}")
    webbrowser.open(f"http://127.0.0.1:{port}/holdings")
    app.run(host="127.0.0.1", port=port, debug=True)