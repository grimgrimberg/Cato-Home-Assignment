from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from daily_movers.errors import IngestionError
from daily_movers.models import TickerRow
from daily_movers.providers import yahoo_movers
from daily_movers.storage.runs import StructuredLogger


class FakeHttpClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        stage: str,
        logger: StructuredLogger,
    ) -> dict[str, Any]:
        self.calls.append((url, dict(params or {})))
        return self.payload

    def get_text(self, url: str, *, stage: str, logger: StructuredLogger) -> str:
        raise AssertionError("HTML fallback should not be used in this test")


def test_get_us_movers_uses_screener_json_and_parses_quotes(tmp_path: Path) -> None:
    payload = {
        "finance": {
            "result": [
                {
                    "quotes": [
                        {
                            "symbol": "NVDA",
                            "shortName": "NVIDIA",
                            "regularMarketPrice": {"raw": 700.0},
                            "regularMarketChange": {"raw": 10.0},
                            "regularMarketChangePercent": {"raw": 1.45},
                            "regularMarketVolume": {"raw": 12345678},
                            "currency": "USD",
                            "exchange": "NMS",
                        },
                        {
                            "symbol": "AMZN",
                            "shortName": "Amazon",
                            "regularMarketPrice": {"raw": 160.0},
                            "regularMarketChange": {"raw": -1.0},
                            "regularMarketChangePercent": {"raw": -0.62},
                            "regularMarketVolume": {"raw": 22222222},
                            "currency": "USD",
                            "exchange": "NMS",
                        },
                    ]
                }
            ]
        }
    }

    client = FakeHttpClient(payload)
    logger = StructuredLogger(path=tmp_path / "run.log", run_id="test")

    rows = yahoo_movers.get_us_movers(top_n=2, client=client, logger=logger)

    assert len(rows) == 2
    assert client.calls, "expected at least one client.get_json call"
    url, params = client.calls[0]
    assert url == yahoo_movers.US_SCREENER_URL
    assert params["scrIds"] == "most_actives"
    assert params["count"] == "2"
    assert rows[0].ingestion_source == "yahoo_screener_json"
    assert rows[0].ingestion_fallback_used is False


def test_get_movers_source_validation(tmp_path: Path) -> None:
    logger = StructuredLogger(path=tmp_path / "run.log", run_id="test")

    with pytest.raises(IngestionError):
        yahoo_movers.get_movers(region="us", source="bogus", top_n=5, client=FakeHttpClient({}), logger=logger)

    with pytest.raises(IngestionError):
        yahoo_movers.get_movers(region="il", source="most-active", top_n=5, client=FakeHttpClient({}), logger=logger)


def test_get_movers_us_universe_routes_to_chart_builder(monkeypatch, tmp_path: Path) -> None:
    logger = StructuredLogger(path=tmp_path / "run.log", run_id="test")

    seen: dict[str, object] = {}

    def fake_build_rows_from_symbols(*, symbols, top_n, source, market, client, logger):
        seen["symbols"] = symbols
        seen["top_n"] = top_n
        seen["source"] = source
        seen["market"] = market
        return [
            TickerRow(ticker="AAA", pct_change=2.0, volume=1000, market="us", ingestion_source=source),
            TickerRow(ticker="BBB", pct_change=-10.0, volume=9999, market="us", ingestion_source=source),
        ]

    monkeypatch.setattr(yahoo_movers, "build_rows_from_symbols", fake_build_rows_from_symbols)

    rows = yahoo_movers.get_movers(
        region="us",
        source="universe",
        top_n=1,
        client=FakeHttpClient({}),
        logger=logger,
    )

    assert seen["market"] == "us"
    assert seen["source"] == "yahoo_chart_us_universe"
    assert isinstance(seen["symbols"], list) and len(seen["symbols"]) >= 1

    # Ranking is by absolute pct_change desc then volume desc
    assert rows[0].ticker == "BBB"
