"""
Legacy simulated paper-trading engine (superseded by alpaca_broker.py).

Kept for reference/fallback only - it is no longer imported by
alpaca_mcp_server.py or dashboard/app.py, which now use Alpaca Markets'
real, hosted paper-trading account instead.

All state (accounts, positions, orders, simulated market prices) lives in
Lakebase (Databricks-managed Postgres), via lakebase.py - same connection
pattern as Day 2. This module has NO knowledge of MCP or Flask.

There is no real brokerage connection here: prices are a seeded random
walk stored in `paper_market_prices`, and orders just move fake
cash/shares around in Lakebase.
"""

import os
import random
from datetime import datetime, timezone

import lakebase

ACCOUNTS_TABLE = os.environ.get("PAPER_ACCOUNTS_TABLE", "paper_accounts")
POSITIONS_TABLE = os.environ.get("PAPER_POSITIONS_TABLE", "paper_positions")
ORDERS_TABLE = os.environ.get("PAPER_ORDERS_TABLE", "paper_orders")
PRICES_TABLE = os.environ.get("PAPER_PRICES_TABLE", "paper_market_prices")

DEFAULT_STARTING_CASH = float(os.environ.get("PAPER_STARTING_CASH", "100000"))

# Deterministic per-symbol base price so a fresh symbol always starts
# somewhere sane instead of $0 - a simple hash-based seed, no external API.
_MIN_BASE_PRICE = 20.0
_MAX_BASE_PRICE = 450.0


def _seed_price(symbol: str) -> float:
    rng = random.Random(symbol.upper())
    return round(rng.uniform(_MIN_BASE_PRICE, _MAX_BASE_PRICE), 2)


def ensure_tables() -> None:
    """Create all paper-trading tables in Lakebase if they don't exist yet."""
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {ACCOUNTS_TABLE} (
            account_id TEXT PRIMARY KEY,
            cash_balance NUMERIC NOT NULL DEFAULT {DEFAULT_STARTING_CASH},
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {POSITIONS_TABLE} (
            account_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            quantity NUMERIC NOT NULL DEFAULT 0,
            avg_cost NUMERIC NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (account_id, symbol)
        )
        """
    )
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {ORDERS_TABLE} (
            id SERIAL PRIMARY KEY,
            account_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity NUMERIC NOT NULL,
            price NUMERIC NOT NULL,
            notional NUMERIC NOT NULL,
            status TEXT NOT NULL DEFAULT 'FILLED',
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {PRICES_TABLE} (
            symbol TEXT PRIMARY KEY,
            price NUMERIC NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def get_quote(symbol: str) -> dict:
    """
    Return a simulated quote for `symbol`. If the symbol has never been
    quoted before, seed it with a deterministic base price and nudge it
    with a small random walk on every call (a stand-in for a live
    live market-data feed - see the README for wiring in a real
    quote source instead).
    """
    ensure_tables()
    symbol = symbol.strip().upper()

    rows = lakebase.run_query(
        f"SELECT price FROM {PRICES_TABLE} WHERE symbol = %s", (symbol,)
    )
    if rows:
        last_price = float(rows[0]["price"])
    else:
        last_price = _seed_price(symbol)

    # Random-walk nudge (+/- ~1.5%) so repeated quotes drift like a real tape.
    rng = random.Random()
    drift = rng.uniform(-0.015, 0.015)
    new_price = round(max(0.01, last_price * (1 + drift)), 2)

    lakebase.run_write(
        f"""
        INSERT INTO {PRICES_TABLE} (symbol, price, updated_at)
        VALUES (%s, %s, now())
        ON CONFLICT (symbol) DO UPDATE
            SET price = EXCLUDED.price,
                updated_at = EXCLUDED.updated_at
        """,
        (symbol, new_price),
    )

    return {
        "symbol": symbol,
        "price": new_price,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def get_or_create_account(account_id: str) -> dict:
    """Fetch an account, creating it with the default starting cash if new."""
    ensure_tables()
    lakebase.run_write(
        f"""
        INSERT INTO {ACCOUNTS_TABLE} (account_id, cash_balance)
        VALUES (%s, {DEFAULT_STARTING_CASH})
        ON CONFLICT (account_id) DO NOTHING
        """,
        (account_id,),
    )
    rows = lakebase.run_query(
        f"SELECT account_id, cash_balance, created_at, updated_at "
        f"FROM {ACCOUNTS_TABLE} WHERE account_id = %s",
        (account_id,),
    )
    return rows[0]


def place_order(account_id: str, symbol: str, side: str, quantity: float) -> dict:
    """
    Place a fake market order: BUY debits cash and adds/increases the
    position (weighted-average cost); SELL credits cash and reduces the
    position. Rejects BUYs that would overdraw cash and SELLs larger than
    the current position - this is a paper account, but it should still
    behave like a real one so students see realistic guardrails.
    """
    ensure_tables()
    symbol = symbol.strip().upper()
    side = side.strip().upper()
    quantity = float(quantity)

    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be 'BUY' or 'SELL', got {side!r}")
    if quantity <= 0:
        raise ValueError(f"quantity must be positive, got {quantity!r}")

    account = get_or_create_account(account_id)
    quote = get_quote(symbol)
    price = quote["price"]
    notional = round(price * quantity, 2)

    position_rows = lakebase.run_query(
        f"SELECT quantity, avg_cost FROM {POSITIONS_TABLE} "
        f"WHERE account_id = %s AND symbol = %s",
        (account_id, symbol),
    )
    current_qty = float(position_rows[0]["quantity"]) if position_rows else 0.0
    current_avg_cost = float(position_rows[0]["avg_cost"]) if position_rows else 0.0
    cash_balance = float(account["cash_balance"])

    if side == "BUY":
        if notional > cash_balance:
            raise ValueError(
                f"Insufficient paper cash: order costs ${notional:,.2f}, "
                f"account {account_id} has ${cash_balance:,.2f}"
            )
        new_qty = current_qty + quantity
        new_avg_cost = (
            ((current_qty * current_avg_cost) + notional) / new_qty if new_qty else 0.0
        )
        new_cash = cash_balance - notional
    else:  # SELL
        if quantity > current_qty:
            raise ValueError(
                f"Cannot sell {quantity} shares of {symbol}: account {account_id} "
                f"only holds {current_qty}"
            )
        new_qty = current_qty - quantity
        new_avg_cost = current_avg_cost if new_qty > 0 else 0.0
        new_cash = cash_balance + notional

    lakebase.run_write(
        f"""
        INSERT INTO {POSITIONS_TABLE} (account_id, symbol, quantity, avg_cost, updated_at)
        VALUES (%s, %s, %s, %s, now())
        ON CONFLICT (account_id, symbol) DO UPDATE
            SET quantity = EXCLUDED.quantity,
                avg_cost = EXCLUDED.avg_cost,
                updated_at = EXCLUDED.updated_at
        """,
        (account_id, symbol, new_qty, new_avg_cost),
    )
    lakebase.run_write(
        f"UPDATE {ACCOUNTS_TABLE} SET cash_balance = %s, updated_at = now() "
        f"WHERE account_id = %s",
        (new_cash, account_id),
    )
    order_rows = lakebase.run_query(
        f"""
        INSERT INTO {ORDERS_TABLE} (account_id, symbol, side, quantity, price, notional, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'FILLED')
        RETURNING id, account_id, symbol, side, quantity, price, notional, status, created_at
        """,
        (account_id, symbol, side, quantity, price, notional),
    )
    return order_rows[0]


def get_positions(account_id: str) -> list[dict]:
    ensure_tables()
    return lakebase.run_query(
        f"SELECT symbol, quantity, avg_cost, updated_at FROM {POSITIONS_TABLE} "
        f"WHERE account_id = %s AND quantity > 0 ORDER BY symbol ASC",
        (account_id,),
    )


def get_account_summary(account_id: str) -> dict:
    """Cash + mark-to-market value of every open position + total equity."""
    account = get_or_create_account(account_id)
    positions = get_positions(account_id)

    positions_out = []
    market_value = 0.0
    for pos in positions:
        quote = get_quote(pos["symbol"])
        qty = float(pos["quantity"])
        value = round(quote["price"] * qty, 2)
        market_value += value
        positions_out.append(
            {
                "symbol": pos["symbol"],
                "quantity": qty,
                "avg_cost": float(pos["avg_cost"]),
                "last_price": quote["price"],
                "market_value": value,
                "unrealized_pl": round((quote["price"] - float(pos["avg_cost"])) * qty, 2),
            }
        )

    cash_balance = float(account["cash_balance"])
    return {
        "account_id": account_id,
        "cash_balance": cash_balance,
        "positions": positions_out,
        "market_value": round(market_value, 2),
        "total_equity": round(cash_balance + market_value, 2),
    }


def get_order_history(account_id: str, limit: int = 50) -> list[dict]:
    ensure_tables()
    return lakebase.run_query(
        f"SELECT id, symbol, side, quantity, price, notional, status, created_at "
        f"FROM {ORDERS_TABLE} WHERE account_id = %s ORDER BY created_at DESC LIMIT %s",
        (account_id, limit),
    )
