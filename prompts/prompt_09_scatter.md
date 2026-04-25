# Промпт #9 — Scatter plot "Темп vs Пульс" в карточке прогресса

## Контекст

Проект `running-portal`. Код актуальный — прочитан из репозитория.

Задача: в карточке "Прогресс формы" на главной странице добавить кнопку
"Scatter plot" которая показывает/скрывает график "Темп vs Пульс" по всем
пробежкам. Точки раскрашены по периодам (месяцам).

---

## Задача 1 — portal/routers/activities.py

В эндпоинт `GET /api/activities/progress` добавь поле `scatter` в ответ —
данные для scatter plot:

```python
# Добавь в конец функции get_progress(), перед return:

scatter = []
for a in activities:
    if not a.get("avg_pace") or not a.get("avg_hrm"):
        continue
    try:
        dt = datetime.fromisoformat(a["date"].replace("Z", "+00:00"))
    except Exception:
        continue
    # Темп в мин/км для отображения (дробное число)
    pace_min_km = round(a["avg_pace"] / 60, 3)
    scatter.append({
        "date": a["date"][:10],
        "pace_sec": a["avg_pace"],           # секунды/км для расчётов
        "pace_min": pace_min_km,             # мин/км для отображения
        "hrm": a["avg_hrm"],
        "distance_km": a.get("distance_km"),
        "month": dt.strftime("%Y-%m"),       # для группировки по цвету
        "month_label": dt.strftime("%m.%Y"), # для легенды
    })

# В return добавь scatter:
return {
    "weeks": weeks_data,
    "summary": { ... },  # как было
    "scatter": scatter,
}
```

---

## Задача 2 — templates/index.html

В карточке `progress-card` добавь кнопку и контейнер для scatter plot
после основного графика EF и заметки:

```html
<div style="margin-top:12px">
  <button class="btn btn-secondary" id="scatter-toggle-btn"
          onclick="toggleScatterPlot()">
    Scatter plot ↓
  </button>
</div>

<div id="scatter-section" style="display:none;margin-top:16px">
  <div style="font-size:11px;color:var(--text3);margin-bottom:8px">
    Каждая точка — одна пробежка. Цвет — период. Левый нижний угол = высокий EF.
  </div>
  <div id="scatter-legend" style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:10px;font-size:11px;color:var(--text3)"></div>
  <div style="position:relative;width:100%;height:280px">
    <canvas id="scatter-chart" role="img"
            aria-label="Scatter plot темп vs пульс по всем пробежкам">
      Scatter plot темп vs пульс
    </canvas>
  </div>
</div>
```

---

## Задача 3 — static/app.js

### Добавь переменную вверху файла:
```javascript
let scatterChart = null;
let scatterDataCache = null;
```

### Добавь функцию `toggleScatterPlot()`

```javascript
async function toggleScatterPlot() {
  const section = document.getElementById("scatter-section");
  const btn = document.getElementById("scatter-toggle-btn");
  if (!section || !btn) return;

  const isVisible = section.style.display !== "none";

  if (isVisible) {
    section.style.display = "none";
    btn.textContent = "Scatter plot ↓";
    return;
  }

  section.style.display = "block";
  btn.textContent = "Scatter plot ↑";

  // Данные уже загружены при инициализации — используем кэш
  if (scatterDataCache) {
    renderScatterChart(scatterDataCache);
  }
}
```

### В функцию `renderProgressCard()` добавь сохранение данных в кэш:

После получения `data` из `/api/activities/progress` добавь:
```javascript
if (data.scatter) {
  scatterDataCache = data.scatter;
}
```

### Добавь функцию `renderScatterChart(scatterData)`

```javascript
function renderScatterChart(scatterData) {
  const canvas = document.getElementById("scatter-chart");
  if (!canvas || !window.Chart) return;
  if (scatterChart) scatterChart.destroy();

  // Группируем по месяцам
  const monthGroups = {};
  for (const point of scatterData) {
    if (!monthGroups[point.month]) {
      monthGroups[point.month] = {
        label: point.month_label,
        data: [],
      };
    }
    monthGroups[point.month].data.push({
      x: point.pace_min,   // мин/км (дробное)
      y: point.hrm,
      date: point.date,
      distance: point.distance_km,
    });
  }

  // Цвета по периодам — от старых (светлее) к новым (темнее)
  const PERIOD_COLORS = [
    "#c0dda0", "#8fc46a", "#639922", "#3B6D11",
    "#27500A", "#3a5040", "#1e2e18",
  ];

  const sortedMonths = Object.keys(monthGroups).sort();
  const datasets = sortedMonths.map((month, i) => ({
    label: monthGroups[month].label,
    data: monthGroups[month].data,
    backgroundColor: PERIOD_COLORS[i % PERIOD_COLORS.length] + "cc",
    borderColor: PERIOD_COLORS[i % PERIOD_COLORS.length],
    borderWidth: 1,
    pointRadius: 6,
    pointHoverRadius: 8,
  }));

  // Легенда
  const legendEl = document.getElementById("scatter-legend");
  if (legendEl) {
    legendEl.innerHTML = sortedMonths.map((month, i) => `
      <span style="display:flex;align-items:center;gap:5px">
        <span style="width:10px;height:10px;border-radius:50%;
                     background:${PERIOD_COLORS[i % PERIOD_COLORS.length]};
                     display:inline-block"></span>
        ${monthGroups[month].label}
      </span>
    `).join("");
  }

  // Диапазон осей
  const paces = scatterData.map(d => d.pace_min);
  const hrms = scatterData.map(d => d.hrm);
  const paceMin = Math.floor(Math.min(...paces) * 10) / 10 - 0.3;
  const paceMax = Math.ceil(Math.max(...paces) * 10) / 10 + 0.3;
  const hrmMin = Math.min(...hrms) - 10;
  const hrmMax = Math.max(...hrms) + 10;

  scatterChart = new Chart(canvas, {
    type: "scatter",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              const d = ctx.raw;
              const paceStr = formatPace(Math.round(d.x * 60));
              return [
                `${ctx.raw.date}`,
                `Темп: ${paceStr}/км`,
                `Пульс: ${d.y} уд/мин`,
                `Дистанция: ${d.distance?.toFixed(2) ?? "—"} км`,
              ];
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Темп (мин/км)", font: { size: 11 }, color: "#90a89a" },
          min: paceMin,
          max: paceMax,
          ticks: {
            font: { size: 10 },
            color: "#90a89a",
            callback: v => formatPace(Math.round(v * 60)),
          },
          grid: { color: "rgba(128,128,128,0.08)" },
        },
        y: {
          title: { display: true, text: "Пульс (уд/мин)", font: { size: 11 }, color: "#90a89a" },
          min: hrmMin,
          max: hrmMax,
          ticks: { font: { size: 10 }, color: "#90a89a" },
          grid: { color: "rgba(128,128,128,0.08)" },
        },
      },
    },
  });
}
```

---

## Задача 4 — static/style.css

Добавь стиль для кнопки переключения:

```css
#scatter-toggle-btn {
  font-size: 12px;
  padding: 5px 12px;
}
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
2. Открой главную страницу — видна ли кнопка "Scatter plot ↓" в карточке прогресса?
3. Нажми кнопку — появился ли график?
4. Сколько точек на графике и сколько периодов в легенде?
