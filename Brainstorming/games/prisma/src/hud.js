/**
 * PRISMA - DOM interface.
 *
 * Pure DOM, no three.js. Every identifier it touches is declared in index.html;
 * nothing here creates a screen that does not already exist there.
 */

import { COLOR_NAMES, CELL, CELL_TO_KIND } from './grid.js';
import { PIECE_KINDS, PIECE_LABEL, PIECE_HELP, ROTATIONS } from './levels.js';

const MASK_CSS = ['#666680', '#ff3a44', '#3dff68', '#ffdc3d', '#4a7cff', '#ff56ee', '#4ef7ff', '#ffffff'];

export const MEDALS = [
  { key: 'or', label: 'Or', css: 'm-gold' },
  { key: 'argent', label: 'Argent', css: 'm-silver' },
  { key: 'bronze', label: 'Bronze', css: 'm-bronze' },
  { key: 'aucune', label: 'Resolu', css: 'm-none' },
];

export function medalFor(used, optimum) {
  if (used <= optimum) return MEDALS[0];
  if (used <= optimum + 1) return MEDALS[1];
  if (used <= optimum + 2) return MEDALS[2];
  return MEDALS[3];
}

function el(id) {
  const node = document.getElementById(id);
  if (!node) throw new Error(`Element #${id} absent de index.html`);
  return node;
}

export function createHUD(icons) {
  const dom = {
    hud: el('hud'),
    levelIndex: el('level-index'),
    levelName: el('level-name'),
    statTargets: el('stat-targets'),
    statPieces: el('stat-pieces'),
    statOptimum: el('stat-optimum'),
    targetsStrip: el('targets-strip'),
    hintBar: el('hint-bar'),
    hintText: el('hint-text'),
    inventory: el('inventory'),
    toasts: el('toasts'),
    banner: el('banner'),
    bannerTitle: el('banner-title'),
    bannerSub: el('banner-sub'),
    btnMute: el('btn-mute'),
    levelGrid: el('level-grid'),
    levelsSub: el('levels-sub'),
    winMedal: el('win-medal'),
    winTitle: el('win-title'),
    winSub: el('win-sub'),
    winDetail: el('win-detail'),
    pauseSub: el('pause-sub'),
    endStats: el('end-stats'),
    loadingFill: el('loading-fill'),
    loadingLine: el('loading-line'),
  };

  const screens = {
    loading: el('screen-loading'),
    title: el('screen-title'),
    levels: el('screen-levels'),
    pause: el('screen-pause'),
    win: el('screen-win'),
    end: el('screen-end'),
    error: el('screen-error'),
  };

  const slots = new Map();
  let hintTimer = 0;

  /** Once the error screen is up it stays up: nothing may hide a crash report. */
  function errorLatched() {
    return !screens.error.classList.contains('hidden');
  }

  function showScreen(name) {
    if (errorLatched()) return;
    for (const [key, node] of Object.entries(screens)) {
      node.classList.toggle('hidden', key !== name);
    }
  }

  function hideScreens() {
    if (errorLatched()) return;
    for (const node of Object.values(screens)) node.classList.add('hidden');
  }

  function setLoading(pct, line) {
    dom.loadingFill.style.width = `${Math.round(pct * 100)}%`;
    if (line) dom.loadingLine.textContent = line;
  }

  function show() {
    dom.hud.classList.remove('hidden');
  }

  function hide() {
    dom.hud.classList.add('hidden');
  }

  function setLevel(number, level) {
    dom.levelIndex.textContent = String(number).padStart(2, '0');
    dom.levelName.textContent = level.name;
    dom.statOptimum.textContent = String(level.optimum);
  }

  function setStats(lit, total, pieces) {
    dom.statTargets.textContent = `${lit}/${total}`;
    dom.statTargets.parentElement.classList.toggle('good', lit === total && total > 0);
    dom.statPieces.textContent = String(pieces);
  }

  function setTargets(grid, res) {
    const wanted = grid.targets.length;
    while (dom.targetsStrip.children.length > wanted) {
      dom.targetsStrip.removeChild(dom.targetsStrip.lastChild);
    }
    while (dom.targetsStrip.children.length < wanted) {
      const chip = document.createElement('div');
      chip.className = 'target-chip';
      chip.innerHTML = '<span class="chip-dot"></span><span class="chip-text"></span>';
      dom.targetsStrip.appendChild(chip);
    }
    for (let i = 0; i < wanted; i++) {
      const chip = dom.targetsStrip.children[i];
      const target = grid.targets[i];
      const lit = res.targetLit[i] === 1;
      chip.style.color = MASK_CSS[target.mask & 7];
      chip.classList.toggle('lit', lit);
      const got = res.targetGot[i];
      const label = COLOR_NAMES[target.mask].toUpperCase();
      chip.lastChild.textContent = lit
        ? label
        : got
          ? `${label} (recu ${COLOR_NAMES[got]})`
          : `${label} (eteinte)`;
    }
  }

  /** Slots are rebuilt once per level: only the counts change afterwards. */
  function buildInventory(level, onSelect) {
    dom.inventory.replaceChildren();
    slots.clear();
    PIECE_KINDS.forEach((kind, i) => {
      const stock = level.inventory[kind] || 0;
      const slot = document.createElement('button');
      slot.className = 'slot' + (stock === 0 ? ' absent' : '');
      slot.type = 'button';
      slot.title = `${PIECE_LABEL[kind]} - ${PIECE_HELP[kind]} (${ROTATIONS[kind]} orientations)`;
      slot.innerHTML =
        `<span class="slot-key">${i + 1}</span>` +
        `<span class="slot-icon" style="background-image:url(${icons[kind]})"></span>` +
        `<span class="slot-name">${PIECE_LABEL[kind]}</span>` +
        '<span class="slot-count">0</span>';
      slot.addEventListener('click', () => onSelect(kind));
      dom.inventory.appendChild(slot);
      slots.set(kind, slot);
    });
  }

  function updateInventory(grid, selectedKind) {
    for (const [kind, slot] of slots) {
      const stock = grid.inventory[kind] || 0;
      if (stock === 0) continue;
      let placed = 0;
      for (const cell of grid.cells) {
        if (!cell.fixed && cell.type !== CELL.EMPTY && CELL_TO_KIND[cell.type] === kind) placed++;
      }
      const left = stock - placed;
      slot.querySelector('.slot-count').textContent = `${left}/${stock}`;
      slot.classList.toggle('empty', left <= 0);
      slot.classList.toggle('selected', kind === selectedKind);
    }
  }

  function setHint(text, sticky = false) {
    dom.hintText.textContent = text;
    dom.hintBar.classList.toggle('hidden', !text);
    dom.hintBar.classList.remove('faded');
    window.clearTimeout(hintTimer);
    if (text && !sticky) {
      hintTimer = window.setTimeout(() => dom.hintBar.classList.add('faded'), 9000);
    }
  }

  function toast(text, warn = false) {
    const node = document.createElement('div');
    node.className = warn ? 'toast warn' : 'toast';
    node.textContent = text;
    dom.toasts.appendChild(node);
    window.setTimeout(() => node.remove(), 1950);
    while (dom.toasts.children.length > 4) dom.toasts.removeChild(dom.toasts.firstChild);
  }

  let bannerTimer = 0;
  function banner(title, sub, ms = 1600) {
    dom.bannerTitle.textContent = title;
    dom.bannerSub.textContent = sub || '';
    dom.banner.classList.remove('on');
    void dom.banner.offsetWidth; // restart the animation
    dom.banner.classList.add('on');
    window.clearTimeout(bannerTimer);
    bannerTimer = window.setTimeout(() => dom.banner.classList.remove('on'), ms);
  }

  function setMuted(muted) {
    dom.btnMute.classList.toggle('off', muted);
    dom.btnMute.innerHTML = muted ? 'Son coupe <kbd>M</kbd>' : 'Son <kbd>M</kbd>';
  }

  function buildLevelGrid(levels, progress, currentIndex, onPick) {
    dom.levelGrid.replaceChildren();
    let golds = 0;
    let solved = 0;
    levels.forEach((level, i) => {
      const best = progress.best[level.id];
      const unlocked = i <= progress.unlocked;
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'level-card' + (unlocked ? '' : ' locked') + (i === currentIndex ? ' current' : '');
      const medal = best === undefined ? MEDALS[3] : medalFor(best, level.optimum);
      if (best !== undefined) {
        solved++;
        if (medal.key === 'or') golds++;
      }
      card.innerHTML =
        `<span class="medal-dot ${best === undefined ? 'm-none' : medal.css}"></span>` +
        `<span class="level-num">${String(i + 1).padStart(2, '0')}</span>` +
        `<span class="level-title">${level.name}</span>` +
        `<span class="level-score">${best === undefined ? `optimum ${level.optimum}` : `${best} / ${level.optimum} - ${medal.label}`}</span>`;
      if (unlocked) card.addEventListener('click', () => onPick(i));
      dom.levelGrid.appendChild(card);
    });
    dom.levelsSub.textContent = `${solved} resolues sur ${levels.length} - ${golds} en or`;
  }

  function setWin({ medal, used, optimum, levelName, isLast, improved }) {
    dom.winMedal.textContent = medal.label;
    dom.winMedal.className = `medal ${medal.css}`;
    dom.winTitle.textContent = isLast ? 'Derniere chambre resolue' : 'Chambre resolue';
    dom.winSub.textContent = levelName;
    const delta = used - optimum;
    let detail = `${used} composant${used > 1 ? 's' : ''} pose${used > 1 ? 's' : ''}, optimum connu ${optimum}.`;
    if (delta <= 0) detail += ' Rien a retirer : trajet parfait.';
    else if (delta === 1) detail += ' Un composant de trop pour la medaille d or.';
    else detail += ` ${delta} composants de trop pour la medaille d or.`;
    if (improved) detail += ' Nouveau meilleur score.';
    dom.winDetail.textContent = detail;
  }

  function setPauseSub(text) {
    dom.pauseSub.textContent = text;
  }

  function setEndStats(text) {
    dom.endStats.textContent = text;
  }

  return {
    show,
    hide,
    showScreen,
    hideScreens,
    setLoading,
    setLevel,
    setStats,
    setTargets,
    buildInventory,
    updateInventory,
    setHint,
    toast,
    banner,
    setMuted,
    buildLevelGrid,
    setWin,
    setPauseSub,
    setEndStats,
  };
}
