# STARSANIM: hero stars with a mobile style reveal on the level end screen (2026-11-26)

User request: "the stars in the CENTER of the screen, with a quick animation like many mobile games: 3 empty stars
appear, then fill up one by one, each with a sound and a zoom/explosion effect". How many stars a run earns is
unchanged (`Stars.Count`, `StarsTests`, `RecordLine`): only how they are shown changed. The fail panel is untouched.

## 1. Layout per mode

One centred column on the win panel and on the end screen, the same in the PC and the touch layout
(`Assets/Scripts/Runtime/HudWinStars.cs`, `Hud.LayoutWinColumn`). Reference units (1920 x 1080, match 0.5), y from the
screen centre, before the column's lift. Every text box keeps a band of its own (the boxes are 1600 wide and the tests
compare boxes).

| Line | Win panel | End screen | y (box) |
|---|---|---|---|
| Title (150, unchanged size) | DEHORS ! | FIN | 335 (260 to 410) |
| Hero stars: 150, 184 (middle, raised 16), 150; 28 apart; row 540 wide | stars | stars | middle star 156 (row box 64 to 248) |
| "Nouvelles étoiles !" (30, gold, fades in after the last star) | when new | when new | 33 (16 to 50) |
| Row 0 (52) | the time | end.body | -18 (-48 to 12) |
| Row 1 (40) | record line | the time (EndTime) | -75 (-98 to -52) |
| Row 2 (38) | hint (win.action) | record line | -125 (-148 to -102) |
| Row 3 (38) | win.next | hint (win.action) | -175 (-198 to -152) |
| Buttons | PC: the centred row at -300 (top -207), unchanged. Touch: the BIGBUTTONS bottom bar, unchanged | | |

The record line ("Record : 12,3 s" then "Nouveau record !" beside it) is one centred row in both layouts now
(`RecordLine.cs`, `Hud.RecordRowY`): it used to sit under the PC buttons (y -430) and, on touch, left of the time
mirroring the old stars. The old star spot (right of the time, "New stars!" under it) is gone.

The column moves up as a whole (`Hud.ColumnLift`), recomputed when the canvas height, the layout or the safe area changes:

- PC: centred between the top of the screen and the buttons' top, clamped to 0..80: 26 at 21:9 (943 units high),
  32 at 20:9, 60 at 16:9, 75 at 16:10, 80 at 4:3. Gap to the buttons: 35 at 21:9, 69 at 16:9; the title box top stays
  35 (21:9) to 70 (16:9) under the top edge.
- Touch: centred between the top of the screen (under `Screen.safeArea`'s top inset) and the bottom bar's top
  (28 + safe bottom inset + 210 above the bottom edge), never closer than 12 to the bar. With no insets that is +13 at
  every shape (the bar is bottom anchored): column bottom -185 against a bar top of -233.5 at 21:9, -245 at 20:9,
  -302 at 16:9, -385.5 at 4:3. A bottom inset lifts the column by half of it (more if the bar would come closer than 12).
- Widths: the star row is 540 (4:3 canvas: 1663), sparkles fly at most about 250 from a star, every text box as before.

## 2. Animation timeline (unscaled time, `WinStarsView.cs`, values in `Tuning.StarsAnim*`)

| t (s) | 3 stars | 2 stars | 1 star |
|---|---|---|---|
| 0, 0.06, 0.12 | the three empty slots pop in (scale 0 to 1, ease out back, 0.22 s each) | same | same |
| 0.42 | star 1 fills | star 1 fills | star 1 fills |
| 0.82 / 0.72 | star 2 fills | star 2 fills | star 2 ticks (empty) |
| 1.22 / 1.12 / 1.02 | star 3 fills (big finish) | star 3 ticks | star 3 ticks |
| end | 1.87 | 1.77 | 1.67 |

- A fill: the gold star punches in from 1.8x to 1 over 0.32 s (dipping to about 0.92, then back), flashing white to
  gold; a soft glow behind it (0.35 s, 0.7x to 2x of 1.6 star sizes); a ring expanding and fading (0.45 s, 0.5x to 2.1x);
  10 sparkles flying out (0.45 to 0.65 s, drag and a little gravity, spinning, gold, cream and orange); a 0.22 s shake of
  the row (9 units).
- The third star: 14 faster and bigger sparkles, a wider ring (to 2.6x), a stronger shake (15) and a 0.32 s pulse of
  the whole row (+7 %).
- An unearned star stays an empty slot: a small squash (0.24 s) and a soft dull tick.
- "Nouvelles étoiles !" fades in from 0.15 s after the last event (0.3 s).
- The buttons are up and usable from the panel's first frame; keyboard and gamepad focus are as before (Menu principal
  selected on the end screen, Retry on the fail panel; the win panel selects nothing and Enter / gamepad A load the next
  level through GameState).

## 3. Sound

- `Sfx.PlayStarChime(index)`, synthesized at startup like the M2 to M5 cues (no recording added): a glockenspiel bar
  (partials 1, 2, 2.76, 5.40, 8.93 f, decays 4.2 to 40 per second, 2.5 ms attack), normalised to a 0.85 peak.
  Star 1 G5 (784 Hz), star 2 C6 (1046.5 Hz), star 3 a rolled C major chord led by E6 (E6, C6, G6, C7, 0 / 20 / 45 / 80 ms),
  so the three climb G, C, E and the last lands on the chord. 0.9 s clips, the chord 1.4 s.
- `Sfx.PlayStarDull()`: a 0.14 s low wooden "tok" for an empty star (its own hashed noise, so the shared noise
  generator and every jitter drawn after it are unchanged).
- Volumes `Tuning.SfxStarChimeVolume` 0.5, `SfxStarChimeFinalVolume` 0.6, `SfxStarDullVolume` 0.35, times Sfx's mix
  scale (0.485): a little under the win jingle they follow.
- Played as one shots on `Sfx.UiSource` (the menu click's source: chimes overlap, no new AudioSource, so Step27g's
  "only the UI source ignores the pause" still holds). Volume and mute: through `AudioListener.volume` (the options'
  Volume via `SaveStore.ApplyVolume`, 0 under `AudioMute`), like every effect. `LastClip` is never set by them (like
  `PlayUiHover`). Counters for tests: `StarChimesPlayed`, `StarDullsPlayed`, `LastStarChime`, `LastStarChimeVolume`.

## 4. Skip rule and refreshes

- `InputReader.SkipPressed()` (peek, nothing consumed): a left click or a finger landing anywhere, Enter (main or
  keypad), Space or gamepad A, or `InputReader.InjectSkipPress()` (tests). While the reveal plays, the HUD then calls
  `WinStarsView.Complete(true)`: every earned star gold at scale 1, effects gone, and exactly one chime (the highest
  earned star's) on the next frame if that star had not chimed yet; nothing if the press also left the panel (Enter on
  a win loads the next level the same frame: `Hide` drops the owed chime). The same Enter still loads the next level,
  the same tap still presses the button under it: nothing is ever blocked.
- `Hud.CompleteStarsAnimation()`: the same completion, public for tests.
- A menu over the panel (the HUD hidden): the reveal settles silently (`WinStarsView.Silence`), so it never rings over
  the menu nor replays after it.
- No replay on a refresh: `Hud.ShowWinStars` starts the reveal only for a new win (ShowWin and HidePanels hide the row)
  or a different count; a language change, a touch layout switch, a resize or a safe area change only re-place it.
- `Hud.ReducedMotion` (the accessibility hook): the row shows settled at once, with one chime.

## 5. Ad coordination

`AdDirector.ShowAfterDelay` waits one frame (every StateChanged listener has run, RecordLine has started the reveal),
then while `Hud.StarsAnimating` (with the same "still on the panel" checks, capped at 6 s), and only then starts
`showDelaySeconds` (1.2). An ad after a three star win now shows about 1.9 + 1.2 s after the win, or 1.2 s after a skip.
A fail (no stars) waits that one frame only.

## 6. Cost on Android

- One nested Canvas (only it rebuilds while the reveal plays, never the panel's texts): 3 glows, 3 slots, 3 gold stars,
  3 rings and a pool of 24 sparkles, all built once, raycast off, culled when transparent; at rest 3 to 6 images draw.
  No allocation per frame (structs, arrays, one `System.Random`, indexed touch loop).
- Textures drawn once in code: `Stars.StarLarge` and `Stars.StarSlot` 192 x 192 (about 147 KB each),
  `ProceduralArt.BurstRing` 128 x 128, `SoftGlow` and `Sparkle` 64 x 64 (about 390 KB in all). Audio: about 3.3 s of
  mono 44.1 kHz.

## 7. Files

- New: `Assets/Scripts/Runtime/WinStarsView.cs` (the hero row and its reveal), `Assets/Scripts/Runtime/HudWinStars.cs`
  (partial Hud: the column, the lift, ShowWinStars, the skip, the sounds' glue, the probes `WinStars`, `StarsAnimating`,
  `CompleteStarsAnimation`, `RecordRowY`, `WinLayoutStamp`).
- Edited: `Hud.cs` (old star row and its constants removed, `BuildWinStars`, `LayoutWinColumn` from Init, ShowWin and
  ShowEnd, the stars' Canvas in ApplyCanvases, `UpdateWinStars` in Update), `HudTouchLayout.cs` (the end hint's touch
  height removed, the column laid out again on a layout change), `RecordLine.cs` (one centred row on the column's record
  row, follows `WinLayoutStamp`), `Stars.cs` (`StarLarge`, `StarSlot`), `ProceduralArt.cs` (`BurstRing`, `SoftGlow`,
  `Sparkle`), `Sfx.cs` (chimes, tick), `InputReader.cs` (`SkipPressed`, `InjectSkipPress`), `Monetization/AdDirector.cs`
  (wait for the reveal), `Core/Tuning.cs` (`StarsAnim*`, `SfxStar*`).
- Tests edited (not run): `Assets/Tests/PlayMode/ProbeTestsStars.cs` (Step76a: hero layout, timeline, chimes, refresh,
  skip; new Step76c: one star, two ticks), `Assets/Tests/PlayMode/ProbeTestsEndPanel.cs` (stars settled before the
  shots, the row inside the canvas and clear of every button at 20:9, 16:9 and 4:3).

## 8. How to check

- Compile: `SetupAndCompile` (Build/stars.log), no `error CS`.
- Tests to run: PlayMode `ProbeTestsStars|ProbeTestsEndPanel|ProbeTestsM5Ui|ProbeTestsM3Look|ProbeTestsM3Audio|ProbeTestsAudioOverhaul`,
  EditMode `StarsTests|MonetizationTests`.
- By hand, after a rebuild of the player: `Build/Play/OutOfSight.exe`, win a level (three stars on a quick run: the
  slots pop, the stars fill with rising chimes, the third with the chord); click during the reveal to complete it;
  press Enter right away to check Next level is never blocked; win the last level for the end screen. Then
  `Build/Play/OutOfSight.exe -touch` for the touch layout (bottom bar under the column). With the Simulated ad provider
  (`simulatedEveryLevelEnd`), the ad shows about 1.2 s after the stars settled.

## 9. Confetti (2026-11-27)

User request: "add confetti at the end of a level when the player gets 3 stars".

### When

- Only for a three star result, on the win panel and on the end screen. Never on 0 to 2 stars, never on the fail panel.
- Fired by the third star's fill (`Hud.OnStarFilled(2)` with `WinStars.Count == 3`), so it bursts on the same frame as the
  third star's big finish (t = 1.22 s), with the chord chime. A skip or `Hud.CompleteStarsAnimation()` on a three star
  result fires it at once, with the one chime the skip owes (the next frame). A press that also leaves the panel (Enter
  on Next level) drops that chime, so no confetti either.
- Once per win: a refresh (language change, layout switch, resize, RecordLine asking again with the same count) never
  fires it again, since nothing fills again. A new count (`ShowWinStars` restarting the reveal) stops the old shower.
- Stops at once (`WinConfettiView.Stop`: every piece hidden, its canvas off) when the panel goes: Next level, Replay,
  Menu (ShowWin and HidePanels hide the row), a fail panel, the HUD hidden by a menu over the panel, or an ad opening
  (`AdService.Showing`, checked every frame). It never starts under an ad, a menu or `Hud.ReducedMotion` (no flying
  paper and no pop for the accessibility hook).
- The ad is untouched: `AdDirector` still waits on `Hud.StarsAnimating` only (the stars' reveal, 1.87 s), then its 1.2 s;
  the shower (about 3.3 s from 1.22 s) is simply cut if the ad opens before it ends.

### What it looks like (`Assets/Scripts/Runtime/WinConfettiView.cs`)

- 96 pieces (`Tuning.ConfettiPieces`): 72 from two cannons just below the bottom corners (40 units in, plus the safe area's
  side insets), fired in turn within 0.16 s, up and inward at 56 to 84 degrees; 24 rained from just above the top edge
  between 0.2 and 0.7 s (`Tuning.ConfettiCannonShare` 0.75).
- Shapes (`ProceduralArt.ConfettiShapes`, one 128 x 32 atlas of four 32 x 32 cells): paper rectangles 11-16 x 15-22
  (34 %), streamer strips 5.5-7.5 x 28-44 (22 %), dots 10-15 (20 %), curled ribbons 18-26 (14 %, an open ring), wavy
  streamers 10-13 x 26-36 (10 %). Colours: the stars' gold, the player furniture's red (`LevelMiniature.ChairRed`), teal,
  white and soft blue.
- Motion (reference units for a 1080 high canvas, scaled by the canvas's height, so every aspect ratio looks the same):
  shots at 2300 to 3400 units/s, linear (1.2 to 1.9 /s) plus quadratic air drag, gravity 600; the shots reach 60 to 95 %
  of the screen's height in about a second, then the paper flutters down at about 330 units/s, swaying sideways (50 to
  120 units/s, more as it slows), spinning 120 to 620 degrees/s and flipping in 3D (scale X = cos, 5 to 13 rad/s, a
  negative scale shows the back, the colour 40 % darker edge-on). Each piece lives 2.4 to 3 s (top rain 2.1 to 2.6 s)
  and fades out over its last 0.6 s: the shower ends after about 3.3 s (`Duration`).
- Draw order: its nested Canvas sits right after the stars and "New stars!" in the win panel, before the Next level /
  Replay / Menu groups and the end screen's group: over the dim, the texts and the stars, under every button. Raycast
  off on every piece and no raycaster on its canvas: nothing is ever blocked.
- Sound: `Sfx.PlayConfettiPop()`, a party popper synthesized at startup (0.75 s: a low-passed noise pop with a thump
  falling from 170 Hz, the streamers' high-passed whoosh, a thinning crackle of tiny 2.8 to 7.2 kHz ticks; its own hashed
  noise, so every clip drawn after it is unchanged), once per shower, a one shot on `Sfx.UiSource` like the chimes
  (options' volume, silent under AudioMute). `Tuning.SfxConfettiPopVolume` 0.42 times the mix scale. Counter
  `ConfettiPopsPlayed`.

### Cost on Android

- One extra nested Canvas (only it rebuilds while the paper falls, enabled only then), 96 images built once, one atlas
  and the default UI material: one draw call. Unscaled time (the end screen may be paused). No allocation per frame
  (struct maths, arrays, one `System.Random`). Atlas 16 KB, popper about 66 KB of audio.

### Probes for tests

- `Hud.WinConfetti` (`Playing`, `Bursts`, `LivePieces`, `PieceCount`, `Duration`, `Images`, `Canvas`, `Root`),
  `Hud.ConfettiPlaying`, `Hud.CompleteConfetti()` (ends it at once), `Sfx.ConfettiPop`, `Sfx.ConfettiPopsPlayed`.
- `ProbeTestsStars` (edited, not run): Step76a checks no confetti before the third star, one burst and one pop at the
  third star, 60 to 120 pieces, about 3 s, raycast off and one atlas for every piece, the shower under the three buttons,
  no new burst on a refresh, stopped by Replay, fired at once by a skip on the second three star win, and ending by
  itself (canvas off, no piece left). Step76c checks the three star shower stops when the count becomes one, and that the
  one star result (its reveal, then a completion) never fires one nor pops.
- `ProbeTestsEndPanel` unchanged: its shots now catch the confetti fired by `CompleteStarsAnimation` (no assertion looks
  at it; call `Hud.CompleteConfetti()` there for clean shots if wanted).

## 10. STAR3D: bevelled 3D hero stars (2026-11-27)

User request: "make the 3 stars look strongly 3D with shading; right now they are very flat".

- `Stars.StarLarge` (the filled hero star) is now drawn in its own colours, 256 x 256 (no mipmaps, bilinear): ten facets
  (the distance field's gradient is constant on each arm half, so each arm splits down its ridge into a lit and a shaded
  half), a thick rounded bevel along the edges (slope 2.4 at the edge easing to 0.42 over 0.15 of the half box), Lambert
  light from the top-left plus a Blinn sheen, a gold gradient from bright yellow at the top tip to deep amber at the
  bottom tips, a glossy streak across the upper-left, a dark amber rim and outline, and a soft drop shadow 0.05 right and
  0.065 down baked in. The shape is a little chunkier (inner ratio 0.5) and smaller (outer radius 0.84 of the half box
  instead of 0.88 plus a 0.09 outline) so the outline and the shadow fit inside the same box: sizes and layout unchanged.
- `Stars.StarSlot` (an empty slot): the same shape recessed in a dark grey-blue: the surface leans inward (a lip sloping
  into the hole, steep walls, the floor's facets upside down), so the top walls are in shadow and the bottom ones catch
  the light; the top-left wall casts its shadow on the floor. The filled star covers it exactly and pops out of it.
- `Stars.StarFlash` (new, 128 x 128): the star's white silhouette. The fills are no longer tinted gold (a tint can only
  darken the baked colours): they show white (`WinStarsView.FilledTint`), and the punch's white-hot flash is this
  silhouette laid over the star (`WinStarsView` builds one per star between the stars and the rings), fading from 0.95
  over the first 0.55 of the punch. The punch, glow, ring, sparkles and shake are unchanged.
- Small uses keep the old flat sprite: `Stars.Star` (96 texels, tinted gold or faint cream) on the level select cards
  (56 units) and the level select's total icon; at that size the bevel and the facets would turn to mush. Only the end
  screen's hero row uses the 3D sprites.
- Cost: drawn once at the HUD's start (two 258 x 258 distance fields, about 135 000 star distance evaluations, a few
  milliseconds), 256 + 256 + 64 KB of texture instead of 2 x 147 KB. At rest one more texture in the row's canvas only
  while a star flashes.
- Tests: the settled fill colour assertions in `ProbeTestsStars` now compare with `WinStarsView.FilledTint` (they compared
  with `Stars.Gold`, which the 3D sprite no longer uses as a tint). The cards' `Stars.Gold` / `Stars.Empty` checks are
  unchanged.

## 11. Files and checks (Confetti and STAR3D)

- New: `Assets/Scripts/Runtime/WinConfettiView.cs`.
- Edited: `HudWinStars.cs` (the shower: built in BuildWinStars, fired from OnStarFilled, stopped in ShowWinStars,
  HideWinStars and UpdateWinStars, the probes), `Hud.cs` (its canvas in ApplyCanvases), `ProceduralArt.cs`
  (`ConfettiShapes`, `DrawCells`), `Sfx.cs` (`ConfettiPop`, `PlayConfettiPop`, `SynthesizePopper`), `Core/Tuning.cs`
  (`ConfettiPieces`, `ConfettiCannonShare`, `SfxConfettiPopVolume`), `Stars.cs` (the 3D `StarLarge`, `StarSlot`, the new
  `StarFlash`), `WinStarsView.cs` (`FilledTint`, the flash images), `Assets/Tests/PlayMode/ProbeTestsStars.cs`.
- Compile: `SetupAndCompile` (Build/confetti.log), no `error CS`.
- Tests to run: PlayMode `ProbeTestsStars|ProbeTestsEndPanel|ProbeTestsM5Ui|ProbeTestsM3Audio|ProbeTestsAudioOverhaul`,
  EditMode `StarsTests|MonetizationTests`.
- By hand, after a rebuild of the player: `Build/Play/OutOfSight.exe`, win a level quickly (three stars): the 3D slots
  pop in, each gold star flashes white and fills its socket, and as the third lands with the chord the confetti bursts
  from both bottom corners with a pop, rains from the top, flutters down and fades in about 3 s, under the buttons
  (click Next level or Replay during the shower: it works and the shower stops). Click during the reveal: the stars
  settle and the confetti bursts at once. Win slowly (one or two stars): no confetti. Then
  `Build/Play/OutOfSight.exe -touch` for the touch layout (the bottom bar over the paper). With the Simulated ad provider
  (`simulatedEveryLevelEnd`), the ad still shows about 1.2 s after the stars settled and cuts the shower.
