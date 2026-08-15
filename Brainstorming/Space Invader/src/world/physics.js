// Helpers de physique de vol. Fonctions pures (aucun etat de jeu conserve) :
// tout ce qui varie est passe en argument et ecrit dans un `out` fourni par
// l'appelant, afin de n'allouer AUCUN objet par frame.
//
// Conventions :
// - `absPos` est une position ABSOLUE (origine = le soleil).
// - `planet` est l'objet renvoye par world/planet.js. On ne suppose de lui que
//   le minimum et on degrade proprement si un champ manque (specs partielles,
//   planete pas encore activee, geante gazeuse sans sol).
// - les vecteurs de sortie sont en espace ABSOLU.

import * as THREE from 'three';
import { clamp, saturate } from '../core/math.js';
import { makeNoise3D } from '../gen/noise.js';

// Vecteurs de travail au niveau module : zero allocation en vol.
const _center = new THREE.Vector3();
const _center2 = new THREE.Vector3();
const _local = new THREE.Vector3();
const _dir = new THREE.Vector3();
const _nrm = new THREE.Vector3();

/** Centre de la planete en absolu, avec plusieurs noms de champ toleres. */
function centerOf(planet, out) {
  if (planet.absolutePosition && planet.absolutePosition.isVector3) return out.copy(planet.absolutePosition);
  if (planet.absPosition && planet.absPosition.isVector3) return out.copy(planet.absPosition);
  if (planet.center && planet.center.isVector3) return out.copy(planet.center);
  const op = planet.spec && planet.spec.orbitPosition;
  if (op) return out.set(op[0], op[1], op[2]);
  return out.set(0, 0, 0);
}

/** Position absolue -> espace local planete (centre = origine, +Y = poles). */
function toLocalOf(planet, absPos, out) {
  if (typeof planet.toLocal === 'function') return planet.toLocal(absPos, out);
  centerOf(planet, _center2);
  return out.copy(absPos).sub(_center2);
}

/**
 * Gravite subie a `absPos`. Direction : vers le centre de la planete.
 * Magnitude : g0 * (R / d)^2, bornee a 3 g0 pour eviter toute divergence
 * numerique quand on frole le centre (ou dans une geante gazeuse).
 */
export function gravityAt(planet, absPos, out) {
  const res = out || new THREE.Vector3();
  res.set(0, 0, 0);
  if (!planet || !planet.spec) return res;
  const spec = planet.spec;
  const g0 = spec.gravity || 0;
  if (g0 <= 0) return res;

  toLocalOf(planet, absPos, _local);
  const dist = _local.length();
  if (dist < 1e-3) return res;

  // Direction absolue : l'oppose de la verticale locale.
  if (typeof planet.upAt === 'function') {
    planet.upAt(absPos, res);
    if (res.lengthSq() < 1e-12) return res.set(0, 0, 0);
    res.normalize().multiplyScalar(-1);
  } else {
    centerOf(planet, _center);
    res.copy(_center).sub(absPos).multiplyScalar(1 / dist);
  }

  const ratio = spec.radius / dist;
  const mag = Math.min(g0 * ratio * ratio, g0 * 3);
  return res.multiplyScalar(mag);
}

/**
 * Densite atmospherique 0..1 a une altitude donnee (metres au-dessus du sol).
 * Delegue au module d'atmosphere s'il est monte, sinon profil exponentiel
 * derive du spec (et 0 si la planete n'a pas d'atmosphere du tout).
 */
export function atmosphereDensity(planet, altitude) {
  if (!planet) return 0;
  const atmo = planet.atmosphere;
  if (atmo && typeof atmo.densityAt === 'function') {
    const d = atmo.densityAt(altitude);
    return Number.isFinite(d) ? saturate(d) : 0;
  }
  const spec = planet.spec;
  const sa = spec && spec.atmosphere;
  if (!sa) return 0;
  const h = sa.height || (spec.radius || 1) * 0.1;
  if (altitude >= h) return 0;
  const seaDensity = sa.densitySea === undefined ? 1 : sa.densitySea;
  // Decroissance exponentielle, puis fondu lineaire jusqu'au plafond de la
  // couche pour ne pas laisser de marche a la sortie.
  const fall = Math.exp(-Math.max(altitude, 0) / (h * 0.34));
  const fade = saturate(1 - altitude / h);
  return saturate(seaDensity * fall * fade);
}

// Resultat partage : lu immediatement par l'appelant, jamais conserve.
const _contact = { hit: false, groundRadius: 0, depth: 0, normal: new THREE.Vector3(0, 1, 0) };

/**
 * Contact avec le sol sous `absPos`, avec une marge de securite.
 * `depth` > 0 signifie penetration de `depth` metres sous (sol + margin).
 * La surface liquide (mer, lave, banquise) est traitee comme un sol : on ne
 * coule pas, on se pose dessus. Les geantes gazeuses n'ont aucun contact.
 */
export function groundContact(planet, absPos, margin = 0) {
  _contact.hit = false;
  _contact.groundRadius = 0;
  _contact.depth = 0;
  _contact.normal.set(0, 1, 0);
  if (!planet || !planet.spec) return _contact;
  const spec = planet.spec;
  if (spec.isGas || spec.type === 'gas') return _contact;

  const hasTransform = typeof planet.toLocal === 'function';
  toLocalOf(planet, absPos, _local);
  const dist = _local.length();
  if (dist < 1e-6) {
    _contact.groundRadius = spec.radius;
    _contact.depth = spec.radius + margin;
    _contact.hit = true;
    return _contact;
  }
  _dir.copy(_local).multiplyScalar(1 / dist);

  const hf = planet.heightField;
  let groundRadius = spec.radius;
  if (hf && typeof hf.surfaceRadius === 'function') groundRadius = hf.surfaceRadius(_dir);

  // Niveau de la mer : plancher de la surface praticable.
  const sea = spec.seaLevel;
  let onLiquid = false;
  if (sea !== null && sea !== undefined) {
    const seaRadius = spec.radius + sea;
    if (seaRadius > groundRadius) {
      groundRadius = seaRadius;
      onLiquid = true;
    }
  }

  _contact.groundRadius = groundRadius;
  _contact.depth = groundRadius + margin - dist;
  _contact.hit = _contact.depth > 0;

  if (onLiquid || !hf || typeof hf.normalAt !== 'function') {
    _nrm.copy(_dir);
  } else {
    hf.normalAt(_dir, _nrm);
    if (_nrm.lengthSq() < 1e-10) _nrm.copy(_dir);
  }
  // Retour en absolu : la rotation de la planete n'est appliquee que si l'on
  // sait qu'un vrai passage local a eu lieu.
  if (hasTransform) {
    const q = planet.quaternion || (planet.object3D && planet.object3D.quaternion);
    if (q) _nrm.applyQuaternion(q);
  }
  _contact.normal.copy(_nrm).normalize();
  return _contact;
}

// Trois bruits decorreles, un par axe. Instancies une seule fois.
const _tA = makeNoise3D(0x51de0001);
const _tB = makeNoise3D(0x51de0002);
const _tC = makeNoise3D(0x51de0003);
const TURB_F1 = 0.31;
const TURB_F2 = 1.17;
const TURB_F3 = 4.63;
const TURB_NORM = 1 / (1 + 0.44 + 0.17);

/**
 * Turbulence lisse a 3 frequences, deterministe en fonction du temps.
 * Utilisee par les geantes gazeuses, la rentree atmospherique et la secousse
 * de camera. `strength` est l'amplitude crete du resultat.
 */
export function turbulence(t, strength = 1, out) {
  const res = out || new THREE.Vector3();
  const x =
    _tA(t * TURB_F1, 0.0, 0.0) + _tA(t * TURB_F2, 4.7, 0.0) * 0.44 + _tA(t * TURB_F3, 9.3, 0.0) * 0.17;
  const y =
    _tB(t * TURB_F1, 1.3, 0.0) + _tB(t * TURB_F2, 6.1, 0.0) * 0.44 + _tB(t * TURB_F3, 12.7, 0.0) * 0.17;
  const z =
    _tC(t * TURB_F1, 2.9, 0.0) + _tC(t * TURB_F2, 7.9, 0.0) * 0.44 + _tC(t * TURB_F3, 15.1, 0.0) * 0.17;
  const k = strength * TURB_NORM;
  return res.set(x * k, y * k, z * k);
}

/**
 * Integration semi-implicite (Euler symplectique) : la vitesse est mise a jour
 * avant la position, ce qui est stable pour une gravite centrale.
 * `forces` est traite comme une acceleration (masse = 1) et peut etre
 * n'importe quel objet `{x, y, z}`.
 */
export function integrate(state, forces, dt) {
  if (!state || !(dt > 0)) return;
  const v = state.velocity;
  const p = state.position;
  if (!v || !p) return;
  if (forces) {
    v.x += forces.x * dt;
    v.y += forces.y * dt;
    v.z += forces.z * dt;
  }
  p.x += v.x * dt;
  p.y += v.y * dt;
  p.z += v.z * dt;
}

/** Petit utilitaire partage : borne une vitesse sans changer sa direction. */
export function clampSpeed(velocity, maxSpeed) {
  const s = velocity.length();
  if (s > maxSpeed && s > 1e-6) velocity.multiplyScalar(clamp(maxSpeed / s, 0, 1));
  return velocity;
}
