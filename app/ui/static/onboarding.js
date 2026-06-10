(async function () {
  const isAdmin = (window.currentUser || {}).role === "admin";
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

  const recHint = document.getElementById("recHint");
  if (recHint) {
    recHint.textContent = `Donanim sinifiniz: ${(cap.hardware_tier || "?").toUpperCase()} · ${(accel || "?").toUpperCase()}`;
  }

  if (!isAdmin) {
    const notice = document.createElement("div");
    notice.className = "card";
    notice.style.cssText = "margin:0.75rem 0 1rem; border-left:3px solid var(--warn);";
    notice.innerHTML = `
      <strong>Sistemde henuz kurulu model yok.</strong>
      <p class="muted" style="margin:0.4rem 0 0.6rem;">Model kurulumu yonetici yetkisi gerektirir.
      Asagidaki liste donaniminiza uygun modelleri gosterir; kurulum icin yoneticinize iletebilirsiniz.</p>
      <a href="/ui/dashboard" class="nav-item" style="display:inline-block;">Panele don →</a>`;
    list.parentElement.insertBefore(notice, list);
  }

  function render() {
    list.innerHTML = "";
    // Backend zaten onerilenleri basa koydu; kategori filtresi uygula
    const items = (recs.models || []).filter(m => !currentCat || m.category === currentCat);
    for (const m of items) {
      const fits = m.fits;
      const card = document.createElement("div");
      let cls = "model-card";
      if (m.recommended) cls += " in-catalog";
      if (fits) cls += " fits-current";
      card.className = cls;
      const recBadge = m.recommended ? '<span class="badge ok">donaniminiza onerilen</span>' : "";
      const srcBadge = m.source === "huggingface" ? '<span class="badge busy">HF</span>' : "";
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
          <span class="badge plain">${escapeHtml(m.tier)}</span>
          ${fits ? '<span class="badge ok">butceye sigar</span>' : '<span class="badge warn">butce yetersiz</span>'}
          ${srcBadge}
          ${recBadge}
        </div>
        <div class="actions">
          ${isAdmin ? `
          <button class="primary" data-tag="${escapeHtml(m.tag)}" data-mid="${escapeHtml(m.model_id || "")}" data-cat="${m.category}" data-gb="${m.approx_gb}" data-label="${escapeHtml(m.label)}" ${fits ? "" : "disabled"}>
            ${m.pulled ? "Indirilmis ✓" : "Ekle ve pull et"}
          </button>
          <button data-skip="1" class="ghost">Atlat</button>
          ` : `
          <span class="muted" style="font-size:0.78rem;">${m.pulled ? "Kurulu ✓" : "Kurulum yonetici yetkisi gerektirir"}</span>
          `}
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
      const tag = btn.dataset.tag;
      // Katalogdaki gercek id'yi kullan; yoksa ortak kuralla turet (mukerrer kayit onlenir)
      const modelId = btn.dataset.mid || tagToModelId(tag);
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
