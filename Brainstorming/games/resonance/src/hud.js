/**
 * RESONANCE - DOM HUD and overlay screens. All game text lives here or in
 * index.html (accents are fine in the DOM, only canvas text avoids them).
 * This module never reads game state on its own: main.js pushes updates.
 */

import { BAND_NAMES } from './board.js';

const MEDAL_LABELS = { or: 'OR', argent: 'ARGENT', bronze: 'BRONZE' };

export function createHud(handlers) {
  const el = (id) => document.getElementById(id);

  const screens = {
    title: el('screen-title'),
    pause: el('screen-pause'),
    complete: el('screen-complete'),
    end: el('screen-end'),
  };
  const hud = el('hud');
  const banner = el('banner-fail');
  const toasts = el('toasts');
  const chips = [el('chip-0'), el('chip-1'), el('chip-2')];
  const stockEls = [el('stock-0'), el('stock-1'), el('stock-2')];

  chips.forEach((chip, b) => chip.addEventListener('click', () => handlers.onBandSelect(b)));
  el('btn-play').addEventListener('click', () => handlers.onPlay());
  el('btn-resume').addEventListener('click', () => handlers.onResume());
  el('btn-restart-pause').addEventListener('click', () => handlers.onRestart());
  el('btn-title-pause').addEventListener('click', () => handlers.onTitle());
  el('btn-next').addEventListener('click', () => handlers.onNext());
  el('btn-replay').addEventListener('click', () => handlers.onReplay());
  el('btn-end-title').addEventListener('click', () => handlers.onTitle());

  function showScreen(name) {
    for (const [k, s] of Object.entries(screens)) s.classList.toggle('hidden', k !== name);
    hud.classList.toggle('hidden', name === 'title' || name === 'end');
  }

  function setLevel(level, idx, total, best) {
    el('level-name').textContent = level.name;
    el('level-num').textContent = `${idx + 1} / ${total}`;
    el('hint').textContent = level.hint;
    el('par-value').textContent = level.par;
    el('best-value').textContent = best ? `${best.forks} (${MEDAL_LABELS[best.medal]})` : '-';
  }

  function setStock(stock, selectedBand) {
    stock.forEach((n, b) => {
      stockEls[b].textContent = n;
      chips[b].classList.toggle('selected', b === selectedBand);
      chips[b].classList.toggle('empty', n === 0);
    });
  }

  function setPoses(n) { el('poses-value').textContent = n; }

  function setMuted(m) { el('mute-state').textContent = m ? 'coupé (M)' : 'actif (M)'; }

  function showFail(on) { banner.classList.toggle('hidden', !on); }

  function toast(msg, kind = 'info') {
    const t = document.createElement('div');
    t.className = `toast ${kind}`;
    t.textContent = msg;
    toasts.appendChild(t);
    setTimeout(() => t.classList.add('out'), 2200);
    setTimeout(() => t.remove(), 2700);
    while (toasts.children.length > 4) toasts.firstChild.remove();
  }

  function showComplete(info) {
    el('complete-name').textContent = info.name;
    el('complete-medal').textContent = MEDAL_LABELS[info.medal];
    el('complete-medal').dataset.medal = info.medal;
    el('complete-detail').textContent =
      `${info.forks} diapason${info.forks > 1 ? 's' : ''} (optimum : ${info.par}) · ${info.poses} pose${info.poses > 1 ? 's' : ''} au total`;
    el('btn-next').textContent = info.isLast ? 'Voir la fin' : 'Niveau suivant (N)';
    showScreen('complete');
  }

  function bandName(b) { return BAND_NAMES[b]; }

  return {
    showScreen, setLevel, setStock, setPoses, setMuted,
    showFail, toast, showComplete, bandName,
  };
}
