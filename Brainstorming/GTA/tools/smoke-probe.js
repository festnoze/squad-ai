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

const m = g.missions.missions.find(x => x.state === 'available');
g.missions.start(m); await wait(1);
ok('mission starts', g.missions.active === m, m.name);
ok('mission gives an objective', !!g.missions.currentObjective, g.missions.statusLine);

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
