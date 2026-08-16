/**
 * Procedural city.
 *
 * Consumes a RoadNetwork and emits a handful of merged meshes (one per material) plus
 * static physics colliders.
 *
 * Variety comes from four independent axes, which is what stops a procedural grid from
 * reading as copy-paste:
 *   1. district        - radial zoning sets the *mix* of what can appear
 *   2. lot programme   - not every lot is a building; some are car parks, vacant plots,
 *                        construction sites, plazas or pocket parks
 *   3. archetype       - the chosen building shape (tower, podium+tower, walk-up,
 *                        stucco block, shophouse, house, warehouse), each with its own
 *                        silhouette rules
 *   4. per-instance    - height drawn from a heavy-tailed distribution, facade colour
 *                        drawn from a district palette and written into the vertex
 *                        colour stream, UV offset jittered so no two facades line up
 *
 * Because the tint lives in vertex colours, all of that variety still costs one draw
 * call per material.
 */

import { Mesh, Group, Vector3, Box3, Color } from 'three/webgpu';
import { GeometryBuilder } from './GeometryBuilder.js';
import { RoadNetwork, ROAD, PAVEMENT_WIDTH } from './RoadNetwork.js';
import { getMaterial, getFlat } from '../render/Materials.js';
import { GROUP } from '../physics/Physics.js';
import { makeRng } from '../core/Noise.js';

export const DISTRICT = {
  DOWNTOWN: 'downtown',
  MIDTOWN: 'midtown',
  RESIDENTIAL: 'residential',
  INDUSTRIAL: 'industrial',
};

// Single source of truth lives in RoadNetwork, where the lane maths needs it too.
const SIDEWALK_WIDTH = PAVEMENT_WIDTH;
const SIDEWALK_HEIGHT = 0.17;

/** Facade palettes per district. Muted, slightly desaturated - reads as a real city. */
const PALETTE = {
  [DISTRICT.DOWNTOWN]: {
    glass: [0x93a8bd, 0x7f9bb2, 0xa8b6bd, 0x6e8799, 0x8fa39b, 0xb0b6ba, 0x5f7488],
    solid: [0xa8a49c, 0x928d86, 0xb5b0a6, 0x7d7a75, 0xc0b8ab],
  },
  [DISTRICT.MIDTOWN]: {
    brick: [0x9c5842, 0x8a4a38, 0xb0705a, 0x77463a, 0xa35f45, 0x6d3f33, 0xbd8a6b],
    solid: [0xbdb4a4, 0xa79d8d, 0xd0c7b4, 0x8e857a, 0xc9b79a, 0x9fa8a4],
  },
  [DISTRICT.RESIDENTIAL]: {
    brick: [0xa8604a, 0x8f5340, 0xbd7c62, 0x94533f],
    solid: [0xd8cfbc, 0xe3dccb, 0xc4c9c0, 0xd9c9a8, 0xbfc7cf, 0xe6d9c2, 0xcbb9a6],
    roof: [0x6b4a3c, 0x4f4642, 0x7a5140, 0x3f4448, 0x5c4a44],
  },
  [DISTRICT.INDUSTRIAL]: {
    metal: [0x8a9298, 0x76808a, 0x9aa0a2, 0x6b7378, 0x8f8a80],
    solid: [0x9c9a94, 0x87857f, 0xaba79c],
  },
};

const CANOPY_COLOURS = [0x3f6b32, 0x4a7a38, 0x2f5c2a, 0x567f3c, 0x466e42, 0x5c8442, 0x6b8438];
const AUTUMN_COLOURS = [0xa8722c, 0xb5883a, 0x8f5a24];
const TRUNK_COLOURS = [0x4a3a2c, 0x3f3428, 0x554434];

/** Which district a point belongs to. */
export function districtAt(x, z) {
  const d = Math.hypot(x, z);
  if (d < 270) return DISTRICT.DOWNTOWN;
  if (d < 580) return DISTRICT.MIDTOWN;
  if (d < 880) return DISTRICT.RESIDENTIAL;
  return DISTRICT.INDUSTRIAL;
}

/** Weighted pick from `{key: weight}`. */
function weightedPick(rng, weights) {
  let total = 0;
  for (const w of Object.values(weights)) total += w;
  let r = rng() * total;
  for (const [k, w] of Object.entries(weights)) {
    r -= w;
    if (r <= 0) return k;
  }
  return Object.keys(weights)[0];
}

/** Lot programmes per district: what can occupy a plot, and how often. */
const PROGRAMME = {
  [DISTRICT.DOWNTOWN]: { tower: 46, podium: 22, stucco: 12, shophouse: 8, carpark: 7, plaza: 5 },
  [DISTRICT.MIDTOWN]: { walkup: 34, stucco: 22, shophouse: 18, podium: 8, carpark: 9, vacant: 5, pocketpark: 4 },
  [DISTRICT.RESIDENTIAL]: { house: 62, walkup: 9, stucco: 7, carpark: 4, vacant: 9, pocketpark: 9 },
  [DISTRICT.INDUSTRIAL]: { warehouse: 47, yard: 20, carpark: 12, vacant: 12, stucco: 5, site: 4 },
};

export class City {
  /**
   * @param {import('../physics/Physics.js').Physics} physics
   * @param {object} opts
   */
  constructor(physics, { extent = 1200, seed = 20260814, island = null } = {}) {
    this.physics = physics;
    this.seed = seed;
    this.rng = makeRng(seed);
    this.island = island;
    this.group = new Group();
    this.group.name = 'city';

    // The island mask keeps roads and blocks off the water, so the grid ends at a
    // coastline instead of running out into the sea.
    this.network = new RoadNetwork({
      extent, seed,
      isLand: island ? (x, z) => island.landField(x, z) > 26 : () => true,
    });

    /** Axis-aligned footprints for the minimap and spawn de-confliction. */
    this.buildingBoxes = [];
    this.landmarks = [];
    this.parks = [];
    /** Small solid props (tree trunks, posts) for spawn de-confliction. */
    this.props = [];
    /** Flat open areas suitable for spawning a vehicle or staging a mission. */
    this.openAreas = [];
    this._tmpColor = new Color();

    this._buildTerrainBase();
    this._buildRoads();
    this._buildBlocks();
    this._finalise();
  }

  /** Random element of an array. */
  _pick(arr) { return arr[Math.floor(this.rng() * arr.length)]; }

  /**
   * Heavy-tailed height sampler. A plain uniform range makes every building look like
   * the average; this produces mostly modest buildings with a few genuine standouts.
   */
  _heightSample(base, spread, tailChance = 0.1, tailMultiplier = 2.4) {
    const r = this.rng();
    // Cube the roll so low values dominate, then occasionally let one run away.
    let h = base + spread * (r * r * r * 0.6 + r * 0.4);
    if (this.rng() < tailChance) h *= 1 + this.rng() * (tailMultiplier - 1);
    return h;
  }

  /* ------------------------------------------------------------------- base plane */

  /**
   * The road surface. Rather than one huge quad, this is emitted cell by cell and
   * clipped to the island, so asphalt stops at the shore and the beach takes over.
   * Sidewalk slabs and buildings are laid on top, so the only place it shows through is
   * the carriageway itself.
   */
  _buildTerrainBase() {
    const b = new GeometryBuilder();
    const e = this.network.extent + 70;
    const cell = 40;
    const n = Math.ceil((e * 2) / cell);
    for (let j = 0; j < n; j++) {
      for (let i = 0; i < n; i++) {
        const x0 = -e + i * cell, z0 = -e + j * cell;
        const cx = x0 + cell / 2, cz = z0 + cell / 2;
        if (this.island && this.island.landField(cx, cz) < 8) continue;
        b.ground(x0, z0, x0 + cell, z0 + cell, 0, 6);
      }
    }
    if (!b.isEmpty) {
      const mesh = new Mesh(b.build(), getMaterial('road'));
      mesh.receiveShadow = true;
      mesh.name = 'roadSurface';
      this.group.add(mesh);
    }

    // Without an island there is no other ground provider, so add one here.
    if (!this.island) this.physics.addGround(0, e + 200, GROUP.TERRAIN);
  }

  /* ------------------------------------------------------------------------ roads */

  _buildRoads() {
    const markings = new GeometryBuilder();
    const net = this.network;

    for (const e of net.edges) {
      const a = net.nodes[e.a], b = net.nodes[e.b];
      const isAvenue = e.type === ROAD.AVENUE;
      const halfW = e.type.width / 2;

      if (isAvenue) {
        markings.setColor(0xd8c24a);            // yellow centre pair
        this._stripe(markings, a, e, -0.35, 0.16);
        this._stripe(markings, a, e, 0.35, 0.16);
        markings.setColor(0xdedbd2);
      } else {
        this._dashedStripe(markings, a, e, 0, 0.14, 3.0, 4.5);
      }

      this._stripe(markings, a, e, halfW - 0.55, 0.13);
      this._stripe(markings, a, e, -(halfW - 0.55), 0.13);

      if (isAvenue) {
        this._dashedStripe(markings, a, e, halfW / 2 + 0.4, 0.12, 2.5, 5.0);
        this._dashedStripe(markings, a, e, -(halfW / 2 + 0.4), 0.12, 2.5, 5.0);
      }
    }

    for (const n of net.nodes) {
      if (n.edges.length < 3) continue;
      for (const eid of n.edges) {
        const e = net.edges[eid];
        const other = net.nodes[net.otherEnd(e, n.id)];
        this._crossing(markings, n, other, e);
      }
    }

    if (!markings.isEmpty) {
      const mesh = new Mesh(markings.build(), getFlat(0xffffff, { roughness: 0.55, metalness: 0.0 }));
      mesh.name = 'roadMarkings';
      mesh.receiveShadow = true;
      this.group.add(mesh);
    }
  }

  _stripe(b, a, e, lateral, width) {
    const ux = e.dirX, uz = e.dirZ;
    const rx = -uz, rz = ux;
    const inset = e.type.width / 2 + 1.5;
    const len = e.length - inset * 2;
    if (len <= 0) return;
    const sx = a.x + ux * inset + rx * lateral;
    const sz = a.z + uz * inset + rz * lateral;
    const cx = sx + ux * (len / 2), cz = sz + uz * (len / 2);
    const yaw = Math.atan2(ux, uz);
    b.rotatedBox(cx, 0.012, cz, width / 2, 0.006, len / 2, -yaw, 1, { sides: false, top: true });
  }

  _dashedStripe(b, a, e, lateral, width, dash, gap) {
    const ux = e.dirX, uz = e.dirZ;
    const rx = -uz, rz = ux;
    const inset = e.type.width / 2 + 1.5;
    const usable = e.length - inset * 2;
    if (usable <= dash) return;
    const period = dash + gap;
    const count = Math.floor(usable / period);
    const yaw = Math.atan2(ux, uz);
    for (let i = 0; i < count; i++) {
      const start = inset + i * period + gap / 2;
      const cx = a.x + ux * (start + dash / 2) + rx * lateral;
      const cz = a.z + uz * (start + dash / 2) + rz * lateral;
      b.rotatedBox(cx, 0.012, cz, width / 2, 0.006, dash / 2, -yaw, 1, { sides: false, top: true });
    }
  }

  _crossing(b, node, other, edge) {
    const dx = other.x - node.x, dz = other.z - node.z;
    const len = Math.hypot(dx, dz);
    const ux = dx / len, uz = dz / len;
    const rx = -uz, rz = ux;
    const dist = edge.type.width / 2 + 2.6;
    const halfW = edge.type.width / 2 - 0.6;
    const yaw = Math.atan2(ux, uz);
    for (let i = 0; i < 6; i++) {
      const t = (i + 0.5) / 6;
      const lateral = (t - 0.5) * 2 * halfW;
      const cx = node.x + ux * dist + rx * lateral;
      const cz = node.z + uz * dist + rz * lateral;
      b.rotatedBox(cx, 0.013, cz, 0.32, 0.006, 1.9, -yaw, 1, { sides: false, top: true });
    }
  }

  /* ----------------------------------------------------------------------- blocks */

  _buildBlocks() {
    this.builders = {
      sidewalk: new GeometryBuilder(),
      concrete: new GeometryBuilder(),
      brick: new GeometryBuilder(),
      glassTower: new GeometryBuilder(),
      roof: new GeometryBuilder(),
      grass: new GeometryBuilder(),
      corrugated: new GeometryBuilder(),
      metal: new GeometryBuilder(),
      wood: new GeometryBuilder(),
      foliage: new GeometryBuilder(),
    };

    for (const block of this.network.blocks) {
      const district = districtAt(block.cx, block.cz);
      this._sidewalkFor(block);

      // Whole-block parks, distinct from per-lot pocket parks.
      const parkChance = district === DISTRICT.RESIDENTIAL ? 0.13
        : district === DISTRICT.MIDTOWN ? 0.06 : 0.035;
      if (this.rng() < parkChance && block.w > 34 && block.d > 34) {
        this._bigPark(block);
        this._streetTrees(block, district);
        continue;
      }

      for (const lot of this._subdivide(block, district)) {
        this._developLot(lot, district);
      }
      this._streetTrees(block, district);
    }
  }

  _sidewalkFor(block) {
    const b = this.builders.sidewalk;
    const x0 = block.x0 - SIDEWALK_WIDTH, x1 = block.x1 + SIDEWALK_WIDTH;
    const z0 = block.z0 - SIDEWALK_WIDTH, z1 = block.z1 + SIDEWALK_WIDTH;
    // Slight per-block tint variation so pavements are not one flat sheet of grey.
    b.setColor(0xffffff, 0.9 + this.rng() * 0.18);
    b.box(new Vector3(x0, 0, z0), new Vector3(x1, SIDEWALK_HEIGHT, z1), 3.0);
    b.resetColor();
    this.physics.addStaticBox(
      new Vector3(block.cx, SIDEWALK_HEIGHT / 2, block.cz),
      new Vector3((x1 - x0) / 2, SIDEWALK_HEIGHT / 2, (z1 - z0) / 2),
      0, GROUP.STATIC,
    );
  }

  /**
   * Street trees around a block perimeter. Randomised spacing with gaps, so blocks read
   * as leafy, patchy or bare rather than uniformly planted.
   */
  _streetTrees(block, district) {
    const density = {
      [DISTRICT.DOWNTOWN]: 0.35,
      [DISTRICT.MIDTOWN]: 0.55,
      [DISTRICT.RESIDENTIAL]: 0.75,
      [DISTRICT.INDUSTRIAL]: 0.12,
    }[district];
    // A block-level roll means some streets are avenues of trees and others are bare.
    const blockDensity = density * (0.3 + this.rng() * 1.4);
    const spacing = 11 + this.rng() * 7;
    const inset = SIDEWALK_WIDTH * 0.55;

    const edges = [
      { x0: block.x0, z0: block.z0 - inset, x1: block.x1, z1: block.z0 - inset },
      { x0: block.x0, z0: block.z1 + inset, x1: block.x1, z1: block.z1 + inset },
      { x0: block.x0 - inset, z0: block.z0, x1: block.x0 - inset, z1: block.z1 },
      { x0: block.x1 + inset, z0: block.z0, x1: block.x1 + inset, z1: block.z1 },
    ];
    for (const e of edges) {
      const len = Math.hypot(e.x1 - e.x0, e.z1 - e.z0);
      const count = Math.floor(len / spacing);
      for (let i = 0; i < count; i++) {
        if (this.rng() > blockDensity) continue;
        const t = (i + 0.5) / count;
        const x = e.x0 + (e.x1 - e.x0) * t + (this.rng() - 0.5) * 1.2;
        const z = e.z0 + (e.z1 - e.z0) * t + (this.rng() - 0.5) * 1.2;
        this._tree(x, SIDEWALK_HEIGHT, z, 0.8 + this.rng() * 0.6);
      }
    }
  }

  /** One tree: tapered trunk plus two or three overlapping canopy blobs. */
  _tree(x, y, z, scale = 1) {
    const f = this.builders.foliage;
    const trunkH = (2.2 + this.rng() * 1.9) * scale;
    const trunkR = (0.16 + this.rng() * 0.09) * scale;

    f.setColor(this._pick(TRUNK_COLOURS), 0.85 + this.rng() * 0.3);
    f.cylinder(x, y, z, trunkR, trunkH, 7, 1.4, false, trunkR * 0.62);

    const autumn = this.rng() < 0.12;
    const base = autumn ? this._pick(AUTUMN_COLOURS) : this._pick(CANOPY_COLOURS);
    const blobs = 2 + Math.floor(this.rng() * 2);
    const canopyR = (1.5 + this.rng() * 1.1) * scale;
    for (let i = 0; i < blobs; i++) {
      // Per-blob brightness variation fakes self-shadowing inside the canopy.
      f.setColor(base, 0.72 + this.rng() * 0.55);
      f.blob(
        x + (this.rng() - 0.5) * canopyR * 0.85,
        y + trunkH + canopyR * (0.35 + this.rng() * 0.4),
        z + (this.rng() - 0.5) * canopyR * 0.85,
        canopyR * (0.62 + this.rng() * 0.42),
        { rings: 4, segments: 7, squashY: 0.82 + this.rng() * 0.3, jitter: 0.35, rand: this.rng },
      );
    }
    f.resetColor();

    // Thin collider so the player and cars cannot walk through trunks. Kept close to the
    // visible trunk radius: an oversized box is an invisible obstacle, and anything that
    // spawns inside it starts the game stuck in solid geometry.
    const colliderR = Math.max(0.12, trunkR * 1.05);
    this.physics.addStaticBox(
      new Vector3(x, y + trunkH / 2, z),
      new Vector3(colliderR, trunkH / 2, colliderR), 0, GROUP.PROP,
    );
    this.props.push({ x, z, radius: colliderR * 1.5 });
  }

  /** Full-block park: lawn, paths, scattered trees, hedges. */
  _bigPark(block) {
    const g = this.builders.grass;
    const inset = 1.4;
    g.setColor(0xffffff, 0.82 + this.rng() * 0.36);
    g.box(
      new Vector3(block.x0 + inset, SIDEWALK_HEIGHT, block.z0 + inset),
      new Vector3(block.x1 - inset, SIDEWALK_HEIGHT + 0.12, block.z1 - inset),
      5.0,
    );
    g.resetColor();

    // Crossing gravel paths.
    const s = this.builders.sidewalk;
    const y = SIDEWALK_HEIGHT + 0.13;
    s.setColor(0xffffff, 0.86);
    s.ground(block.x0 + inset, block.cz - 1.5, block.x1 - inset, block.cz + 1.5, y, 2.5);
    s.ground(block.cx - 1.5, block.z0 + inset, block.cx + 1.5, block.z1 - inset, y, 2.5);
    s.resetColor();

    const trees = 4 + Math.floor(this.rng() * 9);
    for (let i = 0; i < trees; i++) {
      const x = block.x0 + 4 + this.rng() * (block.w - 8);
      const z = block.z0 + 4 + this.rng() * (block.d - 8);
      if (Math.abs(x - block.cx) < 3 || Math.abs(z - block.cz) < 3) continue;
      this._tree(x, SIDEWALK_HEIGHT + 0.12, z, 1.0 + this.rng() * 0.9);
    }

    this.parks.push({ ...block });
    this.openAreas.push({ x: block.cx, z: block.cz, radius: Math.min(block.w, block.d) / 2 });
    this.landmarks.push({ kind: 'park', x: block.cx, y: SIDEWALK_HEIGHT, z: block.cz });
  }

  _subdivide(block, district) {
    const target = {
      [DISTRICT.DOWNTOWN]: 48,
      [DISTRICT.MIDTOWN]: 34,
      [DISTRICT.RESIDENTIAL]: 19,
      [DISTRICT.INDUSTRIAL]: 44,
    }[district] ?? 30;

    const lots = [];
    const split = (x0, z0, x1, z1, depth) => {
      const w = x1 - x0, d = z1 - z0;
      if (depth > 5 || (w <= target * 1.5 && d <= target * 1.5)) {
        if (w > 8 && d > 8) lots.push({ x0, z0, x1, z1, cx: (x0 + x1) / 2, cz: (z0 + z1) / 2, w, d });
        return;
      }
      const alongX = w > d ? true : w < d ? false : this.rng() < 0.5;
      // Wider jitter than a clean halving: produces genuinely different lot sizes.
      const jitter = 0.5 + (this.rng() - 0.5) * 0.36;
      if (alongX) {
        const m = x0 + w * jitter;
        split(x0, z0, m, z1, depth + 1);
        split(m, z0, x1, z1, depth + 1);
      } else {
        const m = z0 + d * jitter;
        split(x0, z0, x1, m, depth + 1);
        split(x0, m, x1, z1, depth + 1);
      }
    };
    split(block.x0, block.z0, block.x1, block.z1, 0);
    return lots;
  }

  /** Choose and build a programme for one lot. */
  _developLot(lot, district) {
    const kind = weightedPick(this.rng, PROGRAMME[district]);
    const y = SIDEWALK_HEIGHT;
    // Setback varies per lot so the street wall is not perfectly flush.
    const gap = (district === DISTRICT.RESIDENTIAL ? 1.8 : 0.5) + this.rng() * 1.6;
    const x0 = lot.x0 + gap, x1 = lot.x1 - gap;
    const z0 = lot.z0 + gap, z1 = lot.z1 - gap;
    if (x1 - x0 < 6 || z1 - z0 < 6) return;

    switch (kind) {
      case 'tower': return this._tower(x0, z0, x1, z1, y, district);
      case 'podium': return this._podiumTower(x0, z0, x1, z1, y, district);
      case 'walkup': return this._walkup(x0, z0, x1, z1, y, district);
      case 'stucco': return this._stuccoBlock(x0, z0, x1, z1, y, district);
      case 'shophouse': return this._shophouseRow(x0, z0, x1, z1, y, district);
      case 'house': return this._house(x0, z0, x1, z1, y);
      case 'warehouse': return this._warehouse(x0, z0, x1, z1, y);
      case 'carpark': return this._carPark(lot, y);
      case 'vacant': return this._vacantLot(lot, y);
      case 'pocketpark': return this._pocketPark(lot, y);
      case 'plaza': return this._plaza(lot, y);
      case 'yard': return this._yard(lot, y);
      case 'site': return this._constructionSite(x0, z0, x1, z1, y);
      default: return undefined;
    }
  }

  _registerCollider(x0, z0, x1, z1, y0, y1, district) {
    this.physics.addStaticBox(
      new Vector3((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
      new Vector3((x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2),
      0, GROUP.BUILDING,
    );
    this.buildingBoxes.push({ x0, z0, x1, z1, height: y1, district });
  }

  /* ------------------------------------------------------------------ archetypes */

  /** Setback tower: glass or solid, 1-4 tiers, occasional spire. */
  _tower(x0, z0, x1, z1, y, district) {
    const r = this.rng;
    const pal = PALETTE[district] ?? PALETTE[DISTRICT.DOWNTOWN];
    const footprint = Math.min(x1 - x0, z1 - z0);
    const glassy = r() < (district === DISTRICT.DOWNTOWN ? 0.66 : 0.3);
    const shell = glassy ? this.builders.glassTower : this.builders.concrete;
    const tileShell = glassy ? 9 : 5;
    const tint = glassy ? this._pick(pal.glass ?? pal.solid) : this._pick(pal.solid);

    const centrality = 1 - Math.min(1, Math.hypot((x0 + x1) / 2, (z0 + z1) / 2) / 320);
    let height = this._heightSample(20 + centrality * 40 + footprint * 0.7, 70 * (0.4 + centrality), 0.12, 2.6);
    const tiers = 1 + Math.floor(r() * 4);
    let cx0 = x0, cz0 = z0, cx1 = x1, cz1 = z1;
    let base = y;
    const uvOffset = [r() * 6, r() * 6];
    const shade = 0.82 + r() * 0.36;

    for (let t = 0; t < tiers; t++) {
      const share = t === tiers - 1 ? 1 : 0.3 + r() * 0.35;
      const remaining = height - (base - y);
      if (remaining < 6) break;
      const h = Math.max(7, remaining * share);
      const top = base + h;

      shell.setColor(tint, shade);
      shell.box(new Vector3(cx0, base, cz0), new Vector3(cx1, top, cz1), tileShell, { top: false, uvOffset });
      shell.resetColor();

      this.builders.roof.setColor(0xffffff, 0.8 + r() * 0.4);
      this.builders.roof.ground(cx0, cz0, cx1, cz1, top + 0.02, 4);
      this.builders.roof.resetColor();

      this.builders.concrete.setColor(tint, shade * 0.9);
      this.builders.concrete.box(
        new Vector3(cx0 - 0.35, top, cz0 - 0.35), new Vector3(cx1 + 0.35, top + 0.9, cz1 + 0.35), 2.5,
      );
      this.builders.concrete.resetColor();

      this._registerCollider(cx0, cz0, cx1, cz1, base, top + 0.9, district);

      base = top + 0.9;
      const inset = 1.2 + r() * 4.0;
      cx0 += inset; cz0 += inset; cx1 -= inset; cz1 -= inset;
      if (cx1 - cx0 < 9 || cz1 - cz0 < 9) break;
    }

    this._rooftop(cx0, cz0, cx1, cz1, base);
    // Antenna mast on a minority of the tall ones - breaks up the skyline.
    if (base - y > 70 && r() < 0.35) {
      const m = this.builders.metal;
      m.setColor(0xb0b4b8, 0.9);
      m.cylinder((cx0 + cx1) / 2, base, (cz0 + cz1) / 2, 0.28, 6 + r() * 16, 6, 2, true, 0.09);
      m.resetColor();
    }
    if (base - y > 85) {
      this.landmarks.push({ kind: 'tower', x: (x0 + x1) / 2, y: base, z: (z0 + z1) / 2, height: base - y });
    }
  }

  /** Wide podium with a slender tower offset on top - a very recognisable city shape. */
  _podiumTower(x0, z0, x1, z1, y, district) {
    const r = this.rng;
    const pal = PALETTE[district] ?? PALETTE[DISTRICT.MIDTOWN];
    const podiumH = 8 + r() * 12;
    const podiumTop = y + podiumH;
    const podTint = this._pick(pal.solid);

    const c = this.builders.concrete;
    c.setColor(podTint, 0.85 + r() * 0.3);
    c.box(new Vector3(x0, y, z0), new Vector3(x1, podiumTop, z1), 5, { top: false, uvOffset: [r() * 4, 0] });
    c.resetColor();
    this.builders.roof.ground(x0, z0, x1, z1, podiumTop + 0.02, 4);
    this._registerCollider(x0, z0, x1, z1, y, podiumTop, district);

    // Tower sits on part of the podium, pushed to one side.
    const tw = (x1 - x0) * (0.4 + r() * 0.32);
    const td = (z1 - z0) * (0.4 + r() * 0.32);
    if (tw < 7 || td < 7) return;
    const tx0 = x0 + (x1 - x0 - tw) * r();
    const tz0 = z0 + (z1 - z0 - td) * r();
    const tx1 = tx0 + tw, tz1 = tz0 + td;
    const glassy = r() < 0.6;
    const shell = glassy ? this.builders.glassTower : this.builders.brick;
    const tint = glassy ? this._pick(pal.glass ?? pal.solid) : this._pick(pal.brick ?? pal.solid);
    const height = this._heightSample(16, 60, 0.14, 2.2);
    const top = podiumTop + height;

    shell.setColor(tint, 0.82 + r() * 0.34);
    shell.box(new Vector3(tx0, podiumTop, tz0), new Vector3(tx1, top, tz1), glassy ? 9 : 3.2,
      { top: false, uvOffset: [r() * 5, r() * 3] });
    shell.resetColor();
    this.builders.roof.ground(tx0, tz0, tx1, tz1, top + 0.02, 4);
    this._registerCollider(tx0, tz0, tx1, tz1, podiumTop, top, district);
    this._rooftop(tx0 + 0.5, tz0 + 0.5, tx1 - 0.5, tz1 - 0.5, top);
  }

  /** Brick walk-up with cornice, fire escape and a shopfront plinth. */
  _walkup(x0, z0, x1, z1, y, district) {
    const r = this.rng;
    const pal = PALETTE[district] ?? PALETTE[DISTRICT.MIDTOWN];
    const brickish = r() < 0.7;
    const shell = brickish ? this.builders.brick : this.builders.concrete;
    const tint = brickish ? this._pick(pal.brick ?? pal.solid) : this._pick(pal.solid);
    const tile = brickish ? 3.2 : 5;
    const floors = 2 + Math.floor(this._heightSample(1, 11, 0.1, 1.8));
    const height = floors * (3.1 + r() * 0.6);
    const top = y + height;
    const shade = 0.8 + r() * 0.4;

    const plinth = 3.2 + r() * 0.9;
    const c = this.builders.concrete;
    c.setColor(0xffffff, 0.55 + r() * 0.3);
    c.box(new Vector3(x0 - 0.2, y, z0 - 0.2), new Vector3(x1 + 0.2, y + plinth, z1 + 0.2), 4, { top: false });
    c.resetColor();

    shell.setColor(tint, shade);
    shell.box(new Vector3(x0, y + plinth, z0), new Vector3(x1, top, z1), tile,
      { top: false, uvOffset: [r() * 5, r() * 2] });
    shell.resetColor();

    c.setColor(tint, shade * 1.15);
    c.box(new Vector3(x0 - 0.45, top, z0 - 0.45), new Vector3(x1 + 0.45, top + 0.75, z1 + 0.45), 2.5);
    c.resetColor();

    this.builders.roof.setColor(0xffffff, 0.85 + r() * 0.3);
    this.builders.roof.ground(x0, z0, x1, z1, top + 0.03, 4);
    this.builders.roof.resetColor();

    this._registerCollider(x0, z0, x1, z1, y, top + 0.75, district);
    this._rooftop(x0 + 1, z0 + 1, x1 - 1, z1 - 1, top + 0.75);

    // Water tower on a few of them.
    if (r() < 0.18 && x1 - x0 > 11 && z1 - z0 > 11) {
      const w = this.builders.wood;
      const px = (x0 + x1) / 2, pz = (z0 + z1) / 2;
      const legH = 1.9;
      w.setColor(0xffffff, 0.8 + r() * 0.3);
      for (const [dx, dz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
        w.cylinder(px + dx * 1.5, top + 0.75, pz + dz * 1.5, 0.11, legH, 5, 1, false);
      }
      w.cylinder(px, top + 0.75 + legH, pz, 2.0, 3.0, 10, 2, true, 1.85);
      w.resetColor();
    }
  }

  /** Painted stucco/concrete block: the workhorse mid-rise, strong colour variation. */
  _stuccoBlock(x0, z0, x1, z1, y, district) {
    const r = this.rng;
    const pal = PALETTE[district] ?? PALETTE[DISTRICT.MIDTOWN];
    const tint = this._pick(pal.solid);
    const floors = 2 + Math.floor(r() * 7);
    const height = floors * (3.0 + r() * 0.5);
    const top = y + height;

    const c = this.builders.concrete;
    c.setColor(tint, 0.78 + r() * 0.44);
    c.box(new Vector3(x0, y, z0), new Vector3(x1, top, z1), 4.5,
      { top: false, uvOffset: [r() * 6, r() * 3] });
    c.resetColor();

    // Flat roof with a low parapet, sometimes a stair box.
    this.builders.roof.setColor(0xffffff, 0.8 + r() * 0.4);
    this.builders.roof.ground(x0, z0, x1, z1, top + 0.02, 4);
    this.builders.roof.resetColor();
    c.setColor(tint, 0.9);
    c.box(new Vector3(x0 - 0.2, top, z0 - 0.2), new Vector3(x1 + 0.2, top + 0.55, z1 + 0.2), 2.5);
    c.resetColor();

    this._registerCollider(x0, z0, x1, z1, y, top + 0.55, district);
    this._rooftop(x0 + 1, z0 + 1, x1 - 1, z1 - 1, top + 0.55);
  }

  /** A terrace of narrow shopfronts, each its own width, height and colour. */
  _shophouseRow(x0, z0, x1, z1, y, district) {
    const r = this.rng;
    const pal = PALETTE[district] ?? PALETTE[DISTRICT.MIDTOWN];
    const alongX = (x1 - x0) >= (z1 - z0);
    const span = alongX ? x1 - x0 : z1 - z0;
    const units = Math.max(2, Math.floor(span / (7 + r() * 5)));
    let cursor = 0;

    for (let i = 0; i < units; i++) {
      const share = (1 / units) * (0.72 + r() * 0.56);
      const w = Math.min(span - cursor, span * share);
      if (w < 4.5) break;
      const a0 = cursor, a1 = cursor + w - 0.35;
      cursor += w;

      const brickish = r() < 0.55;
      const shell = brickish ? this.builders.brick : this.builders.concrete;
      const tint = brickish ? this._pick(pal.brick ?? pal.solid) : this._pick(pal.solid);
      const floors = 2 + Math.floor(r() * 3);
      const height = floors * (3.2 + r() * 0.5);
      const top = y + height;

      const bx0 = alongX ? x0 + a0 : x0;
      const bx1 = alongX ? x0 + a1 : x1;
      const bz0 = alongX ? z0 : z0 + a0;
      const bz1 = alongX ? z1 : z0 + a1;

      shell.setColor(tint, 0.75 + r() * 0.5);
      shell.box(new Vector3(bx0, y, bz0), new Vector3(bx1, top, bz1), brickish ? 3.0 : 4,
        { top: false, uvOffset: [r() * 6, r() * 2] });
      shell.resetColor();

      // Shop awning in a saturated colour - the strongest street-level read.
      const m = this.builders.metal;
      m.setColor([0xb5453a, 0x2f6f4f, 0x2f5f8f, 0xc98a2f, 0x7a3f6f][Math.floor(r() * 5)], 1.0);
      if (alongX) {
        m.box(new Vector3(bx0, y + 3.0, bz0 - 1.5), new Vector3(bx1, y + 3.28, bz0), 1.4);
      } else {
        m.box(new Vector3(bx0 - 1.5, y + 3.0, bz0), new Vector3(bx0, y + 3.28, bz1), 1.4);
      }
      m.resetColor();

      this.builders.roof.ground(bx0, bz0, bx1, bz1, top + 0.02, 4);
      this._registerCollider(bx0, bz0, bx1, bz1, y, top, district);
    }
  }

  /** Suburban house: garden, driveway, varied roof and colour. */
  _house(x0, z0, x1, z1, y) {
    const r = this.rng;
    const pal = PALETTE[DISTRICT.RESIDENTIAL];
    const g = this.builders.grass;
    g.setColor(0xffffff, 0.75 + r() * 0.5);
    g.box(new Vector3(x0, y, z0), new Vector3(x1, y + 0.1, z1), 4);
    g.resetColor();

    const w = x1 - x0, d = z1 - z0;
    const hw = Math.min(w - 2.5, 5 + r() * 7);
    const hd = Math.min(d - 2.5, 5 + r() * 7);
    if (hw < 4 || hd < 4) return;
    const hx0 = x0 + (w - hw) * (0.25 + r() * 0.5);
    const hz0 = z0 + (d - hd) * (0.25 + r() * 0.5);
    const hx1 = hx0 + hw, hz1 = hz0 + hd;
    const storeys = r() < 0.32 ? 2 : 1;
    const height = storeys * (2.9 + r() * 0.5);
    const top = y + 0.1 + height;

    const brickish = r() < 0.42;
    const shell = brickish ? this.builders.brick : this.builders.concrete;
    const tint = brickish ? this._pick(pal.brick) : this._pick(pal.solid);
    shell.setColor(tint, 0.8 + r() * 0.42);
    shell.box(new Vector3(hx0, y + 0.1, hz0), new Vector3(hx1, top, hz1), brickish ? 3.0 : 4,
      { top: false, uvOffset: [r() * 4, 0] });
    shell.resetColor();

    const roof = this.builders.roof;
    roof.setColor(this._pick(pal.roof), 0.85 + r() * 0.35);
    if (r() < 0.82) {
      roof.gableRoof(hx0 - 0.5, hz0 - 0.5, hx1 + 0.5, hz1 + 0.5, top, 1.4 + r() * 1.8, 2.2, hw > hd);
    } else {
      roof.box(new Vector3(hx0 - 0.4, top, hz0 - 0.4), new Vector3(hx1 + 0.4, top + 0.35, hz1 + 0.4), 2.5);
    }
    roof.resetColor();

    // Driveway slab and a hedge or two in the garden.
    const s = this.builders.sidewalk;
    s.setColor(0xffffff, 0.7 + r() * 0.25);
    s.ground(hx0, z0, Math.min(hx0 + 3.2, hx1), hz0, y + 0.12, 2.5);
    s.resetColor();
    const hedges = Math.floor(r() * 3);
    for (let i = 0; i < hedges; i++) {
      const f = this.builders.foliage;
      f.setColor(this._pick(CANOPY_COLOURS), 0.7 + r() * 0.4);
      f.blob(x0 + 1 + r() * (w - 2), y + 0.5, z0 + 1 + r() * (d - 2), 0.5 + r() * 0.4,
        { rings: 3, segments: 6, squashY: 0.8, jitter: 0.4, rand: this.rng });
      f.resetColor();
    }
    if (r() < 0.5) this._tree(x0 + 1.2 + r() * (w - 2.4), y + 0.1, z0 + 1.2 + r() * (d - 2.4), 0.9 + r() * 0.8);

    this._registerCollider(hx0, hz0, hx1, hz1, y, top + 1.6, DISTRICT.RESIDENTIAL);
  }

  /** Industrial shed with corrugated walls and a yard. */
  _warehouse(x0, z0, x1, z1, y) {
    const r = this.rng;
    const pal = PALETTE[DISTRICT.INDUSTRIAL];
    const height = 6 + this._heightSample(1, 12, 0.08, 1.6);
    const top = y + height;
    const tint = this._pick(pal.metal);

    const cg = this.builders.corrugated;
    cg.setColor(tint, 0.78 + r() * 0.44);
    cg.box(new Vector3(x0, y, z0), new Vector3(x1, top, z1), 4.5,
      { top: false, uvOffset: [r() * 4, 0] });
    cg.resetColor();

    this.builders.roof.setColor(0xffffff, 0.8 + r() * 0.3);
    this.builders.roof.ground(x0 - 0.5, z0 - 0.5, x1 + 0.5, z1 + 0.5, top, 4);
    this.builders.roof.resetColor();

    const m = this.builders.metal;
    m.setColor(tint, 0.9);
    m.box(new Vector3(x0 - 0.6, top, z0 - 0.6), new Vector3(x1 + 0.6, top + 0.4, z1 + 0.6), 3, { top: false });
    // Roller shutter band in a contrasting colour.
    m.setColor(0x8a6f3a, 1.0);
    m.box(new Vector3(x0 + (x1 - x0) * 0.3, y, z0 - 0.12),
      new Vector3(x0 + (x1 - x0) * 0.62, y + 4.2, z0 + 0.06), 2.0, { top: false });
    m.resetColor();

    this._registerCollider(x0, z0, x1, z1, y, top + 0.4, DISTRICT.INDUSTRIAL);
    this._rooftop(x0 + 1.5, z0 + 1.5, x1 - 1.5, z1 - 1.5, top + 0.4);
  }

  /** Rooftop plant: AC units, lift overrun, vents. */
  _rooftop(x0, z0, x1, z1, y) {
    const r = this.rng;
    if (x1 - x0 < 7 || z1 - z0 < 7) return;
    const units = Math.floor(r() * 4);
    const m = this.builders.metal;
    for (let i = 0; i < units; i++) {
      const w = 1.4 + r() * 2.8, d = 1.4 + r() * 2.8, h = 0.8 + r() * 1.9;
      const px = x0 + 1.2 + r() * Math.max(0.1, (x1 - x0) - w - 2.4);
      const pz = z0 + 1.2 + r() * Math.max(0.1, (z1 - z0) - d - 2.4);
      m.setColor(0xb8bcc0, 0.7 + r() * 0.5);
      m.box(new Vector3(px, y, pz), new Vector3(px + w, y + h, pz + d), 1.6);
      m.resetColor();
    }
    if (r() < 0.4) {
      const c = this.builders.concrete;
      const w = 2.6 + r() * 1.6, d = 2.6 + r() * 1.6, h = 2.6 + r() * 1.4;
      const px = (x0 + x1) / 2 - w / 2, pz = (z0 + z1) / 2 - d / 2;
      c.setColor(0xffffff, 0.75 + r() * 0.3);
      c.box(new Vector3(px, y, pz), new Vector3(px + w, y + h, pz + d), 2.5);
      c.resetColor();
    }
  }

  /* --------------------------------------------------------- non-building lots */

  /** Surface car park: asphalt apron, painted bays, a kerb line. */
  _carPark(lot, y) {
    const s = this.builders.sidewalk;
    // Asphalt sits just above the pavement slab so it reads as a separate surface.
    s.setColor(0x4a4a4d, 1.0);
    s.ground(lot.x0, lot.z0, lot.x1, lot.z1, y + 0.02, 4);
    s.resetColor();

    const bays = Math.floor((lot.x1 - lot.x0) / 2.7);
    const m = this.builders.metal;
    m.setColor(0xe0ddd4, 1.0);
    for (let i = 0; i <= bays; i++) {
      const x = lot.x0 + 0.4 + i * 2.7;
      if (x > lot.x1 - 0.3) break;
      m.box(new Vector3(x, y + 0.03, lot.z0 + 0.6), new Vector3(x + 0.12, y + 0.035, lot.z0 + 5.4), 1,
        { sides: false });
    }
    m.resetColor();
    this.openAreas.push({ x: lot.cx, z: lot.cz, radius: Math.min(lot.w, lot.d) / 2 });
  }

  /** Vacant plot: dirt, weeds, rubble, hoarding on one side. */
  _vacantLot(lot, y) {
    const r = this.rng;
    const g = this.builders.grass;
    g.setColor(0xbfae86, 0.85 + r() * 0.3);        // dry, dusty ground
    g.box(new Vector3(lot.x0, y, lot.z0), new Vector3(lot.x1, y + 0.06, lot.z1), 4);
    g.resetColor();

    const f = this.builders.foliage;
    const weeds = 3 + Math.floor(r() * 8);
    for (let i = 0; i < weeds; i++) {
      f.setColor(this._pick(CANOPY_COLOURS), 0.55 + r() * 0.4);
      f.blob(lot.x0 + r() * lot.w, y + 0.3, lot.z0 + r() * lot.d, 0.25 + r() * 0.45,
        { rings: 3, segments: 5, squashY: 0.7, jitter: 0.5, rand: this.rng });
      f.resetColor();
    }
    const c = this.builders.concrete;
    const chunks = Math.floor(r() * 5);
    for (let i = 0; i < chunks; i++) {
      const w = 0.4 + r() * 1.2;
      const px = lot.x0 + r() * (lot.w - w), pz = lot.z0 + r() * (lot.d - w);
      c.setColor(0xffffff, 0.6 + r() * 0.3);
      c.box(new Vector3(px, y, pz), new Vector3(px + w, y + 0.2 + r() * 0.4, pz + w), 1.5);
      c.resetColor();
    }
    // Hoarding fence along the street edge.
    const m = this.builders.metal;
    m.setColor(0x7a8288, 0.9);
    m.box(new Vector3(lot.x0, y, lot.z0), new Vector3(lot.x1, y + 2.1, lot.z0 + 0.12), 2.0, { top: false });
    m.resetColor();
    this.openAreas.push({ x: lot.cx, z: lot.cz, radius: Math.min(lot.w, lot.d) / 2 });
  }

  /** Pocket park inside a single lot: lawn, a few trees, a bench-sized plinth. */
  _pocketPark(lot, y) {
    const r = this.rng;
    const g = this.builders.grass;
    g.setColor(0xffffff, 0.8 + r() * 0.4);
    g.box(new Vector3(lot.x0, y, lot.z0), new Vector3(lot.x1, y + 0.1, lot.z1), 4.5);
    g.resetColor();
    const trees = 1 + Math.floor(r() * 4);
    for (let i = 0; i < trees; i++) {
      this._tree(lot.x0 + 1.5 + r() * (lot.w - 3), y + 0.1, lot.z0 + 1.5 + r() * (lot.d - 3), 1.0 + r() * 0.8);
    }
    this.parks.push({ ...lot });
    this.openAreas.push({ x: lot.cx, z: lot.cz, radius: Math.min(lot.w, lot.d) / 2 });
  }

  /** Paved plaza with planters - the downtown alternative to a building. */
  _plaza(lot, y) {
    const r = this.rng;
    const s = this.builders.sidewalk;
    s.setColor(0xffffff, 0.95 + r() * 0.15);
    s.ground(lot.x0, lot.z0, lot.x1, lot.z1, y + 0.03, 2.2);
    s.resetColor();
    const planters = 1 + Math.floor(r() * 4);
    for (let i = 0; i < planters; i++) {
      const w = 2.0 + r() * 2.4;
      const px = lot.x0 + 1 + r() * Math.max(0.2, lot.w - w - 2);
      const pz = lot.z0 + 1 + r() * Math.max(0.2, lot.d - w - 2);
      const c = this.builders.concrete;
      c.setColor(0xffffff, 0.7 + r() * 0.3);
      c.box(new Vector3(px, y + 0.03, pz), new Vector3(px + w, y + 0.55, pz + w), 2);
      c.resetColor();
      this._tree(px + w / 2, y + 0.55, pz + w / 2, 0.9 + r() * 0.5);
    }
    this.openAreas.push({ x: lot.cx, z: lot.cz, radius: Math.min(lot.w, lot.d) / 2 });
  }

  /** Industrial yard: containers, pallets, a crate stack. */
  _yard(lot, y) {
    const r = this.rng;
    const s = this.builders.sidewalk;
    s.setColor(0x53535a, 1.0);
    s.ground(lot.x0, lot.z0, lot.x1, lot.z1, y + 0.02, 4);
    s.resetColor();

    const CONTAINER = [0xa8442f, 0x2f6f8f, 0x3f7a4f, 0xc9a02f, 0x7a4f8f, 0x8a8a8a];
    const count = 2 + Math.floor(r() * 6);
    const m = this.builders.metal;
    for (let i = 0; i < count; i++) {
      const alongX = r() < 0.5;
      const cl = 6.0, cw = 2.44, ch = 2.6;
      const w = alongX ? cl : cw, d = alongX ? cw : cl;
      if (lot.w < w + 1 || lot.d < d + 1) continue;
      const px = lot.x0 + r() * (lot.w - w), pz = lot.z0 + r() * (lot.d - d);
      const stack = 1 + (r() < 0.35 ? 1 : 0) + (r() < 0.12 ? 1 : 0);
      for (let k = 0; k < stack; k++) {
        m.setColor(this._pick(CONTAINER), 0.8 + r() * 0.4);
        m.box(new Vector3(px, y + k * ch, pz), new Vector3(px + w, y + (k + 1) * ch - 0.05, pz + d), 2.2);
        m.resetColor();
      }
      this._registerCollider(px, pz, px + w, pz + d, y, y + stack * ch, DISTRICT.INDUSTRIAL);
    }
    this.openAreas.push({ x: lot.cx, z: lot.cz, radius: Math.min(lot.w, lot.d) / 3 });
  }

  /** Construction site: slab, columns rising, scaffolding, a crane base. */
  _constructionSite(x0, z0, x1, z1, y) {
    const r = this.rng;
    const c = this.builders.concrete;
    c.setColor(0xffffff, 0.7 + r() * 0.2);
    c.box(new Vector3(x0, y, z0), new Vector3(x1, y + 0.5, z1), 4);
    c.resetColor();

    const floors = 1 + Math.floor(r() * 5);
    const fh = 3.3;
    const cols = 3, rows = 3;
    for (let f = 0; f < floors; f++) {
      const base = y + 0.5 + f * fh;
      // Slabs get progressively smaller as they go up, as if mid-pour.
      const shrink = f * 0.6;
      const sx0 = x0 + shrink, sx1 = x1 - shrink, sz0 = z0 + shrink, sz1 = z1 - shrink;
      if (sx1 - sx0 < 4 || sz1 - sz0 < 4) break;
      c.setColor(0xffffff, 0.72 + r() * 0.16);
      c.box(new Vector3(sx0, base + fh - 0.3, sz0), new Vector3(sx1, base + fh, sz1), 4);
      for (let i = 0; i < cols; i++) {
        for (let j = 0; j < rows; j++) {
          const px = sx0 + (i / (cols - 1)) * (sx1 - sx0 - 0.5);
          const pz = sz0 + (j / (rows - 1)) * (sz1 - sz0 - 0.5);
          c.box(new Vector3(px, base, pz), new Vector3(px + 0.5, base + fh - 0.3, pz + 0.5), 2);
        }
      }
      c.resetColor();
      this._registerCollider(sx0, sz0, sx1, sz1, base + fh - 0.3, base + fh, DISTRICT.MIDTOWN);
    }

    // Site hoarding and a scaffold tower in raw metal.
    const m = this.builders.metal;
    m.setColor(0xc9a02f, 1.0);
    m.box(new Vector3(x0 - 0.6, y, z0 - 0.6), new Vector3(x1 + 0.6, y + 2.3, z0 - 0.45), 2, { top: false });
    m.setColor(0xb0b4b8, 0.85);
    const legH = 0.5 + floors * fh + 4;
    for (const [dx, dz] of [[0, 0], [1.6, 0], [0, 1.6], [1.6, 1.6]]) {
      m.cylinder(x1 - 2.4 + dx, y, z1 - 2.4 + dz, 0.09, legH, 5, 1.5, false);
    }
    m.resetColor();
  }

  /* ----------------------------------------------------------------------- finish */

  _finalise() {
    const MATERIAL_FOR = {
      sidewalk: 'sidewalk', concrete: 'concrete', brick: 'brick',
      glassTower: 'glassTower', roof: 'roof', grass: 'grass',
      corrugated: 'corrugated', metal: 'metal', wood: 'wood',
    };
    for (const [key, builder] of Object.entries(this.builders)) {
      if (builder.isEmpty) continue;
      const material = key === 'foliage'
        ? getFlat(0xffffff, { roughness: 0.85, metalness: 0.0 })
        : getMaterial(MATERIAL_FOR[key]);
      const mesh = new Mesh(builder.build(), material);
      mesh.name = `city_${key}`;
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      this.group.add(mesh);
    }
    this.bounds = new Box3().setFromObject(this.group);
    this.builders = null;
  }

  /**
   * A safe spawn on a pavement near the middle of downtown.
   *
   * Candidates are walked along the block edge until one is clear of buildings and
   * props - spawning inside a tree trunk leaves the player wedged in solid geometry and
   * makes every camera ray start inside a collider.
   */
  playerSpawn() {
    let best = null, bestD = Infinity;
    for (const b of this.network.blocks) {
      const d = Math.hypot(b.cx, b.cz);
      if (d < bestD) { bestD = d; best = b; }
    }
    if (!best) return new Vector3(0, SIDEWALK_HEIGHT + 1, 0);

    const z = best.z0 - SIDEWALK_WIDTH * 0.5;
    for (let i = 0; i < 24; i++) {
      // Alternate either side of the block centre, stepping outward.
      const offset = Math.ceil(i / 2) * 3.5 * (i % 2 === 0 ? 1 : -1);
      const x = best.cx + offset;
      if (x < best.x0 || x > best.x1) continue;
      if (this.isSpawnClear(x, z, 0.8)) {
        return new Vector3(x, SIDEWALK_HEIGHT + 0.6, z);
      }
    }
    return new Vector3(best.cx, SIDEWALK_HEIGHT + 0.6, z);
  }

  /** Clear of both buildings and small props. */
  isSpawnClear(x, z, radius) {
    if (!this.isFootprintClear(x, z, radius)) return false;
    for (const p of this.props) {
      const r = p.radius + radius;
      if ((p.x - x) ** 2 + (p.z - z) ** 2 < r * r) return false;
    }
    return true;
  }

  /** Whether a footprint overlaps any building - used before dropping a vehicle. */
  isFootprintClear(x, z, radius) {
    for (const b of this.buildingBoxes) {
      if (x + radius > b.x0 && x - radius < b.x1 && z + radius > b.z0 && z - radius < b.z1) return false;
    }
    return true;
  }
}
