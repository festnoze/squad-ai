"""Measure audio files for docs/M3_AUDIO.md (stdlib only, run with python -I: inputs are untrusted).

For each file: container and codec (ffprobe), WAV header (wave module), duration, sample rate,
channels, peak and RMS in dBFS, "active" RMS (RMS of the 20 ms frames within 30 dB of the loudest
frame), leading and trailing silence, number of transients, zero crossing rate (a brightness
proxy), a 24 bin loudness envelope, and for loops the seam (sample jump and level step between the
end and the start).

Decoding goes through ffmpeg to 32 bit float PCM at the native rate and channel count, so OGG,
FLAC, AIFF and MP3 are measured the same way as WAV.

Usage: python -I tools/assets/audio_measure.py [--json OUT] FILE [FILE ...]
"""
import array
import json
import math
import os
import subprocess
import sys
import wave

FRAME_S = 0.02
BARS = " .:-=+*#%@"


def db(x):
    return 20.0 * math.log10(x) if x > 1e-9 else -180.0


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_name,sample_rate,channels,bits_per_sample,bit_rate,sample_fmt:format=duration,format_name,bit_rate",
         "-of", "json", path],
        capture_output=True, check=True).stdout
    info = json.loads(out)
    st = info["streams"][0]
    return {
        "container": info["format"].get("format_name"),
        "codec": st.get("codec_name"),
        "sample_fmt": st.get("sample_fmt"),
        "bits": int(st.get("bits_per_sample") or 0) or None,
        "rate": int(st["sample_rate"]),
        "channels": int(st["channels"]),
        "bitrate_kbps": round(int(st.get("bit_rate") or info["format"].get("bit_rate") or 0) / 1000) or None,
    }


def wav_header(path):
    try:
        with wave.open(path, "rb") as w:
            return {"rate": w.getframerate(), "channels": w.getnchannels(), "sampwidth_bits": w.getsampwidth() * 8,
                    "frames": w.getnframes(), "duration": round(w.getnframes() / w.getframerate(), 3)}
    except (wave.Error, EOFError) as e:
        return {"error": str(e)}


def decode(path, channels):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-acodec", "pcm_f32le", "-"],
                         capture_output=True, check=True).stdout
    a = array.array("f")
    a.frombytes(raw[: len(raw) - len(raw) % (4 * channels)])
    return a


def measure(path):
    p = probe(path)
    rate, ch = p["rate"], p["channels"]
    a = decode(path, ch)
    n = len(a) // ch
    res = {"file": path.replace("\\", "/"), **p, "duration": round(n / rate, 3), "bytes": os.path.getsize(path)}
    if path.lower().endswith(".wav"):
        res["wav_header"] = wav_header(path)
    if n == 0:
        return res
    peak = max(abs(min(a)), abs(max(a)))
    sq = math.fsum(x * x for x in a)
    res["peak_dbfs"] = round(db(peak), 1)
    res["rms_dbfs"] = round(db(math.sqrt(sq / len(a))), 1)
    # Mono loudness per 20 ms frame.
    fl = max(1, int(rate * FRAME_S))
    frames = []
    for i in range(0, n, fl):
        seg = a[i * ch:min(n, i + fl) * ch]
        frames.append(math.sqrt(math.fsum(x * x for x in seg) / max(1, len(seg))))
    loud = max(frames)
    active = [f for f in frames if f > loud * 10 ** (-30 / 20)]
    res["active_rms_dbfs"] = round(db(math.sqrt(math.fsum(f * f for f in active) / len(active))), 1)
    gate = loud * 10 ** (-40 / 20)
    first = next(i for i, f in enumerate(frames) if f > gate)
    last = len(frames) - 1 - next(i for i, f in enumerate(reversed(frames)) if f > gate)
    res["lead_silence_ms"] = round(first * FRAME_S * 1000)
    res["tail_silence_ms"] = round((len(frames) - 1 - last) * FRAME_S * 1000)
    res["sounding_s"] = round((last - first + 1) * FRAME_S, 2)
    # Transients: frames rising at least 9 dB over the frame before and within 20 dB of the loudest.
    hits = 0
    for i in range(1, len(frames)):
        if frames[i] > loud * 0.1 and frames[i] > frames[i - 1] * 2.8 and (i < 3 or frames[i] > max(frames[i - 3:i]) * 2.0):
            hits += 1
    res["transients"] = hits
    # Zero crossings per second on the first channel, over the sounding part only.
    s0, s1 = first * fl, min(n, (last + 1) * fl)
    zc = sum(1 for i in range(s0 + 1, s1) if (a[(i - 1) * ch] >= 0) != (a[i * ch] >= 0))
    res["zcr_hz"] = round(zc / max(1e-6, (s1 - s0) / rate) / 2)
    # 24 bin envelope, relative to the loudest frame, 0 to 9 over a 40 dB range.
    bins = 24
    env = ""
    for b in range(bins):
        lo, hi = b * len(frames) // bins, max(b * len(frames) // bins + 1, (b + 1) * len(frames) // bins)
        v = max(frames[lo:hi])
        level = 0 if v <= gate else min(9, int((db(v) - db(gate)) / 40 * 9.999))
        env += BARS[level]
    res["envelope"] = env
    # Loop seam: jump from the last sample back to the first, and the level step across the seam.
    w = max(1, int(rate * 0.1))
    head = math.sqrt(math.fsum(x * x for x in a[: w * ch]) / (w * ch))
    tail = math.sqrt(math.fsum(x * x for x in a[(n - w) * ch:]) / (w * ch))
    res["seam_jump"] = round(max(abs(a[(n - 1) * ch + c] - a[c]) for c in range(ch)), 4)
    res["seam_step_db"] = round(db(tail) - db(head), 1)
    if ch == 2:
        diff = math.fsum((a[2 * i] - a[2 * i + 1]) ** 2 for i in range(n))
        res["stereo_side_db"] = round(db(math.sqrt(diff / n / 2)) - db(math.sqrt(sq / len(a))), 1)
    return res


def main(argv):
    out = None
    if argv and argv[0] == "--json":
        out, argv = argv[1], argv[2:]
    rows = []
    for path in argv:
        try:
            r = measure(path)
        except Exception as e:  # noqa: BLE001 - report the file and keep going
            r = {"file": path, "error": str(e)}
        rows.append(r)
        if "error" in r:
            print("ERR", path, r["error"])
            continue
        print(f'{os.path.basename(path)[:44]:44} {r["codec"]:>9} {r["rate"]:>6} {r["channels"]}ch '
              f'{r["duration"]:7.3f}s pk{r.get("peak_dbfs", 0):6.1f} rms{r.get("rms_dbfs", 0):6.1f} '
              f'act{r.get("active_rms_dbfs", 0):6.1f} lead{r.get("lead_silence_ms", 0):5} '
              f'tail{r.get("tail_silence_ms", 0):5} hits{r.get("transients", 0):3} zcr{r.get("zcr_hz", 0):6} '
              f'|{r.get("envelope", "")}|')
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1:])
