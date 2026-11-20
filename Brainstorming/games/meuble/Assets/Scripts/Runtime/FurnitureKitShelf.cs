using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// M9 soft shapes, the bookshelf pass: the frame and the contents of a bookshelf (FurnitureKit.Bookshelf).
    /// <list type="bullet">
    /// <item>Frame (<see cref="ShelfFrameMesh"/>): one mesh of the faces that can be seen (no face against the floor, a panel or
    /// another board), its front edges shaded round through bent normals, 54 triangles whatever its size.</item>
    /// <item>Fill: every level is as full as the M5 blocks made it (the same slots: starts, widths, gaps and heights), now one
    /// packed row of books from the first slot to the last, with varied thicknesses and heights, a book here and there in
    /// another colour of the level, a leaning book at the end of levels 0 and 2, a round jar at the end of level 1 and a
    /// round vase at the start of level 3.</item>
    /// <item>A cheap rounded book (<see cref="BookMesh"/>): only its spine (one quad whose normals turn from one side to the
    /// other, so it shades as a half round and a crease parts it from the next book), its top, and its side faces where a
    /// neighbour does not hide them (a higher step, a row end, a lean): 4 to 8 triangles, never a bottom or a back.</item>
    /// <item>Budget: the books' thickness is the smallest (from <see cref="ShelfBookMin"/>) whose row, counted exactly, keeps
    /// the frame and the contents within Tuning.FurnitureTriangleBudget (400 per 1.6 m of width), so a long shelf gets as
    /// many books per metre as a short one.</item>
    /// <item>Colours (materials): every piece takes the colour of one of the M5 book slots of its level that fitted (the
    /// accent, then BookColors), so a shelf never shows a colour its M5 books did not (the level material budgets hold); a
    /// piece joins its colour's "Books" renderer. UVs in metres, as RoundedMesh and PrimitiveKit.</item>
    /// </list>
    /// </summary>
    public static partial class FurnitureKit
    {
        /// <summary>How far a leaning book tilts against its neighbour (degrees).</summary>
        private const float LeanDegrees = 14f;

        /// <summary>The thinnest book a row is planned with (metres): its thickness grows from here until the row fits the budget.</summary>
        private const float ShelfBookMin = 0.045f;

        /// <summary>How far a spine's normals turn toward its sides (degrees): the half round of its shading.</summary>
        private const float SpineDegrees = 55f;

        private static readonly Dictionary<string, Mesh> ShelfMeshes = new Dictionary<string, Mesh>();

        // Varied thicknesses and heights (factors), walked with a different start on every level, so the rows never repeat.
        private static readonly float[] BookThickness = { 1.1f, 0.85f, 1.0f, 1.25f, 0.9f, 1.05f, 0.8f, 1.15f, 0.95f };
        private static readonly float[] BookHeight = { 1.0f, 1.0f, 0.9f, 1.07f, 0.95f, 0.95f, 1.03f, 0.86f, 1.1f, 0.97f, 0.97f };

        /// <summary>One book of a planned row: where it stands, its size, the heights its side faces start from, its colour.</summary>
        private struct ShelfBook
        {
            public float X;
            public float Thickness;
            public float Height;
            public float LeftFrom;
            public float RightFrom;
            public bool Leaning;
            public Color Color;
        }

        /// <summary>One M5 book slot that fitted: its extent along x, its height (clear height share) and its colour.</summary>
        private struct ShelfSlot
        {
            public float X0;
            public float X1;
            public float Height;
            public Color Color;
        }

        /// <summary>
        /// The contents of a bookshelf of size <paramref name="s"/> (inner width <paramref name="innerW"/>, shelves of
        /// <paramref name="shelf"/> every <paramref name="pitch"/>) into <paramref name="parts"/>, within
        /// <paramref name="budget"/> triangles, as the class summary says.
        /// </summary>
        private static void ShelfContents(PartBatch parts, Vector3 s, float innerW, float shelf, float pitch, int levels, Color accent, bool visual,
            int budget)
        {
            float clear = pitch - shelf;
            float depth = s.z * 0.7f;
            var slots = new List<ShelfSlot>[levels];
            for (int level = 0; level < levels; level++)
            {
                slots[level] = BookSlots(innerW, clear, level, accent);
            }

            // The decor first: its triangles come off the books' budget.
            var decor = new List<(Mesh mesh, Vector3 at, Color color)>();
            var rows = new (float x0, float x1)[levels];
            for (int level = 0; level < levels; level++)
            {
                List<ShelfSlot> row = slots[level];
                if (row.Count == 0)
                {
                    continue;
                }
                float x0 = row[0].X0;
                float x1 = row[row.Count - 1].X1;
                float y = shelf + level * pitch;
                if (level == 1 && row.Count >= 3)
                {
                    // A round jar at the right end of the row, in the colour of the level's third slot.
                    float d = Mathf.Min(Mathf.Min(depth, clear * 0.6f), Mathf.Min(0.2f, (x1 - x0) * 0.3f));
                    Mesh jar = RoundedMesh.Slab(new Vector3(d, clear * 0.5f, d), d, 0f, 0, 0f, 0, 2, false, true);
                    decor.Add((jar, new Vector3(x1 - d * 0.5f - 0.01f, y, 0f), row[2].Color));
                    x1 -= d + 0.04f;
                }
                else if (level == 3 && row.Count >= 2)
                {
                    // A round vase at the left start of the row, in the colour of the level's first slot.
                    float d = Mathf.Min(depth, Mathf.Min(0.17f, (x1 - x0) * 0.25f));
                    decor.Add((VaseMesh(d, clear * 0.85f), new Vector3(x0 + d * 0.5f + 0.02f, y, 0f), row[0].Color));
                    x0 += d + 0.06f;
                }
                rows[level] = (x0, x1);
            }
            int left = budget;
            foreach (var (mesh, _, _) in decor)
            {
                left -= (int)ModelKit.Triangles(mesh);
            }

            // The thinnest books that fit the budget, counted exactly.
            float thickness = ShelfBookMin;
            List<ShelfBook>[] books = null;
            for (int attempt = 0; attempt < 60; attempt++)
            {
                books = new List<ShelfBook>[levels];
                int count = 0;
                for (int level = 0; level < levels; level++)
                {
                    books[level] = PlanRow(slots[level], rows[level].x0, rows[level].x1, thickness, clear, level, level == 0 || level == 2);
                    foreach (ShelfBook book in books[level])
                    {
                        count += BookTriangles(book);
                    }
                }
                if (count <= left)
                {
                    break;
                }
                thickness *= 1.06f;
            }

            for (int level = 0; level < levels; level++)
            {
                float y = shelf + level * pitch;
                for (int i = 0; i < books[level].Count; i++)
                {
                    ShelfBook book = books[level][i];
                    Mesh mesh = BookMesh(book.Thickness, book.Height, depth, book.LeftFrom, book.RightFrom);
                    Vector3 at = new Vector3(book.X, y, 0f);
                    Quaternion turn = Quaternion.identity;
                    if (book.Leaning)
                    {
                        // Tilted toward -x about its lower left edge, its top left corner against its neighbour: book.X is
                        // where its footprint starts.
                        float lean = LeanDegrees * Mathf.Deg2Rad;
                        at = new Vector3(book.X + book.Thickness * 0.5f * Mathf.Cos(lean) + book.Height * Mathf.Sin(lean),
                            y + book.Thickness * 0.5f * Mathf.Sin(lean), 0f);
                        turn = Quaternion.Euler(0f, 0f, LeanDegrees);
                    }
                    parts.Shape($"Books{level}_{i}", "Books " + ColorUtility.ToHtmlStringRGB(book.Color), mesh, at, turn, Mat(book.Color, 0.3f, visual),
                        visual, Surface.Plain);
                }
            }
            for (int i = 0; i < decor.Count; i++)
            {
                (Mesh mesh, Vector3 at, Color color) = decor[i];
                parts.Shape("Decor" + i, "Books " + ColorUtility.ToHtmlStringRGB(color), mesh, at, Quaternion.identity, Mat(color, 0.3f, visual), visual,
                    Surface.Plain);
            }
        }

        /// <summary>
        /// The M5 book slots of <paramref name="level"/> that fitted on a shelf of inner width <paramref name="innerW"/>
        /// (their widths, start and gaps, and the first book that did not fit ended the row), with their colour (the accent
        /// first, then BookColors, never red) and their height.
        /// </summary>
        private static List<ShelfSlot> BookSlots(float innerW, float clear, int level, Color accent)
        {
            float[] widths = { 0.30f, 0.22f, 0.34f, 0.26f };
            float[] heights = { 0.78f, 0.62f, 0.86f, 0.70f };
            var slots = new List<ShelfSlot>();
            float x = -innerW * 0.5f + 0.04f + 0.05f * (level % 2);
            for (int b = 0; b < 4; b++)
            {
                float w = widths[(b + level) % 4] * innerW / 1.52f * 0.95f;
                if (x + w > innerW * 0.5f - 0.02f)
                {
                    break;
                }
                slots.Add(new ShelfSlot
                {
                    X0 = x + 0.005f,
                    X1 = x + w - 0.005f,
                    // A little taller than the M5 blocks: a row of books reaches higher than a box of them.
                    Height = clear * Mathf.Min(0.92f, heights[(b + 2 * level) % 4] + 0.06f),
                    Color = b == 0 ? accent : BookColors[(b + level * 2) % BookColors.Length],
                });
                x += w + 0.03f;
            }
            return slots;
        }

        /// <summary>
        /// The books of one level's row from <paramref name="x0"/> to <paramref name="x1"/>, about
        /// <paramref name="thickness"/> thick, each in the colour of the slot it stands in (one in four in another slot's),
        /// the last one leaning when <paramref name="lean"/>.
        /// </summary>
        private static List<ShelfBook> PlanRow(List<ShelfSlot> slots, float x0, float x1, float thickness, float clear, int level, bool lean)
        {
            var books = new List<ShelfBook>();
            float width = x1 - x0;
            if (slots.Count == 0 || width < thickness * 0.5f)
            {
                return books;
            }
            float leanAngle = LeanDegrees * Mathf.Deg2Rad;
            float leanHeight = 0f;
            float leanFoot = 0f;
            if (lean)
            {
                leanHeight = slots[slots.Count - 1].Height * 0.92f;
                leanFoot = thickness * Mathf.Cos(leanAngle) + leanHeight * Mathf.Sin(leanAngle);
                lean = width - leanFoot - 0.004f >= thickness;
            }
            float upright = lean ? width - leanFoot - 0.004f : width;
            int n = Mathf.Max(1, Mathf.RoundToInt(upright / thickness));
            int start = level * 5;
            float sum = 0f;
            for (int i = 0; i < n; i++)
            {
                sum += BookThickness[(start + i) % BookThickness.Length];
            }
            float x = x0;
            for (int i = 0; i < n; i++)
            {
                float t = upright * BookThickness[(start + i) % BookThickness.Length] / sum;
                ShelfSlot slot = SlotAt(slots, x + t * 0.5f);
                float h = Mathf.Min(clear * 0.96f, slot.Height * BookHeight[(start * 2 + i) % BookHeight.Length]);
                books.Add(new ShelfBook { X = x + t * 0.5f, Thickness = t, Height = h, Color = BookColor(slots, slot, level, i) });
                x += t;
            }
            if (lean)
            {
                float h = Mathf.Min(leanHeight, books[n - 1].Height);
                books.Add(new ShelfBook
                {
                    X = x + 0.004f, Thickness = thickness, Height = h, Leaning = true, Color = BookColor(slots, slots[0], level, n + 1),
                });
            }
            // The side faces a neighbour does not hide: from its height up, the whole side at a row end or next to a lean.
            for (int i = 0; i < books.Count; i++)
            {
                ShelfBook book = books[i];
                if (!book.Leaning)
                {
                    book.LeftFrom = i > 0 ? books[i - 1].Height : 0f;
                    book.RightFrom = i + 1 < books.Count && !books[i + 1].Leaning ? books[i + 1].Height : 0f;
                }
                books[i] = book;
            }
            return books;
        }

        private static ShelfSlot SlotAt(List<ShelfSlot> slots, float x)
        {
            ShelfSlot found = slots[0];
            foreach (ShelfSlot slot in slots)
            {
                if (slot.X0 <= x)
                {
                    found = slot;
                }
            }
            return found;
        }

        /// <summary>A book's colour: its slot's, but one book in four takes another slot's of the same level.</summary>
        private static Color BookColor(List<ShelfSlot> slots, ShelfSlot slot, int level, int index)
        {
            if ((index + level) % 4 != 3 || slots.Count < 2)
            {
                return slot.Color;
            }
            Color other = slots[(index + level) % slots.Count].Color;
            return other == slot.Color ? slots[(index + level + 1) % slots.Count].Color : other;
        }

        /// <summary>The triangles of a planned book: its spine and top, and each side face its neighbours leave in view.</summary>
        private static int BookTriangles(ShelfBook book) =>
            4 + (book.LeftFrom < book.Height - 1e-4f ? 2 : 0) + (book.RightFrom < book.Height - 1e-4f ? 2 : 0);

        /// <summary>
        /// A book standing on y = 0, centred in x and z, as the class summary says: its spine (z = -depth / 2) shaded round,
        /// its top, and its left and right faces from <paramref name="leftFrom"/> and <paramref name="rightFrom"/> up (none
        /// when that is its height).
        /// </summary>
        private static Mesh BookMesh(float thickness, float height, float depth, float leftFrom, float rightFrom)
        {
            CultureInfo c = CultureInfo.InvariantCulture;
            string key = string.Format(c, "book{0:0.####}x{1:0.####}x{2:0.####}l{3:0.####}r{4:0.####}", thickness, height, depth, leftFrom, rightFrom);
            if (ShelfMeshes.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            float hx = thickness * 0.5f;
            float hz = depth * 0.5f;
            float h = height;
            float sin = Mathf.Sin(SpineDegrees * Mathf.Deg2Rad);
            float cos = Mathf.Cos(SpineDegrees * Mathf.Deg2Rad);
            var quads = new QuadMesh();
            // The spine: its normals turn from the left side to the right one, and up a little along its top edge.
            quads.Quad(new Vector3(-hx, 0f, -hz), new Vector3(hx, 0f, -hz), new Vector3(hx, h, -hz), new Vector3(-hx, h, -hz), Vector3.back,
                new Vector3(-sin, 0f, -cos), new Vector3(sin, 0f, -cos), new Vector3(sin, 0.45f, -cos), new Vector3(-sin, 0.45f, -cos));
            Vector3 topFront = new Vector3(0f, 0.85f, -0.5f);
            quads.Quad(new Vector3(-hx, h, -hz), new Vector3(hx, h, -hz), new Vector3(hx, h, hz), new Vector3(-hx, h, hz), Vector3.up,
                topFront, topFront, Vector3.up, Vector3.up);
            if (leftFrom < h - 1e-4f)
            {
                quads.Flat(new Vector3(-hx, leftFrom, -hz), new Vector3(-hx, leftFrom, hz), new Vector3(-hx, h, hz), new Vector3(-hx, h, -hz), Vector3.left);
            }
            if (rightFrom < h - 1e-4f)
            {
                quads.Flat(new Vector3(hx, rightFrom, -hz), new Vector3(hx, rightFrom, hz), new Vector3(hx, h, hz), new Vector3(hx, h, -hz), Vector3.right);
            }
            Mesh mesh = quads.Build("Book");
            ShelfMeshes[key] = mesh;
            return mesh;
        }

        /// <summary>
        /// The frame of a bookshelf of size <paramref name="s"/> as one mesh in its frame (x and z centred, y from the floor):
        /// two side panels of <paramref name="panel"/> (outer, inner, front, back and top faces: 10 triangles each), the
        /// <paramref name="levels"/> + 1 shelves of <paramref name="shelf"/> every <paramref name="pitch"/> between them (top,
        /// front and bottom, the floor one without its bottom: 28) and the back panel (front, back and top: 6). The front and
        /// back edges of the panels and the front edge of the shelves turn their normals toward their faces, so they shade
        /// round. Cached by size, kept across level rebuilds.
        /// </summary>
        private static Mesh ShelfFrameMesh(Vector3 s, float panel, float shelf, float pitch, int levels)
        {
            CultureInfo c = CultureInfo.InvariantCulture;
            string key = string.Format(c, "frame{0:0.####}x{1:0.####}x{2:0.####}p{3:0.####}s{4:0.####}l{5}", s.x, s.y, s.z, panel, shelf, levels);
            if (ShelfMeshes.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            float hx = s.x * 0.5f;
            float hz = s.z * 0.5f;
            float top = s.y;
            float inner = hx - panel;
            const float bend = 0.7071f;
            var quads = new QuadMesh();
            foreach (float side in new[] { -1f, 1f })
            {
                float xo = side * hx;
                float xi = side * inner;
                quads.Flat(new Vector3(xo, 0f, -hz), new Vector3(xo, 0f, hz), new Vector3(xo, top, hz), new Vector3(xo, top, -hz), new Vector3(side, 0f, 0f));
                quads.Flat(new Vector3(xi, 0f, -hz), new Vector3(xi, 0f, hz), new Vector3(xi, top, hz), new Vector3(xi, top, -hz), new Vector3(-side, 0f, 0f));
                foreach (float face in new[] { -1f, 1f })
                {
                    float z = face * hz;
                    var outer = new Vector3(side * bend, 0f, face * bend);
                    var toward = new Vector3(-side * bend, 0f, face * bend);
                    quads.Quad(new Vector3(xi, 0f, z), new Vector3(xo, 0f, z), new Vector3(xo, top, z), new Vector3(xi, top, z), new Vector3(0f, 0f, face),
                        toward, outer, outer, toward);
                }
                quads.Flat(new Vector3(xi, top, -hz), new Vector3(xo, top, -hz), new Vector3(xo, top, hz), new Vector3(xi, top, hz), Vector3.up);
            }
            float back = hz - 0.02f;
            for (int i = 0; i <= levels; i++)
            {
                float y0 = i * pitch;
                float y1 = y0 + shelf;
                quads.Flat(new Vector3(-inner, y1, -hz), new Vector3(inner, y1, -hz), new Vector3(inner, y1, back), new Vector3(-inner, y1, back), Vector3.up);
                var up = new Vector3(0f, bend, -bend);
                var down = new Vector3(0f, -bend, -bend);
                quads.Quad(new Vector3(-inner, y0, -hz), new Vector3(inner, y0, -hz), new Vector3(inner, y1, -hz), new Vector3(-inner, y1, -hz), Vector3.back,
                    down, down, up, up);
                if (i > 0)
                {
                    quads.Flat(new Vector3(-inner, y0, -hz), new Vector3(inner, y0, -hz), new Vector3(inner, y0, back), new Vector3(-inner, y0, back),
                        Vector3.down);
                }
            }
            quads.Flat(new Vector3(-inner, 0f, back), new Vector3(inner, 0f, back), new Vector3(inner, top, back), new Vector3(-inner, top, back), Vector3.back);
            quads.Flat(new Vector3(-inner, 0f, hz), new Vector3(inner, 0f, hz), new Vector3(inner, top, hz), new Vector3(-inner, top, hz), Vector3.forward);
            quads.Flat(new Vector3(-inner, top, back), new Vector3(inner, top, back), new Vector3(inner, top, hz), new Vector3(-inner, top, hz), Vector3.up);
            Mesh mesh = quads.Build("BookshelfFrame");
            ShelfMeshes[key] = mesh;
            return mesh;
        }

        /// <summary>A round vase of <paramref name="diameter"/>: a narrow foot, a full belly and a closed neck, 38 triangles.</summary>
        private static Mesh VaseMesh(float diameter, float height)
        {
            float[] radii = { diameter * 0.3f, diameter * 0.5f, diameter * 0.2f };
            float[] heights = { 0f, height * 0.38f, height };
            var rings = new List<RoundedMesh.Ring>();
            for (int i = 0; i < radii.Length; i++)
            {
                int a = Mathf.Max(0, i - 1);
                int b = Mathf.Min(radii.Length - 1, i + 1);
                // The profile normal: the tangent (dr, dy) turned outward.
                Vector2 n = new Vector2(heights[b] - heights[a], -(radii[b] - radii[a])).normalized;
                rings.Add(RoundedMesh.At(radii[i], radii[i], heights[i], radii[i], n.x, n.y));
            }
            return RoundedMesh.Sweep(rings, 2, false, true);
        }

        /// <summary>
        /// A mesh of quads, each with its own four vertices and normals, its UVs in metres on its plane (V along its longer
        /// side, the grain of a PrimitiveKit box face), wound to face the way it is told (Unity's clockwise front).
        /// </summary>
        private sealed class QuadMesh
        {
            private readonly List<Vector3> vertices = new List<Vector3>();
            private readonly List<Vector3> normals = new List<Vector3>();
            private readonly List<Vector2> uvs = new List<Vector2>();
            private readonly List<int> triangles = new List<int>();

            /// <summary>A flat quad a, b, c, d (in order around it), its normal <paramref name="facing"/>.</summary>
            public void Flat(Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 facing) => Quad(a, b, c, d, facing, facing, facing, facing, facing);

            /// <summary>A quad a, b, c, d (in order around it) facing <paramref name="facing"/>, with a normal per corner.</summary>
            public void Quad(Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 facing, Vector3 na, Vector3 nb, Vector3 nc, Vector3 nd)
            {
                Vector3 u = b - a;
                Vector3 v = d - a;
                if (u.sqrMagnitude > v.sqrMagnitude)
                {
                    (u, v) = (v, u);
                }
                u.Normalize();
                v.Normalize();
                int start = vertices.Count;
                Add(a, na, u, v);
                Add(b, nb, u, v);
                Add(c, nc, u, v);
                Add(d, nd, u, v);
                Triangle(start, start + 1, start + 2, facing);
                Triangle(start, start + 2, start + 3, facing);
            }

            private void Add(Vector3 p, Vector3 n, Vector3 u, Vector3 v)
            {
                vertices.Add(p);
                normals.Add(n.normalized);
                uvs.Add(new Vector2(Vector3.Dot(p, u), Vector3.Dot(p, v)));
            }

            private void Triangle(int a, int b, int c, Vector3 facing)
            {
                Vector3 face = Vector3.Cross(vertices[b] - vertices[a], vertices[c] - vertices[a]);
                if (face.sqrMagnitude < 1e-14f)
                {
                    return;
                }
                if (Vector3.Dot(face, facing) < 0f)
                {
                    (b, c) = (c, b);
                }
                triangles.Add(a);
                triangles.Add(b);
                triangles.Add(c);
            }

            public Mesh Build(string name)
            {
                var mesh = new Mesh { name = name };
                mesh.SetVertices(vertices);
                mesh.SetNormals(normals);
                mesh.SetUVs(0, uvs);
                mesh.SetTriangles(triangles, 0);
                mesh.RecalculateBounds();
                mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
                return mesh;
            }
        }
    }
}
