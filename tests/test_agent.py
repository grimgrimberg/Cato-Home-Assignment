"""Tests for the LangGraph agent pipeline."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from daily_movers.config import AppConfig
from daily_movers.models import (
    Action,
    Analysis,
    Enrichment,
    Headline,
    ReportRow,
    TickerRow,
)
from daily_movers.pipeline.agent import (
    AgentState,
    _heuristic_analyst,
    _ensure_two_sentences,
    _extract_json,
    _normalise_action,
    analyst_node,
    critic_node,
    recommender_node,
    researcher_node,
    run_agent_analysis,
)
from daily_movers.storage.runs import StructuredLogger


def _logger(tmp_path: Path) -> StructuredLogger:
    return StructuredLogger(path=tmp_path / "run.log", run_id="agent-test")


def _sample_row() -> TickerRow:
    return TickerRow(
        ticker="AAPL",
        name="Apple Inc.",
        price=189.12,
        abs_change=7.63,
        pct_change=4.2,
        volume=123_456_789,
        market="us",
        ingestion_source="fixture",
    )


def _sample_enrichment() -> Enrichment:
    return Enrichment(
        sector="Technology",
        industry="Consumer Electronics",
        earnings_date="Apr 30, 2026",
        headlines=[
            Headline(
                title="Apple unveils new product line at WWDC",
                url="https://news.example.com/apple-1",
                published_at="2026-02-08T10:00:00+00:00",
            ),
            Headline(
                title="AAPL surges on strong earnings beat",
                url="https://news.example.com/apple-2",
                published_at="2026-02-08T09:00:00+00:00",
            ),
        ],
        price_series=[176.2, 179.5, 182.1, 185.0, 189.12],
    )


# ---------------------------------------------------------------------------
# Test researcher node
# ---------------------------------------------------------------------------

def test_researcher_node_extracts_evidence() -> None:
    row = _sample_row()
    enrichment = _sample_enrichment()
    state: AgentState = {
        "row": row.model_dump(),
        "enrichment": enrichment.model_dump(),
    }

    result = researcher_node(state)

    assert "evidence_summary" in result
    assert "AAPL" in result["evidence_summary"]
    assert len(result["evidence_headlines"]) == 2
    assert result["numeric_signals"]["pct_change"] == 4.2
    assert result["numeric_signals"]["sector"] == "Technology"


def test_researcher_node_handles_no_headlines() -> None:
    row = _sample_row()
    enrichment = Enrichment()
    state: AgentState = {
        "row": row.model_dump(),
        "enrichment": enrichment.model_dump(),
    }

    result = researcher_node(state)
    assert "No fresh headline" in result["evidence_summary"]
    assert len(result["evidence_headlines"]) == 0


# ---------------------------------------------------------------------------
# Test analyst node (heuristic path)
# ---------------------------------------------------------------------------

def test_analyst_node_produces_valid_output_without_api_key() -> None:
    row = _sample_row()
    enrichment = _sample_enrichment()
    researcher_out = researcher_node({
        "row": row.model_dump(),
        "enrichment": enrichment.model_dump(),
    })

    state: AgentState = {
        "row": row.model_dump(),
        "enrichment": enrichment.model_dump(),
        "_config": {"openai_api_key": None},
        **researcher_out,
    }

    result = analyst_node(state)
    ao = result["analyst_output"]

    assert ao["action"] in ("BUY", "WATCH", "SELL")
    assert -1 <= ao["sentiment"] <= 1
    assert 0 <= ao["confidence"] <= 1
    assert ao["why_it_moved"]
    assert result["model_used"] == "langgraph:heuristics"


# ---------------------------------------------------------------------------
# Test critic node
# ---------------------------------------------------------------------------

def test_critic_node_builds_valid_analysis() -> None:
    row = _sample_row()
    enrichment = _sample_enrichment()
    researcher_out = researcher_node({
        "row": row.model_dump(),
        "enrichment": enrichment.model_dump(),
    })
    analyst_out = analyst_node({
        "row": row.model_dump(),
        "enrichment": enrichment.model_dump(),
        "_config": {"openai_api_key": None},
        **researcher_out,
    })

    state: AgentState = {
        "row": row.model_dump(),
        "enrichment": enrichment.model_dump(),
        "retry_count": 0,
        **researcher_out,
        **analyst_out,
    }

    result = critic_node(state)

    assert result["critic_approved"] is True
    analysis = result["analysis"]
    assert analysis["action"] in ("BUY", "WATCH", "SELL")
    assert -1 <= analysis["sentiment"] <= 1
    assert 0 <= analysis["confidence"] <= 1
    assert "decision_trace" in analysis
    assert "provenance_urls" in analysis


def test_critic_node_removes_cot_language() -> None:
    state: AgentState = {
        "row": {"ticker": "AAPL", "pct_change": 2.0},
        "enrichment": {},
        "evidence_headlines": [],
        "numeric_signals": {"pct_change": 2.0, "volume": 100000},
        "retry_count": 0,
        "model_used": "test",
        "analyst_output": {
            "why_it_moved": "Let me think step-by-step about why AAPL moved. It went up.",
            "sentiment": 0.5,
            "action": "BUY",
            "confidence": 0.8,
            "rules_triggered": ["test_rule"],
            "explainability_summary": "Test summary.",
        },
    }

    result = critic_node(state)
    assert "chain of thought" not in result["analysis"]["why_it_moved"].lower()
    assert "let me think" not in result["analysis"]["why_it_moved"].lower()


# ---------------------------------------------------------------------------
# Test recommender node
# ---------------------------------------------------------------------------

def test_recommender_tags_top_pick() -> None:
    state: AgentState = {
        "analysis": {
            "action": "BUY",
            "confidence": 0.85,
            "sentiment": 0.6,
        },
        "numeric_signals": {
            "pct_change": 5.0,
            "volume": 10_000_000,
        },
    }

    result = recommender_node(state)
    assert "top_pick_candidate" in result["recommendation_tags"]


def test_recommender_tags_most_potential() -> None:
    state: AgentState = {
        "analysis": {
            "action": "WATCH",
            "confidence": 0.6,
            "sentiment": 0.3,
        },
        "numeric_signals": {
            "pct_change": 1.0,
            "volume": 1_000_000,
        },
    }

    result = recommender_node(state)
    assert "most_potential_candidate" in result["recommendation_tags"]


def test_recommender_tags_contrarian() -> None:
    state: AgentState = {
        "analysis": {
            "action": "SELL",
            "confidence": 0.7,
            "sentiment": -0.5,
        },
        "numeric_signals": {
            "pct_change": -8.0,
            "volume": 10_000_000,
        },
    }

    result = recommender_node(state)
    assert "contrarian_bounce_candidate" in result["recommendation_tags"]


# ---------------------------------------------------------------------------
# Test full agent pipeline (heuristic path, no API key)
# ---------------------------------------------------------------------------

def test_full_agent_pipeline_heuristic_mode(tmp_path: Path) -> None:
    row = _sample_row()
    enrichment = _sample_enrichment()
    config = AppConfig(cache_dir=tmp_path / "cache", openai_api_key=None)
    logger = _logger(tmp_path)

    analysis = run_agent_analysis(
        row=row,
        enrichment=enrichment,
        config=config,
        run_logger=logger,
    )

    assert isinstance(analysis, Analysis)
    assert analysis.action in (Action.BUY, Action.WATCH, Action.SELL)
    assert -1 <= analysis.sentiment <= 1
    assert 0 <= analysis.confidence <= 1
    assert "langgraph" in analysis.model_used
    assert analysis.decision_trace.rules_triggered
    assert analysis.why_it_moved

    # Verify two sentences
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", analysis.why_it_moved) if s.strip()]
    assert len(sentences) == 2


def test_full_agent_pipeline_with_no_headlines(tmp_path: Path) -> None:
    row = TickerRow(
        ticker="XYZ",
        name="Unknown Corp",
        price=10.0,
        abs_change=-0.5,
        pct_change=-4.8,
        volume=500_000,
        ingestion_source="fixture",
    )
    enrichment = Enrichment()
    config = AppConfig(cache_dir=tmp_path / "cache", openai_api_key=None)
    logger = _logger(tmp_path)

    analysis = run_agent_analysis(
        row=row,
        enrichment=enrichment,
        config=config,
        run_logger=logger,
    )

    assert isinstance(analysis, Analysis)
    assert "langgraph" in analysis.model_used


# ---------------------------------------------------------------------------
# Test helper functions
# ---------------------------------------------------------------------------

def test_extract_json_from_clean_input() -> None:
    text = '{"sentiment": 0.5, "action": "BUY"}'
    result = _extract_json(text)
    assert result["action"] == "BUY"


def test_extract_json_from_markdown_wrapped() -> None:
    text = '```json\n{"sentiment": 0.5, "action": "SELL"}\n```'
    result = _extract_json(text)
    assert result["action"] == "SELL"


def test_normalise_action_fallback() -> None:
    assert _normalise_action("BUY", 0.5) == "BUY"
    assert _normalise_action("invalid", 0.5) == "BUY"
    assert _normalise_action("invalid", -0.5) == "SELL"
    assert _normalise_action("invalid", 0.0) == "WATCH"


def test_ensure_two_sentences_pads_single() -> None:
    result = _ensure_two_sentences(
        "AAPL went up today.",
        ticker="AAPL",
        pct=2.0,
        action="BUY",
        confidence=0.8,
        has_headlines=True,
    )
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", result) if s.strip()]
    assert len(sentences) == 2


def test_ensure_two_sentences_handles_empty() -> None:
    result = _ensure_two_sentences(
        "",
        ticker="TSLA",
        pct=-3.0,
        action="SELL",
        confidence=0.6,
        has_headlines=False,
    )
    assert "TSLA" in result
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", result) if s.strip()]
    assert len(sentences) == 2


# ---------------------------------------------------------------------------
# Test multi-market tickers through agent
# ---------------------------------------------------------------------------

def test_agent_handles_tase_ticker(tmp_path: Path) -> None:
    row = TickerRow(
        ticker="TEVA.TA",
        name="Teva Pharmaceutical",
        price=10820,
        abs_change=140,
        pct_change=1.31,
        volume=4_450_021,
        market="il",
        ingestion_source="fixture",
    )
    enrichment = Enrichment(
        sector="Healthcare",
        headlines=[Headline(title="Teva reports Q4", url="https://example.com/teva")],
    )
    config = AppConfig(cache_dir=tmp_path / "cache")
    logger = _logger(tmp_path)

    analysis = run_agent_analysis(row=row, enrichment=enrichment, config=config, run_logger=logger)
    assert isinstance(analysis, Analysis)


def test_agent_handles_crypto_ticker(tmp_path: Path) -> None:
    row = TickerRow(
        ticker="BTC-USD",
        name="Bitcoin USD",
        price=95000,
        abs_change=2500,
        pct_change=2.7,
        volume=45_000_000_000,
        market="crypto",
        ingestion_source="fixture",
    )
    enrichment = Enrichment(
        headlines=[Headline(title="Bitcoin rallies", url="https://example.com/btc")],
    )
    config = AppConfig(cache_dir=tmp_path / "cache")
    logger = _logger(tmp_path)

    analysis = run_agent_analysis(row=row, enrichment=enrichment, config=config, run_logger=logger)
    assert isinstance(analysis, Analysis)


def test_agent_handles_eu_ticker(tmp_path: Path) -> None:
    row = TickerRow(
        ticker="ASML.AS",
        name="ASML Holding",
        price=680.5,
        abs_change=12.3,
        pct_change=1.84,
        volume=2_100_000,
        market="eu",
        ingestion_source="fixture",
    )
    enrichment = Enrichment(sector="Technology", industry="Semiconductors")
    config = AppConfig(cache_dir=tmp_path / "cache")
    logger = _logger(tmp_path)

    analysis = run_agent_analysis(row=row, enrichment=enrichment, config=config, run_logger=logger)
    assert isinstance(analysis, Analysis)
