"""Pluggable email backends for digest delivery."""

from daily_movers.email.eml_backend import EmlBackend
from daily_movers.email.smtp_backend import SmtpBackend

__all__ = ["EmlBackend", "SmtpBackend"]
