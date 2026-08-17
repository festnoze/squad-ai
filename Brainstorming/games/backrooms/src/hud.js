// Pure DOM manipulation, no game logic. Element ids are fixed by index.html.
function el(id) { return document.getElementById(id); }

export function createHUD() {
  const screens = {
    loading: el('screen-loading'),
    menu: el('screen-menu'),
    pause: el('screen-pause'),
    intro: el('screen-levelintro'),
    complete: el('screen-levelcomplete'),
    finale: el('screen-finale'),
    error: el('screen-error'),
  };
  const hud = el('hud');
  const toastBox = el('toast-container');
  let toastTimer = null;

  function hideAll() {
    for (const s of Object.values(screens)) if (s) s.classList.add('hidden');
  }

  function showScreen(name) {
    hideAll();
    if (screens[name]) screens[name].classList.remove('hidden');
  }

  function showHUD(v) {
    hud.classList.toggle('hidden', !v);
  }

  function setLevelInfo(name, index, total) {
    el('hud-level-name').textContent = name;
    el('hud-level-num').textContent = `${index + 1} / ${total}`;
  }

  function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function setTimer(seconds) {
    el('hud-timer').textContent = formatTime(seconds);
  }

  function setStamina(ratio01) {
    el('stamina-fill').style.width = `${Math.round(Math.max(0, Math.min(1, ratio01)) * 100)}%`;
  }

  function setBattery(ratio01, visible) {
    const row = el('battery-row');
    row.classList.toggle('hidden', !visible);
    if (visible) el('battery-fill').style.width = `${Math.round(Math.max(0, Math.min(1, ratio01)) * 100)}%`;
  }

  function setEncounters(n, limit) {
    el('hud-encounters').textContent = limit > 0 ? `${n} / ${limit}` : `${n}`;
    el('hud-encounters').classList.toggle('warn', limit > 0 && n >= limit);
  }

  function setInteractHint(text) {
    const box = el('interact-hint');
    if (!text) { box.classList.add('hidden'); return; }
    box.textContent = text;
    box.classList.remove('hidden');
  }

  function setVignette(intensity01) {
    el('vignette').style.opacity = String(Math.max(0, Math.min(1, intensity01)));
    el('desat').style.opacity = String(Math.max(0, Math.min(0.85, intensity01 * 0.9)));
  }

  function flashContact() {
    const f = el('contact-flash');
    f.style.transition = 'none';
    f.style.opacity = '0.85';
    requestAnimationFrame(() => {
      f.style.transition = 'opacity 0.6s ease-out';
      f.style.opacity = '0';
    });
  }

  function toast(text, ms = 4200) {
    const div = document.createElement('div');
    div.className = 'toast';
    div.textContent = text;
    toastBox.appendChild(div);
    requestAnimationFrame(() => div.classList.add('show'));
    setTimeout(() => {
      div.classList.remove('show');
      setTimeout(() => div.remove(), 500);
    }, ms);
  }

  function showLevelIntro(def, index, total, best) {
    el('intro-title').textContent = def.name;
    el('intro-text').textContent = def.intro;
    el('intro-progress').textContent = `Niveau ${index + 1} / ${total}`;
    el('intro-best').textContent = best ? `Meilleur temps : ${formatTime(best.time)} - ${best.medal}` : 'Pas encore tente';
    showScreen('intro');
  }

  function showLevelComplete(stats) {
    el('complete-time').textContent = formatTime(stats.time);
    el('complete-encounters').textContent = String(stats.encounters);
    el('complete-medal').textContent = stats.medal;
    el('complete-medal').className = `medal medal-${stats.medal}`;
    el('btn-next-level').classList.toggle('hidden', stats.isLast);
    el('btn-finish-run').classList.toggle('hidden', !stats.isLast);
    showScreen('complete');
  }

  function showFinale(stats) {
    el('finale-levels').textContent = String(stats.levelsCleared);
    el('finale-encounters').textContent = String(stats.totalEncounters);
    el('finale-time').textContent = formatTime(stats.totalTime);
    showScreen('finale');
  }

  function showPause(sensitivity, invertY, volume) {
    el('sens-slider').value = String(Math.round(sensitivity * 10000));
    el('sens-value').textContent = sensitivity.toFixed(4);
    el('invert-y').checked = invertY;
    el('volume-slider').value = String(Math.round(volume * 100));
    showScreen('pause');
  }

  function showError(message) {
    el('error-text').textContent = message;
    showScreen('error');
  }

  function setLoadingLine(text) {
    el('loading-line').textContent = text;
  }

  return {
    showScreen, hideAll, showHUD, setLevelInfo, setTimer, setStamina, setBattery,
    setEncounters, setInteractHint, setVignette, flashContact, toast,
    showLevelIntro, showLevelComplete, showFinale, showPause, showError,
    setLoadingLine, formatTime,
  };
}
