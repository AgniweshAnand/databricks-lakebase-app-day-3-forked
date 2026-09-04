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