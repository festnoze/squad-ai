/**
 * GRAVITE NEUF - DOM interface.
 *
 * Pure DOM, no dependency. Every identifier used here exists in index.html; the
 * module never creates markup outside #level-grid and #toasts.
 */

// One colour per gravity direction, matching the sky dome in sky.js.
const AXIS_COLOR = ['#3fd7c8', '#b47cff', '#ff8ac4', '#6fa8ff', '#ffc94a', '#7ee06a'];

function byId(id) {
  return document.getElementById(id);
}

export function createHUD() {
  const el = {
    hud: byId('hud'),
    index: byId('hud-index'),
    total: byId('hud-total'),
    name: byId('hud-name'),
    moves: byId('hud-moves'),
    movesStat: byId('hud-moves').parentElement,
    par: byId('hud-par'),
    keys: byId('hud-keys'),
    keysStat: byId('stat-keys'),
    undo: byId('hud-undo'),
    hint: byId('hud-hint'),
    gravAxis: byId('grav-axis'),
    gravSwatch: byId('grav-swatch'),
    banner: byId('banner'),
    bannerTitle: byId('banner-title'),
    bannerSub: byId('banner-sub'),
    toasts: byId('toasts'),
    levelGrid: byId('level-grid'),
    loadingFill: byId('loading-fill'),
    loadingLine: byId('loading-line'),
  };

  let bannerTimer = 0;

  const hud = {};

  hud.show = function show() {
    el.hud.classList.remove('hidden');
  };

  hud.hide = function hide() {
    el.hud.classList.add('hidden');
  };

  hud.showScreen = function showScreen(id) {
    const screens = document.querySelectorAll('.screen');
    for (let i = 0; i < screens.length; i++) screens[i].classList.add('hidden');
    if (id) {
      const node = byId(id);
      if (node) node.classList.remove('hidden');
    }
  };

  hud.setLoading = function setLoading(pct, line) {
    el.loadingFill.style.width = Math.max(0, Math.min(100, pct)) + '%';
    el.loadingLine.textContent = line;
  };

  hud.setLevel = function setLevel(index, total, name, hint, par) {
    el.index.textContent = String(index + 1);
    el.total.textContent = String(total);
    el.name.textContent = name;
    el.hint.textContent = hint;
    el.par.textContent = String(par);
  };

  hud.setMoves = function setMoves(moves, par) {
    el.moves.textContent = String(moves);
    el.movesStat.classList.toggle('good', moves <= par);
    el.movesStat.classList.toggle('over', moves > par);
  };

  hud.setKeys = function setKeys(taken, total) {
    if (total === 0) {
      el.keysStat.classList.add('hidden');
      return;
    }
    el.keysStat.classList.remove('hidden');
    el.keys.textContent = taken + '/' + total;
  };

  hud.setUndo = function setUndo(count) {
    el.undo.textContent = String(count);
  };

  hud.setGravity = function setGravity(label, dirIndex) {
    el.gravAxis.textContent = label;
    const color = AXIS_COLOR[dirIndex] || '#ffc94a';
    el.gravSwatch.style.background = color;
    el.gravSwatch.style.color = color;
  };

  hud.banner = function banner(title, sub, good, ms) {
    el.bannerTitle.textContent = title;
    el.bannerSub.textContent = sub || '';
    el.banner.classList.toggle('good', !!good);
    el.banner.classList.remove('hidden');
    bannerTimer = ms ? ms / 1000 : 0;
  };

  hud.clearBanner = function clearBanner() {
    el.banner.classList.add('hidden');
    bannerTimer = 0;
  };

  hud.toast = function toast(text) {
    const node = document.createElement('div');
    node.className = 'toast';
    node.textContent = text;
    el.toasts.appendChild(node);
    window.setTimeout(() => node.classList.add('fading'), 2200);
    window.setTimeout(() => {
      if (node.parentNode) node.parentNode.removeChild(node);
    }, 2700);
  };

  /** entries: [{ name, unlocked, best, par }] */
  hud.buildLevelGrid = function buildLevelGrid(entries, onPick) {
    el.levelGrid.textContent = '';
    for (let i = 0; i < entries.length; i++) {
      const e = entries[i];
      const btn = document.createElement('button');
      btn.className = 'lvl';
      btn.type = 'button';
      btn.disabled = !e.unlocked;
      btn.title = e.unlocked ? e.name : 'Verrouille';
      const num = document.createElement('b');
      num.textContent = String(i + 1);
      const sub = document.createElement('small');
      if (e.best === null || e.best === undefined) sub.textContent = e.unlocked ? '-' : 'x';
      else sub.textContent = e.best + '/' + e.par;
      btn.appendChild(num);
      btn.appendChild(sub);
      if (e.best !== null && e.best !== undefined) {
        btn.classList.add(e.best <= e.par ? 'perfect' : 'done');
      }
      btn.addEventListener('click', () => onPick(i));
      el.levelGrid.appendChild(btn);
    }
  };

  hud.update = function update(dt) {
    if (bannerTimer > 0) {
      bannerTimer -= dt;
      if (bannerTimer <= 0) el.banner.classList.add('hidden');
    }
  };

  return hud;
}
