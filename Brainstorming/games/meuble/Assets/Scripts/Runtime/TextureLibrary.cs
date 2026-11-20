using System;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// M4.2: the detail a renderer slot shows over its palette colour. Plain shows none (skin, eyes, hair, books): its
    /// material's flat base map keeps the palette colour exactly. M7 real colours (CONTRACT_M7 5): every other surface
    /// shows its image in the image's own colours (the player furniture: the owner's red image).
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
        // ----- Wall finishes (product owner request, 2026-11-19): a room's "wallFinish" (RoomDef.WallFinishes), on the
        // room-facing side of its walls only; every other wall face, the caps and the outside faces keep Plaster. -----
        Sage,
        Limewash,
        Grasscloth,
        Wallpaper,
        // ----- M8 floor finishes (docs/m8/ROOMS_PLAN.md 4, product owner request, 2026-11-19): a room's "floorFinish"
        // (RoomDef.FloorFinishes). Marble and Herringbone are hard-floor-only looks. CarpetFinish is the soft-floor-only
        // "carpet" value: a wall-to-wall look, distinct from the plain soft floor's own Carpet above (its border and
        // field, and the rug's and doormat's own picture). -----
        Marble,
        Herringbone,
        CarpetFinish,
        // ----- M9 floors (2026-11-19, docs/m9/FLOORS_WALLS.md): the third parquet (wide light oak planks), the second
        // marble (dark green verde) and the product owner's two bathroom tiles; all hard-floor-only looks. -----
        LightOak,
        Verde,
        IvoryTile,
        TealTile,
        // ----- Tiled walls (2026-11-19, docs/m9/FLOORS_WALLS.md): the product owner's two wall images, a room's
        // "wallFinish" "whitetile" (bathrooms) and "subwaytile" (kitchens): each spans the wall once, floor to top
        // (TextureLibrary.ClampsVertically). Last, so the library's serialized surfaces keep their values. -----
        WhiteTile,
        SubwayTile,
        // ----- Printed and stone walls (2026-11-19, docs/m9/FLOORS_WALLS.md section 6): the product owner's three
        // all-over wall images, a room's "wallFinish" "travertine", "arches" and "pinstripe": each repeats both ways at
        // its metric size, like the four procedural finishes. Last, so the library's serialized surfaces keep their
        // values. -----
        Travertine,
        Arches,
        Pinstripe,
        // ----- Walls 4 (2026-11-19, docs/m9/FLOORS_WALLS.md section 7): two more all-over wall images of the product
        // owner, a room's "wallFinish" "quatrefoil" and "sageribbed". Last, so the library's serialized surfaces keep their
        // values. -----
        Quatrefoil,
        SageRibbed,
    }

    /// <summary>
    /// The environment textures (the product owner's images, docs/LICENSES.md), at Assets/Resources/TextureLibrary.asset,
    /// built by OutOfSight.Editor.ModelCatalogBuilder. Being referenced from Resources is what ships them in the player.
    ///
    /// M7 real colours (CONTRACT_M7 5, product owner decision of 2026-11-18): every textured surface shows its image in
    /// the image's own colours, tiled as a visible repeating pattern (URP Lit only, no custom shader, no keyword):
    /// - each surface has a seamless sRGB colour map (<see cref="ColourOf"/>, Assets/Art/Environment/Colour) and ONE
    ///   URP Lit material (<see cref="PrimitiveKit.SurfaceMaterial"/>): white base colour, the colour map as base map,
    ///   the surface's own finish (<see cref="ColourFinishOf"/>). <see cref="PrimitiveKit.Detail(Renderer, int, Surface)"/>
    ///   puts that material in the slot and a MaterialPropertyBlock sets the tiling so one repeat spans the surface's
    ///   tile in metres, plus the surface's normal map: one material per surface replaces one per palette colour;
    /// - the one exception is the player's furniture (PRD 7.2: found instantly in any frame): its red slots take
    ///   <see cref="PrimitiveKit.PlayerMaterial"/>, the owner's red image (<see cref="PlayerColour"/>) at its own
    ///   painted metal finish;
    /// - the inhabitants (their clothes belong to CharacterLook) keep the M4.2 rule: their palette material (its base
    ///   colour the palette over <see cref="Tuning.DetailMean"/>, its base map <see cref="Flat"/>) with the grayscale
    ///   detail of mean <see cref="Tuning.DetailMean"/> (<see cref="TextureOf"/>) in the property block.
    /// The URP Lit base map needs no shader keyword: no shader variant can be stripped from the player.
    ///
    /// M7 rug image (product owner, 2026-11-18): the rug and the doormat are a second exception, the opposite of
    /// tiling: their own picture (<see cref="RugColour"/>) shows exactly once per rug, stretched over its own size
    /// (<see cref="PrimitiveKit.RugDetail"/>), on the same shared <see cref="Surface.Carpet"/> material (<see cref="SurfaceOf"/>
    /// resolves it too); the "soft" room floor keeps the tiled Carpet detail above, untouched.
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
            /// <summary>The source image the detail was derived from (its file stem in Assets/Art/Environment).</summary>
            public string source;
            /// <summary>
            /// M7 (CONTRACT_M7 1.2): the 512 tangent space normal map derived from the same source (a gentle Sobel of
            /// the detail), or null (Plastic, Foliage, Soil: not in the 1.2 list, stay bump-free).
            /// </summary>
            public Texture2D normal;
            /// <summary>
            /// M7 real colours (CONTRACT_M7 5): the seamless 512 sRGB colour map prepared from the same source image
            /// (Assets/Art/Environment/Colour, tools/assets/derive_env_colours.py), in phase with <see cref="normal"/>.
            /// </summary>
            public Texture2D colour;
            /// <summary>The mean texel of <see cref="colour"/> in linear (measured by the builder on the source PNG).</summary>
            public Color colourMean;
        }

        public List<Entry> entries = new List<Entry>();

        /// <summary>M7 real colours: the player furniture's colour map (the owner's red painted metal image), or null.</summary>
        public Texture2D playerColour;

        /// <summary>The mean texel of <see cref="playerColour"/> in linear.</summary>
        public Color playerMean;

        /// <summary>The source image of <see cref="playerColour"/> (its file stem in Assets/Art/Environment).</summary>
        public string playerSource;

        /// <summary>
        /// M7 rug image (product owner, 2026-11-18): the rug's and the doormat's own picture (Assets/Art/Environment/
        /// rug_modern_inset_border.png), shown exactly once per rug (<see cref="PrimitiveKit.RugDetail"/>: UV 0 to 1,
        /// never tiled), never the "soft" room floor's tiled <see cref="Surface.Carpet"/> detail (<see cref="ColourOf"/>,
        /// unchanged). Resolves as <see cref="Surface.Carpet"/> too (<see cref="SurfaceOf"/>): one shared material.
        /// </summary>
        public Texture2D rugColour;

        /// <summary>The mean texel of <see cref="rugColour"/> in linear.</summary>
        public Color rugMean;

        /// <summary>The source image of <see cref="rugColour"/> (its file stem in Assets/Art/Environment).</summary>
        public string rugSource;

        // ----- Walls 4 (2026-11-19, docs/m9/FLOORS_WALLS.md section 7): one material for every wall finish. -----

        /// <summary>
        /// The colour maps of every wall finish (<see cref="WallArray.Slices"/>, in that order) as one sRGB Texture2DArray,
        /// 512 x 512 per slice, mipmapped, repeating both ways (Assets/Art/Environment/Arrays/wall_colours.png, a vertical
        /// flipbook built by ModelCatalogBuilder from the same colour maps as the entries'), or null.
        /// </summary>
        public Texture2DArray wallColours;

        /// <summary>The matching normal maps (linear RGB, OpenGL convention), one slice per finish, or null.</summary>
        public Texture2DArray wallNormals;

        /// <summary>
        /// The one opaque material every wall face, fill, cap and stub is drawn with (OutOfSight/Wall Finishes, the two
        /// arrays above): each vertex names its finish (WallArray.Tag), so a level's walls cost one material whatever the
        /// number of finishes it shows (PRD 7.4), and the two faces of a shared wall combine into one renderer even when
        /// their rooms differ. Null when the library has none: the walls then keep one URP Lit material per finish.
        /// </summary>
        public Material wallMaterial;

        /// <summary>
        /// The one see-through material of the wall fader (OutOfSight/Wall See-through): a faded wall finish from the two
        /// arrays, any other faded part (door frames, baseboards, windows, leaves) from the 2D maps of its property block.
        /// Null when the library has none: the fader then builds its URP Lit see-through material.
        /// </summary>
        public Material wallSeeThrough;

        /// <summary>The surfaces of the slices of <see cref="wallColours"/> and <see cref="wallNormals"/>, as built (a check of <see cref="WallArray.Slices"/>).</summary>
        public List<Surface> wallSlices = new List<Surface>();

        /// <summary>Every surface that shows a texture, in library order.</summary>
        public static readonly Surface[] Textured =
        {
            Surface.Wood, Surface.Parquet, Surface.Plaster, Surface.Upholstery, Surface.Linen, Surface.Carpet,
            // M6 texture pass 2 (CONTRACT_M6 2.4).
            Surface.Grass, Surface.Lacquer, Surface.Metal, Surface.Plastic, Surface.Foliage, Surface.Soil,
            // M7 textures (CONTRACT_M7 1.2): kitchen and bathroom floor tiles.
            Surface.Tile,
            // Wall finishes (2026-11-19).
            Surface.Sage, Surface.Limewash, Surface.Grasscloth, Surface.Wallpaper,
            // M8 floor finishes (2026-11-19).
            Surface.Marble, Surface.Herringbone, Surface.CarpetFinish,
            // M9 floors (2026-11-19).
            Surface.LightOak, Surface.Verde, Surface.IvoryTile, Surface.TealTile,
            // Tiled walls (2026-11-19).
            Surface.WhiteTile, Surface.SubwayTile,
            // Printed and stone walls (2026-11-19).
            Surface.Travertine, Surface.Arches, Surface.Pinstripe,
            // Walls 4 (2026-11-19).
            Surface.Quatrefoil, Surface.SageRibbed,
        };

        /// <summary>
        /// Wall finishes (product owner request, 2026-11-19): the surface the room-facing side of a room's walls shows,
        /// by its "wallFinish" (<see cref="RoomDef.WallFinishes"/>): null or empty (the default) is the cream crepi,
        /// <see cref="Surface.Plaster"/>; an unknown value too (LevelValidator rejects it).
        /// </summary>
        public static Surface WallSurface(string finish)
        {
            switch (finish)
            {
                case RoomDef.SageFinish:
                    return Surface.Sage;
                case RoomDef.LimewashFinish:
                    return Surface.Limewash;
                case RoomDef.GrassclothFinish:
                    return Surface.Grasscloth;
                case RoomDef.WallpaperFinish:
                    return Surface.Wallpaper;
                case RoomDef.WhiteTileFinish:
                    return Surface.WhiteTile;
                case RoomDef.SubwayTileFinish:
                    return Surface.SubwayTile;
                case RoomDef.TravertineFinish:
                    return Surface.Travertine;
                case RoomDef.ArchesFinish:
                    return Surface.Arches;
                case RoomDef.PinstripeFinish:
                    return Surface.Pinstripe;
                case RoomDef.QuatrefoilFinish:
                    return Surface.Quatrefoil;
                case RoomDef.SageRibbedFinish:
                    return Surface.SageRibbed;
                default:
                    return Surface.Plaster;
            }
        }

        /// <summary>
        /// Tiled walls (2026-11-19): true for a surface whose image is a whole wall, floor to top (tiles above a trim above
        /// paint), mapped once up the wall (one repeat is <see cref="Tuning.TiledWallHeight"/>, every room's wall height;
        /// a wall face's V is its height above the floor, LevelBuilder) and repeated only along it: its maps are imported
        /// Repeat on U and Clamp on V (ModelCatalogBuilder), so neither the wall top nor the floor samples the other end.
        /// </summary>
        public static bool ClampsVertically(Surface surface)
        {
            return surface == Surface.WhiteTile || surface == Surface.SubwayTile;
        }

        /// <summary>
        /// Walls 4 (docs/m9/FLOORS_WALLS.md section 7): how a tiled wall's image is laid up the wall by the wall material.
        /// <paramref name="trimHeight"/> is the bottom of the trim above the floor (metres); <paramref name="paintTop"/> and
        /// <paramref name="tilesBottom"/> are the image's V (0 at its bottom, the paint) of the top of the paint and of the
        /// bottom of the tile field, the trim between them (measured on the 512 colour maps by make_wall_finishes.band_rows:
        /// the bathroom's tile field is six whole rows, the kitchen's seven whole courses, each wrapping on its grout line);
        /// <paramref name="rowShift"/> is the image U every other repeat of the field moves by (half a subway tile, so an odd
        /// number of courses keeps the running bond). False, all 0, for any other surface.
        /// </summary>
        public static bool BandOf(Surface surface, out float trimHeight, out float paintTop, out float tilesBottom, out float rowShift)
        {
            switch (surface)
            {
                case Surface.WhiteTile:
                    trimHeight = Tuning.WhiteTileTrimHeight;
                    paintTop = 0.3672f;
                    tilesBottom = 0.3789f;
                    rowShift = 0f;
                    return true;
                case Surface.SubwayTile:
                    trimHeight = Tuning.SubwayTileTrimHeight;
                    paintTop = 0.4023f;
                    tilesBottom = 0.4160f;
                    rowShift = 0.125f;
                    return true;
                default:
                    trimHeight = 0f;
                    paintTop = 0f;
                    tilesBottom = 0f;
                    rowShift = 0f;
                    return false;
            }
        }

        /// <summary>
        /// M8 floor finishes (docs/m8/ROOMS_PLAN.md 4, product owner request, 2026-11-19): the surface a room's floor
        /// shows, by its "floorFinish" (<see cref="RoomDef.FloorFinishes"/>) and whether its "floor" is soft
        /// (<paramref name="isSoft"/>): null or empty is the default (<see cref="Surface.Parquet"/> on a hard floor,
        /// the plain border-and-field <see cref="Surface.Carpet"/> on a soft one, unchanged since M1); "tile",
        /// "marble" and "herringbone" are hard-floor-only looks, "carpet" the soft-floor-only wall-to-wall one
        /// (<see cref="Surface.CarpetFinish"/>); (M9 floors) "lightoak", "verde", "ivorytile" and "tealtile" are
        /// hard-floor-only looks too; an unknown value too (LevelValidator rejects it, falls back here).
        /// </summary>
        public static Surface FloorSurface(string finish, bool isSoft)
        {
            switch (finish)
            {
                case RoomDef.TileFinish:
                    return Surface.Tile;
                case RoomDef.MarbleFinish:
                    return Surface.Marble;
                case RoomDef.HerringboneFinish:
                    return Surface.Herringbone;
                case RoomDef.CarpetFinish:
                    return Surface.CarpetFinish;
                case RoomDef.LightOakFinish:
                    return Surface.LightOak;
                case RoomDef.VerdeFinish:
                    return Surface.Verde;
                case RoomDef.IvoryTileFinish:
                    return Surface.IvoryTile;
                case RoomDef.TealTileFinish:
                    return Surface.TealTile;
                default:
                    return isSoft ? Surface.Carpet : Surface.Parquet;
            }
        }

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

        /// <summary>
        /// The grayscale detail texture of a surface (linear, mean <see cref="Tuning.DetailMean"/>), or null (Plain, or a
        /// library without it). M7 real colours: only a slot that keeps its palette colour (an inhabitant's) shows it.
        /// </summary>
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

        /// <summary>M7 real colours (CONTRACT_M7 5): the sRGB colour map of a surface, or null (Plain, or a library without it).</summary>
        public static Texture2D ColourOf(Surface surface)
        {
            if (surface == Surface.Plain)
            {
                return null;
            }
            TextureLibrary library = Load();
            Entry e = library != null ? library.Find(surface) : null;
            return e != null ? e.colour : null;
        }

        /// <summary>M7 real colours (CONTRACT_M7 5): the player furniture's colour map (the owner's red image), or null.</summary>
        public static Texture2D PlayerColour
        {
            get
            {
                TextureLibrary library = Load();
                return library != null ? library.playerColour : null;
            }
        }

        /// <summary>M7 rug image (product owner, 2026-11-18): the rug's and the doormat's own picture, or null.</summary>
        public static Texture2D RugColour
        {
            get
            {
                TextureLibrary library = Load();
                return library != null ? library.rugColour : null;
            }
        }

        /// <summary>
        /// The surface a texture shows: the detail or the colour map of that surface; Lacquer for the player's own colour
        /// map (it replaces the lacquer the player furniture showed); Plain for the flat map, null or any other texture.
        /// </summary>
        public static Surface SurfaceOf(Texture texture)
        {
            TextureLibrary library = Load();
            if (texture == null || library == null)
            {
                return Surface.Plain;
            }
            if (texture == library.playerColour)
            {
                return Surface.Lacquer;
            }
            if (texture == library.rugColour)
            {
                return Surface.Carpet;
            }
            foreach (Entry e in library.entries)
            {
                if (e != null && (e.texture == texture || e.colour == texture))
                {
                    return e.surface;
                }
            }
            return Surface.Plain;
        }

        /// <summary>
        /// The mean texel (linear) of a base map of the library: a colour map's measured mean, the detail mean (grey) for a
        /// detail or the flat map, null for any other texture (null included).
        /// </summary>
        public static Color? MeanColourOf(Texture texture)
        {
            if (texture == null)
            {
                return null;
            }
            if (texture == flat)
            {
                return new Color(Tuning.DetailMean, Tuning.DetailMean, Tuning.DetailMean, 1f);
            }
            TextureLibrary library = Load();
            if (library == null)
            {
                return null;
            }
            if (texture == library.playerColour)
            {
                return library.playerMean;
            }
            if (texture == library.rugColour)
            {
                return library.rugMean;
            }
            foreach (Entry e in library.entries)
            {
                if (e == null)
                {
                    continue;
                }
                if (e.colour == texture)
                {
                    return e.colourMean;
                }
                if (e.texture == texture)
                {
                    return new Color(e.mean, e.mean, e.mean, 1f);
                }
            }
            return null;
        }

        /// <summary>True for a colour map of the library (a surface's or the player's), false for a detail or anything else.</summary>
        public static bool IsColourMap(Texture texture)
        {
            TextureLibrary library = Load();
            if (texture == null || library == null)
            {
                return false;
            }
            if (texture == library.playerColour)
            {
                return true;
            }
            if (texture == library.rugColour)
            {
                return true;
            }
            foreach (Entry e in library.entries)
            {
                if (e != null && e.colour == texture)
                {
                    return true;
                }
            }
            return false;
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
                case Surface.Sage:
                    return Tuning.DetailTileSage;
                case Surface.Limewash:
                    return Tuning.DetailTileLimewash;
                case Surface.Grasscloth:
                    return Tuning.DetailTileGrasscloth;
                case Surface.Wallpaper:
                    return Tuning.DetailTileWallpaper;
                case Surface.Marble:
                    return Tuning.DetailTileMarble;
                case Surface.Herringbone:
                    return Tuning.DetailTileHerringbone;
                case Surface.CarpetFinish:
                    return Tuning.DetailTileCarpetFinish;
                case Surface.LightOak:
                    return Tuning.DetailTileLightOak;
                case Surface.Verde:
                    return Tuning.DetailTileVerde;
                case Surface.IvoryTile:
                    return Tuning.DetailTileIvoryTile;
                case Surface.TealTile:
                    return Tuning.DetailTileTealTile;
                case Surface.WhiteTile:
                    return Tuning.DetailTileWhiteTile;
                case Surface.SubwayTile:
                    return Tuning.DetailTileSubwayTile;
                case Surface.Travertine:
                    return Tuning.DetailTileTravertine;
                case Surface.Arches:
                    return Tuning.DetailTileArches;
                case Surface.Pinstripe:
                    return Tuning.DetailTilePinstripe;
                case Surface.Quatrefoil:
                    return Tuning.DetailTileQuatrefoil;
                case Surface.SageRibbed:
                    return Tuning.DetailTileSageRibbed;
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
                case Surface.Sage:
                case Surface.Limewash:
                case Surface.Grasscloth:
                case Surface.Wallpaper:
                case Surface.WhiteTile:
                case Surface.SubwayTile:
                case Surface.Travertine:
                case Surface.Arches:
                case Surface.Pinstripe:
                case Surface.Quatrefoil:
                case Surface.SageRibbed:
                    return Tuning.NormalScaleWallFinish;
                case Surface.Marble:
                case Surface.Herringbone:
                case Surface.CarpetFinish:
                case Surface.LightOak:
                case Surface.Verde:
                case Surface.IvoryTile:
                case Surface.TealTile:
                    return Tuning.NormalScaleFloorFinish;
                default:
                    return 0f;
            }
        }

        // ----- M6 texture pass 2 (CONTRACT_M6 2.4) -----

        /// <summary>
        /// The one smoothness and metallic every renderer of <paramref name="surface"/> uses (a fixed finish per surface,
        /// unlike the six M4.2 details whose smoothness varies by what draws them): Grass, Lacquer, Metal, Plastic,
        /// Foliage, Soil, (M7, CONTRACT_M7 1.2) Tile and (M8 floor finishes, docs/m8/ROOMS_PLAN.md 4) Marble,
        /// Herringbone and CarpetFinish only. False, with both out params at 0, for any other surface (the caller
        /// picks its own).
        /// </summary>
        public static bool FinishOf(Surface surface, out float smoothness, out float metallic)
        {
            switch (surface)
            {
                case Surface.Tile:
                    smoothness = Tuning.TileSmoothness;
                    metallic = 0f;
                    return true;
                // M8 floor finishes (2026-11-19): polished marble is glossier than Tile, matte oak Herringbone as
                // matte as Parquet's own colour finish, the wall-to-wall carpet as matte as the plain soft floor's.
                case Surface.Marble:
                    smoothness = Tuning.MarbleSmoothness;
                    metallic = 0f;
                    return true;
                case Surface.Herringbone:
                    smoothness = Tuning.HerringboneSmoothness;
                    metallic = 0f;
                    return true;
                case Surface.CarpetFinish:
                    smoothness = Tuning.CarpetFinishSmoothness;
                    metallic = 0f;
                    return true;
                // M9 floors (2026-11-19): the light oak as matte as the other parquets, the verde as polished as the
                // white marble, the two bathroom tiles glazed as the kitchen Tile.
                case Surface.LightOak:
                    smoothness = Tuning.HerringboneSmoothness;
                    metallic = 0f;
                    return true;
                case Surface.Verde:
                    smoothness = Tuning.MarbleSmoothness;
                    metallic = 0f;
                    return true;
                case Surface.IvoryTile:
                case Surface.TealTile:
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

        // ----- M7 real colours (CONTRACT_M7 5) -----

        /// <summary>
        /// The one smoothness and metallic of a surface's colour material (<see cref="PrimitiveKit.SurfaceMaterial"/>,
        /// one material per surface): the M4.2 surfaces, whose finish used to vary with the palette material drawing
        /// them, get one fixed finish each, and Lacquer's colour material (the door leaves: the player furniture has its
        /// own <see cref="PrimitiveKit.PlayerMaterial"/>) is painted wood, not glossy; every other surface keeps
        /// <see cref="FinishOf"/>. False, both at 0, for Plain.
        /// </summary>
        public static bool ColourFinishOf(Surface surface, out float smoothness, out float metallic)
        {
            metallic = 0f;
            switch (surface)
            {
                case Surface.Wood:
                    smoothness = Tuning.ColourWoodSmoothness;
                    return true;
                case Surface.Parquet:
                    smoothness = Tuning.ColourParquetSmoothness;
                    return true;
                case Surface.Plaster:
                    smoothness = Tuning.ColourPlasterSmoothness;
                    return true;
                case Surface.Upholstery:
                    smoothness = Tuning.ColourUpholsterySmoothness;
                    return true;
                case Surface.Linen:
                    smoothness = Tuning.ColourLinenSmoothness;
                    return true;
                case Surface.Carpet:
                    smoothness = Tuning.ColourCarpetSmoothness;
                    return true;
                case Surface.Lacquer:
                    smoothness = Tuning.ColourDoorSmoothness;
                    return true;
                case Surface.Sage:
                case Surface.Limewash:
                case Surface.Grasscloth:
                case Surface.Wallpaper:
                // Printed and stone walls (2026-11-19): the two printed papers as matte as the other wallpapers.
                case Surface.Arches:
                case Surface.Pinstripe:
                // Walls 4 (2026-11-19): the quatrefoil is a printed paper too.
                case Surface.Quatrefoil:
                    smoothness = Tuning.ColourWallFinishSmoothness;
                    return true;
                // The fluted panel is painted wood in a satin paint.
                case Surface.SageRibbed:
                    smoothness = Tuning.SageRibbedSmoothness;
                    return true;
                // The travertine is honed stone: a soft sheen, between the matte papers and the glazed tiled walls.
                case Surface.Travertine:
                    smoothness = Tuning.TravertineSmoothness;
                    return true;
                // Tiled walls (2026-11-19): the glazed tiles and the paint share one material.
                case Surface.WhiteTile:
                case Surface.SubwayTile:
                    smoothness = Tuning.TiledWallSmoothness;
                    return true;
                default:
                    return FinishOf(surface, out smoothness, out metallic);
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
