/**
 * GRAVITE NEUF - synthesised feedback.
 *
 * Web Audio only, not one sound file. The context is created lazily on the
 * first user gesture (browsers refuse it before) and every voice disconnects
 * itself when its source ends, so nothing accumulates over a long session.
 *
 * The whole point of the palette is restraint: a puzzle is played for an hour,
 * so every cue is short, soft, and low in the mix.
 */

const NOISE_SECONDS = 1.2;

// One pitch per gravity axis, in the DIRS order of world.js. Hearing the axis
// is a second, free orientation cue on top of the sky colour.
const AXIS_NOTE = [329.63, 261.63, 493.88, 196.0, 392.0, 220.0];

export function createAudio() {
  let ctx = null;
  let master = null;
  let compressor = null;
  let noiseBuffer = null;
  let muted = false;
  let volume = 0.55;

  function ensure() {
    if (ctx) return true;
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return false;
    ctx = new Ctor();
    master = ctx.createGain();
    master.gain.value = muted ? 0 : volume;
    compressor = ctx.createDynamicsCompressor();
    compressor.threshold.value = -14;
    compressor.ratio.value = 6;
    master.connect(compressor);
    compressor.connect(ctx.destination);

    const frames = Math.floor(ctx.sampleRate * NOISE_SECONDS);
    noiseBuffer = ctx.createBuffer(1, frames, ctx.sampleRate);
    const data = noiseBuffer.getChannelData(0);
    let seed = 12345;
    for (let i = 0; i < frames; i++) {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      data[i] = (seed / 2147483648 - 1) * 0.6;
    }
    return true;
  }

  function now() {
    return ctx.currentTime;
  }

  /** One decaying oscillator voice with an optional pitch glide. */
  function tone(opts) {
    if (!ensure()) return;
    const t0 = now() + (opts.delay || 0);
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = opts.type || 'sine';
    osc.frequency.setValueAtTime(opts.freq, t0);
    if (opts.to) osc.frequency.exponentialRampToValueAtTime(Math.max(20, opts.to), t0 + opts.dur);
    const peak = (opts.gain === undefined ? 0.22 : opts.gain) * 0.9;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(peak, t0 + (opts.attack || 0.008));
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + opts.dur);
    osc.connect(gain);
    if (opts.cutoff) {
      const filter = ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(opts.cutoff, t0);
      gain.connect(filter);
      filter.connect(master);
    } else {
      gain.connect(master);
    }
    osc.start(t0);
    osc.stop(t0 + opts.dur + 0.05);
    osc.onended = () => {
      osc.disconnect();
      gain.disconnect();
    };
  }

  /** One filtered noise burst, for impacts and dust. */
  function burst(opts) {
    if (!ensure()) return;
    const t0 = now() + (opts.delay || 0);
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer;
    src.loop = true;
    const filter = ctx.createBiquadFilter();
    filter.type = opts.type || 'bandpass';
    filter.frequency.setValueAtTime(opts.freq, t0);
    if (opts.to) filter.frequency.exponentialRampToValueAtTime(Math.max(60, opts.to), t0 + opts.dur);
    filter.Q.value = opts.q === undefined ? 1.1 : opts.q;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(opts.gain === undefined ? 0.2 : opts.gain, t0 + 0.006);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + opts.dur);
    src.connect(filter);
    filter.connect(gain);
    gain.connect(master);
    src.start(t0);
    src.stop(t0 + opts.dur + 0.03);
    src.onended = () => {
      src.disconnect();
      filter.disconnect();
      gain.disconnect();
    };
  }

  return {
    resume() {
      if (!ensure()) return;
      if (ctx.state === 'suspended') ctx.resume();
    },
    get muted() {
      return muted;
    },
    setVolume(v) {
      volume = Math.max(0, Math.min(1, v));
      if (master) master.gain.value = muted ? 0 : volume;
    },
    getVolume() {
      return volume;
    },
    setMuted(value) {
      muted = !!value;
      if (master) master.gain.value = muted ? 0 : volume;
      return muted;
    },
    toggleMute() {
      return this.setMuted(!muted);
    },

    tilt(dirIndex) {
      const f = AXIS_NOTE[dirIndex] || 220;
      tone({ freq: f * 0.5, to: f, type: 'triangle', dur: 0.26, gain: 0.16, cutoff: 2400 });
      burst({ freq: 900, to: 240, dur: 0.3, gain: 0.055, q: 0.7 });
    },
    land(strength) {
      const s = Math.max(0.2, Math.min(1, strength));
      burst({ freq: 210, to: 90, dur: 0.13 + s * 0.08, gain: 0.1 + s * 0.1, q: 0.9, type: 'lowpass' });
      tone({ freq: 96, to: 62, type: 'sine', dur: 0.16, gain: 0.14 });
    },
    blocked() {
      burst({ freq: 320, to: 180, dur: 0.09, gain: 0.07, q: 1.4 });
    },
    key() {
      tone({ freq: 987.77, type: 'triangle', dur: 0.22, gain: 0.13 });
      tone({ freq: 1318.51, type: 'sine', dur: 0.3, gain: 0.1, delay: 0.05 });
    },
    glue() {
      tone({ freq: 180, to: 90, type: 'sawtooth', dur: 0.28, gain: 0.1, cutoff: 700 });
      burst({ freq: 420, to: 150, dur: 0.2, gain: 0.06, q: 2.4 });
    },
    spike() {
      burst({ freq: 1600, to: 200, dur: 0.26, gain: 0.16, q: 0.6 });
      tone({ freq: 140, to: 55, type: 'square', dur: 0.24, gain: 0.09, cutoff: 900 });
    },
    voidFall() {
      tone({ freq: 420, to: 48, type: 'sine', dur: 0.85, gain: 0.13 });
      burst({ freq: 700, to: 90, dur: 0.8, gain: 0.05, q: 0.8 });
    },
    win(perfect) {
      const notes = perfect ? [523.25, 659.25, 783.99, 1046.5] : [523.25, 659.25, 783.99];
      for (let i = 0; i < notes.length; i++) {
        tone({ freq: notes[i], type: 'triangle', dur: 0.45, gain: 0.14, delay: i * 0.085 });
      }
    },
    fail() {
      tone({ freq: 220, to: 82, type: 'sawtooth', dur: 0.5, gain: 0.11, cutoff: 800 });
    },
    undo() {
      tone({ freq: 300, to: 520, type: 'sine', dur: 0.16, gain: 0.1 });
    },
    click() {
      tone({ freq: 660, to: 880, type: 'square', dur: 0.06, gain: 0.06, cutoff: 2000 });
    },
    dispose() {
      if (ctx) ctx.close();
      ctx = null;
      master = null;
    },
  };
}
