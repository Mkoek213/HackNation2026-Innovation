"""Optional SMTP delivery: reviewed handoff messages with a PDF attachment and contact form messages."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.config import settings
from app.exceptions import DependencyUnavailable


def mail_delivery_available() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def send_with_pdf(
    *,
    recipient: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_name: str,
) -> None:
    if not mail_delivery_available():
        raise DependencyUnavailable(
            msg="Wysyłka poczty nie jest skonfigurowana. Pobierz PDF i otwórz swojego klienta poczty.",
            loc=("body",),
        )
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid()
    message.set_content(body)
    message.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=pdf_name,
    )
    try:
        deliver(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise DependencyUnavailable(
            msg="Nie udało się wysłać wiadomości. Pobierz PDF i otwórz swojego klienta poczty.",
            loc=("body",),
        ) from exc


def contact_message(*, recipient: str, name: str, email: str, body: str) -> EmailMessage:
    """A contact form message for operator staff; replying goes straight to the sender."""
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Reply-To"] = email
    message["Subject"] = f"Formularz kontaktowy: {name}"
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid()
    message.set_content(f"Imię i nazwisko: {name}\nE-mail: {email}\n\n{body}\n")
    return message


def deliver(message: EmailMessage) -> None:
    """Sends through the configured SMTP server.
    :raises OSError, smtplib.SMTPException: connection, authentication or delivery failure."""
    context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds, context=context) as smtp:
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as smtp:
            if settings.smtp_starttls:
                smtp.starttls(context=context)
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
