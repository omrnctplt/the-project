(async function () {
  let timer = null;
  let failStreak = 0;

  function setOfflineBanner(on, msg) {
    let b = document.getElementById("resOffline");
    if (on) {
      if (!b) {
        b = document.createElement("div");
        b.id = "resOffline";
        b.className = "card";
        b.style.cssText = "border-left:3px solid var(--danger); margin-bottom:0.75rem;";
        const main = document.querySelector("main") || document.body;
        main.insertBefore(b, main.firstChild);
      }
      b.innerHTML = `<strong>Kaynak verisi alinamiyor.</strong> <span class="muted">${escapeHtml(msg || "")} — otomatik yeniden denenecek.</span>`;
    } else if (b) {
      b.remove();
    }
  }

  async function refresh() {
    try {
      const r = await api("/api/v1/system/resources");
      if (failStreak >= 3) restartTimer(5000);
      failStreak = 0;
      setOfflineBanner(false);
      render(r);
    } catch (e) {
      failStreak++;
      if (failStreak === 1) toast("Kaynak verisi alinamadi: " + e.message, "error");
      setOfflineBanner(true, e.message);
      if (failStreak === 3) restartTimer(20000);
    }
  }

  function restartTimer(ms) {
    if (!timer) return;
    clearInterval(timer);
    timer = setInterval(refresh, ms);
  }

  function render(d) {
    const h = d.host || {};

    // CPU
    document.getElementById("vCpu").textContent = fmtNumber(h.cpu_percent, 1) + " %";
    document.getElementById("vCpuSub").textContent = (h.cpu_count || "?") + " cekirdek";
    barColor("statCpu", "vCpuBar", h.cpu_percent || 0);
    setTemp("tempCpu", h.cpu_temp_c, "cpu");

    // Memory
    document.getElementById("vMem").textContent = `${fmtNumber(h.memory_used_gb, 1)} / ${fmtNumber(h.memory_total_gb, 1)} GB`;
    document.getElementById("vMemSub").textContent = fmtNumber(h.memory_percent, 1) + " % dolu";
    barColor("statMem", "vMemBar", h.memory_percent || 0);

    // Disk
    document.getElementById("vDisk").textContent = `${fmtNumber(h.disk_total_gb - h.disk_free_gb, 1)} / ${fmtNumber(h.disk_total_gb, 1)} GB`;
    document.getElementById("vDiskSub").textContent = fmtNumber(h.disk_percent, 1) + " % dolu · " + fmtNumber(h.disk_free_gb, 1) + " GB bos";
    barColor("statDisk", "vDiskBar", h.disk_percent || 0);
    setTemp("tempDisk", h.disk_temp_c, "disk");

    // GPU'lar (varsa)
    renderGpus(d.gpus || []);

    // Actions
    const actDiv = document.getElementById("actionList");
    actDiv.innerHTML = "";
    for (const a of (d.actions || [])) {
      const div = document.createElement("div");
      div.className = "action-pill " + (a.severity === "error" ? "error" : "");
      div.innerHTML = `<div><div class="title">${escapeHtml(a.title)}</div><div class="detail">${escapeHtml(a.detail)}</div></div>`;
      actDiv.appendChild(div);
    }

    // Containers
    const cardC = document.getElementById("containersCard");
    const tbc = document.querySelector("#containersTable tbody");
    tbc.innerHTML = "";
    if (!d.containers || !d.containers.length) {
      cardC.style.display = "none";
    } else {
      cardC.style.display = "";
      for (const c of d.containers) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${escapeHtml(c.name)}</td>
          <td>${escapeHtml(c.cpu_percent)}</td>
          <td>${escapeHtml(c.memory_usage)}</td>
          <td>${escapeHtml(c.memory_percent)}</td>
          <td>${escapeHtml(c.net_io)}</td>
          <td>${escapeHtml(c.block_io)}</td>`;
        tbc.appendChild(tr);
      }
    }

    // Top processes
    const tbCpu = document.getElementById("cpuTable");
    tbCpu.innerHTML = "";
    for (const p of (d.top_cpu || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(p.name)}</td><td>${p.pid}</td><td>${escapeHtml(p.user || "")}</td><td>${p.cpu_percent} %</td><td>${fmtBytes(p.memory_mb)}</td>`;
      tbCpu.appendChild(tr);
    }
    const tbMem = document.getElementById("memTable");
    tbMem.innerHTML = "";
    for (const p of (d.top_mem || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(p.name)}</td><td>${p.pid}</td><td>${escapeHtml(p.user || "")}</td><td>${p.memory_percent} %</td><td>${fmtBytes(p.memory_mb)}</td>`;
      tbMem.appendChild(tr);
    }
  }

  function setTemp(slotId, tempC, kind) {
    const slot = document.getElementById(slotId);
    if (!slot) return;
    slot.innerHTML = (window.Charts && Charts.tempGauge) ? Charts.tempGauge(tempC, kind) : "";
  }

  function renderGpus(gpus) {
    const sec = document.getElementById("gpuSection");
    if (!sec) return;
    if (!gpus.length) { sec.style.display = "none"; return; }
    sec.style.display = "";
    sec.innerHTML = gpus.map(g => {
      const vramPct = g.vram_percent || 0;
      const utilPct = g.util_percent;
      const cls = vramPct > 90 ? "error" : vramPct > 75 ? "warn" : "ok";
      const gauge = (window.Charts && Charts.tempGauge) ? Charts.tempGauge(g.temperature_c, "gpu") : "";
      const subBits = [];
      if (utilPct != null) subBits.push(`kullanim %${fmtNumber(utilPct, 0)}`);
      if (g.power_w != null) subBits.push(`${fmtNumber(g.power_w, 0)} W`);
      return `
      <div class="stat ${cls}">
        ${gauge ? `<div class="temp-slot">${gauge}</div>` : ""}
        <div class="stat-label">GPU ${g.index} · ${escapeHtml(g.name || "?")}</div>
        <div class="stat-value">${fmtNumber(g.vram_used_gb, 1)} / ${fmtNumber(g.vram_total_gb, 1)} GB</div>
        <div class="stat-sub">VRAM %${fmtNumber(vramPct, 1)}${subBits.length ? " · " + subBits.join(" · ") : ""}</div>
        <div class="progress ${vramPct > 90 ? "error" : vramPct > 75 ? "warn" : ""}" style="margin-top:0.6rem;">
          <div class="bar" style="width:${Math.min(100, vramPct)}%"></div>
        </div>
        ${utilPct != null ? `
        <div class="muted" style="font-size:0.7rem; margin-top:0.45rem; display:flex; justify-content:space-between;"><span>GPU kullanimi</span><span>%${fmtNumber(utilPct, 0)}</span></div>
        <div class="progress" style="margin-top:0.2rem;"><div class="bar" style="width:${Math.min(100, utilPct)}%"></div></div>` : ""}
      </div>`;
    }).join("");
  }

  function barColor(statId, barId, pct) {
    const stat = document.getElementById(statId);
    const bar = document.getElementById(barId);
    bar.style.width = Math.min(100, pct) + "%";
    const prog = bar.parentElement;
    prog.className = "progress" + (pct > 90 ? " error" : pct > 75 ? " warn" : "");
    stat.className = "stat " + (pct > 90 ? "error" : pct > 75 ? "warn" : "ok");
  }

  // Tabs
  document.querySelector(".tabs").addEventListener("click", (e) => {
    if (!e.target.matches("button[data-tab]")) return;
    const t = e.target.dataset.tab;
    document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("active", p.dataset.panel === t));
  });

  document.getElementById("refreshBtn").onclick = refresh;
  document.getElementById("autoRefresh").addEventListener("change", (e) => {
    if (timer) { clearInterval(timer); timer = null; }
    if (e.target.checked) timer = setInterval(refresh, 5000);
  });

  refresh();
  timer = setInterval(refresh, 5000);

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
})();
