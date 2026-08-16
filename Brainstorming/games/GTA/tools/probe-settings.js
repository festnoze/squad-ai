/*
 * Task 12 - persisted settings.
 *
 * Two phases in one file, because the acceptance test is "reload the page and the choices
 * hold", and a page-side script cannot outlive its own document. `tools/probe-settings-run.mjs`
 * evaluates this file, calls page.reload(), and evaluates it again against the second boot.
 *
 *   phase 1 (nothing stored yet): drive the *real* pause menu - Escape, then clicks on the
 *           actual buttons and drags on the actual sliders - and check the store is written.
 *   phase 2 (a phase-1 marker is stored): assert every choice came back, and that quality
 *           and resolution reached the pipeline while it was being built rather than being
 *           re-applied over a default one.
 *
 * Run under tools/shoot.mjs on its own it will only ever see phase 1: a freshly launched
 * Chromium has empty storage. That is why the runner exists.
 */
(async () => {
const g = window.game, E = g.engine;
const log = []; const T0 = performance.now();
const BUDGET = 180000;
const ok = (n, c, x) => log.push({ step: n, pass: !!c, ...(x !== undefined ? { info: String(x) } : {}) });
const out = () => performance.now() - T0 > BUDGET;
// Frame-based waiting, not sim-time: the fixed step is gated while the pause menu is open,
// so anything counting simulation seconds would hang the moment the menu appears.
const frames = async (n) => { for (let i = 0; i < n && !out(); i++) await new Promise((r) => requestAnimationFrame(r)); };
const down = (code) => window.dispatchEvent(new KeyboardEvent('keydown', { code, bubbles: true }));
const up = (code) => window.dispatchEvent(new KeyboardEvent('keyup', { code, bubbles: true }));
const tap = async (c) => { down(c); await frames(4); up(c); await frames(4); };

const SETTINGS_KEY = 'liberty-horizon:settings:v1';
const SAVE_KEY = 'liberty-horizon:save:v1';
const QUALITIES = ['low', 'medium', 'high', 'ultra'];
const S = g.settings;

/** What the four persisted preferences currently are, read from the live systems. */
const live = () => ({
  quality: g.postfx.quality,
  volume: +g.audio.volume.toFixed(3),
  resolutionScale: +E.resolutionScale.toFixed(3),
  post: g.postfx.enabled,
});

const phase = S && S.get('probePhase') === 1 ? 2 : 1;

/* =============================================================== phase 1: choose */
if (phase === 1) {
  ok('game exposes a settings store',
    !!S && typeof S.set === 'function' && typeof S.number === 'function');
  S.clear();
  ok('store starts empty on a fresh browser', Object.keys(S.all()).length === 0);

  // Expectations come off the URL, because a URL parameter outranks the store by design and
  // the standard capture harness boots with `?post=off`.
  const urlParams = new URLSearchParams(location.search);
  const before = live();
  ok('nothing stored means defaults, or whatever the URL pinned',
    before.quality === (urlParams.get('quality') ?? 'high')
    && before.post === (urlParams.get('post') !== 'off')
    && before.resolutionScale === 1 && Math.abs(before.volume - 0.65) < 1e-6,
    `${JSON.stringify(before)} with "${location.search || 'no params'}"`);

  await tap('Escape');
  ok('pause menu opens on Escape',
    g.pauseMenu.open === true && !document.getElementById('pause').hidden);
  const settingsTab = [...document.querySelectorAll('#pause-body .tabs button')]
    .find((b) => b.dataset.tab === 'settings');
  settingsTab.click();
  await frames(2);
  const panel = document.getElementById('pause-settings');
  ok('settings tab shows', !panel.hidden);

  const rowNamed = (name) => [...panel.querySelectorAll('.row.setting')]
    .find((r) => r.querySelector('span') && r.querySelector('span').textContent === name);
  const pick = (name, label) => {
    const row = rowNamed(name);
    const b = row && [...row.querySelectorAll('.choices button')].find((x) => x.textContent === label);
    if (b) b.click();
    return !!b;
  };
  const slide = (name, v) => {
    const row = rowNamed(name);
    const input = row && row.querySelector('input[type=range]');
    if (!input) return null;
    input.value = String(v);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return Number(input.value);
  };

  const clickedPost = pick('Post FX', 'off');
  await frames(2);
  // Rebuilds the whole node graph synchronously inside the click handler.
  const clickedQuality = pick('Quality', 'low');
  await frames(2);
  const slidRes = slide('Resolution', 0.7);
  await frames(2);
  const slidVol = slide('Volume', 0.2);
  await frames(2);

  ok('every settings control was found and driven',
    clickedPost && clickedQuality && slidRes === 0.7 && slidVol === 0.2,
    `post=${clickedPost} quality=${clickedQuality} res=${slidRes} vol=${slidVol}`);

  const chosen = live();
  ok('quality applies live', chosen.quality === 'low', chosen.quality);
  ok('volume applies live', Math.abs(g.audio.volume - 0.2) < 1e-6
    && (!g.audio.master || Math.abs(g.audio.master.gain.value - 0.2) < 1e-6),
    `volume ${g.audio.volume}, gain ${g.audio.master && g.audio.master.gain.value}`);
  ok('resolution applies live', Math.abs(E.resolutionScale - 0.7) < 1e-6, `scale ${E.resolutionScale}`);
  ok('post toggle applies live', g.postfx.enabled === false, `enabled ${g.postfx.enabled}`);
  ok('picking a preset does not switch post back on',
    g.postfx.enabled === false && !!g.postfx.post,
    `enabled ${g.postfx.enabled}, chain ${!!g.postfx.post}`);

  /* ---------------------------------------------------------------- storage layer */
  S.flush();
  const rawSettings = JSON.parse(localStorage.getItem(SETTINGS_KEY) || 'null');
  ok('preferences are written to localStorage', !!rawSettings && !!rawSettings.values,
    rawSettings && JSON.stringify(rawSettings.values));
  const v = (rawSettings && rawSettings.values) || {};
  ok('all four values are in the stored blob',
    v.quality === 'low' && Math.abs(v.volume - 0.2) < 1e-6
    && Math.abs(v.resolutionScale - 0.7) < 1e-6 && v.post === false,
    JSON.stringify(v));

  // Preferences must not ride in the save slot, and deleting a save must not take them.
  g.money = 4242;
  g.save.save();
  const savedBlob = localStorage.getItem(SAVE_KEY) || '';
  ok('the save slot carries no preferences',
    savedBlob.length > 0 && !/"quality"|"resolutionScale"|"post"/.test(savedBlob),
    `${savedBlob.length} chars`);
  g.save.clear();
  ok('deleting the save keeps preferences',
    localStorage.getItem(SAVE_KEY) === null && localStorage.getItem(SETTINGS_KEY) !== null);

  // A hand-edited or stale value must not be able to brick boot: the typed accessors fall
  // back rather than handing a garbage preset to PostFX.
  S.set('quality', 'banana'); S.set('resolutionScale', -3);
  ok('corrupt values fall back instead of propagating',
    S.choice('quality', 'high', QUALITIES) === 'high'
    && S.number('resolutionScale', 1, 0.5, 1) === 0.5,
    `choice=${S.choice('quality', 'high', QUALITIES)} number=${S.number('resolutionScale', 1, 0.5, 1)}`);

  /*
   * Put the real choices back, plus what phase 2 needs to recognise itself. `timeOrigin` is
   * stamped when a document is created, so phase 2 comparing its own against this one is a
   * hard proof that it is a different document and not the same page still running.
   */
  S.setMany({ quality: 'low', resolutionScale: 0.7, volume: 0.2, post: false,
    probePhase: 1, probeOrigin: Math.round(performance.timeOrigin) });
  ok('flush to localStorage succeeds', S.flush() === true);

  await tap('Escape');
  ok('pause menu closes', g.pauseMenu.open === false);

  return { phase, before, chosen, ranOutOfTime: out(),
    wallSeconds: Math.round((performance.now() - T0) / 1000),
    passed: log.filter((l) => l.pass).length, total: log.length,
    failures: log.filter((l) => !l.pass), log };
}

/* ============================================== phase 2: the document after reload */
const after = live();
const origin = Math.round(performance.timeOrigin);
ok('this is a genuinely different document', origin !== S.get('probeOrigin'),
  `timeOrigin ${origin} vs stored ${S.get('probeOrigin')} (${origin - S.get('probeOrigin')} ms apart)`);
// `webgl=1` is allowed through: it picks a backend, it does not pin any stored preference.
ok('the reload URL pins none of the persisted settings',
  !/quality=|post=/.test(location.search), location.search || '(none)');

ok('quality survives the reload', after.quality === 'low', `quality ${after.quality}`);
ok('volume survives the reload', Math.abs(g.audio.volume - 0.2) < 1e-6,
  `volume ${g.audio.volume}, gain ${g.audio.master && g.audio.master.gain.value}`);
ok('resolution scale survives the reload', Math.abs(E.resolutionScale - 0.7) < 1e-6,
  `scale ${E.resolutionScale}`);
ok('post toggle survives the reload', g.postfx.enabled === false && !!g.postfx.post,
  `enabled ${g.postfx.enabled}, chain built ${!!g.postfx.post}`);

/*
 * The point of the whole task: the preset has to be known *before* the pipeline is built,
 * not applied over the top of a default one. PostFX only builds in its constructor and in
 * setQuality, nothing calls setQuality at boot, and the low preset has no AO stage - so a
 * chain with no aoPass is a chain that was built from the stored preset on the first try.
 */
ok('quality reached the pipeline at build time, not after first render',
  g.postfx.aoPass === undefined && !!g.postfx.post, `aoPass ${g.postfx.aoPass}`);

// Same story for the swap chain: the very first setSize already used the stored scale.
const dpr = E.renderer.getPixelRatio();
const ratio = E.renderer.domElement.width / (window.innerWidth * dpr);
ok('the swap chain was sized from the stored scale', Math.abs(ratio - 0.7) < 0.02,
  `${E.renderer.domElement.width}px of ${window.innerWidth * dpr}px = ${ratio.toFixed(3)}`);

// And the reloaded document is a working game, not a frozen one.
const f0 = E.frame;
await frames(6);
ok('the reloaded document keeps rendering', E.frame >= f0 + 5,
  `${f0} -> ${E.frame} frames, ${E.stats.fps} fps`);

/* ------------------------------------------------------------------------ cleanup */
S.clear();
const leftover = localStorage.getItem(SETTINGS_KEY);
ok('cleanup left no stored preferences',
  leftover === null || Object.keys(JSON.parse(leftover).values).length === 0, leftover);

return { phase, after, ranOutOfTime: out(),
  wallSeconds: Math.round((performance.now() - T0) / 1000),
  passed: log.filter((l) => l.pass).length, total: log.length,
  failures: log.filter((l) => !l.pass), log };
})()
