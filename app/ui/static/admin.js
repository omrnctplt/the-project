(async function () {
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
      toast("Konfigurasyon kaydedildi, sistem yeniden planladi.", "ok");
      setTimeout(() => location.reload(), 700);
    } catch (err) {
      toast("Kaydetme basarisiz: " + err.message, "error");
    }
  });

  try {
    const u = await api("/api/v1/users");
    const tb = document.querySelector("#usersTable tbody");
    tb.innerHTML = "";
    for (const row of (u.users || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.username}</td>
        <td>${row.department}</td>
        <td>${row.role}</td>
        <td>${row.label || "—"}</td>
        <td>${row.last_login_at || "—"}</td>`;
      tb.appendChild(tr);
    }
  } catch (e) { console.error(e); }

  try {
    const g = await api("/api/v1/usage/global");
    const tbu = document.querySelector("#globalUsers tbody");
    tbu.innerHTML = "";
    for (const row of (g.users || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row.username}</td><td>${row.requests}</td><td>${row.tokens}</td>`;
      tbu.appendChild(tr);
    }
    const tbm = document.querySelector("#globalModels tbody");
    tbm.innerHTML = "";
    for (const row of (g.models || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row.model_id}</td><td>${row.requests}</td><td>${row.avg_latency_ms ? row.avg_latency_ms.toFixed(0) : "—"}</td>`;
      tbm.appendChild(tr);
    }
  } catch (e) { console.error(e); }

  // ---- Katalog yonetimi ----
  async function refreshCatalog() {
    try {
      const c = await api("/api/v1/system/catalog");
      const overridden = new Set(c.overridden || []);
      const tb = document.querySelector("#catalogTable tbody");
      tb.innerHTML = "";
      for (const [mid, m] of Object.entries(c.models || {})) {
        const isOverride = overridden.has(mid);
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${mid}</td>
          <td><code>${m.ollama_tag}</code></td>
          <td>${m.category}</td>
          <td>${m.ram_gb || "?"} / ${m.vram_gb || "?"} GB</td>
          <td>${isOverride ? '<span class="badge warn">override</span>' : '<span class="badge plain">yaml</span>'}</td>
          <td>
            <button data-pull="${mid}" class="small">pull</button>
            ${isOverride ? `<button data-del="${mid}" class="small">sil</button>` : ""}
          </td>`;
        tb.appendChild(tr);
      }
      tb.querySelectorAll("button[data-pull]").forEach((b) => {
        b.addEventListener("click", async () => {
          try {
            await api(`/api/v1/system/pull/${encodeURIComponent(b.dataset.pull)}`, { method: "POST" });
            toast(`Pull baslatildi: ${b.dataset.pull}`, "ok");
          } catch (e) { toast("Hata: " + e.message, "error"); }
        });
      });
      tb.querySelectorAll("button[data-del]").forEach((b) => {
        b.addEventListener("click", async () => {
          if (!confirm(`'${b.dataset.del}' override'i silinsin mi?`)) return;
          try {
            await api(`/api/v1/system/catalog/models/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" });
            refreshCatalog();
            toast("Override silindi.", "ok");
          } catch (e) { toast("Hata: " + e.message, "error"); }
        });
      });
    } catch (e) { console.error(e); }
  }
  refreshCatalog();

  document.getElementById("cm_inspect").addEventListener("click", async () => {
    const tag = document.getElementById("cm_ollama_tag").value.trim();
    if (!tag) { toast("Once Ollama tag girin.", "warn"); return; }
    try {
      const r = await api("/api/v1/system/ollama/inspect", { method: "POST", body: JSON.stringify({ ollama_tag: tag }) });
      if (r.estimated_ram_gb) document.getElementById("cm_ram_gb").value = r.estimated_ram_gb;
      if (r.parameter_size) {
        const num = parseFloat(String(r.parameter_size).replace(/[^0-9.]/g, ""));
        if (!isNaN(num)) document.getElementById("cm_parameters_b").value = num;
      }
      toast(`${r.parameter_size || "?"} parametre · ~${r.estimated_ram_gb || "?"} GB`, "ok");
    } catch (e) { toast("Inspect basarisiz: " + e.message, "error", 5000); }
  });

  document.getElementById("catalogForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      model_id: document.getElementById("cm_model_id").value.trim(),
      ollama_tag: document.getElementById("cm_ollama_tag").value.trim(),
      category: document.getElementById("cm_category").value,
      ram_gb: parseFloat(document.getElementById("cm_ram_gb").value),
    };
    const pb = parseFloat(document.getElementById("cm_parameters_b").value);
    const vr = parseFloat(document.getElementById("cm_vram_gb").value);
    const prof = document.getElementById("cm_profile").value.trim();
    if (!isNaN(pb)) body.parameters_b = pb;
    if (!isNaN(vr)) body.vram_gb = vr;
    if (prof) body.profile = prof;
    try {
      await api("/api/v1/system/catalog/models", { method: "POST", body: JSON.stringify(body) });
      refreshCatalog();
      toast("Katalog'a eklendi, plan yenilendi.", "ok");
      e.target.reset();
    } catch (err) { toast("Eklenemedi: " + err.message, "error", 5000); }
  });

  // ---- Sifre degistir ----
  document.getElementById("pwForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      current_password: document.getElementById("pw_current").value,
      new_password: document.getElementById("pw_new").value,
    };
    try {
      await api("/api/v1/me/password", { method: "POST", body: JSON.stringify(body) });
      toast("Sifre guncellendi.", "ok");
      document.getElementById("pwForm").reset();
    } catch (err) { toast("Sifre degistirilemedi: " + err.message, "error", 5000); }
  });

  try {
    const a = await api("/api/v1/audit?limit=100");
    const tb = document.querySelector("#auditTable tbody");
    tb.innerHTML = "";
    for (const row of (a.entries || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.timestamp?.replace("T", " ").slice(0, 19)}</td>
        <td>${row.username}</td>
        <td>${row.department}</td>
        <td>${row.model_id || "—"}</td>
        <td>${row.matched_rule || "—"}</td>
        <td>${row.fallback ? "evet" : "—"}</td>
        <td>${row.status}</td>
        <td>${row.latency_ms ? row.latency_ms.toFixed(0) : "—"}</td>`;
      tb.appendChild(tr);
    }
  } catch (e) { console.error(e); }
})();
