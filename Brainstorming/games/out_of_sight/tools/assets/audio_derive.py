"""Build import-ready clips from the M3 audio picks (docs/M3_AUDIO.md), stdlib + ffmpeg only.

Every pick is decoded by ffmpeg to mono 44.1 kHz float, optionally trimmed, faded, loudness matched
(active RMS target with a peak ceiling) or turned into a seamless loop by an equal power crossfade
of its tail into its head, then written as 16 bit mono WAV to ThirdParty_staging/audio/derived/.
The originals are never modified. Run with python -I: the inputs are untrusted downloads.

Usage: python -I tools/assets/audio_derive.py
"""
import array
import hashlib
import json
import math
import os
import subprocess
import wave

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "ThirdParty_staging", "audio", "oga")
OUT = os.path.join(ROOT, "ThirdParty_staging", "audio", "derived")
RATE = 44100
CEILING_DB = -1.0

K_RPG = "50-rpg-sound-effects/x/OGG/"
RD_WM = "100-cc0-metal-and-wood-sfx/x/"
RD_BFH = "75-cc0-breaking-falling-hit-sfx/x/"
SAW = "saw-or-wood-impact/saw_-_starninjas_0.ogg"

# name, source, start s, end s (None = to the end), fade in ms, fade out ms, target active RMS dBFS
# (None = peak normalize to the ceiling), loop crossfade s (0 = one shot)
PICKS = [
    ("hop_01", RD_BFH + "bfh1_wood_hit_01.ogg", 0, None, 0, 10, -16, 0),
    ("hop_02", RD_BFH + "bfh1_wood_hit_02.ogg", 0, None, 0, 10, -16, 0),
    ("hop_03", RD_WM + "wood_hit_05.ogg", 0.03, None, 2, 10, -16, 0),
    ("hop_04", RD_WM + "wood_hit_09.ogg", 0.01, None, 2, 10, -16, 0),
    ("scrape_01", SAW, 1.13, 1.45, 15, 40, -18, 0),
    ("scrape_02", SAW, 1.96, 2.26, 15, 40, -18, 0),
    ("scrape_03", SAW, 2.75, 3.10, 15, 40, -18, 0),
    ("creak_long", "100-cc0-sfx/x/door_02.ogg", 0.04, None, 10, 60, -18, 0),
    ("creak_short", K_RPG + "creak3.ogg", 0.01, None, 5, 30, -18, 0),
    ("footstep_01", K_RPG + "footstep00.ogg", 0.01, None, 2, 20, -18, 0),
    ("footstep_02", K_RPG + "footstep01.ogg", 0.01, None, 2, 20, -18, 0),
    ("footstep_03", K_RPG + "footstep03.ogg", 0, None, 2, 20, -18, 0),
    ("footstep_04", K_RPG + "footstep07.ogg", 0, None, 2, 20, -18, 0),
    ("footstep_05", K_RPG + "footstep08.ogg", 0, None, 2, 20, -18, 0),
    ("thump", "door-open-door-close/x/door/door-05.flac", 0, None, 0, 30, -16, 0),
    ("sting_caught", "85-short-music-jingles/x/OGG/jingles_SAX/jingles_SAX05.ogg", 0.01, None, 3, 30, -16, 0),
    ("sting_caught_long", "game-over-trumpet-sfx/losetrumpet.wav", 0, None, 3, 40, -16, 0),
    ("vocal_huh", "huh/huh.wav", 0, None, 5, 20, -18, 0),
    ("ui_click", "interface-sounds/x/Audio/click_001.ogg", 0, None, 0, 5, None, 0),
    ("roomtone_airvent_loop", "airvent-loop/airvent-large-loop.wav", 0, None, 0, 0, -30, 1.0),
    ("roomtone_clock_loop", "ticking-clock/ticking_clock.wav", 0, None, 0, 0, -30, 0),
]


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    a = array.array("f")
    a.frombytes(raw)
    return list(a)


def db(x):
    return 20 * math.log10(x) if x > 1e-12 else -240.0


def active_rms(x):
    fl = int(RATE * 0.02)
    frames = [math.sqrt(math.fsum(v * v for v in x[i:i + fl]) / len(x[i:i + fl])) for i in range(0, len(x), fl)]
    loud = max(frames)
    act = [f for f in frames if f > loud * 10 ** (-30 / 20)]
    return math.sqrt(math.fsum(f * f for f in act) / len(act))


def loop_crossfade(x, seconds):
    """Equal power crossfade of the last `seconds` into the first: out[-1] flows into out[0]."""
    n = int(RATE * seconds)
    head, tail = x[:n], x[len(x) - n:]
    body = x[n:len(x) - n]
    fade = [math.sin(0.5 * math.pi * i / n) * h + math.cos(0.5 * math.pi * i / n) * t
            for i, (h, t) in enumerate(zip(head, tail))]
    # The tail now leads into the crossfaded head, so the loop is body + crossfade.
    return body + fade


def write_wav(path, x):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(array.array("h", (max(-32767, min(32767, round(v * 32767))) for v in x)).tobytes())


def main():
    os.makedirs(OUT, exist_ok=True)
    report = []
    for name, src, start, end, fin, fout, target, xfade in PICKS:
        x = decode(os.path.join(SRC, src))
        s = int(start * RATE)
        e = len(x) if end is None else min(len(x), int(end * RATE))
        x = x[s:e]
        if xfade:
            x = loop_crossfade(x, xfade)
        n_in, n_out = int(RATE * fin / 1000), int(RATE * fout / 1000)
        for i in range(min(n_in, len(x))):
            x[i] *= i / n_in
        for i in range(min(n_out, len(x))):
            x[len(x) - 1 - i] *= i / n_out
        peak = max(abs(v) for v in x)
        if target is None:
            gain_db = CEILING_DB - db(peak)
        else:
            gain_db = min(target - db(active_rms(x)), CEILING_DB - db(peak))
        g = 10 ** (gain_db / 20)
        x = [v * g for v in x]
        out = os.path.join(OUT, name + ".wav")
        write_wav(out, x)
        with open(out, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
        report.append({"name": name, "source": src, "trim_s": [start, end], "fade_ms": [fin, fout],
                       "loop_crossfade_s": xfade, "gain_db": round(gain_db, 1),
                       "duration_s": round(len(x) / RATE, 3), "peak_dbfs": round(db(max(abs(v) for v in x)), 1),
                       "active_rms_dbfs": round(db(active_rms(x)), 1), "seam_jump": round(abs(x[-1] - x[0]), 4),
                       "bytes": os.path.getsize(out), "sha256": sha})
        r = report[-1]
        print(f'{name:24} {r["duration_s"]:6.3f}s gain {r["gain_db"]:+5.1f} pk {r["peak_dbfs"]:5.1f} '
              f'act {r["active_rms_dbfs"]:6.1f} seam {r["seam_jump"]:.4f} {r["bytes"]:>8} B')
    with open(os.path.join(OUT, "derived.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
