/**
 * VELOCITRON - procedural audio engine.
 *
 * Pure Web Audio: not a single sound file, not a single fetch. Everything is
 * synthesised from oscillators and one deterministic white noise buffer.
 *
 * Layout of the graph (built exactly once, on the first resume()):
 *
 *   engine oscillators -> resonant lowpass -> engineLevel -\
 *   wind noise         -> bandpass -> windGain ------------> engineBus --\
 *   drums / bass / arp -> musicBus (arp also feeds a ping pong delay) ---+-> master
 *   one shots + scrape -> sfxBus ---------------------------------------/
 *
 *   master -> DynamicsCompressor -> destination
 *
 * The engine and the scrape voices are persistent: they are started once and
 * only ever modulated with setTargetAtTime ramps, so they never click. One
 * shots and music notes are short lived voices that disconnect themselves when
 * their source ends.
 */

import { AUDIO } from './config.js';

// ---------------------------------------------------------------------------
// Musical constants. Dark techno in A minor, 4 bars of 16 steps.
// ---------------------------------------------------------------------------
const REST = -128;
const BAR_STEPS = 16;
const LOOP_STEPS = 64;
const SCHEDULER_MS = 25;
const LOOKAHEAD = 0.1;
const NOISE_SECONDS = 2.5;

// Chord roots of the 4 bar loop, in semitones from the tonic: Am - F - C - G.
const BASS_ROOT_MIDI = 33; // A1
const ARP_ROOT_MIDI = 69; // A4
const BAR_ROOT_BASS = [0, -4, 3, -2];
const BAR_ROOT_ARP = [0, 8, 3, 10];
const BAR_THIRD = [3, 4, 4, 4]; // minor, major, major, major
const BAR_ARP_GAIN = [0.55, 1.0, 0.78, 1.0];

// Acid line: semitone offsets above the bar root, REST for a silent step.
const BASS_NOTES = [0, REST, 0, 12, REST, 0, 3, REST, 7, REST, 0, 10, 12, REST, 7, 3];
const BASS_ACCENT = [1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1];
const BASS_SLIDE = [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0];

// Arpeggio: indices into the extended triad [root, third, fifth, +8ve, third+8ve].
const ARP_SHAPE = [0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 4, 3, 2, 1, 0, 2];
const ARP_LEVEL = [1, 0.55, 0.75, 0.55, 0.9, 0.55, 0.8, 0.6, 1, 0.55, 0.75, 0.6, 0.9, 0.6, 0.85, 0.7];
const HAT_LEVEL = [1, 0.42, 0.66, 0.44, 0.95, 0.42, 0.66, 0.5, 1, 0.42, 0.66, 0.44, 0.9, 0.5, 0.7, 0.55];

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

function midiToFreq(m) {
  return 440 * Math.pow(2, (m - 69) / 12);
}

/** Deterministic PRNG so the noise bed is identical from one session to the next. */
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
  let gestureDone = false; // resume() has been called from a user gesture
  let resumeRetry = 0;

  // master chain
  let master = null;
  let compressor = null;
  let sfxBus = null;

  // engine voices
  let engineBus = null;
  let engineLevel = null;
  let engineFilter = null;
  let oscSaw = null;
  let oscSquare = null;
  let oscSub = null;
  let windFilter = null;
  let windGain = null;
  let windSource = null;

  // scrape voice
  let scrapeSource = null;
  let scrapeFilter = null;
  let scrapeGain = null;

  // music graph
  let musicBus = null;
  let drumBus = null;
  let bassBus = null;
  let arpBus = null;
  let delaySend = null;
  let delayL = null;
  let delayR = null;
  let delayFb = null;
  let delayWet = null;
  let delayMerger = null;

  let noiseBuffer = null;

  // state
  let volume = 1;
  let muted = false;
  let engineOn = false;
  let musicOn = false;
  let schedulerId = 0;
  let nextStepTime = 0;
  let stepIndex = 0;
  let prevBassFreq = 0;
  let prevBassSlide = 0;
  let scrapeLevel = 0;
  let noiseCursor = 0.137;

  // engine control targets and their smoothed values (no per frame allocation)
  let tSpeed = 0;
  let tThrottle = 0;
  let tBoost = 0;
  let tAir = 0;
  let sSpeed = 0;
  let sThrottle = 0;
  let sBoost = 0;
  let sAir = 0;

  // last value pushed to each AudioParam, to keep the automation timeline short
  const applied = {
    saw: -1, sq: -1, sub: -1, cut: -1, res: -1,
    wind: -1, windF: -1, drive: -1, scrapeG: -1, scrapeF: -1,
  };

  const stepDur = 60 / AUDIO.bpm / 4;

  // -------------------------------------------------------------------------
  // Guards
  // -------------------------------------------------------------------------
  /** True once a user gesture created the context and it can still be scheduled on. */
  function live() {
    return ctx !== null && !disposed && gestureDone && ctx.state !== 'closed';
  }

  function now() {
    return ctx.currentTime;
  }

  /** Release a short lived voice as soon as its source stops. */
  function freeOnEnd(source, a, b, c) {
    source.onended = function onended() {
      source.disconnect();
      if (a) a.disconnect();
      if (b) b.disconnect();
      if (c) c.disconnect();
    };
  }

  /** Push a value onto an AudioParam only when it actually moved. */
  function ramp(param, key, value, tc) {
    const prev = applied[key];
    if (prev >= 0 && Math.abs(prev - value) <= Math.abs(value) * 0.002 + 0.0004) return;
    applied[key] = value;
    param.setTargetAtTime(value, ctx.currentTime, tc);
  }

  /** Rolling read offset into the noise buffer, so two bursts never phase align. */
  function noiseOffset(span) {
    noiseCursor = (noiseCursor + 0.6180339887) % 1;
    return noiseCursor * span;
  }

  // -------------------------------------------------------------------------
  // Graph construction (once)
  // -------------------------------------------------------------------------
  function buildNoise() {
    const rate = ctx.sampleRate;
    const len = Math.floor(rate * NOISE_SECONDS);
    const buf = ctx.createBuffer(1, len, rate);
    const data = buf.getChannelData(0);
    const rnd = mulberry32(0x5eed1234);
    for (let i = 0; i < len; i++) data[i] = rnd() * 2 - 1;
    return buf;
  }

  function buildMaster() {
    compressor = ctx.createDynamicsCompressor();
    compressor.threshold.value = -17;
    compressor.knee.value = 14;
    compressor.ratio.value = 5;
    compressor.attack.value = 0.004;
    compressor.release.value = 0.19;
    compressor.connect(ctx.destination);

    master = ctx.createGain();
    master.gain.value = muted ? 0.0001 : AUDIO.masterGain * volume;
    master.connect(compressor);

    sfxBus = ctx.createGain();
    sfxBus.gain.value = 1;
    sfxBus.connect(master);
  }

  function buildEngine() {
    engineBus = ctx.createGain();
    engineBus.gain.value = engineOn ? AUDIO.engineGain : 0.0001;
    engineBus.connect(master);

    engineLevel = ctx.createGain();
    engineLevel.gain.value = 0.6;
    engineLevel.connect(engineBus);

    engineFilter = ctx.createBiquadFilter();
    engineFilter.type = 'lowpass';
    engineFilter.frequency.value = 320;
    engineFilter.Q.value = 6;
    engineFilter.connect(engineLevel);

    oscSaw = ctx.createOscillator();
    oscSaw.type = 'sawtooth';
    oscSaw.frequency.value = 42;
    oscSaw.detune.value = 7;
    const gSaw = ctx.createGain();
    gSaw.gain.value = 0.5;
    oscSaw.connect(gSaw);
    gSaw.connect(engineFilter);

    oscSquare = ctx.createOscillator();
    oscSquare.type = 'square';
    oscSquare.frequency.value = 42;
    oscSquare.detune.value = -11;
    const gSq = ctx.createGain();
    gSq.gain.value = 0.2;
    oscSquare.connect(gSq);
    gSq.connect(engineFilter);

    // The sub bypasses the filter so the low end stays solid when it closes.
    oscSub = ctx.createOscillator();
    oscSub.type = 'sine';
    oscSub.frequency.value = 21;
    const gSub = ctx.createGain();
    gSub.gain.value = 0.55;
    oscSub.connect(gSub);
    gSub.connect(engineLevel);

    windFilter = ctx.createBiquadFilter();
    windFilter.type = 'bandpass';
    windFilter.frequency.value = 500;
    windFilter.Q.value = 0.7;

    windGain = ctx.createGain();
    windGain.gain.value = 0.0001;
    windFilter.connect(windGain);
    windGain.connect(engineBus);

    windSource = ctx.createBufferSource();
    windSource.buffer = noiseBuffer;
    windSource.loop = true;
    windSource.connect(windFilter);
  }

  function buildScrape() {
    scrapeFilter = ctx.createBiquadFilter();
    scrapeFilter.type = 'bandpass';
    scrapeFilter.frequency.value = 1800;
    scrapeFilter.Q.value = 2.6;

    scrapeGain = ctx.createGain();
    scrapeGain.gain.value = 0.0001;
    scrapeFilter.connect(scrapeGain);
    scrapeGain.connect(sfxBus);

    scrapeSource = ctx.createBufferSource();
    scrapeSource.buffer = noiseBuffer;
    scrapeSource.loop = true;
    scrapeSource.playbackRate.value = 1.31;
    scrapeSource.connect(scrapeFilter);
  }

  function buildMusic() {
    musicBus = ctx.createGain();
    musicBus.gain.value = musicOn ? AUDIO.musicGain : 0.0001;
    musicBus.connect(master);

    drumBus = ctx.createGain();
    drumBus.gain.value = 0.9;
    drumBus.connect(musicBus);

    bassBus = ctx.createGain();
    bassBus.gain.value = 0.5;
    bassBus.connect(musicBus);

    arpBus = ctx.createGain();
    arpBus.gain.value = 0.15;
    arpBus.connect(musicBus);

    // Ping pong delay fed by the arpeggio bus only.
    const tapTime = (60 / AUDIO.bpm) * 0.375; // dotted eighth, tempo locked
    delaySend = ctx.createGain();
    delaySend.gain.value = 0.6;
    delayL = ctx.createDelay(1.5);
    delayR = ctx.createDelay(1.5);
    delayL.delayTime.value = tapTime;
    delayR.delayTime.value = tapTime;
    delayFb = ctx.createGain();
    delayFb.gain.value = 0.38;
    delayMerger = ctx.createChannelMerger(2);
    delayWet = ctx.createGain();
    delayWet.gain.value = 0.5;

    arpBus.connect(delaySend);
    delaySend.connect(delayL);
    delayL.connect(delayMerger, 0, 0);
    delayL.connect(delayR);
    delayR.connect(delayMerger, 0, 1);
    delayR.connect(delayFb);
    delayFb.connect(delayL);
    delayMerger.connect(delayWet);
    delayWet.connect(musicBus);
  }

  function ensureContext() {
    if (ctx || disposed) return;
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return;
    ctx = new Ctor({ latencyHint: 'interactive' });
    noiseBuffer = buildNoise();
    buildMaster();
    buildEngine();
    buildScrape();
    buildMusic();
    // Persistent sources: started exactly once, for the lifetime of the context.
    const t = ctx.currentTime;
    oscSaw.start(t);
    oscSquare.start(t);
    oscSub.start(t);
    windSource.start(t);
    scrapeSource.start(t);
  }

  // -------------------------------------------------------------------------
  // Generic voices
  // -------------------------------------------------------------------------
  function noiseBurst(t, dur, type, freq, q, level, dest, sweepTo) {
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer;
    const flt = ctx.createBiquadFilter();
    flt.type = type;
    flt.Q.value = q;
    flt.frequency.setValueAtTime(freq, t);
    if (sweepTo) flt.frequency.exponentialRampToValueAtTime(sweepTo, t + dur);
    const g = ctx.createGain();
    const atk = Math.min(0.012, dur * 0.25);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0002, level), t + atk);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(flt);
    flt.connect(g);
    g.connect(dest);
    const span = Math.max(0.05, NOISE_SECONDS - dur - 0.1);
    src.start(t, noiseOffset(span), dur + 0.06);
    freeOnEnd(src, flt, g);
    return g;
  }

  function playTone(t, midi, dur, level, type, dest, detune) {
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(midiToFreq(midi), t);
    if (detune) osc.detune.setValueAtTime(detune, t);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0002, level), t + Math.min(0.014, dur * 0.2));
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g);
    g.connect(dest);
    osc.start(t);
    osc.stop(t + dur + 0.02);
    freeOnEnd(osc, g);
    return g;
  }

  function sweepTone(t, f0, f1, dur, level, type, dest, cutFrom, cutTo) {
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(f0, t);
    osc.frequency.exponentialRampToValueAtTime(f1, t + dur * 0.75);
    const flt = ctx.createBiquadFilter();
    flt.type = 'lowpass';
    flt.Q.value = 3;
    flt.frequency.setValueAtTime(cutFrom, t);
    flt.frequency.exponentialRampToValueAtTime(cutTo, t + dur * 0.8);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(level, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(flt);
    flt.connect(g);
    g.connect(dest);
    osc.start(t);
    osc.stop(t + dur + 0.02);
    freeOnEnd(osc, flt, g);
    return g;
  }

  // -------------------------------------------------------------------------
  // Drum and synth voices
  // -------------------------------------------------------------------------
  function playKick(t, level) {
    const osc = ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(152, t);
    osc.frequency.exponentialRampToValueAtTime(44, t + 0.085);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(level, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.34);
    osc.connect(g);
    g.connect(drumBus);
    osc.start(t);
    osc.stop(t + 0.36);
    freeOnEnd(osc, g);
    noiseBurst(t, 0.022, 'highpass', 2400, 0.9, level * 0.3, drumBus);
  }

  function playSnare(t, level) {
    noiseBurst(t, 0.19, 'bandpass', 1750, 0.85, level * 0.55, drumBus, 900);
    const osc = ctx.createOscillator();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(198, t);
    osc.frequency.exponentialRampToValueAtTime(132, t + 0.08);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(level * 0.4, t + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.13);
    osc.connect(g);
    g.connect(drumBus);
    osc.start(t);
    osc.stop(t + 0.15);
    freeOnEnd(osc, g);
  }

  function playHat(t, level, open) {
    noiseBurst(t, open ? 0.17 : 0.035, 'highpass', open ? 6800 : 8200, 0.8, level * 0.16, drumBus);
  }

  function playBass(t, midi, accent, slide) {
    const osc = ctx.createOscillator();
    osc.type = 'sawtooth';
    const f = midiToFreq(midi);
    if (prevBassSlide && prevBassFreq > 0) {
      osc.frequency.setValueAtTime(prevBassFreq, t);
      osc.frequency.exponentialRampToValueAtTime(f, t + stepDur * 0.55);
    } else {
      osc.frequency.setValueAtTime(f, t);
    }

    const flt = ctx.createBiquadFilter();
    flt.type = 'lowpass';
    flt.Q.value = 11 + accent * 5;
    const cut0 = 190 + accent * 240;
    const peak = 950 + accent * 2100;
    flt.frequency.setValueAtTime(cut0, t);
    flt.frequency.exponentialRampToValueAtTime(peak, t + 0.018);
    flt.frequency.exponentialRampToValueAtTime(cut0 + 90, t + stepDur * (accent ? 1.7 : 0.95));

    const dur = stepDur * (slide ? 1.08 : 0.74);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.55 + accent * 0.3, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);

    osc.connect(flt);
    flt.connect(g);
    g.connect(bassBus);
    osc.start(t);
    osc.stop(t + dur + 0.03);
    freeOnEnd(osc, flt, g);

    prevBassFreq = f;
    prevBassSlide = slide;
  }

  function playArp(t, midi, level) {
    const g = ctx.createGain();
    const dur = stepDur * 0.85;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(level, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    g.connect(arpBus);

    const a = ctx.createOscillator();
    a.type = 'square';
    a.frequency.setValueAtTime(midiToFreq(midi), t);
    a.detune.setValueAtTime(-6, t);
    a.connect(g);

    const b = ctx.createOscillator();
    b.type = 'triangle';
    b.frequency.setValueAtTime(midiToFreq(midi + 12), t);
    b.detune.setValueAtTime(9, t);
    b.connect(g);

    a.start(t);
    b.start(t);
    a.stop(t + dur + 0.02);
    b.stop(t + dur + 0.02);
    freeOnEnd(a, b, g);
  }

  // -------------------------------------------------------------------------
  // Music scheduler: 25 ms tick, 100 ms lookahead, notes placed on the audio
  // clock so the loop never drifts.
  // -------------------------------------------------------------------------
  function scheduleStep(step, t) {
    const bar = (step / BAR_STEPS) | 0;
    const i = step % BAR_STEPS;
    const lastBar = bar === 3;

    // kick, four on the floor, with a fill on the last bar
    if (i % 4 === 0) playKick(t, 0.95);
    else if (lastBar && i === 14) playKick(t, 0.7);

    // snare on 2 and 4, ghost notes to close the loop
    if (i === 4 || i === 12) playSnare(t, 0.8);
    else if (lastBar && (i === 14 || i === 15)) playSnare(t, i === 15 ? 0.55 : 0.35);

    // hats on every sixteenth, one open hat per bar
    playHat(t, HAT_LEVEL[i], i === 14);

    // acid bass
    const bn = BASS_NOTES[i];
    if (bn !== REST) {
      playBass(t, BASS_ROOT_MIDI + BAR_ROOT_BASS[bar] + bn, BASS_ACCENT[i], BASS_SLIDE[i]);
    } else {
      prevBassSlide = 0;
    }

    // arpeggio over the bar triad
    const shape = ARP_SHAPE[i];
    const third = BAR_THIRD[bar];
    let off;
    if (shape === 0) off = 0;
    else if (shape === 1) off = third;
    else if (shape === 2) off = 7;
    else if (shape === 3) off = 12;
    else off = 12 + third;
    playArp(t, ARP_ROOT_MIDI + BAR_ROOT_ARP[bar] + off, ARP_LEVEL[i] * BAR_ARP_GAIN[bar] * 0.5);
  }

  function schedulerTick() {
    if (!musicOn || !ctx || disposed) return;
    if (ctx.state !== 'running') {
      // Clock is frozen while suspended: keep the cursor glued to the present.
      nextStepTime = ctx.currentTime + 0.06;
      return;
    }
    const horizon = ctx.currentTime + LOOKAHEAD;
    // Recover from a long stall (tab in background) without firing a burst.
    if (nextStepTime < ctx.currentTime - 0.25) nextStepTime = ctx.currentTime + 0.03;
    let guard = 0;
    while (nextStepTime < horizon && guard < 64) {
      scheduleStep(stepIndex, nextStepTime);
      nextStepTime += stepDur;
      stepIndex = (stepIndex + 1) % LOOP_STEPS;
      guard++;
    }
  }

  // -------------------------------------------------------------------------
  // Public surface
  // -------------------------------------------------------------------------
  function applyMasterGain() {
    if (!ctx) return;
    const target = muted ? 0.0001 : Math.max(0.0001, AUDIO.masterGain * volume);
    master.gain.setTargetAtTime(target, now(), 0.05);
  }

  const api = {
    /** Must be called from a user gesture: creates and unlocks the context. */
    resume() {
      if (disposed) return;
      gestureDone = true;
      ensureContext();
      if (!ctx) return;
      if (ctx.state !== 'running') {
        const p = ctx.resume();
        // A rejected resume simply means the gesture was not accepted: update()
        // keeps retrying once a second, so nothing else is needed here.
        if (p && p.catch) p.catch(function onResumeRefused() { resumeRetry = 0.9; });
      }
      nextStepTime = ctx.currentTime + 0.06;
      // startMusic() may have been called before the context existed.
      if (musicOn && !schedulerId) {
        stepIndex = 0;
        prevBassFreq = 0;
        prevBassSlide = 0;
        musicBus.gain.setTargetAtTime(AUDIO.musicGain, ctx.currentTime, 0.25);
        schedulerId = setInterval(schedulerTick, SCHEDULER_MS);
      }
    },

    setMasterVolume(v01) {
      volume = clamp01(v01);
      applyMasterGain();
    },

    toggleMute() {
      muted = !muted;
      applyMasterGain();
      return muted;
    },

    startEngine() {
      engineOn = true;
      if (!live()) return;
      engineBus.gain.setTargetAtTime(AUDIO.engineGain, now(), 0.18);
    },

    stopEngine() {
      engineOn = false;
      if (!live()) return;
      engineBus.gain.setTargetAtTime(0.0001, now(), 0.12);
    },

    /** Engine control input, called once per frame by main.js. */
    setEngine(p) {
      if (!p) return;
      if (typeof p.speed01 === 'number') tSpeed = clamp01(p.speed01);
      if (typeof p.throttle01 === 'number') tThrottle = clamp01(p.throttle01);
      tBoost = p.boost ? 1 : 0;
      tAir = p.airborne ? 1 : 0;
    },

    startMusic() {
      if (musicOn) return;
      musicOn = true;
      if (!live()) return;
      stepIndex = 0;
      prevBassFreq = 0;
      prevBassSlide = 0;
      nextStepTime = now() + 0.08;
      musicBus.gain.setTargetAtTime(AUDIO.musicGain, now(), 0.25);
      if (!schedulerId) schedulerId = setInterval(schedulerTick, SCHEDULER_MS);
    },

    stopMusic() {
      if (!musicOn) return;
      musicOn = false;
      if (schedulerId) {
        clearInterval(schedulerId);
        schedulerId = 0;
      }
      if (!live()) return;
      musicBus.gain.setTargetAtTime(0.0001, now(), 0.12);
    },

    /** step is 3, 2, 1 for the low beeps then 0 for the GO. */
    countdownBeep(step) {
      if (!live()) return;
      const t = now() + 0.01;
      if (step > 0) {
        playTone(t, 69, 0.19, 0.36, 'triangle', sfxBus, 0);
        playTone(t, 57, 0.22, 0.22, 'sine', sfxBus, 0);
        noiseBurst(t, 0.05, 'bandpass', 900, 1.4, 0.1, sfxBus);
      } else {
        sweepTone(t, 660, 1480, 0.55, 0.34, 'sawtooth', sfxBus, 900, 7000);
        playTone(t, 81, 0.5, 0.28, 'sine', sfxBus, 0);
        playTone(t + 0.02, 88, 0.45, 0.18, 'triangle', sfxBus, 6);
        noiseBurst(t, 0.3, 'highpass', 1200, 0.7, 0.16, sfxBus, 6500);
      }
    },

    /**
     * Wall scrape. Retriggered many times a second: it only raises the level of
     * a permanent noise voice, the decay happens in update().
     */
    scrape(intensity01) {
      const v = clamp01(intensity01);
      if (v > scrapeLevel) scrapeLevel = v;
    },

    impact(intensity01) {
      if (!live()) return;
      const v = clamp01(intensity01);
      const t = now() + 0.005;
      // low thud
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(128, t);
      osc.frequency.exponentialRampToValueAtTime(38, t + 0.19);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.24 + v * 0.5, t + 0.006);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.4);
      osc.connect(g);
      g.connect(sfxBus);
      osc.start(t);
      osc.stop(t + 0.42);
      freeOnEnd(osc, g);
      // metallic ring, inharmonic partials through a bandpass
      const ring = ctx.createBiquadFilter();
      ring.type = 'bandpass';
      ring.frequency.setValueAtTime(1400, t);
      ring.Q.value = 1.6;
      const rg = ctx.createGain();
      rg.gain.setValueAtTime(0.0001, t);
      rg.gain.exponentialRampToValueAtTime(0.05 + v * 0.17, t + 0.008);
      rg.gain.exponentialRampToValueAtTime(0.0001, t + 0.5 + v * 0.4);
      ring.connect(rg);
      rg.connect(sfxBus);
      const p0 = ctx.createOscillator();
      const p1 = ctx.createOscillator();
      const p2 = ctx.createOscillator();
      p0.type = 'square';
      p1.type = 'triangle';
      p2.type = 'triangle';
      p0.frequency.setValueAtTime(611, t);
      p1.frequency.setValueAtTime(1244, t);
      p2.frequency.setValueAtTime(1907, t);
      p0.connect(ring);
      p1.connect(ring);
      p2.connect(ring);
      const stopAt = t + 0.95 + v * 0.4;
      p0.start(t); p1.start(t); p2.start(t);
      p0.stop(stopAt); p1.stop(stopAt); p2.stop(stopAt);
      p0.onended = function onended() {
        p0.disconnect(); p1.disconnect(); p2.disconnect();
        ring.disconnect(); rg.disconnect();
      };
      noiseBurst(t, 0.09, 'bandpass', 2600, 0.9, 0.08 + v * 0.2, sfxBus, 700);
    },

    boost() {
      if (!live()) return;
      const t = now() + 0.005;
      // rising whoosh then a falling tail
      noiseBurst(t, 0.34, 'bandpass', 400, 1.1, 0.22, sfxBus, 5200);
      noiseBurst(t + 0.3, 0.65, 'bandpass', 5000, 1.0, 0.14, sfxBus, 700);
      // doppler-ish tonal sweep
      const osc = ctx.createOscillator();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(190, t);
      osc.frequency.exponentialRampToValueAtTime(880, t + 0.3);
      osc.frequency.exponentialRampToValueAtTime(360, t + 0.95);
      const flt = ctx.createBiquadFilter();
      flt.type = 'lowpass';
      flt.Q.value = 6;
      flt.frequency.setValueAtTime(700, t);
      flt.frequency.exponentialRampToValueAtTime(4200, t + 0.32);
      flt.frequency.exponentialRampToValueAtTime(600, t + 0.95);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.26, t + 0.05);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.95);
      osc.connect(flt);
      flt.connect(g);
      g.connect(sfxBus);
      osc.start(t);
      osc.stop(t + 0.98);
      freeOnEnd(osc, flt, g);
    },

    lapChime(isBest) {
      if (!live()) return;
      const t = now() + 0.01;
      const a = isBest ? 88 : 81; // E6 when it is a best lap, A5 otherwise
      const b = isBest ? 95 : 88;
      const lvl = isBest ? 0.3 : 0.22;
      playTone(t, a, 0.5, lvl, 'sine', sfxBus, 0);
      playTone(t, a + 12, 0.35, lvl * 0.35, 'triangle', sfxBus, 5);
      playTone(t + 0.15, b, 0.8, lvl, 'sine', sfxBus, 0);
      playTone(t + 0.15, b + 12, 0.6, lvl * (isBest ? 0.5 : 0.25), 'triangle', sfxBus, -7);
      if (isBest) playTone(t + 0.3, b + 19, 0.7, lvl * 0.22, 'sine', sfxBus, 4);
    },

    explosion() {
      if (!live()) return;
      const t = now() + 0.005;
      noiseBurst(t, 0.06, 'highpass', 3000, 0.8, 0.42, sfxBus);
      noiseBurst(t, 1.35, 'lowpass', 6000, 3.2, 0.5, sfxBus, 95);
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(115, t);
      osc.frequency.exponentialRampToValueAtTime(26, t + 0.8);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.6, t + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 1.0);
      osc.connect(g);
      g.connect(sfxBus);
      osc.start(t);
      osc.stop(t + 1.02);
      freeOnEnd(osc, g);
    },

    finish(won) {
      if (!live()) return;
      const t = now() + 0.02;
      if (won) {
        // Short rising fanfare on the tonic triad (A4 C5 E5 A5), then a held chord.
        const root = 69, third = 72, fifth = 76, octave = 81;
        playTone(t + 0.00, root, 0.22, 0.3, 'sawtooth', sfxBus, 0);
        playTone(t + 0.12, third, 0.22, 0.3, 'sawtooth', sfxBus, 0);
        playTone(t + 0.24, fifth, 0.22, 0.3, 'sawtooth', sfxBus, 0);
        playTone(t + 0.36, octave, 1.5, 0.32, 'sawtooth', sfxBus, 0);
        playTone(t + 0.36, fifth, 1.5, 0.2, 'square', sfxBus, -8);
        playTone(t + 0.36, root, 1.6, 0.18, 'triangle', sfxBus, 6);
        playTone(t + 0.36, 57, 1.7, 0.26, 'sine', sfxBus, 0);
        noiseBurst(t + 0.36, 0.5, 'highpass', 5000, 0.7, 0.1, sfxBus, 9000);
      } else {
        // downbeat sting: a minor second grinding down
        playTone(t, 41, 1.8, 0.3, 'sawtooth', sfxBus, 0);
        playTone(t, 40, 1.8, 0.26, 'sawtooth', sfxBus, 12);
        playTone(t + 0.45, 36, 2.0, 0.28, 'sine', sfxBus, 0);
        noiseBurst(t, 1.2, 'lowpass', 900, 2.0, 0.16, sfxBus, 140);
      }
    },

    /** Per frame smoothing of every continuous parameter. Allocation free. */
    update(dt) {
      if (!ctx || disposed) return;
      const d = dt > 0.1 ? 0.1 : dt < 0 ? 0 : dt;

      if (ctx.state === 'suspended' && gestureDone) {
        // Some browsers suspend on tab switch: try to come back, at most once a second.
        resumeRetry += d;
        if (resumeRetry > 1) {
          resumeRetry = 0;
          const p = ctx.resume();
          if (p && p.catch) p.catch(function onResumeRefused() { resumeRetry = 0.9; });
        }
        return;
      }
      if (ctx.state !== 'running') return;

      sSpeed += (tSpeed - sSpeed) * (1 - Math.exp(-d * 8));
      sThrottle += (tThrottle - sThrottle) * (1 - Math.exp(-d * 12));
      sBoost += (tBoost - sBoost) * (1 - Math.exp(-d * 9));
      sAir += (tAir - sAir) * (1 - Math.exp(-d * 5));

      // Engine pitch: roughly 40 Hz idle to 260 Hz flat out, dropping when airborne.
      const base = (40 + 220 * Math.pow(sSpeed, 0.85)) * (1 - 0.09 * sAir) * (1 + 0.07 * sBoost);
      ramp(oscSaw.frequency, 'saw', base, 0.05);
      ramp(oscSquare.frequency, 'sq', base * 1.006, 0.05);
      ramp(oscSub.frequency, 'sub', base * 0.5, 0.06);

      const cutoff = clamp(
        (230 + 2500 * sThrottle + 2700 * sSpeed * sSpeed + 1500 * sBoost) * (1 - 0.38 * sAir),
        120, 9000,
      );
      ramp(engineFilter.frequency, 'cut', cutoff, 0.05);
      ramp(engineFilter.Q, 'res', 5 + 3 * sThrottle + 5 * sBoost, 0.12);
      ramp(engineLevel.gain, 'drive', 0.45 + 0.4 * sThrottle + 0.25 * sBoost, 0.08);

      // Wind bed rises with speed and opens up when the craft leaves the road.
      ramp(windGain.gain, 'wind', Math.max(0.0002, 0.012 + 0.2 * sSpeed * sSpeed + 0.09 * sAir), 0.09);
      ramp(windFilter.frequency, 'windF', 420 + 2600 * sSpeed, 0.09);

      // Scrape decay, kept in JS so retriggering never restarts a node.
      if (scrapeLevel > 0.0005) scrapeLevel *= Math.exp(-d * 9);
      else scrapeLevel = 0;
      ramp(scrapeGain.gain, 'scrapeG', Math.max(0.0002, 0.3 * scrapeLevel * scrapeLevel + 0.05 * scrapeLevel), 0.02);
      ramp(scrapeFilter.frequency, 'scrapeF', 1200 + 2800 * scrapeLevel, 0.03);
    },

    dispose() {
      if (disposed) return;
      disposed = true;
      if (schedulerId) {
        clearInterval(schedulerId);
        schedulerId = 0;
      }
      musicOn = false;
      engineOn = false;
      if (!ctx) return;
      const t = ctx.currentTime;
      const sources = [oscSaw, oscSquare, oscSub, windSource, scrapeSource];
      for (let i = 0; i < sources.length; i++) {
        const s = sources[i];
        if (!s) continue;
        try {
          s.stop(t);
        } catch (err) {
          // A source can already have been stopped by a previous teardown.
        }
        s.disconnect();
      }
      const nodes = [
        engineFilter, engineLevel, engineBus, windFilter, windGain,
        scrapeFilter, scrapeGain, drumBus, bassBus, arpBus, delaySend,
        delayL, delayR, delayFb, delayMerger, delayWet, musicBus, sfxBus,
        master, compressor,
      ];
      for (let i = 0; i < nodes.length; i++) {
        if (nodes[i]) nodes[i].disconnect();
      }
      const dying = ctx;
      ctx = null;
      const closing = dying.close();
      // close() rejects if the context was already closed by the browser.
      if (closing && closing.catch) closing.catch(function onCloseFailed() { dying.onstatechange = null; });
    },

    /** Read only handle, handy from the debug console. */
    get context() {
      return ctx;
    },
  };

  return api;
}
