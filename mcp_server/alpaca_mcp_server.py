"""
Alpaca Markets paper-trading MCP server.

Exposes paper-trading tools over MCP (Model Context Protocol) so a
Databricks Agent Bricks agent can call them like any other tool:
    - get_quote(symbol)
    - place_trade(account_id, symbol, side, quantity)
    - get_positions(account_id)
    - get_account_summary(account_id)
    - get_order_history(account_id, limit)

These tools are backed by Alpaca Markets' real, hosted paper-trading
account (see alpaca_broker.py), so students can safely wire an Agent
Bricks agent to place real (but fake-money) trades without a real
brokerage account or risk of real money moving. account_id is accepted
for signature compatibility but is not used to select an account - Alpaca
paper trading is one account per API key pair.

Swap-in-a-real-broker note: to point this at a different broker instead,
keep the same 5 tool signatures below and replace the alpaca_broker.*
calls inside each tool with calls to that broker's SDK/API - the MCP
surface for the agent does not need to change. The original Lakebase-
simulated engine is preserved in paper_broker.py for reference.

Deploy this as its own Databricks App (same app.yaml + FastMCP entrypoint
pattern documented at
https://docs.databricks.com/aws/en/agents/mcp-tools/custom-mcp), separate
from the dashboard app, so an Agent Bricks agent (or any MCP client) can
register its URL as an external MCP server.

Run locally:
    python alpaca_mcp_server.py
"""

import os

from fastmcp import FastMCP

import alpaca_broker

mcp = FastMCP("alpaca-paper-trading")


@mcp.tool
def get_quote(symbol: str) -> dict:
    """
    Get the latest real quote for a stock ticker symbol from Alpaca.

    Args:
        symbol: Stock ticker symbol, e.g. "AAPL".

    Returns:
        A dict with symbol, price, and as_of (ISO timestamp).
    """
    return alpaca_broker.get_quote(symbol)


@mcp.tool
def place_trade(account_id: str, symbol: str, side: str, quantity: float) -> dict:
    """
    Place a real market order (paper trade) - BUY or SELL - against the
    configured Alpaca paper trading account.

    Args:
        account_id: Accepted for signature compatibility; not used to
            select an account (Alpaca paper trading is one account per
            API key pair).
        symbol: Stock ticker symbol, e.g. "AAPL".
        side: "BUY" or "SELL".
        quantity: Number of shares to trade (must be positive).

    Returns:
        A dict describing the order (id, symbol, side, quantity,
        price, notional, status, created_at).
    """
    return alpaca_broker.place_order(account_id, symbol, side, quantity)


@mcp.tool
def get_positions(account_id: str) -> list[dict]:
    """
    Get all open positions for the Alpaca paper trading account.

    Args:
        account_id: Accepted for signature compatibility; not used to
            select an account.

    Returns:
        A list of dicts, each with symbol, quantity, avg_cost, updated_at.
    """
    return alpaca_broker.get_positions(account_id)


@mcp.tool
def get_account_summary(account_id: str) -> dict:
    """
    Get a full account summary for the Alpaca paper trading account: cash
    balance, open positions marked-to-market, total market value, and
    total equity (cash + market value).

    Args:
        account_id: Accepted for signature compatibility; not used to
            select an account.

    Returns:
        A dict with account_id, cash_balance, positions, market_value,
        total_equity.
    """
    return alpaca_broker.get_account_summary(account_id)


@mcp.tool
def get_order_history(account_id: str, limit: int = 50) -> list[dict]:
    """
    Get recent orders for the Alpaca paper trading account, most recent first.

    Args:
        account_id: Accepted for signature compatibility; not used to
            select an account.
        limit: Max number of orders to return (default 50).

    Returns:
        A list of dicts, each with id, symbol, side, quantity, price,
        notional, status, created_at.
    """
    return alpaca_broker.get_order_history(account_id, limit)


if __name__ == "__main__":
    # Databricks Apps route external HTTP traffic to this port via app.yaml;
    # streamable-http is the transport Databricks' MCP client/gateway expects
    # (see the "Host your own MCP" doc linked in the module docstring above).
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", 8000)))
    mcp.run(transport="http", host="0.0.0.0", port=port)
