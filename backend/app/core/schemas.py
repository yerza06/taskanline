"""Общие приёмы для схем запросов."""

from pydantic import BaseModel


def reject_explicit_null(model: BaseModel, *fields: str) -> None:
    """PATCH с `"name": null` — ошибка клиента (422), а не 500 от NOT NULL в базе.

    Поле, которое не прислали, остаётся как было; поле, присланное как null, для
    обязательной колонки означает «стереть» — а стирать его нельзя.
    """
    for field in fields:
        if field in model.model_fields_set and getattr(model, field) is None:
            raise ValueError(f"Поле {field} не может быть пустым")
