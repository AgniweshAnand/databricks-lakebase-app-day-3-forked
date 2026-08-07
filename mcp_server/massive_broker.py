"""
Massive.com API integration for stock quotes.

This module provides a thin wrapper around Massive.com's aggregates API
to retrieve previous day's stock market data. It replaces Alpaca's data API
for quote fetching while maintaining the same interface.

API endpoint: GET /v2/aggs/ticker/{stocksTicker}/prev
Returns previous day's aggregate (open, high, low, close, volume) for a stock.
"""

import base64
import os
import requests
from databricks.sdk import WorkspaceClient

_w = WorkspaceClient()

_SECRET_SCOPE = os.environ.get("MASSIVE_SECRET_SCOPE", "massive")
_API_KEY_SECRET_KEY = os.environ.get("MASSIVE_SECRET_KEY", "api-key")

_api_key: str | None = None


def _secret(key: str) -> str:
    """Fetch and base64-decode a value from the Databricks secret scope."""
    secret = _w.secrets.get_secret(scope=_SECRET_SCOPE, key=key)
    return base64.b64decode(secret.value).decode("utf-8")


def _get_api_key() -> str:
    global _api_key
    if _api_key is None:
        _api_key = _secret(_API_KEY_SECRET_KEY)
    return _api_key


def get_quote(symbol: str) -> dict:
    """
    Get previous day's aggregate data for a stock ticker symbol from Massive.com.
    
    Args:
        symbol: Stock ticker symbol, e.g. "AAPL".
    
    Returns:
        A dict with symbol, price (close), as_of (ISO timestamp), volume, change,
        change_percent, open, high, and low.
    """
    symbol = symbol.strip().upper()
    
    # Massive.com API endpoint for previous day aggregates
    url = f"https://api.massive.com/v2/aggs/ticker/{symbol}/prev"
    
    headers = {
        "Authorization": f"Bearer {_get_api_key()}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # The response typically contains a 'results' array with aggregate data
        # Example structure: {"ticker": "AAPL", "results": [{"c": close, "h": high, "l": low, "o": open, "v": volume, "t": timestamp}]}
        if "results" in data and len(data["results"]) > 0:
            result = data["results"][0]
            close_price = float(result.get("c", 0))  # Close price
            open_price = float(result.get("o", 0))   # Open price
            volume = int(result.get("v", 0))         # Volume
            timestamp = result.get("t", 0)           # Unix timestamp in milliseconds
            
            # Calculate change and change percent
            change = close_price - open_price
            change_percent = (change / open_price * 100) if open_price > 0 else 0
            
            # Convert timestamp to ISO format
            from datetime import datetime
            as_of = datetime.fromtimestamp(timestamp / 1000).isoformat() if timestamp else ""
            
            return {
                "symbol": data.get("ticker", symbol),
                "price": close_price,
                "as_of": as_of,
                "volume": volume,
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
                "open": open_price,
                "high": float(result.get("h", 0)),
                "low": float(result.get("l", 0)),
            }
        else:
            raise RuntimeError(f"No results returned for {symbol}")
            
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to fetch quote for {symbol} from Massive.com: {e}")
