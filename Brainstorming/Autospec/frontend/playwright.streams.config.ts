import { defineConfig, devices } from "@playwright/test";

/**
 * ST-17 - e2e MULTI-STREAM harness (streams ON), separate from the exhaustive
 * default-flow suite: autospec.spec.ts asserts the single-stream board shape
 * and would break under the stream-aware scripted plan (_PO_PLAN_STREAMS). This
 * config boots its OWN hermetic backend (dedicated port + workspace) with
 * AUTOSPEC STREAMS enabled and runs only e2e-streams/.
 *
 * Run: `npm run test:e2e:streams` (builds the SPA first - the backend serves
 * frontend/dist same-origin, no Vite proxy).
 */
const BACKEND_PORT = 8124;
const PYTHON =
  process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";

export default defineConfig({
  testDir: "./e2e-streams",
  globalSetup: "./e2e-streams/global-setup.ts",
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
      FAKE_AGENTS: "1",
      DEMO_DELAY_S: "0.4",
      WORKSPACE_ROOT: "./.e2e-workspace-streams",
      // The whole point of this harness: the parallel multi-stream build path.
      STREAMS: "1",
      // Keep the optional phases quiet - this suite validates the STREAMS UI
      // (badges, task rows, cross-stream dependency), not the full surface.
      COMPONENTS: "0",
      ARCHITECTURE: "0",
      REFINE: "0",
      EVALUATOR: "0",
      RETRO: "0",
      BRAINSTORM_ASSIST: "0",
    },
    url: `http://127.0.0.1:${BACKEND_PORT}/`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
