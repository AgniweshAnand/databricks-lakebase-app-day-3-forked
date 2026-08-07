"""
One-time script to create the secret scope and store the Lakebase
connection URL, following the same pattern as Day 2's setup_secrets.py.

Run once from a Databricks notebook in your workspace:
    %sh python setup_secrets.py
"""

import base64
import getpass

from databricks.sdk import WorkspaceClient

SCOPE = "database"
KEY = "lakebase-url"


def main():
    w = WorkspaceClient()

    existing_scopes = {s.name for s in w.secrets.list_scopes()}
    if SCOPE not in existing_scopes:
        w.secrets.create_scope(scope=SCOPE)
        print(f"Created secret scope: {SCOPE}")

    lakebase_url = getpass.getpass(
        "Paste your Lakebase connection URL "
        "(postgresql://role:password@host:5432/databricks_postgres?sslmode=require): "
    ).strip()
    if not lakebase_url:
        raise SystemExit("No Lakebase URL provided - aborting.")

    encoded = base64.b64encode(lakebase_url.encode("utf-8")).decode("utf-8")
    w.secrets.put_secret(scope=SCOPE, key=KEY, string_value=encoded)
    print(f"Stored secret: {SCOPE}/{KEY}")


if __name__ == "__main__":
    main()
