(async () => {
const g = window.game, E = g.engine;
const log = []; const T0 = performance.now();
const BUDGET = 420000;
const ok = (n, c, x) => log.push({ step: n, pass: !!c, ...(x !== undefined ? { info: String(x) } : {}) });
let simT = 0; E.fixedCallbacks.push((dt) => { simT += dt; });
const wait = async (sec) => { const t = simT + sec;
  while (simT < t && performance.now() - T0 < BUDGET) await new Promise(r => requestAnimationFrame(r)); };
const out = () => performance.now() - T0 > BUDGET;
// Where the game thinks the player is. Player.update returns early while DRIVING, so
// player.position is stale in a car - Missions._playerPoint reads the vehicle instead,
// and any test measuring progress has to do the same or it measures a parked corpse.
const here = () => { const c = g.traffic.playerVehicle;
  if (!c) return g.player.position;
  const t = c.body.translation(); return { x: t.x, y: t.y, z: t.z }; };
const distTo = (q) => Math.hypot(here().x - q.x, here().z - q.z);
const down = (code) => window.dispatchEvent(new KeyboardEvent('keydown', { code, bubbles: true }));
const up = (code) => window.dispatchEvent(new KeyboardEvent('keyup', { code, bubbles: true }));
const tap = async (c) => { down(c); await wait(0.2); up(c); await wait(0.4); };
const hold = async (c, s) => { down(c); await wait(s); up(c); await wait(0.2); };

const p0 = g.player.position.clone();
ok('player spawns on land', g.island.landField(p0.x, p0.z) > 0, `y=${p0.y.toFixed(1)}`);
await hold('KeyW', 2.5);
const walked = g.player.position.distanceTo(p0);
ok('player walks on key input', walked > 2, `${walked.toFixed(1)}m`);

const car = g.starterCar;
g.player.body.setTranslation({ x: car.position.x + 2, y: car.position.y + 1, z: car.position.z }, true);
await wait(1); await tap('KeyF');
ok('enter car with F', g.traffic.playerVehicle === car, car.spec.label);
const c0 = car.position.clone();
await hold('KeyW', 5);
ok('car drives', car.position.distanceTo(c0) > 25, `${Math.round(car.speedKmh)} km/h, ${Math.round(car.position.distanceTo(c0))}m`);
await tap('KeyF');
ok('exit car with F', g.traffic.playerVehicle === null);

if (!out()) {
  const boat = g.boats[0];
  g.player.body.setTranslation({ x: boat.position.x, y: boat.position.y + 2.5, z: boat.position.z }, true);
  await wait(1); await tap('KeyF');
  const inBoat = g.traffic.playerVehicle === boat;
  ok('enter boat with F', inBoat);
  if (inBoat) {
    const b0 = boat.position.clone();
    await hold('KeyW', 5);
    ok('boat drives', boat.position.distanceTo(b0) > 12, `${Math.round(boat.speedKmh)} km/h, ${Math.round(boat.position.distanceTo(b0))}m`);
    ok('boat floats at sea level', boat.position.y > -3 && boat.position.y < 3, `y=${boat.position.y.toFixed(1)}`);
    await tap('KeyF');
  }
}

// --- mission, start to reward -------------------------------------------------
// The cross-city commute is skipped by teleporting the car, but every state
// transition is driven the way a player drives it: walk into the start marker,
// get in a car to clear the steal objective, then drive the last stretch under
// throttle so arrival is real motion into the trigger radius.
const m = g.missions.missions.find(x => x.id === 'first-ride') || g.missions.missions[0];
const moneyBefore = g.money, doneBefore = g.missions.completed;
g.player.body.setTranslation({ x: m.start.x, y: 1.2, z: m.start.z }, true);
await wait(1.2);
ok('mission triggers on approach', g.missions.active === m, m.name);
ok('mission gives an objective', !!g.missions.currentObjective, g.missions.statusLine);

const mcar = g.starterCar;
mcar.body.setTranslation({ x: m.start.x + 4, y: 1.5, z: m.start.z }, true);
mcar.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
await wait(0.6);
g.player.body.setTranslation({ x: m.start.x + 2.5, y: 1.2, z: m.start.z }, true);
await wait(0.6);
await tap('KeyF');
await wait(0.6);
ok('steal objective clears on entering a car', g.missions.objectiveIndex > 0, g.missions.statusLine);

const goal = g.missions.currentObjective && g.missions.currentObjective.at;
if (goal && g.traffic.playerVehicle === mcar) {
  /*
   * Drop the car on an actual road running into the goal, not 40 m back along the
   * straight line from the mission start - that line cuts through city blocks, and a car
   * teleported inside a building sits at full throttle going nowhere.
   */
  const net = g.city.network;
  let node = net.nodes[0], nd = Infinity;
  for (const n of net.nodes) {
    const d = Math.hypot(n.x - goal.x, n.z - goal.z);
    if (d < nd) { nd = d; node = n; }
  }
  const edge = net.edges[node.edges[0]];
  const far = net.nodes[edge.a === node.id ? edge.b : edge.a];
  const ex = far.x - node.x, ez = far.z - node.z;
  const eL = Math.hypot(ex, ez) || 1;
  const back = Math.min(45, eL * 0.8);
  const sx = node.x + (ex / eL) * back, sz = node.z + (ez / eL) * back;
  const yaw = Math.atan2(goal.x - sx, goal.z - sz);
  mcar.body.setTranslation({ x: sx, y: 1.5, z: sz }, true);
  mcar.body.setRotation({ x: 0, y: Math.sin(yaw / 2), z: 0, w: Math.cos(yaw / 2) }, true);
  mcar.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
  mcar.body.setAngvel({ x: 0, y: 0, z: 0 }, true);
  await wait(1);
  const approach0 = distTo(goal);
  down('KeyW');
  let topSpeed = 0;
  const deadline = simT + 25;
  while (g.missions.active === m && simT < deadline && !out()) {
    topSpeed = Math.max(topSpeed, mcar.speedKmh);
    await wait(0.25);
  }
  up('KeyW');
  ok('mission car actually accelerates', topSpeed > 15, `top ${Math.round(topSpeed)} km/h`);
  await wait(0.5);
  const approach1 = distTo(goal);
  ok('car closes on the objective under throttle', approach1 < approach0 - 15,
    `${Math.round(approach0)}m -> ${Math.round(approach1)}m`);
  ok('mission completes', m.state === 'complete', m.state);
  ok('completion counter increments', g.missions.completed === doneBefore + 1,
    `${doneBefore} -> ${g.missions.completed}`);
  ok('reward is paid', g.money === moneyBefore + m.reward,
    `${moneyBefore} -> ${g.money} (reward ${m.reward})`);
  if (g.traffic.playerVehicle) await tap('KeyF');
} else {
  ok('drive objective reachable', false, 'no goal or not in the mission car');
}

g.weapons.give('rifle', 90); g.weapons.select('rifle'); await wait(0.4);
const s0 = g.weapons.shotsFired;
window.dispatchEvent(new MouseEvent('mousedown', { button: 0, bubbles: true }));
await wait(1); window.dispatchEvent(new MouseEvent('mouseup', { button: 0, bubbles: true }));
await wait(0.4);
ok('weapon fires on click', g.weapons.shotsFired > s0, `${g.weapons.shotsFired - s0} shots, mag ${g.weapons.magazine}`);

g.wanted.report(3.5, 'smoke'); await wait(0.8);
ok('wanted rises', g.wanted.stars > 0, `stars ${g.wanted.stars}`);

// --- failure paths ------------------------------------------------------------
// Everything above proves the happy path. These prove the game can also tell you no.

// Wasted: health to zero must respawn, bill the player and end the current job.
const m2 = g.missions.missions.find(x => x.state === 'available');
g.missions.start(m2); await wait(0.6);
const cashBeforeDeath = g.money, deathsBefore = g.deaths ?? 0;
g.player.health = 4;
g.player.damage(50);
await wait(1.2);
ok('death respawns with full health', g.player.health === 100, `hp ${g.player.health}`);
ok('death charges a hospital fee', g.money === Math.max(0, cashBeforeDeath - 750),
  `${cashBeforeDeath} -> ${g.money}`);
ok('death ends the active mission', g.missions.active === null, String(g.missions.active));
ok('death is counted', (g.deaths ?? 0) === deathsBefore + 1, String(g.deaths));

// Busted: the arrest path must also end the job and clear the stars.
const m3 = g.missions.missions.find(x => x.state === 'available');
g.missions.start(m3); await wait(0.6);
const cashBeforeBust = g.money, bustsBefore = g.wanted.busted;
g.wanted.report(5, 'smoke'); await wait(0.4);
g.wanted._bust(); await wait(0.8);
ok('busted clears the wanted level', g.wanted.stars === 0, `stars ${g.wanted.stars}`);
ok('busted ends the active mission', g.missions.active === null, String(g.missions.active));
ok('busted is counted and fined', g.wanted.busted === bustsBefore + 1 && g.money === Math.max(0, cashBeforeBust - 500),
  `busts ${g.wanted.busted}, ${cashBeforeBust} -> ${g.money}`);

// Mission timeout: a timed objective must fail itself and return the mission to the pool.
const timed = g.missions.missions.find(x => x.objectives.some(o => o.timeLimit));
if (timed) {
  g.missions.start(timed); await wait(0.5);
  // Skip to the timed objective, then run the clock out.
  let guard = 0;
  while (g.missions.active && !g.missions.currentObjective.timeLimit && guard++ < 6) g.missions._advance();
  const timedObj = g.missions.active && g.missions.currentObjective;
  if (timedObj && timedObj.timeLimit) {
    g.missions.timer = 0.4;
    await wait(1.5);
    ok('timed objective fails on the clock', g.missions.active === null, String(g.missions.active));
    ok('failed mission returns to the pool', timed.state === 'available', timed.state);
  } else ok('timed objective reachable', false, 'could not reach a timed objective');
} else ok('a timed mission exists', false);

/*
 * Police return fire. Asserting the method exists would pass while it did nothing, so
 * this stands a cruiser next to the player at four stars, gives it line of sight, and
 * checks the health bar actually moves.
 */
g.wanted.clear(); await wait(0.3);
g.player.teleport(g.city.playerSpawn());
await wait(0.5);
g.wanted.report(9, 'smoke');
let dispatchGuard = 0;
while (g.wanted.units.length === 0 && dispatchGuard++ < 40 && !out()) await wait(0.5);
ok('police units dispatch at a high wanted level',
  g.wanted.units.length > 0, `${g.wanted.units.length} units, ${g.wanted.stars} stars`);
if (g.wanted.units.length) {
  const unit = g.wanted.units[0];
  const pp = g.player.position;
  unit.vehicle.body.setTranslation({ x: pp.x + 9, y: 1.0, z: pp.z }, true);
  unit.vehicle.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
  unit.seen = true;
  unit.fireTimer = 0;
  const hpBefore = g.player.health;
  const deathsBefore2 = g.deaths ?? 0;
  let fired = 0;
  const shotHook = g.wanted.onShot;
  g.wanted.onShot = (from, hitP) => { fired++; shotHook?.(from, hitP); };
  for (let i = 0; i < 24 && !out(); i++) {
    unit.seen = true;
    const q = g.player.position;
    unit.vehicle.body.setTranslation({ x: q.x + 9, y: 1.0, z: q.z }, true);
    await wait(0.5);
  }
  g.wanted.onShot = shotHook;
  ok('police open fire', fired > 0, `${fired} shots`);
  ok('police gunfire damages the player',
    g.player.health < hpBefore || (g.deaths ?? 0) > deathsBefore2,
    `hp ${hpBefore} -> ${g.player.health}, deaths ${deathsBefore2} -> ${g.deaths ?? 0}`);
}
g.wanted.clear();

g.money = 4321; const wrote = g.save.save(); g.money = 0; g.save.load(); await wait(0.4);
ok('save writes', !!wrote);
ok('load restores money', g.money === 4321, `money=${g.money}`);

/*
 * Save/load fidelity. Loading has to *replace* progress, not merge into it - the original
 * only ever added the saved weapons and marked the saved missions complete, so anything
 * gained after the save survived a load of an older one.
 */
g.weapons.owned = new Set(['unarmed', 'pistol']); g.weapons.select('pistol');
g.missions.restoreProgress([]);
g.money = 1000;
g.save.save();
g.weapons.give('rifle', 90);
g.missions.missions[0].state = 'complete'; g.missions.completed = 1;
const laterMission = g.missions.missions.find(x => x.state === 'available');
g.missions.start(laterMission);
g.money = 9999;
await wait(0.5);
g.save.load(); await wait(0.6);
ok('load drops weapons gained after the save', !g.weapons.owned.has('rifle'),
  `owned [${[...g.weapons.owned]}]`);
ok('load reverts missions completed after the save',
  g.missions.missions[0].state === 'available', g.missions.missions[0].state);
ok('load cancels a mission in progress', g.missions.active === null,
  String(g.missions.active && g.missions.active.name));
ok('mission counter agrees with mission states',
  g.missions.completed === g.missions.missions.filter(m => m.state === 'complete').length,
  `counter ${g.missions.completed} vs ${g.missions.missions.filter(m => m.state === 'complete').length} flagged`);

return { simSeconds: Math.round(simT), wallSeconds: Math.round((performance.now()-T0)/1000),
  ranOutOfTime: out(), passed: log.filter(l=>l.pass).length, total: log.length,
  failures: log.filter(l=>!l.pass), log };
})()
