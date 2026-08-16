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
 *   chase     - run down a fleeing AI car and wreck it or force it to a stop
 *   defend    - hold a point through N waves of hostiles
 *   race      - pass a ring of water checkpoints in order, against a ghost time
 *
 * Any objective may carry `timeLimit` (seconds) to make it a race.
 *
 * The three templates added last are deliberately thin: they own no new AI, no new
 * spawner and no new reward path. `chase` hands its quarry to the ordinary traffic
 * autopilot and reads the vehicle damage the collision and weapon systems already apply;
 * `defend` calls the same `spawnPolice` the wanted system dispatches with, but reports no
 * heat, so a siege never costs the player stars; `race` is the `sail` proximity test in a
 * loop with a split timer on top. Everything still ends through `_advance` / `fail`, which
 * is what keeps completion, payout and the return-to-pool behaviour identical across all
 * fourteen missions.
 *
 * Every template has a way to lose that is not just the clock, because an objective whose
 * only failure is a countdown teaches the player nothing about how to play it: a chase is
 * lost when the quarry outruns you, a siege when you leave the ground you agreed to hold,
 * a race when you abandon the boat.
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

/** Objective marker tint per type; anything unlisted takes the default amber. */
const MARKER_COLOUR = {
  sail: 0x63b3d6,
  race: 0x63b3d6,
  chase: 0xe8503a,
  defend: 0xf07f2a,
};

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

/* ------------------------------------------------------------- chase template */

/**
 * A balanced `chase` objective record.
 *
 * Exported because the chase is the one template meant to be reused outside the story
 * chain - vigilante side hustles are a chase with a different label and a different
 * payer. Everything the template needs is in the record, so a caller that never touches
 * this file can author one; the defaults below are the tuning, not the mechanism.
 *
 * `escape` and `fleeSpeed` are a pair and have to be tuned together, because the ring is
 * only a rule if the runner can actually reach it, and for a long time this one could not:
 * the quarry queued at every red light and the "target got away" branch was dead code.
 *
 * The ring is now set from measurement rather than from taste. A `fleeSpeed` 26 runner
 * covers 400 to 900 m of road inside the flee window at up to 90 km/h, but it is picking a
 * random exit at every junction, so the *gap* it opens grows far more slowly than the
 * distance it drives. Three runs put it 250 m out at 30 s, 300 m at 36 s and 340 m at 47 s
 * with the player standing still - and one run of the mission probe, with the player also
 * driving away, was still short of 340 m after a minute. So the default ring is 280 m: a
 * distance every run cleared inside about 35 s of a 150 s clock. Raising it back without
 * raising `fleeSpeed` makes the defeat unreachable again; dropping `fleeSpeed` means the
 * ring has to come down with it.
 *
 * @param {object} [o]
 * @param {string} [o.label]        HUD line
 * @param {string} [o.vehicleClass] any `VEHICLE_CLASSES` key - what the runner drives
 * @param {number} [o.colour]       hull colour, so a marked target reads at a distance
 * @param {number} [o.spawnMin]     nearest the quarry may appear, metres
 * @param {number} [o.spawnMax]     furthest the quarry may appear, metres
 * @param {number} [o.fleeSpeed]    autopilot target speed, m/s
 * @param {number} [o.escape]       lose it by this far and the job is blown
 * @param {number} [o.stopRange]    close enough for a stopped runner to count as caught
 * @param {number} [o.stopSeconds]  how long it has to stay stopped
 * @param {number} [o.timeLimit]    optional countdown, as on any other objective
 */
export function chaseObjective(o = {}) {
  return {
    type: 'chase',
    label: o.label ?? 'Wreck or stop the runner',
    vehicleClass: o.vehicleClass ?? 'sports',
    colour: o.colour ?? 0x1f6f4f,
    spawnMin: o.spawnMin ?? 45,
    spawnMax: o.spawnMax ?? 130,
    fleeSpeed: o.fleeSpeed ?? 28,
    escape: o.escape ?? 280,
    stopRange: o.stopRange ?? 26,
    stopSeconds: o.stopSeconds ?? 2.5,
    ...(o.timeLimit ? { timeLimit: o.timeLimit } : {}),
  };
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
  /**
   * Open water near a point. `nearestWater` returns null when a 900 m spiral found nothing,
   * which for an island this size means the caller asked about the middle of the map; the
   * fallback keeps the record well-formed and `ring` below is what refuses to use it.
   */
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

  /**
   * A ring of open-water checkpoints around an inlet, for the boat races. Every candidate
   * goes through `water()` so a buoy that would have landed on a spit of shoreline is
   * pushed out to the nearest sailable point instead of being unreachable.
   */
  const ring = (centre, count, radius, phase = 0) => {
    const out = [];
    for (let i = 0; i < count; i++) {
      const a = phase + (i / count) * Math.PI * 2;
      const p = water(centre.x + Math.cos(a) * radius, centre.z + Math.sin(a) * radius);
      // A buoy that is still on land after the push-to-water search is unreachable by
      // boat, so it is dropped rather than left in the lap as an objective that can only
      // time out. A short lap is a worse race; an impossible one is a broken mission.
      if (p && !island.isLand(p.x, p.z)) out.push({ x: p.x, z: p.z });
    }
    return out;
  };

  const bayRing = ring(island.bay, 4, island.bay.radius * 0.6, 0.4);
  const marinaRing = ring(island.marina, 3, island.marina.radius * 0.62, 1.1);
  const yardSiege = road(-700, -420);

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

    /* ------------------------------------------------------------------- chase */
    {
      id: 'hot-pursuit',
      name: 'Hot Pursuit',
      brief: 'He is already moving. Stop him before he clears the district.',
      reward: 2400,
      start: road(180, 320),
      objectives: [
        // Spawned close enough to be found on foot, far enough that it is a chase.
        chaseObjective({
          label: 'Wreck or stop the runner',
          spawnMin: 40, spawnMax: 110, fleeSpeed: 26, timeLimit: 150,
        }),
      ],
    },
    {
      id: 'bagman',
      name: 'The Bagman',
      brief: 'The bag is in the boot and the boot is doing sixty.',
      reward: 3100,
      start: road(-520, -160),
      objectives: [
        { type: 'steal', label: 'Get a car' },
        chaseObjective({
          label: 'Run the bagman down',
          vehicleClass: 'coupe', colour: 0x2b2f38,
          // A wider ring than the default, because this runner is faster and the player
          // starts the objective already in a car. 340 m is the distance the slower
          // 26 m/s runner was measured clearing on its own, so a 32 m/s one has it.
          spawnMin: 55, spawnMax: 150, fleeSpeed: 32,
          escape: 340, stopRange: 22, timeLimit: 180,
        }),
      ],
    },

    /* ------------------------------------------------------------------ defend */
    {
      id: 'hold-the-line',
      name: 'Hold the Line',
      brief: 'Somebody made a call. Do not be anywhere else when they arrive.',
      reward: 2800,
      // No `at`: a defend objective with no point of its own anchors to the mission start,
      // so the marker the player walked into IS the ground they have to hold. Anything
      // else would fail them for standing exactly where the job began.
      objectives: [
        {
          type: 'defend', label: 'Hold the corner',
          radius: 55, grace: 5, waves: 2, waveSeconds: 16, perWave: 2,
        },
      ],
      start: road(520, -260),
    },
    {
      id: 'last-stand',
      name: 'Last Stand',
      brief: 'Three waves. One yard. No exit.',
      reward: 3800,
      start: road(-780, -300),
      objectives: [
        { type: 'drive', at: yardSiege, radius: 16, label: 'Get to the yard' },
        {
          type: 'defend', at: yardSiege, label: 'Hold the yard',
          radius: 60, grace: 6, waves: 3, waveSeconds: 18, perWave: 2,
        },
      ],
    },

    /* -------------------------------------------------------------------- race */
    {
      id: 'bay-blast',
      name: 'Bay Blast',
      brief: 'Four buoys, one lap, and a time nobody has beaten sober.',
      reward: 3000,
      start: road(island.bay.x - 300, island.bay.z + 260),
      objectives: [
        // `sail`, not `goto`: the race objective that follows fails you for not being in a
        // boat, so the grid has to be a place you can only reach in one.
        { type: 'sail', at: harbour, radius: 26, label: 'Get a boat out to the start' },
        {
          type: 'race', ring: bayRing, radius: 42,
          label: 'Run the bay circuit',
          timeLimit: 260, ghost: 170, ghostBonus: 1200, abandon: 10,
        },
      ],
    },
    {
      id: 'marina-sprint',
      name: 'Marina Sprint',
      brief: 'Short course, tight water, and the clock does not care.',
      reward: 2400,
      start: road(island.marina.x + 260, island.marina.z - 200),
      objectives: [
        { type: 'sail', at: marinaWater, radius: 26, label: 'Get a boat out to the start' },
        {
          type: 'race', ring: marinaRing, radius: 38,
          label: 'Three buoys, no mistakes',
          timeLimit: 200, ghost: 120, ghostBonus: 900, abandon: 10,
        },
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
    /** Extra payout earned inside the current mission (race ghost bonus). */
    this.bonus = 0;
    /** @type {{vehicle: object, stalled: number, closest: number}|null} */
    this.chase = null;
    /** Seconds until the next attempt to put a quarry on the street. See `_beginChase`. */
    this._chaseRetry = 0;
    /** @type {{at: object, wave: number, timer: number, away: number, attackers: object[]}|null} */
    this.defend = null;
    /** @type {{index: number, splits: number[]}|null} */
    this.race = null;

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
    // Separate scratch for spawn positions: `_v` holds the player point for the whole of
    // `update`, and handing it to a spawner mid-frame moves the thing being measured.
    this._spawnAt = new Vector3();
    this._chasePoint = { x: 0, z: 0 };
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
    if (objective.type === 'chase') {
      const v = this.chase?.vehicle;
      if (!v) return null;
      // Reused: this getter is polled every frame by the map blips while a chase runs.
      this._chasePoint.x = v.position.x;
      this._chasePoint.z = v.position.z;
      return this._chasePoint;
    }
    if (objective.type === 'race') {
      const cp = objective.ring?.[this.race?.index ?? 0];
      return cp ?? null;
    }
    if (objective.at) return objective.at;
    // A defend objective without a point of its own holds the mission start marker.
    if (objective.type === 'defend') return this.active ? this.active.start : null;
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
    this.bonus = 0;
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
    if (o.type === 'chase') this._beginChase(o);
    if (o.type === 'defend') this._beginDefend(o);
    if (o.type === 'race') this.race = { index: 0, splits: [], adrift: 0 };

    const at = this._objectivePosition(o);
    if (at) {
      const y = this._groundY(at.x, at.z);
      this.objectiveMarker.setColour(MARKER_COLOUR[o.type] ?? 0xffb703);
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

  /* ------------------------------------------------------------------ templates */

  /**
   * A free lane point on the road graph within a distance band of `near`, the same shape
   * of search the wanted system uses to dispatch a cruiser out of sight. Returns null if
   * 48 tries found nothing clear, and every caller treats that as "no spawn this wave"
   * rather than as a reason to stall the mission.
   */
  _roadSpot(near, minDistance, maxDistance) {
    const net = this.city.network;
    for (let attempt = 0; attempt < 48; attempt++) {
      const edge = net.edges[Math.floor(Math.random() * net.edges.length)];
      const forward = Math.random() < 0.5;
      const p = net.lanePointOnEdge(edge, Math.random(), forward, 0);
      const d = Math.hypot(p.x - near.x, p.z - near.z);
      if (d < minDistance || d > maxDistance) continue;
      // Landing on top of parked traffic starts the chase already wedged.
      if (this.traffic._occupied(p.x, p.z, 9)) continue;
      return { x: p.x, z: p.z, heading: p.heading, edge, forward };
    }
    return null;
  }

  /**
   * Put a runner on the street and hand it to the ordinary traffic autopilot.
   *
   * There is no bespoke evade behaviour and there deliberately is not one: the autopilot
   * already picks a random exit at every junction at a target speed we choose, which from
   * behind is indistinguishable from a driver taking turns to lose you, and it keeps the
   * quarry on real lanes instead of driving it through a block.
   *
   * @returns {boolean} whether a quarry actually reached the world
   */
  _beginChase(objective) {
    this._endChase();
    const point = this._playerPoint(this._v);
    const spot = this._roadSpot(point, objective.spawnMin ?? 45, objective.spawnMax ?? 130);
    // Nothing clear in the band this instant - the player may be parked in a cul-de-sac or
    // boxed in by traffic. The caller retries rather than skipping the objective, because
    // skipping paid the full reward for a chase that never happened.
    if (!spot) { this._chaseRetry = 0.6; return false; }
    const vehicle = this.traffic._spawn(
      objective.vehicleClass ?? 'sports',
      this._spawnAt.set(spot.x, 0.9, spot.z),
      spot.heading,
      { colour: objective.colour ?? 0x1f6f4f },
    );
    /*
     * `scripted` is the one thing that separates the runner from the traffic around it.
     * The autopilot reads it in three places (VehicleManager): it stops re-rolling the
     * target speed at every junction, so the mission's `fleeSpeed` survives the first
     * corner; it skips the red-light clamp, because the traffic obeys the signals and a
     * driver being chased does not; and it exempts the car from the distance recycler,
     * whose job is to keep ambient traffic near the player - the exact opposite of what a
     * quarry is trying to do. Without it the runner cruised at street pace and queued at
     * every red, which put the escape ring out of its own reach.
     */
    this.traffic.ai.set(vehicle, {
      edge: spot.edge, forward: spot.forward, lane: 0,
      targetSpeed: objective.fleeSpeed ?? 28,
      patience: 0, stuckTimer: 0, scripted: true,
    });
    this.chase = { vehicle, stalled: 0, closest: Infinity };
    return true;
  }

  _endChase() {
    this._chaseRetry = 0;
    if (!this.chase) return;
    this._despawn(this.chase.vehicle);
    this.chase = null;
  }

  _beginDefend(objective) {
    this._clearAttackers();
    this.defend = {
      at: this._objectivePosition(objective) ?? this.active.start,
      wave: 1, timer: objective.waveSeconds ?? 18, away: 0, attackers: [],
    };
    this._spawnWave(objective);
    this.hud.say(`Wave 1 of ${objective.waves ?? 1}`, 2.4);
  }

  /**
   * A wave is police cruisers, dispatched exactly the way the wanted system dispatches
   * them and then driven straight at the player. What is deliberately missing is the
   * `wanted.report` call: a siege is a mission, not a crime, so surviving one must not
   * leave the player with stars they never earned.
   */
  _spawnWave(objective) {
    const count = objective.perWave ?? 2;
    for (let i = 0; i < count; i++) {
      const spot = this._roadSpot(
        this.defend.at, objective.spawnMin ?? 55, objective.spawnMax ?? 200,
      );
      if (!spot) continue;
      const car = this.traffic.spawnPolice(
        this._spawnAt.set(spot.x, 0.9, spot.z), spot.heading,
      );
      this.defend.attackers.push(car);
    }
  }

  _clearAttackers() {
    if (!this.defend) return;
    for (const car of this.defend.attackers) this._despawn(car);
    this.defend.attackers.length = 0;
  }

  /** Steer every live attacker at the point being defended. */
  _driveAttackers(target) {
    for (const car of this.defend.attackers) {
      if (car.health <= 0) {
        car.setInput({ throttle: 0, brake: 1, steer: 0, handbrake: false });
        continue;
      }
      const pos = car.position;
      let error = Math.atan2(target.x - pos.x, target.z - pos.z) - car.heading;
      while (error > Math.PI) error -= Math.PI * 2;
      while (error < -Math.PI) error += Math.PI * 2;
      const speed = Math.abs(car.speed);
      const wanted = MathUtils.clamp(24 * (1 - Math.abs(error) * 0.6), 3, 26);
      const delta = wanted - speed;
      car.setInput({
        throttle: MathUtils.clamp(delta * 0.4, 0, 1),
        brake: MathUtils.clamp(-delta * 0.3, 0, 1),
        steer: MathUtils.clamp(error * 1.8, -1, 1),
        handbrake: false,
      });
      car.headlightsOn = true;
      car.wake();
    }
  }

  /**
   * Take a mission-spawned vehicle back out of the world. Never the one the player is
   * sitting in - stealing the quarry is a legitimate way to stop it, and disposing of it
   * underneath them would leave the camera bound to a destroyed body.
   */
  _despawn(vehicle) {
    if (!vehicle || vehicle === this.traffic.playerVehicle) return;
    const list = this.traffic.vehicles;
    const i = list.indexOf(vehicle);
    if (i >= 0) list.splice(i, 1);
    this.traffic.ai.delete(vehicle);
    vehicle.dispose();
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
    // Bonuses are earned inside the mission (so far only the race ghost time) and paid as
    // part of the same reward, through the same hook - there is one place money arrives.
    const payout = mission.reward + this.bonus;
    this.earned += payout;
    this.hud.say(
      `${mission.name} complete  +$${payout.toLocaleString('en-US')}`
      + (this.bonus ? `  (ghost bonus $${this.bonus.toLocaleString('en-US')})` : ''), 5,
    );
    this.onReward?.(payout);
    this._endMission();
  }

  /**
   * Drop the current mission without failing it, and put every mission into the state a
   * save describes. Used by `SaveGame.load`, which has to *replace* progress rather than
   * merge into it: marking the saved ones complete and leaving the rest alone means a
   * mission finished after the save stays finished, and its start marker stays hidden,
   * while the completion counter says otherwise.
   *
   * @param {Set<string>|string[]} completedIds mission ids complete at save time
   */
  restoreProgress(completedIds) {
    const done = completedIds instanceof Set ? completedIds : new Set(completedIds ?? []);
    if (this.active) this._endMission();
    for (const m of this.missions) {
      const isDone = done.has(m.id);
      m.state = isDone ? MISSION_STATE.COMPLETE : MISSION_STATE.AVAILABLE;
      const marker = this.startMarkers.get(m.id);
      if (!marker) continue;
      if (isDone) marker.hide();
      else marker.place(m.start.x, 0.2, m.start.z, 4);
    }
    this.completed = done.size;
    return this.completed;
  }

  _endMission() {
    this.active = null;
    this.objectiveIndex = 0;
    this.objectiveMarker.hide();
    this._clearPickups();
    // Anything the templates put into the world goes with the mission, however it ended.
    // A quarry or a wave of attackers left running after a failure would keep driving at
    // a player who is no longer on the job.
    this._endChase();
    this._clearAttackers();
    this.defend = null;
    this.race = null;
    this.bonus = 0;
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

      case 'chase': {
        const t = this.chase;
        /*
         * No quarry yet. The spawn search only looks at the road graph around wherever the
         * player is standing this instant, so a failure is a transient, not a dead end -
         * keep retrying and let the objective's own clock decide when to give up. The
         * earlier version advanced the objective instead, which paid the reward for a
         * chase the player never had.
         */
        if (!t) {
          this._chaseRetry -= dt;
          if (this._chaseRetry <= 0) this._beginChase(o);
          break;
        }
        const v = t.vehicle;
        const pos = v.position;
        const distance = Math.hypot(point.x - pos.x, point.z - pos.z);
        if (distance < t.closest) t.closest = distance;
        // The marker rides the quarry, so the HUD arrow and the map blip both track it.
        this.objectiveMarker.place(pos.x, pos.y - 0.4, pos.z, 8);

        if (v.health <= 0) { this._advance(); break; }
        // Stopped counts as well as wrecked - a runner boxed in against a wall is caught.
        if (distance < (o.stopRange ?? 26) && Math.abs(v.speed) < 1.6) {
          t.stalled += dt;
          if (t.stalled > (o.stopSeconds ?? 2.5)) { this._advance(); break; }
        } else {
          t.stalled = 0;
        }
        if (distance > (o.escape ?? 280)) this.fail('the target got away');
        break;
      }

      case 'defend': {
        const st = this.defend;
        if (!st) { this._advance(); break; }
        const inside = Math.hypot(point.x - st.at.x, point.z - st.at.z) <= (o.radius ?? 50);
        // A short grace window, so clipping the edge of the zone at speed is not a loss.
        st.away = inside ? 0 : st.away + dt;
        if (st.away > (o.grace ?? 5)) { this.fail('you abandoned the position'); break; }

        this._driveAttackers(st.at);
        st.timer -= dt;
        let cleared = st.attackers.length > 0;
        for (const car of st.attackers) if (car.health > 0) { cleared = false; break; }

        if (st.timer > 0 && !cleared) break;
        st.wave++;
        this._clearAttackers();
        if (st.wave > (o.waves ?? 1)) { this._advance(); break; }
        st.timer = o.waveSeconds ?? 18;
        this._spawnWave(o);
        this.hud.say(`Wave ${st.wave} of ${o.waves ?? 1}`, 2.4);
        break;
      }

      case 'race': {
        const st = this.race;
        const cp = o.ring?.[st?.index ?? 0];
        if (!st || !cp) { this._advance(); break; }
        /*
         * Stepping off the boat scratches you. Without this the clock is the only way to
         * lose a race, so bailing out at buoy one and swimming ashore costs nothing and
         * the mission just sits there. The window is generous because being thrown out by
         * a bad landing and climbing back aboard is racing, not quitting.
         */
        st.adrift = inBoat ? 0 : st.adrift + dt;
        if (st.adrift > (o.abandon ?? 10)) { this.fail('you left the boat'); break; }
        if (!inBoat) break;
        if (Math.hypot(point.x - cp.x, point.z - cp.z) > (o.radius ?? 40)) break;

        st.index++;
        st.splits.push(Math.round(((o.timeLimit ?? 0) - this.timer) * 10) / 10);
        if (st.index >= o.ring.length) {
          // Ghost time: the reward is flat, beating the ghost is what the bonus is for.
          const elapsed = (o.timeLimit ?? 0) - this.timer;
          if (o.ghost && elapsed <= o.ghost) {
            this.bonus += o.ghostBonus ?? 0;
            this.hud.say(`Ghost beaten by ${(o.ghost - elapsed).toFixed(1)}s`, 3);
          }
          this._advance();
          break;
        }
        const next = o.ring[st.index];
        this.hud.say(`Buoy ${st.index} of ${o.ring.length}`, 1.6);
        this.objectiveMarker.place(next.x, this._groundY(next.x, next.z), next.z, o.radius ?? 40);
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
    const clock = o.timeLimit
      ? `  ${Math.floor(Math.max(0, this.timer) / 60)}:${String(Math.floor(Math.max(0, this.timer) % 60)).padStart(2, '0')}`
      : '';
    if (o.type === 'race' && this.race) {
      return `${o.label}  buoy ${Math.min(this.race.index + 1, o.ring.length)}/${o.ring.length}${clock}`;
    }
    if (o.type === 'defend' && this.defend) {
      return `${o.label}  wave ${this.defend.wave}/${o.waves ?? 1}  ${Math.ceil(Math.max(0, this.defend.timer))}s`;
    }
    if (o.type === 'chase' && this.chase) {
      const p = this._playerPoint(this._v);
      const v = this.chase.vehicle.position;
      return `${o.label}  ${Math.round(Math.hypot(p.x - v.x, p.z - v.z))}m${clock}`;
    }
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
