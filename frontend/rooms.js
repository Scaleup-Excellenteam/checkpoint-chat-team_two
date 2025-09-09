// ===== Config =====
const API = (window.API_BASE && String(window.API_BASE).trim()) || "http://localhost:8090";

// ===== Small helpers =====
function toast(msg, isError = false){
  const el = document.getElementById('toast');
  if(!el) return;
  el.textContent = msg;
  el.style.background = isError ? '#ff4d4f' : '#4caf50';
  el.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(()=> el.classList.remove('show'), 1800);
}
function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]
  ));
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// ===== Auth state (from login/register) =====
const token    = localStorage.getItem('token');
const nickname = localStorage.getItem('nickname') || 'anon';
const userId   = localStorage.getItem('user_id');

// If no token → force login (comment out if backend doesn't require auth)
if(!token){
  window.location.replace('login.html');
}

// Greet bar
const whoEl   = document.getElementById('who');
const greetEl = document.getElementById('greet');
if (whoEl)   whoEl.textContent   = `Signed in as ${nickname}`;
if (greetEl) greetEl.textContent = 'Rooms';

// Logout
document.getElementById('logoutBtn')?.addEventListener('click', ()=>{
  localStorage.removeItem('token');
  localStorage.removeItem('nickname');
  localStorage.removeItem('user_id');
  window.location.replace('login.html');
});

// ===== DOM refs =====
const listEl  = document.getElementById('rooms-list');
const formEl  = document.getElementById('create-room-form');
const inputEl = document.getElementById('room-name');

// Build fetch init with optional auth header
function withAuth(init = {}){
  const headers = new Headers(init.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return { ...init, headers };
}

// Parse backend error nicely
async function parseError(res){
  try {
    const j = await res.json();
    if (typeof j?.detail === 'string') return j.detail;
    if (Array.isArray(j?.errors) && j.errors[0]?.message) return j.errors[0].message;
  } catch {}
  try { const t = await res.text(); if (t) return t; } catch {}
  return 'Request failed';
}

// ===== Load & render rooms =====
async function loadRooms(){
  try{
    // GET /rooms -> { rooms: { "<name>": <count>, ... } }  OR  [{name,count}]
    const res = await fetch(`${API}/rooms`, withAuth({ method:'GET' }));
    if(!res.ok) throw new Error(await parseError(res));
    const data = await res.json();

    let entries = [];
    if (Array.isArray(data)) {
      // backend returns list
      entries = data.map(r => [r.name, r.count ?? 0]);
    } else if (data && typeof data === 'object') {
      // backend returns { rooms: {...} }
      const obj = data.rooms || {};
      entries = Object.entries(obj);
    }
    renderRooms(entries);
  }catch(err){
    console.error(err);
    toast('Failed to load rooms', true);
  }
}

function renderRooms(entries){
  listEl.innerHTML = '';
  if(!entries.length){
    const empty = document.createElement('div');
    empty.className = 'helper';
    empty.textContent = 'No rooms yet — create one!';
    listEl.appendChild(empty);
    return;
  }
  for(const [name, count] of entries){
    const item = document.createElement('div');
    item.className = 'room';
    item.innerHTML = `
      <div class="row">
        <strong>${escapeHtml(name)}</strong>
        <span class="pill">${count ?? 0} online</span>
      </div>
      <div class="row">
        <button class="btn" data-join="${escapeHtml(name)}" style="width:auto;padding-inline:14px">Join</button>
      </div>
    `;
    listEl.appendChild(item);
  }
}

// ===== Create room =====
formEl.addEventListener('submit', async (e)=>{
  e.preventDefault();
  let name = (inputEl.value || '').trim();

  // simple room-name validation (letters, numbers, dashes/underscores, 2-32 chars)
  if(!/^[a-zA-Z0-9_-]{2,32}$/.test(name)){
    toast('Room name: 2–32 chars, letters/numbers/_/- only', true);
    return;
  }

  try{
    // POST /rooms  body: { name }
    const res = await fetch(`${API}/rooms`, withAuth({
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ name }),
    }));
    if(!res.ok){
      throw new Error(await parseError(res));
    }
    toast('Room created ✓');
    inputEl.value = '';
    await sleep(200);
    await loadRooms(); // refresh list
  }catch(err){
    console.error(err);
    toast(String(err.message || 'Create error'), true);
  }
});

// ===== Join room (event delegation) =====
listEl.addEventListener('click', (e)=>{
  const btn = e.target.closest('button[data-join]');
  if(!btn) return;
  const room = btn.getAttribute('data-join');
  // Navigate with query param; chat.js should open WS using ?room=
  window.location.href = `chat.html?room=${encodeURIComponent(room)}`;
});

// ===== Init =====
loadRooms();
