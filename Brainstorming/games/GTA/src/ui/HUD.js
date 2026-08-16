/**
 * HUD. Thin wrapper over the DOM nodes declared in index.html.
 *
 * Everything writes through setters that early-out when the value has not changed, so the
 * HUD costs nothing on frames where nothing happened.
 */

export class HUD {
  constructor() {
    this.root = document.getElementById('hud');
    this.el = {
      health: document.getElementById('bar-health'),
      armour: document.getElementById('bar-armour'),
      money: document.getElementById('money'),
      clock: document.getElementById('clock'),
      wanted: document.getElementById('wanted'),
      speedo: document.getElementById('speedo'),
      speed: document.getElementById('speed-value'),
      gear: document.getElementById('gear-value'),
      objective: document.getElementById('objective'),
      objectiveTitle: document.getElementById('objective-title'),
      objectiveText: document.getElementById('objective-text'),
      subtitle: document.getElementById('subtitle'),
      prompt: document.getElementById('prompt'),
      stats: document.getElementById('stats'),
      minimap: document.getElementById('minimap-canvas'),
      crosshair: document.getElementById('crosshair'),
      weapon: document.getElementById('weapon'),
    };
    this._cache = {};
    this._subtitleTimer = 0;
    this.showStats = true;
  }

  show() { this.root.hidden = false; }
  hide() { this.root.hidden = true; }

  _set(key, el, text) {
    if (this._cache[key] === text) return;
    this._cache[key] = text;
    el.textContent = text;
  }

  _width(key, el, pct) {
    const v = `${Math.max(0, Math.min(100, pct)).toFixed(1)}%`;
    if (this._cache[key] === v) return;
    this._cache[key] = v;
    el.style.width = v;
  }

  setVitals(health, armour) {
    this._width('health', this.el.health, health);
    this._width('armour', this.el.armour, armour);
  }

  /**
   * Breath meter, shown only while the lungs are anything less than full.
   *
   * The row is built on demand rather than declared in index.html, the same way the damage
   * flash is: it is the one bar that is off screen most of the time, and keeping it out of
   * the static markup keeps that markup to the things that are always there.
   *
   * @param {number} fraction 0-1 air remaining
   */
  setBreath(fraction) {
    if (fraction >= 0.999) {
      if (this._breathRow && !this._breathRow.hidden) this._breathRow.hidden = true;
      return;
    }
    if (!this._breathRow) {
      const row = document.createElement('div');
      row.className = 'row-breath';
      const fill = document.createElement('i');
      fill.id = 'bar-breath';
      row.appendChild(fill);
      document.getElementById('bars').appendChild(row);
      this._breathRow = row;
      this.el.breath = fill;
    }
    if (this._breathRow.hidden) this._breathRow.hidden = false;
    this._width('breath', this.el.breath, fraction * 100);
    // Below a quarter the bar goes red and pulses: the drain is silent otherwise, and by
    // the time the health bar starts moving it is already too late to turn back.
    const low = fraction < 0.25;
    if (this._cache.breathLow !== low) {
      this._cache.breathLow = low;
      this.el.breath.classList.toggle('low', low);
    }
  }

  setMoney(amount) {
    this._set('money', this.el.money, `$${Math.floor(amount).toLocaleString('en-US')}`);
  }

  setClock(text) { this._set('clock', this.el.clock, text); }

  setWanted(stars) {
    this._set('wanted', this.el.wanted, '★'.repeat(Math.min(5, stars)));
  }

  /** @param {number|null} speedKmh null hides the speedometer */
  setVehicle(speedKmh, gearLabel) {
    if (speedKmh === null) {
      if (!this.el.speedo.hidden) this.el.speedo.hidden = true;
      return;
    }
    if (this.el.speedo.hidden) this.el.speedo.hidden = false;
    this._set('speed', this.el.speed, String(Math.round(speedKmh)));
    this._set('gear', this.el.gear, gearLabel);
  }

  setObjective(title, text) {
    if (!title) {
      if (!this.el.objective.hidden) this.el.objective.hidden = true;
      return;
    }
    if (this.el.objective.hidden) this.el.objective.hidden = false;
    this._set('objTitle', this.el.objectiveTitle, title);
    this._set('objText', this.el.objectiveText, text ?? '');
  }

  /**
   * Red edge flash when the player takes a hit.
   *
   * Being shot at from off-screen is otherwise only visible as the health bar ticking
   * down in the corner, which is not where anyone is looking during a chase.
   */
  flashDamage(strength = 1) {
    if (!this._damageEl) {
      const el = document.createElement('div');
      el.id = 'damage-flash';
      document.body.appendChild(el);
      this._damageEl = el;
    }
    this._damageTimer = Math.min(0.5, 0.28 * strength);
    this._damageEl.style.opacity = String(Math.min(0.6, 0.42 * strength));
  }

  /** Transient centre-screen line, e.g. mission dialogue. */
  say(text, seconds = 3.5) {
    this.el.subtitle.textContent = text;
    this.el.subtitle.hidden = false;
    this._subtitleTimer = seconds;
  }

  /** Context action hint, e.g. "F Enter vehicle". */
  setPrompt(key, label) {
    if (!label) {
      if (!this.el.prompt.hidden) this.el.prompt.hidden = true;
      this._cache.prompt = null;
      return;
    }
    const html = `<kbd>${key}</kbd>${label}`;
    if (this._cache.prompt !== html) {
      this._cache.prompt = html;
      this.el.prompt.innerHTML = html;
    }
    if (this.el.prompt.hidden) this.el.prompt.hidden = false;
  }

  /** Weapon readout and crosshair. Pass null to hide both. */
  setWeapon(text, showCrosshair) {
    if (!text) {
      if (!this.el.weapon.hidden) this.el.weapon.hidden = true;
    } else {
      if (this.el.weapon.hidden) this.el.weapon.hidden = false;
      this._set('weapon', this.el.weapon, text);
    }
    this.el.crosshair.hidden = !showCrosshair;
  }

  setStats(lines) {
    if (!this.showStats) {
      this._set('stats', this.el.stats, '');
      return;
    }
    this._set('stats', this.el.stats, lines.join('\n'));
  }

  update(dt) {
    if (this._subtitleTimer > 0) {
      this._subtitleTimer -= dt;
      if (this._subtitleTimer <= 0) this.el.subtitle.hidden = true;
    }
    if (this._damageTimer > 0) {
      this._damageTimer -= dt;
      const el = this._damageEl;
      if (el) {
        el.style.opacity = this._damageTimer > 0
          ? String(Math.max(0, Number(el.style.opacity) - dt * 1.6))
          : '0';
      }
    }
  }
}

/** Loading screen controller, used before the HUD exists. */
export class LoadingScreen {
  constructor() {
    this.root = document.getElementById('loading');
    this.bar = document.getElementById('loading-bar');
    this.status = document.getElementById('loading-status');
  }

  /** @param {number} pct 0-100 @param {string} label */
  set(pct, label) {
    this.bar.style.width = `${pct}%`;
    if (label) this.status.textContent = label;
  }

  /** Yield to the browser so the bar actually repaints between heavy build steps. */
  async step(pct, label) {
    this.set(pct, label);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  }

  finish() {
    this.root.classList.add('gone');
    setTimeout(() => { this.root.hidden = true; }, 700);
  }

  fail(message) {
    this.status.textContent = message;
    this.status.style.color = '#e5383b';
    this.bar.style.background = '#e5383b';
  }
}
