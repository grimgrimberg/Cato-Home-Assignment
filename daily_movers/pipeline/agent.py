"""
LangGraph-powered agentic analysis pipeline.

This module implements a multi-node StateGraph with four specialised agent nodes:
  1. Researcher   – gathers and structures raw evidence from enrichment data
  2. Analyst      – produces sentiment, action, and a two-sentence explanation
  3. Critic       – validates, normalises, and applies guard-rails
  4. Recommender  – assigns portfolio-level tags (top_pick / most_potential)

The graph uses conditional edges so that:
  • If the Analyst fails or returns low-confidence output the Critic can
    request a re-analysis (up to one retry).
  • The Recommender only runs after the Critic approves.

When OPENAI_API_KEY is absent the graph still runs, but every node falls back
to deterministic heuristic logic – so the pipeline never crashes.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any, Literal, TypedDict

from daily_movers.config import AppConfig
from daily_movers.models import (
    Action,
    Analysis,
    DecisionTrace,
    Enrichment,
    Headline,
    TickerRow,
)
from daily_movers.storage.runs import StructuredLogger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typed state that flows through the graph
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    """Mutable state passed between LangGraph nodes."""
    row: dict[str, Any]
    enrichment: dict[str, Any]
    _config: dict[str, Any]
    _logger_path: str
    _run_id: str
    evidence_summary: str
    evidence_headlines: list[dict[str, Any]]
    numeric_signals: dict[str, Any]
    analyst_output: dict[str, Any]
    critic_flags: list[str]
    critic_approved: bool
    retry_count: int
    analysis: dict[str, Any]
    recommendation_tags: list[str]
    model_used: str
    error: str | None


# ---------------------------------------------------------------------------
# LangGraph builder – lazy import so the module loads even if langgraph
# is not installed (heuristic fallback still works).
# ---------------------------------------------------------------------------

def _build_graph():
    """Build and compile the LangGraph StateGraph.  Import is deferred so
    the rest of the package works without langgraph installed."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)

    graph.add_node("researcher", researcher_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("critic", critic_node)
    graph.add_node("recommender", recommender_node)

    graph.add_edge(START, "researcher")
    graph.add_edge("researcher", "analyst")
    graph.add_conditional_edges(
        "analyst",
        _analyst_to_critic_or_end,
        {"critic": "critic", "end": END},
    )
    graph.add_conditional_edges(
        "critic",
        _critic_routing,
        {"recommender": "recommender", "retry_analyst": "analyst", "end": END},
    )
    graph.add_edge("recommender", END)

    return graph.compile()


# Singleton compiled graph (created once per process)
_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()
    return _compiled_graph


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

def run_agent_analysis(
    *,
    row: TickerRow,
    enrichment: Enrichment,
    config: AppConfig,
    run_logger: StructuredLogger,
) -> Analysis:
    """Execute the full LangGraph agent pipeline for a single ticker.

    Returns a validated Analysis model.  Never raises – falls back to
    heuristics on any internal error.
    """
    initial_state: AgentState = {
        "row": row.model_dump(),
        "enrichment": enrichment.model_dump(),
        "evidence_summary": "",
        "evidence_headlines": [],
        "numeric_signals": {},
        "analyst_output": {},
        "critic_flags": [],
        "critic_approved": False,
        "retry_count": 0,
        "analysis": {},
        "recommendation_tags": [],
        "model_used": "langgraph:heuristics",
        "error": None,
    }

    # Inject config so nodes can access LLM settings
    initial_state["_config"] = config.model_dump()  # type: ignore[typeddict-unknown-key]
    initial_state["_logger_path"] = str(run_logger.path)  # type: ignore[typeddict-unknown-key]
    initial_state["_run_id"] = run_logger.run_id  # type: ignore[typeddict-unknown-key]

    try:
        graph = _get_graph()
        final_state = graph.invoke(initial_state)
        analysis_dict = final_state.get("analysis") or {}
        if not analysis_dict:
            raise ValueError("agent graph produced empty analysis")

        analysis = Analysis.model_validate(analysis_dict)
        analysis.model_used = final_state.get("model_used", "langgraph:heuristics")

        run_logger.info(
            "agent_analysis_completed",
            stage="agent",
            symbol=row.ticker,
            model_used=analysis.model_used,
        )
        return analysis

    except Exception as exc:
        run_logger.warning(
            "agent_analysis_fallback",
            stage="agent",
            symbol=row.ticker,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )
        # Fall back to deterministic heuristics
        from daily_movers.pipeline.heuristics import analyze_with_heuristics
        analysis = analyze_with_heuristics(row=row, enrichment=enrichment)
        analysis.model_used = "langgraph:heuristic_fallback"
        return analysis


# ---------------------------------------------------------------------------
# Node 1: RESEARCHER
# ---------------------------------------------------------------------------

def researcher_node(state: AgentState) -> dict[str, Any]:
    """Gathers and structures evidence from the enrichment payload."""
    enrichment = state.get("enrichment", {})
    row = state.get("row", {})

    headlines_raw = enrichment.get("headlines", [])
    evidence: list[dict[str, Any]] = []
    for h in headlines_raw[:5]:
        evidence.append({
            "title": h.get("title", ""),
            "url": h.get("url", ""),
            "published_at": h.get("published_at"),
        })

    pct = float(row.get("pct_change") or 0.0)
    abs_change = float(row.get("abs_change") or 0.0)
    price = float(row.get("price") or 0.0)
    volume = float(row.get("volume") or 0.0)

    numeric_signals = {
        "price": price,
        "abs_change": abs_change,
        "pct_change": pct,
        "volume": volume,
        "headline_count": len(evidence),
        "sector": enrichment.get("sector"),
        "industry": enrichment.get("industry"),
        "earnings_date": enrichment.get("earnings_date"),
        "price_trend_points": len(enrichment.get("price_series", [])),
    }

    # Build a human-readable evidence summary for the analyst
    ticker = row.get("ticker", "???")
    if evidence:
        top_titles = "; ".join(h["title"][:80] for h in evidence[:3])
        summary = (
            f"{ticker} moved {pct:+.2f}% (${abs_change:+.2f}) on volume {volume:,.0f}. "
            f"Key headlines: {top_titles}."
        )
    else:
        summary = (
            f"{ticker} moved {pct:+.2f}% (${abs_change:+.2f}) on volume {volume:,.0f}. "
            f"No fresh headline evidence available."
        )

    if enrichment.get("sector"):
        summary += f" Sector: {enrichment['sector']}."
    if enrichment.get("earnings_date"):
        summary += f" Next earnings: {enrichment['earnings_date']}."

    return {
        "evidence_summary": summary,
        "evidence_headlines": evidence,
        "numeric_signals": numeric_signals,
    }


# ---------------------------------------------------------------------------
# Node 2: ANALYST
# ---------------------------------------------------------------------------

def analyst_node(state: AgentState) -> dict[str, Any]:
    """Produces sentiment, action, confidence, and explanation.

    If an OpenAI key is available and LangChain ChatOpenAI works, uses the LLM.
    Otherwise falls back to rule-based heuristics.
    """
    config_dict = state.get("_config", {})
    api_key = config_dict.get("openai_api_key")
    row = state.get("row", {})
    enrichment_dict = state.get("enrichment", {})
    evidence_summary = state.get("evidence_summary", "")
    evidence_headlines = state.get("evidence_headlines", [])
    numeric_signals = state.get("numeric_signals", {})

    if api_key:
        try:
            result = _llm_analyst(
                api_key=api_key,
                model=config_dict.get("analysis_model", "gpt-4o-mini"),
                base_url=config_dict.get("openai_base_url", "https://api.openai.com/v1"),
                timeout=config_dict.get("openai_timeout_seconds", 45),
                ticker=row.get("ticker", "???"),
                evidence_summary=evidence_summary,
                evidence_headlines=evidence_headlines,
                numeric_signals=numeric_signals,
            )
            result["model_used"] = f"langgraph:openai:{config_dict.get('analysis_model', 'gpt-4o-mini')}"
            return {"analyst_output": result, "model_used": result["model_used"]}
        except Exception as exc:
            logger.warning("LLM analyst failed (%s), falling back to heuristics", exc)

    # Heuristic fallback
    result = _heuristic_analyst(
        row=row,
        evidence_summary=evidence_summary,
        evidence_headlines=evidence_headlines,
        numeric_signals=numeric_signals,
    )
    return {"analyst_output": result, "model_used": "langgraph:heuristics"}


def _llm_analyst(
    *,
    api_key: str,
    model: str,
    base_url: str,
    timeout: int,
    ticker: str,
    evidence_summary: str,
    evidence_headlines: list[dict[str, Any]],
    numeric_signals: dict[str, Any],
) -> dict[str, Any]:
    """Call ChatOpenAI via LangChain to produce structured analysis."""
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = ChatOpenAI(
        model=model,
        api_key=lambda: api_key,
        base_url=base_url,
        temperature=0.1,
        timeout=timeout,
        max_retries=1,
    )

    system_msg = SystemMessage(content=(
        "You are a financial analyst AI. You produce concise, evidence-based stock analysis. "
        "Return ONLY valid JSON with these exact keys: "
        "why_it_moved (exactly 2 sentences), sentiment (float -1 to 1), "
        "action (BUY/WATCH/SELL), confidence (float 0 to 1), "
        "rules_triggered (list of rule name strings), "
        "explainability_summary (1 sentence). "
        "Never include chain-of-thought. Reference only provided evidence."
    ))

    human_msg = HumanMessage(content=(
        f"Analyze {ticker}.\n\n"
        f"Evidence summary: {evidence_summary}\n\n"
        f"Numeric signals: {json.dumps(numeric_signals)}\n\n"
        f"Headlines: {json.dumps(evidence_headlines)}\n\n"
        "Produce your JSON analysis now."
    ))

    response = llm.invoke([system_msg, human_msg])
    text = response.content if isinstance(response.content, str) else str(response.content)
    parsed = _extract_json(text)

    # Normalise and validate
    sentiment = _clamp(_to_float(parsed.get("sentiment"), 0.0), -1.0, 1.0)
    confidence = _clamp(_to_float(parsed.get("confidence"), 0.6), 0.0, 1.0)
    action = _normalise_action(parsed.get("action"), sentiment)
    why = _ensure_two_sentences(
        parsed.get("why_it_moved", ""),
        ticker=ticker,
        pct=numeric_signals.get("pct_change", 0.0),
        action=action,
        confidence=confidence,
        has_headlines=bool(evidence_headlines),
    )
    rules = parsed.get("rules_triggered", [])
    if not isinstance(rules, list):
        rules = []
    rules = [str(r) for r in rules if r]

    expl = parsed.get("explainability_summary", "")
    if not isinstance(expl, str) or not expl.strip():
        expl = f"{ticker} analysis produced by LLM agent with {len(rules)} rules."

    return {
        "why_it_moved": why,
        "sentiment": sentiment,
        "action": action,
        "confidence": confidence,
        "rules_triggered": rules,
        "explainability_summary": expl,
    }


def _heuristic_analyst(
    *,
    row: dict[str, Any],
    evidence_summary: str,
    evidence_headlines: list[dict[str, Any]],
    numeric_signals: dict[str, Any],
) -> dict[str, Any]:
    """Pure heuristic analysis matching the logic in heuristics.py."""
    pct = float(row.get("pct_change") or 0.0)
    volume = float(row.get("volume") or 0.0)
    has_headlines = bool(evidence_headlines)
    ticker = row.get("ticker", "???")

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
        action = "BUY"
    elif sentiment <= -0.4 and confidence >= 0.65:
        action = "SELL"
    else:
        action = "WATCH"

    if has_headlines:
        title = evidence_headlines[0].get("title", "")[:80]
        why = (
            f"{ticker} moved {pct:+.2f}% while coverage highlighted {title}. "
            f"Volume near {_fmt_vol(volume)} supports a {action.lower()} stance at {confidence:.2f} confidence."
        )
    else:
        why = (
            f"{ticker} moved {pct:+.2f}% but no fresh headline evidence was available at analysis time. "
            f"The recommendation is {action.lower()} with {confidence:.2f} confidence based on price and volume signals only."
        )

    expl = (
        f"{ticker} is tagged {action} from {pct:+.2f}% movement with "
        f"{len(rules)} triggered rules."
    )

    return {
        "why_it_moved": why,
        "sentiment": sentiment,
        "action": action,
        "confidence": confidence,
        "rules_triggered": rules,
        "explainability_summary": expl,
    }


# ---------------------------------------------------------------------------
# Conditional edge: analyst → critic or end
# ---------------------------------------------------------------------------

def _analyst_to_critic_or_end(state: AgentState) -> Literal["critic", "end"]:
    """If analyst produced output, proceed to critic.  Otherwise end."""
    if state.get("analyst_output"):
        return "critic"
    return "end"


# ---------------------------------------------------------------------------
# Node 3: CRITIC
# ---------------------------------------------------------------------------

def critic_node(state: AgentState) -> dict[str, Any]:
    """Validates analyst output, applies guard-rails, and builds the final
    Analysis dict.  May request one retry by setting critic_approved=False."""
    analyst = state.get("analyst_output", {})
    row = state.get("row", {})
    enrichment_dict = state.get("enrichment", {})
    evidence_headlines = state.get("evidence_headlines", [])
    numeric_signals = state.get("numeric_signals", {})
    retry_count = state.get("retry_count", 0)

    flags: list[str] = []
    ticker = row.get("ticker", "???")

    # -- Guard-rails --
    why = analyst.get("why_it_moved", "")
    lower_why = why.lower()
    cot_patterns = ["chain of thought", "chain-of-thought", "step-by-step", "let me think", "internal reasoning"]
    if any(p in lower_why for p in cot_patterns):
        pct = float(row.get("pct_change") or 0)
        why = (
            f"{ticker} moved {pct:+.2f}% based on observed market signals and cited evidence only. "
            "The explanation was sanitised to remove internal reasoning language."
        )
        flags.append("cot_language_removed")

    sentiment = _clamp(_to_float(analyst.get("sentiment"), 0.0), -1.0, 1.0)
    confidence = _clamp(_to_float(analyst.get("confidence"), 0.6), 0.0, 1.0)
    action = _normalise_action(analyst.get("action"), sentiment)

    # Reduce confidence when no headline evidence
    has_headlines = bool(evidence_headlines)
    if not has_headlines and confidence > 0.7:
        confidence = 0.7
        flags.append("confidence_reduced_no_headlines")

    # Low confidence → maybe retry once
    if confidence < 0.35 and retry_count < 1:
        flags.append("low_confidence_retry_requested")
        return {
            "critic_flags": flags,
            "critic_approved": False,
            "retry_count": retry_count + 1,
        }

    # Build provenance URLs
    provenance: list[str] = []
    for h in evidence_headlines:
        url = h.get("url")
        if url and url not in provenance:
            provenance.append(url)
    quote_url = f"https://finance.yahoo.com/quote/{ticker}"
    if quote_url not in provenance:
        provenance.append(quote_url)

    rules = analyst.get("rules_triggered", [])
    if not isinstance(rules, list):
        rules = []
    rules = [str(r) for r in rules if r]
    if not rules:
        rules = ["critic_default_rule"]
        flags.append("rules_backfilled")

    expl = analyst.get("explainability_summary", "")
    if not isinstance(expl, str) or not expl.strip():
        expl = f"{ticker} assessment normalised by critic for completeness."
        flags.append("explainability_backfilled")

    # Ensure why_it_moved is exactly two sentences
    pct_val = float(row.get("pct_change") or 0)
    why = _ensure_two_sentences(why, ticker=ticker, pct=pct_val, action=action,
                                confidence=confidence, has_headlines=has_headlines)

    analysis_dict = {
        "why_it_moved": why,
        "sentiment": sentiment,
        "action": action,
        "confidence": confidence,
        "decision_trace": {
            "evidence_used": [
                {"title": h.get("title", ""), "url": h.get("url", ""), "published_at": h.get("published_at")}
                for h in evidence_headlines[:3]
            ],
            "numeric_signals_used": numeric_signals,
            "rules_triggered": rules,
            "explainability_summary": expl.strip(),
        },
        "provenance_urls": provenance,
        "model_used": state.get("model_used", "langgraph:heuristics"),
    }

    return {
        "analysis": analysis_dict,
        "critic_flags": flags,
        "critic_approved": True,
    }


# ---------------------------------------------------------------------------
# Conditional edge: critic → recommender, retry, or end
# ---------------------------------------------------------------------------

def _critic_routing(state: AgentState) -> Literal["recommender", "retry_analyst", "end"]:
    if state.get("critic_approved"):
        return "recommender"
    if state.get("retry_count", 0) <= 1 and not state.get("critic_approved"):
        return "retry_analyst"
    return "end"


# ---------------------------------------------------------------------------
# Node 4: RECOMMENDER
# ---------------------------------------------------------------------------

def recommender_node(state: AgentState) -> dict[str, Any]:
    """Assigns portfolio-level recommendation tags based on the analysis."""
    analysis = state.get("analysis", {})
    numeric = state.get("numeric_signals", {})
    tags: list[str] = []

    action = analysis.get("action", "WATCH")
    confidence = float(analysis.get("confidence", 0))
    sentiment = float(analysis.get("sentiment", 0))
    pct = float(numeric.get("pct_change", 0))
    volume = float(numeric.get("volume", 0))

    # Top pick: strong buy + high confidence
    if action == "BUY" and confidence >= 0.75 and sentiment > 0.3:
        tags.append("top_pick_candidate")

    # Most potential: positive sentiment but moderate confidence (room to grow)
    if sentiment > 0.15 and confidence < 0.75 and action in ("BUY", "WATCH"):
        tags.append("most_potential_candidate")

    # Contrarian signal: heavily sold off but high volume (potential bounce)
    if pct < -5 and volume >= 5_000_000:
        tags.append("contrarian_bounce_candidate")

    # Momentum flag
    if pct > 3 and volume >= 2_000_000:
        tags.append("momentum_signal")

    if not tags:
        tags.append("standard")

    return {"recommendation_tags": tags}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    # Try parsing directly
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Try extracting first JSON object
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def _to_float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        f = float(value)
        return default if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(value, str):
        try:
            f = float(value.strip().replace("%", ""))
            return default if (math.isnan(f) or math.isinf(f)) else f
        except ValueError:
            return default
    return default


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _normalise_action(value: Any, sentiment: float) -> str:
    if isinstance(value, str):
        upper = value.strip().upper()
        if upper in ("BUY", "WATCH", "SELL"):
            return upper
    if sentiment >= 0.25:
        return "BUY"
    if sentiment <= -0.25:
        return "SELL"
    return "WATCH"


def _ensure_two_sentences(
    text: str,
    *,
    ticker: str,
    pct: float,
    action: str,
    confidence: float,
    has_headlines: bool,
) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        if has_headlines:
            return (
                f"{ticker} moved {pct:+.2f}% with headline evidence in the provided input. "
                f"The suggested action is {action} with {confidence:.2f} confidence."
            )
        return (
            f"{ticker} moved {pct:+.2f}% and no fresh headline evidence was available. "
            f"The suggested action is {action} with {confidence:.2f} confidence."
        )

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    if len(sentences) >= 2:
        s1 = sentences[0] if sentences[0].endswith((".", "!", "?")) else sentences[0] + "."
        s2 = sentences[1] if sentences[1].endswith((".", "!", "?")) else sentences[1] + "."
        return f"{s1} {s2}"

    first = sentences[0] if sentences else f"{ticker} moved {pct:+.2f}%."
    if not first.endswith((".", "!", "?")):
        first += "."
    second = f"The suggested action is {action} with {confidence:.2f} confidence."
    return f"{first} {second}"


def _fmt_vol(volume: float) -> str:
    if volume >= 1_000_000_000:
        return f"{volume / 1_000_000_000:.2f}B"
    if volume >= 1_000_000:
        return f"{volume / 1_000_000:.2f}M"
    if volume >= 1_000:
        return f"{volume / 1_000:.2f}K"
    return f"{volume:.0f}"
