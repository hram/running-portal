# Промпт #3 — Фронтенд: дашборд и страница детальной пробежки

## Контекст

Проект `running-portal`. Фазы 1 и 2 завершены.
- БД содержит 55 активностей
- API работает: `/api/activities`, `/api/sync`, `/api/auth/status`
- Шаблонизатор: Jinja2, файлы в `templates/`
- Стили и JS: `static/style.css`, `static/app.js`

Стек фронтенда: Jinja2 + vanilla JS + Chart.js (CDN). Никаких фреймворков.

---

## Задача 1 — templates/base.html

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
    <a href="/" class="nav-logo">🏃 Running Portal</a>
    <div class="nav-links">
      <a href="/">Дашборд</a>
      <button id="sync-btn" onclick="triggerSync()">Синхронизировать</button>
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

## Задача 2 — templates/index.html (дашборд)

Расширяет base.html. Структура страницы:

### Секция 1 — Метрики (4 карточки)

Данные подгружаются через JS из `/api/activities?limit=100`.

| Карточка | Значение |
|---|---|
| Последняя пробежка | дата + дистанция |
| Всего пробежек | count |
| Средний пульс | avg за последние 7 пробежек |
| Личный рекорд | max distance_km |

### Секция 2 — Алерты

JS анализирует последние данные и показывает цветные плашки:
- 🔴 если последний пульс > 185
- 🟡 если нагрузка выросла > 20% неделя к неделе
- 🟡 если с последней пробежки > 7 дней
- 🟢 если всё в норме

### Секция 3 — График дистанций

Chart.js bar chart. Последние 20 пробежек. X — дата, Y — distance_km.

### Секция 4 — Таблица последних пробежек

Последние 20 пробежек. Колонки:
- Дата (ссылка на `/activity/{activity_id}`)
- Дистанция
- Пульс (цветной: зелёный ≤160, жёлтый 161–180, красный >180)
- Темп (форматировать из секунд: `Math.floor(p/60) + ':' + (p%60).toString().padStart(2,'0')`)
- Нагрузка
- Восстановление (ч)

---

## Задача 3 — templates/detail.html (детальная пробежка)

Расширяет base.html.

### Секция 1 — Заголовок

```
← Назад  |  Пробежка 24.04.2026  |  3.17 км
```

### Секция 2 — Метрики (6 карточек)

Пульс, Темп, Каденс, Длина шага, Нагрузка, Восстановление.

### Секция 3 — Пульсовые зоны

4 цветных бара с процентами:
- Жиросжигание (синий) — `hrm_fat_burning_duration`
- Аэробная (зелёный) — `hrm_aerobic_duration`
- Анаэробная (жёлтый) — `hrm_anaerobic_duration`
- Экстремальная (красный) — `hrm_extreme_duration`

### Секция 4 — График пульса по времени

Загружается через `GET /api/activities/{id}/detail`.

Если детали ещё не загружены — показывает кнопку "Загрузить детали" которая вызывает `/api/activities/{id}/detail` и перерисовывает график.

Chart.js line chart:
- X — время в минутах (из `samples[i].start_time - samples[0].start_time`)
- Y левая — пульс (красный)
- Y правая — скорость км/ч из `track_points[i].speed_mps * 3.6` (синий пунктир)
- Горизонтальная зелёная полоса: зона 140–160 уд/мин

### Секция 5 — AI тренер

Кнопка "Получить анализ от тренера".

При клике делает `POST /api/ai/analyze` с `activity_id`.
Показывает результат в блоке под кнопкой.

(Эндпоинт `/api/ai/analyze` реализуем в промпте #4 — пока заглушка возвращает `{"analysis": "AI анализ будет доступен в следующей версии"}`)

---

## Задача 4 — portal/routers/activities.py — добавить эндпоинт страницы

Добавь в `portal/main.py`:

```python
@app.get("/activity/{activity_id}")
async def activity_detail_page(activity_id: str, request: Request):
    # Загружает активность из БД
    # Отдаёт detail.html с activity данными в контексте шаблона
```

---

## Задача 5 — static/style.css

Минималистичный стиль. Цветовая схема — тёмная (как у профессиональных спортивных приложений).

```css
/* Переменные */
:root {
  --bg: #1a1a18;
  --bg2: #242422;
  --bg3: #2e2e2b;
  --text: #e8e6de;
  --text2: #9b9b96;
  --text3: #6b6b67;
  --border: rgba(255,255,255,0.1);
  --blue: #378ADD;
  --green: #639922;
  --amber: #EF9F27;
  --red: #E24B4A;
  --radius: 8px;
  --radius-lg: 12px;
}
```

Компоненты:
- `nav` — тёмная навбар, logo слева, links справа
- `.metrics` — grid 4 колонки, gap 12px
- `.metric-card` — bg2, border-radius, padding
- `.alert` — цветные плашки (danger/warning/success)
- `.run-table` — таблица с hover эффектом
- `.chart-container` — обёртка для Chart.js
- `.zone-bar` — горизонтальные бары для пульсовых зон
- кнопки — минималистичные, outline стиль

---

## Задача 6 — static/app.js

Глобальные функции:

```javascript
// Синк через навбар
async function triggerSync() {
  // показывает "Синхронизация..." в #sync-status
  // POST /api/sync
  // показывает результат: "Добавлено: N" или ошибку
  // обновляет страницу после успешного синка
}

// Форматирование темпа из секунд в MM:SS
function formatPace(seconds) { ... }

// Форматирование даты
function formatDate(isoString) { ... }

// Цвет пульса
function hrColor(hr) {
  if (hr <= 160) return 'var(--green)';
  if (hr <= 180) return 'var(--amber)';
  return 'var(--red)';
}
```

---

## Задача 7 — portal/routers/ai.py (заглушка)

Создай новый файл `portal/routers/ai.py`:

```python
@router.post("/api/ai/analyze")
async def analyze_activity(body: dict):
    return {"analysis": "AI анализ будет доступен в следующей версии"}
```

Подключи роутер в `portal/main.py`.

---

## Финальные шаги

```bash
cd running-portal
python -m pytest tests/ -v
uvicorn portal.main:app --port 8001
```

Сообщи:
1. Результат pytest
2. Открой в браузере `http://localhost:8001` — сделай скриншот или опиши что видно
3. Открой `http://localhost:8001/activity/986361512:outdoor_running:1777007641` — опиши что видно
4. Любые ошибки в консоли браузера или терминале
