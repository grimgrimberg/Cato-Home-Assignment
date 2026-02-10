from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from daily_movers.config import AppConfig
from daily_movers.errors import EmailDeliveryError
from daily_movers.storage.runs import StructuredLogger


class SmtpBackend:
    """SMTP backend with STARTTLS primary and SSL fallback."""

    def __init__(self, *, config: AppConfig, logger: StructuredLogger) -> None:
        self.config = config
        self.logger = logger

    def can_send(self) -> bool:
        return self.config.smtp_ready

    def send_message(self, *, message: EmailMessage) -> None:
        if not self.can_send():
            raise EmailDeliveryError(
                "SMTP configuration incomplete",
                stage="email",
                url=self.config.smtp_host,
            )

        host = self.config.smtp_host
        username = str(self.config.smtp_username)
        password = str(self.config.smtp_password)

        try:
            with smtplib.SMTP(host, self.config.smtp_port, timeout=self.config.request_timeout_seconds) as server:
                server.ehlo()
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
                server.login(username, password)
                server.send_message(message)
            self.logger.info(
                "email_sent_starttls",
                stage="email",
                status="ok",
                url=f"smtp://{host}:{self.config.smtp_port}",
            )
            return
        except Exception as starttls_exc:  # noqa: BLE001
            self.logger.warning(
                "email_starttls_failed",
                stage="email",
                error_type=starttls_exc.__class__.__name__,
                error_message=str(starttls_exc),
                url=f"smtp://{host}:{self.config.smtp_port}",
            )

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                host,
                self.config.smtp_ssl_port,
                timeout=self.config.request_timeout_seconds,
                context=context,
            ) as server:
                server.login(username, password)
                server.send_message(message)
            self.logger.info(
                "email_sent_ssl",
                stage="email",
                status="ok",
                url=f"smtps://{host}:{self.config.smtp_ssl_port}",
            )
            return
        except Exception as ssl_exc:  # noqa: BLE001
            raise EmailDeliveryError(
                f"SMTP send failed on STARTTLS and SSL: {ssl_exc}",
                stage="email",
                url=host,
            ) from ssl_exc
