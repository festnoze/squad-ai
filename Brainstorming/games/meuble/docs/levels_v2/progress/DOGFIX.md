# DOGFIX progress (dog contrast on the v2 floors of level12 and level15)

## Cause
`ModelM5Tests.The_dog_stands_out_from_every_floor_it_walks_on` measures the CIE76 distance (linear sRGB, D65) between
the dog's tint `#4F6670` (PersonalityDef) and the `floorColor` of every room of every listed level with a dog (plus the
0.82 border of a soft room), bar dE 30. The v2 palette put dark teal and green floors under the dog:

| Room | finish | floorColor | dE to the dog | finish image mean | dE to the dog |
|---|---|---|---|---|---|
| level12 cuisine | tealtile | #5E9C9A | 23.8 | #406361 | 9.3 |
| level12 entree | verde | #4F7A62 | 23.1 | #2A4036 | 21.2 |
| level15 entree (Rex naps here) | verde | #3F6B4F | 25.2 | #2A4036 | 21.2 |

So the problem was not only the miniature colours: the rendered finishes themselves (the teal tiles above all) hide the
blue-grey dog. Means computed offline (tools/assets venv, numpy + Pillow, linear mean of each PNG in
Assets/Art/Environment), with a Python replica of the test's metric (control "orange dog on wood" = 14.1, as the test).

## Change (visual data only, no route, station, prop, door, `floor` hard/soft or wall touched)
- level12 cuisine: `floorFinish` tealtile -> marble, `floorColor` #5E9C9A -> #D8D4CC.
- level12 entree: `floorFinish` verde -> marble, `floorColor` #4F7A62 -> #D8D4CC.
- level15 entree: `floorFinish` verde -> marble, `floorColor` #3F6B4F -> #D8D4CC.

`floorColor` had to move too: the test reads it, not the finish (it is the level-select miniature tint, LEVELS_V2.md
"floorColor/wallColor only tint the miniature"); #D8D4CC is the marble miniature colour already used by level2 (LV1)
and sits on the marble image mean #D6D3CB. Room-type rules (FLOORS_WALLS.md 2): kitchen = tile or marble, hall = marble
or parquet: both kept. Floor looks: level12 parquet, light oak, marble = 3 (it had 4 with the v2 palette: parquet,
light oak, teal tile, verde); level15 parquet, ivory tile, marble = 3. Coverage (ProbeTestsM42Look Step22e): teal tile
stays in level19 (cuisine), verde in levels 4, 8, 14, 18, 22. LEVELS_V2.md palette lines for level12 (cuisine
limewash/tealtile, entree quatrefoil/verde) and level15 (entree limewash/verde) are superseded on the floor side only.

## After
Every room of the dog levels 12, 15, 17, 20, 24 at dE >= 41.2 (offline); level12 cuisine/entree and level15 entree 45.5.

## Unity run (one, EditMode, filter ModelM5Tests)
`TestResults/DOGFIX.xml` (2026-11-20 23:27): 12 / 12 pass, 0 failure, including
`The_dog_stands_out_from_every_floor_it_walks_on` and `The_dog_alarm_cone_is_as_distinct_from_its_calm_as_a_human_s`.

## To look at in game
level12 kitchen and hall, level15 long hall: white-grey marble instead of teal tiles / verde (lighter rooms, Rex now
clearly readable). Step22e coverage still needs teal tile in level19 (RULEFIX owns it; it has it today).
