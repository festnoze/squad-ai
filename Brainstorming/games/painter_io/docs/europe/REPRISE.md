# Europe levels: final status

Status of 27 November 2026. Project: `games/painter_io`. Both phases are done and verified in a built Windows player
(`Build/europe/PainterIO.exe`). Machine-readable summary: [progression.json](progression.json). Progression rules,
constants, save format and hooks: [PROGRESSION.md](PROGRESSION.md).

## What exists

- `Assets/Resources/Europe/countries.json`: 46 countries (Europe region of UN M49 with Turkey, Cyprus, Kosovo and the UK, no
  Russia), shared border edges, generator `tools/generate_europe.py`. Rules and sources: [EUROPE_CONTOURS.md](../EUROPE_CONTOURS.md).
- `Assets/Resources/EuropeFlags/`: 46 flag textures. Manifest: [FLAGS.md](FLAGS.md).
- The **Pays** screen (`EuropeScreen`) shows the 3D map (`EuropeMapView`, `EuropeMap.shader`). **Jouer ce pays** starts the
  country arena (`EuropeCatalog.Configure`, `ArenaPolygon`), **Rejouer** replays it, **Menu** goes back. The main menu
  **JOUER** still starts the classic square arena.
- Country progression on top of it (phase 2): start with France only, a first win unlocks 2 countries (neighbors first),
  locked countries dimmed and unplayable, floating GPU-waved flags on unlocked countries, medals on won ones, reveal of the
  new flags, its own save, a hidden reset and command line test flags.

## Phase 1: finish and verify

1. The interrupted PlayMode validation was re-run through the lock under Direct3D 11: `EuropeMenuTests` 1 test, 1 passed,
   0 failed, 0 skipped (`TestResults/europe-play.xml`). Nothing to fix there.
2. Built player check (`tools/europe_shots.ps1` + the new `-europeshot` command line, `EuropeShot.cs`) at 540x960 and
   1080x2400 exposed real readability problems in portrait, now fixed:
   - The map was framed on the whole continent in a square texture: in portrait the selected country, its flag and the
     micro-states were a few pixels. The map now eases to a regional framing of the selected country
     (`FocusGain`, `FocusMargin`, `MinFocusSize`), from an overview when the screen opens.
   - The render texture now follows the viewport's aspect (`EuropeMapView.SetAspect`), so tall phones use their height.
   - Selected micro-states get a pulsing ring (Monaco and the Vatican were invisible).
   - Round shots drive the human out of its home and to the nearest border, so the country outline is in view in each
     biome (`-biome liquid|fire|electric`).
   The country border in a round is the biome's arena edge from the composite shaders (darker outside, bevel), the same
   look as the classic arena; those shaders belong to the wave D rendering work and were not touched.
3. Full EditMode suite at the end of phase 1: 663 tests, 658 passed, 1 failed, 4 skipped, 0 errors
   (`TestResults/europe-phase1-edit.xml`). The failure is the known, pre-existing `WaveC_Composites_KeepTheirFetchCount`
   (13 expected, 14 found), owned by the rendering agent. PlayMode `EuropeMenuTests` after the map changes: 1 of 1 passed.

Shots: `docs/europe/shots/540x960/` and `docs/europe/shots/1080x2400/` (map opened on France, Monaco reached with the
arrows, Vatican, Norway, Turkey, UK, and a France round in the three biomes: `<biome>_round_fr_capture.png` and
`<biome>_round_fr_border.png`).

## Phase 2: country progression

See [PROGRESSION.md](PROGRESSION.md). Final tests:

- Full EditMode suite: 680 tests, 675 passed, 1 failed (the same known `WaveC_Composites_KeepTheirFetchCount`),
  4 skipped (diagnostic reports), 0 errors (`TestResults/europe-final-edit-full.xml`). The 19 Europe tests all pass
  (10 `EuropeProgressionTests`, 7 `EuropeProgressTests`, 2 `EuropeLevelsTests`).
- `EuropeProgressionTests` in the dotnet loop (`tools/CoreTests`): 10 of 10 passed.
- PlayMode `EuropeMenuTests` (progression, reveal, hidden reset, round): 1 of 1 passed (`TestResults/europe-final-play.xml`).

Shots: `docs/europe/shots/progression/` with `0_start`, `1_win` (`-europe-wins FR`), `3_wins` (`-europe-wins FR,ES,CH`,
plus `flags_closeup_0..2.png`) and `unlock_all` (46 flags), each at 540x960 and 1080x2400.

## Resume commands

```powershell
# Tests (through the project lock; read the JUnit counts, not only the exit code)
pwsh -NoProfile -File tools/unity.ps1 -Agent europe -UnityArgs "test . --mode PlayMode --filter EuropeMenuTests --report-format junit --output TestResults/europe-play.xml --timeout 900 -- -force-d3d11 -logFile Logs/europe-play.log"
pwsh -NoProfile -File tools/unity.ps1 -Agent europe -UnityArgs "test . --mode EditMode --filter EuropeProgressTests|EuropeProgressionTests|EuropeLevelsTests --report-format junit --output TestResults/europe-edit.xml --timeout 1800"
dotnet test tools/CoreTests/PainterIO.CoreTests.csproj --artifacts-path tools/CoreTests/.art/europe -v q --filter "FullyQualifiedName~EuropeProgressionTests"

# Player build (never into Build/Windows or Build/Play) and screenshots
pwsh -NoProfile -File tools/unity.ps1 -Agent europe -UnityArgs "run . --timeout 2400 -- -executeMethod PainterIO.Editor.Builder.BuildWindows -buildOut Build/europe -logFile Logs/europe-build.log"
pwsh -NoProfile -File tools/europe_shots.ps1 -Plan "map,round" -Biomes "liquid,fire,electric" -Sizes "540x960,1080x2400" -Out docs/europe/shots
pwsh -NoProfile -File tools/europe_shots.ps1 -Plan "progress,flags" -Sizes "540x960,1080x2400" -Out docs/europe/shots/progression/3_wins -Extra "-europe-reset -europe-wins FR,ES,CH"
```

## Not verified

- Android: touch on the map, the arrows and the hidden title taps, and the frame rate of the map with many flags on a
  real device. Nobody can test it here.
- A real won round end to end in the player (the win hook is covered by tests on its inputs and by `-europe-wins`, which
  goes through the same `RecordWin`).
- `docs/EUROPE_CONTOURS.md` (outside `docs/europe/`) still describes the map before the progression; this file and
  PROGRESSION.md are the current reference.
