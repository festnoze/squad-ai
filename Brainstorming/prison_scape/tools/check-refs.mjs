/**
 * Undefined-reference check.
 *
 *   node tools/check-refs.mjs
 *
 * Parsing a file only proves it is syntactically valid. `WALL_H` used inside a
 * method that was never imported parses perfectly and then throws the moment
 * the method runs - which, for level-building code, means a black screen on
 * load. This walks every module, collects everything it declares or imports,
 * and reports identifiers it uses but never obtained.
 *
 * It is a heuristic, not a real scope analyser: it over-collects declarations
 * (any binding anywhere counts for the whole file) so it under-reports rather
 * than crying wolf. Anything it does report is real.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const SRC = join(dirname(fileURLToPath(import.meta.url)), '../src');

/** Strip comments and string bodies, but keep `${...}` expressions. */
function scrub(src) {
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
      i++;
      while (i < n && src[i] !== q) i += src[i] === '\\' ? 2 : 1;
      i++;
      out += '""';
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
          out += ` ${scrub(expr)} `;
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

let failures = 0;
const files = readdirSync(SRC).filter((f) => f.endsWith('.js')).sort();

console.log(`Reference check over ${files.length} modules\n`);

for (const file of files) {
  const raw = readFileSync(join(SRC, file), 'utf8');
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
    failures++;
    const list = [...unknown].map(([n, l]) => `${n} (line ${l})`).join(', ');
    console.log(`  FAIL  ${file}\n          undefined: ${list}`);
  }
}

console.log(`\n${failures === 0 ? 'PASS' : `${failures} module(s) reference something undefined`}\n`);
process.exit(failures === 0 ? 0 : 1);
