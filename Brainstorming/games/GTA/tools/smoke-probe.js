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
/*
 * A third of the sim time of the tap above. Everything between lighting a fuse and standing
 * clear of the car has to fit inside the SHORTEST natural fuse (3.4 s), or the wreck block
 * below fails for reasons that have nothing to do with the feature. `justPressed` is cleared
 * once per rendered frame, so a key only has to be held across one frame, not one second.
 */
const quickTap = async (c) => { down(c); await wait(0.15); up(c); await wait(0.25); };
const hold = async (c, s) => { down(c); await wait(s); up(c); await wait(0.2); };
/*
 * Frame-based waiting, for the pause-menu block only. The fixed step is gated while the menu
 * is open, so anything counting simulation seconds hangs the moment the menu appears.
 */
const frames = async (n) => { for (let i = 0; i < n && !out(); i++) await new Promise((r) => requestAnimationFrame(r)); };
const tapFrames = async (c) => { down(c); await frames(4); up(c); await frames(4); };

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

/* -------- pickups, settings and the render pipeline -------- */
const at = (item) => { g.player.body.setTranslation({ x: item.x, y: 1.2, z: item.z }, true); };
const find = (type) => g.pickups.items.find((i) => i.type === type && !i.taken);

/* ---------------------------------------------------------------- pickups */
const took0 = g.pickups.collected;

// Health pickup while already at full health must NOT be consumed.
g.player.health = 100;
const hFull = find('health');
if (hFull) { at(hFull); await wait(1.2);
  ok('full-health player does not waste a health pickup', !hFull.taken, `taken=${hFull.taken}`); }

g.player.health = 40;
const h = find('health');
if (h) { at(h); await wait(1.2);
  ok('health pickup heals and is consumed', g.player.health > 40 && h.taken,
    `hp 40 -> ${g.player.health}, taken ${h.taken}`); }

g.player.armour = 0;
const a = find('armour');
if (a) { at(a); await wait(1.2);
  ok('armour pickup raises armour', g.player.armour > 0, `armour ${g.player.armour}`); }

g.weapons.owned = new Set(['unarmed', 'pistol']);
const wpn = g.pickups.items.find((i) => !i.taken && ['smg', 'shotgun', 'rifle'].includes(i.type));
if (wpn) { at(wpn); await wait(1.2);
  ok('weapon pickup grants the weapon', g.weapons.owned.has(wpn.type),
    `${wpn.type}: owned [${[...g.weapons.owned]}]`); }

ok('collected counter tracks pickups', g.pickups.collected > took0,
  `${took0} -> ${g.pickups.collected}`);

/* --------------------------------------------------------------- settings */
const framesAt = () => E.frame;

// Volume
g.audio.setVolume(0.2);
ok('volume setting reaches the audio graph',
  Math.abs(g.audio.volume - 0.2) < 0.001 && (!g.audio.master || Math.abs(g.audio.master.gain.value - 0.2) < 0.001),
  `volume ${g.audio.volume}, gain ${g.audio.master && g.audio.master.gain.value}`);
g.audio.setVolume(0.65);

// Resolution scale must actually resize the drawing buffer.
const w0 = E.renderer.domElement.width;
E.setResolutionScale(0.5);
await wait(0.5);
const w1 = E.renderer.domElement.width;
ok('resolution scale resizes the framebuffer', w1 < w0, `${w0}px -> ${w1}px`);
E.setResolutionScale(1);
await wait(0.5);
ok('resolution scale restores', E.renderer.domElement.width === w0, `back to ${E.renderer.domElement.width}px`);

// Quality switch rebuilds the post chain and keeps rendering.
const q0 = g.postfx.quality;
const f0 = framesAt();
g.postfx.setQuality('ultra');
await wait(2);
ok('quality switch to ultra keeps rendering', E.frame > f0 + 5 && g.postfx.quality === 'ultra',
  `${q0} -> ${g.postfx.quality}, +${E.frame - f0} frames`);
const f1 = framesAt();
g.postfx.setQuality('low');
await wait(2);
ok('quality switch to low keeps rendering', E.frame > f1 + 5 && g.postfx.quality === 'low',
  `+${E.frame - f1} frames`);
g.postfx.setQuality(q0);
await wait(1.5);

// Post FX off/on must not black-screen.
const f2 = framesAt();
g.postfx.enabled = false;
await wait(1.5);
ok('post fx off keeps rendering', E.frame > f2 + 5, `+${E.frame - f2} frames`);
const f3 = framesAt();
g.postfx.enabled = true && !!g.postfx.post;
await wait(1.5);
ok('post fx back on keeps rendering', E.frame > f3 + 5 && g.postfx.enabled, `+${E.frame - f3} frames`);

/* ================================================================================
 * The P1 systems: burning wrecks, fall damage, drowning, persisted preferences.
 *
 * Each of these shipped with a throwaway probe of its own (tools/probe-wreck.js,
 * tools/probe-falldmg.js, tools/probe-settings.js) that nothing runs on a schedule, so
 * `WreckSystem` could have been deleted from main.js without a single check falling over.
 * What follows is the condensed core of those three files - enough to break loudly when a
 * system stops working, not the full parameter sweep, which stays in the probes.
 *
 * The blocks run last because they hurt the player and blow up scenery, and they run in
 * this order because each one leaves the player somewhere the next one wants him: at the
 * spawn, then on the highway, then in open water.
 * ============================================================================= */

/* ------------------------------------------------------ wrecks and the explosion */
if (!out()) {
  // No stars, no police bullets: the only thing allowed to move the health bar in this
  // block is the blast, and a cruiser firing through it would be indistinguishable.
  g.wanted.clear();
  if (g.missions.active) g.missions.fail('smoke');

  const wcar = (g.starterCar && !g.starterCar.wrecked)
    ? g.starterCar : g.traffic.vehicles.find((v) => !v.isBoat && !v.wrecked);
  const spawnW = g.city.playerSpawn();
  wcar.body.setTranslation({ x: spawnW.x + 6, y: 1.5, z: spawnW.z }, true);
  wcar.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
  wcar.body.setAngvel({ x: 0, y: 0, z: 0 }, true);
  g.player.body.setTranslation({ x: spawnW.x + 8, y: 1.2, z: spawnW.z }, true);
  await wait(1);
  await tap('KeyF');
  const drivingWreck = g.traffic.playerVehicle === wcar;
  let topW = 0;
  if (drivingWreck) {
    down('KeyW');
    // Torque, not distance, is the baseline here: `engineOn` gates engine force, so the
    // healthy car has to be shown pulling before the wreck is shown dead. How far it gets
    // is street furniture and luck, so only the speed is asserted on.
    for (let i = 0; i < 14 && !out(); i++) { topW = Math.max(topW, wcar.speedKmh); await wait(0.25); }
    up('KeyW');
  }
  ok('wreck: the car drives under throttle before it is wrecked',
    drivingWreck && topW > 5, `in car=${drivingWreck}, top ${topW.toFixed(1)} km/h`);

  /*
   * Count what the fire spawns. `smoke.activeCount > 0` would pass on leftover tyre smoke,
   * so the pool's spawn is wrapped and flame puffs (the ones with an over-range red
   * channel) are counted apart from grey soot. Restored before the block ends.
   */
  let flames = 0;
  const smoke = g.traffic.smoke;
  const realSpawn = smoke.spawn.bind(smoke);
  smoke.spawn = (pos, o = {}) => { if ((o.r ?? 1) >= 2) flames++; return realSpawn(pos, o); };

  // The blast tally, read off the game's own hook, so the numbers checked are the ones the
  // game acted on rather than a second measurement of the same thing.
  let boom = null;
  const prevExplode = g.wrecks.onExplode;
  g.wrecks.onExplode = (p, hit) => {
    // The standoff is read HERE: a wrecked car still coasts, and measuring at bail-out time
    // would report six metres while the hull rolled twelve away before it went off.
    boom = { t: simT, player: hit.player,
      standoff: Math.hypot(p.x - g.player.position.x, p.y - g.player.position.y, p.z - g.player.position.z) };
    prevExplode?.(p, hit);
  };

  /*
   * Damage goes in through the collision resolver rather than straight into the vehicle, so
   * this is the same path a head-on shunt takes. `handleImpact` caps a single event at 38
   * damage, hence the loop. It breaks the instant health hits 0 so the fuse clock starts
   * with no sim time wasted on it.
   */
  let impacts = 0;
  while (wcar.health > 0 && impacts++ < 8 && !out()) {
    g.traffic.handleImpact(wcar, null, 200000);
    if (wcar.health <= 0) break;
    await wait(0.3);
  }
  const tIgnite = simT;
  const fuse0 = wcar.fuse;
  ok('wreck: collision damage takes the car to 0 HP and lights a fuse',
    wcar.health === 0 && wcar.wrecked === true && fuse0 >= 3 && fuse0 <= 6 && wcar.engineOn === false,
    `hp ${wcar.health} after ${impacts} impacts, fuse ${fuse0.toFixed(2)}s, engineOn=${wcar.engineOn}`);

  await wait(0.15);
  const promptBurning = g.hud.el.prompt.textContent;
  ok('wreck: the HUD gives the driver a bail-out countdown',
    /Bail out/.test(promptBurning) && /\d\.\ds/.test(promptBurning), promptBurning.trim());

  await quickTap('KeyF');
  ok('wreck: F still gets the driver out of a burning car', g.traffic.playerVehicle === null,
    String(g.traffic.playerVehicle && g.traffic.playerVehicle.spec.label));

  /*
   * Six metres off, and held there while the hull coasts. Health is topped up first so the
   * blast delta is clean - the collision damage above has already been billed to the player.
   * The stand height is read back once and reused: replanting the capsule above the car
   * every step made it fall and land over and over, bleeding real fall damage into the
   * health delta the blast is supposed to own.
   */
  const wpos = () => wcar.body.translation();
  const w0 = wpos();
  g.player.health = 100; g.player.armour = 0;
  g.player.body.setTranslation({ x: w0.x + 6, y: w0.y + 0.4, z: w0.z }, true);
  await wait(0.4);
  const standY = g.player.body.translation().y;
  g.player.health = 100;
  const blasts0 = g.wrecks.explosions;
  let guardW = 0;
  while (!boom && guardW++ < 60 && !out()) {
    if (!wcar.exploded) {
      const p = wpos();
      g.player.body.setTranslation({ x: p.x + 6, y: standY, z: p.z }, true);
    }
    await wait(0.15);
  }
  const lost = 100 - g.player.health;
  const delay = boom ? boom.t - tIgnite : -1;
  ok('explosion: the wreck detonates when its own fuse runs out',
    !!boom && wcar.exploded === true && g.wrecks.explosions === blasts0 + 1
      && Math.abs(delay - fuse0) < 0.4,
    `fuse ${fuse0.toFixed(2)}s, went off after ${delay.toFixed(2)}s, explosions ${blasts0} -> ${g.wrecks.explosions}`);
  ok('explosion: a player six metres away loses health to the blast',
    !!boom && lost > 0 && boom.standoff > 5 && boom.standoff < 7.5
      && Math.abs(boom.player - lost) < 0.01,
    boom ? `${boom.standoff.toFixed(2)}m: hp 100 -> ${g.player.health.toFixed(1)} (-${lost.toFixed(1)}), hook says ${boom.player.toFixed(1)}`
      : 'no detonation');
  ok('explosion: the burning wreck spends flame particles', flames > 0, `${flames} flame puffs`);

  const paint = wcar._paint;
  ok('explosion: the hull comes out charred',
    !!paint && (paint.color.r + paint.color.g + paint.color.b) < 0.15,
    paint ? `rgb ${paint.color.r.toFixed(3)} ${paint.color.g.toFixed(3)} ${paint.color.b.toFixed(3)}` : 'no paint clone');

  // Driven through F from arm's length, not by asking the gate a question directly.
  const wEnd = wpos();
  g.player.body.setTranslation({ x: wEnd.x + 1.6, y: standY, z: wEnd.z }, true);
  await wait(0.4);
  const reach = g.traffic.nearestEnterable(g.player.position);
  await tap('KeyF');
  const promptBurnt = g.hud.el.prompt.textContent;
  ok('explosion: F refuses a burnt-out hull that is still the nearest vehicle',
    reach === wcar && g.traffic.playerVehicle === null
      && (g.hud.el.prompt.hidden === true || !/Enter/.test(promptBurnt)),
    `nearest=${reach ? reach.spec.label : 'none'}, in car=${g.traffic.playerVehicle}, prompt "${promptBurnt.trim()}"`);

  smoke.spawn = realSpawn;
  g.wrecks.onExplode = prevExplode;
  // Defuse whatever the blast set alight. Their detonations would land in the middle of the
  // fall-damage control drops below, which happen on this same stretch of street.
  for (const v of g.traffic.vehicles) if (v.wrecked && !v.exploded) v.fuse = 9000;
  g.player.health = 100;
  g.player.armour = 0;
}

/* -------------------------------------------------------------- fall damage */
/*
 * The drop height is not a constant copied out of a source file: the probe stands the
 * player on the real highway deck, reads back where he settled, then steps him off the
 * outer shoulder of that same deck. A 2 m hop on flat street is the control.
 */
if (!out()) {
  const R = g.highway.radius, OUT = R + 14;
  const clearAt = (x, z) => {
    if (!g.island.isLand(x, z)) return false;
    for (const b of g.city.buildingBoxes) {
      if (x > b.x0 - 3 && x < b.x1 + 3 && z > b.z0 - 3 && z < b.z1 + 3) return false;
    }
    return true;
  };
  let ang = null;
  for (let a = 0; a < 6.283 && ang === null; a += 0.01) {
    if (clearAt(Math.cos(a) * OUT, Math.sin(a) * OUT) && clearAt(Math.cos(a) * R, Math.sin(a) * R)) ang = a;
  }
  ok('fall: found a clear stretch of highway to step off',
    ang !== null, ang === null ? 'none' : `angle ${ang.toFixed(2)} rad`);

  g.player.teleport({ x: Math.cos(ang ?? 0.6) * R, y: g.highway.height + 0.4, z: Math.sin(ang ?? 0.6) * R });
  await wait(2);
  const deckY = g.player.position.y;
  ok('fall: the player stands on the highway deck',
    g.player.grounded && Math.abs(deckY - g.highway.height) < 0.6,
    `settled y=${deckY.toFixed(2)} vs deck height ${g.highway.height}`);

  if (ang !== null && !out()) {
    g.player.health = 100; g.player.armour = 0;
    await wait(0.4);
    // sqrt(2h/22) is 0.93 s for the 9.5 m deck; 3 s covers the fall and the landing step.
    g.player.teleport({ x: Math.cos(ang) * OUT, y: deckY, z: Math.sin(ang) * OUT });
    await wait(3);
    const fell = deckY - g.player.position.y;
    ok('fall: stepping off the highway deck costs health',
      g.player.health < 100 && g.player.health > 0 && fell > 8,
      `fell ${fell.toFixed(2)}m: hp 100 -> ${g.player.health.toFixed(1)} (-${(100 - g.player.health).toFixed(1)})`);
  }

  // The control. A drop the legs can absorb has to stay free, or every kerb bleeds health.
  const spawnF = g.city.playerSpawn();
  g.player.teleport({ x: spawnF.x, y: spawnF.y + 0.5, z: spawnF.z });
  await wait(2);
  const groundY = g.player.position.y;
  g.player.health = 100; g.player.armour = 0;
  await wait(0.4);
  g.player.teleport({ x: spawnF.x, y: groundY + 2, z: spawnF.z });
  await wait(2.5);
  ok('fall: a 2 m drop costs no health', g.player.health === 100 && g.player.grounded,
    `hp ${g.player.health.toFixed(1)}, landed y=${g.player.position.y.toFixed(2)}`);
}

/* ------------------------------------------------------------------ drowning */
if (!out()) {
  let deep = null;
  for (let r = g.island.radius + 140; r < g.island.radius + 700 && !deep; r += 60) {
    for (let a = 0; a < 6.28 && !deep; a += 0.4) {
      const x = Math.cos(a) * r, z = Math.sin(a) * r;
      if (g.island.landField(x, z) < -120) deep = { x, z };
    }
  }
  ok('drowning: found open water deep enough to swim in',
    !!deep, deep ? `${deep.x.toFixed(0)}, ${deep.z.toFixed(0)}` : 'none');

  if (deep) {
    g.player.health = 100; g.player.armour = 0;
    g.player.teleport({ x: deep.x, y: g.ocean.heightAt(deep.x, deep.z) - 1.2, z: deep.z });
    await wait(2);
    // Falling into water is a splash, not a landing: the swim branch never reaches _land().
    ok('drowning: the player swims in open water and the entry costs no health',
      g.player.isSwimming && g.player.health === 100,
      `state ${g.player.state}, depth ${g.player.waterDepth.toFixed(2)}m, hp ${g.player.health.toFixed(1)}`);

    const bar = document.getElementById('bar-breath');
    const air0 = g.player.breath;
    ok('drowning: the breath bar appears on the HUD while submerged',
      !!bar && !bar.parentElement.hidden && parseFloat(bar.style.width) < 100,
      bar ? `width ${bar.style.width}, row hidden=${bar.parentElement.hidden}` : 'no element');

    await wait(4);
    ok('drowning: the breath meter drains while the player stays under',
      g.player.breath < air0 - 3 && !!bar && parseFloat(bar.style.width) < 100,
      `air ${air0.toFixed(1)}s -> ${g.player.breath.toFixed(1)}s, bar ${bar && bar.style.width}`);

    /*
     * Twenty seconds of air is twenty seconds of wall clock spent re-proving what the two
     * checks above already prove. Wind the meter down instead - the same shortcut the timed
     * -mission check takes with `missions.timer` - and let the last of it run out on its own,
     * so the transitions that matter (red bar, empty, first damage) are the game's own.
     */
    g.player.breath = 1.2;
    const start = simT;
    let emptyAt = null, hurtAt = null, redAt = null;
    while (hurtAt === null && simT - start < 10 && !out()) {
      await wait(0.25);
      const t = simT - start;
      if (emptyAt === null && g.player.breath <= 0) emptyAt = t;
      if (redAt === null && bar && bar.classList.contains('low')) redAt = t;
      if (g.player.health < 100) hurtAt = t;
    }
    ok('drowning: the breath bar goes red before the meter runs dry',
      redAt !== null && emptyAt !== null && redAt <= emptyAt,
      `red at ${redAt === null ? 'never' : redAt.toFixed(2) + 's'}, empty after ${emptyAt === null ? 'never' : emptyAt.toFixed(2) + 's'}`);
    ok('drowning: an empty breath meter drains health',
      hurtAt !== null && emptyAt !== null && hurtAt >= emptyAt,
      `first damage at ${hurtAt === null ? 'never' : hurtAt.toFixed(2) + 's'}, hp ${g.player.health.toFixed(1)}`);

    // Back on dry land the lungs refill (3x faster than they empty) and the row hides again.
    g.player.teleport(g.city.playerSpawn());
    for (let i = 0; i < 20 && g.player.breath01 < 0.999 && !out(); i++) await wait(0.5);
    await wait(0.4);
    ok('drowning: breath refills and the bar hides back on land',
      g.player.breath01 > 0.99 && (!bar || bar.parentElement.hidden),
      `breath ${(g.player.breath01 * 100).toFixed(0)}%, row hidden=${bar && bar.parentElement.hidden}`);
    g.player.health = 100;
  }
}

/* ------------------------------------------------------- persisted preferences */
/*
 * The half of task 12 that fits inside one document: the pause menu writes the player's
 * choices to localStorage under the settings key, corrupt values fall back instead of
 * reaching the pipeline, and the save slot carries no preferences at all. The other half -
 * "reload the page and the choices hold" - cannot be tested by a script that dies with its
 * own document, and lives in `npm run smoke:settings` (tools/probe-settings-run.mjs).
 *
 * Nothing below may wait on sim time: an open pause menu gates the fixed step.
 */
if (!out()) {
  const SETTINGS_KEY = 'liberty-horizon:settings:v1';
  const SAVE_KEY = 'liberty-horizon:save:v1';
  const QUALITIES = ['low', 'medium', 'high', 'ultra'];
  const S = g.settings;
  const quality0 = g.postfx.quality, volume0 = g.audio.volume;
  S.clear();

  await tapFrames('Escape');
  const opened = g.pauseMenu.open === true && !document.getElementById('pause').hidden;
  const settingsTab = [...document.querySelectorAll('#pause-body .tabs button')]
    .find((b) => b.dataset.tab === 'settings');
  if (settingsTab) settingsTab.click();
  await frames(2);
  const panel = document.getElementById('pause-settings');
  ok('settings: Escape opens the pause menu and the settings tab shows',
    opened && !!panel && !panel.hidden, `open=${opened}, panel hidden=${panel && panel.hidden}`);

  const rowNamed = (name) => [...panel.querySelectorAll('.row.setting')]
    .find((r) => r.querySelector('span') && r.querySelector('span').textContent === name);
  const pick = (name, label) => {
    const row = rowNamed(name);
    const b = row && [...row.querySelectorAll('.choices button')].find((x) => x.textContent === label);
    if (b) b.click();
    return !!b;
  };
  const slide = (name, v) => {
    const row = rowNamed(name);
    const input = row && row.querySelector('input[type=range]');
    if (!input) return null;
    input.value = String(v);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return Number(input.value);
  };

  // Real clicks and a real drag on the real controls: the menu rows are the only writers of
  // the store, so driving the systems directly would prove nothing about persistence.
  const clickedQuality = pick('Quality', 'low');
  await frames(2);
  const slidVolume = slide('Volume', 0.2);
  await frames(2);
  ok('settings: clicking Quality "low" rebuilds the live pipeline',
    clickedQuality && g.postfx.quality === 'low', `${quality0} -> ${g.postfx.quality}`);
  ok('settings: dragging the Volume slider reaches the audio graph',
    slidVolume === 0.2 && Math.abs(g.audio.volume - 0.2) < 1e-6
      && (!g.audio.master || Math.abs(g.audio.master.gain.value - 0.2) < 1e-6),
    `slider ${slidVolume}, volume ${g.audio.volume}, gain ${g.audio.master && g.audio.master.gain.value}`);

  const flushed = S.flush();
  const stored = JSON.parse(localStorage.getItem(SETTINGS_KEY) || 'null');
  const values = (stored && stored.values) || {};
  ok('settings persistence: the menu choices are written to localStorage under the settings key',
    flushed === true && values.quality === 'low' && Math.abs(values.volume - 0.2) < 1e-6,
    `flushed=${flushed}, ${JSON.stringify(values)}`);

  // A hand-edited or stale store must not be able to brick boot: the typed accessors fall
  // back rather than handing a garbage preset to PostFX or a negative scale to the swap chain.
  S.set('quality', 'banana'); S.set('resolutionScale', -3);
  ok('settings persistence: corrupt stored values fall back instead of propagating',
    S.choice('quality', 'high', QUALITIES) === 'high' && S.number('resolutionScale', 1, 0.5, 1) === 0.5,
    `choice=${S.choice('quality', 'high', QUALITIES)}, number=${S.number('resolutionScale', 1, 0.5, 1)}`);

  S.setMany({ quality: 'low', volume: 0.2 });
  S.flush();
  g.money = 4242;
  g.save.save();
  const savedBlob = localStorage.getItem(SAVE_KEY) || '';
  ok('settings persistence: the save slot carries no preferences',
    savedBlob.length > 0 && !/"quality"|"resolutionScale"|"post"/.test(savedBlob),
    `${savedBlob.length} chars of save`);
  g.save.clear();
  ok('settings persistence: deleting the save keeps the preferences',
    localStorage.getItem(SAVE_KEY) === null && localStorage.getItem(SETTINGS_KEY) !== null,
    `save=${localStorage.getItem(SAVE_KEY)}, settings kept=${localStorage.getItem(SETTINGS_KEY) !== null}`);

  // Put the session back the way it was found, so the capture that follows is the shot the
  // harness asked for and not whatever this block last clicked.
  pick('Quality', quality0);
  slide('Volume', volume0);
  await frames(2);
  await tapFrames('Escape');
  ok('settings: Escape closes the menu and the simulation runs again',
    g.pauseMenu.open === false && E.paused === false,
    `open=${g.pauseMenu.open}, engine paused=${E.paused}`);
  S.clear();
}

return { simSeconds: Math.round(simT), wallSeconds: Math.round((performance.now()-T0)/1000),
  ranOutOfTime: out(), passed: log.filter(l=>l.pass).length, total: log.length,
  failures: log.filter(l=>!l.pass), log };
})()
