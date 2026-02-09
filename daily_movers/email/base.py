from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import Protocol


class EmlWriter(Protocol):
    def build_message(self, *, subject: str, html_body: str, from_email: str, to_email: str) -> EmailMessage:
        """Build an RFC822 message."""

    def write_message(self, *, message: EmailMessage, out_path: Path) -> None:
        """Persist message to .eml."""


class SmtpSender(Protocol):
    def can_send(self) -> bool:
        """Whether backend has enough configuration to attempt send."""

    def send_message(self, *, message: EmailMessage) -> None:
        """Send an already constructed message."""
