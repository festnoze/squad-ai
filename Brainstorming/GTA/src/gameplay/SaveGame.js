/**
 * Save / load.
 *
 * Persists to localStorage. The world itself is never saved - it is regenerated from a
 * fixed seed, so it is identical every run and storing it would be several megabytes of
 * redundancy. What gets saved is only what the player changed: progress, money, loadout,
 * where they were standing and what time it was.
 *
 * Saves are versioned. A save from an older build loads what it can and ignores the rest
 * rather than throwing, because a corrupt or stale save should cost you your progress at
 * worst - never the ability to start the game.
 */

const KEY = 'liberty-horizon:save:v1';
const VERSION = 1;
const AUTOSAVE_SECONDS = 60;

export class SaveGame {
  /**
   * @param {object} game the root Game instance
   */
  constructor(game) {
    this.game = game;
    this.autosaveTimer = AUTOSAVE_SECONDS;
    this.lastSavedAt = null;
    this.enabled = true;
  }

  /** Collect the mutable state worth persisting. */
  serialise() {
    const g = this.game;
    const car = g.traffic.playerVehicle;
    return {
      version: VERSION,
      savedAt: new Date().toISOString(),
      money: g.money,
      timeOfDay: g.atmosphere.timeOfDay,
      weather: g.weather?.target ?? 'clear',
      player: {
        x: g.player.position.x,
        y: g.player.position.y,
        z: g.player.position.z,
        yaw: g.player.yaw,
        health: g.player.health,
        armour: g.player.armour,
        // Never restore the player inside a vehicle: the specific car will not exist
        // after a regenerate, so they would end up welded to nothing.
        inVehicle: !!car,
      },
      weapons: {
        current: g.weapons.current,
        owned: [...g.weapons.owned],
        ammo: g.weapons.ammo,
      },
      missions: {
        completed: g.missions.missions
          .filter((m) => m.state === 'complete')
          .map((m) => m.id),
        earned: g.missions.earned,
      },
      stats: {
        kills: g.weapons.kills,
        knockdowns: g.peds.knockdowns,
        pickups: g.pickups.collected,
        busted: g.wanted.busted,
      },
    };
  }

  save() {
    if (!this.enabled) return false;
    try {
      localStorage.setItem(KEY, JSON.stringify(this.serialise()));
      this.lastSavedAt = Date.now();
      return true;
    } catch (err) {
      // Private browsing and full quotas both throw here; neither should break the game.
      console.warn('[SaveGame] could not write save:', err.message);
      this.enabled = false;
      return false;
    }
  }

  /** @returns {object|null} */
  read() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (!data || data.version !== VERSION) return null;
      return data;
    } catch (err) {
      console.warn('[SaveGame] save unreadable, ignoring:', err.message);
      return null;
    }
  }

  get exists() { return this.read() !== null; }

  /**
   * Apply a save to the live game. Every field is optional; anything missing keeps its
   * current value, so a partial or older save still loads.
   */
  load() {
    const data = this.read();
    if (!data) return false;
    const g = this.game;

    if (typeof data.money === 'number') g.money = data.money;
    if (typeof data.timeOfDay === 'number') g.atmosphere.timeOfDay = data.timeOfDay;
    if (data.weather && g.weather) g.weather.set(data.weather, { auto: true });

    if (data.player) {
      const p = data.player;
      // If they saved while driving, put them back on foot at the same spot.
      if (g.traffic.playerVehicle) g.traffic.exit(g.player);
      if (typeof p.x === 'number') {
        g.player.teleport(new g.player.position.constructor(p.x, p.y, p.z), p.yaw ?? 0);
      }
      if (typeof p.health === 'number') g.player.health = p.health;
      if (typeof p.armour === 'number') g.player.armour = p.armour;
    }

    if (data.weapons) {
      const w = data.weapons;
      if (Array.isArray(w.owned)) {
        for (const kind of w.owned) if (g.weapons.ammo[kind]) g.weapons.owned.add(kind);
      }
      if (w.ammo) {
        for (const [kind, state] of Object.entries(w.ammo)) {
          if (!g.weapons.ammo[kind] || !state) continue;
          g.weapons.ammo[kind].magazine = state.magazine ?? 0;
          g.weapons.ammo[kind].reserve = state.reserve ?? 0;
        }
      }
      if (w.current && g.weapons.owned.has(w.current)) g.weapons.select(w.current);
    }

    if (data.missions) {
      const done = new Set(data.missions.completed ?? []);
      for (const m of g.missions.missions) {
        if (!done.has(m.id)) continue;
        m.state = 'complete';
        g.missions.startMarkers.get(m.id)?.hide();
      }
      g.missions.completed = done.size;
      g.missions.earned = data.missions.earned ?? 0;
    }

    if (data.stats) {
      g.weapons.kills = data.stats.kills ?? 0;
      g.peds.knockdowns = data.stats.knockdowns ?? 0;
      g.pickups.collected = data.stats.pickups ?? 0;
      g.wanted.busted = data.stats.busted ?? 0;
    }

    // A fresh start after loading: no lingering heat from before the save.
    g.wanted.clear();
    return true;
  }

  clear() {
    try { localStorage.removeItem(KEY); } catch { /* nothing to do */ }
  }

  /** Autosave on a timer. Call once per frame. */
  update(dt) {
    if (!this.enabled) return;
    this.autosaveTimer -= dt;
    if (this.autosaveTimer > 0) return;
    this.autosaveTimer = AUTOSAVE_SECONDS;
    // Do not autosave mid-mission: reloading into a half-finished objective chain would
    // restore progress the mission state machine has no way to resume.
    if (this.game.missions.active) return;
    this.save();
  }

  /** Human-readable summary for the pause menu. */
  describe() {
    const data = this.read();
    if (!data) return 'no save';
    const when = new Date(data.savedAt);
    const money = `$${Math.floor(data.money ?? 0).toLocaleString('en-US')}`;
    const done = data.missions?.completed?.length ?? 0;
    return `${when.toLocaleTimeString()} - ${money}, ${done} missions`;
  }
}
