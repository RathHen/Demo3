"""
Credential loader: reads from Windows Credential Manager first, falls back
to environment variables / .env file. This module is shared by both
mcp_server.py and app.py so the lookup logic lives in one place.

To store credentials interactively, run:  store_credentials.bat
To clear them from Credential Manager, run:
    python -c "import credentials; credentials.clear_all()"
"""
import os

_SERVICE = "webull-dashboard"

# Keys stored in Credential Manager (secrets).
# Non-sensitive config (region, account ID, callback URLs) lives only in .env / env vars.
_KEYRING_KEYS = (
    "WEBULL_APP_KEY", "WEBULL_APP_SECRET", "DASHBOARD_PASSWORD",
    "SCHWAB_APP_KEY", "SCHWAB_APP_SECRET",
)


def _from_keyring(key: str) -> str:
    try:
        import keyring
        val = keyring.get_password(_SERVICE, key)
        return val or ""
    except Exception:
        return ""


def get(key: str, default: str = "") -> str:
    """Return a credential, preferring Credential Manager over env vars."""
    if key in _KEYRING_KEYS:
        val = _from_keyring(key)
        if val:
            return val
    return os.getenv(key, default)


def store(key: str, value: str) -> None:
    """Save a credential to Windows Credential Manager."""
    import keyring
    keyring.set_password(_SERVICE, key, value)


def clear_all() -> None:
    """Remove all stored Webull credentials from Credential Manager."""
    import keyring
    for key in _KEYRING_KEYS:
        try:
            keyring.delete_password(_SERVICE, key)
            print(f"  Cleared {key}")
        except Exception:
            pass
