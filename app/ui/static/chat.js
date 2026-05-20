(async function () {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const isAdmin = user.role === "admin";
  if (isAdmin) {
    document.getElementById("adminPicker").classList.remove("hidden");
    try {
      const ml = await api("/api/v1/models");
      const sel = document.getElementById("adminModel");
      for (const s of (ml.states || [])) {
        const opt = document.createElement("option");
        opt.value = s.model_id;
        opt.textContent = `${s.model_id} [${s.category}] · ${s.status}`;
        sel.appendChild(opt);
      }
    } catch (e) { console.error(e); }
  }

  const form = document.getElementById("chatForm");
  const log = document.getElementById("chatLog");
  const promptEl = document.getElementById("prompt");
  const btn = form.querySelector("button[type=submit]");

  /* Ctrl/Cmd+Enter => submit */
  promptEl.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = promptEl.value.trim();
    if (!prompt) return;
    btn.disabled = true;
    btn.textContent = "Gonderiliyor...";

    const turn = document.createElement("div");
    turn.className = "turn";
    turn.innerHTML = `
      <div class="meta"><span class="badge busy">isteniyor</span></div>
      <div class="prompt"><strong>Siz:</strong>${escapeHtml(prompt)}</div>
      <div class="response streaming"></div>
    `;
    log.prepend(turn);

    const useStream = document.getElementById("streamToggle").checked;
    const body = { prompt };
    if (isAdmin) {
      const v = document.getElementById("adminModel").value;
      if (v) body.model_id = v;
    }
    try {
      if (useStream) await runStream(turn, body);
      else           await runOneShot(turn, body);
      promptEl.value = "";
    } catch (err) {
      turn.querySelector(".meta").innerHTML = `<span class="badge error">hata</span>`;
      turn.querySelector(".response").classList.remove("streaming");
      turn.querySelector(".response").textContent = err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = "Gonder";
    }
  });

  async function runOneShot(turn, body) {
    const t0 = performance.now();
    const r = await api("/api/v1/chat", { method: "POST", body: JSON.stringify(body) });
    const dt = (performance.now() - t0).toFixed(0);
    renderMeta(turn, r, dt, r.eval_count);
    const resp = turn.querySelector(".response");
    resp.classList.remove("streaming");
    resp.textContent = r.response || "(bos yanit)";
  }

  async function runStream(turn, body) {
    const t0 = performance.now();
    const token = localStorage.getItem("token");
    const resp = await fetch("/api/v1/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": token ? `Bearer ${token}` : "",
      },
      body: JSON.stringify(body),
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
    let header = null;
    const respEl = turn.querySelector(".response");
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
          header = evt;
          renderMeta(turn, evt, null, null, true);
        } else if (evt.event === "token") {
          if (evt.response) respEl.textContent += evt.response;
          if (evt.done) evalCount = evt.eval_count || 0;
        } else if (evt.event === "error") {
          throw new Error(evt.detail || "Stream hatasi");
        }
      }
    }
    respEl.classList.remove("streaming");
    const dt = (performance.now() - t0).toFixed(0);
    renderMeta(turn, header || {}, dt, evalCount);
  }

  function renderMeta(turn, r, dtMs, tok, streaming = false) {
    const meta = turn.querySelector(".meta");
    const fallbackBadge = r.fallback_triggered ? `<span class="badge warn">fallback</span>` : "";
    const stat = streaming
      ? `<span class="badge busy">streaming</span>`
      : (dtMs !== null ? `<span class="muted">${dtMs} ms · ${tok || 0} tok</span>` : "");
    meta.innerHTML = `
      <span class="badge ok">${r.model_id || "?"}</span>
      <span class="badge plain">${r.category || "?"}</span>
      <span class="badge plain">${r.matched_rule || "?"}</span>
      ${fallbackBadge}
      ${stat}`;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
