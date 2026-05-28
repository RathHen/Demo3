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

APP_KEY      = credentials.get("WEBULL_APP_KEY")
APP_SECRET   = credentials.get("WEBULL_APP_SECRET")
REGION_ID    = credentials.get("WEBULL_REGION_ID", "us")
ENVIRONMENT  = os.environ.get("WEBULL_ENVIRONMENT", "prod")
API_ENDPOINT = credentials.get("WEBULL_API_ENDPOINT")

print()
print("=" * 55)
print("  Webull API — One-Time Token Setup")
print("=" * 55)
print()

if not APP_KEY or not APP_SECRET:
    print("ERROR: credentials not found.")
    print("Run  store_credentials.bat  first, then re-run this.")
    sys.exit(1)

token_path = os.path.join(_runtime_dir, "conf", "token.txt")
print(f"  App Key   : {APP_KEY[:8]}...")
print(f"  Region    : {REGION_ID}")
print(f"  Env       : {ENVIRONMENT}")
print(f"  Token file: {token_path}")
print()

# Delete any stale cached token so the SDK always starts a fresh flow.
stale = os.path.join(_runtime_dir, "conf", "token.txt")
if os.path.exists(stale):
    os.remove(stale)
    print("Removed old cached token.")

print("Starting token request. The SDK will now connect to Webull...")
print()
print("=" * 55)
print("  ACTION REQUIRED")
print("  Open the Webull app on your phone.")
print("  A verification notification will appear — tap Approve.")
print("  You have up to 5 minutes.")
print("=" * 55)
print()

try:
    from webull.core.client import ApiClient

    # token_check_duration_seconds=300 lets the SDK poll for 2FA approval
    # for up to 5 minutes (default is already 300, but we set it explicitly).
    client = ApiClient(
        APP_KEY,
        APP_SECRET,
        REGION_ID,
        token_check_duration_seconds=300,
        token_check_interval_seconds=5,
    )
    if API_ENDPOINT:
        client.add_endpoint(REGION_ID, API_ENDPOINT)

    print("ApiClient created. Connecting to trade API...")

    from webull.trade.trade_client import TradeClient
    tc = TradeClient(client)

    print("TradeClient ready. Calling account list to verify token...")
    res = tc.account_v2.get_account_list()

    if res.status_code == 200:
        print()
        print("SUCCESS! Token approved and cached.")
        print(f"  Saved to: {token_path}")
        print()
        data = res.json()
        accounts = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(accounts, list) and accounts:
            print(f"  Found {len(accounts)} account(s):")
            for acct in accounts:
                aid = acct.get("account_id") or acct.get("id", "?")
                print(f"    - {aid}")
            print()
            print("  Copy your account ID into the .env file:")
            print("    WEBULL_ACCOUNT_ID=<id from above>")
        print()
        print("Next steps:")
        print("  1. Fully quit Claude Desktop (right-click tray icon -> Quit)")
        print("  2. Reopen Claude Desktop")
        print("  3. Ask Claude about your Webull account.")
        print()
        print("  Token lasts ~15 days. Re-run this script when it expires.")
        print()
    else:
        print()
        print(f"API returned status {res.status_code}: {res.text}")
        print("Token may not be activated. Check the Webull app for a pending")
        print("verification request and tap Approve, then re-run this script.")
        sys.exit(1)

except Exception as e:
    err = str(e)
    print()
    print(f"Error: {err}")
    print()
    if "INVALID_TOKEN" in err or "token" in err.lower():
        print("The token was not approved or has expired.")
        print("Make sure you tap Approve in the Webull app when the notification")
        print("appears, then re-run this script.")
    elif "401" in err or "UNAUTHORIZED" in err:
        print("Authentication failed. Possible causes:")
        print("  - Wrong APP_KEY or APP_SECRET (run store_credentials.bat again)")
        print("  - API application not yet approved in the developer portal")
        print("  - Account not enabled for API access")
    sys.exit(1)
