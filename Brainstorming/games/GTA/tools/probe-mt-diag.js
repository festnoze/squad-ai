(async () => {
const g = window.game, E = g.engine;
const T0 = performance.now();
let simT = 0; E.fixedCallbacks.push((dt) => { simT += dt; });
const wait = async (sec) => { const t = simT + sec;
  while (simT < t && performance.now() - T0 < 120000) await new Promise(r => requestAnimationFrame(r)); };
const wrap = (a) => { while (a > Math.PI) a -= Math.PI * 2; while (a < -Math.PI) a += Math.PI * 2; return a; };
g.input.mouse.locked = true;
const SENS = g.cameraRig.sensitivity;
const mouse = (dx, dy) => window.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, movementX: dx, movementY: dy }));
const camFwd = () => { const e = g.cameraRig.camera.matrixWorld.elements;
  const l = Math.hypot(e[8], e[9], e[10]) || 1; return { x: -e[8] / l, y: -e[9] / l, z: -e[10] / l }; };
const aimError = (t) => {
  const p = g.player.position;
  const dx = t.x - p.x, dy = t.y - (p.y + 1.4), dz = t.z - p.z;
  const len = Math.hypot(dx, dy, dz) || 1; const f = camFwd();
  const c1 = (v) => Math.max(-1, Math.min(1, v));
  return { yaw: wrap(Math.atan2(dx, dz) - Math.atan2(f.x, f.z)),
    pitch: Math.asin(c1(dy / len)) - Math.asin(c1(f.y)), len };
};

g.weapons.give('rifle', 240); g.weapons.select('rifle');
const m = g.missions.missions.find((x) => x.id === 'hot-pursuit');
g.missions.start(m);
let guard = 0;
while (!g.missions.chase && guard++ < 30) await wait(0.4);
const v = g.missions.chase.vehicle;

const t0 = v.body.translation();
const h = v.heading;
const px = t0.x + Math.sin(h) * 14, pz = t0.z + Math.cos(h) * 14;
g.player.body.setTranslation({ x: px, y: Math.max(g.island.heightAt(px, pz), g.ocean.level) + 1.2, z: pz }, true);
await wait(0.6);

for (let i = 0; i < 8; i++) {
  const q = v.body.translation();
  const e = aimError({ x: q.x, y: q.y + 0.6, z: q.z });
  mouse(-e.yaw / SENS * 0.9, -e.pitch / SENS * 0.9);
  await wait(0.1);
}

const rays = [];
const rayHook = g.physics.raycast.bind(g.physics);
g.physics.raycast = (o, d, max, f, ex) => {
  const hit = rayHook(o, d, max, f, ex);
  if (rays.length < 12) {
    const q = v.body.translation();
    rays.push({
      originY: +o.y.toFixed(2), dirY: +d.y.toFixed(3), max,
      hit: hit ? +hit.distance.toFixed(1) : null,
      owner: hit ? (hit.owner ? (hit.owner.spec?.label ?? hit.owner.constructor?.name ?? 'obj') : 'static') : 'none',
      isQuarry: hit ? hit.owner === v : false,
      toQuarry: +Math.hypot(q.x - o.x, q.y - o.y, q.z - o.z).toFixed(1),
    });
  }
  return hit;
};

const hp0 = v.health;
const shots0 = g.weapons.shotsFired;
window.dispatchEvent(new MouseEvent('mousedown', { button: 0, bubbles: true }));
await wait(1.2);
window.dispatchEvent(new MouseEvent('mouseup', { button: 0, bubbles: true }));
await wait(0.3);
g.physics.raycast = rayHook;

const p = g.player.position;
const c = g.cameraRig.camera.getWorldPosition(g.player.position.clone());
const e = aimError({ x: v.position.x, y: v.position.y + 0.6, z: v.position.z });
const r = { shots: g.weapons.shotsFired - shots0, hp0, hp: v.health,
  aimYaw: +e.yaw.toFixed(4), aimPitch: +e.pitch.toFixed(4), range: +e.len.toFixed(1),
  playerY: +p.y.toFixed(2), camY: +c.y.toFixed(2),
  camBehind: +Math.hypot(c.x - p.x, c.z - p.z).toFixed(2),
  fwd: camFwd(), state: g.player.state, mag: g.weapons.magazine, rays };
g.missions.fail('diag done');
return r;
})()
