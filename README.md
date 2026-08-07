# Day 3: Agent Bricks + an Alpaca Markets Paper-Trading MCP Server

Builds on [Day 2](../databricks-lakebase-app-day-2/README.md)'s Lakebase pattern. Day 3 adds:

- An **Alpaca Markets paper-trading MCP server** (`mcp_server/`) - exposes paper-trading tools
  (`get_quote`, `place_trade`, `get_positions`, `get_account_summary`, `get_order_history`)
  over the Model Context Protocol, backed by a real Alpaca paper-trading account.
- A **Databricks Agent Bricks agent** that connects to that MCP server as an external tool,
  reads market data from your Lakebase Day 2 watchlist/news tables, and decides to place
  paper trades against your real (but fake-money) Alpaca account.
- A small **dashboard app** (`dashboard/`) to watch those trades land in near real time.

> **Why Alpaca?** Alpaca Markets provides a free, real, hosted paper-trading environment with a
> clean Python SDK ([alpaca-py](https://alpaca.markets/sdks/python/)) and no lengthy manual app
> approval process, so students get real market data and real (simulated-money) order fills
> without any risk of real money moving. See "Setting up Alpaca Markets" below to create your
> paper account and API keys.

## Architecture

```
Agent Bricks agent  --(MCP tool calls)-->  mcp_server/alpaca_mcp_server.py  --(REST)-->  Alpaca Markets (paper)
        ^                                                                                     
        | (reads context: watchlist, ticker_news_* from Day 2 Lakebase)                        
        +-----------------------------------------------------------------------------------+
                                                                                              |
                                        dashboard/app.py  <--(reads same Alpaca account)------+
```

- `mcp_server/` and `dashboard/` are **two separate Databricks Apps** - one serves MCP tool
  calls to the agent, the other serves a human-facing dashboard. Both read/write the exact same
  Alpaca paper-trading account (via their own copy of `alpaca_broker.py`), so trades placed by
  the agent through MCP show up in the dashboard immediately, and vice versa.
- `mcp_server/alpaca_broker.py` is the broker adapter: it wraps `alpaca-py`'s `TradingClient`
  (orders, positions, account info) and `StockHistoricalDataClient` (quotes) to implement the
  5 functions the MCP tools call. There's no local simulation - quotes, fills, cash, and
  positions all come straight from Alpaca's paper-trading API.
- `mcp_server/alpaca_mcp_server.py` wraps `alpaca_broker.py` with [FastMCP](https://gofastmcp.com/)
  `@mcp.tool` decorators and serves them over streamable HTTP - the transport Databricks'
  MCP client/gateway expects when you [host your own MCP server as a Databricks App](https://docs.databricks.com/aws/en/agents/mcp-tools/custom-mcp).
- Alpaca's paper trading is **one account per API key pair**, not multi-tenant - `account_id` is
  accepted by every tool for signature compatibility but doesn't select between accounts; every
  call operates against the single Alpaca paper account configured via secrets (see below).

## Files

- `mcp_server/alpaca_mcp_server.py` - FastMCP server exposing the 5 paper-trading tools
- `mcp_server/alpaca_broker.py` - Broker adapter wrapping Alpaca's `alpaca-py` SDK
- `mcp_server/paper_broker.py` / `mcp_server/lakebase.py` - legacy Lakebase-simulated engine,
  kept for reference/fallback only (no longer imported)
- `mcp_server/app.yaml` / `mcp_server/requirements.txt` - Databricks App config for the MCP server
- `dashboard/app.py` - Flask dashboard (read-only view of the Alpaca paper account)
- `dashboard/templates/index.html` - Dashboard UI (cash, positions, P/L, recent orders)
- `dashboard/alpaca_broker.py` - copy of the same broker adapter (each Databricks App deploys
  from its own folder, so each needs its own copy of shared code)
- `dashboard/paper_broker.py` / `dashboard/lakebase.py` - legacy Lakebase-simulated engine,
  kept for reference/fallback only (no longer imported)
- `dashboard/app.yaml` / `dashboard/requirements.txt` - Databricks App config for the dashboard
- `setup_secrets.py` - One-time script to store the Lakebase URL secret (same as Day 2; still
  used if you keep Day 2's watchlist/news tables for agent context)
- `.env.example` - Local dev env var template

## Setting up Alpaca Markets

Both apps need an Alpaca **paper-trading** API key ID and secret key, stored as Databricks
secrets (never committed to the repo).

### 1. Create a free Alpaca account

Sign up at [alpaca.markets](https://alpaca.markets/) (no funding or brokerage approval needed
for paper trading - it's instant, unlike a real brokerage app).

### 2. Generate paper-trading API keys

1. Log in to the [Alpaca dashboard](https://app.alpaca.markets/).
2. Make sure you're viewing **Paper Trading** (there's a live/paper toggle in the dashboard) -
   never use live-trading keys for this lab.
3. Under **API Keys**, generate a new key pair. Copy the **Key ID** and **Secret Key**
   immediately - the secret is only shown once.

### 3. Store the keys as Databricks secrets

From a Databricks notebook or the CLI, base64-encode and store both values (same pattern as
the Lakebase URL secret):

```bash
databricks secrets put-secret database alpaca-key-id --string-value "$(echo -n YOUR_KEY_ID | base64)"
databricks secrets put-secret database alpaca-secret-key --string-value "$(echo -n YOUR_SECRET_KEY | base64)"
```

If you use a different secret scope than `database`, update `ALPACA_SECRET_SCOPE` in both
`mcp_server/app.yaml` and `dashboard/app.yaml` to match.

### 4. (Local dev only) set the keys as environment variables

For running the apps locally without Databricks secrets, `alpaca_broker.py` still reads through
`WorkspaceClient().secrets.get_secret()`, so local runs need a Databricks CLI profile configured
with access to the secret scope above (`databricks auth login`), or you can temporarily hardcode
test keys - just never commit them.

## Step-by-step setup

### 1. Reuse (or create) your Lakebase instance from Day 2

Lakebase is still used for agent context (Day 2's `watchlist`/`ticker_news_*` tables) even
though trading now goes through Alpaca. If you already have a Lakebase instance from Day 2,
reuse it. Otherwise, follow
[Day 2's step 2](../databricks-lakebase-app-day-2/README.md#2-create-a-lakebase-instance-and-a-native-password-role)
to create one.

### 2. Store secrets

- Lakebase URL: from a Databricks notebook (`%sh python setup_secrets.py`), same as Day 2.
- Alpaca API keys: see "Setting up Alpaca Markets" above.

### 3. Configure environment variables (local dev)

```bash
cp .env.example .env
# paste your Lakebase URL into LAKEBASE_URL
```

### 4. Install dependencies and run both apps locally

```bash
cd mcp_server && pip install -r requirements.txt && python alpaca_mcp_server.py   # serves MCP on :8000
```

In a second terminal:

```bash
cd dashboard && pip install -r requirements.txt && python app.py                    # serves UI on :8001
```

Open `http://localhost:8001` to see your Alpaca paper account (starting cash, no positions
yet). Use an [MCP Inspector](https://docs.databricks.com/aws/en/agents/mcp-tools/connect-clients)
or `curl` against `http://localhost:8000` to sanity-check the tools before deploying.

### 5. Deploy both apps to Databricks Apps

Following [Day 2's step 7](../databricks-lakebase-app-day-2/README.md#7-create-a-git-folder-in-databricks-and-deploy-the-app-no-cli-required)
(Git folder + Apps UI, no CLI needed), but this time deploy **two** apps pointed at two
different subfolders of the same Git folder:

1. Create a Git folder for this repo (once) as in Day 2.
2. **Deploy the MCP server app**: Compute > Apps > Create app > Custom, name it e.g.
   `alpaca-paper-mcp`, and point its source at the Git folder's `databricks-lakebase-app-day-3/mcp_server/`
   subfolder (so it picks up `mcp_server/app.yaml`). Deploy it, then copy its app URL - you'll
   register that URL as an external MCP server in step 6.
3. **Deploy the dashboard app**: repeat, naming it e.g. `paper-trading-dashboard`, pointing at
   `databricks-lakebase-app-day-3/dashboard/`. Deploy it and open its URL to confirm the
   dashboard loads and shows your Alpaca account.

### 6. Register the MCP server as an external MCP in your workspace

Follow [Connect agents to external MCPs and tools](https://docs.databricks.com/aws/en/agents/mcp-tools/connect-external):

1. In your workspace, go to **AI Gateway** > **MCPs** > **Add MCP** (or **Register external MCP**).
2. Paste the `alpaca-paper-mcp` app's URL from step 5 as the server endpoint (streamable HTTP).
3. Give it a name (e.g. `alpaca-paper-trading`) and save. Databricks will introspect the
   server and list the 5 tools (`get_quote`, `place_trade`, `get_positions`,
   `get_account_summary`, `get_order_history`).
4. Grant your Agent Bricks agent (created next) access to this MCP server via Unity Catalog
   permissions, if prompted.

### 7. Build the Agent Bricks agent

1. In your workspace sidebar, go to **Agents** > **Agent Bricks** > **Create agent**.
2. Choose the **Custom LLM** (or **Multi-agent supervisor**, if you want to combine this with a
   research agent) agent type - either works for a single tool-calling agent like this.
3. Under **Tools**, add:
   - The `alpaca-paper-trading` MCP server you registered in step 6 (all 5 tools, or a
     curated subset - e.g. leave out `place_trade` for a "research-only" version of the agent
     first, then add it back once you trust the guardrails).
   - Optionally, a **Unity Catalog function tool** or **Genie space** wired to your Day 2
     `watchlist` / `ticker_news_documents` / `ticker_news_embeddings` tables, so the agent has
     real context (tracked tickers + recent news/sentiment) to reason about before trading.
4. Give the agent a system prompt along the lines of:

   > You are a paper-trading research assistant. Use `get_account_summary` to check current
   > cash/positions before proposing a trade. Use the watchlist/news tools to justify any BUY or
   > SELL. Always call `get_quote` immediately before `place_trade` to confirm price. Only trade
   > symbols already on the watchlist. Never exceed 10% of account equity in a single order.
   > Explain your reasoning before calling `place_trade`.

5. **Evaluate and iterate**: Agent Bricks auto-evaluates the agent against sample prompts (e.g.
   "Check AAPL and buy 10 shares if sentiment is positive") - use this to tune the system prompt
   and tool selection before enabling it for live chat.
6. Deploy the agent and chat with it, e.g.: *"Look at my watchlist, check recent news sentiment,
   and place a small paper trade if you find a good opportunity."* Watch the trade land on the
   dashboard from step 5, and in your Alpaca paper-trading dashboard too.

## Notes

- `mcp_server/` and `dashboard/` intentionally duplicate `alpaca_broker.py` rather than sharing
  a package, because each Databricks App deploys independently from its own folder with its own
  `app.yaml`/`requirements.txt` - there's no shared Python package install step across
  Databricks Apps. If you prefer a single shared package, publish `alpaca_broker.py` to a
  private PyPI index or wheel and add it to both `requirements.txt` files instead of
  duplicating.
- `place_trade` submits real orders against your real Alpaca **paper** account - fills use real
  market prices, but no real money moves. Never point `alpaca_broker.py` at live-trading keys
  for this lab.
- The legacy `paper_broker.py` + `lakebase.py` Lakebase-simulated engine is still present in
  both folders for reference, in case you want to compare a fully local simulation against
  Alpaca's real paper-trading fills, or fall back to it if you don't want to create an Alpaca
  account.
