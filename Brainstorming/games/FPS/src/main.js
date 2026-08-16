import * as THREE from 'three';
import { buildTextureSet } from './textures.js';
import { buildCity, buildSky, buildHorizon, AshField, SUN_DIR } from './world.js';
import { Effects } from './fx.js';
import { AudioEngine } from './audio.js';
import { Input } from './input.js';
import { Player } from './player.js';
import { Rifle, RIFLE_STATS } from './weapon.js';
import { EnemyManager } from './enemies.js';
import { PickupManager } from './pickups.js';
import { HUD } from './hud.js';

const FOV_HIP = 78;
const FOV_ADS = 55;
const WAVE_BREAK = 6.5;

class Game {
  constructor() {
    this.state = 'loading';
    this.hud = new HUD();
    this.clock = new THREE.Clock();
    this.elapsed = 0;
    this.waveBreakTimer = 0;
    this.deathTimer = 0;
    this.bestWave = Number(localStorage.getItem('ashfall.bestWave') || 0);
    this._tmp = new THREE.Vector3();
    this._tmp2 = new THREE.Vector3();
    this._suppressPause = false;
  }

  async boot() {
    const canvas = document.getElementById('scene');
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      powerPreference: 'high-performance',
      stencil: false,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.18;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.autoClear = false;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(FOV_HIP, window.innerWidth / window.innerHeight, 0.08, 520);
    this.camera.rotation.order = 'YXZ';

    // The weapon lives in its own scene so it can never clip through geometry.
    this.viewScene = new THREE.Scene();
    this.viewCamera = new THREE.PerspectiveCamera(58, this.camera.aspect, 0.004, 6);
    const vKey = new THREE.DirectionalLight(0xffe8cc, 2.2);
    vKey.position.set(0.6, 1.2, 0.8);
    this.viewScene.add(vKey);
    const vFill = new THREE.DirectionalLight(0x9dbdf0, 1.5);
    vFill.position.set(-0.8, -0.3, 0.4);
    this.viewScene.add(vFill);
    this.viewScene.add(new THREE.AmbientLight(0x8b8b8f, 1.3));

    await this._nextFrame();
    this._setLoading('BUILDING CITY...');

    this.tex = buildTextureSet(20260814);
    this.skyRig = buildSky(this.scene, this.renderer);

    // Bake the sky gradient into an environment map so metal reads as metal
    // instead of black. Done before the city exists, so it stays cheap.
    {
      const pmrem = new THREE.PMREMGenerator(this.renderer);
      pmrem.compileEquirectangularShader();
      const env = pmrem.fromScene(this.scene, 0, 1, 1000);
      this.scene.environment = env.texture;
      this.scene.environmentIntensity = 0.55;
      this.viewScene.environment = env.texture;
      this.viewScene.environmentIntensity = 0.7;
      pmrem.dispose();
    }

    await this._nextFrame();
    this._setLoading('RAISING RUINS...');

    this.city = buildCity(this.scene, this.tex, 20260814);
    this.colliders = this.city.colliders;
    this.horizon = buildHorizon(this.scene, this.tex, 4242);

    await this._nextFrame();
    this._setLoading('ARMING SYSTEMS...');

    this.ash = new AshField(this.scene, this.tex, 900, 55);
    this.effects = new Effects(this.scene, this.tex);
    this.audio = new AudioEngine();
    this.input = new Input(canvas);
    this.player = new Player(this.camera, this.colliders, this.audio);
    this.enemies = new EnemyManager({
      scene: this.scene,
      colliders: this.colliders,
      effects: this.effects,
      audio: this.audio,
      tex: this.tex,
      spawnPoints: this.city.spawnPoints,
    });
    this.pickups = new PickupManager(this.scene, this.audio);
    this.rifle = new Rifle({
      camera: this.camera,
      viewScene: this.viewScene,
      colliders: this.colliders,
      effects: this.effects,
      audio: this.audio,
      player: this.player,
      enemies: this.enemies,
    });

    this._wireEvents();
    this.player.spawn(this.city.playerStart);
    this.player.yaw = Math.PI * 0.15;
    this.player.update(0.016, this.input, { canMove: false, canLook: false });

    await this._nextFrame();
    // Warm the shader cache so the first shot does not hitch.
    this.renderer.compile(this.scene, this.camera);
    this.render();

    this.state = 'menu';
    this.hud.showScreen('menu');
    this.hud.showHUD(false);
    this.clock.start();
    this.loop();
  }

  _nextFrame() {
    return new Promise((r) => requestAnimationFrame(() => r()));
  }

  _setLoading(text) {
    const el = document.getElementById('loading-line');
    if (el) el.textContent = text;
  }

  _wireEvents() {
    window.addEventListener('resize', () => this.onResize());

    document.getElementById('btn-start').addEventListener('click', () => this.startRun());
    document.getElementById('btn-restart').addEventListener('click', () => this.startRun());
    document.getElementById('btn-resume').addEventListener('click', () => this.resume());
    document.getElementById('btn-restart-pause').addEventListener('click', () => this.startRun());

    const sens = document.getElementById('sens');
    const sensValue = document.getElementById('sens-value');
    const applySens = () => {
      const v = Number(sens.value);
      this.input.sensitivity = v * 0.0001;
      sensValue.textContent = (v / 10).toFixed(1);
      localStorage.setItem('ashfall.sens', String(v));
    };
    const saved = localStorage.getItem('ashfall.sens');
    if (saved) sens.value = saved;
    applySens();
    sens.addEventListener('input', applySens);

    this.input.onLockChange = (locked) => {
      if (!locked && this.state === 'playing' && !this._suppressPause) this.pause();
      if (locked && this.state === 'paused') {
        this.state = 'playing';
        this.hud.showScreen(null);
        this.hud.showHUD(true);
      }
    };

    this.input.onLockError = () => {
      if (this._lockWarned) return;
      this._lockWarned = true;
      this.hud.toast('POINTER LOCK BLOCKED - FREE MOUSE LOOK ON', 'warn');
    };

    // Clicking the canvas while paused or in the menu grabs the pointer again.
    this.renderer.domElement.addEventListener('click', () => {
      if (this.state === 'paused') this.resume();
      else if (this.state === 'playing' && !this.input.active) this.input.requestLock();
    });

    document.addEventListener('visibilitychange', () => {
      if (document.hidden && this.state === 'playing') this.pause();
    });

    this.enemies.onKill = (enemy) => this.onEnemyKilled(enemy);
    this.enemies.onPlayerHitCb = (enemy) => this.onPlayerHit(enemy);
    this.rifle.onHitmarker = (head, kill) => this.hud.hitmarker(head, kill);
  }

  onResize() {
    const w = window.innerWidth, h = window.innerHeight;
    this.renderer.setSize(w, h);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.viewCamera.aspect = w / h;
    this.viewCamera.updateProjectionMatrix();
  }

  // ------------------------------------------------------------- run flow
  startRun() {
    this.enemies.reset();
    this.pickups.reset();
    this.effects.reset();
    this.rifle.refill();
    this.player.spawn(this.city.playerStart);
    this.player.yaw = Math.PI * 0.15;
    this.player.kills = 0;
    this.elapsed = 0;
    this.waveBreakTimer = 0;
    this.deathTimer = 0;
    this.currentWave = 0;
    this.hud.showScreen(null);
    this.hud.showHUD(true);
    this.hud.setCrosshairVisible(true);
    this.state = 'playing';
    this.audio.init();
    this.input.requestLock();
    this.nextWave();
  }

  nextWave() {
    this.currentWave = (this.currentWave || 0) + 1;
    this.enemies.startWave(this.currentWave, this.player);
    this.hud.banner(`WAVE ${this.currentWave}`, this._waveTagline(this.currentWave));
    if (this.currentWave > 1) {
      this.rifle.addAmmo(30);
      this.hud.toast('+30 RESUPPLY ROUNDS', 'good');
    }
  }

  _waveTagline(n) {
    if (n === 1) return 'THEY HEARD YOU LAND';
    if (n === 2) return 'RAIDERS INBOUND';
    if (n === 4) return 'SOMETHING BIG IS COMING';
    if (n % 5 === 0) return 'THE HORDE THICKENS';
    return 'HOLD THE BLOCK';
  }

  pause() {
    if (this.state !== 'playing') return;
    this.state = 'paused';
    this._suppressPause = true;
    this.input.releaseLock();
    this._suppressPause = false;
    this.hud.showScreen('pause');
  }

  resume() {
    if (this.state !== 'paused') return;
    this.hud.showScreen(null);
    this.hud.showHUD(true);
    this.state = 'playing';
    this.audio.init();
    this.input.requestLock();
  }

  onEnemyKilled(enemy) {
    this.player.kills++;
    const head = false;
    this.hud.killLine(enemy.def.label, head);

    // loot: ammo is common, medkits show up when you actually need them
    const pos = enemy.position.clone();
    const hurt = this.player.health < this.player.maxHealth * 0.65;
    const roll = Math.random();
    if (roll < (hurt ? 0.3 : 0.12)) this.pickups.spawn('health', pos);
    else if (roll < 0.62) this.pickups.spawn('ammo', pos);
  }

  onPlayerHit(enemy) {
    this.audio.playerHurt();
    const dx = enemy.position.x - this.player.position.x;
    const dz = enemy.position.z - this.player.position.z;
    const worldAngle = Math.atan2(dx, -dz);
    // rotate into view space so the arc points where the hit came from
    this.hud.damageFrom(worldAngle - this.player.yaw);
  }

  onPlayerDeath() {
    this.state = 'dead';
    this.deathTimer = 0;
    this.audio.gameOver();
    this._suppressPause = true;
    this.input.releaseLock();
    this._suppressPause = false;
    this.hud.setCrosshairVisible(false);
    if (this.currentWave > this.bestWave) {
      this.bestWave = this.currentWave;
      localStorage.setItem('ashfall.bestWave', String(this.bestWave));
    }
  }

  _showGameOver() {
    const shots = this.rifle.shotsFired;
    const acc = shots > 0 ? Math.round((this.rifle.shotsHit / shots) * 100) : 0;
    const mins = Math.floor(this.elapsed / 60);
    const secs = Math.floor(this.elapsed % 60);
    this.hud.showHUD(false);
    this.hud.gameOver({
      wave: this.currentWave,
      kills: this.enemies.totalKills,
      score: this.enemies.score,
      accuracy: acc,
      time: `${mins}:${String(secs).padStart(2, '0')}`,
      best: this.bestWave,
    });
  }

  // ------------------------------------------------------------- main loop
  loop() {
    requestAnimationFrame(() => this.loop());
    const dt = Math.min(this.clock.getDelta(), 0.05);
    try {
      this.update(dt);
      this.render();
    } catch (err) {
      console.error(err);
      this.hud.error(String(err && err.stack ? err.stack : err));
      this.state = 'error';
    }
    this.input.endFrame();
  }

  update(dt) {
    if (this.state === 'error') return;

    if (this.input.pressedAny('KeyM', 'char:m')) {
      this.audio.setMuted(!this.audio.muted);
      this.hud.toast(this.audio.muted ? 'AUDIO MUTED' : 'AUDIO ON');
    }
    if (this.input.pressed('Escape') && this.state === 'playing') this.pause();

    const playing = this.state === 'playing';
    const dying = this.state === 'dead';

    if (playing) this.elapsed += dt;

    // --- player ---
    this.player.update(dt, this.input, {
      canMove: playing,
      canLook: playing,
      aiming: this.rifle.aiming,
      aimSensScale: 1 - this.rifle.adsAmount * 0.45,
    });

    if (playing && !this.player.alive) this.onPlayerDeath();

    if (dying) {
      // slump to the ground and roll the view
      this.deathTimer += dt;
      const t = Math.min(1, this.deathTimer / 1.1);
      const ease = 1 - Math.pow(1 - t, 3);
      this.camera.position.y = this.player.position.y + 1.6 - ease * 1.05;
      this.camera.rotation.z = ease * 0.85;
      this.camera.rotation.x = this.player.pitch * (1 - ease) - ease * 0.25;
      if (this.deathTimer > 1.9 && !this._gameOverShown) {
        this._gameOverShown = true;
        this._showGameOver();
      }
    } else {
      this._gameOverShown = false;
    }

    // --- weapon ---
    this.rifle.update(dt, this.input, { active: playing });

    // --- field of view eases when aiming ---
    const targetFov = THREE.MathUtils.lerp(FOV_HIP, FOV_ADS, this.rifle.adsAmount) +
      (this.player.sprinting ? 4 : 0);
    if (Math.abs(this.camera.fov - targetFov) > 0.01) {
      this.camera.fov += (targetFov - this.camera.fov) * Math.min(1, 10 * dt);
      this.camera.updateProjectionMatrix();
    }

    // --- world sim ---
    if (playing || dying) {
      this.enemies.update(dt, this.player);
      this.pickups.update(dt, this.player, (type) => this.collect(type));
    }
    this.effects.update(dt);
    this.ash.update(dt, this.camera);
    this.skyRig.update(dt);
    this.horizon.update(dt);

    // Sky dome and horizon ride along with the camera so they stay infinitely
    // far away, and the shadow frustum follows the player.
    this.skyRig.sky.position.set(this.camera.position.x, 0, this.camera.position.z);
    this.horizon.group.position.set(this.camera.position.x, 0, this.camera.position.z);
    const sun = this.skyRig.sun;
    sun.position.copy(this.player.position).addScaledVector(SUN_DIR, 95);
    sun.target.position.set(this.player.position.x, 0, this.player.position.z);
    sun.target.updateMatrixWorld();

    // --- wave pacing ---
    if (playing) {
      if (!this.enemies.waveActive && this.enemies.remainingInWave === 0) {
        if (this.waveBreakTimer === 0) {
          this.hud.banner('SECTOR CLEAR', `WAVE ${this.currentWave} SURVIVED`, 2.6);
          this.waveBreakTimer = WAVE_BREAK;
        } else {
          this.waveBreakTimer -= dt;
          if (this.waveBreakTimer <= 0) {
            this.waveBreakTimer = 0;
            this.nextWave();
          }
        }
      }
    }

    // --- HUD ---
    if (playing || dying) {
      const aimHit = this._enemyUnderCrosshair();
      this.hud.update(dt, {
        health: this.player.health,
        maxHealth: this.player.maxHealth,
        damageFlash: this.player.damageFlash,
        crouching: this.player.crouching,
        sprinting: this.player.sprinting,
        moving: this.player.speed2D > 0.6,
        ammo: this.rifle.ammo,
        reserve: this.rifle.reserve,
        reloadProgress: this.rifle.reloading
          ? 1 - this.rifle.reloadTimer / this.rifle.reloadDuration
          : null,
        spreadNorm: this.rifle.spreadNorm,
        aiming: this.rifle.adsAmount,
        wave: this.currentWave,
        enemiesLeft: this.enemies.remainingInWave,
        score: this.enemies.score,
        enemyUnderCrosshair: aimHit,
      });
    }
  }

  _enemyUnderCrosshair() {
    if (this.state !== 'playing') return false;
    this.camera.getWorldDirection(this._tmp);
    const origin = this.camera.getWorldPosition(this._tmp2);
    const hit = this.enemies.raycast(origin, this._tmp, 120);
    if (!hit) return false;
    const wall = this.colliders.raycast(origin, this._tmp, hit.distance);
    return !wall;
  }

  collect(type) {
    if (type === 'ammo') {
      const gained = this.rifle.addAmmo(45);
      if (gained <= 0) return false;
      this.hud.toast(`+${gained} ROUNDS`, 'good');
      return true;
    }
    if (this.player.health >= this.player.maxHealth) return false;
    this.player.heal(45);
    this.hud.toast('+45 HEALTH', 'good');
    return true;
  }

  render() {
    this.renderer.clear();
    this.renderer.render(this.scene, this.camera);
    // draw the weapon on top with a fresh depth buffer
    this.renderer.clearDepth();
    this.renderer.render(this.viewScene, this.viewCamera);
  }
}

// ---------------------------------------------------------------- bootstrap
const game = new Game();
window.__ashfall = game; // handy for debugging from the console
game.boot().catch((err) => {
  console.error(err);
  const hud = new HUD();
  hud.error(String(err && err.stack ? err.stack : err));
});
