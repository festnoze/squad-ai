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
  timeout: 60_000,
  expect: { timeout: 12_000 },
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
      AUTOSPEC_DEMO_DELAY_S: "1.0",
      AUTOSPEC_WORKSPACE_ROOT: "./.e2e-workspace",
    },
    url: `http://127.0.0.1:${BACKEND_PORT}/`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
