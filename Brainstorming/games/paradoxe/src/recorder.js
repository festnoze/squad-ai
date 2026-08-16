/**
 * PARADOXE - input tapes.
 *
 * A run is stored as raw input, never as a path: one byte of key bits and one
 * byte of quantised camera yaw per simulation tick. Replaying means feeding
 * those bytes back into the same simulation, so a clone is not an animation,
 * it is the same physics running again.
 *
 * `pos` is recorded alongside but is never fed back in: it only serves the
 * rewind animation and the "this clone got blocked" drift check.
 */

/**
 * @param {number} maxTicks capacity, usually level.ticks
 */
export function createRecording(maxTicks) {
  return {
    ticks: 0,
    capacity: maxTicks,
    bits: new Uint8Array(maxTicks),
    yaw: new Uint8Array(maxTicks),
    pos: new Float32Array(maxTicks * 3),
    /** Marking events, in tick order: [{ tick, key }]. */
    events: [],
  };
}

/** Append one tick of input. Positions are filled in afterwards by markPos. */
export function pushTick(rec, bits, yaw) {
  if (rec.ticks >= rec.capacity) return false;
  rec.bits[rec.ticks] = bits;
  rec.yaw[rec.ticks] = yaw;
  rec.ticks++;
  return true;
}

/** Store where the actor ended up after the tick that was just pushed. */
export function markPos(rec, x, y, z) {
  const i = rec.ticks - 1;
  if (i < 0) return;
  rec.pos[i * 3] = x;
  rec.pos[i * 3 + 1] = y;
  rec.pos[i * 3 + 2] = z;
}

export function pushEvent(rec, tick, key) {
  rec.events.push({ tick, key });
}

/** Position at a tick, clamped to the tape. Writes into `out` (no allocation). */
export function posAt(rec, tick, out) {
  if (rec.ticks === 0) {
    out.x = NaN;
    out.y = NaN;
    out.z = NaN;
    return out;
  }
  const t = tick < 0 ? 0 : tick >= rec.ticks ? rec.ticks - 1 : tick;
  out.x = rec.pos[t * 3];
  out.y = rec.pos[t * 3 + 1];
  out.z = rec.pos[t * 3 + 2];
  return out;
}

/**
 * Shrink a finished tape to the ticks actually used. Keeps memory flat when a
 * player rewinds after two seconds of a twenty second level, twenty times.
 */
export function sealRecording(rec) {
  if (rec.ticks === rec.capacity) return rec;
  const out = {
    ticks: rec.ticks,
    capacity: rec.ticks,
    bits: rec.bits.slice(0, rec.ticks),
    yaw: rec.yaw.slice(0, rec.ticks),
    pos: rec.pos.slice(0, rec.ticks * 3),
    events: rec.events,
  };
  return out;
}

/** Human readable summary used by the timeline strip. */
export function eventLabel(key) {
  if (key === 'exit') return 'sortie';
  if (key === 'jump') return 'saut';
  if (key === 'fall') return 'chute';
  if (key.startsWith('grab')) return 'prise';
  if (key.startsWith('drop')) return 'depose';
  if (key.startsWith('tp')) return 'teleport';
  if (key.startsWith('b+')) return 'appui';
  if (key.startsWith('b-')) return 'relache';
  return key;
}

/** Events worth drawing on the timeline and worth checking for paradoxes. */
export function isMarkingEvent(key) {
  return (
    key.startsWith('grab') ||
    key.startsWith('drop') ||
    key.startsWith('tp') ||
    key.startsWith('b+') ||
    key.startsWith('b-') ||
    key === 'exit'
  );
}
