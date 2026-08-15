/**
 * VELOCITRON - race director.
 *
 * Headless on purpose: this module never touches the DOM, the renderer, the
 * audio graph or the FX system. It owns the race clock, the starting grid, the
 * per frame simulation order (AI -> ship physics -> ship to ship collisions),
 * lap and checkpoint validation, the live standings and the final results.
 * Everything it wants the presentation layer to react to is pushed into
 * `race.events`, which main.js consumes and clears once per frame.
 *
 * Time units: `race.time` and `ship.lapStartTime` are in seconds (negative
 * during the countdown, zero at the GO). Every value handed out for display
 * (`lapTimes`, `bestLap`, `finishTime`, results rows) is in milliseconds, as
 * required by the contract.
 *
 * Progress metric: `ship.totalProgress` is rewritten here every frame as the
 * signed distance travelled since the start line (negative on the grid). It is
 * accumulated from `track.deltaS`, so it is monotonic through the `s` wrap and
 * through a respawn, which makes it a safe sort key for the standings.
 */

import { RACE, SHIP } from './config.js';
import { updateShip, respawnShip, resolveShipCollisions } from './ship.js';
import { updateAI } from './ai.js';

// ---------------------------------------------------------------------------
// Tuning that is local to the race director
// ---------------------------------------------------------------------------
const FINISH_HOLD = 20; // seconds the rivals keep racing after the player finishes
const GRID_LINE_MARGIN = 16; // metres between the pole slot and the start line
const GO_TEXT_HOLD = 1.0; // seconds the "GO" caption stays up after the start
const GAP_MAX = 99; // seconds, clamp for the standings gaps
const GAP_MIN_SPEED = 25; // m/s, floor used to turn a distance into a duration
const WALL_EVENT_MIN = 2.5; // m/s of impact below which a wall hit is silent
const SHIP_EVENT_MIN = 1.5;
const LAND_EVENT_MIN = 6; // matches the landing threshold used by ship.js
const IMPACT_REFERENCE = 30; // m/s mapped to an intensity of 1
const RESPAWN_SHIELD = 0.35; // fraction of the shield left by a manual respawn
const RESPAWN_COOLDOWN = 3; // seconds before the respawn key answers again for a craft
const EVENT_POOL = 16; // records kept per event channel, recycled round robin

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/** Round robin pool so the per frame event lists never allocate. */
function makePool(size, make) {
  const items = new Array(size);
  for (let i = 0; i < size; i++) items[i] = make();
  return { items, cursor: 0 };
}

function poolTake(pool) {
  const item = pool.items[pool.cursor];
  pool.cursor = (pool.cursor + 1) % pool.items.length;
  return item;
}

/**
 * True when the ship crossed `target` while moving forward during this step.
 * `deltaS` handles the wrap, so this cannot be fooled by the seam and a ship
 * driving backwards never triggers it.
 */
function crossedForward(track, fromS, toS, target) {
  const move = track.deltaS(fromS, toS);
  if (move <= 0) return false;
  const toTarget = track.deltaS(fromS, target);
  return toTarget > 0 && toTarget <= move;
}

/** Mirror of crossedForward for a ship travelling the wrong way. */
function crossedBackward(track, fromS, toS, target) {
  const move = track.deltaS(fromS, toS);
  if (move >= 0) return false;
  const toTarget = track.deltaS(fromS, target);
  return toTarget < 0 && toTarget >= move;
}

/** Standings order: finishers first by finish time, then by distance covered. */
function compareEntries(a, b) {
  const sa = a.ship;
  const sb = b.ship;
  if (sa.finished !== sb.finished) return sa.finished ? -1 : 1;
  if (sa.finished && sb.finished) return (sa.finishTime || 0) - (sb.finishTime || 0);
  return b.progress - a.progress;
}

// ---------------------------------------------------------------------------
// Race
// ---------------------------------------------------------------------------

/**
 * @param {{ track: object, ships: object[], ais: object[], laps: number }} opts
 * @returns {object} race
 */
export function createRace(opts) {
  const track = opts.track;
  const ships = opts.ships || [];
  const ais = opts.ais || [];
  const shipCount = ships.length;
  const totalLaps = Math.max(1, Math.floor(opts.laps || RACE.laps));

  // -- checkpoints, ordered by distance from the start line -----------------
  const startS = track.wrapS(track.startS || 0);
  const checkpointS = buildCheckpoints(track, startS);
  const cpCount = checkpointS.length;

  // -- per ship bookkeeping, all preallocated -------------------------------
  const prevS = new Float64Array(shipCount);
  const progress = new Float64Array(shipCount);
  const prevPos = new Int32Array(shipCount);
  const wasDestroyed = new Uint8Array(shipCount);
  const respawnCooldown = new Float64Array(shipCount);
  const idleControls = new Array(shipCount);
  const aiForShip = new Array(shipCount);
  const entries = new Array(shipCount);
  const standings = new Array(shipCount);

  for (let i = 0; i < shipCount; i++) {
    idleControls[i] = { thrust: 0, brake: 0, steer: 0, airLeft: 0, airRight: 0, boost: false };
    aiForShip[i] = null;
    const ship = ships[i];
    const entry = {
      ship,
      pos: i + 1,
      gap: 0, // seconds behind the leader
      interval: 0, // seconds behind the ship directly ahead
      progress: 0,
      lap: 1, // 1 based lap for display
      lapsDone: 0,
      name: ship.name || 'PILOTE',
      color: ship.color,
      isPlayer: !!ship.isPlayer,
      finished: false,
    };
    entries[i] = entry;
    standings[i] = entry;
  }

  bindAIs(ships, ais, aiForShip);

  // -- grid slot order: rivals up front, the player on the last row ---------
  const slotOrder = new Int32Array(shipCount);
  let slot = 0;
  for (let i = 0; i < shipCount; i++) if (!ships[i].isPlayer) slotOrder[slot++] = i;
  for (let i = 0; i < shipCount; i++) if (ships[i].isPlayer) slotOrder[slot++] = i;

  let playerShip = null;
  for (let i = 0; i < shipCount; i++) {
    if (ships[i].isPlayer) {
      playerShip = ships[i];
      break;
    }
  }
  if (!playerShip && shipCount > 0) playerShip = ships[0];

  // -- event pools ----------------------------------------------------------
  const lapPool = makePool(EVENT_POOL, () => ({ ship: null, lap: 0, time: 0, isBest: false, isPlayer: false }));
  const posPool = makePool(EVENT_POOL, () => ({ ship: null, pos: 0, previousPos: 0, isPlayer: false }));
  const hitPool = makePool(EVENT_POOL * 2, () => ({ ship: null, impact: 0, intensity: 0, isPlayer: false }));
  const flagPool = makePool(EVENT_POOL, () => ({ ship: null, pos: 0, isPlayer: false }));
  const invalidPool = makePool(EVENT_POOL, () => ({ ship: null, lap: 0, reached: 0, required: 0, isPlayer: false }));

  // Rivals only: a solo race must never start the end of race hold on its own.
  let rivalCount = 0;
  for (let i = 0; i < shipCount; i++) if (!ships[i].isPlayer) rivalCount++;

  const events = {
    countdown: null, // 3 | 2 | 1 | 0 (0 is the GO), one step per frame at most
    go: false, // true on the frame the lights go out
    lap: null, // latest lap completed this frame, the player one wins
    laps: [], // every lap completed this frame
    invalidLaps: [], // line crossed with missing checkpoints, the lap was dropped
    overtakes: [],
    wallHits: [],
    shipHits: [],
    landings: [],
    padHits: [],
    explosions: [],
    respawns: [],
    finishers: [], // ships that took the flag this frame
    finish: false, // the player took the flag this frame
    finishPos: 0,
    raceOver: false, // the race switched to 'finished' this frame
  };

  const aiContext = { ships, playerProgress: 0, raceTime: 0, state: 'countdown' };

  let lastCountdownStep = null;

  const race = {
    state: 'countdown',
    time: -RACE.countdown,
    track,
    ships,
    ais,
    laps: totalLaps,
    checkpoints: checkpointS,
    playerShip,
    playerPosition: shipCount,
    playerFinished: false,
    finishHold: FINISH_HOLD,
    countdownText: null,
    winner: null,
    standings,
    results: [],
    events,
    update,
    placeOnGrid,
    reset,
    clearEvents,
    requestRespawn,
    displayLap,
  };

  // -------------------------------------------------------------------------
  // Grid
  // -------------------------------------------------------------------------

  /**
   * Two staggered columns behind the start line, the player on the last row so
   * there is always something to overtake. Also rewinds the race clock, so it
   * doubles as a full restart.
   */
  function placeOnGrid() {
    for (let k = 0; k < shipCount; k++) {
      const i = slotOrder[k];
      const ship = ships[i];
      const row = Math.floor(k / 2);
      const col = k % 2;
      const s = track.wrapS(startS - GRID_LINE_MARGIN - row * RACE.gridSpacing);
      const limit = Math.max(1, track.halfWidthAt(s) - SHIP.halfWidth - 0.6);
      const x = clamp((col === 0 ? -0.5 : 0.5) * RACE.gridStagger, -limit, limit);

      ship.s = s;
      ship.x = x;
      ship.h = SHIP.hoverHeight;
      ship.yaw = 0;
      ship.speed = 0;
      ship.vLat = 0;
      ship.vh = 0;
      ship.roll = 0;
      ship.pitch = 0;
      ship.shield = SHIP.shieldMax;
      ship.boostEnergy = 100;
      ship.boostTimer = 0;
      ship.padBoostTimer = 0;
      ship.lap = 0;
      ship.lastCheckpoint = -1;
      ship.lapStarted = false;
      ship.finished = false;
      ship.finishTime = null;
      ship.lapStartTime = 0;
      ship.bestLap = null;
      if (Array.isArray(ship.lapTimes)) ship.lapTimes.length = 0;
      else ship.lapTimes = [];
      ship.destroyed = false;
      ship.respawnTimer = 0;

      const ev = ship.events;
      if (ev) {
        ev.wallHit = 0;
        ev.padHit = false;
        ev.land = 0;
        ev.shipHit = 0;
      }
      if (ship.mesh) ship.mesh.visible = true;
      if (ship.worldPos) {
        track.toWorld(s, x, ship.h, ship.worldPos);
        if (ship.mesh) ship.mesh.position.copy(ship.worldPos);
      }

      progress[i] = track.deltaS(startS, s); // negative: the grid is behind the line
      ship.totalProgress = progress[i];
      prevS[i] = s;
      prevPos[i] = 0;
      wasDestroyed[i] = 0;
      respawnCooldown[i] = 0;
    }

    race.time = -RACE.countdown;
    race.state = 'countdown';
    race.playerFinished = false;
    race.finishHold = FINISH_HOLD;
    race.countdownText = null;
    race.winner = null;
    race.playerPosition = shipCount;
    race.results = [];
    lastCountdownStep = null;
    clearEvents();
    updateStandings();
    for (let i = 0; i < shipCount; i++) prevPos[i] = entries[i].pos;
  }

  /** Full restart, kept as an explicit name for main.js. */
  function reset() {
    placeOnGrid();
  }

  // -------------------------------------------------------------------------
  // Events
  // -------------------------------------------------------------------------
  function clearEvents() {
    events.countdown = null;
    events.go = false;
    events.lap = null;
    events.laps.length = 0;
    events.invalidLaps.length = 0;
    events.overtakes.length = 0;
    events.wallHits.length = 0;
    events.shipHits.length = 0;
    events.landings.length = 0;
    events.padHits.length = 0;
    events.explosions.length = 0;
    events.respawns.length = 0;
    events.finishers.length = 0;
    events.finish = false;
    events.finishPos = 0;
    events.raceOver = false;
  }

  function pushHit(list, ship, impact) {
    const rec = poolTake(hitPool);
    rec.ship = ship;
    rec.impact = impact;
    rec.intensity = clamp01(impact / IMPACT_REFERENCE);
    rec.isPlayer = !!ship.isPlayer;
    list.push(rec);
  }

  function pushFlag(list, ship, pos) {
    const rec = poolTake(flagPool);
    rec.ship = ship;
    rec.pos = pos;
    rec.isPlayer = !!ship.isPlayer;
    list.push(rec);
  }

  // -------------------------------------------------------------------------
  // Frame update
  // -------------------------------------------------------------------------

  /**
   * @param {number} dt seconds, already clamped by main.js
   * @param {object} playerControls the reused controls object from input.js
   */
  function update(dt, playerControls) {
    clearEvents();
    if (race.state === 'finished') return;
    const step = dt > 0 ? dt : 0;

    race.time += step;
    if (race.state === 'countdown') updateCountdown();
    const racing = race.state === 'racing';
    if (racing) race.countdownText = race.time < GO_TEXT_HOLD ? 'GO' : null;

    aiContext.playerProgress = playerShip ? playerShip.totalProgress : 0;
    aiContext.raceTime = race.time;
    aiContext.state = race.state;

    // 1 - drive every craft
    for (let i = 0; i < shipCount; i++) {
      const ship = ships[i];
      prevS[i] = ship.s;
      if (respawnCooldown[i] > 0) respawnCooldown[i] = Math.max(0, respawnCooldown[i] - step);

      const wasWrecked = !!ship.destroyed;
      let controls;
      if (wasWrecked || !racing) {
        controls = resetIdle(i);
      } else if (ship.isPlayer) {
        controls = ship.finished || !playerControls ? resetIdle(i) : playerControls;
      } else {
        const ai = aiForShip[i];
        controls = ai ? updateAI(ai, step, aiContext) : resetIdle(i);
      }
      // updateShip owns the wrecked state and its respawn timer, so a destroyed
      // craft is still simulated (it coasts) instead of being frozen here.
      updateShip(ship, controls, step, track);

      if (wasWrecked && !ship.destroyed) {
        // updateShip just dropped the craft back on the racing line.
        prevS[i] = ship.s;
        // race.js owns totalProgress: respawnShip wrote the ship.js definition
        // into it, which the AIs updated later this frame would read otherwise.
        ship.totalProgress = progress[i];
        entries[i].progress = progress[i];
        if (ship.mesh) ship.mesh.visible = true;
        pushFlag(events.respawns, ship, entries[i].pos);
      }
    }

    // 2 - ship to ship, once for the whole field
    resolveShipCollisions(ships, track, step);

    // 3 - progress, laps and per craft events
    for (let i = 0; i < shipCount; i++) {
      const ship = ships[i];
      const s = ship.s;
      const moved = track.deltaS(prevS[i], s);
      progress[i] += moved;
      ship.totalProgress = progress[i];

      harvestShipEvents(ship, i);

      if (!racing || ship.finished) continue;
      if (moved > 0) {
        let guard = 0;
        while (ship.lastCheckpoint < cpCount - 1 && guard++ <= cpCount) {
          const next = ship.lastCheckpoint + 1;
          if (crossedForward(track, prevS[i], s, checkpointS[next])) ship.lastCheckpoint = next;
          else break;
        }
        if (crossedForward(track, prevS[i], s, startS)) crossLine(ship);
      } else if (moved < 0) {
        // Driving the wrong way unwinds the chain, so a lap can never be
        // validated by shuffling back and forth over the line.
        if (ship.lastCheckpoint >= 0 && crossedBackward(track, prevS[i], s, checkpointS[ship.lastCheckpoint])) {
          ship.lastCheckpoint -= 1;
        }
        if (crossedBackward(track, prevS[i], s, startS)) ship.lastCheckpoint = -1;
      }
    }

    // 4 - standings, then the position changes they imply
    updateStandings();
    if (racing) {
      for (let i = 0; i < shipCount; i++) {
        const pos = entries[i].pos;
        const before = prevPos[i];
        if (before > 0 && pos < before) {
          const rec = poolTake(posPool);
          rec.ship = ships[i];
          rec.pos = pos;
          rec.previousPos = before;
          rec.isPlayer = !!ships[i].isPlayer;
          events.overtakes.push(rec);
        }
        prevPos[i] = pos;
      }
    } else {
      for (let i = 0; i < shipCount; i++) prevPos[i] = entries[i].pos;
    }

    if (events.finish && playerShip) {
      const entry = entryOf(playerShip);
      events.finishPos = entry ? entry.pos : race.playerPosition;
    }

    // 5 - end of race rules
    if (race.state === 'racing') {
      let allDone = shipCount > 0;
      let rivalsDone = rivalCount > 0;
      for (let i = 0; i < shipCount; i++) {
        if (ships[i].finished) continue;
        allDone = false;
        if (!ships[i].isPlayer) rivalsDone = false;
      }
      // The hold also starts once the whole field but the player is parked at
      // the flag, otherwise a pilot who never takes the chequered flag would
      // leave the race running forever. The player keeps full control until it
      // expires.
      if (race.playerFinished || rivalsDone) race.finishHold -= step;
      if (allDone || race.finishHold <= 0) finishRace();
    }
  }

  function updateCountdown() {
    const remaining = -race.time;
    let step = null;
    if (remaining <= 0) step = 0;
    else if (remaining <= 1) step = 1;
    else if (remaining <= 2) step = 2;
    else if (remaining <= 3) step = 3;

    if (step !== null && (lastCountdownStep === null || step < lastCountdownStep)) {
      lastCountdownStep = step;
      events.countdown = step;
      if (step === 0) {
        events.go = true;
        race.state = 'racing';
      }
    }
    race.countdownText = step === null ? null : step === 0 ? 'GO' : String(step);
  }

  function resetIdle(i) {
    const c = idleControls[i];
    c.thrust = 0;
    c.brake = 0;
    c.steer = 0;
    c.airLeft = 0;
    c.airRight = 0;
    c.boost = false;
    return c;
  }

  /**
   * Manual respawn path. `respawnShip` fully repairs the craft, so the shield is
   * overwritten right after: asking for a respawn always costs shield, which
   * keeps it a recovery move and not a free repair.
   */
  function reviveShip(ship, i) {
    respawnShip(ship, track);
    ship.destroyed = false;
    ship.respawnTimer = 0;
    ship.shield = SHIP.shieldMax * RESPAWN_SHIELD;
    if (ship.mesh) ship.mesh.visible = true;
    prevS[i] = ship.s;
    // Same ownership rule as the automatic path: the accumulated progress is
    // the only definition the standings and the AI are allowed to see.
    ship.totalProgress = progress[i];
    entries[i].progress = progress[i];
    pushFlag(events.respawns, ship, entries[i].pos);
  }

  /** Turns the flags left by updateShip into race level events. */
  function harvestShipEvents(ship, i) {
    const ev = ship.events;
    if (ev) {
      if (ev.wallHit > WALL_EVENT_MIN) pushHit(events.wallHits, ship, ev.wallHit);
      if (ev.shipHit > SHIP_EVENT_MIN) pushHit(events.shipHits, ship, ev.shipHit);
      if (ev.land > LAND_EVENT_MIN) pushHit(events.landings, ship, ev.land);
      if (ev.padHit) pushFlag(events.padHits, ship, entries[i].pos);
    }
    const destroyed = ship.destroyed ? 1 : 0;
    if (destroyed && !wasDestroyed[i]) pushFlag(events.explosions, ship, entries[i].pos);
    wasDestroyed[i] = destroyed;
  }

  /**
   * Forward crossing of the start line. The lap only counts when every
   * checkpoint has been taken in order since the previous crossing, which also
   * makes the very first crossing (leaving the grid) the start of lap 1.
   */
  function crossLine(ship) {
    const complete = ship.lapStarted && ship.lastCheckpoint === cpCount - 1;
    if (complete) {
      const time = Math.max(0, (race.time - ship.lapStartTime) * 1000);
      ship.lap += 1;
      if (!Array.isArray(ship.lapTimes)) ship.lapTimes = [];
      ship.lapTimes.push(time);
      const isBest = ship.bestLap === null || ship.bestLap === undefined || time < ship.bestLap;
      if (isBest) ship.bestLap = time;

      const rec = poolTake(lapPool);
      rec.ship = ship;
      rec.lap = ship.lap;
      rec.time = time;
      rec.isBest = isBest;
      rec.isPlayer = !!ship.isPlayer;
      events.laps.push(rec);
      if (!events.lap || rec.isPlayer) events.lap = rec;

      if (ship.lap >= totalLaps) {
        ship.finished = true;
        ship.finishTime = race.time * 1000;
        const entry = entryOf(ship);
        pushFlag(events.finishers, ship, entry ? entry.pos : 0);
        if (ship.isPlayer) {
          events.finish = true;
          race.playerFinished = true;
          race.finishHold = FINISH_HOLD;
        }
      }
    } else if (ship.lapStarted) {
      // Checkpoints missing: the lap is dropped without touching the counter.
      // The presentation layer decides how to tell the pilot about it.
      const rec = poolTake(invalidPool);
      rec.ship = ship;
      rec.lap = (ship.lap || 0) + 1;
      rec.reached = ship.lastCheckpoint + 1;
      rec.required = cpCount;
      rec.isPlayer = !!ship.isPlayer;
      events.invalidLaps.push(rec);
    }
    ship.lastCheckpoint = -1;
    ship.lapStarted = true;
    ship.lapStartTime = race.time;
  }

  function entryOf(ship) {
    for (let i = 0; i < shipCount; i++) if (entries[i].ship === ship) return entries[i];
    return null;
  }

  // -------------------------------------------------------------------------
  // Standings
  // -------------------------------------------------------------------------
  function updateStandings() {
    if (shipCount === 0) return;
    for (let i = 0; i < shipCount; i++) {
      const entry = entries[i];
      const ship = ships[i];
      entry.progress = progress[i];
      entry.lapsDone = ship.lap;
      entry.lap = displayLap(ship);
      entry.finished = !!ship.finished;
      entry.color = ship.color;
      entry.name = ship.name || entry.name;
    }
    standings.sort(compareEntries);

    const leader = standings[0];
    const leaderSpeed = Math.max(GAP_MIN_SPEED, Math.abs(leader.ship.speed || 0));
    leader.pos = 1;
    leader.gap = 0;
    leader.interval = 0;
    for (let k = 1; k < shipCount; k++) {
      const entry = standings[k];
      const ahead = standings[k - 1];
      entry.pos = k + 1;
      if (entry.finished && leader.finished) {
        entry.gap = clamp(((entry.ship.finishTime || 0) - (leader.ship.finishTime || 0)) / 1000, 0, GAP_MAX);
      } else {
        entry.gap = clamp((leader.progress - entry.progress) / leaderSpeed, 0, GAP_MAX);
      }
      const aheadSpeed = Math.max(GAP_MIN_SPEED, Math.abs(ahead.ship.speed || 0));
      entry.interval = clamp((ahead.progress - entry.progress) / aheadSpeed, 0, GAP_MAX);
    }

    if (playerShip) {
      const entry = entryOf(playerShip);
      if (entry) race.playerPosition = entry.pos;
    }
  }

  /** 1 based lap number for the HUD, never above the race distance. */
  function displayLap(ship) {
    return Math.min(totalLaps, Math.max(1, (ship.lap || 0) + (ship.finished ? 0 : 1)));
  }

  // -------------------------------------------------------------------------
  // Results
  // -------------------------------------------------------------------------
  function finishRace() {
    race.state = 'finished';
    updateStandings();
    const rows = new Array(shipCount);
    const winnerEntry = standings[0];
    const winnerTime = winnerEntry && winnerEntry.ship.finished ? winnerEntry.ship.finishTime : null;
    for (let k = 0; k < shipCount; k++) {
      const entry = standings[k];
      const ship = entry.ship;
      const totalTime = ship.finished ? ship.finishTime : null;
      rows[k] = {
        pos: k + 1,
        ship,
        name: ship.name || 'PILOTE',
        color: ship.color,
        isPlayer: !!ship.isPlayer,
        finished: !!ship.finished,
        laps: ship.lap || 0,
        totalTime,
        bestLap: ship.bestLap === undefined ? null : ship.bestLap,
        gap: totalTime !== null && winnerTime !== null ? totalTime - winnerTime : null,
        lapTimes: Array.isArray(ship.lapTimes) ? ship.lapTimes.slice() : [],
      };
    }
    race.results = rows;
    race.winner = winnerEntry ? winnerEntry.ship : null;
    race.countdownText = null;
    events.raceOver = true;
  }

  // -------------------------------------------------------------------------
  // Manual respawn (bound to the respawn key by main.js)
  // -------------------------------------------------------------------------
  function requestRespawn(ship) {
    const target = ship || playerShip;
    if (!target || target.finished) return false;
    const i = ships.indexOf(target);
    if (i < 0) return false;
    if (respawnCooldown[i] > 0) return false; // still on cooldown, the key does nothing
    reviveShip(target, i);
    respawnCooldown[i] = RESPAWN_COOLDOWN;
    return true;
  }

  placeOnGrid();
  return race;
}

// ---------------------------------------------------------------------------
// Construction helpers
// ---------------------------------------------------------------------------

/**
 * Checkpoints sorted by distance from the start line, which is the order a
 * craft meets them during a lap. Any checkpoint sitting on the line itself is
 * dropped: it would validate a lap on the crossing that starts it.
 */
function buildCheckpoints(track, startS) {
  const source = Array.isArray(track.checkpoints) ? track.checkpoints : [];
  const list = [];
  for (let i = 0; i < source.length; i++) {
    const s = track.wrapS(source[i]);
    const rel = track.wrapS(s - startS);
    if (rel < 1 || rel > track.length - 1) continue;
    list.push({ s, rel });
  }
  list.sort((a, b) => a.rel - b.rel);
  const out = new Float64Array(list.length);
  for (let i = 0; i < list.length; i++) out[i] = list[i].s;
  return out;
}

/**
 * Maps every AI to its craft. `ai.ship` is used when the AI exposes it, and the
 * remaining AIs are handed out to the non player craft in order.
 */
function bindAIs(ships, ais, aiForShip) {
  const shipCount = ships.length;
  for (let i = 0; i < ais.length; i++) {
    const ai = ais[i];
    if (!ai) continue;
    let idx = ai.ship ? ships.indexOf(ai.ship) : -1;
    if (idx < 0 || aiForShip[idx]) {
      idx = -1;
      for (let k = 0; k < shipCount; k++) {
        if (!ships[k].isPlayer && !aiForShip[k]) {
          idx = k;
          break;
        }
      }
    }
    if (idx >= 0) aiForShip[idx] = ai;
  }
}
