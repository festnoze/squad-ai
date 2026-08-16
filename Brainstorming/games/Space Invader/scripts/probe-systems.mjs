// Sonde des systemes disponibles au menu : coherence des specs, unicite de la
// planete viable, presence d'un monde d'origine, ecartement des orbites.
// Usage : node scripts/probe-systems.mjs
import { buildSystem, SYSTEM_CHOICES } from '../src/gen/planetSpec.js';
import { createHeightField } from '../src/gen/heightField.js';
import { BIOMES } from '../src/gen/palettes.js';
import { SCALE } from '../src/core/settings.js';

let erreurs = 0;

/** Distance reelle entre deux corps, a partir de leur position orbitale 3D. */
function distance3D(a, b) {
  const [ax, ay, az] = a.orbitPosition;
  const [bx, by, bz] = b.orbitPosition;
  return Math.hypot(ax - bx, ay - by, az - bz);
}

function verifie(system, label) {
  console.log(`\n=== ${label} : ${system.planets.length} corps, etoile ${system.star.name} ===`);
  console.log(
    `  UA du systeme = ${Math.round(system.star.auUnit).toLocaleString('fr-FR')} u,` +
      ` rayon solaire = ${Math.round(system.star.radius).toLocaleString('fr-FR')} u,` +
      ` diametre apparent a 1 UA = ${((2 * system.star.radius) / system.star.auUnit * 57.3).toFixed(2)} deg`,
  );

  const viables = system.planets.filter((p) => p.hasOcean && p.hasTrees && p.hasFauna);
  const foyers = system.planets.filter((p) => p.isHome);
  if (viables.length !== 1) {
    console.error(`  ERREUR : ${viables.length} planetes viables (attendu 1)`);
    erreurs++;
  }
  if (foyers.length !== 1) {
    console.error(`  ERREUR : ${foyers.length} mondes d'origine (attendu 1)`);
    erreurs++;
  }
  if (viables[0] && foyers[0] && viables[0].id === foyers[0].id) {
    console.error("  ERREUR : on demarre sur la planete viable, la partie est gagnee d'avance");
    erreurs++;
  }

  const tri = [...system.planets].sort((a, b) => a.orbitRadius - b.orbitRadius);

  // Ecartement : distance 3D REELLE entre les corps, pas difference de rayons
  // orbitaux. Deux planetes voisines en rayon peuvent etre diametralement
  // opposees sur leur orbite (phases differentes) et donc tres loin l'une de
  // l'autre ; l'ancienne mesure radiale criait au recouvrement dans Sol-1 alors
  // qu'il n'y en avait aucun. On compare toutes les paires, pas seulement les
  // voisines par orbite.
  const P = system.planets;
  let pire = null;
  for (let i = 0; i < P.length; i++) {
    for (let j = i + 1; j < P.length; j++) {
      const a = P[i];
      const b = P[j];
      const d = distance3D(a, b);
      // Les spheres de DESACTIVATION ne doivent jamais se recouvrir : si elles
      // le font, deux corps restent actifs en meme temps et les deux terrains
      // sont construits simultanement.
      const besoin = (a.radius + b.radius) * SCALE.DEACTIVATE_RADII;
      const ratio = d / besoin;
      if (!pire || ratio < pire.ratio) pire = { ratio, a, b, distance: d, besoin };
    }
  }
  if (pire) {
    console.log(
      `  marge d'ecartement minimale (distance 3D reelle) : x${pire.ratio.toFixed(2)}` +
        ` entre ${pire.a.name} et ${pire.b.name}` +
        ` (${Math.round(pire.distance).toLocaleString('fr-FR')} u pour` +
        ` ${Math.round(pire.besoin).toLocaleString('fr-FR')} u requis)`,
    );
    if (pire.ratio <= 1) {
      console.error(
        `  ERREUR : les spheres de desactivation de ${pire.a.name} et ${pire.b.name} se recouvrent`,
      );
      erreurs++;
    }
  }

  for (const p of tri) {
    const hf = createHeightField(p);
    let ligne =
      `  ${String(p.orbitAU).padStart(6)} UA  ${p.name.padEnd(12)} ${p.typeLabel.padEnd(15)}` +
      ` R=${String(p.radius).padStart(6)} ${p.tempLabel.padEnd(14)}` +
      ` OTF=${[p.hasOcean, p.hasTrees, p.hasFauna].map((b) => (b ? 1 : 0)).join('')}`;
    if (p.isHome) ligne += ' [DEPART]';
    if (p.viable) ligne += ' [VIABLE]';
    if (p.ring) ligne += ' [ANNEAUX]';
    if (!p.isGas) {
      // Biome dominant, pour verifier que la planete ressemble a ce qu'on attend.
      const N = 1200;
      const ga = Math.PI * (3 - Math.sqrt(5));
      const hist = new Array(BIOMES.length).fill(0);
      for (let i = 0; i < N; i++) {
        const y = 1 - (i / (N - 1)) * 2;
        const r = Math.sqrt(Math.max(0, 1 - y * y));
        const th = ga * i;
        const x = Math.cos(th) * r;
        const z = Math.sin(th) * r;
        const e = hf.elevation(x, y, z);
        hist[hf.biomeId(x, y, z, e)]++;
      }
      const top = hist
        .map((c, i) => [BIOMES[i].key, c])
        .filter((a) => a[1] > 0)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map((a) => `${a[0]}:${Math.round((a[1] / N) * 100)}%`)
        .join(' ');
      ligne += `  ${top}`;
    }
    console.log(ligne);
  }
}

verifie(buildSystem('sol1'), 'Sol-1');
verifie(buildSystem('odyssey'), 'Odyssee');
for (const seed of ['x1', 'x2', 'x3']) {
  verifie(buildSystem('random', seed), `Aleatoire (seed ${seed})`);
}

console.log(`\nchoix exposes au menu : ${SYSTEM_CHOICES.map((c) => c.id).join(', ')}`);
if (erreurs) {
  console.error(`\n${erreurs} erreur(s).`);
  process.exit(1);
}
console.log('Tous les systemes sont jouables.');
