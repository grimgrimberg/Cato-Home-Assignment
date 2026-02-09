# Daily Movers Assistant

Daily Movers Assistant is a Python market digest pipeline powered by a **LangGraph agentic analysis engine**, deterministic data ingestion, explainable AI synthesis, strong failure handling, and demo-quality HTML + Excel reports.

## Agentic Architecture (LangGraph)

The core analysis uses a **LangGraph StateGraph** with four specialised nodes connected by conditional edges:

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

The pipeline uses a 3-tier fallback strategy:
1. **LangGraph agent** (primary) – uses `langchain-openai` `ChatOpenAI`
2. **Raw OpenAI** (secondary) – direct Responses API via `requests`
3. **Deterministic heuristics** (always available) – rule-based, no API key needed

## Features
- **LangGraph StateGraph** with conditional edges and typed state (`AgentState`)
- **LangChain integration** via `langchain-openai` for LLM calls
- Movers mode (US screener + hybrid non-US universes)
- Watchlist mode across **US, TASE (.TA), UK (.L), EU (.PA/.DE/.AS), and Crypto (-USD)**
- Enrichment: headlines, earnings date, sector/industry (best effort)
- Analysis with decision trace, confidence, HITL flags, and **recommendation tags**
- **Top Pick** and **Most Potential** highlight cards in HTML digest
- **Market badges** showing breakdown across US, TASE, UK, EU, Crypto
- Outputs: Excel (with Highlights sheet), HTML digest, JSONL archive, run metadata, structured logs, EML
- Pluggable email backends (`eml` default + optional `smtp`)
- UiPath migration adapter (`daily_movers.adapters.uipath`)
- Auto-open `digest.html` in your default browser after each run (`--no-open` to disable)

## Install
```bash
# Daily Movers Assistant

Daily Movers Assistant is a **Python market-digest pipeline** that:

1) chooses a set of tickers (either from Yahoo “Most Active” or a user watchlist)
2) enriches each ticker with best-effort evidence (headlines + profile fields + short price series)
3) synthesizes an explainable recommendation (LangGraph + OpenAI when available, with deterministic fallbacks)
4) writes a complete run folder with:
   - `digest.html` (human-friendly digest)
   - `report.xlsx` (spreadsheet report)
   - `digest.eml` (email file; always generated)
   - `archive.jsonl` (one JSON record per ticker)
   - `run.json` (run metadata + summary)
   - `run.log` (structured JSONL logs)

The project is intentionally:

- VS Code friendly (works well with `py -3` on Windows)
- resilient (per-ticker failures don’t crash the entire run)
- explainable (every analysis includes a decision trace + provenance URLs)

Important: `--date` is a **report label** (metadata). This is not a historical backtesting engine.

---

## Table of Contents

- Quick start
- What the project does
- Modes: `movers` vs `watchlist`
- Ingestion details (Yahoo sources, `--source`)
- Watchlist file format
- Enrichment details
- Analysis architecture (LangGraph + fallbacks)
- HITL (human-in-the-loop) review rules
- Output artifacts (file-by-file)
- Configuration & environment variables
- CLI reference (every flag)
- UiPath integration (function-call adapter)
- Testing & hardening
- Debugging & troubleshooting
- Project layout

---

## Quick Start

### Install

Windows PowerShell:

```powershell
py -3 -m pip install -r requirements.txt -r requirements-dev.txt
```

### Run a small “movers” run (fast sanity check)

```powershell
py -3 -m daily_movers run --mode movers --region us --top 5 --out runs/debug-top5 --no-open
```

### Run a mixed-market watchlist

```powershell
py -3 -m daily_movers run --mode watchlist --watchlist watchlist.yaml --top 20 --out runs/watchlist-demo --no-open
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
.\scripts\tasks.ps1 run-movers -Date 2026-02-08 -Top 20 -Region us -Out runs/2026-02-08
.\scripts\tasks.ps1 run-watchlist -Watchlist watchlist.yaml -WatchOut runs/watchlist-demo
```

---

## Examples (Copy/Paste)

### A) US movers: explicitly use Yahoo “most-active”

Recommended for a realistic demo run.

```powershell
$env:MAX_WORKERS=2
py -3 -m daily_movers run --date 2026-02-09 --mode movers --region us --source most-active --top 20 --out runs/most-active-us-top20 --no-open
```

What you get in `runs/most-active-us-top20/`:

- `digest.html` (open it in a browser)
- `report.xlsx`
- `digest.eml`
- `archive.jsonl`
- `run.json`
- `run.log`

### B) Mixed-market watchlist: 60 symbols

```powershell
$env:MAX_WORKERS=2
py -3 -m daily_movers run --date 2026-02-09 --mode watchlist --watchlist watchlist_all_exchanges_60.yaml --top 60 --out runs/all-exchanges-top60 --no-open
```

### C) Try SMTP sending (optional)

SMTP send is attempted only when you pass `--send-email` and your SMTP env vars are set. The pipeline still always writes `digest.eml`.

```powershell
py -3 -m daily_movers run --date 2026-02-09 --mode movers --region us --top 20 --source most-active --send-email --out runs/email-demo --no-open
```

### D) UiPath adapter (function call)

```powershell
py -3 -c "from daily_movers.adapters.uipath import run_daily_movers; import json; print(json.dumps(run_daily_movers(out_dir='runs/uipath-demo', date='2026-02-09', mode='movers', region='us', source='most-active', top='5', send_email='false'), indent=2))"
```

---

## Best Test Runs (Copy/Paste)

These are the highest-signal test commands to demonstrate correctness and regression coverage.

### 1) Everything (fastest single command)

```powershell
py -3 -m pytest -q
```

### 2) Model + validation rules (schemas + HITL)

```powershell
py -3 -m pytest -q tests/test_models.py
```

### 3) Yahoo ingestion routing (including `--source` semantics)

```powershell
py -3 -m pytest -q tests/test_yahoo_movers_source.py
```

### 4) UiPath adapter contract (strict inputs, stable outputs)

```powershell
py -3 -m pytest -q tests/test_uipath_adapter.py
```

### 5) Golden run (artifact generation contract)

```powershell
py -3 -m pytest -q tests/test_golden_run.py
```

### 6) Ralphing harness (adversarial/failure-path hardening)

```powershell
py -3 -m pytest -q tests/ralphing_harness.py
```

---

## High-Value Notes (Stuff People Usually Miss)

### 1) Success vs partial success vs failed (what it actually means)

The pipeline is designed to be resilient. A single bad ticker should not crash the run.

- **`status=success`**: the run completed and there were no error rows.
- **`status=partial_success`**: the run completed and artifacts were generated, but at least one ticker row had errors (network timeouts, missing fields, parse issues, etc.).
- **`status=failed`**: the run failed at a run-level step (rare). The run may still have some artifacts depending on where it failed.

When you demo correctness, the key is: **artifacts exist even in partial-success runs**, and per-row errors are explicitly recorded.

### 2) Where to look first when something “looks off”

In order of usefulness:

1) `run.json`
  - run metadata (date/mode/region/source/top)
  - run timings
  - `status` and `summary`
  - email metadata (attempted/sent/status/error/backend)
2) `run.log`
  - structured JSONL logs for every stage (ingestion/enrichment/analysis/email)
  - includes retries, latency, fallback markers, and error messages
3) `archive.jsonl`
  - the full per-ticker payload (ticker/enrichment/analysis/needs_review/errors)

Practical commands:

```powershell
Get-Content runs/debug-top5/run.json
Get-Content runs/debug-top5/run.log | Select-Object -Last 50
Get-Content runs/debug-top5/archive.jsonl | Select-Object -First 3
```

### 3) The CLI prints the “artifact index” (`paths`) for you

After each run, the CLI prints a JSON object to stdout that looks like:

- `status`: run status
- `summary`: run summary counters and email metadata
- `paths`: absolute/relative paths to artifacts

This is the simplest integration point for scripts: parse stdout and use `paths["digest_html"]`, `paths["report_xlsx"]`, etc.

### 4) Cache behavior (why reruns get faster)

All Yahoo/OpenAI HTTP calls go through a disk-backed cache:

- location: `CACHE_DIR` (default `.cache/http`)
- TTL: `CACHE_TTL_SECONDS` (default 1800 seconds)

Meaning:

- rerunning the same request soon after is much faster
- if you suspect stale data or want to force fresh pulls, delete the cache folder:

```powershell
Remove-Item -Recurse -Force .\.cache\http
```

### 5) Reliability knobs (when Yahoo/OpenAI gets flaky)

These are the knobs that matter most for stable demos:

- **Reduce concurrency** (most important):

```powershell
$env:MAX_WORKERS=2
```

- Increase Yahoo timeout:

```powershell
$env:REQUEST_TIMEOUT_SECONDS=30
```

- Increase OpenAI timeout (only affects OpenAI calls):

```powershell
$env:OPENAI_TIMEOUT_SECONDS=60
```

### 6) Common pitfalls / “gotchas”

- `--date` is a label. It does not force Yahoo to return historical movers.
- `--source most-active` only supports `--region us` (by design).
- `--mode watchlist` requires `--watchlist` and the file must exist.
- `--send-email` does not change whether `digest.eml` is created (it’s always created). It only controls whether SMTP sending is attempted.
- If a run “looks empty”, check `--top` and then check `run.json` and `archive.jsonl` to confirm what was actually processed.

### 7) Environment loading behavior on Windows

Config loading uses `.env` (if present) and intentionally uses `override=true`. This avoids a common Windows issue where old shell environment variables accidentally override your `.env` values.

---

## What the Project Does (End-to-End)

Each run follows the same high-level stages:

1) Ingest a list of tickers

- `movers` mode: choose top-N “interesting” tickers based on region strategy
- `watchlist` mode: load your provided list and fetch them

2) Enrich each ticker (best effort)

- recent price series (for sparkline)
- sector/industry and earnings date when obtainable
- top headlines (title + URL + optional published time)

3) Analyze each ticker

- produce: 2-sentence “why it moved”, sentiment, action, confidence
- include a `decision_trace` explaining evidence + numeric signals + triggered rules
- include `provenance_urls`

4) Apply HITL rules to mark items requiring manual review

5) Render artifacts (HTML + Excel + EML) and write structured logs and metadata

The orchestrator is implemented in `daily_movers/pipeline/orchestrator.py`.

---

## Modes: `movers` vs `watchlist`

### Movers mode

```powershell
py -3 -m daily_movers run --date 2026-02-09 --mode movers --region us --source auto --top 20 --out runs/2026-02-09
```

Movers mode answers: “Given a market/region, what are the top N tickers worth investigating today?”

- For `region=us`, movers are sourced from Yahoo’s “Most Active” screener (JSON primary, HTML fallback).
- For `region=il|uk|eu|crypto`, movers are selected by ranking a curated universe using Yahoo chart data.

### Watchlist mode

```powershell
py -3 -m daily_movers run --mode watchlist --watchlist watchlist.yaml --top 60 --out runs/watchlist-60
```

Watchlist mode answers: “Analyze exactly these symbols.”

---

## Ingestion Details (Yahoo) and `--source`

Ingestion code is in `daily_movers/providers/yahoo_movers.py`.

### Movers sources (`--source`)

`--source` controls how **movers mode** selects tickers:

- `auto` (default)
  - US → Yahoo screener `most_actives`
  - non-US → curated universe ranking
- `most-active`
  - force Yahoo screener `most_actives` (only supported for `region=us`)
- `universe`
  - force curated universe ranking (supported for all regions)

### US “Most Active” endpoint

Primary JSON endpoint:

- `https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved` with `scrIds=most_actives`

If it fails or changes shape, ingestion falls back to parsing:

- `https://finance.yahoo.com/most-active`

Fallback usage is explicit:

- row-level: `ingestion_fallback_used=true`
- logging: `ingestion_primary_failed` in `run.log`

### Non-US movers ranking

Non-US movers are derived from `REGION_UNIVERSES` in `daily_movers/config.py`.
The pipeline fetches chart data for each symbol and ranks by movement/volume.

This is a deliberate tradeoff: stable, deterministic behavior over a fragile market-wide scraper.

---

## Watchlist File Format (YAML/JSON)

Accepted formats:

1) YAML/YML object with `symbols:`
2) JSON object with `symbols:`
3) JSON list

Example YAML:

```yaml
symbols:
  - AAPL
  - TEVA.TA
  - BP.L
  - ASML.AS
  - BTC-USD
```

Normalization behavior:

- symbols are uppercased and trimmed
- duplicates removed while preserving order
- empty/invalid items ignored
- if no valid symbols remain, ingestion fails with an `IngestionError`

---

## Enrichment (Best Effort)

Enrichment is implemented in `daily_movers/providers/yahoo_ticker.py`.

Typical enrichment includes:

- headline evidence (prefer RSS, best effort)
- sector / industry (best effort)
- earnings date (best effort)
- short price series for trend sparkline

Best-effort semantics:

- missing fields are set to `null`
- failures are recorded into `errors[]` on the row
- the run continues

---

## Analysis Architecture

### Required analysis fields

Per ticker, analysis must include:

- `why_it_moved` (exactly 2 sentences)
- `sentiment` in [-1, 1]
- `action` in {BUY, WATCH, SELL}
- `confidence` in [0, 1]
- `decision_trace` (evidence + numeric signals + rules + summary)
- `provenance_urls`

The schema is enforced by Pydantic models in `daily_movers/models.py`.

### LangGraph agent pipeline

Primary path: a LangGraph `StateGraph` with 4 nodes:

```
Researcher  →  Analyst  →  Critic  →  Recommender
                 ▲           │
                 └── retry ◄─┘   (at most one retry)
```

Node responsibilities:

- Researcher: structure evidence into a compact summary + normalized headline list + numeric signals
- Analyst: produce the analysis (LLM when configured, else heuristic)
- Critic: guardrails (two-sentence enforcement, bounds checking, provenance consistency)
- Recommender: assign portfolio tags (momentum/top-pick/contrarian, etc.)

This graph is implemented in `daily_movers/pipeline/agent.py`.

### 3-tier fallback strategy

The orchestrator uses this order:

1) LangGraph agent pipeline
2) raw OpenAI Responses API synthesis (`daily_movers/pipeline/llm.py`)
3) deterministic heuristics (`daily_movers/pipeline/heuristics.py`)

With no `OPENAI_API_KEY`, the pipeline still runs and generates all artifacts.

---

## HITL (Human-in-the-loop) Review Rules

HITL rules are implemented by `apply_hitl_rules` in `daily_movers/models.py`.
Rows are flagged `needs_review=true` when any of these triggers fire:

- confidence < 0.75
- abs(% change) > 15
- missing headlines
- ingestion fallback used
- explicit errors exist

The row includes `needs_review_reason` listing all triggered reasons.

---

## Output Artifacts (Per Run Folder)

Every run folder contains:

- `digest.html`
  - a single-file HTML digest with inline styling and a sortable/filterable table
- `report.xlsx`
  - spreadsheet report with stable columns and a highlights view
- `digest.eml`
  - always generated, even if SMTP is not configured
- `archive.jsonl`
  - one line per ticker; full structured data for audits/debugging
- `run.json`
  - run metadata: parameters, timings, status, summary, email metadata
- `run.log`
  - structured JSONL logs (events, stages, errors, retries)

The CLI prints a `RunArtifacts` JSON object to stdout, containing `{status, summary, paths}`.

---

## Configuration & Environment Variables

Configuration is a Pydantic model (`AppConfig`) in `daily_movers/config.py`.
`load_config()` loads `.env` (if present) and overrides existing process env vars.

### Common knobs

- `MAX_WORKERS` (default 5)
- `REQUEST_TIMEOUT_SECONDS` (default 20)
- `CACHE_TTL_SECONDS` (default 1800)
- `CACHE_DIR` (default `.cache/http`)
- `LOG_LEVEL` (default `INFO`)

### OpenAI

- `OPENAI_API_KEY` (optional)
- `ANALYSIS_MODEL` (default `gpt-4o-mini`)
- `OPENAI_BASE_URL` (default `https://api.openai.com/v1`)
- `OPENAI_TIMEOUT_SECONDS` (default 45)

### SMTP (optional)

The pipeline always writes `digest.eml`. SMTP sending only happens if you pass `--send-email`.
SMTP becomes “ready” when these are set:

- `SMTP_HOST`, `SMTP_PORT`, `SMTP_SSL_PORT`
- `SMTP_USERNAME`, `SMTP_PASSWORD`
- `FROM_EMAIL`, `SELF_EMAIL`

See the bottom of this README for copy/paste SMTP presets.

---

## CLI Reference (Every Flag)

Entrypoint:

```powershell
py -3 -m daily_movers run [flags]
```

Flags:

- `--date YYYY-MM-DD`
  - report metadata label (defaults to today)
- `--mode movers|watchlist`
  - ticker selection mode
- `--region us|il|uk|eu|crypto`
  - region strategy (movers mode)
- `--source auto|most-active|universe`
  - movers ingestion source selector
- `--top N`
  - number of items to ingest/analyze
- `--watchlist PATH`
  - required for watchlist mode (YAML/YML/JSON)
- `--out PATH`
  - output directory (default `runs/<date>`)
- `--send-email`
  - attempt SMTP delivery if configured
- `--no-open`
  - disable auto-opening `digest.html`

---

## UiPath Integration (Function-call Adapter)

UiPath commonly passes inputs as strings, so this repo includes a strict adapter:

- module: `daily_movers/adapters/uipath.py`
- function: `run_daily_movers(out_dir, *, date, mode, region, source, top, watchlist, send_email)`

Example:

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

Contract notes:

- unknown arguments are rejected (Python raises `TypeError`)
- `mode=watchlist` requires `watchlist` and the path must exist
- returns a JSON-serializable dict with keys: `status`, `summary`, `paths`
- `run.json` in the run folder is the canonical machine-readable record

---

## Testing & Hardening

Run all tests:

```powershell
py -3 -m pytest -q
```

Determinism note:

- this repo includes `sitecustomize.py` to set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` when running pytest
- this prevents unrelated third-party pytest plugins installed in your environment from breaking test runs

Focused test runs:

```powershell
py -3 -m pytest tests/test_models.py -q
py -3 -m pytest tests/test_golden_run.py -q
py -3 -m pytest tests/ralphing_harness.py -q
```

---

## Debugging & Troubleshooting

Practical debug recipe:

1) Print resolved config:

```powershell
py -3 -c "from daily_movers.config import load_config; print(load_config().model_dump())"
```

2) Run a small run:

```powershell
py -3 -m daily_movers run --mode movers --region us --top 5 --out runs/debug-top5 --no-open
```

3) Inspect metadata and logs:

```powershell
Get-Content runs/debug-top5/run.json
Get-Content runs/debug-top5/run.log | Select-Object -Last 50
```

Common issues:

- Yahoo throttling: check `run.log` for `http_fetch_failed` / `ingestion_primary_failed`
- slow network/timeouts: lower `MAX_WORKERS` and raise timeouts
- no OpenAI key: expected; heuristic fallback still produces outputs
- SMTP auth failure: non-fatal; `.eml` is still written

---

## Project Layout

```text
daily_movers/
  __main__.py            # python -m daily_movers entrypoint
  cli.py                 # argparse-based CLI
  config.py              # AppConfig + env loading + region universes
  errors.py              # application-specific exceptions
  models.py              # Pydantic models + HITL rules
  adapters/
    uipath.py            # strict UiPath adapter
  providers/
    yahoo_movers.py      # movers + watchlist ingestion
    yahoo_ticker.py      # per-ticker enrichment
  pipeline/
    orchestrator.py      # orchestration + artifact writing
    agent.py             # LangGraph analysis graph
    llm.py               # raw OpenAI analyzer
    heuristics.py        # deterministic analysis
    critic.py            # guardrails
  render/
    html.py              # digest renderer
    excel.py             # Excel renderer
  email/
    eml_backend.py       # always writes digest.eml
    smtp_backend.py      # optional SMTP delivery
  storage/
    cache.py             # disk HTTP cache
    runs.py              # run dirs + structured logger

tests/
  fixtures/
  ralphing_harness.py
  test_agent.py
  test_cli.py
  test_email_backends.py
  test_golden_run.py
  test_llm_normalization.py
  test_models.py
  test_optional_fallbacks.py
  test_uipath_adapter.py
  test_yahoo_movers_source.py
```

---

## SMTP Presets (Copy/Paste)

Gmail (App Password required):

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SSL_PORT=465
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
FROM_EMAIL=your_email@gmail.com
SELF_EMAIL=your_email@gmail.com
```

Mailtrap sandbox:

```env
SMTP_HOST=sandbox.smtp.mailtrap.io
SMTP_PORT=587
SMTP_SSL_PORT=465
SMTP_USERNAME=<mailtrap_username>
SMTP_PASSWORD=<mailtrap_password>
FROM_EMAIL=alerts@example.test
SELF_EMAIL=alerts@example.test
```

Ethereal:

```env
SMTP_HOST=smtp.ethereal.email
SMTP_PORT=587
SMTP_SSL_PORT=465
SMTP_USERNAME=<ethereal_username>
SMTP_PASSWORD=<ethereal_password>
FROM_EMAIL=<ethereal_username>
SELF_EMAIL=<ethereal_username>
```
