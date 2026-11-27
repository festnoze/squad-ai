# Painter IO - Game overview (handoff for an AI agent)

Snapshot: 2026-11-26, late evening. Project root: `C:\Dev\squad-ai\Brainstorming\games\painter_io` (Unity project at the root).
All relative paths below are relative to `docs/` (this file's folder) unless they start with `Assets/`, `tools/` or `Build/` (relative to the
project root).

Sources of truth, in order: `docs/REGLES_DU_JEU.txt` (the designer's French brief, v0.1) as amended by the designer's later decisions recorded
in `docs/CONTRACT.md` (v1.7, about 2000 lines: rules, algorithms, APIs, rendering, UI, verification), plus the normative wave D specs
`docs/BIOME_TRAITS.md` and `docs/WAVE_D_FEEDBACK.md`. Build reports per agent are in `docs/waveA/`, `docs/waveB/`, `docs/waveC/`, `docs/waveD/`.

---

## 1. Pitch

A mobile-first (portrait) arena territory game deliberately modeled very closely on Voodoo's **Paper.io 2**. You steer a pawn non-stop, draw a
free curve outside your color, and come back home to paint the enclosed surface. One human against three bots, 90 second rounds, one life,
the largest surface wins.

Two signature rules come from the designer's brief:
- **La Revanche** (the core rule): when a rival cuts your trail, a spark starts at the cut point and races up your trail toward you.
- **Le Lasso**: a one-charge bonus that lets you close a pocket on your own trail mid-excursion.

The art direction is glossy liquid paint. On top of it there are three switchable **biomes**: Liquide, Feu (fire) and Électricité.

**Working title:** "Painter IO". The final name is still open (see section 9). A naming study recommends Splash.io, Drip.io or Spark.io. Paint.io
and Painter.io are already used by clones of the same genre.

## 2. Relationship to Paper.io 2

**Kept on purpose (players should recognise the game at a glance):**
- Top-down arena, constant-speed pawn, steering by a thumb drag anywhere on screen; lifting the finger keeps the heading.
- Safe inside your color. Outside, a visible trail links your exit point to your head.
- Coming back home captures what the trail and your territory enclose, including land taken from rivals.
- A rival's head touching your exposed trail is the threat; heads pass through heads.
- One life, instant restart, a percent-of-map score, a small round-based arena, a bright four-color palette, short sessions.
- The ".io" genre feel: one rule, short rounds, die and replay.

**Different on purpose:**
- **Cuts are not instant deaths (La Revanche).** A spark runs along the victim's trail at 1.8x pawn speed, from the cut toward the head.
  - If the spark reaches the head first, the victim is eliminated and all its territory turns neutral. The attacker gains nothing automatically.
  - If the victim gets home first, it survives but captures nothing: the cut loop is lost. This is the designer's v1.4 change; the brief
    originally said the whole gain was kept.
  - A cut close behind the head is deadly; a cut far behind gives time to get home.
- **Crossing your own trail is allowed** (Paper.io kills you). Without a lasso charge, a self loop is simply not captured (decided reading R8).
- **Le Lasso.** A ring spawns on neutral ground. Carrying its single charge, your first real self-crossing closes a hatched pending pocket,
  which is validated only by an unchased return.
- **The border never kills** and never closes territory: the pawn slides along it, and an order straight outward holds it against the wall.
- **Rounds last 90 s** against 3 bots. The last survivor wins at once; otherwise the largest surface at time-up wins (exact ties share the place).
- **Visual identity:** glossy liquid paint instead of flat paper, plus fire and electricity biomes.
- **Planned per-biome gameplay traits** (wave D, in progress): propagation, conduction, arc reach and more (section 5).

## 3. Rules (summary of the normative rules R1-R20 in CONTRACT.md section 4, with sections 24 and 26)

- **Arena:** rounded square, half size 32 u, corner radius 10 u, ownership grid 512 x 512 (0.125 u cells). Cells outside the shape are void.
  Four start discs of radius 3.5 u at (+/-16, +/-16).
- **Motion:** 6 u/s, turn rate 540 deg/s (0 means instant turns, used by tests). The sim runs fixed ticks (60 Hz) with continuous in-tick event
  times, so outcomes do not depend on the frame rate.
- **Home and exit:** you are home while your head's current cell is yours. The trail starts at the exact cell-edge crossing point.
- **Capture:** inside = cells not reachable from outside the map when the walls are your territory plus your trail. Only NEWLY enclosed cells
  are captured (holes enclosed by your territory alone stay as they are).
  - The trail outline is loop-erased, so self loops are not captured without a lasso.
  - A bare back-and-forth line captures nothing.
  - An excursion along the border cannot paint the map.
  - The rim of trail cells around a captured area is included (8-adjacency).
- **Cut:** an enemy head (radius 0.45) touching your trail capsule (half width 0.18), outside the last 1.0 u behind your head (head grace).
  - If several passes of the same trail are touched at the same instant, the most recent pass gives the cut point.
  - If several attackers cut at the same instant, the cut closest to the head is kept.
- **Spark:** spawns at the cut point and follows the real path in passing order (no shortcut through loops), at a constant 1.8x pawn speed.
  - Later cuts change nothing.
  - It keeps running if the attacker dies.
  - An exact tie between the return and the impact means the return wins.
  - A cut at the exact instant the trail closes has no effect.
- **Simultaneous returns:** each is judged against the grid just before the instant. Cells claimed by two returns keep their previous owner.
- **Territory theft:** if a rival takes the cell under you while you are home, an exit starts there. Losing your last cell eliminates you.
- **Ring and lasso:**
  - The first ring spawns at 15 s, then 15 s after each pickup, one at a time, on neutral ground.
  - Capacity is one charge, kept across exits. A contested ring stays until exactly one eligible player touches it.
  - The pocket is pending: it does not count for the score and the land owners keep their rights.
  - The lasso is **OFF by default** in the runtime (the brief asks for a first Revanche trial without rings). The Options switch turns it on.
- **Round end and ranking:** competition ranking (1, 1, 3). Eliminated players rank by elimination time. An eliminated player sees its area
  just before elimination. Pending pockets never count.

## 4. Feel, UI and presentation

- **Rendering idea:** metaball-like additive fields. A blurred territory field in world space plus an actor field (threads, pearls, bulbs) in a
  screen-space render target feed a full-screen composite that shades a height field (glossy highlights, soft shadows).
  - Necks between pearl, thread and puddle appear by themselves.
  - Surface shaders are thin Shader Graphs (logic in .hlsl Custom Functions); the additive field shaders and the blur are hand-written HLSL.
- **Liquide (default):**
  - each territory is one puddle (wave D is making it read more like a domed drop);
  - your head is a glossy pearl pulling a thin liquid thread;
  - a capture fills with one liquid wave;
  - a cut makes the thread retract from the pinch point toward the pearl, leaving a chain of droplets. The retraction front IS the spark.
- **Camera:** orthographic, top-down, about 18 u visible width in portrait. It follows the head with a smoothed lookahead and zooms out during
  a chase to frame the front and the way home.
- **Controls:**
  - Touch: a floating stick anywhere on screen.
  - PC: the pawn heads toward the mouse cursor, a left-drag acts like the touch stick, arrows or WASD give 8 directions.
  - Escape or Android back pauses.
  - A round waits for the first steering input.
- **HUD:** your % (left, in your color), the countdown (center), the best rival % (right, opens a 4-row leaderboard), a pause button, toasts,
  a danger vignette while chased, a home arrow and an off-screen spark indicator.
- **Tutorial (French by default, English available):**
  - "Sors de ta couleur et reviens pour agrandir ton terrain."
  - "On a coupé ton trait ! Rentre avant l'étincelle pour rester en vie."
  - A one-time lesson when you cross your own thread without a charge.
  - The lasso explanation only at the first ring pickup.
- **Results screen:** a WHY line that makes La Revanche learnable, for example "Rentré 0,4 s avant l'étincelle : boucle perdue." or
  "Safran t'a coupé : rattrapé à 2,3 m de chez toi.", plus a stats line, REJOUER and MENU.
- **Menu:** title, three biome cards with animated previews, a color picker (4 colors), JOUER, Options (sound, vibration, lasso, language,
  quality, biome rules) and hidden test settings (5 taps on the version label: spark speed, round length, ring delay, trait matrix in wave D).
- **Audio:** procedural, no audio assets, one clip set per biome. The spark tension loop rises as the spark closes in. Bot sounds play only on
  screen and quieter.
- **Haptics:** Android only.

## 5. The three biomes

Each biome is a complete visual and audio theme. The rules are identical in all three except for the optional traits below.

| Biome | Look | Fill on capture | La Revanche (cut) | Elimination |
|---|---|---|---|---|
| **Liquide** | Navy table, glossy coral / teal / saffron / lilac paint puddles, pearl heads, liquid threads | One liquid wave from the return point | Thread retracts toward the pearl, droplet chain left behind | Puddle evaporates, pearl splashes |
| **Feu** | Charred ash ground, ember beds in chemical flame colors with flame tongues at the edge, burning fuse threads, fireball heads | A spreading flame front (the designer likes fire because it spreads) | A white-hot spark races along the fuse; burnt fuse becomes cooling embers and ash with smoke | Burns out to smoking ash |
| **Électricité** | Blue-black ground with a faint hex grid, neon plasma territories with a hex pattern and a crackling rim, live-wire threads, plasma-orb heads | A branching lightning discharge | A packet of current races up the wire; dead grey cable with fading sparks behind | Short circuit, blackout |

**Gameplay traits per biome (wave D, being implemented; see BIOME_TRAITS.md).** Each trait is one independent module (one file in
`Assets/Scripts/Core/Traits/`). The table below is the default assignment, and it is the only place that ties traits to biomes.

| Biome | Default traits | Intended play style |
|---|---|---|
| Liquide | Inertia (turn rate 420 deg/s), Coalescence (small neutral holes in your puddle fill after an unchased capture) | Forgiving, smooth big loops, closest to the brief |
| Feu | Propagation (your fire grabs one ring of neutral cells every 4 s), SparkSpeed 2.1x, ScorchedEarth (an eliminated player leaves ash that propagation cannot reclaim for 15 s) | Snowball and danger: short careful excursions, hold your land |
| Électricité | Conduction (+30 % speed on your own territory), ArcReach (cut reach +40 %), SparkSpeed 1.5x, RingInterval 10 s | Tempo and harassment: many cuts, more survivable chases |

**Switching traits off or moving them:**
- every trait can be switched off individually or moved to another biome: a trait x biome matrix in the hidden test settings, or command-line
  flags `-classic`, `-traits "<key>"`, `-trait <Id>=0|1`;
- the "Règles classiques" option switches all of them off;
- with all traits off, the simulation is bit-identical to the classic one.

## 6. Screenshots

Captured from the release player (`-devshot`, the scripted demo round) after wave C. Checkpoint meanings:
- `menu`: main menu over the attract match;
- `ThreadOut`: the human is out with its thread;
- `MidFill`: a clean capture filling;
- `CutDroplets`: during a chase right after a cut;
- `SavedReturn`: just after a chased return that survived but lost its loop;
- `PocketPending`: a lasso pocket over a rival;
- `Caught`: the spark catches the human;
- `results`: the results screen.

Same checkpoint names in every folder.

### Liquide
| | 540 x 960, High | 1080 x 2400, High |
|---|---|---|
| Menu | ![](waveC/shots/final/liquid_high_540x960/liquid_menu.png) | [liquid_menu.png](waveC/shots/final/liquid_high_1080x2400/liquid_menu.png) |
| Thread out | ![](waveC/shots/final/liquid_high_540x960/liquid_ThreadOut.png) | [liquid_ThreadOut.png](waveC/shots/final/liquid_high_1080x2400/liquid_ThreadOut.png) |
| Capture fill | ![](waveC/shots/final/liquid_high_540x960/liquid_MidFill.png) | [liquid_MidFill.png](waveC/shots/final/liquid_high_1080x2400/liquid_MidFill.png) |
| Cut, droplet chain | ![](waveC/shots/final/liquid_high_540x960/liquid_CutDroplets.png) | [liquid_CutDroplets.png](waveC/shots/final/liquid_high_1080x2400/liquid_CutDroplets.png) |
| Saved return (loop lost) | ![](waveC/shots/final/liquid_high_540x960/liquid_SavedReturn.png) | [liquid_SavedReturn.png](waveC/shots/final/liquid_high_1080x2400/liquid_SavedReturn.png) |
| Lasso pocket | ![](waveC/shots/final/liquid_high_540x960/liquid_PocketPending.png) | [liquid_PocketPending.png](waveC/shots/final/liquid_high_1080x2400/liquid_PocketPending.png) |
| Caught | ![](waveC/shots/final/liquid_high_540x960/liquid_Caught.png) | [liquid_Caught.png](waveC/shots/final/liquid_high_1080x2400/liquid_Caught.png) |
| Results | ![](waveC/shots/final/liquid_high_540x960/liquid_results.png) | [liquid_results.png](waveC/shots/final/liquid_high_1080x2400/liquid_results.png) |

### Feu
| | 540 x 960, High | 1080 x 2400, High |
|---|---|---|
| Menu | ![](waveC/shots/final/fire_high_540x960/fire_menu.png) | [fire_menu.png](waveC/shots/final/fire_high_1080x2400/fire_menu.png) |
| Thread out | ![](waveC/shots/final/fire_high_540x960/fire_ThreadOut.png) | [fire_ThreadOut.png](waveC/shots/final/fire_high_1080x2400/fire_ThreadOut.png) |
| Capture fill (flame front) | ![](waveC/shots/final/fire_high_540x960/fire_MidFill.png) | [fire_MidFill.png](waveC/shots/final/fire_high_1080x2400/fire_MidFill.png) |
| Cut, lit fuse | ![](waveC/shots/final/fire_high_540x960/fire_CutDroplets.png) | [fire_CutDroplets.png](waveC/shots/final/fire_high_1080x2400/fire_CutDroplets.png) |
| Saved return (loop lost) | ![](waveC/shots/final/fire_high_540x960/fire_SavedReturn.png) | [fire_SavedReturn.png](waveC/shots/final/fire_high_1080x2400/fire_SavedReturn.png) |
| Lasso pocket | ![](waveC/shots/final/fire_high_540x960/fire_PocketPending.png) | [fire_PocketPending.png](waveC/shots/final/fire_high_1080x2400/fire_PocketPending.png) |
| Caught | ![](waveC/shots/final/fire_high_540x960/fire_Caught.png) | [fire_Caught.png](waveC/shots/final/fire_high_1080x2400/fire_Caught.png) |
| Results | ![](waveC/shots/final/fire_high_540x960/fire_results.png) | [fire_results.png](waveC/shots/final/fire_high_1080x2400/fire_results.png) |

### Électricité
| | 540 x 960, High | 1080 x 2400, High |
|---|---|---|
| Menu | ![](waveC/shots/final/electric_high_540x960/electric_menu.png) | [electric_menu.png](waveC/shots/final/electric_high_1080x2400/electric_menu.png) |
| Thread out | ![](waveC/shots/final/electric_high_540x960/electric_ThreadOut.png) | [electric_ThreadOut.png](waveC/shots/final/electric_high_1080x2400/electric_ThreadOut.png) |
| Capture fill (discharge) | ![](waveC/shots/final/electric_high_540x960/electric_MidFill.png) | [electric_MidFill.png](waveC/shots/final/electric_high_1080x2400/electric_MidFill.png) |
| Cut, current packet | ![](waveC/shots/final/electric_high_540x960/electric_CutDroplets.png) | [electric_CutDroplets.png](waveC/shots/final/electric_high_1080x2400/electric_CutDroplets.png) |
| Saved return (loop lost) | ![](waveC/shots/final/electric_high_540x960/electric_SavedReturn.png) | [electric_SavedReturn.png](waveC/shots/final/electric_high_1080x2400/electric_SavedReturn.png) |
| Lasso pocket | ![](waveC/shots/final/electric_high_540x960/electric_PocketPending.png) | [electric_PocketPending.png](waveC/shots/final/electric_high_1080x2400/electric_PocketPending.png) |
| Caught | ![](waveC/shots/final/electric_high_540x960/electric_Caught.png) | [electric_Caught.png](waveC/shots/final/electric_high_1080x2400/electric_Caught.png) |
| Results | ![](waveC/shots/final/electric_high_540x960/electric_results.png) | [electric_results.png](waveC/shots/final/electric_high_1080x2400/electric_results.png) |

### Other references
- Target liquid look given by the designer: ![](reference_gouttes.png)
- **Medium tier (the Android default)** for each biome: `waveC/shots/final/<biome>_medium_540x960/` and `<biome>_medium_1080x2400/`.
- **Contact sheets** comparing Gate B and the final build: `waveC/shots/final/compare/` (liquid_sheet_a.png, fire_sheet_a.png,
  electric_sheet_a.png, ui_aspects_sheet.png, ui_landscape_sheet.png).
- **UI at other aspect ratios:** `waveC/shots/final/ui_liquid_1080x2520_21x9/`, `ui_liquid_900x1200_tablet/`,
  `ui_liquid_1280x720_landscape/`.
- **Wave D work in progress** (not in the release build yet):
  - electric bases crossed by small arcs: `waveD/shots/elec-arcs/` (see `compare/`);
  - liquid drop look: `waveD/shots/liq-drop/`.

## 7. Technology and project layout

- **Stack:** Unity 6000.3.23f1 (6.3 LTS), URP 17.3, Shader Graph 17.3, Input System 1.20, uGUI (no TextMeshPro), C#.
- **Targets:**
  - Windows: Mono, portrait window 540 x 960.
  - Android APK: IL2CPP ARM64, minSdk 25, portrait, Vulkan then GLES3.
- **Assemblies:**
  - `PainterIO.Core` (`Assets/Scripts/Core`): pure C#, no UnityEngine, double precision, deterministic. Grid, capture solver, trail
    geometry, event engine, bots, traits.
  - `PainterIO.Runtime` (`Assets/Scripts/Runtime`): GameDirector, GameSession, render, actors, UI, audio, probe.
  - `PainterIO.Editor`: Builder, ShaderCheck.
  - Tests in `Assets/Tests/EditMode` and `Assets/Tests/PlayMode`.
- **Shaders:** `Assets/Resources/Shaders/`, loaded with Resources.Load, never Shader.Find.
- **Font:** OFL Nunito in `Assets/Resources/Fonts/`.
- **Tooling:**
  - `tools/unity.ps1`: an exclusive Unity lock wrapper. Unity is single-instance; always call it from PowerShell, because Git Bash can hang
    on this machine.
  - `tools/verify.ps1`: the full verification, step by step (dotnet, setup, editmode, playmode, buildwindows, probe, probe-fire,
    probe-electric, perfslope, android).
  - `tools/CoreTests/`: a dotnet test project that runs the Core tests outside Unity.
  - `tools/run.cmd` launches `Build/Windows`; `tools/play.cmd` launches the copy in `Build/Play`, which is safe to use while agents rebuild.
- **Useful player flags:**
  - `-biome liquid|fire|electric`, `-lasso 0|1`;
  - `-devshot <dir>` (scripted demo, one PNG per checkpoint);
  - `-probe -shotdir <dir> -fps <n>` (self-check: prints `[ProbeResult]` and `[ProbeHash]`);
  - `-quality high|medium|low`, `-mute`;
  - `-sparkFactor`, `-roundDuration`, `-ringInterval` (test overrides).
- **Determinism anchor:** the classic probe hash is `246577239DE179C4`. It must be equal at -fps 30 and -fps 144.

## 8. Status (end of wave C, wave D running)

- **Done and verified (Gate C, verify OVERALL PASS):**
  - tests: 316 dotnet Core, 493 EditMode and 8 PlayMode, all green;
  - probes pass in the three biomes with the same hash at 30 and 144 fps;
  - per-pixel cost on Medium: liquid 2.14, fire 2.66, electric 2.36 ms per megapixel;
  - builds: Windows 93.8 MB, APK 32.5 MB.
- **Wave D running:** biome traits in Core (with an adversarial verifier), the liquid drop look and the electric base arcs. Then traits wired
  into the runtime (options, matrix, generic visuals), a gate with a per-biome bot balance report, and a rebuild.
- **Never checked on a real Android device:** performance, touch, haptics, safe area, GLES3 fallback (see `docs/playtest_7_7.md`).
- **Sounds never listened to by a human:** they are only checked numerically.

## 9. Open decisions (owned by the designer)

1. **Game name.** Options: keep "Painter IO", or Splash.io, Drip.io, Spark.io. The logo (wordmark, per-biome variants, app icons) waits for
   this choice.
2. **feel-01.** A longer slow motion when a cut lands close behind the pearl, and a "cut right behind you: caught in 0.2 s" results line.
3. **feel-11.** A final standings list on the results screen.
4. **After the device playtest:** tune the traits and the bot difficulty, and decide whether the lasso should be on by default.

## 10. Glossary (French UI term -> meaning)

| French UI term | Meaning |
|---|---|
| fil / trait | trail (thread in the liquid look) |
| perle | the pawn head |
| flaque / base | territory |
| étincelle | the spark of La Revanche (the retraction front in the liquid look) |
| coupure / couper | cut |
| boucle | the loop being drawn |
| poche | lasso pocket |
| anneau | ring bonus |
| rentrer | get back home |
| Règles classiques | all biome traits off |
| Réglages de test | hidden test settings |
