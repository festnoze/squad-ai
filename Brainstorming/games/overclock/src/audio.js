/**
 * OVERCLOCK - Web Audio only, no sound file.
 *
 * Every cue is a short envelope on one or two oscillators. The context is
 * created on the first user gesture, which is the only moment a browser lets
 * it start.
 */

const NOTES = {
  ui: { f: 520, f2: 700, d: 0.07, type: 'triangle', g: 0.16 },
  place: { f: 660, f2: 880, d: 0.08, type: 'square', g: 0.1 },
  clear: { f: 420, f2: 240, d: 0.09, type: 'square', g: 0.09 },
  move: { f: 300, f2: 360, d: 0.09, type: 'sine', g: 0.13 },
  turn: { f: 420, f2: 500, d: 0.07, type: 'sine', g: 0.1 },
  jump: { f: 340, f2: 660, d: 0.16, type: 'sine', g: 0.15 },
  act: { f: 780, f2: 1180, d: 0.22, type: 'triangle', g: 0.2 },
  paint: { f: 560, f2: 430, d: 0.13, type: 'sine', g: 0.13 },
  grab: { f: 240, f2: 400, d: 0.11, type: 'square', g: 0.09 },
  drop: { f: 400, f2: 190, d: 0.14, type: 'square', g: 0.11 },
  call: { f: 900, f2: 900, d: 0.05, type: 'sine', g: 0.07 },
  start: { f: 260, f2: 620, d: 0.28, type: 'triangle', g: 0.18 },
};

export function createAudio() {
  let ctx = null;
  let master = null;
  let comp = null;
  let hum = null;
  let humGain = null;
  let volume = 0.6;
  let muted = false;

  function ensure() {
    if (ctx) return ctx;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14;
    comp.ratio.value = 6;
    master = ctx.createGain();
    master.gain.value = muted ? 0 : volume;
    master.connect(comp);
    comp.connect(ctx.destination);

    // Rotor bed: two detuned saws through a low pass, silent until a run starts.
    humGain = ctx.createGain();
    humGain.gain.value = 0;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 420;
    lp.Q.value = 3;
    humGain.connect(master);
    lp.connect(humGain);
    hum = [];
    for (const f of [58, 87.5]) {
      const o = ctx.createOscillator();
      o.type = 'sawtooth';
      o.frequency.value = f;
      o.connect(lp);
      o.start();
      hum.push(o);
    }
    return ctx;
  }

  function envTone(spec, when, detune) {
    const c = ensure();
    if (!c || muted) return;
    const t = when || c.currentTime;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = spec.type;
    o.frequency.setValueAtTime(spec.f * (detune || 1), t);
    o.frequency.exponentialRampToValueAtTime(Math.max(30, spec.f2 * (detune || 1)), t + spec.d);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(spec.g, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + spec.d);
    o.connect(g);
    g.connect(master);
    o.start(t);
    o.stop(t + spec.d + 0.05);
  }

  function noiseBurst(dur, freq, gain) {
    const c = ensure();
    if (!c || muted) return;
    const len = Math.floor(c.sampleRate * dur);
    const buf = c.createBuffer(1, len, c.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len);
    const src = c.createBufferSource();
    src.buffer = buf;
    const bp = c.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = freq;
    bp.Q.value = 1.4;
    const g = c.createGain();
    g.gain.value = gain;
    src.connect(bp);
    bp.connect(g);
    g.connect(master);
    src.start();
  }

  const audio = {
    get ready() {
      return !!ctx;
    },

    resume() {
      const c = ensure();
      if (c && c.state === 'suspended') c.resume();
    },

    setVolume(v) {
      volume = Math.max(0, Math.min(1, v));
      if (master) master.gain.setTargetAtTime(muted ? 0 : volume, ctx.currentTime, 0.02);
    },

    getVolume() {
      return volume;
    },

    toggleMute() {
      muted = !muted;
      if (master) master.gain.setTargetAtTime(muted ? 0 : volume, ctx.currentTime, 0.02);
      return muted;
    },

    /**
     * Rotor bed follows the run, so silence means the drone is idle. It never
     * creates the context: doing so before a user gesture only earns a browser
     * warning and a suspended context.
     */
    setRunning(on) {
      if (!ctx || !humGain) return;
      humGain.gain.setTargetAtTime(on ? 0.045 : 0, ctx.currentTime, 0.15);
    },

    play(kind) {
      const spec = NOTES[kind];
      if (spec) envTone(spec);
    },

    refuse() {
      noiseBurst(0.12, 220, 0.11);
      envTone({ f: 200, f2: 120, d: 0.14, type: 'square', g: 0.09 });
    },

    win() {
      const c = ensure();
      if (!c) return;
      const t = c.currentTime;
      const steps = [0, 4, 7, 12];
      for (let i = 0; i < steps.length; i++) {
        const f = 440 * Math.pow(2, steps[i] / 12);
        envTone({ f, f2: f * 1.005, d: 0.34, type: 'triangle', g: 0.16 }, t + i * 0.1);
      }
    },

    fail() {
      const c = ensure();
      if (!c) return;
      const t = c.currentTime;
      envTone({ f: 320, f2: 210, d: 0.22, type: 'sawtooth', g: 0.11 }, t);
      envTone({ f: 210, f2: 140, d: 0.32, type: 'sawtooth', g: 0.1 }, t + 0.14);
    },

    dispose() {
      if (hum) for (const o of hum) o.stop();
      if (ctx) ctx.close();
      ctx = null;
      master = null;
      hum = null;
    },
  };

  return audio;
}
