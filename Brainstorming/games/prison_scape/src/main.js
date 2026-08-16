import * as THREE from 'three';
import { Input } from './input.js';
import { AudioEngine } from './audio.js';
import { Effects } from './fx.js';
import { World, tileVec, PLAYER_SPAWN, EXIT_TILE, tileX, tileZ } from './world.js';
import { Player } from './player.js';
import { Arsenal } from './weapons.js';
import { SecurityCameras } from './cameras.js';
import { Guards, PUNCH_RADIO_SETBACK } from './guards.js';
import { Pickups } from './pickups.js';
import { Hud, alertSourceFrom } from './hud.js';
import { Minimap } from './minimap.js';
import { Cutscene } from './cutscene.js';

/**
 * The prison has ONE lockdown clock, not one per officer, and it runs at the
 * same speed however many guards and cameras are calling it in. Being seen by
 * three people is not three times worse than being seen by one: you always get
 * the same eight seconds to shut every caller up, and silencing them all winds
 * the clock back. Per-guard timers used to stack, so a second officer who
 * spotted you a moment after the first ended the run before you could react.
 */
const LOCKDOWN_TIME = 8.0;      // seconds of uninterrupted calling to lock down
const LOCKDOWN_RECOVER = 0.9;   // progress clawed back per second with nobody calling

const STATE = {
  MENU: 'menu',
  CUTSCENE: 'cutscene',
  PLAYING: 'playing',
  PAUSED: 'paused',
  LOST: 'lost',
  WON: 'won',
};

/** Ordered objective chain. Each step knows when it is done and where to point. */
const OBJECTIVES = [
  {
    id: 'cell', text: 'Sortez de votre cellule',
    done: (g) => g.player.position.z > tileZ(6) + 2 || g.world.areaAt(g.player.position)?.id === 'corridorA',
    marker: () => new THREE.Vector3(tileX(2), 1.5, tileZ(8)),
  },
  {
    id: 'gun', text: 'Trouvez une arme a feu (poste de garde, au nord de la rotonde)',
    done: (g) => g.arsenal.hasGun,
    marker: () => new THREE.Vector3(tileX(34), 1.5, tileZ(8)),
  },
  {
    id: 'uniform', text: 'Abattez un policier et prenez son uniforme',
    done: (g) => g.player.disguised,
    marker: (g) => {
      const c = g.guards.lootableNear(g.player.position, 999);
      return c ? c.position.clone() : null;
    },
  },
  {
    id: 'cam2', text: 'Detruisez CAM-2 (rotonde) pour deverrouiller l\'armurerie',
    done: (g) => g.cameras.dead.has('CAM-2'),
    marker: (g) => g.cameras.cameras.find((c) => c.id === 'CAM-2')?.position.clone(),
  },
  {
    id: 'cam3', text: 'Detruisez CAM-3 (refectoire) pour ouvrir le sas de la cour',
    // Reaching the yard by the back way counts too: whoever found that route
    // has earned skipping this.
    done: (g) => g.cameras.dead.has('CAM-3') || g.world.areaAt(g.player.position)?.outdoor,
    marker: (g) => g.cameras.cameras.find((c) => c.id === 'CAM-3')?.position.clone(),
  },
  {
    id: 'cam45', text: 'Detruisez CAM-4 et CAM-5 (miradors) pour ouvrir la porte principale',
    done: (g) => g.cameras.dead.has('CAM-4') && g.cameras.dead.has('CAM-5'),
    marker: (g) => {
      const c4 = g.cameras.cameras.find((c) => c.id === 'CAM-4');
      const c5 = g.cameras.cameras.find((c) => c.id === 'CAM-5');
      if (c4?.alive) return c4.position.clone();
      return c5?.position.clone() ?? null;
    },
  },
  {
    id: 'escape', text: 'Franchissez la porte principale',
    done: (g) => g.player.position.x > tileX(EXIT_TILE[0]) - 2,
    marker: () => new THREE.Vector3(tileX(EXIT_TILE[0]) + 2, 1.5, tileZ(EXIT_TILE[1])),
  },
];

class Game {
  constructor() {
    this.canvas = document.getElementById('scene');
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas, antialias: true, powerPreference: 'high-performance',
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;

    this.audio = new AudioEngine();
    this.hud = new Hud();
    this.input = new Input(this.canvas);

    this._buildScene();

    this.cutscene = new Cutscene(this.renderer, this.audio, (t) => this.hud.setSubtitle(t));

    this.state = STATE.MENU;
    this.clock = new THREE.Clock();
    this.time = 0;
    this.objectiveIndex = 0;
    this.introTimer = 0;
    this.lockdown = 0;
    this.endReason = '';
    this.stats = { kills: 0, camsDown: 0, spotted: 0, time: 0 };

    this._bindUi();
    window.addEventListener('resize', () => this._resize());
    this._resize();
    this._loop();
  }

  // --------------------------------------------------------------- scene
  _buildScene() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0d11);
    this.scene.fog = new THREE.Fog(0x0a0d11, 26, 120);

    this.camera = new THREE.PerspectiveCamera(70, 16 / 9, 0.05, 400);
    this.camera.rotation.order = 'YXZ';
    this.scene.add(this.camera);

    this.hemi = new THREE.HemisphereLight(0x6d8098, 0x1b1f26, 0.95);
    this.scene.add(this.hemi);
    this.ambient = new THREE.AmbientLight(0x2e3743, 0.55);
    this.scene.add(this.ambient);
    const moon = new THREE.DirectionalLight(0xb6c8ff, 0.55);
    moon.position.set(-40, 90, 30);
    this.scene.add(moon);

    // Keeps the view model readable wherever the player is standing. Sits
    // behind and above the eye so it never ends up inside the model itself.
    const handLight = new THREE.PointLight(0xfff0d8, 1.4, 7, 1.2);
    handLight.position.set(0.25, 0.55, 0.9);
    this.camera.add(handLight);

    this.fx = new Effects(this.scene);
    this.world = new World(this.scene);
    this.player = new Player(this.world, this.camera, this.audio);
    this.arsenal = new Arsenal(this.camera, this.audio, this.fx);
    this.cameras = new SecurityCameras(this.scene, this.world, this.audio, this.fx);
    this.guards = new Guards(this.scene, this.world, this.audio, this.fx);
    this.pickups = new Pickups(this.scene, this.world, this.audio);
    this.minimap = new Minimap(this.world);
    this.camsTotal = this.cameras.cameras.length;
  }

  _resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.cutscene.resize(w / h);
  }

  // ------------------------------------------------------------------ ui
  _bindUi() {
    this.screens = {
      menu: document.getElementById('screen-menu'),
      pause: document.getElementById('screen-pause'),
      over: document.getElementById('screen-over'),
      win: document.getElementById('screen-win'),
    };
    document.getElementById('btn-start').addEventListener('click', () => this._startFilm());
    document.getElementById('btn-skip-menu').addEventListener('click', () => this._startRun());
    document.getElementById('btn-resume').addEventListener('click', () => this._resume());
    for (const id of ['btn-restart', 'btn-restart-pause', 'btn-restart-win']) {
      document.getElementById(id).addEventListener('click', () => this._startRun());
    }
    for (const id of ['btn-quit', 'btn-quit-pause', 'btn-quit-win']) {
      document.getElementById(id).addEventListener('click', () => this._toMenu());
    }
    document.getElementById('skip-hint').addEventListener('click', () => this._skipFilm());

    this.input.onLockChange = (locked) => {
      if (!locked && this.state === STATE.PLAYING) this._pause();
    };
    this.input.onLockError = () => {
      this.hud.toast('Pointer lock refuse - visee a la souris libre', 'warn');
    };
  }

  _screen(name) {
    for (const [key, el] of Object.entries(this.screens)) {
      el.classList.toggle('hidden', key !== name);
    }
  }

  _toMenu() {
    this.state = STATE.MENU;
    this.input.releaseLock();
    this.hud.show(false);
    this.hud.setSubtitle(null);
    this.audio.stopSiren();
    this.audio.stopHum();
    this._inBackrooms = false;
    this.audio.stopDrone();
    this._screen('menu');
    document.getElementById('skip-hint').classList.add('hidden');
  }

  _startFilm() {
    this.audio.init();
    this.state = STATE.CUTSCENE;
    this._screen(null);
    this.hud.show(false);
    this.cutscene.start();
    document.getElementById('skip-hint').classList.remove('hidden');
  }

  _skipFilm() {
    if (this.state !== STATE.CUTSCENE) return;
    this.cutscene.skip();
    this._startRun();
  }

  _startRun() {
    this.audio.init();
    this.audio.stopDrone();
    this.audio.stopSiren();
    this.audio.stopHum();
    this._inBackrooms = false;
    document.getElementById('skip-hint').classList.add('hidden');

    this.fx.reset();
    this.arsenal.reset();
    this.cameras.reset();
    this.guards.reset();
    this.pickups.reset();
    this.minimap.reset();
    this.hud.reset();
    this.hud.setSubtitle(null);

    this.world.resetSecurity();

    this.player.spawn(tileVec(PLAYER_SPAWN.tile[0], PLAYER_SPAWN.tile[1]), PLAYER_SPAWN.yaw);
    this.objectiveIndex = 0;
    this.introTimer = 4.0;
    this.stats = { kills: 0, camsDown: 0, spotted: 0, time: 0 };
    this.lockdown = 0;

    this.state = STATE.PLAYING;
    this._screen(null);
    this.hud.show(true);
    this.hud.toast('BLOC A - 03:12', 'info');
    this.input.requestLock();
  }

  _pause() {
    if (this.state !== STATE.PLAYING) return;
    this.state = STATE.PAUSED;
    // Escape both exits pointer lock and reaches us as a keypress; the grace
    // period stops the pause menu from opening and closing on the same frame.
    this._pauseGrace = 0.4;
    this._screen('pause');
    this.input.releaseLock();
  }

  _resume() {
    if (this.state !== STATE.PAUSED) return;
    this.state = STATE.PLAYING;
    this._screen(null);
    this.input.requestLock();
  }

  _lose(reason) {
    if (this.state !== STATE.PLAYING) return;
    this.state = STATE.LOST;
    this.endReason = reason;
    this.audio.startSiren();
    this.audio.gameOver();
    this.input.releaseLock();
    document.getElementById('over-reason').textContent = reason;
    document.getElementById('over-stats').textContent =
      `${this.stats.kills} policiers neutralises  -  ${this.stats.camsDown}/${this.camsTotal} cameras detruites`
      + `  -  ${this.minimap.roomsSeen}/${this.minimap.roomsTotal} salles explorees  -  ${formatTime(this.stats.time)}`;
    this._screen('over');
    this.hud.show(false);
    this.audio.stopHum();
    this._inBackrooms = false;
    setTimeout(() => this.audio.stopSiren(), 4500);
  }

  _win() {
    if (this.state !== STATE.PLAYING) return;
    this.state = STATE.WON;
    this.audio.stopSiren();
    this.audio.stopHum();
    this._inBackrooms = false;
    this.audio.victory();
    this.input.releaseLock();
    document.getElementById('win-stats').textContent =
      `${this.stats.kills} policiers neutralises  -  ${this.stats.camsDown}/${this.camsTotal} cameras detruites`
      + `  -  ${this.minimap.roomsSeen}/${this.minimap.roomsTotal} salles explorees  -  ${formatTime(this.stats.time)}`;
    this._screen('win');
    this.hud.show(false);
  }

  // --------------------------------------------------------------- combat
  /** Resolves one bullet against the world, the guards and the cameras. */
  _resolveShot(origin, dir, damage, weapon) {
    const maxDist = weapon.range;
    const wall = this.world.colliders.raycast(origin, dir, maxDist);
    const guard = this.guards.raycast(origin, dir, maxDist);
    const cam = this.cameras.raycast(origin, dir, maxDist);

    const wallD = wall ? wall.distance : Infinity;
    const guardD = guard ? guard.distance : Infinity;
    const camD = cam ? cam.distance : Infinity;
    const nearest = Math.min(wallD, guardD, camD);
    if (nearest === Infinity) {
      this.fx.tracer(origin, origin.clone().addScaledVector(dir, maxDist));
      return;
    }

    if (nearest === guardD) {
      this.fx.tracer(origin, guard.point);
      const killed = this.guards.damage(guard.guard, damage, guard.point, dir, guard.head);
      this.hud.hit(killed);
      if (killed) {
        this.stats.kills++;
        this.hud.toast(guard.head ? 'POLICIER NEUTRALISE (TETE)' : 'POLICIER NEUTRALISE', 'good');
      }
      return;
    }

    if (nearest === camD) {
      this.fx.tracer(origin, cam.point);
      const killed = this.cameras.damage(cam.cam, damage, cam.point);
      this.hud.hit(killed);
      if (killed) this._onCameraDown(cam.cam);
      return;
    }

    this.fx.tracer(origin, wall.point);
    this.fx.sparks(wall.point, wall.normal, 6);
    this.fx.dust(wall.point, 4);
    this.fx.decal(wall.point, wall.normal, 0.22);
    this.audio.impact(true);
  }

  /**
   * Resolves a swing. A punch in the back drops a guard silently; a punch in
   * the face staggers him and makes him start his radio call over, which is
   * the unarmed way out of an alert.
   */
  _resolvePunch() {
    const target = this.guards.meleeTarget(this.player.position, this.player.lookDir(), 2.7);
    if (!target) return;

    const result = this.guards.punch(target, this.player.position);
    this.hud.hit(result.killed);
    if (result.killed) {
      this.stats.kills++;
      this.hud.toast(result.behind ? 'ETRANGLEMENT - AUCUN BRUIT' : 'POLICIER ASSOMME', 'good');
    } else if (result.staggered) {
      // The punch knocks the handset out of his hand: real time back on the clock.
      this.lockdown = Math.max(0, this.lockdown - PUNCH_RADIO_SETBACK);
      this.hud.toast('RADIO COUPEE - APPEL REPOUSSE', 'warn');
    }
  }

  _onCameraDown(cam) {
    this.stats.camsDown++;
    this.hud.toast(`${cam.id} HORS SERVICE`, 'good');
    const opened = this.world.releaseDoors(this.cameras.dead);
    for (const door of opened) {
      this.audio.doorOpen();
      this.hud.toast(`${door.label} : DEVERROUILLEE`, 'good');
    }
  }

  // ---------------------------------------------------------------- frame
  _updatePlaying(dt) {
    this.stats.time += dt;

    // ---- opening beat: the blackout that pops every cell on the wing ----
    if (this.introTimer > 0) {
      const before = this.introTimer;
      this.introTimer -= dt;
      if (before > 2.6 && this.introTimer <= 2.6) {
        this.hud.toast('COUPURE DE COURANT - SECTEUR OUEST', 'warn');
      }
      if (before > 0 && this.introTimer <= 0) {
        this.world.openCellGates();
        this.audio.cellOpen();
        this.hud.toast('LES GRILLES SE SONT OUVERTES. BOUGEZ.', 'good');
      }
    }

    // ------------------------------------------------------------ input --
    if (this.input.pressedAny('Escape')) {
      this._pause();
      return;
    }
    if (this.input.pressedAny('Digit1', 'char:1')) this.arsenal.select('pistol');
    if (this.input.pressedAny('Digit2', 'char:2')) this.arsenal.select('shotgun');
    if (this.input.pressedAny('Digit3', 'char:3')) this.arsenal.select('rifle');
    if (this.input.pressedAny('KeyR', 'char:r')) this.arsenal.startReload();
    if (this.input.pressedAny('KeyM', 'char:m')) this.minimap.toggle();

    this.player.update(dt, this.input, true);

    // ------------------------------------------------- melee and firing --
    const canShoot = this.input.active && this.player.alive;

    // Bare knuckles. Left click does it when there is no gun in hand, and F
    // always does, so an alerted guard can be silenced without firing a shot.
    const wantsPunch = canShoot
      && (this.input.pressedAny('KeyF', 'char:f')
        || (!this.arsenal.hasGun && this.input.clicked(0)));
    if (wantsPunch && this.arsenal.tryMelee(this.player)) {
      this._resolvePunch();
    }

    if (canShoot) {
      const fired = this.arsenal.tryFire(
        this.player,
        this.input.buttons[0],
        this.input.clicked(0),
        (o, d, dmg, w) => this._resolveShot(o, d, dmg, w)
      );
      if (fired) {
        const drawn = this.guards.hearGunshot(this.player.position, 48);
        // Say it out loud: these are patrols walking over to the noise, not
        // reinforcements being spawned. Ten officers, and that is all there is.
        if (drawn > 0) {
          this.hud.toast(
            `${drawn} PATROUILLE${drawn > 1 ? 'S' : ''} SE DIRIGE${drawn > 1 ? 'NT' : ''} VERS LE BRUIT`,
            'warn'
          );
        }
        // A shot fired in front of a living guard blows the uniform.
        if (this.player.disguised && this._seenByAnyGuard()) {
          if (this.player.blowDisguise()) {
            this.hud.toast('COUVERTURE GRILLEE', 'bad');
          }
        }
      }
    }

    // -------------------------------------------------------- interaction --
    const corpse = this.guards.lootableNear(this.player.position, 2.6);
    const secret = this.world.secretDoorNear(this.player.position);
    if (secret) {
      this.hud.setPrompt(`[E]  ${secret.label}`);
      if (this.input.pressedAny('KeyE', 'char:e') && this.world.openSecretDoor(secret)) {
        this.audio.panelPull();
        this.hud.toast('LE MUR N\'EST PAS UN MUR', 'warn');
      }
    } else if (corpse && !this.player.disguised) {
      this.hud.setPrompt('[E]  PRENDRE L\'UNIFORME');
      if (this.input.pressedAny('KeyE', 'char:e')) {
        this.guards.loot(corpse);
        this.player.wearUniform();
        this.hud.toast('UNIFORME DE POLICIER ENFILE', 'good');
        this.hud.setPrompt('');
      }
    } else if (corpse && this.player.disguised) {
      this.hud.setPrompt('[E]  FOUILLER LE CORPS');
      if (this.input.pressedAny('KeyE', 'char:e')) {
        this.guards.loot(corpse);
        const msg = this.arsenal.giveAmmo(12);
        this.hud.toast(msg || 'RIEN A RECUPERER', msg ? 'good' : 'info');
        this.hud.setPrompt('');
      }
    } else {
      this.hud.setPrompt('');
    }

    for (const msg of this.pickups.collect(this.player.position, (it) => {
      if (it.kind === 'ammo') return this.arsenal.giveAmmo(it.amount ?? 18);
      if (it.kind === 'medkit') {
        if (this.player.health >= this.player.maxHealth) return null;
        this.player.heal(45);
        return 'SOINS +45';
      }
      return this.arsenal.give(it.kind, it.amount);
    })) {
      this.hud.toast(msg, 'good');
    }

    // ------------------------------------------------------------ world --
    this.world.updateDoors(dt);
    this.world.updateCellGates(dt);
    this.world.updateSecretDoors(dt);
    this.world.updateLights(this.camera.position, dt);
    this.pickups.update(dt, this.time);
    this.fx.update(dt);
    this.arsenal.update(dt, this.player);
    this.cameras.updateWrecks(dt);

    const camResult = this.cameras.update(dt, this.player, this.introTimer <= 0);
    const guardResult = this.guards.update(dt, this.player, this.introTimer <= 0);

    // ------------------------------------------------- the lockdown clock --
    const callers = guardResult.callers + camResult.reporters;
    if (camResult.justReported) {
      this.hud.toast(`${camResult.justReported.id} VOUS A A L'ECRAN - DETRUISEZ-LA`, 'bad');
      // A camera that has you also puts the nearest patrols on your trail.
      this.guards.hearGunshot(this.player.position, 26);
    }
    if (callers > 0 && this.lockdown <= 0) this.audio.startSiren();
    if (callers === 0 && this.lockdown <= 0) this.audio.stopSiren();

    // One caller or five, the clock ticks at the same rate.
    const rate = callers > 0 ? 1 : 0;
    if (callers > 0) {
      this.lockdown = Math.min(LOCKDOWN_TIME, this.lockdown + dt * rate);
    } else {
      this.lockdown = Math.max(0, this.lockdown - dt * LOCKDOWN_RECOVER);
      if (this.lockdown === 0) this.audio.stopSiren();
    }

    // ------------------------------------------------------- lose / win --
    if (this.lockdown >= LOCKDOWN_TIME) {
      this._lose('L\'alerte est passee. Le penitencier est boucle.');
      return;
    }
    if (!this.player.alive) {
      this._lose('Abattu avant d\'avoir franchi les grilles.');
      return;
    }

    // ---------------------------------------------------------- progress --
    this._updateObjective();
    if (this.player.position.x > tileX(EXIT_TILE[0]) - 2) {
      this._win();
      return;
    }

    // -------------------------------------------------------------- hud --
    const detection = Math.max(camResult.worst, guardResult.awareness);
    // A camera on the line is an alert just like a guard on his radio: both
    // feed the same clock, so both have to raise the banner. The source is
    // passed along so the label names what actually has to be silenced.
    const camAlert = camResult.reporters > 0;
    const alertSource = alertSourceFrom(guardResult.anyAlert, camAlert);
    this.hud.update(dt, {
      player: this.player,
      arsenal: this.arsenal,
      detection,
      alerted: alertSource !== null,
      alertSource,
      camsLeft: this.cameras.aliveCount,
      camsTotal: this.camsTotal,
      guardsLeft: this.guards.aliveCount,
      guardsTotal: this.guards.list.length,
      callers,
      lockdownLeft: rate > 0 ? (LOCKDOWN_TIME - this.lockdown) / rate : 0,
      lockdownFrac: this.lockdown / LOCKDOWN_TIME,
      objective: OBJECTIVES[this.objectiveIndex]?.text ?? 'Sortez d\'ici',
      disguised: this.player.disguised,
    });
    const area = this.world.areaAt(this.player.position);
    this.hud.setZone(area?.name ?? null);
    const marker = this._updateCompass();

    this.minimap.observe(this.player.position);
    this.minimap.draw(dt, {
      player: this.player,
      cameras: this.cameras.cameras,
      guards: this.guards.list,
      doors: this.world.doors,
      marker,
    });

    this._updateAtmosphere(area);
  }

  /**
   * Fog, ambient tint and room tone. Stepping off-plan swaps the cold prison
   * blues for the flat yellow of the backrooms and starts the mains hum.
   */
  _updateAtmosphere(area) {
    const back = !!area?.back;
    if (back !== this._inBackrooms) {
      this._inBackrooms = back;
      if (back) {
        this.audio.startHum();
        this.hud.toast('HORS-PLAN', 'warn');
      } else {
        this.audio.stopHum();
      }
    }

    const outdoor = !!area?.outdoor;
    const target = back
      ? { near: 6, far: 46, fog: 0x6a5c22, hemiSky: 0xd8c878, hemiGround: 0x8a7530, hemi: 1.35, amb: 0.85 }
      : outdoor
        ? { near: 40, far: 200, fog: 0x0a0d11, hemiSky: 0x6d8098, hemiGround: 0x1b1f26, hemi: 0.95, amb: 0.55 }
        : { near: 24, far: 110, fog: 0x0a0d11, hemiSky: 0x6d8098, hemiGround: 0x1b1f26, hemi: 0.95, amb: 0.55 };

    // Eased so walking through the panel is a transition, not a hard cut.
    const k = 1 - Math.pow(0.002, 0.016);
    this.scene.fog.near += (target.near - this.scene.fog.near) * k;
    this.scene.fog.far += (target.far - this.scene.fog.far) * k;
    this.scene.fog.color.lerp(_tmpColor.setHex(target.fog), k);
    this.scene.background.copy(this.scene.fog.color);
    this.hemi.color.lerp(_tmpColor.setHex(target.hemiSky), k);
    this.hemi.groundColor.lerp(_tmpColor.setHex(target.hemiGround), k);
    this.hemi.intensity += (target.hemi - this.hemi.intensity) * k;
    this.ambient.intensity += (target.amb - this.ambient.intensity) * k;
  }

  _seenByAnyGuard() {
    for (const g of this.guards.list) {
      if (!g.alive) continue;
      if (g.position.distanceTo(this.player.position) > 26) continue;
      const eye = new THREE.Vector3(g.position.x, g.position.y + 0.72, g.position.z);
      if (this.world.colliders.lineOfSight(eye, this.player.chest)) return true;
    }
    return false;
  }

  _updateObjective() {
    let guard = 0;
    while (this.objectiveIndex < OBJECTIVES.length
      && OBJECTIVES[this.objectiveIndex].done(this)
      && guard++ < OBJECTIVES.length) {
      this.objectiveIndex++;
      const next = OBJECTIVES[this.objectiveIndex];
      if (next) this.hud.toast(`OBJECTIF : ${next.text}`, 'info');
    }
  }

  /** Points the on-screen arrow at the current objective. Returns the marker. */
  _updateCompass() {
    const obj = OBJECTIVES[this.objectiveIndex];
    const marker = obj?.marker?.(this);
    if (!marker) {
      this.hud.setCompass(0, 0, false);
      return null;
    }
    const dx = marker.x - this.player.position.x;
    const dz = marker.z - this.player.position.z;
    const dist = Math.hypot(dx, dz);
    // Angle relative to where the player is looking.
    const worldAngle = Math.atan2(dx, -dz);
    const rel = worldAngle - (-this.player.yaw);
    this.hud.setCompass(rel, dist, true);
    return marker;
  }

  _loop() {
    requestAnimationFrame(() => this._loop());
    const dt = Math.min(0.05, this.clock.getDelta());
    this.time += dt;

    switch (this.state) {
      case STATE.CUTSCENE:
        if (this.input.pressedAny('Escape', 'Space', 'Enter')) {
          this._skipFilm();
          break;
        }
        this.cutscene.update(dt);
        this.cutscene.render();
        if (this.cutscene.finished) this._startRun();
        this.input.endFrame();
        return;

      case STATE.PLAYING:
        this._updatePlaying(dt);
        break;

      case STATE.PAUSED:
        this._pauseGrace = Math.max(0, (this._pauseGrace ?? 0) - dt);
        if (this._pauseGrace <= 0 && this.input.pressedAny('Escape')) this._resume();
        break;

      case STATE.LOST:
      case STATE.WON:
        this.fx.update(dt);
        if (this.input.pressedAny('Enter')) this._startRun();
        break;

      case STATE.MENU:
      default:
        // Slow orbit over the yard behind the menu.
        this._menuCamera(dt);
        break;
    }

    this.renderer.render(this.scene, this.camera);
    this.input.endFrame();
  }

  _menuCamera(dt) {
    this._menuT = (this._menuT ?? 0) + dt * 0.08;
    const r = 30;
    const cx = tileX(34), cz = tileZ(33);
    this.camera.position.set(
      cx + Math.cos(this._menuT) * r,
      14 + Math.sin(this._menuT * 0.7) * 3,
      cz + Math.sin(this._menuT) * r
    );
    this.camera.lookAt(cx, 3, cz);
    this.world.updateLights(this.camera.position, dt);
    this.cameras.update(dt, this.player, false);
    this.guards.update(dt, this.player, false);
    this.pickups.update(dt, this.time);
    this.fx.update(dt);
  }
}

const _tmpColor = new THREE.Color();

function formatTime(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

// Surface load errors instead of leaving a black canvas.
window.addEventListener('error', (e) => {
  const el = document.getElementById('fatal');
  if (!el) return;
  el.classList.remove('hidden');
  el.textContent = `Erreur : ${e.message}`;
});

// Exposed for debugging from the console (state, player position, cameras...).
window.game = new Game();
