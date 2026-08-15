/** Thin wrapper over the DOM overlay. No frameworks, just element updates. */
export class Hud {
  constructor() {
    this.el = {
      hud: document.getElementById('hud'),
      health: document.getElementById('health-value'),
      healthBar: document.getElementById('health-bar'),
      weapon: document.getElementById('weapon-name'),
      ammo: document.getElementById('ammo-value'),
      reserve: document.getElementById('ammo-reserve'),
      detect: document.getElementById('detect-fill'),
      detectWrap: document.getElementById('detect'),
      detectLabel: document.getElementById('detect-label'),
      objective: document.getElementById('objective-text'),
      cams: document.getElementById('cams-value'),
      guards: document.getElementById('guards-value'),
      lockdown: document.getElementById('lockdown'),
      lockdownLabel: document.getElementById('lockdown-label'),
      lockdownTime: document.getElementById('lockdown-time'),
      lockdownFill: document.getElementById('lockdown-fill'),
      toast: document.getElementById('toast'),
      prompt: document.getElementById('prompt'),
      subtitle: document.getElementById('subtitle'),
      crosshair: document.getElementById('crosshair'),
      hitmarker: document.getElementById('hitmarker'),
      damage: document.getElementById('damage-flash'),
      disguise: document.getElementById('disguise-chip'),
      compass: document.getElementById('compass'),
      zone: document.getElementById('zone-name'),
    };
    this._toasts = [];
    this._hitT = 0;
    this._lastZone = null;
  }

  show(v) { this.el.hud.classList.toggle('hidden', !v); }

  setSubtitle(text) {
    const el = this.el.subtitle;
    if (!text) {
      el.classList.add('hidden');
      el.textContent = '';
      return;
    }
    el.classList.remove('hidden');
    el.innerHTML = text.split('\n').map((l) => `<span>${l || '&nbsp;'}</span>`).join('');
  }

  toast(text, kind = 'info') {
    const div = document.createElement('div');
    div.className = `toast-line toast-${kind}`;
    div.textContent = text;
    this.el.toast.prepend(div);
    this._toasts.push({ div, t: 0 });
    while (this._toasts.length > 5) {
      const old = this._toasts.shift();
      old.div.remove();
    }
  }

  hit(kill = false) {
    this._hitT = kill ? 0.35 : 0.18;
    this.el.hitmarker.classList.toggle('kill', kill);
  }

  setPrompt(text) {
    this.el.prompt.textContent = text || '';
    this.el.prompt.classList.toggle('hidden', !text);
  }

  setZone(name) {
    if (name === this._lastZone) return;
    this._lastZone = name;
    if (!name) return;
    this.el.zone.textContent = name;
    this.el.zone.classList.remove('fade');
    // restart the CSS fade
    void this.el.zone.offsetWidth;
    this.el.zone.classList.add('fade');
  }

  update(dt, state) {
    const {
      player, arsenal, detection, alerted, camsLeft, camsTotal, objective, disguised,
      guardsLeft, guardsTotal, callers, lockdownLeft, lockdownFrac,
    } = state;

    const hp = Math.max(0, Math.round(player.health));
    this.el.health.textContent = hp;
    this.el.healthBar.style.width = `${(hp / player.maxHealth) * 100}%`;
    this.el.healthBar.classList.toggle('low', hp <= 35);

    const w = arsenal.weapon;
    if (w) {
      this.el.weapon.textContent = w.name;
      this.el.ammo.textContent = arsenal.mag[w.id];
      this.el.reserve.textContent = `/ ${arsenal.reserve[w.id]}`;
      this.el.ammo.classList.toggle('empty', arsenal.mag[w.id] === 0);
    } else {
      this.el.weapon.textContent = 'MAINS NUES';
      this.el.ammo.textContent = '--';
      this.el.reserve.textContent = '';
      this.el.ammo.classList.remove('empty');
    }

    const pct = Math.round(detection * 100);
    this.el.detect.style.width = `${pct}%`;
    const level = alerted ? 'alert' : (detection > 0.6 ? 'high' : detection > 0.05 ? 'mid' : 'calm');
    this.el.detectWrap.dataset.level = level;
    this.el.detectLabel.textContent = alerted
      ? 'ALERTE - NEUTRALISEZ LE GARDE'
      : detection > 0.05 ? 'REPERAGE EN COURS' : 'DISCRETION';
    // Lockdown countdown. Visible whenever the clock is running or winding
    // back, so the player can always see how long they have and that dealing
    // with the callers actually buys the time back.
    const showLockdown = callers > 0 || lockdownFrac > 0.01;
    this.el.lockdown.classList.toggle('hidden', !showLockdown);
    if (showLockdown) {
      this.el.lockdownFill.style.width = `${Math.min(100, lockdownFrac * 100)}%`;
      this.el.lockdown.dataset.state = callers > 0 ? 'calling' : 'recovering';
      if (callers > 0) {
        this.el.lockdownLabel.textContent = callers > 1
          ? `ALERTE RADIO x${callers}`
          : 'ALERTE RADIO';
        this.el.lockdownTime.textContent = `${Math.max(0, lockdownLeft).toFixed(1)}s`;
      } else {
        this.el.lockdownLabel.textContent = 'APPEL INTERROMPU';
        this.el.lockdownTime.textContent = '';
      }
    }

    this.el.cams.textContent = `${camsTotal - camsLeft}/${camsTotal}`;
    // The roster never refills, so this only ever counts down.
    this.el.guards.textContent = `${guardsLeft}/${guardsTotal}`;
    this.el.guards.classList.toggle('cleared', guardsLeft === 0);
    this.el.objective.textContent = objective;
    this.el.disguise.classList.toggle('hidden', !disguised);

    this.el.damage.style.opacity = player.damageFlash.toFixed(3);

    if (this._hitT > 0) {
      this._hitT -= dt;
      this.el.hitmarker.classList.remove('hidden');
      if (this._hitT <= 0) this.el.hitmarker.classList.add('hidden');
    }

    for (const t of this._toasts) {
      t.t += dt;
      if (t.t > 3.2) t.div.style.opacity = Math.max(0, 1 - (t.t - 3.2) / 0.8);
    }
    while (this._toasts.length && this._toasts[0].t > 4.2) {
      this._toasts.shift().div.remove();
    }
  }

  /** Small arrow pointing at the current objective marker. */
  setCompass(angleRad, distance, visible) {
    const el = this.el.compass;
    el.classList.toggle('hidden', !visible);
    if (!visible) return;
    el.style.transform = `translateX(-50%) rotate(${angleRad}rad)`;
    el.dataset.distance = `${Math.round(distance)}m`;
  }

  reset() {
    this._toasts.forEach((t) => t.div.remove());
    this._toasts = [];
    this._lastZone = null;
    this.setPrompt('');
    this.el.hitmarker.classList.add('hidden');
    this.el.lockdown.classList.add('hidden');
  }
}
