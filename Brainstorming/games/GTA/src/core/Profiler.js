/**
 * Frame profiler.
 *
 * Accumulates wall-clock time per named section and reports a rolling average, so the
 * cost of each subsystem can be read off directly instead of inferred from total frame
 * time. Averaging over a window matters: single-frame samples in a game are dominated by
 * whatever happened to run that frame (a shader compile, a GC pause, a weather change),
 * and optimising against that noise wastes effort on the wrong code.
 *
 * `performance.now()` is cheap but not free, so sections should be coarse - a subsystem,
 * not a loop body.
 */

const WINDOW_SECONDS = 0.5;

export class Profiler {
  constructor() {
    this.enabled = true;
    /** Accumulated milliseconds this window, by section. */
    this._acc = new Map();
    /** Rolling average milliseconds per frame, by section. */
    this.timings = new Map();
    this._open = new Map();
    this._elapsed = 0;
    this._frames = 0;
  }

  begin(name) {
    if (!this.enabled) return;
    this._open.set(name, performance.now());
  }

  end(name) {
    if (!this.enabled) return;
    const start = this._open.get(name);
    if (start === undefined) return;
    this._acc.set(name, (this._acc.get(name) ?? 0) + (performance.now() - start));
    this._open.delete(name);
  }

  /** Time a function and return its result. */
  measure(name, fn) {
    if (!this.enabled) return fn();
    this.begin(name);
    const result = fn();
    this.end(name);
    return result;
  }

  /** Call once per frame with the frame's delta time. */
  frame(dt) {
    if (!this.enabled) return;
    this._frames++;
    this._elapsed += dt;
    if (this._elapsed < WINDOW_SECONDS) return;
    for (const [name, total] of this._acc) {
      this.timings.set(name, total / this._frames);
    }
    this._acc.clear();
    this._elapsed = 0;
    this._frames = 0;
  }

  /** Sections sorted most expensive first. */
  get sorted() {
    return [...this.timings.entries()].sort((a, b) => b[1] - a[1]);
  }

  /** Compact lines for the debug overlay. */
  lines(limit = 6) {
    return this.sorted.slice(0, limit).map(([name, ms]) => `${name.padEnd(10)} ${ms.toFixed(2)}ms`);
  }

  get totalMs() {
    let total = 0;
    for (const ms of this.timings.values()) total += ms;
    return total;
  }
}
