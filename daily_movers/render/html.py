from __future__ import annotations

import html
from urllib.parse import quote, urlparse
from typing import Any

from daily_movers.models import ReportRow


def build_digest_html(*, rows: list[ReportRow], run_meta: dict[str, Any]) -> str:
    """Build the standalone HTML digest for a run.

    Security posture:
    - All user-/upstream-provided strings are escaped before embedding in HTML.
    - Outbound links are restricted to safe schemes (http/https) where applicable.
    """
    gainers = sorted(
        rows,
        key=lambda r: r.ticker.pct_change if r.ticker.pct_change is not None else -9999,
        reverse=True,
    )[:3]
    losers = sorted(
        rows,
        key=lambda r: r.ticker.pct_change if r.ticker.pct_change is not None else 9999,
    )[:3]

    # --- Top Pick & Most Potential ---
    top_pick = None
    most_potential = None
    for r in rows:
        if "top_pick_candidate" in r.recommendation_tags:
            if top_pick is None or r.analysis.confidence > top_pick.analysis.confidence:
                top_pick = r
        if "most_potential_candidate" in r.recommendation_tags:
            if most_potential is None or r.analysis.sentiment > most_potential.analysis.sentiment:
                most_potential = r

    # --- Market breakdown ---
    market_counts: dict[str, int] = {}
    for r in rows:
        mkt = _detect_market(r.ticker.ticker, r.ticker.market)
        market_counts[mkt] = market_counts.get(mkt, 0) + 1

    table_rows = "".join(_build_table_row(row, idx) for idx, row in enumerate(rows))

    processed = len(rows)
    needs_review = sum(1 for row in rows if row.needs_review)
    action_buy = sum(1 for row in rows if row.analysis.action.value == "BUY")
    action_watch = sum(1 for row in rows if row.analysis.action.value == "WATCH")
    action_sell = sum(1 for row in rows if row.analysis.action.value == "SELL")
    avg_confidence = (sum(row.analysis.confidence for row in rows) / processed) if processed else 0.0
    langgraph_rows = sum(1 for row in rows if "langgraph" in (row.analysis.model_used or ""))

    cards_gainers = "".join(_build_card(r, positive=True) for r in gainers)
    cards_losers = "".join(_build_card(r, positive=False) for r in losers)
    highlight_cards = _build_highlight_section(top_pick, most_potential)
    market_badges = _build_market_badges(market_counts)

    run_id = html.escape(str(run_meta.get("run_id", "n/a")))
    requested_date = html.escape(str(run_meta.get("requested_date", "n/a")))
    mode = html.escape(str(run_meta.get("mode", "n/a")))
    region = html.escape(str(run_meta.get("region", "n/a")))
    top = html.escape(str(run_meta.get("top", "n/a")))

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Daily Movers Digest</title>
  <style>
    :root {{
      --ink-1: #11131a;
      --ink-2: #2f3443;
      --ink-3: #646d82;
      --bg: #eef2f8;
      --panel: #ffffff;
      --line: #d7deea;
      --good: #0f8a5f;
      --bad: #b6263e;
      --watch: #1f6db3;
      --warn: #b66a00;
      --shadow: 0 20px 42px rgba(20, 29, 55, 0.11);
      --accent-grad: linear-gradient(128deg, #0f8a5f 0%, #1454a5 56%, #8f3fb8 100%);
      --hero-pattern:
        radial-gradient(900px 480px at 10% -20%, rgba(100, 223, 172, 0.37) 0%, rgba(100, 223, 172, 0) 62%),
        radial-gradient(950px 530px at 96% 5%, rgba(176, 121, 255, 0.34) 0%, rgba(176, 121, 255, 0) 58%),
        linear-gradient(148deg, #0b1222 0%, #101933 60%, #1a1739 100%);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      color: var(--ink-1);
      background:
        radial-gradient(circle at 8% 0%, #dff7eb 0%, rgba(223, 247, 235, 0) 40%),
        radial-gradient(circle at 95% 0%, #efe5ff 0%, rgba(239, 229, 255, 0) 36%),
        var(--bg);
      font-family: "Trebuchet MS", "Lucida Grande", "Geneva", sans-serif;
    }}

    .wrap {{
      max-width: 1300px;
      margin: 0 auto;
      padding: 26px 20px 30px;
    }}

    .hero {{
      position: relative;
      overflow: hidden;
      border-radius: 24px;
      background: var(--hero-pattern);
      color: #f2f7ff;
      box-shadow: var(--shadow);
      padding: 28px 26px 24px;
      margin-bottom: 18px;
      animation: reveal 0.58s ease-out both;
    }}

    .hero::after {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(110deg, rgba(255,255,255,0.0) 15%, rgba(255,255,255,0.11) 45%, rgba(255,255,255,0.0) 80%);
      transform: translateX(-70%);
      animation: sweep 5.6s linear infinite;
      pointer-events: none;
    }}

    .hero-title {{
      margin: 0;
      font-size: clamp(30px, 4vw, 42px);
      line-height: 1.03;
      font-family: "Georgia", "Times New Roman", serif;
      letter-spacing: 0.2px;
    }}

    .hero-sub {{
      margin: 10px 0 0;
      color: #d4e0fb;
      font-size: 14px;
    }}

    .meta-row {{
      margin-top: 15px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 7px 10px;
      border-radius: 999px;
      font-size: 12px;
      border: 1px solid rgba(213, 228, 255, 0.36);
      color: #ebf2ff;
      background: rgba(255, 255, 255, 0.1);
      backdrop-filter: blur(4px);
    }}

    .stats {{
      margin-top: 14px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(125px, 1fr));
      gap: 10px;
    }}

    .stat {{
      border-radius: 14px;
      padding: 10px 12px;
      background: rgba(255, 255, 255, 0.1);
      border: 1px solid rgba(214, 232, 255, 0.32);
    }}

    .stat .label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #d6e7ff;
    }}

    .stat .value {{
      margin-top: 2px;
      font-size: 20px;
      font-weight: 700;
      color: #ffffff;
    }}

    .split {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin: 14px 0 16px;
    }}

    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: var(--shadow);
      padding: 14px;
      animation: reveal 0.6s ease-out both;
    }}

    .panel h3 {{
      margin: 0 0 10px;
      font-size: 13px;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--ink-3);
    }}

    .mover-card {{
      border-radius: 12px;
      padding: 10px 11px;
      margin-bottom: 8px;
      border: 1px solid transparent;
      background: linear-gradient(130deg, #f9fcff 0%, #f5f8fd 100%);
      transition: transform 0.14s ease, border-color 0.14s ease;
    }}

    .mover-card:hover {{
      transform: translateY(-1px);
      border-color: #b7cae6;
    }}

    .mover-line {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 8px;
    }}

    .ticker {{
      font-size: 18px;
      font-weight: 800;
      letter-spacing: 0.3px;
    }}

    .pct {{
      font-weight: 800;
      font-size: 14px;
    }}

    .pct.good {{
      color: var(--good);
    }}

    .pct.bad {{
      color: var(--bad);
    }}

    .mover-meta {{
      margin-top: 4px;
      color: var(--ink-3);
      font-size: 12px;
    }}

    .toolbar {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: var(--shadow);
      padding: 11px;
      display: grid;
      grid-template-columns: minmax(220px, 1.8fr) 0.9fr 0.9fr auto auto;
      gap: 9px;
      align-items: center;
      margin-bottom: 12px;
      animation: reveal 0.62s ease-out both;
    }}

    .toolbar input,
    .toolbar select,
    .toolbar button {{
      border-radius: 10px;
      border: 1px solid var(--line);
      padding: 9px 10px;
      font-size: 13px;
      background: #fff;
      color: var(--ink-2);
    }}

    .toolbar input:focus,
    .toolbar select:focus,
    .toolbar button:focus {{
      outline: 2px solid #8cbaff;
      outline-offset: 1px;
    }}

    .toolbar button {{
      cursor: pointer;
      font-weight: 700;
      background: var(--accent-grad);
      color: #fff;
      border: none;
      box-shadow: 0 8px 20px rgba(19, 67, 138, 0.26);
    }}

    .toolbar .counter {{
      justify-self: end;
      color: var(--ink-3);
      font-family: "Consolas", "Courier New", monospace;
      font-size: 12px;
    }}

    .table-wrap {{
      overflow-x: auto;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
      animation: reveal 0.66s ease-out both;
    }}

    table {{
      width: 100%;
      min-width: 1300px;
      border-collapse: collapse;
    }}

    th,
    td {{
      border-bottom: 1px solid #e7edf6;
      padding: 10px 11px;
      vertical-align: top;
      font-size: 12.5px;
      text-align: left;
    }}

    th {{
      position: sticky;
      top: 0;
      z-index: 2;
      background: #f4f7fd;
      color: #405071;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-size: 11px;
      cursor: pointer;
      user-select: none;
    }}

    th.sorted-asc::after {{
      content: "  ↑";
      color: #1454a5;
      font-weight: 900;
    }}

    th.sorted-desc::after {{
      content: "  ↓";
      color: #1454a5;
      font-weight: 900;
    }}

    tr.row-in {{
      animation: rowIn 0.44s ease-out both;
    }}

    tr:hover td {{
      background: #f8fbff;
    }}

    .mono {{
      font-family: "Consolas", "Courier New", monospace;
      font-size: 12px;
    }}

    .symbol-link {{
      color: #0d4e87;
      font-weight: 700;
      text-decoration: none;
    }}

    .symbol-link:hover {{
      text-decoration: underline;
    }}

    .company-name {{
      color: var(--ink-3);
      font-size: 11px;
      margin-top: 2px;
    }}

    .pill {{
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.03em;
      border: 1px solid transparent;
      white-space: nowrap;
    }}

    .action-BUY {{
      background: #dbf7ea;
      color: #0d704a;
      border-color: #99dfc0;
    }}

    .action-WATCH {{
      background: #e1efff;
      color: var(--watch);
      border-color: #9ec4f2;
    }}

    .action-SELL {{
      background: #ffe2e8;
      color: #a01834;
      border-color: #f0a9b8;
    }}

    .confidence.high {{
      color: #0e7d53;
      font-weight: 700;
    }}

    .confidence.medium {{
      color: #9b6a00;
      font-weight: 700;
    }}

    .confidence.low {{
      color: #a01834;
      font-weight: 700;
    }}

    .review-yes {{
      color: #a75d00;
      font-weight: 800;
    }}

    .review-no {{
      color: #1f7d51;
      font-weight: 800;
    }}

    .muted {{
      color: var(--ink-3);
    }}

    details {{
      max-width: 345px;
    }}

    summary {{
      cursor: pointer;
      color: #0d4e87;
      font-weight: 700;
    }}

    .trace-list {{
      margin: 7px 0 0 18px;
      padding: 0;
    }}

    .trace-list li {{
      margin-bottom: 5px;
    }}

    .spark svg {{
      width: 132px;
      height: 30px;
      display: block;
    }}

    .empty {{
      color: var(--ink-3);
      font-style: italic;
    }}

    .highlight-section {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin: 14px 0;
    }}

    .highlight-card {{
      border-radius: 16px;
      padding: 16px 18px;
      border: 2px solid transparent;
      position: relative;
      overflow: hidden;
    }}

    .highlight-card.top-pick {{
      background: linear-gradient(135deg, #fdf8e8 0%, #fef3cd 100%);
      border-color: #f0c040;
      box-shadow: 0 8px 24px rgba(240, 192, 64, 0.22);
    }}

    .highlight-card.most-potential {{
      background: linear-gradient(135deg, #e8f4fd 0%, #cce5ff 100%);
      border-color: #4dabf7;
      box-shadow: 0 8px 24px rgba(77, 171, 247, 0.22);
    }}

    .highlight-card .badge {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      padding: 3px 9px;
      border-radius: 999px;
      margin-bottom: 8px;
    }}

    .highlight-card.top-pick .badge {{
      background: #f0c040;
      color: #5a4200;
    }}

    .highlight-card.most-potential .badge {{
      background: #4dabf7;
      color: #003d6b;
    }}

    .highlight-card .hl-ticker {{
      font-size: 22px;
      font-weight: 800;
      color: var(--ink-1);
    }}

    .highlight-card .hl-meta {{
      margin-top: 4px;
      font-size: 13px;
      color: var(--ink-2);
    }}

    .highlight-card .hl-reason {{
      margin-top: 6px;
      font-size: 12px;
      color: var(--ink-3);
    }}

    .market-badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin: 12px 0 14px;
      animation: reveal 0.6s ease-out both;
    }}

    .market-badge {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 6px 12px;
      border-radius: 10px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }}

    .market-badge .flag {{
      font-size: 15px;
    }}

    .agent-chip {{
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
      border-color: #667eea;
    }}

    @keyframes reveal {{
      from {{
        opacity: 0;
        transform: translateY(8px);
      }}
      to {{
        opacity: 1;
        transform: translateY(0);
      }}
    }}

    @keyframes rowIn {{
      from {{
        opacity: 0;
        transform: translateY(6px);
      }}
      to {{
        opacity: 1;
        transform: translateY(0);
      }}
    }}

    @keyframes sweep {{
      0% {{
        transform: translateX(-75%);
      }}
      100% {{
        transform: translateX(115%);
      }}
    }}

    @media (max-width: 960px) {{
      .split {{
        grid-template-columns: 1fr;
      }}

      .toolbar {{
        grid-template-columns: 1fr;
      }}

      .toolbar .counter {{
        justify-self: start;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1 class="hero-title">Daily Movers Assistant</h1>
      <p class="hero-sub">Evidence-first digest with traceable decisions and fast triage.</p>
      <div class="meta-row">
        <span class="chip"><strong>Run</strong> {run_id}</span>
        <span class="chip"><strong>Date</strong> {requested_date}</span>
        <span class="chip"><strong>Mode</strong> {mode}</span>
        <span class="chip"><strong>Region</strong> {region}</span>
        <span class="chip"><strong>Top</strong> {top}</span>
      </div>
      <div class="stats">
        <div class="stat"><div class="label">Rows</div><div class="value">{processed}</div></div>
        <div class="stat"><div class="label">Needs Review</div><div class="value">{needs_review}</div></div>
        <div class="stat"><div class="label">BUY</div><div class="value">{action_buy}</div></div>
        <div class="stat"><div class="label">WATCH</div><div class="value">{action_watch}</div></div>
        <div class="stat"><div class="label">SELL</div><div class="value">{action_sell}</div></div>
        <div class="stat"><div class="label">Avg Confidence</div><div class="value">{avg_confidence:.2f}</div></div>
        <div class="stat"><div class="label">Agent (LangGraph)</div><div class="value">{langgraph_rows}</div></div>
      </div>
    </section>

    {market_badges}
    {highlight_cards}

    <section class="split">
      <div class="panel">
        <h3>Top 3 Gainers</h3>
        {cards_gainers or '<div class="empty">No gainers in this slice.</div>'}
      </div>
      <div class="panel">
        <h3>Top 3 Losers</h3>
        {cards_losers or '<div class="empty">No losers in this slice.</div>'}
      </div>
    </section>

    <section class="toolbar">
      <input id="filterInput" type="search" placeholder="Search ticker, company, explanation, trace, reasons..." />
      <select id="actionFilter">
        <option value="ALL">All Actions</option>
        <option value="BUY">BUY</option>
        <option value="WATCH">WATCH</option>
        <option value="SELL">SELL</option>
      </select>
      <select id="reviewFilter">
        <option value="ALL">Review: All</option>
        <option value="YES">Needs Review</option>
        <option value="NO">No Review</option>
      </select>
      <button type="button" id="clearFilters">Clear Filters</button>
      <div class="counter" id="rowCount"></div>
    </section>

    <section class="table-wrap">
      <table id="moversTable">
        <thead>
          <tr>
            <th data-type="text">Symbol</th>
            <th data-type="text">Market</th>
            <th data-type="number">% Change</th>
            <th data-type="number">Price</th>
            <th data-type="number">Open</th>
            <th data-type="number">Close</th>
            <th data-type="number">Volume</th>
            <th data-type="text">Action</th>
            <th data-type="number">Confidence</th>
            <th data-type="text">Needs Review</th>
            <th data-type="text">Tags</th>
            <th data-type="text">Why It Moved</th>
            <th data-type="text">Decision Trace</th>
            <th data-type="text">Trend</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </section>
  </div>

  <script>
    (function() {{
      const table = document.getElementById("moversTable");
      const tbody = table.querySelector("tbody");
      const headers = [...table.querySelectorAll("th")];
      const filterInput = document.getElementById("filterInput");
      const actionFilter = document.getElementById("actionFilter");
      const reviewFilter = document.getElementById("reviewFilter");
      const clearFilters = document.getElementById("clearFilters");
      const rowCount = document.getElementById("rowCount");

      let sortIndex = null;
      let sortAsc = true;

      function normalizeNumber(value) {{
        const n = Number(value);
        return Number.isFinite(n) ? n : -999999999;
      }}

      function parseCellValue(cell, type) {{
        const raw = cell.dataset.sort || cell.innerText.trim();
        if (type === "number") {{
          return normalizeNumber(raw);
        }}
        return raw.toLowerCase();
      }}

      function applyFilters() {{
        const query = filterInput.value.trim().toLowerCase();
        const action = actionFilter.value;
        const review = reviewFilter.value;
        let visible = 0;

        [...tbody.querySelectorAll("tr")].forEach((tr) => {{
          const text = tr.innerText.toLowerCase();
          const rowAction = tr.dataset.action || "";
          const rowReview = tr.dataset.review || "";

          const matchQuery = !query || text.includes(query);
          const matchAction = action === "ALL" || rowAction === action;
          const matchReview = review === "ALL" || rowReview === review;
          const show = matchQuery && matchAction && matchReview;
          tr.style.display = show ? "" : "none";
          if (show) {{
            visible += 1;
          }}
        }});

        rowCount.textContent = `Visible rows: ${{visible}}`;
      }}

      function clearSortClasses() {{
        headers.forEach((h) => {{
          h.classList.remove("sorted-asc", "sorted-desc");
        }});
      }}

      headers.forEach((header, index) => {{
        header.addEventListener("click", () => {{
          const type = header.dataset.type || "text";
          const rows = [...tbody.querySelectorAll("tr")];

          if (sortIndex === index) {{
            sortAsc = !sortAsc;
          }} else {{
            sortIndex = index;
            sortAsc = true;
          }}

          rows.sort((a, b) => {{
            const av = parseCellValue(a.children[index], type);
            const bv = parseCellValue(b.children[index], type);
            if (type === "number") {{
              return sortAsc ? av - bv : bv - av;
            }}
            return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
          }});

          rows.forEach((row) => tbody.appendChild(row));
          clearSortClasses();
          header.classList.add(sortAsc ? "sorted-asc" : "sorted-desc");
          applyFilters();
        }});
      }});

      filterInput.addEventListener("input", applyFilters);
      actionFilter.addEventListener("change", applyFilters);
      reviewFilter.addEventListener("change", applyFilters);
      clearFilters.addEventListener("click", () => {{
        filterInput.value = "";
        actionFilter.value = "ALL";
        reviewFilter.value = "ALL";
        applyFilters();
      }});

      [...tbody.querySelectorAll("tr")].forEach((tr, idx) => {{
        tr.classList.add("row-in");
        tr.style.animationDelay = `${{Math.min(idx * 20, 280)}}ms`;
      }});

      applyFilters();
    }})();
  </script>
</body>
</html>
"""


def _build_card(row: ReportRow, *, positive: bool) -> str:
    ticker = html.escape(row.ticker.ticker)
    pct = row.ticker.pct_change or 0.0
    cls = "good" if (pct >= 0 if positive else pct <= 0) else "bad"
    action = html.escape(row.analysis.action.value)
    confidence = f"{row.analysis.confidence:.2f}"
    reason = html.escape(", ".join(row.needs_review_reason[:2])) if row.needs_review_reason else "none"

    return (
        "<div class='mover-card'>"
        "<div class='mover-line'>"
        f"<span class='ticker'>{ticker}</span>"
        f"<span class='pct {cls}'>{pct:+.2f}%</span>"
        "</div>"
        f"<div class='mover-meta'>Action: {action} | Conf: {confidence} | Review reason: {reason}</div>"
        "</div>"
    )


def _build_table_row(row: ReportRow, idx: int) -> str:
    flat = row.to_flat_dict()

    ticker_raw = str(flat.get("ticker") or "")
    ticker = html.escape(ticker_raw)
    ticker_url = f"https://finance.yahoo.com/quote/{quote(ticker_raw, safe='')}"
    company = html.escape(str(flat.get("name") or "Unknown"))
    pct = float(flat.get("pct_change") or 0.0)
    price_val = _to_float(flat.get("price"))
    open_val = _to_float(flat.get("open_price"))
    close_val = _to_float(flat.get("close_price"))
    price_sort = price_val if price_val is not None else -999999
    open_sort = open_val if open_val is not None else -999999
    close_sort = close_val if close_val is not None else -999999
    volume = float(flat.get("volume") or 0.0)
    price_display = _fmt_price(price_val)
    open_display = _fmt_price(open_val)
    close_display = _fmt_price(close_val)
    action = html.escape(str(flat.get("action") or "WATCH"))
    confidence = float(flat.get("confidence") or 0.0)
    why = html.escape(str(flat.get("why_it_moved") or ""))
    trace = html.escape(str(flat.get("decision_trace") or ""))
    reasons = html.escape(str(flat.get("needs_review_reason") or ""))
    errors = html.escape(str(flat.get("errors") or ""))

    review_value = "YES" if row.needs_review else "NO"
    review_cls = "review-yes" if row.needs_review else "review-no"
    confidence_cls = "high" if confidence >= 0.8 else ("medium" if confidence >= 0.6 else "low")
    action_cls = f"action-{action}"

    # Market detection
    market_label = _detect_market(row.ticker.ticker, row.ticker.market)
    market_info = _MARKET_INFO.get(market_label, ("🌍", "Other"))
    market_badge_html = f"<span class='market-badge'><span class='flag'>{market_info[0]}</span>{market_info[1]}</span>"

    # Recommendation tags
    rec_tags = row.recommendation_tags or []
    rec_tags_html = " ".join(
        f"<span class='pill action-{_tag_style(t)}'>{html.escape(t)}</span>"
        for t in rec_tags
    ) if rec_tags else "<span class='muted'>standard</span>"

    rule_items = "".join(
        f"<li>{html.escape(rule)}</li>" for rule in row.analysis.decision_trace.rules_triggered[:4]
    )
    if not rule_items:
        rule_items = "<li>No explicit rules</li>"

    headline_items = "".join(
        _build_headline_item(h.title, h.url)
        for h in row.analysis.decision_trace.evidence_used[:3]
        if h.title
    )
    if not headline_items:
        headline_items = "<li>No evidence headlines</li>"

    spark = _sparkline_svg(row.enrichment.price_series)

    return f"""
<tr data-action="{action}" data-review="{review_value}" data-row="{idx}">
  <td data-sort="{ticker}">
    <a class="symbol-link mono" href="{ticker_url}" target="_blank" rel="noopener noreferrer">{ticker}</a>
    <div class="company-name">{company}</div>
  </td>
  <td data-sort="{market_label}">{market_badge_html}</td>
  <td data-sort="{pct:.6f}" class="mono">{pct:+.2f}%</td>
  <td data-sort="{price_sort:.6f}" class="mono">{price_display}</td>
  <td data-sort="{open_sort:.6f}" class="mono">{open_display}</td>
  <td data-sort="{close_sort:.6f}" class="mono">{close_display}</td>
  <td data-sort="{volume:.6f}" class="mono">{volume:,.0f}</td>
  <td data-sort="{action}"><span class="pill {action_cls}">{action}</span></td>
  <td data-sort="{confidence:.6f}" class="confidence {confidence_cls}">{confidence:.2f}</td>
  <td data-sort="{review_value}">
    <div class="{review_cls}">{review_value}</div>
    <div class="muted">{reasons or "none"}</div>
  </td>
  <td>{rec_tags_html}</td>
  <td>{why}</td>
  <td>
    <details>
      <summary>Open Trace</summary>
      <div class="muted" style="margin-top:6px;">{trace}</div>
      <ul class="trace-list">{rule_items}</ul>
      <ul class="trace-list">{headline_items}</ul>
      <div class="muted" style="margin-top:6px;">{errors}</div>
    </details>
  </td>
  <td class="spark">{spark}</td>
</tr>
"""


def _sparkline_svg(points: list[float]) -> str:
    if len(points) < 2:
        return "<span class='mono muted'>n/a</span>"

    trimmed = points[-15:]
    min_v = min(trimmed)
    max_v = max(trimmed)
    if min_v == max_v:
        max_v = min_v + 1.0

    width = 132
    height = 30
    x_pad = 3
    y_pad = 4

    def x(i: int) -> float:
        return x_pad + (i / (len(trimmed) - 1)) * (width - (2 * x_pad))

    def y(v: float) -> float:
        ratio = (v - min_v) / (max_v - min_v)
        return (height - y_pad) - ratio * (height - (2 * y_pad))

    coords = " ".join(f"{x(i):.2f},{y(v):.2f}" for i, v in enumerate(trimmed))
    first = trimmed[0]
    last = trimmed[-1]
    stroke = "#0f8a5f" if last >= first else "#b6263e"

    return (
        f"<svg viewBox='0 0 {width} {height}' preserveAspectRatio='none'>"
        f"<rect x='0' y='0' width='{width}' height='{height}' fill='#eef3fb' rx='5' />"
        f"<polyline points='{coords}' fill='none' stroke='{stroke}' stroke-width='2.15' />"
        "</svg>"
    )


# ---------------------------------------------------------------------------
# Market detection & badge helpers
# ---------------------------------------------------------------------------

_MARKET_INFO: dict[str, tuple[str, str]] = {
    "us": ("🇺🇸", "US"),
    "tase": ("🇮🇱", "TASE"),
    "uk": ("🇬🇧", "UK"),
    "eu": ("🇪🇺", "EU"),
    "crypto": ("₿", "Crypto"),
    "other": ("🌍", "Other"),
}


def _detect_market(ticker: str, market_hint: str | None) -> str:
    """Detect market from ticker suffix and market hint."""
    t = ticker.upper()
    if t.endswith(".TA"):
        return "tase"
    if t.endswith(".L"):
        return "uk"
    if any(t.endswith(s) for s in (".PA", ".DE", ".AS", ".MI", ".MC")):
        return "eu"
    if "-USD" in t or t in ("BTC", "ETH", "SOL", "XRP", "DOGE", "BNB"):
        return "crypto"
    if market_hint:
        hint = market_hint.lower()
        if hint in _MARKET_INFO:
            return hint
        if hint in ("il",):
            return "tase"
    return "us"


def _build_market_badges(market_counts: dict[str, int]) -> str:
    """Build the market badges row HTML."""
    if not market_counts:
        return ""
    badges = []
    for mkt, count in sorted(market_counts.items(), key=lambda x: -x[1]):
        info = _MARKET_INFO.get(mkt, ("🌍", "Other"))
        badges.append(
            f"<span class='market-badge'><span class='flag'>{info[0]}</span>{info[1]}: {count}</span>"
        )
    return f"<div class='market-badges'>{''.join(badges)}</div>"


def _build_highlight_section(
    top_pick: ReportRow | None,
    most_potential: ReportRow | None,
) -> str:
    """Build the highlight cards for Top Pick and Most Potential."""
    if not top_pick and not most_potential:
        return ""

    cards = []
    if top_pick:
        t = top_pick
        pct = t.ticker.pct_change or 0.0
        cards.append(
            f"<div class='highlight-card top-pick'>"
            f"<div class='badge'>🏆 Top Recommended Pick</div>"
            f"<div class='hl-ticker'>{html.escape(t.ticker.ticker)}</div>"
            f"<div class='hl-meta'>{html.escape(t.ticker.name or '')} &mdash; "
            f"{pct:+.2f}% | Confidence: {t.analysis.confidence:.2f} | {t.analysis.action.value}</div>"
            f"<div class='hl-reason'>{html.escape(t.analysis.why_it_moved)}</div>"
            f"</div>"
        )
    else:
        cards.append(
            "<div class='highlight-card top-pick'>"
            "<div class='badge'>🏆 Top Pick</div>"
            "<div class='hl-meta'>No strong BUY signal with high confidence found in this run.</div>"
            "</div>"
        )

    if most_potential:
        t = most_potential
        pct = t.ticker.pct_change or 0.0
        cards.append(
            f"<div class='highlight-card most-potential'>"
            f"<div class='badge'>📈 Most Potential</div>"
            f"<div class='hl-ticker'>{html.escape(t.ticker.ticker)}</div>"
            f"<div class='hl-meta'>{html.escape(t.ticker.name or '')} &mdash; "
            f"{pct:+.2f}% | Sentiment: {t.analysis.sentiment:+.2f} | {t.analysis.action.value}</div>"
            f"<div class='hl-reason'>{html.escape(t.analysis.why_it_moved)}</div>"
            f"</div>"
        )
    else:
        cards.append(
            "<div class='highlight-card most-potential'>"
            "<div class='badge'>📈 Most Potential</div>"
            "<div class='hl-meta'>No moderate-confidence upside candidate identified.</div>"
            "</div>"
        )

    return f"<section class='highlight-section'>{''.join(cards)}</section>"


def _to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.2f}"


def _safe_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme in {"http", "https"}:
        return value.strip()
    return None


def _build_headline_item(title: str, url: str | None) -> str:
    safe_url = _safe_url(url)
    safe_title = html.escape(title or "")
    if safe_url:
        return (
            f"<li><a href='{html.escape(safe_url)}' target='_blank' "
            f"rel='noopener noreferrer'>{safe_title}</a></li>"
        )
    return f"<li>{safe_title}</li>"


def _tag_style(tag: str) -> str:
    """Map recommendation tag to a pill style class suffix."""
    if "top_pick" in tag:
        return "BUY"
    if "most_potential" in tag:
        return "WATCH"
    if "contrarian" in tag:
        return "SELL"
    if "momentum" in tag:
        return "BUY"
    return "WATCH"
