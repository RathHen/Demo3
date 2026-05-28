import os
import secrets
from flask import Flask, render_template, jsonify, request, Response
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

APP_KEY = os.getenv("WEBULL_APP_KEY", "")
APP_SECRET = os.getenv("WEBULL_APP_SECRET", "")
REGION_ID = os.getenv("WEBULL_REGION_ID", "us")
API_ENDPOINT = os.getenv("WEBULL_API_ENDPOINT", "")
DEFAULT_ACCOUNT_ID = os.getenv("WEBULL_ACCOUNT_ID", "")

# Dashboard login. When DASHBOARD_PASSWORD is set, every request must supply
# matching HTTP Basic credentials. Leave it unset only for trusted local use.
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")


@app.before_request
def _require_login():
    if not DASHBOARD_PASSWORD:
        return None
    auth = request.authorization
    if not auth or not (
        secrets.compare_digest(auth.username or "", DASHBOARD_USER)
        and secrets.compare_digest(auth.password or "", DASHBOARD_PASSWORD)
    ):
        return Response(
            "Authentication required.", 401,
            {"WWW-Authenticate": 'Basic realm="Webull Dashboard"'},
        )
    return None


def _api_client():
    from webull.core.client import ApiClient
    client = ApiClient(APP_KEY, APP_SECRET, REGION_ID)
    if API_ENDPOINT:
        client.add_endpoint(REGION_ID, API_ENDPOINT)
    return client


def _trade_client():
    from webull.trade.trade_client import TradeClient
    return TradeClient(_api_client())


def _data_client():
    from webull.data.data_client import DataClient
    return DataClient(_api_client())


def _respond(res):
    """Wrap a Webull API response into a Flask JSON response."""
    if res.status_code == 200:
        try:
            return jsonify({"success": True, "data": res.json()})
        except Exception:
            return jsonify({"success": True, "data": res.text})
    return jsonify({"success": False, "error": f"Webull API error {res.status_code}", "details": res.text}), res.status_code


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config")
def get_config():
    return jsonify({
        "has_credentials": bool(APP_KEY and APP_SECRET),
        "region_id": REGION_ID,
        "default_account_id": DEFAULT_ACCOUNT_ID,
    })


@app.route("/api/accounts")
def get_accounts():
    try:
        tc = _trade_client()
        return _respond(tc.account_v2.get_account_list())
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/account/<account_id>/balance")
def get_balance(account_id):
    try:
        tc = _trade_client()
        return _respond(tc.account_v2.get_account_balance(account_id))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/account/<account_id>/profile")
def get_profile(account_id):
    try:
        tc = _trade_client()
        # get_account_profile may not exist in all SDK versions
        if hasattr(tc.account_v2, "get_account_profile"):
            return _respond(tc.account_v2.get_account_profile(account_id))
        return _respond(tc.account_v2.get_account_balance(account_id))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/account/<account_id>/positions")
def get_positions(account_id):
    try:
        tc = _trade_client()
        return _respond(tc.account_v2.get_account_position(account_id))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/account/<account_id>/orders")
def get_orders(account_id):
    order_type = request.args.get("type", "history")
    try:
        tc = _trade_client()
        res = None

        if order_type == "open":
            for method_name in ("list_open_orders", "get_open_orders"):
                for obj in (tc.order_v2, tc):
                    m = getattr(obj, method_name, None)
                    if m:
                        res = m(account_id)
                        break
                if res:
                    break
        elif order_type == "today":
            for method_name in ("list_today_orders", "get_today_orders"):
                for obj in (tc.order_v2, tc):
                    m = getattr(obj, method_name, None)
                    if m:
                        res = m(account_id)
                        break
                if res:
                    break
        else:
            # history / default
            for method_name in ("get_order_history", "list_history_orders", "list_all_orders"):
                for obj in (tc.order_v2, tc):
                    m = getattr(obj, method_name, None)
                    if m:
                        try:
                            res = m(account_id=account_id)
                        except TypeError:
                            res = m(account_id)
                        break
                if res:
                    break

        if res is not None:
            return _respond(res)
        return jsonify({"success": False, "error": f"Order type '{order_type}' is not available in this SDK version"}), 501
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/market/quote/<symbol>")
def get_quote(symbol):
    try:
        from webull.data.common.category import Category
        dc = _data_client()
        category = request.args.get("category", Category.US_STOCK.name)
        res = dc.market_data.get_snapshot(symbol.upper(), category, extend_hour_required=True)
        return _respond(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/market/history/<symbol>")
def get_history(symbol):
    try:
        from webull.data.common.category import Category
        from webull.data.common.timespan import Timespan
        dc = _data_client()
        category = request.args.get("category", Category.US_STOCK.name)
        timespan_name = request.args.get("timespan", "D1")
        # Validate timespan against available enum values
        valid_timespans = {t.name for t in Timespan}
        if timespan_name not in valid_timespans:
            timespan_name = "D1"
        res = dc.market_data.get_history_bar(symbol.upper(), category, timespan_name)
        return _respond(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/market/instrument/<symbol>")
def get_instrument(symbol):
    try:
        from webull.data.common.category import Category
        dc = _data_client()
        category = request.args.get("category", Category.US_STOCK.name)
        res = dc.instrument.get_instrument(symbol.upper(), category)
        return _respond(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    if not DASHBOARD_PASSWORD:
        print("\n  WARNING: DASHBOARD_PASSWORD is not set — the dashboard has NO login.")
        print("  Do NOT expose it through a tunnel until you set one in .env.\n")
    app.run(debug=debug, host="0.0.0.0", port=port)
