import * as THREE from 'three';
import { makeRNG } from './textures.js';
import { Colliders } from './collision.js';

const GRID = 6;            // blocks per side
const PITCH = 34;          // distance between block centres
const HALF_MAP = (GRID * PITCH) / 2;

/**
 * Builds the single map: "Sector 7 - Ashfall", a burnt-out downtown grid.
 * Returns the scene graph, the collision world, and gameplay anchor points.
 */
export function buildCity(scene, tex, seed = 20260814) {
  const rng = makeRNG(seed);
  const root = new THREE.Group();
  root.name = 'city';
  scene.add(root);

  const colliders = new Colliders(10);

  const mats = {
    asphalt: new THREE.MeshStandardMaterial({ map: tex.asphalt, roughness: 1, metalness: 0 }),
    concrete: new THREE.MeshStandardMaterial({ map: tex.concrete, roughness: 0.95, metalness: 0 }),
    concreteDark: new THREE.MeshStandardMaterial({ map: tex.concreteDark, roughness: 1, metalness: 0 }),
    rubble: new THREE.MeshStandardMaterial({ map: tex.rubble, roughness: 1, metalness: 0 }),
    facadeA: new THREE.MeshStandardMaterial({ map: tex.facadeA, roughness: 0.9, metalness: 0 }),
    facadeB: new THREE.MeshStandardMaterial({ map: tex.facadeB, roughness: 0.9, metalness: 0 }),
    facadeC: new THREE.MeshStandardMaterial({ map: tex.facadeC, roughness: 0.9, metalness: 0 }),
    facadeD: new THREE.MeshStandardMaterial({ map: tex.facadeD, roughness: 0.9, metalness: 0 }),
    roof: new THREE.MeshStandardMaterial({ map: tex.roof, roughness: 1, metalness: 0 }),
    rust: new THREE.MeshStandardMaterial({ map: tex.rust, roughness: 0.85, metalness: 0.35 }),
    rustDark: new THREE.MeshStandardMaterial({ map: tex.rustDark, roughness: 0.9, metalness: 0.3 }),
    glassBroken: new THREE.MeshStandardMaterial({ color: 0x1b2422, roughness: 0.35, metalness: 0.2 }),
  };

  const box = new THREE.BoxGeometry(1, 1, 1);
  const cyl = new THREE.CylinderGeometry(0.5, 0.5, 1, 10);

  /**
   * A box whose UVs are scaled by its real size, so a 6 m wall and a 40 m
   * tower show the same texel density instead of stretching the texture.
   * BoxGeometry lays vertices out per face: +X, -X, +Y, -Y, +Z, -Z.
   */
  function tiledBox(w, h, d, tile) {
    const geo = new THREE.BoxGeometry(w, h, d);
    const uv = geo.attributes.uv;
    const spans = [
      [d, h], [d, h],
      [w, d], [w, d],
      [w, h], [w, h],
    ];
    for (let f = 0; f < 6; f++) {
      const su = spans[f][0] / tile;
      const sv = spans[f][1] / tile;
      for (let i = 0; i < 4; i++) {
        const k = f * 4 + i;
        uv.setXY(k, uv.getX(k) * su, uv.getY(k) * sv);
      }
    }
    uv.needsUpdate = true;
    return geo;
  }

  /** Add a solid box mesh plus its matching collider. */
  function solid(mat, cx, cy, cz, sx, sy, sz, opts = {}) {
    const tile = opts.tile ?? 4;
    const m = new THREE.Mesh(tiledBox(sx, sy, sz, tile), mat);
    m.position.set(cx, cy, cz);
    m.castShadow = opts.castShadow !== false;
    m.receiveShadow = true;
    root.add(m);
    if (opts.collide !== false) {
      colliders.add(
        new THREE.Vector3(cx - sx / 2, cy - sy / 2, cz - sz / 2),
        new THREE.Vector3(cx + sx / 2, cy + sy / 2, cz + sz / 2),
        { tag: opts.tag ?? 'world' }
      );
    }
    return m;
  }

  /**
   * A building block: facade texture on the walls, tar roof on top.
   * The facade tile is 4 windows wide, one window every 3.2 m.
   */
  function buildingBlock(facade, cx, cy, cz, w, h, d, tag = 'building') {
    const geo = tiledBox(w, h, d, 12.8);
    const m = new THREE.Mesh(geo, [facade, facade, mats.roof, mats.concreteDark, facade, facade]);
    m.position.set(cx, cy, cz);
    m.castShadow = true;
    m.receiveShadow = true;
    root.add(m);
    colliders.add(
      new THREE.Vector3(cx - w / 2, cy - h / 2, cz - d / 2),
      new THREE.Vector3(cx + w / 2, cy + h / 2, cz + d / 2),
      { tag }
    );
    return m;
  }

  /** Decorative mesh with a conservative AABB collider around it. */
  function prop(mesh, halfX, halfY, halfZ, collide = true) {
    root.add(mesh);
    if (collide) {
      const p = mesh.position;
      colliders.add(
        new THREE.Vector3(p.x - halfX, p.y - halfY, p.z - halfZ),
        new THREE.Vector3(p.x + halfX, p.y + halfY, p.z + halfZ),
        { tag: 'prop' }
      );
    }
    return mesh;
  }

  // ---------------------------------------------------------------- ground
  {
    const size = GRID * PITCH + 60;
    const g = new THREE.PlaneGeometry(size, size, 1, 1);
    const groundTex = tex.asphalt.clone();
    groundTex.needsUpdate = true;
    groundTex.repeat.set(size / 10, size / 10);
    const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ map: groundTex, roughness: 1, metalness: 0 }));
    m.rotation.x = -Math.PI / 2;
    m.receiveShadow = true;
    root.add(m);
    // an invisible floor collider so nothing can fall through
    colliders.add(
      new THREE.Vector3(-size / 2, -2, -size / 2),
      new THREE.Vector3(size / 2, 0, size / 2),
      { tag: 'ground' }
    );
  }

  // --------------------------------------------------------------- kerbs
  for (let i = 0; i <= GRID; i++) {
    const p = -HALF_MAP + i * PITCH;
    // thin raised kerbs marking the street edges (walk-over height)
    for (const side of [-1, 1]) {
      const off = side * (PITCH * 0.5 - 5.4);
      solid(mats.concreteDark, 0, 0.07, p + off, GRID * PITCH, 0.14, 0.5, { collide: false, castShadow: false });
      solid(mats.concreteDark, p + off, 0.07, 0, 0.5, 0.14, GRID * PITCH, { collide: false, castShadow: false });
    }
  }

  // ------------------------------------------- faded road markings
  {
    const L = GRID * PITCH + 20;
    const lineMat = new THREE.MeshBasicMaterial({
      map: tex.roadLine, transparent: true, depthWrite: false, fog: true,
    });
    for (let i = 0; i <= GRID; i++) {
      const p = -HALF_MAP + i * PITCH;
      for (const axis of ['x', 'z']) {
        const m = new THREE.Mesh(new THREE.PlaneGeometry(0.7, L), lineMat);
        m.rotation.x = -Math.PI / 2;
        m.position.y = 0.02;
        if (axis === 'x') {
          m.position.set(p, 0.02, 0);
        } else {
          m.position.set(0, 0.02, p);
          m.rotation.z = Math.PI / 2;
        }
        m.renderOrder = 1;
        root.add(m);
      }
    }
    tex.roadLine.repeat.set(1, L / 9);
  }

  // ------------------------------------------------------------- buildings
  const facades = [mats.facadeA, mats.facadeB, mats.facadeC, mats.facadeD];
  const blockInfo = [];
  // Small non-blocking debris chunks, collected here and drawn later as one
  // instanced mesh. Declared before the generators that push into it.
  const debrisTransforms = [];

  for (let gx = 0; gx < GRID; gx++) {
    for (let gz = 0; gz < GRID; gz++) {
      const cx = -HALF_MAP + PITCH * (gx + 0.5);
      const cz = -HALF_MAP + PITCH * (gz + 0.5);
      const isStart = gx === 2 && gz === 5; // player spawns in this plaza
      const roll = rng();
      let type;
      if (isStart) type = 'plaza';
      else if (roll < 0.40) type = 'tower';
      else if (roll < 0.68) type = 'ruin';
      else if (roll < 0.86) type = 'rubble';
      else type = 'plaza';

      blockInfo.push({ cx, cz, type });

      if (type === 'tower') buildTower(cx, cz);
      else if (type === 'ruin') buildRuin(cx, cz);
      else if (type === 'rubble') buildRubbleLot(cx, cz);
      else buildPlaza(cx, cz, isStart);
    }
  }

  function buildTower(cx, cz) {
    const facade = facades[(rng() * facades.length) | 0];
    const w = 14 + rng() * 8;
    const d = 14 + rng() * 8;
    const h = 16 + rng() * 20;
    buildingBlock(facade, cx, h / 2, cz, w, h, d);
    // parapet running around the roof edge
    solid(mats.concreteDark, cx, h + 0.45, cz, w + 0.8, 0.9, d + 0.8, { tag: 'building', tile: 3 });

    // setback upper section, sheared off on one side
    if (rng() < 0.7) {
      const w2 = w * (0.45 + rng() * 0.3);
      const d2 = d * (0.45 + rng() * 0.3);
      const h2 = 4 + rng() * 12;
      const ox = (rng() - 0.5) * (w - w2) * 0.7;
      const oz = (rng() - 0.5) * (d - d2) * 0.7;
      buildingBlock(facade, cx + ox, h + h2 / 2, cz + oz, w2, h2, d2);
    }
    // rooftop clutter: water tank, vents, a leaning aerial
    if (rng() < 0.55) {
      const tank = new THREE.Mesh(cyl, mats.rustDark);
      tank.position.set(cx + (rng() - 0.5) * w * 0.5, h + 2.2, cz + (rng() - 0.5) * d * 0.5);
      tank.scale.set(3, 3.4, 3);
      tank.castShadow = true;
      root.add(tank);
    }
    for (let i = 0; i < 3; i++) {
      if (rng() > 0.6) continue;
      solid(mats.rustDark, cx + (rng() - 0.5) * w * 0.6, h + 0.9, cz + (rng() - 0.5) * d * 0.6,
        1 + rng(), 1.4, 1 + rng(), { collide: false, tile: 2 });
    }
    // blast hole at street level, faked with a dark recess and rubble spill
    if (rng() < 0.55) {
      const side = (rng() * 4) | 0;
      const ang = (side * Math.PI) / 2;
      const px = cx + Math.sin(ang) * (d / 2 + 0.2);
      const pz = cz + Math.cos(ang) * (w / 2 + 0.2);
      const hole = new THREE.Mesh(box, mats.concreteDark);
      hole.position.set(px, 2, pz);
      hole.scale.set(4, 4, 4);
      // no collider: it sits inside the building volume already
      root.add(hole);
      spillRubble(cx + (px - cx) * 1.25, cz + (pz - cz) * 1.25, 3);
    }
    scatterDebris(cx, cz, 16, 5);
  }

  function buildRuin(cx, cz) {
    const facade = facades[(rng() * facades.length) | 0];
    const parts = 2 + ((rng() * 3) | 0);
    for (let i = 0; i < parts; i++) {
      const w = 6 + rng() * 10;
      const d = 6 + rng() * 10;
      const h = 3 + rng() * 9;
      const ox = (rng() - 0.5) * 12;
      const oz = (rng() - 0.5) * 12;
      if (rng() < 0.65) buildingBlock(facade, cx + ox, h / 2, cz + oz, w, h, d);
      else solid(mats.concrete, cx + ox, h / 2, cz + oz, w, h, d, { tag: 'building' });
    }
    // leaning slab against the shell
    if (rng() < 0.8) {
      const slab = new THREE.Mesh(box, mats.rubble);
      slab.position.set(cx + (rng() - 0.5) * 14, 2.4, cz + (rng() - 0.5) * 14);
      slab.scale.set(6 + rng() * 4, 0.5, 4 + rng() * 3);
      slab.rotation.set((rng() - 0.5) * 0.5, rng() * Math.PI, 0.5 + rng() * 0.5);
      slab.castShadow = true;
      slab.receiveShadow = true;
      root.add(slab);
    }
    scatterDebris(cx, cz, 15, 8);
  }

  function buildRubbleLot(cx, cz) {
    // a collapsed block: knee-high mounds you can walk over, plus tall spikes of wall
    for (let i = 0; i < 7; i++) {
      const w = 3 + rng() * 7;
      const d = 3 + rng() * 7;
      const h = 0.4 + rng() * 1.1;
      solid(mats.rubble, cx + (rng() - 0.5) * 20, h / 2, cz + (rng() - 0.5) * 20, w, h, d, { tag: 'rubble' });
    }
    const spikes = 1 + ((rng() * 3) | 0);
    for (let i = 0; i < spikes; i++) {
      const h = 4 + rng() * 7;
      solid(mats.concrete, cx + (rng() - 0.5) * 16, h / 2, cz + (rng() - 0.5) * 16, 1 + rng() * 4, h, 0.8 + rng() * 2, { tag: 'building' });
    }
    scatterDebris(cx, cz, 18, 14);
  }

  function buildPlaza(cx, cz, isStart) {
    // open square: low cover, barrels, a burnt car or two
    const covers = isStart ? 3 : 4 + ((rng() * 3) | 0);
    for (let i = 0; i < covers; i++) {
      const ang = rng() * Math.PI * 2;
      const r = 5 + rng() * 10;
      const px = cx + Math.cos(ang) * r;
      const pz = cz + Math.sin(ang) * r;
      const pick = rng();
      if (pick < 0.4) barrier(px, pz, rng() * Math.PI);
      else if (pick < 0.7) sandbags(px, pz, rng() * Math.PI);
      else barrel(px, pz);
    }
    if (!isStart && rng() < 0.6) wreckedCar(cx + (rng() - 0.5) * 12, cz + (rng() - 0.5) * 12, rng() * Math.PI * 2);
    scatterDebris(cx, cz, 16, 8);
  }

  // ------------------------------------------------------------- props
  function barrel(x, z) {
    const m = new THREE.Mesh(cyl, rng() < 0.5 ? mats.rust : mats.rustDark);
    m.position.set(x, 0.55, z);
    m.scale.set(0.78, 1.1, 0.78);
    m.rotation.y = rng() * Math.PI;
    m.castShadow = true;
    m.receiveShadow = true;
    return prop(m, 0.42, 0.55, 0.42);
  }

  function barrier(x, z, ry) {
    const m = new THREE.Mesh(tiledBox(2.6, 1.1, 0.7, 2), mats.concreteDark);
    m.position.set(x, 0.55, z);
    m.rotation.y = ry;
    m.castShadow = true;
    m.receiveShadow = true;
    root.add(m);
    const s = Math.abs(Math.sin(ry)), c = Math.abs(Math.cos(ry));
    colliders.add(
      new THREE.Vector3(x - (1.3 * c + 0.35 * s), 0, z - (1.3 * s + 0.35 * c)),
      new THREE.Vector3(x + (1.3 * c + 0.35 * s), 1.1, z + (1.3 * s + 0.35 * c)),
      { tag: 'prop' }
    );
    return m;
  }

  function sandbags(x, z, ry) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    g.rotation.y = ry;
    const bagMat = new THREE.MeshStandardMaterial({ color: 0x6a6247, roughness: 1 });
    for (let row = 0; row < 3; row++) {
      const n = 5 - row;
      for (let i = 0; i < n; i++) {
        const b = new THREE.Mesh(box, bagMat);
        b.position.set((i - (n - 1) / 2) * 0.62, 0.16 + row * 0.3, (row % 2) * 0.06);
        b.scale.set(0.6, 0.3, 0.42);
        b.rotation.y = (rng() - 0.5) * 0.25;
        b.castShadow = true;
        b.receiveShadow = true;
        g.add(b);
      }
    }
    root.add(g);
    const s = Math.abs(Math.sin(ry)), c = Math.abs(Math.cos(ry));
    colliders.add(
      new THREE.Vector3(x - (1.6 * c + 0.3 * s), 0, z - (1.6 * s + 0.3 * c)),
      new THREE.Vector3(x + (1.6 * c + 0.3 * s), 0.95, z + (1.6 * s + 0.3 * c)),
      { tag: 'prop' }
    );
    return g;
  }

  function wreckedCar(x, z, ry) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    g.rotation.y = ry;
    const bodyMat = rng() < 0.5 ? mats.rust : mats.rustDark;

    const body = new THREE.Mesh(tiledBox(4.3, 0.75, 1.85, 1.6), bodyMat);
    body.position.y = 0.62;
    g.add(body);

    // sills and a crumpled roof line
    const sill = new THREE.Mesh(tiledBox(4.34, 0.14, 1.9, 1.6), mats.rustDark);
    sill.position.y = 0.3;
    g.add(sill);

    const cabin = new THREE.Mesh(tiledBox(2.1, 0.72, 1.66, 1.6), mats.glassBroken);
    cabin.position.set(-0.25, 1.22, 0);
    g.add(cabin);

    const roof = new THREE.Mesh(tiledBox(2.0, 0.12, 1.6, 1.6), bodyMat);
    roof.position.set(-0.3, 1.58, 0);
    roof.rotation.z = (rng() - 0.5) * 0.16;
    g.add(roof);

    const hood = new THREE.Mesh(tiledBox(1.3, 0.18, 1.7, 1.6), bodyMat);
    hood.position.set(1.5, 1.02, 0);
    hood.rotation.z = -0.12;
    g.add(hood);

    for (const [wx, wz] of [[1.4, 0.92], [1.4, -0.92], [-1.4, 0.92], [-1.4, -0.92]]) {
      if (rng() < 0.22) continue; // some wheels are gone
      const w = new THREE.Mesh(cyl, new THREE.MeshStandardMaterial({ color: 0x14120f, roughness: 1 }));
      w.position.set(wx, 0.34, wz);
      w.scale.set(0.68, 0.3, 0.68);
      w.rotation.x = Math.PI / 2;
      g.add(w);
    }
    g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    root.add(g);

    const s = Math.abs(Math.sin(ry)), c = Math.abs(Math.cos(ry));
    const hx = 2.15 * c + 0.95 * s;
    const hz = 2.15 * s + 0.95 * c;
    colliders.add(
      new THREE.Vector3(x - hx, 0, z - hz),
      new THREE.Vector3(x + hx, 1.55, z + hz),
      { tag: 'prop' }
    );
    return g;
  }

  function lamppost(x, z) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    const lean = (rng() - 0.5) * 0.5;
    g.rotation.z = lean;
    const pole = new THREE.Mesh(cyl, mats.rustDark);
    pole.position.y = 3.2;
    pole.scale.set(0.22, 6.4, 0.22);
    g.add(pole);
    const arm = new THREE.Mesh(box, mats.rustDark);
    arm.position.set(0.9, 6.2, 0);
    arm.scale.set(1.9, 0.16, 0.16);
    g.add(arm);
    const head = new THREE.Mesh(box, mats.rustDark);
    head.position.set(1.75, 6.05, 0);
    head.scale.set(0.7, 0.25, 0.4);
    g.add(head);
    g.traverse((o) => { if (o.isMesh) { o.castShadow = true; } });
    root.add(g);
    colliders.add(
      new THREE.Vector3(x - 0.25, 0, z - 0.25),
      new THREE.Vector3(x + 0.25, 6.4, z + 0.25),
      { tag: 'prop' }
    );
    return g;
  }

  function spillRubble(x, z, n) {
    for (let i = 0; i < n; i++) {
      const w = 1.5 + rng() * 3;
      const h = 0.3 + rng() * 0.7;
      solid(mats.rubble, x + (rng() - 0.5) * 5, h / 2, z + (rng() - 0.5) * 5, w, h, w * (0.6 + rng() * 0.7), { tag: 'rubble' });
    }
  }

  function scatterDebris(cx, cz, radius, count) {
    for (let i = 0; i < count; i++) {
      debrisTransforms.push({
        x: cx + (rng() - 0.5) * radius * 2,
        z: cz + (rng() - 0.5) * radius * 2,
        s: 0.15 + rng() * 0.5,
        ry: rng() * Math.PI,
        rx: (rng() - 0.5) * 0.6,
        flat: 0.25 + rng() * 0.6,
      });
    }
  }

  // ------------------------------------------------- streets: wrecks + poles
  for (let i = 0; i <= GRID; i++) {
    const line = -HALF_MAP + i * PITCH;
    for (let j = 0; j < GRID; j++) {
      const along = -HALF_MAP + PITCH * (j + 0.5) + (rng() - 0.5) * 10;
      if (rng() < 0.5) wreckedCar(along, line + (rng() - 0.5) * 3, (rng() < 0.5 ? 0 : Math.PI / 2) + (rng() - 0.5) * 0.5);
      if (rng() < 0.5) wreckedCar(line + (rng() - 0.5) * 3, along, (rng() < 0.5 ? 0 : Math.PI / 2) + (rng() - 0.5) * 0.5);
      if (rng() < 0.35) barrier(along, line + (rng() - 0.5) * 4, rng() * Math.PI);
      if (rng() < 0.35) barrel(line + (rng() - 0.5) * 4, along);
    }
    for (let j = 0; j <= GRID; j++) {
      const cross = -HALF_MAP + j * PITCH;
      if (rng() < 0.45) lamppost(line + 3.4, cross + 3.4);
    }
    scatterDebris(line, 0, 3, 10);
    scatterDebris(0, line, 3, 10);
  }

  // ------------------------------------------------ landmark: fallen overpass
  {
    const z = -HALF_MAP + PITCH * 2;
    for (let i = 0; i < 5; i++) {
      const x = -HALF_MAP + 8 + i * 22;
      const h = 7.5;
      // support pillars
      solid(mats.concreteDark, x, h / 2, z, 2.2, h, 2.2, { tag: 'building' });
      if (i < 4) {
        const collapsed = i === 2;
        const deck = new THREE.Mesh(box, mats.concreteDark);
        if (collapsed) {
          deck.position.set(x + 11, 3.4, z);
          deck.rotation.z = 0.55;
          deck.scale.set(22, 0.8, 9);
          root.add(deck);
          deck.castShadow = true;
          deck.receiveShadow = true;
          colliders.add(new THREE.Vector3(x + 2, 0, z - 4.5), new THREE.Vector3(x + 20, 2.2, z + 4.5), { tag: 'rubble' });
          spillRubble(x + 11, z + 6, 4);
        } else {
          solid(mats.concreteDark, x + 11, h + 0.4, z, 22, 0.8, 9, { tag: 'building' });
          // guard rails
          for (const s of [-1, 1]) {
            solid(mats.rustDark, x + 11, h + 1.3, z + s * 4.3, 22, 1, 0.25, { tag: 'building' });
          }
        }
      }
    }
  }

  // --------------------------------------------------- landmark: radio mast
  {
    const x = HALF_MAP - 18, z = HALF_MAP - 18;
    for (let i = 0; i < 6; i++) {
      const y = i * 6;
      const w = 3.2 - i * 0.4;
      solid(mats.rustDark, x, y + 3, z, w, 0.35, w, { collide: i === 0, tag: 'building', castShadow: true });
      for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
        const leg = new THREE.Mesh(box, mats.rustDark);
        leg.position.set(x + sx * w * 0.45, y + 3, z + sz * w * 0.45);
        leg.scale.set(0.22, 6, 0.22);
        leg.castShadow = true;
        root.add(leg);
      }
    }
    colliders.add(new THREE.Vector3(x - 1.8, 0, z - 1.8), new THREE.Vector3(x + 1.8, 36, z + 1.8), { tag: 'building' });
  }

  // ------------------------------------------------------- perimeter wall
  {
    const L = GRID * PITCH + 12;
    const H = 14;
    const T = 4;
    const edge = HALF_MAP + 5;
    // Big tile: at 216 m long a 4 m tile turns the soot streaks into a barcode.
    const wall = { tag: 'wall', tile: 11 };
    solid(mats.rubble, 0, H / 2, -edge, L, H, T, wall);
    solid(mats.rubble, 0, H / 2, edge, L, H, T, wall);
    solid(mats.rubble, -edge, H / 2, 0, T, H, L, wall);
    solid(mats.rubble, edge, H / 2, 0, T, H, L, wall);
    // ragged silhouette on top of the barricade
    for (let i = 0; i < 90; i++) {
      const side = (rng() * 4) | 0;
      const t = (rng() - 0.5) * L;
      const h = 1 + rng() * 4;
      const w = 1.5 + rng() * 4;
      let px, pz;
      if (side === 0) { px = t; pz = -edge + (rng() - 0.5) * 2; }
      else if (side === 1) { px = t; pz = edge + (rng() - 0.5) * 2; }
      else if (side === 2) { px = -edge + (rng() - 0.5) * 2; pz = t; }
      else { px = edge + (rng() - 0.5) * 2; pz = t; }
      const m = new THREE.Mesh(box, mats.rubble);
      m.position.set(px, H + h / 2 - 0.5, pz);
      m.scale.set(w, h, w);
      m.rotation.y = rng() * Math.PI;
      m.castShadow = true;
      root.add(m);
    }
  }

  // ------------------------------------------------------- instanced debris
  {
    const geo = new THREE.BoxGeometry(1, 1, 1);
    const mat = new THREE.MeshStandardMaterial({ map: tex.rubble, roughness: 1 });
    const inst = new THREE.InstancedMesh(geo, mat, debrisTransforms.length);
    inst.castShadow = true;
    inst.receiveShadow = true;
    const dummy = new THREE.Object3D();
    debrisTransforms.forEach((d, i) => {
      dummy.position.set(d.x, d.s * d.flat * 0.5, d.z);
      dummy.rotation.set(d.rx, d.ry, d.rx * 0.5);
      dummy.scale.set(d.s, d.s * d.flat, d.s * (0.7 + 0.6 * d.flat));
      dummy.updateMatrix();
      inst.setMatrixAt(i, dummy.matrix);
    });
    inst.instanceMatrix.needsUpdate = true;
    root.add(inst);
  }

  // ----------------------------------------------------------- spawn points
  const spawnPoints = [];
  const playerStart = new THREE.Vector3(-HALF_MAP + PITCH * 2.5, 0, -HALF_MAP + PITCH * 5.5);
  {
    const step = 5;
    for (let x = -HALF_MAP + 6; x <= HALF_MAP - 6; x += step) {
      for (let z = -HALF_MAP + 6; z <= HALF_MAP - 6; z += step) {
        // needs to be free for a standing body
        if (colliders.overlaps(x, 1.0, z, 0.6, 0.95, 0.6)) continue;
        spawnPoints.push(new THREE.Vector3(x, 0, z));
      }
    }
  }
  // Guarantee the player's own spot is clear.
  if (colliders.overlaps(playerStart.x, 1.0, playerStart.z, 0.6, 0.95, 0.6)) {
    const alt = spawnPoints.reduce((best, p) =>
      p.distanceToSquared(playerStart) < best.distanceToSquared(playerStart) ? p : best, spawnPoints[0]);
    playerStart.copy(alt);
  }

  return { root, colliders, spawnPoints, playerStart, mats, bounds: HALF_MAP };
}

/** Direction the sun sits in, shared by the sky shader and the key light. */
export const SUN_DIR = new THREE.Vector3(0.52, 0.23, -0.82).normalize();

/**
 * Sky dome, sun, fog and lighting for a permanent dust-storm dusk.
 * The dome is one shader: layered fbm dust, a real sun disc with a scattering
 * halo, and a thick haze band packed against the horizon.
 */
export function buildSky(scene, renderer) {
  // Late-afternoon haze: warm, but light enough that distance reads blue
  // rather than brown.
  const fogColor = new THREE.Color(0xa4977f);
  scene.fog = new THREE.FogExp2(fogColor, 0.0072);
  scene.background = fogColor;

  // Radius stays inside the camera far plane so the dome is never clipped, and
  // wider than the horizon backdrop so that stays in front of it. Drawn last
  // with depth testing on, so covered pixels never run the (costly) shader.
  const skyGeo = new THREE.SphereGeometry(450, 32, 20);
  const skyMat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
    uniforms: {
      // Sunset ramp: deep blue overhead, steel blue at altitude, then warm
      // ochre and bright orange packed into the last few degrees of sky.
      uZenith: { value: new THREE.Color(0x2e5285) },
      uHigh: { value: new THREE.Color(0x5f7ba6) },
      uMid: { value: new THREE.Color(0xc78d5e) },
      uHorizon: { value: new THREE.Color(0xffb87a) },
      uGround: { value: new THREE.Color(0x8a7a63) },
      uSunColor: { value: new THREE.Color(0xfff0cf) },
      uSunDir: { value: SUN_DIR.clone() },
      uTime: { value: 0 },
    },
    vertexShader: /* glsl */ `
      varying vec3 vDir;
      void main() {
        vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec3 vDir;
      uniform vec3 uZenith, uHigh, uMid, uHorizon, uGround, uSunColor, uSunDir;
      uniform float uTime;

      float hash(vec3 p) {
        p = fract(p * 0.3183099 + vec3(0.1, 0.2, 0.3));
        p *= 17.0;
        return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
      }
      float noise(vec3 x) {
        vec3 i = floor(x);
        vec3 f = fract(x);
        f = f * f * (3.0 - 2.0 * f);
        return mix(
          mix(mix(hash(i + vec3(0.0,0.0,0.0)), hash(i + vec3(1.0,0.0,0.0)), f.x),
              mix(hash(i + vec3(0.0,1.0,0.0)), hash(i + vec3(1.0,1.0,0.0)), f.x), f.y),
          mix(mix(hash(i + vec3(0.0,0.0,1.0)), hash(i + vec3(1.0,0.0,1.0)), f.x),
              mix(hash(i + vec3(0.0,1.0,1.0)), hash(i + vec3(1.0,1.0,1.0)), f.x), f.y), f.z);
      }
      float fbm3(vec3 p) {
        float v = 0.0;
        float a = 0.5;
        for (int i = 0; i < 3; i++) {
          v += a * noise(p);
          p *= 2.03;
          a *= 0.5;
        }
        return v;
      }

      void main() {
        vec3 dir = normalize(vDir);
        float h = dir.y;
        float sunAmt = max(dot(dir, normalize(uSunDir)), 0.0);

        // base vertical gradient
        vec3 col = mix(uHorizon, uMid, smoothstep(0.0, 0.16, h));
        col = mix(col, uHigh, smoothstep(0.14, 0.42, h));
        col = mix(col, uZenith, smoothstep(0.40, 0.92, h));
        col = mix(col, uGround, smoothstep(0.0, -0.16, h));

        // warm scattering around the sun
        col += uSunColor * pow(sunAmt, 5.0) * 0.50;
        col += vec3(1.0, 0.46, 0.16) * pow(sunAmt, 1.6) * 0.28;

        // drifting dust layers, only worth evaluating above the horizon
        float density = 0.0;
        float band = smoothstep(-0.02, 0.22, h);
        if (band > 0.001) {
          vec3 p = dir * (2.4 / max(abs(h) + 0.14, 0.14));
          p.x += uTime * 0.010;
          p.z += uTime * 0.006;
          float clouds = fbm3(p * 1.5);
          float wisps = noise(p * 4.5 + vec3(uTime * 0.02, 0.0, 0.0));
          density = smoothstep(0.40, 0.80, clouds * 0.80 + wisps * 0.30);
          density *= band;
          density *= 1.0 - smoothstep(0.55, 1.0, h) * 0.55;
          // dust in shadow keeps a blue cast, dust near the sun goes hot
          vec3 dustLit = mix(vec3(0.34, 0.39, 0.53), uSunColor * 1.02, pow(sunAmt, 1.7));
          col = mix(col, dustLit, density * 0.55);
        }

        // the sun disc itself
        float disc = smoothstep(0.99920, 0.99975, sunAmt);
        float bloom = pow(sunAmt, 220.0);
        col += uSunColor * (disc * 2.4 + bloom * 1.1) * (1.0 - density * 0.85);

        // heavy haze on the horizon line
        float haze = exp(-abs(h) * 13.0);
        col = mix(col, uHorizon * 1.03, haze * 0.46);

        // grain, so the gradient does not band
        col += (hash(dir * 900.0) - 0.5) * 0.012;

        gl_FragColor = vec4(col, 1.0);
      }
    `,
  });
  const sky = new THREE.Mesh(skyGeo, skyMat);
  sky.frustumCulled = false;
  sky.renderOrder = 999;
  scene.add(sky);

  // Blue sky bounce against a warm low sun: that contrast is what sells dusk.
  const hemi = new THREE.HemisphereLight(0x9fbde4, 0x6a5c48, 2.1);
  scene.add(hemi);

  const sun = new THREE.DirectionalLight(0xffd2a0, 3.1);
  sun.position.copy(SUN_DIR).multiplyScalar(90);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 240;
  sun.shadow.camera.left = -58;
  sun.shadow.camera.right = 58;
  sun.shadow.camera.top = 58;
  sun.shadow.camera.bottom = -58;
  sun.shadow.bias = -0.0008;
  sun.shadow.normalBias = 0.04;
  scene.add(sun);
  scene.add(sun.target);

  // cool bounce from the opposite side so shadowed faces are not dead black
  const fill = new THREE.DirectionalLight(0x93b6ee, 1.05);
  fill.position.set(-60, 34, 66);
  scene.add(fill);

  return {
    sky, sun, hemi, fill, fogColor,
    update(dt) { skyMat.uniforms.uTime.value += dt; },
  };
}

/**
 * The rest of the city, far beyond the barricade: tower silhouettes fading
 * into the haze and columns of smoke still burning out there. Purely visual.
 */
export function buildHorizon(scene, tex, seed = 99) {
  const rng = makeRNG(seed);
  const group = new THREE.Group();
  group.name = 'horizon';
  scene.add(group);

  const geo = new THREE.BoxGeometry(1, 1, 1);
  // Fog is off here and the haze is baked into the colour instead: these are a
  // painted backdrop, so aerial perspective is faked by the further ring being
  // lighter and closer to the sky.
  const near = new THREE.MeshBasicMaterial({ color: 0x545b6b, fog: false });
  const far = new THREE.MeshBasicMaterial({ color: 0x6e7688, fog: false });
  const count = 120;
  const dummy = new THREE.Object3D();

  const ringA = new THREE.InstancedMesh(geo, near, count);
  const ringB = new THREE.InstancedMesh(geo, far, count);
  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2 + rng() * 0.06;
    const r = 150 + rng() * 45;
    const h = 24 + rng() * 60;
    dummy.position.set(Math.cos(a) * r, h / 2 - 5, Math.sin(a) * r);
    dummy.rotation.set(0, a + (rng() - 0.5) * 0.7, 0);
    dummy.scale.set(12 + rng() * 22, h, 12 + rng() * 20);
    dummy.updateMatrix();
    ringA.setMatrixAt(i, dummy.matrix);

    const a2 = (i / count) * Math.PI * 2 + rng() * 0.25;
    const r2 = 235 + rng() * 95;
    const h2 = 34 + rng() * 92;
    dummy.position.set(Math.cos(a2) * r2, h2 / 2 - 8, Math.sin(a2) * r2);
    dummy.rotation.set(0, a2, 0);
    dummy.scale.set(18 + rng() * 32, h2, 18 + rng() * 30);
    dummy.updateMatrix();
    ringB.setMatrixAt(i, dummy.matrix);
  }
  ringA.instanceMatrix.needsUpdate = true;
  ringB.instanceMatrix.needsUpdate = true;
  ringA.frustumCulled = false;
  ringB.frustumCulled = false;
  group.add(ringB);
  group.add(ringA);

  // --- smoke columns still burning somewhere out there ---
  const plumes = [];
  const spots = [
    { x: -120, z: -150, s: 1.0 },
    { x: 175, z: -95, s: 1.35 },
    { x: 45, z: 200, s: 0.85 },
    { x: -190, z: 75, s: 1.1 },
  ];
  for (const spot of spots) {
    for (let i = 0; i < 12; i++) {
      const m = new THREE.SpriteMaterial({
        map: tex.smoke,
        color: 0x2e261e,
        transparent: true,
        opacity: 0.45,
        depthWrite: false,
        fog: false,
      });
      const sp = new THREE.Sprite(m);
      sp.renderOrder = -1;
      group.add(sp);
      plumes.push({ sprite: sp, t: i / 12, speed: 0.7 + rng() * 0.5, drift: (rng() - 0.5) * 0.6, spot });
    }
  }

  const tick = (dt) => {
    for (const p of plumes) {
      p.t += dt * 0.013 * p.speed;
      if (p.t > 1) p.t -= 1;
      const y = p.t * 95;
      const size = (16 + p.t * 60) * p.spot.s;
      p.sprite.position.set(p.spot.x + p.drift * y * 0.4, y, p.spot.z);
      p.sprite.scale.set(size, size, 1);
      p.sprite.material.opacity = 0.5 * Math.min(1, p.t * 6) * (1 - p.t * 0.6);
    }
  };
  tick(0);

  return { group, update: tick };
}

/** Ash and embers drifting past the camera, recycled in a box around it. */
export class AshField {
  constructor(scene, tex, count = 900, extent = 60) {
    this.count = count;
    this.extent = extent;
    this.positions = new Float32Array(count * 3);
    this.speeds = new Float32Array(count);
    this.phase = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      this.positions[i * 3] = (Math.random() - 0.5) * extent * 2;
      this.positions[i * 3 + 1] = Math.random() * 26;
      this.positions[i * 3 + 2] = (Math.random() - 0.5) * extent * 2;
      this.speeds[i] = 0.3 + Math.random() * 0.9;
      this.phase[i] = Math.random() * Math.PI * 2;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.positions, 3));
    const mat = new THREE.PointsMaterial({
      map: tex.ash,
      color: 0xbdb09b,
      size: 0.085,
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
      sizeAttenuation: true,
      fog: true,
    });
    this.points = new THREE.Points(geo, mat);
    this.points.frustumCulled = false;
    scene.add(this.points);
    this.geo = geo;
    this.t = 0;
  }

  update(dt, camera) {
    this.t += dt;
    const cx = camera.position.x;
    const cz = camera.position.z;
    const e = this.extent;
    const p = this.positions;
    for (let i = 0; i < this.count; i++) {
      const i3 = i * 3;
      p[i3 + 1] -= this.speeds[i] * dt;
      p[i3] += Math.sin(this.t * 0.5 + this.phase[i]) * 0.35 * dt + 0.55 * dt;
      if (p[i3 + 1] < -1) {
        p[i3 + 1] = 26;
        p[i3] = cx + (Math.random() - 0.5) * e * 2;
        p[i3 + 2] = cz + (Math.random() - 0.5) * e * 2;
      }
      // wrap horizontally so the field always surrounds the player
      if (p[i3] - cx > e) p[i3] -= e * 2;
      else if (p[i3] - cx < -e) p[i3] += e * 2;
      if (p[i3 + 2] - cz > e) p[i3 + 2] -= e * 2;
      else if (p[i3 + 2] - cz < -e) p[i3 + 2] += e * 2;
    }
    this.geo.attributes.position.needsUpdate = true;
  }
}
