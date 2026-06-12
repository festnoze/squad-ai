import { rmSync } from "node:fs";
import { resolve } from "node:path";

/** Wipe the demo workspace so each e2e run starts from a clean, hermetic state.
 * Runs from the frontend directory (Playwright cwd). */
export default function globalSetup() {
  const dir = resolve(process.cwd(), "../backend/.e2e-workspace");
  rmSync(dir, { recursive: true, force: true });
}
