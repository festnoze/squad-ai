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

g.money = 4321; const wrote = g.save.save(); g.money = 0; g.save.load(); await wait(0.4);
ok('save writes', !!wrote);
ok('load restores money', g.money === 4321, `money=${g.money}`);

return { simSeconds: Math.round(simT), wallSeconds: Math.round((performance.now()-T0)/1000),
  ranOutOfTime: out(), passed: log.filter(l=>l.pass).length, total: log.length,
  failures: log.filter(l=>!l.pass), log };
})()
