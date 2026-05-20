/* Bootstrap progress overlay — sistem ready degilse gosterir.
   Token gerektirmez, /api/v1/system/bootstrap'i polluyor.
*/
(function () {
  const root = document.body;
  let overlayEl = null;
  let pollTimer = null;
  let lastReady = false;

  function ensureOverlay() {
    if (overlayEl) return overlayEl;
    overlayEl = document.createElement("div");
    overlayEl.className = "bootstrap-overlay";
    overlayEl.innerHTML = `
      <div class="panel">
        <h2><span class="pulse"></span> Sistem hazirlaniyor</h2>
        <div class="sub">Donanim taraniyor, kapasite plani uretiliyor ve modeller iniyor. Bu islem ilk acilista 30 sn - 5 dk surebilir.</div>
        <ul class="boot-steps" id="bootSteps"></ul>
      </div>
    `;
    root.appendChild(overlayEl);
    return overlayEl;
  }

  function removeOverlay() {
    if (!overlayEl) return;
    overlayEl.style.opacity = "0";
    overlayEl.style.transition = "opacity 250ms";
    setTimeout(() => { overlayEl?.remove(); overlayEl = null; }, 280);
  }

  function render(data) {
    ensureOverlay();
    const list = document.getElementById("bootSteps");
    list.innerHTML = "";
    for (const step of data.steps || []) {
      const li = document.createElement("li");
      li.className = "boot-step " + step.status;
      const detail = step.detail ? `<div class="detail">${escapeHtml(step.detail)}</div>` : "";
      const ms = step.elapsed_ms != null && step.status !== "pending"
        ? `<div class="ms">${step.elapsed_ms} ms</div>`
        : "";
      li.innerHTML = `
        <span class="icon"></span>
        <div class="body">
          <div class="label">${escapeHtml(step.label)}</div>
          ${detail}
        </div>
        ${ms}
      `;
      list.appendChild(li);
    }
  }

  async function tick() {
    try {
      const r = await fetch("/api/v1/system/bootstrap", { cache: "no-store" });
      if (!r.ok) return;
      const data = await r.json();
      if (data.ready && !lastReady) {
        lastReady = true;
        const allDone = (data.steps || []).every(s =>
          ["ok", "warn", "skipped", "error"].includes(s.status)
        );
        render(data);
        if (allDone) {
          setTimeout(removeOverlay, 600);
          stop();
        }
      } else if (data.ready) {
        const allDone = (data.steps || []).every(s =>
          ["ok", "warn", "skipped", "error"].includes(s.status)
        );
        if (allDone) { removeOverlay(); stop(); return; }
        render(data);
      } else {
        render(data);
      }
    } catch (e) {
      // baglanti yok — overlay'i acik birak, retry
      ensureOverlay();
    }
  }

  function start() {
    if (pollTimer) return;
    tick();
    pollTimer = setInterval(tick, 1500);
  }

  function stop() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  // Auto-start: her sayfada calissin (login dahil)
  document.addEventListener("DOMContentLoaded", start);

  window.bootstrapUI = { start, stop };
})();
