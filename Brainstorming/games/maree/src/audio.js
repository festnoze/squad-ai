/**
 * MAREE - synthesised audio. Web Audio only, no sound file. The context is
 * created lazily on the first user gesture, and every voice disconnects
 * itself once its envelope ends.
 */

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
    compressor.threshold.value = -16;
    compressor.ratio.value = 5;
    master.connect(compressor);
    compressor.connect(ctx.destination);

    const frames = Math.floor(ctx.sampleRate * 1.0);
    noiseBuffer = ctx.createBuffer(1, frames, ctx.sampleRate);
    const data = noiseBuffer.getChannelData(0);
    let seed = 88172645;
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

    raise() {
      tone({ freq: 220, to: 330, type: 'sine', dur: 0.28, gain: 0.15 });
      burst({ freq: 500, to: 900, dur: 0.3, gain: 0.05, q: 0.8 });
    },
    lower() {
      tone({ freq: 330, to: 200, type: 'sine', dur: 0.28, gain: 0.14 });
      burst({ freq: 700, to: 300, dur: 0.28, gain: 0.05, q: 0.8 });
    },
    gateOpen() {
      tone({ freq: 180, to: 420, type: 'triangle', dur: 0.32, gain: 0.15, cutoff: 2200 });
    },
    gateClose() {
      tone({ freq: 420, to: 160, type: 'triangle', dur: 0.3, gain: 0.14, cutoff: 1800 });
    },
    freeze() {
      tone({ freq: 900, type: 'sine', dur: 0.5, gain: 0.11, delay: 0 });
      tone({ freq: 1200, type: 'sine', dur: 0.6, gain: 0.08, delay: 0.08 });
      tone({ freq: 1500, type: 'sine', dur: 0.7, gain: 0.06, delay: 0.16 });
    },
    step(swimming) {
      if (swimming) burst({ freq: 500, to: 260, dur: 0.16, gain: 0.05, q: 1.2 });
      else tone({ freq: 140, type: 'sine', dur: 0.08, gain: 0.05 });
    },
    select() {
      tone({ freq: 700, type: 'triangle', dur: 0.08, gain: 0.09, cutoff: 3000 });
    },
    win() {
      const notes = [523.25, 659.25, 783.99, 1046.5];
      for (let i = 0; i < notes.length; i++) tone({ freq: notes[i], type: 'triangle', dur: 0.45, gain: 0.14, delay: i * 0.09 });
    },
    drown() {
      tone({ freq: 260, to: 60, type: 'sawtooth', dur: 0.9, gain: 0.13, cutoff: 700 });
      burst({ freq: 400, to: 60, dur: 0.9, gain: 0.06, q: 0.7 });
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
