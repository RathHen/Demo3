"""
One-time Schwab API OAuth token setup.

Schwab uses OAuth 2.0. This script opens your browser to the Schwab login page.
After you log in and authorize the app, copy the full redirect URL from your
browser's address bar and paste it back here. The token is saved to disk and
the MCP server loads it automatically on startup (refreshing it when needed).

Run:  init_schwab_token.bat  (or: py -3.13 init_schwab_token.py)
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)

_runtime_dir = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or _here,
    "WebullDashboard",
)
os.makedirs(_runtime_dir, exist_ok=True)

from dotenv import load_dotenv
load_dotenv(os.path.join(_here, ".env"))

import credentials

SCHWAB_APP_KEY    = credentials.get("SCHWAB_APP_KEY")
SCHWAB_APP_SECRET = credentials.get("SCHWAB_APP_SECRET")
CALLBACK_URL      = os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1")

_TOKEN_FILE = os.path.join(_runtime_dir, "schwab_token.json")

print()
print("=" * 55)
print("  Schwab API — One-Time Token Setup")
print("=" * 55)
print()

if not SCHWAB_APP_KEY or not SCHWAB_APP_SECRET:
    print("ERROR: Schwab credentials not found.")
    print("Run  store_credentials.bat  first, enter your Schwab App Key and")
    print("App Secret, then re-run this script.")
    sys.exit(1)

try:
    import schwab
except ImportError:
    print("ERROR: schwab-py is not installed.")
    print("Run  install.bat  first, then re-run this script.")
    sys.exit(1)

print(f"  App Key      : {SCHWAB_APP_KEY[:8]}...")
print(f"  Callback URL : {CALLBACK_URL}")
print(f"  Token file   : {_TOKEN_FILE}")
print()
print("=" * 55)
print("  ACTION REQUIRED")
print("  1. A browser window will open — log in with your Schwab account")
print("     and click 'Allow' to authorize the app.")
print("  2. Your browser will redirect to your callback URL.")
print("     That page may show an error — that is expected.")
print("  3. Copy the FULL URL from the browser address bar and")
print("     paste it below when prompted.")
print("=" * 55)
print()

# Remove stale token so we always start a fresh flow.
if os.path.exists(_TOKEN_FILE):
    os.remove(_TOKEN_FILE)
    print(f"Removed old cached token: {_TOKEN_FILE}")
    print()

try:
    client = schwab.auth.easy_client(
        SCHWAB_APP_KEY,
        SCHWAB_APP_SECRET,
        CALLBACK_URL,
        _TOKEN_FILE,
    )

    print()
    print("Testing Schwab connection (fetching SPY option chain)...")
    r = client.get_option_chain("SPY", strike_count=1)
    if r.status_code == 200:
        data = r.json()
        if data.get("status") == "SUCCESS":
            exp_count = len(data.get("callExpDateMap", {}))
            print()
            print("SUCCESS! Schwab token saved and verified.")
            print(f"  Token file    : {_TOKEN_FILE}")
            print(f"  SPY expirations available: {exp_count}")
            print()
            print("Next steps:")
            print("  1. Fully quit Claude Desktop (right-click tray icon -> Quit)")
            print("  2. Reopen Claude Desktop")
            print("  3. Ask Claude about option chains — now powered by Schwab (real-time).")
            print()
            print("  Token auto-refreshes. Re-run this script only if it expires (~7 days).")
            print()
        else:
            print(f"Unexpected API status: {data.get('status')}")
            print(f"Full response: {data}")
            sys.exit(1)
    else:
        print(f"API returned HTTP {r.status_code}: {r.text}")
        sys.exit(1)

except KeyboardInterrupt:
    print()
    print("Cancelled.")
    sys.exit(0)
except Exception as e:
    err = str(e)
    print()
    print(f"Error: {err}")
    print()
    if "callback" in err.lower() or "redirect" in err.lower():
        print("Make sure your Schwab developer app has this callback URL registered:")
        print(f"  {CALLBACK_URL}")
        print()
        print("Set SCHWAB_CALLBACK_URL in your .env file if you use a different URL.")
    elif "invalid_client" in err.lower() or "401" in err:
        print("Authentication failed. Check that your App Key and App Secret are correct.")
        print("Re-run  store_credentials.bat  to update them.")
    sys.exit(1)
