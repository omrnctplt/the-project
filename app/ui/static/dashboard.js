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
      const rank = (s) => ({ loaded: 0, ready: 1, pulling: 2, queued: 3, unknown: 4, passive: 5, error: 6 }[s.status] ?? 9);
      return rank(a) - rank(b);
    });
    for (const s of sorted.slice(0, 8)) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(s.model_id)}</strong><span class="muted">${escapeHtml(s.ollama_tag)}</span></td>
        <td><span class="badge plain">${escapeHtml(s.category)}</span></td>
        <td><span class="badge ${badgeClass(s.status)}">${escapeHtml(s.status)}</span></td>
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
      const order = ["loaded", "ready", "pulling", "queued", "passive", "unknown", "error"];
      const labelTr = { loaded: "Yuklu", ready: "Hazir", pulling: "Iniyor", queued: "Sirada", passive: "Pasif", unknown: "Bilinmiyor", error: "Hata" };
      const colorOf = { loaded: "var(--ok)", ready: "var(--accent)", pulling: "var(--warn)", queued: "var(--warn)", passive: "var(--muted-2)", unknown: "var(--surface-3)", error: "var(--danger)" };
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
    if (status === "pulling" || status === "queued") return "busy";
    if (status === "error")   return "error";
    if (status === "passive") return "plain";
    return "plain";
  }

  /* ---------- Bellek kokpiti: canli RAM/VRAM yerlesimi ----------
     Diskte olmak != bellekte olmak. Kaynak Ollama /api/ps oldugundan
     gosterilen, tahmin degil gercek yerlesimdir. */
  const isAdmin = (window.currentUser || {}).role === "admin";
  const memGroups = document.getElementById("memGroups");
  const memBar = document.getElementById("memBar");
  const memLegend = document.getElementById("memLegend");
  const memSummary = document.getElementById("memSummary");
  const MEM_PALETTE = ["var(--accent)", "var(--teal)", "var(--warn)", "var(--ok)", "var(--danger)", "var(--muted-2)"];

  const gbOf = (bytes) => (bytes || 0) / 1024 ** 3;
  const fmtGb = (bytes, d = 1) => fmtNumber(gbOf(bytes), d) + " GB";

  async function refreshMemory(force = false) {
    if (!memGroups || (!force && document.hidden)) return;
    let snap;
    try { snap = await api("/api/v1/system/memory"); } catch { return; }
    renderMemory(snap);
  }

  function memRows(list, kind) {
    return list.map(m => {
      const place = m.loaded
        ? [m.vram_bytes ? `GPU ${fmtGb(m.vram_bytes)}` : "", m.ram_bytes ? `RAM ${fmtGb(m.ram_bytes)}` : ""].filter(Boolean).join(" + ")
        : kind === "active"
        ? "bellege yukleniyor…"
        : (m.disk_bytes ? `diskte ${fmtGb(m.disk_bytes)}` : "");
      const extra = kind === "active"
        ? `<span class="badge busy">${m.inflight_requests} istek isleniyor</span>`
        : kind === "warm" && m.expires_in_seconds != null
        ? `<span class="muted mem-exp">~${fmtEta(m.expires_in_seconds)} sonra otomatik bosalir</span>`
        : kind === "warming"
        ? `<span class="spin" aria-hidden="true"></span>`
        : "";
      let act = "";
      if (isAdmin) {
        if (kind === "warm") act = `<button class="small" data-mem="unload" data-mid="${escapeHtml(m.model_id)}">Bellekten cikar</button>`;
        if (kind === "disk") act = `<button class="small" data-mem="load" data-mid="${escapeHtml(m.model_id)}">Bellege yukle</button>`;
      }
      return `<div class="mem-row">
          <span class="mem-dot ${kind}" aria-hidden="true"></span>
          <span class="mem-name">${escapeHtml(m.model_id)}</span>
          <span class="mem-place">${escapeHtml(place)}</span>
          ${extra}
          <span class="mem-act">${act}</span>
        </div>`;
    }).join("");
  }

  function renderMemory(snap) {
    const models = snap.models || [];
    const totals = snap.totals || {};
    const budget = snap.budget || {};
    if (!snap.reachable) {
      memSummary.textContent = "Ollama'ya ulasilamiyor";
      memBar.innerHTML = "";
      memLegend.innerHTML = "";
      memGroups.innerHTML = `<div class="muted mem-empty">Motor (Ollama) erisilebilir oldugunda gercek bellek yerlesimi burada canli gorunur.</div>`;
      return;
    }
    const active = models.filter(m => m.pulled && m.inflight_requests > 0);
    const warming = models.filter(m => m.warming_up && m.inflight_requests === 0);
    const warm = models.filter(m => m.loaded && m.inflight_requests === 0 && !m.warming_up);
    const onDisk = models.filter(m => m.pulled && !m.loaded && !m.warming_up && m.inflight_requests === 0);
    const notPulled = models.filter(m => !m.pulled && !m.warming_up);

    memSummary.textContent =
      `${totals.loaded_count || 0} model bellekte (${fmtGb(totals.memory_bytes)})` +
      (totals.vram_bytes ? ` · GPU'da ${fmtGb(totals.vram_bytes)}` : "") +
      ` · diskte toplam ${fmtGb(totals.disk_bytes)}`;

    const loaded = models.filter(m => m.loaded);
    const budgetBytes = (budget.total_gb || 0) * 1024 ** 3;
    const denom = Math.max(budgetBytes, totals.memory_bytes || 0, 1);
    memBar.innerHTML = loaded.map((m, i) =>
      `<div class="mem-seg" style="width:${Math.max(1, (m.memory_bytes / denom) * 100).toFixed(2)}%; background:${MEM_PALETTE[i % MEM_PALETTE.length]};" title="${escapeHtml(m.model_id)}: ${fmtGb(m.memory_bytes)}"></div>`
    ).join("");
    memLegend.innerHTML =
      loaded.map((m, i) =>
        `<span class="mem-key"><span class="dot" style="background:${MEM_PALETTE[i % MEM_PALETTE.length]};"></span>${escapeHtml(m.model_id)} · ${fmtGb(m.memory_bytes)}</span>`
      ).join("") +
      (budget.total_gb
        ? `<span class="mem-key muted">ayrilan butce: ${fmtNumber(budget.total_gb, 1)} GB (${escapeHtml((budget.accelerator || "?").toUpperCase())})</span>`
        : "");

    const bits = [];
    if (notPulled.length) bits.push(`${notPulled.length} katalog modeli henuz indirilmemis`);
    if ((snap.unmanaged || []).length) {
      bits.push("Katalog disi (Ollama'da): " + snap.unmanaged
        .map(u => `${u.ollama_tag} (${fmtGb(u.disk_bytes)}${u.loaded ? ", bellekte" : ""})`).join(", "));
    }
    const footer = bits.length ? `<div class="muted mem-foot">${escapeHtml(bits.join(" · "))}</div>` : "";

    const groups = [
      { key: "active", title: "Aktif calisiyor", list: active, empty: "Su anda istek isleyen model yok." },
      { key: "warming", title: "Bellege yukleniyor", list: warming, hideEmpty: true },
      { key: "warm", title: "Bellekte hazir (sicak)", list: warm, empty: "Bellekte bekleyen model yok — ilk istekte otomatik yuklenir." },
      { key: "disk", title: "Diskte hazir (bellekte degil)", list: onDisk, empty: "Indirilmis ama bellekte olmayan model yok." },
    ];
    memGroups.innerHTML = groups.map(g => {
      if (g.hideEmpty && !g.list.length) return "";
      return `<div class="mem-group">
          <div class="mem-group-title">${g.title} <span class="count">${g.list.length}</span></div>
          ${g.list.length ? memRows(g.list, g.key) : `<div class="muted mem-empty">${g.empty}</div>`}
        </div>`;
    }).join("") + footer;
  }

  if (memGroups) {
    memGroups.addEventListener("click", async (e) => {
      const btn = e.target.closest("button[data-mem]");
      if (!btn) return;
      btn.disabled = true;
      const mid = btn.dataset.mid;
      try {
        if (btn.dataset.mem === "load") {
          await api(`/api/v1/system/models/${encodeURIComponent(mid)}/load`, { method: "POST" });
          toast(`${mid} bellege yukleniyor — hazir olunca "sicak" grubuna gecer`, "ok", 4000);
        } else {
          await api(`/api/v1/system/models/${encodeURIComponent(mid)}/unload`, { method: "POST" });
          toast(`${mid} bellekten cikarildi (disk kopyasi duruyor)`, "ok", 4000);
        }
        setTimeout(refreshMemory, 600);
      } catch (err) {
        toast("Hata: " + err.message, "error", 5000);
        btn.disabled = false;
      }
    });
    refreshMemory(true);
    setInterval(() => refreshMemory(), 4000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshMemory(); });
  }
})();
