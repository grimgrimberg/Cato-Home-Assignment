from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from daily_movers.errors import EnrichmentError, HTTPFetchError
from daily_movers.models import Enrichment, ErrorInfo, Headline, TickerRow
from daily_movers.storage.cache import HttpClient
from daily_movers.storage.runs import StructuredLogger


CHART_URL_TEMPLATE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
QUOTE_HTML_TEMPLATE = "https://finance.yahoo.com/quote/{symbol}"
RSS_TEMPLATE = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"


def enrich_ticker(
    *,
    row: TickerRow,
    client: HttpClient,
    logger: StructuredLogger,
) -> Enrichment:
    errors: list[ErrorInfo] = []
    headlines: list[Headline] = []
    sector: str | None = None
    industry: str | None = None
    earnings_date: str | None = None
    price_series: list[float] = []

    try:
        price_series = fetch_price_series(row.ticker, client=client, logger=logger)
    except EnrichmentError as exc:
        errors.append(
            ErrorInfo(
                stage="enrichment",
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                url=exc.url,
            )
        )

    try:
        headlines = fetch_headlines(row.ticker, client=client, logger=logger)
    except EnrichmentError as exc:
        errors.append(
            ErrorInfo(
                stage="enrichment",
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                url=exc.url,
            )
        )

    try:
        sector, industry, earnings_date = fetch_quote_profile_fields(row.ticker, client=client, logger=logger)
    except EnrichmentError as exc:
        # Quote profile fields are optional enrichment. We log and continue without
        # marking the row as a hard error when Yahoo blocks quote pages.
        logger.warning(
            "optional_profile_enrichment_failed",
            stage="enrichment",
            symbol=row.ticker,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            url=exc.url,
        )

    return Enrichment(
        sector=sector,
        industry=industry,
        earnings_date=earnings_date,
        headlines=headlines,
        price_series=price_series,
        errors=errors,
    )


def fetch_price_series(
    symbol: str,
    *,
    client: HttpClient,
    logger: StructuredLogger,
) -> list[float]:
    url = CHART_URL_TEMPLATE.format(symbol=symbol)
    try:
        payload = client.get_json(
            url,
            params={"range": "1mo", "interval": "1d"},
            stage="enrichment",
            logger=logger,
        )
        result = (((payload.get("chart") or {}).get("result") or [None])[0])
        if not result:
            raise EnrichmentError(
                f"missing chart result for {symbol}",
                stage="enrichment",
                url=url,
            )
        quote = (((result.get("indicators") or {}).get("quote") or [None])[0]) or {}
        closes = [float(v) for v in (quote.get("close") or []) if isinstance(v, (int, float))]
        return closes[-15:]
    except (HTTPFetchError, KeyError, IndexError, TypeError, ValueError, EnrichmentError) as exc:
        if isinstance(exc, EnrichmentError):
            raise
        raise EnrichmentError(str(exc), stage="enrichment", url=url) from exc


def fetch_headlines(
    symbol: str,
    *,
    client: HttpClient,
    logger: StructuredLogger,
    top_n: int = 3,
) -> list[Headline]:
    url = RSS_TEMPLATE.format(symbol=symbol)
    try:
        xml_text = client.get_text(url, stage="enrichment", logger=logger)
        root = ET.fromstring(xml_text)
        items = root.findall("./channel/item")
        headlines: list[Headline] = []
        for item in items[:top_n]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            published_at: str | None = None
            if pub:
                try:
                    published_at = parsedate_to_datetime(pub).isoformat()
                except ValueError:
                    published_at = pub
            if title and link:
                headlines.append(Headline(title=title, url=link, published_at=published_at))
        return headlines
    except (HTTPFetchError, ET.ParseError, TypeError) as exc:
        raise EnrichmentError(str(exc), stage="enrichment", url=url) from exc


def fetch_quote_profile_fields(
    symbol: str,
    *,
    client: HttpClient,
    logger: StructuredLogger,
) -> tuple[str | None, str | None, str | None]:
    url = QUOTE_HTML_TEMPLATE.format(symbol=symbol)
    try:
        html = client.get_text(url, stage="enrichment", logger=logger)

        sector_match = re.search(r'\\"sector\\":\\"([^\\"]+)\\"', html)
        industry_match = re.search(r'\\"industry\\":\\"([^\\"]+)\\"', html)
        earnings_match = re.search(
            r"Earnings Date \(est\.\)\s*</span>\s*<span[^>]*>([^<]+)</span>",
            html,
            flags=re.IGNORECASE,
        )

        sector = sector_match.group(1).strip() if sector_match else None
        industry = industry_match.group(1).strip() if industry_match else None
        earnings_date = earnings_match.group(1).strip() if earnings_match else None

        return sector, industry, earnings_date
    except HTTPFetchError as exc:
        raise EnrichmentError(str(exc), stage="enrichment", url=url) from exc
