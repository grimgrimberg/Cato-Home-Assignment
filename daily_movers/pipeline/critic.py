from __future__ import annotations

import re

from daily_movers.models import Analysis, Enrichment, TickerRow


_FORBIDDEN_PATTERNS = [
    "chain of thought",
    "chain-of-thought",
    "step-by-step reasoning",
    "internal reasoning",
    "let me think",
]


def critic_review(*, row: TickerRow, enrichment: Enrichment, analysis: Analysis) -> tuple[Analysis, list[str]]:
    reasons: list[str] = []

    why_text = analysis.why_it_moved or ""
    lower = why_text.lower()
    if any(pattern in lower for pattern in _FORBIDDEN_PATTERNS):
        analysis.why_it_moved = (
            f"{row.ticker} moved {row.pct_change or 0:+.2f}% based on observed market signals and cited evidence only. "
            "The explanation was sanitized to remove internal reasoning language."
        )
        reasons.append("cot_language_removed")

    normalized = _force_two_sentences(analysis.why_it_moved, ticker=row.ticker, pct_change=row.pct_change or 0.0)
    if normalized != analysis.why_it_moved:
        analysis.why_it_moved = normalized
        reasons.append("why_it_moved_normalized_to_two_sentences")

    if analysis.sentiment < -1:
        analysis.sentiment = -1
        reasons.append("sentiment_clipped")
    elif analysis.sentiment > 1:
        analysis.sentiment = 1
        reasons.append("sentiment_clipped")

    if analysis.confidence < 0:
        analysis.confidence = 0
        reasons.append("confidence_clipped")
    elif analysis.confidence > 1:
        analysis.confidence = 1
        reasons.append("confidence_clipped")

    evidence_urls = [h.url for h in analysis.decision_trace.evidence_used if h.url]
    for url in evidence_urls:
        if url not in analysis.provenance_urls:
            analysis.provenance_urls.append(url)
            reasons.append("missing_provenance_url_added")

    if not analysis.decision_trace.numeric_signals_used:
        analysis.decision_trace.numeric_signals_used = {
            "price": row.price,
            "abs_change": row.abs_change,
            "pct_change": row.pct_change,
            "volume": row.volume,
        }
        reasons.append("numeric_signals_backfilled")

    if not analysis.decision_trace.rules_triggered:
        analysis.decision_trace.rules_triggered = ["critic_default_rule"]
        reasons.append("rules_triggered_backfilled")

    if not analysis.decision_trace.explainability_summary:
        analysis.decision_trace.explainability_summary = (
            f"{row.ticker} assessment was normalized by critic checks for completeness and plausibility."
        )
        reasons.append("explainability_summary_backfilled")

    has_headlines = bool(enrichment.headlines)
    if not has_headlines and analysis.confidence > 0.7:
        analysis.confidence = 0.7
        reasons.append("confidence_reduced_no_headlines")

    return analysis, sorted(set(reasons))


def _force_two_sentences(text: str, *, ticker: str, pct_change: float) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return (
            f"{ticker} moved {pct_change:+.2f}% based on available numerical signals and evidence. "
            "Evidence coverage was limited, so the interpretation remains cautious."
        )

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    if len(sentences) >= 2:
        return _ensure_sentence_end(sentences[0]) + " " + _ensure_sentence_end(sentences[1])
    if len(sentences) == 1:
        first = _ensure_sentence_end(sentences[0])
        second = "Evidence was limited, so the confidence is treated cautiously."
        return f"{first} {second}"

    return (
        f"{ticker} moved {pct_change:+.2f}% based on available numerical signals and evidence. "
        "Evidence coverage was limited, so the interpretation remains cautious."
    )


def _ensure_sentence_end(sentence: str) -> str:
    return sentence if sentence.endswith((".", "!", "?")) else sentence + "."
