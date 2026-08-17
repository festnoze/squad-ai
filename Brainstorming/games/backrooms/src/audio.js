// Web Audio only, zero sound files. AudioContext is created lazily and
// resumed on the first user gesture (browsers refuse autoplay otherwise).
const SURFACE_TONE = {
  carpet: { type: 'lowpass', freq: 900, gain: 0.16, decay: 0.09 },
  tile: { type: 'highpass', freq: 1200, gain: 0.14, decay: 0.05 },
  metal: { type: 'bandpass', freq: 2200, gain: 0.22, decay: 0.16 },
  concrete: { type: 'lowpass', freq: 1500, gain: 0.18, decay: 0.08 },
};

function makeNoiseBuffer(ctx, seconds = 2) {
  const buf = ctx.createBuffer(1, ctx.sampleRate * seconds, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  return buf;
}

export function createAudio() {
  let ctx = null;
  let master = null;
  let muted = false;
  let noiseBuffer = null;
  let ambienceNodes = null;
  let interferenceGain = null;
  let heartbeatTimer = 0.9;
  let heartbeatBpmTarget = 62;

  function ensure() {
    if (ctx) return;
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    master = ctx.createGain();
    master.gain.value = 0.75;
    const comp = ctx.createDynamicsCompressor();
    master.connect(comp).connect(ctx.destination);
    noiseBuffer = makeNoiseBuffer(ctx, 3);
  }

  function resume() {
    ensure();
    if (ctx.state === 'suspended') ctx.resume();
  }

  function noiseSource(loop = false) {
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer;
    src.loop = loop;
    return src;
  }

  function setMasterVolume(v) {
    ensure();
    master.gain.setTargetAtTime(muted ? 0 : v, ctx.currentTime, 0.05);
  }

  function toggleMute() {
    ensure();
    muted = !muted;
    master.gain.setTargetAtTime(muted ? 0 : 0.75, ctx.currentTime, 0.05);
    return muted;
  }

  /** Fluorescent hum + a faint wind bed, tinted per theme. Never cuts, only crossfades. */
  function startAmbience(themeKey) {
    ensure();
    stopAmbience();
    const now = ctx.currentTime;
    const hum = ctx.createOscillator();
    hum.type = 'sine';
    hum.frequency.value = themeKey === 'electrical' ? 120 : themeKey === 'pipes' ? 68 : 100;
    const hum2 = ctx.createOscillator();
    hum2.type = 'sine';
    hum2.frequency.value = hum.frequency.value * 2.01;
    const humGain = ctx.createGain();
    humGain.gain.value = 0;
    humGain.gain.setTargetAtTime(0.05, now, 1.2);
    hum.connect(humGain);
    hum2.connect(humGain);

    const wind = noiseSource(true);
    const windFilter = ctx.createBiquadFilter();
    windFilter.type = 'lowpass';
    windFilter.frequency.value = themeKey === 'poolrooms' ? 2600 : 500;
    const windGain = ctx.createGain();
    windGain.gain.value = 0;
    windGain.gain.setTargetAtTime(themeKey === 'dark' ? 0.05 : 0.03, now, 1.4);
    wind.connect(windFilter).connect(windGain);

    // radio interference bed, silent until update() raises it with proximity
    const inter = noiseSource(true);
    const interFilter = ctx.createBiquadFilter();
    interFilter.type = 'bandpass';
    interFilter.frequency.value = 1800;
    interFilter.Q.value = 4;
    interferenceGain = ctx.createGain();
    interferenceGain.gain.value = 0;
    inter.connect(interFilter).connect(interferenceGain);

    humGain.connect(master);
    windGain.connect(master);
    interferenceGain.connect(master);
    hum.start(); hum2.start(); wind.start(); inter.start();

    ambienceNodes = { hum, hum2, wind, inter, humGain, windGain };
  }

  function stopAmbience() {
    if (!ambienceNodes) return;
    const { hum, hum2, wind, inter } = ambienceNodes;
    try { hum.stop(); hum2.stop(); wind.stop(); inter.stop(); } catch (e) { /* already stopped */ }
    ambienceNodes = null;
    interferenceGain = null;
  }

  function footstep(surface, sprinting) {
    ensure();
    const cfg = SURFACE_TONE[surface] ?? SURFACE_TONE.carpet;
    const now = ctx.currentTime;
    const src = noiseSource(false);
    const filter = ctx.createBiquadFilter();
    filter.type = cfg.type;
    filter.frequency.value = cfg.freq;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime((sprinting ? 1.3 : 1) * cfg.gain, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + cfg.decay);
    src.connect(filter).connect(gain).connect(master);
    src.start(now);
    src.stop(now + cfg.decay + 0.02);
  }

  function doorOpen() {
    ensure();
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(140, now);
    osc.frequency.exponentialRampToValueAtTime(80, now + 0.5);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.001, now);
    gain.gain.exponentialRampToValueAtTime(0.12, now + 0.08);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.55);
    osc.connect(gain).connect(master);
    osc.start(now);
    osc.stop(now + 0.6);
  }

  function pickup() {
    ensure();
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(520, now);
    osc.frequency.exponentialRampToValueAtTime(940, now + 0.18);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.001, now);
    gain.gain.exponentialRampToValueAtTime(0.2, now + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
    osc.connect(gain).connect(master);
    osc.start(now);
    osc.stop(now + 0.32);
  }

  function contact() {
    ensure();
    const now = ctx.currentTime;
    const src = noiseSource(false);
    const filter = ctx.createBiquadFilter();
    filter.type = 'bandpass';
    filter.frequency.value = 300;
    filter.Q.value = 0.6;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.5, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.7);
    src.connect(filter).connect(gain).connect(master);
    src.start(now);
    src.stop(now + 0.72);
  }

  function flashlightClick() {
    ensure();
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    osc.type = 'square';
    osc.frequency.value = 1200;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.06, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
    osc.connect(gain).connect(master);
    osc.start(now);
    osc.stop(now + 0.05);
  }

  function exitChime() {
    ensure();
    const now = ctx.currentTime;
    [0, 0.14, 0.28].forEach((t, i) => {
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = 440 * Math.pow(1.5, i);
      const gain = ctx.createGain();
      gain.gain.setValueAtTime(0.001, now + t);
      gain.gain.exponentialRampToValueAtTime(0.18, now + t + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, now + t + 0.35);
      osc.connect(gain).connect(master);
      osc.start(now + t);
      osc.stop(now + t + 0.4);
    });
  }

  function heartThump(strength) {
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(58, now);
    osc.frequency.exponentialRampToValueAtTime(32, now + 0.14);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.001, now);
    gain.gain.exponentialRampToValueAtTime(0.28 * strength, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
    osc.connect(gain).connect(master);
    osc.start(now);
    osc.stop(now + 0.24);
  }

  /** Diegetic danger feedback: driven by real proximity, not by whether the entity has detected the player. */
  function update(dt, proximity01, detected) {
    if (!ctx) return;
    if (interferenceGain) {
      const target = Math.max(0, proximity01 - 0.15) * 0.22 * (detected ? 1.6 : 1);
      interferenceGain.gain.setTargetAtTime(target, ctx.currentTime, 0.25);
    }
    heartbeatBpmTarget = 58 + proximity01 * 90;
    if (proximity01 > 0.03) {
      heartbeatTimer -= dt;
      if (heartbeatTimer <= 0) {
        heartThump(0.4 + proximity01 * 0.9);
        heartbeatTimer = 60 / heartbeatBpmTarget;
      }
    } else {
      heartbeatTimer = Math.max(heartbeatTimer, 0.5);
    }
  }

  return {
    resume, setMasterVolume, toggleMute, startAmbience, stopAmbience,
    footstep, doorOpen, pickup, contact, flashlightClick, exitChime, update,
    dispose() { stopAmbience(); if (ctx) ctx.close(); },
  };
}
