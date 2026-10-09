# Справочник MCP-сервера `tkl-mcp`

Сервер работает от имени владельца токена и не делает ничего сверх API: те же права, та же
видимость. Ошибка инструмента приходит текстом, по которому можно исправиться, например:
`Статус «Ревью» не существует в команде ENG. Доступные: Backlog, Todo, In Progress, Done, Canceled.`

## Подключение

Установка (нужен [uv](https://docs.astral.sh/uv/)):

```bash
uv tool install "taskanline-mcp @ git+https://github.com/yerza06/taskanline#subdirectory=mcp"
```

Токен и адрес API сервер берёт из конфига CLI (`tkl auth login`), либо из `--token`,
`--api-url`, `TKL_TOKEN`, `TKL_API_URL`.

Claude Code:

```bash
claude mcp add taskanline -- tkl-mcp                       # чтение и запись
claude mcp add taskanline -- tkl-mcp --read-only --workspace acme
```

Или `.mcp.json` в корне проекта:

```json
{"mcpServers": {"taskanline": {"command": "tkl-mcp", "args": ["--workspace", "acme"]}}}
```

Другие клиенты (Claude Desktop, Cursor и т. п.) — та же запись `command`/`args` в их конфиге;
если бинарь не находится, укажите полный путь из `which tkl-mcp`. После подключения клиент
нужно перезапустить — подключить сервер посреди диалога агент не может, это делает человек.

Флаги: `--read-only` (убрать инструменты записи), `--workspace SLUG` (одно пространство),
`--profile P`, `--max-items N` (до 50), `--transport http --host --port --allowed-host` (для
удалённых клиентов за HTTPS-прокси; токен — только из заголовка `Authorization` запроса).

## Инструменты чтения

| Инструмент | Параметры | Когда |
|---|---|---|
| `list_workspaces` | — | только если пространств несколько |
| `list_teams` | `workspace?` | ключи команд и **их статусы**; до создания задач и смены статусов |
| `list_projects` | `team?`, `status?` (`planned`, `in_progress`, `paused`, `completed`, `canceled`) | имя проекта для поиска и создания, сроки |
| `search_tasks` | `query?` (подстрока заголовка), `team?`, `project?`, `assignee?` (email или `me`), `state_type?[]`, `label?[]` (любая), `priority?`, `due_before?` (`YYYY-MM-DD`, `today+7d`), `limit?` (1–50), `cursor?` | главный поиск; условия через И. **Без фильтров — только открытые** (`unstarted`, `started`); описание обрезано до 200 символов |
| `get_task` | `key`, `include?[]` из `comments`, `activity`, `subtasks`, `relations` (по умолчанию comments и subtasks) | полная карточка; вызывай перед работой и пересказом |
| `list_views` | — | сохранённые срезы с фильтрами словами; если просьба похожа на view — он точнее |
| `run_view` | `view` (имя или id), `limit?` | выполнить view; `@me` — текущий пользователь |

Закрытые задачи `search_tasks` отдаёт только при явном `state_type=["completed"]` (или
`canceled`).

## Инструменты записи (нет при `--read-only`)

| Инструмент | Параметры | Заметки |
|---|---|---|
| `create_task` | `title`, `team?`, `description?` (Markdown), `project?`, `state?`, `assignee?`, `priority?`, `due_date?`, `labels?[]`, `parent?` | команду можно опустить, если она одна или задан проект; метки — только существующие |
| `update_task` | `key` + любые из `title`, `description`, `state`, `assignee`, `priority`, `due_date`, `project`, `parent`; `clear?[]` из `description`, `assignee`, `due_date`, `project`, `parent` | меняются только переданные поля; очистить — через `clear`, пустая строка не очищает |
| `assign_task` | `key`, `assignee` (email, `me` или `null`) | `null` снимает исполнителя |
| `update_task_state` | `key`, `state` (имя статуса) | взять в работу, закрыть, отменить |
| `comment_task` | `key`, `body` (Markdown, до 20000 символов) | `@email` уведомит человека |
| `link_tasks` | `source`, `target`, `type` (`blocks`, `blocked_by`, `relates_to`, `duplicates`) | `source <type> target` |

Удаления задач в MCP нет. Если человек просит удалить — CLI `tkl task delete KEY` или
веб-клиент.

Приоритеты везде: `urgent`, `high`, `medium`, `low`, `none`.

## Ресурсы

`taskanline://workspace/{slug}`, `taskanline://team/{key}`, `taskanline://project/{id}`,
`taskanline://task/{key}` — обзоры в Markdown, если клиент умеет прикреплять ресурсы.

## Промпты

| Промпт | Аргументы | Что делает |
|---|---|---|
| `breakdown_task` | `key`, `max_subtasks` (по умолчанию 5) | предложить подзадачи, создать после подтверждения |
| `project_status` | `project` | сделано / в работе / заблокировано / просрочено и главный риск |
| `whats_next` | `team`, `assignee` (по умолчанию `me`) | одна задача и две запасные с обоснованием |
| `standup` | `team`, `since` (по умолчанию `yesterday`) | по людям: сделано, в работе, что мешает |

В Claude Code они доступны как `/mcp__taskanline__standup` и т. п. Без промптов тот же порядок
действий можно выполнить вручную теми же инструментами.

## Соответствие MCP ↔ CLI

| MCP | CLI |
|---|---|
| `list_teams` | `tkl team list` + `tkl team states KEY` |
| `search_tasks(assignee="me", state_type=["started"])` | `tkl task list -f "assignee:me state-type:started" --all-teams` |
| `get_task(key)` | `tkl task show KEY` |
| `run_view(view)` | `tkl view run NAME` |
| `create_task(...)` | `tkl task create --title … --team …` |
| `update_task_state(key, state)` | `tkl task state KEY "State"` |
| `assign_task(key, "me")` | `tkl task assign KEY me` |
| `comment_task(key, body)` | `tkl task comment KEY -m "…"` |
| `link_tasks(source, target, "blocks")` | `tkl task link SOURCE --blocks TARGET` |
