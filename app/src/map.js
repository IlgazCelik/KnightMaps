// Pinch / drag / double-tap zoom for the floor plan (mouse wheel too, for the website).

const map = document.getElementById('map');
const img = document.getElementById('plan');
const overlay = document.getElementById('nodes');   // location nodes, kept on top of the plan

const MAX_ZOOM = 8;          // relative to fitting the whole plan on screen
const MIN_ZOOM = 0.3;
const DOUBLE_TAP_MS = 300;
const FIT_MARGIN = 8;        // px of space around the plan when fitted

let base = 1;                // scale at which the whole plan fits
let scale = 1;
let tx = 0;
let ty = 0;
const pointers = new Map();  // pointerId -> { x, y }
let moved = false;
let lastTap = 0;

function fit() {
  base = Math.min((map.clientWidth - 2 * FIT_MARGIN) / img.naturalWidth,
                  (map.clientHeight - 2 * FIT_MARGIN) / img.naturalHeight);
  scale = base;
  tx = (map.clientWidth - img.naturalWidth * scale) / 2;
  ty = (map.clientHeight - img.naturalHeight * scale) / 2;
  apply();
}

// The plan can be dragged out into empty space, but some of it always stays under the middle of the screen.
function clamp() {
  const W = map.clientWidth, H = map.clientHeight;
  const w = img.naturalWidth * scale, h = img.naturalHeight * scale;
  tx = Math.min(W / 2, Math.max(W / 2 - w, tx));
  ty = Math.min(H / 2, Math.max(H / 2 - h, ty));
}

function apply() {
  clamp();
  // Size the image itself (not a CSS scale) so the vector plan is redrawn sharp at every zoom level.
  img.style.width = `${img.naturalWidth * scale}px`;
  img.style.height = `${img.naturalHeight * scale}px`;
  img.style.transform = `translate(${tx}px, ${ty}px)`;
  for (const el of [overlay]) {
    el.style.width = img.style.width;
    el.style.height = img.style.height;
    el.style.transform = img.style.transform;
  }
}

// Zooms by factor f, keeping the point (cx, cy) under the finger fixed.
function zoomAt(f, cx, cy) {
  const next = Math.min(base * MAX_ZOOM, Math.max(base * MIN_ZOOM, scale * f));
  f = next / scale;
  tx = cx - (cx - tx) * f;
  ty = cy - (cy - ty) * f;
  scale = next;
}

function local(e) {
  const r = map.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}

const TAP_SLOP_PX = 8;   // a finger moving less than this is still a tap, not a drag
let downAt = null;

map.addEventListener('pointerdown', e => {
  map.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, local(e));
  downAt = local(e);
  moved = false;
});

map.addEventListener('pointermove', e => {
  if (!pointers.has(e.pointerId)) return;
  const prev = [...pointers.values()];
  pointers.set(e.pointerId, local(e));
  const cur = [...pointers.values()];

  if (cur.length === 1) {
    const dx = cur[0].x - prev[0].x, dy = cur[0].y - prev[0].y;
    if (downAt && Math.hypot(cur[0].x - downAt.x, cur[0].y - downAt.y) > TAP_SLOP_PX) moved = true;
    tx += dx;
    ty += dy;
  } else {
    // Two fingers: pan with their midpoint, zoom with the change in distance between them.
    const mid = p => ({ x: (p[0].x + p[1].x) / 2, y: (p[0].y + p[1].y) / 2 });
    const dist = p => Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y);
    const m0 = mid(prev), m1 = mid(cur);
    tx += m1.x - m0.x;
    ty += m1.y - m0.y;
    if (dist(prev) > 0) zoomAt(dist(cur) / dist(prev), m1.x, m1.y);
    moved = true;
  }
  apply();
});

function release(e) {
  if (!pointers.has(e.pointerId)) return;
  const p = pointers.get(e.pointerId);
  pointers.delete(e.pointerId);
  if (e.type !== 'pointerup' || moved || pointers.size) return;

  // Double tap: zoom in on that spot, or back out to the whole plan if already zoomed.
  const now = Date.now();
  if (now - lastTap < DOUBLE_TAP_MS) {
    clearTimeout(tapTimer);
    if (scale > base * 1.01) fit();
    else { zoomAt(3, p.x, p.y); apply(); }
    lastTap = 0;
  } else {
    lastTap = now;
    // Single tap (once it's clear no second tap follows): tell the app which plan point was tapped.
    const plan = { x: (p.x - tx) / scale, y: (p.y - ty) / scale };
    tapTimer = setTimeout(() => map.dispatchEvent(new CustomEvent('plan-tap', { detail: plan })), DOUBLE_TAP_MS);
  }
}
let tapTimer = 0;
map.addEventListener('pointerup', release);
map.addEventListener('pointercancel', release);

map.addEventListener('wheel', e => {
  e.preventDefault();
  const p = local(e);
  zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, p.x, p.y);
  apply();
}, { passive: false });

// Rotating the phone (width changes) refits the plan; the keyboard opening (height only) keeps the zoom.
let lastWidth = map.clientWidth;
window.addEventListener('resize', () => {
  if (map.clientWidth !== lastWidth) { lastWidth = map.clientWidth; fit(); }
  else apply();
});
if (img.complete && img.naturalWidth) fit();
else img.addEventListener('load', fit);
