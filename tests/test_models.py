from __future__ import annotations

import pytest

from daily_movers.models import (
    Action,
    Analysis,
    DecisionTrace,
    Enrichment,
    Headline,
    ReportRow,
    TickerRow,
    apply_hitl_rules,
)


def _base_analysis(confidence: float = 0.8) -> Analysis:
    return Analysis(
        why_it_moved="AAPL moved +1.00% on available evidence. Volume and price context support a cautious watch call.",
        sentiment=0.2,
        action=Action.WATCH,
        confidence=confidence,
        decision_trace=DecisionTrace(
            evidence_used=[],
            numeric_signals_used={"pct_change": 1.0},
            rules_triggered=["baseline_rule"],
            explainability_summary="Baseline summary.",
        ),
        provenance_urls=["https://finance.yahoo.com/quote/AAPL"],
    )


def test_apply_hitl_rules_triggers_for_missing_headlines_and_low_confidence() -> None:
    row = ReportRow(
        ticker=TickerRow(ticker="AAPL", ingestion_source="test", pct_change=2.0),
        enrichment=Enrichment(headlines=[]),
        analysis=_base_analysis(confidence=0.6),
    )

    flagged = apply_hitl_rules(row)

    assert flagged.needs_review is True
    assert "confidence_below_threshold" in flagged.needs_review_reason
    assert "missing_headlines" in flagged.needs_review_reason


def test_apply_hitl_rules_triggers_for_fallback_and_extreme_move() -> None:
    row = ReportRow(
        ticker=TickerRow(
            ticker="TSLA",
            ingestion_source="fallback",
            ingestion_fallback_used=True,
            pct_change=18.0,
        ),
        enrichment=Enrichment(headlines=[Headline(title="x", url="https://example.com")]),
        analysis=_base_analysis(confidence=0.9),
    )

    flagged = apply_hitl_rules(row)

    assert flagged.needs_review is True
    assert "extreme_percent_change" in flagged.needs_review_reason
    assert "ingestion_fallback_used" in flagged.needs_review_reason


def test_analysis_validation_rejects_out_of_range_values() -> None:
    with pytest.raises(Exception):
        Analysis(
            why_it_moved="One. Two.",
            sentiment=1.2,
            action=Action.WATCH,
            confidence=0.5,
            decision_trace=DecisionTrace(
                evidence_used=[],
                numeric_signals_used={},
                rules_triggered=[],
                explainability_summary="x",
            ),
            provenance_urls=[],
        )

    with pytest.raises(Exception):
        Analysis(
            why_it_moved="One. Two.",
            sentiment=0.1,
            action=Action.WATCH,
            confidence=1.2,
            decision_trace=DecisionTrace(
                evidence_used=[],
                numeric_signals_used={},
                rules_triggered=[],
                explainability_summary="x",
            ),
            provenance_urls=[],
        )
