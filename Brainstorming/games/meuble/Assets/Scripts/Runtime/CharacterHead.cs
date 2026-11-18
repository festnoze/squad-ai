using System;
using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// The human head: the product owner's all-around head image of each gender (Art/Characters/man_head_around.png and
    /// woman_head_around.png, copied to Resources as CharacterManHeadWrap and CharacterWomanHeadWrap) wrapped once around
    /// a sculpted head, joined to the original skin at its weighted neck boundary. The image is a 2:1 longitude by height
    /// unwrap: u is the longitude (the face at u = 0.5, the ears near 0.25 and 0.75, the seam at the back of the head),
    /// v runs from the crown (top row) through the eyes (45 %) and the chin (85 %) to the neck (bottom row). Hair, skin and
    /// face all come from the image, in its own colours: the model's hair, eyebrows and eyes are cut away.
    /// </summary>
    internal static class CharacterHead
    {
        private const int Sectors = 32;
        private const float BackCentre = -0.112f;
        private const float Turn = 2f * Mathf.PI;

        // The vertical coordinates follow the artwork: eyes at 45%, nose at 60%, mouth at 70%.
        // Width, front and back are in metres in the rig's eye frame.
        private static readonly (float v, float y, float width, float front, float back)[] Profile =
        {
            (0f,    0.119f, 0f,      -0.087f, -0.087f),
            (0.08f, 0.111f, 0.043f, -0.039f, -0.131f),
            (0.16f, 0.095f, 0.068f, -0.013f, -0.156f),
            (0.24f, 0.072f, 0.083f,  0.008f, -0.176f),
            (0.34f, 0.038f, 0.088f,  0.014f, -0.185f),
            (0.42f, 0.009f, 0.088f,  0.012f, -0.188f),
            (0.47f,-0.005f, 0.087f,  0.013f, -0.187f),
            (0.53f,-0.021f, 0.086f,  0.017f, -0.185f),
            (0.59f,-0.036f, 0.082f,  0.019f, -0.181f),
            (0.64f,-0.047f, 0.076f,  0.019f, -0.176f),
            (0.70f,-0.061f, 0.070f,  0.019f, -0.170f),
            (0.78f,-0.078f, 0.062f,  0.012f, -0.168f),
            (0.86f,-0.092f, 0.054f, -0.007f, -0.165f),
            (0.94f,-0.106f, 0.046f, -0.036f, -0.160f),
        };

        private static readonly Texture2D[] Sources = new Texture2D[2];
        private static readonly Texture2D[] Wraps = new Texture2D[2];

        /// <summary>Where the rest of the skin (neck below the collar, arms, hands) samples the image: its neck colour.</summary>
        public static readonly Vector2 BodyUv = new Vector2(0.5f, 0f);

        private sealed class Edge
        {
            public bool Cut;
            public int Kept = -1;
            public int Other = -1;
        }

        public static bool HasSource(bool female) => Source(female) != null && Source(female).isReadable;

        private static Texture2D Source(bool female)
        {
            int slot = female ? 1 : 0;
            if (Sources[slot] == null)
            {
                Sources[slot] = Resources.Load<Texture2D>(female ? "CharacterWomanHeadWrap" : "CharacterManHeadWrap");
            }
            return Sources[slot];
        }

        public static bool IsWrap(Texture texture) => texture != null && (texture == Wraps[0] || texture == Wraps[1]);

        /// <summary>
        /// The head image of a gender, ready to wrap (null without its source), shared by every head of that gender. It
        /// keeps the image's own colours; only three places are evened out: the neck strip at the bottom (into the image's
        /// mean neck colour, which the rest of the skin samples at <see cref="BodyUv"/>), the crown (where every longitude
        /// meets) and the seam at the back.
        /// </summary>
        public static Texture2D Wrap(bool female)
        {
            int slot = female ? 1 : 0;
            if (Wraps[slot] != null)
            {
                return Wraps[slot];
            }
            if (!HasSource(female))
            {
                return null;
            }

            Texture2D source = Source(female);
            int width = source.width;
            int height = source.height;
            Color32[] pixels = source.GetPixels32();
            // Row 0 is the bottom of the image: the neck under the chin, skin all the way round.
            int neckRows = Mathf.Max(1, height / 40);
            Color neck = Color.black;
            for (int y = 0; y < neckRows; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    neck += ((Color)pixels[y * width + x]).linear;
                }
            }
            neck /= neckRows * width;
            for (int y = 0; y < height; y++)
            {
                float body = 1f - Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.025f, 0.14f, y / (float)(height - 1)));
                if (body <= 0f)
                {
                    break;
                }
                for (int x = 0; x < width; x++)
                {
                    int i = y * width + x;
                    pixels[i] = Color.Lerp(((Color)pixels[i]).linear, neck, body).gamma;
                }
            }

            // All longitudes collapse to one vertex at the crown.
            Color32 crown = pixels[(height - 1) * width + width / 2];
            int pole = Mathf.Max(2, height / 38);
            for (int y = 0; y < pole; y++)
            {
                float fade = 1f - Mathf.SmoothStep(0f, 1f, y / (float)pole);
                int row = (height - 1 - y) * width;
                for (int x = 0; x < width; x++)
                {
                    pixels[row + x] = Color.Lerp(pixels[row + x], crown, fade);
                }
            }

            // Equalize both ends of the image in a narrow band at the back of the head, including the crown.
            int band = Mathf.Max(2, width / 28);
            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < band; x++)
                {
                    int a = y * width + x;
                    int b = y * width + width - 1 - x;
                    Color middle = Color.Lerp(pixels[a], pixels[b], 0.5f);
                    float blend = 1f - Mathf.SmoothStep(0f, 1f, x / (float)band);
                    pixels[a] = Color.Lerp(pixels[a], middle, blend);
                    pixels[b] = Color.Lerp(pixels[b], middle, blend);
                }
            }

            var wrap = new Texture2D(width, height, TextureFormat.RGB24, true)
            {
                name = (female ? "Woman" : "Man") + " head wrap",
                wrapModeU = TextureWrapMode.Repeat,
                wrapModeV = TextureWrapMode.Clamp,
                filterMode = FilterMode.Trilinear,
            };
            wrap.SetPixels32(pixels);
            wrap.Apply(true, true);
            Wraps[slot] = wrap;
            return wrap;
        }

        public static bool CutsSkin(float a, float b, float c, bool female)
        {
            // These two families use different influence weights on the same anatomical neck transition.
            return Mathf.Min(a, Mathf.Min(b, c)) > (female ? 0.17f : 0.5f);
        }

        private static Vector3Int WeldKey(Vector3 point) => Vector3Int.RoundToInt(point * 100000f);

        public static List<int> Collar(int[] triangles, Vector3[] points, float[] weights, bool female)
        {
            var edges = new Dictionary<(int, int), Edge>();
            var welded = new Dictionary<Vector3Int, int>();
            int Index(int i)
            {
                Vector3Int key = WeldKey(points[i]);
                if (!welded.TryGetValue(key, out int index))
                {
                    index = welded.Count;
                    welded.Add(key, index);
                }
                return index;
            }
            void Record(int a, int b, bool cut)
            {
                int x = Index(a);
                int y = Index(b);
                if (x == y) { return; }
                var key = x < y ? (x, y) : (y, x);
                if (!edges.TryGetValue(key, out Edge edge))
                {
                    edge = new Edge();
                    edges.Add(key, edge);
                }
                edge.Cut |= cut;
                if (!cut)
                {
                    edge.Kept = a;
                    edge.Other = b;
                }
            }
            for (int i = 0; i < triangles.Length; i += 3)
            {
                int a = triangles[i], b = triangles[i + 1], c = triangles[i + 2];
                bool cut = CutsSkin(weights[a], weights[b], weights[c], female);
                Record(a, b, cut);
                Record(b, c, cut);
                Record(c, a, cut);
            }
            var border = new Dictionary<int, (int source, int degree)>();
            void Add(int i)
            {
                int key = Index(i);
                border.TryGetValue(key, out var node);
                border[key] = (i, node.degree + 1);
            }
            foreach (Edge edge in edges.Values)
            {
                if (edge.Cut && edge.Kept >= 0)
                {
                    Add(edge.Kept);
                    Add(edge.Other);
                }
            }
            var collar = new List<int>(border.Count);
            foreach (var item in border.Values)
            {
                if (item.degree != 2)
                {
                    return null;
                }
                collar.Add(item.source);
            }
            if (collar.Count < 6)
            {
                return null;
            }
            collar.Sort((a, b) => Around(points[a]).CompareTo(Around(points[b])));
            return collar;
        }

        private static float Around(Vector3 p) => 0.5f + Mathf.Atan2(-p.x, p.z - BackCentre) / Turn;

        public static void Append(List<int> into, List<int> collar, Vector3[] points, bool female,
            Func<Vector3, Vector3, Vector2, int> addHeadVertex, Func<int, Vector2, int> addCollarVertex)
        {
            int stride = Sectors + 1;
            var grid = new int[Profile.Length * stride];
            for (int row = 0; row < Profile.Length; row++)
            {
                float v = Profile[row].v;
                for (int col = 0; col <= Sectors; col++)
                {
                    float u = col / (float)Sectors;
                    Vector3 p = Position(u, v, female);
                    const float step = 0.002f;
                    Vector3 du = Position(u + step, v, female) - Position(u - step, v, female);
                    Vector3 dv = Position(u, Mathf.Min(0.94f, v + step), female) - Position(u, Mathf.Max(0f, v - step), female);
                    // Normalize each derivative before crossing: the unscaled cross of metre-sized
                    // samples falls below Unity's normalization epsilon.
                    Vector3 n = row == 0 ? Vector3.up : Vector3.Cross(du.normalized, dv.normalized).normalized;
                    grid[row * stride + col] = addHeadVertex(p, n, new Vector2(u, 1f - v));
                }
            }
            void Triangle(int a, int b, int c)
            {
                into.Add(a);
                into.Add(b);
                into.Add(c);
            }
            for (int row = 0; row < Profile.Length - 1; row++)
            {
                for (int col = 0; col < Sectors; col++)
                {
                    int a = row * stride + col;
                    int b = a + 1;
                    int c = a + stride;
                    if (row != 0)
                    {
                        Triangle(grid[a], grid[b], grid[c]);
                    }
                    Triangle(grid[b], grid[c + 1], grid[c]);
                }
            }

            // Sew the two rings in angular order. Copy the exact original boundary vertices and weights,
            // so the opening stays closed when the head bone turns and the neck bends.
            int ring = (Profile.Length - 1) * stride;
            var border = new int[collar.Count + 1];
            var fractions = new float[border.Length];
            int seam = collar.Count - 1;
            if (Around(points[collar[0]]) < 1f - Around(points[collar[seam]]))
            {
                seam = 0;
            }
            for (int i = 0; i <= collar.Count; i++)
            {
                int source = collar[(seam + i) % collar.Count];
                float u = i == 0 ? 0f : i == collar.Count ? 1f : Around(points[source]);
                fractions[i] = u;
                border[i] = addCollarVertex(source, new Vector2(u, 0f));
            }
            int head = 0, neck = 0;
            while (head < Sectors || neck < collar.Count)
            {
                if (head < Sectors && (neck == collar.Count || (head + 1f) / Sectors <= fractions[neck + 1]))
                {
                    Triangle(grid[ring + head], grid[ring + head + 1], border[neck]);
                    head++;
                }
                else
                {
                    Triangle(grid[ring + head], border[neck + 1], border[neck]);
                    neck++;
                }
            }
        }

        private static Vector3 Position(float u, float v, bool female)
        {
            int hi = 1;
            while (hi < Profile.Length - 1 && Profile[hi].v < v) { hi++; }
            var a = Profile[hi - 1];
            var b = Profile[hi];
            float t = Mathf.InverseLerp(a.v, b.v, v);
            float yaw = (0.5f - Mathf.Repeat(u, 1f)) * Turn;
            float side = Mathf.Sin(yaw);
            float front = Mathf.Cos(yaw);
            float width = Mathf.Lerp(a.width, b.width, t) * (female ? 0.98f : 1f);
            float y = Mathf.Lerp(a.y, b.y, t);
            float near = Mathf.Lerp(a.front, b.front, t);
            float far = Mathf.Lerp(a.back, b.back, t) - (female ? 0.005f * Mathf.Sin(Mathf.PI * v) : 0f);
            // A small sculpted nose and ear silhouette under the already painted features.
            float nose = 0.019f * Bump((u - 0.5f) / 0.031f, (v - 0.59f) / 0.064f);
            float earU = female ? 0.237f : 0.235f;
            float ear = 0.013f * Bump((Mathf.Min(u, 1f - u) - earU) / 0.054f, (v - 0.53f) / 0.123f);
            float jaw = 0.026f * (1f - front) * Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.63f, 0.94f, v));
            return new Vector3(side * (width + ear), y + jaw, Mathf.Lerp(far, near, 0.5f + 0.5f * front) + nose);
        }

        private static float Bump(float x, float y) => Mathf.Exp(-2f * (x * x + y * y));
    }
}
