/* Bagimliliksiz, tema-uyumlu mini grafikler (SVG). Renkler CSS degiskenlerinden gelir. */
(function () {
  const esc = window.escapeHtml || ((s) => String(s));

  const PALETTE = [
    "var(--accent)", "var(--violet)", "var(--teal)",
    "var(--ok)", "var(--warn)", "var(--accent-2)",
  ];

  /* Yuzde donut/gauge — bir oran gosterir (orn. bellek butcesi). */
  function donut(el, value, max, opts = {}) {
    if (!el) return;
    const pct = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
    const r = 42;
    const circ = 2 * Math.PI * r;
    const offset = circ * (1 - pct);
    const tone = pct > 0.9 ? "var(--danger)" : pct > 0.7 ? "var(--warn)" : "var(--accent)";
    const label = opts.label != null ? opts.label : Math.round(pct * 100) + "%";
    el.innerHTML =
      `<svg viewBox="0 0 100 100" class="donut-svg" role="img" aria-label="${esc(opts.aria || label)}">` +
      `<circle class="donut-track" cx="50" cy="50" r="${r}"></circle>` +
      `<circle class="donut-val" cx="50" cy="50" r="${r}" stroke="${tone}" ` +
      `stroke-dasharray="${circ.toFixed(2)}" stroke-dashoffset="${offset.toFixed(2)}" ` +
      `transform="rotate(-90 50 50)"></circle>` +
      `<text class="donut-label" x="50" y="${opts.sub ? 47 : 54}">${esc(label)}</text>` +
      (opts.sub ? `<text class="donut-sub" x="50" y="61">${esc(opts.sub)}</text>` : "") +
      `</svg>`;
  }

  /* Yatay bar listesi — items: [{label, value, sub?, color?}] */
  function bars(el, items, opts = {}) {
    if (!el) return;
    if (!items || !items.length) {
      el.innerHTML = `<div class="muted" style="padding:0.5rem 0; font-size:0.82rem;">${esc(opts.empty || "Henuz veri yok")}</div>`;
      return;
    }
    const max = Math.max(1, ...items.map((i) => i.value || 0));
    el.innerHTML = items.map((it, idx) => {
      const w = ((it.value || 0) / max * 100).toFixed(1);
      const color = it.color || PALETTE[idx % PALETTE.length];
      return (
        `<div class="cbar-row">` +
        `<div class="cbar-label" title="${esc(it.label)}">${esc(it.label)}</div>` +
        `<div class="cbar-track"><div class="cbar-fill" style="width:${w}%; background:${color};"></div></div>` +
        `<div class="cbar-val">${esc(it.sub != null ? it.sub : it.value)}</div>` +
        `</div>`
      );
    }).join("");
  }

  /* Mini sparkline (trend cizgisi) — values: number[] */
  function sparkline(el, values, opts = {}) {
    if (!el) return;
    const vals = (values || []).filter((v) => typeof v === "number");
    if (vals.length < 2) { el.innerHTML = ""; return; }
    const w = opts.w || 140, h = opts.h || 36, pad = 3;
    const max = Math.max(...vals), min = Math.min(...vals), rng = (max - min) || 1;
    const x = (i) => (i / (vals.length - 1) * (w - pad * 2) + pad).toFixed(1);
    const y = (v) => (h - pad - ((v - min) / rng) * (h - pad * 2)).toFixed(1);
    const line = vals.map((v, i) => `${x(i)},${y(v)}`).join(" ");
    const area = `${x(0)},${h - pad} ` + line + ` ${x(vals.length - 1)},${h - pad}`;
    el.innerHTML =
      `<svg viewBox="0 0 ${w} ${h}" class="spark" preserveAspectRatio="none" role="img" aria-label="${esc(opts.aria || "trend")}">` +
      `<polygon class="spark-area" points="${area}"></polygon>` +
      `<polyline class="spark-line" points="${line}"></polyline>` +
      `</svg>`;
  }

  window.Charts = { donut, bars, sparkline, PALETTE };
})();
