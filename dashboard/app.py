"""
Paper-trading dashboard: a small Flask app to WATCH what the Agent Bricks
agent is doing to the paper account via the thinkorswim MCP server
(tos_mcp_server.py). This app never places trades itself - it only reads
from Lakebase via paper_broker.py, so it can run side-by-side with the MCP
server and show, in near real time, the same account/positions/orders the
agent is manipulating.

Deploy this as its OWN Databricks App (separate from tos_mcp_server.py) -
one app serves MCP tool calls, the other serves the human-facing UI.

Run locally:
    python dashboard_app.py
"""

import os

from flask import Flask, jsonify, render_template, request

import paper_broker

app = Flask(__name__)

DEFAULT_ACCOUNT_ID = os.environ.get("PAPER_ACCOUNT_ID", "agent-bricks-demo")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.errorhandler(Exception)
def handle_exception(err):
    """Ensure all unhandled errors return JSON (not an HTML error page)."""
    status_code = getattr(err, "code", 500)
    if not isinstance(status_code, int):
        status_code = 500
    return jsonify({"error": str(err)}), status_code


@app.route("/")
def index():
    """Dashboard UI showing the paper account's live state."""
    return render_template("index.html", default_account_id=DEFAULT_ACCOUNT_ID)


@app.route("/api/account")
def api_account():
    """Full account summary: cash, positions marked-to-market, total equity."""
    account_id = request.args.get("account_id", DEFAULT_ACCOUNT_ID)
    return jsonify(paper_broker.get_account_summary(account_id))


@app.route("/api/orders")
def api_orders():
    """Recent order history for the account, most recent first."""
    account_id = request.args.get("account_id", DEFAULT_ACCOUNT_ID)
    limit = int(request.args.get("limit", 50))
    return jsonify(paper_broker.get_order_history(account_id, limit))


@app.route("/api/quote")
def api_quote():
    """Ad-hoc quote lookup, for manually checking a price in the UI."""
    symbol = request.args.get("symbol", "")
    if not symbol:
        return jsonify({"error": "symbol query param is required"}), 400
    return jsonify(paper_broker.get_quote(symbol))


if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_RUN_PORT", 8001))
    app.run(debug=True, host=host, port=port)
