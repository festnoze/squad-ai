/**
 * ABYSSE - application entry point.
 *
 * Boots the renderer, builds every subsystem in order, then runs the loop:
 *   input -> diver -> fauna -> sub -> world -> water -> interactions -> hud -> audio
 *
 * The whole boot is wrapped so any failure routes to window.__fail (declared in
 * index.html) and the player sees an error panel instead of a black canvas.
 *
 * Game states:
 *   'loading'  building the world
 *   'title'    main menu, the scene renders behind it
 *   'play'     diving or walking on the island
 *   'transit'  riding the submarine between the reef and the dock
 *   'modal'    a blocking panel is open (codex, skins, scientist, pause, help)
 *   'dead'     the death screen
 */

import * as THREE from 'three';
import {
  GAME_TITLE,
  WORLD,
  DIVER,
  SUB,
  CAMERA,
  BIOME_INFO,
  SPECIES,
  SPECIES_BY_ID,
  PROGRESSION,
  DEBUG,
  clamp,
  clamp01,
  springK,
} from './config.js';
import { createTextures } from './textures.js';
import { createWater } from './water.js';
import { createWorld } from './world.js';
import { createFauna } from './fauna.js';
import { createSub } from './sub.js';
import { createDiver } from './diver.js';
import { createHUD } from './hud.js';
import { createAudio } from './audio.js';
import { createInput } from './input.js';
import {
  loadSave,
  writeSave,
  resetSave,
  isDiscovered,
  discoveredCount,
  recordSpecies,
  grantSkinPicks,
  unlockSkin,
  medalsToNextSkin,
} from './save.js';

const DT_MAX = 1 / 30;
const SCAN_RANGE = 42;
const SCAN_TIME = 1.5;

const _v1 = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const _dir = new THREE.Vector3();

function byId(id) {
  return document.getElementById(id);
}

function fail(err) {
  const message = err && err.message ? err.message : String(err);
  const where = err && err.stack ? err.stack : '';
  if (typeof window.__fail === 'function') window.__fail(message, where);
  else console.error(err);
}

/** Yield to the browser so the loading bar actually paints between steps. */
function paint() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => setTimeout(resolve, 0));
  });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function boot() {
  const canvas = byId('scene');
  if (!canvas) throw new Error('Canvas introuvable');

  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    powerPreference: 'high-performance',
    stencil: false,
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.08;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(
    CAMERA.fov,
    window.innerWidth / Math.max(1, window.innerHeight),
    CAMERA.near,
    CAMERA.far
  );

  // ----------------------------------------------------------------- HUD first
  // The HUD owns the loading screen, so it has to exist before anything slow.
  const game = {
    state: 'loading',
    time: 0,
    save: loadSave(),
    // Species identified with the scanner during this session. Identifying is
    // not the same as discovering: only the scientist writes the codex.
    scanned: new Set(),
    scanTarget: null,
    scanProgress: 0,
    runStats: { kills: 0, collected: 0, maxDepth: 0, startedAt: 0 },
    lastStreamAt: 0,
    depositedThisTrip: false,
    // setTimeout ids for the first dive tutorial toasts.
    hintTimers: [],
    // Set while the submarine carries the diver.
    riding: false,
  };

  // The HUD is built before the world, so its buttons exist while the loading
  // screen is still up. `booted` keeps them inert until every subsystem is in
  // place, otherwise a click reaches code whose bindings do not exist yet.
  let booted = false;

  const hud = createHUD({
    onPlay: () => {
      if (booted && game.state === 'title') startDive();
    },
    onResume: () => {
      if (booted) resumeFromPause();
    },
    onQuit: () => {
      if (booted) quitToTitle();
    },
    onRespawn: () => {
      if (booted) respawn();
    },
    onSelectSkin: (skinId) => {
      if (booted) pickSkin(skinId);
    },
    onScientistDone: () => {
      if (booted) closeScientist();
    },
    onReset: () => {
      if (!booted) return;
      game.save = resetSave();
      diver.setSkin(game.save.currentSkin);
      hud.refreshTitle(game.save);
      hud.toast('Progression effacee', 'warn');
    },
    onToggleMute: () => {
      if (!booted) return false;
      audio.setMuted(!audio.muted);
      hud.toast(audio.muted ? 'Son coupe' : 'Son actif', 'info');
      return audio.muted;
    },
  });

  hud.showScreen('loading');
  hud.setLoading(0.02, 'Preparation du materiel');
  await paint();

  // -------------------------------------------------------------- subsystems
  hud.setLoading(0.08, 'Generation des textures');
  await paint();
  const textures = createTextures(renderer);

  hud.setLoading(0.24, 'Mise en eau');
  await paint();
  const water = createWater(scene, textures, renderer);

  hud.setLoading(0.4, 'Modelage du fond marin');
  await paint();
  const world = createWorld(scene, textures);

  hud.setLoading(0.62, 'Peuplement du recif');
  await paint();
  const fauna = createFauna(scene, world, textures);

  hud.setLoading(0.78, 'Mise a l eau du sous-marin');
  await paint();
  const sub = createSub(scene, world, textures);

  hud.setLoading(0.88, 'Equipement du plongeur');
  await paint();
  const diver = createDiver(scene, camera, world, textures);
  diver.setSkin(game.save.currentSkin);

  const audio = createAudio();
  const input = createInput(canvas);

  hud.setLoading(1, 'Pret');
  await paint();

  // -------------------------------------------------------------------- wiring

  diver.hooks.onSound = (name, opts) => audio.play(name, opts);
  diver.hooks.onBubbles = (pos, count, spread) => water.spawnBubbles(pos, count, spread);

  diver.hooks.onHitscan = (origin, dir, weapon) => {
    const hit = fauna.raycast(origin, dir, weapon.range);
    if (!hit) return;
    resolveHit(hit.creature, weapon.damage, origin, weapon, hit.point);
  };

  diver.hooks.onMelee = (origin, dir, weapon) => {
    _v1.copy(origin).addScaledVector(dir, weapon.range * 0.6);
    const hits = fauna.sphereHit(_v1, weapon.radius);
    for (let i = 0; i < hits.length; i++) {
      resolveHit(hits[i], weapon.damage, origin, weapon, hits[i].position);
    }
  };

  diver.hooks.onProjectileStep = (from, to, weapon) => {
    _dir.copy(to).sub(from);
    const dist = _dir.length();
    if (dist < 1e-5) return null;
    _dir.multiplyScalar(1 / dist);
    // Widen the ray slightly so a fast spear does not slip past a small fish.
    const hit = fauna.raycast(from, _dir, dist + 0.5);
    if (!hit) return null;
    resolveHit(hit.creature, weapon.damage, from, weapon, hit.point);
    return { point: hit.point, stop: true };
  };

  // The net bundle only needs to know whether it ran into an animal, it never
  // wounds one, so it reuses the raycast without calling resolveHit.
  diver.hooks.onNetProbe = (from, to, weapon) => {
    _dir.copy(to).sub(from);
    const dist = _dir.length();
    if (dist < 1e-5) return null;
    _dir.multiplyScalar(1 / dist);
    const hit = fauna.raycast(from, _dir, dist + 0.5);
    void weapon;
    return hit ? { point: hit.point } : null;
  };

  /**
   * The net has opened. Small harmless animals go straight into the collection
   * net, alive: that is the whole point of the tool, chasing a clownfish with a
   * speargun is miserable. Anything bigger, or anything that hunts you, is only
   * tangled up for a few seconds.
   */
  diver.hooks.onNetDeploy = (position, weapon) => {
    const caught = fauna.sphereHit(position, weapon.captureRadius);
    let taken = 0;
    let tangled = 0;
    let full = false;

    for (let i = 0; i < caught.length; i++) {
      const creature = caught[i];
      if (!creature.alive) continue;
      const species = creature.species;
      const nettable = species.size <= weapon.captureSize && species.danger < 2;

      if (!nettable) {
        fauna.damage(creature, 0, { knockback: 0, from: position, stun: weapon.entangle });
        tangled += 1;
        continue;
      }
      // Reserve a slot now: several captures land in the same shot, and the
      // capsules only reach the bag a moment later.
      if (diver.net.length + taken >= DIVER.netCapacity) {
        full = true;
        continue;
      }
      // A real capture, not a kill: the capsule appears where the animal was
      // and is then reeled in to the diver, so the catch reads the same way as
      // any other, without the swim.
      if (fauna.capture(creature, diver.position)) taken += 1;
    }

    if (taken > 0) {
      audio.play('deposit', { volume: 0.5 });
      hud.toast(
        taken === 1 ? '1 prise dans le filet' : taken + ' prises dans le filet',
        'good'
      );
    }
    if (tangled > 0) {
      audio.play('hitArmor');
      hud.toast(tangled === 1 ? 'Une prise trop grosse, seulement empetree' : 'Grosses prises empetrees', 'warn');
    }
    if (full) hud.toast('Filet plein, retournez au sous-marin', 'warn');
    if (taken === 0 && tangled === 0) audio.play('dryfire');
  };

  diver.hooks.onGasp = () => {
    hud.toast('Bouteille rechargee en surface', 'good');
  };

  diver.hooks.onHurt = (kind, amount, angle) => {
    hud.flashDamage(clamp01(amount / 40), angle);
    audio.play(kind === 'sting' ? 'sting' : 'bite');
  };

  fauna.onDiverAttacked = (creature, damage) => {
    if (!diver.alive || game.state !== 'play') return;
    const kind = creature.species.danger === 2 ? 'bite' : 'sting';
    diver.applyDamage(damage, creature.position, kind);
    water.spawnBlood(diver.position, 0.4);
  };

  fauna.onKill = (creature) => {
    game.runStats.kills += 1;
    game.save.totalKills += 1;
    audio.play('kill');
    water.spawnBlood(creature.position, 1);
  };

  // A netted capsule has drifted back to the diver.
  fauna.onSpecimenArrived = (specimen) => {
    const species = SPECIES_BY_ID[specimen.speciesId];
    if (diver.netFull()) {
      // No room after all: leave it floating where it caught up with us.
      fauna.releaseSpecimen(specimen);
      hud.toast('Filet plein, specimen laisse sur place', 'warn');
      return;
    }
    diver.addSpecimen({
      speciesId: specimen.speciesId,
      name: species ? species.name : specimen.speciesId,
      value: specimen.value,
    });
    fauna.collect(specimen);
    game.runStats.collected += 1;
    audio.play('pickup');
    hud.flashPickup();
    hud.toast(
      (species ? species.name : 'Specimen')
        + ' au filet (' + diver.net.length + '/' + DIVER.netCapacity + ')',
      isDiscovered(game.save, specimen.speciesId) ? 'info' : 'good'
    );
  };

  fauna.onSpecimenSpawn = (specimen) => {
    if (!isDiscovered(game.save, specimen.speciesId)) {
      hud.toast('Specimen inedit a recuperer', 'good');
    }
  };

  sub.onArrive = (state) => {
    if (state === 'surface') arriveAtIsland();
    else arriveAtReef();
  };

  /** Apply damage to a creature and play the right feedback. */
  function resolveHit(creature, amount, fromPos, weapon, point) {
    if (!creature || !creature.alive) return;
    const res = fauna.damage(creature, amount, {
      knockback: weapon.knockback || 0,
      from: fromPos,
      stun: weapon.stun || 0,
    });
    audio.play(res.killed ? 'kill' : 'hit');
    if (point) water.spawnBubbles(point, res.killed ? 12 : 4, 0.3);
    // A hit is loud, and blood spreads.
    diver.noise = Math.min(1, diver.noise + 0.35);
  }

  // ---------------------------------------------------------------- lifecycle

  /**
   * The audio context can only start from a user gesture, and init() may reject
   * if the browser is not ready. Never let that bubble up as a fatal error.
   */
  function startAudio(then) {
    try {
      const p = audio.init();
      if (p && typeof p.then === 'function') {
        p.then(() => {
          if (then) then();
        }).catch(() => {});
      } else if (then) {
        then();
      }
    } catch (err) {
      console.warn('ABYSSE: audio indisponible.', err);
    }
  }

  /**
   * Where the diver enters the water. Far enough off the hull that the sub is a
   * silhouette in front of you rather than a wall of yellow paint, and always
   * clear of the seabed.
   */
  function diveSpawn(out) {
    out.set(sub.anchor.x + 15, sub.anchor.y + 3.5, sub.anchor.z + 17);
    const ground = world.heightAt(out.x, out.z);
    out.y = Math.max(out.y, ground + 3.5);
    return out;
  }

  /** Yaw that points the camera back at the submarine. */
  function faceSub() {
    return Math.atan2(sub.anchor.x - diver.position.x, sub.anchor.z - diver.position.z) + Math.PI;
  }

  function startDive() {
    game.state = 'play';
    game.runStats = { kills: 0, collected: 0, maxDepth: 0, startedAt: game.time };
    game.save.totalDives += 1;
    game.depositedThisTrip = false;
    diver.autoMode = true;
    diver.mode = 'swim';
    diver.revive(diveSpawn(_v1));
    diver.net.length = 0;
    diver.pitch = 0;
    diver.yaw = faceSub();
    hud.showScreen(null);
    hud.setHudVisible(true);
    input.requestLock();
    startAudio(() => audio.play('splashIn'));
    if (game.save.totalDives === 1) queueIntroHints();
    persist();
  }

  /**
   * Nothing on screen tells a first time diver that the loop is shoot, collect,
   * unload. Three toasts spaced out over the first minute do, once, and never
   * again.
   */
  function queueIntroHints() {
    const hints = [
      [3, 'Visez une creature quelques secondes: le masque l identifie', 'info'],
      [11, 'Clic gauche pour harponner, puis nagez dans le specimen', 'info'],
      [26, 'Filet plein: E le vide en soute. Bouteille basse: restez a quai, le plein se fait seul', 'info'],
      [42, 'Un requin vous charge ? Touche 3, le baton electrique le fait fuir', 'warn'],
    ];
    for (const [delay, text, kind] of hints) {
      game.hintTimers.push(
        window.setTimeout(() => {
          if (game.state === 'play') hud.toast(text, kind);
        }, delay * 1000)
      );
    }
  }

  function clearIntroHints() {
    for (const id of game.hintTimers) window.clearTimeout(id);
    game.hintTimers.length = 0;
  }

  function quitToTitle() {
    clearIntroHints();
    game.state = 'title';
    hud.setHudVisible(false);
    hud.showScreen('title');
    hud.refreshTitle(game.save);
    input.exitLock();
  }

  function resumeFromPause() {
    if (game.state !== 'modal') return;
    game.state = 'play';
    hud.showScreen(null);
    hud.setHudVisible(true);
    input.requestLock();
  }

  function openModal(screen) {
    if (game.state === 'play') game.state = 'modal';
    hud.showScreen(screen);
    hud.setHudVisible(false);
    input.exitLock();
  }

  function respawn() {
    game.state = 'play';
    diver.autoMode = true;
    diver.mode = 'swim';
    diver.revive(diveSpawn(_v1));
    diver.pitch = 0;
    diver.yaw = faceSub();
    // The net is lost with the dive, the submarine hold is not.
    diver.net.length = 0;
    hud.showScreen(null);
    hud.setHudVisible(true);
    input.requestLock();
    audio.play('surface');
  }

  function onDeath(reason) {
    if (game.state === 'dead') return;
    clearIntroHints();
    game.state = 'dead';
    input.exitLock();
    hud.setHudVisible(false);
    hud.openDead(reason, {
      depth: Math.round(game.runStats.maxDepth),
      kills: game.runStats.kills,
      collected: game.runStats.collected,
      lost: diver.net.length,
      cargo: sub.cargo.length,
    });
    audio.play('sharkAlert');
    persist();
  }

  function persist() {
    game.save.bestDepth = Math.max(game.save.bestDepth, Math.round(game.runStats.maxDepth));
    writeSave(game.save);
  }

  // ------------------------------------------------------------- submarine trips

  function boardAndAscend() {
    if (!sub.ascend()) return;
    game.state = 'transit';
    game.riding = true;
    diver.autoMode = false;
    diver.mode = 'ride';
    diver.velocity.set(0, 0, 0);
    hud.setHudVisible(false);
    hud.showTransit('Remontee vers la surface', 'Palier de decompression en cours');
    audio.play('engine');
    audio.play('uiConfirm');
  }

  /**
   * The landing spot has to be dry ground, otherwise the diver drops straight
   * back into the sea. Walk from the dock toward the laboratory and take the
   * first point that is properly above the waterline.
   */
  function findLanding(out) {
    const from = WORLD.dockLanding;
    const to = WORLD.lab;
    const dx = to.x - from.x;
    const dz = to.z - from.z;
    const len = Math.max(1, Math.hypot(dx, dz));
    for (let d = 0; d <= len; d += 1.5) {
      const x = from.x + (dx / len) * d;
      const z = from.z + (dz / len) * d;
      const h = world.heightAt(x, z);
      if (h > 0.45) return out.set(x, h + DIVER.eyeHeight, z);
    }
    // Nothing dry on that line, fall back to the island summit area.
    const h = world.heightAt(WORLD.island.x, WORLD.island.z);
    return out.set(WORLD.island.x, h + DIVER.eyeHeight, WORLD.island.z);
  }

  function arriveAtIsland() {
    game.riding = false;
    diver.autoMode = true;
    diver.mode = 'walk';
    findLanding(_v1);
    diver.teleport(
      _v1,
      Math.atan2(WORLD.scientist.x - _v1.x, WORLD.scientist.z - _v1.z) + Math.PI
    );
    diver.refillOxygen(DIVER.maxOxygen);
    game.state = 'play';
    hud.showTransit(null);
    hud.setHudVisible(true);
    input.requestLock();
    audio.play('splashOut');
    hud.toast('Laboratoire de terrain droit devant', 'info');
  }

  function boardAndDescend() {
    if (!sub.descend()) return;
    game.state = 'transit';
    game.riding = true;
    diver.autoMode = false;
    diver.mode = 'ride';
    diver.velocity.set(0, 0, 0);
    hud.setHudVisible(false);
    hud.showTransit('Descente vers le recif', 'Ballasts en remplissage');
    audio.play('engine');
  }

  function arriveAtReef() {
    game.riding = false;
    diver.autoMode = true;
    diver.mode = 'swim';
    diver.teleport(diveSpawn(_v1), faceSub());
    diver.revive();
    diver.net.length = 0;
    game.state = 'play';
    game.depositedThisTrip = false;
    hud.showTransit(null);
    hud.setHudVisible(true);
    input.requestLock();
    audio.play('splashIn');
  }

  // ------------------------------------------------------------------ scientist

  function openScientist() {
    const cargo = sub.cargo.slice();
    if (cargo.length === 0) {
      hud.toast('La soute est vide', 'warn');
      return;
    }

    const handed = [];
    let newSpecies = 0;
    let credits = 0;
    for (let i = 0; i < cargo.length; i++) {
      const species = SPECIES_BY_ID[cargo[i].speciesId];
      if (!species) continue;
      const isNew = recordSpecies(game.save, species.id);
      if (isNew) newSpecies += 1;
      credits += species.value;
      handed.push({ speciesId: species.id, name: species.name, isNew, value: species.value });
    }

    let medalsEarned = newSpecies * PROGRESSION.medalPerNewSpecies;
    const total = discoveredCount(game.save);
    let bonus = false;
    if (!game.save.expeditionBonusClaimed && total >= PROGRESSION.expeditionBonusAt) {
      game.save.expeditionBonusClaimed = true;
      medalsEarned += PROGRESSION.expeditionBonusMedals;
      bonus = true;
    }

    game.save.medals += medalsEarned;
    game.save.credits += credits;
    const picks = grantSkinPicks(game.save);

    const lines = buildDialogue(handed, newSpecies, medalsEarned, bonus, picks);

    sub.cargo.length = 0;
    persist();

    game.state = 'modal';
    hud.setHudVisible(false);
    input.exitLock();
    hud.openScientist(
      {
        handed,
        newSpecies,
        medalsEarned,
        bonus,
        totalMedals: game.save.medals,
        skinUnlocked: picks > 0,
        credits,
        lines,
      },
      game.save
    );
    audio.play(medalsEarned > 0 ? 'medal' : 'uiConfirm');
  }

  function buildDialogue(handed, newSpecies, medals, bonus, picks) {
    const lines = [];
    if (handed.length === 0) {
      lines.push('Vous revenez les mains vides. Ca arrive.');
      return lines;
    }
    lines.push(
      handed.length === 1
        ? 'Un seul specimen. Voyons ce que vous avez rapporte.'
        : 'Bien. ' + handed.length + ' specimens sur la table, je regarde ca.'
    );
    if (newSpecies === 0) {
      lines.push('Rien de nouveau pour le catalogue, mais les doublons servent aux mesures. Merci.');
    } else if (newSpecies === 1) {
      lines.push('La. Celle-ci n etait pas repertoriee sur ce recif. Une medaille pour vous.');
    } else {
      lines.push(newSpecies + ' especes inedites en une seule sortie. Vous vous rendez compte ?');
    }
    if (bonus) {
      lines.push(
        'Et vous venez de passer la barre des ' +
          PROGRESSION.expeditionBonusAt +
          ' especes cataloguees. L institut double la prime.'
      );
    }
    if (picks > 0) {
      lines.push('Avec ' + game.save.medals + ' medailles, vous avez droit a une nouvelle combinaison. Choisissez.');
    } else if (medals > 0) {
      const left = medalsToNextSkin(game.save);
      lines.push('Plus que ' + left + ' medaille' + (left > 1 ? 's' : '') + ' avant la prochaine combinaison.');
    }
    lines.push('Le sous-marin est amarre. Reprenez quand vous voulez, la fosse ne va nulle part.');
    return lines;
  }

  function closeScientist() {
    if (game.save.pendingSkinPicks > 0) {
      hud.openSkins(game.save, { forcePick: true });
      game.state = 'modal';
      return;
    }
    game.state = 'play';
    hud.showScreen(null);
    hud.setHudVisible(true);
    input.requestLock();
  }

  function pickSkin(skinId) {
    const owned = game.save.skins.indexOf(skinId) !== -1;
    if (!owned) {
      if (game.save.pendingSkinPicks <= 0) {
        hud.toast('Pas assez de medailles', 'warn');
        return;
      }
      unlockSkin(game.save, skinId);
      audio.play('skin');
      hud.toast('Combinaison debloquee', 'medal');
    } else {
      game.save.currentSkin = skinId;
      audio.play('uiConfirm');
      // Equipping something already owned does not spend the reward, so say so
      // rather than silently reopening the picker.
      if (game.save.pendingSkinPicks > 0) {
        hud.toast('Choisissez une combinaison encore verrouillee', 'warn');
      }
    }
    diver.setSkin(game.save.currentSkin);
    persist();
    hud.refreshTitle(game.save);

    if (game.save.pendingSkinPicks > 0) {
      hud.openSkins(game.save, { forcePick: true });
      return;
    }
    if (game.state === 'modal') {
      // Coming out of the scientist flow, hand control back to the player.
      hud.showScreen(null);
      if (game.save.totalDives > 0 && diver.mode !== 'ride') {
        game.state = 'play';
        hud.setHudVisible(true);
        input.requestLock();
      } else {
        game.state = 'title';
        hud.showScreen('title');
      }
    }
  }

  // ---------------------------------------------------------------- interaction

  let promptText = null;
  let promptKey = 'E';
  let promptAction = null;

  /**
   * Top up every weapon on the rack while docked, magazine and reserve alike.
   * The weapon in hand is not the only one that ran dry, and the stun baton is
   * usually the one that did.
   */
  function refillAllAmmo(amount) {
    const list = diver.weapons;
    for (let i = 0; i < list.length; i++) {
      const w = list[i];
      if (w.reserve < w.def.reserve) w.reserve = Math.min(w.def.reserve, w.reserve + amount);
      // A reload in flight moves rounds out of the reserve on its own, leave
      // its magazine alone until it lands.
      if (!w.reloading && w.mag < w.def.magazine) w.mag = Math.min(w.def.magazine, w.mag + amount);
    }
  }

  function ammoTopped() {
    const list = diver.weapons;
    for (let i = 0; i < list.length; i++) {
      const w = list[i];
      if (w.reserve < w.def.reserve - 0.01) return false;
      if (!w.reloading && w.mag < w.def.magazine - 0.01) return false;
    }
    return true;
  }

  /**
   * What the dock is still filling, as a short readable list. Empty string once
   * there is nothing left to give, which is what turns the status into an
   * actual offer to surface.
   */
  function resupplyStatus() {
    const parts = [];
    if (diver.oxygen < DIVER.maxOxygen - 0.5) {
      parts.push('oxygene ' + Math.round((diver.oxygen / DIVER.maxOxygen) * 100) + '%');
    }
    if (diver.health < DIVER.maxHealth - 0.5) {
      parts.push('sante ' + Math.round((diver.health / DIVER.maxHealth) * 100) + '%');
    }
    if (!ammoTopped()) parts.push('munitions');
    return parts.join(', ');
  }

  function computePrompt() {
    promptText = null;
    promptAction = null;
    promptKey = 'E';
    if (game.state !== 'play' || !diver.alive) return;

    // Near the submarine. On land the pier keeps you a little further from the
    // hull than the underwater docking radius allows, so it gets more slack.
    const subDist = sub.distanceTo(diver.position);
    const subReach = diver.mode === 'walk' ? SUB.interactRadius + 8 : SUB.interactRadius;
    if (sub.state !== 'ascending' && sub.state !== 'descending' && subDist < subReach) {
      if (sub.state === 'deep') {
        if (diver.net.length > 0) {
          promptText = 'Decharger le filet (' + diver.net.length + ')';
          promptAction = depositNet;
        } else if (sub.cargo.length > 0) {
          promptText = 'Remonter a la surface';
          promptAction = boardAndAscend;
        } else {
          // Nothing to unload and nothing to deliver. Standing here is still
          // doing something as long as the sub has anything left to top up, so
          // report what is filling and show no key: a badge nobody can press is
          // how the whole dock reads as broken.
          const filling = resupplyStatus();
          if (filling) {
            promptText = 'Amarre, ravitaillement: ' + filling;
            promptKey = null;
            promptAction = null;
          } else {
            // Everything full and the hold empty. The trip up is the only thing
            // left to offer, and without it an empty handed diver has no way
            // back to the island at all.
            promptText = 'Remonter a la surface (soute vide)';
            promptAction = boardAndAscend;
          }
        }
      } else if (sub.state === 'surface') {
        // Deliberately not restricted to walking: stepping off the pier into
        // the water next to the moored sub must not strand the player.
        promptText = 'Redescendre sur le recif';
        promptAction = boardAndDescend;
      }
      return;
    }

    // Near the scientist, on foot.
    if (diver.mode === 'walk') {
      _v1.set(WORLD.scientist.x, diver.position.y, WORLD.scientist.z);
      if (_v1.distanceTo(diver.position) < 6.5) {
        promptText = sub.cargo.length > 0
          ? 'Presenter les specimens (' + sub.cargo.length + ')'
          : 'Parler a Dr. Vasseur';
        promptAction = sub.cargo.length > 0 ? openScientist : () => {
          hud.toast('Rapportez des specimens dans la soute', 'info');
        };
      }
    }
  }

  function depositNet() {
    const taken = diver.clearNet();
    if (taken.length === 0) return;
    for (let i = 0; i < taken.length; i++) sub.cargo.push(taken[i]);
    game.depositedThisTrip = true;
    audio.play('deposit');
    const fresh = taken.filter((t) => !isDiscovered(game.save, t.speciesId)).length;
    hud.toast(
      taken.length + ' specimen' + (taken.length > 1 ? 's' : '') + ' en soute' + (fresh ? ' (' + fresh + ' inedit' + (fresh > 1 ? 's' : '') + ')' : ''),
      fresh ? 'good' : 'info'
    );
    if (sub.cargo.length >= PROGRESSION.expeditionBonusAt) {
      hud.toast('Soute pleine a craquer, remontez les montrer', 'medal');
    }
  }

  // ------------------------------------------------------------------ scanning

  function updateScanning(dt) {
    const target = fauna.scanTarget(camera, SCAN_RANGE);
    if (!target || !target.alive) {
      game.scanTarget = null;
      game.scanProgress = 0;
      return;
    }
    if (game.scanTarget !== target) {
      game.scanTarget = target;
      game.scanProgress = 0;
    }
    const known = game.scanned.has(target.speciesId) || isDiscovered(game.save, target.speciesId);
    if (known) {
      game.scanProgress = 1;
      return;
    }
    // Closer and steadier means a faster identification.
    const dist = target.position.distanceTo(diver.position);
    const rate = clamp(1.6 - dist / SCAN_RANGE, 0.35, 1.4) / SCAN_TIME;
    game.scanProgress = Math.min(1, game.scanProgress + rate * dt);
    if (game.scanProgress >= 1) {
      game.scanned.add(target.speciesId);
      audio.play('scanDone');
      hud.toast('Identifie: ' + target.species.name, 'good');
    }
  }

  // ------------------------------------------------------------------ pickups

  function updatePickups() {
    const list = fauna.specimens;
    for (let i = list.length - 1; i >= 0; i--) {
      const sp = list[i];
      if (sp.collected) continue;
      if (sp.position.distanceTo(diver.position) > DIVER.pickupRadius) continue;
      if (diver.netFull()) {
        // Tell the player once every couple of seconds, not every frame.
        if (game.time - (game.lastFullWarn || -9) > 3) {
          game.lastFullWarn = game.time;
          hud.toast('Filet plein, retournez au sous-marin', 'warn');
        }
        continue;
      }
      const species = SPECIES_BY_ID[sp.speciesId];
      diver.addSpecimen({ speciesId: sp.speciesId, name: species ? species.name : sp.speciesId, value: sp.value });
      fauna.collect(sp);
      game.runStats.collected += 1;
      audio.play('pickup');
      hud.flashPickup();
      hud.toast(
        (species ? species.name : 'Specimen') + ' au filet (' + diver.net.length + '/' + DIVER.netCapacity + ')',
        isDiscovered(game.save, sp.speciesId) ? 'info' : 'good'
      );
    }
  }

  // ----------------------------------------------------------------- objective

  function currentObjective() {
    if (diver.mode === 'walk') {
      return sub.cargo.length > 0 ? 'Montrez vos prises a Dr. Vasseur' : 'Retournez au sous-marin';
    }
    if (diver.netFull()) return 'Filet plein, rejoignez le sous-marin';
    if (sub.cargo.length >= PROGRESSION.expeditionBonusAt) return 'Soute pleine, remontez a la surface';
    if (diver.net.length > 0) return 'Decharger au sous-marin ou continuer';
    const missing = SPECIES.length - discoveredCount(game.save);
    if (missing <= 0) return 'Catalogue complet, chassez les records';
    return 'Trouvez de nouvelles especes (' + missing + ' restantes)';
  }

  // --------------------------------------------------------------------- keys

  /** The contract leaves `currentScreen` free to be a getter or a method. */
  function currentScreen() {
    const c = hud.currentScreen;
    return typeof c === 'function' ? c.call(hud) : c;
  }

  function handleGlobalKeys() {
    if (input.pressed('Escape')) {
      if (game.state === 'play') {
        openModal('pause');
        audio.play('uiBack');
      } else if (game.state === 'modal') {
        const screen = currentScreen();
        if (screen === 'pause') resumeFromPause();
        else if (screen === 'skins' && game.save.pendingSkinPicks > 0) {
          // A pending pick has to be made, do not let it be dismissed.
          hud.toast('Choisissez une combinaison', 'warn');
        } else if (screen === 'scientist') {
          closeScientist();
        } else {
          hud.showScreen('pause');
        }
        audio.play('uiBack');
      } else if (game.state === 'title') {
        const screen = currentScreen();
        if (screen !== 'title') {
          hud.showScreen('title');
          audio.play('uiBack');
        }
      }
    }

    if (input.pressed('Tab')) {
      if (game.state === 'play') {
        openModal('codex');
        hud.openCodex(game.save);
        audio.play('ui');
      } else if (game.state === 'modal' && currentScreen() === 'codex') {
        resumeFromPause();
      } else if (game.state === 'title') {
        hud.openCodex(game.save);
      }
    }

    if (input.pressed('KeyE') && promptAction) {
      promptAction();
    }
  }

  // -------------------------------------------------- adaptive resolution
  // The reef carries a lot of instanced geometry, and integrated GPUs are
  // fill rate bound long before they are triangle bound. Rather than ship a
  // quality menu nobody opens, watch the frame time and trade pixels for
  // smoothness, slowly, so the change is never noticeable mid dive.

  const PIXEL_RATIO_MAX = Math.min(window.devicePixelRatio || 1, 1.75);
  const PIXEL_RATIO_MIN = 0.62;
  let pixelRatio = PIXEL_RATIO_MAX;
  let frameAccum = 0;
  let frameCount = 0;

  function tuneResolution(dt) {
    frameAccum += dt;
    frameCount += 1;
    if (frameAccum < 1.5) return;
    const fps = frameCount / frameAccum;
    frameAccum = 0;
    frameCount = 0;
    let next = pixelRatio;
    if (fps < 42) next = Math.max(PIXEL_RATIO_MIN, pixelRatio - 0.18);
    else if (fps > 57 && pixelRatio < PIXEL_RATIO_MAX) {
      next = Math.min(PIXEL_RATIO_MAX, pixelRatio + 0.08);
    }
    if (Math.abs(next - pixelRatio) > 0.01) {
      pixelRatio = next;
      renderer.setPixelRatio(pixelRatio);
      renderer.setSize(window.innerWidth, Math.max(1, window.innerHeight), false);
    }
  }

  // ------------------------------------------------------------------ resizing

  function onResize() {
    const w = window.innerWidth;
    const h = Math.max(1, window.innerHeight);
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener('resize', onResize);
  onResize();

  input.state.onLockChange = (locked) => {
    // Losing the lock mid dive pauses rather than leaving the player exposed.
    if (!locked && game.state === 'play' && !hud.isModalOpen()) {
      openModal('pause');
    }
  };

  canvas.addEventListener('mousedown', () => {
    if (game.state === 'play' && !input.state.locked) input.requestLock();
    startAudio(null);
  });

  // --------------------------------------------------------------------- loop

  const waterCtx = {
    camera,
    time: 0,
    depth: 0,
    aboveWater: false,
    biome: 'lagoon',
    speed: 0,
    lampOn: false,
  };
  const faunaCtx = {
    time: 0,
    camera,
    playerPos: diver.position,
    playerVel: diver.velocity,
    playerVisible: true,
    lampOn: false,
    noise: 0,
    bleeding: 0,
  };
  const worldCtx = { time: 0, camera, playerPos: diver.position };
  const subCtx = { time: 0, onBubbles: (p, c, s) => water.spawnBubbles(p, c, s) };
  const audioCtx = {
    depth: 0,
    biome: 'lagoon',
    moving: false,
    threat: 0,
    aboveWater: false,
    insideSub: false,
    oxygen01: 1,
    health01: 1,
  };
  const hudState = {
    mode: 'dive',
    oxygen: 100,
    maxOxygen: DIVER.maxOxygen,
    health: 100,
    maxHealth: DIVER.maxHealth,
    stamina: 100,
    maxStamina: DIVER.maxStamina,
    depth: 0,
    biomeLabel: '',
    yaw: 0,
    weapon: { name: '', kind: '', mag: 0, magSize: 0, reserve: 0, reloading: false, reloadProgress: 0 },
    net: { count: 0, capacity: DIVER.netCapacity, items: [] },
    cargoCount: 0,
    medals: 0,
    skinCount: 1,
    discoveredCount: 0,
    speciesTotal: SPECIES.length,
    scan: null,
    threat: 0,
    objective: '',
    prompt: null,
  };

  let threatLevel = 0;
  let last = performance.now();

  function frame(now) {
    requestAnimationFrame(frame);
    let dt = (now - last) / 1000;
    last = now;
    if (!isFinite(dt) || dt <= 0) return;
    dt = Math.min(dt, DT_MAX);
    game.time += dt;

    const playing = game.state === 'play';
    const modal = !playing;

    handleGlobalKeys();

    // ------------------------------------------------------------- simulation
    diver.update(dt, input, { modal, allowLook: game.state === 'transit' });

    if (game.riding) {
      // Ride along inside the sub, free to look around.
      diver.position.copy(sub.seat);
      diver.rig.position.copy(sub.seat);
    }

    const biome = world.biomeAt(diver.position.x, diver.position.z);
    const info = BIOME_INFO[biome] || BIOME_INFO.lagoon;

    faunaCtx.time = game.time;
    // Docking makes the sub a safe haven: its lights and machinery push the
    // predators off, which is the answer to being hunted with an empty tank.
    const docked = sub.isNear(diver.position);
    faunaCtx.playerVisible =
      playing && diver.mode !== 'ride' && !diver.aboveWater && !docked;
    faunaCtx.lampOn = diver.lampOn;
    faunaCtx.noise = diver.noise;
    faunaCtx.bleeding = diver.bleeding;
    fauna.update(dt, faunaCtx);

    subCtx.time = game.time;
    sub.update(dt, subCtx);

    worldCtx.time = game.time;
    world.update(dt, worldCtx);

    waterCtx.time = game.time;
    waterCtx.depth = diver.depth;
    waterCtx.aboveWater = camera.getWorldPosition(_v2).y > 0.05;
    waterCtx.biome = biome;
    waterCtx.speed = diver.speed;
    waterCtx.lampOn = diver.lampOn;
    water.update(dt, waterCtx);

    // ---------------------------------------------------------------- gameplay
    if (playing) {
      updateScanning(dt);
      updatePickups();
      computePrompt();

      // Docking at the sub tops everything up.
      if (docked && sub.state === 'deep') {
        diver.refillOxygen(SUB.oxygenRefill * dt);
        diver.heal(SUB.healthRefill * dt);
        refillAllAmmo(SUB.ammoRefill * dt);
      }

      game.runStats.maxDepth = Math.max(game.runStats.maxDepth, diver.depth);

      // Streaming, a couple of times a second is plenty.
      if (game.time - game.lastStreamAt > 1.2) {
        game.lastStreamAt = game.time;
        fauna.stream(diver.position);
      }

      if (!diver.alive) {
        onDeath(diver.oxygen <= 0.5 ? 'drowned' : 'shark');
      }
    } else {
      game.scanTarget = null;
      game.scanProgress = 0;
    }

    // ------------------------------------------------------------------ threat
    const threat = fauna.nearestThreat(diver.position);
    const rawThreat = threat ? clamp01(1 - threat.distance / 55) : 0;
    threatLevel += (rawThreat - threatLevel) * springK(2.6, dt);

    // --------------------------------------------------------------------- HUD
    const w = diver.currentWeapon();
    hudState.mode = game.state === 'transit' ? 'transit' : diver.mode === 'walk' ? 'land' : 'dive';
    hudState.oxygen = diver.oxygen;
    hudState.health = diver.health;
    hudState.stamina = diver.stamina;
    hudState.depth = diver.depth;
    hudState.biomeLabel = diver.mode === 'walk' ? 'Ile de Kaloa' : info.label;
    hudState.yaw = diver.yaw;
    hudState.weapon.name = w.def.name;
    hudState.weapon.kind = w.def.kind;
    hudState.weapon.mag = Math.floor(w.mag);
    hudState.weapon.magSize = w.def.magazine;
    hudState.weapon.reserve = Math.floor(w.reserve);
    hudState.weapon.reloading = w.reloading;
    hudState.weapon.reloadProgress = w.reloading ? clamp01(w.reloadT / w.def.reloadTime) : 0;
    hudState.net.count = diver.net.length;
    hudState.net.items = diver.net;
    hudState.cargoCount = sub.cargo.length;
    hudState.medals = game.save.medals;
    hudState.skinCount = game.save.skins.length;
    hudState.discoveredCount = discoveredCount(game.save);
    hudState.threat = threatLevel;
    hudState.objective = currentObjective();
    hudState.prompt = promptText ? { text: promptText, key: promptKey } : null;
    if (game.scanTarget && game.scanTarget.alive) {
      hudState.scan = {
        creature: game.scanTarget,
        progress: game.scanProgress,
        known: game.scanned.has(game.scanTarget.speciesId) || isDiscovered(game.save, game.scanTarget.speciesId),
      };
    } else {
      hudState.scan = null;
    }
    hud.update(dt, hudState);

    // ------------------------------------------------------------------- audio
    audioCtx.depth = diver.depth;
    audioCtx.biome = biome;
    audioCtx.moving = diver.speed > 1.2;
    audioCtx.threat = threatLevel;
    audioCtx.aboveWater = waterCtx.aboveWater;
    audioCtx.insideSub = game.riding;
    audioCtx.oxygen01 = clamp01(diver.oxygen / DIVER.maxOxygen);
    audioCtx.health01 = clamp01(diver.health / DIVER.maxHealth);
    audio.update(dt, audioCtx);

    input.endFrame();
    renderer.render(scene, camera);
    tuneResolution(dt);
  }

  // ------------------------------------------------------------------- title

  // Put the camera somewhere flattering for the menu backdrop.
  diver.teleport(_v1.set(sub.anchor.x + 24, sub.anchor.y + 7, sub.anchor.z + 30));
  diver.yaw = faceSub();
  diver.pitch = -0.1;

  game.state = 'title';
  booted = true;
  hud.setHudVisible(false);
  hud.showScreen('title');
  hud.refreshTitle(game.save);

  if (DEBUG.spawnAll) fauna.stream(diver.position);

  requestAnimationFrame((t) => {
    last = t;
    requestAnimationFrame(frame);
  });

  // Expose a handle for debugging from the console.
  // Debug handle, also what tools/smoke.mjs drives the game through.
  window.__abysse = {
    game,
    scene,
    renderer,
    camera,
    diver,
    fauna,
    world,
    water,
    sub,
    hud,
    audio,
    species: SPECIES.map((s) => s.id),
  };
  console.log(GAME_TITLE + ' pret. Especes au catalogue: ' + SPECIES.length + '.');
}

boot().catch(fail);
