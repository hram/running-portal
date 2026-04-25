# Промпт #5 — Карточка "Ответ на сегодня"

## Контекст

Проект `running-portal`. Фазы 1–4 завершены.

Задача: добавить на главную страницу большую карточку вверху с AI рекомендацией
на сегодня. Генерируется один раз после синка, кэшируется до следующего синка.

---

## Логика карточки

Три возможных состояния:

| Состояние | Цвет | Когда |
|---|---|---|
| **Бежать** | зелёный | recover_time последней пробежки истёк, нагрузка в норме |
| **Бежать легко** | жёлтый | пульс был высокий или нагрузка умеренная |
| **Отдыхать** | красный | recover_time не истёк или нагрузка была экстремальная |

Под состоянием — два предложения от AI с объяснением.

---

## Задача 1 — portal/db.py

Добавь таблицу:

```sql
CREATE TABLE IF NOT EXISTS daily_recommendation (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,
    status       TEXT NOT NULL,  -- 'run' | 'run_easy' | 'rest'
    message      TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    sync_id      INTEGER,
    FOREIGN KEY (sync_id) REFERENCES sync_log(id)
);
```

Добавь функции:

```python
async def get_latest_recommendation(conn) -> dict | None:
    # Возвращает последнюю запись из daily_recommendation

async def save_recommendation(conn, status: str, message: str, sync_id: int | None = None):
    # Вставляет новую запись с текущей датой
```

---

## Задача 2 — portal/routers/ai.py

Добавь функцию генерации рекомендации:

### `build_daily_prompt(activities: list[dict]) -> str`

```python
def build_daily_prompt(activities: list[dict]) -> str:
    if not activities:
        return ""

    last = activities[0]
    from datetime import datetime, timezone

    # Сколько часов прошло с последней пробежки
    last_date = datetime.fromisoformat(last['date'])
    now = datetime.now(timezone.utc)
    hours_since = round((now - last_date).total_seconds() / 3600)

    def fmt_pace(s):
        if not s: return "—"
        return f"{s//60}:{s%60:02d}/км"

    recent_lines = "\n".join([
        f"  {r['date'][:10]}: {r['distance_km']}км, пульс {r['avg_hrm']}, "
        f"нагрузка {r['train_load']}, восстановление {r['recover_time']}ч"
        for r in activities[:7]
    ])

    return f"""Ты персональный тренер по бегу. Отвечай строго в формате JSON.

Бегун восстанавливается после травмы ступней. Цель: войти в ритм, бегать регулярно.
Новые кроссовки 361 KAIROS 2 — первые недели в них.

Последняя пробежка: {last['date'][:10]}, {last['distance_km']}км,
пульс {last['avg_hrm']} уд/мин, темп {fmt_pace(last['avg_pace'])},
нагрузка {last['train_load']}, восстановление {last['recover_time']}ч.
С последней пробежки прошло: {hours_since} часов.

Последние 7 пробежек:
{recent_lines}

Ответь ТОЛЬКО валидным JSON без markdown, без пояснений:
{{
  "status": "run" | "run_easy" | "rest",
  "message": "два предложения — анализ ситуации и конкретная рекомендация на сегодня"
}}

Критерии выбора status:
- "rest": recover_time последней пробежки ещё не истёк (часов прошло < recover_time) ИЛИ пульс был > 185
- "run_easy": пульс был 170–185 ИЛИ нагрузка > 200 ИЛИ recover_time почти истёк
- "run": всё в норме, можно бежать в обычном режиме"""
```

### `async def generate_daily_recommendation(sync_id: int | None = None) -> dict`

```python
async def generate_daily_recommendation(sync_id=None):
    async with get_db() as conn:
        activities = await get_activities(conn, limit=10, offset=0)

    if not activities:
        return {"status": "run", "message": "Нет данных для анализа. Начни бегать!"}

    prompt = build_daily_prompt(activities)

    try:
        process = subprocess.Popen(
            [CLAUDE_CLI_PATH, '-p', prompt,
             '--output-format', 'stream-json', '--verbose'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        full_text = []
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if event.get('type') == 'assistant':
                    for block in event.get('message', {}).get('content', []):
                        if block.get('type') == 'text':
                            full_text.append(block['text'])
            except json.JSONDecodeError:
                continue

        process.wait()
        raw = ''.join(full_text).strip()

        # Парсим JSON из ответа
        # Claude может обернуть в ```json ... ``` — чистим
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        result = json.loads(raw)

        status = result.get('status', 'run')
        message = result.get('message', '')

        async with get_db() as conn:
            await save_recommendation(conn, status, message, sync_id)

        return {"status": status, "message": message}

    except Exception as e:
        fallback = {"status": "run", "message": f"Не удалось получить анализ: {e}"}
        return fallback
```

Добавь `import re` в импорты файла.

---

## Задача 3 — portal/routers/sync.py

В эндпоинте `POST /api/sync` после успешного синка добавь вызов генерации рекомендации:

```python
from portal.routers.ai import generate_daily_recommendation

# После sync_activities()
if result.get('error') is None:
    await generate_daily_recommendation(sync_id=sync_log_id)
```

Также добавь эндпоинт для ручной генерации рекомендации:

```python
@router.post("/api/ai/recommendation/refresh")
async def refresh_recommendation():
    result = await generate_daily_recommendation()
    return result
```

---

## Задача 4 — portal/routers/ai.py — GET эндпоинт

```python
@router.get("/api/ai/recommendation")
async def get_recommendation():
    async with get_db() as conn:
        rec = await get_latest_recommendation(conn)
    if not rec:
        return {"status": None, "message": None, "generated_at": None}
    return rec
```

---

## Задача 5 — templates/index.html

Добавь карточку **первой** на странице, до секции "Ключевые метрики":

```html
<!-- Карточка "Ответ на сегодня" -->
<section id="today-card" class="today-card today-card--loading">
  <div class="today-status-icon" id="today-icon">⏳</div>
  <div class="today-content">
    <div class="today-label">Ответ на сегодня</div>
    <div class="today-status" id="today-status">Загрузка...</div>
    <div class="today-message" id="today-message"></div>
  </div>
  <button class="btn btn-secondary today-refresh"
          onclick="refreshRecommendation()"
          title="Обновить рекомендацию">↻</button>
</section>
```

---

## Задача 6 — static/style.css

```css
/* Карточка "Ответ на сегодня" */
.today-card {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  padding: 1.5rem 1.75rem;
  border-radius: var(--radius-lg);
  border: 0.5px solid var(--border);
  margin-bottom: 1.25rem;
  transition: background .2s;
}

.today-card--loading {
  background: var(--bg2);
}

.today-card--run {
  background: linear-gradient(135deg, rgba(99,153,34,0.15), var(--bg2));
  border-color: rgba(99,153,34,0.4);
}

.today-card--run_easy {
  background: linear-gradient(135deg, rgba(239,159,39,0.15), var(--bg2));
  border-color: rgba(239,159,39,0.4);
}

.today-card--rest {
  background: linear-gradient(135deg, rgba(226,75,74,0.15), var(--bg2));
  border-color: rgba(226,75,74,0.4);
}

.today-status-icon {
  font-size: 2.5rem;
  line-height: 1;
  flex-shrink: 0;
}

.today-content {
  flex: 1;
}

.today-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text3);
  margin-bottom: 4px;
}

.today-status {
  font-size: 22px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 6px;
}

.today-card--run .today-status    { color: var(--green); }
.today-card--run_easy .today-status { color: var(--amber); }
.today-card--rest .today-status   { color: var(--red); }

.today-message {
  font-size: 14px;
  color: var(--text2);
  line-height: 1.6;
}

.today-refresh {
  flex-shrink: 0;
  font-size: 18px;
  padding: 6px 10px;
}
```

---

## Задача 7 — static/app.js

Добавь функции:

```javascript
const STATUS_LABELS = {
  'run':      '🏃 Бежать',
  'run_easy': '🚶 Бежать легко',
  'rest':     '😴 Отдыхать',
};

async function loadTodayRecommendation() {
  const card = document.getElementById('today-card');
  if (!card) return;

  try {
    const res = await fetch('/api/ai/recommendation');
    const data = await res.json();

    if (!data.status) {
      document.getElementById('today-status').textContent = 'Нет данных';
      document.getElementById('today-message').textContent =
        'Нажми "Синхронизировать" чтобы получить рекомендацию.';
      return;
    }

    card.className = `today-card today-card--${data.status}`;
    document.getElementById('today-icon').textContent =
      data.status === 'run' ? '🏃' :
      data.status === 'run_easy' ? '🚶' : '😴';
    document.getElementById('today-status').textContent =
      STATUS_LABELS[data.status] || data.status;
    document.getElementById('today-message').textContent = data.message;

  } catch(e) {
    document.getElementById('today-status').textContent = 'Ошибка загрузки';
  }
}

async function refreshRecommendation() {
  const card = document.getElementById('today-card');
  if (card) card.className = 'today-card today-card--loading';
  document.getElementById('today-status').textContent = 'Генерирую...';
  document.getElementById('today-message').textContent = '';

  try {
    await fetch('/api/ai/recommendation/refresh', {method: 'POST'});
    await loadTodayRecommendation();
  } catch(e) {
    document.getElementById('today-status').textContent = 'Ошибка';
  }
}

// Вызывай при загрузке страницы вместе с остальными init функциями
// loadTodayRecommendation();
```

В существующей функции инициализации страницы добавь вызов `loadTodayRecommendation()`.

---

## Задача 8 — Тесты

### tests/test_db.py — добавь:

```python
# test_save_and_get_recommendation
# — save_recommendation сохраняет status и message
# — get_latest_recommendation возвращает последнюю запись

# test_get_latest_recommendation_returns_none_if_empty
```

### tests/test_ai.py — добавь:

```python
# test_get_recommendation_returns_none_when_empty
# — GET /api/ai/recommendation когда таблица пустая
# — ожидаем {"status": null, "message": null}

# test_get_recommendation_returns_latest
# — сохранить рекомендацию в БД
# — GET /api/ai/recommendation
# — проверить status и message
```

---

## Финальные шаги

```bash
cd running-portal
python -m pytest tests/ -v
uvicorn portal.main:app --port 8001 --reload
```

Сообщи:
1. Результат pytest
2. Запусти POST /api/sync — появилась ли рекомендация автоматически:
   `curl -s -X POST http://localhost:8001/api/sync | python -m json.tool`
3. Проверь рекомендацию:
   `curl -s http://localhost:8001/api/ai/recommendation | python -m json.tool`
4. Открой http://localhost:8001 — опиши карточку вверху страницы
