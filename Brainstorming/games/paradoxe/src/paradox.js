/**
 * PARADOXE - divergence detection.
 *
 * A clone is allowed to wobble; it is not allowed to fail. The watch is
 * deliberately asymmetric:
 *
 *  - strict on marking events (grab, drop, teleport, stepping on or off a
 *    button): if the tape says "clone 2 stepped on button 1 at tick 140" and
 *    the replay has not produced that event 22 ticks later, the timeline is
 *    broken and we say so,
 *  - lenient on everything else: extra events are ignored, and position only
 *    counts as proof when the clone has been more than driftRadius off its own
 *    recorded path for driftTicks in a row (that is what catches "the player
 *    stood in the doorway and the clone is stuck against him").
 */

import { SIM } from './config.js';
import { isMarkingEvent, posAt } from './recorder.js';

const scratch = { x: 0, y: 0, z: 0 };

function describe(key) {
  if (key.startsWith('b+')) return 'atteindre son bouton';
  if (key.startsWith('b-')) return 'quitter son bouton';
  if (key.startsWith('grab')) return 'attraper sa caisse';
  if (key.startsWith('drop')) return 'poser sa caisse';
  if (key.startsWith('tp')) return 'prendre le teleporteur';
  return 'refaire son geste';
}

export function createParadoxWatch() {
  /** One entry per clone: { expected, head, drift }. */
  const lanes = [];
  const watch = {
    lanes,
    failure: null,
  };

  watch.reset = function reset(recordings) {
    lanes.length = 0;
    watch.failure = null;
    for (let i = 0; i < recordings.length; i++) {
      const rec = recordings[i];
      const expected = [];
      for (let k = 0; k < rec.events.length; k++) {
        const e = rec.events[k];
        if (!isMarkingEvent(e.key) || e.key === 'exit') continue;
        expected.push({ tick: e.tick, key: e.key, matched: false });
      }
      lanes.push({ rec, expected, head: 0, drift: 0 });
    }
  };

  function fail(cloneIndex, text) {
    if (watch.failure) return;
    watch.failure = { clone: cloneIndex, text };
  }

  /** Route one simulation event. actorIndex 0 is the live player. */
  watch.onEvent = function onEvent(actorIndex, key, tick) {
    if (actorIndex < 1) return;
    const lane = lanes[actorIndex - 1];
    if (!lane) return;
    if (key === 'fall') {
      fail(actorIndex - 1, 'Le clone ' + actorIndex + ' est tombe dans le vide.');
      return;
    }
    if (!isMarkingEvent(key)) return;
    let best = -1;
    let bestD = SIM.eventTolerance + 1;
    for (let i = 0; i < lane.expected.length; i++) {
      const e = lane.expected[i];
      if (e.matched || e.key !== key) continue;
      const d = Math.abs(e.tick - tick);
      if (d <= SIM.eventTolerance && d < bestD) {
        bestD = d;
        best = i;
      }
    }
    if (best >= 0) lane.expected[best].matched = true;
  };

  /** Called once per simulation tick, after the step. */
  watch.update = function update(sim) {
    if (watch.failure) return watch.failure;
    const t = sim.tick;
    for (let i = 0; i < lanes.length; i++) {
      const lane = lanes[i];
      while (lane.head < lane.expected.length && lane.expected[lane.head].tick + SIM.eventTolerance < t) {
        const e = lane.expected[lane.head];
        if (!e.matched) {
          fail(i, 'Le clone ' + (i + 1) + ' n a pas pu ' + describe(e.key) + '.');
          return watch.failure;
        }
        lane.head++;
      }
      const a = sim.actors[i + 1];
      if (!a || !a.active) continue;
      posAt(lane.rec, t - 1, scratch);
      if (Number.isNaN(scratch.x)) continue;
      const dx = a.x - scratch.x;
      const dy = a.y - scratch.y;
      const dz = a.z - scratch.z;
      const d2 = dx * dx + dy * dy + dz * dz;
      if (d2 > SIM.driftRadius * SIM.driftRadius) {
        lane.drift++;
        if (lane.drift > SIM.driftTicks) {
          fail(i, 'Le clone ' + (i + 1) + ' a ete detourne de sa trajectoire.');
          return watch.failure;
        }
      } else if (lane.drift > 0) {
        lane.drift--;
      }
    }
    return null;
  };

  /** 0..1 per clone, how close it is to breaking. Drives the glitch shader. */
  watch.stress = function stress(cloneIndex) {
    const lane = lanes[cloneIndex];
    if (!lane) return 0;
    const v = lane.drift / SIM.driftTicks;
    return v > 1 ? 1 : v;
  };

  return watch;
}
