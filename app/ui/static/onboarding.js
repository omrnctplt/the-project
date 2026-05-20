(async function () {
  // HW + budget
  let profile = null;
  try {
    profile = await api("/api/v1/system/profile");
  } catch (e) { toast("Profil alinamadi: " + e.message, "error"); return; }
  const hw = profile.hardware || {};
  const cap = profile.capacity || {};

  const hwStats = document.getElementById("hwStats");
  hwStats.innerHTML = `
    <div class="stat">
      <div class="stat-label">CPU</div>
      <div class="stat-value">${hw.cpu?.logical_cores || "?"}</div>
      <div class="stat-sub">${hw.cpu?.physical_cores || "?"} fiziksel cekirdek</div>
    </div>
    <div class="stat">
      <div class="stat-label">Bellek (effective)</div>
      <div class="stat-value">${fmtNumber(hw.memory?.effective_total_gb, 1)} GB</div>
      <div class="stat-sub">${hw.memory?.effective_source || "—"}</div>
    </div>
    <div class="stat ${hw.gpu?.available ? "ok" : "warn"}">
      <div class="stat-label">GPU</div>
      <div class="stat-value">${hw.gpu?.available ? fmtNumber(hw.gpu.vram_total_gb, 1) + " GB" : "yok"}</div>
      <div class="stat-sub">${hw.gpu?.available ? (hw.gpu.devices[0]?.name || "") : "CPU modunda yavas olabilir"}</div>
    </div>`;

  const accel = cap.accelerator || "cpu";
  const maxFit = parseFloat(cap.budget_free_gb || cap.budget_total_gb || 0);

  // Recommended models
  const recs = await api("/api/v1/system/discover");
  const list = document.getElementById("recList");
  const filter = document.getElementById("recCatFilter");
  let currentCat = "";

  function render() {
    list.innerHTML = "";
    const items = (recs.models || []).filter(m =>
      !currentCat || m.category === currentCat
    );
    // Once sigan + kategori bazli ekleyelim
    items.sort((a, b) => a.approx_gb - b.approx_gb);
    let recommendedFlagged = false;
    for (const m of items) {
      const fits = m.approx_gb <= maxFit + 0.01;
      const card = document.createElement("div");
      let cls = "model-card";
      if (m.in_catalog) cls += " in-catalog";
      if (fits) cls += " fits-current";
      card.className = cls;
      const recBadge = (!recommendedFlagged && fits && m.category === "fallback")
        ? '<span class="badge ok">onerilen baslangic</span>' : "";
      if (recBadge) recommendedFlagged = true;
      card.innerHTML = `
        <div class="head">
          <div>
            <div class="label">${escapeHtml(m.label)}</div>
            <div class="tag">${escapeHtml(m.tag)}</div>
          </div>
          <span class="badge plain">${escapeHtml(m.category)}</span>
        </div>
        <div class="blurb">${escapeHtml(m.blurb || "")}</div>
        <div class="meta">
          <span class="badge plain">~${m.approx_gb} GB</span>
          ${fits ? '<span class="badge ok">butceye sigar</span>' : '<span class="badge warn">butce yetersiz</span>'}
          ${m.in_catalog ? '<span class="badge busy">katalogda</span>' : ''}
          ${recBadge}
        </div>
        <div class="actions">
          <button class="primary" data-tag="${escapeHtml(m.tag)}" data-cat="${m.category}" data-gb="${m.approx_gb}" data-label="${escapeHtml(m.label)}" ${fits ? "" : "disabled"}>
            ${m.in_catalog ? "Pull et" : "Ekle ve pull et"}
          </button>
          <button data-skip="1" class="ghost">Atlat</button>
        </div>`;
      list.appendChild(card);
    }
    if (!items.length) {
      list.innerHTML = `<div class="muted" style="grid-column:1/-1; padding:2rem;">Bu kategoride oneri yok.</div>`;
    }
  }
  render();

  filter.addEventListener("click", (e) => {
    if (!e.target.matches("button[data-cat]")) return;
    filter.querySelectorAll("button").forEach(b => b.classList.remove("active"));
    e.target.classList.add("active");
    currentCat = e.target.dataset.cat || "";
    render();
  });

  list.addEventListener("click", async (e) => {
    if (e.target.dataset.skip === "1") {
      location.href = "/ui/chat";
      return;
    }
    const btn = e.target.closest("button[data-tag]");
    if (!btn) return;
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = "Ekleniyor...";
    try {
      // Generate ID from tag
      const tag = btn.dataset.tag;
      const modelId = tag.replace(/[:.]/g, "-").replace(/[^a-zA-Z0-9._\-]/g, "");
      const category = btn.dataset.cat;
      const ram = parseFloat(btn.dataset.gb);
      // Try add to catalog (idempotent — if exists, just pull)
      try {
        await api("/api/v1/system/catalog/models", {
          method: "POST",
          body: JSON.stringify({
            model_id: modelId,
            ollama_tag: tag,
            category,
            ram_gb: ram,
            vram_gb: ram,
            profile: btn.dataset.label,
          }),
        });
      } catch (e) {
        // Might already exist — that's fine
      }
      // Trigger pull
      await api(`/api/v1/system/pull/${encodeURIComponent(modelId)}`, { method: "POST" });
      toast(`Pull baslatildi: ${btn.dataset.label}`, "ok");
      btn.textContent = "Pull baslatildi ✓";
      setTimeout(() => { location.href = "/ui/chat"; }, 1200);
    } catch (err) {
      toast("Hata: " + err.message, "error", 5000);
      btn.disabled = false;
      btn.textContent = original;
    }
  });
})();
