"""Decoy cell checker for levels v2 (wave 2 tool, read-only on the game).

The audit (LevelAudit.cs) walks a per-room 0.5 m grid: cell centres at room.MinX + (i + 0.5) * 0.5 and
room.MinZ + (j + 0.5) * 0.5, nx = round(sizeX / 0.5). A cell is walkable when the body's capsule (radius =
body radius, no skin) touches no Furniture or Occluder collider. A still cell seen by a human of tolerance t
is explained when it lies within 0.6 * t / 0.75 m of a decoy of the player's kind (0.6 m for 0.75 watchers,
0.4 m watchful, 0.32 m tidy).

This script approximates that in 2D: boxes for props (yaw 0/90/180/270) and decoys (body footprint), walls at
the room boundaries (door gaps ignored, so a cell next to a doorway may be reported "wall" wrongly). It lists,
for every decoy of the player's kind, the walkable cells it explains at the 0.75 class. The audit is the
arbiter; run this before an audit to avoid "aucun horaire ... qui se serve d'un leurre".

Usage: python decoy_cells.py path/to/levelN.json [explained_radius]
"""
import json
import math
import sys

BODY = {  # kind: (radius, footprint w, footprint d) from BodyDef.For
    "chair": (0.28, 0.45, 0.45),
    "stool": (0.22, 0.35, 0.35),
    "armchair": (0.45, 0.85, 0.85),
    "floor_lamp": (0.22, 0.35, 0.35),
    "office_chair": (0.30, 0.55, 0.55),
    "rocking_chair": (0.36, 0.60, 0.85),
}


def box(x, z, sx, sz, yaw):
    quarter = int(round((yaw or 0) / 90.0)) % 2
    hx, hz = (sz / 2, sx / 2) if quarter else (sx / 2, sz / 2)
    return (x - hx, z - hz, x + hx, z + hz)


def dist_box(px, pz, b):
    dx = max(b[0] - px, 0, px - b[2])
    dz = max(b[1] - pz, 0, pz - b[3])
    return math.hypot(dx, dz)


def main():
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    er = float(sys.argv[2]) if len(sys.argv) > 2 else 0.6
    if d.get("rooms"):
        rooms = d["rooms"]
    else:
        rm = dict(d["room"])
        rm.setdefault("x", 0.0)
        rm.setdefault("z", 0.0)
        rooms = [rm]
    kind = d["player"].get("kind", "chair")
    r = BODY[kind][0]
    boxes = []
    for p in d.get("props", []):
        boxes.append((p.get("name"), box(p["x"], p["z"], p["sizeX"], p["sizeZ"], p.get("yaw"))))
    decoys = []
    for i, q in enumerate(d.get("decoys", [])):
        k = q.get("kind", "chair")
        b = box(q["x"], q["z"], BODY[k][1], BODY[k][2], q.get("yaw"))
        boxes.append((f"decoy{i}", b))
        if k == kind:
            decoys.append((i, q["x"], q["z"]))
    total = 0
    for i, dx, dz in decoys:
        cells = []
        for rm in rooms:
            minx = rm["x"] - rm["sizeX"] / 2
            minz = rm["z"] - rm["sizeZ"] / 2
            nx = max(1, round(rm["sizeX"] / 0.5))
            nz = max(1, round(rm["sizeZ"] / 0.5))
            for a in range(nx):
                for b in range(nz):
                    cx = minx + (a + 0.5) * 0.5
                    cz = minz + (b + 0.5) * 0.5
                    dd = math.hypot(cx - dx, cz - dz)
                    if dd > er:
                        continue
                    wall = min(cx - minx, minx + rm["sizeX"] - cx, cz - minz, minz + rm["sizeZ"] - cz)
                    hit = [n for n, bb in boxes if dist_box(cx, cz, bb) < r]
                    if wall < r:
                        state = "wall"
                    elif hit:
                        state = "blocked by " + ",".join(hit)
                    else:
                        state = "ok"
                    cells.append((round(cx, 2), round(cz, 2), round(dd, 3), state))
        good = [c for c in cells if c[3] == "ok"]
        total += len(good)
        extra = "" if good else f"  candidates: {cells}"
        print(f"decoy{i} ({dx}, {dz}): {len(good)} explained walkable cell(s) {good}{extra}")
    print(f"TOTAL explained walkable cells: {total} (player {kind}, radius {r}, explained radius {er})")


if __name__ == "__main__":
    main()
