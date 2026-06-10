(async function () {
  const badge = document.getElementById("readyBadge");
  try {
    const ready = await fetch("/readyz").then(r => r.json());
    badge.textContent = ready.ready ? "hazir" : "hazirlaniyor";
    badge.className = "badge " + (ready.ready ? "ok" : "warn");
  } catch {
    badge.textContent = "baglanti hatasi";
    badge.className = "badge error";
  }

  let cap = {}, hw = {};
  try {
    const profile = await api("/api/v1/system/profile");
    hw = profile.hardware || {};
    cap = profile.capacity || {};

    document.getElementById("vProfile").textContent = (cap.profile || "?").toUpperCase();
    document.getElementById("vProfileSub").textContent = cap.profile_label
      ? (cap.profile_auto ? "otomatik" : "manuel") + " secildi"
      : "—";

    document.getElementById("vBudget").textContent =
      `${fmtNumber(cap.budget_used_gb, 1)} / ${fmtNumber(cap.budget_total_gb, 1)} GB`;
    document.getElementById("vBudgetSub").textContent = (cap.accelerator || "?").toUpperCase() + " uzerinde";
    const usedPct = cap.budget_total_gb ? cap.budget_used_gb / cap.budget_total_gb : 0;
    document.getElementById("statBudget").className = "stat " + (usedPct > 0.9 ? "error" : usedPct > 0.7 ? "warn" : "ok");

    document.getElementById("vModels").textContent =
      `${(cap.active_models || []).length}/${(cap.active_models || []).length + (cap.passive_models || []).length}`;
    document.getElementById("vModelsSub").textContent = `${cap.max_concurrent_requests || 1} es zamanli`;

    kvRows(document.getElementById("hwTable"), [
      ["Platform", `${hw.platform?.system || "?"} ${hw.platform?.release || ""}`],
      ["CPU", `${hw.cpu?.physical_cores || "?"} fiziksel · ${hw.cpu?.logical_cores || "?"} mantiksal`],
      ["RAM (effective)", `${fmtNumber(hw.memory?.effective_total_gb, 2)} GB`],
      ["GPU", hw.gpu?.available ? `${hw.gpu.devices.length}× ${hw.gpu.devices.map(g => g.name).join(", ")}` : "yok"],
      ["VRAM", hw.gpu?.available ? `${fmtNumber(hw.gpu.vram_total_gb, 2)} GB` : "—"],
      ["Disk bos", `${fmtNumber(hw.disk?.free_gb, 1)} GB`],
    ]);

    kvRows(document.getElementById("capTable"), [
      ["Profil", `${cap.profile_label || cap.profile || "?"}`],
      ["Donanim sinifi", (cap.hardware_tier || "?").toUpperCase()],
      ["Hizlandirici", (cap.accelerator || "?").toUpperCase()],
      ["Bellek butcesi kullanimi", `${fmtNumber(cap.budget_used_gb, 2)} / ${fmtNumber(cap.budget_total_gb, 2)} GB`],
      ["Max yuklu model", cap.max_loaded_models || 1],
      ["Es zamanli istek", cap.max_concurrent_requests || 1],
      ["Beklenen kullanici", cap.expected_users || "—"],
      ["Uyarilar", (cap.warnings || []).length ? (cap.warnings || []).join(" · ") : "—"],
    ]);

    if (window.Charts) {
      Charts.donut(
        document.getElementById("budgetDonut"),
        cap.budget_used_gb || 0, cap.budget_total_gb || 0,
        {
          sub: `${fmtNumber(cap.budget_used_gb, 1)}/${fmtNumber(cap.budget_total_gb, 1)} GB`,
          aria: "Bellek butce kullanim orani",
        }
      );
      const note = document.getElementById("budgetNote");
      if (note) note.textContent =
        `${(cap.accelerator || "?").toUpperCase()} · bos ${fmtNumber(cap.budget_free_gb, 1)} GB`;
    }
  } catch (e) { console.error(e); }

  // Host CPU mini widget (admin only — uses resources endpoint)
  try {
    const res = await api("/api/v1/system/resources");
    if (res?.host) {
      document.getElementById("vCpuHome").textContent = `${fmtNumber(res.host.cpu_percent, 1)} %`;
      document.getElementById("vCpuHomeSub").textContent = `${res.host.cpu_count} cekirdek · bellek ${fmtNumber(res.host.memory_percent, 0)}%`;
      const p = res.host.cpu_percent || 0;
      document.getElementById("statCpu").className = "stat " + (p > 80 ? "error" : p > 60 ? "warn" : "ok");
    }
  } catch { /* normal kullanici icin endpoint visible olabilir */ }

  // Models
  try {
    const models = await api("/api/v1/models");
    const tb = document.querySelector("#modelsTable tbody");
    tb.innerHTML = "";
    const sorted = [...(models.states || [])].sort((a, b) => {
      const rank = (s) => ({ loaded: 0, ready: 1, pulling: 2, unknown: 3, passive: 4, error: 5 }[s.status] ?? 9);
      return rank(a) - rank(b);
    });
    for (const s of sorted.slice(0, 8)) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${s.model_id}</strong><span class="muted">${s.ollama_tag}</span></td>
        <td><span class="badge plain">${s.category}</span></td>
        <td><span class="badge ${badgeClass(s.status)}">${s.status}</span></td>
        <td>${s.inflight_requests}</td>
        <td>${s.total_requests}</td>
        <td>${s.avg_latency_ms ? Math.round(s.avg_latency_ms) + " ms" : "—"}</td>`;
      tb.appendChild(tr);
    }
    if (!sorted.length) {
      tb.innerHTML = `<tr><td colspan="6" class="muted">Henuz model yuklenmemis — <a href="/ui/models">Modeller</a> sayfasindan ekleyin.</td></tr>`;
    } else if (sorted.length > 8) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="6" class="muted"><a href="/ui/models">+ ${sorted.length - 8} model daha — tumune git</a></td>`;
      tb.appendChild(tr);
    }

    if (window.Charts) {
      const counts = {};
      for (const s of (models.states || [])) counts[s.status] = (counts[s.status] || 0) + 1;
      const order = ["loaded", "ready", "pulling", "passive", "unknown", "error"];
      const labelTr = { loaded: "Yuklu", ready: "Hazir", pulling: "Iniyor", passive: "Pasif", unknown: "Bilinmiyor", error: "Hata" };
      const colorOf = { loaded: "var(--ok)", ready: "var(--accent)", pulling: "var(--warn)", passive: "var(--muted-2)", unknown: "var(--surface-3)", error: "var(--danger)" };
      const items = order.filter(k => counts[k]).map(k => ({ label: labelTr[k] || k, value: counts[k], color: colorOf[k] }));
      Charts.bars(document.getElementById("statusBars"), items, { empty: "Henuz model yok" });
    }
  } catch (e) { console.error(e); }

  // Usage
  try {
    const usage = await api("/api/v1/usage/me");
    kvRows(document.getElementById("usageTable"), [
      ["Kullanici", usage.username],
      ["Departman", usage.department],
      ["Toplam istek", usage.total_requests],
      ["Toplam token", usage.total_tokens],
      ["Ort. gecikme", usage.avg_latency_ms ? Math.round(usage.avg_latency_ms) + " ms" : "—"],
    ]);
    const tb2 = document.querySelector("#usageByModel tbody");
    tb2.innerHTML = "";
    const entries = Object.entries(usage.by_model || {});
    if (!entries.length) tb2.innerHTML = `<tr><td colspan="2" class="muted">Henuz veri yok</td></tr>`;
    else {
      for (const [m, c] of entries) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${m}</td><td style="text-align:right; font-variant-numeric:tabular-nums;">${c}</td>`;
        tb2.appendChild(tr);
      }
    }
    if (window.Charts) {
      const items = entries.map(([m, c]) => ({ label: m, value: c }))
        .sort((a, b) => b.value - a.value).slice(0, 6);
      Charts.bars(document.getElementById("usageBars"), items, { empty: "Henuz istek yok" });
    }
  } catch (e) { console.error(e); }

  function badgeClass(status) {
    if (status === "loaded" || status === "ready") return "ok";
    if (status === "pulling") return "busy";
    if (status === "error")   return "error";
    if (status === "passive") return "plain";
    return "plain";
  }
})();
