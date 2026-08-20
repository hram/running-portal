let dashboardChart = null;
let detailChart = null;
let efChart = null;
let efDetailChart = null;
let scatterChart = null;
let scatterDataCache = null;
let healthStatesCache = [];
let currentActivity = null;
let currentDetails = null;
let currentSettings = null;
let currentChartMode = "time";
let runsPage = 0;
let analysisRequestActive = false;
const RUNS_PAGE_SIZE = 10;
const DASHBOARD_CARD_KEYS = ["today", "metrics", "progress", "goal", "distance", "runs"];

function pickRenderableDetails(details) {
  if (!details) {
    return null;
  }
  if (Array.isArray(details.samples) && details.samples.length) {
    return details;
  }
  if (details.raw_detail && Array.isArray(details.raw_detail.samples) && details.raw_detail.samples.length) {
    return details.raw_detail;
  }
  return details.raw_detail || details;
}

function bindDetailChartModeToggle() {
  const btnTime = document.getElementById("btn-by-time");
  const btnDist = document.getElementById("btn-by-dist");

  if (btnTime && !btnTime.dataset.boundChartMode) {
    btnTime.addEventListener("click", () => switchChartMode("time"));
    btnTime.dataset.boundChartMode = "true";
  }
  if (btnDist && !btnDist.dataset.boundChartMode) {
    btnDist.addEventListener("click", () => switchChartMode("distance"));
    btnDist.dataset.boundChartMode = "true";
  }
}

function buildDistanceSeries(samples, trackPoints, activityDistanceKm) {
  const trackPointsWithDistance = trackPoints.filter((point) => point.distance_meters != null);
  if (trackPointsWithDistance.length) {
    return {
      labels: trackPointsWithDistance.map((point) => Math.round(point.distance_meters)),
      heartRate: trackPointsWithDistance.map((point) => point.heart_rate || null),
      speed: trackPointsWithDistance.map((point) => point.speed_mps ? Number((point.speed_mps * 3.6).toFixed(2)) : null),
    };
  }

  const sampleSteps = samples.map((sample) => Number(sample.distance_meters || 0));
  const totalRawDistance = sampleSteps.reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0);
  const targetMeters = Number(activityDistanceKm || 0) * 1000;
  if (!totalRawDistance || !targetMeters) {
    return null;
  }

  const scale = targetMeters / totalRawDistance;
  let cumulative = 0;
  const labels = sampleSteps.map((value) => {
    cumulative += Number.isFinite(value) ? value : 0;
    return Math.round(cumulative * scale);
  });

  return {
    labels,
    heartRate: samples.map((sample, index) => sample.heart_rate || trackPoints[index]?.heart_rate || null),
    speed: labels.map((_, index) => {
      const pointSpeed = trackPoints[index]?.speed_mps;
      const sampleSpeed = samples[index]?.speed_mps;
      const speedMps = pointSpeed ?? sampleSpeed ?? null;
      return speedMps ? Number((speedMps * 3.6).toFixed(2)) : null;
    }),
  };
}
const STATUS_LABELS = {
  run: "🏃 Бежать",
  run_easy: "🚶 Бежать легко",
  rest: "😴 Отдыхать",
};

const MONTH_NAMES = [
  "",
  "январь",
  "февраль",
  "март",
  "апрель",
  "май",
  "июнь",
  "июль",
  "август",
  "сентябрь",
  "октябрь",
  "ноябрь",
  "декабрь",
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderLimitedMarkdown(value) {
  return escapeHtml(value).replace(/\*\*(.+?)\*\*/gs, "<strong>$1</strong>");
}

function setAiResultText(element, text) {
  if (element) {
    element.innerHTML = renderLimitedMarkdown(text);
  }
}

async function triggerSync() {
  const status = document.getElementById("sync-status");
  const button = document.getElementById("sync-btn");

  if (status) {
    status.textContent = "Синхронизация...";
  }
  if (button) {
    button.disabled = true;
  }

  try {
    const response = await fetch("/api/sync", { method: "POST" });
    const payload = await response.json();
    if (payload.error) {
      if (status) {
        status.textContent = `Ошибка: ${payload.error}`;
      }
      return;
    }

    if (status) {
      status.textContent = `Добавлено: ${payload.added}, обновлено: ${payload.updated}`;
    }
    window.setTimeout(() => window.location.reload(), 900);
  } catch (error) {
    if (status) {
      status.textContent = `Ошибка: ${error.message}`;
    }
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

function formatPace(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) {
    return "—";
  }
  const rounded = Math.max(0, Math.round(Number(seconds)));
  const minutes = Math.floor(rounded / 60);
  const rest = String(rounded % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
}

function formatDate(isoString) {
  if (!isoString) {
    return "—";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(isoString));
}

function formatShortDate(isoString) {
  if (!isoString) {
    return "—";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(isoString));
}

function formatDateTime(isoString) {
  if (!isoString) {
    return "—";
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(isoString))) {
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(new Date(`${isoString}T00:00:00`));
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(isoString));
}

function toDateInputValue(date = new Date()) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function normalizeDateInputValue(value) {
  return value || null;
}

function toDateInputValueFromStored(value) {
  if (!value) {
    return "";
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(value))) {
    return value;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value).slice(0, 10);
  }
  return toDateInputValue(date);
}

function hrColor(hr) {
  if (hr === null || hr === undefined) {
    return "var(--text2)";
  }
  if (hr <= 160) {
    return "var(--green)";
  }
  if (hr <= 180) {
    return "var(--amber)";
  }
  return "var(--red)";
}

function formatHours(hours) {
  if (hours === null || hours === undefined) {
    return "—";
  }
  return `${hours} ч`;
}

function metricCard(label, value, subtext = "") {
  return `
    <article class="metric">
      <p class="metric-label">${label}</p>
      <p class="metric-value">${value}</p>
      <div class="metric-sub">${subtext || "&nbsp;"}</div>
    </article>
  `;
}

async function initDashboard() {
  loadPageSettings();
  applyDashboardCardVisibility();

  if (isDashboardCardEnabled("today")) {
    await loadTodayRecommendation();
  }

  const needsActivities = isDashboardCardEnabled("metrics") || isDashboardCardEnabled("distance");
  let activities = [];
  let healthStates = [];
  if (needsActivities) {
    const [activitiesResponse, healthResponse] = await Promise.all([
      fetch("/api/activities?limit=100"),
      isDashboardCardEnabled("distance") ? fetch("/api/health-states") : Promise.resolve(null),
    ]);
    const payload = await activitiesResponse.json();
    activities = payload.activities || [];
    if (healthResponse) {
      const healthPayload = await healthResponse.json();
      healthStates = healthPayload.states || [];
    }
  }

  if (isDashboardCardEnabled("metrics")) {
    renderDashboardMetrics(activities);
    renderDashboardAlerts(activities);
  }
  if (isDashboardCardEnabled("progress")) {
    await renderProgressCard();
  }
  if (isDashboardCardEnabled("goal")) {
    await renderGoalCard();
  }
  if (isDashboardCardEnabled("distance")) {
    renderDistanceChart(buildDailyDistanceSeries(activities.slice(0, 20).reverse()), healthStates);
  }
  if (isDashboardCardEnabled("runs")) {
    await loadRunsPage(0);
  }
}

function loadPageSettings() {
  const settingsScript = document.getElementById("settings-data");
  if (settingsScript) {
    currentSettings = JSON.parse(settingsScript.textContent);
  }
}

function settingIsEnabled(key, fallback = true) {
  const value = currentSettings?.[key];
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  return value === true || value === "true" || value === "1";
}

function isDashboardCardEnabled(cardName) {
  return settingIsEnabled(`dashboard_card_${cardName}`);
}

function applyDashboardCardVisibility() {
  DASHBOARD_CARD_KEYS.forEach((cardName) => {
    const element = document.querySelector(`[data-dashboard-card="${cardName}"]`);
    if (element) {
      element.hidden = !isDashboardCardEnabled(cardName);
    }
  });
}

async function initHealthPage() {
  await loadHealthStates();
}

async function loadHealthStates() {
  const list = document.getElementById("health-list");
  const status = document.getElementById("health-status");
  if (!list) {
    return;
  }
  if (status) {
    status.textContent = "Загрузка...";
  }

  try {
    const states = await fetchHealthStates();
    if (status) {
      status.textContent = states.length ? "" : "Записей пока нет";
    }
    renderHealthStates(states);
  } catch (error) {
    if (status) {
      status.textContent = `Ошибка: ${error.message}`;
    }
  }
}

async function fetchHealthStates() {
  const response = await fetch("/api/health-states");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "Не удалось загрузить журнал");
  }
  return payload.states || [];
}

function renderHealthStates(states) {
  const list = document.getElementById("health-list");
  if (!list) {
    return;
  }
  healthStatesCache = states;
  if (!states.length) {
    list.innerHTML = "";
    return;
  }
  list.innerHTML = states.map((state) => {
    const isActive = !state.ended_at;
    return `
      <article class="health-item ${isActive ? "health-item--active" : ""}">
        <div class="health-item-main">
          <div class="health-period">
            <span>${formatDateTime(state.started_at)}</span>
            <span class="health-period-separator">-</span>
            <span>${state.ended_at ? formatDateTime(state.ended_at) : "сейчас"}</span>
            ${isActive ? '<span class="goal-badge goal-badge--warn">активно</span>' : ""}
          </div>
          <div class="health-description">${escapeHtml(state.description)}</div>
        </div>
        <div class="health-item-actions">
          <button class="table-action-btn" type="button" onclick="openHealthStateDialogById(${state.id})">Изменить</button>
          <button class="table-action-btn table-action-btn--danger" type="button" onclick="deleteHealthState(${state.id})">Удалить</button>
        </div>
      </article>
    `;
  }).join("");
}

function openHealthStateDialogById(id) {
  const state = healthStatesCache.find((item) => Number(item.id) === Number(id));
  if (state) {
    openHealthStateDialog(state);
  }
}

function openHealthStateDialog(state = null) {
  const modal = document.getElementById("health-modal");
  const title = document.getElementById("health-modal-title");
  const idInput = document.getElementById("health-state-id");
  const description = document.getElementById("health-description");
  const startedAt = document.getElementById("health-started-at");
  const endedAt = document.getElementById("health-ended-at");
  const endedField = document.getElementById("health-ended-field");
  const error = document.getElementById("health-form-error");
  if (!modal || !title || !idInput || !description || !startedAt || !endedAt) {
    return;
  }

  title.textContent = state ? "Редактировать состояние" : "Новое состояние";
  idInput.value = state?.id || "";
  description.value = state?.description || "";
  startedAt.value = state?.started_at ? toDateInputValueFromStored(state.started_at) : toDateInputValue();
  endedAt.value = state?.ended_at ? toDateInputValueFromStored(state.ended_at) : "";
  if (endedField) {
    endedField.hidden = !state;
  }
  if (error) {
    error.style.display = "none";
    error.textContent = "";
  }
  modal.style.display = "flex";
  description.focus();
}

function closeHealthStateDialog(event) {
  const modal = document.getElementById("health-modal");
  if (!modal) {
    return;
  }
  if (event && event.target !== modal) {
    return;
  }
  modal.style.display = "none";
}

async function saveHealthState(event) {
  event.preventDefault();
  const id = document.getElementById("health-state-id")?.value;
  const description = document.getElementById("health-description")?.value.trim();
  const startedAt = document.getElementById("health-started-at")?.value;
  const endedAt = document.getElementById("health-ended-at")?.value;
  const error = document.getElementById("health-form-error");

  if (error) {
    error.style.display = "none";
    error.textContent = "";
  }
  if (!description || !startedAt) {
    if (error) {
      error.textContent = "Заполни описание и дату начала";
      error.style.display = "flex";
    }
    return;
  }

  const payload = {
    description,
    started_at: normalizeDateInputValue(startedAt),
    ended_at: normalizeDateInputValue(endedAt),
  };
  if (payload.ended_at && payload.ended_at < payload.started_at) {
    if (error) {
      error.textContent = "Дата завершения не может быть раньше даты начала";
      error.style.display = "flex";
    }
    return;
  }

  try {
    const response = await fetch(id ? `/api/health-states/${id}` : "/api/health-states", {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "Не удалось сохранить запись");
    }
    closeHealthStateDialog();
    await loadHealthStates();
  } catch (err) {
    if (error) {
      error.textContent = err.message;
      error.style.display = "flex";
    }
  }
}

async function deleteHealthState(id) {
  if (!window.confirm("Удалить запись из журнала?")) {
    return;
  }
  const response = await fetch(`/api/health-states/${id}`, { method: "DELETE" });
  if (!response.ok) {
    const payload = await response.json();
    window.alert(payload.detail || "Не удалось удалить запись");
    return;
  }
  await loadHealthStates();
}

function goalStatusBadge(status) {
  const statusMap = {
    on_track: { cls: "goal-badge--ok", text: "идёт по плану" },
    slightly_behind: { cls: "goal-badge--warn", text: "немного отстаём" },
    behind: { cls: "goal-badge--danger", text: "отстаём" },
    no_goal: { cls: "", text: "цель не установлена" },
  };
  const item = statusMap[status] || statusMap.no_goal;
  return `<span class="goal-badge ${item.cls}">${item.text}</span>`;
}

function progressBar(label, percent, expectedPercent, showExpectedLabel = false) {
  const safePercent = Math.max(0, Math.min(100, Number(percent || 0)));
  const safeExpected = Math.max(0, Math.min(100, Number(expectedPercent || 0)));
  return `
    <div class="goal-progress">
      <div class="goal-progress-row">
        <span>${label}</span>
        <span>${Number(percent || 0).toFixed(1)}%</span>
      </div>
      <div class="goal-progress-track">
        <div class="goal-progress-bar" style="width:${safePercent}%"></div>
        <div class="goal-progress-expected" style="left:${safeExpected}%">
          ${showExpectedLabel ? `<span class="goal-progress-expected-label">план ${Number(expectedPercent || 0).toFixed(1)}%</span>` : ""}
        </div>
      </div>
    </div>
  `;
}

async function renderGoalCard() {
  const card = document.getElementById("goal-card");
  const titleEl = document.getElementById("goal-card-title");
  const badgeEl = document.getElementById("goal-status-badge");
  const content = document.getElementById("goal-content");
  if (!card || !titleEl || !badgeEl || !content) {
    return;
  }

  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  titleEl.textContent = `Цель на ${MONTH_NAMES[month]}`;
  badgeEl.innerHTML = "";
  content.innerHTML = '<div class="card-hint">Загрузка цели...</div>';

  try {
    const res = await fetch(`/api/goals/monthly?year=${year}&month=${month}`);
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Не удалось загрузить цель.");
    }
    badgeEl.innerHTML = goalStatusBadge(data.status);

    if (data.status === "no_goal") {
      content.innerHTML = `
        <div class="goal-empty">
          <div class="goal-empty-title">Установи цель на месяц</div>
          <div class="goal-empty-text">
            AI может предложить реалистичную цель по истории пробежек, или можно ввести цель вручную.
          </div>
          <div class="goal-actions goal-actions--center">
            <button class="btn btn-primary" type="button" onclick="suggestGoal(${year}, ${month})">Спросить AI</button>
            <button class="btn" type="button" onclick="showManualGoalForm(${year}, ${month})">Ввести вручную</button>
          </div>
        </div>
        <div id="goal-suggestion" class="goal-panel" hidden></div>
        <div id="goal-form" class="goal-panel" hidden></div>
      `;
      return;
    }

    const goal = data.goal;
    const progress = data.progress;
    const neededPerRunText = data.runs_remaining > 0
      ? `${Number(data.needed_km_per_run || 0).toFixed(1)} км/пробежку`
      : "цель по пробежкам закрыта";
    content.innerHTML = `
      <div class="goal-metrics">
        ${metricCard("Пройдено", Number(progress.total_km || 0).toFixed(1), `км из ${Number(goal.km_goal).toFixed(1)}`)}
        ${metricCard("Пробежек", String(progress.runs_count || 0), `из ${goal.runs_goal}`)}
        ${metricCard("Осталось", Number(data.km_remaining || 0).toFixed(1), `км · ${data.days_remaining} дней`)}
        ${metricCard("Нужно", neededPerRunText, `${Number(data.needed_km_per_day || 0).toFixed(2)} км/день`)}
      </div>
      ${progressBar("Километры", data.km_pct, data.days_elapsed_pct, true)}
      ${progressBar("Пробежки", data.runs_pct, data.days_elapsed_pct)}
      <div class="goal-note">
        Осталось ${Number(data.km_remaining || 0).toFixed(1)} км и ${data.runs_remaining} пробежек.
        Плановая отметка месяца сейчас ${Number(data.days_elapsed_pct || 0).toFixed(1)}%.
      </div>
      <div class="goal-actions">
        <button class="btn" type="button" onclick="suggestGoal(${year}, ${month})">Скорректировать с AI</button>
        <button class="btn btn-secondary" type="button" onclick="showManualGoalForm(${year}, ${month}, ${Number(goal.km_goal)}, ${Number(goal.runs_goal)})">Изменить вручную</button>
      </div>
      <div id="goal-suggestion" class="goal-panel" hidden></div>
      <div id="goal-form" class="goal-panel" hidden></div>
    `;
  } catch (error) {
    badgeEl.innerHTML = "";
    content.innerHTML = `<div class="alert alert-warning"><span class="alert-dot"></span>${escapeHtml(error.message)}</div>`;
  }
}

async function suggestGoal(year, month) {
  const suggestion = document.getElementById("goal-suggestion");
  const form = document.getElementById("goal-form");
  if (!suggestion) {
    return;
  }
  if (form) {
    form.hidden = true;
  }
  suggestion.hidden = false;
  suggestion.innerHTML = '<div class="ai-bubble"><span class="spinner"></span>AI анализирует историю...</div>';

  try {
    const res = await fetch(`/api/goals/monthly/suggest?year=${year}&month=${month}`);
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Не удалось получить предложение.");
    }
    suggestion.innerHTML = `
      <div class="ai-bubble">${escapeHtml(data.message || "Анализ получен.")}</div>
      <div class="goal-variants">
        ${goalVariant("Консервативная", data.conservative?.km_goal, data.conservative?.runs_goal)}
        ${goalVariant("Рекомендуется", data.km_goal, data.runs_goal, true)}
        ${goalVariant("Амбициозная", data.ambitious?.km_goal, data.ambitious?.runs_goal)}
      </div>
      <div class="goal-actions">
        <button class="btn btn-primary" id="accept-goal-btn" type="button"
          data-km="${Number(data.km_goal || 0)}"
          data-runs="${Number(data.runs_goal || 0)}"
          data-message="${escapeHtml(data.message || "")}"
          onclick="acceptSuggestedGoal(${year}, ${month})">Принять цель</button>
        <button class="btn" type="button" onclick="hideGoalPanel('goal-suggestion')">Отмена</button>
      </div>
    `;
  } catch (error) {
    suggestion.innerHTML = `<div class="alert alert-warning"><span class="alert-dot"></span>${escapeHtml(error.message)}</div>`;
  }
}

function goalVariant(label, km, runs, selected = false) {
  const safeKm = Number(km || 0);
  const safeRuns = Number(runs || 0);
  return `
    <button class="metric goal-variant ${selected ? "goal-variant--selected" : ""}" type="button"
      data-km="${safeKm}" data-runs="${safeRuns}" onclick="selectGoalVariant(this)">
      <span class="metric-label">${label}</span>
      <span class="metric-value">${safeKm ? safeKm.toFixed(1) : "—"}</span>
      <span class="metric-sub">км · ${safeRuns || "—"} пробежек</span>
    </button>
  `;
}

function selectGoalVariant(el) {
  const root = el.closest(".goal-variants");
  if (root) {
    root.querySelectorAll(".goal-variant").forEach((item) => item.classList.remove("goal-variant--selected"));
  }
  el.classList.add("goal-variant--selected");
  const button = document.getElementById("accept-goal-btn");
  if (button) {
    button.dataset.km = el.dataset.km;
    button.dataset.runs = el.dataset.runs;
  }
}

async function acceptSuggestedGoal(year, month) {
  const button = document.getElementById("accept-goal-btn");
  if (!button) {
    return;
  }
  await saveGoal(year, month, Number(button.dataset.km), Number(button.dataset.runs), button.dataset.message || null);
}

function showManualGoalForm(year, month, km = 50, runs = 12) {
  const form = document.getElementById("goal-form");
  const suggestion = document.getElementById("goal-suggestion");
  if (!form) {
    return;
  }
  if (suggestion) {
    suggestion.hidden = true;
  }
  form.hidden = false;
  form.innerHTML = `
    <div class="goal-form-grid">
      <label class="settings-field">
        <span class="settings-label">Километры</span>
        <input class="settings-input" type="number" id="goal-km-input" min="1" max="1000" step="0.1" value="${Number(km).toFixed(1)}">
      </label>
      <label class="settings-field">
        <span class="settings-label">Пробежек</span>
        <input class="settings-input" type="number" id="goal-runs-input" min="1" max="31" step="1" value="${Number(runs)}">
      </label>
    </div>
    <div class="goal-actions">
      <button class="btn btn-primary" type="button" onclick="saveManualGoal(${year}, ${month})">Сохранить</button>
      <button class="btn" type="button" onclick="hideGoalPanel('goal-form')">Отмена</button>
    </div>
  `;
}

async function saveManualGoal(year, month) {
  const km = Number(document.getElementById("goal-km-input")?.value);
  const runs = Number(document.getElementById("goal-runs-input")?.value);
  await saveGoal(year, month, km, runs, null);
}

async function saveGoal(year, month, km, runs, aiSuggestion) {
  if (!Number.isFinite(km) || km <= 0 || !Number.isFinite(runs) || runs <= 0) {
    return;
  }
  const response = await fetch("/api/goals/monthly", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      year,
      month,
      km_goal: km,
      runs_goal: Math.round(runs),
      ai_suggestion: aiSuggestion,
    }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const panel = document.getElementById("goal-form") || document.getElementById("goal-suggestion");
    if (panel) {
      panel.hidden = false;
      panel.innerHTML = `<div class="alert alert-warning"><span class="alert-dot"></span>${escapeHtml(payload.detail || "Не удалось сохранить цель.")}</div>`;
    }
    return;
  }
  await renderGoalCard();
}

function hideGoalPanel(id) {
  const panel = document.getElementById(id);
  if (panel) {
    panel.hidden = true;
  }
}

async function renderProgressCard() {
  try {
    const res = await fetch("/api/activities/progress");
    const data = await res.json();
    const weeks = data.weeks || [];
    const summary = data.summary || {};
    const card = document.getElementById("progress-card");
    const summaryEl = document.getElementById("progress-summary");
    const hintEl = document.getElementById("progress-hint");
    const canvas = document.getElementById("ef-chart");

    if (!card || !summaryEl || !hintEl || !canvas || !window.Chart) {
      return;
    }

    if (data.scatter) {
      scatterDataCache = data.scatter;
    }

    if (!weeks.length) {
      card.style.display = "none";
      return;
    }

    const trendVal = summary.trend;
    const trendClass = trendVal === null || trendVal === undefined ? "" : trendVal >= 0 ? "positive" : "negative";
    const trendStr = trendVal === null || trendVal === undefined ? "—" : `${trendVal >= 0 ? "+" : ""}${Number(trendVal).toFixed(1)}%`;

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
        <span class="progress-stat-label">Тренд</span>
        <span class="progress-stat-value ${trendClass}">${trendStr}</span>
      </div>
    `;

    hintEl.textContent = `пик ${summary.peak_week ?? "—"} · ${summary.total_weeks ?? 0} нед.`;

    const labels = weeks.map((week) => week.label);
    const efValues = weeks.map((week) => week.ef);
    const trendData = weeks.map((_, index) => {
      const slice = efValues.slice(Math.max(0, index - 2), index + 1);
      if (!slice.length) {
        return null;
      }
      const avg = slice.reduce((sum, value) => sum + value, 0) / slice.length;
      return Number(avg.toFixed(3));
    });

    if (efChart) {
      efChart.destroy();
    }

    efChart = new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "EF",
            data: efValues,
            borderColor: "#3a5040",
            backgroundColor: "rgba(58,80,64,0.06)",
            tension: 0.3,
            pointRadius: 3,
            pointBackgroundColor: "#3a5040",
            borderWidth: 2,
            fill: true,
          },
          {
            label: "тренд",
            data: trendData,
            borderColor: "#c8a020",
            borderDash: [5, 3],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(context) {
                return context.datasetIndex === 0
                  ? `EF: ${context.parsed.y.toFixed(2)}`
                  : `тренд: ${context.parsed.y.toFixed(2)}`;
              },
            },
          },
        },
        scales: {
          x: {
            ticks: { autoSkip: true, maxRotation: 45, maxTicksLimit: 12, font: { size: 11 } },
            grid: { display: false },
          },
          y: {
            ticks: {
              font: { size: 11 },
              callback(value) {
                return Number(value).toFixed(2);
              },
            },
            grid: { color: "rgba(128,128,128,0.1)" },
          },
        },
      },
    });
  } catch (error) {
    const card = document.getElementById("progress-card");
    if (card) {
      card.style.display = "none";
    }
  }
}

function openScatterModal() {
  const modal = document.getElementById("scatter-modal");
  if (!modal) {
    return;
  }
  modal.style.display = "flex";
  if (scatterDataCache) {
    renderScatterChart(scatterDataCache);
  }
}

function closeScatterModal(event) {
  const modal = document.getElementById("scatter-modal");
  if (!modal) {
    return;
  }
  if (event && event.target !== modal) {
    return;
  }
  modal.style.display = "none";
}

function openPromptModal(title, promptText) {
  const modal = document.getElementById("prompt-modal");
  const titleEl = document.getElementById("prompt-modal-title");
  const textEl = document.getElementById("prompt-modal-text");
  const copyBtn = document.getElementById("prompt-copy-btn");
  if (!modal || !titleEl || !textEl) {
    return;
  }
  titleEl.textContent = title;
  textEl.textContent = promptText || "Промпт пустой";
  if (copyBtn) {
    copyBtn.textContent = "Копировать";
  }
  modal.style.display = "flex";
}

function closePromptModal(event) {
  const modal = document.getElementById("prompt-modal");
  if (!modal) {
    return;
  }
  if (event && event.target !== modal) {
    return;
  }
  modal.style.display = "none";
}

function setAnalysisMode(hasAnalysis, cached = false) {
  const getBtn = document.getElementById("get-analysis-btn");
  const refreshBtn = document.getElementById("refresh-btn");
  const cachedBadge = document.getElementById("ai-cached-badge");

  if (getBtn) {
    getBtn.style.display = hasAnalysis ? "none" : "inline-block";
  }
  if (refreshBtn) {
    refreshBtn.style.display = hasAnalysis ? "inline-block" : "none";
  }
  if (cachedBadge) {
    cachedBadge.style.display = cached ? "inline-block" : "none";
  }
}

async function showPromptFromUrl(url, title) {
  openPromptModal(title, "Загрузка...");
  try {
    const response = await fetch(url);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || "Не удалось загрузить промпт");
    }
    openPromptModal(title, payload.prompt || "");
  } catch (error) {
    openPromptModal(title, `Ошибка: ${error.message}`);
  }
}

async function copyPromptText() {
  const textEl = document.getElementById("prompt-modal-text");
  const copyBtn = document.getElementById("prompt-copy-btn");
  if (!textEl) {
    return;
  }
  const text = textEl.textContent || "";
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    if (copyBtn) {
      copyBtn.textContent = "Скопировано";
    }
  } catch (error) {
    if (copyBtn) {
      copyBtn.textContent = "Ошибка";
    }
  }
}

async function showTodayPrompt() {
  await showPromptFromUrl("/api/ai/recommendation/prompt", "Промпт рекомендации на сегодня");
}

async function showActivityPrompt() {
  const activityId = document.getElementById("activity-id")?.value;
  if (!activityId) {
    return;
  }
  await showPromptFromUrl(
    `/api/ai/analyze/prompt?activity_id=${encodeURIComponent(activityId)}`,
    "Промпт анализа тренировки",
  );
}

function renderScatterChart(scatterData) {
  const canvas = document.getElementById("scatter-chart");
  if (!canvas || !window.Chart) {
    return;
  }
  if (scatterChart) {
    scatterChart.destroy();
  }

  const monthGroups = {};
  const latestPoint = scatterData.length ? scatterData[scatterData.length - 1] : null;
  for (const point of scatterData) {
    if (latestPoint && point.date === latestPoint.date && point.pace_sec === latestPoint.pace_sec && point.hrm === latestPoint.hrm) {
      continue;
    }
    if (!monthGroups[point.month]) {
      monthGroups[point.month] = {
        label: point.month_label,
        data: [],
      };
    }
    monthGroups[point.month].data.push({
      x: point.pace_min,
      y: point.hrm,
      date: point.date,
      distance: point.distance_km,
    });
  }

  const PERIOD_COLORS = [
    "#c0dda0", "#8fc46a", "#639922", "#3B6D11",
    "#27500A", "#3a5040", "#1e2e18",
  ];
  const EF_LINES = [
    { ef: 0.80, color: "#85b7eb", label: "EF 0.80" },
    { ef: 0.90, color: "#639922", label: "EF 0.90" },
    { ef: 1.00, color: "#3a5040", label: "EF 1.00" },
    { ef: 1.10, color: "#c8a020", label: "EF 1.10" },
    { ef: 1.20, color: "#a04040", label: "EF 1.20" },
  ];

  const sortedMonths = Object.keys(monthGroups).sort();
  const scatterDatasets = sortedMonths.map((month, i) => ({
    label: monthGroups[month].label,
    data: monthGroups[month].data,
    backgroundColor: `${PERIOD_COLORS[i % PERIOD_COLORS.length]}cc`,
    borderColor: PERIOD_COLORS[i % PERIOD_COLORS.length],
    borderWidth: 1,
    pointRadius: 6,
    pointHoverRadius: 8,
  }));

  if (latestPoint) {
    scatterDatasets.push({
      label: "Последняя тренировка",
      data: [
        {
          x: latestPoint.pace_min,
          y: latestPoint.hrm,
          date: latestPoint.date,
          distance: latestPoint.distance_km,
        },
      ],
      backgroundColor: "#b54444",
      borderColor: "#b54444",
      borderWidth: 1,
      pointRadius: 7,
      pointHoverRadius: 9,
      order: 1,
    });
  }

  const paceRange = [];
  for (let p = 270; p <= 600; p += 5) {
    paceRange.push(p);
  }

  const efLineDatasets = EF_LINES.map(({ ef, color, label }) => ({
    label,
    data: paceRange
      .map((p) => ({
        x: p / 60,
        y: (1000 / p * 60) / ef,
      }))
      .filter((pt) => pt.y >= 95 && pt.y <= 205),
    borderColor: color,
    borderDash: [5, 3],
    borderWidth: 1.5,
    pointRadius: 0,
    type: "line",
    fill: false,
    tension: 0,
    order: 2,
  }));

  const legendEl = document.getElementById("scatter-legend");
  if (legendEl) {
    const periodItems = sortedMonths.map((month, i) => `
      <span style="display:flex;align-items:center;gap:5px">
        <span style="width:10px;height:10px;border-radius:50%;background:${PERIOD_COLORS[i % PERIOD_COLORS.length]};display:inline-block"></span>
        ${monthGroups[month].label}
      </span>
    `).join("");
    const latestItem = latestPoint ? `
      <span style="display:flex;align-items:center;gap:5px">
        <span style="width:10px;height:10px;border-radius:50%;background:#b54444;display:inline-block"></span>
        Последняя
      </span>
    ` : "";
    const efItems = EF_LINES.map(({ ef, color }) => `
      <span style="display:flex;align-items:center;gap:4px">
        <span style="width:16px;height:0;border-top:1.5px dashed ${color};display:inline-block;vertical-align:middle"></span>
        EF ${ef.toFixed(2)}
      </span>
    `).join("");
    legendEl.innerHTML = `
      <span style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-right:4px">Периоды:</span>
      ${periodItems}
      ${latestItem}
      <span style="margin-left:8px;font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-right:4px">EF:</span>
      ${efItems}
    `;
  }

  const paces = scatterData.map((d) => d.pace_min);
  const hrms = scatterData.map((d) => d.hrm);
  const paceMin = Math.floor(Math.min(...paces) * 10) / 10 - 0.3;
  const paceMax = Math.ceil(Math.max(...paces) * 10) / 10 + 0.3;
  const hrmMin = Math.min(...hrms) - 10;
  const hrmMax = Math.max(...hrms) + 10;

  scatterChart = new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        ...efLineDatasets,
        ...scatterDatasets,
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          filter: (ctx) => ctx.dataset.type !== "line",
          callbacks: {
            label(ctx) {
              const d = ctx.raw;
              const paceStr = formatPace(Math.round(d.x * 60));
              return [
                `${d.date}`,
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
            callback(value) {
              return formatPace(Math.round(Number(value) * 60));
            },
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

function renderDashboardMetrics(activities) {
  const root = document.getElementById("metrics-grid");
  if (!root) {
    return;
  }

  if (!activities.length) {
    root.innerHTML = metricCard("Последняя пробежка", "Нет данных", "Сначала выполните синк");
    return;
  }

  const latest = activities[0];
  const avgHrRuns = activities.slice(0, 7).filter((item) => item.avg_hrm);
  const avgHr = avgHrRuns.length
    ? Math.round(avgHrRuns.reduce((sum, item) => sum + item.avg_hrm, 0) / avgHrRuns.length)
    : null;
  const recordRun = activities.reduce(
    (best, item) => ((item.distance_km || 0) > (best.distance_km || 0) ? item : best),
    activities[0]
  );

  root.innerHTML = [
    metricCard("Последняя", latest.distance_km ? Number(latest.distance_km).toFixed(2) : "—", `км · ${formatDate(latest.date)}`),
    metricCard("Всего", String(activities.length), "пробежек"),
    metricCard("Пульс", avgHr ? String(avgHr) : "—", "среднее · 7 пробежек"),
    metricCard("Рекорд", recordRun.distance_km ? Number(recordRun.distance_km).toFixed(2) : "—", `км · ${formatDate(recordRun.date)}`),
  ].join("");
}

function renderDashboardAlerts(activities) {
  const root = document.getElementById("alerts-section");
  if (!root) {
    return;
  }
  if (!activities.length) {
    root.innerHTML = '<div class="alert alert-warning"><span class="alert-dot"></span>Нет данных для анализа алертов.</div>';
    return;
  }

  const alerts = [];
  const latest = activities[0];
  const lastRunDate = new Date(latest.date);
  const now = new Date();
  const daysSinceLastRun = Math.floor((now - lastRunDate) / 86400000);

  if (latest.avg_hrm && latest.avg_hrm > 185) {
    alerts.push({ cls: "alert-danger", text: "🔴 Последний пульс выше 185 bpm. Проверь восстановление." });
  }

  const currentWeek = activities.slice(0, 7).reduce((sum, item) => sum + (item.train_load || 0), 0);
  const prevWeek = activities.slice(7, 14).reduce((sum, item) => sum + (item.train_load || 0), 0);
  if (prevWeek > 0 && currentWeek > prevWeek * 1.2) {
    alerts.push({ cls: "alert-warning", text: "🟡 Недельная нагрузка выросла больше чем на 20%." });
  }

  if (daysSinceLastRun > 7) {
    alerts.push({ cls: "alert-warning", text: "🟡 С последней пробежки прошло больше 7 дней." });
  }

  if (!alerts.length) {
    alerts.push({ cls: "alert-success", text: "🟢 Всё в норме. Нагрузка и пульс в ожидаемом диапазоне." });
  }

  root.innerHTML = alerts
    .map((item) => `<div class="alert ${item.cls}"><span class="alert-dot"></span>${item.text}</div>`)
    .join("");
}

function renderDistanceChart(activities, healthStates = []) {
  const canvas = document.getElementById("dist-chart");
  if (!canvas || !window.Chart) {
    return;
  }

  if (dashboardChart) {
    dashboardChart.destroy();
  }

  const labels = activities.map((item) => formatShortDate(item.date));
  const maxDistance = Math.max(1, ...activities.map((item) => Number(item.distance_km || 0)));
  const healthMarkers = buildHealthMarkersForDistanceChart(activities, healthStates, maxDistance);
  const visibleTickIndexes = new Set();
  activities.forEach((item, index) => {
    if (item.showTick) {
      visibleTickIndexes.add(index);
    }
  });

  dashboardChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Дистанция, км",
          data: activities.map((item) => item.distance_km),
          backgroundColor: activities.map((_, i) =>
            i === activities.length - 1 ? "#3a5040" : "rgba(58,80,64,0.25)"
          ),
          borderRadius: 6,
          barPercentage: 0.92,
          categoryPercentage: 0.98,
        },
        {
          type: "line",
          label: "Состояние",
          data: healthMarkers.map((item) => item ? item.y : null),
          healthMarkers,
          showLine: false,
          pointStyle: "triangle",
          pointRadius: healthMarkers.map((item) => item ? 6 : 0),
          pointHoverRadius: healthMarkers.map((item) => item ? 8 : 0),
          pointRotation: 180,
          pointBackgroundColor: "#a04040",
          pointBorderColor: "#a04040",
          pointBorderWidth: 1,
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(context) {
              if (context.dataset.healthMarkers) {
                const marker = context.dataset.healthMarkers[context.dataIndex];
                if (!marker) {
                  return "";
                }
                return [
                  "Проблема со здоровьем",
                  ...marker.descriptions.map((text) => `- ${text}`),
                ];
              }
              return `Дистанция: ${Number(context.raw || 0).toFixed(2)} км`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#9b9b96",
            autoSkip: false,
            minRotation: 0,
            maxRotation: 0,
            callback(value, index) {
              return visibleTickIndexes.has(index) ? labels[index] : "";
            },
          },
          grid: { display: false },
        },
        y: {
          suggestedMax: maxDistance * 1.25,
          ticks: { color: "#9b9b96" },
          grid: { color: "rgba(255,255,255,0.08)" },
        },
      },
    },
  });
}

function buildHealthMarkersForDistanceChart(activities, healthStates, maxDistance) {
  if (!activities.length || !healthStates.length) {
    return activities.map(() => null);
  }

  const chartStart = dateKey(activities[0].date);
  const chartEnd = dateKey(activities[activities.length - 1].date);
  const markerY = maxDistance * 1.12;
  return activities.map((activity) => {
    const activityKey = dateKey(activity.date);
    const descriptions = healthStates
      .filter((state) => {
        const startedAt = dateKey(state.started_at);
        const endedAt = dateKey(state.ended_at) || todayDateKey();
        return startedAt <= chartEnd && endedAt >= chartStart && activityKey >= startedAt && activityKey <= endedAt;
      })
      .map((state) => state.description)
      .filter(Boolean);

    if (!descriptions.length) {
      return null;
    }
    return {
      y: markerY,
      descriptions,
    };
  });
}

function buildDailyDistanceSeries(activities) {
  if (!Array.isArray(activities) || !activities.length) {
    return [];
  }

  const distanceByDate = new Map();
  for (const item of activities) {
    const key = dateKey(item.date);
    if (!key) {
      continue;
    }
    distanceByDate.set(key, (distanceByDate.get(key) || 0) + Number(item.distance_km || 0));
  }

  const keys = Array.from(distanceByDate.keys()).sort();
  if (!keys.length) {
    return [];
  }
  const tickKeys = new Set();
  const anchors = [0, Math.floor((keys.length - 1) * 0.25), Math.floor((keys.length - 1) * 0.5), Math.floor((keys.length - 1) * 0.75), keys.length - 1];
  anchors.forEach((index) => tickKeys.add(keys[index]));

  const series = [];
  const endKey = todayDateKey() > keys[keys.length - 1] ? todayDateKey() : keys[keys.length - 1];
  for (let cursor = parseDateKey(keys[0]), end = parseDateKey(endKey); cursor <= end; cursor = addUtcDays(cursor, 1)) {
    const key = cursor.toISOString().slice(0, 10);
    series.push({
      date: `${key}T00:00:00Z`,
      distance_km: distanceByDate.get(key) || 0,
      hasRun: distanceByDate.has(key),
      showTick: tickKeys.has(key),
    });
  }
  return series;
}

function dateKey(value) {
  if (!value) {
    return "";
  }
  const direct = String(value).match(/^(\d{4}-\d{2}-\d{2})/);
  if (direct) {
    return direct[1];
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return parsed.toISOString().slice(0, 10);
}

function parseDateKey(key) {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function todayDateKey() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addUtcDays(date, days) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + days));
}

function renderRunsTable(activities) {
  const body = document.getElementById("run-list");
  if (!body) {
    return;
  }

  if (!activities.length) {
    body.innerHTML = '<tr><td colspan="8" class="empty-message">Пробежек пока нет.</td></tr>';
    return;
  }

  body.innerHTML = activities.map((item) => {
    const pace = formatPace(item.avg_pace);
    const ef = item.avg_pace && item.avg_hrm
      ? ((1000 / item.avg_pace * 60) / item.avg_hrm).toFixed(2)
      : "—";
    const recovery = item.recover_time !== null && item.recover_time !== undefined
      ? `${Math.round(item.recover_time)} ч`
      : "—";
    const detailsCell = item.has_details
      ? '<span class="detail-status detail-status--ready">есть</span>'
      : `<button class="table-action-btn" type="button" onclick="loadRunDetails('${encodeURIComponent(item.activity_id)}', this)">Загрузить</button>`;
    return `
      <tr>
        <td><a class="run-link" href="/activity/${encodeURIComponent(item.activity_id)}">${formatDate(item.date)}</a></td>
        <td>${Number(item.distance_km).toFixed(2)} км</td>
        <td class="${item.avg_hrm <= 160 ? "hr-green" : item.avg_hrm <= 180 ? "hr-amber" : "hr-red"}">${item.avg_hrm ?? "—"}</td>
        <td>${pace}</td>
        <td>${ef}</td>
        <td>${item.train_load ?? "—"}</td>
        <td>${recovery}</td>
        <td>${detailsCell}</td>
      </tr>
    `;
  }).join("");
}

async function loadRunDetails(activityId, button) {
  if (!button) {
    return;
  }

  const cell = button.closest("td");
  button.disabled = true;
  button.textContent = "Загрузка...";

  try {
    const response = await fetch(`/api/activities/${activityId}/detail`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || "Не удалось загрузить детали");
    }
    if (cell) {
      cell.innerHTML = '<span class="detail-status detail-status--ready">есть</span>';
    }
  } catch (error) {
    button.disabled = false;
    button.textContent = "Повторить";
  }
}

async function loadAllRunDetails() {
  const button = document.getElementById("load-all-details-btn");
  const status = document.getElementById("details-bulk-status");

  if (button) {
    button.disabled = true;
    button.textContent = "Загрузка...";
  }
  if (status) {
    status.textContent = "Запущена догрузка деталей по всем тренировкам без графика.";
  }

  try {
    const response = await fetch("/api/activities/details/load-all", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || "Не удалось загрузить детали");
    }
    if (status) {
      status.textContent = `Готово: загружено ${payload.loaded} из ${payload.total}, ошибок ${payload.failed}.`;
    }
    await loadRunsPage(runsPage);
  } catch (error) {
    if (status) {
      status.textContent = `Ошибка: ${error.message}`;
    }
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Загрузить все детали";
    }
  }
}

async function loadRunsPage(page) {
  const offset = page * RUNS_PAGE_SIZE;
  const response = await fetch(`/api/activities?limit=${RUNS_PAGE_SIZE}&offset=${offset}`);
  const payload = await response.json();
  renderRunsTable(payload.activities || []);
  runsPage = page;
  updateRunsPager(payload.total || 0);
}

function updateRunsPager(total) {
  const totalPages = Math.max(1, Math.ceil(total / RUNS_PAGE_SIZE));
  const pageStatus = document.getElementById("runs-page-status");
  const prevBtn = document.getElementById("runs-prev-btn");
  const nextBtn = document.getElementById("runs-next-btn");

  if (pageStatus) {
    pageStatus.textContent = `Страница ${runsPage + 1} из ${totalPages}`;
  }
  if (prevBtn) {
    prevBtn.disabled = runsPage <= 0;
  }
  if (nextBtn) {
    nextBtn.disabled = runsPage >= totalPages - 1;
  }
}

async function changeRunsPage(delta) {
  const nextPage = Math.max(0, runsPage + delta);
  if (nextPage === runsPage && delta < 0) {
    return;
  }
  await loadRunsPage(nextPage);
}

async function initDetailPage(activityId) {
  bindDetailChartModeToggle();
  const script = document.getElementById("activity-data");
  if (!script) {
    return;
  }
  currentActivity = JSON.parse(script.textContent);
  loadPageSettings();
  currentDetails = null;

  const activityDate = document.getElementById("detail-date-title");
  const distanceTitle = document.getElementById("detail-distance-title");
  const button = document.getElementById("load-detail-btn");
  if (activityDate) {
    activityDate.textContent = formatDate(currentActivity.date);
  }
  if (distanceTitle) {
    distanceTitle.textContent = `${Number(currentActivity.distance_km || 0).toFixed(2)} км`;
  }

  renderDetailMetrics(currentActivity);
  renderZoneBars(currentActivity);

  const response = await fetch(`/api/activities/${encodeURIComponent(activityId)}`);
  if (!response.ok) {
    setDetailStatus("Не удалось загрузить активность");
    return;
  }

  const payload = await response.json();
  if (payload.details) {
    currentDetails = pickRenderableDetails(payload.details);
    renderDetailChart(currentDetails, currentChartMode);
    setDetailStatus("Детали уже доступны");
    if (button) {
      button.style.display = "none";
    }
  } else {
    setDetailStatus("Детали ещё не загружены");
    if (button) {
      button.style.display = "inline-flex";
      button.textContent = "Загрузить детали";
    }
  }

  await loadCachedAnalysis();
}

function renderDetailMetrics(activity) {
  const root = document.getElementById("detail-metrics");
  if (!root) {
    return;
  }
  root.innerHTML = [
    metricCard("Пульс", activity.avg_hrm ? `${activity.avg_hrm} bpm` : "—", "Средний пульс"),
    metricCard("Темп", formatPace(activity.avg_pace), "Средний темп"),
    metricCard("Каденс", activity.avg_cadence ?? "—", "Шагов в минуту"),
    metricCard("Длина шага", activity.avg_stride ? `${activity.avg_stride} см` : "—", "Средняя длина шага"),
    metricCard("Нагрузка", activity.train_load ?? "—", "Train load"),
    metricCard("Восстановление", formatHours(Math.round(activity.recover_time || 0)), "Прогноз восстановления"),
  ].join("");
}

function renderZoneBars(activity) {
  const root = document.getElementById("zones-section");
  if (!root) {
    return;
  }

  const zones = [
    { label: "Жиросжигание", value: activity.hrm_fat_burning_duration || 0, color: "#85b7eb" },
    { label: "Аэробная", value: activity.hrm_aerobic_duration || 0, color: "#3a5040" },
    { label: "Анаэробная", value: activity.hrm_anaerobic_duration || 0, color: "#c8a020" },
    { label: "Экстремальная", value: activity.hrm_extreme_duration || 0, color: "#a04040" },
  ];

  const total = zones.reduce((sum, zone) => sum + zone.value, 0) || 1;
  root.innerHTML = zones.map((zone) => {
    const percent = Math.round((zone.value / total) * 100);
    return `
      <div class="zone-row">
        <div class="zone-name">${zone.label}</div>
        <div class="zone-bar-wrap">
          <div class="zone-bar" style="width:${percent}%; background:${zone.color}"></div>
        </div>
        <div class="zone-pct">${percent}%</div>
      </div>
    `;
  }).join("");
}

function renderDetailChart(details, mode = "time") {
  const canvas = document.getElementById("hr-chart");
  const efCanvas = document.getElementById("ef-detail-chart");
  const labelsRoot = document.getElementById("detail-chart-labels");
  if (!canvas || !efCanvas || !window.Chart) {
    return;
  }

  const samples = details.samples || [];
  const trackPoints = details.track_points || [];
  if (!samples.length) {
    setDetailStatus("В деталях нет samples для графика");
    return;
  }

  if (detailChart) {
    detailChart.destroy();
  }
  if (efDetailChart) {
    efDetailChart.destroy();
  }

  const toggle = document.getElementById("chart-mode-toggle");
  const btnDist = document.getElementById("btn-by-dist");
  const title = document.getElementById("detail-chart-title");
  const distanceSeries = buildDistanceSeries(samples, trackPoints, currentActivity?.distance_km);
  const hasDistance = Boolean(distanceSeries?.labels?.length);
  const effectiveMode = mode === "distance" && hasDistance ? "distance" : "time";
  currentChartMode = effectiveMode;
  if (toggle) {
    toggle.style.display = "flex";
  }
  if (btnDist) {
    btnDist.disabled = !hasDistance;
    btnDist.title = !hasDistance ? "GPS данные недоступны" : "";
  }
  if (title) {
    title.textContent = effectiveMode === "distance"
      ? "Пульс и скорость по дистанции"
      : "Пульс и скорость по времени";
  }
  document.getElementById("btn-by-time")?.classList.toggle("active", effectiveMode === "time");
  document.getElementById("btn-by-dist")?.classList.toggle("active", effectiveMode === "distance");

  const baseTime = samples[0].start_time || samples[0].timestamp || 0;
  const timeLabels = samples.map((sample) => {
    const t = sample.start_time || sample.timestamp || baseTime;
    return Math.max(0, Number(((t - baseTime) / 60).toFixed(2)));
  });
  const timeHeartRate = samples.map((sample) => sample.heart_rate);
  const timeSpeed = trackPoints.length
    ? trackPoints.slice(0, timeLabels.length).map((point) => point.speed_mps ? Number((point.speed_mps * 3.6).toFixed(2)) : null)
    : samples.map((sample) => sample.speed_mps ? Number((sample.speed_mps * 3.6).toFixed(2)) : null);

  let labels;
  let heartRate;
  let speed;

  if (effectiveMode === "distance") {
    labels = distanceSeries.labels;
    heartRate = distanceSeries.heartRate;
    speed = distanceSeries.speed;
  } else {
    labels = timeLabels;
    heartRate = timeHeartRate;
    speed = timeSpeed;
  }

  const maxAxisValue = labels[labels.length - 1] || 0;
  const heartRatePoints = labels.map((x, index) => ({ x, y: heartRate[index] }));
  const speedPoints = labels.map((x, index) => ({ x, y: speed[index] }));
  const ef = labels.map((_, index) => {
    const hr = timeHeartRate[index];
    const speedKmh = timeSpeed[index];
    if (!hr || !speedKmh) {
      return null;
    }
    const speedMpm = speedKmh * 1000 / 60;
    return Number((speedMpm / hr).toFixed(3));
  });
  const zoneLowValue = Number(currentSettings?.target_hr_zone_low ?? 140);
  const zoneHighValue = Number(currentSettings?.target_hr_zone_high ?? 160);
  const zoneLow = labels.map((x) => ({ x, y: zoneLowValue }));
  const zoneHigh = labels.map((x) => ({ x, y: zoneHighValue }));

  if (labelsRoot) {
    const anchors = [0, Math.round(maxAxisValue * 0.25), Math.round(maxAxisValue * 0.5), Math.round(maxAxisValue * 0.75), maxAxisValue];
    const uniqueAnchors = [...new Set(anchors)];
    if (effectiveMode === "distance") {
      labelsRoot.innerHTML = uniqueAnchors
        .map((value) => `<span>${value >= 1000 ? `${(value / 1000).toFixed(1)}км` : `${value}м`}</span>`)
        .join("");
    } else {
      labelsRoot.innerHTML = uniqueAnchors.map((minute) => `<span>${minute} м</span>`).join("");
    }
  }

  detailChart = new Chart(canvas, {
    type: "line",
    data: {
      datasets: [
        {
          label: "Пульс",
          data: heartRatePoints,
          borderColor: "#b54444",
          backgroundColor: "rgba(181,68,68,0.08)",
          yAxisID: "y",
          tension: 0.22,
        },
        {
          label: "Скорость км/ч",
          data: speedPoints,
          borderColor: "#4f7db8",
          yAxisID: "y1",
          tension: 0.18,
        },
        {
          label: "Нижняя граница зоны",
          data: zoneLow,
          borderColor: "rgba(99, 153, 34, 0)",
          pointRadius: 0,
          yAxisID: "y",
        },
        {
          label: `Зона ${zoneLowValue}–${zoneHighValue}`,
          data: zoneHigh,
          borderColor: "rgba(99, 153, 34, 0)",
          backgroundColor: "rgba(99, 153, 34, 0.16)",
          pointRadius: 0,
          fill: "-1",
          yAxisID: "y",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: 2,
      animation: false,
      interaction: { mode: "index", intersect: false },
      elements: {
        line: { borderWidth: 2 },
        point: { radius: 0 },
      },
      scales: {
        x: {
          type: "linear",
          min: 0,
          max: maxAxisValue,
          ticks: { display: false },
          grid: { color: "rgba(255,255,255,0.05)" },
        },
        y: {
          position: "left",
          ticks: { color: "#90a89a", font: { size: 11 } },
          grid: { color: "rgba(255,255,255,0.08)" },
        },
        y1: {
          position: "right",
          ticks: { color: "#90a89a", font: { size: 11 } },
          grid: { drawOnChartArea: false },
        },
      },
      plugins: {
        tooltip: {
          filter(context) {
            return context.datasetIndex === 0 || context.datasetIndex === 1;
          },
          callbacks: {
            label(context) {
              if (context.datasetIndex === 0) {
                return `Пульс: ${context.parsed.y} уд/мин`;
              }
              if (context.datasetIndex === 1) {
                return `Скорость: ${context.parsed.y} км/ч`;
              }
              return "";
            },
          },
        },
        legend: { display: false },
      },
    },
  });

  efDetailChart = new Chart(efCanvas, {
    type: "line",
    data: {
      labels: timeLabels,
      datasets: [
        {
          label: "EF",
          data: ef,
          borderColor: "#3a5040",
          backgroundColor: "rgba(58,80,64,0.08)",
          tension: 0.24,
          pointRadius: 0,
          borderWidth: 2,
          fill: true,
          spanGaps: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: 2,
      animation: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          ticks: { display: false },
          grid: { display: false },
        },
        y: {
          ticks: {
            color: "#90a89a",
            font: { size: 10 },
            callback(value) {
              return Number(value).toFixed(2);
            },
          },
          grid: { color: "rgba(255,255,255,0.06)" },
        },
      },
      plugins: {
        tooltip: {
          callbacks: {
            label(context) {
              return `EF: ${Number(context.parsed.y).toFixed(3)}`;
            },
          },
        },
        legend: { display: false },
      },
    },
  });
}

async function loadActivityDetails() {
  if (!currentActivity) {
    return;
  }
  const button = document.getElementById("load-detail-btn");
  if (button) {
    button.disabled = true;
  }
  setDetailStatus("Загружаем детали...");

  try {
    const response = await fetch(`/api/activities/${encodeURIComponent(currentActivity.activity_id)}/detail`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || "Не удалось загрузить детали");
    }
    currentDetails = pickRenderableDetails(payload.details);
    renderDetailChart(currentDetails, currentChartMode);
    setDetailStatus("Детали загружены");
    if (button) {
      button.style.display = "none";
    }
  } catch (error) {
    setDetailStatus(error.message);
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function loadDetail() {
  await loadActivityDetails();
}

function switchChartMode(mode) {
  if (!currentDetails) {
    return;
  }
  currentChartMode = mode;
  renderDetailChart(currentDetails, mode);
}

async function requestAiAnalysis() {
  if (!currentActivity) {
    return;
  }
  const container = document.getElementById("ai-analysis");
  if (container) {
    container.textContent = "Запрашиваем анализ...";
  }

  try {
    const response = await fetch("/api/ai/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ activity_id: currentActivity.activity_id }),
    });
    const payload = await response.json();
    if (container) {
      container.textContent = payload.analysis || "Ответ пустой";
    }
  } catch (error) {
    if (container) {
      container.textContent = `Ошибка: ${error.message}`;
    }
  }
}

function setDetailStatus(text) {
  const status = document.getElementById("detail-status");
  if (status) {
    status.textContent = text;
  }
}

async function loadTodayRecommendation() {
  const card = document.getElementById("today-card");
  if (!card) {
    return;
  }

  try {
    const res = await fetch("/api/ai/recommendation");
    const data = await res.json();

    if (data.status === "error") {
      renderTodayRefreshError(data);
      return;
    }

    if (!data.status) {
      setTodayEyebrow();
      document.getElementById("today-status").textContent = "Нет данных";
      document.getElementById("today-message").textContent =
        'Нажми "Синхронизировать" чтобы получить рекомендацию.';
      const meta = document.getElementById("today-meta");
      if (meta) {
        meta.innerHTML = "";
      }
      return;
    }

    setTodayEyebrow(data.date);
    card.className = `today-card today-card--${data.status}`;
    document.getElementById("today-status").textContent =
      STATUS_LABELS[data.status] || data.status;
    document.getElementById("today-message").textContent = data.message;
    const meta = document.getElementById("today-meta");
    if (meta) {
      const generated = data.generated_at
        ? new Date(data.generated_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
        : "—";
      meta.innerHTML = `
        <div>
          <div class="today-stat-label">статус</div>
          <div class="today-stat-value">${STATUS_LABELS[data.status] || data.status}</div>
        </div>
        <div>
          <div class="today-stat-label">обновлено</div>
          <div class="today-stat-value">${generated}</div>
        </div>
      `;
    }
  } catch (error) {
    document.getElementById("today-status").textContent = "Ошибка загрузки";
  }
}

function formatRecommendationDate(dateKey) {
  const match = String(dateKey || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return "";
  }
  return `${match[3]}.${match[2]}.${match[1]}`;
}

function setTodayEyebrow(recommendationDate) {
  const eyebrow = document.getElementById("today-eyebrow");
  if (!eyebrow) {
    return;
  }
  if (!recommendationDate || recommendationDate === todayDateKey()) {
    eyebrow.textContent = "ответ на сегодня";
    return;
  }
  const formatted = formatRecommendationDate(recommendationDate);
  eyebrow.textContent = formatted ? `ответ на ${formatted}` : "ответ на дату записи";
}

function renderTodayRefreshError(data) {
  const card = document.getElementById("today-card");
  if (card) {
    card.className = "today-card today-card--loading";
  }

  const eyebrow = document.getElementById("today-eyebrow");
  if (eyebrow) {
    eyebrow.textContent = "ответ не обновлён";
  }
  document.getElementById("today-status").textContent = "Нужно действие";
  const message = document.getElementById("today-message");
  const errorText = data.message || "Не удалось обновить рекомендацию.";
  const meta = document.getElementById("today-meta");
  if (meta) {
    meta.innerHTML = "";
  }

  if (data.action_url && data.action_label) {
    message.innerHTML = `
      <span>${escapeHtml(errorText)}</span>
      <a class="today-action-link" href="${escapeHtml(data.action_url)}">${escapeHtml(data.action_label)}</a>
    `;
  } else {
    message.textContent = errorText;
  }
}

async function refreshRecommendation() {
  const card = document.getElementById("today-card");
  if (card) {
    card.className = "today-card today-card--loading";
  }
  document.getElementById("today-status").textContent = "Генерирую...";
  document.getElementById("today-message").textContent = "";

  try {
    const res = await fetch("/api/ai/recommendation/refresh", { method: "POST" });
    const data = await res.json();
    if (!res.ok || data.status === "error") {
      renderTodayRefreshError(data);
      return;
    }
    await loadTodayRecommendation();
  } catch (error) {
    document.getElementById("today-status").textContent = "Ошибка";
    document.getElementById("today-message").textContent = String(error);
  }
}

async function getAnalysis(forceRefresh = false) {
  if (analysisRequestActive) {
    return;
  }
  const activityId = document.getElementById("activity-id")?.value;
  if (!activityId) {
    return;
  }

  const resultEl = document.getElementById("ai-result");
  const loadingEl = document.getElementById("ai-loading");
  const loadingTextEl = document.getElementById("ai-loading-text");
  const controlsEl = document.getElementById("ai-controls");

  if (!resultEl || !loadingEl || !loadingTextEl || !controlsEl) {
    return;
  }

  analysisRequestActive = true;
  controlsEl.querySelectorAll("button").forEach((button) => {
    button.disabled = true;
  });
  loadingEl.style.display = "block";
  loadingTextEl.textContent = forceRefresh ? "Готовлю новый анализ..." : "Проверяю сохранённый анализ...";
  setAnalysisMode(false, false);

  if (!forceRefresh) {
    try {
      const res = await fetch("/api/ai/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ activity_id: activityId, force_refresh: false }),
      });
      const data = await res.json();
      if (data.cached && data.analysis) {
        setAiResultText(resultEl, data.analysis);
        resultEl.style.display = "block";
        setAnalysisMode(true, true);
        loadingEl.style.display = "none";
        controlsEl.querySelectorAll("button").forEach((button) => {
          button.disabled = false;
        });
        analysisRequestActive = false;
        return;
      }
    } catch (error) {
      setAiResultText(resultEl, `Ошибка: ${error.message}`);
      resultEl.style.display = "block";
      loadingEl.style.display = "none";
      controlsEl.querySelectorAll("button").forEach((button) => {
        button.disabled = false;
      });
      analysisRequestActive = false;
      return;
    }
  }

  setAiResultText(resultEl, "");
  resultEl.style.display = "block";
  loadingEl.style.display = "block";
  loadingTextEl.textContent = "Тренер анализирует...";
  setAnalysisMode(false, false);

  const url = `/api/ai/analyze/stream?activity_id=${encodeURIComponent(activityId)}`;
  const source = new EventSource(url);

  source.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.error) {
      setAiResultText(resultEl, "Ошибка: " + data.error);
      loadingEl.style.display = "none";
      controlsEl.querySelectorAll("button").forEach((button) => {
        button.disabled = false;
      });
      analysisRequestActive = false;
      source.close();
      return;
    }
    if (data.chunk) {
      setAiResultText(resultEl, `${resultEl.textContent}${data.chunk}`);
    }
    if (data.done) {
      loadingEl.style.display = "none";
      setAnalysisMode(true, false);
      controlsEl.querySelectorAll("button").forEach((button) => {
        button.disabled = false;
      });
      analysisRequestActive = false;
      source.close();
    }
  };

  source.onerror = () => {
    loadingEl.style.display = "none";
    controlsEl.querySelectorAll("button").forEach((button) => {
      button.disabled = false;
    });
    analysisRequestActive = false;
    setAiResultText(resultEl, `${resultEl.textContent}\n[Соединение прервано]`);
    source.close();
  };
}

async function loadCachedAnalysis() {
  const activityId = document.getElementById("activity-id")?.value;
  const resultEl = document.getElementById("ai-result");

  if (!activityId || !resultEl) {
    return;
  }

  try {
    const res = await fetch("/api/ai/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ activity_id: activityId, force_refresh: false }),
    });
    const data = await res.json();
    if (data.cached && data.analysis) {
      setAiResultText(resultEl, data.analysis);
      resultEl.style.display = "block";
      setAnalysisMode(true, true);
    } else {
      setAnalysisMode(false, false);
    }
  } catch (error) {
    // Ignore cache lookup errors on initial page load.
    setAnalysisMode(false, false);
  }
}

async function initSettingsPage() {
  const status = document.getElementById("settings-status");
  if (status) {
    status.textContent = "Изменения применяются сразу после сохранения.";
  }
}

async function saveSettings() {
  const status = document.getElementById("settings-status");
  const dailyPrompt = document.getElementById("daily-prompt-template");
  const activityPrompt = document.getElementById("activity-prompt-template");
  const zoneLow = document.getElementById("target-hr-zone-low");
  const zoneHigh = document.getElementById("target-hr-zone-high");

  if (!dailyPrompt || !activityPrompt || !zoneLow || !zoneHigh) {
    return;
  }

  if (status) {
    status.textContent = "Сохраняю...";
  }

  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        daily_prompt_template: dailyPrompt.value,
        activity_prompt_template: activityPrompt.value,
        target_hr_zone_low: Number(zoneLow.value),
        target_hr_zone_high: Number(zoneHigh.value),
        dashboard_card_today: document.getElementById("dashboard-card-today")?.checked ?? true,
        dashboard_card_metrics: document.getElementById("dashboard-card-metrics")?.checked ?? true,
        dashboard_card_progress: document.getElementById("dashboard-card-progress")?.checked ?? true,
        dashboard_card_goal: document.getElementById("dashboard-card-goal")?.checked ?? true,
        dashboard_card_distance: document.getElementById("dashboard-card-distance")?.checked ?? true,
        dashboard_card_runs: document.getElementById("dashboard-card-runs")?.checked ?? true,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || payload.error || "Не удалось сохранить настройки");
    }
    if (status) {
      status.textContent = "Сохранено.";
    }
  } catch (error) {
    if (status) {
      status.textContent = `Ошибка: ${error.message}`;
    }
  }
}

async function initClaudeAuthPage() {
  const status = document.getElementById("claude-auth-status");
  const path = document.getElementById("claude-auth-path");

  if (status) {
    status.textContent = "Проверяю текущий файл авторизации...";
  }

  try {
    const response = await fetch("/api/claude-auth");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || "Не удалось проверить Claude auth");
    }
    if (path) {
      path.textContent = payload.credentials_path || "";
    }
    if (status) {
      status.textContent = payload.configured
        ? "Файл авторизации найден. Вставь новый токен, чтобы заменить его."
        : "Файл авторизации пока не найден. Вставь токен и сохрани.";
    }
    await startClaudeOAuth({ silent: true });
  } catch (error) {
    if (status) {
      status.textContent = `Ошибка: ${error.message}`;
    }
  }
}

async function saveClaudeAuth(event) {
  event.preventDefault();

  const status = document.getElementById("claude-auth-status");
  const token = document.getElementById("claude-auth-token");
  if (!token) {
    return;
  }

  if (status) {
    status.textContent = "Сохраняю...";
  }

  try {
    const response = await fetch("/api/claude-auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claudeAiOauth: token.value }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || payload.error || "Не удалось сохранить Claude auth");
    }
    token.value = "";
    if (status) {
      status.textContent = `Сохранено: ${payload.credentials_path}`;
    }
  } catch (error) {
    if (status) {
      status.textContent = `Ошибка: ${error.message}`;
    }
  }
}

async function startClaudeOAuth(options = {}) {
  const status = document.getElementById("claude-auth-status");
  const wrap = document.getElementById("claude-login-url-wrap");
  const urlField = document.getElementById("claude-login-url");

  if (status && !options.silent) {
    status.textContent = "Запускаю claude auth login на сервере...";
  }

  try {
    const response = await fetch("/api/claude-auth/login-url", { method: "POST" });
    const payload = await response.json();
    if (!response.ok || !payload.login_url || !payload.session_id) {
      throw new Error(payload.detail || payload.error || "Не удалось получить OAuth-ссылку");
    }

    window.currentClaudeLoginSessionId = payload.session_id;
    window.currentClaudeLoginUrl = payload.login_url;
    if (urlField) {
      urlField.value = payload.login_url;
    }
    if (wrap) {
      wrap.style.display = "";
    }
    if (status) {
      status.textContent = "OAuth-ссылка готова. Нажми “Получить код”, затем вставь код из браузера.";
    }
  } catch (error) {
    if (status) {
      status.textContent = `Ошибка: ${error.message}`;
    }
  }
}

function openClaudeLoginUrl() {
  const status = document.getElementById("claude-auth-status");
  const value = window.currentClaudeLoginUrl || document.getElementById("claude-login-url")?.value || "";
  if (!value) {
    if (status) {
      status.textContent = "OAuth-ссылка еще не готова.";
    }
    return;
  }
  window.open(value, "_blank", "noopener,noreferrer");
}

async function copyClaudeLoginUrl() {
  const status = document.getElementById("claude-auth-status");
  const urlField = document.getElementById("claude-login-url");
  const value = urlField?.value || "";
  if (!value) {
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
    if (status) {
      status.textContent = "OAuth-ссылка скопирована.";
    }
  } catch (error) {
    if (status) {
      status.textContent = `Ошибка копирования: ${error.message}`;
    }
  }
}

async function submitClaudeOAuthCode(event) {
  event.preventDefault();

  const status = document.getElementById("claude-auth-status");
  const code = document.getElementById("claude-login-code");
  const sessionId = window.currentClaudeLoginSessionId;
  if (!code || !sessionId) {
    if (status) {
      status.textContent = "Сначала получи OAuth-ссылку.";
    }
    return;
  }

  if (status) {
    status.textContent = "Передаю код в claude auth login...";
  }

  try {
    const response = await fetch("/api/claude-auth/login-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, code: code.value }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || payload.error || "Не удалось завершить Claude login");
    }
    code.value = "";
    window.currentClaudeLoginSessionId = null;
    if (status) {
      status.textContent = `Claude auth обновлен: ${payload.credentials_path}`;
    }
  } catch (error) {
    if (status) {
      status.textContent = `Ошибка: ${error.message}`;
    }
  }
}

window.triggerSync = triggerSync;
window.openScatterModal = openScatterModal;
window.closeScatterModal = closeScatterModal;
window.closePromptModal = closePromptModal;
window.initClaudeAuthPage = initClaudeAuthPage;
window.saveClaudeAuth = saveClaudeAuth;
window.startClaudeOAuth = startClaudeOAuth;
window.openClaudeLoginUrl = openClaudeLoginUrl;
window.copyClaudeLoginUrl = copyClaudeLoginUrl;
window.submitClaudeOAuthCode = submitClaudeOAuthCode;
window.copyPromptText = copyPromptText;
window.showTodayPrompt = showTodayPrompt;
window.showActivityPrompt = showActivityPrompt;
window.loadDetail = loadDetail;
window.switchChartMode = switchChartMode;
window.getAnalysis = getAnalysis;
window.refreshRecommendation = refreshRecommendation;
window.loadAllRunDetails = loadAllRunDetails;
window.changeRunsPage = changeRunsPage;
window.saveSettings = saveSettings;
