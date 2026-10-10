# Справочник CLI `tkl`

Глобальные опции: `--json`, `--output json|table|plain|quiet`, `-q`, `--profile P`,
`--api-url URL`, `--token T`, `--timeout S`, `-v` (запросы в stderr), `--no-color`.
Подробно о любой команде — `tkl <группа> <команда> --help`.

`KEY` — ключ задачи (`ENG-142`) или UUID. Значения по умолчанию берутся по порядку: флаг →
переменная окружения (`TKL_API_URL`, `TKL_TOKEN`, `TKL_WORKSPACE`, `TKL_TEAM`, `TKL_PROFILE`) →
профиль в `~/.config/taskanline/config.toml`.

## Доступ и конфиг

| Команда | Что делает |
|---|---|
| `tkl auth login --token T [--api-url URL] [--profile P]` | проверить токен и сохранить в профиль |
| `tkl auth status` | пользователь, профиль, адрес API, права токена |
| `tkl auth logout` | удалить токен из профиля |
| `tkl config list` · `get KEY` · `set KEY VALUE` · `path` | ключи: `api_url`, `token`, `workspace`, `team`, `web_url` |
| `tkl me tasks [--state-type T]` | задачи, назначенные на меня |
| `tkl me inbox [--unread]` | уведомления |

## Структура

| Команда | Что делает |
|---|---|
| `tkl workspace list` · `show SLUG` · `members` | пространства, детали, участники с ролями (алиас `ws`) |
| `tkl team list` · `show KEY` · `members KEY` | команды |
| `tkl team states KEY` | статусы команды — **начинай с них** |
| `tkl project list [--team KEY] [--status S] [--archived]` · `show ID\|NAME` | проекты |
| `tkl label list` | метки: общие для пространства и команды |

Создание структуры (`workspace create`, `team create`, `project create`, `label create`,
`… invite`) — только по прямой просьбе человека; детали — в `--help`.

## Задачи

| Команда | Что делает |
|---|---|
| `tkl task list [-f DSL] [--team KEY] [--all-teams] [--sort F] [--limit N] [--cursor C]` | список; без `--team` — команда профиля |
| `tkl task show KEY` | карточка целиком |
| `tkl task create --title T [--team] [--project] [-d TEXT\|@file\|-] [--state] [--assignee] [--priority] [--due] [--label L …] [--parent KEY]` | создать |
| `tkl task update KEY [те же поля]` | менять только переданное; значение `none` очищает поле |
| `tkl task assign KEY EMAIL\|me\|none` | исполнитель |
| `tkl task state KEY "In Progress"` | статус по имени |
| `tkl task close KEY [--canceled]` | первый статус типа `completed` (или `canceled`) |
| `tkl task move KEY --after K \| --before K \| --top \| --bottom` | ручной порядок в команде |
| `tkl task label KEY --add L --remove L` | метки |
| `tkl task link KEY --blocks K \| --blocked-by K \| --relates-to K \| --duplicates K` | связь |
| `tkl task unlink KEY OTHER [--type T]` | снять связь |
| `tkl task comment KEY -m TEXT \| --file PATH \| -` | комментарий (`-` — stdin) |
| `tkl task delete KEY` · `restore KEY` | мягкое удаление и восстановление |

Сортировка: `manual` (по умолчанию), `priority` (срочные первыми, без приоритета — в конце),
`due`, `created`, `updated`, `title`; минус или `:desc` — по убыванию: `--sort -updated`.

## Views

| Команда | Что делает |
|---|---|
| `tkl view list` | views, видимые мне |
| `tkl view show ID\|NAME` | фильтры, группировка, сортировка |
| `tkl view run ID\|NAME [--group G] [--limit N]` | выполнить |
| `tkl view create --name N [-f DSL] [--scope user\|team\|workspace] [--team] [--group-by] [--layout list\|board] [--sort]` | создать |
| `tkl view delete ID\|NAME` | удалить |

## Язык фильтров `-f`

Условия через пробел — **И**; значения через запятую — **ИЛИ**; `!` перед значением —
отрицание; `null` / `!null` — поле пустое / заполнено; значение с пробелами — в кавычках.

| Поле | Значения | Пример |
|---|---|---|
| `team` | ключ команды | `team:ENG,DES` |
| `project` | имя или id; `null` — вне проектов | `project:"Мобильное приложение"` |
| `state` | имя статуса | `state:"In Progress"` |
| `state-type` | `backlog`, `unstarted`, `started`, `completed`, `canceled` | `state-type:!completed,!canceled` |
| `assignee`, `creator` | email или `me`; `null` — не назначена | `assignee:me`, `assignee:null` |
| `label` | имя метки | `label:bug,regression` |
| `priority` | `none`, `urgent`, `high`, `medium`, `low` или 0–4; `<`, `<=`, `>`, `>=` | `priority:<=2` |
| `due`, `created`, `updated` | `YYYY-MM-DD`, `@today`, `@today+7d`, `@today-3d`, `@week`; сравнения | `due:<@today+7d` |
| `parent` | ключ родителя; `null` — только верхний уровень | `parent:ENG-1` |
| `title` | подстрока, через `~` | `title~логин` |

Ошибка в фильтре находится до запроса к серверу (exit 1) и показывает позицию и подсказку
(«Возможно, вы имели в виду: assignee»).

Готовые фильтры:

| Просьба | Фильтр |
|---|---|
| мои открытые | `assignee:me state-type:!completed,!canceled` |
| мои в работе | `assignee:me state-type:started` |
| незакрытые баги | `label:bug state-type:!completed,!canceled` |
| горит на этой неделе | `due:<@today+7d state-type:!completed,!canceled` |
| никому не назначено | `assignee:null state-type:unstarted,backlog` |
| срочное и высокое | `priority:<=2 state-type:!completed,!canceled` |
| изменилось за сутки | `updated:>=@today-1d` |

## Формат JSON

`tkl --json task list …`:

```json
{"items": [{"key": "ENG-1", "title": "Вход через Apple ID падает на iOS 18",
  "state": {"name": "In Progress", "type": "started"},
  "assignee": {"email": "anna@acme.example", "name": "Анна Смирнова"},
  "priority": "urgent", "due_date": "2026-10-14", "labels": ["bug"],
  "project": "Мобильное приложение", "url": "…"}],
 "next_cursor": null, "has_more": false, "total_hint": 1}
```

Команды изменения (`create`, `update`, `state`, `assign`, `close`, …) возвращают задачу после
изменения в том же компактном виде.
