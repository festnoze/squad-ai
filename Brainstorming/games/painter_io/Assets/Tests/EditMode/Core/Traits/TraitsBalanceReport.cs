// Owned by traits-core (wave D-1), updated by kill-core (wave D-2). docs/BIOME_TRAITS.md section 6 balance report: bot-only
// rounds, 50 seeds per biome default set and in classic mode. Asserted only for safety (no exception, invariants every
// tick, TimeUp in >= 40 % of the rounds); every other figure is reported (TestContext output, copied into the wave D
// reports) and compared with the expected tendencies: Feu has the highest kill share per cut and the highest passive
// growth; Electricite has the most cuts and the most saved chases; Liquide stays closest to classic.
// Since wave D-2 the default sets are the v1.1 table (section 3 + section 7: Feu + KillInheritance, Electricite +
// KillSpeedBoost, Liquide + KillShield) and the report adds the kill reward figures, among them the swing section 7.2
// asks for (TimeUp rounds won by less than the winner's largest single inheritance, and lead flips by an inheritance).
// Lasso off is the runtime default (SaveData.LassoOn); the lasso-on figures are reported by a second case. The [Explicit]
// diagnostic case adds the D-1 proposals (Liquide Inertia 480, Feu SparkSpeed 2.3), the section 3 sets and each kill trait
// alone (run it with --filter "FullyQualifiedName~TraitsBalance_Diagnostics").
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Text;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    public class TraitsBalanceReport
    {
#if UNITY_5_3_OR_NEWER
        private const int Seeds = 2;   // Editor Mono: safety only (no exception, invariants every tick)
#else
        private const int Seeds = 50;
#endif

        internal sealed class SetStats
        {
            public string Name;
            public int Rounds, TimeUps, Cuts, Kills, SavedChases, Eliminations, SparkEliminations, Returns, Captures;
            public long CapturedCells, GrownCells, AliveTicks;
            public double Coverage, EndTime, WallSeconds;
            public double[] CapturesPerPlayer = new double[4];

            // Kill rewards (section 7).
            public int Inheritances, Boosts, Shields, Extinguished, LeadFlips, RoundsWithFlip, DecidedByOneKill, TimeUpDuels;
            public long InheritedCells;

            public double CapturesPerBot => Captures / (4.0 * Rounds);
            public double CutsPerRound => Cuts / (double)Rounds;
            public double KillShare => Cuts > 0 ? Kills / (double)Cuts : 0.0;
            public double SavedPerRound => SavedChases / (double)Rounds;
            public double MeanCoverage => Coverage / Rounds;
            public double EliminationsPerRound => Eliminations / (double)Rounds;
            public double MeanEndTime => EndTime / Rounds;
            public double ReturnsPerBotMinute => AliveTicks > 0 ? Returns / (AliveTicks / 3600.0) : 0.0;
            public double CellsPerCapture => Captures > 0 ? CapturedCells / (double)Captures : 0.0;
            public double GrowthPercentPerRound(int arenaCells) => 100.0 * GrownCells / Rounds / arenaCells;
            public double TimeUpShare => TimeUps / (double)Rounds;
            public double InheritedPercentPerKill(int arenaCells) => Inheritances > 0 ? 100.0 * InheritedCells / Inheritances / arenaCells : 0.0;
            public double DecidedShare => TimeUpDuels > 0 ? DecidedByOneKill / (double)TimeUpDuels : 0.0;
        }

        internal static SetStats RunSet(string name, RuleTraits traits, int seeds, bool lasso)
        {
            var s = new SetStats { Name = name };
            var watch = Stopwatch.StartNew();
            for (int k = 1; k <= seeds; k++)
            {
                Simulation sim = TraitTestKit.BotRound((ulong)k, traits, lasso);
                var largestInheritance = new int[4];
                bool flipped = false;
                sim.EventRaised += e =>
                {
                    switch (e.Type)
                    {
                        case SimEventType.Cut: s.Cuts++; break;
                        case SimEventType.SparkCaught: s.Kills++; break;
                        case SimEventType.Eliminated:
                            s.Eliminations++;
                            if (e.Cause == EliminationCause.Spark) s.SparkEliminations++;
                            break;
                        case SimEventType.Return:
                            s.Returns++;
                            if (e.Chased) s.SavedChases++;
                            if (e.Cells.Length > 0)
                            {
                                s.Captures++;
                                s.CapturesPerPlayer[e.Player]++;
                                s.CapturedCells += e.Cells.Length;
                            }
                            break;
                        case SimEventType.TerritoryGrew: s.GrownCells += e.Cells.Length; break;
                        case SimEventType.TerritoryInherited:
                        {
                            s.Inheritances++;
                            s.InheritedCells += e.Cells.Length;
                            if (e.Cells.Length > largestInheritance[e.Player]) largestInheritance[e.Player] = e.Cells.Length;
                            // Lead flip: the killer was not the strict leader among the alive players before the inheritance
                            // and is after it.
                            int after = sim.Grid.CountOf(sim.Players[e.Player].Id), before = after - e.Cells.Length, best = 0;
                            for (int i = 0; i < 4; i++)
                            {
                                if (i != e.Player && sim.Players[i].Alive) best = Math.Max(best, sim.Grid.CountOf(sim.Players[i].Id));
                            }
                            if (before <= best && after > best)
                            {
                                s.LeadFlips++;
                                flipped = true;
                            }
                            break;
                        }
                        case SimEventType.SpeedBoosted: s.Boosts++; break;
                        case SimEventType.ShieldStarted:
                            s.Shields++;
                            if (e.Chased) s.Extinguished++;
                            break;
                    }
                };
                while (!sim.Ended)
                {
                    sim.Step();
                    TraitTestKit.AssertTraitInvariants(sim);
                    for (int i = 0; i < 4; i++)
                    {
                        if (sim.Players[i].Alive) s.AliveTicks++;
                    }
                }
                s.Rounds++;
                if (flipped) s.RoundsWithFlip++;
                if (sim.Result.Reason == RoundEndReason.TimeUp) s.TimeUps++;
                s.EndTime += sim.Result.EndTime;
                long owned = 0;
                for (int i = 0; i < 4; i++) owned += sim.Grid.CountOf(sim.Players[i].Id);
                s.Coverage += 100.0 * owned / sim.Grid.ArenaCellCount;

                // Swing (section 7.2): a TimeUp round with a single winner and at least one other survivor is "decided by
                // one kill" when the winner's margin over the best other survivor is smaller than its largest inheritance.
                if (sim.Result.Reason == RoundEndReason.TimeUp && sim.Result.Winners.Count == 1)
                {
                    int w = sim.Result.Winners[0], runnerUp = -1;
                    for (int i = 0; i < 4; i++)
                    {
                        if (i != w && sim.Players[i].Alive) runnerUp = Math.Max(runnerUp, sim.Result.FinalCells[i]);
                    }
                    if (runnerUp >= 0)
                    {
                        s.TimeUpDuels++;
                        if (largestInheritance[w] > sim.Result.FinalCells[w] - runnerUp) s.DecidedByOneKill++;
                    }
                }
            }
            for (int i = 0; i < 4; i++) s.CapturesPerPlayer[i] /= seeds;
            s.WallSeconds = watch.Elapsed.TotalSeconds;
            return s;
        }

        private static string Row(SetStats s, int arenaCells)
        {
            CultureInfo ci = CultureInfo.InvariantCulture;
            return string.Format(ci,
                "{0,-17} captures/bot {1,5:F2} [{2}]  cuts/round {3,5:F2}  kill share {4,5:P0}  saved/round {5,4:F2}  coverage {6,5:F1} %  "
                + "elims/round {7,4:F2}  end {8,5:F1} s  returns/bot-min {9,4:F1}  cells/capture {10,6:F0}  growth {11,5:F1} %/round  TimeUp {12,4:P0}  ({13:F1} s)",
                s.Name, s.CapturesPerBot, string.Join(" ", Array.ConvertAll(s.CapturesPerPlayer, v => v.ToString("F1", ci))), s.CutsPerRound,
                s.KillShare, s.SavedPerRound, s.MeanCoverage, s.EliminationsPerRound, s.MeanEndTime, s.ReturnsPerBotMinute,
                s.CellsPerCapture, s.GrowthPercentPerRound(arenaCells), s.TimeUpShare, s.WallSeconds);
        }

        private static string KillRow(SetStats s, int arenaCells)
        {
            CultureInfo ci = CultureInfo.InvariantCulture;
            return string.Format(ci,
                "{0,-17} kills/round {1,4:F2}  inherit/round {2,4:F2} ({3,4:F1} % arena each)  rounds with a lead flip {4,4:P0}  "
                + "TimeUp duels decided by one kill {5,4:P0} ({6}/{7})  boosts/round {8,4:F2}  shields/round {9,4:F2}  sparks extinguished/round {10,4:F2}",
                s.Name, s.Kills / (double)s.Rounds, s.Inheritances / (double)s.Rounds, s.InheritedPercentPerKill(arenaCells),
                s.RoundsWithFlip / (double)s.Rounds, s.DecidedShare, s.DecidedByOneKill, s.TimeUpDuels, s.Boosts / (double)s.Rounds,
                s.Shields / (double)s.Rounds, s.Extinguished / (double)s.Rounds);
        }

        /// <summary>Relative distance to classic over the main metrics (mean of |m - m_classic| / max(|m_classic|, eps)).</summary>
        internal static double DistanceToClassic(SetStats s, SetStats c)
        {
            double[] a = { s.CapturesPerBot, s.CutsPerRound, s.KillShare, s.SavedPerRound, s.MeanCoverage, s.EliminationsPerRound, s.MeanEndTime, s.CellsPerCapture };
            double[] b = { c.CapturesPerBot, c.CutsPerRound, c.KillShare, c.SavedPerRound, c.MeanCoverage, c.EliminationsPerRound, c.MeanEndTime, c.CellsPerCapture };
            double sum = 0.0;
            for (int k = 0; k < a.Length; k++) sum += Math.Abs(a[k] - b[k]) / Math.Max(Math.Abs(b[k]), 1e-6);
            return sum / a.Length;
        }

        /// <summary>The five section 6 tendencies for one (classic, liquid, fire, electric) quadruple.</summary>
        private static string Tendencies(SetStats classic, SetStats liquid, SetStats fire, SetStats electric)
        {
            CultureInfo ci = CultureInfo.InvariantCulture;
            Func<bool, string> ok = b => b ? "MET" : "MISSED";
            bool fireKill = fire.KillShare > liquid.KillShare && fire.KillShare > electric.KillShare && fire.KillShare > classic.KillShare;
            bool fireGrowth = fire.GrownCells > liquid.GrownCells && fire.GrownCells > electric.GrownCells;
            bool elecCuts = electric.CutsPerRound > Math.Max(Math.Max(classic.CutsPerRound, liquid.CutsPerRound), fire.CutsPerRound);
            bool elecSaved = electric.SavedPerRound > Math.Max(Math.Max(classic.SavedPerRound, liquid.SavedPerRound), fire.SavedPerRound);
            double dL = DistanceToClassic(liquid, classic), dF = DistanceToClassic(fire, classic), dE = DistanceToClassic(electric, classic);
            bool liquidClosest = dL < dF && dL < dE;
            return "Tendencies (" + liquid.Name + " / " + fire.Name + " / " + electric.Name + "): Feu highest kill share per cut " + ok(fireKill)
                   + "; Feu highest passive growth " + ok(fireGrowth)
                   + "; Electricite most cuts " + ok(elecCuts)
                   + "; Electricite most saved chases " + ok(elecSaved)
                   + "; Liquide closest to classic " + ok(liquidClosest)
                   + string.Format(ci, " (distance L {0:F3}, F {1:F3}, E {2:F3})", dL, dF, dE);
        }

        private static int ArenaCells()
        {
            return new OwnerGrid(new Arena(Tuning.ArenaHalfSize, Tuning.ArenaCornerRadius, Tuning.ArenaMargin), Tuning.CellSize).ArenaCellCount;
        }

        private static string Report(string title, List<SetStats> sets, int arena, IEnumerable<SetStats[]> quadruples)
        {
            var sb = new StringBuilder();
            sb.Append(title).Append('\n');
            foreach (SetStats s in sets) sb.Append(Row(s, arena)).Append('\n');
            foreach (SetStats s in sets) sb.Append(KillRow(s, arena)).Append('\n');
            foreach (SetStats[] q in quadruples) sb.Append(Tendencies(q[0], q[1], q[2], q[3])).Append('\n');
            return sb.ToString();
        }

        [TestCase(false)]
        [TestCase(true)]
        public void TraitsBalance_BotOnlyRoundsPerBiomeSet(bool lasso)
        {
#if !UNITY_5_3_OR_NEWER
            // The lasso-on case is reported on 20 seeds to keep the dotnet loop short; lasso off (the runtime default) on 50.
            int seeds = lasso ? 20 : Seeds;
#else
            int seeds = Seeds;
#endif
            var sets = new List<SetStats>
            {
                RunSet("Classic", RuleTraits.Classic, seeds, lasso),
                RunSet("Liquide v1.1", TraitTestKit.LiquidV11, seeds, lasso),
                RunSet("Feu v1.1", TraitTestKit.FireV11, seeds, lasso),
                RunSet("Electricite v1.1", TraitTestKit.ElectricV11, seeds, lasso),
            };
            int arena = ArenaCells();
            string title = "Balance report (v1.1 defaults), bot-only, " + seeds + " seeds per set, lasso " + (lasso ? "on" : "off");
            TestContext.WriteLine(Report(title, sets, arena, new[] { new[] { sets[0], sets[1], sets[2], sets[3] } }));

            // Safety only (section 6): no exception and the invariants were checked every tick above; TimeUp >= 40 %.
            foreach (SetStats s in sets)
            {
                Assert.AreEqual(seeds, s.Rounds, s.Name);
#if !UNITY_5_3_OR_NEWER
                Assert.That(s.TimeUpShare, Is.GreaterThanOrEqualTo(0.40), s.Name + ": share of rounds reaching TimeUp");
#endif
            }
        }

        /// <summary>
        /// Diagnostic (explicit, reported only): the v1.1 defaults with and without the D-1 proposals (Liquide Inertia 480,
        /// Feu SparkSpeed 2.3), the section 3 sets (before section 7) and each kill trait alone, so the effect of every
        /// change can be read against classic.
        /// </summary>
        [TestCase(false)]
        [TestCase(true)]
        [Explicit("diagnostic balance runs (several minutes): run with --filter FullyQualifiedName~TraitsBalance_Diagnostics")]
        public void TraitsBalance_Diagnostics(bool lasso)
        {
            int seeds = lasso ? 20 : Seeds;
            var sets = new List<SetStats>
            {
                RunSet("Classic", RuleTraits.Classic, seeds, lasso),
                RunSet("Liquide v1.1", TraitTestKit.LiquidV11, seeds, lasso),
                RunSet("Feu v1.1", TraitTestKit.FireV11, seeds, lasso),
                RunSet("Electricite v1.1", TraitTestKit.ElectricV11, seeds, lasso),
                RunSet("Liquide v1.1 I480", TraitTestKit.LiquidV11Proposal, seeds, lasso),
                RunSet("Feu v1.1 SS2.3", TraitTestKit.FireV11Proposal, seeds, lasso),
                RunSet("Liquide s3", TraitTestKit.Liquid, seeds, lasso),
                RunSet("Feu s3", TraitTestKit.Fire, seeds, lasso),
                RunSet("Electricite s3", TraitTestKit.Electric, seeds, lasso),
                RunSet("KillInheritance", TraitTestKit.One(TraitId.KillInheritance), seeds, lasso),
                RunSet("KillSpeedBoost", TraitTestKit.One(TraitId.KillSpeedBoost), seeds, lasso),
                RunSet("KillShield", TraitTestKit.One(TraitId.KillShield), seeds, lasso),
                RunSet("Feu v1.1 Share0.5", TraitTestKit.FireV11.With(new TraitSpec(TraitId.KillInheritance, 0.5)), seeds, lasso),
                RunSet("Feu SS2.3 Share0.5", TraitTestKit.FireV11Proposal.With(new TraitSpec(TraitId.KillInheritance, 0.5)), seeds, lasso),
            };
            int arena = ArenaCells();
            string title = "Balance diagnostics, bot-only, " + seeds + " seeds per set, lasso " + (lasso ? "on" : "off");
            var quadruples = new[]
            {
                new[] { sets[0], sets[1], sets[2], sets[3] },   // v1.1 defaults
                new[] { sets[0], sets[4], sets[5], sets[3] },   // v1.1 + D-1 proposals
                new[] { sets[0], sets[4], sets[2], sets[3] },   // v1.1 + Liquide proposal only
                new[] { sets[0], sets[6], sets[7], sets[8] },   // section 3 (wave D-1 defaults)
            };
            var sb = new StringBuilder(Report(title, sets, arena, quadruples));
            CultureInfo ci = CultureInfo.InvariantCulture;
            foreach (SetStats s in sets)
                sb.Append(string.Format(ci, "distance to classic {0,-17} {1:F3}\n", s.Name, DistanceToClassic(s, sets[0])));
            TestContext.WriteLine(sb.ToString());
            foreach (SetStats s in sets) Assert.AreEqual(seeds, s.Rounds, s.Name);
        }
    }
}
