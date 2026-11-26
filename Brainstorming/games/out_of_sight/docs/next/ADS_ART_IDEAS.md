# Out of Sight - art ideas from the promo ads

Date: 2026-11-25. Analysis only: no game file, scene, asset or script was changed, nothing was run in Unity.

Sources: every file in `Assets/Resources/Ads`, a few existing captures under `Build/shots`, and a skim of the runtime code
that draws the house. Each idea below names the ad and the timestamp that inspired it, the files or systems it would touch,
an effort (S / M / L), an impact (low / med / high) and the Android performance risk.

## 0. Material studied

| Alias | File | Length, size | What it is |
|---|---|---|---|
| REAL | `Out of Sight 2026-11-25 11-17-29.mp4` | 63 s, 1920x1200, 59.94 fps | **Confirmed real game capture** (the baseline): title screen with the kitchen tour (0:00-0:04.5), level select (0:06-0:09), level 10 "Le chien" intro card (0:10.5), then gameplay with Paul and Rex (0:15-1:01) |
| POSTER | `out-of-sight-affiche-fr.png` | 1024x1536 | Key art: floor level hero chair, man with a yellow gaze beam, "Qui a bougé la chaise ?" |
| S5 | `out_of_sight_ad_seedance_25.mp4` | 5 s, 854x480 | Hero chair in a sunbeam, woman's gaze cone, end card |
| S30 | `out_of_sight_ad_seedance_25_flash_30s.mp4` | 30 s, 530x794 | Chair, Claire, robot, two red chairs, Labrador, doormat, stool in kitchen, office chair, end card |
| GO | `out_of_sight_ad_google_omni.mp4` | 10 s, 640x360 | Low hero shot, then the dollhouse seen from outside, zoom out with confetti |
| GH | `out_of_sight_ad_gemini-omni-1.2-flash-15s-horizontal.mp4` | 15 s, 640x360 | Uses the real HUD; living room, kitchen, dining room, dogs, night rooms, confetti end card |
| GV | `out_of_sight_ad_gemini-omni-1.2-flash-15s-vertical.mp4` | 15 s, 360x640 | Uses the real HUD; herringbone, kilim rug, Labrador, SUCCESS banner, night kitchen, spotlight end card |
| WAN | `out_of_sight_ad_15s-wan_30.mp4` | 15 s, 1174x1764 | Pixar-like characters, robot, three red chairs, Labrador, gauge, doormat glow, night lamp |

Contact sheets (one frame every 1.5 s for REAL and S30, every 1 s for the others, every 0.5 s for S5) are in the session
scratchpad, `...\scratchpad\adframes\` (`real_01.png`, `real_02.png`, `seed5_01.png`, `seed30_01.png`, `gomni_01.png`,
`gemh_01.png`, `gemv_01.png`, `wan_01.png`, `poster_small.png`, `ingame_shots.png` = four `Build/shots` captures:
night level 20 start and overview, level 12 overview, level 17 corridor).

## 1. What the ads do better

The gemini ads (GH, GV) were clearly built from the game: same HUD (Grincement capsule, eye, Soupçon capsule), same cream
serif title, red lacquered chair, Claire in a teal jacket, Hugo with his phone, the woman in a dress, the black Labrador, the
robot vacuum, the rocking chair, the floor lamp, wooden casement windows onto a garden, the green doormat. So the brand is
already consistent. The gap is in light, density, materials, effects and framing:

- **Lighting mood.** Every ad shot has one obvious low warm key light: a golden sun raking through the window, long crisp
  shadows of the chair and window bars across a glossy floor (POSTER, S5 0-1 s, S30 0-7.5 s, GO 0-1 s). REAL is lit from
  a high sun (`Main.DaySunPitch` = 44 degrees) with a fairly even ambient: correct, readable, but flat (REAL 0:15-0:31).
- **Color palette.** The ads play complementary colors: honey and orange floors against navy, slate blue or teal walls and a
  blue sofa, with the chair as the only saturated red (POSTER, S5, S30, GO 0:04). REAL rooms are cream, beige and pale sage
  over light wood: low value contrast, and the most saturated color on screen is the blue x-ray hatching, not the chair
  (REAL 0:15-0:24, 0:34-0:46).
- **Materials.** Glossy lacquer chair with a visible sheen, varnished planks or herringbone with sun streaks, patterned
  textiles (kilim and Persian rugs, mustard cushions), colorful book spines (S30 9-16.5 s, GV 0-7 s, GH 5 s). REAL surfaces
  read matte, every rug shows the same tinted picture, sofas are plain.
- **Silhouettes.** The chair always has a backrest of 3 or 4 vertical slats and chunky splayed legs (POSTER, every end
  card). The in-game chair has posts and horizontal rails. Ad characters have big readable heads.
- **Props.** The ad rooms are lived in: framed pictures, curtains, wall shelves, full bookcases, plants, cushions,
  radiators, table and floor lamps (GO 0:04, GH 0-5 s, GV 0-7 s). REAL rooms are sparse with bare walls (REAL 0:27).
- **Character readability.** Faces and expressions sell the joke (WAN 1 s: Claire's surprised face, GO 1 s: "!" over the
  guard). REAL has the same "?" and "!" markers and speech bubbles, but characters are small and expressionless.
- **Vision cones.** The single most repeated motif: a warm yellow translucent beam that starts at the eyes and lands as a
  bright pool around the chair (POSTER, S5 1.5-3 s, S30 4.5-7.5 s and 22.5 s, GH 1-3 s, GV 1-2 s, WAN 9-11 s). REAL draws a
  flat fan on the floor at alpha 0.2 (`VisionConeView.Calm`), plus blue hatched sheets through walls.
- **UI and gauges.** GH and GV reuse the real HUD, which validates it. Additions worth taking: a ribbon banner on success,
  an eye pop above the watcher (S5 2 s), sparkles as confirmation. The S30 single bar and the WAN segmented bar are worse
  than the real HUD.
- **Camera framing.** Low, close, chair level shots with a little depth of field, and one establishing shot of the
  dollhouse from outside (GO 3-7 s). REAL plays from a high orbit (right for gameplay) and the title tour walks an empty,
  cold kitchen under a heavy vignette (REAL 0:00-0:04.5).
- **VFX.** Dust puffs when the chair moves (S30 22.5 s), sparkles on the exit (WAN 11 s, GH 9 s, GV 11 s), confetti on the
  win (GO 8 s, GH 14 s). REAL has no world effect at all (only the HUD sparks of `GaugeFx`).
- **Garden and windows.** Bright windows that bloom, flowers and a white picket fence behind the glass (GH 0-2 s, GV 0-2 s),
  and outside the house: cream clapboard siding, blue shutters, a green front door, flowerbeds and a stone path (GO 3-7 s).
  REAL has a good painted garden ring, but the house exterior is plain plaster on a flat lawn (REAL 0:21-0:31).
- **Night look.** Windows are the brightest cool element (deep blue moonlit sky), lamps glow with halos, warm pools against
  blue shadows (WAN 12 s, GH 10-12 s, GV 12-13 s). REAL night (Build/shots/night) has the warm pools, but dark windows, a
  near black garden and less warm/cool contrast.

## 2. Ranked improvement ideas

Ranking weighs visual impact (in play and in store captures) against effort and Android cost. The Android default tier is
Moyen (`QualityTier`: Mobile_RPAsset, hard shadows, 1024 shadow map, no SSAO, 30 fps). Budgets to keep in mind: 120
renderers / 25 materials per level, 160 / 33 for a house (`Tuning.Budget*`, checked by `Probe` / LevelAudit), 400
triangles per piece of furniture (`Tuning.FurnitureTriangleBudget`).

| # | Idea | Inspired by | Target files / systems | Effort | Impact | Android risk |
|---|---|---|---|---|---|---|
| 1 | Golden hour light and grade pass | POSTER; S5 0-1 s; S30 0-7.5 s; GO 0 s | `Main.cs` (BuildLighting, BuildVolume, ApplyLighting), `Tuning.LookSunIntensity`, optional `LevelDef.Lighting` preset | S | high | none |
| 2 | Title screen key art: hero chair in a sunbeam | POSTER; S30 27 s; GH 13-14 s; GV 14 s | `TitleCameraTour.cs`, `Resources/Levels/title_house.json`, `StreamingAssets/menu_camera.json`, `MenuFisheye.cs`, `Menu.cs`, `TitleLogo.cs` | S-M | high | none |
| 3 | Gaze beam cones (fake volume from the eyes) | S5 1.5-3 s; S30 4.5-7.5 s; GH 1-3 s; GV 1-2 s; WAN 9-11 s | `VisionConeView.cs`, `Assets/Settings/VisionCone.shader`, XRay features (keep the beam off the cone layer) | M | high | med |
| 4 | World juice VFX: hop dust, freeze poof, win sparkles and confetti | S30 22.5 s; WAN 11 s; GH 9 s, 14 s; GO 8 s | new pooled `WorldFx`, `FurnitureController.cs` (hop landing counter), `GameState.cs`, `LevelBuilder` doormat, `ProceduralArt.cs` (sprites in code) | M | high | low-med |
| 5 | Rug and doormat atlas (4 to 6 designs) | S30 10.5-16.5 s; GV 0-7 s; GH 5 s; GO 4 s | `TextureLibrary.cs` (rugColour), `PrimitiveKit.RugDetail`, `LevelDef` rug style, `LevelMiniature.cs`, new art in `Art/Environment` | M | high | low |
| 6 | Hero chair silhouette + lacquer reflections | POSTER; all end cards; S5 0 s | `SoftBodies.Chair`, `FurnitureKit.Chair`, `TitleLogo.cs`, `LevelMiniature` glyph, `RenderSettings.customReflection` in `Main` | S-M | high | low |
| 7 | Lived-in dressing: wall art, curtains, cushions, wall shelves, radiators | GO 4 s; GH 0-5 s; GV 0-7 s; S30 0-3 s | `LevelBuilderDressing.cs` (new wall host), `DecorKinds.cs`, `DressingLibrary`, editor DressingBuilder, level JSON, `WallFader` | M-L | high | low |
| 8 | Deeper wall palette and two-tone walls (dado, baseboard) | POSTER; S5; S30 0-9 s; GO 4 s | level JSON `wallFinish`, `TextureLibrary.cs`, `WallArray.cs`, `WallFinishes.shader` / `WallFinishesForward.hlsl` | S-M | med-high | none |
| 9 | Dollhouse exterior: siding, trim, shutters, flowerbeds, path | GO 3-7 s; GH 0 s | `LevelBuilder` (outside faces, caps), `WallArray` + `Art/Environment/Arrays`, `WindowModel.cs`, `LevelBuilderDressing`, `GardenBackdrop.cs` | L | high (zoomed out) | low-med |
| 10 | Night look 2.0: moonlit windows, lamp halos, moonbeams | WAN 12 s; GH 10-12 s; GV 12-13 s | `Main.ApplyLighting`, `GardenBackdrop` (night image instead of NightTint), `WindowModel.NightBlock`, `LampLight.cs`, `RoomLights.cs` | M | med-high | low-med |
| 11 | Window sunbeams and dust motes (cards, not volumetrics) | POSTER; S5 0-1 s; S30 0-3 s | `LevelBuilder.Window3D`, `WindowModel`, new shaft mesh, `QualityTier` gating | M | med-high | med |
| 12 | Contact shadows on mobile | S30 12 s; GH 6 s; all ads | `FloorDust.cs` (AO channel, enable on Moyen) or blob quads merged in the floor renderer | M | med | low |
| 13 | Camera beats: zoom-linked pitch, establishing shot, win and caught close-ups | GH 1-9 s; GV 1-11 s; GO 3-7 s; WAN 1 s | `OrbitCamera.cs`, `Hud` intro card, `GameState` (win, caught), `TitleCameraTour` spline code | M | med-high | none |
| 14 | "Watched" ring under the player furniture | WAN 9-10 s; GV 10-11 s | `GhostView.cs` rings or the `LitZoneView` pool material, `Vision` state | S | med | low |
| 15 | Calmer x-ray (lower alpha, finer hatch, edge line) | REAL 0:15-0:24, 0:34-0:46 (ads never show it) | `XRay_Cone.mat`, `XRay_Silhouette.mat`, `VisionCone.shader`, `XRayFlat.shader` | S | med | none |
| 16 | Dog readability: teal collar, faint fur sheen | WAN 6 s; GH 6-7 s; GV 8-9 s | `ModelKit.ApplyPetFurMap`, `DogFur.png` / Labrador GLB (ArtHandoff), `Tuning.DogConeColor` | S | med | none |
| 17 | Character expressions and a slightly bigger head | WAN 1 s; GO 1 s | `CharacterHead.cs`, `CharacterLook.cs`, `Art/Characters/Resources/*HeadWrap.png`, `Inhabitant.cs` | M-L | med | low |
| 18 | Varnished floors, herringbone in living rooms | GV 0-7 s; S30 3-9 s | `Tuning` floor smoothness, level JSON floor finish, needs idea 6's cubemap | S | med | none |
| 19 | Crisper mobile shadows (shadow distance) | POSTER and S5 crisp chair shadows | `Assets/Settings/Mobile_RPAsset.asset` (shadow distance 50 m) | S | med | none (gain) |
| 20 | Small story beats: chair "Chut..." bubble, eye pop above the seer, French win ribbon | WAN 2 s; S5 2 s; GH 14 s; GV 10 s | `SpeechBubbles.cs`, `VisionConeView` markers, `Hud` win panel, `Strings.cs` | S | med | none |
| 21 | Robot LED ring and underglow, Hugo's phone glow | GH 3-4 s; WAN 2-3 s; GH 4-5 s | `Robot.cs` (status light), Hugo's model / `CharacterLook` | S | low-med | none |
| 22 | Lawn mowing stripes, picket fence in the ring | GO 8-9 s; GH 0-2 s | `LevelBuilder` grass, `Resources/GardenBackdrop.png` | S-M | low-med | none |

### 2.1 Details

**1. Golden hour light and grade pass.** The cheapest way to get the ad mood. In `Main.cs`: lower `DaySunPitch` from 44 to
about 32-36 degrees for longer shadows, warm `DaySunColour` (1, 0.87, 0.67) toward (1, 0.80, 0.58), push
`DayAmbientSky` cooler and a bit darker so the shadow side goes blue; in `BuildVolume` raise `ColorAdjustments.saturation`
from 11 to about 15-18 and add `SplitToning` or `ShadowsMidtonesHighlights` (shadows toward teal, highlights toward amber).
Keep Neutral tonemapping and the bloom threshold above 1: `Main.LookProblems` enforces both (PRD 8.4). URP bakes every grading
override into the 32^3 LUT, so the extra override costs nothing per pixel. Option: a third `LevelDef.Lighting` preset
("golden") next to day and night, for variety across the 25 levels. Check with captures that the longer shadows never hide
the chair, and update the look tests (`ProbeTestsM7Look`, `ProbeTestsM7Quality`) that pin these values.

**2. Title screen key art.** REAL 0:00-0:04.5: the tour shows an empty kitchen corridor with a fluorescent tube, a strong
vignette and fisheye, and no chair. Every ad end card and the poster show the red chair as the hero in a warm living room.
Start or hold the tour (`title_house.json` waypoints, `TitleCameraTour`) in the living room: the red chair in a sunbeam by
the blue sofa and the bookcase, one decorative calm cone at its feet (the tour hides cones today), lower vignette and
fisheye strength (`menu_camera.json`). Optional tagline "Qui a bougé la chaise ?" under the logo (POSTER). First
impression and store video for free.

**3. Gaze beam cones.** Keep the floor fan as the rule display and add a beam: triangles from an apex at the eyes (about
1.6 m for humans, 0.5 m for the dog) to the fan's outer vertices (already clipped by the occlusion recast), with an alpha
gradient that brightens toward the floor, plus a brighter rim on the fan's far arc (the "pool" edge of GV 1-2 s). Flag the
beam vertices in a spare UV channel of the same fan mesh (the fan already passes `ConeLook` through UV1.w), so it costs no
material and no draw call. It must stay out of the x-ray `ConeFeature` (a beam drawn through walls would be noise).
Android: transparent overdraw grows when the camera is close; Haut full alpha, Moyen half, Bas off, fade it out at short
camera distance.

**4. World juice VFX.** `FurnitureController` already counts hop landings (it drives the hop tick sound): spawn 3-5 soft
beige dust quads at the feet that grow and fade in 0.4 s. A small poof when the furniture freezes inside a cone. On the win:
30-40 confetti quads (cream, teal, amber; no red, see section 5) and sparkles on the doormat. One pooled camera facing quad
mesh updated without allocation (the `GaugeFx` pattern) or one ParticleSystem with a 2x2 atlas, sprites drawn in code like
`ProceduralArt`. Cost: about 1 material and 1-2 renderers in the level budget; no lights, no collisions.

**5. Rug and doormat atlas.** Today every rug and the doormat show the same picture (`rug_modern_inset_border.png`,
`TextureLibrary.rugColour`), only tinted. Rugs are the largest patterned areas seen from the high camera. Build one atlas
with a kilim, a Persian medallion, a braided round rug (needs a disc mesh in `PrimitiveKit`), a striped runner, a coir
doormat with a border, and the current modern one; a `style` key per rug in the level JSON picks the atlas rect, same
shared Carpet material. Keep reds desaturated toward terracotta or rust so the chair stays the only saturated red.

**6. Hero chair silhouette and lacquer.** `SoftBodies.Chair` builds posts and horizontal rails (342 triangles). Replace the
rails with a top rail and 3 vertical slats, slightly thicker splayed legs, within the 400 triangle budget; update the title
logo chair (`TitleLogo.cs`) and the level select glyph (`LevelMiniature`) to the same silhouette. Lacquer: `PlayerSmoothness`
0.7 and `LacquerSmoothness` 0.9 are set, but at runtime `RenderSettings.skybox` is null, no custom reflection exists and many
renderers turn reflection probes off, so glossy surfaces mostly catch only the sun's specular lobe (verify in a capture).
A tiny warm interior cubemap (64-128 px, day and night variants) as `RenderSettings.customReflection` gives the ad sheen to
the chair, the window glass and varnished floors; URP Lit already samples the reflection, so no extra cost.

**7. Lived-in dressing.** Missing kinds compared to the ads: framed prints (one print atlas, 2-3 sizes), curtains on
living room and bedroom windows, a wall shelf with books and a plant, radiators under windows, a wall clock, two accent
cushions per sofa (mustard, as GH 0 s and GV 3 s). Decor hosts today are props and the floor; add a wall host in
`LevelBuilderDressing`, with automatic rules (a print centred over each sofa and bed, curtains on every window of those
rooms) to avoid per-level hand placement. Merge into the wall material renderer like the current dressing (no material),
fade with `WallFader`, never on the Occluder layer, no collider.

**8. Wall palette and two-tone walls.** (a) S: use the deeper finishes that already exist (`wall_deco_arches_blue`,
`wall_sage_ribbed`, `wall_linen_pinstripe_olive`) in living rooms through the level JSON, so the red chair sits on blue or
green instead of beige. (b) M: a dado rail at about 0.9 m with a darker lower band and a baseboard, chosen by height in
`WallFinishesForward.hlsl` (no geometry), or a baseboard vertex band in the wall faces.

**9. Dollhouse exterior.** Outside faces and caps are plaster today. Add a clapboard siding slice for outside faces, a white
trim on the caps, a stone plinth band at the foot, louvered shutters on outer windows (merged into the `WindowModel` frame
mesh, wall material), flowerbed strips with low poly bushes and flowers along the facades, stepping stones from the exit
door into the garden. Matters when the camera zooms out and in every store screenshot. Check the Android size of the wall
arrays first (`wall_colours.png` 12.5 MB and `wall_normals.png` 8.8 MB as sources) before adding slices.

**10. Night look 2.0.** Replace the darkening `GardenBackdrop.NightTint` by a night picture (deep blue sky, moon, stars in
`GardenSky`) bright enough for the glass to read as a light source; raise the glass emission in `WindowModel.NightBlock`;
make lamp shades emissive above the 1.15 bloom threshold for halos; blue moonbeam cards from the windows (idea 11); tiny
emissive accents (robot LED, Hugo's phone).

**11. Window sunbeams.** One additive card per sunlit window along the sun direction (`SunYaw` 32 degrees) down to the
floor, soft gradient, very low alpha, merged into one renderer per level with one material; 10-20 drifting dust motes on
Haut. The window shaped light patches already exist through the sun shadows (REAL 0:42-0:46): the card only adds the air.
Overdraw risk on Moyen: thin, short cards, Bas off.

**12. Contact shadows.** `Mobile_Renderer` has no SSAO (only `PC_Renderer` has it), so furniture floats on Android. Either
add an AO channel to the `FloorDust` map (it already computes grime against walls) from prop footprints and enable that
keyword on Moyen (today Haut only), or bake soft blob quads under props into the floor renderer, plus one moving blob per
character.

**13. Camera beats.** Tie `OrbitCamera` pitch to zoom (closer means lower, down to about 30 degrees), which gives the ad
framing when zoomed in and keeps the overview zoomed out. A 2 s establishing move from outside the dollhouse to the chair
behind the intro card; a chair level close-up on the win with confetti; a quick push-in on the surprised human when caught.
Depth of field only during these beats, on Haut.

**14. Watched ring.** While the furniture stands inside a calm cone, a soft warm ring under it; red when it is seen moving.
On a phone the HUD eye is far from the action; the ring tells "freeze" where the eyes already are.

**15. Calmer x-ray.** `XRay_Cone.mat` draws (0.12, 0.30, 0.95) at alpha 0.38 with a heavy hatch: in REAL these sheets
cross walls and dominate the frame. Try alpha about 0.22, a finer hatch and a thin bright edge line so the shape still
reads; silhouettes a little softer than (0.22, 0.52, 1, 0.85). Pillar 2 (docs/CONTRACT_M3.md 6) stays: validate with
captures.

**16. Dog readability.** A collar in the dog's cone teal (`Tuning.DogConeColor`), not the ads' red or orange: it ties the dog
to its cyan cone and outlines the black Labrador on dark floors and at night. A faint fur sheen helps too.

**17. Character expressions.** `CharacterHead` wraps one face image: add 2 alternative faces (surprised on "!", squint on
"?") selected by UV offset through the property block, and scale heads about 10-15 % for readability from the high camera.

**18. Varnished floors.** With idea 6's cubemap, raise `ColourWoodSmoothness` (0.3), `ColourParquetSmoothness` (0.35) and
`HerringboneSmoothness` (0.35) to about 0.45-0.5; use `floor_herringbone` in living rooms.

**19. Crisper mobile shadows.** `Mobile_RPAsset` spends a 1024 map on 50 m of shadow distance with one cascade, while a
house fits in about 20-25 m: lowering the distance to the farthest camera view actually needed (from
`Tuning.CameraMaxDistanceHouse` plus the house size) roughly doubles shadow sharpness for free. PC already uses 30 m.

**20. Story beats.** The chair "thinks" "Chut..." when it freezes inside a cone (WAN 2 s, through `SpeechBubbles`); an open
eye pops over the watcher that sees it (S5 2 s) next to the existing "!"; a French ribbon "Pas vu, pas pris !" on the win
panel (GH 14 s).

**21. Robot and phone glow.** The robot's status light (radius 0.012 m in `Robot.cs`) is invisible from the play camera:
an emissive rim ring and a soft additive floor disc at night. Hugo's phone screen as a small emissive quad.

**22. Lawn.** Alternating tint bands (mowing stripes) on the grass and a picket fence painted into the garden ring.

## 3. Quick wins (cheap, high impact)

1. Golden hour grade and sun (idea 1): a handful of constants in `Main.cs`, zero runtime cost.
2. Reflection cubemap for the lacquer chair, glass and floors (part of idea 6) and the floor smoothness bump (idea 18).
3. Title tour opening on the hero chair in a sunbeam, lighter vignette (idea 2).
4. Deeper wall finishes in living rooms through the level JSON (idea 8a).
5. Mobile shadow distance (idea 19).
6. Calmer x-ray material values (idea 15).
7. Teal dog collar (idea 16) and robot LED ring (idea 21).
8. Watched ring under the chair (idea 14).
9. Hop dust puff alone (the first slice of idea 4).

## 4. Bigger projects

- Gaze beam cones (idea 3), M: the strongest link between the ads and the game.
- VFX pack complete (idea 4), M.
- Rug and doormat atlas (idea 5), M: needs new art.
- Chair silhouette (idea 6), S-M, but touches the logo and the level select glyphs.
- Wall dressing (idea 7), M-L: art sourcing plus placement rules.
- Two-tone walls (idea 8b), M.
- Dollhouse exterior (idea 9), L.
- Night look 2.0 (idea 10) and sunbeams (idea 11), M each, best done together (same card system).
- Contact shadows (idea 12), M.
- Camera beats (idea 13), M.
- Expressions (idea 17), M-L.

## 5. Do not copy

- **Several red chairs or a red stool next to the chair** (S30 12-16.5 s, WAN 3-4 s, GV 6-7 s): breaks PRD 7.2 (only the
  player furniture is red, found instantly). Decoys stay non red; confetti and rugs avoid saturated red.
- **Green as the only success cue and a gauge that turns green as it fills** (WAN 11 s glowing dome, S30 19.5-22.5 s, GV
  10-11 s): full means danger in the game, and AX3 keeps the exit marker amber, never green beside the red player. If the
  doormat glows, pair it with a shape cue (ring, sparkles).
- **English or garbled text**: "SUCCESS" (GV 10 s), "Creak" (GV 12 s, GO), "GOAL" on the mat (GH 8 s), "Ce meible" (S30 0 s),
  "est vivent" / "viveant" (WAN 0-2 s), "persone" / "personn" (S30 27 s, S5 4 s), "Pas vu, pas prié" (WAN 14 s), a garbled
  label (WAN 9 s), the "AI generated" watermark (S5). The game is French first through `Strings.cs`.
- **Real volumetric fog, screen space reflections, mirror floors, bokeh depth of field everywhere, motion blur** (WAN 8 s):
  too costly for Moyen at 30 fps and blur hurts readability. Fake them with cards, a cubemap and short camera beats.
- **The floor level hero camera as the gameplay camera** (POSTER, S5, GO 0 s): perfect for the menu and short beats, but
  cones and routes need the high view.
- **Pixar grade faces and acting** (WAN 1 s): out of scope for the Quaternius bodies; 2-3 face frames are enough.
- **Ceilings and pendant lamps in the gameplay view** (GV 0-2 s): `RoomCeilings` already hides ceilings from above; keep
  them for low cameras and the menu.
- **The fully zoomed out roofless overview** (GO 8-9 s): the chair is a dot on a phone.
- **A cat on the windowsill or other animals as decor** (GV 12 s): anything animal shaped reads as a watcher.
- **The S30 and WAN gauges**: the real two capsule HUD is better, and GH and GV already prove it works in an ad.

## 6. Technical issues with the Ads folder

1. **Everything under a Resources folder ships in the build.** `Assets/Resources/Ads` holds 7 MP4 (147.9 MB) plus the poster
   PNG (1.8 MB): about 150 MB, mostly the 93 MB real capture (63 s, 11.6 Mbps) and the 36 MB WAN clip (19 Mbps). H.264 does
   not compress further, so the APK or AAB grows by that much and runs into Google Play's base module download size limit
   (check the current Play Console figure).
2. **Orphan meta and a dead config path.** `out_of_sight_ad.mp4.meta` (guid d85e0508168ed2e41ab0e6c27780e0ad) has no mp4,
   while `AdConfig.SimulatedVideo` defaults to "Ads/out_of_sight_ad" and `Resources/Config/ads.json` sets the same
   `simulatedVideo`. `Resources.Load<VideoClip>` returns null and `SimulatedAdProvider` falls back to the text card without
   any warning. Unity will also delete the orphan meta on the next refresh, losing that GUID.
3. **Not imported, not tracked.** The 7 MP4 and the PNG have no .meta yet, and git shows `?? Assets/Resources/Ads/` and
   `?? Assets/Resources/Ads.meta`: decide where they live before Unity imports them and creates GUIDs.
4. **Android decode compatibility.** REAL is H.264 Main level 5.0 at 1920x1200, 59.94 fps; WAN is H.264 High level 4.2 at
   1174x1764 (width not a multiple of 16), 19 Mbps. Low end hardware decoders can refuse these, and the meta has no
   transcode settings (`targetSettings: {}`). A shipped house ad should be at most 720p, 30 fps, H.264 Main or Baseline,
   about 3 Mbps or less, with standard dimensions (1280x720 or 720x1280).
5. **Length versus policy.** `ads.json` has `preferredMaxDurationSeconds` 15 and `skippableAfterSeconds` 5, but the
   simulated provider plays a clip for its own length: S30 lasts 30 s and REAL 63 s.
6. **Content.** The AI clips carry typos, English labels and an "AI generated" watermark (S5): not shippable as house ads.
7. **Minor, same cause.** About 100 `test_*.json` levels under `Resources/Levels` also ship (small), and
   `Resources/GardenBackdrop.png` is a 6.6 MB 4096x1024 source: check its Android compression.

Suggested fix: move the folder out of `Assets` (for example `Marketing/Ads/` at the repo root, ideally with Git LFS), and keep
at most one short re-encoded clip at `Assets/Resources/Ads/out_of_sight_ad.mp4`, which matches the existing meta, GUID
and config path. Or set `simulatedVideo` to "" to keep the text card.

## 7. Suggested order

1. Quick wins 1 to 5 together, then compare captures (`Build/shots`) against POSTER and S30 0-7.5 s.
2. Gaze beam cones and the VFX pack (ideas 3 and 4): they make gameplay captures look like the ads.
3. Rug atlas, chair silhouette, wall dressing (ideas 5 to 7): content passes, can run in parallel.
4. Night 2.0 with sunbeams, then the dollhouse exterior and the camera beats.
