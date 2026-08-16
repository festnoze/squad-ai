/**
 * In-game phone.
 *
 * A compact overlay for the things you want mid-game without opening a settings panel:
 * which missions are available and how far away they are, a waypoint you can drop on one,
 * and a run of stats.
 *
 * Unlike the pause menu, the phone does NOT pause the world - you pull it out while
 * standing in the street and the city keeps moving around you. It does release pointer
 * lock so the list is clickable.
 */

const TABS = [
  { id: 'jobs', label: 'Jobs' },
  { id: 'stats', label: 'Stats' },
  { id: 'help', label: 'Help' },
];

export class Phone {
  /** @param {object} game */
  constructor(game) {
    this.game = game;
    this.open = false;
    this.tab = 'jobs';
    /** @type {{x:number,z:number,label:string}|null} */
    this.waypoint = null;

    const el = document.createElement('div');
    el.id = 'phone';
    el.hidden = true;
    el.innerHTML = `
      <div class="shell">
        <div class="bar"><span class="carrier">LIBERTY</span><span class="time" id="phone-time">--:--</span></div>
        <div class="tabs">
          ${TABS.map((t) => `<button data-tab="${t.id}">${t.label}</button>`).join('')}
        </div>
        <div class="body" id="phone-body"></div>
        <div class="foot">T to close</div>
      </div>`;
    document.body.appendChild(el);

    this.el = el;
    this.body = el.querySelector('#phone-body');
    this.timeEl = el.querySelector('#phone-time');
    this.tabButtons = el.querySelectorAll('.tabs button');
    for (const b of this.tabButtons) {
      b.addEventListener('click', () => this._select(b.dataset.tab));
    }
  }

  _select(tab) {
    this.tab = tab;
    for (const b of this.tabButtons) b.classList.toggle('on', b.dataset.tab === tab);
    this.render();
  }

  toggle() {
    this.open = !this.open;
    this.el.hidden = !this.open;
    if (this.open) {
      this._select(this.tab);
      this.game.input.releaseLock();
    }
    return this.open;
  }

  /** Distance from the player to a world point, formatted. */
  _distance(x, z) {
    const p = this.game.cameraTarget;
    const d = Math.hypot(p.x - x, p.z - z);
    return d > 999 ? `${(d / 1000).toFixed(1)} km` : `${Math.round(d)} m`;
  }

  setWaypoint(x, z, label) {
    this.waypoint = { x, z, label };
    this.game.hud.say(`Waypoint set: ${label}`, 2.5);
  }

  clearWaypoint() {
    this.waypoint = null;
    this.game.hud.say('Waypoint cleared', 1.8);
  }

  render() {
    if (!this.open) return;
    this.timeEl.textContent = this.game.atmosphere.clockString();

    if (this.tab === 'jobs') return this._renderJobs();
    if (this.tab === 'stats') return this._renderStats();
    return this._renderHelp();
  }

  _renderJobs() {
    const g = this.game;
    const active = g.missions.active;
    const rows = [];

    if (active) {
      rows.push(`<div class="job active">
        <div class="name">${active.name}</div>
        <div class="meta">in progress - ${g.missions.statusLine ?? ''}</div>
      </div>`);
    }

    const available = g.missions.missions
      .filter((m) => m.state === 'available')
      .map((m) => ({ m, d: Math.hypot(g.cameraTarget.x - m.start.x, g.cameraTarget.z - m.start.z) }))
      .sort((a, b) => a.d - b.d);

    for (const { m } of available) {
      rows.push(`<div class="job">
        <div class="name">${m.name}<b>$${m.reward.toLocaleString('en-US')}</b></div>
        <div class="meta">${m.brief}</div>
        <div class="meta dist">${this._distance(m.start.x, m.start.z)} away
          <button data-wp="${m.id}">Waypoint</button></div>
      </div>`);
    }

    const done = g.missions.missions.filter((m) => m.state === 'complete').length;
    rows.push(`<div class="job muted"><div class="meta">${done} of
      ${g.missions.missions.length} jobs completed</div></div>`);

    if (this.waypoint) {
      rows.unshift(`<div class="job wp">
        <div class="name">Waypoint</div>
        <div class="meta dist">${this.waypoint.label} - ${this._distance(this.waypoint.x, this.waypoint.z)}
          <button data-wp="clear">Clear</button></div>
      </div>`);
    }

    this.body.innerHTML = rows.join('');
    for (const b of this.body.querySelectorAll('button[data-wp]')) {
      b.addEventListener('click', () => {
        const id = b.dataset.wp;
        if (id === 'clear') return this.clearWaypoint();
        const mission = g.missions.missions.find((m) => m.id === id);
        if (mission) this.setWaypoint(mission.start.x, mission.start.z, mission.name);
        this.render();
        return undefined;
      });
    }
  }

  _renderStats() {
    const g = this.game;
    const rows = [
      ['Money', `$${Math.floor(g.money).toLocaleString('en-US')}`],
      ['Jobs done', `${g.missions.completed} / ${g.missions.missions.length}`],
      ['Earned from jobs', `$${g.missions.earned.toLocaleString('en-US')}`],
      ['Wanted level', g.wanted.stars || 'clean'],
      ['Times busted', g.wanted.busted],
      ['Shots fired', g.weapons.shotsFired],
      ['Pickups', g.pickups.collected],
      ['Pedestrians hit', g.peds.knockdowns],
      ['Weapons', [...g.weapons.owned].filter((w) => w !== 'unarmed').join(', ') || 'none'],
      ['Weather', g.weather.label],
      ['Time', g.atmosphere.clockString()],
    ];
    this.body.innerHTML = rows
      .map(([k, v]) => `<div class="row"><span>${k}</span><b>${v}</b></div>`)
      .join('');
  }

  _renderHelp() {
    const keys = this.game.input;
    const rows = [
      ['Move', keys.moveKeysLabel],
      ['Sprint', 'Shift'],
      ['Jump', 'Space'],
      ['Enter / exit vehicle', keys.actionLabel('interact')],
      ['Aim / fire', 'Right / Left mouse'],
      ['Reload', keys.actionLabel('reload')],
      ['Next weapon or radio', keys.actionLabel('nextRadio')],
      ['Headlights', keys.actionLabel('lights')],
      ['World map', keys.actionLabel('map')],
      ['Phone', keys.actionLabel('phone')],
      ['Free camera', keys.actionLabel('freeCam')],
      ['Pause / settings', 'Esc'],
    ];
    this.body.innerHTML = rows
      .map(([k, v]) => `<div class="row"><span>${k}</span><b>${v}</b></div>`)
      .join('');
  }

  /** Radar blip for the waypoint, if one is set. */
  get blips() {
    if (!this.waypoint) return [];
    return [{ x: this.waypoint.x, z: this.waypoint.z, kind: 'waypoint', size: 4, pin: true }];
  }
}
