(async function () {
  const badge = document.getElementById("readyBadge");
  try {
    const ready = await fetch("/readyz").then((r) => r.json());
    badge.textContent = ready.ready ? "Sistem hazir" : "Sistem hazirlaniyor...";
    badge.className = "badge " + (ready.ready ? "ok" : "warn");
  } catch (e) {
    badge.textContent = "Baglanti hatasi";
    badge.className = "badge error";
  }

  try {
    const profile = await api("/api/v1/system/profile");
    const hw = profile.hardware || {};
    const cap = profile.capacity || {};

    kvRows(document.getElementById("hwTable"), [
      ["Platform", `${hw.platform?.system || "?"} ${hw.platform?.release || ""}`],
      ["CPU (fiziksel / mantiksal)", `${hw.cpu?.physical_cores || "?"} / ${hw.cpu?.logical_cores || "?"}`],
      ["CPU max frekans (MHz)", fmtNumber(hw.cpu?.max_frequency_mhz, 0)],
      ["RAM toplam (GB)", fmtNumber(hw.memory?.effective_total_gb, 2)],
      ["RAM kullanilabilir (GB)", fmtNumber(hw.memory?.available_gb, 2)],
      ["GPU", hw.gpu?.available ? `${hw.gpu.devices.length} adet (${hw.gpu.devices.map(g => g.name).join(", ")})` : "Yok"],
      ["VRAM toplam (GB)", hw.gpu?.available ? fmtNumber(hw.gpu.vram_total_gb, 2) : "—"],
      ["Disk bos (GB)", fmtNumber(hw.disk?.free_gb, 2)],
    ]);

    kvRows(document.getElementById("capTable"), [
      ["Hizlandirici", cap.accelerator?.toUpperCase()],
      ["Toplam butce (GB)", fmtNumber(cap.budget_total_gb, 2)],
      ["Kullanilan butce (GB)", fmtNumber(cap.budget_used_gb, 2)],
      ["Aktif model sayisi", (cap.active_models || []).length],
      ["Maks. es zamanli istek", cap.max_concurrent_requests],
      ["Beklenen kullanici", cap.expected_users],
      ["Es zamanlilik", cap.expected_concurrency],
      ["Uyarilar", (cap.warnings || []).join(" · ") || "—"],
    ]);
  } catch (e) {
    console.error(e);
  }

  try {
    const models = await api("/api/v1/models");
    const tb = document.querySelector("#modelsTable tbody");
    tb.innerHTML = "";
    for (const s of (models.states || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${s.model_id}<br><small class="muted">${s.ollama_tag}</small></td>
        <td>${s.category}</td>
        <td><span class="badge ${badgeClass(s.status)}">${s.status}</span></td>
        <td>${s.pulled ? "Evet" : "Hayir"}</td>
        <td>${s.inflight_requests}</td>
        <td>${s.total_requests}</td>
        <td>${s.avg_latency_ms ? fmtNumber(s.avg_latency_ms, 1) : "—"}</td>
      `;
      tb.appendChild(tr);
    }
  } catch (e) {
    console.error(e);
  }

  try {
    const usage = await api("/api/v1/usage/me");
    kvRows(document.getElementById("usageTable"), [
      ["Kullanici", usage.username],
      ["Departman", usage.department],
      ["Toplam istek", usage.total_requests],
      ["Toplam token", usage.total_tokens],
      ["Ort. gecikme (ms)", usage.avg_latency_ms ? fmtNumber(usage.avg_latency_ms, 1) : "—"],
    ]);
    const tb2 = document.querySelector("#usageByModel tbody");
    tb2.innerHTML = "";
    for (const [m, c] of Object.entries(usage.by_model || {})) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${m}</td><td>${c}</td>`;
      tb2.appendChild(tr);
    }
  } catch (e) {
    console.error(e);
  }

  function badgeClass(status) {
    if (status === "ready" || status === "loaded") return "ok";
    if (status === "pulling") return "busy";
    if (status === "error") return "error";
    if (status === "passive") return "warn";
    return "";
  }
})();
