import { playInstruction } from './audio.js';

// Turn-by-turn instruction from the route still ahead: one of "Go straight", "Turn left", "Turn right"
// (main.js shows "You have arrived" for a few seconds at the destination).
// Worked out from the path alone (the remaining route line, already trimmed behind the marker): when the
// person gets within TURN_SOON_M of a corner, it's that corner's turn; otherwise "Go straight".
const PX_PER_M = [15.363, 13.22];   // plan px per metre (1 m per grid cell) along x and y
const TURN_SOON_M = 4;              // a corner closer than this: say the turn now
const ARRIVED_M = 2;                // this close to the end: no instruction

const el = document.getElementById('directions');
const metres = (a, b) => Math.hypot((b[0] - a[0]) / PX_PER_M[0], (b[1] - a[1]) / PX_PER_M[1]);
const angleOf = (a, b) => (Math.atan2((b[0] - a[0]) / PX_PER_M[0], -(b[1] - a[1]) / PX_PER_M[1]) * 180 / Math.PI + 360) % 360;
const signedTurn = (from, to) => ((to - from + 540) % 360) - 180;   // + = right (clockwise), - = left

const NOW_M = 3;       // the path's direction right now: from here to 3 m along
const CHORD_M = 8;     // the path's direction further on: from a spot to 8 m beyond it
const BEND_DEG = 50;   // the path turning at least this much counts as a turn (gradual bends included)

// Point `d` metres along the polyline pts (clamped to its end).
function pointAt(pts, d) {
  for (let i = 1; i < pts.length; i++) {
    const seg = metres(pts[i - 1], pts[i]);
    if (d <= seg) {
      const t = seg ? d / seg : 0;
      return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t];
    }
    d -= seg;
  }
  return pts[pts.length - 1];
}

// From the path alone: if the path a little way ahead (starting within TURN_SOON_M) heads BEND_DEG or more
// away from the way it goes right now -- one sharp corner or several small bends -- it's that turn;
// otherwise go straight. Once round the corner, "right now" is the new direction, so it's straight again.
export function instruction(pos, route) {
  if (!pos || !Array.isArray(route) || route.length < 1) return '';
  // Measure along the path itself (route[0] is the point on the line nearest the marker); the marker may sit
  // a little off the line, and starting from it would add a false bend.
  const pts = route.length >= 2 ? route : [pos, ...route];
  let total = 0;
  for (let i = 1; i < pts.length; i++) total += metres(pts[i - 1], pts[i]);
  if (total < ARRIVED_M) return '';
  const now = angleOf(pointAt(pts, 0), pointAt(pts, NOW_M));
  for (let d = 0.5; d <= TURN_SOON_M && d + 1 <= total; d += 0.5) {
    const turn = signedTurn(now, angleOf(pointAt(pts, d), pointAt(pts, Math.min(d + CHORD_M, total))));
    if (Math.abs(turn) >= BEND_DEG) return turn > 0 ? 'Turn right' : 'Turn left';
  }
  return 'Go straight';
}

// Shows the instruction; whenever it changes to a new one, one of its three clips is spoken.
export function showInstruction(text) {
  if (el.textContent === text) return;
  el.textContent = text;
  if (text) playInstruction(text);
}
