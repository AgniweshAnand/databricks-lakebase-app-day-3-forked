# Day 3: Agent Bricks + a mock "thinkorswim" MCP Server (Fake Trades on Lakebase)

Builds on [Day 2](../databricks-lakebase-app-day-2/README.md)'s Lakebase pattern. Day 3 adds:

- A **mock "thinkorswim" MCP server** (`mcp_server/`) - exposes paper-trading tools
  (`get_quote`, `place_trade`, `get_positions`, `get_account_summary`, `get_order_history`)
  over the Model Context Protocol, backed by Lakebase.
- A **Databricks Agent Bricks agent** that connects to that MCP server as an external tool,
  reads market data from your Lakebase Day 2 watchlist/news tables, and decides to place
  simulated ("paper") trades.
- A small **dashboard app** (`dashboard/`) to watch the fake trades land in near real time.

> **Why "mock"?** As of this writing there is no official public thinkorswim/Schwab MCP server
> you can just plug in. This lab builds one with the exact shape a real one would have
> (quote / trade / positions / order history), backed by a safe, Lakebase-persisted paper
> trading engine - so students can wire an Agent Bricks agent to "trade" with zero risk of real
> money moving, and zero dependency on a real brokerage account or market-data key. See
> "Swapping in a real broker" below for pointing this at a real paper/live trading API later
> without changing the agent side at all.

## Architecture

```
Agent Bricks agent  --(MCP tool calls)-->  mcp_server/tos_mcp_server.py  --(SQL)-->  Lakebase
        ^                                                                              ^
        | (reads context: watchlist, ticker_news_* from Day 2)                         |
        +------------------------------------------------------------------------------+
                                                                                         |
                                        dashboard/app.py  <--(reads same tables)---------+
```

- `mcp_server/` and `dashboard/` are **two separate Databricks Apps** - one serves MCP tool
  calls to the agent, the other serves a human-facing dashboard. Both read/write the exact same
  Lakebase tables (via their own copy of `lakebase.py` + `paper_broker.py`), so trades placed by
  the agent through MCP show up in the dashboard immediately, and vice versa.
- `mcp_server/paper_broker.py` is the actual paper-trading engine: it creates
  `paper_accounts`, `paper_positions`, `paper_orders`, and `paper_market_prices` tables in
  Lakebase, and implements quote simulation (seeded random walk per symbol) + order
  execution (cash/position accounting, insufficient-funds and oversell guardrails).
- `mcp_server/tos_mcp_server.py` wraps `paper_broker.py` with [FastMCP](https://gofastmcp.com/)
  `@mcp.tool` decorators and serves them over streamable HTTP - the transport Databricks'
  MCP client/gateway expects when you [host your own MCP server as a Databricks App](https://docs.databricks.com/aws/en/agents/mcp-tools/custom-mcp).

## Files

- `mcp_server/tos_mcp_server.py` - FastMCP server exposing the 5 paper-trading tools
- `mcp_server/paper_broker.py` - Paper-trading engine (accounts, positions, orders, simulated quotes)
- `mcp_server/lakebase.py` - Lakebase connection helper (same pattern as Day 2)
- `mcp_server/app.yaml` / `mcp_server/requirements.txt` - Databricks App config for the MCP server
- `dashboard/app.py` - Flask dashboard (read-only view of the paper account)
- `dashboard/templates/index.html` - Dashboard UI (cash, positions, P/L, recent orders)
- `dashboard/paper_broker.py` / `dashboard/lakebase.py` - copies of the same modules (each
  Databricks App deploys from its own folder, so each needs its own copy of shared code)
- `dashboard/app.yaml` / `dashboard/requirements.txt` - Databricks App config for the dashboard
- `setup_secrets.py` - One-time script to store the Lakebase URL secret (same as Day 2)
- `.env.example` - Local dev env var template

## Step-by-step setup

### 1. Reuse (or create) your Lakebase instance from Day 2

If you already have a Lakebase instance + native-password role from Day 2, reuse it - this lab
just adds new tables to the same instance. Otherwise, follow
[Day 2's step 2](../databricks-lakebase-app-day-2/README.md#2-create-a-lakebase-instance-and-a-native-password-role)
to create one.

### 2. Store the Lakebase secret

From a Databricks notebook (`%sh python setup_secrets.py`), same as Day 2 - this stores your
Lakebase URL as secret `database/lakebase-url`. If you already ran Day 2's `setup_secrets.py`
against the same secret scope/key, you can skip this.

### 3. Configure environment variables (local dev)

```bash
cp .env.example .env
# paste your Lakebase URL into LAKEBASE_URL
```

### 4. Install dependencies and run both apps locally

```bash
cd mcp_server && pip install -r requirements.txt && python tos_mcp_server.py   # serves MCP on :8000
```

In a second terminal:

```bash
cd dashboard && pip install -r requirements.txt && python app.py                # serves UI on :8001
```

Open `http://localhost:8001` to see the (initially empty) paper account. Use an
[MCP Inspector](https://docs.databricks.com/aws/en/agents/mcp-tools/connect-clients) or `curl`
against `http://localhost:8000` to sanity-check the tools before deploying.

### 5. Deploy both apps to Databricks Apps

Following [Day 2's step 7](../databricks-lakebase-app-day-2/README.md#7-create-a-git-folder-in-databricks-and-deploy-the-app-no-cli-required)
(Git folder + Apps UI, no CLI needed), but this time deploy **two** apps pointed at two
different subfolders of the same Git folder:

1. Create a Git folder for this repo (once) as in Day 2.
2. **Deploy the MCP server app**: Compute > Apps > Create app > Custom, name it e.g.
   `thinkorswim-mcp`, and point its source at the Git folder's `databricks-lakebase-app-day-3/mcp_server/`
   subfolder (so it picks up `mcp_server/app.yaml`). Deploy it, then copy its app URL - you'll
   register that URL as an external MCP server in step 6.
3. **Deploy the dashboard app**: repeat, naming it e.g. `paper-trading-dashboard`, pointing at
   `databricks-lakebase-app-day-3/dashboard/`. Deploy it and open its URL to confirm the (still
   empty) dashboard loads.

### 6. Register the MCP server as an external MCP in your workspace

Follow [Connect agents to external MCPs and tools](https://docs.databricks.com/aws/en/agents/mcp-tools/connect-external):

1. In your workspace, go to **AI Gateway** > **MCPs** > **Add MCP** (or **Register external MCP**).
2. Paste the `thinkorswim-mcp` app's URL from step 5 as the server endpoint (streamable HTTP).
3. Give it a name (e.g. `thinkorswim-paper-trading`) and save. Databricks will introspect the
   server and list the 5 tools (`get_quote`, `place_trade`, `get_positions`,
   `get_account_summary`, `get_order_history`).
4. Grant your Agent Bricks agent (created next) access to this MCP server via Unity Catalog
   permissions, if prompted.

### 7. Build the Agent Bricks agent

1. In your workspace sidebar, go to **Agents** > **Agent Bricks** > **Create agent**.
2. Choose the **Custom LLM** (or **Multi-agent supervisor**, if you want to combine this with a
   research agent) agent type - either works for a single tool-calling agent like this.
3. Under **Tools**, add:
   - The `thinkorswim-paper-trading` MCP server you registered in step 6 (all 5 tools, or a
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
   dashboard from step 5.

## Guardrails already built into `paper_broker.py`

- **No real money, no real brokerage**: everything is simulated and stored only in your own
  Lakebase instance.
- **Insufficient-funds check**: a BUY that would exceed the paper account's cash balance is
  rejected with a clear error (surfaced back to the agent as a tool error, so it can retry with
  a smaller size).
- **Oversell check**: a SELL larger than the current position is rejected the same way.
- **Deterministic quote seeding**: a fresh symbol always gets a sane starting price (a
  `random.Random(symbol)`-seeded value between $20-$450) instead of $0, so the first trade of a
  new ticker doesn't error out or produce a nonsensical fill price.

You (or students) can tighten these further - e.g. a max order size, a daily trade count limit,
or an allow-list of symbols - directly in `place_order()` in `paper_broker.py`.

## Swapping in a real broker later

Keep `mcp_server/tos_mcp_server.py`'s 5 tool signatures the same (`get_quote`, `place_trade`,
`get_positions`, `get_account_summary`, `get_order_history`) and replace the `paper_broker.*`
calls inside each `@mcp.tool` function with calls to a real broker SDK (e.g.
[schwab-py](https://github.com/alexgolec/schwab-py) for Schwab/thinkorswim's actual paper
trading API, or Alpaca's official MCP server). The Agent Bricks agent and its MCP registration
in step 6 don't need to change at all - only what's inside the tool implementations does.

## Notes

- `mcp_server/` and `dashboard/` intentionally duplicate `lakebase.py` and `paper_broker.py`
  rather than sharing a package, because each Databricks App deploys independently from its own
  folder with its own `app.yaml`/`requirements.txt` - there's no shared Python package install
  step across Databricks Apps. If you prefer a single shared package, publish `paper_broker.py`
  + `lakebase.py` to a private PyPI index or wheel and add it to both `requirements.txt` files
  instead of duplicating.
- `get_quote`'s random-walk simulation has no relationship to real market prices - don't use this
  lab's fills for anything beyond demonstrating the MCP wiring.
