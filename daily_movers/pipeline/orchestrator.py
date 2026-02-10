from __future__ import annotations

"""Pipeline orchestrator (the main entrypoint behind the CLI).

This module is intentionally boring: it wires together the subsystems and ensures
every run produces a complete set of local artifacts even when upstream services
fail.

High-level flow (one CLI invocation → one run folder):

1) Ingest tickers (movers list or watchlist)
2) For each ticker (in parallel): enrich → analyze → critic/HITL
3) Render outputs: HTML digest + Excel report + JSONL archive + run metadata
4) Build an EML message (always) and optionally send it via SMTP

Key behavior:
- The run does not crash on per-ticker failures; errors are embedded into rows.
- Analysis uses a tiered strategy: heuristics baseline → LangGraph agent → raw
    OpenAI fallback → heuristics.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from daily_movers.config import AppConfig, load_config
from daily_movers.email.eml_backend import EmlBackend
from daily_movers.email.smtp_backend import SmtpBackend
from daily_movers.errors import AnalysisError, EmailDeliveryError, IngestionError
from daily_movers.models import (
    Analysis,
    Enrichment,
    ErrorInfo,
    ReportRow,
    RunArtifacts,
    RunMeta,
    TickerRow,
    apply_hitl_rules,
    utc_now_iso,
)
from daily_movers.pipeline.critic import critic_review
from daily_movers.pipeline.heuristics import analyze_with_heuristics
from daily_movers.pipeline.llm import OpenAIAnalyzer
from daily_movers.pipeline.agent import run_agent_analysis
from daily_movers.providers.yahoo_movers import get_movers, get_watchlist_rows
from daily_movers.providers.yahoo_ticker import enrich_ticker
from daily_movers.render.excel import write_excel_report
from daily_movers.render.html import build_digest_html
from daily_movers.storage.cache import CachedHttpClient
from daily_movers.storage.runs import StructuredLogger, ensure_run_dir, write_json, write_jsonl


@dataclass
class RunRequest:
    date: str
    mode: str = "movers"
    region: str = "us"
    source: str = "auto"
    top: int = 20
    watchlist: str | None = None
    out_dir: str = "runs/latest"
    send_email: bool = False


def run_daily_movers(*, request: RunRequest, config: AppConfig | None = None) -> RunArtifacts:
    """Run the full pipeline once and write artifacts to the run directory.

    This is the function the CLI calls.

    Returns a RunArtifacts object containing:
    - status + summary counts
    - absolute/relative paths to the generated outputs
    """
    cfg = config or load_config()
    run_id = uuid4().hex[:12]
    started_at = utc_now_iso()

    out_dir = ensure_run_dir(Path(request.out_dir))
    logger = StructuredLogger(path=out_dir / "run.log", run_id=run_id, log_level=cfg.log_level)
    http_client = CachedHttpClient(
        cache_dir=cfg.cache_dir,
        default_ttl_seconds=cfg.cache_ttl_seconds,
        timeout_seconds=cfg.request_timeout_seconds,
        user_agent=cfg.user_agent,
        max_requests_per_host=cfg.max_requests_per_host,
    )
    llm = OpenAIAnalyzer(config=cfg, logger=logger)
    eml_backend = EmlBackend(logger=logger)
    smtp_backend = SmtpBackend(config=cfg, logger=logger)

    logger.info(
        "run_started",
        stage="orchestrator",
        status="ok",
        mode=request.mode,
        region=request.region,
        source=request.source,
        top=request.top,
        out_dir=str(out_dir),
    )

    total_start = time.perf_counter()

    ingest_start = time.perf_counter()
    ticker_rows = _ingest_rows(request=request, client=http_client, logger=logger)
    ingest_ms = int((time.perf_counter() - ingest_start) * 1000)

    process_start = time.perf_counter()
    report_rows = _process_rows(
        rows=ticker_rows,
        client=http_client,
        logger=logger,
        llm=llm,
        config=cfg,
        max_workers=cfg.max_workers,
    )
    process_ms = int((time.perf_counter() - process_start) * 1000)

    if request.mode == "movers":
        report_rows.sort(
            key=lambda r: (
                r.ticker.pct_change if r.ticker.pct_change is not None else float("-inf"),
                r.ticker.volume if r.ticker.volume is not None else float("-inf"),
            ),
            reverse=True,
        )

    archive_path = out_dir / "archive.jsonl"
    write_jsonl(
        archive_path,
        [
            {
                "run_id": run_id,
                "requested_date": request.date,
                "mode": request.mode,
                "region": request.region,
                **row.to_archive_dict(),
            }
            for row in report_rows
        ],
    )

    render_start = time.perf_counter()
    digest_html = build_digest_html(
        rows=report_rows,
        run_meta={
            "run_id": run_id,
            "requested_date": request.date,
            "mode": request.mode,
            "region": request.region,
            "source": request.source,
            "top": request.top,
        },
    )
    digest_path = out_dir / "digest.html"
    digest_path.write_text(digest_html, encoding="utf-8")

    excel_path = out_dir / "report.xlsx"
    write_excel_report(rows=report_rows, out_path=excel_path)
    render_ms = int((time.perf_counter() - render_start) * 1000)

    email_start = time.perf_counter()
    from_email = cfg.from_email or "daily-movers@localhost"
    to_email = cfg.self_email or from_email
    subject = f"Daily Movers Digest - {request.date}"
    eml_message = eml_backend.build_message(
        subject=subject,
        html_body=digest_html,
        from_email=from_email,
        to_email=to_email,
    )
    eml_path = out_dir / "digest.eml"
    eml_backend.write_message(message=eml_message, out_path=eml_path)

    email_meta: dict[str, Any] = {
        "attempted": bool(request.send_email),
        "sent": False,
        "status": "eml_only",
        "error": None,
        "backend": "eml",
    }

    if request.send_email:
        if smtp_backend.can_send():
            try:
                smtp_backend.send_message(message=eml_message)
                email_meta = {
                    "attempted": True,
                    "sent": True,
                    "status": "sent",
                    "error": None,
                    "backend": "smtp",
                }
            except EmailDeliveryError as exc:
                email_meta = {
                    "attempted": True,
                    "sent": False,
                    "status": "failed",
                    "error": str(exc),
                    "backend": "smtp",
                }
                logger.error(
                    "email_send_failed",
                    stage="email",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
        else:
            email_meta = {
                "attempted": True,
                "sent": False,
                "status": "skipped_missing_credentials",
                "error": "SMTP credentials not fully configured",
                "backend": "smtp",
            }
            logger.warning(
                "email_send_skipped",
                stage="email",
                error_type="MissingCredentials",
                error_message="SMTP credentials not fully configured",
            )
    email_ms = int((time.perf_counter() - email_start) * 1000)

    summary = _build_summary(
        report_rows=report_rows,
        email_meta=email_meta,
        openai_attempted=llm.enabled,
    )
    status = _resolve_run_status(report_rows=report_rows, email_meta=email_meta)
    ended_at = utc_now_iso()
    total_ms = int((time.perf_counter() - total_start) * 1000)

    run_meta = RunMeta(
        run_id=run_id,
        requested_date=request.date,
        mode=request.mode,
        region=request.region,
        source=request.source,
        top=request.top,
        out_dir=str(out_dir),
        started_at=started_at,
        ended_at=ended_at,
        status=status,
        summary=summary,
        email=email_meta,
        timings_ms={
            "ingestion": ingest_ms,
            "processing": process_ms,
            "rendering": render_ms,
            "email": email_ms,
            "total": total_ms,
        },
    )

    run_json_path = out_dir / "run.json"
    write_json(run_json_path, run_meta.model_dump())

    logger.info(
        "run_completed",
        stage="orchestrator",
        status=status,
        processed=summary["processed"],
        needs_review=summary["needs_review"],
        error_rows=summary["error_rows"],
    )

    paths = {
        "report_xlsx": str(excel_path),
        "digest_html": str(digest_path),
        "digest_eml": str(eml_path),
        "archive_jsonl": str(archive_path),
        "run_json": str(run_json_path),
        "run_log": str(out_dir / "run.log"),
    }
    return RunArtifacts(status=status, summary=summary, paths=paths)


def _ingest_rows(
    *,
    request: RunRequest,
    client: CachedHttpClient,
    logger: StructuredLogger,
) -> list[TickerRow]:
    try:
        if request.mode == "watchlist":
            if not request.watchlist:
                raise IngestionError(
                    "watchlist mode requires --watchlist",
                    stage="ingestion",
                    url=None,
                )
            rows = get_watchlist_rows(
                watchlist_path=Path(request.watchlist),
                top_n=request.top,
                client=client,
                logger=logger,
            )
        else:
            rows = get_movers(
                region=request.region,
                source=request.source,
                top_n=request.top,
                client=client,
                logger=logger,
            )

        logger.info("ingestion_completed", stage="ingestion", status="ok", count=len(rows))
        return rows
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "ingestion_failed",
            stage="ingestion",
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )
        return []


def _process_rows(
    *,
    rows: list[TickerRow],
    client: CachedHttpClient,
    logger: StructuredLogger,
    llm: OpenAIAnalyzer,
    config: AppConfig,
    max_workers: int,
) -> list[ReportRow]:
    if not rows:
        return []

    results: list[ReportRow | None] = [None] * len(rows)

    # Per-ticker processing is embarrassingly parallel (HTTP-bound), so we use a
    # thread pool. A separate per-host semaphore in CachedHttpClient prevents
    # hammering Yahoo with too many concurrent requests.
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(_process_single_row, idx, row, client, logger, llm, config): idx
            for idx, row in enumerate(rows)
        }
        per_row_timeout = max(60, config.request_timeout_seconds * 6)
        batches = max(1, (len(rows) + max_workers - 1) // max_workers)
        overall_timeout = per_row_timeout * batches
        completed: set[int] = set()
        try:
            for future in as_completed(future_to_idx, timeout=overall_timeout):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:  # noqa: BLE001
                    fallback_row = rows[idx]
                    analysis = analyze_with_heuristics(
                        row=fallback_row,
                        enrichment=Enrichment(),
                    )
                    analysis.errors.append(
                        ErrorInfo(
                            stage="analysis",
                            error_type=exc.__class__.__name__,
                            error_message=str(exc),
                        )
                    )
                    report = ReportRow(
                        ticker=fallback_row,
                        enrichment=Enrichment(),
                        analysis=analysis,
                        status="partial",
                        needs_review=True,
                        needs_review_reason=["processing_exception"],
                    )
                    results[idx] = apply_hitl_rules(report)
                completed.add(idx)
        except TimeoutError:
            for idx, row in enumerate(rows):
                if idx in completed:
                    continue
                analysis = analyze_with_heuristics(
                    row=row,
                    enrichment=Enrichment(),
                )
                analysis.errors.append(
                    ErrorInfo(
                        stage="analysis",
                        error_type="TimeoutError",
                        error_message="processing timed out",
                    )
                )
                report = ReportRow(
                    ticker=row,
                    enrichment=Enrichment(),
                    analysis=analysis,
                    status="partial",
                    needs_review=True,
                    needs_review_reason=["processing_timeout"],
                )
                results[idx] = apply_hitl_rules(report)

    return [r for r in results if r is not None]


def _process_single_row(
    idx: int,
    row: TickerRow,
    client: CachedHttpClient,
    logger: StructuredLogger,
    llm: OpenAIAnalyzer,
    config: AppConfig,
) -> ReportRow:
    logger.info("ticker_processing_started", stage="orchestrator", symbol=row.ticker, index=idx)

    enrichment = enrich_ticker(row=row, client=client, logger=logger)
    heuristic_analysis = analyze_with_heuristics(row=row, enrichment=enrichment)
    analysis = heuristic_analysis
    recommendation_tags: list[str] = []

    # Analysis strategy (in priority order):
    # 1) LangGraph agent: multi-node reasoning with guardrails. It may use OpenAI
    #    if configured, but still works in heuristic mode.
    # 2) Raw OpenAI fallback: only when the agent failed and OPENAI_API_KEY exists.
    # 3) Deterministic heuristics: always available baseline.
    #
    # This arrangement keeps the pipeline reliable: you always get a digest even
    # with no API keys or when upstream dependencies are flaky.

    # --- Path 1: LangGraph agent (primary) ---
    agent_succeeded = False
    try:
        agent_analysis = run_agent_analysis(
            row=row,
            enrichment=enrichment,
            config=config,
            run_logger=logger,
        )
        analysis = agent_analysis
        agent_succeeded = True
        # Tags are derived from the final analysis; this is intentionally
        # deterministic so Excel/HTML stay consistent across model variants.
        recommendation_tags = _derive_recommendation_tags(row, analysis)
        logger.info(
            "agent_analysis_used",
            stage="analysis",
            symbol=row.ticker,
            model_used=analysis.model_used,
        )
    except Exception as exc:
        logger.warning(
            "agent_analysis_failed",
            stage="analysis",
            symbol=row.ticker,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            fallback_used=True,
        )

    # --- Path 2: Raw OpenAI fallback (secondary) ---
    if not agent_succeeded and llm.enabled:
        try:
            analysis = llm.synthesize(row=row, enrichment=enrichment)
            recommendation_tags = _derive_recommendation_tags(row, analysis)
        except AnalysisError as exc:
            analysis = heuristic_analysis
            if "openai_fallback_used" not in analysis.decision_trace.rules_triggered:
                analysis.decision_trace.rules_triggered.append("openai_fallback_used")
            logger.warning(
                "analysis_fallback_to_heuristics",
                stage="analysis",
                symbol=row.ticker,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                url=exc.url,
                fallback_used=True,
            )

    # --- Path 3: Heuristics already assigned as default ---
    if not recommendation_tags:
        recommendation_tags = _derive_recommendation_tags(row, analysis)

    analysis, critic_flags = critic_review(row=row, enrichment=enrichment, analysis=analysis)

    report = ReportRow(
        ticker=row,
        enrichment=enrichment,
        analysis=analysis,
        needs_review_reason=critic_flags,
        recommendation_tags=recommendation_tags,
        status="ok",
    )
    report = apply_hitl_rules(report)
    if report.all_errors():
        report.status = "partial"

    logger.info(
        "ticker_processing_completed",
        stage="orchestrator",
        symbol=row.ticker,
        status=report.status,
        needs_review=report.needs_review,
    )
    return report


def _derive_recommendation_tags(row: TickerRow, analysis: Analysis) -> list[str]:
    """Derive recommendation tags from analysis results."""
    tags: list[str] = []
    pct = float(row.pct_change or 0)
    volume = float(row.volume or 0)
    confidence = analysis.confidence
    sentiment = analysis.sentiment
    action = analysis.action.value

    if action == "BUY" and confidence >= 0.75 and sentiment > 0.3:
        tags.append("top_pick_candidate")
    if sentiment > 0.15 and confidence < 0.75 and action in ("BUY", "WATCH"):
        tags.append("most_potential_candidate")
    if pct < -5 and volume >= 5_000_000:
        tags.append("contrarian_bounce_candidate")
    if pct > 3 and volume >= 2_000_000:
        tags.append("momentum_signal")
    if not tags:
        tags.append("standard")
    return tags


def _build_summary(
    *,
    report_rows: list[ReportRow],
    email_meta: dict[str, Any],
    openai_attempted: bool,
) -> dict[str, Any]:
    error_rows = sum(1 for row in report_rows if row.all_errors())
    needs_review = sum(1 for row in report_rows if row.needs_review)
    fallback_rows = sum(1 for row in report_rows if row.ticker.ingestion_fallback_used)
    openai_used_rows = sum(
        1 for row in report_rows
        if "openai" in (row.analysis.model_used or "")
    )
    openai_fallback_rows = sum(
        1 for row in report_rows if "openai_fallback_used" in row.analysis.decision_trace.rules_triggered
    )
    langgraph_rows = sum(1 for row in report_rows if "langgraph" in (row.analysis.model_used or ""))
    top_pick_rows = sum(1 for row in report_rows if "top_pick_candidate" in row.recommendation_tags)
    most_potential_rows = sum(1 for row in report_rows if "most_potential_candidate" in row.recommendation_tags)

    # Identify the single top pick and most potential
    top_pick = None
    most_potential = None
    for row in report_rows:
        if "top_pick_candidate" in row.recommendation_tags:
            if top_pick is None or row.analysis.confidence > top_pick.analysis.confidence:
                top_pick = row
        if "most_potential_candidate" in row.recommendation_tags:
            if most_potential is None or (row.analysis.sentiment > most_potential.analysis.sentiment):
                most_potential = row

    return {
        "processed": len(report_rows),
        "error_rows": error_rows,
        "needs_review": needs_review,
        "fallback_rows": fallback_rows,
        "email_sent": bool(email_meta.get("sent")),
        "openai_attempted": openai_attempted,
        "openai_used": openai_used_rows > 0,
        "openai_used_rows": openai_used_rows,
        "openai_fallback_rows": openai_fallback_rows,
        "langgraph_rows": langgraph_rows,
        "top_pick": top_pick.ticker.ticker if top_pick else None,
        "most_potential": most_potential.ticker.ticker if most_potential else None,
        "top_pick_count": top_pick_rows,
        "most_potential_count": most_potential_rows,
    }


def _resolve_run_status(*, report_rows: list[ReportRow], email_meta: dict[str, Any]) -> str:
    if not report_rows:
        return "failed"
    has_errors = any(row.all_errors() for row in report_rows)
    email_failed = bool(email_meta.get("attempted")) and not bool(email_meta.get("sent")) and email_meta.get("status") == "failed"
    if has_errors or email_failed:
        return "partial_success"
    return "success"
