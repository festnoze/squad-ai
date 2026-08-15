// Audio 100% procedural (WebAudio). Aucun fichier, aucun fetch.
//
// Deux sources continues (moteur et souffle atmospherique) sont construites une
// seule fois et pilotees en continu par des rampes douces. Les effets ponctuels
// sont crees a la demande et se deconnectent seuls a la fin de leur enveloppe,
// donc aucun noeud ne fuit.
//
// Tout est sans-echec : si l'AudioContext n'existe pas encore (aucune
// interaction utilisateur) ou s'il est suspendu, les appels ne font rien et ne
// levent jamais d'exception.

const MASTER_GAIN = 0.5;
const NOISE_SECONDS = 2;
const RAMP = 0.09; // constante de temps des rampes continues (secondes)

const saturate = (x) => (Number.isFinite(x) ? (x < 0 ? 0 : x > 1 ? 1 : x) : 0);

export function createAudio() {
  let ctx = null;
  let master = null;
  let noiseBuffer = null;
  let engineChain = null;
  let windChain = null;
  let muted = false;
  let disposed = false;

  function alive() {
    return !!ctx && !disposed && ctx.state !== 'closed';
  }

  /** Rampe douce d'un AudioParam, tolerante aux implementations partielles. */
  function set(param, value, time) {
    if (!param) return;
    const v = Number.isFinite(value) ? value : 0;
    try {
      if (param.setTargetAtTime) param.setTargetAtTime(v, ctx.currentTime, time || RAMP);
      else param.value = v;
    } catch (err) {
      try {
        param.value = v;
      } catch (err2) {
        /* rien */
      }
    }
  }

  function buildNoiseBuffer() {
    const len = Math.floor(ctx.sampleRate * NOISE_SECONDS);
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = buf.getChannelData(0);
    // Bruit blanc simple, deterministe (LCG) pour eviter Math.random.
    let s = 0x9e3779b9;
    for (let i = 0; i < len; i++) {
      s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
      data[i] = (s / 4294967296) * 2 - 1;
    }
    return buf;
  }

  // -------------------------------------------------------------------------
  // Chaines continues
  // -------------------------------------------------------------------------

  function buildEngine() {
    const gain = ctx.createGain();
    gain.gain.value = 0;
    const lowpass = ctx.createBiquadFilter();
    lowpass.type = 'lowpass';
    lowpass.frequency.value = 240;
    lowpass.Q.value = 1.1;
    lowpass.connect(gain);
    gain.connect(master);

    const o1 = ctx.createOscillator();
    o1.type = 'sawtooth';
    o1.frequency.value = 55;
    const o2 = ctx.createOscillator();
    o2.type = 'sawtooth';
    o2.frequency.value = 55;
    o2.detune.value = 13; // leger desaccord : battement organique
    // Troisieme voix : sinus une octave au-dessus, uniquement en boost.
    const o3 = ctx.createOscillator();
    o3.type = 'sine';
    o3.frequency.value = 110;
    const o3Gain = ctx.createGain();
    o3Gain.gain.value = 0;

    o1.connect(lowpass);
    o2.connect(lowpass);
    o3.connect(o3Gain);
    o3Gain.connect(lowpass);
    o1.start();
    o2.start();
    o3.start();
    return { o1, o2, o3, o3Gain, lowpass, gain };
  }

  function buildWind() {
    const source = ctx.createBufferSource();
    source.buffer = noiseBuffer;
    source.loop = true;
    const bandpass = ctx.createBiquadFilter();
    bandpass.type = 'bandpass';
    bandpass.frequency.value = 400;
    bandpass.Q.value = 0.7;
    const gain = ctx.createGain();
    gain.gain.value = 0;
    source.connect(bandpass);
    bandpass.connect(gain);
    gain.connect(master);
    source.start();
    return { source, bandpass, gain };
  }

  // -------------------------------------------------------------------------
  // Voix ponctuelles (auto-nettoyantes)
  // -------------------------------------------------------------------------

  /** Enveloppe attaque / extinction exponentielle sur un GainNode. */
  function envelope(gainNode, t0, attack, duration, peak) {
    const g = gainNode.gain;
    const p = Math.max(peak, 0.0002);
    const a = Math.max(0.004, Math.min(attack, duration * 0.9));
    g.setValueAtTime(0.0001, t0);
    g.exponentialRampToValueAtTime(p, t0 + a);
    g.exponentialRampToValueAtTime(0.0001, t0 + duration);
  }

  /** Oscillateur avec balayage de frequence et enveloppe, detruit a la fin. */
  function voice(type, f0, f1, t0, duration, peak, attack, dest) {
    const osc = ctx.createOscillator();
    osc.type = type;
    const gain = ctx.createGain();
    osc.frequency.setValueAtTime(Math.max(f0, 1), t0);
    if (f1 && f1 !== f0) osc.frequency.exponentialRampToValueAtTime(Math.max(f1, 1), t0 + duration);
    envelope(gain, t0, attack === undefined ? 0.012 : attack, duration, peak);
    osc.connect(gain);
    gain.connect(dest || master);
    osc.start(t0);
    osc.stop(t0 + duration + 0.05);
    osc.onended = () => {
      try {
        osc.disconnect();
        gain.disconnect();
      } catch (err) {
        /* rien */
      }
    };
    return { osc, gain };
  }

  /** Bruit filtre avec balayage du filtre, detruit a la fin. */
  function noiseVoice(t0, duration, filterType, f0, f1, q, peak, attack) {
    const source = ctx.createBufferSource();
    source.buffer = noiseBuffer;
    source.loop = true;
    const filter = ctx.createBiquadFilter();
    filter.type = filterType;
    filter.Q.value = q;
    filter.frequency.setValueAtTime(Math.max(f0, 1), t0);
    if (f1 && f1 !== f0) filter.frequency.exponentialRampToValueAtTime(Math.max(f1, 1), t0 + duration);
    const gain = ctx.createGain();
    envelope(gain, t0, attack === undefined ? 0.02 : attack, duration, peak);
    source.connect(filter);
    filter.connect(gain);
    gain.connect(master);
    source.start(t0);
    source.stop(t0 + duration + 0.05);
    source.onended = () => {
      try {
        source.disconnect();
        filter.disconnect();
        gain.disconnect();
      } catch (err) {
        /* rien */
      }
    };
    return { source, filter, gain };
  }

  // -------------------------------------------------------------------------
  // Banque de sons
  // -------------------------------------------------------------------------

  const SOUNDS = {
    // Bip de scan : 880 -> 1320 Hz en 120 ms.
    scan(t0) {
      voice('sine', 880, 1320, t0, 0.12, 0.2, 0.008);
    },

    // Decouverte validee : arpege majeur 3 notes.
    found(t0) {
      const notes = [523.25, 659.25, 783.99];
      for (let i = 0; i < notes.length; i++) {
        voice('triangle', notes[i], notes[i], t0 + i * 0.1, 0.26, 0.18, 0.01);
      }
    },

    // Victoire : motif de 6 notes puis pad tenu 3 s.
    win(t0) {
      const notes = [523.25, 587.33, 659.25, 783.99, 880, 1046.5];
      for (let i = 0; i < notes.length; i++) {
        voice('triangle', notes[i], notes[i], t0 + i * 0.17, 0.34, 0.16, 0.012);
      }
      const pad = ctx.createGain();
      const padFilter = ctx.createBiquadFilter();
      padFilter.type = 'lowpass';
      padFilter.frequency.value = 1100;
      padFilter.connect(pad);
      pad.connect(master);
      envelope(pad, t0 + 0.2, 0.8, 3.0, 0.13);
      const padStart = t0 + 0.2;
      const roots = [130.81, 196.0, 261.63];
      const oscs = [];
      for (const f of roots) {
        const o = ctx.createOscillator();
        o.type = 'sawtooth';
        o.frequency.value = f;
        o.detune.value = f === 196.0 ? 6 : -6;
        o.connect(padFilter);
        o.start(padStart);
        o.stop(padStart + 3.1);
        oscs.push(o);
      }
      oscs[oscs.length - 1].onended = () => {
        try {
          for (const o of oscs) o.disconnect();
          padFilter.disconnect();
          pad.disconnect();
        } catch (err) {
          /* rien */
        }
      };
    },

    // Warp : sweep 60 -> 2000 Hz sur 1.2 s + bruit filtre montant.
    warp(t0) {
      voice('sawtooth', 60, 2000, t0, 1.2, 0.16, 0.25);
      noiseVoice(t0, 1.2, 'bandpass', 200, 3200, 1.4, 0.14, 0.4);
    },

    // Alarme de proximite : carre 220 Hz pulse 3 fois.
    alarm(t0) {
      for (let i = 0; i < 3; i++) {
        voice('square', 220, 220, t0 + i * 0.22, 0.13, 0.14, 0.006);
      }
    },

    // Clic d'interface tres court.
    ui(t0) {
      voice('triangle', 1500, 900, t0, 0.045, 0.1, 0.004);
    },

    // Entree dans l'atmosphere : montee de bruit filtre sur 1.5 s.
    enterAtmo(t0) {
      noiseVoice(t0, 1.5, 'bandpass', 180, 1800, 0.8, 0.22, 0.95);
    },
  };

  // -------------------------------------------------------------------------
  // API publique
  // -------------------------------------------------------------------------

  const api = {
    /** Cree l'AudioContext au premier geste utilisateur puis le reprend. */
    async resume() {
      if (disposed) return;
      try {
        if (!ctx) {
          const Ctor = window.AudioContext || window.webkitAudioContext;
          if (!Ctor) return;
          ctx = new Ctor();
          master = ctx.createGain();
          master.gain.value = muted ? 0 : MASTER_GAIN;
          master.connect(ctx.destination);
          noiseBuffer = buildNoiseBuffer();
          engineChain = buildEngine();
          windChain = buildWind();
        }
        if (ctx.state === 'suspended') await ctx.resume();
      } catch (err) {
        /* audio indisponible : le jeu continue en silence */
      }
    },

    /** Drone moteur. throttle 0..1, boost 0..1, density 0..1. */
    engine(throttle, boost, density) {
      if (!alive() || !engineChain) return;
      const th = saturate(throttle);
      const bo = saturate(boost);
      const de = saturate(density);
      const base = 55 * (1 + th * 1.5 + bo * 1.15);
      set(engineChain.o1.frequency, base);
      set(engineChain.o2.frequency, base * 1.006);
      set(engineChain.o3.frequency, base * 2);
      set(engineChain.o3Gain.gain, bo * 0.18);
      set(engineChain.lowpass.frequency, 220 + th * 2400 + bo * 2200 + de * 260);
      set(engineChain.gain.gain, 0.035 + th * 0.2 + bo * 0.1);
    },

    /** Souffle atmospherique. Disparait dans le vide (density = 0). */
    wind(speed, density) {
      if (!alive() || !windChain) return;
      const s = saturate((speed || 0) / 420);
      const d = saturate(density);
      const amp = Math.pow(s, 1.4) * d;
      set(windChain.bandpass.frequency, 260 + s * 2400);
      set(windChain.gain.gain, amp * 0.34);
    },

    play(name) {
      if (!alive()) return;
      const fn = SOUNDS[name];
      if (!fn) return;
      try {
        fn(ctx.currentTime + 0.02);
      } catch (err) {
        /* rien : un son rate ne doit jamais casser la frame */
      }
    },

    setMuted(value) {
      muted = !!value;
      if (!alive() || !master) return;
      set(master.gain, muted ? 0 : MASTER_GAIN, 0.05);
    },

    get muted() {
      return muted;
    },

    dispose() {
      if (disposed) return;
      disposed = true;
      try {
        if (engineChain) {
          engineChain.o1.stop();
          engineChain.o2.stop();
          engineChain.o3.stop();
          engineChain.o1.disconnect();
          engineChain.o2.disconnect();
          engineChain.o3.disconnect();
          engineChain.o3Gain.disconnect();
          engineChain.lowpass.disconnect();
          engineChain.gain.disconnect();
        }
      } catch (err) {
        /* rien */
      }
      try {
        if (windChain) {
          windChain.source.stop();
          windChain.source.disconnect();
          windChain.bandpass.disconnect();
          windChain.gain.disconnect();
        }
      } catch (err) {
        /* rien */
      }
      try {
        if (master) master.disconnect();
        if (ctx && ctx.state !== 'closed' && ctx.close) ctx.close();
      } catch (err) {
        /* rien */
      }
      engineChain = null;
      windChain = null;
      noiseBuffer = null;
      master = null;
      ctx = null;
    },
  };

  return api;
}
