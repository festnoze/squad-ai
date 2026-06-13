import { chmodSync, type Dirent, readdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";

/** Recursively clear the read-only bit. Git marks its pack/object files
 * read-only, and Windows then refuses to delete them — `rmSync({force})` does
 * NOT clear read-only (unlike the bit it implies on POSIX), so we do it first. */
function makeWritable(path: string) {
  try {
    chmodSync(path, 0o666);
  } catch {
    /* missing or already gone */
  }
  let entries: Dirent[] = [];
  try {
    entries = readdirSync(path, { withFileTypes: true });
  } catch {
    return; // not a directory / does not exist
  }
  for (const entry of entries) makeWritable(join(path, entry.name));
}

/** Wipe the demo workspace so each e2e run starts from a clean, hermetic state.
 * Runs from the frontend directory (Playwright cwd). */
export default function globalSetup() {
  const dir = resolve(process.cwd(), "../backend/.e2e-workspace");
  makeWritable(dir);
  rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
