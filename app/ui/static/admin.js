(async function () {
  // Tab system
  document.querySelector(".tabs").addEventListener("click", (e) => {
    if (!e.target.matches("button[data-tab]")) return;
    const t = e.target.dataset.tab;
    document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("active", p.dataset.panel === t));
  });

  // --- Settings ---
  try {
    const cfg = await api("/api/v1/system/config");
    document.getElementById("profile").value = cfg.profile || "auto";
    document.getElementById("expectedUsers").value = cfg.expected_users;
    document.getElementById("expectedConcurrency").value = cfg.expected_concurrency;
    document.getElementById("idleUnloadMinutes").value = cfg.idle_unload_minutes;
    document.getElementById("autoPull").checked = !!cfg.auto_pull;
    document.getElementById("manualOverride").checked = !!cfg.manual_override;
    document.getElementById("activeModels").value = (cfg.active_models || []).join(", ");
  } catch (e) { console.error(e); }

  document.getElementById("configForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      profile: document.getElementById("profile").value,
      expected_users: parseInt(document.getElementById("expectedUsers").value || "0", 10),
      expected_concurrency: parseInt(document.getElementById("expectedConcurrency").value || "0", 10),
      idle_unload_minutes: parseInt(document.getElementById("idleUnloadMinutes").value || "10", 10),
      auto_pull: document.getElementById("autoPull").checked,
      manual_override: document.getElementById("manualOverride").checked,
      active_models: document.getElementById("activeModels").value.split(",").map(s => s.trim()).filter(Boolean),
    };
    try {
      await api("/api/v1/system/config", { method: "PUT", body: JSON.stringify(body) });
      toast(t("Profil kaydedildi ve plan yenilendi."), "ok");
    } catch (err) {
      toast(t("Kaydetme basarisiz: {m}", { m: err.message }), "error", 5000);
    }
  });

  // --- Users (tam yonetim: olustur / sifre sifirla / duzenle / sil) ---
  let _departments = [];

  async function loadUsersTab() {
    try {
      try {
        const cat = await api("/api/v1/system/catalog");
        _departments = Object.keys(cat.departments || {});
      } catch { _departments = []; }
      const u = await api("/api/v1/users");
      const tb = document.querySelector("#usersTable tbody");
      tb.innerHTML = "";
      const me = (window.currentUser || {}).username;
      for (const row of (u.users || [])) {
        const tr = document.createElement("tr");
        const isSelf = row.username === me;
        const isAdminRow = row.role === "admin";
        tr.innerHTML = `
          <td>${escapeHtml(row.username)}${isSelf ? ` <span class="muted">${t("(siz)")}</span>` : ""}</td>
          <td>${escapeHtml(row.department)}</td>
          <td><span class="badge ${isAdminRow ? "ok" : "plain"}">${escapeHtml(row.role)}</span></td>
          <td>${escapeHtml(row.label || "—")}</td>
          <td class="muted">${row.last_login_at ? row.last_login_at.replace("T", " ").slice(0, 19) : "—"}</td>
          <td style="white-space:nowrap;">
            <button class="small" data-uact="edit" data-u="${escapeHtml(row.username)}" title="${t("Departman/rol duzenle")}">${t("Duzenle")}</button>
            <button class="small" data-uact="pw" data-u="${escapeHtml(row.username)}" title="${t("Sifre sifirla")}">${t("Sifre")}</button>
            ${!isAdminRow ? `<button class="small danger" data-uact="del" data-u="${escapeHtml(row.username)}" title="${t("Hesabi sil (KVKK: tum verisiyle)")}">${t("Sil")}</button>` : ""}
          </td>`;
        tb.appendChild(tr);
      }
    } catch (e) { console.error(e); }
  }

  function deptOptions(selected) {
    const opts = (_departments.length ? _departments : ["general"]).map(d =>
      `<option value="${escapeHtml(d)}" ${d === selected ? "selected" : ""}>${escapeHtml(d)}</option>`).join("");
    return opts;
  }

  const newUserBtn = document.getElementById("newUserBtn");
  if (newUserBtn) {
    newUserBtn.onclick = () => {
      modal({
        title: t("Yeni calisan hesabi"),
        body: `
          <label>${t("Kullanici adi")} <input id="nu_user" placeholder="${t("orn: ahmet.yilmaz")}" autocomplete="off" /></label>
          <label>${t("Gecici sifre (en az 6 karakter)")} <input id="nu_pass" type="text" autocomplete="off" /></label>
          <label>${t("Departman")} <select id="nu_dept">${deptOptions("general")}</select></label>
          <label>${t("Rol")} <select id="nu_role"><option value="user">${t("Kullanici")}</option><option value="admin">${t("Yonetici")}</option></select></label>
          <label>${t("Etiket (gorunen ad)")} <input id="nu_label" placeholder="${t("orn: Ahmet Yilmaz")}" /></label>
          <p class="muted" style="font-size:0.78rem;">${t('Calisana kullanici adi + gecici sifreyi iletin; ilk giriste "Sifre degistir" ile kendi sifresini belirlemesini isteyin.')}</p>
        `,
        primary: t("Olustur"),
        onPrimary: async () => {
          const body = {
            username: document.getElementById("nu_user").value.trim(),
            password: document.getElementById("nu_pass").value,
            department: document.getElementById("nu_dept").value,
            role: document.getElementById("nu_role").value,
            label: document.getElementById("nu_label").value.trim() || null,
          };
          if (!body.username || body.password.length < 6) {
            toast(t("Kullanici adi + en az 6 karakterli sifre gerekli"), "warn"); return;
          }
          try {
            await api("/api/v1/users", { method: "POST", body: JSON.stringify(body) });
            toast(t("Hesap olusturuldu: {u}", { u: body.username }), "ok");
            loadUsersTab();
          } catch (e) { toast(t("Olusturulamadi: {m}", { m: e.message }), "error", 5000); }
        },
      });
    };
  }

  document.querySelector("#usersTable").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-uact]");
    if (!btn) return;
    const username = btn.dataset.u;
    const act = btn.dataset.uact;
    if (act === "pw") {
      modal({
        title: t("Sifre sifirla — {u}", { u: username }),
        body: `<label>${t("Yeni gecici sifre (en az 6 karakter)")} <input id="rp_pass" type="text" autocomplete="off" /></label>`,
        primary: t("Sifirla"),
        onPrimary: async () => {
          const pw = document.getElementById("rp_pass").value;
          if (pw.length < 6) { toast(t("En az 6 karakter"), "warn"); return; }
          try {
            await api(`/api/v1/users/${encodeURIComponent(username)}`, {
              method: "PUT", body: JSON.stringify({ new_password: pw }),
            });
            toast(t("Sifre sifirlandi"), "ok");
          } catch (err) { toast(t("Hata: {m}", { m: err.message }), "error", 5000); }
        },
      });
    } else if (act === "edit") {
      modal({
        title: t("Duzenle — {u}", { u: username }),
        body: `
          <label>${t("Departman")} <select id="eu_dept">${deptOptions("")}</select></label>
          <label>${t("Rol")} <select id="eu_role"><option value="user">${t("Kullanici")}</option><option value="admin">${t("Yonetici")}</option></select></label>
          <label>${t("Etiket")} <input id="eu_label" placeholder="${t("(degistirmemek icin bos birak)")}" /></label>
        `,
        primary: t("Kaydet"),
        onPrimary: async () => {
          const body = {
            department: document.getElementById("eu_dept").value,
            role: document.getElementById("eu_role").value,
          };
          const lbl = document.getElementById("eu_label").value.trim();
          if (lbl) body.label = lbl;
          try {
            await api(`/api/v1/users/${encodeURIComponent(username)}`, {
              method: "PUT", body: JSON.stringify(body),
            });
            toast(t("Guncellendi — kullanici yeniden giris yapinca gecerli olur"), "ok", 4500);
            loadUsersTab();
          } catch (err) { toast(t("Hata: {m}", { m: err.message }), "error", 5000); }
        },
      });
    } else if (act === "del") {
      if (!confirm(t("'{u}' hesabi ve TUM kisisel verisi (KVKK) silinsin mi? Geri alinamaz.", { u: username }))) return;
      try {
        await api(`/api/v1/users/${encodeURIComponent(username)}`, { method: "DELETE" });
        toast(t("Hesap silindi"), "ok");
        loadUsersTab();
      } catch (err) { toast(t("Hata: {m}", { m: err.message }), "error", 5000); }
    }
  });

  loadUsersTab();

  // --- Usage ---
  try {
    const g = await api("/api/v1/usage/global");
    const tbu = document.querySelector("#globalUsers tbody");
    tbu.innerHTML = "";
    for (const row of (g.users || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(row.username)}</td><td>${row.requests}</td><td>${row.tokens}</td>`;
      tbu.appendChild(tr);
    }
    if (!(g.users || []).length) tbu.innerHTML = `<tr><td colspan="3" class="muted">${t("Henuz veri yok")}</td></tr>`;
    const tbm = document.querySelector("#globalModels tbody");
    tbm.innerHTML = "";
    for (const row of (g.models || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(row.model_id)}</td><td>${row.requests}</td><td>${row.avg_latency_ms ? Math.round(row.avg_latency_ms) : "—"}</td>`;
      tbm.appendChild(tr);
    }
    if (!(g.models || []).length) tbm.innerHTML = `<tr><td colspan="3" class="muted">${t("Henuz veri yok")}</td></tr>`;
  } catch (e) { console.error(e); }

  // --- Audit ---
  try {
    const a = await api("/api/v1/audit?limit=100");
    const tb = document.querySelector("#auditTable tbody");
    tb.innerHTML = "";
    for (const row of (a.entries || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="muted">${row.timestamp?.replace("T", " ").slice(0, 19)}</td>
        <td>${escapeHtml(row.username)}</td>
        <td>${escapeHtml(row.department)}</td>
        <td>${escapeHtml(row.model_id || "—")}</td>
        <td class="muted">${escapeHtml(row.matched_rule || "—")}</td>
        <td>${row.fallback ? `<span class="badge warn">${t("evet")}</span>` : "—"}</td>
        <td>${row.status === "ok" ? '<span class="badge ok">ok</span>' : '<span class="badge error">'+row.status+'</span>'}</td>
        <td>${row.latency_ms ? Math.round(row.latency_ms) : "—"}</td>`;
      tb.appendChild(tr);
    }
    if (!(a.entries || []).length) tb.innerHTML = `<tr><td colspan="8" class="muted">${t("Denetim kaydi bos")}</td></tr>`;
  } catch (e) { console.error(e); }

  // --- Kategori -> model atamasi ---
  const ASSIGN_CATS = [
    { key: "code", label: t("Kodlama") },
    { key: "text", label: t("Metin / genel") },
    { key: "reasoning", label: t("Reasoning / matematik") },
    { key: "persona", label: t("Persona / rol yapma") },
  ];
  let _allModels = [];
  let _assignments = {};

  async function loadCatAssign() {
    try {
      const cfg = await api("/api/v1/system/config");
      _assignments = cfg.category_assignments || {};
      const cat = await api("/api/v1/system/catalog");
      const models = cat.models || {};
      _allModels = Object.entries(models).map(([mid, d]) => ({
        model_id: mid, category: d.category || "text",
      }));
      renderCatAssign();
    } catch (e) { console.error(e); }
  }

  function renderCatAssign() {
    const root = document.getElementById("catAssignList");
    if (!root) return;
    root.innerHTML = "";
    for (const c of ASSIGN_CATS) {
      const inCat = _allModels.filter(m => m.category === c.key);
      const sel = new Set(_assignments[c.key] || []);
      const section = document.createElement("div");
      section.className = "card";
      section.style.marginBottom = "0.75rem";
      section.style.background = "var(--bg-elev)";
      const boxes = inCat.length
        ? inCat.map(m => `
            <label class="checkbox" style="font-size:0.82rem;">
              <input type="checkbox" data-cat="${c.key}" value="${escapeHtml(m.model_id)}" ${sel.has(m.model_id) ? "checked" : ""} />
              ${escapeHtml(m.model_id)}
            </label>`).join("")
        : `<span class="muted" style="font-size:0.82rem;">${t("Bu kategoride katalog modeli yok.")}</span>`;
      section.innerHTML = `
        <h3 style="margin-top:0;">${escapeHtml(c.label)} <span class="muted">${t("({n} secili)", { n: sel.size })}</span></h3>
        <div class="grid three">${boxes}</div>`;
      root.appendChild(section);
    }
  }

  const saveCatBtn = document.getElementById("saveCatAssign");
  if (saveCatBtn) {
    saveCatBtn.onclick = async () => {
      const result = {};
      document.querySelectorAll('#catAssignList input[type=checkbox]:checked').forEach((cb) => {
        (result[cb.dataset.cat] = result[cb.dataset.cat] || []).push(cb.value);
      });
      try {
        await api("/api/v1/system/config", { method: "PUT", body: JSON.stringify({ category_assignments: result }) });
        _assignments = result;
        renderCatAssign();
        toast(t("Kategori atamalari kaydedildi ve plan yenilendi"), "ok");
      } catch (e) { toast(t("Kaydetme hatasi: {m}", { m: e.message }), "error", 5000); }
    };
  }
  loadCatAssign();

  // --- Password modal ---
  document.getElementById("changePwBtn").onclick = () => {
    modal({
      title: t("Sifre degistir"),
      body: `
        <label>${t("Mevcut sifre")} <input type="password" id="pw_current" /></label>
        <label>${t("Yeni sifre (en az 6 karakter)")} <input type="password" id="pw_new" minlength="6" /></label>
        <label>${t("Yeni sifre tekrar")} <input type="password" id="pw_new2" minlength="6" /></label>
      `,
      primary: t("Guncelle"),
      onPrimary: async () => {
        const cur = document.getElementById("pw_current").value;
        const n1 = document.getElementById("pw_new").value;
        const n2 = document.getElementById("pw_new2").value;
        if (!cur || n1.length < 6) { toast(t("Mevcut sifre + en az 6 karakterli yeni sifre"), "warn"); return; }
        if (n1 !== n2) { toast(t("Yeni sifreler eslesmiyor"), "warn"); return; }
        try {
          await api("/api/v1/me/password", { method: "POST", body: JSON.stringify({ current_password: cur, new_password: n1 }) });
          toast(t("Sifre guncellendi"), "ok");
        } catch (e) { toast(t("Hata: {m}", { m: e.message }), "error", 5000); }
      },
    });
  };

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
})();
