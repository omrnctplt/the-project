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
      toast("Profil kaydedildi ve plan yenilendi.", "ok");
    } catch (err) {
      toast("Kaydetme basarisiz: " + err.message, "error", 5000);
    }
  });

  // --- Users ---
  try {
    const u = await api("/api/v1/users");
    const tb = document.querySelector("#usersTable tbody");
    tb.innerHTML = "";
    for (const row of (u.users || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(row.username)}</td>
        <td>${escapeHtml(row.department)}</td>
        <td><span class="badge plain">${escapeHtml(row.role)}</span></td>
        <td>${escapeHtml(row.label || "—")}</td>
        <td class="muted">${row.last_login_at ? row.last_login_at.replace("T", " ").slice(0, 19) : "—"}</td>`;
      tb.appendChild(tr);
    }
  } catch (e) { console.error(e); }

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
    if (!(g.users || []).length) tbu.innerHTML = `<tr><td colspan="3" class="muted">Henuz veri yok</td></tr>`;
    const tbm = document.querySelector("#globalModels tbody");
    tbm.innerHTML = "";
    for (const row of (g.models || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(row.model_id)}</td><td>${row.requests}</td><td>${row.avg_latency_ms ? Math.round(row.avg_latency_ms) : "—"}</td>`;
      tbm.appendChild(tr);
    }
    if (!(g.models || []).length) tbm.innerHTML = `<tr><td colspan="3" class="muted">Henuz veri yok</td></tr>`;
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
        <td>${row.fallback ? '<span class="badge warn">evet</span>' : "—"}</td>
        <td>${row.status === "ok" ? '<span class="badge ok">ok</span>' : '<span class="badge error">'+row.status+'</span>'}</td>
        <td>${row.latency_ms ? Math.round(row.latency_ms) : "—"}</td>`;
      tb.appendChild(tr);
    }
    if (!(a.entries || []).length) tb.innerHTML = `<tr><td colspan="8" class="muted">Denetim kaydi bos</td></tr>`;
  } catch (e) { console.error(e); }

  // --- Kategori -> model atamasi ---
  const ASSIGN_CATS = [
    { key: "code", label: "Kodlama" },
    { key: "text", label: "Metin / genel" },
    { key: "reasoning", label: "Reasoning / matematik" },
    { key: "persona", label: "Persona / rol yapma" },
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
        : '<span class="muted" style="font-size:0.82rem;">Bu kategoride katalog modeli yok.</span>';
      section.innerHTML = `
        <h3 style="margin-top:0;">${escapeHtml(c.label)} <span class="muted">(${sel.size} secili)</span></h3>
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
        toast("Kategori atamalari kaydedildi ve plan yenilendi", "ok");
      } catch (e) { toast("Kaydetme hatasi: " + e.message, "error", 5000); }
    };
  }
  loadCatAssign();

  // --- Password modal ---
  document.getElementById("changePwBtn").onclick = () => {
    modal({
      title: "Sifre degistir",
      body: `
        <label>Mevcut sifre <input type="password" id="pw_current" /></label>
        <label>Yeni sifre (en az 6 karakter) <input type="password" id="pw_new" minlength="6" /></label>
        <label>Yeni sifre tekrar <input type="password" id="pw_new2" minlength="6" /></label>
      `,
      primary: "Guncelle",
      onPrimary: async () => {
        const cur = document.getElementById("pw_current").value;
        const n1 = document.getElementById("pw_new").value;
        const n2 = document.getElementById("pw_new2").value;
        if (!cur || n1.length < 6) { toast("Mevcut sifre + en az 6 karakterli yeni sifre", "warn"); return; }
        if (n1 !== n2) { toast("Yeni sifreler eslesmiyor", "warn"); return; }
        try {
          await api("/api/v1/me/password", { method: "POST", body: JSON.stringify({ current_password: cur, new_password: n1 }) });
          toast("Sifre guncellendi", "ok");
        } catch (e) { toast("Hata: " + e.message, "error", 5000); }
      },
    });
  };

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
})();
