/**
 * Undefined-reference and module-graph check.
 *
 *   node tools/check-refs.mjs
 *
 * Parsing a file only proves it is syntactically valid. Two different mistakes
 * survive parsing and then blow up in the browser as a black screen on load,
 * so this tool runs two passes over src/.
 *
 * Pass 1, references: `WALL_H` used inside a method that was never imported
 * parses perfectly and then throws the moment the method runs. The pass walks
 * every module, collects everything it declares or imports, and reports
 * identifiers it uses but never obtained.
 *
 * Pass 2, module graph: `import { WALL_H } from './layout.js'` is fine for
 * pass 1 even when layout.js never exports that name - the module simply fails
 * to link, and the browser says "does not provide an export named ...". The
 * pass collects the real export surface of every module (including names
 * re-exported from another module, `export { TILE } from './layout.js'`) and
 * checks each relative import against it: the target file must exist and every
 * imported name must actually be exported. Bare specifiers such as 'three' are
 * left alone.
 *
 * Both passes are heuristics, not a real parser: they over-collect (any
 * binding anywhere counts for the whole file, export lists are read
 * generously) so they under-report rather than crying wolf. Namespace imports
 * `import * as X` are never inspected beyond the module they point at.
 * Anything reported is real.
 */
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const SRC = join(dirname(fileURLToPath(import.meta.url)), '../src');

/**
 * Strip comments and string bodies, but keep `${...}` expressions.
 * With `keepQuoted`, plain '...' and "..." literals survive intact - the
 * module-graph pass needs the specifiers they hold.
 */
function scrub(src, keepQuoted = false) {
  let out = '';
  let i = 0;
  const n = src.length;
  while (i < n) {
    const c = src[i];
    const next = src[i + 1];
    if (c === '/' && next === '/') {
      while (i < n && src[i] !== '\n') i++;
    } else if (c === '/' && next === '*') {
      i += 2;
      while (i < n && !(src[i] === '*' && src[i + 1] === '/')) i++;
      i += 2;
    } else if (c === "'" || c === '"') {
      const q = c;
      const start = i;
      i++;
      while (i < n && src[i] !== q) i += src[i] === '\\' ? 2 : 1;
      i++;
      out += keepQuoted ? src.slice(start, Math.min(i, n)) : '""';
    } else if (c === '`') {
      i++;
      while (i < n && src[i] !== '`') {
        if (src[i] === '\\') { i += 2; continue; }
        if (src[i] === '$' && src[i + 1] === '{') {
          // Keep the expression - it holds real references - but scrub it too,
          // or the strings nested inside it leak through as identifiers.
          let depth = 1;
          i += 2;
          let expr = '';
          while (i < n && depth > 0) {
            if (src[i] === '{') depth++;
            else if (src[i] === '}') depth--;
            if (depth > 0) expr += src[i];
            i++;
          }
          out += ` ${scrub(expr, keepQuoted)} `;
          continue;
        }
        i++;
      }
      i++;
      out += '""';
    } else if (c === '/' && /[=(,:[!&|?{;\n]\s*$/.test(out)) {
      // regex literal
      i++;
      while (i < n && src[i] !== '/') i += src[i] === '\\' ? 2 : 1;
      i++;
      while (i < n && /[gimsuy]/.test(src[i])) i++;
      out += '/RE/';
    } else {
      out += c;
      i++;
    }
  }
  return out;
}

const GLOBALS = new Set([
  // language
  'undefined', 'NaN', 'Infinity', 'globalThis', 'this', 'arguments', 'super',
  'Object', 'Array', 'String', 'Number', 'Boolean', 'Symbol', 'BigInt',
  'Math', 'JSON', 'Date', 'RegExp', 'Error', 'TypeError', 'RangeError',
  'Map', 'Set', 'WeakMap', 'WeakSet', 'Promise', 'Proxy', 'Reflect',
  'Float32Array', 'Float64Array', 'Uint8Array', 'Uint16Array', 'Uint32Array',
  'Int8Array', 'Int16Array', 'Int32Array', 'ArrayBuffer', 'DataView',
  'parseInt', 'parseFloat', 'isNaN', 'isFinite', 'structuredClone',
  // browser
  'window', 'document', 'console', 'performance', 'navigator', 'location',
  'requestAnimationFrame', 'cancelAnimationFrame', 'setTimeout', 'clearTimeout',
  'setInterval', 'clearInterval', 'fetch', 'Image', 'Audio', 'AudioContext',
  'HTMLCanvasElement', 'CanvasRenderingContext2D', 'KeyboardEvent', 'MouseEvent',
  'devicePixelRatio', 'localStorage', 'sessionStorage', 'CustomEvent', 'Event',
  // keywords that the tokeniser will hand us
  'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default', 'break',
  'continue', 'return', 'function', 'class', 'const', 'let', 'var', 'new',
  'delete', 'typeof', 'instanceof', 'in', 'of', 'void', 'throw', 'try',
  'catch', 'finally', 'import', 'export', 'from', 'as', 'async', 'await',
  'yield', 'true', 'false', 'null', 'static', 'get', 'set', 'extends',
]);

let refFailures = 0;
let graphFailures = 0;
const files = readdirSync(SRC).filter((f) => f.endsWith('.js')).sort();
const sources = new Map(files.map((f) => [f, readFileSync(join(SRC, f), 'utf8')]));

// ------------------------------------------------------- pass 1: references
console.log(`Reference check over ${files.length} modules\n`);

for (const file of files) {
  const raw = sources.get(file);
  const src = scrub(raw);
  const declared = new Set();

  // import { a, b as c } from '...'   /   import * as X   /   import X
  for (const m of src.matchAll(/import\s+([^;]+?)\s+from/g)) {
    const clause = m[1];
    for (const g of clause.matchAll(/\*\s+as\s+(\w+)/g)) declared.add(g[1]);
    const braces = clause.match(/\{([^}]*)\}/);
    if (braces) {
      for (const part of braces[1].split(',')) {
        const nm = part.trim().split(/\s+as\s+/).pop().trim();
        if (nm) declared.add(nm);
      }
    }
    const bare = clause.replace(/\{[^}]*\}/g, '').replace(/\*\s+as\s+\w+/g, '').replace(/,/g, '').trim();
    if (/^\w+$/.test(bare)) declared.add(bare);
  }

  // every binding anywhere in the file (over-collected on purpose)
  const bindPatterns = [
    /\b(?:const|let|var)\s+(\w+)/g,
    // further declarators in the same statement: const a = 1, b = 2
    /,\s*(\w+)\s*=/g,
    /\bfunction\s*\*?\s*(\w+)/g,
    /\bclass\s+(\w+)/g,
    /\bcatch\s*\(\s*(\w+)/g,
    /\bfor\s*\(\s*(?:const|let|var)\s+(\w+)/g,
    // accessors: get ready() / set foo(v) / static get bar()
    /^\s*(?:static\s+)?(?:get|set)\s+(\w+)\s*\(/gm,
  ];
  for (const re of bindPatterns) {
    for (const m of src.matchAll(re)) declared.add(m[1]);
  }
  // destructured bindings: const { a, b } = / const [a, b] =
  for (const m of src.matchAll(/\b(?:const|let|var)\s*[[{]([^)]*?)[\]}]\s*=/g)) {
    for (const part of m[1].split(',')) {
      const nm = part.trim().split(/[:=]/).pop().trim().replace(/^\.\.\./, '');
      if (/^\w+$/.test(nm)) declared.add(nm);
    }
  }
  // function parameters and arrow params
  for (const m of src.matchAll(/(?:function\s*\*?\s*\w*|\b\w+)\s*\(([^()]*)\)\s*(?:\{|=>)/g)) {
    for (const part of m[1].split(',')) {
      const nm = part.trim().split(/[:=]/)[0].trim().replace(/^\.\.\./, '');
      if (/^\w+$/.test(nm)) declared.add(nm);
    }
  }
  // any parenthesised arrow parameter list, including defaults: (a, b = c) =>
  for (const m of src.matchAll(/\(([^()]*)\)\s*=>/g)) {
    for (const part of m[1].split(',')) {
      const nm = part.trim().split(/[:=]/)[0].trim().replace(/^\.\.\./, '');
      if (/^\w+$/.test(nm)) declared.add(nm);
    }
  }
  for (const m of src.matchAll(/(?:^|[^\w.])(\w+)\s*=>/g)) declared.add(m[1]);
  // destructured params: ({ a, b }) =>  and  ([a, b]) =>
  for (const m of src.matchAll(/[({[]\s*\{([^}]*)\}\s*[)\]]?\s*(?:=>|\{)/g)) {
    for (const part of m[1].split(',')) {
      const nm = part.trim().split(/[:=]/).pop().trim();
      if (/^\w+$/.test(nm)) declared.add(nm);
    }
  }
  for (const m of src.matchAll(/\[\s*([\w,\s]*?)\s*\]\s*(?:of|=)/g)) {
    for (const part of m[1].split(',')) {
      const nm = part.trim();
      if (/^\w+$/.test(nm)) declared.add(nm);
    }
  }
  // class members and object methods are properties, not references
  for (const m of src.matchAll(/^\s*(\w+)\s*\(/gm)) declared.add(m[1]);

  // Now find references. Skip property access, object keys and labels.
  // `export { A as B }` names bindings, it does not reference them.
  const body = src.replace(/export\s*\{[^}]*\}\s*(?:from\s*""\s*)?;?/g, '');
  const unknown = new Map();
  const tokenRe = /(\.\s*)?\b([A-Za-z_$][\w$]*)\b(\s*:)?/g;
  let m;
  while ((m = tokenRe.exec(body))) {
    const [, dot, name, colon] = m;
    if (dot || colon) continue;              // a.foo   or   { foo: ... }
    if (GLOBALS.has(name)) continue;
    if (declared.has(name)) continue;
    const line = body.slice(0, m.index).split('\n').length;
    if (!unknown.has(name)) unknown.set(name, line);
  }

  if (unknown.size === 0) {
    console.log(`  ok    ${file}`);
  } else {
    refFailures++;
    const list = [...unknown].map(([n, l]) => `${n} (line ${l})`).join(', ');
    console.log(`  FAIL  ${file}\n          undefined: ${list}`);
  }
}

// ----------------------------------------------------- pass 2: module graph
const RELATIVE = /^\.\.?\//;

/** `import D, { a, b as c } from '...'` -> the clause and the specifier. */
function parseImports(src) {
  const out = [];
  for (const m of src.matchAll(/^[ \t]*import\s+([^;'"]*?)\s+from\s*(['"])([^'"]+)\2/gm)) {
    out.push({ clause: m[1], spec: m[3], index: m.index });
  }
  // side-effect only: import '...'
  for (const m of src.matchAll(/^[ \t]*import\s*(['"])([^'"]+)\1/gm)) {
    out.push({ clause: '', spec: m[2], index: m.index });
  }
  return out;
}

/** Names taken out of a module by an import clause, before any `as`. */
function importedNames(clause) {
  const names = [];
  const braces = clause.match(/\{([^}]*)\}/);
  if (braces) {
    for (const part of braces[1].split(',')) {
      const t = part.trim();
      if (!t) continue;
      const nm = t.split(/\s+as\s+/)[0].trim();
      if (/^[A-Za-z_$][\w$]*$/.test(nm)) names.push(nm);
    }
  }
  // `import Thing from '...'` needs a default export to link
  const bare = clause
    .replace(/\{[^}]*\}/g, '')
    .replace(/\*\s+as\s+[\w$]+/g, '')
    .replace(/,/g, ' ')
    .trim();
  if (/^[A-Za-z_$][\w$]*$/.test(bare)) names.push('default');
  return names;
}

/** Every name a `const a = 1, { b } = o` declaration head binds. */
function bindingNames(text) {
  const names = [];
  for (const part of text.split(',')) {
    const m = part.trim().replace(/^[[{\s]+/, '').match(/^([\w$]+)/);
    if (m) names.push(m[1]);
  }
  return names;
}

/**
 * Export surface of one module: the names it declares as exported (a
 * re-exported name counts as its own), plus the edges it needs resolved -
 * `export * from '...'` widens the surface, `export { a } from '...'` is an
 * import in disguise and gets checked like one.
 */
function parseExports(src) {
  const own = new Set();
  const edges = [];   // { spec, names, index } - same shape as an import
  const stars = [];   // { spec, index }
  for (const m of src.matchAll(/^[ \t]*export\s*\{([^}]*)\}\s*(?:from\s*(['"])([^'"]+)\2)?/gm)) {
    const names = [];
    for (const part of m[1].split(',')) {
      const t = part.trim();
      if (!t) continue;
      const bits = t.split(/\s+as\s+/);
      const local = bits[0].trim();
      const exported = (bits[1] || bits[0]).trim();
      if (/^[A-Za-z_$][\w$]*$/.test(exported)) own.add(exported);
      if (/^[A-Za-z_$][\w$]*$/.test(local)) names.push(local);
    }
    if (m[3]) edges.push({ spec: m[3], names, index: m.index });
  }
  for (const m of src.matchAll(/^[ \t]*export\s*\*\s*(?:as\s+([\w$]+)\s*)?from\s*(['"])([^'"]+)\2/gm)) {
    if (m[1]) own.add(m[1]);
    else stars.push({ spec: m[3], index: m.index });
  }
  if (/^[ \t]*export\s+default\b/m.test(src)) own.add('default');
  for (const m of src.matchAll(/^[ \t]*export\s+(?:async\s+)?function\s*\*?\s*([\w$]+)/gm)) own.add(m[1]);
  for (const m of src.matchAll(/^[ \t]*export\s+class\s+([\w$]+)/gm)) own.add(m[1]);
  for (const m of src.matchAll(/^[ \t]*export\s+(?:const|let|var)\s+([^\n;]*)/gm)) {
    for (const nm of bindingNames(m[1])) own.add(nm);
  }
  return { own, edges, stars };
}

const modules = new Map();   // absolute path -> parsed module
for (const file of files) {
  const abs = join(SRC, file);
  const src = scrub(sources.get(file), true);
  modules.set(abs, { file, src, ...parseExports(src), imports: parseImports(src) });
}

/** A relative specifier resolved to an existing file, or null. */
function resolveSpec(fromAbs, spec) {
  const target = resolve(dirname(fromAbs), spec);
  if (!existsSync(target) || !statSync(target).isFile()) return null;
  return target;
}

const exportCache = new Map();
/**
 * Names a module provides. `trusted` goes false when part of the surface
 * comes from somewhere we did not read - then the module tells us nothing and
 * its importers are left alone rather than wrongly accused.
 */
function exportsOf(abs, stack = new Set()) {
  if (exportCache.has(abs)) return exportCache.get(abs);
  const mod = modules.get(abs);
  if (!mod || stack.has(abs)) return { names: new Set(), trusted: false };
  stack.add(abs);
  const names = new Set(mod.own);
  let trusted = true;
  for (const star of mod.stars) {
    const target = RELATIVE.test(star.spec) ? resolveSpec(abs, star.spec) : null;
    const sub = target ? exportsOf(target, stack) : { names: new Set(), trusted: false };
    if (!sub.trusted) { trusted = false; continue; }
    for (const nm of sub.names) names.add(nm);
  }
  stack.delete(abs);
  const surface = { names, trusted };
  if (trusted) exportCache.set(abs, surface);
  return surface;
}

/** Line of the statement that names this specifier, for the report. */
function lineOf(src, index) {
  return src.slice(0, index).split('\n').length;
}

console.log(`\nModule graph over ${files.length} modules\n`);

for (const file of files) {
  const abs = join(SRC, file);
  const mod = modules.get(abs);
  const problems = [];
  for (const edge of [...mod.imports, ...mod.edges]) {
    if (!RELATIVE.test(edge.spec)) continue;   // 'three' and friends: not ours
    const line = lineOf(mod.src, edge.index);
    const target = resolveSpec(abs, edge.spec);
    if (!target) {
      problems.push(`module not found: ${edge.spec} (line ${line})`);
      continue;
    }
    const surface = exportsOf(target);
    if (!surface.trusted) continue;            // unknown surface: stay quiet
    const names = edge.names ?? importedNames(edge.clause);
    for (const nm of names) {
      if (surface.names.has(nm)) continue;
      problems.push(nm === 'default'
        ? `${edge.spec} has no default export (line ${line})`
        : `${edge.spec} does not export ${nm} (line ${line})`);
    }
  }

  if (problems.length === 0) {
    console.log(`  ok    ${file}`);
  } else {
    graphFailures++;
    console.log(`  FAIL  ${file}\n          ${problems.join('\n          ')}`);
  }
}

// ---------------------------------------------------------------------- end
const failures = refFailures + graphFailures;
if (failures === 0) {
  console.log('\nPASS\n');
} else {
  const lines = [];
  if (refFailures) lines.push(`${refFailures} module(s) reference something undefined`);
  if (graphFailures) lines.push(`${graphFailures} module(s) import something that is not there`);
  console.log(`\n${lines.join('\n')}\n`);
}
process.exit(failures === 0 ? 0 : 1);
