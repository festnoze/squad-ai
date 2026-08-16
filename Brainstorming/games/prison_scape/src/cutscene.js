import * as THREE from 'three';

/**
 * The opening film. Roughly two and a half minutes of real-time low-poly
 * cinematic that tells the story: the heist, the diamond, the sirens, the
 * arrest, the sentence, and the cell door closing behind you.
 *
 * It is built as a shot list. Every shot names a stage (a set that gets shown
 * while the shot runs), a pair of camera keyframes, and an optional `act`
 * callback that animates the actors with the shot's normalised time.
 */

const NIGHT_FOG = 0x090c14;

// ---------------------------------------------------------------- utilities
function box(parent, w, h, d, color, x, y, z, ry = 0, opts = {}) {
  const mat = opts.emissive
    ? new THREE.MeshBasicMaterial({ color, transparent: !!opts.opacity, opacity: opts.opacity ?? 1 })
    : new THREE.MeshLambertMaterial({
      color,
      transparent: opts.opacity !== undefined,
      opacity: opts.opacity ?? 1,
      emissive: opts.glow ?? 0x000000,
    });
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, y, z);
  m.rotation.y = ry;
  parent.add(m);
  return m;
}

function ease(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }
function lerp3(a, b, t, out) {
  out.set(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t);
  return out;
}

/** A blocky person: works as thief, officer, judge or inmate by recolouring. */
function buildFigure(colors) {
  const g = new THREE.Group();
  const body = new THREE.MeshLambertMaterial({ color: colors.body });
  const limb = new THREE.MeshLambertMaterial({ color: colors.limb ?? colors.body });
  const skin = new THREE.MeshLambertMaterial({ color: colors.skin ?? 0xc79a7a });

  const mesh = (w, h, d, mat, x, y, z, parent = g) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.position.set(x, y, z);
    parent.add(m);
    return m;
  };

  mesh(0.60, 0.70, 0.34, body, 0, 1.25, 0);
  const head = mesh(0.30, 0.30, 0.30, skin, 0, 1.75, 0);
  if (colors.hat) mesh(0.38, 0.12, 0.38, new THREE.MeshLambertMaterial({ color: colors.hat }), 0, 1.94, 0);
  if (colors.mask) mesh(0.32, 0.12, 0.32, new THREE.MeshLambertMaterial({ color: colors.mask }), 0, 1.80, 0);

  const armL = new THREE.Group(); armL.position.set(-0.39, 1.54, 0); g.add(armL);
  mesh(0.17, 0.60, 0.19, limb, 0, -0.30, 0, armL);
  const armR = new THREE.Group(); armR.position.set(0.39, 1.54, 0); g.add(armR);
  mesh(0.17, 0.60, 0.19, limb, 0, -0.30, 0, armR);
  const legL = new THREE.Group(); legL.position.set(-0.17, 0.90, 0); g.add(legL);
  mesh(0.23, 0.90, 0.25, limb, 0, -0.45, 0, legL);
  const legR = new THREE.Group(); legR.position.set(0.17, 0.90, 0); g.add(legR);
  mesh(0.23, 0.90, 0.25, limb, 0, -0.45, 0, legR);

  g.userData = { armL, armR, legL, legR, head };
  return g;
}

/** Drives a figure's limbs from a phase value. */
function walk(fig, phase, amount = 1) {
  const s = Math.sin(phase) * 0.8 * amount;
  fig.userData.legL.rotation.x = s;
  fig.userData.legR.rotation.x = -s;
  fig.userData.armL.rotation.x = -s * 0.8;
  fig.userData.armR.rotation.x = s * 0.8;
}

function raise(fig, t) {
  fig.userData.armL.rotation.x = -2.6 * t;
  fig.userData.armR.rotation.x = -2.6 * t;
  fig.userData.armL.rotation.z = 0.35 * t;
  fig.userData.armR.rotation.z = -0.35 * t;
}

export class Cutscene {
  constructor(renderer, audio, onSubtitle) {
    this.renderer = renderer;
    this.audio = audio;
    this.onSubtitle = onSubtitle;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(NIGHT_FOG);
    this.scene.fog = new THREE.Fog(NIGHT_FOG, 20, 160);

    this.camera = new THREE.PerspectiveCamera(38, 16 / 9, 0.1, 600);
    this.camera.rotation.order = 'YXZ';

    this.key = new THREE.DirectionalLight(0xb4c6ff, 1.15);
    this.key.position.set(-30, 60, 25);
    this.scene.add(this.key);
    this.fill = new THREE.HemisphereLight(0x4a5a80, 0x14171f, 1.35);
    this.scene.add(this.fill);
    this.scene.add(new THREE.AmbientLight(0x39445c, 0.55));
    this.spot = new THREE.PointLight(0xffd9a0, 0, 40, 2);
    this.scene.add(this.spot);
    this.flashLight = new THREE.PointLight(0xff3030, 0, 50, 2);
    this.scene.add(this.flashLight);

    this.stages = {};
    this._buildStages();
    this._buildRain();

    this.shots = buildShotList();
    this.duration = this.shots.reduce((a, s) => a + s.dur, 0);
    this.time = 0;
    this.finished = false;
    this._currentStage = null;
    this._shotIndex = -1;
    this._subtitle = null;
    this._tmpA = new THREE.Vector3();
    this._tmpB = new THREE.Vector3();
    this._cued = new Set();
  }

  // -------------------------------------------------------------- the sets
  _buildStages() {
    this._stageCity();
    this._stageVault();
    this._stageStreet();
    this._stageAlley();
    this._stageCourt();
    this._stagePrison();
    this._stageCell();
    for (const s of Object.values(this.stages)) {
      s.group.visible = false;
      this.scene.add(s.group);
    }
  }

  /** Skyline plus the museum facade. Shots 1-3. */
  _stageCity() {
    const g = new THREE.Group();
    const palette = [0x11151f, 0x161b27, 0x0d1119, 0x1a2030];
    let seed = 7;
    const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;

    for (let i = 0; i < 90; i++) {
      const w = 6 + rnd() * 14;
      const h = 12 + rnd() * 70;
      const d = 6 + rnd() * 14;
      const x = -160 + rnd() * 320;
      const z = -240 + rnd() * 200;
      if (Math.abs(x) < 26 && z > -70) continue;   // keep the museum plaza clear
      box(g, w, h, d, palette[(rnd() * palette.length) | 0], x, h / 2, z);
      // lit windows
      const rows = Math.max(1, Math.floor(h / 6));
      for (let r = 0; r < rows; r++) {
        if (rnd() > 0.42) continue;
        box(g, w * 0.7, 1.1, 0.3, 0xffd9a0, x, 3 + r * 6, z + d / 2 + 0.2, 0, { emissive: true, opacity: 0.55 });
      }
    }

    // ground plane and wet street sheen
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(600, 600),
      new THREE.MeshLambertMaterial({ color: 0x0b0e15 })
    );
    ground.rotation.x = -Math.PI / 2;
    g.add(ground);

    // The museum: colonnade, pediment, banner, steps.
    const museum = new THREE.Group();
    museum.position.set(0, 0, -40);
    g.add(museum);
    box(museum, 44, 2.0, 26, 0x2b2f38, 0, 1.0, 0);
    for (let i = 0; i < 4; i++) box(museum, 46 - i * 2, 0.7, 28 - i * 2, 0x333842, 0, 0.35 + i * 0.7, 4 + i * 0.9);
    box(museum, 40, 18, 20, 0x242833, 0, 11, -2);
    for (let i = -4; i <= 4; i++) {
      const col = new THREE.Mesh(
        new THREE.CylinderGeometry(1.05, 1.05, 16, 10),
        new THREE.MeshLambertMaterial({ color: 0x3a4150 })
      );
      col.position.set(i * 4.4, 10, 8);
      museum.add(col);
    }
    box(museum, 42, 2.2, 22, 0x3a4150, 0, 19.2, 2);
    // Triangular pediment: a 3-sided prism tipped onto its side. thetaStart of
    // -90 degrees puts the apex up and the flat edge down once rotated.
    const ped = new THREE.Mesh(
      new THREE.CylinderGeometry(13, 13, 10, 3, 1, false, -Math.PI / 2),
      new THREE.MeshLambertMaterial({ color: 0x39404e })
    );
    ped.rotation.x = Math.PI / 2;
    ped.scale.set(1.55, 1, 0.30);
    ped.position.set(0, 22.2, 5);
    museum.add(ped);
    box(museum, 16, 6, 0.4, 0x8a2530, 0, 13, 18.3, 0, { glow: 0x2a0a0d });
    box(museum, 13, 1.1, 0.5, 0xf0e6d0, 0, 14.4, 18.6, 0, { emissive: true });
    box(museum, 9, 0.7, 0.5, 0xd8c48a, 0, 12.4, 18.6, 0, { emissive: true });
    this.spotMuseum = new THREE.PointLight(0xffe0b0, 5.5, 70, 2);
    this.spotMuseum.position.set(0, 16, -18);
    g.add(this.spotMuseum);
    const uplight = new THREE.PointLight(0xffd8a0, 3.0, 46, 2);
    uplight.position.set(0, 3, -22);
    g.add(uplight);

    // The thief on the museum roof.
    const thief = buildFigure({ body: 0x14161c, limb: 0x0f1115, mask: 0x0a0b0e, skin: 0xbb8f6e });
    thief.position.set(-16, 22.4, 2);
    g.add(thief);

    // A rooftop water tank and vents for parallax.
    box(g, 5, 5, 5, 0x1a1e27, 14, 24.8, -6);
    box(g, 3, 2, 3, 0x1a1e27, 8, 23.3, 6);

    const moon = new THREE.Mesh(
      new THREE.CircleGeometry(9, 24),
      new THREE.MeshBasicMaterial({ color: 0xdfe6f5 })
    );
    moon.position.set(-90, 96, -230);
    g.add(moon);

    this.stages.city = { group: g, thief, museum };
  }

  /** The vault: pedestal, diamond, laser grid, rope descent. Shots 4-6. */
  _stageVault() {
    const g = new THREE.Group();
    g.position.set(0, -400, 0);   // parked far from the other sets

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(60, 60),
      new THREE.MeshLambertMaterial({ color: 0x14161d })
    );
    floor.rotation.x = -Math.PI / 2;
    g.add(floor);
    for (let i = -3; i <= 3; i++) {
      box(g, 60, 0.06, 0.12, 0x232935, 0, 0.03, i * 4);
      box(g, 0.12, 0.06, 60, 0x232935, i * 4, 0.03, 0);
    }
    // walls with display alcoves
    box(g, 60, 14, 1, 0x1b2029, 0, 7, -22);
    box(g, 1, 14, 44, 0x1b2029, -24, 7, 0);
    box(g, 1, 14, 44, 0x1b2029, 24, 7, 0);
    for (let i = -2; i <= 2; i++) {
      box(g, 4.4, 6, 0.6, 0x0d1015, i * 8, 5, -21.3);
      box(g, 3.6, 5, 0.3, 0x2b3a4a, i * 8, 5, -20.9, 0, { glow: 0x0a1a24 });
    }
    // ceiling with a hole the thief came through
    box(g, 60, 0.6, 44, 0x121620, 0, 14, 0);
    box(g, 3.4, 0.9, 3.4, 0x000000, 0, 14, 6, 0, { emissive: true });

    // pedestal + display case + the diamond itself
    const pedestal = new THREE.Group();
    pedestal.position.set(0, 0, 0);
    g.add(pedestal);
    box(pedestal, 2.6, 0.4, 2.6, 0x2c323d, 0, 0.2, 0);
    box(pedestal, 1.8, 2.6, 1.8, 0x22272f, 0, 1.7, 0);
    box(pedestal, 2.4, 0.25, 2.4, 0x3a4150, 0, 3.1, 0);
    const glass = new THREE.Mesh(
      new THREE.BoxGeometry(2.0, 2.2, 2.0),
      new THREE.MeshLambertMaterial({ color: 0x9fd8ff, transparent: true, opacity: 0.16 })
    );
    glass.position.y = 4.3;
    pedestal.add(glass);

    const diamond = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.55, 0),
      new THREE.MeshBasicMaterial({ color: 0xbdf0ff })
    );
    diamond.position.set(0, 4.0, 0);
    pedestal.add(diamond);
    const diamondGlow = new THREE.PointLight(0x9fe4ff, 2.6, 16, 2);
    diamondGlow.position.copy(diamond.position);
    pedestal.add(diamondGlow);

    // laser grid
    const lasers = new THREE.Group();
    g.add(lasers);
    const laserMat = new THREE.MeshBasicMaterial({
      color: 0x35ff8a, transparent: true, opacity: 0.45, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    for (let i = 0; i < 7; i++) {
      const beam = new THREE.Mesh(new THREE.BoxGeometry(30, 0.035, 0.035), laserMat);
      beam.position.set(0, 1.0 + i * 1.1, -6 + (i % 3) * 6);
      lasers.add(beam);
    }
    for (let i = 0; i < 5; i++) {
      const beam = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.035, 26), laserMat);
      beam.position.set(-8 + i * 4, 1.6 + (i % 2) * 2.2, 0);
      lasers.add(beam);
    }

    // rope + thief descending
    const rope = new THREE.Mesh(
      new THREE.CylinderGeometry(0.045, 0.045, 12, 6),
      new THREE.MeshBasicMaterial({ color: 0x2a2f36 })
    );
    rope.position.set(0, 8, 6);
    g.add(rope);
    const thief = buildFigure({ body: 0x14161c, limb: 0x0f1115, mask: 0x0a0b0e, skin: 0xbb8f6e });
    thief.position.set(0, 6, 6);
    g.add(thief);

    // The alarm strobes on the walls, dark until shot 6.
    const strobes = [];
    for (const x of [-16, 16]) {
      const s = box(g, 1.0, 0.5, 0.5, 0x3a1013, x, 10, -21.2, 0, { emissive: true });
      strobes.push(s);
    }

    this.stages.vault = {
      group: g, thief, rope, diamond, diamondGlow, glass, lasers, laserMat, strobes, pedestal,
    };
  }

  /** Rain-slick street with police cars closing in. Shot 7. */
  _stageStreet() {
    const g = new THREE.Group();
    g.position.set(400, 0, 0);

    const road = new THREE.Mesh(
      new THREE.PlaneGeometry(40, 320),
      new THREE.MeshLambertMaterial({ color: 0x14171d })
    );
    road.rotation.x = -Math.PI / 2;
    g.add(road);
    for (let i = 0; i < 30; i++) box(g, 0.5, 0.02, 4, 0xb8b09a, 0, 0.02, -150 + i * 10);

    // buildings either side
    let seed = 19;
    const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
    for (let side of [-1, 1]) {
      for (let i = 0; i < 26; i++) {
        const h = 14 + rnd() * 40;
        const d = 10 + rnd() * 12;
        box(g, 16 + rnd() * 8, h, d, 0x171c27, side * (28 + rnd() * 6), h / 2, -140 + i * 12);
        for (let r = 0; r < 4; r++) {
          if (rnd() > 0.5) continue;
          box(g, 8, 1.0, 0.3, 0xffcf8a, side * 20.2, 4 + r * 6, -140 + i * 12 + d / 2, 0, { emissive: true, opacity: 0.5 });
        }
      }
      for (let i = 0; i < 12; i++) {
        box(g, 0.4, 8, 0.4, 0x2a2f38, side * 17, 4, -130 + i * 24);
        box(g, 2.4, 0.4, 0.8, 0xffd9a0, side * 15.6, 8.1, -130 + i * 24, 0, { emissive: true });
      }
    }

    const thief = buildFigure({ body: 0x14161c, limb: 0x0f1115, mask: 0x0a0b0e, skin: 0xbb8f6e });
    thief.position.set(0, 0, 0);
    g.add(thief);

    const cars = [];
    for (let i = 0; i < 3; i++) {
      const car = buildPoliceCar();
      car.position.set(i === 2 ? 0 : (i === 0 ? -7 : 7), 0, 40 + i * 14);
      car.rotation.y = Math.PI;
      g.add(car);
      cars.push(car);
    }

    this.stages.street = { group: g, thief, cars };
  }

  /** Dead-end alley and the arrest. Shots 8-10. */
  _stageAlley() {
    const g = new THREE.Group();
    g.position.set(-400, 0, 0);

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(200, 200),
      new THREE.MeshLambertMaterial({ color: 0x101319 })
    );
    ground.rotation.x = -Math.PI / 2;
    g.add(ground);

    box(g, 1.5, 34, 70, 0x191d26, -9, 17, -10);
    box(g, 1.5, 34, 70, 0x1b2029, 9, 17, -10);
    box(g, 20, 26, 1.5, 0x22272f, 0, 13, -44);           // the wall he cannot climb
    for (let i = 0; i < 5; i++) box(g, 3, 0.3, 1.2, 0x2f3540, -6.5, 2 + i * 2.4, -43.2);  // useless ladder rungs
    // dumpsters and crates
    box(g, 3.4, 2.4, 2.0, 0x1f3a2a, -6.5, 1.2, -30);
    box(g, 3.4, 2.4, 2.0, 0x2a2f1f, 6.5, 1.2, -36);
    box(g, 1.6, 1.6, 1.6, 0x2b241a, 6.0, 0.8, -25);
    // fire escapes
    for (let i = 0; i < 4; i++) {
      box(g, 1.2, 0.2, 8, 0x2a3038, 8.2, 6 + i * 5, -18 - i * 3);
      box(g, 0.15, 3.4, 0.15, 0x2a3038, 8.6, 7.7 + i * 5, -14 - i * 3);
    }

    const thief = buildFigure({ body: 0x14161c, limb: 0x0f1115, mask: 0x0a0b0e, skin: 0xbb8f6e });
    thief.position.set(0, 0, -34);
    g.add(thief);

    const cops = [];
    for (let i = 0; i < 5; i++) {
      const cop = buildFigure({ body: 0x1d2540, limb: 0x161c30, hat: 0x11162a, skin: 0xc79a7a });
      cop.position.set(-6 + i * 3, 0, -14 - (i % 2) * 2.5);
      cop.rotation.y = Math.PI;
      g.add(cop);
      cops.push(cop);
    }
    const cars = [];
    for (let i = 0; i < 2; i++) {
      const car = buildPoliceCar();
      car.position.set(i === 0 ? -5 : 5, 0, -4);
      car.rotation.y = Math.PI + (i === 0 ? 0.4 : -0.4);
      g.add(car);
      cars.push(car);
    }

    // the diamond, dropped
    const diamond = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.4, 0),
      new THREE.MeshBasicMaterial({ color: 0xbdf0ff })
    );
    diamond.position.set(0, 0.4, -32);
    diamond.visible = false;
    g.add(diamond);
    const dGlow = new THREE.PointLight(0x9fe4ff, 0, 12, 2);
    g.add(dGlow);

    // Helicopter searchlight cone above the alley. Kept narrow and centred on
    // the thief so the camera never ends up inside it and washes the shot out.
    const beam = new THREE.Mesh(
      new THREE.ConeGeometry(4.5, 40, 18, 1, true),
      new THREE.MeshBasicMaterial({
        color: 0xfff0c0, transparent: true, opacity: 0.0,
        side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
      })
    );
    beam.position.set(0, 20, -36);
    g.add(beam);
    const heliLight = new THREE.PointLight(0xfff0c0, 0, 60, 2);
    heliLight.position.set(0, 26, -36);
    g.add(heliLight);

    this.stages.alley = { group: g, thief, cops, cars, diamond, dGlow, beam, heliLight };
  }

  /** Courtroom. Shot 11. */
  _stageCourt() {
    const g = new THREE.Group();
    g.position.set(0, 400, 0);

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(60, 60),
      new THREE.MeshLambertMaterial({ color: 0x2a1f16 })
    );
    floor.rotation.x = -Math.PI / 2;
    g.add(floor);
    box(g, 44, 16, 1, 0x3a2a1c, 0, 8, -18);
    box(g, 1, 16, 40, 0x3a2a1c, -22, 8, 0);
    box(g, 1, 16, 40, 0x3a2a1c, 22, 8, 0);
    box(g, 44, 0.8, 40, 0x1d1610, 0, 16, 0);
    // bench
    box(g, 16, 3.0, 3.0, 0x4a3624, 0, 1.5, -12);
    box(g, 17, 1.2, 3.4, 0x5b432c, 0, 3.4, -12);
    box(g, 20, 8, 0.6, 0x342518, 0, 8, -16.5);
    box(g, 4, 5, 0.3, 0x8a7440, 0, 10, -16.1, 0, { glow: 0x241c0a });
    // gallery pews
    for (let i = 0; i < 4; i++) {
      box(g, 26, 1.0, 1.2, 0x4a3624, 0, 0.6, 4 + i * 4);
      box(g, 26, 2.0, 0.4, 0x40301f, 0, 1.4, 4.7 + i * 4);
    }
    const judge = buildFigure({ body: 0x14141a, limb: 0x101016, skin: 0xd6b394 });
    judge.position.set(0, 3.4, -13.6);
    judge.rotation.y = Math.PI;
    g.add(judge);
    const gavel = box(g, 0.5, 0.5, 1.4, 0x6b4a28, 1.6, 4.7, -11.0);

    const accused = buildFigure({ body: 0x8c8378, limb: 0x7a7266, skin: 0xbb8f6e });
    accused.position.set(0, 0, 2);
    g.add(accused);
    const guards = [];
    for (const x of [-2.4, 2.4]) {
      const gd = buildFigure({ body: 0x1d2540, limb: 0x161c30, hat: 0x11162a });
      gd.position.set(x, 0, 2.6);
      g.add(gd);
      guards.push(gd);
    }

    const shaft = new THREE.Mesh(
      new THREE.ConeGeometry(6, 18, 14, 1, true),
      new THREE.MeshBasicMaterial({
        color: 0xffe6b8, transparent: true, opacity: 0.06,
        side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
      })
    );
    shaft.position.set(-4, 9, -4);
    g.add(shaft);
    const lamp = new THREE.PointLight(0xffe6b8, 1.6, 40, 2);
    lamp.position.set(-4, 13, -4);
    g.add(lamp);

    this.stages.court = { group: g, judge, gavel, accused, guards };
  }

  /** The penitentiary seen from outside, at dawn. Shot 12. */
  _stagePrison() {
    const g = new THREE.Group();
    g.position.set(0, -800, 0);

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(600, 600),
      new THREE.MeshLambertMaterial({ color: 0x2a2b22 })
    );
    ground.rotation.x = -Math.PI / 2;
    g.add(ground);
    // approach road
    box(g, 12, 0.05, 300, 0x1b1c20, 0, 0.03, 60);

    // perimeter wall with towers
    box(g, 200, 14, 2.4, 0x5a5b52, 0, 7, -30);
    box(g, 2.4, 14, 90, 0x5a5b52, -100, 7, -74);
    box(g, 2.4, 14, 90, 0x5a5b52, 100, 7, -74);
    for (const x of [-100, -50, 0, 50, 100]) {
      box(g, 7, 5, 7, 0x4e4f47, x, 16, -30);
      box(g, 9, 1.0, 9, 0x3f403a, x, 19, -30);
      const lamp = box(g, 1.4, 1.0, 0.8, 0xfff2c8, x, 17.6, -25.6, 0, { emissive: true });
      void lamp;
    }
    // gatehouse
    box(g, 26, 16, 10, 0x4e4f47, 0, 8, -34);
    box(g, 12, 11, 1.2, 0x2f3129, 0, 5.5, -29.2);
    box(g, 12, 0.9, 1.4, 0xb8362f, 0, 11.4, -29.0, 0, { glow: 0x2a0a08 });

    // cell blocks behind the wall
    for (let i = 0; i < 3; i++) {
      box(g, 46, 20, 22, 0x4a4b44, -55 + i * 55, 10, -70 - (i % 2) * 12);
      for (let r = 0; r < 4; r++) {
        for (let c = 0; c < 8; c++) {
          box(g, 1.6, 2.4, 0.4, 0x1a1c18, -55 + i * 55 - 17 + c * 5, 4 + r * 4.6, -70 - (i % 2) * 12 + 11.2, 0, { glow: 0x2a2410 });
        }
      }
    }

    const van = new THREE.Group();
    box(van, 3.4, 2.0, 2.6, 0x2a3244, 0, 2.4, -2.4);
    box(van, 3.6, 3.0, 7.0, 0x3a4459, 0, 2.9, 2.4);
    box(van, 3.0, 0.9, 0.3, 0x11141c, 0, 3.6, 5.9);
    for (const [x, z] of [[-1.7, -2.6], [1.7, -2.6], [-1.7, 3.6], [1.7, 3.6]]) {
      const w = new THREE.Mesh(
        new THREE.CylinderGeometry(0.8, 0.8, 0.5, 10),
        new THREE.MeshLambertMaterial({ color: 0x14161a })
      );
      w.rotation.z = Math.PI / 2;
      w.position.set(x, 0.8, z);
      van.add(w);
    }
    box(van, 0.5, 0.4, 0.3, 0xff3a2a, -1.2, 4.5, 0, 0, { emissive: true });
    box(van, 0.5, 0.4, 0.3, 0x3a6aff, 1.2, 4.5, 0, 0, { emissive: true });
    van.position.set(0, 0, 60);
    g.add(van);

    const sun = new THREE.Mesh(
      new THREE.CircleGeometry(14, 24),
      new THREE.MeshBasicMaterial({ color: 0xff9a5a })
    );
    sun.position.set(60, 22, -260);
    g.add(sun);

    this.stages.prison = { group: g, van };
  }

  /** Cell wing interior: the last shots and the title card. */
  _stageCell() {
    const g = new THREE.Group();
    g.position.set(800, 0, 0);

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(120, 60),
      new THREE.MeshLambertMaterial({ color: 0x3c3f42 })
    );
    floor.rotation.x = -Math.PI / 2;
    g.add(floor);
    box(g, 120, 0.6, 60, 0x22262b, 0, 9, 0);

    // corridor walls with cell openings on both sides
    for (const side of [-1, 1]) {
      for (let i = 0; i < 8; i++) {
        box(g, 2.2, 9, 4.0, 0x6f7a6a, -30 + i * 8, 4.5, side * 8);
      }
      box(g, 66, 9, 0.6, 0x6f7a6a, 0, 4.5, side * 10.2);
    }
    // barred gates along the corridor
    const gates = [];
    for (const side of [-1, 1]) {
      for (let i = 0; i < 7; i++) {
        const gate = new THREE.Group();
        for (let b = 0; b < 6; b++) {
          box(gate, 0.14, 8, 0.14, 0x878f95, -2.2 + b * 0.9, 4, 0);
        }
        box(gate, 5.6, 0.22, 0.22, 0x6b7379, 0, 7.6, 0);
        box(gate, 5.6, 0.22, 0.22, 0x6b7379, 0, 0.6, 0);
        gate.position.set(-26 + i * 8, 0, side * 8);
        g.add(gate);
        gates.push(gate);
      }
    }
    // strip lights
    for (let i = 0; i < 9; i++) {
      box(g, 5, 0.2, 0.5, 0xdfe6ee, -32 + i * 8, 8.6, 0, 0, { emissive: true });
    }
    const lamp = new THREE.PointLight(0xffeccb, 2.4, 44, 2);
    lamp.position.set(0, 8, 0);
    g.add(lamp);

    // the player's cell, at the far end
    const cell = new THREE.Group();
    cell.position.set(-26, 0, -14);
    g.add(cell);
    box(cell, 10, 9, 0.6, 0x7c8578, 0, 4.5, -4);
    box(cell, 0.6, 9, 8, 0x7c8578, -5, 4.5, 0);
    box(cell, 0.6, 9, 8, 0x7c8578, 5, 4.5, 0);
    box(cell, 3.6, 0.3, 6.4, 0x5b6167, -2.6, 1.1, 0);
    box(cell, 3.4, 0.35, 6.2, 0x8a8272, -2.6, 1.35, 0);
    box(cell, 3.6, 0.3, 6.4, 0x5b6167, -2.6, 3.2, 0);
    box(cell, 3.4, 0.35, 6.2, 0x8a8272, -2.6, 3.45, 0);
    box(cell, 1.4, 1.3, 1.2, 0xb9bec0, 3.6, 0.65, -2.6);
    // barred window with moonlight
    box(cell, 3.0, 2.6, 0.2, 0x0d1622, 0, 6.2, -4.2, 0, { emissive: true });
    for (let i = 0; i < 4; i++) box(cell, 0.14, 2.6, 0.3, 0x5b6167, -1.1 + i * 0.72, 6.2, -4.25);
    // Sits against the far wall, well clear of the camera path.
    const moonShaft = new THREE.Mesh(
      new THREE.ConeGeometry(1.5, 9, 12, 1, true),
      new THREE.MeshBasicMaterial({
        color: 0x9fc4ff, transparent: true, opacity: 0.09,
        side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
      })
    );
    moonShaft.position.set(2.4, 3.4, -2.6);
    moonShaft.rotation.z = 0.30;
    moonShaft.rotation.x = -0.30;
    cell.add(moonShaft);

    // the inmate walking in, and the gate that shuts on him
    const inmate = buildFigure({ body: 0xb56a3a, limb: 0xa15c31, skin: 0xbb8f6e });
    inmate.position.set(-26, 0, 2);
    g.add(inmate);
    const escort = buildFigure({ body: 0x1d2540, limb: 0x161c30, hat: 0x11162a });
    escort.position.set(-26, 0, 5);
    g.add(escort);

    const cellGate = new THREE.Group();
    for (let b = 0; b < 7; b++) box(cellGate, 0.16, 8.2, 0.16, 0x9aa2a8, -2.7 + b * 0.9, 4.1, 0);
    box(cellGate, 6.2, 0.24, 0.24, 0x7b8389, 0, 7.8, 0);
    box(cellGate, 6.2, 0.24, 0.24, 0x7b8389, 0, 0.5, 0);
    cellGate.position.set(-26 + 7, 0, -9.6);
    g.add(cellGate);

    this.stages.cell = { group: g, cell, inmate, escort, cellGate, gates, moonShaft };
  }

  /** Falling rain, shown only on the outdoor night shots. */
  _buildRain() {
    const COUNT = 1400;
    const pos = new Float32Array(COUNT * 3);
    for (let i = 0; i < COUNT; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 90;
      pos[i * 3 + 1] = Math.random() * 60;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 90;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    this.rain = new THREE.Points(geo, new THREE.PointsMaterial({
      color: 0x9fb6d8, size: 0.16, transparent: true, opacity: 0.5, depthWrite: false,
    }));
    this.rain.frustumCulled = false;
    this.rain.visible = false;
    this.scene.add(this.rain);
    this._rainSpeed = 46;
  }

  /** Drop the rain field around wherever the next shot starts. */
  _reseedRain(shot) {
    const origin = this.stages[shot.stage].group.position;
    const p = this.rain.geometry.attributes.position.array;
    for (let i = 0; i < p.length; i += 3) {
      p[i] = origin.x + shot.from[0] + (Math.random() - 0.5) * 90;
      p[i + 1] = origin.y + shot.from[1] + (Math.random() - 0.5) * 60;
      p[i + 2] = origin.z + shot.from[2] + (Math.random() - 0.5) * 90;
    }
    this.rain.geometry.attributes.position.needsUpdate = true;
  }

  _updateRain(dt) {
    if (!this.rain.visible) return;
    const p = this.rain.geometry.attributes.position.array;
    const base = this.camera.position;
    for (let i = 0; i < p.length; i += 3) {
      p[i + 1] -= this._rainSpeed * dt;
      if (p[i + 1] < base.y - 30) {
        p[i] = base.x + (Math.random() - 0.5) * 90;
        p[i + 1] = base.y + 30;
        p[i + 2] = base.z + (Math.random() - 0.5) * 90;
      }
    }
    this.rain.geometry.attributes.position.needsUpdate = true;
  }

  // ------------------------------------------------------------- playback
  start() {
    this.time = 0;
    this.finished = false;
    this._shotIndex = -1;
    this._cued.clear();
    this.audio.startDrone(46);
  }

  skip() {
    this.finished = true;
    this.onSubtitle(null);
    this.audio.stopDrone();
  }

  _showStage(name) {
    if (this._currentStage === name) return;
    for (const [key, s] of Object.entries(this.stages)) s.group.visible = key === name;
    this._currentStage = name;
  }

  /** One-shot audio/lighting cues, fired at most once per playthrough. */
  _cue(key, fn) {
    if (this._cued.has(key)) return;
    this._cued.add(key);
    fn();
  }

  update(dt) {
    if (this.finished) return;
    this.time += dt;

    // locate the current shot
    let acc = 0;
    let index = -1;
    let local = 0;
    for (let i = 0; i < this.shots.length; i++) {
      if (this.time < acc + this.shots[i].dur) {
        index = i;
        local = this.time - acc;
        break;
      }
      acc += this.shots[i].dur;
    }
    if (index === -1) {
      this.finished = true;
      this.onSubtitle(null);
      this.audio.stopDrone();
      return;
    }

    const shot = this.shots[index];
    if (index !== this._shotIndex) {
      this._shotIndex = index;
      this._showStage(shot.stage);
      this.onSubtitle(shot.text ?? null);
      if (shot.rain && !this.rain.visible) this._reseedRain(shot);
      this.rain.visible = !!shot.rain;
      this.camera.fov = shot.fov ?? 38;
      this.camera.updateProjectionMatrix();
      this.scene.fog.near = shot.fogNear ?? 20;
      this.scene.fog.far = shot.fogFar ?? 160;
      this.scene.background.setHex(shot.bg ?? NIGHT_FOG);
      this.scene.fog.color.setHex(shot.bg ?? NIGHT_FOG);
    }

    const u = Math.min(1, local / shot.dur);
    const e = shot.linear ? u : ease(u);

    const origin = this.stages[shot.stage].group.position;
    lerp3(shot.from, shot.to, e, this._tmpA).add(origin);
    lerp3(shot.lookFrom, shot.lookTo ?? shot.lookFrom, e, this._tmpB).add(origin);

    if (shot.shake) {
      const s = shot.shake * (1 - u * 0.5);
      this._tmpA.x += (Math.random() - 0.5) * s;
      this._tmpA.y += (Math.random() - 0.5) * s;
      this._tmpA.z += (Math.random() - 0.5) * s;
    }
    this.camera.position.copy(this._tmpA);
    this.camera.lookAt(this._tmpB);
    if (shot.roll) this.camera.rotateZ(shot.roll * Math.sin(u * Math.PI));

    if (shot.act) shot.act(this, u, dt, local);
    this._updateRain(dt);
  }

  render() {
    this.renderer.render(this.scene, this.camera);
  }

  resize(aspect) {
    this.camera.aspect = aspect;
    this.camera.updateProjectionMatrix();
  }

  dispose() {
    this.audio.stopDrone();
  }
}

/** Police cruiser: white body, blue stripe, light bar. */
function buildPoliceCar() {
  const g = new THREE.Group();
  box(g, 3.2, 1.0, 7.2, 0xe8eaee, 0, 1.0, 0);
  box(g, 3.0, 0.9, 3.6, 0x2b3346, 0, 1.9, -0.3);
  box(g, 3.24, 0.5, 5.0, 0x2a52a8, 0, 1.05, 0.2);
  box(g, 1.5, 0.35, 0.45, 0x1a1e26, 0, 2.45, -0.3);
  const blue = box(g, 0.6, 0.3, 0.4, 0x3a6aff, -0.45, 2.6, -0.3, 0, { emissive: true });
  const red = box(g, 0.6, 0.3, 0.4, 0xff3a2a, 0.45, 2.6, -0.3, 0, { emissive: true });
  box(g, 2.2, 0.3, 0.3, 0xfff0c0, 0, 1.2, 3.6, 0, { emissive: true });
  for (const [x, z] of [[-1.55, -2.4], [1.55, -2.4], [-1.55, 2.4], [1.55, 2.4]]) {
    const w = new THREE.Mesh(
      new THREE.CylinderGeometry(0.7, 0.7, 0.45, 10),
      new THREE.MeshLambertMaterial({ color: 0x111318 })
    );
    w.rotation.z = Math.PI / 2;
    w.position.set(x, 0.7, z);
    g.add(w);
  }
  const blueLight = new THREE.PointLight(0x3a6aff, 0, 26, 2);
  blueLight.position.set(0, 3.0, -0.3);
  g.add(blueLight);
  const redLight = new THREE.PointLight(0xff3a2a, 0, 26, 2);
  redLight.position.set(0, 3.0, -0.3);
  g.add(redLight);
  g.userData = { blue, red, blueLight, redLight };
  return g;
}

/** Flashing light bar, shared by every cruiser in the film. */
function strobeCar(car, t) {
  const on = Math.sin(t * 11) > 0;
  car.userData.blue.material.color.setHex(on ? 0x6a9aff : 0x101a3a);
  car.userData.red.material.color.setHex(on ? 0x101a3a : 0xff5a3a);
  car.userData.blueLight.intensity = on ? 3.2 : 0;
  car.userData.redLight.intensity = on ? 0 : 3.2;
}

// ------------------------------------------------------------- the shot list
function buildShotList() {
  return [
    // ---------------------------------------------------------------- ACT I
    {
      stage: 'city', dur: 10, rain: true, fov: 34, fogNear: 40, fogFar: 320,
      text: 'VALMONT  -  02:47',
      from: [-70, 46, 90], to: [-20, 40, 78], lookFrom: [0, 26, -40], lookTo: [0, 22, -40],
      act: (c, u) => { c.stages.city.thief.visible = false; c.spotMuseum.intensity = 2.2 + Math.sin(u * 8) * 0.15; },
    },
    {
      stage: 'city', dur: 9, rain: true, fov: 40, fogNear: 30, fogFar: 260,
      text: 'Musee National. Salle des pierres.\nLe Coeur de Valmont : quarante-deux carats.',
      from: [4, 3, 44], to: [0, 16, 34], lookFrom: [0, 12, -30], lookTo: [0, 18, -30],
      act: (c) => { c.stages.city.thief.visible = false; },
    },
    {
      stage: 'city', dur: 9, rain: true, fov: 44, fogNear: 20, fogFar: 200,
      text: 'Tout le monde disait que le toit etait imprenable.',
      from: [-30, 27, 24], to: [-14, 25, 16], lookFrom: [-16, 23, -38], lookTo: [-12, 23, -38],
      act: (c, u, dt, local) => {
        const t = c.stages.city.thief;
        t.visible = true;
        t.position.set(-16 + u * 10, 22.4, 2 - u * 6);
        t.rotation.y = -0.5;
        walk(t, local * 9);
      },
    },

    // --------------------------------------------------------------- ACT II
    {
      stage: 'vault', dur: 11, fov: 40, bg: 0x05070b, fogNear: 10, fogFar: 90,
      text: 'Trois mois de preparation.\nQuarante secondes d\'execution.',
      from: [10, 11, 20], to: [4, 7, 13], lookFrom: [0, 6, 2], lookTo: [0, 4, 0],
      act: (c, u, dt, local) => {
        const s = c.stages.vault;
        s.thief.visible = true;
        s.thief.position.set(0, 8.5 - u * 6.4, 6);
        s.thief.rotation.y = 0.4 + u * 0.6;
        s.rope.scale.y = 1;
        s.rope.position.y = 8;
        raise(s.thief, 0.9);
        s.laserMat.opacity = 0.35 + Math.sin(local * 3) * 0.1;
        s.diamond.rotation.y += dt * 0.9;
      },
    },
    {
      stage: 'vault', dur: 10, fov: 30, bg: 0x05070b, fogNear: 8, fogFar: 60,
      text: 'Le Coeur etait a moi.',
      from: [3.4, 4.6, 5.4], to: [1.6, 4.3, 3.2], lookFrom: [0, 4.1, 0], lookTo: [0, 4.0, 0],
      act: (c, u, dt) => {
        const s = c.stages.vault;
        s.thief.visible = true;
        s.thief.position.set(1.4, 0, 2.6);
        s.thief.rotation.y = Math.PI + 0.4;
        raise(s.thief, u > 0.35 ? 0.75 : 0.2);
        s.glass.material.opacity = u > 0.35 ? 0.0 : 0.16;
        s.diamond.rotation.y += dt * 2.4;
        s.diamond.position.y = 4.0 + (u > 0.5 ? (u - 0.5) * 1.2 : 0);
        s.diamondGlow.intensity = 2.4 + Math.sin(u * 30) * 1.6;
        if (u > 0.34 && u < 0.36) c._cue('glass', () => c.audio.glassBreak());
      },
    },
    {
      stage: 'vault', dur: 8, fov: 46, bg: 0x120608, fogNear: 8, fogFar: 70, shake: 0.35,
      text: 'Une erreur. Une seule.',
      from: [2, 5, 8], to: [-6, 6, 12], lookFrom: [0, 4, 0], lookTo: [0, 4, 0],
      act: (c, u, dt, local) => {
        const s = c.stages.vault;
        s.thief.visible = true;
        s.thief.position.set(-2 - u * 7, 0, 3 + u * 3);
        s.thief.rotation.y = Math.PI * 0.8;
        walk(s.thief, local * 14);
        const on = Math.sin(local * 12) > 0;
        s.laserMat.color.setHex(0xff2a2a);
        s.laserMat.opacity = on ? 0.7 : 0.25;
        for (const st of s.strobes) st.material.color.setHex(on ? 0xff3020 : 0x2a0a08);
        c.flashLight.position.set(0, 9, -18);
        c.flashLight.intensity = on ? 4.5 : 0.2;
        c._cue('klaxon', () => c.audio.klaxon(6));
      },
    },

    // -------------------------------------------------------------- ACT III
    {
      stage: 'street', dur: 11, rain: true, fov: 52, fogNear: 20, fogFar: 150, shake: 0.12,
      text: 'Ils etaient deja la.',
      from: [2.5, 2.0, -14], to: [2.0, 2.2, 6], lookFrom: [0, 1.4, 10], lookTo: [0, 1.4, 30],
      act: (c, u, dt, local) => {
        const s = c.stages.street;
        // Stays ahead of the dollying camera, running straight at the cordon.
        s.thief.position.set(0.5, 0, 8 + u * 14);
        s.thief.rotation.y = Math.PI;
        walk(s.thief, local * 15);
        s.cars.forEach((car, i) => {
          car.position.z = 60 - u * (34 + i * 5) - i * 6;
          strobeCar(car, local + i);
        });
        c.flashLight.intensity = 0;
        c._cue('engine', () => c.audio.carEngine());
      },
    },
    {
      stage: 'alley', dur: 10, rain: true, fov: 46, fogNear: 12, fogFar: 90,
      text: 'Impasse.',
      from: [0, 3.2, -18], to: [0, 6.5, -26], lookFrom: [0, 2.0, -40], lookTo: [0, 8.0, -44],
      act: (c, u, dt, local) => {
        const s = c.stages.alley;
        s.thief.position.set(0, 0, -28 - u * 8);
        s.thief.rotation.y = 0;
        walk(s.thief, local * 15, 1 - u * 0.7);
        s.cops.forEach((cop) => { cop.visible = false; });
        s.cars.forEach((car) => { car.visible = false; });
        s.beam.material.opacity = 0.03 + u * 0.16;
        s.heliLight.intensity = u * 4.5;
        s.diamond.visible = false;
      },
    },
    {
      stage: 'alley', dur: 10, rain: true, fov: 40, fogNear: 12, fogFar: 90,
      text: '"A GENOUX ! LES MAINS SUR LA TETE !"',
      from: [-5.2, 2.6, -41.5], to: [-4.2, 2.3, -40.2], lookFrom: [0, 1.8, -30], lookTo: [0, 1.6, -28],
      act: (c, u, dt, local) => {
        const s = c.stages.alley;
        s.thief.position.set(0, 0, -37);
        s.thief.rotation.y = Math.PI;
        raise(s.thief, Math.min(1, u * 2.4));
        s.cops.forEach((cop, i) => {
          cop.visible = true;
          cop.position.z = -20 - (i % 2) * 2.5 - u * 8;
          walk(cop, local * 10 + i, 1 - u);
          raise(cop, 0.55);
        });
        s.cars.forEach((car, i) => { car.visible = true; strobeCar(car, local + i * 0.7); });
        s.beam.material.opacity = 0.19;
        s.heliLight.intensity = 4.5;
        c._cue('shout', () => c.audio.guardShout(0));
      },
    },
    {
      stage: 'alley', dur: 8, rain: true, fov: 26, fogNear: 6, fogFar: 60,
      text: 'Quarante-deux carats, sur le bitume mouille.',
      from: [1.4, 1.2, -29.5], to: [0.6, 0.55, -31.0], lookFrom: [0, 0.4, -32], lookTo: [0, 0.35, -32],
      act: (c, u, dt) => {
        const s = c.stages.alley;
        s.diamond.visible = true;
        const bounce = Math.abs(Math.sin(u * 7)) * Math.max(0, 1 - u * 1.6);
        s.diamond.position.set(0, 0.35 + bounce * 1.6, -32 + u * 0.5);
        s.diamond.rotation.set(u * 6, u * 9, u * 3);
        s.dGlow.position.copy(s.diamond.position);
        s.dGlow.intensity = 2.2;
        s.cops.forEach((cop) => { cop.position.z = -22; });
        s.cars.forEach((car, i) => strobeCar(car, u * 8 + i));
        void dt;
      },
    },

    // --------------------------------------------------------------- ACT IV
    {
      stage: 'court', dur: 10, fov: 42, bg: 0x1a130c, fogNear: 20, fogFar: 120,
      text: 'Vol aggrave. Effraction de nuit.\nDouze ans.',
      from: [-8, 4.5, 16], to: [-2, 3.4, 8], lookFrom: [0, 4.0, -13], lookTo: [0, 4.2, -13],
      act: (c, u, dt, local) => {
        const s = c.stages.court;
        s.gavel.position.y = 4.7 + Math.max(0, Math.sin(local * 3.4)) * 1.1;
        s.judge.userData.armR.rotation.x = -0.9 - Math.max(0, Math.sin(local * 3.4)) * 0.8;
        if (u > 0.55 && u < 0.60) c._cue('gavel', () => c.audio.gavel());
        void dt;
      },
    },
    {
      stage: 'prison', dur: 12, fov: 36, bg: 0x2a2438, fogNear: 60, fogFar: 420,
      text: 'PENITENCIER DE BLACKRIDGE\nQuartier de haute securite',
      from: [-26, 12, 120], to: [-6, 9, 40], lookFrom: [0, 12, -34], lookTo: [0, 10, -34],
      act: (c, u, dt, local) => {
        const s = c.stages.prison;
        s.van.position.z = 90 - u * 62;
        void c; void dt; void local;
      },
    },

    // ---------------------------------------------------------------- ACT V
    {
      stage: 'cell', dur: 11, fov: 48, bg: 0x0d1014, fogNear: 14, fogFar: 90,
      text: 'Bloc A. Cellule 1.',
      from: [8, 3.4, 26], to: [-18, 2.6, 6], lookFrom: [-20, 2.6, -6], lookTo: [-26, 2.4, -10],
      act: (c, u, dt, local) => {
        const s = c.stages.cell;
        s.inmate.position.set(-26 + (1 - u) * 14, 0, 8 - u * 14);
        s.inmate.rotation.y = Math.PI * 0.75;
        walk(s.inmate, local * 7, 0.8);
        s.escort.position.set(-24 + (1 - u) * 14, 0, 11 - u * 14);
        s.escort.rotation.y = Math.PI * 0.75;
        walk(s.escort, local * 7 + 1, 0.8);
        s.cellGate.position.x = -19;
        void dt;
      },
    },
    {
      stage: 'cell', dur: 10, fov: 55, bg: 0x0d1014, fogNear: 10, fogFar: 70,
      text: 'Trois metres sur deux. Douze ans.',
      from: [-26, 2.6, -8], to: [-26, 2.5, -11], lookFrom: [-26, 2.4, -18], lookTo: [-26, 3.2, -18],
      act: (c, u, dt) => {
        const s = c.stages.cell;
        s.inmate.visible = false;
        s.escort.visible = false;
        // The gate slides across the camera and slams.
        s.cellGate.position.x = -19 - Math.min(1, u * 1.5) * 7;
        if (u > 0.66 && u < 0.70) c._cue('slam', () => c.audio.slam());
        void dt;
      },
    },
    {
      stage: 'cell', dur: 14, fov: 34, bg: 0x080a0e, fogNear: 8, fogFar: 60,
      text: 'PRISON SCAPE\n\nIls ont pris douze ans de ma vie.\nJe reprends la premiere nuit.',
      from: [-24.6, 2.2, -9.5], to: [-25.4, 3.2, -13.4], lookFrom: [-26, 5.4, -18.4], lookTo: [-26, 6.2, -18.4],
      act: (c, u, dt) => {
        const s = c.stages.cell;
        s.inmate.visible = false;
        s.escort.visible = false;
        s.cellGate.position.x = -26;
        s.moonShaft.material.opacity = 0.05 + Math.sin(u * 3) * 0.02;
        void dt;
      },
    },
  ];
}
