# ACT3A progress (2026-11-24): act 3 reorder, level25 rush, level22 waiting cell

Task: part of finding 1 of docs/next/LEVEL_REVIEW.md ("Act 3 falls apart after card 17"). ACT3B reworks the finale
(level24.json) in parallel; level24.json is not touched here and stays the last card.

## 1. New act 3 order (Assets/Resources/Levels/levels.json, rev 3)

| Card | File | Title | Before (rev 2) |
|---|---|---|---|
| 17 | level25 | The Showroom (act 3 opener, act tag) | card 21 |
| 18 | level19 | Hide and Seek, Family Size | card 17 |
| 19 | level22 | Skeletons in the Closet | card 20 |
| 20 | level24 | The Great Escape (finale, ACT3B) | card 22 |

- Parked (out of the line-up, files kept and still valid): level21 (The Catwalk, was card 18) and level20 (Midnight
  Munchies, was card 19). Their names, hints and PlayMode replays (Step58a3/a4, Step58b1/b2) stay: tests load them by id.
- 20 levels, 60 stars (was 22 / 66). Acts: from 0, 7, 16 (unchanged indices; act 3 now has 4 cards).
- Cards 1 to 16 keep their numbers and order.

## 2. Save migration (how the code does it, and what was done)
- `SaveData.IsUnlocked`: a card is playable when it is index 0, or won, or its predecessor in the current order is won,
  or its id is in the save's `unlocked` list.
- `SaveStore.Load` runs `SaveData.MigrateOrder(manifest.rev, manifest.previous, manifest.levels)` once when the save's
  `order` is below the manifest `rev`: every id of `previous` that was playable under the previous order (index 0 or its
  predecessor in `previous` won) and is still listed joins `unlocked`; then `order` = rev and the save is written.
  Won, best times and stars are never touched. Records and stars are keyed by the level's own record revision
  (`id~rev` per level file), not by the manifest rev, so the reorder changes no record or star key.
- Done: `rev` 2 -> 3, `previous` = the rev 2 order (22 ids). That is the single-hop mechanism the code expects.
- Effect on a rev 2 save: a player who has won the first 16 cards keeps level19 (their next card in rev 2) open through
  `unlocked`, and level25 opens after level17 as the new card 17. A player deep in act 3 loses nothing (level22 opens
  after level19 as before; level20 / level21 are not listed so they never join `unlocked`).
- Fresh saves start at order 3 and never migrate.
- Limit (single hop): a v1 save (order 1, never booted on a rev 2 build) now migrates against the rev 2 order, not the
  v1 order. It keeps every win, time and star, but can lose a v1-only unlock (example: v1 wins level1-level10 used to
  open level11 through `unlocked`; now level12 opens instead and level11 waits for level12). See A VERIFIER.

## 3. level22 (card 19, Skeletons in the Closet): the waiting cell on the Comtesse's line

Run 1 (Build/act3a_r1.log, -slack, no -writeRoutes), Normal:

| variant | change | walk-line warning | other |
|---|---|---|---|
| shipped | - | Comtesse 0.29 m from (14.75, 10.75) at 24.3 s | 0 defects, exit 50.1 s, slack 5 |
| k1 | Comtesse s0 z 10.95 -> 10.4 | 0.43 m | 0 defects, slack 5 |
| k2 | ArmoireGalerie2 x 15 -> 15.5 | 0.54 m | 1 DEFECT (view fidelity at the hide entry, 20.4 s) |
| k3 | k1 + k2 (both review options) | 0.60 m (still warns: the rule is "at least 0.6") | same view-fidelity DEFECT |
| k4 | k1 + wardrobe x 16.0 | 0.44 m | view-fidelity DEFECT |
| k5 | Comtesse s1 dwell 5 -> 4 | 0.29 m | 0 defects |
| k6 | Comtesse s0 dwell 3 -> 4 | 0.29 m | 0 defects |

Why neither review option works: the gallery is 1.9 m deep (z 10.0-11.9), the wardrobe's hide cells sit at z 10.75 and
the Comtesse's NavMesh line from the library door corner (about (17.05, 10.3)) to s0 runs at z 10.3-10.5 under the
wardrobe. No station or 0.5 m shift puts 0.6 m between them, and timing changes only move the moment: the solver always
leaves the wardrobe right behind her back. The fix has to move the hide cell itself out of the walking strip.

## 4. level25 (card 17, The Showroom): rush (a)

Diagnosis:
- Every route ends through the south aisle "gate": the decoy slot (4.75, 0.75) in front of Nina, then about 2.3 m to
  the doormat. Nina loops N0 (4.75, 3.25) facing 170 (the aisle) dwell 2.4 and N1 (4.75, 4.0) facing 0 (away) dwell 1.6.
- From N0 she sees the aisle west of x about 7.25 (the shelf Rayon1S hides the rest). Rush (a) (route without waits)
  must cross about 4.8 m of that aisle in one of her away windows; the designer route only the 2.3 m from the slot.
  The shipped away window (turn, walk, 1.6 s at N1, turn back) was long enough for both: rush (a) won at 15.5 s.
- The review's glance "on N1 toward the south aisle" is not possible as written: N1 faces 0 and the aisle is behind
  her (bearing 180-212), beyond the 80 degree head limit plus her 50 degree half angle. Tried as N1 facing 270 with a
  -80 glance held 1.0 s (offsets 0.6 and 0.3): no schedule at all (variants d and e, 4 defects each). The smallest
  equivalent that works is a shorter away window: Nina's N1 dwell.

Run 1 (Normal, -slack): shipped slack 11, exit 29.9 s, 5 pauses. N1 dwell 1.0 (c): slack 8, exit 28.8 s, but 4 pauses
(the 1.3 s stop at (13.75, 0.75) vanished): 1 pace defect. N1 dwell 0.8 (b): two slot waits, loiter 11.3 s (defect).
N1 dwell 0.6 (a): 76.9 s, loiter 21 s. Difficile baseline: 0 defects, exit 30.9 s, slack 10, longest pause 6.0 s.

Window model (InhabitantRoutine: a turn over 30 degrees is telegraphed 0.6 s, body 180 deg/s; Nina hurried 1.7 m/s):
the aisle is out of her cone from about 0.2 s into the N0 -> N1 turn until about 0.7 s into the N1 -> N0 turn, so the
away window is about 2.5 s + N1 dwell: 4.1 s shipped (rush (a) needs about 4.0 s for its 4.8 m at 1.25 m/s plus a turn,
and won), 3.5 s at N1 dwell 1.0. The slot dash needs about 2.1 s, which matches the measured slack (11 -> 8).

Run 2 (Build/act3a_r2.log, Normal, -slack; N0 dwell w0 / N1 dwell w1):

| variant | w0 / w1 | result | slack | exit | pauses |
|---|---|---|---|---|---|
| shipped | 2.4 / 1.6 | 0 defects | 11 | 29.9 s | 5 (4 mid) |
| f | 2.6 / 1.0 | 1 defect (4 pauses) | 8 | 28.9 s | 4 |
| **g** | **2.8 / 1.0** | **0 defects** | **8** | **29.7 s** | **5 (4 mid)** |
| h | 2.4 / 1.2 | 1 defect (4 pauses) | 9 | 28.8 s | 4 |
| i | 2.6 / 1.2 | 0 defects | 9 | 29.5 s | 5 |
| j | 2.4 / 0.9 | 2 defects (loiter 10.7 s, share 46 %) | 7 | 35.3 s | 5 |
| l | 2.6 / 0.9 | 1 defect (4 pauses) | 7 | 28.8 s | 4 |

Chosen: **g** (Nina N0 dwell 2.4 -> 2.8, N1 dwell 1.6 -> 1.0): the shortest away window that keeps every rule (about
3.5 s against about 4.1 s shipped), the same cycle length (about 7.1 s), 0.6 s more of Nina watching the aisle per
cycle. Boulevard via: now a warning (x1.53, best 29.7 s), it was x1.30; the via stays a note, not a defect.

Written (run 3, Build/act3a_r3.log, -slack -writeRoutes, level25.json):

| level25 | Normal before | Normal after | Difficile before | Difficile after |
|---|---|---|---|---|
| defects | 0 | 0 | 0 | 0 |
| exit | 29.9 s | 29.7 s | 30.9 s | 30.7 s |
| slack | 11 (1.1 s) | 8 (0.8 s) | 10 (1.0 s) | 7 (0.7 s) |
| waiting share | 38 % | 38 % | 40 % | 40 % |
| pauses (mid) | 5 (4) | 5 (4) | 5 (4) | 5 (4) |
| longest pause | 4.7 s | 5.1 s | 6.0 s | 5.8 s |
| decoys | required | required | required | required |

- Routes: designerRoute and designerRouteHard rewritten (27 points each, same cells as before; only the waits moved).
- The two micro-stops (0.6 s at (16.75, 3.75), 0.7 s at (16.25, 3.75) at Normal) are still there: they are freezes
  while Marcel walks past the reserve door, not Nina's. Left as they are (optional item, not attempted).
- Rush (a) keeps the same waypoints, so it reaches the aisle at the same time as before; with the shorter away window
  the model says Nina turns back to the aisle about 0.9 s before it reaches the doormat. Checked by Rush04 (section 6).

Level22, more variants (run 2): the wardrobe turned sideways against the north wall (yaw 270 or 90 at (15, 11.3)) puts
the hide cell at (14.25, 11.25) / (15.75, 11.25), off her line, but it blocks the gallery for the stool: both variants
fall back to a 169 s route through the salon (loiter 57 s, view-fidelity defect). Rejected.

Runs 3 and 4 (Build/act3a_r3.log, act3a_r4.log), the wardrobe kept against the wall:

| variant | wardrobe x / Comtesse s0 z / s0 dwell / s1 dwell | walk-line | result |
|---|---|---|---|
| m1 | 15.5 / 10.3 / 3.0 / 5.0 | none (cleared) | view-fidelity DEFECT at the hide entry (20.4 s) |
| m2 | 15.25 / 10.3 / 3.0 / 5.0 | none (cleared) | same DEFECT |
| m3 | 15.5 / 10.4 / 3.3 / 5.0 | 0.60 m | same DEFECT |
| m4 | 15.5 / 10.3 / 3.3 / 5.0 | none | same DEFECT |
| candidate | 15.25 / 10.3 / 3.0 / 6.0 | none | same DEFECT (21.4 s) |
| n3, n5, n6, n7 | 15.25-15.5 / 10.3 / 3.0 / 5.5-6.5 | none or 0.45 m | same DEFECT |

Why: a hide cell at x 15.25 or east is on the Comtesse's view as she comes back out of the library door, and the
solver always arrives there just before her (whatever her dwell, it follows her timing). The audit's fine view check
then sees the last 0.1 m of the entry move. At x 14.75 (shipped) the entry is out of her cone, but the cell is on her
line.

**Decision: level22.json is left exactly as shipped** (git checkout after the runs; routes untouched; 0 DEFECTS at both
difficulties, re-measured in run 1). The 0.29 m walk-line warning stays (a visual issue: she walks through the stool for
about 0.3 s right after the player leaves the wardrobe; the audit has never made it a defect). A real fix needs the
hide moved out of the gallery strip, which is the "v2 path with a second hide" of the review (L effort), or a
wardrobe-entry rule change. See A VERIFIER.

level22 numbers (run 1, shipped file, -slack): Normal 0 defects, exit 50.1 s, 31 %, 4 pauses (3 mid), longest 5.8 s,
slack 5 (0.5 s); Difficile 0 defects, exit 68.6 s, 40 %, 6 pauses (5 mid), longest 7.0 s, slack 5 (0.5 s), Alfred
0.46 m walk-line warning at (20.75, 7.25). Both slack values are new (the review listed card 20 slack "not measured").

## 5. What else changed for the new count and order
- levels.json: rev 3, previous = rev 2 order, levels = 20 ids, acts unchanged (0, 7, 16).
- Tuning.cs (StarsPerLevel comment: 20 levels, 60 stars), LevelSelect.cs (DisplayNumber comment: level19 is 18).
- Tests:
  - LevelDataM2Tests: PlayOrder (20), Rev2Order, ParkedLevels (level21, level20: unlisted, on disk, valid), manifest test
    renamed `Manifest_is_the_rev3_order_with_its_acts_and_the_rev2_order_as_previous` (rev 3, previous = rev 2).
  - SaveM5Tests: the v1 -> v2 worked cases now run on a built rev 2 manifest through `SaveStore.ManifestOverride` (re-set
    after each ResetForTests), unchanged in substance; `Manifest_v2_acts_and_lists_are_consistent` reads the shipped
    manifest; new `Migration_rev3_a_rev2_save_keeps_its_next_level_open_after_the_act3_reorder`.
  - StarsTests: `LineUp_EveryLevelHasAReferenceAtBothDifficulties_And60Stars` (was And66Stars).
  - ProbeTestsM5Levels: V2LevelCount 20; Step40 premise also rejects the parked level21 / level20.
  - ProbeTestsLevelNum: level19 is card 18, level25 card 17, level20 has no number; LevelNum01 shoots level1 and level22
    (was level20, now unlisted). Shots land in Build/shots/levelnum/level22_*.
  - ProbeTestsM5Ui Step41h: a rev 2 save (16 cards won) migrated to rev 3 opens level25 and level19, default card level25.
  - ProbeTestsRush: new `Rush04_Level25RushesLose` (level25 alone, not Slow). Rush02 follows levels.json by itself.
  - Comments: ProbeTestsM42Look (20 levels), ProbeTestsL17HideLook (level19 is the 18th card).
- mutation.sh: no row depends on the level count, the order or the renamed tests (checked); nothing to change. Note:
  the LEVELS_V2 migration tags (UNLOCK_WON, UNLOCK_MIGRATED, MIGRATE_PREDECESSOR) still have no mutation.sh row.
- Strings / Credits / achievements: no level count anywhere in the UI text (the level select builds one card per
  levels.json entry; the stars total is computed). No achievements exist. Nothing to change.
- level25 hint already reads "Marcel zigzags through the shop, Nina sweeps by the door, and the lights stay on."

## 6. Night levels: what is lost
- level20 (Midnight Munchies) was the only level where darkness carried a rule (the floor lamp switched off at night,
  dark ranges of three watchers, a door only Papa opens). With it parked, the lamp body appears only in card 6, and
  "night" survives only as level25's look (lighting night, visual only: no rule reads it).
- The level25 hint "the lights stay on" still makes sense, slightly less urgently: no night level precedes it any more,
  but card 6 teaches "switched off, you are only seen up close", and the Showroom is a dark-looking shop. The line keeps
  players from assuming the dark hides them. Keep it.
- Night tests (ProbeTestsNight, NightLook, M8Lights, Ceiling) load level20 by id and still work on the parked file.

## 7. Unity runs and tests (6 runs)
1. Build/act3a_r1.log: baseline level25 + level22 (-slack, both difficulties) and level25 a-e, level22 k1-k6 (Normal;
   stopped after the baseline Difficile pass).
2. Build/act3a_r2.log: level22 k7-k8, level25 f-l (Normal; stopped before Difficile).
3. Build/act3a_r3.log: level25 (variant g) -slack -writeRoutes, both difficulties: 0 DEFECTS; level22 m1-m4.
4. Build/act3a_r4.log: level22 candidate (-writeRoutes, failed, so nothing written) and n3-n7; level22.json restored.
5. EditMode (TestResults/act3a_edit.xml), filter LevelDataM2Tests|SaveM5Tests|StarsTests|DoorwayTests|LevelDefV2Tests:
   **157/157 passed**.
6. PlayMode (TestResults/act3a_play.xml): Rush04_Level25RushesLose, Step58C5/C6 (level25 Normal/Difficile),
   Step64b_Level25Hard, Step58b3/b4 (level22 Normal/Difficile), LevelNum01_, Step41h_: **8/8 passed**.
   - Rush04 table: level25 (a) **lost (Caught, SeenMoving) at 15.4 s, wp 25/27** (was WON at 15.5 s); (c) lost at
     6.7 s; (b) n/a.
- Killing a run left Library/EditorInstance.json and Temp/UnityLockfile behind (the next CLI call refused "already
  open, PID 4572"); removed by hand once the process was gone.

## A VERIFIER
- level25 rush (a) is caught at 15.4 s, at waypoint 25 of 27: right at the end, the margin is thin (Nina turns back as
  it reaches the last aisle cells). Run the full Rush02 (Slow) once to refresh Build/levels_v2/rush_probe.txt.
- level25 boulevard via went from x1.30 to x1.53 (a warning now): the second route is even less viable.
- level22 still has the Comtesse walk-line warning (0.29 m at (14.75, 10.75)): no small fix passes the audit (section 3).
  Needs the v2 rework (second hide) or a decision that it is acceptable.
- Single-hop save migration: a v1 save (never booted on a rev 2 build) migrating straight to rev 3 can lose a v1-only
  unlock (it keeps wins, times and stars). Fine unless v1 saves still exist on a device.
- Act 3 now opens on level25 (night look, "the lights stay on") right after the exam card 16; check the curve by hand.
- LevelNum shots now come from level22 (Build/shots/levelnum/level22_*), not level20: compare with the old ones if a
  reviewer looks for them.
- No build was made (the coordinator builds).
