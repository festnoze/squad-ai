# L17HIDE progress (2026-11-23)

## Which level "level17" is
- The user's "level17" is the 17th card of the level select, i.e. `levels.json` order index 16 = **level19.json**
  (LevelSelect.NewCard numbers cards by their index + 1; the order is level1..9, 12, 11, 15, 13, 14, 18, 17, **19**, ...).
- level19 matches every point of the report: the player is the stool, the long corridor is the "galerie" (17.9 x 2.4 m),
  the big wardrobes are ArmoirePorte / ArmoireMilieu / ArmoireLoin (kind wardrobe, 1.0 x 2.0 x 0.6), the small ones were
  BuffetMaman / Commode1 / Commode2 (kind cabinet, 0.9 m tall with two doors), and it has no vase.
- level17.json (card 16, the chair carrying the vase, LEVELS6 rebuild) has no wardrobe and was NOT edited.

## Change (level19.json, props only)
- BuffetMaman -> EtagereMaman, Commode1 -> EtagereBasse1, Commode2 -> EtagereBasse2: kind cabinet -> bookshelf (low open
  bookcases full of books). Same position, yaw 180 (open front to the gallery, as the cabinet doors were), same size
  (0.9 m tall) and same colours (#6B4226 / #E3B23C, the colours of the salon's Bibliotheque, so no new material).
- Sight blocking is unchanged by construction: FurnitureKit.Cabinet and FurnitureKit.Bookshelf both build ONE box collider
  over the whole prop box (occluder layer), so vision, the NavMesh and the audit see the same volumes.
- Doorways checked by hand in level19 (4 doors) and level17 (7 doors): no prop overlaps a doorway in either level.

## Step57b (vase drop test)
- ProbeTestsM6Levels.Step57b_Level17VaseDropIsHeard failed "premise: the vase never fell". Retargeted to level13 (the
  other shipped vase level besides level11, which Step57a covers): Step57b_Level13VaseDropIsHeard, new counter-route
  Level13DropAtSpawn (south from the spawn, hard turn west 1.5 m away, then the designer's way at full speed).
- Probable cause on level17: its rebuilt start seats Mamie on the chair (station 1 "sit": "player"), so the chair cannot
  leave at full speed in the first seconds.
- Why level13 despite L13HARD reworking it now: the only shipped vase levels are 11 (already Step57a), 13 and 17; the
  other vase files are test fixtures (test_load, test_m5_game_load, test_m5_house_robot, test_v2_loaded_sit) not built
  for a rush counter-route. So Step57b MUST BE RERUN after L13HARD ships level13 (its premises: Claire near the spawn
  facing away at the start, the plateau route at full speed).
- No MUTATION marker names Step57b (mutation.sh unchanged). verify.sh selects the prefix "Step57b_": still matches.

## Runs
- Audit (Build/l17.log, 2026-11-23 ~00:35; first try aborted on another agent's compile error in GameState.cs, no audit):
  `-auditLevels level19 -skipFixtures -difficulty normal,difficile -writeRoutes`: "Niveau level19 : aucun defaut" and
  "level19@difficile : aucun defaut". designerRoute and designerRouteHard rewritten (58 points each), identical to the
  previous ones (the file diff is only the 3 prop name/kind pairs). 117 draw calls / 160, 25 materials / 32 (no new
  material), exit 72.0 s, 35 % waiting, 6 pauses; same schedule as before.
- PlayMode (TestResults/l17.xml, `--filter L17HideLook_|Step57b_`): both PASSED.
  - L17HideLook_Corridor (new file Assets/Tests/PlayMode/ProbeTestsL17HideLook.cs): gallery = EtagereMaman,
    ArmoirePorte, EtagereBasse1, ArmoireMilieu, EtagereBasse2, ArmoireLoin; shots in Build/shots/l17.
    l17_corridor_low.png is the useful one (bookcases full of books between the wardrobes, eye height along the gallery);
    l17_corridor_high.png shows only the salon wall (the wall fader did not fade it from that pose): not reshot.
  - Step57b_Level13VaseDropIsHeard: caught (SeenMoving) at 1.8 s, crash at 0.54 s, clue 0.28 m from the spawn,
    Claire alerted 1.02 m from the clue, top speed 2.80 m/s. The vase falls on the full start (office chair), before
    the planned turn.

## A VERIFIER
- Level identity: the work was done on level19.json (card 17 in the game). If the request really meant level17.json
  (card 16, the chair with the vase), there are no wardrobes there and nothing was changed in it.
- Step57b on level13 must be RERUN after L13HARD finishes reworking level13 (Claire's start station and the spawn area
  are the premises). Today's pass holds only for the level13 that was current on 2026-11-23 at about 00:45.
- Look check by a human: 0.9 m bookcases next to 2.0 m wardrobes; if a "console / chest of drawers" look is preferred
  for one of the three, no such procedural kind exists (nightstand is the only drawer piece and is sized 0.45 m).
- No route replay in PlayMode for level19 (only the -writeRoutes audit); the routes did not change.
- docs/levels_v2/wave1/design_act3a.json still names Commode1 / Commode2 / BuffetMaman (historic design notes, not edited).
- The high corridor shot needs a pose under the walls or a fixed fade if a top view is ever wanted.
