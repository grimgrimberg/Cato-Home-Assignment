# Observability

## Structured Logs
`run.log` is JSONL with one event per line. Required fields include:
- `timestamp`, `level`, `event`, `run_id`, `stage`, `symbol`
- `status`, `error_type`, `error_message`, `url`, `latency_ms`, `retries`, `fallback_used`

Use `LOG_LEVEL` to control verbosity.

## Run Metadata
`run.json` provides:
- run configuration
- summary counts
- email delivery metadata
- per-stage timings (ms)

## Suggested Metrics
If you want metrics beyond logs, consider extracting:
- cache hit ratio
- per-stage latency
- error rates by stage
- model usage rates (LLM vs heuristics)
