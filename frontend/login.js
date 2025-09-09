// Define backend base (from config.js or fallback)
const API_BASE = window.API_BASE || "http://localhost:8090";

const qs = (s) => document.querySelector(s);

const toast = (msg, isError = false) => {
  const t = qs("#toast");
  if (!t) return;
  t.textContent = msg;
  t.style.background = isError ? "#ff4d4f" : "#4caf50";
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2000);
};

const setHelp = (id, txt) => {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = txt;
    el.className = txt ? "error" : "helper";
  }
};

qs("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  setHelp("nicknameHelp", "");
  setHelp("passwordHelp", "");

  const nickname = qs("#nickname").value.trim();
  const password = qs("#password").value.trim();

  let ok = true;
  if (!nickname) {
    setHelp("nicknameHelp", "Enter your nickname");
    ok = false;
  }
  if (!password || password.length < 4) {
    setHelp("passwordHelp", "At least 4 characters");
    ok = false;
  }
  if (!ok) return;

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nickname, password }),
    });

    if (!res.ok) {
      let errMsg = "Login failed";
      try {
        const err = await res.json();
        if (err.detail) errMsg = err.detail;
      } catch (_) {}
      toast(errMsg, true);
      return;
    }

    const data = await res.json();
    // Expected: { user_id, token, nickname }
    localStorage.setItem("token", data.token);
    localStorage.setItem("nickname", data.nickname);
    localStorage.setItem("user_id", data.user_id);

    toast("Signed in ✓");
    setTimeout(() => {
      window.location.href = "rooms.html";
    }, 500);
  } catch (err) {
    console.error("Login error:", err);
    toast("Server unreachable", true);
  }
});
