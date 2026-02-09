from __future__ import annotations

import json
from pathlib import Path

from daily_movers.config import AppConfig
from daily_movers.errors import EnrichmentError
from daily_movers.models import Enrichment, ErrorInfo, Headline, TickerRow
from daily_movers.pipeline.orchestrator import RunRequest, run_daily_movers


def test_ralphing_handles_missing_headlines_and_weird_tickers(tmp_path: Path, monkeypatch) -> None:
    from daily_movers.pipeline import orchestrator

    def fake_get_movers(*, region, source, top_n, client, logger):
        return [
            TickerRow(
                ticker="AAPL",
                name="Apple",
                price=278,
                abs_change=2,
                pct_change=0.7,
                volume=10_000_000,
                ingestion_source="fixture",
            ),
            TickerRow(
                ticker="BAD$$$",
                name="Broken",
                ingestion_source="fixture",
                errors=[
                    ErrorInfo(
                        stage="ingestion",
                        error_type="MalformedSymbol",
                        error_message="weird ticker format",
                    )
                ],
            ),
        ][:top_n]

    def fake_enrich_ticker(*, row, client, logger):
        if row.ticker == "AAPL":
            return Enrichment(headlines=[], price_series=[1, 2, 3])
        raise EnrichmentError("rate limit", stage="enrichment", url="https://example.com")

    monkeypatch.setattr(orchestrator, "get_movers", fake_get_movers)
    monkeypatch.setattr(orchestrator, "enrich_ticker", fake_enrich_ticker)

    request = RunRequest(
        date="2026-02-08",
        mode="movers",
        top=10,
        out_dir=str(tmp_path / "ralph-run"),
    )
    config = AppConfig(cache_dir=tmp_path / "cache")

    artifacts = run_daily_movers(request=request, config=config)

    assert artifacts.status in {"success", "partial_success"}
    archive = Path(artifacts.paths["archive_jsonl"])  # type: ignore[index]
    rows = [json.loads(line) for line in archive.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert any(r["needs_review"] for r in rows)
    assert any(r["ticker"]["errors"] for r in rows)


def test_ralphing_email_failure_is_nonfatal(tmp_path: Path, monkeypatch) -> None:
    from daily_movers.pipeline import orchestrator

    def fake_get_movers(*, region, source, top_n, client, logger):
        return [
            TickerRow(
                ticker="MSFT",
                name="Microsoft",
                price=401,
                abs_change=7,
                pct_change=1.8,
                volume=12_000_000,
                ingestion_source="fixture",
            )
        ]

    def fake_enrich_ticker(*, row, client, logger):
        return Enrichment(
            headlines=[Headline(title="MSFT signal", url="https://example.com/msft")],
            price_series=[10, 11, 12],
        )

    monkeypatch.setattr(orchestrator, "get_movers", fake_get_movers)
    monkeypatch.setattr(orchestrator, "enrich_ticker", fake_enrich_ticker)

    request = RunRequest(
        date="2026-02-08",
        mode="movers",
        top=1,
        out_dir=str(tmp_path / "email-run"),
        send_email=True,
    )
    config = AppConfig(cache_dir=tmp_path / "cache")

    artifacts = run_daily_movers(request=request, config=config)
    run_json_path = Path(artifacts.paths["run_json"])  # type: ignore[index]
    run_meta = json.loads(run_json_path.read_text(encoding="utf-8"))

    assert run_meta["email"]["attempted"] is True
    assert run_meta["email"]["sent"] is False
    assert Path(artifacts.paths["digest_eml"]).exists()  # type: ignore[index]
