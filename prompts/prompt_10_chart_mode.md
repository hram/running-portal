# Промпт #10 — Переключатель "по времени / по дистанции" на графике детальной пробежки

## Контекст

Проект `running-portal`. Код актуальный — прочитан из репозитория.

На странице детальной пробежки есть график "Пульс и скорость по времени".
Ось X сейчас — время в минутах (из `samples[i].start_time - samples[0].start_time`).

Задача: добавить переключатель который меняет ось X с "времени" на "дистанцию в метрах".
Данные для дистанции берутся из `track_points[i].distance_meters`.

---

## Как устроены данные

В `details` из `/api/activities/{id}`:
- `samples` — посекундные данные: `start_time` (unix timestamp), `heart_rate`, `speed_mps`
- `track_points` — GPS точки: `timestamp`, `distance_meters`, `speed_mps`, `heart_rate`

Для режима "по дистанции" используем `track_points` — там есть `distance_meters`.
Для режима "по времени" используем `samples` как сейчас.

Важно: `track_points` может быть пустым если детали не загружены или GPS не было.
В этом случае кнопку "по дистанции" показывать задизабленной.

---

## Задача 1 — templates/detail.html

В карточке "Пульс и скорость по времени" добавь переключатель в `card-header`:

```html
<div class="card-header">
  <span class="card-title" id="detail-chart-title">Пульс и скорость по времени</span>
  <div style="display:flex;align-items:center;gap:10px">
    <div class="chart-mode-toggle" id="chart-mode-toggle" style="display:none">
      <button class="toggle-btn active" id="btn-by-time"
              onclick="switchChartMode('time')">по времени</button>
      <button class="toggle-btn" id="btn-by-dist"
              onclick="switchChartMode('distance')">по дистанции</button>
    </div>
    <div class="detail-chart-legend">
      <!-- легенда как была -->
    </div>
  </div>
</div>
```

---

## Задача 2 — static/style.css

```css
.chart-mode-toggle {
  display: flex;
  border: 0.5px solid var(--border-card);
  border-radius: var(--radius);
  overflow: hidden;
}

.toggle-btn {
  font-size: 11px;
  padding: 4px 10px;
  border: none;
  background: transparent;
  color: var(--text3);
  cursor: pointer;
  border-radius: 0;
}

.toggle-btn:hover { background: var(--bg); color: var(--text); }

.toggle-btn.active {
  background: var(--accent);
  color: var(--bg-card);
}
```

---

## Задача 3 — static/app.js

### Добавь переменную:
```javascript
let currentChartMode = 'time'; // 'time' | 'distance'
```

### Обнови `renderDetailChart(details)`

Текущая функция строит график только по времени.
Переработай её чтобы поддерживала оба режима:

```javascript
function renderDetailChart(details, mode = 'time') {
  const canvas = document.getElementById("hr-chart");
  if (!canvas || !window.Chart) return;
  if (detailChart) detailChart.destroy();

  const samples = details.samples || [];
  const trackPoints = details.track_points || [];

  if (!samples.length) {
    setDetailStatus("Нет данных для графика");
    return;
  }

  // Показываем переключатель
  const toggle = document.getElementById("chart-mode-toggle");
  const btnDist = document.getElementById("btn-by-dist");
  if (toggle) toggle.style.display = "flex";
  if (btnDist) {
    // дистанция доступна только если есть track_points с distance_meters
    const hasDistance = trackPoints.some(p => p.distance_meters != null);
    btnDist.disabled = !hasDistance;
    if (!hasDistance) btnDist.title = "GPS данные недоступны";
  }

  // Обновляем заголовок
  const title = document.getElementById("detail-chart-title");
  if (title) {
    title.textContent = mode === 'time'
      ? "Пульс и скорость по времени"
      : "Пульс и скорость по дистанции";
  }

  // Обновляем активную кнопку
  document.getElementById("btn-by-time")?.classList.toggle("active", mode === 'time');
  document.getElementById("btn-by-dist")?.classList.toggle("active", mode === 'distance');

  let labels, heartRate, speed, xLabel;

  if (mode === 'distance' && trackPoints.length) {
    // Режим по дистанции — используем track_points
    const validPoints = trackPoints.filter(p => p.distance_meters != null);
    labels = validPoints.map(p => Math.round(p.distance_meters));
    heartRate = validPoints.map(p => p.heart_rate || null);
    speed = validPoints.map(p => p.speed_mps ? Number((p.speed_mps * 3.6).toFixed(2)) : null);
    xLabel = "м";
  } else {
    // Режим по времени — используем samples (как было)
    const baseTime = samples[0].start_time || samples[0].timestamp || 0;
    labels = samples.map(s => {
      const t = s.start_time || s.timestamp || baseTime;
      return Math.max(0, Math.round((t - baseTime) / 60));
    });
    heartRate = samples.map(s => s.heart_rate);
    speed = trackPoints.length
      ? trackPoints.slice(0, labels.length).map(p =>
          p.speed_mps ? Number((p.speed_mps * 3.6).toFixed(2)) : null)
      : samples.map(s =>
          s.speed_mps ? Number((s.speed_mps * 3.6).toFixed(2)) : null);
    xLabel = "м";
  }

  // Зоны пульса из настроек
  const zoneLowValue = Number(currentSettings?.target_hr_zone_low ?? 140);
  const zoneHighValue = Number(currentSettings?.target_hr_zone_high ?? 160);
  const zoneLow = labels.map(() => zoneLowValue);
  const zoneHigh = labels.map(() => zoneHighValue);

  // EF по ходу тренировки (как уже реализовано)
  // ... оставь существующую логику EF без изменений

  // Обновляем подписи оси X
  const labelsRoot = document.getElementById("detail-chart-labels");
  if (labelsRoot) {
    const maxVal = labels[labels.length - 1] || 0;
    const anchors = [0, 0.25, 0.5, 0.75, 1].map(f => Math.round(maxVal * f));
    const unique = [...new Set(anchors)];
    if (mode === 'distance') {
      labelsRoot.innerHTML = unique.map(v =>
        `<span>${v >= 1000 ? (v/1000).toFixed(1)+'км' : v+'м'}</span>`
      ).join('');
    } else {
      labelsRoot.innerHTML = unique.map(v => `<span>${v} м</span>`).join('');
    }
  }

  // Строим chart — та же конфигурация что была, только labels другие
  detailChart = new Chart(canvas, {
    // ... вставь существующую конфигурацию Chart.js
    // единственное изменение — в scale x убери callback который форматировал минуты
    // и замени на:
    scales: {
      x: {
        ticks: { display: false },
        grid: { color: "rgba(255,255,255,0.05)" },
      },
      // y и y1 как были
    }
  });
}
```

### Добавь функцию `switchChartMode(mode)`:

```javascript
function switchChartMode(mode) {
  if (!currentDetails) return;
  currentChartMode = mode;
  renderDetailChart(currentDetails, mode);
}
```

### В `initDetailPage()` обнови вызов `renderDetailChart`:

```javascript
// Было:
renderDetailChart(currentDetails);

// Стало:
renderDetailChart(currentDetails, currentChartMode);
```

### В `loadActivityDetails()` тоже обнови:

```javascript
renderDetailChart(currentDetails, currentChartMode);
```

---

## Важные детали

1. `track_points` в деталях могут не иметь `distance_meters` — это нормально,
   кнопка просто будет задизабленной.

2. Если `track_points` пустые — режим по дистанции недоступен совсем.

3. При переключении режима график перестраивается с теми же данными,
   просто другая ось X. Не нужно делать новый запрос к API.

4. EF мини-график под основным — он по времени всегда (не переключать),
   так как EF привязан к секундам из `samples`.

---

## Финальные шаги

```bash
uvicorn portal.main:app --port 8001 --reload
```

Сообщи:
1. Открой детальную страницу пробежки у которой есть загруженные детали
2. Виден ли переключатель "по времени / по дистанции"?
3. Работает ли переключение?
4. Как выглядит ось X в режиме "по дистанции" — в метрах или километрах?
