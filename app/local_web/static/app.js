const VIEW_QUERY = new URLSearchParams(window.location.search).get("view");
const VIEW_PATH =
  window.location.pathname === "/monitor"
    ? "monitor"
    : window.location.pathname === "/client"
      ? "client"
      : null;
const VIEW = VIEW_PATH || (VIEW_QUERY === "monitor" ? "monitor" : "client");
const DEVICE_NAME_STORAGE_KEY = "sinai_device_name_v3";
const SITE_NAME = "Sinai Local Node A-17";

const connectionPill = document.getElementById("connectionPill");
const healthPill = document.getElementById("healthPill");
const brandSubtitle = document.getElementById("brandSubtitle");

const monitorView = document.getElementById("monitorView");
const monitorMeta = document.getElementById("monitorMeta");
const sensorSourceBadge = document.getElementById("sensorSourceBadge");
const modeSwitch = document.getElementById("modeSwitch");
const monitorAssistantMode = document.getElementById("monitorAssistantMode");
const monitorDataMode = document.getElementById("monitorDataMode");
const monitorFeedList = document.getElementById("monitorFeedList");
const deviceList = document.getElementById("deviceList");
const activityList = document.getElementById("activityList");
const deviceCount = document.getElementById("deviceCount");
const queueCount = document.getElementById("queueCount");
const queueNext = document.getElementById("queueNext");
const queueList = document.getElementById("queueList");
const modelPhase = document.getElementById("modelPhase");
const modelProgressBar = document.getElementById("modelProgressBar");
const modelProgressText = document.getElementById("modelProgressText");
const sensorTimestamp = document.getElementById("sensorTimestamp");
const sensorFeedList = document.getElementById("sensorFeedList");
const sensorWarnings = document.getElementById("sensorWarnings");

const metricTemp = document.getElementById("metricTemp");
const metricHumidity = document.getElementById("metricHumidity");
const metricSoil = document.getElementById("metricSoil");
const metricLight = document.getElementById("metricLight");
const metricPressure = document.getElementById("metricPressure");
const metricEco2 = document.getElementById("metricEco2");
const metricTvoc = document.getElementById("metricTvoc");

const labelTemp = document.getElementById("labelTemp");
const labelHumidity = document.getElementById("labelHumidity");
const labelSoil = document.getElementById("labelSoil");
const labelLight = document.getElementById("labelLight");
const labelPressure = document.getElementById("labelPressure");
const labelAir = document.getElementById("labelAir");
const metricSource = document.getElementById("metricSource");

const sparkTemp = document.getElementById("sparkTemp");
const sparkHumidity = document.getElementById("sparkHumidity");
const sparkSoil = document.getElementById("sparkSoil");
const sparkLight = document.getElementById("sparkLight");
const sparkPressure = document.getElementById("sparkPressure");
const sparkEco2 = document.getElementById("sparkEco2");
const sparkTvoc = document.getElementById("sparkTvoc");

const clientView = document.getElementById("clientView");
const clientStatusText = document.getElementById("clientStatusText");
const clientChatLog = document.getElementById("clientChatLog");
const clientChatForm = document.getElementById("clientChatForm");
const clientInput = document.getElementById("clientInput");
const clientSendBtn = document.getElementById("clientSendBtn");
const clientTypingRow = document.getElementById("clientTypingRow");
const clientModeSelect = document.getElementById("clientModeSelect");
const clientRegionSelect = document.getElementById("clientRegionSelect");
const deviceChip = document.getElementById("deviceChip");
const clientQueueStatus = document.getElementById("clientQueueStatus");

const identityModal = document.getElementById("identityModal");
const deviceNameInput = document.getElementById("deviceNameInput");
const saveDeviceNameBtn = document.getElementById("saveDeviceNameBtn");

const state = {
  view: VIEW,
  sessionId: null,
  device: null,
  ws: null,
  wsRetryTimer: null,
  wsPingTimer: null,
  healthTimer: null,
  modelProgressTimer: null,
  monitorPollTimer: null,
  monitorMode: "assistant",
  feed: [],
  devices: [],
  sensorData: null,
  clientMessages: [],
  region: null,
  mode: "live",
  clientBusy: false,
  queue: {
    queued: 0,
    waiting: 0,
    processing: false,
    pending_total: 0,
    active: null,
    items: [],
    next_question: null,
    next_device_name: null,
  },
  modelProgress: null,
};

function setConnectionStatus(text, variant = "warn") {
  if (!connectionPill) return;
  connectionPill.textContent = text;
  connectionPill.dataset.variant = variant;
  if (clientStatusText) {
    clientStatusText.textContent =
      variant === "ok" ? "Connected to local Sinai node" : "Connection unstable, retrying";
  }
}

function setHealthStatus(text, ok = false) {
  if (!healthPill) return;
  healthPill.textContent = text;
  healthPill.dataset.variant = ok ? "ok" : "warn";
}

function formatTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtNumber(value, digits = 1) {
  if (value === null || value === undefined) return "--";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return "--";
  return numeric.toFixed(digits);
}

function setView() {
  if (monitorView) monitorView.classList.toggle("hidden", VIEW !== "monitor");
  if (clientView) clientView.classList.toggle("hidden", VIEW !== "client");
  if (!brandSubtitle) return;
  brandSubtitle.textContent =
    VIEW === "monitor"
      ? "Shared stage display for prompts, responses, and sensor intelligence"
      : "Phone controller for prompts and local response history";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      "Cache-Control": "no-store",
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed ${response.status}`);
  }
  return response.json();
}

async function refreshHealth() {
  try {
    const payload = await fetchJson("/api/health");
    const healthy = Boolean(payload.ok);
    setHealthStatus(payload.status_text || "Local AI ready", healthy);
  } catch {
    setHealthStatus("Local AI unavailable", false);
  }
}

function scheduleHealthChecks() {
  if (state.healthTimer) {
    clearInterval(state.healthTimer);
  }
  state.healthTimer = window.setInterval(() => {
    refreshHealth();
  }, 5000);
}

function sparklinePath(values, width, height) {
  const points = values
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
  if (points.length < 2) return "";

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = Math.max(max - min, 0.00001);
  const stepX = width / (points.length - 1);

  return points
    .map((value, index) => {
      const x = index * stepX;
      const y = height - ((value - min) / range) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

function renderSparkline(svg, values, color) {
  if (!svg) return;
  const width = 120;
  const height = 34;
  const path = sparklinePath(values || [], width, height);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!path) {
    svg.innerHTML = "";
    return;
  }
  svg.innerHTML = `<path d="${path}" stroke="${color}" stroke-width="2" fill="none" stroke-linecap="round" />`;
}

function initialsFromName(name) {
  const cleaned = (name || "").trim();
  if (!cleaned) return "?";
  const parts = cleaned.split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() || "").join("");
}

function renderMonitorFeed() {
  if (!monitorFeedList) return;
  monitorFeedList.innerHTML = "";
  const feed = (state.feed || []).slice(0, 50);

  if (feed.length === 0) {
    const li = document.createElement("li");
    li.className = "feed-row empty";
    li.textContent = "No prompts yet. Connect a local phone to begin.";
    monitorFeedList.appendChild(li);
    return;
  }

  for (const item of feed) {
    const li = document.createElement("li");
    const role = item.role === "assistant" ? "assistant" : "user";
    const deviceName = item.device_name || "Unknown device";
    const accent = item.device_color || "#4f9d7a";
    li.className = `feed-row ${role}`;
    li.style.setProperty("--device-accent", accent);
    li.innerHTML = `
      <div class="feed-row-top">
        <span class="event-type">${role === "assistant" ? "Reply" : "Prompt"}</span>
        <span class="event-name">${deviceName}</span>
        <span class="event-time">${formatTime(item.timestamp_utc)}</span>
      </div>
      <div class="event-text"></div>
    `;
    const content = li.querySelector(".event-text");
    if (content) {
      content.textContent = item.content || "";
    }
    monitorFeedList.appendChild(li);
  }
}

function renderDeviceList() {
  if (!deviceList || !activityList || !deviceCount || !monitorMeta) return;

  const devices = state.devices || [];
  const onlineCount = devices.filter((item) => item.connected).length;
  deviceCount.textContent = `${onlineCount} active`;
  monitorMeta.textContent = `${devices.length} known local devices | ${onlineCount} online`;

  deviceList.innerHTML = "";
  if (devices.length === 0) {
    const li = document.createElement("li");
    li.className = "device-row empty";
    li.textContent = "No devices joined yet.";
    deviceList.appendChild(li);
  } else {
    for (const device of devices) {
      const li = document.createElement("li");
      li.className = "device-row";
      const color = device.device_color || "#4f9d7a";
      const name = device.device_name || "Unknown";
      const status = device.connected
        ? "online"
        : `last seen ${formatTime(device.last_seen_utc)}`;

      li.innerHTML = `
        <span class="device-avatar">${initialsFromName(name)}</span>
        <div class="device-meta">
          <div class="device-name">${name}</div>
          <div class="device-status">${status}</div>
        </div>
        <div class="device-count">${device.message_count || 0}</div>
      `;
      const avatar = li.querySelector(".device-avatar");
      if (avatar) {
        avatar.style.backgroundColor = color;
      }
      deviceList.appendChild(li);
    }
  }

  activityList.innerHTML = "";
  const recent = (state.feed || []).slice(0, 7);
  if (recent.length === 0) {
    const li = document.createElement("li");
    li.className = "activity-row empty";
    li.textContent = "No recent events.";
    activityList.appendChild(li);
  } else {
    for (const item of recent) {
      const li = document.createElement("li");
      li.className = "activity-row";
      const action = item.role === "assistant" ? "reply" : "prompt";
      li.textContent = `${item.device_name || "Unknown"} - ${action} - ${formatTime(item.timestamp_utc)}`;
      activityList.appendChild(li);
    }
  }
}

function renderQueueStatus() {
  const queue = state.queue || {};
  const active = queue.active || null;
  const items = queue.items || [];
  const pending = Number(queue.pending_total || 0);
  const queued = Number(queue.queued || 0);
  const nextQuestion = queue.next_question || "";
  const nextDevice = queue.next_device_name || "";

  if (queueCount) {
    queueCount.textContent = `${pending} total`;
  }
  if (queueNext) {
    if (active) {
      queueNext.textContent = `Now answering: ${active.device_name || "Device"} - ${active.question || ""}`;
    } else if (nextQuestion) {
      queueNext.textContent = `Next: ${nextDevice || "Device"} - ${nextQuestion}`;
    } else {
      queueNext.textContent = "No queued prompts.";
    }
  }
  if (queueList) {
    queueList.innerHTML = "";
    if (active) {
      const li = document.createElement("li");
      li.className = "queue-row active";
      li.innerHTML = `
        <div class="queue-pos">#1</div>
        <div class="queue-text">
          <div class="queue-device">${active.device_name || "Device"} <span class="queue-live-pill">LIVE</span></div>
          <div class="queue-question"></div>
        </div>
      `;
      const q = li.querySelector(".queue-question");
      if (q) {
        q.textContent = active.question || "";
      }
      queueList.appendChild(li);
    }

    if (items.length === 0) {
      const li = document.createElement("li");
      li.className = "queue-row empty";
      li.textContent = active ? "No one waiting behind current prompt." : "Queue is empty.";
      queueList.appendChild(li);
    } else {
      items.forEach((item) => {
        const li = document.createElement("li");
        li.className = "queue-row";
        li.innerHTML = `
          <div class="queue-pos">#${item.position}</div>
          <div class="queue-text">
            <div class="queue-device">${item.device_name || "Device"}</div>
            <div class="queue-question"></div>
          </div>
        `;
        const q = li.querySelector(".queue-question");
        if (q) {
          q.textContent = item.question || "";
        }
        queueList.appendChild(li);
      });
    }
  }

  if (clientQueueStatus) {
    const mySessionId = state.sessionId || "";
    if (active && active.session_id === mySessionId) {
      clientQueueStatus.textContent = "Your prompt is being processed...";
      return;
    }
    const mine = items.find((item) => item.session_id === mySessionId);
    if (mine) {
      clientQueueStatus.textContent = `You are #${mine.position} in queue.`;
      return;
    }
    if (state.clientBusy && pending > 0) {
      clientQueueStatus.textContent = "Your prompt is being processed...";
    } else if (pending > 0) {
      clientQueueStatus.textContent = `${queued} waiting. Next: ${nextDevice || "Device"}`;
    } else {
      clientQueueStatus.textContent = "Queue ready.";
    }
  }
}

function renderModelProgress() {
  const progress = state.modelProgress || {};
  const phase = progress.phase || "unknown";
  const percent =
    progress.percent === null || progress.percent === undefined
      ? null
      : Math.max(0, Math.min(100, Number(progress.percent)));

  if (modelPhase) {
    modelPhase.textContent = phase.replaceAll("_", " ");
  }
  if (modelProgressBar) {
    modelProgressBar.style.width = `${Number.isFinite(percent) ? percent : 12}%`;
  }
  if (modelProgressText) {
    modelProgressText.textContent = progress.message || "Waiting for local model setup status.";
  }
}

async function refreshModelProgress() {
  try {
    state.modelProgress = await fetchJson("/api/ollama/progress");
  } catch {
    state.modelProgress = {
      phase: "unknown",
      percent: null,
      message: "Model setup status is temporarily unavailable.",
    };
  }
  renderModelProgress();
}

function scheduleModelProgressChecks() {
  if (state.modelProgressTimer) {
    clearInterval(state.modelProgressTimer);
  }
  state.modelProgressTimer = window.setInterval(() => {
    refreshModelProgress();
  }, 3000);
}

function applyMetricValue(element, valueText) {
  if (!element) return;
  element.textContent = valueText;
}

function renderSensorData() {
  if (!state.sensorData) return;

  const payload = state.sensorData.current ? state.sensorData : { current: state.sensorData };
  const current = payload.current || {};
  const readings = current.readings || {};
  const labels = current.labels || {};
  const series = payload.series || {};
  const bridge = current.bridge || {};

  if (sensorSourceBadge) {
    sensorSourceBadge.textContent = bridge.active
      ? `${bridge.device_name || "Arduino"} live`
      : `Source ${current.source || "--"}`;
  }
  if (sensorTimestamp) {
    sensorTimestamp.textContent = `Latest ${formatTime(current.timestamp_utc)} | ${current.source || "unknown"}`;
  }

  applyMetricValue(metricTemp, `${fmtNumber(readings.temperature_c, 1)} C`);
  applyMetricValue(metricHumidity, `${fmtNumber(readings.humidity_percent, 0)}%`);
  applyMetricValue(metricSoil, `${fmtNumber(readings.soil_moisture_pct, 0)}%`);
  applyMetricValue(metricLight, `${fmtNumber(readings.light_lux, 0)} lx`);
  applyMetricValue(metricPressure, `${fmtNumber(readings.pressure_hpa, 1)} hPa`);
  applyMetricValue(metricEco2, `${fmtNumber(readings.air_quality_eco2_ppm, 0)} ppm`);
  applyMetricValue(metricTvoc, `${fmtNumber(readings.air_quality_tvoc_ppb, 0)} ppb`);

  applyMetricValue(labelTemp, labels.temperature || "--");
  applyMetricValue(labelHumidity, labels.humidity || "--");
  applyMetricValue(labelSoil, labels.soil || "--");
  applyMetricValue(labelLight, labels.light || "--");
  applyMetricValue(labelPressure, labels.pressure_trend || "--");
  applyMetricValue(labelAir, labels.air_quality || "--");
  applyMetricValue(metricSource, current.source || "--");

  renderSparkline(sparkTemp, series.temperature_c || [], "#4f9d7a");
  renderSparkline(sparkHumidity, series.humidity_percent || [], "#c58f4a");
  renderSparkline(sparkSoil, series.soil_moisture_pct || [], "#6a8c6b");
  renderSparkline(sparkLight, series.light_lux || [], "#c06d4f");
  renderSparkline(sparkPressure, series.pressure_hpa || [], "#5b8ec6");
  renderSparkline(sparkEco2, series.air_quality_eco2_ppm || [], "#4aa3a0");
  renderSparkline(sparkTvoc, series.air_quality_tvoc_ppb || [], "#aa7b52");

  if (sensorWarnings) {
    sensorWarnings.innerHTML = "";
    const warnings = current.warnings || [];
    if (warnings.length === 0) {
      const li = document.createElement("li");
      li.className = "warning-row ok";
      li.textContent = "No high priority warnings.";
      sensorWarnings.appendChild(li);
    } else {
      warnings.slice(0, 4).forEach((warning) => {
        const li = document.createElement("li");
        li.className = "warning-row";
        li.textContent = warning;
        sensorWarnings.appendChild(li);
      });
    }
  }

  if (sensorFeedList) {
    sensorFeedList.innerHTML = "";
    const history = (payload.history || []).slice().reverse();
    if (history.length === 0) {
      const li = document.createElement("li");
      li.className = "sensor-event empty";
      li.textContent = "Waiting for readings...";
      sensorFeedList.appendChild(li);
    } else {
      history.forEach((frame) => {
        const li = document.createElement("li");
        li.className = "sensor-event";
        const line = frame.summary_line || "No sensor values available";
        li.innerHTML = `
          <div class="sensor-time">${formatTime(frame.timestamp_utc)}</div>
          <div class="sensor-line">${line}</div>
        `;
        sensorFeedList.appendChild(li);
      });
    }
  }
}

function updateMonitorMode(mode) {
  state.monitorMode = mode;
  document.querySelectorAll(".mode-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  if (monitorAssistantMode) {
    monitorAssistantMode.classList.toggle("active", mode === "assistant");
  }
  if (monitorDataMode) {
    monitorDataMode.classList.toggle("active", mode === "data");
  }
}

function renderClientMessages() {
  if (!clientChatLog) return;
  clientChatLog.innerHTML = "";
  for (const item of state.clientMessages) {
    const row = document.createElement("div");
    row.className = `chat-row ${item.role}`;

    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${item.role}`;

    const sender =
      item.role === "assistant"
        ? "Sinai"
        : item.device_name || state.device?.device_name || "You";

    bubble.innerHTML = `
      <div class="chat-meta">${sender} - ${formatTime(item.timestamp_utc)}</div>
      <div class="chat-text"></div>
    `;
    const text = bubble.querySelector(".chat-text");
    if (text) {
      text.textContent = item.content || "";
    }

    row.appendChild(bubble);
    clientChatLog.appendChild(row);
  }
  clientChatLog.scrollTop = clientChatLog.scrollHeight;
}

function setClientBusy(busy) {
  state.clientBusy = busy;
  if (clientSendBtn) clientSendBtn.disabled = busy;
  if (clientTypingRow) clientTypingRow.classList.toggle("hidden", !busy);
}

function resizeClientInput() {
  if (!clientInput) return;
  clientInput.style.height = "auto";
  const nextHeight = Math.min(clientInput.scrollHeight, 140);
  clientInput.style.height = `${Math.max(42, nextHeight)}px`;
}

function applyDeviceToChip(device) {
  if (!deviceChip || !device) return;
  deviceChip.textContent = `Device: ${device.device_name}`;
  deviceChip.style.setProperty("--device-color", device.device_color || "#4f9d7a");
}

async function fetchClientContextOptions() {
  try {
    const payload = await fetchJson(
      `/api/context?mode=${encodeURIComponent(state.mode)}&site_name=${encodeURIComponent(SITE_NAME)}&region=${encodeURIComponent(state.region || "")}`
    );

    const regions = payload.available_regions || [];
    clientRegionSelect.innerHTML = "";
    regions.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      clientRegionSelect.appendChild(option);
    });
    if (regions.length > 0) {
      const nextRegion = regions.includes(payload.region)
        ? payload.region
        : state.region && regions.includes(state.region)
          ? state.region
          : regions[0];
      state.region = nextRegion;
      clientRegionSelect.value = nextRegion;
    }
  } catch {
    // Keep existing options if temporary network error.
  }
}

async function fetchClientHistory() {
  try {
    const payload = await fetchJson("/api/history");
    state.clientMessages = payload.messages || [];
    renderClientMessages();
  } catch {
    // No-op, realtime should recover.
  }
}

async function sendClientMessage(rawText) {
  const message = (rawText || "").trim();
  if (!message || state.clientBusy) return;

  const optimistic = {
    role: "user",
    content: message,
    timestamp_utc: new Date().toISOString(),
    device_name: state.device?.device_name || "You",
  };
  state.clientMessages.push(optimistic);
  renderClientMessages();
  clientInput.value = "";
  resizeClientInput();
  setClientBusy(true);
  if (clientQueueStatus) {
    clientQueueStatus.textContent = "Submitting to queue...";
  }

  try {
    const payload = await fetchJson("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        mode: state.mode,
        region: state.region,
        site_name: SITE_NAME,
      }),
    });
    state.clientMessages = payload.history || state.clientMessages;
    if (payload.queue) {
      state.queue = {
        ...state.queue,
        ...payload.queue,
      };
      renderQueueStatus();
    }
    renderClientMessages();
  } catch {
    state.clientMessages.push({
      role: "assistant",
      content: "Local AI is temporarily unavailable. Please retry.",
      timestamp_utc: new Date().toISOString(),
      device_name: "Sinai",
    });
    renderClientMessages();
  } finally {
    setClientBusy(false);
    refreshHealth();
  }
}

function wsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  if (VIEW === "monitor") {
    return `${protocol}://${window.location.host}/ws/realtime?role=monitor`;
  }
  return `${protocol}://${window.location.host}/ws/realtime?role=client&session_id=${encodeURIComponent(state.sessionId || "")}`;
}

function clearRealtimeTimers() {
  if (state.wsRetryTimer) {
    clearTimeout(state.wsRetryTimer);
    state.wsRetryTimer = null;
  }
  if (state.wsPingTimer) {
    clearInterval(state.wsPingTimer);
    state.wsPingTimer = null;
  }
}

function scheduleWsReconnect() {
  if (state.wsRetryTimer) return;
  state.wsRetryTimer = window.setTimeout(() => {
    state.wsRetryTimer = null;
    connectRealtime();
  }, 1600);
}

function handleSocketEvent(payload) {
  const type = payload.type;

  if (type === "welcome") {
    if (payload.device && VIEW === "client") {
      state.device = payload.device;
      applyDeviceToChip(payload.device);
    }
    if (payload.devices) {
      state.devices = payload.devices;
      renderDeviceList();
    }
    if (payload.feed) {
      state.feed = payload.feed;
      renderMonitorFeed();
      renderDeviceList();
    }
    if (payload.data) {
      state.sensorData = payload.data;
      renderSensorData();
    }
    if (payload.queue) {
      state.queue = {
        ...state.queue,
        ...payload.queue,
      };
      renderQueueStatus();
    }
    return;
  }

  if (type === "chat_event") {
    if (VIEW === "monitor") {
      state.feed.unshift(payload.item);
      state.feed = state.feed.slice(0, 60);
      renderMonitorFeed();
      renderDeviceList();
      return;
    }

    if (VIEW === "client" && payload.item?.role === "assistant") {
      state.clientMessages.push(payload.item);
      state.clientMessages = state.clientMessages.slice(-40);
      renderClientMessages();
      setClientBusy(false);
      return;
    }
    return;
  }

  if (type === "device_snapshot") {
    state.devices = payload.devices || [];
    renderDeviceList();
    return;
  }

  if (type === "queue_status") {
    state.queue = {
      ...state.queue,
      ...payload,
    };
    renderQueueStatus();
    return;
  }

  if (type === "sensor_update") {
    if (payload.payload?.current) {
      state.sensorData = payload.payload;
      renderSensorData();
      return;
    }

    const current = payload.payload;
    if (!current) return;

    const history = state.sensorData?.history ? [...state.sensorData.history] : [];
    history.push(current);
    const trimmed = history.slice(-16);
    state.sensorData = {
      current,
      history: trimmed,
      series: state.sensorData?.series || {},
    };
    renderSensorData();
    return;
  }

  if (type === "snapshot") {
    state.feed = payload.feed || [];
    state.devices = payload.devices || [];
    state.sensorData = payload.data || null;
    if (payload.queue) {
      state.queue = {
        ...state.queue,
        ...payload.queue,
      };
    }
    renderMonitorFeed();
    renderDeviceList();
    renderSensorData();
    renderQueueStatus();
  }
}

function connectRealtime() {
  if (VIEW === "client" && !state.sessionId) return;
  clearRealtimeTimers();
  if (state.ws) {
    state.ws.close();
  }

  setConnectionStatus("Connecting realtime...", "warn");
  const socket = new WebSocket(wsUrl());
  state.ws = socket;

  socket.addEventListener("open", () => {
    setConnectionStatus("Realtime connected", "ok");
    state.wsPingTimer = window.setInterval(() => {
      if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send("ping");
      }
    }, 18000);
  });

  socket.addEventListener("message", (event) => {
    if (event.data === "pong") return;
    try {
      const payload = JSON.parse(event.data);
      handleSocketEvent(payload);
    } catch {
      // Ignore invalid payloads.
    }
  });

  socket.addEventListener("close", () => {
    clearRealtimeTimers();
    setConnectionStatus("Realtime reconnecting...", "warn");
    scheduleWsReconnect();
  });

  socket.addEventListener("error", () => {
    setConnectionStatus("Realtime reconnecting...", "warn");
  });
}

async function fetchMonitorSnapshots() {
  try {
    const [feedPayload, devicePayload, dataPayload, queuePayload] = await Promise.all([
      fetchJson("/api/live-feed?limit=40"),
      fetchJson("/api/devices"),
      fetchJson("/api/data/live"),
      fetchJson("/api/queue/status"),
    ]);
    state.feed = feedPayload.items || [];
    state.devices = devicePayload.devices || [];
    state.sensorData = dataPayload || null;
    state.queue = {
      ...state.queue,
      ...queuePayload,
    };
    renderMonitorFeed();
    renderDeviceList();
    renderSensorData();
    renderQueueStatus();
  } catch {
    // Monitor view recovers on next cycle.
  }
}

async function ensureClientIdentity() {
  const session = await fetchJson("/api/session");
  state.sessionId = session.session_id;
  state.device = session.device || null;

  const saveAndRegister = async (name) => {
    const response = await fetchJson("/api/device/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_name: name }),
    });
    state.device = response.device;
    localStorage.setItem(DEVICE_NAME_STORAGE_KEY, response.device.device_name);
    applyDeviceToChip(response.device);
  };

  const savedName = (localStorage.getItem(DEVICE_NAME_STORAGE_KEY) || "").trim();
  if (savedName) {
    await saveAndRegister(savedName);
    return;
  }

  identityModal.classList.remove("hidden");
  deviceNameInput.value = state.device?.device_name || "";
  deviceNameInput.focus();

  await new Promise((resolve) => {
    const submit = async () => {
      const name = deviceNameInput.value.trim();
      if (!name) return;
      try {
        await saveAndRegister(name);
        identityModal.classList.add("hidden");
        saveDeviceNameBtn.removeEventListener("click", submit);
        deviceNameInput.removeEventListener("keydown", enterHandler);
        resolve();
      } catch {
        // Keep modal open so user can retry.
      }
    };

    const enterHandler = (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      submit();
    };

    saveDeviceNameBtn.addEventListener("click", submit);
    deviceNameInput.addEventListener("keydown", enterHandler);
  });
}

function bindMonitorEvents() {
  if (!modeSwitch) return;
  modeSwitch.addEventListener("click", (event) => {
    const button = event.target.closest(".mode-btn");
    if (!button) return;
    updateMonitorMode(button.dataset.mode || "assistant");
  });
}

function bindClientEvents() {
  clientChatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendClientMessage(clientInput.value);
  });

  clientInput.addEventListener("keydown", async (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      await sendClientMessage(clientInput.value);
    }
  });

  clientInput.addEventListener("input", resizeClientInput);

  clientModeSelect.addEventListener("change", async () => {
    state.mode = clientModeSelect.value;
    await fetchClientContextOptions();
  });

  clientRegionSelect.addEventListener("change", () => {
    state.region = clientRegionSelect.value;
  });

  document.querySelectorAll(".quick-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      const prompt = button.dataset.prompt || "";
      await sendClientMessage(prompt);
    });
  });
}

async function initMonitor() {
  bindMonitorEvents();
  updateMonitorMode("assistant");
  await refreshModelProgress();
  await fetchMonitorSnapshots();
  connectRealtime();
  scheduleModelProgressChecks();
  if (state.monitorPollTimer) {
    clearInterval(state.monitorPollTimer);
  }
  state.monitorPollTimer = window.setInterval(() => {
    const disconnected = !state.ws || state.ws.readyState !== WebSocket.OPEN;
    if (disconnected) {
      fetchMonitorSnapshots();
    }
  }, 7000);
}

async function initClient() {
  bindClientEvents();
  await ensureClientIdentity();
  await fetchClientContextOptions();
  await fetchClientHistory();
  try {
    const queuePayload = await fetchJson("/api/queue/status");
    state.queue = {
      ...state.queue,
      ...queuePayload,
    };
    renderQueueStatus();
  } catch {
    // Ignore transient queue fetch failures.
  }
  resizeClientInput();
  connectRealtime();
}

async function bootstrap() {
  setView();
  await refreshHealth();
  scheduleHealthChecks();

  if (VIEW === "monitor") {
    await initMonitor();
  } else {
    await initClient();
  }
}

bootstrap();
