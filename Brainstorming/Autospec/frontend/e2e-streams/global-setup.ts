import { chmodSync, type Dirent, readdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";

/** Recursively clear the read-only bit (git packs) - mirrors e2e/global-setup. */
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
    return;
  }
  for (const entry of entries) makeWritable(join(path, entry.name));
}

/** Wipe the STREAMS demo workspace so each run starts hermetic. */
export default function globalSetup() {
  const dir = resolve(process.cwd(), "../backend/.e2e-workspace-streams");
  makeWritable(dir);
  try {
    rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  } catch {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      try {
        rmSync(join(dir, entry.name), {
          recursive: true,
          force: true,
          maxRetries: 2,
          retryDelay: 100,
        });
      } catch {
        /* fichier encore verrouillé - toléré */
      }
    }
  }
}
