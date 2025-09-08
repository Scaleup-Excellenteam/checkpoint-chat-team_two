// ===== Config =====
const API_BASE = window.API_BASE || "http://localhost:8080"; // backend base

// ===== Shared helpers (same behavior as login.js) =====

// Show toast message (error=true -> red border, otherwise green)
function showToast(msg, error=false){
  const el = document.getElementById('toast');
  if(!el) return;
  el.textContent = msg;
  el.style.borderColor = error ? 'rgba(239,68,68,.45)' : 'rgba(22,163,74,.45)';
  el.classList.add('show');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(()=> el.classList.remove('show'), 2200);
}

// Set helper text under inputs; kind: 'helper' | 'error' | 'success'
function setHelper(id, text, kind='helper'){
  const el = document.getElementById(id);
  if(!el) return;
  el.textContent = text;
  el.className = kind;
}

// Small sleep helper (simulate latency)
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// ===== Register form logic =====
const form   = document.getElementById('registerForm');
const fullEl = document.getElementById('fullname');
const mailEl = document.getElementById('email');
const pass1  = document.getElementById('password');
const pass2  = document.getElementById('password2');
const terms  = document.getElementById('terms');
const btn    = document.getElementById('registerBtn');

// Optional nickname field (preferred if exists)
const nickEl = document.getElementById('nickname');

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  // reset helpers
  setHelper('fullnameHelp','');
  setHelper('emailHelp','');
  setHelper('passwordHelp','');
  setHelper('password2Help','');
  setHelper('nicknameHelp','');

  let ok = true;

  // --- Resolve nickname ---
  // Preferred: explicit nickname input; fallback: fullname; fallback: email local-part
  let nickname = '';
  if (nickEl && nickEl.value.trim()) {
    nickname = nickEl.value.trim();
  } else if (fullEl && fullEl.value.trim()) {
    nickname = fullEl.value.trim();
  } else if (mailEl && mailEl.value.includes('@')) {
    nickname = mailEl.value.split('@')[0].trim();
  }

  // --- Validations (frontend only) ---
  if (nickEl && !nickname) {
    // If nickname field exists, require it
    setHelper('nicknameHelp','Nickname is required','error');
    ok = false;
  }
  if (fullEl && !fullEl.value.trim()) {
    setHelper('fullnameHelp','Full name is required','error');
    // not fatal if nickname is provided; keep ok state only if no nickname
    if (!nickname) ok = false;
  }
  if (mailEl && !mailEl.value.includes('@')) {
    setHelper('emailHelp','Please enter a valid email','error');
    // email not required by backend, but keep UX hint
  }
  if (!pass1.value || pass1.value.length < 4) {
    // Backend requires at least 4 in our Pydantic schema
    setHelper('passwordHelp','Password must be at least 4 characters','error');
    ok = false;
  }
  if (pass1.value !== pass2.value) {
    setHelper('password2Help','Passwords do not match','error');
    ok = false;
  }
  if (terms && !terms.checked) {
    showToast('Please accept the Terms of Service', true);
    ok = false;
  }
  if (!nickname) {
    // Final guard if no nickname could be derived
    setHelper('nicknameHelp','Nickname is required','error');
    ok = false;
  }
  if (!ok) return;

  btn.disabled = true;
  try {
    // --- Real backend call: POST /auth/register ---
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // Backend expects: { nickname, password }
      body: JSON.stringify({ nickname, password: pass1.value })
    });

    if (!res.ok) {
      const txt = await res.text().catch(()=>'');
      throw new Error(txt || 'Registration failed');
    }

    const data = await res.json();
    // Expected: { user_id, token, nickname }
    localStorage.setItem('token', data.token);
    localStorage.setItem('nickname', data.nickname);
    localStorage.setItem('user_id', data.user_id);

    showToast('Account created successfully');
    await sleep(400);

    // Redirect to rooms list (or login if you prefer)
    window.location.href = 'rooms.html';
  } catch (err) {
    console.error(err);
    showToast('Registration error', true);
  } finally {
    btn.disabled = false;
  }
});
