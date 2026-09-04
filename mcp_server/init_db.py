"""
Initializes the AI Movie Night Planner tables in Lakebase PostgreSQL.
"""

import logging
from lakebase import run_write, run_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init-db")

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) UNIQUE NOT NULL,
        display_name VARCHAR(100) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS groups (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        created_by VARCHAR(255) REFERENCES users(email) ON DELETE SET NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS group_members (
        id SERIAL PRIMARY KEY,
        group_id INT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
        user_email VARCHAR(255) NOT NULL,
        joined_at TIMESTAMPTZ DEFAULT NOW(),
        CONSTRAINT unique_group_user UNIQUE (group_id, user_email)
    );
    """,
    """
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
    """,
    """
    CREATE TABLE IF NOT EXISTS ratings (
        id SERIAL PRIMARY KEY,
        user_email VARCHAR(255) NOT NULL,
        tmdb_id INT NOT NULL REFERENCES movies(tmdb_id) ON DELETE CASCADE,
        score INT NOT NULL CHECK (score >= 1 AND score <= 10),
        review TEXT,
        rated_at TIMESTAMPTZ DEFAULT NOW(),
        CONSTRAINT unique_user_rating UNIQUE (user_email, tmdb_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist_items (
        id SERIAL PRIMARY KEY,
        group_id INT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
        tmdb_id INT NOT NULL REFERENCES movies(tmdb_id) ON DELETE CASCADE,
        added_by VARCHAR(255) NOT NULL,
        status VARCHAR(20) DEFAULT 'queued',
        added_at TIMESTAMPTZ DEFAULT NOW(),
        CONSTRAINT unique_group_movie UNIQUE (group_id, tmdb_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS recommendations (
        id SERIAL PRIMARY KEY,
        group_id INT REFERENCES groups(id) ON DELETE CASCADE,
        prompt_query TEXT NOT NULL,
        recommended_tmdb_ids INT[],
        agent_reasoning TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id);",
    "CREATE INDEX IF NOT EXISTS idx_ratings_user ON ratings(user_email);",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_status ON watchlist_items(group_id, status);",
    "CREATE INDEX IF NOT EXISTS idx_movies_tmdb_id ON movies(tmdb_id);"
]


def init_database():
    logger.info("Initializing Movie Night Planner database schema...")
    for ddl in DDL_STATEMENTS:
        run_write(ddl)
    logger.info("✓ All 7 tables and indexes created successfully in Lakebase.")


if __name__ == "__main__":
    init_database()
