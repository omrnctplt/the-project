(async function () {
  const user = window.currentUser || {};
  const isAdmin = user.role === "admin";

  /* ---------- Conversation store (localStorage, kullanici bazli) ----------
     Anahtar kullanici adina baglidir: ayni tarayicida farkli hesaplarin
     sohbetleri birbirine karismaz. Eski paylasimli anahtar temizlenir. */
  const STORAGE = "hub_convs_v1:" + (user.username || "anon");
  localStorage.removeItem("hub_convs_v1");
  function loadConvs() {
    try { return JSON.parse(localStorage.getItem(STORAGE) || "[]"); } catch { return []; }
  }
  function saveConvs(list) { localStorage.setItem(STORAGE, JSON.stringify(list)); }
  let convs = loadConvs();
  let activeId = null;

  function newConv() {
    const id = "c" + Date.now();
    const c = { id, title: t("Yeni sohbet"), created_at: Date.now(), messages: [] };
    convs.unshift(c);
    saveConvs(convs);
    activeId = id;
    return c;
  }
  function getActive() {
    if (!activeId) return null;
    return convs.find(c => c.id === activeId);
  }
  function deleteConv(id) {
    convs = convs.filter(c => c.id !== id);
    saveConvs(convs);
    if (activeId === id) activeId = null;
  }

  /* ---------- DOM elements ---------- */
  const body = document.getElementById("chatBody");
  const form = document.getElementById("chatForm");
  const promptEl = document.getElementById("prompt");
  const sendBtn = document.getElementById("sendBtn");
  const titleEl = document.getElementById("chatTitle");
  const convListEl = document.getElementById("convList");
  const newChatBtn = document.getElementById("newChatBtn");
  const streamToggle = document.getElementById("streamToggle");
  const adminPicker = document.getElementById("adminModel");
  const tempSelect = document.getElementById("tempSelect");

  let isGenerating = false;
  let abortCtl = null;

  if (isAdmin) {
    adminPicker.classList.remove("hidden");
    try {
      const ml = await api("/api/v1/models");
      for (const s of (ml.states || [])) {
        const opt = document.createElement("option");
        opt.value = s.model_id;
        opt.textContent = `${s.model_id} [${s.category}] · ${s.status}`;
        adminPicker.appendChild(opt);
      }
    } catch (e) { console.error(e); }
  }

  /* ---------- Sidebar render ---------- */
  function renderSidebar() {
    convListEl.innerHTML = "";
    for (const c of convs) {
      const li = document.createElement("li");
      li.className = "conv" + (c.id === activeId ? " active" : "");
      li.innerHTML = `
        <span class="title">${escapeHtml(c.title || t("Sohbet"))}</span>
        <button class="del" data-del="${c.id}" title="${t("Sil")}" aria-label="${t("Sohbeti sil")}">✕</button>`;
      li.onclick = async (e) => {
        if (e.target.dataset.del) {
          const id = e.target.dataset.del;
          const ok = await confirmModal({
            title: t("Sohbeti sil"),
            body: t("Bu sohbet kalici olarak silinecek. Emin misiniz?"),
            primary: t("Sil"),
          });
          if (!ok) return;
          deleteConv(id);
          renderAll();
          return;
        }
        activeId = c.id;
        renderAll();
      };
      convListEl.appendChild(li);
    }
    if (!convs.length) {
      convListEl.innerHTML = `<li class="muted" style="padding:0.5rem 0.6rem; font-size:0.8rem;">${t("Henuz sohbet yok.")}</li>`;
    }
  }

  function renderBody() {
    const c = getActive();
    body.innerHTML = "";
    if (!c || !c.messages.length) {
      titleEl.textContent = c?.title || t("Yeni sohbet");
      const dep = user.department || "general";
      const examples = examplePromptsFor(dep);
      body.innerHTML = `
        <div class="chat-empty">
          <div class="chat-empty-logo" aria-hidden="true"></div>
          <h2>${t("Merhaba {name}", { name: escapeHtml(user.label || user.username || "") })}</h2>
          <p>${t("{d} departmaniniza atanmis modele otomatik yonlendireceğim. Asagidan birini secebilir veya kendi sorunuzu yazabilirsiniz.", { d: `<strong>${escapeHtml(dep)}</strong>` })}</p>
          <div class="examples">
            ${examples.map(ex => `
              <button class="ex-card" type="button" data-ex="${escapeHtml(ex.prompt)}">
                <div class="ex-title">${escapeHtml(ex.title)}</div>
                <div class="ex-sub">${escapeHtml(ex.sub)}</div>
              </button>
            `).join("")}
          </div>
        </div>`;
      body.querySelectorAll(".ex-card").forEach(el => {
        el.onclick = () => {
          promptEl.value = el.dataset.ex;
          promptEl.focus();
          autoResize();
        };
      });
      return;
    }
    titleEl.textContent = c.title || t("Sohbet");
    for (let i = 0; i < c.messages.length; i++) {
      const m = c.messages[i];
      const isLast = i === c.messages.length - 1 && m.role === "assistant" && !m.streaming;
      body.appendChild(renderMsg(m, i, { isLast }));
    }
    body.scrollTop = body.scrollHeight;
  }

  function renderMsg(m, idx, opts = {}) {
    const div = document.createElement("div");
    div.className = "msg " + m.role;
    div.dataset.idx = idx;
    const avatar = m.role === "user"
      ? (user.label || user.username || "?").trim().slice(0, 2).toUpperCase()
      : "AI";

    let meta = "";
    if (m.role === "assistant" && m.meta) {
      const tps = (m.meta.eval_count && m.meta.latency_ms)
        ? (m.meta.eval_count / (m.meta.latency_ms / 1000)) : null;
      meta = `<div class="meta">
          ${m.meta.model_id ? `<span class="badge ok">${escapeHtml(m.meta.model_id)}</span>` : ""}
          ${m.meta.category ? `<span class="badge plain">${escapeHtml(m.meta.category)}</span>` : ""}
          ${m.meta.fallback_triggered ? '<span class="badge warn">fallback</span>' : ""}
          ${m.meta.latency_ms ? `<span class="muted">${Math.round(m.meta.latency_ms)} ms · ${m.meta.eval_count || 0} tok${tps ? ` · ${tps.toFixed(1)} tok/s` : ""}</span>` : ""}
        </div>`;
    }

    const contentHtml = m.role === "assistant"
      ? (m.content ? renderMarkdown(m.content) : (m.streaming ? genStatusHtml(null) : ""))
      : escapeHtml(m.content || "");

    let actions = "";
    if (m.role === "assistant" && !m.streaming && m.content) {
      actions = `<div class="msg-actions">
          <button class="msg-act" type="button" data-act="copy" title="${t("Yaniti kopyala")}"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> ${t("Kopyala")}</button>
          ${opts.isLast ? `<button class="msg-act" type="button" data-act="regen" title="${t("Yeniden uret")}"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/></svg> ${t("Yeniden uret")}</button>` : ""}
        </div>`;
    }

    div.innerHTML = `
      <div class="avatar">${escapeHtml(avatar)}</div>
      <div class="body">
        ${meta}
        <div class="content${m.streaming ? " streaming" : ""}"${m.streaming ? ' aria-live="polite" aria-busy="true"' : ""}>${contentHtml}</div>
        ${actions}
      </div>`;
    return div;
  }

  function examplePromptsFor(dep) {
    const map = {
      engineering: [
        { title: t("Kod review"), sub: t("Bu fonksiyonu daha temiz nasil yazarim?"), prompt: t("Asagidaki Python fonksiyonunu daha temiz hale getir:\n\ndef calc(items):\n    s = 0\n    for i in items:\n        if i > 0: s += i\n    return s") },
        { title: t("Bug ariyorum"), sub: t("Hata mesajini birlikte inceleyelim"), prompt: t("Su hatayi aliyorum, sebebi ne olabilir: 'TypeError: cannot unpack non-iterable NoneType object'") },
      ],
      hr: [
        { title: t("Mulakat sorulari"), sub: t("Junior developer icin 5 soru"), prompt: t("Junior bir Python developer pozisyonu icin teknik ve davranissal toplam 5 mulakat sorusu yaz.") },
        { title: t("Izin politikasi"), sub: t("Kisaca ozet"), prompt: t("Yillik iznin kisaca nasil hesaplandigini 3 maddede acikla.") },
      ],
      finance: [
        { title: t("Hizli hesap"), sub: t("KDV dahil/haric"), prompt: t("Hesapla: 12500 TL'lik bir hizmetin %20 KDV dahil ve haric tutari nedir? Aciklamali yaz.") },
        { title: t("Tahmin"), sub: t("Aylik gelir tahmini"), prompt: t("Asagidaki son 6 ay gelir verisine bakarak gelecek 3 ayi tahmin et: 120k, 135k, 128k, 142k, 150k, 145k") },
      ],
      legal: [
        { title: t("Sozlesme ozeti"), sub: t("Kisaca ana noktalar"), prompt: t("Bir SaaS hizmet sozlesmesindeki en kritik 5 maddeyi ozetle.") },
      ],
      marketing: [
        { title: t("Reklam metni"), sub: t("3 farkli ton"), prompt: t("Bir yeni mobil bankacilik uygulamasi icin: profesyonel, samimi ve mizahi tonda birer Twitter reklami yaz.") },
      ],
      general: [
        { title: t("Acikla"), sub: t("Konsept anlama"), prompt: t("Docker container ile sanal makine farkini bana 3 cumlede acikla.") },
        { title: t("Ceviri"), sub: t("Hizli ceviri"), prompt: t("Lutfen su cumleyi Ingilizce'ye dogru cevir: 'Bu projeyi onumuzdeki hafta teslim edebiliriz.'") },
      ],
    };
    return map[dep] || map.general;
  }

  /* ---------- Send flow ---------- */
  promptEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isGenerating) form.requestSubmit();
    }
  });
  promptEl.addEventListener("input", autoResize);
  function autoResize() {
    promptEl.style.height = "auto";
    promptEl.style.height = Math.min(180, promptEl.scrollHeight) + "px";
  }

  function setGenerating(on) {
    isGenerating = on;
    sendBtn.classList.toggle("stop", on);
    sendBtn.textContent = on ? t("◼ Durdur") : t("Gonder ↵");
    promptEl.disabled = false;
  }

  // Send butonu: uretim sirasinda durdurma gorevi gorur
  sendBtn.addEventListener("click", (e) => {
    if (isGenerating) {
      e.preventDefault();
      if (abortCtl) abortCtl.abort();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (isGenerating) return;
    const prompt = promptEl.value.trim();
    if (!prompt) return;
    promptEl.value = "";
    autoResize();
    await sendPrompt(prompt, {});
  });

  async function sendPrompt(prompt, { skipUserPush }) {
    setGenerating(true);

    if (!getActive()) newConv();
    const conv = getActive();
    const targetConvId = conv.id;

    // Cok turlu baglam: bu sohbetin onceki turlari (yeni eklenen haric)
    const history = conv.messages
      .filter(m => m.content && !m.streaming)
      .slice(-8)
      .map(m => ({ role: m.role, content: String(m.content).slice(0, 8000) }));

    if (!skipUserPush) {
      conv.messages.push({ role: "user", content: prompt, ts: Date.now() });
      if (conv.messages.filter(m => m.role === "user").length === 1) {
        conv.title = prompt.slice(0, 40) + (prompt.length > 40 ? "…" : "");
      }
      saveConvs(convs);
      renderAll();
    }

    const asst = { role: "assistant", content: "", streaming: true, meta: null, ts: Date.now() };
    conv.messages.push(asst);
    renderBody();

    const useStream = streamToggle.checked;
    const adminPick = isAdmin ? adminPicker.value : "";
    const body_ = { prompt };
    if (history.length) body_.history = history;
    if (adminPick) body_.model_id = adminPick;
    const temp = tempSelect && tempSelect.value ? parseFloat(tempSelect.value) : null;
    if (temp != null && !isNaN(temp)) body_.temperature = temp;

    abortCtl = new AbortController();
    let aborted = false;
    try {
      if (useStream) {
        await runStream(asst, body_, abortCtl.signal, targetConvId);
      } else {
        await runOneShot(asst, body_, abortCtl.signal, targetConvId);
      }
    } catch (err) {
      if (err.name === "AbortError") {
        aborted = true;
        if (!asst.content) asst.content = t("_(durduruldu)_");
        else asst.content += "\n\n" + t("_(durduruldu)_");
      } else {
        asst.content = t("**Hata:** {m}", { m: err.message });
        asst.meta = { model_id: "—", category: "error" };
        toast(t("Istek basarisiz: {m}", { m: err.message }), "error", 5000);
      }
    } finally {
      asst.streaming = false;
      abortCtl = null;
      saveConvs(convs);
      renderAll();
      setGenerating(false);
      promptEl.focus();
    }
    return !aborted;
  }

  async function runOneShot(asst, body_, signal, targetConvId) {
    const token = localStorage.getItem("token");
    const watcher = startPullWatch(asst, targetConvId);
    let resp;
    try {
      resp = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": token ? `Bearer ${token}` : "" },
        body: JSON.stringify(body_),
        signal,
      });
    } finally {
      watcher.stop();
    }
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try { const j = await resp.json(); detail = j.detail || detail; } catch {}
      throw new Error(detail);
    }
    const r = await resp.json();
    asst.content = r.response || t("(bos yanit)");
    asst.meta = {
      model_id: r.model_id, category: r.category,
      matched_rule: r.matched_rule, fallback_triggered: r.fallback_triggered,
      latency_ms: r.latency_ms, eval_count: r.eval_count,
    };
    if (activeId === targetConvId) renderBody();
  }

  async function runStream(asst, body_, signal, targetConvId) {
    const t0 = performance.now();
    const token = localStorage.getItem("token");
    const resp = await fetch("/api/v1/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": token ? `Bearer ${token}` : "" },
      body: JSON.stringify(body_),
      signal,
    });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try { const j = await resp.json(); detail = j.detail || detail; } catch {}
      throw new Error(detail);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let evalCount = 0;
    let lastRender = 0;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (!line) continue;
        let evt;
        try { evt = JSON.parse(line); } catch { continue; }
        if (evt.event === "start") {
          asst.meta = {
            model_id: evt.model_id, category: evt.category,
            matched_rule: evt.matched_rule,
            fallback_triggered: evt.fallback_triggered,
          };
          if (activeId === targetConvId) renderBody();
        } else if (evt.event === "status") {
          if (!asst.content) updateGenStatus(evt, targetConvId);
        } else if (evt.event === "token") {
          if (evt.response) {
            asst.content += evt.response;
            const now = performance.now();
            if (now - lastRender > 60) { updateLastContent(asst.content, targetConvId); lastRender = now; }
          }
          if (evt.done) evalCount = evt.eval_count || 0;
        } else if (evt.event === "error") {
          throw new Error(evt.detail || t("Stream hatasi"));
        }
      }
    }
    updateLastContent(asst.content, targetConvId);
    const dt = performance.now() - t0;
    if (asst.meta) {
      asst.meta.latency_ms = dt;
      asst.meta.eval_count = evalCount;
    }
  }

  /* ---------- Yanit oncesi durum gosterimi (indirme / bellege yukleme) ----------
     Ilk token gelene kadar bos balon yerine canli durum gosterilir; boylece
     model indirilirken ya da bellege yuklenirken arayuz donmus gibi durmaz. */
  function genStatusHtml(evt) {
    if (evt && evt.stage === "pull") {
      const attributed = evt.attributed !== false;
      const p = {
        status: evt.status || "pulling",
        pull_progress: evt.progress,
        pull_stage: evt.stage_text,
        pull_completed_mb: evt.completed_mb,
        pull_total_mb: evt.total_mb,
        pull_speed_mbps: evt.speed_mbps,
        pull_eta_seconds: evt.eta_seconds,
      };
      if (attributed && p.status !== "queued" && (p.pull_progress || 0) >= 1) {
        return `<div class="gen-status"><div class="gs-row"><span class="spin" aria-hidden="true"></span><span>${t("Model indirildi — bellege yukleniyor…")}</span></div></div>`;
      }
      const title = !attributed
        ? t("Sunucuda bir model indiriliyor: {m} — yanitiniz bunu bekliyor olabilir", { m: escapeHtml(evt.model_id || "?") })
        : p.status === "queued"
        ? t("{m} indirme sirasinda", { m: escapeHtml(evt.model_id || "Model") })
        : t("{m} ilk kez kullaniliyor — indiriliyor", { m: escapeHtml(evt.model_id || "Model") });
      return `
        <div class="gen-status">
          <div class="gs-row"><span class="spin" aria-hidden="true"></span><span>${title}</span></div>
          ${pullProgressHtml(p)}
          ${attributed ? `<div class="gs-note">${t("Tek seferlik indirme; tamamlaninca yanit otomatik baslayacak.")}</div>` : ""}
        </div>`;
    }
    return `<div class="gen-status"><div class="gs-row"><span class="spin" aria-hidden="true"></span><span>${t("Model hazirlaniyor…")}</span></div></div>`;
  }

  function updateGenStatus(evt, targetConvId) {
    if (targetConvId && activeId !== targetConvId) return;
    const msgs = body.querySelectorAll(".msg.assistant .content");
    if (!msgs.length) return;
    const last = msgs[msgs.length - 1];
    last.innerHTML = genStatusHtml(evt);
    const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 90;
    if (nearBottom) body.scrollTop = body.scrollHeight;
  }

  function startPullWatch(asst, targetConvId) {
    let stopped = false;
    const idle = () => stopped || !!asst.content || !asst.streaming;
    const timer = setInterval(async () => {
      if (idle()) return;
      let r;
      try { r = await api("/api/v1/models"); } catch { return; }
      if (idle()) return;
      const states = r.states || [];
      const s = states.find(x => x.status === "pulling") || states.find(x => x.status === "queued");
      if (!s) return;
      updateGenStatus({
        stage: "pull", attributed: false, status: s.status, model_id: s.model_id,
        progress: s.pull_progress, stage_text: s.pull_stage,
        completed_mb: s.pull_completed_mb, total_mb: s.pull_total_mb,
        speed_mbps: s.pull_speed_mbps, eta_seconds: s.pull_eta_seconds,
      }, targetConvId);
    }, 1500);
    return { stop: () => { stopped = true; clearInterval(timer); } };
  }

  function updateLastContent(text, targetConvId) {
    // Kullanici baska sohbete gectiyse DOM'a yazma — store guncel kalir
    if (targetConvId && activeId !== targetConvId) return;
    const msgs = body.querySelectorAll(".msg.assistant .content");
    if (!msgs.length) return;
    const last = msgs[msgs.length - 1];
    const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 90;
    last.innerHTML = renderMarkdown(text);
    if (nearBottom) body.scrollTop = body.scrollHeight;
  }

  /* ---------- Mesaj aksiyonlari (kopyala / yeniden uret) ---------- */
  body.addEventListener("click", async (e) => {
    const btn = e.target.closest(".msg-act");
    if (!btn) return;
    const msgEl = btn.closest(".msg");
    const idx = parseInt(msgEl?.dataset.idx ?? "-1", 10);
    const conv = getActive();
    if (!conv || idx < 0 || !conv.messages[idx]) return;

    if (btn.dataset.act === "copy") {
      const ok = await copyToClipboard(conv.messages[idx].content || "");
      toast(ok ? t("Yanit kopyalandi") : t("Kopyalanamadi"), ok ? "ok" : "warn", 2000);
    } else if (btn.dataset.act === "regen") {
      if (isGenerating) return;
      const lastUser = [...conv.messages].reverse().find(m => m.role === "user");
      if (!lastUser) { toast(t("Yeniden uretilecek soru yok"), "warn"); return; }
      if (conv.messages[conv.messages.length - 1]?.role === "assistant") {
        conv.messages.pop();
      }
      saveConvs(convs);
      renderAll();
      await sendPrompt(lastUser.content, { skipUserPush: true });
    }
  });

  newChatBtn.onclick = () => {
    if (isGenerating && abortCtl) abortCtl.abort();
    newConv();
    renderAll();
    promptEl.focus();
  };

  // Sohbeti markdown olarak disa aktar
  const exportBtn = document.getElementById("exportBtn");
  if (exportBtn) {
    exportBtn.onclick = () => {
      const c = getActive();
      if (!c || !c.messages.length) { toast(t("Disa aktarilacak sohbet yok"), "warn"); return; }
      let md = `# ${c.title || t("Sohbet")}\n\n`;
      for (const m of c.messages) {
        if (m.role === "user") {
          md += `${t("**Soru:**")}\n\n${m.content}\n\n`;
        } else {
          const tag = m.meta?.model_id ? ` — ${m.meta.model_id}` : "";
          md += `${t("**Yanit{tag}:**", { tag })}\n\n${m.content}\n\n---\n\n`;
        }
      }
      const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = (c.title || t("sohbet")).replace(/[^\w-]+/g, "_").slice(0, 40) + ".md";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast(t("Sohbet markdown olarak indirildi"), "ok");
    };
  }

  // Klavye kisayolu: Ctrl/Cmd+Shift+O -> yeni sohbet
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "o") {
      e.preventDefault();
      newChatBtn.click();
    }
  });

  function renderAll() { renderSidebar(); renderBody(); }

  // Initial
  if (convs.length) activeId = convs[0].id;
  renderAll();
  autoResize();
  promptEl.focus();

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
})();
