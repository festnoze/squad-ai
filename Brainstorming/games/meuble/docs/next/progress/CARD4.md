# CARD4 progress (2026-11-25): card 4 redesigned around Lea, level14 routes rewritten from its spawn

## Requests
1. "Level 4 is too easy, you don't even have to meet the single human." Card 4 = levels[3] =
   Assets/Resources/Levels/level11.json ("The Vase", lesson load, chair with a vase, one inhabitant: Lea, tidy, loop).
2. "Level 14's saved routes still start from the old spawn point." Gameplay of level14 untouched, only its designer
   routes rewritten from the current spawn (2.25, 7.75).

## 1. level11 (card 4)

### Why it was too easy
The strict audit (Build/leveldiff.log) found the exit at 15.0 s with 2 % waiting and no pause. Lea started facing the
bedroom wall for 14 s, so the chair drove out of the bedroom, through the living room and the kitchen while she was
still looking at that wall; she never stood between the chair and the exit. A second way out (corridor south end to
the kitchen) made it even freer.

### New design: "red light, green light" in Lea's living room
- One way out only: bedroom, corridor, living room, kitchen. The corridor to kitchen door is gone and the corridor
  is shortened to the living room (z 4.0 to 8.9, it was a dead end otherwise).
- The living room is split by two 2.0 m tall open bookcases (BibliothequeOuest x 7.2 to 8.8, BibliothequeEst x 9.7 to
  10.6, both at z 5.75). North of them is Lea's half (bookshelf on the north wall, coffee table, sofa backing onto the
  bookcases and facing her). South of them runs a lane along the south wall (z 4.75) from the corridor door to the
  kitchen door. The lane is hidden behind the bookcases and exposed at three gaps: the corridor door, the gap between
  the two bookcases, and the gap at the kitchen door.
- Lea stands at the bookshelf (9.25, 8.15) the whole time: she dusts it (back to the room, 1.3 s), says "hm?" (0.6 s
  telegraph), turns around to check the room over her right shoulder (facing 170, 2.0 s), turns back, dusts again,
  then checks over her left shoulder (facing 190, 2.0 s). One check every 6.4 s, the loop lasts 12.8 s.
- Each gap must be crossed while she dusts, and the free window (about 3.1 to 3.3 s) is too short to cross two gaps:
  the chair has to stop behind the west bookcase, then behind the east one, 3 to 4 m from her. The kitchen and the
  bedroom stay out of her sight; the vase still needs {careful} at the four corners (bedroom, top and bottom of the
  corridor, end of the lane).
- Safe spawn: unchanged spawn (2.25, 6.25) in the bedroom, Lea is two rooms away.
- rev 1 -> 2 (old best times are not read), pace gate added like the other act 1 levels:
  minShare 0.25, maxShare 0.55, minPauses 2, maxPause 6.0.
- Hint (Strings.cs level11.hint, EN / FR "tu", threat only):
  "Slow down ({careful}) before every turn or the vase falls. Lea dusts her bookshelf but keeps turning around to check
  the living room." / "Ralentis ({careful}) avant chaque virage, sinon le vase tombe. Lea époussette sa bibliothèque,
  mais se retourne sans cesse pour surveiller le salon."
- Kept: the bedroom, living room and kitchen rectangles, every prop, plant (corners rule), rug, decor
  (11 items, hosts moved with their props), the two dressed props (TableBasse walnut coffee table, Plan kitchen base
  cabinet), colours (the new bookcases reuse the Etagere colours: still 25/25 materials).

### Maps (top = +z, x from 0 to 12 m; S spawn, L Lea, E exit mat, P plant, = exit door)
Before (rev 1):
```
z 8.9 +---------------+----+-------------------------+
      | Lit           |    |      [Etagere]      P   |
      |              D1  c D2 . . . . . . . . . .    |   the route: straight across,
      |   chambre  S  |  o |      (TableBasse)   .   |   nobody watching it
      |      (rug)    |  u |      [ Canape  ]    .   |
      | L>wall 14 s  P|  l +---------------D3--- . --+
z 4.5 +--[Coiffeuse]--+  o |   cuisine           .   |
                      |  i |   (Table)           E  =|
                      |  r D4  [ Plan ]          P   |
z 0.0                 +----+-------------------------+
      x 0            4.5  6.0                       11.9
```
After (rev 2):
```
z 8.9 +---------------+----+-------------------------+
      | Lit           |    |  [ Etagere ]  L      P  |   L dusts (back turned) or
      |              D1  c |  (TableBasse)           |   checks the room (facing the
      |   chambre  S  |  o |  [  Canape  ]           |   bookcases and their gaps)
      |      (rug)    |  u |  ###BW####  gap ##BE## gap
      |              P|  l D2 > > a a > > > b b > v  |   lane z 4.75: a, b = forced
z 4.5 +--[Coiffeuse]--+----+--------------------D3---+   stops behind BW and BE
                           |   cuisine            v  |
                           |   (Table)            E =|
                           |   [ Plan ]           P  |
z 0.0                      +-------------------------+
      x 0            4.5  6.0  7.2   8.8 9.7 10.6 11.9
```
The audit's own map of the living room (0 to 9 = share of time unseen, * route), Build/card4fix.log:
```
    # # # # # # # # # # # #
    # 8 8 8 # # # 8 8 8 # #
    # 8 8 8 # # # 4 6 8 8 #
    # 6 6 # # # # # 4 6 6 #
    # 7 7 # # # # # 4 5 7 #
    # 7 5 # # # # # 5 5 5 #
    # 7 # # # # 5 # # # 5 #
    # 5 9 9 9 5 5 5 9 5 5 #      <- behind the bookcases: 9 (never seen)
    * * * * * * * * * * * #      <- the lane
    # # # # # # # # # # * #      <- kitchen door
```

### Where the player must deal with Lea
1. Corridor door (5.25 to 6.25, 4.75): wait in the corridor out of the door's line, go when she turns back to her shelf.
2. Behind the west bookcase (6.75 to 8.25, 4.75): stop while she checks the room (audit: 8.4 to 11.4 s).
3. Middle gap (8.75 to 9.75, 4.75): cross while she dusts.
4. Behind the east bookcase (10.25 to 10.75, 4.75): stop again (audit: 15.0 to 19.0 s).
5. Kitchen door gap (11.25, 4.75 to 4.25): cross while she dusts; then the kitchen is out of her sight.
Every exposed crossing takes 0.9 to 1.3 s inside a 3.1 to 3.3 s window (about 2 s of slack, no frame-perfect timing).

### Audit (strict, Normal, -writeRoutes), Build/card4fix.log and Build/card4fix.json
| | before (rev 1, leveldiff) | after (rev 2) |
|---|---|---|
| defects | 0 | 0 |
| exit | 15.0 s | 22.1 s |
| waiting | 0.3 s (2 %) | 5.9 s (27 %) |
| pauses | 0 | 4, all on the way: 1.4 s (6.75, 4.75), 0.9 s (7.25, 4.75), 1.4 s (10.25, 4.75), 1.9 s (10.75, 4.75) |
| spawn wait | 0.3 s | 0.3 s |
- The four pauses are the two stops (one hop each) behind the two bookcases.
- Lesson load binds: the schedule computed without the load rule drops the vase at 2.58 s. Fidelity replay: 0
  observations. Budgets: 93/120 draw calls, 25/25 materials. Pace inside the new gate.
- designerRoute written by the audit (23 points). designerRouteHard: the run was Normal only, so it was set to a copy of
  the new Normal route (the old one crossed the removed door). NOT audited at Difficile; the scratchpad simulator saw
  no sighting of it with the Difficile cone (range x1.15, +5 deg). Run the Difficile audit when allowed.
- Design method: a scratchpad simulator of the audit (grid, routine with telegraphs and turn rates, cone and 3D
  occlusion, hearing, earliest exit with the audit's "wait as early as possible" tie-break) scanned the layouts and
  routines, and kept the variant whose two stops survive a faster player model, slower turns and a 0.5 s margin. It
  predicted the audit's exit time exactly (22.1 s).

### Tests touched (not run, per instructions)
- ProbeTestsM5Levels.Level11RouteAtFullSpeed (Step45q): replaced by the new counter-route of the audit's load note, as
  its comment asks for a new layout.
- ProbeTestsM6Levels.Level11DropAtSpawn (Step57a): same bedroom start and first corner, then the new corridor, lane
  and kitchen. Risk: the premise "Lea heard the crash within 6 m" now has about 0.3 m of margin (Lea stands about
  5.5 to 5.8 m from the corner where the vase falls).

## 2. level14 (routes only)
- No gameplay change: spawn, rooms, doors, props, inhabitants and routines are byte-identical; only the
  designerRoute and designerRouteHard arrays changed.
- The strict audit still reports the 3 known lint defects (Mamie and Lea never meet; 9.1 s loitering near (1.25, 6.75)
  vs 8 s; longest pause 6.8 s vs 6.0 s), so -writeRoutes, which only writes passing levels, refused to write. There was
  no existing way to record it (the route is not printed nor in the -json report).
- Added an opt-in flag to LevelAudit: "-forceRoutes" (with -writeRoutes) also writes the found schedule of a failing
  level, unless that schedule itself was refused after the search (fidelity sighting, rocking timing guard,
  Result.RouteRefused). The level still fails the run and its defects are printed. Default runs are unchanged.
- Run: `-auditLevels level11,level14 -skipFixtures -difficulty normal -writeRoutes -forceRoutes -json Build/card4fix.json`
  -> "designerRoute ecrite dans ... level14.json (41 points), malgre 3 defaut(s) (-forceRoutes)". The route now starts
  next to the spawn (first waypoint (1.25, 7.75)), exit 54.9 s, 25 % waiting, fidelity 0 observations, lesson split and
  requires sit bind (same numbers as the last audit, the gameplay being unchanged).
- designerRouteHard set to a copy of the new Normal route (Normal-only run; not audited at Difficile).
- This closes the stale-route item of docs/next/progress/L14START.md (Step45c, Step45f and Step64b replayed the old
  route from the old spawn).

## How to test
- PC: rebuild the player, then `Build/Play/OutOfSight.exe --level level11` (and `--level level14`).
- EditMode filters: `LevelDataM2Tests|LevelDefV2Tests|DoorwayTests|PlantPlacementTests|DressingTests|StarsTests|LevelDataM8RoomTypeTests`
- PlayMode filters: `Step45k_Level11Routes|Step45q_Level11FullSpeedRouteDropsTheVase|Step45r_|Step57a_Level11VaseDropIsHeard|Step64b_Level11Hard|Step45c_Level14Routes|Step45f_|Step45h_|Step64b_Level14Hard`
  (slow, optional: `ProbeTestsRush` and `ChinLook_`).
- Difficile audit, when allowed: `-auditLevels level11,level14 -skipFixtures -difficulty difficile -writeRoutes -forceRoutes`.

## Files
- Assets/Resources/Levels/level11.json (redesign, rev 2, routes), Assets/Resources/Levels/level14.json (routes only)
- Assets/Scripts/Core/Strings.cs (level11.hint, EN and FR)
- Assets/Editor/LevelAudit.cs (-forceRoutes, Result.RouteRefused)
- Assets/Tests/PlayMode/ProbeTestsM5Levels.cs, Assets/Tests/PlayMode/ProbeTestsM6Levels.cs (level11 hard-coded routes)
- Logs: Build/card4fix_compile.log (0 "error CS"), Build/card4fix.log, Build/card4fix.json
- Side effect of the compile check (Builder.SetupAndCompile runs ModelCatalogBuilder): Assets/Resources/ModelCatalog.asset
  now points the "quaternius.husky" entry at quaternius_labrador.glb, the Labrador model the LABRADOR work already
  selects in code; no other generated asset changed.
