const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const typingRow = document.getElementById("typingRow");
const resetBtn = document.getElementById("resetBtn");
const modeSelect = document.getElementById("modeSelect");
const regionSelect = document.getElementById("regionSelect");
const statusWrap = document.getElementById("statusWrap");
const statusText = document.getElementById("statusText");

const contextSummary = document.getElementById("contextSummary");
const metricTemperature = document.getElementById("metricTemperature");
const metricLight = document.getElementById("metricLight");
const metricUv = document.getElementById("metricUv");
const metricPressure = document.getElementById("metricPressure");
const metricAir = document.getElementById("metricAir");
const metricSource = document.getElementById("metricSource");
const cropList = document.getElementById("cropList");
const riskList = document.getElementById("riskList");
const liveFeedList = document.getElementById("liveFeedList");
const liveFeedStatus = document.getElementById("liveFeedStatus");

const STORAGE_KEY = "sinai_chat_history_v1";
const LIVE_FEED_INTERVAL_MS = 2500;
const LIVE_FEED_LIMIT = 18;

let localMessages = [];
let currentContext = null;
let liveFeedTimer = null;

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function setBusy(isBusy) {
  sendBtn.disabled = isBusy;
  typingRow.classList.toggle("hidden", !isBusy);
}

function persistMessages(messages) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
}

function restoreMessages() {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((entry) => entry?.role && entry?.content);
  } catch {
    return [];
  }
}

function scrollChatToBottom() {
  chatLog.scrollTop = chatLog.scrollHeight;
}

function appendInlineText(parent, text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  parts.forEach((part) => {
    if (!part) return;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      const strong = document.createElement("strong");
      strong.textContent = part.slice(2, -2);
      parent.appendChild(strong);
      return;
    }
    parent.appendChild(document.createTextNode(part));
  });
}

function renderAssistantContent(target, content) {
  target.innerHTML = "";
  const wrapper = document.createElement("div");
  wrapper.className = "answer-content";
  const lines = (content || "").replace(/\r\n/g, "\n").split("\n");
  let paragraph = [];
  let list = null;

  const closeList = () => {
    list = null;
  };

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    const p = document.createElement("p");
    appendInlineText(p, paragraph.join(" "));
    wrapper.appendChild(p);
    paragraph = [];
  };

  const addLabel = (text) => {
    const p = document.createElement("p");
    p.className = "answer-label";
    appendInlineText(p, text.replace(/:$/, ""));
    wrapper.appendChild(p);
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      closeList();
      return;
    }

    const markdownLabel = line.match(/^#{1,4}\s+(.+)$/);
    const bullet = line.match(/^[-*]\s+(.+)$/);
    const numbered = line.match(/^\d+[\.)]\s+(.+)$/);
    const looksLikeLabel = line.endsWith(":") && line.length <= 64;

    if (markdownLabel || looksLikeLabel) {
      flushParagraph();
      closeList();
      addLabel(markdownLabel ? markdownLabel[1] : line);
      return;
    }

    if (bullet || numbered) {
      flushParagraph();
      const tagName = numbered ? "OL" : "UL";
      if (!list || list.tagName !== tagName) {
        list = document.createElement(numbered ? "ol" : "ul");
        wrapper.appendChild(list);
      }
      const li = document.createElement("li");
      appendInlineText(li, bullet ? bullet[1] : numbered[1]);
      list.appendChild(li);
      return;
    }

    closeList();
    paragraph.push(line);
  });

  flushParagraph();

  if (wrapper.childElementCount === 0) {
    wrapper.textContent = content || "";
  }

  target.appendChild(wrapper);
}

function messageRow(role, content) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  if (role === "assistant") {
    renderAssistantContent(bubble, content);
  } else {
    bubble.textContent = content;
  }
  row.appendChild(bubble);
  return { row, bubble };
}

function renderMessages(messages) {
  chatLog.innerHTML = "";
  messages.forEach((item) => {
    const { row } = messageRow(item.role, item.content);
    chatLog.appendChild(row);
  });
  scrollChatToBottom();
}

async function typeAssistantMessage(content) {
  const { row, bubble } = messageRow("assistant", "");
  chatLog.appendChild(row);
  const text = content || "";
  let output = "";
  for (let i = 0; i < text.length; i += 1) {
    output += text[i];
    bubble.textContent = output;
    if (i % 2 === 0) {
      await new Promise((resolve) => setTimeout(resolve, 8));
    }
    if (i % 18 === 0) {
      scrollChatToBottom();
    }
  }
  renderAssistantContent(bubble, text);
  scrollChatToBottom();
}

function resizeChatInput() {
  chatInput.style.height = "auto";
  const nextHeight = Math.min(chatInput.scrollHeight, 132);
  chatInput.style.height = `${nextHeight}px`;
  chatInput.style.overflowY = chatInput.scrollHeight > 132 ? "auto" : "hidden";
}

function shortSessionId(sessionId) {
  if (!sessionId) return "unknown";
  return sessionId.slice(0, 8);
}

function formatLocalTime(timestampUtc) {
  if (!timestampUtc) return "--";
  const date = new Date(timestampUtc);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function renderLiveFeed(entries) {
  if (!liveFeedList) return;
  liveFeedList.innerHTML = "";

  if (!Array.isArray(entries) || entries.length === 0) {
    const li = document.createElement("li");
    li.className = "feed-item empty";
    li.textContent = "No prompts yet. Phones can join and ask now.";
    liveFeedList.appendChild(li);
    if (liveFeedStatus) {
      liveFeedStatus.textContent = "Waiting for network activity...";
    }
    return;
  }

  entries.forEach((entry) => {
    const item = document.createElement("li");
    item.className = `feed-item ${entry.role || "unknown"}`;

    const meta = document.createElement("div");
    meta.className = "feed-meta";
    const roleLabel = entry.role === "assistant" ? "reply" : "prompt";
    meta.textContent = `${roleLabel} · ${shortSessionId(entry.session_id)} · ${formatLocalTime(entry.timestamp_utc)}`;

    const content = document.createElement("div");
    content.className = "feed-content";
    content.textContent = entry.content || "";

    item.appendChild(meta);
    item.appendChild(content);
    liveFeedList.appendChild(item);
  });

  if (liveFeedStatus) {
    liveFeedStatus.textContent = `Live across all connected sessions (${entries.length} recent events).`;
  }
}

async function fetchLiveFeed() {
  if (!liveFeedList) return;
  try {
    const response = await fetch(`/api/live-feed?limit=${LIVE_FEED_LIMIT}`);
    if (!response.ok) throw new Error("Live feed request failed.");
    const payload = await response.json();
    renderLiveFeed(payload.items || []);
  } catch {
    if (liveFeedStatus) {
      liveFeedStatus.textContent = "Live feed unavailable right now.";
    }
  }
}

function renderContext(context) {
  currentContext = context;
  const labels = context.labels || {};
  contextSummary.textContent = context.summary || "No context summary available.";
  metricTemperature.textContent = labels.temperature || "--";
  metricLight.textContent = labels.light || "--";
  metricUv.textContent = labels.uv || "--";
  metricPressure.textContent = labels.pressure_trend || "--";
  metricAir.textContent = labels.air_quality || "--";
  metricSource.textContent = context.source || "--";

  const regions = context.available_regions || [];
  const currentRegion = context.region || "";
  if (regions.length > 0) {
    regionSelect.innerHTML = "";
    regions.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      regionSelect.appendChild(opt);
    });
    regionSelect.value = regions.includes(currentRegion) ? currentRegion : regions[0];
  }

  const crops = context.top_crops || [];
  cropList.innerHTML = "";
  if (crops.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No crop ranking available yet.";
    cropList.appendChild(li);
  } else {
    crops.slice(0, 4).forEach((crop) => {
      const li = document.createElement("li");
      li.innerHTML = `<strong>${escapeHtml(crop.name)}</strong> - score ${crop.score}/100, ${crop.time_to_harvest_days}d harvest`;
      cropList.appendChild(li);
    });
  }

  const risks = context.risk_flags || [];
  riskList.innerHTML = "";
  risks.forEach((risk) => {
    const li = document.createElement("li");
    li.textContent = risk;
    riskList.appendChild(li);
  });
}

async function fetchHealth() {
  try {
    const response = await fetch("/api/health");
    const payload = await response.json();
    statusText.textContent = payload.status_text || "Status unavailable.";
    statusWrap.classList.remove("ok", "warn");
    statusWrap.classList.add(payload.ok ? "ok" : "warn");
  } catch {
    statusText.textContent = "Cannot reach local AI endpoint.";
    statusWrap.classList.remove("ok");
    statusWrap.classList.add("warn");
  }
}

async function fetchContext() {
  const params = new URLSearchParams({
    mode: modeSelect.value,
    region: regionSelect.value || "",
    site_name: "Sinai Local Node A-17",
  });
  const response = await fetch(`/api/context?${params.toString()}`);
  if (!response.ok) throw new Error("Could not load context.");
  const payload = await response.json();
  renderContext(payload);
}

async function syncHistoryFromServer() {
  try {
    const response = await fetch("/api/history");
    const payload = await response.json();
    if (Array.isArray(payload.messages) && payload.messages.length > 0) {
      localMessages = payload.messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      persistMessages(localMessages);
      renderMessages(localMessages);
      return;
    }
  } catch {
    // Fall back to sessionStorage below.
  }

  localMessages = restoreMessages();
  if (localMessages.length === 0) {
    localMessages = [
      {
        role: "assistant",
        content:
          "Sinai is online. Ask me about crop suitability, risk preparedness, and resilient food-system actions for current local conditions.",
      },
    ];
  }
  persistMessages(localMessages);
  renderMessages(localMessages);
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message) return;

  localMessages.push({ role: "user", content: message });
  persistMessages(localMessages);
  renderMessages(localMessages);
  chatInput.value = "";
  resizeChatInput();
  setBusy(true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        mode: modeSelect.value,
        region: regionSelect.value || null,
        site_name: "Sinai Local Node A-17",
      }),
    });

    if (!response.ok) {
      throw new Error("Chat request failed.");
    }

    const payload = await response.json();
    if (payload.context) {
      renderContext(payload.context);
    }
    if (payload.history && Array.isArray(payload.history)) {
      localMessages = payload.history.map((item) => ({
        role: item.role,
        content: item.content,
      }));
      persistMessages(localMessages);
      // Render all except last assistant so we can type it in.
      const withoutLast = [...localMessages];
      const last = withoutLast.pop();
      renderMessages(withoutLast);
      if (last && last.role === "assistant") {
        await typeAssistantMessage(last.content);
      } else {
        renderMessages(localMessages);
      }
    } else {
      const reply = payload.reply || "No reply returned.";
      localMessages.push({ role: "assistant", content: reply });
      persistMessages(localMessages);
      renderMessages(localMessages.slice(0, -1));
      await typeAssistantMessage(reply);
    }
  } catch {
    const fallback =
      "I could not reach the assistant service. Please check that the server and Ollama are running.";
    localMessages.push({ role: "assistant", content: fallback });
    persistMessages(localMessages);
    renderMessages(localMessages);
  } finally {
    setBusy(false);
    await fetchLiveFeed();
    await fetchHealth();
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendMessage(chatInput.value);
});

chatInput.addEventListener("keydown", async (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    await sendMessage(chatInput.value);
  }
});

chatInput.addEventListener("input", resizeChatInput);

document.querySelectorAll(".quick-btn").forEach((button) => {
  button.addEventListener("click", async () => {
    const prompt = button.dataset.prompt || "";
    await sendMessage(prompt);
  });
});

resetBtn.addEventListener("click", async () => {
  try {
    await fetch("/api/reset", { method: "POST" });
  } catch {
    // Keep local reset even if request fails.
  }
  localMessages = [
    {
      role: "assistant",
      content:
        "Session reset complete. Ask Sinai anything about current conditions, risk, preparedness, or resilience planning.",
    },
  ];
  persistMessages(localMessages);
  renderMessages(localMessages);
  resizeChatInput();
  chatInput.focus();
});

modeSelect.addEventListener("change", async () => {
  await fetchContext();
});

regionSelect.addEventListener("change", async () => {
  await fetchContext();
});

async function bootstrap() {
  await fetchHealth();
  await fetchContext();
  await syncHistoryFromServer();
  await fetchLiveFeed();
  if (liveFeedTimer) {
    clearInterval(liveFeedTimer);
  }
  liveFeedTimer = window.setInterval(() => {
    fetchLiveFeed();
  }, LIVE_FEED_INTERVAL_MS);
  resizeChatInput();
  chatInput.focus();
}

bootstrap();
