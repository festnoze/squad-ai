// End-to-end acceptance check of a generated server-rendered web app.
//
// Launches the built app (`uv run python main.py`) in its workspace, waits for
// the HTTP port, then drives it with Playwright and asserts the project's
// acceptance criteria. Tears the app down at the end. Exits 0 iff all pass.
//
// Usage: NODE_PATH=<frontend>/node_modules node verify_app.js <workspaceDir> [port]
const { chromium } = require('playwright');
const { spawnSync, spawn } = require('child_process');
const http = require('http');
const fs = require('fs');
const path = require('path');

const WS = process.argv[2];
let PORT = parseInt(process.argv[3] || '8099', 10);
const BASE = () => `http://127.0.0.1:${PORT}`;

function log(...a) { console.log(...a); }

// Tolerant matcher for "Compteur : N" (whitespace/levels may vary).
const countRe = (n) => new RegExp(`Compteur\\s*:?\\s*${n}\\b`, 'i');

function waitForPort(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve) => {
    const tick = () => {
      const req = http.get(BASE() + '/', (res) => { res.resume(); resolve(true); });
      req.on('error', () => {
        if (Date.now() > deadline) return resolve(false);
        setTimeout(tick, 1000);
      });
    };
    tick();
  });
}

(async () => {
  const results = [];
  const record = (name, ok, detail = '') => { results.push({ name, ok, detail }); log(`  [${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ' — ' + detail : ''}`); };

  // Fresh DB so criterion 1 (starts at 0) is meaningful.
  for (const f of fs.readdirSync(WS)) {
    if (f.endsWith('.db') || f.endsWith('.sqlite') || f.endsWith('.sqlite3')) {
      try { fs.unlinkSync(path.join(WS, f)); } catch {}
    }
  }

  log(`Launching app in ${WS} → ${BASE()}`);

  // Serve the generated FastAPI ASGI app via uvicorn on a known port. `--with
  // uvicorn` supplies the server even when the project didn't declare it as a
  // dependency, so we exercise the real generated routes/render/persistence.
  const app = spawn(
    'uv',
    ['run', '--with', 'uvicorn', 'uvicorn', 'main:app',
      '--host', '127.0.0.1', '--port', String(PORT)],
    { cwd: WS, shell: true },
  );
  let appOut = '';
  app.stdout.on('data', (d) => { appOut += d; });
  app.stderr.on('data', (d) => { appOut += d; });

  let browser;
  try {
    const up = await waitForPort(150000); // first `uv run` installs deps
    record('app starts and serves HTTP', up, up ? BASE() : 'port never opened\n' + appOut.slice(-500));
    if (!up) throw new Error('app did not start');

    browser = await chromium.launch();
    const page = await browser.newPage();

    // Criterion 1: home shows Compteur : 0
    await page.goto(BASE() + '/', { waitUntil: 'domcontentloaded' });
    let body = await page.textContent('body');
    record('AC1: home shows "Compteur : 0"', countRe(0).test(body), JSON.stringify((body || '').trim().slice(0, 80)));

    // Criterion 2: click Incrémenter → Compteur : 1
    const btn = page.locator('button:has-text("Incrémenter"), input[type=submit]').first();
    await btn.click();
    await page.waitForLoadState('domcontentloaded');
    body = await page.textContent('body');
    record('AC2: after increment shows "Compteur : 1"', countRe(1).test(body), JSON.stringify((body || '').trim().slice(0, 80)));

    // Criterion 3: reload persists the value
    await page.reload({ waitUntil: 'domcontentloaded' });
    body = await page.textContent('body');
    record('AC3: value persists after reload (Compteur : 1)', countRe(1).test(body), JSON.stringify((body || '').trim().slice(0, 80)));
  } catch (e) {
    record('exception', false, String(e));
  } finally {
    if (browser) await browser.close();
    // Kill the whole process tree (uv → python → uvicorn).
    try { spawnSync('taskkill', ['/PID', String(app.pid), '/T', '/F'], { stdio: 'ignore' }); } catch {}
  }

  const allPass = results.length > 0 && results.every((r) => r.ok);
  log('\n=== ACCEPTANCE RESULT ===');
  log(JSON.stringify({ allPass, results }, null, 2));
  process.exit(allPass ? 0 : 1);
})();
