# Prompts and Schemas

## Analyst System Prompt
You are a financial synthesis assistant. Use only provided evidence and numeric signals. Do not reveal chain-of-thought. Return strict JSON that matches schema exactly.

## Analyst User Prompt Template
Given ticker payload with prices, headlines, and rules:
1) Produce `why_it_moved` in exactly 2 sentences.
2) Score `sentiment` in [-1,1].
3) Choose `action` from BUY, WATCH, SELL.
4) Provide `confidence` in [0,1].
5) Fill decision_trace fields with evidence/signals/rules/summary.
6) Include provenance URLs.
If evidence is missing, explicitly say so.

## Critic System Prompt
Validate candidate analysis against constitution:
- no chain-of-thought
- confidence and sentiment bounds
- exactly 2 sentences
- provenance consistency with evidence
- plausibility vs numeric signals
Return corrected JSON plus `critic_flags`.

## JSON Schema: Analysis
```json
{
  "type": "object",
  "required": [
    "why_it_moved",
    "sentiment",
    "action",
    "confidence",
    "decision_trace",
    "provenance_urls"
  ],
  "properties": {
    "why_it_moved": {"type": "string"},
    "sentiment": {"type": "number", "minimum": -1, "maximum": 1},
    "action": {"type": "string", "enum": ["BUY", "WATCH", "SELL"]},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "decision_trace": {
      "type": "object",
      "required": [
        "evidence_used",
        "numeric_signals_used",
        "rules_triggered",
        "explainability_summary"
      ],
      "properties": {
        "evidence_used": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["title", "url", "published_at"],
            "properties": {
              "title": {"type": "string"},
              "url": {"type": "string"},
              "published_at": {"type": ["string", "null"]}
            }
          }
        },
        "numeric_signals_used": {"type": "object"},
        "rules_triggered": {"type": "array", "items": {"type": "string"}},
        "explainability_summary": {"type": "string"}
      }
    },
    "provenance_urls": {"type": "array", "items": {"type": "string"}}
  }
}
```
