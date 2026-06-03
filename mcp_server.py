import concurrent.futures
import contextlib
import functools
import json
import os
import sys

# ── Protect the MCP stdio channel from stray output ───────────────────────────
# The MCP stdio transport speaks JSON-RPC over stdout. Any other byte on stdout
# corrupts the protocol ("non-whitespace after JSON" / "EOF while parsing").
# Python-level redirect_stdout is not enough: grpcio (used by the Webull SDK) is
# C code that writes straight to file descriptor 1, bypassing sys.stdout.
#
# Fix: keep a private duplicate of the real stdout and bind Python's sys.stdout
# to it (this is the only thing MCP writes JSON-RPC to). Then repoint OS fd 1 at
# stderr, so any C-level write (grpcio, native logging) lands on stderr and can
# no longer corrupt the protocol. Tool bodies further redirect Python-level
# stdout to stderr via the _quiet decorator while SDK calls run.
import io

_real_stdout_fd = os.dup(1)                         # private handle to real stdout
os.dup2(2, 1)                                       # fd 1 -> stderr (C-level safety)
# Rebuild a normal stdout (TextIOWrapper over a BufferedWriter) on the saved fd,
# so code that touches sys.stdout.buffer (the MCP transport does) behaves as usual.
sys.stdout = io.TextIOWrapper(
    io.BufferedWriter(io.FileIO(_real_stdout_fd, "w")),
    encoding="utf-8",
    line_buffering=True,
)                                                   # MCP writes JSON-RPC here

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

# Pin the token cache to one absolute folder so this server and init_token.py
# always read/write the SAME token.txt, regardless of the process working
# directory (Claude Desktop may launch us from System32 where chdir can fail).
_TOKEN_DIR = os.path.join(_runtime_dir, "conf")
try:
    os.makedirs(_TOKEN_DIR, exist_ok=True)
except OSError:
    pass
os.environ["WEBULL_OPENAPI_TOKEN_DIR"] = _TOKEN_DIR

import logging

# Pre-configure the root logger with a stderr handler BEFORE any SDK import.
# The Webull SDK checks "if logging is already configured" and skips adding
# its own stdout handler when it finds one. Background threads that fire after
# our contextlib.redirect_stdout block exits will then log to stderr, not stdout.
logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stderr,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

from dotenv import load_dotenv
load_dotenv(os.path.join(_here, ".env"))

import credentials
from mcp.server.fastmcp import FastMCP

APP_KEY      = credentials.get("WEBULL_APP_KEY")
APP_SECRET   = credentials.get("WEBULL_APP_SECRET")
REGION_ID    = credentials.get("WEBULL_REGION_ID", "us")
API_ENDPOINT = credentials.get("WEBULL_API_ENDPOINT")
ACCOUNT_ID   = credentials.get("WEBULL_ACCOUNT_ID")

SCHWAB_APP_KEY    = credentials.get("SCHWAB_APP_KEY")
SCHWAB_APP_SECRET = credentials.get("SCHWAB_APP_SECRET")
_schwab_token_file = os.path.join(_runtime_dir, "schwab_token.json")

mcp = FastMCP("Webull")

# ── Build SDK clients once at startup ─────────────────────────────────────────
with contextlib.redirect_stdout(sys.stderr):
    from webull.core.client import ApiClient as _ApiClient
    from webull.trade.trade_client import TradeClient as _TradeClient
    from webull.data.data_client import DataClient as _DataClient

    _api = _ApiClient(
        APP_KEY, APP_SECRET, REGION_ID,
        token_check_duration_seconds=1,
        token_check_interval_seconds=1,
    )
    try:
        _api.set_token_dir(_TOKEN_DIR)
    except Exception:
        pass

    # Read the cached token and inject it directly — bypasses SDK file-reading.
    _token_file = os.path.join(_TOKEN_DIR, "token.txt")
    try:
        with open(_token_file) as _f:
            _token_value = _f.read().strip().splitlines()[0].strip()
        if _token_value:
            _api.set_token(_token_value)
    except Exception:
        pass

    if API_ENDPOINT:
        _api.add_endpoint(REGION_ID, API_ENDPOINT)

    _trade_client = _TradeClient(_api)
    _data_client  = _DataClient(_api)

    # ── Schwab client (real-time options with full greeks) ────────────────────
    _schwab_client = None
    if SCHWAB_APP_KEY and SCHWAB_APP_SECRET and os.path.exists(_schwab_token_file):
        try:
            import schwab as _schwab_lib
            _schwab_client = _schwab_lib.auth.client_from_token_file(
                _schwab_token_file, SCHWAB_APP_KEY, SCHWAB_APP_SECRET
            )
        except Exception as _se:
            print(f"Schwab client init skipped: {_se}", file=sys.stderr)

    # After SDK init, redirect any stdout-bound logging handlers to stderr.
    # Catches cases where the SDK ignored basicConfig and added its own handler.
    for _lname, _lobj in list(logging.Logger.manager.loggerDict.items()):
        if not isinstance(_lobj, logging.Logger):
            continue
        for _h in list(_lobj.handlers):
            if isinstance(_h, logging.StreamHandler):
                if getattr(_h, "stream", None) in (sys.stdout, sys.__stdout__):
                    # Some handlers (e.g. logging._StderrHandler) expose `stream`
                    # as a read-only property — setting it raises AttributeError.
                    # Skip those; they already point at stderr anyway.
                    try:
                        _h.stream = sys.stderr
                    except AttributeError:
                        pass


def _quiet(fn):
    """Redirect stdout to stderr while the tool runs — keeps MCP's JSON-RPC clean."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with contextlib.redirect_stdout(sys.stderr):
            return fn(*args, **kwargs)
    return wrapper


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
        return _run(lambda: _fmt(_trade_client.account_v2.get_account_balance(ACCOUNT_ID)))
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
        return _run(lambda: _fmt(_trade_client.account_v2.get_account_position(ACCOUNT_ID)))
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
        tc = _trade_client
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
        return _run(lambda: _fmt(_data_client.market_data.get_snapshot(
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
        return _run(lambda: _fmt(_data_client.market_data.get_history_bar(symbol.upper(), category, ts)))
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
        return _run(lambda: _fmt(_data_client.instrument.get_instrument(symbol.upper(), category)))
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
        return _run(lambda: _fmt(_trade_client.account_v2.get_account_list()))
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Options (Schwab, real-time with full greeks) ─────────────────────────────
# Uses the Schwab Trader API for real-time option chains including delta, gamma,
# theta, vega, rho, and implied volatility. Run init_schwab_token.bat once to
# authorize. Token auto-refreshes; re-run only if it fully expires (~7 days).


def _schwab_unavailable() -> str:
    if not SCHWAB_APP_KEY or not SCHWAB_APP_SECRET:
        return json.dumps({
            "error": "Schwab credentials not configured",
            "fix": "Run store_credentials.bat and enter your SCHWAB_APP_KEY and SCHWAB_APP_SECRET",
        })
    if not os.path.exists(_schwab_token_file):
        return json.dumps({
            "error": "Schwab not authorized",
            "fix": "Run init_schwab_token.bat to complete the one-time OAuth login",
        })
    return json.dumps({
        "error": "Schwab client unavailable",
        "fix": "Restart Claude Desktop; if the problem persists, re-run init_schwab_token.bat",
    })


def _schwab_contract(c: dict, strike: float) -> dict:
    return {
        "strike":            strike,
        "bid":               c.get("bid"),
        "ask":               c.get("ask"),
        "last":              c.get("last"),
        "volume":            c.get("totalVolume"),
        "openInterest":      c.get("openInterest"),
        "impliedVolatility": round((c.get("volatility") or 0) / 100, 4),
        "delta":             c.get("delta"),
        "gamma":             c.get("gamma"),
        "theta":             c.get("theta"),
        "vega":              c.get("vega"),
        "rho":               c.get("rho"),
        "daysToExpiration":  c.get("daysToExpiration"),
        "inTheMoney":        c.get("inTheMoney"),
    }


def _extract_contracts(exp_date_map: dict, target_exp: str) -> list:
    out = []
    for key, strikes_data in exp_date_map.items():
        if key.split(":")[0] != target_exp:
            continue
        for strike_str, contracts_list in strikes_data.items():
            for c in contracts_list:
                out.append(_schwab_contract(c, float(strike_str)))
    return sorted(out, key=lambda x: x["strike"])


@mcp.tool()
@_quiet
def get_option_expirations(symbol: str) -> str:
    """
    List the available option expiration dates for a stock (Schwab, real-time).
    Use this first to pick an expiration for get_option_chain.

    Args:
        symbol: Underlying ticker, e.g. "AAPL", "SPY"
    """
    if _schwab_client is None:
        return _schwab_unavailable()

    def _call():
        import schwab as _sc
        r = _schwab_client.get_option_chain(
            symbol.upper(),
            contract_type=_sc.client.Client.Options.ContractType.CALL,
            strike_count=1,
            include_underlying_quote=False,
        )
        if r.status_code != 200:
            return json.dumps({"error": f"Schwab API {r.status_code}", "detail": r.text})
        data = r.json()
        dates = sorted({k.split(":")[0] for k in data.get("callExpDateMap", {})})
        if not dates:
            return json.dumps({"error": f"No options found for {symbol.upper()}"})
        return json.dumps({"symbol": symbol.upper(), "expirations": dates}, indent=2)

    try:
        return _run(_call)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@_quiet
def get_option_chain(
    symbol: str,
    expiration: str = "",
    option_type: str = "both",
    strike_count: int = 10,
) -> str:
    """
    Return a real-time option chain from Schwab with full greeks (delta, gamma,
    theta, vega, rho), bid/ask/last, volume, open interest, and implied
    volatility. Ideal for building spreads and multi-leg strategies.

    impliedVolatility is expressed as a decimal (0.25 = 25% IV).

    Args:
        symbol:       Underlying ticker, e.g. "AAPL"
        expiration:   Expiry date "YYYY-MM-DD". If empty, uses the nearest one.
        option_type:  "calls", "puts", or "both" (default)
        strike_count: Strikes to include on each side of the current price
                      (default 10). Use 0 for the full chain.
    """
    if _schwab_client is None:
        return _schwab_unavailable()

    def _call():
        import schwab as _sc
        import datetime

        ct_map = {
            "calls": _sc.client.Client.Options.ContractType.CALL,
            "puts":  _sc.client.Client.Options.ContractType.PUT,
            "both":  _sc.client.Client.Options.ContractType.ALL,
        }
        ct = ct_map.get(option_type, _sc.client.Client.Options.ContractType.ALL)

        # Resolve expiration: if none given, fetch available dates and pick the first.
        exp = expiration
        if not exp:
            r0 = _schwab_client.get_option_chain(
                symbol.upper(),
                contract_type=_sc.client.Client.Options.ContractType.CALL,
                strike_count=1,
                include_underlying_quote=False,
            )
            if r0.status_code != 200:
                return json.dumps({"error": f"Schwab API {r0.status_code}"})
            dates = sorted({k.split(":")[0] for k in r0.json().get("callExpDateMap", {})})
            exp = dates[0] if dates else None

        if not exp:
            return json.dumps({"error": f"No options found for {symbol.upper()}"})

        kwargs = dict(
            contract_type=ct,
            from_date=datetime.date.fromisoformat(exp),
            to_date=datetime.date.fromisoformat(exp),
            include_underlying_quote=True,
            strategy=_sc.client.Client.Options.Strategy.SINGLE,
        )
        if strike_count:
            kwargs["strike_count"] = strike_count

        r = _schwab_client.get_option_chain(symbol.upper(), **kwargs)
        if r.status_code != 200:
            return json.dumps({"error": f"Schwab API {r.status_code}", "detail": r.text})
        data = r.json()

        underlying = data.get("underlying") or {}
        spot = underlying.get("last") or underlying.get("close")

        out = {
            "symbol": symbol.upper(),
            "expiration": exp,
            "underlying_price": spot,
            "source": "Schwab (real-time)",
        }
        if option_type in ("calls", "both"):
            out["calls"] = _extract_contracts(data.get("callExpDateMap", {}), exp)
        if option_type in ("puts", "both"):
            out["puts"] = _extract_contracts(data.get("putExpDateMap", {}), exp)
        return json.dumps(out, indent=2, default=str)

    try:
        return _run(_call)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@_quiet
def get_option_quote(
    symbol: str,
    expiration: str,
    strike: float,
    option_type: str = "call",
) -> str:
    """
    Return the real-time quote for a single specific option contract from Schwab,
    including full greeks (delta, gamma, theta, vega, rho).

    impliedVolatility is expressed as a decimal (0.25 = 25% IV).

    Args:
        symbol:      Underlying ticker, e.g. "AAPL"
        expiration:  Expiry date "YYYY-MM-DD"
        strike:      Strike price, e.g. 190.0
        option_type: "call" or "put"
    """
    if _schwab_client is None:
        return _schwab_unavailable()

    def _call():
        import schwab as _sc
        import datetime

        ct = (
            _sc.client.Client.Options.ContractType.CALL
            if option_type.lower().startswith("c")
            else _sc.client.Client.Options.ContractType.PUT
        )
        exp_date = datetime.date.fromisoformat(expiration)
        r = _schwab_client.get_option_chain(
            symbol.upper(),
            contract_type=ct,
            strike=float(strike),
            from_date=exp_date,
            to_date=exp_date,
            include_underlying_quote=True,
            strategy=_sc.client.Client.Options.Strategy.SINGLE,
        )
        if r.status_code != 200:
            return json.dumps({"error": f"Schwab API {r.status_code}", "detail": r.text})
        data = r.json()

        map_key = "callExpDateMap" if option_type.lower().startswith("c") else "putExpDateMap"
        exp_map = data.get(map_key, {})
        underlying = data.get("underlying") or {}
        spot = underlying.get("last") or underlying.get("close")

        for key, strikes_data in exp_map.items():
            if key.split(":")[0] != expiration:
                continue
            for strike_str, contracts_list in strikes_data.items():
                if abs(float(strike_str) - float(strike)) < 0.01:
                    rec = _schwab_contract(contracts_list[0], float(strike_str))
                    rec["symbol"]           = contracts_list[0].get("symbol")
                    rec["expiration"]       = expiration
                    rec["option_type"]      = option_type
                    rec["underlying_price"] = spot
                    rec["source"]           = "Schwab (real-time)"
                    return json.dumps(rec, indent=2, default=str)

        # Strike not found — return the available strikes so the caller can retry.
        all_strikes = sorted(
            float(s)
            for key, strikes_data in exp_map.items()
            if key.split(":")[0] == expiration
            for s in strikes_data
        )
        return json.dumps({
            "error": f"No {option_type} at strike {strike} for {expiration}",
            "available_strikes": all_strikes,
        })

    try:
        return _run(_call)
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
