// Rule v1.7 (contract 31): the conquest goal. The conquerable mask (what can really be owned), the threshold logic, and
// scripted rounds that end by conquest on the default square arena and on a non-convex country polygon with a thin neck.
// The scripted RimFollower makes short excursions along the border (it leans into the wall, so the border motion of R4
// keeps its head on the inset line), each one closed by a return straight inward to its land, until the whole rim band
// is painted: this is the reachability proof that the goal shown as 100 % can be met by real captures.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public sealed class ConquestTests
    {
        // ------------------------------------------------------------------------------------------------------------
        // Threshold logic.

        [Test]
        public void Conquest_TargetAndPercent()
        {
            Assert.AreEqual(995, Conquest.TargetCells(1000, 1.0), "goal 100 % = 99.5 % of the conquerable cells (reads 100 %)");
            Assert.AreEqual(995, Conquest.TargetCells(1000, 2.0), "a share above 1 counts as 1");
            Assert.AreEqual(495, Conquest.TargetCells(1000, 0.5));
            Assert.AreEqual(1, Conquest.TargetCells(1000, 0.001), "at least one cell");
            Assert.AreEqual(int.MaxValue, Conquest.TargetCells(1000, 0.0), "0 turns the goal off");
            Assert.AreEqual(int.MaxValue, Conquest.TargetCells(1000, -1.0));
            Assert.AreEqual(int.MaxValue, Conquest.TargetCells(1000, double.NaN));
            Assert.AreEqual(int.MaxValue, Conquest.TargetCells(0, 1.0), "no conquerable cell, no goal");

            Assert.AreEqual(100.0, Conquest.Percent(1200, 1000), 1e-12, "clamped: a captured rim cell outside the mask never shows more than 100 %");
            Assert.AreEqual(50.0, Conquest.Percent(500, 1000), 1e-12);
            Assert.AreEqual(0.0, Conquest.Percent(0, 1000), 1e-12);
            Assert.AreEqual(0.0, Conquest.Percent(10, 0), 1e-12);
            // The target is the first count whose percentage the HUD rounds to the goal (whole numbers from 10 %).
            Assert.That(Conquest.Percent(Conquest.TargetCells(1000, 1.0), 1000), Is.GreaterThanOrEqualTo(99.5));
            Assert.That(Conquest.Percent(Conquest.TargetCells(1000, 1.0) - 1, 1000), Is.LessThan(99.5));
        }

        // ------------------------------------------------------------------------------------------------------------
        // The conquerable mask.

        [Test]
        public void Conquest_SquareArena_TheRimBandIsNotConquerable()
        {
            var sim = new Simulation(new SimConfig(), new IController[4]);
            OwnerGrid g = sim.Grid;
            int arena = g.ArenaCellCount;
            int conquerable = sim.ConquestCellCount;
            double lostShare = 1.0 - conquerable / (double)arena;
            TestContext.WriteLine("square arena: " + arena + " arena cells, " + conquerable + " conquerable, rim band "
                                  + (100.0 * lostShare).ToString("F2") + " %");
            Assert.That(lostShare, Is.InRange(0.01, 0.04), "the rim band (about 3 cells deep) is a few percent of the arena");

            int wrongLost = 0, wrongKept = 0;
            for (int j = 0; j < g.Size; j++)
            {
                for (int i = 0; i < g.Size; i++)
                {
                    int k = g.Index(i, j);
                    if (g.Cells[k] == OwnerGrid.Void)
                    {
                        Assert.IsFalse(sim.IsConquerable(k), "a Void cell is never conquerable");
                        continue;
                    }
                    double sd = sim.Arena.SignedDistance(g.CellCenter(i, j));
                    if (sd <= -sim.Arena.Margin && !sim.IsConquerable(k)) wrongLost++;
                    if (sd > -sim.Arena.Margin + 0.2 && sim.IsConquerable(k)) wrongKept++;
                }
            }
            Assert.AreEqual(0, wrongLost, "every cell whose center a head can reach is conquerable");
            Assert.AreEqual(0, wrongKept, "no cell of the outer rim band is conquerable");
            Assert.That(sim.ConquestTargetCells, Is.EqualTo((int)Math.Ceiling(conquerable * 0.995 - 1e-9)));
        }

        [Test]
        public void Conquest_Polygon_APieceBeyondAThinNeckIsNotConquerable()
        {
            Simulation sim = NeckCountry(1.0, out _);
            OwnerGrid g = sim.Grid;
            int island = 0, islandKept = 0, body = 0, bodyLost = 0;
            for (int j = 0; j < g.Size; j++)
            {
                for (int i = 0; i < g.Size; i++)
                {
                    int k = g.Index(i, j);
                    if (g.Cells[k] == OwnerGrid.Void) continue;
                    Vec2d c = g.CellCenter(i, j);
                    double sd = sim.Arena.SignedDistance(c);
                    if (c.Y > 23.5 && c.X > -5.5 && c.X < 9.5)
                    {
                        island++;
                        if (sim.IsConquerable(k)) islandKept++;
                    }
                    else if (c.Y < 19.0 && sd <= -sim.Arena.Margin)
                    {
                        body++;
                        if (!sim.IsConquerable(k)) bodyLost++;
                    }
                }
            }
            TestContext.WriteLine("neck country: " + g.ArenaCellCount + " arena cells, " + sim.ConquestCellCount + " conquerable, island "
                                  + island + " cells");
            Assert.That(island, Is.GreaterThan(3000), "the piece beyond the neck is large");
            Assert.AreEqual(0, islandKept, "no head can pass a neck narrower than 2 x ArenaMargin: that piece is out of the goal");
            Assert.That(body, Is.GreaterThan(50000));
            Assert.AreEqual(0, bodyLost, "every reachable cell of the main body is conquerable");
        }

        // ------------------------------------------------------------------------------------------------------------
        // Rounds that end by conquest.

        [Test]
        public void Conquest_SquareArena_ARimLapEndsTheRoundByConquest()
        {
            var sb = new SimBuilder(60);
            sb.Config.RoundDuration = 400.0;
            var follower = new RimFollower();
            sb.Add(V(-10, -10), East, follower, (g, id) => FillInner(g, id, 2.0, null));
            Simulation sim = sb.Build();
            var log = new EventLog(sim);
            RunUntilTime(sim, sb.Config.RoundDuration);

            Report("square", sim, 0);
            Assert.IsTrue(sim.Ended);
            Assert.AreEqual(RoundEndReason.Conquest, sim.Result.Reason, "ended by conquest, before the time limit:\n" + Tail(log));
            Assert.That(sim.Result.EndTime, Is.LessThan(sb.Config.RoundDuration));
            Assert.AreEqual(new List<int> { 0 }, sim.Result.Winners);
            Assert.That(sim.ConquestPercent(0), Is.GreaterThanOrEqualTo(99.5), "the HUD reads 100 %");
            Assert.That(sim.Grid.CountOf(sim.Players[0].Id), Is.GreaterThanOrEqualTo(sim.ConquestTargetCells));
            Assert.AreEqual(1, log.Count(SimEventType.RoundEnded));
        }

        [Test]
        public void Conquest_SquareArena_ARivalStillAliveOnASpeckDoesNotStopTheConquest()
        {
            // The rival holds a 3 x 3 square at the center (about 0.23 % of the conquerable cells) and circles there:
            // the goal shown as 100 % is met while it lives, so the round ends by Conquest, not LastSurvivor.
            SimConfig config = SimTestKit.Config(60);
            config.RoundDuration = 400.0;
            const int rival = 1;
            Simulation sim = BuildWithRivalDisc(config);
            var log = new EventLog(sim);
            RunUntilTime(sim, config.RoundDuration);

            Report("square + rival", sim, 0);
            Assert.IsTrue(sim.Ended);
            Assert.IsTrue(sim.Players[rival].Alive, "the rival survives on its speck");
            Assert.AreEqual(RoundEndReason.Conquest, sim.Result.Reason, Tail(log));
            Assert.AreEqual(new List<int> { 0 }, sim.Result.Winners);
            Assert.AreEqual(2, sim.Result.Ranks[rival]);
        }

        [Test]
        public void Conquest_CountryPolygon_ARimTourEndsTheRoundByConquest()
        {
            Simulation sim = NeckCountry(1.0, out EventLog log);
            RunUntilTime(sim, sim.Config.RoundDuration);

            Report("neck country", sim, 0);
            Assert.IsTrue(sim.Ended);
            Assert.AreEqual(RoundEndReason.Conquest, sim.Result.Reason, "the piece beyond the neck does not block the goal:\n" + Tail(log));
            Assert.That(sim.Result.EndTime, Is.LessThan(sim.Config.RoundDuration));
            Assert.That(sim.ConquestPercent(0), Is.GreaterThanOrEqualTo(99.5));
        }

        [Test]
        public void Conquest_ALowerShareEndsTheRoundEarlierAndZeroTurnsTheGoalOff()
        {
            var sb = new SimBuilder(60);
            sb.Config.RoundDuration = 400.0;
            sb.Config.ConquestShare = 0.95;
            sb.Add(V(-10, -10), East, new RimFollower(), (g, id) => FillInner(g, id, 2.0, null));
            Simulation low = sb.Build();
            RunUntilTime(low, 400.0);
            Assert.AreEqual(RoundEndReason.Conquest, low.Result.Reason);
            Assert.That(low.ConquestPercent(0), Is.InRange(94.5, 99.5), "stops as soon as the HUD reads 95 %");

            var off = new SimBuilder(60);
            off.Config.RoundDuration = 60.0;
            off.Config.ConquestShare = 0.0;
            off.Add(V(-10, -10), East, new RimFollower(), (g, id) => FillInner(g, id, 2.0, null));
            Simulation sim = off.Build();
            RunUntilTime(sim, 60.0);
            Assert.AreEqual(RoundEndReason.TimeUp, sim.Result.Reason, "ConquestShare 0: the goal is off");
        }

        [Test]
        public void Conquest_AFullTourWithTheGoalOffLeavesAlmostNoConquerableCell()
        {
            // Strict reachability: with the goal off, the follower goes on for more than one full tour; what is still not
            // owned afterwards is the corners it cuts (look-ahead) and stair notches, far below the 0.5 % slack.
            var sb = new SimBuilder(60);
            sb.Config.RoundDuration = 75.0;
            sb.Config.ConquestShare = 0.0;
            sb.Add(V(-10, -10), East, new RimFollower(), (g, id) => FillInner(g, id, 2.0, null));
            Simulation square = sb.Build();
            RunUntilTime(square, 75.0);
            int squareMissing = Report("square, goal off, 75 s", square, 0);
            Assert.That(squareMissing, Is.LessThan(square.ConquestCellCount * 0.001), "square: almost every conquerable cell is owned");

            Simulation country = NeckCountry(0.0, out _);
            RunUntilTime(country, 75.0);
            int countryMissing = Report("neck country, goal off, 75 s", country, 0);
            Assert.That(countryMissing, Is.LessThan(country.ConquestCellCount * 0.002), "country: almost every conquerable cell is owned");
        }

        // ------------------------------------------------------------------------------------------------------------
        // Helpers.

        /// <summary>
        /// Leans into the border and follows it counter-clockwise (the head slides on the inset line, R4). Once its trail is
        /// ExcursionLength long it heads straight inward until it is home again, then goes back to the border and on.
        /// </summary>
        private sealed class RimFollower : IController
        {
            public const double ExcursionLength = 9.0;
            public const double LookAhead = 0.3;
            private readonly Dictionary<int, bool> returning = new Dictionary<int, bool>();

            public double? DesiredHeading(SimView view, int playerIndex)
            {
                PlayerState me = view.Player(playerIndex);
                Arena arena = view.Arena;
                // The normal a little ahead along the wall, so a convex corner of the inset shape turns the follower
                // onto the next side instead of pinning it into the corner.
                Vec2d here = arena.OutwardNormal(me.Pos);
                Vec2d normal = arena.OutwardNormal(me.Pos + here.Perp() * LookAhead);
                returning.TryGetValue(playerIndex, out bool back);
                if (me.Home) back = false;
                else if (me.Trail.Length >= ExcursionLength) back = true;
                returning[playerIndex] = back;
                if (back) return (-normal).Angle();
                double gap = -arena.SignedDistance(me.Pos) - arena.Margin;   // distance to the inset line
                double lean = Math.Min(0.5 * Math.PI, 20.0 * Math.PI / 180.0 + Math.Max(0.0, gap) * 1.2);
                Vec2d tangent = normal.Perp();
                Vec2d dir = tangent * Math.Cos(lean) + normal * Math.Sin(lean);
                return dir.Angle();
            }
        }

        /// <summary>Sets owner on every arena cell whose center is at least depth inside the shape (and passes keep).</summary>
        private static void FillInner(OwnerGrid g, byte owner, double depth, Func<Vec2d, bool> keep, Arena arena = null)
        {
            arena = arena ?? new Arena(Tuning.ArenaHalfSize, Tuning.ArenaCornerRadius, Tuning.ArenaMargin);
            for (int j = 0; j < g.Size; j++)
            {
                for (int i = 0; i < g.Size; i++)
                {
                    Vec2d c = g.CellCenter(i, j);
                    if (keep != null && !keep(c)) continue;
                    if (arena.SignedDistance(c) <= -depth) g.Set(g.Index(i, j), owner);
                }
            }
        }

        /// <summary>
        /// Player 0: the RimFollower on the block deeper than 2 u. Player 1: a disc of 1.7 u at the center painted over the
        /// block, where its HomeCircler (orbit 1.5 u) stays home forever (about 0.23 % of the conquerable cells).
        /// </summary>
        private static Simulation BuildWithRivalDisc(SimConfig config)
        {
            var setup = new SimSetup
            {
                PlayerCount = 2,
                StartPositions = new[] { V(-10, -10), V(0.0625, 0.0625) },
                StartHeadings = new[] { East, East },
                Territory = g =>
                {
                    FillInner(g, 1, 2.0, null);
                    g.FillDisc(V(0.0625, 0.0625), 1.7, 2);
                },
                HumanIndex = -1,
            };
            return new Simulation(config, new IController[] { new RimFollower(), new HomeCirclerController(V(0.0625, 0.0625)) }, setup);
        }

        /// <summary>
        /// A non-convex country: a main body with a notch, and an island of 16 x 5 u joined by a neck 0.6 u wide (narrower
        /// than 2 x ArenaMargin, so no head can pass it). One RimFollower player owning the body deeper than 2 u.
        /// </summary>
        private static Simulation NeckCountry(double share, out EventLog log)
        {
            Vec2d[] outline =
            {
                V(-24, -22), V(22, -22), V(22, -4), V(8, -4), V(8, 6), V(22, 6), V(22, 20), V(2.6, 20), V(2.6, 23),
                V(10, 23), V(10, 28), V(-6, 28), V(-6, 23), V(2, 23), V(2, 20), V(-24, 20),
            };
            var polygon = new ArenaPolygon(outline, V(0, 0));
            SimConfig config = SimTestKit.Config(60);
            config.ArenaBoundary = polygon;
            config.RoundDuration = 400.0;
            config.ConquestShare = share;
            var arena = new Arena(config.ArenaHalfSize, config.ArenaCornerRadius, config.ArenaMargin, polygon);
            var setup = new SimSetup
            {
                PlayerCount = 1,
                StartPositions = new[] { V(-10, -10) },
                StartHeadings = new[] { East },
                Territory = g => FillInner(g, 1, 2.0, c => c.Y < 19.0, arena),
                HumanIndex = -1,
            };
            var sim = new Simulation(config, new IController[] { new RimFollower() }, setup);
            log = new EventLog(sim);
            return sim;
        }

        /// <summary>Writes the conquest figures of a player; returns the conquerable cells it does not own.</summary>
        private static int Report(string label, Simulation sim, int player)
        {
            OwnerGrid g = sim.Grid;
            byte id = sim.Players[player].Id;
            int missing = 0, outside = 0;
            for (int k = 0; k < g.Cells.Length; k++)
            {
                bool c = sim.IsConquerable(k);
                if (c && g.Cells[k] != id) missing++;
                if (!c && g.Cells[k] == id) outside++;
            }
            TestContext.WriteLine(label + ": reason " + (sim.Result != null ? sim.Result.Reason.ToString() : "none") + " at t = "
                                  + sim.Time.ToString("F2") + " s, conquest " + sim.ConquestPercent(player).ToString("F3")
                                  + " %, conquerable " + sim.ConquestCellCount + ", target " + sim.ConquestTargetCells
                                  + ", conquerable cells not owned " + missing + ", owned rim cells outside the mask " + outside
                                  + ", R20 area " + sim.AreaPercent(player).ToString("F2") + " %");
            return missing;
        }

        private static string Tail(EventLog log)
        {
            string dump = log.Dump();
            return dump.Length > 3000 ? dump.Substring(dump.Length - 3000) : dump;
        }
    }
}
