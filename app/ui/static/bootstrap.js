/* Bootstrap overlay — SADECE backend ready=false oldugunda gosterilir.
   - Sayfa yuklendiginde tek bir HEAD-style fetch atilir
   - ready=true ise overlay yaratilmaz, polling baslamaz
   - ready=false ise overlay olusturulur, 1.5sn polling baslar
   - ready'a gecince fade-out + polling stop
   - localStorage 'hub_bootstrapped' bayragi: bir kez ready oldu mu, sonraki
     sayfa gecislerinde fetch bile yapilmaz (oturum kapanana kadar)
*/
(function () {
  const STORAGE_KEY = "hub_bootstrapped";
  let overlayEl = null;
  let pollTimer = null;

  async function fetchStatus() {
    try {
      const r = await fetch("/api/v1/system/bootstrap", { cache: "no-store" });
      if (!r.ok) return null;
      return await r.json();
    } catch { return null; }
  }

  function ensureOverlay() {
    if (overlayEl) return overlayEl;
    overlayEl = document.createElement("div");
    overlayEl.className = "bootstrap-overlay";
    overlayEl.innerHTML = `
      <div class="panel">
        <h2><span class="pulse"></span> Sistem hazirlaniyor</h2>
        <div class="sub">Donanim taraniyor, kapasite plani uretiliyor.<br/>Ilk acilis 5-30 sn surebilir.</div>
        <ul class="boot-steps" id="bootSteps"></ul>
      </div>`;
    document.body.appendChild(overlayEl);
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
      const detail = step.detail ? `<div class="detail">${escape(step.detail)}</div>` : "";
      const ms = step.elapsed_ms != null && step.status !== "pending"
        ? `<div class="ms">${step.elapsed_ms} ms</div>` : "";
      li.innerHTML = `
        <span class="icon"></span>
        <div class="body">
          <div class="label">${escape(step.label)}</div>
          ${detail}
        </div>
        ${ms}`;
      list.appendChild(li);
    }
  }

  function escape(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  async function start() {
    // Bir kez ready olduysa bu oturumda hic fetch atma
    if (sessionStorage.getItem(STORAGE_KEY) === "1") return;
    const first = await fetchStatus();
    if (!first) return;  // baglanti yok — sessizce gec
    if (first.ready) {
      sessionStorage.setItem(STORAGE_KEY, "1");
      return;  // overlay yaratilmaz
    }
    // Hazir degil — overlay ac + polling
    render(first);
    pollTimer = setInterval(async () => {
      const data = await fetchStatus();
      if (!data) return;
      render(data);
      if (data.ready) {
        sessionStorage.setItem(STORAGE_KEY, "1");
        clearInterval(pollTimer);
        pollTimer = null;
        setTimeout(removeOverlay, 500);
      }
    }, 1500);
  }

  document.addEventListener("DOMContentLoaded", start);
})();
