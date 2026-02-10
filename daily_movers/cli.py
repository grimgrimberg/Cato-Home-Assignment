from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from datetime import date
from pathlib import Path

from daily_movers.config import load_config
from daily_movers.pipeline.orchestrator import RunRequest, run_daily_movers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="daily_movers", description="Daily Movers Assistant")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run daily movers pipeline")
    run_parser.add_argument("--date", default=date.today().isoformat(), help="report date label (YYYY-MM-DD)")
    run_parser.add_argument("--mode", choices=["movers", "watchlist"], default="movers")
    run_parser.add_argument(
        "--source",
        choices=["auto", "most-active", "universe"],
        default="auto",
        help="movers source selector (auto=region default; most-active=Yahoo most_actives screener; universe=static universe)",
    )
    run_parser.add_argument("--top", type=int, default=20)
    run_parser.add_argument("--region", choices=["us", "il", "uk", "eu", "crypto"], default="us")
    run_parser.add_argument("--watchlist", default=None, help="path to watchlist YAML/JSON")
    run_parser.add_argument("--out", default=None, help="output run directory")
    run_parser.add_argument("--send-email", action="store_true", help="send email when SMTP is configured")
    run_parser.add_argument(
        "--no-open",
        action="store_true",
        help="do not auto-open digest.html in your default browser",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    Parses args, builds a RunRequest, runs the orchestrator, prints the artifact
    paths as JSON, and (by default) opens the HTML digest in a browser.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "run":
        parser.print_help()
        return 1

    out = args.out or f"runs/{args.date}"

    cfg = load_config()
    request = RunRequest(
        date=args.date,
        mode=args.mode,
        region=args.region,
        source=args.source,
        top=args.top,
        watchlist=args.watchlist,
        out_dir=out,
        send_email=bool(args.send_email),
    )
    artifacts = run_daily_movers(request=request, config=cfg)
    print(json.dumps(artifacts.model_dump(), indent=2, ensure_ascii=True))
    if not args.no_open:
        _open_digest_html(artifacts.paths.get("digest_html"))
    return 0


def _open_digest_html(path: str | None) -> None:
    """Best-effort: open digest.html in the default browser.

    Failure to open is not fatal; the artifact is still written to disk.
    """
    if not path:
        return
    html_path = Path(path)
    if not html_path.exists():
        return
    try:
        webbrowser.open(html_path.resolve().as_uri(), new=2)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[daily_movers] unable to auto-open digest: {exc}",
            file=sys.stderr,
        )
