/**
 * PARADOXE - DOM overlay.
 *
 * Pure DOM, no canvas except the timeline (its own module). The ids are frozen
 * by index.html; this module only reads them once and fails loudly if one is
 * missing, because a silent null here shows up much later as a black screen.
 */

const IDS = [
  'hud',
  'hud-level-index',
  'hud-level-name',
  'hud-timer-value',
  'hud-timer-fill',
  'hud-clone-dots',
  'hud-clone-text',
  'hud-hint',
  'hud-toast',
  'hud-banner',
  'hud-banner-title',
  'hud-banner-sub',
  'timeline',
  'fx-rewind',
  'fx-flash',
  'screen-loading',
  'loading-fill',
  'screen-menu',
  'menu-progress',
  'btn-play',
  'btn-levels',
  'screen-levels',
  'level-grid',
  'btn-levels-back',
  'screen-pause',
  'btn-resume',
  'btn-restart-level',
  'btn-pause-menu',
  'screen-win',
  'win-title',
  'win-detail',
  'win-medal',
  'btn-next',
  'btn-replay',
  'screen-fail',
  'fail-title',
  'fail-detail',
  'btn-fail-retry',
  'btn-fail-undo',
  'screen-end',
  'end-detail',
  'btn-end-menu',
  'screen-error',
  'error-text',
];

export function createHUD() {
  const els = {};
  for (let i = 0; i < IDS.length; i++) {
    const el = document.getElementById(IDS[i]);
    if (!el) throw new Error('Element manquant dans index.html: #' + IDS[i]);
    els[IDS[i]] = el;
  }

  let bannerTimer = 0;
  let toastTimer = 0;

  const hud = { els };

  const SCREENS = ['screen-loading', 'screen-menu', 'screen-levels', 'screen-pause', 'screen-win', 'screen-fail', 'screen-end', 'screen-error'];

  hud.showScreen = function showScreen(name) {
    for (let i = 0; i < SCREENS.length; i++) {
      els[SCREENS[i]].classList.toggle('hidden', SCREENS[i] !== name);
    }
  };

  hud.setHudVisible = function setHudVisible(v) {
    els.hud.classList.toggle('hidden', !v);
  };

  hud.setLoading = function setLoading(ratio, label) {
    els['loading-fill'].style.width = Math.round(ratio * 100) + '%';
    if (label) els['screen-loading'].dataset.label = label;
  };

  hud.setLevel = function setLevel(index, total, name, hint) {
    els['hud-level-index'].textContent = String(index + 1).padStart(2, '0') + ' / ' + total;
    els['hud-level-name'].textContent = name;
    els['hud-hint'].textContent = hint || '';
    els['hud-hint'].classList.remove('fade');
    // Restart the CSS animation.
    void els['hud-hint'].offsetWidth;
    els['hud-hint'].classList.add('fade');
  };

  hud.setTimer = function setTimer(remaining, ratio) {
    els['hud-timer-value'].textContent = remaining.toFixed(1);
    els['hud-timer-fill'].style.transform = 'scaleX(' + Math.max(0, Math.min(1, ratio)).toFixed(4) + ')';
    els['hud-timer-value'].classList.toggle('urgent', remaining <= 3);
  };

  hud.setClones = function setClones(used, max) {
    const dots = els['hud-clone-dots'];
    // Hard bound: these two loops read from the DOM, so a bad `max` (NaN, a
    // huge number) must not be able to spin them forever.
    const slots = Number.isFinite(max) ? Math.max(0, Math.min(16, Math.floor(max))) : 0;
    while (dots.children.length < slots) {
      const d = document.createElement('i');
      dots.appendChild(d);
    }
    while (dots.children.length > slots) dots.removeChild(dots.lastChild);
    for (let i = 0; i < dots.children.length; i++) {
      dots.children[i].className = i < used ? 'on' : '';
    }
    els['hud-clone-text'].textContent = used + ' / ' + max;
  };

  hud.banner = function banner(title, sub, ms) {
    els['hud-banner-title'].textContent = title;
    els['hud-banner-sub'].textContent = sub || '';
    els['hud-banner'].classList.add('show');
    bannerTimer = (ms || 1600) / 1000;
  };

  hud.toast = function toast(text, kind) {
    els['hud-toast'].textContent = text;
    els['hud-toast'].className = 'show ' + (kind || '');
    toastTimer = 1.8;
  };

  hud.setRewind = function setRewind(t) {
    els['fx-rewind'].style.opacity = t > 0 ? String(0.15 + t * 0.45) : '0';
    els['fx-rewind'].classList.toggle('active', t > 0);
  };

  hud.flash = function flash(kind) {
    const el = els['fx-flash'];
    el.className = 'on ' + (kind || '');
    void el.offsetWidth;
    el.className = kind || '';
  };

  hud.update = function update(dt) {
    if (bannerTimer > 0) {
      bannerTimer -= dt;
      if (bannerTimer <= 0) els['hud-banner'].classList.remove('show');
    }
    if (toastTimer > 0) {
      toastTimer -= dt;
      if (toastTimer <= 0) els['hud-toast'].className = '';
    }
  };

  hud.setWin = function setWin(levelName, clones, medal, best) {
    els['win-title'].textContent = levelName + ' resolu';
    let detail = clones + (clones > 1 ? ' clones utilises' : ' clone utilise');
    if (clones === 0) detail = 'Aucun clone: resolu du premier coup';
    if (best !== null && best !== undefined) detail += ' - meilleur: ' + best;
    els['win-detail'].textContent = detail;
    els['win-medal'].classList.toggle('hidden', !medal);
  };

  hud.setFail = function setFail(title, detail, canUndo) {
    els['fail-title'].textContent = title;
    els['fail-detail'].textContent = detail;
    els['btn-fail-undo'].classList.toggle('hidden', !canUndo);
  };

  hud.setEnd = function setEnd(text) {
    els['end-detail'].textContent = text;
  };

  hud.setMenuProgress = function setMenuProgress(text) {
    els['menu-progress'].textContent = text;
  };

  /**
   * Rebuild the level picker. `onPick(index)` is called for unlocked entries.
   */
  hud.buildLevelGrid = function buildLevelGrid(levels, progress, best, onPick) {
    const grid = els['level-grid'];
    grid.textContent = '';
    for (let i = 0; i < levels.length; i++) {
      const btn = document.createElement('button');
      const unlocked = i <= progress;
      btn.className = 'level-cell' + (unlocked ? '' : ' locked');
      btn.disabled = !unlocked;
      const num = document.createElement('b');
      num.textContent = String(i + 1).padStart(2, '0');
      const name = document.createElement('span');
      name.textContent = unlocked ? levels[i].name : 'Verrouille';
      btn.appendChild(num);
      btn.appendChild(name);
      const b = best[i];
      if (unlocked && b !== undefined && b !== null) {
        const s = document.createElement('em');
        s.textContent = b === 0 ? 'sans clone' : b + (b > 1 ? ' clones' : ' clone');
        if (b <= levels[i].medalClones) s.classList.add('medal');
        btn.appendChild(s);
      }
      if (unlocked) btn.addEventListener('click', () => onPick(i));
      grid.appendChild(btn);
    }
  };

  hud.showError = function showError(message) {
    els['error-text'].textContent = message;
    hud.showScreen('screen-error');
  };

  return hud;
}
