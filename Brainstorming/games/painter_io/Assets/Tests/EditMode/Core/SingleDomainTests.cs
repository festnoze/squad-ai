// Owned by domain (rule v1.8, contract section 32, test id R23): single domain in every round type. A return whose capture
// would leave the returner's domain in pieces (a trail from one piece to another, a lasso pocket or a region that touches
// only the trail) takes the band of its trail, so the domain stays ONE 8-connected region; SimConfig.SingleDomain = Off
// restores the pre-v1.8 behaviour. Pure NUnit + PainterIO.Core (no UnityEngine), NUnit 3.5 features only.
//
// Geometry (contract 10.0 item 2, SimTestKit conventions: integer coordinates are cell edges, n + H is a cell-center line).
// Link scenario: player 0 owns two separate pieces A = [-12, -4] x [-4, 4] and B = [4, 12] x [-4, 4] (a domain cut in two,
// the designer's report) and drives East on y = H from (-4.9375, 0.0625): exit at x = -4 (t = 0.15625), entry into B at
// x = 4 (t = 8.9375 / 6). With rival, player 2 owns C = [-2, 2] x [-9, 9] across that path and circles at home around (0, 5).
// Pocket scenario: player 0 owns A, is charged and runs E 9, N 6, E 4, N 3, W 2, S 7, W 12 from (-4.9375, 0.5625): the S leg
// crosses the E 4 leg at X = (6.0625, 6.5625) (lasso pocket [6.0625, 8.0625] x [6.5625, 9.5625], far from A), the W leg
// crosses the N 6 leg at (4.0625, 2.5625) and enters A at x = -4: the ordinary capture is the strip x in [-4, 4.0625],
// y in [0.5625, 2.5625] (attached), the pocket is not.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class SingleDomainTests
    {
        private const double LinkTime = 8.9375 / 6.0;
        /// <summary>The W leg starts at 31/6 s at x = 6.0625 and enters A at x = -4.</summary>
        private const double PocketReturn = (31.0 + 10.0625) / 6.0;

        // ------------------------------------------------------------------------------------------------------------
        // Scenario builders

        private static Simulation Link(int rate, SingleDomainRule rule, bool rival = false, IController driver = null)
        {
            var sb = new SimBuilder(rate);
            sb.Config.SingleDomain = rule;
            sb.Add(V(-5 + H, H), East, driver ?? Legs((East, 30)), (g, id) =>
            {
                FillRect(g, id, -12, -4, -4, 4);
                FillRect(g, id, 4, -4, 12, 4);
            });
            sb.AddIdle(IdleCorners[1]);
            if (rival) sb.AddRect(-2, -9, 2, 9, V(0, 6.5), West, new HomeCirclerController(V(0, 5)));
            else sb.AddIdle(IdleCorners[2]);
            sb.AddIdle(IdleCorners[3]);
            return sb.Build();
        }

        private static Simulation Pocket(int rate, SingleDomainRule rule)
        {
            var sb = new SimBuilder(rate);
            sb.Config.SingleDomain = rule;
            sb.AddRect(-12, -4, -4, 4, V(-5 + H, 0.5 + H), East,
                       Legs((East, 9), (North, 6), (East, 4), (North, 3), (West, 2), (South, 7), (West, 12), (South, 20)));
            sb.AddIdle(IdleCorners[1]);
            sb.AddIdle(IdleCorners[2]);
            sb.AddIdle(IdleCorners[3]);
            Simulation sim = sb.Build();
            sim.DebugSetCharged(0, true);
            return sim;
        }

        private static int Pieces(Simulation sim, int player) => InheritanceBridgeTests.PieceCounts(sim.Grid, sim.Players.Count)[player + 1];

        private static byte Owner(Simulation sim, double x, double y) => sim.Grid.Cells[CellIndex(sim.Grid, x, y)];

        private static void AssertOneDomain(Simulation sim, string at) => InheritanceBridgeTests.AssertSingleDomain(sim, at);

        // ------------------------------------------------------------------------------------------------------------
        // 1. The designer's report: joining the two parts does not close the loop (Off), the link (default)

        [Test]
        public void R23_ReproductionOffAJoinBetweenTwoPiecesCapturesNothing()
        {
            Simulation sim = Link(60, SingleDomainRule.Off);
            var log = new EventLog(sim);
            RunUntilTime(sim, LinkTime + 0.05);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.That(ret.Time, Is.EqualTo(LinkTime).Within(1e-6));
            Assert.AreEqual(0, ret.Cells.Length, "Off: a trail from one piece to the other encloses nothing (the report)");
            Assert.AreEqual(2, Pieces(sim, 0), "Off: the domain stays in two pieces");
            Assert.AreEqual(OwnerGrid.Neutral, Owner(sim, 0, H), "Off: the trail did not become domain");
            Assert.AreEqual(0, sim.Players[0].DomainLinks);
        }

        [Test]
        public void R23_AJoinBetweenTwoPiecesBecomesABandOfTerritory()
        {
            TraitTestKit.CrossRate("link", rate => Link(rate, SingleDomainRule.On), LinkTime + 0.05, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                byte id = sim.Players[0].Id;
                SimEvent ret = run.Log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(LinkTime).Within(1e-6), at + "return into B");
                Assert.IsFalse(ret.Chased);
                Assert.That(ret.Cells.Length, Is.GreaterThan(400), at + "the band is the capture");
                Assert.AreEqual(1, Pieces(sim, 0), at + "one domain");
                Assert.AreEqual(1, sim.Players[0].DomainLinks, at + "one link");
                // 7 cells across the band (cells whose center lies within 0.45 u of the line y = H), never one.
                for (double x = -3.5; x <= 3.5; x += 1.0)
                {
                    int across = 0;
                    for (int j = -6; j <= 6; j++)
                    {
                        if (Owner(sim, x + H, H + j * 0.125) == id) across++;
                    }
                    Assert.AreEqual(7, across, at + "7 cells across the band at x = " + x);
                }
                Assert.IsTrue(sim.Players[0].Home);
            }, s => AssertOneDomainAfterLink(s));
        }

        private static void AssertOneDomainAfterLink(Simulation s)
        {
            if (s.Time > LinkTime + 1e-6) AssertOneDomain(s, "after the link: ");
        }

        [Test]
        public void R23_ABandOverARivalsLandIsACaptureAndTheRivalKeepsThePieceOfItsPawn()
        {
            TraitTestKit.CrossRate("link over a rival", rate => Link(rate, SingleDomainRule.On, true), LinkTime + 0.05, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                byte id = sim.Players[0].Id, c = sim.Players[2].Id;
                SimEvent ret = run.Log.Single(SimEventType.Return, 0);
                Assert.IsTrue(TraitTestKit.Contains(ret.Cells, CellIndex(sim.Grid, H, H)), at + "the band crosses C's land");
                Assert.AreEqual(id, Owner(sim, H, H));
                SimEvent severed = run.Log.Single(SimEventType.TerritorySevered, 2);
                Assert.AreEqual(0, severed.Other, at + "rule v1.5: the linker is the cutter");
                Assert.AreEqual(-1, severed.Recipient, at + "Neutral (default)");
                Assert.AreEqual(OwnerGrid.Neutral, Owner(sim, H, -5 + H), at + "C's south part (without its pawn) is severed");
                Assert.AreEqual(c, Owner(sim, H, 5 + H), at + "C keeps the piece of its pawn");
                Assert.AreEqual(1, Pieces(sim, 0));
                Assert.AreEqual(1, Pieces(sim, 2));
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // 2. A lasso pocket far from the domain

        [Test]
        public void R23_ReproductionOffADetachedPocketLeavesTwoPieces()
        {
            Simulation sim = Pocket(60, SingleDomainRule.Off);
            var log = new EventLog(sim);
            RunUntilTime(sim, PocketReturn + 0.1);
            Assert.AreEqual(1, log.Count(SimEventType.LassoPocket, 0), "the pocket was made");
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.That(ret.Cells.Length, Is.GreaterThan(0));
            Assert.AreEqual(sim.Players[0].Id, Owner(sim, 7 + H, 8 + H), "the pocket is captured");
            Assert.AreEqual(2, Pieces(sim, 0), "Off: the pocket is an island");
        }

        [Test]
        public void R23_ADetachedPocketIsLinkedByTheBandOfItsTrail()
        {
            TraitTestKit.CrossRate("pocket link", rate => Pocket(rate, SingleDomainRule.On), PocketReturn + 0.1, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                byte id = sim.Players[0].Id;
                Assert.AreEqual(1, run.Log.Count(SimEventType.LassoPocket, 0), at + "the pocket was made");
                Assert.AreEqual(1, run.Log.Count(SimEventType.Return, 0), at + "one return");
                Assert.IsTrue(sim.Players[0].Home);
                Assert.AreEqual(id, Owner(sim, 7 + H, 8 + H), at + "the pocket is captured");
                Assert.AreEqual(id, Owner(sim, 4 + H, 4.5 + H), at + "the North leg became land");
                Assert.AreEqual(id, Owner(sim, 5 + H, 6.5 + H), at + "the East leg up to the pocket became land");
                Assert.AreEqual(1, Pieces(sim, 0), at + "one domain");
                Assert.AreEqual(1, sim.Players[0].DomainLinks);
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // 3. Bots after a link, determinism, the switch

        private sealed class Switch : IController
        {
            private readonly IController first, then;
            private readonly double at;

            public Switch(IController first, double at, IController then)
            {
                this.first = first;
                this.at = at;
                this.then = then;
            }

            public double? DesiredHeading(SimView view, int playerIndex)
            {
                return view.Time < at - 1e-9 ? first.DesiredHeading(view, playerIndex) : then.DesiredHeading(view, playerIndex);
            }
        }

        [Test]
        public void R23_ABotKeepsFindingItsWayHomeAfterALink()
        {
            // The scripted legs make the link at LinkTime; a Balanced bot drives player 0 from t = 2 (home in B, now one
            // domain with the band and A). It must keep making excursions and coming home, the domain one piece.
            var bot = new BotController(BotPersonality.Preset(BotStyle.Balanced), 5UL);
            Simulation sim = Link(60, SingleDomainRule.On, false, new Switch(Legs((East, 30)), 2.0, bot));
            var log = new EventLog(sim);
            double outSince = double.NaN, longest = 0.0;
            RunUntilTime(sim, 30.0, true, s =>
            {
                if (s.Time > LinkTime + 1e-6) AssertOneDomain(s, "bot after the link: ");
                PlayerState p = s.Players[0];
                if (!p.Home && double.IsNaN(outSince)) outSince = s.Time;
                if (p.Home && !double.IsNaN(outSince))
                {
                    longest = Math.Max(longest, s.Time - outSince);
                    outSince = double.NaN;
                }
            });
            Assert.IsTrue(sim.Players[0].Alive, "nobody can reach it");
            int captures = 0;
            foreach (SimEvent e in log.Of(SimEventType.Return, 0))
            {
                if (e.Time > 2.0 && e.Cells.Length > 0) captures++;
            }
            Assert.That(captures, Is.GreaterThanOrEqualTo(3), "the bot keeps capturing after the link");
            Assert.That(longest, Is.LessThan(10.0), "every excursion ends");
        }

        [Test]
        public void R23_SameSeedSameHashWithLinks()
        {
            Simulation a = TraitTestKit.BotRound(3UL, RuleTraits.Classic, false), b = TraitTestKit.BotRound(3UL, RuleTraits.Classic, false);
            while (!a.Ended)
            {
                a.Step();
                b.Step();
                if (a.Tick % 15 == 0 || a.Ended) Assert.AreEqual(a.StateHash(), b.StateHash(), "twin StateHash at tick " + a.Tick);
            }
            int links = 0;
            for (int i = 0; i < 4; i++) links += a.Players[i].DomainLinks;
            TestContext.WriteLine("links in the twin round: " + links);
        }

        [Test]
        public void R23_TheRuleHoldsInEveryRoundTypeAndOffRestoresThePreV18Switch()
        {
            var cfg = new SimConfig();
            Assert.AreEqual(SingleDomainRule.On, cfg.SingleDomain, "On is the default");
            Assert.AreEqual(0, (int)SingleDomainRule.Off);
            foreach (RuleTraits traits in new[] { RuleTraits.Classic, TraitTestKit.LiquidV11, TraitTestKit.FireV11, TraitTestKit.ElectricV11 })
            {
                Assert.IsTrue(new Simulation(new SimConfig { Traits = traits }, new IController[] { null, null }).View.SingleDomain,
                              "v1.8: " + traits.ToKey());
            }
            Assert.IsFalse(new Simulation(new SimConfig { SingleDomain = SingleDomainRule.Off }, new IController[] { null, null }).View.SingleDomain,
                           "Off: classic has no guarantee (pre-v1.8)");
            Assert.IsTrue(new Simulation(new SimConfig { SingleDomain = SingleDomainRule.Off, Traits = TraitTestKit.FireV11 },
                                         new IController[] { null, null }).View.SingleDomain, "Off: the v1.6 Feu rule stays");
        }

        /// <summary>
        /// Rolling hashes (TraitTestKit.RollingRoundHash every 30 ticks) of v1.1 biome bot rounds: SingleDomain = Off (the
        /// pre-v1.8 rules) and the default (rule v1.8). The Feu rows are the rounds of InheritanceBridgeTests.FireRows.
        /// </summary>
        private static readonly object[] BiomeRows =
        {
            new object[] { "Liquide v1.1", 1UL, 60, true, 0x919D60BB084C34C4UL, 0xA5DA3E9225B83D0DUL },
            new object[] { "Electricite v1.1", 2UL, 60, false, 0x06CEAB293AB96B3CUL, 0x490D14DA9896513CUL },
            new object[] { "Feu v1.1", 1UL, 60, true, 0x6A081F4785E9DCEBUL, 0x6A081F4785E9DCEBUL },
            new object[] { "Feu v1.1", 3UL, 60, false, 0x3B68A996FF6CCED3UL, 0xC33B24C3C6D51695UL },
            new object[] { "Feu v1.1", 4UL, 30, true, 0x444396D4DF17FBAAUL, 0x8BD70059B541DD05UL },
            new object[] { "Feu v1.1", 5UL, 144, true, 0xFABA4ABCAD0A5181UL, 0x9EB4402BCB65ACABUL },
        };

        private static RuleTraits SetNamed(string name)
        {
            if (name.StartsWith("Liquide", StringComparison.Ordinal)) return TraitTestKit.LiquidV11;
            if (name.StartsWith("Electricite", StringComparison.Ordinal)) return TraitTestKit.ElectricV11;
            return TraitTestKit.FireV11;
        }

        [TestCaseSource(nameof(BiomeRows))]
        public void R23_BiomeRoundHashesOffAndDefault(string set, ulong seed, int rate, bool lasso, ulong off, ulong v17)
        {
#if UNITY_5_3_OR_NEWER
            if (seed > 1UL) return;
#endif
            RuleTraits traits = SetNamed(set);
            var config = new SimConfig { Seed = seed, TickRate = rate, LassoEnabled = lasso, Traits = traits, SingleDomain = SingleDomainRule.Off };
            var controllers = new IController[4];
            for (int i = 0; i < 4; i++)
                controllers[i] = new BotController(BotPersonality.Preset(TraitTestKit.Lineup[i]), BotTests.BotSeed(seed, i));
            var offRound = new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
            Assert.AreEqual(off.ToString("X16"), TraitTestKit.RollingRoundHash(offRound, 30, false).ToString("X16"), set + ": SingleDomain = Off");
            Assert.AreEqual(v17.ToString("X16"), TraitTestKit.RollingRoundHash(TraitTestKit.BotRound(seed, traits, lasso, rate), 30, false).ToString("X16"),
                            set + ": the default (rule v1.8)");
        }
    }
}
