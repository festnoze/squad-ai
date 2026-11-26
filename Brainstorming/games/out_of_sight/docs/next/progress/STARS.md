# STARS progress (idea 5: three stars per level and difficulty)

## Design
- Reference per level and difficulty: the "at" of the last point of the level's designer route (designerRouteHard at
  Difficile, designerRoute at Normal and Facile: Facile has no route of its own, Normal's is the more generous side), plus
  `Tuning.StarsReferenceSlack` (2 s). Why the slack: the route's last "at" is the departure of the last run, the doormat is
  reached 0.3 to 1.8 s later (docs/levels_v2/wave1/numbers.md, finding 2), and a human reads the room before moving.
- Thresholds (Tuning.cs, with a comment): 3 stars at or under reference x `StarsThreeFactor` (1.5), 2 stars under
  reference x `StarsTwoFactor` (2.5), 1 star for any other win. A level without a route gives 3 stars (nothing to beat).
- Level 1 (route 11.6 s, reference 13.6 s): 3 stars up to 20.4 s, 2 stars under 34.0 s. Level 19 (71.5 s): 3 up to 110 s.
  Level 22 Difficile (67.6 s): 3 up to 104 s, Normal (49.1 s): 3 up to 76.6 s.
- Save: `SaveData.Stars`, `{ "stars": { "<record key>": n } }`, keyed like `best` (`DifficultyDef.RecordKey` of the level's
  RecordId, so "level6~1" after a redesign resets the stars as it resets the records). Only up, clamped to 0..3. Missing
  on an older save reads as empty (version stays 1); a malformed object or entry never fails the load (skipped or clamped).
  `RecordLine` records the stars in memory just before `SaveStore.RecordWin`, so the one file write carries both.
- Shown: the win panel (a row of three 56 px stars right of the time, x 330, the lit ones popping in 0.22 s apart over
  0.35 s each, with "Nouvelles étoiles !" / "New stars!" under them when the saved count rose; on the end screen the row sits
  beside EndTime at y -82); every playable level select card (three 16 px stars at the right end of the record line); the
  level select column (a gold star and "x / 66 étoiles" under the progress line, at the current difficulty).
- Art: `Stars.Star`, a five point star drawn once in code (white, dark outline) like GaugeArt; gold tint `Stars.Gold`, faint
  cream `Stars.Empty` for an unearned star. No texture asset, no icon library entry.
- The reveal allocates nothing per frame (scales and colours are structs); `StarRow.Animate` returns at once once settled.

## Files
- Assets/Scripts/Core/Tuning.cs: StarsPerLevel, StarsReferenceSlack, StarsThreeFactor, StarsTwoFactor, StarsRevealStagger,
  StarsRevealSeconds (end of the file).
- Assets/Scripts/Core/SaveData.cs: `Stars` field, `RecordStars`, `StarsOf`, the lenient "stars" parse.
- Assets/Scripts/Core/Strings.cs: section "stars.*" at the end of the table (stars.total, stars.newBest) and the two members.
- Assets/Scripts/Runtime/Stars.cs (new): `Stars` (RouteFor, Reference, Count, CountFor, Total, Possible, Star sprite) and
  `StarRow` (a plain class: three Images under a centred root, Set, Place, SetVisible, Animate).
- Assets/Scripts/Runtime/RecordLine.cs: computes and records the stars, then `Hud.ShowWinStars`; `LastStars`, `LastStarsNew`.
- Assets/Scripts/Runtime/Hud.cs: the row and the "New stars!" line on the win panel, `ShowWinStars`, `WinStars`,
  `WinStarsVisible`, `WinStarsNewVisible`; hidden by ShowWin and HidePanels; animated from Update; relocalized.
- Assets/Scripts/Runtime/LevelSelect.cs: `Card.Stars`, the total line (`StarsEarned`, `StarsPossible`, `StarsLineText`),
  the levelshot seeds 3, 2, 1 stars.
- Assets/Tests/EditMode/StarsTests.cs (new): thresholds, reference per difficulty, save rules and parse, round trip,
  strings, the real line-up (22 levels, 66 stars, every level has a reference at both difficulties).
- Assets/Tests/PlayMode/ProbeTestsStars.cs (new, static, not run): Step76a (a quick win earns three stars beside the time,
  above the buttons, clear of the record line, revealed then settled, saved; an equal second win is not "new") and Step76b
  (the level select's first card lights three stars, the total reads "3 / 66", a locked card hides its row).

## Mutation markers added
- SaveData.RecordStars: `MUTATION:STARS_ONLY_UP`. Stars.RouteFor: `MUTATION:STARS_HARD_ROUTE`. Stars.Count:
  `MUTATION:STARS_THREE`, `MUTATION:STARS_TWO`. Every existing marker in the edited files is kept.

## Compile (2026-11-21, Build/STARS.log, the single compile-only run)
- Zero errors and zero warnings from the STARS files (Core, Runtime and the EditMode tests compiled clean).
- The run still ends with "Scripts have compiler errors": one error, not ours, in the PlayMode test assembly:
  `Assets/Tests/PlayMode/ProbeTestsHeldStart.cs(11,12): error CS0579: Duplicate 'TestRunCallback' attribute`, a clash
  between two other agents' files (ProbeTestsFocusPause.cs and ProbeTestsHeldStart.cs both declare an assembly level
  `[assembly: TestRunCallback(...)]`; the attribute allows one per assembly). Not retried: the one-run cap, and the fix
  belongs to FOCUS / the owner of ProbeTestsHeldStart.cs (merge the two callbacks into one ITestRunCallback, or drop one).
- Unity wrote the .meta files of the three new .cs files during the run.

## A VERIFIER
- Run StarsTests (EditMode) and ProbeTestsStars Step76a/76b (PlayMode): written against the real APIs but never run.
- Run ProbeTestsEndPanel Step73a/73b again: the stars are Images (not in the texts the steps check) and sit above the
  button row, but the screenshots should be looked at (the row right of the time on 4:3, the "New stars!" line).
- Look at the win panel in the player: the row at x 330 right of "Temps : 37,4 s" (52 px); a time over 999 s would reach it.
- Look at a level select card: the three 16 px stars in the 60 px right of the record line, with the furniture chip above.
- Thresholds in play: the factors are a first guess (1.5 and 2.5 over the route's last "at" plus 2 s); tune in Tuning.cs
  after a few human runs, Difficile of levels 13, 19, 20 and 22 in particular (their hard routes are longer).
- Facile is judged against the Normal route (no Facile route exists): generous by design, confirm it is wanted.
- A level without any route gives three stars: no shipped level is in that case (StarsTests checks the line-up).
