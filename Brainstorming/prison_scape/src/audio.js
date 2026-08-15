/**
 * Every sound is synthesised at runtime with the Web Audio API: the game ships
 * with zero audio files. Prison flavour - concrete slaps, buzzers, sirens.
 */
export class AudioEngine {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.muted = false;
    this.noiseBuffer = null;
    this._siren = null;
    this._drone = null;
  }

  /** Must be called from a user gesture (the first click). */
  init() {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') this.ctx.resume();
      return;
    }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    this.ctx = new AC();
    this.master = this.ctx.createGain();
    this.master.gain.value = 0.5;
    this.master.connect(this.ctx.destination);

    const len = this.ctx.sampleRate;
    const buf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
    this.noiseBuffer = buf;
  }

  setMuted(m) {
    this.muted = m;
    if (this.master) this.master.gain.value = m ? 0 : 0.5;
  }

  get ready() {
    return !!this.ctx && this.ctx.state === 'running';
  }

  _noise(duration, gainValue, filterType, freqStart, freqEnd, q = 1) {
    const ctx = this.ctx;
    const src = ctx.createBufferSource();
    src.buffer = this.noiseBuffer;
    src.loop = true;
    const filter = ctx.createBiquadFilter();
    filter.type = filterType;
    filter.Q.value = q;
    const now = ctx.currentTime;
    filter.frequency.setValueAtTime(freqStart, now);
    filter.frequency.exponentialRampToValueAtTime(Math.max(40, freqEnd), now + duration);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(gainValue, now);
    gain.gain.exponentialRampToValueAtTime(0.0008, now + duration);
    src.connect(filter).connect(gain).connect(this.master);
    src.start(now);
    src.stop(now + duration + 0.02);
    return { gain, filter };
  }

  _tone(type, freqStart, freqEnd, duration, gainValue, delay = 0) {
    const ctx = this.ctx;
    const osc = ctx.createOscillator();
    osc.type = type;
    const now = ctx.currentTime + delay;
    osc.frequency.setValueAtTime(freqStart, now);
    osc.frequency.exponentialRampToValueAtTime(Math.max(20, freqEnd), now + duration);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(gainValue, now + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    osc.connect(gain).connect(this.master);
    osc.start(now);
    osc.stop(now + duration + 0.02);
    return osc;
  }

  /** Distance-attenuated variant used for anything that happens away from the player. */
  _at(distance, base) {
    return base * Math.max(0.05, 1 - distance / 45);
  }

  // ---------------------------------------------------------------- weapons
  shot(kind = 'pistol', distance = 0) {
    if (!this.ready) return;
    const a = this._at(distance, 1);
    if (kind === 'shotgun') {
      this._noise(0.14, 0.6 * a, 'bandpass', 1800, 400, 0.6);
      this._noise(0.45, 0.24 * a, 'lowpass', 800, 90, 1);
      this._tone('square', 140, 34, 0.16, 0.26 * a);
    } else if (kind === 'rifle') {
      this._noise(0.08, 0.5 * a, 'bandpass', 3000, 900, 0.8);
      this._noise(0.26, 0.16 * a, 'lowpass', 1000, 140, 1);
      this._tone('square', 200, 50, 0.09, 0.2 * a);
    } else {
      this._noise(0.06, 0.42 * a, 'bandpass', 2400, 800, 0.9);
      this._noise(0.20, 0.13 * a, 'lowpass', 900, 150, 1);
      this._tone('square', 230, 60, 0.07, 0.16 * a);
    }
    // concrete corridor slap-back
    setTimeout(() => {
      if (this.ready) this._noise(0.34, 0.07 * a, 'bandpass', 1000, 260, 0.5);
    }, 75);
  }

  dryFire() {
    if (!this.ready) return;
    this._noise(0.04, 0.16, 'highpass', 3200, 1800, 2);
  }

  reloadStart() {
    if (!this.ready) return;
    this._noise(0.07, 0.20, 'bandpass', 1500, 600, 3);
    this._tone('square', 320, 160, 0.05, 0.10, 0.06);
  }

  reloadEnd() {
    if (!this.ready) return;
    this._noise(0.06, 0.22, 'bandpass', 1100, 500, 4);
    this._tone('square', 540, 250, 0.05, 0.12, 0.05);
  }

  impact(hard = true) {
    if (!this.ready) return;
    this._noise(hard ? 0.09 : 0.15, 0.20, hard ? 'highpass' : 'lowpass', hard ? 2600 : 700, hard ? 900 : 160, 1);
  }

  flesh() {
    if (!this.ready) return;
    this._noise(0.12, 0.28, 'lowpass', 1100, 170, 1);
    this._tone('sine', 150, 60, 0.10, 0.14);
  }

  // ------------------------------------------------------------- environment
  /** Sparks + shattering lens when a security camera dies. */
  cameraBreak() {
    if (!this.ready) return;
    this._noise(0.10, 0.34, 'highpass', 5000, 2200, 1);
    this._noise(0.5, 0.12, 'bandpass', 3200, 900, 2);
    for (let i = 0; i < 5; i++) {
      this._tone('square', 2600 + Math.random() * 2400, 900, 0.03, 0.06, 0.02 + i * 0.035);
    }
  }

  /** Heavy security door sliding into its pocket. */
  doorOpen() {
    if (!this.ready) return;
    this._tone('sine', 90, 62, 1.5, 0.14);
    this._noise(1.5, 0.14, 'lowpass', 700, 200, 1);
    this._tone('square', 880, 1320, 0.08, 0.10);
    this._tone('square', 1320, 1320, 0.10, 0.09, 0.11);
  }

  doorLocked() {
    if (!this.ready) return;
    this._tone('square', 180, 178, 0.16, 0.16);
    this._tone('square', 150, 148, 0.20, 0.14, 0.18);
  }

  cellOpen() {
    if (!this.ready) return;
    this._noise(0.7, 0.24, 'bandpass', 2400, 600, 2.5);
    this._tone('sawtooth', 130, 90, 0.8, 0.10);
  }

  pickup() {
    if (!this.ready) return;
    this._tone('sine', 620, 940, 0.10, 0.14);
    this._tone('sine', 940, 1280, 0.10, 0.10, 0.08);
  }

  /** Uniform looted: heavier, cloth-and-velcro. */
  disguise() {
    if (!this.ready) return;
    this._noise(0.35, 0.18, 'bandpass', 1400, 400, 1.5);
    this._tone('sine', 320, 480, 0.22, 0.12, 0.1);
    this._tone('sine', 480, 640, 0.24, 0.10, 0.28);
  }

  footstep(running) {
    if (!this.ready) return;
    this._noise(running ? 0.09 : 0.12, running ? 0.11 : 0.055, 'lowpass', 1100, 200, 1);
  }

  land(hard) {
    if (!this.ready) return;
    this._noise(0.15, hard ? 0.20 : 0.09, 'lowpass', 500, 90, 1);
  }

  playerHurt() {
    if (!this.ready) return;
    this._tone('sawtooth', 120, 55, 0.30, 0.20);
    this._noise(0.22, 0.16, 'lowpass', 600, 120, 1);
  }

  // ----------------------------------------------------------------- guards
  /** A camera or guard has started to notice you. Short rising blip. */
  suspicion() {
    if (!this.ready) return;
    this._tone('sine', 500, 780, 0.14, 0.09);
  }

  guardShout(distance = 0) {
    if (!this.ready) return;
    const a = this._at(distance, 1);
    this._tone('sawtooth', 200, 150, 0.22, 0.14 * a);
    this._tone('sawtooth', 250, 180, 0.18, 0.10 * a, 0.24);
  }

  /** Radio call-in: the sound of losing. */
  radio(distance = 0) {
    if (!this.ready) return;
    const a = this._at(distance, 1);
    this._noise(0.10, 0.10 * a, 'bandpass', 2000, 1600, 6);
    this._tone('square', 1200, 1200, 0.06, 0.07 * a, 0.12);
    this._tone('square', 900, 900, 0.06, 0.07 * a, 0.2);
  }

  /** Fist cutting through the air. */
  punchSwing() {
    if (!this.ready) return;
    this._noise(0.13, 0.10, 'bandpass', 900, 260, 1.2);
  }

  /** Knuckles landing on a stab vest. */
  punchHit() {
    if (!this.ready) return;
    this._noise(0.09, 0.34, 'lowpass', 1400, 200, 1);
    this._tone('sine', 190, 70, 0.11, 0.20);
  }

  /** Silent takedown from behind: dull impact, then a body folding. */
  knockout() {
    if (!this.ready) return;
    this._noise(0.14, 0.30, 'lowpass', 900, 120, 1);
    this._tone('sine', 130, 48, 0.22, 0.18);
    setTimeout(() => {
      if (this.ready) this._noise(0.28, 0.16, 'lowpass', 500, 90, 1);
    }, 180);
  }

  guardDeath() {
    if (!this.ready) return;
    this._tone('sawtooth', 210, 60, 0.6, 0.13);
    this._noise(0.45, 0.12, 'lowpass', 800, 110, 1);
  }

  // ------------------------------------------------------------------ music
  /** Looping alarm siren, started when the prison goes into lockdown. */
  startSiren() {
    if (!this.ready || this._siren) return;
    const ctx = this.ctx;
    const osc = ctx.createOscillator();
    osc.type = 'sawtooth';
    const lfo = ctx.createOscillator();
    lfo.type = 'sine';
    lfo.frequency.value = 0.6;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = 180;
    const gain = ctx.createGain();
    gain.gain.value = 0.0;
    gain.gain.linearRampToValueAtTime(0.09, ctx.currentTime + 0.4);
    osc.frequency.value = 620;
    lfo.connect(lfoGain).connect(osc.frequency);
    osc.connect(gain).connect(this.master);
    osc.start();
    lfo.start();
    this._siren = { osc, lfo, gain };
  }

  stopSiren() {
    if (!this._siren) return;
    const { osc, lfo, gain } = this._siren;
    this._siren = null;
    try {
      gain.gain.linearRampToValueAtTime(0.0001, this.ctx.currentTime + 0.3);
      osc.stop(this.ctx.currentTime + 0.35);
      lfo.stop(this.ctx.currentTime + 0.35);
    } catch (err) { /* already stopped */ }
  }

  /**
   * The backrooms hum: mains buzz at 60Hz with its harmonics, plus the hiss of
   * fluorescent tubes. Runs the whole time the player is off-plan.
   */
  startHum() {
    if (!this.ready || this._hum) return;
    const ctx = this.ctx;
    const gain = ctx.createGain();
    gain.gain.value = 0.0001;
    gain.gain.linearRampToValueAtTime(0.075, ctx.currentTime + 1.2);
    gain.connect(this.master);

    const oscs = [];
    for (const [freq, level, type] of [[60, 1, 'sawtooth'], [120, 0.5, 'sine'], [180, 0.22, 'sine']]) {
      const o = ctx.createOscillator();
      o.type = type;
      o.frequency.value = freq;
      const g = ctx.createGain();
      g.gain.value = level;
      o.connect(g).connect(gain);
      o.start();
      oscs.push(o);
    }
    // tube hiss
    const src = ctx.createBufferSource();
    src.buffer = this.noiseBuffer;
    src.loop = true;
    const hp = ctx.createBiquadFilter();
    hp.type = 'bandpass';
    hp.frequency.value = 4200;
    hp.Q.value = 0.8;
    const hissGain = ctx.createGain();
    hissGain.gain.value = 0.09;
    src.connect(hp).connect(hissGain).connect(gain);
    src.start();

    this._hum = { gain, oscs, src };
  }

  stopHum() {
    if (!this._hum) return;
    const { gain, oscs, src } = this._hum;
    this._hum = null;
    try {
      gain.gain.linearRampToValueAtTime(0.0001, this.ctx.currentTime + 0.6);
      const stopAt = this.ctx.currentTime + 0.7;
      oscs.forEach((o) => o.stop(stopAt));
      src.stop(stopAt);
    } catch (err) { /* already stopped */ }
  }

  /** Plaster and tile giving way as the loose panel comes out. */
  panelPull() {
    if (!this.ready) return;
    this._noise(0.45, 0.34, 'lowpass', 1800, 200, 1);
    this._tone('square', 130, 48, 0.3, 0.16);
    setTimeout(() => {
      if (this.ready) this._noise(0.30, 0.22, 'lowpass', 900, 120, 1);
    }, 260);
  }

  /** Low tension drone under the cutscene and the game. */
  startDrone(freq = 55) {
    if (!this.ready || this._drone) return;
    const ctx = this.ctx;
    const a = ctx.createOscillator();
    a.type = 'sawtooth';
    a.frequency.value = freq;
    const b = ctx.createOscillator();
    b.type = 'sine';
    b.frequency.value = freq * 1.5;
    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 320;
    const gain = ctx.createGain();
    gain.gain.value = 0.0001;
    gain.gain.linearRampToValueAtTime(0.055, ctx.currentTime + 2);
    a.connect(filter);
    b.connect(filter);
    filter.connect(gain).connect(this.master);
    a.start();
    b.start();
    this._drone = { a, b, gain };
  }

  stopDrone() {
    if (!this._drone) return;
    const { a, b, gain } = this._drone;
    this._drone = null;
    try {
      gain.gain.linearRampToValueAtTime(0.0001, this.ctx.currentTime + 1.2);
      a.stop(this.ctx.currentTime + 1.3);
      b.stop(this.ctx.currentTime + 1.3);
    } catch (err) { /* already stopped */ }
  }

  // --------------------------------------------------------------- cutscene
  glassBreak() {
    if (!this.ready) return;
    this._noise(0.5, 0.3, 'highpass', 6000, 2000, 1);
    for (let i = 0; i < 8; i++) {
      this._tone('triangle', 2000 + Math.random() * 3000, 1200, 0.05, 0.05, Math.random() * 0.4);
    }
  }

  /** Museum alarm klaxon during the intro. */
  klaxon(count = 3) {
    if (!this.ready) return;
    for (let i = 0; i < count; i++) {
      this._tone('square', 740, 735, 0.28, 0.11, i * 0.55);
      this._tone('square', 560, 556, 0.28, 0.09, i * 0.55 + 0.3);
    }
  }

  carEngine() {
    if (!this.ready) return;
    this._tone('sawtooth', 60, 130, 1.2, 0.10);
    this._noise(1.4, 0.09, 'lowpass', 420, 200, 1);
  }

  /** Cell door / prison gate slamming shut. */
  slam() {
    if (!this.ready) return;
    this._noise(0.35, 0.4, 'lowpass', 900, 70, 1);
    this._tone('sine', 110, 34, 0.5, 0.24);
    this._tone('square', 70, 30, 0.6, 0.16);
  }

  gavel() {
    if (!this.ready) return;
    this._noise(0.10, 0.28, 'bandpass', 900, 300, 1.5);
    this._tone('sine', 200, 80, 0.14, 0.16);
  }

  victory() {
    if (!this.ready) return;
    const notes = [220, 277, 330, 440, 554];
    notes.forEach((f, i) => this._tone('triangle', f, f, 0.5, 0.12, i * 0.16));
  }

  gameOver() {
    if (!this.ready) return;
    this._tone('sawtooth', 200, 40, 1.8, 0.16);
    this._tone('sine', 100, 30, 2.2, 0.12, 0.1);
  }
}
