(async () => {
const g = window.game, E = g.engine;
const log = []; const T0 = performance.now();
const BUDGET = 300000;
const ok = (n, c, x) => log.push({ step: n, pass: !!c, ...(x !== undefined ? { info: String(x) } : {}) });
let simT = 0; E.fixedCallbacks.push((dt) => { simT += dt; });
const wait = async (sec) => { const t = simT + sec;
  while (simT < t && performance.now() - T0 < BUDGET) await new Promise(r => requestAnimationFrame(r)); };
const out = () => performance.now() - T0 > BUDGET;
const down = (code) => window.dispatchEvent(new KeyboardEvent('keydown', { code, bubbles: true }));
const up = (code) => window.dispatchEvent(new KeyboardEvent('keyup', { code, bubbles: true }));
const tap = async (c) => { down(c); await wait(0.2); up(c); await wait(0.4); };
/*
 * A tap that costs a third of the sim time of the one above. Everything between lighting
 * the fuse and standing clear has to fit inside the SHORTEST natural fuse (3.4 s) or the
 * run fails for reasons that have nothing to do with the feature. `justPressed` is cleared
 * once per rendered frame, so the key only has to be held across one frame, not one second.
 */
const quickTap = async (c) => { down(c); await wait(0.15); up(c); await wait(0.25); };
const hold = async (c, s) => { down(c); await wait(s); up(c); await wait(0.2); };
const at = (o) => { const t = o.body.translation(); return { x: t.x, y: t.y, z: t.z }; };
const dist3 = (a, b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
const V3 = g.player.position.constructor;

/* ------------------------------------------------------ a healthy car is a working car */
const car = g.starterCar;
g.player.body.setTranslation({ x: car.position.x + 2, y: car.position.y + 1, z: car.position.z }, true);
await wait(1);
await tap('KeyF');
ok('probe gets in the car with F', g.traffic.playerVehicle === car, car.spec.label);

const drive0 = at(car);
down('KeyW');
let topSpeed = 0, rolled = 0;
for (let i = 0; i < 14; i++) {
  topSpeed = Math.max(topSpeed, car.speedKmh);
  const p = at(car);
  rolled = Math.max(rolled, Math.hypot(p.x - drive0.x, p.z - drive0.z));
  await wait(0.25);
}
up('KeyW');
/*
 * Torque, not distance, is the baseline this probe needs: `engineOn` now gates engine
 * force, so the healthy car has to be shown pulling before the wreck is shown dead. How
 * far it gets is street furniture and luck (one run bumped a kerb at 2.5 m), so the
 * distance is reported but not asserted on.
 */
ok('the car makes engine torque before it is wrecked', topSpeed > 8,
  `top ${topSpeed.toFixed(1)} km/h, ${rolled.toFixed(1)}m out`);
await wait(1.2);

/*
 * Count what the fire actually spawns. `activeCount > 0` would pass on leftover tyre smoke,
 * so the pool's spawn is wrapped and flame puffs (the ones with an over-range red channel)
 * are counted apart from grey soot. Restored before the run ends.
 */
let flames = 0, soot = 0;
const smoke = g.traffic.smoke;
const realSpawn = smoke.spawn.bind(smoke);
smoke.spawn = (pos, o = {}) => { if ((o.r ?? 1) >= 2) flames++; else soot++; return realSpawn(pos, o); };

// The blast tally, captured from the game's own hook so the numbers are the ones the game
// acted on rather than a second measurement of the same thing.
let boom = null;
const prevExplode = g.wrecks.onExplode;
g.wrecks.onExplode = (p, hit) => {
  // The standoff is read HERE, not before the wait loop: a wrecked car still coasts (no
  // engine torque, only engine braking), and the first version of this probe measured
  // 6.0 m at bail-out, then let the hull roll 12 m away before it went off and wondered
  // why the blast missed. The distance that matters is the one at the instant of the bang.
  boom = { t: simT, player: hit.player, vehicles: hit.vehicles, peds: hit.peds, ignited: hit.ignited,
    standoff: dist3({ x: p.x, y: p.y, z: p.z }, g.player.position) };
  prevExplode?.(p, hit);
};

/* -------------------------------------------------------------------- drive it to zero */
/*
 * Damage goes in through the collision resolver, not straight into the vehicle, so this
 * exercises the same path a head-on shunt takes. `handleImpact` caps a single event at 38
 * damage, which is why it takes three of them. The loop breaks the instant health hits 0
 * so the fuse clock starts with no wasted sim time on it.
 */
let impacts = 0;
while (car.health > 0 && impacts++ < 8 && !out()) {
  g.traffic.handleImpact(car, null, 200000);
  if (car.health <= 0) break;
  await wait(0.4);
}
const tIgnite = simT;
const fuse0 = car.fuse;
ok('collision damage drives the car to 0 HP', car.health === 0, `hp ${car.health} after ${impacts} impacts`);
ok('zero HP lights a fuse', car.wrecked === true && fuse0 > 0, `wrecked=${car.wrecked} fuse=${fuse0.toFixed(2)}s`);
ok('the fuse is long enough to be a decision', fuse0 >= 3 && fuse0 <= 6, `${fuse0.toFixed(2)}s`);
ok('a wrecked engine is dead', car.engineOn === false && car.exploded === false,
  `engineOn=${car.engineOn} exploded=${car.exploded}`);

// The bail-out clock is on screen while the player is still in the seat.
await wait(0.15);
const prompt = g.hud.el.prompt.textContent;
ok('HUD gives the driver a bail-out clock', /Bail out/.test(prompt), prompt.trim());

/* -------------------------------------------------------- get out, then keep him out */
await quickTap('KeyF');
ok('the player can still bail out of a burning car', g.traffic.playerVehicle === null);

const c = at(car);
g.player.body.setTranslation({ x: c.x + 1.6, y: c.y + 0.4, z: c.z }, true);
await wait(0.3);
const reach = g.traffic.nearestEnterable(g.player.position);
ok('the wreck is still the nearest vehicle (so the gate is what refuses it, not distance)',
  reach === car, reach ? reach.spec.label : 'none');
await quickTap('KeyF');
const promptBurning = g.hud.el.prompt.textContent;
ok('F does not put the player back into a burning car', g.traffic.playerVehicle === null,
  String(g.traffic.playerVehicle && g.traffic.playerVehicle.spec.label));
ok('no enter prompt for a burning car',
  g.hud.el.prompt.hidden === true || !/Enter/.test(promptBurning),
  `hidden=${g.hud.el.prompt.hidden} "${promptBurning.trim()}"`);
ok('the burning car is emitting fire, not just soot', flames > 0, `${flames} flame puffs, ${soot} soot`);
ok('flame puffs carry an over-range colour into the pool',
  Array.from(smoke.rgb).some((v) => v > 2), `max channel ${Math.max(...smoke.rgb).toFixed(2)}`);

/* --------------------------------------------------------------------- the detonation */
// Stand six metres off and hold there. Health is topped up first so the blast delta is
// clean: the collision damage above has already been billed to the player.
g.player.health = 100; g.player.armour = 0;
g.player.body.setTranslation({ x: at(car).x + 6, y: c.y + 0.4, z: c.z }, true);
await wait(0.4);
// Keep the capsule at the height it settled at. Re-planting it 0.4 m above the car centre
// every step made the player fall and land over and over, which bled real fall damage into
// the health delta the blast is supposed to own.
const standY = g.player.body.translation().y;
const standoff0 = dist3(at(car), g.player.position);
const hpBefore = g.player.health;
const pedsDown0 = g.peds.knockdowns;
const blasts0 = g.wrecks.explosions;
const flames0 = flames;

/*
 * A neighbour parked inside the blast radius, on the far side from the player. It is left
 * on 20 HP on purpose: a healthy car four metres away takes about 29 of the 55 damage, so
 * a chain reaction has to be earned. A parked car is used rather than a traffic one so the
 * autopilot is not fighting the placement.
 */
const near2 = g.traffic.vehicles.find((v) => v !== car && !v.isBoat && !g.traffic.ai.has(v));
const near2Hp0 = 20;

let guard = 0;
while (!boom && guard++ < 60 && !out()) {
  // Track the hull rather than a fixed spot: the standoff is what is under test, and a
  // coasting wreck would otherwise decide it for us.
  if (!car.exploded) {
    const p = at(car);
    g.player.body.setTranslation({ x: p.x + 6, y: standY, z: p.z }, true);
    if (near2) {
      near2.health = near2Hp0;
      near2.body.setTranslation({ x: p.x - 4, y: p.y, z: p.z }, true);
      near2.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
    }
  }
  await wait(0.15);
}
const standoff = boom ? boom.standoff : dist3(at(car), g.player.position);
const hpAfter = g.player.health;
const delay = boom ? boom.t - tIgnite : -1;
const lost = hpBefore - hpAfter;

ok('the car detonates on its own clock', !!boom && car.exploded === true && g.wrecks.explosions === blasts0 + 1,
  `explosions ${blasts0} -> ${g.wrecks.explosions}, exploded=${car.exploded}`);
ok('the detonation lands on the fuse it advertised', boom && Math.abs(delay - fuse0) < 0.35,
  `fuse ${fuse0.toFixed(2)}s, measured ${delay.toFixed(2)}s`);
ok('a player six metres away is hurt by the blast', lost > 0,
  `${standoff.toFixed(2)}m: hp ${hpBefore} -> ${hpAfter.toFixed(1)} (-${lost.toFixed(1)})`);
ok('the standoff really was about six metres', standoff > 5 && standoff < 7.5,
  `${standoff.toFixed(2)}m at the bang, ${standoff0.toFixed(2)}m when the wait started`);
ok('the damage the game applied is the damage the hook reported',
  boom && Math.abs(boom.player - lost) < 0.01, boom ? `hook ${boom.player.toFixed(1)} vs bar ${lost.toFixed(1)}` : 'no boom');
ok('the fireball spends particles', flames > flames0, `+${flames - flames0} flame puffs`);
ok('the blast reached the crowd', g.peds.knockdowns >= pedsDown0 && !!boom,
  boom ? `${boom.peds} floored, ${boom.vehicles} cars shoved, ${boom.ignited} set alight` : 'no boom');
ok('a car four metres away is damaged and set alight in turn',
  !!near2 && near2.health === 0 && near2.wrecked === true && boom && boom.vehicles >= 1 && boom.ignited >= 1,
  near2 ? `${near2.spec.label} ${near2Hp0} -> ${near2.health} hp, wrecked=${near2.wrecked}` : 'no neighbour car');
// Defuse it: its own detonation would land in the middle of the helper checks below and
// bill the player for damage those checks are trying to isolate.
if (near2) near2.fuse = 900;

const paint = car._paint;
const charred = paint && (paint.color.r + paint.color.g + paint.color.b) < 0.15;
ok('the hull is charred', !!charred, paint
  ? `rgb ${paint.color.r.toFixed(3)} ${paint.color.g.toFixed(3)} ${paint.color.b.toFixed(3)}, rough ${paint.roughness.toFixed(2)}`
  : 'no paint clone');
ok('the wreck is no longer AI traffic', g.traffic.ai.has(car) === false);

// Not enterable after the bang either, driven through F from arm's length.
g.player.body.setTranslation({ x: c.x + 1.6, y: c.y + 0.4, z: c.z }, true);
await wait(0.4);
await tap('KeyF');
const promptBurnt = g.hud.el.prompt.textContent;
ok('F does not put the player into a burnt-out hull', g.traffic.playerVehicle === null,
  String(g.traffic.playerVehicle && g.traffic.playerVehicle.spec.label));
ok('no enter prompt for a burnt-out hull',
  g.hud.el.prompt.hidden === true || !/Enter/.test(promptBurnt),
  `hidden=${g.hud.el.prompt.hidden} "${promptBurnt.trim()}"`);

/* ------------------------------------------- the blast helper on its own (for grenades) */
// Later batches reuse `wrecks.blast(point)` without wrecking a car first, so it is called
// directly here: once outside the radius, once close in, to prove the falloff is graded
// rather than a flat "everyone in range takes 70".
const pFar = new V3(g.player.position.x + 40, g.player.position.y, g.player.position.z);
g.player.health = 100; g.player.armour = 0;
g.wrecks.blast(pFar);
await wait(0.2);
ok('blast() outside its radius costs nothing', g.player.health === 100, `hp ${g.player.health}`);

const pNear = new V3(g.player.position.x + 2, g.player.position.y + 0.9, g.player.position.z);
g.wrecks.blast(pNear);
await wait(0.2);
const lostNear = 100 - g.player.health;
ok('blast() falls off with distance', lostNear > lost,
  `2m -${lostNear.toFixed(1)} hp vs 6m -${lost.toFixed(1)} hp`);

smoke.spawn = realSpawn;
g.wrecks.onExplode = prevExplode;
g.player.health = 100;

// One last check the world survived it.
const f0 = E.frame;
await wait(1.5);
ok('the game keeps rendering after the explosion', E.frame > f0 + 5, `+${E.frame - f0} frames`);

return { simSeconds: Math.round(simT), wallSeconds: Math.round((performance.now() - T0) / 1000),
  ranOutOfTime: out(),
  fuseSeconds: Number(fuse0.toFixed(2)), detonationDelay: Number(delay.toFixed(2)),
  healthLostAt6m: Number(lost.toFixed(1)), healthLostAt2m: Number(lostNear.toFixed(1)),
  flamePuffs: flames,
  passed: log.filter(l => l.pass).length, total: log.length,
  failures: log.filter(l => !l.pass), log };
})()
