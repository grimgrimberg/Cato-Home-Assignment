# Daily Movers Constitution

## 1) Quality Bar
- All outputs must be deterministic for the same inputs and cached HTTP state.
- No silent failures: every external failure must produce explicit typed error fields and structured logs.
- Partial success is acceptable only when each failed ticker has `needs_review=true` with a clear reason.
- Public explanations must be evidence-based and concise.

## 2) Explanation Policy (No CoT)
- Do not expose chain-of-thought or hidden reasoning.
- Use `decision_trace` only:
  - `evidence_used`: headline title + URL + published time.
  - `numeric_signals_used`: concrete metrics (price, change, volume, confidence inputs).
  - `rules_triggered`: explicit rule names.
  - `explainability_summary`: short plain-language summary.
- If evidence is missing, say so directly.

## 3) Reliability Posture
- Treat Yahoo/OpenAI/SMTP/network as unreliable dependencies.
- Every external call must be guarded by typed exceptions and retries where appropriate.
- A single ticker failure must not crash the run.
- Run-level status must be one of: `success`, `partial_success`, `failed`.

## 4) Logging Schema
- Log format is JSON lines in `run.log`.
- Required keys:
  - `timestamp`
  - `level`
  - `event`
  - `run_id`
  - `stage`
  - `symbol`
  - `status`
  - `error_type`
  - `error_message`
  - `url`
  - `latency_ms`
  - `retries`
  - `fallback_used`
- Extra keys are allowed but cannot replace required keys.

## 5) Caching Rules
- Cache HTTP responses on disk by request fingerprint.
- Cache entries include body, status code, content type, creation time, TTL.
- Expired cache entries are refreshed.
- Cache is read/write best effort; cache errors cannot stop processing.

## 6) HITL Rules
Set `needs_review=true` if any is true:
- `confidence < 0.75`
- `abs(%change) > 15`
- missing headlines
- ingestion fallback used
- any enrichment/analysis/email error tied to ticker

Also include `needs_review_reason` as a non-empty list.

## 7) Data Integrity Rules
- LLM is synthesis-only and must never invent unsupported facts.
- Provenance URLs are mandatory for non-empty evidence.
- Column order in Excel and table order in HTML must be stable.
- Archive JSONL stores one complete ticker record per line.
