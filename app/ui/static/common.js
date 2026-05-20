(function () {
  const token = localStorage.getItem("token");
  const userJson = localStorage.getItem("user");
  const path = location.pathname;
  const isLogin = path.endsWith("/ui/login");

  if (!token && !isLogin) { location.href = "/ui/login"; return; }
  if (token && isLogin)   { location.href = "/ui/chat"; return; }

  let user = {};
  if (!isLogin) {
    try { user = JSON.parse(userJson || "{}"); } catch (e) { user = {}; }

    // User card
    const uc = document.getElementById("userCard");
    if (uc) {
      const initials = (user.label || user.username || "?").trim().slice(0, 2).toUpperCase();
      uc.innerHTML = `
        <div class="avatar">${escapeHtml(initials)}</div>
        <div class="who">
          <div class="nm">${escapeHtml(user.label || user.username || "Kullanici")}</div>
          <div class="dep">${escapeHtml(user.department || "")} · ${escapeHtml(user.role || "")}</div>
        </div>
        <button class="logout" id="logoutBtn" title="Cikis">⏻</button>`;
    }
    // Admin gizleme
    if (user.role !== "admin") {
      document.querySelectorAll("[data-admin-only]").forEach((el) => el.classList.add("hidden"));
    }
    // Active nav
    const navKey = path.includes("/admin") ? "admin"
                 : path.includes("/chat")  ? "chat"
                 : path.includes("/models") ? "models"
                 : path.includes("/resources") ? "resources"
                 : path.includes("/onboarding") ? ""
                 : "dashboard";
    document.querySelectorAll("[data-nav]").forEach((a) => {
      if (a.dataset.nav === navKey) a.classList.add("active");
    });
    // Logout binding (delegated)
    document.addEventListener("click", (e) => {
      if (e.target && e.target.id === "logoutBtn") {
        localStorage.removeItem("token");
        localStorage.removeItem("user");
        localStorage.removeItem("hub_bootstrapped");
        location.href = "/ui/login";
      }
    });
  }
  window.currentUser = user;

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
  window.fmtBytes = function (mb) {
    if (mb == null || isNaN(mb)) return "—";
    if (mb >= 1024) return (mb / 1024).toFixed(1) + " GB";
    return Math.round(mb) + " MB";
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

  /* ---------- Modal ---------- */
  window.modal = function ({ title, body, primary, onPrimary, cancel = "Vazgec" }) {
    const back = document.createElement("div");
    back.className = "modal-backdrop";
    back.innerHTML = `
      <div class="modal">
        <h2>${escapeHtml(title || "")}</h2>
        <div class="modal-body">${body || ""}</div>
        <div class="modal-actions">
          <button data-act="cancel">${escapeHtml(cancel)}</button>
          ${primary ? `<button class="primary" data-act="ok">${escapeHtml(primary)}</button>` : ""}
        </div>
      </div>`;
    document.body.appendChild(back);
    function close() { back.remove(); }
    back.addEventListener("click", (e) => {
      if (e.target === back) close();
      if (e.target?.dataset?.act === "cancel") close();
      if (e.target?.dataset?.act === "ok") {
        if (onPrimary) onPrimary(back);
        close();
      }
    });
    return { close, root: back };
  };

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
  window.escapeHtml = escapeHtml;
})();
