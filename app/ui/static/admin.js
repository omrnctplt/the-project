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
      alert("Konfigurasyon kaydedildi. Sistem yeniden planladi.");
      location.reload();
    } catch (err) {
      alert("Kaydetme basarisiz: " + err.message);
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
