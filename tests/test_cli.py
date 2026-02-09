from __future__ import annotations

from pathlib import Path

from daily_movers.models import RunArtifacts


def test_cli_auto_opens_digest_by_default(tmp_path: Path, monkeypatch) -> None:
    import daily_movers.cli as cli

    opened: dict[str, str] = {}
    digest = tmp_path / "digest.html"
    digest.write_text("<html><body>ok</body></html>", encoding="utf-8")

    def fake_run_daily_movers(*, request, config):  # noqa: ANN001
        return RunArtifacts(
            status="success",
            summary={"processed": 1},
            paths={"digest_html": str(digest)},
        )

    def fake_open(url: str, new: int = 0) -> bool:
        opened["url"] = url
        return True

    monkeypatch.setattr(cli, "run_daily_movers", fake_run_daily_movers)
    monkeypatch.setattr(cli, "load_config", lambda: object())
    monkeypatch.setattr(cli.webbrowser, "open", fake_open)

    exit_code = cli.main(
        [
            "run",
            "--date",
            "2026-02-08",
            "--mode",
            "movers",
            "--region",
            "us",
            "--top",
            "1",
            "--out",
            str(tmp_path / "run"),
        ]
    )

    assert exit_code == 0
    assert opened["url"].startswith("file:")


def test_cli_no_open_flag_skips_auto_open(tmp_path: Path, monkeypatch) -> None:
    import daily_movers.cli as cli

    called: dict[str, bool] = {"open_called": False}
    digest = tmp_path / "digest.html"
    digest.write_text("<html><body>ok</body></html>", encoding="utf-8")

    def fake_run_daily_movers(*, request, config):  # noqa: ANN001
        return RunArtifacts(
            status="success",
            summary={"processed": 1},
            paths={"digest_html": str(digest)},
        )

    def fake_open(url: str, new: int = 0) -> bool:
        called["open_called"] = True
        return True

    monkeypatch.setattr(cli, "run_daily_movers", fake_run_daily_movers)
    monkeypatch.setattr(cli, "load_config", lambda: object())
    monkeypatch.setattr(cli.webbrowser, "open", fake_open)

    exit_code = cli.main(
        [
            "run",
            "--date",
            "2026-02-08",
            "--mode",
            "movers",
            "--region",
            "us",
            "--top",
            "1",
            "--out",
            str(tmp_path / "run"),
            "--no-open",
        ]
    )

    assert exit_code == 0
    assert called["open_called"] is False
