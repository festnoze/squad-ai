/**
 * AIGUILLAGE - DOM HUD and screens. Pure presentation, no game logic: every
 * element id referenced here already exists in index.html. main.js wires
 * button clicks itself; this module only ever writes to the DOM.
 */

const SCREEN_IDS = ['loading', 'menu', 'controls', 'levels', 'pause', 'results', 'error'];

function el(id) {
  return document.getElementById(id);
}

function formatClock(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m + ':' + String(r).padStart(2, '0');
}

export function createHUD() {
  const hud = el('hud');
  const toastsEl = el('toasts');
  const banner = el('banner');
  const bannerTitle = el('banner-title');
  const bannerSub = el('banner-sub');
  let bannerTimer = null;

  const screens = {};
  for (const name of SCREEN_IDS) screens[name] = el('screen-' + name);

  return {
    show() {
      hud.classList.remove('hidden');
    },
    hide() {
      hud.classList.add('hidden');
    },

    showScreen(name) {
      for (const key of SCREEN_IDS) {
        if (!screens[key]) continue;
        screens[key].classList.toggle('hidden', key !== name);
      }
    },

    hideAllScreens() {
      for (const key of SCREEN_IDS) if (screens[key]) screens[key].classList.add('hidden');
    },

    setLoading(progress01, line) {
      el('loading-fill').style.width = Math.round(progress01 * 100) + '%';
      if (line) el('loading-line').textContent = line;
    },

    setLevelInfo(name) {
      el('hud-level-name').textContent = name;
    },

    setTrainCount(delivered, total) {
      el('hud-train-count').textContent = delivered + ' / ' + total + ' trains';
    },

    setClock(seconds) {
      el('hud-clock').textContent = formatClock(seconds);
    },

    setTeach(text) {
      const box = el('hud-teach');
      if (!text) {
        box.classList.add('hidden');
        return;
      }
      el('hud-teach-text').textContent = text;
      box.classList.remove('hidden');
    },

    setPauseBudget(remaining, total) {
      const ratio = total > 0 ? Math.max(0, remaining / total) : 0;
      el('pause-budget-fill').style.width = Math.round(ratio * 100) + '%';
    },

    setTacticalActive(active) {
      el('btn-tactical').classList.toggle('active', !!active);
    },

    setMuted(muted) {
      el('btn-mute-hud').textContent = muted ? '\u{1F507}' : '\u{1F50A}';
    },

    setVolume(v) {
      el('volume').value = String(Math.round(v * 100));
      el('volume-value').textContent = String(Math.round(v * 100));
    },

    toast(text) {
      const node = document.createElement('div');
      node.className = 'toast';
      node.textContent = text;
      toastsEl.appendChild(node);
      requestAnimationFrame(() => node.classList.add('show'));
      setTimeout(() => {
        node.classList.remove('show');
        setTimeout(() => node.remove(), 400);
      }, 2600);
    },

    banner(title, sub, ms) {
      bannerTitle.textContent = title;
      bannerSub.textContent = sub || '';
      banner.classList.add('show');
      if (bannerTimer) clearTimeout(bannerTimer);
      bannerTimer = setTimeout(() => banner.classList.remove('show'), ms || 3200);
    },

    /** Builds the level selection grid. `progress` = highest unlocked index. */
    setLevelGrid(levels, progress, bestScores) {
      const grid = el('level-grid');
      grid.innerHTML = '';
      levels.forEach((lvl, i) => {
        const locked = i > progress;
        const card = document.createElement('button');
        card.className = 'level-card' + (locked ? ' locked' : '');
        card.dataset.index = String(i);
        const best = bestScores[i];
        const stars = best ? '★'.repeat(best.stars) + '☆'.repeat(3 - best.stars) : '';
        card.innerHTML =
          '<span class="level-number">' + String(i + 1).padStart(2, '0') + '</span>' +
          '<span class="level-copy"><b>' + lvl.name + '</b><small>' + stars + '</small></span>';
        if (locked) card.disabled = true;
        grid.appendChild(card);
      });
    },

    setLevelDetail(lvl, best) {
      el('level-name').textContent = lvl.name;
      el('level-teach').textContent = lvl.teach || '';
      el('level-teach').classList.toggle('hidden', !lvl.teach);
      el('level-best').textContent = best
        ? 'Meilleur score : ' + best.delivered + '/' + best.total + ' (' + '★'.repeat(best.stars) + ')'
        : 'Meilleur score : -';
    },

    setResults(data) {
      el('results-title').textContent = data.success ? 'POSTE REUSSI' : 'ECHEC DU POSTE';
      el('results-sub').textContent = data.subtitle;
      el('results-delivered').textContent = String(data.delivered);
      el('results-total').textContent = String(data.total);
      el('results-late').textContent = String(data.late);
      const starsEl = el('results-stars');
      starsEl.innerHTML = '';
      for (let i = 0; i < 3; i++) {
        const span = document.createElement('span');
        span.className = 'star' + (i < data.stars ? ' lit' : '');
        span.textContent = i < data.stars ? '★' : '☆';
        starsEl.appendChild(span);
      }
      el('btn-results-next').classList.toggle('hidden', !data.hasNext);
    },
  };
}
