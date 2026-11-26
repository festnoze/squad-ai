# LOADDOTS - loading dots on "Niveaux"

## What was slow

The level select's cards are built with the menu (at boot), so the click itself did not build them. The cost of the
first open is in `LevelSelect.SetOpen(true)`:

- `RecordIdOf` / `StarsText` call `LevelMiniature.Def` for every level: `Resources.Load` of the level JSON plus
  `LevelJson.Parse` (24 levels).
- `EnsureArt` calls `LevelMiniature.MiniatureOf` for every level: a 240 x 200 CPU raster of the plan, then
  `Texture2D.Apply` and `Sprite.Create`.

All of it is cached statically (`LevelMiniature` dictionaries), so only the first open of a run is slow; later opens
only refresh texts. The canvas of 24 cards is also built (layout, text meshes) when it is first enabled, in that frame's
render, outside the measured time.

Measures in the player log (`%USERPROFILE%\AppData\LocalLow\<company>\OutOfSight\Player.log`):

- `[LevelSelect] open took X ms`: every open (the old synchronous path, or the final step after the dots).
- `[LevelSelect] loaded behind the dots in X ms: W ms of work over N frames (worst frame F ms)`: a first open by click.
- `[LevelSelect] pre-warm done: W ms of work over N steps (worst step S ms)`: the pre-warm on the title.

## How it works now

- `LevelSelect.WarmStep()` does one piece of the first-open work: the next level's parse, or its miniature and summary.
  `LevelSelect.Warm` says it is all done (then `SetOpen` only reads caches).
- `Menu.OpenLevelSelect()`: when the page is warm (or `Menu.InstantLevelSelect`), it opens at once as before. Otherwise
  the coroutine `LoadLevelSelect` starts (coroutines in this project carry no "a" prefix, like `AutoShot`, `Shot`):
  label becomes "Niveaux." and one frame passes so the dot renders; then up to 8 ms of `WarmStep` per frame, the label
  cycling ".", "..", "..." every 0.3 s; the page opens on the frame the work ends, label restored, default card selected
  as before.
- Width stays stable: the missing dots are drawn invisible (`<color=#00000000>..</color>`), so the label is always
  "Niveaux..." wide (the title buttons are left aligned anyway).
- Guards: a second press during the load is ignored (`LevelSelectLoading`); Escape or gamepad B cancels the load (click
  sound, Niveaux stays selected); Jouer, Options, Credits, `OpenTitle` and `OnDisable` cancel it too; the coroutine
  stops itself when the title's main page is no longer what shows. Work done before a cancel stays cached.
- Focus: nothing touches the selection during the load; Niveaux keeps it and the arrows still move it.
- Pre-warm (done): after the title's main page has shown for 1.5 s, one `WarmStep` every 3 frames (one parse or one
  miniature, never both in a frame). Off during a load, while Options or Credits show, and under `InstantLevelSelect`.
  A click before it finishes shows the dots only for the part left.

## Tests

`Menu.InstantLevelSelect` (default on under --probe, --look, batch mode) keeps the old synchronous open; the PlayMode
run callback `HeldStartTestRun` turns it on before the run and each test, and resets it after the run. `LevelSelect.Shot`
(--levelshot) waits for `LevelSelectLoading` to end before its screenshot. Tests not run (user runs them).

## A VERIFIER

- Player: first click on Niveaux right after boot shows "Niveaux." then ".." "..." cycling, no text jump, then the page.
- Player: wait 5 s on the title, then click: the page opens at once (log "pre-warm done", then "open took" small).
- Escape / gamepad B during the dots cancels; a double click does not open twice; Jouer during the dots starts the game
  with the label back to "Niveaux".
- Keyboard and gamepad: Niveaux stays highlighted during the dots, up/down still move the selection.
- Mobile: no visible stutter of the title animation during the pre-warm (log "worst step"); if there is, raise
  `PrewarmEveryFrames` or drop the pre-warm (Menu.cs).
- Language switch (English) after a load: the label reads "Levels" with no dots left.
