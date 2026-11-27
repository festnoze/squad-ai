# Europe country progression

Designer request: "once a win on a country unlocks the right to select 2 new countries, adjacent to the won country when
possible; the other countries stay disabled; for unlocked countries not yet won, make a 3D animated flag float, printed
with the colors of that country's flag."

**Countries first (rule change v1.7, docs/CONTRACT.md section 31).** The countries are the core of the game: the main menu
has no **Pays** button any more, and **JOUER** opens the country screen (`MenuScreen.OnPlay` calls `UiRoot.OpenEurope`).
"Jouer ce pays" starts the round (`GameDirector.StartCountry`); a country round lasts at most 15 minutes and its goal is
to conquer 100 % of the land (`RoundEndReason.Conquest`; after the 15 minutes the largest land wins). The results always
offer **PAYS SUIVANT** (main button and Escape / back: `GameDirector.ToCountryScreen`, the country screen over the attract
match, where a win plays the reveal of the newly unlocked flags) and **REJOUER** (the same country again). The classic
square arena is no longer reachable from the menu (only `StartRound` with no country: probe, DevShot, launch flags, tests).

## Rules

| Rule | Where | Value |
| --- | --- | --- |
| Start state: one unlocked country | `EuropeProgression.StartCountry` | `"FR"` |
| Countries unlocked by the FIRST win on a country | `EuropeProgression.UnlocksPerFirstWin` | `2` |
| Unlock order | `EuropeProgression.PickUnlocks` (one static function) | see below |
| What counts as a win | `EuropeProgress.IsCountedWin` (one static function) | see below |

**Unlock rule** (`PickUnlocks`). On the first win of country X, up to 2 still locked countries are unlocked:

1. the locked land neighbors of X, longest shared border first, then nearest centroid, then ISO code (ordinal);
2. if fewer than 2, the remaining slots go to the other locked countries by centroid distance to X, then ISO code.

Step 2 covers the islands (CY, IS, MT, and GB / IE once their only neighbor is open) and the Nordic block: with Russia out
of the map, Norway, Sweden and Finland have no land link to the continent, so they are reached through the centroid
fallback. Replaying an already won country unlocks nothing. A win on a locked country can only come from the test hooks;
it unlocks that country first. Everything is ordered explicitly, so the same history always gives the same map
(tested).

Examples on the real map: winning FR unlocks ES then CH (548 km and 455 km of border; BE is third with 454 km); winning
GB first unlocks IE (its only land neighbor) and the nearest locked centroid.

**Win definition** (`IsCountedWin`). The game's existing round victory, exactly the one that increments `SaveData.Wins`
in `GameDirector.RecordStats`: a real round (`GameSession.CountsForStats`, so not attract, probe, DevShot or test
sessions), stats-valid settings (no modified hidden test settings, no command line tuning override), and the human
ranked first (`HumanOutcome.Rank == 1`, shared first place included). `GameDirector.ShowResults` calls
`EuropeProgress.OnRoundResults(session, outcome, selectedCountry)` right after `RecordStats`; nothing happens for the
classic arena (no country). Rank 1 covers every winning end of rule v1.7: Conquest, last survivor, and first (or shared
first) at the 15 min limit. The default round time (15 min) is not a "modified test setting"; 5 or 10 min is.

**Invariant**: the playable pool (unlocked, not won) never becomes empty before all 46 countries are won. Each first win
removes one country from the pool and adds `min(2, locked)`; the full campaign walk test wins the first pool country 46
times in a row.

## Code

| File | Role |
| --- | --- |
| `Assets/Scripts/Core/Europe/EuropeGraph.cs` | Pure C#. Land adjacency from the exactly shared ring edges of `countries.json` (vertices compared at 1 m), shared border lengths, area-weighted centroids. Independent of input order. |
| `Assets/Scripts/Core/Europe/EuropeProgression.cs` | Pure C#. `CountryProgress` (Locked, Unlocked, Won), the campaign state, `RecordWin`, `PickUnlocks`, `Reset`, `UnlockAll`, the pending reveal list, `ToData` / `FromData` (`EuropeProgressData`). |
| `Assets/Scripts/Runtime/Game/EuropeProgress.cs` | Unity side: builds the graph once from `EuropeCatalog`, loads and saves the JSON under its own PlayerPrefs key, the win hook, the command line flags, the `Changed` event. |
| `Assets/Scripts/Runtime/View/EuropeMapView.cs` | The 3D map: state tints, floating flags, medals, selection lift and ring, focus camera, reveal, close-up. |
| `Assets/Scripts/Runtime/UI/MenuScreen.cs` | JOUER opens the country screen (rule v1.7; no Pays button). |
| `Assets/Scripts/Runtime/UI/ResultsScreen.cs` | PAYS SUIVANT (`GameDirector.ToCountryScreen`) and REJOUER (same country). |
| `Assets/Scripts/Runtime/UI/EuropeScreen.cs` | The Pays screen: progress line, status line, locked hint, arrows that skip locked countries, "Jouer ce pays" gating, reveal on open, hidden reset. |
| `Assets/Resources/Shaders/EuropeMap.shader` | Land, poles and cloth. `_Wave` animates the cloth in the vertex shader, `_Phase` shifts each flag, `_Cutout` cuts the medal. |
| `Assets/Scripts/Runtime/Game/GameDirector.cs` | Two lines: the `EuropeShot` factory and the `EuropeProgress.OnRoundResults` call in `ShowResults`. |

## Map states

| State | Land | Marker | Interaction |
| --- | --- | --- | --- |
| Locked | dark desaturated slate `(40, 48, 61)` | none | tap selects it and shows "Verrouillé : gagne un pays voisin"; "Jouer ce pays" is dimmed and refuses; the arrows skip it |
| Unlocked, not won | the original map palette | floating flag on a pole, its cloth waving, printed with `EuropeFlags/<code>` | playable; status "À conquérir" ("Nouveau ! À conquérir" right after its reveal) |
| Won | the human's color (current biome, muted by `WonColorMute`) | gold medal with a white check, standing on the country, facing the camera | playable (replay); status "Conquis" |

The selected country is lifted, brightened, framed by the easing focus camera (`FocusGain`, `FocusMargin`,
`MinFocusSize`), its flag is drawn 1.3x larger, and a micro-state also gets a pulsing ring. The title area shows
"N / 46 pays conquis".

**Floating flags.** All flags share one cloth mesh (16 columns), one pole mesh (a copy of the built-in cylinder) and the
one `EuropeMap` material loaded with `Resources.Load<Shader>("Shaders/EuropeMap")` (no `Shader.Find`). Each cloth gets
its flag texture and a wave phase from a `MaterialPropertyBlock`; the wave runs in the vertex shader, so there is no CPU
mesh work per frame. Flags are created the first time a country needs one and are then only shown or hidden. Pole
heights vary between 0.85x, 1x and 1.15x by country code so that close flags stack instead of covering each other;
micro-states (footprint under `SmallCountryExtent`) use 0.6x flags and medals. The cloth leans back by `ClothTilt` to
face the tilted map camera. With every country unlocked (46 flags, the worst case) the map still reads; see
`shots/progression/unlock_all/`.

**Reveal.** A first win queues the newly unlocked codes in the campaign (`PendingReveal`, saved). The next time the map
opens, it selects the first of them, raises their flags one after the other (`RevealRiseSeconds` with an overshoot,
`RevealStagger` apart) with a short flash of their land, frames all of them together with the selection for
`RevealHoldSeconds`, then eases back to the selection. The reveal plays once (`EuropeProgress.ConsumeReveal`). A country
won before its reveal was shown leaves the list.

## Save format

PlayerPrefs key `pio.europe.progress` (separate from `SaveData`, which this feature does not touch). Value:

```json
{"version":1,"won":["CH","ES","FR"],"unlocked":["AD","CH","DE","ES","FR","IT","PT"],"reveal":["PT","AD","IT","DE"]}
```

`won` and `unlocked` are sorted ISO codes (won countries are also unlocked); `reveal` keeps the unlock order. On load,
unknown codes are dropped, won implies unlocked, `FR` is always unlocked, `reveal` keeps only unlocked, not won
countries, and an empty or unreadable value starts a new campaign. Writes happen only on changes (win, reset, unlock all,
reveal played) and call `PlayerPrefs.Save()`.

## Reset and test hooks

| Hook | Effect |
| --- | --- |
| Five taps on the "Europe" title within 1.5 s | shows "Réinitialiser la progression"; a first tap turns it into "Confirmer la réinitialisation ?", a second one resets; it hides itself after 8 s |
| `-europe-reset` | new campaign (saved) |
| `-europe-wins FR,ES,CH` | records these wins in order, exactly as real first wins (saved, reveal queued) |
| `-europe-unlockall` | every country playable, wins kept (saved) |
| `EuropeProgress.StorageKey` | tests only: another PlayerPrefs key, so tests never touch the player's save |

The flags apply once per run, in the order reset, wins, unlock all, the first time the campaign is read. They change the
saved campaign of that machine (Windows: `HKCU\Software\PainterIO\Painter.io`); the screenshot runs end with an
`-europe-reset` run.

Screenshots from a built player: `tools/europe_shots.ps1` launches `PainterIO.exe -europeshot <dir>` with
`-europeshot-plan map|round|progress|flags` (see `Assets/Scripts/Runtime/Probe/EuropeShot.cs`). Everything is driven
in-process (`UiRoot.OpenEurope`, `EuropeScreen.StepSelection` / `SelectCode` / `PlaySelected` / `SetCloseUp`, the
human's `ExternalController`); no OS input is sent.

```powershell
pwsh -NoProfile -File tools/europe_shots.ps1 -Plan "progress,flags" -Sizes "540x960,1080x2400" -Out docs/europe/shots/progression/3_wins -Extra "-europe-reset -europe-wins FR,ES,CH"
```

## Tests

- `Assets/Tests/EditMode/Core/EuropeProgressionTests.cs` (synthetic maps, also in the dotnet loop `tools/CoreTests`):
  start state, first win unlocks the 2 longest borders, tie-breaks, island fallback, fewer than 2 locked neighbors left,
  replay unlocks nothing, determinism (same history, shapes in any order), full campaign with a never empty pool, data
  round trip and sanitizing, graph from shapes.
- `Assets/Tests/EditMode/Runtime/EuropeProgressTests.cs` (real map): adjacency symmetry and expected neighbors, land
  connectivity, FR unlocks ES and CH, GB and IS fallbacks, replay, full 46-country campaign (twice, identical), JSON and
  PlayerPrefs round trip, win definition.
- `Assets/Tests/PlayMode/EuropeMenuTests.cs`: no Pays button and JOUER opens the country screen, a new campaign shows one
  flag (France), arrows skip locked countries, a locked country cannot start, a first win shows two rising flags and a
  medal on the next opening, the hidden reset, then a France round (900 s, goal 100 %), REJOUER keeps France, PAYS SUIVANT
  shows the country screen over the attract match.
- `Assets/Tests/EditMode/Runtime/FlowV17Tests.cs` and `EuropeLevelsTests.EveryCountryHasAReachableConquestGoal`: the
  round time setting and its migration, the conquest texts, every winning end counted, every level's conquest goal.
