using System;
using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// M4.2: the detail a renderer slot shows over its palette colour. Plain shows none (skin, eyes, hair, metal,
    /// books, leaves, the garden): its material's flat base map keeps the palette colour exactly.
    /// </summary>
    public enum Surface
    {
        Plain,
        Wood,
        Parquet,
        Plaster,
        Upholstery,
        Linen,
        Carpet,
        // ----- M6 texture pass 2 (CONTRACT_M6 2.4) -----
        Grass,
        Lacquer,
        Metal,
        Plastic,
        Foliage,
        Soil,
        // ----- M7 textures (CONTRACT_M7 1.2): the kitchen and bathroom floor tiles. -----
        Tile,
    }

    /// <summary>
    /// M4.2 textures: the grayscale detail textures (CC0, ambientCG, docs/LICENSES.md), at
    /// Assets/Resources/TextureLibrary.asset, built by Meuble.Editor.ModelCatalogBuilder. Being referenced from
    /// Resources is what ships them in the player.
    ///
    /// The technique (URP Lit only, no custom shader, no keyword):
    /// - one URP Lit material per palette colour, as before. Its base colour is the palette colour divided by
    ///   <see cref="Tuning.DetailMean"/> (in linear), and its base map is <see cref="Flat"/>, a constant texture of
    ///   that mean: a renderer without a detail shows its palette colour exactly;
    /// - a renderer slot that shows a detail gets a MaterialPropertyBlock (<see cref="PrimitiveKit.Detail(Renderer, int, Surface)"/>)
    ///   with the surface's texture as its base map and a tiling so one repeat spans the surface's tile in metres.
    ///   Every detail texture has the same mean, so the palette colour is kept on average whatever the surface;
    /// - so the same blue can be a woven sofa and a wooden counter without a second material (PRD 7.4: 24 per level).
    /// The URP Lit base map needs no shader keyword: no shader variant can be stripped from the player.
    /// </summary>
    public sealed class TextureLibrary : ScriptableObject
    {
        public const string ResourcePath = "TextureLibrary";

        [Serializable]
        public sealed class Entry
        {
            public Surface surface;
            public Texture2D texture;
            /// <summary>Mean texel of the source PNG (a linear multiplier), measured by the builder.</summary>
            public float mean;
            /// <summary>The ambientCG asset the detail was derived from.</summary>
            public string source;
            /// <summary>
            /// M7 (CONTRACT_M7 1.2): the 512 tangent space normal map derived from the same ambientCG material's
            /// NormalGL map, or null (Plastic, Foliage, Soil: not in the 1.2 list, stay bump-free).
            /// </summary>
            public Texture2D normal;
        }

        public List<Entry> entries = new List<Entry>();

        /// <summary>Every surface that shows a texture, in library order.</summary>
        public static readonly Surface[] Textured =
        {
            Surface.Wood, Surface.Parquet, Surface.Plaster, Surface.Upholstery, Surface.Linen, Surface.Carpet,
            // M6 texture pass 2 (CONTRACT_M6 2.4).
            Surface.Grass, Surface.Lacquer, Surface.Metal, Surface.Plastic, Surface.Foliage, Surface.Soil,
            // M7 textures (CONTRACT_M7 1.2): kitchen and bathroom floor tiles.
            Surface.Tile,
        };

        /// <summary>
        /// Tests only: when true, <see cref="PrimitiveKit.Detail(Renderer, int, Surface)"/> does nothing, so a level
        /// rebuilt then shows its palette colours flat (the materials do not change), for a side by side render.
        /// </summary>
        public static bool Disabled;

        public Entry Find(Surface surface)
        {
            foreach (Entry e in entries)
            {
                if (e != null && e.surface == surface)
                {
                    return e;
                }
            }
            return null;
        }

        private static TextureLibrary loaded;

        /// <summary>The library in Resources, or null when it does not exist yet.</summary>
        public static TextureLibrary Load()
        {
            if (loaded == null)
            {
                loaded = Resources.Load<TextureLibrary>(ResourcePath);
            }
            return loaded;
        }

        /// <summary>The detail texture of a surface, or null (Plain, or a library without it).</summary>
        public static Texture2D TextureOf(Surface surface)
        {
            if (surface == Surface.Plain)
            {
                return null;
            }
            TextureLibrary library = Load();
            Entry e = library != null ? library.Find(surface) : null;
            return e != null ? e.texture : null;
        }

        /// <summary>The surface a texture is the detail of; Plain for the flat map, null or any other texture.</summary>
        public static Surface SurfaceOf(Texture texture)
        {
            TextureLibrary library = Load();
            if (texture == null || library == null)
            {
                return Surface.Plain;
            }
            foreach (Entry e in library.entries)
            {
                if (e != null && e.texture == texture)
                {
                    return e.surface;
                }
            }
            return Surface.Plain;
        }

        /// <summary>The mean texel of a detail texture (the flat map: <see cref="Tuning.DetailMean"/>); NaN when unknown.</summary>
        public static float MeanOf(Texture texture)
        {
            if (texture != null && texture == flat)
            {
                return FlatValue / 255f;
            }
            TextureLibrary library = Load();
            if (texture != null && library != null)
            {
                foreach (Entry e in library.entries)
                {
                    if (e != null && e.texture == texture)
                    {
                        return e.mean;
                    }
                }
            }
            return float.NaN;
        }

        /// <summary>Metres covered by one repeat of a surface's texture (0 for Plain).</summary>
        public static float TileMetres(Surface surface)
        {
            switch (surface)
            {
                case Surface.Wood:
                    return Tuning.DetailTileWood;
                case Surface.Parquet:
                    return Tuning.DetailTileParquet;
                case Surface.Plaster:
                    return Tuning.DetailTilePlaster;
                case Surface.Upholstery:
                    return Tuning.DetailTileUpholstery;
                case Surface.Linen:
                    return Tuning.DetailTileLinen;
                case Surface.Carpet:
                    return Tuning.DetailTileCarpet;
                case Surface.Grass:
                    return Tuning.DetailTileGrass;
                case Surface.Lacquer:
                    return Tuning.DetailTileLacquer;
                case Surface.Metal:
                    return Tuning.DetailTileMetal;
                case Surface.Plastic:
                    return Tuning.DetailTilePlastic;
                case Surface.Foliage:
                    return Tuning.DetailTileFoliage;
                case Surface.Soil:
                    return Tuning.DetailTileSoil;
                case Surface.Tile:
                    return Tuning.DetailTileTile;
                default:
                    return 0f;
            }
        }

        // ----- M7 textures (CONTRACT_M7 1.2): normal maps -----

        /// <summary>The 512 tangent space normal map of a surface, or null (Plain, or a surface not in the 1.2 list).</summary>
        public static Texture2D NormalOf(Surface surface)
        {
            if (surface == Surface.Plain)
            {
                return null;
            }
            TextureLibrary library = Load();
            Entry e = library != null ? library.Find(surface) : null;
            return e != null ? e.normal : null;
        }

        /// <summary>
        /// The modest <c>_BumpScale</c> of a surface's normal map (CONTRACT_M7 1.2): one fixed value per surface, read
        /// by PrimitiveKit.Detail wherever <see cref="NormalOf"/> resolves a texture. 0 for a surface with none.
        /// </summary>
        public static float BumpScaleOf(Surface surface)
        {
            switch (surface)
            {
                case Surface.Wood:
                    return Tuning.NormalScaleWood;
                case Surface.Parquet:
                    return Tuning.NormalScaleParquet;
                case Surface.Plaster:
                    return Tuning.NormalScalePlaster;
                case Surface.Upholstery:
                    return Tuning.NormalScaleUpholstery;
                case Surface.Linen:
                    return Tuning.NormalScaleLinen;
                case Surface.Carpet:
                    return Tuning.NormalScaleCarpet;
                case Surface.Grass:
                    return Tuning.NormalScaleGrass;
                case Surface.Lacquer:
                    return Tuning.NormalScaleLacquer;
                case Surface.Metal:
                    return Tuning.NormalScaleMetal;
                case Surface.Tile:
                    return Tuning.NormalScaleTile;
                default:
                    return 0f;
            }
        }

        // ----- M6 texture pass 2 (CONTRACT_M6 2.4) -----

        /// <summary>
        /// The one smoothness and metallic every renderer of <paramref name="surface"/> uses (a fixed finish per surface,
        /// unlike the six M4.2 details whose smoothness varies by what draws them): Grass, Lacquer, Metal, Plastic,
        /// Foliage, Soil and (M7, CONTRACT_M7 1.2) Tile only. False, with both out params at 0, for any other surface
        /// (the caller picks its own).
        /// </summary>
        public static bool FinishOf(Surface surface, out float smoothness, out float metallic)
        {
            switch (surface)
            {
                case Surface.Tile:
                    smoothness = Tuning.TileSmoothness;
                    metallic = 0f;
                    return true;
                case Surface.Grass:
                    smoothness = Tuning.GrassSmoothness;
                    metallic = 0f;
                    return true;
                case Surface.Lacquer:
                    smoothness = Tuning.LacquerSmoothness;
                    metallic = 0f;
                    return true;
                case Surface.Metal:
                    smoothness = Tuning.MetalSmoothness;
                    metallic = Tuning.MetalMetallic;
                    return true;
                case Surface.Plastic:
                    smoothness = Tuning.PlasticSmoothness;
                    metallic = 0f;
                    return true;
                case Surface.Foliage:
                    smoothness = Tuning.FoliageSmoothness;
                    metallic = 0f;
                    return true;
                case Surface.Soil:
                    smoothness = Tuning.SoilSmoothness;
                    metallic = 0f;
                    return true;
                default:
                    smoothness = 0f;
                    metallic = 0f;
                    return false;
            }
        }

        // ----- The flat map and the colour compensation -----

        /// <summary>The byte of the flat map: <see cref="Tuning.DetailMean"/> is 240 / 255 exactly.</summary>
        private const byte FlatValue = 240;

        private static Texture2D flat;

        /// <summary>
        /// The base map of every URP Lit material: a 4 x 4 linear texture of <see cref="Tuning.DetailMean"/>, so a
        /// slot without a detail shows its material's base colour times the mean, the palette colour.
        /// </summary>
        public static Texture2D Flat
        {
            get
            {
                if (flat != null)
                {
                    return flat;
                }
                flat = new Texture2D(4, 4, TextureFormat.RGBA32, false, true)
                {
                    name = "Detail Flat",
                    wrapMode = TextureWrapMode.Repeat,
                    filterMode = FilterMode.Point,
                    hideFlags = HideFlags.DontUnloadUnusedAsset,
                };
                var pixels = new Color32[16];
                for (int i = 0; i < pixels.Length; i++)
                {
                    pixels[i] = new Color32(FlatValue, FlatValue, FlatValue, 255);
                }
                flat.SetPixels32(pixels);
                flat.Apply(false, true);
                return flat;
            }
        }

        /// <summary>
        /// The base colour of the material of a palette colour (sRGB in, sRGB out): the palette divided by
        /// <see cref="Tuning.DetailMean"/> in linear. Times any detail (all share that mean) it averages to the palette.
        /// </summary>
        public static Color Compensate(Color palette)
        {
            Color linear = palette.linear;
            float k = 1f / Tuning.DetailMean;
            return new Color(linear.r * k, linear.g * k, linear.b * k, palette.a).gamma;
        }
    }
}
