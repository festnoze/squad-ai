# Levels v2 - field feedback and design requirements (agent: feedback)

Date 2026-11-20. Read-only pass. Sources: the product owner's level review (scratchpad level_review.txt), docs/IDEAS.md,
docs/m7/design.md, docs/PRD.md (v1.10), docs/CONTRACT_M5.md 17 to 20, docs/CONTRACT_M6.md, docs/CONTRACT_M7.md 4 and 5,
docs/m6/levels.json, docs/m6/audit.json, docs/m7/design.json, docs/m8/ROOMS_PLAN.md, docs/m9/FLOORS_WALLS.md, the 24
level JSON files, levels.json, Core/Strings.cs, and spot reads of the code named below. Every number was re-read from
the files; where my reading disagrees with the review, section 2 says so with the evidence.

IDs: F = field fact, C = correction to the review, R = requirement (P0 must, P1 should, P2 could).

---

## 0. Headline

1. **The whole game is under 10 minutes of clean play.** The sum of the 24 designerRoute exits is about 575 s (9.6 min;
   level 10 stores departure times only). PRD 1.3 promises levels of 2 to 6 minutes, PRD 6.3 a first run of 60 to
   120 s on level 1 against a designer route under 40 s. The owner's best times on the first 18 levels were 8 to 34 s
   (CONTRACT_M7 4: level 13 in 8.4 s, level 17 in 15.6 s).
2. **Humans beat the audit, so the audit's exit is not a floor.** The owner cleared level 13 in 8.4 s when its audited
   exit was 26.2 s (now 25.4 s), and level 17 in 15.6 s against 21.2 s (now 20.4 s). The review's method note ("a
   human waits longer than a solver, so the waiting times are a floor") does not hold for a skilled player (C1). Any
   retune measured only with the strict audit can still be skipped.
3. **The review is right on direction** (no dead rooms, the titled obstacle on the route, wait often never long, vary
   neighbours, give the late game its own identity), and its levers mostly match docs/m7/design.md section 3, which was
   never applied (IDEAS bug 27). What the field data adds: rush counter-routes on every level, a start that waits for
   the player, a visible exit, readable threats (names, hum radius, noise), true hints, pillar 3 (lures) back in the
   level design, unlocks that survive a reorder, and several levers the review calls "data only" that need code or art.

---

## 1. Field facts (owner observations during development, checked against the files)

| ID | Observation (verbatim facts) | Status today, with evidence | What it means for the overhaul |
|---|---|---|---|
| F1 | Owner playtest of the first 18 levels: 8 to 34 s per level | Open: the curve retune never followed (docs/m7/design.md 2: "the table after is the table above"; IDEAS bug 27); later edits to levels 1 to 18 were looks (M8/M9) and level 13's hard route | Difficulty and length are the first problem, not looks |
| F2 | Level 21 felt very short (about 19 s) | designerRoute exit 18.7 s, 1 wait of 0.7 s in the route data; three of seven rooms hold no route point, station or robot waypoint (reunion, couloir, archives) | Matches review finding; level 21 is the clearest "big house, no puzzle" case |
| F3 | The dog did nothing when it detected you | Fixed: CONTRACT_M5 20 (run at 2.6 m/s, pin, a human comes, one discovery if out of place) | The dog is now a real setback, so a dog on patrol (review, level 24) has teeth; audited routes still forbid barks |
| F4 | Humans walked through walls instead of doors | Fixed (NavMesh walks, audit checks every station walk) | Every new plan keeps the NavMesh walk check green |
| F5 | Furniture placed back to front against walls | Fixed by hand; no automatic check found (LevelValidator.cs checks seat fronts only; PropKinds.cs:10 states the convention "back on +z against a wall, at yaw 0") | The overhaul moves many props: add a validator rule (R14) |
| F6 | Wants varied rooms, objects, floors, lights per room type | Done in M8/M9: 12 wall finishes and 10 floor looks in use over 108 rooms; lights by room type (RoomLights) | Keep room function coherent when plans change; the room id drives its type, objects and light |
| F7 | Asked whether the marble bathroom carved from a soft room in level 24 is right | See section 5, level 24: the soft "bureau" of V4 (4.4 x 6.4 m) became chambre_enfants (soft) + sdb (hard, marble); both are dead rooms, sdb is a dead end reachable only through the kids' room | Fine as fiction, but "floor" is a gameplay field: a soft/hard change is a design decision, and here it decorates two rooms nobody enters |
| F8 | Humans pass through the player furniture | Open: Main.cs:69 `IgnoreLayerCollision(Player, Inhabitant)` (IDEAS bug 1, AI1) | Until AI1 lands, no designed rest spot may sit on an inhabitant walk line (R14); with AI1 a bump becomes a design tool |
| F9 | Level 16 "night" is as bright as day levels | Open: no night or time-of-day concept exists anywhere in Assets/Scripts (grep "night": only prop kinds and level names); IDEAS bug 17 measured 0.446 start luminance, same as day | "Night" and "lit zone" need code (R12); the review's level 20 "Look night" is not data only |
| F10 | The exit is invisible from the start in big houses | Open: the exit is a green doormat only (QW9); no opening camera move (CA2) | R4 |
| F11 | The level timer and the house start while the intro card hides the player | Open: GameState.cs:1733 `Steps++` from the build; the card is held 4 s then fades 1 s (Tuning.cs:573 comment); 9 designer routes act at 0.3 s (levels 6, 9, 11, 12, 16, 17, 20, 21, 24; a lamp toggle on 6, 16, 20) | The designed first window is spent under the card; records include reading time (R4) |

---

## 2. Corrections and additions to the review (evidence from the files)

**C1. The audited exit is an upper bound on a skilled clean run, not a floor.** The audit is conservative on purpose
(LevelAudit.cs:150-203): moves at 1.25 m/s on a 0.5 m grid with axis-aligned legs (every designerRoute is a Manhattan
path, see level1.json), sight dilated 0.3 s each way (MarginSamples 3), "in place" only within 0.3 m of the spawn
(InPlaceRadius) where the game tolerates 0.75 m, decoys within 0.6 m where the game accepts 0.75 m, hearing plus
0.25 m, the creak gauge capped at 0.85, and zero discoveries, zero alerts, no creak (PRD M2 notes). A human cuts
diagonals, rides the real 0.2 s grace, and may spend two discoveries at Normal (suspicion +0.34 each). The owner's
8.4 s on level 13 (audit 26.2 s) is the proof. The ranking between levels is still useful; the absolute times and the
waiting shares are not a floor. Rush counter-routes exist only for level 5 (Step35b) and level 8 (Step45e), plus
lesson-specific ones on 10 (Step45p, waived), 11 (Step45q, Step57a vase drop), 12 (Step45g uncovered crossing) and 17
(Step57b vase drop): none for 13, none for 18 to 24.

**C2. floorColor and wallColor are not what the player sees.** The review says room colours are a data lever ("floorColor
and wallColor already exist per room"). In the shipped build every floor and wall is drawn by the one Texture2DArray
material: LevelBuilder.RoomSurface (LevelBuilder.cs:456-466) swaps the floor material for WallArray.Material and tags the
mesh with its finish only, and walls use `wallArray != null ? wallArray : Lit(WallColor)` (LevelBuilder.cs:1081). The
colours only reach the level select miniature (LevelMiniature.cs:315) and the no-texture fallback. The literal count is
right (84 of 108 rooms are "#B07A4E on #EDE6DA"), but the rendered variety comes from wallFinish (12 values, crepi
default in only 7 rooms) and floorFinish (10 looks). The palette lever is therefore the choice of finish (free since
walls 4), plus new slices where no existing finish gives the look (art, not data). Existing slices worth trying first:
sage and sageribbed walls with verde or herringbone floors for the manor, carpet or tile (no parquet) for the office
(WallArray.Slices, WallArray.cs:43-49). Whether a slice reads "dark green panelling" or "grey carpet" at play distance must
be checked on shots before promising it. What does support the review's "same house" impression is the mapping across
houses: every one of the 18 kitchens has subway tile walls, all 5 bathrooms white tile, quatrefoil appears in 14 levels
and travertine in 13 (FLOORS_WALLS.md 7.4). Within a house the rooms differ; between houses the same room type always
looks the same. Per-house finish sets (a manor set, an office set, a night set) are the fix.

**C3. The proposed level 24 finale cannot ask for a hide with the chair.** The review gives the finale "Chair (the one from
level 1)" and also asks it for "a hide". The wardrobe fits width and depth at most 0.40 m (Tuning.WardrobeFitWidth,
Tuning.cs:697): the stool and the floor lamp only; the chair is 0.45 m wide. Either the finale's hide is "rest among
decoys" (the chair's own hide, rule of level 3), or the body changes, or the fit rule changes (code).

**C4. A rocking chair lesson needs a watcher without memory, or rocker decoys.** The review rebuilds 15 as "short hops
between cover, each ending in a visible swing". docs/m6/levels.json explains why six audits failed on level 10: a still
furniture seen by a human must be within 0.3 m of its slot (InPlaceRadius), so a stop in a human's view is a discovery
unless it is at the spawn; the swing can only bind where a watcher sees the stop without minding where it is. The same
report found the fix: a dog (no displacement memory) made the rock lesson bind (rock-off schedule seen rocking at 14.2 s)
but the spawn idle broke the wait rule. So the rebuilt rocker level must put the swings in the dog's view or beside
rocking chair decoys (same-kind decoys explain the stop), and start the dog's first awake window early (about 9 s, the
agent's own note).

**C5. Unlocking follows the play order, and a reorder locks levels already won.** SaveData.IsUnlocked (Core/SaveData.cs:
285-292): index i is unlocked when i is 0 or order[i-1] is won. With the review's order (..., 14, 18, 17, ...), a save
that won 1 to 17 but not 18 finds level 17 locked although won; a save that won 1 to 10 finds level 11 (new slot 11,
after level 15) locked although it was playable. Cut ids stay harmlessly in `won`. Records are keyed by id, so they also
survive a redesign, which is wrong: the owner's 8.4 s on level 13 would stand as an unbeatable record on a retuned 13.
See R13.

**C6. Level 20's designer route toggles the lamp 17 times at the spawn.** designerRoute steps 1 to 17 are `toggle` every
0.3 s from 0.3 to 5.1 s at (5.75, 1.25) (15 toggles in designerRouteHard). It replays fine but it is an audit artifact:
the search treats an in-place action as an alternative to waiting. Any waiting-share metric must count in-place actions
as waiting, and the search should cost useless actions (a replay used as a "show me the route" assist or a trailer clip,
IDEAS MO1 and MK1, would flicker the lamp).

**C7. Soft floors swallow the hearing rule in the late game.** No room is soft in levels 1 to 12 (level 2 teaches rugs);
soft rooms then grow: 13: 1, 18: 2, 19: 3, 20: 2, 21: 2, 22: 3, 23: 3, 24: 4. In level 19, 55 of the 63 designerRoute
points lie on carpet (chambre, salon, galerie); in level 18, 15 of 18. Where the route is carpeted, hops are silent and
hearing never constrains. The review's matrix row "Rug or soft floor" looks like a rule in play; in practice it marks
the hearing rule switched off.

**C8. Level 16's hint is false and level 12's English hint is backwards.** level16.hint says "The dog never sleeps" but Rex
sleeps 10 s of every 14 s (level16.json: station (5.5, 0.75) dwell 10 sleep true, then (6.75, 0.75) dwell 4). level12.hint
(EN) "Catch his eye moving and he pins you" reads backwards (IDEAS bug 15, still present). If 16 is cut the first goes
away; the second must be fixed.

**C9. "Upstairs, Downstairs" (23) promises a floor the engine does not have.** Stacked floors are deferred (PRD open
question 21: one split level at most); the "upstairs" is the same 0.6 m platform as 14, 17, 19, 21 and 24. Another
reason, beside the review's, to cut or rename it.

**C10. Level 1 misses its own design intent.** PRD 6.3: "station 2 sweeps the whole room and forces a full stop", first run
60 to 120 s. Since M2.1 the watcher starts at station 3 and the clean schedule exits in about 11 s and "never meets
station 2" (PRD M2 notes); open question 10 (start station A/B) was never decided. The review says "change nothing";
I would still run that A/B (start at station 1 with an 8 s cap, or let the route meet station 2 once) because level 1
is the demo's first minute (IDEAS MO1, MK3).

**C11. docs/m7/design.md levers the review leaves out.** Level 5 (sit on the player 0.5 to 2.5 s, station 2 dwell 8 to
6.5), level 7 (both dwells 2.5 to 2.0), level 18 (Odile looks away 5 to 4.7 s), level 9 (start Claire at station 1 facing
the route, glances +-45 to +-80), level 12 (Paul station 2 faces north over the salon). They are compatible with the
review's levers (9: the review moves the robot, design.md moves Claire; doing both binds the lesson and forces the wait).
The review keeps 5, 7 and 18 unchanged: a minor conflict to settle with one audit each.

---

## 3. Design principles and requirements, prioritized

### P0 (the overhaul is not judgeable without these)

**R1. Measure length and difficulty with three numbers, not one.** (Adds to the review.)
- (a) Strict audit exit, Normal and Difficile (what exists).
- (b) A relaxed audit or bot run that uses the game's own tolerances (0.75 m in place, 0.75 m decoys, the 0.2 s grace,
  diagonal moves, up to the discovery budget), or the IDEAS LD2 human-reaction bot. Acceptance: the relaxed exit is at
  least 60 % of the strict exit on every level; below that, the level is skippable (for scale: the owner's 8.4 s on
  level 13 was 32 % of its 26.2 s audit). Needs audit code.
- (c) Human first clear including retries, from a local run log (IDEAS AN1; `GameState.Restarts` exists, GameState.cs:101,
  but is never kept). Needs code; until then, the owner's stopwatch.
- Targets per act in section 4.

**R2. Every level has a rush counter-route that loses.** (Adds; direct answer to F1 and C1.) For each level, three
replays at Normal must not win: the designer route with every wait removed (as Step45e does for level 8); the straight
shortest path at full speed from the spawn; and, on load levels, "drop the vase at the spawn, then full speed" (the
CONTRACT_M5 19 M5 item, deferred by 19.1 and done only for 11 and 17). Acceptance: a PlayMode step per level, or one
data-driven step over levels.json.

**R3. Wait often, never long, and tighten the margin curve.** (Agrees with the review's rule 3 and design.md 4.2.)
- Waiting share 25 to 40 % of the strict schedule, three or more pauses, none above 6 s (the audit's hard cap is 8 s,
  PRD M2 gate; a wardrobe hide counts as waiting, docs/m6/audit.json: keep a hide with both 0.5 s actions to about 6 s).
- Count in-place actions (toggles, hides) as waiting in the metric (C6).
- Margin (slack samples) from about 15 on levels 1 and 2 down to 4 to 6 on the act closers (CONTRACT_M7 4.2), passing at
  Normal and Difficile; never easier than two levels before.
- The creak stays a safety net (with pauses under 6 s and drain twice as fast as fill, it never fires in a designed
  route); do not design a level that needs a creak unless R9 lands.

**R4. The level starts when the player does, and the goal is known before the first step.** (Adds IDEAS QW4, QW9, CA2,
UX3; F10, F11.)
- Hold the clock, every routine, the robot and the creak start delay until the first move or action input after the
  card (QW4). Then the audit's "first move at 0.3 s" is true in play and records exclude reading time.
- An exit marker drawn over everything (door icon, fades near it) on every level, not only big houses (QW9); colour
  safe against the red player (AX3: a green exit and a red player are a red-green pair).
- Levels with 5 rooms or more: a 2 s skippable glide from the exit to the player during the held start (CA2).
- Card text in a top band, wrapped, never over the furniture (UX3); the hint repeated in the pause menu (UX1).

**R5. The obstacle in the title is on the route, and the hint is true.** (Agrees with the review's rule 2; adds hint
truth.)
- After a retune the strict schedule passes within reach of the titled mechanic (robot hum, dog cone, wardrobe,
  mezzanine, dark range), and the lesson-required check binds with no `lessonAdvisory` waiver (level 10 has one today,
  CONTRACT_M6 5).
- A hint may never contradict the data (C8: level 16 "never sleeps"; level 12 EN backwards). Add a review step: each hint
  sentence is checked against the level JSON by the levels agent and listed in its report.
- Titles promise only what exists (C9).

**R6. Every room has a job.** (Agrees with the review's rule 1, with the owner's room-variety wish as a constraint.)
- A room is on a viable route, holds a station, a robot dock, a sleeping dog or a needed hide; otherwise it is merged or
  removed. Today 12 rooms in levels 19 to 24 hold no route point, no station and no robot waypoint: 19 cuisine and sdb,
  20 bureau and sdb, 21 reunion, couloir and archives, 22 boudoir and office, 23 bureau, 24 chambre_enfants and sdb
  (my count matches the review's 12 of 44).
- Owner's wish (F6) is met by giving a room a role, not by keeping it as scenery: a marble bathroom is the noisy
  shortcut, a carpeted bedroom the quiet detour, a kitchen the place the robot docks.
- Dead rooms also cost budget: after walls 4, level 24 is at 28 / 32 materials and 143 / 160 draw calls, 21 and 22 at
  144 / 160 (FLOORS_WALLS.md 7.4 table).

### P1 (the overhaul should deliver these)

**R7. Threats readable at a glance, on screen, not only on the card.** (Adds.)
- Names: the intro card lists personality labels only (Hud.PeopleLines uses PersonalityDef.NameKey, Hud.cs:1487-1511),
  while hints 19 to 24 speak of Odile, Hugo, Dad, Mum, the butler, the countess, Rex and Lea. Show "Lea, the Suspicious
  One" on the card (IDEAS NA2, bug 14) and keep each hint to names the card shows.
- Personality readable from the model (AI3: granny's cane, the teen's phone glow), so habits are read in play.
- Show what the rules use and the player cannot see today: the robot's 2.5 m hum (no visual exists: Tuning.RobotHumRadius
  is used by Hearing.cs only) must be drawn as a floor disc if any level asks the player to travel inside it (review
  levels 9, 10, 24); a hop on a hard floor shows its 2 m reach (FX1 dust, none on rugs, which also shows the rug rule).
- Off-screen watcher arrows when a cone covers the furniture or a turn toward it is telegraphed (CA3); the "who saw you"
  replay on a catch (UX4) and the near-miss beat (QW10) teach the grace and the cones without text.
- Sentinels on a fixed beat are readable once, then repetitive: keep them to the wardrobe lesson and one house (agrees
  with the review on 18 and 19). Data hygiene: Odile (18) and Maman (19, 20) carry 320 s dwells with 34 to 58 hand-written
  glances, Bertrand and Sofia (21) 300 s with 65 and 64, Odile (23) 400 s, Rex (24) one 600 s station. A periodic glance
  field (period, hold, yaw alternation) would replace them (code, small).

**R8. Onboarding: teach each rule once, in play, and keep late hints about the threat, not the route.** (Adds.)
- Contextual first-time tips with a short pause for the creak gauge, the suspicion gauge, the memory ghost, the carry
  back and the action key (UX2). Level 1 shows both gauges with no word about them.
- Teach displacement memory explicitly in act 1. It is the core M2 twist (PRD 4.4, pillar 4: "they frown and put it
  back"), but no level has it as its lesson (LevelDef.Lessons has no memory entry) and no hint mentions it. A harmless
  first carry back in level 1 or 2 makes later "stand still out of place" decisions legible.
- Device-aware hints: six hints hard-code Shift or E (levels 4, 6, 8, 11, 13, 18; IDEAS bug 4, QW2): use `{action}` and
  `{careful}` tokens.
- Act 3 hints describe the threat or the twist, never the solution. Today 20 ("Stay switched off. Let Dad open the
  kitchen door"), 21 ("Go over the desks, not between them"), 23 ("hide halfway") and 24 ("hug the sideboards, then take
  the bridge while Lea is away") hand the route over; the review found level 20 "the answer is in the hint". Route help
  belongs to an opt-in assist (show the designer route after N failures, IDEAS MO1; routine preview in Facile, AI4).
- French register: hints 21 and 22 switch to "vous" (Passez, Laissez) while every other line uses "tu" (bug 11).

**R9. Put pillar 3 back into the levels: the player creates windows.** (Adds; not in the review.) PRD pillar 3: "the
player must always have a way to create their own window (noise, light, line of sight blockers)". Today every level is
pure timing: designer routes must have 0 alerts, 0 discoveries and no creak (PRD M2 notes), so no level can require a
lure, and the creak-as-lure (PRD 4.6, open question 6) is never used. Requirement: two or three levels in acts 2 and 3
whose intended solution is a lure: a hop on a hard floor near a watcher, then move the other way (PRD 4.5); later a
deliberate knock (GP1), a prop knocked off a table (GP2) or a household appliance that masks like the robot (GP3), with
AI2 (walk to an unexplained noise) to give it a cost. Needs audit support for a deliberate alert (code); the robot hum
and the door opened by an inhabitant are the existing data-only "windows from the household" and should carry the act 2
version.

**R10. Goal variety from the systems that exist.** (Agrees with the review's finding 3; adds the list.)
- Data only today: reach the doormat (default); be in your seat when someone sits (level 5 sit, level 14); leave every
  door as you found it (door memory, level 22); exit in a watched room so the last step is the puzzle (review, 24; today
  the exit room holds no station in 9, 12, 13, 15, 17, 18, 19, 22, 23 and 24); exit in another direction (the review
  counts east in 22 of 24; in the data the exit's x exceeds the spawn's in 23 of 24, all but 19, with 6 and 18 leaning
  north).
- Needs code: a timed return as the win (review), two exits (review), an optional collectible off the safe path (PR2),
  hop into a decoy (GP4).
- Stars per level (escape, no discovery, under par from the audit) turn one goal into three (PR1); par must use R1(b),
  not the strict exit, or the owner beats par by 3x on day one.

**R11. Change one axis per neighbour, including the body.** (Agrees with the review's rule 4.) Body, main threat, plan
shape, exit direction, look: neighbours share at most two. The stool is the body in 5 of the last 7 levels (18, 19, 22,
23, 24). New bodies with one rule each (GP5: a pouf silent everywhere and too low to see over anything, a bar cart that
rolls and rattles) refresh act 3 without new systems; the wardrobe fit rule (C3) limits which bodies can hide.

**R12. Look per act and per room comes from finishes and lighting, not from colour fields.** (Corrects the review's lever,
C2; adds F9.)
- Choose wallFinish and floorFinish per room for the house identity (manor, office, family house), check on shots.
- Night is code: a per-level lighting preset (moon key light, dark ambient, room lights on) keeping the HUD contrast and
  probe luminance checks (IDEAS ART1). Required before any level is called "night" (16 and 20 today).
- The "lit zone" the review wants in level 20 is a rules change (PRD 4.7 M4: only the lamp's own light matters; room
  light is visual), so code and audit.

### P2 (could, or after the first retune pass)

**R13. Progression that survives a reorder and a redesign.** (Answers the review's "to check before reordering".)
- Unlock rule: a level is playable when it is won, or when any level at or after the previous slot is won (or simply:
  up to the furthest won slot plus one). Small change in Core/SaveData.cs IsUnlocked plus a test (C5).
- Version the records of a redesigned level (a `rev` in the level JSON, record key id@rev, or reset its best), so old
  records from easier versions do not stand.
- Acts in the level select (LD3), "skip this level" after 5 failures with the card left unwon (QW6), the select opening on
  the first unwon level rather than level 1 (bug 20, LevelSelect.cs:65-78), a game speed assist filed apart (QW5).

**R14. Fiction and data checks for moved props and walk lines.** (Adds; from F5, F8.)
- Validator: a wall-backed kind (bookshelf, sofa, wardrobe, cabinet, counters, bed head) within 0.15 m of a wall must
  have its back to it (PropKinds.cs:10 convention).
- Until AI1: the audit or the validator flags a designed rest cell that lies on an inhabitant walk segment (people
  visibly walk through the furniture, Main.cs:69). With AI1, "a person bumps into a chair out of place" becomes a
  discovery and a new design constraint (do not park in the corridor).
- Per-level strings live in the level JSON (bug 28) once levels are added, cut and renamed; levels 19 to 24 already have
  no named members in Strings.cs.

**R15. Narrative frame for the acts.** One line per act card and an epilogue (NA4), within PRD 1.3 ("no narrative beyond a
line of text per level"); speech bubbles on a discovery or a carry back (NA1) make the comedy pillar audible.

---

## 4. Level length targets against the PRD

PRD 1.3 (2 to 6 minutes) can only mean a first clear including failures: a 6-minute clean route would break the 8 s wait
cap or be a walk. Proposed targets, all at Normal:

| Act | Strict audit exit | Relaxed exit / strict (R1b) | Waiting share | Pauses (none above 6 s) | Margin (samples) | Human first clear incl. retries (R1c) |
|---|---|---|---|---|---|---|
| 1 (learn, 7 levels) | 12 to 25 s | at least 60 % | 20 to 35 % | 2 to 4 | 15 down to 8 | 1 to 2 min |
| 2 (combine, about 9) | 25 to 50 s | at least 60 % | 25 to 40 % | 4 to 8 | 8 down to 5 | 2 to 4 min |
| 3 (houses, about 5) | 45 to 90 s | at least 65 % | 25 to 40 % | 8 to 15 | 6 down to 4 | 3 to 6 min |

Today: act 1 strict exits 10.3 to 20 s (in range or just under); the act 2 exam (17) at 20.4 s against design.md's 45+;
21 at 18.7 s and 24 at 39.9 s under the act 3 range; 19 (57.2 s), 20 (54.4 s), 22 (49.1 s) in range by length but with
the review's low waiting shares. Length must come from more decisions (pauses where a watcher is deciding), not from
more floor: the review's finding 1 ("longer routes, not harder ones") is the failure mode to avoid.

---

## 5. Per-level field notes (only where they add to the review)

- **1:** C10 (station 2 never met; open question 10 A/B).
- **5, 7, 18:** design.md levers exist (C11); settle "change nothing" against them with one audit each.
- **6:** agree (same lever as design.md: station 0 (4, -0.25) to (2, -0.25)).
- **8, 11, 17:** agree; the review's levers are design.md's.
- **9, 12:** apply both levers (C11). Level 12's hint EN must be fixed (C8).
- **10 / 15 (rocker):** C4: the swings must be seen by the dog or sit beside rocker decoys; the m6 dog trial is the
  starting point.
- **13:** the review's template level was cleared by the owner in 8.4 s against a 26.2 s audit (now 25.4 s). Before
  copying its recipe, give it R2's counter-routes (vase drop then full speed is the first suspect; no such step exists
  for 13).
- **14:** fine as an armchair level; the same 0.6 m platform with two ramps is in 14, 17, 19, 21, 23 and 24 (1 m wide in
  all but 19 and 21): it should be the crossing in at most two of them, and vary in shape where it stays.
- **16:** if kept, its hint is false (C8) and it needs the night preset (F9, R12). If cut (review), level 20 becomes the
  second dark level after level 6, a jump from 52 m² to 199 m².
- **19:** 55 of 63 route points on carpet (C7): give the gallery a hard floor so hearing returns; cuisine (43.6 m²) and
  sdb (21.6 m²) are empty.
- **20:** C6 (17 toggles), the hint gives the route (R8), Maman's 320 s dwell with 58 glances (R7), night is code (R12).
- **21:** F2 confirmed. IDEAS LD5 ("wide empty floors with little cover") and the review ("seven tall cabinets hide the
  catwalk") both hold: the open space (88 m²) has 8 props, and 7 bookshelves of 1.2 to 1.9 m line the catwalk.
- **22:** "the butler" and "the countess" are not named on the card (R7); hint in "vous" (R8).
- **23:** C9.
- **24:** F7. In V4 (commit cc733ea87) the west-middle room was one soft "bureau" with a desk and the wardrobe
  "ArmoireBureau" (1.75, 4.05); V5 split it into chambre_enfants (soft, z 3.5 to 6.9) and sdb (hard marble, z 7.0 to 9.9,
  doors only to the kids' room). Nobody enters either; the wardrobe kept its old name and is a hide nobody needs. Answer
  to the owner: right as a picture, wrong as a level: either make the pair a real alternative (a door from sdb to the
  couloir or the galerie, the marble as the noisy shortcut, the carpet as the quiet way, a station or the robot there), or
  remove both. Rex is one 600 s awake station (a statue), the exit room (entree, soft) holds no station, and C3 applies to
  the proposed chair finale.

---

## 6. Agree / add / conflict with the review (summary)

| Topic | Review | This report |
|---|---|---|
| Curve and length | Longer routes not harder; PRD 2 to 6 min vs 10 to 57 s | Agree; add C1 (audit is not a floor), R1 three measures, R2 rush counter-routes, section 4 targets |
| Dead rooms | No dead room | Agree (12 rooms, same count); nuance: give rooms a job to honour the owner's room variety (R6) |
| Titled obstacle on route | Yes | Agree; add hint truth and title truth (R5, C8, C9) |
| Waiting | 25 to 40 %, 3+ pauses, none above 6 s | Agree; count in-place actions (C6); hide counts as waiting |
| Variety | One axis per neighbour; bodies, threats, shapes | Agree; add new bodies (GP5), soft floors silencing hearing (C7) |
| Look | Room colours are data | Conflict: colours are not rendered (C2); finishes are the lever; night is code (F9) |
| Cuts | 10, 16, 23 | Agree on 23 (also C9); 10 only if the rocker lesson moves with C4's conditions; 16 if night lands in 20 |
| Finale | Chair, every verb once, exit in a watched room | Agree on watched exit and dog patrol; conflict: chair cannot hide (C3) |
| Reorder | Records survive; unlock not verified | Unlock follows the list and can lock won levels; records survive redesigns wrongly (C5, R13) |
| Onboarding, readability, exit, timer | Not covered | R4, R7, R8 (start on input, exit marker, names, hum disc, tips, hints) |
| Pillar 3 (lures) | Not covered | R9: no level can require a lure today; needs audit support |
| Goal variety | One goal, propose timed return and two exits (code) | Agree; add data-only goals and stars with a relaxed par (R10) |

---

## 7. Needs code (consolidated, smallest first)

1. Start on first input (QW4) and exit marker over walls (QW9): Hud, GameState.
2. Unlock rule and record versioning (R13): Core/SaveData.cs, tests.
3. Rush counter-route probe step over every level (R2): Tests/PlayMode, RouteReplayer.
4. Names on the intro card (NA2): Hud.PeopleLines.
5. Device-aware hint tokens (QW2): Strings, Hud.
6. Robot hum disc and hop noise reach (R7): a floor decal, Tuning radii.
7. Periodic glance field for sentinels (R7): Core/LevelDef, InhabitantRoutine, validator, audit.
8. Validator rule for wall-backed props, audit flag for rest cells on walk lines (R14).
9. Relaxed audit mode or human-reaction bot (R1b, LD2), local run log (R1c, AN1).
10. Night lighting preset (R12, ART1); lit zone rule (review, level 20).
11. Deliberate alert in the audit for lure levels (R9); GP1, GP2, GP3, AI2 as later verbs.
12. Opening glide (CA2), off-screen indicators (CA3), who-saw-you replay (UX4), first-time tips (UX2).
13. Goal types: timed return, two exits (review), collectibles (PR2), stars (PR1).

---

## 8. Open questions for the product owner

1. Is "2 to 6 minutes" (PRD 1.3) the first clear including retries? If yes, section 4's targets hold; if it means a
   clean run, the 8 s wait cap and the creak must change first.
2. Should a skilled player be allowed to beat the strict audit by spending discoveries (a "dirty run" style), or must
   every level resist it (R2)? It decides whether suspicion is a budget or a fail-safe.
3. Level 1 start station A/B (PRD open question 10), now that level 1 is the demo's first minute.
4. May the finale's body be the stool or lamp again (C3), or should the wardrobe fit the chair?
5. Night levels: worth the lighting code (R12), or cut 16 and drop "night" from 20's identity?
6. Lure levels (R9): accept the audit work so pillar 3 shows up in the levels, or keep the game pure timing?
