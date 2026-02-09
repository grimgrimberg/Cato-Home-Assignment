# Daily Movers Assistant

A Python market-digest pipeline that ingests Yahoo Finance data, enriches tickers with evidence, synthesizes explainable recommendations via a **LangGraph agentic engine** (with deterministic fallbacks), and produces demo-quality HTML + Excel + Email reports.

---

## Table of Contents

- [Quick Start](#quick-start)
- [What the Project Does](#what-the-project-does)
- [Architecture Diagram](#architecture-diagram)
- [Agentic Architecture (LangGraph)](#agentic-architecture-langgraph)
- [Modes: movers vs watchlist](#modes-movers-vs-watchlist)
- [Ingestion Details (Yahoo)](#ingestion-details-yahoo-and---source)
- [Watchlist File Format](#watchlist-file-format-yamljson)
- [Enrichment](#enrichment-best-effort)
- [Analysis Architecture](#analysis-architecture)
- [HITL Review Rules](#hitl-human-in-the-loop-review-rules)
- [Output Artifacts](#output-artifacts-per-run-folder)
- [Email & SMTP Setup](#email--smtp-setup)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [CLI Reference](#cli-reference-every-flag)
- [UiPath Integration](#uipath-integration-function-call-adapter)
- [Testing](#testing--hardening)
- [Debugging & Troubleshooting](#debugging--troubleshooting)
- [High-Value Notes](#high-value-notes-stuff-people-usually-miss)
- [Project Layout](#project-layout)

---

## Quick Start

### Install

```powershell
py -3 -m pip install -r requirements.txt -r requirements-dev.txt
```

### Run (opens digest.html automatically)

```powershell
py -3 -m daily_movers run --mode movers --region us --top 5 --out runs/quick-test
```

### Run tests

```powershell
py -3 -m pytest -q
```

### Convenience runner (Windows)

```powershell
.\scripts\tasks.ps1 help
.\scripts\tasks.ps1 install
.\scripts\tasks.ps1 test
.\scripts\tasks.ps1 run-movers -Date 2026-02-09 -Top 20 -Region us -Out runs/2026-02-09
```

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

```powershell
py -3 -m daily_movers run --mode movers --region us --source most-active --top 20 --out runs/movers-demo
```

Answers: "Given a market/region, what are the top N tickers worth investigating today?"

- `region=us` → Yahoo "Most Active" screener (JSON primary, HTML fallback)
- `region=il|uk|eu|crypto` → curated universe ranking via chart data

### Watchlist mode

```powershell
py -3 -m daily_movers run --mode watchlist --watchlist watchlist.yaml --top 60 --out runs/watchlist-demo
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
| `finance.yahoo.com/most-active` | HTML fallback for US movers | — |
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

```powershell
py -3 scripts/ethereal_run.py
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

```powershell
py -3 -m daily_movers run --mode movers --region us --top 5 --send-email --out runs/email-test
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

```powershell
py -3 -m pytest -q
```

### High-signal test subsets

| Command | What it covers |
|---------|---------------|
| `py -3 -m pytest tests/test_models.py -q` | Pydantic schemas + HITL rules |
| `py -3 -m pytest tests/test_yahoo_movers_source.py -q` | Ingestion routing + `--source` |
| `py -3 -m pytest tests/test_uipath_adapter.py -q` | UiPath adapter contract |
| `py -3 -m pytest tests/test_golden_run.py -q` | Artifact generation |
| `py -3 -m pytest tests/test_email_backends.py -q` | Email backends + SMTP fallback |
| `py -3 -m pytest tests/test_llm_normalization.py -q` | OpenAI output normalization |
| `py -3 -m pytest tests/ralphing_harness.py -q` | Adversarial / failure paths |

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

```powershell
# 1. Print resolved config
py -3 -c "from daily_movers.config import load_config; print(load_config().model_dump())"

# 2. Run a small test
py -3 -m daily_movers run --mode movers --region us --top 5 --out runs/debug-top5 --no-open

# 3. Inspect metadata and logs
Get-Content runs/debug-top5/run.json
Get-Content runs/debug-top5/run.log | Select-Object -Last 30
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

```powershell
$env:MAX_WORKERS=1
$env:REQUEST_TIMEOUT_SECONDS=30
$env:OPENAI_TIMEOUT_SECONDS=60
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
