"""Timed frame sequence of a DevShot run (elec-arcs, wave D F3): judge the interior arcs' flicker frame by frame.

usage: python seqcap.py <exe> <outdir> <quality> <W> <H> <start_s> <end_s> <x0> <y0> <x1> <y1> [<sheet_frames>]

Launches "<exe> -devshot <outdir>/ds -biome electric", grabs the window's client area as fast as it can between
start_s and end_s after launch (frames fNNNN_<ms>.png), then writes sheet.png: the box (x0, y0, x1, y1) of
<sheet_frames> consecutive frames (default 16) from the middle of the run, each labelled with its time, plus
timing.txt (frame count, mean interval). Based on docs/waveC/biome-electric-liquid/tools/seqcap.py.
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageGrab

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32 = ctypes.windll.user32
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def find_window(pid):
    found = []

    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            r = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(r))
            if r.right > 100:
                found.append(hwnd)
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return found[0] if found else None


def main():
    exe, out, quality, w, h, t0, t1 = sys.argv[1:8]
    box = tuple(int(v) for v in sys.argv[8:12])
    count = int(sys.argv[12]) if len(sys.argv) > 12 else 16
    w, h, t0, t1 = int(w), int(h), float(t0), float(t1)
    os.makedirs(out, exist_ok=True)
    args = [exe, "-devshot", os.path.join(out, "ds"), "-biome", "electric", "-screen-width", str(w), "-screen-height",
            str(h), "-screen-fullscreen", "0", "-logFile", os.path.join(out, "p.log")]
    if quality != "default":
        args += ["-quality", quality]
    start = time.perf_counter()
    proc = subprocess.Popen(args)
    hwnd = None
    frames = []
    while proc.poll() is None:
        now = time.perf_counter() - start
        if hwnd is None:
            hwnd = find_window(proc.pid)
            if hwnd is None:
                time.sleep(0.05)
                continue
        if now < t0:
            time.sleep(0.005)
            continue
        if now > t1:
            break
        r = wt.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(r))
        pt = wt.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)
        frames.append((now, ImageGrab.grab(bbox=(pt.x, pt.y, pt.x + r.right, pt.y + r.bottom), all_screens=True)))
    proc.wait(timeout=240)
    for i, (t, img) in enumerate(frames):
        img.save(os.path.join(out, "f%04d_%05d.png" % (i, int(t * 1000))))
    if len(frames) < 2:
        print("frames", len(frames))
        return
    span = frames[-1][0] - frames[0][0]
    mean = span / (len(frames) - 1)
    with open(os.path.join(out, "timing.txt"), "w") as f:
        f.write("frames %d span %.2f-%.2f s mean interval %.1f ms (%.1f fps)\n"
                % (len(frames), frames[0][0], frames[-1][0], mean * 1000, 1.0 / mean))
    first = max(0, len(frames) // 2 - count // 2)
    pick = frames[first:first + count]
    tiles = []
    for t, img in pick:
        c = img.crop(box)
        lab = Image.new("RGB", (c.width, c.height + 18), (12, 14, 24))
        lab.paste(c, (0, 18))
        ImageDraw.Draw(lab).text((4, 3), "%.3f s" % t, fill=(235, 235, 235))
        tiles.append(lab)
    cols = 8
    rows = (len(tiles) + cols - 1) // cols
    tw, th = tiles[0].width, tiles[0].height
    sheet = Image.new("RGB", (cols * tw + (cols - 1) * 4, rows * th + (rows - 1) * 4), (40, 40, 40))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % cols) * (tw + 4), (i // cols) * (th + 4)))
    sheet.save(os.path.join(out, "sheet.png"))
    print("frames %d, mean interval %.1f ms" % (len(frames), mean * 1000))


if __name__ == "__main__":
    main()
