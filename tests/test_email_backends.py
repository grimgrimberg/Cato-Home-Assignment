from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from daily_movers.config import AppConfig
from daily_movers.email.eml_backend import EmlBackend
from daily_movers.email.smtp_backend import SmtpBackend
from daily_movers.errors import EmailDeliveryError
from daily_movers.storage.runs import StructuredLogger


def _logger(tmp_path: Path) -> StructuredLogger:
    return StructuredLogger(path=tmp_path / "run.log", run_id="test-run")


def _message() -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Daily Movers Digest - 2026-02-08"
    msg["From"] = "from@example.com"
    msg["To"] = "to@example.com"
    msg.set_content("plain")
    msg.add_alternative("<html><body>hello</body></html>", subtype="html")
    return msg


def test_eml_backend_builds_and_writes_message(tmp_path: Path) -> None:
    backend = EmlBackend(logger=_logger(tmp_path))
    message = backend.build_message(
        subject="Digest",
        html_body="<html><body>ok</body></html>",
        from_email="from@example.com",
        to_email="to@example.com",
    )

    out_path = tmp_path / "digest.eml"
    backend.write_message(message=message, out_path=out_path)

    assert out_path.exists()
    payload = out_path.read_text(encoding="utf-8")
    assert "Subject: Digest" in payload
    assert "Content-Type: multipart/alternative" in payload


def test_smtp_backend_requires_complete_config(tmp_path: Path) -> None:
    config = AppConfig(cache_dir=tmp_path / "cache")
    backend = SmtpBackend(config=config, logger=_logger(tmp_path))

    assert backend.can_send() is False
    with pytest.raises(EmailDeliveryError):
        backend.send_message(message=_message())


def test_smtp_backend_falls_back_to_ssl_when_starttls_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"smtp_ssl_sent": False}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            return None

        def starttls(self):
            raise RuntimeError("starttls failed")

        def login(self, username, password):
            return None

        def send_message(self, message):
            return None

    class FakeSMTPSSL:
        def __init__(self, host, port, timeout, context):
            self.host = host
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, username, password):
            return None

        def send_message(self, message):
            state["smtp_ssl_sent"] = True

    monkeypatch.setattr("daily_movers.email.smtp_backend.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("daily_movers.email.smtp_backend.smtplib.SMTP_SSL", FakeSMTPSSL)

    config = AppConfig(
        cache_dir=tmp_path / "cache",
        smtp_username="user",
        smtp_password="pass",
        from_email="from@example.com",
        self_email="to@example.com",
    )
    backend = SmtpBackend(config=config, logger=_logger(tmp_path))

    backend.send_message(message=_message())

    assert state["smtp_ssl_sent"] is True


def test_smtp_backend_raises_typed_error_when_both_transports_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSMTP:
        def __init__(self, host, port, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            return None

        def starttls(self):
            raise RuntimeError("starttls failure")

        def login(self, username, password):
            return None

        def send_message(self, message):
            return None

    class FakeSMTPSSL:
        def __init__(self, host, port, timeout, context):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, username, password):
            raise RuntimeError("ssl login failure")

        def send_message(self, message):
            return None

    monkeypatch.setattr("daily_movers.email.smtp_backend.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("daily_movers.email.smtp_backend.smtplib.SMTP_SSL", FakeSMTPSSL)

    config = AppConfig(
        cache_dir=tmp_path / "cache",
        smtp_username="user",
        smtp_password="pass",
        from_email="from@example.com",
        self_email="to@example.com",
    )
    backend = SmtpBackend(config=config, logger=_logger(tmp_path))

    with pytest.raises(EmailDeliveryError):
        backend.send_message(message=_message())
