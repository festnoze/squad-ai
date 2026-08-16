/**
 * ABYSSE - HUD and screen layer.
 *
 * Owns every DOM element declared in index.html: the dive instruments, the
 * full screen washes, and all the menu screens. Never touches the 3D scene.
 * Imports config.js only.
 *
 * Performance notes:
 * - Every element reference is cached once at construction.
 * - update() runs 60 times per second, so each written value is compared
 *   against a `last` cache and the DOM is only touched on change.
 * - The depth gauge is a canvas redrawn only when the depth moves by more
 *   than a small epsilon or the biome changes.
 */

import {
  GAME_TITLE,
  GAME_SUBTITLE,
  BIOME_INFO,
  DIVER,
  PROGRESSION,
  SPECIES,
  SPECIES_BY_ID,
  RARITY_COLOR,
  SKINS,
  WORLD,
  clamp,
  clamp01,
  oxygenDrain,
} from './config.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SCREEN_IDS = [
  'loading', 'title', 'codex', 'scientist', 'skins',
  'pause', 'help', 'dead', 'error',
];

// Screens the player can open on top of the game and simply close again.
const CLOSABLE = { codex: true, skins: true, help: true };

const COMPASS_PX_PER_DEG = 2;
const COMPASS_SEGMENT = 360 * COMPASS_PX_PER_DEG;
const COMPASS_LABELS = { 0: 'N', 45: 'NE', 90: 'E', 135: 'SE', 180: 'S', 225: 'SO', 270: 'O', 315: 'NO' };

// Reload ring geometry (r = 17 in the SVG viewBox).
const RING_CIRC = 2 * Math.PI * 17;

// Depth gauge canvas metrics.
const GAUGE_SPAN = 64; // metres visible in the window

const DEG = 180 / Math.PI;

// Latin-ish glyphs used to scramble the name of unidentified species.
const SCRAMBLE_GLYPHS = 'abcdefghijklmnopqrstuvxyz';

// Simple silhouette paths (64 x 40 viewBox), keyed by a coarse shape family.
const SIL_PATHS = {
  fish: 'M8 20 Q20 7 36 9 Q49 11 54 20 Q49 29 36 31 Q20 33 8 20 Z M54 20 L62 11 L59 20 L62 29 Z',
  shark: 'M4 23 Q18 12 34 13 L29 4 L39 12 Q51 14 57 21 L62 13 L60 22 L62 31 L55 23 Q40 30 20 28 Q10 26 4 23 Z',
  ray: 'M32 8 Q52 13 61 24 Q47 21 39 25 L37 36 L32 29 L27 36 L25 25 Q17 21 3 24 Q12 13 32 8 Z',
  turtle: 'M13 20 Q13 10 30 9 Q45 10 47 16 L58 12 L55 21 L47 24 Q45 31 30 31 Q13 30 13 20 Z',
  eel: 'M3 27 Q13 17 24 23 Q34 29 44 21 Q52 15 61 17 Q55 24 46 28 Q34 34 21 31 Q11 29 3 27 Z',
  jelly: 'M18 17 Q18 5 32 5 Q46 5 46 17 L43 19 L45 32 L40 23 L37 35 L33 22 L30 35 L26 23 L22 32 L21 19 Z',
  octopus: 'M22 15 Q22 4 32 4 Q42 4 42 15 L45 30 L40 21 L38 34 L34 23 L32 36 L29 23 L26 34 L23 21 L19 30 Z',
};

const BODY_TO_SIL = {
  reeffish: 'fish', bulkfish: 'fish', sleekfish: 'fish', lionfish: 'fish', angler: 'fish',
  shark: 'shark', hammerhead: 'shark',
  ray: 'ray',
  turtle: 'turtle',
  eel: 'eel',
  jelly: 'jelly',
  octopus: 'octopus', squid: 'octopus',
};

const DEATHS = {
  drowned: ['Noye', 'La bouteille etait vide et la surface trop loin.'],
  shark: ['Devore', 'Le predateur a frappe avant que vous ne le voyiez.'],
  crushed: ['Ecrase', 'La pression de la fosse ne negocie pas.'],
};
const DEATH_DEFAULT = ['Perdu en mer', 'L expedition continue sans vous, pour cette fois.'];

const DEAD_STAT_LABELS = {
  depth: ['Profondeur max', (v) => Math.round(v) + ' m'],
  bestDepth: ['Profondeur max', (v) => Math.round(v) + ' m'],
  time: ['Duree de plongee', fmtTime],
  kills: ['Creatures neutralisees', String],
  collected: ['Specimens recoltes', String],
  specimens: ['Specimens recoltes', String],
  medals: ['Medailles', String],
  credits: ['Credits', String],
  distance: ['Distance parcourue', (v) => Math.round(v) + ' m'],
};

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function $(id) {
  return document.getElementById(id);
}

function cssHex(n) {
  return '#' + (n >>> 0).toString(16).padStart(6, '0');
}

function fmtTime(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m + ':' + String(r).padStart(2, '0');
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function silhouetteSVG(body, color) {
  const path = SIL_PATHS[BODY_TO_SIL[body] || 'fish'];
  return '<svg class="sil" viewBox="0 0 64 40" aria-hidden="true">'
    + '<path d="' + path + '" fill="' + color + '"></path></svg>';
}

function scramble(text) {
  let out = '';
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    out += (c === ' ' || c === '.') ? c
      : SCRAMBLE_GLYPHS[(Math.random() * SCRAMBLE_GLYPHS.length) | 0];
  }
  return out;
}

function emptySave() {
  return {
    discovered: {},
    medals: 0,
    skins: ['standard'],
    currentSkin: 'standard',
    bestDepth: 0,
    totalKills: 0,
    credits: 0,
  };
}

function safeSave(save) {
  const s = save || {};
  return {
    discovered: s.discovered || {},
    medals: s.medals || 0,
    skins: Array.isArray(s.skins) ? s.skins : ['standard'],
    currentSkin: s.currentSkin || 'standard',
    bestDepth: s.bestDepth || 0,
    totalKills: s.totalKills || 0,
    credits: s.credits || 0,
  };
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createHUD(callbacks) {
  const cb = callbacks || {};

  // -------------------------------------------------------------------------
  // Element cache
  // -------------------------------------------------------------------------

  const E = {
    hud: $('hud'),
    // fx
    fxWater: $('fx-water'),
    fxDamage: $('fx-damage'),
    fxOxygen: $('fx-oxygen'),
    airAlert: $('air-alert'),
    airAlertTitle: $('air-alert-title'),
    airAlertSub: $('air-alert-sub'),
    fxFlash: $('fx-flash'),
    fxFade: $('fx-fade'),
    // crosshair
    crosshair: $('crosshair'),
    chReload: $('ch-reload'),
    chReloadCircle: $('ch-reload') ? $('ch-reload').querySelector('circle') : null,
    // vitals
    vitalOxygen: document.querySelector('.vital-oxygen'),
    vitalHealth: document.querySelector('.vital-health'),
    vitalStamina: document.querySelector('.vital-stamina'),
    oxygenFill: $('oxygen-fill'),
    oxygenNum: $('oxygen-num'),
    healthFill: $('health-fill'),
    healthNum: $('health-num'),
    staminaFill: $('stamina-fill'),
    staminaNum: $('stamina-num'),
    // depth
    depthGauge: $('depth-gauge'),
    depthValue: $('depth-value'),
    biomeLabel: $('biome-label'),
    // weapon and net
    weaponRow: $('weapon-row'),
    weaponName: $('weapon-name'),
    ammoMag: $('ammo-mag'),
    ammoReserve: $('ammo-reserve'),
    netSlots: $('net-slots'),
    // compass
    compass: $('compass'),
    compassStrip: $('compass-strip'),
    // scanner
    scanner: $('scanner'),
    scanName: $('scan-name'),
    scanLatin: $('scan-latin'),
    scanFill: $('scan-fill'),
    scanStatus: $('scan-status'),
    scanHealth: $('scan-health'),
    scanHealthFill: $('scan-health-fill'),
    // objective, chips, threat, prompt, toasts
    objectiveText: $('objective-text'),
    chipSpeciesNum: $('chip-species-num'),
    chipMedalsNum: $('chip-medals-num'),
    chipCargoNum: $('chip-cargo-num'),
    threat: $('threat'),
    prompt: $('prompt'),
    promptKey: $('prompt-key'),
    promptText: $('prompt-text'),
    damageArrows: $('damage-arrows'),
    toasts: $('toasts'),
    // loading
    loadFill: $('load-fill'),
    loadStep: $('load-step'),
    // title
    titleStats: $('title-stats'),
    // codex
    codexGrid: $('codex-grid'),
    codexDetail: $('codex-detail'),
    codexCount: $('codex-count'),
    // scientist
    sciDialogue: $('sci-dialogue'),
    sciResults: $('sci-results'),
    sciContinue: $('sci-continue'),
    // skins
    skinGrid: $('skin-grid'),
    skinsSub: $('skins-sub'),
    skinDesc: $('skin-desc'),
    skinConfirm: $('skin-confirm'),
    skinsClose: document.querySelector('#skins [data-close]'),
    // dead
    deadTitle: $('dead-title'),
    deadText: $('dead-text'),
    deadStats: $('dead-stats'),
    // transit
    transit: $('transit'),
    transitText: $('transit-text'),
    transitSub: $('transit-sub'),
    // buttons
    btnMute: $('btn-mute'),
  };

  const screens = {};
  for (const id of SCREEN_IDS) screens[id] = $(id);

  // -------------------------------------------------------------------------
  // Internal state
  // -------------------------------------------------------------------------

  const last = {}; // change cache for every DOM write in update()
  let screenId = 'loading'; // loading is the only screen visible in index.html
  let returnTo = null; // screen to go back to when a closable screen closes
  let lastSave = emptySave();
  let disposed = false;

  // fx intensities, decayed in update()
  let damageA = 0;
  let flashA = 0;

  // scanner scramble throttle
  let scrambleClock = 0;
  let scannerVisible = false;

  // codex selection
  let codexIndex = -1;
  let codexCards = [];

  // skins selection
  let skinSelected = null;
  let skinForcePick = false;

  // scientist typing machine
  let sci = null;

  // muted label toggle
  let mutedLabel = false;

  // listener and timer bookkeeping for dispose()
  const bound = [];
  const timers = new Set();
  const intervals = new Set();

  function on(node, type, fn) {
    if (!node) return;
    node.addEventListener(type, fn);
    bound.push([node, type, fn]);
  }

  function later(fn, ms) {
    const id = setTimeout(() => { timers.delete(id); if (!disposed) fn(); }, ms);
    timers.add(id);
    return id;
  }

  function every(fn, ms) {
    const id = setInterval(() => { if (!disposed) fn(); }, ms);
    intervals.add(id);
    return id;
  }

  function stopInterval(id) {
    clearInterval(id);
    intervals.delete(id);
  }

  // -------------------------------------------------------------------------
  // Cached-write helpers
  // -------------------------------------------------------------------------

  function wText(key, node, text) {
    if (last[key] !== text) {
      last[key] = text;
      node.textContent = text;
    }
  }

  function wVar(key, node, name, value) {
    if (last[key] !== value) {
      last[key] = value;
      node.style.setProperty(name, value);
    }
  }

  function wAttr(key, node, name, value) {
    if (last[key] !== value) {
      last[key] = value;
      node.setAttribute(name, value);
    }
  }

  function wClass(key, node, cls, active) {
    if (last[key] !== active) {
      last[key] = active;
      node.classList.toggle(cls, active);
    }
  }

  function wTransform(key, node, value) {
    if (last[key] !== value) {
      last[key] = value;
      node.style.transform = value;
    }
  }

  // -------------------------------------------------------------------------
  // Compass ribbon (built once, translated on update)
  // -------------------------------------------------------------------------

  let compassHalf = 170; // half of the visible ribbon, refreshed on resize

  function buildCompass() {
    const frag = document.createDocumentFragment();
    // Three copies of the 360 degree band so the window never sees an edge.
    for (let rep = 0; rep < 3; rep++) {
      for (let d = 0; d < 360; d += 15) {
        const x = (rep * 360 + d) * COMPASS_PX_PER_DEG;
        if (d % 45 === 0) {
          const lab = el('span', 'cp-label' + (d === 0 ? ' cp-north' : ''), COMPASS_LABELS[d]);
          lab.style.left = x + 'px';
          frag.appendChild(lab);
        } else {
          const tick = el('span', 'cp-tick');
          tick.style.left = x + 'px';
          frag.appendChild(tick);
        }
      }
    }
    E.compassStrip.appendChild(frag);
    E.compassStrip.style.width = (COMPASS_SEGMENT * 3) + 'px';
    refreshCompassMetrics();
  }

  function refreshCompassMetrics() {
    if (E.compass && E.compass.clientWidth > 0) {
      compassHalf = E.compass.clientWidth / 2;
    }
  }

  function updateCompass(yaw) {
    // yaw = 0 faces -Z which is north (the island); compass heading is
    // clockwise from north while yaw grows counter clockwise.
    let heading = (-(yaw || 0) * DEG) % 360;
    if (heading < 0) heading += 360;
    const q = Math.round(heading * 4) / 4; // quarter degree quantisation
    if (last.compassHeading === q) return;
    last.compassHeading = q;
    // The middle copy of the band carries the current heading.
    const x = compassHalf - (q + 360) * COMPASS_PX_PER_DEG;
    E.compassStrip.style.transform = 'translateX(' + x.toFixed(1) + 'px)';
  }

  // -------------------------------------------------------------------------
  // Depth gauge canvas
  // -------------------------------------------------------------------------

  const gaugeCtx = E.depthGauge ? E.depthGauge.getContext('2d') : null;
  const GW = E.depthGauge ? E.depthGauge.width : 86;
  const GH = E.depthGauge ? E.depthGauge.height : 420;
  const BIOME_IDS = Object.keys(BIOME_INFO);

  function drawGauge(depth) {
    if (!gaugeCtx) return;
    const ctx = gaugeCtx;
    ctx.clearRect(0, 0, GW, GH);

    const pxPerM = GH / GAUGE_SPAN;
    const top = depth - GAUGE_SPAN / 2; // metres at the top edge
    const yOf = (d) => (d - top) * pxPerM;

    // Biome strata: one thin column per biome on the right edge.
    for (let i = 0; i < BIOME_IDS.length; i++) {
      const info = BIOME_INFO[BIOME_IDS[i]];
      const y0 = clamp(yOf(info.depth[0]), 0, GH);
      const y1 = clamp(yOf(info.depth[1]), 0, GH);
      if (y1 <= 0 || y0 >= GH || y1 - y0 < 1) continue;
      ctx.fillStyle = cssHex(info.fogColor);
      ctx.globalAlpha = 0.7;
      ctx.fillRect(GW - 21 + i * 4, y0, 3, y1 - y0);
    }
    ctx.globalAlpha = 1;

    // Graduations every 10 m, labelled every 20 m.
    ctx.font = '600 10px "Segoe UI", system-ui, sans-serif';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    const first = Math.floor(top / 10) * 10;
    for (let d = first; d <= top + GAUGE_SPAN + 10; d += 10) {
      if (d < 0 || d > -WORLD.floorMin + 10) continue;
      const y = yOf(d);
      if (y < -2 || y > GH + 2) continue;
      const major = d % 20 === 0;
      ctx.strokeStyle = major ? 'rgba(200,240,255,0.55)' : 'rgba(200,240,255,0.28)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(4, y + 0.5);
      ctx.lineTo(major ? 22 : 13, y + 0.5);
      ctx.stroke();
      if (major) {
        ctx.fillStyle = 'rgba(190,235,252,0.75)';
        ctx.fillText(String(d), 26, y + 0.5);
      }
    }

    // Surface line.
    const ySurf = yOf(0);
    if (ySurf > -2 && ySurf < GH + 2) {
      ctx.strokeStyle = 'rgba(255,255,255,0.85)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(2, ySurf);
      ctx.lineTo(GW - 24, ySurf);
      ctx.stroke();
      ctx.fillStyle = 'rgba(255,255,255,0.8)';
      ctx.fillText('AIR', 26, ySurf - 9);
    }

    // Bottom of the trench.
    const yFloor = yOf(-WORLD.floorMin);
    if (yFloor > -2 && yFloor < GH + 2) {
      ctx.strokeStyle = 'rgba(255,77,94,0.7)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(2, yFloor);
      ctx.lineTo(GW - 24, yFloor);
      ctx.stroke();
      ctx.fillStyle = 'rgba(255,120,130,0.85)';
      ctx.fillText('FOND', 26, yFloor + 10);
    }

    // Current depth marker: a line across the middle plus a side triangle.
    const yMid = GH / 2;
    ctx.strokeStyle = 'rgba(127,233,255,0.95)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, yMid);
    ctx.lineTo(GW, yMid);
    ctx.stroke();
    ctx.fillStyle = 'rgba(127,233,255,0.95)';
    ctx.beginPath();
    ctx.moveTo(0, yMid - 5);
    ctx.lineTo(8, yMid);
    ctx.lineTo(0, yMid + 5);
    ctx.closePath();
    ctx.fill();
  }

  // -------------------------------------------------------------------------
  // Net slots (built once from DIVER.netCapacity)
  // -------------------------------------------------------------------------

  const netSlotEls = [];

  function buildNetSlots() {
    for (let i = 0; i < DIVER.netCapacity; i++) {
      const slot = el('span', 'net-slot');
      const pip = el('i', 'net-pip');
      slot.appendChild(pip);
      E.netSlots.appendChild(slot);
      netSlotEls.push(slot);
    }
  }

  function updateNet(net) {
    const items = (net && net.items) || [];
    const key = items.map((it) => it && it.speciesId).join(',');
    if (last.netKey === key) return;
    last.netKey = key;
    for (let i = 0; i < netSlotEls.length; i++) {
      const slot = netSlotEls[i];
      const item = items[i];
      if (item) {
        const species = SPECIES_BY_ID[item.speciesId];
        const color = species ? (RARITY_COLOR[species.rarity] || '#9fb6c2') : '#9fb6c2';
        slot.classList.add('filled');
        slot.firstChild.style.background = color;
        slot.firstChild.style.boxShadow = '0 0 6px ' + color;
        slot.title = item.name || (species ? species.name : '');
      } else {
        slot.classList.remove('filled');
        slot.firstChild.style.background = '';
        slot.firstChild.style.boxShadow = '';
        slot.title = '';
      }
    }
  }

  // -------------------------------------------------------------------------
  // Prompt
  // -------------------------------------------------------------------------

  /**
   * `key` null means the line is a plain status, not something to press. The
   * badge is dropped entirely in that case: showing a key that does nothing is
   * how the submarine ended up looking broken.
   */
  function applyPrompt(text, key) {
    if (text) {
      const badge = key === undefined ? 'E' : key;
      wText('promptText', E.promptText, text);
      wText('promptKey', E.promptKey, badge || '');
      wClass('promptNoKey', E.prompt, 'no-key', !badge);
      wClass('promptHidden', E.prompt, 'hidden', false);
    } else {
      wClass('promptHidden', E.prompt, 'hidden', true);
    }
  }

  // -------------------------------------------------------------------------
  // Scanner
  // -------------------------------------------------------------------------

  function updateScanner(scan, dt) {
    if (scan && scan.creature) {
      if (!scannerVisible) {
        scannerVisible = true;
        E.scanner.classList.remove('hidden');
        // Next frame so the opacity transition can play.
        requestAnimationFrame(() => E.scanner.classList.add('show'));
      }
      const creature = scan.creature;
      const species = creature.species || SPECIES_BY_ID[creature.speciesId] || {};
      const known = !!scan.known;
      const progress = clamp01(scan.progress || 0);
      const done = progress >= 1;

      if (known || done) {
        wText('scanName', E.scanName, species.name || 'Espece inconnue');
        wText('scanLatin', E.scanLatin, species.latin || '');
      } else {
        wText('scanName', E.scanName, 'Espece inconnue');
        // Scrambled latin, refreshed at about 8 Hz so it flickers.
        scrambleClock += dt;
        if (scrambleClock > 0.12) {
          scrambleClock = 0;
          E.scanLatin.textContent = scramble(species.latin || 'genus species');
          last.scanLatin = null;
        }
      }
      wText('scanStatus', E.scanStatus,
        done ? 'Identification confirmee' : (known ? 'Espece identifiee' : 'Analyse en cours'));
      wClass('scanDone', E.scanner, 'done', done);
      wClass('scanKnown', E.scanner, 'known', known && !done);

      const p = Math.round(progress * 1000) / 1000;
      wVar('scanFill', E.scanFill, '--p', String(p));

      const hp = creature.maxHealth > 0 ? clamp01(creature.health / creature.maxHealth) : 0;
      const hpQ = Math.round(hp * 200) / 200;
      wVar('scanHp', E.scanHealthFill, '--p', String(hpQ));
      wClass('scanHpLow', E.scanHealth, 'low', hp < 0.35);
    } else if (scannerVisible) {
      scannerVisible = false;
      E.scanner.classList.remove('show');
    }
  }

  // -------------------------------------------------------------------------
  // update(dt, state)
  // -------------------------------------------------------------------------

  function update(dt, state) {
    if (disposed || !state) return;
    const mode = state.mode || 'menu';
    const dive = mode === 'dive';

    // ---- vitals -----------------------------------------------------------
    const o01 = state.maxOxygen > 0 ? clamp01(state.oxygen / state.maxOxygen) : 0;
    const h01 = state.maxHealth > 0 ? clamp01(state.health / state.maxHealth) : 0;
    const s01 = state.maxStamina > 0 ? clamp01(state.stamina / state.maxStamina) : 0;

    wTransform('oFill', E.oxygenFill, 'scaleX(' + (Math.round(o01 * 500) / 500) + ')');
    wTransform('hFill', E.healthFill, 'scaleX(' + (Math.round(h01 * 500) / 500) + ')');
    wTransform('sFill', E.staminaFill, 'scaleX(' + (Math.round(s01 * 500) / 500) + ')');
    wText('oNum', E.oxygenNum, String(Math.ceil(state.oxygen || 0)));
    wText('hNum', E.healthNum, String(Math.ceil(state.health || 0)));
    wText('sNum', E.staminaNum, String(Math.ceil(state.stamina || 0)));

    wAttr('oLvl', E.vitalOxygen, 'data-level', o01 > 0.5 ? 'ok' : o01 > 0.25 ? 'warn' : 'low');
    wAttr('hLvl', E.vitalHealth, 'data-level', h01 > 0.5 ? 'ok' : h01 > 0.25 ? 'warn' : 'low');
    wAttr('sLvl', E.vitalStamina, 'data-level', s01 > 0.3 ? 'ok' : 'warn');

    // ---- depth ------------------------------------------------------------
    const depth = Math.max(0, state.depth || 0);
    wText('depthVal', E.depthValue, String(Math.round(depth)));
    wText('biome', E.biomeLabel, state.biomeLabel || 'Surface');
    if (last.gaugeDepth === undefined || Math.abs(depth - last.gaugeDepth) > 0.08) {
      last.gaugeDepth = depth;
      drawGauge(depth);
    }

    // ---- compass ----------------------------------------------------------
    updateCompass(state.yaw);

    // ---- weapon -----------------------------------------------------------
    const w = state.weapon || {};
    wText('wName', E.weaponName, w.name || '');
    wText('wMag', E.ammoMag, String(w.mag != null ? w.mag : 0));
    wText('wRes', E.ammoReserve, String(w.reserve != null ? w.reserve : 0));
    wClass('wReload', E.weaponRow, 'reloading', !!w.reloading);
    wClass('wEmpty', E.weaponRow, 'empty', !w.reloading && (w.mag | 0) === 0);

    if (w.reloading && E.chReloadCircle) {
      const rp = clamp01(w.reloadProgress || 0);
      const off = (RING_CIRC * (1 - rp)).toFixed(1);
      if (last.ringOff !== off) {
        last.ringOff = off;
        E.chReloadCircle.style.strokeDashoffset = off;
      }
    }

    // ---- crosshair mode ---------------------------------------------------
    let chMode = 'idle';
    if (!dive && mode !== 'land') chMode = 'none';
    else if (w.reloading) chMode = 'reload';
    else if (state.scan && state.scan.creature) {
      chMode = state.scan.creature.danger === 2 ? 'danger' : 'target';
    } else if (w.kind === 'melee') chMode = 'melee';
    wAttr('chMode', E.crosshair, 'data-mode', chMode);

    // ---- net + chips ------------------------------------------------------
    updateNet(state.net);
    wText('chipSp', E.chipSpeciesNum,
      (state.discoveredCount || 0) + '/' + (state.speciesTotal || SPECIES.length));
    wText('chipMd', E.chipMedalsNum, String(state.medals || 0));
    wText('chipCg', E.chipCargoNum, String(state.cargoCount || 0));

    // ---- objective --------------------------------------------------------
    wText('objective', E.objectiveText, state.objective || '');

    // ---- threat -----------------------------------------------------------
    const threat = clamp01(state.threat || 0);
    const showThreat = threat >= 0.05;
    wClass('threatHidden', E.threat, 'hidden', !showThreat);
    if (showThreat) {
      const tq = Math.round(threat * 100) / 100;
      wVar('threatI', E.threat, '--i', String(tq));
      wClass('threatHigh', E.threat, 'high', threat > 0.6);
    }

    // ---- scanner ----------------------------------------------------------
    updateScanner(state.scan, dt);

    // ---- prompt -----------------------------------------------------------
    const pr = state.prompt;
    applyPrompt(pr ? pr.text : null, pr ? pr.key : 'E');

    // ---- full screen washes ----------------------------------------------
    // Water wash: present while diving, deepens with depth.
    const waterA = dive ? clamp(0.22 + (depth / -WORLD.floorMin) * 0.3, 0.22, 0.55) : 0;
    wVar('fxWaterA', E.fxWater, '--a', (Math.round(waterA * 100) / 100).toFixed(2));
    wVar('fxWaterD', E.fxWater, '--deep',
      (Math.round(clamp01(depth / -WORLD.floorMin) * 100) / 100).toFixed(2));

    // Oxygen tunnel: closes in under 35 percent, pulses under 15.
    const oxA = dive && o01 < 0.35 ? (1 - o01 / 0.35) * 0.85 : 0;
    wVar('fxOxA', E.fxOxygen, '--a', (Math.round(oxA * 100) / 100).toFixed(2));
    wClass('fxOxPulse', E.fxOxygen, 'pulse', dive && o01 < 0.15 && o01 > 0);

    // Air reserve alarm. Two levels, and a real time to empty rather than a
    // percentage, because what the player needs to know is whether they can
    // still make the surface from here.
    const airOn = dive && state.oxygen > 0 && o01 < 0.3;
    if (E.airAlert) {
      wClass('airHide', E.airAlert, 'hidden', !airOn);
      if (airOn) {
        const critical = o01 < 0.15;
        wAttr('airLvl', E.airAlert, 'data-level', critical ? 'critical' : 'warn');
        wText('airTitle', E.airAlertTitle, critical ? 'AIR CRITIQUE' : 'RESERVE D AIR');
        // Seconds left at the current depth, and how long the ascent costs.
        const drain = Math.max(0.01, oxygenDrain(depth, false));
        const left = Math.round(state.oxygen / drain);
        const climb = Math.round(depth / 4.5);
        wText(
          'airSub',
          E.airAlertSub,
          left + ' s d air  -  ' + climb + ' s pour remonter'
        );
      }
    }

    // Damage and flash decay.
    if (damageA > 0) {
      damageA = Math.max(0, damageA - dt * 1.1);
      wVar('fxDmgA', E.fxDamage, '--a', (Math.round(damageA * 200) / 200).toFixed(3));
    }
    if (flashA > 0) {
      flashA = Math.max(0, flashA - dt * 2.6);
      wVar('fxFlashA', E.fxFlash, '--a', (Math.round(flashA * 200) / 200).toFixed(3));
    }
  }

  // -------------------------------------------------------------------------
  // Screens
  // -------------------------------------------------------------------------

  function showScreen(id) {
    for (const sid of SCREEN_IDS) {
      if (screens[sid]) screens[sid].classList.toggle('hidden', sid !== id);
    }
    screenId = id || null;
    if (!screenId || !CLOSABLE[screenId]) returnTo = null;
  }

  function closeScreen() {
    const back = returnTo;
    returnTo = null;
    showScreen(back || null);
  }

  function rememberOrigin(target) {
    if (screenId && screenId !== target) returnTo = CLOSABLE[screenId] ? returnTo : screenId;
  }

  function isModalOpen() {
    return screenId !== null;
  }

  function setLoading(progress, label) {
    if (E.loadFill) E.loadFill.style.transform = 'scaleX(' + clamp01(progress || 0) + ')';
    if (label && E.loadStep) E.loadStep.textContent = label;
  }

  function setHudVisible(visible) {
    E.hud.classList.toggle('hidden', !visible);
  }

  // -------------------------------------------------------------------------
  // Toasts
  // -------------------------------------------------------------------------

  function toast(text, kind) {
    const k = kind || 'info';
    while (E.toasts.children.length >= 5) {
      E.toasts.removeChild(E.toasts.firstChild);
    }
    const t = el('div', 'toast ' + k, text);
    E.toasts.appendChild(t);
    const life = k === 'medal' ? 4200 : 3200;
    later(() => t.classList.add('out'), life);
    later(() => t.remove(), life + 650);
  }

  // -------------------------------------------------------------------------
  // Flashes, transit, fade
  // -------------------------------------------------------------------------

  function flashDamage(strength, angle) {
    damageA = Math.max(damageA, clamp01(strength || 0.4));
    E.fxDamage.style.setProperty('--a', damageA.toFixed(3));
    last.fxDmgA = null;
    if (angle !== null && angle !== undefined && Number.isFinite(angle)) {
      const arrow = el('div', 'dmg-arrow');
      arrow.style.transform = 'rotate(' + angle.toFixed(3) + 'rad)';
      E.damageArrows.appendChild(arrow);
      later(() => arrow.remove(), 1250);
    }
  }

  function flashPickup() {
    flashA = Math.max(flashA, 0.35);
    E.fxFlash.style.setProperty('--a', flashA.toFixed(3));
    last.fxFlashA = null;
  }

  function showTransit(title, subtitle) {
    if (title === null || title === undefined) {
      E.transit.classList.remove('show');
      later(() => {
        if (!E.transit.classList.contains('show')) E.transit.classList.add('hidden');
      }, 650);
      return;
    }
    E.transitText.textContent = title;
    E.transitSub.textContent = subtitle || '';
    E.transit.classList.remove('hidden');
    requestAnimationFrame(() => E.transit.classList.add('show'));
  }

  function fade(alpha, seconds) {
    const dur = Math.max(0, seconds || 0);
    E.fxFade.style.transitionDuration = dur.toFixed(2) + 's';
    // Flush the style so the new duration applies to this very change.
    void E.fxFade.offsetWidth;
    E.fxFade.style.opacity = String(clamp01(alpha));
  }

  // -------------------------------------------------------------------------
  // Codex
  // -------------------------------------------------------------------------

  function openCodex(save) {
    lastSave = safeSave(save || lastSave);
    rememberOrigin('codex');
    buildCodexGrid();
    showScreen('codex');
  }

  function buildCodexGrid() {
    const discovered = lastSave.discovered;
    E.codexGrid.innerHTML = '';
    codexCards = [];
    codexIndex = -1;

    let known = 0;
    SPECIES.forEach((species, i) => {
      const entry = discovered[species.id];
      const isKnown = !!entry;
      if (isKnown) known++;

      const card = el('button', 'codex-card ' + (isKnown ? 'known' : 'unknown'));
      card.type = 'button';
      const color = isKnown ? cssHex(species.colors && species.colors[0] || 0x7fe9ff) : '#0b2230';
      card.innerHTML = silhouetteSVG(species.body, color)
        + '<span class="cc-name">' + (isKnown ? species.name : '? ? ?') + '</span>'
        + (isKnown
          ? '<span class="cc-rarity" style="--rc:' + (RARITY_COLOR[species.rarity] || '#9fb6c2') + '">'
            + species.rarity + '</span>'
          : '<span class="cc-rarity dim">non identifie</span>');
      // Direct listener: the node is discarded with the grid on rebuild.
      card.addEventListener('click', () => selectCodex(i));
      E.codexGrid.appendChild(card);
      codexCards.push(card);
    });

    E.codexCount.textContent = known + ' / ' + SPECIES.length + ' identifiees';

    // Preselect the first discovered species, or the first card.
    let start = SPECIES.findIndex((s) => discovered[s.id]);
    if (start < 0) start = 0;
    selectCodex(start);
  }

  function selectCodex(index) {
    if (index < 0 || index >= SPECIES.length) return;
    if (codexIndex >= 0 && codexCards[codexIndex]) {
      codexCards[codexIndex].classList.remove('selected');
    }
    codexIndex = index;
    const card = codexCards[index];
    if (card) {
      card.classList.add('selected');
      if (card.scrollIntoView) card.scrollIntoView({ block: 'nearest' });
    }
    renderCodexDetail(SPECIES[index]);
  }

  function renderCodexDetail(species) {
    const entry = lastSave.discovered[species.id];
    const box = E.codexDetail;
    box.innerHTML = '';

    if (!entry) {
      const sil = el('div', 'cd-sil unknown');
      sil.innerHTML = silhouetteSVG(species.body, '#0d2836');
      box.appendChild(sil);
      box.appendChild(el('h3', 'cd-name', '? ? ?'));
      box.appendChild(el('p', 'cd-latin', scramble(species.latin)));
      const hint = el('div', 'cd-rows');
      hint.appendChild(cdRow('Indice profondeur', species.depth[0] + ' - ' + species.depth[1] + ' m'));
      box.appendChild(hint);
      box.appendChild(el('p', 'cd-note dim',
        'Espece non identifiee. Capturez un specimen et rapportez-le au laboratoire de l institut.'));
      return;
    }

    const sil = el('div', 'cd-sil');
    sil.innerHTML = silhouetteSVG(species.body, cssHex(species.colors && species.colors[0] || 0x7fe9ff));
    box.appendChild(sil);
    box.appendChild(el('h3', 'cd-name', species.name));
    box.appendChild(el('p', 'cd-latin', species.latin));

    const chip = el('span', 'cd-rarity', species.rarity);
    chip.style.setProperty('--rc', RARITY_COLOR[species.rarity] || '#9fb6c2');
    box.appendChild(chip);

    const biomes = (species.biomes || [])
      .map((b) => (BIOME_INFO[b] ? BIOME_INFO[b].label : b))
      .join(', ');
    const rows = el('div', 'cd-rows');
    rows.appendChild(cdRow('Profondeur', species.depth[0] + ' - ' + species.depth[1] + ' m'));
    rows.appendChild(cdRow('Biome', biomes));
    rows.appendChild(cdRow('Valeur', species.value + ' cr'));
    rows.appendChild(cdRow('Specimens', String(entry.count || 0)));
    if (species.danger === 2) rows.appendChild(cdRow('Danger', 'Predateur actif'));
    else if (species.danger === 1) rows.appendChild(cdRow('Danger', 'Contact nocif'));
    box.appendChild(rows);

    box.appendChild(el('p', 'cd-note', species.note || ''));
  }

  function cdRow(label, value) {
    const row = el('div', 'cd-row');
    row.appendChild(el('span', 'cd-k', label));
    row.appendChild(el('span', 'cd-v', value));
    return row;
  }

  function codexColumns() {
    if (!codexCards.length) return 1;
    const cw = codexCards[0].offsetWidth || 1;
    const gw = E.codexGrid.clientWidth || cw;
    return Math.max(1, Math.floor(gw / cw));
  }

  function onKeyDown(e) {
    if (screenId !== 'codex') return;
    let next = codexIndex;
    const cols = codexColumns();
    if (e.key === 'ArrowRight') next = codexIndex + 1;
    else if (e.key === 'ArrowLeft') next = codexIndex - 1;
    else if (e.key === 'ArrowDown') next = codexIndex + cols;
    else if (e.key === 'ArrowUp') next = codexIndex - cols;
    else return;
    e.preventDefault();
    if (next >= 0 && next < SPECIES.length) selectCodex(next);
  }

  // -------------------------------------------------------------------------
  // Skins
  // -------------------------------------------------------------------------

  function openSkins(save, opts) {
    lastSave = safeSave(save || lastSave);
    const o = opts || {};
    skinForcePick = !!o.forcePick;
    rememberOrigin('skins');
    buildSkinGrid();
    if (E.skinsClose) E.skinsClose.classList.toggle('hidden', skinForcePick);
    E.skinsSub.textContent = skinForcePick
      ? 'Nouvelle combinaison debloquee, choisissez votre recompense'
      : 'Choisissez votre livree';
    E.skinsSub.classList.toggle('celebrate', skinForcePick);
    showScreen('skins');
  }

  function skinOwned(skin) {
    return !skin.locked || lastSave.skins.indexOf(skin.id) >= 0;
  }

  function buildSkinGrid() {
    E.skinGrid.innerHTML = '';
    skinSelected = null;
    E.skinConfirm.disabled = true;
    E.skinDesc.textContent = '';

    // Medals still needed before the next locked skin can be picked.
    const ownedLocked = SKINS.filter((s) => s.locked && lastSave.skins.indexOf(s.id) >= 0).length;
    const need = Math.max(0, (ownedLocked + 1) * PROGRESSION.medalsPerSkin - lastSave.medals);

    SKINS.forEach((skin) => {
      const owned = skinOwned(skin);
      const pickable = owned || skinForcePick;

      const card = el('button', 'skin-card'
        + (owned ? ' owned' : ' locked')
        + (pickable ? '' : ' inert'));
      card.type = 'button';
      card.dataset.skin = skin.id;
      card.dataset.owned = owned ? '1' : '0';
      card.style.setProperty('--suit', cssHex(skin.suit));
      card.style.setProperty('--trim', cssHex(skin.trim));
      card.style.setProperty('--accent', cssHex(skin.accent));

      const swatch = el('div', 'skin-swatch');
      swatch.appendChild(el('i', 'sw-hood'));
      swatch.appendChild(el('i', 'sw-torso'));
      swatch.appendChild(el('i', 'sw-band'));
      card.appendChild(swatch);
      card.appendChild(el('span', 'skin-name', skin.name));

      if (!owned && !skinForcePick) {
        // The padlock body and shackle are drawn in CSS.
        card.appendChild(el('span', 'skin-lock'));
        card.appendChild(el('span', 'skin-need',
          need > 0 ? 'encore ' + need + ' medaille' + (need > 1 ? 's' : '') : 'pret a debloquer'));
      } else if (!owned && skinForcePick) {
        card.appendChild(el('span', 'skin-need pick', 'disponible'));
      }
      if (skin.id === lastSave.currentSkin) card.classList.add('current');

      card.addEventListener('click', () => {
        if (!pickable) {
          E.skinDesc.textContent = 'Verrouillee. ' + (need > 0
            ? 'Encore ' + need + ' medaille' + (need > 1 ? 's' : '') + ' pour la prochaine combinaison.'
            : 'Rapportez vos prises a la scientifique pour la debloquer.');
          return;
        }
        selectSkin(skin, card);
      });

      E.skinGrid.appendChild(card);
    });

    // Preselect the current skin.
    const current = SKINS.find((s) => s.id === lastSave.currentSkin) || SKINS[0];
    const cards = E.skinGrid.children;
    const idx = SKINS.indexOf(current);
    if (cards[idx] && (skinOwned(current) || skinForcePick)) selectSkin(current, cards[idx]);
  }

  function selectSkin(skin, card) {
    skinSelected = skin;
    for (const c of E.skinGrid.children) c.classList.remove('selected');
    card.classList.add('selected');
    E.skinDesc.textContent = skin.desc || '';
    E.skinConfirm.disabled = false;
  }

  // -------------------------------------------------------------------------
  // Scientist debrief
  // -------------------------------------------------------------------------

  function openScientist(report, save) {
    if (save) lastSave = safeSave(save);
    const r = report || {};
    showScreen('scientist');

    E.sciDialogue.innerHTML = '';
    E.sciResults.innerHTML = '';
    E.sciResults.classList.add('hidden');
    E.sciContinue.textContent = 'Passer';

    sci = {
      report: r,
      lines: Array.isArray(r.lines) ? r.lines : [],
      li: 0,
      ci: 0,
      pause: 0,
      para: null,
      done: false,
      interval: null,
    };
    if (!sci.lines.length) {
      finishTyping();
      return;
    }
    sci.interval = every(sciTick, 18);
  }

  function sciTick() {
    if (!sci || sci.done) return;
    if (sci.pause > 0) { sci.pause--; return; }
    const line = sci.lines[sci.li];
    if (line === undefined) { finishTyping(); return; }
    if (!sci.para) {
      sci.para = el('p', 'sci-line typing');
      E.sciDialogue.appendChild(sci.para);
    }
    sci.ci += 1;
    sci.para.textContent = line.slice(0, sci.ci);
    if (sci.ci >= line.length) {
      sci.para.classList.remove('typing');
      sci.para = null;
      sci.ci = 0;
      sci.li += 1;
      sci.pause = 22; // beat between lines
      if (sci.li >= sci.lines.length) finishTyping();
    }
  }

  function skipTyping() {
    if (!sci || sci.done) return;
    E.sciDialogue.innerHTML = '';
    for (const line of sci.lines) {
      E.sciDialogue.appendChild(el('p', 'sci-line', line));
    }
    finishTyping();
  }

  function finishTyping() {
    if (!sci) return;
    if (sci.interval) stopInterval(sci.interval);
    sci.interval = null;
    sci.done = true;
    E.sciContinue.textContent = 'Continuer';
    renderSciResults(sci.report);
  }

  function renderSciResults(report) {
    const box = E.sciResults;
    box.innerHTML = '';
    box.classList.remove('hidden');
    const handed = Array.isArray(report.handed) ? report.handed : [];

    if (handed.length) {
      const list = el('div', 'sci-handed');
      for (const item of handed) {
        const species = SPECIES_BY_ID[item.speciesId];
        const row = el('div', 'sci-row');
        const dot = el('i', 'sci-dot');
        if (species) {
          const c = RARITY_COLOR[species.rarity] || '#9fb6c2';
          dot.style.background = c;
          dot.style.boxShadow = '0 0 6px ' + c;
        }
        row.appendChild(dot);
        row.appendChild(el('span', 'sci-species', item.name || (species ? species.name : item.speciesId)));
        if (item.isNew) row.appendChild(el('span', 'sci-new', 'NOUVEAU'));
        row.appendChild(el('span', 'sci-value', '+' + (item.value || 0) + ' cr'));
        list.appendChild(row);
      }
      box.appendChild(list);
    }

    // Medals earned, counting up.
    const earned = report.medalsEarned || 0;
    if (earned > 0) {
      const medalBox = el('div', 'sci-medals');
      medalBox.appendChild(el('span', 'sci-medal-icon', '⭐'));
      const num = el('b', 'sci-medal-num', '+0');
      medalBox.appendChild(num);
      medalBox.appendChild(el('span', 'sci-medal-label',
        earned > 1 ? 'medailles' : 'medaille'));
      box.appendChild(medalBox);
      let shown = 0;
      const tick = every(() => {
        shown += 1;
        num.textContent = '+' + Math.min(shown, earned);
        if (shown >= earned) stopInterval(tick);
      }, 160);
    }

    if (report.bonus) {
      box.appendChild(el('div', 'sci-bonus',
        'Palier d expedition atteint: ' + PROGRESSION.expeditionBonusAt
        + ' especes remises d un coup. Prime de +' + PROGRESSION.expeditionBonusMedals + ' medailles.'));
    }
    if (report.skinUnlocked) {
      box.appendChild(el('div', 'sci-skin',
        'Nouvelle combinaison debloquee. L institut salue votre travail.'));
    }
    if (!handed.length && !earned) {
      box.appendChild(el('p', 'sci-empty', 'Rien a remettre cette fois. La fosse attend.'));
    }
  }

  // -------------------------------------------------------------------------
  // Death screen
  // -------------------------------------------------------------------------

  function openDead(reason, stats) {
    const info = DEATHS[reason] || DEATH_DEFAULT;
    E.deadTitle.textContent = info[0];
    E.deadText.textContent = info[1];
    E.deadStats.innerHTML = '';
    if (stats && typeof stats === 'object') {
      for (const key of Object.keys(stats)) {
        const conf = DEAD_STAT_LABELS[key];
        if (!conf) continue;
        const row = el('div', 'dead-row');
        row.appendChild(el('span', 'dead-k', conf[0]));
        row.appendChild(el('span', 'dead-v', conf[1](stats[key])));
        E.deadStats.appendChild(row);
      }
    }
    showScreen('dead');
  }

  // -------------------------------------------------------------------------
  // Title
  // -------------------------------------------------------------------------

  function refreshTitle(save) {
    lastSave = safeSave(save || lastSave);
    const discovered = Object.keys(lastSave.discovered).length;
    const box = E.titleStats;
    box.innerHTML = '';
    box.appendChild(titleStat(discovered + ' / ' + SPECIES.length, 'especes'));
    box.appendChild(titleStat(String(lastSave.medals), 'medailles'));
    box.appendChild(titleStat(String(lastSave.skins.length) + ' / ' + SKINS.length, 'combinaisons'));
    box.appendChild(titleStat(Math.round(lastSave.bestDepth) + ' m', 'prof. max'));
  }

  function titleStat(value, label) {
    const s = el('span', 'tstat');
    s.appendChild(el('b', null, value));
    s.appendChild(el('i', null, label));
    return s;
  }

  // -------------------------------------------------------------------------
  // Wiring
  // -------------------------------------------------------------------------

  function wire(id, fn) {
    const btn = $(id);
    if (btn) on(btn, 'click', fn);
  }

  wire('btn-play', () => cb.onPlay && cb.onPlay());
  wire('btn-codex', () => openCodex(lastSave));
  wire('btn-skins', () => openSkins(lastSave, { forcePick: false }));
  wire('btn-help', () => { rememberOrigin('help'); showScreen('help'); });
  wire('btn-reset', () => cb.onReset && cb.onReset());

  wire('btn-resume', () => cb.onResume && cb.onResume());
  wire('btn-pause-codex', () => openCodex(lastSave));
  wire('btn-pause-help', () => { rememberOrigin('help'); showScreen('help'); });
  wire('btn-quit', () => cb.onQuit && cb.onQuit());
  wire('btn-mute', () => {
    mutedLabel = !mutedLabel;
    E.btnMute.textContent = mutedLabel ? 'Remettre le son' : 'Couper le son';
    if (cb.onToggleMute) cb.onToggleMute();
  });

  wire('btn-respawn', () => cb.onRespawn && cb.onRespawn());

  wire('sci-continue', () => {
    if (sci && !sci.done) skipTyping();
    else if (cb.onScientistDone) cb.onScientistDone();
  });
  on(E.sciDialogue, 'click', () => { if (sci && !sci.done) skipTyping(); });

  wire('skin-confirm', () => {
    if (!skinSelected) return;
    if (cb.onSelectSkin) cb.onSelectSkin(skinSelected.id);
    if (!skinForcePick) closeScreen();
  });

  // Generic close buttons.
  for (const btn of document.querySelectorAll('[data-close]')) {
    on(btn, 'click', () => closeScreen());
  }

  // Codex keyboard navigation. Escape stays with main.js.
  on(window, 'keydown', onKeyDown);
  on(window, 'resize', refreshCompassMetrics);

  // -------------------------------------------------------------------------
  // One time construction
  // -------------------------------------------------------------------------

  buildCompass();
  buildNetSlots();
  if (E.chReloadCircle) {
    E.chReloadCircle.style.strokeDasharray = RING_CIRC.toFixed(1);
    E.chReloadCircle.style.strokeDashoffset = RING_CIRC.toFixed(1);
  }
  drawGauge(0);
  document.title = GAME_TITLE + ' - ' + GAME_SUBTITLE;

  // -------------------------------------------------------------------------
  // Dispose
  // -------------------------------------------------------------------------

  function dispose() {
    disposed = true;
    for (const [node, type, fn] of bound) node.removeEventListener(type, fn);
    bound.length = 0;
    for (const id of timers) clearTimeout(id);
    timers.clear();
    for (const id of intervals) clearInterval(id);
    intervals.clear();
    sci = null;
  }

  // -------------------------------------------------------------------------
  // Public interface
  // -------------------------------------------------------------------------

  return {
    update,
    dispose,

    showScreen,
    get currentScreen() { return screenId; },
    isModalOpen,

    setLoading,
    setHudVisible,
    toast,
    setPrompt: applyPrompt,
    flashDamage,
    flashPickup,
    showTransit,
    fade,

    openCodex,
    openSkins,
    openScientist,
    openDead,
    refreshTitle,
  };
}
