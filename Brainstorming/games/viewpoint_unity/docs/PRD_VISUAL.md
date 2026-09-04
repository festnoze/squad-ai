# PRD - VIEWPOINT Visual Upgrade

Product requirements document. Version 1.0, 2026-09-04.

This document specifies how to take the Unity port of VIEWPOINT from a
faithful but flat-shaded prototype to a game that looks professionally made,
using what Unity's Universal Render Pipeline offers and the original Godot
build never had. It changes NOTHING about the rules: `docs/PRD.md` remains the
gameplay contract and every number in it stays true. This document only
changes what the player sees.

It was written after the port reached functional parity (101 EditMode tests,
29 PlayMode tests, 0 design defects, player verified by screenshot) and after
an honest look at those screenshots. Section 1 is that look.

---

## 0. How to read this document

- Section 1 : what the game looks like today, with evidence. Read it first.
- Section 2 : the target look, in words and references.
- Section 3 : the constraints that every item below must respect. The first
  one is not negotiable.
- Section 4 : the improvement catalog, by domain. Every item has an id, the
  current state, the target, the technique, a priority, an effort estimate and
  an acceptance criterion a reviewer can check.
- Section 5 : the roadmap, in tiers, cheapest and most visible first.
- Section 6 : how the result is verified, because "it looks better" is not a
  criterion.
- Section 7 : risks. Section 8 : what this document does not cover.

Priorities: **P0** transforms the look for almost no effort, do it first.
**P1** is what makes the game read as professional. **P2** is polish that a
player notices without naming. **P3** is optional and gated on a decision.
Effort: **S** under half a day, **M** one to two days, **L** three days or
more, for one engineer who knows URP.

---

## 1. Where the game stands today (visual audit)

Evidence: the six frames written by `VIEWPOINT.exe --shot` on 2026-09-04
(`Build/Windows/Shots/`) and the project's rendering settings.

### 1.1 What the frames show

| observation | consequence for the player |
|---|---|
| Every surface is one flat color. No grain, no roughness variation, no normal detail. Platforms read as plastic blocks, crates as painted foam. | Nothing feels like a material. The world has no scale cue except the player's height. |
| Every edge is razor sharp. Boxes meet the sky with a one pixel line. | The eye reads "primitives", not "architecture". |
| Emissive materials do not glow. The amber battery, the lavender shimmer, the teleporter ring are lit surfaces and nothing more. | The three most important objects in the game do not draw the eye. |
| Objects do not sit in the world. No contact darkening where a crate meets the floor, where a cage meets its platform, under the hovering polaroid. | Everything looks pasted on. SSAO is technically on and practically invisible. |
| Shadows band visibly. Looking straight down at the ground, the sun shadow shows diagonal stripes (acne) and the polaroid casts a large hard blob with a blurred rim. | Reads as a rendering bug even to someone who cannot name it. |
| The sky is a two color gradient with no sun, no clouds, no haze band. | It is a background, not a place. |
| Below the islands is a flat grey-blue plane meeting the sky in one hard line. | The islands are supposed to float. They stand on a floor. |
| Distant decor islands are as sharp as the near ones. Fog is set but its density (0.0012, squared) is imperceptible at 40 m. | No depth. The world is a tabletop. |
| The skirt under each platform is a darker box. | The one thing meant to say "terrain" says "second box". |
| The teleporter is a cylinder, a torus, a pillar and a text label. The battery is two cylinders. The camera is three boxes. | Functional, and exactly as the design specified, but nothing more. |
| The polaroids show their rendered pictures correctly, which is the one thing that already looks right. The frame is a flat white box. | Almost there. Paper would finish it. |
| HUD and menu are white system font with a black outline over a dim. | It reads. It does not look designed. |
| Nothing moves except the hover bob of pickups and the ring spin. Placing a photo, carving a wall, breaking a cage, picking up a battery, charging the teleporter: none has a visual event. | The game's best moments are silent. |

### 1.2 What the settings say

Read from `Assets/Settings/PC_RPAsset.asset`, `PC_Renderer.asset`,
`DefaultVolumeProfile.asset` and `Assets/Scripts/Core/Environment.cs`.

| setting | today | note |
|---|---|---|
| MSAA | off (`m_MSAA: 1`) | quality tier `antiAliasing: 0` too |
| HDR | on | good, and unused by anything |
| Color grading mode | LDR, LUT 32 | HDR grading needed for clean bloom |
| Shadow distance | 50 m | the RP asset value. The 120 m written by `Environment.cs` through `QualitySettings.shadowDistance` is a **no-op under URP**: URP reads the RP asset only |
| Shadow cascades | 4 | fine |
| Shadowmap | 2048 | fine for this world size |
| Shadow bias | depth 0.1, normal 0.5 (RP asset) | the `Light.shadowNormalBias = 1.5` in `Environment.cs` is also a **no-op under URP**. The banding in the frames is this |
| Soft shadows | on, quality high | good |
| SSAO | on: intensity 0.4, radius 0.3, samples Low, blur Low, depth-normals source | present, far too faint to seat anything |
| Bloom | intensity 0 | off |
| Vignette | intensity 0 | off |
| Color adjustments | all neutral | off |
| Tonemapping | Neutral | correct, keep |
| Fog | exponential squared, density 0.0012, `sky_horizon` | imperceptible |
| Ambient | trilight from the palette at 0.8 | flat but correct in hue |
| Sun | (45, -30, 0), 1.15, warm white | good direction, no atmosphere around it |
| Reflections | default (skybox) | fine; nothing is glossy enough to show them |
| Rendering path | Forward+ | good, supports many lights |
| Renderer features | SSAO only | Decal, Full Screen Pass available and unused |
| Shader Graph | installed (URP dependency) | the whole materials plan rests on it |

Two of those rows are bugs in the current code, not just missing polish:
`Environment.cs` believes it set a 120 m shadow distance and a 1.5 normal
bias, and set neither. Section 4.1 fixes both where URP actually reads them.

### 1.3 What is already right and must not be lost

- The palette. Cream, sand, lavender, coral, teal, amber, indigo: it is a good
  pastel set and it carries the whole gameplay language (section 3.1).
- Neutral tonemapping. The pastels survive it; ACES would grey them.
- The picture on each polaroid is the real rendered view of what it places.
  That identity is the game's central illusion and every change to the world's
  look must reach the picture studio too (section 3.4).
- Readability at a glance: from anywhere on a platform you can tell what is
  permanent, what a photo will carve, what a photo can copy, and where to
  stand. A professional look must sharpen that, never blur it.

---

## 2. The target look

### 2.1 In one sentence

**Clean stylized realism-lite**: soft matte materials with a fine visible
grain, warm key light against a cool sky, gentle bloom on the few things that
glow, atmospheric depth to the horizon, and props with enough tactile detail
to feel handled. Nothing photoreal, nothing noisy. Every surface should look
like a well-made model of the thing rather than the thing itself.

### 2.2 References (for direction, not for copying)

- **Viewfinder** (Sad Owl Studios): the obvious one. Soft-lit interiors and
  floating architecture, subtle grain, warm light, the polaroid as an object.
- **Superliminal**: clean flat-shaded volumes made rich by lighting, AO and a
  little surface noise. The closest to what this palette wants to become.
- **Manifold Garden**: how far pure geometry can go when edges, lighting and
  atmosphere are treated as the art.
- **The Witness**: saturated but disciplined color, materials that read as
  material from twenty metres, emissives used as guidance.
- **Islanders** / **Monument Valley 2**: the pastel-in-a-void aesthetic done
  well: soft ground planes, gradient skies with a horizon glow, gentle fog.

### 2.3 The one design rule

**Every visual choice is judged first on whether the color language still
reads at a glance.** A material that makes a lavender wall look richer but
harder to tell from a grey one is a regression, whatever it does for a
screenshot. See 3.1.

---

## 3. Constraints

### 3.1 The color language must survive (non negotiable)

The game teaches its rules in color and never in words (gameplay PRD 5.1):

| reading | meaning | today's palette |
|---|---|---|
| grey ground and grey blocks | permanent: a photo is added to them | `platform` (0.70, 0.71, 0.75) |
| pale, blue-leaning ground | carvable floor (the exception) | `platform_soft` (0.93, 0.92, 0.97) |
| lavender, faint shimmer | ephemeral: a photo carves it | `erasable` (0.69, 0.62, 0.86), emission 0.25 |
| darker steel grey cage | sealed: no photo ever opens it | `sealed` (0.58, 0.60, 0.66) |
| lead grey battery, inert | no film prints it | `battery_sealed` (0.50, 0.52, 0.57) |
| amber, glowing, bobbing | live battery | `battery` (1.0, 0.76, 0.29), emission 0.8 |
| teal flat slab | where to stand, standard route | `teal` |
| coral flat slab | where to stand, the critical shot | `accent` |

The palette unit tests pin the RELATIONS between these (grey is grey with a
component spread below 0.12; pale is 0.12 luminance above grey and leans
blue; steel is darker than grey and lead is far from amber). Those tests stay
green throughout this upgrade, and they are the floor, not the target.

Rules for every material and post-processing change:

- **The mean albedo of a surface stays its palette color.** Procedural grain,
  edge wear and hue jitter are zero-mean variations of bounded amplitude:
  luminance within **plus or minus 0.04**, hue within **plus or minus 4
  degrees** of the palette value. A block sampled and averaged over its face
  must still pass the palette relations.
- **Lavender stays the only thing that shimmers.** Emission on carvable
  matter is the tell; no other material gets an idle emissive.
- **Live amber stays the only thing that is warm and animated among
  pickups.** Lead stays still and cold. Whatever motion or glow the upgrade
  adds to batteries applies to live ones only.
- **Markers stay flat, saturated and on the ground.** They may become decals
  (crisper) but never raised, textured or dimmed.
- **Post-processing never shifts hue.** Bloom threshold above the palette's
  brightest non-emissive value, so only emissives bloom. No LUT, no split
  toning, no color filter. Contrast and saturation adjustments within plus or
  minus 5.
- **The grayscale test**: a frame converted to grayscale must still separate
  permanent (mid grey), pale (light), steel (darker), and the three must be
  tellable from lavender by the shimmer. Section 6.3 makes this a check.

### 3.2 Asset policy: a decision this document needs

The original ships **no binary asset**: every mesh, texture, picture and now
font is generated. The Unity port kept that promise, and it has real value
here: the whole game is reviewable as text, there is no import pipeline, and
the data files stay the only source of truth.

Most of what section 4 asks for is achievable without breaking it, because
Shader Graph can generate grain, wear, stratification and paper in the shader,
and every mesh in the game is simple enough to generate with bevels and
displacement in code. That is the **recommended path**, and the catalog is
written for it.

Two places where an asset would pay for itself:

1. **A UI font.** The engine's builtin font is legible and looks like a
   placeholder. One OFL-licensed geometric sans (Inter, Manrope, Outfit; a
   TTF of 100 to 300 KB) changes how the entire interface reads. This is the
   single highest-value asset in the whole document. **Recommendation:
   allow it**, as the one exception, documented as such.
2. **Surface textures** (a CC0 concrete, a wood, a brushed metal, from
   ambientCG). Faster to a rich look than authoring noise in Shader Graph, and
   a different look: more literal, less "made". **Recommendation: do not,
   unless the procedural result of Tier 2 disappoints.** Kept as Tier 6.

Decision required from the owner before Tier 5: font yes or no. Everything
before Tier 5 is procedural and needs no decision.

### 3.3 Performance budget

- **Target: 60 fps at 1600 x 900 with every item in this document enabled**
  on the development laptop (RTX 4050 Laptop GPU). The scenes are tiny (under
  a hundred renderers, no skinned meshes, no transparency to speak of), so the
  real cost is post-processing and SSAO, and the budget is generous.
- **Mobile tier** (`Mobile_RPAsset`, already in the project): the same look
  with SSAO off, bloom at half resolution, MSAA 2x, fog and sky unchanged
  (they are shader math, nearly free), procedural materials with the detail
  octave removed. The Android and WebGL modules are installed; this document
  does not target them but must not make them impossible.
- Every P0 and P1 item is measured (section 6.2) before it is accepted.

### 3.4 The picture identity

The polaroid picture IS the view the placed content will produce
(gameplay PRD 6.9). The picture studio (`PhotoSnaps`) renders with its own
camera, light and sky. **Any change to how the world looks must be applied to
the studio too**, or the picture stops matching the world it promises:

- materials: automatic, they are shared;
- sky: the studio camera uses the same skybox material;
- sun color and angle: the studio light copies the world light's values;
- post-processing: the studio camera renders to a texture, so bloom, AO and
  vignette apply to it only if its camera has post enabled and its renderer
  has the features. Decision: **the studio gets bloom and SSAO, not vignette**
  (a vignette on the picture would double with the polaroid frame).

Each item in section 4 says whether it touches the studio.

### 3.5 The harness stays green and grows

- All 101 EditMode, 29 PlayMode tests and the design audit stay green: no
  item here may change a collider, a position, a group, a string or a number
  the gameplay PRD pins.
- `verify-player.ps1` stays green and gains the visual checks of section 6.
- Every tier ends with a new reference screenshot set committed to
  `docs/reference/` as small JPEGs for side-by-side review (the one place
  binary files are welcome: they document, they do not ship).

---

## 4. Improvement catalog

Each item: **id** - current - target - technique - priority / effort -
studio impact - acceptance.

### 4.1 Rendering pipeline settings

These cost nothing but a few numbers and they are the largest single jump.

**V-PIPE-01 Anti-aliasing.** MSAA off; every edge shimmers. Target: no
visible edge crawl on the sharp box edges this game is made of. Technique:
`PC_RPAsset` `m_MSAA: 4`, camera `antialiasing = SMAA` (high) on top for the
specular and emissive edges MSAA misses; `Mobile_RPAsset` MSAA 2, no SMAA.
**P0 / S.** Studio: the studio camera gets the same MSAA (its target texture
must be created with the matching sample count). Acceptance: a frame of level
4 at 1280 x 720 shows no stair-stepping on the lavender wall's top edge at
100 percent zoom.

**V-PIPE-02 Shadows that do not band.** Diagonal acne when looking down; the
`Environment.cs` bias and distance are URP no-ops. Target: clean soft
shadows, no acne on flat ground, no peter-panning under blocks. Technique: in
`PC_RPAsset`, `m_ShadowDepthBias 1.0`, `m_ShadowNormalBias 1.0` (tune between
0.6 and 1.5 while watching a block's contact), `m_ShadowDistance 90` (the
decor islands sit at 30 to 40 m; 90 covers them with margin and keeps cascade
resolution), cascades 4 with splits 0.05 / 0.15 / 0.35; **remove the dead
`QualitySettings` and `Light.shadowNormalBias` lines from `Environment.cs`**
and leave a comment saying where URP reads these. **P0 / S.** Studio: the
studio light uses the same RP asset, nothing to do. Acceptance: the
looking-down frame shows no stripes; a crate on the ground has a shadow that
meets its base.

**V-PIPE-03 Ambient occlusion that seats objects.** SSAO on at 0.4 / 0.3 /
Low. Target: visible contact darkening under every crate, cage foot, socle
and polaroid, and in the inner corners of the cage. Technique: SSAO
intensity **1.6**, radius **0.6**, falloff 60, samples **Medium**, blur
**Medium**, source depth-normals, direct lighting strength 0.25, after-opaque
off (so it darkens ambient, which is the point). Mobile tier: off.
**P0 / S.** Studio: the studio renderer must be the same renderer asset so the
picture seats its props too. Acceptance: in level 6, the cage's bars show a
darker band where they meet the floor; a crate in level 4 has a soft dark
halo on the ground around its base.

**V-PIPE-04 HDR grading.** LDR LUT 32. Target: bloom without banding, no
clipping on the amber battery's highlight. Technique: `m_ColorGradingMode: 1`
(HDR), LUT 32 is fine. **P0 / S.** Acceptance: the bloom of item V-POST-01
shows no visible steps in its falloff.

### 4.2 Post-processing

All in `DefaultVolumeProfile.asset` (URP applies it globally).

**V-POST-01 Bloom on emissives only.** Nothing glows. Target: the amber
battery, the lavender shimmer, the charged teleporter ring, the filled cells
and the camera lens glow softly; nothing else does. Technique: Bloom
intensity **0.35**, threshold **1.05** (the brightest non-emissive palette
value after lighting stays below 1.0 in HDR; emissives at 0.8 to 2.0 energy
cross it), scatter 0.65, clamp default, high quality filtering on, downscale
half. **P0 / S.** Studio: on (a glowing battery in the picture is correct).
Acceptance: a frame with a battery in view shows a soft halo around it;
converting the frame to grayscale and thresholding at 0.98 selects only
emissive objects (section 6.3 automates this).

**V-POST-02 Vignette.** None. Target: a barely-there darkening of the
corners that pulls the eye to the crosshair. Technique: intensity **0.18**,
smoothness 0.6, rounded off. **P1 / S.** Studio: **off**. Acceptance: the
corners of a frame are darker than the centre by 8 to 15 percent luminance on
a flat sky.

**V-POST-03 Color adjustments.** Neutral. Target: a touch more contrast and
saturation so the pastels are confident rather than washed. Technique:
contrast **+6**, saturation **+5**, post exposure 0. **P1 / S.** Studio: on.
Acceptance: palette relations hold when sampled from a frame (section 6.3);
no hue shifts beyond 3 degrees on a sampled grey platform.

**V-POST-04 Rewind treatment.** A blue tint quad and a label. Target: the
world visibly runs backwards: desaturated, a slight chromatic split, a
faint film grain, the tint kept. Technique: a second Volume with priority 10
and weight driven by `Main` (0 to 1 over 0.25 s) holding Chromatic Aberration
0.4, Color Adjustments saturation -60, Film Grain type Thin1 intensity 0.25,
Lens Distortion -0.08. Add a subtle time-scrub scanline via a Full Screen Pass
feature only if it reads well; skip if it looks like a filter. **P1 / M.**
Studio: n/a. Acceptance: holding R produces a visibly different frame within
one quarter of a second; releasing restores the normal frame within the same
time; the HUD label remains legible.

**V-POST-05 Raised-photo focus.** The raised picture sits over a sharp
world. Target: while a photo is raised, the world beyond the picture softens
slightly so the eye stays on the picture and its edges. Technique: Depth of
Field, Gaussian, start 6 m end 30 m, max radius 0.6, weight 0 to 1 over 0.2 s
while `Placer.Raised`. Keep it subtle; this is also the moment the player
lines up a shot and must still read the world's edges. **P2 / S.** Studio:
n/a. Acceptance: with a photo raised, the far platform is measurably blurred
(edge contrast down at least 30 percent) while objects within 6 m are not.

**V-POST-06 Fall and depart transitions.** A 0.6 s black fade for both.
Target: leaving a level fades to **white** with a bloom bloom-up (the
teleporter light swallows the frame); falling fades to black with a brief
downward blur. Technique: fade color per transition; a Motion Blur volume
weight ramped to 0.5 during the fall's last 0.3 s. **P2 / S.** Acceptance:
the two transitions are visually distinct; the durations in the gameplay PRD
(0.6 s) are unchanged.

### 4.3 Sky and atmosphere

**V-SKY-01 A sky with a sun.** Two-color gradient, no sun. Target: the
existing gradient plus a soft sun disc at the light's direction with a warm
halo, and a brighter haze band at the horizon. Technique: extend
`GradientSky.shader` with `_SunDirection`, `_SunColor`, `_SunSize` (angular
radius about 1.5 degrees), `_SunHalo` (a wide `pow(dot, 24)` glow), and a
horizon band mixed by `exp(-abs(y) * 8)`. `Environment.cs` feeds the sun
direction from the light every frame it changes (it does not, but do not
hard-code it twice). **P0 / M.** Studio: same material, automatic.
Acceptance: the sun disc is visible when looking toward (45, -30, 0); its
halo blooms (V-POST-01); the horizon is brighter than the zenith.

**V-SKY-02 Procedural clouds.** None. Target: sparse, soft, slow cumulus
that read as very far away, not as a texture. Technique: in the same shader,
two octaves of 3D value noise sampled on the sky direction scaled by
`1 / (y + 0.05)` to flatten toward the horizon, thresholded softly, tinted
with `sky_horizon` on the lit side and `sky_horizon` darkened 10 percent on
the shadow side, scrolled at 0.004 units per second. Density 0.35. No
texture. **P1 / M.** Studio: automatic. Acceptance: clouds move perceptibly
over a minute and imperceptibly over a second; a cloud never has a hard edge;
the average sky luminance changes by less than 5 percent (the palette tests on
`sky_top` and `sky_horizon` are about the material colors, which do not
change).

**V-SKY-03 The void below.** A flat plane and a hard horizon. Target: the
islands float over a soft abyss: the ground half of the sky darkens gently
toward the nadir, with a band of haze just under the horizon and thin
drifting cloud wisps far below the islands. Technique: the sky shader's ground
half already exists; raise its curve so the darkening starts sooner, add the
haze band, and add a second, lower cloud layer sampled on `-y` with 60
percent density and a slightly darker tint. **P0 / S** for the gradient and
band, **P1 / S** for the lower clouds. Acceptance: looking down past a
platform edge shows no horizon line, and the eye reads depth below.

**V-SKY-04 Distance fog that shows.** Density 0.0012 squared, invisible.
Target: the decor islands at 30 to 40 m are softened and cooled toward the
sky, the level's own far platforms at 15 to 20 m are barely touched.
Technique: fog mode **Exponential**, density **0.018**, color the sky
horizon; or, better, a height-aware fog in a Full Screen Pass that adds
`sky_horizon` with strength `1 - exp(-d * 0.02)` scaled by
`saturate(1 - (y - (-2)) / 12)` so the abyss below the islands is foggier
than the air at platform height. Start with the built-in exponential fog;
promote to the height fog if the abyss still reads flat after V-SKY-03.
**P0 / S** (built-in), **P2 / M** (height fog). Studio: the studio camera
renders 36 m deep backdrops; fog applies and is correct there too. Acceptance:
the farthest decor island is at least 25 percent lower in contrast than the
nearest platform; a platform 15 m away loses under 8 percent.

**V-SKY-05 Sun flare.** None. Target: a restrained lens flare when the sun
is in frame. Technique: URP `LensFlareComponentSRP` on the sun with a
generated procedural flare (two soft circles, one streak), intensity 0.3,
fades out over 0.5 s of occlusion. **P2 / S.** Acceptance: visible only when
the sun disc is within the frame; never over the HUD.

### 4.4 Lighting

**V-LIGHT-01 Warm key, cool fill.** One directional light and a flat
trilight ambient. Target: a warm sun and a cool sky bounce that models every
box: lit faces warm, shaded faces faintly blue, undersides darker. Technique:
sun color (1.0, 0.94, 0.84) intensity 1.3; ambient trilight sky
`sky_top * 0.9`, equator `sky_horizon * 0.75`, ground `sky_horizon * 0.35`
darkened toward (0.55, 0.58, 0.66). Verify with a grey block: its top must be
brighter than its shaded side by at least 35 percent and the shaded side must
lean blue. **P0 / S.** Studio: the studio light copies these values; the
ambient is global. Acceptance: on a grey platform, top and side faces differ
by 35 percent or more in luminance, and the side's blue channel exceeds its
red channel.

**V-LIGHT-02 Reflection probe from the sky.** Default. Target: correct
specular on the few glossier surfaces (steel, polaroid gloss, the lens).
Technique: `RenderSettings.defaultReflectionMode = Skybox`, resolution 128,
refreshed by `DynamicGI.UpdateEnvironment()` after the sky material is set
(already called). **P1 / S.** Acceptance: the steel cage shows a faint sky
reflection on its top rails.

**V-LIGHT-03 Local light on the teleporter.** None. Target: a soft indigo
point light at the pad, intensity rising with charge, so the exit is a warm
spot in the level even from behind. Technique: `Light` point, range 6,
intensity 0.6 idle to 2.0 charged, color `teleporter_ring`, shadows off,
Forward+ handles it. **P1 / S.** Studio: n/a (teleporters are never in a
photo). Acceptance: the ground around a charged pad is visibly tinted.

**V-LIGHT-04 Battery glow light.** None. Target: a live battery casts a
faint amber pool on the ground under it. Technique: point light range 1.6,
intensity 0.5, color `battery`, on live batteries only (lead gets none, that
is the tell), shadows off. Budget note: a level has at most five batteries.
**P2 / S.** Studio: display-mode content gets no lights. Acceptance: the
ground under a live battery is warmer than the ground under a leaden one.

### 4.5 World materials (Shader Graph, procedural)

One Shader Graph, `Viewpoint/Surface`, replaces `Universal Render Pipeline/
Lit` for every `Materials.Solid` call. It keeps the same property names
(`_BaseColor`, `_Smoothness`, `_Metallic`, `_EmissionColor`) so `Materials.cs`
changes one `Shader.Find` string and the tests stay green, and it adds the
procedural detail below behind a `_Style` float that selects a look per
material family. Everything is **triplanar in world space** so carved
fragments and rotated ramps stay seamless with their neighbours, and so
nothing depends on UVs (generated meshes have none worth using).

Add the new shader to Always Included Shaders (section 1.2 of the port's
history says why).

**V-MAT-01 Ground and blocks: fine matte grain.** Flat. Target: a fine,
slightly directional grain like cast plaster or fine concrete, more visible
close up than far. Technique: two octaves of triplanar gradient noise
(scale 3.0 and 11.0 world units) into albedo at amplitude **0.03**
luminance (constraint 3.1) and into smoothness at 0.08; a normal from the same
noise at strength 0.15 for micro-shading; smoothness base 0.22. **P1 / M.**
Studio: shared material. Acceptance: at 2 m a platform shows visible grain; at
20 m it reads flat; the sampled mean color of a platform face stays within
0.02 of `platform`.

**V-MAT-02 Edge wear.** Sharp uniform edges. Target: block edges catch the
light with a hairline of brighter, smoother material, as a painted object
worn at its corners. Technique: the beveled mesh of V-GEO-01 gives real edge
geometry; the shader adds `saturate(1 - abs(dot(normal, up)))` blended with a
curvature approximation from the normal's derivative to brighten the bevel by
0.06 and raise smoothness by 0.2 there. **P1 / S** (given V-GEO-01).
Acceptance: a lit crate shows bright edges against a matte face.

**V-MAT-03 Hue jitter per block.** Every block of one color is identical.
Target: blocks of the same family differ imperceptibly, as real painted
pieces do. Technique: `_Style` includes a per-instance seed set by
`ErasableBlock` through a `MaterialPropertyBlock` (`_Seed = hash(position)`),
hue shift plus or minus 3 degrees and value plus or minus 0.025 (constraint
3.1). Fragments of a carved block inherit the parent's seed so a carve does
not recolor the survivors. **P2 / S.** Acceptance: two adjacent grey blocks
are distinguishable side by side and indistinguishable by category.

**V-MAT-04 Lavender that breathes.** Constant emission 0.25. Target: the
ephemeral matter is unmistakable: a slow pulse (period 3.2 s, emission 0.18
to 0.34) plus a fresnel rim of the same lavender at grazing angles, so a
lavender wall's edges glow faintly against the sky. Technique: in the shader,
emission multiplied by `0.26 + 0.08 * sin(time * 1.96)` and a fresnel term
`pow(1 - saturate(dot(N, V)), 3) * 0.4` added to emission, both gated by
`_Style == Ephemeral`. Bloom (V-POST-01) picks it up. **P0 / M.** Studio: a
photographed lavender plank pulses in its picture, which is correct.
Acceptance: the pulse is visible in a 4 s video; the grayscale test still
separates lavender from grey by the shimmer alone.

**V-MAT-05 Pale carvable ground.** A lighter flat color. Target: it reads as
lavender's pale cousin, not as a lighter grey: the same faint pulse at half
amplitude and a subtle diagonal hatch in the grain. Technique: `_Style ==
Ephemeral` at 0.5 emission scale plus a stretched noise octave. **P1 / S.**
Acceptance: in level 11 the pale bridge floor is identifiable as carvable
from the far island.

**V-MAT-06 Steel and lead.** Darker greys. Target: brushed metal for the
steel cage (anisotropic streak along the bars, smoothness 0.55, metallic 0.8)
and a dull, slightly greasy lead for the sealed battery (smoothness 0.35,
metallic 0.6, no emission, no motion). Technique: `_Style == Steel` and
`_Style == Lead` branches; the streak is a 1D noise along the object's long
axis via object-space UV. **P1 / M.** Acceptance: steel reflects the sky
(V-LIGHT-02) and reads as harder than grey ground; lead reads as heavier than
amber.

**V-MAT-07 Wood and stone props.** Flat brown and flat grey. Target: crates
and bridge decks show a soft plank grain and darker end grain; socles, stairs
and the pillar show a stone grain with faint veins. Technique: `_Style ==
Wood` uses a stretched 1D noise along the object's longest axis plus a fine
2D noise across, amplitude 0.05; `_Style == Stone` uses the ground grain at
double scale plus a low-frequency vein noise at 0.03. **P1 / M.** Acceptance:
a crate reads as wood from 4 m; the stairs read as stone.

**V-MAT-08 The painted backdrop as a painting.** A gradient quad. Target:
the placed backdrop wall reads as a painted sky on a panel: a faint paper
grain, a slight vignette toward its edges, a hairline lighter border where the
paint stops before the edge. Technique: `Viewpoint/Backdrop` unlit graph: the
gradient, plus grain 0.02, plus edge vignette 0.06, plus a 2 cm border band at
`sky_horizon` lightened 0.05. **P2 / S.** Studio: display mode uses the same
material. Acceptance: a placed backdrop is distinguishable from the real sky
at its edges and indistinguishable at its centre.

### 4.6 Geometry (generated meshes)

**V-GEO-01 Beveled blocks.** Sharp cubes. Target: every box has a small
chamfer (2.5 cm, or 12 percent of the smallest dimension if that is smaller)
so edges catch the light and the world stops reading as primitives.
Technique: `ProceduralMeshes.BeveledBox(size, bevel)` cached by size,
replacing the scaled unit cube in `ErasableBlock` and everywhere `Solid`
boxes are built (`PhotoContent`, `Cage` bars and rails, `Teleporter` pillar
and cells, pickups). Colliders stay exact boxes; the bevel is visual.
Fragments from a carve are new boxes and get their own bevel. **P0 / M.**
Studio: shared code. Acceptance: in level 4 the lavender wall's top edge shows
a distinct highlight line; the physics probe stages still pass (colliders are
untouched).

**V-GEO-02 Platform skirts as rock.** A darker box. Target: the underside
of each island is a rough, tapered rock mass, wider at the top, breaking into
a few facets, darker toward the bottom where it fades into the abyss.
Technique: `ProceduralMeshes.IslandSkirt(footprint, depth, seed)`: a
frustum of 8 to 12 irregular sides, vertices displaced by low-frequency
noise (amplitude 12 percent of the footprint), flat-shaded for facets,
material `_Style == Rock` (stone grain, darker base by a vertical gradient
baked into vertex color). Child of the platform block as today, so it
vanishes with it. **P1 / M.** Acceptance: from a platform edge, the island
below reads as a mass, not a box; the design audit still reports zero defects
(it reads data, not meshes).

**V-GEO-03 Decor islands as rock.** Two boxes each. Target: same rock as
V-GEO-02, with a thin pale cap and one or two low outcrops. Technique: reuse
`IslandSkirt` plus a cap slab with a slightly irregular outline. Positions
and sizes unchanged (they are data). **P1 / S** (given V-GEO-02).
Acceptance: distant islands read as terrain under the fog of V-SKY-04.

**V-GEO-04 Ground top lip.** The top face meets the skirt at a hard step.
Target: a 6 cm rounded lip around each platform top, slightly lighter,
suggesting a paved edge. Technique: part of `BeveledBox` with a larger bevel
on the top edges only (`bevelTop = 0.06`). **P2 / S.** Acceptance: platform
edges read as finished from the standing height.

**V-GEO-05 Cage bars as rods.** Square bars. Target: round rods with a
polished cap where they meet the rails. Technique: `ProceduralMeshes.Rod`
(cylinder, 10 sides) and small spheres at joints; collision unchanged (it is
the four wall boxes and roof, not the bars). **P2 / S.** Acceptance: the cage
reads as forged; the smoke stage that breaks the cage still passes.

### 4.7 Props

**V-PROP-01 The battery as an object.** Two cylinders. Target: a battery
you could pick up: a body with a wrapped label band (a slightly different
amber ring at mid height), a metal top cap, a small positive terminal, a
soft glow from within (V-MAT-04 style emission on the body, V-LIGHT-04
light). Lead: identical shape, lead material, no glow, no motion. Technique:
generated cylinders and a torus band; two materials. **P1 / S.** Acceptance:
live and lead batteries are identical in shape and unmistakable in nature.

**V-PROP-02 The polaroid as paper.** A white box. Target: a real instant
print: a paper-white frame with the wider bottom margin, a hairline shadow
gap between frame and picture, slightly rounded corners, a faint gloss on the
picture, and a soft drop shadow on the floor from the AO. Technique: a
generated rounded-rect frame mesh; picture quad inset by 1 cm and 3 mm behind
the frame face; frame material `_Style == Paper` (grain 0.015, smoothness
0.35); picture material smoothness 0.6. **P1 / M.** Studio: the studio
renders its own polaroid border into the picture (unchanged). Acceptance: a
polaroid in the world reads as printed paper at 1.5 m.

**V-PROP-03 The polaroid picture.** Correct but raw. Target: a picture that
looks printed: a faint paper grain over the render, slightly lifted blacks,
a 3 percent vignette, and the hairline chemical border instant prints have.
Technique: post-process the studio's readback in code (it already paints the
frame): grain via a small hash, blacks lifted by 0.02, vignette, a 2 px
darker line inside the frame. **P2 / S.** Studio: this IS the studio.
Acceptance: the picture is recognisably a print and still matches the placed
content to the eye when raised (the identity of gameplay PRD 6.9 is about
geometry, and this touches only tone).

**V-PROP-04 The camera item.** Three boxes. Target: a compact rangefinder:
a beveled body with a leatherette band (darker, grainier), a chromed lens
barrel with a glass disc that reflects the sky, a small viewfinder window, a
shutter button, the flash cube. Technique: generated primitives with three
materials (body dark grey, chrome steel style, glass smoothness 0.95 with a
faint teal tint). **P1 / M.** Acceptance: it reads as a camera from 3 m.

**V-PROP-05 The teleporter as a machine.** Cylinder, torus, pillar, text.
Target: a pad with a stepped base and an inlaid glowing ring track; a floating
ring of segmented indigo glass whose segments light up as batteries are
inserted (one segment per required battery, replacing the pillar cells'
job while the pillar keeps them as a readout); a soft vertical light column
inside the ring when charged (V-VFX-05); the label on a small floating plate.
Technique: generated meshes, `_Style == Glass` for the ring (smoothness 0.9,
emission driven by charge). **P1 / L.** Acceptance: the exit is the most
visually inviting object in every level; the "PRET" state is obvious from
15 m without reading the label.

**V-PROP-06 Markers as decals.** Thin slabs (1.4 x 0.06 x 1.4) that z-fight
at grazing angles and cast a step shadow. Target: crisp painted squares on
the ground, with a slightly worn edge, no thickness. Technique: URP Decal
Renderer Feature (add to `PC_Renderer`), a `DecalProjector` per marker with a
generated 128 x 128 square texture (soft inner edge, 6 percent noise) tinted
teal or coral; the physical slab is kept **invisible** because the design
audit and the level data treat markers as decor slabs and nothing about that
changes. **P1 / M.** Acceptance: a marker viewed from its own edge shows no
flicker; the audit still finds the markers.

### 4.8 VFX and feedback

The game's key moments have no visual event today. Each effect below is
short, readable, and never hides what it comments on.

**V-VFX-01 Placement.** Content appears instantly. Target: the frame of the
photo flashes as a thin bright rectangle at the placement plane and fades
(0.25 s); the new content resolves from a lavender-white edge glow to its
final material over 0.4 s (a dissolve driven by a `_Reveal` float in the
surface shader, seeded from the content root); a few soft dust motes drift
where the carve happened. Technique: a quad with an unlit additive material
sized to the frustum section at the near plane, scaled outward; `_Reveal`
animated by `PhotoContent`; a particle system of 20 to 40 motes with soft
alpha, 1.5 s life. **P1 / M.** Acceptance: the smoke probe stages that
raycast placed content immediately after `Place()` still pass (colliders are
present from frame one; only the look resolves over time).

**V-VFX-02 Carve.** Blocks vanish and fragments appear. Target: the cut
faces of the surviving fragments glow lavender-white for 0.6 s and settle; the
removed volume leaves a short puff of the block's own color. Technique:
fragments receive `_CutGlow = 1` decaying to 0; the shader adds emission on
faces whose world normal matches the hole's faces (passed as a plane list of
up to six). Simpler fallback: glow the whole fragment for 0.3 s. **P2 / M.**
Acceptance: a carve is legible as an event without obscuring the new opening.

**V-VFX-03 Cage break.** The cage disappears. Target: the bars flash
white, split into their rod segments and fall as rigid bodies for 1.5 s, then
retire (they are visual only; the real cage body is retired by the placer as
today, so the batteries are free immediately). Technique: on retire, spawn a
"debris" object of 12 to 20 rods with `Rigidbody`, random impulses, and a
timed `Rewind.Retire`. Debris joins no group. **P2 / M.** Acceptance: the
smoke stage that checks the cage is gone and the batteries are free passes
unchanged; the debris is gone within 2 s.

**V-VFX-04 Battery pickup and drop.** Instant. Target: on pickup, a brief
amber burst of 8 sparks toward the camera and a soft chime-shaped scale pop
of the HUD counter; on drop, the battery lands with a tiny dust ring.
Technique: a pooled particle burst; the HUD counter tweens scale 1.0 to 1.25
to 1.0 over 0.2 s. **P2 / S.** Acceptance: a pickup is felt without looking
at the HUD.

**V-VFX-05 Teleporter charge and departure.** The ring spins faster. Target:
each insertion lights a ring segment with a rising pitch of brightness; when
charged, a column of slowly rising indigo motes fills the ring and the ground
ring track glows; on departure, the column brightens to white over 0.4 s and
the fade to white (V-POST-06) takes over. Technique: particle system of 60
motes, cylinder emitter, 3 s life, upward drift 0.4 m per s, emissive
material; ring segment emission driven by `GameState.InsertedBatteries`.
**P1 / M.** Acceptance: charge state is readable from anywhere on the level.

**V-VFX-06 Viewfinder.** Dim, edge, brackets. Target: raising the camera
animates the brackets in from the corners (0.15 s), adds a faint frosted
ring at the frame edge, and the shutter closes as two black leaves for 0.12 s
on capture with a white flash frame; the new polaroid then slides up into
the raised position as if pulled from the camera (0.35 s). Technique: HUD
tweens; the polaroid slide is `Hud.SetPhotoView` with an animated offset.
**P1 / M.** Acceptance: capture is legible as an event; the photo appears in
hand within the gameplay PRD's same frame (the slide is presentation only:
`Placer.HeldId` is set at once).

**V-VFX-07 Hover pickups.** Bob and spin. Target: a soft ground halo (a
decal disc, 6 percent alpha of the object's color) under each hovering
polaroid, battery and camera, breathing with the bob. Technique: a
`DecalProjector` per pickup driven by the same bob phase. **P2 / S.**
Acceptance: a pickup's height above ground is readable from its halo.

**V-VFX-08 Ambient life.** Static world. Target: a very sparse field of
drifting dust motes in the air of every level (30 to 50 particles over the
playable area, 2 percent alpha, 12 s life), and a barely visible heat-shimmer
above the teleporter pad. Technique: one particle system per level under the
level root; the shimmer is a small distortion quad using the opaque texture.
**P3 / S.** Acceptance: the world does not look paused when the player stands
still.

### 4.9 Motion and animation

**V-ANIM-01 Camera feel.** Rigid. Target: a subtle head bob while walking
(2 cm at 1.8 Hz, halved when sprinting), a 2 degree FOV widening when
sprinting (75 to 77, 0.25 s), a soft landing dip of 3 cm after a fall of more
than 1 m, and a 1.5 degree roll lag on quick yaw. All on the camera transform,
**never on the placer's anchor**: the placer stays the camera's child at
identity, so the anchor still equals the eye pose (gameplay PRD 6.4), and the
bob is included in the anchor the way it is in Viewfinder. **P1 / M.**
Acceptance: the smoke probe (which uses `SetLook` and `Teleport`, and reads
the placer's world transform) passes unchanged; a walking player's view moves
gently.

**V-ANIM-02 Pickup motion.** Linear bob. Target: bob eased with a sine
already, add a slow 4 degree pendulum tilt on polaroids and a faint scale
breath (plus or minus 1 percent) on live batteries. **P3 / S.**

**V-ANIM-03 HUD tweens.** Instant state changes. Target: every HUD change
animates: counters pop on change, the prompt fades in over 0.12 s and out
over 0.2 s, the held panel slides in from the right over 0.2 s, the banner
keeps its curve, the toast slides up 12 px as it appears. Technique: a small
tween helper in `Hud` (no package). **P1 / S.** Acceptance: no HUD element
appears or vanishes in one frame.

**V-ANIM-04 Raised photo motion.** The picture snaps to the square. Target:
raising eases the picture up from the held-card position to the square over
0.18 s with a slight overshoot; rotating rotates the picture with a 0.12 s
ease rather than a snap; lowering reverses. The placer's roll changes at
once (the anchor is not animated, only the picture). **P1 / S.** Acceptance:
the on-screen picture and the placer's roll agree at the end of every tween;
the roll-direction smoke stage passes.

### 4.10 The picture studio

**V-SNAP-01 Studio matches the world.** It has its own light and ambient.
Target: identical lighting to the world at all times. Technique: `PhotoSnaps`
reads the world light's color and intensity and the ambient from
`RenderSettings` at request time rather than owning constants; it enables
post-processing on its camera with bloom and SSAO on and vignette off
(section 3.4), which requires the studio camera to use `PC_Renderer` and the
Volume to be global (it is). **P0 / S.** Acceptance: a shot of a lavender
plank placed from where it was taken is indistinguishable in tone from the
original plank beside it (the geometry test exists; add a mean-color check of
the two in the shot probe).

**V-SNAP-02 Print look.** See V-PROP-03.

**V-SNAP-03 Studio resolution.** 512 x 512. Target: 768 x 768 with 4x
MSAA, so a raised picture at 547 px on a 900 px tall window is not upscaled.
Technique: constants in `PhotoSnaps`; the RenderTexture gets `antiAliasing =
4`. **P1 / S.** Acceptance: a raised picture shows no visible pixelation at
1600 x 900.

### 4.11 HUD

**V-HUD-01 Typeface.** Engine builtin font. Target: a geometric sans with
real weights. Technique: **gated on the section 3.2 decision.** If allowed:
Inter (OFL), regular and semibold, as a TTF in `Assets/Fonts/`, loaded by
`Fonts.Default` in place of the builtin, with `Outline` replaced by a
`Shadow` component (1 px, 60 percent) for a cleaner look. If not allowed: keep
the builtin and compensate with size, spacing and panels (the rest of 4.11
assumes either). **P1 / S.** Acceptance: every string of gameplay PRD 12
renders at the sizes it specifies; the French plural rules and accents-free
text are unchanged.

**V-HUD-02 Counters as a panel.** Bare text top left. Target: a single
rounded panel (generated 9-slice from a rounded-rect texture drawn in code)
at 60 percent dark with a battery glyph (a generated 16 x 24 icon: a rounded
rect with a nub) and a film-can glyph before the numbers; the pipe separator
replaced by spacing. Text unchanged. **P1 / S.** Acceptance: the strings of
gameplay PRD 12.1 are present verbatim; the panel occupies no more than
420 x 64 px at reference.

**V-HUD-03 Prompt styling.** Centered white text. Target: the interaction
prompt sits in a pill (generated rounded rect, 55 percent dark), fades in and
out (V-ANIM-03), and prefixes the key with a key-cap glyph (a small square
with "E" in it, drawn as a nested Text on a rounded rect). The French string
after the key-cap is unchanged. **P1 / S.** Acceptance: the prompt reads
against both a bright sky and the dark cage bars.

**V-HUD-04 Held panel.** Dark box with text and card. Target: the panel
becomes a translucent frosted card (a blurred copy of the frame behind it via
the opaque texture, or a simple 65 percent dark if the blur costs too much)
with the polaroid card lying on it (V-PROP-02's paper look on the card
texture) and the four control hints as key-cap glyph pairs in a row.
**P1 / M.** Acceptance: the hint string's four commands stay in the same
order and words.

**V-HUD-05 Crosshair.** A 5 px square. Target: a 6 px ring with a 2 px dot,
white at 85 percent, that shrinks to the dot alone while a photo is raised (the
square is the frame then) and turns into a small camera reticle (a circle with
tick marks) while the viewfinder is up. **P2 / S.**

**V-HUD-06 Rewind treatment.** Blue wash and label. Target: with V-POST-04
handling the world, the HUD adds a thin progress bar under the label showing
`AvailableSeconds` as a shrinking amber line, and the label gets a slow
"reverse" pulse. **P2 / S.** Acceptance: the label string is unchanged.

**V-HUD-07 Banner.** Two lines of text. Target: a thin rule line grows
outward under the title as it appears, and the subtitle fades in 0.15 s after
the title. **P2 / S.** Acceptance: the 4.5 s duration and curve are
unchanged.

### 4.12 Menus

**V-MENU-01 A place behind the menu.** The menu dims the live sky. Target:
the title and victory menus float over a slow orbit of a small diorama: a
generated three-island scene with a teleporter and two polaroids, lit like
the game, rotating at 2 degrees per second, blurred slightly (DoF) behind the
text. Pause keeps the live level behind a stronger dim (it is where the
player is). Technique: `Menu` asks `Main` for a `MenuDiorama` object (built
from the same builders as a level, on its own layer, rendered by a second
camera to a full-screen RawImage or directly with depth 1). **P1 / M.**
Acceptance: the title screen looks like the game, not like a settings page.

**V-MENU-02 Level grid with pictures.** Text buttons. Target: each unlocked
level button shows a small rendered thumbnail of that level from its spawn
(the picture studio can render it: build the level in the studio, shoot,
tear down; cache 25 textures at first title screen, 160 x 90 each), the
number and name below, a lock glyph for locked levels. Technique: extend
`PhotoSnaps` with `RequestLevelThumbnail(index)`; buttons 180 x 130 in a 5
column grid; the grid's label and the locked strings are unchanged.
**P1 / L.** Acceptance: every unlocked level's thumbnail is recognisably that
level; building all 25 for thumbnails takes under 2 s in total at first
launch and the result is cached for the session.

**V-MENU-03 Button states.** Flat buttons. Target: rounded buttons with hover
lift (scale 1.03, 0.1 s), a teal focus outline for keyboard focus, a coral
tint on the current level, locked buttons at 45 percent with the lock glyph.
**P1 / S.**

**V-MENU-04 Transitions.** Instant show and hide. Target: menus fade and
slide 16 px over 0.2 s; the title's letters settle in with a 0.4 s stagger on
first show only. **P2 / S.** Acceptance: Enter on the title still starts the
game within the same frame's input handling (the visual leads, the state does
not wait).

### 4.13 Level dressing (optional, additive)

Purely decorative additions that touch no collider, no group, no data the
audit reads, and are therefore invisible to gameplay. Each is a P3 and gated
on Tiers 0 to 4 being done and reviewed, because dressing before the base look
is right is how a game ends up busy.

- **V-DRESS-01** A few low pale posts (0.3 m) along the far edges of large
  platforms, spaced 4 m, as a scale cue (no collision).
- **V-DRESS-02** A thin painted line (decal) marking the platform edge lip.
- **V-DRESS-03** One or two small floating shards of the island's rock
  drifting slowly near the underside of each level's main platform.
- **V-DRESS-04** A far, very faint ring of larger islands at 120 m, fogged
  almost to the sky, so the horizon is not empty in every direction.

---

## 5. Roadmap

Ordered by value per effort. Each tier ends with a reference screenshot set
(section 6.1) and a green harness. Do not start a tier before the previous
one is reviewed on screen by a person.

| tier | scope | items | effort | what changes on screen |
|---|---|---|---|---|
| **0. Settings** | numbers only, no new code beyond deleting two dead lines | V-PIPE-01..04, V-POST-01..03, V-LIGHT-01, V-SKY-04 (built-in fog), V-SNAP-01 | 1 day | Edges stop shimmering, shadows stop banding, objects seat, emissives glow, the pastels gain confidence, distance softens. The largest single jump. |
| **1. Sky and light** | one shader, one script | V-SKY-01, V-SKY-02, V-SKY-03, V-LIGHT-02, V-LIGHT-03 | 2 days | A sun, clouds, an abyss below, an exit that lights its surroundings. The world becomes a place. |
| **2. Materials** | the Surface shader graph and its styles | V-MAT-01..07, V-GEO-01 | 4 days | Every surface reads as a material; every edge catches light; lavender breathes. This is where "professional" happens. |
| **3. Geometry and props** | generated meshes | V-GEO-02..05, V-PROP-01, 02, 04, 05, 06, V-MAT-08, V-SNAP-03 | 5 days | Islands become terrain, props become objects, markers become paint. |
| **4. Feedback** | VFX and animation | V-VFX-01..07, V-ANIM-01, 03, 04, V-POST-04, 05, 06, V-HUD-06 | 5 days | The game's moments become events. Placement, carve, break, pickup, charge, capture, rewind and fall each look like something. |
| **5. Interface** | HUD and menus; needs the 3.2 decision first | V-HUD-01..05, 07, V-MENU-01..04, V-PROP-03 | 4 days | The interface looks designed; the title screen sells the game; levels have faces. |
| **6. Optional** | gated | V-DRESS-01..04, V-VFX-08, V-ANIM-02, V-SKY-05, CC0 textures if Tier 2 disappoints | as wanted | Life and richness at the margins. |

Total for tiers 0 to 5: about **three weeks** for one engineer comfortable
with URP and Shader Graph, with review time. Tier 0 alone, one day, should be
done first and shown, because it changes the conversation about the rest.

---

## 6. Verification

"It looks better" is an opinion. These are the checks.

### 6.1 Reference frames

`VIEWPOINT.exe --shot` already writes six frames and a diagnostics file.
Extend the probe (`Assets/Scripts/Core/ShotProbe.cs`) with the moments this
document changes: a battery close up, the lavender wall at 4 m, a carve
result, a raised photo, the viewfinder, the charged teleporter, the rewind
mid-scrub, the title screen, the level grid. At the end of each tier, the set
is reviewed side by side with the previous tier's set and committed as JPEG
(quality 80, 1280 x 720) under `docs/reference/tier-N/`. A person signs the
tier off on those frames; nothing else counts as done.

### 6.2 Performance capture

The shot probe records `Time.smoothDeltaTime` over 120 frames on level 15
(the busiest) and level 25 and writes the 1 percent low. `verify-player.ps1`
fails if the 1 percent low frame time exceeds **20 ms** (50 fps floor for a
60 fps target) on the PC tier. Recorded per tier so a regression names its
tier.

### 6.3 Color language checks (automated, in the shot probe)

- **Mean albedo**: for one platform, one lavender block, one steel cage bar
  and one leaden battery in view, sample a 24 x 24 px patch of a lit face
  from the frame, average, and assert the palette relations from
  `PaletteTests` on the sampled values with a tolerance of 0.06 (lighting
  shifts everything; relations survive).
- **Grayscale separation**: convert the level 25 frame to grayscale; the
  sampled platform, pale ground, steel and lead patches must be pairwise at
  least 0.08 apart in luminance.
- **Emissive isolation**: threshold the HDR-graded frame's luminance at 0.98;
  the surviving pixels must lie within the bounding rectangles of emissive
  objects (batteries, lavender, the ring, the lens) plus the sun disc. Any
  other survivor is a bloom leak and fails.
- **Hue stability**: the sampled grey platform's hue must be within 4 degrees
  of the palette `platform` hue.

### 6.4 The existing harness

All of it stays green at every tier: 101 EditMode, 29 PlayMode, the design
audit, and `verify-player.ps1` including its zero-exception and eye-height
checks. A visual change that requires a gameplay test to change is a
gameplay change and does not belong to this document.

### 6.5 Studio identity

Extend the smoke probe's plank stage (stage 18): after placing the shot from
where it was taken, sample the mean color of the copy and of the original in
a shot-probe frame; they must match within 0.04. This is the test that the
picture still IS the world after every lighting and material change.

---

## 7. Risks

| risk | mitigation |
|---|---|
| Procedural materials make grey and lavender harder to tell apart at distance | Constraint 3.1 amplitudes; the grayscale check of 6.3; lavender's pulse is the tell and is kept exclusive |
| Bloom leaks onto pale ground or the sky's horizon band | Threshold above 1.0 in HDR; emissive-isolation check of 6.3; the horizon band is authored below 0.95 |
| Head bob (V-ANIM-01) moves the placement anchor and breaks the "picture equals placement" identity | The bob is ON the camera and the placer is the camera's child, so the picture and the anchor move together: the identity holds by construction, as it does in Viewfinder. The roll-direction and bridge smoke stages verify it |
| Beveled meshes change collider extents | Colliders stay exact boxes; only the mesh bevels. The physics stages of the probe verify it |
| Studio drifts from the world after a lighting change | V-SNAP-01 makes the studio read the world's values; check 6.5 pins it |
| Shader Graph output is stripped from a build like the first shaders were | Every new shader goes into Always Included Shaders in the same change that adds it; `verify-player.ps1` asserts each by name |
| Performance on the Mobile tier | Each item states its Mobile degradation; the perf capture runs on both RP assets |
| The look becomes busy | Tiers are reviewed on frames by a person before the next starts; Tier 6 is gated on that review |
| A font is added and the "no binary asset" story weakens | Section 3.2 names it as the one documented exception, with the licence file beside it |

---

## 8. Out of scope

- **Audio.** A professional game has it and this one has none: ambient wind,
  the placement "shk" of a print, the carve, the cage break, the battery
  chime, the teleporter hum and departure, the rewind tape whine, UI ticks.
  It deserves its own document with the same discipline (generated where
  possible, licensed where not). Not visual, not here.
- **Gameplay, levels, rules, strings.** `docs/PRD.md` is the contract and is
  unchanged by anything above.
- **Mobile and WebGL ports.** Degradation is specified per item so they stay
  possible; making them good is separate work.
- **Accessibility options** (colorblind palettes, motion reduction toggles
  for V-ANIM-01, larger text). Worth doing; a separate short document, after
  this one lands, because motion reduction and palette alternatives need the
  final look to exist first.

---

## Appendix A. Technique notes

**Triplanar in Shader Graph.** Sample the noise three times with world
position `xy`, `yz`, `xz`, weight by `abs(normal)` raised to 4 and
normalised, sum. Use `Gradient Noise` nodes at two scales; feed the result
through a `Remap` to the amplitude constraint and `Add` to the base color.
Keep the whole graph under 40 nodes; it runs on every surface in the game.

**Per-instance seed without per-instance materials.** `ErasableBlock`
sets `_Seed` through a `MaterialPropertyBlock` on its renderer, so all blocks
still share one material and SRP batching still works. Fragments copy the
parent's seed. The graph reads `_Seed` as a float property marked
"Override Property Declaration: Hybrid Per Instance" (or simply a normal
property, since the property block overrides it per renderer either way).

**Bevelled box mesh.** 26 quads (6 faces, 12 edge strips, 8 corner
triangles), smooth normals on the bevel strips, hard normals on the faces.
Generated once per size and cached; a level has a few dozen distinct sizes.

**Adding a renderer feature from code.** The Decal feature can be added to
`PC_Renderer.asset` in the editor once and committed (it is text YAML). Do
not add features at runtime.

**Always Included Shaders.** Every new `.shader` and Shader Graph the game
finds by name goes into `ProjectSettings/GraphicsSettings.asset`
`m_AlwaysIncludedShaders` as `{fileID: 4800000, guid: <meta guid>, type: 3}`
in the same commit. `verify-player.ps1` already asserts the three shaders the
game has; extend the list with each new one.

**Studio post-processing.** The studio camera needs
`UniversalAdditionalCameraData.renderPostProcessing = true` and its
`renderType` left at Base; SSAO comes from the renderer, bloom from the global
volume. To keep vignette off for the studio only, give the studio a
child Volume (priority 5, `isGlobal = false`, a trigger collider the studio
camera sits inside) overriding Vignette intensity to 0.

## Appendix B. Reading list

- URP documentation: Universal Render Pipeline Asset, Renderer Features
  (SSAO, Decal, Full Screen Pass), Volumes and post-processing overrides,
  Lens Flare (SRP).
- Shader Graph: Gradient Noise, Triplanar, Fresnel Effect, Master Stack
  emission and custom properties.
- "Rendering Manifold Garden" (William Chyr, GDC): what edges, AO and
  atmosphere do for pure geometry.
- "The Art of The Witness" (Luis Antonio): color discipline as a gameplay
  tool.
