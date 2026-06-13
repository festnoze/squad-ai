import { defineConfig, devices } from "@playwright/test";

/**
 * E2E config. The FastAPI backend serves the *built* frontend (frontend/dist)
 * itself, so /api and /ws are same-origin — no Vite proxy in the loop (which was
 * flaky for WebSockets under Playwright). Run `npm run build` first (the
 * `test:e2e` script does this). Backend runs in demo mode: scripted agents, no
 * Claude CLI, no uv venv build — fully hermetic.
 */
const BACKEND_PORT = 8123;
// Relative to the backend cwd below.
const PYTHON =
  process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 240_000,
  expect: { timeout: 25_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${BACKEND_PORT}`,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `${PYTHON} -m uvicorn autospec.api.server:app --port ${BACKEND_PORT}`,
    cwd: "../backend",
    env: {
      AUTOSPEC_FAKE_AGENTS: "1",
      AUTOSPEC_DEMO_DELAY_S: "0.6",
      AUTOSPEC_WORKSPACE_ROOT: "./.e2e-workspace",
      // Exercise every optional pipeline phase in the exhaustive e2e scenario.
      AUTOSPEC_COMPONENTS: "1", // E3/E4 — component proposal + setup
      AUTOSPEC_ARCHITECTURE: "1", // item 7 — architecture phase
      AUTOSPEC_REFINE: "1", // item 0/10 — refinement scores (plan + code)
      AUTOSPEC_REFINE_MAX_ROUNDS: "1",
      AUTOSPEC_EVALUATOR: "1", // E6 — closed-loop product evaluator
      AUTOSPEC_RETRO: "1", // E7 — factory retrospective
    },
    url: `http://127.0.0.1:${BACKEND_PORT}/`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
