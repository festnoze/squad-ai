// Owned by A3 (trail). Contract 5.4 and section 7 (the capture outline is the loop-erased trail, R8).
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    public static class LoopErase
    {
        // Per-thread scratch so a return does not rebuild a dictionary every time (the Core is single threaded; the
        // attribute only keeps parallel test runners safe).
        [ThreadStatic] private static SegmentBuckets scratchBuckets;
        [ThreadStatic] private static List<int> scratchCandidates;

        /// <summary>
        /// Removes every self loop. Walks the polyline; for each new segment, among the kept non-adjacent segments it
        /// properly crosses (Geo.ProperIntersect, new segment first), takes the one with the SMALLEST index j, truncates
        /// the kept path after segment j, appends the crossing point and continues with the rest of the new segment. No
        /// re-test is needed: by minimality of j the rest crosses no kept segment of index &lt; j, and it cannot cross the
        /// piece of segment j it starts on. Result: a simple polyline from the first to the last input point.
        /// Exact duplicate consecutive points are dropped. Kept segments live in a spatial hash (bucket 2 u): a truncated
        /// segment keeps its old registration (a superset of its new extent), stale ids beyond the kept count are
        /// skipped, so a query never misses a kept segment.
        /// </summary>
        public static List<Vec2d> Erase(IReadOnlyList<Vec2d> points)
        {
            int n = points == null ? 0 : points.Count;
            var kept = new List<Vec2d>(n);
            if (n == 0) return kept;

            SegmentBuckets buckets = scratchBuckets ?? (scratchBuckets = new SegmentBuckets());
            List<int> candidates = scratchCandidates ?? (scratchCandidates = new List<int>());
            buckets.Clear();
            // kept.Count never exceeds n: a truncation at j <= Count - 3 removes at least as many points as it adds
            // (X and p), so ids (kept segment indices) stay below n.
            var stamps = new int[n + 1];
            int stamp = 0;

            kept.Add(points[0]);
            const double pad = 1e-7;
            for (int i = 1; i < n; i++)
            {
                Vec2d p = points[i];
                Vec2d c = kept[kept.Count - 1];
                if (p == c) continue;

                // Kept segments are 0 .. segs-1; segs-1 ends at c (adjacent) and is excluded through idLimit.
                int segs = kept.Count - 1;
                int jMin = -1;
                double taMin = 0.0, tbMin = 0.0;
                if (segs >= 2)
                {
                    stamp++;
                    candidates.Clear();
                    double minX = Math.Min(c.X, p.X) - pad, minY = Math.Min(c.Y, p.Y) - pad;
                    double maxX = Math.Max(c.X, p.X) + pad, maxY = Math.Max(c.Y, p.Y) + pad;
                    if (buckets.BucketSpan(minX, minY, maxX, maxY) > 2L * segs + 8)
                    {
                        for (int j = 0; j < segs - 1; j++) candidates.Add(j); // huge box: plain scan, same result
                    }
                    else
                    {
                        buckets.Query(minX, minY, maxX, maxY, segs - 1, stamps, stamp, candidates);
                    }
                    for (int m = 0; m < candidates.Count; m++)
                    {
                        int j = candidates[m];
                        if (jMin >= 0 && j >= jMin) continue;
                        // Same crossing rule as Trail.SelfCrossings (Geo.ProperIntersect with its rounding band at the
                        // new segment's end), so R8 and R16 see the same loops.
                        if (Geo.ProperIntersect(c, p, kept[j], kept[j + 1], out double ta, out double tb))
                        {
                            jMin = j;
                            taMin = ta;
                            tbMin = tb;
                        }
                    }
                }

                if (jMin >= 0)
                {
                    // Crossing point, taken exactly at an old vertex (tb = 0) or at the new segment's end (ta = 1).
                    Vec2d x = tbMin == 0.0 ? kept[jMin]
                            : taMin == 1.0 ? p
                            : Vec2d.Lerp(kept[jMin], kept[jMin + 1], tbMin);
                    kept.RemoveRange(jMin + 1, kept.Count - jMin - 1);
                    // Segment jMin becomes [kept[jMin], x], a piece of its old extent: its registration still covers it.
                    if (x != kept[jMin]) kept.Add(x);
                }

                Vec2d last = kept[kept.Count - 1];
                if (p != last)
                {
                    int id = kept.Count - 1;
                    kept.Add(p);
                    buckets.Add(id, last, p);
                }
            }
            buckets.Clear();
            return kept;
        }
    }
}
