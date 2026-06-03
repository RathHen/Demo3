"""
One-time Schwab API OAuth token setup.

Run:  init_schwab_token.bat  (or: py -3.13 init_schwab_token.py)
"""
import os
import sys

# Everything must be inside this guard on Windows — schwab-py spawns a
# subprocess for its redirect server, which re-imports this module.
# Any top-level code outside __main__ runs again in that subprocess,
# causing the multiprocessing bootstrap error.
if __name__ == "__main__":
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
    CALLBACK_URL      = os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182")
    _TOKEN_FILE       = os.path.join(_runtime_dir, "schwab_token.json")

    print()
    print("=" * 55)
    print("  Schwab API — One-Time Token Setup")
    print("=" * 55)
    print()

    if not SCHWAB_APP_KEY or not SCHWAB_APP_SECRET:
        print("ERROR: Schwab credentials not found.")
        print("Run  store_credentials.bat  first, then re-run this.")
        sys.exit(1)

    try:
        import schwab
    except ImportError:
        print("ERROR: schwab-py is not installed.")
        print("Run  install.bat  first, then re-run this.")
        sys.exit(1)

    print(f"  App Key      : {SCHWAB_APP_KEY[:8]}...")
    print(f"  Callback URL : {CALLBACK_URL}")
    print(f"  Token file   : {_TOKEN_FILE}")
    print()
    print("=" * 55)
    print("  ACTION REQUIRED")
    print("  1. A browser window will open — log in with your Schwab")
    print("     account and click 'Allow' to authorize the app.")
    print("  2. Your browser redirects to the callback URL.")
    print("     A connection error in the browser is expected.")
    print("  3. Copy the FULL URL from the browser address bar")
    print("     and paste it when prompted below.")
    print("=" * 55)
    print()

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
                print(f"  Token file              : {_TOKEN_FILE}")
                print(f"  SPY expirations found   : {exp_count}")
                print()
                print("Next steps:")
                print("  1. Fully quit Claude Desktop (tray icon -> Quit)")
                print("  2. Reopen Claude Desktop")
                print("  3. Ask Claude about option chains — now real-time via Schwab.")
                print()
                print("  Token auto-refreshes. Re-run only if it expires (~7 days).")
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
            print("Make sure your Schwab developer app has this callback URL:")
            print(f"  {CALLBACK_URL}")
            print()
            print("Set SCHWAB_CALLBACK_URL in .env if you use a different URL.")
        elif "invalid_client" in err.lower() or "401" in err:
            print("Authentication failed — check App Key and App Secret.")
            print("Re-run  store_credentials.bat  to update them.")
        sys.exit(1)
