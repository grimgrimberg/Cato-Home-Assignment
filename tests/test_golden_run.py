from __future__ import annotations

import json
from pathlib import Path

from daily_movers.config import AppConfig
from daily_movers.models import Enrichment, Headline, TickerRow
from daily_movers.pipeline.orchestrator import RunRequest, run_daily_movers


def test_golden_run_generates_all_artifacts(tmp_path: Path, monkeypatch) -> None:
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
            ),
            TickerRow(
                ticker="TEVA.TA",
                name="Teva",
                price=10820,
                abs_change=140,
                pct_change=1.31,
                volume=4_450_021,
                market="il",
                ingestion_source="fixture",
            ),
        ][:top_n]

    def fake_enrich_ticker(*, row, client, logger):
        return Enrichment(
            sector="Technology" if row.ticker == "AAPL" else "Healthcare",
            industry="Consumer Electronics" if row.ticker == "AAPL" else "Drug Manufacturers",
            earnings_date="Apr 30, 2026",
            headlines=[
                Headline(
                    title=f"{row.ticker} headline",
                    url=f"https://example.com/{row.ticker.lower()}",
                    published_at="2026-02-08T00:00:00+00:00",
                )
            ],
            price_series=[100, 102, 101, 104],
        )

    monkeypatch.setattr(orchestrator, "get_movers", fake_get_movers)
    monkeypatch.setattr(orchestrator, "enrich_ticker", fake_enrich_ticker)

    out_dir = tmp_path / "run"
    request = RunRequest(
        date="2026-02-08",
        mode="movers",
        region="us",
        top=20,
        out_dir=str(out_dir),
    )
    config = AppConfig(
        cache_dir=tmp_path / "cache",
        openai_api_key=None,
        from_email="from@example.com",
        self_email="self@example.com",
    )

    artifacts = run_daily_movers(request=request, config=config)

    assert artifacts.status in {"success", "partial_success"}

    expected = [
        out_dir / "report.xlsx",
        out_dir / "digest.html",
        out_dir / "digest.eml",
        out_dir / "archive.jsonl",
        out_dir / "run.json",
        out_dir / "run.log",
    ]
    for path in expected:
        assert path.exists(), f"missing artifact: {path}"

    with (out_dir / "archive.jsonl").open("r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 2

    run_meta = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert run_meta["requested_date"] == "2026-02-08"
    assert run_meta["summary"]["processed"] == 2
