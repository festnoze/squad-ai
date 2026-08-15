/**
 * Mission framework.
 *
 * A mission is a list of objectives, each a small declarative record the runtime knows
 * how to evaluate and how to render. Keeping objectives data rather than code means a new
 * mission is a few lines at the bottom of this file, and the HUD, map blips, world markers
 * and completion logic all come for free.
 *
 * Objective types:
 *   goto      - reach a position (on foot or in anything)
 *   drive     - reach a position while in a road vehicle
 *   sail      - reach a position while in a boat
 *   steal     - get into any vehicle (optionally of a given class)
 *   deliver   - reach a position while driving a specific vehicle instance
 *   wait      - hold position for N seconds
 *   collect   - pick up N scattered pickups
 *
 * Any objective may carry `timeLimit` (seconds) to make it a race.
 */

import {
  Group, Mesh, CylinderGeometry, RingGeometry, MeshBasicMaterial, Color,
  DoubleSide, Vector3, MathUtils,
} from 'three/webgpu';

export const MISSION_STATE = {
  AVAILABLE: 'available',
  ACTIVE: 'active',
  COMPLETE: 'complete',
  FAILED: 'failed',
};

/* ------------------------------------------------------------------- markers */

const markerGeo = new CylinderGeometry(2.2, 2.2, 14, 20, 1, true);
const ringGeo = new RingGeometry(2.4, 3.1, 28);
ringGeo.rotateX(-Math.PI / 2);

/** A shaft of coloured light with a spinning ground ring - the GTA objective marker. */
class Marker {
  constructor(colour = 0xffb703) {
    this.group = new Group();
    const c = new Color(colour);
    this.pillar = new Mesh(markerGeo, new MeshBasicMaterial({
      color: c, transparent: true, opacity: 0.24, side: DoubleSide, depthWrite: false,
    }));
    this.pillar.position.y = 7;
    this.ring = new Mesh(ringGeo, new MeshBasicMaterial({
      color: c, transparent: true, opacity: 0.75, side: DoubleSide, depthWrite: false,
    }));
    this.ring.position.y = 0.08;
    this.group.add(this.pillar, this.ring);
    this.group.renderOrder = 20;
    this.group.visible = false;
  }

  setColour(colour) {
    this.pillar.material.color.set(colour);
    this.ring.material.color.set(colour);
  }

  place(x, y, z, radius = 3) {
    this.group.position.set(x, y, z);
    this.group.scale.setScalar(Math.max(0.6, radius / 3));
    this.group.visible = true;
  }

  hide() { this.group.visible = false; }

  update(dt, t) {
    if (!this.group.visible) return;
    this.ring.rotation.z += dt * 1.4;
    // Gentle breathing so the marker reads as interactive rather than as scenery.
    const pulse = 0.6 + Math.sin(t * 2.4) * 0.18;
    this.ring.material.opacity = pulse;
    this.pillar.material.opacity = 0.16 + pulse * 0.14;
  }
}

/* ----------------------------------------------------------------- definitions */

/**
 * Build the mission list. Positions are resolved from the world so missions always land
 * on real streets, real docks and real water rather than hard-coded coordinates that
 * could end up inside a building.
 *
 * @param {object} world `{ city, island, ocean }`
 */
export function buildMissions(world) {
  const { city, island } = world;
  const net = city.network;

  /** Nearest road node to a point, as a plain {x,z}. */
  const road = (x, z) => {
    const n = net.nearestNode(x, z);
    return { x: n.x, z: n.z };
  };
  /** Open water near a point. */
  const water = (x, z) => island.nearestWater(x, z) ?? { x, z };

  const downtown = road(60, 60);
  const midtown = road(-420, 380);
  const suburbs = road(700, 620);
  const industrial = road(-780, -720);
  const northShore = road(-260, -980);
  const eastSide = road(880, 180);
  const parkSide = city.parks.length
    ? road(city.parks[Math.floor(city.parks.length / 2)].cx, city.parks[Math.floor(city.parks.length / 2)].cz)
    : road(200, -200);

  const harbour = water(island.bay.x, island.bay.z);
  const marinaWater = water(island.marina.x, island.marina.z);
  const openSea = water(island.bay.x + 700, island.bay.z - 500);

  return [
    {
      id: 'first-ride',
      name: 'First Ride',
      brief: 'Wheels first. Everything else follows.',
      reward: 750,
      start: downtown,
      objectives: [
        { type: 'steal', label: 'Get in any car' },
        { type: 'drive', at: midtown, radius: 12, label: 'Drive to the Midtown lockup' },
      ],
    },
    {
      id: 'courier',
      name: 'Hot Courier',
      brief: 'A package, a clock, and no questions.',
      reward: 1400,
      start: midtown,
      objectives: [
        { type: 'steal', label: 'Get a car' },
        { type: 'drive', at: eastSide, radius: 13, label: 'Make the East Side drop', timeLimit: 115 },
      ],
    },
    {
      id: 'dockside',
      name: 'Dockside Pickup',
      brief: 'Down to the water. Bring something back.',
      reward: 1900,
      start: industrial,
      objectives: [
        { type: 'drive', at: road(island.bay.x - 260, island.bay.z + 220), radius: 16, label: 'Drive to the docks' },
        { type: 'goto', at: harbour, radius: 22, label: 'Find the boat', onFoot: false },
        { type: 'sail', at: openSea, radius: 40, label: 'Take the boat out past the headland' },
      ],
    },
    {
      id: 'harbour-run',
      name: 'Harbour Run',
      brief: 'Customs are asleep. Move it before they wake.',
      reward: 2600,
      start: road(island.bay.x - 220, island.bay.z + 180),
      objectives: [
        { type: 'sail', at: marinaWater, radius: 45, label: 'Run the cargo to the marina', timeLimit: 210 },
      ],
    },
    {
      id: 'grand-tour',
      name: 'The Grand Tour',
      brief: 'Four corners of the island. One tank of fuel.',
      reward: 3200,
      start: downtown,
      objectives: [
        { type: 'steal', label: 'Get a fast car' },
        { type: 'drive', at: northShore, radius: 18, label: 'North shore', timeLimit: 150 },
        { type: 'drive', at: eastSide, radius: 18, label: 'East side', timeLimit: 150 },
        { type: 'drive', at: suburbs, radius: 18, label: 'The suburbs', timeLimit: 150 },
        { type: 'drive', at: industrial, radius: 18, label: 'Back to the yards', timeLimit: 160 },
      ],
    },
    {
      id: 'park-life',
      name: 'Park Life',
      brief: 'Somebody dropped their stash across the park.',
      reward: 1500,
      start: parkSide,
      objectives: [
        { type: 'collect', around: parkSide, count: 6, spread: 90, label: 'Collect the packages' },
      ],
    },
    {
      id: 'night-shift',
      name: 'Night Shift',
      brief: 'Wait for the handover. Do not be early.',
      reward: 2100,
      start: eastSide,
      objectives: [
        { type: 'drive', at: suburbs, radius: 14, label: 'Get to the meet' },
        { type: 'wait', seconds: 12, label: 'Wait for the contact' },
        { type: 'drive', at: downtown, radius: 14, label: 'Get clear', timeLimit: 130 },
      ],
    },
    {
      id: 'the-long-way',
      name: 'The Long Way Home',
      brief: 'Land, then water, then land again.',
      reward: 4200,
      start: suburbs,
      objectives: [
        { type: 'steal', label: 'Get a car' },
        { type: 'drive', at: road(island.marina.x + 240, island.marina.z - 180), radius: 16, label: 'Drive to the marina' },
        { type: 'sail', at: harbour, radius: 45, label: 'Sail round to the harbour', timeLimit: 260 },
        { type: 'goto', at: road(island.bay.x - 240, island.bay.z + 200), radius: 16, label: 'Meet the buyer ashore' },
      ],
    },
  ];
}

/* -------------------------------------------------------------------- runtime */

export class MissionManager {
  /**
   * @param {object} deps `{ scene, player, traffic, city, island, ocean, hud }`
   */
  constructor({ scene, player, traffic, city, island, ocean, hud }) {
    this.scene = scene;
    this.player = player;
    this.traffic = traffic;
    this.city = city;
    this.island = island;
    this.ocean = ocean;
    this.hud = hud;

    this.missions = buildMissions({ city, island, ocean });
    for (const m of this.missions) {
      m.state = MISSION_STATE.AVAILABLE;
    }
    this._separateStarts();

    this.active = null;
    this.objectiveIndex = 0;
    this.timer = 0;
    this.waitTimer = 0;
    this.completed = 0;
    this.earned = 0;
    this.pickups = [];
    this.time = 0;

    this.group = new Group();
    this.group.name = 'missions';
    scene.add(this.group);

    // One marker for the current objective, one per available mission start.
    this.objectiveMarker = new Marker(0xffb703);
    this.group.add(this.objectiveMarker.group);
    this.startMarkers = new Map();
    for (const m of this.missions) {
      const marker = new Marker(0x4cc9f0);
      marker.place(m.start.x, 0.2, m.start.z, 4);
      this.group.add(marker.group);
      this.startMarkers.set(m.id, marker);
    }

    this._v = new Vector3();
  }

  /**
   * Several missions naturally resolve to the same district, and two start markers in
   * the same spot means one of them can never be triggered. Nudge duplicates onto
   * nearby road nodes so every mission is reachable.
   */
  _separateStarts() {
    const MIN_GAP = 45;
    const placed = [];
    const nodes = this.city.network.nodes;
    for (const m of this.missions) {
      let start = m.start;
      let guard = 0;
      while (placed.some((p) => Math.hypot(p.x - start.x, p.z - start.z) < MIN_GAP) && guard < 40) {
        // Walk outward through nearby road nodes until we find clear space.
        const candidates = nodes
          .map((n) => ({ n, d: Math.hypot(n.x - m.start.x, n.z - m.start.z) }))
          .filter((c) => c.d > MIN_GAP * (guard + 1) && c.d < MIN_GAP * (guard + 3))
          .sort((a, b) => a.d - b.d);
        if (!candidates.length) break;
        start = { x: candidates[0].n.x, z: candidates[0].n.z };
        guard++;
      }
      m.start = start;
      placed.push(start);
    }
  }

  /** Blips for the map: available mission starts, plus the live objective. */
  get blips() {
    const out = [];
    if (this.active) {
      const o = this.currentObjective;
      const at = this._objectivePosition(o);
      if (at) out.push({ x: at.x, z: at.z });
    } else {
      for (const m of this.missions) {
        if (m.state === MISSION_STATE.AVAILABLE) out.push({ x: m.start.x, z: m.start.z });
      }
    }
    return out;
  }

  get currentObjective() {
    return this.active ? this.active.objectives[this.objectiveIndex] : null;
  }

  _objectivePosition(objective) {
    if (!objective) return null;
    if (objective.at) return objective.at;
    if (objective.type === 'collect') {
      const next = this.pickups.find((p) => !p.taken);
      return next ? { x: next.x, z: next.z } : null;
    }
    return null;
  }

  /** Position the player is judged from - the vehicle when driving. */
  _playerPoint(out) {
    const car = this.traffic.playerVehicle;
    if (car) {
      const t = car.body.translation();
      return out.set(t.x, t.y, t.z);
    }
    return out.copy(this.player.position);
  }

  start(mission) {
    this.active = mission;
    mission.state = MISSION_STATE.ACTIVE;
    this.objectiveIndex = 0;
    this.startMarkers.get(mission.id)?.hide();
    this.hud.say(`${mission.name} - ${mission.brief}`, 5);
    this._beginObjective();
  }

  _beginObjective() {
    const o = this.currentObjective;
    if (!o) return;
    this.timer = o.timeLimit ?? 0;
    this.waitTimer = o.seconds ?? 0;

    if (o.type === 'collect') this._spawnPickups(o);

    const at = this._objectivePosition(o);
    if (at) {
      const y = this._groundY(at.x, at.z);
      this.objectiveMarker.setColour(o.type === 'sail' ? 0x63b3d6 : 0xffb703);
      this.objectiveMarker.place(at.x, y, at.z, o.radius ?? 6);
    } else {
      this.objectiveMarker.hide();
    }
    this.hud.setObjective(this.active.name, o.label);
  }

  _groundY(x, z) {
    const h = this.island ? this.island.heightAt(x, z) : 0;
    return h < this.ocean.level ? this.ocean.level + 0.1 : h + 0.2;
  }

  _spawnPickups(objective) {
    this._clearPickups();
    const { around, count, spread } = objective;
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2 + Math.random() * 0.6;
      const r = spread * (0.35 + Math.random() * 0.65);
      const x = around.x + Math.cos(angle) * r;
      const z = around.z + Math.sin(angle) * r;
      const marker = new Marker(0x57cc99);
      marker.place(x, this._groundY(x, z), z, 2.4);
      this.group.add(marker.group);
      this.pickups.push({ x, z, taken: false, marker });
    }
  }

  _clearPickups() {
    for (const p of this.pickups) {
      p.marker.group.removeFromParent();
    }
    this.pickups.length = 0;
  }

  fail(reason) {
    if (!this.active) return;
    const mission = this.active;
    mission.state = MISSION_STATE.AVAILABLE;
    this.hud.say(`${mission.name} failed - ${reason}`, 4);
    this.startMarkers.get(mission.id)?.place(mission.start.x, 0.2, mission.start.z, 4);
    this._endMission();
  }

  _complete() {
    const mission = this.active;
    mission.state = MISSION_STATE.COMPLETE;
    this.completed++;
    this.earned += mission.reward;
    this.hud.say(`${mission.name} complete  +$${mission.reward.toLocaleString('en-US')}`, 5);
    this.onReward?.(mission.reward);
    this._endMission();
  }

  _endMission() {
    this.active = null;
    this.objectiveIndex = 0;
    this.objectiveMarker.hide();
    this._clearPickups();
    this.hud.setObjective(null);
  }

  _advance() {
    this.objectiveIndex++;
    if (this.objectiveIndex >= this.active.objectives.length) this._complete();
    else {
      this.hud.say('Objective complete', 1.6);
      this._beginObjective();
    }
  }

  /**
   * @param {number} dt
   */
  update(dt) {
    this.time += dt;
    this.objectiveMarker.update(dt, this.time);
    for (const m of this.startMarkers.values()) m.update(dt, this.time);
    for (const p of this.pickups) p.marker.update(dt, this.time);

    const point = this._playerPoint(this._v);

    if (!this.active) {
      // Walk or drive into a start marker to begin.
      for (const m of this.missions) {
        if (m.state !== MISSION_STATE.AVAILABLE) continue;
        if (Math.hypot(point.x - m.start.x, point.z - m.start.z) < 6) {
          this.start(m);
          break;
        }
      }
      return;
    }

    const o = this.currentObjective;
    if (o.timeLimit) {
      this.timer -= dt;
      if (this.timer <= 0) { this.fail('out of time'); return; }
    }

    const car = this.traffic.playerVehicle;
    const inBoat = !!car?.isBoat;
    const inCar = !!car && !car.isBoat;

    switch (o.type) {
      case 'steal':
        if (inCar) this._advance();
        break;

      case 'wait': {
        const at = this._objectivePosition(o);
        const near = !at || Math.hypot(point.x - at.x, point.z - at.z) < (o.radius ?? 14);
        if (near) {
          this.waitTimer -= dt;
          if (this.waitTimer <= 0) this._advance();
        }
        break;
      }

      case 'collect': {
        for (const p of this.pickups) {
          if (p.taken) continue;
          if (Math.hypot(point.x - p.x, point.z - p.z) < 4.5) {
            p.taken = true;
            p.marker.hide();
            const left = this.pickups.filter((q) => !q.taken).length;
            this.hud.say(left ? `${left} to go` : 'All collected', 1.8);
            const next = this._objectivePosition(o);
            if (next) this.objectiveMarker.place(next.x, this._groundY(next.x, next.z), next.z, 2.6);
          }
        }
        if (this.pickups.every((p) => p.taken)) this._advance();
        break;
      }

      default: {
        // Positional objectives: goto / drive / sail / deliver.
        const at = o.at;
        if (!at) break;
        const distance = Math.hypot(point.x - at.x, point.z - at.z);
        if (distance > (o.radius ?? 10)) break;
        if (o.type === 'drive' && !inCar) {
          this.hud.setPrompt(null);
          break;
        }
        if (o.type === 'sail' && !inBoat) break;
        this._advance();
        break;
      }
    }
  }

  /** HUD line for the current objective, including any countdown. */
  get statusLine() {
    if (!this.active) return null;
    const o = this.currentObjective;
    if (!o) return null;
    if (o.timeLimit) {
      const s = Math.max(0, this.timer);
      return `${o.label}  ${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
    }
    if (o.type === 'wait' && this.waitTimer > 0 && this.waitTimer < (o.seconds ?? 0)) {
      return `${o.label}  ${Math.ceil(this.waitTimer)}s`;
    }
    return o.label;
  }

  /** Distance to the current objective, for the HUD arrow. */
  get distanceToObjective() {
    const at = this._objectivePosition(this.currentObjective);
    if (!at) return null;
    const p = this._playerPoint(this._v);
    return Math.hypot(p.x - at.x, p.z - at.z);
  }
}

export { MathUtils };
