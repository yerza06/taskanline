"""Исходящая почта: выбор бэкенда, сборка письма и живучесть фоновой отправки."""

from typing import Any

import pytest
from pydantic import SecretStr

from app.core import mail
from app.core.config import MailSettings
from app.core.mail import ConsoleMailer, MailMessage, SmtpMailer, build_mailer, send_safely

MESSAGE = MailMessage(to="anna@example.com", subject="Приглашение", body="Ссылка: http://x")


def test_console_is_default() -> None:
    assert isinstance(build_mailer(MailSettings()), ConsoleMailer)


def test_smtp_backend_is_selected() -> None:
    assert isinstance(build_mailer(MailSettings(backend="smtp")), SmtpMailer)


async def test_smtp_passes_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_send(message: Any, **kwargs: Any) -> None:
        calls.append({"message": message, **kwargs})

    monkeypatch.setattr(mail.aiosmtplib, "send", fake_send)
    settings = MailSettings(
        backend="smtp",
        host="smtp.example.com",
        port=465,
        username="bot",
        password=SecretStr("secret"),
        security="tls",
        from_address="TasKanLine <bot@example.com>",
    )

    await SmtpMailer(settings).send(MESSAGE)

    call = calls[0]
    assert call["hostname"] == "smtp.example.com"
    assert call["port"] == 465
    assert call["password"] == "secret"
    assert call["use_tls"] is True
    assert call["start_tls"] is False
    assert call["message"]["To"] == "anna@example.com"
    assert call["message"]["From"] == "TasKanLine <bot@example.com>"


async def test_empty_credentials_are_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустой логин — это «без аутентификации», а не логин из пустой строки."""
    calls: list[dict[str, Any]] = []

    async def fake_send(message: Any, **kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(mail.aiosmtplib, "send", fake_send)

    await SmtpMailer(MailSettings(backend="smtp")).send(MESSAGE)

    assert calls[0]["username"] is None
    assert calls[0]["password"] is None


async def test_send_safely_swallows_failure() -> None:
    """Ответ клиенту уже ушёл: сбой SMTP — строка в логе, а не исключение."""

    class Broken:
        async def send(self, message: MailMessage) -> None:
            raise ConnectionError("smtp down")

    await send_safely(Broken(), MESSAGE)
