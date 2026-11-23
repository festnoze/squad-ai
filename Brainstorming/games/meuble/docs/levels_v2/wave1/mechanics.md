# Out of Sight: mechanics catalogue (levels_v2, wave 1, agent "mechanics")

Read-only pass. Every number below was read from code or data, with its location. Sources:

- Code: `Assets/Scripts/Core/Tuning.cs`, `BodyDef.cs`, `PersonalityDef.cs`, `DifficultyDef.cs`, `Hearing.cs`, `CreakGauge.cs`,
  `CaughtRule.cs`, `MotionRule.cs`, `FurnitureMemory.cs`, `SuspicionMeter.cs`, `DoorMemory.cs`, `RobotPath.cs`, `LoadBalance.cs`,
  `LevelDefM5.cs` (WardrobeRule), `LevelDef.cs`, `LevelValidator.cs`, `RoutineFactory.cs`, `InhabitantRoutine.cs`;
  `Assets/Scripts/Runtime/GameState.cs`, `FurnitureController.cs`, `Vision.cs`, `VisionConeView.cs`, `LampLight.cs`, `Hud.cs`,
  `LevelBuilder.cs`, `DoorLeaf.cs`; `Assets/Editor/LevelAudit.cs`.
- Data: the 24 level files, scanned with two read-only scripts in this folder (`mech_scan.py`, `mech_inhab.py`).
- Audit evidence: `Build/backdrop_audit.log` (full audit, Normal and Difficile, 2026-11-19 23:52). Every level file is older
  than that log (newest: level21.json 22:45), so the log describes the current data. `Tuning.cs` and `SaveData.cs` carry
  uncommitted edits from the parallel visual workflow: camera pitch, wall opacity, title logo only. No gameplay value changed.

Conventions: yaw 0 faces +z, 90 faces +x. "Moving" means the PRD 3.3 predicate. "Route" means `designerRoute` (Normal).
"The solver" means the audit's earliest schedule.

---

## 1. The core rules everything else feeds

| Rule | How it works | Numbers | Code |
|---|---|---|---|
| Fixed step | One deterministic order per step: furniture, inhabitants (+household doors, robot), vision, win then caught, sitting + memory + door memory, investigations/dog hold/lamp/put-away, noise + creak, suspicion decay, HUD | dt 0.02 s | `GameState.FixedUpdate` (1641) |
| Moving | planar speed > 0.05 m/s, or yaw rate > 3 deg/s, or any **action** in progress (stool fall/right, lamp toggle, door opening, wardrobe in/out, robot shove, rocking-chair rock). Pinned (sat on, dog hold) and carried are never moving | 0.05 m/s, 3 deg/s | `MotionRule`, `FurnitureController.EndStep` (742) |
| Caught | timer runs while seen by a human AND moving; reset otherwise; caught at the grace. A door leaf seen swinging counts as the furniture seen moving | grace 0.20 s (Facile 0.30, Difficile 0.14) | `CaughtRule`, `GameState` 1743 |
| Win | furniture centre in the exit zone, not carried, not hidden, and not seen by any human (the dog does not count) | `ExitOnlyUnseen` | `GameState` 1736 |
| Lose | caught ("VU !") or one inhabitant's suspicion reaches 1 ("LOUCHE !") | | `GameState.Lose` |
| Telegraph | every body or head turn above 30 deg is preceded by a 0.6 s still beat ("hm ?" for humans, a sniff for the dog, head tilt 12 deg). Not a difficulty knob | 0.6 s, 30 deg | `InhabitantRoutine` header, `Tuning` 49-50 |
| Inhabitant motion | walk speed per personality; body turn 180 deg/s; head 200 deg/s, head yaw limit +-80 deg. Inhabitants walk THROUGH the player furniture (no collision, IDEAS bug 1) | | `Tuning` 53-56 |

Perception (always on): HUD eye (Closed / Calm / Alarm / Dog, `GameState.ComputeEye` 2377), red screen-edge pulse while the
caught timer is above zero, floor cone per watcher (shader looks: calm gradient, sweeping band when alerted or investigating,
outward waves + red when seeing; dashed outline when seeing; cone cut by occluders, x-ray hatching behind walls), a facing
chevron drawn over walls (`VisionConeView` 166-176, 249-263, 448-472). No near-miss feedback exists (IDEAS QW10).

---

## 2. The six bodies

All rows from `BodyDef.For`; careful = `Tuning.CarefulFactor` 0.5 x max speed. Hop = one noise event every pi/14 = 0.224 s
of moving (turning in place included), 2.0 m radius, on a hard floor (`FurnitureController` 782-791). The office chair rolls
instead (one tick every 0.3 s of rolling, glide included, radius 1.2 m).

| Body | Size w x h x d (m) | Radius | Max / careful (m/s) | Accel | Turn | Special rule | Noise per metre at max | Fits wardrobe | Seat (can be sat on) | Load allowed | Levels |
|---|---|---|---|---|---|---|---|---|---|---|---|
| chair | 0.45 x 0.90 x 0.45 | 0.28 | 1.5 / 0.75 | 10 | 360 | none | 1 hop / 0.34 m | no (0.45 > 0.40) | yes | yes | 1 2 3 8 9 11 17 |
| stool | 0.35 x 0.55 x 0.35 | 0.22 | 2.4 / 1.2 | 14 to 1.0 m/s, then 1.2 | 540 | tips when released above 1.3 m/s or on a head-on wall hit above 1.3 m/s | 1 hop / 0.27 m (careful) | yes | yes | yes (fits with it: 0.80 m) | 4 12 18 19 22 23 24 |
| armchair | 0.85 x 1.05 x 0.85 | 0.45 | 0.9 / 0.45 | 6 | 200 | needs 1.5 m corridors | 1 hop / 0.20 m | no | yes | yes | 5 14 |
| floor lamp | 0.35 x 1.80 x 0.35 | 0.22 | 0.6 / 0.3 | 4 | 180 | light switch, dark range | 1 hop / 0.13 m | yes (1.80 <= 1.85) | no | no (validator) | 6 16 20 |
| office chair | 0.55 x 1.00 x 0.55 | 0.30 | 2.8 / 1.4 | 8 | 360 | glides 0.4 s after release | 1 roll / 0.84 m, radius 1.2 m | no | yes | yes | 7 13 21 |
| rocking chair | 0.60 x 1.05 x 0.85 | 0.36 | 1.2 / 0.6 | 6 | 240 | rocks 0.8 s (0.4 careful) after every stop | 1 hop / 0.27 m | no | yes | no (validator) | 10 15 |

Notes that matter for design:
- Careful mode is NOT quieter. It halves speed only; the hop rate is per second, so a careful body makes twice the hops
  per metre at the same 2.0 m radius. Its uses: the stool never reaches its tip speed (1.2 < 1.3), the rock shortens to
  0.4 s, the load holds (section 3.13). (`FurnitureController.MaxSpeed` 233, `GameState.StepRock` 1352.)
- A move shorter than 0.224 s makes no hop at all (`hopTime` restarts at 0 on every stop). The audit does not use this
  (it keeps hops out of earshot), a human can.
- The stool is played at 1.2 m/s everywhere: the audit models the stool as always careful unless asked for full speed
  (`SearchOptions.FullSpeed`, only the level 4 lesson check). Every stool route (4, 12, 18, 19, 22, 23, 24) is 100 % careful.
  After level 4 the stool is "the small slow body that fits in a wardrobe"; its tip rule never matters to the solver.
- The dog runs at 2.6 m/s (`Tuning.DogRunSpeed`); the code comment says "faster than every body", but the office chair
  (2.8) outruns it. No level pairs them.

---

## 3. Verb and rule catalogue

Each entry: how it works (code), numbers, how the player perceives it, which levels use it (verified in the JSON; "on the
route" verified in the route or the audit log).

### 3.1 Vision and personalities
- How: at least one of 5 sample points (box centre + 4 top corners, inset 0.03 m) inside range, inside the half angle (a
  true 3D cone), and no Occluder-layer hit on the ray (`Vision.Step`, `VisionMath`). Occluders: walls, props with
  `occluder: true`, platforms and ramps, closed or open door leaves. NOT occluders: decoys (Furniture layer), railings,
  inhabitants, the robot. A load raises the box by 0.25 m; a stool lying down uses a lying box.
- Personality rows (`PersonalityDef.For`, all used somewhere):

| Personality | Walk | Range | Half angle | Hearing | Suspicion gain | Tolerance | Carry | Dark range (x0.4) | Levels |
|---|---|---|---|---|---|---|---|---|---|
| default | 1.2 | 10 | 55 | 1.0 | 1.0 | 0.75 | 1.0 | 4.0 | 1-7 |
| dreamer | 0.9 | 8 | 45 | 0.7 | 0.7 | 0.75 | 1.0 | 3.2 | 8 12 19 20 24 |
| watchful | 1.2 | 10 | 60 | 1.0 | 1.5 | 0.50 | 1.0 | 4.0 | 9 13 15 16 19 20 21 22 24 |
| hurried | 1.7 | 10 | 50 | 0.5 | 1.0 | 0.75 | 1.2 | 4.0 | 13 16 21 22 |
| granny | 0.8 | 7 | 55 | 0.6 | 1.0 | 0.75 | 0.8 | 2.8 | 10 14 17 22 24 |
| teen | 1.1 | 6 | 35 | 0.4 | 0.8 | 0.75 | 1.0 | 2.4 | 15 17 23 |
| tidy | 1.2 | 10 | 55 | 1.0 | 1.3 | 0.40 | 1.3 | 4.0 | 11 14 17 18 21 23 |
| dog | 1.4 (run 2.6) | 6 | 70 | 0 | 0 | n/a | 0 | 2.4 | 12 16 17 20 23 24 |

- The PRD "habits" (dreamer long dwells, watchful glances, hurried short dwells, granny sits, teen narrow) are NOT code: they
  are data conventions, checked as audit warnings (`LevelAudit.HabitWarnings`). Current warnings in the log: Max (13, hurried,
  mean dwell 5.5 s), Kevin (21, hurried, 11.3 s), Alfred (22, hurried, 23 s), Comtesse (22, watchful, two dwells without a
  glance), Mamie (17 and 22, granny, 60 to 120 s without sitting), Hugo (23, teen, a 30 deg glance).
- Seated watchers (any `sit` station) see from 1.15 m instead of 1.6 m (`SitEyeHeight`), so low cover hides more from them.
- Patterns: `loop`, `pingpong` (13 Max, 16 Max, 21 Kevin, 22 Comtesse and Alfred), `wander` seeded (14 Lea, 15 Hugo, 17 Hugo).
- Perception: the intro card lists each human's personality name and one habit line (`Hud.ShowPeople`); the model and tint
  differ per personality. Range and angle are visible only through the cone.

### 3.2 Displacement memory, suspicion, discoveries
- How (`FurnitureMemory`, `SuspicionMeter`, `GameState.StepMemory` 1977): each human keeps one player slot (start: the spawn).
  Seen within its tolerance of the slot: Confirmed, and **the slot moves to the seen pose** (the memory ratchets: a player
  seen still after a 0.7 m shift has a new home for that watcher). Seen beyond tolerance and not explained by a decoy for
  0.2 s in a row: one Discovery per incident, the watcher walks over (stops within 0.8 m), and if the furniture is within
  0.9 m picks it up (0.5 s), carries it back to the slot at 1.0 m/s x carry factor, puts it down (0.5 s); every memory then
  holds the put-down pose. Memories are per watcher, shared only after a carry or a sit.
- Discovery sources (each +0.34 x personality x difficulty on THAT watcher's meter): furniture seen out of place; stool seen
  lying down (anywhere); pratfall (a sitter sits on an empty seat); spot seen empty while the player hides in a wardrobe; a
  fallen load's clue seen; a door seen in another state than remembered (door memory); the human called by the dog finding
  the furniture out of place.
- Decay 0.02/s, only while that watcher is in Routine or Alerted. Lose at 1.0 (latched).
- Discoveries to lose (no decay), from the factors: default/hurried/granny 4 / 3 / 2 (Facile / Normal / Difficile); dreamer
  6 / 5 / 3; watchful 3 / 2 / 2; teen 5 / 4 / 3; tidy 4 / 3 / 2. A watchful watcher loses you on 2 discoveries at Normal.
- Unreachable: an investigator with no path (for example a closed leaf in the way, investigations use the current door mask)
  gives up and accepts the furniture where it stands (`GameState` 2163-2168, `GiveUpCount`).
- Perception: "hein ?" on a discovery; eye Alarm when seen out of place; suspicion bar (highest meter); a ghost of the last
  seer's remembered pose plus rings of that seer's tolerance around every same-kind decoy (`UpdateGhost` 2414).

### 3.3 Decoys
- How: a decoy of the player's kind explains the furniture when the player's centre is within the seer's tolerance of the
  decoy's centre, seen or not (`FurnitureMemory.Observe` 173-181). Decoys of another kind explain nothing. Decoys are on the
  Furniture layer: they block the player's movement but never hide it. A level with same-kind decoys forces the solver's
  schedule to be explained at least once (`World.NeedDecoy`, `LevelAudit` 4467); nothing proves the decoy is necessary.
- Geometry limit (new finding): the player cannot get closer to a decoy than collider half-width + body radius (skin 0.02 m).
  Approximate minimum centre distances: chair to chair decoy 0.49 to 0.51 m; office chair 0.56 m; rocking chair 0.64 m (narrow
  side); armchair 0.86 m; stool and lamp 0.38 m. Consequences: chair decoys never fool a tidy watcher (0.40) and at best
  marginally a watchful one (0.50); office-chair decoys fool only 0.75-tolerance watchers; armchair decoys can never explain
  an armchair, even at 0.75. The audit already warns for level 13: all four office-chair decoys "n'explique rien" for
  Claire (watchful), only Max (hurried) is fooled (8 explained samples).
- Perception: eye stays Calm when explained; rings around same-kind decoys while out of place.
- Levels: 3 (6 chairs, 30 explained samples on the route), 7 (4 office chairs, 24), 13 (4 office chairs, 8). None after 13.

### 3.4 Hearing, rugs and soft floors
- How (`Hearing`, `GameState.StepNoise` 2281, `Emit` 2341): noise events with a radius, scaled by each listener's hearing
  factor; walls do not block sound. Radii: hop 2.0, roll 1.2, lamp click 2.5, topple 3.5, creak 7 (3.5 from a wardrobe),
  bark 6, crash 6. Rugs and `floor: "soft"` rooms silence hops, rolls, clicks and topples; never creaks, barks or crashes.
  A listener in Routine who hears anything is Alerted: telegraph, turn body and head to the source, look 2 s, turn back,
  resume. Already Alerted, only creak, bark and crash retarget it. The dog hears nothing.
- The solver is never heard: it keeps hard-floor moves out of each listener's radius + 0.25 m (`NoiseMargin`). So no level's
  designed solution uses a lure, although PRD 4.5 and 4.6 describe noise and the creak as lures.
- Perception: hop sound on hard floor, a faint "soft hop" on a silent floor or inside the robot's hum; no ring shows any
  noise radius. Rugs and carpet finishes are the only visual cue for silence (`floorFinish: carpet` is soft-only).
- Levels: rugs in 2 3 5 9 11 14 17 20 22 23 24; soft rooms in 13 18 19 20 21 22 23 24. Silent floor used within earshot
  (audit "echantillons sur tapis a portee d'oreille"): 2 (31), 5 (31), 14 (51), 19 (30), 22 (24), 23 (10), 24 (9). The rugs of
  9, 11 and 17 are never touched by the route (0 route samples); 3, 13, 18, 20, 21 cross silent floor out of earshot only.

### 3.5 Creak gauge
- How (`CreakGauge`): fills 0 to 1 while still, drains in 10 s while moving, creaks at 1 (7 m noise, then reset). Paused while
  carried or pinned (sat on, dog hold), not during the first 5 s. NOT paused while hidden in a wardrobe (muffled to 3.5 m).
  An action counts as moving, so it drains the gauge (a lamp toggling in place never creaks).
- Numbers: fill 20 s (Facile 25, Difficile 16), warning in the last 3 s.
- Perception: HUD gauge, last 3 s tremble + rising wood tension + gauge flashing at 6 Hz (IDEAS bug 9).
- Levels: every level. The solver keeps the gauge under 0.85; the log's peak is 0.29 (level 22), so the creak never shapes a
  designed route. Its only effect on the solver is the 8 s wait cap (section 8).

### 3.6 Careful mode (tiptoe)
- How: hold Left Shift or the left trigger; max speed x0.5, under `GameRules.Bodies` (`FurnitureController` 583).
- Perception: a careful hint on the HUD for every body (`Hud.SetBodyHints`); keyboard-only wording (IDEAS bug 3).
- Levels (route legs marked careful): 4, 12, 18, 19, 22, 23, 24 all legs (stool); 11 (4 of 22), 13 (21 of 22), 17 (5 of 32) for
  the vase. Audit "careful" lesson only in 4 (no schedule at full stool speed).

### 3.7 Stool tip
- How (`FurnitureController.Drive` 685, `EndStep` 765): released above 1.3 m/s, or a head-on (within 30 deg) wall hit above
  1.3 m/s, starts a 0.3 s fall (moving), lands with a 3.5 m topple noise, lies still until a move key, rights in 0.4 s (moving).
  Seen lying down = out of place anywhere. Tell between 1.0 and 1.3 m/s: lean back 8 deg and rattle; no tell while careful.
- Numbers: 0 to 1.0 m/s in 0.07 s, 1.0 to 1.3 in 0.25 s (the tell window), max 2.4. Braking: pressing careful above 1.2
  pulls the speed down at 14 m/s2, so "sprint then Shift then release" is safe; the audit never sprints.
- Perception: lean + rattle sound, topple sound, HUD "tipped" line.
- Levels: all stool levels have it; only 4 checks it.

### 3.8 Office chair glide
- How (`FurnitureController.Drive` 692-716): released (or steered against its motion) above 0.05 m/s, it slows to 0 in exactly
  0.4 s at constant deceleration, turning with its velocity. The glide is moving. Input against the motion brakes no faster.
- Numbers: glide distance about 0.19 x v0: 0.53 m from 2.8 m/s, 0.27 m from careful 1.4 m/s. Rolls are 1.2 m noise.
- Perception: a stop ring on the floor at the predicted rest point (`GhostView.ShowStopRing`); caster rumble per roll tick
  (muffled on soft floor or in the hum).
- Levels: 7 (6 glide stops in the schedule), 13 (5), 21 (1). Lesson "glide" checked in 7 only.

### 3.9 Rocking chair after-swing
- How (`GameState.StepRock` 1339): on the first still step after travelling or turning, the chair rocks: an external action
  (moving, input ignored) of 0.8 s, or 0.4 s if careful is held at that moment. Never while pinned, carried or in an action.
  The rock creak is a sound only, not a noise event; no hops during the rock.
- Timing vs fairness: the rock (0.8 s) is longer than the telegraph (0.6 s); stopping at a telegraph's first step leaves
  0.2 s of rock after the turn begins, plus the 0.2 s grace, so it is survivable only if the cone does not land at once. The
  careful rock (0.4 s) is always inside the telegraph. That is the lesson the levels never teach.
- Perception: visual pitch 9 deg, 1.5 swings; runner creak.
- Levels: 10 (lesson "rock", waived by `lessonAdvisory: true`; audit: "les arrets ne contraignent rien"; the schedule never
  stops before its dash), 15 (1 rock in the schedule; lesson robot, the rock is not checked).

### 3.10 Floor lamp, darkness and switch-on
- How: E toggles the lamp (0.3 s action, moving, lit range during the toggle, 2.5 m click on hard floor, maskable by the hum)
  (`FurnitureController` 628-636; the comment there still says 0.2 s). Off: each watcher's range for the lamp's own samples
  x0.4 (`LampLight.RangeFactor`, `Vision.Step`), so the dark range is per personality and difficulty: 4.0 m for range-10
  humans at Normal (3.4 Facile, 4.6 Difficile), 3.2 dreamer, 2.8 granny, 2.4 teen, 2.4 dog. It does not apply to door leaves,
  the empty-spot check or clues. A human in Routine who sees the dark lamp where it belongs walks over and switches it on
  (0.5 s beat, `GameState.StepLamp` 2228); the dog never does. Only the lamp's own light is a rule: room lights, windows and
  "night" are visual (PRD 4.7). There is no per-level night lighting (IDEAS ART1: level 16's start view is as bright as day).
- Audit: lesson dark = (a) no schedule with the lamp always on (real check), (b) "not a free pass": some memory watcher comes
  within its dark range of ANY cell of the lamp's path at ANY time (`DarkFreePass` 2165-2210), unsynchronised and blind to
  facing. It is weak: level 6 passes with the watcher 1.3 m from the path at 19.8 s, after the 15.9 s exit; level 20 passes
  with Papa 0.0 m from the path at 42.6 s.
- Perception: lamp light off and the room's lights dimmed to 0.4, each cone drawn shorter and dimmer, click sound, lamp hint.
- Levels: 6 (1 toggle), 16 (1), 20 (17 toggles: see section 5, item 13).

### 3.11 Being sat on
- How (`InhabitantRoutine` sitting, `GameState.StepSitting` 2047, `PlayerSeatIsHome` 1609): a station with `"sit": "player"`
  and a `seat` home. At the moment of sitting, if the body is a seat, upright, not carried or hidden, and its centre is within
  0.75 m of the seat home: it snaps there, is pinned for the dwell (never moving, never caught, creak paused) and every memory
  takes that pose. Otherwise a pratfall: 1.0 s fall, one discovery, an Alerted look at the empty seat. Any seat body works
  (all but the lamp), not only the armchair: level 10's granny sits on the rocking chair.
- Perception: from the start of the sitter's walk, a seat ghost and a 0.75 m ring at the seat home; HUD "sat on" line.
- Levels: 5 (dwell 0.5; sat on 1.7 s in the schedule), 10 (dwell 4.0; never fires: Mamie reaches station 3 after about 25 s,
  the exit is at 18.1 s, no "assis dessus" in the log), 14 (dwell 0.5; sat on 1.6 s). Audit lesson "sit" only in 5.

### 3.12 Seats on props (context)
Sitting on a sofa or armchair prop lowers the eye to 1.15 m and claims the seat (`SeatRegistry`; a held seat makes the visit a
standing dwell). Used in 4 8 10 12 14 15 17 22 24. No player rule beyond the lower eye.

### 3.13 Load (vase on board)
- How (`LoadBalance`, `GameState.StepLoad` 1406): kinematic rule. The load falls when |v(t) - v(t - 0.5 s)| reaches 1.8 m/s.
  Holds: chair straight start or stop (1.5), any careful straight move, careful 90 deg chair turn (1.06), careful chair
  reversal (1.5), robot shove (0.5). Falls: 90 deg turn at full chair speed (2.12), full reversals, office chair full start or
  full glide (2.8), careful U-turns of the stool and office chair. (PRD 3.4 says "a full speed start or stop drops it": wrong
  for the chair, right for the office chair.) The sample box is 0.25 m taller while loaded. A fall: 6 m crash (alerts like a
  creak, never masked), a clue on the floor; a memory watcher who sees it takes one discovery and puts it away (0.6 s).
- Perception: the vase sways (visual spring), balance gauge left of the creak gauge, red from 0.9 of the threshold; crash.
- Kinds: `vase`, `books`, `plant` exist (`LoadView` 32-34) with the same rule; only `vase` is used.
- Levels: 11 (lesson load binds: the load-blind schedule drops it at 1.68 s), 13 (binds, 6.14 s), 17 (binds inside "final").

### 3.14 Closed doors (the player opens)
- How (`GameState.ClaimActionKey` 925, `DoorGeometry.InReach` 299): E within 0.85 m of the door centre, footprint outside the
  swing sector, still and upright: a 0.6 s opening action (moving). The leaf's 4 samples are tested during the swing: a human
  who sees the swinging leaf sees the furniture moving (caught after the grace) even if the furniture itself is out of sight.
  The swing is a sound, not a noise event. The player can only open, never close. The leaf stays open. Station walks are
  frozen at build time with the authored door state (`RoutineFactory`, `FreezeStationWalks`), so opening a door never changes
  a routine; investigations and carries plan on the current door mask.
- Hard cap: at most 2 leaves per level (`Tuning.MaxLeavesPerLevel`, validator 777): leaf i is NavMesh area 3 + i and the audit's
  door state is a bitmask.
- Perception: "E : ouvrir la porte" hint (keyboard wording only), door sound.
- Levels with a closed leaf: 8 16 17 18 20 21 22 23 24. Opened on the route: 8, 17, 21, 23, 24 (one each). Never opened by the
  player: 16, 18, 20, 22. Lesson door binds in 8, 17 and 24 (no schedule with every leaf locked).

### 3.15 Doors opened by inhabitants
- How (`GameState.StepHouseholdDoors` 2754, `WalkReachesLeaf` 2799): a closed leaf with `openedByInhabitants: true` that an
  inhabitant's walk crosses: it stops 0.6 s, the leaf swings open (household swing: no samples, cannot catch), stays open, and
  every door memory remembers it open. Nothing stops the player from opening that same leaf first.
- Perception: the walker pauses at the door, door sound.
- Levels: 18 (Odile opens the kitchen door in the first seconds), 20, 21, 22, 23, 24 (one leaf each).

### 3.16 Door memory
- How (`DoorMemory`, `GameState.StepDoorMemory` 2613, `StepDoorPutBack` 2700): a LEVEL flag (`doorMemory: true`). Every human
  with memory knows the authored leaf states. A leaf seen (its 4 samples) in another state: first sighting = one discovery
  ("hein ?"), and the watcher walks to put it back (close it) unless someone is already going; the put-back updates every
  memory. Household openings update every memory. It is not a personality trait: in 22 Alfred and Mamie remember doors as
  much as the Comtesse.
- Perception: "hein ?", then a watcher walking to the door and closing it. No HUD marker of remembered door states.
- Levels: 18, 20, 22, 23. Only 23 has the player open a door in a door-memory level.

### 3.17 Robot vacuum
- How (`RobotPath`, `GameState.StepRobots` 1248, `Contact` 1286, `Hearing.IsMasked`): a fixed timeline on a loop of waypoints
  (2 points = there and back), never waits, not seen, no collider, not an occluder, ignored by the household. Contact (its
  0.17 m disc begins to overlap the footprint): a 0.25 m shove over 0.5 s along its heading (moving: caught if seen; can leave
  the furniture out of place), refused while pinned, carried, lying or in an action, stopped by any collider; the robot then
  reverses. Hum: within 2.5 m of the robot, hops, rolls and clicks emit no noise; creak, topple, bark and crash still do.
- Limits: at most 1 robot; floor level only; never through a leafed doorway; 1 m clear of spawn, seat homes and exit; clear of
  props and decoys (validator 1394-1449). Speed and start index are per robot.
- Perception: a 3D hum loop audible from 0.6 to 7 m (the rule radius is 2.5 m: the ear cannot tell where masking ends), a
  pulsing status light, a bump sound on contact, masked hops play the soft hop. No floor ring for the hum.
- Levels (loop, period): 9 (5.0 m line, 25 s), 15 (2.0 m, 10 s), 17 (1.5 m, 7.5 s), 21 (1.75 m, 8.75 s), 24 (3.5 m, 17.5 s). All
  five are 2-point lines at 0.4 m/s from waypoint 0. Audit: the hum binds in 9, 15 and 17 ("ronronnement coupe, aucun
  horaire"); in 24 the robot binds by contact only (the hum is not needed); 21 does not check it.

### 3.18 Dog
- How (`GameState.StepBarks` 996, `StepDogHold` 1054, `Vision`): eye 0.35 m, 6 m, 70 deg; hears nothing; no memory; never
  catches; does not count for the exit; never switches the lamp on. Sleep stations: eye closed for the whole dwell, then a 0.6 s
  wake telegraph (sniff). Seen moving (furniture or a swinging leaf) by the awake dog for the grace: a bark (6 m noise that
  retargets Alerted humans), then 3 s of cooldown. After a bark the dog runs at 2.6 m/s to the furniture (chasing it if it
  moved), pins it within 0.9 m (no input, creak paused, barking every 0.8 s as a sound), and the nearest free human with memory
  is sent: out of place for that human's memory = one discovery and a carry back; in place = nothing, the hold ends. No human
  can come within 6 s: the dog gives up. Hiding in a wardrobe ends the hold.
- Perception: cyan cone (vivid while it sees you), "z" while asleep, blinking marker on waking, sniff, bark, HUD hold line.
- Levels (stations): 12 one spot (7.25, 4.5) facing 320, awake 12 s then asleep 2 s (awake 86 %); 16 asleep 10 s / awake 4 s;
  17 asleep 18 / awake 6; 20 asleep 10 / awake 6, walks 5.6 m between them; 23 asleep 10 / awake 6; 24 one spot, awake 600 s.
  Audit lesson pet (no schedule with the dog's eye at 1.6 m, so low cover is required) binds in 12 and 24, not in 17.

### 3.19 Platforms (mezzanine) and height
- How (`LevelBuilder.BuildSplitLevel` 526, `FloorMap`): solid boxes on the Occluder layer, 0.6 to 1.0 m high, ramps up to 20 deg
  (occluders too), railings 0.9 m on the Furniture layer (stop movement and the NavMesh, never sight). The furniture, its samples,
  the inhabitants and their eyes all stand on the floor height.
- What height does for cover: the platform box hides only rays that pass below its top. A body standing on a 0.6 m platform
  has every sample above 0.6 m, so the platform never hides it from a standing (1.6 m) or seated (1.15 m) human: it is MORE
  exposed over furniture. The platform hides a body on it from the dog (0.35 m eye), and hides a low body (the stool, top
  samples at 0.52 m) hugging its far side from humans. The audit's split lesson only proves the platform is needed as a PATH.
- Perception: raised floor, railings; cones drape over platform edges.
- Levels: 14 (1.0 x 6.9 m), 17 (1.0 x 7.4), 19 (10 x 1.5), 21 ("Passerelle" 1.5 x 7.4), 23 and 24 (identical 1.0 x 6.4 at
  (9.25, 6.7), same ramps). All 0.6 m high. Route points on the platform: 14: 2, 17: 2, 19: 15, 21: 9, 23: 6, 24: 6. Split binds in
  14, 17 (inside final), 21, 24 (inside final).

### 3.20 Wardrobe
- How (`WardrobeRule`, `GameState.ClaimActionKey` 932-961, `StepWardrobe` 2559): a prop of kind `wardrobe`, exactly
  1.0 x 2.0 x 0.6 m (validator), full occluder. The body fits if width and depth <= 0.40 m and height (+0.25 m load) <= 1.85 m:
  the stool and the floor lamp only. E with the centre 0 to 0.6 m in front of the front face (local +z) and within its width,
  no closed leaf in reach: a 0.25 s action (moving), then hidden: no samples (never seen, robot contact ignored, dog hold
  ends, exit does not count), no movement; E again: 0.25 s action, visible in front. The creak gauge keeps filling (3.5 m
  creak). While hidden, each human who sees the remembered spot empty for 0.2 s takes one discovery (once per hiding) and
  walks to the spot (`FurnitureMemory.ObserveEmptySpot`). Asymmetry: an empty spot is only noticed while you hide; a
  furniture that simply moved away unseen leaves no trace.
- Perception: hide/leave hint (pad variant, no touch variant), door swing animation, the furniture slides 0.3 m in, sounds.
- Levels: present in 18 (1), 19 (4), 20 (3), 22 (4), 23 (3), 24 (3); hides on the route: 18 (1, hidden 3.8 s), 19 (2, 5.7 s),
  22 (4, 8.9 s), 23 (1, 3.7 s). 20 and 24 have wardrobes the route never uses. Lesson wardrobe binds in 18, 19, 22, 23.

### 3.21 Fixed sentinel and metronome glance (a data pattern, not a code mechanic)
- How: one station with a dwell longer than the audit horizon (300 s) and its glances listed one by one at a constant period
  (34 to 65 entries per sentinel). A glance of yaw above 30 deg costs 0.6 s telegraph + |yaw| / 200 s turn + hold + 0.6 s
  telegraph + turn back. Every metronome uses the head limit, 80 deg (0.4 s turns), so one glance lasts hold + 2.0 s.
- The metronomes: 18 Odile 9 s period / 5 s hold (2 s facing front between glances); 19 Maman 7.5 / 4.5 (1 s front); 20 Maman
  5.5 / 1.5 alternating +-80 (2 s front); 21 Bertrand and Sofia 4.5 / 2.5 alternating +-80 (0 s front between glances, the head
  never rests; Sofia 0.75 s ahead of Bertrand); 23 Odile 10 / 6 (2 s front).
- Watchers who never leave one spot (all patterns): 9 Claire (8.25, 6.75), 15 Claire (6.75, 4.25) (each turns between facing
  180 and 0); 12 dog; 18 Odile (after a 2 m walk); 19 Maman (after a 16 m walk across the house in the first ~14 s); 20 Maman;
  21 Bertrand and Sofia; 23 Odile; 24 dog. Near-fixed: 22 Alfred spends 40 of every 46 s at (20.35, 2.75).
- Perception: as any watcher: "hm ?" and head tilt before each glance, cone and chevron sweep.

### 3.22 Difficulty (Facile / Normal / Difficile)
- Knobs (`DifficultyDef`, values `Tuning` 942-958), applied at level build (`RoutineFactory.PersonalityOf`, `GameState` 642-644,
  763): view range x0.85 / 1 / 1.15 (lamp factor on top, dog included); half angle -5 / 0 / +5 deg; hearing x0.75 / 1 / 1;
  suspicion gain x0.75 / 1 / 1.5; caught grace and dog bark grace 0.30 / 0.20 / 0.14 s; creak fill 25 / 20 / 16 s.
- Not scaled: telegraph, glance timings, dwell times, walk and run speeds, tolerances, robot, load threshold, rock, glide,
  wardrobe, dark factor itself. Records are per difficulty (`level@facile`, `@difficile`); a win at any difficulty unlocks.
- Effect on the solver: Difficile changes the earliest exit in only 6 levels (1 +0.4 s, 13 +10.4, 19 +7.5, 20 +1.9,
  22 +18.5, 24 +0.5); identical in the other 18. The solver is never heard, never seen moving, never discovered, so hearing, grace and
  suspicion never touch it: Difficile is mostly human pressure (2-discovery losses, 7-step grace) the audit cannot show.

---

## 4. Corrected mechanics matrix (from the JSON and the audit log)

Legend: "o" present but not used by the route; "X" used on the route (or binding per the audit, noted); "n/c" present,
binding not checked by the audit (no matching lesson). Numbers as stated.

| Mechanic | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Body | C | C | C | S | A | L | O | C | C | R | C | S | O | A | R | L | C | S | S | L | O | S | S | S |
| Lesson field | | | | careful | sit | dark | glide | door | robot | rock (waived) | load | pet | load | split | robot | dark | final | wardrobe | wardrobe | dark | split | wardrobe | wardrobe | final |
| Humans (+ dog) | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1+d | 2 | 2 | 2 | 2+d | 3+d | 1 | 2 | 2+d | 3 | 3 | 2+d | 3+d |
| Same-kind decoys | | | X 6 | | | | X 4 | | | | | | X 4 | | | | | | | | | | | |
| Rug / soft floor | | X | o | | X | | | | o | | o | | o | X | | | o | o | X | o | o | X | X | X |
| Sat on (player seat) | | | | | X | | | | | o | | | | X | | | | | | | | | | |
| Vase on board | | | | | | | | | | | X | | X | | | | X | | | | | | | |
| Closed leaves / opened by route | | | | | | | | 2/1 | | | | | | | | 1/0 | 2/1 | 1/0 | | 2/0 | 2/1 | 2/0 | 2/1 | 2/1 |
| Door opened by inhabitants | | | | | | | | | | | | | | | | | | X | | X | X | X | X | X |
| Door memory | | | | | | | | | | | | | | | | | | X | | X | | X | X | |
| Robot (binds by) | | | | | | | | | hum | | | | | | hum | | hum | | | | n/c | | | contact |
| Dog (awake share; binds?) | | | | | | | | | | | | 86 %, binds | | | | 29 % | 25 %, no | | | 38 % | | | 38 % | 100 %, binds |
| Mezzanine (route pts; binds?) | | | | | | | | | | | | | | 2, binds | | | 2, binds | | 15 | | 9, binds | | 6 | 6, binds |
| Wardrobes / hides on route | | | | | | | | | | | | | | | | | | 1/1 | 4/2 | 3/0 | | 4/4 | 3/1 | 3/0 |
| Watcher who never leaves | | | | | | | | | X | | | dog | | | X | | | X | X | X | X x2 | (Alfred) | X | dog |
| Metronome glance (period/hold s) | | | | | | | | | | | | | | | | | | 9/5 | 7.5/4.5 | 5.5/1.5 | 4.5/2.5 x2 | | 10/6 | |
| Lamp toggles on route | | | | | | 1 | | | | | | | | | | 1 | | | | 17 | | | | |
| Careful legs on route | | | | all | | | | | | | 4/22 | all | 21/22 | | | | 5/32 | all | all | | | all | all | all |
| Glide stops / rocks on route | | | | | | | 6 | | | 0 | | | 5 | | 1 rock | | | | | | 1 | | | |
| Pingpong / wander watcher | | | | | | | | | | | | | P | W | W | P | W | | | | P | P x2 | | |
| Seated watcher (prop) | | | | X | | | | X | | X | | X | | X | X | | X | | | | | X | | X |

Bodies: C chair, S stool, A armchair, L floor lamp, O office chair, R rocking chair.

---

## 5. Where my reading disagrees with the review (with evidence)

1. **The fixed sentinel is not new in 18.** Claire never leaves (8.25, 6.75) in 9 nor (6.75, 4.25) in 15 (one position, two
   facings); the dog never leaves its spot in 12. What 18 introduces is the metronome glance. Also, 19's Maman is not fixed at
   first: station 0 is (16.75, 8.25) for 0.5 s, then a 16 m walk to her post (0.75, 6.25).
2. **"A countess who remembers doors" (22):** door memory is a level flag that applies to every human with memory
   (`GameState` 806). In 22 Alfred and Mamie remember doors too.
3. **Level 9 robot "neither blocks nor helps":** the audit's robot lesson binds by the hum in 9 ("ronronnement coupe, aucun
   horaire : le ronronnement est requis"). Same in 15 and 17. Only in 24 does the robot bind by contact alone.
4. **Level 17 "robot, mezzanine bypassed":** the final lesson reports door, split, robot (hum) and load as binding; only the
   dog does not bind. The mezzanine carries 2 route points but no schedule exists without it.
5. **Level 12 "sofa-as-cover is optional":** the pet lesson binds (no schedule with the dog's eye at 1.6 m), so low cover is
   required somewhere on the route. And the dog is awake 12 s of every 14 s at one spot facing 320: it is not a sleeping dog.
6. **Level 24's dog:** a 600 s statue, yes, but awake throughout, and the pet check binds in 24.
7. **Level 17 "Lea faces the main room during her 25 s on the sofa":** her 25 s dwell is station 0 at (11.75, 0.6) facing 180;
   the sofa (Canape) is station 1, 6 s. docs/m7/design.md has the correct lever (station 0 faces north).
8. **"Someone sits on you" in 10:** the station exists (Mamie #3, dwell 4) but never fires before the exit (18.1 s); the log
   has no "assis dessus" for 10. The sit rule is not armchair-specific: any seat body works.
9. **Rug row:** 9, 11 and 17 have rugs the route never touches; silent floor matters (in earshot) only in 2, 5, 14, 19, 22,
   23, 24.
10. **"Exactly two closed doors in 20 to 24":** that is the hard cap `Tuning.MaxLeavesPerLevel = 2`, not a design habit. A third
    door needs code (NavMesh areas and the audit's door bitmask).
11. **Decoys in the late game (21 "fill the open space with decoy office chairs", the Showroom, "a rest among decoys"):**
    the collider geometry in 3.3 means office-chair decoys fool only 0.75-tolerance watchers. In 21 they would fool Kevin
    (hurried) and never Bertrand (watchful) nor Sofia (tidy). A chair Showroom needs a default, dreamer, hurried, granny or
    teen guard. The audit already warns about this for level 13.
12. **"Switched off, the lamp is seen from 4 m only":** 4 m holds for range-10 humans at Normal only; it is range x 0.4 per
    watcher and difficulty (Maman in 20 at Difficile: 4.6 m, still under the 4.9 m the review measured; Papa 3.2 m).
13. **Level 20's route:** its 17 toggles (t 0.3 to 5.1 s, every 0.3 s, in place) are a solver artefact: each toggle is a 0.3 s
    "moving" action that waits in place and drains the creak gauge; the lamp ends off. A human presses E once.
14. **Height as cover (14 "with height as cover", 17 "route the path over the mezzanine"):** a body on a 0.6 m platform is
    never hidden from a human by the platform (3.19). Moving the route onto the mezzanine changes the path, not the cover;
    cover from height exists only against the dog.
15. **Level 21's "two sentinels share one metronome":** same period (4.5 s) and hold (2.5 s), alternating +-80, Sofia 0.75 s
    ahead. With a 2.5 s hold each glance fills the whole period: the heads never rest facing front.
16. **"Data only" for every fix:** true for the 10 retunes as written, but the redesign must respect hard caps: 2 leaves, 1 robot,
    1 dog, 3 humans, platforms 0.6 to 1.0 m, ramps up to 20 deg, wardrobe size fixed, corridors 1.2 m (1.5 m for the armchair),
    robot 1 m from spawn, seats and exit, plus the draw-call budget (21: 150/160, 22: 145/160, 24: 144/160; materials 31/32 in
    22 and 23).
17. **Reordering and unlocks** (the review's open question): `SaveData.IsUnlocked(order, i)` = i is 0 or `order[i - 1]` is won.
    Records are keyed by id and survive, but after a reorder a level locks if its NEW predecessor was not won, even if the
    level itself was won before (for example 17 placed after 18: a player who won 1 to 17 but not 18 can open 19, not 17).
18. **23 and 24 share their core:** the galerie (8.95, 6.7, 8.9 x 6.4), the salon/salle rectangle, the mezzanine, both ramps
    and the corridor wardrobe at (14.05, 6.25) are identical. Reusing 23's plan for the Showroom also means changing 24.

The review is right on the rest I checked: decoys stop after 13, the sit after 14, the rocking chair after 15, the vase after
17; the stool is the body in 5 of 18 to 24; a wardrobe stands in 6 of 18 to 24; 20 to 24 each have two closed leaves, one with
`openedByInhabitants`; four of 19 to 24 have a 0.6 m mezzanine with two ramps; 23's Odile is 18's Odile with 10 s / 6 s instead
of 9 s / 5 s; 6's station 0 is at (4, -0.25) facing 270; level 10 is waived (`lessonAdvisory: true`).

---

## 6. In the code, used in no level (or never on any route)

| Mechanic | State | Note for the redesign |
|---|---|---|
| Loads `books` and `plant` | never used | same rule as the vase; free visual variety |
| Load on the stool or the armchair | never used | a loaded stool still fits a wardrobe (0.80 m): "hide with the vase" is data-only |
| Robot loops of 3+ waypoints, custom `speed`, `start` index | never used | all 5 robots are 2-point lines at 0.4 m/s from waypoint 0; a loop that crosses a room is data-only |
| Door leaf authored `open` | never used | the player cannot close doors, so an open leaf is only a door-memory trap if the household changes it |
| Platform heights above 0.6 m (max 1.0) | never used | |
| Dog patrol (pingpong or wander, real distances) | never used | dogs use at most 2 stations, longest walk 5.6 m (20) |
| Dog hold as a designed beat | never in a solution | the solver is never seen moving by the dog, so it never barks |
| Noise lures (hop, creak, load crash as lure) | never in a solution | the solver is never heard; PRD 4.5/4.6 lures exist only for humans |
| Accepting a discovery and the carry back | never in a solution | the solver is never seen out of place (except explained) |
| Investigator gives up behind a closed leaf and accepts the new spot | never designed | a real lever in door levels |
| Floor lamp in a wardrobe | never used | the lamp fits; 20 has three wardrobes and never hides |
| Careful rock (0.4 s) as the rocking-chair lesson | never binds | 10 is waived, 15 rocks once |
| Stool sprint (2.4 m/s) with careful braking | never used | the audit plays the stool at 1.2 m/s |
| Pratfall (sitter sits on an empty seat) | only as a fail path | a "be back in time" goal lives here |
| Empty-spot discovery while hidden | rarely relevant | hides are short (3.7 to 13.8 s) |
| Office chair outrunning the dog (2.8 > 2.6) | no level pairs them | |
| Seated-watcher low eye (1.15 m) as an intended cover lever | incidental only | |

---

## 7. Proposed by the review (or implied) that does not exist yet

| Proposal | Status | What it needs |
|---|---|---|
| Lit zone the lamp must cross switched on (20) | missing | only the lamp's own light is a rule; a lit-zone flag per room or area, read by `FurnitureController.SightRangeFactor` / `Vision`, modelled in the audit's lamp search and `DarkFreePass` (review flags it) |
| Two exits in one level | missing | `LevelDef.Exit` is one `ZoneDef`; win check (`GameState` 1736), validator, audit `InExit`, builder (review flags it) |
| Timed return as the goal | missing | a goal type beyond the exit; nearest existing pieces: sit station, seat ghost, pratfall (review flags it) |
| "A door only Dad opens" (20) | partial | `openedByInhabitants` exists but the player can open the same leaf; needs a player-locked flag (`OpeningDef`, `ClaimActionKey`, audit `Doors`). Data-only approximation: door memory on, so opening it in view is a discovery |
| Night look: dark walls, pools of light (20) | partial | colours, finishes, `lightWall: "none"` exist (visual); no per-level lighting preset (IDEAS ART1) |
| Ride in the robot's hum (9, 10, finale) | rule exists | readability: hum audible to 7 m but masks to 2.5 m, no floor ring; a hum ring or matched rolloff is presentation code |
| Third closed door anywhere | blocked | `MaxLeavesPerLevel = 2` |
| Two viable routes / "both wings viable" / "no dead room" checks | missing in the audit | the audit returns one earliest schedule; `Barred` cells exist only for platform cells (split lesson). A "barred region" or "must visit" search option is audit code |
| "Wait often, never long" (25 to 40 %, 3+ pauses, none above 6 s) | partial | the audit caps any wait at 8 s (`Tuning.AuditMaxWait`, loiter radius 1.5 m) and reports the longest wait, not the share or count of pauses; a 6 s cap changes a tuning constant used by every level |
| "Obstacle in the title on the route" | mostly exists | lesson checks exist for careful, sit, dark, glide, door, pet, split, robot, rock, load, wardrobe, final; none for decoys (forced use, not necessity), rugs, door memory, household doors, sentinels |
| Metronome sentinels | exists as data | glances are enumerated by hand (up to 65 entries); a "repeat every N s" glance field would be a small schema addition (optional) |
| Showroom with thirty decoys | data-only, at risk | draw-call budget (house levels already at 144 to 150 of 160) and the decoy geometry limit (3.3) |
| Dog on a patrol, exit in a watched room, Kevin across the way down, decoys at empty desks, gaps in cabinets, stations turned | data-only | `ExitOnlyUnseen` already makes the exit a watched-room puzzle (only humans count) |

---

## 8. Audit facts the level designers must know

- The solver is a perfect ghost: never seen moving, never seen out of place unless explained, never heard (hops kept
  0.25 m outside every radius), creak under 0.85, no wait over 8 s within 1.5 m. Its waiting times are a floor for humans, and
  every mechanic that needs a mistake or a lure (barks, holds, discoveries, carries, creak lures) is invisible to it.
- Lesson checks prove a mechanic is needed at least once, not that it shapes the level: 9's hum and 17's mezzanine bind while
  the review's distance metrics say they are barely used. Both readings are true; the redesign should target both.
- The dark free-pass check is unsynchronised and ignores facing (3.10): it cannot prove darkness matters in time.
- `AVERTISSEMENT depart retarde` in 1, 2, 3, 5, 7: some late starts have no schedule. Routines and the clock start at build,
  during the 5 s intro card (IDEAS bug 7), so a player who reads the card starts late.
- Difficile barely moves the solver (3.22).
