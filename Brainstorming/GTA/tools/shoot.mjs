/**
 * Screenshot / smoke-test harness.
 *
 * Launches the bundled Chromium against the dev server, waits for the game to finish
 * booting, optionally repositions the camera, and reports console errors alongside a
 * screenshot. This is the project's verification loop: every visual change gets checked
 * here rather than by eyeballing a dev server by hand.
 *
 * Usage:
 *   node tools/shoot.mjs --out shots/city.png --shot aerial
 *   node tools/shoot.mjs --webgl --shot street --time 20.5
 *   node tools/shoot.mjs --shot list          # print available shots
 *
 * WebGPU is the default. Pass --webgl to force the WebGL2 backend; headless Chromium
 * composites WebGL far more reliably for capture.
 */

import { chromium } from 'playwright-core';
import { mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { existsSync } from 'node:fs';

const CHROME_CANDIDATES = [
  'C:/Users/e.millerioux/AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe',
  'C:/Users/e.millerioux/AppData/Local/ms-playwright/chromium-1194/chrome-win64/chrome.exe',
];

/** Camera setups. Each returns a function evaluated in the page. */
const SHOTS = {
  /** Default third-person view from wherever the player spawned. */
  street: () => {
    const g = window.game;
    g.cameraRig.pitch = -0.14;
    g.cameraRig.yaw = 0.6;
    g.cameraRig.distanceScale = 1.3;
  },
  /** High oblique over downtown - judges skyline variety. */
  aerial: () => {
    const g = window.game;
    g.freeCam.enable(g.cameraRig.camera);
    g.freeCam.position.set(420, 300, 420);
    g.freeCam.yaw = Math.PI * 1.25;
    g.freeCam.pitch = -0.52;
  },
  /** Low angle down an avenue - judges street-level detail and traffic. */
  avenue: () => {
    const g = window.game;
    g.freeCam.enable(g.cameraRig.camera);
    g.freeCam.position.set(6, 5.5, -120);
    g.freeCam.yaw = 0;
    g.freeCam.pitch = -0.07;
  },
  /** Close on the player's starter car. */
  car: () => {
    const g = window.game;
    const car = g.starterCar ?? g.traffic.vehicles[0];
    const p = car.position;
    g.freeCam.enable(g.cameraRig.camera);
    g.freeCam.position.set(p.x + 6.5, p.y + 2.6, p.z + 6.5);
    g.freeCam.yaw = Math.PI * 1.25;
    g.freeCam.pitch = -0.28;
  },
  /** Suburbs - judges houses, gardens and trees. */
  suburb: () => {
    const g = window.game;
    g.freeCam.enable(g.cameraRig.camera);
    g.freeCam.position.set(700, 70, 700);
    g.freeCam.yaw = Math.PI * 1.25;
    g.freeCam.pitch = -0.42;
  },
  /** The harbour: docks, moored boats and open water. */
  bay: () => {
    const g = window.game;
    const bay = g.island.bay;
    g.freeCam.enable(g.cameraRig.camera);
    g.freeCam.position.set(bay.x - 260, 95, bay.z - 260);
    g.freeCam.yaw = Math.PI * 0.25;
    g.freeCam.pitch = -0.34;
  },
  /** Water level, next to a moored boat. */
  boat: () => {
    const g = window.game;
    const b = g.boats[0];
    const p = b.position;
    g.freeCam.enable(g.cameraRig.camera);
    g.freeCam.position.set(p.x + 9, p.y + 3.4, p.z + 9);
    g.freeCam.yaw = Math.PI * 1.25;
    g.freeCam.pitch = -0.22;
  },
  /** Looking up from the street - judges the sky gradient and sun. */
  skyview: () => {
    const g = window.game;
    g.freeCam.enable(g.cameraRig.camera);
    g.freeCam.position.set(0, 30, 0);
    g.freeCam.yaw = Math.PI * 0.5;
    g.freeCam.pitch = 0.42;
  },
  /** Docks / industrial edge. */
  docks: () => {
    const g = window.game;
    g.freeCam.enable(g.cameraRig.camera);
    g.freeCam.position.set(-980, 90, -980);
    g.freeCam.yaw = Math.PI * 0.25;
    g.freeCam.pitch = -0.38;
  },
};

function parseArgs(argv) {
  const args = { out: 'shots/shot.png', shot: 'street', webgl: false, time: null, wait: 2.5, post: true, url: null, width: 1600, height: 900 };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--webgl') args.webgl = true;
    else if (a === '--no-post') args.post = false;
    else if (a === '--out') args.out = argv[++i];
    else if (a === '--shot') args.shot = argv[++i];
    else if (a === '--time') args.time = Number(argv[++i]);
    else if (a === '--wait') args.wait = Number(argv[++i]);
    else if (a === '--url') args.url = argv[++i];
    else if (a === '--width') args.width = Number(argv[++i]);
    else if (a === '--height') args.height = Number(argv[++i]);
    // Arbitrary page-side code, evaluated after the shot is set up. For one-off probes.
    else if (a === '--js') args.js = argv[++i];
  }
  return args;
}

const args = parseArgs(process.argv);

if (args.shot === 'list') {
  console.log('Available shots:', Object.keys(SHOTS).join(', '));
  process.exit(0);
}
if (!SHOTS[args.shot]) {
  console.error(`Unknown shot "${args.shot}". Available: ${Object.keys(SHOTS).join(', ')}`);
  process.exit(1);
}

const executablePath = CHROME_CANDIDATES.find((p) => existsSync(p));
if (!executablePath) {
  console.error('No Chromium found. Run `npx playwright install chromium`.');
  process.exit(1);
}

const url = args.url ?? `http://localhost:8092/${buildQuery(args)}`;

function buildQuery(a) {
  const q = new URLSearchParams();
  if (a.webgl) q.set('webgl', '1');
  if (!a.post) q.set('post', 'off');
  const s = q.toString();
  return s ? `?${s}` : '';
}

const browser = await chromium.launch({
  executablePath,
  headless: true,
  args: [
    // Headless Chromium needs to be told explicitly to expose a GPU backend.
    '--enable-unsafe-webgpu',
    '--enable-features=Vulkan,UseSkiaRenderer',
    '--use-angle=default',
    '--ignore-gpu-blocklist',
    '--enable-gpu-rasterization',
  ],
});

const page = await browser.newPage({ viewport: { width: args.width, height: args.height } });

/** @type {string[]} */
const errors = [];
const warnings = [];
page.on('console', (msg) => {
  const type = msg.type();
  const text = msg.text();
  if (type === 'error') errors.push(text);
  else if (type === 'warning' && !/deprecated|powerPreference|renamed to/i.test(text)) warnings.push(text);
});
page.on('pageerror', (err) => errors.push(`PAGEERROR: ${err.message}`));

console.log(`-> ${url}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });

// Wait for boot: `window.game.engine.stats.fps` only becomes non-zero once the render
// loop has been running for half a second, which is exactly the signal we want.
const booted = await page.waitForFunction(
  () => {
    const g = window.game;
    if (g?.engine?.stats?.fps > 0) return { ok: true };
    const status = document.getElementById('loading-status');
    if (status && status.style.color) return { ok: false, error: status.textContent };
    return false;
  },
  null,
  { timeout: 120000 },
).then((h) => h.jsonValue()).catch((e) => ({ ok: false, error: `boot timeout: ${e.message}` }));

if (!booted.ok) {
  console.error('BOOT FAILED:', booted.error);
  for (const e of errors) console.error('  console:', e);
  await browser.close();
  process.exit(1);
}

if (args.time !== null) {
  await page.evaluate((t) => {
    window.game.atmosphere.timeOfDay = t;
    window.game.atmosphere.paused = true;
    window.game.atmosphere._envDirtyAt = -999;
  }, args.time);
}

await page.evaluate(SHOTS[args.shot]);
if (args.js) {
  const probe = await page.evaluate(args.js);
  if (probe !== undefined) console.log('js:', JSON.stringify(probe));
}
// Let the camera settle, shadows re-render and the environment rebake.
await page.waitForTimeout(args.wait * 1000);

const stats = await page.evaluate(() => {
  const g = window.game;
  return {
    backend: g.engine.backend,
    fps: g.engine.stats.fps,
    ms: g.engine.stats.ms,
    draws: g.engine.stats.drawCalls,
    tris: g.engine.stats.triangles,
    buildings: g.city.buildingBoxes.length,
    parks: g.city.parks.length,
    vehicles: g.traffic?.count ?? 0,
    traffic: g.traffic?.trafficCount ?? 0,
    post: g.postfx.enabled ? g.postfx.quality : 'off',
    clock: g.atmosphere.clockString(),
    moveKeys: g.input.moveKeysLabel,
  };
});

const outPath = resolve(args.out);
await mkdir(dirname(outPath), { recursive: true });
await page.screenshot({ path: outPath });

console.log('stats:', JSON.stringify(stats, null, 2));
console.log(`errors: ${errors.length}, warnings: ${warnings.length}`);
for (const e of errors.slice(0, 15)) console.log('  ERROR:', e);
for (const w of warnings.slice(0, 10)) console.log('  WARN :', w);
console.log(`saved ${outPath}`);

await browser.close();
process.exit(errors.length ? 2 : 0);
