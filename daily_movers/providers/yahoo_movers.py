from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from bs4 import BeautifulSoup

from daily_movers.config import REGION_UNIVERSES
from daily_movers.errors import HTTPFetchError, IngestionError
from daily_movers.models import ErrorInfo, TickerRow
from daily_movers.storage.cache import HttpClient
from daily_movers.storage.runs import StructuredLogger


US_SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
US_HTML_FALLBACK_URL = "https://finance.yahoo.com/most-active"
CHART_URL_TEMPLATE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def get_movers(
    *,
    region: str,
    source: str = "auto",
    top_n: int,
    client: HttpClient,
    logger: StructuredLogger,
) -> list[TickerRow]:
    normalized_region = region.lower()
    normalized_source = (source or "auto").lower()
    if normalized_source not in {"auto", "most-active", "universe"}:
        raise IngestionError(
            f"unsupported movers source: {source}",
            stage="ingestion",
            url=None,
        )

    if normalized_region == "us" and normalized_source in {"auto", "most-active"}:
        return get_us_movers(top_n=top_n, client=client, logger=logger)

    universe = REGION_UNIVERSES.get(normalized_region)
    if not universe:
        raise IngestionError(
            f"unsupported region for movers mode: {region}",
            stage="ingestion",
            url=None,
        )

    if normalized_source == "most-active":
        raise IngestionError(
            f"most-active source is only supported for region=us (got region={region})",
            stage="ingestion",
            url=US_SCREENER_URL,
        )

    rows = build_rows_from_symbols(
        symbols=universe,
        top_n=top_n,
        source=f"yahoo_chart_{normalized_region}_universe",
        market=normalized_region,
        client=client,
        logger=logger,
    )
    ranked = sorted(
        rows,
        key=lambda r: (
            abs(r.pct_change) if r.pct_change is not None else -1,
            r.volume if r.volume is not None else -1,
        ),
        reverse=True,
    )
    return ranked[:top_n]


def get_watchlist_rows(
    *,
    watchlist_path: Path,
    top_n: int,
    client: HttpClient,
    logger: StructuredLogger,
) -> list[TickerRow]:
    symbols = load_watchlist_symbols(watchlist_path)
    rows = build_rows_from_symbols(
        symbols=symbols,
        top_n=top_n,
        source="watchlist_chart",
        market="watchlist",
        client=client,
        logger=logger,
    )
    return rows[:top_n] if top_n > 0 else rows


def load_watchlist_symbols(path: Path) -> list[str]:
    if not path.exists():
        raise IngestionError(
            f"watchlist file does not exist: {path}",
            stage="ingestion",
            url=str(path),
        )

    if path.suffix.lower() in {".yaml", ".yml"}:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise IngestionError(
            "watchlist must be yaml/yml/json",
            stage="ingestion",
            url=str(path),
        )

    if isinstance(raw, dict):
        symbols = raw.get("symbols", [])
    elif isinstance(raw, list):
        symbols = raw
    else:
        raise IngestionError(
            "watchlist content must be list or object with symbols",
            stage="ingestion",
            url=str(path),
        )

    normalized: list[str] = []
    for item in symbols:
        if isinstance(item, str):
            symbol = item.strip().upper()
        elif isinstance(item, dict) and "symbol" in item:
            symbol = str(item["symbol"]).strip().upper()
        else:
            continue
        if symbol and symbol not in normalized:
            normalized.append(symbol)

    if not normalized:
        raise IngestionError(
            "watchlist has no valid symbols",
            stage="ingestion",
            url=str(path),
        )
    return normalized


def get_us_movers(
    *,
    top_n: int,
    client: HttpClient,
    logger: StructuredLogger,
) -> list[TickerRow]:
    try:
        data = client.get_json(
            US_SCREENER_URL,
            params={
                "formatted": "true",
                "scrIds": "most_actives",
                "count": str(top_n),
                "start": "0",
            },
            stage="ingestion",
            logger=logger,
        )
        quotes = (((data.get("finance") or {}).get("result") or [{}])[0]).get("quotes") or []
        rows = [_parse_screener_quote(q) for q in quotes[:top_n]]
        if not rows:
            raise IngestionError(
                "screener returned no quotes",
                stage="ingestion",
                url=US_SCREENER_URL,
            )
        return rows
    except (HTTPFetchError, IngestionError, KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning(
            "ingestion_primary_failed",
            stage="ingestion",
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            url=US_SCREENER_URL,
        )
        return _get_us_movers_html_fallback(top_n=top_n, client=client, logger=logger)


def _parse_screener_quote(raw: dict[str, Any]) -> TickerRow:
    symbol = str(raw.get("symbol", "")).upper()
    if not symbol:
        raise IngestionError("missing symbol in screener quote", stage="ingestion", url=US_SCREENER_URL)

    price = _as_float(raw.get("regularMarketPrice"))
    abs_change = _as_float(raw.get("regularMarketChange"))
    pct_change = _as_float(raw.get("regularMarketChangePercent"))
    volume = _as_float(raw.get("regularMarketVolume"))

    return TickerRow(
        ticker=symbol,
        name=str(raw.get("shortName") or raw.get("longName") or symbol),
        price=price,
        abs_change=abs_change,
        pct_change=pct_change,
        volume=volume,
        currency=str(raw.get("currency")) if raw.get("currency") else None,
        exchange=str(raw.get("exchange")) if raw.get("exchange") else None,
        market="us",
        ingestion_source="yahoo_screener_json",
        ingestion_fallback_used=False,
    )


def _get_us_movers_html_fallback(
    *,
    top_n: int,
    client: HttpClient,
    logger: StructuredLogger,
) -> list[TickerRow]:
    try:
        html = client.get_text(
            US_HTML_FALLBACK_URL,
            stage="ingestion",
            logger=logger,
        )
        soup = BeautifulSoup(html, "html.parser")
        rows: list[TickerRow] = []
        for tr in soup.select("table tbody tr")[:top_n]:
            cols = tr.find_all("td")
            if len(cols) < 7:
                continue
            symbol = cols[0].get_text(strip=True).upper()
            name = cols[1].get_text(strip=True)
            price = _parse_human_number(cols[2].get_text(strip=True))
            abs_change = _parse_human_number(cols[3].get_text(strip=True))
            pct_change_text = cols[4].get_text(strip=True).replace("%", "")
            pct_change = _parse_human_number(pct_change_text)
            volume = _parse_human_number(cols[5].get_text(strip=True))

            if not symbol:
                continue

            rows.append(
                TickerRow(
                    ticker=symbol,
                    name=name,
                    price=price,
                    abs_change=abs_change,
                    pct_change=pct_change,
                    volume=volume,
                    market="us",
                    ingestion_source="yahoo_most_active_html",
                    ingestion_fallback_used=True,
                )
            )

        if not rows:
            raise IngestionError(
                "html fallback produced no rows",
                stage="ingestion",
                url=US_HTML_FALLBACK_URL,
            )
        return rows
    except (HTTPFetchError, ValueError, IngestionError) as exc:
        raise IngestionError(
            f"US fallback ingestion failed: {exc}",
            stage="ingestion",
            url=US_HTML_FALLBACK_URL,
        ) from exc


def build_rows_from_symbols(
    *,
    symbols: list[str],
    top_n: int,
    source: str,
    market: str,
    client: HttpClient,
    logger: StructuredLogger,
) -> list[TickerRow]:
    rows: list[TickerRow] = []
    for symbol in symbols:
        rows.append(
            _row_from_chart(
                symbol=symbol,
                source=source,
                market=market,
                client=client,
                logger=logger,
            )
        )

    return rows


def _row_from_chart(
    *,
    symbol: str,
    source: str,
    market: str,
    client: HttpClient,
    logger: StructuredLogger,
) -> TickerRow:
    url = CHART_URL_TEMPLATE.format(symbol=symbol)
    try:
        payload = client.get_json(
            url,
            params={"range": "5d", "interval": "1d"},
            stage="ingestion",
            logger=logger,
        )
        result = (((payload.get("chart") or {}).get("result") or [None])[0])
        if not result:
            raise IngestionError(
                f"missing chart result for {symbol}",
                stage="ingestion",
                url=url,
            )
        meta = result.get("meta") or {}
        quote = (((result.get("indicators") or {}).get("quote") or [None])[0]) or {}
        closes = [v for v in (quote.get("close") or []) if isinstance(v, (int, float))]
        volumes = [v for v in (quote.get("volume") or []) if isinstance(v, (int, float))]

        price = _as_float(meta.get("regularMarketPrice"))
        if price is None and closes:
            price = float(closes[-1])

        prev = _as_float(meta.get("chartPreviousClose"))
        if prev is None and len(closes) >= 2:
            prev = float(closes[-2])

        abs_change = (price - prev) if (price is not None and prev is not None) else None
        pct_change = ((abs_change / prev) * 100.0) if (abs_change is not None and prev not in (0, None)) else None
        volume = float(volumes[-1]) if volumes else None

        return TickerRow(
            ticker=symbol,
            name=str(meta.get("shortName") or meta.get("longName") or symbol),
            price=price,
            abs_change=abs_change,
            pct_change=pct_change,
            volume=volume,
            currency=str(meta.get("currency")) if meta.get("currency") else None,
            exchange=str(meta.get("exchangeName")) if meta.get("exchangeName") else None,
            market=market,
            ingestion_source=source,
            ingestion_fallback_used=False,
        )
    except (HTTPFetchError, IngestionError, KeyError, IndexError, TypeError, ValueError) as exc:
        return TickerRow(
            ticker=symbol,
            name=symbol,
            market=market,
            ingestion_source=source,
            ingestion_fallback_used=False,
            errors=[
                ErrorInfo(
                    stage="ingestion",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    url=url,
                    fallback_used=False,
                )
            ],
        )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict) and "raw" in value:
        return _as_float(value["raw"])
    if isinstance(value, str):
        return _parse_human_number(value)
    return None


def _parse_human_number(text: str) -> float | None:
    t = text.strip().replace(",", "")
    if not t or t in {"-", "--"}:
        return None

    suffix_scale = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)([KMBT]?)", t, flags=re.IGNORECASE)
    if not match:
        try:
            return float(t)
        except ValueError:
            return None

    number = float(match.group(1))
    suffix = match.group(2).upper()
    return number * suffix_scale.get(suffix, 1)
