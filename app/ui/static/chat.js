(async function () {
  const user = window.currentUser || {};
  const isAdmin = user.role === "admin";

  /* ---------- Conversation store (localStorage) ---------- */
  const STORAGE = "hub_convs_v1";
  function loadConvs() {
    try { return JSON.parse(localStorage.getItem(STORAGE) || "[]"); } catch { return []; }
  }
  function saveConvs(list) { localStorage.setItem(STORAGE, JSON.stringify(list)); }
  let convs = loadConvs();
  let activeId = null;

  function newConv() {
    const id = "c" + Date.now();
    const c = { id, title: "Yeni sohbet", created_at: Date.now(), messages: [] };
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
        <span class="title">${escapeHtml(c.title || "Sohbet")}</span>
        <button class="del" data-del="${c.id}" title="Sil">✕</button>`;
      li.onclick = (e) => {
        if (e.target.dataset.del) {
          if (!confirm("Bu sohbet silinsin mi?")) return;
          deleteConv(e.target.dataset.del);
          renderAll();
          return;
        }
        activeId = c.id;
        renderAll();
      };
      convListEl.appendChild(li);
    }
    if (!convs.length) {
      convListEl.innerHTML = `<li class="muted" style="padding:0.5rem 0.6rem; font-size:0.8rem;">Henuz sohbet yok.</li>`;
    }
  }

  function renderBody() {
    const c = getActive();
    body.innerHTML = "";
    if (!c || !c.messages.length) {
      titleEl.textContent = c?.title || "Yeni sohbet";
      const dep = user.department || "general";
      const examples = examplePromptsFor(dep);
      body.innerHTML = `
        <div class="chat-empty">
          <h2>Merhaba ${escapeHtml(user.label || user.username || "")}</h2>
          <p>${escapeHtml(dep)} departmaniniza atanmis modele otomatik yonlendireceğim. Asagidan birini secebilir veya kendi sorunuzu yazabilirsiniz.</p>
          <div class="examples">
            ${examples.map(ex => `
              <div class="ex-card" data-ex="${escapeHtml(ex.prompt)}">
                <div class="ex-title">${escapeHtml(ex.title)}</div>
                <div class="ex-sub">${escapeHtml(ex.sub)}</div>
              </div>
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
    titleEl.textContent = c.title || "Sohbet";
    for (const m of c.messages) {
      body.appendChild(renderMsg(m));
    }
    body.scrollTop = body.scrollHeight;
  }

  function renderMsg(m) {
    const div = document.createElement("div");
    div.className = "msg " + m.role;
    const avatar = m.role === "user"
      ? (user.label || user.username || "?").trim().slice(0, 2).toUpperCase()
      : "AI";
    const meta = m.role === "assistant" && m.meta
      ? `<div class="meta">
          <span class="badge ok">${escapeHtml(m.meta.model_id || "")}</span>
          <span class="badge plain">${escapeHtml(m.meta.category || "")}</span>
          ${m.meta.fallback_triggered ? '<span class="badge warn">fallback</span>' : ""}
          ${m.meta.latency_ms ? `<span class="muted">${Math.round(m.meta.latency_ms)} ms · ${m.meta.eval_count || 0} tok</span>` : ""}
        </div>` : "";
    div.innerHTML = `
      <div class="avatar">${escapeHtml(avatar)}</div>
      <div class="body">
        ${meta}
        <div class="content${m.streaming ? " streaming" : ""}">${escapeHtml(m.content || "")}</div>
      </div>`;
    return div;
  }

  function examplePromptsFor(dep) {
    const map = {
      engineering: [
        { title: "Kod review", sub: "Bu fonksiyonu daha temiz nasil yazarim?", prompt: "Asagidaki Python fonksiyonunu daha temiz hale getir:\n\ndef calc(items):\n    s = 0\n    for i in items:\n        if i > 0: s += i\n    return s" },
        { title: "Bug ariyorum", sub: "Hata mesajini birlikte inceleyelim", prompt: "Su hatayi alıyorum, sebebi ne olabilir: 'TypeError: cannot unpack non-iterable NoneType object'" },
      ],
      hr: [
        { title: "Mulakat sorulari", sub: "Junior developer icin 5 soru", prompt: "Junior bir Python developer pozisyonu icin teknik ve davranissal toplam 5 mulakat sorusu yaz." },
        { title: "Iz politikasi", sub: "Kisaca ozet", prompt: "Yillik iznin kisaca nasil hesaplandigini 3 maddede acikla." },
      ],
      finance: [
        { title: "Hizli hesap", sub: "KDV dahil/haric", prompt: "Hesapla: 12500 TL'lik bir hizmetin %20 KDV dahil ve haric tutari nedir? Aciklamali yaz." },
        { title: "Tahmin", sub: "Aylik gelir tahmini", prompt: "Asagidaki son 6 ay gelir verisine bakarak gelecek 3 ayi tahmin et: 120k, 135k, 128k, 142k, 150k, 145k" },
      ],
      legal: [
        { title: "Sozlesme ozeti", sub: "Kisaca ana noktalar", prompt: "Bir SaaS hizmet sozlesmesindeki en kritik 5 maddeyi ozetle." },
      ],
      marketing: [
        { title: "Reklam metni", sub: "3 farkli ton", prompt: "Bir yeni mobil bankacilik uygulamasi icin: profesyonel, samimi ve mizahi tonda birer Twitter reklami yaz." },
      ],
      general: [
        { title: "Acikla", sub: "Konsept anlama", prompt: "Docker container ile sanal makine farkini bana 3 cumlede acikla." },
        { title: "Cevirisi", sub: "Hizli ceviri", prompt: "Lutfen su cumleyi Ingilizce'ye dogru cevir: 'Bu projeyi onumuzdeki hafta teslim edebiliriz.'" },
      ],
    };
    return map[dep] || map.general;
  }

  /* ---------- Send flow ---------- */
  function ensureActive() {
    if (!getActive()) {
      newConv();
    }
  }

  promptEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
  promptEl.addEventListener("input", autoResize);
  function autoResize() {
    promptEl.style.height = "auto";
    promptEl.style.height = Math.min(180, promptEl.scrollHeight) + "px";
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = promptEl.value.trim();
    if (!prompt) return;
    sendBtn.disabled = true;
    sendBtn.textContent = "...";

    ensureActive();
    const conv = getActive();

    // Add user message
    conv.messages.push({ role: "user", content: prompt, ts: Date.now() });
    if (conv.messages.length === 1) {
      conv.title = prompt.slice(0, 40) + (prompt.length > 40 ? "…" : "");
    }
    saveConvs(convs);
    renderAll();
    promptEl.value = "";
    autoResize();

    // Add assistant placeholder
    const asst = { role: "assistant", content: "", streaming: true, meta: null, ts: Date.now() };
    conv.messages.push(asst);
    renderBody();

    const useStream = streamToggle.checked;
    const adminPick = isAdmin ? adminPicker.value : "";

    const body_ = { prompt };
    if (adminPick) body_.model_id = adminPick;

    try {
      if (useStream) {
        await runStream(asst, body_);
      } else {
        await runOneShot(asst, body_);
      }
    } catch (err) {
      asst.streaming = false;
      asst.content = `Hata: ${err.message}`;
      asst.meta = { model_id: "—", category: "error" };
      toast("Istek basarisiz: " + err.message, "error", 5000);
    } finally {
      asst.streaming = false;
      saveConvs(convs);
      renderAll();
      sendBtn.disabled = false;
      sendBtn.textContent = "Gonder ↵";
      promptEl.focus();
    }
  });

  async function runOneShot(asst, body_) {
    const r = await api("/api/v1/chat", { method: "POST", body: JSON.stringify(body_) });
    asst.content = r.response || "(bos yanit)";
    asst.meta = {
      model_id: r.model_id, category: r.category,
      matched_rule: r.matched_rule, fallback_triggered: r.fallback_triggered,
      latency_ms: r.latency_ms, eval_count: r.eval_count,
    };
    renderBody();
  }

  async function runStream(asst, body_) {
    const t0 = performance.now();
    const token = localStorage.getItem("token");
    const resp = await fetch("/api/v1/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": token ? `Bearer ${token}` : "",
      },
      body: JSON.stringify(body_),
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
          renderBody();
        } else if (evt.event === "token") {
          if (evt.response) {
            asst.content += evt.response;
            updateLastContent(asst.content);
          }
          if (evt.done) evalCount = evt.eval_count || 0;
        } else if (evt.event === "error") {
          throw new Error(evt.detail || "Stream hatasi");
        }
      }
    }
    const dt = performance.now() - t0;
    if (asst.meta) {
      asst.meta.latency_ms = dt;
      asst.meta.eval_count = evalCount;
    }
  }

  function updateLastContent(text) {
    const msgs = body.querySelectorAll(".msg.assistant .content");
    if (!msgs.length) return;
    const last = msgs[msgs.length - 1];
    last.textContent = text;
    body.scrollTop = body.scrollHeight;
  }

  newChatBtn.onclick = () => {
    newConv();
    renderAll();
    promptEl.focus();
  };

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
