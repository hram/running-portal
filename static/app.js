let dashboardChart = null;
let detailChart = null;
let efChart = null;
let efDetailChart = null;
let currentActivity = null;
let currentDetails = null;
let currentSettings = null;
let runsPage = 0;
const RUNS_PAGE_SIZE = 10;
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

function formatShortDate(isoString) {
  if (!isoString) {
    return "—";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
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
    <article class="metric">
      <p class="metric-label">${label}</p>
      <p class="metric-value">${value}</p>
      <div class="metric-sub">${subtext || "&nbsp;"}</div>
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
  await renderProgressCard();
  renderDistanceChart(activities.slice(0, 20).reverse());
  await loadRunsPage(0);
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

function renderDistanceChart(activities) {
  const canvas = document.getElementById("dist-chart");
  if (!canvas || !window.Chart) {
    return;
  }

  if (dashboardChart) {
    dashboardChart.destroy();
  }

  const labels = activities.map((item) => formatShortDate(item.date));
  const visibleTickIndexes = new Set();
  if (labels.length) {
    const anchors = [0, Math.floor((labels.length - 1) * 0.25), Math.floor((labels.length - 1) * 0.5), Math.floor((labels.length - 1) * 0.75), labels.length - 1];
    anchors.forEach((index) => visibleTickIndexes.add(index));
  }

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
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        x: {
          ticks: {
            color: "#9b9b96",
            autoSkip: false,
            callback(value, index) {
              return visibleTickIndexes.has(index) ? labels[index] : "";
            },
          },
          grid: { display: false },
        },
        y: { ticks: { color: "#9b9b96" }, grid: { color: "rgba(255,255,255,0.08)" } },
      },
    },
  });
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
  const script = document.getElementById("activity-data");
  if (!script) {
    return;
  }
  const settingsScript = document.getElementById("settings-data");

  currentActivity = JSON.parse(script.textContent);
  currentSettings = settingsScript ? JSON.parse(settingsScript.textContent) : null;
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
    currentDetails = payload.details.raw_detail || payload.details;
    renderDetailChart(currentDetails);
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

function renderDetailChart(details) {
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

  const baseTime = samples[0].start_time || samples[0].timestamp || 0;
  const labels = samples.map((sample) => {
    const t = sample.start_time || sample.timestamp || baseTime;
    return Math.max(0, Math.round((t - baseTime) / 60));
  });
  const maxMinutes = labels[labels.length - 1] || 0;
  const heartRate = samples.map((sample) => sample.heart_rate);
  const speed = trackPoints.length
    ? trackPoints.slice(0, labels.length).map((point) => point.speed_mps ? Number((point.speed_mps * 3.6).toFixed(2)) : null)
    : samples.map((sample) => sample.speed_mps ? Number((sample.speed_mps * 3.6).toFixed(2)) : null);
  const ef = labels.map((_, index) => {
    const hr = heartRate[index];
    const speedKmh = speed[index];
    if (!hr || !speedKmh) {
      return null;
    }
    const speedMpm = speedKmh * 1000 / 60;
    return Number((speedMpm / hr).toFixed(3));
  });
  const zoneLowValue = Number(currentSettings?.target_hr_zone_low ?? 140);
  const zoneHighValue = Number(currentSettings?.target_hr_zone_high ?? 160);
  const zoneLow = labels.map(() => zoneLowValue);
  const zoneHigh = labels.map(() => zoneHighValue);

  if (labelsRoot) {
    const anchors = [0, Math.floor(maxMinutes * 0.25), Math.floor(maxMinutes * 0.5), Math.floor(maxMinutes * 0.75), maxMinutes];
    const uniqueAnchors = [...new Set(anchors)];
    labelsRoot.innerHTML = uniqueAnchors.map((minute) => `<span>${minute} м</span>`).join("");
  }

  detailChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Пульс",
          data: heartRate,
          borderColor: "#b54444",
          backgroundColor: "rgba(181,68,68,0.08)",
          yAxisID: "y",
          tension: 0.22,
        },
        {
          label: "Скорость км/ч",
          data: speed,
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
      labels,
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
    currentDetails = payload.details.raw_detail || payload.details;
    renderDetailChart(currentDetails);
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

async function loadCachedAnalysis() {
  const activityId = document.getElementById("activity-id")?.value;
  const resultEl = document.getElementById("ai-result");
  const cachedBadge = document.getElementById("ai-cached-badge");
  const refreshBtn = document.getElementById("refresh-btn");

  if (!activityId || !resultEl || !cachedBadge || !refreshBtn) {
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
      resultEl.textContent = data.analysis;
      resultEl.style.display = "block";
      cachedBadge.style.display = "inline-block";
      refreshBtn.style.display = "inline-block";
    }
  } catch (error) {
    // Ignore cache lookup errors on initial page load.
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
