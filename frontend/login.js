const API_BASE = window.API_BASE || "http://localhost:8080"; // backend base

const qs = (s) => document.querySelector(s);
const toast = (msg) => {
  const t = qs('#toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 1800);
};
const setHelp = (id, txt) => {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = txt;
    el.className = txt ? 'error' : 'helper';
  }
};

qs('#loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  setHelp('nicknameHelp', '');
  setHelp('passwordHelp', '');

  const nickname = qs('#nickname').value.trim();
  const password = qs('#password').value;

  let ok = true;
  if (!nickname) { 
    setHelp('nicknameHelp', 'Enter your nickname'); 
    ok = false; 
  }
  if (!password || password.length < 4) { 
    setHelp('passwordHelp', 'At least 4 characters'); 
    ok = false; 
  }
  if (!ok) return;

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname, password })
    });
    if (!res.ok) throw new Error('Login failed');
    const data = await res.json();
    // Expected payload: { user_id, token, nickname }
    localStorage.setItem('token', data.token);
    localStorage.setItem('nickname', data.nickname);
    localStorage.setItem('user_id', data.user_id);

    toast('Signed in ✓');
    // Redirect to rooms list
    window.location.href = 'rooms.html';
  } catch (err) {
    console.error(err);
    toast('Login error');
  }
});
