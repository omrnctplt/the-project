(function () {
  const token = localStorage.getItem("token");
  const userJson = localStorage.getItem("user");
  const path = location.pathname;
  const isLogin = path.endsWith("/ui/login");
  const isPublic = isLogin || path.endsWith("/ui/privacy");

  if (!token && !isPublic) { location.href = "/ui/login"; return; }
  if (token && isLogin)    { location.href = "/ui/dashboard"; return; }

  let user = {};
  if (!isPublic) {
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
    // Admin gizleme + sayfa kapisi
    if (user.role !== "admin") {
      document.querySelectorAll("[data-admin-only]").forEach((el) => el.classList.add("hidden"));
      if (path.includes("/ui/admin") || path.includes("/ui/resources")) {
        location.href = "/ui/dashboard";
        return;
      }
    }
    // Active nav
    const navKey = path.includes("/admin") ? "admin"
                 : path.includes("/chat")  ? "chat"
                 : path.includes("/models") ? "models"
                 : path.includes("/resources") ? "resources"
                 : path.includes("/onboarding") ? ""
                 : "dashboard";
    document.querySelectorAll("[data-nav]").forEach((a) => {
      if (a.dataset.nav === navKey) {
        a.classList.add("active");
        a.setAttribute("aria-current", "page");
      }
    });
    // Logout binding (delegated) — sohbet gecmisi dahil tum kisisel izler silinir
    document.addEventListener("click", (e) => {
      if (e.target && e.target.id === "logoutBtn") {
        const toRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (k && (k === "token" || k === "user" || k === "hub_bootstrapped" || k.startsWith("hub_convs"))) {
            toRemove.push(k);
          }
        }
        toRemove.forEach((k) => localStorage.removeItem(k));
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
      throw new Error("Oturum suresi doldu, yeniden giris yapin");
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
  window.fmtEta = function (sec) {
    if (sec == null || isNaN(sec)) return "";
    sec = Math.max(0, Math.round(sec));
    if (sec < 60) return sec + " sn";
    const m = Math.floor(sec / 60), r = sec % 60;
    if (m < 60) return m + " dk" + (r ? " " + r + " sn" : "");
    return Math.floor(m / 60) + " sa " + (m % 60) + " dk";
  };

  /* ---------- Model indirme (pull) ilerleme gosterimi ---------- */
  window.trPullStage = function (stage) {
    if (!stage) return "Indiriliyor";
    if (stage === "success") return "Tamamlandi";
    if (stage === "baslatiliyor") return "Baslatiliyor";
    if (/sirada/.test(stage)) return "Sirada bekliyor";
    if (/^pulling manifest/.test(stage)) return "Manifest aliniyor";
    if (/^pulling /.test(stage)) return "Model dosyasi indiriliyor";
    if (/verifying/.test(stage)) return "Dosya butunlugu dogrulaniyor";
    if (/writing manifest/.test(stage)) return "Manifest yaziliyor";
    if (/removing/.test(stage)) return "Gecici dosyalar temizleniyor";
    return stage;
  };
  window.pullProgressHtml = function (s) {
    if (s.status === "queued") {
      return `
        <div class="pp-head"><span>Sirada bekliyor — baska bir indirme suruyor</span></div>
        <div class="cbar-track pp-bar"><div class="cbar-fill indeterminate"></div></div>`;
    }
    const pct = Math.min(100, Math.round((s.pull_progress || 0) * 100));
    const haveBytes = (s.pull_total_mb || 0) > 0;
    const parts = [];
    if (haveBytes) parts.push(`${fmtBytes(s.pull_completed_mb)} / ${fmtBytes(s.pull_total_mb)}`);
    if ((s.pull_speed_mbps || 0) > 0.01) parts.push(`${Number(s.pull_speed_mbps).toFixed(1)} MB/s`);
    if (s.pull_eta_seconds != null && s.pull_eta_seconds > 0) parts.push(`~${fmtEta(s.pull_eta_seconds)} kaldi`);
    return `
      <div class="pp-head"><span>${escapeHtml(trPullStage(s.pull_stage))}</span><span>%${pct}</span></div>
      <div class="cbar-track pp-bar"><div class="cbar-fill pulling" style="width:${pct}%"></div></div>
      ${parts.length ? `<div class="pp-meta">${escapeHtml(parts.join(" · "))}</div>` : ""}`;
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

  /* ---------- Modal ----------
     onPrimary false dondururse (veya Promise'i false'a cozulurse) modal ACIK
     kalir — dogrulama hatasinda kullanicinin girdigi veri kaybolmaz. */
  window.modal = function ({ title, body, primary, onPrimary, cancel = "Vazgec", danger = false }) {
    const back = document.createElement("div");
    back.className = "modal-backdrop";
    const titleId = "modal-title-" + Math.random().toString(36).slice(2, 8);
    back.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="${titleId}">
        <h2 id="${titleId}">${escapeHtml(title || "")}</h2>
        <div class="modal-body">${body || ""}</div>
        <div class="modal-actions">
          <button type="button" data-act="cancel">${escapeHtml(cancel)}</button>
          ${primary ? `<button type="button" class="${danger ? "danger" : "primary"}" data-act="ok">${escapeHtml(primary)}</button>` : ""}
        </div>
      </div>`;
    document.body.appendChild(back);
    const prevFocus = document.activeElement;
    function close() {
      back.remove();
      document.removeEventListener("keydown", onKey);
      if (prevFocus && prevFocus.focus) prevFocus.focus();
    }
    function onKey(e) {
      if (e.key === "Escape") { e.stopPropagation(); close(); return; }
      if (e.key === "Tab") {
        const focusables = back.querySelectorAll("button, input, select, textarea, a[href]");
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener("keydown", onKey);
    const firstField = back.querySelector("input, select, textarea") || back.querySelector("button[data-act=ok]") || back.querySelector("button");
    if (firstField) setTimeout(() => firstField.focus(), 30);
    back.addEventListener("click", async (e) => {
      if (e.target === back) { close(); return; }
      if (e.target?.dataset?.act === "cancel") { close(); return; }
      if (e.target?.dataset?.act === "ok") {
        if (onPrimary) {
          const okBtn = e.target;
          okBtn.disabled = true;
          let result;
          try {
            result = await onPrimary(back);
          } finally {
            okBtn.disabled = false;
          }
          if (result === false) return;
        }
        close();
      }
    });
    return { close, root: back };
  };

  /* ---------- Onay diyalogu (native confirm yerine) ---------- */
  window.confirmModal = function ({ title, body, primary = "Evet", danger = true }) {
    return new Promise((resolve) => {
      const m = window.modal({
        title,
        body: body ? `<p style="margin-top:0;">${body}</p>` : "",
        primary,
        danger,
        onPrimary: () => { resolve(true); },
      });
      const origClose = m.close;
      m.root.addEventListener("click", (e) => {
        if (e.target === m.root || e.target?.dataset?.act === "cancel") resolve(false);
      });
      document.addEventListener("keydown", function esc(e) {
        if (e.key === "Escape") { resolve(false); document.removeEventListener("keydown", esc); }
      });
    });
  };

  /* ---------- Ollama tag -> katalog model_id (backend kuralina esdeger) ---------- */
  window.tagToModelId = function (tag) {
    return String(tag).replace(/[:.\/]/g, "-").replace(/[^a-zA-Z0-9._\-]/g, "").slice(0, 64);
  };

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
  window.escapeHtml = escapeHtml;

  /* ---------- Panoya kopyalama (clipboard API + fallback) ---------- */
  window.copyToClipboard = async function (text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.top = "-1000px";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch {}
      ta.remove();
      return ok;
    }
  };

  /* ---------- Guvenli markdown renderer (bagimliliksiz, XSS'siz) ----------
     Once tum girdi escape edilir; sadece kontrollu, beyaz listeli HTML uretilir.
     Desteklenen: fenced kod blogu (```lang), inline `code`, **kalin**, *italik*,
     # basliklar, - / 1. listeler, > alinti, [metin](http...) linkleri. */
  window.renderMarkdown = function (src) {
    if (!src) return "";
    const esc = escapeHtml;

    // 1) Fenced kod bloklarini ayikla, yerlerine sentinel koy
    const blocks = [];
    let text = String(src).replace(/```([\w+.-]*)\n?([\s\S]*?)```/g, (_m, lang, code) => {
      blocks.push({ lang: (lang || "").trim(), code: code.replace(/\n$/, "") });
      return ` B${blocks.length - 1} `;
    });

    // 2) Govdeyi escape et, sonra satir-ici bicimleri uygula
    text = esc(text);
    text = text.replace(/`([^`\n]+)`/g, (_m, c) => `<code>${c}</code>`);
    text = text.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, "$1<em>$2</em>");
    text = text.replace(/(^|[^_\w])_([^_\n]+)_(?!\w)/g, "$1<em>$2</em>");
    text = text.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    );

    // 3) Blok seviyesi: basliklar, listeler, alinti, paragraf
    const lines = text.split("\n");
    let html = "";
    let listType = null;
    let inQuote = false;
    const closeList = () => { if (listType) { html += `</${listType}>`; listType = null; } };
    const closeQuote = () => { if (inQuote) { html += "</blockquote>"; inQuote = false; } };

    for (const line of lines) {
      if (/^ B\d+ $/.test(line.trim())) { closeList(); closeQuote(); html += line.trim(); continue; }
      let m;
      if ((m = line.match(/^(#{1,4})\s+(.*)$/))) {
        closeList(); closeQuote();
        const lvl = m[1].length;
        html += `<h${lvl}>${m[2]}</h${lvl}>`;
      } else if (/^\s*[-*]\s+/.test(line)) {
        closeQuote();
        if (listType !== "ul") { closeList(); html += "<ul>"; listType = "ul"; }
        html += `<li>${line.replace(/^\s*[-*]\s+/, "")}</li>`;
      } else if (/^\s*\d+\.\s+/.test(line)) {
        closeQuote();
        if (listType !== "ol") { closeList(); html += "<ol>"; listType = "ol"; }
        html += `<li>${line.replace(/^\s*\d+\.\s+/, "")}</li>`;
      } else if (/^\s*>\s?/.test(line)) {
        closeList();
        if (!inQuote) { html += "<blockquote>"; inQuote = true; }
        html += line.replace(/^\s*>\s?/, "") + "<br>";
      } else if (line.trim() === "") {
        closeList(); closeQuote();
      } else {
        closeList(); closeQuote();
        html += `<p>${line}</p>`;
      }
    }
    closeList(); closeQuote();

    // 4) Kod bloklarini geri yerlestir (kopyala butonu ile)
    html = html.replace(/ B(\d+) /g, (_m, i) => {
      const b = blocks[+i];
      if (!b) return "";
      const langLabel = b.lang ? `<span class="code-lang">${esc(b.lang)}</span>` : `<span class="code-lang">metin</span>`;
      return (
        `<div class="code-block" data-code="${esc(b.code)}">` +
        `<div class="code-head">${langLabel}` +
        `<button class="copy-code" type="button" aria-label="Kodu kopyala">Kopyala</button></div>` +
        `<pre><code>${esc(b.code)}</code></pre></div>`
      );
    });

    return html;
  };

  /* Kod blogu kopyala butonlari icin tek delege dinleyici (tum sayfalarda) */
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest && e.target.closest(".copy-code");
    if (!btn) return;
    const block = btn.closest(".code-block");
    const code = block ? block.getAttribute("data-code") : "";
    const ok = await window.copyToClipboard(code || "");
    const prev = btn.textContent;
    btn.textContent = ok ? "Kopyalandi ✓" : "Hata";
    btn.classList.toggle("copied", ok);
    setTimeout(() => { btn.textContent = prev; btn.classList.remove("copied"); }, 1500);
  });

  /* ---------- Tema yonetimi (auto / acik / koyu) ---------- */
  (function setupTheme() {
    const root = document.documentElement;
    const order = ["auto", "light", "dark"];
    const icons = { auto: "🌗", light: "☀", dark: "☾" };
    const labels = { auto: "Sistem", light: "Acik", dark: "Koyu" };
    const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

    function resolve(pref) {
      if (pref === "dark") return "dark";
      if (pref === "light") return "light";
      return media && media.matches ? "dark" : "light";
    }
    function updateBtn(pref) {
      const btn = document.getElementById("themeToggle");
      if (!btn) return;
      const ico = btn.querySelector(".ico");
      const lbl = btn.querySelector(".lbl");
      if (ico) ico.textContent = icons[pref];
      if (lbl) lbl.textContent = "Tema: " + labels[pref];
      btn.setAttribute("title", "Tema: " + labels[pref] + " — degistirmek icin tikla");
    }
    function apply(pref) {
      const mode = resolve(pref);
      root.setAttribute("data-theme", mode);
      root.setAttribute("data-theme-pref", pref);
      const meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute("content", mode === "dark" ? "#0a0c11" : "#f6f7f9");
      updateBtn(pref);
    }
    let pref = localStorage.getItem("hub_theme") || "auto";
    apply(pref);
    if (media && media.addEventListener) {
      media.addEventListener("change", () => {
        if ((localStorage.getItem("hub_theme") || "auto") === "auto") apply("auto");
      });
    }
    const btn = document.getElementById("themeToggle");
    if (btn) {
      btn.addEventListener("click", () => {
        pref = order[(order.indexOf(pref) + 1) % order.length];
        localStorage.setItem("hub_theme", pref);
        apply(pref);
      });
    }
  })();

  /* ---------- Izleme linkleri: sunucunun adresine gore dinamik ----------
     LAN'dan erisen calisanlarda localhost kirilir; gateway hangi host'tan
     acildiysa Grafana/Prometheus da ayni host uzerinden linklenir. */
  document.querySelectorAll("[data-monitor-link]").forEach((a) => {
    a.href = location.protocol + "//" + location.hostname + ":" + a.dataset.monitorLink;
  });

  /* ---------- Mobil navigasyon (drawer) ---------- */
  (function setupMobileNav() {
    const toggle = document.getElementById("navToggle");
    const sidebar = document.getElementById("mainSidebar");
    const backdrop = document.getElementById("navBackdrop");
    if (!toggle || !sidebar) return;
    const open = () => {
      sidebar.classList.add("open");
      if (backdrop) backdrop.classList.add("show");
      toggle.setAttribute("aria-expanded", "true");
    };
    const close = () => {
      sidebar.classList.remove("open");
      if (backdrop) backdrop.classList.remove("show");
      toggle.setAttribute("aria-expanded", "false");
    };
    toggle.addEventListener("click", () => {
      sidebar.classList.contains("open") ? close() : open();
    });
    if (backdrop) backdrop.addEventListener("click", close);
    sidebar.addEventListener("click", (e) => {
      if (e.target.closest("a.nav-item")) close();
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  })();

  /* ---------- Global model indirme gostergesi ----------
     Hangi sayfada olursa olsun suren bir model indirmesi varsa sag altta
     canli ilerleme karti gosterir — kullanici arayuzu donmus sanmaz. */
  (function globalPullIndicator() {
    if (isPublic || !token) return;
    const el = document.createElement("div");
    el.id = "globalPullBar";
    el.className = "global-pull hidden";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.title = "Modeller sayfasina git";
    el.addEventListener("click", () => { location.href = "/ui/models"; });
    document.body.appendChild(el);

    const IDLE_MS = 8000, ACTIVE_MS = 1500;
    let timer = null;
    function schedule(ms) {
      clearTimeout(timer);
      timer = setTimeout(tick, ms);
    }
    async function tick() {
      let r;
      try { r = await api("/api/v1/models"); }
      catch { schedule(IDLE_MS * 2); return; }
      const states = r.states || [];
      const active = states.filter(s => s.status === "pulling" || s.status === "queued");
      if (!active.length) {
        el.classList.add("hidden");
        schedule(IDLE_MS);
        return;
      }
      const s = active.find(x => x.status === "pulling") || active[0];
      const rest = active.length - 1;
      el.innerHTML = `
        <div class="gp-title">Model indiriliyor — arayuzu kullanmaya devam edebilirsiniz</div>
        <div class="gp-model">${escapeHtml(s.model_id)}${rest > 0 ? ` <span class="gp-more">+${rest} sirada</span>` : ""}</div>
        ${pullProgressHtml(s)}`;
      el.classList.remove("hidden");
      schedule(ACTIVE_MS);
    }
    tick();
  })();

  /* ---------- Cihaza gore optimizasyon (dusuk guc -> efektleri azalt) ---------- */
  (function deviceTune() {
    try {
      const lowCores = (navigator.hardwareConcurrency || 8) <= 2;
      const lowMem = navigator.deviceMemory && navigator.deviceMemory <= 2;
      const coarse = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
      const narrow = window.innerWidth <= 480;
      if (lowCores || lowMem || (coarse && narrow)) {
        document.documentElement.classList.add("reduce-fx");
      }
    } catch (e) {}
  })();
})();
