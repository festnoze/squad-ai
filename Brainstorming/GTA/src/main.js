/**
 * Liberty Horizon - entry point.
 *
 * Boots the renderer, physics and world, then owns the top-level game loop wiring:
 * fixed-step callbacks for simulation, render-rate callbacks for visuals and HUD.
 */

import { Vector3, MathUtils } from 'three/webgpu';
import { Engine } from './core/Engine.js';
import { Profiler } from './core/Profiler.js';
import { Input } from './core/Input.js';
import { CameraRig } from './core/CameraRig.js';
import { FreeCamera } from './core/FreeCamera.js';
import { Atmosphere } from './render/Atmosphere.js';
import { PostFX } from './render/PostFX.js';
import { initPhysicsEngine, Physics } from './physics/Physics.js';
import { City, districtAt, DISTRICT } from './world/City.js';
import { Island } from './world/Island.js';
import { Ocean } from './world/Ocean.js';
import { StreetProps } from './world/StreetProps.js';
import { Signage } from './world/Signage.js';
import { Neon } from './world/Neon.js';
import { Highway } from './world/Highway.js';
import { Bridges } from './world/Bridges.js';
import { NightLights } from './render/NightLights.js';
import { Boat, BOAT_CLASSES } from './entities/Boat.js';
import { Player, PLAYER_STATE } from './entities/Player.js';
import { VehicleManager } from './entities/VehicleManager.js';
import { HUD, LoadingScreen } from './ui/HUD.js';
import { Minimap } from './ui/Minimap.js';
import { MissionManager } from './gameplay/Missions.js';
import { PedestrianManager } from './entities/PedestrianManager.js';
import { WantedSystem, CRIME } from './gameplay/Wanted.js';
import { WeaponSystem } from './gameplay/Weapons.js';
import { PickupManager } from './gameplay/Pickups.js';
import { AudioEngine } from './core/Audio.js';
import { Radio } from './core/Radio.js';
import { Weather } from './render/Weather.js';
import { SaveGame } from './gameplay/SaveGame.js';
import { PauseMenu } from './ui/PauseMenu.js';
import { Phone } from './ui/Phone.js';
import { getMaterial } from './render/Materials.js';

const PARAMS = new URLSearchParams(location.search);
/** `?quality=low|medium|high|ultra`, or `?post=off` to bypass post-processing entirely. */
const QUALITY_DEFAULT = PARAMS.get('quality') ?? 'high';
const POST_ENABLED = PARAMS.get('post') !== 'off';
const ZERO_MOVE = { x: 0, y: 0 };
const BOAT_COLOURS = [0xb8453a, 0xf0ece0, 0x2f5f8f, 0x1f2933, 0xd8a03a, 0x2f6f5f];

class Game {
  constructor() {
    this.loading = new LoadingScreen();
    this.canvas = document.getElementById('viewport');
    this.moveInput = { x: 0, y: 0 };
    this.money = 2500;
    this.pausedByMenu = false;
    this._focus = new Vector3();
    this.profiler = new Profiler();
  }

  async boot() {
    await this.loading.step(6, 'starting renderer');
    this.engine = new Engine(this.canvas);
    await this.engine.init();

    await this.loading.step(16, 'loading physics');
    await initPhysicsEngine();
    this.physics = new Physics();

    await this.loading.step(26, 'building sky');
    this.atmosphere = new Atmosphere(this.engine.scene, this.engine.renderer);

    await this.loading.step(36, 'generating textures');
    // Touch the material library up-front so the first frame does not stall on a few
    // hundred milliseconds of procedural texture synthesis.
    for (const name of ['road', 'sidewalk', 'concrete', 'brick', 'glassTower', 'roof', 'grass', 'metal', 'corrugated', 'wood']) {
      getMaterial(name);
      await new Promise((r) => setTimeout(r, 0));
    }

    await this.loading.step(52, 'raising the island');
    this.island = new Island({ radius: 1320 });
    for (const mesh of this.island.buildTerrain(this.physics)) this.engine.scene.add(mesh);

    this.ocean = new Ocean();
    this.engine.scene.add(this.ocean.mesh);

    await this.loading.step(62, 'laying out streets');
    this.city = new City(this.physics, { extent: 1150, island: this.island });
    this.engine.scene.add(this.city.group);

    await this.loading.step(72, 'building the waterfront');
    const seaWall = this.island.buildSeaWall(this.physics, this.city.network);
    if (seaWall) this.engine.scene.add(seaWall);
    const docks = this.island.buildDocks(this.physics);
    if (docks.mesh) this.engine.scene.add(docks.mesh);
    this.moorings = docks.moorings;

    await this.loading.step(76, 'installing street lighting');
    this.props = new StreetProps(this.physics, this.city);
    for (const mesh of this.props.meshes) this.engine.scene.add(mesh);
    this.nightLights = new NightLights(this.engine.scene, this.props.lamps);
    this.highway = new Highway(this.physics, this.city);
    for (const mesh of this.highway.meshes) this.engine.scene.add(mesh);

    this.bridges = new Bridges(this.physics, this.city, this.island);
    for (const mesh of this.bridges.meshes) this.engine.scene.add(mesh);
    this.signage = new Signage(this.physics, this.city);
    for (const mesh of this.signage.meshes) this.engine.scene.add(mesh);
    this.neon = new Neon(this.city);
    for (const mesh of this.neon.meshes) this.engine.scene.add(mesh);

    await this.loading.step(78, 'spawning player');
    this.input = new Input(window);
    await this.input.loadLayout();
    this.cameraRig = new CameraRig(this.physics, window.innerWidth / window.innerHeight);
    this.freeCam = new FreeCamera();
    this.engine.setCamera(this.cameraRig.camera);

    this.player = new Player(this.physics, this.city.playerSpawn());
    this.player.setWorld({ ocean: this.ocean, island: this.island });
    this.engine.scene.add(this.player.group);

    await this.loading.step(84, 'putting cars on the street');
    this.traffic = new VehicleManager(this.physics, this.city, this.engine.scene);
    this.traffic.spawnParked(110);
    this.traffic.spawnTraffic(28);
    /*
     * Highway traffic, on by default. `?hwtraffic=N` overrides the count; 0 empties it.
     *
     * This was off for a long time behind a comment blaming the lane-following autopilot
     * for cars leaving the deck. That diagnosis was wrong. The cars were not drifting off
     * the edge - they were being *teleported* off it, by a stuck-recovery path that
     * hardcoded ground height and so dropped them onto the streets below whenever the
     * timer fired. The giveaway was that they landed at their correct ring radius. With
     * that fixed, every car holds the deck across 130 s of simulation and the ring
     * sustains ~40 km/h, so there is no longer any reason to run an empty expressway.
     *
     * 26 is a density choice, not a performance one: it halves the median gap between
     * cars to 139 m on a 4 km ring, and costs 1.5 ms more than 14 did.
     */
    this.highway.buildNetwork();
    const hwCars = PARAMS.has('hwtraffic') ? Number(PARAMS.get('hwtraffic')) : 26;
    if (hwCars > 0) this.traffic.spawnOnNetwork(this.highway.network, hwCars);
    // A car waiting right where the player starts, so driving is one keypress away.
    this._spawnStarterCar();
    this._spawnBoats();

    await this.loading.step(86, 'filling the pavements');
    this.peds = new PedestrianManager(this.physics, this.city, this.engine.scene);
    this.wanted = new WantedSystem({
      physics: this.physics, city: this.city, traffic: this.traffic,
      player: this.player, hud: null,
    });

    await this.loading.step(88, 'compiling shaders');
    this.postfx = new PostFX(
      this.engine.renderer, this.engine.scene, this.cameraRig.camera,
      QUALITY_DEFAULT, this.atmosphere.sun,
    );
    if (!POST_ENABLED) this.postfx.enabled = false;
    this.engine.drawOverride = () => this.postfx.render();
    // Warm the pipeline cache so the first seconds are not a stutter-fest.
    try {
      await this.engine.renderer.compileAsync(this.engine.scene, this.cameraRig.camera);
    } catch { /* compileAsync is best-effort */ }

    this.hud = new HUD();
    this.wanted.hud = this.hud;
    this.audio = new AudioEngine().init();
    this.radio = new Radio(this.audio);
    this.weapons = new WeaponSystem({
      scene: this.engine.scene, physics: this.physics, player: this.player,
      peds: this.peds, traffic: this.traffic, wanted: this.wanted,
      hud: this.hud, cameraRig: this.cameraRig,
    });
    this.weapons.onShot = (kind) => this.audio.gunshot(kind);
    this.weapons.select('pistol');
    this.pickups = new PickupManager({
      scene: this.engine.scene, city: this.city, player: this.player,
      weapons: this.weapons, hud: this.hud, audio: this.audio,
    });
    this.wanted.onBusted = () => {
      this.money = Math.max(0, this.money - 500);
      this.player.teleport(this.city.playerSpawn());
      // Being arrested ends the job. Without this the mission kept running while the
      // player stood outside the police station on the far side of the map.
      this.missions?.fail('busted');
    };
    this.wanted.onShot = (from, hitPlayer) => {
      this.audio.gunshot('pistol');
      if (hitPlayer) this.hud.flashDamage?.();
      void from;
    };
    this.missions = new MissionManager({
      scene: this.engine.scene, player: this.player, traffic: this.traffic,
      city: this.city, island: this.island, ocean: this.ocean, hud: this.hud,
    });
    this.missions.onReward = (amount) => { this.money += amount; };

    this.weather = new Weather(this.engine.scene, this.atmosphere);
    this.weather.onLightning = () => this.audio.impact(1.6);
    // Materials that should look wet in the rain.
    this.groundMaterials = ['road', 'sidewalk', 'concrete', 'roof'].map((n) => getMaterial(n));
    this.save = new SaveGame(this);

    await this.loading.step(94, 'drawing the map');
    this.minimap = new Minimap(this.hud.el.minimap, {
      island: this.island, city: this.city, highway: this.highway, bridges: this.bridges,
    });
    // Collision damage: Rapier reports contact force magnitudes, which the manager turns
    // into vehicle damage. Wired once, here, rather than polled per frame.
    this.physics.onContact((a, b, kind, magnitude) => {
      if (kind !== 'force') return;
      this.traffic.handleImpact(a, b, magnitude);
    });

    this.pauseMenu = new PauseMenu(this);
    this.phone = new Phone(this);
    this._wireLoop();
    this._wireUI();

    await this.loading.step(100, 'ready');
    this.loading.finish();
    this.hud.show();
    this.engine.start();
    this.hud.say(
      `Click to look around. ${this.input.moveKeysLabel} to move, Shift to sprint.`, 7,
    );
  }

  /** Park a sports car in the road beside the player's spawn point. */
  _spawnStarterCar() {
    const spawn = this.player.position;
    const near = this.city.network.nearestOnRoad(spawn.x, spawn.z);
    if (!near) return;
    const lane = this.city.network.lanePointOnEdge(near.edge, near.t, true, 0);
    this.starterCar = this.traffic._spawn(
      'sports', new Vector3(lane.x, 0.9, lane.z), lane.heading, { colour: 0x9a2f2f },
    );
  }

  /** Moor a boat at the end of each jetty, plus a few drifting out in the bay. */
  _spawnBoats() {
    this.boats = [];
    const classes = Object.keys(BOAT_CLASSES);
    this.moorings.forEach((m, i) => {
      const className = classes[i % classes.length];
      const boat = new Boat(this.physics, this.ocean, {
        className,
        // Start just above the waterline and let buoyancy settle it.
        position: new Vector3(m.x, this.ocean.level + 0.25, m.z),
        heading: m.heading,
        colour: BOAT_COLOURS[i % BOAT_COLOURS.length],
        island: this.island,
      });
      this.traffic.addVehicle(boat);
      this.boats.push(boat);
    });

    // A couple anchored off the harbour mouth so the bay is not empty.
    for (let i = 0; i < 3; i++) {
      const angle = (i / 3) * Math.PI * 2;
      const p = {
        x: this.island.bay.x + Math.cos(angle) * this.island.bay.radius * 0.55,
        z: this.island.bay.z + Math.sin(angle) * this.island.bay.radius * 0.55,
      };
      if (this.island.isLand(p.x, p.z)) continue;
      const boat = new Boat(this.physics, this.ocean, {
        className: 'speedboat',
        position: new Vector3(p.x, this.ocean.level + 0.6, p.z),
        heading: angle,
        colour: BOAT_COLOURS[(i + 2) % BOAT_COLOURS.length],
        island: this.island,
      });
      this.traffic.addVehicle(boat);
      this.boats.push(boat);
    }
  }

  _wireLoop() {
    this.engine.onFixed((dt) => this.fixedUpdate(dt));
    this.engine.onRender((dt) => this.renderUpdate(dt));
    this.engine.onResized = () => {
      this.cameraRig.resize(window.innerWidth / window.innerHeight);
    };
  }

  _wireUI() {
    this.canvas.addEventListener('mousedown', () => {
      // Browsers keep an AudioContext suspended until a user gesture.
      this.audio.resume();
      if (!this.input.mouse.locked && !this.pausedByMenu) this.input.requestLock(this.canvas);
    });
    window.addEventListener('keydown', () => this.audio.resume(), { once: true });

  }

  /** Fixed 1/60 simulation step. */
  fixedUpdate(dt) {
    this.input.pollGamepad();
    this.input.moveVector(this.moveInput);

    const driving = this.player.state === PLAYER_STATE.DRIVING;

    if (!driving) {
      // In free-cam the movement keys fly the camera, so the player stands still.
      const move = this.freeCam.active ? ZERO_MOVE : this.moveInput;
      this.player.fixedUpdate(dt, move, this.cameraRig.yaw, {
        sprint: !this.freeCam.active && this.input.down('sprint'),
        jump: !this.freeCam.active && this.input.pressed('jump'),
        aiming: !this.freeCam.active && this.input.down('aim'),
      });
    }

    // Driver input. Analog triggers win over the digital keys when a pad is connected.
    let vehicleInput = null;
    if (driving && !this.freeCam.active) {
      const pad = this.input.axes;
      const throttle = Math.max(this.moveInput.y > 0 ? this.moveInput.y : 0, pad.throttle);
      const brake = Math.max(this.moveInput.y < 0 ? -this.moveInput.y : 0, pad.brake);
      vehicleInput = {
        throttle, brake,
        steer: this.moveInput.x,
        handbrake: this.input.down('handbrake'),
      };
    } else if (driving) {
      vehicleInput = { throttle: 0, brake: 1, steer: 0, handbrake: true };
    }

    this.profiler.begin('vehicles');
    this.traffic.fixedUpdate(dt, vehicleInput);
    this.profiler.end('vehicles');
    this.profiler.begin('physics');
    this.physics.step();
    this.profiler.end('physics');
  }

  /** Render-rate update: camera, visuals, HUD. */
  renderUpdate(dt) {
    // Look input routes to whichever camera is driving the view.
    const lookTarget = this.freeCam.active ? this.freeCam : this.cameraRig;
    if (this.input.mouse.locked) {
      lookTarget.look(this.input.mouse.dx, this.input.mouse.dy);
    }
    const { lookX, lookY } = this.input.axes;
    if (Math.abs(lookX) + Math.abs(lookY) > 0.02) {
      lookTarget.look(lookX * 620 * dt, lookY * 480 * dt);
    }
    if (this.input.mouse.wheel) this.cameraRig.zoom(-this.input.mouse.wheel);

    if (this.input.pressed('pause')) this.togglePause();
    if (this.input.pressed('debug')) this.hud.showStats = !this.hud.showStats;
    if (this.input.pressed('respawn')) this.player.teleport(this.city.playerSpawn());
    if (this.input.pressed('map')) this.minimap.toggleFull();
    if (this.input.pressed('phone')) this.phone.toggle();
    if (this.phone.open && this.engine.frame % 20 === 0) this.phone.render();
    this._handleVehicleInteraction();

    if (this.input.pressed('freeCam')) {
      if (this.freeCam.active) this.freeCam.disable();
      else this.freeCam.enable(this.cameraRig.camera);
      this.hud.say(this.freeCam.active ? 'Free camera on' : 'Free camera off', 2);
    }

    this.profiler.begin('sync');
    this.physics.sync();
    this.ocean.update(dt, this.cameraTarget);
    this.player.render(dt);
    this.profiler.end('sync');
    this.profiler.begin('vehicleFX');
    this.traffic.render(
      dt, this.atmosphere.isNight, this.cameraRig.camera.position,
      this.weather.wind, this.cameraRig.camera,
    );
    this.profiler.end('vehicleFX');
    if (this.engine.frame % 120 === 0) this.traffic.recycle(this.cameraTarget);

    if (this.freeCam.active) {
      this.freeCam.update(dt, this.cameraRig.camera, this.moveInput, {
        up: this.input.down('camUp'),
        down: this.input.down('camDown'),
        boost: this.input.down('sprint'),
      });
    } else {
      const car = this.traffic.playerVehicle;
      if (car) {
        this.cameraRig.setMode(car.isBoat ? 'boat' : 'vehicle');
        this.cameraRig.update(dt, car.cameraFocus(this._focus), Math.abs(car.speed));
      } else {
        this.cameraRig.setMode(this.player.aiming ? 'aim' : 'onFoot');
        this.cameraRig.update(dt, this.player.position, this.player.speed);
      }
    }
    // Shadows and sky follow whatever the camera is actually looking at.
    this.profiler.begin('atmosphere');
    this.atmosphere.update(dt, this.cameraTarget);
    this.profiler.end('atmosphere');

    this.profiler.begin('weather');
    this.weather.update(dt, this.cameraRig.camera.position);
    this.weather.applyTo(this.groundMaterials);
    this.profiler.end('weather');
    this.save.update(dt);

    // One night factor drives street lamps, lit windows and headlights together.
    const night = this.atmosphere.nightFactor;
    this.props.update(night, this.engine.elapsed);
    this.signage.update(night);
    this.neon.update(night, this.engine.elapsed);
    this.profiler.begin('lights');
    this.nightLights.update(night, this.cameraRig.camera.position, this.traffic.playerVehicle);
    this.profiler.end('lights');
    getMaterial('glassTower').emissiveIntensity = night * 0.85;
    // Traffic runs with lights on after dusk.
    if (night > 0.35 && !this._nightLightsOn) {
      this._nightLightsOn = true;
      for (const v of this.traffic.vehicles) if (!v.isBoat) v.headlightsOn = true;
    } else if (night <= 0.35 && this._nightLightsOn) {
      this._nightLightsOn = false;
      for (const v of this.traffic.vehicles) {
        if (!v.isBoat && v !== this.traffic.playerVehicle) v.headlightsOn = false;
      }
    }

    const car = this.traffic.playerVehicle;
    const onFoot = this.player.state === PLAYER_STATE.ON_FOOT && !this.freeCam.active;

    /* ------------------------------------------------------------- simulation */
    // Crowd, police and weapons run at render rate: they are steering behaviours and
    // hitscans, not rigid-body physics, so they need not be locked to the fixed step.
    const focus = this.cameraTarget;
    this.profiler.begin('peds');
    this.peds.update(dt, focus, { vehicles: this.traffic.vehicles });
    this.peds.render(dt, this.cameraRig.camera.position);
    this.profiler.end('peds');
    this._checkPedCollisions();
    this.profiler.begin('wanted');
    this.wanted.update(dt);
    this.profiler.end('wanted');

    if (this.input.pressed('nextRadio')) this.weapons.next();
    if (this.input.pressed('reload')) this.weapons.reload();
    this.weapons.update(dt, {
      firing: onFoot && this.input.down('fire'),
      firePressed: this.input.pressed('fire'),
      aiming: this.player.aiming,
    });
    if (this.traffic.lastImpact > 0) {
      const hit = this.traffic.lastImpact;
      this.traffic.lastImpact = 0;
      this.audio.impact(Math.min(1.5, hit / 18));
      this.cameraRig.shake(Math.min(0.7, hit * 0.03), 0.3);
      // A heavy shunt hurts the driver too.
      if (hit > 14) this.player.damage(hit * 0.35);
    }

    // Health is checked in one place rather than at each damage site, so nothing can add
    // a new way to hurt the player and forget to handle killing them. `damage()` has
    // always returned true at zero health and every call site discarded it.
    if (this.player.health <= 0) this._onWasted();

    // Splash on entering or leaving the water. The smoke pool doubles as spray: same
    // billboards, brighter tint, shorter life.
    if (this.player.enteredWaterThisStep || this.player.leftWaterThisStep) {
      this.audio.splash();
      const p = this.player.position;
      for (let i = 0; i < 10; i++) {
        this._focus.set(
          p.x + (Math.random() - 0.5) * 1.4, p.y + 0.9, p.z + (Math.random() - 0.5) * 1.4,
        );
        this.traffic.smoke.spawn(this._focus, {
          vx: (Math.random() - 0.5) * 2.4,
          vy: 1.6 + Math.random() * 2,
          vz: (Math.random() - 0.5) * 2.4,
          size: 0.35, life: 0.7, colour: 0.95, growth: 1.1,
        });
      }
      this.player.enteredWaterThisStep = false;
      this.player.leftWaterThisStep = false;
    }

    this.pickups.update(dt, this.player.position);
    this.radio.update();
    this._updateAudio(dt, car);
    this.missions.update(dt);

    /* -------------------------------------------------------------------- hud */
    // Written after the simulation so the HUD reflects this frame, not the last one.
    this.hud.setVitals(this.player.health, this.player.armour);
    this.hud.setMoney(this.money);
    this.hud.setClock(this.atmosphere.clockString());
    this.postfx.setSunElevation(this.atmosphere.sunAbove);
    this.hud.setWanted(this.wanted.stars);
    this.hud.setVehicle(car ? car.speedKmh : null, car ? car.gearLabel : '');
    this.hud.setWeapon(
      onFoot && this.weapons.isArmed ? this.weapons.statusLine : null,
      onFoot && this.weapons.isArmed && this.player.aiming,
    );
    this.hud.setObjective(
      this.missions.active ? this.missions.active.name : null,
      this.missions.statusLine,
    );
    this.hud.update(dt);
    this.profiler.begin('map');
    this._updateMap(car);
    this.profiler.end('map');
    this.hud.setStats([
      `${this.engine.stats.fps} fps   ${this.engine.stats.ms} ms`,
      `${this.engine.backend}`,
      `draws ${this.engine.stats.drawCalls}  tris ${(this.engine.stats.triangles / 1000).toFixed(0)}k`,
      `pos ${this.cameraTarget.x.toFixed(0)} ${this.cameraTarget.y.toFixed(1)} ${this.cameraTarget.z.toFixed(0)}`,
      // A boat has a throttle and a gear label but no gearbox and therefore no `rpm`.
      // Reading it unconditionally threw here on every single frame the player was
      // aboard one, which took the rest of the render update down with it and ran the
      // game at a fraction of real time. Found by an end-to-end input-level smoke test;
      // no amount of looking at screenshots would have surfaced it.
      car
        ? `${car.spec.label}  ${car.speedKmh.toFixed(0)} km/h  gear ${car.gearLabel}`
          + (car.isBoat ? '' : `  ${car.rpm.toFixed(0)} rpm`)
        : `spd ${(this.player.speed * 3.6).toFixed(0)} km/h  ${this.player.isSwimming ? 'swimming' : this.player.grounded ? 'grounded' : 'air'}`,
      `cars ${this.traffic.count} (${this.traffic.trafficCount} ai)   post ${this.postfx.enabled ? this.postfx.quality : 'off'}`,
      `missions ${this.missions.completed}/${this.missions.missions.length}   earned $${this.missions.earned}`,
      `night ${this.atmosphere.nightFactor.toFixed(2)}  ${this.weather.label} (wet ${this.weather.wetness.toFixed(2)})  lit ${this.nightLights.pool.filter((l) => l.visible).length}`,
      `peds ${this.peds.count}  wanted ${this.wanted.stars} (heat ${this.wanted.heat.toFixed(1)})  cops ${this.wanted.units.length}`,
      `${this.weapons.spec.label}  ${this.weapons.magazine}/${this.weapons.reserve}  kills ${this.weapons.kills}  pickups ${this.pickups.collected}/${this.pickups.available}`,
      ...this.profiler.lines(7),
      `skids ${this.traffic.skids.count}  smoke ${this.traffic.smoke.activeCount}` + (car ? `  dmg ${(car.damage * 100).toFixed(0)}%` : ''),
    ]);

    this.profiler.frame(dt);
    this.input.endFrame();
  }

  /**
   * Run pedestrians over. A proximity test against the player's vehicle is enough here:
   * Rapier contact events between a kinematic capsule and a fast car are unreliable at
   * speed, and this also lets us gate on impact speed rather than on mere touching.
   */
  _checkPedCollisions() {
    const car = this.traffic.playerVehicle;
    if (!car || car.isBoat) return;
    const speed = Math.abs(car.speed);
    if (speed < 3.5) return;

    const t = car.body.translation();
    const reach = (car.spec.chassis?.hz ?? 2) + 1.2;
    car.forward(this._forwardScratch ??= new Vector3());
    for (const ped of this.peds.peds) {
      if (!ped.active || ped.state === 'down') continue;
      const dx = ped.position.x - t.x, dz = ped.position.z - t.z;
      if (dx * dx + dz * dz > reach * reach) continue;
      if (this.peds.knockDown(ped, this._forwardScratch)) {
        this.wanted.report(speed > 11 ? CRIME.PED_KILL : CRIME.PED_HIT, 'hit a pedestrian');
        this.cameraRig.shake(0.35, 0.25);
        this.peds.scatter(ped.position, 22);
      }
    }
  }

  /** Refresh radar blips and draw the map. */
  _updateMap(car) {
    const focus = this.cameraTarget;
    const heading = car ? -car.heading : -this.player.yaw;
    const blips = [];
    // Only nearby traffic is worth plotting; the full list would be noise.
    for (const v of this.traffic.vehicles) {
      const t = v.body.translation();
      if (Math.abs(t.x - focus.x) > 300 || Math.abs(t.z - focus.z) > 300) continue;
      blips.push({ x: t.x, z: t.z, kind: v.isBoat ? 'boat' : 'vehicle', size: 2 });
    }
    for (const b of this.peds.blips(focus)) blips.push(b);
    for (const b of this.pickups.blips(focus)) blips.push(b);
    for (const b of this.phone.blips) blips.push(b);
    for (const b of this.wanted.blips) blips.push(b);
    for (const m of this.missions.blips) blips.push({ ...m, kind: 'mission', pin: true, size: 4 });
    this.minimap.setBlips(blips);
    this.minimap.draw(focus, heading);
    this.minimap.drawFull(focus);
  }

  /**
   * Drive the audio mix from game state. The engine loop only exists while the player is
   * in a car, so an idle world costs nothing.
   */
  _updateAudio(dt, car) {
    if (!this.audio.enabled) return;
    if (car && !car.isBoat) {
      this.audio.startEngine();
      this.audio.updateEngine(car.rpm, car.throttle, Math.abs(car.speed));
      // Tyre squeal from handbrake or hard cornering.
      const slip = car.handbrake ? 1 : MathUtils.clamp(
        Math.abs(car.steer) * Math.abs(car.speed) / 22, 0, 1,
      );
      this.audio.updateSkid(slip);
      if (this.input.pressed('horn')) this.audio.horn();
      if (this.input.pressed('nextRadio')) {
        const station = this.radio.next();
        if (!station.silent) this.radio.start();
        this.hud.say(
          station.silent ? 'Radio off' : `${station.name}  -  ${station.tag}`, 2.5,
        );
      }
      // Resume whatever station was tuned when you get back in.
      if (!this.radio.playing && !this.radio.station.silent) this.radio.start();
    } else if (car && car.isBoat) {
      this.audio.startEngine();
      this.audio.updateEngine(1200 + car.throttle * 3600, car.throttle, Math.abs(car.speed));
      this.audio.updateSkid(0);
    } else {
      this.audio.stopEngine();
      this.audio.updateSkid(0);
      // It is a car radio: it goes quiet when you step out.
      this.radio.stop();
    }
    // Sirens whenever police are actively on you.
    this.audio.siren(this.wanted.units.some((u) => u.seen));

    this._updateAmbience(car);
  }

  /**
   * The bed under everything else: city hum, wind, surf.
   *
   * The three beds run continuously from the first user gesture and are only ever
   * re-mixed, never started and stopped, because a bed that fades up from silence is a
   * bed you notice. What varies is the balance: traffic hum falls away as you climb or
   * leave downtown, wind rises with altitude and speed, surf rises as you approach the
   * coastline. Sampled at 6 Hz - none of these inputs change fast enough to care, and
   * `landField` is a noise evaluation we would rather not do every frame.
   */
  _updateAmbience(car) {
    this.audio.startAmbience();
    if (this.engine.frame % 10 !== 0) return;

    const p = this.cameraTarget;
    const speed = car ? Math.abs(car.speed) : this.player.speed;

    // How close we are to open water: the land field is metres-ish inland from the
    // shoreline, so it doubles as a distance-to-surf measure without a second query.
    const f = this.island.landField(p.x, p.z);
    const water = MathUtils.clamp(1 - Math.max(0, f) / 90, 0, 1);

    // Traffic hum tracks how built-up the ground is, not where the camera happens to be
    // looking - fly straight up over downtown and the hum should fade, not vanish.
    const density = {
      [DISTRICT.DOWNTOWN]: 1,
      [DISTRICT.MIDTOWN]: 0.72,
      [DISTRICT.RESIDENTIAL]: 0.4,
      [DISTRICT.INDUSTRIAL]: 0.26,
    }[districtAt(p.x, p.z)] ?? 0.3;

    this.audio.updateAmbience({
      speed,
      height: p.y,
      water,
      density: f > 0 ? density : 0,
      night: this.atmosphere.nightFactor,
    });
  }

  /** Whatever the camera should be following - the car when driving, else the player. */
  get cameraTarget() {
    if (this.freeCam.active) return this.freeCam.position;
    const car = this.traffic?.playerVehicle;
    return car ? car.position : this.player.position;
  }

  /** F to get in or out of the nearest car. */
  _handleVehicleInteraction() {
    if (this.freeCam.active) return;
    const driving = this.player.state === PLAYER_STATE.DRIVING;

    if (driving) {
      this.hud.setPrompt(this.input.actionLabel('interact'), 'Exit vehicle');
      if (this.input.pressed('interact')) {
        this.traffic.exit(this.player);
        this.hud.setPrompt(null);
      }
      if (this.input.pressed('lights')) {
        const car = this.traffic.playerVehicle;
        if (car) car.headlightsOn = !car.headlightsOn;
      }
      return;
    }

    const near = this.traffic.nearestEnterable(this.player.position);
    if (near) {
      this.hud.setPrompt(this.input.actionLabel('interact'), `Enter ${near.spec.label}`);
      if (this.input.pressed('interact')) {
        this.traffic.enter(this.player, near);
        this.hud.setPrompt(null);
        // Taking a car off the street is, technically, a crime.
        if (near !== this.starterCar) this.wanted.report(CRIME.CAR_THEFT, 'car theft');
      }
    } else {
      this.hud.setPrompt(null);
    }
  }

  /**
   * Wasted.
   *
   * The player could not die before this existed: `Player.damage()` returned true at zero
   * health and the single call site threw the result away, so the health bar simply
   * emptied and play continued. That made every threat in the game cosmetic.
   *
   * Recovery is deliberately not free but not punishing either - a hospital fee and the
   * loss of armour and the current job, which is what makes running from a wanted level
   * a decision rather than a formality.
   */
  _onWasted() {
    this.player.health = 100;
    this.player.armour = 0;
    this.money = Math.max(0, this.money - 750);
    // Out of the car first: respawning while still bound to a vehicle leaves the camera
    // following an empty wreck across the map.
    if (this.traffic.playerVehicle) this.traffic.exit(this.player);
    this.wanted.clear();
    this.missions.fail('wasted');
    this.player.teleport(this.city.playerSpawn());
    this.weapons.reload();
    this.hud.say('Wasted  -  $750 in medical bills', 4);
    this.deaths = (this.deaths ?? 0) + 1;
  }

  togglePause() {
    this.pausedByMenu = this.pauseMenu.toggle();
    this.engine.paused = this.pausedByMenu;
    if (this.pausedByMenu) this.input.releaseLock();
  }
}

/** Surface fatal boot errors on the loading screen rather than a blank canvas. */
const game = new Game();
game.boot().catch((err) => {
  console.error('[boot] failed', err);
  game.loading.fail(String(err?.message ?? err));
});

// Expose for console poking during development.
window.game = game;
export { game };
