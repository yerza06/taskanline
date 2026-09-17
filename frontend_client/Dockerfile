# Контекст сборки — корень репозитория.
FROM oven/bun:1 AS build

WORKDIR /app
COPY frontend_client/package.json frontend_client/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend_client/ ./
RUN bun run build

FROM nginx:alpine
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /srv/frontend_client
EXPOSE 80
