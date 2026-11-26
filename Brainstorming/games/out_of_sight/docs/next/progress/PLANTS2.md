# PLANTS2: plants in room corners and at corridor ends

Product owner rules: a potted plant always stands close to a corner of its room, or at the end of a corridor; never
in a bathroom; every played level has at least 3 plants; no room has more than 2.

## Rule and thresholds (Assets/Tests/EditMode/PlantPlacementTests.cs)

- Gap = distance from the plant's footprint to the inner wall face (room edge minus half the wall thickness), per axis.
- Corner: gap at most 0.35 m on both axes (`NearWall`).
- Corridor: a room at least 2.5 times longer than wide (`CorridorRatio`); a plant within 0.35 m of an end wall (the
  long axis) stands at the corridor end.
- Bathroom: the room id contains sdb, bain, bath, wc or toilet, or the room holds a bathtub, washbasin, toilet or
  shower prop (level14 names its bathroom "salle"; level3's "salle" is a dining room).
- Every level*.json and title_house.json: corner or corridor end, no bathroom.
- Every played level (levels.json): at least 3 plants (`MinPerLevel`), at most 2 per room (`MaxPerRoom`), except the
  `Fewer` list, which fails as soon as a level in it reaches 3:
  - level1, level5, level7: a single room, so 2 per room caps them at 2;
  - level18: 1. The rooms are tiny; every other corner is a doorway approach, the porte_cuisine leaf sweep, the bed,
    the buffet, the counter, the spawn, the exit mat or Odile's station;
  - level15: 0. The first plant brings two materials (Colour Foliage, Colour Soil): 25, over the budget of 24;
  - level25: 2. A plant costs 3 draw-call slots; a third one gave 123, over the budget of 120.

## Plants per played level

Before (state before PLANTS2): card 2 level2 Plant (couloir NE, corridor end); card 7 level7 Plant (bureau NE);
card 8 level8 Plante (salon, (5.25, 6.5), 0.45 m off the west wall); card 10 level12 Plante (couloir NE, corridor
end) and PlanteSalon (salon, (7.75, 5.9), middle of the room); card 14 level14 Plante (sejour SW). All others: none.

After (new plants are 0.5 x 0.5, height 1.0 to 1.5, colours #3F8F4F / #8C5A36, no "style"):

| Card | File | Count | Plants |
|---|---|---|---|
| 1 | level1 | 2 | Plante room (3.6, -2.6) SE; PlanteNord room (-3.6, 2.6) NW |
| 2 | level2 | 3 | Plant couloir (4.2, 2.7) NE corridor; PlanteChambre chambre (4.1, 0.3) NE; PlanteChambre2 chambre (-0.1, 0.4) NW |
| 3 | level3 | 3 | PlanteSalle salle (-4.1, -2.1) SW; PlanteCuisine cuisine (4.7, 2.1) NE; PlanteBuffet salle (0.65, -2.2) SE |
| 4 | level4 | 3 | PlanteSalon salon (-4.6, 1.6) NW; PlanteFenetre salon (-0.6, 1.6) NE; PlanteEntree entree (3.75, -1.65) SE |
| 5 | level5 | 2 | PlanteSalon salon (3.6, 2.1) NE; PlanteSud salon (-3.6, -2.1) SW |
| 6 | level6 | 3 | PlanteSalon salon (4.6, -1.6) SE corridor; PlanteChambre chambre (-4.6, -2.7) NW; PlanteChambre2 chambre (-1.4, -2.7) NE |
| 7 | level7 | 2 | Plant bureau (2.0, 4.5) NE; PlanteBureau bureau (2.1, -4.6) SE |
| 8 | level8 | 3 | Plante salon (4.85, 6.6) NW (moved); PlanteCuisine cuisine (4.0, 4.0) NE; PlanteChambre chambre (0.4, 5.1) SW |
| 9 | level9 | 3 | PlanteSalon salon (5.1, 0.4) SW; PlanteChambre chambre (0.4, 4.9) SW; PlanteSalon2 salon (11.3, 0.4) SE |
| 10 | level12 | 4 | Plante couloir (9.5, 8.75) NE corridor; PlanteSalon salon (9.55, 7.55) NE (moved); PlanteCuisine cuisine (0.4, 0.4) SW; PlanteEntree entree (12.0, 9.0) NE |
| 11 | level11 | 3 | PlanteChambre chambre (3.8, 4.9) SE; PlanteSalon salon (11.5, 8.5) NE; PlanteCuisine cuisine (11.5, 0.4) SE |
| 12 | level15 | 0 | (material budget) |
| 13 | level13 | 3 | PlantePlateau plateau (0.4, 0.4) SW; PlanteDirection direction (0.4, 9.5) NW; PlanteCafeteria cafeteria (13.5, 3.6) SE |
| 14 | level14 | 3 | Plante sejour (4.85, 1.85) SW; PlanteChambre chambre (0.4, 8.0) NW; PlanteCuisine cuisine (17.5, 8.0) NE |
| 15 | level18 | 1 | PlanteCuisine cuisine (-8.45, -0.15) SE |
| 16 | level17 | 3 | PlanteCuisine cuisine (17.5, 8.5) NE; PlanteBureau bureau (0.4, 0.4) SW; PlanteChambre chambre (0.4, 5.4) SW |
| 17 | level25 | 2 | PlanteBureau bureau (0.4, 11.6) NW; PlanteMagasin magasin (17.0, 11.6) NE (draw-call budget) |
| 18 | level19 | 3 | PlanteCuisine cuisine (13.0, 0.4) SE; PlanteSalon salon (17.5, 11.5) NE corridor; PlanteEntree entree (4.0, 0.4) SE |
| 19 | level22 | 3 | PlanteBoudoir boudoir (3.3, 3.4) SE; PlanteBibliotheque bibliotheque (14.6, 6.4) SW; PlanteVestibule vestibule (24.5, 0.9) SE |
| 20 | level24 | 3 | PlanteCuisine cuisine (19.5, 12.5) NE; PlanteCouloir couloir (13.0, 12.5) NE corridor; PlanteGalerie galerie (4.9, 4.1) SW |

level12 also gets MeubleHaut, a 0.5 x 0.5 x 1.3 cabinet (occluder) where PlanteSalon stood: with the plant moved to
the corner and nothing there, the audit found only a loitering schedule (normal: 67 % waiting, a 32 s stay near
(1.75, 1.25); hard: a 27 s stay and a fidelity miss at (4.35, 8.75)). The level was tuned around that cover.

Candidates came from a scratch script: every corner of every non-bathroom room, kept when the footprint is 0.05 m
clear of props, decoys, platforms and ramps, outside every door approach (1.1 m deep), 0.8 m from the spawn, the exit
and every station, 0.6 m from walk lines and robot loops, 0.6 m from both designer routes, 1 m from another plant;
the corner farthest from the routes and stations won.

## Audit (LevelAudit.RunBatch, normal and difficile, -writeRoutes)

- Round 1 (Build/plants2_r1.log, 19 levels): 0 defects except level12 (2, the cover above), level15 (materials 25 of
  24) and level25 (draw calls 123 of 120), at both difficulties.
- Round 2 (Build/plants2_r2.log: level1, 2, 3, 4, 5, 6, 8, 9, 12, 11, 13, 25, 24): 0 defects at both difficulties.
  level15 is back to its original file. Levels unchanged since round 1 (7, 14, 17, 18, 19, 22) kept their round 1
  result.
- level24: requires door, pet, decoy, hum and exitwatch all still binding; Normal margin 0.3 s (ACT3B2 reported
  0.4 s).
- Slack (-slack) was not measured, to save Unity runs.

Tests were not run (the user runs them): EditMode `PlantPlacementTests|DoorwayTests`, PlayMode
`ProbeTestsRush|ProbeTestsM7Levels` for the route replays and rushes.

## A VERIFIER

- level12: MeubleHaut (cabinet) in the middle of the salon replaces the plant's cover; look at it in game, and
  PlanteSalon now stands 0.7 m from the couloir plant, through the wall.
- level24: Normal margin 0.3 s instead of 0.4 s; remove PlanteGalerie first if it must go back.
- level3 PlanteBuffet and level4 PlanteEntree touch the dresser / sit 0.1 m from the bookshelf; check for clipping.
- level15 (0 plants) and level25 (2): raise the material / draw-call budgets, or accept the exceptions.
- Look at the new plants in game for clipping with window frames (windows were not a constraint).
