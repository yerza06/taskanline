"""Выгрузка OpenAPI-схемы в stdout.

Нужна одному потребителю — генератору типов веб-клиента:

    uv run python -m app.openapi > frontend_client/openapi.json

Схема снимается с собранного приложения, а не пишется отдельно: второй источник
правды о контракте разошёлся бы с первым в тот же день, когда появился.
"""

import json

from app.main import create_app


def dump() -> str:
    """Схема в виде текста, готового лечь в файл под контролем версий.

    `sort_keys` — ради diff: FastAPI не обещает порядок ключей, и без сортировки
    каждая выгрузка переставляла бы строки местами. `ensure_ascii=False` — ради
    описаний на русском: `\\u041e\\u043f\\u0438` не читает никто.
    """
    return json.dumps(create_app().openapi(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> None:
    print(dump(), end="")


if __name__ == "__main__":
    main()
