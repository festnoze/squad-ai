/**
 * PONTS DE FORTUNE - DOM interface.
 *
 * Pure DOM, no three.js. Every identifier used here exists in index.html; this
 * module never creates layout, only fills it and toggles state classes.
 */

import { MATERIALS, MATERIAL_ORDER } from './config.js';

function el(id) {
  const node = document.getElementById(id);
  if (!node) throw new Error('element DOM manquant: #' + id);
  return node;
}

export function createHUD() {
  const dom = {
    hud: el('hud'),
    levelIndex: el('hud-level-index'),
    levelName: el('hud-level-name'),
    levelBrief: el('hud-level-brief'),
    levelHint: el('hud-level-hint'),
    budgetPanel: el('panel-budget'),
    budgetLeft: el('budget-left'),
    budgetTotal: el('budget-total'),
    budgetSpent: el('budget-spent'),
    budgetCount: el('budget-count'),
    budgetFill: el('budget-fill'),
    palette: el('palette'),
    matBlurb: el('mat-blurb'),
    cursorInfo: el('cursor-info'),
    cursorCost: el('cursor-cost'),
    cursorReason: el('cursor-reason'),
    testStatus: el('test-status'),
    testLoad: el('test-load'),
    stressLabel: el('stress-label'),
    stressFill: el('stress-fill'),
    replayNote: el('replay-note'),
    toasts: el('toasts'),
    levelGrid: el('level-grid'),
    winStats: el('win-stats'),
    winTitle: el('win-title'),
    winSub: el('win-sub'),
    loseReason: el('lose-reason'),
    loseDetail: el('lose-detail'),
    titleProgress: el('title-progress'),
    loadingFill: el('loading-fill'),
    loadingLine: el('loading-line'),
    volume: el('volume'),
    volumeValue: el('volume-value'),
    errorText: el('error-text'),
  };

  const buttons = {
    play: el('btn-play'),
    levels: el('btn-levels'),
    levelsBack: el('btn-levels-back'),
    test: el('btn-test'),
    abort: el('btn-abort'),
    undo: el('btn-undo'),
    clear: el('btn-clear'),
    view: el('btn-view'),
    resume: el('btn-resume'),
    restart: el('btn-restart-level'),
    quit: el('btn-quit'),
    next: el('btn-next'),
    replayLevel: el('btn-replay-level'),
    winLevels: el('btn-win-levels'),
    retry: el('btn-retry'),
    loseLevels: el('btn-lose-levels'),
  };

  const matButtons = new Map();
  dom.palette.querySelectorAll('.mat-btn').forEach((btn) => {
    matButtons.set(btn.dataset.mat, btn);
    const cost = btn.querySelector('.mat-cost');
    cost.textContent = MATERIALS[btn.dataset.mat].cost.toFixed(1) + '/m';
  });

  let materialHandler = null;
  dom.palette.addEventListener('click', (e) => {
    const btn = e.target.closest('.mat-btn');
    if (!btn || btn.classList.contains('locked')) return;
    if (materialHandler) materialHandler(btn.dataset.mat);
  });

  function show() { dom.hud.classList.remove('hidden'); }
  function hide() { dom.hud.classList.add('hidden'); }

  function setMode(mode) {
    document.body.classList.remove('mode-build', 'mode-test', 'mode-replay');
    document.body.classList.add('mode-' + mode);
  }

  function showScreen(id) {
    document.querySelectorAll('.screen').forEach((s) => s.classList.add('hidden'));
    if (id) el(id).classList.remove('hidden');
  }

  function setLevel(level, index, total) {
    dom.levelIndex.textContent = (index + 1) + ' / ' + total;
    dom.levelName.textContent = level.name;
    dom.levelBrief.textContent = level.brief;
    dom.levelHint.textContent = level.hint;
  }

  function setBudget(spent, total, count) {
    const left = total - spent;
    dom.budgetLeft.textContent = String(left);
    dom.budgetTotal.textContent = String(total);
    dom.budgetSpent.textContent = String(spent);
    dom.budgetCount.textContent = String(count);
    const pct = Math.max(0, Math.min(100, (left / Math.max(1, total)) * 100));
    dom.budgetFill.style.width = pct.toFixed(1) + '%';
    dom.budgetPanel.classList.toggle('tight', pct < 22);
  }

  function setPalette(allowed, current) {
    for (let i = 0; i < MATERIAL_ORDER.length; i++) {
      const key = MATERIAL_ORDER[i];
      const btn = matButtons.get(key);
      if (!btn) continue;
      const ok = allowed.indexOf(key) >= 0;
      btn.classList.toggle('locked', !ok);
      btn.classList.toggle('active', ok && key === current);
    }
    dom.matBlurb.textContent = MATERIALS[current] ? MATERIALS[current].blurb : '';
  }

  function setCursor(cost, reason, ok) {
    if (cost === null) {
      dom.cursorInfo.classList.remove('on');
      return;
    }
    dom.cursorInfo.classList.add('on');
    dom.cursorInfo.classList.toggle('ok', !!ok);
    dom.cursorCost.textContent = cost;
    dom.cursorReason.textContent = reason || '';
  }

  function setTest(status, loadKg, ratio) {
    dom.testStatus.textContent = status;
    dom.testLoad.textContent = (loadKg / 1000).toFixed(1) + ' t';
    const pct = Math.max(0, Math.min(100, ratio * 100));
    dom.stressFill.style.width = pct.toFixed(0) + '%';
    dom.stressLabel.textContent = pct.toFixed(0) + ' %';
  }

  function setReplayNote(text) { dom.replayNote.textContent = text; }

  function toast(text, kind) {
    const node = document.createElement('div');
    node.className = 'toast' + (kind ? ' ' + kind : '');
    node.textContent = text;
    dom.toasts.appendChild(node);
    window.setTimeout(() => { if (node.parentNode) node.parentNode.removeChild(node); }, 2400);
    while (dom.toasts.children.length > 4) dom.toasts.removeChild(dom.toasts.firstChild);
  }

  function setLevelGrid(levels, progress, onPick) {
    dom.levelGrid.textContent = '';
    for (let i = 0; i < levels.length; i++) {
      const lv = levels[i];
      const rec = progress.levels[lv.key];
      const unlocked = i <= progress.unlocked;
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'level-card' + (unlocked ? '' : ' locked') + (rec && rec.done ? ' done' : '');
      const meta = rec && rec.done
        ? 'reste ' + rec.credits + ' cr &middot; ' + (rec.load / 1000).toFixed(1) + ' t'
        : 'portee ' + (lv.right - lv.left) * 4 + ' m &middot; ' + lv.budget + ' cr';
      card.innerHTML = '<span class="lc-idx">CHANTIER ' + String(i + 1).padStart(2, '0') + '</span>'
        + '<span class="lc-name">' + lv.name + '</span>'
        + '<span class="lc-meta">' + meta + '</span>'
        + (rec && rec.done ? '<span class="lc-flag">OK</span>' : '');
      if (unlocked) card.addEventListener('click', () => onPick(i));
      dom.levelGrid.appendChild(card);
    }
  }

  function setWin(level, rows, title, sub) {
    dom.winTitle.textContent = title;
    dom.winSub.textContent = sub;
    dom.winStats.textContent = '';
    for (let i = 0; i < rows.length; i++) {
      const li = document.createElement('li');
      const a = document.createElement('span');
      a.textContent = rows[i][0];
      const b = document.createElement('b');
      b.textContent = rows[i][1];
      li.appendChild(a);
      li.appendChild(b);
      dom.winStats.appendChild(li);
    }
  }

  function setLose(reason, detail) {
    dom.loseReason.textContent = reason;
    dom.loseDetail.textContent = detail || '';
  }

  function setProgressLine(done, total) {
    dom.titleProgress.textContent = done > 0
      ? done + ' CHANTIER' + (done > 1 ? 'S' : '') + ' TERMINE' + (done > 1 ? 'S' : '') + ' SUR ' + total
      : 'AUCUN CHANTIER TERMINE';
  }

  function setLoading(pct, line) {
    dom.loadingFill.style.width = Math.round(pct * 100) + '%';
    if (line) dom.loadingLine.textContent = line;
  }

  function onMaterial(cb) { materialHandler = cb; }

  function setUndoEnabled(v) { buttons.undo.disabled = !v; }

  return {
    dom, buttons,
    show, hide, setMode, showScreen, setLevel, setBudget, setPalette, setCursor,
    setTest, setReplayNote, toast, setLevelGrid, setWin, setLose, setProgressLine,
    setLoading, onMaterial, setUndoEnabled,
  };
}
