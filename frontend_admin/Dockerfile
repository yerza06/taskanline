# Контекст сборки — корень репозитория. Отдельный образ и отдельный хост: код
# админки не попадает в бандл, который получает обычный пользователь.
FROM oven/bun:1 AS build

# Раскладка как в репозитории: index.css импортирует ../../frontend_shared/tokens.css.
WORKDIR /repo/frontend_admin
COPY frontend_admin/package.json frontend_admin/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend_shared/ /repo/frontend_shared/
COPY frontend_admin/ ./
# Своего входа у админки нет: ссылка «войти» ведёт в веб-клиент.
ARG VITE_CLIENT_URL=http://localhost:8080
ENV VITE_CLIENT_URL=$VITE_CLIENT_URL
RUN bun run build

FROM nginx:alpine
COPY deploy/nginx/admin.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/frontend_admin/dist /srv/frontend_admin
EXPOSE 80
