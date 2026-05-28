"""
One-time Webull API token initialisation.

The Webull OpenAPI requires a 2FA approval the first time (and every ~15 days
when the token expires). This script triggers the token flow and waits for you
to approve the request inside the Webull mobile app. Once approved, the token
is cached to disk and the MCP server / Claude Desktop will work without 2FA.

Run:  init_token.bat  (or: py -3.13 init_token.py)
"""
import os
import sys
import time

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)

# Use the same runtime dir as mcp_server.py so the token cache is shared.
_runtime_dir = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or _here,
    "WebullDashboard",
)
os.makedirs(_runtime_dir, exist_ok=True)
os.chdir(_runtime_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(_here, ".env"))

import credentials

APP_KEY    = credentials.get("WEBULL_APP_KEY")
APP_SECRET = credentials.get("WEBULL_APP_SECRET")
REGION_ID  = credentials.get("WEBULL_REGION_ID", "us")
API_ENDPOINT = credentials.get("WEBULL_API_ENDPOINT")

print()
print("=" * 55)
print("  Webull API — One-Time Token Setup")
print("=" * 55)

if not APP_KEY or not APP_SECRET:
    print()
    print("ERROR: credentials not found.")
    print("Run  store_credentials.bat  first, then re-run this.")
    sys.exit(1)

token_path = os.path.join(_runtime_dir, "conf", "token.txt")
print(f"  App Key  : {APP_KEY[:8]}...")
print(f"  Region   : {REGION_ID}")
print(f"  Token file: {token_path}")
print()
print("Connecting to Webull and requesting a new token...")
print()
print(">>> OPEN THE WEBULL APP ON YOUR PHONE <<<")
print("    A verification / approval notification will appear.")
print("    Tap Approve. You have up to 5 minutes.")
print()

try:
    from webull.core.client import ApiClient
    client = ApiClient(APP_KEY, APP_SECRET, REGION_ID)
    if API_ENDPOINT:
        client.add_endpoint(REGION_ID, API_ENDPOINT)

    from webull.trade.trade_client import TradeClient
    tc = TradeClient(client)

    print("Waiting for your approval in the Webull app", end="", flush=True)
    start = time.time()
    while True:
        res = tc.account_v2.get_account_list()
        if res.status_code == 200:
            break
        if "INVALID_TOKEN" in res.text or "PENDING" in res.text.upper():
            elapsed = int(time.time() - start)
            if elapsed >= 300:
                print()
                print()
                print("ERROR: Timed out after 5 minutes. Please try again.")
                sys.exit(1)
            print(".", end="", flush=True)
            time.sleep(5)
            continue
        # Any other non-200 is a real error
        print()
        print(f"\nAPI error {res.status_code}: {res.text}")
        sys.exit(1)

    print()
    print()
    print("SUCCESS! Token approved and cached.")
    print(f"  Saved to: {token_path}")
    print()
    print("Next steps:")
    print("  1. Fully quit Claude Desktop (right-click tray icon → Quit)")
    print("  2. Reopen Claude Desktop")
    print("  3. Ask Claude about your Webull account — it should work now.")
    print()
    print("  The token lasts ~15 days. Run this script again when it expires.")
    print()

except Exception as e:
    print()
    print(f"Error: {e}")
    sys.exit(1)
