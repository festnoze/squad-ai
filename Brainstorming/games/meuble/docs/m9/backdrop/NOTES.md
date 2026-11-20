# Garden backdrop: iteration notes

Product owner request of 2026-11-19: a ring round every house (and the title house) showing
`Assets/Art/Environment/garden_open_horizontal_tile.png` on its inside, so the horizon closes on a garden instead of grass
running into the dark void. Code: `Assets/Scripts/Runtime/GardenBackdrop.cs`; picture: `tools/assets/make_garden_backdrop.py`
into `Assets/Resources/GardenBackdrop.png`; tests and shots: `Assets/Tests/PlayMode/ProbeTestsM9Backdrop.cs` (Step95a/b/z).

## Design

- Source: 1254 x 1254, its last column equals its first (mean difference 0.0): it wraps once that column goes. No blend
  needed; the derived copy only drops it, resamples to 1024 x 1024 with the wrap kept (three copies side by side, the middle
  one kept) and makes the top of the sky one exact colour (127, 190, 253), which is also the game camera's clear colour.
- Ring: centred on the interior centre. Radius = farthest focus point (interior corners, props, exit zone, + 1.5 m) +
  longest horizontal arm (`OrbitCamera.MaxDistanceFor` x cos `PitchMin`) + 2.5 m. Height >= highest eye (highest floor + half
  the body + `CameraTargetHeight` + arm x sin `PitchMax`) + 1.5 m, so the camera never sees over it. Repeats =
  floor(circumference / (wanted height x aspect)), then height = circumference / (repeats x aspect): the aspect is exact and
  the height never below the wanted one.
- Camera: `OrbitCamera.Fence` (the level's ring) shortens the arm at the fence (never in play: Step95a proves the unclamped
  pose is always inside) and raises the far clip to hold the whole ring.
- Budget: one renderer, one slot, the windows' own unlit material with a property block (no new material; level16 is at
  24/24 materials). No collider, Default layer, no shadows.

## Iterations

### v1 (shots `v1_*.png`)

Picture: wrap kept, sky top uniform, no other change. Rings: level1 R 14.8 m H 8.5 m x11, level12 R 19.0 H 9.9 x12, level22
(largest) R 32.2 H 16.9 x12, title house R 19.8 H 10.4 x12; the camera always at least 4.0 m inside, far clip at most 69 m
(the game camera keeps 80).

Seen: the horizon closes on the garden at every angle, no seam at the wrap, no stretching, the sky above the ring is the
camera's clear colour with no line; the camera never sees over the top (the ring is taller than its highest eye), so the
ring never reads as a cardboard fence standing in a field. The round enclosure is felt at the low pitch near the ring (its
foot bends toward the screen edges), which reads as a round garden. Defect: the painted lawn strip drew lighter and
yellower than the grass plane next to it ((116, 157, 0) against (96, 137, 40) on screen): a visible band at the foot.
Repetition (x11 to x12 copies) shows the same two trees every 30 degrees; judged acceptable at these distances.

### v2 (shots `v2_*.png`)

Picture: the lawn strip's mean shifted toward the grass plane's look (grain kept), fading out over the bottom 16 %; a light
aerial haze (3 % at the foot to 14 % at the top, toward a pale sky colour) so the painted garden sits behind the lit house.

Seen: the band is gone on most views, but the very foot still drew darker ((75, 121, 22) against the plane's
(96, 137, 44)): the source's bottom rows are darker than its lawn's mean, and the grade still ate the blue.

### v3 (shots `v3_*.png`, final look)

Picture: each lawn row's mean moved to (90, 127, 68) (full on the bottom 5 %, fading out at 16 %), the grass plane's look
read back through the grade. Seen: the painted lawn now continues the grass plane (no band, no dark foot) on small and
large houses, at the lowest pitch and the longest zoom; the haze keeps the garden behind the house; no seam, no clipping,
the camera always inside. Title menu: the title tour runs inside the title house under its ceiling, so the menu shot
(`menu_title_1920x1080.png`, from ProbeTestsTitleChair) is unchanged; the title house's own ring is built and checked
(Step95b) and shown from the game camera in `v4_title_house.png`.

## Checks

- LevelAudit, all 24 levels, normal and difficile (`-skipFixtures`, no `-writeRoutes`): 48 runs, 0 defects. Materials
  unchanged on every level (level16 stays 24/24), one more draw call each (largest: level21, 150/160).
- Step95a (9000 poses, every level and the title house), Step95b, Step95z: pass.
- Also passing with the backdrop: Step39h, Step39i, Step36o, Step22d, Step22e, Step61a, Step74a (title chair, menu shots),
  Step72a and the EditMode credits tests, Step26_*, Step51a, Step63a_*, Lights_c (vision unchanged). Step22c failed once on
  level21 ("only 55 of 112 Lit slots show a detail", threshold 56): it counts URP Lit slots only and the ring is URP Unlit,
  so it comes from the level's other content being edited in parallel, not from the backdrop.
