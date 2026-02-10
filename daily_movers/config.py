from __future__ import annotations

"""Application configuration (loaded from environment variables + .env).

Design:
- All settings have sensible defaults for demo/dev use.
- Optional features (OpenAI, SMTP) are disabled-by-default.
- Environment variables always override .env file values.
"""

from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


# Small curated universes for non-US regions (used when Yahoo screener isn't
# available or when --source=universe is explicitly requested).
REGION_UNIVERSES: dict[str, list[str]] = {
    "us": [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "TSLA",
        "META",
        "GOOGL",
        "AMD",
        "PLTR",
        "INTC",
        "SOFI",
        "NIO",
    ],
    "il": ["TEVA.TA", "NICE.TA", "ICL.TA", "DSCT.TA", "POLI.TA", "LUMI.TA"],
    "uk": ["BP.L", "HSBA.L", "VOD.L", "BARC.L", "AZN.L", "SHEL.L"],
    "eu": ["ASML.AS", "SAN.PA", "BMW.DE", "SIE.DE", "AIR.PA", "OR.PA"],
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "BNB-USD"],
}


class AppConfig(BaseModel):
    # HTTP cache settings (Yahoo endpoints can be slow/flaky)
    cache_dir: Path = Path(".cache/http")
    cache_ttl_seconds: int = 1800  # 30 minutes
    
    # Concurrency controls (prevents hammering Yahoo)
    max_workers: int = 5
    max_requests_per_host: int = 5
    request_timeout_seconds: int = 20
    openai_timeout_seconds: int = 45
    
    user_agent: str = "DailyMoversAssistant/0.1"
    log_level: str = "INFO"

    # OpenAI settings (optional; pipeline works without an API key)
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    analysis_model: str = "gpt-4o-mini"

    # SMTP settings (optional; digest.eml is always written even without SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_ssl_port: int = 465
    smtp_username: str | None = None
    smtp_password: str | None = None
    from_email: str | None = None
    self_email: str | None = None

    @field_validator(
        "cache_ttl_seconds",
        "max_workers",
        "max_requests_per_host",
        "request_timeout_seconds",
        "openai_timeout_seconds",
    )
    @classmethod
    def _positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be positive")
        return value

    @field_validator("smtp_port", "smtp_ssl_port")
    @classmethod
    def _valid_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("port must be in 1..65535")
        return value

    @property
    def openai_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def smtp_ready(self) -> bool:
        required = [
            self.smtp_host,
            self.smtp_username,
            self.smtp_password,
            self.from_email,
            self.self_email,
        ]
        return all(bool(v) for v in required)


def load_config(env_file: str | None = ".env") -> AppConfig:
    if env_file:
        # Load .env values but let shell environment variables win
        # (important for scripts that set SMTP_* before calling the CLI)
        load_dotenv(env_file, override=False)
    return AppConfig(
        openai_api_key=_getenv_opt("OPENAI_API_KEY"),
        analysis_model=_getenv_str("ANALYSIS_MODEL", "gpt-4o-mini"),
        openai_base_url=_getenv_str("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        smtp_host=_getenv_str("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(_getenv_str("SMTP_PORT", "587")),
        smtp_ssl_port=int(_getenv_str("SMTP_SSL_PORT", "465")),
        smtp_username=_getenv_opt("SMTP_USERNAME"),
        smtp_password=_getenv_opt("SMTP_PASSWORD"),
        from_email=_getenv_opt("FROM_EMAIL"),
        self_email=_getenv_opt("SELF_EMAIL"),
        cache_dir=Path(_getenv_str("CACHE_DIR", ".cache/http")),
        cache_ttl_seconds=int(_getenv_str("CACHE_TTL_SECONDS", "1800")),
        max_workers=int(_getenv_str("MAX_WORKERS", "5")),
        max_requests_per_host=int(_getenv_str("MAX_REQUESTS_PER_HOST", "5")),
        request_timeout_seconds=int(_getenv_str("REQUEST_TIMEOUT_SECONDS", "20")),
        openai_timeout_seconds=int(_getenv_str("OPENAI_TIMEOUT_SECONDS", "45")),
        log_level=_getenv_str("LOG_LEVEL", "INFO"),
    )


def _getenv_opt(name: str) -> str | None:
    import os

    value = os.getenv(name)
    if value is None or value == "":
        return None
    return value


def _getenv_str(name: str, default: str) -> str:
    value = _getenv_opt(name)
    return value if value is not None else default
