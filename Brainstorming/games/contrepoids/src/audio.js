/**
 * CONTREPOIDS - synthesised feedback.
 *
 * Web Audio only, no sound file. The context is created lazily on the first
 * user gesture (browsers refuse it before), and every voice disconnects
 * itself when its source ends so nothing accumulates over a long session.
 */

const NOISE_SECONDS = 1.2;

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
    let seed = 77123;
    for (let i = 0; i < frames; i++) {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      data[i] = (seed / 2147483648 - 1) * 0.6;
    }
    return true;
  }

  function now() {
    return ctx.currentTime;
  }

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

    step() {
      burst({ freq: 320, to: 180, dur: 0.07, gain: 0.05, q: 1.6 });
    },
    jump() {
      tone({ freq: 340, to: 520, type: 'triangle', dur: 0.16, gain: 0.12 });
    },
    blocked() {
      burst({ freq: 220, to: 140, dur: 0.09, gain: 0.06, q: 1.4 });
    },
    take() {
      tone({ freq: 520, to: 700, type: 'sine', dur: 0.12, gain: 0.12 });
    },
    drop() {
      tone({ freq: 300, to: 190, type: 'sine', dur: 0.14, gain: 0.13 });
      burst({ freq: 260, to: 140, dur: 0.1, gain: 0.05, q: 1.2 });
    },
    push() {
      burst({ freq: 180, to: 90, dur: 0.32, gain: 0.11, q: 0.6, type: 'lowpass' });
    },
    /** Pulley creak, pitched a little by how far the rope moved. */
    pulley(amount) {
      const a = Math.max(1, Math.min(6, amount));
      tone({ freq: 180 + a * 12, to: 130 + a * 8, type: 'sawtooth', dur: 0.3 + a * 0.03, gain: 0.1, cutoff: 1200 });
      burst({ freq: 900, to: 260, dur: 0.28, gain: 0.05, q: 0.8 });
    },
    win(perfect) {
      const notes = perfect ? [523.25, 659.25, 783.99, 1046.5] : [523.25, 659.25, 783.99];
      for (let i = 0; i < notes.length; i++) {
        tone({ freq: notes[i], type: 'triangle', dur: 0.45, gain: 0.14, delay: i * 0.085 });
      }
    },
    undo() {
      tone({ freq: 300, to: 480, type: 'sine', dur: 0.15, gain: 0.1 });
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
