(async () => {
/*
 * Mission templates: chase, defend, race.
 *
 * Each template is put through both endings - the one that pays and the one that puts the
 * mission back on the map - and every ending is reached by the simulation rather than by
 * calling the manager's own completion methods. Following the smoke probe's rule, the
 * commute is teleported and the decisive act is driven: the quarry is killed with aimed
 * gunfire, the siege is abandoned by running out of the zone under sprint input, the race
 * is scratched by pressing F to step off the boat and won by throttling through each buoy.
 */
const g = window.game, E = g.engine;
const log = []; const T0 = performance.now();
const BUDGET = 480000;
const ok = (n, c, x) => log.push({ step: n, pass: !!c, ...(x !== undefined ? { info: String(x) } : {}) });
let simT = 0; E.fixedCallbacks.push((dt) => { simT += dt; });
const wait = async (sec) => { const t = simT + sec;
  while (simT < t && performance.now() - T0 < BUDGET) await new Promise(r => requestAnimationFrame(r)); };
const out = () => performance.now() - T0 > BUDGET;
const here = () => { const c = g.traffic.playerVehicle;
  if (!c) return g.player.position;
  const t = c.body.translation(); return { x: t.x, y: t.y, z: t.z }; };
const dist2 = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
const down = (code) => window.dispatchEvent(new KeyboardEvent('keydown', { code, bubbles: true }));
const up = (code) => window.dispatchEvent(new KeyboardEvent('keyup', { code, bubbles: true }));
const tap = async (c) => { down(c); await wait(0.2); up(c); await wait(0.4); };
const hold = async (c, s) => { down(c); await wait(s); up(c); await wait(0.2); };
const wrap = (a) => { while (a > Math.PI) a -= Math.PI * 2; while (a < -Math.PI) a += Math.PI * 2; return a; };

/*
 * Mouse look only reaches the camera while the pointer is locked, and headless Chromium
 * has no pointer lock. Flipping the flag is the harness equivalent of the synthetic
 * KeyboardEvents above: the deltas still travel the real listener -> CameraRig.look path,
 * which is what the aiming assertions below are actually testing.
 */
const wasLocked = g.input.mouse.locked;
g.input.mouse.locked = true;
const SENS = g.cameraRig.sensitivity;
const mouse = (dx, dy) => window.dispatchEvent(
  new MouseEvent('mousemove', { bubbles: true, movementX: dx, movementY: dy }));
const camFwd = () => {
  const e = g.cameraRig.camera.matrixWorld.elements;
  const l = Math.hypot(e[8], e[9], e[10]) || 1;
  return { x: -e[8] / l, y: -e[9] / l, z: -e[10] / l };
};
/*
 * Angular error from the camera's aim line to a world point.
 *
 * Measured from the camera boom's pivot, NOT from the player's chest. `WeaponSystem._fire`
 * slides the ray origin back down the boom until it is level with the player, and the boom
 * passes through the pivot, so that slide lands the origin at `player.y + 1.55` - fifteen
 * centimetres above the chest. Measuring from the chest sends every round about a
 * hand's width high, which is exactly enough to skim the roof of a sports car at twelve
 * metres and hit a building a hundred metres behind it.
 */
const BOOM_HEIGHT = 1.55;
const aimError = (t) => {
  const p = g.player.position;
  const dx = t.x - p.x, dy = t.y - (p.y + BOOM_HEIGHT), dz = t.z - p.z;
  const len = Math.hypot(dx, dy, dz) || 1;
  const f = camFwd();
  const clamp1 = (v) => Math.max(-1, Math.min(1, v));
  return {
    yaw: wrap(Math.atan2(dx, dz) - Math.atan2(f.x, f.z)),
    pitch: Math.asin(clamp1(dy / len)) - Math.asin(clamp1(f.y)),
  };
};
/** Closed-loop aim: nudge the mouse, re-measure, repeat. Returns the residual error. */
const aimAt = async (t, iters = 6) => {
  let e = aimError(t);
  for (let i = 0; i < iters && !out(); i++) {
    if (Math.abs(e.yaw) < 0.012 && Math.abs(e.pitch) < 0.012) break;
    mouse(-e.yaw / SENS * 0.85, -e.pitch / SENS * 0.85);
    await wait(0.09);
    e = aimError(t);
  }
  return e;
};
const trigger = (downNow) => window.dispatchEvent(
  new MouseEvent(downNow ? 'mousedown' : 'mouseup', { button: 0, bubbles: true }));
const groundY = (x, z) => Math.max(g.island.heightAt(x, z), g.ocean.level) + 1.2;

/**
 * Stand in the runner's path and hold the trigger as it comes at you.
 *
 * Shooting a car crossing at 26 m/s is hopeless at 12 headless fps: one frame of aim
 * latency is two metres of lead, which at ten metres is a fifth of a radian. Head-on the
 * bearing barely moves, so the same aim loop lands rounds - and standing in front of a
 * fleeing car is how a player does this anyway.
 *
 * Fire is broken into short bursts. Every round kicks the camera up by the rifle's recoil
 * (0.028 rad), which at 9 shots a second outruns a once-per-frame correction; re-settling
 * between bursts keeps the accumulated kick to a fraction of the car's angular height.
 */
const interceptAndFire = async (v, bursts) => {
  const t = v.body.translation();
  const h = v.heading;
  const fx = Math.sin(h), fz = Math.cos(h);
  const ahead = Math.abs(v.speed) > 3 ? 30 : 11;
  const px = t.x + fx * ahead + fz * 3, pz = t.z + fz * ahead - fx * 3;
  put(px, groundY(px, pz), pz);
  await wait(0.35);
  // Aim low on the body rather than at the roof line: the chassis collider is the whole
  // hull, so a round into the door counts and a round over the roof does not.
  const mark = (q) => ({ x: q.x, y: q.y + 0.25, z: q.z });
  for (let k = 0; k < bursts && v.health > 0 && !out(); k++) {
    await aimAt(mark(v.body.translation()), 4);
    trigger(true);
    const end = simT + 0.22;
    while (simT < end && v.health > 0 && !out()) {
      const e = aimError(mark(v.body.translation()));
      mouse(-e.yaw / SENS, -e.pitch / SENS);
      await new Promise((r) => requestAnimationFrame(r));
    }
    trigger(false);
    await wait(0.06);
  }
  trigger(false);
  await wait(0.15);
};

// Payouts, captured at the source so a ghost bonus is visible separately from the reward.
const rewards = [];
const payHook = g.missions.onReward;
g.missions.onReward = (amount) => { rewards.push(amount); payHook?.(amount); };

/*
 * The reason string, captured at the source. Sampling the gap on a timer cannot prove
 * WHICH rule fired - a chase that ran out of clock and a chase that was outrun both end
 * with `active === null` - so the failure tests assert on the reason the manager gave.
 */
let lastFail = null, failGap = null;
const failHook = g.missions.fail.bind(g.missions);
g.missions.fail = (reason) => {
  lastFail = reason;
  /*
   * The gap as the manager itself saw it, taken before `fail` tears the quarry down.
   * Polling it from the flee loop instead reports whatever the last sample caught, which
   * is always a metre or two short of the ring that actually fired - the run that proved
   * this read 339 m against a 340 m ring - and that reads as if the rule triggered early.
   */
  const q = g.missions.chase && g.missions.chase.vehicle.position;
  if (q) failGap = dist2(here(), q);
  return failHook(reason);
};

const byId = (id) => g.missions.missions.find((m) => m.id === id);
const reset = async () => {
  if (g.missions.active) g.missions.fail('probe reset');
  lastFail = null; failGap = null;
  g.wanted.clear();
  await wait(0.3);
};
const put = (x, y, z) => g.player.body.setTranslation({ x, y, z }, true);
/**
 * Sprint on foot towards a world point, re-aiming as we go, until `stopWhen` or the cap.
 *
 * Movement is camera-relative, so steering the player means turning the camera - the same
 * mousemove path the aiming loop uses. Blind "hold W and hope" runs into the first wall.
 */
const sprintTowards = async (aimPoint, stopWhen, maxSec) => {
  down('ShiftLeft'); down('KeyW');
  const end = simT + maxSec;
  while (simT < end && !stopWhen() && !out()) {
    const p = g.player.position;
    await aimAt({ x: aimPoint.x, y: p.y + 1.4, z: aimPoint.z }, 3);
    await wait(0.7);
  }
  up('KeyW'); up('ShiftLeft');
  await wait(0.2);
};

/** Face a craft at a point and drop it `back` metres short of it, motionless. */
const lineUp = (craft, from, to, back, y) => {
  let vx = from.x - to.x, vz = from.z - to.z;
  const l = Math.hypot(vx, vz) || 1;
  vx /= l; vz /= l;
  const sx = to.x + vx * back, sz = to.z + vz * back;
  const yaw = Math.atan2(to.x - sx, to.z - sz);
  craft.body.setTranslation({ x: sx, y, z: sz }, true);
  craft.body.setRotation({ x: 0, y: Math.sin(yaw / 2), z: 0, w: Math.cos(yaw / 2) }, true);
  craft.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
  craft.body.setAngvel({ x: 0, y: 0, z: 0 }, true);
};

const totals = { missions: g.missions.missions.length };
ok('mission count grew to fourteen', g.missions.missions.length === 14, `${g.missions.missions.length} missions`);
const kinds = {};
for (const m of g.missions.missions) for (const o of m.objectives) kinds[o.type] = (kinds[o.type] ?? 0) + 1;
ok('all three templates are authored', kinds.chase >= 2 && kinds.defend >= 2 && kinds.race >= 2,
  `chase ${kinds.chase}, defend ${kinds.defend}, race ${kinds.race}`);

/* ===================================================================== chase */
/*
 * Fail first, then complete the same mission - which also proves the failure really did
 * return it to the pool, because a mission that never came back cannot be started again.
 */
const chaseM = byId('hot-pursuit');
const chaseObj = chaseM.objectives[0];

await reset();
put(chaseM.start.x, 1.2, chaseM.start.z);
await wait(1.2);
ok('chase mission triggers by walking into its marker', g.missions.active === chaseM,
  g.missions.active ? g.missions.active.name : 'none');

// The quarry may need a couple of tries to find clear road; the retry path is what stops a
// failed spawn silently paying out.
let spawnGuard = 0;
while (!g.missions.chase && spawnGuard++ < 30 && !out()) await wait(0.4);
ok('chase spawns a quarry on the road graph', !!g.missions.chase,
  g.missions.chase ? `${g.missions.chase.vehicle.spec.label} at ${Math.round(dist2(here(), g.missions.chase.vehicle.position))}m` : 'no spawn');

const quarry = g.missions.chase && g.missions.chase.vehicle;
const d0 = quarry ? dist2(here(), quarry.position) : 0;
let dMax = d0;
/*
 * A route out, as a list of road nodes leading away from `anchor`.
 *
 * Beelining at a distant point does not work: the first building broadside wedges the car
 * and it never recovers (measured 14 m of travel in fifty seconds of held throttle). The
 * road graph already knows which way is drivable, so the retreat follows an A* path
 * through it - the same `findPath` the police use to close in.
 */
const net = g.city.network;
const routeAway = (from, anchor) => {
  const start = net.nearestNode(from.x, from.z);
  let goal = null, far = -Infinity;
  for (const n of net.nodes) {
    if (Math.hypot(n.x - from.x, n.z - from.z) > 700) continue;
    const away = Math.hypot(n.x - anchor.x, n.z - anchor.z);
    if (away > far) { far = away; goal = n; }
  }
  const ids = goal ? net.findPath(start.id, goal.id) : null;
  return (ids ?? [start.id]).map((id) => net.nodes[id]);
};

/*
 * Give up and drive off. Fleeing on foot measured under 2 m/s net once walls and junctions
 * are counted - not enough to clear a 340 m ring inside the mission clock, so the test
 * came down to whether the autopilot's coin flips happened to carry the runner far enough.
 * A car on a road route makes the escape rule provable in half a minute of throttle.
 */
const fleeCar = g.starterCar;
/*
 * On a lane, pointing along it. Dropped three metres to one side of the player instead,
 * the car starts half on the pavement facing a wall and fifty seconds of held throttle
 * moves it forty-seven metres - the smoke test's own commute teleport does the same lane
 * lookup for the same reason.
 */
const lane0 = net.nearestOnRoad(g.player.position.x, g.player.position.z);
const spot0 = lane0 ? net.lanePointOnEdge(lane0.edge, lane0.t, true, 0) : g.player.position;
fleeCar.body.setTranslation({ x: spot0.x, y: 1.4, z: spot0.z }, true);
if (spot0.heading !== undefined) {
  fleeCar.body.setRotation(
    { x: 0, y: Math.sin(spot0.heading / 2), z: 0, w: Math.cos(spot0.heading / 2) }, true);
}
fleeCar.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
fleeCar.body.setAngvel({ x: 0, y: 0, z: 0 }, true);
await wait(0.6);
put(spot0.x + 2.6, 1.2, spot0.z);
await wait(0.8);
await tap('KeyF');
ok('player can drive away from a chase', g.traffic.playerVehicle === fleeCar,
  String(g.traffic.playerVehicle && g.traffic.playerVehicle.spec.label));

// The anchor is where the quarry was when the player gave up: the route runs away from
// that, not from the live car, whose bearing rotates faster than a car can turn.
const anchor = quarry ? { x: quarry.position.x, z: quarry.position.z } : here();
let fleeGuard = 0, stuck = 0, path = 0, topKmh = 0, wp = 1;
let lastX = here().x, lastZ = here().z;
/*
 * The runner is measured alongside the player, because the escape rule is only honest if
 * the quarry is genuinely driving away rather than the player simply walking off the map.
 * A runner that queues at every red covers a couple of hundred metres of road in the whole
 * window; one that is actually running covers four hundred and clears the ring on its own.
 */
let qPath = 0, qTopKmh = 0;
let qLastX = null, qLastZ = null;
let route = routeAway(here(), anchor);
down('KeyW');
while (g.missions.active === chaseM && fleeGuard++ < 260 && !out()) {
  const run = g.missions.chase && g.missions.chase.vehicle;
  const q = run && run.position;
  const p = here();
  if (q) {
    dMax = Math.max(dMax, dist2(p, q));
    if (qLastX !== null) qPath += Math.hypot(q.x - qLastX, q.z - qLastZ);
    qLastX = q.x; qLastZ = q.z;
    qTopKmh = Math.max(qTopKmh, Math.abs(run.speedKmh));
  }
  if (g.player.health < 50) g.player.health = 100;
  // A burning car is about to remove the driver from the test; get out and keep going.
  if (fleeCar.wrecked) { up('KeyW'); await tap('KeyF'); break; }

  const moved = Math.hypot(p.x - lastX, p.z - lastZ);
  lastX = p.x; lastZ = p.z;
  path += moved;
  topKmh = Math.max(topKmh, fleeCar.speedKmh);

  if (wp >= route.length) { route = routeAway(p, anchor); wp = 1; }
  const node = route[Math.min(wp, route.length - 1)];
  if (dist2(p, node) < 24) { wp++; stuck = 0; }

  stuck = moved < 0.5 ? stuck + 1 : 0;
  if (stuck >= 4) {
    // Back off the wall and re-plan, which is the only thing that gets a wedged car moving.
    up('KeyW'); up('KeyA'); up('KeyD');
    down('KeyS'); down('KeyD');
    await wait(1.1);
    up('KeyS'); up('KeyD'); down('KeyW');
    route = routeAway(here(), anchor); wp = 1; stuck = 0;
    continue;
  }

  const err = wrap(Math.atan2(node.x - p.x, node.z - p.z) - fleeCar.heading);
  if (err > 0.09) { up('KeyA'); down('KeyD'); }
  else if (err < -0.09) { up('KeyD'); down('KeyA'); }
  else { up('KeyA'); up('KeyD'); }
  await wait(0.25);
}
totals.fleePath = Math.round(path);
totals.fleeTopKmh = Math.round(topKmh);
totals.quarryPath = Math.round(qPath);
totals.quarryTopKmh = Math.round(qTopKmh);
up('KeyW'); up('KeyA'); up('KeyD');
await wait(0.4);
if (g.traffic.playerVehicle) await tap('KeyF');
ok('chase fails when the quarry clears the escape ring',
  g.missions.active === null && lastFail === 'the target got away'
    && (failGap ?? 0) > (chaseObj.escape ?? 340),
  `reason "${lastFail}", gap ${Math.round(d0)}m -> ${Math.round(dMax)}m sampled, `
  + `${failGap === null ? 'no' : Math.round(failGap)}m at the call (escape ${chaseObj.escape}m), `
  + `runner covered ${totals.quarryPath}m at up to ${totals.quarryTopKmh} km/h`);
ok('failed chase returns to the pool', chaseM.state === 'available', chaseM.state);
ok('failed chase leaves no quarry behind', g.missions.chase === null,
  `traffic ${g.traffic.vehicles.length} vehicles`);
totals.chaseFailGap = Math.round(failGap ?? dMax);

// --- and now win it -----------------------------------------------------------
await reset();
g.weapons.give('rifle', 240); g.weapons.select('rifle');
g.player.health = 100;
put(chaseM.start.x, 1.2, chaseM.start.z);
await wait(1.4);
ok('chase mission is startable again after failing', g.missions.active === chaseM,
  g.missions.active ? g.missions.active.name : 'none');
spawnGuard = 0;
while (!g.missions.chase && spawnGuard++ < 30 && !out()) await wait(0.4);

const q2 = g.missions.chase && g.missions.chase.vehicle;
const shots0 = g.weapons.shotsFired;
const hp0 = q2 ? q2.health : 0;
let hpMin = hp0, bursts = 0;
if (q2) {
  /*
   * Closing the gap is teleported (the same shortcut the smoke test uses for a cross-city
   * commute); the kill is not. Every round is an aimed shot: the camera is turned onto the
   * car with real mousemove deltas and the trigger is a real mousedown.
   */
  while (g.missions.active === chaseM && g.missions.objectiveIndex === 0
         && bursts++ < 14 && !out()) {
    // Shooting a civilian car is a crime; the heat it earns is a different system's test.
    g.wanted.clear();
    if (g.player.health < 60) g.player.health = 100;
    await interceptAndFire(q2, 5);
    hpMin = Math.min(hpMin, q2.health);
    if (q2.health <= 0) break;
  }
  await wait(0.8);
}
ok('aimed fire under mouse input lands on the quarry',
  g.weapons.shotsFired > shots0 && hpMin < hp0,
  `${g.weapons.shotsFired - shots0} shots over ${bursts} passes, quarry hp ${hp0} -> ${hpMin}`);
ok('chase completes when the quarry is wrecked or stopped', chaseM.state === 'complete',
  `${chaseM.state}, quarry hp ${hpMin} (0 = wrecked, >0 = ran it to a standstill)`);
const chasePay = rewards[rewards.length - 1];
ok('chase pays its reward', chasePay === chaseM.reward, `paid $${chasePay} of $${chaseM.reward}`);
ok('completed chase clears its quarry from the world', g.missions.chase === null,
  `${g.traffic.vehicles.length} vehicles`);
totals.chaseReward = chasePay;
totals.chaseBursts = bursts;

/* ==================================================================== defend */
await reset();
g.wanted.clear();
const defM = byId('hold-the-line');
const defObj = defM.objectives[0];
const hold0 = defM.start;

g.player.health = 100;
put(hold0.x, 1.2, hold0.z);
await wait(1.4);
ok('defend mission triggers by walking into its marker', g.missions.active === defM,
  g.missions.active ? g.missions.statusLine : 'none');
ok('defend anchors on the mission start when it has no point of its own',
  !!g.missions.defend && dist2(g.missions.defend.at, hold0) < 0.001,
  g.missions.defend ? `${Math.round(g.missions.defend.at.x)},${Math.round(g.missions.defend.at.z)}` : 'none');

/*
 * Abandon the position on foot, down a street rather than into the first wall: the escape
 * target is a real road node just outside the zone, and the run has to beat the two waves
 * (2 x 16 s) or the mission completes underneath the test.
 */
let escape = null, escapeD = Infinity;
for (const n of g.city.network.nodes) {
  const d = Math.hypot(n.x - hold0.x, n.z - hold0.z);
  if (d < defObj.radius + 15 || d > defObj.radius + 90) continue;
  if (d < escapeD) { escapeD = d; escape = n; }
}
ok('there is a road out of the defend zone', !!escape, escape ? `${Math.round(escapeD)}m away` : 'none');
const outside = () => dist2(g.player.position, hold0) > defObj.radius + 8;
if (escape) await sprintTowards(escape, () => outside() || g.missions.active !== defM, 26);
const leftAt = dist2(g.player.position, hold0);
let graceGuard = 0;
while (g.missions.active === defM && graceGuard++ < 30 && !out()) await wait(0.5);
ok('defend fails once the player abandons the zone past the grace window',
  g.missions.active === null && lastFail === 'you abandoned the position',
  `reason "${lastFail}", ran to ${Math.round(leftAt)}m out of a ${defObj.radius}m zone, grace ${defObj.grace}s`);
ok('failed defend returns to the pool', defM.state === 'available', defM.state);
ok('failed defend despawns its attackers', g.missions.defend === null, String(g.missions.defend));
totals.defendFailRange = Math.round(leftAt);

// --- and now hold it ----------------------------------------------------------
await reset();
g.wanted.clear();
g.player.health = 100;
put(hold0.x, 1.2, hold0.z);
await wait(1.4);
ok('defend mission is startable again after failing', g.missions.active === defM, defM.state);

let wavesSeen = 0, spawned = 0, maxStars = 0, holdGuard = 0;
while (g.missions.active === defM && holdGuard++ < 160 && !out()) {
  const st = g.missions.defend;
  if (st) {
    wavesSeen = Math.max(wavesSeen, st.wave);
    spawned = Math.max(spawned, st.attackers.length);
  }
  maxStars = Math.max(maxStars, g.wanted.stars);
  // Stay standing: a cruiser running the player down would end the run as a death, which
  // is a different failure path and not the one under test here.
  if (g.player.health < 55) g.player.health = 100;
  put(hold0.x, 1.2, hold0.z);
  await wait(0.5);
}
await wait(0.5);
ok('defend runs every wave', wavesSeen >= (defObj.waves ?? 1),
  `reached wave ${wavesSeen} of ${defObj.waves}, up to ${spawned} attackers at once`);
ok('defend completes after the last wave', defM.state === 'complete', defM.state);
const defPay = rewards[rewards.length - 1];
ok('defend pays its reward', defPay === defM.reward, `paid $${defPay} of $${defM.reward}`);
ok('a siege never awards wanted stars', maxStars === 0, `peak stars ${maxStars}`);
totals.defendWaves = wavesSeen;
totals.defendReward = defPay;

/* ====================================================================== race */
await reset();
const raceM = byId('marina-sprint');
const raceObj = raceM.objectives[1];
const gate = raceM.objectives[0].at;
const centre = g.island.marina;
const boat = g.boats.reduce((best, b) =>
  (dist2(b.position, gate) < dist2(best.position, gate) ? b : best), g.boats[0]);
const seaY = g.ocean.level + 0.6;

ok('every buoy in the lap is on open water',
  raceObj.ring.length > 0 && raceObj.ring.every((c) => !g.island.isLand(c.x, c.z)),
  `${raceObj.ring.length} buoys`);

/** Start the race objective: board the boat and throttle into the start gate. */
const toTheLine = async () => {
  g.missions.start(raceM);
  await wait(0.5);
  if (g.traffic.playerVehicle) await tap('KeyF');
  lineUp(boat, centre, gate, 55, seaY);
  await wait(0.8);
  const b = boat.body.translation();
  put(b.x, b.y + 2.2, b.z);
  await wait(0.9);
  await tap('KeyF');
  const boarded = g.traffic.playerVehicle === boat;
  down('KeyW');
  let guard = 0;
  while (g.missions.objectiveIndex === 0 && guard++ < 50 && !out()) await wait(0.5);
  up('KeyW');
  await wait(0.3);
  return boarded;
};

const boarded = await toTheLine();
ok('race start gate is reached under boat throttle',
  boarded && g.missions.active === raceM && g.missions.objectiveIndex === 1,
  `boarded ${boarded}, objective ${g.missions.objectiveIndex}, ${g.missions.statusLine}`);

// Scratch: step off the boat and stay off it.
await tap('KeyF');
ok('player is out of the boat', g.traffic.playerVehicle === null, String(g.traffic.playerVehicle));
/*
 * Stay alive while the abandon clock runs. Stepping off a launch in open water leaves the
 * player treading it with a breath meter draining, and a drowned player fails the mission
 * as 'wasted' - a different rule, from a different system, reached before the one under
 * test. The chase and defend loops above hold health up for the same reason.
 */
let adriftGuard = 0;
while (g.missions.active === raceM && adriftGuard++ < 40 && !out()) {
  if (g.player.health < 60) g.player.health = 100;
  await wait(0.5);
}
ok('race fails when the boat is abandoned',
  g.missions.active === null && lastFail === 'you left the boat',
  `reason "${lastFail}", abandon window ${raceObj.abandon}s`);
ok('failed race returns to the pool', raceM.state === 'available', raceM.state);
totals.raceAbandon = raceObj.abandon;

// --- and now run the lap ------------------------------------------------------
await reset();
const boarded2 = await toTheLine();
ok('race mission is startable again after failing',
  boarded2 && g.missions.active === raceM && g.missions.objectiveIndex === 1, raceM.state);

let buoys = 0, laps = 0;
while (g.missions.active === raceM && g.missions.race && laps++ < 12 && !out()) {
  const st = g.missions.race;
  const cp = raceObj.ring[st.index];
  if (!cp) break;
  // Approach each buoy from inside the ring, so the run-up is always over water.
  lineUp(boat, centre, cp, 70, seaY);
  await wait(0.7);
  down('KeyW');
  const target = st.index;
  let guard = 0;
  while (g.missions.active === raceM && g.missions.race
         && g.missions.race.index === target && guard++ < 40 && !out()) await wait(0.5);
  up('KeyW');
  await wait(0.3);
  if (!g.missions.race || g.missions.race.index > target) buoys++;
}
await wait(0.6);
ok('every buoy is passed under throttle', buoys === raceObj.ring.length,
  `${buoys} of ${raceObj.ring.length} buoys`);
ok('race completes on the last buoy', raceM.state === 'complete', raceM.state);
const racePay = rewards[rewards.length - 1];
ok('race pays its reward, ghost bonus included',
  racePay === raceM.reward || racePay === raceM.reward + raceObj.ghostBonus,
  `paid $${racePay} (reward $${raceM.reward}, ghost bonus $${raceObj.ghostBonus})`);
totals.raceBuoys = buoys;
totals.raceReward = racePay;

/* -------------------------------------------------------------- shared plumbing */
ok('completion counter agrees with mission states',
  g.missions.completed === g.missions.missions.filter((m) => m.state === 'complete').length,
  `counter ${g.missions.completed} vs ${g.missions.missions.filter((m) => m.state === 'complete').length} flagged`);
ok('nothing template-shaped is left running',
  g.missions.chase === null && g.missions.defend === null && g.missions.race === null,
  `chase ${g.missions.chase}, defend ${g.missions.defend}, race ${g.missions.race}`);

// Put the harness back the way it found it.
g.missions.onReward = payHook;
delete g.missions.fail;
g.input.mouse.locked = wasLocked;
if (g.traffic.playerVehicle) await tap('KeyF');
g.wanted.clear();

return { simSeconds: Math.round(simT), wallSeconds: Math.round((performance.now() - T0) / 1000),
  ranOutOfTime: out(), totals, payouts: rewards,
  passed: log.filter((l) => l.pass).length, total: log.length,
  failures: log.filter((l) => !l.pass), log };
})()
