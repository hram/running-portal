# Промпт #11 — Карточка "Цель на месяц"

## Контекст

Проект `running-portal`. Код актуальный — прочитан из репозитория.

Задача: добавить карточку "Цель на месяц" на главную страницу.
AI помогает ставить цель, отслеживает прогресс, даёт рекомендации.

---

## Задача 1 — portal/db.py

Добавь таблицу и функции:

```sql
CREATE TABLE IF NOT EXISTS monthly_goals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    year         INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    km_goal      REAL NOT NULL,
    runs_goal    INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    ai_suggestion TEXT,
    UNIQUE(year, month)
);
```

Функции:

```python
async def get_monthly_goal(conn, year: int, month: int) -> dict | None:
    """Возвращает цель на указанный месяц."""
    cursor = await conn.execute(
        "SELECT * FROM monthly_goals WHERE year = ? AND month = ?",
        (year, month)
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)

async def save_monthly_goal(
    conn,
    year: int,
    month: int,
    km_goal: float,
    runs_goal: int,
    ai_suggestion: str | None = None,
) -> None:
    """Создаёт или обновляет цель на месяц."""
    await conn.execute(
        """
        INSERT INTO monthly_goals (year, month, km_goal, runs_goal, created_at, ai_suggestion)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(year, month) DO UPDATE SET
            km_goal = excluded.km_goal,
            runs_goal = excluded.runs_goal,
            ai_suggestion = excluded.ai_suggestion
        """,
        (year, month, km_goal, runs_goal, utc_now_iso(), ai_suggestion)
    )
    await conn.commit()

async def get_monthly_progress(conn, year: int, month: int) -> dict:
    """Считает прогресс за указанный месяц из таблицы activities."""
    cursor = await conn.execute(
        """
        SELECT
            COUNT(*) as runs_count,
            COALESCE(SUM(distance_km), 0) as total_km
        FROM activities
        WHERE strftime('%Y', date) = ?
          AND strftime('%m', date) = ?
        """,
        (str(year), f"{month:02d}")
    )
    row = await cursor.fetchone()
    return {
        "runs_count": row["runs_count"] if row else 0,
        "total_km": round(float(row["total_km"]), 2) if row else 0.0,
    }
```

Вызови `CREATE TABLE` в `init_db()`.

---

## Задача 2 — portal/routers/goals.py

Создай новый файл:

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from portal.db import (
    connect_db,
    get_activities,
    get_monthly_goal,
    get_monthly_progress,
    save_monthly_goal,
)
from portal.sync import _resolve_db_path
from portal.routers.ai import generate_goal_suggestion

router = APIRouter()


class GoalRequest(BaseModel):
    year: int
    month: int
    km_goal: float
    runs_goal: int


@router.get("/goals/monthly")
async def get_goal(year: int | None = None, month: int | None = None):
    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month

    conn = await connect_db(_resolve_db_path())
    try:
        goal = await get_monthly_goal(conn, year, month)
        progress = await get_monthly_progress(conn, year, month)
    finally:
        await conn.close()

    # Сколько дней в месяце прошло
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    today = now.day if (now.year == year and now.month == month) else days_in_month
    days_elapsed_pct = round(today / days_in_month * 100, 1)

    if not goal:
        return {
            "goal": None,
            "progress": progress,
            "days_elapsed_pct": days_elapsed_pct,
            "status": "no_goal",
        }

    km_pct = round(progress["total_km"] / goal["km_goal"] * 100, 1) if goal["km_goal"] > 0 else 0
    runs_pct = round(progress["runs_count"] / goal["runs_goal"] * 100, 1) if goal["runs_goal"] > 0 else 0

    # Статус
    if km_pct >= days_elapsed_pct - 5:
        status = "on_track"
    elif km_pct >= days_elapsed_pct - 15:
        status = "slightly_behind"
    else:
        status = "behind"

    # Что нужно для выполнения цели
    km_remaining = round(max(0, goal["km_goal"] - progress["total_km"]), 1)
    runs_remaining = max(0, goal["runs_goal"] - progress["runs_count"])
    days_remaining = days_in_month - today

    return {
        "goal": goal,
        "progress": progress,
        "km_pct": km_pct,
        "runs_pct": runs_pct,
        "days_elapsed_pct": days_elapsed_pct,
        "km_remaining": km_remaining,
        "runs_remaining": runs_remaining,
        "days_remaining": days_remaining,
        "status": status,
    }


@router.post("/goals/monthly")
async def set_goal(body: GoalRequest):
    conn = await connect_db(_resolve_db_path())
    try:
        await save_monthly_goal(
            conn,
            year=body.year,
            month=body.month,
            km_goal=body.km_goal,
            runs_goal=body.runs_goal,
        )
        goal = await get_monthly_goal(conn, body.year, body.month)
    finally:
        await conn.close()
    return {"ok": True, "goal": goal}


@router.get("/goals/monthly/suggest")
async def suggest_goal(year: int | None = None, month: int | None = None):
    """AI анализирует историю и предлагает цель на месяц."""
    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month

    conn = await connect_db(_resolve_db_path())
    try:
        # Берём данные за последние 2 месяца для контекста
        activities = await get_activities(conn, limit=40, offset=0)
    finally:
        await conn.close()

    suggestion = await generate_goal_suggestion(activities, year, month)
    return suggestion
```

---

## Задача 3 — portal/routers/ai.py

Добавь функцию `generate_goal_suggestion`:

```python
async def generate_goal_suggestion(
    activities: list[dict],
    year: int,
    month: int,
) -> dict:
    """Генерирует предложение цели на месяц через Claude CLI."""
    import calendar
    month_name_ru = [
        '', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
        'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'
    ][month]

    if not activities:
        return {
            "km_goal": 40.0,
            "runs_goal": 10,
            "message": "Нет данных для анализа. Предлагаю начать с 40 км / 10 пробежек.",
            "reasoning": "default"
        }

    def fmt_pace(s):
        if not s: return "—"
        return f"{s//60}:{s%60:02d}/км"

    # Статистика по месяцам
    from collections import defaultdict
    monthly = defaultdict(lambda: {"km": 0.0, "runs": 0})
    for a in activities:
        date_str = a.get("date", "")
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            key = f"{dt.year}-{dt.month:02d}"
            monthly[key]["km"] += a.get("distance_km") or 0
            monthly[key]["runs"] += 1
        except Exception:
            continue

    monthly_lines = "\n".join([
        f"  {k}: {v['km']:.1f} км, {v['runs']} пробежек"
        for k, v in sorted(monthly.items())[-3:]
    ])

    recent_lines = "\n".join([
        f"  {a['date'][:10]}: {a.get('distance_km')}км, пульс {a.get('avg_hrm')}, нагрузка {a.get('train_load')}"
        for a in activities[:7]
    ])

    prompt = f"""Ты персональный тренер по бегу. Отвечай строго в формате JSON.

Бегун восстанавливается после травмы ступней. Цель: войти в ритм, бегать регулярно.

Статистика по последним месяцам:
{monthly_lines}

Последние 7 пробежек:
{recent_lines}

Предложи реалистичную цель на {month_name_ru} {year}.
Учти: нельзя увеличивать нагрузку больше чем на 20% по сравнению с лучшим предыдущим месяцем.

Ответь ТОЛЬКО валидным JSON без markdown:
{{
  "km_goal": <число с одним знаком после запятой>,
  "runs_goal": <целое число>,
  "message": "2-3 предложения: почему именно эта цель и как её достичь",
  "conservative": {{"km_goal": <число>, "runs_goal": <число>}},
  "ambitious": {{"km_goal": <число>, "runs_goal": <число>}}
}}"""

    try:
        process = subprocess.Popen(
            [config.CLAUDE_CLI_PATH, '-p', prompt,
             '--output-format', 'stream-json', '--verbose'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        full_text = []
        for line in process.stdout:
            line = line.strip()
            if not line: continue
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
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        return {
            "km_goal": 50.0,
            "runs_goal": 12,
            "message": f"Не удалось получить анализ: {e}",
            "conservative": {"km_goal": 40.0, "runs_goal": 10},
            "ambitious": {"km_goal": 60.0, "runs_goal": 14},
        }
```

---

## Задача 4 — portal/main.py

Подключи новый роутер:

```python
from portal.routers import goals
app.include_router(goals.router, prefix="/api")
```

---

## Задача 5 — templates/index.html

Добавь карточку после карточки "Прогресс формы":

```html
<div class="card" id="goal-card">
  <div class="card-header">
    <span class="card-title" id="goal-card-title">Цель на месяц</span>
    <span id="goal-status-badge"></span>
  </div>
  <div id="goal-content"></div>
</div>
```

---

## Задача 6 — static/app.js

### Добавь в `initDashboard()`:
```javascript
await renderGoalCard();
```

### Добавь функции:

```javascript
async function renderGoalCard() {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1;

  try {
    const res = await fetch(`/api/goals/monthly?year=${year}&month=${month}`);
    const data = await res.json();

    const MONTH_NAMES = ['','январь','февраль','март','апрель','май','июнь',
                         'июль','август','сентябрь','октябрь','ноябрь','декабрь'];

    const titleEl = document.getElementById("goal-card-title");
    if (titleEl) titleEl.textContent = `Цель на ${MONTH_NAMES[month]}`;

    const content = document.getElementById("goal-content");
    if (!content) return;

    if (data.status === "no_goal") {
      content.innerHTML = `
        <div style="text-align:center;padding:20px 0">
          <div style="font-size:14px;color:var(--text2);margin-bottom:12px">
            Цель на этот месяц не установлена.<br>
            AI проанализирует твою историю и предложит реалистичную цель.
          </div>
          <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
            <button class="btn btn-primary" onclick="suggestGoal(${year},${month})">
              Спросить AI
            </button>
            <button class="btn" onclick="showManualGoalForm(${year},${month})">
              Ввести вручную
            </button>
          </div>
        </div>
        <div id="goal-suggestion" style="display:none"></div>
        <div id="goal-form" style="display:none"></div>
      `;
      return;
    }

    // Есть цель — показываем прогресс
    const { goal, progress, km_pct, runs_pct,
            days_elapsed_pct, km_remaining,
            runs_remaining, days_remaining, status } = data;

    const STATUS_BADGE = {
      on_track:       { cls: 'alert-success', text: 'идёт по плану' },
      slightly_behind:{ cls: 'alert-warning', text: 'немного отстаём' },
      behind:         { cls: 'alert-danger',  text: 'отстаём' },
    };
    const badge = STATUS_BADGE[status] || STATUS_BADGE.on_track;
    const badgeEl = document.getElementById("goal-status-badge");
    if (badgeEl) {
      badgeEl.innerHTML = `<span class="badge" style="
        background:var(--alert-${badge.cls.replace('alert-','')}-bg);
        color:var(--alert-${badge.cls.replace('alert-','')}-text);
        border:0.5px solid var(--alert-${badge.cls.replace('alert-','')}-border)
      ">${badge.text}</span>`;
    }

    content.innerHTML = `
      <div class="metrics" style="grid-template-columns:repeat(4,1fr);margin-bottom:14px">
        <div class="metric">
          <div class="metric-label">Пройдено</div>
          <div class="metric-value">${progress.total_km.toFixed(1)}</div>
          <div class="metric-sub">км из ${goal.km_goal}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Пробежек</div>
          <div class="metric-value">${progress.runs_count}</div>
          <div class="metric-sub">из ${goal.runs_goal}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Осталось</div>
          <div class="metric-value">${km_remaining}</div>
          <div class="metric-sub">км · ${days_remaining} дней</div>
        </div>
        <div class="metric">
          <div class="metric-label">Пробежек ещё</div>
          <div class="metric-value">${runs_remaining}</div>
          <div class="metric-sub">до цели</div>
        </div>
      </div>

      <div class="progress-wrap" style="margin-bottom:10px">
        <div style="display:flex;justify-content:space-between;margin-bottom:5px">
          <span style="font-size:12px;color:var(--text2)">Километры</span>
          <span style="font-size:12px;font-weight:500;color:var(--text)">${km_pct}%</span>
        </div>
        <div style="height:8px;background:var(--bg);border-radius:4px;overflow:visible;position:relative">
          <div style="height:100%;width:${Math.min(km_pct,100)}%;
                      background:#3a5040;border-radius:4px"></div>
          <div style="position:absolute;top:-3px;left:${Math.min(days_elapsed_pct,100)}%;
                      width:2px;height:14px;background:#c8a020;border-radius:1px;
                      transform:translateX(-50%)">
            <span style="position:absolute;top:-17px;left:50%;transform:translateX(-50%);
                         font-size:10px;color:#854F0B;white-space:nowrap">
              план ${days_elapsed_pct}%
            </span>
          </div>
        </div>
      </div>

      <div class="progress-wrap" style="margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;margin-bottom:5px">
          <span style="font-size:12px;color:var(--text2)">Пробежки</span>
          <span style="font-size:12px;font-weight:500;color:var(--text)">${runs_pct}%</span>
        </div>
        <div style="height:8px;background:var(--bg);border-radius:4px;overflow:visible;position:relative">
          <div style="height:100%;width:${Math.min(runs_pct,100)}%;
                      background:#3a5040;border-radius:4px"></div>
          <div style="position:absolute;top:-3px;left:${Math.min(days_elapsed_pct,100)}%;
                      width:2px;height:14px;background:#c8a020;border-radius:1px;
                      transform:translateX(-50%)">
          </div>
        </div>
      </div>

      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn" onclick="suggestGoal(${year},${month})">
          Скорректировать цель
        </button>
        <button class="btn btn-secondary" onclick="showManualGoalForm(${year},${month})">
          Изменить вручную
        </button>
      </div>
      <div id="goal-suggestion" style="display:none;margin-top:12px"></div>
      <div id="goal-form" style="display:none;margin-top:12px"></div>
    `;
  } catch (e) {
    const content = document.getElementById("goal-content");
    if (content) content.textContent = "Не удалось загрузить цель.";
  }
}

async function suggestGoal(year, month) {
  const suggEl = document.getElementById("goal-suggestion");
  const formEl = document.getElementById("goal-form");
  if (!suggEl) return;

  if (formEl) formEl.style.display = "none";
  suggEl.style.display = "block";
  suggEl.innerHTML = `<div class="ai-bubble"><span class="spinner"></span> AI анализирует историю...</div>`;

  try {
    const res = await fetch(`/api/goals/monthly/suggest?year=${year}&month=${month}`);
    const data = await res.json();

    suggEl.innerHTML = `
      <div class="ai-bubble">${data.message || "Анализ получен."}</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px">
        <div class="metric" style="cursor:pointer;border:2px solid transparent"
             onclick="selectGoalVariant(this,${data.conservative?.km_goal},${data.conservative?.runs_goal})"
             data-km="${data.conservative?.km_goal}" data-runs="${data.conservative?.runs_goal}">
          <div class="metric-label">Консервативная</div>
          <div class="metric-value">${data.conservative?.km_goal ?? '—'}</div>
          <div class="metric-sub">км · ${data.conservative?.runs_goal ?? '—'} пробежек</div>
        </div>
        <div class="metric" style="cursor:pointer;border:2px solid #3a5040"
             onclick="selectGoalVariant(this,${data.km_goal},${data.runs_goal})"
             data-km="${data.km_goal}" data-runs="${data.runs_goal}">
          <div class="metric-label">Рекомендуется</div>
          <div class="metric-value">${data.km_goal ?? '—'}</div>
          <div class="metric-sub">км · ${data.runs_goal ?? '—'} пробежек</div>
        </div>
        <div class="metric" style="cursor:pointer;border:2px solid transparent"
             onclick="selectGoalVariant(this,${data.ambitious?.km_goal},${data.ambitious?.runs_goal})"
             data-km="${data.ambitious?.km_goal}" data-runs="${data.ambitious?.runs_goal}">
          <div class="metric-label">Амбициозная</div>
          <div class="metric-value">${data.ambitious?.km_goal ?? '—'}</div>
          <div class="metric-sub">км · ${data.ambitious?.runs_goal ?? '—'} пробежек</div>
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" id="accept-goal-btn"
                onclick="acceptSuggestedGoal(${year},${month})"
                data-km="${data.km_goal}" data-runs="${data.runs_goal}">
          Принять цель
        </button>
        <button class="btn" onclick="document.getElementById('goal-suggestion').style.display='none'">
          Отмена
        </button>
      </div>
    `;
  } catch (e) {
    suggEl.innerHTML = `<div class="ai-bubble">Ошибка: ${e.message}</div>`;
  }
}

function selectGoalVariant(el, km, runs) {
  // Снимаем выделение со всех
  el.closest('.ai-bubble')?.parentElement
    ?.querySelectorAll('.metric[data-km]')
    .forEach(m => m.style.border = '2px solid transparent');
  el.style.border = '2px solid #3a5040';
  // Обновляем кнопку принятия
  const btn = document.getElementById('accept-goal-btn');
  if (btn) { btn.dataset.km = km; btn.dataset.runs = runs; }
}

async function acceptSuggestedGoal(year, month) {
  const btn = document.getElementById('accept-goal-btn');
  if (!btn) return;
  const km = parseFloat(btn.dataset.km);
  const runs = parseInt(btn.dataset.runs);
  await saveGoal(year, month, km, runs);
}

function showManualGoalForm(year, month) {
  const formEl = document.getElementById("goal-form");
  const suggEl = document.getElementById("goal-suggestion");
  if (!formEl) return;
  if (suggEl) suggEl.style.display = "none";
  formEl.style.display = "block";
  formEl.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
      <div>
        <div class="section-label" style="margin-bottom:4px">Километры</div>
        <input type="number" id="goal-km-input" value="50" min="1" max="500"
               style="width:100%;padding:7px 10px;border-radius:var(--radius);
                      border:0.5px solid var(--border-card);background:var(--bg-card);
                      color:var(--text);font-size:14px">
      </div>
      <div>
        <div class="section-label" style="margin-bottom:4px">Пробежек</div>
        <input type="number" id="goal-runs-input" value="12" min="1" max="31"
               style="width:100%;padding:7px 10px;border-radius:var(--radius);
                      border:0.5px solid var(--border-card);background:var(--bg-card);
                      color:var(--text);font-size:14px">
      </div>
    </div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-primary" onclick="saveManualGoal(${year},${month})">Сохранить</button>
      <button class="btn" onclick="document.getElementById('goal-form').style.display='none'">Отмена</button>
    </div>
  `;
}

async function saveManualGoal(year, month) {
  const km = parseFloat(document.getElementById('goal-km-input')?.value);
  const runs = parseInt(document.getElementById('goal-runs-input')?.value);
  if (!km || !runs) return;
  await saveGoal(year, month, km, runs);
}

async function saveGoal(year, month, km, runs) {
  try {
    await fetch('/api/goals/monthly', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({year, month, km_goal: km, runs_goal: runs}),
    });
    await renderGoalCard();
  } catch (e) {
    console.error('Не удалось сохранить цель:', e);
  }
}
```

---

## Задача 7 — Тесты

### tests/test_db.py — добавь:

```python
# test_save_and_get_monthly_goal
# test_get_monthly_progress_counts_correctly
# test_monthly_goal_unique_per_month
```

### tests/test_routers.py — добавь:

```python
# test_get_goal_returns_no_goal_when_not_set
# test_set_and_get_goal
# test_goal_progress_calculates_correctly
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
2. Открой главную страницу — видна ли карточка "Цель на месяц"?
3. Нажми "Спросить AI" — что предложил?
4. Прими цель — обновилась ли карточка с прогрессом?
