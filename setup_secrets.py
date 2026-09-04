"""
Setup script to configure required secret scope and credentials in Databricks.
"""

import os
import getpass
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import ResourceAlreadyExists

SCOPE_NAME = "database"


def setup_secrets():
    w = WorkspaceClient()

    # 1. Create secret scope if it doesn't already exist
    try:
        w.secrets.create_scope(scope=SCOPE_NAME)
        print(f"✓ Secret scope '{SCOPE_NAME}' created.")
    except ResourceAlreadyExists:
        print(f"✓ Secret scope '{SCOPE_NAME}' already exists.")
    except Exception as e:
        print(f"Scope creation note: {e}")

    # 2. Collect credentials
    lakebase_url = os.getenv("LAKEBASE_URL")
    if not lakebase_url:
        lakebase_url = getpass.getpass("Enter Lakebase Database URL (press Enter to skip if already set): ").strip()

    tmdb_token = os.getenv("TMDB_TOKEN")
    if not tmdb_token:
        tmdb_token = getpass.getpass("Enter TMDB API Read Access Token (v4): ").strip()

    # 3. Store Lakebase URL
    if lakebase_url:
        w.secrets.put_secret(
            scope=SCOPE_NAME,
            key="lakebase-url",
            string_value=lakebase_url
        )
        print("✓ Secret 'lakebase-url' stored successfully.")

    # 4. Store TMDB Read Access Token
    if tmdb_token:
        w.secrets.put_secret(
            scope=SCOPE_NAME,
            key="tmdb-token",
            string_value=tmdb_token
        )
        print("✓ Secret 'tmdb-token' stored successfully.")

    print("\nAll required secrets are configured in Databricks!")


if __name__ == "__main__":
    setup_secrets()