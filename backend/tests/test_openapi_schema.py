"""Выгрузка OpenAPI: из неё генерируются типы веб-клиента.

Схема — это контракт, который читает не человек, а `openapi-typescript`. Тест
следит за тем, чтобы выгрузка оставалась и полной, и пригодной для хранения в git.
"""

import json

from app.openapi import dump


class TestSchema:
    def test_covers_stage_one_paths(self) -> None:
        paths = json.loads(dump())["paths"]

        assert "/api/v1/auth/register" in paths
        assert "/api/v1/auth/login" in paths
        assert "/api/v1/auth/refresh" in paths
        assert "/api/v1/auth/logout" in paths
        assert "/api/v1/me" in paths
        assert "/api/v1/me/tokens" in paths
        assert "/api/v1/me/tokens/{token_id}" in paths

    def test_describes_response_schemas(self) -> None:
        """Без схем ответов генератор отдаст `unknown` вместо типов."""
        schemas = json.loads(dump())["components"]["schemas"]

        assert {"SessionResponse", "MeResponse", "TokenCreated", "TokenList"} <= set(schemas)


class TestDumpFormat:
    def test_is_stable(self) -> None:
        """Порядок ключей фиксирован: иначе каждая выгрузка даёт шумный diff."""
        assert dump() == dump()

    def test_ends_with_newline(self) -> None:
        assert dump().endswith("\n")

    def test_keeps_cyrillic_readable(self) -> None:
        """Описания эндпоинтов на русском; \\uXXXX превратил бы файл в шум."""
        assert "\\u0410" not in dump()
        assert "Регистрация" in dump()
