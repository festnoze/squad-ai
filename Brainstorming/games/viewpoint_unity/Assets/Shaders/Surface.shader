// The one lit shader of VIEWPOINT. Every solid surface in the game is drawn by
// it: ground, blocks, cages, batteries, crates, stairs, island skirts, the
// polaroid frame, the teleporter ring and the painted markers on the floor.
// PRD_VISUAL 4.5 specifies it; Appendix C.9 records why it is hand written URP
// HLSL and not a Shader Graph (a .shadergraph is version specific JSON that
// fails silently when hand authored, and Assets/Shaders/GradientSky.shader
// already set the precedent for hand written URP HLSL in this project).
//
// ---------------------------------------------------------------------------
// THE TWO THINGS THIS FILE EXISTS TO RECONCILE
// ---------------------------------------------------------------------------
// The owner asked on 2026-09-07 for real material detail and as much realism as
// the scene will carry (PRD_VISUAL Appendix C.11 and C.12), so ten CC0 PBR sets
// now live under Assets/Resources/Textures/ and this shader samples five maps
// from each. But the game teaches EVERY rule in color and never in words
// (gameplay PRD 5.1): grey is permanent, pale is carvable, lavender is
// ephemeral, steel is sealed, lead takes no film. A player who cannot separate
// those at a glance cannot play, whatever the screenshot looks like.
//
// A texture cannot simply multiply the palette color. An ambientCG concrete
// averages about 0.5, so _BaseColor * texColor would render every platform at
// half its palette value and the whole game would go dark and muddy, taking the
// color language down with it. So every map here is turned into a MODULATION
// CENTRED ON 1.0 by dividing it by its own mean, and that modulation is applied
// to the palette color:
//
//     mean   = the texture's 1x1 mip, which IS its average
//     detail = texColor / mean                      (averages to 1.0)
//     albedo = _BaseColor * lerp(1.0, detail, _TextureStrength)
//
// Full grain, veins and wear at strength 0.9, and the MEAN albedo of any face
// is still exactly its palette color. The same trick is used on roughness: the
// map becomes a ZERO MEAN offset around the style's working smoothness, so a
// concrete's polished and worn patches both read while the family still has the
// smoothness PRD_VISUAL 4.5 asks of it. Realism was bought without spending the
// color language, which is the whole argument of Appendix C.12.
//
// ---------------------------------------------------------------------------
// WHY EVERYTHING IS TRIPLANAR AND WORLD SPACE
// ---------------------------------------------------------------------------
// The meshes are generated: a scaled box, a beveled box, a carved fragment, a
// ramp. None of them has a UV set worth sampling, and a carved fragment must
// stay seamless with the block it broke off even though it is a new mesh at a
// new position. So texture coordinates come from WORLD POSITION, projected on
// the three axis planes and blended by the normal. Nothing here reads a mesh UV
// or a mesh tangent, and nothing may start to.
//
// ---------------------------------------------------------------------------
// WHAT TIER 0 AND TIER 1 PUT IN THIS SHADER'S HANDS
// ---------------------------------------------------------------------------
// Four things landed before this file existed and are silently reverted by a
// shader that drops one line:
//   - SSAO in PC_Renderer.asset runs from DEPTH-NORMALS (Source: 1). A shader
//     with no DepthNormals pass gets NO ambient occlusion at all, silently, on
//     every surface. Hence the fourth pass, and hence it does the full
//     triplanar normal rather than the cheap geometric one: the occlusion in a
//     paving stone's grout is worth the three fetches.
//   - Forward+ (m_RenderingMode: 2) needs _CLUSTER_LIGHT_LOOP or the teleporter
//     pad light and the live battery pools light nothing.
//   - Fog is RenderSettings Exponential at density 0.018, and in URP 17 fog is
//     a keyword INCLUDE (Fog.hlsl), not a multi_compile_fog line. Without it
//     the sky fogs and no solid surface does, which reads as a bug.
//   - Bloom is thresholded at 1.05 in HDR so only emissives cross it. Nothing
//     here clamps _EmissionColor: a charged ring at energy 2.0 and a filled
//     cell at 1.2 MUST cross that threshold.
// The pragma blocks below were copied from URP's own Shaders/Lit.shader pass by
// pass, and only the "#pragma shader_feature_local..." lines naming features
// this shader does not have were removed. Every multi_compile and every
// include_with_pragmas is kept exactly as it stands there. Do not prune them by
// eye: three of the four failures above are invisible until someone looks at a
// frame and says "the ground looks wrong" a month later.
Shader "Viewpoint/Surface"
{
    Properties
    {
        // The first four are written BY NAME from Assets/Scripts/Render/
        // Materials.cs and read back by Assets/Tests/EditMode/MaterialsTests.cs
        // to a tolerance of 0.001. Renaming or retyping one of them is a test
        // failure, not a refactor.
        _BaseColor ("Base color", Color) = (1,1,1,1)

        // Gameplay PRD 14.2 pins Godot roughness 0.85, which is URP smoothness
        // 0.15, and MaterialsTests asserts exactly that on the MATERIAL. Every
        // per family smoothness PRD_VISUAL 4.5 asks for (0.22 ground, 0.55
        // steel, 0.35 lead, 0.9 glass) is therefore the SHADER's working value,
        // derived from this one inside the style branch. That is Appendix C.4:
        // the two numbers cannot both live on the material, and the port
        // fidelity one is the one that stays there.
        _Smoothness ("Smoothness", Range(0,1)) = 0.15
        _Metallic ("Metallic", Range(0,1)) = 0

        // HDR and never saturated anywhere below. See the bloom note above.
        [HDR] _EmissionColor ("Emission color", Color) = (0,0,0,1)

        // Which family this surface belongs to. Materials.cs writes the float,
        // this shader branches on the integer. The values are fixed and shared:
        //   0 Ground  1 Ephemeral  2 PaleSoft  3 Steel  4 Lead  5 Wood
        //   6 Stone   7 Rock       8 Paper     9 Glass 10 Marker
        _Style ("Style", Float) = 0

        // Per RENDERER, through a MaterialPropertyBlock, so a hundred blocks
        // still share the ONE material the factory cached (PRD_VISUAL Appendix
        // A). That does opt each such renderer out of SRP batching, and it is
        // affordable only because a scene here holds under a hundred renderers
        // (PRD_VISUAL 3.3); it would not be at ten times that.
        //
        // It cannot be hashed from world position inside the shader: a carved
        // fragment must INHERIT its parent's seed (V-MAT-03) and it sits at a
        // new position, so the value has to be handed in.
        _Seed ("Per instance seed", Float) = 0

        // Tier 4 animates these two. At 1 and 0 respectively they are complete
        // no ops: the reveal branch is not entered and the cut glow adds a
        // literal zero. They are declared now so Tier 4 needs no shader change,
        // and because _Reveal CLIPS, the same clip runs in all four passes (a
        // half revealed block that casts a whole shadow is worse than one that
        // does not dissolve at all).
        _Reveal ("Reveal", Range(0,1)) = 1
        _CutGlow ("Cut glow", Range(0,1)) = 0

        // The five CC0 maps, assigned per style by Materials.cs from
        // Assets/Resources/Textures/. Every default is a MEANINGFUL value, not a
        // placeholder: three of the ten sets ship no metalness map and none of
        // them ships a height map that must be absent, so a missing file must
        // land on "no metal", "no roughness offset", "flat height" rather than
        // on an undefined sample. That is why the shader never branches per set.
        _BaseMap ("Albedo", 2D) = "white" {}
        _NormalMap ("Normal", 2D) = "bump" {}
        _RoughMap ("Roughness", 2D) = "white" {}
        _MetalMap ("Metalness", 2D) = "black" {}
        _HeightMap ("Height", 2D) = "gray" {}

        // Beyond the orchestrator's list, and neutral by default so nothing
        // breaks if it is never assigned. Three sets ship an ambient occlusion
        // map (PavingStones092, Rock030, Rock023) and PRD_VISUAL asks for it on
        // stone and rock; white is "no occlusion", so a material that never sets
        // it renders exactly as it would without the property.
        _AOMap ("Ambient occlusion", 2D) = "white" {}

        // Texture repeats per world metre. 0.5 is one repeat every two metres,
        // the scale the ground was tuned at. Materials.cs writes it per style.
        _MapScale ("World texture scale", Float) = 0.5

        // How far the mean preserving detail is pushed. 0.9 is the house value;
        // paper takes 0.3 because a polaroid frame carrying concrete grade
        // texture stops looking like paper. Materials.cs writes it per style.
        _TextureStrength ("Texture detail strength", Range(0,2)) = 0.9

        _NormalStrength ("Normal strength", Range(0,3)) = 1.2

        // In UV units, i.e. a fraction of one texture repeat, which is URP's own
        // convention for _Parallax. At _MapScale 0.5 the default 0.02 is about
        // four centimetres of apparent depth: enough for a paving stone to have
        // a real edge, not enough for the silhouette to give the lie away.
        _ParallaxHeight ("Parallax height", Range(0,0.1)) = 0.02
    }

    // Shared by all four passes. It lives here rather than being copied per pass
    // because the triplanar setup, the style table and above all the reveal clip
    // must be BIT IDENTICAL across the forward, shadow, depth and depth-normals
    // passes. The three URP "#include_with_pragmas" files each pass names below
    // contain pragmas and nothing else, so nothing here depends on being
    // textually included before or after them.
    HLSLINCLUDE

    #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
    // Color.hlsl is what declares Luminance(), which the tiling break below uses
    // to compare a macro sample against the map's mean. Core.hlsl does NOT pull
    // it in: the forward pass only sees it because Lighting.hlsl includes it
    // further down, so the function resolved there and was undeclared in this
    // shared block and in the three other passes. That failed to compile with
    // "undeclared identifier 'Luminance'", and it is worth knowing that NOTHING
    // in the harness caught it: Builder.CompileCheck reports C# errors only, so
    // it printed "les scripts compilent" while this shader was broken, and Unity
    // logs a shader error and carries on building. The error was found by
    // grepping the editor log. Include guards make this free if it arrives twice.
    #include "Packages/com.unity.render-pipelines.core/ShaderLibrary/Color.hlsl"

    // Every property above appears here in the SAME ORDER with the matching HLSL
    // type, textures and samplers excepted: those are declared outside the
    // cbuffer while their _ST float4 stays inside it. A property declared in
    // Properties and missing here is not a warning, it is a shader that has
    // silently fallen out of SRP batching, so the two lists are kept in step by
    // eye every time one of them grows. GradientSky.shader carries the same note
    // for the same reason.
    CBUFFER_START(UnityPerMaterial)
        float4 _BaseColor;
        float _Smoothness;
        float _Metallic;
        float4 _EmissionColor;
        float _Style;
        float _Seed;
        float _Reveal;
        float _CutGlow;
        // The tiling and offset of every map. Nothing samples through them: this
        // shader derives its coordinates from world position, so a per material
        // tiling would only be a second, conflicting way of saying _MapScale.
        // They are declared because Unity serialises an _ST for every 2D
        // property, and a serialised property outside the cbuffer is exactly the
        // thing that breaks batching.
        float4 _BaseMap_ST;
        float4 _NormalMap_ST;
        float4 _RoughMap_ST;
        float4 _MetalMap_ST;
        float4 _HeightMap_ST;
        float4 _AOMap_ST;
        float _MapScale;
        float _TextureStrength;
        float _NormalStrength;
        float _ParallaxHeight;
    CBUFFER_END

    // One sampler for six textures. The import rules in Assets/Editor/
    // TextureImportRules.cs give every map in the set the same wrap, filter and
    // anisotropy, so a second sampler state would be a copy of the first, and
    // sampler slots are the scarce resource here, not texture slots.
    //
    // THAT REASONING IS SOUND AND THE CONCLUSION WAS STILL WRONG, so the shared
    // sampler is gone. Sharing sampler_BaseMap across all six maps compiled fine
    // in the forward pass and failed in the depth-normals one:
    //     Unrecognized sampler 'sampler_basemap' - does not match any texture
    // The cause is per-pass stripping. Each pass compiles only the code it
    // reaches, and the depth-normals fragment needs the NORMAL map and nothing
    // else, so _BaseMap is stripped out of that pass and the sampler named after
    // it is left pointing at a texture that no longer exists there. A sampler
    // whose name matches a texture that is live in EVERY pass using it cannot
    // have that problem, so each map now carries its own.
    //
    // An inline sampler state (sampler_linear_repeat and friends) would also
    // have fixed it and is wrong here for a different reason: inline states
    // cannot express anisotropy, and TextureImportRules.cs sets aniso 8 exactly
    // because almost every textured surface in this game is a large flat plane
    // seen at a grazing angle. A named sampler inherits the imported texture's
    // settings; an inline one would silently throw that away.
    TEXTURE2D(_BaseMap);        SAMPLER(sampler_BaseMap);
    TEXTURE2D(_NormalMap);      SAMPLER(sampler_NormalMap);
    TEXTURE2D(_RoughMap);       SAMPLER(sampler_RoughMap);
    TEXTURE2D(_MetalMap);       SAMPLER(sampler_MetalMap);
    TEXTURE2D(_HeightMap);      SAMPLER(sampler_HeightMap);
    TEXTURE2D(_AOMap);          SAMPLER(sampler_AOMap);

    // ---------------------------------------------------------------------
    // The style families. These integers are a contract with Materials.cs.
    // ---------------------------------------------------------------------
    #define STYLE_GROUND     0
    #define STYLE_EPHEMERAL  1
    #define STYLE_PALESOFT   2
    #define STYLE_STEEL      3
    #define STYLE_LEAD       4
    #define STYLE_WOOD       5
    #define STYLE_STONE      6
    #define STYLE_ROCK       7
    #define STYLE_PAPER      8
    #define STYLE_GLASS      9
    #define STYLE_MARKER    10

    // ---------------------------------------------------------------------
    // Tuning constants. Every one of them is a look decision, so they are named
    // and gathered rather than typed into the maths where nobody can find them.
    // ---------------------------------------------------------------------

    // The 1x1 mip IS the texture's average. 1024 is 2^10, so mip 10 is that
    // single texel; asking for 12 makes the sampler clamp to the smallest mip,
    // which costs nothing and survives a set imported at a different size.
    static const float MeanMipLevel = 12.0;

    // V-MAT-04. PRD_VISUAL 4.5 writes the pulse as emission * (0.26 + 0.08 *
    // sin(time * 1.96)), for a period of 3.2 s and a range of 0.18 to 0.34.
    // Taken literally that factor would DIVIDE the authored emission by about
    // four: Materials.cs already writes _EmissionColor as the palette color
    // times the Godot emission energy, and erasable matter ships at 0.25, so
    // 0.25 * 0.26 is 0.065 and the lavender would stop reading altogether.
    // The factor is therefore normalised by its own mean, 0.26, which leaves
    // the SHAPE, the PERIOD and the RANGE the document asks for (0.25 times
    // 0.69 to 1.31 is 0.173 to 0.327) while keeping the authored emission as
    // the mean. This is the only sane reading of the two numbers together.
    static const float PulseOmega = 1.96;              // 3.2 s period
    static const float PulseAmplitude = 0.08 / 0.26;   // about 0.308

    // V-MAT-04's rim: pow(1 - saturate(dot(N, V)), 3) * 0.4 added to emission,
    // in the surface's own color, so a lavender wall's edges glow faintly
    // against the sky and bloom picks them up.
    static const float RimExponent = 3.0;
    static const float RimStrength = 0.4;

    // V-MAT-05. The pale carvable floor is created by Materials.Solid with no
    // emission energy at all (it is a floor, not a lamp), so a pulse that only
    // scaled _EmissionColor would scale zero and the item would quietly not
    // exist. A small floor derived from the surface's own color gives it the
    // shimmer the item asks for without needing a second material. It is kept
    // deliberately faint: pale albedo is already the brightest thing in the
    // palette and PRD_VISUAL 6.3 wants nothing but emissives above 0.98.
    static const float PaleSoftGlow = 0.05;

    // V-MAT-05's "subtle diagonal hatch in the grain". Zero mean by
    // construction (a sine over a face averages out), so it costs the palette
    // nothing, and it is the one place a procedural term still beats a map:
    // no set in the library has a diagonal hatch, and the point of the hatch is
    // to separate pale from lavender when both sample the same Plaster001.
    static const float HatchFrequency = 9.0;
    static const float HatchAmplitude = 0.018;

    // V-MAT-02. Curvature is measured in radians per world METRE (see
    // EdgeWear below), so the gain is in metres per radian. A 2.5 cm bevel from
    // V-GEO-01 turns 90 degrees over 2.5 cm, i.e. about 63 rad/m, which
    // saturates; a flat face is 0 and stays 0. That is the "degrades to nearly
    // nothing on a flat face" the item asks for, and it holds whether or not
    // the beveled meshes have landed yet.
    static const float EdgeWearGain = 0.045;
    static const float EdgeWearLift = 0.06;        // PRD_VISUAL 4.5: brighten by 0.06
    static const float EdgeWearSmoothness = 0.20;  // PRD_VISUAL 4.5: raise smoothness by 0.2

    // Bounds on the albedo modulation. See the long note at the tint itself for
    // why an unbounded ratio was wrong; these are the numbers that make it safe.
    //
    // DetailCeil is 1.0 and that is the whole point: the map may DARKEN the
    // palette value and may never brighten it. It makes "no non-emissive surface
    // crosses the 1.05 bloom threshold" true BY CONSTRUCTION rather than by
    // arithmetic that has to be redone whenever a texture set changes, and
    // PRD_VISUAL 6.3's emissive isolation check depends on exactly that. The
    // brightest albedo in the palette is 'frame' at 0.98 and platform_soft at
    // 0.97, so there was never headroom above 1 to spend anyway.
    //
    // DetailFloor 0.55 leaves a shade range of nearly two to one across a
    // surface, which is plenty of grain: wear, dirt and shadowed pits are all
    // darkening, so nothing about a real material is lost by refusing to
    // brighten. What IS lost is a few percent of mean luminance, since a clamped
    // signal no longer averages exactly 1.0; that shows up as surfaces reading a
    // touch deeper than their palette value, which the palette RELATIONS
    // (spreads and orderings, not absolutes) survive untouched.
    static const float DetailFloor = 0.55;
    static const float DetailCeil = 1.0;

    // HEIGHT FOG (V-SKY-04 stage two). See the note where it is applied.
    //
    // HeightFogTop is the walking plane: platform tops in this game sit between
    // about y = 0 and y = 6, so measuring downward from 2 leaves the
    // architecture the player stands on essentially clear and starts thickening
    // as soon as a surface hangs below it. That is exactly the island skirts and
    // the drop.
    // HeightFogDepth is how far below that the air reaches full thickness: 12 m,
    // the figure the item itself gives.
    // HeightFogDistance keys it to distance as well, so a skirt at the player's
    // feet stays readable and the same skirt seen across the level does not.
    static const float HeightFogTop = 2.0;
    static const float HeightFogDepth = 12.0;
    static const float HeightFogDistance = 0.02;
    static const float HeightFogStrength = 0.85;

    // The tiling break. See MacroVariation() for what it does and what it costs.
    static const float MacroScale = 0.149;                 // one repeat per 6.7 detail repeats
    static const float2 MacroRotation = float2(0.799, 0.602); // cos and sin of 37 degrees
    // Raised from 0.30. The looking-down frame of level 1 showed the ground
    // tiling as a plain grid of repeating specks, and while the map scale was
    // the bigger culprit, this is the term whose actual job is to hide the
    // repeat: a broad, low-frequency brightness wander that has nothing in
    // common with the tile period, so the eye stops locking onto the grid.
    // Luminance only, so it still shifts no hue and the palette relations of
    // constraint 3.1 are untouched however high it goes.
    static const float MacroStrength = 0.42;
    static const float MacroSmoothness = 0.04;

    // Distance fades. PRD_VISUAL 1.1 lists edge shimmer as a defect this whole
    // document exists to remove, and both tiled detail and screen space
    // curvature alias at range. V-MAT-01's acceptance is literally "at 2 m a
    // platform shows visible grain; at 20 m it reads flat", so the numbers are
    // chosen against that sentence: full detail inside 4 m, about a third of it
    // left at 20 m, where mip filtering has taken most of the rest anyway.
    static const float DetailFadeNear = 4.0;
    static const float DetailFadeFar = 24.0;
    static const float DetailFadeAmount = 0.70;
    static const float NormalFadeNear = 3.0;
    static const float NormalFadeFar = 22.0;
    static const float NormalFadeAmount = 0.75;
    static const float WearFadeNear = 8.0;
    static const float WearFadeFar = 30.0;
    static const float WearFadeAmount = 0.70;

    // Parallax fades out entirely, because past a dozen metres it buys nothing
    // an eye can see and it is the most expensive thing in the fragment.
    static const float ParallaxFadeNear = 4.0;
    static const float ParallaxFadeFar = 14.0;
    static const int ParallaxMinSteps = 5;
    static const int ParallaxMaxSteps = 14;

    // How much of the roughness map's zero mean offset is applied. Below 1 the
    // family's working smoothness dominates; at 1 the map has full say.
    static const float RoughDetailStrength = 0.85;

    // V-GEO-02. A rock skirt darkens toward its lower end so an island fades
    // into the abyss instead of ending in a bright stump. Measured DOWN FROM THE
    // OBJECT'S OWN ORIGIN and not from world y = 0, because platforms float at
    // every height in this game and an absolute gradient would black out the low
    // ones and do nothing to the high ones.
    static const float RockFadeDepth = 3.0;
    static const float RockFadeFloor = 0.45;

    // Ambient occlusion from the map is multiplied into OCCLUSION and never into
    // albedo: baked shadow painted into a color is the thing that makes a
    // textured surface look like a photograph of a surface.
    static const float AoStrength = 0.85;

    // V-MAT-03. The amplitude bounds of PRD_VISUAL 3.1 were lifted on
    // 2026-09-07, but the READING they protect was not, and this is the one term
    // that would break it first: jitter two greys far enough apart and the
    // player stops seeing one category. So it stays at the item's own numbers,
    // value plus or minus 0.03 and hue plus or minus 4 degrees, which is
    // "distinguishable side by side and indistinguishable by category".
    static const float SeedValueJitter = 0.03;
    static const float SeedHueJitter = 0.0698;   // 4 degrees in radians

    // Tier 4. The dissolve edge and the carve flash are the same lavender white,
    // authored above the 1.05 bloom threshold so a carve reads as light and not
    // as a color change.
    static const float3 CutColor = float3(0.86, 0.82, 0.98);
    static const float CutGlowEnergy = 1.7;
    static const float RevealEdgeEnergy = 1.9;
    static const float RevealEdgeWidth = 0.16;
    static const float RevealNoiseScale = 6.0;

    // ---------------------------------------------------------------------
    // Value noise. Lifted from GradientSky.shader, which explains the choice at
    // length: no sin() in the hash, because sin based hashes differ between GPU
    // vendors and a dissolve that changes shape per driver is not a dissolve.
    // ---------------------------------------------------------------------
    float SurfaceHash(float3 cell)
    {
        float3 p = frac(cell * 0.3183099 + 0.1);
        p *= 17.0;
        return frac(p.x * p.y * p.z * (p.x + p.y + p.z));
    }

    float SurfaceNoise(float3 p)
    {
        float3 cell = floor(p);
        float3 f = frac(p);
        float3 u = f * f * (3.0 - 2.0 * f);

        float c000 = SurfaceHash(cell + float3(0.0, 0.0, 0.0));
        float c100 = SurfaceHash(cell + float3(1.0, 0.0, 0.0));
        float c010 = SurfaceHash(cell + float3(0.0, 1.0, 0.0));
        float c110 = SurfaceHash(cell + float3(1.0, 1.0, 0.0));
        float c001 = SurfaceHash(cell + float3(0.0, 0.0, 1.0));
        float c101 = SurfaceHash(cell + float3(1.0, 0.0, 1.0));
        float c011 = SurfaceHash(cell + float3(0.0, 1.0, 1.0));
        float c111 = SurfaceHash(cell + float3(1.0, 1.0, 1.0));

        float x00 = lerp(c000, c100, u.x);
        float x10 = lerp(c010, c110, u.x);
        float x01 = lerp(c001, c101, u.x);
        float x11 = lerp(c011, c111, u.x);
        return lerp(lerp(x00, x10, u.y), lerp(x01, x11, u.y), u.z);
    }

    // ---------------------------------------------------------------------
    // _Reveal (Tier 4). Declared and wired now so Tier 4 needs no shader change.
    //
    // The field must be a pure function of world position and _Seed, because the
    // SAME value has to come out in the forward, shadow, depth and depth-normals
    // passes. Anything view dependent in here and a dissolving block casts a
    // shadow of a different shape than itself.
    // ---------------------------------------------------------------------
    float RevealField(float3 positionWS)
    {
        return SurfaceNoise(positionWS * RevealNoiseScale + _Seed * 37.0);
    }

    // At _Reveal 1 the branch is not entered at all, so a fully resolved block
    // pays nothing and, more importantly, cannot be clipped by a noise value
    // that happens to land on exactly zero at a lattice point.
    void ApplyReveal(float3 positionWS)
    {
        UNITY_BRANCH
        if (_Reveal < 1.0)
        {
            clip(RevealField(positionWS) - (1.0 - _Reveal));
        }
    }

    // ---------------------------------------------------------------------
    // Per style look. One struct, one if chain. _Style is uniform per material,
    // so the branch is coherent across every warp and a real dynamic branch is
    // cheaper here than computing eleven looks and lerping between them.
    // Every smoothness is an OFFSET on _Smoothness rather than an absolute, so
    // the families still track the material if that number ever moves
    // (PRD_VISUAL Appendix C.4 asks for "derived from _Smoothness").
    // ---------------------------------------------------------------------
    struct StyleParams
    {
        float smoothnessOffset;   // added to _Smoothness
        float metallicFloor;      // lowest metallic this family accepts
        float useMetalMap;        // 1 when the metalness map has a say
        float aoStrength;         // 1 when this family's set ships an AO map
        float parallaxScale;      // 0 switches parallax off entirely
        float normalScale;        // 0 keeps the geometric normal
        float pulse;              // 0 none, 1 full (V-MAT-04), 0.5 half (V-MAT-05)
        float rim;                // fresnel rim strength multiplier
        float paleGlow;           // 1 for the synthesised pale floor shimmer
        float hatch;              // 1 for V-MAT-05's diagonal hatch
        float textured;           // 0 samples no map at all
        float seedJitter;         // per instance hue and value jitter, 0..1
        float rockFade;           // 1 fades the surface downward (V-GEO-02)
        float verticalStretch;    // brushed streak: world y tiling divisor
        float inert;              // 1 ignores emission and every time varying term
    };

    StyleParams GetStyleParams(int style)
    {
        StyleParams p;
        p.smoothnessOffset = 0.07;
        p.metallicFloor = 0.0;
        p.useMetalMap = 0.0;
        p.aoStrength = 0.0;
        p.parallaxScale = 1.0;
        p.normalScale = 1.0;
        p.pulse = 0.0;
        p.rim = 0.0;
        p.paleGlow = 0.0;
        p.hatch = 0.0;
        p.textured = 1.0;
        p.seedJitter = 1.0;
        p.rockFade = 0.0;
        p.verticalStretch = 1.0;
        p.inert = 0.0;

        if (style == STYLE_EPHEMERAL)
        {
            // V-MAT-04. Lavender is the only thing in this game that shimmers,
            // and the shimmer IS the rule it teaches. A touch more sheen than
            // the grey ground so it also reads as a different substance under a
            // grazing sun.
            p.smoothnessOffset = 0.13;
            p.parallaxScale = 0.7;
            p.normalScale = 0.9;
            p.pulse = 1.0;
            p.rim = 1.0;
        }
        else if (style == STYLE_PALESOFT)
        {
            // V-MAT-05. Lavender's pale cousin: the same pulse at half
            // amplitude, plus the diagonal hatch that keeps it apart from
            // lavender in a grayscale frame even though both sample Plaster001.
            p.smoothnessOffset = 0.09;
            p.parallaxScale = 0.7;
            p.normalScale = 0.9;
            p.pulse = 0.5;
            p.paleGlow = 1.0;
            p.hatch = 1.0;
        }
        else if (style == STYLE_STEEL)
        {
            // V-MAT-06. Smoothness 0.55 and metallic 0.8 or better, which is
            // what finally makes V-LIGHT-02's sky reflection probe visible: it
            // was set in Tier 1 and until now nothing in the game was glossy
            // enough to show it. The vertical stretch is the item's "brushed
            // streak along the bars": Metal032 is already a brushed set, and
            // stretching its world y tiling draws the streak along the bar
            // instead of across it.
            p.smoothnessOffset = 0.40;
            p.metallicFloor = 0.80;
            p.useMetalMap = 1.0;
            p.parallaxScale = 0.5;
            p.seedJitter = 0.5;
            p.verticalStretch = 2.2;
        }
        else if (style == STYLE_LEAD)
        {
            // V-MAT-06 and gameplay PRD 5.1. Dull, greasy, and INERT: no
            // emission, no pulse, no rim, no seed, nothing that reads _Time.
            // A leaden battery sitting perfectly still next to a live amber one
            // that bobs and glows is how the game says "no film prints this
            // one", and it is the one thing in this file that is a rule rather
            // than a look.
            p.smoothnessOffset = 0.20;
            p.metallicFloor = 0.60;
            p.parallaxScale = 0.6;
            p.seedJitter = 0.0;
            p.inert = 1.0;
        }
        else if (style == STYLE_WOOD)
        {
            p.smoothnessOffset = 0.15;
        }
        else if (style == STYLE_STONE)
        {
            // V-MAT-07. Paving stones are the one set with real relief in the
            // height map, so parallax runs at full strength here and the AO map
            // does the grout.
            p.smoothnessOffset = 0.11;
            p.aoStrength = 1.0;
            p.parallaxScale = 1.4;
            p.normalScale = 1.15;
        }
        else if (style == STYLE_ROCK)
        {
            p.smoothnessOffset = 0.03;
            p.aoStrength = 1.0;
            p.parallaxScale = 1.2;
            p.normalScale = 1.1;
            p.rockFade = 1.0;
        }
        else if (style == STYLE_PAPER)
        {
            // V-PROP-02. Paper has no depth to parallax and almost no gloss.
            // Its low texture strength comes from the material (Materials.cs
            // writes 0.3 for this family), not from here, so there is exactly
            // one place that number lives.
            p.smoothnessOffset = 0.20;
            p.parallaxScale = 0.0;
            p.normalScale = 0.8;
            p.seedJitter = 0.4;
        }
        else if (style == STYLE_GLASS)
        {
            // V-PROP-05. The teleporter ring: smooth, unmapped, and carried
            // entirely by its emission.
            p.smoothnessOffset = 0.75;
            p.parallaxScale = 0.0;
            p.normalScale = 0.0;
            p.textured = 0.0;
            p.seedJitter = 0.0;
        }
        else if (style == STYLE_MARKER)
        {
            // Gameplay PRD 5.1. Markers are painted signs on the ground that say
            // "stand here", and they are the level's only wordless instruction.
            // A marker that gathers grain, wear, a parallax offset and a seed
            // jitter stops reading as paint and starts reading as one more slab.
            // So: flat _BaseColor, straight out, no sample of any kind.
            p.smoothnessOffset = 0.0;
            p.parallaxScale = 0.0;
            p.normalScale = 0.0;
            p.textured = 0.0;
            p.seedJitter = 0.0;
        }

        return p;
    }

    // ---------------------------------------------------------------------
    // Triplanar setup.
    //
    // The gradients are carried alongside the coordinates and every sample below
    // is an explicit-gradient sample. That is not caution for its own sake: the
    // dominant axis, and with it the parallax offset, flips between neighbouring
    // pixels along a 45 degree crease, and an implicit derivative there jumps to
    // the smallest mip and paints a grey line down every corner of every box in
    // the game. The gradients are taken from the UNOFFSET coordinates, before
    // parallax, for the same reason.
    // ---------------------------------------------------------------------
    struct Triplanar
    {
        float2 uvX; float2 uvY; float2 uvZ;
        float2 ddxX; float2 ddyX;
        float2 ddxY; float2 ddyY;
        float2 ddxZ; float2 ddyZ;
        float3 blend;
        float3 axisSign;
        int dominant;         // 0 = x facing, 1 = y facing, 2 = z facing
        float dominantWeight;
        float2 dominantUV;
        float2 dominantDdx;
        float2 dominantDdy;
    };

    Triplanar BuildTriplanar(float3 positionWS, float3 normalWS, float scale, float verticalStretch)
    {
        Triplanar t;

        float3 wp = positionWS * scale;
        // A brushed metal is rolled along one axis, so its texture must stretch
        // along that axis rather than tile square. World y is the cage bars'
        // axis; see the deviation note in the report for why it is not the
        // object's own long axis (this shader has no object space to ask).
        wp.y /= max(verticalStretch, 0.001);

        // Flip one coordinate per plane by the sign of the normal, so the two
        // opposite faces of a box do not read as mirror images of each other.
        // Written out as two float3 rather than as sign(): sign() returns zero
        // for a zero component and would collapse that plane's coordinate to a
        // single texel, and written out rather than as a scalar ternary because
        // a vector condition with scalar arms is the form DXC rejects.
        t.axisSign = normalWS < 0.0 ? float3(-1.0, -1.0, -1.0) : float3(1.0, 1.0, 1.0);
        t.uvX = float2(wp.z * t.axisSign.x, wp.y);
        t.uvY = float2(wp.x * t.axisSign.y, wp.z);
        t.uvZ = float2(wp.x * -t.axisSign.z, wp.y);

        t.ddxX = ddx(t.uvX); t.ddyX = ddy(t.uvX);
        t.ddxY = ddx(t.uvY); t.ddyY = ddy(t.uvY);
        t.ddxZ = ddx(t.uvZ); t.ddyZ = ddy(t.uvZ);

        // abs(normal) to the fourth, normalised: PRD_VISUAL Appendix A pins the
        // exponent. Written as two squarings rather than pow(), which is a log
        // and an exp on most hardware for a value that may be zero.
        float3 an = abs(normalWS);
        float3 b = an * an;
        b = b * b;
        t.blend = b / max(b.x + b.y + b.z, 1e-4);

        t.dominant = (t.blend.x >= t.blend.y && t.blend.x >= t.blend.z)
            ? 0
            : ((t.blend.y >= t.blend.z) ? 1 : 2);
        t.dominantWeight = max(max(t.blend.x, t.blend.y), t.blend.z);

        if (t.dominant == 0)
        {
            t.dominantUV = t.uvX; t.dominantDdx = t.ddxX; t.dominantDdy = t.ddyX;
        }
        else if (t.dominant == 1)
        {
            t.dominantUV = t.uvY; t.dominantDdx = t.ddxY; t.dominantDdy = t.ddyY;
        }
        else
        {
            t.dominantUV = t.uvZ; t.dominantDdx = t.ddxZ; t.dominantDdy = t.ddyZ;
        }

        return t;
    }

    // The parallax offset is applied to the DOMINANT plane only, and to that
    // plane's copy of the coordinates, so every later sample of every map picks
    // it up without any of them having to know parallax exists.
    void OffsetDominant(inout Triplanar t, float2 offset)
    {
        if (t.dominant == 0) { t.uvX += offset; }
        else if (t.dominant == 1) { t.uvY += offset; }
        else { t.uvZ += offset; }
        t.dominantUV += offset;
    }

    float4 TriplanarSample(TEXTURE2D_PARAM(map, samp), Triplanar t)
    {
        return SAMPLE_TEXTURE2D_GRAD(map, samp, t.uvX, t.ddxX, t.ddyX) * t.blend.x
             + SAMPLE_TEXTURE2D_GRAD(map, samp, t.uvY, t.ddxY, t.ddyY) * t.blend.y
             + SAMPLE_TEXTURE2D_GRAD(map, samp, t.uvZ, t.ddxZ, t.ddyZ) * t.blend.z;
    }

    float4 DominantSample(TEXTURE2D_PARAM(map, samp), Triplanar t)
    {
        return SAMPLE_TEXTURE2D_GRAD(map, samp, t.dominantUV, t.dominantDdx, t.dominantDdy);
    }

    // The whiteout triplanar normal blend. Lerping three tangent space normals
    // and calling it a day is the obvious thing and it is visibly wrong on every
    // diagonal, which in a game made of boxes means every single edge: the three
    // normals disagree about which way is up and the average points somewhere
    // none of them did. Whiteout re-expresses each sample as a perturbation of
    // the geometric normal before blending, so a face that is 50/50 between two
    // planes gets the sum of two perturbations instead of the average of two
    // absolute directions.
    float3 TriplanarNormalWS(Triplanar t, float3 geomNormalWS, float strength)
    {
        float3 nX = UnpackNormalScale(SAMPLE_TEXTURE2D_GRAD(_NormalMap, sampler_NormalMap, t.uvX, t.ddxX, t.ddyX), strength);
        float3 nY = UnpackNormalScale(SAMPLE_TEXTURE2D_GRAD(_NormalMap, sampler_NormalMap, t.uvY, t.ddxY, t.ddyY), strength);
        float3 nZ = UnpackNormalScale(SAMPLE_TEXTURE2D_GRAD(_NormalMap, sampler_NormalMap, t.uvZ, t.ddxZ, t.ddyZ), strength);

        // Undo the coordinate flips BuildTriplanar put on the u axis, or the
        // bumps on the two opposite faces of a box light from opposite sides.
        nX.x *= t.axisSign.x;
        nY.x *= t.axisSign.y;
        nZ.x *= -t.axisSign.z;

        // The whiteout itself: the sample's u and v are ADDED to the geometric
        // normal's own u and v, and its n component is scaled by the geometric
        // normal's SIGNED component along that axis. Signed, not abs(): the
        // absolute value is the form that circulates, and on a face pointing at
        // -x it produces a normal pointing at +x, which lights the whole back of
        // every box as if the sun were on this side of it.
        nX = float3(nX.xy + geomNormalWS.zy, nX.z * geomNormalWS.x);
        nY = float3(nY.xy + geomNormalWS.xz, nY.z * geomNormalWS.y);
        nZ = float3(nZ.xy + geomNormalWS.xy, nZ.z * geomNormalWS.z);

        // Each plane's (u, v, n) back into world axes, then the triplanar blend.
        // X projects on world (z, y), Y on world (x, z), Z on world (x, y),
        // which is what the three different swizzles say.
        return normalize(nX.zyx * t.blend.x + nY.xzy * t.blend.y + nZ.xyz * t.blend.z);
    }

    // ---------------------------------------------------------------------
    // Parallax occlusion mapping on the dominant plane.
    //
    // It is what makes stone and paving read as having real depth rather than a
    // painted picture of depth, and it is the most expensive thing in this
    // shader, so it is also the first thing to go: the step count follows the
    // view angle (a face seen head on needs almost none) and the distance fade
    // takes it to zero steps well before the detail itself stops mattering.
    // ---------------------------------------------------------------------
    float2 ParallaxOffset(Triplanar t, float3 viewTS, float amplitude, float fade)
    {
        int steps = (int)(lerp((float)ParallaxMinSteps, (float)ParallaxMaxSteps,
            saturate(1.0 - abs(viewTS.z))) * fade + 0.5);
        if (steps < 1 || amplitude <= 0.0)
        {
            return float2(0.0, 0.0);
        }

        // Total travel across the uv plane for one full unit of depth. The 0.2
        // floor on the normal component is what keeps a face seen edge on from
        // asking for an infinite offset and smearing across the screen.
        float2 travel = (viewTS.xy / max(abs(viewTS.z), 0.2)) * amplitude;

        float layerStep = 1.0 / (float)steps;
        float2 uvStep = travel * layerStep;

        float2 uv = t.dominantUV;
        float layer = 0.0;
        // ambientCG height maps are white high and black low, so depth is the
        // complement.
        float depth = 1.0 - SAMPLE_TEXTURE2D_GRAD(_HeightMap, sampler_HeightMap, uv, t.dominantDdx, t.dominantDdy).r;

        UNITY_LOOP
        for (int i = 0; i < steps; i++)
        {
            if (layer >= depth)
            {
                break;
            }
            uv -= uvStep;
            layer += layerStep;
            depth = 1.0 - SAMPLE_TEXTURE2D_GRAD(_HeightMap, sampler_HeightMap, uv, t.dominantDdx, t.dominantDdy).r;
        }

        // One linear refinement between the last two layers. Without it the
        // silhouette of a paving stone steps in exactly as many bands as there
        // are steps, and the adaptive step count makes those bands MOVE as the
        // player walks, which is worse than no parallax at all.
        float2 prevUV = uv + uvStep;
        float after = depth - layer;
        float before = (1.0 - SAMPLE_TEXTURE2D_GRAD(_HeightMap, sampler_HeightMap, prevUV, t.dominantDdx, t.dominantDdy).r)
            - (layer - layerStep);
        float weight = after / max(after - before, 1e-4);

        return lerp(uv, prevUV, saturate(weight)) - t.dominantUV;
    }

    // The view direction expressed in the dominant plane's own frame, as
    // (along u, along v, along the plane normal). Built from the WORLD AXIS the
    // plane belongs to and not from the shaded normal, because the parallax ray
    // travels through the geometry, not through the bumps.
    float3 ViewInDominantPlane(Triplanar t, float3 viewDirWS)
    {
        if (t.dominant == 0)
        {
            return float3(viewDirWS.z * t.axisSign.x, viewDirWS.y, viewDirWS.x * t.axisSign.x);
        }
        if (t.dominant == 1)
        {
            return float3(viewDirWS.x * t.axisSign.y, viewDirWS.z, viewDirWS.y * t.axisSign.y);
        }
        return float3(viewDirWS.x * -t.axisSign.z, viewDirWS.y, viewDirWS.z * t.axisSign.z);
    }

    // ---------------------------------------------------------------------
    // The tiling break.
    //
    // A 1K map at one repeat per two metres crosses a 12 m platform six times,
    // and this game is made of large flat ground planes seen from above, which
    // is precisely the case where a repeating texture announces itself. The
    // technique here is macro variation: ONE extra sample of the albedo map,
    // rotated 37 degrees and scaled to one repeat per 6.7 detail repeats, used
    // for its LUMINANCE only and turned into a modulation centred on 1.0 by the
    // same mean division as everything else.
    //
    // What it costs: one texture fetch and about eight ALU per fragment. It
    // reuses the 1x1 mip already fetched for the albedo mean, so it adds no
    // second mean fetch.
    //
    // What it does and does not do: it does not remove the repeat, it makes the
    // repeat unrecognisable. Recognising a tiled texture is recognising a
    // remembered blotch in a new place; superimposing a much larger, non
    // commensurate variation (about 13.4 m against the 2 m tile, and rotated so
    // the two structures never line up) means no two visible repeats have the
    // same brightness, and the eye stops finding the grid. Luminance only, so it
    // shifts no hue, which is what PRD_VISUAL 3.1 cares about.
    //
    // The alternatives were weighed and rejected: a full second sample of all
    // five maps doubles eighteen fetches to thirty six, and stochastic or hex
    // grid sampling costs three weighted samples per map instead of one, i.e.
    // three times the whole texture budget, for a scene that has to leave room
    // for SSAO and bloom inside a 60 fps target.
    // ---------------------------------------------------------------------
    float MacroVariation(Triplanar t, float meanLuminance)
    {
        float2 rotated = float2(
            dot(t.dominantUV, MacroRotation),
            dot(t.dominantUV, float2(-MacroRotation.y, MacroRotation.x))) * MacroScale;
        float2 rdx = float2(
            dot(t.dominantDdx, MacroRotation),
            dot(t.dominantDdx, float2(-MacroRotation.y, MacroRotation.x))) * MacroScale;
        float2 rdy = float2(
            dot(t.dominantDdy, MacroRotation),
            dot(t.dominantDdy, float2(-MacroRotation.y, MacroRotation.x))) * MacroScale;

        float3 macro = SAMPLE_TEXTURE2D_GRAD(_BaseMap, sampler_BaseMap, rotated, rdx, rdy).rgb;
        return Luminance(macro) / max(meanLuminance, 1e-3);
    }

    // Rodrigues rotation about the grey axis: a hue shift that needs no RGB to
    // HSV round trip and cannot change luminance. Four degrees of it is what
    // V-MAT-03 allows.
    float3 HueRotate(float3 color, float angle)
    {
        const float3 axis = float3(0.5773503, 0.5773503, 0.5773503);
        float c = cos(angle);
        float s = sin(angle);
        return color * c + cross(axis, color) * s + axis * dot(axis, color) * (1.0 - c);
    }

    // V-MAT-02. Curvature in radians per world metre: how fast the GEOMETRIC
    // normal turns, divided by how far the surface travels, both measured across
    // the same pixel quad. Dividing by the world space derivative is what makes
    // it view independent, and that matters more than it sounds: the raw screen
    // space derivative of a normal GROWS with distance, because a distant bevel
    // turns the same 90 degrees across fewer pixels, so an unnormalised version
    // would paint bright edges on everything far away and nothing near.
    //
    // The geometric normal, never the mapped one: a normal map has curvature
    // everywhere and would wear the whole surface evenly, which is no wear.
    float EdgeWear(float3 geomNormalWS, float3 positionWS)
    {
        float3 dNdx = ddx(geomNormalWS);
        float3 dNdy = ddy(geomNormalWS);
        float3 dPdx = ddx(positionWS);
        float3 dPdy = ddy(positionWS);

        float curvature = (length(dNdx) + length(dNdy)) / max(length(dPdx) + length(dPdy), 1e-4);
        float wear = saturate(curvature * EdgeWearGain);

        // PRD_VISUAL 4.5 asks for the curvature term blended with
        // saturate(1 - abs(dot(normal, up))), so a vertical bevel wears a little
        // harder than the chamfer around a floor. Kept as a mild weighting and
        // not as a second factor: on its own that term brightens every wall.
        float verticality = saturate(1.0 - abs(geomNormalWS.y));
        return wear * lerp(0.6, 1.0, verticality);
    }

    // ---------------------------------------------------------------------
    // The surface itself. Everything above meets here.
    // ---------------------------------------------------------------------
    struct SurfaceInputs
    {
        float3 positionWS;
        float3 geomNormalWS;
        float3 viewDirWS;      // fragment toward the eye, unit length
        float viewDistance;
        float3 objectOriginWS;
    };

    void EvaluateSurface(SurfaceInputs si, out half3 albedo, out half3 normalWS,
        out half smoothness, out half metallic, out half occlusion, out half3 emission)
    {
        int style = (int)(_Style + 0.5);
        StyleParams sp = GetStyleParams(style);

        albedo = half3(_BaseColor.rgb);
        normalWS = half3(si.geomNormalWS);
        smoothness = half(saturate(_Smoothness + sp.smoothnessOffset));
        metallic = half(saturate(max(_Metallic, sp.metallicFloor)));
        occlusion = half(1.0);
        emission = half3(0.0, 0.0, 0.0);

        // The base emission. NEVER saturated: V-POST-01 thresholds bloom at 1.05
        // in HDR, and a charged teleporter ring authored at energy 2.0 and a
        // filled cell at 1.2 have to cross it. Clamping here is how a glow
        // quietly stops glowing.
        #ifdef _EMISSION
            emission = half3(_EmissionColor.rgb);
        #endif

        // -----------------------------------------------------------------
        // The two families that sample nothing, taken out before any fetch.
        // The compiler still emits the sampling code below, but no marker and no
        // teleporter ring ever executes a texture instruction.
        // -----------------------------------------------------------------
        UNITY_BRANCH
        if (sp.textured < 0.5)
        {
            if (style != STYLE_MARKER)
            {
                // Glass: the cut flash still reaches it, a marker's does not.
                emission += half3(CutColor * (_CutGlow * CutGlowEnergy));
            }
            return;
        }

        // -----------------------------------------------------------------
        // Distance fades. PRD_VISUAL 1.1 lists edge shimmer as a defect this
        // document exists to remove, and V-MAT-01's acceptance is "at 2 m a
        // platform shows visible grain; at 20 m it reads flat".
        // -----------------------------------------------------------------
        float detailFade = 1.0 - DetailFadeAmount * smoothstep(DetailFadeNear, DetailFadeFar, si.viewDistance);
        float normalFade = 1.0 - NormalFadeAmount * smoothstep(NormalFadeNear, NormalFadeFar, si.viewDistance);
        float wearFade = 1.0 - WearFadeAmount * smoothstep(WearFadeNear, WearFadeFar, si.viewDistance);
        float parallaxFade = 1.0 - smoothstep(ParallaxFadeNear, ParallaxFadeFar, si.viewDistance);

        Triplanar t = BuildTriplanar(si.positionWS, si.geomNormalWS, _MapScale, sp.verticalStretch);

        // -----------------------------------------------------------------
        // Parallax, before any other sample, so every map picks the offset up.
        // -----------------------------------------------------------------
        UNITY_BRANCH
        if (sp.parallaxScale > 0.0 && parallaxFade > 0.0)
        {
            float3 viewTS = ViewInDominantPlane(t, si.viewDirWS);
            OffsetDominant(t, ParallaxOffset(t, viewTS, _ParallaxHeight * sp.parallaxScale, parallaxFade));
        }

        // -----------------------------------------------------------------
        // Albedo: the mean preserving tint. See the header of this file.
        // -----------------------------------------------------------------
        float3 baseMean = SAMPLE_TEXTURE2D_LOD(_BaseMap, sampler_BaseMap, float2(0.5, 0.5), MeanMipLevel).rgb;
        float3 baseColor = TriplanarSample(TEXTURE2D_ARGS(_BaseMap, sampler_BaseMap), t).rgb;

        // LUMINANCE ONLY, AND BOUNDED. The first version of this divided the
        // sample by the mean PER CHANNEL and unbounded, which is wrong twice:
        //
        //   - unbounded: a high contrast map with a dark mean produces a ratio
        //     of three or four. Multiplied into the palette colour that lands
        //     the albedo well above 1, so a NON-EMISSIVE surface crosses the
        //     1.05 bloom threshold and "only live things glow" stops being
        //     true (PRD_VISUAL 6.3's emissive isolation check). It also let a
        //     single stone stair span the whole grey-to-pale readability band
        //     at once, which is the one thing constraint 3.1 still protects
        //     after the owner lifted its amplitudes. Visible on the level 6
        //     frame as a pillar with blown-out white veins.
        //   - per channel: the ratio carries the MAP's hue, so a warm concrete
        //     dragged the palette's neutral grey warm. The palette is the
        //     game's whole teaching language and the map has no business
        //     voting on it.
        //
        // So the map modulates LUMINANCE and nothing else, and the modulation
        // is clamped. The ceiling is 1.0 on purpose: the texture may only ever
        // DARKEN the palette value, never brighten it, which is what makes the
        // bloom behaviour Tier 0 verified hold by construction rather than by
        // arithmetic that has to be redone every time a map changes. Nothing is
        // lost visually, because grain, wear and dirt are darkening phenomena.
        float baseMeanLum = max(Luminance(baseMean), 1e-3);
        float detail = clamp(Luminance(baseColor) / baseMeanLum, DetailFloor, DetailCeil);
        float3 tinted = _BaseColor.rgb * lerp(1.0, detail, _TextureStrength * detailFade);

        // The tiling break, luminance only so it shifts no hue.
        float macro = MacroVariation(t, max(Luminance(baseMean), 1e-3));
        tinted *= lerp(1.0, macro, MacroStrength);

        // -----------------------------------------------------------------
        // Roughness, by the same trick: the map is a ZERO MEAN offset around the
        // family's working smoothness, so the family keeps the number
        // PRD_VISUAL 4.5 gives it and the map still has full say about which
        // patches are polished and which are worn.
        // -----------------------------------------------------------------
        float roughMean = SAMPLE_TEXTURE2D_LOD(_RoughMap, sampler_RoughMap, float2(0.5, 0.5), MeanMipLevel).r;
        float rough = TriplanarSample(TEXTURE2D_ARGS(_RoughMap, sampler_RoughMap), t).r;
        float working = saturate(_Smoothness + sp.smoothnessOffset)
            - (rough - roughMean) * RoughDetailStrength * detailFade;

        // A darker macro patch is a slightly rougher one. Two multiply-adds for
        // a surface that stops looking uniformly polished across a whole floor.
        working += (1.0 - macro) * MacroSmoothness;

        // -----------------------------------------------------------------
        // Metalness. The map has a say only where it means something. Steel is
        // floored at V-MAT-06's 0.8 so a checkout with no Metal032_Metal.jpg
        // still reflects the sky, and lead ignores the map entirely: Metal030's
        // metalness is uniform, there is nothing in it to drive, and V-MAT-06
        // pins lead at 0.6 precisely so it stays duller than the cage.
        // -----------------------------------------------------------------
        UNITY_BRANCH
        if (sp.useMetalMap > 0.5)
        {
            float metalSample = DominantSample(TEXTURE2D_ARGS(_MetalMap, sampler_MetalMap), t).r;
            metallic = half(saturate(max(metallic, metalSample)));
        }

        // -----------------------------------------------------------------
        // Ambient occlusion from the map, into OCCLUSION and never into albedo.
        // Sampled on the dominant plane only: AO is low frequency, three
        // projections would be three times the cost for a difference nobody can
        // see, and fading it by the dominant weight keeps the bevel seamless
        // where no single plane dominates.
        // -----------------------------------------------------------------
        UNITY_BRANCH
        if (sp.aoStrength > 0.0)
        {
            float ao = DominantSample(TEXTURE2D_ARGS(_AOMap, sampler_AOMap), t).r;
            occlusion = half(lerp(1.0, ao, AoStrength * t.dominantWeight * detailFade));
        }

        // -----------------------------------------------------------------
        // The triplanar normal.
        // -----------------------------------------------------------------
        UNITY_BRANCH
        if (sp.normalScale > 0.0)
        {
            normalWS = half3(TriplanarNormalWS(t, si.geomNormalWS, _NormalStrength * sp.normalScale * normalFade));
        }

        // -----------------------------------------------------------------
        // V-MAT-03, the per instance jitter. Applied to the TINT and not to the
        // detail, so two blocks differ as two painted pieces differ and not as
        // two different textures.
        // -----------------------------------------------------------------
        UNITY_BRANCH
        if (sp.seedJitter > 0.0)
        {
            // Materials.SeedFor already hands over a well mixed value in
            // [0, 1); the second decorrelated draw is what keeps a block that
            // happens to be dark from also always being the same hue.
            float j = _Seed * 2.0 - 1.0;
            float k = frac(_Seed * 7.31 + 0.37) * 2.0 - 1.0;
            tinted = HueRotate(tinted, k * SeedHueJitter * sp.seedJitter);
            tinted *= 1.0 + j * SeedValueJitter * sp.seedJitter;
        }

        // -----------------------------------------------------------------
        // V-MAT-05's diagonal hatch, zero mean, pale floor only.
        // -----------------------------------------------------------------
        UNITY_BRANCH
        if (sp.hatch > 0.0)
        {
            float diagonal = (si.positionWS.x + si.positionWS.z) * 0.7071 + si.positionWS.y * 0.35;
            tinted *= 1.0 + sin(diagonal * HatchFrequency) * HatchAmplitude * detailFade;
        }

        // -----------------------------------------------------------------
        // V-GEO-02. A rock skirt darkens toward its lower end so an island fades
        // into the abyss. Measured down from the OBJECT's origin, so it works at
        // whatever height that island floats.
        // -----------------------------------------------------------------
        UNITY_BRANCH
        if (sp.rockFade > 0.0)
        {
            float below = saturate((si.objectOriginWS.y - si.positionWS.y) / RockFadeDepth);
            tinted *= lerp(1.0, RockFadeFloor, below);
            working = lerp(working, working * 0.7, below);
        }

        // -----------------------------------------------------------------
        // V-MAT-02, edge wear, last of the albedo terms so it sits on top of the
        // texture rather than under it: a worn corner is paint rubbed off, and
        // rubbed off paint shows above the grain, not through it.
        // -----------------------------------------------------------------
        float wear = EdgeWear(si.geomNormalWS, si.positionWS) * wearFade;
        tinted += wear * EdgeWearLift;
        working += wear * EdgeWearSmoothness;

        albedo = half3(max(tinted, 0.0));
        smoothness = half(saturate(working));

        // -----------------------------------------------------------------
        // Emission. Lead never gets here with anything: it is the one surface in
        // the game that must be provably inert.
        // -----------------------------------------------------------------
        UNITY_BRANCH
        if (sp.inert > 0.5)
        {
            emission = half3(0.0, 0.0, 0.0);
            return;
        }

        UNITY_BRANCH
        if (sp.pulse > 0.0)
        {
            // V-MAT-04 and V-MAT-05. _Time.y is seconds since load, used raw:
            // no frac() on it, because wrapping the phase makes every lavender
            // surface in the level jump at the wrap.
            float pulse = 1.0 + PulseAmplitude * sp.pulse * sin(_Time.y * PulseOmega);
            emission = half3((emission + half3(_BaseColor.rgb * (PaleSoftGlow * sp.paleGlow))) * pulse);
        }

        UNITY_BRANCH
        if (sp.rim > 0.0)
        {
            // The fresnel rim of V-MAT-04, in the surface's own lavender, so a
            // lavender wall's edges glow faintly against the sky and bloom picks
            // them up. Uses the SHADED normal on purpose: the rim should follow
            // the surface the player sees, bumps included.
            float fresnel = pow(1.0 - saturate(dot(normalize((float3)normalWS), si.viewDirWS)), RimExponent);
            emission += half3(_BaseColor.rgb * (fresnel * RimStrength * sp.rim));
        }

        // Tier 4's carve flash. A literal zero at _CutGlow 0.
        emission += half3(CutColor * (_CutGlow * CutGlowEnergy));
    }

    // The normal alone, for the DepthNormals prepass. It matters that this is
    // the mapped normal and not the geometric one: SSAO in PC_Renderer.asset
    // reads the depth-normals buffer, so this is what puts occlusion in the
    // grout between paving stones and in the grain of a plank.
    //
    // It deliberately does NOT run parallax. The offset moves the sampled point
    // by a couple of centimetres at most, which changes the normal by far less
    // than the SSAO blur radius, and skipping it saves up to fourteen fetches
    // per fragment across the whole screen in a pass that does no lighting.
    half3 EvaluateSurfaceNormal(SurfaceInputs si)
    {
        int style = (int)(_Style + 0.5);
        StyleParams sp = GetStyleParams(style);

        UNITY_BRANCH
        if (sp.textured < 0.5 || sp.normalScale <= 0.0)
        {
            return half3(si.geomNormalWS);
        }

        float normalFade = 1.0 - NormalFadeAmount * smoothstep(NormalFadeNear, NormalFadeFar, si.viewDistance);
        Triplanar t = BuildTriplanar(si.positionWS, si.geomNormalWS, _MapScale, sp.verticalStretch);
        return half3(TriplanarNormalWS(t, si.geomNormalWS, _NormalStrength * sp.normalScale * normalFade));
    }

    // The object's world origin, used by the rock fade. unity_ObjectToWorld
    // lives in UnityPerDraw, so reading it costs nothing and breaks no batching.
    float3 GetObjectOriginWS()
    {
        float4x4 objectToWorld = GetObjectToWorldMatrix();
        return float3(objectToWorld._m03, objectToWorld._m13, objectToWorld._m23);
    }

    SurfaceInputs BuildSurfaceInputs(float3 positionWS, float3 normalWS)
    {
        SurfaceInputs si;
        si.positionWS = positionWS;
        si.geomNormalWS = normalize(normalWS);
        float3 toEye = _WorldSpaceCameraPos - positionWS;
        si.viewDistance = length(toEye);
        si.viewDirWS = toEye / max(si.viewDistance, 1e-4);
        si.objectOriginWS = GetObjectOriginWS();
        return si;
    }

    ENDHLSL

    SubShader
    {
        Tags
        {
            "RenderType" = "Opaque"
            "Queue" = "Geometry"
            "RenderPipeline" = "UniversalPipeline"
            "UniversalMaterialType" = "Lit"
            "IgnoreProjector" = "True"
        }
        LOD 300

        // ------------------------------------------------------------------
        //  Forward pass. All lighting, GI, emission and fog in one go.
        Pass
        {
            Name "ForwardLit"
            Tags
            {
                "LightMode" = "UniversalForward"
            }

            // -------------------------------------
            // Render State Commands
            Blend One Zero
            ZWrite On
            Cull Back

            HLSLPROGRAM
            // 3.5 rather than URP Lit's 2.0, and the same profile on all four
            // passes so one number governs the whole shader. Three things need
            // it: the dynamic loop in ParallaxOffset, the explicit gradient
            // sampling every triplanar fetch uses, and SAMPLE_TEXTURE2D_LOD for
            // the 1x1 mean mip.
            #pragma target 3.5

            // -------------------------------------
            // Shader Stages
            #pragma vertex SurfaceForwardVertex
            #pragma fragment SurfaceForwardFragment

            // -------------------------------------
            // Material Keywords
            // Materials.cs calls EnableKeyword("_EMISSION") / DisableKeyword and
            // MaterialsTests asserts IsKeywordEnabled("_EMISSION"), so this one
            // line is a test contract as much as a variant.
            #pragma shader_feature_local_fragment _EMISSION

            // -------------------------------------
            // Universal Pipeline keywords
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ EVALUATE_SH_MIXED EVALUATE_SH_VERTEX
            #pragma multi_compile_fragment _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BLENDING
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BOX_PROJECTION
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_ATLAS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ _SCREEN_SPACE_OCCLUSION
            #pragma multi_compile_fragment _ _SCREEN_SPACE_IRRADIANCE
            #pragma multi_compile_fragment _ _DBUFFER_MRT1 _DBUFFER_MRT2 _DBUFFER_MRT3
            #pragma multi_compile_fragment _ _LIGHT_COOKIES
            #pragma multi_compile _ _LIGHT_LAYERS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #include_with_pragmas "Packages/com.unity.render-pipelines.core/ShaderLibrary/FoveatedRenderingKeywords.hlsl"
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"

            // -------------------------------------
            // Unity defined keywords
            #pragma multi_compile _ LIGHTMAP_SHADOW_MIXING
            #pragma multi_compile _ SHADOWS_SHADOWMASK
            #pragma multi_compile _ DIRLIGHTMAP_COMBINED
            #pragma multi_compile _ LIGHTMAP_ON
            #pragma multi_compile_fragment _ LIGHTMAP_BICUBIC_SAMPLING
            #pragma multi_compile_fragment _ REFLECTION_PROBE_ROTATION
            #pragma multi_compile _ DYNAMICLIGHTMAP_ON
            #pragma multi_compile _ USE_LEGACY_LIGHTMAPS
            #pragma multi_compile _ LOD_FADE_CROSSFADE
            #pragma multi_compile_fragment _ DEBUG_DISPLAY
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/ProbeVolumeVariants.hlsl"

            //--------------------------------------
            // GPU Instancing
            #pragma multi_compile_instancing
            #pragma instancing_options renderinglayer
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DOTS.hlsl"

            // -------------------------------------
            // Includes
            //
            // Lighting.hlsl and NOT URP's Shaders/LitInput.hlsl or
            // Shaders/LitForwardPass.hlsl. Those two declare their OWN
            // UnityPerMaterial cbuffer, which would clash with the one above,
            // and their fragment calls InitializeStandardLitSurfaceData(uv, ...)
            // which is handed a UV and nothing else, while every sample in this
            // shader needs world position and world normal. What is worth
            // reusing is UniversalFragmentPBR, and that comes from here: main
            // light, additional lights under Forward+, shadows, SH and ambient,
            // reflection probes and SSAO, none of which is maths this file
            // should be getting wrong on its own.
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #if defined(LOD_FADE_CROSSFADE)
                #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/LODCrossFade.hlsl"
            #endif

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float2 staticLightmapUV : TEXCOORD1;
                float2 dynamicLightmapUV : TEXCOORD2;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            // No uv and no tangent anywhere in here, and none may be added: the
            // generated meshes have neither, and everything this shader samples
            // is a function of world position and world normal.
            struct Varyings
            {
                float3 positionWS : TEXCOORD0;
                float3 normalWS : TEXCOORD1;

            #ifdef _ADDITIONAL_LIGHTS_VERTEX
                half4 fogFactorAndVertexLight : TEXCOORD2;
            #else
                half fogFactor : TEXCOORD2;
            #endif

            #if defined(REQUIRES_VERTEX_SHADOW_COORD_INTERPOLATOR)
                float4 shadowCoord : TEXCOORD3;
            #endif

                DECLARE_LIGHTMAP_OR_SH(staticLightmapUV, vertexSH, 4);
            #ifdef DYNAMICLIGHTMAP_ON
                float2 dynamicLightmapUV : TEXCOORD5;
            #endif
            #ifdef USE_APV_PROBE_OCCLUSION
                float4 probeOcclusion : TEXCOORD6;
            #endif

                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            void InitializeInputData(Varyings input, half3 shadedNormalWS, out InputData inputData)
            {
                inputData = (InputData)0;

                inputData.positionWS = input.positionWS;

            #if defined(DEBUG_DISPLAY)
                inputData.positionCS = input.positionCS;
            #endif

                inputData.normalWS = NormalizeNormalPerPixel(shadedNormalWS);
                inputData.viewDirectionWS = GetWorldSpaceNormalizeViewDir(input.positionWS);

            #if defined(REQUIRES_VERTEX_SHADOW_COORD_INTERPOLATOR)
                inputData.shadowCoord = input.shadowCoord;
            #elif defined(MAIN_LIGHT_CALCULATE_SHADOWS)
                inputData.shadowCoord = TransformWorldToShadowCoord(inputData.positionWS);
            #else
                inputData.shadowCoord = float4(0, 0, 0, 0);
            #endif

            #ifdef _ADDITIONAL_LIGHTS_VERTEX
                inputData.fogCoord = InitializeInputDataFog(float4(input.positionWS, 1.0), input.fogFactorAndVertexLight.x);
                inputData.vertexLighting = input.fogFactorAndVertexLight.yzw;
            #else
                inputData.fogCoord = InitializeInputDataFog(float4(input.positionWS, 1.0), input.fogFactor);
            #endif

                inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(input.positionCS);

            #if defined(DEBUG_DISPLAY)
                #if defined(DYNAMICLIGHTMAP_ON)
                    inputData.dynamicLightmapUV = input.dynamicLightmapUV;
                #endif
                #if defined(LIGHTMAP_ON)
                    inputData.staticLightmapUV = input.staticLightmapUV;
                #else
                    inputData.vertexSH = input.vertexSH;
                #endif
                #if defined(USE_APV_PROBE_OCCLUSION)
                    inputData.probeOcclusion = input.probeOcclusion;
                #endif
            #endif
            }

            void InitializeBakedGIData(Varyings input, inout InputData inputData)
            {
            #if defined(_SCREEN_SPACE_IRRADIANCE)
                inputData.bakedGI = SAMPLE_GI(_ScreenSpaceIrradiance, input.positionCS.xy);
            #elif defined(DYNAMICLIGHTMAP_ON)
                inputData.bakedGI = SAMPLE_GI(input.staticLightmapUV, input.dynamicLightmapUV, input.vertexSH, inputData.normalWS);
                inputData.shadowMask = SAMPLE_SHADOWMASK(input.staticLightmapUV);
            #elif !defined(LIGHTMAP_ON) && (defined(PROBE_VOLUMES_L1) || defined(PROBE_VOLUMES_L2))
                inputData.bakedGI = SAMPLE_GI(input.vertexSH,
                    GetAbsolutePositionWS(inputData.positionWS),
                    inputData.normalWS,
                    inputData.viewDirectionWS,
                    input.positionCS.xy,
                    input.probeOcclusion,
                    inputData.shadowMask);
            #else
                inputData.bakedGI = SAMPLE_GI(input.staticLightmapUV, input.vertexSH, inputData.normalWS);
                inputData.shadowMask = SAMPLE_SHADOWMASK(input.staticLightmapUV);
            #endif
            }

            Varyings SurfaceForwardVertex(Attributes input)
            {
                Varyings output = (Varyings)0;

                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                VertexPositionInputs vertexInput = GetVertexPositionInputs(input.positionOS.xyz);
                // TransformObjectToWorldNormal and not a tangent frame: the
                // blocks are non uniformly scaled boxes, and this is the call
                // that carries the inverse transpose.
                float3 normalWS = TransformObjectToWorldNormal(input.normalOS);

                half3 vertexLight = VertexLighting(vertexInput.positionWS, normalWS);

                half fogFactor = 0;
            #if !defined(_FOG_FRAGMENT)
                fogFactor = ComputeFogFactor(vertexInput.positionCS.z);
            #endif

                output.positionWS = vertexInput.positionWS;
                output.normalWS = normalWS;

                OUTPUT_LIGHTMAP_UV(input.staticLightmapUV, unity_LightmapST, output.staticLightmapUV);
            #ifdef DYNAMICLIGHTMAP_ON
                output.dynamicLightmapUV = input.dynamicLightmapUV.xy * unity_DynamicLightmapST.xy + unity_DynamicLightmapST.zw;
            #endif
                OUTPUT_SH4(vertexInput.positionWS, normalWS.xyz, GetWorldSpaceNormalizeViewDir(vertexInput.positionWS), output.vertexSH, output.probeOcclusion);

            #ifdef _ADDITIONAL_LIGHTS_VERTEX
                output.fogFactorAndVertexLight = half4(fogFactor, vertexLight);
            #else
                output.fogFactor = fogFactor;
            #endif

            #if defined(REQUIRES_VERTEX_SHADOW_COORD_INTERPOLATOR)
                output.shadowCoord = GetShadowCoord(vertexInput);
            #endif

                output.positionCS = vertexInput.positionCS;
                return output;
            }

            void SurfaceForwardFragment(
                Varyings input
                , out half4 outColor : SV_Target0
            #ifdef _WRITE_RENDERING_LAYERS
                , out uint outRenderingLayers : SV_Target1
            #endif
            )
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                // The same clip as the other three passes, and it has to come
                // first: clipping after the lighting would still be correct on
                // screen and would still cost the lighting.
                ApplyReveal(input.positionWS);

            #ifdef LOD_FADE_CROSSFADE
                LODFadeCrossFade(input.positionCS);
            #endif

                SurfaceInputs si = BuildSurfaceInputs(input.positionWS, input.normalWS);

                half3 albedo;
                half3 shadedNormalWS;
                half smoothness;
                half metallic;
                half occlusion;
                half3 emission;
                EvaluateSurface(si, albedo, shadedNormalWS, smoothness, metallic, occlusion, emission);

                // The dissolve edge of Tier 4: a lavender white band on the
                // threshold, so a block being carved reads as light leaving it
                // rather than as a hole appearing. Recomputed rather than
                // carried out of ApplyReveal, because at _Reveal 1 nothing here
                // runs at all and that is the case that has to be free.
                UNITY_BRANCH
                if (_Reveal < 1.0)
                {
                    float band = 1.0 - smoothstep(0.0, RevealEdgeWidth,
                        RevealField(input.positionWS) - (1.0 - _Reveal));
                    emission += half3(CutColor * (band * RevealEdgeEnergy));
                }

                SurfaceData surfaceData;
                surfaceData.albedo = albedo;
                surfaceData.specular = half3(0.0, 0.0, 0.0);
                surfaceData.metallic = metallic;
                surfaceData.smoothness = smoothness;
                // The world normal is handed to UniversalFragmentPBR through
                // inputData, which is the path a world space normal takes; the
                // tangent space slot stays flat because nothing here has, or
                // wants, a tangent frame.
                surfaceData.normalTS = half3(0.0, 0.0, 1.0);
                surfaceData.emission = emission;
                surfaceData.occlusion = occlusion;
                surfaceData.alpha = 1.0;
                surfaceData.clearCoatMask = 0.0;
                surfaceData.clearCoatSmoothness = 0.0;

                InputData inputData;
                InitializeInputData(input, shadedNormalWS, inputData);
                // The mipmap streaming debug view has no UV to key on in a
                // triplanar shader, and URP ships the no-UV form for exactly
                // this case.
                SETUP_DEBUG_TEXTURE_DATA_NO_UV(inputData);

            #if defined(_DBUFFER)
                ApplyDecalToSurfaceData(input.positionCS, surfaceData, inputData);
            #endif

                InitializeBakedGIData(input, inputData);

                half4 color = UniversalFragmentPBR(inputData, surfaceData);
                // Fog is RenderSettings Exponential at density 0.018 (Tier 1). A
                // forward pass that forgets this line exempts every solid surface
                // in the game from fog while the sky keeps fogging, and the
                // result reads as a rendering bug rather than as a missing line.
                color.rgb = MixFog(color.rgb, inputData.fogCoord);

                // HEIGHT FOG, the second stage of PRD_VISUAL 4.3 V-SKY-04, and
                // the reason it exists is arithmetic recorded in Appendix C.7:
                // the item asks the decor islands 30 to 40 m out to lose at
                // least 25 percent of their contrast while a platform at 15 m
                // loses under 8, and DISTANCE-ONLY fog cannot do both. One
                // density satisfies either clause, never both.
                //
                // The item itself names the way out: thicken the air by DEPTH
                // rather than only by distance, "so the abyss below the islands
                // is foggier than the air at platform height". Platform tops sit
                // around y = 0 to 6 and the void runs away below, so a term
                // keyed on how far a surface falls under the walking plane costs
                // the near architecture almost nothing while it swallows the
                // island undersides and the drop.
                //
                // Done here rather than as a Full Screen Pass renderer feature:
                // the pass would also need a material asset and a renderer
                // feature entry in PC_Renderer.asset, three files of hand
                // written YAML whose failure mode is silent, and Appendix A
                // forbids adding features at runtime. A term in the surface
                // shader reaches exactly the geometry that needs it. The SKY's
                // own abyss darkening (V-SKY-03) already handles the background
                // behind it, and the two meet because both fade toward the same
                // horizon colour.
                float heightBelow = saturate((HeightFogTop - inputData.positionWS.y) / HeightFogDepth);
                float heightReach = 1.0 - exp(-inputData.fogCoord * HeightFogDistance);
                float heightMix = saturate(heightBelow * heightReach * HeightFogStrength);
                color.rgb = lerp(color.rgb, unity_FogColor.rgb, heightMix);

                color.a = 1.0;

                outColor = color;

            #ifdef _WRITE_RENDERING_LAYERS
                outRenderingLayers = EncodeMeshRenderingLayer();
            #endif
            }
            ENDHLSL
        }

        // ------------------------------------------------------------------
        //  Shadow caster. Present for the reveal clip as much as for the shadow:
        //  a half dissolved block that casts a whole shadow gives the carve away.
        Pass
        {
            Name "ShadowCaster"
            Tags
            {
                "LightMode" = "ShadowCaster"
            }

            // -------------------------------------
            // Render State Commands
            ZWrite On
            ZTest LEqual
            ColorMask 0
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5

            // -------------------------------------
            // Shader Stages
            #pragma vertex SurfaceShadowVertex
            #pragma fragment SurfaceShadowFragment

            //--------------------------------------
            // GPU Instancing
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DOTS.hlsl"

            // -------------------------------------
            // Unity defined keywords
            #pragma multi_compile _ LOD_FADE_CROSSFADE

            // Directional and punctual shadows apply the normal bias by
            // different formulas, which is what this switches between.
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW

            // -------------------------------------
            // Includes
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"
            #if defined(LOD_FADE_CROSSFADE)
                #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/LODCrossFade.hlsl"
            #endif

            // Set by ShadowUtils.SetupShadowCasterConstantBuffer on the C# side.
            // Global, so outside UnityPerMaterial.
            float3 _LightDirection;
            float3 _LightPosition;

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float3 positionWS : TEXCOORD0;
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            Varyings SurfaceShadowVertex(Attributes input)
            {
                Varyings output = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);

                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                float3 normalWS = TransformObjectToWorldNormal(input.normalOS);

            #if _CASTING_PUNCTUAL_LIGHT_SHADOW
                float3 lightDirectionWS = normalize(_LightPosition - positionWS);
            #else
                float3 lightDirectionWS = _LightDirection;
            #endif

                // The biased position is what goes to the clip space, but the
                // UNBIASED one is what the reveal clip reads: biasing it would
                // make the dissolve pattern in the shadow drift away from the
                // one on the surface, by an amount that changes with the sun.
                float4 positionCS = TransformWorldToHClip(ApplyShadowBias(positionWS, normalWS, lightDirectionWS));
                output.positionCS = ApplyShadowClamping(positionCS);
                output.positionWS = positionWS;
                return output;
            }

            half4 SurfaceShadowFragment(Varyings input) : SV_TARGET
            {
                UNITY_SETUP_INSTANCE_ID(input);

                ApplyReveal(input.positionWS);

            #if defined(LOD_FADE_CROSSFADE)
                LODFadeCrossFade(input.positionCS);
            #endif

                return 0;
            }
            ENDHLSL
        }

        // ------------------------------------------------------------------
        //  Depth only.
        Pass
        {
            Name "DepthOnly"
            Tags
            {
                "LightMode" = "DepthOnly"
            }

            // -------------------------------------
            // Render State Commands
            ZWrite On
            ColorMask R
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5

            // -------------------------------------
            // Shader Stages
            #pragma vertex SurfaceDepthOnlyVertex
            #pragma fragment SurfaceDepthOnlyFragment

            // -------------------------------------
            // Unity defined keywords
            #pragma multi_compile _ LOD_FADE_CROSSFADE

            //--------------------------------------
            // GPU Instancing
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DOTS.hlsl"

            // -------------------------------------
            // Includes
            #if defined(LOD_FADE_CROSSFADE)
                #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/LODCrossFade.hlsl"
            #endif

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float3 positionWS : TEXCOORD0;
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings SurfaceDepthOnlyVertex(Attributes input)
            {
                Varyings output = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                output.positionWS = TransformObjectToWorld(input.positionOS.xyz);
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                return output;
            }

            half SurfaceDepthOnlyFragment(Varyings input) : SV_TARGET
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                // The same clip again. Depth written for a fragment the forward
                // pass discards puts a hole in every effect that reads depth.
                ApplyReveal(input.positionWS);

            #if defined(LOD_FADE_CROSSFADE)
                LODFadeCrossFade(input.positionCS);
            #endif

                return input.positionCS.z;
            }
            ENDHLSL
        }

        // ------------------------------------------------------------------
        //  Depth normals. THE pass that decides whether this shader gets ambient
        //  occlusion at all: SSAO in Assets/Settings/PC_Renderer.asset runs with
        //  Source: 1, which is DEPTH-NORMALS. Without this pass every surface in
        //  the game silently loses its AO, with no error anywhere.
        Pass
        {
            Name "DepthNormals"
            Tags
            {
                "LightMode" = "DepthNormals"
            }

            // -------------------------------------
            // Render State Commands
            ZWrite On
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5

            // -------------------------------------
            // Shader Stages
            #pragma vertex SurfaceDepthNormalsVertex
            #pragma fragment SurfaceDepthNormalsFragment

            // -------------------------------------
            // Unity defined keywords
            #pragma multi_compile _ LOD_FADE_CROSSFADE

            // -------------------------------------
            // Universal Pipeline keywords
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"

            //--------------------------------------
            // GPU Instancing
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DOTS.hlsl"

            // -------------------------------------
            // Includes
            #if defined(LOD_FADE_CROSSFADE)
                #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/LODCrossFade.hlsl"
            #endif

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float3 positionWS : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings SurfaceDepthNormalsVertex(Attributes input)
            {
                Varyings output = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                output.positionWS = TransformObjectToWorld(input.positionOS.xyz);
                output.normalWS = TransformObjectToWorldNormal(input.normalOS);
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                return output;
            }

            void SurfaceDepthNormalsFragment(
                Varyings input
                , out half4 outNormalWS : SV_Target0
            #ifdef _WRITE_RENDERING_LAYERS
                , out uint outRenderingLayers : SV_Target1
            #endif
            )
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                ApplyReveal(input.positionWS);

            #if defined(LOD_FADE_CROSSFADE)
                LODFadeCrossFade(input.positionCS);
            #endif

                SurfaceInputs si = BuildSurfaceInputs(input.positionWS, input.normalWS);
                outNormalWS = half4(NormalizeNormalPerPixel(EvaluateSurfaceNormal(si)), 0.0);

            #ifdef _WRITE_RENDERING_LAYERS
                outRenderingLayers = EncodeMeshRenderingLayer();
            #endif
            }
            ENDHLSL
        }
    }

    // No fallback. A fallback here would let a stripped variant draw as
    // something else entirely (URP Lit, or worse the built in diffuse), which is
    // the failure mode the README already paid for once with the shaders that
    // were dropped from the player: a surface that renders WRONG is far harder
    // to see than one that renders magenta.
    Fallback Off
}
