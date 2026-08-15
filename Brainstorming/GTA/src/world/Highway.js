/**
 * Elevated ring highway.
 *
 * A raised expressway circling the city on concrete piers, with four ramps spiralling down
 * to street level. It gives the map a second layer: somewhere to open the throttle, a
 * shaded underside to drive through, and a landmark visible from most of the island.
 *
 * The highway is deliberately NOT added to the ground road graph. That graph is 2D - it
 * has no elevation - and every consumer of it (traffic routing, police pursuit, mission
 * placement, pedestrian spawns, parked cars) assumes any node is reachable from any other
 * at ground level. Splicing an elevated ring into it would have police pathing straight
 * off a viaduct. The highway instead carries its own waypoint ring for its own traffic.
 */

import { Mesh, Vector3, MathUtils } from 'three/webgpu';
import { GeometryBuilder, colliderYaw } from './GeometryBuilder.js';
import { getMaterial } from '../render/Materials.js';
import { GROUP } from '../physics/Physics.js';

const DECK_HALF_WIDTH = 11;
const DECK_THICKNESS = 0.9;
const BARRIER_HEIGHT = 0.95;
const BARRIER_THICKNESS = 0.45;
const PIER_EVERY = 3;

export class Highway {
  /**
   * @param {import('../physics/Physics.js').Physics} physics
   * @param {import('./City.js').City} city
   * @param {object} opts
   */
  constructor(physics, city, {
    radius = 640, height = 9.5, segments = 96, rampCount = 4, rampLength = 165,
  } = {}) {
    this.physics = physics;
    this.city = city;
    this.radius = radius;
    this.height = height;
    this.segments = segments;

    this.deck = new GeometryBuilder();
    this.structure = new GeometryBuilder();
    this.markings = new GeometryBuilder();

    /** Centreline waypoints around the ring, for highway traffic. */
    this.waypoints = [];
    /** Where ramps meet the ground, so missions and spawns can use them. */
    this.rampFeet = [];

    // Ramp bearings are needed while building the ring, so the outer barrier can be
    // left open where a ramp branches off - otherwise the ramps are walled off from the
    // road they are supposed to serve.
    this.rampAngles = [];
    for (let i = 0; i < rampCount; i++) {
      this.rampAngles.push((i / rampCount) * Math.PI * 2 + Math.PI / rampCount);
    }

    this._buildRing();
    for (const angle of this.rampAngles) this._buildRamp(angle, rampLength);

    this.meshes = [];
    const add = (builder, material, name, cast = true) => {
      if (builder.isEmpty) return;
      const mesh = new Mesh(builder.build(), material);
      mesh.name = name;
      mesh.castShadow = cast;
      mesh.receiveShadow = true;
      this.meshes.push(mesh);
    };
    add(this.deck, getMaterial('road'), 'highwayDeck');
    add(this.structure, getMaterial('concrete'), 'highwayStructure');
    add(this.markings, getMaterial('sidewalk'), 'highwayMarkings', false);

    this.deck = null;
    this.structure = null;
    this.markings = null;
  }

  _pointAt(angle, offset = 0, y = this.height) {
    const r = this.radius + offset;
    return new Vector3(Math.cos(angle) * r, y, Math.sin(angle) * r);
  }

  /**
   * The ring deck. Built segment by segment as quads rather than as an extruded curve, so
   * each span can carry its own piers and its own collider without any of them needing to
   * know about the curve as a whole.
   */
  _buildRing() {
    const step = (Math.PI * 2) / this.segments;
    for (let i = 0; i < this.segments; i++) {
      const a0 = i * step;
      const a1 = (i + 1) * step;

      const inner0 = this._pointAt(a0, -DECK_HALF_WIDTH);
      const outer0 = this._pointAt(a0, DECK_HALF_WIDTH);
      const inner1 = this._pointAt(a1, -DECK_HALF_WIDTH);
      const outer1 = this._pointAt(a1, DECK_HALF_WIDTH);

      this._deckSpan(inner0, outer0, inner1, outer1, i);

      const mid = this._pointAt((a0 + a1) / 2);
      this.waypoints.push({ x: mid.x, y: mid.y, z: mid.z, angle: (a0 + a1) / 2 });

      if (i % PIER_EVERY === 0) this._pier(mid, (a0 + a1) / 2);
    }
  }

  /** One span of deck: road surface, soffit, kerb barriers, lane paint and collider. */
  _deckSpan(inner0, outer0, inner1, outer1, index) {
    const up = new Vector3(0, 1, 0);
    const down = new Vector3(0, -1, 0);
    const tile = 7;
    const uv = (p) => [p.x / tile, p.z / tile];

    // Running surface.
    this.deck.quad(inner0, inner1, outer1, outer0, uv(inner0), uv(inner1), uv(outer1), uv(outer0), up);

    // Soffit, one deck thickness below - visible whenever you drive underneath.
    const drop = (p) => new Vector3(p.x, p.y - DECK_THICKNESS, p.z);
    const si0 = drop(inner0), so0 = drop(outer0), si1 = drop(inner1), so1 = drop(outer1);
    this.structure.quad(si0, so0, so1, si1, uv(si0), uv(so0), uv(so1), uv(si1), down);

    // Outer fascia beams on both edges, which is what gives a viaduct its silhouette.
    const fascia = (a, b, aLow, bLow, normal) => {
      this.structure.quad(a, b, bLow, aLow, [0, 1], [1, 1], [1, 0], [0, 0], normal);
    };
    const outward = new Vector3(outer0.x, 0, outer0.z).normalize();
    fascia(outer0, outer1, so0, so1, outward);
    fascia(inner1, inner0, si1, si0, outward.clone().negate());

    // Barriers.
    const mid0 = new Vector3((inner0.x + outer0.x) / 2, this.height, (inner0.z + outer0.z) / 2);
    const mid1 = new Vector3((inner1.x + outer1.x) / 2, this.height, (inner1.z + outer1.z) / 2);
    const yaw = Math.atan2(mid1.x - mid0.x, mid1.z - mid0.z);
    const spanLength = mid0.distanceTo(mid1);
    const cx = (mid0.x + mid1.x) / 2, cz = (mid0.z + mid1.z) / 2;
    const nx = Math.cos((yaw)), nz = Math.sin(yaw);
    void nx; void nz;
    const radial = new Vector3(cx, 0, cz).normalize();

    const spanAngle = Math.atan2(cz, cx);
    const atRamp = this.rampAngles.some((ra) => {
      let d = Math.abs(((spanAngle - ra + Math.PI * 3) % (Math.PI * 2)) - Math.PI);
      return d < 0.045;
    });

    for (const side of [-1, 1]) {
      // side = +1 is the outer kerb; leave it open where a ramp joins.
      if (side === 1 && atRamp) continue;
      const bx = cx + radial.x * DECK_HALF_WIDTH * side;
      const bz = cz + radial.z * DECK_HALF_WIDTH * side;
      this.structure.setColor(0xffffff, 0.9);
      this.structure.rotatedBox(
        bx, this.height + BARRIER_HEIGHT / 2, bz,
        BARRIER_THICKNESS / 2, BARRIER_HEIGHT / 2, spanLength / 2 + 0.2,
        -yaw, 2.5,
      );
      this.structure.resetColor();
      this.physics.addStaticBox(
        new Vector3(bx, this.height + BARRIER_HEIGHT / 2, bz),
        new Vector3(BARRIER_THICKNESS / 2, BARRIER_HEIGHT / 2, spanLength / 2 + 1.2),
        colliderYaw(-yaw), GROUP.BUILDING,
      );
    }

    /*
     * Deck collider: a thin slab under the running surface.
     *
     * The ring is a polygon, so consecutive slabs meet at an angle and leave wedge-shaped
     * gaps towards the outer edge - exactly where the outer lane runs. A wheel raycast
     * that lands in one finds no ground and the car drops off the viaduct. The slabs are
     * therefore deliberately over-long and over-wide so they overlap at every seam;
     * overlapping static boxes cost nothing.
     */
    this.physics.addStaticBox(
      new Vector3(cx, this.height - DECK_THICKNESS / 2, cz),
      new Vector3(DECK_HALF_WIDTH + 0.6, DECK_THICKNESS / 2, spanLength / 2 + 1.6),
      colliderYaw(-yaw), GROUP.BUILDING,
    );

    // Dashed lane line down the middle of each carriageway.
    if (index % 2 === 0) {
      for (const lane of [-DECK_HALF_WIDTH / 2, DECK_HALF_WIDTH / 2]) {
        const lx = cx + radial.x * lane;
        const lz = cz + radial.z * lane;
        this.markings.rotatedBox(
          lx, this.height + 0.02, lz, 0.14, 0.01, spanLength * 0.3, -yaw, 1,
          { sides: false },
        );
      }
    }
  }

  /** Concrete pier down to the ground, with a splayed head under the deck. */
  _pier(mid, angle) {
    const groundY = 0;
    const shaftHeight = this.height - DECK_THICKNESS - groundY;
    if (shaftHeight < 2) return;

    this.structure.setColor(0xffffff, 0.82);
    // Head beam spanning the deck width.
    this.structure.rotatedBox(
      mid.x, this.height - DECK_THICKNESS - 0.45, mid.z,
      DECK_HALF_WIDTH * 0.72, 0.45, 0.9, -(angle + Math.PI / 2), 3,
    );
    // Tapered shaft.
    this.structure.cylinder(mid.x, groundY, mid.z, 1.35, shaftHeight - 0.9, 10, 3, false, 1.0);
    // Footing.
    this.structure.box(
      new Vector3(mid.x - 2.1, groundY - 0.1, mid.z - 2.1),
      new Vector3(mid.x + 2.1, groundY + 0.45, mid.z + 2.1), 3,
    );
    this.structure.resetColor();

    this.physics.addStaticBox(
      new Vector3(mid.x, groundY + shaftHeight / 2, mid.z),
      new Vector3(1.5, shaftHeight / 2, 1.5), 0, GROUP.BUILDING,
    );
    this.city.props.push({ x: mid.x, z: mid.z, radius: 2.6 });
  }

  /**
   * A ramp running radially outward and down from the ring to street level.
   *
   * Radial rather than tangential on purpose: it crosses the ring cleanly at a right
   * angle, so the join needs no curve blending, and it lands pointing away from the city
   * where there is room for it to meet a street.
   */
  _buildRamp(angle, length) {
    const halfWidth = 6.5;
    const steps = 18;
    const dirX = Math.cos(angle), dirZ = Math.sin(angle);
    // Perpendicular, for the ramp's own width.
    const px = -dirZ, pz = dirX;

    const startR = this.radius + DECK_HALF_WIDTH - 1;
    const groundY = 0.1;

    let prevL = null, prevR = null, prevY = 0;
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const r = startR + t * length;
      // Ease the gradient at both ends so a car does not launch off the transition.
      const eased = t * t * (3 - 2 * t);
      const y = MathUtils.lerp(this.height, groundY, eased);
      const cx = dirX * r, cz = dirZ * r;
      const left = new Vector3(cx + px * halfWidth, y, cz + pz * halfWidth);
      const right = new Vector3(cx - px * halfWidth, y, cz - pz * halfWidth);

      if (prevL) {
        const tile = 7;
        const uv = (p) => [p.x / tile, p.z / tile];
        const up = new Vector3(0, 1, 0);
        this.deck.quad(prevL, left, right, prevR, uv(prevL), uv(left), uv(right), uv(prevR), up);

        // Soffit and collider for this ramp span.
        const midX = (prevL.x + prevR.x + left.x + right.x) / 4;
        const midZ = (prevL.z + prevR.z + left.z + right.z) / 4;
        const midY = (prevY + y) / 2;
        const spanLength = Math.hypot(left.x - prevL.x, left.z - prevL.z);
        const yaw = Math.atan2(dirX, dirZ);

        this.structure.setColor(0xffffff, 0.85);
        this.structure.rotatedBox(
          midX, midY - DECK_THICKNESS / 2, midZ,
          halfWidth, DECK_THICKNESS / 2, spanLength / 2 + 0.2, -yaw, 4,
        );
        // Barriers along both edges of the ramp.
        for (const side of [-1, 1]) {
          this.structure.rotatedBox(
            midX + px * halfWidth * side, midY + BARRIER_HEIGHT / 2, midZ + pz * halfWidth * side,
            BARRIER_THICKNESS / 2, BARRIER_HEIGHT / 2, spanLength / 2 + 0.2, -yaw, 2.5,
          );
          this.physics.addStaticBox(
            new Vector3(
              midX + px * halfWidth * side, midY + BARRIER_HEIGHT / 2, midZ + pz * halfWidth * side,
            ),
            new Vector3(BARRIER_THICKNESS / 2, BARRIER_HEIGHT / 2, spanLength / 2 + 0.2),
            colliderYaw(-yaw), GROUP.BUILDING,
          );
        }
        this.structure.resetColor();

        /*
         * The ramp collider is a flat slab tilted to match the gradient. Rapier cuboids
         * only take a yaw here, so the slope is approximated by stacking short level
         * slabs - at this segment length the step is a couple of centimetres, well inside
         * what the suspension absorbs.
         */
        this.physics.addStaticBox(
          new Vector3(midX, midY - DECK_THICKNESS / 2, midZ),
          new Vector3(halfWidth, DECK_THICKNESS / 2 + 0.15, spanLength / 2 + 0.3),
          colliderYaw(-yaw), GROUP.BUILDING,
        );

        // Support piers under the higher part of the ramp.
        if (i % 4 === 0 && midY > 2.5) {
          this.structure.setColor(0xffffff, 0.8);
          this.structure.cylinder(midX, 0, midZ, 1.0, midY - DECK_THICKNESS, 8, 3, false, 0.8);
          this.structure.resetColor();
          this.physics.addStaticBox(
            new Vector3(midX, (midY - DECK_THICKNESS) / 2, midZ),
            new Vector3(1.1, (midY - DECK_THICKNESS) / 2, 1.1), 0, GROUP.BUILDING,
          );
        }
      }
      prevL = left;
      prevR = right;
      prevY = y;
    }

    this.rampFeet.push({
      x: dirX * (startR + length), z: dirZ * (startR + length), angle,
    });
  }

  /** Ring waypoints for the minimap to draw. */
  get ringPoints() { return this.waypoints; }

  /**
   * A road graph for the ring, exposing the same surface the traffic AI already consumes
   * from `RoadNetwork`. Building a parallel graph rather than adding elevation to the
   * city's one keeps every existing consumer - police pathing, missions, pedestrian
   * spawns - working on a purely ground-level graph, while letting the same autopilot
   * drive up here unchanged.
   */
  buildNetwork() {
    const nodes = this.waypoints.map((wp, i) => ({
      id: i, x: wp.x, y: wp.y, z: wp.z, edges: [],
    }));
    const edges = [];
    const type = { width: DECK_HALF_WIDTH * 2, lanes: 2, speed: 38 };

    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      const b = nodes[(i + 1) % nodes.length];
      const dx = b.x - a.x, dz = b.z - a.z;
      const length = Math.hypot(dx, dz);
      const edge = {
        id: edges.length, a: a.id, b: b.id, type, axis: 'ring', length,
        dirX: dx / length, dirZ: dz / length,
      };
      edges.push(edge);
      a.edges.push(edge.id);
      b.edges.push(edge.id);
    }

    const network = {
      nodes,
      edges,
      elevated: true,
      deckY: this.height,

      otherEnd(edge, nodeId) { return edge.a === nodeId ? edge.b : edge.a; },

      /** Only ever one way onward round a ring, which keeps traffic flowing one way. */
      exitsFrom(nodeId, fromEdgeId) {
        const node = nodes[nodeId];
        const onward = node.edges.filter((id) => id !== fromEdgeId);
        return onward.length ? onward : node.edges.slice();
      },

      /*
       * Lanes straddle the centreline. Offsets are measured to the right of travel,
       * which on a counter-clockwise ring points *inward* - so a one-sided offset put
       * the outer lane hard against the inner barrier, where cars ground to a halt.
       * Straddling keeps both lanes eight metres clear of either barrier.
       */
      laneOffset(_type, lane = 0) { return (lane - 0.5) * 5.4; },

      lanePointOnEdge(e, t, forward, lane = 0) {
        const a = nodes[e.a], b = nodes[e.b];
        const from = forward ? a : b, to = forward ? b : a;
        const dx = to.x - from.x, dz = to.z - from.z;
        const len = Math.hypot(dx, dz) || 1;
        const ux = dx / len, uz = dz / len;
        const rx = -uz, rz = ux;
        const off = network.laneOffset(e.type, lane);
        return {
          x: from.x + dx * t + rx * off,
          y: from.y + (to.y - from.y) * t,
          z: from.z + dz * t + rz * off,
          heading: Math.atan2(ux, uz),
          dirX: ux, dirZ: uz,
          edge: e, forward, lane,
        };
      },

      nearestNode(x, z) {
        let best = null, bestD = Infinity;
        for (const n of nodes) {
          const d = (n.x - x) ** 2 + (n.z - z) ** 2;
          if (d < bestD) { bestD = d; best = n; }
        }
        return best;
      },

      nearestOnRoad(x, z) {
        let best = null, bestD = Infinity;
        for (const e of edges) {
          const a = nodes[e.a], b = nodes[e.b];
          const vx = b.x - a.x, vz = b.z - a.z;
          const len2 = vx * vx + vz * vz;
          let t = ((x - a.x) * vx + (z - a.z) * vz) / len2;
          t = t < 0 ? 0 : t > 1 ? 1 : t;
          const px = a.x + vx * t, pz = a.z + vz * t;
          const d = (px - x) ** 2 + (pz - z) ** 2;
          if (d < bestD) { bestD = d; best = { edge: e, t, x: px, z: pz, distance: Math.sqrt(d) }; }
        }
        return best;
      },
    };

    this.network = network;
    return network;
  }
}
