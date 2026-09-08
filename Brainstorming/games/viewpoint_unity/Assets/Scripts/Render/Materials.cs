using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Material factory with a cache (PRD 14.2), so every box of the same color
    /// and emission shares one material. Nothing in the game builds a material
    /// by hand: the palette is the only source of color.
    ///
    /// Since PRD_VISUAL Tier 2 the lit half of this factory drives
    /// <c>Viewpoint/Surface</c> instead of <c>Universal Render Pipeline/Lit</c>.
    /// That shader is triplanar and world space, so it needs no UVs from the
    /// generated meshes, and it takes two things from here that the palette
    /// alone cannot say: WHICH family a surface belongs to (<c>_Style</c>) and
    /// WHICH CC0 PBR set it samples. Both are pure functions of the palette key,
    /// which is why <see cref="Solid"/> keeps its signature and its cache key.
    ///
    /// The albedo maps do NOT replace the palette color. The shader divides each
    /// sample by the texture's own mean so it becomes a modulation centred on
    /// 1.0, and the MEAN albedo of a face stays exactly its palette value
    /// (PRD_VISUAL Appendix C.12). That is what lets the game be heavily
    /// textured and still teach its rules in color: grey permanent, pale
    /// carvable, lavender ephemeral.
    ///
    /// Since PRD_VISUAL Tier 3 the UNLIT half drives <c>Viewpoint/Backdrop</c>
    /// instead of <c>Universal Render Pipeline/Unlit</c> (V-MAT-08). It is
    /// handed exactly what URP Unlit was handed and nothing more, so the only
    /// thing that changed on this side of the file is the Shader.Find string.
    /// Both of those names have to be in Always Included Shaders; the note on
    /// <see cref="SolidShader"/> says what happens when one is not.
    /// </summary>
    public static class Materials
    {
        // PRD 14.2: the original sets Godot roughness 0.85, which is smoothness
        // 0.15 for a URP Lit material. It stays 0.15 on the MATERIAL even though
        // PRD_VISUAL 4.5 asks for other values per family: those are the
        // shader's WORKING smoothness, derived from this one inside the style
        // branch (PRD_VISUAL Appendix C.4). Moving this number breaks port
        // fidelity and MaterialsTests at once.
        private const float SolidSmoothness = 0.15f;
        private const float SolidMetallic = 0f;

        // 4 x 64 vertical ramp, the size used by the original. Four pixels wide
        // because a one pixel wide texture is awkward to inspect and costs the
        // same in practice.
        private const int GradientWidth = 4;
        private const int GradientHeight = 64;

        // STYLE VALUES, fixed by the shader contract: the shader branches on the
        // integer, so these are data and not an enum anyone may renumber. Named
        // here so the table below reads as English rather than as a column of
        // digits.
        private const int StyleGround = 0;
        private const int StyleEphemeral = 1;
        private const int StylePaleSoft = 2;
        private const int StyleSteel = 3;
        private const int StyleLead = 4;
        private const int StyleWood = 5;
        private const int StyleStone = 6;
        private const int StyleRock = 7;
        private const int StylePaper = 8;
        private const int StyleGlass = 9;
        private const int StyleMarker = 10;

        /// <summary>Number of style slots, i.e. the length of the tables below.</summary>
        private const int StyleCount = 11;

        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        private static readonly int BaseMapId = Shader.PropertyToID("_BaseMap");
        private static readonly int SmoothnessId = Shader.PropertyToID("_Smoothness");
        private static readonly int MetallicId = Shader.PropertyToID("_Metallic");
        private static readonly int EmissionColorId = Shader.PropertyToID("_EmissionColor");
        private static readonly int StyleId = Shader.PropertyToID("_Style");
        private static readonly int NormalMapId = Shader.PropertyToID("_NormalMap");
        private static readonly int RoughMapId = Shader.PropertyToID("_RoughMap");
        private static readonly int MetalMapId = Shader.PropertyToID("_MetalMap");
        private static readonly int HeightMapId = Shader.PropertyToID("_HeightMap");
        private static readonly int AOMapId = Shader.PropertyToID("_AOMap");
        private static readonly int MapScaleId = Shader.PropertyToID("_MapScale");
        private static readonly int TextureStrengthId = Shader.PropertyToID("_TextureStrength");

        /// <summary>
        /// The per instance seed (V-MAT-03). Public because the seed is written
        /// per RENDERER through a MaterialPropertyBlock, by the component that
        /// owns the renderer, while all of those renderers keep sharing the one
        /// material this factory cached. See <see cref="SeedFor"/>.
        /// </summary>
        public static readonly int SeedId = Shader.PropertyToID("_Seed");

        /// <summary>
        /// The Tier 4 animation floats, public for exactly the reason
        /// <see cref="SeedId"/> is: both are written per RENDERER through a
        /// MaterialPropertyBlock by whichever component owns that renderer,
        /// while every one of those renderers keeps sharing the one material
        /// this factory cached.
        ///
        /// They live here, once, because three components were each declaring
        /// their own private copy. Three ids for the same two shader
        /// properties is three chances for one of them to drift from the name
        /// Surface.shader actually declares, and a MaterialPropertyBlock
        /// written to a name no shader has is silently a no-op.
        /// </summary>
        public static readonly int RevealId = Shader.PropertyToID("_Reveal");

        /// <inheritdoc cref="RevealId"/>
        public static readonly int CutGlowId = Shader.PropertyToID("_CutGlow");

        private static readonly Dictionary<string, Material> Cache = new Dictionary<string, Material>();

        /// <summary>
        /// Gradient textures, cached SEPARATELY from the materials and never
        /// cleared. Two reasons, and the second is the one that bites: a live
        /// material may still be sampling one, so destroying it on a cache clear
        /// would turn a painted backdrop black; and without its own cache every
        /// ClearCache followed by a Backdrop call allocated another 4 x 64
        /// texture with no owner, which the unit suite does about a dozen times
        /// a run.
        /// </summary>
        private static readonly Dictionary<string, Texture2D> Gradients = new Dictionary<string, Texture2D>();

        /// <summary>
        /// The CC0 PBR maps, keyed by their Resources path, and cached for the
        /// same reasons as the gradients above plus a third: about forty
        /// materials ask for the same five maps, and a Resources.Load per
        /// material pays the lookup forty times over for one texture.
        ///
        /// A MISS is cached too (a null value), because three of the ten sets
        /// ship no metalness map and none of them is an error: retrying the load
        /// on every material would just be a slower way of getting null.
        ///
        /// Never cleared and never destroyed, exactly like the gradients. These
        /// are assets owned by Resources and live materials are sampling them,
        /// and unlike a material nothing here depends on the palette: ClearCache
        /// exists so the next material picks up the current PALETTE, and the
        /// maps on disk have no palette in them.
        /// </summary>
        private static readonly Dictionary<string, Texture2D> Maps = new Dictionary<string, Texture2D>();

        /// <summary>
        /// Palette key to style family. This table is the ONE place the mapping
        /// lives: the shader knows the integers and this file knows the keys,
        /// and nothing in between gets an opinion.
        ///
        /// Two entries are worth explaining because they look wrong:
        ///   - the markers (teal, accent and their dark sides) are style Marker,
        ///     which samples NO texture at all. Gameplay PRD 5.1 makes them
        ///     painted signs on the ground: "stand here". A marker that gathers
        ///     grain, wear and a parallax offset stops reading as paint and
        ///     starts reading as one more slab, and the level loses its only
        ///     wordless instruction;
        ///   - the live battery is style Ground, not a metal. It is the amber
        ///     glowing thing in a grey world and its emission carries it; the
        ///     concrete grain is only there so its shell is not a flat blob.
        ///     Its LEAD twin (battery_sealed) is style Lead, which by contract
        ///     ignores emission and every time varying term. That contrast is
        ///     how the game says "no film prints this one".
        /// </summary>
        private static readonly Dictionary<string, int> StylesByKey = new Dictionary<string, int>
        {
            // Permanent ground and blocks: grey, a photo is ADDED to them.
            { "platform", StyleGround },
            // The SIDE keys are the island undersides, and they are the only
            // thing in the game that wants the Rock style: rock grain, a low
            // working smoothness, and the downward fade that sinks a mass into
            // the abyss. Until now nothing mapped to Rock at all, so Rock030 was
            // loaded by nobody and V-GEO-02's whole material half was dead.
            // The platform TOP stays Ground: you walk on concrete, not on rock.
            { "platform_side", StyleRock },

            // Pale carvable ground: lavender's pale cousin, so it pulses at half
            // amplitude rather than sitting flat like grey (V-MAT-05).
            { "platform_soft", StylePaleSoft },
            { "platform_soft_side", StylePaleSoft },

            // Ephemeral matter: the only family in the game that shimmers on its
            // own (constraint 3.1), which is the whole tell (V-MAT-04).
            { "erasable", StyleEphemeral },

            // Sealed matter: steel no photo opens, lead no film prints.
            { "sealed", StyleSteel },
            { "sealed_dark", StyleSteel },
            { "battery_sealed", StyleLead },

            // Props (V-MAT-07, V-PROP-02, V-PROP-05).
            { "wood", StyleWood },
            { "wood_dark", StyleWood },
            { "stone", StyleStone },
            { "frame", StylePaper },
            { "photo_back", StylePaper },
            // The MACHINE is metal, only the RING is glass. Both keys pointed at
            // Glass, which carries no maps at all, so the teleporter - one of the
            // two objects the owner named in PRD_VISUAL Appendix C.11 as wanting
            // real material detail - sampled no texture whatsoever while every
            // platform around it did. Steel gives the pad and the pillar brushed
            // metal that catches the sky reflection V-LIGHT-02 set up in Tier 1,
            // and its indigo palette colour keeps it unmistakable against the
            // grey steel of a sealed cage.
            //
            // The ring stays Glass: it is smooth, emission driven, and its glow
            // at energy 2.0 crossing the 1.05 bloom threshold is how a charged
            // exit reads from across a level. A texture on it would fight that.
            //
            // MetalPlates006 is on disk for the fuller "machine" look V-PROP-05
            // describes and is still unreferenced; wiring it needs a style of its
            // own, which belongs with the Tier 3 rebuild of this prop.
            { "teleporter", StyleSteel },
            { "teleporter_ring", StyleGlass },

            // Painted markers on the ground: flat, saturated, untextured.
            { "teal", StyleMarker },
            { "teal_dark", StyleMarker },
            { "accent", StyleMarker },
            { "accent_dark", StyleMarker },

            // The live battery and its tip.
            { "battery", StyleGround },
            { "battery_tip", StyleGround },
        };

        /// <summary>
        /// Style to CC0 texture set, indexed by the style integer. The sets and
        /// their purpose are listed in Assets/Resources/Textures/LICENSE.md; the
        /// file names are the contract that Assets/Editor/TextureImportRules
        /// reads to decide the import settings of each map.
        ///
        /// Two styles carry no set on purpose: Glass is smooth and driven by its
        /// emission, and Marker is flat paint. A null here means "leave every map
        /// at the shader's own property default", which is also what a missing
        /// FILE gets, so a set that ships no metalness map needs no special case
        /// anywhere.
        ///
        /// Rock023 (the decor islands) and MetalPlates006 (the teleporter
        /// machine) exist on disk and are not referenced here: both belong to
        /// geometry that Tier 3 introduces, and nothing in this table prevents a
        /// style being pointed at them then.
        /// </summary>
        private static readonly string[] SetsByStyle =
        {
            // Was Concrete034, changed after three passes at the looking-down
            // frame of level 1. Concrete034 kept reading as a GRID whatever the
            // scale, for two reasons no amount of retuning fixes:
            //   - it is 1024 x 512, and triplanar sampling uses square world
            //     space UVs, so the map is stretched 2:1 and its repeat is
            //     doubly obvious along one axis;
            //   - its features are cracks and aggregate, which the eye
            //     recognises by SHAPE. The tiling break in the shader is a
            //     luminance wander, so it can hide a brightness seam and can do
            //     nothing at all about a recognisable shape repeating.
            // Plaster001 is square and is, by the nature of plaster, almost
            // featureless: fine tone variation and no landmark to recognise.
            // V-MAT-01 asks for "a fine grain like cast plaster or fine
            // concrete", so this is the item's own first choice anyway.
            "Plaster001",       // 0  Ground     grey permanent ground and blocks
            "Plaster001",       // 1  Ephemeral  lavender matter
            "Plaster001",       // 2  PaleSoft   pale carvable ground
            "Metal032",         // 3  Steel      brushed steel, the sealed cage
            "Metal030",         // 4  Lead       dull lead, the sealed battery
            "Wood067",          // 5  Wood       crates and bridge decks
            // Was PavingStones092, and it was WRONG on sight: it read as a pink
            // brick wall with mortar lines on the teleporter pillar, which is
            // architecture rather than the "stone grain with faint veins"
            // V-MAT-07 asks for, and badly out of place in a pastel puzzle game.
            // Rock023 is the other rock set and gives grain and veins with no
            // masonry pattern to announce itself. Caught by looking at a frame
            // of level 6; no test could have told us.
            "Rock023",          // 6  Stone      stairs, socles, the pillar
            "Rock030",          // 7  Rock       island skirts
            "Cardboard004",     // 8  Paper      the polaroid frame
            null,               // 9  Glass      no maps, emission driven
            null,               // 10 Marker     no maps, flat paint
        };

        /// <summary>
        /// Texture repeats per world metre, per style (PRD_VISUAL 4.5). Only one
        /// family needs a value of its own: wood is tightened so a plank reads at
        /// crate size rather than spanning two metres. Everything else takes the
        /// shader's declared default of 0.5 (one repeat per two metres), which is
        /// the scale the ground was tuned at.
        /// </summary>
        private static readonly float[] MapScaleByStyle =
        {
            // RETUNED BY EYE on the level 4 and level 6 frames, because 0.5
            // across the board was wrong and only a picture could say so.
            //
            // The number is texture repeats per world metre, so 0.5 meant one
            // repeat every two metres. On a twelve metre platform that magnifies
            // Concrete034's largest features into soft metre-wide blobs, and the
            // ground read as SNOW rather than as the "fine grain like cast
            // plaster or fine concrete" V-MAT-01 asks for. Its acceptance
            // criterion is "at 2 m a platform shows visible grain; at 20 m it
            // reads flat", and grain that big is still a shape at 20 m.
            //
            // Higher numbers make the pattern finer. The tiling break in the
            // shader is what lets these go high without the repeat announcing
            // itself on a large flat plane.
            // 3.0 was the second wrong answer and the frames caught both. At
            // 0.5 the concrete's big features became metre-wide blobs and the
            // ground read as SNOW; at 3.0 the 1K map repeats about 36 times
            // across a 12 m platform and the looking-down frame showed a plain
            // GRID of repeating specks, which is worse than either. 1.4 is a
            // repeat every 71 cm: fine enough to read as cast concrete at 2 m,
            // coarse enough that the tiling break can actually hide the seam.
            1.4f,               // 0 Ground:    fine cast concrete underfoot
            2.0f,               // 1 Ephemeral: lavender, slightly coarser so the plaster reads through the glow
            1.3f,               // 2 PaleSoft:  the pale cousin of the ground
            2.4f,               // 3 Steel:     brushed metal is a fine grain or it looks like corrugation
            2.0f,               // 4 Lead:      dull and close grained
            0.7f,               // 5 Wood:      planks at crate size, and this one WAS right
            1.5f,               // 6 Stone:     veins want to be readable, so coarser than the ground
            0.8f,               // 7 Rock:      an island is a big mass and wants big features
            6.0f,               // 8 Paper:     paper grain is nearly invisible or it is not paper
            1.0f,               // 9 Glass:     samples nothing; kept sane for the day it does
            1.0f,               // 10 Marker:   samples nothing at all (markers are painted signs)
        };

        /// <summary>
        /// How far the mean preserving detail is pushed, per style. 0.9 is the
        /// house value: full grain, veins and wear, with the mean albedo of a
        /// face still exactly its palette color. Paper is the exception at 0.3,
        /// because a polaroid frame carrying concrete grade texture stops looking
        /// like paper and starts looking like a slab someone photographed.
        /// </summary>
        private static readonly float[] TextureStrengthByStyle =
        {
            // Ground and PaleSoft are softened from 0.9. They are the two the
            // player spends the whole game looking at, they cover the largest
            // unbroken areas in the game, and they are therefore the two where
            // a repeat is easiest to notice. Turning the detail down is the
            // other half of the tiling fix (the first half was swapping
            // Concrete034 for the featureless Plaster001): the grain still
            // reads at 2 m, and there is less of a pattern to lock onto at 12.
            0.6f,               // 0 Ground
            0.9f,               // 1 Ephemeral
            0.55f,              // 2 PaleSoft
            0.9f, 0.9f, 0.9f, 0.9f, 0.9f,
            0.3f,               // 8 Paper: subtle, or it stops being paper
            0.9f, 0.9f,
        };

        private static Shader _solidShader;
        private static Shader _backdropShader;

        /// <summary>
        /// False when Viewpoint/Surface could not be found and the factory fell
        /// back to URP Lit. Everything only the surface shader understands is
        /// then skipped, and the MAPS above all: URP Lit MULTIPLIES _BaseMap into
        /// the albedo instead of dividing it by its own mean, so handing it a
        /// concrete map would render the whole game at half value. Under the
        /// fallback the colors stay exactly right and the detail is simply
        /// absent, which is a game one can still play.
        /// </summary>
        private static bool _surfaceAvailable;

        /// <summary>
        /// Lit material for a palette key, cached per (key, emissive).
        /// <paramref name="emissive"/> is the Godot emission energy multiplier:
        /// the emission color is the base color scaled by it.
        ///
        /// The signature is fixed by its forty odd call sites and by the tests.
        /// Style and textures are pure functions of the key, so they need no
        /// argument of their own and add nothing to the cache key.
        /// </summary>
        public static Material Solid(string key, float emissive = 0f)
        {
            // The key carries the emission EXACTLY, not rounded. Rounding it to
            // two decimals put Solid(key, 0.001f) and Solid(key) on the same
            // cache line while they take opposite branches below, so whichever
            // was built first won and the other silently got the wrong
            // material: a plain block that glows, or a glow that does not. No
            // shipped value trips it, which is exactly why it would have
            // survived until someone added one.
            string cacheKey = "s:" + key + ":" + ExactKey(emissive);
            Material cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            Color color = Palette.Get(key);
            Material material = new Material(SolidShader());
            material.name = emissive > 0f
                ? "Solid_" + key + "_e" + Round2(emissive)
                : "Solid_" + key;
            material.SetColor(BaseColorId, color);
            material.SetFloat(SmoothnessId, SolidSmoothness);
            material.SetFloat(MetallicId, SolidMetallic);
            ApplyStyle(material, key);

            if (emissive > 0f)
            {
                // Alpha stays at 1: an HDR emission color scales rgb only, and a
                // scaled alpha would make the material look transparent to any
                // code that reads the color back.
                material.SetColor(EmissionColorId, new Color(color.r * emissive, color.g * emissive, color.b * emissive, 1f));
                // The keyword is what puts the glow on screen; the flag below
                // only tells the lightmapper how to treat this material, and is
                // the value Unity's own emissive fixup writes when the emission
                // is not baked.
                material.EnableKeyword("_EMISSION");
                material.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
            }
            else
            {
                material.SetColor(EmissionColorId, Color.black);
                material.DisableKeyword("_EMISSION");
                material.globalIlluminationFlags = MaterialGlobalIlluminationFlags.EmissiveIsBlack;
            }

            Cache[cacheKey] = material;
            return material;
        }

        /// <summary>
        /// Unlit material carrying the painted backdrop gradient, cached per
        /// (top, bottom). Both arguments are palette keys, not colors. Unlit on
        /// purpose: a painted sky must not react to the sun, or the illusion of
        /// depth behind the photo breaks.
        ///
        /// Since PRD_VISUAL 4.5 V-MAT-08 the shader is <c>Viewpoint/Backdrop</c>
        /// rather than URP Unlit. It is still unlit, for exactly the reason
        /// above, and the gradient reaching it is UNCHANGED: the same 4 x 64
        /// generated ramp in <c>_BaseMap</c> and the same white
        /// <c>_BaseColor</c>, so the ramp is never tinted twice. What the new
        /// shader adds is what turns a gradient quad into a painting on a panel
        /// (a faint paper grain, an edge vignette and a hairline lighter border
        /// where the paint stops short of the edge), and all three are authored
        /// as shader property defaults. Nothing about them is written from here:
        /// they are not functions of the palette, so putting them in the
        /// material would only add a second place to look for them, exactly as
        /// GradientSky.shader's sun and cloud knobs are left to the shader.
        ///
        /// The panel's world SIZE, which the 2 cm border needs to mean 2 cm, is
        /// NOT set here either and could not be: one material serves every
        /// backdrop sharing a palette pair while the size is a function of the
        /// photo's depth, so a material float2 would be right for one panel and
        /// silently wrong for the rest. The shader derives it from its own
        /// object-to-world matrix instead; the file says how.
        /// </summary>
        public static Material Backdrop(string top, string bottom)
        {
            string cacheKey = "b:" + top + ":" + bottom;
            Material cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            Material material = new Material(BackdropShader());
            material.name = "Backdrop_" + top + "_" + bottom;
            material.SetColor(BaseColorId, Color.white);
            material.SetTexture(BaseMapId, GradientTexture(top, bottom));

            Cache[cacheKey] = material;
            return material;
        }

        /// <summary>
        /// The style family a palette key belongs to, as the integer the shader
        /// branches on. An unlisted key is Ground: a key reaching a renderer with
        /// no entry here is a data bug, but grey permanent matter is the reading
        /// that misleads a player least, and Palette.Get has already shouted
        /// about anything genuinely unknown.
        /// </summary>
        public static int StyleFor(string key)
        {
            int style;
            if (key != null && StylesByKey.TryGetValue(key, out style))
            {
                return style;
            }

            return StyleGround;
        }

        /// <summary>
        /// The per instance seed for a block at <paramref name="worldPosition"/>,
        /// in the range [0, 1): zero is reachable, one is not. It drives the
        /// small hue and value jitter of V-MAT-03, so two adjacent grey blocks
        /// are distinguishable side by side and still obviously the same
        /// category.
        ///
        /// Deterministic and stable across runs: no Random, no Time, no frame
        /// counter, no static state. The same level rebuilt tomorrow gives every
        /// block the seed it had today, which is what keeps a screenshot
        /// comparable with the reference frames of PRD_VISUAL 6.1.
        ///
        /// The caller applies it through a MaterialPropertyBlock, which is what
        /// lets a hundred blocks keep sharing the ONE material this factory
        /// cached. That does opt each such renderer out of SRP batching, and it
        /// is affordable only because these scenes hold under a hundred
        /// renderers (PRD_VISUAL 3.3); it would not be at ten times that.
        ///
        /// Why the seed cannot simply be hashed from position INSIDE the shader:
        /// a carved fragment must INHERIT its parent's seed (V-MAT-03) and it
        /// sits at a new position, so the value has to be handed to it. Hence a
        /// function of a position the CALLER chooses, not of the fragment's own.
        /// </summary>
        public static float SeedFor(Vector3 worldPosition)
        {
            // Quantised to the centimetre before hashing. The hash needs only bit
            // identical input to be stable, which float maths already gives on
            // one machine; the rounding buys the tolerance for a position
            // recomputed a slightly different way to land on the same seed all
            // the same. A centimetre grid still leaves two blocks a metre apart a
            // hundred steps apart in the hash, and the avalanche below makes one
            // step enough.
            int x = Mathf.RoundToInt(worldPosition.x * 100f);
            int y = Mathf.RoundToInt(worldPosition.y * 100f);
            int z = Mathf.RoundToInt(worldPosition.z * 100f);

            unchecked
            {
                // FNV-1a over the three axes, then a final avalanche. FNV alone
                // mixes the LOW bits well and leaves neighbouring positions
                // correlated in the HIGH ones, which is the wrong half for a
                // value read as a fraction: without the avalanche a row of blocks
                // one metre apart comes out in a visible ramp of shades instead
                // of a scatter.
                uint h = 2166136261u;
                h = (h ^ (uint)x) * 16777619u;
                h = (h ^ (uint)y) * 16777619u;
                h = (h ^ (uint)z) * 16777619u;
                h ^= h >> 16;
                h *= 2246822507u;
                h ^= h >> 13;
                h *= 3266489909u;
                h ^= h >> 16;

                // 24 bits, which is every bit a float holds without rounding,
                // over 2^24: the result lands in [0, 1) and never reaches 1.
                return (h & 0x00FFFFFFu) / 16777216f;
            }
        }

        /// <summary>
        /// Drops every cached material so the next call rebuilds from the
        /// current palette. Used by the tests. The materials themselves are not
        /// destroyed: a renderer somewhere may still be pointing at one, and a
        /// destroyed material would turn it magenta.
        ///
        /// The gradient and map caches are deliberately NOT dropped here; the
        /// comment on each says why.
        /// </summary>
        public static void ClearCache()
        {
            Cache.Clear();
        }

        /// <summary>
        /// Tells the surface shader which family this material belongs to, and
        /// hands it the PBR set that family samples.
        ///
        /// Every map load is null tolerant. A missing file leaves the shader's
        /// own property default (white albedo, flat bump, white roughness, black
        /// metalness, mid grey height), which is a surface that still renders and
        /// still carries its palette color. A texture set is detail, never a
        /// dependency: the game must come up on a checkout that has none.
        /// </summary>
        private static void ApplyStyle(Material material, string key)
        {
            int style = StyleFor(key);
            material.SetFloat(StyleId, style);

            if (!_surfaceAvailable)
            {
                // See the field comment: URP Lit would multiply these maps into
                // the albedo instead of dividing them by their own mean.
                return;
            }

            string set = style >= 0 && style < StyleCount ? SetsByStyle[style] : null;
            if (set == null)
            {
                // Glass and Marker: smooth emission and flat paint. Their maps
                // stay at the shader defaults, and so do their tuning floats.
                return;
            }

            AssignMap(material, BaseMapId, set, "Color");
            AssignMap(material, NormalMapId, set, "Normal");
            AssignMap(material, RoughMapId, set, "Rough");
            AssignMap(material, MetalMapId, set, "Metal");
            AssignMap(material, HeightMapId, set, "Height");
            // The shader SAMPLES _AOMap and nothing was assigning it, so the
            // occlusion branch sat on its declared "white" default (occlusion 1,
            // i.e. none) forever and the AO maps that Rock023, Rock030 and
            // PavingStones092 ship were dead weight in the build. Only three of
            // the ten sets have one; AssignMap leaves the property alone when the
            // file is absent, which is exactly right here because "white" IS
            // "no occlusion data" and the shader reads it as such.
            AssignMap(material, AOMapId, set, "AO");

            material.SetFloat(MapScaleId, MapScaleByStyle[style]);
            material.SetFloat(TextureStrengthId, TextureStrengthByStyle[style]);
        }

        /// <summary>
        /// Assigns one map, or leaves the property alone when the file is not
        /// there. Leaving it ALONE rather than assigning null is the point: the
        /// shader's declared default is a meaningful value for every one of the
        /// five maps, and a set that ships no metalness file must read as
        /// metalness zero and not as an undefined sample.
        /// </summary>
        private static void AssignMap(Material material, int propertyId, string set, string map)
        {
            Texture2D texture = LoadMap(set, map);
            if (texture != null)
            {
                material.SetTexture(propertyId, texture);
            }
        }

        /// <summary>
        /// One PBR map from Resources, cached by path, misses included.
        ///
        /// Resources.Load and not AssetDatabase, and the folder is not a filing
        /// preference: AssetDatabase does not exist in a player, and Unity STRIPS
        /// from a build every asset that no other asset references. This game
        /// references nothing from a scene (one scene, one object, the world
        /// built in code), so Resources is the only path a texture survives on,
        /// and it is the same reason the level data and the font already live
        /// there. A map parked in a plain Assets/Textures/ folder imports
        /// perfectly, looks right in the editor, and is absent from the player:
        /// the exact failure the README records for the shaders.
        /// </summary>
        private static Texture2D LoadMap(string set, string map)
        {
            // No folder prefix and no extension: Resources.Load addresses the
            // path UNDER a Resources folder, and an extension makes it miss.
            string path = "Textures/" + set + "_" + map;
            Texture2D cached;
            if (Maps.TryGetValue(path, out cached))
            {
                // May be null, and that is a cached MISS rather than a cold
                // entry. Silence is correct here: not every set ships every map,
                // and the caller falls back to the shader's own default.
                return cached;
            }

            Texture2D texture = Resources.Load<Texture2D>(path);
            Maps[path] = texture;
            return texture;
        }

        /// <summary>
        /// Vertical ramp used as the backdrop albedo. Unity texture rows go
        /// bottom up, so row 0 is the BOTTOM of the panel and the ramp runs
        /// bottom (v = 0) to top (v = 1). The Godot original filled row 0 with
        /// the TOP color because its images are y down.
        /// </summary>
        private static Texture2D GradientTexture(string topKey, string bottomKey)
        {
            string gradientKey = topKey + ":" + bottomKey;
            Texture2D existing;
            if (Gradients.TryGetValue(gradientKey, out existing) && existing != null)
            {
                return existing;
            }

            Color top = Palette.Get(topKey);
            Color bottom = Palette.Get(bottomKey);

            // linear: false, so the sRGB palette values are stored as authored
            // and the sampler converts them, exactly like a Color on a material.
            Texture2D texture = new Texture2D(GradientWidth, GradientHeight, TextureFormat.RGBA32, false, false);
            texture.name = "BackdropGradient";
            texture.filterMode = FilterMode.Bilinear;
            texture.wrapMode = TextureWrapMode.Clamp;

            Color[] pixels = new Color[GradientWidth * GradientHeight];
            for (int y = 0; y < GradientHeight; y++)
            {
                Color row = Color.Lerp(bottom, top, y / (float)(GradientHeight - 1));
                for (int x = 0; x < GradientWidth; x++)
                {
                    pixels[y * GradientWidth + x] = row;
                }
            }

            texture.SetPixels(pixels);
            // Keep it readable: the unit tests sample the ramp back out.
            texture.Apply(false, false);
            Gradients[gradientKey] = texture;
            return texture;
        }

        /// <summary>
        /// The lit shader every solid uses: Viewpoint/Surface since Tier 2.
        ///
        /// It falls back to URP Lit when the surface shader cannot be found, and
        /// that fallback is not defensive noise. This project has already lost a
        /// whole build to Shader.Find returning null in a PLAYER, because Unity
        /// keeps only the shaders an ASSET references and this game creates every
        /// material at start up: each block came out with no shader at all, which
        /// draws nothing, and the symptom read as "the levels are empty".
        /// Viewpoint/Surface has to sit in Always Included Shaders for the same
        /// reason the other three do. If that is ever missed, this fallback costs
        /// the material detail and keeps the game visible and playable, while the
        /// error logged above says exactly what happened. MaterialsTests pins the
        /// shader NAME, so the fallback can never pass unnoticed in the harness.
        /// </summary>
        private static Shader SolidShader()
        {
            if (_solidShader == null)
            {
                _solidShader = FindShader("Viewpoint/Surface");
                _surfaceAvailable = _solidShader != null;
                if (_solidShader == null)
                {
                    _solidShader = FindShader("Universal Render Pipeline/Lit");
                }
            }

            return _solidShader;
        }

        /// <summary>
        /// The unlit shader the painted backdrop uses: Viewpoint/Backdrop since
        /// PRD_VISUAL 4.5 V-MAT-08.
        ///
        /// It falls back to URP Unlit the same way <see cref="SolidShader"/>
        /// falls back to URP Lit, and for the same reason: this game creates
        /// every material at start up and references no shader from an asset, so
        /// Viewpoint/Backdrop has to sit in ProjectSettings/GraphicsSettings.asset
        /// m_AlwaysIncludedShaders or Unity STRIPS it from the player and
        /// Shader.Find returns null there while working perfectly in the editor.
        /// This project has already lost a whole build to that (see the README),
        /// and the symptom read as "the levels are empty".
        ///
        /// The fallback is cheaper here than it is for the solids, and that is
        /// deliberate in the shader: Viewpoint/Backdrop keeps URP Unlit's own
        /// property names (<c>_BaseMap</c>, <c>_BaseColor</c>) and asks nothing
        /// else of the material, so a fallback material needs no second code
        /// path and loses only the grain, the vignette and the border while the
        /// gradient still reads as a painted sky. Compare
        /// <see cref="_surfaceAvailable"/>, which exists because URP Lit would
        /// MISINTERPRET what Viewpoint/Surface is handed.
        ///
        /// MaterialsTests pins the shader NAME, so a fallback can never pass
        /// unnoticed in the harness.
        /// </summary>
        private static Shader BackdropShader()
        {
            if (_backdropShader == null)
            {
                _backdropShader = FindShader("Viewpoint/Backdrop");
                if (_backdropShader == null)
                {
                    _backdropShader = FindShader("Universal Render Pipeline/Unlit");
                }
            }

            return _backdropShader;
        }

        private static Shader FindShader(string name)
        {
            Shader shader = Shader.Find(name);
            if (shader == null)
            {
                // A URP project always ships these. A miss means the pipeline
                // package is absent, or the shader was stripped from a build
                // because nothing references it: say so loudly rather than
                // silently drawing the whole game in magenta.
                Debug.LogError("Materials: shader not found: " + name);
            }

            return shader;
        }

        /// <summary>
        /// A cache key for a float that distinguishes every distinct value.
        /// "R" round-trips, so two floats compare equal if and only if their
        /// keys do, which is the whole requirement. Invariant culture because a
        /// cache key must not change with the machine's decimal separator.
        /// </summary>
        private static string ExactKey(float value)
        {
            return value.ToString("R", CultureInfo.InvariantCulture);
        }

        /// <summary>Readable two-decimal form, for material names only.</summary>
        private static string Round2(float value)
        {
            return value.ToString("F2", CultureInfo.InvariantCulture);
        }
    }
}
