/**
 * PONTS DE FORTUNE - synthesised audio.
 *
 * No sound file anywhere. Two persistent voices (the convoy engine and the
 * timber creak) are started once and only ever ramped, so they never click;
 * everything else is a short lived voice that disconnects itself when it ends.
 *
 * The creak is the important one: it rises with the worst stress ratio in the
 * structure, which means the player hears the bridge complain before it fails.
 */

const NOISE_SECONDS = 2.2;

function mulberry32(seed) {
  let a = seed >>> 0;
  return function random() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function createAudio() {
  let ctx = null;
  let master = null;
  let comp = null;
  let sfx = null;
  let noise = null;

  let engineOsc = null;
  let engineSub = null;
  let engineFilter = null;
  let engineGain = null;

  let creakSrc = null;
  let creakFilter = null;
  let creakGain = null;

  let volume = 0.7;
  let muted = false;
  let ready = false;

  function buildNoise() {
    const len = Math.floor(ctx.sampleRate * NOISE_SECONDS);
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    const rand = mulberry32(0x1234abcd);
    for (let i = 0; i < len; i++) d[i] = rand() * 2 - 1;
    return buf;
  }

  function build() {
    master = ctx.createGain();
    master.gain.value = muted ? 0 : volume;
    comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14;
    comp.ratio.value = 7;
    comp.attack.value = 0.004;
    comp.release.value = 0.18;
    master.connect(comp);
    comp.connect(ctx.destination);

    sfx = ctx.createGain();
    sfx.gain.value = 0.9;
    sfx.connect(master);

    noise = buildNoise();

    // Engine: a saw plus a sub, through a lowpass that opens with the load.
    engineGain = ctx.createGain();
    engineGain.gain.value = 0;
    engineFilter = ctx.createBiquadFilter();
    engineFilter.type = 'lowpass';
    engineFilter.frequency.value = 320;
    engineFilter.Q.value = 3.2;
    engineFilter.connect(engineGain);
    engineGain.connect(master);
    engineOsc = ctx.createOscillator();
    engineOsc.type = 'sawtooth';
    engineOsc.frequency.value = 58;
    engineOsc.connect(engineFilter);
    engineOsc.start();
    engineSub = ctx.createOscillator();
    engineSub.type = 'sine';
    engineSub.frequency.value = 29;
    engineSub.connect(engineFilter);
    engineSub.start();

    // Creak: bandpassed noise whose centre frequency wanders.
    creakGain = ctx.createGain();
    creakGain.gain.value = 0;
    creakFilter = ctx.createBiquadFilter();
    creakFilter.type = 'bandpass';
    creakFilter.frequency.value = 700;
    creakFilter.Q.value = 11;
    creakFilter.connect(creakGain);
    creakGain.connect(master);
    creakSrc = ctx.createBufferSource();
    creakSrc.buffer = noise;
    creakSrc.loop = true;
    creakSrc.connect(creakFilter);
    creakSrc.start();

    ready = true;
  }

  function resume() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      ctx = new AC();
      build();
    }
    if (ctx.state === 'suspended') ctx.resume();
  }

  function now() { return ctx ? ctx.currentTime : 0; }

  /** One short tone. `wave` picks the timbre, `bend` slides the pitch. */
  function blip(freq, dur, gain, wave, bend) {
    if (!ready) return;
    const t = now();
    const o = ctx.createOscillator();
    o.type = wave || 'triangle';
    o.frequency.setValueAtTime(freq, t);
    if (bend) o.frequency.exponentialRampToValueAtTime(Math.max(30, freq * bend), t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g);
    g.connect(sfx);
    o.start(t);
    o.stop(t + dur + 0.02);
    o.onended = () => { g.disconnect(); };
  }

  /** One filtered noise burst: impacts, cracks, dust. */
  function burst(freq, dur, gain, type, q) {
    if (!ready) return;
    const t = now();
    const s = ctx.createBufferSource();
    s.buffer = noise;
    s.loop = true;
    const f = ctx.createBiquadFilter();
    f.type = type || 'bandpass';
    f.frequency.setValueAtTime(freq, t);
    f.frequency.exponentialRampToValueAtTime(Math.max(60, freq * 0.35), t + dur);
    f.Q.value = q === undefined ? 2.2 : q;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.006);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    s.connect(f);
    f.connect(g);
    g.connect(sfx);
    s.start(t, Math.random() * 1.5);
    s.stop(t + dur + 0.02);
    s.onended = () => { g.disconnect(); f.disconnect(); };
  }

  function chord(freqs, dur, gain, wave) {
    for (let i = 0; i < freqs.length; i++) {
      window.setTimeout(() => blip(freqs[i], dur, gain, wave || 'triangle'), i * 70);
    }
  }

  const api = {
    resume,
    get muted() { return muted; },
    setVolume(v) {
      volume = Math.max(0, Math.min(1, v));
      if (master) master.gain.setTargetAtTime(muted ? 0 : volume, now(), 0.05);
    },
    toggleMute() {
      muted = !muted;
      if (master) master.gain.setTargetAtTime(muted ? 0 : volume, now(), 0.03);
      return muted;
    },
    click() { blip(560, 0.06, 0.10, 'square'); },
    place(type) {
      const f = { wood: 300, steel: 470, cable: 660, road: 220 }[type] || 380;
      blip(f, 0.11, 0.16, type === 'cable' ? 'sine' : 'triangle', 1.22);
      if (type === 'road') burst(900, 0.09, 0.08, 'bandpass', 1.4);
    },
    remove() { blip(340, 0.1, 0.13, 'triangle', 0.55); },
    deny() { blip(150, 0.16, 0.14, 'square', 0.78); },
    undo() { blip(430, 0.09, 0.11, 'sine', 0.72); },
    testStart() { chord([262, 392, 523], 0.28, 0.13, 'triangle'); },
    crack(intensity) {
      const i = Math.max(0.25, Math.min(1, intensity || 0.6));
      burst(1500 + Math.random() * 900, 0.14 + i * 0.16, 0.16 + i * 0.18, 'bandpass', 1.1);
      blip(120 + Math.random() * 60, 0.18, 0.09 * i, 'square', 0.45);
    },
    collapse() {
      burst(220, 1.5, 0.34, 'lowpass', 0.9);
      burst(80, 2.1, 0.28, 'lowpass', 0.7);
    },
    win() { chord([392, 523, 659, 784], 0.38, 0.15, 'triangle'); },
    lose() { chord([330, 262, 196], 0.4, 0.14, 'sine'); },
    /** Convoy drone. `load` 0..1 raises pitch and opens the filter. */
    engine(on, load) {
      if (!ready) return;
      const t = now();
      const l = Math.max(0, Math.min(1, load || 0));
      engineGain.gain.setTargetAtTime(on ? 0.07 + l * 0.05 : 0, t, 0.14);
      engineOsc.frequency.setTargetAtTime(52 + l * 26, t, 0.2);
      engineSub.frequency.setTargetAtTime(26 + l * 13, t, 0.2);
      engineFilter.frequency.setTargetAtTime(220 + l * 620, t, 0.2);
    },
    /** Stress voice. `ratio` is the worst member in the structure. */
    creak(ratio) {
      if (!ready) return;
      const t = now();
      const r = Math.max(0, Math.min(1, ratio || 0));
      const audible = r > 0.45 ? (r - 0.45) / 0.55 : 0;
      creakGain.gain.setTargetAtTime(audible * 0.09, t, 0.12);
      creakFilter.frequency.setTargetAtTime(420 + audible * 1400 + Math.sin(t * 3.1) * 90, t, 0.1);
      creakFilter.Q.setTargetAtTime(8 + audible * 14, t, 0.2);
    },
    dispose() {
      if (!ctx) return;
      try {
        if (engineOsc) engineOsc.stop();
        if (engineSub) engineSub.stop();
        if (creakSrc) creakSrc.stop();
        ctx.close();
      } catch (e) { /* context already gone */ }
      ctx = null;
      ready = false;
    },
  };
  return api;
}
