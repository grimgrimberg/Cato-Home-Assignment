from __future__ import annotations

from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path


def build_digest_eml(*, subject: str, html_body: str, from_email: str, to_email: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content("This digest contains an HTML body. Open in an email client to view formatting.")
    msg.add_alternative(html_body, subtype="html")
    return msg


def write_eml_file(*, message: EmailMessage, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        f.write(message.as_bytes(policy=SMTP))
