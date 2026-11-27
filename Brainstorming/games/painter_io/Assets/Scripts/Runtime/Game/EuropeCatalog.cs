using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    [Serializable]
    public sealed class EuropeCatalog
    {
        public Country[] countries;
        private static EuropeCatalog loaded;

        public static EuropeCatalog Load()
        {
            if (loaded != null) return loaded;
            TextAsset source = Resources.Load<TextAsset>("Europe/countries");
            if (source == null) throw new InvalidOperationException("Europe/countries.json est introuvable.");
            return loaded = JsonUtility.FromJson<EuropeCatalog>(source.text);
        }

        [Serializable]
        public sealed class Point
        {
            public float x, y;
            public Vector2 Vector => new Vector2(x, y);
            public Vec2d Scale(double factor) => new Vec2d(x * factor, y * factor);
        }

        [Serializable]
        public sealed class Ring
        {
            public Point[] points;
        }

        [Serializable]
        public sealed class Part
        {
            public Point[] outer, vertices;
            public Ring[] holes;
            public int[] triangles;
        }

        [Serializable]
        public sealed class Country
        {
            public string code, name;
            public Part[] parts;
            public Point[] level;
            public Point label, levelCenter;

            public string DisplayName
            {
                get
                {
                    if (Strings.Language == 0) return name;
                    if (code == "XK") return "Kosovo";
                    if (code == "TR") return "Türkiye";
                    try { return new System.Globalization.RegionInfo(code).EnglishName; }
                    catch (ArgumentException) { return name; }
                }
            }

            public void Configure(SimConfig config, SimSetup setup)
            {
                double scale = config.ArenaHalfSize - 1.2;
                Vec2d center = levelCenter.Scale(scale);
                var polygon = new ArenaPolygon(Array.ConvertAll(level, point => point.Scale(scale)), center);
                config.ArenaBoundary = polygon;

                var candidates = new List<Vec2d>();
                double inset = config.ArenaMargin + 0.3;
                if (polygon.Distance(center, out _) < -inset) candidates.Add(center);
                for (double y = -scale; y <= scale; y += 1.0)
                for (double x = -scale; x <= scale; x += 1.0)
                {
                    var p = new Vec2d(x, y);
                    if (polygon.Distance(p, out _) < -inset) candidates.Add(p);
                }

                // Give each pawn room to turn, favouring separated starts and the deeper parts of narrow countries.
                var starts = new Vec2d[setup.PlayerCount];
                var headings = new double[starts.Length];
                double safeRadius = config.StartDiscRadius;
                for (int player = 0; player < starts.Length; player++)
                {
                    double best = double.NegativeInfinity;
                    foreach (Vec2d candidate in candidates)
                    {
                        double clearance = -polygon.Distance(candidate, out _);
                        double separation = double.PositiveInfinity;
                        for (int i = 0; i < player; i++)
                            separation = Math.Min(separation, Vec2d.Distance(starts[i], candidate));
                        double score = Math.Min(separation * 0.5, clearance * 2.5);
                        if (score <= best) continue;
                        best = score;
                        starts[player] = candidate;
                    }
                    if (!(best > 0)) throw new InvalidOperationException($"Départs impossibles pour {code}.");
                    headings[player] = (center - starts[player]).Angle();
                    double edgeRoom = -polygon.Distance(starts[player], out _) - 0.15;
                    safeRadius = Math.Min(safeRadius, Math.Min(edgeRoom, best * 0.8));
                }
                config.StartDiscRadius = safeRadius;
                setup.StartPositions = starts;
                setup.StartHeadings = headings;
            }
        }
    }
}
