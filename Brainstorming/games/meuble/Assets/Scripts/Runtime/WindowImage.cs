using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// Window picture (product owner image of 2026-11-19, Assets/Art/Environment/window_wood_blurred_garden.png, docs/LICENSES.md):
    /// every wall window shows the owner's wood framed window with its blurred garden, instead of the plain pane and the
    /// trim strips of M3 (LevelBuilder.WindowDecor, which keeps that look only when the picture is missing or the textures
    /// are off, <see cref="TextureLibrary.Disabled"/>).
    ///
    /// The picture replaces the whole window, frame and glass: the image has its own frame, mullion, transom and sill, so
    /// no 3D strip stays on top of it (no double frame). It is drawn by the window pane's own material (the cached unlit
    /// <see cref="PrimitiveKit.Emissive(Color, float, float, float)"/> one, shared with the cool fixture glows and the robot
    /// light) through a property block (<see cref="Block"/>: the picture as base map, a neutral colour): no level gains a
    /// material (PRD 7.4), the other users of that material keep their plain colour. The wall fader's see-through and
    /// lowered copies read the same block, so the window still fades and sinks with its wall line.
    ///
    /// Shipped file: Assets/Resources/WindowImage.png, made by tools/assets/make_window_image.py (the source cropped to the
    /// frame's rectangle, every texel opaque, 1024 x 1024). Windows come in several proportions (0.8 to 1.6 m wide, 0.9 to
    /// 1.2 m high), so the picture is never stretched in one piece: <see cref="Mesh"/> slices it. The frame, the mullion,
    /// the transom and the sill keep the picture's own thickness ratio (one scale per window); each of the four panes
    /// shows its own glass at one uniform zoom, cropped (never stretched) on the axis it has too much of, its two edge
    /// bands (the bright bevel highlights) kept and only its middle cut.
    /// </summary>
    public static class WindowImage
    {
        /// <summary>The picture's path under Resources.</summary>
        public const string ResourcePath = "WindowImage";

        /// <summary>The picture's frame overhangs the opening by this on the left, the right and the top (the M3 trim's half width).</summary>
        public const float FrameOverhang = 0.04f;

        /// <summary>The picture's sill reaches this far below the opening's bottom (the M3 sill strip's half height).</summary>
        public const float SillDrop = 0.052f;

        /// <summary>
        /// The picture's colour factor (sRGB, the unlit pane material's base colour through the block). Slightly above 1 so
        /// the brightest glass highlights still touch the bloom, as the plain pane did, the wood frame staying wood.
        /// </summary>
        public const float Intensity = 1.15f;

        // The layout of WindowImage.png, measured on its 1048 x 1109 px crop by tools/assets/make_window_image.py (x from the
        // left, y from the top): the frame is 61 px wide on both sides, the mullion runs from 509.5 to 538.5, the top frame
        // ends at 49.5, the transom runs from 296 to 326, the bottom band (frame and sill) starts at 1016.
        private const float ImageW = 1048f;
        private const float ImageH = 1109f;
        private static readonly float[] ColumnsPx = { 0f, 61f, 509.5f, 538.5f, 987f, 1048f };
        private static readonly float[] RowsPx = { 0f, 49.5f, 296f, 326f, 1016f, 1109f };

        /// <summary>The glass band kept whole along each cut edge of a pane (its bevel highlights), in picture pixels.</summary>
        private const float GlassEdgePx = 28f;

        private static readonly int BaseMapId = Shader.PropertyToID("_BaseMap");
        private static readonly int BaseMapStId = Shader.PropertyToID("_BaseMap_ST");
        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");

        private static readonly Dictionary<string, Mesh> Meshes = new Dictionary<string, Mesh>();
        private static Texture2D texture;
        private static bool loaded;
        private static MaterialPropertyBlock block;

        /// <summary>The picture, or null with <see cref="TextureLibrary.Disabled"/> or when it is missing (one error logged).</summary>
        public static Texture2D Texture
        {
            get
            {
                if (TextureLibrary.Disabled)
                {
                    return null;
                }
                if (!loaded || texture == null)
                {
                    bool first = !loaded;
                    loaded = true;
                    texture = Resources.Load<Texture2D>(ResourcePath);
                    if (texture == null && first)
                    {
                        Debug.LogError($"[WindowImage] no window picture at Resources/{ResourcePath}: the windows keep their plain pane and trim strips");
                    }
                }
                return texture;
            }
        }

        /// <summary>
        /// The property block of every window: the picture once over the mesh's own UV 0 to 1, a neutral colour of
        /// <see cref="Intensity"/>; null without the picture.
        /// </summary>
        public static MaterialPropertyBlock Block
        {
            get
            {
                Texture2D t = Texture;
                if (t == null)
                {
                    return null;
                }
                if (block == null)
                {
                    block = new MaterialPropertyBlock();
                }
                block.Clear();
                block.SetTexture(BaseMapId, t); // MUTATION:WINDOW_IMAGE
                block.SetVector(BaseMapStId, new Vector4(1f, 1f, 0f, 0f));
                block.SetColor(BaseColorId, Colour);
                return block;
            }
        }

        /// <summary>
        /// Levels v2 (D25, C10): the night preset's factor on the picture (sRGB): a dark blue window, the garden behind it
        /// under the moon (every channel well below 1, so a night window never feeds the bloom). Visual only.
        /// </summary>
        public static readonly Color NightColour = new Color(0.26f, 0.34f, 0.62f, 1f);

        /// <summary>The windows' base colour (sRGB): the picture's neutral factor, or <see cref="NightColour"/> under the night preset (<see cref="Main.Night"/>, read as the level builds).</summary>
        public static Color Colour => Main.Night ? NightColour : new Color(Intensity, Intensity, Intensity, 1f); // MUTATION:NIGHT_WINDOW

        /// <summary>True when <paramref name="properties"/> (a renderer's block) shows the window picture (the wall fader's copies).</summary>
        public static bool Shows(MaterialPropertyBlock properties)
        {
            return properties != null && texture != null && properties.HasTexture(BaseMapId) && properties.GetTexture(BaseMapId) == texture;
        }

        /// <summary>The picture's outer size for an opening of <paramref name="width"/> by <paramref name="height"/> (frame and sill included).</summary>
        public static Vector2 OuterSize(float width, float height)
        {
            return new Vector2(width + 2f * FrameOverhang, height + FrameOverhang + SillDrop);
        }

        /// <summary>The height of the picture's centre over the opening's centre (negative: the sill reaches lower than the top frame rises).</summary>
        public static float CentreOffset => (FrameOverhang - SillDrop) * 0.5f;

        /// <summary>
        /// The sliced window over the unit quad (-0.5 to 0.5 in x and y, facing -z like PrimitiveKit.QuadMesh), scaled by
        /// the transform to <paramref name="outer"/> (<see cref="OuterSize"/>); UV0 in the picture's own 0 to 1. Columns:
        /// frame, pane, mullion, pane, frame; rows: top frame, upper panes, transom, lower panes, sill. One scale per
        /// window, the tighter axis's (as PrimitiveKit.RugNineSliceMesh), keeps the wood's thickness ratio; the panes take
        /// the rest, split between upper and lower in the picture's proportion. Cached by size.
        /// </summary>
        public static Mesh Mesh(Vector2 outer)
        {
            System.Globalization.CultureInfo c = System.Globalization.CultureInfo.InvariantCulture;
            string key = outer.x.ToString("0.####", c) + "x" + outer.y.ToString("0.####", c);
            if (Meshes.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            float scale = Mathf.Min(outer.x / ImageW, outer.y / ImageH);
            // World widths of the columns and heights of the rows (top down), the panes taking what the wood leaves.
            float frameL = (ColumnsPx[1] - ColumnsPx[0]) * scale;
            float mullion = (ColumnsPx[3] - ColumnsPx[2]) * scale;
            float frameR = (ColumnsPx[5] - ColumnsPx[4]) * scale;
            float paneW = Mathf.Max(0.01f, (outer.x - frameL - mullion - frameR) * 0.5f);
            float top = (RowsPx[1] - RowsPx[0]) * scale;
            float transom = (RowsPx[3] - RowsPx[2]) * scale;
            float sill = (RowsPx[5] - RowsPx[4]) * scale;
            float upperPx = RowsPx[2] - RowsPx[1];
            float lowerPx = RowsPx[4] - RowsPx[3];
            float glass = Mathf.Max(0.02f, outer.y - top - transom - sill);
            float upper = glass * upperPx / (upperPx + lowerPx);
            float lower = glass - upper;
            float[] widths = { frameL, paneW, mullion, paneW, frameR };
            float[] heights = { top, upper, transom, lower, sill };

            var vertices = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            float y0 = 0.5f; // unit space, top down
            for (int row = 0; row < 5; row++)
            {
                float y1 = y0 - heights[row] / outer.y;
                float x0 = -0.5f;
                for (int col = 0; col < 5; col++)
                {
                    float x1 = x0 + widths[col] / outer.x;
                    bool pane = (row == 1 || row == 3) && (col == 1 || col == 3);
                    if (pane)
                    {
                        Pane(vertices, uvs, triangles, x0, x1, y0, y1, ColumnsPx[col], ColumnsPx[col + 1], RowsPx[row], RowsPx[row + 1],
                            widths[col], heights[row]);
                    }
                    else
                    {
                        // Wood: the picture's own piece, stretched along its length only (its thickness is at the window's scale).
                        Cell(vertices, uvs, triangles, x0, x1, y0, y1, ColumnsPx[col], ColumnsPx[col + 1], RowsPx[row], RowsPx[row + 1]);
                    }
                    x0 = x1;
                }
                y0 = y1;
            }
            var normals = new Vector3[vertices.Count];
            for (int i = 0; i < normals.Length; i++)
            {
                normals[i] = Vector3.back;
            }
            var mesh = new Mesh { name = "WindowImage" };
            mesh.SetVertices(vertices);
            mesh.normals = normals;
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            Meshes[key] = mesh;
            return mesh;
        }

        /// <summary>
        /// One pane: its glass at one uniform zoom covering the pane (the larger of its two fits), cut on the other axis.
        /// The cut keeps a <see cref="GlassEdgePx"/> band at both ends (the bevel highlights) and takes the middle of what is
        /// left, so the pane reads as the picture's glass, never stretched.
        /// </summary>
        private static void Pane(List<Vector3> v, List<Vector2> uv, List<int> t, float x0, float x1, float y0, float y1,
            float left, float right, float top, float bottom, float worldW, float worldH)
        {
            float srcW = right - left;
            float srcH = bottom - top;
            float zoom = Mathf.Max(worldW / srcW, worldH / srcH); // metres per picture pixel
            float needW = worldW / zoom;
            float needH = worldH / zoom;
            if (needH < srcH - 0.5f)
            {
                // Too much height: three bands, the top and bottom edges kept, the middle rows cut.
                float edge = Mathf.Min(GlassEdgePx, needH * 0.25f);
                float middle = needH - 2f * edge;
                float midTop = top + (srcH - middle) * 0.5f;
                float unitPerPx = (y0 - y1) / needH;
                float yA = y0 - edge * unitPerPx;
                float yB = y1 + edge * unitPerPx;
                Cell(v, uv, t, x0, x1, y0, yA, left, right, top, top + edge);
                Cell(v, uv, t, x0, x1, yA, yB, left, right, midTop, midTop + middle);
                Cell(v, uv, t, x0, x1, yB, y1, left, right, bottom - edge, bottom);
            }
            else if (needW < srcW - 0.5f)
            {
                // Too much width: three columns, the left and right edges kept, the middle columns cut.
                float edge = Mathf.Min(GlassEdgePx, needW * 0.25f);
                float middle = needW - 2f * edge;
                float midLeft = left + (srcW - middle) * 0.5f;
                float unitPerPx = (x1 - x0) / needW;
                float xA = x0 + edge * unitPerPx;
                float xB = x1 - edge * unitPerPx;
                Cell(v, uv, t, x0, xA, y0, y1, left, left + edge, top, bottom);
                Cell(v, uv, t, xA, xB, y0, y1, midLeft, midLeft + middle, top, bottom);
                Cell(v, uv, t, xB, x1, y0, y1, right - edge, right, top, bottom);
            }
            else
            {
                Cell(v, uv, t, x0, x1, y0, y1, left, right, top, bottom);
            }
        }

        /// <summary>One quad: unit rectangle (x0..x1, y0 top..y1 bottom) showing the picture's pixel rectangle (left..right, top..bottom).</summary>
        private static void Cell(List<Vector3> v, List<Vector2> uv, List<int> t, float x0, float x1, float y0, float y1,
            float left, float right, float top, float bottom)
        {
            int a = v.Count;
            float u0 = left / ImageW;
            float u1 = right / ImageW;
            float vTop = 1f - top / ImageH;
            float vBottom = 1f - bottom / ImageH;
            v.Add(new Vector3(x0, y1, 0f)); // bottom left
            v.Add(new Vector3(x1, y1, 0f)); // bottom right
            v.Add(new Vector3(x0, y0, 0f)); // top left
            v.Add(new Vector3(x1, y0, 0f)); // top right
            uv.Add(new Vector2(u0, vBottom));
            uv.Add(new Vector2(u1, vBottom));
            uv.Add(new Vector2(u0, vTop));
            uv.Add(new Vector2(u1, vTop));
            // Same winding as PrimitiveKit.RugNineSliceMesh (front face toward -z).
            t.Add(a);
            t.Add(a + 2);
            t.Add(a + 3);
            t.Add(a);
            t.Add(a + 3);
            t.Add(a + 1);
        }
    }
}
