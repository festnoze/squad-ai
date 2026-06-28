// Generic runtime acceptance gate for generated web/fullstack apps.
//
// Usage:
//   node runtime_acceptance.js <workspace> <timeoutMs> <frontendRoot|''> <backendWeb:0|1>

const fs = require("fs");
const http = require("http");
const path = require("path");
const { spawnSync, spawn } = require("child_process");

let chromium;
try {
  chromium = require("playwright").chromium;
} catch {
  chromium = require("@playwright/test").chromium;
}

const WS = process.argv[2];
const TIMEOUT = Number(process.argv[3] || 90000);
const FRONTEND = process.argv[4] || "";
const BACKEND_WEB = process.argv[5] === "1";
const BACKEND_PORT = Number(process.env.AUTOSPEC_RUNTIME_BACKEND_PORT || 8000);
const FRONTEND_PORT = Number(process.env.AUTOSPEC_RUNTIME_FRONTEND_PORT || 5174);

const procs = [];
const startedAt = Date.now();

function remaining(min = 1000) {
  return Math.max(min, TIMEOUT - (Date.now() - startedAt));
}

function record(line) {
  console.log(line);
}

function killTree(proc) {
  if (!proc || proc.killed) return;
  try {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/PID", String(proc.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      proc.kill("SIGTERM");
    }
  } catch {
    try { proc.kill(); } catch {}
  }
}

function launch(label, cmd, args, cwd) {
  record(`[runtime] launch ${label}: ${cmd} ${args.join(" ")}`);
  const proc = spawn(cmd, args, {
    cwd,
    shell: process.platform === "win32",
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  proc.stdout.on("data", (d) => { output += d.toString(); });
  proc.stderr.on("data", (d) => { output += d.toString(); });
  proc._autospecLabel = label;
  proc._autospecOutput = () => output.slice(-2000);
  procs.push(proc);
  return proc;
}

function waitForHttp(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve) => {
    const tick = () => {
      const req = http.get(`http://127.0.0.1:${port}/`, (res) => {
        res.resume();
        resolve(res.statusCode && res.statusCode < 500);
      });
      req.on("error", () => {
        if (Date.now() > deadline) return resolve(false);
        setTimeout(tick, 500);
      });
      req.setTimeout(1500, () => {
        req.destroy();
        if (Date.now() > deadline) return resolve(false);
        setTimeout(tick, 500);
      });
    };
    tick();
  });
}

async function startBackendIfNeeded() {
  if (!BACKEND_WEB) return false;
  const main = path.join(WS, "main.py");
  if (!fs.existsSync(main)) throw new Error("backend web demandé mais main.py absent");

  let proc = launch("backend", "uv", ["run", "python", "main.py"], WS);
  if (await waitForHttp(BACKEND_PORT, Math.min(12000, remaining()))) return true;

  record("[runtime] python main.py n'a pas ouvert le port, essai uvicorn main:app");
  killTree(proc);
  proc = launch("backend-uvicorn", "uv", [
    "run", "--with", "uvicorn", "uvicorn", "main:app",
    "--host", "127.0.0.1", "--port", String(BACKEND_PORT),
  ], WS);
  if (await waitForHttp(BACKEND_PORT, remaining())) return true;
  throw new Error(`backend web non joignable sur :${BACKEND_PORT}\n${proc._autospecOutput()}`);
}

function runFrontendBuild() {
  if (!FRONTEND) return;
  record("[runtime] npm run build (frontend)");
  const res = spawnSync("npm", ["run", "build"], {
    cwd: FRONTEND,
    shell: process.platform === "win32",
    encoding: "utf8",
    timeout: remaining(),
  });
  if (res.status !== 0) {
    throw new Error(`build frontend échoué\n${(res.stdout || "")}${(res.stderr || "")}`.slice(-3000));
  }
}

async function startFrontendIfNeeded() {
  if (!FRONTEND) return "";
  runFrontendBuild();
  const proc = launch("frontend", "npm", [
    "run", "preview", "--", "--host", "127.0.0.1", "--port", String(FRONTEND_PORT),
  ], FRONTEND);
  if (!(await waitForHttp(FRONTEND_PORT, remaining()))) {
    throw new Error(`frontend preview non joignable sur :${FRONTEND_PORT}\n${proc._autospecOutput()}`);
  }
  return `http://127.0.0.1:${FRONTEND_PORT}/`;
}

(async () => {
  let browser;
  try {
    const backendUp = await startBackendIfNeeded();
    const frontendUrl = await startFrontendIfNeeded();
    const target = frontendUrl || (backendUp ? `http://127.0.0.1:${BACKEND_PORT}/` : "");
    if (!target) throw new Error("aucune URL runtime à vérifier");

    browser = await chromium.launch();
    const page = await browser.newPage();
    const browserErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") browserErrors.push(msg.text());
    });
    page.on("pageerror", (err) => browserErrors.push(String(err)));
    const response = await page.goto(target, { waitUntil: "domcontentloaded", timeout: remaining() });
    const status = response ? response.status() : 0;
    const body = (await page.locator("body").innerText({ timeout: 5000 })).trim();
    if (!status || status >= 500) throw new Error(`HTTP ${status} sur ${target}`);
    if (!body) throw new Error(`page vide sur ${target}`);
    if (/internal server error|vite error|failed to load/i.test(body)) {
      throw new Error(`contenu runtime suspect : ${body.slice(0, 300)}`);
    }
    if (browserErrors.length) {
      throw new Error(`erreurs navigateur : ${browserErrors.slice(0, 5).join(" | ")}`);
    }
    record(`[runtime] OK ${target} (${body.length} caractères visibles)`);
    process.exit(0);
  } catch (err) {
    record(`[runtime] FAIL ${err && err.stack ? err.stack : String(err)}`);
    process.exit(1);
  } finally {
    if (browser) await browser.close().catch(() => {});
    for (const proc of procs) killTree(proc);
  }
})();
