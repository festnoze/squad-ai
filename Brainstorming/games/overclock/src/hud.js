/**
 * OVERCLOCK - HUD and overlay screens. Pure DOM, no dependency.
 * Every id referenced here exists in index.html.
 */

const MEDALS = [
  { name: 'OR', cls: 'gold', over: 0 },
  { name: 'ARGENT', cls: 'silver', over: 2 },
  { name: 'BRONZE', cls: 'bronze', over: 4 },
  { name: 'VALIDE', cls: '', over: Infinity },
];

export function medalFor(used, optimal) {
  const over = used - optimal;
  for (const m of MEDALS) if (over <= m.over) return m;
  return MEDALS[MEDALS.length - 1];
}

function $(id) {
  return document.getElementById(id);
}

export function createHUD() {
  const el = {
    level: $('hud-level'),
    targets: $('hud-targets'),
    stack: $('hud-stack'),
    steps: $('hud-steps'),
    status: $('hud-status'),
    levelName: $('level-name'),
    levelHint: $('level-hint'),
    budgetUsed: $('budget-used'),
    budgetOptimal: $('budget-optimal'),
    budgetMedal: $('budget-medal'),
    toast: $('toast'),
    grid: $('level-grid'),
  };

  const screens = {
    title: $('screen-title'),
    levels: $('screen-levels'),
    pause: $('screen-pause'),
    win: $('screen-win'),
    end: $('screen-end'),
    error: $('screen-error'),
  };

  let lastToast = '';
  let lastToastAt = 0;

  const hud = {
    setLevel(index, total, level) {
      el.level.textContent = index + 1 + ' / ' + total;
      el.levelName.textContent = index + 1 + '. ' + level.name;
      el.levelHint.textContent = level.hint;
    },

    setTargets(lit, total) {
      el.targets.textContent = lit + ' / ' + total;
    },

    setStack(n) {
      el.stack.textContent = String(n);
    },

    setSteps(n) {
      el.steps.textContent = String(n);
    },

    setStatus(text, cls) {
      el.status.textContent = text;
      el.status.className = cls || '';
    },

    setBudget(used, optimal) {
      el.budgetUsed.textContent = String(used);
      el.budgetOptimal.textContent = String(optimal);
      if (used === 0) {
        el.budgetMedal.textContent = '-';
        el.budgetMedal.className = '';
        return;
      }
      const m = medalFor(used, optimal);
      el.budgetMedal.textContent = m.name;
      el.budgetMedal.className = m.cls;
    },

    /** Same message twice in a row within 400 ms is dropped, runs are chatty. */
    toast(text, cls) {
      const now = performance.now();
      if (text === lastToast && now - lastToastAt < 400) return;
      lastToast = text;
      lastToastAt = now;
      const line = document.createElement('div');
      line.className = 'toast-line' + (cls ? ' ' + cls : '');
      line.textContent = text;
      el.toast.appendChild(line);
      while (el.toast.children.length > 4) el.toast.removeChild(el.toast.firstChild);
      setTimeout(() => line.classList.add('fade'), 1500);
      setTimeout(() => line.remove(), 2000);
    },

    clearToasts() {
      el.toast.textContent = '';
    },

    showScreen(name) {
      for (const key of Object.keys(screens)) {
        if (screens[key]) screens[key].classList.toggle('hidden', key !== name);
      }
    },

    hideScreens() {
      for (const key of Object.keys(screens)) if (screens[key]) screens[key].classList.add('hidden');
    },

    buildLevelGrid(levels, storage, onPick) {
      el.grid.textContent = '';
      levels.forEach((lv, i) => {
        const b = document.createElement('button');
        const locked = i > storage.maxIndex;
        b.className = 'lvl' + (locked ? ' locked' : '');
        b.type = 'button';
        const best = storage.bestFor(lv.id);
        const m = best !== null ? medalFor(best, lv.optimal) : null;
        b.innerHTML =
          '<span class="num">' + String(i + 1).padStart(2, '0') + '</span>' +
          '<span class="nm">' + lv.name + '</span>' +
          (m ? '<span class="md ' + m.cls + '">' + m.name + ' ' + best + '</span>' : '');
        if (!locked) b.addEventListener('click', () => onPick(i));
        el.grid.appendChild(b);
      });
    },

    setWin(info) {
      $('win-title').textContent = info.title;
      $('win-medal').textContent = info.medal.name;
      $('win-medal').className = info.medal.cls;
      $('win-sub').textContent = info.sub;
      $('win-used').textContent = String(info.used);
      $('win-optimal').textContent = String(info.optimal);
      $('win-steps').textContent = String(info.steps);
      $('win-best').textContent = info.best === null ? '-' : String(info.best);
      // Never disabled: on the last level the same button opens the end screen.
      $('btn-next').textContent = info.hasNext ? 'NIVEAU SUIVANT' : 'ECRAN DE FIN';
    },

    setEndSummary(text) {
      $('end-sub').textContent = text;
    },
  };

  return hud;
}
