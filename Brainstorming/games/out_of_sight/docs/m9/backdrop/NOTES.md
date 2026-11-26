# Garden backdrop: iteration notes

The 2026-11-20 round (wide panorama, sky ceiling, higher look) is at the end; the 2026-11-19 notes below it are kept as
they were (their sizes and shots predate it).

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

## 2026-11-20: wide panorama, sky ceiling, higher look

Product owner request of 2026-11-20: replace the garden picture by `garden_open_horizontal_tile_wide.png`, close the ring
with a round ceiling showing `sky_disc_sun_glow.png`, and let the camera look higher now that there is a sky. Code:
`GardenBackdrop.cs` (ring, ceiling), `OrbitCamera.cs` (`ArmPitchFor`), `Tuning.PitchMin` / `OrbitArmPitchMin` /
`OrbitArmPitchEase`; pictures: `tools/assets/make_garden_backdrop.py`; tests: `ProbeTestsM9Backdrop` (Step95a/b/c/z).
Shots now go to `Build/shots/backdrop/` (ignored by git), never under docs/.

### Design

- Garden source: 5016 x 1254, last column equal to the first (wraps once it goes), four different garden stretches.
  Derived copy `Assets/Resources/GardenBackdrop.png`, 4096 x 1024 (aspect exactly 4), the same pipeline as before (three
  copies resampled side by side, middle kept; haze; each lawn row's mean moved to the grass plane's look; the top 6 % made
  one exact colour). The top colour is now (130, 191, 253): the sky disc's own rim colour, which the panorama's top rows
  already show to within 2 levels.
- Ring: the picture keeps its aspect with a fixed ratio to the radius (`PictureRatio` 0.5): repeats = round(circumference /
  (0.5 R x 4)) = 3 on every level (twelve garden stretches round the ring, never the same one twice in a view), picture
  height = circumference / (3 x 4) = 0.52 R, about the 2026-11-19 heights (0.52 to 0.57 R). The ring itself is
  max(picture + the ceiling's rounded rim (2.5 m), the camera's highest eye + head room): its straight wall always holds the
  whole picture, and where it is taller the band above the picture shows its uniform top sky (the texture is clamped in V,
  the wall's top UV is wall height / picture height). Sizes (ceiling height from the foot): level1 R 15.0 H 10.3 (picture
  7.8), level12 R 19.2 H 12.5 (10.0), level22 R 32.7 H 19.6 (17.1), title house R 20.1 H 12.9 (10.5).
- Ceiling: a flat disc whose rim rounds down onto the wall's top in a quarter circle of 2.5 m (GardenBackdrop.Fillet, 6
  facets; 7 rings of 73 vertices and a centre), its lowest ring the ring's own 72 top vertices with the wall's own normals
  (same angles, radius and height: no gap, no crease), every face toward the inside, no collider, no shadow, a child of the
  ring. The sky picture is projected from below over the ring's diameter once (planar UVs from the horizontal position:
  exact on the flat part, no stretch; the rounded rim shows the picture's outer band). Same material as the ring and the windows (the cached
  unlit pane material) with its own property block: no new material, one more draw call (level21 151/160).
- Sky picture `Assets/Resources/GardenSky.png`, 1024 x 1024: the source's disc (radius 1000 px) cropped to fill the
  square, over the rim colour (no transparent corner bleeds in when filtered). The sun is moved off centre by a disc
  automorphism (Moebius map z to (z - c) / (1 - conj(c) z), c = 0.45 toward image right): conformal, so the sun and the
  wisps stay round, and the rim stays the rim. The ceiling turns image right toward the azimuth the scene's directional
  light comes from (`GardenBackdrop.SunAzimuth`: Main's sun, else its 2026-11-20 angles), so seen from inside the glow
  stands roughly where the light comes from (from the house centre the sun is at about 44 degrees, the light's own
  elevation). Each ring of the source beyond 0.70 of the radius has its median moved onto a smooth ramp to the rim colour
  (the source dips 1.5 levels near 0.85 before rising toward the glow, which the grade drew as a faint dark circle), and
  beyond 0.92 the disc is exactly the rim colour: the ring's top, the band above the picture and the ceiling's rim are one
  colour, and the seam does not show.
- Camera: `Pitch` is now the view's pitch, from `Tuning.PitchMin` -10 (10 degrees above the horizon, was 15 below it) to
  75. The arm follows it down to `Tuning.OrbitArmPitchMin` 5 only, easing onto it over 5 degrees either side (a quadratic
  blend, no kink); below, the camera stays at its lowest point (about 1.2 to 1.5 m above the floor on the small levels)
  and only the view tilts up, so at the sky look the top of the screen reaches 37.5 degrees above the horizon (12.5
  before). The furniture then sits in the lower third of the frame (fully in frame at the default and the longest zoom;
  its lower part leaves the frame only at the shortest zoom). Default pitch, zoom, the title tour and the showcase are
  unchanged. The ring's horizontal reach uses the arm's lowest pitch (cos 5 instead of cos 15: radii up to 0.5 m larger);
  its height still comes from the highest pitch, so the camera stays inside the closed volume at every pose. Mouse, right
  stick and touch all clamp to the same range; the far clip (2 R and the height) holds the ceiling too.

### Iterations (shots in the session scratchpad, not in the repository)

- v5: the new picture and the ceiling as above, the lawn target of v3 (90, 127, 68). Seen: the horizon closes on the
  wide garden, the ceiling and its glow show above the walls when looking up, no seam between the ring and the ceiling,
  no void at any pose. Defects: the grass plane by the ring's foot now draws (84, 127, 22) and the painted lawn (86, 122,
  47): a bluish band at the foot; and, contrast-stretched, a faint dark circle in the sky (the source's dip near 0.85 of
  its radius, 1 to 2 levels).
- v6: lawn target (88, 132, 40), the ring medians ramp. The circle is gone; the lawn drew (84, 127, 11), a touch yellow.
- v7: lawn target (88, 132, 50): the painted lawn (83, 126, 19) meets the plane (84, 127, 22) on level1. From close (the
  camera a few metres from the ring on level22) a light band showed under the flower beds: the lawn's brightest top rows
  were only half shifted.
- v8: the lawn shifted fully up to 11.5 % of the picture, fading out at 14 %. The light band is gone. New defect, seen on
  level9 and level1 when looking up at the sky away from the sun: a soft dark arc all round the sky at the junction of the
  ring and the flat ceiling (up to 9 levels darker over 10 to 20 px at 1280 x 720). Cause: URP's Unlit shader applies the
  screen space ambient occlusion too (opaque surfaces), and the right angle between the wall and the ceiling is a concave
  crease, which the 0.3 m occlusion darkened.
- v9 (final): the ceiling's rim rounds down onto the wall in a quarter circle of 2.5 m (the wall ends 2.5 m lower, the
  ceiling height grows by 2.5 m where the picture set it). The arc is gone on every level and every view; the sky reads as
  one continuous dome from the garden's tree line to the sun.

### Checks (2026-11-20)

- ProbeTestsM9Backdrop: Step95a (15000 poses: every level and the title house, the sky look, the arm's floor, 15, the
  default and the highest pitch; the rounded rim never reaches the camera space), Step95b (ring and ceiling built, no gap,
  no crease, faces inward, same material, the view pitch and the arm checked at every pitch, no magenta void pixel in 96
  renders at the sky look and the highest pitch, the longest and the shortest zoom), Step95c (the garden's top rows and the
  sky's rim exactly (130, 191, 253), the garden wraps, the sun on the right half), Step95z (shots): pass.
- LevelAudit, all 24 levels, normal and difficile (-skipFixtures, no -writeRoutes): 48 runs, 0 defects; materials
  unchanged, one more draw call per level for the ceiling (level21 151/160, level22 146/160).
- Also passing: Step39h, Step39i, Step51a, Step63a_TouchDragOrbitsCamera, Step90a/b/c/z, Step91z (near walls and doors;
  their shots moved out of docs/), Step26_TitlePausesAndPlayStartsLevel1, Step26_XRayShowsWhereAHiddenInhabitantLooks,
  Step26_MarkersStayClearOfTheHud, Step36o, Step70b/c/e, EditMode CreditsTests and LicenseTests.