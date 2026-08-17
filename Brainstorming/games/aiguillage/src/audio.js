/**
 * AIGUILLAGE - procedural Web Audio, zero sound files.
 *
 * A small persistent graph (ambient night drone + alarm siren, both muted
 * until needed) plus one-shot voices for switch clicks, whistles, the level
 * crossing bell and the crash boom. Everything is built once, on the first
 * resume() called from a user gesture.
 */

const NOISE_SECONDS = 2.0;

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
  let disposed = false;
  let gestureDone = false;

  let master = null;
  let compressor = null;
  let sfxBus = null;
  let noiseBuffer = null;

  let droneBus = null;
  let droneOscA = null;
  let droneOscB = null;

  let alarmBus = null;
  let alarmOsc = null;
  let alarmOn = false;
  let alarmPhase = 0;

  let bellTimer = 0;
  let bellActive = false;

  let volume = 1;
  let muted = false;

  function live() {
    return ctx !== null && !disposed && gestureDone && ctx.state !== 'closed';
  }
  function now() {
    return ctx.currentTime;
  }
  function freeOnEnd(source, a, b, c) {
    source.onended = function onended() {
      source.disconnect();
      if (a) a.disconnect();
      if (b) b.disconnect();
      if (c) c.disconnect();
    };
  }

  function buildNoise() {
    const rate = ctx.sampleRate;
    const len = Math.floor(rate * NOISE_SECONDS);
    const buf = ctx.createBuffer(1, len, rate);
    const data = buf.getChannelData(0);
    const rnd = mulberry32(0x1ec0de11);
    for (let i = 0; i < len; i++) data[i] = rnd() * 2 - 1;
    return buf;
  }

  function buildMaster() {
    compressor = ctx.createDynamicsCompressor();
    compressor.threshold.value = -16;
    compressor.knee.value = 12;
    compressor.ratio.value = 4.5;
    compressor.attack.value = 0.005;
    compressor.release.value = 0.2;
    compressor.connect(ctx.destination);

    master = ctx.createGain();
    master.gain.value = muted ? 0.0001 : 0.85 * volume;
    master.connect(compressor);

    sfxBus = ctx.createGain();
    sfxBus.gain.value = 1;
    sfxBus.connect(master);
  }

  function buildDrone() {
    droneBus = ctx.createGain();
    droneBus.gain.value = 0.05;
    droneBus.connect(master);

    droneOscA = ctx.createOscillator();
    droneOscA.type = 'sine';
    droneOscA.frequency.value = 55;
    droneOscB = ctx.createOscillator();
    droneOscB.type = 'sine';
    droneOscB.frequency.value = 55.6;
    const g = ctx.createGain();
    g.gain.value = 0.5;
    droneOscA.connect(g);
    droneOscB.connect(g);
    g.connect(droneBus);
  }

  function buildAlarm() {
    alarmBus = ctx.createGain();
    alarmBus.gain.value = 0.0001;
    alarmBus.connect(master);

    alarmOsc = ctx.createOscillator();
    alarmOsc.type = 'sawtooth';
    alarmOsc.frequency.value = 500;
    const filt = ctx.createBiquadFilter();
    filt.type = 'bandpass';
    filt.frequency.value = 900;
    filt.Q.value = 3;
    alarmOsc.connect(filt);
    filt.connect(alarmBus);
    alarmOsc.__filter = filt;
  }

  function ensureContext() {
    if (ctx || disposed) return;
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return;
    ctx = new Ctor({ latencyHint: 'interactive' });
    noiseBuffer = buildNoise();
    buildMaster();
    buildDrone();
    buildAlarm();
    const t = ctx.currentTime;
    droneOscA.start(t);
    droneOscB.start(t);
    alarmOsc.start(t);
  }

  function noiseBurst(t, dur, type, freq, q, level, dest, sweepTo) {
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer;
    const flt = ctx.createBiquadFilter();
    flt.type = type;
    flt.Q.value = q;
    flt.frequency.setValueAtTime(freq, t);
    if (sweepTo) flt.frequency.exponentialRampToValueAtTime(sweepTo, t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0005, level), t + Math.min(0.012, dur * 0.3));
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(flt);
    flt.connect(g);
    g.connect(dest);
    src.start(t, 0, dur + 0.05);
    freeOnEnd(src, flt, g);
  }

  function playTone(t, freq, dur, level, type, dest, detune) {
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    if (detune) osc.detune.setValueAtTime(detune, t);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0005, level), t + Math.min(0.012, dur * 0.2));
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g);
    g.connect(dest);
    osc.start(t);
    osc.stop(t + dur + 0.02);
    freeOnEnd(osc, g);
  }

  const api = {
    resume() {
      if (disposed) return;
      gestureDone = true;
      ensureContext();
      if (ctx && ctx.state !== 'running') ctx.resume().catch(() => {});
    },

    setMasterVolume(v01) {
      volume = v01 < 0 ? 0 : v01 > 1 ? 1 : v01;
      if (ctx) master.gain.setTargetAtTime(muted ? 0.0001 : 0.85 * volume, now(), 0.05);
    },

    toggleMute() {
      muted = !muted;
      if (ctx) master.gain.setTargetAtTime(muted ? 0.0001 : 0.85 * volume, now(), 0.05);
      return muted;
    },

    /** Short mechanical click, pitched a touch differently for each state. */
    switchClick(state) {
      if (!live()) return;
      const t = now() + 0.004;
      noiseBurst(t, 0.05, 'highpass', state ? 2600 : 2000, 2.2, 0.35, sfxBus, 5200);
      playTone(t, state ? 720 : 560, 0.05, 0.18, 'square', sfxBus, 0);
    },

    /** Train entering the yard: two note horn. */
    whistle() {
      if (!live()) return;
      const t = now() + 0.01;
      playTone(t, 262, 0.5, 0.16, 'sawtooth', sfxBus, 0);
      playTone(t, 330, 0.5, 0.1, 'sawtooth', sfxBus, -4);
      playTone(t + 0.05, 392, 0.9, 0.14, 'sawtooth', sfxBus, 0);
      playTone(t + 0.05, 330, 0.9, 0.08, 'sawtooth', sfxBus, 5);
    },

    /** Train correctly (or incorrectly) delivered. */
    chime(good) {
      if (!live()) return;
      const t = now() + 0.005;
      if (good) {
        playTone(t, 523, 0.16, 0.2, 'sine', sfxBus, 0);
        playTone(t + 0.1, 659, 0.28, 0.2, 'sine', sfxBus, 0);
        playTone(t + 0.2, 784, 0.4, 0.2, 'sine', sfxBus, 0);
      } else {
        playTone(t, 300, 0.3, 0.2, 'sawtooth', sfxBus, 0);
        playTone(t + 0.14, 220, 0.5, 0.2, 'sawtooth', sfxBus, 0);
      }
    },

    /** Level crossing bell, called repeatedly while the gate is closed. */
    bellTick() {
      if (!live()) return;
      const t = now() + 0.004;
      playTone(t, 1500, 0.1, 0.14, 'square', sfxBus, 0);
    },

    crash() {
      if (!live()) return;
      const t = now() + 0.005;
      noiseBurst(t, 1.1, 'lowpass', 5000, 2.4, 0.5, sfxBus, 90);
      noiseBurst(t, 0.05, 'highpass', 3200, 0.8, 0.4, sfxBus);
      playTone(t, 90, 0.7, 0.4, 'sine', sfxBus, 0);
      playTone(t + 0.05, 60, 0.9, 0.3, 'sine', sfxBus, 0);
    },

    setAlarm(on) {
      alarmOn = on;
      if (!live()) return;
      alarmBus.gain.setTargetAtTime(on ? 0.14 : 0.0001, now(), on ? 0.05 : 0.2);
    },

    finish(won) {
      if (!live()) return;
      const t = now() + 0.02;
      if (won) {
        playTone(t, 523, 0.2, 0.22, 'triangle', sfxBus, 0);
        playTone(t + 0.15, 659, 0.2, 0.22, 'triangle', sfxBus, 0);
        playTone(t + 0.3, 784, 0.5, 0.24, 'triangle', sfxBus, 0);
        playTone(t + 0.3, 988, 0.5, 0.16, 'sine', sfxBus, 0);
      } else {
        playTone(t, 220, 0.9, 0.22, 'sawtooth', sfxBus, 0);
        playTone(t, 210, 0.9, 0.2, 'sawtooth', sfxBus, 8);
      }
    },

    /** Per frame smoothing: alarm siren pitch wobble and crossing bell cadence. */
    update(dt) {
      if (!ctx || disposed) return;
      if (ctx.state !== 'running') return;
      if (alarmOn) {
        alarmPhase += dt;
        const f = 480 + Math.sin(alarmPhase * 6) * 220;
        alarmOsc.frequency.setTargetAtTime(f, now(), 0.03);
      }
      if (bellActive) {
        bellTimer -= dt;
        if (bellTimer <= 0) {
          bellTimer = 0.55;
          api.bellTick();
        }
      }
    },

    setBell(active) {
      bellActive = active;
      if (active) bellTimer = 0;
    },

    dispose() {
      if (disposed) return;
      disposed = true;
      if (!ctx) return;
      const t = ctx.currentTime;
      for (const s of [droneOscA, droneOscB, alarmOsc]) {
        if (!s) continue;
        try { s.stop(t); } catch (err) { /* already stopped */ }
        s.disconnect();
      }
      const dying = ctx;
      ctx = null;
      const closing = dying.close();
      if (closing && closing.catch) closing.catch(() => {});
    },
  };

  return api;
}
