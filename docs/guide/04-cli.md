# 4. CLI `tkl`

`tkl` — TasKanLine из терминала. Он одинаково удобен человеку и агенту: таблица в терминале,
JSON — когда вывод уходит в файл или в другую программу, понятные коды выхода и сообщения об
ошибках с подсказкой, что делать дальше.

Все примеры ниже — настоящий вывод на тестовом пространстве Acme из
[веб-клиента](02-client.md).

## Установка

Из корня репозитория:

```bash
uv tool install ./cli      # ставит бинарь tkl в ~/.local/bin
tkl --version
```

Без установки, прямо из репозитория — `uv run tkl …`.

Автодополнение для своей оболочки: `tkl --install-completion`.

## Вход

CLI входит не паролем, а **токеном доступа**. Выпустите его в веб-клиенте: меню профиля →
«Токены доступа» ([подробнее](02-client.md#токены-доступа)). Для чтения хватит «Только чтение»;
чтобы CLI менял задачи — «Чтение и запись».

```console
$ tkl auth login --token tkl_8Yz2HAP1… --api-url http://localhost:8000
Токен сохранён в профиль «default» (/home/anna/.config/taskanline/config.toml)
email        anna@acme.example
name         Анна Смирнова
profile      default
api_url      http://localhost:8000
auth_method  token
scopes       read,write
```

`--api-url` — адрес **API**, а не веб-клиента: локально `http://localhost:8000`, на сервере —
тот адрес, где отвечает `/api/v1`.

Затем — значения по умолчанию, чтобы не повторять их в каждой команде:

```bash
tkl config set workspace acme                    # slug пространства
tkl config set team ENG                          # команда по умолчанию
tkl config set web_url http://localhost:5173     # база поля url в выводе
```

> Поле `url` в выводе строится как `<web_url>/<ключ>` (`http://localhost:5173/ENG-1`), а страница
> задачи в веб-клиенте живёт по адресу `/w/<slug>/task/ENG-1` — такая ссылка пока не открывает
> задачу напрямую. Для перехода в браузер используйте адрес вида
> `http://localhost:5173/w/acme/task/ENG-1`.

Проверить, кто вы и что разрешено, — `tkl auth status`. Выйти — `tkl auth logout`.

### Профили и переменные окружения

Конфиг лежит в `~/.config/taskanline/config.toml` (или `$XDG_CONFIG_HOME/taskanline/`), с
правами `600`. Он же общий с [MCP-сервером](05-mcp.md).

```toml
default_profile = "default"

[profiles."default"]
api_url = "http://localhost:8000"
token = "tkl_…"
workspace = "acme"
team = "ENG"
```

Несколько серверов или учётных записей — несколько профилей:
`tkl --profile work auth login --token …`, затем `tkl --profile work task list`.

Любое значение можно переопределить окружением — удобно в CI и для агентов:
`TKL_API_URL`, `TKL_TOKEN`, `TKL_WORKSPACE`, `TKL_TEAM`, `TKL_PROFILE`. Порядок: флаг командной
строки → переменная окружения → профиль.

## Первые шаги

Начинайте со статусов команды — у каждой они свои, и CLI принимает их по имени:

```console
$ tkl team list
KEY  NAME       PRIVATE
DES  Дизайн     false
ENG  Инженерия  false

$ tkl team states ENG
NAME         TYPE       DEFAULT
Backlog      backlog    false
Todo         unstarted  true
In Progress  started    false
Done         completed  false
Canceled     canceled   false
```

Задачи команды по умолчанию:

```console
$ tkl task list
KEY     STATE        PRIORITY  TITLE                                       ASSIGNEE
ENG-1   In Progress  urgent    Вход через Apple ID падает на iOS 18        anna@acme.example
ENG-2   Todo         high      Офлайн-режим для списка заказов             boris@acme.example
ENG-3   In Progress  high      Push-уведомления о смене статуса            boris@acme.example
ENG-4   Todo         high      Экран оплаты съезжает на маленьких экранах  dmitry@partner.example
ENG-5   Backlog      medium    Подготовить сборку 2.0 в TestFlight         anna@acme.example
…
```

Полная карточка:

```console
$ tkl task show ENG-1
key           ENG-1
title         Вход через Apple ID падает на iOS 18
state         In Progress
assignee      Анна Смирнова
priority      urgent
due_date      2026-10-14
labels        bug
project       Мобильное приложение
url           http://localhost:5173/ENG-1
description   После обновления до iOS 18 вход через Apple ID завершается ошибкой `invalid_grant`.
              …
relations     [{"type": "blocks", "task": "ENG-5", …}]
…
```

## Работа с задачей: полный цикл

```console
$ tkl task create --title "Кэшировать аватары" --project "Мобильное приложение" \
    --priority medium --label feature --assignee me
key           ENG-14
title         Кэшировать аватары
state         Todo
…

$ tkl task state ENG-14 "In Progress"
$ tkl task comment ENG-14 -m "Начал: кэш на 24 часа, ключ — хеш URL"
$ tkl task link ENG-14 --relates-to ENG-3
$ tkl task close ENG-14                 # первый статус типа completed — здесь Done
```

Каждая команда изменения печатает задачу после изменения. Создание идемпотентно: если сеть
оборвалась и команда повторилась, вторая задача не появится.

## Фильтры: мини-язык `--filter`

`tkl task list -f "…"` и `tkl view create -f "…"` принимают условия через пробел — они
соединяются через **И**; значения через запятую — через **ИЛИ**.

```console
$ tkl task list -f "assignee:me state-type:started"
KEY    STATE        PRIORITY  TITLE                                 ASSIGNEE
ENG-1  In Progress  urgent    Вход через Apple ID падает на iOS 18  anna@acme.example

$ tkl task list -f "label:bug state-type:!completed,!canceled priority:<=2"
KEY    STATE        PRIORITY  TITLE                                       ASSIGNEE
ENG-1  In Progress  urgent    Вход через Apple ID падает на iOS 18        anna@acme.example
ENG-4  Todo         high      Экран оплаты съезжает на маленьких экранах  dmitry@partner.example
```

| Поле | Значения | Пример |
|---|---|---|
| `team` | ключ команды | `team:ENG,DES` |
| `project` | имя или id проекта; `null` — вне проектов | `project:"Мобильное приложение"` |
| `state` | имя статуса | `state:"In Progress"` |
| `state-type` | `backlog`, `unstarted`, `started`, `completed`, `canceled` | `state-type:!completed,!canceled` |
| `assignee`, `creator` | email или `me`; `null` — не назначена | `assignee:me`, `assignee:null` |
| `label` | имя метки | `label:bug,regression` |
| `priority` | `none`, `urgent`, `high`, `medium`, `low` или 0–4; сравнения | `priority:<=2` |
| `due`, `created`, `updated` | `YYYY-MM-DD`, `@today`, `@today+7d`, `@today-3d`, `@week`; сравнения | `due:<@today+7d` |
| `parent` | ключ родителя; `null` — только верхний уровень | `parent:ENG-1` |
| `title` | подстрока, через `~` | `title~логин` |

- `!` перед значениями — отрицание: `state-type:!completed,!canceled` — «ни то, ни другое».
- `null` и `!null` — поле пустое или заполнено.
- `<`, `<=`, `>`, `>=` — для приоритета и дат.
- Значение с пробелами — в кавычках: `project:"Платёжный шлюз"`.

Ошибка в фильтре находится до запроса к серверу и показывает место:

```console
$ tkl task list -f "asignee:me"
Ошибка в фильтре на позиции 0: неизвестное поле «asignee».
  asignee:me
  ^
Возможно, вы имели в виду: assignee
```

Без `--team` список ограничен командой из профиля; `--all-teams` снимает ограничение.
Сортировка — `--sort priority`, `--sort -updated` (минус — по убыванию).

## Views

Сохранённые срезы из веб-клиента доступны и здесь:

```console
$ tkl view list
NAME                      SCOPE      GROUP     LAYOUT  ID
Мои на этой неделе        user       —         list    01a121ee-2aff-…
Незакрытые баги           team       priority  board   01a121ee-2ae4-…
Срочное по всем командам  workspace  —         list    01a121ee-2af2-…

$ tkl view run "Незакрытые баги"
GROUP   KEY    STATE        PRIORITY  TITLE                                       ASSIGNEE
urgent  ENG-1  In Progress  urgent    Вход через Apple ID падает на iOS 18        anna@acme.example
high    ENG-4  Todo         high      Экран оплаты съезжает на маленьких экранах  dmitry@partner.example
```

Создать view из того же мини-языка:

```bash
tkl view create --name "Мои незакрытые баги" --scope team --team ENG \
  -f "assignee:me label:bug state-type:!completed,!canceled" --group-by priority --layout board
```

## Вывод: таблица, JSON, только ключи

| Флаг | Что выводит |
|---|---|
| (ничего, терминал) | таблица |
| (ничего, вывод в файл или трубу) | JSON — автоматически |
| `--json` или `--output json` | JSON принудительно |
| `--output plain` | без рамок и выравнивания |
| `-q`, `--quiet` | только идентификаторы, по одному на строку |
| `--no-color` | без цвета |
| `-v`, `--verbose` | запросы к API — в stderr |

```console
$ tkl task list -f "assignee:me state-type:started" --json
{"items": [{"key": "ENG-1", "title": "Вход через Apple ID падает на iOS 18",
  "state": {"name": "In Progress", "type": "started"},
  "assignee": {"email": "anna@acme.example", "name": "Анна Смирнова"},
  "priority": "urgent", "due_date": "2026-10-14", "labels": ["bug"],
  "project": "Мобильное приложение", "url": "http://localhost:5173/ENG-1"}],
 "next_cursor": null, "has_more": false, "total_hint": 1}

$ tkl -q task list -f "label:bug"
ENG-1
ENG-4
ENG-8
ENG-10
```

В stdout идут только данные; сообщения и предупреждения — в stderr. Поэтому
`tkl task list --json | jq …` и `for k in $(tkl -q task list …)` работают без фильтрации мусора.

Списки постраничные: `--limit` (до 100) и `--cursor` из `next_cursor` предыдущего ответа.

## Ошибки и коды выхода

Ошибка — это код, сообщение и подсказка:

```console
$ tkl task state ENG-14 Ревью
Ошибка [state_not_found]: Статус «Ревью» не существует в команде ENG.
Доступные: Backlog, Todo, In Progress, Done, Canceled

$ tkl task show ENG-999
Ошибка [task_not_found]: Задача ENG-999 не найдена.
Доступные команды: DES, ENG
```

| Код | Значение | Что делать |
|---|---|---|
| 0 | успех | |
| 1 | неверный вызов: опции, фильтр, конфиг | прочитать сообщение, поправить команду |
| 2 | ошибка API | `--verbose`, лог сервера |
| 3 | нет прав: токен отозван, только чтение, роль | `tkl auth status`; выпустить токен с нужными правами |
| 4 | не найдено (или не видно вам) | проверить ключ, команду, пространство |
| 5 | конфликт | перечитать объект и повторить |
| 6 | превышен лимит запросов | подождать и повторить |
| 7 | сеть: сервер недоступен | проверить `--api-url` и что API запущено |

Скрипт или агент ветвится по коду выхода и по `code` в квадратных скобках — он не меняется от
версии к версии, в отличие от текста.

## Справочник команд

Глобальные опции ставятся **до** команды: `tkl --profile work --json task list`.

### `auth`, `config`, `me`

| Команда | Что делает |
|---|---|
| `tkl auth login --token T [--api-url URL] [--profile P]` | проверить токен и сохранить в профиль |
| `tkl auth status` | текущий пользователь, профиль, адрес API, права токена |
| `tkl auth logout` | удалить токен из профиля |
| `tkl config list` · `get KEY` · `set KEY VALUE` · `path` | конфиг; ключи: `api_url`, `token`, `workspace`, `team`, `web_url` |
| `tkl me tasks [--state-type T]` | задачи, назначенные на меня |
| `tkl me inbox [--unread]` | уведомления |

### `workspace` (алиас `ws`), `team`, `project`, `label`

| Команда | Что делает |
|---|---|
| `tkl workspace list` · `show SLUG` · `members` | пространства, детали, участники с ролями |
| `tkl workspace create --name N --slug S` | создать пространство |
| `tkl workspace invite --email E [--role guest\|member\|admin]` | пригласить в пространство |
| `tkl team list` · `show KEY` · `members KEY` | команды, детали, участники |
| `tkl team states KEY` | статусы команды — **с них стоит начинать** |
| `tkl team create --key ENG --name N [--private]` | создать команду |
| `tkl team invite KEY --email E [--role member\|lead]` | пригласить в команду |
| `tkl project list [--team KEY] [--status S] [--archived]` · `show` | проекты |
| `tkl project create --name N [--team] [--lead] [--status] [--target-date]` | создать проект |
| `tkl project update` · `archive` | изменить, архивировать |
| `tkl project invite ID\|NAME --email E [--role viewer\|member\|lead]` | пригласить в проект |
| `tkl label list` | метки: общие и команды |
| `tkl label create --name N --color "#555555" [--team KEY]` · `delete` | без `--team` — общая для пространства |

### `task`

| Команда | Что делает |
|---|---|
| `tkl task list [-f DSL] [--team] [--all-teams] [--sort] [--limit]` | список по фильтру |
| `tkl task show KEY` | задача целиком |
| `tkl task create --title T [--team] [--project] [-d TEXT\|@file\|-] [--state] [--assignee] [--priority] [--due] [--label …] [--parent]` | создать |
| `tkl task update KEY [те же поля]` | изменить только переданные поля; `none` очищает |
| `tkl task assign KEY EMAIL\|me\|none` | исполнитель |
| `tkl task state KEY "In Progress"` | статус по имени |
| `tkl task close KEY [--canceled]` | завершить (или отменить) |
| `tkl task move KEY --after K \| --before K \| --top \| --bottom` | ручной порядок |
| `tkl task label KEY --add L --remove L` | метки |
| `tkl task link KEY --blocks K \| --blocked-by K \| --relates-to K \| --duplicates K` | связь |
| `tkl task unlink KEY OTHER [--type T]` | снять связь с задачей `OTHER` |
| `tkl task comment KEY -m TEXT \| --file PATH \| -` | комментарий (`-` — из stdin) |
| `tkl task delete KEY` · `restore KEY` | мягкое удаление и восстановление |

`KEY` — ключ (`ENG-142`) или UUID. Описание и комментарий принимают текст, `@файл` или `-` для
stdin: `git log -1 --format=%B | tkl task comment ENG-14 -`.

### `view`

| Команда | Что делает |
|---|---|
| `tkl view list` | views, видимые мне |
| `tkl view show ID\|NAME` | определение: фильтры, группировка, сортировка |
| `tkl view run ID\|NAME [--group G] [--limit]` | выполнить |
| `tkl view create --name N [-f DSL] [--scope user\|team\|workspace] [--team] [--group-by] [--layout] [--sort]` | создать |
| `tkl view delete ID\|NAME` | удалить |

Подробная справка по любой команде — `tkl <группа> <команда> --help`.

## Рецепты

**Агент берёт задачу в работу и отчитывается:**

```bash
tkl task list -f "assignee:me state-type:unstarted" --sort priority --limit 1 -q \
  | xargs -I{} tkl task state {} "In Progress"
tkl task comment ENG-14 -m "Готово в PR #218: кэш на 24 часа, тесты в tests/test_avatars.py"
tkl task close ENG-14
```

**Ежедневная сводка в CI:**

```bash
export TKL_API_URL=https://tasks.acme.example TKL_TOKEN=$TKL_READ_TOKEN TKL_WORKSPACE=acme
tkl view run "Срочное по всем командам" --json > urgent.json
```

**Отдельный токен на агента.** Выпускайте каждому агенту и машине свой токен с понятным
именем: в списке токенов видно, когда каким пользовались, и отозвать один можно, не трогая
остальные. Где хватает чтения — давайте `read`.
