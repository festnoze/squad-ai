"""Spectrogram contact sheet for listening-free review (docs/M3_AUDIO.md).

Renders one mono spectrogram per file (log frequency 50 Hz to 12 kHz, 90 dB range) with ffmpeg
(rendered 1024 px tall then shrunk: showspectrumpic sizes its FFT from the height),
stacks them vertically in the given order into one PNG, and prints the row order. Each row is
padded or trimmed to the same duration so time reads the same across rows.

Usage: python -I tools/assets/audio_sheet.py OUT.png SECONDS FILE [FILE ...]
"""
import os
import subprocess
import sys
import tempfile


def main(out, seconds, files):
    tmp = tempfile.mkdtemp(prefix="sheet_")
    rows = []
    for i, f in enumerate(files):
        png = os.path.join(tmp, f"{i:02d}.png")
        flt = (f"[0:a]aformat=channel_layouts=mono,apad,atrim=0:{seconds},"
               f"showspectrumpic=s=600x1024:legend=0:fscale=log:start=50:stop=12000:drange=90:color=intensity,scale=600:120[v]")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f, "-filter_complex", flt, "-map", "[v]",
                        "-frames:v", "1", png], check=True)
        rows.append(png)
        print(f"row {i + 1}: {os.path.basename(f)}")
    args = ["ffmpeg", "-v", "error", "-y"]
    for r in rows:
        args += ["-i", r]
    pad = "".join(f"[{i}:v]pad=iw:ih+4:0:0:white[p{i}];" for i in range(len(rows)))
    stack = "".join(f"[p{i}]" for i in range(len(rows)))
    args += ["-filter_complex", f"{pad}{stack}vstack=inputs={len(rows)}[v]" if len(rows) > 1 else "[0:v]copy[v]",
             "-map", "[v]", out]
    subprocess.run(args, check=True)


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]), sys.argv[3:])
