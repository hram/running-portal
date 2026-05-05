# running-portal

Локальный FastAPI-портал для просмотра беговых активностей и синхронизации данных из Mi Fitness.

## Контекст

- Стек: Python 3.12+, FastAPI, uvicorn, Jinja2, aiosqlite, APScheduler, httpx, requests, python-dotenv.
- Тесты: pytest, pytest-asyncio.
- Данные хранятся в SQLite; runtime/config-файлы задаются через `.env`, `auth.json` и переменные окружения.
- Авторизационное состояние Mi Fitness лежит в `MI_FITNESS_STATE_PATH`; при `401` приложение пытается обновить сохраненное состояние.

## Архитектура

- `portal/main.py` - FastAPI-приложение, HTML-страницы, API-роутеры, lifespan.
- `portal/db.py` - SQLite-схема, настройки, CRUD для активностей и аналитики.
- `portal/scheduler.py` - фоновые задачи синхронизации.
- `portal/sync.py` - логика синхронизации с Mi Fitness.
- `portal/routers/` - API для активностей, AI, целей, настроек, sync и auth.
- `templates/` - Jinja2-страницы.
- `static/` - frontend на Vanilla JS/CSS.

## Команды

```bash
pip install -e ".[dev]"
uvicorn portal.main:app --reload --port 8001
python -m pytest tests/ -v
```

## Правила работы

- Не коммить секреты и локальное авторизационное состояние.
- Для файловых и DB-сценариев в тестах использовать временные директории.
- После изменений запускать релевантные pytest-тесты проекта.
