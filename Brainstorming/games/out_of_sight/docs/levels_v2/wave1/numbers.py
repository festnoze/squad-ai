"""Measures the 24 levels of Out of Sight: level files plus the LevelAudit log (Normal and Difficile).

Read-only on the game. Writes numbers.json and numbers.md next to this script.
"""
import heapq
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

GAME = r"C:\Dev\squad-ai\Brainstorming\games\out_of_sight"
LEVELS = os.path.join(GAME, "Assets", "Resources", "Levels")
LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(GAME, "Build", "numbers.log")
OUT = os.path.dirname(os.path.abspath(__file__))
SAMPLE = 0.1          # one audit sample (5 fixed steps of 0.02 s)
CELL = 0.5            # audit cell
OPEN_S, TOGGLE_S, HIDE_S, STOP_S = 6, 3, 3, 4   # action samples (Tuning.AuditOpenSamples, LampToggleTime, WardrobeActionTime, AuditStopSamples)
PAUSE_MIN = 0.5       # a standing interval counts as a pause from 0.5 s

REVIEW = {  # level: (body, rooms, area, watchers text, exit s, waiting s, floor off route %)
    1: ("Chair", 1, 48, "1", 10, 2, 0), 2: ("Chair", 2, 40, "1", 12, 4, 0), 3: ("Chair", 2, 48, "1", 18, 14, 0),
    4: ("Stool", 2, 36, "1", 14, 5, 0), 5: ("Armchair", 1, 40, "1", 16, 11, 0), 6: ("Lamp", 2, 52, "1", 14, 6, 0),
    7: ("Office chair", 1, 50, "1", 20, 13, 0), 8: ("Chair", 4, 76, "1", 17, 7, 10), 9: ("Chair", 4, 114, "1", 12, 1, 17),
    10: ("Rocking chair", 5, 110, "1", 15, 7, 49), 11: ("Chair", 4, 84, "1", 15, 2, 35), 12: ("Stool", 5, 102, "1+dog", 14, 1, 23),
    13: ("Office chair", 5, 112, "2", 25, 10, 22), 14: ("Armchair", 6, 127, "2", 26, 4, 35), 15: ("Rocking chair", 6, 116, "2", 27, 16, 42),
    16: ("Lamp", 4, 90, "2+dog", 26, 12, 22), 17: ("Chair", 6, 156, "3+dog", 20, 5, 26), 18: ("Stool", 4, 32, "1", 21, 15, 28),
    19: ("Stool", 6, 208, "2", 57, 11, 31), 20: ("Lamp", 7, 199, "2+dog", 54, 7, 39), 21: ("Office chair", 7, 192, "3", 19, 2, 34),
    22: ("Stool", 8, 205, "3", 49, 15, 62), 23: ("Stool", 7, 192, "2+dog", 43, 10, 38), 24: ("Stool", 9, 234, "3+dog", 40, 1, 37),
}


# ----------------------------------------------------------------- geometry

def rooms_of(d):
    if d.get("rooms"):
        out = []
        for r in d["rooms"]:
            out.append(dict(r))
        return out
    r = dict(d["room"])
    r.setdefault("id", "room")
    r.setdefault("x", 0.0)
    r.setdefault("z", 0.0)
    return [r]


def rect(r):
    return (r["x"] - r["sizeX"] / 2, r["x"] + r["sizeX"] / 2, r["z"] - r["sizeZ"] / 2, r["z"] + r["sizeZ"] / 2)


def room_at(rooms, x, z, tol=0.0):
    best = None
    for r in rooms:
        x0, x1, z0, z1 = rect(r)
        if x0 - tol <= x <= x1 + tol and z0 - tol <= z <= z1 + tol:
            # prefer the room whose centre is nearest (a point on a shared wall)
            dist = abs(x - r["x"]) / r["sizeX"] + abs(z - r["z"]) / r["sizeZ"]
            if best is None or dist < best[0]:
                best = (dist, r["id"])
    return best[1] if best else None


def rooms_touching(rooms, x, z, tol=0.15):
    out = []
    for r in rooms:
        x0, x1, z0, z1 = rect(r)
        if x0 - tol <= x <= x1 + tol and z0 - tol <= z <= z1 + tol:
            out.append(r["id"])
    return out


def snap(v):
    return math.floor(v / CELL) * CELL + CELL / 2


# ----------------------------------------------------------------- inhabitants' rooms

def walk_rooms(rooms, doors, a, b):
    """Rooms an inhabitant crosses from point a to point b: shortest path through passable doorways (Dijkstra)."""
    if len(rooms) == 1:
        return {rooms[0]["id"]}
    ra, rb = room_at(rooms, *a, tol=0.3), room_at(rooms, *b, tol=0.3)
    if ra is None or rb is None:
        return {x for x in (ra, rb) if x}
    if ra == rb:
        return {ra}
    pts = [("A", a, {ra}), ("B", b, {rb})]
    for i, dr in enumerate(doors):
        if "x" not in dr:
            continue
        if dr.get("leaf") == "closed" and not dr.get("openedByInhabitants"):
            continue
        touch = rooms_touching(rooms, dr["x"], dr["z"])
        if len(touch) >= 2:
            pts.append((f"D{i}", (dr["x"], dr["z"]), set(touch)))
    dist = {0: 0.0}
    prev = {}
    heap = [(0.0, 0)]
    while heap:
        dcur, u = heapq.heappop(heap)
        if dcur > dist.get(u, 1e9):
            continue
        if u == 1:
            break
        for v in range(len(pts)):
            if v == u:
                continue
            shared = pts[u][2] & pts[v][2]
            if not shared:
                continue
            w = math.dist(pts[u][1], pts[v][1])
            if dcur + w < dist.get(v, 1e9):
                dist[v] = dcur + w
                prev[v] = (u, shared)
                heapq.heappush(heap, (dcur + w, v))
    if 1 not in prev:
        return {ra, rb}
    out = set()
    v = 1
    while v in prev:
        u, shared = prev[v]
        out |= shared if len(shared) == 1 else (shared & (pts[u][2] if u != 0 else shared))
        v = u
    return out | {ra, rb}


def transitions(inh):
    n = len(inh["stations"])
    pat = inh.get("pattern") or "loop"
    if n <= 1:
        return []
    if pat == "wander":
        return [(i, j) for i in range(n) for j in range(n) if i != j]
    if pat == "pingpong":
        return [(i, i + 1) for i in range(n - 1)]
    return [(i, (i + 1) % n) for i in range(n)]


def visitors(d, rooms):
    """Room -> set of non-player visitors (inhabitants by name, the robot) and per-inhabitant station rooms."""
    seen = defaultdict(set)
    detail = {}
    for inh in d.get("inhabitants", []):
        name = inh.get("name", "?")
        st = [(s["x"], s["z"]) for s in inh["stations"]]
        st_rooms = [room_at(rooms, x, z, tol=0.3) for x, z in st]
        crossed = set(r for r in st_rooms if r)
        for i, j in transitions(inh):
            crossed |= walk_rooms(rooms, d["doors"], st[i], st[j])
        for r in crossed:
            seen[r].add(name)
        detail[name] = {"stationRooms": st_rooms, "roomsCrossed": sorted(crossed)}
    for rb in d.get("robots", []):
        pts = [(p["x"], p["z"]) for p in rb["loop"]]
        crossed = set()
        for k in range(len(pts)):
            a, b = pts[k], pts[(k + 1) % len(pts)]
            for t in range(21):
                x = a[0] + (b[0] - a[0]) * t / 20
                z = a[1] + (b[1] - a[1]) * t / 20
                r = room_at(rooms, x, z)
                if r:
                    crossed.add(r)
        for r in crossed:
            seen[r].add(rb.get("name", "Robot"))
        detail[rb.get("name", "Robot")] = {"roomsCrossed": sorted(crossed)}
    return seen, detail


# ----------------------------------------------------------------- route timing

def route_timing(d, route, body, per_cell, careful_cell, rock=None):
    """Standing intervals of a designerRoute.

    A waypoint's "at" is the departure of the run that ends at it (a run is at most 2 straight cells). A rocking body's
    route chains the waypoints of one run under the first one's "at"; its cells are costed with the audit's printed
    costs (start, straight, turn) and every stop rocks rock["rock"] samples (counted as motion, not waiting).
    """
    if not route:
        return None
    sp = d["player"]
    pos = (snap(sp["x"]), snap(sp["z"]))
    t_free = 0.0           # the time the body is free to act again
    moving = []            # (start, end) of motion
    hidden = 0.0
    hide_at = None
    hides = []             # [hide pressed at, seconds hidden]
    events = []
    path_cells = [pos]
    i = 0
    n = len(route)
    last_dir = None
    run_end_pending = False
    while i < n:
        s = route[i]
        act = s.get("action")
        at = s["at"]
        if act in ("open", "toggle", "hide", "leave"):
            if run_end_pending and rock:
                moving.append((t_free, t_free + rock["rock"] * SAMPLE))
                t_free += rock["rock"] * SAMPLE
                run_end_pending = False
            cost = {"open": OPEN_S, "toggle": TOGGLE_S, "hide": HIDE_S, "leave": HIDE_S}[act] * SAMPLE
            if act == "leave" and hide_at is not None:
                hidden += max(0.0, at - hide_at)
                hides.append([round(hide_at - HIDE_S * SAMPLE, 1), round(max(0.0, at - hide_at), 1)])
            events.append((act, round(at, 1), s.get("door")))
            t_free = max(t_free, at) + cost
            if act == "toggle":
                moving.append((max(t_free - cost, at), t_free))  # a toggle is costed as motion by the audit
            if act == "hide":
                hide_at = t_free
            last_dir = None
            i += 1
            continue
        if i == n - 1 and (s["x"], s["z"]) != pos and abs(s["x"] - pos[0]) < CELL and abs(s["z"] - pos[1]) < CELL:
            break  # the exit centre, appended after the last run
        if rock:
            # one chained run: every waypoint sharing this "at"
            j = i
            cells = []
            p = pos
            while j < n and route[j]["at"] == at and not route[j].get("action"):
                q = (route[j]["x"], route[j]["z"])
                if j == n - 1 and abs(q[0] - p[0]) < CELL and abs(q[1] - p[1]) < CELL and q != p:
                    break
                k = int(round(max(abs(q[0] - p[0]), abs(q[1] - p[1])) / CELL))
                dx = (q[0] - p[0]) / max(k, 1)
                dz = (q[1] - p[1]) / max(k, 1)
                for _ in range(k):
                    p = (p[0] + dx, p[1] + dz)
                    cells.append(((round(dx / CELL), round(dz / CELL)), p))
                j += 1
            if run_end_pending:
                moving.append((t_free, t_free + rock["rock"] * SAMPLE))
                t_free += rock["rock"] * SAMPLE
            start = max(at, t_free)
            travel = 0.0
            prevd = None
            for dirc, c in cells:
                if prevd is None:
                    travel += rock["start"] * SAMPLE
                elif dirc == prevd:
                    travel += rock["straight"] * SAMPLE
                else:
                    travel += rock["turn"] * SAMPLE
                prevd = dirc
                path_cells.append(c)
            moving.append((start, start + travel))
            t_free = start + travel
            pos = p
            run_end_pending = True
            i = j
            continue
        q = (s["x"], s["z"])
        k = int(round(max(abs(q[0] - pos[0]), abs(q[1] - pos[1])) / CELL))
        if k == 0:
            i += 1
            continue
        dx = (q[0] - pos[0]) / k
        dz = (q[1] - pos[1]) / k
        for m in range(1, k + 1):
            path_cells.append((pos[0] + dx * m, pos[1] + dz * m))
        cost_cell = careful_cell if s.get("careful") and careful_cell else per_cell
        start = max(at, t_free)
        dirc = (round(dx / CELL), round(dz / CELL))
        # the office chair glides on every stop: a run that departs after standing pays the glide of the stop before it
        glide = 0.0
        if body == "office_chair" and at > t_free + 1e-6 and last_dir is not None:
            glide = STOP_S * SAMPLE
            moving.append((t_free, t_free + glide))
        moving.append((start, start + k * cost_cell * SAMPLE))
        t_free = start + k * cost_cell * SAMPLE
        pos = q
        last_dir = dirc
        i += 1
    exit_t = t_free  # the audit's exit time is the arrival on the exit cell (the office chair's last glide is not counted)
    # merge motion, measure standing intervals inside [0, exit]
    moving.sort()
    merged = []
    for a, b in moving:
        if b <= a:
            continue
        if merged and a <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    stands = []
    t = 0.0
    for a, b in merged:
        if a - t > 1e-6:
            stands.append((round(t, 2), round(a - t, 2)))
        t = max(t, b)
    if exit_t - t > 1e-6:
        stands.append((round(t, 2), round(exit_t - t, 2)))
    waits = [w for _, w in stands]
    pauses = [(t0, w) for t0, w in stands if w >= PAUSE_MIN - 1e-6]
    length = 0.0
    for a, b in zip(path_cells, path_cells[1:]):
        length += math.dist(a, b)
    return {
        "exitFromRoute": round(exit_t, 1),
        "waitTotal": round(sum(waits), 1),
        "pauses": len(pauses),
        "pausesOver1s": sum(1 for _, w in pauses if w >= 1.0),
        "longestPause": round(max(waits), 1) if waits else 0.0,
        "pauseList": [[round(t0, 1), round(w, 1)] for t0, w in pauses],
        "hidden": round(hidden, 1),
        "hideList": hides,
        "lastDeparture": round(max(s["at"] for s in route), 1),
        "events": events,
        "lengthM": round(length, 1),
        "cells": path_cells,
    }


# ----------------------------------------------------------------- the log

NUM = r"(-?\d+(?:\.\d+)?)"


def parse_log(path):
    if not os.path.exists(path):
        return {}
    text = open(path, encoding="utf-8", errors="replace").read().splitlines()
    out = {}
    cur = None
    room = None
    for line in text:
        m = re.match(r"^\[LevelAudit\] Niveau (\S+) : (aucun defaut|(\d+) defaut\(s\))", line)
        if m:
            cur = {"pass": m.group(2) == "aucun defaut", "defects": [], "infos": [], "map": {}, "warnings": []}
            out[m.group(1)] = cur
            room = None
            continue
        if cur is None:
            continue
        if line.startswith("  [DEFAUT] "):
            cur["defects"].append(line[11:].strip())
            continue
        if line.startswith("  [info] "):
            cur["infos"].append(line[9:].strip())
            continue
        m = re.match(r"^  piece (\S+) :", line)
        if m:
            room = m.group(1)
            cur["map"][room] = []
            continue
        if line.startswith("  carte"):
            room = "room"
            cur["map"][room] = []
            continue
        if line.startswith("    ") and room is not None:
            cur["map"][room].append(line.strip())
            continue
        if not line.startswith("  "):
            room = None
            if not line.startswith("[LevelAudit]") and line.strip() and not line.startswith("OutOfSight") and not line.startswith("(Filename"):
                pass
            if line.startswith("OutOfSight") or line.startswith("(Filename") or line.startswith("UnityEngine"):
                continue
            cur = None if line.startswith("[") else cur
    # decode the infos
    for key, r in out.items():
        info = {}
        for s in r["infos"]:
            m = re.match(r"horaire : sortie a " + NUM + r" s, attente la plus longue " + NUM + r" s \(max \d+ s\), marge " + NUM +
                         r" s en avance / " + NUM + r" s en retard, (\d+) deplacements de case, grincement au plus " + NUM +
                         r", (\d+) echantillons expliques par un leurre, (\d+) echantillons sur tapis a portee d'oreille(.*)$", s)
            if m:
                info.update(exit=float(m.group(1)), longestWaitAudit=float(m.group(2)), marginEarly=float(m.group(3)),
                            marginLate=float(m.group(4)), moves=int(m.group(5)), creakPeak=float(m.group(6)),
                            decoySamples=int(m.group(7)), rugHeardSamples=int(m.group(8)))
                rest = m.group(9)
                for pat, name in [(r"(\d+) interrupteur", "toggles"), (r"(\d+) bascule", "rockStops"), (r"(\d+) arret\(s\) glisse", "glideStops"),
                                  (r"(\d+) porte\(s\) ouverte", "doorsOpened"), (r"(\d+) cachette\(s\) dans l'armoire \(" + NUM + r" s cache\)", "hides")]:
                    mm = re.search(pat, rest)
                    if mm:
                        info[name] = int(mm.group(1))
                        if name == "hides":
                            info["hiddenSeconds"] = float(mm.group(2))
                mm = re.search(r"assis dessus " + NUM + " s", rest)
                if mm:
                    info["satOnSeconds"] = float(mm.group(1))
                continue
            m = re.match(r"budgets : (\d+) emplacements \(draw calls, max (\d+)\), (\d+) renderers, (\d+) materiaux \(max (\d+)[^)]*\), (\d+) triangles, (\d+) modeles", s)
            if m:
                info.update(drawCalls=int(m.group(1)), drawCallsMax=int(m.group(2)), renderers=int(m.group(3)), materials=int(m.group(4)),
                            materialsMax=int(m.group(5)), triangles=int(m.group(6)), models=int(m.group(7)))
                continue
            m = re.match(r"corps (\S+) : (\d+) echantillons par case \(" + NUM + r" m/s\)( en mode prudent \((\d+) a pleine vitesse\))?", s)
            if m:
                info.update(bodyKind=m.group(1), moveSamples=int(m.group(2)), cellSpeed=float(m.group(3)))
                if m.group(5):
                    info["fullSpeedSamples"] = int(m.group(5))
                continue
            m = re.match(r"flanerie la plus longue : " + NUM + r" s sans bouger sur un sejour de " + NUM + r" s", s)
            if m:
                info.update(longestLoiter=float(m.group(1)), loiterStay=float(m.group(2)))
                continue
            m = re.match(r"marge maximale : un horaire existe encore avec (\d+) echantillons de marge de chaque cote \(" + NUM + r" s[^)]*\)(, au moins)?", s)
            if m:
                info.update(slackSamples=int(m.group(1)), slackSeconds=float(m.group(2)), slackAtLeast=bool(m.group(3)))
                continue
            m = re.match(r"charge \S+ : .*jambes prudentes (seulement|permises) \((\d+) echantillons par case\)(, pleine vitesse (\d+))?", s)
            if m:
                info.update(loadCarefulOnly=m.group(1) == "seulement", carefulSamples=int(m.group(2)))
                if m.group(4):
                    info["loadFullSamples"] = int(m.group(4))
                continue
            m = re.match(r"charge : tenue sur tout l'horaire .*?, (\d+) deplacement\(s\) de case prudent\(s\) ; marge " + NUM + r" m/s avant la chute", s)
            if m:
                info.update(carefulMoves=int(m.group(1)), loadMarginMs=float(m.group(2)))
                continue
            m = re.match(r"bascule : chaque arret coute (\d+) echantillons .*?; (\d+) echantillons par case au depart et dans un virage, (\d+) en continuant tout droit, (\d+) quand.*cout reel : depart " + NUM + r", tout droit " + NUM + r" a " + NUM + r", virage " + NUM + r" a " + NUM, s)
            if m:
                info.update(rockSamples=int(m.group(1)), rockMove=int(m.group(2)), rockContinue=int(m.group(3)), rockLag=int(m.group(4)),
                            rockStart=float(m.group(5)), rockStraightMin=float(m.group(6)), rockStraightMax=float(m.group(7)),
                            rockTurnMin=float(m.group(8)), rockTurnMax=float(m.group(9)))
                continue
            m = re.match(r"robot : l'horaire passe au plus pres a " + NUM + r" m de lui a " + NUM + r" s ; (\d+) echantillon", s)
            if m:
                info.update(robotNearest=float(m.group(1)), robotNearestAt=float(m.group(2)), humMasked=int(m.group(3)))
                continue
            m = re.match(r"temps : " + NUM + r" s, (\d+) noeuds", s)
            if m:
                info.update(auditSeconds=float(m.group(1)), nodes=int(m.group(2)))
                continue
            m = re.match(r"route : (\d+) points", s)
            if m:
                info["routePoints"] = int(m.group(1))
                continue
            if "du fichier differe de cet horaire" in s:
                info["fileRouteDiffers"] = True
                continue
            if s.startswith("AVERTISSEMENT") or "AVERTISSEMENT" in s[:40]:
                r["warnings"].append(s)
                continue
            m = re.match(r"lecon (\S+) : (.*)$", s)
            if m:
                info.setdefault("lessonNotes", []).append(s[:300])
                continue
            if s.startswith("lecon "):
                info.setdefault("lessonNotes", []).append(s[:300])
        # rooms on the schedule from the map
        onroute = {}
        for rid, rows in r["map"].items():
            cells = " ".join(rows).split()
            stars = sum(1 for c in cells if c == "*")
            special = [c for c in cells if c in ("S", "E")]
            if stars or special:
                onroute[rid] = stars + len(special)
        info["mapRoomsOnRoute"] = onroute
        r["info"] = info
    return out


# ----------------------------------------------------------------- per level

def level_numbers(n, log):
    d = json.load(open(os.path.join(LEVELS, f"level{n}.json"), encoding="utf-8"))
    rooms = rooms_of(d)
    area = sum(r["sizeX"] * r["sizeZ"] for r in rooms)
    inh = d.get("inhabitants", [])
    humans = [i for i in inh if i.get("kind") != "dog"]
    dogs = [i for i in inh if i.get("kind") == "dog"]
    def fixed(i):
        # never leaves one spot: a single position, or one station holding >= 85 % of the cycle with a dwell of 60 s or more
        if len({(s["x"], s["z"]) for s in i["stations"]}) == 1:
            return True
        dw = [s["dwell"] for s in i["stations"]]
        return max(dw) >= 60 and max(dw) >= 0.85 * sum(dw)
    def beat(i):
        st = max(i["stations"], key=lambda s: s["dwell"])
        g = st["glances"]
        if len(g) < 3:
            return f"{len(g)} glances"
        offs = sorted(x["offset"] for x in g)
        gaps = sorted(round(b - a, 2) for a, b in zip(offs, offs[1:]))
        return f"{len(g)} glances every {gaps[len(gaps) // 2]} s, hold {g[0]['hold']} s, yaw {g[0]['yaw']}"
    sentinels = [i["name"] + (" (dog)" if i.get("kind") == "dog" else "") + f" [{beat(i)}]" for i in inh if fixed(i)]
    closed = [dr for dr in d["doors"] if dr.get("leaf") == "closed"]
    props = d.get("props", [])
    wardrobes = [p for p in props if p.get("kind") == "wardrobe"]
    sits_player = sum(1 for i in inh for s in i["stations"] if s.get("sit") == "player" or s.get("seat"))
    sp, ex = d["player"], d["exit"]
    dx, dz = ex["x"] - sp["x"], ex["z"] - sp["z"]
    ang = math.degrees(math.atan2(dz, dx))
    compass = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"][int(((ang + 22.5) % 360) // 45)]
    seen, detail = visitors(d, rooms)
    floors = Counter((r.get("floorColor"), r.get("wallColor")) for r in rooms)
    rec = {
        "level": n, "id": d["id"], "lesson": d.get("lesson"), "lessonAdvisory": bool(d.get("lessonAdvisory")),
        "body": sp["kind"], "load": sp.get("load"),
        "rooms": len(rooms), "roomIds": [r["id"] for r in rooms], "areaM2": round(area, 1),
        "roomArea": {r["id"]: round(r["sizeX"] * r["sizeZ"], 1) for r in rooms},
        "humans": len(humans), "dogs": len(dogs), "humanNames": [i["name"] for i in humans],
        "sentinels": sentinels, "patterns": {i["name"]: i.get("pattern") or "loop" for i in inh},
        "personalities": {i["name"]: i.get("personality") for i in humans},
        "closedDoors": len(closed), "doorsOpenedByInhabitants": sum(1 for dr in closed if dr.get("openedByInhabitants")),
        "doorMemory": bool(d.get("doorMemory")),
        "wardrobes": len(wardrobes), "decoys": len(d.get("decoys", [])), "rugs": len(d.get("rugs", [])),
        "softFloorRooms": sum(1 for r in rooms if r.get("floor") == "soft"),
        "platforms": [(p.get("name"), p.get("height")) for p in d.get("platforms", [])], "ramps": len(d.get("ramps", [])),
        "robots": len(d.get("robots", [])), "sitsOnPlayer": sits_player,
        "spawn": [sp["x"], sp["z"]], "exit": [ex["x"], ex["z"]], "exitDirection": compass, "crowFlyM": round(math.hypot(dx, dz), 1),
        "palette": {f"{k[0]} on {k[1]}": v for k, v in floors.items()},
        "defaultPaletteRooms": floors.get(("#B07A4E", "#EDE6DA"), 0),
        "wallFinishes": sorted({r.get("wallFinish") or "-" for r in rooms}), "floorFinishes": sorted({r.get("floorFinish") or "-" for r in rooms}),
        "visitors": {r["id"]: sorted(seen.get(r["id"], [])) for r in rooms}, "inhabitantRooms": detail,
        "difficulties": {},
    }
    for diff, key, rkey in (("normal", f"level{n}", "designerRoute"), ("difficile", f"level{n}@difficile", "designerRouteHard")):
        lg = log.get(key, {})
        info = lg.get("info", {})
        body = sp["kind"]
        per = info.get("moveSamples")
        careful = info.get("carefulSamples") if info.get("carefulSamples") else None
        if info.get("loadCarefulOnly"):
            per = info.get("carefulSamples", per)
            careful = per
        rock = None
        if info.get("rockSamples"):
            rock = {"rock": info["rockSamples"], "start": info["rockStart"],
                    "straight": (info["rockStraightMin"] + info["rockStraightMax"]) / 2, "turn": (info["rockTurnMin"] + info["rockTurnMax"]) / 2}
        if per is None:
            per = {"chair": 4, "stool": 5, "armchair": 5, "floor_lamp": 4, "office_chair": 2, "rocking_chair": 4}.get(body, 4)
        rt = route_timing(d, d.get(rkey, []), body, per, careful, rock)
        # travel and waiting from the log's own counts (exact for the bodies without a rock)
        wait_log = None
        if "exit" in info and "moves" in info and not rock:
            cm = info.get("carefulMoves", 0) if not info.get("loadCarefulOnly") else 0
            travel = (info["moves"] - cm) * per + cm * (careful or per)
            travel += info.get("glideStops", 0) * STOP_S + info.get("toggles", 0) * TOGGLE_S
            wait_log = round(info["exit"] - travel * SAMPLE, 1)
        route_rooms = sorted({room_at(rooms, x, z) for x, z in rt["cells"]} - {None}) if rt else []
        map_rooms = sorted(info.get("mapRoomsOnRoute", {}).keys())
        if len(rooms) == 1:
            map_rooms = [rooms[0]["id"]] if info.get("mapRoomsOnRoute") else map_rooms
        on_route = map_rooms or route_rooms
        off = [r["id"] for r in rooms if r["id"] not in on_route]
        nobody = [rid for rid in off if not seen.get(rid)]
        # nearest approach of the file route to every station (straight distance, walls ignored)
        near = {}
        if rt:
            for i_ in inh:
                near[i_["name"]] = [round(min(math.dist((s["x"], s["z"]), c) for c in rt["cells"]), 1) for s in i_["stations"]]
            for rb in d.get("robots", []):
                near[rb.get("name", "Robot") + " loop points"] = [round(min(math.dist((p["x"], p["z"]), c) for c in rt["cells"]), 1) for p in rb["loop"]]
        plat = {}
        if rt:
            for p in d.get("platforms", []):
                x0, x1 = p["x"] - p["sizeX"] / 2, p["x"] + p["sizeX"] / 2
                z0, z1 = p["z"] - p["sizeZ"] / 2, p["z"] + p["sizeZ"] / 2
                plat[p["name"]] = sum(1 for x, z in rt["cells"] if x0 <= x <= x1 and z0 <= z <= z1)
        wait_best = wait_log if wait_log is not None else (rt or {}).get("waitTotal")
        entry = {
            "waitTotal": wait_best,
            "waitShare": round(wait_best / info["exit"], 2) if wait_best is not None and info.get("exit") else None,
            "stationDistanceToRoute": near,
            "pass": lg.get("pass"), "defects": lg.get("defects", []), "warnings": [short_warning(w) for w in lg.get("warnings", [])],
            "exit": info.get("exit"), "waitTotalLog": wait_log, "longestWaitAudit": info.get("longestWaitAudit"),
            "longestLoiter": info.get("longestLoiter"), "marginEarly": info.get("marginEarly"), "marginLate": info.get("marginLate"),
            "slackSeconds": info.get("slackSeconds"), "slackAtLeast": info.get("slackAtLeast"),
            "moves": info.get("moves"), "toggles": info.get("toggles", 0), "doorsOpened": info.get("doorsOpened", 0),
            "hides": info.get("hides", 0), "hiddenSeconds": info.get("hiddenSeconds", 0.0), "rockStops": info.get("rockStops", 0),
            "glideStops": info.get("glideStops", 0), "satOnSeconds": info.get("satOnSeconds", 0.0), "decoySamples": info.get("decoySamples"),
            "robotNearest": info.get("robotNearest"), "humMaskedSamples": info.get("humMasked"),
            "routeCellsOnPlatform": plat,
            "midRoutePauses": sum(1 for t0, _ in (rt or {}).get("pauseList", []) if t0 > 0.05),
            "meetsWaitRule": (None if not rt or wait_best is None or not info.get("exit") else
                              bool(0.25 <= wait_best / info["exit"] <= 0.40 and rt["pauses"] >= 3 and rt["longestPause"] <= 6.0)),
            "drawCalls": info.get("drawCalls"), "drawCallsMax": info.get("drawCallsMax"), "materials": info.get("materials"),
            "materialsMax": info.get("materialsMax"), "renderers": info.get("renderers"), "triangles": info.get("triangles"),
            "auditSeconds": info.get("auditSeconds"), "fileRouteDiffers": bool(info.get("fileRouteDiffers")),
            "fileRoute": {k: v for k, v in (rt or {}).items() if k != "cells"},
            "roomsOnRoute": on_route, "roomsOnRouteFromFileRoute": route_rooms, "roomsOffRoute": off, "roomsVisitedByNobody": nobody,
            "floorOffRoutePct": round(100 * sum(rec["roomArea"][r] for r in off) / area) if area else 0,
            "lessonChecks": lesson_verdicts(info.get("lessonNotes", [])),
            "lessonNotes": info.get("lessonNotes", []),
        }
        rec["difficulties"][diff] = entry
    return rec


VERDICTS = [
    ("la lecon n'est pas requise", "NOT required"), ("les arrets ne contraignent rien", "NOT binding (advisory)"),
    ("le niveau n'a pas la mecanique", None), ("le noir ne suffit pas", "dark alone not enough, timing needed"),
    ("le mode prudent est requis", "required"), ("la lecon ne peut pas etre evitee", "required"), ("le noir est requis", "required"),
    ("les arrets sont requis", "required"), ("il faut ouvrir une porte", "required"), ("le ronronnement est requis", "required (hum)"),
    ("la conduite prudente est requise", "required"), ("le couvert bas est requis", "required"), ("la mezzanine est requise", "required"),
    ("l'armoire est requise", "required"), ("le robot est requis", "required (contact)"),
]


def lesson_verdicts(notes):
    out = []
    for s in notes:
        m = re.match(r"lecon (?:final, lecon )?(\w+)", s)
        if not m or s.startswith("lecon final :"):
            continue
        for key, label in VERDICTS:
            if key in s:
                if label:
                    out.append(f"{m.group(1)}: {label}")
                break
    return out


def short_warning(w):
    w = w.replace("AVERTISSEMENT ", "")
    m = re.match(r"depart retarde : .* commence a ([\d, ]+) s \(boucle de ([\d,]+) s\)", w)
    if m:
        return f"start-delay sweep: an 8 s+ wait is forced when starting at {m.group(1).strip()} s of a {m.group(2).replace(',', '.')} s loop"
    if w.startswith("lecon indicative"):
        return "lesson advisory waiver: " + ("rock stops constrain nothing" if "ne contraignent rien" in w else w[:80])
    m = re.match(r"tolerance ([\d.]+) m : le leurre (\d+)", w)
    if m:
        return f"decoy {m.group(2)} explains nothing (off cell centres, {m.group(1)} m tolerance)"
    m = re.match(r"habitude \((\w+), (\w+)\) : (.*)$", w)
    if m:
        t = m.group(3)
        t = re.sub(r"attente moyenne ([\d.]+) s, au dessus de 2 s", r"mean dwell \1 s (habit wants <= 2 s)", t)
        t = re.sub(r"(\d+) s sans s'asseoir \(au plus 60 s\)", r"\1 s without sitting (habit <= 60 s)", t)
        t = re.sub(r"la station (\d+) attend ([\d,]+) s sans coup d'oeil", r"station \1 waits \2 s without a glance", t)
        t = t.replace("un coup d'oeil de 30 deg ou plus", "a glance of 30 deg or more")
        return f"habit {m.group(1)} ({m.group(2)}): {t}"
    return w[:120]


def fmt(v, nd=1):
    if v is None:
        return "?"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def main():
    log = parse_log(LOG)
    recs = [level_numbers(n, log) for n in range(1, 25)]
    json.dump({"log": LOG, "levels": recs}, open(os.path.join(OUT, "numbers.json"), "w", encoding="utf-8"), indent=1)
    print("levels in log:", sorted(log.keys(), key=lambda k: (int(re.sub(r"\D", "", k.split("@")[0])), k)))


if __name__ == "__main__":
    main()
