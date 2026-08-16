/**
 * PRISMA - synthesised audio.
 *
 * Web Audio only, no sound file. A puzzle is a quiet game: every cue is short,
 * soft and pitched inside one pentatonic scale so a fast sequence of edits never
 * turns into noise. The ambient pad is persistent and only ever ramped.
 */

const SCALE = [0, 3, 5, 7, 10, 12, 15, 17, 19, 22]; // minor pentatonic degrees
const BASE_MIDI = 62;

function midiToFreq(m) {
  return 440 * Math.pow(2, (m - 69) / 12);
}

export function createAudio() {
  let ctx = null;
  let master = null;
  let comp = null;
  let sfx = null;
  let padGain = null;
  let padNodes = [];
  let noiseBuffer = null;
  let volume = 0.6;
  let muted = false;
  let started = false;

  function buildGraph() {
    comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14;
    comp.ratio.value = 6;
    comp.attack.value = 0.004;
    comp.release.value = 0.2;
    comp.connect(ctx.destination);

    master = ctx.createGain();
    master.gain.value = muted ? 0 : volume;
    master.connect(comp);

    sfx = ctx.createGain();
    sfx.gain.value = 0.9;
    sfx.connect(master);

    const len = Math.floor(ctx.sampleRate * 1.5);
    noiseBuffer = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = noiseBuffer.getChannelData(0);
    let seed = 0x2545f491;
    for (let i = 0; i < len; i++) {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      data[i] = (seed / 4294967296) * 2 - 1;
    }

    padGain = ctx.createGain();
    padGain.gain.value = 0;
    const padFilter = ctx.createBiquadFilter();
    padFilter.type = 'lowpass';
    padFilter.frequency.value = 620;
    padFilter.Q.value = 1.2;
    padGain.connect(padFilter);
    padFilter.connect(master);

    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.07;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = 220;
    lfo.connect(lfoGain);
    lfoGain.connect(padFilter.frequency);
    lfo.start();
    padNodes.push(lfo);

    for (const [semi, detune, gain] of [
      [-24, -4, 0.5],
      [-12, 3, 0.34],
      [-5, -7, 0.22],
      [3, 6, 0.14],
    ]) {
      const osc = ctx.createOscillator();
      osc.type = 'sawtooth';
      osc.frequency.value = midiToFreq(BASE_MIDI + semi);
      osc.detune.value = detune;
      const g = ctx.createGain();
      g.gain.value = gain;
      osc.connect(g);
      g.connect(padGain);
      osc.start();
      padNodes.push(osc);
    }
  }

  function resume() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      ctx = new AC();
      buildGraph();
    }
    if (ctx.state === 'suspended') ctx.resume();
    if (!started) {
      started = true;
      padGain.gain.setTargetAtTime(0.055, ctx.currentTime, 2.5);
    }
  }

  /** One short enveloped voice. Everything audible in this game is built here. */
  function blip({ freq, type = 'sine', dur = 0.16, gain = 0.2, attack = 0.006, glide = 0, filter = 0, q = 1 }) {
    if (!ctx) return;
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    if (glide) osc.frequency.exponentialRampToValueAtTime(Math.max(30, freq * glide), t + dur);

    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);

    let tail = g;
    if (filter) {
      const f = ctx.createBiquadFilter();
      f.type = 'lowpass';
      f.frequency.value = filter;
      f.Q.value = q;
      g.connect(f);
      tail = f;
    }
    osc.connect(g);
    tail.connect(sfx);
    osc.start(t);
    osc.stop(t + dur + 0.05);
    osc.onended = () => {
      osc.disconnect();
      g.disconnect();
      if (tail !== g) tail.disconnect();
    };
  }

  function noise({ dur = 0.12, gain = 0.12, freq = 1800, type = 'bandpass', q = 1.4 }) {
    if (!ctx || !noiseBuffer) return;
    const t = ctx.currentTime;
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer;
    src.loop = true;
    const f = ctx.createBiquadFilter();
    f.type = type;
    f.frequency.value = freq;
    f.Q.value = q;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.006);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(f);
    f.connect(g);
    g.connect(sfx);
    src.start(t);
    src.stop(t + dur + 0.03);
    src.onended = () => {
      src.disconnect();
      f.disconnect();
      g.disconnect();
    };
  }

  function degree(i) {
    return midiToFreq(BASE_MIDI + SCALE[Math.max(0, Math.min(SCALE.length - 1, i))]);
  }

  return {
    resume,
    isMuted: () => muted,
    setVolume(v) {
      volume = Math.max(0, Math.min(1, v));
      if (master && !muted) master.gain.setTargetAtTime(volume, ctx.currentTime, 0.05);
    },
    getVolume: () => volume,
    toggleMute() {
      muted = !muted;
      if (master) master.gain.setTargetAtTime(muted ? 0 : volume, ctx.currentTime, 0.05);
      return muted;
    },
    place() {
      blip({ freq: degree(4), type: 'triangle', dur: 0.13, gain: 0.19, filter: 2600 });
      noise({ dur: 0.05, gain: 0.05, freq: 3200 });
    },
    remove() {
      blip({ freq: degree(1), type: 'sine', dur: 0.14, gain: 0.15, glide: 0.55 });
    },
    rotate() {
      blip({ freq: degree(6), type: 'square', dur: 0.05, gain: 0.06, filter: 2200 });
    },
    select() {
      blip({ freq: degree(5), type: 'sine', dur: 0.07, gain: 0.09 });
    },
    refuse() {
      blip({ freq: 116, type: 'sawtooth', dur: 0.17, gain: 0.11, filter: 480, q: 4 });
    },
    undo() {
      blip({ freq: degree(2), type: 'triangle', dur: 0.16, gain: 0.13, glide: 1.6 });
    },
    lit(index) {
      blip({ freq: degree(4 + (index % 5)) * 2, type: 'sine', dur: 0.5, gain: 0.17, filter: 5200 });
    },
    unlit() {
      blip({ freq: degree(2), type: 'sine', dur: 0.18, gain: 0.07, glide: 0.7 });
    },
    solved() {
      if (!ctx) return;
      [0, 2, 4, 6, 7].forEach((d, i) => {
        window.setTimeout(() => blip({ freq: degree(d) * 2, type: 'triangle', dur: 0.55, gain: 0.16, filter: 6000 }), i * 95);
      });
    },
    levelStart() {
      blip({ freq: degree(0), type: 'sine', dur: 0.6, gain: 0.13, filter: 1400 });
    },
    dispose() {
      for (const n of padNodes) {
        try {
          n.stop();
        } catch {
          /* already stopped */
        }
        n.disconnect();
      }
      padNodes = [];
      if (ctx) ctx.close();
      ctx = null;
    },
  };
}
