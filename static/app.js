let dashboardChart = null;
let detailChart = null;
let currentActivity = null;
let currentDetails = null;
const STATUS_LABELS = {
  run: "🏃 Бежать",
  run_easy: "🚶 Бежать легко",
  rest: "😴 Отдыхать",
};

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
    <article class="metric-card">
      <p class="metric-label">${label}</p>
      <p class="metric-value">${value}</p>
      <div class="metric-subtext">${subtext || "&nbsp;"}</div>
    </article>
  `;
}

async function initDashboard() {
  await loadTodayRecommendation();
  const response = await fetch("/api/activities?limit=100");
  const payload = await response.json();
  const activities = payload.activities || [];

  renderDashboardMetrics(activities);
  renderDashboardAlerts(activities);
  renderDistanceChart(activities.slice(0, 20).reverse());
  renderRunsTable(activities.slice(0, 20));
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
  const latestLabel = `${formatDate(latest.date)} · ${Number(latest.distance_km).toFixed(2)} км`;
  const avgHrRuns = activities.slice(0, 7).filter((item) => item.avg_hrm);
  const avgHr = avgHrRuns.length
    ? Math.round(avgHrRuns.reduce((sum, item) => sum + item.avg_hrm, 0) / avgHrRuns.length)
    : null;
  const maxDistance = activities.reduce((max, item) => Math.max(max, item.distance_km || 0), 0);

  root.innerHTML = [
    metricCard("Последняя пробежка", latestLabel, "Последняя запись в базе"),
    metricCard("Всего пробежек", String(activities.length), "Количество синхронизированных записей"),
    metricCard("Средний пульс", avgHr ? `${avgHr} bpm` : "—", "Среднее за последние 7 пробежек"),
    metricCard("Личный рекорд", `${maxDistance.toFixed(2)} км`, "Максимальная дистанция"),
  ].join("");
}

function renderDashboardAlerts(activities) {
  const root = document.getElementById("alerts");
  if (!root) {
    return;
  }
  if (!activities.length) {
    root.innerHTML = '<div class="alert alert-warning">Нет данных для анализа алертов.</div>';
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

  root.innerHTML = alerts.map((item) => `<div class="alert ${item.cls}">${item.text}</div>`).join("");
}

function renderDistanceChart(activities) {
  const canvas = document.getElementById("distance-chart");
  if (!canvas || !window.Chart) {
    return;
  }

  if (dashboardChart) {
    dashboardChart.destroy();
  }

  dashboardChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: activities.map((item) => formatDate(item.date)),
      datasets: [
        {
          label: "Дистанция, км",
          data: activities.map((item) => item.distance_km),
          backgroundColor: "rgba(55, 138, 221, 0.72)",
          borderRadius: 8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        x: { ticks: { color: "#9b9b96" }, grid: { display: false } },
        y: { ticks: { color: "#9b9b96" }, grid: { color: "rgba(255,255,255,0.08)" } },
      },
    },
  });
}

function renderRunsTable(activities) {
  const body = document.getElementById("runs-table-body");
  if (!body) {
    return;
  }

  if (!activities.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty-message">Пробежек пока нет.</td></tr>';
    return;
  }

  body.innerHTML = activities.map((item) => {
    const pace = formatPace(item.avg_pace);
    const recovery = item.recover_time !== null && item.recover_time !== undefined
      ? `${Math.round(item.recover_time / 60)} ч`
      : "—";
    return `
      <tr>
        <td><a class="run-link" href="/activity/${encodeURIComponent(item.activity_id)}">${formatDate(item.date)}</a></td>
        <td>${Number(item.distance_km).toFixed(2)} км</td>
        <td style="color:${hrColor(item.avg_hrm)}">${item.avg_hrm ?? "—"}</td>
        <td>${pace}</td>
        <td>${item.train_load ?? "—"}</td>
        <td>${recovery}</td>
      </tr>
    `;
  }).join("");
}

async function initDetailPage(activityId) {
  const script = document.getElementById("activity-data");
  if (!script) {
    return;
  }

  currentActivity = JSON.parse(script.textContent);
  currentDetails = null;

  const activityDate = document.getElementById("detail-date-title");
  const distanceTitle = document.getElementById("detail-distance-title");
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
    currentDetails = payload.details.raw_detail || payload.details;
    renderDetailChart(currentDetails);
    setDetailStatus("Детали уже доступны");
    const button = document.getElementById("load-detail-btn");
    if (button) {
      button.textContent = "Обновить детали";
    }
  } else {
    setDetailStatus("Детали ещё не загружены");
  }
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
    metricCard("Восстановление", formatHours(Math.round((activity.recover_time || 0) / 60)), "Прогноз восстановления"),
  ].join("");
}

function renderZoneBars(activity) {
  const root = document.getElementById("zone-bars");
  if (!root) {
    return;
  }

  const zones = [
    { label: "Жиросжигание", value: activity.hrm_fat_burning_duration || 0, color: "var(--blue)" },
    { label: "Аэробная", value: activity.hrm_aerobic_duration || 0, color: "var(--green)" },
    { label: "Анаэробная", value: activity.hrm_anaerobic_duration || 0, color: "var(--amber)" },
    { label: "Экстремальная", value: activity.hrm_extreme_duration || 0, color: "var(--red)" },
  ];

  const total = zones.reduce((sum, zone) => sum + zone.value, 0) || 1;
  root.innerHTML = zones.map((zone) => {
    const percent = Math.round((zone.value / total) * 100);
    return `
      <div class="zone-row">
        <div class="zone-label">${zone.label}</div>
        <div class="zone-track">
          <div class="zone-bar" style="width:${percent}%; background:${zone.color}"></div>
        </div>
        <div class="zone-value">${percent}%</div>
      </div>
    `;
  }).join("");
}

function renderDetailChart(details) {
  const canvas = document.getElementById("detail-chart");
  if (!canvas || !window.Chart) {
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

  const baseTime = samples[0].start_time || samples[0].timestamp || 0;
  const labels = samples.map((sample) => {
    const t = sample.start_time || sample.timestamp || baseTime;
    return Math.max(0, Math.round((t - baseTime) / 60));
  });
  const heartRate = samples.map((sample) => sample.heart_rate);
  const speed = trackPoints.length
    ? trackPoints.slice(0, labels.length).map((point) => point.speed_mps ? Number((point.speed_mps * 3.6).toFixed(2)) : null)
    : samples.map((sample) => sample.speed_mps ? Number((sample.speed_mps * 3.6).toFixed(2)) : null);
  const zoneLow = labels.map(() => 140);
  const zoneHigh = labels.map(() => 160);

  detailChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Пульс",
          data: heartRate,
          borderColor: "#e24b4a",
          backgroundColor: "rgba(226, 75, 74, 0.2)",
          yAxisID: "y",
          tension: 0.22,
        },
        {
          label: "Скорость км/ч",
          data: speed,
          borderColor: "#378add",
          borderDash: [8, 6],
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
          label: "Зона 140–160",
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
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          title: { display: true, text: "Минуты" },
          ticks: { color: "#9b9b96" },
          grid: { color: "rgba(255,255,255,0.05)" },
        },
        y: {
          position: "left",
          ticks: { color: "#9b9b96" },
          grid: { color: "rgba(255,255,255,0.08)" },
        },
        y1: {
          position: "right",
          ticks: { color: "#9b9b96" },
          grid: { drawOnChartArea: false },
        },
      },
      plugins: {
        legend: {
          labels: { color: "#e8e6de" },
        },
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
    currentDetails = payload.details.raw_detail || payload.details;
    renderDetailChart(currentDetails);
    setDetailStatus("Детали загружены");
  } catch (error) {
    setDetailStatus(error.message);
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
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

    if (!data.status) {
      document.getElementById("today-status").textContent = "Нет данных";
      document.getElementById("today-message").textContent =
        'Нажми "Синхронизировать" чтобы получить рекомендацию.';
      return;
    }

    card.className = `today-card today-card--${data.status}`;
    document.getElementById("today-icon").textContent =
      data.status === "run" ? "🏃" : data.status === "run_easy" ? "🚶" : "😴";
    document.getElementById("today-status").textContent =
      STATUS_LABELS[data.status] || data.status;
    document.getElementById("today-message").textContent = data.message;
  } catch (error) {
    document.getElementById("today-status").textContent = "Ошибка загрузки";
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
    await fetch("/api/ai/recommendation/refresh", { method: "POST" });
    await loadTodayRecommendation();
  } catch (error) {
    document.getElementById("today-status").textContent = "Ошибка";
  }
}

async function getAnalysis(forceRefresh = false) {
  const activityId = document.getElementById("activity-id")?.value;
  if (!activityId) {
    return;
  }

  const resultEl = document.getElementById("ai-result");
  const loadingEl = document.getElementById("ai-loading");
  const controlsEl = document.getElementById("ai-controls");
  const cachedBadge = document.getElementById("ai-cached-badge");
  const refreshBtn = document.getElementById("refresh-btn");

  if (!resultEl || !loadingEl || !controlsEl || !cachedBadge || !refreshBtn) {
    return;
  }

  if (!forceRefresh) {
    const res = await fetch("/api/ai/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ activity_id: activityId, force_refresh: false }),
    });
    const data = await res.json();
    if (data.cached && data.analysis) {
      resultEl.textContent = data.analysis;
      resultEl.style.display = "block";
      cachedBadge.style.display = "inline-block";
      refreshBtn.style.display = "inline-block";
      return;
    }
  }

  resultEl.textContent = "";
  resultEl.style.display = "block";
  loadingEl.style.display = "block";
  controlsEl.style.display = "none";
  cachedBadge.style.display = "none";

  const url = `/api/ai/analyze/stream?activity_id=${encodeURIComponent(activityId)}`;
  const source = new EventSource(url);

  source.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.error) {
      resultEl.textContent = "Ошибка: " + data.error;
      loadingEl.style.display = "none";
      controlsEl.style.display = "block";
      source.close();
      return;
    }
    if (data.chunk) {
      resultEl.textContent += data.chunk;
    }
    if (data.done) {
      loadingEl.style.display = "none";
      controlsEl.style.display = "block";
      refreshBtn.style.display = "inline-block";
      source.close();
    }
  };

  source.onerror = () => {
    loadingEl.style.display = "none";
    controlsEl.style.display = "block";
    resultEl.textContent += "\n[Соединение прервано]";
    source.close();
  };
}
