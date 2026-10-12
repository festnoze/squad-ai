// Trusted factory-only E2E configuration. The frozen tests, demo-mode flags,
// assertions, timeout, and global setup stay unchanged. Only the isolated
// worktree's interpreter path and loopback port differ from the saved config.
import config from "../../../../frontend/playwright.config";
import { resolve } from "node:path";

const frontend = resolve(process.cwd());
const backend = resolve(frontend, "../backend");
const port = 8237;
const python = "C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/factory-env/Scripts/python.exe";
const baseURL = `http://127.0.0.1:${port}`;

export default {
  ...config,
  testDir: resolve(frontend, "e2e"),
  globalSetup: resolve(frontend, "e2e/global-setup.ts"),
  outputDir: resolve(frontend, "../artifacts/remediation/REM-04/20261012-frontend-upgrade/e2e-results"),
  reporter: [["list"], ["junit", {outputFile: resolve(frontend, "../artifacts/remediation/REM-04/20261012-frontend-upgrade/e2e.xml")}]],
  use: {...config.use, baseURL},
  webServer: {
    ...config.webServer,
    command: `"${python}" -m uvicorn autospec.api.server:app --port ${port}`,
    cwd: backend,
    env: {...config.webServer?.env},
    url: baseURL + "/",
    reuseExistingServer: false,
  },
};
