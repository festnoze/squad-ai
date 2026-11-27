"""Launch a DevShot run and grab its window's client area as fast as possible, to look at an animation frame by frame.

usage: python seqcap.py exe outdir biome quality W H start_s end_s
Frames between start_s and end_s after launch are kept (named fNNNN_<ms>.png) plus a contact sheet."""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

from PIL import Image, ImageGrab, ImageDraw

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32 = ctypes.windll.user32

exe, out, biome, quality, W, H, t0, t1 = sys.argv[1:9]
W, H, t0, t1 = int(W), int(H), float(t0), float(t1)
os.makedirs(out, exist_ok=True)
args = [exe, "-devshot", os.path.join(out, "ds"), "-biome", biome, "-screen-width", str(W), "-screen-height", str(H),
        "-screen-fullscreen", "0", "-logFile", os.path.join(out, "p.log")]
if quality != "default":
    args += ["-quality", quality]
start = time.perf_counter()
proc = subprocess.Popen(args)

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
    img = ImageGrab.grab(bbox=(pt.x, pt.y, pt.x + r.right, pt.y + r.bottom), all_screens=True)
    frames.append((now, img))
proc.wait(timeout=240)
for i, (t, img) in enumerate(frames):
    img.save(os.path.join(out, "f%04d_%05d.png" % (i, int(t * 1000))))
print("frames", len(frames), "span %.2f-%.2f s" % (frames[0][0], frames[-1][0]) if frames else "")
