"""Общие приёмы для схем запросов."""

import unicodedata

from pydantic import BaseModel


def reject_explicit_null(model: BaseModel, *fields: str) -> None:
    """PATCH с `"name": null` — ошибка клиента (422), а не 500 от NOT NULL в базе.

    Поле, которое не прислали, остаётся как было; поле, присланное как null, для
    обязательной колонки означает «стереть» — а стирать его нельзя.
    """
    for field in fields:
        if field in model.model_fields_set and getattr(model, field) is None:
            raise ValueError(f"Поле {field} не может быть пустым")


def reject_control_characters(value: object) -> object:
    """Перевод строки в названии — ошибка клиента (422), а не тихая потеря письма.

    `EmailMessage` отклоняет `Subject` с переводом строки, а `send_safely` эту
    ошибку только логирует: приглашение с таким названием пространства в теме
    письма ушло бы в никуда без единого сообщения об этом пользователю.
    """
    if isinstance(value, str) and any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError("Поле не может содержать управляющие символы")
    return value
