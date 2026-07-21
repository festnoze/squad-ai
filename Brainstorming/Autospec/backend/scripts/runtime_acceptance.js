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
//
// Exit-code contract (the Python side branches on these):
//   0 = pass (integration OK).
//   1 = integration/CODE failure — repairable (blank page, wrong asset MIME,
//       app HTTP 4xx/5xx, broken API probe, empty #root, console errors,
//       journey click producing a 5xx).
//   2 = INFRA/ENVIRONMENT failure — NOT repairable (playwright/chromium absent
//       or unlaunchable, npm/node missing, build tool absent, or the target
//       backend port already occupied by an EXTERNAL process the gate did not
//       spawn). Printed as `[runtime] INFRA <reason>`; code failures as
//       `[runtime] FAIL <reason>`.
//
// Env: RUNTIME_BACKEND_PORT, RUNTIME_FRONTEND_PORT, RUNTIME_JOURNEY (when
// non-empty, run a best-effort write-path interaction after integrity checks).

const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");
const { spawnSync, spawn } = require("child_process");

// Infra/environment error marker. Errors carrying `.infra === true` are NOT
// repairable by the Python side → exit code 2. Everything else = code failure
// (exit 1). See the shared exit-code contract in the header/README.
class InfraError extends Error {
  constructor(message) {
    super(message);
    this.name = "InfraError";
    this.infra = true;
  }
}

// Resolve chromium from either playwright package. A missing package here is an
// ENVIRONMENT problem (playwright/chromium not installed), not a code failure.
let chromium;
try {
  chromium = require("playwright").chromium;
} catch {
  try {
    chromium = require("@playwright/test").chromium;
  } catch {
    chromium = null;
  }
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

// D10a (run supervisé 2026-07-20) : avec `shell: true` (win32), proc.pid est
// celui du SHELL et `taskkill /T` peut rater un descendant re-parenté (uv run →
// python orphelin restant à l'écoute). Filet final : tuer tout process qui
// écoute encore sur `port` ET dont la ligne de commande pointe dans le
// workspace — jamais un tiers. Best-effort, ne lève jamais.
function reapWorkspacePortHolders(port) {
  try {
    const needle = String(WS).toLowerCase();
    if (process.platform === "win32") {
      const script =
        `$l = Get-NetTCPConnection -LocalPort ${Number(port)} -State Listen ` +
        `-ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; ` +
        `foreach ($p in $l) { $ci = Get-CimInstance Win32_Process -Filter "ProcessId=$p" ` +
        `-ErrorAction SilentlyContinue; if ($ci -and $ci.CommandLine -and ` +
        `$ci.CommandLine.ToLower().Contains('${needle.replace(/'/g, "''")}')) { ` +
        `taskkill /PID $p /T /F | Out-Null } }`;
      spawnSync("powershell", ["-NoProfile", "-Command", script], { stdio: "ignore", timeout: 20000 });
    } else {
      const lsof = spawnSync("lsof", ["-ti", `tcp:${Number(port)}`, "-sTCP:LISTEN"], {
        encoding: "utf8", timeout: 15000,
      });
      for (const pid of String(lsof.stdout || "").split(/\s+/).filter(Boolean)) {
        const ps = spawnSync("ps", ["-o", "command=", "-p", pid], { encoding: "utf8", timeout: 10000 });
        if (String(ps.stdout || "").toLowerCase().includes(needle)) {
          spawnSync("kill", ["-9", pid], { stdio: "ignore", timeout: 10000 });
        }
      }
    }
  } catch {
    /* le nettoyage ne doit jamais faire échouer le gate */
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

// Resolve `true` if NOTHING is listening on the port (a fresh connection is
// refused), `false` if a server is already accepting connections there.
function isPortFree(port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let settled = false;
    const done = (free) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(free);
    };
    socket.setTimeout(1500);
    socket.once("connect", () => done(false)); // someone answered → occupied
    socket.once("timeout", () => done(true));
    socket.once("error", () => done(true)); // ECONNREFUSED → free
    socket.connect(port, "127.0.0.1");
  });
}

async function startBackendIfNeeded() {
  if (!BACKEND_WEB) return false;
  const main = path.join(WS, "main.py");
  if (!fs.existsSync(main)) throw new Error("backend web demandé mais main.py absent");

  // Guard against validating a STALE/foreign server: if the target port is
  // already taken before we spawn anything, this is an external process the
  // gate did not start → INFRA failure (exit 2), NOT a code failure.
  if (!(await isPortFree(BACKEND_PORT))) {
    throw new InfraError(`port :${BACKEND_PORT} déjà occupé par un process externe`);
  }

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
  // A missing `npm`/build tool (ENOENT) is an ENVIRONMENT failure (exit 2),
  // distinct from a build that ran and failed on the app's code (exit 1).
  if (res.error) {
    if (res.error.code === "ENOENT") {
      throw new InfraError("npm introuvable pour build frontend (outil de build absent)");
    }
    throw new InfraError(`échec de lancement de npm run build : ${res.error.message}`);
  }
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
  // Fallback (no openapi.json): try a few conventional health endpoints. Only
  // claim "OK" when we actually got a real, non-404 response < 500. A pure-404
  // result means we probed NOTHING — that's legitimate for some apps, so stay
  // neutral rather than fabricate a false OK (or a false failure).
  for (const p of ["/api/health", "/health", "/api"]) {
    const res = await fetchText(origin + p, Math.min(5000, remaining()));
    if (res.status >= 500) {
      throw new Error(`sonde API : GET ${p} → HTTP ${res.status}\n${res.body.slice(0, 400)}`);
    }
    if (res.status && res.status < 500 && res.status !== 404) {
      return `sonde API OK (${p} → ${res.status})`;
    }
  }
  return "sonde API ignorée (aucun endpoint santé joignable)";
}

// Load `target` in a real browser and require an actually-working app:
// assets resolved with the right MIME, JS executed (SPA root rendered),
// no failed requests, no console errors.
async function checkPage(browser, target, requireApp) {
  const page = await browser.newPage();
  const origin = new URL(target).origin;
  const problems = [];
  const browserErrors = [];
  const serverErrors = []; // same-origin responses with status >= 500 (write-path breakage)
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
    if (res.status() >= 500) {
      serverErrors.push(`${res.request().method()} ${url.pathname} → HTTP ${res.status()}`);
    }
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

  // Let the SPA bundle execute and render before judging the DOM. Instead of a
  // fixed sleep (flaky on slow machines, wasteful on fast ones), POLL for the
  // SPA container to have rendered content, up to a bounded deadline.
  const settleDeadline = Date.now() + Math.min(4000, remaining());
  while (Date.now() < settleDeadline) {
    let rendered = false;
    try {
      rendered = await page.evaluate(() => {
        const root = document.querySelector("#root, #app");
        if (root) {
          return root.childElementCount > 0 || !!root.textContent.trim();
        }
        // No SPA container: fall back to any visible body text.
        return !!(document.body && document.body.innerText.trim());
      });
    } catch { rendered = false; }
    if (rendered) break;
    await page.waitForTimeout(150);
  }
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

  // Write-path journey (Gherkin-derived happy path). BEST-EFFORT: exercises a
  // form submit to catch broken POST→DB wiring that GET-only probes miss. It
  // only FAILS on an OBSERVED 5xx (same-origin) or a NEW page/console error the
  // interaction triggered — never merely because nothing was found to click.
  if (process.env.RUNTIME_JOURNEY) {
    const errorsBefore = browserErrors.length;
    const serverErrorsBefore = serverErrors.length;
    const acted = await runJourney(page).catch((e) => {
      record(`[runtime] journey: interaction interrompue (${String(e).slice(0, 120)})`);
      return false;
    });
    // Let any triggered network settle, bounded by the remaining budget.
    await page.waitForTimeout(Math.min(1500, remaining(0)));

    const journeyProblems = [];
    const newServerErrors = serverErrors.slice(serverErrorsBefore);
    if (newServerErrors.length) {
      journeyProblems.push(
        `journey a déclenché une erreur serveur 5xx : ${newServerErrors.slice(0, 5).join(" | ")} ` +
        `— câblage écriture cassé (POST→DB : router/dépendance/migration ?)`
      );
    }
    const newBrowserErrors = browserErrors.slice(errorsBefore);
    if (newBrowserErrors.length) {
      journeyProblems.push(`journey a déclenché des erreurs navigateur : ${newBrowserErrors.slice(0, 5).join(" | ")}`);
    }
    if (journeyProblems.length) {
      throw new Error(`journey KO sur ${target} :\n- ${journeyProblems.join("\n- ")}`);
    }
    record(`[runtime] journey ${acted ? "exécuté (formulaire soumis)" : "sans interaction (aucun formulaire/bouton trouvé)"} — aucun 5xx`);
  }

  return body.length;
}

// BEST-EFFORT interaction: fill visible inputs with plausible values, then click
// the most prominent submit/primary button. Returns true if it clicked something.
// Never throws for "nothing found" — resilient by design.
async function runJourney(page) {
  let filled = 0;
  const inputs = await page.locator(
    "form input:visible, form textarea:visible, input:visible, textarea:visible"
  ).all().catch(() => []);
  for (const input of inputs.slice(0, 8)) {
    try {
      const type = ((await input.getAttribute("type")) || "text").toLowerCase();
      if (["hidden", "submit", "button", "checkbox", "radio", "file", "range", "color"].includes(type)) continue;
      let value = "test";
      if (type === "email") value = "test@example.com";
      else if (type === "number") value = "1";
      else if (type === "password") value = "Test1234!";
      else if (type === "tel") value = "0102030405";
      else if (type === "url") value = "https://example.com";
      else if (type === "date") value = "2024-01-01";
      await input.fill(value, { timeout: 1500 });
      filled += 1;
    } catch { /* skip this input */ }
  }

  // Prefer an explicit submit; otherwise a button whose text reads like a primary action.
  let button = page.locator("button[type=submit], input[type=submit]").first();
  if (!(await button.count().catch(() => 0))) {
    button = page.getByRole("button", { name: /envoyer|ajouter|créer|creer|enregistrer|save|submit|send|add|create/i }).first();
  }
  if (!(await button.count().catch(() => 0))) return false;
  try {
    await button.click({ timeout: 2000 });
  } catch {
    return false;
  }
  return filled > 0 || true;
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

    // Playwright/chromium not resolvable or not launchable → ENVIRONMENT failure.
    if (!chromium) {
      throw new InfraError("playwright/chromium introuvable (require playwright/@playwright/test a échoué)");
    }
    try {
      browser = await chromium.launch();
    } catch (e) {
      throw new InfraError(`chromium n'a pas pu démarrer (navigateur non installé ?) : ${String(e).slice(0, 300)}`);
    }
    const visible = await checkPage(browser, target, requireApp);
    record(`[runtime] OK ${target} (${visible} caractères visibles)`);
    process.exit(0);
  } catch (err) {
    const detail = err && err.stack ? err.stack : String(err);
    if (err && err.infra) {
      record(`[runtime] INFRA ${err.message || detail}`);
      process.exit(2);
    }
    record(`[runtime] FAIL ${detail}`);
    process.exit(1);
  } finally {
    if (browser) await browser.close().catch(() => {});
    for (const proc of procs) killTree(proc);
    // Filet anti-zombie : un descendant re-parenté peut survivre au killTree.
    if (BACKEND_WEB) reapWorkspacePortHolders(BACKEND_PORT);
    if (FRONTEND) reapWorkspacePortHolders(FRONTEND_PORT);
  }
})();
