# Промпт #9b — Линии равного EF на scatter plot

## Контекст

Проект `running-portal`. Scatter plot уже реализован (промпт #9).
Задача: добавить пунктирные линии равного EF поверх точек.

---

## Задача 1 — static/app.js

В функции `renderScatterChart(scatterData)` добавь datasets с линиями EF
**перед** scatter datasets (чтобы линии были под точками).

### Линии EF

```javascript
const EF_LINES = [
  { ef: 0.80, color: '#85b7eb', label: 'EF 0.80' },
  { ef: 0.90, color: '#639922', label: 'EF 0.90' },
  { ef: 1.00, color: '#3a5040', label: 'EF 1.00' },
  { ef: 1.10, color: '#c8a020', label: 'EF 1.10' },
  { ef: 1.20, color: '#a04040', label: 'EF 1.20' },
];

// Диапазон темпа для линий: от 4:30 до 10:00 мин/км
const paceRange = [];
for (let p = 270; p <= 600; p += 5) paceRange.push(p);

const efLineDatasets = EF_LINES.map(({ ef, color, label }) => ({
  label,
  data: paceRange
    .map(p => ({
      x: p / 60,                        // мин/км дробное
      y: (1000 / p * 60) / ef,          // hrm = speed_mpm / ef
    }))
    .filter(pt => pt.y >= 95 && pt.y <= 205),
  borderColor: color,
  borderDash: [5, 3],
  borderWidth: 1.5,
  pointRadius: 0,
  type: 'line',
  fill: false,
  tension: 0,
  order: 2,   // рисуется под точками
}));
```

### Добавь подписи к линиям

В конце каждой линии нарисуй подпись через Chart.js plugin или просто
добавь в легенду.

Обнови легенду `scatter-legend` чтобы она показывала и периоды и линии EF:

```javascript
// Периоды
const periodItems = sortedMonths.map((month, i) => `
  <span style="display:flex;align-items:center;gap:4px">
    <span style="width:9px;height:9px;border-radius:50%;
                 background:${PERIOD_COLORS[i % PERIOD_COLORS.length]};
                 display:inline-block"></span>
    ${monthGroups[month].label}
  </span>
`).join('');

// Линии EF
const efItems = EF_LINES.map(({ ef, color }) => `
  <span style="display:flex;align-items:center;gap:4px">
    <span style="width:16px;height:0;border-top:1.5px dashed ${color};
                 display:inline-block;vertical-align:middle"></span>
    EF ${ef.toFixed(2)}
  </span>
`).join('');

legendEl.innerHTML = `
  <span style="font-size:10px;color:var(--text3);text-transform:uppercase;
               letter-spacing:.06em;margin-right:4px">Периоды:</span>
  ${periodItems}
  <span style="margin-left:8px;font-size:10px;color:var(--text3);
               text-transform:uppercase;letter-spacing:.06em;margin-right:4px">EF:</span>
  ${efItems}
`;
```

### Итоговый порядок datasets в Chart.js

```javascript
scatterChart = new Chart(canvas, {
  type: 'scatter',
  data: {
    datasets: [
      ...efLineDatasets,   // сначала линии (под точками)
      ...scatterDatasets,  // потом точки (поверх)
    ]
  },
  options: {
    // tooltip фильтруем — показываем только для scatter точек
    plugins: {
      tooltip: {
        filter: ctx => ctx.dataset.type !== 'line',
        // ... остальное как было
      }
    }
    // ... остальные опции как были
  }
});
```

---

## Финальные шаги

```bash
uvicorn portal.main:app --port 8001 --reload
```

Сообщи:
1. Открой scatter plot — видны ли пунктирные линии EF?
2. Легенда показывает и периоды и линии EF?
3. Tooltip на точках работает (не показывает tooltip для линий)?
