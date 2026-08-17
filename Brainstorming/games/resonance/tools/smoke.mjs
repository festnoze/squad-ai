/**
 * RESONANCE - headless smoke test over the Chrome DevTools protocol.
 *
 * Boots the game with the software renderer, waits for window.__ready by
 * polling (never a fixed delay: swiftshader runs under one frame per second),
 * starts a level, exercises placement / phase / undo / restart through
 * window.game, checks zero JS errors, and measures the average screen
 * luminance (readability threshold 25/255, measured, never eyeballed).
 *
 * Usage (static server already running):
 *     python -m http.server 8123   (from the resonance folder)
 *     node tools/smoke.mjs [url]
 */

import { spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SHOT_DIR = join(HERE, '..', '.smoke');
mkdirSync(SHOT_DIR, { recursive: true });

const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  (process.env.LOCALAPPDATA || '') + '\\Google\\Chrome\\Application\\chrome.exe',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
];
const CHROME = CHROME_CANDIDATES.find((p) => p && existsSync(p));
if (!CHROME) {
  console.error('Chrome introuvable.');
  process.exit(2);
}

const url = process.argv[2] || 'http://localhost:8123/index.html';
const port = 9500 + Math.floor(Date.now() % 300);
const profile = mkdtempSync(join(tmpdir(), 'resonance-smoke-'));

const chrome = spawn(CHROME, [
  '--headless=new',
  '--remote-debugging-port=' + port,
  '--user-data-dir=' + profile,
  '--no-first-run',
  '--no-default-browser-check',
  '--disable-extensions',
  '--mute-audio',
  '--window-size=1280,800',
  '--use-gl=angle',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--disable-gpu-sandbox',
  'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });
let chromeErr = '';
chrome.stderr.on('data', (d) => { chromeErr += d.toString(); });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function findTarget() {
  for (let i = 0; i < 80; i++) {
    try {
      const list = await (await fetch('http://127.0.0.1:' + port + '/json/list')).json();
      const page = list.find((t) => t.type === 'page');
      if (page && page.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch (err) { void err; }
    await sleep(250);
  }
  throw new Error('Pas de cible de debogage.\n' + chromeErr.slice(0, 600));
}

const ws = new WebSocket(await findTarget());
await new Promise((res, rej) => {
  ws.addEventListener('open', res, { once: true });
  ws.addEventListener('error', rej, { once: true });
});

let nextId = 1;
const pending = new Map();
const jsErrors = [];
ws.addEventListener('message', (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error)));
    else resolve(msg.result);
    return;
  }
  if (msg.method === 'Runtime.exceptionThrown') {
    const d = msg.params.exceptionDetails;
    jsErrors.push('[EXCEPTION] ' + ((d.exception && d.exception.description) || d.text));
  } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
    jsErrors.push('[console.error] ' + msg.params.args.map((a) => a.value || a.description).join(' '));
  }
});
function send(method, params) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params: params || {} }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}
async function evaluate(expression) {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) {
    const d = r.exceptionDetails;
    throw new Error('evaluate: ' + ((d.exception && d.exception.description) || d.text));
  }
  return r.result.value;
}

const results = [];
function check(label, ok, detail) {
  results.push({ ok: !!ok, label, detail: detail === undefined ? '' : String(detail) });
}

async function screenshot(name) {
  try {
    const s = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(join(SHOT_DIR, name + '.png'), Buffer.from(s.data, 'base64'));
  } catch (err) { void err; }
}

function finish() {
  const failed = results.filter((r) => !r.ok);
  console.log('\n===== RESONANCE, smoke test =====\n');
  for (const r of results) {
    console.log((r.ok ? '  ok    ' : '  ECHEC ') + r.label + (r.detail ? '  (' + r.detail + ')' : ''));
  }
  console.log('\n  ' + (results.length - failed.length) + ' / ' + results.length + ' verifications passees');
  console.log('  ' + jsErrors.length + ' erreur(s) JavaScript');
  for (const e of jsErrors.slice(0, 12)) console.log('    ' + e);
  try { ws.close(); } catch (err) { void err; }
  chrome.kill();
  process.exit(failed.length === 0 && jsErrors.length === 0 ? 0 : 1);
}

await send('Runtime.enable');
await send('Page.enable');
await send('Page.navigate', { url });

// Boot: poll for readiness, never a blind delay.
const boot = await evaluate(`(async()=>{
  const w=(ms)=>new Promise(r=>setTimeout(r,ms));
  for(let i=0;i<180 && !window.__ready;i++) await w(1000);
  if(!window.__ready) return 'TIMEOUT boot';
  localStorage.removeItem('resonance.progress');
  window.__t={ w, async until(fn, s){ const end=Date.now()+s*1000;
    while(Date.now()<end){ try{ if(fn()) return true; }catch(e){ void e; } await w(200); } return false; } };
  return 'ok mode=' + window.game.mode;
})()`);
check('demarrage (window.__ready)', boot.startsWith('ok'), boot);
if (!boot.startsWith('ok')) finish();

const errScreen = await evaluate(`document.getElementById('screen-error').classList.contains('hidden')`);
check('ecran d erreur cache', errScreen === true);

// Start playing.
const start = await evaluate(`(async()=>{
  document.getElementById('btn-play').click();
  const ok = await window.__t.until(()=>window.game.mode==='play', 30);
  return JSON.stringify({ok, mode:window.game.mode, level:window.game.levelIndex});
})()`).then(JSON.parse);
check('passage en jeu via JOUER', start.ok === true, 'mode=' + start.mode);

// Place a fork through the public hook; stock must drop, wave must gain a source.
const place = await evaluate(`(async()=>{
  const g=window.game;
  const stock0=g.board.stock[0];
  g.place(12, 10, 0);
  const fork=g.board.forkAt(12,10);
  return JSON.stringify({stock0, stock1:g.board.stock[0], fork:!!fork, poses:g.board.poses});
})()`).then(JSON.parse);
check('pose d un diapason', place.fork === true && place.stock1 === place.stock0 - 1,
  `stock ${place.stock0}->${place.stock1}, poses=${place.poses}`);

// Phase turn + refusal feedback on an occupied slot (legal actions always run,
// impossible ones are refused with feedback, never silently).
const rules = await evaluate(`(async()=>{
  const g=window.game;
  const f=g.board.forkAt(12,10);
  g.board.setPhase(f, f.phase+1);
  const phase=f.phase;
  const refuse=g.board.place(12,10,0,0);
  return JSON.stringify({phase, refused:!refuse.ok, reason:refuse.reason||''});
})()`).then(JSON.parse);
check('changement de phase', rules.phase === 1);
check('refus motive sur case occupee', rules.refused === true, rules.reason);

// Undo restores the stock.
const undo = await evaluate(`(async()=>{
  const g=window.game;
  g.undo();
  return JSON.stringify({fork:!!g.board.forkAt(12,10), stock:g.board.stock[0]});
})()`).then(JSON.parse);
check('annulation (Ctrl+Z)', undo.fork === false && undo.stock === place.stock0,
  'stock=' + undo.stock);

// Restart, re-place, fast-forward the deterministic sim so the measure sees
// normal play (waves visibly propagating), then read the framebuffer.
const lum = await evaluate(`(async()=>{
  const g=window.game;
  g.restart();
  g.place(12, 10, 0);
  for(let i=0;i<150;i++){ g.wave.step(); g.board.tick(); }
  const v = await g.measureLuminance();
  return JSON.stringify({lum:+v.toFixed(1)});
})()`).then(JSON.parse);
check('luminance moyenne >= 25/255 en jeu', lum.lum >= 25, lum.lum + '/255');
await screenshot('jeu');

// Level navigation hook.
const nav = await evaluate(`(async()=>{
  const g=window.game;
  g.loadLevel(3);
  return JSON.stringify({idx:g.levelIndex, walls:(g.levels[3].walls||[]).length,
    crystals:g.board.crystals.length});
})()`).then(JSON.parse);
check('chargement direct d un niveau a parois', nav.idx === 3 && nav.crystals === 1,
  JSON.stringify(nav));
await screenshot('niveau-echo');

finish();
