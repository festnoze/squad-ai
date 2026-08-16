/**
 * Audio.
 *
 * Everything is synthesised with WebAudio - there are no sound files, for the same reason
 * there are no texture files. The engine is an additive stack of sawtooth oscillators
 * whose frequencies track RPM, so it revs and shifts with the actual drivetrain state
 * rather than crossfading between recorded loops. Gunshots, impacts and tyre squeal are
 * shaped noise bursts.
 *
 * Browsers block audio until a user gesture, so the context starts suspended and is
 * resumed on the first click or key press.
 */

/** Fill a buffer with white noise - the basis for gunfire, skids and impacts. */
function makeNoiseBuffer(ctx, seconds = 1) {
  const length = Math.floor(ctx.sampleRate * seconds);
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
  return buffer;
}

export class AudioEngine {
  constructor() {
    this.enabled = false;
    this.ctx = null;
    this.master = null;
    this.volume = 0.65;
    this._engine = null;
    this._skid = null;
  }

  /** Create the context. Safe to call before any user gesture. */
  init() {
    if (this.ctx) return this;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return this;
    this.ctx = new Ctx();
    this.master = this.ctx.createGain();
    this.master.gain.value = this.volume;
    this.master.connect(this.ctx.destination);
    this.noise = makeNoiseBuffer(this.ctx, 1.2);
    this.enabled = true;
    return this;
  }

  /** Resume after a user gesture. Browsers require this before anything is audible. */
  resume() {
    if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume();
  }

  setVolume(v) {
    this.volume = Math.max(0, Math.min(1, v));
    if (this.master) this.master.gain.value = this.volume;
  }

  get now() { return this.ctx ? this.ctx.currentTime : 0; }

  /* -------------------------------------------------------------------- engine */

  /**
   * Start the engine loop. Three detuned sawtooths an octave apart give the harmonic
   * stack a real engine has; a lowpass whose cutoff tracks RPM opens the sound up as it
   * revs instead of just raising the pitch.
   */
  startEngine() {
    if (!this.enabled || this._engine) return;
    const ctx = this.ctx;
    const gain = ctx.createGain();
    gain.gain.value = 0;
    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 600;
    filter.Q.value = 1.4;
    filter.connect(gain);
    gain.connect(this.master);

    const oscillators = [];
    for (const [ratio, level, detune] of [[1, 0.5, 0], [2, 0.28, 8], [0.5, 0.34, -6], [3, 0.12, 14]]) {
      const osc = ctx.createOscillator();
      osc.type = ratio === 0.5 ? 'square' : 'sawtooth';
      osc.frequency.value = 60 * ratio;
      osc.detune.value = detune;
      const g = ctx.createGain();
      g.gain.value = level;
      osc.connect(g);
      g.connect(filter);
      osc.start();
      oscillators.push({ osc, ratio });
    }

    // A little noise mixed in reads as induction and exhaust roar.
    const noiseSource = ctx.createBufferSource();
    noiseSource.buffer = this.noise;
    noiseSource.loop = true;
    const noiseGain = ctx.createGain();
    noiseGain.gain.value = 0.05;
    const noiseFilter = ctx.createBiquadFilter();
    noiseFilter.type = 'bandpass';
    noiseFilter.frequency.value = 320;
    noiseSource.connect(noiseFilter);
    noiseFilter.connect(noiseGain);
    noiseGain.connect(gain);
    noiseSource.start();

    this._engine = { gain, filter, oscillators, noiseSource, noiseGain, noiseFilter };
  }

  stopEngine() {
    if (!this._engine) return;
    const { gain, oscillators, noiseSource } = this._engine;
    gain.gain.setTargetAtTime(0, this.now, 0.05);
    const stopAt = this.now + 0.2;
    for (const { osc } of oscillators) osc.stop(stopAt);
    noiseSource.stop(stopAt);
    this._engine = null;
  }

  /**
   * @param {number} rpm
   * @param {number} load 0-1 throttle
   * @param {number} speed m/s, drives the noise layer
   */
  updateEngine(rpm, load = 0, speed = 0) {
    if (!this._engine) return;
    const { gain, filter, oscillators, noiseGain, noiseFilter } = this._engine;
    const base = 26 + (rpm / 60) * 0.92;
    const t = this.now;
    for (const { osc, ratio } of oscillators) {
      osc.frequency.setTargetAtTime(base * ratio, t, 0.04);
    }
    filter.frequency.setTargetAtTime(420 + rpm * 0.34 + load * 900, t, 0.06);
    gain.gain.setTargetAtTime(0.055 + load * 0.075, t, 0.08);
    noiseGain.gain.setTargetAtTime(0.02 + Math.min(0.06, speed * 0.0035), t, 0.1);
    noiseFilter.frequency.setTargetAtTime(260 + speed * 12, t, 0.1);
  }

  /* --------------------------------------------------------------- one-shots */

  /** Shaped noise burst. The workhorse for impacts, shots and splashes. */
  _burst({
    duration = 0.12, level = 0.4, type = 'lowpass', frequency = 900, q = 1,
    sweepTo = null, playbackRate = 1,
  } = {}) {
    if (!this.enabled) return;
    const ctx = this.ctx;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    src.playbackRate.value = playbackRate;
    const filter = ctx.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = frequency;
    filter.Q.value = q;
    const gain = ctx.createGain();
    const t = this.now;
    gain.gain.setValueAtTime(level, t);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + duration);
    if (sweepTo !== null) filter.frequency.exponentialRampToValueAtTime(sweepTo, t + duration);
    src.connect(filter);
    filter.connect(gain);
    gain.connect(this.master);
    src.start(t);
    src.stop(t + duration + 0.02);
  }

  /** Short pitched tone, for horns and UI. */
  _tone({ frequency = 440, duration = 0.2, level = 0.2, type = 'square', glideTo = null } = {}) {
    if (!this.enabled) return;
    const ctx = this.ctx;
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.value = frequency;
    const gain = ctx.createGain();
    const t = this.now;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(level, t + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + duration);
    if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, t + duration);
    osc.connect(gain);
    gain.connect(this.master);
    osc.start(t);
    osc.stop(t + duration + 0.02);
  }

  gunshot(kind = 'pistol') {
    const profile = {
      pistol: { duration: 0.13, level: 0.5, frequency: 2600, sweepTo: 260 },
      smg: { duration: 0.08, level: 0.36, frequency: 3000, sweepTo: 400 },
      shotgun: { duration: 0.3, level: 0.62, frequency: 1500, sweepTo: 120, playbackRate: 0.7 },
      rifle: { duration: 0.16, level: 0.52, frequency: 3400, sweepTo: 300 },
    }[kind] ?? { duration: 0.12, level: 0.4, frequency: 2200, sweepTo: 300 };
    this._burst({ type: 'lowpass', q: 0.9, ...profile });
    // A brief low thump underneath gives the shot weight.
    this._tone({ frequency: 90, glideTo: 45, duration: 0.1, level: 0.22, type: 'sine' });
  }

  impact(strength = 1) {
    this._burst({
      duration: 0.1 + strength * 0.16,
      level: Math.min(0.65, 0.16 + strength * 0.4),
      type: 'lowpass',
      frequency: 700 + strength * 500,
      sweepTo: 90,
      playbackRate: 0.85,
    });
  }

  splash() {
    this._burst({ duration: 0.35, level: 0.3, type: 'bandpass', frequency: 1400, sweepTo: 500, q: 0.7 });
  }

  horn() {
    this._tone({ frequency: 392, duration: 0.42, level: 0.16, type: 'sawtooth' });
    this._tone({ frequency: 494, duration: 0.42, level: 0.13, type: 'sawtooth' });
  }

  pickup() {
    this._tone({ frequency: 660, glideTo: 1320, duration: 0.16, level: 0.16, type: 'triangle' });
  }

  siren(on) {
    if (!this.enabled) return;
    if (on && !this._siren) {
      const ctx = this.ctx;
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = 620;
      const lfo = ctx.createOscillator();
      lfo.type = 'triangle';
      lfo.frequency.value = 0.9;
      const lfoGain = ctx.createGain();
      lfoGain.gain.value = 220;
      lfo.connect(lfoGain);
      lfoGain.connect(osc.frequency);
      const gain = ctx.createGain();
      gain.gain.value = 0.0;
      gain.gain.setTargetAtTime(0.05, this.now, 0.3);
      osc.connect(gain);
      gain.connect(this.master);
      osc.start();
      lfo.start();
      this._siren = { osc, lfo, gain };
    } else if (!on && this._siren) {
      const { osc, lfo, gain } = this._siren;
      gain.gain.setTargetAtTime(0, this.now, 0.2);
      osc.stop(this.now + 0.6);
      lfo.stop(this.now + 0.6);
      this._siren = null;
    }
  }

  /* ------------------------------------------------------------------ ambience */

  /**
   * Three continuous noise beds - city hum, wind and surf - each shaped by its own
   * filter. They run for the whole session and are mixed by context rather than started
   * and stopped, because a bed that fades in from silence announces itself; one that is
   * always there and merely changes level is heard as the world rather than as a sound.
   */
  startAmbience() {
    if (!this.enabled || this._ambience) return;
    const ctx = this.ctx;

    const bed = (type, frequency, q, rate) => {
      const src = ctx.createBufferSource();
      src.buffer = this.noise;
      src.loop = true;
      src.playbackRate.value = rate;
      const filter = ctx.createBiquadFilter();
      filter.type = type;
      filter.frequency.value = frequency;
      filter.Q.value = q;
      const gain = ctx.createGain();
      gain.gain.value = 0;
      src.connect(filter);
      filter.connect(gain);
      gain.connect(this.master);
      src.start();
      return { src, filter, gain };
    };

    // City: low rumble, the sum of distant traffic and plant.
    const city = bed('lowpass', 240, 0.8, 0.35);
    // Wind: broad and airy, rises with speed and altitude.
    const wind = bed('bandpass', 900, 0.5, 0.8);
    // Surf: mid band with a slow swell applied below.
    const surf = bed('bandpass', 620, 0.7, 0.45);

    // A slow LFO on the surf gain gives waves their breathing rhythm.
    const lfo = ctx.createOscillator();
    lfo.type = 'sine';
    lfo.frequency.value = 0.13;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = 0.5;
    lfo.connect(lfoGain);
    lfoGain.connect(surf.filter.frequency);
    lfo.start();

    this._ambience = { city, wind, surf, lfo };
  }

  /**
   * @param {object} ctx
   * @param {number} ctx.speed player speed, m/s
   * @param {number} ctx.height metres above ground
   * @param {number} ctx.water 0-1 proximity to open water
   * @param {number} ctx.density 0-1 how built-up the surroundings are
   * @param {number} ctx.night 0-1
   */
  updateAmbience({ speed = 0, height = 0, water = 0, density = 0, night = 0 } = {}) {
    if (!this._ambience) return;
    const t = this.now;
    const { city, wind, surf } = this._ambience;

    // The city quietens at night but never goes silent.
    city.gain.gain.setTargetAtTime(0.02 + density * 0.05 * (1 - night * 0.45), t, 0.8);
    city.filter.frequency.setTargetAtTime(200 + density * 160, t, 1.2);

    // Wind is speed and exposure: fast, high or out over the water.
    const exposure = Math.min(1, height / 60) * 0.6 + water * 0.4;
    wind.gain.gain.setTargetAtTime(
      0.008 + Math.min(0.07, speed * 0.0032) + exposure * 0.03, t, 0.5,
    );
    wind.filter.frequency.setTargetAtTime(700 + speed * 26, t, 0.6);

    surf.gain.gain.setTargetAtTime(water * 0.055, t, 1.0);
  }

  stopAmbience() {
    if (!this._ambience) return;
    const { city, wind, surf, lfo } = this._ambience;
    for (const b of [city, wind, surf]) {
      b.gain.gain.setTargetAtTime(0, this.now, 0.2);
      b.src.stop(this.now + 0.8);
    }
    lfo.stop(this.now + 0.8);
    this._ambience = null;
  }

  /** Continuous tyre squeal, level driven by slip. */
  updateSkid(amount) {
    if (!this.enabled) return;
    if (amount > 0.05 && !this._skid) {
      const ctx = this.ctx;
      const src = ctx.createBufferSource();
      src.buffer = this.noise;
      src.loop = true;
      const filter = ctx.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.value = 1800;
      filter.Q.value = 6;
      const gain = ctx.createGain();
      gain.gain.value = 0;
      src.connect(filter);
      filter.connect(gain);
      gain.connect(this.master);
      src.start();
      this._skid = { src, gain, filter };
    }
    if (this._skid) {
      this._skid.gain.gain.setTargetAtTime(Math.min(0.16, amount * 0.2), this.now, 0.05);
      this._skid.filter.frequency.setTargetAtTime(1500 + amount * 900, this.now, 0.1);
      if (amount <= 0.05) {
        const { src, gain } = this._skid;
        gain.gain.setTargetAtTime(0, this.now, 0.08);
        src.stop(this.now + 0.3);
        this._skid = null;
      }
    }
  }

  dispose() {
    this.stopEngine();
    this.siren(false);
    this.ctx?.close();
    this.ctx = null;
    this.enabled = false;
  }
}
