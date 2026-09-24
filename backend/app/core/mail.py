"""Исходящая почта.

Письмо уходит в фоне, после ответа клиенту (`BackgroundTasks`): сбой SMTP не
откатывает то, ради чего письмо писалось, а только попадает в лог. Гарантии
доставки нет и не будет до очереди задач на этапе 9 — ссылку всегда можно
переслать вручную или создать приглашение заново.
"""

from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib as aiosmtplib  # реэкспорт: тесты подменяют aiosmtplib.send через monkeypatch
import structlog
from fastapi import Request

from app.core.config import MailSettings

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class MailMessage:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    async def send(self, message: MailMessage) -> None: ...


class ConsoleMailer:
    """Письмо в лог вместо отправки: разработчик видит ссылку из приглашения в консоли."""

    async def send(self, message: MailMessage) -> None:
        logger.info("mail.console", to=message.to, subject=message.subject, body=message.body)


class SmtpMailer:
    def __init__(self, settings: MailSettings) -> None:
        self._settings = settings

    def _build(self, message: MailMessage) -> EmailMessage:
        email = EmailMessage()
        email["From"] = self._settings.from_address
        email["To"] = message.to
        email["Subject"] = message.subject
        email.set_content(message.body)
        return email

    async def send(self, message: MailMessage) -> None:
        settings = self._settings
        await aiosmtplib.send(
            self._build(message),
            hostname=settings.host,
            port=settings.port,
            # Пустая строка — «без аутентификации», а не логин из пустой строки.
            username=settings.username or None,
            password=settings.password.get_secret_value() or None,
            use_tls=settings.security == "tls",
            start_tls=settings.security == "starttls",
            timeout=settings.timeout_seconds,
        )


def build_mailer(settings: MailSettings) -> Mailer:
    return SmtpMailer(settings) if settings.backend == "smtp" else ConsoleMailer()


def get_mailer(request: Request) -> Mailer:
    """Зависимость FastAPI. Почтальон живёт в `app.state`: тесты подменяют его целиком."""
    mailer: Mailer = request.app.state.mailer
    return mailer


async def send_safely(mailer: Mailer, message: MailMessage) -> None:
    """Сбой отправки — строка в логе, а не 500: ответ клиенту к этому моменту уже ушёл."""
    try:
        await mailer.send(message)
    except Exception as error:
        logger.warning("mail.send_failed", to=message.to, error=type(error).__name__)
