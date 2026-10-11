// KNN reference nodes from the enriched map (message-3.txt): grid cell (r, c) -> position on floorplan.svg.
// Grid-to-plan mapping fitted by lining up the grid's walls with the plan's walls:
//   x = 15.363 * (c + 0.5) + -73.45,  y = 13.220 * (r + 0.5) + -158.50
export const NODES = [{"r":31,"c":22,"x":272.2,"y":257.9},{"r":31,"c":25,"x":318.3,"y":257.9},{"r":34,"c":14,"x":149.3,"y":297.6},{"r":34,"c":21,"x":256.9,"y":297.6},{"r":34,"c":27,"x":349.0,"y":297.6},{"r":34,"c":36,"x":487.3,"y":297.6},{"r":34,"c":40,"x":548.8,"y":297.6},{"r":34,"c":48,"x":671.7,"y":297.6},{"r":34,"c":56,"x":794.6,"y":297.6},{"r":34,"c":64,"x":917.5,"y":297.6},{"r":34,"c":73,"x":1055.7,"y":297.6},{"r":34,"c":76,"x":1101.8,"y":297.6},{"r":35,"c":23,"x":287.6,"y":310.8},{"r":38,"c":76,"x":1101.8,"y":350.5},{"r":40,"c":25,"x":318.3,"y":376.9},{"r":43,"c":75,"x":1086.5,"y":416.6},{"r":44,"c":83,"x":1209.4,"y":429.8},{"r":48,"c":27,"x":349.0,"y":482.7},{"r":50,"c":27,"x":349.0,"y":509.1},{"r":50,"c":91,"x":1332.3,"y":509.1},{"r":51,"c":27,"x":349.0,"y":522.3},{"r":53,"c":27,"x":349.0,"y":548.8},{"r":56,"c":8,"x":57.1,"y":588.4},{"r":56,"c":11,"x":103.2,"y":588.4},{"r":56,"c":17,"x":195.4,"y":588.4},{"r":56,"c":20,"x":241.5,"y":588.4},{"r":56,"c":22,"x":272.2,"y":588.4},{"r":56,"c":27,"x":349.0,"y":588.4},{"r":56,"c":32,"x":425.8,"y":588.4},{"r":56,"c":36,"x":487.3,"y":588.4},{"r":56,"c":42,"x":579.5,"y":588.4},{"r":56,"c":50,"x":702.4,"y":588.4},{"r":56,"c":58,"x":825.3,"y":588.4},{"r":56,"c":62,"x":886.7,"y":588.4},{"r":56,"c":70,"x":1009.6,"y":588.4},{"r":56,"c":75,"x":1086.5,"y":588.4},{"r":57,"c":79,"x":1147.9,"y":601.7},{"r":59,"c":91,"x":1332.3,"y":628.1}];

import { snapToWalkable, towardMiddle } from './walkable.js';

const GRID_TO_PLAN = [15.363, -73.45, 13.220, -158.50];   // ax, bx, ay, by
const SVG_NS = 'http://www.w3.org/2000/svg';
const layer = document.getElementById('nodes');

for (const n of NODES) {
  const dot = document.createElementNS(SVG_NS, 'circle');
  dot.setAttribute('cx', n.x);
  dot.setAttribute('cy', n.y);
  dot.setAttribute('class', 'node');
  layer.appendChild(dot);
}

// The chosen destination, filled yellow with its label redrawn on top (under the route and marker).
const roomFill = document.createElementNS(SVG_NS, 'polygon');
roomFill.setAttribute('class', 'room-selected');
const roomText = document.createElementNS(SVG_NS, 'text');
roomText.setAttribute('class', 'room-selected-label');
roomFill.style.display = roomText.style.display = 'none';
layer.append(roomFill, roomText);

export function highlightRoom(room) {
  const on = !!(room && room.shape);
  roomFill.style.display = roomText.style.display = on ? '' : 'none';
  if (!on) return;
  roomFill.setAttribute('points', room.shape.map(p => p.join(',')).join(' '));
  roomText.setAttribute('x', room.label.x);
  roomText.setAttribute('y', room.label.y);
  roomText.setAttribute('font-size', room.label.size);
  roomText.textContent = room.label.text;
}

// Route from the server: a line along `path` ([row, col] cells) and a ring at the goal; drawn under the dot.
const route = document.createElementNS(SVG_NS, 'polyline');
route.setAttribute('class', 'route');
const goal = document.createElementNS(SVG_NS, 'circle');
goal.setAttribute('class', 'goal');
layer.append(route, goal);
route.style.display = goal.style.display = 'none';

// Grid [row, col] -> plan point.
function toPlan(row, col) {
  const [ax, bx, ay, by] = GRID_TO_PLAN;
  return [ax * (col + 0.5) + bx, ay * (row + 0.5) + by];
}

const isCell = p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite);

// Draws the server's route as straight lines from point to point, and the goal ring. The part of the
// line the marker has passed over is removed as it goes (see trimRoute).
let routePts = [];
let fullRoute = [];   // the route as the server sent it (not trimmed), for placing positions along it
const PASS_DIST = 14;   // plan px: the marker counts as on the line within this distance

function drawRoute() {
  route.style.display = routePts.length >= 2 ? '' : 'none';
  route.setAttribute('points', routePts.map(p => p.join(',')).join(' '));
}

// Where the goal ring is (plan point), or null when there's no destination.
export function goalPoint() {
  return goal.style.display === 'none' ? null : [Number(goal.getAttribute('cx')), Number(goal.getAttribute('cy'))];
}

export function showRoute(path, goalCoord) {
  routePts = (Array.isArray(path) ? path.filter(isCell) : []).map(([r, c]) => toPlan(r, c));
  fullRoute = routePts.slice();
  drawRoute();
  goal.style.display = isCell(goalCoord) ? '' : 'none';
  if (isCell(goalCoord)) {
    const [x, y] = toPlan(...goalCoord);
    goal.setAttribute('cx', x);
    goal.setAttribute('cy', y);
  }
}

// Removes the stretch of route behind the marker at (x, y): finds the nearest point on the line and, if the
// marker is on the line there, cuts everything before it. Only ever trims forward.
function trimRoute(x, y) {
  if (routePts.length < 2) return;
  let best = null;
  for (let i = 0; i < routePts.length - 1; i++) {
    const [ax, ay] = routePts[i], [bx, by] = routePts[i + 1];
    const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / len2));
    const px = ax + dx * t, py = ay + dy * t, d = Math.hypot(x - px, y - py);
    if (!best || d < best.d) best = { d, i, p: [px, py] };
  }
  if (best.d > PASS_DIST || (best.i === 0 && Math.hypot(best.p[0] - routePts[0][0], best.p[1] - routePts[0][1]) < 1)) return;
  routePts = [best.p, ...routePts.slice(best.i + 1)];
  if (routePts.length === 2 && Math.hypot(routePts[1][0] - best.p[0], routePts[1][1] - best.p[1]) < PASS_DIST) routePts = [];
  drawRoute();
}

// Assume the person follows the route: put them `metres` along the server's route from grid cell (row, col)
// (with 1 m per cell, metres and cells are the same)
// (the fix, placed on the route). Returns false if there's no route, so the caller can fall back.
export function placeAlongRoute(row, col, metres, { correction = false } = {}) {
  motionSensors = true;
  const [ax, bx, ay, by] = GRID_TO_PLAN;
  const spot = alongRoute({ x: ax * (col + 0.5) + bx, y: ay * (row + 0.5) + by }, Math.max(metres, 0), fullRoute);
  followingRoute = !!spot;
  if (!spot) return false;
  placeDot(0, 0, { correction, plan: spot });   // plan point given directly
  return true;
}

// Grid (row, col) -> plan point (for comparing a server fix with where the marker is).
export function cellToPlan(row, col) {
  const [ax, bx, ay, by] = GRID_TO_PLAN;
  return [ax * (col + 0.5) + bx, ay * (row + 0.5) + by];
}

// The person: a UCF gold triangle at their position, its tip pointing the way they're moving.
// Two kinds of movement:
//  - walking (the motion sensors, ~10 updates/s): followed closely, lightly eased so it's continuous;
//  - corrections (a new server fix): the marker transitions from where it is to the new spot over
//    CORRECTION_MS, while walking movement carries on underneath, so it never skips;
//  - drift while waiting: after each correction it keeps moving slowly the way that correction pointed
//    (the vector from where it was to the new spot), steered along the hallway and toward its middle,
//    until the next fix arrives.
// Target spots are kept in walkable space (never in a classroom or outside the building).
const accuracy = document.createElementNS(SVG_NS, 'ellipse');   // faint gold "how sure" circle
accuracy.setAttribute('class', 'accuracy');
accuracy.style.display = 'none';
const ACCURACY_EASE_MS = 400;
let accuracyM = null, accuracyTarget = null;

const located = document.createElementNS(SVG_NS, 'polygon');
located.setAttribute('class', 'located');
located.setAttribute('points', '0,-20 13,13 0,7 -13,13');   // tip up (toward the top of the map), notched base
located.style.display = 'none';

const WALK_EASE_MS = 120;     // smooths the ~10 Hz walking updates
const CORRECTION_MS = 3000;   // how long a server correction takes to play out
const DRIFT_MAX_MS = 6000;    // stop drifting if no new fix arrives for this long
const CENTER_PULL = 0.015;    // plan px per ms toward the hallway's middle line (15 px/s at a wall)
const DEFAULT_WALK_MPS = 1.3; // drift speed until the step sensor has measured the person's own pace
const PX_PER_M = [GRID_TO_PLAN[0], GRID_TO_PLAN[2]];   // plan px per metre along x and y (1 m per cell)
let walkSpeed = null;         // the person's walking speed (m/s) from the step sensor
let followingRoute = false;   // true while the position comes from "fix + distance walked along the route"
let motionSensors = false;    // the phone reports steps (then the drift isn't needed along a route)
const TURN_EASE_MS = 150;     // smooths turning

let target = null;            // plan point where the person is now (walking estimate)
let walk = null;              // eased walking position
let offset = { x: 0, y: 0 };  // what's left of the last correction, fading to zero
let correctionStart = 0;
let drift = { x: 0, y: 0 };   // plan px per ms, in the direction of the last correction
let drifted = { x: 0, y: 0 }; // how far the drift has carried the marker since the last correction
let drawnAt = null;           // where the marker is drawn (plan point), for directions
let standingStill = false;    // from the step sensor: no drift while the person isn't walking
let walkingAngle = null;      // from the step sensor: direction of the last few steps (map degrees), if walking
let phoneAngle = null;        // where the phone faces (compass, map degrees), used when not walking
let angle = 0, targetAngle = 0;   // degrees clockwise from the top of the map
let lastDrawn = null;                // previous frame's position, to see which way the marker moves
let vel = { x: 0, y: 0 };            // smoothed movement, plan px per ms
const MIN_TURN_SPEED = 0.004;        // plan px per ms (~4 px/s): slower than this, keep the last direction
let frame = 0, lastFrame = 0;

const smoothstep = k => k * k * (3 - 2 * k);

// Moves the drift on by dt ms from base point p: along the hallway (the part of the drift vector that
// runs with the corridor) at the person's walking speed, plus a pull toward the hallway's middle line.
// Where you end up walking `metres` along the route from plan point p (starting at the nearest point on
// the line), or null if there's no route. Stops at the end of the route.
function alongRoute(p, metres, pts = routePts) {
  if (pts.length < 2) return null;
  let best = null;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
    const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((p.x - ax) * dx + (p.y - ay) * dy) / len2));
    const qx = ax + dx * t, qy = ay + dy * t, d = Math.hypot(p.x - qx, p.y - qy);
    if (!best || d < best.d) best = { d, i, q: [qx, qy] };
  }
  let [x, y] = best.q, left = metres;
  for (let i = best.i + 1; i < pts.length && left > 0; i++) {
    const [nx, ny] = pts[i];
    const seg = Math.hypot((nx - x) / PX_PER_M[0], (ny - y) / PX_PER_M[1]);
    if (seg >= left) { const t = left / seg; return [x + (nx - x) * t, y + (ny - y) * t]; }
    left -= seg;
    [x, y] = [nx, ny];
  }
  return [x, y];
}

// Moves the drift on by dt ms from base point p. When the steps already place the person along the route
// (see placeAlongRoute), there's nothing to add. Phones without a step sensor: assume the person follows
// the route at a normal walking pace. No route: keep going the way the last correction pointed, steered
// along the hallway and toward its middle.
function advanceDrift(p, dt) {
  if (followingRoute) return;
  const ahead = motionSensors ? null : alongRoute(p, (walkSpeed || DEFAULT_WALK_MPS) * dt / 1000);
  if (ahead) {
    drifted.x += ahead[0] - p.x;
    drifted.y += ahead[1] - p.y;
    return;
  }
  if (!drift.x && !drift.y) return;
  const [gx, gy] = towardMiddle(p.x, p.y);
  const g = Math.hypot(gx, gy);
  let vx = drift.x, vy = drift.y;
  if (g > 0.3) {   // in a corridor: keep only the along-the-hallway part, at the same speed
    const nx = gx / g, ny = gy / g, across = vx * nx + vy * ny;
    vx -= across * nx;
    vy -= across * ny;
  }
  // Same speed as the person walks: convert m/s to plan px/ms along this direction.
  const len = Math.hypot(vx, vy);
  if (len > 1e-9) {
    const ux = vx / len, uy = vy / len;
    const pxPerMs = (walkSpeed || DEFAULT_WALK_MPS) / 1000 / Math.hypot(ux / PX_PER_M[0], uy / PX_PER_M[1]);
    vx = ux * pxPerMs;
    vy = uy * pxPerMs;
  }
  drifted.x += (vx + gx * CENTER_PULL) * dt;
  drifted.y += (vy + gy * CENTER_PULL) * dt;
}

function tick(now) {
  const dt = lastFrame ? Math.min(now - lastFrame, 100) : 16;
  lastFrame = now;
  const k = 1 - Math.exp(-dt / WALK_EASE_MS);
  walk = { x: walk.x + (target.x - walk.x) * k, y: walk.y + (target.y - walk.y) * k };
  const turn = ((targetAngle - angle + 540) % 360) - 180;   // shortest way round
  angle += turn * (1 - Math.exp(-dt / TURN_EASE_MS));
  const left = 1 - smoothstep(Math.min((now - correctionStart) / CORRECTION_MS, 1));
  if (now - correctionStart < DRIFT_MAX_MS && !standingStill) {
    advanceDrift({ x: walk.x + offset.x * left + drifted.x, y: walk.y + offset.y * left + drifted.y }, dt);
  }
  const x = walk.x + offset.x * left + drifted.x, y = walk.y + offset.y * left + drifted.y;
  // Point the way it's moving: walking + drift (smoothed). The correction glide is left out, so a pull
  // back toward a server fix doesn't turn the marker round.
  const travel = { x: walk.x + drifted.x, y: walk.y + drifted.y };
  if (lastDrawn) {
    const a = 1 - Math.exp(-dt / 600);
    vel = { x: vel.x + ((travel.x - lastDrawn.x) / dt - vel.x) * a, y: vel.y + ((travel.y - lastDrawn.y) / dt - vel.y) * a };
    // Which way it points: walking -> the way the steps go; not moving -> where the phone faces;
    // no compass either -> the marker's own movement on the map.
    if (walkingAngle != null) targetAngle = walkingAngle;
    else if (phoneAngle != null) targetAngle = phoneAngle;
    else if (Math.hypot(vel.x, vel.y) > MIN_TURN_SPEED) targetAngle = (Math.atan2(vel.x, -vel.y) * 180 / Math.PI + 360) % 360;
  }
  lastDrawn = travel;
  drawnAt = [x, y];
  trimRoute(x, y);
  located.setAttribute('transform', `translate(${x.toFixed(2)} ${y.toFixed(2)}) rotate(${angle.toFixed(1)})`);
  if (accuracyTarget != null) {
    accuracyM = accuracyM == null ? accuracyTarget : accuracyM + (accuracyTarget - accuracyM) * (1 - Math.exp(-dt / ACCURACY_EASE_MS));
    accuracy.setAttribute('cx', x.toFixed(2));
    accuracy.setAttribute('cy', y.toFixed(2));
    accuracy.setAttribute('rx', (accuracyM * PX_PER_M[0]).toFixed(1));   // metres -> plan px (x and y differ a little)
    accuracy.setAttribute('ry', (accuracyM * PX_PER_M[1]).toFixed(1));
    accuracy.style.display = '';
  }
  const drifting = (drift.x || drift.y || routePts.length >= 2) && now - correctionStart < DRIFT_MAX_MS && !standingStill;
  const sizing = accuracyTarget != null && Math.abs(accuracyTarget - accuracyM) > 0.02;
  const moving = left > 0 || drifting || sizing || Math.hypot(target.x - walk.x, target.y - walk.y) > 0.2 || Math.abs(turn) > 0.5;
  if (moving) frame = requestAnimationFrame(tick);
  else { frame = 0; lastFrame = 0; lastDrawn = null; vel = { x: 0, y: 0 }; }
}

function drawnNow() {
  const left = 1 - smoothstep(Math.min((performance.now() - correctionStart) / CORRECTION_MS, 1));
  return { x: walk.x + offset.x * left + drifted.x, y: walk.y + offset.y * left + drifted.y };
}

function wake() {
  if (walk && !frame) frame = requestAnimationFrame(tick);
}

// How sure the position is, in metres: the radius of the faint gold circle around the marker.
export function setAccuracy(metres) {
  accuracyTarget = Number.isFinite(metres) ? Math.min(Math.max(metres, 0.5), 25) : null;
  if (accuracyTarget == null) accuracy.style.display = 'none';
  wake();
}

// The step sensor's view: whether the person has stopped, and (while walking) which way their recent
// steps went, in degrees clockwise from the top of the map (null if unknown).
export function setStandingStill(still) {
  standingStill = still;
}

// The person's walking speed in m/s from the step sensor (null if not measured): the drift matches it.
export function setWalkingSpeed(mps) {
  walkSpeed = Number.isFinite(mps) ? Math.min(Math.max(mps, 0.3), 2.5) : null;
}

export function setWalkingDirection(deg) {
  walkingAngle = deg == null ? null : ((deg % 360) + 360) % 360;
  if (walkingAngle != null) { targetAngle = walkingAngle; wake(); }
}

// Where the phone is facing (compass), in degrees clockwise from the top of the map; null if unknown.
export function setPhoneDirection(deg) {
  phoneAngle = deg == null ? null : ((deg % 360) + 360) % 360;
  if (walkingAngle == null && phoneAngle != null) { targetAngle = phoneAngle; wake(); }
}

// Grid (x = column, y = row) -> plan point in walkable space. correction: true for a new server fix.
export function placeDot(x, y, { correction = false, plan = null } = {}) {
  const [ax, bx, ay, by] = GRID_TO_PLAN;
  const [px, py] = snapToWalkable(...(plan || [ax * (x + 0.5) + bx, ay * (y + 0.5) + by]));
  const next = { x: px, y: py };
  if (!walk) {                       // first position: appear there directly
    walk = { ...next };
  } else if (correction) {           // start from wherever the marker is drawn now
    const now = performance.now();
    const from = drawnNow();
    // The walking position jumps to the new fix here (the offset hides that on screen); shift the
    // direction tracker by the same jump so it isn't read as movement.
    if (lastDrawn) lastDrawn = { x: lastDrawn.x + next.x - walk.x - drifted.x, y: lastDrawn.y + next.y - walk.y - drifted.y };
    walk = { ...next };
    offset = { x: from.x - next.x, y: from.y - next.y };
    // Keep moving the same way while waiting: the direction of the move to the new spot (the speed is the
    // person's walking speed, applied in advanceDrift).
    drift = correctionStart && Math.hypot(offset.x, offset.y) > 0.5 ? { x: -offset.x, y: -offset.y } : { x: 0, y: 0 };
    drifted = { x: 0, y: 0 };   // already included in `from`, so the offset carries it
    correctionStart = now;
  } else if (!correctionStart) {
    correctionStart = performance.now();
  }
  target = next;
  located.style.display = '';
  layer.appendChild(accuracy);       // accuracy circle, then the triangle on top of it
  layer.appendChild(located);
  wake();
}

// For the turn-by-turn instruction: marker position, the way it faces (degrees clockwise from the map's
// top), and the route still ahead (plan points).
export function guidance() {
  return { pos: drawnAt, facing: walk ? ((targetAngle % 360) + 360) % 360 : null, route: routePts };
}
