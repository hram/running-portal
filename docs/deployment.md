# Деплой

Единственный оформленный способ деплоя в репозитории — Docker-образ по
корневому `Dockerfile`, без Docker Compose и без CI-пайплайна
(`.gitlab-ci.yml`/`.github/workflows` в репозитории нет — сборка и
раскладка по продакшену делаются вручную/через Coolify).

## Образ

Multi-stage сборка:

1. **Слой `claude-cli`** (`node:22-bookworm-slim`) — ставит
   `@anthropic-ai/claude-code` глобально через `npm`.
2. **Основной слой** (`python:3.12-slim`) — копирует `node`, `claude` и
   его модули из первого слоя, ставит проект через `pip install .`
   (без dev-зависимостей), создаёт непривилегированного пользователя
   `app` и каталог `/data/running-portal` для рантайм-данных.

Ключевые ENV, зашитые прямо в `Dockerfile` (переопределяются реальными
переменными окружения контейнера при деплое):

```env
PORT=8000
DB_PATH=/data/running-portal/portal.db
MI_FITNESS_STATE_PATH=/data/running-portal/auth.json
MI_FITNESS_CACHE_DIR=/data/running-portal/fds_cache
HOME=/data/running-portal
CLAUDE_CLI_PATH=/usr/local/bin/claude
```

`HOME=/data/running-portal` — не случайность: Claude CLI ищет файл
авторизации в `$HOME/.claude`, и это значение выравнивает его с тем же
персистентным томом, где лежат `portal.db`/`auth.json`, чтобы
Claude-сессия тоже переживала пересоздание контейнера.

Здоровье контейнера проверяется встроенным `HEALTHCHECK` —
HTTP GET на `/` (сам портал не имеет отдельного `/health`-эндпоинта:
`portal/routers/health.py` — это CRUD журнала состояния, а не
healthcheck; для этой роли используется главная страница).

## Персистентные данные

Всё состояние, которое должно пережить пересоздание контейнера, лежит
под одним каталогом — `/data/running-portal` (см. ENV выше):

- `portal.db` — SQLite;
- `auth.json` — состояние сессии Mi Fitness;
- `fds_cache/` — кэш скачанных бинарных файлов Mi Fitness;
- `.claude/` (косвенно, через `HOME`) — авторизация Claude CLI.

Ни одно из этого не должно попадать в образ или в репозиторий — все
четыре пути либо в `.gitignore`, либо (для `.claude/`) вне рабочей
директории проекта в принципе.

## Сборка и запуск локально

```bash
docker build -t running-portal .
docker run -p 8000:8000 \
  -v running-portal-data:/data/running-portal \
  -e MI_FITNESS_COUNTRY_CODE=RU \
  running-portal
```

Полный список переменных окружения — в README
([раздел «Конфигурация»](../README.md#конфигурация-env)) и в
`.env.production.example`.

## Текущий продакшен

Портал развёрнут через Coolify на внутреннем dev-сервере — конкретные
параметры (URL, точка монтирования тома, UUID приложения, файл
API-токена, история миграции данных) зафиксированы отдельно в
[`docs/coolify-deploy.md`](./coolify-deploy.md) и не дублируются здесь,
так как это runbook по конкретному инстансу, а не общий рецепт деплоя.

## Что не реализовано (см. `PRODUCTION_READINESS.md`)

Корневой [`PRODUCTION_READINESS.md`](../PRODUCTION_READINESS.md)
фиксирует разрыв между текущим состоянием (личный проект, один
пользователь, SQLite, in-process планировщик, прямой subprocess до
Claude CLI) и тем, что нужно для более широкого использования:
шифрование состояния Mi Fitness, аутентификация самого портала,
вынесение синхронизации из HTTP-пути запроса, PostgreSQL + миграции,
внешний воркер вместо APScheduler, наблюдаемость. Ничего из этого в
коде пока не реализовано — считать частью текущей архитектуры нельзя.
