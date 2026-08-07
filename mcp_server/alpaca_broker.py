"""
Alpaca Markets paper-trading engine backing the Alpaca paper-trading MCP
server.

Unlike paper_broker.py (which simulated everything in Lakebase), this
module is a thin wrapper around Alpaca's real, hosted paper-trading
account via alpaca-py (https://alpaca.markets/sdks/python/). Quotes, fills,
positions, cash, and order history are all real Alpaca paper-trading data
- there is no local simulation or Lakebase bookkeeping involved.

Alpaca's paper trading is one account per API key pair (not multi-tenant),
so `account_id` is accepted on every function below purely to keep the
same signatures alpaca_mcp_server.py already calls - it is not used to select
between multiple accounts. Every call operates against the single Alpaca
paper account configured via the ALPACA_* secrets below.

Swap-in note: this module implements the trading functions
(get_quote, place_order, get_positions, get_account_summary, 
get_order_history, get_balance) that mirror paper_broker.py, 
so alpaca_mcp_server.py only needs to import this module instead.
"""

import base64
import os

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest
from databricks.sdk import WorkspaceClient

_w = WorkspaceClient()

_SECRET_SCOPE = os.environ.get("ALPACA_SECRET_SCOPE", "database")
_KEY_ID_SECRET_KEY = os.environ.get("ALPACA_KEY_ID_SECRET_KEY", "alpaca-key-id")
_SECRET_KEY_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY_SECRET_KEY", "alpaca-secret-key")

_trading_client: TradingClient | None = None
_data_client: StockHistoricalDataClient | None = None


def _secret(key: str) -> str:
    """Fetch and base64-decode a value from the Databricks secret scope."""
    secret = _w.secrets.get_secret(scope=_SECRET_SCOPE, key=key)
    return base64.b64decode(secret.value).decode("utf-8")


def _get_trading_client() -> TradingClient:
    global _trading_client
    if _trading_client is None:
        _trading_client = TradingClient(
            _secret(_KEY_ID_SECRET_KEY),
            _secret(_SECRET_KEY_SECRET_KEY),
            paper=True,
        )
    return _trading_client


def _get_data_client() -> StockHistoricalDataClient:
    global _data_client
    if _data_client is None:
        _data_client = StockHistoricalDataClient(
            _secret(_KEY_ID_SECRET_KEY),
            _secret(_SECRET_KEY_SECRET_KEY),
        )
    return _data_client


def get_quote(symbol: str) -> dict:
    """
    Get the latest real quote for a stock ticker symbol from Alpaca's
    market data API. Returns the bid/ask midpoint as `price`.
    """
    symbol = symbol.strip().upper()
    quotes = _get_data_client().get_stock_latest_quote(
        StockLatestQuoteRequest(symbol_or_symbols=symbol)
    )
    quote = quotes[symbol]
    price = round((float(quote.bid_price) + float(quote.ask_price)) / 2, 2)
    return {
        "symbol": symbol,
        "price": price,
        "as_of": quote.timestamp.isoformat(),
    }


def place_order(account_id: str, symbol: str, side: str, quantity: float) -> dict:
    """
    Place a real market order against the single configured Alpaca paper
    trading account. `account_id` is accepted for signature compatibility
    with the mock engine but is not used to select an account - Alpaca
    paper trading is one account per API key pair.
    """
    symbol = symbol.strip().upper()
    side = side.strip().upper()
    quantity = float(quantity)

    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be 'BUY' or 'SELL', got {side!r}")
    if quantity <= 0:
        raise ValueError(f"quantity must be positive, got {quantity!r}")

    # Crypto orders require GTC (Good-Til-Canceled) or IOC (Immediate-Or-Cancel)
    # Stock orders can use DAY
    # Crypto symbols typically end with USD (e.g., BTCUSD, ETHUSD)
    is_crypto = symbol.endswith('USD') and len(symbol) > 3
    time_in_force = TimeInForce.GTC if is_crypto else TimeInForce.DAY

    order_data = MarketOrderRequest(
        symbol=symbol,
        qty=quantity,
        side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
        time_in_force=time_in_force,
    )
    order = _get_trading_client().submit_order(order_data=order_data)
    return _order_to_dict(order)


def get_positions(account_id: str) -> list[dict]:
    """Get all open positions in the Alpaca paper trading account."""
    positions = _get_trading_client().get_all_positions()
    return [
        {
            "symbol": pos.symbol,
            "quantity": float(pos.qty),
            "avg_cost": float(pos.avg_entry_price),
            "updated_at": None,
        }
        for pos in positions
    ]


def get_account_summary(account_id: str) -> dict:
    """Cash + mark-to-market value of every open position + total equity."""
    account = _get_trading_client().get_account()
    positions = _get_trading_client().get_all_positions()

    positions_out = []
    market_value = 0.0
    for pos in positions:
        qty = float(pos.qty)
        last_price = float(pos.current_price)
        value = round(last_price * qty, 2)
        market_value += value
        positions_out.append(
            {
                "symbol": pos.symbol,
                "quantity": qty,
                "avg_cost": float(pos.avg_entry_price),
                "last_price": last_price,
                "market_value": value,
                "unrealized_pl": round(float(pos.unrealized_pl), 2),
            }
        )

    cash_balance = float(account.cash)
    return {
        "account_id": account_id,
        "cash_balance": cash_balance,
        "positions": positions_out,
        "market_value": round(market_value, 2),
        "total_equity": round(float(account.equity), 2),
    }


def get_order_history(account_id: str, limit: int = 50) -> list[dict]:
    """Get recent orders for the Alpaca paper trading account, most recent first."""
    request_params = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit)
    orders = _get_trading_client().get_orders(filter=request_params)
    return [_order_to_dict(order) for order in orders]


def _order_to_dict(order) -> dict:
    """Convert an alpaca-py Order object into the dict shape alpaca_mcp_server expects."""
    quantity = float(order.qty) if order.qty is not None else None
    price = float(order.filled_avg_price) if order.filled_avg_price is not None else None
    notional = round(price * quantity, 2) if price is not None and quantity is not None else None
    return {
        "id": str(order.id),
        "symbol": order.symbol,
        "side": order.side.value if order.side else None,
        "quantity": quantity,
        "price": price,
        "notional": notional,
        "status": order.status.value if order.status else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }
