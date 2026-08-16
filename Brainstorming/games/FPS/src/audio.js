/**
 * Every sound in the game is synthesised at runtime with the Web Audio API,
 * so the build ships with zero audio files.
 */
export class AudioEngine {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.muted = false;
    this.noiseBuffer = null;
  }

  /** Must be called from a user gesture (the click that grabs the pointer). */
  init() {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') this.ctx.resume();
      return;
    }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    this.ctx = new AC();
    this.master = this.ctx.createGain();
    this.master.gain.value = 0.55;
    this.master.connect(this.ctx.destination);

    // One second of white noise, reused by every noise-based sound.
    const len = this.ctx.sampleRate;
    const buf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
    this.noiseBuffer = buf;
  }

  setMuted(m) {
    this.muted = m;
    if (this.master) this.master.gain.value = m ? 0 : 0.55;
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

  /** Rifle crack: sharp transient, body thump, and a tail of street reverb. */
  shot() {
    if (!this.ready) return;
    this._noise(0.09, 0.55, 'bandpass', 2600, 700, 0.7);
    this._noise(0.32, 0.20, 'lowpass', 900, 120, 1);
    this._tone('square', 180, 42, 0.10, 0.22);
    // slap-back off the surrounding buildings
    setTimeout(() => {
      if (this.ready) this._noise(0.28, 0.07, 'bandpass', 1200, 300, 0.5);
    }, 90);
  }

  dryFire() {
    if (!this.ready) return;
    this._noise(0.04, 0.16, 'highpass', 3000, 1800, 2);
  }

  reloadStart() {
    if (!this.ready) return;
    this._noise(0.07, 0.20, 'bandpass', 1500, 600, 3);
    this._tone('square', 320, 160, 0.05, 0.10, 0.06);
  }

  reloadEnd() {
    if (!this.ready) return;
    this._noise(0.06, 0.22, 'bandpass', 1100, 500, 4);
    this._tone('square', 520, 240, 0.05, 0.12, 0.05);
    this._tone('square', 700, 380, 0.04, 0.10, 0.13);
  }

  impact(hard = true) {
    if (!this.ready) return;
    this._noise(hard ? 0.10 : 0.16, 0.22, hard ? 'highpass' : 'lowpass', hard ? 2400 : 700, hard ? 900 : 160, 1);
  }

  flesh() {
    if (!this.ready) return;
    this._noise(0.13, 0.30, 'lowpass', 1200, 180, 1);
    this._tone('sine', 150, 60, 0.10, 0.16);
  }

  headshot() {
    if (!this.ready) return;
    this._noise(0.18, 0.34, 'lowpass', 2200, 200, 1.4);
    this._tone('triangle', 420, 90, 0.14, 0.18);
  }

  footstep(running) {
    if (!this.ready) return;
    this._noise(running ? 0.10 : 0.13, running ? 0.13 : 0.08, 'lowpass', 900, 180, 1);
  }

  jump() {
    if (!this.ready) return;
    this._tone('sine', 260, 140, 0.10, 0.07);
  }

  land(hard) {
    if (!this.ready) return;
    this._noise(0.15, hard ? 0.22 : 0.11, 'lowpass', 500, 90, 1);
  }

  growl() {
    if (!this.ready) return;
    const base = 70 + Math.random() * 50;
    this._tone('sawtooth', base, base * 0.55, 0.55, 0.10);
    this._noise(0.5, 0.07, 'bandpass', 500, 220, 1.5);
  }

  enemyDeath() {
    if (!this.ready) return;
    this._tone('sawtooth', 190, 40, 0.7, 0.14);
    this._noise(0.5, 0.12, 'lowpass', 800, 100, 1);
  }

  playerHurt() {
    if (!this.ready) return;
    this._tone('sawtooth', 120, 55, 0.30, 0.20);
    this._noise(0.22, 0.16, 'lowpass', 600, 120, 1);
  }

  enemyShot() {
    if (!this.ready) return;
    this._noise(0.07, 0.22, 'bandpass', 1800, 600, 0.8);
    this._tone('square', 140, 50, 0.08, 0.10);
  }

  pickup() {
    if (!this.ready) return;
    this._tone('sine', 620, 900, 0.10, 0.14);
    this._tone('sine', 900, 1250, 0.10, 0.10, 0.08);
  }

  waveStart() {
    if (!this.ready) return;
    this._tone('sawtooth', 110, 108, 1.2, 0.10);
    this._tone('sawtooth', 165, 162, 1.2, 0.07, 0.1);
    this._noise(1.4, 0.05, 'lowpass', 400, 120, 1);
  }

  gameOver() {
    if (!this.ready) return;
    this._tone('sawtooth', 200, 40, 1.8, 0.16);
    this._tone('sine', 100, 30, 2.2, 0.12, 0.1);
  }
}
