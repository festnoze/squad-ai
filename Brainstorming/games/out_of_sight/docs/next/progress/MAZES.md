# MAZES - two night labyrinths (level34, level35)

Date: 2026-11-26. Task: two special levels with no furniture and no doors, at night, lit only by wall sconces, built as
real labyrinths (at least 8 x 8 base cells, a single way to the exit, many dead ends), with humans and the dog patrolling.

| Card | Id | Title (EN / FR) | Grid (1.5 m cells) | Way | Dead ends | Rooms / passages | Watchers | Sconces | Solver exit (Normal) |
|---|---|---|---|---|---|---|---|---|---|
| 25 | level34 | Night Maze / Le labyrinthe de nuit | 8 x 8 (12 x 12 m), seed 3413 | 30 cells | 17 | 26 / 25 | Hugo, Theo, Mamie, Rex | 3 | 88.8 s, 0 defects |
| 26 | level35 | Lost in the Dark / Perdu dans le noir | 10 x 10 (15 x 15 m), seed 3543 | 30 cells | 28 | 36 / 35 | Hugo, Paul, Mamie, Rex | 3 | 84.5 s, 0 defects |

Both: the floor lamp (the only body the dark hides), `"lighting": "night"`, no prop, no decor, no decoy, no rug, no
window, no door leaf, `lesson: "dark"`, `requires: ["lit"]`. The card numbers assume the two ids stay last in the
manifest (another agent appends level30 to level33 in parallel). The solver exit is the audit's fastest unseen schedule,
an upper bound on a skilled run, never a difficulty measure: a first clear, finding the way through 17 or 28 dead ends,
takes much longer.

## 1. The generator

Sources: `Build/mazes/tools/` (Python 3.14, standard library only, in its own venv `Build/mazes/tools/venv`). They are
not part of the game: the level files in `Assets/Resources/Levels/` are the source of truth.

| File | Role |
|---|---|
| `maze.py` | the perfect maze generator and its analysis (paths, dead ends, side branches, straight runs, strips, ASCII) |
| `mzlib.py` | maze to level: rooms, passages, sconce lit zones, watchers, the level JSON |
| `gen34.py`, `gen35.py` | one per level: seed, grid, spawn, exit, sconces, watchers; writes the level file |
| `survey.py`, `show.py` | seed survey (dead ends, rooms, straight runs, best spawn/exit pair) and one maze on screen |
| `variants.py` | audit variants that keep only some watchers (to find which one blocks a schedule) |
| `plan.py` | the plans and numbers of this document |

Run (PowerShell): `cd Build/mazes/tools; .\venv\Scripts\Activate.ps1; python gen34.py; python gen35.py`.

### 1.1 Perfect maze

`maze.generate(w, h, seed, newest, straight)` is a seeded "growing tree": it carves from the newest active cell with
probability `newest` (long winding corridors, like a depth first search) and from a random active cell otherwise (many
short dead ends, like Prim's algorithm), and it keeps going straight with probability `straight` (long straight runs, such
as a 6 x 1 or 9 x 1 corridor). The result is a spanning tree of the cell grid (checked: `w h - 1` edges, every cell
reached): exactly one path joins any two cells, so there is a single way from the spawn to the exit and every branch off
it ends in a dead end. Both levels use `newest = 0.45`, `straight = 0.7`.

The seeds were picked with `survey.py` (60 seeds each): many dead ends, a long straight run on the way, a spawn and an
exit that are both dead ends far apart.

### 1.2 From a maze to the level format

The format already expresses a maze: rooms are rectangles that share one wall thickness, and a door without a leaf is a
gap in the wall.

- **Cell size.** One maze cell is 1.5 m (pitch): 1.4 m of interior and 0.1 m of wall. It is the smallest pitch the rules
  accept (corridors must be at least `Tuning.PassageWidth` = 1.2 m wide), it keeps the 0.5 m audit grid on .25/.75, and it
  gives the floor lamp (radius 0.22 m) two lanes per corridor. A human (NavMesh radius 0.25 m) walks down the middle.
- **Rooms.** A perfect maze has no open 2 x 2 block, so every room is a straight strip of cells open to each other
  (`maze.strips`, longest runs first). Every room is a `"corridor"`, hard floor, wood colour (the dog's floor contrast
  test), herringbone, `"lightWall": "none"` (no automatic light at all), and a wall finish by region of the maze, so the
  player can tell the corridors apart (one wall material for every finish: no material cost).
- **Passages.** Every open edge of the maze between two rooms is a leafless doorway as wide as the corridor (1.4 m) and
  as tall as the wall (`"top": 2.7`). Inside a strip the cells are simply open.
- **Spawn, exit.** The spawn stands on a lane centre of a dead-end cell, facing its opening; the doormat (1 x 1 m) fills
  the exit cell, the dead end at the far end of the single way.

## 2. Code added (minimal runtime support)

1. **Passages** (`OpeningDef.IsPassage`, `LevelBuilder.BuildWallLine`). A leafless doorway whose top reaches its wall's
   height is drawn as an open gap: no lintel (the piece above it is empty), no door frame, and the top cap of its wall line
   is cut around it, so from the high camera the way through shows as a gap in the wall (a cap across it read as a closed
   wall). Its jambs get the closing quads a span end gets, where the line has solid wall beside it (a passage that fills a
   whole room side meets the crossing walls, whose own faces close it). The doorway floor (threshold and its NavMesh
   collider) is kept. No new data: every rule (validator, audit, NavMesh, sight, the wall fader) already treated it as a
   doorway, and every other level keeps its 2.1 m doors exactly.
2. **Sconce lit zones** (`LitZoneDef.Sconce`, JSON `"sconce": "+x" | "-x" | "+z" | "-z"`, not written when unset).
   - `RoomLights` draws a warm wall sconce for each such zone, on that wall of the zone's room at the zone's centre along
     it (`LitZoneView.SconceSpot`): the existing sconce glow (warm family, the floor lamp's glow material) and its black
     metal housing merged into the wall line's cap, so it fades and sinks with its wall like every wall fixture. It is
     placed whatever the room's `lightWall` says (the maze rooms say `"none"`), with no light and no fixture entry.
   - `LitZoneView` builds no ceiling ring for such a zone. Its spot stands above the sconce, 0.35 m off the wall, aimed at
     the zone's centre, its cone kept from the floor behind the wall (the RoomLights rule), so no light leaks into the
     corridor on the other side; the floor pool is unchanged. The light is the zone's own, so the switched-off lamp never
     dims it (`LitZoneView.IsZoneLight`), and Bas switches it off like any zone light (the pool and the glow still show
     the zone).
   - Cost per zone: one unshadowed spot light, one pool renderer (shared material); the glow joins the one warm glow
     renderer of RoomLights. No new material.
   - The rule (`FurnitureController.SightRangeFactor`: full range while the lamp's centre stands in a zone) and the
     audit's lit cells are unchanged.
3. **Validator** (`LevelValidator.CheckSconce`): a sconce names one of the four walls and hangs on solid wall: never
   within 0.12 m of the opening of a doorway or a passage on that side of the room.
4. **Tests** (exception lists only, not the play order, count or star pins owned by the other agent):
   `PlantPlacementTests.Fewer` (`level34`, `level35`: 0 plants) and `DressingTests.Bare` (the two mazes keep no decor
   and no prop; the 2 to 10 decor items rule needs host furniture).

Walls, see-through and NavMesh in the narrow corridors need nothing new: a maze of grid-aligned rooms has only one wall
line per grid coordinate (18 lines for 8 x 8, 22 for 10 x 10), each one fade unit as in every house, and the NavMesh
(agent radius 0.25 m) runs down the 1.4 m corridors (172 and 255 triangles; every station walk has a path). The camera
zoom bound grows with the house side as for any big house.

## 3. Design rules learned on the way (worth knowing for any maze level)

The audit loop ran 6 times (`Build/mazes_r1.log` to `Build/mazes_r6.log`, variants with one watcher each under
`Build/mazes/`). What it taught:

- **The lamp cannot follow a patrol down a corridor.** The floor lamp crosses a 1.5 m cell in 2.7 s; every walker is 1.5 to
  3 times faster. A patrol pacing a corridor that the way follows turns back and catches it, alcoves or not (first
  design of level34, Hugo along the long corridor: no schedule at all). Patrols must pace corridors the way **crosses**
  or only touches, and their far end must face away (Hugo in level34 walks down his own dead-end branch; Hugo in level35
  paces a 21-cell dead-end branch whose mouth the way passes).
- **A lit patch is crossed in about 3 moves, so make it short.** A zone filling a whole cell has three lit rows along the
  corridor (4 moves, 3.6 s plus the 0.6 s margin), longer than a glance. Every zone is 1 m long along its corridor (2 lit
  rows, 3 moves, about 2.7 s) and every glance holds 4.5 s every 7 s.
- **Two gates on one spot multiply their periods.** The dog's sight reaches 6 m in a lit zone. In level34 the first nook
  chosen for Rex saw the lit junction Theo watches, so the junction needed Theo's glance and Rex's nap at once (7 s and
  7.5 s clocks: one common window per 105 s); the solver burned 16 s near the spawn and failed the loitering rule. Every
  gate now has its own place.
- **Hearing goes through walls.** A tidy sentinel hears a move 2.25 m away, so a sentinel next to the end of the way is a
  wall nobody passes: level35's first exit ran one wall away from the bottom-row sentinel. The exit moved to the dead end
  right after her watched turn, and the old final stretch became a 7-cell dead end in her earshot (a trap).
- **A turn inside a sentinel's dark range costs about 5 moves.** A tidy watcher (dark range 4 m) at the end of the bottom
  row saw the whole last turn; a granny (2.8 m) leaves its far lane dark-safe, so only the lit patch needs her glance.
- **Short clocks.** Every gate is a 7 to 7.5 s clock (glances, naps) except the two patrols (18 s and 17 s), whose windows
  are long (11 s and about 9 s).
- **Practical:** never write into `Assets` while a Unity run is open (a new level file there made the editor reload and
  the run stopped after its first level); audit variants outside `Assets` with `-auditLevels ../../../Build/mazes/<id>`.

## 4. level34 - Night Maze (8 x 8, the floor lamp)

**Concept.** The lamp wakes up in a dark dead end of an empty maze at night. Four watchers, four kinds of gate: a guard
at a junction, a lit crossing seen from a long dead-end corridor, a dog in a nook, and a last turn watched from below.

**Plan** (north up, `S` spawn, `E` exit, `. ` the single way, `x ` a dead end off the way, `* ` a lit zone (sconce),
lowercase the watchers: `h~` Hugo's turning points, `t` Theo, `m` Mamie, `r` Rex):

```
+--+--+--+--+--+--+--+--+
|S  .  x |x |.  .  .  E |
+--+  +--+  +  +--+--+--+
|.  . |x |*  . |r |x |x |
+  +--+  +  +--+  +  +  +
|.  .  . |.  .  .  .  * |
+--+--+  +  +--+--+--+  +
|x |x |. |  |x       |. |
+  +  +  +  +--+--+  +  +
|  |.  . |m |t        * |
+  +  +--+--+--+--+--+  +
|   h~ .  .  .  .  .  . |
+--+  +  +--+--+  +  +  +
|     |      x |  |  |x |
+  +  +--+--+--+  +  +--+
|x |      h~|x    |   x |
+--+--+--+--+--+--+--+--+
```

Cells are (x, z) from the south-west corner (0, 0); cell (i, j) spans x 1.5 i to 1.5 i + 1.4, z 1.5 j to 1.5 j + 1.4.
Numbers: 26 rooms, 25 passages, the way 30 cells, 17 dead ends, 15 side branches off the way, longest straight run 8
cells (the long corridor, row 2), longest straight stretch of the way 7 cells.

**Watchers.** The three humans start together in the long corridor (they meet there, as the audit wants), then go:
- *Hugo* (hurried, 10 m / dark 4 m, hears 1.25 m): ping-pong between the corridor's west junction (1,2), looking north
  up column 1 for 3 s, and the end of his dead-end branch (3,0), 8 s (an 18 s cycle).
- *Theo* (teen, 6 m / dark 2.4 m, 35 deg): walks to the dead end (4,3) and stares east along row 3 at the lit junction
  (7,3), 4.5 m away; glances at the walls (+-80 deg, 4.5 s every 7 s).
- *Mamie* (granny, 7 m / dark 2.8 m): walks to the dead end (3,3) and looks north up column 3; same glances.
- *Rex* (dog, sees motion only, 2.4 m in the dark, 6 m in a lit zone): naps in the nook (5,6) facing row 5, asleep 5 s,
  awake 2.5 s.

**Sconces** (each 1 m long along the way, the sconce on solid wall at the zone's centre):

| Zone | Cell | Sconce wall | Watched by |
|---|---|---|---|
| Applique carrefour | (7,3) | +x (outer east wall) | Theo, along row 3 |
| Applique angle | (7,5) | +x (outer east wall) | Rex, 3 m (lit range 6 m) |
| Applique virage | (3,6) | -x | Mamie, up column 3 (4 m, within her 7 m) |

**Beat sheet.**

| # | Step | Threat | Intended action | Window |
|---|---|---|---|---|
| 1 | Dead end (0,7), spawn | the switch's click | switch off at once: nobody within earshot | free |
| 2 | West descent to (2,4) | none | learn the dark maze; three short dead ends tempt you | free |
| 3 | Into the long corridor (2,3), (1,3), (1,2) | Hugo at (1,2), then walking back up his branch | wait at (2,3) out of his sight, slip in when he walks south | about 11 s every 18 s |
| 4 | Long corridor east | none (Hugo is down his branch) | the long dark walk; its south branches are safe pockets | free |
| 5 | Lit junction (7,3) | Theo staring along row 3 | cross the light during a glance | 4.5 s every 7 s |
| 6 | Lit corner (7,5), row 5 west | Rex in his nook | move while he naps, freeze while he is awake | 5 s every 7.5 s |
| 7 | Last turn (3,5), (3,6), (4,6) | Mamie looking up column 3 | the far lane of (3,5) is dark-safe; cross the lit (3,6) during a glance | 4.5 s every 7 s |
| 8 | Final corridor to (7,7) | none | the doormat | free |

**Traps** (dead ends where a watcher comes in or looks): Hugo's branch (1,1), (1,0), (2,0), (3,0), which he walks to
its end every 18 s; the row 3 arm (5,3), (6,3) in front of Theo; (3,4) in front of Mamie; Rex's nook. Safe pockets: the
west dead ends, the south branches of the long corridor, (7,6), (6,6), (3,7).

**Audit (Normal, `Build/mazes.log`, `Build/mazes.json`): 0 defects.**
- Exit 88.8 s, 81 cell moves; waiting 18 %, 5 pauses (4 on the way), longest 6.2 s; spawn wait 2.5 s; longest loiter
  7.3 s (max 8 s). Pauses: at (2,3) for Hugo, by Rex's row, and at (3,5) for Mamie's glance. 3 switches (the folded
  flickers).
- Lesson dark binds (lamp always lit: no schedule). Requires lit binds (the schedule computed without the zones is seen at
  the lit junction (7,3) at 49.5 s).
- Pace in the level's target `{minShare 0.1, maxShare 0.4, minPauses 3, maxPause 7}`.
- Fidelity replay: 0 sightings. Separation: closest pair Theo and Mamie 0.92 m (min 0.6), all three pairs meet.
- Budgets: 100 of 160 draw calls, 25 of 33 materials, 16 326 triangles. Audit time 11.2 s, 2.56 million nodes.
- Warnings only: 10 dead rooms (maze corridors nobody uses: expected), habits (Hugo's 5.5 s mean dwell, Theo's wide
  glance, Mamie never sits).
- designerRoute written (50 points).

## 5. level35 - Lost in the Dark (10 x 10, the floor lamp)

**Concept.** A bigger maze, 28 dead ends, longer straight rows. A long dark walk, a corner swept by a patrol, a lit
junction seen from 8.5 m away, the dog at the bottom, and a granny who stares down the last row.

**Plan** (`h~` Hugo's turning points, `p` Paul, `m` Mamie, `r` Rex):

```
+--+--+--+--+--+--+--+--+--+--+
|.  .  .  .  .  .  .  .  . |x |
+  +  +--+--+--+--+--+--+  +  +
|. |   x |x |x |x |x |x  . |  |
+  +--+--+  +  +  +  +--+  +  +
|. |   h~             h~ *  . |
+  +  +--+  +  +--+--+--+--+  +
|S |     |  |x |x     .  .  . |
+--+  +  +  +--+--+  +  +  +  +
|x |  |x |  |     |  |. |x |  |
+  +  +--+  +  +  +  +  +--+  +
|  |   x |x |x |  |x |. |x |  |
+  +--+--+--+--+  +--+  +  +  +
|  |p                 * |     |
+  +--+--+--+--+--+--+  +  +  +
|      x |E |   x |x  . |x |x |
+  +--+--+  +  +--+--+  +--+--+
|         . |  |x |x |. |x    |
+  +--+--+  +  +  +  +  +--+  +
|x |m     .  .  *  .  .  r    |
+--+--+--+--+--+--+--+--+--+--+
```

Numbers: 36 rooms, 35 passages, the way 30 cells, 28 dead ends, 15 side branches off the way, longest straight run 9
cells (rows 9, 7 and 0), longest straight stretch of the way 9 cells (the top row).

**Watchers.** The three humans start together in row 7, then:
- *Hugo* (watchful, 10 m / dark 4 m, 60 deg, hears 2.25 m): ping-pongs along row 7, a 21-cell dead-end branch, between
  (2,7) facing west (3 s) and (7,7) facing east (1.5 s): about 17 s. Facing east he sees the lit corner (8,7) where the way
  passes.
- *Paul* (hurried, 10 m / dark 4 m): walks to the dead end (1,3) and stares east along row 3 at the lit junction (7,3),
  8.5 m away; glances +-80 deg, 4.5 s every 7 s.
- *Mamie* (granny, 7 m / dark 2.8 m, hears 1.45 m): walks to the dead end (1,0) and stares east along the bottom row;
  same glances.
- *Rex* (dog): naps at the east end of the bottom row (8,0) facing west, asleep 5 s, awake 2.5 s.

**Sconces.**

| Zone | Cell | Sconce wall | Watched by |
|---|---|---|---|
| Applique angle | (8,7) | -z | Hugo, along row 7 (up to 9 m) |
| Applique carrefour | (7,3) | +x (east wall) | Paul, along row 3 (8.5 m) |
| Applique rangee | (5,0) | -z (outer south wall) | Mamie, along row 0 (6 m) |

**Beat sheet.**

| # | Step | Threat | Intended action | Window |
|---|---|---|---|---|
| 1 | Dead end (0,6), spawn; up to (0,9) | the click | switch off at once | free |
| 2 | Top row (0,9) to (8,9), 9 cells | none | the long dark walk | free |
| 3 | Lit corner (8,8), (8,7), (9,7), (9,6) | Hugo pacing row 7 | wait at (8,8) or in the nook (7,8), cross while he walks west or faces west | about 9 s of his 17 s |
| 4 | East wiggle, column 7 down to (7,4) | none | | free |
| 5 | Lit junction (7,3) | Paul staring along row 3 | cross the light during a glance | 4.5 s every 7 s |
| 6 | (7,2), (7,1), (7,0) | Rex at (8,0) | move while he naps, freeze while he is awake | 5 s every 7.5 s |
| 7 | Bottom row west, the lit (5,0) | Mamie staring along row 0 | wait in the dark niche (6,1), cross the light during a glance, the niches (5,1), (4,1) are dark pockets | 4.5 s every 7 s |
| 8 | Last turn (3,0), (3,1), doormat (3,2) | Mamie 2.5 to 3 m away | the far lane of (3,0) is just beyond her dark range; or wait for a glance | free on the far lane |

**Traps.** Row 7 and its four north niches (Hugo's beat); row 3 in Paul's sight; the south-west block beside the exit,
(0..2, 1), (0..2, 2), (0,0), within Mamie's earshot through the wall: moving there is heard.

**Audit (Normal): 0 defects.**
- Exit 84.5 s, 82 cell moves; waiting 13 %, 6 pauses (5 on the way), longest 1.8 s; spawn wait 6.2 s; longest loiter
  2.4 s. One switch.
- Lesson dark binds. Requires lit binds (the schedule computed without the zones is seen at the lit junction (7,3) at
  61.9 s).
- Pace in the level's target `{minShare 0.05, maxShare 0.4, minPauses 3, maxPause 6}`.
- Fidelity replay: 0 sightings. Separation: closest pair Paul and Mamie 1.38 m, all three pairs meet.
- Budgets: 108 of 160 draw calls, 24 of 33 materials, 17 724 triangles. Audit time 12.4 s, 2.38 million nodes (far under
  the node cap: the maze leaves the lamp only two lanes per corridor).
- Warnings only: 24 dead rooms (expected in a maze), habits (Hugo's 3 s without a glance, Paul's long post, Mamie never
  sits).
- designerRoute written (48 points).

The solver slides through level35 with short pauses: its gates are frequent clocks and its way is long and dark. The
difficulty for a player is finding the way among 28 dead ends while reading four watchers; the solver knows the way.

## 6. Integration

- `Assets/Resources/Levels/level34.json`, `level35.json` (new, with their `.meta`), generated by `gen34.py` and
  `gen35.py`, designerRoute written by the audit (`-writeRoutes`).
- `Assets/Resources/Levels/levels.json`: `"level34", "level35"` appended at the end of `"levels"` (rev 5, `"previous"` and
  the acts unchanged: the two cards fall in act 4).
- `Assets/Scripts/Core/Strings.cs`: `level34.name`, `level34.hint`, `level35.name`, `level35.hint` in English and French,
  after level30. Hints name the threats with the data's names, never the way; `{action}` only for the lamp switch; the
  "tu" register.
- Code: `LevelDef.cs` (`OpeningDef.IsPassage`, `LitZoneDef.Sconce`, `SconceWalls`, `HasSconce`), `LevelBuilder.cs`
  (passages), `RoomLights.cs` (`ZoneSconce`, `Fixture` shared with `PlaceWall`), `LitZoneView.cs` (`SconceSpot`, the
  sconce light, `BuildCeilingLight`), `LevelValidator.cs` (`CheckSconce`, `SconceHalfWidth`).
- Tests: `PlantPlacementTests.cs` (Fewer), `DressingTests.cs` (Bare). Not edited (owned by another agent): the play
  order, act starts, level count and star pins (`LevelDataM2Tests`, `StarsTests`, `ProbeTestsM5Levels`,
  `ProbeTestsStars`), which now need the two new ids (26 cards, 78 stars, if level30 to level33 are not there yet).
- Compile: `OutOfSight.Editor.Builder.SetupAndCompile`, 0 "error CS" (`Build/mazes_compile.log`).

## 7. Known limits and follow-ups

- **Difficile** was not audited (the task asked for Normal only): no designerRouteHard, so Difficile's stars use the Normal
  route, as for act 4.
- **Not run:** the test suites (as asked). Worth a look once they run: the PlayMode look and budget probes that load every
  played level (`Step22c_EveryMaterialHasItsDetailTexture` counts the share of Lit slots with a colour image; the mazes
  have no furniture, so their Lit slots are mostly baseboards and the watchers), `Step40_FullPlaythrough` (two more
  routes of about 90 s each) and `Rush02` (a full-speed dash must not win: every way here runs past a sentinel).
- **Lights on Android Moyen:** the Forward renderer shades at most 4 additional lights per object; the combined floor of a
  maze is one object, so the three zone spots plus the lamp's own light can exceed it. The zones stay readable anyway
  (the pools and the sconce glows are unlit).
- **Rooms:** 26 and 36 rooms, the most of any level (12 before); budgets are well inside (100 and 108 of 160 draw calls).

## 8. How to play them on PC

After the user rebuilds the player:

```
Build/Play/OutOfSight.exe --level level34
Build/Play/OutOfSight.exe --level level35
```

In the game they are the last cards of the level select (act 4), unlocked in order.
