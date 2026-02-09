from __future__ import annotations

from daily_movers.models import Action, Analysis, DecisionTrace, Enrichment, Headline, TickerRow


def analyze_with_heuristics(*, row: TickerRow, enrichment: Enrichment) -> Analysis:
    pct = float(row.pct_change or 0.0)
    abs_change = float(row.abs_change or 0.0)
    volume = float(row.volume or 0.0)
    price = float(row.price or 0.0)
    has_headlines = bool(enrichment.headlines)

    sentiment = _clamp(pct / 12.0, -1.0, 1.0)
    confidence = 0.58
    confidence += min(abs(pct) / 60.0, 0.18)
    confidence += 0.12 if has_headlines else -0.10
    confidence += 0.05 if volume >= 1_000_000 else 0.0
    confidence = _clamp(confidence, 0.05, 0.95)

    rules: list[str] = []
    if pct >= 5:
        rules.append("positive_price_impulse")
    if pct <= -5:
        rules.append("negative_price_impulse")
    if abs(pct) > 15:
        rules.append("extreme_percent_change")
    if volume >= 5_000_000:
        rules.append("elevated_volume")
    if not has_headlines:
        rules.append("no_headline_evidence")

    if sentiment >= 0.4 and confidence >= 0.65:
        action = Action.BUY
    elif sentiment <= -0.4 and confidence >= 0.65:
        action = Action.SELL
    else:
        action = Action.WATCH

    evidence = enrichment.headlines[:3]
    why_it_moved = _build_two_sentence_explanation(
        ticker=row.ticker,
        pct=pct,
        action=action,
        confidence=confidence,
        headlines=evidence,
        volume=volume,
    )

    trace = DecisionTrace(
        evidence_used=evidence,
        numeric_signals_used={
            "price": price,
            "abs_change": abs_change,
            "pct_change": pct,
            "volume": volume,
            "headline_count": len(evidence),
        },
        rules_triggered=rules,
        explainability_summary=_build_trace_summary(
            ticker=row.ticker,
            action=action,
            pct=pct,
            rule_count=len(rules),
            has_headlines=has_headlines,
        ),
    )

    provenance = [h.url for h in evidence if h.url]
    quote_url = f"https://finance.yahoo.com/quote/{row.ticker}"
    if quote_url not in provenance:
        provenance.append(quote_url)

    return Analysis(
        why_it_moved=why_it_moved,
        sentiment=sentiment,
        action=action,
        confidence=confidence,
        decision_trace=trace,
        provenance_urls=provenance,
        model_used="heuristics",
    )


def _build_two_sentence_explanation(
    *,
    ticker: str,
    pct: float,
    action: Action,
    confidence: float,
    headlines: list[Headline],
    volume: float,
) -> str:
    if headlines:
        title = _sanitize_title(headlines[0].title)
        sentence_1 = f"{ticker} moved {pct:+.2f}% while coverage highlighted {title}."
        sentence_2 = (
            f"Volume near {_format_volume(volume)} supports a {action.value.lower()} stance at {confidence:.2f} confidence."
        )
        return f"{sentence_1} {sentence_2}"

    sentence_1 = f"{ticker} moved {pct:+.2f}% but no fresh headline evidence was available at analysis time."
    sentence_2 = (
        f"The recommendation is {action.value.lower()} with {confidence:.2f} confidence based on price and volume signals only."
    )
    return f"{sentence_1} {sentence_2}"


def _build_trace_summary(*, ticker: str, action: Action, pct: float, rule_count: int, has_headlines: bool) -> str:
    evidence_state = "headline-supported" if has_headlines else "headline-light"
    return (
        f"{ticker} is tagged {action.value} from {pct:+.2f}% movement with {rule_count} triggered rules under a {evidence_state} context."
    )


def _sanitize_title(title: str) -> str:
    cleaned = title.replace("\"", "").replace("'", "")
    cleaned = cleaned.replace(".", "")
    return cleaned[:120] if len(cleaned) > 120 else cleaned


def _format_volume(volume: float) -> str:
    if volume >= 1_000_000_000:
        return f"{volume / 1_000_000_000:.2f}B"
    if volume >= 1_000_000:
        return f"{volume / 1_000_000:.2f}M"
    if volume >= 1_000:
        return f"{volume / 1_000:.2f}K"
    return f"{volume:.0f}"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
