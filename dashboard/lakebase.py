"""
Lakebase PostgreSQL connection manager using Databricks Secrets.
Provides pooled execution for SELECT and INSERT/UPDATE/DELETE queries.
"""

import os
import base64
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from databricks.sdk import WorkspaceClient

logger = logging.getLogger("lakebase")


def get_db_url() -> str:
    """Retrieve the PostgreSQL connection string from Databricks Secrets or env."""
    # 1. Direct environment variable fallback
    if os.getenv("LAKEBASE_URL"):
        return os.getenv("LAKEBASE_URL")

    # 2. Databricks Secrets Scope
    try:
        scope = os.getenv("LAKEBASE_SECRET_SCOPE", "database")
        key = os.getenv("LAKEBASE_SECRET_KEY", "lakebase-url")
        w = WorkspaceClient()
        secret_resp = w.secrets.get_secret(scope=scope, key=key)
        if secret_resp.value:
            return base64.b64decode(secret_resp.value).decode("utf-8")
    except Exception as e:
        logger.warning(f"Could not load Lakebase URL from Databricks secrets: {e}")

    raise ValueError("Lakebase database URL is not configured.")


def get_connection():
    """Create and return a raw psycopg2 database connection."""
    db_url = get_db_url()
    return psycopg2.connect(db_url)


def run_query(query: str, params=None):
    """Execute a read query and return rows as dictionaries."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def run_write(query: str, params=None):
    """Execute an INSERT, UPDATE, or DDL statement and commit changes."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
        conn.commit()
    finally:
        conn.close()