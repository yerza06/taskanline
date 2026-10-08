# Контекст сборки — корень репозитория.
FROM oven/bun:1 AS build

# Раскладка как в репозитории: index.css импортирует ../../frontend_shared/tokens.css.
WORKDIR /repo/frontend_client
COPY frontend_client/package.json frontend_client/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend_shared/ /repo/frontend_shared/
COPY frontend_client/ ./
RUN bun run build

FROM nginx:alpine
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/frontend_client/dist /srv/frontend_client
EXPOSE 80
