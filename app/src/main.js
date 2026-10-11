import { WifiScan } from './wifi.js';
import { cellToPlan, goalPoint, guidance, highlightRoom, placeAlongRoute, placeDot, setAccuracy, setPhoneDirection, setStandingStill, setWalkingDirection, setWalkingSpeed, showRoute } from './nodes.js';
import { BSSID_ORDER } from './bssid_order.js';
import { ROOMS } from './rooms.js';
import { initSearch, setQuery } from './search.js';
import { initVoice, stopVoice } from './voice.js';
import { sendPickedImage, startCamera, stopCamera, takeAndSend } from './camera.js';
import { setOutsidePosition, stopOutside } from './outside.js';
import { instruction, showInstruction } from './directions.js';

// Localization server endpoint; each round is one POST, like requests.post(url, json=numeric_vector).
const SERVER_URL = 'http://10.42.0.1:5000/api/localize_json?k=3';
const SERVER_TIMEOUT_MS = 10000;   // give up on a request after this long
// Dead reckoning between server fixes: position = server fix + steps walked since the fix's timestamp.
// Map calibration (set these for your building):
// From Engineering I's real outline (OpenStreetMap, traced from aerial imagery): its walls run at
// 44/134/224/314 deg true, and the top of the map faces 134. (An earlier indoor compass reading gave 165 --
// steel in the building throws the compass off, so the outline is the better source.)
const MAP_UP_BEARING = 134;   // true-north bearing (degrees, clockwise) that the top of the grid faces
const METERS_PER_CELL = 1.0;  // size of one grid cell in metres
const MOTION_UPDATE_MS = 100; // how often the target is updated from the motion sensors
// Destination sent to the server, [row, col] on the grid: the hallway just outside the room picked in the
// search bar. None by default (and after arriving, or choosing "No destination"): goal is then null.
let goalRoom = null;
let GOAL = null;
const ARRIVED_M = 2.5;   // this close to the goal ring counts as arrived
const MISSING_RSSI = 0;   // BSSIDs in the order that this scan didn't see (sent as 0.0)

const statusEl = document.getElementById('status');
const scanBtn = document.getElementById('scan');

// Wi-Fi Direct peers (printers, laptops, TVs) also show up in Wi-Fi scans; keep only real access points.
// Android sometimes reports RSSI 0 for an entry it has no valid reading for; real RSSI is always negative.
function isAccessPoint(n) {
  return !(n.ssid || '').startsWith('DIRECT-') && n.rssi < 0;
}

const PAUSE_BETWEEN_MS = 1500;   // breather between tracking cycles

let tracking = false;
let fix = null;          // latest server fix: { row, col, time } (time = epoch ms the fix applies to)
let motionTimer = 0;
let run = 0;   // identifies the current tracking loop, so a quick Stop -> Locate never leaves two running

function stopTracking() {
  tracking = false;
  clearInterval(motionTimer);
  motionTimer = 0;
  WifiScan.stopMotion();
  scanBtn.textContent = 'Locate';
  scanBtn.classList.remove('tracking');
  statusEl.textContent = '';
}

// Locate starts continuous tracking; pressing it again (now "Stop") ends it.
async function toggleTracking() {
  if (tracking) return stopTracking();
  tracking = true;
  const me = ++run;
  fix = null;
  WifiScan.startMotion().catch(() => {});   // without motion sensors the dot just follows the server
  motionTimer = setInterval(moveByMotion, MOTION_UPDATE_MS);
  scanBtn.textContent = 'Stop';
  scanBtn.classList.add('tracking');
  statusEl.textContent = 'Locating…';
  while (tracking && me === run) {
    const problem = await locateOnce();
    if (!tracking || me !== run) break;
    statusEl.textContent = problem;   // '' while all is well, else what went wrong
    await new Promise(r => setTimeout(r, PAUSE_BETWEEN_MS));
  }
}

// One cycle: Wi-Fi scan + compass heading -> server -> move the gold dot. Returns '' or a problem message.
async function locateOnce() {
  try {
    // Which way the phone faces, read while the Wi-Fi scan runs (null if the compass can't tell).
    const headingRead = WifiScan.getHeading().then(h => h.heading, () => null);
    const { supported, networks } = await WifiScan.scan();
    if (supported === false) {
      tracking = false;
      return 'Wi-Fi scanning only works in the Android app.';
    }
    const readings = networks.filter(isAccessPoint)
      .sort((a, b) => b.rssi - a.rssi)
      .map(({ bssid, rssi }) => ({ bssid, rssi }));
    if (!readings.length) return 'No Wi-Fi networks found';   // e.g. while Wi-Fi is switching networks
    const scannedAt = Date.now();
    return await sendScan(toVector(readings), await headingRead, scannedAt);
  } catch (err) {
    return 'Error: ' + (err.message || err);
  }
}

// The scan as an RSSI vector: one number per BSSID in BSSID_ORDER (message-4.txt), unseen ones = MISSING_RSSI.
function toVector(readings) {
  const seen = new Map(readings.map(r => [r.bssid.toLowerCase(), r.rssi]));
  return BSSID_ORDER.map(b => seen.get(b) ?? MISSING_RSSI);
}

// POSTs the payload as JSON (json.dumps formatting: floats, ", " separators):
//   {"orientation": 271.5, "goal": [34.0, 36.0], "scan": [0.0, 0.0, -74.0, ...]}
// orientation = degrees clockwise from true north (0 = north, 90 = east), null if the compass couldn't tell.
// and reads the JSON reply: {"success": true, "estimated_coord": [row, col], ...} or {"success": false, "error": "..."}
async function sendScan(vector, orientation, scannedAt) {
  try {
    const request = fetch(SERVER_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: `{"orientation": ${orientation == null ? 'null' : orientation.toFixed(1)}, `
        + `"goal": ${GOAL ? `[${GOAL.map(v => v.toFixed(1)).join(', ')}]` : 'null'}, `
        + `"scan": [${vector.map(v => v.toFixed(1)).join(', ')}]}`,
    }).then(async res => ({ res, text: await res.text() }));
    const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), SERVER_TIMEOUT_MS));
    const { res, text } = await Promise.race([request, timeout]);
    console.log(`Server response (${res.status}): ${text}`);
    if (!res.ok) return `Server error ${res.status}`;
    return showReply(text, scannedAt);   // '' on success: the moving dot is the only feedback
  } catch {
    return "Can't reach the server";
  }
}

// Takes the server's position as the new fix and draws its route. The reply looks like
//   {"success": true, "estimated_coord": [42.5312, 88.1024], "orientation": 271.5, "goal_coord": [45.0, 80.0],
//    "matches": [...], "path": [[42, 88], [42, 80], [45, 80]], "timestamp": 1791643055.14289}
// Coordinates are [row, column] grid cells; timestamp is when the position was true (epoch seconds or ms).
// Returns '' on success, else a short problem message.
function showReply(text, scannedAt) {
  let data = text;
  try { data = JSON.parse(text); } catch { /* plain-text "(x, y)" */ }
  if (data && typeof data === 'object' && data.success === false) {
    return `Server error: ${data.error || data.message || 'localization failed'}`;
  }
  let row, col;
  const est = data && data.estimated_coord;
  if (Array.isArray(est) && est.length === 2 && est.every(Number.isFinite)) {
    [row, col] = est;
  } else {
    const xy = findXY(data);
    if (!xy) return 'Unexpected server reply';
    [col, row] = xy;
  }
  if (isBacktrack(row, col)) return '';   // a big jump backwards: treat as noise and keep what we have
  fix = { row, col, time: replyTime(data, scannedAt), spread: matchSpread(data, row, col),
    receivedAt: performance.now() };   // phone clock: the circle grows from here (server clock may differ)
  if (goalRoom) showRoute(data && data.path, (data && data.goal_coord) || GOAL);   // no destination: no route
  moveByMotion({ correction: true });   // new spot = fix + steps walked since then; the dot transitions there
  return '';
}

// A fix far behind the person -- more than BACKTRACK_M back along the way the route is heading -- is
// almost always Wi-Fi noise, so it's ignored. If several in a row say so, the person really did turn
// round, and the fix is accepted.
const BACKTRACK_M = 4;
const BACKTRACK_ACCEPT = 3;
let backtracks = 0;
function isBacktrack(row, col) {
  const g = guidance();
  if (!fix || !g.pos || !g.route || g.route.length < 2) return false;
  const P = [15.363, 13.22];                       // plan px per metre along x and y
  const m = (a, b) => [(b[0] - a[0]) / P[0], (b[1] - a[1]) / P[1]];   // a -> b in metres
  let ahead = null;                                 // the route's heading from here, as a unit vector
  for (const q of g.route) {
    const v = m(g.pos, q), len = Math.hypot(v[0], v[1]);
    if (len > 2) { ahead = [v[0] / len, v[1] / len]; break; }
  }
  if (!ahead) return false;
  const jump = m(g.pos, cellToPlan(row, col));
  const back = -(jump[0] * ahead[0] + jump[1] * ahead[1]);   // metres backwards along the route
  if (back > BACKTRACK_M && ++backtracks < BACKTRACK_ACCEPT) return true;
  backtracks = 0;
  return false;
}

// How sure the fix is, in metres: how far the KNN matches spread around the estimate (root-mean-square),
// at least ACCURACY_MIN_M. Close agreement = small circle; scattered matches = big one.
const ACCURACY_MIN_M = 1.5;
const ACCURACY_DEFAULT_M = 3;      // replies without matches
const ACCURACY_GROWTH_MPS = 0.3;   // the step-based estimate drifts; the circle grows until the next fix
function matchSpread(data, row, col) {
  const ms = (Array.isArray(data.matches) ? data.matches : [])
    .map(m => m && m.coord).filter(c => Array.isArray(c) && c.length === 2 && c.every(Number.isFinite));
  if (!ms.length) return ACCURACY_DEFAULT_M;
  const rms = Math.sqrt(ms.reduce((a, [r, c]) => a + (r - row) ** 2 + (c - col) ** 2, 0) / ms.length) * METERS_PER_CELL;
  return Math.max(ACCURACY_MIN_M, rms);
}

// Epoch ms the fix applies to, on the computer's clock: the reply's "timestamp" (seconds, ms, or an ISO
// date). Steps are timed by the phone's clock, so the two clocks are assumed to agree. No timestamp: our scan time.
function replyTime(data, scannedAt) {
  const t = data && typeof data === 'object' ? data.timestamp : undefined;
  let ms = NaN;
  if (typeof t === 'number') ms = t < 1e11 ? t * 1000 : t;
  else if (typeof t === 'string' && t.trim()) {
    const n = Number(t);
    ms = Number.isFinite(n) ? (n < 1e11 ? n * 1000 : n) : Date.parse(t);
  }
  return Number.isFinite(ms) ? ms : scannedAt;
}

// Where the person is now: the latest server fix + every step counted since its timestamp + how far into
// the current step they are (while walking, a fraction of a stride along the current heading, so the dot
// keeps moving between counted steps). Converted to grid cells and handed to the dot, which eases there.
async function moveByMotion({ correction = false } = {}) {
  if (!fix) return;
  const anchor = fix;
  let m = { east: 0, north: 0 };
  try { m = await WifiScan.getDisplacement({ since: anchor.time }); } catch { /* no motion data */ }
  if (anchor !== fix) return;   // a newer fix arrived meanwhile
  setAccuracy(anchor.spread + ACCURACY_GROWTH_MPS * Math.max(0, (performance.now() - anchor.receivedAt) / 1000));
  let { east, north } = m;
  // Walking or not, by the step sensor (only once it has seen steps; without step data the drift carries on).
  const still = m.stepPeriod > 0 && m.now - m.lastStep > 1.5 * m.stepPeriod;
  setStandingStill(still);
  setWalkingSpeed(!still && m.stepPeriod > 0 && m.stride > 0 ? m.stride / (m.stepPeriod / 1000) : null);   // drift matches it
  // Point the arrow the way the last few steps went (converted from compass to map directions).
  const re = m.recentEast || 0, rn = m.recentNorth || 0, bb = MAP_UP_BEARING * Math.PI / 180;
  setWalkingDirection(!still && Math.hypot(re, rn) > 0.3
    ? Math.atan2(re * Math.cos(bb) - rn * Math.sin(bb), rn * Math.cos(bb) + re * Math.sin(bb)) * 180 / Math.PI
    : null);
  setPhoneDirection(m.heading != null ? m.heading - MAP_UP_BEARING : null);   // used while not walking
  // Part of the current step (while walking), so the marker keeps moving between counted steps.
  let part = 0, h = 0;
  if (m.stepPeriod > 0 && m.heading != null) {
    const into = m.now - Math.max(m.lastStep, anchor.time);   // ms into the current step (after the fix)
    if (m.now - m.lastStep < 1.5 * m.stepPeriod && into > 0) part = Math.min(into / m.stepPeriod, 1) * m.stride;
    h = m.heading * Math.PI / 180;
  }
  // With a route: assume the person is following it -- the fix plus the distance walked since, along the
  // route (steps say how far, the route says which way).
  if (m.distance != null && placeAlongRoute(anchor.row, anchor.col, (m.distance + part) / METERS_PER_CELL, { correction })) return;
  east += part * Math.sin(h);
  north += part * Math.cos(h);
  const b = MAP_UP_BEARING * Math.PI / 180;
  const up = north * Math.cos(b) + east * Math.sin(b);      // metres toward the top of the grid
  const right = east * Math.cos(b) - north * Math.sin(b);   // metres toward the right of the grid
  placeDot(anchor.col + right / METERS_PER_CELL, anchor.row - up / METERS_PER_CELL, { correction });
}

function findXY(v) {
  const num = n => typeof n === 'number' || (typeof n === 'string' && n.trim() !== '' && !isNaN(n));
  if (typeof v === 'string') {
    const m = v.match(/(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/);
    return m ? [Number(m[1]), Number(m[2])] : null;
  }
  if (Array.isArray(v)) return v.length === 2 && v.every(num) ? v.map(Number) : null;
  if (v && typeof v === 'object') {
    if (num(v.x_value) && num(v.y_value)) return [Number(v.x_value), Number(v.y_value)];
    if (num(v.x) && num(v.y)) return [Number(v.x), Number(v.y)];
    for (const key of ['location', 'position', 'coord', 'coords', 'xy', 'point', 'result']) {
      const found = key in v && findXY(v[key]);
      if (found) return found;
    }
  }
  return null;
}

scanBtn.addEventListener('click', toggleTracking);
// ---- Inside / Outside slider. Inside: the map and tracking. Outside: live camera; the shutter sends a
// picture (with the destination and GPS), and the reply's position -- outdoor Google Maps coordinates --
// starts outside guidance toward the target (outside.js): "Turn left/right" / "Go straight" and distance.
const shutterBtn = document.getElementById('shutter');
const uploadBtn = document.getElementById('upload');
const pickInput = document.getElementById('pick-photo');
const modeButtons = document.querySelectorAll('#mode button');

async function setMode(mode) {
  const outside = mode === 'outside';
  document.body.classList.toggle('outside', outside);
  modeButtons.forEach(b => b.setAttribute('aria-checked', String(b.dataset.mode === mode)));
  scanBtn.hidden = outside;
  shutterBtn.hidden = !outside;
  uploadBtn.hidden = !outside;
  statusEl.textContent = '';
  stopOutside();
  if (outside) {
    if (tracking) stopTracking();
    WifiScan.startGps().catch(() => {});   // warm up GPS so pictures go out with a current fix
    try { await startCamera(); } catch { statusEl.textContent = 'Camera not available'; }
  } else {
    stopCamera();
    WifiScan.stopGps().catch(() => {});
  }
}
modeButtons.forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));

// Reads where we are from the reply and starts guiding toward the target. The position is
// "estimated_gps": {"latitude": .., "longitude": ..}; older replies put it in "estimated_coord" instead.
function useOutsideReply(body) {
  let data;
  try { data = JSON.parse(body); } catch { return 'Unexpected server reply'; }
  if (data.success === false) return `Server error: ${data.error || data.message || 'localization failed'}`;
  const gps = data.estimated_gps;
  if (gps && Number.isFinite(gps.latitude) && Number.isFinite(gps.longitude)) {
    setOutsidePosition([gps.latitude, gps.longitude]);
    return '';
  }
  const est = data.estimated_coord;
  if (!Array.isArray(est) || est.length !== 2 || !est.every(Number.isFinite)) return 'Unexpected server reply';
  setOutsidePosition(est);
  return '';
}

// The text fields sent with every picture: destination, heading and the phone's GPS.
async function pictureFields() {
  const [orientation, gps] = await Promise.all([
    WifiScan.getHeading().then(h => h.heading, () => null),
    WifiScan.getLocation().catch(() => null),
  ]);
  const num = (v, digits) => (v == null || !Number.isFinite(v) ? 'null' : v.toFixed(digits));
  return {
    goal: GOAL ? `[${GOAL.map(v => v.toFixed(1)).join(', ')}]` : 'null',
    orientation: num(orientation, 1),
    // GPS: degrees (WGS84), accuracy and altitude in metres, gps_time = when the fix was taken (epoch s)
    latitude: num(gps && gps.latitude, 7),
    longitude: num(gps && gps.longitude, 7),
    accuracy: num(gps && gps.accuracy, 1),
    altitude: num(gps && gps.altitude, 1),
    gps_time: gps ? (gps.time / 1000).toFixed(3) : 'null',
  };
}

async function sendPicture(send) {
  shutterBtn.disabled = uploadBtn.disabled = true;
  statusEl.textContent = 'Sending…';
  const { message, body } = await send(await pictureFields());
  shutterBtn.disabled = uploadBtn.disabled = false;
  statusEl.textContent = body ? useOutsideReply(body) : message;
}

shutterBtn.addEventListener('click', () => sendPicture(takeAndSend));
// Upload: pick a picture from the phone and send it the same way.
uploadBtn.addEventListener('click', () => pickInput.click());
pickInput.addEventListener('change', () => {
  const file = pickInput.files && pickInput.files[0];
  pickInput.value = '';   // so picking the same picture again still triggers
  if (file) sendPicture(fields => sendPickedImage(file, fields));
});


// Turn-by-turn (Inside): "Go straight" / "Turn left" / "Turn right" from the route ahead, a few times a
// second -- and arrival: close enough to the goal ring ends the trip.
const PX_PER_M = [15.363, 13.22];
const ARRIVED_SHOW_MS = 5000;   // how long "You have arrived" stays up
let arrivedUntil = 0;
setInterval(() => {
  const g = guidance();
  showInstruction(Date.now() < arrivedUntil ? 'You have arrived' : instruction(g.pos, g.route));
  const ring = goalPoint();
  if (goalRoom && g.pos && ring &&
      Math.hypot((g.pos[0] - ring[0]) / PX_PER_M[0], (g.pos[1] - ring[1]) / PX_PER_M[1]) < ARRIVED_M) arrive();
}, 250);

const destinationEl = document.getElementById('destination');

function setDestination(room) {
  stopVoice();
  setQuery('');   // any choice (list, map tap, voice) clears the search bar
  document.getElementById('room-search').blur();   // and ends the search: closes the keyboard
  goalRoom = room;
  GOAL = room ? room.goal : null;
  destinationEl.replaceChildren();
  if (!room) destinationEl.textContent = 'Select a destination';
  else if (room.restroom || room.kind) destinationEl.append(Object.assign(document.createElement('span'), { textContent: room.name }));
  else destinationEl.append('Room ', Object.assign(document.createElement('span'), { textContent: room.name }));
  highlightRoom(room);                 // the chosen room turns yellow on the map
  showRoute(null, GOAL);               // the old route was for the old destination; the next reply brings the new one
}

// Arrived: say so, drop the goal ring, route and highlight, and reset the destination for the next search.
function arrive() {
  arrivedUntil = Date.now() + ARRIVED_SHOW_MS;
  showInstruction('You have arrived');
  setDestination(null);
}

setDestination(goalRoom);
initSearch(room => { arrivedUntil = 0; setDestination(room); });   // a new pick replaces "You have arrived"
initVoice(setQuery);   // mic button: speech goes into the search bar

// Tapping a room on the map selects it, the same as picking it in the search.
function roomAt(x, y) {
  return ROOMS.find(r => {
    let inside = false;   // ray casting
    for (let i = 0, j = r.shape.length - 1; i < r.shape.length; j = i++) {
      const [xi, yi] = r.shape[i], [xj, yj] = r.shape[j];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  });
}
document.getElementById('map').addEventListener('plan-tap', e => {
  if (document.body.classList.contains('outside')) return;
  const room = roomAt(e.detail.x, e.detail.y);
  if (!room) return;
  arrivedUntil = 0;
  setDestination(room === goalRoom ? null : room);   // tapping the selected room again unselects it
});
// Don't keep scanning and sending while the app is in the background.
document.addEventListener('visibilitychange', () => {
  if (document.hidden && tracking) stopTracking();
  if (document.body.classList.contains('outside')) {   // release the camera and GPS in the background, resume after
    if (document.hidden) { stopCamera(); WifiScan.stopGps().catch(() => {}); }
    else { startCamera().catch(() => {}); WifiScan.startGps().catch(() => {}); }
  }
});
