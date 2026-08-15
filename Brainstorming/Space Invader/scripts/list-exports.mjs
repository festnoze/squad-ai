// Liste les exports publics de chaque module de src/, pour verifier la
// conformite aux contrats. Usage : node scripts/list-exports.mjs
import { readdirSync, statSync, readFileSync } from 'node:fs';
import { join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const files = [];
(function walk(d) {
  for (const e of readdirSync(d)) {
    const f = join(d, e);
    if (statSync(f).isDirectory()) walk(f);
    else if (e.endsWith('.js')) files.push(f);
  }
})(join(root, 'src'));

for (const f of files.sort()) {
  const s = readFileSync(f, 'utf8');
  const decl = [...s.matchAll(/^export\s+(?:async\s+)?(?:function|class|const|let)\s+([A-Za-z0-9_$]+)/gm)].map((m) => m[1]);
  const named = [...s.matchAll(/^export\s*\{([^}]+)\}/gm)].flatMap((m) =>
    m[1].split(',').map((x) => x.trim().split(/\s+as\s+/).pop()).filter(Boolean),
  );
  const all = [...new Set([...decl, ...named])];
  console.log(relative(root, f).replace(/\\/g, '/').padEnd(40) + ' :: ' + (all.join(', ') || '(rien)'));
}
