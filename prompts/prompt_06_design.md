# Промпт #6 — Рефакторинг дизайна: светлый сланец

## Контекст

Проект `running-portal`. Фазы 1–5 завершены.
Задача: полностью заменить визуальный стиль на утверждённый дизайн — светлый сланец.

## Цветовая система

```css
:root {
  /* Фоны */
  --bg:       #f2f4f0;   /* страница */
  --bg-card:  #ffffff;   /* карточки */
  --bg-hover: #fafcfa;   /* hover строки */

  /* Акцент */
  --accent:        #3a5040;  /* основной — тёмный серо-зелёный */
  --accent-light:  #e8f0ea;  /* светлый фон акцента */
  --accent-border: #ccd8d0;  /* бордер карточек */

  /* Текст */
  --text:    #22302a;   /* основной */
  --text2:   #607068;   /* вторичный */
  --text3:   #90a89a;   /* третичный / лейблы */
  --text4:   #a8c0b0;   /* совсем приглушённый */

  /* Разделители */
  --border:       #d8e0da;
  --border-card:  #ccd8d0;
  --border-inner: #e8f0ea;

  /* Состояния пульса */
  --hr-green: #2a4a20;
  --hr-amber: #7a4010;
  --hr-red:   #8a1a1a;

  /* Алерты */
  --alert-ok-bg:     #f0f8ec;
  --alert-ok-border: #b8d4a8;
  --alert-ok-text:   #3a5040;
  --alert-warn-bg:     #fdf4e4;
  --alert-warn-border: #e0c080;
  --alert-warn-text:   #7a4010;
  --alert-danger-bg:     #fdf0f0;
  --alert-danger-border: #e0a8a8;
  --alert-danger-text:   #8a1a1a;

  /* Геометрия */
  --radius:    6px;
  --radius-lg: 8px;
  --radius-xl: 10px;
}
```

---

## Задача 1 — static/style.css

Полностью перепиши файл. Структура:

### Reset и base

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  font-size: 14px;
  line-height: 1.5;
}
a { color: inherit; text-decoration: none; }
button { cursor: pointer; font-family: inherit; }
```

### Nav

```css
nav {
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  padding: 0 24px;
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
}
.nav-logo {
  font-size: 10px;
  letter-spacing: .16em;
  color: var(--text);
  text-transform: uppercase;
  font-weight: 500;
}
.nav-right { display: flex; align-items: center; gap: 16px; }
.nav-link { font-size: 12px; color: var(--text3); }
.nav-link:hover { color: var(--text); }
.nav-btn {
  font-size: 11px;
  color: var(--bg-card);
  background: var(--accent);
  border: none;
  padding: 5px 14px;
  border-radius: var(--radius);
}
.nav-btn:hover { opacity: .85; }
#sync-status { font-size: 11px; color: var(--text3); }
```

### Page layout

```css
.page { max-width: 720px; margin: 0 auto; padding: 24px 20px; }
.section-label {
  font-size: 9px;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: .12em;
  font-weight: 500;
  margin-bottom: 10px;
}
```

### Today card (главная карточка "ответ на сегодня")

```css
.today-card {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  border: 0.5px solid var(--border-card);
  border-left: 3px solid var(--accent);
  padding: 18px 20px;
  margin-bottom: 16px;
}
.today-card--loading { opacity: .7; }
.today-card--run     { border-left-color: var(--accent); }
.today-card--run_easy { border-left-color: #c8a020; }
.today-card--rest    { border-left-color: #a04040; }

.today-eyebrow {
  font-size: 9px;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: .12em;
  margin-bottom: 8px;
}
.today-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.today-status {
  font-size: 26px;
  font-weight: 500;
  color: var(--accent);
  line-height: 1.1;
  margin-bottom: 6px;
}
.today-card--run_easy .today-status { color: #8a5010; }
.today-card--rest .today-status     { color: #8a1a1a; }

.today-message {
  font-size: 12px;
  color: var(--text2);
  line-height: 1.65;
  max-width: 440px;
}
.today-refresh {
  font-size: 11px;
  color: var(--text3);
  border: 0.5px solid var(--border-card);
  background: transparent;
  padding: 4px 10px;
  border-radius: var(--radius);
  white-space: nowrap;
  flex-shrink: 0;
}
.today-refresh:hover { background: var(--bg); }
.today-meta {
  display: flex;
  gap: 24px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border-inner);
}
.today-stat-label {
  font-size: 9px;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: .06em;
  margin-bottom: 2px;
}
.today-stat-value {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
}
```

### Alerts

```css
.alert {
  border-radius: var(--radius);
  padding: 9px 14px;
  margin-bottom: 16px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0.5px solid;
}
.alert-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.alert-success {
  background: var(--alert-ok-bg);
  border-color: var(--alert-ok-border);
  color: var(--alert-ok-text);
}
.alert-success .alert-dot { background: var(--accent); }
.alert-warning {
  background: var(--alert-warn-bg);
  border-color: var(--alert-warn-border);
  color: var(--alert-warn-text);
}
.alert-warning .alert-dot { background: #c8a020; }
.alert-danger {
  background: var(--alert-danger-bg);
  border-color: var(--alert-danger-border);
  color: var(--alert-danger-text);
}
.alert-danger .alert-dot { background: #a04040; }
```

### Metrics grid

```css
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 20px;
}
@media (max-width: 480px) { .metrics { grid-template-columns: repeat(2, 1fr); } }
.metric {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  border: 0.5px solid var(--border-card);
  padding: 12px 14px;
}
.metric-label {
  font-size: 9px;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: .06em;
  margin-bottom: 5px;
}
.metric-value {
  font-size: 22px;
  font-weight: 500;
  color: var(--text);
  line-height: 1.1;
}
.metric-sub {
  font-size: 9px;
  color: var(--text4);
  margin-top: 3px;
}
```

### Card (общий)

```css
.card {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  border: 0.5px solid var(--border-card);
  padding: 16px 20px;
  margin-bottom: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.card-title { font-size: 13px; font-weight: 500; color: var(--text); }
.card-hint  { font-size: 10px; color: var(--text3); }
```

### Chart

```css
.chart-wrap { position: relative; width: 100%; height: 100px; margin-bottom: 8px; }
.chart-labels {
  display: flex;
  justify-content: space-between;
  font-size: 8px;
  color: var(--text4);
}
```

### Table

```css
.run-table { width: 100%; border-collapse: collapse; }
.run-table th {
  font-size: 9px;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: .06em;
  font-weight: 500;
  padding: 0 0 10px;
  text-align: left;
  border-bottom: 1px solid var(--border-inner);
}
.run-table td {
  font-size: 12px;
  color: var(--text);
  padding: 9px 0;
  border-bottom: 0.5px solid var(--border-inner);
}
.run-table tr:last-child td { border-bottom: none; }
.run-table tbody tr:hover td { background: var(--bg-hover); }
.run-table a { color: var(--accent); font-weight: 500; }
.hr-green { color: var(--hr-green); font-weight: 500; }
.hr-amber { color: var(--hr-amber); font-weight: 500; }
.hr-red   { color: var(--hr-red);   font-weight: 500; }
```

### Buttons

```css
.btn {
  font-size: 12px;
  padding: 7px 16px;
  border-radius: var(--radius);
  border: 0.5px solid var(--border-card);
  background: transparent;
  color: var(--text);
}
.btn:hover { background: var(--bg); }
.btn-primary {
  background: var(--accent);
  color: var(--bg-card);
  border-color: transparent;
}
.btn-primary:hover { opacity: .85; background: var(--accent); }
.btn-secondary { color: var(--text3); }
```

### Пульсовые зоны (detail.html)

```css
.zones { display: flex; flex-direction: column; gap: 8px; margin-bottom: 4px; }
.zone-row { display: flex; align-items: center; gap: 10px; }
.zone-name { font-size: 11px; color: var(--text2); min-width: 100px; }
.zone-bar-wrap { flex: 1; height: 8px; background: var(--bg); border-radius: 4px; overflow: hidden; }
.zone-bar { height: 100%; border-radius: 4px; }
.zone-pct { font-size: 11px; color: var(--text3); min-width: 32px; text-align: right; }
```

### AI bubble

```css
.ai-bubble {
  background: var(--bg);
  border-radius: var(--radius);
  padding: 14px 16px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text);
  white-space: pre-wrap;
  border-left: 3px solid var(--accent);
  margin-bottom: 12px;
}
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  background: var(--accent-light);
  color: var(--accent);
  border: 0.5px solid var(--border-card);
  margin-left: 8px;
  vertical-align: middle;
}
.spinner {
  display: inline-block;
  width: 13px; height: 13px;
  border: 2px solid var(--border-card);
  border-top-color: var(--text3);
  border-radius: 50%;
  animation: spin .7s linear infinite;
  vertical-align: middle;
  margin-right: 6px;
}
@keyframes spin { to { transform: rotate(360deg); } }
```

---

## Задача 2 — templates/base.html

Обнови структуру:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Running Portal{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
</head>
<body>
<nav>
  <span class="nav-logo">Running Portal</span>
  <div class="nav-right">
    <a href="/" class="nav-link">Дашборд</a>
    <button class="nav-btn" onclick="triggerSync()">↻ Синхронизировать</button>
    <span id="sync-status"></span>
  </div>
</nav>
<main>
  {% block content %}{% endblock %}
</main>
<script src="/static/app.js"></script>
{% block scripts %}{% endblock %}
</body>
</html>
```

---

## Задача 3 — templates/index.html

Обнови разметку под новые классы. Структура страницы:

```html
{% extends "base.html" %}
{% block content %}
<div class="page">

  <!-- Today card -->
  <div id="today-card" class="today-card today-card--loading">
    <div class="today-eyebrow">ответ на сегодня</div>
    <div class="today-row">
      <div>
        <div class="today-status" id="today-status">Загрузка...</div>
        <div class="today-message" id="today-message"></div>
      </div>
      <button class="today-refresh" onclick="refreshRecommendation()">обновить</button>
    </div>
    <div class="today-meta" id="today-meta"></div>
  </div>

  <!-- Alerts -->
  <div id="alerts-section"></div>

  <!-- Metrics -->
  <div class="section-label">Ключевые метрики</div>
  <div class="metrics" id="metrics-grid">
    <!-- JS заполняет -->
  </div>

  <!-- Chart -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">Дистанции</span>
      <span class="card-hint">20 последних пробежек</span>
    </div>
    <div class="chart-wrap" style="height:100px">
      <canvas id="dist-chart"></canvas>
    </div>
  </div>

  <!-- Table -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">Последние пробежки</span>
    </div>
    <table class="run-table">
      <thead>
        <tr>
          <th>Дата</th><th>Дистанция</th><th>Пульс</th>
          <th>Темп</th><th>Нагрузка</th><th>Восст.</th>
        </tr>
      </thead>
      <tbody id="run-list"></tbody>
    </table>
  </div>

</div>
{% endblock %}
```

---

## Задача 4 — templates/detail.html

Обнови разметку. Структура:

```html
{% extends "base.html" %}
{% block content %}
<div class="page">

  <div style="margin-bottom:16px">
    <a href="/" style="font-size:12px;color:var(--text3)">← Назад</a>
    <span style="font-size:12px;color:var(--text3);margin:0 8px">·</span>
    <span style="font-size:13px;font-weight:500;color:var(--text)">
      Пробежка {{ activity.date[:10] }}
    </span>
    <span style="font-size:13px;color:var(--accent);margin-left:8px">
      {{ activity.distance_km }} км
    </span>
  </div>

  <!-- Metrics 6 карточек -->
  <div class="metrics" style="grid-template-columns:repeat(3,1fr);margin-bottom:16px">
    <!-- пульс, темп, каденс, длина шага, нагрузка, восстановление -->
  </div>

  <!-- Пульсовые зоны -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">Пульсовые зоны</span>
    </div>
    <div class="zones" id="zones-section"></div>
  </div>

  <!-- График -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">Пульс и скорость по времени</span>
      <span class="card-hint" id="detail-hint"></span>
    </div>
    <div class="chart-wrap" style="height:180px">
      <canvas id="hr-chart"></canvas>
    </div>
    <button class="btn" id="load-detail-btn" onclick="loadDetail()" style="margin-top:10px">
      Загрузить детали
    </button>
  </div>

  <!-- AI тренер -->
  <div class="card" id="ai-section">
    <div class="card-header">
      <span class="card-title">AI тренер</span>
      <span class="card-hint">Персональный анализ</span>
    </div>
    <input type="hidden" id="activity-id" value="{{ activity.activity_id }}">
    <div id="ai-result" class="ai-bubble" style="display:none"></div>
    <div id="ai-loading" style="display:none">
      <span class="spinner"></span> Тренер анализирует...
    </div>
    <div id="ai-controls">
      <button class="btn btn-primary" onclick="getAnalysis()">Получить анализ</button>
      <button class="btn" onclick="getAnalysis(true)" id="refresh-btn" style="display:none">Обновить</button>
      <span id="ai-cached-badge" class="badge" style="display:none">из кэша</span>
    </div>
  </div>

</div>
{% endblock %}
```

---

## Задача 5 — Chart.js цвета

В `static/app.js` обнови цвета графиков:

```javascript
// Дашборд — бар чарт дистанций
backgroundColor: runs.map((r, i) =>
  i === runs.length - 1 ? '#3a5040' : 'rgba(58,80,64,0.25)'
)

// Detail — пульс
borderColor: '#3a5040'

// Detail — скорость
borderColor: 'rgba(58,80,64,0.4)'
borderDash: [4, 2]

// Зоны (цвета баров)
// жиросжигание: #85b7eb
// аэробная:     #3a5040
// анаэробная:   #c8a020
// экстремальная: #a04040
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
2. Скриншот или описание http://localhost:8001
3. Скриншот или описание детальной страницы любой пробежки
4. Любые ошибки в консоли браузера
