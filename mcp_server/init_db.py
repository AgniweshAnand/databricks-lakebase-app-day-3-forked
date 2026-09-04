"""
Script to create the weather tables in Lakebase Postgres.
"""

import lakebase

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS weather_watchlist (
    id SERIAL PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    city_name VARCHAR(100) NOT NULL,
    country VARCHAR(100),
    latitude NUMERIC(8, 5),
    longitude NUMERIC(8, 5),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_user_city UNIQUE (user_email, city_name)
);

CREATE INDEX IF NOT EXISTS idx_weather_user ON weather_watchlist(user_email);
"""


def init_database():
    print("Initializing weather tables in Lakebase...")
    lakebase.run_write(SCHEMA_SQL)
    print("✓ Lakebase weather tables ready.")


if __name__ == "__main__":
    init_database()