# Out of Sight - level system map (wave 1, agent system-map)

Read-only map of the level system for the level designers and implementers of the levels_v2 rework. Every fact below was
read from the files on 2026-11-20 (paths are relative to `C:\Dev\squad-ai\Brainstorming\games\out_of_sight`). Tuning values are
quoted by name because the parallel visual-polish workflow is editing `Tuning.cs` (its line numbers move; the values I
quote did not change while I read). Audit figures come from `Build/backdrop_audit.log` (full audit, 2026-11-19 23:41 to
23:52, `-skipFixtures`, Normal then Difficile, no defect), the most recent full run.

---

## 0. The twenty facts a designer must know before touching a level

1. A level is one JSON file `Assets/Resources/Levels/<id>.json` parsed by Newtonsoft with camelCase names and
   **unknown members rejected** (`LevelJson`, `MissingMemberHandling.Error`): a field the code does not know (a "goal",
   a "lighting", a per-level "difficulty") makes the level fail to load. New fields always need code.
2. Units are metres on the floor plane (x, z). Yaw follows `YawMath`: **0 faces +z, 90 faces +x, 180 faces -z, 270 faces -x**.
3. The audit works on a **0.5 m grid per room** (cell centres at `room.MinX + 0.25 + 0.5 k`). Spawns, decoys, stations and
   ramp axes should sit on cell centres (all shipped levels use x.25 / x.75), or tidy and watchful watchers warn.
4. **floorColor / wallColor do not show in the game any more.** With the texture library on, walls and floors are drawn by
   one Texture2DArray material that only reads the finish (`WallArray.Tag` writes the surface, not the colour) and props
   use "real colour" images on a white base colour (`PrimitiveKit.NewLit`). The colours only tint the level-select
   miniature floor (`LevelMiniature.WarmFloor`) and the no-texture fallback used by tests. The look levers are
   `floorFinish` (10 looks) and `wallFinish` (12 looks).
5. At most **2 door leaves** per level, open or closed, household doors included (`Tuning.MaxLeavesPerLevel = 2`). The
   review's "levels 20 to 24 each have exactly two closed doors" is this ceiling, not a habit.
6. At most **3 humans + 1 dog + 1 robot** (`Tuning.MaxHumans = 3`, validator).
7. Only the **stool and the floor lamp fit a wardrobe** (`WardrobeRule.Fits`: width and depth <= 0.40 m, height plus load <=
   1.85 m; the chair is 0.45 m wide). No load can hide. A chair finale cannot ask for a hide without code.
8. Any decoy **of the player's body kind** makes decoys mandatory: the audit then requires a schedule explained by a decoy
   at least once AND no schedule at all with decoys switched off (`w.NeedDecoy`, LevelAudit line ~4467). Decoys of another
   kind are scenery.
9. Humans must **cross**: every pair shares a room at the same instant at least once in the horizon, and never comes closer
   than 0.6 m (`CheckSeparation`, hard failures).
10. The audit horizon is **180 s for ids level1..level7, 300 s for every other id** (`LegacyLevels` keyed by id, not slot).
    A level whose earliest exit is past the horizon fails.
11. The audit never lets a schedule wait more than **8 s within 1 m** of one spot (`Tuning.AuditMaxWait`), nor loiter more
    than 8 s within 1.5 m (`Tuning.AuditLoiterRadius`), **hidden in a wardrobe included**. A design that needs a 10 s hide fails.
12. The creak gauge fills while still after 5 s (20 s fill at Normal, 16 s Difficile, audit cap 0.85): long waits creak.
13. A "metronome" sentinel is **not a feature**: it is one long dwell (300 to 400 s, longer than the 300 s horizon) whose
    glances are written out one by one (level 18 Odile: 34 glances every 9 s). There is no repeat field.
14. `pingpong` with 2 stations is identical to `loop` with 2 stations (levels 22, 13). A real back-and-forth needs 3+ stations.
15. Every shipped robot loop has 2 waypoints (a there-and-back line). A closed polygon of 3+ waypoints is supported.
16. Platforms are 0.6 to 1.0 m high; ramps rise at most 20 deg (a 0.6 m platform needs a ramp >= 1.65 m, a 1.0 m one >= 2.75 m),
    yaw a multiple of 90, width >= 1.2 m (1.5 m for the armchair); nothing over a door threshold; the robot never climbs.
17. Rooms are at least 1.2 m on their narrow side (1.5 m on an armchair level). Doors are at least `2 x body radius + 0.1`.
18. The exit only counts while **no human sees the furniture** (`rules.ExitOnlyUnseen`, GameState line ~1736; the audit's
    goal is `InExit && !HumanSeen`). An exit in a watched room is pure data.
19. The level select numbers cards by **play-order slot**, names them by **id** (`<id>.name`); records and wins are keyed
    by **id**; unlocking needs the **previous slot's id** won.
20. Removing or reordering ids in `levels.json` breaks about ten tests that hardcode the order or the count (section 3.5).

---

## 1. The level JSON schema actually supported

Sources: `Assets/Scripts/Core/LevelDef.cs` (LevelDef, RoomDef, OpeningDef, SpawnDef, ZoneDef, PropDef, RugDef, DecoyDef,
InhabitantDef, StationDef, GlanceDef, SeatDef, RouteStepDef, BodyKinds, LevelManifest, LevelJson), `LevelDefM5.cs`
(PlatformDef, RampDef, PointDef, RobotDef, WardrobeRule), `PropKinds.cs`, `RoomTypes.cs`, `PersonalityDef.cs`,
`RoutinePatterns.cs`, `BodyDef.cs`, `DifficultyDef.cs`; checks in `LevelValidator.cs`.

Serialization: null values are omitted; `designerRouteHard`, `platforms`, `ramps`, `robots` are written only when not empty;
`doorMemory`, `openedByInhabitants`, `seed`, `sleep`, `careful`, robot `speed`/`start` only when not default
(so an audit rewrite keeps old files byte-stable).

### 1.1 Top level (LevelDef)

| Field | Type | Notes |
|---|---|---|
| `id` | string | must equal the file name (test `Manifest_lists_the_levels...`) |
| `nameKey`, `hintKey` | string | keys into `Strings.cs` (EN + FR); convention `<id>.name`, `<id>.hint` |
| `room` | RoomDef | M1 form, single room centred on the origin (level 1 only). Never together with `rooms` |
| `rooms` | RoomDef[] | v2 form, every other level |
| `doors`, `windows` | OpeningDef[] | doors are gaps (optionally with a leaf); windows are decorative |
| `player` | SpawnDef | the player furniture |
| `exit` | ZoneDef | one doormat (a single zone; no list) |
| `props` | PropDef[] | static furniture, walls of cover |
| `rugs` | RugDef[] | silent floor patches |
| `decoys` | DecoyDef[] | static furniture bodies |
| `inhabitants` | InhabitantDef[] | humans and the dog (at least one) |
| `platforms`, `ramps` | PlatformDef[], RampDef[] | the split level |
| `robots` | RobotDef[] | at most one |
| `doorMemory` | bool | household remembers door states |
| `lesson`, `lessonAdvisory` | string, bool | the audit's lesson gate and its waiver |
| `designerRoute`, `designerRouteHard` | RouteStepDef[] | written by the audit (Normal, Difficile) |

Not in the schema (needs code): per-level difficulty overrides, lighting or time of day, a goal type, several exits, lit
zones, a time limit, a par time, a per-level music.

### 1.2 Rooms (RoomDef)

Fields: `id`, `x`, `z` (centre), `sizeX`, `sizeZ` (interior), `wallHeight`, `wallThickness` (same for all rooms; adjacent
rooms are exactly one thickness apart, otherwise clear by 2 t), `floor` (`"hard"` default, `"soft"` = silent, PRD 4.5),
`floorFinish`, `wallFinish`, `floorColor`, `wallColor`, `type`, `lightWall`.

- `floorFinish` (visual only; the `floor` field alone drives silence): null = default parquet (hard) or the plain
  border-and-field carpet look (soft); hard only: `tile`, `marble` (white-grey), `herringbone` (dark oak), `lightoak`,
  `verde` (dark green marble), `ivorytile`, `tealtile`; soft only: `carpet` (warm grey-beige loop pile).
  In use: parquet 23 rooms, plain soft 15, carpet 5, herringbone 21, marble 19, lightoak 11, tile 6, verde 6,
  ivorytile 1 (level 14 only), tealtile 1 (level 19 only).
- `wallFinish`: null = cream crepi; `sage`, `limewash`, `grasscloth` (dusty blue), `wallpaper` (sage stripes and sprigs),
  `whitetile` and `subwaytile` (band images, wall height <= 2.7 m), `travertine`, `arches` (slate blue on cream),
  `pinstripe` (olive on beige), `quatrefoil`, `sageribbed` (sage fluted panel). Only 7 of the 108 rooms show the crepi.
  None of the 12 looks is dark.
- `floorColor` / `wallColor`: still parsed, still in every room (84 of 108 rooms carry `#B07A4E` / `#EDE6DA`), **but not
  rendered** with textures on (see fact 4). Only the level-select miniature floor tint reads `floorColor`.
- `type` (visual only; drives room light fixtures and dressing): `bathroom`, `kitchen`, `dining`, `living`, `bedroom`,
  `study`, `hall`, `corridor`, `other`; null = inferred from the French id (`cuisine` kitchen, `couloir*` corridor,
  `bureau` study, `salle` dining, `sdb` bathroom, ...; `RoomTypes.Infer`). Declared in 3 rooms only (level 14 `salle`
  = bathroom, level 23 `galerie` = living, level 23 `bureau` = bathroom).
- `lightWall` (visual only): `+x`, `-x`, `+z`, `-z` puts the wall fixtures on that side, `none` removes the room's
  secondary light. Unused in shipped levels.

```json
{ "id": "couloir", "x": 4.0, "z": 1.0, "sizeX": 8.0, "sizeZ": 2.0, "wallHeight": 2.7, "wallThickness": 0.1,
  "floor": "soft", "floorFinish": "carpet", "floorColor": "#B07A4E", "wallColor": "#EDE6DA", "wallFinish": "quatrefoil" }
```
(level 18; level 14 shows `"id": "salle", "type": "bathroom", "floorFinish": "ivorytile", "wallFinish": "whitetile"`.)

### 1.3 Doors, windows, leaves, household doors, door memory (OpeningDef)

- M1 form (single room only): `wall` (`+x` ...) and `center` along it. v2 form: `x`, `z` = a point on a wall line.
- `width`, `bottom` (0), `top` (default 2.1). Doors must fit the body (`2 x radius + 0.1`: chair 0.66, stool/lamp 0.54,
  office chair 0.70, rocking chair 0.82, armchair 1.0). All rooms must connect through doors.
- Leaf (doors only): `leaf` = `"open"` or `"closed"`, `id` (unique), `swing` (id of a room on either side), `hinge`
  (`start` = lower world coordinate, or `end`). The swing sector (quarter disc of radius the width) must be free of props,
  decoys, rugs, stations, seat homes and the spawn. Max 2 leaves.
- `openedByInhabitants: true` (closed leaf only): an inhabitant whose walk crosses it stops, opens it and leaves it open;
  the audit forbids the player from opening it (the household opens it "for you").
- The player can only **open** a closed leaf (E, 0.6 s, seen swinging = seen moving). It can never close one.
- `doorMemory: true` (needs at least one leaf): each human remembers door states; a leaf seen in another state is a
  Suspect (suspicion), and an inhabitant may walk to put it back (close it). The audit models it conservatively: a leaf the
  player opened must never be seen open by a human.
- Windows: same geometry fields, never a leaf.

```json
{ "x": 1.25, "z": 4.45, "width": 1.0, "top": 2.1, "leaf": "closed", "id": "porte_cuisine", "swing": "cuisine", "hinge": "start" }
```
(level 8) and, with the household opener and memory (level 18):
```json
"doorMemory": true,
{ "x": 8.05, "z": 1.45, "width": 1.0, "top": 2.1, "leaf": "closed", "id": "porte_cuisine", "swing": "cuisine",
  "hinge": "start", "openedByInhabitants": true }
```
M1 door and window (level 1): `{ "wall": "+x", "center": 2.3, "width": 1.0, "bottom": 0.0, "top": 2.1 }`,
`{ "wall": "-z", "center": 0.0, "width": 1.6, "bottom": 0.9, "top": 2.1 }`.

### 1.4 The player (SpawnDef) and the bodies

Fields: `kind`, `x`, `z`, `yaw`, `sizeX/Y/Z` (must equal the body size, `BodyDef` is the one size source), `model` (null or
the body's model), `color` (the red `#D7263D`; no decoy may share it), `load` (`vase`, `books`, `plant`; never on the
lamp or the rocking chair).

| Body | Size (m) | Audit speed | Special rule | Model |
|---|---|---|---|---|
| chair | 0.45 x 0.9 x 0.45 | 1.25 m/s | none (seat) | kenney.chair |
| stool | 0.35 x 0.55 x 0.35 | 1.00 m/s careful | tips above 1.3 m/s, careful = half speed (Shift); fits a wardrobe | kenney.stool |
| armchair | 0.85 x 1.05 x 0.85 | 0.83 m/s | needs 1.5 m passages, 1.0 m doors | kenney.armchair |
| floor_lamp | 0.35 x 1.8 x 0.35 | 0.56 m/s | E toggles the light; switched off it is seen only within 0.4 x each watcher's range; not a seat; fits a wardrobe | kenney.floorlamp |
| office_chair | 0.55 x 1.0 x 0.55 | 1.67 m/s | every stop glides 4 samples; quiet roll (1.2 m noise) | procedural |
| rocking_chair | 0.6 x 1.05 x 0.85 | 1.00 m/s | rocks 0.8 s after every stop (seen moving); no load | procedural |

Dark ranges at Normal (range x 0.4): default, watchful, hurried, tidy 4.0 m; dreamer 3.2 m; granny 2.8 m; teen 2.4 m;
x1.15 at Difficile, x0.85 at Facile. The load falls when the speed changes by more than 1.8 m/s within 0.5 s (audit refuses
1.7); a fall is a crash heard 6 m away and one discovery.

```json
"player": { "kind": "chair", "x": 2.25, "z": 6.25, "yaw": 90.0, "sizeX": 0.45, "sizeY": 0.9, "sizeZ": 0.45,
            "color": "#D7263D", "model": "kenney.chair", "load": "vase" }
```
(level 11; level 10: `{ "kind": "rocking_chair", "x": 5.75, "z": 6.25, "yaw": 90.0, "sizeX": 0.6, "sizeY": 1.05, "sizeZ": 0.85, "color": "#D7263D" }`.)

### 1.5 The exit (ZoneDef)

`x`, `z`, `sizeX`, `sizeZ` (axis aligned), `model` (`kenney.doormat`), `color`. Inside a room, clear of props and decoys,
not straddling a platform, 1 m from the robot's loop. Nothing ties it to an outer door (convention only). It counts only
while unseen by humans (the dog does not count, `CountsForExit` false).

```json
"exit": { "model": "kenney.doormat", "x": 3.5, "z": 2.3, "sizeX": 0.9, "sizeZ": 0.9, "color": "#3F8F4F" }
```

### 1.6 Props (PropDef), occluders, wardrobes

Fields: `name` (unique when a `sit` names it), `kind`, `x`, `z`, `yaw`, `sizeX/Y/Z`, `occluder` (default true: colliders on
the Occluder layer block sight; false = see-through scenery; no shipped prop sets false), `model` (catalog id, null =
procedural), `color`, `accentColor` (palette colours, replaced by real-colour images in game).

Kinds: `sofa`, `bookshelf`, `table`, `cabinet`, `counter`, `plant`, `armchair`, `wardrobe`, `box`, and the M8 room objects
`bathtub`, `washbasin`, `toilet`, `kitchen_sink`, `stove`, `fridge`, `coffee_table`, `tv_unit`, `bed`, `nightstand`
(default sizes in `PropKinds.DefaultSize`). A new kind's front is its local -z face. No "desk", "partition", "shelf
divider" or "ceiling light" kind exists. Catalog prop models: kenney.sofa, armchair, bed, fridge, coffee_table, nightstand,
rug, doormat, chair, stool, floorlamp.

Wardrobe (`kind: "wardrobe"`): exactly 1.0 x 2.0 x 0.6 m, occluder, front = local +z (its yaw), entry zone 0.6 m deep
along the whole front, clear of props and decoys. E in the zone hides a fitting body (0.25 s action seen as moving);
hidden = not seen, not heard, cannot move; the creak gauge keeps filling (muffled creak, half radius); a human who sees the
remembered spot empty grows suspicious; E again comes out where it went in.

```json
{ "name": "Armoire", "kind": "wardrobe", "x": 4.0, "z": 1.45, "yaw": 180.0, "sizeX": 1.0, "sizeY": 2.0, "sizeZ": 0.6,
  "occluder": true, "color": "#8C5A36", "accentColor": "#A0703F" }
```
(level 18; a plain prop, level 1: `{ "model": "kenney.sofa", "name": "Sofa", "kind": "sofa", "x": -0.75, "z": -0.05, "yaw": 0.0, "sizeX": 2.0, "sizeY": 0.85, "sizeZ": 0.9, "occluder": true, ... }`.)

### 1.7 Rugs (RugDef)

`x`, `z`, `sizeX`, `sizeZ`, `yaw`, `model` (`kenney.rug`), `color`. A rug makes its footprint silent like a soft room.
Inside a room, out of door swing sectors.

```json
{ "model": "kenney.rug", "x": 0.0, "z": 1.55, "sizeX": 5.2, "sizeZ": 0.8, "yaw": 0.0, "color": "#2E6DB4" }
```
(level 2)

### 1.8 Decoys (DecoyDef)

`kind` (a body kind, default chair), `x`, `z`, `yaw`, optional `sizeX/Y/Z` (default the body size), `model` (null or the
body's model), `color` (never the player's red). A decoy within 0.6 m (minus the tolerance margin) of a still player of the
same kind "explains" it: a watcher seeing the player still out of place there counts nothing. Rule of fact 8 applies.
Decoys used: level 3 (6 chairs), 7 (4 office chairs), 13 (4 office chairs); none after 13.

```json
{ "model": "kenney.chair", "kind": "chair", "x": -2.3, "z": 0.6, "yaw": 180.0, "color": "#8C5A36" }
```
(level 3; level 13: `{ "kind": "office_chair", "x": 2.84, "z": 2.25, "yaw": 180.0, "color": "#6B4226" }`.)

### 1.9 Inhabitants (InhabitantDef, StationDef, GlanceDef, SeatDef)

InhabitantDef: `name`, `kind` (null/`"human"` or `"dog"`), `personality`, `pattern` (`loop` default, `pingpong`, `wander`),
`seed` (wander only, >= 0), `startStation` (the level starts inside that station's dwell), `stations`, `model` (overrides
the personality's), `bodyColor` (overrides its tint), `headColor`.

StationDef: `x`, `z`, `facing` (body yaw while dwelling), `dwell` (s), `glances`, `sit`, `seat`, `sleep` (dog only).
GlanceDef: `offset` (s into the dwell, increasing), `yaw` (head yaw relative to the body, |yaw| <= 80), `hold` (s). Every
turn is telegraphed 0.6 s (fairness rule, never a knob).

- Patterns (`RoutinePatterns`): loop = 0,1,..,n-1,0; pingpong = there and back (needs >= 2 stations, identical to loop with
  2); wander = deterministic pseudo-random next station among the others from `seed` (needs >= 3). Wander disables the
  audit's start-delay sweep. Every walk between reachable station pairs must have a NavMesh path with all leaves closed.
- Sit on a prop: `"sit": "<prop name>"`; the station is the seat front, 0.3 to 0.8 m from the prop centre, facing away from it.
- Sit on the player: `"sit": "player"` + `seat` {x, z, yaw} = the player's seat home; the station stands 0.3 to 0.8 m in
  front of the seat and faces the seat's yaw; the body must be a seat (all but the lamp). If the furniture is home in
  time it is pinned under the sitter; if not, a pratfall = one discovery (+0.34 suspicion). The audit forces the schedule
  onto the seat for the whole sit.
- Sleep (`"sleep": true`, dog only): eye closed for the whole dwell.
- The dog (`"kind": "dog"`, personality ignored): range 6 m, half angle 70 deg, eye 0.35 m, sees only movement, never
  hears, has no memory, never sits or glances, does not count for the catch or the exit; seeing the player move makes it
  bark, run (2.6 m/s), pin and the household carry the furniture back. The audit forbids being seen moving by an awake dog.
- Sentinel: one long station (level 21 Bertrand, 1 station, dwell 300, 65 glances) or a long second station (levels 18 to
  20); the glances are written out by hand over more than the 300 s horizon.

Personalities (`PersonalityDef`; walk m/s, range m, half angle deg, hearing x, suspicion x, displacement tolerance m, carry x):

| id | walk | range | half | hear | susp | tol | carry | audit habit warning |
|---|---|---|---|---|---|---|---|---|
| default (levels 1-7) | 1.2 | 10 | 55 | 1 | 1 | 0.75 | 1 | none |
| dreamer | 0.9 | 8 | 45 | 0.7 | 0.7 | 0.75 | 1.0 | average dwell >= 4 s |
| watchful | 1.2 | 10 | 60 | 1.0 | 1.5 | 0.5 | 1.0 | a glance in every dwell >= 2 s |
| hurried | 1.7 | 10 | 50 | 0.5 | 1.0 | 0.75 | 1.2 | average dwell <= 2 s |
| granny | 0.8 | 7 | 55 | 0.6 | 1.0 | 0.75 | 0.8 | sits at least once every 60 s |
| teen | 1.1 | 6 | 35 | 0.4 | 0.8 | 0.75 | 1.0 | average dwell >= 3 s, glances < 30 deg |
| tidy | 1.2 | 10 | 55 | 1.0 | 1.3 | 0.4 | 1.3 | none |

Human models: quaternius.man, woman, man_shorts, man_suit, man_tshirt, woman_jacket, woman_dress (each personality has
its own model and tint); dog quaternius.shiba. No guard or butler model.

```json
{ "name": "Rex", "kind": "dog", "pattern": "loop", "startStation": 0, "stations": [
  { "x": 7.25, "z": 4.5, "facing": 320.0, "dwell": 12.0, "glances": [] },
  { "x": 7.25, "z": 4.5, "facing": 320.0, "dwell": 2.0, "glances": [], "sleep": true } ] }
```
(level 12) Sit on the player (level 5):
```json
{ "x": -2.75, "z": 0.25, "facing": 90.0, "dwell": 0.5, "sit": "player", "seat": { "x": -3.25, "z": 0.25, "yaw": 90.0 }, "glances": [] }
```
Sit on a prop (level 8 Paul): `{ "x": 7.25, "z": 2.0, "facing": 180.0, "dwell": 8.0, "glances": [ { "offset": 4.0, "yaw": -40.0, "hold": 1.0 } ], "sit": "Canape" }`.
Wander (level 14): `"name": "Lea", "personality": "tidy", "pattern": "wander", "seed": 1234, "startStation": 0` (4 stations).
Pingpong (level 13): `"name": "Max", "personality": "hurried", "pattern": "pingpong"`, stations (1.25, 3.0) facing 270 dwell 9 and (12.75, 5.25) facing 90 dwell 2.
Metronome sentinel (level 18 Odile, station 2): `{ "x": 7.75, "z": 0.5, "facing": 270.0, "dwell": 320.0, "glances": [ { "offset": 2.0, "yaw": -80.0, "hold": 5.0 }, { "offset": 11.0, "yaw": -80.0, "hold": 5.0 }, ... up to offset 299 ] }`.

### 1.10 The robot vacuum (RobotDef)

`name`, `loop` (>= 2 points {x, z}, closed: the last leads back to the first; 2 points = there and back), `speed` (0 =
0.4 m/s), `start` (waypoint index). It runs on the floor level only, clear of walls (crosses only leafless doorways), props,
decoys, leaves and swing sectors (radius 0.17 m), keeps 1 m from the spawn, seat homes and exit. No collider for
inhabitants. Contact shoves the player 0.25 m (seen as moving) and reverses the robot. Its hum masks the player's noise
within 2.5 m (`Tuning.RobotHumRadius`).

```json
"robots": [ { "name": "Robot", "loop": [ { "x": 5.75, "z": 7.25 }, { "x": 10.75, "z": 7.25 } ] } ]
```
(level 9)

### 1.11 Mezzanine: platforms and ramps

PlatformDef: `name` (unique), `x`, `z`, `sizeX`, `sizeZ` (axis aligned), `height` (0.6 to 1.0), `color`.
RampDef: `x`, `z` (centre), `width`, `length`, `yaw` (uphill, multiple of 90), `platform` (name). Ramp head flush with the
platform edge, foot on the floor; railings; no surface over another; no platform or ramp over a door threshold (+ one cell);
props, decoys, rugs, spawn, exit, stations and seats stand wholly on one height and never on a ramp. The ramp axis must lie
on a line of the room's audit cell centres (exactly, for the armchair).

```json
"platforms": [ { "name": "Mezzanine", "x": 9.0, "z": 4.95, "sizeX": 1.0, "sizeZ": 6.9, "height": 0.6, "color": "#B07A4E" } ],
"ramps": [ { "x": 7.5, "z": 4.75, "width": 1.5, "length": 2.0, "yaw": 90.0, "platform": "Mezzanine" },
           { "x": 10.5, "z": 4.75, "width": 1.5, "length": 2.0, "yaw": 270.0, "platform": "Mezzanine" } ]
```
(level 14; all five platformed levels use 0.6 m)

### 1.12 Lessons and lessonAdvisory

`lesson` is one of `careful`, `sit`, `dark`, `glide`, `door`, `pet`, `split`, `robot`, `rock`, `load`, `final`, `wardrobe`
or null. The validator checks the premise (careful needs the stool, dark the lamp, glide the office chair, sit a
"player" sit, door a closed leaf, pet a dog, split a platform, robot a robot, rock the rocking chair, load a load, wardrobe
a wardrobe and a fitting body, final at least 3 of door/pet/split/robot/rock/load). The audit checks that the lesson binds
(section 2.5). `lessonAdvisory: true` turns a non-binding door, pet, split, robot, rock or load lesson into a warning
(level 10 only: `"lesson": "rock", "lessonAdvisory": true`). It does not waive careful, sit, dark, glide, wardrobe or final.

### 1.13 designerRoute and designerRouteHard (RouteStepDef)

Step: `x`, `z`, `at` (game time the leg starts: "at `at`, drive straight to (x, z)"), `careful` (hold Shift),
`action` (`toggle` lamp E, `rightup` right a tipped stool, `open` + `door` leaf id, `hide`, `leave`). Written by the audit
(`-writeRoutes`), one waypoint per run of at most 2 straight cell moves, the last point = exit centre. Read by tests only
(Step40 plays the whole order on designerRoute at offset 0; Step45 replays levels 8 to 17 at -0.2, 0, +0.2 s; Step64b and
Step58 replay the hard routes); no runtime feature uses it. First `at` must be >= 0.2 s.

Reading caveats: a rocking chair's route gives chained waypoints the same `at` (level 15: eight points at 6.3 s), so
travel time is not in the file; an action costs time (toggle 0.3 s, open 0.6 s, hide/leave 0.3 s, office chair stop 0.4 s,
rock stop 0.9 s); repeated toggles at one point are a wait (level 20 starts with 17 toggles at (5.75, 1.25) from 0.3 to
5.1 s: the solver prefers toggling to standing because a toggle drains the creak gauge and is not a "move").

```json
{ "x": -4.25, "z": -4.35, "at": 0.3, "action": "toggle" }
{ "x": 1.25, "z": 4.75, "at": 8.4, "action": "open", "door": "porte_cuisine" }
{ "x": 4.25, "z": 0.75, "at": 13.4, "careful": true, "action": "hide" }
```
(levels 6, 8, 18)

### 1.14 Strings

`Assets/Scripts/Core/Strings.cs` holds `levelN.name` and `levelN.hint` (EN, FR) for level1..level24, plus properties
Level1Name..Level16Hint; personalities use `person.<id>` and `person.<id>.trait`. A new level id needs both entries in both
languages (tests assert `Strings.Get(key) != key` for levels 2 to 7). The level select uses `<id>.name` directly (falls back
to the id). The intro card shows name, hint and the people of non-default personalities; no level number.

---

## 2. How LevelAudit works (`Assets/Editor/LevelAudit.cs`, 8 100 lines)

### 2.1 What one level run does, in order

1. `LevelValidator.Validate` (any issue stops the level).
2. Builds the real level (`LevelBuilder.Build`) in an empty editor scene: real colliders, runtime NavMesh, real routines
   (`RoutineFactory`), at the run's difficulty (`DifficultyDef.Current`).
3. Walks: every station pair the pattern can produce has a complete NavMesh path with all leaves closed (notes corners).
4. Budgets: draw calls as material slots (120; 160 for 5+ rooms), distinct materials (24; 32 for 5+ rooms; one per cone
   colour), triangles per furniture (400, bookshelf scales with width), per inhabitant (3000) and bones (40, pet 46).
5. The schedule search (2.2), its description, the route, the rock timing guard, the fidelity replay (the found schedule
   replayed against the game's own sight points: any sighting is a defect).
6. Decoys: if needed, the same search with decoys switched off must find nothing.
7. The lesson check (2.5).
8. Design data: start-delay sweep and slack report on level1..level7 ids (or `-sweep`, `-slack`), then the ASCII map.

### 2.2 The search model

Time-expanded search on 0.5 m cells per room, 0.1 s samples, horizon 180 s (ids level1-7 and M2/M4 fixtures) or 300 s.
A schedule is never seen moving (humans and the awake dog), never seen still out of place by a human unless a decoy
explains it (in-place radius from each personality's tolerance), never makes noise on a hard floor within a listener's
hearing (hop radius 2 m + 0.25 m margin, x hearing factor; masked by the robot hum), keeps the creak gauge under 0.85,
never waits more than 8 s within 1 m (and never loiters more than 8 s within 1.5 m), never touches the robot, never drops
the load. Sight and hearing are dilated by 3 samples (0.3 s) each way, so the schedule survives a 0.3 s global shift.
State bits carry the lamp, the stool lying, motion (glide, rock direction), leaves open, hidden, load history.

### 2.3 Earliest exit

The search expands time layer by layer and stops at the **first layer** where a node stands in the exit unseen (and has used
a decoy when needed); ties go to fewer cell moves, then a lower creak gauge (`Search`, line ~7144). So the printed
"sortie a T s" is the **earliest possible exit** under the rules, and the found schedule is the fastest one: it waits as
little as the watchers allow. Any human plays slower; waiting measured on it is a floor.

### 2.4 Waiting time

The audit prints "attente la plus longue" (longest single wait within the 1 m anchor) and "flanerie la plus longue"
(longest loiter within 1.5 m) and caps both at 8 s. It does **not** print total waiting, the number of pauses, or a
waiting share. To compute them from a route: for each leg, travel = distance / audit speed of the body (section 1.4 table),
plus action costs (1.13); waiting = next `at` - (this `at` + travel). Rocking chair routes cannot be measured this way.

### 2.5 Lesson checks (`CheckLesson`, `LessonBinds`, `MechanicBinds`)

| Lesson | Counterfactual search | Binds when |
|---|---|---|
| careful | stool at full speed (every stop tips) | no schedule |
| dark | lamp always on | no schedule; plus `DarkFreePass`: some watcher with memory passes within its dark range of the lamp's path |
| glide | stops cost 0 samples | that schedule is seen gliding |
| sit | nobody sits | its exit comes after the first sit on the player |
| door | every leaf locked | no schedule |
| pet | dog eye raised to 1.6 m | no schedule (low cover required) |
| split | platform and ramp cells barred | no schedule |
| robot | hum off | no schedule; else the schedule computed without the robot hits it |
| rock | no rock after stops | that schedule is seen rocking |
| load | no load rule | that schedule drops the load |
| wardrobe | hiding forbidden | no schedule |
| final | each of door, pet, split, robot, rock, load | at least 3 bind |

Counterfactuals run without the wait cap. Weakness: `DarkFreePass` compares watcher positions at every sample with every
cell of the path, **not at the same time** (level 6: "Habitant passe a 1.3 m du chemin de la lampe a 19.8 s" while the
exit is at 15.9 s), so it does not prove the darkness matters at the moment of crossing.

### 2.6 Other hard checks and the warnings

Hard: humans cross and stay 0.6 m apart; every closed leaf has reachable cells; a "player" seat has a free cell near it;
decoys necessary when present (player kind); node cap 80 M, search cap 40 M nodes, ray cap 20 M (exhausted = defect,
seconds never are). Warnings only ("AVERTISSEMENT"): personality habits, tolerance (spawn or decoy off the cell grid for tidy
or watchful), start-delay sweep failures, run time above 240 s, lessonAdvisory waivers.

### 2.7 Margins

- Built in: 3 samples (0.3 s) of dilation, always.
- "marge E s en avance / L s en retard": the largest global shift (up to 3.0 s) the found schedule survives, early and late.
- "marge maximale" (slack report, level1-7 or `-slack`): the largest dilation, up to 15 samples, for which a schedule still
  exists; "15 ... au moins" is the review's "15+". docs/m7/design.md calls it "margin". There is no "margin mean".

### 2.8 Flags, routes, run time

Command (lock wrapper, no spaces inside arguments):
`pwsh -NoProfile -File tools/unity.ps1 -Agent <name> -UnityArgs "run . --timeout 3000 -- -executeMethod OutOfSight.Editor.LevelAudit.RunBatch -auditLevels level1,level2 -skipFixtures -difficulty normal,difficile -logFile Build/<name>.log"`

- `-auditLevels a,b` (default: levels.json; an id may be an **absolute path without .json**, `Path.Combine` keeps it, so
  variants outside Assets can be audited: docs/m7/design.md section 3 used `-auditLevels C:/.../level6_a`; the `id` inside
  the file still decides the 180 / 300 s horizon), `-fixtures`, `-skipFixtures`, `-difficulty normal,difficile` (default
  both; facile is accepted but writes no route), `-sweep`, `-slack`, `-skipSweep`, `-debugSamples 20,40`, `-checkSight`.
- `-writeRoutes`: for each passing level, writes `designerRoute` (Normal) or `designerRouteHard` (Difficile) into the file
  in place (regex on the key, inserted before `inhabitants` if absent), then re-parses it. A note says when the file
  route differs from the found schedule. Menu items: OutOfSight/Audit Levels (and Write Designer Routes).
- Run time (2026-11-19 full run): 24 levels x 2 difficulties = 650 s of audit, about 11 min wall clock with Unity start.
  Per level 1 s (level 18) to 56 s (level 24 Normal); heavy: 17 (38 s N, 54 s D), 22 (25 s), 20 (22 s), 21 (19 s),
  23 (19 s), 15 (18 s N, 22 s D). The self-test (22 or 23 fixtures) adds about 50 s. Plus time queued on the lock.

### 2.9 Reading the log (French)

`[LevelAudit] Niveau levelN : aucun defaut` (or `N defaut(s)`), Difficile results are `levelN@difficile`; `[DEFAUT]` lines
fail the level; `[info]` lines are notes. Glossary: horaire = schedule; sortie a = exit at; attente la plus longue = longest
wait; marge en avance / en retard = early / late shift survived; deplacements de case = cell moves; grincement au plus =
peak creak; echantillons expliques par un leurre = samples explained by a decoy; sur tapis a portee d'oreille = rug samples
within earshot; interrupteur = toggle; arret glisse = glide stop; bascule = rock; assis dessus = sat on; porte ouverte =
door opened; cachette dans l'armoire = hide; flanerie = loiter; lecon ... requise = lesson binds; la lecon n'est pas requise
= it does not; contre-route = counter-route JSON; temps = run cost; budgets = draw calls / materials. The map: `#` blocked,
`0-9` share of the horizon unseen (`!` under 25 %), `c` explained by a decoy, `*` schedule, `S` start, `E` exit, `A` hide
cell. Example (level 22):

```
[LevelAudit] Niveau level22 : aucun defaut
  [info] budgets : 145 emplacements (draw calls, max 160), 114 renderers, 31 materiaux (max 32, un par couleur de cone), 15883 triangles, 8 modeles
  [info] corps stool : 5 echantillons par case (1.00 m/s) en mode prudent (4 a pleine vitesse), anneau 0.25 m, bruit de deplacement 2.0 m
  [info] Comtesse et Alfred : au plus pres 1.73 m a 71.4 s, se croisent
  [info] flanerie la plus longue : 5.8 s sans bouger sur un sejour de 9.2 s a moins de 1.5 m de (20.25, 7.75), de 33.8 s a 43.0 s (max 8 s)
  [info] horaire : sortie a 50.1 s, attente la plus longue 6.8 s (max 8 s), marge 0.3 s en avance / 0.3 s en retard, 69 deplacements de case, ...
  [info] lecon wardrobe : sans se cacher dans l'armoire, aucun horaire : l'armoire est requise
```

### 2.10 Current budgets (Normal, 2026-11-19, before the visual-polish workflow)

Draw calls / materials: 1 39/120 19/24; 2 58 18; 3 64 17; 4 50 21; 5 49 20; 6 52 21; 7 51 18; 8 69 23/24; 9 83 18;
10 70/160 24/32; 11 77/120 21/24; 12 84/160 20/32; 13 104 28; 14 95 26; 15 86 23; 16 82/120 **24/24**; 17 112/160 29;
18 60/120 16/24; 19 125/160 25; 20 126 24; 21 **150/160** 29; 22 145 **31/32**; 23 132 **31/32**; 24 144 28.
Wall and floor finishes are free (one array material); new prop kinds, models, personalities and decoys are not. Level 21
(10 draw calls left) cannot take many decoys; level 16 (4 rooms) is at its material cap.

---

## 3. Level order, progression, saves

### 3.1 The order

`Assets/Resources/Levels/levels.json` = `{ "levels": ["level1", ..., "level24"] }` (currently 1 to 24 in number order).
`LevelLoader.LoadManifest` reads it (missing file: a single level). `GameState.LevelOrder`, `NextLevelId` (next entry),
`HasNextLevel`, `IsLastLevel` (last entry: its win shows the end screen), `FirstLevelId` (first entry). Title "Play" goes
to `SaveStore.FirstUnwonLevel` (first unlocked level not won, else the last). `title_house.json` is the title-screen
house (TitleCameraTour), not in the manifest. Any id in Resources/Levels can be loaded by `GameState.LoadLevel(id)`,
listed or not.

### 3.2 Unlocking and the level select

`SaveData.IsUnlocked(order, i)`: slot 0, or the id at slot i-1 is in `won` (any difficulty). `SaveStore.UnlockAll` opens
everything (tests). The level select (`LevelSelect.cs`) builds one card per manifest entry in rows of 6
(`Tuning.LevelSelectColumns`): number = slot + 1; name = `<id>.name`; top-down miniature drawn from the JSON and cached by
id (`LevelMiniature`, floor tinted by `floorColor`); one icon per human, pet and robot (5 max, then "+n"); the player body
icon; the record of the current difficulty or "-"; a locked card shows the lock and is not interactable; the green
"won" badge shows only on playable cards. Progress line = won ids among the listed ids / count.

### 3.3 Save data (`SaveData.cs`, `SaveStore.cs`)

`{ "version": 1, "won": ["level1", ...], "best": { "level1": 10.3, "level1@difficile": 11.2, ... }, "options": {...} }`.
A win adds the id to `won` whatever the difficulty and keeps the best time under `DifficultyDef.RecordKey` (bare id at
Normal, `id@facile`, `id@difficile`). No slot, no level count, no migration.

### 3.4 What a removal or a reorder does to a save

- Records and wins survive (keyed by id). A removed id stays in `won` and `best` as an orphan: never shown, never counted,
  harmless; re-adding the id brings it back.
- Unlocking follows the new list. With the review's line-up (`level1..9, level15, level11, level12, level13, level14,
  level18, level17, level19, level21, level20, level22, [new], level24`), a player who had won 1 to 14 but not 15 sees
  level15 open at slot 10 and **level11 to level14 locked** (slot 11 needs level15), although they are won; their won
  badges hide because the cards are not playable. Winning level15 reopens them. Same for 17 behind 18, 20 behind 21.
  Nothing is lost; "Play" sends the player to the first unlocked unwon level.
- A new id starts unwon, so a player who finished all 24 sees e.g. 20/21 and the new level as their next "Play".
- The end screen follows whatever id is last.

### 3.5 Every hardcoded order, count or level id (tests and code)

Order and count (break on any cut or reorder):

| File | What it asserts | Breaks under the proposal |
|---|---|---|
| EditMode/LevelDataM2Tests.cs `PlayOrder` + `Manifest_lists_the_levels_in_play_order...` | count == 24 and the exact list | yes (count and list) |
| LevelDataM2Tests `Wave5B_levels_are_valid_and_played_in_number_order` | level9, 10, 11, 13, 15, 17 each right after level(n-1) | yes: 10 missing, 11 not after 10, 15 not after 14, 17 not after 16 |
| LevelDataM2Tests `Wave5B_levels_follow_the_revised_level_table` | level9/10/11/13/15/17 body, load, room count, lesson, people (personality:pattern), robots, closed leaves, platform, decoys | yes if 15 is rebuilt (row: robot lesson, teen:wander + watchful:loop, 6 rooms, 1 robot); constrains every retune of 9, 11, 13, 17 (17 row: dog, granny:loop, teen:wander, tidy:loop, robot, 2 closed leaves, platform) |
| EditMode/LevelDataM4Tests `Levels_4_to_7_have_one_body_and_its_lesson_each` | first seven slots = level1..7; 4-7 bodies, lessons, <= 2 rooms, inhabitant model quaternius.man, strings | no (unchanged); constrains the fix of level 6 |
| PlayMode/ProbeTestsM5Levels `Step40_FullPlaythrough` | count == 24, every route wins in order, save after each win | yes (count) |
| ProbeTestsM5Levels `Step45a` (WaveA rows) | level8, 12, 14, 16 each right after level(n-1); their body, lesson, humans, dogs | yes: 16 missing |
| ProbeTestsM5Levels `Step45r` (WaveB rows) | listed WaveB levels in increasing number order; body, lesson, people, robot, load | yes: level15 listed before level11 |
| ProbeTestsM5Levels `ReplayDesignerRoute` (Step45, 45b-d, 45i-n) | premise: the id is in levels.json | yes for cut levels 10 (Step45j) and 16 (Step45d) |
| PlayMode/ProbeTestsM7Design `ReplayHard` (Step64b_Level01..18Hard) | premise: the id is in levels.json | yes for 10 and 16 |
| PlayMode/ProbeTestsM6Levels Step (level 18) | premise: level18 in levels.json | no |
| PlayMode/ProbeTestsM42Look Step22e | every textured surface but Soil appears in the listed levels | maybe: re-check after cuts (ivorytile only in 14, tealtile only in 19) |
| Editor/LevelAudit.cs `LegacyLevels` | ids level1..7 get the 180 s horizon, sweep and slack | keyed by id: fine unless 1-7 change ids |
| Runtime/GameState.cs `LevelId = "level1"` | fallback id when there is no manifest | no |

Level content asserted by tests (break if the retune changes it):

- LevelDataM4Tests: level4 (>= 3 low props, a sofa sit, careful route), level5 (seat home = spawn, doors fit the armchair),
  level6 (a toggle on the route, exactly 2 rooms), level7 (>= 2 office chair decoys, a floor >= 8 m, procedural model).
  `mutation.sh` kills `audit_sit_moment` on level5: keep its sit lesson binding.
- LevelDataM2Tests: level1 frozen (stations, start station 2, prop positions, M1 form); level2 and 3 (two rooms, one
  doorway, one outer door); level2 rug path; level9 hard floors and rugs; every door lesson route opens a door.
- ProbeTestsM5Levels: level8 route opens its door + counter-routes (rushed route caught by the swinging leaf; route
  without the open never wins; first open after 3 s); level12 (stool never tips; every route point in an awake dog
  station's room, range and cone has a sofa between; Step45g uncovered crossing barks and loses); level14 (route climbs
  the platform, granny sits on the armchair, first sit by 10 s, bookshelf "Etagere" under 2 m, start view clear);
  level16 (exactly one closed leaf, a toggle, no switch-on, the leaf never opened); level9 (robot lane at z 7.25 heading
  east, Step45o collision shove); level10 (Step45p hardcoded rockless route seen rocking, no closed door); level11
  (Step45q hardcoded full-speed route drops the vase); level13, 15, 17 (load held, robot present).
- ProbeTestsM6Levels: level18 (wardrobe lesson, doorMemory, a household door, route hides, household opens the kitchen
  door); level11 and level17 counter-routes with hardcoded coordinates (`Level11DropAtSpawn`, `Level17DropAtSpawn`,
  door `porte_entree`, premise: nobody saw the chair before the crash, the alerted human stood within crash range).
- ProbeTestsM7LevelsA/B/C (no manifest premise): level19 (wardrobe, climbs the mezzanine, hides), level20 (dark,
  doorMemory, household door, toggles, the player opens no door, the household opens the kitchen door), level21 (split,
  climbs the catwalk), level22 (wardrobe, doorMemory, hides), level23 (wardrobe, doorMemory, household door), level24
  (final, closed door `porte_chambre`); each at Normal and Difficile.
- ProbeTestsM7Design: level16 used as "every kind of watcher" (watchful, hurried, dog; >= 3 watchers).
- Visual tests loading fixed ids (still load if the file stays): LightingShots 4, 12, 16, title; M7Look 5, 16; M7Walls
  2, 6, 9, 10, 12, 19, 24; M8Lights 12, 20; M9Backdrop 1, 9, 12, 21, 22; M9NearWalls 1, 8 (`porte_cuisine`), 12;
  M6Textures 3, 7, 9; M5House 8; LevelDataM8RoomTypeTests 4; SaveM5Tests 1-4 and CoreM5Tests (synthetic ids only).
- Editor tool (not a test): `Assets/Editor/BodyShots.cs` (new, visual workflow) lists level1, 4, 5, 6, 7, 10, 11, 3, 9.

Recommendation for implementers: never delete a cut level's file (many tests load ids directly); remove it from
levels.json and update the order and count tests in the same change; give a new level a new id (level25) rather than
reusing a cut id, so records stay meaningful.

---

## 4. What needs code (not data)

| Wanted | Exists today? | Data path | Code needed |
|---|---|---|---|
| Two exits in one level | No: `exit` is one ZoneDef | none | LevelDef (list or second zone), LevelValidator exit checks, LevelBuilder doormat, GameState exit test, LevelAudit `InExit` and `Route` end point, robot clearance, LevelMiniature, GardenBackdrop, Menu/Probe exit approach, editor shot tools, tests ("route ends in the exit"). Medium |
| Timed return goal (be home by X, no exit) | No goal type. Level 5 is an exit level whose sit-on-player forces the timing | "Be back in your spot when someone sits" is data for every seat body (not the lamp): a `sit: "player"` station + `seat`, lesson `sit` (level 5, level 14) | A goal field, GameState win rule and HUD timer, an audit goal (seat cell at sample T instead of the exit), validator, strings, tests. Medium to large |
| Lit zone that reveals the switched-off lamp | No: the dark factor is global (`LampLight.RangeFactor`, `FurnitureController.SightRangeFactor`) | Approximation only: bring a memory watcher inside the 4 m dark range of the crossing (corridor >= 1.2 m) | LevelDef zones, position-aware SightRangeFactor and cone display, audit (dark table = lit table on those cells, and a time-synchronous dark check), visual light pool (RoomLights), validator, miniature, a fixture. Medium |
| Exit in a watched room | Yes | place the doormat in sight; the exit counts only unseen (`ExitOnlyUnseen`), the audit's goal is `InExit && !HumanSeen` | none |
| Night guard on a random walk | Yes (behaviour) | `"pattern": "wander"`, `seed`, 3+ stations, any personality (no sweep then) | only for a guard look (new model) |
| Dog on patrol | Yes | dog with 2+ awake stations, `loop` or `pingpong` | none |
| Robot on a real loop | Yes | 3+ waypoints | none |
| Office grey carpet | Partly: `carpet` (warm grey-beige) and the plain soft look exist, **soft floors only** (silent: changes hearing) | `"floor": "soft", "floorFinish": "carpet"` | a hard grey floor needs a new finish: image, `RoomDef.FloorFinishes`, TextureLibrary, `WallArray.Slices` (22 slices today), ModelCatalogBuilder arrays, tests (Step22e, Step22f) |
| Blue partitions | No partition kind; prop colours do not render | walls between rooms in `grasscloth` (dusty blue) or `arches` (slate blue); cabinets or bookshelves as low cover | a partition prop kind (FurnitureKit, PropKinds, validator) with a blue surface |
| Night look: dark walls, pools of light | No: sun and ambient are global (`Main.cs` trilight), no level lighting field; IDEAS ART1 measured level 16 as bright as day | none (room light fixtures by `type`/`lightWall` only) | a level mood field (Main ambient and sun, windows, GardenBackdrop, RoomLights), a dark wall finish slice, HUD/probe contrast checks |
| Manor dark green panelling | No: closest is `sageribbed` (light sage fluted panel) + `verde` floor (dark green marble) + `herringbone` (dark oak) | those three | a new wall finish slice (asset + the same chain as the grey carpet) |
| Each room its own colour | Yes via finishes (12 wall x 10 floor looks, free of material cost) | `wallFinish`, `floorFinish` per room | none; `floorColor`/`wallColor` will not do it |
| A hide in a chair level | No | use the stool or the lamp | widen `Tuning.WardrobeFitWidth` (0.40) or a bigger wardrobe size (validator, audit, tests, mutation `WARDROBE_FIT`) |
| A third door leaf | No (`MaxLeavesPerLevel = 2`) | none | Tuning, audit tables (one per leaf mask), test `At_most_two_leaves_per_level` |
| A fourth human, a second dog or robot | No | none | Tuning.MaxHumans / validator / budgets |
| Per-level difficulty tweaks | No | none (global `DifficultyDef`; only routes differ per difficulty) | a schema field and RoutineFactory |
| Total waiting / pause count as an audit gate | No | compute from designerRoute (2.4) | Editor-only code in LevelAudit (`Describe`) |

---

## 5. Where the files disagree with the review (evidence)

1. **Palette lever.** "floorColor and wallColor already exist per room" (Cost and limits) and "84 of the 108 rooms share one
   floor colour and one wall colour": the count is right, but these fields are not rendered with textures on
   (`WallArray.Tag` ignores colour; `PrimitiveKit.NewLit` uses a white base colour for real-colour maps; only
   `LevelMiniature.WarmFloor` reads `floorColor`). Since walls 4 (docs/m9/FLOORS_WALLS.md section 7) 101 of 108 rooms show
   a wall finish and 10 floor looks are in use. The working lever is `floorFinish`/`wallFinish`, and the missing looks
   (dark, manor green, grey office) need assets and code.
2. **Two closed doors in 20 to 24** is the code ceiling (2 leaves per level), and level 24 has `"doorMemory": false`.
3. **Level 9 robot "neither blocks nor helps".** The audit at Normal and Difficile: "lecon robot : ronronnement coupe,
   aucun horaire : le ronronnement est requis" and "robot : l'horaire passe au plus pres a 1.00 m de lui a 5.7 s ;
   27 echantillon(s) de deplacement entendus sans le ronronnement, masques par lui". The hum is required; what is true is
   that the route barely waits (longest wait 1.1 s).
4. **Level 12 "the sofa-as-cover idea is optional".** "lecon pet : l'oeil du chien a 1.6 m, aucun horaire : le couvert bas
   est requis", and PlayMode Step45b asserts a sofa between the awake dog and every route point in its range and cone (the
   route runs at z 7.25 just behind CanapeOuest/CanapeEst at z 6.6). The dog's station is about 2.75 m off the route, but
   inside its 6 m, 70 deg cone. True: the crossing takes 14.3 s with a 1.3 s longest wait.
5. **Level 17 "the robot, the mezzanine ... are all bypassed".** The final lesson binds on door, split, robot (hum) and
   load; only pet does not ("un horaire existe aussi avec l'oeil du chien a 1.6 m"). The dog is the bypassed element.
6. **Level 24 "the dog is a 600 s statue, the robot is brushed, no wardrobe is needed".** Rex has one station, dwell 600 s
   (true) but pet binds; the robot binds by contact ("l'horaire calcule sans le robot le heurte a 31.2 s"); split and door
   bind; the final lesson does not check wardrobes (true, none is needed). The "0.9 s of waiting" matches (longest wait 1.6 s).
7. **Level 6 "darkness is barely tested".** Dark binds ("lampe toujours allumee, aucun horaire : le noir est requis"); the
   15+ is the timing slack. The review's concern is still right in substance: the audit's darkness check is not
   time-synchronous (2.5), so nothing proves the dark range matters at the crossing. Moving station 0 to (2, -0.25) is
   the lever already in docs/m7/design.md section 3.
8. **Level 20 "walk 54 s without ever stopping".** The route opens with 17 lamp toggles at the spawn from 0.3 to 5.1 s
   (a wait in disguise, 15 in the hard route); the first leg starts at 5.4 s. Papa (dreamer, dark range 3.2 m) passes over
   the path ("a 0.0 m ... a 42.6 s"), though not necessarily while the lamp is there.
9. **Finale body "Chair (the one from level 1)" asking for "a hide".** Impossible without code: only the stool and the
   floor lamp fit a wardrobe. Either keep a stool or lamp finale, or widen the fit rule.
10. **"Data only ... Cutting a level is removing its id from levels.json."** Data-wise yes, but it breaks the order and
    count tests of section 3.5 (about ten), and moving 15 to slot 10 breaks the number-order tests and the WaveB table.
11. **"Records are keyed by level id, so they survive a new order; I did not verify how unlocking follows the list."**
    Records survive; unlocking follows the list by previous slot, so moved levels re-lock won levels behind them until the
    moved level is won (3.4). No data is lost.
12. **"Wait often, never long: ... three or more pauses, none above 6 s."** The audit cannot enforce it: it finds the
    earliest exit (which minimises waiting), caps one wait at 8 s, and prints no pause count. Checking the rule needs the
    route arithmetic of 2.4 or new Editor code.
13. **Level 5 as a "deadline instead of a distance" goal.** It still ends on a doormat 3.7 m away; the deadline is the
    sit on the player. Reusing that beat late in the game is data (any seat body); a real timed-return goal is code.
14. **New late decoys (21 "fill the open space with decoy office chairs", the showroom's thirty decoys).** Data-wise
    possible, but decoys of the player's kind make "decoys required" a hard audit gate (no schedule may exist without
    them), and level 21 already uses 150 of 160 draw calls.
