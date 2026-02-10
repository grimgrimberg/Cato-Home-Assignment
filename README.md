# Daily Movers Assistant

**Python version required:** Python 3.10 or higher


Fetches market movers from Yahoo Finance, enriches each ticker with evidence (headlines + price series), runs an “agentic” analysis (LangGraph if available, otherwise deterministic fallbacks), and renders a digest as HTML + Excel + EML (optionally SMTP).
**Cross-platform:** Works identically on Windows, macOS, and Linux.  
**Plug-and-play:** No API keys required for basic runs (LLM and email are optional).
If you only want to run it: follow **Quickstart** and ignore the rest.

---

## Quickstart (2 minutes)

### 1) Create a venv + install deps

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```

**Windows (cmd):**
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
pip install -r requirements.txt -r requirements-dev.txt
```

### 2) Run a small demo (auto-opens the HTML digest)

```bash
python -m daily_movers run --mode movers --region us --top 5 --out runs/quick-test
```

**What `python -m daily_movers` means:**  
Runs Python and executes the `daily_movers` package as a module. This is the standard cross-platform way to run Python packages.

If you prefer running the CLI file directly:

**macOS / Linux:**
```bash
python daily_movers/cli.py run --mode movers --region us --top 5 --out runs/quick-test
```

**Windows:**
```powershell
python .\daily_movers\cli.py run --mode movers --region us --top 5 --out runs/quick-test
```

### 3) Run tests

```bash
python -m pytest -q
```

### 4) (Optional) Use helper scripts

**Windows (PowerShell):**
```powershell
.\scripts\tasks.ps1 help
.\scripts\tasks.ps1 install
.\scripts\tasks.ps1 test
.\scripts\tasks.ps1 run-movers -Date 2026-02-09 -Top 20 -Region us -Out runs/2026-02-09
```

**macOS / Linux (bash):**
```bash
bash scripts/quickstart.sh  # Quick setup + demo run
bash scripts/demo.sh        # Alternative demo script
python scripts/ethereal_run.py  # Ethereal SMTP demo
```

---

## What happens when you run it

The CLI is just a wrapper around one orchestrator function:

- **Ingest**: get a list of tickers (US “Most Active” screener or a regional universe or a watchlist file).
- **Enrich**: fetch per-ticker evidence (headlines RSS, quote page fields, price series).
- **Analyze** (per ticker):
  - baseline: deterministic heuristics (always available)
  - primary: LangGraph agent (uses OpenAI if configured; otherwise internal heuristics)
  - fallback: raw OpenAI call (only if LangGraph failed and key exists)
- **Critic + HITL rules**: normalize outputs + flag “needs review”.
- **Render**: write `digest.html`, `report.xlsx`, `digest.eml`, `archive.jsonl`, `run.json`, `run.log`.

Outputs live under `runs/<date-or-out>`.

---

## Configuration (optional)

Config is loaded from environment variables, and `.env` is auto-loaded (if present). See `daily_movers/config.py`.

Common env vars:

| Variable | What it does | When you need it |
| --- | --- | --- |
| `OPENAI_API_KEY` | Enables OpenAI-backed analysis | Only if you want LLM analysis |
| `OPENAI_BASE_URL` | OpenAI API base URL (default `https://api.openai.com/v1`) | Only for custom endpoints |
| `ANALYSIS_MODEL` | Model name (default `gpt-4o-mini`) | Optional |
| `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `FROM_EMAIL`, `SELF_EMAIL` | Enables SMTP sending (`--send-email`) | Only if you want email delivery |
| `CACHE_DIR`, `CACHE_TTL_SECONDS` | HTTP cache settings | Optional |
| `MAX_WORKERS`, `MAX_REQUESTS_PER_HOST` | Concurrency controls | Optional |
| `LOG_LEVEL` | `INFO`/`WARNING`/`ERROR` | Optional |

Minimal `.env` example (LLM + email):

```env
OPENAI_API_KEY=...
SMTP_HOST=smtp.gmail.com
SMTP_USERNAME=...
SMTP_PASSWORD=...
FROM_EMAIL=me@example.com
SELF_EMAIL=me@example.com
```

### Ethereal demo (SMTP)

If you’re using Ethereal for testing, set these in your `.env` (values come
from your Ethereal inbox page):

```env
SMTP_HOST=smtp.ethereal.email
SMTP_PORT=587
SMTP_USERNAME=your_ethereal_user
SMTP_PASSWORD=your_ethereal_password
FROM_EMAIL=your_ethereal_user
SELF_EMAIL=your_ethereal_user
```

The helper script [scripts/ethereal_run.py](scripts/ethereal_run.py) uses the
`.env` values first. If SMTP isn’t configured there, it will fall back to
`credentials.csv` (if present).

---

## Repo tour (the parts that matter)

If you’re trying to understand the codebase, start here:

- `daily_movers/cli.py` — CLI flags, builds a `RunRequest`, calls the orchestrator.
- `daily_movers/pipeline/orchestrator.py` — the main “do the whole run” function.
- `daily_movers/providers/yahoo_movers.py` — ingestion (movers list / watchlist list).
- `daily_movers/providers/yahoo_ticker.py` — per-ticker enrichment (RSS/quote/chart).
- `daily_movers/pipeline/agent.py` — LangGraph agent (research → analyst → critic → recommender).
- `daily_movers/pipeline/llm.py` — raw OpenAI Responses API fallback + strict JSON normalization.
- `daily_movers/pipeline/heuristics.py` — deterministic analysis when LLMs aren’t available.
- `daily_movers/pipeline/critic.py` — guardrails (two sentences, no chain-of-thought language, etc.).
- `daily_movers/render/html.py` + `daily_movers/render/excel.py` — output reports.
- `daily_movers/email/*` — always writes `digest.eml`, optionally sends via SMTP.
- `daily_movers/storage/cache.py` + `daily_movers/storage/runs.py` — HTTP caching + structured JSONL logs.

### Understanding the code

**Data flow:**
1. `cli.py` → `orchestrator.py` (the main function)
2. Ingestion: `yahoo_movers.py` fetches ticker list
3. Per-ticker loop (parallel): `yahoo_ticker.py` enriches → `agent.py`/`llm.py`/`heuristics.py` analyze → `critic.py` validates
4. Render: `html.py` + `excel.py` + `email/*` generate outputs
5. Write artifacts to `runs/<date>/`

**Key patterns:**
- Every module has a docstring explaining its purpose
- Errors are captured, not raised (so one bad ticker doesn't crash the run)
- All models are Pydantic (see `models.py` for the full schema)
- HTTP requests are cached + retried automatically (`storage/cache.py`)

---

## Common commands

All commands work identically on macOS, Linux, and Windows.

Movers (US most-active):

```bash
python -m daily_movers run --mode movers --region us --source most-active --top 20 --out runs/us-top20
```

Movers (regional universe ranking):

```ash
python -m daily_movers run --mode movers --region eu --source universe --top 20 --out runs/eu-top20
```

Watchlist:

```ash
python -m daily_movers run --mode watchlist --watchlist watchlist.yaml --top 60 --out runs/watchlist
```

Don’t auto-open the browser:

```ash
python -m daily_movers run --mode movers --region us --top 5 --no-open
```

---

## Business Concept

This project automates the daily "market movers" research flow for analysts and executives.
Instead of manually scanning Yahoo Finance and summarizing news, the pipeline fetches the top movers,
adds evidence, and produces explainable recommendations in analyst-friendly outputs (HTML, Excel, email).

See `docs/BUSINESS_CONCEPT.md` for the full business framing and stakeholder view.

---

## Technical Overview

The system is a Python CLI pipeline with an agentic analysis core (LangGraph) and deterministic fallbacks.
It ingests market data, enriches each ticker, runs a multi-node reasoning graph, and renders multiple outputs.
The design emphasizes explainability, consistent artifacts, and graceful degradation when external services fail.

See `docs/TECHNICAL_OVERVIEW.md` for architecture, reasoning logic, and system boundaries.

---

## Documentation

- `docs/BUSINESS_CONCEPT.md`
- `docs/TECHNICAL_OVERVIEW.md`
- `docs/DEPLOYMENT.md`
- `docs/OBSERVABILITY.md`

---

## What the Project Does

Each run follows five stages:

1. **Ingest** a list of tickers (from Yahoo "Most Active" screener, a curated universe, or a user watchlist)
2. **Enrich** each ticker with best-effort evidence (headlines, sector/industry, price series)
3. **Analyze** each ticker (LangGraph agent → raw OpenAI fallback → deterministic heuristics)
4. **Review** — apply HITL rules to flag items requiring manual attention
5. **Render** — produce `digest.html`, `report.xlsx`, `digest.eml`, `archive.jsonl`, `run.json`, `run.log`

The pipeline is resilient: per-ticker failures don't crash the run, and every error is recorded.

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────┐
│  CLI / UiPath Adapter                                │
│  ▼                                                   │
│  run_daily_movers(request, config)                   │
└──────────────────────────────────────────────────────┘
                         ▼
        ┌────────────────────────────────┐
        │  INGESTION                     │
        │  ├─ movers: Yahoo screener     │
        │  │   (JSON primary → HTML      │
        │  │    fallback)                │
        │  └─ watchlist: Chart API       │
        └────────────────────────────────┘
                         ▼
        ┌────────────────────────────────┐
        │  PER-TICKER (parallel)         │
        │  ├─ Enrich (headlines, sector, │
        │  │         price series)       │
        │  ├─ Analyze (LangGraph agent   │
        │  │   → OpenAI → heuristics)    │
        │  └─ HITL Review                │
        └────────────────────────────────┘
                         ▼
        ┌────────────────────────────────┐
        │  RENDERING & OUTPUT            │
        │  ├─ digest.html (auto-opens)   │
        │  ├─ report.xlsx                │
        │  ├─ digest.eml (always)        │
        │  ├─ SMTP send (if configured)  │
        │  ├─ archive.jsonl              │
        │  ├─ run.json                   │
        │  └─ run.log                    │
        └────────────────────────────────┘
```

---

## Agentic Architecture (LangGraph)

The core analysis uses a **LangGraph StateGraph** with four specialised nodes:

```
┌────────────┐     ┌──────────┐     ┌─────────┐     ┌─────────────┐
│ Researcher │────▶│ Analyst  │────▶│ Critic  │────▶│ Recommender │
└────────────┘     └──────────┘     └─────────┘     └─────────────┘
                        ▲               │
                        └── retry ◄─────┘  (conditional edge on low confidence)
```

| Node | Role |
|------|------|
| **Researcher** | Structures raw evidence from enrichment (headlines, numeric signals, sector) |
| **Analyst** | Produces sentiment, action (BUY/WATCH/SELL), confidence via `ChatOpenAI` or heuristic fallback |
| **Critic** | Guard-rails: CoT removal, confidence clipping, 2-sentence enforcement, provenance assembly |
| **Recommender** | Assigns portfolio tags: `top_pick_candidate`, `most_potential_candidate`, `contrarian_bounce`, `momentum_signal` |

**3-tier fallback strategy:**

1. **LangGraph agent** (primary) — uses `langchain-openai` `ChatOpenAI`
2. **Raw OpenAI** (secondary) — direct Responses API via `requests`
3. **Deterministic heuristics** (always available) — rule-based, no API key needed

With no `OPENAI_API_KEY`, the pipeline still runs and generates all artifacts.

---

## Modes: movers vs watchlist

### Movers mode


```bash
python -m daily_movers run --mode movers --region us --source most-active --top 20 --out runs/movers-demo
```

Answers: "Given a market/region, what are the top N tickers worth investigating today?"

- `region=us` → Yahoo "Most Active" screener (JSON primary, HTML fallback)
- `region=il|uk|eu|crypto` → curated universe ranking via chart data

### Watchlist mode


```bash
python -m daily_movers run --mode watchlist --watchlist watchlist.yaml --top 60 --out runs/watchlist-demo
```

Answers: "Analyze exactly these symbols."

---

## Ingestion Details (Yahoo) and `--source`

Ingestion code: `daily_movers/providers/yahoo_movers.py`

### `--source` options (movers mode only)

| Source | Behavior |
|--------|----------|
| `auto` (default) | US → screener; non-US → universe ranking |
| `most-active` | Force Yahoo screener (only `region=us`) |
| `universe` | Force curated universe ranking (all regions) |

### Yahoo endpoints used

| Endpoint | Purpose | Fallback |
|----------|---------|----------|
| `v1/finance/screener/predefined/saved?scrIds=most_actives` | US most-active movers | → HTML scrape |
| `finance.yahoo.com/markets/stocks/most-active/` | HTML fallback for US movers | — |
| `v8/finance/chart/{symbol}` | Price history + non-US movers + watchlist | — |
| `feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}` | Headlines | — |
| `finance.yahoo.com/quote/{symbol}` | Sector, industry, earnings | — |

---

## Watchlist File Format (YAML/JSON)

```yaml
symbols:
  - AAPL
  - TEVA.TA
  - BP.L
  - ASML.AS
  - BTC-USD
```

- Symbols are uppercased, trimmed, deduplicated (order preserved)
- Empty/invalid items are silently ignored
- If no valid symbols remain → `IngestionError`

---

## Enrichment (Best Effort)

Code: `daily_movers/providers/yahoo_ticker.py`

Per ticker, enrichment attempts:
- **Headlines** (RSS feed — title + URL + published time)
- **Sector / Industry** (Yahoo quote page, regex extraction)
- **Earnings date** (best effort)
- **Price series** (last 15 closes from chart API, for sparkline)

Missing fields → `null`. Failures → recorded in `errors[]`. The run continues.

---

## Analysis Architecture

### Required fields per ticker

| Field | Type | Constraint |
|-------|------|------------|
| `why_it_moved` | string | Exactly 2 sentences |
| `sentiment` | float | [-1, 1] |
| `action` | enum | BUY / WATCH / SELL |
| `confidence` | float | [0, 1] |
| `decision_trace` | object | evidence + numeric signals + rules + summary |
| `provenance_urls` | list | URLs backing the analysis |

Schema enforced by Pydantic models in `daily_movers/models.py`.

### LangGraph graph (primary path)

```
Researcher  →  Analyst  →  Critic  →  Recommender
                 ▲           │
                 └── retry ◄─┘   (at most one retry)
```

Implemented in `daily_movers/pipeline/agent.py`.

### Fallback chain

1. LangGraph agent (`daily_movers/pipeline/agent.py`)
2. Raw OpenAI Responses API (`daily_movers/pipeline/llm.py`)
3. Deterministic heuristics (`daily_movers/pipeline/heuristics.py`)

---

## HITL (Human-in-the-loop) Review Rules

Implemented by `apply_hitl_rules()` in `daily_movers/models.py`.

Rows are flagged `needs_review=true` when any trigger fires:

- confidence < 0.75
- |% change| > 15
- missing headlines
- ingestion fallback used
- explicit errors exist

The row includes `needs_review_reason` listing all triggered reasons.

---

## Output Artifacts (Per Run Folder)

| File | Description |
|------|-------------|
| `digest.html` | Single-file HTML digest with inline styling and sortable table |
| `report.xlsx` | Spreadsheet report with highlights sheet |
| `digest.eml` | RFC822 email message (always generated, even without SMTP) |
| `archive.jsonl` | One JSON line per ticker — full structured data |
| `run.json` | Run metadata: parameters, timings, status, summary, email metadata |
| `run.log` | Structured JSONL logs (events, stages, errors, retries) |

The CLI prints `{status, summary, paths}` JSON to stdout after each run.

Note: The HTML and Excel reports include open and close prices when available.

---

## Email & SMTP Setup

### How email works

- **`digest.eml`** is always written to the run folder (no configuration needed)
- **SMTP sending** only happens when you pass `--send-email` and SMTP credentials are configured
- The SMTP backend tries STARTTLS first, then falls back to SSL

### Option A: Ethereal Email (recommended for demos)

[Ethereal](https://ethereal.email/) is a free fake SMTP service. Emails are captured in a web inbox — nothing is delivered to real addresses.

**Step 1 — Create an Ethereal account**

1. Go to https://ethereal.email/create
2. Click **"Create Ethereal Account"**
3. Download the `credentials.csv` file (or copy the SMTP credentials shown on screen)

**Step 2 — Place `credentials.csv` in the project root**

The file Ethereal gives you looks like:

```csv
"Service","Name","Username","Password","Hostname","Port","Security"
"SMTP","Your Name","your.name@ethereal.email","yourpassword","smtp.ethereal.email",587,"STARTTLS"
"IMAP","Your Name","your.name@ethereal.email","yourpassword","imap.ethereal.email",993,"TLS"
"POP3","Your Name","your.name@ethereal.email","yourpassword","pop3.ethereal.email",995,"TLS"
```

> `credentials.csv` is git-ignored — it will **never** be committed.

**Step 3 — Run the Ethereal helper**


```bash
python scripts/ethereal_run.py
```

This will:
- Read SMTP credentials from `credentials.csv`
- Run a fresh movers pipeline (top 5, US most-active)
- Send the digest via Ethereal SMTP
- Open `digest.html` in your browser

**Step 4 — View the captured email**

1. Go to https://ethereal.email/login
2. Log in with your Ethereal username and password
3. Click **Messages** — your digest email will be there

### Option B: Gmail (App Password)

Set in `.env`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SSL_PORT=465
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
FROM_EMAIL=your_email@gmail.com
SELF_EMAIL=your_email@gmail.com
```

Then run with `--send-email`:


```bash
python -m daily_movers run --mode movers --region us --top 5 --send-email --out runs/email-test
```

### Option C: Mailtrap

```env
SMTP_HOST=sandbox.smtp.mailtrap.io
SMTP_PORT=587
SMTP_SSL_PORT=465
SMTP_USERNAME=<mailtrap_username>
SMTP_PASSWORD=<mailtrap_password>
FROM_EMAIL=alerts@example.test
SELF_EMAIL=alerts@example.test
```

---

## Configuration & Environment Variables

Configuration is a Pydantic model (`AppConfig`) in `daily_movers/config.py`.
`load_config()` loads `.env` (with `override=True` to avoid stale Windows shell vars).

### Runtime tuning

| Variable | Default | Purpose |
|----------|---------|---------|
| `MAX_WORKERS` | 5 | Thread pool size for parallel ticker processing |
| `MAX_REQUESTS_PER_HOST` | 5 | Concurrent HTTP requests allowed per host |
| `REQUEST_TIMEOUT_SECONDS` | 20 | Yahoo HTTP timeout |
| `CACHE_DIR` | `.cache/http` | Disk cache location |
| `CACHE_TTL_SECONDS` | 1800 | Cache freshness window |
| `LOG_LEVEL` | INFO | Logging verbosity |

### OpenAI (optional)

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | — | Enables LLM analysis (pipeline works without it) |
| `ANALYSIS_MODEL` | `gpt-4o-mini` | OpenAI model name |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | API base URL |
| `OPENAI_TIMEOUT_SECONDS` | 45 | OpenAI request timeout |

### SMTP (optional)

| Variable | Default | Purpose |
|----------|---------|---------|
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | 587 | STARTTLS port |
| `SMTP_SSL_PORT` | 465 | SSL fallback port |
| `SMTP_USERNAME` | — | SMTP login username |
| `SMTP_PASSWORD` | — | SMTP login password |
| `FROM_EMAIL` | — | Sender address |
| `SELF_EMAIL` | — | Recipient address |

---

## CLI Reference (Every Flag)

```powershell
py -3 -m daily_movers run [flags]
```

| Flag | Values | Default | Purpose |
|------|--------|---------|---------|
| `--date` | `YYYY-MM-DD` | today | Report metadata label (not historical) |
| `--mode` | `movers` / `watchlist` | `movers` | Ticker selection mode |
| `--region` | `us` / `il` / `uk` / `eu` / `crypto` | `us` | Region strategy (movers mode) |
| `--source` | `auto` / `most-active` / `universe` | `auto` | Movers ingestion source |
| `--top` | integer | 20 | Number of tickers to process |
| `--watchlist` | file path | — | Required for watchlist mode |
| `--out` | directory path | `runs/<date>` | Output directory |
| `--send-email` | flag | off | Attempt SMTP delivery |
| `--no-open` | flag | off | Don't auto-open digest.html |

---

## UiPath Integration (Function-call Adapter)

Module: `daily_movers/adapters/uipath.py`

```python
from daily_movers.adapters.uipath import run_daily_movers

result = run_daily_movers(
    out_dir="runs/uipath-demo",
    date="2026-02-09",
    mode="movers",
    region="us",
    source="most-active",
    top="20",
    send_email="false",
)
```

Contract:
- All inputs accept strings (UiPath-friendly coercion)
- Unknown arguments raise `TypeError`
- `mode=watchlist` requires `watchlist` and the file must exist
- Returns `dict` with keys: `status`, `summary`, `paths`

---

## Testing & Hardening


```bash
python -m pytest -q
```

### High-signal test subsets

| Command | What it covers |
|---------|---------------|
`python -m pytest tests/test_models.py -q` | Pydantic schemas + HITL rules |
`python -m pytest tests/test_yahoo_movers_source.py -q` | Ingestion routing + `--source` |
`python -m pytest tests/test_uipath_adapter.py -q` | UiPath adapter contract |
`python -m pytest tests/test_golden_run.py -q` | Artifact generation |
`python -m pytest tests/test_email_backends.py -q` | Email backends + SMTP fallback |
`python -m pytest tests/test_llm_normalization.py -q` | OpenAI output normalization |
`python -m pytest tests/ralphing_harness.py -q` | Adversarial / failure paths |

Note: `sitecustomize.py` sets `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` to prevent third-party pytest plugins from breaking test runs.

---

## Debugging & Troubleshooting

### VS Code debug configurations

The repo includes 4 debug configs in `.vscode/launch.json`:

- **Movers US (Most-Active Top 5 FAST)** — single-threaded, quickest for stepping through
- **Movers US (Most-Active Top 20)** — full run
- **Watchlist (All Exchanges 60)** — multi-market
- **UiPath Adapter (Smoke)** — runs `scripts/uipath_smoke.py`

### Practical debug recipe


```bash
# 1. Print resolved config
python -c "from daily_movers.config import load_config; print(load_config().model_dump())"

# 2. Run a small test
python -m daily_movers run --mode movers --region us --top 5 --out runs/debug-top5 --no-open

# 3. Inspect metadata and logs (Linux/macOS)
cat runs/debug-top5/run.json
tail -n 30 runs/debug-top5/run.log
# On Windows, use:
# Get-Content runs/debug-top5/run.json
# Get-Content runs/debug-top5/run.log | Select-Object -Last 30
```

### Common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Yahoo throttling | Too many parallel requests | `$env:MAX_WORKERS=1` |
| Slow/timeout | Network latency | Raise `REQUEST_TIMEOUT_SECONDS` |
| No OpenAI output | Missing API key | Expected — heuristic fallback works |
| SMTP auth failure | Bad credentials | Non-fatal; `.eml` is still written |
| Run "looks empty" | Low `--top` or ingestion error | Check `run.json` + `archive.jsonl` |

---

## High-Value Notes (Stuff People Usually Miss)

### Run status semantics

| Status | Meaning |
|--------|---------|
| `success` | All tickers processed without errors |
| `partial_success` | Artifacts generated, but ≥1 ticker had errors |
| `failed` | Run-level failure (rare) |

### Where to look when something seems wrong

1. `run.json` — status, summary, email metadata
2. `run.log` — structured JSONL with retries, latencies, errors
3. `archive.jsonl` — full per-ticker payload including error details

### Cache behavior

- All HTTP calls go through disk cache at `CACHE_DIR` (default `.cache/http`)
- TTL: `CACHE_TTL_SECONDS` (default 1800s)
- Force fresh data: `Remove-Item -Recurse -Force .\.cache\http`

### `--date` is a label

`--date` sets report metadata only. It does not fetch historical data.

### Reliability knobs for stable demos


```bash
# Linux/macOS
export MAX_WORKERS=1
export REQUEST_TIMEOUT_SECONDS=30
export OPENAI_TIMEOUT_SECONDS=60
# Windows (PowerShell)
# $env:MAX_WORKERS=1
# $env:REQUEST_TIMEOUT_SECONDS=30
# $env:OPENAI_TIMEOUT_SECONDS=60
```

---

## Project Layout

```
daily_movers/
  __main__.py              # python -m daily_movers entrypoint
  cli.py                   # argparse CLI
  config.py                # AppConfig + env loading + region universes
  errors.py                # typed exceptions
  models.py                # Pydantic models + HITL rules
  adapters/
    uipath.py              # strict UiPath function-call adapter
  email/
    base.py                # Protocol interfaces (EmlWriter, SmtpSender)
    eml_backend.py         # always writes digest.eml
    smtp_backend.py        # optional SMTP delivery (STARTTLS + SSL fallback)
  pipeline/
    orchestrator.py        # orchestration + artifact writing
    agent.py               # LangGraph analysis graph (4-node StateGraph)
    llm.py                 # raw OpenAI Responses API analyzer
    heuristics.py          # deterministic rule-based analysis
    critic.py              # guardrails (confidence, provenance, format)
  providers/
    yahoo_movers.py        # movers + watchlist ingestion
    yahoo_ticker.py        # per-ticker enrichment (chart, RSS, quote)
  render/
    html.py                # digest HTML renderer
    excel.py               # Excel renderer
    eml.py                 # EML message builder (standalone)
  storage/
    cache.py               # disk HTTP cache + HttpClient protocol
    runs.py                # run dirs + structured logger

scripts/
  ethereal_run.py          # one-click Ethereal SMTP demo
  uipath_smoke.py          # UiPath adapter debug entrypoint
  tasks.ps1                # Windows convenience runner
  demo.sh                  # bash demo script

tests/
  fixtures/                # test data (JSON, XML)
  test_models.py           # schema + HITL validation
  test_yahoo_movers_source.py  # ingestion routing
  test_uipath_adapter.py   # adapter contract
  test_golden_run.py       # artifact generation
  test_email_backends.py   # email backend coverage
  test_llm_normalization.py    # OpenAI output normalization
  test_agent.py            # LangGraph agent tests
  test_cli.py              # CLI argument parsing
  test_optional_fallbacks.py   # fallback chain
  ralphing_harness.py      # adversarial hardening
```
