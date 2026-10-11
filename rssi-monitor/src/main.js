import { RssiScan } from './scanner.js';
import { drawChart, attachHover } from './chart.js';

// Watch one BSSID: scan continuously and plot its RSSI against time.
const $ = id => document.getElementById(id);
const bssidInput = $('bssid'), nearby = $('nearby'), runBtn = $('run'), statusEl = $('status');
const svg = $('chart'), wrap = $('chart-wrap'), tip = $('tip'), nowEl = $('now'), metaEl = $('meta'), tableEl = $('table');
const norm = b => b.trim().toLowerCase();
const KEY = 'rssiMonitorBssid';

let target = '';
try { target = localStorage.getItem(KEY) || ''; } catch {}
bssidInput.value = target;
let samples = [];        // { t: epoch ms (when the AP was heard), rssi: dBm or null = not heard }
let lastSeenAt = 0;      // newest measurement time already recorded (cached repeats are skipped)
let running = false, windowS = 60, state = null, lastNetworks = [];

function setTarget(b) {
  const next = norm(b);
  if (next === target) return;
  target = next;
  bssidInput.value = target;
  samples = []; lastSeenAt = 0;
  try { localStorage.setItem(KEY, target); } catch {}
  render();
}
bssidInput.addEventListener('change', () => setTarget(bssidInput.value));

// ---- scanning
async function scanOnce() {
  const { fresh, networks } = await RssiScan.scan();
  lastNetworks = networks;
  const hit = networks.find(n => norm(n.bssid) === target);
  if (hit) {
    if (hit.seenAt > lastSeenAt) {   // a new measurement (not a repeat of a cached one)
      samples.push({ t: hit.seenAt, rssi: hit.rssi });
      lastSeenAt = hit.seenAt;
    }
  } else if (fresh) {
    samples.push({ t: Date.now(), rssi: null });   // a full scan that didn't hear it: break the line
  }
  statusEl.textContent = fresh ? '' : 'Android is limiting scans: readings come every ~30 s. Turn off "Wi-Fi scan throttling" in Developer options for one every few seconds.';
}

async function loop() {
  while (running) {
    try { await scanOnce(); } catch (e) { statusEl.textContent = e.message || String(e); }
    render();
    await new Promise(r => setTimeout(r, 400));
  }
}

runBtn.addEventListener('click', () => {
  if (!target) { setTarget(bssidInput.value); if (!target) { statusEl.textContent = 'Enter a BSSID first (or tap Nearby).'; return; } }
  running = !running;
  runBtn.textContent = running ? 'Stop' : 'Start';
  runBtn.classList.toggle('on', running);
  if (running) loop();
});

// ---- choosing a BSSID from what's in range
$('pick').addEventListener('click', async () => {
  if (!nearby.hidden) { nearby.hidden = true; return; }
  statusEl.textContent = 'Scanning…';
  try { if (!running) lastNetworks = (await RssiScan.scan()).networks; statusEl.textContent = ''; }
  catch (e) { statusEl.textContent = e.message || String(e); return; }
  nearby.replaceChildren(...[...lastNetworks].sort((a, b) => b.rssi - a.rssi).map(n => {
    const li = document.createElement('li');
    li.innerHTML = `<span class="b"></span><span class="r"></span><span class="s"></span>`;
    li.querySelector('.b').textContent = n.bssid;
    li.querySelector('.s').textContent = n.ssid || '(hidden network)';
    li.querySelector('.r').textContent = `${n.rssi} dBm`;
    li.addEventListener('click', () => { setTarget(n.bssid); nearby.hidden = true; });
    return li;
  }));
  nearby.hidden = false;
});

// ---- window, table, clear
document.querySelectorAll('[data-window]').forEach(b => b.addEventListener('click', () => {
  windowS = Number(b.dataset.window);
  document.querySelectorAll('[data-window]').forEach(o => o.setAttribute('aria-pressed', String(o === b)));
  render();
}));
$('table-toggle').addEventListener('click', e => {
  const on = e.currentTarget.getAttribute('aria-pressed') !== 'true';
  e.currentTarget.setAttribute('aria-pressed', String(on));
  tableEl.hidden = !on;
  render();
});
$('clear').addEventListener('click', () => { samples = []; lastSeenAt = 0; render(); });

// ---- drawing
function render() {
  state = drawChart(svg, samples, windowS);
  const last = [...samples].reverse().find(s => s.rssi != null);
  nowEl.innerHTML = `${last ? last.rssi : '—'} <small>dBm</small>`;
  const n = samples.filter(s => s.rssi != null).length;
  metaEl.textContent = !target ? 'Pick a BSSID and press Start'
    : `${target} · ${n} sample${n === 1 ? '' : 's'}${last ? ` · heard ${Math.max(0, Math.round((Date.now() - last.t) / 1000))} s ago` : ''}`;
  if (!tableEl.hidden) {
    const rows = [...samples].reverse().slice(0, 100).map(s =>
      `<tr><td>${new Date(s.t).toLocaleTimeString()}</td><td class="num">${s.rssi == null ? 'not heard' : s.rssi + ' dBm'}</td></tr>`).join('');
    tableEl.innerHTML = `<table><thead><tr><th>Time</th><th class="num">RSSI</th></tr></thead><tbody>${rows}</tbody></table>`;
  }
}
attachHover(wrap, svg, tip, () => state);
setInterval(render, 1000);   // keeps the time axis and "heard … s ago" moving
window.addEventListener('resize', render);
render();
