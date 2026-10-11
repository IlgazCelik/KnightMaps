import { WifiScan } from './wifi.js';
import { playInstruction } from './audio.js';

// Outside guidance: a straight line from the person's position (from the server, Google Maps coordinates)
// to the target; the direction of that line, compared with where the phone points, says which way to go.
export const TARGET = [28.6013132, -81.1986156];   // latitude, longitude
const STRAIGHT_DEG = 20;   // target within +/-20 deg of where the phone points: go straight
const STRAIGHT_EXIT_DEG = 30;   // ...and stay "Go straight" until it's more than 30 deg off (no flicker at 20)
const HEADING_SMOOTH_MS = 1000; // average the compass over about this long
const ARRIVED_M = 10;      // GPS-level accuracy
// "Go straight" only along the building grid: the buildings run at 134 deg true (Engineering I's outline from
// OpenStreetMap), so their walls line up at 44/134/224/314. A line to the set point within AXIS_TOL_DEG of one of those is
// straight; a diagonal one is "Turn left"/"Turn right", by which way it leans off the grid.
const BUILDING_DEG = 134;
const AXIS_TOL_DEG = 15;
const STRAIGHT_REPEAT_MS = 5000;   // while going straight, say it again this often
const UPDATE_MS = 300;
// The phone's direction reading in Outside mode came out pointing the opposite way (180 deg off) in field
// testing, which reversed the directions; this turns it round so the guidance follows the line from the
// server's position to the set point.
const HEADING_CORRECTION_DEG = 180;

const box = document.getElementById('camera-info');
let here = null, timer = 0, shown = '', lastSpoken = 0;
let smooth = null, lastReading = 0;     // smoothed heading as a unit vector [east, north]

const rad = d => d * Math.PI / 180;

// Great-circle distance (m) and initial bearing (degrees from true north) from a to b, both [lat, lng].
function lineTo(a, b) {
  const [la1, lo1, la2, lo2] = [rad(a[0]), rad(a[1]), rad(b[0]), rad(b[1])];
  const h = Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2;
  const metres = 2 * 6371000 * Math.asin(Math.sqrt(h));
  const y = Math.sin(lo2 - lo1) * Math.cos(la2);
  const x = Math.cos(la1) * Math.sin(la2) - Math.sin(la1) * Math.cos(la2) * Math.cos(lo2 - lo1);
  return { metres, bearing: (Math.atan2(y, x) * 180 / Math.PI + 360) % 360 };
}

// The server's (x, y) as [lat, lng]: whichever order puts it nearer the target.
function asLatLng(p) {
  const swapped = [p[1], p[0]];
  const ok = q => Math.abs(q[0]) <= 90 && Math.abs(q[1]) <= 180;
  if (!ok(swapped)) return p;
  if (!ok(p)) return swapped;
  return lineTo(p, TARGET).metres <= lineTo(swapped, TARGET).metres ? p : swapped;
}

// Shows the instruction (no holding: it changes as soon as the direction says so); the clip plays on change.
// "Go straight" is spoken again every STRAIGHT_REPEAT_MS while it stays up.
function show(instruction, detail) {
  const now = Date.now();
  if (instruction !== shown || (shown === 'Go straight' && now - lastSpoken >= STRAIGHT_REPEAT_MS)) {
    shown = instruction;
    lastSpoken = now;
    playInstruction(instruction);
  }
  box.replaceChildren(
    Object.assign(document.createElement('div'), { className: 'instruction', textContent: shown }),
    Object.assign(document.createElement('div'), { textContent: detail }),
  );
  box.hidden = false;
}

// Averages compass readings (as unit vectors, so 359 and 1 average to 0), over about HEADING_SMOOTH_MS.
function smoothHeading(deg) {
  const now = Date.now(), v = [Math.sin(rad(deg)), Math.cos(rad(deg))];
  const a = smooth ? 1 - Math.exp(-(now - lastReading) / HEADING_SMOOTH_MS) : 1;
  smooth = smooth ? [smooth[0] + (v[0] - smooth[0]) * a, smooth[1] + (v[1] - smooth[1]) * a] : v;
  lastReading = now;
  return (Math.atan2(smooth[0], smooth[1]) * 180 / Math.PI + 360) % 360;
}

async function update() {
  if (!here) return;
  const { metres, bearing } = lineTo(here, TARGET);
  if (metres < ARRIVED_M) return show('You have arrived', '');
  const raw = await WifiScan.getHeading().then(h => h.heading, () => null);
  const heading = raw == null ? null : smoothHeading((raw + HEADING_CORRECTION_DEG) % 360);
  const away = `${metres < 1000 ? Math.round(metres) + ' m' : (metres / 1000).toFixed(1) + ' km'}`;
  if (heading == null) return show('Go straight', `${away} — hold the phone flat to aim`);
  const turn = ((bearing - heading + 540) % 360) - 180;   // + = target is to the right
  // Where the phone points (camera direction when held up) vs the line to the target.
  const limit = shown === 'Go straight' ? STRAIGHT_EXIT_DEG : STRAIGHT_DEG;
  if (Math.abs(turn) > limit) return show(turn > 0 ? 'Turn right' : 'Turn left', away);
  // Facing the set point: straight only if the line runs along the building grid, else the way it leans.
  const offGrid = ((bearing - BUILDING_DEG) % 90 + 90 + 45) % 90 - 45;   // -45..45, + = clockwise of the grid
  show(Math.abs(offGrid) <= AXIS_TOL_DEG ? 'Go straight' : offGrid > 0 ? 'Turn right' : 'Turn left', away);
}

// A new position from the server ([x, y] in Google Maps coordinates).
export function setOutsidePosition(xy) {
  here = asLatLng(xy);
  update();
  if (!timer) timer = setInterval(update, UPDATE_MS);
}

export function stopOutside() {
  clearInterval(timer);
  timer = 0;
  here = null;
  shown = '';
  lastSpoken = 0;
  smooth = null;
  box.hidden = true;
}
