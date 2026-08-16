/**
 * Pause menu and settings.
 *
 * Built from plain DOM. Pointer lock is released while paused, so ordinary clicks work
 * and there is no need for an in-world UI layer.
 *
 * Settings that change the render pipeline (quality preset, resolution scale) are applied
 * immediately rather than on close, so the effect is visible behind the panel while the
 * player is still adjusting it.
 *
 * The display and audio rows are also the only writers of the persistent settings store -
 * `Engine.setResolutionScale()` and `AudioEngine.setVolume()` stay pure setters so that
 * test harnesses and debug code can drive them without silently rewriting the player's
 * preferences. The world rows below them (weather, time of day, clock) are deliberately
 * *not* persisted: they are session toys, and the save game already carries the real ones.
 */

import { settings } from '../core/Settings.js';

const QUALITY_LEVELS = ['low', 'medium', 'high', 'ultra'];
const WEATHER_LEVELS = ['clear', 'cloudy', 'rain', 'storm'];

export class PauseMenu {
  /** @param {object} game */
  constructor(game) {
    this.game = game;
    this.root = document.getElementById('pause');
    this.body = document.getElementById('pause-body');
    this.open = false;
    this._build();
  }

  _build() {
    this.body.innerHTML = `
      <div class="tabs">
        <button data-tab="stats" class="active">Stats</button>
        <button data-tab="settings">Settings</button>
        <button data-tab="save">Save</button>
      </div>
      <div class="tab-body" id="pause-stats"></div>
      <div class="tab-body" id="pause-settings" hidden></div>
      <div class="tab-body" id="pause-save" hidden></div>
    `;
    this.tabs = this.body.querySelectorAll('.tabs button');
    this.panels = {
      stats: this.body.querySelector('#pause-stats'),
      settings: this.body.querySelector('#pause-settings'),
      save: this.body.querySelector('#pause-save'),
    };
    for (const tab of this.tabs) {
      tab.addEventListener('click', () => this._selectTab(tab.dataset.tab));
    }
    this._buildSettings();
    this._buildSave();
  }

  _selectTab(name) {
    for (const tab of this.tabs) tab.classList.toggle('active', tab.dataset.tab === name);
    for (const [key, panel] of Object.entries(this.panels)) panel.hidden = key !== name;
    if (name === 'stats') this._refreshStats();
    if (name === 'save') this._refreshSave();
  }

  /** A labelled row with a set of choice buttons. */
  _choiceRow(parent, label, options, current, onPick) {
    const row = document.createElement('div');
    row.className = 'row setting';
    row.innerHTML = `<span>${label}</span>`;
    const group = document.createElement('div');
    group.className = 'choices';
    const buttons = [];
    for (const opt of options) {
      const b = document.createElement('button');
      b.textContent = opt.label;
      b.classList.toggle('on', opt.value === current);
      b.addEventListener('click', () => {
        onPick(opt.value);
        for (const other of buttons) other.classList.toggle('on', other === b);
      });
      group.appendChild(b);
      buttons.push(b);
    }
    row.appendChild(group);
    parent.appendChild(row);
    return { row, buttons };
  }

  _sliderRow(parent, label, { min, max, step, value }, onInput) {
    const row = document.createElement('div');
    row.className = 'row setting';
    row.innerHTML = `<span>${label}</span>`;
    const input = document.createElement('input');
    input.type = 'range';
    input.min = min; input.max = max; input.step = step; input.value = value;
    const readout = document.createElement('b');
    readout.textContent = Number(value).toFixed(2);
    input.addEventListener('input', () => {
      readout.textContent = Number(input.value).toFixed(2);
      onInput(Number(input.value));
    });
    const wrap = document.createElement('div');
    wrap.className = 'choices';
    wrap.append(input, readout);
    row.appendChild(wrap);
    parent.appendChild(row);
    return input;
  }

  _buildSettings() {
    const g = this.game;
    const p = this.panels.settings;
    p.innerHTML = '';

    this._choiceRow(
      p, 'Quality',
      QUALITY_LEVELS.map((q) => ({ label: q, value: q })),
      g.postfx.quality,
      (q) => {
        const wasEnabled = g.postfx.enabled;
        g.postfx.setQuality(q);
        // Rebuilding the node graph turns the chain back on, so the post choice has to be
        // re-asserted or picking a preset silently switches post-processing back on.
        g.postfx.enabled = wasEnabled && !!g.postfx.post;
        settings.set('quality', q);
      },
    );

    this._sliderRow(p, 'Resolution', { min: 0.5, max: 1, step: 0.05, value: g.engine.resolutionScale },
      (v) => { g.engine.setResolutionScale(v); settings.set('resolutionScale', g.engine.resolutionScale); });

    this._sliderRow(p, 'Volume', { min: 0, max: 1, step: 0.05, value: g.audio.volume },
      (v) => { g.audio.setVolume(v); settings.set('volume', g.audio.volume); });

    this._choiceRow(
      p, 'Post FX',
      [{ label: 'on', value: true }, { label: 'off', value: false }],
      g.postfx.enabled,
      (on) => {
        g.postfx.enabled = on && !!g.postfx.post;
        settings.set('post', on);
      },
    );

    this._choiceRow(
      p, 'Weather',
      [{ label: 'auto', value: 'auto' }, ...WEATHER_LEVELS.map((w) => ({ label: w, value: w }))],
      'auto',
      (w) => {
        if (w === 'auto') g.weather.auto = true;
        else g.weather.set(w);
      },
    );

    this._sliderRow(p, 'Time of day', { min: 0, max: 24, step: 0.25, value: g.atmosphere.timeOfDay },
      (v) => { g.atmosphere.timeOfDay = v; g.atmosphere._envDirtyAt = -999; });

    this._choiceRow(
      p, 'Clock',
      [{ label: 'running', value: false }, { label: 'frozen', value: true }],
      g.atmosphere.paused,
      (frozen) => { g.atmosphere.paused = frozen; },
    );
  }

  _buildSave() {
    const p = this.panels.save;
    p.innerHTML = '<div class="row"><span>Last save</span><b id="save-desc">-</b></div>';
    const actions = document.createElement('div');
    actions.className = 'actions';
    const mk = (label, fn) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.addEventListener('click', () => { fn(); this._refreshSave(); });
      actions.appendChild(b);
      return b;
    };
    mk('Save now', () => {
      const ok = this.game.save.save();
      this.game.hud.say(ok ? 'Game saved' : 'Could not save', 2.5);
    });
    mk('Load', () => {
      const ok = this.game.save.load();
      this.game.hud.say(ok ? 'Game loaded' : 'No save found', 2.5);
    });
    mk('Delete save', () => {
      this.game.save.clear();
      this.game.hud.say('Save deleted', 2);
    });
    p.appendChild(actions);
    p.insertAdjacentHTML('beforeend',
      '<p class="hint">Autosaves every minute while not on a mission. The world is '
      + 'regenerated from a fixed seed, so only your progress is stored.</p>');
  }

  _refreshSave() {
    const el = this.body.querySelector('#save-desc');
    if (el) el.textContent = this.game.save.describe();
  }

  _refreshStats() {
    const g = this.game;
    const rows = [
      ['Backend', g.engine.backend],
      ['Frame', `${g.engine.stats.fps} fps  /  ${g.engine.stats.ms} ms`],
      ['Draw calls', g.engine.stats.drawCalls],
      ['Money', `$${Math.floor(g.money).toLocaleString('en-US')}`],
      ['Missions', `${g.missions.completed} / ${g.missions.missions.length}`],
      ['Weather', `${g.weather.label}  (wet ${g.weather.wetness.toFixed(2)})`],
      ['Time', g.atmosphere.clockString()],
      ['Buildings', g.city.buildingBoxes.length],
      ['Vehicles', `${g.traffic.count} (${g.traffic.trafficCount} ai)`],
      ['Pedestrians', g.peds.count],
      ['Street lamps', g.props.lamps.length],
      ['Kills / knockdowns', `${g.weapons.kills} / ${g.peds.knockdowns}`],
      ['Times busted', g.wanted.busted],
    ];
    this.panels.stats.innerHTML = rows
      .map(([k, v]) => `<div class="row"><span>${k}</span><b>${v}</b></div>`)
      .join('');
  }

  toggle() {
    this.open = !this.open;
    this.root.hidden = !this.open;
    if (this.open) this._selectTab('stats');
    return this.open;
  }
}
