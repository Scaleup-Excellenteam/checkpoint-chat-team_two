// ===== Config =====
const WS_BASE = window.WS_BASE || "ws://localhost:8080"; // backend ws base (no /ws suffix)
const RECONNECT_BASE_MS = 500;   // initial backoff
const RECONNECT_MAX_MS  = 5000;  // cap backoff
const HEARTBEAT_MS      = 25000; // ping interval

// ===== Auth & room state =====
const token    = localStorage.getItem("token");
const nickname = localStorage.getItem("nickname") || "anon";

// Prefer room from URL (?room=NAME); fallback to 'lobby'
const params = new URLSearchParams(window.location.search);
const room   = params.get("room") || "lobby";

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
  $status.textContent = on ? "Connected" : "Disconnected";
  $status.classList.toggle("ok", !!on);
  $input.disabled = !on;
  $send.disabled  = !on;
}
function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]
  ));
}
function addSystem(msg){
  const li = document.createElement("li");
  li.className = "sys";
  li.textContent = `[system] ${msg}`;
  $msgs.appendChild(li);
  $msgs.scrollTop = $msgs.scrollHeight;
}
function addChat(nick, text){
  const li = document.createElement("li");
  li.className = "msg";
  li.innerHTML = `<strong>${escapeHtml(nick)}:</strong> ${escapeHtml(text)}`;
  $msgs.appendChild(li);
  $msgs.scrollTop = $msgs.scrollHeight;
}

// ===== Message parser (unified) =====
function parseIncoming(raw) {
  try {
    const data = JSON.parse(raw);

    // chat envelope {type:"chat", nickname, text}
    if (data && data.type === "chat") {
      return {
        kind: "chat",
        nick: data.nickname || "anon",
        text: data.text ?? data.message ?? ""
      };
    }

    // system envelope {type:"system", event, nickname}
    if (data && data.type === "system") {
      const who = data.nickname ? ` ${data.nickname}` : "";
      const evt = data.event ? `${data.event}${who}` : JSON.stringify(data);
      return { kind: "system", text: evt };
    }

    // unknown JSON → show raw
    return { kind: "system", text: raw };
  } catch {
    // not JSON → show raw
    return { kind: "system", text: raw };
  }
}

// ===== WebSocket with reconnect & heartbeat =====
let ws = null;
let hbTimer = null;
let reconnectTimer = null;
let backoff = RECONNECT_BASE_MS;

function clearTimers() {
  if (hbTimer)      { clearInterval(hbTimer); hbTimer = null; }
  if (reconnectTimer){ clearTimeout(reconnectTimer); reconnectTimer = null; }
}

function scheduleReconnect() {
  clearTimers();
  backoff = Math.min(backoff * 2, RECONNECT_MAX_MS);
  reconnectTimer = setTimeout(connect, backoff);
}

function connect(){
  const url = `${WS_BASE}/ws?room=${encodeURIComponent(room)}&token=${encodeURIComponent(token)}`;
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
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, HEARTBEAT_MS);
  };

  ws.onmessage = (ev) => {
    const msg = parseIncoming(ev.data);
    if (msg.kind === "chat") {
      addChat(msg.nick, msg.text);   // <-- only "nick: text"
    } else {
      addSystem(msg.text);
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
  const text = ($input.value || "").trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

  // Backend expects {type:"chat", text}
  ws.send(JSON.stringify({ type: "chat", text }));
  $input.value = "";
  $input.focus();
}

$send.addEventListener("click", sendMessage);
$input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Ensure clean close on navigation
window.addEventListener("beforeunload", () => { try { ws?.close(1001); } catch {} });

// Go!
connect();
