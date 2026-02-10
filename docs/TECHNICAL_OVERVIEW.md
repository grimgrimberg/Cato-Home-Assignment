# Technical Overview

## Architecture Summary
The system is a Python CLI pipeline with an agentic core:
- Ingestion: fetches top movers from Yahoo Finance (JSON with HTML fallback).
- Enrichment: headlines, sector/industry, earnings date, and price series.
- Analysis: LangGraph agent with LLM primary, OpenAI raw fallback, and deterministic heuristics.
- Rendering: HTML digest, Excel report, email (EML and optional SMTP).

## Agentic Reasoning
LangGraph StateGraph uses four nodes:
1. Researcher: structures evidence and signals.
2. Analyst: generates sentiment, action, and summary.
3. Critic: normalizes output, enforces constraints, and removes reasoning leaks.
4. Recommender: assigns portfolio-level tags.

## Explainability
Each row includes a `decision_trace` with:
- evidence used (headlines)
- numeric signals
- rules triggered
- explainability summary

## Fallback Strategy
1. LangGraph agent (primary).
2. OpenAI Responses API (secondary).
3. Deterministic heuristics (always available).

## Key Artifacts
Per run:
- `digest.html`, `report.xlsx`, `digest.eml`
- `archive.jsonl` (full per-ticker data)
- `run.json` (metadata and timings)
- `run.log` (structured JSONL logs)
