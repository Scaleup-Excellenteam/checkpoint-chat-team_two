function deriveWsBase() {
  if (window.WS_BASE) return String(window.WS_BASE).trim();
  if (window.API_BASE) {
    try {
      const u = new URL(String(window.API_BASE).trim());
      u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
      return u.origin;
    } catch {}
  }
  return "ws://localhost:8090";
}
const WS_BASE = deriveWsBase();

// true  -> /ws/<room>?token=...&nick=...
// false -> /ws?room=<room>&token=...&nick=...
const USE_PATH_STYLE = true;

const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS  = 5000;
const HEARTBEAT_MS      = 25000;

// ===== Auth & room state =====
const token    = localStorage.getItem("token");
const nickname = localStorage.getItem("nickname") || "anon";
const params   = new URLSearchParams(window.location.search);
const room     = params.get("room") || "lobby";

// Guard: must be authenticated
if (!token) window.location.replace("login.html");

// ===== DOM =====
const $title  = document.getElementById("title");
const $ud     = document.getElementById("userDisplay");
const $status = document.getElementById("status");
const $msgs   = document.getElementById("messages");
const $input  = document.getElementById("input");
const $send   = document.getElementById("sendBtn");

// Header
if ($ud)    $ud.textContent    = `👤 ${nickname}`;
if ($title) $title.textContent = `TSPO Chat — ${room}`;

// ===== UI helpers =====
function setConnected(on){
  // Be defensive if elements are missing
  if ($status) {
    $status.textContent = on ? "Connected" : "Disconnected";
    $status.classList.toggle("ok", !!on);
  }
  if ($input) $input.disabled = !on;
  if ($send)  $send.disabled  = !on;
}
function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]
  ));
}
function addSystem(msg){
  if (!$msgs) return;
  const li = document.createElement("li");
  li.className = "sys";
  li.textContent = `[system] ${msg}`;
  $msgs.appendChild(li);
  $msgs.scrollTop = $msgs.scrollHeight;
}
function addChat(nick, text){
  if (!$msgs) return;
  const li = document.createElement("li");
  li.className = "msg";
  li.innerHTML = `<strong>${escapeHtml(nick)}:</strong> ${escapeHtml(text)}`;
  $msgs.appendChild(li);
  $msgs.scrollTop = $msgs.scrollHeight;
}

// ===== Message parser (JSON or plain) =====
// Supports:
// 1) JSON: { type: "chat", nick, text } or { event: "pong" } or { type: "system", text }
// 2) Pipe-delimited: "room|nick|text" (from other minimal clients)
// 3) Bare text => system line
function parseIncoming(data) {
  // Try JSON first
  if (typeof data === "string") {
    try {
      const obj = JSON.parse(data);

      // Heartbeat "pong" (ignore in UI)
      if (obj && (obj.event?.toLowerCase() === "pong" || obj.type === "pong")) {
        return { kind: "heartbeat", event: "pong", text: "" };
      }

      // Chat shape
      if (obj && obj.type === "chat") {
        return {
          kind: "chat",
          nick: obj.nick || obj.nickname || "unknown",
          text: obj.text != null ? String(obj.text) : ""
        };
      }

      // System-ish events
      if (obj && (obj.type === "system" || obj.event)) {
        const txt =
          obj.text ||
          obj.message ||
          (obj.event ? String(obj.event) : "system");
        return { kind: "system", event: obj.event || "system", text: String(txt) };
      }
      // Unknown JSON -> stringify as system
      return { kind: "system", event: "json", text: data };
    } catch {
      // Not JSON, fall through
    }

    // Try legacy "room|nick|text"
    const parts = data.split("|");
    if (parts.length >= 3) {
      const nick = parts[1].slice(0, 64);
      const text = parts.slice(2).join("|");
      return { kind: "chat", nick, text };
    }

    // Plain text -> system
    return { kind: "system", event: "text", text: data };
  }

  // Non-string (e.g., Blob/Binary) -> system
  return { kind: "system", event: "binary", text: "[binary message]" };
}

// ===== WebSocket with reconnect, jitter & heartbeat =====
let ws = null;
let hbTimer = null;
let reconnectTimer = null;
let backoff = RECONNECT_BASE_MS;

function clearTimers() {
  if (hbTimer)       { clearInterval(hbTimer); hbTimer = null; }
  if (reconnectTimer){ clearTimeout(reconnectTimer); reconnectTimer = null; }
}

// Add small random jitter to avoid thundering herd
function withJitter(ms) {
  const jitter = Math.floor(Math.random() * 250); // 0..250ms
  return ms + jitter;
}

function scheduleReconnect() {
  clearTimers();
  backoff = Math.min(backoff * 2, RECONNECT_MAX_MS);
  reconnectTimer = setTimeout(connect, withJitter(backoff));
}

function wsUrlForRoom(roomName) {
  const q = new URLSearchParams();
  if (token)    q.set("token", token);
  if (nickname) q.set("nick", nickname);

  if (USE_PATH_STYLE) {
    // /ws/<room>?token=...&nick=...
    const qs = q.toString();
    return `${WS_BASE}/ws/${encodeURIComponent(roomName)}${qs ? "?" + qs : ""}`;
  } else {
    // /ws?room=<room>&token=...&nick=...
    q.set("room", roomName);
    return `${WS_BASE}/ws?${q.toString()}`;
  }
}

function connect(){
  // If browser is offline, wait until it's back
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    addSystem("offline, waiting for network…");
    window.addEventListener("online", connect, { once: true });
    return;
  }

  const url = wsUrlForRoom(room);
  try { ws?.close(); } catch {}
  clearTimers();

  ws = new WebSocket(url);

  ws.onopen = () => {
    setConnected(true);
    addSystem(`joined "${room}"`);
    backoff = RECONNECT_BASE_MS;

    // Heartbeat (ping) to keep connection alive
    hbTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        // Backend should answer with {event:"pong"} or {type:"pong"}
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, HEARTBEAT_MS);
  };

  ws.onmessage = (ev) => {
    const msg = parseIncoming(ev.data);

    // Ignore explicit heartbeat pongs
    if (msg.kind === "heartbeat") return;

    if (msg.kind === "chat") {
      addChat(msg.nick, msg.text);
    } else {
      // Show only meaningful system events; filter empty texts
      if (msg.text && msg.text.toLowerCase() !== "pong") {
        addSystem(msg.text);
      }
    }
  };

  ws.onclose = () => {
    setConnected(false);
    addSystem("connection closed");
    scheduleReconnect();
  };

  ws.onerror = () => {
    setConnected(false);
    addSystem("connection error");
    try { ws.close(); } catch {}
  };
}

// ===== Send handlers =====
function sendMessage(){
  const text = ($input?.value || "").trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

  // Backend expects JSON: {type:"chat", text}
  // If your server currently echoes raw strings, you can also send `${room}|${nickname}|${text}`
  ws.send(JSON.stringify({ type: "chat", text, nick: nickname, room }));
  if ($input) {
    $input.value = "";
    $input.focus();
  }
}

$send?.addEventListener("click", sendMessage);
$input?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Clean close on navigation
window.addEventListener("beforeunload", () => { try { ws?.close(1001); } catch {} });

// Reconnect immediately when network returns
window.addEventListener("online", () => {
  if (!ws || ws.readyState === WebSocket.CLOSED) connect();
});

// Go!
connect();