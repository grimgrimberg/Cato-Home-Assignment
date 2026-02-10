# Daily Movers Assistant Specification

## Scope
Python + pip only, runnable in plain VS Code. No UiPath dependency for MVP.

## REQ-001 Movers Ingestion
- Fetch most active top N (default 20): ticker, name, open, close, price, abs change, % change, volume.
- Primary source: Yahoo screener JSON (`most_actives`) for US.
- Fallback: Yahoo HTML most-active parsing.

### Acceptance
- `--mode movers --region us --top 20` returns up to 20 rows with required fields.
- Fallback usage is explicitly marked in row + logs.

## REQ-002 Multi-Market Support
- Priorities: US, TASE (`.TA`), EU/UK (`.L`, `.PA`, `.DE`, etc.), crypto (`BTC-USD`).
- Modes:
  - `movers`: top-N using market strategy.
  - `watchlist`: explicit watchlist symbols for any market.
- Include sample watchlist with US + TASE + UK + crypto.

### Acceptance
- `--mode watchlist --watchlist watchlist.yaml` supports mixed-market symbols.
- Non-US movers use deterministic curated universes + chart ranking.

## REQ-003 Enrichment
For each ticker, attempt to provide:
- sector/industry (best effort)
- earnings date (best effort)
- top 3 headlines: title, URL, published_at (Yahoo RSS preferred)

### Acceptance
- Missing enrichment fields are explicit null + error details when retrieval failed.

## REQ-004 Analysis Output
Required fields per ticker:
- `why_it_moved` (exactly 2 sentences, references evidence or states none)
- `sentiment` in [-1, 1]
- `action` in {BUY, WATCH, SELL}
- `confidence` in [0, 1]
- `decision_trace` with evidence/signals/rules/summary
- `provenance_urls` list

### Acceptance
- Schema validation passes for each row.

## REQ-005 HITL
- `needs_review=true` if confidence < 0.75 OR abs(%change) > 15 OR missing headlines OR ingestion fallback used.
- Include `needs_review_reason`.

### Acceptance
- Rule triggers verified by tests.

## REQ-006 Outputs
Per run folder:
- `report.xlsx`: Movers sheet, conditional formatting, hyperlinks, stable columns, freeze panes.
- `digest.html`: single-file HTML with inline CSS/JS, Top 3 gainers, Top 3 losers, full sortable/filterable table.
- `archive.jsonl`: one full record per ticker.
- `run.json` and `run.log`.
- Sparkline: include mini trend; if unavailable, gracefully note fallback.
- Report table includes open and close prices.

### Acceptance
- All files are generated even for partial-success runs.

## REQ-007 Email
- Always generate `digest.eml`.
- If SMTP env vars exist and `--send-email` is true, send to SELF_EMAIL from FROM_EMAIL.
- Gmail defaults: 587 STARTTLS, fallback 465 SSL.
- Auth failure is non-fatal; status logged and in run metadata.
- Email backends must be modular/pluggable:
  - `eml` backend (default, always active)
  - `smtp` backend (optional, only when requested and configured)

### Acceptance
- `digest.eml` exists for every run, with or without SMTP configuration.
- Backend metadata in `run.json` indicates `eml` default path and `smtp` when send is attempted.
- Documentation includes SMTP presets for Gmail, Mailtrap sandbox, and Ethereal.

## REQ-008 Agentic Analysis (LangGraph + LangChain)
- Primary analysis uses a **LangGraph StateGraph** with 4 nodes: Researcher → Analyst → Critic → Recommender.
- The Analyst node uses `langchain-openai` `ChatOpenAI` when `OPENAI_API_KEY` is available.
- Conditional edges: Critic can request one retry from Analyst on low confidence.
- Recommender assigns portfolio tags: `top_pick_candidate`, `most_potential_candidate`, `contrarian_bounce_candidate`, `momentum_signal`.
- 3-tier fallback: LangGraph agent (primary) → Raw OpenAI Responses API (secondary) → Deterministic heuristics (always available).
- Model configurable via `ANALYSIS_MODEL` (default `gpt-4o-mini`).
- Strict JSON parsing to Pydantic, CoT sanitisation, 2-sentence enforcement.
- Without key, all agent nodes run with heuristic logic – pipeline never crashes.

## REQ-009 Performance
- Disk cache HTTP calls.
- Bounded concurrency (default 5 workers) for enrich/analyze.
- Avoid pathological slowness for top 20.

## REQ-010 Tests and Hardening
- Include unit tests for models/rules and backend behavior.
- Include golden run tests with fixtures to validate artifact generation.
- Include ralphing harness with adversarial cases:
  - missing data
  - rate limiting/transport failures
  - malformed symbols
  - non-US tickers
  - SMTP failure path

### Acceptance
- `pytest` passes including `tests/ralphing_harness.py`.
- Failure scenarios produce explicit error fields and never crash the run.

## CLI
`python -m daily_movers run --date YYYY-MM-DD --mode movers|watchlist --top N --region us|il|uk|eu|crypto --watchlist watchlist.yaml --out runs/<date> --send-email`

## Failure Semantics
- No run-level crash for per-item errors.
- Failed item includes explicit `errors[]`, `needs_review=true`, and reason.
