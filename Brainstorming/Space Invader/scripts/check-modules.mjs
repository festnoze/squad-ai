// Verification syntaxique de tous les modules de src/ (parse ES module).
// Usage : node scripts/check-modules.mjs
import { readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const files = [];

function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) walk(p);
    else if (entry.endsWith('.js')) files.push(p);
  }
}
walk(join(root, 'src'));

let failed = 0;
for (const f of files) {
  try {
    execFileSync(process.execPath, ['--input-type=module', '--check', f], { stdio: 'pipe' });
  } catch {
    // node --check ne gere pas --input-type ; on retombe sur un import dynamique
    // de secours uniquement pour la syntaxe via new Function n'est pas fiable.
    // On utilise donc directement `node --check` sur le fichier.
    try {
      execFileSync(process.execPath, ['--check', f], { stdio: 'pipe' });
    } catch (err) {
      failed++;
      console.error(`FAIL ${f.replace(root, '.')}`);
      console.error(String(err.stderr || err.message).split('\n').slice(0, 6).join('\n'));
    }
  }
}

console.log(`${files.length - failed}/${files.length} modules OK`);
process.exit(failed ? 1 : 0);
