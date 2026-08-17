/**
 * RESONANCE - synthesized diegetic audio. No sample, no fetch: everything is
 * Web Audio oscillators and noise buffers. The AudioContext is created on the
 * first user gesture (unlock()), as required by autoplay policies.
 *
 * Each placed fork hums at its band's pitch; the shared danger voice climbs
 * with the most charged crystal; shattering is a bright ping over a noise
 * burst. M mutes everything through the master gain.
 */

const BAND_FREQ = [110, 220, 440];

export function createAudio() {
  let ctx = null;
  let master = null;
  let muted = false;
  const forkVoices = new Map(); // fork object -> {osc, gain}
  let danger = null;            // {osc, gain}
  let noiseBuf = null;

  function unlock() {
    if (ctx) {
      if (ctx.state === 'suspended') ctx.resume();
      return;
    }
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    master = ctx.createGain();
    master.gain.value = muted ? 0 : 0.85;
    master.connect(ctx.destination);

    noiseBuf = ctx.createBuffer(1, ctx.sampleRate * 0.5, ctx.sampleRate);
    const d = noiseBuf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 600;
    gain.gain.value = 0;
    osc.connect(gain).connect(master);
    osc.start();
    danger = { osc, gain };
  }

  function setMuted(m) {
    muted = m;
    if (master) master.gain.setTargetAtTime(muted ? 0 : 0.85, ctx.currentTime, 0.05);
  }

  /** Keep one soft drone per placed fork; detune slightly per voice. */
  function syncForks(forks) {
    if (!ctx) return;
    for (const [fork, v] of forkVoices) {
      if (!forks.includes(fork)) {
        v.gain.gain.setTargetAtTime(0, ctx.currentTime, 0.12);
        v.osc.stop(ctx.currentTime + 0.6);
        forkVoices.delete(fork);
      }
    }
    forks.forEach((fork, i) => {
      let v = forkVoices.get(fork);
      if (!v) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'triangle';
        gain.gain.value = 0;
        gain.gain.setTargetAtTime(0.05, ctx.currentTime, 0.2);
        osc.connect(gain).connect(master);
        osc.start();
        v = { osc, gain };
        forkVoices.set(fork, v);
      }
      v.osc.frequency.setTargetAtTime(BAND_FREQ[fork.band] * (1 + i * 0.004), ctx.currentTime, 0.05);
    });
  }

  /** frac 0..1: charge of the most charged crystal. Climbing harmonic. */
  function setDanger(frac) {
    if (!ctx) return;
    danger.gain.gain.setTargetAtTime(frac > 0.02 ? 0.028 + frac * 0.05 : 0, ctx.currentTime, 0.08);
    danger.osc.frequency.setTargetAtTime(500 + frac * 1300, ctx.currentTime, 0.06);
  }

  function blip(freq, dur, vol, type = 'sine') {
    if (!ctx || muted) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(vol, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + dur);
    osc.connect(gain).connect(master);
    osc.start();
    osc.stop(ctx.currentTime + dur + 0.05);
  }

  function noise(dur, vol, freq) {
    if (!ctx || muted) return;
    const src = ctx.createBufferSource();
    src.buffer = noiseBuf;
    const filt = ctx.createBiquadFilter();
    filt.type = 'bandpass';
    filt.frequency.value = freq;
    filt.Q.value = 1.2;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(vol, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + dur);
    src.connect(filt).connect(gain).connect(master);
    src.start();
    src.stop(ctx.currentTime + dur + 0.05);
  }

  function place(band) { blip(BAND_FREQ[band] * 2, 0.18, 0.16, 'triangle'); }
  function remove() { blip(180, 0.16, 0.12, 'sine'); }
  function tweak(band) { blip(BAND_FREQ[band] * 3, 0.1, 0.1, 'square'); }
  function error() { blip(140, 0.22, 0.14, 'sawtooth'); noise(0.12, 0.05, 500); }
  function shatter(band) {
    noise(0.5, 0.3, 2400);
    blip(BAND_FREQ[band] * 6, 0.7, 0.22, 'sine');
    blip(BAND_FREQ[band] * 9, 0.4, 0.1, 'sine');
  }
  function fail() { blip(90, 0.9, 0.25, 'sawtooth'); noise(0.8, 0.2, 240); }
  function win() {
    if (!ctx || muted) return;
    [261.6, 329.6, 392.0, 523.3].forEach((f, i) => {
      setTimeout(() => blip(f, 0.8, 0.14, 'triangle'), i * 110);
    });
  }
  function click() { blip(900, 0.05, 0.06, 'square'); }

  function dispose() {
    if (ctx) ctx.close();
    ctx = null;
    forkVoices.clear();
  }

  return {
    unlock, setMuted, get muted() { return muted; },
    syncForks, setDanger,
    place, remove, tweak, error, shatter, fail, win, click,
    dispose,
  };
}
