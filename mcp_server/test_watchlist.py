#!/usr/bin/env python
"""
Test script for watchlist functionality.

This script demonstrates how to use the watchlist MCP tools.
Run this locally or in a notebook to test the integration.
"""

import sys
import os

# Add the mcp_server directory to the path
sys.path.insert(0, os.path.dirname(__file__))

import massive_broker
import lakebase


def test_get_quote():
    """Test fetching a quote from Massive.com."""
    print("\n=== Testing get_quote ===")
    try:
        quote = massive_broker.get_quote("AAPL")
        print(f"✓ Quote retrieved successfully:")
        print(f"  Symbol: {quote['symbol']}")
        print(f"  Price: ${quote['price']}")
        print(f"  Volume: {quote.get('volume', 'N/A')}")
        print(f"  Change: {quote.get('change', 'N/A')}")
        print(f"  Change %: {quote.get('change_percent', 'N/A')}%")
        print(f"  As of: {quote['as_of']}")
        return True
    except Exception as e:
        print(f"✗ Failed to get quote: {e}")
        return False


def test_add_to_watchlist():
    """Test adding a stock to the watchlist."""
    print("\n=== Testing add_to_watchlist ===")
    try:
        # Get the logged-in user's email
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        user_email = w.current_user.me().user_name
        
        # Get quote
        quote = massive_broker.get_quote("AAPL")
        
        # Insert into watchlist
        sql = """
        INSERT INTO watchlist (email, symbol, price, volume, change, change_percent, timestamp, added_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (email, symbol) 
        DO UPDATE SET 
            price = EXCLUDED.price,
            volume = EXCLUDED.volume,
            change = EXCLUDED.change,
            change_percent = EXCLUDED.change_percent,
            timestamp = EXCLUDED.timestamp,
            updated_at = NOW()
        """
        
        lakebase.run_write(
            sql,
            (
                user_email,
                quote["symbol"],
                quote["price"],
                quote.get("volume"),
                quote.get("change"),
                quote.get("change_percent"),
                quote["as_of"],
            ),
        )
        
        print(f"✓ Added {quote['symbol']} to watchlist for {user_email}")
        return True
    except Exception as e:
        print(f"✗ Failed to add to watchlist: {e}")
        return False


def test_get_watchlist():
    """Test retrieving the watchlist."""
    print("\n=== Testing get_watchlist ===")
    try:
        sql = """
        SELECT 
            symbol,
            price,
            volume,
            change,
            change_percent,
            timestamp,
            added_at,
            updated_at
        FROM watchlist
        WHERE email = %s
        ORDER BY added_at DESC
        LIMIT 10
        """
        
        rows = lakebase.run_query(sql, ("test_user",))
        
        print(f"✓ Retrieved {len(rows)} watchlist entries:")
        for row in rows:
            print(f"  - {row['symbol']}: ${row['price']} ({row.get('change_percent', 'N/A')}%)")
        return True
    except Exception as e:
        print(f"✗ Failed to get watchlist: {e}")
        return False


def test_remove_from_watchlist():
    """Test removing a stock from the watchlist."""
    print("\n=== Testing remove_from_watchlist ===")
    try:
        sql = """
        DELETE FROM watchlist
        WHERE email = %s AND symbol = %s
        """
        
        rows_affected = lakebase.run_write(sql, ("test_user", "AAPL"))
        
        if rows_affected > 0:
            print(f"✓ Removed AAPL from watchlist")
            return True
        else:
            print(f"⚠ AAPL was not in the watchlist")
            return False
    except Exception as e:
        print(f"✗ Failed to remove from watchlist: {e}")
        return False


def main():
    """Run all tests."""
    print("="*60)
    print("Watchlist Functionality Test Suite")
    print("="*60)
    
    results = [
        test_get_quote(),
        test_add_to_watchlist(),
        test_get_watchlist(),
        test_remove_from_watchlist(),
    ]
    
    print("\n" + "="*60)
    print(f"Test Results: {sum(results)}/{len(results)} passed")
    print("="*60)
    
    return all(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
