# L9LONG: card 9 (level9, "The Robot") longer and less obvious (2026-11-24)

User request: level9 was a straight line along the north wall behind the vacuum. Make it a bit longer and more complex,
nothing extreme.

## Changes (Assets/Resources/Levels/level9.json)

- Door chambre -> salon moved from z 8.25 to z 5.25 (south end of the chambre's east wall): the player enters the salon
  west of Claire, 3.5 m from her, and must time her west glance.
- Door salon -> entree moved from z 8.25 to z 6.25: the way out is now down the east side of the salon, toward Claire's
  east glance, instead of straight on from the north corridor.
- The robot runs a lap of the salon instead of a back and forth on the north wall: (5.25, 4.25) -> (5.25, 8.25) ->
  (11.25, 8.25) -> (11.25, 4.25), 20 m at 0.45 m/s. Following it: up the west side, along the north wall, down the east
  side.
- New free-standing "Bibliotheque" (bookshelf, 1.2 x 2.0 x 0.35, yaw 90) at (10.0, 7.3): it hides the east side from
  Claire down to z 6.7, so the last metre to the door is exposed (wait for her east glance to end).
- Armoire moved from x 3.6 to x 2.2 along the chambre's south wall, out of the new doorway.

## Not done

- No audit, no test (user runs them). designerRoute / designerRouteHard are stale: run
  `LevelAudit.RunBatch -auditLevels level9 -skipFixtures -difficulty normal,difficile -writeRoutes`.
- Pace (minShare 0.22 to 0.45, minPauses 4, maxPause 6) not re-checked: the audit says if the new route fits.
