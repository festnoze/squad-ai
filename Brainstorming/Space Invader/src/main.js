// TERRAFORM ODYSSEY - point d'entree et boucle de jeu.
//
// Responsabilites de ce fichier, et de lui seul :
//   - assembler tous les modules,
//   - tenir viewOrigin (= position du vaisseau) et le rendu relatif camera,
//   - calculer l'environnement de vol (planete courante, gravite, densite),
//   - alimenter le HUD et la logique de decouverte,
//   - gerer le saut hyperspatial et l'ecran titre.

import * as THREE from 'three';
import Stats from 'stats.js';
import { createEngine } from './core/engine.js';
import { createInput } from './core/input.js';
import { createAudio } from './core/audio.js';
import { getQuality, setQuality, guessQuality, SCALE, SHIP } from './core/settings.js';
import { formatDistance, easeInOutCubic, damp, saturate } from './core/math.js';
import { getSystem } from './gen/planetSpec.js';
import { SolarSystem } from './world/solarSystem.js';
import { createStarfield } from './render/starfield.js';
import { createSun } from './render/sun.js';
import { createSpeedLines, createReentryGlow, createEngineTrail } from './render/fx.js';
import { createShip } from './game/ship.js';
import { createCameraRig } from './game/camera.js';
import { createHUD } from './game/hud.js';
import { createDiscovery } from './game/discovery.js';
import { STR } from './game/strings.js';
import { gravityAt } from './world/physics.js';

const canvas = document.getElementById('scene');
const loading = document.getElementById('loading');

const system = getSystem();
const hud = createHUD({ system, strings: STR });
const audio = createAudio();

// Vecteurs de travail, alloues une fois.
const _up = new THREE.Vector3();
const _gravity = new THREE.Vector3();
const _sunDirTarget = new THREE.Vector3(1, 0, 0);
const _sunDirSmooth = new THREE.Vector3(1, 0, 0);
const _sunView = new THREE.Vector3();
const _tmp = new THREE.Vector3();
const _tmp2 = new THREE.Vector3();
const _tmp3 = new THREE.Vector3();
const _zero = new THREE.Vector3();

const env = {
  planet: null,
  altitude: Infinity,
  up: new THREE.Vector3(0, 1, 0),
  gravity: new THREE.Vector3(),
  density: 0,
  groundRadius: 0,
  insideGas: 0,
  // Distance a la surface du corps le plus proche, tous corps confondus.
  // Le vaisseau s'en sert pour son gouverneur de vitesse dans le vide.
  nearestDistance: Infinity,
};

const stats = {
  elapsed: 0,
  distanceTravelled: 0,
  planetsVisited: new Set(),
};

hud.showTitle((qualityName) => {
  setQuality(qualityName || guessQuality());
  boot().catch((err) => {
    console.error('[main] demarrage impossible', err);
    if (loading) loading.textContent = `Erreur de demarrage : ${err.message}`;
  });
});

async function boot() {
  const quality = getQuality();
  if (loading) {
    loading.classList.remove('hidden');
    loading.textContent = STR.loading || 'Generation du systeme...';
  }

  const engine = createEngine({ canvas });
  const { scene, camera } = engine;

  // Brouillard permanent (densite quasi nulle dans le vide) : changer scene.fog
  // de null a non-null recompilerait tous les shaders, on l'evite.
  scene.fog = new THREE.FogExp2(0x000000, 1e-7);

  const solar = new SolarSystem({ scene, system, quality });
  const starfield = createStarfield({ seed: 1337, quality });
  scene.add(starfield.object3D);
  if (starfield.background) scene.background = starfield.background;

  const sun = createSun({ star: system.star, quality });
  scene.add(sun.object3D);
  const sunTarget = new THREE.Object3D();
  scene.add(sunTarget);
  if (sun.light) sun.light.target = sunTarget;

  const ship = createShip();
  scene.add(ship.object3D);
  const trail = createEngineTrail();
  ship.object3D.add(trail.object3D);
  const reentry = createReentryGlow();
  ship.object3D.add(reentry.object3D);
  const speedLines = createSpeedLines({ quality });
  camera.add(speedLines.object3D);

  const input = createInput(canvas);
  const rig = createCameraRig({ camera });
  const discovery = createDiscovery({ audio, strings: STR });

  // ------------------------------------------------------------------
  // Depart : posé sur la planete d'origine, au soleil, sur la terre ferme.
  // ------------------------------------------------------------------
  const home = solar.planets.find((p) => p.spec.isHome) || solar.planets[2];
  const startDir = findStartDirection(home);
  const startRadius = home.groundRadiusAt(
    _tmp.copy(startDir).multiplyScalar(home.spec.radius * 2).add(home.absolutePosition),
  );
  ship.state.position
    .copy(startDir)
    .multiplyScalar(startRadius + 60)
    .add(home.absolutePosition);
  ship.state.velocity.set(0, 0, 0);
  orientShipOnSurface(ship, home);
  engine.viewOrigin.copy(ship.state.position);

  await home.activate();

  // ------------------------------------------------------------------
  // Cible de navigation, saut hyperspatial
  // ------------------------------------------------------------------
  let targetIndex = solar.planets.findIndex((p) => !p.spec.isHome);
  let warp = null;
  const navItems = solar.planets.map((p) => ({
    id: p.spec.id,
    name: p.spec.name,
    distance: 0,
    type: p.spec.typeLabel,
    tempClass: p.spec.tempLabel,
    progress: 0,
    active: false,
  }));

  function cycleTarget(step) {
    const n = solar.planets.length;
    targetIndex = (targetIndex + step + n) % n;
    const p = solar.planets[targetIndex];
    if (hud.setTarget) hud.setTarget(p.spec.id);
    hud.toast(`${STR.targetSet || 'Cible'} : ${p.spec.name}`, 'info');
    audio.play('ui');
  }

  function startWarp() {
    const target = solar.planets[targetIndex];
    if (!target || warp) return;
    if (env.planet === target && env.altitude < target.spec.radius * 2) {
      hud.toast(STR.warpTooClose || 'Deja sur place', 'warn');
      return;
    }
    const dir = _tmp.copy(ship.state.position).sub(target.absolutePosition);
    if (dir.lengthSq() < 1) dir.set(1, 0, 0);
    dir.normalize();
    const dest = new THREE.Vector3()
      .copy(dir)
      .multiplyScalar(target.spec.radius * 3.4)
      .add(target.absolutePosition);
    warp = {
      from: ship.state.position.clone(),
      to: dest,
      t: 0,
      duration: SHIP.warpTime,
      target,
    };
    ship.state.velocity.set(0, 0, 0);
    ship.state.landed = false;
    audio.play('warp');
    rig.shake(0.6);
    hud.toast(`${STR.warpTo || 'Saut vers'} ${target.spec.name}`, 'info');
  }

  window.addEventListener('keydown', (e) => {
    if (e.code === 'KeyT') cycleTarget(1);
    else if (e.code === 'KeyR') cycleTarget(-1);
  });
  canvas.addEventListener('click', () => input.setLocked(true));
  if (hud.setTarget) hud.setTarget(solar.planets[targetIndex].spec.id);

  // ------------------------------------------------------------------
  // Outillage de mise au point (touche G)
  // ------------------------------------------------------------------
  const fps = new Stats();
  fps.dom.style.cssText = 'position:fixed;top:8px;left:8px;z-index:50;display:none';
  document.body.appendChild(fps.dom);
  let gui = null;
  let guiVisible = false;
  async function toggleGui() {
    if (!gui) {
      const { default: GUI } = await import('lil-gui');
      gui = new GUI({ title: 'Terraform Odyssey' });
      const dbg = {
        planete: '-',
        altitude: 0,
        patches: 0,
        arbres: 0,
        faune: 0,
        exposition: 1.05,
        rejoindreCible: () => startWarp(),
      };
      gui.add(dbg, 'planete').listen().disable();
      gui.add(dbg, 'altitude').listen().disable();
      gui.add(dbg, 'patches').listen().disable();
      gui.add(dbg, 'arbres').listen().disable();
      gui.add(dbg, 'faune').listen().disable();
      gui.add(dbg, 'exposition', 0.4, 2, 0.05).onChange((v) => engine.setExposure(v));
      gui.add(dbg, 'rejoindreCible');
      gui.userData = dbg;
    }
    guiVisible = !guiVisible;
    gui.domElement.style.display = guiVisible ? '' : 'none';
    fps.dom.style.display = guiVisible ? '' : 'none';
  }

  // ------------------------------------------------------------------
  // Boucle
  // ------------------------------------------------------------------
  let won = false;
  discovery.onWin((report) => {
    won = true;
    input.setLocked(false);
    hud.showWin({
      ...report,
      elapsed: stats.elapsed,
      planetsVisited: stats.planetsVisited.size,
      distanceTravelled: stats.distanceTravelled,
    });
  });
  discovery.onDiscover((e) => {
    const label = STR[`element_${e.key}`] || e.key;
    hud.toast(`${label} ${STR.confirmed || 'confirme'}`, 'good');
  });
  if (discovery.onHint) discovery.onHint((text) => hud.setHint(text));

  const lastPos = ship.state.position.clone();

  engine.onFrame((dt, elapsed) => {
    fps.begin();
    stats.elapsed = elapsed;
    input.update(dt);

    if (input.pressed('gui')) toggleGui();
    if (input.pressed('help')) document.getElementById('help')?.classList.toggle('hidden');
    if (input.pressed('cameraToggle')) {
      const order = ['chase', 'cockpit', 'orbit'];
      rig.setMode(order[(order.indexOf(rig.mode) + 1) % order.length]);
      audio.play('ui');
    }
    if (input.pressed('map')) solar.setOrbitLinesVisible(!solar.orbitLines.visible);
    if (input.pressed('warp')) startWarp();

    // --- Environnement de vol -------------------------------------------
    updateEnv(solar, ship.state.position);

    // --- Saut hyperspatial ou vol normal --------------------------------
    if (warp) {
      warp.t += dt;
      const k = easeInOutCubic(saturate(warp.t / warp.duration));
      ship.state.position.lerpVectors(warp.from, warp.to, k);
      ship.state.velocity.set(0, 0, 0);
      // On regarde vers la destination pendant le saut.
      _tmp.copy(warp.target.absolutePosition).sub(ship.state.position).normalize();
      lookAlong(ship.state.quaternion, _tmp, env.up);
      if (warp.t >= warp.duration) {
        warp = null;
        hud.toast(STR.warpDone || 'Sortie de saut', 'info');
      }
    } else if (!won) {
      ship.update(dt, input, env);
      // Assistance de cap (touche C maintenue) : le nez pivote vers la cible de
      // navigation. Sans elle, viser un point lumineux a 2 millions d'unites au
      // milieu du vide est une corvee.
      if (input.buttons.align) alignToTarget(ship, solar.planets[targetIndex], dt);
    }

    // --- Rendu relatif camera -------------------------------------------
    stats.distanceTravelled += ship.state.position.distanceTo(lastPos);
    lastPos.copy(ship.state.position);
    engine.viewOrigin.copy(ship.state.position);
    ship.object3D.position.set(0, 0, 0);
    ship.object3D.quaternion.copy(ship.state.quaternion);

    solar.update(dt, {
      viewOrigin: engine.viewOrigin,
      cameraAbsPos: ship.state.position,
      elapsed,
    });

    // --- Soleil : direction apparente sur une planete, geometrique sinon --
    const planet = env.planet;
    if (planet && planet.isActive) _sunDirTarget.copy(planet.sunDirWorld);
    else _sunDirTarget.copy(ship.state.position).negate().normalize();
    _sunDirSmooth.x = damp(_sunDirSmooth.x, _sunDirTarget.x, 4, dt);
    _sunDirSmooth.y = damp(_sunDirSmooth.y, _sunDirTarget.y, 4, dt);
    _sunDirSmooth.z = damp(_sunDirSmooth.z, _sunDirTarget.z, 4, dt);
    _sunDirSmooth.normalize();

    const distToSun = ship.state.position.length();
    _sunView.copy(_sunDirSmooth).multiplyScalar(distToSun);
    sun.update(dt, {
      sunViewPos: _sunView,
      cameraViewPos: camera.position,
      distanceToSun: distToSun,
    });
    if (sun.light) {
      sun.light.position.copy(_sunDirSmooth).multiplyScalar(120000);
      sunTarget.position.set(0, 0, 0);
    }

    // --- Camera, effets, brouillard --------------------------------------
    rig.update(dt, { ship, env, input, dt });
    starfield.update(dt, { cameraPosition: camera.position, atmoDensity: env.density });

    const speed = ship.state.velocity.length();
    speedLines.update(dt, { velocity: ship.state.velocity, speed, density: env.density });
    trail.update(dt, { throttle: ship.state.throttle, boost: ship.state.boost });
    ship.forward(_tmp2);
    reentry.update(dt, { speed, density: env.density, forward: _tmp2 });

    if (planet) {
      scene.fog.color.copy(planet.fogColor);
      scene.fog.density = Math.max(1e-7, planet.fogDensity);
    } else {
      scene.fog.density = 1e-7;
    }
    engine.setExposure(1.05 + env.density * 0.12);

    // --- Decouverte -------------------------------------------------------
    const nearTree = planet ? planet.nearestTree(ship.state.position) : null;
    const nearFauna = planet ? planet.nearestFauna(ship.state.position) : null;
    const overWater = planet ? planet.isOverWater(ship.state.position) : false;
    if (planet && env.altitude < planet.spec.radius * 0.4) stats.planetsVisited.add(planet.spec.id);

    if (discovery.setStats) {
      discovery.setStats({
        elapsed,
        planetsVisited: stats.planetsVisited.size,
        distanceTravelled: stats.distanceTravelled,
      });
    }
    discovery.update(dt, {
      planet,
      altitude: env.altitude,
      overWater,
      biomeId: planet && !planet.spec.isGas ? planet.biomeIdAt(ship.state.position) : -1,
      nearestTree: nearTree,
      nearestFauna: nearFauna,
      scanPressed: input.pressed('scan'),
      dt,
      stats: {
        elapsed,
        planetsVisited: stats.planetsVisited.size,
        distanceTravelled: stats.distanceTravelled,
      },
    });

    // --- HUD --------------------------------------------------------------
    updateHud(hud, {
      solar,
      ship,
      env,
      planet,
      discovery,
      navItems,
      targetId: solar.planets[targetIndex].spec.id,
      warping: !!warp,
    });
    hud.tick(dt);

    // --- Audio ------------------------------------------------------------
    audio.engine(ship.state.throttle, ship.state.boost, env.density);
    audio.wind(speed, env.density);

    if (gui && guiVisible) {
      const d = gui.userData;
      d.planete = planet ? planet.spec.name : 'espace profond';
      d.altitude = Math.round(env.altitude);
      const ts = planet ? planet.terrainStats : null;
      d.patches = ts ? ts.meshes : 0;
      d.arbres = planet && planet.vegetation ? planet.vegetation.count : 0;
      d.faune = planet && planet.fauna ? planet.fauna.count : 0;
    }
    fps.end();
  });

  engine.start();
  window.__odyssey = { engine, solar, ship, discovery, input, hud };

  // Le terrain proche se construit dans les premieres frames : on attend qu'il
  // soit la avant de rendre la main au joueur.
  await waitForTerrain(home, 6000);
  if (loading) loading.classList.add('hidden');
  hud.setHint(STR.hintTakeoff || 'Espace pour decoller, Shift pour la poussee maximale');
  audio.resume();
}

// ---------------------------------------------------------------------------
// Environnement de vol
// ---------------------------------------------------------------------------
function updateEnv(solar, absPos) {
  const planet = solar.currentPlanet(absPos);
  env.planet = planet;

  // Corps le plus proche, meme si l'on n'est dans la sphere d'influence
  // d'aucun : c'est lui qui borne la vitesse en vol libre.
  const near = solar.nearestPlanet(absPos);
  env.nearestDistance =
    near && near.planet ? Math.max(0, near.distance - near.planet.spec.radius) : Infinity;

  if (!planet) {
    env.altitude = Infinity;
    env.density = 0;
    env.groundRadius = 0;
    env.insideGas = 0;
    env.gravity.set(0, 0, 0);
    env.up.copy(absPos).normalize();
    return;
  }
  planet.upAt(absPos, env.up);
  env.groundRadius = planet.groundRadiusAt(absPos);
  env.altitude = planet.altitudeOf(absPos);
  env.density = planet.atmosphereDensityAt(absPos);
  env.insideGas = planet.insideGasAt(absPos);
  gravityAt(planet, absPos, env.gravity);
  return env;
}

// ---------------------------------------------------------------------------
// HUD
// ---------------------------------------------------------------------------
function updateHud(hud, { solar, ship, env, planet, discovery, navItems, targetId, warping }) {
  const t = ship.telemetry;
  hud.setTelemetry({
    speed: t.speed,
    altitude: env.altitude,
    thrust: ship.state.throttle,
    boost: ship.state.boost,
    verticalSpeed: t.verticalSpeed,
    gForce: t.gForce,
    mach: t.mach,
    landed: ship.state.landed,
    warping,
  });

  const abs = ship.state.position;
  for (let i = 0; i < solar.planets.length; i++) {
    const p = solar.planets[i];
    const item = navItems[i];
    item.distance = p.distanceTo(abs) - p.spec.radius;
    item.active = p.spec.id === targetId;
    const prog = discovery.progressFor(p.spec.id);
    item.progress = (prog.ocean ? 1 : 0) + (prog.trees ? 1 : 0) + (prog.fauna ? 1 : 0);
  }
  hud.setNavList(navItems);

  if (planet) {
    hud.setPlanetInfo(planet.spec, {
      localHour: planet.localHour,
      atmoDensity: env.density,
      biomeName: planet.spec.isGas ? planet.spec.typeLabel : planet.biomeNameAt(abs),
      altitude: env.altitude,
    });
    hud.setProgress(discovery.progressFor(planet.spec.id));
    const maps = planet.maps;
    if (!maps) {
      // Geante gazeuse ou planete pas encore active : pas de carte.
      hud.setMinimap(null);
    } else {
      const ll = planet.latLonAt(abs);
      hud.setMinimap({
        imageData: maps.imageData,
        biomeTexture: maps.biomeTexture,
        planetId: planet.spec.id,
        lat: ll.lat,
        lon: ll.lon,
        markers: discovery.markersFor ? discovery.markersFor(planet.spec.id) : [],
      });
    }
  } else {
    hud.setPlanetInfo(null, { localHour: 0, atmoDensity: 0, biomeName: '', altitude: Infinity });
    hud.setMinimap(null);
  }

  // Assiette : roulis et tangage par rapport a la verticale locale.
  ship.up(_tmp);
  ship.forward(_tmp2);
  _tmp3.copy(_tmp).cross(env.up);
  const roll = Math.atan2(_tmp3.dot(_tmp2), _tmp.dot(env.up));
  const pitch = Math.asin(Math.max(-1, Math.min(1, _tmp2.dot(env.up))));
  hud.setAttitude({ roll, pitch, up: env.up });
}

// ---------------------------------------------------------------------------
// Utilitaires de demarrage
// ---------------------------------------------------------------------------

/** Cherche une direction de depart : terre ferme, pas trop pentue, cote jour. */
function findStartDirection(planet) {
  const hf = planet.heightField;
  const sea = planet.spec.seaLevel;
  const dir = new THREE.Vector3();
  let best = null;
  let bestScore = -Infinity;
  const N = 220;
  const ga = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < N; i++) {
    const y = (1 - (i / (N - 1)) * 2) * 0.7; // on evite les poles
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = ga * i;
    dir.set(Math.cos(th) * r, y, Math.sin(th) * r).normalize();
    const elev = hf.elevation(dir.x, dir.y, dir.z);
    if (sea !== null && elev < sea + planet.spec.maxElevation * 0.03) continue;
    const slope = hf.slope(dir.x, dir.y, dir.z);
    const score = -Math.abs(elev - (sea === null ? 0 : sea) - planet.spec.maxElevation * 0.12) - slope * 4000;
    if (score > bestScore) {
      bestScore = score;
      best = dir.clone();
    }
  }
  return best || new THREE.Vector3(1, 0, 0);
}

const _alignQuat = new THREE.Quaternion();
const _alignDir = new THREE.Vector3();
const _alignUp = new THREE.Vector3();

/**
 * Fait pivoter progressivement le vaisseau vers la cible de navigation.
 * On conserve la verticale actuelle du vaisseau comme reference : le cap change,
 * pas le roulis, ce qui evite une embardee desagreable.
 */
function alignToTarget(ship, target, dt) {
  if (!target) return;
  _alignDir.copy(target.absolutePosition).sub(ship.state.position);
  const len = _alignDir.length();
  if (len < 1e-3) return;
  _alignDir.divideScalar(len);
  ship.up(_alignUp);
  // Si la verticale du vaisseau est presque colineaire a la cible, lookAt
  // degenere : on prend alors une reference de secours.
  if (Math.abs(_alignUp.dot(_alignDir)) > 0.99) ship.forward(_alignUp);
  lookAlong(_alignQuat, _alignDir, _alignUp);
  ship.state.quaternion.slerp(_alignQuat, 1 - Math.exp(-SHIP.alignRate * dt));
}

/** Oriente le vaisseau a plat sur la surface, nez vers l'horizon. */
function orientShipOnSurface(ship, planet) {
  planet.upAt(ship.state.position, _up);
  // Un axe tangent quelconque comme direction de nez.
  _tmp.set(0, 1, 0);
  if (Math.abs(_up.dot(_tmp)) > 0.9) _tmp.set(1, 0, 0);
  _tmp.cross(_up).normalize();
  lookAlong(ship.state.quaternion, _tmp, _up);
}

const _m4 = new THREE.Matrix4();

/** Construit un quaternion regardant vers `forward` avec `up` comme verticale. */
function lookAlong(quaternion, forward, up) {
  // Matrix4.lookAt(eye, target, up) place l'axe -Z de l'objet vers la cible.
  // Le nez du vaisseau etant en -Z, on passe donc `forward` tel quel.
  _m4.lookAt(_zero, forward, up);
  quaternion.setFromRotationMatrix(_m4);
  return quaternion;
}

/** Attend que le terrain proche soit arrive (ou expire). */
function waitForTerrain(planet, timeoutMs) {
  return new Promise((resolve) => {
    const t0 = performance.now();
    const tick = () => {
      const s = planet.terrainStats;
      if ((s && s.meshes >= 6 && s.pending === 0) || performance.now() - t0 > timeoutMs) {
        resolve();
        return;
      }
      requestAnimationFrame(tick);
    };
    tick();
  });
}
