-- Schema for AI Movie Night Planner (Lakebase Postgres)

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Groups Table
CREATE TABLE IF NOT EXISTS groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    created_by VARCHAR(255) REFERENCES users(email) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Group Members (Junction Table)
CREATE TABLE IF NOT EXISTS group_members (
    id SERIAL PRIMARY KEY,
    group_id INT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_email VARCHAR(255) NOT NULL,
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_group_user UNIQUE (group_id, user_email)
);

-- 4. Cached Movies Table
CREATE TABLE IF NOT EXISTS movies (
    id SERIAL PRIMARY KEY,
    tmdb_id INT UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    overview TEXT,
    genres TEXT[],
    runtime INT,
    vote_average NUMERIC(3, 1),
    poster_path VARCHAR(255),
    release_date VARCHAR(20),
    keywords TEXT[],
    streaming_providers TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Ratings Table (Tracks watched movies and member scores 1-10)
CREATE TABLE IF NOT EXISTS ratings (
    id SERIAL PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    tmdb_id INT NOT NULL REFERENCES movies(tmdb_id) ON DELETE CASCADE,
    score INT NOT NULL CHECK (score >= 1 AND score <= 10),
    review TEXT,
    rated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_user_rating UNIQUE (user_email, tmdb_id)
);

-- 6. Watchlist Items Table (Queue for group movie nights)
CREATE TABLE IF NOT EXISTS watchlist_items (
    id SERIAL PRIMARY KEY,
    group_id INT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    tmdb_id INT NOT NULL REFERENCES movies(tmdb_id) ON DELETE CASCADE,
    added_by VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'queued', -- 'queued', 'watched', 'skipped'
    added_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_group_movie UNIQUE (group_id, tmdb_id)
);

-- 7. Recommendations Log Table
CREATE TABLE IF NOT EXISTS recommendations (
    id SERIAL PRIMARY KEY,
    group_id INT REFERENCES groups(id) ON DELETE CASCADE,
    prompt_query TEXT NOT NULL,
    recommended_tmdb_ids INT[],
    agent_reasoning TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fast Index Lookups
CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_ratings_user ON ratings(user_email);
CREATE INDEX IF NOT EXISTS idx_watchlist_status ON watchlist_items(group_id, status);
CREATE INDEX IF NOT EXISTS idx_movies_tmdb_id ON movies(tmdb_id);