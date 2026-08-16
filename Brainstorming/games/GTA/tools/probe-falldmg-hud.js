/*
 * Capture aid for the fall-damage task: leave the player treading water with the breath
 * meter low, so the screenshot shows the bar in its red pulsing state next to health and
 * armour. No assertions - tools/probe-falldmg.js is the test.
 */
(async () => {
const g = window.game, E = g.engine;
const T0 = performance.now();
let simT = 0; E.fixedCallbacks.push((dt) => { simT += dt; });
const wait = async (sec) => { const t = simT + sec;
  while (simT < t && performance.now() - T0 < 120000) await new Promise(r => requestAnimationFrame(r)); };

g.wanted.clear();
g.player.armour = 55;
g.player.health = 100;

let deep = null;
for (let r = g.island.radius + 140; r < g.island.radius + 700 && !deep; r += 60) {
  for (let a = 0; a < 6.28 && !deep; a += 0.4) {
    const x = Math.cos(a) * r, z = Math.sin(a) * r;
    if (g.island.landField(x, z) < -120) deep = { x, z };
  }
}
g.player.teleport({ x: deep.x, y: g.ocean.heightAt(deep.x, deep.z) - 1.2, z: deep.z });
// 13 s here plus the 3 s settle before the shutter is 16 s of the 20 s bar, so the meter
// sits at 20% and is already in its red pulsing state. The `street` shot leaves the rig
// following the player, so the frame lands on the swimmer without touching the camera.
await wait(13);

return { breathPercent: Math.round(g.player.breath01 * 100), health: g.player.health,
  swimming: g.player.isSwimming,
  barWidth: document.getElementById('bar-breath')?.style.width ?? null };
})()
