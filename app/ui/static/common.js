(function () {
  const token = localStorage.getItem("token");
  const userJson = localStorage.getItem("user");
  const path = location.pathname;
  const isLogin = path.endsWith("/ui/login");

  if (!token && !isLogin) { location.href = "/ui/login"; return; }
  if (token && isLogin)   { location.href = "/ui/dashboard"; return; }

  if (!isLogin) {
    const nav = document.getElementById("mainNav");
    if (nav) nav.classList.remove("hidden");
    let user = {};
    try { user = JSON.parse(userJson || "{}"); } catch (e) { user = {}; }

    const navUser = document.getElementById("navUser");
    if (navUser) {
      const lbl = user.label || user.username || "";
      const dept = user.department ? ` · ${user.department}` : "";
      navUser.textContent = lbl + dept;
    }

    if (user.role !== "admin") {
      document.querySelectorAll("[data-admin-only]").forEach((el) => el.classList.add("hidden"));
    }

    // Active nav link
    const navKey = path.includes("/admin") ? "admin"
                 : path.includes("/chat")  ? "chat"
                 : "dashboard";
    document.querySelectorAll("[data-nav]").forEach((a) => {
      if (a.dataset.nav === navKey) a.classList.add("active");
    });

    const lo = document.getElementById("logoutBtn");
    if (lo) {
      lo.addEventListener("click", () => {
        localStorage.removeItem("token");
        localStorage.removeItem("user");
        location.href = "/ui/login";
      });
    }
  }

  /* ---------- API helper ---------- */
  window.api = async function api(path, opts = {}) {
    const headers = Object.assign(
      { "Content-Type": "application/json" },
      opts.headers || {},
    );
    const t = localStorage.getItem("token");
    if (t) headers["Authorization"] = `Bearer ${t}`;
    const r = await fetch(path, Object.assign({}, opts, { headers }));
    if (r.status === 401) {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      location.href = "/ui/login";
      return null;
    }
    if (!r.ok) {
      let detail = `${r.status} ${r.statusText}`;
      try { const j = await r.json(); if (j.detail) detail = j.detail; } catch (e) {}
      throw new Error(detail);
    }
    if (r.status === 204) return null;
    return r.json();
  };

  /* ---------- Number formatting ---------- */
  window.fmtNumber = function (n, digits = 1) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return Number(n).toLocaleString("tr-TR", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  };

  /* ---------- Key/value table ---------- */
  window.kvRows = function (table, rows) {
    table.innerHTML = "";
    for (const [k, v] of rows) {
      const tr = document.createElement("tr");
      const td1 = document.createElement("td"); td1.textContent = k;
      const td2 = document.createElement("td");
      td2.textContent = v === null || v === undefined || v === "" ? "—" : v;
      tr.appendChild(td1); tr.appendChild(td2);
      table.appendChild(tr);
    }
  };

  /* ---------- Toast notifications ---------- */
  window.toast = function (message, kind = "ok", ttl = 3500) {
    const area = document.getElementById("toast-area");
    if (!area) { console.log(`[${kind}]`, message); return; }
    const t = document.createElement("div");
    t.className = "toast " + kind;
    t.textContent = message;
    area.appendChild(t);
    setTimeout(() => {
      t.style.opacity = "0";
      t.style.transition = "opacity 200ms";
      setTimeout(() => t.remove(), 220);
    }, ttl);
  };

  /* Polyfill: replace alert() calls in pages */
  window.notify = window.toast;
})();
