// RSSI-vs-time line chart (SVG). One series: no legend; the page title names it. 2px line, gaps where the
// BSSID wasn't heard, recessive grid, crosshair + tooltip on touch/drag, latest point marked.
const NS = 'http://www.w3.org/2000/svg';
const M = { l: 40, r: 12, t: 10, b: 24 };   // margins for axis labels
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const el = (tag, attrs = {}) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };

export function drawChart(svg, samples, windowS, now = Date.now()) {
  const W = svg.clientWidth, H = svg.clientHeight;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.replaceChildren();
  const t0 = windowS ? now - windowS * 1000 : (samples.length ? samples[0].t : now - 60000);
  const span = Math.max(now - t0, 1000);
  const shown = samples.filter(s => s.t >= t0);
  const vals = shown.filter(s => s.rssi != null).map(s => s.rssi);
  // y range: snap to 10 dBm, at least 30 dBm tall, within -100..-20
  let lo = vals.length ? Math.floor((Math.min(...vals) - 3) / 10) * 10 : -90;
  let hi = vals.length ? Math.ceil((Math.max(...vals) + 3) / 10) * 10 : -30;
  if (hi - lo < 30) lo = hi - 30;
  lo = Math.max(lo, -110); hi = Math.min(hi, -10);
  const x = t => M.l + (t - t0) / span * (W - M.l - M.r);
  const y = v => M.t + (hi - v) / (hi - lo) * (H - M.t - M.b);
  const grid = css('--grid'), muted = css('--text-muted'), series = css('--series-1'), surface = css('--surface-1');

  for (let v = lo; v <= hi; v += 10) {   // horizontal grid + dBm labels
    svg.append(el('line', { x1: M.l, x2: W - M.r, y1: y(v), y2: y(v), stroke: grid, 'stroke-width': 1 }));
    const tx = el('text', { x: M.l - 6, y: y(v) + 4, fill: muted, 'font-size': 11, 'text-anchor': 'end' }); tx.textContent = v; svg.append(tx);
  }
  const step = span <= 70000 ? 10000 : span <= 320000 ? 60000 : Math.ceil(span / 6 / 60000) * 60000;
  for (let k = 0; k * step <= span; k++) {   // time ticks, counted back from now
    const t = now - k * step; if (t < t0) break;
    const tx = el('text', { x: x(t), y: H - 6, fill: muted, 'font-size': 11, 'text-anchor': k ? 'middle' : 'end' });
    tx.textContent = k ? `-${step >= 60000 ? (k * step / 60000) + 'm' : (k * step / 1000) + 's'}` : 'now'; svg.append(tx);
  }
  // the line, broken where the BSSID wasn't heard (rssi null)
  let d = '', pen = false;
  for (const s of shown) {
    if (s.rssi == null) { pen = false; continue; }
    d += `${pen ? 'L' : 'M'}${x(s.t).toFixed(1)},${y(s.rssi).toFixed(1)}`; pen = true;
  }
  svg.append(el('path', { d, fill: 'none', stroke: series, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
  // lone points (heard once between gaps) would vanish as a line: show them as dots
  shown.forEach((s, i) => {
    if (s.rssi == null) return;
    const prev = shown[i - 1], next = shown[i + 1];
    if ((!prev || prev.rssi == null) && (!next || next.rssi == null))
      svg.append(el('circle', { cx: x(s.t), cy: y(s.rssi), r: 3, fill: series }));
  });
  const last = [...shown].reverse().find(s => s.rssi != null);
  if (last) svg.append(el('circle', { cx: x(last.t), cy: y(last.rssi), r: 4, fill: series, stroke: surface, 'stroke-width': 2 }));
  return { x, y, t0, span, shown };
}

// Crosshair + tooltip: the nearest sample to the finger.
export function attachHover(wrap, svg, tip, getState) {
  let cross = null;
  const move = e => {
    const st = getState(); if (!st || !st.shown.length) return;
    const r = svg.getBoundingClientRect(), px = e.clientX - r.left;
    const s = st.shown.filter(p => p.rssi != null).reduce((a, b) => Math.abs(st.x(b.t) - px) < Math.abs(st.x(a.t) - px) ? b : a, { t: -Infinity });
    if (!Number.isFinite(s.t)) return;
    if (!cross) { cross = el('line', { stroke: css('--text-secondary'), 'stroke-width': 1, 'stroke-dasharray': '3 3' }); }
    cross.setAttribute('x1', st.x(s.t)); cross.setAttribute('x2', st.x(s.t));
    cross.setAttribute('y1', M.t); cross.setAttribute('y2', svg.clientHeight - M.b);
    svg.append(cross);
    tip.textContent = `${s.rssi} dBm · ${new Date(s.t).toLocaleTimeString()}`;
    tip.style.left = `${st.x(s.t) + 4}px`; tip.style.top = `${st.y(s.rssi) + 6}px`;
    tip.hidden = false;
  };
  const end = () => { tip.hidden = true; if (cross) cross.remove(); };
  wrap.addEventListener('pointerdown', e => { wrap.setPointerCapture(e.pointerId); move(e); });
  wrap.addEventListener('pointermove', e => { if (e.buttons || e.pointerType === 'mouse') move(e); });
  wrap.addEventListener('pointerup', end);
  wrap.addEventListener('pointercancel', end);
  wrap.addEventListener('pointerleave', end);
}
