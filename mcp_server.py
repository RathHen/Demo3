import concurrent.futures
import contextlib
import functools
import json
import os
import sys

# Resolve paths relative to this script so Claude Desktop can launch from anywhere.
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)

# Claude Desktop launches this process with the working directory set to a
# protected system folder (e.g. C:\Windows\System32). The Webull SDK writes a
# log file and caches its 2FA token relative to the working directory, so move
# to a writable, persistent runtime folder before any SDK calls run.
_runtime_dir = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or _here,
    "WebullDashboard",
)
try:
    os.makedirs(_runtime_dir, exist_ok=True)
    os.chdir(_runtime_dir)
except OSError:
    pass

from dotenv import load_dotenv
load_dotenv(os.path.join(_here, ".env"))

import credentials
from mcp.server.fastmcp import FastMCP

APP_KEY = credentials.get("WEBULL_APP_KEY")
APP_SECRET = credentials.get("WEBULL_APP_SECRET")
REGION_ID = credentials.get("WEBULL_REGION_ID", "us")
API_ENDPOINT = credentials.get("WEBULL_API_ENDPOINT")
ACCOUNT_ID = credentials.get("WEBULL_ACCOUNT_ID")

mcp = FastMCP("Webull")


def _quiet(fn):
    """
    Run the wrapped tool with stdout redirected to stderr. The MCP stdio
    transport uses stdout for JSON-RPC, so any stray print or SDK log line on
    stdout would corrupt the protocol. Because the Webull SDK is imported lazily
    inside the tools, running here also binds its logging handlers to stderr.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with contextlib.redirect_stdout(sys.stderr):
            return fn(*args, **kwargs)
    return wrapper


def _api_client():
    from webull.core.client import ApiClient
    client = ApiClient(APP_KEY, APP_SECRET, REGION_ID)
    if API_ENDPOINT:
        client.add_endpoint(REGION_ID, API_ENDPOINT)
    return client


def _trade():
    from webull.trade.trade_client import TradeClient
    return TradeClient(_api_client())


def _data():
    from webull.data.data_client import DataClient
    return DataClient(_api_client())


def _fmt(res) -> str:
    if res.status_code == 200:
        return json.dumps(res.json(), indent=2)
    return json.dumps({"error": f"Webull API {res.status_code}", "detail": res.text})


def _call_order_method(tc, names: list[str], account_id: str):
    for name in names:
        for obj in (tc.order_v2, tc):
            m = getattr(obj, name, None)
            if m:
                try:
                    return m(account_id=account_id)
                except TypeError:
                    return m(account_id)
    return None


_TIMEOUT_SECS = 20


def _run(fn):
    """Run fn() with a hard timeout; return JSON error string on timeout."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=_TIMEOUT_SECS)
        except concurrent.futures.TimeoutError:
            return json.dumps({"error": f"Webull API timed out after {_TIMEOUT_SECS}s"})


# ─── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
@_quiet
def get_account_balance() -> str:
    """
    Return the current account balance: net liquidation value, buying power,
    cash balance, and any unrealized P&L summary.
    """
    try:
        return _run(lambda: _fmt(_trade().account_v2.get_account_balance(ACCOUNT_ID)))
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@_quiet
def get_positions() -> str:
    """
    Return all current portfolio positions with symbol, quantity, average cost,
    current/last price, market value, and unrealized P&L for each holding.
    Use this to understand what the user owns right now.
    """
    try:
        return _run(lambda: _fmt(_trade().account_v2.get_account_position(ACCOUNT_ID)))
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@_quiet
def get_orders(order_type: str = "history") -> str:
    """
    Return orders from the account.

    Args:
        order_type: "history" for all past orders, "open" for currently open
                    orders, "today" for today's activity only.
    """
    try:
        tc = _trade()
        names = {
            "open":    ["list_open_orders",    "get_open_orders"],
            "today":   ["list_today_orders",   "get_today_orders"],
            "history": ["get_order_history",   "list_history_orders", "list_all_orders"],
        }.get(order_type, ["get_order_history"])

        def _call():
            r = _call_order_method(tc, names, ACCOUNT_ID)
            if r is not None:
                return _fmt(r)
            return json.dumps({"error": f"Order type '{order_type}' not supported by this SDK version"})
        return _run(_call)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@_quiet
def get_market_quote(symbol: str, category: str = "US_STOCK") -> str:
    """
    Return a real-time market snapshot for any ticker: last price, change,
    open, high, low, volume, and extended-hours data.

    Args:
        symbol:   Ticker symbol, e.g. "AAPL", "TSLA", "SPY", "BTC"
        category: "US_STOCK" (default), "US_OPTION", "US_FUTURES", "US_CRYPTO"
    """
    try:
        return _run(lambda: _fmt(_data().market_data.get_snapshot(
            symbol.upper(), category, extend_hour_required=True
        )))
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@_quiet
def get_price_history(
    symbol: str,
    timespan: str = "D1",
    category: str = "US_STOCK",
) -> str:
    """
    Return historical OHLCV price bars for a symbol. Useful for trend analysis,
    support/resistance levels, and charting patterns.

    Args:
        symbol:   Ticker symbol, e.g. "AAPL"
        timespan: Bar size — M1, M5, M15, M30, H1, D1 (daily), W1 (weekly)
        category: "US_STOCK" (default), "US_OPTION", "US_FUTURES", "US_CRYPTO"
    """
    try:
        from webull.data.common.timespan import Timespan
        valid = {t.name for t in Timespan}
        ts = timespan if timespan in valid else "D1"
        return _run(lambda: _fmt(_data().market_data.get_history_bar(symbol.upper(), category, ts)))
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@_quiet
def get_instrument_info(symbol: str, category: str = "US_STOCK") -> str:
    """
    Return instrument details: company name, sector, industry, exchange,
    and any other fundamental metadata Webull exposes for this symbol.

    Args:
        symbol:   Ticker symbol, e.g. "AAPL"
        category: "US_STOCK" (default), "US_OPTION", "US_FUTURES", "US_CRYPTO"
    """
    try:
        return _run(lambda: _fmt(_data().instrument.get_instrument(symbol.upper(), category)))
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@_quiet
def get_accounts() -> str:
    """
    List all Webull accounts linked to these API credentials.
    Use this if WEBULL_ACCOUNT_ID is not set and you need to find your account ID.
    """
    try:
        return _run(lambda: _fmt(_trade().account_v2.get_account_list()))
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
