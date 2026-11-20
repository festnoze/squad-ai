using System;
using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// The human head: the product owner's all-around head image of each gender (Art/Characters/man_head_around.png and
    /// woman_head_around.png, copied to Resources as CharacterManHeadWrap and CharacterWomanHeadWrap) wrapped once around
    /// a sculpted head of that gender, joined to the original skin at its weighted neck boundary. The image is a 2:1
    /// unwrap around the head: u goes once around (the face at u = 0.5, the ears near 0.23 and 0.77, the seam at the back
    /// of the head), v runs from the crown (top row) through the eyes (45.7 %) and the chin (87 to 90 %) to the neck
    /// (bottom row). Hair, skin and face all come from the image, in its own colours: the model's hair, eyebrows and eyes
    /// are cut away.
    /// <para>Each row of the mesh is one image row at one height; its plan contour is a superellipse, flat across the
    /// face and round at the back. Along a row, the image is laid by arc length through landmarks measured on the image:
    /// the pupils land at a natural eye span on the flat face front, the ears on the sides, the back of the head at the
    /// seam. Below the image's jaw line the surface tucks into the neck, down to a ring on the original collar.
    /// The nose, brow, cheeks and ears are sculpted where the image paints them.</para>
    /// <para>M9 (docs/m9/heads/NOTES.md): a gender's <see cref="Sculpt"/> marks the features further (a larger head, a
    /// longer nose with its wings, a brow ridge over shallow eye sockets, cheekbones, lips, a chin, the jaw angle, ears
    /// that stand off the head toward their back rim), always at the image's own landmarks, so the painted eyes, nose,
    /// mouth and ears stay on their relief. The head is one grid in the skin's own slot: no material, no renderer.</para>
    /// </summary>
    internal static class CharacterHead
    {
        private const float Turn = 2f * Mathf.PI;
        private const int ArcSamples = 241;

        /// <summary>
        /// How strongly a gender's features are sculpted on top of its <see cref="Shape"/> (metres unless noted; the
        /// trials that chose these values are in docs/m9/heads/NOTES.md and Editor/HeadShots.cs).
        /// </summary>
        internal struct Sculpt
        {
            /// <summary>Uniform scale of the whole head about <see cref="Pivot"/> (1: the M7 size).</summary>
            public float Scale;
            /// <summary>Factor on the nose's height table, and on its width.</summary>
            public float Nose, NoseWidth;
            /// <summary>The nose wings beside the tip, the brow ridge, the eye sockets (a hollow), the cheekbones, the
            /// hollow under them, the lips, the chin, the groove over it, the jaw angle (outward) and the ears' rim.</summary>
            public float Alar, Brow, Socket, Cheekbone, CheekHollow, Lips, Chin, ChinGroove, Jaw, Ear;
            /// <summary>0 to 1: how abruptly the surface turns under the jaw line into the neck (0: the M7 smooth step).</summary>
            public float JawEdge;
            /// <summary>0 to 1: the hollow of the ear's bowl, in front of its rim.</summary>
            public float EarCup;
            /// <summary>0 to 1: how far the flat face front rounds off toward an ellipse (the outer eye corners and the
            /// mouth corners set back from the nose, as on a real face; 0: the M7 flat front).</summary>
            public float FrontRound;
        }

        /// <summary>Where the head grows from (eye frame): low in the head, over the neck, so the chin barely moves.</summary>
        private static readonly Vector3 Pivot = new Vector3(0f, -0.10f, -0.08f);

        // The M9 heads (trial v7_refined): 14 % larger, a defined but short nose, a face front rounded toward the eye
        // corners, a square jaw and firm brow for the man, a soft jaw and small chin for the woman, ears standing 14 to
        // 16 mm off the head at their back rim. Read by Editor/HeadShots.cs (by name, to try other sculpts): keep the
        // field names.
        internal static Sculpt ManSculpt = new Sculpt
        {
            Scale = 1.14f, Nose = 1.35f, NoseWidth = 1.05f, Alar = 0.003f, Brow = 0.007f, Socket = 0.004f,
            Cheekbone = 0.004f, CheekHollow = 0.0015f, Lips = 0.003f, Chin = 0.007f, ChinGroove = 0.002f, Jaw = 0.006f,
            Ear = 0.016f, JawEdge = 0.5f, EarCup = 0.3f, FrontRound = 0.6f,
        };

        internal static Sculpt WomanSculpt = new Sculpt
        {
            Scale = 1.14f, Nose = 1.35f, NoseWidth = 1.05f, Alar = 0.0025f, Brow = 0.003f, Socket = 0.0035f,
            Cheekbone = 0.003f, CheekHollow = 0f, Lips = 0.003f, Chin = 0.005f, ChinGroove = 0.002f, Jaw = 0.003f,
            Ear = 0.014f, JawEdge = 0.3f, EarCup = 0.3f, FrontRound = 0.5f,
        };

        /// <summary>One plan section of the head: its height, half width, the z of its widest point, of its front and of
        /// its back centre, and the superellipse exponents of its front and back halves (metres, eye frame).</summary>
        private struct Section
        {
            public float V, Y, A, Zc, Zf, Zb, Nf, Nb;

            public Section(float v, float y, float a, float zc, float zf, float zb, float nf, float nb)
            {
                V = v; Y = y; A = a; Zc = zc; Zf = zf; Zb = zb; Nf = nf; Nb = nb;
            }
        }

        /// <summary>
        /// One gender's head. The image landmarks are measured on its *_head_around.png (du = u - 0.5, v from the top);
        /// the geometry is in metres in the rig's eye frame (origin between the eyes, x right, y up, z forward).
        /// </summary>
        private sealed class Shape
        {
            /// <summary>Image |du| of the pupils, of the end of the flat face front and of the ear centres.</summary>
            public float PupilDu, FrontDu, EarDu;
            /// <summary>Where the pupils land on the face front (x, metres): the eye span.</summary>
            public float EyeHalfSpan;
            /// <summary>The image's jaw line (|du|, v), from the chin to the nape: below it the surface tucks into the neck.</summary>
            public (float du, float v)[] Jaw;
            /// <summary>The mesh rows (image v): denser on the features; the last one is the ring on the collar.</summary>
            public float[] Rows;
            public Section[] Sections;
            /// <summary>Per image v: how far the nose stands out of the face, and its half width (metres).</summary>
            public (float v, float height, float sigma)[] Nose;
            /// <summary>The nose wings: their centre's x (metres) and image v.</summary>
            public float AlarX, AlarV;
            public float BrowV, BrowSigma;
            public float CheekHeight, CheekDu, CheekV, CheekSigmaX, CheekSigmaV;
            /// <summary>The mouth's image v, the chin's half width (metres) and the jaw angle's image v.</summary>
            public float MouthV, ChinSigmaX, JawAngleV;
            /// <summary>The painted ear: its centre's image v and its half extent in |du| and in v.</summary>
            public float EarV, EarHalfDu, EarHalfV;
        }

        // The man: a larger head, a square brow and jaw, a strong nose. Landmarks: pupils at u 0.434 and 0.565, v 0.457;
        // nose tip v 0.60; mouth v 0.69; chin v 0.896; ears at u 0.234 and 0.767, v 0.40 to 0.65; nape hairline v 0.72.
        private static readonly Shape Man = new Shape
        {
            PupilDu = 0.0655f, FrontDu = 0.11f, EarDu = 0.266f, EyeHalfSpan = 0.032f,
            Jaw = new[] { (0f, 0.896f), (0.134f, 0.857f), (0.207f, 0.789f), (0.27f, 0.745f), (0.34f, 0.71f), (0.5f, 0.70f) },
            Rows = new[] { 0f, 0.05f, 0.11f, 0.17f, 0.225f, 0.30f, 0.37f, 0.415f, 0.457f, 0.51f, 0.555f, 0.585f, 0.605f, 0.625f, 0.645f, 0.69f, 0.76f, 0.83f, 0.896f, 0.925f, 0.96f },
            Sections = new[]
            {
                new Section(0f, 0.122f, 0f, -0.085f, -0.085f, -0.085f, 2f, 2f),
                new Section(0.06f, 0.118f, 0.042f, -0.085f, -0.040f, -0.130f, 2.2f, 2f),
                new Section(0.12f, 0.107f, 0.064f, -0.083f, -0.012f, -0.158f, 2.6f, 2.1f),
                new Section(0.18f, 0.090f, 0.078f, -0.081f, 0.004f, -0.174f, 3f, 2.2f),
                new Section(0.225f, 0.073f, 0.084f, -0.079f, 0.010f, -0.181f, 3.3f, 2.2f),
                new Section(0.30f, 0.050f, 0.088f, -0.078f, 0.014f, -0.186f, 3.6f, 2.3f),
                new Section(0.37f, 0.022f, 0.089f, -0.078f, 0.016f, -0.188f, 3.6f, 2.3f),
                new Section(0.457f, 0f, 0.088f, -0.078f, 0.012f, -0.188f, 3.6f, 2.3f),
                new Section(0.53f, -0.018f, 0.088f, -0.078f, 0.015f, -0.185f, 3.5f, 2.3f),
                new Section(0.60f, -0.036f, 0.086f, -0.078f, 0.017f, -0.180f, 3.3f, 2.3f),
                new Section(0.69f, -0.058f, 0.081f, -0.079f, 0.020f, -0.172f, 3.1f, 2.3f),
                new Section(0.76f, -0.076f, 0.075f, -0.081f, 0.019f, -0.167f, 3f, 2.3f),
                new Section(0.83f, -0.093f, 0.064f, -0.085f, 0.017f, -0.163f, 2.9f, 2.3f),
                new Section(0.896f, -0.108f, 0.050f, -0.090f, 0.011f, -0.160f, 2.9f, 2.3f),
                new Section(1f, -0.112f, 0.045f, -0.098f, -0.040f, -0.158f, 2.6f, 2.3f),
            },
            // A straight bridge and a round tip (a plateau over two rows), undercut to the lip.
            Nose = new[] { (0.42f, 0f, 0.006f), (0.457f, 0.0035f, 0.0062f), (0.49f, 0.006f, 0.0066f), (0.525f, 0.009f, 0.0072f), (0.555f, 0.0125f, 0.008f),
                (0.585f, 0.0175f, 0.010f), (0.60f, 0.0195f, 0.012f), (0.615f, 0.019f, 0.013f), (0.628f, 0.013f, 0.014f),
                (0.642f, 0.004f, 0.015f), (0.655f, 0f, 0.015f) },
            AlarX = 0.015f, AlarV = 0.615f,
            BrowV = 0.37f, BrowSigma = 0.035f,
            CheekHeight = 0.002f, CheekDu = 0.11f, CheekV = 0.58f, CheekSigmaX = 0.02f, CheekSigmaV = 0.06f,
            MouthV = 0.69f, ChinSigmaX = 0.021f, JawAngleV = 0.765f,
            EarV = 0.53f, EarHalfDu = 0.036f, EarHalfV = 0.125f,
        };

        // The woman: a smaller head, round cheeks, a soft narrow chin, a small nose. Landmarks: pupils at u 0.428 and
        // 0.569, v 0.457; nose tip v 0.60; mouth v 0.682; chin v 0.868; ears at u 0.231 and 0.769, v 0.40 to 0.65.
        private static readonly Shape Woman = new Shape
        {
            PupilDu = 0.0705f, FrontDu = 0.115f, EarDu = 0.269f, EyeHalfSpan = 0.030f,
            Jaw = new[] { (0f, 0.868f), (0.13f, 0.835f), (0.2f, 0.775f), (0.27f, 0.735f), (0.34f, 0.705f), (0.5f, 0.70f) },
            Rows = new[] { 0f, 0.05f, 0.11f, 0.17f, 0.235f, 0.30f, 0.36f, 0.41f, 0.457f, 0.51f, 0.555f, 0.585f, 0.603f, 0.621f, 0.64f, 0.682f, 0.745f, 0.81f, 0.868f, 0.9f, 0.94f },
            Sections = new[]
            {
                new Section(0f, 0.115f, 0f, -0.086f, -0.086f, -0.086f, 2f, 2f),
                new Section(0.06f, 0.111f, 0.040f, -0.086f, -0.044f, -0.128f, 2.2f, 2f),
                new Section(0.12f, 0.101f, 0.060f, -0.084f, -0.016f, -0.155f, 2.5f, 2.1f),
                new Section(0.18f, 0.085f, 0.074f, -0.082f, 0f, -0.171f, 2.9f, 2.2f),
                new Section(0.24f, 0.066f, 0.081f, -0.080f, 0.008f, -0.180f, 3.1f, 2.2f),
                new Section(0.33f, 0.036f, 0.084f, -0.079f, 0.012f, -0.186f, 3.2f, 2.3f),
                new Section(0.39f, 0.016f, 0.084f, -0.079f, 0.013f, -0.187f, 3.2f, 2.3f),
                new Section(0.457f, 0f, 0.084f, -0.079f, 0.010f, -0.187f, 3.2f, 2.3f),
                new Section(0.53f, -0.017f, 0.085f, -0.079f, 0.013f, -0.184f, 3f, 2.3f),
                new Section(0.60f, -0.033f, 0.083f, -0.079f, 0.015f, -0.178f, 2.8f, 2.3f),
                new Section(0.682f, -0.052f, 0.077f, -0.080f, 0.017f, -0.172f, 2.5f, 2.3f),
                new Section(0.745f, -0.067f, 0.070f, -0.082f, 0.016f, -0.169f, 2.3f, 2.3f),
                new Section(0.81f, -0.083f, 0.059f, -0.086f, 0.013f, -0.167f, 2.2f, 2.3f),
                new Section(0.868f, -0.097f, 0.045f, -0.091f, 0.006f, -0.165f, 2.1f, 2.3f),
                new Section(1f, -0.108f, 0.042f, -0.100f, -0.045f, -0.165f, 2.2f, 2.3f),
            },
            Nose = new[] { (0.43f, 0f, 0.005f), (0.457f, 0.0025f, 0.0052f), (0.49f, 0.004f, 0.0056f), (0.525f, 0.006f, 0.006f), (0.555f, 0.0088f, 0.007f),
                (0.585f, 0.0125f, 0.0085f), (0.60f, 0.0145f, 0.010f), (0.612f, 0.0135f, 0.011f), (0.625f, 0.009f, 0.012f),
                (0.638f, 0.003f, 0.013f), (0.65f, 0f, 0.013f) },
            AlarX = 0.014f, AlarV = 0.612f,
            BrowV = 0.355f, BrowSigma = 0.035f,
            CheekHeight = 0.006f, CheekDu = 0.11f, CheekV = 0.58f, CheekSigmaX = 0.022f, CheekSigmaV = 0.065f,
            MouthV = 0.682f, ChinSigmaX = 0.016f, JawAngleV = 0.755f,
            EarV = 0.527f, EarHalfDu = 0.037f, EarHalfV = 0.125f,
        };

        /// <summary>The mesh columns (image u, 0 to 1): dense over the face, sparser over the sides and the back.</summary>
        private static readonly float[] Columns = BuildColumns();

        // The half contour of the row being laid (x >= 0, from the front centre to the back centre) and its arc length.
        private static readonly float[] ArcX = new float[ArcSamples];
        private static readonly float[] ArcZ = new float[ArcSamples];
        private static readonly float[] ArcS = new float[ArcSamples];

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
            return collar;
        }

        private static Vector3 CentreOf(List<int> collar, Vector3[] points)
        {
            Vector3 centre = Vector3.zero;
            foreach (int i in collar)
            {
                centre += points[i];
            }
            return centre / collar.Count;
        }

        /// <summary>The angle of a point around the neck's axis, as a fraction of a turn in [0, 1): 0.5 in front, 0 at the
        /// back. A point right at the back may land just under 1 or at 0 depending on rounding: sort with one centre only.</summary>
        private static float Around(Vector3 p, Vector3 centre) => Mathf.Repeat(0.5f + Mathf.Atan2(centre.x - p.x, p.z - centre.z) / Turn, 1f);

        /// <summary>The collar ring, sorted around the neck by its own angles: where the head's lowest ring tucks in.</summary>
        private sealed class Neck
        {
            public readonly Vector3 Centre;
            /// <summary>The collar's vertex indices in increasing <see cref="Around(Vector3)"/>.</summary>
            public readonly List<int> Order;
            private readonly float[] angles;
            private readonly Vector3[] ring;

            public Neck(List<int> collar, Vector3[] points)
            {
                Vector3 centre = CentreOf(collar, points);
                Centre = centre;
                Order = new List<int>(collar);
                Order.Sort((a, b) => CharacterHead.Around(points[a], centre).CompareTo(CharacterHead.Around(points[b], centre)));
                angles = new float[Order.Count];
                ring = new Vector3[Order.Count];
                for (int i = 0; i < Order.Count; i++)
                {
                    ring[i] = points[Order[i]];
                    angles[i] = CharacterHead.Around(ring[i], Centre);
                }
            }

            public float Around(Vector3 p) => CharacterHead.Around(p, Centre);

            /// <summary>The collar point at that angle (linear between its vertices, across the back too).</summary>
            public Vector3 At(float angle)
            {
                angle = Mathf.Repeat(angle, 1f);
                int n = ring.Length;
                int next = 0;
                while (next < n && angles[next] < angle) { next++; }
                int prev = next - 1;
                float from = prev < 0 ? angles[n - 1] - 1f : angles[prev];
                float to = next >= n ? angles[0] + 1f : angles[next];
                Vector3 a = ring[(prev + n) % n];
                Vector3 b = ring[next % n];
                return Vector3.Lerp(a, b, Mathf.InverseLerp(from, to, angle));
            }
        }

        /// <summary>
        /// Adds the head grid (one vertex per column and row, its image coordinates as UVs) and the strip that sews its
        /// lowest ring to the collar. <paramref name="addHeadVertex"/> receives the position and normal in the eye frame,
        /// the UV and how far the vertex is tucked into the neck (0 on the head, 1 on the ring on the collar).
        /// </summary>
        public static void Append(List<int> into, List<int> collar, Vector3[] points, bool female,
            Func<Vector3, Vector3, Vector2, float, int> addHeadVertex, Func<int, Vector2, int> addCollarVertex)
        {
            Shape shape = female ? Woman : Man;
            Sculpt sculpt = female ? WomanSculpt : ManSculpt;
            var neck = new Neck(collar, points);
            collar = neck.Order;
            int rows = shape.Rows.Length;
            int stride = Columns.Length;
            var position = new Vector3[rows * stride];
            var tucks = new float[position.Length];
            for (int row = 0; row < rows; row++)
            {
                for (int col = 0; col < stride; col++)
                {
                    position[row * stride + col] = Position(shape, sculpt, Columns[col], shape.Rows[row], neck, out tucks[row * stride + col]);
                }
            }
            var grid = new int[position.Length];
            for (int row = 0; row < rows; row++)
            {
                for (int col = 0; col < stride; col++)
                {
                    // Columns 0 and stride - 1 are the same seam at the back of the head.
                    int before = row * stride + (col == 0 ? stride - 2 : col - 1);
                    int after = row * stride + (col == stride - 1 ? 1 : col + 1);
                    Vector3 du = position[after] - position[before];
                    Vector3 dv = position[Mathf.Min(row + 1, rows - 1) * stride + col] - position[Mathf.Max(row - 1, 0) * stride + col];
                    // At the nape the lowest rows can all lie on the collar: take the column's slope further up.
                    for (int up = row - 2; dv.sqrMagnitude < 1e-14f && up >= 0; up--)
                    {
                        dv = position[row * stride + col] - position[up * stride + col];
                    }
                    int i = row * stride + col;
                    // Normalize each derivative before crossing (Vector3.normalized gives zero under 1e-5, and tucked
                    // neighbours on the collar can be closer than that); where they still give no plane, face out of
                    // the neck's axis.
                    Vector3 n = row == 0 ? Vector3.up : Unit(Vector3.Cross(Unit(du), Unit(dv)));
                    if (n.sqrMagnitude < 0.5f)
                    {
                        Vector3 outward = position[i] - neck.Centre;
                        outward.y = 0f;
                        n = outward.sqrMagnitude > 1e-12f ? outward.normalized : Vector3.up;
                    }
                    grid[i] = addHeadVertex(position[i], n, new Vector2(Columns[col], 1f - shape.Rows[row]), tucks[i]);
                }
            }
            void Triangle(int a, int b, int c)
            {
                into.Add(a);
                into.Add(b);
                into.Add(c);
            }
            for (int row = 0; row < rows - 1; row++)
            {
                for (int col = 0; col < stride - 1; col++)
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
            int ring = (rows - 1) * stride;
            var around = new float[stride];
            for (int col = 0; col < stride; col++)
            {
                around[col] = col == 0 ? 0f : col == stride - 1 ? 1f : neck.Around(position[ring + col]);
            }
            var border = new int[collar.Count + 1];
            var fractions = new float[border.Length];
            int seam = collar.Count - 1;
            if (neck.Around(points[collar[0]]) < 1f - neck.Around(points[collar[seam]]))
            {
                seam = 0;
            }
            for (int i = 0; i <= collar.Count; i++)
            {
                int source = collar[(seam + i) % collar.Count];
                float u = i == 0 ? 0f : i == collar.Count ? 1f : neck.Around(points[source]);
                fractions[i] = u;
                border[i] = addCollarVertex(source, new Vector2(u, 0f));
            }
            int head = 0, low = 0, last = stride - 1;
            while (head < last || low < collar.Count)
            {
                if (head < last && (low == collar.Count || around[head + 1] <= fractions[low + 1]))
                {
                    Triangle(grid[ring + head], grid[ring + head + 1], border[low]);
                    head++;
                }
                else
                {
                    Triangle(grid[ring + head], border[low + 1], border[low]);
                    low++;
                }
            }
        }

        private static float[] BuildColumns()
        {
            const int face = 18;
            const float faceEdge = 0.12f;
            // The side columns' |du| beyond the face (from the face edge to the seam): dense over the ears (|du| 0.23 to
            // 0.30), sparser over the hair behind them. (A local: Columns is initialized before any field below it.)
            float[] side = { 0.155f, 0.195f, 0.228f, 0.248f, 0.268f, 0.288f, 0.31f, 0.35f, 0.40f, 0.45f, 0.5f };
            var u = new List<float>();
            for (int i = side.Length - 1; i >= 0; i--)
            {
                u.Add(0.5f - side[i]);
            }
            for (int i = 0; i <= face; i++)
            {
                u.Add(0.5f + Mathf.Lerp(-faceEdge, faceEdge, i / (float)face));
            }
            for (int i = 0; i < side.Length; i++)
            {
                u.Add(0.5f + side[i]);
            }
            return u.ToArray();
        }

        /// <summary>The surface at image (u, v), tucked into the neck below the image's jaw line.</summary>
        private static Vector3 Position(Shape shape, Sculpt sculpt, float u, float v, Neck neck, out float tuck)
        {
            Vector3 p = Surface(shape, sculpt, u, v);
            float jaw = Lookup(shape.Jaw, Mathf.Abs(u - 0.5f));
            tuck = 0f;
            if (v > jaw)
            {
                // On the collar itself: the strip that sews the lowest ring to it then has no visible width.
                Vector3 target = neck.At(neck.Around(p));
                // The collar rises toward the nape: there the head meets it where its sections come down to the
                // collar's height, so the surface never dips below the collar and folds back up. The sections are
                // before the sculpt's scale: compare the collar's height brought back to that size.
                float sectionY = Pivot.y + (target.y - Pivot.y) / sculpt.Scale;
                float end = Mathf.Clamp(HeightToV(shape.Sections, sectionY), jaw + 0.04f, shape.Rows[shape.Rows.Length - 1]);
                // A sharper jaw leaves the head surface faster right under the jaw line (slope 2 instead of 0).
                float t = Mathf.InverseLerp(jaw, end, v);
                tuck = Mathf.Lerp(Mathf.SmoothStep(0f, 1f, t), 1f - Sq(1f - t), sculpt.JawEdge);
                p = Vector3.Lerp(p, target, tuck);
            }
            return p;
        }

        /// <summary>The image v at which the head's sections come down to the height <paramref name="y"/>.</summary>
        private static float HeightToV(Section[] table, float y)
        {
            for (int i = 1; i < table.Length; i++)
            {
                if (table[i].Y <= y)
                {
                    return Mathf.Lerp(table[i - 1].V, table[i].V, Mathf.InverseLerp(table[i - 1].Y, table[i].Y, y));
                }
            }
            return table[table.Length - 1].V;
        }

        /// <summary>The head surface at image (u, v): the row's contour laid by arc length, then the sculpted features,
        /// then the sculpt's scale.</summary>
        private static Vector3 Surface(Shape shape, Sculpt sculpt, float u, float v)
        {
            float du = u - 0.5f;
            float ad = Mathf.Abs(du);
            Section r = SectionAt(shape.Sections, v);
            if (r.A < 1e-5f)
            {
                return Pivot + (new Vector3(0f, r.Y, r.Zc) - Pivot) * sculpt.Scale;
            }
            if (r.Nf > 2.2f)
            {
                r.Nf = Mathf.Lerp(r.Nf, 2.2f, sculpt.FrontRound);
            }
            float widest = Trace(r);
            float total = ArcS[ArcSamples - 1];
            // The face front keeps the image's own proportions (x proportional to du), the pupils at the eye span; the
            // cheeks and temples take the arc to the ears, the hair the rest to the back of the head.
            float scale = shape.EyeHalfSpan / shape.PupilDu;
            float ear = widest - 0.004f;
            float front = Mathf.Min(scale * shape.FrontDu, 0.55f * ear);
            float s = ad <= shape.FrontDu ? front * ad / shape.FrontDu
                : ad <= shape.EarDu ? Mathf.Lerp(front, ear, (ad - shape.FrontDu) / (shape.EarDu - shape.FrontDu))
                : Mathf.Lerp(ear, total, (ad - shape.EarDu) / (0.5f - shape.EarDu));
            int i = 1;
            while (i < ArcSamples - 1 && ArcS[i] < s) { i++; }
            float k = Mathf.InverseLerp(ArcS[i - 1], ArcS[i], s);
            float px = Mathf.Lerp(ArcX[i - 1], ArcX[i], k);
            float pz = Mathf.Lerp(ArcZ[i - 1], ArcZ[i], k);
            // Image left (u < 0.5) is the character's right (+x).
            float sign = du > 0f ? -1f : 1f;
            var p = new Vector3(sign * px, r.Y, pz);

            // The face relief stays on the face: the contour's x is small again at the back of the head.
            float face = 1f - Smooth(0.16f, 0.26f, ad);
            var nose = shape.Nose;
            if (v >= nose[0].v && v <= nose[nose.Length - 1].v)
            {
                float height = sculpt.Nose * Lookup(nose, v, out float sigma);
                p.z += face * height * Mathf.Exp(-0.5f * Sq(px / (sigma * sculpt.NoseWidth)));
            }
            // The nose wings round off the base of the nose on either side of its tip.
            p.z += face * sculpt.Alar * Bump(px - shape.AlarX, 0.0065f, v - shape.AlarV, 0.018f);
            // The brow ridge over the painted brows, the eye sockets under it, toward the nose.
            p.z += face * sculpt.Brow * Mathf.Exp(-0.5f * Sq((v - shape.BrowV) / shape.BrowSigma)) * (1f - Smooth(0.045f, 0.075f, px));
            p.z -= face * sculpt.Socket * Bump(px - 0.8f * shape.EyeHalfSpan, 0.014f, v - 0.425f, 0.03f);
            // The lips, the groove under them and the chin, which also reaches a little lower.
            p.z += face * sculpt.Lips * Bump(px, 0.02f, v - shape.MouthV, 0.022f);
            p.z -= face * sculpt.ChinGroove * Bump(px, 0.022f, v - (shape.MouthV + 0.07f), 0.02f);
            float chin = face * sculpt.Chin * Bump(px, shape.ChinSigmaX, v - (shape.Jaw[0].v - 0.045f), 0.032f);
            p.z += chin;
            p.y -= 0.35f * chin;
            // Round cheeks, the cheekbones under the outer eye corners and the hollow below them, out of the contour.
            float cheek = face * (shape.CheekHeight * Mathf.Exp(-0.5f * Sq((px - scale * shape.CheekDu) / shape.CheekSigmaX)
                - 0.5f * Sq((v - shape.CheekV) / shape.CheekSigmaV))
                + sculpt.Cheekbone * Bump(px - 0.056f, 0.016f, v - 0.525f, 0.04f)
                - sculpt.CheekHollow * Bump(px - 0.056f, 0.015f, v - 0.665f, 0.04f));
            p += new Vector3(sign * px, 0f, pz - r.Zc).normalized * cheek;
            // The jaw angle, between the cheek and the ear, just above the image's jaw line.
            p.x += sign * sculpt.Jaw * Bump(ad - 0.205f, 0.04f, v - shape.JawAngleV, 0.05f);
            p += Ear(shape, sculpt, ad, v, sign);
            return Pivot + (p - Pivot) * sculpt.Scale;
        }

        /// <summary>
        /// The ear over its painting: an egg outline (the lobe narrower), standing off the head along a line swept back,
        /// little at its front (where it joins the cheek) and most at its back rim, which drops steeply to the hair
        /// behind; a shallow bowl in front of the rim.
        /// </summary>
        private static Vector3 Ear(Shape shape, Sculpt sculpt, float ad, float v, float sign)
        {
            float eu = (ad - shape.EarDu) / shape.EarHalfDu;
            float ev = (v - shape.EarV) / shape.EarHalfV;
            float width = 1f - 0.3f * Smooth(0f, 1f, ev);
            float outline = 1f - Smooth(0.55f, 1.05f, Mathf.Sqrt(Sq(eu / width) + Sq(ev)));
            if (outline <= 0f || sculpt.Ear <= 0f)
            {
                return Vector3.zero;
            }
            float rim = 0.25f + 0.75f * Smooth(-1f, 0.85f, eu);
            float lobe = 1f - 0.4f * Smooth(0.35f, 1f, ev);
            float bowl = 1f - sculpt.EarCup * Mathf.Exp(-0.5f * Sq((eu + 0.1f) / 0.35f) - 0.5f * Sq((ev + 0.05f) / 0.35f));
            return new Vector3(sign * 0.94f, 0f, -0.34f) * (sculpt.Ear * outline * rim * lobe * bowl);
        }

        /// <summary>A unit bump: a Gaussian of half widths <paramref name="sx"/> and <paramref name="sy"/>.</summary>
        private static float Bump(float x, float sx, float y, float sy) => Mathf.Exp(-0.5f * Sq(x / sx) - 0.5f * Sq(y / sy));

        /// <summary>Samples the row's half contour into the arc buffers; returns the arc length to its widest point.</summary>
        private static float Trace(Section r)
        {
            for (int i = 0; i < ArcSamples; i++)
            {
                float t = Mathf.PI * i / (ArcSamples - 1);
                float cos = Mathf.Cos(t);
                bool front = cos >= 0f;
                float e = 2f / (front ? r.Nf : r.Nb);
                ArcX[i] = r.A * Mathf.Pow(Mathf.Abs(Mathf.Sin(t)), e);
                float c = Mathf.Pow(Mathf.Abs(cos), e);
                ArcZ[i] = front ? r.Zc + (r.Zf - r.Zc) * c : r.Zc - (r.Zc - r.Zb) * c;
                ArcS[i] = i == 0 ? 0f : ArcS[i - 1] + Mathf.Sqrt(Sq(ArcX[i] - ArcX[i - 1]) + Sq(ArcZ[i] - ArcZ[i - 1]));
            }
            return ArcS[(ArcSamples - 1) / 2];
        }

        private static Section SectionAt(Section[] table, float v)
        {
            int hi = 1;
            while (hi < table.Length - 1 && table[hi].V < v) { hi++; }
            Section a = table[hi - 1], b = table[hi];
            float t = Mathf.Clamp01((v - a.V) / (b.V - a.V));
            return new Section(v, Mathf.Lerp(a.Y, b.Y, t), Mathf.Lerp(a.A, b.A, t), Mathf.Lerp(a.Zc, b.Zc, t),
                Mathf.Lerp(a.Zf, b.Zf, t), Mathf.Lerp(a.Zb, b.Zb, t), Mathf.Lerp(a.Nf, b.Nf, t), Mathf.Lerp(a.Nb, b.Nb, t));
        }

        private static float Lookup((float x, float y)[] table, float x)
        {
            int hi = 1;
            while (hi < table.Length - 1 && table[hi].x < x) { hi++; }
            return Mathf.Lerp(table[hi - 1].y, table[hi].y, Mathf.Clamp01((x - table[hi - 1].x) / (table[hi].x - table[hi - 1].x)));
        }

        private static float Lookup((float x, float y, float z)[] table, float x, out float z)
        {
            int hi = 1;
            while (hi < table.Length - 1 && table[hi].x < x) { hi++; }
            float t = Mathf.Clamp01((x - table[hi - 1].x) / (table[hi].x - table[hi - 1].x));
            z = Mathf.Lerp(table[hi - 1].z, table[hi].z, t);
            return Mathf.Lerp(table[hi - 1].y, table[hi].y, t);
        }

        private static float Smooth(float from, float to, float x) => Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(from, to, x));

        private static float Sq(float x) => x * x;

        /// <summary>The unit vector along <paramref name="v"/> (zero when it has no length at all).</summary>
        private static Vector3 Unit(Vector3 v)
        {
            float length = v.magnitude;
            return length > 1e-9f ? v / length : Vector3.zero;
        }
    }
}
