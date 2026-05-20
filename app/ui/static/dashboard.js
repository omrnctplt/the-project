(async function () {
  const badge = document.getElementById("readyBadge");
  try {
    const ready = await fetch("/readyz").then((r) => r.json());
    badge.textContent = ready.ready ? "hazir" : "hazirlaniyor";
    badge.className = "badge " + (ready.ready ? "ok" : "warn");
  } catch (e) {
    badge.textContent = "baglanti hatasi";
    badge.className = "badge error";
  }

  let cap = {};
  let hw = {};
  try {
    const profile = await api("/api/v1/system/profile");
    hw = profile.hardware || {};
    cap = profile.capacity || {};

    /* ---- stat cards ---- */
    document.getElementById("vProfile").textContent = (cap.profile || "?").toUpperCase();
    document.getElementById("vProfileSub").textContent = cap.profile_label
      ? `${cap.profile_auto ? "otomatik" : "manuel"} secildi`
      : "—";

    const budget = `${fmtNumber(cap.budget_used_gb, 1)} / ${fmtNumber(cap.budget_total_gb, 1)} GB`;
    document.getElementById("vBudget").textContent = budget;
    document.getElementById("vBudgetSub").textContent =
      (cap.accelerator || "?").toUpperCase() + " uzerinde";

    document.getElementById("vModels").textContent =
      `${(cap.active_models || []).length}/${(cap.active_models || []).length + (cap.passive_models || []).length}`;
    document.getElementById("vModelsSub").textContent = `${cap.max_concurrent_requests || 1} es zamanli istek`;

    const statBudget = document.getElementById("statBudget");
    const usedPct = cap.budget_total_gb ? cap.budget_used_gb / cap.budget_total_gb : 0;
    statBudget.className = "stat " + (usedPct > 0.9 ? "error" : usedPct > 0.7 ? "warn" : "ok");

    /* ---- hardware table ---- */
    kvRows(document.getElementById("hwTable"), [
      ["Platform", `${hw.platform?.system || "?"} ${hw.platform?.release || ""}`],
      ["CPU", `${hw.cpu?.physical_cores || "?"} fiziksel · ${hw.cpu?.logical_cores || "?"} mantiksal`],
      ["CPU max freq", hw.cpu?.max_frequency_mhz ? `${fmtNumber(hw.cpu.max_frequency_mhz, 0)} MHz` : "—"],
      ["RAM (effective)", `${fmtNumber(hw.memory?.effective_total_gb, 2)} GB`],
      ["RAM kaynak", hw.memory?.effective_source || "—"],
      ["RAM available", `${fmtNumber(hw.memory?.available_gb, 2)} GB`],
      ["GPU", hw.gpu?.available
        ? `${hw.gpu.devices.length}× ${hw.gpu.devices.map((g) => g.name).join(", ")}`
        : "yok"],
      ["VRAM", hw.gpu?.available ? `${fmtNumber(hw.gpu.vram_total_gb, 2)} GB` : "—"],
      ["Disk bos", `${fmtNumber(hw.disk?.free_gb, 1)} GB`],
    ]);

    /* ---- capacity table ---- */
    kvRows(document.getElementById("capTable"), [
      ["Profil", `${cap.profile_label || cap.profile || "?"}`],
      ["Profil secimi", cap.profile_auto ? "otomatik" : "manuel"],
      ["Hizlandirici", (cap.accelerator || "?").toUpperCase()],
      ["Toplam butce", `${fmtNumber(cap.budget_total_gb, 2)} GB`],
      ["Kullanilan", `${fmtNumber(cap.budget_used_gb, 2)} GB`],
      ["Bos", `${fmtNumber(cap.budget_free_gb, 2)} GB`],
      ["Aktif model", (cap.active_models || []).length],
      ["Max yuklu", cap.max_loaded_models || 1],
      ["Es zamanli istek", cap.max_concurrent_requests || 1],
      ["Beklenen kullanici", cap.expected_users || "—"],
      ["Uyarilar", (cap.warnings || []).length
        ? (cap.warnings || []).join(" · ")
        : "—"],
    ]);
  } catch (e) {
    console.error(e);
    toast("Sistem profili alinamadi", "error");
  }

  /* ---- models table ---- */
  try {
    const models = await api("/api/v1/models");
    const tb = document.querySelector("#modelsTable tbody");
    tb.innerHTML = "";
    const sorted = [...(models.states || [])].sort((a, b) => {
      const rank = (s) => ({ loaded: 0, ready: 1, pulling: 2, unknown: 3, passive: 4, error: 5 }[s.status] ?? 9);
      return rank(a) - rank(b);
    });
    for (const s of sorted) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>
          <strong>${s.model_id}</strong>
          <span class="muted">${s.ollama_tag}</span>
        </td>
        <td><span class="badge plain">${s.category}</span></td>
        <td><span class="badge ${badgeClass(s.status)}">${s.status}</span></td>
        <td>${s.inflight_requests}</td>
        <td>${s.total_requests}</td>
        <td>${s.avg_latency_ms ? fmtNumber(s.avg_latency_ms, 0) + " ms" : "—"}</td>`;
      tb.appendChild(tr);
    }
    if (!sorted.length) {
      tb.innerHTML = `<tr><td colspan="6" class="muted">Henuz hicbir model kayitli degil.</td></tr>`;
    }
  } catch (e) { console.error(e); }

  /* ---- usage ---- */
  try {
    const usage = await api("/api/v1/usage/me");
    kvRows(document.getElementById("usageTable"), [
      ["Kullanici", usage.username],
      ["Departman", usage.department],
      ["Toplam istek", usage.total_requests],
      ["Toplam token", usage.total_tokens],
      ["Ort. gecikme", usage.avg_latency_ms ? fmtNumber(usage.avg_latency_ms, 0) + " ms" : "—"],
    ]);
    const tb2 = document.querySelector("#usageByModel tbody");
    tb2.innerHTML = "";
    const entries = Object.entries(usage.by_model || {});
    if (!entries.length) {
      tb2.innerHTML = `<tr><td colspan="2" class="muted">Henuz veri yok.</td></tr>`;
    } else {
      for (const [m, c] of entries) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${m}</td><td style="text-align:right; font-variant-numeric:tabular-nums;">${c}</td>`;
        tb2.appendChild(tr);
      }
    }
  } catch (e) { console.error(e); }

  function badgeClass(status) {
    if (status === "loaded" || status === "ready") return "ok";
    if (status === "pulling") return "busy";
    if (status === "error")   return "error";
    if (status === "passive") return "warn";
    return "plain";
  }
})();
