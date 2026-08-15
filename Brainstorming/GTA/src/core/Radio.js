/**
 * Car radio.
 *
 * The stations are generated, not recorded - same principle as the textures and the city.
 * Each station is a scale, a tempo, a chord progression and a set of instrument voices;
 * a scheduler walks the progression and queues WebAudio notes a beat ahead of time, which
 * is what keeps the timing solid regardless of frame rate.
 *
 * Scheduling ahead matters: driving note triggers off `requestAnimationFrame` puts every
 * note wherever the frame happened to land, and the result audibly stumbles. The audio
 * clock is sample-accurate; the render loop is not.
 */

/** Semitone offsets from the root for each scale. */
const SCALES = {
  minor: [0, 2, 3, 5, 7, 8, 10],
  dorian: [0, 2, 3, 5, 7, 9, 10],
  major: [0, 2, 4, 5, 7, 9, 11],
  phrygian: [0, 1, 3, 5, 7, 8, 10],
};

/** Chord degrees, as scale-index roots. */
const PROGRESSIONS = [
  [0, 5, 3, 4],
  [0, 3, 4, 4],
  [0, 6, 5, 4],
  [0, 4, 5, 3],
  [0, 2, 3, 5],
];

export const STATIONS = [
  {
    name: 'LIBERTY FM', tag: 'synthwave',
    root: 45, scale: 'minor', bpm: 104, wave: 'sawtooth',
    bass: 'square', pad: true, hats: true, swing: 0,
  },
  {
    name: 'HORIZON GOLD', tag: 'lounge',
    root: 48, scale: 'major', bpm: 88, wave: 'triangle',
    bass: 'sine', pad: true, hats: false, swing: 0.18,
  },
  {
    name: 'DOCKSIDE', tag: 'dub',
    root: 41, scale: 'dorian', bpm: 74, wave: 'square',
    bass: 'sine', pad: false, hats: true, swing: 0.12,
  },
  {
    name: 'NIGHT SHIFT', tag: 'darkwave',
    root: 40, scale: 'phrygian', bpm: 120, wave: 'sawtooth',
    bass: 'sawtooth', pad: true, hats: true, swing: 0,
  },
  { name: 'RADIO OFF', tag: 'silence', silent: true },
];

const midiToHz = (n) => 440 * (2 ** ((n - 69) / 12));

export class Radio {
  /** @param {import('./Audio.js').AudioEngine} audio */
  constructor(audio) {
    this.audio = audio;
    this.index = STATIONS.length - 1;   // start on RADIO OFF
    this.volume = 0.5;
    this.playing = false;

    this._nextNoteTime = 0;
    this._step = 0;
    this._bar = 0;
    this._progression = PROGRESSIONS[0];
    this._gain = null;
  }

  get station() { return STATIONS[this.index]; }
  get label() { return this.station.name; }

  /** Cycle to the next station. Called from the horn/radio key while driving. */
  next() {
    this.index = (this.index + 1) % STATIONS.length;
    this._step = 0;
    this._bar = 0;
    this._progression = PROGRESSIONS[Math.floor(Math.random() * PROGRESSIONS.length)];
    this._nextNoteTime = this.audio.now + 0.05;
    if (this.station.silent) this.stop();
    return this.station;
  }

  start() {
    if (!this.audio.enabled || this.playing || this.station.silent) return;
    const ctx = this.audio.ctx;
    this._gain = ctx.createGain();
    this._gain.gain.value = this.volume * 0.35;
    // A gentle lowpass keeps the square and saw voices from being fatiguing.
    this._filter = ctx.createBiquadFilter();
    this._filter.type = 'lowpass';
    this._filter.frequency.value = 2600;
    this._filter.Q.value = 0.7;
    this._gain.connect(this._filter);
    this._filter.connect(this.audio.master);
    this._nextNoteTime = this.audio.now + 0.08;
    this.playing = true;
  }

  stop() {
    if (!this.playing) return;
    this._gain?.disconnect();
    this._filter?.disconnect();
    this._gain = null;
    this._filter = null;
    this.playing = false;
  }

  setVolume(v) {
    this.volume = Math.max(0, Math.min(1, v));
    if (this._gain) this._gain.gain.value = this.volume * 0.35;
  }

  /** One synth note. */
  _note(freq, start, duration, type, level, detune = 0) {
    const ctx = this.audio.ctx;
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.value = freq;
    osc.detune.value = detune;
    const env = ctx.createGain();
    // Short attack, exponential decay - a plucked/keys envelope rather than an organ.
    env.gain.setValueAtTime(0.0001, start);
    env.gain.exponentialRampToValueAtTime(level, start + 0.012);
    env.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    osc.connect(env);
    env.connect(this._gain);
    osc.start(start);
    osc.stop(start + duration + 0.02);
  }

  /** Noise-based hi-hat. */
  _hat(start, level) {
    const ctx = this.audio.ctx;
    const src = ctx.createBufferSource();
    src.buffer = this.audio.noise;
    src.playbackRate.value = 1.8;
    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 7000;
    const env = ctx.createGain();
    env.gain.setValueAtTime(level, start);
    env.gain.exponentialRampToValueAtTime(0.0001, start + 0.05);
    src.connect(hp);
    hp.connect(env);
    env.connect(this._gain);
    src.start(start);
    src.stop(start + 0.08);
  }

  _kick(start) {
    const ctx = this.audio.ctx;
    const osc = ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(120, start);
    osc.frequency.exponentialRampToValueAtTime(42, start + 0.11);
    const env = ctx.createGain();
    env.gain.setValueAtTime(0.5, start);
    env.gain.exponentialRampToValueAtTime(0.0001, start + 0.16);
    osc.connect(env);
    env.connect(this._gain);
    osc.start(start);
    osc.stop(start + 0.2);
  }

  /**
   * Queue any notes due in the next lookahead window. Call every frame; it is cheap and
   * does nothing most frames.
   */
  update() {
    if (!this.playing || !this.audio.enabled || !this._gain) return;
    const s = this.station;
    const beat = 60 / s.bpm;
    const stepDuration = beat / 2;          // eighth notes
    const lookahead = 0.15;

    const scale = SCALES[s.scale];
    while (this._nextNoteTime < this.audio.now + lookahead) {
      const t = this._nextNoteTime;
      const step = this._step % 8;
      const chordIndex = this._progression[this._bar % this._progression.length];
      const rootDegree = scale[chordIndex % scale.length] + (chordIndex >= scale.length ? 12 : 0);
      const chordRoot = s.root + rootDegree;

      // Bass on the downbeat and the "and" of three - enough to imply a groove.
      if (step === 0 || step === 5) {
        this._note(midiToHz(chordRoot - 12), t, beat * 0.9, s.bass, 0.28);
      }
      if (step === 0 || step === 4) this._kick(t);
      if (s.hats && step % 2 === 1) this._hat(t, 0.07);

      // Arpeggio over the triad.
      const triad = [0, 2, 4].map((d) => scale[(chordIndex + d) % scale.length]
        + (chordIndex + d >= scale.length ? 12 : 0));
      const note = s.root + triad[step % triad.length] + (step >= 4 ? 12 : 0);
      this._note(midiToHz(note), t, stepDuration * 1.6, s.wave, 0.12, (Math.random() - 0.5) * 8);

      // Sustained pad on the bar line.
      if (s.pad && step === 0) {
        for (const d of triad) {
          this._note(midiToHz(s.root + d), t, beat * 3.4, 'triangle', 0.045);
        }
      }

      // Swing: delay every off-beat slightly.
      const swing = (this._step % 2 === 0) ? 0 : stepDuration * (s.swing ?? 0);
      this._nextNoteTime += stepDuration + swing - (this._step % 2 === 0 ? 0 : 0);
      this._step++;
      if (this._step % 8 === 0) this._bar++;
    }
  }
}
