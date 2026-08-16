/**
 * Luminance statistics for a screenshot.
 *
 * "It looks too dark" and "it looks better now" are not measurements, and lighting is
 * exactly the kind of change where the eye adapts between the before and the after. This
 * decodes a PNG (in Chromium, which already ships with the toolchain) and reports how much
 * of the frame is actually near-black, so a lighting change can be judged on numbers.
 *
 * The HUD overlay is excluded by ignoring the top-left stats block and the bottom strip,
 * otherwise bright white text skews the histogram of a dark scene.
 *
 *   node tools/luma.mjs shots/avenue.png [more.png ...]
 */

import { chromium } from 'playwright-core';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
];

const files = process.argv.slice(2);
if (!files.length) {
  console.error('usage: node tools/luma.mjs <png> [png ...]');
  process.exit(2);
}

const executablePath = CHROME_CANDIDATES.find((p) => existsSync(p));
const browser = await chromium.launch(executablePath ? { executablePath, headless: true } : { headless: true });
const page = await browser.newPage();

const rows = [];
for (const file of files) {
  const path = resolve(file);
  if (!existsSync(path)) { console.error(`missing: ${file}`); continue; }
  const dataUri = `data:image/png;base64,${readFileSync(path).toString('base64')}`;

  const stats = await page.evaluate(async (uri) => {
    const img = new Image();
    img.src = uri;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(img, 0, 0);
    const { data } = ctx.getImageData(0, 0, c.width, c.height);

    // Skip the stats overlay (top-left) and the HUD strip along the bottom.
    const skipX = c.width * 0.22, skipY = c.height * 0.36, hudY = c.height * 0.9;
    const lum = [];
    for (let y = 0; y < c.height; y += 2) {
      if (y > hudY) break;
      for (let x = 0; x < c.width; x += 2) {
        if (x < skipX && y < skipY) continue;
        const o = (y * c.width + x) * 4;
        // Rec. 709 luma on the sRGB values, which is what the eye is judging.
        lum.push(0.2126 * data[o] + 0.7152 * data[o + 1] + 0.0722 * data[o + 2]);
      }
    }
    lum.sort((a, b) => a - b);
    const at = (q) => lum[Math.floor((lum.length - 1) * q)];
    const below = (t) => lum.filter((v) => v < t).length / lum.length;
    return {
      samples: lum.length,
      mean: lum.reduce((a, b) => a + b, 0) / lum.length,
      p10: at(0.10), p50: at(0.50), p90: at(0.90),
      nearBlack: below(16),
      veryDark: below(40),
    };
  }, dataUri);

  rows.push({ file, ...stats });
}

await browser.close();

const pct = (v) => `${(v * 100).toFixed(1)}%`;
console.log('file'.padEnd(34), 'mean'.padStart(6), 'p10'.padStart(6), 'p50'.padStart(6),
  'p90'.padStart(6), '<16'.padStart(7), '<40'.padStart(7));
for (const r of rows) {
  console.log(
    r.file.padEnd(34),
    r.mean.toFixed(1).padStart(6), r.p10.toFixed(1).padStart(6),
    r.p50.toFixed(1).padStart(6), r.p90.toFixed(1).padStart(6),
    pct(r.nearBlack).padStart(7), pct(r.veryDark).padStart(7),
  );
}
