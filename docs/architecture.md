# Архитектура

## Обзор

Классическое серверное веб-приложение на FastAPI: один процесс, Jinja2
рендерит HTML на сервере, `static/app.js` донастраивает интерактив
(графики Chart.js, модалки, полинг статуса синка) через `fetch`-запросы к
`/api/...`. Полностью синхронный монолит без очередей и отдельных
воркеров: фоновые задачи — это `APScheduler` внутри того же процесса
(`portal/scheduler.py`), а вызовы Mi Fitness API и Claude CLI выполняются
в хендлерах запросов (блокирующие вызовы — через `asyncio.to_thread` или
напрямую блокирующий `subprocess.Popen` в потоке event loop).

Отдельного сервиса аутентификации портала нет — маршруты `/api/*` и
HTML-страницы открыты без проверки личности. Авторизация есть только у
двух внешних интеграций: Mi Fitness (`/api/auth/*`, состояние в
`MI_FITNESS_STATE_PATH`) и Claude CLI (`/claude-auth`, файл
`~/.claude/.credentials.json`).

```mermaid
flowchart TB
    subgraph Browser["Браузер"]
        UI["Jinja2-страницы + static/app.js<br/>(дашборд, детали пробежки, настройки, здоровье)"]
    end

    subgraph App["FastAPI-приложение (portal/)"]
        R_ACT["routers/activities<br/>список, прогресс/EF, детали"]
        R_AI["routers/ai<br/>разбор / ответ на сегодня / цель на месяц"]
        R_GOALS["routers/goals<br/>/api/goals/monthly"]
        R_HEALTH["routers/health<br/>/api/health-states"]
        R_SETTINGS["routers/settings<br/>prompt-шаблоны, зона, карточки"]
        R_SYNC["routers/sync<br/>/api/sync, /api/sync/status"]
        R_AUTH["routers/auth<br/>/api/auth/login, /status"]
        R_CLAUDE["routers/claude_auth<br/>/claude-auth"]
        R_MANIFEST["routers/assistant_manifest<br/>/.well-known/assistant-integration.json"]
        SCHED["scheduler.py<br/>APScheduler: почасовой + утренний sync"]
    end

    DB[("SQLite<br/>portal/db.py")]
    MIFIT["src/mi_fitness_sync<br/>клиент Mi Fitness API"]
    CLI["Claude Code CLI<br/>(subprocess, локально/в контейнере)"]
    XIAOMI["Xiaomi account/health API<br/>account.xiaomi.com · hlth.io.mi.com"]
    EXT_ASSISTANT["Внешний AI-ассистент<br/>(потребитель манифеста, вне этого репозитория)"]

    UI --> R_ACT & R_AI & R_GOALS & R_HEALTH & R_SETTINGS & R_SYNC & R_AUTH & R_CLAUDE
    EXT_ASSISTANT -->|GET, без авторизации| R_MANIFEST

    SCHED -->|sync_activities| R_SYNC
    SCHED -->|generate_daily_recommendation| R_AI

    R_SYNC --> MIFIT
    R_ACT --> MIFIT
    R_AUTH --> MIFIT
    MIFIT -->|RC4/AES, подписанные запросы| XIAOMI

    R_AI -->|subprocess -p prompt --output-format stream-json| CLI
    R_GOALS -->|generate_goal_suggestion| R_AI
    R_CLAUDE -->|subprocess auth login| CLI

    R_ACT & R_AI & R_GOALS & R_HEALTH & R_SETTINGS & R_SYNC --> DB
```

## Точка входа и жизненный цикл

`portal/main.py` собирает `FastAPI(lifespan=lifespan)`, подключает все
роутеры под префиксом `/api` (кроме `assistant_manifest`, у него свой
путь `/.well-known/...`) и монтирует `static/`. `lifespan`
(`portal/main.py:27`) при старте создаёт директорию БД, вызывает
`init_db` (создание схемы + сидирование дефолтных настроек +
миграция prompt-шаблонов) и запускает планировщик; при остановке —
глушит планировщик.

HTML-страницы, которые отдаёт `main.py` напрямую (не через роутер):
`/` (дашборд), `/activity/{activity_id}`, `/settings`, `/claude-auth`,
`/health`.

## Планировщик

`portal/scheduler.py` — `AsyncIOScheduler` в том же процессе. Два джоба:

- `auto_sync` — интервал `AUTO_SYNC_INTERVAL_HOURS` часов (по умолчанию
  1; `0` — джоб не создаётся);
- `morning_sync` — cron на `MORNING_SYNC_TIME` (по умолчанию `09:00`).

Оба вызывают один и тот же `scheduled_sync()`, защищённый `asyncio.Lock`,
чтобы не запускать параллельно две синхронизации. После успешной
синхронизации с реальными изменениями (`added > 0` или `updated > 0`)
джоб сразу пересчитывает «ответ на сегодня»
(`generate_daily_recommendation`).

## Соединение с БД — без пула

Каждый HTTP-хендлер и каждая фоновая задача открывают собственное
соединение `aiosqlite` через `connect_db()` и закрывают его в `finally` —
постоянного пула соединений нет (`portal/db.py`). При высокой
параллельности это может стать узким местом, но при личном
однопользовательском использовании не критично.

## Синхронизация: где обрезается объём данных

`sync_activities()` (`portal/sync.py`) при первом запуске (нет ни одной
сохранённой активности) берёт `DEFAULT_SYNC_LOOKBACK_DAYS = 90` дней
назад; при повторных — от даты последней сохранённой активности.
Отфильтровываются активности не категории `running` и короче 300 метров.
Детали (GPS-трек, посекундные пульс/темп) автоматически подгружаются
только если за один прогон синхронизации добавилась **ровно одна** новая
активность (`portal/sync.py:323`) — иначе их нужно грузить вручную
кнопкой «Загрузить все детали» (`/api/activities/details/load-all`).

## Схема данных (ER)

```mermaid
erDiagram
    activities ||--o| activity_details : "activity_id"
    activities ||--o| ai_analysis : "activity_id"
    sync_log ||--o{ daily_recommendation : "sync_id"

    activities {
        text activity_id PK
        text date
        real distance_km
        int duration_seconds
        int avg_hrm
        int avg_pace
        int avg_cadence
        int avg_stride
        int train_load
        int recover_time
        int vo2_max
        real aerobic_train_effect
        real anaerobic_train_effect
        int hrm_warm_up_duration
        int hrm_fat_burning_duration
        int hrm_aerobic_duration
        int hrm_anaerobic_duration
        int hrm_extreme_duration
        real avg_vertical_stride_ratio
        int avg_touchdown_duration
        real avg_vertical_amplitude
        text raw_report "JSON, сырой ответ Xiaomi"
        text synced_at
    }
    activity_details {
        text activity_id PK, FK
        text samples "JSON: посекундные HR/каденс/темп"
        text track_points "JSON: GPS-точки"
        text raw_detail "JSON, сырой ответ Xiaomi"
        text fetched_at "TTL кэша — 7 дней"
    }
    sync_log {
        int id PK
        text started_at
        text finished_at
        int activities_added
        int activities_updated
        text error
    }
    ai_analysis {
        text activity_id PK, FK
        text analysis "текст разбора AI-тренера"
        text created_at
    }
    daily_recommendation {
        int id PK
        text date
        text status "run | run_easy | rest"
        text message
        text generated_at
        int sync_id FK
    }
    settings {
        text key PK
        text value
        text updated_at
    }
    monthly_goals {
        int id PK
        int year
        int month
        real km_goal
        int runs_goal
        text created_at
        text ai_suggestion
    }
    health_states {
        int id PK
        text description
        text started_at
        text ended_at
        text created_at
        text updated_at
    }
```

Все таблицы — общие на всё приложение, колонки `user_id` нигде нет:
портал рассчитан на одного пользователя (см.
[`PRODUCTION_READINESS.md`](../PRODUCTION_READINESS.md) — там же зафиксирован
путь к многопользовательской версии, которая пока не реализована).
Подробности по полям — в [`docs/data-model.md`](./data-model.md).
