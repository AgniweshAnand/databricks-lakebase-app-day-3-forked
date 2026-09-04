"""
Weather broker adapter using Open-Meteo API.

Handles geocoding lookups, weather forecasts, condition translation,
and activity recommendations without requiring an API key.
"""

import logging
from typing import Any
import requests

logger = logging.getLogger("weather-broker")

GEOCODING_BASE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# WMO Weather interpretation codes (WW)
WMO_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _geocode(location: str) -> dict[str, Any]:
    """Resolve a city or place name into geographic coordinates."""
    location = location.strip()
    if not location:
        raise ValueError("Location query cannot be empty.")

    params = {"name": location, "count": 1, "language": "en", "format": "json"}
    response = requests.get(GEOCODING_BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    results = data.get("results")
    if not results:
        raise ValueError(f"Could not resolve location '{location}'. Please check spelling.")

    match = results[0]
    return {
        "name": match.get("name"),
        "country": match.get("country", ""),
        "admin1": match.get("admin1", ""),
        "latitude": match.get("latitude"),
        "longitude": match.get("longitude"),
        "timezone": match.get("timezone", "UTC"),
    }


def get_current_weather(location: str) -> dict[str, Any]:
    """Fetch current real-time weather conditions for a given location."""
    geo = _geocode(location)
    params = {
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
            "wind_direction_10m",
        ],
        "timezone": geo["timezone"],
    }

    response = requests.get(FORECAST_BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    current = data.get("current", {})

    code = current.get("weather_code", 0)
    condition = WMO_CODE_MAP.get(code, "Unknown")

    return {
        "location": f"{geo['name']}, {geo['admin1']} ({geo['country']})".replace(",  ", " "),
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "timezone": geo["timezone"],
        "temperature_c": current.get("temperature_2m"),
        "temperature_f": round((current.get("temperature_2m", 0) * 9 / 5) + 32, 1),
        "feels_like_c": current.get("apparent_temperature"),
        "feels_like_f": round((current.get("apparent_temperature", 0) * 9 / 5) + 32, 1),
        "humidity_percent": current.get("relative_humidity_2m"),
        "precipitation_mm": current.get("precipitation"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "condition": condition,
        "as_of": current.get("time"),
    }


def get_forecast(location: str, days: int = 5) -> dict[str, Any]:
    """Fetch multi-day weather forecast."""
    days = max(1, min(days, 14))
    geo = _geocode(location)

    params = {
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "daily": [
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
            "precipitation_sum",
            "wind_speed_10m_max",
        ],
        "forecast_days": days,
        "timezone": geo["timezone"],
    }

    response = requests.get(FORECAST_BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    daily = response.json().get("daily", {})

    forecast_entries = []
    dates = daily.get("time", [])
    for idx, date_str in enumerate(dates):
        code = daily["weather_code"][idx]
        t_max_c = daily["temperature_2m_max"][idx]
        t_min_c = daily["temperature_2m_min"][idx]
        pop = daily["precipitation_probability_max"][idx]

        forecast_entries.append(
            {
                "date": date_str,
                "temp_max_c": t_max_c,
                "temp_max_f": round((t_max_c * 9 / 5) + 32, 1),
                "temp_min_c": t_min_c,
                "temp_min_f": round((t_min_c * 9 / 5) + 32, 1),
                "precipitation_probability": pop,
                "precipitation_sum_mm": daily["precipitation_sum"][idx],
                "max_wind_kmh": daily["wind_speed_10m_max"][idx],
                "condition": WMO_CODE_MAP.get(code, "Unknown"),
            }
        )

    return {
        "location": f"{geo['name']}, {geo['country']}",
        "forecast_days": days,
        "timezone": geo["timezone"],
        "forecast": forecast_entries,
    }


def get_activity_recommendation(
    location: str, date: str | None = None, activity: str = "general"
) -> dict[str, Any]:
    """Generate actionable advice based on rain probability, temperature, and wind."""
    forecast_data = get_forecast(location, days=7)
    forecast_list = forecast_data["forecast"]

    target_day = forecast_list[0]
    if date:
        matched = [d for d in forecast_list if d["date"] == date.strip()]
        if matched:
            target_day = matched[0]

    precip_prob = target_day["precipitation_probability"] or 0
    temp_max_c = target_day["temp_max_c"] or 20
    temp_min_c = target_day["temp_min_c"] or 10
    wind_speed = target_day["max_wind_kmh"] or 0

    umbrella_needed = precip_prob >= 40 or target_day["precipitation_sum_mm"] > 1.5

    if temp_max_c < 10:
        clothing = "Heavy coat, layers, and warm hat/gloves"
    elif temp_max_c < 18:
        clothing = "Light jacket or sweater"
    elif temp_max_c < 28:
        clothing = "T-shirt and comfortable pants"
    else:
        clothing = "Light summer clothing, sunscreen, and hydration"

    reasons = []
    if umbrella_needed:
        reasons.append(f"{precip_prob}% chance of precipitation")
    if wind_speed > 35:
        reasons.append(f"Strong winds up to {wind_speed} km/h")
    if temp_min_c <= 0:
        reasons.append(f"Freezing low temperatures ({temp_min_c}°C)")

    if precip_prob > 60 or wind_speed > 45:
        outdoor_rating = "Poor (Indoor activities recommended)"
    elif precip_prob > 30 or wind_speed > 30:
        outdoor_rating = "Fair (Monitor local radar)"
    else:
        outdoor_rating = "Excellent"

    return {
        "location": forecast_data["location"],
        "evaluated_date": target_day["date"],
        "condition": target_day["condition"],
        "umbrella_needed": umbrella_needed,
        "recommended_clothing": clothing,
        "outdoor_activity_rating": outdoor_rating,
        "advisories": reasons or ["Ideal conditions expected"],
        "summary": (
            f"Expect {target_day['condition']} with highs of {target_day['temp_max_c']}°C "
            f"and lows of {target_day['temp_min_c']}°C. Umbrella: {'YES' if umbrella_needed else 'NO'}."
        ),
    }


def compare_weather(locations: list[str]) -> list[dict[str, Any]]:
    """Compare current conditions across multiple locations side by side."""
    results = []
    for loc in locations:
        try:
            weather = get_current_weather(loc)
            results.append(
                {
                    "location": weather["location"],
                    "temperature_c": weather["temperature_c"],
                    "temperature_f": weather["temperature_f"],
                    "condition": weather["condition"],
                    "humidity": f"{weather['humidity_percent']}%",
                    "wind_speed": f"{weather['wind_speed_kmh']} km/h",
                    "status": "success",
                }
            )
        except Exception as e:
            results.append({"location": loc, "status": "error", "message": str(e)})
    return results