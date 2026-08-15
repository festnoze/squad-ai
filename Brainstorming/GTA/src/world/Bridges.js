/**
 * Cable-stayed bridges across the island's two inlets.
 *
 * The island is a single connected landmass - the road graph is one component - so these
 * bridges are not there to make anywhere reachable. They are there because the harbour
 * and the marina are big bites out of the coast and driving round them is a long way:
 * measured on the road graph, the harbour crossing turns a 1478 m detour into a 909 m
 * run and the marina one a 1150 m detour into 684 m. That is what makes a bridge worth
 * building rather than decorative.
 *
 * Like {@link Highway}, a bridge is deliberately NOT spliced into the ground road graph.
 * That graph has no elevation and every consumer of it - traffic, police pursuit, mission
 * placement, parked cars, pedestrians - assumes any node is reachable from any other at
 * y=0. Adding a deck 26 m in the air would put police cars in the water. The bridges
 * carry their own centreline for the map and for anything that later wants to route over
 * them.
 *
 * The deck profile is a ramp-flat-ramp: approach ramps rise over the first and last
 * `rise` of the span, and the main span between the towers is level with a shallow arch.
 * A single smooth hump would put the steepest grade at the shoreline, which is exactly
 * where the deck has to meet a flat street.
 */

import { Mesh, Vector3, Quaternion, Euler } from 'three/webgpu';
import { GeometryBuilder } from './GeometryBuilder.js';
import { getMaterial } from '../render/Materials.js';
import { GROUP } from '../physics/Physics.js';
import { SEA_LEVEL } from './Island.js';

const DECK_THICKNESS = 1.1;
const BARRIER_HEIGHT = 1.05;
const BARRIER_THICKNESS = 0.4;
/** Metres of deck per built segment. Short enough that the pitch reads as a curve. */
const SEGMENT_LENGTH = 13;
/** Piers are only worth placing where there is enough air under the deck to see them. */
const PIER_SPACING = 58;

/**
 * Default spans. Anchors are road-network node positions on either side of each inlet,
 * chosen because the straight line between them crosses open water and no city block -
 * verified by sampling the corridor before these were fixed.
 */
export const BRIDGE_SPECS = [
  {
    id: 'harbour',
    name: 'Harbour Bridge',
    a: { x: 1158, z: -468 },
    b: { x: 566, z: -1158 },
    clearance: 26,
    halfWidth: 9.5,
    towerHeight: 34,
    rise: 0.22,
    arch: 2.2,
  },
  {
    id: 'marina',
    name: 'Marina Bridge',
    a: { x: -1158, z: 468 },
    b: { x: -762, z: 1026 },
    clearance: 16,
    halfWidth: 8,
    towerHeight: 23,
    rise: 0.26,
    arch: 1.4,
  },
];

/** Hermite-style smoothstep, matching the one the terrain uses. */
const smooth = (t) => {
  const c = Math.min(1, Math.max(0, t));
  return c * c * (3 - 2 * c);
};

export class Bridges {
  /**
   * @param {import('../physics/Physics.js').Physics} physics
   * @param {import('./City.js').City} city
   * @param {import('./Island.js').Island} island
   * @param {object[]} specs
   */
  constructor(physics, city, island, specs = BRIDGE_SPECS) {
    this.physics = physics;
    this.city = city;
    this.island = island;

    this.deck = new GeometryBuilder();
    this.structure = new GeometryBuilder();
    this.cables = new GeometryBuilder();
    this.markings = new GeometryBuilder();

    /** One entry per bridge: `{ id, name, a, b, points }` for the map and for routing. */
    this.spans = [];
    /** Deck centreline waypoints with elevation, for anything that later drives them. */
    this.waypoints = [];

    for (const spec of specs) this._build(spec);

    this.meshes = [];
    const add = (builder, material, name, cast = true) => {
      if (builder.isEmpty) return;
      const mesh = new Mesh(builder.build(), material);
      mesh.name = name;
      mesh.castShadow = cast;
      mesh.receiveShadow = true;
      this.meshes.push(mesh);
    };
    add(this.deck, getMaterial('road'), 'bridgeDeck');
    add(this.structure, getMaterial('concrete'), 'bridgeStructure');
    add(this.cables, getMaterial('metal'), 'bridgeCables');
    add(this.markings, getMaterial('sidewalk'), 'bridgeMarkings', false);

    this.deck = this.structure = this.cables = this.markings = null;
  }

  /* ------------------------------------------------------------------ geometry */

  /**
   * A four-sided prism between two arbitrary 3D points, used for cables and tower legs.
   * `rotatedBox` is yaw-only, and a stay cable is by definition neither level nor
   * vertical, so struts get their own frame built from the direction vector.
   */
  _strut(builder, from, to, radius, tile = 3) {
    const dir = new Vector3().subVectors(to, from);
    const length = dir.length();
    if (length < 0.01) return;
    dir.divideScalar(length);
    // Any vector not parallel to `dir` will do to seed the frame.
    const seed = Math.abs(dir.y) > 0.9 ? new Vector3(1, 0, 0) : new Vector3(0, 1, 0);
    const u = new Vector3().crossVectors(seed, dir).normalize().multiplyScalar(radius);
    const v = new Vector3().crossVectors(dir, u).normalize().multiplyScalar(radius);

    const corner = (p, su, sv) => new Vector3(
      p.x + u.x * su + v.x * sv, p.y + u.y * su + v.y * sv, p.z + u.z * su + v.z * sv,
    );
    const quads = [[1, 1, -1, 1], [-1, 1, -1, -1], [-1, -1, 1, -1], [1, -1, 1, 1]];
    for (const [au, av, bu, bv] of quads) {
      const a0 = corner(from, au, av), b0 = corner(from, bu, bv);
      const a1 = corner(to, au, av), b1 = corner(to, bu, bv);
      const normal = new Vector3(
        u.x * (au + bu) / 2 + v.x * (av + bv) / 2,
        u.y * (au + bu) / 2 + v.y * (av + bv) / 2,
        u.z * (au + bu) / 2 + v.z * (av + bv) / 2,
      ).normalize();
      builder.quad(a0, b0, b1, a1, [0, 0], [radius * 2 / tile, 0],
        [radius * 2 / tile, length / tile], [0, length / tile], normal);
    }
  }

  /**
   * Collider aligned with a deck segment. `addStaticBox` is yaw-only; a bridge approach
   * is pitched, so the box needs a full rotation or the wheels find a staircase.
   */
  _pitchedBox(centre, halfExtents, dir, group = GROUP.BUILDING) {
    const yaw = Math.atan2(dir.x, dir.z);
    const pitch = -Math.asin(Math.max(-1, Math.min(1, dir.y)));
    const q = new Quaternion().setFromEuler(new Euler(pitch, yaw, 0, 'YXZ'));
    this.physics.addStaticBoxQuat(centre, halfExtents, q, group);
  }

  /* ------------------------------------------------------------------- building */

  _build(spec) {
    const { a, b, clearance, halfWidth, rise, arch } = spec;
    const dx = b.x - a.x, dz = b.z - a.z;
    const length = Math.hypot(dx, dz);
    const ux = dx / length, uz = dz / length;
    /*
     * Across-deck direction. The sign matters: the deck quads are wound
     * (left0, left1, right1, right0) the same way the highway winds its ring, and that
     * winding only produces an upward-facing surface if (along x across) points up.
     * With `(-uz, ux)` it points *down* and the whole carriageway renders unlit black -
     * which looks like a material bug and is a handedness bug.
     */
    const px = uz, pz = -ux;

    /** Deck height at parametric position `t`, ramp-flat-ramp with a shallow arch. */
    const deckY = (t) => {
      if (t < rise) return clearance * smooth(t / rise);
      if (t > 1 - rise) return clearance * smooth((1 - t) / rise);
      const m = (t - rise) / (1 - 2 * rise);
      return clearance + Math.sin(m * Math.PI) * arch;
    };

    // Overrun the anchors slightly so the deck definitely meets the street rather than
    // stopping a metre short of it and leaving a lip the wheels catch on.
    const pad = 6 / length;
    const segments = Math.ceil(length / SEGMENT_LENGTH);
    const point = (t) => new Vector3(a.x + dx * t, deckY(t), a.z + dz * t);

    const centreline = [];
    let sincePier = PIER_SPACING;

    for (let i = 0; i < segments; i++) {
      const t0 = -pad + (i / segments) * (1 + pad * 2);
      const t1 = -pad + ((i + 1) / segments) * (1 + pad * 2);
      const c0 = point(Math.min(1, Math.max(0, t0)));
      const c1 = point(Math.min(1, Math.max(0, t1)));
      c0.set(a.x + dx * t0, deckY(Math.min(1, Math.max(0, t0))), a.z + dz * t0);
      c1.set(a.x + dx * t1, deckY(Math.min(1, Math.max(0, t1))), a.z + dz * t1);

      this._deckSpan(c0, c1, px, pz, halfWidth, i);

      const mid = new Vector3((c0.x + c1.x) / 2, (c0.y + c1.y) / 2, (c0.z + c1.z) / 2);
      centreline.push({ x: mid.x, y: mid.y, z: mid.z });
      this.waypoints.push({ x: mid.x, y: mid.y, z: mid.z, bridge: spec.id });

      // Piers only under the approaches: the main span hangs from the towers, which is
      // the whole point of a cable stay, and a pier out there would be 30 m of column
      // standing in a shipping lane.
      const tMid = (t0 + t1) / 2;
      sincePier += c0.distanceTo(c1);
      if (sincePier >= PIER_SPACING && mid.y > 4 && (tMid < rise || tMid > 1 - rise)) {
        this._pier(mid, ux, uz, halfWidth);
        sincePier = 0;
      }
    }

    // Towers straddle the deck where the approach ramps end and the main span begins.
    for (const t of [rise, 1 - rise]) {
      this._tower(spec, point(t), px, pz, ux, uz, deckY, length);
    }

    this.spans.push({
      id: spec.id, name: spec.name, a: { ...a }, b: { ...b },
      length: Math.round(length), clearance, points: centreline,
    });
  }

  /** One segment: running surface, soffit, fascias, kerbs, paint and colliders. */
  _deckSpan(c0, c1, px, pz, halfWidth, index) {
    const dir = new Vector3().subVectors(c1, c0);
    const spanLength = dir.length();
    if (spanLength < 0.01) return;
    dir.divideScalar(spanLength);

    const edge = (c, side) => new Vector3(c.x + px * halfWidth * side, c.y, c.z + pz * halfWidth * side);
    const l0 = edge(c0, -1), r0 = edge(c0, 1), l1 = edge(c1, -1), r1 = edge(c1, 1);
    const up = new Vector3(0, 1, 0);
    const down = new Vector3(0, -1, 0);
    const tile = 7;
    const uv = (p) => [p.x / tile, p.z / tile];

    this.deck.quad(l0, l1, r1, r0, uv(l0), uv(l1), uv(r1), uv(r0), up);

    const drop = (p) => new Vector3(p.x, p.y - DECK_THICKNESS, p.z);
    const dl0 = drop(l0), dr0 = drop(r0), dl1 = drop(l1), dr1 = drop(r1);
    this.structure.quad(dl0, dr0, dr1, dl1, uv(dl0), uv(dr0), uv(dr1), uv(dl1), down);

    const outward = new Vector3(px, 0, pz);
    this.structure.quad(r0, r1, dr1, dr0, [0, 1], [1, 1], [1, 0], [0, 0], outward);
    this.structure.quad(l1, l0, dl0, dl1, [0, 1], [1, 1], [1, 0], [0, 0], outward.clone().negate());

    // Barriers as ribbons rather than boxes: on a 10% approach grade a yaw-only box
    // stands proud of the deck at one end and buried at the other.
    for (const side of [-1, 1]) {
      const b0 = edge(c0, side), b1 = edge(c1, side);
      const t0 = new Vector3(b0.x, b0.y + BARRIER_HEIGHT, b0.z);
      const t1 = new Vector3(b1.x, b1.y + BARRIER_HEIGHT, b1.z);
      const inward = new Vector3(-px * side, 0, -pz * side);
      this.structure.setColor(0xffffff, 0.92);
      this.structure.quad(b0, b1, t1, t0, [0, 0], [spanLength / 3, 0],
        [spanLength / 3, 0.35], [0, 0.35], inward);
      this.structure.quad(b1, b0, t0, t1, [0, 0], [spanLength / 3, 0],
        [spanLength / 3, 0.35], [0, 0.35], inward.clone().negate());
      this.structure.quad(t0, t1,
        new Vector3(t1.x - px * side * BARRIER_THICKNESS, t1.y, t1.z - pz * side * BARRIER_THICKNESS),
        new Vector3(t0.x - px * side * BARRIER_THICKNESS, t0.y, t0.z - pz * side * BARRIER_THICKNESS),
        [0, 0], [spanLength / 3, 0], [spanLength / 3, 0.2], [0, 0.2], up);
      this.structure.resetColor();

      const bc = new Vector3(
        (b0.x + b1.x) / 2 - px * side * BARRIER_THICKNESS / 2,
        (b0.y + b1.y) / 2 + BARRIER_HEIGHT / 2,
        (b0.z + b1.z) / 2 - pz * side * BARRIER_THICKNESS / 2,
      );
      this._pitchedBox(bc, new Vector3(BARRIER_THICKNESS, BARRIER_HEIGHT / 2, spanLength / 2 + 0.8), dir);
    }

    /*
     * Deck slab collider, deliberately over-long and over-wide. Consecutive slabs meet at
     * a pitch break, and an exact-length slab leaves a wedge of nothing at each seam that
     * a wheel raycast falls straight through. Overlapping static boxes are free.
     */
    const centre = new Vector3(
      (c0.x + c1.x) / 2, (c0.y + c1.y) / 2 - DECK_THICKNESS / 2, (c0.z + c1.z) / 2,
    );
    this._pitchedBox(
      centre,
      new Vector3(halfWidth + 0.5, DECK_THICKNESS / 2, spanLength / 2 + 1.4),
      dir,
    );

    if (index % 2 === 0) {
      const lane = new Vector3(
        (c0.x + c1.x) / 2, (c0.y + c1.y) / 2 + 0.03, (c0.z + c1.z) / 2,
      );
      this.markings.quad(
        new Vector3(lane.x - px * 0.16 - dir.x * spanLength * 0.3, lane.y, lane.z - pz * 0.16 - dir.z * spanLength * 0.3),
        new Vector3(lane.x - px * 0.16 + dir.x * spanLength * 0.3, lane.y, lane.z - pz * 0.16 + dir.z * spanLength * 0.3),
        new Vector3(lane.x + px * 0.16 + dir.x * spanLength * 0.3, lane.y, lane.z + pz * 0.16 + dir.z * spanLength * 0.3),
        new Vector3(lane.x + px * 0.16 - dir.x * spanLength * 0.3, lane.y, lane.z + pz * 0.16 - dir.z * spanLength * 0.3),
        [0, 0], [0, 1], [1, 1], [1, 0], new Vector3(0, 1, 0),
      );
    }
  }

  /** Concrete pier from the deck soffit down to whatever is underneath - land or seabed. */
  _pier(mid, ux, uz, halfWidth) {
    const groundY = Math.min(0, this.island.heightAt(mid.x, mid.z));
    const shaft = mid.y - DECK_THICKNESS - groundY;
    if (shaft < 2.5) return;

    this.structure.setColor(0xffffff, 0.84);
    // Head beam across the deck.
    this.structure.rotatedBox(
      mid.x, mid.y - DECK_THICKNESS - 0.5, mid.z,
      halfWidth * 0.7, 0.5, 1.1, -Math.atan2(uz, ux), 3,
    );
    this.structure.cylinder(mid.x, groundY, mid.z, 1.8, shaft - 1.0, 12, 3, false, 1.4);
    this.structure.resetColor();

    this.physics.addStaticBox(
      new Vector3(mid.x, groundY + shaft / 2, mid.z),
      new Vector3(1.9, shaft / 2, 1.9), 0, GROUP.BUILDING,
    );
    // Keep spawners out of the footprint; a pier on land is as solid as a building.
    if (groundY >= -0.5) this.city.props.push({ x: mid.x, z: mid.z, radius: 3.2 });
  }

  /**
   * An A-frame tower with stay cables fanning out over the main span.
   *
   * The cables are anchored at deck level rather than at the barrier, so from the deck
   * they sweep past the windscreen instead of standing in the lane.
   */
  _tower(spec, at, px, pz, ux, uz, deckY, length) {
    const { halfWidth, towerHeight, rise } = spec;
    const baseY = Math.min(0, this.island.heightAt(at.x, at.z));
    const legOffset = halfWidth + 1.6;
    const apexY = at.y + towerHeight;

    this.structure.setColor(0xffffff, 0.88);
    const legs = [];
    for (const side of [-1, 1]) {
      /*
       * Each leg is two segments, not one. A single strut from the foot to the apex
       * leans continuously, so at deck height it has already travelled most of the way
       * inboard and stands squarely in the carriageway - a 3 m column in the middle of
       * the road. The leg is therefore vertical up to the deck, clear of the barrier,
       * and only leans in above it.
       */
      const foot = new Vector3(at.x + px * legOffset * side, baseY, at.z + pz * legOffset * side);
      const knee = new Vector3(foot.x, at.y + BARRIER_HEIGHT + 0.6, foot.z);
      const apex = new Vector3(at.x + px * 1.6 * side, apexY, at.z + pz * 1.6 * side);
      this._strut(this.structure, foot, knee, 1.6, 4);
      this._strut(this.structure, knee, apex, 1.4, 4);
      legs.push(apex);
    }
    // Cross beam just under the apex, tying the legs together.
    this._strut(
      this.structure,
      new Vector3(legs[0].x, apexY - 3, legs[0].z),
      new Vector3(legs[1].x, apexY - 3, legs[1].z),
      0.9, 3,
    );
    this.structure.resetColor();

    // Portal beam tying the legs together above the road. Well clear of the tallest
    // thing that can drive under it - a beam at windscreen height reads as a mistake.
    this.structure.setColor(0xffffff, 0.8);
    this.structure.rotatedBox(
      at.x, at.y + 7, at.z, legOffset + 0.6, 0.6, 1.2, -Math.atan2(uz, ux), 3,
    );
    this.structure.resetColor();

    for (const side of [-1, 1]) {
      this.physics.addStaticBox(
        new Vector3(at.x + px * legOffset * side, baseY + (apexY - baseY) / 2, at.z + pz * legOffset * side),
        new Vector3(1.7, (apexY - baseY) / 2, 1.7), 0, GROUP.BUILDING,
      );
      if (baseY >= -0.5) {
        this.city.props.push({
          x: at.x + px * legOffset * side, z: at.z + pz * legOffset * side, radius: 2.8,
        });
      }
    }

    // Stay cables. `dirSign` points the fan at the middle of the span for the first
    // tower and back towards its own approach for the second.
    const tAt = ((at.x - spec.a.x) * ux + (at.z - spec.a.z) * uz) / length;
    const dirSign = tAt < 0.5 ? 1 : -1;
    const reach = (0.5 - rise) * 0.92;
    const stays = 7;
    for (let i = 1; i <= stays; i++) {
      const t = tAt + dirSign * reach * (i / stays);
      const y = deckY(Math.min(1, Math.max(0, t)));
      const on = new Vector3(spec.a.x + (spec.b.x - spec.a.x) * t, y + 0.9, spec.a.z + (spec.b.z - spec.a.z) * t);
      for (const side of [-1, 1]) {
        const top = new Vector3(at.x + px * 1.6 * side, apexY - 1.5 - i * 1.6, at.z + pz * 1.6 * side);
        const anchor = new Vector3(on.x + px * (halfWidth - 0.5) * side, on.y, on.z + pz * (halfWidth - 0.5) * side);
        this._strut(this.cables, top, anchor, 0.16, 2);
      }
      // Back-stays over the approach keep the tower in balance, and read correctly.
      const bt = tAt - dirSign * reach * (i / stays) * 0.55;
      const by = deckY(Math.min(1, Math.max(0, bt)));
      const back = new Vector3(
        spec.a.x + (spec.b.x - spec.a.x) * bt, by + 0.9, spec.a.z + (spec.b.z - spec.a.z) * bt,
      );
      for (const side of [-1, 1]) {
        const top = new Vector3(at.x + px * 1.6 * side, apexY - 1.5 - i * 1.6, at.z + pz * 1.6 * side);
        const anchor = new Vector3(
          back.x + px * (halfWidth - 0.5) * side, back.y, back.z + pz * (halfWidth - 0.5) * side,
        );
        this._strut(this.cables, top, anchor, 0.13, 2);
      }
    }
  }

  /** Height of the deck at a world point, or null if the point is not over a bridge. */
  deckHeightAt(x, z, tolerance = 12) {
    for (const span of this.spans) {
      const dx = span.b.x - span.a.x, dz = span.b.z - span.a.z;
      const len2 = dx * dx + dz * dz;
      const t = ((x - span.a.x) * dx + (z - span.a.z) * dz) / len2;
      if (t < 0 || t > 1) continue;
      const cx = span.a.x + dx * t, cz = span.a.z + dz * t;
      if (Math.hypot(x - cx, z - cz) > tolerance) continue;
      const i = Math.min(span.points.length - 1, Math.round(t * (span.points.length - 1)));
      return span.points[i].y;
    }
    return null;
  }

  /** Sea level, exported for anything checking clearance. */
  static get seaLevel() { return SEA_LEVEL; }
}
