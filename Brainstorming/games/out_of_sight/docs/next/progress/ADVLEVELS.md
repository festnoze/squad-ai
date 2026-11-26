# ADVLEVELS - Act 5: three big maze houses (level31 to level33)

Date: 2026-11-26. User request (translated): "create new levels with an even more advanced level design: more rooms, more
complicated maze, more humans and dogs, tighter timings." This task builds three of them: level31, level32 and level33.
In parallel, NEWFURN builds level30 (the plant stand) and MAZES builds level34 and level35. Act 5 ("Full house" /
"Maison pleine") starts at index 24 of levels.json, so it holds every new card from 25 on.

All three levels pass LevelAudit (Normal) with 0 defects. levels.json at the end of the task holds 30 levels; act 5 is
level34, level35, level30, level31, level32, level33 (cards 25 to 30). Test pins are updated to that list (section 7).

## 1. Method

The HARDLEVELS method (docs/next/progress/HARDLEVELS.md) was kept: beat sheet first, then topology, then routines, then
furniture. What changed is the tooling, because these houses are larger and their watchers more numerous.

1. **Beat sheet first** (10 to 14 steps per level: threat, intended action, window, alternatives).
2. **Topology** on the 0.5 m audit grid (rooms start on half metres, sizes n x 0.5 - 0.1 m, door gaps on cell centres).
3. **Routines** with short clocks (glances every 4.0 to 5.0 s, naps of 1.4 to 2.5 s awake), then furniture.
4. **Audit loop**, with three helpers under `Build/advlevels/tools/` (not part of the game):
   - `variants.py`: segment tests. The exit is moved onto an intermediate cell (the 0.9 m zone nudged to lie inside the
     room, clear of props and decoys) and the variant gets its own level id, so a failing house is cut into beats and the
     first failing beat is found in one audit run. `_nd` variants drop the decoys (a level with decoys must use one).
   - `-debugSamples` dense runs on a passing prefix: the audit prints its moving sight table every 0.2 s for the whole
     house. `timeline.py` turns that into one line per cell (`x` seen, `.` unseen), which shows each watcher's real
     windows (head turns, telegraphs and the 0.3 s margins included).
   - `solve.py`: a coarse earliest-arrival search over those tables for one crossing (it cannot tell a dog from a human,
     so it is too strict in dog rooms, where standing still is free). It finds which beat is short, and by how much.
5. **Finals**: the files are copied into `Assets/Resources/Levels/` (`finalize.py`) and audited with `-writeRoutes`.

### What the audit taught (worth knowing for any future level)

- **One clock per gate.** A cell watched by two inhabitants with different periods (8.8 s and 9.0 s) is free only when
  both clocks agree, which drifts out for minutes. Every gate here is meant to depend on one watcher; a second watcher's
  line through a doorway was the cause of most failures (Mamie into the dining room, Papa into the dining room through the
  kitchen door, Paul into the kitchen). Fixes: move the door out of the line, or put a tall cabinet in it.
- **Glance windows are shorter than the hold.** With the 0.3 s margins and the 0.4 s head turn, a cell in the base cone is
  free for about hold + 0.2 s per glance, and a cell in the glance cone is seen for about hold + 1.4 s. With alternating
  glances, a cell that only one side glance sees is free for about 2 x period - hold - 1.4 s.
- **Decoy hops.** Hops must alternate glance sides when two consecutive hops need the same side, or the 8 s loiter rule
  breaks (two stops 1.5 m apart both count).
- **Meeting rule and patrols.** Every pair of humans must share a room once in 300 s. A pingpong routine returns to its
  first station, so a patroller cannot start at a meeting point outside its patrol. In each house all humans start in one
  room, at most one human patrols, and the patrol has one end in that room.
- **Budgets.** A human costs 8 to 10 draw calls and one material per personality; a dog about 3 draw calls; a decoy chair
  about 5 (an office chair decoy about 3); a plant 3; a room 4 to 5. With 14 to 15 rooms, four humans and two or three
  dogs, a house holds about 20 props.

## 2. Engine limits raised

- `Tuning.MaxHumans` 3 to 5 and the new `Tuning.MaxDogs` = 3 (the validator said "at most one dog"). GameState and the
  audit already ran every watcher on its own (one bark accumulator per dog, one hold at a time), so nothing else changed.
- Test: `LevelDataM5Tests.At_most_MaxHumans_humans_and_MaxDogs_dogs` (was `At_most_three_humans_and_one_dog`).

## 3. level31 - The Dinner Party / Le diner de famille (chair)

**Concept.** A family dinner in a 14-room manor. The study chair escapes from the study (north-west) to the front door
(south-east) through three bands of rooms joined at their ends: north band west to east, middle band east to west, south
band west to east. Four people and two Labradors, each owning one gate; the dining room is the decoy room.

**Inhabitants and routines** (all four humans start in the dining room and walk to their posts).
- *Paul* (dreamer, seated eye 1.15 m): at the head of the dining table facing south over it; glances west and east in
  turn (+-80 deg, hold 2.4 s, every 4.4 s). He never counts the three dining chairs on the south side.
- *Mamie* (granny, seated): in her armchair in the small salon facing the TV (south), glances east and west in turn
  (hold 2.0 s, every 4.5 s). A display cabinet hides the dining-room door from her.
- *Papa* (hurried): at his stove on the kitchen's north wall, facing it; glances east and west in turn (hold 2.0 s,
  every 4.0 s). The kitchen's south strip is behind him; his west glance guards the cellar door.
- *Maman* (tidy, never fooled, hears 2 m on hard floors): in the hall facing south-west, glancing north-west and
  south-east in turn (hold 2.0 s, every 4.5 s).
- *Rex* (dog): naps in the north corridor facing the study door (asleep 3.0 s, awake 2.0 s).
- *Filou* (dog): naps in the parents' bedroom facing west (asleep 2.5 s, awake 2.0 s).

**Beat sheet.**

| # | Step | Threat | Intended action | Window | Alternative |
|---|---|---|---|---|---|
| 1 | Study door (closed leaf) | Rex awake, 4 m away, facing it | push the door open while he sleeps (a swinging leaf is motion) | 3.0 s nap, about 2.4 s usable | none |
| 2 | North corridor, past Rex | Rex | move only while he naps, freeze while he is awake | 3.0 s naps, about 5 cells each | the guest room and linen room doorways as pockets |
| 3 | Guest room, linen room | none | dead ends; the linen room sits next to the dining room but has no door | - | (misleading) |
| 4 | Bedroom, west strip | Filou | two nap windows to the small-salon door | 2.5 s naps | none |
| 5 | Small salon, west wall | Mamie's west glance | go down the west wall between two west glances | about 6 s between them | none |
| 6 | Dining room, south-east door | Paul's east glance and base | enter during his west glance, 4 cells to the first chair | 2.4 s hold, 1.6 s needed | none |
| 7 | First hop | Paul | 4 cells to the next chair during a glance, freeze beside it while he looks | 2.4 s | none: without the chairs, no schedule |
| 8 | Second and third hops | Paul | 3 to 4 cells per glance, alternating sides | 2.4 s each | |
| 9 | Kitchen door (south-west) | Paul's west glance | last hop during his east glance | 2.4 s | |
| 10 | Kitchen | Papa's west glance on the cellar door | cross behind Papa, leave during his east glance | about 6 s | |
| 11 | Cellar, laundry, salon | none | a breather | free | |
| 12 | Library or cloakroom | Maman | library: open door; cloakroom: closed leaf in her base cone | | the cloakroom (harder) |
| 13 | Hall, north wall | Maman's north-west glance, her ears | slip along the runner rug between two north-west glances | about 6 s between them | |
| 14 | Doormat | none behind her | down the east wall to the mat | free | |

**Plan** (`d` dogs, `p` Paul and Papa, `m` Mamie and Maman, `%` dining chairs, `#` tall furniture, `:` / `.` leaves):

```
+-------------------+-------------------------------------------------------+-------------------+
|                   |                                                       |                   |
|                   :                d                                      |                   |
|                   |                          C O                                              |
|                   +------------ --------------+------ --------------------+                   |
|        B S        |            C H            |            L I            |        C H        |
|                   |                           |                           |          d        |
+-------------------+-----------------------+---+---------------------------+-- ----------------+
|                   |    #       p          |    p                          |            m      |
|                                           |                               |                   |
|        C E        |          K I          |              S M              |        P E        |
|                   |                       |        %     %       %     m  |      #            |
|                   |                                                                           |
+------ ------------+-----------------------+-------+-------------------+---+-------------------+
|                   |                                                                           |
|        L A        |              S L              |        L I        |          m         E  |
|                   |                               +-------------------+          E N          |
|                                                            V E        :                       |
+-------------------+-------------------------------+-------------------+-----------------------+
BU=bureau, CO=couloir_nord, CH=chambre_amis, LI=lingerie, CH=chambre, PE=petit_salon, SM=salle_a_manger,
KI=cuisine, CE=cellier, LA=buanderie, SL=salon, LI=bibliotheque, VE=vestiaire, EN=entree (rows condensed)
```

**Audit (Normal): 0 defects** (`Build/advlevels_final31.log`, `-writeRoutes`).
- Exit 103.6 s, 169 cell moves; waiting 36.0 s (35 %), 13 pauses (12 on the way), longest 5.7 s; spawn wait 7.2 s.
- Route (97 points): study 7.2 s, corridor 12.9 s, bedroom 31.0 s, small salon 36.9 s, dining room 47.5 s, kitchen
  62.4 s, cellar 72.0 s, laundry 78.4 s, salon 84.8 s, library 93.6 s, hall 97.6 s; one leaf opened (the study door).
- Lesson door binds (every leaf locked: no schedule). Requires decoy binds (chairs explaining nothing: no schedule).
- Budgets: 159 of 160 draw calls, 32 of 33 materials. 14 rooms, 14 doors (2 leaves), 14 props, 3 decoys, 1 rug.
- Warnings only: the guest room, the linen room and the cloakroom are dead rooms on the found route (maze dead ends and
  the alternative), Papa's long dwell (a habit note).

## 4. level32 - A Dog's Life / Une vie de chien (stool, three Labradors)

**Concept.** A family house of 15 rooms laid out as a 4 x 4 grid of 5 x 4 m cells (the gallery spans two), where only
the doors make the maze: a serpentine west, east, north and south again, a shortcut from the landing into the salon
(in Marc's view), and a three-room dead end (kitchen, pantry, laundry) that ends right beside the front hall with no
door. Three Labradors (they only see what moves) and four people. The stool tips at full speed, so the audit plays it
careful (0.5 s a cell): every window is short for it.

**Inhabitants and routines** (the four humans start in the salon; Marc keeps his post, the others walk to theirs, Nina
reaching the playroom before the stool may leave the kids' room).
- *Nina* (teen, 6 m, 35 deg): stands at her game console in the playroom facing west, glancing north every 4.6 s
  (hold 2.4 s). Her base cone holds the kids'-room doorway; a toy chest hides the landing doorway from her.
- *Marc* (hurried): watches the salon from its middle, facing the landing shortcut (north), glancing east and west in
  turn (hold 2.0 s, every 4.4 s). The salon is carpeted.
- *Mamie* (granny): reads in her library armchair facing the window (west), glancing +-60 deg in turn.
- *Claire* (tidy, never fooled): looks at a painting on the gallery's north wall, glancing +-60 deg in turn (hold
  2.2 s, every 4.4 s). Two wardrobes stand along the gallery's south wall as hiding places.
- *Rex* (dog): naps on the landing facing west (asleep 3.0 s, awake 1.2 s).
- *Pirate* (dog): paces the dining room south side, 2.0 s at each end, at 1.4 m/s.
- *Biscuit* (dog): naps in the veranda facing east (asleep 2.0 s, awake 2.0 s).

**Beat sheet.**

| # | Step | Threat | Intended action | Window | Alternative |
|---|---|---|---|---|---|
| 1 | Kids' room (spawn) | everyone leaving the salon... then Nina | wait for Nina to take her post | spawn wait | none |
| 2 | Kids'-room door into the playroom | Nina's base cone | cross the doorway cells during her north glance | 2.4 s, 3 cells | none |
| 3 | Landing door | Nina (hidden by the toy chest) | slip down the west wall | free | |
| 4 | Landing | Rex facing the west wall | move only in his naps, freeze while he is awake | 3.0 s naps | the shortcut into the salon (Marc's view) |
| 5 | Parents' bedroom | none | a breather | free | |
| 6 | Library | Mamie's glances | through the north door and out the east door between glances | about 3 s | |
| 7 | Salon | Marc's base and glances | along the south wall behind him, up to the dining door during his west glance | about 2 s | |
| 8 | Dining room | Pirate pacing | cross while he walks away | his walk, about 2.3 s | |
| 9 | Study | none | a breather | free | |
| 10 | Gallery | Claire (never fooled) | between her glances, a wardrobe as a pocket | about 3 s | the two wardrobes |
| 11 | Dressing | none | a breather | free | |
| 12 | Veranda | Biscuit | down to the hall door in his naps | 2.0 s naps | |
| 13 | Kitchen, pantry, laundry | none | dead ends: the laundry backs onto the hall | - | (misleading) |
| 14 | Hall, doormat | none | reach the mat | free | |

**Plan** (`n` Nina, `c` Claire, `m` Mamie and Marc, `d` dogs, `W` wardrobes, `#` tall furniture):

```
+-------------------+-------------------+---------------------------------------+
|                   |            n      |                    c                  |
|        C S                 S A        |                  G A                  |
|                   |                   |          W               W            |
+-------------------+-- ----------------+---- --------------+------------ ------+
|                   |              d    |                   |      #            |
|        C H        |        P A        |        B U        |        D R        |
|                                       |                   |                   |
+------------ ------+------------ ------+-------------- ----+-------- ----------+
|                   |                                       |    d              |
|        L I        |        S L        |        S M        |        V E        |
|    m                             m    |    d           d  |                   |
+-------------------+------ ------------+-------------------+-------------- ----+
|          #        |                                       |                   |
|        P A                 K I        |        L A        |        E N        |
|                   |                   |                   |        E          |
+-------------------+-------------------+-------------------+-------------------+
Top row: chambre_enfants (spawn), salle_de_jeux, galerie. Second: chambre_parents, palier, bureau, dressing.
Third: bibliotheque, salon, salle_a_manger, veranda. Bottom: office (pantry), cuisine, buanderie, entree (exit, E).
North is up; rows condensed from Build/advlevels/tools/plan.py.
```

**Audit (Normal): 0 defects** (`Build/advlevels_final32.log`, `-writeRoutes`).
- Exit 100.3 s, 116 cell moves; waiting 42.3 s (42 %), 14 pauses (13 on the way), longest 7.0 s; spawn wait 7.0 s.
- Route (71 points): kids' room 7.0 s, playroom 8.9 s, landing 19.5 s, parents' bedroom 24.3 s, library 29.5 s, salon
  37.6 s, dining room 52.0 s, study 57.9 s, gallery 64.4 s, dressing 74.4 s, veranda 80.0 s, hall 93.3 s.
- Budgets: 149 of 160 draw calls, 32 of 33 materials. 15 rooms, 15 doors, 21 props (2 wardrobes).
- Warnings only: the kitchen, the pantry and the laundry are dead rooms (the dead-end branch).
- What the iterations taught here: Nina's cone edge ran through the doorway cells (fidelity sightings) until she faced
  due west; a waiting cell on the landing was in her line through the doorway until the toy chest and the north-only
  glances; Mamie's +-80 deg glance looked through the library door at the bedroom; the salon's hard floor put the south
  wall within Marc's earshot.

## 5. level33 - The Farewell Party / Le pot de depart (office chair)

**Concept.** A leaving do on an office floor of 15 rooms. The boss's office chair (procedural, glides 0.4 s at every
stop) crosses from the boss's office (north-east) to the front desk (south-west): the north wing west, the west hall down,
the open space and the party east, then the 18 m south corridor west. Five dead ends (meeting room, copy room,
cloakroom, server room, cleaning closet); a shortcut from the open space to the south corridor sits in Gerard's view.

**Inhabitants and routines** (all four humans start in the north corridor; Kevin paces it, the others walk to their
posts while the chair is still held back by Rex and Kevin).
- *Kevin* (teen, 6 m, 35 deg): paces the north corridor along its north lane, 3.0 s at the east end, 1.5 s at the west
  end, at 1.1 m/s.
- *Gerard* (dreamer): at the west desk island facing east along the open-space aisle; glances north every 4.4 s (hold
  2.4 s). He never counts the two desk chairs on the aisle; beyond 8 m he sees nothing.
- *Bertrand* (hurried): at the cafeteria buffet facing it; glances east and west in turn (hold 2.4 s, every 4.4 s).
- *Sofia* (watchful, 10 m, 60 deg, decoys never fool her): behind the front desk facing the corridor door
  (east-south-east); glances north and south in turn (hold 2.4 s, every 4.8 s). A runner keeps the desk strip silent.
- *Rex* (dog): naps at the boss's door in the secretariat, facing it (asleep 2.0 s, awake 2.0 s).
- *Max* (dog): naps in the west hall facing north (asleep 2.5 s, awake 2.0 s).

**Beat sheet.**

| # | Step | Threat | Intended action | Window | Alternative |
|---|---|---|---|---|---|
| 1 | Boss's office (spawn) | Rex at the door | wait for his nap | free | none |
| 2 | Secretariat | Rex, 1.4 m from the door | slip past while he sleeps; every stop glides | 2.0 s naps | none |
| 3 | North corridor | Kevin pacing | follow behind him, step aside into a doorway while he turns back, then reach the archives door | his walks, about 7 s | meeting room or copy room doorway |
| 4 | Archives | none | a breather | free | |
| 5 | West hall | Max | cross to the open-space door in his naps | 2.5 s naps | |
| 6 | Open space, first hop | Gerard, 1.6 m away | 6 cells to the first desk chair during his north glance | 2.4 s | |
| 7 | Second hop | Gerard | 4 cells to the next chair, freeze in his view (he never counts them) | 2.4 s | none: without the chairs, no schedule |
| 8 | End of the aisle | Gerard | out of his range to the cafeteria door | 2.4 s | the shortcut south door (in his view) |
| 9 | Cafeteria | Bertrand's west glance on the entry | enter during his east glance; the room behind him is out of view | about 6 s | |
| 10 | HR office, south corridor | none | 18 m west, past three dead ends | free | |
| 11 | Front desk door | Sofia's base and north glance | dash in during her south glance (3 cells) | 2.4 s | none |
| 12 | Desk strip | Sofia's north glance | along the runner before her next north glance | about 4 s | |
| 13 | Doormat | Sofia's south glance | down the west wall to the mat | between two south glances | |

**Plan** (`k` Kevin's two ends, `g` Gerard, `b` Bertrand, `s` Sofia, `d` dogs, `%` desk chairs):

```
+---------------+---------------------------------------+-------------------+-------------------+
|    #          |  k                                 k  |                   |                   |
|               |              s   C g                  |              d    |          S        |
|               +---------- --------+---------- --------+                   |                   |
|#     A R      |        S A        |        R E        |        S E        |        B U        |
+------ --------+-------------------+-------------------+-------------------+---+---------------+
|               |  g                                    |            b          |               |
|      C W                         O P         %   %                C A          |      B U      |
|        d      |                                       |                                       |
+---------------+-------+------------------ ------------+-----------------------+-------- ------+
|                       |                                  C O                                  |
|            s          +------------ --------------+------------ --------------+---------- ----+
|    E     A C          |            V E            |            S A            |      L O      |
+-----------------------+---------------------------+---------------------------+---------------+
AR=archives, CO=couloir_nord, SA=salle_reunion, RE=reprographie, SE=secretariat, BU=bureau_direction,
CW=couloir_ouest, OP=openspace, CA=cafeteria, BU=bureau_rh, AC=accueil, CO=couloir_sud, VE=vestiaire,
SA=salle_serveurs, LO=local_menage (rows condensed; the starts of Gerard, Bertrand and Sofia in the corridor shown)
```

**Audit (Normal): 0 defects** (`Build/advlevels_final33.log`, `-writeRoutes`).
- Exit 96.8 s, 159 cell moves, 49 glide stops; waiting 29.5 s (30 %), 13 pauses (12 on the way), longest 3.1 s; spawn
  wait 4.8 s.
- Route (107 points): boss's office 4.8 s, secretariat 14.1 s, north corridor 26.3 s, archives 38.0 s, west hall
  42.6 s, open space 51.8 s, cafeteria 65.8 s, HR office 69.7 s, south corridor 72.1 s, front desk 92.3 s.
- Requires decoy binds (desk chairs explaining nothing: no schedule).
- Budgets: 158 of 160 draw calls, 32 of 33 materials. 15 rooms, 15 doors (the office chair opens no leaf), 2 decoys,
  1 rug.
- Warnings only: the five dead ends are dead rooms (the found route used no doorway pocket in the corridor).

## 6. Level select: a scrolling grid

The level select laid every card on a 6-column grid sized by anchors to fill the area right of the column: 24 cards made 4
rows; 30 would have made 5 squashed rows (190 px instead of 238). The grid is now a vertical scroll view
(`Assets/Scripts/Runtime/LevelSelect.cs`):

- The masked viewport keeps the name "Grid" and the old offsets. A content rect ("GridContent") holds the cards with the same
  fractional anchors; it is exactly the viewport while the cards fit in `Tuning.LevelSelectVisibleRows` (4) rows, and
  taller past that (rows / 4 of the viewport), so every row keeps the height of today's rows. Up to 24 cards the page is
  pixel for pixel what it was.
- Scrolling: mouse wheel and touch drag (a ScrollRect, vertical, clamped; the cards pass their drags up). A slim chair-red
  indicator in the right margin shows the position and hides when nothing scrolls; it is never selectable.
- Keyboard and gamepad: the explicit navigation is unchanged (left/right in play order, up/down by column, Retour and the
  spectator box at the ends). Whatever card gets selected is scrolled into view (eased), and the default card (Jouer's
  level) at once when the page opens.
- Touch layout (BIGBUTTONS): the cards are already finger sized (a quarter of the screen's height); `MenuTouchLayout`
  calls `LevelSelect.SetTouchLayout`, which keeps the grid and its indicator clear of a notch (right, top, bottom).
- Card names ("Card1"...) and act tags are unchanged; act 5's tag sits on card 25.
- Test: `ProbeTestsM5Ui.Step41_CardsFollowTheLevelOrder` now checks the first 24 cards on screen, that the grid scrolls
  exactly when the cards outgrow 4 rows, and that selecting the last card scrolls it into view (and the first one back).

## 7. Integration

- `Assets/Resources/Levels/levels.json`: my ids appended at the end of "levels" (after level34, level35 and level30, which
  the parallel tasks appended first); act 5 added as `{ "from": 24, "nameKey": "act5.name" }`; rev 5 and "previous"
  unchanged. Act 5 therefore opens on card 25 (level34) and holds every new card.
- `Assets/Scripts/Core/Strings.cs`: `act5.name` ("Full house" / "Maison pleine") and `level31..33.name` and `.hint` in both
  languages. Hints name the threats with the data's names (Gerard without an accent, as in the data), never the route,
  in the "tu" register, no key named, no em-dash.
- Level files: `Assets/Resources/Levels/level31.json`, `level32.json`, `level33.json` (written by
  `Build/advlevels/tools/finalize.py` from the generators, then audited in place with `-writeRoutes`).
- Test pins, edited at the end against levels.json as it stood then (30 levels, act 5 = level34, level35, level30,
  level31, level32, level33): `LevelDataM2Tests` (PlayOrder, ActStarts { 0, 7, 16, 20, 24 }, "five acts"),
  `StarsTests.LineUp_EveryLevelHasAReferenceAtBothDifficulties_And90Stars` (90 = 3 x 30),
  `ProbeTestsM5Levels.V2LevelCount` (30), `ProbeTestsStars` ("3 / 90"), plus `LevelDataM5Tests` for the raised limits
  and `ProbeTestsM5Ui.Step41` for the scrolling grid.
- Checked offline against the manifest-wide tests: 3 plants per level, at most 2 per room (`PlantPlacementTests`); decor
  4 to 6 items on hosts, none on the floor, no prop wearing a look (`DressingTests`); the dog's tint and fur stay at
  least 34.9 (CIE76) from every floor and carpet border (`ModelM5Tests`, threshold 30); every undeclared room id is in
  the room type table (`LevelDataM8RoomTypeTests`): level31's `petit_salon` declares `"type": "other"` for that (it is
  what the inference gave, so the audited build is unchanged: no extra light fixtures in a level at 159 of 160).
- Furniture conventions checked against the code (FurnitureKit, ROOMS_PLAN): room furniture (sofa, bed, cabinet,
  bookshelf, counter, stove, fridge, TV unit, bathtub) faces local -z, so its front is yaw + 180 (back on a +z wall: yaw
  0; -z: 180; +x: 90; -x: 270); seats that are bodies (armchair, chairs) and wardrobes face their yaw. The generator
  library now flags a front facing its wall and a sitter not in front of its seat. The same check flags older act 4
  props (not changed here, for the record): level26 Commode, level27 Vestiaire, MeubleTV and Etabli, level28 Bar and
  Cuisiniere, level29 Etagere face their walls.

## 8. Known limits and follow-ups

- **Difficile** was not audited (this task audits Normal only); no designerRouteHard is written, so Difficile's stars use
  the Normal reference, as for act 4.
- **Dead rooms** are warnings: maze dead ends (and the routes the solver did not take) by design.
- **Rug models cost 5 draw calls** in these houses: level31 keeps one runner (the hall's north wall); level33 keeps one.
- **Not run here** (as asked): EditMode and PlayMode suites, the player build. PlayMode pins were edited by reasoning.
- **Sources**: `Build/advlevels/tools/` (generators `gen31.py` to `gen33.py`, `lvlib.py`, `variants.py`, `timeline.py`,
  `solve.py`, `seen.py`, `plan.py`, `finalize.py`, `audit.ps1`) and the audit logs `Build/advlevels_*.log` (the finals:
  `advlevels_final31.log`, `advlevels_final32.log`, `advlevels_final33.log`). The level files in Assets are the source of
  truth.

## 9. How to play them on PC

After the user rebuilds the player:

```
Build/Play/OutOfSight.exe --level level31
Build/Play/OutOfSight.exe --level level32
Build/Play/OutOfSight.exe --level level33
```
