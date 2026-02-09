from __future__ import annotations


class DailyMoversError(Exception):
    """Base error type for application-specific exceptions."""


class ExternalCallError(DailyMoversError):
    """Raised for external dependency failures."""

    def __init__(self, message: str, *, stage: str, url: str | None = None):
        super().__init__(message)
        self.stage = stage
        self.url = url


class HTTPFetchError(ExternalCallError):
    """HTTP call failed."""


class IngestionError(ExternalCallError):
    """Ingestion stage failed."""


class EnrichmentError(ExternalCallError):
    """Enrichment stage failed."""


class AnalysisError(ExternalCallError):
    """Analysis stage failed."""


class EmailDeliveryError(ExternalCallError):
    """Email delivery failed."""
