# Промпт #4 — AI тренер через Claude CLI + SSE стрим

## Контекст

Проект `running-portal`. AI анализ реализуется через локальный CLI `claude`,
запущенный через `subprocess.Popen` — точно так же как в gitlab-panel.

Путь к CLI: `/home/hram/.local/bin/claude` (читается из env `CLAUDE_CLI_PATH`).

Формат запуска (из gitlab-panel):
```python
subprocess.Popen(
    [CLAUDE_CLI_PATH, '-p', prompt, '--output-format', 'stream-json', '--verbose'],
    stdout=PIPE, stderr=PIPE
)
```

Ответ приходит потоком JSON-событий. Нужно вытаскивать блоки `assistant`
и отдавать на фронт через SSE.

---

## Задача 1 — portal/infrastructure/config.py

Создай файл:

```python
import os

CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", "/home/hram/.local/bin/claude")
DB_PATH = os.getenv("DB_PATH", "~/.running_portal/portal.db")
MI_FITNESS_STATE_PATH = os.getenv("MI_FITNESS_STATE_PATH", "~/.running_portal/auth.json")
MI_FITNESS_CACHE_DIR = os.getenv("MI_FITNESS_CACHE_DIR", "~/.running_portal/fds_cache")
MI_FITNESS_COUNTRY_CODE = os.getenv("MI_FITNESS_COUNTRY_CODE", "RU")
```

Обнови `portal/main.py` и `portal/sync.py` — читай конфиг отсюда вместо
прямых `os.getenv()` вызовов.

Добавь в `.env.example`:
```
CLAUDE_CLI_PATH=/home/hram/.local/bin/claude
```

---

## Задача 2 — portal/routers/ai.py

Полная реализация. Два эндпоинта.

### `POST /api/ai/analyze`

Только проверяет кэш, не запускает CLI.

```python
class AnalyzeRequest(BaseModel):
    activity_id: str
    force_refresh: bool = False
```

Логика:
1. Загрузи активность из БД — если нет, верни 404
2. Если `force_refresh=False` — проверь кэш через `get_ai_analysis(conn, activity_id)`
3. Если кэш есть — верни `{"analysis": "...", "cached": True, "activity_id": "..."}`
4. Если кэша нет или `force_refresh=True` — верни:
   `{"analysis": null, "cached": False, "stream_url": f"/api/ai/analyze/stream?activity_id={activity_id}"}`

### `GET /api/ai/analyze/stream?activity_id=...`

SSE эндпоинт. Запускает `claude` CLI и стримит ответ.

```python
from fastapi.responses import StreamingResponse
from portal.infrastructure.config import CLAUDE_CLI_PATH
import subprocess, json, asyncio

@router.get("/api/ai/analyze/stream")
async def analyze_stream(activity_id: str):
    return StreamingResponse(
        _analysis_stream(activity_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

async def _analysis_stream(activity_id: str):
    async with get_db() as conn:
        activity = await get_activity(conn, activity_id)
        if not activity:
            yield f"data: {json.dumps({'error': 'Activity not found'})}\n\n"
            return
        recent = await get_activities(conn, limit=10, offset=0)
        prompt = build_prompt(activity, recent)

    full_text = []

    try:
        process = subprocess.Popen(
            [CLAUDE_CLI_PATH, '-p', prompt,
             '--output-format', 'stream-json', '--verbose'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if event.get('type') == 'assistant':
                    for block in event.get('message', {}).get('content', []):
                        if block.get('type') == 'text':
                            chunk = block['text']
                            full_text.append(chunk)
                            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                elif event.get('type') == 'result':
                    analysis = ''.join(full_text)
                    if analysis:
                        async with get_db() as conn:
                            await save_ai_analysis(conn, activity_id, analysis)
                    yield f"data: {json.dumps({'done': True, 'cached': False})}\n\n"
                    return
            except json.JSONDecodeError:
                continue

        process.wait()
        analysis = ''.join(full_text)
        if analysis:
            async with get_db() as conn:
                await save_ai_analysis(conn, activity_id, analysis)
        yield f"data: {json.dumps({'done': True, 'cached': False})}\n\n"

    except FileNotFoundError:
        yield f"data: {json.dumps({'error': f'Claude CLI не найден: {CLAUDE_CLI_PATH}'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
```

### `build_prompt(activity, recent)` — в том же файле

```python
def build_prompt(activity: dict, recent: list[dict]) -> str:
    def fmt_pace(s):
        if not s: return "—"
        return f"{s//60}:{s%60:02d}/км"

    def fmt_zones(a):
        total = sum([
            a.get('hrm_fat_burning_duration') or 0,
            a.get('hrm_aerobic_duration') or 0,
            a.get('hrm_anaerobic_duration') or 0,
            a.get('hrm_extreme_duration') or 0,
        ])
        if total == 0:
            return "нет данных"
        def pct(v):
            return f"{round((v or 0) / total * 100)}%"
        return (
            f"жиросжигание {pct(a.get('hrm_fat_burning_duration'))}, "
            f"аэробная {pct(a.get('hrm_aerobic_duration'))}, "
            f"анаэробная {pct(a.get('hrm_anaerobic_duration'))}, "
            f"экстремальная {pct(a.get('hrm_extreme_duration'))}"
        )

    recent_lines = "\n".join([
        f"  {r['date'][:10]}: {r['distance_km']}км, "
        f"пульс {r['avg_hrm']}, темп {fmt_pace(r['avg_pace'])}, "
        f"нагрузка {r['train_load']}"
        for r in recent
    ])

    return f"""Ты персональный тренер по бегу. Говори коротко и по-русски, \
как живой тренер — без воды. Пиши связным текстом, 3–5 предложений.

Бегун восстанавливается после травмы ступней и голеностопа. \
Цель: войти в ритм, бегать регулярно. \
Недавно купил новые кроссовки 361 KAIROS 2 (стек 34мм, перепад 8мм) — \
первые недели в них.

Пробежка {activity['date'][:10]}:
- Дистанция: {activity['distance_km']} км
- Пульс: {activity['avg_hrm']} уд/мин
- Темп: {fmt_pace(activity['avg_pace'])}
- Каденс: {activity['avg_cadence']} ш/мин
- Длина шага: {activity['avg_stride']} см
- Нагрузка: {activity['train_load']}
- Восстановление: {activity['recover_time']} ч
- Пульсовые зоны: {fmt_zones(activity)}

Последние 10 пробежек:
{recent_lines}

Дай короткий анализ этой пробежки и одну конкретную рекомендацию \
на следующую тренировку."""
```

---

## Задача 3 — Кэш в portal/db.py

Добавь таблицу в схему и вызови в `init_db()`:

```sql
CREATE TABLE IF NOT EXISTS ai_analysis (
    activity_id  TEXT PRIMARY KEY,
    analysis     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);
```

Добавь функции:

```python
async def get_ai_analysis(conn, activity_id: str) -> str | None:
    ...

async def save_ai_analysis(conn, activity_id: str, analysis: str):
    ...
```

---

## Задача 4 — UI в templates/detail.html

Найди секцию AI тренера и замени на:

```html
<section class="card" id="ai-section">
  <div class="card-header">
    <h2>AI тренер</h2>
    <span class="card-hint">Персональный анализ на основе твоих данных</span>
  </div>

  <input type="hidden" id="activity-id" value="{{ activity.activity_id }}">

  <div id="ai-result" class="ai-bubble" style="display:none"></div>

  <div id="ai-loading" style="display:none">
    <span class="spinner"></span> Тренер анализирует пробежку...
  </div>

  <div id="ai-controls">
    <button class="btn" onclick="getAnalysis()">Получить анализ</button>
    <button class="btn btn-secondary" onclick="getAnalysis(true)"
            id="refresh-btn" style="display:none">
      Обновить анализ
    </button>
    <span id="ai-cached-badge" class="badge" style="display:none">из кэша</span>
  </div>
</section>
```

---

## Задача 5 — JS в static/app.js

```javascript
async function getAnalysis(forceRefresh = false) {
  const activityId = document.getElementById('activity-id')?.value;
  if (!activityId) return;

  const resultEl   = document.getElementById('ai-result');
  const loadingEl  = document.getElementById('ai-loading');
  const controlsEl = document.getElementById('ai-controls');
  const cachedBadge = document.getElementById('ai-cached-badge');
  const refreshBtn  = document.getElementById('refresh-btn');

  // Проверяем кэш
  if (!forceRefresh) {
    const res = await fetch('/api/ai/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({activity_id: activityId, force_refresh: false})
    });
    const data = await res.json();
    if (data.cached && data.analysis) {
      resultEl.textContent = data.analysis;
      resultEl.style.display = 'block';
      cachedBadge.style.display = 'inline';
      refreshBtn.style.display = 'inline-block';
      return;
    }
  }

  // Стрим
  resultEl.textContent = '';
  resultEl.style.display = 'block';
  loadingEl.style.display = 'block';
  controlsEl.style.display = 'none';
  cachedBadge.style.display = 'none';

  const url = `/api/ai/analyze/stream?activity_id=${encodeURIComponent(activityId)}`;
  const source = new EventSource(url);

  source.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.error) {
      resultEl.textContent = 'Ошибка: ' + data.error;
      loadingEl.style.display = 'none';
      controlsEl.style.display = 'block';
      source.close();
      return;
    }
    if (data.chunk) {
      resultEl.textContent += data.chunk;
    }
    if (data.done) {
      loadingEl.style.display = 'none';
      controlsEl.style.display = 'block';
      refreshBtn.style.display = 'inline-block';
      source.close();
    }
  };

  source.onerror = () => {
    loadingEl.style.display = 'none';
    controlsEl.style.display = 'block';
    resultEl.textContent += '\n[Соединение прервано]';
    source.close();
  };
}
```

---

## Задача 6 — CSS в static/style.css

```css
.ai-bubble {
  background: var(--bg3);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text);
  white-space: pre-wrap;
  border-left: 3px solid var(--blue);
  margin-bottom: 1rem;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  background: var(--bg3);
  color: var(--text2);
  border: 0.5px solid var(--border);
  margin-left: 8px;
  vertical-align: middle;
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--text2);
  border-radius: 50%;
  animation: spin .7s linear infinite;
  vertical-align: middle;
  margin-right: 6px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
```

---

## Задача 7 — Тесты

### tests/test_db.py — добавь:

```python
# test_save_and_get_ai_analysis
# — save_ai_analysis сохраняет текст
# — get_ai_analysis возвращает его обратно

# test_get_ai_analysis_returns_none_if_missing
# — get_ai_analysis для несуществующего activity_id возвращает None
```

### tests/test_ai.py — новый файл:

```python
# test_analyze_returns_cached_result
# — сохрани анализ через save_ai_analysis
# — POST /api/ai/analyze с force_refresh=False
# — проверь cached=True и правильный текст

# test_analyze_returns_stream_url_when_no_cache
# — POST /api/ai/analyze для активности без кэша
# — проверь cached=False и наличие stream_url

# test_analyze_returns_404_for_unknown_activity
# — POST /api/ai/analyze с несуществующим activity_id
# — ожидаем 404
```

---

## Финальные шаги

```bash
cd running-portal
python -m pytest tests/ -v
uvicorn portal.main:app --port 8001 --reload
```

Сообщи:
1. Результат pytest (passed/failed)
2. Открой детальную страницу любой пробежки, нажми "Получить анализ"
3. Текст стримится по словам или появляется целиком?
4. При повторном нажатии — появился бейдж "из кэша"?
5. Любые ошибки в терминале сервера
