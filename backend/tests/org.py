"""Помощники тестов организационной структуры."""

from app.core.mail import MailMessage

CSRF = {"X-Requested-With": "XMLHttpRequest"}
PASSWORD = "correct horse battery"


class RecordingMailer:
    """Почтальон тестов: складывает письма в список вместо отправки."""

    def __init__(self) -> None:
        self.sent: list[MailMessage] = []

    async def send(self, message: MailMessage) -> None:
        self.sent.append(message)
