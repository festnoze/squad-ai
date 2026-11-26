# HUD: gauge danger animation and the open eye (2026-11-20)

Two changes to the bottom band of the HUD: what the creak ("Grincement") and suspicion ("Soupçon") gauges show in
their high zone, and the open eye in the middle. Everything is still drawn in code (no texture asset): `GaugeArt.cs`
and `ProceduralArt.cs` draw the sprites once at startup, `GaugeFx.cs` animates the gauges, `Hud.cs` drives both.

## Gauges: the danger animation replaces the red flash

Before: during the creak warning the creak fill alternated between hot red and pale cream three times a second, and
every gauge near its limit pulsed its glow and its scale quickly. It read as an error blink.

Now a gauge is "in danger" once its drawn fill is past its threshold marker (or the creak warning is on, or the
balance gauge is red). The fill keeps its level colour on every frame (never a flash) and `GaugeFx` adds four layers,
eased in over 0.2 s and out over 0.4 s (`Heat`):

1. **Bloom**: a wide, very soft halo of the fill's colour behind the capsule (`GaugeArt.Bloom`, nine sliced), breathing
   at 0.85 Hz in alpha and 5 % in size; the existing glow and a 1.2 % scale of the capsule breathe with it.
2. **Laser sheen**: a slanted light band (`GaugeArt.Sheen`) sweeps from the track's left end to the fill's head in
   0.65 s, then rests 0.65 s. It is a horizontally Filled image whose fill amount stops it exactly at the fill's
   straight edge (no mask, no extra material).
3. **Hot spot**: a thin bright core in an oval bloom (`GaugeArt.Flare`) on the fill's leading edge, flickering, and
   flaring when the sheen arrives.
4. **Burst**: crossing into the danger zone sends a shockwave ring (`GaugeArt.Ring`) and 12 spark streaks
   (`GaugeArt.Spark`, rotated along their flight, gravity and drag) from the head. The creak itself (the full creak
   gauge emptying at once) bursts all 14 sparks where the fill stood, with the existing shake.

Cost: UI images only, the default UI material, 18 extra images per gauge created up front. Idle layers and dead
sparks are made transparent and culled by their CanvasRenderer (`cullTransparentMesh`); spark state lives in fixed
arrays with an xorshift generator, so no frame allocates. The gauge canvases were already rebuilt every frame.

### How the look was chosen

Four prototypes were compared frame by frame (20 frames at 15 fps, at 70, 90 and 100 %) against the old flash:
bloom alone, laser (sheen and hot spot), embers (ring and burst, plus embers rising off the fill while in danger) and
the combination. Bloom alone was soft but too static to say "now"; the laser alone was the most readable motion;
continuous embers were busy over a long suspicion danger zone. Kept: the combination without the continuous embers,
with the sparks, ring and hot spot pushed to a saturated yellow (pale sparks vanished over the garden lawn).

## The open eye

The closed eye (a cream lid arc with three lashes) is unchanged. The open eyes are redrawn in its line: the same cream
ink, the same 0.1 lid stroke and 0.07 lashes, an almond exactly as wide as the closed arc. A dark almond between a
cream upper and lower lid that meet in round corners, a two tone amber iris, a round pupil and two glints, and the
closed eye's three lashes turned up on the upper lid.

- Calm: half open, "?" badge. Alarm: wide open, small pupil, longer splayed lashes, two shock strokes beside each
  corner, "!" badge. Dog: wide open under the ears, no lashes (they touched the ears).
- The badges moved beside the outer lash (they were clipped at the sprite's top) and got the glyph ink outline; the
  "!" is cream, the red one vanished on the red alarm backdrop.
- Blink: a change between closed and open shows `ProceduralArt.EyeHalf` (lids nearly shut, the iris peeking) for
  0.06 s, then the new eye pops in from 114 % (an opening eye) or settles from a slight squash (a closing one) over
  0.16 s. A change between two open eyes only pops. `Hud.EyeSprite` is the new state's sprite at once.

The eye was designed offline first with a numpy prototype that mirrors `ProceduralArt.EyeShape` (not kept in the repo).

## Tests and shots

`ProbeTestsBars.Step75b_DangerAnimationAndEyeBlink` pauses the game, steps the HUD clock 1/30 s per frame
(`Hud.ShotStep`) and checks: no heat below the marker, sparks at once on crossing, full heat within half a second, one
fill colour on every frame at a constant level, a burst on the creak, the blink frame showing then hiding. It writes
frame sequences of the band at 70, 90 and 100 % (1920x1080 and 2400x1080), the creak burst and every eye state to
`$OUTOFSIGHT_SHOTS/hud`, else `Build/shots/hud` (ignored by git, never under docs).
