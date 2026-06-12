(async function () {
  const isAdmin = (window.currentUser || {}).role === "admin";
  let catalog = {};        // model_id -> def
  let states = [];         // orchestrator states
  let discover = [];       // populer modeller
  let remote = [];         // canli kesif (ollama.com + HF)
  let remoteMeta = {};
  let capacity = {};
  let overridden = [];     // kullanici tarafindan eklenen (silinebilir) model id'leri
  let q = "";
  let cat = "";
  let st = "";
  let remoteProv = "";
  let remoteFit = "";
  let pollTimer = null;

  const acc = document.getElementById("accordion");
  const searchInput = document.getElementById("searchInput");
  const catFilter = document.getElementById("catFilter");
  const statusFilter = document.getElementById("statusFilter");
  const remoteGrid = document.getElementById("remoteGrid");
  const remoteMetaEl = document.getElementById("remoteMeta");

  async function refresh() {
    if (!acc.children.length) {
      acc.innerHTML = `<div class="model-grid">${Array.from({ length: 6 }, () =>
        `<div class="model-card"><div class="skeleton" style="height:1rem; width:60%; margin-bottom:0.5rem;"></div><div class="skeleton" style="height:0.8rem; width:90%;"></div><div class="skeleton" style="height:0.8rem; width:40%; margin-top:0.5rem;"></div></div>`
      ).join("")}</div>`;
    }
    try {
      const profile = await api("/api/v1/system/profile");
      capacity = profile.capacity || {};
      const catRes = await api("/api/v1/system/catalog");
      catalog = catRes.models || {};
      overridden = catRes.overridden || [];
      const modelsRes = await api("/api/v1/models");
      states = modelsRes.states || [];
    } catch (e) {
      toast(t("Yenileme hatasi: {m}", { m: e.message }), "error", 5000);
      schedulePullPolling();
      return;
    }
    try {
      const dis = await api("/api/v1/system/discover");
      discover = dis.models || [];
    } catch (e) {
      discover = [];
    }
    render();
    if (remote.length) renderRemote();
    schedulePullPolling();
  }

  function schedulePullPolling() {
    const active = states.some(s => s.status === "pulling" || s.status === "queued");
    if (active && !pollTimer) {
      pollTimer = setInterval(pollPullProgress, 1200);
    } else if (!active && pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function pollPullProgress() {
    let res;
    try { res = await api("/api/v1/models"); } catch { return; }
    const fresh = res.states || [];
    const prev = states;
    states = fresh;
    const finished = fresh.filter(s => {
      const p = prev.find(x => x.model_id === s.model_id);
      return p && (p.status === "pulling" || p.status === "queued") && s.pulled && s.status !== "pulling";
    });
    const failed = fresh.filter(s => {
      const p = prev.find(x => x.model_id === s.model_id);
      return p && p.status !== "error" && s.status === "error";
    });
    const transition = fresh.some(s => {
      const p = prev.find(x => x.model_id === s.model_id);
      return !p || p.status !== s.status || p.pulled !== s.pulled;
    });
    if (transition) {
      clearInterval(pollTimer);
      pollTimer = null;
      finished.forEach(s => toast(t("{m} indirildi ve kullanima hazir", { m: s.model_id }), "ok", 4500));
      failed.forEach(s => toast(t("{m} indirilemedi: {e}", { m: s.model_id, e: s.error || t("bilinmeyen hata") }), "error", 6000));
      try {
        await refresh();
        if (remote.length) renderRemote();
      } finally {
        schedulePullPolling();
      }
      return;
    }
    for (const s of fresh) {
      if (s.status !== "pulling" && s.status !== "queued") continue;
      document.querySelectorAll(`[data-pp="${CSS.escape(s.model_id)}"]`).forEach(pp => {
        pp.innerHTML = pullProgressHtml(s);
      });
      if (s.status === "pulling") {
        document.querySelectorAll(`[data-pbadge="${CSS.escape(s.model_id)}"]`).forEach(badge => {
          badge.textContent = t("indiriliyor %{p}", { p: Math.min(100, Math.round((s.pull_progress || 0) * 100)) });
        });
      }
    }
  }

  async function refreshRemote(force) {
    remoteGrid.innerHTML = `<div class="muted" style="padding:0.8rem;">${t("Guncel model listesi yukleniyor...")}</div>`;
    try {
      const r = await api("/api/v1/system/discover/remote?limit=1000" + (force ? "&refresh=true" : ""));
      remote = r.models || [];
      remoteMeta = r;
      renderRemote();
    } catch (e) {
      remote = [];
      remoteGrid.innerHTML = `<div class="muted" style="padding:0.8rem;">${t("Canli kesif su an kullanilamiyor (internet erisimi gerekli): {m}", { m: escapeHtml(e.message) })}</div>`;
    }
  }

  function renderRemote() {
    const pulledTags = new Set(states.filter(s => s.pulled).map(s => s.ollama_tag));
    const catalogTags = new Set(Object.values(catalog).map(d => d.ollama_tag));
    const stateByTag = new Map(states.map(s => [s.ollama_tag, s]));
    const midByTag = new Map(Object.entries(catalog).map(([mid, d]) => [String(d.ollama_tag), mid]));
    let items = remote.filter(it => {
      if (remoteProv && it.provider !== remoteProv) return false;
      if (remoteFit === "recommended" && !it.recommended) return false;
      if (remoteFit === "fits" && !it.fits) return false;
      const lq = q.toLowerCase().trim();
      if (lq && !(`${it.label} ${it.tag}`.toLowerCase().includes(lq))) return false;
      return true;
    });
    const shown = items.slice(0, 60);
    if (remoteMetaEl && remoteMeta.fetched_at) {
      const age = remoteMeta.age_minutes != null ? Math.round(remoteMeta.age_minutes) : "?";
      const src = remoteMeta.sources || {};
      remoteMetaEl.textContent =
        t("{n} model bulundu (ollama.com: {o}, HuggingFace: {h})", { n: remoteMeta.total, o: src.ollama || 0, h: src.huggingface || 0 }) + " · " +
        t("liste {age} dk once guncellendi", { age }) +
        (remoteMeta.stale ? " · " + t("ESKI KOPYA (ag erisimi yok)") : "");
    }
    if (!shown.length) {
      remoteGrid.innerHTML = `<div class="muted" style="padding:0.8rem;">${t("Filtreye uyan model yok.")}</div>`;
      return;
    }
    remoteGrid.innerHTML = shown.map(it => {
      const st = stateByTag.get(it.tag);
      return renderCard({
        source: "discover",
        model_id: midByTag.get(it.tag) || null,
        label: it.label,
        ollama_tag: it.tag,
        category: it.category,
        ram_gb: it.approx_gb,
        parameters_b: it.parameters_b,
        tier: it.tier,
        src: it.provider === "huggingface" ? "huggingface" : null,
        status: st ? st.status : "discoverable",
        pulled: st ? !!st.pulled : pulledTags.has(it.tag),
        pull_progress: st?.pull_progress || 0,
        pull_stage: st?.pull_stage,
        pull_completed_mb: st?.pull_completed_mb,
        pull_total_mb: st?.pull_total_mb,
        pull_speed_mbps: st?.pull_speed_mbps,
        pull_eta_seconds: st?.pull_eta_seconds,
        error: st?.error,
        in_catalog: catalogTags.has(it.tag),
        recommended: it.recommended,
        popularity: it.popularity,
        cloud: !!it.cloud,
        inflight: st?.inflight_requests || 0, total_req: 0, avg_ms: null,
        fits: it.fits,
        blurb: it.blurb,
      });
    }).join("");
    remoteGrid.querySelectorAll("button[data-action]").forEach(b => {
      b.onclick = () => handleAction(b);
    });
  }

  function render() {
    // Merge: tum bilinen modeller (catalog) + discover items
    const byCat = { text: [], code: [], reasoning: [], persona: [], fallback: [] };
    const seenTags = new Set();

    // Catalog'taki modeller (gercek state ile)
    for (const [mid, def] of Object.entries(catalog)) {
      const state = states.find(s => s.model_id === mid);
      const fits = parseFloat(def.ram_gb || 0) <= parseFloat(capacity.budget_total_gb || 0);
      const item = {
        source: "catalog",
        model_id: mid,
        label: mid.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        blurb: def.profile || "",
        ollama_tag: def.ollama_tag,
        category: def.category || "text",
        ram_gb: def.ram_gb,
        parameters_b: def.parameters_b,
        tier: def.tier,
        src: def.source,
        license: def.license,
        status: state?.status || "unknown",
        pulled: !!state?.pulled,
        pull_progress: state?.pull_progress || 0,
        pull_stage: state?.pull_stage,
        pull_completed_mb: state?.pull_completed_mb,
        pull_total_mb: state?.pull_total_mb,
        pull_speed_mbps: state?.pull_speed_mbps,
        pull_eta_seconds: state?.pull_eta_seconds,
        error: state?.error,
        inflight: state?.inflight_requests || 0,
        total_req: state?.total_requests || 0,
        avg_ms: state?.avg_latency_ms,
        fits,
        overridden: overridden.includes(mid),
      };
      if (!byCat[item.category]) byCat[item.category] = [];
      byCat[item.category].push(item);
      if (def.ollama_tag) seenTags.add(def.ollama_tag);
    }

    // Discover'da ama katalog'ta olmayan
    for (const d of discover) {
      if (seenTags.has(d.tag)) continue;
      const item = {
        source: "discover",
        model_id: null,
        label: d.label,
        ollama_tag: d.tag,
        category: d.category,
        ram_gb: d.approx_gb,
        parameters_b: null,
        status: "discoverable",
        pulled: false,
        inflight: 0, total_req: 0, avg_ms: null,
        fits: d.approx_gb <= parseFloat(capacity.budget_total_gb || 0),
        blurb: d.blurb,
      };
      if (!byCat[item.category]) byCat[item.category] = [];
      byCat[item.category].push(item);
    }

    // Filter
    const lq = q.toLowerCase().trim();
    function pass(it) {
      if (cat && it.category !== cat) return false;
      if (st === "pulled" && !it.pulled) return false;
      if (st === "not-pulled" && it.pulled) return false;
      if (st === "fits" && !it.fits) return false;
      if (lq) {
        const hay = `${it.label} ${it.ollama_tag} ${it.model_id || ""}`.toLowerCase();
        if (!hay.includes(lq)) return false;
      }
      return true;
    }

    const labels = {
      text: t("Metin / sozel"),
      code: t("Kod / programlama"),
      reasoning: t("Reasoning / mantik"),
      persona: t("Persona / rol yapma"),
      fallback: t("Fallback (hafif yedek)")
    };
    const order = ["fallback", "text", "code", "reasoning", "persona"];

    acc.innerHTML = "";
    let total = 0;
    for (const c of order) {
      const items = (byCat[c] || []).filter(pass);
      items.sort((a, b) => (a.ram_gb || 0) - (b.ram_gb || 0));
      total += items.length;
      if (!items.length) continue;
      const open = lq.length > 0 ? "open" : (items.some(i => i.pulled) ? "open" : "");
      const section = document.createElement("div");
      section.className = "accordion-section " + open;
      section.innerHTML = `
        <div class="head">
          <div class="name">${labels[c]} <span class="count">${t("{n} model", { n: items.length })}</span></div>
          <div class="chev">▸</div>
        </div>
        <div class="body">
          <div class="model-grid">
            ${items.map(renderCard).join("")}
          </div>
        </div>`;
      acc.appendChild(section);
    }

    if (total === 0) {
      acc.innerHTML = `<div class="card" style="text-align:center; padding:2rem; color:var(--muted);">${t("Eslesme yok.")}</div>`;
    }

    bindCardActions();
    bindAccordion();
  }

  function renderCard(it) {
    const statusBadge = it.source === "discover"
      ? (it.cloud ? '<span class="badge busy">☁ cloud</span>'
        : it.pulled ? `<span class="badge ok">${t("indirilmis")}</span>`
        : it.in_catalog ? `<span class="badge plain">${t("katalogda")}</span>`
        : it.recommended ? `<span class="badge ok">${t("donanima onerilen")}</span>`
        : `<span class="badge">${t("kesfedildi")}</span>`)
      : it.pulled ? `<span class="badge ok">${t("indirilmis")}</span>`
      : `<span class="badge warn">${t("indirilmemis")}</span>`;
    const stateBadge = it.status && it.status !== "discoverable"
      ? (it.status === "pulling"
        ? `<span class="badge busy" data-pbadge="${escapeHtml(it.model_id || "")}">${t("indiriliyor %{p}", { p: Math.min(100, Math.round((it.pull_progress || 0) * 100)) })}</span>`
        : it.status === "queued"
        ? `<span class="badge busy">${t("indirme sirasinda")}</span>`
        : it.status === "error"
        ? `<span class="badge error" title="${escapeHtml(it.error || "")}">${t("hata")}</span>`
        : `<span class="badge ${stateClass(it.status)}">${it.status}</span>`)
      : "";
    const fitsBadge = it.cloud ? ""
      : it.fits
      ? `<span class="badge ok">${t("bellege sigar")}</span>`
      : `<span class="badge warn">${t("bellek yetersiz")}</span>`;
    const sizeBadge = it.cloud
      ? `<span class="badge plain">${t("boyut: bulut")}</span>`
      : `<span class="badge plain">${it.ram_gb || "?"} GB</span>`;
    const paramBadge = it.parameters_b ? `<span class="badge plain">${it.parameters_b}B param</span>` : "";
    const tierBadge = it.tier ? `<span class="badge plain">${escapeHtml(it.tier)}</span>` : "";
    const hfBadge = it.src === "huggingface" ? '<span class="badge busy">HF</span>' : "";
    const popBadge = it.popularity
      ? `<span class="badge plain">${t("{n} indirme", { n: typeof fmtNumber === "function" ? fmtNumber(it.popularity) : it.popularity })}</span>` : "";

    let actions = "";
    if (it.cloud) {
      actions = `<span class="muted" style="font-size:0.78rem;">${t("Yalnizca Ollama Cloud'da calisir — on-premise kurulamaz (veri disari cikar)")}</span>`;
    } else if (!isAdmin) {
      actions = it.pulled
        ? `<span class="muted" style="font-size:0.78rem;">${t("Sistemde kurulu — sohbette kullanilabilir")}</span>`
        : `<span class="muted" style="font-size:0.78rem;">${t("Kurulum icin yoneticinize basvurun")}</span>`;
    } else if ((it.status === "pulling" || it.status === "queued") && it.model_id) {
      actions = `
        <span class="muted" style="font-size:0.78rem;">${it.status === "queued" ? t("Indirme sirasinda bekliyor…") : t("Sayfadan ayrilabilirsiniz, indirme arka planda surer")}</span>
        <button class="danger small" data-action="cancel-pull" data-mid="${escapeHtml(it.model_id)}">${t("Indirmeyi iptal et")}</button>`;
    } else if (it.pulled && it.model_id) {
      actions = `
        <button data-action="test" data-mid="${escapeHtml(it.model_id)}">${t("Hizli test")}</button>
        <button class="danger small" data-action="delete-pulled" data-mid="${escapeHtml(it.model_id)}">${t("Diskten kaldir")}</button>
      `;
      if (it.source !== "discover" && it.overridden) {
        actions += `<button class="danger small" data-action="remove" data-mid="${escapeHtml(it.model_id)}">${t("Katalogdan sil")}</button>`;
      }
    } else if (it.source === "discover") {
      actions = `
        <button class="primary" data-action="add-pull" data-tag="${escapeHtml(it.ollama_tag)}" data-cat="${it.category}" data-gb="${it.ram_gb}" data-label="${escapeHtml(it.label)}" ${it.fits ? "" : `disabled title='${t("Ayrilan bellege sigmiyor")}'`}>${t("+ Kur (ekle & pull)")}</button>
      `;
    } else if (!it.pulled) {
      actions = `<button class="primary" data-action="pull" data-mid="${escapeHtml(it.model_id)}" ${it.fits ? "" : `title='${t("Ayrilan bellege sigmiyor")}'`}>${it.status === "error" ? t("Tekrar dene") : t("Pull et")}</button>`;
      if (it.overridden) {
        actions += `<button class="danger small" data-action="remove" data-mid="${escapeHtml(it.model_id)}">${t("Katalogdan sil")}</button>`;
      }
    }
    const stats = it.total_req > 0
      ? `<div class="muted" style="font-size:0.72rem;">${t("{n} istek · ort {ms} ms", { n: it.total_req, ms: it.avg_ms ? Math.round(it.avg_ms) : "—" })}</div>`
      : "";
    const cls = `model-card ${it.pulled ? "in-catalog" : ""} ${it.fits ? "fits-current" : ""}`;
    const metaBadges = `${sizeBadge}${paramBadge}${tierBadge}${statusBadge}${stateBadge}${fitsBadge}${hfBadge}${popBadge}`;
    const pullBlock = (it.status === "pulling" || it.status === "queued") && it.model_id
      ? `<div class="pull-progress" data-pp="${escapeHtml(it.model_id)}">${pullProgressHtml(it)}</div>`
      : "";
    const budgetTotal = parseFloat(capacity.budget_total_gb || 0);
    const pct = budgetTotal ? Math.min(100, (parseFloat(it.ram_gb || 0) / budgetTotal) * 100) : 0;
    const usageBar = budgetTotal ? `
      <div style="margin-top:0.45rem;">
        <div class="muted" style="font-size:0.7rem; display:flex; justify-content:space-between;"><span>${t("Bellek payi")}</span><span>${pct.toFixed(0)}%</span></div>
        <div class="cbar-track" style="margin-top:0.2rem;"><div class="cbar-fill" style="width:${pct}%; background:${it.fits ? "var(--accent)" : "var(--warn)"};"></div></div>
      </div>` : "";
    return `
      <div class="${cls}">
        <div class="head">
          <div>
            <div class="label">${escapeHtml(it.label || it.ollama_tag)}</div>
            <div class="tag">${escapeHtml(it.ollama_tag)}</div>
          </div>
        </div>
        ${it.blurb ? `<div class="blurb">${escapeHtml(it.blurb)}</div>` : ""}
        <div class="meta">${metaBadges}</div>
        ${pullBlock}
        ${usageBar}
        ${stats}
        <div class="actions">${actions}</div>
      </div>
    `;
  }

  function stateClass(s) {
    if (s === "ready" || s === "loaded") return "ok";
    if (s === "pulling" || s === "queued") return "busy";
    if (s === "error") return "error";
    if (s === "passive") return "plain";
    return "plain";
  }

  function bindAccordion() {
    acc.querySelectorAll(".accordion-section .head").forEach(h => {
      const toggle = () => {
        const open = h.parentElement.classList.toggle("open");
        h.setAttribute("aria-expanded", String(open));
      };
      h.setAttribute("tabindex", "0");
      h.setAttribute("role", "button");
      h.setAttribute("aria-expanded", String(h.parentElement.classList.contains("open")));
      h.onclick = toggle;
      h.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
      };
    });
  }

  function bindCardActions() {
    acc.querySelectorAll("button[data-action]").forEach(b => {
      b.onclick = () => handleAction(b);
    });
  }

  async function handleAction(btn) {
    const act = btn.dataset.action;
    btn.disabled = true;
    const orig = btn.textContent;
    btn.textContent = "...";
    try {
      if (act === "pull") {
        await api(`/api/v1/system/pull/${encodeURIComponent(btn.dataset.mid)}`, { method: "POST" });
        toast(t("Pull baslatildi"), "ok");
      } else if (act === "cancel-pull") {
        const ok = await confirmModal({
          title: t("Indirmeyi iptal et"),
          body: t("{m} indirmesi durdurulacak. Tekrar denerseniz kaldigi yerden devam eder; kullanilmayan parcalar otomatik temizlenir. Devam edilsin mi?", { m: `<code>${escapeHtml(btn.dataset.mid)}</code>` }),
          primary: t("Iptal et"),
        });
        if (!ok) { btn.disabled = false; btn.textContent = orig; return; }
        await api(`/api/v1/system/pull/${encodeURIComponent(btn.dataset.mid)}`, { method: "DELETE" });
        toast(t("Indirme iptal edildi"), "ok", 4000);
      } else if (act === "add-pull") {
        const tag = btn.dataset.tag;
        const mid = tagToModelId(tag);
        try {
          await api("/api/v1/system/catalog/models", {
            method: "POST",
            body: JSON.stringify({
              model_id: mid, ollama_tag: tag, category: btn.dataset.cat,
              ram_gb: parseFloat(btn.dataset.gb), vram_gb: parseFloat(btn.dataset.gb),
              profile: btn.dataset.label,
            }),
          });
        } catch (e) {
          if (!/zaten|already|exist/i.test(e.message || "")) throw e;
        }
        await api(`/api/v1/system/pull/${encodeURIComponent(mid)}`, { method: "POST" });
        toast(t("Kurulum baslatildi: katalog + indirme"), "ok");
      } else if (act === "remove") {
        const ok = await confirmModal({
          title: t("Katalogdan sil"),
          body: t("{m} katalog kaydi silinecek. Devam edilsin mi?", { m: `<code>${escapeHtml(btn.dataset.mid)}</code>` }),
          primary: t("Sil"),
        });
        if (!ok) { btn.disabled = false; btn.textContent = orig; return; }
        await api(`/api/v1/system/catalog/models/${encodeURIComponent(btn.dataset.mid)}`, { method: "DELETE" });
        toast(t("Silindi"), "ok");
      } else if (act === "test") {
        const r = await api("/api/v1/chat", {
          method: "POST",
          body: JSON.stringify({ prompt: t("Merhaba, tek cumlede kendini tanit."), model_id: btn.dataset.mid }),
        });
        toast(`Test OK · ${Math.round(r.latency_ms)} ms · ${r.eval_count} tok`, "ok", 4500);
      } else if (act === "delete-pulled") {
        const ok = await confirmModal({
          title: t("Modeli diskten sil"),
          body: t("{m} Ollama'dan silinecek; disk bosalir, gerektiginde tekrar indirilebilir.", { m: `<code>${escapeHtml(btn.dataset.mid)}</code>` }),
          primary: t("Sil"),
        });
        if (!ok) { btn.disabled = false; btn.textContent = orig; return; }
        await api(`/api/v1/system/models/${encodeURIComponent(btn.dataset.mid)}/pulled`, { method: "DELETE" });
        toast(t("Model Ollama'dan silindi"), "ok");
      }
      setTimeout(async () => { await refresh(); renderRemote(); }, 500);
    } catch (err) {
      toast(t("Hata: {m}", { m: err.message }), "error", 5000);
      btn.disabled = false; btn.textContent = orig;
    }
  }

  // Search / filter
  let searchDebounce = null;
  searchInput.addEventListener("input", (e) => {
    q = e.target.value;
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => { render(); renderRemote(); }, 180);
  });
  catFilter.addEventListener("click", (e) => {
    if (!e.target.matches("button")) return;
    catFilter.querySelectorAll("button").forEach(b => b.classList.remove("active"));
    e.target.classList.add("active");
    cat = e.target.dataset.cat || "";
    render();
  });
  statusFilter.addEventListener("click", (e) => {
    if (!e.target.matches("button")) return;
    statusFilter.querySelectorAll("button").forEach(b => b.classList.remove("active"));
    e.target.classList.add("active");
    st = e.target.dataset.st || "";
    render();
  });

  const remoteProviderFilter = document.getElementById("remoteProviderFilter");
  const remoteFitFilter = document.getElementById("remoteFitFilter");
  remoteProviderFilter.addEventListener("click", (e) => {
    if (!e.target.matches("button")) return;
    remoteProviderFilter.querySelectorAll("button").forEach(b => b.classList.remove("active"));
    e.target.classList.add("active");
    remoteProv = e.target.dataset.prov || "";
    renderRemote();
  });
  remoteFitFilter.addEventListener("click", (e) => {
    if (!e.target.matches("button")) return;
    remoteFitFilter.querySelectorAll("button").forEach(b => b.classList.remove("active"));
    e.target.classList.add("active");
    remoteFit = e.target.dataset.fit || "";
    renderRemote();
  });
  document.getElementById("remoteRefreshBtn").onclick = async (e) => {
    e.target.disabled = true;
    await refreshRemote(true);
    e.target.disabled = false;
  };

  document.getElementById("refreshBtn").onclick = refresh;
  document.getElementById("addCustomBtn").onclick = openCustomModal;

  function openCustomModal() {
    modal({
      title: t("Ozel model ekle"),
      body: `
        <p class="muted" style="margin-top:0;">${t("Ollama Library veya HuggingFace'ten model ekleyin. HuggingFace icin tag'i {code} formatinda girin — sistem otomatik HF olarak isaretler. Boyut icin {inspect} (once pull gerekli) ya da manuel girin.", { code: "<code>hf.co/kullanici/depo-GGUF</code>", inspect: "<strong>Inspect</strong>" })}</p>
        <label>Ollama / HuggingFace tag <input id="cm_tag" placeholder="${t("orn: qwen3:8b  veya  hf.co/bartowski/Qwen3-8B-GGUF")}" /></label>
        <label>${t("Kategori")} <select id="cm_cat">
          <option value="text">${t("Metin")}</option>
          <option value="code">${t("Kod")}</option>
          <option value="reasoning">Reasoning</option>
          <option value="persona">Persona</option>
          <option value="fallback">Fallback</option>
        </select></label>
        <label>RAM/VRAM (GB) <input id="cm_ram" type="number" step="0.1" min="0.1" placeholder="3.0" /></label>
        <div style="display:flex; gap:0.5rem;">
          <button id="cm_inspect" type="button">${t("Boyutu tahmin et")}</button>
          <button id="cm_dryrun" type="button">${t("Bellege sigar mi?")}</button>
        </div>
      `,
      primary: t("Ekle"),
      onPrimary: async () => {
        const tag = document.getElementById("cm_tag").value.trim();
        const cat = document.getElementById("cm_cat").value;
        const ram = parseFloat(document.getElementById("cm_ram").value);
        if (!tag || isNaN(ram)) { toast(t("Tag ve RAM zorunlu"), "warn"); return false; }
        const mid = tagToModelId(tag);
        try {
          await api("/api/v1/system/catalog/models", {
            method: "POST",
            body: JSON.stringify({ model_id: mid, ollama_tag: tag, category: cat, ram_gb: ram, vram_gb: ram }),
          });
          toast(t("Eklendi"), "ok");
          refresh();
        } catch (e) {
          toast(t("Eklenemedi: {m}", { m: e.message }), "error", 5000);
          return false;
        }
      },
    });
    // Bind dynamic buttons inside modal
    setTimeout(() => {
      document.getElementById("cm_inspect")?.addEventListener("click", async () => {
        const tag = document.getElementById("cm_tag").value.trim();
        if (!tag) { toast(t("Tag girin"), "warn"); return; }
        try {
          const r = await api("/api/v1/system/ollama/inspect", { method: "POST", body: JSON.stringify({ ollama_tag: tag }) });
          if (r.estimated_ram_gb) document.getElementById("cm_ram").value = r.estimated_ram_gb;
          toast(`${r.parameter_size || "?"} param · ~${r.estimated_ram_gb || "?"} GB`, "ok", 4000);
        } catch (e) { toast("Inspect: " + e.message, "error", 5000); }
      });
      document.getElementById("cm_dryrun")?.addEventListener("click", async () => {
        const tag = document.getElementById("cm_tag").value.trim();
        const cat = document.getElementById("cm_cat").value;
        const ram = parseFloat(document.getElementById("cm_ram").value);
        if (!tag || isNaN(ram)) { toast(t("Tag ve RAM zorunlu"), "warn"); return; }
        const mid = tagToModelId(tag);
        try {
          const r = await api("/api/v1/system/catalog/dry-run", {
            method: "POST",
            body: JSON.stringify({ model_id: mid, ollama_tag: tag, category: cat, ram_gb: ram, vram_gb: ram }),
          });
          const rows = Object.entries(r.profiles).map(([n, p]) => `
            <tr><td>${escapeHtml(n)}</td><td>${p.budget_total_gb} GB</td>
            <td>${p.fits ? `<span class="badge ok">${t("sigar")}</span>` : `<span class="badge warn">${t("sigmaz")}</span>`}</td></tr>`).join("");
          modal({
            title: t("Bellek raporu"),
            body: `
              <p style="margin-top:0;"><strong>${escapeHtml(r.verdict)}</strong></p>
              <p class="muted">${escapeHtml(r.advice)}</p>
              <table class="kv"><tr><th>${t("Profil")}</th><th>${t("Ayrilan bellek")}</th><th>${t("Durum")}</th></tr>${rows}</table>`,
            primary: t("Tamam"),
          });
        } catch (e) { toast("Dry-run: " + e.message, "error", 5000); }
      });
    }, 50);
  }

  await refresh();
  refreshRemote(false);
})();
