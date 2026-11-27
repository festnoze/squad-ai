// Europe campaign rules (docs/europe/PROGRESSION.md) on small synthetic maps. Pure Core: runs in the dotnet loop
// (tools/CoreTests) and in Unity EditMode. The real 46-country map is covered by Runtime/EuropeProgressTests.cs.
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    public class EuropeProgressionTests
    {
        // A small "Europe": FR in the middle, an island chain in the north-west (GB-IE land border, IS alone).
        private static EuropeGraph MiniMap()
        {
            var codes = new[] { "FR", "ES", "BE", "DE", "IT", "CH", "MC", "GB", "IE", "IS" };
            var centroids = new[]
            {
                new Vec2d(0, 0), new Vec2d(-2, -3), new Vec2d(1, 2), new Vec2d(4, 2), new Vec2d(3, -2),
                new Vec2d(2.5, 0), new Vec2d(1.5, -1.5), new Vec2d(-1, 4), new Vec2d(-3, 4.5), new Vec2d(-5, 9),
            };
            var borders = new List<(string, string, double)>
            {
                ("FR", "ES", 5), ("FR", "BE", 4), ("FR", "CH", 3.9), ("FR", "DE", 3), ("FR", "IT", 2), ("FR", "MC", 0.1),
                ("BE", "DE", 1), ("DE", "CH", 2), ("CH", "IT", 4), ("GB", "IE", 3),
            };
            return new EuropeGraph(codes, centroids, borders);
        }

        [Test]
        public void EU1_StartState_OnlyTheStartCountryIsUnlocked()
        {
            var p = new EuropeProgression(MiniMap());
            Assert.That(EuropeProgression.StartCountry, Is.EqualTo("FR"));
            Assert.That(p.StateOf("FR"), Is.EqualTo(CountryProgress.Unlocked));
            Assert.That(p.PlayablePool(), Is.EqualTo(new[] { "FR" }));
            Assert.That(p.WonCount, Is.EqualTo(0));
            Assert.That(p.UnlockedCount, Is.EqualTo(1));
            foreach (string code in p.Graph.Codes.Where(c => c != "FR"))
            {
                Assert.That(p.StateOf(code), Is.EqualTo(CountryProgress.Locked), code);
                Assert.That(p.IsPlayable(code), Is.False, code);
            }
            Assert.That(p.PendingReveal, Is.Empty);
        }

        [Test]
        public void EU2_FirstWin_UnlocksTwoLandNeighbors_LongestBorderFirst()
        {
            var p = new EuropeProgression(MiniMap());
            IReadOnlyList<string> unlocked = p.RecordWin("FR");
            Assert.That(unlocked, Is.EqualTo(new[] { "ES", "BE" }));
            Assert.That(p.StateOf("FR"), Is.EqualTo(CountryProgress.Won));
            Assert.That(p.StateOf("ES"), Is.EqualTo(CountryProgress.Unlocked));
            Assert.That(p.StateOf("BE"), Is.EqualTo(CountryProgress.Unlocked));
            Assert.That(p.StateOf("CH"), Is.EqualTo(CountryProgress.Locked));
            Assert.That(p.PlayablePool(), Is.EqualTo(new[] { "BE", "ES" }));
            Assert.That(p.PendingReveal, Is.EqualTo(new[] { "ES", "BE" }));
        }

        [Test]
        public void EU3_TieBreaks_SharedBorderThenCentroidDistanceThenCode()
        {
            var codes = new[] { "AA", "ZZ", "BB", "CC", "DD" };
            var centroids = new[] { new Vec2d(0, 0), new Vec2d(1, 0), new Vec2d(0, 1), new Vec2d(-3, 0), new Vec2d(0, -3) };
            var borders = new List<(string, string, double)> { ("AA", "ZZ", 2), ("AA", "BB", 2), ("AA", "CC", 2), ("AA", "DD", 2) };
            var graph = new EuropeGraph(codes, centroids, borders);
            // Same border everywhere: ZZ and BB are nearer than CC and DD; ZZ and BB are equally near, BB < ZZ by code.
            Assert.That(EuropeProgression.PickUnlocks(graph, "AA", c => true, 2), Is.EqualTo(new[] { "BB", "ZZ" }));
            Assert.That(EuropeProgression.PickUnlocks(graph, "AA", c => true, 4), Is.EqualTo(new[] { "BB", "ZZ", "CC", "DD" }));
        }

        [Test]
        public void EU4_IslandFallback_FillsWithTheNearestLockedCountries()
        {
            var p = new EuropeProgression(MiniMap());
            // GB has one land neighbor (IE); the second unlock is the nearest locked country by centroid (BE).
            Assert.That(p.RecordWin("GB"), Is.EqualTo(new[] { "IE", "BE" }));
            // IS has no land neighbor at all: the two nearest locked countries by centroid.
            var q = new EuropeProgression(MiniMap());
            Assert.That(q.RecordWin("IS"), Is.EqualTo(new[] { "IE", "GB" }));
        }

        [Test]
        public void EU5_FewerThanTwoLockedNeighbors_CompletesWithTheNearest()
        {
            var p = new EuropeProgression(MiniMap());
            p.RecordWin("FR");                       // ES, BE
            // BE's neighbors: FR (won) and DE (locked); the second unlock is the nearest locked centroid (CH 2.5 < GB 2.83).
            Assert.That(p.RecordWin("BE"), Is.EqualTo(new[] { "DE", "CH" }));
            // ES has no locked neighbor left: two nearest locked countries by centroid (MC, then IT).
            Assert.That(p.RecordWin("ES"), Is.EqualTo(new[] { "MC", "IT" }));
        }

        [Test]
        public void EU6_ReplayOfAWonCountry_UnlocksNothing()
        {
            var p = new EuropeProgression(MiniMap());
            p.RecordWin("FR");
            p.ClearReveal();
            EuropeProgressData before = p.ToData();
            Assert.That(p.RecordWin("FR"), Is.Empty);
            Assert.That(p.RecordWin("XX"), Is.Empty, "unknown code");
            EuropeProgressData after = p.ToData();
            Assert.That(after.won, Is.EqualTo(before.won));
            Assert.That(after.unlocked, Is.EqualTo(before.unlocked));
            Assert.That(after.reveal, Is.Empty);
        }

        [Test]
        public void EU7_SameHistory_SameMap_WhateverTheInputOrder()
        {
            string[] history = { "FR", "BE", "ES", "DE", "CH" };
            var a = new EuropeProgression(MiniMap());
            var b = new EuropeProgression(MiniMap());
            foreach (string code in history)
            {
                Assert.That(a.RecordWin(code), Is.EqualTo(b.RecordWin(code)), code);
            }
            Assert.That(a.ToData().unlocked, Is.EqualTo(b.ToData().unlocked));
            Assert.That(a.ToData().reveal, Is.EqualTo(b.ToData().reveal));

            // The graph built from shapes in another order gives the same neighbors and picks.
            List<EuropeGraph.Shape> shapes = Squares();
            EuropeGraph forward = EuropeGraph.FromShapes(shapes);
            shapes.Reverse();
            EuropeGraph backward = EuropeGraph.FromShapes(shapes);
            foreach (string code in forward.Codes)
            {
                Assert.That(backward.Neighbors(code).Select(n => n.Code), Is.EqualTo(forward.Neighbors(code).Select(n => n.Code)), code);
                Assert.That(EuropeProgression.PickUnlocks(backward, code, c => true, 2),
                            Is.EqualTo(EuropeProgression.PickUnlocks(forward, code, c => true, 2)), code);
            }
        }

        [Test]
        public void EU8_FullCampaign_ThePlayablePoolNeverEmpties()
        {
            var p = new EuropeProgression(MiniMap());
            int steps = 0;
            while (p.WonCount < p.Graph.Count)
            {
                List<string> pool = p.PlayablePool();
                Assert.That(pool, Is.Not.Empty, "after " + steps + " wins");
                int lockedBefore = p.Graph.Count - p.UnlockedCount;
                IReadOnlyList<string> unlocked = p.RecordWin(pool[0]);
                Assert.That(unlocked.Count, Is.EqualTo(System.Math.Min(EuropeProgression.UnlocksPerFirstWin, lockedBefore)), pool[0]);
                steps++;
                Assert.That(steps, Is.LessThanOrEqualTo(p.Graph.Count));
            }
            Assert.That(steps, Is.EqualTo(p.Graph.Count));
            Assert.That(p.PlayablePool(), Is.Empty);
        }

        [Test]
        public void EU9_DataRoundTrip_AndSanitizing()
        {
            var p = new EuropeProgression(MiniMap());
            p.RecordWin("FR");
            p.RecordWin("ES");
            EuropeProgressData data = p.ToData();
            Assert.That(data.version, Is.EqualTo(EuropeProgression.DataVersion));
            EuropeProgression back = EuropeProgression.FromData(MiniMap(), data);
            foreach (string code in p.Graph.Codes) Assert.That(back.StateOf(code), Is.EqualTo(p.StateOf(code)), code);
            Assert.That(back.PendingReveal, Is.EqualTo(p.PendingReveal));

            var broken = new EuropeProgressData { version = 99, won = new[] { "BE", "XX" }, unlocked = new[] { "YY" }, reveal = new[] { "BE", "ZZ", "GB" } };
            EuropeProgression clean = EuropeProgression.FromData(MiniMap(), broken);
            Assert.That(clean.StateOf("FR"), Is.EqualTo(CountryProgress.Unlocked), "the start country stays playable");
            Assert.That(clean.StateOf("BE"), Is.EqualTo(CountryProgress.Won), "won implies unlocked");
            Assert.That(clean.UnlockedCount, Is.EqualTo(2));
            Assert.That(clean.PendingReveal, Is.Empty, "a reveal lists unlocked, not won countries only");
            Assert.That(EuropeProgression.FromData(MiniMap(), null).PlayablePool(), Is.EqualTo(new[] { "FR" }));
        }

        [Test]
        public void EU10_FromShapes_SharedEdgesAndCentroids()
        {
            EuropeGraph graph = EuropeGraph.FromShapes(Squares());
            Assert.That(graph.Codes, Is.EqualTo(new[] { "FR", "IS", "XA", "XB" }));
            Assert.That(graph.SharedBorder("FR", "XA"), Is.EqualTo(2).Within(1e-9));
            Assert.That(graph.SharedBorder("XA", "FR"), Is.EqualTo(2).Within(1e-9));
            Assert.That(graph.SharedBorder("FR", "XB"), Is.EqualTo(1).Within(1e-9), "a half shared side");
            Assert.That(graph.Neighbors("FR").Select(n => n.Code), Is.EqualTo(new[] { "XA", "XB" }));
            Assert.That(graph.Neighbors("IS"), Is.Empty);
            Assert.That(graph.Centroid("FR").X, Is.EqualTo(1).Within(1e-9));
            Assert.That(graph.Centroid("FR").Y, Is.EqualTo(1).Within(1e-9));
            Assert.That(graph.Centroid("IS").X, Is.EqualTo(11).Within(1e-9));
        }

        // FR: square (0,0)-(2,2); XA: square (2,0)-(4,2) sharing FR's east side; XB: rectangle on FR's north side, over
        // x 0..1 (its south side shares FR's top edge split at (1,2)); IS: an island square far away.
        private static List<EuropeGraph.Shape> Squares()
        {
            EuropeGraph.Shape Make(string code, params Vec2d[] ring)
            {
                var s = new EuropeGraph.Shape { Code = code };
                s.Rings.Add(ring);
                return s;
            }
            return new List<EuropeGraph.Shape>
            {
                Make("FR", new Vec2d(0, 0), new Vec2d(2, 0), new Vec2d(2, 2), new Vec2d(1, 2), new Vec2d(0, 2)),
                Make("XA", new Vec2d(2, 0), new Vec2d(4, 0), new Vec2d(4, 2), new Vec2d(2, 2)),
                Make("XB", new Vec2d(0, 2), new Vec2d(1, 2), new Vec2d(1, 3), new Vec2d(0, 3)),
                Make("IS", new Vec2d(10, 0), new Vec2d(12, 0), new Vec2d(12, 2), new Vec2d(10, 2)),
            };
        }
    }
}
