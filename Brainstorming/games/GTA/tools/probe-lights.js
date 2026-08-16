/*
 * Traffic-signal probe.
 *
 * Measures, over 120 s of *simulation* time (never wall clock - the fixed loop drops steps
 * under load, so a wall-clock window is a third of the game it claims to be):
 *
 *   - whether AI cars actually come to a stop behind the stop line on a red approach,
 *   - whether the crossing axis keeps moving while they do,
 *   - junction throughput, which is what a gridlock would destroy,
 *   - the city-wide flowing count, which must not regress past the 23.8/28 baseline,
 *   - and that the painted lens agrees with the phase the cars are obeying.
 *
 * Speeds are sampled in a band 12 m deep in front of the stop line rather than over the
 * whole approach. A car 30 m back from a red has not been asked to slow down yet - the
 * braking curve is still above its cruising speed there - so averaging it in dilutes the
 * red/green difference to nothing and measures sight distance, not obedience.
 *
 * Run it twice - once plain, once with `&lights=off` in the URL, which detaches the signal
 * reference from the autopilot - for a with/without pair from identical conditions.
 */
(async () => {
const g = window.game, E = g.engine;
const log = []; const T0 = performance.now();
const BUDGET = 560000;
const ok = (n, c, x) => log.push({ step: n, pass: !!c, ...(x !== undefined ? { info: String(x) } : {}) });
let simT = 0; E.fixedCallbacks.push((dt) => { simT += dt; });
const wait = async (sec) => { const t = simT + sec;
  while (simT < t && performance.now() - T0 < BUDGET) await new Promise(r => requestAnimationFrame(r)); };
const out = () => performance.now() - T0 > BUDGET;
const r1 = (v) => Number(v.toFixed(1));

const LIGHTS_OFF = new URLSearchParams(location.search).get('lights') === 'off';
if (LIGHTS_OFF) g.traffic.trafficLights = null;

const props = g.props, net = g.city.network, traffic = g.traffic;
const BAND = 12;        // depth of the stop-line sampling band, metres
/*
 * The city-wide flow figure is taken over the first 120 s, which is the acceptance window.
 * Junction behaviour is measured over the whole run, which defaults to twice that: signals
 * sit on 36 of 534 junctions, so a wandering car meets one about every ninth crossing and
 * 120 s of a 28-car city yields anywhere from 6 to 23 approaches to a red. Three 120 s runs
 * measured 97, 266 and 304 stop-line samples from identical code - a spread wide enough to
 * flip a threshold on luck alone, which is not a measurement.
 */
const WINDOW = Number(new URLSearchParams(location.search).get('win')) || 240;
const ACCEPT = 120;
const WARMUP = 8, SAMPLE = 0.2;

/* ------------------------------------------------------- the cycle and the lenses */
/*
 * The lens colours are what the player reads, and they are painted from the same clock the
 * cars steer by. Checking them by sampling one head across a full cycle proves the two
 * halves cannot drift: an argmax over the three lens brightnesses has to be the phase.
 */
const lensArr = props.lensColours ? props.lensColours.array : null;
const litLens = (s) => {
  const per = (s.vertexEnd - s.vertexStart) / 3;
  let best = -1, bestL = -1;
  for (let i = 0; i < 3; i++) {
    const v = s.vertexStart + i * per;
    const l = lensArr[v * 3] + lensArr[v * 3 + 1] + lensArr[v * 3 + 2];
    if (l > bestL) { bestL = l; best = i; }
  }
  return best;
};
const heads = [props.signals.find((s) => s.axis === 0), props.signals.find((s) => s.axis === 1)];
let lensChecks = 0, lensAgree = 0, bothGreen = 0, phaseSeen = new Set();
const phaseTrace = [];
for (let i = 0; i < 20 && !out(); i++) {
  const p0 = props.signalPhase(0), p1 = props.signalPhase(1);
  phaseSeen.add(`${p0}${p1}`);
  if (p0 === 2 && p1 === 2) bothGreen++;
  if (lensArr) {
    for (let a = 0; a < 2; a++) {
      if (!heads[a]) continue;
      lensChecks++;
      if (litLens(heads[a]) === (a === 0 ? p0 : p1)) lensAgree++;
    }
  }
  phaseTrace.push(`${p0}${p1}`);
  await wait(1);
}

/* ------------------------------------------------------------------ the long window */

// Count stuck-recovery teleports. A signal implementation that gridlocks shows up here
// long before it shows up in the flowing count: every dead queue ends in a teleport.
let teleports = 0;
const clearSpot = traffic._clearSpotAhead.bind(traffic);
traffic._clearSpotAhead = (...a) => { teleports++; return clearSpot(...a); };

/** Where a car sits on its approach, in exactly the terms `_driveAI` uses. */
const approach = (v, st) => {
  const e = st.edge, a = net.nodes[e.a], b = net.nodes[e.b];
  const vx = b.x - a.x, vz = b.z - a.z;
  const len2 = vx * vx + vz * vz;
  let t = ((v.position.x - a.x) * vx + (v.position.z - a.z) * vz) / len2;
  t = t < 0 ? 0 : t > 1 ? 1 : t;
  const along = st.forward ? t : 1 - t;
  const toNode = (1 - along) * e.length;
  return {
    node: st.forward ? e.b : e.a,
    axis: e.axis === 'x' ? 0 : 1,
    toLine: toNode - (e.type.width / 2 + 3.5),
  };
};

const M = {
  samples: 0, carSamples: 0, flowSum: 0, speedSum: 0,
  samples120: 0, flowSum120: 0, speedSum120: 0, carSamples120: 0, teleports120: 0,
  redN: 0, redSpeed: 0, redStopped: 0, greenN: 0, greenSpeed: 0, freeN: 0, freeSpeed: 0,
  boxStall: 0, maxHold: 0,
  crossN: [0, 0, 0], crossSpeed: [0, 0, 0], runners: 0,
  metRed: 0, metRedStopped: 0,
};
/** @type {Map<object, object>} one approach episode per car: node, whether it met a red */
const episodes = new Map();
/** @type {Map<object, number>} junctions crossed, per car - the anti-gridlock metric */
const crossings = new Map();
/** @type {Map<number, object>} per-junction picture */
const perNode = new Map();

await wait(WARMUP);
const startTeleports = teleports;

const started = simT;
const until = simT + WINDOW;
while (simT < until && !out()) {
  const inAccept = simT - started < ACCEPT;
  M.samples++;
  let flowing = 0, cars = 0, speeds = 0;
  for (const [v, st] of traffic.ai) {
    if (st.network) continue;              // elevated ring, no junctions to signal
    const kmh = Math.abs(v.speedKmh);
    cars++; speeds += kmh;
    if (kmh > 5) flowing++;
    if (!crossings.has(v)) crossings.set(v, 0);
    if ((st.signalHold ?? 0) > M.maxHold) M.maxHold = st.signalHold;

    const ap = approach(v, st);
    let ep = episodes.get(v);
    if (!ep || ep.node !== ap.node) {
      ep = { node: ap.node, signalled: props.isSignalled(ap.node), prev: ap.toLine,
        metRed: false, stopped: false, crossed: false };
      episodes.set(v, ep);
    }
    /*
     * Junctions crossed is counted at every junction, signalled or not: it is the
     * anti-gridlock metric and its baseline (12.7 per car per 120 s with the signals
     * detached) only means anything if both sides count the same thing.
     */
    const crossedNow = !ep.crossed && ep.prev > 0 && ap.toLine <= 0;
    if (crossedNow) { ep.crossed = true; crossings.set(v, crossings.get(v) + 1); }

    if (ep.signalled) {
      const phase = props.signalPhase(ap.axis);
      let slot = perNode.get(ap.node);
      if (!slot) {
        slot = { redN: 0, redStopped: 0, redSpeed: 0, greenN: 0, greenSpeed: 0,
          freeN: 0, freeSpeed: 0, cross: 0, runners: 0 };
        perNode.set(ap.node, slot);
      }

      // Stop-line band: from 1 m past the line back to BAND metres before it.
      if (ap.toLine >= -1 && ap.toLine <= BAND) {
        if (phase === 2) {
          M.greenN++; M.greenSpeed += kmh; slot.greenN++; slot.greenSpeed += kmh;
          /*
           * Cross traffic *flowing* means a car that arrived on a green and kept going.
           * A car pulling away from the queue it joined at a red is also on a green and
           * also in this band, and at a busy junction it dominates: node 267 read 8.8 km/h
           * on green from 33 samples that were mostly departing queues, while the city-wide
           * figure over the same run was 23.8. Excluding approaches that met a red measures
           * the claim rather than the queue's own recovery.
           */
          if (!ep.metRed) { M.freeN++; M.freeSpeed += kmh; slot.freeN++; slot.freeSpeed += kmh; }
        } else {
          M.redN++; M.redSpeed += kmh; slot.redN++; slot.redSpeed += kmh;
          ep.metRed = true;
          if (kmh < 2) { M.redStopped++; slot.redStopped++; ep.stopped = true; }
        }
      }
      // Stalled well past the stop line is a car parked in the junction itself - the
      // failure mode that would block the axis that just went green.
      if (kmh < 2 && ap.toLine < -1.5) M.boxStall++;

      if (crossedNow) {
        M.crossN[phase]++; M.crossSpeed[phase] += kmh;
        slot.cross++;
        // A solid red crossed at speed is a car that ignored the light outright. Crossing
        // a red at a crawl is the tail of a stop that overshot the line, which is not the
        // same thing and is what a real car does too.
        if (phase === 0 && kmh > 8) { M.runners++; slot.runners++; }
        if (ep.metRed) { M.metRed++; if (ep.stopped) M.metRedStopped++; }
      }
    }
    ep.prev = ap.toLine;
  }
  M.carSamples += cars;
  M.flowSum += flowing;
  M.speedSum += speeds;
  if (inAccept) {
    M.samples120++; M.carSamples120 += cars; M.flowSum120 += flowing; M.speedSum120 += speeds;
    M.teleports120 = teleports - startTeleports;
  }
  await wait(SAMPLE);
}

/* ---------------------------------------------------------------------- reduction */
const n = Math.max(1, M.samples);
const flowAvg = M.flowSum / n;
const carCount = M.carSamples / n;
const meanSpeed = M.speedSum / Math.max(1, M.carSamples);
// The acceptance pair: flow and mean speed over the first 120 s, on their own.
const flow120 = M.flowSum120 / Math.max(1, M.samples120);
const speed120 = M.speedSum120 / Math.max(1, M.carSamples120);
const redKmh = M.redN ? M.redSpeed / M.redN : 0;
const greenKmh = M.greenN ? M.greenSpeed / M.greenN : 0;
const redStopFrac = M.redN ? M.redStopped / M.redN : 0;
const totalCross = M.crossN[0] + M.crossN[1] + M.crossN[2];
// Every junction crossed, not just the signalled ones - dividing the signalled subtotal by
// the whole fleet is what made this read 0.8 per car on the first pass.
let allCross = 0, stalledCars = 0;
for (const c of crossings.values()) { allCross += c; if (c === 0) stalledCars++; }
const crossPerCar = allCross / Math.max(1, crossings.size);

/*
 * The junction the acceptance test is read off.
 *
 * "Busiest stop lines" is the wrong pick on its own. The claim being read off one junction
 * has two halves - cars stop on a red, cross traffic keeps moving - and the second half is
 * counted only from approaches that arrived on a green without meeting a red first, which
 * is a far thinner stream than the red-band samples. The busiest junction by band traffic
 * measured 3 such samples while the city-wide figure over the same run had hundreds: a
 * junction can be the busiest in town and still say nothing about cross traffic, and the
 * assertion then failed on the probe's sampling rather than on the simulation.
 *
 * So the pick is restricted to junctions that have enough of BOTH to be judged, and the
 * busiest of those wins. If none qualifies the busiest overall is still reported, and the
 * assertion below fails honestly - "no junction saw enough traffic to judge" is a real
 * result about a 240 s window, not a verdict on the signals.
 */
const NODE_RED_MIN = 20, NODE_FREE_MIN = 8;
let best = null, bestId = -1, judgeable = 0;
for (const [id, s] of perNode) {
  if (s.redN < NODE_RED_MIN || s.freeN < NODE_FREE_MIN) continue;
  judgeable++;
  if (!best || s.redN + s.greenN > best.redN + best.greenN) { best = s; bestId = id; }
}
if (!best) {
  for (const [id, s] of perNode) {
    if (!best || s.redN + s.greenN > best.redN + best.greenN) { best = s; bestId = id; }
  }
}
const bestRedStop = best && best.redN ? best.redStopped / best.redN : 0;
const bestGreenKmh = best && best.greenN ? best.greenSpeed / best.greenN : 0;
const bestFreeKmh = best && best.freeN ? best.freeSpeed / best.freeN : 0;
const freeKmh = M.freeN ? M.freeSpeed / M.freeN : 0;

ok('city-wide flow holds the 23.8/28 baseline over the acceptance window', flow120 >= 23.8,
  `${flow120.toFixed(2)} of ${carCount.toFixed(0)} above 5 km/h in the first ${ACCEPT}s, mean ${speed120.toFixed(1)} km/h`);
ok('and holds it over the whole run', flowAvg >= 23.8,
  `${flowAvg.toFixed(2)} of ${carCount.toFixed(0)} over ${WINDOW}s, mean ${meanSpeed.toFixed(1)} km/h`);
ok('cars stop behind the stop line on a red', redStopFrac > 0.45 && redKmh < 8,
  `${(redStopFrac * 100).toFixed(0)}% of ${M.redN} red-band samples stopped, mean ${redKmh.toFixed(1)} km/h`);
ok('cross traffic keeps moving while they wait', freeKmh > 15 && freeKmh > redKmh * 2,
  `cross traffic ${freeKmh.toFixed(1)} km/h over ${M.freeN} samples vs red ${redKmh.toFixed(1)} km/h, all green ${greenKmh.toFixed(1)}`);
/*
 * The episode counts below are deliberately low thresholds. Signals sit on the 36 arterial
 * crossings of 534 junctions, so only about one junction crossing in fifteen city-wide is a
 * signalled one and 120 s of a 28-car city yields tens of approaches, not hundreds. The
 * band-sample statistics are an order of magnitude denser because a car waiting at a red is
 * sampled five times a second, which is why the speed comparison carries the weight here.
 */
ok('an approach that meets a red stops before it crosses', M.metRed > 8 && M.metRedStopped / Math.max(1, M.metRed) > 0.6,
  `${M.metRedStopped} of ${M.metRed} approaches came to a stop first`);
ok('almost nothing crosses a solid red at speed', totalCross > 12 && M.runners / Math.max(1, totalCross) < 0.1,
  `${M.runners} runners of ${totalCross} signalled crossings (green ${M.crossN[2]}, amber ${M.crossN[1]}, red ${M.crossN[0]})`);
ok('nothing parks inside the junction box', M.boxStall < 12,
  `${M.boxStall} car-samples stalled past the line`);
// Both of these are rates, so their thresholds scale with the window rather than being
// numbers that quietly only hold for the default 120 s.
ok('the grid does not gridlock', stalledCars === 0 && crossPerCar > 9 * (WINDOW / 120),
  `${crossPerCar.toFixed(1)} junctions crossed per car in ${WINDOW}s (11.2 per 120 s with the signals detached), ${stalledCars} cars crossed none`);
ok('stuck-recovery churn stays low', teleports - startTeleports < 40 * (WINDOW / 120),
  `${teleports - startTeleports} teleports in ${WINDOW}s (31 per 120 s with the signals detached)`);
ok('one signalled junction shows the whole picture on its own',
  !!best && best.redN >= NODE_RED_MIN && best.freeN >= NODE_FREE_MIN
    && (LIGHTS_OFF || (bestRedStop > 0.4 && bestFreeKmh > 10)),
  best ? `node ${bestId} (best of ${judgeable} junctions with >=${NODE_RED_MIN} red-band and >=${NODE_FREE_MIN} cross samples, of ${perNode.size} signalled seen): ${best.cross} crossings, ${(bestRedStop * 100).toFixed(0)}% of ${best.redN} red-band samples stopped, cross traffic ${bestFreeKmh.toFixed(1)} km/h over ${best.freeN} (all green ${bestGreenKmh.toFixed(1)})`
    : 'no signalled junction saw traffic');
ok('the two axes are never green together', bothGreen === 0 && phaseSeen.size >= 3,
  `phases seen [${[...phaseSeen].sort().join(' ')}]`);
ok('the lit lens agrees with the phase the cars obey', lensChecks > 0 && lensAgree === lensChecks,
  `${lensAgree}/${lensChecks} samples agree`);

return {
  lights: LIGHTS_OFF ? 'off' : 'on',
  simSeconds: Math.round(simT), wallSeconds: Math.round((performance.now() - T0) / 1000),
  samples: M.samples,
  signalHeads: props.signals.length, signalNodes: props.signalNodes.size,
  cityNodes: net.nodes.length,
  acceptWindow: ACCEPT,
  flowing120: Number(flow120.toFixed(2)), meanSpeedKmh120: r1(speed120),
  teleports120: M.teleports120,
  flowing: Number(flowAvg.toFixed(2)), cityCars: Math.round(carCount),
  meanSpeedKmh: r1(meanSpeed),
  redBandKmh: r1(redKmh), greenBandKmh: r1(greenKmh), crossTrafficKmh: r1(freeKmh),
  redBandStoppedPct: Math.round(redStopFrac * 100),
  redBandSamples: M.redN, greenBandSamples: M.greenN,
  approachesMeetingRed: M.metRed, ofWhichStopped: M.metRedStopped,
  signalledCrossings: { green: M.crossN[2], amber: M.crossN[1], red: M.crossN[0], runners: M.runners },
  junctionsPerCar: r1(crossPerCar), carsThatCrossedNothing: stalledCars,
  boxStalls: M.boxStall,
  maxSignalHold: r1(M.maxHold || 0),
  teleports: teleports - startTeleports,
  judgeableJunctions: judgeable, signalledJunctionsSeen: perNode.size,
  busiestJunction: best ? { node: bestId, crossings: best.cross, redBandSamples: best.redN,
    redStoppedPct: Math.round(bestRedStop * 100), crossTrafficKmh: r1(bestFreeKmh),
    crossTrafficSamples: best.freeN, greenBandKmh: r1(bestGreenKmh) } : null,
  lensAgreement: `${lensAgree}/${lensChecks}`,
  phaseTrace: phaseTrace.join(' '),
  passed: log.filter((l) => l.pass).length, total: log.length,
  failures: log.filter((l) => !l.pass), log,
};
})()
