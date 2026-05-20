(async function () {
  let catalog = {};        // model_id -> def
  let states = [];         // orchestrator states
  let discover = [];       // populer modeller
  let capacity = {};
  let q = "";
  let cat = "";
  let st = "";

  const acc = document.getElementById("accordion");
  const searchInput = document.getElementById("searchInput");
  const catFilter = document.getElementById("catFilter");
  const statusFilter = document.getElementById("statusFilter");

  async function refresh() {
    try {
      const profile = await api("/api/v1/system/profile");
      capacity = profile.capacity || {};
      const catRes = await api("/api/v1/system/catalog");
      catalog = catRes.models || {};
      const modelsRes = await api("/api/v1/models");
      states = modelsRes.states || [];
      const dis = await api("/api/v1/system/discover");
      discover = dis.models || [];
      render();
    } catch (e) {
      toast("Yenileme hatasi: " + e.message, "error", 5000);
    }
  }

  function render() {
    // Merge: tum bilinen modeller (catalog) + discover items
    const byCat = { text: [], code: [], reasoning: [], fallback: [] };
    const seenTags = new Set();

    // Catalog'taki modeller (gercek state ile)
    for (const [mid, def] of Object.entries(catalog)) {
      const state = states.find(s => s.model_id === mid);
      const fits = parseFloat(def.ram_gb || 0) <= parseFloat(capacity.budget_total_gb || 0);
      const item = {
        source: "catalog",
        model_id: mid,
        label: def.profile || mid,
        ollama_tag: def.ollama_tag,
        category: def.category || "text",
        ram_gb: def.ram_gb,
        parameters_b: def.parameters_b,
        status: state?.status || "unknown",
        pulled: !!state?.pulled,
        inflight: state?.inflight_requests || 0,
        total_req: state?.total_requests || 0,
        avg_ms: state?.avg_latency_ms,
        fits,
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
      text: "Metin / sozel",
      code: "Kod / programlama",
      reasoning: "Reasoning / mantik",
      fallback: "Fallback (hafif yedek)"
    };
    const order = ["fallback", "text", "code", "reasoning"];

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
          <div class="name">${labels[c]} <span class="count">${items.length} model</span></div>
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
      acc.innerHTML = `<div class="card" style="text-align:center; padding:2rem; color:var(--muted);">Eslesme yok.</div>`;
    }

    bindCardActions();
    bindAccordion();
  }

  function renderCard(it) {
    const statusBadge = it.source === "discover" ? '<span class="badge">onerilen</span>'
                     : it.pulled ? '<span class="badge ok">indirilmis</span>'
                     : '<span class="badge warn">indirilmemis</span>';
    const stateBadge = it.status && it.status !== "discoverable"
      ? `<span class="badge ${stateClass(it.status)}">${it.status}</span>` : "";
    const fitsBadge = it.fits
      ? '<span class="badge ok">butce uygun</span>'
      : '<span class="badge warn">butce yetersiz</span>';
    const sizeBadge = `<span class="badge plain">${it.ram_gb || "?"} GB</span>`;
    const paramBadge = it.parameters_b ? `<span class="badge plain">${it.parameters_b}B param</span>` : "";

    let actions = "";
    if (it.source === "discover") {
      actions = `
        <button class="primary" data-action="add-pull" data-tag="${escapeHtml(it.ollama_tag)}" data-cat="${it.category}" data-gb="${it.ram_gb}" data-label="${escapeHtml(it.label)}" ${it.fits ? "" : "disabled title='Butceye sigmiyor'"}>+ Ekle & pull</button>
      `;
    } else if (!it.pulled) {
      actions = `
        <button class="primary" data-action="pull" data-mid="${escapeHtml(it.model_id)}">Pull et</button>
        <button data-action="remove" data-mid="${escapeHtml(it.model_id)}">Sil</button>
      `;
    } else {
      actions = `
        <button data-action="test" data-mid="${escapeHtml(it.model_id)}">Hizli test</button>
      `;
    }
    const stats = it.total_req > 0
      ? `<div class="muted" style="font-size:0.72rem;">${it.total_req} istek · ort ${it.avg_ms ? Math.round(it.avg_ms) : "—"} ms</div>`
      : "";
    const cls = `model-card ${it.pulled ? "in-catalog" : ""} ${it.fits ? "fits-current" : ""}`;
    return `
      <div class="${cls}">
        <div class="head">
          <div>
            <div class="label">${escapeHtml(it.label || it.ollama_tag)}</div>
            <div class="tag">${escapeHtml(it.ollama_tag)}</div>
          </div>
        </div>
        ${it.blurb ? `<div class="blurb">${escapeHtml(it.blurb)}</div>` : ""}
        <div class="meta">${sizeBadge}${paramBadge}${statusBadge}${stateBadge}${fitsBadge}</div>
        ${stats}
        <div class="actions">${actions}</div>
      </div>
    `;
  }

  function stateClass(s) {
    if (s === "ready" || s === "loaded") return "ok";
    if (s === "pulling") return "busy";
    if (s === "error") return "error";
    if (s === "passive") return "plain";
    return "plain";
  }

  function bindAccordion() {
    acc.querySelectorAll(".accordion-section .head").forEach(h => {
      h.onclick = () => h.parentElement.classList.toggle("open");
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
        toast("Pull baslatildi", "ok");
      } else if (act === "add-pull") {
        const tag = btn.dataset.tag;
        const mid = tag.replace(/[:.]/g, "-").replace(/[^a-zA-Z0-9._\-]/g, "");
        try {
          await api("/api/v1/system/catalog/models", {
            method: "POST",
            body: JSON.stringify({
              model_id: mid, ollama_tag: tag, category: btn.dataset.cat,
              ram_gb: parseFloat(btn.dataset.gb), vram_gb: parseFloat(btn.dataset.gb),
              profile: btn.dataset.label,
            }),
          });
        } catch {}
        await api(`/api/v1/system/pull/${encodeURIComponent(mid)}`, { method: "POST" });
        toast("Ekleme + pull baslatildi", "ok");
      } else if (act === "remove") {
        if (!confirm(`'${btn.dataset.mid}' override silinsin mi?`)) {
          btn.disabled = false; btn.textContent = orig; return;
        }
        await api(`/api/v1/system/catalog/models/${encodeURIComponent(btn.dataset.mid)}`, { method: "DELETE" });
        toast("Silindi", "ok");
      } else if (act === "test") {
        const r = await api("/api/v1/chat", {
          method: "POST",
          body: JSON.stringify({ prompt: "Merhaba, tek cumlede kendini tanit.", model_id: btn.dataset.mid }),
        });
        toast(`Test OK · ${Math.round(r.latency_ms)} ms · ${r.eval_count} tok`, "ok", 4500);
      }
      setTimeout(refresh, 500);
    } catch (err) {
      toast("Hata: " + err.message, "error", 5000);
      btn.disabled = false; btn.textContent = orig;
    }
  }

  // Search / filter
  searchInput.addEventListener("input", (e) => { q = e.target.value; render(); });
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

  document.getElementById("refreshBtn").onclick = refresh;
  document.getElementById("addCustomBtn").onclick = openCustomModal;

  function openCustomModal() {
    modal({
      title: "Ozel model ekle",
      body: `
        <p class="muted" style="margin-top:0;">Ollama Library'den herhangi bir tag ekleyebilirsiniz. Boyutu tahmin etmek icin <strong>Inspect</strong> butonunu kullanin (model Ollama'ya bir kez pull edilmis olmali) ya da manuel girin.</p>
        <label>Ollama tag <input id="cm_tag" placeholder="orn: gemma4:e4b" /></label>
        <label>Kategori <select id="cm_cat">
          <option value="text">Metin</option>
          <option value="code">Kod</option>
          <option value="reasoning">Reasoning</option>
          <option value="fallback">Fallback</option>
        </select></label>
        <label>RAM/VRAM (GB) <input id="cm_ram" type="number" step="0.1" min="0.1" placeholder="3.0" /></label>
        <div style="display:flex; gap:0.5rem;">
          <button id="cm_inspect" type="button">Boyutu tahmin et</button>
          <button id="cm_dryrun" type="button">Butceye sigar mi?</button>
        </div>
      `,
      primary: "Ekle",
      onPrimary: async () => {
        const tag = document.getElementById("cm_tag").value.trim();
        const cat = document.getElementById("cm_cat").value;
        const ram = parseFloat(document.getElementById("cm_ram").value);
        if (!tag || isNaN(ram)) { toast("Tag ve RAM zorunlu", "warn"); return; }
        const mid = tag.replace(/[:.]/g, "-").replace(/[^a-zA-Z0-9._\-]/g, "");
        try {
          await api("/api/v1/system/catalog/models", {
            method: "POST",
            body: JSON.stringify({ model_id: mid, ollama_tag: tag, category: cat, ram_gb: ram, vram_gb: ram }),
          });
          toast("Eklendi", "ok");
          refresh();
        } catch (e) { toast("Eklenemedi: " + e.message, "error", 5000); }
      },
    });
    // Bind dynamic buttons inside modal
    setTimeout(() => {
      document.getElementById("cm_inspect")?.addEventListener("click", async () => {
        const tag = document.getElementById("cm_tag").value.trim();
        if (!tag) { toast("Tag girin", "warn"); return; }
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
        if (!tag || isNaN(ram)) { toast("Tag ve RAM zorunlu", "warn"); return; }
        const mid = tag.replace(/[:.]/g, "-").replace(/[^a-zA-Z0-9._\-]/g, "");
        try {
          const r = await api("/api/v1/system/catalog/dry-run", {
            method: "POST",
            body: JSON.stringify({ model_id: mid, ollama_tag: tag, category: cat, ram_gb: ram, vram_gb: ram }),
          });
          alert(`${r.verdict}\n\n${r.advice}\n\nProfiller:\n` +
            Object.entries(r.profiles).map(([n, p]) =>
              `  ${n}: butce ${p.budget_total_gb} GB, sigar: ${p.fits ? "evet" : "hayir"}`
            ).join("\n"));
        } catch (e) { toast("Dry-run: " + e.message, "error", 5000); }
      });
    }, 50);
  }

  refresh();
})();
