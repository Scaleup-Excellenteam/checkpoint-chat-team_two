// ===== Config =====
const API = window.API_BASE || "http://localhost:8080";

// ===== Small helpers =====
function toast(msg){
  const el = document.getElementById('toast');
  if(!el) return;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(()=> el.classList.remove('show'), 1800);
}
function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]
  ));
}

// ===== Auth state (from login/register) =====
const token     = localStorage.getItem('token');
const nickname  = localStorage.getItem('nickname');
const userId    = localStorage.getItem('user_id');

// If no token → force login
if(!token){
  window.location.replace('login.html');
}

// Greet bar
const whoEl   = document.getElementById('who');
const greetEl = document.getElementById('greet');
if (whoEl)   whoEl.textContent   = nickname ? `Signed in as ${nickname}` : 'Signed in';
if (greetEl) greetEl.textContent = 'Rooms';

// Logout
document.getElementById('logoutBtn')?.addEventListener('click', ()=>{
  localStorage.removeItem('token');
  localStorage.removeItem('nickname');
  localStorage.removeItem('user_id');
  window.location.replace('login.html');
});

// ===== DOM refs =====
const listEl   = document.getElementById('rooms-list');
const formEl   = document.getElementById('create-room-form');
const inputEl  = document.getElementById('room-name');

// ===== Load & render rooms =====
async function loadRooms(){
  try{
    // GET /rooms -> { rooms: { "<name>": <count>, ... } }
    const res = await fetch(`${API}/rooms`, { method:'GET' });
    if(!res.ok) throw new Error('Failed to load rooms');
    const data = await res.json();
    const entries = Object.entries(data.rooms || {}); // [ [name, count], ... ]
    renderRooms(entries);
  }catch(err){
    console.error(err);
    toast('Failed to load rooms');
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
  const name = (inputEl.value || '').trim();
  if(!name) return;

  try{
    // POST /rooms  body: { name }
    const res = await fetch(`${API}/rooms`, {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ name }),
    });
    if(!res.ok){
      const txt = await res.text().catch(()=> '');
      throw new Error(txt || 'Create failed');
    }
    await loadRooms();
    toast('Room created ✓');
    inputEl.value = '';
  }catch(err){
    console.error(err);
    toast('Create error');
  }
});

// ===== Join room (event delegation) =====
listEl.addEventListener('click', (e)=>{
  const btn = e.target.closest('button[data-join]');
  if(!btn) return;
  const room = btn.getAttribute('data-join');
  // Navigate with query param (chat.js will open WS using token+room)
  window.location.href = `chat.html?room=${encodeURIComponent(room)}`;
});

// Init
loadRooms();
