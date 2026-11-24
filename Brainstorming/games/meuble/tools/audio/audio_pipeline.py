"""Out of Sight audio pipeline: measure, derive the shipped sound effects, and build the music loops.

Reruns from the downloaded originals under ThirdParty_staging/audio (gitignored; see docs/M3_AUDIO.md for how
they were fetched and docs/LICENSES.md for every licence). The originals are never modified.

Setup (once), from the project root, in PowerShell:
    python -m venv tools/audio/.venv
    tools/audio/.venv/Scripts/Activate.ps1
    pip install numpy scipy soundfile pyloudnorm
ffmpeg must be on PATH (decoding, resampling and the Ogg Vorbis music sources).

Usage (venv activated):
    python tools/audio/audio_pipeline.py measure <files...>   # one table row per file
    python tools/audio/audio_pipeline.py sfx                  # Assets/ThirdParty/Audio/*.wav + report
    python tools/audio/audio_pipeline.py music                # Assets/ThirdParty/Audio/Music/*.ogg + report
    python tools/audio/audio_pipeline.py all

Processing of every sound effect (docs/audio/AUDIO_REPORT.md section 3):
  decode to 44.1 kHz float, mono downmix (every effect is positional or panned), optional cut, a 30 Hz high pass
  (DC and rumble), optional voicing filter, silence trim (relative threshold), short fades, then loudness
  normalisation to its file target (max momentary loudness, BS.1770, 400 ms window, for one-shots; integrated
  loudness for loops) under a -1 dBTP true peak ceiling (4x oversampled), 16-bit TPDF dithered WAV.
Loops are filtered as three copies end to end and the middle one kept, so the filter adds no seam.
Music: the longest stretch whose next seconds match the seconds after an earlier point (self-similarity of
log band energies, then a sample exact cross-correlation) becomes a seamless loop with a short crossfade.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy import signal

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STAGING = os.path.join(ROOT, "ThirdParty_staging", "audio")
SRC = os.path.join(STAGING, "oga")
MUSIC_SRC = os.path.join(STAGING, "music")
M3_DERIVED = os.path.join(STAGING, "derived")
OUT = os.path.join(ROOT, "Assets", "ThirdParty", "Audio")
MUSIC_OUT = os.path.join(OUT, "Music")
REPORT = os.path.join(ROOT, "tools", "audio", "audio_report.json")
RATE = 44100
TRUE_PEAK_CEILING = -1.0

# File loudness targets. One-shots: max momentary loudness (LUFS-M max); loops and music: integrated (LUFS-I).
# The playback balance is set at run time (AudioLibrary gain to its reference times the Tuning mix of each role):
# these file targets only give every file the same reference and the most headroom under the true peak ceiling.
FILE_TARGET = {
    "oneshot": -12.0,
    "ambience": -30.0,
    "music": -18.0,
}

K_RPG = "50-rpg-sound-effects/x/OGG/"
K_UI = "interface-sounds/x/Audio/"
K_JINGLE = "85-short-music-jingles/x/OGG/"
RD_WM = "100-cc0-metal-and-wood-sfx/x/"
RD_BFH = "75-cc0-breaking-falling-hit-sfx/x/"
RD_100 = "100-cc0-sfx/x/"
SAW = "saw-or-wood-impact/saw_-_starninjas_0.ogg"

# name, source under SRC, cut start s, cut end s (None: to the end), fade in ms, fade out ms, kind, options.
# options: "lowpass" Hz (a muffled variant), "highpass" Hz (instead of 30), "gain_db" (offset from the file target,
# for a variant set that must keep its natural spread), "loop_xfade" s (ambience only), "notrim" (keep as cut),
# "min_len" s (pad a very short blip with trailing silence).
SFX = [
    # The hops (hop_01..04) and the muffled hops (hop_soft_01..04) are made for the game since SOUNDS (2026-11-24) by
    # tools/audio/make_sounds.py, no longer cut from rubberduck's wood hits: not listed here, so "sfx" never overwrites them.
    ("scrape_01", SAW, 1.13, 1.45, 15, 40, "oneshot", {"notrim": True}),
    ("scrape_02", SAW, 1.96, 2.26, 15, 40, "oneshot", {"notrim": True}),
    ("scrape_03", SAW, 2.75, 3.10, 15, 40, "oneshot", {"notrim": True}),
    ("creak_long", RD_100 + "door_02.ogg", 0.04, None, 10, 60, "oneshot", {"highpass": 120}),
    ("creak_short", K_RPG + "creak3.ogg", 0.01, None, 5, 30, "oneshot", {}),
    ("footstep_01", K_RPG + "footstep00.ogg", 0.01, None, 2, 20, "oneshot", {}),
    ("footstep_02", K_RPG + "footstep01.ogg", 0.01, None, 2, 20, "oneshot", {}),
    ("footstep_03", K_RPG + "footstep03.ogg", 0, None, 2, 20, "oneshot", {}),
    ("footstep_04", K_RPG + "footstep07.ogg", 0, None, 2, 20, "oneshot", {}),
    ("footstep_05", K_RPG + "footstep08.ogg", 0, None, 2, 20, "oneshot", {}),
    ("roomtone_airvent_loop", "airvent-loop/airvent-large-loop.wav", 0, None, 0, 0, "ambience", {"loop_xfade": 1.0}),
    ("roomtone_clock_loop", "ticking-clock/ticking_clock.wav", 0, None, 0, 0, "ambience", {}),
    ("thump", "door-open-door-close/x/door/door-05.flac", 0, None, 1, 30, "oneshot", {}),
    # sting_caught and sting_caught_long: made for the game by tools/audio/make_sounds.py since SOUNDS (2026-11-24).
    ("vocal_huh", "huh/huh.wav", 0, None, 5, 20, "oneshot", {"highpass": 150}),
    ("ui_click", K_UI + "click_001.ogg", 0, None, 0, 5, "oneshot", {"notrim": True, "min_len": 0.06}),
    # ----- New recordings replacing a synthesized cue or filling a silent event (AUDIO_REPORT.md section 2) -----
    # The menu's selection tick (hover, arrows, D-pad): Kenney's softest tick, under the click.
    ("ui_hover", K_UI + "tick_001.ogg", 0, None, 0, 5, "oneshot", {"notrim": True, "min_len": 0.06}),
    # The win: Kenney pizzicato jingle 10 (D E F# G, then G held: a resolved rise), the caught sting's opposite and the
    # same plucked strings as the title music.
    ("sting_win", K_JINGLE + "jingles_PIZZA/jingles_PIZZA10.ogg", 0, None, 2, 60, "oneshot", {}),
    # A room door opening (Kenney, a wooden door: latch and swing), replaces the synthesized latch and hinge.
    ("door_open", K_RPG + "doorOpen_1.ogg", 0, None, 2, 60, "oneshot", {}),
    # The wardrobe: a wooden box lid opening as the doors swing, a light wooden close when they shut.
    ("wardrobe_open", RD_100 + "wooded_box_open.ogg", 0, None, 2, 40, "oneshot", {}),
    ("wardrobe_close", RD_WM + "wood_close_01.ogg", 0, None, 1, 40, "oneshot", {}),
    # The fallen load (vase, pot): breaking dishes, replaces the synthesized knock and shards.
    ("crash", RD_100 + "dishes_01.ogg", 0, None, 1, 80, "oneshot", {}),
    # The stool tipping over: a wooden object falling (wood_falling_01 clips at the source, _02 does not).
    ("topple", RD_WM + "wood_falling_02.ogg", 0, None, 1, 60, "oneshot", {}),
    # The floor lamp's switch: a recorded switch (press and release).
    ("lamp_click", RD_100 + "switch_02.ogg", 0, None, 1, 20, "oneshot", {}),
]

# Music: name, source under MUSIC_SRC, shortest loop s, crossfade s, the measured loop is reported.
# Kevin MacLeod (incompetech.com), CC BY 4.0, downloaded from
# https://incompetech.com/music/royalty-free/mp3-royaltyfree/<title>.mp3 (sha256 in docs/audio/AUDIO_REPORT.md).
# "Cool Vibes" (a slow jazz trio) was tried for the level and rejected: played loosely, its best loop point only
# correlates 0.59 at the sample level (Investigations: 0.988).
MUSIC = [
    ("music_title", "Sneaky Snitch.mp3", 50.0, 0.12),
    ("music_level", "Investigations.mp3", 30.0, 0.12),
]


# ----------------------------------------------------------------------------------------------------- decoding

def decode(path, channels=1, rate=RATE):
    """Any file ffmpeg reads, as float32 (frames, channels) at `rate`."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", str(channels), "-ar", str(rate),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, channels).astype(np.float64)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                          "stream=codec_name,sample_rate,channels,bits_per_sample:format=duration",
                          "-of", "json", path], capture_output=True, check=True).stdout
    j = json.loads(out)
    s = j["streams"][0]
    return {"codec": s.get("codec_name"), "rate": int(s.get("sample_rate", 0)), "channels": int(s.get("channels", 0)),
            "duration": float(j["format"].get("duration", 0.0))}


# -------------------------------------------------------------------------------------------------- measuring

def db(x):
    return float(20 * np.log10(x)) if x > 1e-12 else -240.0


def k_weight(x, rate):
    """BS.1770 K-weighting (pyloudnorm's two stage filter), per channel."""
    meter = pyln.Meter(rate)
    y = x.copy()
    for f in meter._filters.values():
        y = f.apply_filter(y)
    return y


def momentary_max(x, rate):
    """Max momentary loudness (LUFS, 400 ms window, 10 ms hop); a clip shorter than 400 ms is padded with silence."""
    n = int(0.4 * rate)
    if len(x) < n:
        x = np.vstack([x, np.zeros((n - len(x), x.shape[1]))])
    y = k_weight(x, rate)
    power = np.sum(y * y, axis=1)
    c = np.concatenate([[0.0], np.cumsum(power)])
    hop = int(0.01 * rate)
    starts = np.arange(0, len(power) - n + 1, hop)
    ms = (c[starts + n] - c[starts]) / n
    return float(-0.691 + 10 * np.log10(max(ms.max(), 1e-20)))


def short_max(x, rate, window=0.1):
    """Max K-weighted loudness over a 100 ms sliding window (LUFS scale), the one-shot loudness of this pipeline.

    The 400 ms momentary window under-reads short impacts (a 0.13 s knock reads 8 dB under a 0.22 s one of the same
    peak and energy density); 100 ms is close to the ear's own integration time for short sounds, so variants matched
    on it sound matched. A clip shorter than the window is padded with silence.
    """
    n = int(window * rate)
    if len(x) < n:
        x = np.vstack([x, np.zeros((n - len(x), x.shape[1]))])
    y = k_weight(x, rate)
    power = np.sum(y * y, axis=1)
    c = np.concatenate([[0.0], np.cumsum(power)])
    hop = int(0.005 * rate)
    starts = np.arange(0, len(power) - n + 1, hop)
    ms = (c[starts + n] - c[starts]) / n
    return float(-0.691 + 10 * np.log10(max(ms.max(), 1e-20)))


def integrated(x, rate):
    if len(x) < int(0.4 * rate):
        return None
    v = pyln.Meter(rate).integrated_loudness(x)
    return float(v) if np.isfinite(v) else None


def true_peak(x):
    up = signal.resample_poly(x, 4, 1, axis=0)
    return db(float(np.max(np.abs(up))))


def frame_rms_db(mono, rate, ms=20):
    n = max(1, int(rate * ms / 1000))
    k = len(mono) // n
    if k == 0:
        return np.array([db(float(np.sqrt(np.mean(mono ** 2))))])
    f = mono[:k * n].reshape(k, n)
    return 20 * np.log10(np.maximum(np.sqrt(np.mean(f * f, axis=1)), 1e-12))


def edges(mono, rate, rel_db=45.0, floor_db=-70.0):
    """First and last sample above max(peak - rel_db, floor_db) on a 5 ms envelope."""
    env = np.sqrt(signal.convolve(mono ** 2, np.ones(int(0.005 * rate)) / int(0.005 * rate), mode="same"))
    peak = env.max() if len(env) else 0.0
    thr = max(peak * 10 ** (-rel_db / 20), 10 ** (floor_db / 20))
    above = np.nonzero(env > thr)[0]
    if len(above) == 0:
        return 0, len(mono)
    return int(above[0]), int(above[-1]) + 1


def measure_array(x, rate):
    mono = x.mean(axis=1)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    frames = frame_rms_db(mono, rate)
    first, last = edges(mono, rate)
    clipped = int(np.sum(np.abs(x) >= 0.999))
    return {
        "duration": round(len(x) / rate, 3),
        "peak_dbfs": round(db(peak), 1),
        "true_peak_dbtp": round(true_peak(x), 1),
        "lufs_i": None if integrated(x, rate) is None else round(integrated(x, rate), 1),
        "lufs_m_max": round(momentary_max(x, rate), 1),
        "lufs_100ms_max": round(short_max(x, rate), 1),
        "dc": round(float(np.mean(mono)), 5),
        "clipped_samples": clipped,
        "noise_floor_dbfs": round(float(np.percentile(frames, 10)), 1),
        "lead_silence_ms": round(first / rate * 1000, 1),
        "trail_silence_ms": round((len(mono) - last) / rate * 1000, 1),
    }


def measure_file(path):
    info = probe(path)
    ch = max(1, min(2, info["channels"]))
    x = decode(path, channels=ch, rate=info["rate"] or RATE)
    m = measure_array(x, info["rate"] or RATE)
    m.update({"file": os.path.relpath(path, ROOT).replace("\\", "/"), "codec": info["codec"], "rate": info["rate"],
              "channels": info["channels"]})
    return m


# ------------------------------------------------------------------------------------------------- processing

def butter(x, kind, hz, order=2):
    sos = signal.butter(order, hz, btype=kind, fs=RATE, output="sos")
    return signal.sosfilt(sos, x, axis=0)


def filter_loop(x, fn):
    """Applies fn to three copies of a loop end to end and keeps the middle one: no seam from the filter state."""
    y = fn(np.vstack([x, x, x]))
    return y[len(x):2 * len(x)]


def fade(x, fade_in_ms, fade_out_ms):
    n_in = int(RATE * fade_in_ms / 1000)
    n_out = int(RATE * fade_out_ms / 1000)
    if n_in > 0:
        x[:n_in] *= (np.sin(np.linspace(0, np.pi / 2, n_in)) ** 2)[:, None]
    if n_out > 0:
        x[-n_out:] *= (np.cos(np.linspace(0, np.pi / 2, n_out)) ** 2)[:, None]
    return x


def loop_crossfade(x, seconds):
    """Equal power crossfade of the last `seconds` into the first: out[-1] flows into out[0]."""
    n = int(RATE * seconds)
    head, tail, body = x[:n], x[-n:], x[n:-n]
    t = np.linspace(0, np.pi / 2, n)[:, None]
    blended = tail * np.cos(t) + head * np.sin(t)
    return np.vstack([body, blended])


def normalize(x, target, kind):
    """Gain to the file target, limited by the true peak ceiling. Returns (y, gain_db, limited)."""
    now = integrated(x, RATE) if kind != "oneshot" else short_max(x, RATE)
    want = target - now
    room = TRUE_PEAK_CEILING - true_peak(x)
    gain = min(want, room)
    return x * 10 ** (gain / 20), gain, room < want


def dither16(x, seed):
    rng = np.random.default_rng(seed)
    tpdf = (rng.random(x.shape) - rng.random(x.shape)) / 32768.0
    return np.clip(x + tpdf, -1.0, 32767 / 32768)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def build_sfx(report):
    os.makedirs(OUT, exist_ok=True)
    # "Before": the M3 clips as tools/assets/audio_derive.py made them (what shipped until this pipeline).
    before = {}
    for name, *_ in SFX:
        old = os.path.join(M3_DERIVED, name + ".wav")
        if os.path.exists(old):
            before[name] = measure_file(old)
    rows = []
    for i, (name, src, start, end, fin, fout, kind, opt) in enumerate(SFX):
        path = os.path.join(SRC, src)
        x = decode(path, channels=1)
        a = int(start * RATE)
        b = len(x) if end is None else int(end * RATE)
        x = x[a:b]
        hp = opt.get("highpass", 30)
        lp = opt.get("lowpass")
        if kind == "ambience":
            x = filter_loop(x, lambda v: butter(v, "highpass", hp))
            if opt.get("loop_xfade"):
                x = loop_crossfade(x, opt["loop_xfade"])
        else:
            x = butter(x, "highpass", hp)
            if lp:
                x = butter(x, "lowpass", lp, order=4)
            trimmed_lead = 0
            if not opt.get("notrim"):
                first, last = edges(x[:, 0], RATE)
                first = max(0, first - int(0.003 * RATE))
                last = min(len(x), last + int(0.010 * RATE))
                trimmed_lead = first
                x = x[first:last]
            # A clip cut inside the sound gets a fade in; one that starts on silence keeps its attack.
            x = fade(x, fin if (a > 0 or trimmed_lead > 0 or opt.get("notrim")) else min(fin, 1), fout)
            # A UI blip shorter than the game's "not empty" floor (50 ms, ProbeTestsM3Audio) gets trailing silence.
            if opt.get("min_len") and len(x) < int(opt["min_len"] * RATE):
                x = np.vstack([x, np.zeros((int(opt["min_len"] * RATE) - len(x), x.shape[1]))])
        y, gain, limited = normalize(x, FILE_TARGET[kind] + opt.get("gain_db", 0.0), kind)
        out = os.path.join(OUT, name + ".wav")
        sf.write(out, dither16(y, i)[:, 0], RATE, subtype="PCM_16")
        after = measure_file(out)
        loud = after["lufs_i"] if kind == "ambience" else after["lufs_100ms_max"]
        rows.append({"name": name, "source": src, "kind": kind, "gain_db": round(gain, 2), "peak_limited": bool(limited),
                     "loudness": loud, "before": before.get(name), "after": after, "sha256": sha(out)})
        print(f"{name:24s} {kind:9s} gain {gain:+6.2f} dB {'(TP limited)' if limited else '':13s}"
              f" {after['duration']:6.3f} s  100ms {after['lufs_100ms_max']:6.1f}  M max {after['lufs_m_max']:6.1f}"
              f"  I {after['lufs_i']}  TP {after['true_peak_dbtp']}")
    report["sfx"] = rows


# ------------------------------------------------------------------------------------------------------ music

def band_features(mono, hop=2048, nfft=4096, bands=40):
    f, t, z = signal.stft(mono, fs=RATE, nperseg=nfft, noverlap=nfft - hop, boundary=None, padded=False)
    mag = np.abs(z)
    edges_hz = np.geomspace(60, 12000, bands + 1)
    feats = np.zeros((bands, mag.shape[1]))
    for k in range(bands):
        sel = (f >= edges_hz[k]) & (f < edges_hz[k + 1])
        if sel.any():
            feats[k] = np.log1p(100 * mag[sel].mean(axis=0))
    feats -= feats.mean(axis=0, keepdims=True)
    feats /= np.maximum(np.linalg.norm(feats, axis=0, keepdims=True), 1e-9)
    return feats.T, hop


def find_loop(x, min_len_s, window_s=6.0, edge_s=6.0):
    """(t1, t2) in samples: the audio after t2 matches the audio after t1, t2 - t1 >= min_len_s, as long as possible."""
    mono = x.mean(axis=1)
    feats, hop = band_features(mono)
    n = len(feats)
    w = int(window_s * RATE / hop)
    e = int(edge_s * RATE / hop)
    lmin = int(min_len_s * RATE / hop)
    best = []
    kernel = np.ones(w) / w
    for lag in range(lmin, n - 2 * e - w):
        sim = np.sum(feats[:-lag] * feats[lag:], axis=1)
        # A window centred on the loop point: what leads into it and what follows must both match.
        avg = np.convolve(sim, kernel, mode="valid")
        lo, hi = e, n - lag - e - w
        if hi <= lo:
            continue
        i = lo + int(np.argmax(avg[lo:hi]))
        best.append((float(avg[i]), lag, i))
    top = max(s for s, _, _ in best)
    good = [c for c in best if c[0] >= top - 0.01]
    score, lag, i = max(good, key=lambda c: c[1])
    t1 = (i + w // 2) * hop
    t2 = t1 + lag * hop
    # Sample exact lag: normalized cross-correlation of 1 s after each point, within +-2 hops.
    seg = int(1.0 * RATE)
    ref = mono[t1:t1 + seg]
    span = 2 * hop
    cand = mono[t2 - span:t2 + span + seg]
    corr = signal.correlate(cand, ref, mode="valid")
    norms = np.sqrt(np.convolve(cand ** 2, np.ones(seg), mode="valid")) * np.linalg.norm(ref)
    ncc = corr / np.maximum(norms, 1e-12)
    k = int(np.argmax(ncc))
    t2 = t2 - span + k
    return t1, t2, score, float(ncc[k])


def build_music(report):
    os.makedirs(MUSIC_OUT, exist_ok=True)
    rows = []
    for name, src, min_len, xfade in MUSIC:
        path = os.path.join(MUSIC_SRC, src)
        source = measure_file(path)
        x = decode(path, channels=2)
        x = butter(x, "highpass", 25)
        t1, t2, score, ncc = find_loop(x, min_len)
        n = int(xfade * RATE)
        loop = x[t1:t2].copy()
        t = np.linspace(0, np.pi / 2, n)[:, None]
        # The loop's last n samples cross into the n samples that led into t1, so its end flows into its start.
        loop[-n:] = x[t2 - n:t2] * np.cos(t) + x[t1 - n:t1] * np.sin(t)
        # Seam check: the jump at the wrap against the typical sample to sample step.
        jump = float(np.max(np.abs(loop[0] - loop[-1])))
        typical = float(np.percentile(np.abs(np.diff(loop[:, 0])), 99))
        y, gain, limited = normalize(loop, FILE_TARGET["music"], "music")
        wav = os.path.join(MUSIC_SRC, name + "_loop.wav")
        sf.write(wav, y, RATE, subtype="FLOAT")
        out = os.path.join(MUSIC_OUT, name + ".ogg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libvorbis", "-q:a", "6", out], check=True)
        after = measure_file(out)
        rows.append({"name": name, "source": src, "loop_start_s": round(t1 / RATE, 3), "loop_end_s": round(t2 / RATE, 3),
                     "loop_length_s": round((t2 - t1) / RATE, 3), "similarity": round(score, 4), "seam_ncc": round(ncc, 4),
                     "seam_jump": round(jump, 4), "typical_step_p99": round(typical, 4), "gain_db": round(gain, 2),
                     "peak_limited": bool(limited), "before": source, "after": after, "sha256": sha(out)})
        print(f"{name}: loop {t1 / RATE:.2f}-{t2 / RATE:.2f} s ({(t2 - t1) / RATE:.1f} s) similarity {score:.3f} "
              f"seam ncc {ncc:.3f} jump {jump:.4f} (p99 step {typical:.4f}) I {after['lufs_i']} TP {after['true_peak_dbtp']}"
              f" size {os.path.getsize(out) // 1024} KB")
    report["music"] = rows


# --------------------------------------------------------------------------------------------------------- cli

def load_report():
    if os.path.exists(REPORT):
        with open(REPORT, encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("command", choices=["measure", "sfx", "music", "all"])
    p.add_argument("files", nargs="*")
    a = p.parse_args()
    if a.command == "measure":
        keys = ["duration", "rate", "channels", "peak_dbfs", "true_peak_dbtp", "lufs_i", "lufs_m_max", "clipped_samples",
                "noise_floor_dbfs", "lead_silence_ms", "trail_silence_ms", "dc"]
        print("file\t" + "\t".join(keys))
        for f in a.files:
            m = measure_file(f)
            print(os.path.basename(f) + "\t" + "\t".join(str(m[k]) for k in keys))
        return
    report = load_report()
    report["file_targets"] = FILE_TARGET
    report["true_peak_ceiling_dbtp"] = TRUE_PEAK_CEILING
    if a.command in ("sfx", "all"):
        build_sfx(report)
    if a.command in ("music", "all"):
        build_music(report)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print("report:", os.path.relpath(REPORT, ROOT))


if __name__ == "__main__":
    sys.exit(main())
