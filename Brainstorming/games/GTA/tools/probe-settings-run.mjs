/**
 * Acceptance runner for task 12 (persisted settings).
 *
 * tools/shoot.mjs evaluates one script against one document, which cannot prove "the
 * choices survive a reload" - a page-side script dies with its document. This runner boots
 * the game, evaluates tools/probe-settings.js (phase 1: drive the pause menu, write the
 * preferences), performs a real `page.reload()`, waits for the second boot, then evaluates
 * the same file again (phase 2: assert everything came back before the first frame).
 *
 * An earlier version of the probe booted the second document in a same-origin iframe. That
 * measured the right thing but killed the renderer process every time: two 2.7M triangle
 * cities with their own physics worlds in one tab is more than headless Chromium survives.
 *
 * Console errors are collected across BOTH loads and reported the way shoot.mjs does, so
 * the pass criterion ("errors: 0") reads identically.
 *
 * Usage:
 *   node tools/probe-settings-run.mjs [--out shots/probe-settings.png] [--webgl]
 */

import { chromium } from 'playwright-core';
import { mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { existsSync, readFileSync } from 'node:fs';

const CHROME_CANDIDATES = [
  'C:/Users/e.millerioux/AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe',
  'C:/Users/e.millerioux/AppData/Local/ms-playwright/chromium-1194/chrome-win64/chrome.exe',
];

const args = { out: 'shots/probe-settings.png', webgl: false, base: 'http://localhost:8092/' };
for (let i = 2; i < process.argv.length; i++) {
  const a = process.argv[i];
  if (a === '--out') args.out = process.argv[++i];
  else if (a === '--webgl') args.webgl = true;
  else if (a === '--base') args.base = process.argv[++i];
  else { console.error(`Unknown argument "${a}".`); process.exit(2); }
}

const executablePath = CHROME_CANDIDATES.find((p) => existsSync(p));
if (!executablePath) {
  console.error('No Chromium found. Run `npx playwright install chromium`.');
  process.exit(1);
}

/*
 * No `quality`, `post` or `webgl` parameter: whatever the second boot ends up with can only
 * have come out of localStorage. `hwtraffic=0` is not a persisted setting, it just keeps
 * two consecutive boots of a heavy scene inside a sane wall clock.
 */
const url = `${args.base}?hwtraffic=0${args.webgl ? '&webgl=1' : ''}`;
const probeSource = readFileSync(new URL('./probe-settings.js', import.meta.url), 'utf8');

const browser = await chromium.launch({
  executablePath,
  headless: true,
  args: [
    '--enable-unsafe-webgpu',
    '--enable-features=Vulkan,UseSkiaRenderer',
    '--use-angle=default',
    '--ignore-gpu-blocklist',
    '--enable-gpu-rasterization',
  ],
});

const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });

const errors = [];
const warnings = [];
page.on('console', (msg) => {
  const type = msg.type();
  const text = msg.text();
  if (type === 'error') errors.push(text);
  else if (type === 'warning' && !/deprecated|powerPreference|renamed to/i.test(text)) warnings.push(text);
});
page.on('pageerror', (err) => errors.push(`PAGEERROR: ${err.message}`));
page.on('crash', () => errors.push('PAGE CRASHED'));

/** Same boot signal shoot.mjs uses: fps only goes non-zero after half a second of loop. */
async function aWaitForBoot(label) {
  const booted = await page.waitForFunction(
    () => {
      const g = window.game;
      if (g?.engine?.stats?.fps > 0) return { ok: true };
      const status = document.getElementById('loading-status');
      if (status && status.style.color) return { ok: false, error: status.textContent };
      return false;
    },
    null,
    { timeout: 180000 },
  ).then((h) => h.jsonValue()).catch((e) => ({ ok: false, error: `boot timeout: ${e.message}` }));
  if (!booted.ok) {
    console.error(`BOOT FAILED (${label}):`, booted.error);
    for (const e of errors) console.error('  console:', e);
    await browser.close();
    process.exit(1);
  }
}

console.log(`-> ${url}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
await aWaitForBoot('first load');
const phase1 = await page.evaluate(probeSource);
console.log('js phase 1:', JSON.stringify(phase1));

console.log('-> reload');
await page.reload({ waitUntil: 'domcontentloaded' });
await aWaitForBoot('after reload');
const phase2 = await page.evaluate(probeSource);
console.log('js phase 2:', JSON.stringify(phase2));

// One merged line in the shape every other probe in this project reports.
const merged = {
  passed: (phase1.passed ?? 0) + (phase2.passed ?? 0),
  total: (phase1.total ?? 0) + (phase2.total ?? 0),
  before: phase1.before, chosen: phase1.chosen, after: phase2.after,
  failures: [...(phase1.failures ?? []), ...(phase2.failures ?? [])],
};
console.log('js:', JSON.stringify(merged));

const stats = await page.evaluate(() => {
  const g = window.game;
  return {
    backend: g.engine.backend,
    fps: g.engine.stats.fps,
    post: g.postfx.enabled ? g.postfx.quality : 'off',
    quality: g.postfx.quality,
    resolutionScale: g.engine.resolutionScale,
    volume: g.audio.volume,
    canvas: `${g.engine.renderer.domElement.width}x${g.engine.renderer.domElement.height}`,
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
process.exit(errors.length || merged.failures.length ? 2 : 0);
