// Sonde hors navigateur : verifie le champ de hauteur, le calibrage du niveau
// des mers et la repartition des biomes des 12 corps.
// Usage : node scripts/probe-planets.mjs [seed]
import { buildSolarSystem } from '../src/gen/planetSpec.js';
import { createHeightField } from '../src/gen/heightField.js';
import { BIOMES } from '../src/gen/palettes.js';

const seed = process.argv[2] || 'odyssey';
const sys = buildSolarSystem(seed);
console.log(`seed="${seed}"  corps=${sys.planets.length}\n`);

for (const p of sys.planets) {
  const t0 = performance.now();
  const hf = createHeightField(p);
  const N = 4000;
  const ga = Math.PI * (3 - Math.sqrt(5));
  let water = 0;
  let wsum = 0;
  const hist = new Array(BIOMES.length).fill(0);
  let lo = Infinity;
  let hi = -Infinity;
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = ga * i;
    const x = Math.cos(th) * r;
    const z = Math.sin(th) * r;
    const e = hf.elevation(x, y, z);
    lo = Math.min(lo, e);
    hi = Math.max(hi, e);
    const w = r + 1e-6; // ponderation par cos(latitude)
    wsum += w;
    if (hf.isWater(e)) water += w;
    hist[hf.biomeId(x, y, z, e)]++;
  }
  const ms = (performance.now() - t0).toFixed(0);
  const top = hist
    .map((c, i) => [BIOMES[i].key, c])
    .filter((a) => a[1] > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map((a) => `${a[0]}:${((a[1] / N) * 100).toFixed(0)}%`)
    .join(' ');
  console.log(
    `${p.name.padEnd(12)} R=${String(p.radius).padStart(5)}` +
      ` mer=${p.seaLevel === null ? ' null' : p.seaLevel.toFixed(0).padStart(5)}` +
      ` cible=${((p.seaFraction || 0) * 100).toFixed(0)}%/reel=${((water / wsum) * 100).toFixed(0)}%` +
      ` elev=[${lo.toFixed(0)},${hi.toFixed(0)}]/${p.maxElevation.toFixed(0)}` +
      ` OTF=${[p.hasOcean, p.hasTrees, p.hasFauna].map((b) => (b ? 1 : 0)).join('')}` +
      ` ${ms}ms | ${top}`,
  );
}

const viable = sys.planets.filter((p) => p.hasOcean && p.hasTrees && p.hasFauna);
console.log(`\nplanetes viables : ${viable.map((p) => p.name).join(', ') || 'AUCUNE (bug)'}`);
if (viable.length !== 1) {
  console.error('ERREUR : il doit y avoir exactement une planete viable.');
  process.exit(1);
}
