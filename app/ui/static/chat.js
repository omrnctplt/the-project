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
        opt.textContent = `${s.model_id} [${s.category}]`;
        sel.appendChild(opt);
      }
    } catch (e) { console.error(e); }
  }

  const form = document.getElementById("chatForm");
  const log = document.getElementById("chatLog");
  const btn = form.querySelector("button");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = document.getElementById("prompt").value.trim();
    if (!prompt) return;
    btn.disabled = true;
    btn.textContent = "Bekleniyor...";
    const turn = document.createElement("div");
    turn.className = "turn";
    turn.innerHTML = `
      <div class="meta"><span class="badge">isteniyor...</span></div>
      <div class="prompt"><strong>Siz:</strong> ${escapeHtml(prompt)}</div>
      <div class="response"></div>
    `;
    log.prepend(turn);
    const useStream = document.getElementById("streamToggle").checked;
    const body = { prompt };
    if (isAdmin) {
      const v = document.getElementById("adminModel").value;
      if (v) body.model_id = v;
    }
    try {
      if (useStream) {
        await runStream(turn, body);
      } else {
        await runOneShot(turn, body);
      }
      document.getElementById("prompt").value = "";
    } catch (err) {
      turn.querySelector(".meta").innerHTML = `<span class="badge error">hata</span>`;
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
    turn.querySelector(".meta").innerHTML = `
      <span class="badge ok">${r.model_id}</span>
      <span class="badge">${r.category}</span>
      <span class="badge">${r.matched_rule}</span>
      ${r.fallback_triggered ? '<span class="badge warn">fallback</span>' : ""}
      <span class="muted">${r.latency_ms ? r.latency_ms.toFixed(0) : dt} ms · ${r.eval_count || 0} tok</span>`;
    turn.querySelector(".response").textContent = r.response || "(bos yanit)";
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
    const respEl = turn.querySelector(".response");
    const metaEl = turn.querySelector(".meta");
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
          metaEl.innerHTML = `
            <span class="badge ok">${evt.model_id}</span>
            <span class="badge">${evt.category}</span>
            <span class="badge">${evt.matched_rule}</span>
            ${evt.fallback_triggered ? '<span class="badge warn">fallback</span>' : ""}
            <span class="muted">streaming...</span>`;
        } else if (evt.event === "token") {
          if (evt.response) {
            respEl.textContent += evt.response;
          }
          if (evt.done) {
            evalCount = evt.eval_count || 0;
          }
        } else if (evt.event === "error") {
          throw new Error(evt.detail || "Stream hatasi");
        }
      }
    }
    const dt = (performance.now() - t0).toFixed(0);
    const badges = metaEl.querySelectorAll(".badge");
    metaEl.innerHTML = "";
    badges.forEach((b) => { if (!b.textContent.includes("streaming")) metaEl.appendChild(b); });
    const muted = document.createElement("span");
    muted.className = "muted";
    muted.textContent = `${dt} ms · ${evalCount} tok`;
    metaEl.appendChild(muted);
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
