# Running Portal

Локальный веб-портал для беговых тренировок: синхронизирует пробежки из
Mi Fitness (Xiaomi Smart Band 9 Pro и другие устройства этой экосистемы) и
даёт персональный AI-разбор — совет на сегодня, разбор конкретной пробежки
и цель на месяц.

Проект личный (family/staff use): портал не имеет собственной страницы
входа и не проверяет, кто им пользуется — доступ ограничен только тем,
кто достал до URL. Авторизация есть только у интеграций (Mi Fitness,
Claude). Технологический стек и структура сознательно повторяют соседний
проект [`orienteering`](https://github.com/hram/orienteering).

> Статус: активная разработка. Разделы, для которых не нашлось материала в
> коде, отмечены как «требует уточнения».

## Что делает портал

1. **Синхронизация с Mi Fitness.** По расписанию (и по кнопке) забирает
   новые пробежки из облака Xiaomi, сохраняет сводные метрики и —
   если добавилась ровно одна новая пробежка — сразу подгружает её
   детали (GPS-трек, посекундные пульс/темп/каденс).
2. **Дашборд.** Карточка «Ответ на сегодня», ключевые метрики, график
   Efficiency Factor по неделям, scatter «темп vs пульс», график
   дистанций последних пробежек, таблица пробежек с пагинацией и цель
   на месяц с прогрессом.
3. **Детали пробежки.** Пульсовые зоны, график пульса/скорости по
   времени или по дистанции, EF-полоска по ходу тренировки.
4. **AI-тренер (три независимые функции)** — все через локально
   установленный Claude Code CLI, не через прямой вызов Anthropic API:
   - разбор конкретной пробежки (потоковый ответ, кэшируется);
   - «ответ на сегодня» — бежать в обычном режиме, бежать легко или
     отдыхать;
   - предложение цели на месяц (км + число пробежек), с эвристическим
     fallback без AI, если Claude CLI недоступен.
5. **Журнал состояния.** Отдельная страница для записей о самочувствии,
   боли и травмах — эти записи попадают во все три AI-промпта.
6. **Редактируемые настройки.** Prompt-шаблоны для двух из трёх AI-функций,
   целевая пульсовая зона для графика, включение/выключение карточек
   дашборда — прямо из `/settings`, без правки кода.

Есть также непубличный технический эндпоинт
`/.well-known/assistant-integration.json` — манифест, который отдаёт
статус месячной цели и «ответ на сегодня» в формате для стороннего
AI-ассистента (в коде не указано, авторизации у эндпоинта нет).

## Скриншоты

Скриншотов пока нет — экраны ниже нужно добавить в
`docs/screenshots/` и подставить в README по аналогии с
[`orienteering`](https://github.com/hram/orienteering):

| Экран | Маршрут |
| --- | --- |
| Дашборд (сегодня, метрики, прогресс, цель, дистанции, пробежки) | `/` |
| Детали пробежки (AI-разбор, зоны, график пульса/скорости) | `/activity/{id}` |
| Журнал состояния | `/health` |
| Настройки | `/settings` |

## Технологический стек

- **Backend:** Python 3.12+, [FastAPI](https://fastapi.tiangolo.com/),
  `uvicorn` (ASGI-сервер).
- **Шаблоны/frontend:** Jinja2 (`templates/`) + ванильный JS/CSS
  (`static/`), без сборки (no bundler); графики — Chart.js (CDN).
- **База данных:** SQLite через `aiosqlite`, схема — вручную в коде
  (`portal/db.py`), без ORM и без Alembic; миграции полей прямо в
  `migrate_prompt_templates` при каждом старте.
- **Фоновые задачи:** `APScheduler` (`AsyncIOScheduler`) в том же
  процессе — почасовая синхронизация и синхронизация по расписанию
  утром, без отдельного воркера/очереди.
- **Интеграция с Mi Fitness:** собственный пакет `src/mi_fitness_sync` —
  реверс-инжиниринг приватного облачного API Xiaomi (`requests` +
  ручная реализация RC4-шифрования запросов и AES-расшифровки бинарных
  файлов через `pycryptodome`), подробности —
  [`docs/integrations.md`](docs/integrations.md).
- **AI-тренер:** не прямой вызов Anthropic API, а системный вызов
  установленного в контейнер `claude` (Claude Code CLI) как subprocess —
  подробности в [`docs/ai-assistant.md`](docs/ai-assistant.md).
- **Тесты:** `pytest` + `pytest-asyncio` + `httpx` (`FastAPI TestClient`),
  74 теста в `tests/`.
- **Деплой:** Docker (multi-stage: Node-слой для Claude CLI + Python
  3.12-slim), рассчитан на Coolify — см.
  [`docs/deployment.md`](docs/deployment.md).

## Быстрый старт

### Требования

- Python 3.12+
- Аккаунт Xiaomi с включённой синхронизацией тренировок в Mi Fitness
- (опционально, для AI-тренера) установленный и авторизованный
  [Claude Code CLI](https://claude.com/product/claude-code)

### Установка

```bash
pip install -e ".[dev]"
cp .env.example .env
```

### Конфигурация (`.env`)

| Переменная | Назначение | По умолчанию (dev) |
| --- | --- | --- |
| `DB_PATH` | Путь к файлу SQLite | `~/.running_portal/portal.db` |
| `MI_FITNESS_STATE_PATH` | Путь к файлу с авторизационным состоянием Mi Fitness (токены, cookies) | `~/.running_portal/auth.json` |
| `MI_FITNESS_CACHE_DIR` | Каталог кэша скачанных FDS-файлов (GPS/пульс) | `~/.running_portal/fds_cache` |
| `MI_FITNESS_COUNTRY_CODE` | Код страны для выбора региона Mi Fitness API | `RU` |
| `MI_FITNESS_EMAIL` | Email для автоматического повторного входа при `401` | не задано |
| `MI_FITNESS_PASSWORD` | Пароль для автоматического повторного входа при `401`; без него истёкшую сессию нужно обновлять вручную через UI | не задано |
| `CLAUDE_CLI_PATH` | Путь к бинарю `claude` для AI-тренера | `/home/<user>/.local/bin/claude` (dev) / `/usr/local/bin/claude` (Docker) |
| `ANTHROPIC_API_KEY` | Резервная авторизация Claude CLI | не задано |
| `AUTO_SYNC_INTERVAL_HOURS` | Интервал фоновой синхронизации в часах (`0` — выключить) | `1` |
| `MORNING_SYNC_TIME` | Время утренней синхронизации, `HH:MM` | `09:00` |
| `PORT` | Порт uvicorn | `8000` |

`.env.production.example` — шаблон для деплоя (Coolify), с путями
`/data/running-portal/...` вместо `~/.running_portal/...`.

### Запуск

```bash
uvicorn portal.main:app --reload --port 8001
```

При старте (`lifespan` в `portal/main.py`) приложение создаёт директорию
БД, инициализирует схему SQLite, сеет дефолтные настройки и промпт-шаблоны
и запускает планировщик синхронизации.

Первый вход в Mi Fitness — через `/api/auth/login` (email + пароль);
сохранённая сессия обновляется автоматически, пока не истечёт
`passToken`.

### Тесты

```bash
python -m pytest tests/ -v
```

## Структура репозитория

```
portal/
  main.py                    # FastAPI-приложение, HTML-страницы, lifespan (init БД + планировщик)
  db.py                      # схема SQLite, дефолтные настройки/промпты, CRUD
  sync.py                    # синхронизация с Mi Fitness, кэш деталей, retry при 401
  scheduler.py                # APScheduler: почасовой + утренний sync
  infrastructure/
    config.py                 # чтение переменных окружения
  routers/
    activities.py              # список пробежек, прогресс/EF, детали
    ai.py                      # три AI-функции: разбор, ответ на сегодня, цель на месяц
    auth.py                    # /api/auth/login, /api/auth/status (Mi Fitness)
    claude_auth.py              # /claude-auth: обновление OAuth-сессии Claude CLI
    goals.py                    # /api/goals/monthly, .../suggest
    health.py                   # /api/health-states — журнал состояния
    settings.py                 # редактируемые настройки и prompt-шаблоны
    sync.py                     # /api/sync, /api/sync/status
    assistant_manifest.py       # /.well-known/assistant-integration.json
src/mi_fitness_sync/          # отдельный пакет: клиент приватного API Mi Fitness
  auth/                        # логин, хранение и обновление токенов
  activity/                    # список/детали активностей, крипто, транспорт
  fds/                         # скачивание и разбор бинарных GPS/пульс-файлов
templates/                    # Jinja2-страницы
static/                       # JS/CSS без сборки (app.js, style.css)
tests/                        # pytest, 74 теста
docs/                          # архитектура, модель данных, сценарии, AI, интеграции, деплой
Dockerfile                    # multi-stage сборка (Node/Claude CLI + Python)
```

Подробности — в [`docs/`](./docs):

- [`docs/architecture.md`](./docs/architecture.md) — компоненты и как они взаимодействуют, ER-диаграмма.
- [`docs/data-model.md`](./docs/data-model.md) — таблицы и поля.
- [`docs/workflows.md`](./docs/workflows.md) — пользовательские сценарии по шагам.
- [`docs/ai-assistant.md`](./docs/ai-assistant.md) — устройство AI-тренера: вход, модель, промпты, выход.
- [`docs/integrations.md`](./docs/integrations.md) — интеграция с Mi Fitness: формат, авторизация, ограничения.
- [`docs/deployment.md`](./docs/deployment.md) — Docker-деплой; операционные детали текущего Coolify-инстанса — в [`docs/coolify-deploy.md`](./docs/coolify-deploy.md).

## Лицензия

Файла `LICENSE` в репозитории нет — нужно добавить, если проект должен
быть лицензирован явно.
