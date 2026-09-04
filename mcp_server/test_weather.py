#!/usr/bin/env python
"""
Unit test suite for the weather broker adapter.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import weather_broker


def test_current_weather():
    print("\n=== Testing get_current_weather ===")
    res = weather_broker.get_current_weather("Chicago")
    assert "temperature_c" in res, "Missing temperature_c in response"
    print(f"✓ Current weather for {res['location']}: {res['temperature_c']}°C, {res['condition']}")


def test_forecast():
    print("\n=== Testing get_forecast ===")
    res = weather_broker.get_forecast("Austin", days=3)
    assert len(res["forecast"]) == 3, "Expected 3 forecast days"
    print(f"✓ 3-day forecast retrieved for {res['location']}")


def test_activity_recommendation():
    print("\n=== Testing get_activity_recommendation ===")
    res = weather_broker.get_activity_recommendation("Tokyo")
    assert "umbrella_needed" in res, "Missing umbrella_needed recommendation"
    print(f"✓ Advisory for {res['location']}: Umbrella={res['umbrella_needed']}, Rating={res['outdoor_activity_rating']}")


def test_compare():
    print("\n=== Testing compare_weather ===")
    res = weather_broker.compare_weather(["London", "Tokyo", "Sydney"])
    assert len(res) == 3, "Expected 3 city comparison results"
    print("✓ Multi-city comparison successful")


if __name__ == "__main__":
    test_current_weather()
    test_forecast()
    test_activity_recommendation()
    test_compare()
    print("\nAll Weather MCP tests passed successfully!")