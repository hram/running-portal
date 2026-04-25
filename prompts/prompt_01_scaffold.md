# Промпт #1 — Scaffold проекта running-portal

## Задача

Создай новый проект `running-portal`.

---

## Структура директорий

```
running-portal/
  src/
    mi_fitness_sync/        # скопировать из ../mi-fitness-sync/src/mi_fitness_sync/
      activity/             # полностью
      auth/                 # полностью
      fds/                  # полностью
      config.py
      exceptions.py
      paths.py
      __init__.py
  portal/
    __init__.py
    main.py
    db.py
    sync.py
    scheduler.py
    routers/
      __init__.py
      activities.py
      sync.py
      auth.py
  templates/
    base.html
    index.html
    detail.html
  static/
    app.js
    style.css
  tests/
    __init__.py
    test_db.py
    test_sync.py
  pyproject.toml
  .env.example
  README.md
```

---

## pyproject.toml

Python 3.12+. Зависимости:

```toml
[project]
name = "running-portal"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "aiosqlite>=0.20",
    "apscheduler>=3.10",
    "jinja2>=3.1",
    "python-dotenv>=1.0",
    "httpx>=0.27",
    "aiofiles>=23.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx>=0.27"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[tool.setuptools.packages.find]
where = ["src"]
```

---

## .env.example

```
MI_FITNESS_STATE_PATH=~/.running_portal/auth.json
MI_FITNESS_CACHE_DIR=~/.running_portal/fds_cache
DB_PATH=~/.running_portal/portal.db
ANTHROPIC_API_KEY=
PORT=8000
```

---

## portal/main.py

Минимальный FastAPI app:

- Загружает `.env` через `python-dotenv`
- Подключает роутеры: `activities`, `sync`, `auth` с префиксом `/api`
- Монтирует `/static` из папки `static/`
- Jinja2Templates из `templates/`
- Lifespan контекст: инициализирует БД (`init_db`), запускает scheduler, останавливает scheduler при завершении
- `GET /` отдаёт `index.html` через Jinja2
- Логирование через стандартный `logging`, уровень INFO

---

## portal/db.py

Схема SQLite:

```sql
CREATE TABLE IF NOT EXISTS activities (
    activity_id     TEXT PRIMARY KEY,
    date            TEXT NOT NULL,
    distance_km     REAL,
    duration_seconds INTEGER,
    avg_hrm         INTEGER,
    avg_pace        INTEGER,
    avg_cadence     INTEGER,
    avg_stride      INTEGER,
    train_load      INTEGER,
    recover_time    INTEGER,
    vo2_max         INTEGER,
    aerobic_train_effect  REAL,
    anaerobic_train_effect REAL,
    hrm_warm_up_duration      INTEGER,
    hrm_fat_burning_duration  INTEGER,
    hrm_aerobic_duration      INTEGER,
    hrm_anaerobic_duration    INTEGER,
    hrm_extreme_duration      INTEGER,
    avg_vertical_stride_ratio REAL,
    avg_touchdown_duration    INTEGER,
    avg_vertical_amplitude    REAL,
    raw_report      TEXT,
    synced_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_details (
    activity_id  TEXT PRIMARY KEY,
    samples      TEXT,
    track_points TEXT,
    raw_detail   TEXT,
    fetched_at   TEXT NOT NULL,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    activities_added   INTEGER DEFAULT 0,
    activities_updated INTEGER DEFAULT 0,
    error           TEXT
);
```

Реализуй следующие async функции:

| Функция | Описание |
|---|---|
| `init_db(db_path: str)` | Создаёт таблицы если не существуют |
| `upsert_activity(conn, activity_dict)` | INSERT OR REPLACE в activities |
| `upsert_detail(conn, activity_id, detail_dict)` | INSERT OR REPLACE в activity_details |
| `get_activities(conn, limit, offset)` | Список активностей ORDER BY date DESC |
| `get_activity(conn, activity_id)` | Одна активность по ID |
| `get_detail(conn, activity_id)` | Детали одной активности |
| `log_sync_start(conn)` → `int` | Вставляет запись в sync_log, возвращает id |
| `log_sync_finish(conn, sync_id, added, updated, error)` | Обновляет запись sync_log |

---

## portal/routers/activities.py

Заглушки эндпоинтов:

```python
GET /api/activities          # limit=20, offset=0
GET /api/activities/{id}     # детали + samples из activity_details
```

Возвращают `{"status": "not implemented"}` пока.

## portal/routers/sync.py

```python
POST /api/sync               # запустить синк вручную
GET  /api/sync/status        # последние 5 записей из sync_log
```

Возвращают `{"status": "not implemented"}` пока.

## portal/routers/auth.py

```python
POST /api/auth/login         # body: {email, password}
GET  /api/auth/status        # проверить авторизацию
```

Возвращают `{"status": "not implemented"}` пока.

---

## portal/scheduler.py

Заглушка APScheduler:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

def start():
    # TODO: добавить job для автосинка каждый час
    scheduler.start()

def stop():
    scheduler.shutdown()
```

---

## portal/sync.py

Заглушка:

```python
# TODO: реализация в промпте #2
async def sync_activities():
    pass

async def fetch_detail(activity_id: str):
    pass
```

---

## Шаблоны

### templates/base.html

Минимальный HTML5 layout:
- `<title>{% block title %}Running Portal{% endblock %}`
- `<link>` к `/static/style.css`
- `<script>` к `/static/app.js` в конце body
- `{% block content %}{% endblock %}`

### templates/index.html

Расширяет base.html. Пока просто:
```html
<h1>Running Portal</h1>
<p>Dashboard coming soon</p>
```

### templates/detail.html

Расширяет base.html. Пока просто:
```html
<h1>Activity Detail</h1>
<p>Coming soon</p>
```

---

## Копирование mi_fitness_sync

Скопируй `../mi-fitness-sync/src/mi_fitness_sync/` в `running-portal/src/mi_fitness_sync/`.

Исключи:
- `cli/`
- `export/`
- все `__pycache__/`

---

## Тесты

### tests/test_db.py

Полные тесты для всех функций `db.py` используя in-memory SQLite (`:memory:`).

Покрыть:
- `init_db` создаёт все три таблицы
- `upsert_activity` вставляет и обновляет
- `upsert_detail` вставляет и обновляет
- `get_activities` возвращает список с пагинацией
- `get_activity` возвращает одну запись и None если не найдена
- `get_detail` возвращает детали и None если не найдены
- `log_sync_start` / `log_sync_finish` корректно пишут в sync_log

### tests/test_sync.py

Только заглушки с TODO:

```python
# TODO: тесты реализуются в промпте #2
def test_sync_activities_todo():
    pass

def test_fetch_detail_todo():
    pass
```

---

## Финальные шаги

После создания всех файлов выполни:

```bash
cd running-portal
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Сообщи:
1. Результат `pytest` (сколько passed/failed)
2. Любые ошибки импорта
3. Итоговое дерево проекта (`tree` или `find . -type f | sort`)
