using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// Walls 4 (product owner request, 2026-11-19, docs/m9/FLOORS_WALLS.md section 7): every wall finish in ONE material.
    ///
    /// Until walls 4 each wall finish was its own URP Lit material (its colour map as base map), so a level paid one
    /// material per finish it showed against the PRD 7.4 cap (24, a house 32), and the two faces of a shared wall drew as
    /// two renderers whenever their rooms differed. The finishes now live in two Texture2DArrays of the library (colour
    /// and normal, one 512 x 512 slice per finish, <see cref="Slices"/>), drawn by one material
    /// (<see cref="TextureLibrary.wallMaterial"/>, shader OutOfSight/Wall Finishes): each vertex of a wall mesh names its
    /// finish (<see cref="Tag"/>):
    /// <list type="bullet">
    /// <item>UV1 (<see cref="FinishChannel"/>): x the slice + 1 (0: no finish; <see cref="FlatFinish"/>: a flat colour, <see cref="Flat"/>), y the repeats per metre (1 / the finish's
    /// tile, TextureLibrary.TileMetres: UV0 stays in metres, so the shader tiles in metres with the hardware wrap, no
    /// frac and no seam), z the smoothness (TextureLibrary.ColourFinishOf), w the normal map strength
    /// (TextureLibrary.BumpScaleOf);</item>
    /// <item>UV2 (<see cref="BandChannel"/>), a tiled wall's band layout (TextureLibrary.BandOf), all 0 for an all-over
    /// finish: x the bottom of the trim above the floor (metres), y the image V of the top of the paint, z the image V of
    /// the bottom of the tile field, w the image U every other repeat of the field moves by. The shader lays the paint
    /// from the floor to the trim (mirrored, never stretched), the trim, then the tile field in whole rows to the top.</item>
    /// </list>
    /// The faces, fills, caps, closures, outside faces and stubs of every wall line use it (LevelBuilder), so a level's walls
    /// cost one material whatever the number of finishes, and the crepi's own material (Colour Plaster) is left to the
    /// furniture that shows plaster. The see-through wall look draws every faded part with one material too
    /// (<see cref="TextureLibrary.wallSeeThrough"/>, OutOfSight/Wall See-through), the walls from the arrays and every other
    /// part (frames, baseboards, windows, leaves) from its own 2D maps, as the URP Lit see-through material did.
    /// Mobile: Texture2DArray needs OpenGL ES 3.0 or Vulkan (shader target 3.5), the project's Android floor.
    /// </summary>
    public static class WallArray
    {
        /// <summary>
        /// The finishes of the arrays' slices, in slice order: the cream crepi, every RoomDef.WallFinishes value, then every
        /// floor look (the default parquet and soft floor, every RoomDef.FloorFinishes value). The floors share the material
        /// too (room floors, doorway thresholds, the floor under the walls, platforms and ramps): the at-cap levels that
        /// had only the crepi before walls 4 (8, 16, 22, 23) would otherwise have paid the wall material on top of their
        /// crepi, still drawn by plaster furniture, so their one to three floor materials pay for it.
        /// </summary>
        public static readonly Surface[] Slices =
        {
            Surface.Plaster, Surface.Sage, Surface.Limewash, Surface.Grasscloth, Surface.Wallpaper, Surface.WhiteTile,
            Surface.SubwayTile, Surface.Travertine, Surface.Arches, Surface.Pinstripe, Surface.Quatrefoil, Surface.SageRibbed,
            Surface.Parquet, Surface.Carpet, Surface.Tile, Surface.Marble, Surface.Herringbone, Surface.CarpetFinish,
            Surface.LightOak, Surface.Verde, Surface.IvoryTile, Surface.TealTile,
        };

        public const string ShaderName = "OutOfSight/Wall Finishes";
        public const string SeeThroughShaderName = "OutOfSight/Wall See-through";

        /// <summary>The UV channel of a vertex's finish (slice + 1, repeats per metre, smoothness, normal strength).</summary>
        public const int FinishChannel = 1;

        /// <summary>The UV channel of a vertex's band layout (trim height, paint top, tile field bottom, row shift; 0 for an all-over finish).</summary>
        public const int BandChannel = 2;

        /// <summary>
        /// The see-through material's float that picks the arrays (1, a wall part's property block) or the 2D maps of the
        /// property block (0, any other faded part).
        /// </summary>
        public const string ArrayFinishProperty = "_ArrayFinish";

        private static readonly Dictionary<(int mesh, Surface surface), Mesh> Tagged = new Dictionary<(int, Surface), Mesh>();

        /// <summary>The slice of a finish, or -1 for a surface that is no wall finish.</summary>
        public static int SliceOf(Surface surface)
        {
            return System.Array.IndexOf(Slices, surface);
        }

        /// <summary>True for a surface the arrays hold (the crepi and every wall finish).</summary>
        public static bool Holds(Surface surface) => SliceOf(surface) >= 0;

        /// <summary>
        /// The wall material, or null when the walls must keep their URP Lit materials: textures off (tests,
        /// TextureLibrary.Disabled), no library, or a library without both arrays in <see cref="Slices"/> order.
        /// </summary>
        public static Material Material
        {
            get
            {
                if (TextureLibrary.Disabled)
                {
                    return null;
                }
                TextureLibrary library = TextureLibrary.Load();
                return Ready(library) ? library.wallMaterial : null;
            }
        }

        /// <summary>The see-through material of the wall fader, or null (the fader then builds its URP Lit one).</summary>
        public static Material SeeThrough
        {
            get
            {
                TextureLibrary library = TextureLibrary.Load();
                Material m = library != null ? library.wallSeeThrough : null;
                return m != null && m.shader != null && m.shader.isSupported ? m : null;
            }
        }

        private static bool Ready(TextureLibrary library)
        {
            if (library == null || library.wallMaterial == null || library.wallColours == null || library.wallNormals == null
                || library.wallMaterial.shader == null || !library.wallMaterial.shader.isSupported || library.wallSlices == null
                || library.wallSlices.Count != Slices.Length || library.wallColours.depth != Slices.Length)
            {
                return false;
            }
            for (int i = 0; i < Slices.Length; i++)
            {
                if (library.wallSlices[i] != Slices[i])
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>True for the wall material (its slots show the finish their vertices name, never a property block's detail).</summary>
        public static bool IsWallMaterial(Material material)
        {
            if (material == null)
            {
                return false;
            }
            TextureLibrary library = TextureLibrary.Load();
            return library != null && material == library.wallMaterial;
        }

        /// <summary>A vertex's finish (UV1) for <paramref name="surface"/>: slice + 1, repeats per metre, smoothness, normal strength.</summary>
        public static Vector4 FinishOf(Surface surface)
        {
            int slice = SliceOf(surface);
            if (slice < 0)
            {
                return Vector4.zero;
            }
            TextureLibrary.ColourFinishOf(surface, out float smoothness, out float _);
            return new Vector4(slice + 1, 1f / TextureLibrary.TileMetres(surface), smoothness, TextureLibrary.BumpScaleOf(surface));
        }

        /// <summary>A vertex's band layout (UV2) for <paramref name="surface"/>: TextureLibrary.BandOf, all 0 for an all-over finish.</summary>
        public static Vector4 BandOf(Surface surface)
        {
            return TextureLibrary.BandOf(surface, out float trim, out float paintTop, out float tilesBottom, out float shift)
                ? new Vector4(trim, paintTop, tilesBottom, shift)
                : Vector4.zero;
        }

        /// <summary>The surface a vertex's finish (UV1) names, Plain when none (tests and tools).</summary>
        public static Surface SurfaceOf(Vector4 finish)
        {
            int slice = Mathf.RoundToInt(finish.x) - 1;
            return slice >= 0 && slice < Slices.Length ? Slices[slice] : Surface.Plain;
        }

        /// <summary>
        /// A copy of a cached metric mesh (UV0 in metres: PrimitiveKit's WallQuadMesh, QuadMeshSized, BoxMeshSized) whose
        /// every vertex names <paramref name="surface"/> (UV1 and UV2), same name and geometry. Cached by mesh and surface.
        /// </summary>
        public static Mesh Tag(Mesh mesh, Surface surface)
        {
            if (mesh == null)
            {
                return null;
            }
            var key = (mesh.GetInstanceID(), surface);
            if (Tagged.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh copy = Object.Instantiate(mesh);
            copy.name = mesh.name;
            int n = copy.vertexCount;
            var finish = new List<Vector4>(n);
            var band = new List<Vector4>(n);
            Vector4 f = FinishOf(surface);
            Vector4 b = BandOf(surface);
            for (int i = 0; i < n; i++)
            {
                finish.Add(f);
                band.Add(b);
            }
            copy.SetUVs(FinishChannel, finish);
            copy.SetUVs(BandChannel, band);
            copy.hideFlags = HideFlags.DontUnloadUnusedAsset;
            Tagged[key] = copy;
            return copy;
        }

        /// <summary>UV1.x of a vertex that names a flat colour instead of a finish (<see cref="Flat"/>).</summary>
        public const float FlatFinish = -1f;

        private static readonly Dictionary<(int mesh, Color32 colour, int smoothness, int metallic), Mesh> Flats =
            new Dictionary<(int, Color32, int, int), Mesh>();

        /// <summary>
        /// Fixture housings (2026-11-19, RoomLights): a copy of a metric mesh whose every vertex names a flat colour instead
        /// of a finish, for a small part merged into a wall renderer of the wall material (no material, no draw call of its
        /// own): UV1 = (<see cref="FlatFinish"/>, <paramref name="metallic"/>, <paramref name="smoothness"/>, 0), UV2 = the
        /// linear <paramref name="colour"/>. The wall shaders light it as URP Lit would a plain material of that colour and
        /// finish (no normal map). <see cref="SurfaceOf"/> reads it as Plain. Cached by mesh, colour and finish.
        /// </summary>
        public static Mesh Flat(Mesh mesh, Color colour, float smoothness, float metallic)
        {
            if (mesh == null)
            {
                return null;
            }
            var key = (mesh.GetInstanceID(), (Color32)colour, Mathf.RoundToInt(smoothness * 1000f), Mathf.RoundToInt(metallic * 1000f));
            if (Flats.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh copy = Object.Instantiate(mesh);
            copy.name = mesh.name;
            int n = copy.vertexCount;
            var finish = new List<Vector4>(n);
            var band = new List<Vector4>(n);
            Color linear = colour.linear;
            var f = new Vector4(FlatFinish, metallic, smoothness, 0f);
            var b = new Vector4(linear.r, linear.g, linear.b, 0f);
            for (int i = 0; i < n; i++)
            {
                finish.Add(f);
                band.Add(b);
            }
            copy.SetUVs(FinishChannel, finish);
            copy.SetUVs(BandChannel, band);
            copy.hideFlags = HideFlags.DontUnloadUnusedAsset;
            Flats[key] = copy;
            return copy;
        }

        /// <summary>
        /// The distinct finishes a mesh's vertices name (UV1), Plain excluded; empty for a mesh without UV1 (tests, tools).
        /// </summary>
        public static HashSet<Surface> SurfacesOf(Mesh mesh)
        {
            var surfaces = new HashSet<Surface>();
            if (mesh == null || !mesh.isReadable || !mesh.HasVertexAttribute(VertexAttribute.TexCoord1))
            {
                return surfaces;
            }
            var finish = new List<Vector4>();
            mesh.GetUVs(FinishChannel, finish);
            foreach (Vector4 f in finish)
            {
                Surface s = SurfaceOf(f);
                if (s != Surface.Plain)
                {
                    surfaces.Add(s);
                }
            }
            return surfaces;
        }
    }
}
