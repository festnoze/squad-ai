"""Out of Sight: the furniture's move step (hop) and the caught stings, synthesized offline (SOUNDS, 2026-11-24).

Replaces, under the same names (so Assets/Resources/AudioLibrary.asset and every test keep their roles):
    hop_01..04.wav        the per-step move sound of every hopping furniture (Sfx.PlayHop)
    hop_soft_01..04.wav   the same step on a rug, in a soft room or masked by a robot's hum (Sfx.PlaySoftHop)
    sting_caught.wav      the short "busted" sting when the furniture is seen moving (Sfx.PlayCaught)
    sting_caught_long.wav the slow defeat sting when the household's suspicion ran out (Sfx.PlayCaught)

The user asked for a move sound "plus feutre, mais brillant" (felted and soft, with a bright pleasant sparkle, neither
dull nor harsh) and a more crafted caught sting. Design:
  hop        SOUNDS2 (the felted wood with a glassy tick did not suit furniture): a muffled footstep on carpet. A low
             padded thump (a 94 to 134 Hz sine whose pitch sags as the pile compresses), a low-mid noise body (the pile
             squashing, 150 to 950 Hz), both under a 3.5 to 5 ms raised cosine attack, gently squashed and low passed at
             1.5 kHz, plus a faint fabric whisper above (1.3 to 4.2 kHz band passed noise with a fibrous flutter, 11 to
             14 dB under the body, rolled off above 5 kHz). Variants: a firm heel, heel then toe (55 ms), a light toe-led
             step, a heavy heel then toe (70 ms).
  hop_soft   the same step on a thick rug: lower, slower attack, the body low passed at 550 Hz, the toe contact 3 dB
             down, the whisper 9 dB down and under 2.2 kHz. The 10 dB level drop is the mix's (Tuning.SfxSoftHopMix).
  caught     a small orchestral "busted!" hit: a swish into a soft brass stab on a diminished chord over a light kick and
             a choked cymbal, a marimba running down the chord, landing on a low pizzicato G with a muted brass "bwomp"
             falling a semitone; a short room reverb.
  long       the same palette, slower: a muted brass "wah wah wah waaah" (D, C#, C, B) with the marimba an octave up,
             the last note held with vibrato over a low G (a G major "aww"), a choked cymbal and the same reverb.

Every file: mono 44.1 kHz 16-bit TPDF dithered WAV, a 40 Hz high pass, a sine fade in from 0 and a cosine fade out to 0,
loudness matched to the one-shot file target of tools/audio/audio_pipeline.py (-12 LUFS, max over 100 ms, K-weighted)
under the -1 dBTP true peak ceiling, so the Tuning.SfxHopMix / SfxSoftHopMix / SfxCaughtMix playback targets hold.

Setup and run, from the project root in PowerShell:
    tools/audio/.venv/Scripts/Activate.ps1
    python tools/audio/make_sounds.py            # write the eight hops, back up the previous ones, print the analysis
    python tools/audio/make_sounds.py --stings   # the same plus the two stings (they regenerate bit identical)
    python tools/audio/make_sounds.py --analyze  # analysis only (old backups vs current files)

Backups are never overwritten: Build/sounds/old/ holds the files before SOUNDS (recorded knocks, old stings),
Build/sounds/old2/ the hops before SOUNDS2 (felted wood with a tick). New hops go to Build/sounds/new2/, new stings to
Build/sounds/new/. Every run writes tools/audio/make_sounds_report.json.
"""
import argparse
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf
from scipy import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audio_pipeline as ap  # noqa: E402  (the shared BS.1770 measures, fades and dither)

ROOT = ap.ROOT
RATE = ap.RATE
OUT = ap.OUT
OLD_DIR = os.path.join(ROOT, "Build", "sounds", "old")
NEW_DIR = os.path.join(ROOT, "Build", "sounds", "new")
OLD2_DIR = os.path.join(ROOT, "Build", "sounds", "old2")  # SOUNDS2: the felted hops replaced by the carpet steps
NEW2_DIR = os.path.join(ROOT, "Build", "sounds", "new2")
REPORT = os.path.join(ROOT, "tools", "audio", "make_sounds_report.json")
TARGET_LUFS = ap.FILE_TARGET["oneshot"]

HOPS = ["hop_01", "hop_02", "hop_03", "hop_04"]
SOFT_HOPS = ["hop_soft_01", "hop_soft_02", "hop_soft_03", "hop_soft_04"]
STINGS = ["sting_caught", "sting_caught_long"]
NAMES = HOPS + SOFT_HOPS + STINGS


def note(name):
    """Frequency of a note name such as 'G2', 'C#4', 'Ab5' (A4 = 440 Hz)."""
    steps = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
    n = steps[name[0]]
    i = 1
    while name[i] in "#b":
        n += 1 if name[i] == "#" else -1
        i += 1
    octave = int(name[i:])
    return 440.0 * 2 ** ((n + 12 * (octave - 4)) / 12)


def timeline(seconds):
    return np.arange(int(round(seconds * RATE))) / RATE


def place(buf, x, at):
    """Adds x into buf starting at `at` seconds (clipped to the buffer)."""
    a = int(round(at * RATE))
    b = min(len(buf), a + len(x))
    if b > a:
        buf[a:b] += x[:b - a]
    return buf


def soft_attack(t, ms):
    """A raised cosine rise over `ms` (a felt mallet, not a click), then 1."""
    a = ms / 1000.0
    return np.where(t < a, 0.5 - 0.5 * np.cos(np.pi * np.clip(t / a, 0, 1)), 1.0)


def lowpass(x, hz, order=2):
    return signal.sosfilt(signal.butter(order, hz, btype="lowpass", fs=RATE, output="sos"), x)


def highpass(x, hz, order=2):
    return signal.sosfilt(signal.butter(order, hz, btype="highpass", fs=RATE, output="sos"), x)


def bandpass(x, lo, hi, order=2):
    return signal.sosfilt(signal.butter(order, [lo, hi], btype="bandpass", fs=RATE, output="sos"), x)


# ------------------------------------------------------------------------------------------- the hop (SOUNDS2)

def unit(x):
    """x scaled to an RMS of 1 (so layer levels below are relative, in dB)."""
    return x / (np.sqrt(np.mean(x ** 2)) + 1e-20)


def dbamp(db):
    return 10 ** (db / 20)


def padded_impact(rng, seconds, thump_hz, sag, decay, attack_ms, body_band, body_decay, body_db):
    """A foot landing on carpet: a low sine thump whose pitch sags as the pile and underlay compress, plus a short burst
    of low-mid noise (the pile squashing), both under a soft raised cosine attack (a pad, never a click)."""
    t = timeline(seconds)
    f = thump_hz * (1 + sag * np.exp(-t / 0.010))
    thump = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t / decay)
    body = bandpass(rng.standard_normal(len(t)), body_band[0], body_band[1]) * np.exp(-t / body_decay)
    return (unit(thump) + dbamp(body_db) * unit(body)) * soft_attack(t, attack_ms)


def fabric_brush(rng, seconds, band, rise_ms, decay):
    """The fabric whisper: band passed noise with a slower rise than the impact and a fibrous flutter (the sole
    brushing the pile), so it reads as cloth, not as a hiss."""
    t = timeline(seconds)
    noise = bandpass(rng.standard_normal(len(t)), band[0], band[1])
    flutter = 1 + 0.45 * unit(lowpass(rng.standard_normal(len(t)), 70))
    return unit(noise * np.clip(flutter, 0, None) * soft_attack(t, rise_ms) * np.exp(-t / decay))


# Per variant (heel or toe feel, pitch and texture vary so a long walk does not fatigue):
#   thump Hz, pitch sag, thump decay s, attack ms, body band Hz, body decay s, body dB,
#   second contact (gap s, level dB, pitch ratio) or None, brush (at s, dB, band Hz, rise ms, decay s).
HOP_VARIANTS = [
    # A firm heel, a short scuff right after it.
    (104, 0.30, 0.030, 4.5, (170, 700), 0.020, -1.0, None, (0.006, -12.0, (1500, 4000), 6.0, 0.030)),
    # Heel then toe: a second, lighter and slightly higher contact 55 ms later, the brush on the roll.
    (116, 0.25, 0.026, 4.0, (200, 800), 0.018, -2.0, (0.055, -6.0, 1.22), (0.030, -13.0, (1400, 3600), 8.0, 0.035)),
    # A light toe-led step: higher, quicker, more pile than thump, a slightly longer brush.
    (134, 0.20, 0.022, 3.5, (250, 950), 0.022, 1.0, None, (0.004, -11.0, (1700, 4200), 7.0, 0.045)),
    # A heavier heel then toe 70 ms later, the deepest body.
    (94, 0.35, 0.036, 5.0, (150, 600), 0.024, -2.0, (0.070, -8.0, 1.3), (0.040, -14.0, (1300, 3400), 9.0, 0.035)),
]
HOP_SECONDS = 0.20          # under the 0.224 s between two hops (pi / Tuning.HopFrequency)
SOFT_HOP_SECONDS = 0.18
IMPACT_LOWPASS_HZ = 1500    # the thump and pile body stay under 1.5 kHz; only the brush whispers above
SOFT_IMPACT_LOWPASS_HZ = 550
SQUASH = 2.0
SOFT_BRUSH_DB = -9.0        # on a thick rug the whisper drops 9 dB further and loses its top


def make_hop(i, soft):
    (thump_hz, sag, decay, attack, body_band, body_decay, body_db, second, brush) = HOP_VARIANTS[i]
    rng = np.random.default_rng(2000 + i)
    seconds = SOFT_HOP_SECONDS if soft else HOP_SECONDS
    if soft:
        # A thick rug: a lower, slower, rounder landing, the body darker, the toe contact nearly swallowed.
        thump_hz *= 0.9
        attack *= 1.7
        decay *= 1.15
        body_band = (body_band[0] * 0.8, body_band[1] * 0.6)
    impact = padded_impact(rng, seconds, thump_hz, sag, decay, attack, body_band, body_decay, body_db)
    if second is not None:
        gap, level_db, ratio = second
        toe = padded_impact(rng, seconds - gap, thump_hz * ratio, sag * 0.6, decay * 0.7, attack * 0.9,
                            (body_band[0] * 1.1, body_band[1] * 1.1), body_decay * 0.8, body_db)
        place(impact, dbamp(level_db - (3.0 if soft else 0.0)) * toe, gap)
    # A gentle tanh squash of the landing's first peak (the pad giving way): about 2 dB less crest, so the file reaches
    # its loudness target under the true peak ceiling; its low harmonics stay under the low pass below.
    impact = np.tanh(SQUASH * impact / np.max(np.abs(impact))) / np.tanh(SQUASH)
    impact = lowpass(impact, SOFT_IMPACT_LOWPASS_HZ if soft else IMPACT_LOWPASS_HZ, order=2)
    at, brush_db, band, rise, brush_decay = brush
    whisper = fabric_brush(rng, seconds - at, band, rise, brush_decay)
    if soft:
        whisper = lowpass(whisper, 2200, order=2)
        brush_db += SOFT_BRUSH_DB
    whisper = lowpass(whisper, 5000, order=1)  # no harsh top, even on the whisper
    y = unit(impact)
    place(y, dbamp(brush_db) * whisper, at)
    return y


# ------------------------------------------------------------------------------------------------ the stings

def brass(f0, seconds, rng, attack=0.025, peak_at=0.05, sustain=0.55, release=0.12, scoop_cents=-35,
          vibrato_cents=0.0, vibrato_from=0.25, fall_cents=0.0, fall_seconds=0.15, wah=None, max_harm=40,
          darkness=1.0):
    """A soft brass note by additive synthesis: it brightens as it gets louder (the brass "blat"), a small pitch scoop
    at the attack, optional vibrato, an optional fall at the end, and an optional wah (a moving formant: a harmon mute).
    """
    t = timeline(seconds)
    # Amplitude: soft rise, a small swell to the peak, a sustain, a release at the end.
    env = np.interp(t, [0, attack, peak_at, max(peak_at + 0.01, seconds - release), seconds],
                    [0, 0.8, 1.0, sustain, 0])
    env = np.clip(env, 0, None)
    cents = scoop_cents * np.exp(-t / 0.03)
    if vibrato_cents:
        depth = vibrato_cents * np.clip((t - vibrato_from) / 0.15, 0, 1)
        cents += depth * np.sin(2 * np.pi * 5.4 * t)
    if fall_cents:
        start = seconds - fall_seconds
        cents += fall_cents * np.clip((t - start) / fall_seconds, 0, 1) ** 1.6
    f = f0 * 2 ** (cents / 1200)
    phase = 2 * np.pi * np.cumsum(f) / RATE + rng.uniform(0, 2 * np.pi)
    # Spectral tilt: k^-tilt, from dark (quiet) to brighter (loud).
    tilt = darkness * (2.6 - 1.1 * env)
    y = np.zeros_like(t)
    for k in range(1, max_harm + 1):
        if k * f0 > 9000:
            break
        a = k ** (-tilt)
        if wah is not None:
            centre = wah(t)
            fk = k * f
            a = a * (0.18 + np.exp(-0.5 * (np.log2(fk / centre) / 0.7) ** 2))
        y += a * np.sin(k * phase)
    return y * env


def marimba(f0, seconds, rng, mallet_ms=1.6):
    """A rosewood bar: partials 1 : 3.93 : 9.2, the fundamental ringing longest, a soft yarn mallet."""
    t = timeline(seconds)
    tau1 = min(0.55, 180.0 / f0 + 0.08)
    y = (np.sin(2 * np.pi * f0 * t) * np.exp(-t / tau1)
         + 0.28 * np.sin(2 * np.pi * f0 * 3.93 * t) * np.exp(-t / (tau1 * 0.22))
         + 0.05 * np.sin(2 * np.pi * f0 * 9.2 * t) * np.exp(-t / (tau1 * 0.08)))
    knock = lowpass(rng.standard_normal(len(t)) * np.exp(-t / 0.004), 2500) * 0.08
    return (y + knock) * soft_attack(t, mallet_ms)


def pizzicato(f0, seconds, rng, tau=0.35):
    """A plucked string: harmonics 1/k, the upper ones dying first, a finger (not a pick) so a soft top."""
    t = timeline(seconds)
    y = np.zeros_like(t)
    for k in range(1, 30):
        if k * f0 > 7000:
            break
        y += (1.0 / k ** 1.3) * np.exp(-t / (tau / (1 + 0.45 * (k - 1)))) * np.sin(2 * np.pi * k * f0 * t + rng.uniform(0, 0.4))
    return y * soft_attack(t, 2.0)


def kick(seconds):
    """A soft orchestral bass drum: a sine falling from 110 to 55 Hz."""
    t = timeline(seconds)
    f = 55 + 55 * np.exp(-t / 0.04)
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t / 0.12) * soft_attack(t, 3.0)


def choked_cymbal(seconds, rng, tau=0.11):
    """A muted (choked) cymbal: metallic square partials plus noise, high passed, a short decay, the top rounded off."""
    t = timeline(seconds)
    metal = sum(signal.square(2 * np.pi * fr * t + rng.uniform(0, 6)) for fr in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0))
    noise = rng.standard_normal(len(t))
    y = highpass(0.35 * metal / 6 + noise, 4500, order=3)
    y = lowpass(y, 9500, order=2)
    return y * np.exp(-t / tau) * soft_attack(t, 1.0)


def swish(seconds, rng):
    """A short rising swish of band passed noise into the hit."""
    t = timeline(seconds)
    noise = rng.standard_normal(len(t))
    # A low band fading into a high band: the swish rises without a time varying filter (no zipper noise).
    u = t / seconds
    y = (1 - u) * bandpass(noise, 900, 2200) + u * bandpass(noise, 2200, 5500)
    env = u ** 2.2
    return y * env


def room_reverb(x, rng, rt60=0.75, wet=0.22, pre_ms=12):
    """A small warm room: an exponentially decaying noise tail (dark), a few early reflections, mixed under the dry."""
    n = int(rt60 * 1.2 * RATE)
    t = timeline(n / RATE)
    tail = rng.standard_normal(n) * np.exp(-6.91 * t / rt60)
    tail = lowpass(tail, 4200, order=2)
    ir = np.zeros(n + int(pre_ms / 1000 * RATE))
    ir[int(pre_ms / 1000 * RATE):] = tail
    for ms, g in ((7, 0.35), (13, 0.25), (19, 0.2), (29, 0.12)):
        ir[int(ms / 1000 * RATE)] += g * 30
    ir /= np.sqrt(np.sum(ir ** 2))
    wet_sig = signal.fftconvolve(x, ir)[:len(x)]
    dry_rms = np.sqrt(np.mean(x ** 2))
    wet_rms = np.sqrt(np.mean(wet_sig ** 2)) + 1e-12
    return x + wet * wet_sig * dry_rms / wet_rms


def make_caught():
    rng = np.random.default_rng(77)
    total = 1.45
    y = np.zeros(int(total * RATE))
    hit = 0.07  # a 70 ms swish leads into the hit
    place(y, 0.10 * swish(hit, rng), 0.0)
    # The stab: B dim7 (B3 D4 F4 Ab4) in soft brass, a slight fall at its end ("bwah"), an octave below for weight.
    stab = np.zeros(int(0.42 * RATE))
    for k, n in enumerate(["B3", "D4", "F4", "Ab4"]):
        b = brass(note(n) * (1 + rng.uniform(-0.002, 0.002)), 0.42, rng, attack=0.012, peak_at=0.03, sustain=0.35,
                  release=0.2, scoop_cents=-25, fall_cents=-70, fall_seconds=0.16, darkness=0.85)
        place(stab, 0.9 * b, 0.003 * k)
    place(stab, 0.5 * brass(note("B2"), 0.38, rng, attack=0.015, peak_at=0.035, sustain=0.3, release=0.2,
                            scoop_cents=-20, fall_cents=-70, fall_seconds=0.16, darkness=1.2), 0.0)
    place(y, 0.75 * stab / np.max(np.abs(stab)), hit)
    place(y, 0.40 * kick(0.35), hit)
    place(y, 0.10 * choked_cymbal(0.4, rng), hit)
    # The marimba runs down the chord: Ab5 F5 D5 B4 ("di-di-di-di").
    for k, n in enumerate(["Ab5", "F5", "D5", "B4"]):
        place(y, (0.30 - 0.02 * k) * marimba(note(n), 0.6, rng), hit + 0.2 + 0.105 * k)
    # The landing: a low pizzicato G (G7b9 under the arpeggio: the "oops" left hanging) and a muted brass "bwomp".
    land = hit + 0.2 + 0.105 * 4 + 0.04
    place(y, 0.30 * pizzicato(note("G2"), 0.7, rng, tau=0.4), land)
    place(y, 0.22 * marimba(note("G3"), 0.6, rng), land)
    mute = lambda tt: 700 + 500 * np.exp(-tt / 0.08)  # noqa: E731  (a closing harmon mute: "bwomp")
    place(y, 0.18 * brass(note("G3"), 0.34, rng, attack=0.02, peak_at=0.05, sustain=0.5, release=0.16,
                          scoop_cents=-30, fall_cents=-100, fall_seconds=0.2, wah=mute), land)
    y = room_reverb(y, rng, rt60=0.7, wet=0.2)
    return y


def make_caught_long():
    rng = np.random.default_rng(78)
    total = 2.6
    y = np.zeros(int(total * RATE))
    starts = [0.0, 0.38, 0.76, 1.14]
    names = ["D4", "C#4", "C4", "B3"]
    for k, (at, n) in enumerate(zip(starts, names)):
        last = k == len(names) - 1
        seconds = 1.05 if last else 0.36
        # The harmon mute opens and closes on each note: "wah".
        open_at = 0.09 if not last else 0.12

        def wah(tt, open_at=open_at, seconds=seconds, last=last):
            shape = np.exp(-0.5 * ((tt - open_at) / (0.06 if not last else 0.09)) ** 2)
            closing = 0.0 if not last else 0.35 * np.clip((tt - 0.3) / 0.6, 0, 1)
            return 500 + 1300 * np.maximum(shape, closing)

        b = brass(note(n), seconds, rng, attack=0.03, peak_at=0.08, sustain=0.75 if last else 0.6,
                  release=0.35 if last else 0.09, scoop_cents=-40, vibrato_cents=22 if last else 0.0, vibrato_from=0.3,
                  fall_cents=-120 if last else 0.0, fall_seconds=0.3, wah=wah)
        place(y, (0.75 if last else 1.0) * b, 0.05 + at)
        place(y, 0.14 * marimba(note(n) * 2, 0.6, rng), 0.05 + at)
    # Under the held B: a low G (a G major "aww"), a soft kick and a choked cymbal, the marimba's G B D on top.
    land = 0.05 + starts[-1]
    place(y, 0.26 * pizzicato(note("G2"), 1.0, rng, tau=0.55), land)
    place(y, 0.22 * kick(0.4), land)
    place(y, 0.05 * choked_cymbal(0.5, rng, tau=0.16), land)
    for k, n in enumerate(["G4", "B4", "D5"]):
        place(y, 0.10 * marimba(note(n), 0.9, rng), land + 0.03 * k)
    y = room_reverb(y, rng, rt60=0.85, wet=0.22)
    return y


# --------------------------------------------------------------------------------------------------- finishing

def finish(y, fade_in_ms, fade_out_ms, seed):
    """High pass, fades to exact zero, loudness match under the true peak ceiling, 16-bit TPDF dither."""
    y = highpass(y, 40, order=2)
    y = y - np.mean(y)
    x = y[:, None].copy()
    x = ap.fade(x, fade_in_ms, fade_out_ms)
    x, gain, limited = ap.normalize(x, TARGET_LUFS, "oneshot")
    x = ap.dither16(x, seed)
    # The dither must not leave the first and last samples off zero: the fades end exactly on silence.
    x[0, 0] = 0.0
    x[-1, 0] = 0.0
    return x[:, 0], gain, limited


def build(with_stings):
    """Writes the eight hops (and the two stings only with --stings: they are final and regenerate bit identical)."""
    names = HOPS + SOFT_HOPS + (STINGS if with_stings else [])
    for folder in (OLD_DIR, NEW_DIR, OLD2_DIR, NEW2_DIR):
        os.makedirs(folder, exist_ok=True)
    for name in names:
        src = os.path.join(OUT, name + ".wav")
        # old/ keeps the files before SOUNDS, old2/ the hops before SOUNDS2 (the felted wood with a glassy tick).
        backup = OLD2_DIR if name in HOPS + SOFT_HOPS else OLD_DIR
        dst = os.path.join(backup, name + ".wav")
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
    made = {}
    for i in range(4):
        made[HOPS[i]] = (make_hop(i, soft=False), 1.0, 30)
        made[SOFT_HOPS[i]] = (make_hop(i, soft=True), 1.0, 30)
    if with_stings:
        made["sting_caught"] = (make_caught(), 1.0, 120)
        made["sting_caught_long"] = (make_caught_long(), 1.0, 200)
    # The dither seed of each file is fixed (the SOUNDS order), so a rerun is reproducible file by file.
    seeds = {n: 500 + k for k, n in enumerate([x for pair in zip(HOPS, SOFT_HOPS) for x in pair] + STINGS)}
    rows = {}
    for name, (y, fin, fout) in made.items():
        out, gain, limited = finish(y, fin, fout, seeds[name])
        path = os.path.join(OUT, name + ".wav")
        sf.write(path, out, RATE, subtype="PCM_16")
        shutil.copy2(path, os.path.join(NEW2_DIR if name in HOPS + SOFT_HOPS else NEW_DIR, name + ".wav"))
        rows[name] = {"gain_db": round(gain, 2), "peak_limited": bool(limited)}
    return rows


# --------------------------------------------------------------------------------------------------- analysis

def rms_frequency(x):
    """The RMS frequency (Hz) from the first difference: 2 asin(rms(dx) / (2 rms(x))) * fs / (2 pi).

    The same proxy ProbeTestsM3Audio computes on the imported clip: a pure tone reads exactly its frequency, and it
    weights the spectrum by power, so it is a brightness measure that a test can recompute without an FFT.
    """
    r = np.sqrt(np.mean(np.diff(x) ** 2)) / (2 * np.sqrt(np.mean(x ** 2)) + 1e-20)
    return float(2 * np.arcsin(min(1.0, r)) * RATE / (2 * np.pi))


def analyze_file(path):
    x, rate = sf.read(path, dtype="float64", always_2d=True)
    mono = x.mean(axis=1)
    # No window: every file starts and ends on silence, and a window would hide the attack at the start.
    spec = np.abs(np.fft.rfft(mono)) ** 2
    freqs = np.fft.rfftfreq(len(mono), 1 / rate)
    centroid = float(np.sum(freqs * spec) / (np.sum(spec) + 1e-20))
    band = lambda lo, hi: float(np.sum(spec[(freqs >= lo) & (freqs < hi)]) / (np.sum(spec) + 1e-20))  # noqa: E731
    edge = int(0.002 * rate)
    active = mono[np.abs(mono) > 10 ** (-50 / 20)]
    return {
        "duration_s": round(len(mono) / rate, 3),
        "rate": rate,
        "channels": x.shape[1],
        "peak_dbfs": round(ap.db(float(np.max(np.abs(mono)))), 1),
        "true_peak_dbtp": round(ap.true_peak(mono[:, None]), 1),
        "rms_dbfs": round(ap.db(float(np.sqrt(np.mean(mono ** 2)))), 1),
        "active_rms_dbfs": round(ap.db(float(np.sqrt(np.mean(active ** 2)))) if len(active) else -240.0, 1),
        "lufs_100ms_max": round(ap.short_max(mono[:, None], rate), 1),
        "centroid_hz": round(centroid),
        "rms_frequency_hz": round(rms_frequency(mono)),
        "energy_below_500": round(band(0, 500), 3),
        "energy_500_2k": round(band(500, 2000), 3),
        "energy_above_1k5": round(band(1500, rate / 2), 3),
        "energy_2k_6k": round(band(2000, 6000), 3),
        "energy_above_6k": round(band(6000, rate / 2), 4),
        "dc": round(float(np.mean(mono)), 6),
        "first_sample": round(float(abs(mono[0])), 5),
        "last_sample": round(float(abs(mono[-1])), 5),
        "head_2ms_dbfs": round(ap.db(float(np.sqrt(np.mean(mono[:edge] ** 2)))), 1),
        "tail_2ms_dbfs": round(ap.db(float(np.sqrt(np.mean(mono[-edge:] ** 2)))), 1),
        "clipped_samples": int(np.sum(np.abs(mono) >= 0.999)),
    }


def analyze(build_rows=None):
    report = {}
    print(f"{'file':20s} {'which':4s} {'dur':>6s} {'peak':>6s} {'TP':>6s} {'RMS':>6s} {'L100':>6s} {'cent':>6s}"
          f" {'rmsF':>6s} {'<500':>5s} {'>1k5':>5s} {'2-6k':>5s} {'>6k':>6s} {'DC':>9s} {'head':>6s} {'tail':>6s} clip")
    for name in NAMES:
        report[name] = {}
        old = OLD2_DIR if name in HOPS + SOFT_HOPS else OLD_DIR
        for which, folder in (("old", old), ("new", OUT)):
            path = os.path.join(folder, name + ".wav")
            if not os.path.exists(path):
                continue
            m = analyze_file(path)
            report[name][which] = m
            print(f"{name:20s} {which:4s} {m['duration_s']:6.3f} {m['peak_dbfs']:6.1f} {m['true_peak_dbtp']:6.1f}"
                  f" {m['rms_dbfs']:6.1f} {m['lufs_100ms_max']:6.1f} {m['centroid_hz']:6d} {m['rms_frequency_hz']:6d}"
                  f" {m['energy_below_500']:5.2f} {m['energy_above_1k5']:5.3f} {m['energy_2k_6k']:5.2f} {m['energy_above_6k']:6.4f}"
                  f" {m['dc']:9.6f} {m['head_2ms_dbfs']:6.1f} {m['tail_2ms_dbfs']:6.1f} {m['clipped_samples']}")
        if build_rows and name in build_rows:
            report[name]["build"] = build_rows[name]
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print("AudioLibraryBuilder loudness (lufs_100ms_max of the new files):")
    for name in NAMES:
        if "new" in report[name]:
            print(f'    new Spec("{name}", ..., {report[name]["new"]["lufs_100ms_max"]:.1f}f),')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--analyze", action="store_true", help="only analyse (old backups vs the current files)")
    p.add_argument("--stings", action="store_true", help="also rewrite the two caught stings (bit identical)")
    args = p.parse_args()
    rows = None if args.analyze else build(args.stings)
    analyze(rows)


if __name__ == "__main__":
    main()
