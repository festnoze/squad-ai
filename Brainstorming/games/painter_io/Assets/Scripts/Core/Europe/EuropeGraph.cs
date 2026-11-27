using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Land adjacency and centroids of the Europe countries (docs/europe/PROGRESSION.md). Built from the exactly shared
    /// border edges of Resources/Europe/countries.json: two countries are neighbors when an edge of one ring is also an
    /// edge of a ring of the other, and the shared border length is the sum of those edges. Pure C#, deterministic: the
    /// result does not depend on the order of the shapes.
    /// </summary>
    public sealed class EuropeGraph
    {
        public readonly struct Neighbor
        {
            public readonly string Code;
            /// <summary>Length of the shared land border, in the units of the rings (kilometers for countries.json).</summary>
            public readonly double SharedLength;

            public Neighbor(string code, double sharedLength)
            {
                Code = code;
                SharedLength = sharedLength;
            }
        }

        /// <summary>One country: every ring of every part (outer rings CCW, holes CW, so signed areas add up).</summary>
        public sealed class Shape
        {
            public string Code;
            public readonly List<Vec2d[]> Rings = new List<Vec2d[]>();
        }

        private readonly string[] codes;
        private readonly Dictionary<string, int> index = new Dictionary<string, int>(StringComparer.Ordinal);
        private readonly Vec2d[] centroids;
        private readonly Neighbor[][] neighbors;

        /// <summary>
        /// A graph from explicit data (tests use small synthetic maps). Codes are kept in ordinal order; each border is
        /// (a, b, length) and is symmetric; repeated pairs add up; non-positive lengths are ignored.
        /// </summary>
        public EuropeGraph(IReadOnlyList<string> countryCodes, IReadOnlyList<Vec2d> countryCentroids,
            IEnumerable<(string a, string b, double length)> borders)
        {
            if (countryCodes == null) throw new ArgumentNullException(nameof(countryCodes));
            if (countryCentroids == null || countryCentroids.Count != countryCodes.Count)
                throw new ArgumentException("One centroid per country.", nameof(countryCentroids));
            var order = new int[countryCodes.Count];
            for (int i = 0; i < order.Length; i++) order[i] = i;
            Array.Sort(order, (x, y) => string.CompareOrdinal(countryCodes[x], countryCodes[y]));
            codes = new string[order.Length];
            centroids = new Vec2d[order.Length];
            for (int i = 0; i < order.Length; i++)
            {
                string code = countryCodes[order[i]];
                if (string.IsNullOrEmpty(code) || index.ContainsKey(code))
                    throw new ArgumentException("Country codes must be unique and not empty: '" + code + "'.", nameof(countryCodes));
                codes[i] = code;
                centroids[i] = countryCentroids[order[i]];
                index[code] = i;
            }

            var lengths = new Dictionary<(int, int), double>();
            if (borders != null)
            {
                foreach (var (a, b, length) in borders)
                {
                    if (!(length > 0) || a == b || !index.TryGetValue(a, out int ia) || !index.TryGetValue(b, out int ib)) continue;
                    var key = ia < ib ? (ia, ib) : (ib, ia);
                    lengths.TryGetValue(key, out double sum);
                    lengths[key] = sum + length;
                }
            }
            var lists = new List<Neighbor>[codes.Length];
            for (int i = 0; i < lists.Length; i++) lists[i] = new List<Neighbor>();
            foreach (var pair in lengths)
            {
                lists[pair.Key.Item1].Add(new Neighbor(codes[pair.Key.Item2], pair.Value));
                lists[pair.Key.Item2].Add(new Neighbor(codes[pair.Key.Item1], pair.Value));
            }
            neighbors = new Neighbor[codes.Length][];
            for (int i = 0; i < lists.Length; i++)
            {
                lists[i].Sort((x, y) =>
                {
                    int byLength = y.SharedLength.CompareTo(x.SharedLength);
                    return byLength != 0 ? byLength : string.CompareOrdinal(x.Code, y.Code);
                });
                neighbors[i] = lists[i].ToArray();
            }
        }

        /// <summary>Country codes in ordinal order.</summary>
        public IReadOnlyList<string> Codes => codes;

        public int Count => codes.Length;

        public bool Contains(string code) => code != null && index.ContainsKey(code);

        /// <summary>Area-weighted centroid of all the parts of the country.</summary>
        public Vec2d Centroid(string code) => centroids[IndexOf(code)];

        /// <summary>Land neighbors, longest shared border first, then by code.</summary>
        public IReadOnlyList<Neighbor> Neighbors(string code) => neighbors[IndexOf(code)];

        /// <summary>Shared land border length between two countries (0 when they are not neighbors).</summary>
        public double SharedBorder(string a, string b)
        {
            foreach (Neighbor n in neighbors[IndexOf(a)])
            {
                if (n.Code == b) return n.SharedLength;
            }
            return 0;
        }

        /// <summary>Distance between the centroids of two countries.</summary>
        public double CentroidDistance(string a, string b) => Vec2d.Distance(Centroid(a), Centroid(b));

        private int IndexOf(string code)
        {
            if (code == null || !index.TryGetValue(code, out int i))
                throw new ArgumentException("Unknown country '" + code + "'.", nameof(code));
            return i;
        }

        /// <summary>
        /// Builds the graph from country rings: centroids from the signed ring areas, borders from the edges that two
        /// countries share exactly (vertices compared after rounding to QuantumPerUnit).
        /// </summary>
        public static EuropeGraph FromShapes(IReadOnlyList<Shape> shapes)
        {
            if (shapes == null) throw new ArgumentNullException(nameof(shapes));
            var codeList = new string[shapes.Count];
            var centroidList = new Vec2d[shapes.Count];
            var firstOwner = new Dictionary<(long, long, long, long), int>();
            var borders = new List<(string, string, double)>();
            for (int s = 0; s < shapes.Count; s++)
            {
                Shape shape = shapes[s];
                codeList[s] = shape.Code;
                centroidList[s] = CentroidOf(shape.Rings);
                foreach (Vec2d[] ring in shape.Rings)
                {
                    if (ring == null) continue;
                    for (int i = 0; i < ring.Length; i++)
                    {
                        Vec2d a = ring[i];
                        Vec2d b = ring[(i + 1) % ring.Length];
                        (long, long) qa = Quantize(a), qb = Quantize(b);
                        if (qa == qb) continue;
                        var key = Compare(qa, qb) < 0 ? (qa.Item1, qa.Item2, qb.Item1, qb.Item2) : (qb.Item1, qb.Item2, qa.Item1, qa.Item2);
                        if (!firstOwner.TryGetValue(key, out int owner))
                        {
                            firstOwner[key] = s;
                            continue;
                        }
                        if (owner == s) continue;
                        borders.Add((shapes[owner].Code, shape.Code, Vec2d.Distance(a, b)));
                    }
                }
            }
            return new EuropeGraph(codeList, centroidList, borders);
        }

        /// <summary>Vertices closer than 1 / QuantumPerUnit are the same vertex (countries.json is precise to 1 m).</summary>
        public const double QuantumPerUnit = 1000.0;

        private static (long, long) Quantize(Vec2d p) =>
            ((long)Math.Round(p.X * QuantumPerUnit), (long)Math.Round(p.Y * QuantumPerUnit));

        private static int Compare((long, long) a, (long, long) b) => a.Item1 != b.Item1 ? a.Item1.CompareTo(b.Item1) : a.Item2.CompareTo(b.Item2);

        private static Vec2d CentroidOf(List<Vec2d[]> rings)
        {
            double area2 = 0, cx = 0, cy = 0, sx = 0, sy = 0;
            int count = 0;
            foreach (Vec2d[] ring in rings)
            {
                if (ring == null) continue;
                for (int i = 0; i < ring.Length; i++)
                {
                    Vec2d a = ring[i];
                    Vec2d b = ring[(i + 1) % ring.Length];
                    double cross = Vec2d.Cross(a, b);
                    area2 += cross;
                    cx += (a.X + b.X) * cross;
                    cy += (a.Y + b.Y) * cross;
                    sx += a.X;
                    sy += a.Y;
                    count++;
                }
            }
            if (Math.Abs(area2) > 1e-12) return new Vec2d(cx / (3.0 * area2), cy / (3.0 * area2));
            return count > 0 ? new Vec2d(sx / count, sy / count) : Vec2d.Zero;
        }
    }
}
