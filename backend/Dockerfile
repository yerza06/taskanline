# Контекст сборки — корень репозитория: uv-workspace нужен целиком.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/srv/.venv/bin:$PATH"

WORKDIR /srv

# Зависимости отдельным слоем: он не пересобирается от правки кода.
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/
COPY sdk/pyproject.toml sdk/
COPY cli/pyproject.toml cli/
COPY mcp/pyproject.toml mcp/
RUN uv sync --frozen --no-dev --no-install-workspace

COPY backend/ backend/
COPY sdk/ sdk/
COPY cli/ cli/
COPY mcp/ mcp/
RUN uv sync --frozen --no-dev

RUN useradd --system --create-home --uid 1000 taskanline && chown -R taskanline:taskanline /srv
USER taskanline

EXPOSE 8000

# Миграции применяются отдельной командой при старте контейнера, а не из кода
# приложения: иначе несколько реплик мигрируют одновременно.
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && python -m app.main"]
