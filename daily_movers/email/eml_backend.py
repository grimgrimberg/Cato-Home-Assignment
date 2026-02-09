from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

from daily_movers.render.eml import build_digest_eml, write_eml_file
from daily_movers.storage.runs import StructuredLogger


class EmlBackend:
    """Default no-setup backend that always emits digest.eml."""

    def __init__(self, *, logger: StructuredLogger) -> None:
        self.logger = logger

    def build_message(self, *, subject: str, html_body: str, from_email: str, to_email: str) -> EmailMessage:
        message = build_digest_eml(
            subject=subject,
            html_body=html_body,
            from_email=from_email,
            to_email=to_email,
        )
        self.logger.info(
            "email_message_built",
            stage="email",
            status="ok",
            fallback_used=False,
            from_email=from_email,
            to_email=to_email,
        )
        return message

    def write_message(self, *, message: EmailMessage, out_path: Path) -> None:
        write_eml_file(message=message, out_path=out_path)
        self.logger.info(
            "email_eml_written",
            stage="email",
            status="ok",
            fallback_used=False,
            path=str(out_path),
        )
