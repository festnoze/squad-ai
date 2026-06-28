import { secondsSinceJ2000 } from "../physics";

/** Simulation clock: maps real wall-clock time to simulated epoch at a given
 *  rate (simulated seconds per real second), with play/pause and seeking. */
export class SimClock {
  unixMs: number;
  running = true;
  /** Simulated seconds advanced per real second. */
  rate: number;

  constructor(unixMs: number = Date.now(), rate = 3600 * 24 * 3) {
    this.unixMs = unixMs;
    this.rate = rate;
  }

  /** Seconds since the J2000 epoch — the time argument for all physics. */
  get tSecJ2000(): number {
    return secondsSinceJ2000(this.unixMs);
  }

  /** Advance by `realDtSeconds` of wall-clock time (no-op when paused). */
  advance(realDtSeconds: number): void {
    if (this.running) this.unixMs += this.rate * realDtSeconds * 1000;
  }

  setDate(unixMs: number): void {
    this.unixMs = unixMs;
  }

  get date(): Date {
    return new Date(this.unixMs);
  }
}
