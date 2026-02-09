from __future__ import annotations

import json
import re
from pathlib import Path

from daily_movers.config import AppConfig
from daily_movers.models import Enrichment, Headline, TickerRow
from daily_movers.pipeline import llm
from daily_movers.pipeline.llm import OpenAIAnalyzer
from daily_movers.storage.runs import StructuredLogger


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_openai_response_normalization_accepts_variant_shapes(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "why_it_moved": "AAPL jumped after positive chatter.",
        "sentiment": 0.74,
        "action": "buy",
        "confidence": "0.88",
        "decision_trace": {
            "evidence_used": [
                "ticker.price = 189.12",
                "headline 1: Apple unveils new product line",
            ],
            "numeric_signals_used": [
                {"name": "pct_change", "value": 4.2},
                {"name": "volume", "value": 123456789},
            ],
            "rules_triggered": [
                {"id": "positive_price_impulse"},
                {"description": "elevated_volume"},
            ],
            "explainability_summary": "",
        },
        "provenance_urls": ["https://example.com/raw-source"],
    }

    def fake_post(url, headers, json, timeout):  # noqa: ANN001
        return _FakeResponse(200, {"output_text": json_module.dumps(payload)})

    # Keep a direct alias so the monkeypatched function can still serialize JSON.
    json_module = json
    monkeypatch.setattr(llm.requests, "post", fake_post)

    row = TickerRow(
        ticker="AAPL",
        name="Apple Inc.",
        price=189.12,
        abs_change=7.63,
        pct_change=4.2,
        volume=123_456_789,
        market="us",
        ingestion_source="fixture",
    )
    enrichment = Enrichment(
        headlines=[
            Headline(
                title="Apple unveils new product line",
                url="https://news.example.com/apple-1",
                published_at="2026-02-08T10:00:00+00:00",
            )
        ],
        price_series=[176.2, 179.5, 182.1, 189.12],
    )

    analyzer = OpenAIAnalyzer(
        config=AppConfig(
            cache_dir=tmp_path / "cache",
            openai_api_key="sk-test-key",
            analysis_model="gpt-4o-mini",
        ),
        logger=StructuredLogger(path=tmp_path / "run.log", run_id="llm-test"),
    )
    analysis = analyzer.synthesize(row=row, enrichment=enrichment)

    assert analysis.model_used.startswith("openai:")
    assert analysis.action.value == "BUY"
    assert analysis.decision_trace.evidence_used
    assert isinstance(analysis.decision_trace.numeric_signals_used, dict)
    assert analysis.decision_trace.rules_triggered
    sentence_count = len([s for s in re.split(r"(?<=[.!?])\s+", analysis.why_it_moved) if s.strip()])
    assert sentence_count == 2
    assert "https://finance.yahoo.com/quote/AAPL" in analysis.provenance_urls


def test_safe_openai_error_redacts_key_text() -> None:
    response = _FakeResponse(
        401,
        {
            "error": {
                "message": "Incorrect API key provided: sk-abc123",
                "type": "invalid_request_error",
                "code": "invalid_api_key",
            }
        },
    )
    assert llm._safe_openai_error(response) == "OpenAI authentication failed (invalid API key)"
