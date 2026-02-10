from __future__ import annotations

"""Core data models for the pipeline.

Hierarchy:
- TickerRow: raw ingestion result (symbol + price/volume deltas)
- Enrichment: per-ticker supporting evidence (headlines, sector, price series)
- Analysis: synthesized recommendation (action, sentiment, confidence, explanation)
- ReportRow: combines all of the above + HITL flags

All models use Pydantic for validation and serialization.
"""

from datetime import datetime, timezone
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Action(str, Enum):
    """Recommendation action (BUY/WATCH/SELL).
    
    Str subclass so it serializes cleanly to JSON without custom encoders.
    """
    BUY = "BUY"
    WATCH = "WATCH"
    SELL = "SELL"


class ErrorInfo(BaseModel):
    stage: str
    error_type: str
    error_message: str
    url: str | None = None
    fallback_used: bool = False


class Headline(BaseModel):
    title: str
    url: str
    published_at: str | None = None


class TickerRow(BaseModel):
    """Raw ingestion output for one ticker.
    
    Contains price/volume deltas and metadata. Failures during ingestion are
    captured in the errors list so the pipeline can continue.
    """
    ticker: str
    name: str | None = None
    price: float | None = None
    abs_change: float | None = None
    pct_change: float | None = None
    volume: float | None = None
    currency: str | None = None
    exchange: str | None = None
    market: str | None = None
    ingestion_source: str
    ingestion_fallback_used: bool = False
    errors: list[ErrorInfo] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def _ticker_upper(cls, value: str) -> str:
        v = value.strip().upper()
        if not v:
            raise ValueError("ticker cannot be empty")
        return v


class Enrichment(BaseModel):
    """Best-effort evidence gathered per ticker.
    
    All fields are optional. Enrichment failures are recorded in errors but
    don't block the run.
    """
    sector: str | None = None
    industry: str | None = None
    earnings_date: str | None = None
    headlines: list[Headline] = Field(default_factory=list)
    price_series: list[float] = Field(default_factory=list)
    open_price: float | None = None
    close_price: float | None = None
    errors: list[ErrorInfo] = Field(default_factory=list)


class DecisionTrace(BaseModel):
    evidence_used: list[Headline] = Field(default_factory=list)
    numeric_signals_used: dict[str, Any] = Field(default_factory=dict)
    rules_triggered: list[str] = Field(default_factory=list)
    explainability_summary: str


class Analysis(BaseModel):
    """Synthesized recommendation for one ticker.
    
    Produced by the analysis layer (LangGraph agent → OpenAI fallback → heuristics).
    Always includes explainability traces and provenance URLs for audit/debugging.
    """
    why_it_moved: str
    sentiment: float
    action: Action
    confidence: float
    decision_trace: DecisionTrace
    provenance_urls: list[str] = Field(default_factory=list)
    model_used: str = "heuristics"
    errors: list[ErrorInfo] = Field(default_factory=list)

    @field_validator("sentiment")
    @classmethod
    def _sentiment_range(cls, value: float) -> float:
        if value < -1 or value > 1:
            raise ValueError("sentiment must be in [-1, 1]")
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("confidence must be in [0, 1]")
        return value


class ReportRow(BaseModel):
    """Complete output for one ticker (ingestion + enrichment + analysis + HITL).
    
    This is the final structure that gets rendered into HTML/Excel/JSONL.
    """
    ticker: TickerRow
    enrichment: Enrichment
    analysis: Analysis
    needs_review: bool = False
    needs_review_reason: list[str] = Field(default_factory=list)
    recommendation_tags: list[str] = Field(default_factory=list)
    status: str = "ok"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def all_errors(self) -> list[ErrorInfo]:
        return [*self.ticker.errors, *self.enrichment.errors, *self.analysis.errors]

    def to_archive_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker.model_dump(),
            "enrichment": self.enrichment.model_dump(),
            "analysis": self.analysis.model_dump(),
            "needs_review": self.needs_review,
            "needs_review_reason": self.needs_review_reason,
            "recommendation_tags": self.recommendation_tags,
            "status": self.status,
            "created_at": self.created_at,
        }

    def to_flat_dict(self) -> dict[str, Any]:
        top_headline = self.enrichment.headlines[0] if self.enrichment.headlines else None
        evidence_titles = "; ".join(
            h.title for h in self.analysis.decision_trace.evidence_used if h.title
        )
        rules_triggered = "; ".join(self.analysis.decision_trace.rules_triggered)
        numeric_signals = json.dumps(
            self.analysis.decision_trace.numeric_signals_used,
            ensure_ascii=True,
        )
        return {
            "ticker": self.ticker.ticker,
            "name": self.ticker.name,
            "open_price": self.enrichment.open_price,
            "close_price": self.enrichment.close_price,
            "price": self.ticker.price,
            "abs_change": self.ticker.abs_change,
            "pct_change": self.ticker.pct_change,
            "volume": self.ticker.volume,
            "currency": self.ticker.currency,
            "exchange": self.ticker.exchange,
            "sector": self.enrichment.sector,
            "industry": self.enrichment.industry,
            "earnings_date": self.enrichment.earnings_date,
            "action": self.analysis.action.value,
            "confidence": self.analysis.confidence,
            "sentiment": self.analysis.sentiment,
            "needs_review": self.needs_review,
            "needs_review_reason": "; ".join(self.needs_review_reason),
            "why_it_moved": self.analysis.why_it_moved,
            "top_headline": top_headline.title if top_headline else None,
            "headline_url": top_headline.url if top_headline else None,
            "trend_points": self.enrichment.price_series,
            "decision_trace": self.analysis.decision_trace.explainability_summary,
            "rules_triggered": rules_triggered,
            "evidence_titles": evidence_titles,
            "numeric_signals": numeric_signals,
            "provenance_urls": ", ".join(self.analysis.provenance_urls),
            "recommendation_tags": ", ".join(self.recommendation_tags),
            "errors": "; ".join(
                f"{e.stage}:{e.error_type}:{e.error_message}" for e in self.all_errors()
            ),
        }


class RunArtifacts(BaseModel):
    status: str
    summary: dict[str, Any]
    paths: dict[str, str]


class RunMeta(BaseModel):
    run_id: str
    requested_date: str
    mode: str
    region: str
    source: str | None = None
    top: int
    out_dir: str
    started_at: str
    ended_at: str
    status: str
    summary: dict[str, Any]
    email: dict[str, Any]
    timings_ms: dict[str, int] = Field(default_factory=dict)


def apply_hitl_rules(report: ReportRow) -> ReportRow:
    reasons = list(report.needs_review_reason)

    confidence = report.analysis.confidence
    pct_change = report.ticker.pct_change
    has_headlines = bool(report.enrichment.headlines)
    fallback_used = report.ticker.ingestion_fallback_used

    if confidence < 0.75:
        reasons.append("confidence_below_threshold")
    if pct_change is not None and abs(pct_change) > 15:
        reasons.append("extreme_percent_change")
    if not has_headlines:
        reasons.append("missing_headlines")
    if fallback_used:
        reasons.append("ingestion_fallback_used")
    if report.all_errors():
        reasons.append("has_explicit_errors")

    unique = sorted(set(reasons))
    report.needs_review_reason = unique
    report.needs_review = bool(unique)
    if report.status == "ok" and report.all_errors():
        report.status = "partial"
    return report


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
