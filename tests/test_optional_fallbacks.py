from __future__ import annotations

import json
from pathlib import Path

from daily_movers.config import AppConfig
from daily_movers.errors import AnalysisError, EnrichmentError
from daily_movers.models import Enrichment, Headline, TickerRow
from daily_movers.pipeline.orchestrator import RunRequest, run_daily_movers
from daily_movers.providers.yahoo_ticker import enrich_ticker
from daily_movers.storage.cache import CachedHttpClient
from daily_movers.storage.runs import StructuredLogger


def test_openai_failure_falls_back_without_hard_row_error(tmp_path: Path, monkeypatch) -> None:
    from daily_movers.pipeline import orchestrator

    def fake_get_movers(*, region, source, top_n, client, logger):
        return [
            TickerRow(
                ticker="AAPL",
                name="Apple Inc.",
                price=278.12,
                abs_change=2.21,
                pct_change=0.80,
                volume=50_420_700,
                market="us",
                ingestion_source="fixture",
            )
        ]

    def fake_enrich_ticker(*, row, client, logger):
        return Enrichment(
            sector="Technology",
            industry="Consumer Electronics",
            headlines=[Headline(title="AAPL headline", url="https://example.com/aapl")],
            price_series=[100, 101, 102],
        )

    def fake_synthesize(self, *, row, enrichment):
        raise AnalysisError("forced OpenAI failure", stage="analysis", url="https://api.openai.com/v1/responses")

    # Also make the LangGraph agent fail completely so Path 2 (raw OpenAI) is exercised
    def fake_agent_analysis(*, row, enrichment, config, run_logger):
        raise RuntimeError("forced agent failure for test")

    monkeypatch.setattr(orchestrator, "get_movers", fake_get_movers)
    monkeypatch.setattr(orchestrator, "enrich_ticker", fake_enrich_ticker)
    monkeypatch.setattr(orchestrator.OpenAIAnalyzer, "synthesize", fake_synthesize)
    monkeypatch.setattr(orchestrator, "run_agent_analysis", fake_agent_analysis)

    out_dir = tmp_path / "run"
    request = RunRequest(date="2026-02-08", mode="movers", out_dir=str(out_dir), top=1)
    config = AppConfig(
        cache_dir=tmp_path / "cache",
        openai_api_key="sk-invalid-for-test",
        from_email="from@example.com",
        self_email="self@example.com",
    )

    artifacts = run_daily_movers(request=request, config=config)
    run_meta = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    row = json.loads((out_dir / "archive.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert artifacts.status == "success"
    assert run_meta["summary"]["error_rows"] == 0
    assert row["analysis"]["errors"] == []
    assert "openai_fallback_used" in row["analysis"]["decision_trace"]["rules_triggered"]


def test_agent_fallback_to_heuristics_produces_valid_result(tmp_path: Path, monkeypatch) -> None:
    """When the LangGraph agent handles fallback internally, the run still succeeds."""
    from daily_movers.pipeline import orchestrator

    def fake_get_movers(*, region, source, top_n, client, logger):
        return [
            TickerRow(
                ticker="AAPL",
                name="Apple Inc.",
                price=278.12,
                abs_change=2.21,
                pct_change=0.80,
                volume=50_420_700,
                market="us",
                ingestion_source="fixture",
            )
        ]

    def fake_enrich_ticker(*, row, client, logger):
        return Enrichment(
            sector="Technology",
            industry="Consumer Electronics",
            headlines=[Headline(title="AAPL headline", url="https://example.com/aapl")],
            price_series=[100, 101, 102],
        )

    monkeypatch.setattr(orchestrator, "get_movers", fake_get_movers)
    monkeypatch.setattr(orchestrator, "enrich_ticker", fake_enrich_ticker)

    out_dir = tmp_path / "run"
    request = RunRequest(date="2026-02-08", mode="movers", out_dir=str(out_dir), top=1)
    config = AppConfig(
        cache_dir=tmp_path / "cache",
        openai_api_key=None,
        from_email="from@example.com",
        self_email="self@example.com",
    )

    artifacts = run_daily_movers(request=request, config=config)
    run_meta = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    row = json.loads((out_dir / "archive.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert artifacts.status == "success"
    assert run_meta["summary"]["processed"] == 1
    # Agent produces analysis via heuristic fallback, uses 'langgraph' model tag
    assert "langgraph" in row["analysis"]["model_used"]


def test_optional_profile_fetch_failure_does_not_mark_enrichment_error(tmp_path: Path, monkeypatch) -> None:
    from daily_movers.providers import yahoo_ticker

    def fake_price_series(symbol, *, client, logger):
        return [1.0, 2.0, 3.0], 100.0, 101.0

    def fake_headlines(symbol, *, client, logger, top_n=3):
        return [Headline(title="h1", url="https://example.com/1")]

    def fake_profile(symbol, *, client, logger):
        raise EnrichmentError("profile blocked", stage="enrichment", url="https://finance.yahoo.com/quote/AAPL")

    monkeypatch.setattr(yahoo_ticker, "fetch_price_series", fake_price_series)
    monkeypatch.setattr(yahoo_ticker, "fetch_headlines", fake_headlines)
    monkeypatch.setattr(yahoo_ticker, "fetch_quote_profile_fields", fake_profile)

    client = CachedHttpClient(
        cache_dir=tmp_path / "cache",
        default_ttl_seconds=60,
        timeout_seconds=5,
        user_agent="test-agent",
    )
    logger = StructuredLogger(path=tmp_path / "run.log", run_id="test")
    row = TickerRow(ticker="AAPL", ingestion_source="fixture")

    enrichment = enrich_ticker(row=row, client=client, logger=logger)

    assert enrichment.errors == []
    assert enrichment.headlines
    assert enrichment.price_series
