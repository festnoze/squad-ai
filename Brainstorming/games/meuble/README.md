# Out of Sight: Don't Get Caught Moving

A 3D stealth comedy in Unity 6.3 (URP): you are a chair, and you may only move while nobody is
looking. The contract is [docs/PRD.md](docs/PRD.md). Code, comments and docs are in English. The
strings shown to the player are in French.

## Play

- **Play:** launch `Build/Play/OutOfSight.exe`. Command-line options: `-mute`, and Unity's
  `-screen-fullscreen 0 -screen-width 1600 -screen-height 900` for a window.
- **Build it** (PowerShell, waits its turn on the Unity lock; the Unity Editor must not have the project open):
  `pwsh -NoProfile -File tools/unity.ps1 -Agent me -UnityArgs "run . --timeout 3000 -- -executeMethod OutOfSight.Editor.Builder.BuildWindows -output Build/Play/OutOfSight.exe -logFile Build/pc.log"`.
  Android: the same with `OutOfSight.Editor.Builder.BuildAndroid` (output `Build/Android/OutOfSight.apk`).
- In game, **Ctrl+F** or **F11** toggles full screen (Alt+Enter works too).
- The probe's build: `Build/Windows/OutOfSight.exe` (produced by `./verify.sh player`).
- Debugging in Visual Studio 2022: install the "Game development with Unity" workload (Visual Studio Installer;
  the project's `.vsconfig` lists it), set Unity's Preferences > External Tools > External Script Editor to
  Visual Studio 2022, open `OutOfSight.sln`, then Debug > Attach Unity Debugger: the Editor in Play mode (switch the
  Editor to Debug mode with the bug icon in its status bar) or a Development Build of the player.
- In the editor: open the project with Unity 6000.3.23f1, open `Assets/Scenes/Boot.unity`, press Play.
- Controls: ZQSD or the arrow keys move (camera relative, keys read by physical position), the
  mouse orbits the camera (click to capture the cursor), the wheel zooms, R restarts, Escape
  pauses (title, pause and end screens since M3). Since M4: Left Shift moves carefully (half
  speed), E switches the floor lamp. Gamepad: the left stick or the D-pad moves, the right stick
  orbits, the left trigger is careful mode, X is the action, Start pauses, Y restarts, B goes back
  (closes the level select). A gamepad alone plays the whole game, menus included.

## Verify

| Command | What it checks |
|---|---|
| `./verify.sh` | runs every stage below and stops on the first red one |
| `./verify.sh compile` | project setup (layers, Always Included Shaders, Boot scene) and the scripts compile |
| `./verify.sh edit` | EditMode unit tests of `OutOfSight.Core` (PRD 10.1) |
| `./verify.sh play` | PlayMode probe on the real Boot scene, steps 01 to 35 (PRD 10.2 and every milestone since) |
| `./verify.sh audit` | level audit: walks free of props, an unseen schedule from spawn to exit, lesson checks and self-test fixtures (PRD 10.3) |
| `./verify.sh player` | builds the Windows player, runs it with `--probe --shot`, and reads its report (PRD 10.4) |
| `./mutation.sh` | the mutation check of PRD 10.2 |

The harness refuses three kinds of false green: a JUnit report with zero tests, an ignored test,
and an expected probe step missing from the report. All waits in the probe are counted in fixed
steps or in game time, never in rendered frames. The built player writes
`TestResults/shots/report.json` and three screenshots. These screenshots are meant to be looked at.

### M5 wave 5A gate (2026-11-13)

The product owner rewrote M5 after the M4 playtest (PRD v1.7):
- 10 new levels that combine mechanics;
- larger maze-like houses;
- several inhabitants with personalities;
- the robot vacuum, the rocking chair and a balanced load.

M5 is built in two waves. Wave 5A ships doors, the dog, the mezzanine, personalities and patterns,
the save, the level select and the records, and levels 8, 12, 14 and 16 (an 11-level play order).

| Stage | Result |
|---|---|
| EditMode | 370 tests, 0 failures |
| PlayMode probe | 169 tests, 0 failures. M5 steps: 36 (doors: leaf poses, E rules, a leaf seen swinging is caught, walks frozen, investigations through an opened door, an open leaf faded), 37 (personalities in the rules and on screen, patterns in play), 38 (the dog: low eye, bark, cooldown, sleeping sees nothing), 39 (split level: floor heights, ramp, railings, visuals on the slope), 40 (full playthrough of the manifest at x8 with the save), 41 (save and level select), 45 (designer routes of levels 8 to 16 at three offsets, counter-routes) |
| Level audit | 11 levels with no defect, 13 self-test fixtures, 2 to 15 s per level after a 20x speed-up |
| Built player | 98 MB, 0 exceptions, frame time 3.6 to 6.9 ms median per level on the development PC, the probe save in the shot folder, the real save untouched |
| Mutations | 58, all killed, run on a mirror of the project while wave 5B was being built |

**How it was built:**
- **Workflows.** Wave 5A ran as a workflow of eight builders: core, ui-save, bodies, audit, house,
  watchers, game and levels.
- **Critique.** An adversarial critique followed, with six critics and a refuter per dimension. It
  confirmed 1 blocker (level 14's armchair hidden at the start) and 5 majors: no frame-time
  measurement, budgets counted on renderers, a sleeping dog's sight untested, dead time on level 14,
  and a level 12 dog that nobody heard.
- **Fixes.** The 5A.1 fix wave (CONTRACT_M5 section 17) fixed them.

**For the product owner's playtest (5A):**
- the doors (E, only unseen);
- the dog's bark and its cyan cone;
- the people on the intro card;
- Mamie sitting on the armchair at the mezzanine;
- the night level with the dog.

### M4 gate (2026-11-13)

| Stage | Result |
|---|---|
| EditMode | 246 tests, 0 failures (bodies, the chair row equal to M1 field by field, sitting, the sit slide on every shipped level, the pratfall, level data) |
| PlayMode probe | 97 tests, 0 failures. M4 steps: 28 (stool: tip, tell band, careful, head-on wall hit, lying, rugs), 29 (bodies: office chair glide and stop ring, careful mode, input latch, short taps, wall graze, dark lamp range, toggle in sight), 30 (lamp: dark range, click, switch-on, HUD hints, toggle caught, out-of-place lamp), 31 to 33 (sitting on a prop and on the player, the pin, the pratfall and its tolerance), 35 (designer routes of levels 4 to 7 at -0.2, 0 and +0.2 s; level 5 rush is caught) |
| Level audit | 7 levels, no defect; lesson checks for levels 4 to 7; 6 self-test fixtures; budgets 85 / 72 / 87 / 65 renderers and 21 / 23 / 23 / 16 materials for levels 4 to 7 |
| Built player | 87 MB, 14 shots (levels 1 to 7 plus states), 0 exceptions |
| Mutations | 19, all killed: the 8 of M1 to M3, plus the stool tip, the glide, the dark lamp range, the gauge paused while sat on, the chair row (M1 step 02 turns red), sat on counts as moving, the sit check at 1 m, the silent topple, the toggle at the lit range, the tell speed, and the audit's sit moment (level 5's lesson turns red) |

M4 was built by four agents (core, bodies, game, levels) against
[docs/CONTRACT_M4.md](docs/CONTRACT_M4.md):
- the contract went through two critiques (v2, then the v3 amendments of its section 9);
- a result critique of the green build found 2 blockers:
  - level 5 could be won without ever being sat on, because the audit forced presence from the
    approach and the game checked at the moment of sitting;
  - sitting on a prop moved the inhabitant's eye 1 m in one step, without a telegraph.
- The M4.1 wave (CONTRACT_M4 section 10) fixed them, along with:
  - the stool's missing warning (a 1.0 to 1.3 m/s tell band) and its tipping on wall grazes;
  - a lamp toggle in sight that was never caught;
  - noises on rugs;
  - fixtures that were copies of levels.
- The harness gained these checks:
  - `mutation.sh` refuses a tree that still holds a mutation, snapshots the sources, checks its
    rows, and runs only the tests a mutation must turn red;
  - mutations can be killed by the audit;
  - `verify.sh` requires the EditMode tests the gate relies on.

**For the product owner's playtest (M4):**
- the stool: is the 0.25 s tell (lean and rattle) enough warning, and is careful mode (Shift)
  the right brake?
- level 5: being sat on is the lesson; the seat home is shown by an amber ghost from the start
  of the sitter's walk;
- level 6: does the darkness read on screen (the room light dims, the cone shrinks to 4 m)?
- open questions 11 to 15 in the PRD (careful mode, the wardrobe dropped, the lamp switched back
  on, the chair pulled away during the back turn, a tipped stool out of place anywhere).

### M3 gate (2026-11-12)

| Stage | Result |
|---|---|
| EditMode | 168 tests, 0 failures (model math, licences, and every earlier suite) |
| PlayMode probe | 58 tests, 0 failures. M3 steps: 22 (models, facing, nothing hides the chair), 23 (colliders identical with and without models), 24 (rig: clips, head follows the eye within 5 deg, eye height, footsteps, carry, brows, pause), 25 (budgets with models, and level 3 with the woman), 26 (title, pause, x-ray gaze render test, HUD, end screen), 27 (audio roles, effective volumes, hop variants, footsteps, room tone, UI click) |
| Level audit | unchanged from M2; budgets with models: 63 / 84 / 79 renderers, 21 / 21 / 22 materials (max 24), 3 143 / 3 073 / 4 949 triangles |
| Built player | 87 MB; every model present (0 fallbacks), rig with Idle/Walk/Jump on every inhabitant, 21 of 21 audio roles, 0 look problems, 0 exceptions |
| Mutations | 8: cone, caught reset, discovery grace, suspicion decay, model facing, head driven by the eye, pause, hop variants |

M3 was built by four agents (models, rig, look, audio) against [docs/CONTRACT_M3.md](docs/CONTRACT_M3.md)
(v2 after a contract critique), then a result critique found two pillar-breaking visual defects
(the near wall cap across the frame, no readable gaze behind walls) and gate holes; the M3.1 wave
fixed them (wall caps fade, x-ray silhouette plus a deep blue cone plus a gaze arrowhead, HUD in
a bottom band, rig failures and audio roles checked by the built player, mutations added).

Assets: Kenney Furniture Kit and Quaternius humans (CC0, poly.pizza) and 21 CC0 recordings
(OpenGameArt), listed with their sources in [docs/LICENSES.md](docs/LICENSES.md) (checked by a
test). The tall bookshelf, tables and doors stay procedural (see CONTRACT_M3 section 2).

**For the product owner's playtest (M3):**
- a listening pass: hops, scrapes, creak, footsteps, room tone, the two stings, "hein ?"
  (synthesized; the recording can be switched on in `Sfx.UseRecordedHein`), UI click;
- the x-ray cone through low props (sofa, desk, bed, sideboard) is strong blue: truthful (the
  chair top behind them would be seen) but heavy;
- the title screen orbits a paused level, and the man stands frozen mid-pose.

### M2 gate (2026-11-11)

| Stage | Result |
|---|---|
| EditMode | 157 tests, 0 failures |
| PlayMode probe | 30 tests, 0 failures. M1 steps 01 to 12 run with the M1 rules; M2 steps 13 to 21 and 13b to 21b with the M2 rules (including a two-inhabitant test level) |
| Level audit (M2-aware since M2.1, hardened in M2.2) | levels 1 to 3: no defect; clean schedule exits at 10.7 / 13.3 / 18.6 s with a longest wait of 2.7 / 4.9 / 6.3 s (max 8 s, measured within 1 m of where the wait started); level 3 has no schedule with its decoys switched off (decoys required); self-test: three fixtures (wait, noise, creak) each fail for their own rule |
| Start delay sweep (warning, for the playtest) | a player who starts acting at time d still has a schedule with waits of at most 8 s, except for d = 29-30 s on level 1 (2 of 39 delays), 26-27 s on level 2 (2 of 31), 7-12 s on level 3 (6 of 43) |
| Designer routes | levels 1 to 3 won by replay at -0.2, 0 and +0.2 s with 0 discoveries, 0 alerts, no creak |
| Built player | 83 MB, 10 screenshots (start, caught, won, level 2, level 3, alert, investigate, creak warning, suspicion with ghost, alarm eye), 0 exceptions, every level within the 7.4 budgets (level 3: 108 renderers of 120) |
| Mutations | `./mutation.sh`: cone, caught reset, discovery grace, suspicion decay mode, each caught by its tests |

M2 was built by four agents in parallel against [docs/CONTRACT_M2.md](docs/CONTRACT_M2.md):
core-rules, core-routine, runtime-world and runtime-game. A critic agent reviewed the contract
before the build and the result after it. The result critique found that a playtest would
measure the wrong game:
- glimpse discoveries;
- 15 to 19 s waits at spawn;
- a decoy rule that did not match its hint.

The M2.1 fix wave (contract section 11) addressed all three, and a second critic pass checked
the fixes. Unity runs are serialized by `tools/unity.sh`, a lock,
because a project can be open in only one editor.

### M1 gate (2026-11-11)

| Stage | Result |
|---|---|
| EditMode | 34 tests, 0 failures |
| PlayMode probe | 12 steps, 0 failures |
| Level audit | level 1: no defect, routine loop 38.7 s, safe path of 23 cells |
| Built player | 83 MB, Lit and Unlit shaders resolved, 72 renderers, 1 449 triangles, 19 materials, 1 shadowed light, 0 exceptions, Caught and Won reached |

### Mutation check (PRD 10.2)

`./mutation.sh` applies each mutation to a marked line, runs the suite, and restores the file.

| Mutation | Expected | Observed |
|---|---|---|
| Invert the cone test (`VisionMath.IsInCone`) | probe steps 03 to 06 turn red | 03, 04, 05 and 06 red (02, 08, 09 too) |
| Remove the grace timer reset (`CaughtRule.Step`) | the CaughtRule reset unit test turns red | `Seen_and_moving_018_then_hidden_is_not_caught_and_resets` red |

## Architecture

| Assembly | Content |
|---|---|
| `OutOfSight.Core` | pure logic: `Tuning` (every constant), `Strings`, `VisionMath`, `MotionRule`, `CaughtRule`, `InhabitantRoutine`, `LevelDef` + `LevelJson`, `LevelValidator` |
| `OutOfSight.Runtime` | `Main` (the only component of `Boot.unity`), `GameState` (one FixedUpdate drives every rule in a fixed order), `LevelBuilder`, `FurnitureKit`, `PrimitiveKit`, `FurnitureController`, `Inhabitant`, `Vision`, `VisionConeView`, `OrbitCamera`, `Hud`, `ProceduralArt`, `Sfx`, `Probe` |
| `OutOfSight.Editor` | `ProjectSetup`, `Builder`, `LevelAudit` |
| `OutOfSight.Tests.EditMode` / `.PlayMode` | unit tests of Core, and the probe |

Levels are data in `Assets/Resources/Levels/*.json`, played in the order of `levels.json`. Meshes, materials, HUD sprites and part of
the sounds are generated in C#. Since M3 the project also ships CC0 models (Kenney, Quaternius) and recordings, and since M4.2 six CC0
detail textures (ambientCG, derived to grayscale by `tools/assets/derive_textures.py`); every one is listed in `docs/LICENSES.md`.

## Deviations from the PRD, and why

Each one is written back into the PRD (v1.2) as an M1 note or an open question.

1. **Level 1 sofa and table moved** (sofa (0.0, 0.3) to (-0.75, -0.05), table (2.2, -1.6) to
   (2.45, -1.9)). The level audit found that three of the four authored straight walks cross a
   prop: 2 to 3 and 4 to 1 cross the sofa, and 3 to 4 cuts a table corner. The stations were
   kept. The audit was first run on the original data to prove that it catches this.
2. **Dwell extension.** When a station's glances need more time than its dwell, the dwell is
   extended. A glance is never cut short.
3. **Telegraph threshold.** Only turns above 30 deg are telegraphed (PRD 4.3). This includes the
   telegraphs of steps 2 and 4 of the station cycle.
4. **A still furniture is never displaced.** The probe bot found a real bug: an inhabitant walking
   through a still chair shoved it, the shove counted as motion, and the player was caught for
   being bumped. Two changes fix it. A still chair no longer calls `CharacterController.Move`.
   The Player and Inhabitant layers no longer collide. Probe step 12 guards against the bug
   coming back. It was confirmed red with the fix reverted.
5. **Floor vision cone.** The 40 rays aim from the eye at the chair top height (0.87 m), so the
   fan shows exactly where the top of the chair is seen.

## What the bots found (data for the product owner)

- **Disciplined bot** (step 10). It stops on the step after the eye opens and wins in **15.1 s**.
- **Bot with a human reaction time** (step 11). It reacts in 0.24 s, which is more than the
  0.2 s grace, and reads only the telegraph and the floor cone. It wins in **17.5 s**. At its
  worst it was seen moving for **0.18 s**, close to the 0.20 s grace.
- **Low props are no cover.** The sofa and the table are lower than the chair top, so they never
  hide it. Only the bookshelf and the walls are cover.
- **Conclusion.** Level 1 is easier and shorter than the 60 to 120 s first run that PRD 6.3 aims
  for, and the margin against a human reaction time is thin. This is PRD open question 8. M2
  displacement memory is the planned answer.

## Known M1 limitations

- The inhabitant walks through a still chair (reacting to a furniture in the way is M2).
- No menu, no save, no second level (out of scope for M1).

## M6 and M6b gate (2026-11-16)

`./verify.sh` green: 448 EditMode, 214 PlayMode, 18 levels audited without defect, built player 101 MB.
Level 10's rock lesson is advisory (docs/CONTRACT_M6.md 5). The agents' reports are in docs/m6/ (run logs
removed 2026-11-20; `./verify.sh` regenerates them). The full `./mutation.sh` run
(with the 21 M6 rows) was skipped to save credits.
