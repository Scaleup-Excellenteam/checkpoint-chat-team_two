// ===== Config =====
// Prefer window.API_BASE if provided (e.g., via config.js), fallback to local FastAPI.
const API_BASE = (window.API_BASE && String(window.API_BASE).trim()) || "http://localhost:8090";

// ===== Shared helpers (same behavior as login.js) =====

// Show toast message (error=true -> red)
function showToast(msg, error = false) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.style.background = error ? "#ff4d4f" : "#4caf50";
  el.classList.add("show");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.remove("show"), 2200);
}

// Set helper text under inputs; kind: 'helper' | 'error' | 'success'
function setHelper(id, text, kind = "helper") {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text || "";
  el.className = kind;
}

// Small sleep helper (simulate latency)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ===== Register form logic =====
const form = document.getElementById("registerForm");
const fullEl = document.getElementById("fullname");
const mailEl = document.getElementById("email");
const pass1 = document.getElementById("password");
const pass2 = document.getElementById("password2");
const terms = document.getElementById("terms");
const btn = document.getElementById("registerBtn");
const nickEl = document.getElementById("nickname");

// simple email check (not exhaustive but good UX)
const emailOk = (s) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s || "");

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  // reset helpers
  setHelper("nicknameHelp", "");
  setHelper("fullnameHelp", "");
  setHelper("emailHelp", "");
  setHelper("passwordHelp", "");
  setHelper("password2Help", "");

  // normalize inputs
  const nicknameInput = (nickEl?.value || "").trim();
  const fullname = (fullEl?.value || "").trim();
  const email = (mailEl?.value || "").trim();
  const pwd1 = pass1.value || "";
  const pwd2 = pass2.value || "";

  // resolve nickname: explicit > fullname > email local-part
  let nickname = nicknameInput;
  if (!nickname) nickname = fullname;
  if (!nickname && email.includes("@")) nickname = email.split("@")[0];

  // validations
  let ok = true;

  if (nickEl && !nickname) {
    setHelper("nicknameHelp", "Nickname is required", "error");
    ok = false;
  } else if (nickname && nickname.length < 2) {
    setHelper("nicknameHelp", "At least 2 characters", "error");
    ok = false;
  }

  if (fullEl && !fullname) {
    // not fatal if nickname exists, but give UX hint
    setHelper("fullnameHelp", "Recommended (used in UI)", "helper");
  }

  if (mailEl && email && !emailOk(email)) {
    setHelper("emailHelp", "Enter a valid email", "error");
    ok = false;
  }

  if (!pwd1 || pwd1.length < 4) {
    setHelper("passwordHelp", "Password must be at least 4 characters", "error");
    ok = false;
  }
  if (pwd1 !== pwd2) {
    setHelper("password2Help", "Passwords do not match", "error");
    ok = false;
  }

  if (terms && !terms.checked) {
    showToast("Please accept the Terms of Service", true);
    ok = false;
  }

  if (!ok) return;

  // submit
  btn.disabled = true;
  btn.textContent = "Creating…";

  try {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Backend expects minimal payload: { nickname, password }
      body: JSON.stringify({ nickname, password: pwd1 }),
    });

    if (!res.ok) {
      // try parse JSON error body for better message (e.g., {"detail": "..."} or {"errors":[...]} )
      let msg = "Registration failed";
      try {
        const err = await res.json();
        if (typeof err?.detail === "string") msg = err.detail;
        else if (Array.isArray(err?.errors) && err.errors.length) msg = err.errors[0].message || msg;
      } catch {
        // fallback to text if not JSON
        try {
          const txt = await res.text();
          if (txt) msg = txt;
        } catch {}
      }
      showToast(msg, true);
      return;
    }

    const data = await res.json();
    // Expected: { user_id, token, nickname }
    if (data?.token) localStorage.setItem("token", data.token);
    if (data?.nickname) localStorage.setItem("nickname", data.nickname);
    if (data?.user_id !== undefined) localStorage.setItem("user_id", data.user_id);

    showToast("Account created successfully");
    await sleep(400);
    window.location.href = "rooms.html";
  } catch (err) {
    console.error("Registration error:", err);
    showToast("Server unreachable", true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Create account";
  }
});
