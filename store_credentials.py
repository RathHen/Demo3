"""
Interactively prompt for Webull credentials and store them in
Windows Credential Manager. Run via store_credentials.bat.
"""
import getpass
import os
import sys

# Load .env so existing values show as defaults
_here = os.path.dirname(os.path.abspath(__file__))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_here, ".env"))
except ImportError:
    pass

try:
    import keyring
except ImportError:
    print("ERROR: keyring is not installed. Run:  pip install keyring")
    sys.exit(1)

from credentials import _SERVICE

PROMPTS = [
    ("WEBULL_APP_KEY",      "Webull App Key",      False),
    ("WEBULL_APP_SECRET",   "Webull App Secret",   True),
    ("DASHBOARD_PASSWORD",  "Dashboard Password (for tunnel access)", True),
]

print()
print("Webull Credential Setup")
print("Credentials will be stored in Windows Credential Manager (encrypted).")
print("Press Enter to keep the current value.  Input is hidden for secrets.")
print()

stored = []
for env_key, label, secret in PROMPTS:
    current = keyring.get_password(_SERVICE, env_key) or os.getenv(env_key, "")
    hint = " [already set]" if current else ""

    if secret:
        val = getpass.getpass(f"  {label}{hint}: ")
    else:
        val = input(f"  {label}{hint}: ")

    if val.strip():
        keyring.set_password(_SERVICE, env_key, val.strip())
        stored.append(env_key)
    elif current:
        stored.append(f"{env_key} (unchanged)")

print()
if stored:
    print("Saved to Windows Credential Manager:")
    for s in stored:
        print(f"  {s}")
else:
    print("Nothing changed.")

print()
print("Non-secret config (WEBULL_REGION_ID, WEBULL_ACCOUNT_ID) still comes")
print("from your .env file — edit that in Notepad for those values.")
print()
