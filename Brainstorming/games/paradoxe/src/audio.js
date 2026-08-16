/**
 * PARADOXE - synthesised audio.
 *
 * No sound file anywhere: oscillators, one seeded noise buffer, and short
 * envelopes. The context is only created on the first user gesture, which is
 * what browsers require, and every voice disconnects itself when it ends so the
 * graph never grows.
 *
 * The palette is deliberately quiet: this is a thinking game, and a puzzle you
 * replay twenty times must not shout at you twenty times.
 */

import { AUDIO } from './config.js';

function mulberry32(seed) {
  let a = seed >>> 0;
  return function random() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function createAudio() {
  let ctx = null;
  let master = null;
  let comp = null;
  let noiseBuffer = null;
  let padGain = null;
  let padNodes = null;
  let muted = false;
  let volume = AUDIO.master;

  function build() {
    if (ctx) return true;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return false;
    ctx = new AC();
    comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14;
    comp.ratio.value = 8;
    comp.attack.value = 0.004;
    comp.release.value = 0.18;
    comp.connect(ctx.destination);
    master = ctx.createGain();
    master.gain.value = muted ? 0 : volume;
    master.connect(comp);

    const len = Math.floor(ctx.sampleRate * 1.6);
    noiseBuffer = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = noiseBuffer.getChannelData(0);
    const rnd = mulberry32(1234567);
    for (let i = 0; i < len; i++) data[i] = rnd() * 2 - 1;
    return true;
  }

  function now() {
    return ctx.currentTime;
  }

  function tone(freq, dur, type, gain, attack, detune) {
    if (!ctx) return null;
    const t0 = now();
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type || 'sine';
    osc.frequency.setValueAtTime(freq, t0);
    if (detune) osc.detune.setValueAtTime(detune, t0);
    const a = attack === undefined ? 0.004 : attack;
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0002, gain), t0 + a);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(g);
    g.connect(master);
    osc.start(t0);
    osc.stop(t0 + dur + 0.05);
    osc.onended = () => {
      g.disconnect();
    };
    return { osc, gain: g, t0 };
  }

  function sweep(f0, f1, dur, type, gain) {
    if (!ctx) return;
    const t0 = now();
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type || 'sawtooth';
    osc.frequency.setValueAtTime(f0, t0);
    osc.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(gain, t0 + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.setValueAtTime(2600, t0);
    osc.connect(lp);
    lp.connect(g);
    g.connect(master);
    osc.start(t0);
    osc.stop(t0 + dur + 0.05);
    osc.onended = () => g.disconnect();
  }

  function noise(dur, freq, q, gain, type) {
    if (!ctx) return;
    const t0 = now();
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer;
    src.loop = true;
    const f = ctx.createBiquadFilter();
    f.type = type || 'bandpass';
    f.frequency.setValueAtTime(freq, t0);
    f.Q.value = q || 1;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(gain, t0 + 0.006);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(f);
    f.connect(g);
    g.connect(master);
    src.start(t0);
    src.stop(t0 + dur + 0.05);
    src.onended = () => g.disconnect();
  }

  const audio = {
    get enabled() {
      return !!ctx && !muted;
    },
    get muted() {
      return muted;
    },
  };

  audio.resume = function resume() {
    if (!build()) return;
    if (ctx.state === 'suspended') ctx.resume();
  };

  audio.setVolume = function setVolume(v) {
    volume = v;
    if (master) master.gain.setTargetAtTime(muted ? 0 : v, now(), 0.05);
  };

  audio.toggleMute = function toggleMute() {
    muted = !muted;
    if (master) master.gain.setTargetAtTime(muted ? 0 : volume, now(), 0.03);
    return muted;
  };

  /** Low, slow pad so silence between attempts is not dead air. */
  audio.startAmbient = function startAmbient() {
    if (!ctx || padNodes) return;
    const t0 = now();
    padGain = ctx.createGain();
    padGain.gain.setValueAtTime(0.0001, t0);
    padGain.gain.exponentialRampToValueAtTime(0.055, t0 + 2.5);
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 520;
    lp.Q.value = 0.7;
    padGain.connect(lp);
    lp.connect(master);
    const freqs = [55, 82.4, 110, 164.8];
    padNodes = [];
    for (let i = 0; i < freqs.length; i++) {
      const osc = ctx.createOscillator();
      osc.type = i % 2 === 0 ? 'sine' : 'triangle';
      osc.frequency.value = freqs[i];
      osc.detune.value = (i - 1.5) * 6;
      const g = ctx.createGain();
      g.gain.value = 0.35 / (i + 1);
      osc.connect(g);
      g.connect(padGain);
      osc.start(t0);
      padNodes.push({ osc, g });
    }
    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.07;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = 160;
    lfo.connect(lfoGain);
    lfoGain.connect(lp.frequency);
    lfo.start(t0);
    padNodes.push({ osc: lfo, g: lfoGain });
  };

  audio.stopAmbient = function stopAmbient() {
    if (!padNodes) return;
    const t0 = now();
    if (padGain) padGain.gain.setTargetAtTime(0.0001, t0, 0.4);
    const nodes = padNodes;
    padNodes = null;
    setTimeout(() => {
      for (let i = 0; i < nodes.length; i++) {
        try {
          nodes[i].osc.stop();
        } catch (e) {
          void e;
        }
        nodes[i].g.disconnect();
      }
      if (padGain) padGain.disconnect();
      padGain = null;
    }, 1400);
  };

  /** Fire one short cue. Unknown names are ignored on purpose. */
  audio.play = function play(name) {
    if (!ctx || muted) return;
    switch (name) {
      case 'jump':
        tone(430, 0.13, 'triangle', 0.13, 0.003);
        tone(660, 0.09, 'sine', 0.05, 0.003);
        break;
      case 'land':
        noise(0.09, 180, 1.1, 0.11, 'lowpass');
        break;
      case 'step':
        noise(0.045, 900, 1.6, 0.022);
        break;
      case 'grab':
        tone(720, 0.07, 'square', 0.055);
        tone(1080, 0.05, 'sine', 0.03);
        break;
      case 'drop':
        tone(300, 0.1, 'square', 0.06);
        noise(0.08, 260, 1.2, 0.06, 'lowpass');
        break;
      case 'refuse':
        tone(150, 0.13, 'square', 0.05);
        tone(142, 0.13, 'square', 0.05);
        break;
      case 'buttonOn':
        tone(880, 0.06, 'square', 0.05);
        tone(1320, 0.1, 'sine', 0.04);
        break;
      case 'buttonOff':
        tone(560, 0.06, 'square', 0.04);
        break;
      case 'plate':
        tone(180, 0.18, 'triangle', 0.09);
        noise(0.12, 320, 1.0, 0.06, 'lowpass');
        break;
      case 'doorOpen':
        sweep(220, 900, 0.35, 'sawtooth', 0.055);
        break;
      case 'doorClose':
        sweep(760, 190, 0.3, 'sawtooth', 0.05);
        break;
      case 'teleport':
        sweep(300, 1900, 0.28, 'sine', 0.07);
        noise(0.25, 2400, 2.4, 0.045);
        break;
      case 'crack':
        noise(0.16, 1400, 3.2, 0.05);
        break;
      case 'collapse':
        noise(0.5, 420, 0.8, 0.1, 'lowpass');
        sweep(180, 60, 0.5, 'triangle', 0.06);
        break;
      case 'rewind':
        sweep(1500, 120, 0.62, 'sawtooth', 0.09);
        noise(0.6, 900, 1.2, 0.05);
        break;
      case 'clone':
        tone(523.25, 0.22, 'sine', 0.07);
        tone(1046.5, 0.3, 'sine', 0.04, 0.05);
        break;
      case 'paradox':
        sweep(600, 70, 0.8, 'square', 0.09);
        tone(93, 0.7, 'sawtooth', 0.07);
        tone(99, 0.7, 'sawtooth', 0.07);
        noise(0.7, 700, 0.9, 0.06);
        break;
      case 'tick':
        tone(1500, 0.035, 'sine', 0.035);
        break;
      case 'win': {
        const notes = [523.25, 659.25, 783.99, 1046.5];
        for (let i = 0; i < notes.length; i++) {
          const t = i * 0.09;
          setTimeout(() => {
            if (ctx && !muted) tone(notes[i], 0.4, 'triangle', 0.09, 0.01);
          }, t * 1000);
        }
        break;
      }
      case 'fail':
        tone(196, 0.5, 'sawtooth', 0.07);
        tone(185, 0.5, 'sawtooth', 0.06);
        break;
      case 'ui':
        tone(1200, 0.04, 'sine', 0.04);
        break;
      case 'medal':
        tone(880, 0.5, 'sine', 0.07);
        tone(1318.5, 0.6, 'sine', 0.05, 0.02);
        break;
      default:
        break;
    }
  };

  audio.dispose = function dispose() {
    audio.stopAmbient();
    if (ctx) {
      try {
        ctx.close();
      } catch (e) {
        void e;
      }
    }
    ctx = null;
    master = null;
    comp = null;
  };

  return audio;
}
