# Промпт #2 — Реализация sync.py и scheduler

## Контекст

Проект `running-portal`. Фаза 1 завершена. Теперь реализуем синхронизацию данных из Mi Fitness.

Точные имена классов из `mi_fitness_sync`:
- `from mi_fitness_sync.auth.client import MiFitnessAuthClient`
- `from mi_fitness_sync.activity.client import MiFitnessActivitiesClient`

---

## Задача 1 — portal/sync.py

Реализуй следующие функции. Изучи сначала исходники:
- `src/mi_fitness_sync/auth/client.py` — как инициализировать и использовать `MiFitnessAuthClient`
- `src/mi_fitness_sync/activity/client.py` — как вызывать `MiFitnessActivitiesClient`, какие методы доступны для листинга активностей и получения деталей
- `src/mi_fitness_sync/activity/models.py` — структура моделей активности
- `src/mi_fitness_sync/paths.py` — как получить дефолтные пути

После изучения реализуй:

### `get_auth_client() -> MiFitnessAuthClient`

Создаёт клиент авторизации используя `MI_FITNESS_STATE_PATH` из `.env` (или дефолтный путь из `paths.py`).

### `get_activity_client() -> MiFitnessActivitiesClient`

Создаёт клиент активностей используя авторизованное состояние.

### `async def sync_activities(since: datetime | None = None) -> dict`

Синхронизирует активности из Mi Fitness в SQLite.

Логика:
1. Если `since=None` — берёт дату последней активности из БД, если БД пустая — берёт 90 дней назад
2. Вызывает `MiFitnessActivitiesClient` для получения списка активностей начиная с `since`
3. Фильтрует только `category == "running"` и `distance_km > 0.3`
4. Для каждой активности вызывает `upsert_activity(conn, activity_dict)`
5. Маппинг полей из модели Mi Fitness в схему БД (все поля из `raw_report`)
6. Логирует в `sync_log` через `log_sync_start` / `log_sync_finish`
7. Возвращает `{"added": N, "updated": N, "total": N, "error": None}`

При любой ошибке: логирует в `sync_log`, возвращает `{"added": 0, "updated": 0, "total": 0, "error": "сообщение"}`

### `async def fetch_detail(activity_id: str) -> dict | None`

Загружает детальные данные одной активности.

Логика:
1. Проверяет есть ли уже в `activity_details` — если есть и `fetched_at` не старше 7 дней, возвращает из кэша
2. Вызывает `MiFitnessActivitiesClient` для получения деталей по `activity_id`
3. Извлекает `samples` и `track_points` из ответа
4. Сохраняет через `upsert_detail(conn, activity_id, detail_dict)`
5. Возвращает `detail_dict` или `None` если не удалось получить

### `async def get_last_sync_date(conn) -> datetime | None`

Возвращает дату последней активности в БД или `None` если БД пустая.

---

## Задача 2 — portal/routers/sync.py

Реализуй эндпоинты:

### `POST /api/sync`

```python
# Запускает sync_activities() и возвращает результат
# Response: {"added": N, "updated": N, "total": N, "error": null, "duration_seconds": X}
```

### `GET /api/sync/status`

```python
# Возвращает последние 10 записей из sync_log
# Response: {"syncs": [...]}
```

---

## Задача 3 — portal/routers/auth.py

Реализуй эндпоинты:

### `GET /api/auth/status`

```python
# Проверяет есть ли сохранённый auth state
# Response: {"authenticated": true/false, "email": "...", "expires_at": "..."}
# Использует MiFitnessAuthClient для проверки статуса без сетевого запроса
```

### `POST /api/auth/login`

```python
# Body: {"email": "...", "password": "..."}
# Вызывает MiFitnessAuthClient.login()
# Response: {"success": true} или {"success": false, "error": "..."}
```

---

## Задача 4 — portal/scheduler.py

Реализуй полноценный scheduler:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from portal.sync import sync_activities
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

async def scheduled_sync():
    logger.info("Scheduler: starting scheduled sync")
    result = await sync_activities()
    logger.info(f"Scheduler: sync complete — {result}")

def start():
    scheduler.add_job(
        scheduled_sync,
        trigger="interval",
        hours=1,
        id="auto_sync",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.start()
    logger.info("Scheduler started, auto-sync every 1 hour")

def stop():
    scheduler.shutdown()
    logger.info("Scheduler stopped")
```

---

## Задача 5 — portal/routers/activities.py

Реализуй эндпоинты:

### `GET /api/activities`

```python
# Query params: limit=20, offset=0
# Response: {"activities": [...], "total": N, "limit": 20, "offset": 0}
```

### `GET /api/activities/{activity_id}`

```python
# Возвращает активность + детали если они есть в activity_details
# Если деталей нет — возвращает активность без деталей, details: null
# Response: {"activity": {...}, "details": {...} | null}
```

### `GET /api/activities/{activity_id}/detail`

```python
# Принудительно загружает детали через fetch_detail()
# Response: {"activity_id": "...", "details": {...}} или 404
```

---

## Задача 6 — Тесты

### tests/test_sync.py

Замени заглушки реальными тестами используя `unittest.mock`:

```python
# test_sync_activities_returns_correct_counts
# — мокает MiFitnessActivitiesClient
# — проверяет что added/updated корректно считаются
# — использует in-memory SQLite

# test_sync_activities_handles_error
# — мокает клиент чтобы бросал исключение
# — проверяет что возвращается {"error": "...", "added": 0}
# — проверяет что sync_log содержит запись об ошибке

# test_fetch_detail_uses_cache
# — проверяет что повторный вызов не делает сетевой запрос
# — если detail уже есть в БД и свежий (< 7 дней)

# test_get_last_sync_date_returns_none_for_empty_db
# test_get_last_sync_date_returns_latest_date
```

### tests/test_routers.py

Новый файл. Тесты для API через `httpx.AsyncClient`:

```python
# test_sync_status_returns_list
# test_auth_status_when_not_authenticated
# test_activities_list_empty
```

---

## Финальные шаги

```bash
cd running-portal
python -m pytest tests/ -v
```

Сообщи:
1. Результат pytest (passed/failed)
2. Если есть ошибки импорта из mi_fitness_sync — покажи полный traceback
3. Пример вывода `curl -s http://localhost:8001/api/auth/status | python -m json.tool`
4. Пример вывода `curl -s http://localhost:8001/api/activities | python -m json.tool`
