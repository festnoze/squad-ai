# ACT3B progress (2026-11-24): the finale, level24 "The Great Escape" (card 20)

ACT3B was cut off by a rate limit before it wrote anything. ACT3B2 picked up its variants (Build/act3b/ACT3B_B1..B3,
generator scripts in the session scratchpad) and finished. Shipped: level24.json = variant ACT3B_E5 (rev 1, chair).

## Design
- Route: bedroom (closed door, open it) > long corridor (Rex the dog, low eye: stay behind the sideboards) > gallery
  (Theo stands at (11.75, 7.25) facing west, glances north 4 s every 8 s; the dining chairs around the table are the
  decoys) > then two ways east:
  - south: salon door, past Mamie in her armchair (glances away 3.5 s every 8 s), east corridor, hall;
  - north: the runner rug behind Theo, the landing, the kitchen, the hall.
- The robot loops (14.5, 3.65) <-> (14.5, 6.05) in the east corridor (12 s loop). Its hum covers the corridor hops near
  Lea (south way) and, at its north end, the bare floor right behind Theo (north way).
- Lea stands at (16.75, 1.0) facing the doormat (exit (19.25, 0.75)) and looks away 3 s every 9 s (start 11 s).
- requires: door, pet, decoy, hum, exitwatch. lesson final: door, pet, robot bind.
- pace: minShare 0.25, maxShare 0.5, minPauses 6, maxPause 6.0 (unchanged from ACT3B, all met at Normal).

## What fixed the two Normal defects of B1..B3
1. "requires hum : ne contraint pas" and "lecon final : 2 verifications": the north way slipped past Theo in silence
   on the lane rug (x 13.0, z 4.75-9.0). Fix: the rug now starts at z 6.85 (z 6.85-9.0), so the floor 1.0-1.4 m
   behind Theo is bare and heard (dreamer hearing 1.4 m), and the robot loop was stretched north from z 5.65 to 6.05
   so its hum reaches that bare strip. Both ways now need the hum: hum binds at Normal and Difficile.
2. That made Normal faster (42 s), which landed inside Lea's look-away and broke exitwatch. Fix: Lea's glance period
   8 -> 9 s, start 9 -> 11 s.

## Audit runs (Build/act3b_r3..r6.log, Build/act3b/r3..r6.json)
- r3: C1..C5 (rug edge 6.6 / 6.85 / 7.0, robot straight or diagonal). Hum binds in C1..C4; exitwatch and pauses fail
  at Normal. C5 (old robot loop) shows the rug alone is not enough without the longer loop (slack 3).
- r4: D1..D6 (Lea phase and hold). Normal clean; Difficile exitwatch fails (free arrival at 53.3 s in her window).
- r5: E1..E6 (Lea period 9). E1, E2, E3, E5 clean at both difficulties; E5 chosen (largest exitwatch gains:
  5.0 s Normal, 2.7 s Difficile; 7 pauses at both).
- r6: the shipped level24 with -profile human.

## Numbers (shipped level24)
| | Normal | Difficile |
|---|---|---|
| defects (strict, -writeRoutes) | 0 | 0 |
| exit | 47.0 s | 56.0 s |
| wait share / pauses / longest | 40 % / 7 / 4.6 s | 49 % / 7 / 5.8 s |
| slack (-slack) | 4 samples (0.4 s) | 3 samples (0.3 s) |
| exitwatch gain | 5.0 s | 2.7 s |
| human profile (advisory) | 0 defects, exit 56.0 s, 49 %, 10 pauses, longest wait 8.0 s | 0 defects, exit 56.0 s, 49 %, 8 pauses |

Vias aile_nord and aile_sud pass at both difficulties; no dead room.

## Tests
- ProbeTestsRush.Rush04_Level24RushesLose: pass (rush a caught at 7.0 s, b and c n/a). Doc comment now says card 20.
- ProbeTestsM7LevelsC.Step58C3_Level24RouteWins / Step58C4_Level24RouteWinsHard: pass.
- DoorwayTests (EditMode, 4): pass.

## Hint (Strings.cs level24.hint)
- EN: "Rex watches the long corridor: stay behind the sideboards. Hide among the dining chairs while Theo and Mamie
  look away. Behind Theo the runner starts a step too late: cross that bare floor while the robot hums close by. Lea
  watches the doormat; go when she turns her head."
- FR (tu): "Rex surveille le long couloir : reste derrière les buffets. Cache-toi parmi les chaises de la salle à
  manger pendant que Theo et Mamie regardent ailleurs. Derrière Theo, le tapis commence un pas trop tard : traverse ce
  parquet nu quand le robot ronronne tout près. Lea surveille le paillasson ; file quand elle tourne la tête."

## A VERIFIER
- Slack is 0.4 s at Normal, short of the 0.5 s target (every variant of B, C, D, E stayed at 4 samples; the limit was
  not located). Difficile is at the audit floor (0.3 s).
- Human profile at Normal: longest wait 8.0 s, at the cap. Play it by hand.
- The robot sits behind the east corridor wall: in the gallery the player only hears it. Check the hum is loud enough
  to time the bare strip behind Theo.
- Decoy warnings (tolerance 0.4 m, Lea): the 4 dining chairs are not within 0.25 m of a cell centre, so they explain
  nothing to Lea (they still explain for Theo and Mamie; decoy binds). Inherited from ACT3B, harmless.
- Budget: 5 audit runs plus 2 test runs (7 Unity runs), slightly over the 5 planned.
