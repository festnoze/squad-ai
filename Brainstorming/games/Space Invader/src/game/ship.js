// Le vaisseau du joueur : maillage procedural low-poly + modele de vol.
//
// Choix de conception :
// - Convention three : le nez pointe vers -Z, le dessus vers +Y.
// - `state.position` est ABSOLUE (origine = soleil). Le visuel `object3D` est
//   place en espace vue par main.js : on ne touche donc jamais a sa position,
//   seulement a son orientation.
// - Le pilotage est arcade et tolerant : on ne meurt pas, on rebondit. Un choc
//   violent se traduit par un rebond amorti et une secousse de camera
//   (telemetry.impact, lu par le rig de camera).
// - Aucune allocation par frame : tous les vecteurs de travail sont crees a la
//   construction, dans la closure.

import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { SHIP } from '../core/settings.js';
import { clamp, damp, saturate } from '../core/math.js';
import { groundContact, integrate, turbulence } from '../world/physics.js';

// ---------------------------------------------------------------------------
// Geometrie
// ---------------------------------------------------------------------------

/**
 * Prisme low-poly a partir d'un polygone convexe du plan XZ, extrude selon Y.
 * Le sens de parcours est normalise pour que les faces regardent dehors.
 * Sert aux ailes delta et aux derives.
 */
function prismGeometry(points, thickness) {
  // Aire signee : si elle est positive, la face haute serait orientee vers -Y.
  let area = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    area += a[0] * b[1] - b[0] * a[1];
  }
  const pts = area > 0 ? points.slice().reverse() : points.slice();

  const n = pts.length;
  const h = thickness * 0.5;
  const pos = [];
  const uv = [];
  const idx = [];

  // Face haute.
  for (let i = 0; i < n; i++) {
    pos.push(pts[i][0], h, pts[i][1]);
    uv.push(i / n, 1);
  }
  for (let i = 1; i < n - 1; i++) idx.push(0, i, i + 1);

  // Face basse.
  const base = n;
  for (let i = 0; i < n; i++) {
    pos.push(pts[i][0], -h, pts[i][1]);
    uv.push(i / n, 0);
  }
  for (let i = 1; i < n - 1; i++) idx.push(base, base + i + 1, base + i);

  // Cotes.
  for (let i = 0; i < n; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % n];
    const s = pos.length / 3;
    pos.push(a[0], h, a[1], b[0], h, b[1], b[0], -h, b[1], a[0], -h, a[1]);
    uv.push(0, 1, 1, 1, 1, 0, 0, 0);
    idx.push(s, s + 1, s + 2, s, s + 2, s + 3);
  }

  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

/** Meme polygone, miroir selon X (aile ou derive opposee). */
function mirrorX(points) {
  return points.map((p) => [-p[0], p[1]]);
}

// Contour de l'aile delta droite, dans le plan XZ (z croissant = vers l'arriere).
const WING = [
  [0.42, -0.62],
  [2.45, 0.42],
  [2.5, 1.05],
  [0.48, 1.5],
];

// Contour d'une derive : x sert de hauteur, il devient +Y apres rotation.
const FIN = [
  [0.0, 0.55],
  [0.92, 1.35],
  [0.92, 1.72],
  [0.0, 1.85],
];

/** Assemble le fuselage, les ailes, les tuyeres et les derives. */
function buildShipGeometries() {
  const hullParts = [];
  const accentParts = [];

  // Fuselage effile, axe le long de Z (rotateX(-PI/2) envoie +Y vers -Z).
  const body = new THREE.CylinderGeometry(0.26, 0.62, 3.0, 10, 1, false);
  body.rotateX(-Math.PI / 2);
  body.scale(1.0, 0.78, 1.0);
  hullParts.push(body);

  // Nez conique, pointe vers -Z.
  const nose = new THREE.ConeGeometry(0.26, 1.15, 10, 1, false);
  nose.rotateX(-Math.PI / 2);
  nose.scale(1.0, 0.78, 1.0);
  nose.translate(0, 0, -2.07);
  hullParts.push(nose);

  // Bloc arriere.
  const tail = new THREE.CylinderGeometry(0.62, 0.44, 0.6, 10, 1, false);
  tail.rotateX(-Math.PI / 2);
  tail.scale(1.0, 0.78, 1.0);
  tail.translate(0, 0, 1.78);
  hullParts.push(tail);

  // Ailes delta.
  const wingR = prismGeometry(WING, 0.16);
  const wingL = prismGeometry(mirrorX(WING), 0.16);
  hullParts.push(wingR, wingL);

  // Bord d'attaque orange (fine bande le long de l'aile).
  const edgeR = prismGeometry(
    [
      [0.45, -0.6],
      [2.42, 0.44],
      [2.4, 0.62],
      [0.5, -0.36],
    ],
    0.18,
  );
  const edgeL = prismGeometry(
    mirrorX([
      [0.45, -0.6],
      [2.42, 0.44],
      [2.4, 0.62],
      [0.5, -0.36],
    ]),
    0.18,
  );
  accentParts.push(edgeR, edgeL);

  // Derives verticales : plaque XZ redressee (rotateZ envoie +X vers +Y).
  const finR = prismGeometry(FIN, 0.1);
  finR.rotateZ(Math.PI / 2);
  finR.translate(0.62, 0.1, 0);
  const finL = prismGeometry(FIN, 0.1);
  finL.rotateZ(Math.PI / 2);
  finL.translate(-0.62, 0.1, 0);
  hullParts.push(finR, finL);

  // Deux tuyeres cylindriques a l'arriere.
  for (const sx of [-1, 1]) {
    const nac = new THREE.CylinderGeometry(0.3, 0.34, 1.5, 9, 1, false);
    nac.rotateX(-Math.PI / 2);
    nac.translate(sx * 0.72, -0.06, 1.25);
    hullParts.push(nac);

    const ring = new THREE.TorusGeometry(0.3, 0.06, 6, 10);
    ring.translate(sx * 0.72, -0.06, 1.98);
    accentParts.push(ring);
  }

  const hull = mergeGeometries(hullParts, false);
  const accent = mergeGeometries(accentParts, false);
  for (const g of hullParts) g.dispose();
  for (const g of accentParts) g.dispose();

  // Verriere : demi-sphere aplatie et allongee.
  const canopy = new THREE.SphereGeometry(0.46, 12, 6, 0, Math.PI * 2, 0, Math.PI * 0.55);
  canopy.scale(0.92, 0.5, 1.7);
  canopy.translate(0, 0.2, -0.72);

  // Disques de tuyere (lueur moteur).
  const glowParts = [];
  for (const sx of [-1, 1]) {
    const disc = new THREE.CircleGeometry(0.27, 12); // dans le plan XY, face +Z
    disc.translate(sx * 0.72, -0.06, 2.02);
    glowParts.push(disc);
  }
  const glow = mergeGeometries(glowParts, false);
  for (const g of glowParts) g.dispose();

  return { hull, accent, canopy, glow };
}

// ---------------------------------------------------------------------------
// Modele de vol
// ---------------------------------------------------------------------------

// Inclinaison maximale prise automatiquement dans un virage, en radians.
const BANK_MAX = 0.52;

const EMPTY_AXES = { pitch: 0, yaw: 0, roll: 0, thrust: 0, strafe: 0, vertical: 0 };
const EMPTY_BUTTONS = { boost: false, brake: false };
const DEFAULT_UP = new THREE.Vector3(0, 1, 0);
const EMPTY_ENV = {
  planet: null,
  altitude: 1e12,
  up: DEFAULT_UP,
  gravity: null,
  density: 0,
  groundRadius: 0,
  insideGas: 0,
  // Distance a la surface du corps le PLUS PROCHE, tous corps confondus (et pas
  // seulement celui dont on subit l'influence). Alimente le gouverneur.
  nearestDistance: Infinity,
};

export function createShip() {
  const geo = buildShipGeometries();

  const hullMat = new THREE.MeshStandardMaterial({
    color: 0xe6e3d8,
    metalness: 0.32,
    roughness: 0.48,
    flatShading: true,
  });
  const accentMat = new THREE.MeshStandardMaterial({
    color: 0xff7a26,
    emissive: 0xff5a10,
    emissiveIntensity: 0.25,
    metalness: 0.35,
    roughness: 0.42,
    flatShading: true,
  });
  const canopyMat = new THREE.MeshStandardMaterial({
    color: 0x0b1520,
    metalness: 0.95,
    roughness: 0.06,
    flatShading: true,
  });
  const glowMat = new THREE.MeshBasicMaterial({
    color: 0x2a1206,
    toneMapped: false,
    side: THREE.DoubleSide,
  });

  const object3D = new THREE.Group();
  object3D.name = 'ship';
  const hullMesh = new THREE.Mesh(geo.hull, hullMat);
  const accentMesh = new THREE.Mesh(geo.accent, accentMat);
  const canopyMesh = new THREE.Mesh(geo.canopy, canopyMat);
  const glowMesh = new THREE.Mesh(geo.glow, glowMat);
  hullMesh.castShadow = true;
  accentMesh.castShadow = true;
  object3D.add(hullMesh, accentMesh, canopyMesh, glowMesh);
  // Le vaisseau est toujours proche de la camera : pas de culling utile.
  object3D.frustumCulled = false;
  for (const m of object3D.children) m.frustumCulled = false;

  const state = {
    position: new THREE.Vector3(),
    velocity: new THREE.Vector3(),
    quaternion: new THREE.Quaternion(),
    throttle: 0,
    boost: 0,
    landed: false,
  };

  const telemetry = {
    speed: 0,
    altitude: 0,
    thrust: 0,
    gForce: 0,
    verticalSpeed: 0,
    mach: 0,
    // Extras utiles au HUD, a la camera et au son (hors contrat, additifs).
    boost: 0,
    pulse: 0,
    impact: 0,
    density: 0,
    speedLimit: 0,
    landed: false,
  };

  // Vecteurs de travail (closure) : aucune allocation dans update().
  const _acc = new THREE.Vector3();
  const _fwd = new THREE.Vector3();
  const _shipUp = new THREE.Vector3();
  const _shipRight = new THREE.Vector3();
  const _up = new THREE.Vector3(0, 1, 0);
  const _upNow = new THREE.Vector3(0, 1, 0);
  const _right = new THREE.Vector3();
  const _desUp = new THREE.Vector3();
  const _cross = new THREE.Vector3();
  const _tmp = new THREE.Vector3();
  const _turb = new THREE.Vector3();
  const _euler = new THREE.Euler(0, 0, 0, 'XYZ');
  const _dq = new THREE.Quaternion();
  const _qc = new THREE.Quaternion();

  let time = 0;
  let pulse = 0;

  function update(dt, input, env) {
    if (!(dt > 0)) return;
    if (dt > 1 / 15) dt = 1 / 15; // robustesse apres un onglet en arriere-plan
    time += dt;

    const ax = (input && input.axes) || EMPTY_AXES;
    const btn = (input && input.buttons) || EMPTY_BUTTONS;
    const e = env || EMPTY_ENV;

    const density = saturate(e.density || 0);
    const inAtmo = density > 0.02;
    const gas = saturate(e.insideGas || 0);

    if (e.up && e.up.isVector3 && e.up.lengthSq() > 1e-8) _up.copy(e.up).normalize();
    else _up.copy(DEFAULT_UP);

    // --- Commandes -------------------------------------------------------
    const thrustIn = saturate(ax.thrust || 0);
    const pitchIn = clamp(ax.pitch || 0, -1, 1);
    const yawIn = clamp(ax.yaw || 0, -1, 1);
    const rollIn = clamp(ax.roll || 0, -1, 1);
    const strafeIn = clamp(ax.strafe || 0, -1, 1);
    const vertIn = clamp(ax.vertical || 0, -1, 1);
    const boostHeld = !!btn.boost;
    const braking = !!btn.brake;

    if (state.landed && (thrustIn > 0.12 || vertIn > 0.12)) state.landed = false;

    state.throttle = damp(state.throttle, thrustIn, 6, dt);
    state.boost = damp(state.boost, boostHeld ? 1 : 0, 5, dt);
    const boostMul = 1 + state.boost * (SHIP.boostFactor - 1);

    // --- Attitude --------------------------------------------------------
    // Les ailes mordent l'air : la manoeuvrabilite grimpe avec la densite et
    // tombe (sans disparaitre, RCS) dans le vide.
    // Dans le vide, les propulseurs d'attitude restent francs : naviguer entre
    // deux mondes ne doit pas donner l'impression de piloter une baignoire.
    const agility =
      SHIP.spaceAgility + (SHIP.atmoAgility - SHIP.spaceAgility) * Math.min(density, 1);
    const authority = state.landed ? 0.22 : 1;
    _euler.set(
      pitchIn * SHIP.pitchRate * agility * authority * dt,
      yawIn * SHIP.yawRate * agility * authority * dt,
      -rollIn * SHIP.rollRate * agility * authority * dt,
    );
    _dq.setFromEuler(_euler);
    state.quaternion.multiply(_dq).normalize();

    _fwd.set(0, 0, -1).applyQuaternion(state.quaternion);
    _shipUp.set(0, 1, 0).applyQuaternion(state.quaternion);
    _shipRight.set(1, 0, 0).applyQuaternion(state.quaternion);

    // --- Accelerations ---------------------------------------------------
    _acc.set(0, 0, 0);
    if (e.gravity) _acc.addScaledVector(e.gravity, SHIP.gravityScale);

    const thrustBase = inAtmo ? SHIP.thrustAtmo : SHIP.thrustSpace;
    const thrustMag = thrustBase * state.throttle * boostMul;
    if (thrustMag > 0) _acc.addScaledVector(_fwd, thrustMag);

    // Propulseurs d'attitude lateraux / verticaux (confort de pilotage).
    const rcs = thrustBase * 0.28;
    if (strafeIn !== 0) _acc.addScaledVector(_shipRight, strafeIn * rcs);
    if (vertIn !== 0) _acc.addScaledVector(_shipUp, vertIn * rcs);

    // Mode pulse : uniquement hors atmosphere, coupe des qu'on entre dans une
    // atmosphere (sinon on traverse la planete).
    const wantPulse = boostHeld && !inAtmo && !braking && !state.landed;
    pulse = damp(pulse, wantPulse ? 1 : 0, wantPulse ? 1.8 : 9, dt);
    if (inAtmo) pulse = 0;
    // Aucun plafond d'acceleration ici : on pousse tant que le joueur maintient
    // la commande. C'est le gouverneur de proximite (plus bas) qui borne la
    // vitesse, et lui seul.
    if (pulse > 0.01) _acc.addScaledVector(_fwd, SHIP.pulseAccel * pulse);

    const speed0 = state.velocity.length();

    if (inAtmo) {
      // Trainee quadratique calibree pour plafonner a atmoMaxSpeed.
      const vmax = SHIP.atmoMaxSpeed * boostMul;
      if (speed0 > 1e-4) {
        _tmp.copy(state.velocity).multiplyScalar(1 / speed0);
        const q = speed0 / vmax;
        const dragMag =
          thrustBase * boostMul * q * q * (0.3 + 0.7 * Math.min(density, 1)) +
          SHIP.dragAtmo * density * speed0;
        _acc.addScaledVector(_tmp, -dragMag);
      }

      // Portance : s'oppose a la gravite, proportionnelle a vitesse et densite,
      // et perdue quand on vole sur le dos.
      if (e.gravity) {
        const gMag = e.gravity.length();
        const align = saturate(_shipUp.dot(_up));
        const vFactor = saturate(speed0 / (SHIP.atmoMaxSpeed * 0.32));
        const lift =
          gMag * SHIP.liftFactor * vFactor * Math.min(density, 1) * (0.3 + 0.7 * align);
        _acc.addScaledVector(_up, lift);
      }

      // Auto-nivellement doux : on annule progressivement le roulis par rapport
      // a la verticale locale, sauf si le joueur agit sur le roulis.
      if (Math.abs(rollIn) < 0.08 && Math.abs(_fwd.dot(_up)) < 0.985) {
        _right.crossVectors(_fwd, _up).normalize();
        _desUp.crossVectors(_right, _fwd).normalize();
        // Virage coordonne : quand le joueur tourne (Q / D), l'assiette visee
        // s'incline DANS le virage. Sans cela, tourner uniquement au lacet donne
        // un vol a plat qui derape et ne ressemble a rien.
        // Signe : une rotation positive autour du nez (-Z) incline la verticale
        // du vaisseau vers sa DROITE, alors que yaw > 0 tourne a GAUCHE. Il faut
        // donc inverser, sinon le vaisseau se penche a l'exterieur du virage.
        const bank = -yawIn * BANK_MAX * Math.min(density, 1);
        if (Math.abs(bank) > 1e-3) {
          _qc.setFromAxisAngle(_fwd, bank);
          _desUp.applyQuaternion(_qc).normalize();
        }
        const d = clamp(_shipUp.dot(_desUp), -1, 1);
        _cross.crossVectors(_shipUp, _desUp);
        const angle = Math.atan2(_cross.dot(_fwd), d);
        if (Math.abs(angle) > 1e-4) {
          // On rejoint l'assiette visee plus vite quand le joueur tourne :
          // sinon l'inclinaison arrive apres le virage et le pilotage semble
          // mou. Au neutre, le retour a plat reste doux.
          const rate = SHIP.autoLevel * (1 + 2.2 * Math.abs(yawIn));
          const k = 1 - Math.exp(-rate * Math.min(density, 1) * dt);
          _qc.setFromAxisAngle(_fwd, angle * k);
          state.quaternion.premultiply(_qc).normalize();
        }
      }
    }

    // Turbulence de geante gazeuse : secoue fort, mais reste pilotable.
    if (gas > 0.001) {
      turbulence(time, 46 * gas, _turb);
      _acc.add(_turb);
      turbulence(time * 0.61 + 17.3, 0.6 * gas, _turb);
      _euler.set(_turb.x * dt, _turb.y * dt, _turb.z * dt);
      _dq.setFromEuler(_euler);
      state.quaternion.multiply(_dq).normalize();
    }

    // Sous pulse, la trajectoire suit le nez : on fait pivoter le vecteur
    // vitesse vers l'avant du vaisseau en conservant sa norme. On va donc la ou
    // l'on pointe, ce qui est le seul moyen de viser un monde a 2 millions
    // d'unites sans deriver indefiniment de cote.
    if (pulse > 0.05) {
      const spv = state.velocity.length();
      if (spv > 1) {
        _tmp.copy(_fwd).multiplyScalar(spv);
        state.velocity.lerp(_tmp, 1 - Math.exp(-SHIP.pulseTrackRate * pulse * dt));
      }
    }

    // --- Integration -----------------------------------------------------
    integrate(state, _acc, dt);

    if (!inAtmo) state.velocity.multiplyScalar(Math.exp(-SHIP.spaceDamping * dt));
    if (braking) {
      state.velocity.multiplyScalar(Math.exp(-SHIP.brakeFactor * dt));
      pulse = 0;
    }

    // Plafonds de vitesse. En atmosphere : ferme. Dans le vide : uniquement le
    // gouverneur de proximite, qui laisse la vitesse grimper sans limite utile
    // loin de tout et la fait retomber d'elle-meme en approche.
    const nearestSurface = Number.isFinite(e.nearestDistance) ? e.nearestDistance : Infinity;
    const governor = clamp(
      nearestSurface * SHIP.pulseProximityRate,
      SHIP.pulseMinSpeed,
      SHIP.pulseMaxSpeed,
    );
    telemetry.speedLimit = inAtmo ? SHIP.atmoMaxSpeed * boostMul : governor;

    const sp = state.velocity.length();
    if (sp > 1e-5) {
      let capSpeed;
      let lambda;
      if (inAtmo) {
        capSpeed = SHIP.atmoMaxSpeed * boostMul;
        lambda = 7;
      } else if (pulse > 0.05) {
        capSpeed = governor;
        lambda = 8;
      } else {
        capSpeed = Math.min(SHIP.spaceMaxSpeed * boostMul, governor);
        lambda = 0.9; // sortie de pulse : longue deceleration lisible
      }
      if (sp > capSpeed) state.velocity.multiplyScalar(damp(sp, capSpeed, lambda, dt) / sp);
    }

    // --- Collision sol ---------------------------------------------------
    telemetry.impact *= Math.exp(-2.6 * dt);
    let altitude = Number.isFinite(e.altitude) ? e.altitude : 1e12;
    _upNow.copy(_up);
    const planet = e.planet;

    if (planet && planet.spec && !planet.spec.isGas) {
      const c = groundContact(planet, state.position, SHIP.minAltitude);
      if (typeof planet.upAt === 'function') {
        planet.upAt(state.position, _tmp);
        if (_tmp.lengthSq() > 1e-8) _upNow.copy(_tmp).normalize();
      }
      altitude = SHIP.minAltitude - c.depth;

      if (c.hit) {
        // On repousse au-dessus du plancher de securite. Jamais de destruction.
        state.position.addScaledVector(_upNow, c.depth);
        const vn = state.velocity.dot(_upNow);
        let impact = 0;
        if (vn < 0) {
          impact = -vn;
          state.velocity.addScaledVector(_upNow, -vn);
          if (impact > SHIP.landingSpeed) {
            // Rebond amorti + secousse.
            state.velocity.addScaledVector(_upNow, impact * 0.3);
            state.velocity.multiplyScalar(0.7);
            telemetry.impact = Math.max(
              telemetry.impact,
              saturate(impact / (SHIP.landingSpeed * 5)),
            );
          }
        }
        _tmp.copy(state.velocity).addScaledVector(_upNow, -state.velocity.dot(_upNow));
        const horiz = _tmp.length();
        if (impact < SHIP.landingSpeed && horiz < SHIP.landingSpeed * 1.6 && thrustIn < 0.12) {
          state.landed = true;
        }
        if (state.landed) {
          // Frottement au sol, moteurs au ralenti.
          state.velocity.multiplyScalar(Math.exp(-5.0 * dt));
          state.throttle = damp(state.throttle, thrustIn, 8, dt);
        }
        altitude = Math.max(altitude, 0);
      } else if (altitude > SHIP.minAltitude * 1.4) {
        state.landed = false;
      }
    } else {
      state.landed = false;
    }

    // --- Telemetrie ------------------------------------------------------
    const finalSpeed = state.velocity.length();
    telemetry.speed = finalSpeed;
    telemetry.altitude = altitude;
    telemetry.thrust = saturate(state.throttle);
    telemetry.boost = state.boost;
    telemetry.pulse = pulse;
    telemetry.density = density;
    telemetry.landed = state.landed;
    telemetry.verticalSpeed = state.velocity.dot(_upNow);
    telemetry.mach = finalSpeed / (300 * Math.max(0.15, density));

    // Facteur de charge : acceleration hors gravite.
    _tmp.copy(_acc);
    if (e.gravity) _tmp.addScaledVector(e.gravity, -SHIP.gravityScale);
    telemetry.gForce = damp(telemetry.gForce, _tmp.length() / 9.81, 8, dt);

    // Rentree atmospherique : contribue a la secousse lue par la camera.
    if (density > 0.03) {
      const reentry = saturate(finalSpeed / SHIP.atmoMaxSpeed) * saturate(density * 1.6);
      telemetry.impact = Math.max(telemetry.impact, reentry * 0.35);
    }
    if (gas > 0.001) telemetry.impact = Math.max(telemetry.impact, gas * 0.4);

    // --- Visuel ----------------------------------------------------------
    object3D.quaternion.copy(state.quaternion);
    const heat = saturate(
      state.landed ? 0.1 : state.throttle * (0.55 + 0.45 * state.boost) + pulse * 0.6,
    );
    // Lueur de tuyere : on ne joue que sur la couleur (une mise a l'echelle du
    // mesh fusionne deplacerait les deux disques).
    glowMat.color.setRGB(0.12 + 1.5 * heat, 0.05 + 0.75 * heat, 0.02 + 0.35 * heat);
    accentMat.emissiveIntensity = 0.25 + 0.9 * heat;
  }

  function forward(out) {
    const res = out || new THREE.Vector3();
    return res.set(0, 0, -1).applyQuaternion(state.quaternion);
  }

  function up(out) {
    const res = out || new THREE.Vector3();
    return res.set(0, 1, 0).applyQuaternion(state.quaternion);
  }

  function dispose() {
    geo.hull.dispose();
    geo.accent.dispose();
    geo.canopy.dispose();
    geo.glow.dispose();
    hullMat.dispose();
    accentMat.dispose();
    canopyMat.dispose();
    glowMat.dispose();
    object3D.clear();
  }

  return { object3D, state, update, telemetry, forward, up, dispose };
}
