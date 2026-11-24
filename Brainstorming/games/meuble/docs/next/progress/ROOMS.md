# ROOMS (2026-11-24): kitchen and bedroom packs placed in the played levels

Follow-up of KITCHEN.md and BEDROOM.md (their packs were registered, no level used them). Every played level of levels.json
and the menu house were scanned (rooms by type, props, decor, doors, rugs, spawn, exit, stations and designer routes). Only
"dress" looks on existing props and decor items were added; no gameplay prop was added, moved or resized. The living room
decor of COHERENCE and the plants were left alone.

Edits made by a text patch (scratchpad `rooms_edit.py`): each file is read right before its edit, the "dress" key goes after
the prop's "kind", the new decor entries are appended to the "decor" list; the formatting of the rest is untouched.

## Code

- `DecorKinds.MaxPerLevel` 6 -> 10 (items on hosts; the floor cap stays `MaxFloorPerLevel` 4). The validator reads the
  constant. Decor and looks draw with the wall material in the level's floor and "Dressing" renderers: no new material.
- `DressingTests.Dressing_Levels_ValidateWithTwoToFiveItems`: counts items on hosts (2 to MaxPerLevel) and floor items
  (at most MaxFloorPerLevel) apart; the expected looks list gains the 24 looks below.

## Turned counters (180 degrees, same collider box)

The kitchen run's fronts face the prop's local -z (run along x) or local -x (run along z). These faced a wall:
level8 Plan and level12 Plan (yaw 0 -> 180, fronts now +x), level11 Plan (0 -> 180, fronts +z), level18 Plan (90 -> 270,
fronts +x; its mug keeps its host frame place). All others already faced their room.

## Per level (card / file)

Host frame: x, z from the host's centre, yaw from the host's front. Floor items: absolute x, z, yaw.

| Card | File | Kitchen | Bedroom |
|---|---|---|---|
| 2 | level2 | none | Nightstand dressed bedside_table; bedside_lamp (-0.09, 0.03) bed side, alarm_clock (0.15, -0.02); slippers floor (-0.1, -2.2) between bed and wardrobe |
| 3 | level3 | Counter (2.4 sink) sink unit; cutting_board and kettle on KitchenTable | none |
| 6 | level6 | none | odd_socks floor (-1.65, -3.625) at the bed foot; slippers floor (-1.175, -4.3) in the strip east of the bed |
| 8 | level8 | Plan turned 180, base/drawer run; cutting_board, saucepan, kettle on Plan | laundry_basket floor (2.1, 8.1) beside the bed head; clothes_heap floor (2.0, 7.0) east of the bed |
| 9 | level9 | none | TableDeChevet dressed; lamp (-0.09) bed side, clock (0.15); slippers floor (1.85, 7.8) |
| 10 | level12 | Plan turned 180, base run; cutting_board, stock_pot, kettle on Plan | laundry_basket floor (1.9, 9.1) between bed and wardrobe; clothes_heap floor (0.75, 6.85) at the bed foot |
| 11 | level11 | Plan turned 180, base run; cutting_board, saucepan (handle to the front), kettle on Plan | alarm_clock on Coiffeuse; slippers floor (1.85, 8.45) by the bed head; clothes_heap floor (3.85, 5.95) by the dresser |
| 12 | level15 | Plan (2.4 sink) sink unit; no utensil host in the kitchen | no bedroom |
| 13 | level13 | Comptoir (cafeteria 2.4 sink) sink unit; no utensil host (MachineCafe is the coffee machine, left plain) | no bedroom |
| 14 | level14 | Plan (2.4 sink) sink unit | alarm_clock on Commode (beside its linen lamp); floor_book_stack floor (1.55, 7.8) by the armchair |
| 15 | level18 | Plan turned to 270, base run; cutting_board, saucepan, kettle on Plan (mug kept) | teddy_bear floor (-1.15, -1.3) by the child bed |
| 16 | level17 | Plan (2.4 sink) sink unit | clothes_heap floor (2.0, 8.35) by the bed head; odd_socks floor (0.9, 6.5) at the bed foot |
| 17 | level25 | shop, no kitchen | no bedroom |
| 18 | level19 | Plan base, Evier sink unit, Cuisiniere range; frying_pan on Cuisiniere, cutting_board on Plan (next to the sink) | Chevet dressed; lamp (0.09) bed side, clock (-0.15); slippers floor (2.2, 10.9) |
| 19 | level22 | Evier sink, Cuisiniere range, Comptoir base; frying_pan and saucepan on Cuisiniere, cutting_board on Comptoir | ChevetChambre and ChevetBoudoir dressed; lamp on ChevetChambre, clock on ChevetBoudoir (x -0.165, clear of the globe it keeps); slippers floor (0.85, 10.95) |
| 20 | level24 | Evier sink, Cuisiniere range, Plan base; stock_pot and frying_pan on Cuisiniere, cutting_board on Plan, kettle on TableCuisine | teddy_bear floor (2.05, 12.3) and floor_book_stack (2.45, 12.35) at the child bed's foot |
| menu | title_house | Plan (2.4 sink) sink unit | alarm_clock on Commode; clothes_heap floor (2.0, 8.35) by the bed head |

Cards 1, 4, 5, 7 have no kitchen or bedroom. Consoles, fireplaces, Accueil, Caisse, Buffet, Bench: never dressed.
No pantry look: no played kitchen has a tall cabinet or wardrobe (level13 MachineCafe is a coffee machine).

Floor items keep about 0.9 m off doorways, off the spawn and the exit, and out of stations and designer routes, with the
exceptions listed below.

## Audit

LevelAudit -writeRoutes, normal and difficile (the r1 run compiled the code change too):

- r1 (Build/rooms_r1.log): 0 defects on level2, 3, 6, 8, 9, 11, 12, 13, 14, 15, 17, 18, 19, 24. level22 had 1 defect: the
  boudoir clock at x -0.15 overlapped the bedside globe by 6 mm (the globe is 0.2 m wide, not the clock's 0.11). Moved to
  x -0.165.
- r2 (Build/rooms_r2.log): level22 had 0 defects in normal and difficile.
- title_house had 2 defects, the same as COHERENCE noted for a menu house: no schedule (no route, so the audit cannot find one)
  and the search budget running out. No validator, decor or lamp defect. Budgets 101/160 draw calls, 32/32 materials (the
  same count as before; the looks share the wall material).
- Budgets (normal, draw calls / materials): level2 65/120 18/24, level3 72/120 19/24, level6 62/120 23/24, level8 74/120
  23/24, level9 72/120 22/24, level12 93/160 21/32, level11 77/120 24/24, level15 63/120 22/24, level13 107/160 30/32,
  level14 98/160 25/32, level18 60/120 20/24, level17 109/160 28/32, level19 108/160 27/32, level22 139/160 31/32,
  level24 127/160 29/32. These are within budget, and no level gained a material.

## Tests (written, not run)

- EditMode `--filter Dressing_` (DressingTests: caps, expected looks), `DoorwayTests`, `PlantPlacementTests`.
- PlayMode `--filter Dressing_` (ProbeTestsDressing), and the route and rush tests of the re-audited levels.

## A VERIFIER

- The four turned counters (level8, 11, 12, 18): fronts into the kitchen, nothing else changed (same box).
- The 2.4 m sinks (level3, 13, 14, 15, 17, menu) are 0.9 m tall: the run is squashed to a 0.75 m worktop.
- level18 teddy: the room is 2 x 2 m and all route; the bear sits 5 cm beside the player's path at x -0.75.
- level6 slippers: in the 0.3 m strip between the bed and the east wall (the west side is the player's route).
- level22 boudoir keeps its 0.2 m bedside globe (lamp only in the chambre: the cap); the clock stands beside it.
- level11 heap is 0.7 to 0.9 m from the east door; level19 has two utensils only (cap 10 reached).
