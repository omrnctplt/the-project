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
      <div class="response">...</div>
    `;
    log.prepend(turn);
    try {
      const body = { prompt };
      if (isAdmin) {
        const v = document.getElementById("adminModel").value;
        if (v) body.model_id = v;
      }
      const t0 = performance.now();
      const r = await api("/api/v1/chat", { method: "POST", body: JSON.stringify(body) });
      const dt = (performance.now() - t0).toFixed(0);
      const meta = turn.querySelector(".meta");
      meta.innerHTML = `
        <span class="badge ok">${r.model_id}</span>
        <span class="badge">${r.category}</span>
        <span class="badge">${r.matched_rule}</span>
        ${r.fallback_triggered ? '<span class="badge warn">fallback</span>' : ""}
        <span class="muted">${r.latency_ms ? r.latency_ms.toFixed(0) : dt} ms · ${r.eval_count || 0} tok</span>
      `;
      turn.querySelector(".response").textContent = r.response || "(bos yanit)";
      document.getElementById("prompt").value = "";
    } catch (err) {
      turn.querySelector(".meta").innerHTML = `<span class="badge error">hata</span>`;
      turn.querySelector(".response").textContent = err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = "Gonder";
    }
  });

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
