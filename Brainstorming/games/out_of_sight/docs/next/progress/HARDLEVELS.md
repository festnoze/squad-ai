# HARDLEVELS - Act 4: four long maze houses (level26 to level29)

Date: 2026-11-26. Task: add four hard, long levels in full houses (10+ rooms each), built like mazes, with tight but fair
windows. They are appended as act 4 ("The long way round" / "Le chemin le plus long") after the finale level24.

| Card | Id | Title (EN / FR) | Body | Rooms | Main threats | Solver exit (Normal) |
|---|---|---|---|---|---|---|
| 21 | level26 | Lights Out / Extinction des feux | floor lamp, night | 12 | the Comtesse's corridor watch, Alfred's kitchen loop, Rex napping | 59.1 s |
| 22 | level27 | Rush Hour / L'heure de pointe | chair | 12 | Theo's doorway and sofa, Papa's dining-room watch, Maman's garage door and car | 43.9 s |
| 23 | level28 | The Labyrinth / Le labyrinthe | stool | 11 | Odile's corridor patrol, Hugo's library, Paul at the bar | 105.1 s |
| 24 | level29 | Moving Day / Le jour du déménagement | office chair | 11 | Theo among the office chairs, Rex, the robot, Mamie, Lea's corridor | 43.0 s |

The solver exit is the audit's fastest unseen schedule, an upper bound on a skilled run and never a difficulty measure.
A first clear including retries is much longer.

## 1. Method

The user asked for gameplay first, topology after. Each level went through the same loop:

1. **Beat sheet first.** Choose the steps the player must solve (8 to 11 per level), the threat of each step, the
   intended action, the window length, and an alternative where the maze offers one.
2. **Then the topology.** Rooms are laid on the 0.5 m audit grid (rooms start on half metres, sizes n x 0.5 - 0.1 m,
   so cell centres fall on .25/.75 and every door gap is a single lane). Doors are placed only where a beat needs them.
   The house is a forced snake (or U) so that the only way to the exit runs through every beat; side rooms are dead
   ends, pockets or alternatives.
3. **Then the moves.** Watcher routines are written to create the windows: sentinels with periodic head glances
   (`glanceEvery`), short ping-pongs, a dog nap cycle, a robot loop. Then furniture, rugs and decor.
4. **Audit loop.** Every iteration was validated by a local pre-check (tiling, doorway approaches, plants in corners,
   wardrobe fronts, station clearance) and then by `LevelAudit` on variant files under `Build/hardlevels/` (about 30
   audit runs). The finals were copied into `Assets/Resources/Levels/` and audited once more with `-writeRoutes`.

### Audit rules that shaped the designs (worth knowing for any future level)

- **Short-period gates.** No wait may exceed 8 s near one spot. The loitering rule counts every still second within
  1.5 m of a point, hidden time and hops included. So every gate is driven by a clock of 5 to 9 s: a glance period,
  a nap cycle, or a short ping-pong. Long roaming loops create long waits and were removed or kept off the route.
- **Humans must meet but never touch.** Every pair of humans must share a room once in 300 s, and must never come
  within 0.6 m. All four levels start their humans in one room. Then each human walks to a post, or keeps to its own
  part of the house, along a path no other human uses.
- **Wardrobes.** A hide cell must stay in front of the wardrobe face after the replay's 0.1 m release. So the face must
  stand 0.15 to 0.4 m from a cell row, and a wardrobe flush against a wall offers no hide cell. Hiding is also refused
  while a human looks at the empty spawn spot, so the spawn must be out of the corridor's view.
- **Decoys are occluders too.** A decoy standing between the watcher and the cell it explains hides that cell, and the
  decoy-free search then passes "behind" it. Explained cells must be in plain view of the watcher.
- **Door leaves.** The reach cell must be on the push side: a leaf swings away from the side the player opens it from.
  The office chair (radius 0.30) has no reach cell in front of a leaf on this grid, so level29 has no player door.
- **Budgets.** Houses have 160 draw calls and 33 materials. Each human personality, the dog's two maps, the robot and
  every distinct prop colour cost a material. Hence the small prop palette and the shared personalities.

## 2. level26 - Lights Out (floor lamp, night)

**Concept.** Night in the Comtesse's manor. You are the guest-room reading lamp and the front door is at the other end
of the house. Switched off, the lamp is seen only up close (dark range: 0.4 x the watcher's range). So the level is
about distance: creep in the dark inside a watcher's cone, and cross the last metres when they look away. The lamp is
the slowest body (0.9 s per 0.5 m cell), so every window has to be long enough for a few cells, never just one.

**Inhabitants and routines.**
- *Comtesse* (watchful, 10 m / dark 4 m, hearing x1.0): starts in the galerie. After 3 s she walks to the bathroom
  doorway and stands there for good, looking west down the long corridor. Her head glances alternately left and right
  (+-80 deg), each held 4.5 s, every 9 s.
- *Alfred* (hurried butler, dark range 4 m, hearing x0.5): a loop of about 15 s. Galerie east end, facing west down the
  galerie, 2 s. Then the stove, facing the wall, 2.5 s. Then the pantry, 2 s. Then back up through the kitchen.
- *Rex* (dog, sees motion only, dark range 2.4 m): naps in the library facing north, asleep 5 s, awake 2.5 s.
- Runner rugs silence the corridor and the galerie. The library and the boudoir have soft floors.

**Beat sheet.**

| # | Step | Threat | Intended action | Window | Alternative |
|---|---|---|---|---|---|
| 1 | Guest room (spawn) | the click of the switch (2.75 m) | switch off at once; nobody is in earshot | free (safe spawn) | stay lit until the corridor: you will be seen |
| 2 | Corridor, west half | the Comtesse's cone | walk in the dark: beyond 4 m her cone does not see you | free while dark | none (only exit of the bedroom) |
| 3 | Corridor, last 4 m | the Comtesse at 3 to 4 m | move only during one of her glances, into the boudoir door | 4.5 s glance, about 5 cells | none (lit, the corridor is impossible: the audit proves it) |
| 4 | Boudoir | none (soft, out of sight) | catch your breath, pick the way | free | library way (step 4b) |
| 4b | Library (alternative) | Rex awake | pass him only while he naps | 5 s nap | |
| 5 | Salon | Alfred coming back from the pantry | cross while he is at the stove or the galerie end | about 4 s | |
| 6 | Salon to galerie door | Alfred's galerie post, 1 m away | slip through behind him as he leaves for the stove | about 2.5 s | |
| 7 | Galerie to kitchen | Alfred at the stove (hearing 1.25 m) | pass behind his back, keeping 1.5 m away | stove dwell 2.5 s plus his turn | |
| 8 | Kitchen to dining room | Alfred walking west from the pantry | through the high door, out of his line | between his passes | |
| 9 | Dining room, vestibule | none | reach the doormat in the dark | free | |

**Plan** (one character per 0.25 m across, 0.25 m per row; `S` spawn, `E` doormat, lowercase = a watcher's post
(c Comtesse, a Alfred, d Rex), `W` wardrobe, `#` tall furniture, gaps in walls = doorways, `:` / `.` = door leaf):

```
+-----------+-----------------------+-----------+
|           |                       |           |
|           |                       |           |
|                      C O             c        |
|           |                       |           |
|           |                       |           |
|           +-----------+-- --------+           |
|    C H S  |           |           |    S B    |
|           |           |           |           |
|           |                       |           |
|           |           |           |           |
|           |           |           |           |
|           |           |           +------ ----+
|           |    L I    |    B O    |           |
+-----------+           |           |           |
|           |    d     #|                       |
|           |           |           |           |
|           |           |           |           |
|           +-- --------+-----------+           |
|           |                W      |    S L    |
|           |                       |           |
|    B U               c            |           |
|           |                       |           |
|           |          G A       a              |
|           |                       |           |
|           |                       |           |
+-----------+-------------+---- ----+-+---- ----+
|           |             |           |         |
|           |             |           |         |
|           |                         |         |
|           |             |           |         |
|           |             |           |  a      |
|           |             |           |         |
|  E V E         S M      |    K I       P A    |
|           |             |           |         |
|           |             |      a    |         |
|           |             |           |         |
|           |             |           |         |
+-----------+-------------+-----------+---------+
CH=chambre, CO=couloir, SB=salle_de_bain, LI=bibliotheque, BO=boudoir, SL=salon, BU=bureau, GA=galerie, VE=vestibule, SM=salle_a_manger, KI=cuisine, PA=office
```

**Audit (Normal): 0 defects.**
- Exit 59.1 s; 48 cell moves.
- Waiting 27 %, 4 pauses (3 mid-route), longest 4.7 s; spawn wait 6.2 s; longest loiter 7.7 s.
- Lesson dark binds: with the lamp always lit there is no schedule.
- Budgets: 133 of 160 draw calls, 33 of 33 materials.
- Solver route: guest room, corridor, boudoir, salon, galerie, kitchen, dining room, vestibule. The solver toggles the
  lamp three times; one switch-off at the start is all a player needs.
- Warnings only: the bureau is a dead end (no route, no post), and two habit notes (the Comtesse's 3 s without a
  glance, Alfred's mean dwell 2.2 s).

**Difficile.** The strict solver finds no schedule. The 1.15 range factor stretches the Comtesse's dark range to 4.6 m,
which closes the corridor beat. No designerRouteHard is written, so Difficile's stars use the Normal reference.

## 3. level27 - Rush Hour (chair)

**Concept.** 8 am, the family rushes out. The desk chair escapes from the home office to the garage. The house is a
forced snake: west corridor, salon, dining room, kitchen, east corridor, laundry, garage. The only way into the garage is
a door only Maman opens on her way out to the car (a player-locked household door). She then keeps watch over the car
and the doormat.

**Inhabitants and routines.**
- *Theo* (teen, 6 m, narrow 35 deg cone, poor hearing): ping-pongs between his bedroom doorway and the salon sofa.
  - At his doorway he looks south into the corridor for 3.5 s, with one glance east.
  - On the sofa he sits facing the TV for 4 s, with one glance.
- *Papa* (hurried): leaves the salon after 5 s and sits in the dining-room armchair, facing the kitchen door. Every 5 s
  he glances north, holding 2.5 s.
- *Maman* (hurried, fast): leaves the salon at 3.5 s. She walks the second half of your route ahead of you and opens the
  garage door at about 21 s. Then she stands by the car and watches the garage, glancing left and right (hold 3 s,
  every 6.5 s).

**Beat sheet.**

| # | Step | Threat | Intended action | Window | Alternative |
|---|---|---|---|---|---|
| 1 | Home office door (closed leaf) | Theo at his doorway | push the door open once he leaves his doorway | about 4 s | none (the only door) |
| 2 | West corridor to the salon door | Theo walking to the sofa | dash behind him | his sofa phase | |
| 3 | Salon, to the bookshelf | Theo on the sofa, facing the TV | cross during his glance, hide behind the bookshelf | 1.5 s glance | |
| 4 | Bookshelf to the dining-room door | Theo | next glance | 1.5 s glance | |
| 5 | Dining room | Papa facing the kitchen door | move during his north glance | 2.5 s every 5 s | the west half is out of his cone: wait there |
| 6 | Kitchen | Maman passing ahead of you | keep behind her; the dresser hides the kitchen from Papa | after she passes | |
| 7 | East corridor, laundry | the garage door still shut | wait for Maman to open it | from about 21 s | none (only Maman opens it) |
| 8 | Garage, north | Maman at the car | hide behind the boxes | free behind them | |
| 9 | Doormat | Maman watching it | slide on during one of her glances | 3 s | |

**Plan** (t Theo, p Papa, m Maman):

```
+---------------+---------------+-----------+---------------+-----------+---------------+
|               |               |           |               |           |               |
|               |               |           |               |           |               |
|               |               |           |               |           |               |
|               |               |           |               |           |               |
|               |               |           |               |           |               |
|               |               |           |               |           |               |
|        S      |               |           |               |           :               |
|               |               |           |               |           |               |
|      B U      |      C T      |    S B    |      C H      |    L A    |               |
|               |               |           |               |           |               |
|               |               |           |               |           |               |
|               |               |           |               |           |               |
|               |        t      |           |               |           |               |
|               |               |           |               |           |               |
|               |               |           |               |           |               |
+--------.------+-------- ------+---+-- ----+-------- ------+------ ----+               |
|                                   |                                   |               |
|                                   |                                   |               |
|                                   |                                   |               |
|                                   |                                   |               |
|                C O                |                C E                |               |
|                                   |                                   |               |
|                                   |                                   |          E    |
+------ --------+---------- --------+---+---------------+---- ----------+               |
|               |                       |               |               |      G R      |
|               |                       |               |               |               |
|               |  m                    |    p          |               |               |
|               |                       |               |               |               |
|               |                       |               |               |               |
|               |                       |               |               |               |
|               |                #      |              #|               |               |
|               |                       |               |               |               |
|               |          t            |               |               |               |
|               |                       |               |               |               |
|#              |                                                       |               |
|               |                                       |               |               |
|      E N      |          S L                 S M      |      K I      |               |
|               |                                       |               |               |
|                                                       |               |               |
|               |                       |               |               |               |
|               |                  p    |               |               |               |
|               |                       |               |               |               |
|               |                       |               |               |               |
|               |                       |               |               |               |
|               |                       |               |               |            m  |
|               |                       |               |               |               |
|               |                       |               |              #|               |
+---------------+-----------------------+---------------+---------------+---------------+
BU=bureau, CT=chambre_theo, SB=salle_de_bain, CH=chambre, LA=buanderie, CO=couloir, CE=couloir_est, EN=entree, SL=salon, SM=salle_a_manger, KI=cuisine, GR=garage
```

**Audit (Normal): 0 defects.**
- Exit 43.9 s; 77 cell moves.
- Waiting 30 %, 5 pauses (4 mid-route), longest 5.5 s; longest loiter 5.5 s.
- Lesson door binds (every leaf locked, no schedule). Requires household binds (without the door Maman opens, no
  schedule).
- Budgets: 149 of 160 draw calls, 31 of 33 materials.
- Warnings only: the bathroom, the parents' bedroom and the hall are dead ends.

**Difficile.** One fidelity sighting: Maman sees the chair in the garage at 38.4 s in the fine replay, so no
designerRouteHard is written. The Normal route is used as Difficile's stars reference.

## 4. level28 - The Labyrinth (stool)

**Concept.** A rambling old house, three bands of rooms joined only at their ends. The route runs west to east upstairs,
east to west through the middle, and west to east downstairs. It mixes the two "pretend" mechanics:
- Upstairs, hide in a wardrobe from a watcher no decoy can fool (Odile, tidy).
- Downstairs, freeze among identical bar stools in front of a watcher who never counts them (Paul, a dreamer).

Both are proven necessary by the audit.

**Inhabitants and routines.**
- *Odile* (tidy, 10 m, never fooled by decoys): ping-pongs along the upstairs corridor, a carpeted runner 8 m long.
  - East end: inside the bathroom door, looking west, 1.5 s.
  - West end: by the bedroom, looking east, 2.5 s.
- *Hugo* (teen): sits in the library armchair facing west, glancing +-80 deg (hold 3 s, every 6.5 s). A long bookshelf
  hides the north lane from him.
- *Paul* (dreamer): stands at the breakfast bar facing the bar stools, glancing +-80 deg (hold 2.2 s, every 4.6 s).
- All three start in the bathroom. Hugo and Paul walk down to their posts in a staggered order, and Odile starts her
  patrol.

**Beat sheet.**

| # | Step | Threat | Intended action | Window | Alternative |
|---|---|---|---|---|---|
| 1 | Bedroom (spawn) | Odile at the west end | wait out of the corridor's view | free | |
| 2 | Corridor, follow her | Odile walking east | move behind her back | her walk, about 6 s | |
| 3 | Wardrobe B | Odile turning back at the bathroom | push into the wardrobe before she turns; she walks past you | hidden about 5 s | wardrobe A, earlier |
| 4 | Corridor to the bathroom | Odile walking west | leave behind her, reach the bathroom before she turns | about 5 s | |
| 5 | Bathroom to salon | Odile's next pass | through the east door, wait in the salon | free | |
| 6 | Library, north lane | Hugo's north glance | enter behind him, walk behind the bookshelf | base phase | the boudoir pocket |
| 7 | Library west side | Hugo's cone | three cells during one of his glances | 3 s glance | |
| 8 | Bar, first stool | Paul looking at the stools | freeze beside a stool while he looks | stop up to about 5 s | none: without the stools no schedule |
| 9 | Bar, second stool | Paul | hop 2 m during his glance, freeze again | about 2.5 s | |
| 10 | Dining room, front door (closed leaf) | none | open it and go | free | |
| 11 | Hall, doormat | none | reach the doormat | free | |

**Plan** (o Odile, h Hugo, p Paul, `%` bar stools):

```
+---------------+-----------------------------------+-----------+
|               |            W           W          |           |
|               |                                   |           |
|                      o                            |           |
|               |                                   |           |
|               |                C O                            |
|               |                                   |           |
|               |                                   |  o        |
|               +---------------+-------------------+           |
|      C H      |               |                   |    S B    |
|               |               |                   |           |
|               |  W            |                   |           |
|               |               |                   |           |
|            S  |      B O      |        B U        |p          |
|               |               |                   |           |
|               |               |                   |           |
+---------------+---+---- ------+---- ------+-------+-------- --+
|                   |                       |                   |
|                   |                       |                   |
|                   |                       |                   |
|                   |                       |                   |
|                   |                       |                   |
|                   |                       |                   |
|                   |        #              |                   |
|                   |                       |                   |
|        S O        |          L I          |        S L        |
|                   |                       |                   |
|                                                               |
|                   |                       |                   |
|                   |              h        |                   |
|                   |                       |                   |
|                   |                       |                   |
+---- --------------+---+-------------------+-------------------+
|                       |                   |                   |
|                       |                   |                   |
|            p          |                   |                   |
|                       |                   |                   |
|                                           |                   |
|                       |                   |                   |
|                       |                   |                   |
|                       |                   |                   |
|          K I          |        S M        |        E N        |
|                       |                   |                   |
|    %           %      |                   :                E  |
|                       |                   |                   |
|                       |                   |                   |
|                       |                   |                   |
|                       |                   |                   |
+-----------------------+-------------------+-------------------+
CH=chambre, CO=couloir, SB=salle_de_bain, BO=boudoir, BU=bureau, SO=salon_ouest, LI=bibliotheque, SL=salon, KI=cuisine, SM=salle_a_manger, EN=entree
```

**Audit (Normal): 0 defects.**
- Exit 105.1 s; 123 cell moves.
- Waiting 41 %, 11 pauses (10 mid-route), longest 6.5 s; longest loiter 6.9 s.
- Lesson wardrobe binds (no schedule without hiding). Requires decoy binds (no schedule with the stools explaining
  nothing).
- Budgets: 144 of 160 draw calls, 31 of 33 materials.
- Warnings only: the boudoir and the bureau are dead ends (the boudoir holds a spare wardrobe). Odile walks over the
  hiding cell while the stool is inside the wardrobe (a note: people walk through furniture).

**Difficile.** The solver's bar crossing loiters 17.1 s within 1.5 m (Paul's wider cone), so no designerRouteHard is
written. The Normal route is used as Difficile's stars reference.

## 5. level29 - Moving Day (office chair, the act 4 finale)

**Concept.** The family moves out; boxes everywhere. The office chair crosses the whole house in a U: home office, west
corridor, salon, dining room, kitchen, pantry, east corridor, front hall. Every family threat appears once:
- decoys (the other office chairs in the home office, which Theo never counts);
- the dog (Rex naps in the west corridor and sees only motion);
- the robot (its bumper sweeps the salon's east lane, right across your way);
- Mamie (dozing in the salon, glancing around);
- a tidy watcher on the last corridor (Lea).

Every stop of the office chair glides for 0.4 s and counts as motion, so stops must happen out of sight too.

**Inhabitants and routines.**
- *Theo* (dreamer): works at his desk in the home office from the first second, facing the room. Every 5 s he glances
  north, holding 1.4 s.
- *Lea* (tidy, never fooled by decoys): leaves the office at once and stands in the east corridor looking east toward
  the front hall. She glances +-80 deg (hold 3 s, every 7 s).
- *Mamie* (granny): leaves the office at 3 s and dozes in the salon armchair facing south, glancing +-80 deg.
- *Rex* (dog): naps at the west end of the corridor, asleep 4 s, awake 2 s, facing east.
- *Robot*: back and forth along the salon's east lane (2.5 m, 12.5 s loop), past the dining-room door.

**Beat sheet.**

| # | Step | Threat | Intended action | Window | Alternative |
|---|---|---|---|---|---|
| 1 | Desk (spawn) | Theo watching the room | wait in place: you are where you belong | spawn wait | |
| 2 | First hop | Theo | two cells during his glance, freeze beside an office chair | 1.4 s glance | none: without the chairs no schedule |
| 3 | Second hop | Theo | two cells to the next office chair | next glance | |
| 4 | To the office door | Theo | four cells out of his cone | next glance | |
| 5 | West corridor | Rex awake, facing east | move only while he naps; boxes line the corridor | 4 s nap | |
| 6 | Salon door | Mamie's glance east | enter while she looks away | most of her cycle | |
| 7 | Salon east lane | the robot's bumper (0.78 m) | cross the lane while the robot is at the far end | about half its 12.5 s loop | |
| 8 | Dining room, kitchen | none | a breather | free | |
| 9 | Pantry to the east corridor | Lea looking east | move during her glances; the pantry door is the pocket | 3 s glance | the kitchen door (longer exposure) |
| 10 | Front hall, doormat | Lea's corridor watch behind you | through the hall door at the far end, to the doormat | 3 s glance | |

**Plan** (t Theo, l Lea, m Mamie, d Rex, `@` robot loop ends, `%` decoy office chairs):

```
+-------------------+---------------+-----------+-------------------+-------------------+
|                   |               |           |                   |                   |
|                   |               |           |                   |                   |
|                   |               |           |                   |                E  |
|                   |               |           |                   |                   |
|    S              |               |           |                   |                   |
|                   |               |           |                   |                   |
|        %       t  |               |           |                   |                   |
|                   |               |           |                   |                   |
|  %     B U        |      C H      |    S B    |        C T        |        E N        |
|                   |               |           |                   |                   |
|                   |               |           |                   |                   |
|                   |               |           |                   |                   |
|          m        |               |           |                   |                   |
|                   |               |           |                   |                   |
|                   |               |           |                   |                   |
+-------------- ----+-------- ------+---- --+---+-------- ----------+---------------- --+
|                                           |                                           |
|                                           |                                           |
|                                           |                                           |
|                                           |                                           |
|    d               C W                    |      l             C E                    |
|                                           |                                           |
|                                           |                                           |
+---------------------------- --+-----------+-----------+---------- --------+---- ------+
|                               |                       |                   |           |
|                               |                       |                   |           |
|                               |                       |                   |           |
|                               |                       |                   |           |
|    m                          |                       |                   |           |
|                               |                       |                   |           |
|                               |                       |                   |           |
|                               |                       |                   |           |
|                               |                       |                   |           |
|                               |                       |                   |           |
|                               |                       |                   |          #|
|                               |                       |                   |           |
|                            @  |                       |                   |           |
|                               |                       |                   |           |
|              S L              |          S M                   K I        |    P A    |
|                               |                       |                   |           |
|                               |                       |                   |           |
|                               |                       |                   |           |
|                                                       |                   |           |
|                               |                       |                   |           |
|                               |                       |                               |
|                               |                       |                   |           |
|                            @  |                       |                   |           |
|                               |                       |                   |           |
|                               |                       |                   |           |
|                               |                       |                   |           |
|                               |                       |#                  |           |
+-------------------------------+-----------------------+-------------------+-----------+
BU=bureau, CH=chambre, SB=salle_de_bain, CT=chambre_theo, EN=entree, CW=couloir_ouest, CE=couloir_est, SL=salon, SM=salle_a_manger, KI=cuisine, PA=office
```

**Audit (Normal): 0 defects.**
- Exit 43.0 s; 85 cell moves.
- Waiting 27 %, 4 pauses (3 mid-route), longest 3.2 s.
- Requires decoy binds (no schedule with the office chairs explaining nothing). The route passes 0.92 m from the
  robot.
- Budgets: 142 of 160 draw calls, 30 of 33 materials.
- Warnings only: the parents' bedroom, the bathroom and Theo's room are dead ends.

**Difficile.** The strict solver's schedule loiters 51 s in the west corridor (Rex's wider dark cone), and Theo's fine replay sees one step, so no designerRouteHard is written. The Normal route is used as Difficile's stars reference. (An earlier version with a corridor-to-dining-room shortcut passed Difficile but skipped the robot and the salon entirely; the finale keeps the robot crossing.)

## 6. Integration

- `Assets/Resources/Levels/levels.json`: level26 to level29 appended at the end of "levels"; act 4 added
  (`{ "from": 20, "nameKey": "act4.name" }`); rev 5 and "previous" unchanged.
- `Assets/Scripts/Core/Strings.cs`: `act4.name` plus `level26..29.name` and `.hint` in both languages (en, fr).
  Hints name the threats with the data's names, never the route. They use `{action}` only for the lamp switch, the
  "tu" register, and no em-dash.
- **Level select:** no code change is needed.
  - 24 cards fill the existing grid of 6 columns x 4 rows exactly (a 25th card would add a 5th row).
  - Act tags come from the manifest.
  - The stars total and the progress line are computed from the card count (now 72 stars).
- **Tests edited:**
  - `LevelDataM2Tests`: PlayOrder plus the 4 ids, ActStarts { 0, 7, 16, 20 }, "four acts".
  - `StarsTests`: 72 stars; the test is renamed `..._And72Stars`.
  - `ProbeTestsM5Levels`: V2LevelCount 24.
  - `ProbeTestsStars`: 66 changed to 72 (this one was already stale at rev 5).
- **Budgets** (Android): every house stays at or under 149 of 160 draw calls and 33 of 33 materials. The 120 draw call
  figure applies to levels under 5 rooms; houses get 160.
- **Compile check:** `OutOfSight.Editor.Builder.SetupAndCompile` gives 0 "error CS" (`Build/hardlevels_compile.log`).
- **Audit logs:**
  - `Build/hardlevels.log` and `Build/hardlevels.json`: the final run, `-writeRoutes`, Normal and Difficile.
  - `Build/hardlevels_l29.log`: level29's final routes.
  - `Build/hardlevels_r*.log`: the iterations.
- **Sources:** `Build/hardlevels/` keeps the variant files used during the iterations, and `Build/hardlevels/tools/` the
  generators: `lvlib.py` (rooms on the grid, doors, props, pre-check), `gen26.py` to `gen29.py` (one per level),
  `plan.py` (the ASCII plans of this document) and `finalize.py` (copies a variant into Assets with lesson, requires
  and pace). They are not part of the game; the level files in Assets are the source of truth.

## 7. Known limits and follow-ups

- **Difficile:** none of the four has a strict-solver schedule at Difficile, so no designerRouteHard is written and the
  stars fall back to the Normal route. The 1.15 range factor is the usual culprit (LEVEL_REVIEW 1.7). A playtest
  should judge whether Difficile is fair on them.
- **Length:** the solver exits are 43-105 s. A first clear takes several times longer (multiple timed gates, wardrobe
  and decoy beats). level27 and level29 are the shortest on the solver clock because the chair and the office chair
  are fast. Their windows are the shortest of the act (1.4 to 3 s).
- **Dead rooms:** a few side rooms per house are maze dead ends with no post (warnings, not defects without
  `-strictRooms`).
- **Not checked here:** PlayMode suites were not run (as asked). Step40_FullPlaythrough, the rush probe and the
  last-level helpers (`WinCurrentLevel` now loads level29) include the new cards automatically.

## 8. How to play them on PC

After the user rebuilds the player:

```
Build/Play/OutOfSight.exe --level level26
Build/Play/OutOfSight.exe --level level27
Build/Play/OutOfSight.exe --level level28
Build/Play/OutOfSight.exe --level level29
```

In the game they are cards 21 to 24 of the level select, under the act 4 tag. They unlock in order after level24.
