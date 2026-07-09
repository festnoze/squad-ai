// Full-stack integration gate for generated web/fullstack apps.
//
// Usage:
//   node runtime_acceptance.js <workspace> <timeoutMs> <frontendRoot|''> <backendWeb:0|1>
//
// Modes (picked from the arguments):
//   - backend + frontend  → INTEGRATED: build the frontend, boot the backend ALONE,
//     then verify the whole app at the BACKEND origin — the URL the user actually
//     opens. This is what catches a backend that mounts the build on a path the
//     index.html asset URLs don't match (SPA fallback silently swallowing /assets/*
//     as text/html → blank page), a dead API, or a broken backend↔database wiring.
//   - frontend only → vite preview + the same page-integrity checks.
//   - backend only  → boot + reachable page + API probe.

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
const BACKEND_PORT = Number(process.env.RUNTIME_BACKEND_PORT || 8000);
const FRONTEND_PORT = Number(process.env.RUNTIME_FRONTEND_PORT || 5174);

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

// Plain HTTP GET that never throws: connection errors → status 0.
function fetchText(url, timeoutMs = 8000) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      let body = "";
      res.on("data", (d) => {
        if (body.length < 65536) body += d.toString();
      });
      res.on("end", () => resolve({
        status: res.statusCode || 0,
        contentType: String(res.headers["content-type"] || ""),
        body,
      }));
    });
    req.on("error", () => resolve({ status: 0, contentType: "", body: "" }));
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      resolve({ status: 0, contentType: "", body: "" });
    });
  });
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
  const dist = path.join(FRONTEND, "dist", "index.html");
  if (!fs.existsSync(dist)) {
    throw new Error(`build frontend sans dist/index.html (${dist})`);
  }
}

async function startFrontendPreview() {
  const proc = launch("frontend", "npm", [
    "run", "preview", "--", "--host", "127.0.0.1", "--port", String(FRONTEND_PORT),
  ], FRONTEND);
  if (!(await waitForHttp(FRONTEND_PORT, remaining()))) {
    throw new Error(`frontend preview non joignable sur :${FRONTEND_PORT}\n${proc._autospecOutput()}`);
  }
  return `http://127.0.0.1:${FRONTEND_PORT}/`;
}

// API / database probe: drive real GET endpoints through the running backend.
// A 5xx here is the generic signature of broken wiring (router not registered,
// DB not initialised / migrations missing…) that unit tests with mocks never see.
async function probeApi(origin) {
  const notes = [];
  const spec = await fetchText(`${origin}/openapi.json`, Math.min(8000, remaining()));
  if (spec.status === 200) {
    let doc = null;
    try { doc = JSON.parse(spec.body); } catch {}
    const paths = doc && doc.paths ? Object.keys(doc.paths) : [];
    const candidates = paths
      .filter((p) => !p.includes("{") && doc.paths[p] && doc.paths[p].get)
      .slice(0, 3);
    for (const p of candidates) {
      const res = await fetchText(origin + p, Math.min(8000, remaining()));
      if (res.status >= 500 || res.status === 0) {
        throw new Error(
          `sonde API : GET ${p} → HTTP ${res.status || "aucune réponse"} — le backend répond ` +
          `mais l'endpoint casse à l'exécution (base de données non initialisée ? dépendance non câblée ?)\n` +
          res.body.slice(0, 400)
        );
      }
      notes.push(`GET ${p} → ${res.status}`);
    }
    if (!candidates.length) notes.push("openapi.json présent, aucun GET sans paramètre à sonder");
    return `sonde API OK (${notes.join(", ") || "openapi seul"})`;
  }
  for (const p of ["/api/health", "/health", "/api"]) {
    const res = await fetchText(origin + p, Math.min(5000, remaining()));
    if (res.status >= 500) {
      throw new Error(`sonde API : GET ${p} → HTTP ${res.status}\n${res.body.slice(0, 400)}`);
    }
    if (res.status && res.status < 500 && res.status !== 404) {
      return `sonde API OK (${p} → ${res.status})`;
    }
  }
  return "sonde API ignorée (pas d'openapi.json ni d'endpoint santé)";
}

// Load `target` in a real browser and require an actually-working app:
// assets resolved with the right MIME, JS executed (SPA root rendered),
// no failed requests, no console errors.
async function checkPage(browser, target, requireApp) {
  const page = await browser.newPage();
  const origin = new URL(target).origin;
  const problems = [];
  const browserErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") browserErrors.push(msg.text());
  });
  page.on("pageerror", (err) => browserErrors.push(String(err)));
  page.on("requestfailed", (req) => {
    problems.push(`requête échouée : ${req.method()} ${req.url()} (${(req.failure() || {}).errorText || "?"})`);
  });
  page.on("response", (res) => {
    let url;
    try { url = new URL(res.url()); } catch { return; }
    if (url.origin !== origin) return;
    const isJs = /\.m?js(\?.*)?$/i.test(url.pathname);
    const isCss = /\.css(\?.*)?$/i.test(url.pathname);
    if (!isJs && !isCss) return;
    const ct = String(res.headers()["content-type"] || "").toLowerCase();
    if (res.status() >= 400) {
      problems.push(`asset ${url.pathname} → HTTP ${res.status()} (le serveur ne sert pas cet asset du build)`);
    } else if (isJs && ct.includes("text/html")) {
      problems.push(
        `asset ${url.pathname} servi en text/html au lieu de javascript — le fallback SPA avale ` +
        `les assets : le chemin des assets du index.html (base vite) ne correspond pas au montage ` +
        `statique du backend (ex. build en base "/" mais montage sur "/static")`
      );
    }
  });

  const response = await page.goto(target, { waitUntil: "domcontentloaded", timeout: remaining() });
  const status = response ? response.status() : 0;
  if (requireApp && (!status || status >= 400)) {
    throw new Error(
      `HTTP ${status} sur ${target} — le backend ne sert pas le frontend buildé à la racine ` +
      `(montage statique de frontend/dist manquant ou fallback SPA absent ?)`
    );
  }
  if (!requireApp && (!status || status >= 500)) {
    throw new Error(`HTTP ${status} sur ${target}`);
  }

  // Let the SPA bundle execute and render before judging the DOM.
  await page.waitForTimeout(1500);
  const body = (await page.locator("body").innerText({ timeout: 5000 })).trim();
  if (requireApp) {
    if (!body) {
      problems.push("page sans aucun texte visible — le bundle JS ne s'exécute probablement pas");
    } else {
      const rootEmpty = await page.evaluate(() => {
        const root = document.querySelector("#root, #app");
        return root ? root.childElementCount === 0 && !root.textContent.trim() : false;
      });
      if (rootEmpty) {
        problems.push("le conteneur SPA (#root/#app) est resté vide — le bundle JS n'a pas rendu l'application");
      }
    }
  }
  if (/internal server error|vite error|failed to load/i.test(body)) {
    problems.push(`contenu runtime suspect : ${body.slice(0, 300)}`);
  }
  if (browserErrors.length) {
    problems.push(`erreurs navigateur : ${browserErrors.slice(0, 5).join(" | ")}`);
  }
  if (problems.length) {
    throw new Error(`intégration KO sur ${target} :\n- ${problems.join("\n- ")}`);
  }
  return body.length;
}

(async () => {
  let browser;
  try {
    runFrontendBuild();
    const backendUp = await startBackendIfNeeded();
    const backendOrigin = `http://127.0.0.1:${BACKEND_PORT}`;

    let target = "";
    let requireApp = false;
    if (backendUp && FRONTEND) {
      // Integrated fullstack: the deliverable is `python main.py` and the user
      // opens the backend port — so THAT origin must serve the working app.
      target = `${backendOrigin}/`;
      requireApp = true;
      record(`[runtime] mode INTÉGRÉ : frontend servi PAR le backend sur ${target}`);
    } else if (FRONTEND) {
      target = await startFrontendPreview();
      requireApp = true;
    } else if (backendUp) {
      target = `${backendOrigin}/`;
    }
    if (!target) throw new Error("aucune URL runtime à vérifier");

    if (backendUp) record(`[runtime] ${await probeApi(backendOrigin)}`);

    browser = await chromium.launch();
    const visible = await checkPage(browser, target, requireApp);
    record(`[runtime] OK ${target} (${visible} caractères visibles)`);
    process.exit(0);
  } catch (err) {
    record(`[runtime] FAIL ${err && err.stack ? err.stack : String(err)}`);
    process.exit(1);
  } finally {
    if (browser) await browser.close().catch(() => {});
    for (const proc of procs) killTree(proc);
  }
})();
