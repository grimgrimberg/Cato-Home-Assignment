# Daily Movers Assistant Execution Plan

> REQUIRED WORKFLOW: follow spec-driven development, test-first iterations, and explicit verification after each batch.

## Batch 1: Foundation and specs
1. Create repository bootstrap files and dependency manifests.
2. Write `specs/CONSTITUTION.md`, `specs/SPEC.md`, `specs/PROMPTS.md`.
3. Add this `specs/PLAN.md` as execution source of truth.
4. Verification:
   - `python -m pip install -r requirements.txt -r requirements-dev.txt`
   - `pytest -q` (expected initial failures or no tests)

## Batch 2: Core package skeleton
1. Add package layout and typed models/config.
2. Add storage modules for cache + run artifacts + structured logs.
3. Add provider modules for movers/watchlist and ticker enrichment.
4. Verification:
   - `pytest tests/test_models.py -q`

## Batch 3: Pipeline + renderers + CLI
1. Implement heuristic + optional LLM analyzer + critic.
2. Implement orchestrator with bounded concurrency and partial success behavior.
3. Implement Excel/HTML/EML rendering and optional SMTP send.
4. Implement modular email backends (`daily_movers/email/eml_backend.py`, `daily_movers/email/smtp_backend.py`).
5. Implement CLI and UiPath adapter.
6. Verification:
   - `python -m daily_movers run --date 2026-02-08 --mode movers --top 20 --out runs/2026-02-08`

## Batch 4: Hardening and ralphing
1. Add fixtures and golden tests.
2. Add ralphing harness for adversarial inputs and external failures.
3. Verify needs-review and explicit error fields.
4. Verification:
   - `pytest -q`

## Batch 5: Release polish
1. Finalize README with setup/demo/troubleshooting/wow checklist.
2. Add sample watchlist and demo script.
3. Final DoD verification:
   - `python -m daily_movers run --date 2026-02-08 --mode movers --top 20 --out runs/2026-02-08`
   - `python -m daily_movers run --mode watchlist --watchlist watchlist.yaml --out runs/watchlist-demo`
   - `pytest -q`

## Notes
- `--date` is report labeling metadata, not historical reconstruction.
- If `OPENAI_API_KEY` is absent, heuristics path must still pass all runs.
- `.eml` must always be created, regardless of SMTP status.
- `create-plan` skill path was unavailable upstream at implementation time; this PLAN follows the same execution workflow as fallback.
