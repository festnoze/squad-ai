/**
 * AIGUILLAGE - pure train simulation, fixed step, no three.js in sight.
 *
 * A train's physical state is `(segmentId, dir, sAbs)`:
 *   dir  = +1 travelling from segment.a to segment.b, -1 the other way
 *   sAbs = absolute progress from node `a`, metres, in [0, segment.length]
 *
 * The routing decision at a switch is taken by `network.resolveArrival`,
 * called fresh every tick and only *acted upon* the tick the front actually
 * reaches the node: this is what makes "the switch position at the moment
 * of crossing decides the route" true without any extra bookkeeping.
 *
 * A double (coupled) train is a single entity with `coupledSecondColor`
 * set: the trailing car is not simulated, it is derived (front position
 * minus one `coupleGap`) purely for spacing and rendering. The moment the
 * front resolves its own arrival at the next node, a brand new, fully
 * independent train is spawned at that derived position: from then on the
 * two halves can be sent to different exits, including by a switch flip
 * that happens between the two crossings.
 */

const DEFAULTS = {
  cruiseSpeed: 9, // m/s
  accel: 4, // m/s^2
  brakeDecel: 5, // m/s^2
  safetyGap: 10, // m, minimum nose to tail gap, same direction
  crashGap: 4, // m, opposite direction collision threshold
  crossingStopMargin: 3, // m short of a closed level crossing barrier
  approachZone: 14, // m, cosmetic slow down window near any node
  coupleGap: 9, // m between the two cars of a double train while coupled
};

export function createTrainSim(network, opts) {
  const params = Object.assign({}, DEFAULTS, opts || {});
  const trains = [];
  let nextId = 1;
  let time = 0;
  let snapshot = [];

  const events = { delivered: [], wrongExit: [], crashed: null };

  function makeTrain(color, segmentId, dir, sAbs, coupledSecondColor) {
    return {
      id: 'tr' + nextId++,
      color,
      segmentId,
      dir,
      sAbs,
      speed: 0,
      state: 'running',
      coupledSecondColor: coupledSecondColor || null,
    };
  }

  function findSpawnSegment(nodeId) {
    for (const seg of network.segments.values()) {
      if (seg.a === nodeId || seg.b === nodeId) return seg;
    }
    return null;
  }

  function ensureSnapshotCapacity(n) {
    while (snapshot.length < n) {
      snapshot.push({ segmentId: '', dir: 1, sAbs: 0, coupledSecondColor: null });
    }
  }

  function spawnRearIfCoupled(train, spawnedThisTick) {
    if (!train.coupledSecondColor) return;
    const rearColor = train.coupledSecondColor;
    train.coupledSecondColor = null;
    const seg = network.segments.get(train.segmentId);
    const rearSAbs = train.sAbs - train.dir * params.coupleGap;
    if (rearSAbs < 0 || rearSAbs > seg.length) return; // rear car not yet fully in the world
    const rear = makeTrain(rearColor, train.segmentId, train.dir, rearSAbs, null);
    rear.speed = train.speed;
    spawnedThisTick.push(rear);
  }

  function stepOne(selfIndex, dt, n, spawnedThisTick) {
    const train = trains[selfIndex];
    if (train.state === 'delivered' || train.state === 'crashed') return;

    const seg = network.segments.get(train.segmentId);
    const distToEnd = train.dir === 1 ? seg.length - train.sAbs : train.sAbs;
    const arrival = network.resolveArrival(train.segmentId, train.dir);
    const mustStopAtEnd = arrival.kind === 'blocked' || arrival.kind === 'siding';

    let stopDist = mustStopAtEnd ? distToEnd : Infinity;

    if (seg.crossing) {
      const aheadDist = train.dir === 1 ? seg.crossing.sAt - train.sAbs : train.sAbs - seg.crossing.sAt;
      if (aheadDist >= -0.2 && network.isCrossingClosed(seg.id, time)) {
        const d = Math.max(0, aheadDist - params.crossingStopMargin);
        if (d < stopDist) stopDist = d;
      }
    }

    for (let i = 0; i < n; i++) {
      if (i === selfIndex) continue;
      const other = snapshot[i];
      if (other.segmentId !== train.segmentId || other.dir !== train.dir) continue;
      const otherPos = other.coupledSecondColor ? other.sAbs - other.dir * params.coupleGap : other.sAbs;
      const gap = train.dir === 1 ? otherPos - train.sAbs : train.sAbs - otherPos;
      if (gap > 0) {
        const d = Math.max(0, gap - params.safetyGap);
        if (d < stopDist) stopDist = d;
      }
    }

    let target = stopDist <= 0 ? 0 : Math.min(params.cruiseSpeed, Math.sqrt(2 * params.brakeDecel * stopDist));
    if (distToEnd < params.approachZone) {
      const f = Math.max(0.45, distToEnd / params.approachZone);
      target = Math.min(target, params.cruiseSpeed * f);
    }
    if (target > train.speed) train.speed = Math.min(target, train.speed + params.accel * dt);
    else train.speed = Math.max(target, train.speed - params.brakeDecel * dt);
    if (train.speed < 0.03 && stopDist < 0.4) train.speed = 0;

    train.sAbs += train.dir * train.speed * dt;
    if (train.dir === 1 && train.sAbs > seg.length) train.sAbs = seg.length;
    if (train.dir === -1 && train.sAbs < 0) train.sAbs = 0;

    const reached = train.dir === 1 ? train.sAbs >= seg.length - 1e-6 : train.sAbs <= 1e-6;
    if (!reached) {
      train.state = train.speed < 0.05 ? 'queued' : 'running';
      return;
    }

    if (arrival.kind === 'blocked') {
      train.speed = 0;
      train.state = 'queued';
      return;
    }
    if (arrival.kind === 'siding') {
      spawnRearIfCoupled(train, spawnedThisTick);
      train.speed = 0;
      train.state = 'parked';
      return;
    }
    if (arrival.kind === 'exit') {
      spawnRearIfCoupled(train, spawnedThisTick);
      if (arrival.color === train.color) events.delivered.push({ id: train.id, color: train.color });
      else events.wrongExit.push({ id: train.id, color: train.color, expected: arrival.color });
      train.state = 'delivered';
      return;
    }
    // through: hand off to the next segment, still moving away from the node
    spawnRearIfCoupled(train, spawnedThisTick);
    train.segmentId = arrival.segmentId;
    train.dir = arrival.dir;
    train.sAbs = arrival.sAbs;
    train.state = 'running';
  }

  function scanCrashes() {
    if (events.crashed) return;
    for (let i = 0; i < trains.length; i++) {
      const a = trains[i];
      if (a.state === 'delivered' || a.state === 'crashed') continue;
      for (let j = i + 1; j < trains.length; j++) {
        const b = trains[j];
        if (b.state === 'delivered' || b.state === 'crashed') continue;
        if (a.segmentId !== b.segmentId || a.dir === b.dir) continue;
        if (Math.abs(a.sAbs - b.sAbs) < params.crashGap) {
          a.state = 'crashed';
          b.state = 'crashed';
          events.crashed = { ids: [a.id, b.id], segmentId: a.segmentId, sAbs: (a.sAbs + b.sAbs) / 2 };
          return;
        }
      }
    }
  }

  const sim = {
    trains,
    events,
    params,

    get time() {
      return time;
    },

    spawnTrain(spec) {
      const seg = findSpawnSegment(spec.nodeId);
      if (!seg) return null;
      const dir = seg.a === spec.nodeId ? 1 : -1;
      const sAbs = dir === 1 ? 0 : seg.length;
      const train = makeTrain(spec.color, seg.id, dir, sAbs, spec.secondColor || null);
      trains.push(train);
      return train.id;
    },

    reverseTrain(trainId) {
      const train = trains.find((t) => t.id === trainId);
      if (!train || train.state !== 'parked') return false;
      train.dir = -train.dir;
      train.state = 'running';
      return true;
    },

    step(dt, paused) {
      time += dt;
      if (paused) return;
      const n = trains.length;
      ensureSnapshotCapacity(n);
      for (let i = 0; i < n; i++) {
        const t = trains[i];
        const s = snapshot[i];
        s.segmentId = t.segmentId;
        s.dir = t.dir;
        s.sAbs = t.sAbs;
        s.coupledSecondColor = t.coupledSecondColor;
      }
      const spawnedThisTick = [];
      for (let i = 0; i < n; i++) stepOne(i, dt, n, spawnedThisTick);
      for (let i = 0; i < spawnedThisTick.length; i++) trains.push(spawnedThisTick[i]);
      scanCrashes();
    },

    clearEvents() {
      events.delivered.length = 0;
      events.wrongExit.length = 0;
      events.crashed = null;
    },

    livingCount() {
      let c = 0;
      for (const t of trains) if (t.state !== 'delivered' && t.state !== 'crashed') c++;
      return c;
    },

    dispose() {
      // Pure simulation state, nothing external to release.
    },
  };

  return sim;
}
