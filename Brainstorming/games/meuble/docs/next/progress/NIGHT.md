# NIGHT progress (night preset look pass + Showroom look pass)

## Scope
- Lighting code and presets: Main.cs (night preset), RoomLights.cs (night pools, night light in "other" rooms),
  LampLight.cs (player floor lamp at night). Level json: lighting fields only.
- Out of scope (parallel agents): GRIP (furniture grip, title logo), DOGFACE, CHIN (characters), LEVELS6 (level layouts),
  HUMANAUDIT (LevelAudit.cs). No layout change, no lit zone meaning change (no rule reads any of this).

## State at start (2026-11-22)
- C10 preset existed (moon 0.5, ambient x0.35, white balance -10, RoomLights Bas keeps 1 light/room at night).
- Only level25 carried `"lighting": "night"`. level20 ("Midnight Munchies", LEVELS_V2 4: `"lighting": "night"`) did not.
- The one earlier capture (ProbeTestsNight, Build/shots/night/level20_*_night.png, level20 forced to night) read as a
  blue dusk: pale blue-grey walls, faint warm pools, the lamp's pool a small spot at its foot.

## Changes
- Main.cs: moon 0.5 -> 0.3 (colour a touch cooler, shadow strength 0.55), ambient factor 0.35 -> 0.24, white balance
  -10 -> -12, vignette 0.22 -> 0.3 at night (day value put back exactly: new DayVignette constant, Vignette kept as a field).
- RoomLights.cs: NightPool 1.45 (every room light built 1.45x stronger at night, MUTATION:NIGHT_POOL); a room of type
  "other" gets one dim warm sconce at night (NightLightMood, MUTATION:NIGHT_OTHER_ROOM): level25's "reserve" (the spawn
  room) was lit by the moon alone. Same tiers, same draw call budget (warm glow family already in level25, housing merged
  into the wall cap).
- LampLight.cs: night intensity 1.6 -> 2.7 and range 4 -> 5.5 (NightIntensity / NightRange, MUTATION:NIGHT_LAMP),
  followed in LateUpdate when the preset changes. RangeFactor (the rule) untouched.
- level25.json: magasin `"lightWall": "-z"` (lighting field only): the hall's sconce pair moves from the north wall
  (automatic placement) to the south wall, so the night pools land on the tables, the display chairs and the exit side
  where Marcel's rounds and the "freeze where a chair belongs" decisions happen (compare level25_high_house.png, north,
  with level25_high_v_southwall_house.png, south). On Moyen the kept light is the west one (x 6.5, near TableOuest).
- level20.json: added `"lighting": "night"` (line 7, lighting field only). **LEVELS6: keep this key when you copy a
  variant over level20.json** (gen20.py variants are built from level20_r8a, which lacks it).
- New look test Assets/Tests/PlayMode/ProbeTestsNightLook.cs (NightLook_a..d: level20 / level25 x Haut / Moyen),
  shots and logs in Build/shots/night.

## Unity runs (max 3, all used)
- r1, r2: died at compile on other agents' mid-edits (ProbeTestsChinLook.cs missing URP reference, then
  LevelAudit.cs `inner.Mask = mask` int -> byte). Nothing of mine ran.
- r3 (Build/night_r3.log, TestResults/night_r3.xml): NightLook_a (level20 Haut) and NightLook_c (level25 Haut) PASS;
  NightLook_b / _d (Moyen) FAILED at the first check: Main.LookProblems() wants SSAO, which Mobile_Renderer never has.
  Test bug, fixed statically after the run (the SSAO line is ignored on Moyen/Bas). So NO mobile capture exists yet.

## Findings from r3 (Haut, Build/shots/night/*_high_*, logs level20_high_log.txt / level25_high_log.txt)
- level20: start view luma day 0.383 -> night 0.225 (no HUD, same region as ProbeTestsNight: floor 0.11 holds); house
  view 0.459 -> 0.154. Lamp off: start view 0.225 -> 0.115 (ratio 0.51): the lamp clearly matters. HUD (intro panel,
  gauges, hints) fully readable over the night frame. Cones bright and crisp (unlit shader). Walls read dark, the warm
  pools carry the rooms.
- level25: start view day 0.436 -> night 0.201 (the reserve's new night sconce pools under the red chair: the target
  reads at once, 5926 clearly red pixels in the target view). House: the hall is dark blue, furniture reads as dark
  silhouettes on the paler floor, cones clear.
- Tuning variants of the same build (moon/ambient x0.75 and x1.35/1.3, pools x1.35): darker made the hall's chairs
  merge with the floor; brighter went back to dusk; pools x1.35 changed little. The shipped values (moon 0.3, ambient
  x0.24, NightPool 1.45) are kept as captured.
- The south-wall variant was rendered in r3 by forcing the field at runtime (same code path as the authored field).

## A VERIFIER
- Mobile (Moyen) captures of level20 and level25 at night: run `--filter NightLook_b|NightLook_d` once (the test is
  fixed). Expect one light per room, hard shadows; check the hall's single west pool is enough and the cones read.
- level25 with the authored `"lightWall": "-z"` from the file (r3 forced it at runtime): rerun NightLook_c; the
  comparison shot is now level25_high_v_otherwall_* (automatic north placement).
- NightLook target view after the camera fix (r3's view of the level25 chair looked through the reserve wall's frame).
- ProbeTestsNight (Night_a / Night_b) not rerun with the new values: Night_a floor 0.11 should hold (r3 measured 0.225
  on level20's start), Night_b reads Main.NightAmbientFactor so it follows the new 0.24.
- ProbeTestsM8Lights / LitZone suites not run (rule: no suites); night-only changes, day paths untouched by design.
- level20.json `"lighting": "night"` must survive LEVELS6's variant copy (see above).
- Draw call / material budget of level25 at night: the reserve's sconce uses the warm glow family already present and
  merges its housing into the wall cap (expected +0 draw calls); confirm in the next LevelAudit budget line.
