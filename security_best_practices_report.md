# Security Best Practices Report

## Executive Summary
No critical or high-severity security issues were found in this codebase. The main gaps are supply-chain
reproducibility (dependency pinning not enforced), and minor hardening opportunities around log redaction
and base URL validation.

## Critical Findings
None.

## High Findings
None.

## Medium Findings

**SBP-001: Dependency pinning is not enforced**
- **Impact:** Builds are not reproducible and are vulnerable to supply-chain drift if upstream versions change.
- **Evidence:** `requirements.txt:1-11`, `pyproject.toml:11-22`.
- **Recommendation:** Enforce `requirements.lock` (or a constraints file) in CI and production installs. Consider
  using a tool like `pip-tools` or `uv` to refresh pins on a cadence.

## Low Findings

**SBP-002: Logs may capture sensitive strings without redaction**
- **Impact:** If upstream services include sensitive data in error messages or URLs, it could be written to `run.log`.
- **Evidence:** `daily_movers/storage/runs.py:31-52`.
- **Recommendation:** Add a redaction step in `StructuredLogger.log` for known secrets (e.g., API keys, tokens,
  SMTP credentials) and strip query parameters from logged URLs by default.

**SBP-003: `OPENAI_BASE_URL` is not validated for HTTPS**
- **Impact:** A misconfigured base URL could send API keys to a non-HTTPS endpoint.
- **Evidence:** `daily_movers/config.py:41-43,95-97`, `daily_movers/pipeline/llm.py:31`.
- **Recommendation:** Validate that `OPENAI_BASE_URL` uses `https://` and warn or refuse non-HTTPS values.
