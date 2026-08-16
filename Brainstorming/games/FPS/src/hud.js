/** All DOM-side HUD state. The 3D layer never touches the document directly. */
export class HUD {
  constructor() {
    const $ = (id) => document.getElementById(id);
    this.el = {
      hud: $('hud'),
      crosshair: $('crosshair'),
      hitmarker: $('hitmarker'),
      dmgDirs: $('dmg-dirs'),
      damageFlash: $('damage-flash'),
      lowHealth: $('lowhealth'),
      wave: $('wave-value'),
      enemies: $('enemies-value'),
      score: $('score-value'),
      banner: $('banner'),
      bannerTitle: $('banner-title'),
      bannerSub: $('banner-sub'),
      toasts: $('toasts'),
      hpFill: $('hp-fill'),
      hpGhost: $('hp-ghost'),
      hpNum: $('hp-num'),
      statusRow: $('status-row'),
      ammoMag: $('ammo-mag'),
      ammoReserve: $('ammo-reserve'),
      reloadBar: document.querySelector('.reload-bar'),
      reloadFill: $('reload-fill'),
      reloadText: $('reload-text'),
      killfeed: $('killfeed'),
      screens: {
        loading: $('screen-loading'),
        menu: $('screen-menu'),
        pause: $('screen-pause'),
        gameover: $('screen-gameover'),
        error: $('screen-error'),
      },
    };
    this.hitmarkerTimer = 0;
    this.bannerTimer = 0;
    this.dirIndicators = [];
    this._lastAmmo = -1;
  }

  showHUD(visible) {
    this.el.hud.classList.toggle('hidden', !visible);
  }

  showScreen(name) {
    for (const [key, el] of Object.entries(this.el.screens)) {
      if (!el) continue;
      el.classList.toggle('hidden', key !== name);
    }
  }

  error(message) {
    const t = document.getElementById('error-text');
    if (t) t.textContent = message;
    this.showScreen('error');
  }

  hitmarker(isHead, isKill) {
    const hm = this.el.hitmarker;
    hm.classList.remove('show', 'kill', 'head');
    // restart the CSS state cleanly
    void hm.offsetWidth;
    hm.classList.add('show');
    if (isKill) hm.classList.add('kill');
    else if (isHead) hm.classList.add('head');
    this.hitmarkerTimer = isKill ? 0.22 : 0.12;
  }

  killLine(label, isHead) {
    const div = document.createElement('div');
    div.className = 'kill-line' + (isHead ? ' head' : '');
    div.innerHTML = `${isHead ? 'HEADSHOT ' : ''}<b>${label}</b> DOWN`;
    this.el.killfeed.appendChild(div);
    setTimeout(() => div.remove(), 3800);
    while (this.el.killfeed.children.length > 5) this.el.killfeed.firstChild.remove();
  }

  toast(text, kind = '') {
    const div = document.createElement('div');
    div.className = 'toast ' + kind;
    div.textContent = text;
    this.el.toasts.appendChild(div);
    setTimeout(() => div.remove(), 2200);
    while (this.el.toasts.children.length > 4) this.el.toasts.firstChild.remove();
  }

  banner(title, sub, duration = 2.4) {
    this.el.bannerTitle.textContent = title;
    this.el.bannerSub.textContent = sub || '';
    this.el.banner.classList.add('show');
    this.bannerTimer = duration;
  }

  /** angle: radians, 0 = straight ahead, positive = to the right. */
  damageFrom(angle) {
    const arc = document.createElement('div');
    arc.className = 'dmg-arc';
    arc.style.transform = `rotate(${angle}rad)`;
    this.el.dmgDirs.appendChild(arc);
    requestAnimationFrame(() => { arc.style.opacity = '0'; });
    setTimeout(() => arc.remove(), 1000);
  }

  setCrosshairVisible(v) {
    this.el.crosshair.dataset.hidden = v ? 'false' : 'true';
  }

  update(dt, s) {
    // --- crosshair spread + ADS ---
    const gap = 4 + s.spreadNorm * 26 + (s.moving ? 2 : 0);
    this.el.crosshair.style.setProperty('--gap', `${gap.toFixed(1)}px`);
    this.el.crosshair.style.setProperty('--col',
      s.enemyUnderCrosshair ? 'rgba(255,120,90,0.98)' : 'rgba(255,226,176,0.92)');
    this.el.crosshair.style.opacity = s.aiming > 0.7 ? '0.25' : '1';

    if (this.hitmarkerTimer > 0) {
      this.hitmarkerTimer -= dt;
      if (this.hitmarkerTimer <= 0) this.el.hitmarker.classList.remove('show', 'kill', 'head');
    }
    if (this.bannerTimer > 0) {
      this.bannerTimer -= dt;
      if (this.bannerTimer <= 0) this.el.banner.classList.remove('show');
    }

    // --- health ---
    const pct = Math.max(0, Math.min(100, (s.health / s.maxHealth) * 100));
    this.el.hpFill.style.width = `${pct}%`;
    this.el.hpGhost.style.width = `${pct}%`;
    const shown = Math.ceil(s.health);
    if (this.el.hpNum.textContent !== String(shown)) this.el.hpNum.textContent = String(shown);
    this.el.damageFlash.style.opacity = String(Math.min(0.9, s.damageFlash));
    this.el.lowHealth.style.opacity = s.health < 35 ? String((35 - s.health) / 35 * 0.9) : '0';

    // --- status chips ---
    const chips = [];
    if (s.crouching) chips.push('CROUCH');
    if (s.sprinting) chips.push('SPRINT');
    if (s.health < 35) chips.push('CRITICAL');
    const chipKey = chips.join('|');
    if (chipKey !== this._lastChips) {
      this._lastChips = chipKey;
      this.el.statusRow.innerHTML = chips.map((c) => `<span class="status-chip">${c}</span>`).join('');
    }

    // --- ammo ---
    if (s.ammo !== this._lastAmmo) {
      this._lastAmmo = s.ammo;
      this.el.ammoMag.textContent = String(s.ammo);
      this.el.ammoMag.classList.toggle('low', s.ammo <= 7);
    }
    if (s.reserve !== this._lastReserve) {
      this._lastReserve = s.reserve;
      this.el.ammoReserve.textContent = String(s.reserve);
    }
    const reloading = s.reloadProgress !== null;
    this.el.reloadBar.classList.toggle('show', reloading);
    this.el.reloadText.classList.toggle('show', reloading);
    if (reloading) this.el.reloadFill.style.width = `${(s.reloadProgress * 100).toFixed(1)}%`;

    // --- top bar ---
    if (s.wave !== this._lastWave) { this._lastWave = s.wave; this.el.wave.textContent = String(s.wave); }
    if (s.enemiesLeft !== this._lastEnemies) { this._lastEnemies = s.enemiesLeft; this.el.enemies.textContent = String(s.enemiesLeft); }
    if (s.score !== this._lastScore) { this._lastScore = s.score; this.el.score.textContent = String(s.score); }
  }

  gameOver(stats) {
    document.getElementById('go-wave').textContent = String(stats.wave);
    document.getElementById('go-kills').textContent = String(stats.kills);
    document.getElementById('go-score').textContent = String(stats.score);
    document.getElementById('go-acc').textContent = `${stats.accuracy}%`;
    document.getElementById('go-time').textContent = stats.time;
    document.getElementById('go-best').textContent = String(stats.best);
    document.getElementById('go-sub').textContent = stats.wave >= 5
      ? 'They will be telling stories about Sector 7.'
      : 'The ash settles over Sector 7.';
    this.showScreen('gameover');
  }
}
