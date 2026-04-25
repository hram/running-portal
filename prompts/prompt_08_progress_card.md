# Промпт #8 — Карточка прогресса (Efficiency Factor) на главной странице

## Контекст

Проект `running-portal`. Код актуальный — прочитан из репозитория.

Efficiency Factor (EF) — метрика аэробной эффективности.
Формула: `EF = (1000 / avg_pace * 60) / avg_hrm`
То есть: скорость в м/мин делить на средний пульс.
Чем выше EF — тем лучше форма. Данные есть для всех активностей в БД.

---

## Задача 1 — portal/db.py

Добавь функцию:

```python
async def get_activities_for_ef(conn: aiosqlite.Connection) -> list[dict[str, Any]]:
    """Возвращает все активности с avg_pace и avg_hrm для расчёта EF по неделям."""
    cursor = await conn.execute(
        """
        SELECT date, avg_pace, avg_hrm, distance_km
        FROM activities
        WHERE avg_pace IS NOT NULL
          AND avg_pace > 0
          AND avg_hrm IS NOT NULL
          AND avg_hrm > 0
          AND distance_km > 0.3
        ORDER BY date ASC
        """
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
```

---

## Задача 2 — portal/routers/activities.py

Добавь новый эндпоинт:

```python
from portal.db import get_activities_for_ef

@router.get("/activities/progress")
async def get_progress() -> dict[str, object]:
    conn = await connect_db(_resolve_db_path())
    try:
        activities = await get_activities_for_ef(conn)
    finally:
        await conn.close()

    if not activities:
        return {"weeks": [], "summary": {}}

    # Группируем по неделям (ISO week)
    from datetime import datetime, timezone
    from collections import defaultdict

    weekly: dict[str, list[float]] = defaultdict(list)
    weekly_dates: dict[str, str] = {}

    for a in activities:
        date_str = a["date"]
        # Парсим дату — может быть ISO с timezone
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            continue

        # Ключ недели: год + номер недели ISO
        week_key = dt.strftime("%Y-W%W")
        # Для отображения берём первый день недели
        if week_key not in weekly_dates:
            weekly_dates[week_key] = dt.strftime("%d.%m")

        pace = a["avg_pace"]  # сек/км
        hrm = a["avg_hrm"]
        if pace and hrm and pace > 0 and hrm > 0:
            speed_mpm = 1000 / pace * 60  # м/мин
            ef = round(speed_mpm / hrm, 3)
            weekly[week_key].append(ef)

    # Среднее EF по неделе
    weeks_data = []
    for week_key in sorted(weekly.keys()):
        values = weekly[week_key]
        if values:
            weeks_data.append({
                "week": week_key,
                "label": weekly_dates[week_key],
                "ef": round(sum(values) / len(values), 3),
                "runs": len(values),
            })

    if not weeks_data:
        return {"weeks": [], "summary": {}}

    ef_values = [w["ef"] for w in weeks_data]
    first_ef = ef_values[0]
    last_ef = ef_values[-1]
    max_ef = max(ef_values)
    peak_week = weeks_data[ef_values.index(max_ef)]["label"]

    # Тренд: сравниваем последние 3 недели с предыдущими 3
    trend = None
    if len(ef_values) >= 6:
        recent = sum(ef_values[-3:]) / 3
        prev = sum(ef_values[-6:-3]) / 3
        if prev > 0:
            trend = round((recent - prev) / prev * 100, 1)

    return {
        "weeks": weeks_data,
        "summary": {
            "first_ef": first_ef,
            "last_ef": last_ef,
            "max_ef": max_ef,
            "peak_week": peak_week,
            "trend": trend,
            "total_weeks": len(weeks_data),
        }
    }
```

---

## Задача 3 — templates/index.html

Добавь карточку прогресса между секцией метрик и графиком дистанций:

```html
<div class="card" id="progress-card">
  <div class="card-header">
    <span class="card-title">Прогресс формы</span>
    <span class="card-hint" id="progress-hint"></span>
  </div>
  <div class="progress-summary" id="progress-summary"></div>
  <div class="chart-wrap" style="height:140px;margin-bottom:4px">
    <canvas id="ef-chart" role="img" aria-label="График Efficiency Factor по неделям">EF по неделям</canvas>
  </div>
  <div class="progress-note">
    EF = скорость (м/мин) / пульс — чем выше, тем лучше. Растёт когда форма улучшается.
  </div>
</div>
```

---

## Задача 4 — static/style.css

Добавь стили:

```css
.progress-summary {
  display: flex;
  gap: 20px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.progress-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.progress-stat-label {
  font-size: 10px;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: .06em;
}

.progress-stat-value {
  font-size: 18px;
  font-weight: 500;
  color: var(--text);
}

.progress-stat-value.positive { color: var(--accent); }
.progress-stat-value.negative { color: #a04040; }

.progress-note {
  font-size: 11px;
  color: var(--text3);
  margin-top: 6px;
}

.ef-legend {
  display: flex;
  gap: 16px;
  font-size: 11px;
  color: var(--text3);
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.ef-legend span {
  display: flex;
  align-items: center;
  gap: 5px;
}

.ef-legend-line {
  display: inline-block;
  width: 14px;
  height: 2px;
  border-radius: 1px;
}
```

---

## Задача 5 — static/app.js

### Добавь в `initDashboard()`

После `renderRunsTable(...)` добавь вызов:
```javascript
await renderProgressCard();
```

### Добавь функцию `renderProgressCard()`

```javascript
let efChart = null;

async function renderProgressCard() {
  try {
    const res = await fetch("/api/activities/progress");
    const data = await res.json();
    const weeks = data.weeks || [];
    const summary = data.summary || {};

    if (!weeks.length) {
      const card = document.getElementById("progress-card");
      if (card) card.style.display = "none";
      return;
    }

    // Summary stats
    const summaryEl = document.getElementById("progress-summary");
    if (summaryEl) {
      const trendVal = summary.trend;
      const trendClass = trendVal === null ? "" : trendVal >= 0 ? "positive" : "negative";
      const trendStr = trendVal === null ? "—" : (trendVal >= 0 ? "+" : "") + trendVal.toFixed(1) + "%";

      summaryEl.innerHTML = `
        <div class="progress-stat">
          <span class="progress-stat-label">Начало</span>
          <span class="progress-stat-value">${summary.first_ef?.toFixed(2) ?? "—"}</span>
        </div>
        <div class="progress-stat">
          <span class="progress-stat-label">Сейчас</span>
          <span class="progress-stat-value">${summary.last_ef?.toFixed(2) ?? "—"}</span>
        </div>
        <div class="progress-stat">
          <span class="progress-stat-label">Пик</span>
          <span class="progress-stat-value">${summary.max_ef?.toFixed(2) ?? "—"}</span>
        </div>
        <div class="progress-stat">
          <span class="progress-stat-label">Тренд (3 нед)</span>
          <span class="progress-stat-value ${trendClass}">${trendStr}</span>
        </div>
      `;
    }

    // Hint
    const hintEl = document.getElementById("progress-hint");
    if (hintEl) {
      hintEl.textContent = `${summary.total_weeks} недель · данные из ${weeks.reduce((s, w) => s + w.runs, 0)} пробежек`;
    }

    // Chart
    const canvas = document.getElementById("ef-chart");
    if (!canvas || !window.Chart) return;
    if (efChart) efChart.destroy();

    const labels = weeks.map(w => w.label);
    const efData = weeks.map(w => w.ef);

    // Скользящее среднее (3 недели)
    const trendLine = efData.map((_, i) => {
      const slice = efData.slice(Math.max(0, i - 2), i + 1).filter(v => v != null);
      return slice.length ? parseFloat((slice.reduce((s, v) => s + v, 0) / slice.length).toFixed(3)) : null;
    });

    efChart = new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "EF по неделям",
            data: efData,
            borderColor: "#3a5040",
            backgroundColor: "rgba(58,80,64,0.07)",
            tension: 0.3,
            pointRadius: 3,
            pointBackgroundColor: "#3a5040",
            borderWidth: 2,
            fill: true,
            spanGaps: false,
          },
          {
            label: "тренд",
            data: trendLine,
            borderColor: "#c8a020",
            borderDash: [5, 3],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
            spanGaps: true,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: c => c.datasetIndex === 0
                ? `EF: ${c.parsed.y.toFixed(2)} (${weeks[c.dataIndex]?.runs ?? 0} пробежек)`
                : `тренд: ${c.parsed.y.toFixed(2)}`
            }
          }
        },
        scales: {
          x: {
            ticks: {
              autoSkip: true,
              maxRotation: 45,
              maxTicksLimit: 12,
              font: { size: 10 },
              color: "#90a89a"
            },
            grid: { display: false }
          },
          y: {
            min: 1.8,
            ticks: { font: { size: 10 }, color: "#90a89a", callback: v => v.toFixed(2) },
            grid: { color: "rgba(128,128,128,0.08)" }
          }
        }
      }
    });

  } catch (e) {
    const card = document.getElementById("progress-card");
    if (card) card.style.display = "none";
  }
}
```

---

## Задача 6 — Тесты

### tests/test_db.py — добавь:

```python
# test_get_activities_for_ef_returns_only_valid
# — вставить 3 активности: одна без avg_pace, одна с нулевым hrm, одна нормальная
# — проверить что возвращается только нормальная
```

### tests/test_routers.py — добавь:

```python
# test_progress_returns_empty_when_no_activities
# — GET /api/activities/progress с пустой БД
# — ожидаем {"weeks": [], "summary": {}}

# test_progress_calculates_ef_correctly
# — вставить 2 активности в одну неделю с известными avg_pace и avg_hrm
# — проверить что ef в ответе правильный
# — например: avg_pace=360 (6:00/км), avg_hrm=150
# — EF = (1000/360*60) / 150 = 166.67 / 150 = 1.111
```

---

## Важное замечание по роутеру

В `portal/routers/activities.py` эндпоинт `/api/activities/progress` должен быть
объявлен ДО эндпоинта `/api/activities/{activity_id}`, иначе FastAPI будет
интерпретировать `progress` как `activity_id`.

---

## Финальные шаги

```bash
cd running-portal
python -m pytest tests/ -v
uvicorn portal.main:app --port 8001 --reload
```

Сообщи:
1. Результат pytest
2. Открой http://localhost:8001 — появилась ли карточка "Прогресс формы"?
3. Какие значения EF показывает (начало / сейчас / пик)?
