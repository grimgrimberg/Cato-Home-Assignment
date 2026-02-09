from __future__ import annotations

import json
import math
import re
from typing import Any

import requests

from daily_movers.config import AppConfig
from daily_movers.errors import AnalysisError
from daily_movers.models import Analysis, Enrichment, Headline, TickerRow
from daily_movers.storage.runs import StructuredLogger


class OpenAIAnalyzer:
    def __init__(self, *, config: AppConfig, logger: StructuredLogger) -> None:
        self.config = config
        self.logger = logger

    @property
    def enabled(self) -> bool:
        return self.config.openai_enabled

    def synthesize(self, *, row: TickerRow, enrichment: Enrichment) -> Analysis:
        if not self.enabled:
            raise AnalysisError("OPENAI_API_KEY is not configured", stage="analysis", url=None)

        url = f"{self.config.openai_base_url.rstrip('/')}/responses"
        prompt_payload = {
            "ticker": row.model_dump(),
            "enrichment": enrichment.model_dump(),
            "constraints": {
                "no_chain_of_thought": True,
                "why_it_moved_exactly_2_sentences": True,
                "sentiment_range": [-1, 1],
                "confidence_range": [0, 1],
                "allowed_action": ["BUY", "WATCH", "SELL"],
            },
        }
        prompt_text = json.dumps(prompt_payload, ensure_ascii=True)

        system_prompt = (
            "You are a financial synthesis model. Use only provided evidence and numeric signals. "
            "Return strict JSON only. Never include chain-of-thought."
        )

        user_prompt = (
            "Produce JSON with keys: why_it_moved, sentiment, action, confidence, decision_trace, provenance_urls. "
            "decision_trace must include evidence_used, numeric_signals_used, rules_triggered, explainability_summary. "
            "why_it_moved must be exactly two sentences and must mention evidence absence when headlines are missing. "
            f"Input: {prompt_text}"
        )

        payload: dict[str, Any] = {
            "model": self.config.analysis_model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.config.openai_api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.config.openai_timeout_seconds,
                )
                if response.status_code >= 400:
                    safe_error = _safe_openai_error(response)
                    raise AnalysisError(
                        safe_error,
                        stage="analysis",
                        url=url,
                    )
                data = response.json()
                text = _extract_response_text(data)
                json_obj = _extract_json_object(text)
                normalized = _normalize_analysis_json(
                    json_obj=json_obj,
                    row=row,
                    enrichment=enrichment,
                )
                analysis = Analysis.model_validate(normalized)
                analysis.model_used = f"openai:{self.config.analysis_model}"
                self.logger.info(
                    "openai_synthesis_success",
                    stage="analysis",
                    symbol=row.ticker,
                    retries=attempt,
                    url=url,
                )
                return analysis
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self.logger.warning(
                    "openai_synthesis_retry" if attempt == 0 else "openai_synthesis_failed",
                    stage="analysis",
                    symbol=row.ticker,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    retries=attempt,
                    url=url,
                )

        message = str(last_error) if last_error else "unknown synthesis failure"
        raise AnalysisError(message, stage="analysis", url=url)


def _extract_response_text(response_json: dict[str, Any]) -> str:
    if isinstance(response_json.get("output_text"), str):
        return response_json["output_text"]

    pieces: list[str] = []
    for item in response_json.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                pieces.append(text)
    if not pieces:
        raise ValueError("no textual output returned by Responses API")
    return "\n".join(pieces)


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in model output")

    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("parsed JSON output is not an object")
    return parsed


def _normalize_analysis_json(
    *,
    json_obj: dict[str, Any],
    row: TickerRow,
    enrichment: Enrichment,
) -> dict[str, Any]:
    normalized: dict[str, Any] = dict(json_obj)

    raw_sentiment = _coerce_float(normalized.get("sentiment"), 0.0)
    sentiment = _clamp(raw_sentiment, -1.0, 1.0)
    action = _coerce_action(normalized.get("action"), sentiment=sentiment)
    confidence = _clamp(_coerce_float(normalized.get("confidence"), 0.6), 0.0, 1.0)
    why_it_moved = _coerce_why_it_moved(
        raw=normalized.get("why_it_moved"),
        row=row,
        action=action,
        confidence=confidence,
        has_headlines=bool(enrichment.headlines),
    )

    trace_raw = normalized.get("decision_trace")
    if not isinstance(trace_raw, dict):
        trace_raw = {}
    evidence_used = _coerce_evidence_used(trace_raw.get("evidence_used"), enrichment=enrichment)
    numeric_signals = _coerce_numeric_signals(
        trace_raw.get("numeric_signals_used"),
        row=row,
        enrichment=enrichment,
    )
    rules_triggered = _coerce_rules(trace_raw.get("rules_triggered"))
    explainability_summary = trace_raw.get("explainability_summary")
    if not isinstance(explainability_summary, str) or not explainability_summary.strip():
        explainability_summary = (
            f"{row.ticker} is tagged {action} from {(row.pct_change or 0.0):+.2f}% movement "
            f"with {len(rules_triggered)} triggered rules."
        )

    provenance_urls = _coerce_provenance_urls(
        raw=normalized.get("provenance_urls"),
        evidence_used=evidence_used,
        ticker=row.ticker,
    )

    normalized["why_it_moved"] = why_it_moved
    normalized["sentiment"] = sentiment
    normalized["action"] = action
    normalized["confidence"] = confidence
    normalized["decision_trace"] = {
        "evidence_used": evidence_used,
        "numeric_signals_used": numeric_signals,
        "rules_triggered": rules_triggered,
        "explainability_summary": explainability_summary.strip(),
    }
    normalized["provenance_urls"] = provenance_urls
    return normalized


def _coerce_float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        if math.isnan(float(value)) or math.isinf(float(value)):
            return default
        return float(value)
    if isinstance(value, str):
        candidate = value.strip().replace("%", "")
        try:
            parsed = float(candidate)
        except ValueError:
            return default
        if math.isnan(parsed) or math.isinf(parsed):
            return default
        return parsed
    return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _coerce_action(value: Any, *, sentiment: float) -> str:
    if isinstance(value, str):
        upper = value.strip().upper()
        if upper in {"BUY", "WATCH", "SELL"}:
            return upper
    if sentiment >= 0.25:
        return "BUY"
    if sentiment <= -0.25:
        return "SELL"
    return "WATCH"


def _coerce_why_it_moved(
    *,
    raw: Any,
    row: TickerRow,
    action: str,
    confidence: float,
    has_headlines: bool,
) -> str:
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        if has_headlines:
            text = f"{row.ticker} moved {(row.pct_change or 0.0):+.2f}% with headline evidence in the provided input."
        else:
            text = (
                f"{row.ticker} moved {(row.pct_change or 0.0):+.2f}% and no fresh headline evidence "
                "was available in the provided input."
            )

    sentences = _split_sentences(text)
    if len(sentences) >= 2:
        return f"{sentences[0]} {sentences[1]}"

    if has_headlines:
        second = (
            f"The suggested action is {action} with {confidence:.2f} confidence using price, volume, and evidence signals."
        )
    else:
        second = (
            f"The suggested action is {action} with {confidence:.2f} confidence using price and volume signals only."
        )
    if sentences:
        first = sentences[0]
    else:
        first = f"{row.ticker} showed {(row.pct_change or 0.0):+.2f}% movement in the latest session."
    if not first.endswith((".", "!", "?")):
        first = f"{first}."
    return f"{first} {second}"


def _split_sentences(text: str) -> list[str]:
    pieces = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
    return pieces


def _coerce_evidence_used(raw: Any, *, enrichment: Enrichment) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            parsed = _coerce_headline(item)
            if parsed is not None:
                evidence.append(parsed)

    if not evidence:
        for headline in enrichment.headlines[:3]:
            evidence.append(
                {
                    "title": headline.title,
                    "url": headline.url,
                    "published_at": headline.published_at,
                }
            )
    return evidence


def _coerce_headline(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, Headline):
        return {
            "title": raw.title,
            "url": raw.url,
            "published_at": raw.published_at,
        }
    if not isinstance(raw, dict):
        return None

    title = raw.get("title") or raw.get("headline") or raw.get("text")
    url = raw.get("url") or raw.get("link")
    published_at = raw.get("published_at") or raw.get("published") or raw.get("pubDate")
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(url, str) or not url.strip():
        return None
    return {
        "title": title.strip(),
        "url": url.strip(),
        "published_at": str(published_at).strip() if published_at is not None else None,
    }


def _coerce_numeric_signals(
    raw: Any,
    *,
    row: TickerRow,
    enrichment: Enrichment,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "price": row.price,
        "abs_change": row.abs_change,
        "pct_change": row.pct_change,
        "volume": row.volume,
        "headline_count": len(enrichment.headlines),
    }
    if isinstance(raw, dict):
        merged = dict(base)
        merged.update(raw)
        return merged

    if isinstance(raw, list):
        merged = dict(base)
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = item.get("name") or item.get("key") or item.get("signal")
            if not isinstance(key, str) or not key.strip():
                continue
            if "value" in item:
                merged[key.strip()] = item.get("value")
            elif "metric_value" in item:
                merged[key.strip()] = item.get("metric_value")
        return merged

    return base


def _coerce_rules(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    results: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            results.append(item.strip())
            continue
        if isinstance(item, dict):
            candidate = (
                item.get("id")
                or item.get("name")
                or item.get("rule")
                or item.get("description")
            )
            if isinstance(candidate, str) and candidate.strip():
                results.append(candidate.strip())
    return _dedupe_keep_order(results)


def _coerce_provenance_urls(*, raw: Any, evidence_used: list[dict[str, Any]], ticker: str) -> list[str]:
    urls: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                urls.append(item.strip())
    for item in evidence_used:
        url = item.get("url")
        if isinstance(url, str) and url.strip():
            urls.append(url.strip())
    quote_url = f"https://finance.yahoo.com/quote/{ticker}"
    urls.append(quote_url)
    return _dedupe_keep_order(urls)


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _safe_openai_error(response: requests.Response) -> str:
    code = response.status_code
    try:
        payload = response.json()
    except ValueError:
        return f"OpenAI API returned HTTP {code}"

    err_obj = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(err_obj, dict):
        return f"OpenAI API returned HTTP {code}"

    message = str(err_obj.get("message") or "").lower()
    if "incorrect api key provided" in message or "invalid_api_key" in message:
        return "OpenAI authentication failed (invalid API key)"
    if "rate limit" in message:
        return "OpenAI request failed due to rate limits"
    if "insufficient_quota" in message:
        return "OpenAI request failed due to insufficient quota"
    return f"OpenAI API returned HTTP {code}"
