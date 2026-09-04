"""
Weather Prediction & Forecast FastMCP Server.

Exposes tools over the Model Context Protocol (MCP) for Databricks Agent Bricks:
    - get_current_weather(location)
    - get_forecast(location, days)
    - get_activity_recommendation(location, date, activity)
    - compare_weather(locations)
    - get_saved_locations()
    - save_favorite_location(location)
"""

import os
import logging
from contextvars import ContextVar
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

import weather_broker
import lakebase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-mcp-server")

_request_context: ContextVar[dict] = ContextVar("request_context", default={})


def _get_end_user_email() -> str:
    """Retrieve end-user email from Databricks App gateway headers or fallback."""
    headers = _request_context.get()
    forwarded_user = headers.get("x-forwarded-user") or headers.get("x-forwarded-email")
    if forwarded_user:
        return forwarded_user
    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        return w.current_user.me().user_name or "user@databricks.com"
    except Exception:
        return "local_dev_user@example.com"


mcp = FastMCP("weather-prediction-service")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        headers = {
            "x-forwarded-user": request.headers.get("x-forwarded-user"),
            "x-forwarded-email": request.headers.get("x-forwarded-email"),
        }
        _request_context.set(headers)
        return await call_next(request)


@mcp.tool
def get_current_weather(location: str) -> dict:
    """
    Get live real-time weather conditions for a specific city or place name.

    Args:
        location: City or location name, e.g. "Chicago", "Tokyo", "London".

    Returns:
        Dict containing temperature, feels-like, humidity, wind, and sky conditions.
    """
    try:
        return weather_broker.get_current_weather(location)
    except Exception as e:
        logger.exception("Failed to get current weather")
        return {"status": "error", "message": str(e)}


@mcp.tool
def get_forecast(location: str, days: int = 5) -> dict:
    """
    Get multi-day weather forecast (up to 14 days) including high/low temps,
    precipitation probability, and conditions.

    Args:
        location: City or location name, e.g. "San Francisco".
        days: Number of forecast days (1 to 14, default 5).

    Returns:
        Dict containing day-by-day weather forecast entries.
    """
    try:
        return weather_broker.get_forecast(location, days=days)
    except Exception as e:
        logger.exception("Failed to get forecast")
        return {"status": "error", "message": str(e)}


@mcp.tool
def get_activity_recommendation(
    location: str, date: str | None = None, activity: str = "general"
) -> dict:
    """
    Get derived weather judgments, including clothing advice, umbrella necessity,
    and outdoor suitability ratings.

    Args:
        location: City or place name.
        date: Target date in 'YYYY-MM-DD' format (defaults to current day).
        activity: Context like 'running', 'travel', or 'general'.

    Returns:
        Dict with umbrella recommendation, clothing guidance, and comfort rating.
    """
    try:
        return weather_broker.get_activity_recommendation(location, date, activity)
    except Exception as e:
        logger.exception("Failed to get recommendation")
        return {"status": "error", "message": str(e)}


@mcp.tool
def compare_weather(locations: list[str]) -> list[dict]:
    """
    Compare current weather across 2 or more locations side-by-side.

    Args:
        locations: List of city names, e.g. ["New York", "London", "Tokyo"].

    Returns:
        List of dicts showing comparative temperature, conditions, and wind.
    """
    try:
        return weather_broker.compare_weather(locations)
    except Exception as e:
        logger.exception("Failed to compare weather")
        return [{"status": "error", "message": str(e)}]


@mcp.tool
def save_favorite_location(location: str) -> dict:
    """
    Save a city to the user's favorite locations list in Lakebase.

    Args:
        location: City name to save.

    Returns:
        Dict with confirmation status.
    """
    try:
        email = _get_end_user_email()
        geo = weather_broker._geocode(location)
        sql = """
        INSERT INTO weather_watchlist (user_email, city_name, country, latitude, longitude)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_email, city_name) DO NOTHING;
        """
        lakebase.run_write(
            sql, (email, geo["name"], geo["country"], geo["latitude"], geo["longitude"])
        )
        return {
            "status": "success",
            "message": f"Saved {geo['name']} to favorites for {email}",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool
def get_saved_locations() -> dict:
    """
    Retrieve all saved favorite locations for the active user.

    Returns:
        Dict containing user's list of saved locations.
    """
    try:
        email = _get_end_user_email()
        sql = "SELECT city_name, country, latitude, longitude, created_at FROM weather_watchlist WHERE user_email = %s"
        rows = lakebase.run_query(sql, (email,))
        return {"status": "success", "user_email": email, "saved_locations": rows}
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    if hasattr(mcp, "app") and mcp.app is not None:
        mcp.app.add_middleware(RequestContextMiddleware)

    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", 8000)))
    mcp.run(transport="http", host="0.0.0.0", port=port)