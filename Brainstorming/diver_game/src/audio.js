/**
 * ABYSSE - audio.js
 *
 * Pure WebAudio, everything synthesised at runtime. No files, no fetch, no
 * external assets. The only import allowed is ./config.js.
 *
 * createAudio() is safe to call before any user gesture: it builds nothing
 * audible. init() (called from a click / keypress) creates the AudioContext
 * and the whole graph. Every play() before init() is a silent no-op.
 *
 * Master chain:
 *   voice buses -> masterGain -> underwater lowpass -> compressor -> output
 * with two parallel convolver reverbs (short "room", long "cave") whose
 * returns re-enter before the lowpass so the tails get muffled with depth.
 *
 * The underwater lowpass is the signature trick: near 18 kHz at the surface,
 * sweeping down toward roughly 700 Hz in the trench, always moved with
 * setTargetAtTime so nothing ever clicks.
 */

import {
  AUDIO,
  BIOMES,
  BIOME_INFO,
  clamp,
  clamp01,
  lerp,
  makeRandom,
} from './config.js';

// Maximum simultaneous one-shot voices. Beyond this the quietest / oldest
// voice is faded out and dropped.
const MAX_VOICES = 24;

// Pentatonic set for the generative pad (semitones above the root).
const PENTA = [0, 2, 4, 7, 9, 12, 14, 16];

export function createAudio() {
  // ---------------------------------------------------------------------
  // State (nothing here touches the audio hardware yet)
  // ---------------------------------------------------------------------

  let ac = null;            // AudioContext, created in init()
  let ready = false;        // graph fully built
  let mutedFlag = false;

  // Master chain nodes
  let masterGain = null;
  let underLowpass = null;
  let compressor = null;

  // Buses
  let sfxBus = null;
  let ambBus = null;
  let musicBus = null;

  // Reverbs
  let roomConvolver = null;
  let caveConvolver = null;
  let roomReturn = null;
  let caveReturn = null;

  // Shared buffers
  let whiteBuffer = null;
  let pinkBuffer = null;

  // Persistent (looping) sources and gains for the ambience layers
  const persistentSources = [];   // sources started at init, stopped at dispose

  let bedGain = null;             // underwater pressure bed
  let bedFilter = null;
  let droneGain = null;           // low underwater drone
  let droneOscA = null;
  let droneOscB = null;
  let windGain = null;            // above water wind
  let windFilter = null;
  let surfGain = null;            // above water surf
  let tensionGain = null;         // threat layer
  let tensionLfoDepth = null;
  let tensionLfo = null;
  let tensionOscA = null;
  let tensionOscB = null;
  let tensionFilter = null;
  let engineGain = null;          // submarine drone
  let engineFilter = null;
  let musicFilter = null;

  // One-shot voice bookkeeping
  const voices = [];

  // Ambience timers, all in seconds, driven by update(dt, ctx)
  let breathTimer = 1.2;          // regulator cycle
  let bubbleTimer = 2.0;          // random ambient bubbles
  let creakTimer = 9.0;           // distant creaks and moans
  let gullTimer = 5.0;            // seabirds above water
  let beepTimer = 0;              // low oxygen warning
  let heartTimer = 0;             // low health heartbeat
  let musicTimer = 2.5;           // next generative pad note

  let engineManual = false;       // toggled by play('engine')

  // Deterministic rng for the music layer, plain Math.random for foley
  const musicRng = makeRandom(48271);
  let musicStep = 0;

  // Last known game context, so triggers between updates stay coherent
  let lastCtx = {
    depth: 0,
    biome: BIOMES.LAGOON,
    moving: false,
    threat: 0,
    aboveWater: true,
    insideSub: false,
    oxygen01: 1,
    health01: 1,
  };

  // ---------------------------------------------------------------------
  // Small helpers
  // ---------------------------------------------------------------------

  function now() {
    return ac ? ac.currentTime : 0;
  }

  function rand(lo, hi) {
    return lo + Math.random() * (hi - lo);
  }

  /** Simple linear attack then exponential-ish release on a gain param. */
  function env(param, t, peak, attack, hold, release) {
    param.setValueAtTime(0.0001, t);
    param.linearRampToValueAtTime(Math.max(0.0001, peak), t + attack);
    if (hold > 0) {
      param.setValueAtTime(Math.max(0.0001, peak), t + attack + hold);
    }
    param.exponentialRampToValueAtTime(0.0001, t + attack + hold + release);
  }

  /** White or pink noise buffer, generated once and reused by every source. */
  function makeNoiseBuffer(pink) {
    const seconds = 2;
    const len = Math.floor(ac.sampleRate * seconds);
    const buf = ac.createBuffer(1, len, ac.sampleRate);
    const data = buf.getChannelData(0);
    if (!pink) {
      for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
      return buf;
    }
    // Paul Kellet pink noise approximation
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
    for (let i = 0; i < len; i++) {
      const w = Math.random() * 2 - 1;
      b0 = 0.99886 * b0 + w * 0.0555179;
      b1 = 0.99332 * b1 + w * 0.0750759;
      b2 = 0.969 * b2 + w * 0.153852;
      b3 = 0.8665 * b3 + w * 0.3104856;
      b4 = 0.55 * b4 + w * 0.5329522;
      b5 = -0.7616 * b5 - w * 0.016898;
      const out = b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362;
      b6 = w * 0.115926;
      data[i] = out * 0.11;
    }
    return buf;
  }

  /** Synthesised impulse response: decaying noise, stereo. */
  function makeImpulse(seconds, decayPower) {
    const len = Math.max(1, Math.floor(ac.sampleRate * seconds));
    const buf = ac.createBuffer(2, len, ac.sampleRate);
    for (let ch = 0; ch < 2; ch++) {
      const data = buf.getChannelData(ch);
      for (let i = 0; i < len; i++) {
        const p = 1 - i / len;
        data[i] = (Math.random() * 2 - 1) * Math.pow(p, decayPower);
      }
    }
    return buf;
  }

  /** Waveshaper curve for a soft-clip distortion. */
  function makeDistortionCurve(amount) {
    const n = 512;
    const curve = new Float32Array(n);
    const k = amount;
    for (let i = 0; i < n; i++) {
      const x = (i * 2) / n - 1;
      curve[i] = ((1 + k) * x) / (1 + k * Math.abs(x));
    }
    return curve;
  }

  /** Noise source from a shared buffer, looping, with playback rate. */
  function noiseSource(pink, rate) {
    const src = ac.createBufferSource();
    src.buffer = pink ? pinkBuffer : whiteBuffer;
    src.loop = true;
    src.loopStart = 0;
    src.loopEnd = src.buffer.duration;
    if (rate && rate !== 1) src.playbackRate.value = rate;
    return src;
  }

  /** Oscillator with an optional exponential pitch sweep. */
  function osc(type, f0, t, f1, sweepEnd) {
    const o = ac.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(Math.max(1, f0), t);
    if (f1 !== undefined && sweepEnd !== undefined) {
      o.frequency.exponentialRampToValueAtTime(Math.max(1, f1), sweepEnd);
    }
    return o;
  }

  /** Biquad with an optional frequency sweep. */
  function filter(type, f0, q, t, f1, sweepEnd) {
    const f = ac.createBiquadFilter();
    f.type = type;
    f.frequency.setValueAtTime(Math.max(10, f0), t);
    if (q !== undefined) f.Q.value = q;
    if (f1 !== undefined && sweepEnd !== undefined) {
      f.frequency.exponentialRampToValueAtTime(Math.max(10, f1), sweepEnd);
    }
    return f;
  }

  // ---------------------------------------------------------------------
  // One-shot voice management
  // ---------------------------------------------------------------------

  function removeVoice(v) {
    const i = voices.indexOf(v);
    if (i >= 0) voices.splice(i, 1);
    if (v.timer) clearTimeout(v.timer);
    try { v.gain.disconnect(); } catch (e) { /* already gone */ }
  }

  /**
   * Create the output gain of a one-shot voice, wired to the sfx bus (and
   * optionally to a reverb send), registered in the voice list with an end
   * time so it disconnects itself after its tail.
   */
  function openVoice(opts, duration, verbAmount, verbBus) {
    const t = now();
    const g = ac.createGain();
    const vol = clamp(opts && opts.volume !== undefined ? opts.volume : 1, 0, 4);
    g.gain.value = vol;

    let tail = g;
    if (opts && opts.pan !== undefined && ac.createStereoPanner) {
      const p = ac.createStereoPanner();
      p.pan.value = clamp(opts.pan, -1, 1);
      g.connect(p);
      tail = p;
    }
    tail.connect(sfxBus);

    if (verbAmount > 0 && verbBus) {
      const send = ac.createGain();
      send.gain.value = verbAmount;
      tail.connect(send);
      send.connect(verbBus);
    }

    const v = { gain: g, end: t + duration, vol };
    voices.push(v);
    v.timer = setTimeout(() => removeVoice(v), (duration + 0.25) * 1000);

    // Cap the polyphony: fade out and drop the quietest, oldest voice
    if (voices.length > MAX_VOICES) {
      let victim = voices[0];
      for (const cand of voices) {
        if (cand === v) continue;
        if (cand.vol < victim.vol - 0.01 ||
            (Math.abs(cand.vol - victim.vol) <= 0.01 && cand.end < victim.end)) {
          victim = cand;
        }
      }
      if (victim !== v) {
        victim.gain.gain.setTargetAtTime(0, t, 0.015);
        if (victim.timer) clearTimeout(victim.timer);
        victim.timer = setTimeout(() => removeVoice(victim), 90);
      }
    }
    return g;
  }

  /** Start a source and schedule its stop, so it can be garbage collected. */
  function fire(src, t, stopAt) {
    src.start(t);
    src.stop(stopAt);
  }

  // ---------------------------------------------------------------------
  // Reusable micro instruments
  // ---------------------------------------------------------------------

  /** A single tonal blip: type, frequency (with optional glide), envelope. */
  function blip(out, t, type, f0, f1, dur, vol, attack) {
    const a = attack !== undefined ? attack : 0.005;
    const o = osc(type, f0, t, f1, t + dur);
    const g = ac.createGain();
    env(g.gain, t, vol, a, 0, dur - a);
    o.connect(g);
    g.connect(out);
    fire(o, t, t + dur + 0.05);
  }

  /** A filtered noise burst: the workhorse of every impact and splash. */
  function burst(out, t, dur, vol, type, f0, f1, q, attack, pink) {
    const src = noiseSource(!!pink, 1);
    const f = filter(type, f0, q || 1, t, f1, t + dur);
    const g = ac.createGain();
    env(g.gain, t, vol, attack !== undefined ? attack : 0.004, 0, dur);
    src.connect(f);
    f.connect(g);
    g.connect(out);
    fire(src, t, t + dur + 0.1);
  }

  /** A tiny click, mostly transient. */
  function click(out, t, vol, freq) {
    burst(out, t, 0.018, vol, 'bandpass', freq, freq, 4, 0.001, false);
  }

  /** One rising bubble "bloop": bandpassed noise plus a sine chirp. */
  function bubbleAt(out, t, vol, pitchMul) {
    const m = (pitchMul || 1) * rand(0.75, 1.35);
    const dur = rand(0.05, 0.13);
    burst(out, t, dur, vol * 0.7, 'bandpass',
      520 * m, 2600 * m, 6, 0.004, false);
    const o = osc('sine', 380 * m, t, 1400 * m * rand(1.1, 1.8), t + dur);
    const g = ac.createGain();
    env(g.gain, t, vol * 0.5, 0.006, 0, dur - 0.006);
    o.connect(g);
    g.connect(out);
    fire(o, t, t + dur + 0.05);
  }

  /** A low body thump: sine with a fast downward glide. */
  function thump(out, t, f0, f1, dur, vol) {
    const o = osc('sine', f0, t, f1, t + dur);
    const g = ac.createGain();
    env(g.gain, t, vol, 0.004, 0, dur);
    o.connect(g);
    g.connect(out);
    fire(o, t, t + dur + 0.05);
  }

  // ---------------------------------------------------------------------
  // Sound builders. Each takes (t, out, rate) and stays within the duration
  // declared in the registry below.
  // ---------------------------------------------------------------------

  function sHarpoon(t, out, r) {
    // Compressed air thump
    thump(out, t, 150 * r, 42 * r, 0.22, 0.95);
    burst(out, t, 0.16, 0.8, 'lowpass', 3800 * r, 500 * r, 0.7, 0.002, false);
    // Metallic whoosh
    burst(out, t + 0.015, 0.3, 0.55, 'bandpass', 700 * r, 2600 * r, 2.2, 0.02, false);
    // Whipping line: fluttering high band
    const src = noiseSource(false, 1);
    const f = filter('bandpass', 2900 * r, 5, t);
    const g = ac.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(0.3, t + 0.05);
    const lfo = osc('sine', 26, t);
    const lfoAmp = ac.createGain();
    lfoAmp.gain.value = 0.16;
    lfo.connect(lfoAmp);
    lfoAmp.connect(g.gain);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.45);
    src.connect(f); f.connect(g); g.connect(out);
    fire(src, t, t + 0.5);
    fire(lfo, t, t + 0.5);
  }

  function sNeedle(t, out, r) {
    // Slight random detune so bursts never sound robotic
    const m = r * rand(0.92, 1.1);
    click(out, t, 0.8, 2400 * m);
    burst(out, t + 0.004, 0.08, 0.55, 'highpass', 1900 * m, 3400 * m, 1.4, 0.002, false);
    thump(out, t, 300 * m, 130 * m, 0.06, 0.3);
  }

  function sShock(t, out, r) {
    // Crackle: a scatter of tiny bandpassed bursts with random gain
    for (let i = 0; i < 9; i++) {
      const tt = t + i * rand(0.018, 0.034);
      burst(out, tt, rand(0.012, 0.03), rand(0.25, 0.7),
        'bandpass', rand(1500, 3600) * r, rand(2000, 4200) * r, 8, 0.001, false);
    }
    // Buzzy core
    const o = osc('square', 110 * r, t);
    const dist = ac.createWaveShaper();
    dist.curve = makeDistortionCurve(30);
    const f = filter('bandpass', 900 * r, 1.6, t);
    const g = ac.createGain();
    env(g.gain, t, 0.35, 0.005, 0.12, 0.15);
    o.connect(dist); dist.connect(f); f.connect(g); g.connect(out);
    fire(o, t, t + 0.35);
    // Low thump
    thump(out, t, 130 * r, 48 * r, 0.2, 0.7);
  }

  function sReload(t, out, r) {
    click(out, t, 0.55, 1500 * r);
    click(out, t + 0.13, 0.6, 900 * r);
    // Spring: wobbling triangle
    const o = osc('triangle', 340 * r, t + 0.18);
    o.frequency.exponentialRampToValueAtTime(820 * r, t + 0.3);
    o.frequency.exponentialRampToValueAtTime(420 * r, t + 0.42);
    const g = ac.createGain();
    env(g.gain, t + 0.18, 0.3, 0.01, 0.1, 0.16);
    o.connect(g); g.connect(out);
    fire(o, t + 0.18, t + 0.5);
    click(out, t + 0.46, 0.7, 1200 * r);
  }

  function sDryfire(t, out, r) {
    click(out, t, 0.7, 1700 * r);
    burst(out, t + 0.01, 0.06, 0.3, 'lowpass', 700 * r, 250 * r, 0.8, 0.002, false);
  }

  function sHit(t, out, r) {
    // Wet thud
    thump(out, t, 190 * r, 62 * r, 0.16, 0.8);
    burst(out, t, 0.11, 0.6, 'lowpass', 900 * r, 260 * r, 0.7, 0.003, true);
    bubbleAt(out, t + 0.03, 0.25, 0.8);
  }

  function sHitArmor(t, out, r) {
    // Harder, brighter clack on shell or carapace
    click(out, t, 0.9, 2600 * r);
    burst(out, t, 0.07, 0.6, 'bandpass', 2100 * r, 1400 * r, 3.5, 0.001, false);
    // Inharmonic metallic ring
    blip(out, t, 'square', 1320 * r, 1180 * r, 0.12, 0.18, 0.002);
    thump(out, t, 240 * r, 120 * r, 0.07, 0.4);
  }

  function sKill(t, out, r) {
    // Lower, longer, with a downward pitch sweep
    thump(out, t, 230 * r, 40 * r, 0.55, 0.95);
    burst(out, t, 0.4, 0.55, 'lowpass', 1200 * r, 180 * r, 0.8, 0.004, true);
    const o = osc('sine', 320 * r, t, 55 * r, t + 0.5);
    const g = ac.createGain();
    env(g.gain, t, 0.4, 0.01, 0.05, 0.45);
    o.connect(g); g.connect(out);
    fire(o, t, t + 0.6);
    for (let i = 0; i < 4; i++) bubbleAt(out, t + 0.1 + i * 0.09, 0.2, 0.7);
  }

  function sPickup(t, out, r) {
    blip(out, t, 'sine', 660 * r, 700 * r, 0.1, 0.5);
    blip(out, t + 0.09, 'sine', 990 * r, 1080 * r, 0.16, 0.5);
    bubbleAt(out, t + 0.02, 0.35, 1.2);
  }

  function sDeposit(t, out, r) {
    // Solid mechanical clunk
    thump(out, t, 170 * r, 78 * r, 0.12, 0.8);
    click(out, t, 0.6, 800 * r);
    click(out, t + 0.09, 0.4, 1100 * r);
    // Confirmation tone
    blip(out, t + 0.16, 'triangle', 520 * r, 524 * r, 0.22, 0.4, 0.01);
  }

  function sMedal(t, out, r) {
    // Warm triumphant arpeggio, heavy on the room reverb
    const notes = [523.25, 659.25, 783.99, 1046.5];
    for (let i = 0; i < notes.length; i++) {
      const tt = t + i * 0.11;
      blip(out, tt, 'triangle', notes[i] * r, notes[i] * r * 1.002, 0.5, 0.4, 0.01);
      blip(out, tt, 'sine', notes[i] * 0.5 * r, notes[i] * 0.5 * r, 0.55, 0.22, 0.015);
    }
    blip(out, t + 0.48, 'sine', 1568 * r, 1568 * r, 0.7, 0.2, 0.02);
  }

  function sSkin(t, out, r) {
    // Shimmering upward sweep
    for (let i = 0; i < 4; i++) {
      const f0 = (700 + i * 260) * r;
      const o = osc('sine', f0, t + i * 0.05, f0 * 3.2, t + 0.7);
      const g = ac.createGain();
      env(g.gain, t + i * 0.05, 0.2, 0.08, 0.15, 0.5);
      o.connect(g); g.connect(out);
      fire(o, t + i * 0.05, t + 0.9);
    }
    burst(out, t, 0.8, 0.25, 'bandpass', 1200 * r, 5200 * r, 3, 0.1, false);
  }

  function sUi(t, out, r) {
    blip(out, t, 'sine', 880 * r, 880 * r, 0.06, 0.35);
  }

  function sUiConfirm(t, out, r) {
    blip(out, t, 'sine', 660 * r, 660 * r, 0.07, 0.35);
    blip(out, t + 0.08, 'sine', 880 * r, 900 * r, 0.1, 0.35);
  }

  function sUiBack(t, out, r) {
    blip(out, t, 'sine', 660 * r, 660 * r, 0.07, 0.35);
    blip(out, t + 0.08, 'sine', 440 * r, 430 * r, 0.1, 0.35);
  }

  function sBubble(t, out, r) {
    bubbleAt(out, t, 0.5, r);
  }

  function sSplashIn(t, out, r) {
    // Darker and heavier: big broadband hit swept down
    thump(out, t, 130 * r, 40 * r, 0.3, 0.9);
    burst(out, t, 0.55, 0.9, 'lowpass', 6500 * r, 380 * r, 0.8, 0.004, false);
    burst(out, t + 0.05, 0.5, 0.4, 'bandpass', 900 * r, 320 * r, 1.2, 0.02, true);
    for (let i = 0; i < 6; i++) bubbleAt(out, t + 0.08 + i * 0.07, 0.25, 0.9);
  }

  function sSplashOut(t, out, r) {
    // Brighter, lighter, sweeping up into the air
    burst(out, t, 0.4, 0.75, 'highpass', 500 * r, 2400 * r, 0.9, 0.004, false);
    burst(out, t + 0.03, 0.35, 0.4, 'bandpass', 1400 * r, 3600 * r, 1.5, 0.02, false);
    thump(out, t, 160 * r, 90 * r, 0.12, 0.35);
    for (let i = 0; i < 4; i++) bubbleAt(out, t + 0.05 + i * 0.06, 0.2, 1.4);
  }

  function sSharkAlert(t, out, r) {
    // Dread stinger: low detuned cluster with a slow swell
    const base = 66 * r;
    const detunes = [1, 1.028, 0.972, 1.5];
    for (let i = 0; i < detunes.length; i++) {
      const o = osc('sawtooth', base * detunes[i], t);
      const f = filter('lowpass', 300 * r, 0.8, t, 700 * r, t + 1.3);
      const g = ac.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.linearRampToValueAtTime(0.22, t + 1.1);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 2.2);
      o.connect(f); f.connect(g); g.connect(out);
      fire(o, t, t + 2.3);
    }
    // A dissonant high whine on top
    const w = osc('sine', 620 * r, t, 660 * r, t + 1.4);
    const wg = ac.createGain();
    env(wg.gain, t + 0.3, 0.08, 0.7, 0.2, 0.9);
    w.connect(wg); wg.connect(out);
    fire(w, t + 0.3, t + 2.3);
  }

  function sBite(t, out, r) {
    // Violent crunch: distorted noise plus a low impact
    const src = noiseSource(false, 1);
    const dist = ac.createWaveShaper();
    dist.curve = makeDistortionCurve(60);
    const f = filter('lowpass', 2600 * r, 1, t, 300 * r, t + 0.24);
    const g = ac.createGain();
    env(g.gain, t, 0.9, 0.003, 0.04, 0.22);
    src.connect(dist); dist.connect(f); f.connect(g); g.connect(out);
    fire(src, t, t + 0.35);
    thump(out, t, 140 * r, 34 * r, 0.3, 1.0);
    // Secondary snap
    click(out, t + 0.06, 0.7, 1000 * r);
    burst(out, t + 0.07, 0.1, 0.5, 'bandpass', 700 * r, 350 * r, 2, 0.002, true);
  }

  function sSting(t, out, r) {
    // Sharp bright zing with a nasty edge
    const o = osc('sawtooth', 2600 * r, t, 4400 * r, t + 0.08);
    o.frequency.exponentialRampToValueAtTime(1800 * r, t + 0.2);
    const dist = ac.createWaveShaper();
    dist.curve = makeDistortionCurve(18);
    const f = filter('highpass', 1400 * r, 1.2, t);
    const g = ac.createGain();
    env(g.gain, t, 0.5, 0.003, 0.02, 0.18);
    o.connect(dist); dist.connect(f); f.connect(g); g.connect(out);
    fire(o, t, t + 0.25);
    click(out, t, 0.5, 3200 * r);
  }

  function sLowOxygen(t, out, r) {
    const o = osc('square', 990 * r, t);
    const f = filter('lowpass', 2400 * r, 0.7, t);
    const g = ac.createGain();
    env(g.gain, t, 0.28, 0.008, 0.09, 0.05);
    o.connect(f); f.connect(g); g.connect(out);
    fire(o, t, t + 0.2);
  }

  function sHeartbeat(t, out, r) {
    thump(out, t, 78 * r, 46 * r, 0.16, 0.85);
    thump(out, t + 0.3, 70 * r, 42 * r, 0.18, 0.65);
  }

  function sSonar(t, out, r) {
    // Classic ping: pure tone with a tiny downward tail, big cave reverb
    const o = osc('sine', 1560 * r, t, 1470 * r, t + 0.3);
    const g = ac.createGain();
    env(g.gain, t, 0.5, 0.004, 0.05, 0.4);
    o.connect(g); g.connect(out);
    fire(o, t, t + 0.5);
    blip(out, t, 'sine', 3120 * r, 2950 * r, 0.15, 0.1, 0.004);
  }

  function sScanDone(t, out, r) {
    blip(out, t, 'sine', 1320 * r, 1320 * r, 0.3, 0.3, 0.005);
    blip(out, t + 0.07, 'sine', 1980 * r, 1990 * r, 0.45, 0.22, 0.005);
  }

  function sSurface(t, out, r) {
    // Breaking the surface: water draining off the mask
    const src = noiseSource(false, 1);
    const f = filter('bandpass', 1300 * r, 1.1, t, 320 * r, t + 1.2);
    const g = ac.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(0.5, t + 0.05);
    const lfo = osc('sine', 9, t);
    const lfoAmp = ac.createGain();
    lfoAmp.gain.value = 0.2;
    lfo.connect(lfoAmp); lfoAmp.connect(g.gain);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 1.3);
    src.connect(f); f.connect(g); g.connect(out);
    fire(src, t, t + 1.4);
    fire(lfo, t, t + 1.4);
    for (let i = 0; i < 5; i++) bubbleAt(out, t + 0.1 + i * 0.12, 0.2, 1.3);
  }

  function sFootstep(t, out, r) {
    const m = r * rand(0.9, 1.12);
    burst(out, t, 0.09, 0.45, 'lowpass', 950 * m, 320 * m, 0.8, 0.004, true);
    click(out, t + 0.01, 0.15, 600 * m);
  }

  function sGull(t, out, r) {
    // Formant-ish seabird: two filtered sweeps
    const cry = (tt, f0, f1, f2, dur, vol) => {
      const o = osc('sawtooth', f0, tt, f1, tt + dur * 0.4);
      o.frequency.exponentialRampToValueAtTime(f2, tt + dur);
      const vib = osc('sine', 34, tt);
      const vibAmp = ac.createGain();
      vibAmp.gain.value = f0 * 0.03;
      vib.connect(vibAmp); vibAmp.connect(o.frequency);
      const f = filter('bandpass', 2500 * r, 2.4, tt);
      const g = ac.createGain();
      env(g.gain, tt, vol, 0.03, dur * 0.4, dur * 0.55);
      o.connect(f); f.connect(g); g.connect(out);
      fire(o, tt, tt + dur + 0.05);
      fire(vib, tt, tt + dur + 0.05);
    };
    cry(t, 1150 * r, 1550 * r, 900 * r, 0.32, 0.28);
    cry(t + 0.4, 1300 * r, 1650 * r, 950 * r, 0.26, 0.22);
  }

  // Registry: builder, worst case duration (for the voice cap and cleanup),
  // reverb send amount and which reverb it feeds.
  // verb: 0 none, otherwise send level; type: 'room' | 'cave'
  let SOUNDS = null;
  function buildRegistry() {
    SOUNDS = {
      harpoon:   { fn: sHarpoon,   dur: 0.6,  verb: 0.25, type: 'room' },
      needle:    { fn: sNeedle,    dur: 0.15, verb: 0.12, type: 'room' },
      shock:     { fn: sShock,     dur: 0.45, verb: 0.2,  type: 'room' },
      reload:    { fn: sReload,    dur: 0.6,  verb: 0.1,  type: 'room' },
      dryfire:   { fn: sDryfire,   dur: 0.12, verb: 0.08, type: 'room' },
      hit:       { fn: sHit,       dur: 0.3,  verb: 0.15, type: 'room' },
      hitArmor:  { fn: sHitArmor,  dur: 0.2,  verb: 0.18, type: 'room' },
      kill:      { fn: sKill,      dur: 0.8,  verb: 0.3,  type: 'cave' },
      pickup:    { fn: sPickup,    dur: 0.35, verb: 0.15, type: 'room' },
      deposit:   { fn: sDeposit,   dur: 0.45, verb: 0.15, type: 'room' },
      medal:     { fn: sMedal,     dur: 1.3,  verb: 0.45, type: 'cave' },
      skin:      { fn: sSkin,      dur: 1.0,  verb: 0.35, type: 'cave' },
      ui:        { fn: sUi,        dur: 0.1,  verb: 0,    type: 'room' },
      uiConfirm: { fn: sUiConfirm, dur: 0.25, verb: 0,    type: 'room' },
      uiBack:    { fn: sUiBack,    dur: 0.25, verb: 0,    type: 'room' },
      bubble:    { fn: sBubble,    dur: 0.2,  verb: 0.05, type: 'room' },
      splashIn:  { fn: sSplashIn,  dur: 0.9,  verb: 0.2,  type: 'room' },
      splashOut: { fn: sSplashOut, dur: 0.7,  verb: 0.2,  type: 'room' },
      sharkAlert:{ fn: sSharkAlert,dur: 2.4,  verb: 0.4,  type: 'cave' },
      bite:      { fn: sBite,      dur: 0.45, verb: 0.2,  type: 'room' },
      sting:     { fn: sSting,     dur: 0.3,  verb: 0.15, type: 'room' },
      lowOxygen: { fn: sLowOxygen, dur: 0.25, verb: 0,    type: 'room' },
      heartbeat: { fn: sHeartbeat, dur: 0.6,  verb: 0.1,  type: 'room' },
      sonar:     { fn: sSonar,     dur: 0.6,  verb: 0.7,  type: 'cave' },
      scanDone:  { fn: sScanDone,  dur: 0.6,  verb: 0.25, type: 'room' },
      engine:    { fn: null,       dur: 0,    verb: 0,    type: 'room' },
      surface:   { fn: sSurface,   dur: 1.6,  verb: 0.15, type: 'room' },
      footstep:  { fn: sFootstep,  dur: 0.15, verb: 0.06, type: 'room' },
      gull:      { fn: sGull,      dur: 0.8,  verb: 0.2,  type: 'cave' },
    };
  }

  // ---------------------------------------------------------------------
  // Graph construction
  // ---------------------------------------------------------------------

  function buildMasterChain() {
    masterGain = ac.createGain();
    masterGain.gain.value = mutedFlag ? 0 : AUDIO.masterVolume;

    underLowpass = ac.createBiquadFilter();
    underLowpass.type = 'lowpass';
    underLowpass.frequency.value = 18000;
    underLowpass.Q.value = 0.4;

    compressor = ac.createDynamicsCompressor();
    compressor.threshold.value = -16;
    compressor.knee.value = 18;
    compressor.ratio.value = 5;
    compressor.attack.value = 0.004;
    compressor.release.value = 0.24;

    masterGain.connect(underLowpass);
    underLowpass.connect(compressor);
    compressor.connect(ac.destination);

    // Buses
    sfxBus = ac.createGain();
    sfxBus.gain.value = AUDIO.sfxVolume;
    sfxBus.connect(masterGain);

    ambBus = ac.createGain();
    ambBus.gain.value = AUDIO.sfxVolume * 0.9;
    ambBus.connect(masterGain);

    musicBus = ac.createGain();
    musicBus.gain.value = AUDIO.musicVolume;
    musicBus.connect(masterGain);

    // Reverbs: short room and long cave, returns before the lowpass so the
    // tails get muffled with everything else.
    roomConvolver = ac.createConvolver();
    roomConvolver.buffer = makeImpulse(0.7, 2.4);
    roomReturn = ac.createGain();
    roomReturn.gain.value = 0.6;
    roomConvolver.connect(roomReturn);
    roomReturn.connect(masterGain);

    caveConvolver = ac.createConvolver();
    caveConvolver.buffer = makeImpulse(3.6, 3.2);
    caveReturn = ac.createGain();
    caveReturn.gain.value = 0.55;
    caveConvolver.connect(caveReturn);
    caveReturn.connect(masterGain);
  }

  function startLoop(src) {
    src.start();
    persistentSources.push(src);
    return src;
  }

  function buildAmbience() {
    const t = now();

    // -- Underwater pressure bed: pink noise, dark filter, biome tinted -----
    const bedSrc = noiseSource(true, 0.7);
    bedFilter = filter('lowpass', 700, 0.6, t);
    bedGain = ac.createGain();
    bedGain.gain.value = 0;
    bedSrc.connect(bedFilter);
    bedFilter.connect(bedGain);
    bedGain.connect(ambBus);
    startLoop(bedSrc);

    // Slow wobble on the bed filter so the pressure feels alive
    const bedLfo = osc('sine', 0.07, t);
    const bedLfoAmp = ac.createGain();
    bedLfoAmp.gain.value = 120;
    bedLfo.connect(bedLfoAmp);
    bedLfoAmp.connect(bedFilter.frequency);
    startLoop(bedLfo);

    // -- Low drone: two detuned sines, deeper biomes lean on it harder ------
    droneOscA = osc('sine', 52, t);
    droneOscB = osc('sine', 52.7, t);
    const droneFilter = filter('lowpass', 160, 0.7, t);
    droneGain = ac.createGain();
    droneGain.gain.value = 0;
    droneOscA.connect(droneFilter);
    droneOscB.connect(droneFilter);
    droneFilter.connect(droneGain);
    droneGain.connect(ambBus);
    startLoop(droneOscA);
    startLoop(droneOscB);

    // -- Above water: wind ---------------------------------------------------
    const windSrc = noiseSource(true, 1);
    windFilter = filter('bandpass', 420, 0.6, t);
    windGain = ac.createGain();
    windGain.gain.value = 0;
    windSrc.connect(windFilter);
    windFilter.connect(windGain);
    windGain.connect(ambBus);
    startLoop(windSrc);

    const windLfo = osc('sine', 0.16, t);
    const windLfoAmp = ac.createGain();
    windLfoAmp.gain.value = 190;
    windLfo.connect(windLfoAmp);
    windLfoAmp.connect(windFilter.frequency);
    startLoop(windLfo);

    // -- Above water: gentle surf, amplitude swells on a slow LFO -----------
    const surfSrc = noiseSource(false, 0.8);
    const surfFilter = filter('lowpass', 950, 0.7, t);
    surfGain = ac.createGain();
    surfGain.gain.value = 0;
    surfSrc.connect(surfFilter);
    surfFilter.connect(surfGain);
    surfGain.connect(ambBus);
    startLoop(surfSrc);

    const surfLfo = osc('sine', 0.09, t);
    const surfLfoAmp = ac.createGain();
    surfLfoAmp.gain.value = 0.05;
    surfLfo.connect(surfLfoAmp);
    surfLfoAmp.connect(surfGain.gain);
    startLoop(surfLfo);

    // -- Threat tension layer: detuned low cluster pulsing with an LFO ------
    tensionOscA = osc('sawtooth', 55, t);
    tensionOscB = osc('sawtooth', 56.6, t);
    tensionFilter = filter('lowpass', 260, 1.1, t);
    tensionGain = ac.createGain();
    tensionGain.gain.value = 0;
    tensionOscA.connect(tensionFilter);
    tensionOscB.connect(tensionFilter);
    tensionFilter.connect(tensionGain);
    tensionGain.connect(ambBus);
    startLoop(tensionOscA);
    startLoop(tensionOscB);

    tensionLfo = osc('sine', 1.4, t);
    tensionLfoDepth = ac.createGain();
    tensionLfoDepth.gain.value = 0;
    tensionLfo.connect(tensionLfoDepth);
    tensionLfoDepth.connect(tensionGain.gain);
    startLoop(tensionLfo);

    // -- Submarine engine drone ---------------------------------------------
    const engA = osc('sawtooth', 55, t);
    const engB = osc('sawtooth', 55.8, t);
    const engSub = osc('sine', 27.5, t);
    engineFilter = filter('lowpass', 230, 1.0, t);
    engineGain = ac.createGain();
    engineGain.gain.value = 0;
    engA.connect(engineFilter);
    engB.connect(engineFilter);
    engSub.connect(engineFilter);
    engineFilter.connect(engineGain);
    engineGain.connect(ambBus);
    startLoop(engA);
    startLoop(engB);
    startLoop(engSub);

    const engLfo = osc('sine', 0.6, t);
    const engLfoAmp = ac.createGain();
    engLfoAmp.gain.value = 45;
    engLfo.connect(engLfoAmp);
    engLfoAmp.connect(engineFilter.frequency);
    startLoop(engLfo);

    // -- Music tone control ---------------------------------------------------
    musicFilter = filter('lowpass', 1800, 0.5, t);
    musicFilter.connect(musicBus);
  }

  // ---------------------------------------------------------------------
  // Regulator breathing (the signature sound)
  // ---------------------------------------------------------------------

  function triggerBreath(cx) {
    if (!ready || cx.aboveWater || cx.insideSub) return;
    const t = now();
    const strained = cx.oxygen01 < 0.3;
    const vol = strained ? 0.55 : 0.42;

    // Inhale: pressurised hiss through the regulator, a touch of body
    const g = openVoice({ volume: 1 }, 2.2, 0.06, roomConvolver);
    const src = noiseSource(false, 1);
    const bp = filter('bandpass', 1500, 0.9, t, 900, t + 0.9);
    const hp = filter('highpass', 480, 0.7, t);
    const hg = ac.createGain();
    hg.gain.setValueAtTime(0.0001, t);
    hg.gain.linearRampToValueAtTime(vol, t + 0.28);
    hg.gain.setValueAtTime(vol, t + 0.62);
    hg.gain.exponentialRampToValueAtTime(0.0001, t + 1.0);
    src.connect(bp); bp.connect(hp); hp.connect(hg); hg.connect(g);
    fire(src, t, t + 1.1);
    // Tiny valve click at the start of the draw
    click(g, t, 0.12, 1300);

    // Exhale: a burst of exhaust bubbles rumbling upward
    const exT = t + 1.15;
    const nb = strained ? 10 : 7;
    for (let i = 0; i < nb; i++) {
      bubbleAt(g, exT + i * rand(0.045, 0.09), rand(0.1, 0.22), rand(0.7, 1.2));
    }
    // Soft broadband wash under the bubbles
    burst(g, exT, 0.7, 0.16, 'bandpass', 700, 1600, 1.2, 0.06, false);
  }

  // ---------------------------------------------------------------------
  // Distant creaks and whale-like moans
  // ---------------------------------------------------------------------

  function triggerCreak(cx) {
    if (!ready || cx.aboveWater) return;
    const t = now();
    const abyssal = cx.biome === BIOMES.ABYSS || cx.biome === BIOMES.WRECK;
    const g = openVoice({ volume: 1, pan: rand(-0.7, 0.7) }, 4.5, 0.5, caveConvolver);

    if (abyssal && Math.random() < 0.55) {
      // Whale-like moan: slow gliding sine with vibrato, very quiet
      const f0 = rand(70, 110);
      const o = osc('sine', f0, t, f0 * rand(1.3, 1.7), t + 1.6);
      o.frequency.exponentialRampToValueAtTime(f0 * 0.8, t + 3.2);
      const vib = osc('sine', rand(3, 5), t);
      const vibAmp = ac.createGain();
      vibAmp.gain.value = f0 * 0.04;
      vib.connect(vibAmp); vibAmp.connect(o.frequency);
      const vg = ac.createGain();
      env(vg.gain, t, rand(0.08, 0.16), 1.1, 0.6, 1.5);
      o.connect(vg); vg.connect(g);
      fire(o, t, t + 3.5);
      fire(vib, t, t + 3.5);
    } else {
      // Hull-like creak: high Q noise slowly bent downward
      const f0 = rand(300, 900);
      burst(g, t, rand(0.5, 1.1), rand(0.06, 0.14), 'bandpass',
        f0, f0 * rand(0.4, 0.7), 14, 0.12, true);
    }
  }

  // ---------------------------------------------------------------------
  // Generative music pad
  // ---------------------------------------------------------------------

  function triggerMusicNote(cx) {
    if (!ready) return;
    const t = now();
    musicStep += 1;

    // Deterministic walk over the pentatonic set
    const idx = Math.floor(musicRng() * PENTA.length);
    const semis = PENTA[idx];

    // The root drifts down as the diver descends: airy up top, grave below
    const depthK = clamp01((cx.depth || 0) / 130);
    const rootHz = 196 * Math.pow(0.5, depthK * 1.2);
    const freq = rootHz * Math.pow(2, semis / 12);

    const dur = 5 + musicRng() * 4;
    const detunes = [0.9972, 1, 1.0031];
    for (const d of detunes) {
      const o = osc(musicRng() < 0.5 ? 'sine' : 'triangle', freq * d, t);
      const g = ac.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.linearRampToValueAtTime(0.09, t + dur * 0.42);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g);
      g.connect(musicFilter);
      fire(o, t, t + dur + 0.1);
      // The pad also feeds the long reverb for space
      const send = ac.createGain();
      send.gain.value = 0.5;
      g.connect(send);
      send.connect(caveConvolver);
      setTimeout(() => {
        try { g.disconnect(); send.disconnect(); } catch (e) { /* gone */ }
      }, (dur + 0.4) * 1000);
    }
  }

  // ---------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------

  async function init() {
    if (ac) {
      if (ac.state === 'suspended') {
        try { await ac.resume(); } catch (e) { /* browser said no */ }
      }
      return;
    }
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    ac = new Ctx();
    if (ac.state === 'suspended') {
      try { await ac.resume(); } catch (e) { /* resumed on next gesture */ }
    }

    whiteBuffer = makeNoiseBuffer(false);
    pinkBuffer = makeNoiseBuffer(true);

    buildMasterChain();
    buildAmbience();
    buildRegistry();

    ready = true;
  }

  function play(name, opts) {
    if (!ready || !ac) return;
    if (ac.state === 'suspended') {
      ac.resume().catch(() => { /* needs a gesture, stay silent */ });
    }

    // The engine is a persistent loop, play() toggles it manually. update()
    // also raises it automatically while the player is inside the sub.
    if (name === 'engine') {
      engineManual = !engineManual;
      return;
    }

    const entry = SOUNDS[name];
    if (!entry || !entry.fn) return;

    const rate = opts && opts.rate ? clamp(opts.rate, 0.25, 4) : 1;
    const verbBus = entry.type === 'cave' ? caveConvolver : roomConvolver;
    const out = openVoice(opts || {}, entry.dur / Math.min(rate, 1) + 0.3,
      entry.verb, verbBus);
    try {
      entry.fn(now(), out, rate);
    } catch (e) {
      // A malformed schedule must never take the game down
    }
  }

  function setMuted(m) {
    mutedFlag = !!m;
    if (ready) {
      masterGain.gain.setTargetAtTime(
        mutedFlag ? 0 : AUDIO.masterVolume, now(), 0.05);
    }
  }

  // ---------------------------------------------------------------------
  // Continuous update
  // ---------------------------------------------------------------------

  function update(dt, cx) {
    if (!ready || !ac) return;
    if (!cx) cx = lastCtx;
    lastCtx = cx;
    if (!(dt > 0)) dt = 0.016;
    if (dt > 0.25) dt = 0.25;

    const t = now();
    const depth = Math.max(0, cx.depth || 0);
    const above = !!cx.aboveWater;
    const inSub = !!cx.insideSub;
    const threat = clamp01(cx.threat || 0);
    const oxygen01 = cx.oxygen01 !== undefined ? clamp01(cx.oxygen01) : 1;
    const health01 = cx.health01 !== undefined ? clamp01(cx.health01) : 1;
    const info = BIOME_INFO[cx.biome] || BIOME_INFO[BIOMES.LAGOON];

    // -- Underwater lowpass: the muffling with depth -------------------------
    // Surface: wide open near 18 kHz. Depth 0..130 m sweeps toward ~700 Hz
    // on an exponential curve so the first metres already darken the mix.
    let cutoff;
    if (above) {
      cutoff = 18000;
    } else {
      const k = clamp01(depth / 130);
      cutoff = 16000 * Math.pow(700 / 16000, Math.pow(k, 0.6));
      cutoff = Math.max(700, cutoff);
    }
    if (inSub) cutoff = Math.min(cutoff, 2400); // hull muffles everything
    underLowpass.frequency.setTargetAtTime(cutoff, t, 0.35);

    // -- Ambience crossfades --------------------------------------------------
    // Underwater bed: brighter and airier in the lagoon, heavy in the abyss.
    const bedTargetGain = (above || inSub) ? 0 : lerp(0.05, 0.14, 1 - info.ambient);
    bedGain.gain.setTargetAtTime(bedTargetGain, t, 0.8);
    bedFilter.frequency.setTargetAtTime(lerp(350, 1250, info.ambient), t, 1.2);

    const droneTarget = (above || inSub) ? 0 : lerp(0.01, 0.12, 1 - info.ambient);
    droneGain.gain.setTargetAtTime(droneTarget, t, 1.2);
    const droneHz = lerp(60, 38, 1 - info.ambient);
    droneOscA.frequency.setTargetAtTime(droneHz, t, 2);
    droneOscB.frequency.setTargetAtTime(droneHz * 1.014, t, 2);

    // Above water: wind and surf fade in, everything wet fades out
    windGain.gain.setTargetAtTime(above && !inSub ? 0.09 : 0, t, 0.7);
    surfGain.gain.setTargetAtTime(above && !inSub ? 0.11 : 0, t, 0.7);

    // Engine: automatic inside the sub, or toggled manually via play('engine')
    const engineOn = inSub || engineManual;
    engineGain.gain.setTargetAtTime(engineOn ? 0.16 : 0, t, 0.5);

    // -- Threat tension layer -------------------------------------------------
    const tBase = threat * 0.1;
    tensionGain.gain.setTargetAtTime(tBase, t, 0.4);
    tensionLfoDepth.gain.setTargetAtTime(tBase * 0.8, t, 0.4);
    tensionLfo.frequency.setTargetAtTime(lerp(1.2, 4.4, threat), t, 0.5);
    const tHz = lerp(52, 74, threat);
    tensionOscA.frequency.setTargetAtTime(tHz, t, 0.8);
    tensionOscB.frequency.setTargetAtTime(tHz * lerp(1.02, 1.045, threat), t, 0.8);
    tensionFilter.frequency.setTargetAtTime(lerp(220, 420, threat), t, 0.6);

    // -- Regulator breathing cycle -------------------------------------------
    if (!above && !inSub) {
      breathTimer -= dt;
      if (breathTimer <= 0) {
        triggerBreath(cx);
        let cycle = 4.2;
        if (cx.moving) cycle *= 0.72;
        if (oxygen01 < 0.35) cycle *= lerp(0.45, 0.85, oxygen01 / 0.35);
        breathTimer = cycle * rand(0.92, 1.08);
      }
    } else {
      breathTimer = Math.min(breathTimer, 1.2);
    }

    // -- Random ambient bubbles ----------------------------------------------
    if (!above && !inSub) {
      bubbleTimer -= dt;
      if (bubbleTimer <= 0) {
        const g = openVoice({ volume: rand(0.15, 0.4), pan: rand(-0.8, 0.8) },
          0.4, 0.05, roomConvolver);
        const n = 1 + Math.floor(Math.random() * 3);
        for (let i = 0; i < n; i++) {
          bubbleAt(g, t + i * rand(0.05, 0.12), rand(0.3, 0.7), rand(0.7, 1.4));
        }
        bubbleTimer = rand(1.6, 5.2);
      }
    }

    // -- Distant creaks and moans, denser and lower in the deep ---------------
    if (!above) {
      creakTimer -= dt;
      if (creakTimer <= 0) {
        triggerCreak(cx);
        const dense = cx.biome === BIOMES.ABYSS ? 0.5 : 1;
        creakTimer = rand(7, 20) * dense;
      }
    }

    // -- Gulls and coastal life above water ------------------------------------
    if (above && !inSub) {
      gullTimer -= dt;
      if (gullTimer <= 0) {
        play('gull', { volume: rand(0.25, 0.55), pan: rand(-0.9, 0.9),
          rate: rand(0.9, 1.15) });
        gullTimer = rand(4, 13);
      }
    }

    // -- Automatic warnings ----------------------------------------------------
    if (oxygen01 < 0.25 && !above && !inSub) {
      beepTimer -= dt;
      if (beepTimer <= 0) {
        play('lowOxygen', { volume: lerp(0.9, 0.5, oxygen01 / 0.25) });
        beepTimer = lerp(0.55, 2.1, oxygen01 / 0.25);
      }
    } else {
      beepTimer = 0;
    }

    if (health01 < 0.4 && health01 > 0) {
      heartTimer -= dt;
      if (heartTimer <= 0) {
        play('heartbeat', { volume: lerp(1.0, 0.5, health01 / 0.4) });
        heartTimer = lerp(0.65, 1.4, health01 / 0.4);
      }
    } else {
      heartTimer = 0;
    }

    // -- Generative music -------------------------------------------------------
    musicTimer -= dt;
    if (musicTimer <= 0) {
      triggerMusicNote(cx);
      musicTimer = 3.2 + musicRng() * 4.5;
    }
    // Darker pad with depth, ducked while threatened
    musicFilter.frequency.setTargetAtTime(
      lerp(2200, 550, clamp01(depth / 120)), t, 1.5);
    musicBus.gain.setTargetAtTime(
      AUDIO.musicVolume * (1 - threat * 0.7), t, 0.8);
  }

  // ---------------------------------------------------------------------
  // Teardown
  // ---------------------------------------------------------------------

  function dispose() {
    ready = false;
    for (const v of voices.slice()) removeVoice(v);
    voices.length = 0;
    for (const src of persistentSources) {
      try { src.stop(); } catch (e) { /* already stopped */ }
      try { src.disconnect(); } catch (e) { /* already gone */ }
    }
    persistentSources.length = 0;
    if (ac) {
      try { masterGain.disconnect(); } catch (e) { /* fine */ }
      const closing = ac;
      ac = null;
      closing.close().catch(() => { /* nothing to do */ });
    }
  }

  return {
    init,
    update,
    dispose,
    play,
    setMuted,
    get muted() { return mutedFlag; },
  };
}
