from __future__ import annotations

from pathlib import Path

import pytest

from daily_movers.models import RunArtifacts


def test_uipath_adapter_success_coerces_and_forwards(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from daily_movers.adapters import uipath

    captured = {}

    def fake_run_pipeline(*, request, config):  # noqa: ANN001
        captured["request"] = request
        return RunArtifacts(
            status="success",
            summary={"processed": 1, "needs_review": 0, "error_rows": 0},
            paths={
                "digest_html": str(tmp_path / "digest.html"),
                "report_xlsx": str(tmp_path / "report.xlsx"),
                "digest_eml": str(tmp_path / "digest.eml"),
                "archive_jsonl": str(tmp_path / "archive.jsonl"),
                "run_json": str(tmp_path / "run.json"),
                "run_log": str(tmp_path / "run.log"),
            },
        )

    monkeypatch.setattr(uipath, "run_pipeline", fake_run_pipeline)

    out_dir = str(tmp_path / "out")
    result = uipath.run_daily_movers(
        out_dir,
        date="2026-02-09",
        mode="movers",
        region="us",
        source="most-active",
        top="5",
        send_email="False",
    )

    assert result["status"] == "success"
    assert isinstance(result["summary"], dict)
    assert isinstance(result["paths"], dict)

    req = captured["request"]
    assert req.date == "2026-02-09"
    assert req.mode == "movers"
    assert req.region == "us"
    assert req.source == "most-active"
    assert req.top == 5
    assert req.watchlist is None
    assert req.send_email is False
    assert req.out_dir == out_dir


def test_uipath_adapter_rejects_unknown_kwargs(tmp_path: Path) -> None:
    from daily_movers.adapters import uipath

    with pytest.raises(TypeError):
        uipath.run_daily_movers(str(tmp_path / "out"), banana=123)  # type: ignore[call-arg]


def test_uipath_adapter_watchlist_requires_path(tmp_path: Path) -> None:
    from daily_movers.adapters import uipath

    result = uipath.run_daily_movers(
        str(tmp_path / "out"),
        mode="watchlist",
        watchlist=None,
    )
    assert result["status"] == "failed"
    assert "watchlist is required" in result["summary"]["error_message"]


def test_uipath_adapter_watchlist_must_exist(tmp_path: Path) -> None:
    from daily_movers.adapters import uipath

    result = uipath.run_daily_movers(
        str(tmp_path / "out"),
        mode="watchlist",
        watchlist=str(tmp_path / "missing.yaml"),
    )
    assert result["status"] == "failed"
    assert "watchlist path not found" in result["summary"]["error_message"]


def test_uipath_adapter_invalid_region_fails(tmp_path: Path) -> None:
    from daily_movers.adapters import uipath

    result = uipath.run_daily_movers(
        str(tmp_path / "out"),
        region="mars",
    )
    assert result["status"] == "failed"
    assert "region must be one of" in result["summary"]["error_message"]


def test_uipath_adapter_invalid_date_fails(tmp_path: Path) -> None:
    from daily_movers.adapters import uipath

    result = uipath.run_daily_movers(
        str(tmp_path / "out"),
        date="2026-13-40",
    )
    assert result["status"] == "failed"
    assert "date must be a YYYY-MM-DD" in result["summary"]["error_message"]


def test_uipath_adapter_send_email_string_true(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from daily_movers.adapters import uipath

    captured = {}

    def fake_run_pipeline(*, request, config):  # noqa: ANN001
        captured["send_email"] = request.send_email
        return RunArtifacts(status="success", summary={}, paths={})

    monkeypatch.setattr(uipath, "run_pipeline", fake_run_pipeline)

    result = uipath.run_daily_movers(str(tmp_path / "out"), send_email="1")
    assert result["status"] == "success"
    assert captured["send_email"] is True
