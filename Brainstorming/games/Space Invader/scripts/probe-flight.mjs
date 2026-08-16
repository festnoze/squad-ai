// Sonde de vol hors navigateur : rejoue le modele de pilotage sans WebGL.
// Verifie, POUR CHAQUE SYSTEME jouable, les temps de trajet interplanetaires,
// le gouverneur de proximite et l'absence de tunneling (deplacement par frame
// contre distance au sol).
//
// Usage : node scripts/probe-flight.mjs
import * as THREE from 'three';
import { buildSystem } from '../src/gen/planetSpec.js';
import { createHeightField } from '../src/gen/heightField.js';
import { SHIP, SCALE } from '../src/core/settings.js';
import { createShip } from '../src/game/ship.js';

// Budgets bloquants. Ils ne decrivent pas la performance du code mais le
// confort de jeu : au-dela, rejoindre un monde devient une corvee.
const BUDGET_SECONDES = 25;
// Pas de simulation rapporte a la distance au sol. A 1 le vaisseau traverse la
// planete entre deux frames ; on garde une marge de securite x2.
const SEUIL_PAS_SOL = 0.5;

let erreurs = 0;

console.log(`AU de reference = ${SCALE.AU.toLocaleString('fr-FR')} unites`);
console.log(
  `budget par trajet : ${BUDGET_SECONDES} s, seuil pas/sol : ${SEUIL_PAS_SOL}`,
);

/** Charge un systeme et prepare ses corps (position absolue + seaLevel calibre). */
function chargeSysteme(choice, seedStr) {
  const sys = buildSystem(choice, seedStr);
  const bodies = sys.planets.map((spec) => {
    createHeightField(spec); // renseigne spec.seaLevel
    return { spec, pos: new THREE.Vector3().fromArray(spec.orbitPosition) };
  });
  return { sys, bodies };
}

// ---------------------------------------------------------------------------
// Ecartement : distance 3D reelle, toutes paires confondues.
// ---------------------------------------------------------------------------
function ecartement(bodies) {
  let pire = null;
  for (let i = 0; i < bodies.length; i++) {
    for (let j = i + 1; j < bodies.length; j++) {
      const a = bodies[i];
      const b = bodies[j];
      const d = a.pos.distanceTo(b.pos);
      // Les spheres de desactivation ne doivent jamais se recouvrir.
      const besoin = (a.spec.radius + b.spec.radius) * SCALE.DEACTIVATE_RADII;
      const ratio = d / besoin;
      if (!pire || ratio < pire.ratio) pire = { ratio, a, b, distance: d, besoin };
    }
  }
  return pire;
}

// ---------------------------------------------------------------------------
// Simulation de trajet : plein pulse, nez sur la cible.
// ---------------------------------------------------------------------------
function nearestSurface(bodies, pos) {
  let best = Infinity;
  for (const b of bodies) best = Math.min(best, pos.distanceTo(b.pos) - b.spec.radius);
  return Math.max(0, best);
}

function trajet(bodies, fromId, toId, { fps = 60, maxSeconds = 300 } = {}) {
  const from = bodies.find((b) => b.spec.id === fromId);
  const to = bodies.find((b) => b.spec.id === toId);
  if (!from || !to) throw new Error(`corps inconnu dans le trajet ${fromId} -> ${toId}`);
  const ship = createShip();
  const dt = 1 / fps;

  // Depart : en orbite basse du corps de depart, nez sur la cible.
  const dir = new THREE.Vector3().subVectors(to.pos, from.pos).normalize();
  ship.state.position.copy(from.pos).addScaledVector(dir, from.spec.radius * 4);
  ship.state.velocity.set(0, 0, 0);
  const m = new THREE.Matrix4().lookAt(new THREE.Vector3(), dir, new THREE.Vector3(0, 1, 0));
  ship.state.quaternion.setFromRotationMatrix(m);

  const input = {
    axes: { pitch: 0, yaw: 0, roll: 0, thrust: 1, strafe: 0, vertical: 0 },
    buttons: { boost: true, brake: false },
  };
  const env = {
    planet: null,
    altitude: Infinity,
    up: new THREE.Vector3(0, 1, 0),
    gravity: null,
    density: 0,
    groundRadius: 0,
    insideGas: 0,
    nearestDistance: Infinity,
  };

  const prev = new THREE.Vector3();
  let t = 0;
  let vmax = 0;
  let pireRapport = 0; // pire (pas par frame / distance au sol)
  let arrive = false;
  const cible = to.spec.radius * 4;

  while (t < maxSeconds) {
    prev.copy(ship.state.position);
    const surf = nearestSurface(bodies, ship.state.position);
    env.nearestDistance = surf;
    env.up.copy(ship.state.position).sub(to.pos).normalize();

    // Le pilote vise la cible en permanence.
    const d = new THREE.Vector3().subVectors(to.pos, ship.state.position);
    const reste = d.length() - to.spec.radius;
    d.normalize();
    const mm = new THREE.Matrix4().lookAt(new THREE.Vector3(), d, new THREE.Vector3(0, 1, 0));
    ship.state.quaternion.setFromRotationMatrix(mm);

    ship.update(dt, input, env);
    t += dt;

    const pas = ship.state.position.distanceTo(prev);
    vmax = Math.max(vmax, ship.telemetry.speed);
    if (surf > 1) pireRapport = Math.max(pireRapport, pas / surf);
    if (reste <= cible) {
      arrive = true;
      break;
    }
  }

  const distance = from.pos.distanceTo(to.pos);
  return {
    de: from.spec.name,
    vers: to.spec.name,
    distance: Math.round(distance),
    secondes: +t.toFixed(1),
    vitesseMax: Math.round(vmax),
    pireRapportPasSol: +pireRapport.toFixed(3),
    arrive,
  };
}

/** Rejoue une liste de routes dans un systeme donne. */
function verifieSysteme(label, choice, seedStr, routes) {
  const { sys, bodies } = chargeSysteme(choice, seedStr);
  console.log(
    `\n=== ${label} (${choice}) : ${sys.planets.length} corps, etoile ${sys.star.name},` +
      ` UA = ${Math.round(sys.star.auUnit).toLocaleString('fr-FR')} u ===`,
  );

  const e = ecartement(bodies);
  if (e) {
    console.log(
      `  ecartement minimal (distance 3D) : x${e.ratio.toFixed(2)} entre ${e.a.spec.name}` +
        ` et ${e.b.spec.name} ${e.ratio > 1 ? '(OK)' : '(RECOUVREMENT)'}`,
    );
    if (e.ratio <= 1) {
      console.error(
        `  ERREUR : spheres de desactivation de ${e.a.spec.name} et ${e.b.spec.name} imbriquees`,
      );
      erreurs++;
    }
  }

  console.log('  --- Trajets, plein pulse, nez sur la cible ---');
  for (const [a, b] of routes) {
    const r = trajet(bodies, a, b);
    const soucis = [];
    if (!r.arrive) soucis.push('JAMAIS ARRIVE');
    if (r.secondes > BUDGET_SECONDES) soucis.push('HORS BUDGET');
    if (r.pireRapportPasSol > SEUIL_PAS_SOL) soucis.push('TUNNELING POSSIBLE');
    console.log(
      `  ${r.de.padEnd(12)} -> ${r.vers.padEnd(12)} ${String(r.distance).padStart(9)} u` +
        ` en ${String(r.secondes).padStart(5)} s` +
        ` (pointe ${r.vitesseMax.toLocaleString('fr-FR').padStart(9)} u/s,` +
        ` pas/sol max ${r.pireRapportPasSol})` +
        (soucis.length ? `  <-- ${soucis.join(' + ')}` : ''),
    );
    if (soucis.length) {
      console.error(`  ERREUR : ${r.de} -> ${r.vers} : ${soucis.join(', ')}`);
      erreurs++;
    }
  }
}

verifieSysteme('Odyssee', 'odyssey', 'odyssey', [
  ['terra-prime', 'nereidia'],
  ['terra-prime', 'aurelia'],
  ['cindra', 'nyx'],
  ['terra-prime', 'bellatrix'],
]);

verifieSysteme('Sol-1', 'sol1', 'sol1', [
  ['mars', 'terre'],
  ['mars', 'jupiter'],
  ['mars', 'neptune'],
  ['terre', 'venus'],
]);

// ---------------------------------------------------------------------------
// Virage sous pulse : la trajectoire doit se recaler sur le nez.
// ---------------------------------------------------------------------------
function virageEnPulse() {
  const ship = createShip();
  const dt = 1 / 60;
  const loin = new THREE.Vector3(2e6, 0, 0); // au milieu du vide
  ship.state.position.copy(loin);
  const input = {
    axes: { pitch: 0, yaw: 0, roll: 0, thrust: 1, strafe: 0, vertical: 0 },
    buttons: { boost: true, brake: false },
  };
  const env = {
    planet: null,
    altitude: Infinity,
    up: new THREE.Vector3(0, 1, 0),
    gravity: null,
    density: 0,
    groundRadius: 0,
    insideGas: 0,
    nearestDistance: 1.5e6,
  };
  for (let i = 0; i < 180; i++) ship.update(dt, input, env); // 3 s plein pulse
  const vitesseAvant = ship.state.velocity.length();

  // Demi-tour a 90 degres : on pointe vers +X.
  const m = new THREE.Matrix4().lookAt(
    new THREE.Vector3(),
    new THREE.Vector3(1, 0, 0),
    new THREE.Vector3(0, 1, 0),
  );
  ship.state.quaternion.setFromRotationMatrix(m);

  const nez = new THREE.Vector3(0, 0, -1).applyQuaternion(ship.state.quaternion);
  const ecarts = [];
  for (let s = 0; s < 4; s++) {
    for (let i = 0; i < 60; i++) ship.update(dt, input, env);
    const v = ship.state.velocity.clone().normalize();
    ecarts.push(+((Math.acos(Math.max(-1, Math.min(1, v.dot(nez)))) * 180) / Math.PI).toFixed(1));
  }
  return { vitesseAvant: Math.round(vitesseAvant), ecartApresVirage: ecarts };
}

const v = virageEnPulse();
console.log('\n--- Virage a 90 degres sous pulse ---');
console.log(
  `vitesse avant virage ${v.vitesseAvant.toLocaleString('fr-FR')} u/s, ` +
    `ecart trajectoire/nez apres 1, 2, 3 et 4 s : ${v.ecartApresVirage.join(' / ')} degres`,
);
if (v.ecartApresVirage[v.ecartApresVirage.length - 1] > 15) {
  console.error('ERREUR : la trajectoire ne suit pas le nez sous pulse.');
  erreurs++;
}

console.log(
  `\ngouverneur : vitesse max = distance au sol x ${SHIP.pulseProximityRate}` +
    `, plancher ${SHIP.pulseMinSpeed} u/s, plafond ${SHIP.pulseMaxSpeed.toLocaleString('fr-FR')} u/s`,
);

if (erreurs) {
  console.error(`\n${erreurs} erreur(s).`);
  process.exit(1);
}
console.log('Tous les trajets tiennent le budget, aucun risque de traverser une planete.');
