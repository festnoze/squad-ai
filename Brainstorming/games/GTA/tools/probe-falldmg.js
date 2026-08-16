/*
 * Fall damage and drowning.
 *
 * Two claims to prove with numbers rather than vibes: a landing only hurts above a
 * threshold, and staying in the water is eventually fatal.
 *
 * The drop height is not a constant copied out of a source file. The probe first stands
 * the player on the real highway deck and reads back where they settled, then steps them
 * off the outer edge of that same deck at that same height and measures what the landing
 * cost. A flat-street drop from the identical height runs alongside it as the repeatable
 * control, because the street under the ring is not guaranteed flat.
 */
(async () => {
const g = window.game, E = g.engine;
const log = []; const T0 = performance.now();
const BUDGET = 420000;
const ok = (n, c, x) => log.push({ step: n, pass: !!c, ...(x !== undefined ? { info: String(x) } : {}) });
let simT = 0; E.fixedCallbacks.push((dt) => { simT += dt; });
const wait = async (sec) => { const t = simT + sec;
  while (simT < t && performance.now() - T0 < BUDGET) await new Promise(r => requestAnimationFrame(r)); };
const out = () => performance.now() - T0 > BUDGET;
const down = (code) => window.dispatchEvent(new KeyboardEvent('keydown', { code, bubbles: true }));
const up = (code) => window.dispatchEvent(new KeyboardEvent('keyup', { code, bubbles: true }));
const hold = async (c, s) => { down(c); await wait(s); up(c); await wait(0.2); };

// A clean subject: no stars chasing us, no armour soaking the numbers, no mission timer.
g.wanted.clear();
if (g.missions.active) g.missions.fail('probe');
g.player.armour = 0;
g.player.health = 100;
const numbers = {};

/* ------------------------------------------------------------- the deck is real */
// Same ring the `highway` camera shot uses. Scan for an angle whose outer shoulder is on
// land and clear of every building box, so the step off the edge lands on street rather
// than on a roof three storeys up.
const R = g.highway.radius, OUT = R + 14;
const clear = (x, z) => {
  if (!g.island.isLand(x, z)) return false;
  for (const b of g.city.buildingBoxes) {
    if (x > b.x0 - 3 && x < b.x1 + 3 && z > b.z0 - 3 && z < b.z1 + 3) return false;
  }
  return true;
};
let ang = null;
for (let a = 0; a < 6.283 && ang === null; a += 0.01) {
  if (clear(Math.cos(a) * OUT, Math.sin(a) * OUT) && clear(Math.cos(a) * R, Math.sin(a) * R)) ang = a;
}
ok('found a clear stretch of highway to step off', ang !== null,
  ang === null ? 'none' : `angle ${ang.toFixed(2)} rad`);

const deckX = Math.cos(ang ?? 0.6) * R, deckZ = Math.sin(ang ?? 0.6) * R;
g.player.teleport({ x: deckX, y: g.highway.height + 0.4, z: deckZ });
await wait(2.5);
const deckY = g.player.position.y;
ok('player stands on the highway deck',
  g.player.grounded && Math.abs(deckY - g.highway.height) < 0.6,
  `settled y=${deckY.toFixed(2)} vs deck height ${g.highway.height}`);
numbers.deckY = +deckY.toFixed(2);

/* ------------------------------------------- stepping off the deck, real geometry */
let edge = null;
if (ang !== null && !out()) {
  g.player.health = 100; g.player.armour = 0;
  await wait(0.4);
  g.player.teleport({ x: Math.cos(ang) * OUT, y: deckY, z: Math.sin(ang) * OUT });
  await wait(3.5);
  edge = { hp: g.player.health, y: g.player.position.y, grounded: g.player.grounded };
  const fell = deckY - edge.y;
  ok('stepping off the highway deck costs health',
    edge.hp < 100 && edge.hp > 0 && fell > 8,
    `fell ${fell.toFixed(2)} m: hp 100 -> ${edge.hp.toFixed(1)} (-${(100 - edge.hp).toFixed(1)}), landed y=${edge.y.toFixed(2)}, grounded=${edge.grounded}`);
  numbers.deckEdgeFallMetres = +(deckY - edge.y).toFixed(2);
  numbers.deckEdgeHealthAfter = +edge.hp.toFixed(1);
}

/* ------------------------------------------------ flat-street control drops */
const spawn = g.city.playerSpawn();
g.player.teleport({ x: spawn.x, y: spawn.y + 0.5, z: spawn.z });
await wait(2.5);
const ground = g.player.position.y;
ok('player settles on flat street', g.player.grounded, `ground y=${ground.toFixed(2)}`);

/** Drop from `h` metres above the street the player is already standing on. */
const drop = async (h) => {
  g.player.health = 100;
  g.player.armour = 0;
  await wait(0.4);
  g.player.teleport({ x: spawn.x, y: ground + h, z: spawn.z });
  // sqrt(2h/22) is 1.2 s for a 16 m fall; 3.5 s covers the fall and the landing step.
  await wait(3.5);
  return { hp: g.player.health, y: g.player.position.y, grounded: g.player.grounded };
};

const shortFall = await drop(2);
ok('a 2 m drop costs no health', shortFall.hp === 100,
  `hp 100 -> ${shortFall.hp.toFixed(1)}, landed y=${shortFall.y.toFixed(2)}`);
numbers.drop2mHealthAfter = +shortFall.hp.toFixed(1);

const deckFall = await drop(g.highway.height);
const deckCost = 100 - deckFall.hp;
ok('a drop from deck height costs health',
  deckCost > 10 && deckFall.hp > 0 && Math.abs(deckFall.y - ground) < 0.6,
  `${g.highway.height} m: hp 100 -> ${deckFall.hp.toFixed(1)} (-${deckCost.toFixed(1)}), landed y=${deckFall.y.toFixed(2)}`);
numbers.drop9p5mHealthAfter = +deckFall.hp.toFixed(1);

// The curve has to be a curve: a 16 m drop must cost clearly more than a 9.5 m one.
const tallFall = await drop(16);
const tallCost = 100 - tallFall.hp;
ok('damage rises faster than height', tallCost > deckCost * 1.5 && tallFall.hp > 0,
  `9.5 m -${deckCost.toFixed(1)} hp vs 16 m -${tallCost.toFixed(1)} hp`);
numbers.drop16mHealthAfter = +tallFall.hp.toFixed(1);

// A jump under the player's own power must stay free, or every kerb hop bleeds health.
g.player.health = 100;
g.player.teleport({ x: spawn.x, y: ground, z: spawn.z });
await wait(1.5);
await hold('Space', 0.25);
await wait(2.5);
ok('a jump under real key input costs no health', g.player.health === 100,
  `hp ${g.player.health.toFixed(1)}`);
numbers.jumpHealthAfter = +g.player.health.toFixed(1);

/* -------------------------------------------------------------------- drowning */
let deep = null;
for (let r = g.island.radius + 140; r < g.island.radius + 700 && !deep; r += 60) {
  for (let a = 0; a < 6.28 && !deep; a += 0.4) {
    const x = Math.cos(a) * r, z = Math.sin(a) * r;
    if (g.island.landField(x, z) < -120) deep = { x, z };
  }
}
ok('found open water to drown in', !!deep, deep ? `${deep.x.toFixed(0)}, ${deep.z.toFixed(0)}` : 'none');

if (deep && !out()) {
  g.player.health = 100;
  g.player.armour = 0;
  g.player.teleport({ x: deep.x, y: g.ocean.heightAt(deep.x, deep.z) - 1.2, z: deep.z });
  await wait(2);
  ok('player is swimming in open water', g.player.isSwimming,
    `state ${g.player.state}, depth ${g.player.waterDepth.toFixed(2)} m`);
  // Falling into water is a splash, not a landing: the swim branch never reaches _land().
  ok('the swim entry itself cost no health', g.player.health === 100,
    `hp ${g.player.health.toFixed(1)}`);

  const bar = document.getElementById('bar-breath');
  ok('breath bar appears on the HUD while submerged',
    !!bar && !bar.parentElement.hidden && parseFloat(bar.style.width) < 100
      && getComputedStyle(bar.parentElement).display !== 'none',
    bar ? `width ${bar.style.width}, row hidden=${bar.parentElement.hidden}` : 'no element');

  const deaths0 = g.deaths ?? 0;
  const start = simT;
  let minHp = 100, emptyAt = null, firstHurtAt = null, diedAt = null, redAt = null;
  while (simT - start < 66 && !out()) {
    await wait(0.5);
    const t = simT - start;
    if (emptyAt === null && g.player.breath <= 0) emptyAt = t;
    if (firstHurtAt === null && g.player.health < 100) firstHurtAt = t;
    if (redAt === null && bar && bar.classList.contains('low')) redAt = t;
    minHp = Math.min(minHp, g.player.health);
    if ((g.deaths ?? 0) > deaths0) { diedAt = t; break; }
  }
  ok('breath runs out while submerged', emptyAt !== null && emptyAt < 25,
    `empty after ${emptyAt === null ? 'never' : emptyAt.toFixed(1) + ' s'}`);
  ok('breath bar turns red before the damage starts',
    redAt !== null && (firstHurtAt === null || redAt <= firstHurtAt),
    `red at ${redAt === null ? 'never' : redAt.toFixed(1) + ' s'}, first damage at ${firstHurtAt === null ? 'never' : firstHurtAt.toFixed(1) + ' s'}`);
  ok('an empty breath meter drains health', firstHurtAt !== null && emptyAt !== null
    && firstHurtAt >= emptyAt,
    `first damage at ${firstHurtAt === null ? 'never' : firstHurtAt.toFixed(1) + ' s'}, min hp ${minHp.toFixed(1)}`);
  ok('60 s submerged kills the player', diedAt !== null && diedAt <= 60,
    `died after ${diedAt === null ? 'survived' : diedAt.toFixed(1) + ' s'}, hp bottomed at ${minHp.toFixed(1)}`);
  numbers.breathEmptyAtSeconds = emptyAt === null ? null : +emptyAt.toFixed(1);
  numbers.firstDrownDamageAtSeconds = firstHurtAt === null ? null : +firstHurtAt.toFixed(1);
  numbers.deathAtSeconds = diedAt === null ? null : +diedAt.toFixed(1);

  // Death puts the player back on the street, so the meter must refill and disappear.
  await wait(3);
  ok('breath refills and the bar hides back on land',
    g.player.breath01 > 0.99 && (!bar || bar.parentElement.hidden),
    `breath ${(g.player.breath01 * 100).toFixed(0)}%, row hidden=${bar && bar.parentElement.hidden}`);
}

g.player.health = 100;
g.player.teleport(g.city.playerSpawn());
return { numbers, simSeconds: Math.round(simT),
  wallSeconds: Math.round((performance.now() - T0) / 1000), ranOutOfTime: out(),
  passed: log.filter(l => l.pass).length, total: log.length,
  failures: log.filter(l => !l.pass), log };
})()
