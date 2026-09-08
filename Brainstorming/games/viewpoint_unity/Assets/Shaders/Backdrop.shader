// The painted backdrop of VIEWPOINT, and nothing else in the game: the flat
// panel a photo definition can carry (gameplay PRD 5.3), built by
// Assets/Scripts/Photo/PhotoContent.BuildBackdrop and handed the material that
// Assets/Scripts/Render/Materials.Backdrop caches. PRD_VISUAL 4.5 V-MAT-08
// specifies it, and its acceptance criterion is the whole design brief: "a
// placed backdrop is distinguishable from the real sky at its EDGES and
// indistinguishable at its CENTRE".
//
// Hand written URP HLSL rather than a Shader Graph, for the reason PRD_VISUAL
// appendix C.9 records for Viewpoint/Surface: a .shadergraph is version
// specific JSON that cannot be hand authored reliably and fails silently when
// it is malformed, while Assets/Shaders/GradientSky.shader set the precedent
// for hand written URP HLSL here.
//
// ---------------------------------------------------------------------------
// WHY UNLIT, AND WHY THAT IS NOT NEGOTIABLE
// ---------------------------------------------------------------------------
// Materials.Backdrop has always said it: a painted sky must not react to the
// sun, or the illusion of depth behind the photo breaks. The panel is a
// PICTURE of somewhere far away hanging in the world; the moment the world's
// directional light shades it, the eye reads a slab of painted board standing
// at four metres, which is exactly what the panel exists not to be. So there is
// no normal in the lighting sense here, no diffuse term, no specular, no GI and
// no light loop: the colour comes out of the ramp and the three small terms
// below, and nothing else touches it.
//
// ---------------------------------------------------------------------------
// WHAT THIS ADDS OVER "Universal Render Pipeline/Unlit", WHICH IT REPLACES
// ---------------------------------------------------------------------------
// The gradient itself is UNCHANGED and must stay so: the 4 x 64 ramp that
// Materials.GradientTexture generates (row 0 = the BOTTOM of the panel, a
// Unity/Godot row order trap that MaterialsTests pins deliberately) arrives as
// _BaseMap, and _BaseColor stays white so the ramp is never tinted twice. Under
// URP Unlit that ramp WAS the whole panel, and a perfect vertical gradient is
// the one thing in nature that never happens: it reads as a quad.
//
// Three terms turn it into a painting, all from V-MAT-08:
//   1. a faint paper GRAIN, about 0.02, from a hand written hash (no texture,
//      and no sin() in the hash: see GrainHash);
//   2. an edge VIGNETTE, about 0.06, so the paint sits in the panel instead of
//      filling it edge to edge;
//   3. a 2 cm BORDER band at the panel's own horizon colour lightened by 0.05,
//      the hairline of bare panel where the paint stopped short of the edge.
// One and two are what keep the CENTRE indistinguishable from the real sky
// (both are imperceptible there); three is what makes the EDGE unmistakable.
//
// ---------------------------------------------------------------------------
// THE PANEL SIZE IS DERIVED FROM THE TRANSFORM, NOT PASSED IN
// ---------------------------------------------------------------------------
// "2 cm" has to mean 2 cm and not 2 percent, so the border band needs the
// panel's size in METRES. It is derived in the vertex shader (see PanelSizeWS)
// and no float2 property is set from C#, deliberately:
//   - ONE material serves every backdrop that shares a palette pair, because
//     that is what Materials caches on, while the panel's size is a function of
//     the photo's DEPTH (PhotoMath.BackdropSize). A material float2 would
//     therefore be right for one panel in a level and wrong for every other,
//     and wrong SILENTLY: a 2 cm band computed against the wrong width is just
//     a slightly different band;
//   - a MaterialPropertyBlock would be per renderer and correct, but it would
//     need Assets/Scripts/Photo/PhotoContent.cs to write it and it would opt
//     each panel out of SRP batching, all to hand the vertex shader a number it
//     can read off its own object-to-world matrix for free.
// The derivation is exact for a quad CENTRED on its origin with UVs running 0
// to 1, which is what both quads in this project are: PhotoContent's own unit
// BackdropQuad scaled by (width, height, 1), and ProceduralMeshes.Quad(size),
// which bakes the size into the mesh and draws at unit scale. It costs nothing
// that the two conventions disagree about where the size lives, which is the
// second reason to derive rather than declare.
//
// ---------------------------------------------------------------------------
// _Reveal (V-VFX-01), AND WHY IT HAD TO EXIST IN THIS FILE TOO
// ---------------------------------------------------------------------------
// Tier 4's placement dissolve is a per renderer _Reveal float:
// Assets/Shaders/Surface.shader declares it, and every solid piece of a placed
// content resolves from a lavender-white edge glow to its final material over
// 0.4 s. This panel was the one face of a placement that did NOT, because the
// property did not exist here, and a backdrop is most of the screen area of a
// placement: the effect read as "everything melts into place except the sky,
// which was already there". So the same semantics are implemented here, and
// they are deliberately the SAME semantics rather than a second dialect:
//   - the field is a pure function of WORLD POSITION and _Seed. Nothing view
//     dependent may enter it, because the identical value has to come out of
//     all three passes: a panel whose paint clips on one pattern and whose
//     depth clips on another is a panel whose silhouette does not match what
//     it looks like;
//   - at _Reveal == 1 the branch is not entered at all, so a resolved panel
//     pays nothing AND cannot be clipped by a noise value that happens to land
//     on exactly zero at a lattice point;
//   - the clip runs in ALL THREE passes, which is the whole trap of this item.
//     A panel that clips in the forward pass and not in the depth ones still
//     OCCLUDES with its full rectangle: it dissolves on screen while going on
//     hiding whatever stands behind it, the drifting dust of
//     Assets/Scripts/Render/Atmosphere.cs keeps reading it as solid, and SSAO
//     (Source: 1, DEPTH-NORMALS) keeps occluding against a panel that is no
//     longer there. That is why both depth passes now carry positionWS in
//     their Varyings, which is the only thing either of them gained.
// The lattice of the dissolve is NOT retuned for the panel's size, and that is
// a decision rather than an oversight: see RevealNoiseScale.
//
// The panel stays UNLIT through all of it: no light reaches the paint that did
// not reach it before. The one thing the dissolve adds to the picture is the
// edge band's EMISSION, which is light LEAVING the paint, and it is gone the
// instant _Reveal reaches 1.
//
// ---------------------------------------------------------------------------
// THIS SHADER MUST BE IN ALWAYS INCLUDED SHADERS OR THE PANELS GO BLANK
// ---------------------------------------------------------------------------
// Nothing in this game references a shader from an ASSET: there is one scene,
// one object, and every material is created in code at start up. Unity strips
// from a player every shader no asset references, so "Viewpoint/Backdrop" has
// to sit in ProjectSettings/GraphicsSettings.asset m_AlwaysIncludedShaders
// beside the other four. This project has already lost a whole build to exactly
// that (see the README): Shader.Find returned null in the player, every
// material came out with no shader, and the symptom read as "the levels are
// empty". Materials.BackdropShader falls back to URP Unlit if it happens again,
// which costs the three terms above and keeps the gradient on screen, and
// MaterialsTests pins the shader NAME so the fallback cannot pass unnoticed in
// the harness.
//
// ---------------------------------------------------------------------------
// THE PASSES, AND WHY EACH ONE IS HERE OR ABSENT
// ---------------------------------------------------------------------------
// The set is URP Unlit's, minus what this project cannot use, because anything
// URP Unlit did and this shader does not do is a SILENT change to a panel that
// already ships:
//   - the forward pass, which is the whole shader;
//   - DepthOnly, because the panel has to appear in _CameraDepthTexture. Every
//     depth reading effect in the game goes through it, the drifting dust of
//     Assets/Scripts/Render/Atmosphere.cs included;
//   - DepthNormalsOnly, because SSAO in Assets/Settings/PC_Renderer.asset runs
//     with Source: 1, which is DEPTH-NORMALS. A shader with no such pass is
//     simply missing from that prepass, which costs it its own ambient
//     occlusion and feeds the pixels behind it a normal that is not there;
//   - no ShadowCaster, because URP Unlit has none either: the panel casts no
//     shadow today and must not start. Its parent is a solid carvable wall
//     (PhotoContent.BuildBackdrop) and THAT casts the shadow;
//   - no GBuffer pass, because the renderer is Forward+ (m_RenderingMode: 2)
//     and deferred lighting is stencilled out of an unlit material anyway;
//   - no Meta pass (nothing here is lightmapped) and no MotionVectors pass (no
//     TAA, no per-object motion vectors; the anti-aliasing is MSAA 4 + SMAA).
//
// PRD_VISUAL appendix C.15's rule applies to every line added here later: each
// pass compiles only the code it reaches, so A SYMBOL IS ONLY AS AVAILABLE AS
// THE LEAST-INCLUDED PASS THAT USES IT. Check all three, not only the one whose
// output you happen to be looking at. And appendix C.14: a .shader that does
// not compile fails NOTHING in this harness (Builder.CompileCheck reports C#
// errors only), so a broken pass here surfaces as a panel that draws in magenta
// weeks later, not as a red test.
//
// ---------------------------------------------------------------------------
// BRIGHTNESS, WHICH IS A CONTRACT AND NOT A TASTE
// ---------------------------------------------------------------------------
// Bloom is thresholded at 1.05 in HDR so that only emissives cross it, and
// check 6.3 thresholds the frame at 0.98 and requires every surviving pixel to
// lie inside an emissive's bounds or the sun disc. A painted backdrop is
// neither, so every term below is bounded: the vignette and the grain can only
// scale the ramp by at most 1.02, and the border band, the one term that
// LIGHTENS, is capped hue-preserving at BorderCeiling. The shipped palette is
// nowhere near that cap (backdrop_bottom is 0.93 sRGB, about 0.85 linear, and
// the band lands near 0.90 linear), so the cap is a guard against a future
// repaint rather than a compromise on this one.
//
// The dissolve's edge band is the ONE term in this file above that ceiling,
// and it is above it on purpose: RevealEdgeEnergy is authored past the bloom
// threshold exactly as Surface.shader's identical band is, because a placement
// has to read as light arriving and not as a colour change. It is also the only
// term here that is TRANSIENT: it exists solely while _Reveal is below 1, which
// PhotoContent holds for 0.4 s per placement and never in the picture studio
// (a display content is never dissolved). Check 6.3's frames are not captured
// mid dissolve, which is the same ground Surface's band has stood on since
// Tier 4; a probe stage that ever does capture one has to whitelist both bands,
// not one.
Shader "Viewpoint/Backdrop"
{
    Properties
    {
        // These two are written BY NAME from Materials.Backdrop and read back by
        // Assets/Tests/EditMode/MaterialsTests.cs. They are also the names URP
        // Unlit uses, and that is the point: the fallback in
        // Materials.BackdropShader needs no second code path, because a
        // material built for this shader is a valid URP Unlit material with the
        // extra floats ignored. Renaming one of them is a test failure and a
        // dead fallback, not a refactor.
        [MainTexture] _BaseMap ("Gradient ramp", 2D) = "white" {}
        [MainColor] _BaseColor ("Tint", Color) = (1, 1, 1, 1)

        // V-VFX-01, and the only two properties here written PER RENDERER
        // through a MaterialPropertyBlock rather than on the material, so a
        // dissolving panel still shares the one material Materials.Backdrop
        // cached for its palette pair (PRD_VISUAL 3.4 needs that sharing: the
        // picture studio draws the same materials as the world).
        //
        // At 1 and 0 they are a complete no op: the reveal branch is not
        // entered, the seed is never read, and a material that nobody writes
        // them on renders exactly as it did before Tier 4. That also keeps the
        // URP Unlit fallback of Materials.BackdropShader honest, which is what
        // the note above is about: two more floats an Unlit material ignores
        // cost that fallback the dissolve and nothing else.
        //
        // Assets/Scripts/Photo/PhotoContent.cs gates on
        // material.HasFloat(Materials.RevealId), so declaring _Reveal here is
        // what makes a placed panel visible to that animation at all.
        _Reveal ("Reveal", Range(0, 1)) = 1

        // A plain decorrelating offset into the dissolve field, and the same
        // float Surface.shader takes for the same purpose, so the two files
        // read the same when they are compared side by side. Here it drives
        // NOTHING but the dissolve: this panel has no colour jitter to disturb
        // (V-MAT-03 belongs to the solids), so a caller may safely push a seed
        // of its own choosing, and nothing pushes one today.
        _Seed ("Per instance seed", Float) = 0

        // Everything from here down is authored as a default and left alone by
        // C#, exactly as GradientSky.shader's sun and cloud knobs are, so the
        // painting can be retuned without touching a script or invalidating a
        // material cache. The defaults ARE the numbers V-MAT-08 pins.
        _Grain ("Paper grain", Range(0, 0.2)) = 0.02

        // Grain lattice cells per world METRE for the coarse octave; the fine
        // one is GrainFineRatio times denser. A density per metre and not per
        // UV, so that panels of different sizes carry the same paper.
        //
        // 18 is a cell of about 5.5 cm, and that number comes from how big
        // these panels really are rather than from what paper looks like in the
        // hand. PhotoMath.BackdropSize builds a panel that exactly fills the
        // photo frustum, so at the depths photos.json ships (18 to 28.5 m at 50
        // degrees of vertical fov) a placed backdrop is 17 to 27 METRES across
        // and stands that same distance away: one pixel of a 1280 x 720 frame
        // covers 2.3 to 3.7 cm out there. A 7 mm cell is therefore already past
        // Nyquist in the first frame anyone sees, and the grain would fade to
        // exactly nothing in every reference frame of PRD_VISUAL 6.1 while
        // looking perfect two metres from the panel. The paper is scaled to the
        // panel, and the panel is twenty metres of painted board rather than a
        // sheet of A4.
        _GrainCells ("Grain cells per metre", Range(2, 500)) = 18

        _Vignette ("Edge vignette", Range(0, 0.5)) = 0.06

        // Where the vignette starts, as a fraction of the way from the centre
        // to the nearest edge. 0.35 spreads the 0.06 over the outer two thirds,
        // which is a gradient the eye reads as light falling off across a
        // surface; concentrating it in the last tenth would read as a dirty
        // frame instead.
        _VignetteStart ("Vignette start", Range(0, 1)) = 0.35

        // In METRES, not in UV. See the panel size note in the header.
        _BorderWidth ("Border band metres", Range(0, 0.2)) = 0.02
        _BorderLighten ("Border lightening", Range(0, 0.5)) = 0.05
    }

    // Shared by all three passes, and holding exactly what HAS to be shared:
    // the material cbuffer, which the SRP batcher requires to be bit identical
    // across passes, the texture it names, and the dissolve. Every constant and
    // every helper of the PAINTING lives in the forward pass instead, because
    // that is the only pass that paints, and appendix C.15's lesson is that a
    // symbol is only as available as the least-included pass that uses it: a
    // helper declared where it is used cannot be the thing that breaks a pass a
    // reviewer never looks at.
    //
    // GrainHash used to live down there with the rest of the painting and now
    // lives here, which is not a tidy-up: the dissolve clips in all three
    // passes, it has to reuse the one hash this file owns rather than grow a
    // second one with a second set of GPU vendor risks, so the hash is no
    // longer a helper of the painting alone. GrainFade stayed below, because
    // the grain's Nyquist guard is still the grain's alone.
    HLSLINCLUDE

    #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

    // Every property above appears here in the SAME ORDER with the matching
    // HLSL type, the texture excepted: it is declared outside the cbuffer while
    // its _ST float4 stays inside. A property declared in Properties and
    // missing here is not a warning, it is a shader that has silently fallen
    // out of SRP batching, so the two lists are kept in step by eye every time
    // one of them grows. Surface.shader and GradientSky.shader both carry this
    // same note for the same reason.
    CBUFFER_START(UnityPerMaterial)
        // Declared because Unity serialises an _ST for every 2D property, and a
        // serialised property outside the cbuffer is exactly what breaks
        // batching. NOTHING samples through it: the panel's UVs must land on
        // the ramp one to one, and a tiling would repeat the sky inside its own
        // frame.
        float4 _BaseMap_ST;
        float4 _BaseColor;
        float _Reveal;
        float _Seed;
        float _Grain;
        float _GrainCells;
        float _Vignette;
        float _VignetteStart;
        float _BorderWidth;
        float _BorderLighten;
    CBUFFER_END

    // Its own sampler rather than a shared one, which is appendix C.15's second
    // trap: a sampler named after a texture that a given pass does not
    // reference fails to compile in THAT pass only. Here the two depth passes
    // reference neither the texture nor the sampler, so both are stripped
    // together and the name can never dangle.
    TEXTURE2D(_BaseMap);
    SAMPLER(sampler_BaseMap);

    /// One pseudo random value per integer lattice cell, in 0..1. Hand
    /// written, because PRD_VISUAL 3.2's ban on binary assets still holds for
    /// anything that is not one of the ten CC0 PBR sets appendix C.11
    /// admitted, and a grain texture is not one of them. No sin() in it, for
    /// the reason GradientSky.NoiseHash gives: sin based hashes differ between
    /// GPU vendors, and a panel whose paper changes per driver is not paper.
    /// The dissolve inherits that guarantee by reusing this: a placement that
    /// broke up in a different pattern per driver would not be a dissolve
    /// either.
    ///
    /// NOT GradientSky's hash itself, and the difference matters here. That one
    /// is frac(p.x * p.y * p.z * (p.x + p.y + p.z)) over a per axis frac, which
    /// is very nearly SEPARABLE: each output is a product of one sequence in x
    /// and one in y, and sampled over a plane it shows a faint diagonal weave.
    /// A cloud hides that behind two octaves and a soft threshold; a flat panel
    /// hides nothing, and a weave in the paper is precisely the regularity this
    /// grain exists to break. Mixing the two coordinates through a dot product
    /// first removes it for the same handful of instructions.
    float GrainHash(float2 cell)
    {
        // The frac() first is what keeps the precision honest whatever the
        // caller feeds in. The coordinates this is called with are bounded by
        // construction (the fine grain octave of a 27 m panel reaches about
        // 3100, and the dissolve's folded lattice a few thousand more), but a
        // hash that quantises into visible bands the day someone raises
        // _GrainCells is not a hash worth having.
        float3 p = frac(float3(cell.xyx) * 0.1031);
        p += dot(p, p.yzx + 33.33);
        return frac((p.x + p.y) * p.z);
    }

    // ---------------------------------------------------------------------
    // V-VFX-01's dissolve. See the header: pure in world position and _Seed,
    // not entered at all at _Reveal 1, and clipped in every pass that writes
    // depth.
    // ---------------------------------------------------------------------

    // The dissolve field's lattice, in cells per world METRE, and deliberately
    // the SAME 6.0 as Surface.shader's RevealNoiseScale rather than a number
    // retuned for a large flat panel.
    //
    // The case for coarsening it here is real and was weighed. A placed panel
    // is 17 to 27 m across (PhotoMath.BackdropSize at the depths photos.json
    // ships), so 6 cells per metre puts about 120 cells across it, and at the
    // 18 to 28.5 m it stands away one pixel covers 2.3 to 3.7 cm, which leaves
    // a 17 cm cell about 5 to 7 pixels wide. Judged on the panel alone, nearer
    // one cell per metre would read the way a dissolving block reads in the
    // hand, and that is the number the grain's own density argument would have
    // produced.
    //
    // It loses to two facts about where this panel actually is. First, the quad
    // hugs the front face of a CARVABLE WALL one millimetre behind it
    // (PhotoContent.BuildBackdrop), and that wall is drawn by
    // Viewpoint/Surface: two dissolves at different cell sizes inside the same
    // rectangle is exactly the seam this change exists to remove, only moved
    // from "one pops, one melts" to "one melts in blobs, one melts in
    // speckle". Second, the props of the same placement stand at the same 18 to
    // 28.5 m as the panel does, so matching the field in METRES is what matches
    // it on SCREEN; an angular argument that treats the panel as the only thing
    // in frame is answering a question nobody asked. A placement therefore
    // dissolves at one grain across every surface it is made of, which is the
    // reading the item asks for. The price is that a 5 pixel pattern of clipped
    // holes crawls a little as the camera moves, and MSAA cannot help (a clip
    // edge inside a triangle has no geometric edge to sample); it is the price
    // every placed prop already pays for the same 0.4 s.
    static const float RevealNoiseScale = 6.0;

    // How the third axis is folded into the two dimensional hash above.
    //
    // The field must be three dimensional, and that is not a preference: a
    // placed panel faces wherever the player aimed, so a field built from two
    // world axes would leave the third free and paint the panel in STRIPES
    // along it, and a panel facing down a world axis would dissolve in bands.
    // Rather than add a second, three dimensional hash, the integer cell is
    // folded into one float2 with non integer weights. Non integer is what
    // makes it injective on the lattice: cell.x differs by whole numbers, so no
    // pair of distinct cells can meet unless a whole number equals 7.31 or 3.79
    // times another. The weights are small so the folded coordinate stays in
    // the range where the hash's leading frac() has precision to spare, and
    // GrainHash amplifies its input by about 33 before wrapping, so a fold of
    // 0.31 of a cell is already a fully decorrelated draw.
    static const float2 RevealFold = float2(7.31, 3.79);

    float RevealHash(float3 cell)
    {
        return GrainHash(cell.xy + cell.z * RevealFold);
    }

    /// Smooth value noise on the lattice, three dimensional, with the same
    /// f * f * (3 - 2f) weights Surface.shader's SurfaceNoise uses.
    ///
    /// SMOOTH and not the hard cells the grain samples, and the two wants are
    /// genuinely opposite: paper grain wants an uncorrelated speckle, while a
    /// dissolve threshold applied to hard cells would clip whole rectangles at
    /// once and read as a mosaic wipe with a mosaic of glowing tiles at its
    /// front. The edge band needs a GRADIENT through the threshold to exist at
    /// all.
    float RevealNoise(float3 p)
    {
        float3 cell = floor(p);
        float3 f = frac(p);
        float3 u = f * f * (3.0 - 2.0 * f);

        float c000 = RevealHash(cell + float3(0.0, 0.0, 0.0));
        float c100 = RevealHash(cell + float3(1.0, 0.0, 0.0));
        float c010 = RevealHash(cell + float3(0.0, 1.0, 0.0));
        float c110 = RevealHash(cell + float3(1.0, 1.0, 0.0));
        float c001 = RevealHash(cell + float3(0.0, 0.0, 1.0));
        float c101 = RevealHash(cell + float3(1.0, 0.0, 1.0));
        float c011 = RevealHash(cell + float3(0.0, 1.0, 1.0));
        float c111 = RevealHash(cell + float3(1.0, 1.0, 1.0));

        float x00 = lerp(c000, c100, u.x);
        float x10 = lerp(c010, c110, u.x);
        float x01 = lerp(c001, c101, u.x);
        float x11 = lerp(c011, c111, u.x);
        return lerp(lerp(x00, x10, u.y), lerp(x01, x11, u.y), u.z);
    }

    /// The field itself, in 0..1, and the same shape as Surface.shader's
    /// RevealField down to the 37.0 the seed is multiplied by, so the two
    /// dissolve at the same rate through the same range of thresholds.
    ///
    /// The patterns are of the same GRAIN and are not the same pattern, since
    /// this file hashes with GrainHash and Surface with SurfaceHash, and they
    /// need not be: the panel and the wall it hugs clip against the same
    /// _Reveal, so they thin out together whatever their patterns are. Pushing
    /// the wall's seed onto the panel would not align them either, and is
    /// therefore not worth a C# change.
    float RevealField(float3 positionWS)
    {
        return RevealNoise(positionWS * RevealNoiseScale + _Seed * 37.0);
    }

    /// The clip, and it runs in the forward pass AND both depth passes. See the
    /// header for what a panel that clips in only one of them does.
    ///
    /// At _Reveal 1 the branch is not entered at all, so a resolved panel pays
    /// nothing and, more importantly, cannot be clipped by a noise value that
    /// happens to land on exactly zero at a lattice point.
    void ApplyReveal(float3 positionWS)
    {
        UNITY_BRANCH
        if (_Reveal < 1.0)
        {
            clip(RevealField(positionWS) - (1.0 - _Reveal));
        }
    }

    ENDHLSL

    SubShader
    {
        Tags
        {
            "RenderType" = "Opaque"
            "Queue" = "Geometry"
            "RenderPipeline" = "UniversalPipeline"
            "UniversalMaterialType" = "Unlit"
            "IgnoreProjector" = "True"
        }
        LOD 100

        // ------------------------------------------------------------------
        //  The painting. Ramp, then vignette, then border band, then grain.
        Pass
        {
            Name "BackdropUnlit"
            Tags
            {
                // URP Unlit leaves this tag off and relies on the implicit
                // SRPDefaultUnlit, which the forward renderer does draw. It is
                // written out here because Surface.shader writes it out, and
                // because "the pass with no LightMode" is a thing one has to
                // know rather than read.
                "LightMode" = "UniversalForward"
            }

            // -------------------------------------
            // Render State Commands
            Blend One Zero
            ZWrite On
            // The quad is single sided and faces the eye (its normal is
            // (0, 0, -1), see ProceduralMeshes.Quad). Cull Back keeps it that
            // way: a backdrop seen from behind shows nothing, which is correct
            // for a painted panel and is what URP Unlit did with _Cull at its
            // default of 2.
            Cull Back

            HLSLPROGRAM
            // 3.5 rather than URP Unlit's 2.0, and the same profile on all three
            // passes so one number governs the whole file. It is needed for the
            // explicit-LOD fetch of the horizon colour below.
            #pragma target 3.5

            // -------------------------------------
            // Shader Stages
            #pragma vertex BackdropVertex
            #pragma fragment BackdropFragment

            // -------------------------------------
            // Unity defined keywords
            // SSAO, and it is here for PARITY and not for looks: URP Unlit
            // multiplies its output by the screen space occlusion factor, so
            // dropping this line would lighten every panel that stands near
            // other geometry compared with what already ships. The occlusion
            // arrives from the DepthNormalsOnly pass at the bottom of this file.
            #pragma multi_compile_fragment _ _SCREEN_SPACE_OCCLUSION
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"
            // Fog, likewise for parity: URP Unlit fogs, and RenderSettings runs
            // Exponential fog at density 0.012 (Tier 1). A panel that skips it
            // while the sky and every solid surface keep fogging reads as a
            // rendering bug. In URP 17 fog is a keyword INCLUDE and not a
            // multi_compile_fog line.
            //
            // The HEIGHT fog of V-SKY-04's second stage is deliberately NOT
            // here: it lives in Surface.shader because it exists to sink SOLID
            // geometry into the abyss, and a painted panel is a picture of
            // somewhere else, not a mass hanging over the drop.
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"

            // Two of URP Unlit's keyword blocks are deliberately NOT here, and
            // both are decisions rather than omissions:
            //   - the _DBUFFER variants, which are how a DECAL reaches an unlit
            //     surface. A painted sky is a picture of somewhere else and
            //     must not collect the world's decals: the paint on the FLOOR
            //     (PRD 5.1's "stand here" markers) belongs to the geometry the
            //     player walks on, which Surface.shader draws and which does
            //     carry those variants. A shader without them simply receives
            //     no decal, with no error;
            //   - DEBUG_DISPLAY, the rendering debugger's views. Nothing in the
            //     game or the harness reads them, and leaving the keyword
            //     undeclared is also what makes the DEBUG_DISPLAY block inside
            //     AmbientOcclusion.hlsl compile out instead of pulling the
            //     whole debug library in behind it.

            //--------------------------------------
            // GPU Instancing
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DOTS.hlsl"

            // -------------------------------------
            // Includes
            // Core.hlsl does NOT pull this in, and it is what declares
            // GetScreenSpaceAmbientOcclusion. Appendix C.15's first trap was
            // exactly this shape: a function that resolved in one pass because
            // something else included it transitively, and was undeclared
            // everywhere else. Only this pass uses it, so only this pass
            // includes it.
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/AmbientOcclusion.hlsl"

            // ---------------------------------------------------------
            //  Constants and helpers of the painting, plus the dissolve's edge
            //  band, which is a colour and therefore belongs here too. They
            //  live in this pass and not in the shared block above because this
            //  is the only pass that paints: appendix C.15's lesson is that a
            //  symbol is only as available as the least-included pass that uses
            //  it, so what the depth passes need (the cbuffer, the hash and the
            //  reveal field) lives up there and nothing else does.
            // ---------------------------------------------------------

            // The linear ceiling the border band is capped at. Under the bloom
            // threshold of 1.05 and under the 0.98 of check 6.3, with room to
            // spare for the grain that is applied after it.
            static const float BorderCeiling = 0.94;

            // A panel smaller than this in either axis gets no border band at
            // all: four times the default band, so a band can never eat a panel
            // it has no room to sit in. It also catches the one way PanelSizeWS
            // can fail (a mesh that is not a centred 0..1 quad comes out with a
            // panel size near zero, and without this guard a zero size would
            // put the WHOLE panel inside the band and paint it flat pale, which
            // is a plausible looking picture and therefore the worst kind of
            // bug).
            static const float MinPanelForBorder = 0.08;

            // A grain octave fades out between these two pixel footprints,
            // measured in lattice cells per pixel. Past half a cell per pixel
            // the lattice is beyond Nyquist.
            static const float GrainFadeStart = 0.5;
            static const float GrainFadeEnd = 1.0;

            // The grain runs in TWO octaves, and the split is forced by the
            // same arithmetic as the density on _GrainCells: at the distance a
            // placed panel is first seen one pixel covers two to four
            // centimetres, so only a coarse lattice survives there, while two
            // metres from the paint that same lattice is five centimetre blocks
            // with nothing finer inside them. One octave can be right at one of
            // those two distances and never at both. So a coarse octave carries
            // the term in the frames the reference shots of PRD_VISUAL 6.1 are
            // taken at, and a fine one 6.4 times denser (about 8 mm cells)
            // appears only within a few metres of the paint and fades out
            // before it can alias. 6.4 rather than 8, so the two lattices never
            // line their cells up, and the offset makes the fine one a
            // different patch of the field rather than a scaled copy of the
            // coarse one.
            static const float GrainFineRatio = 6.4;
            static const float2 GrainFineOffset = float2(23.7, 11.3);

            // Halves, so the two octaves together span exactly the amplitude
            // _Grain asks for and no more.
            static const float GrainCoarseWeight = 0.5;
            static const float GrainFineWeight = 0.5;

            /// Scales a colour so its largest channel lands on the ceiling,
            /// capping its value without touching its hue. Lifted from
            /// GradientSky.shader, where the same note applies: a per channel
            /// clamp caps the value and shifts the hue while doing it, and the
            /// backdrop's warm bottom (0.93, 0.90, 0.84) is exactly the sort of
            /// colour that would go pink under one.
            float3 CapToCeiling(float3 color, float ceiling)
            {
                float peak = max(max(color.r, color.g), max(color.b, 0.0001));
                return color * min(1.0, ceiling / peak);
            }

            // V-VFX-01's edge band, and every number here is Surface.shader's
            // own (CutColor, RevealEdgeEnergy, RevealEdgeWidth), copied because
            // the two files share no include and duplicated on purpose: a
            // placement whose sky glowed a different lavender or for a
            // different width than its blocks would be a worse defect than the
            // one this fixes. The two lists move together or not at all.
            //
            // The width is in FIELD units, not in metres, which is what makes
            // it match: it is a distance through the same noise range that
            // PhotoContent's RevealStart of 0.15 is calibrated against, so the
            // first frame of a placement is edge glow on this panel exactly as
            // it is on the wall behind it.
            static const float3 CutColor = float3(0.86, 0.82, 0.98);
            static const float RevealEdgeEnergy = 1.9;
            static const float RevealEdgeWidth = 0.16;

            /// How much of one grain octave survives at this pixel, in 0..1:
            /// full strength while a cell is comfortably bigger than a pixel,
            /// nothing once a pixel covers a whole cell.
            ///
            /// This is the term that keeps the grain from becoming the worst
            /// artefact on screen. An under-sampled lattice on a large flat
            /// panel does not read as fine grain: it crawls as the camera
            /// moves, and MSAA cannot help, because there is no geometric edge
            /// for it to sample.
            float GrainFade(float2 latticeCoord)
            {
                float footprint = max(length(ddx(latticeCoord)), length(ddy(latticeCoord)));
                return 1.0 - smoothstep(GrainFadeStart, GrainFadeEnd, footprint);
            }

            /// The panel's world size in metres, from the object space position
            /// of one of its corners. See the header: exact for a quad centred
            /// on its origin with UVs 0..1, which is what both of the quads
            /// this project can draw a backdrop with are, whether the size
            /// lives in the mesh or in the transform's scale.
            ///
            /// Computed per VERTEX and interpolated, and that is exact rather
            /// than approximate: abs() makes the result the same at all four
            /// corners of a centred quad, so the interpolator carries a
            /// constant.
            float2 PanelSizeWS(float3 positionOS)
            {
                // The extent, not the half extent: on a centred quad every
                // corner sits at half the size from the origin.
                float2 extentOS = abs(positionOS.xy) * 2.0;

                // Through the object-to-world 3x3 rather than off its column
                // lengths, so a rotated panel (which every placed one is: it
                // faces wherever the player aimed) measures the same as an axis
                // aligned one.
                float3x3 objectToWorld = (float3x3)GetObjectToWorldMatrix();
                return float2(
                    length(mul(objectToWorld, float3(extentOS.x, 0.0, 0.0))),
                    length(mul(objectToWorld, float3(0.0, extentOS.y, 0.0))));
            }

            struct Attributes
            {
                float4 positionOS : POSITION;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float2 uv : TEXCOORD0;
                // In metres. Constant across the quad; see PanelSizeWS.
                float2 panelSize : TEXCOORD1;
                float3 positionWS : TEXCOORD2;
                half fogFactor : TEXCOORD3;
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings BackdropVertex(Attributes input)
            {
                Varyings output = (Varyings)0;

                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                VertexPositionInputs vertexInput = GetVertexPositionInputs(input.positionOS.xyz);

                half fogFactor = 0;
            #if !defined(_FOG_FRAGMENT)
                fogFactor = ComputeFogFactor(vertexInput.positionCS.z);
            #endif

                // The mesh UV, untransformed: v = 0 at the bottom of the panel,
                // which is the row the ramp's bottom colour lives on.
                output.uv = input.uv;
                output.panelSize = PanelSizeWS(input.positionOS.xyz);
                output.positionWS = vertexInput.positionWS;
                output.fogFactor = fogFactor;
                output.positionCS = vertexInput.positionCS;
                return output;
            }

            void BackdropFragment(
                Varyings input
                , out half4 outColor : SV_Target0
            #ifdef _WRITE_RENDERING_LAYERS
                , out uint outRenderingLayers : SV_Target1
            #endif
            )
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                // The same clip as the two depth passes, and first: clipping
                // after the painting would still be correct on screen and would
                // still cost the two ramp fetches and both grain octaves for a
                // fragment that is thrown away.
                ApplyReveal(input.positionWS);

                float2 uv = input.uv;
                float2 panel = input.panelSize;

                // --- the ramp, untouched ------------------------------------
                // _BaseColor is white (Materials.Backdrop, and MaterialsTests
                // asserts it), so this multiply is an identity that exists only
                // so a material authored by hand can still tint the panel.
                float3 color = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, uv).rgb * _BaseColor.rgb;

                // --- V-MAT-08, the edge vignette ----------------------------
                // A BOX falloff and not a radial one: the panel is a rectangle
                // and the darkening has to follow its frame, or a 16:9 panel
                // would carry two dark bands on its short sides and none on its
                // long ones. In normalised coordinates rather than metres, so a
                // small panel and a large one look like the same painting
                // rather than like the same lamp shone on two different sizes.
                float2 fromCentre = abs(uv * 2.0 - 1.0);
                float edgeness = max(fromCentre.x, fromCentre.y);
                color *= 1.0 - _Vignette * smoothstep(_VignetteStart, 1.0, edgeness);

                // --- V-MAT-08, the border band ------------------------------
                // Distance to the nearest edge, in METRES, which is the whole
                // reason the panel size is derived at all.
                float2 edgeMetres = min(uv, 1.0 - uv) * panel;
                float edgeDistance = min(edgeMetres.x, edgeMetres.y);

                // Antialiasing width from the per axis derivatives rather than
                // from fwidth(edgeDistance): the min() above has a crease along
                // the panel's diagonals, and a derivative taken across it
                // reports a jump that would show as four bright pixels in the
                // corners.
                float bandAA = max(max(fwidth(edgeMetres.x), fwidth(edgeMetres.y)), 1e-5);
                float band = 1.0 - smoothstep(_BorderWidth - bandAA, _BorderWidth + bandAA, edgeDistance);

                // Faded out once a pixel is wider than the band itself. A 2 cm
                // line on a 9 m panel is sub-pixel from across a level, and a
                // sub-pixel line that is drawn anyway is a dashed, crawling
                // edge: the acceptance criterion asks the panel to be
                // distinguishable at its edges up close, not to sparkle at
                // thirty metres.
                band *= saturate(_BorderWidth / bandAA);

                // And off entirely where a band cannot fit. See
                // MinPanelForBorder: this is the guard on the derivation.
                band *= step(MinPanelForBorder, min(panel.x, panel.y));

                // The panel's OWN horizon colour, which is the ramp's bottom
                // row: V-MAT-08 words it as "sky_horizon", and for a panel
                // whose two palette keys the caller chose, the horizon is
                // whichever colour the caller put at the bottom. Read from the
                // ramp rather than from a property, so it follows a repaint of
                // the palette with no C# change and no second source of truth.
                // An explicit LOD 0 because the UV is constant here, which
                // gives the sampler no derivatives to pick a mip from (the ramp
                // has no mips either, so this is the honest way to say so).
                float3 horizon = SAMPLE_TEXTURE2D_LOD(_BaseMap, sampler_BaseMap, float2(0.5, 0.0), 0).rgb * _BaseColor.rgb;
                float3 borderColor = CapToCeiling(horizon + _BorderLighten, BorderCeiling);

                // AFTER the vignette on purpose: the band is bare panel where
                // the paint stopped, so it must not be darkened by the paint's
                // own falloff. Vignette the paint, then lay the margin over it.
                color = lerp(color, borderColor, band);

                // --- V-MAT-08, the paper grain ------------------------------
                // Lattice coordinates in cells, from the position on the panel
                // in metres, so the paper has a fixed physical density whatever
                // the panel measures.
                //
                // Anchored to the PANEL's own corner and not to world position,
                // which is two decisions in one. Two panels of the same size
                // carry the same sheet of paper, which is what a sketchbook
                // does anyway; and the paper does not depend on where the
                // player happened to aim, so the reference frames of
                // PRD_VISUAL 6.1 stay comparable between runs.
                float2 coarseCoord = uv * panel * _GrainCells;
                float2 fineCoord = coarseCoord * GrainFineRatio + GrainFineOffset;

                // Hard cells, NOT the smoothly interpolated value noise
                // GradientSky.shader uses. That shader interpolates because a
                // cloud with a discontinuity in it reads as a hard edge, which
                // V-SKY-02 forbids; paper grain wants the opposite, an
                // uncorrelated speckle. Interpolating here would turn fibre
                // into soft blotches and the panel would read as damp.
                //
                // Each octave is SIGNED and centred on zero, so the grain is
                // mean preserving: the average colour of the panel is still
                // exactly its ramp. That is the same discipline appendix C.12
                // imposes on the albedo detail of every solid surface, and it
                // is why the grain can never drift the painting away from the
                // palette however far _Grain is pushed.
                float grain =
                    (GrainHash(floor(coarseCoord)) - 0.5) * GrainCoarseWeight * GrainFade(coarseCoord)
                    + (GrainHash(floor(fineCoord)) - 0.5) * GrainFineWeight * GrainFade(fineCoord);
                color *= 1.0 + grain * 2.0 * _Grain;

                // --- parity with URP Unlit ----------------------------------
            #if defined(_SCREEN_SPACE_OCCLUSION)
                AmbientOcclusionFactor aoFactor = GetScreenSpaceAmbientOcclusion(
                    GetNormalizedScreenSpaceUV(input.positionCS));
                color *= aoFactor.directAmbientOcclusion;
            #endif

                // --- V-VFX-01, the dissolve's edge band --------------------
                // A lavender white glow on the threshold, so a placed panel
                // reads as paint arriving rather than as a hole closing, and
                // the same band Surface.shader puts on every other face of the
                // same placement.
                //
                // Recomputed here rather than carried out of ApplyReveal, for
                // the reason Surface gives: at _Reveal 1 nothing in this block
                // runs at all, and that is the case that has to be free.
                //
                // AFTER the occlusion multiply and before the fog. Emission is
                // light leaving the surface, so screen space occlusion has no
                // business darkening it (URP's own lit path does not occlude
                // emission either), while fog sits between the panel and the
                // eye and dims everything the panel sends, glow included.
                UNITY_BRANCH
                if (_Reveal < 1.0)
                {
                    float band = 1.0 - smoothstep(0.0, RevealEdgeWidth,
                        RevealField(input.positionWS) - (1.0 - _Reveal));
                    color += CutColor * (band * RevealEdgeEnergy);
                }

                // Fog last, and through InitializeInputDataFog rather than the
                // interpolated factor alone: URP forces fragment evaluation
                // (_FOG_FRAGMENT is defined in ShaderVariablesFunctions.hlsl),
                // and this call is what handles both cases from the one vertex
                // value. Surface.shader's forward pass does the same.
                half fogFactor = InitializeInputDataFog(float4(input.positionWS, 1.0), input.fogFactor);
                color = MixFog(color, fogFactor);

                // Opaque, always. The ramp's alpha is 1 and a painted wall that
                // could go transparent would show the abyss through a photo.
                outColor = half4(color, 1.0);

            #ifdef _WRITE_RENDERING_LAYERS
                outRenderingLayers = EncodeMeshRenderingLayer();
            #endif
            }
            ENDHLSL
        }

        // ------------------------------------------------------------------
        //  Depth only. Without it the panel is absent from
        //  _CameraDepthTexture: it draws, and everything that reads depth
        //  behaves as though the sky were there instead.
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
            #pragma vertex BackdropDepthOnlyVertex
            #pragma fragment BackdropDepthOnlyFragment

            //--------------------------------------
            // GPU Instancing
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DOTS.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                // Carried for the dissolve clip and nothing else: the three
                // painting terms never reach this pass, so before V-VFX-01
                // this struct held the clip space position alone.
                float3 positionWS : TEXCOORD0;
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings BackdropDepthOnlyVertex(Attributes input)
            {
                Varyings output = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                output.positionWS = TransformObjectToWorld(input.positionOS.xyz);
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                return output;
            }

            half BackdropDepthOnlyFragment(Varyings input) : SV_TARGET
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                // The dissolve clip, and it is not optional here. The three
                // painting terms only change the panel's colour and still ask
                // nothing of this pass, but _Reveal DISCARDS: depth written for
                // a fragment the forward pass throws away leaves a panel that
                // dissolves on screen while going on hiding what is behind it
                // in _CameraDepthTexture, which is the drifting dust of
                // Atmosphere.cs and every other depth reading effect in the
                // game. Nothing added to the forward pass may discard a
                // fragment without discarding it here too.
                ApplyReveal(input.positionWS);

                return input.positionCS.z;
            }
            ENDHLSL
        }

        // ------------------------------------------------------------------
        //  Depth normals. THE pass that decides whether this panel takes part
        //  in ambient occlusion at all: SSAO in Assets/Settings/PC_Renderer.asset
        //  runs with Source: 1, which is DEPTH-NORMALS.
        //
        //  Tagged DepthNormalsOnly and not DepthNormals, which is the unlit
        //  convention and strictly the safer of the two: URP's prepass looks
        //  for { "DepthNormals", "DepthNormalsOnly" } while the forward-only
        //  path looks for { "DepthNormalsOnly" } alone, so this tag is picked up
        //  in both places and "DepthNormals" in only one.
        Pass
        {
            Name "DepthNormalsOnly"
            Tags
            {
                "LightMode" = "DepthNormalsOnly"
            }

            // -------------------------------------
            // Render State Commands
            ZWrite On
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5

            // -------------------------------------
            // Shader Stages
            #pragma vertex BackdropDepthNormalsVertex
            #pragma fragment BackdropDepthNormalsFragment

            // -------------------------------------
            // Universal Pipeline keywords
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"

            //--------------------------------------
            // GPU Instancing
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DOTS.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float3 normalWS : TEXCOORD0;
                // For the dissolve clip. See the DepthOnly pass: the same
                // value must come out of all three passes, so it comes from the
                // same interpolated world position everywhere.
                float3 positionWS : TEXCOORD1;
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings BackdropDepthNormalsVertex(Attributes input)
            {
                Varyings output = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                output.positionWS = TransformObjectToWorld(input.positionOS.xyz);

                // TransformObjectToWorldNormal and not the plain direction
                // transform: PhotoContent draws this quad at a non-uniform
                // scale (width, height, 1), and this is the call that carries
                // the inverse transpose. With the plain one a stretched panel
                // would hand SSAO a normal that is not perpendicular to it.
                output.normalWS = TransformObjectToWorldNormal(input.normalOS);
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                return output;
            }

            void BackdropDepthNormalsFragment(
                Varyings input
                , out half4 outNormalWS : SV_Target0
            #ifdef _WRITE_RENDERING_LAYERS
                , out uint outRenderingLayers : SV_Target1
            #endif
            )
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                // The dissolve clip, and this is the pass where leaving it out
                // is hardest to see and most wrong: SSAO runs from the
                // depth-normals prepass (Source: 1), so a panel that is still
                // whole in here goes on occluding its neighbours with its full
                // rectangle while dissolving on screen. The clipped fragments
                // must also be absent from the normal buffer, or the pixels
                // behind the holes are shaded against a normal belonging to a
                // surface that is no longer in front of them.
                ApplyReveal(input.positionWS);

                // The flat mesh normal, and no _GBUFFER_NORMALS_OCT variant.
                // URP Unlit carries that keyword for the deferred path; this
                // renderer is Forward+, and Surface.shader (which draws every
                // other surface in the game and feeds the same prepass) writes
                // its normal unpacked. The two encodings must agree or ambient
                // occlusion would be computed from different data on either
                // side of a panel's silhouette.
                outNormalWS = half4(NormalizeNormalPerPixel(input.normalWS), 0.0);

            #ifdef _WRITE_RENDERING_LAYERS
                outRenderingLayers = EncodeMeshRenderingLayer();
            #endif
            }
            ENDHLSL
        }
    }

    // No fallback, for the reason Surface.shader gives: a fallback would let a
    // stripped variant draw as something else entirely, and "the panel is
    // subtly the wrong shader" is a harder bug to see than "the panel is
    // magenta". The graceful degradation for a stripped shader lives in
    // Materials.BackdropShader, in C#, where it can be logged.
    Fallback Off
}
