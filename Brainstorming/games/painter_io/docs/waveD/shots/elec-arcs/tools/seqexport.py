"""Exports part of a seqcap.py sequence (elec-arcs, wave D F3): cropped frames, a contact sheet and a GIF.

usage: python seqexport.py <seqdir> <outdir> <t_start_s> <count> <x0> <y0> <x1> <y1>
Takes <count> consecutive frames from the first one at or after t_start, crops the box, and writes
<outdir>/frames/cNN_<ms>.png, <outdir>/sheet.png (8 per row, labelled with the capture time) and <outdir>/arcs.gif
(each frame shown for its real capture interval, so the GIF plays at the captured speed).
"""
import glob
import os
import sys

from PIL import Image, ImageDraw


def main():
    src, out, t0, count = sys.argv[1], sys.argv[2], float(sys.argv[3]), int(sys.argv[4])
    box = tuple(int(v) for v in sys.argv[5:9])
    frames = []
    for p in sorted(glob.glob(os.path.join(src, "f*.png"))):
        t = int(os.path.basename(p)[6:11]) / 1000.0
        if t >= t0 and len(frames) < count:
            frames.append((t, Image.open(p).convert("RGB").crop(box)))
    os.makedirs(os.path.join(out, "frames"), exist_ok=True)
    tiles = []
    for i, (t, img) in enumerate(frames):
        img.save(os.path.join(out, "frames", "c%02d_%05d.png" % (i, int(t * 1000))))
        tile = Image.new("RGB", (img.width, img.height + 18), (12, 14, 24))
        tile.paste(img, (0, 18))
        ImageDraw.Draw(tile).text((4, 3), "%.3f s" % t, fill=(235, 235, 235))
        tiles.append(tile)
    cols = 8
    rows = (len(tiles) + cols - 1) // cols
    tw, th = tiles[0].width, tiles[0].height
    sheet = Image.new("RGB", (cols * tw + (cols - 1) * 4, rows * th + (rows - 1) * 4), (40, 40, 40))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % cols) * (tw + 4), (i // cols) * (th + 4)))
    sheet.save(os.path.join(out, "sheet.png"))
    durations = [max(20, int(round((frames[i + 1][0] - frames[i][0]) * 1000))) for i in range(len(frames) - 1)]
    durations.append(durations[-1] if durations else 50)
    imgs = [img for _, img in frames]
    imgs[0].save(os.path.join(out, "arcs.gif"), save_all=True, append_images=imgs[1:], duration=durations, loop=0)
    print("%d frames %.3f-%.3f s -> %s" % (len(frames), frames[0][0], frames[-1][0], out))


if __name__ == "__main__":
    main()
