// Owned by A5 (bots). Contract 10.1 "Bots" and section 9: seeded bot-only rounds (asserted targets), invariants every
// tick, and decision-level behaviour of the bot FSM. Pure NUnit + PainterIO.Core (no UnityEngine), NUnit 3.5 features
// only, so the file also runs in Unity EditMode (where the round test runs 10 seeds and asserts only no exception and
// the invariants, contract 10.1).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Text;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    public class BotTests
    {
        // ------------------------------------------------------------------------------------------------------------
        // Round runner shared by the tests

        /// <summary>Bot-only lineup of the target test: the human slot (player 0) is a Balanced bot, then the section 9
        /// presets (player 1 Balanced, player 2 Greedy, player 3 Aggressive).</summary>
        internal static readonly BotStyle[] BotOnlyLineup = { BotStyle.Balanced, BotStyle.Balanced, BotStyle.Greedy, BotStyle.Aggressive };

        internal sealed class RoundStats
        {
            public ulong Seed;
            public RoundEndReason Reason;
            public double EndTime;
            public int[] Captures;          // Return events that captured at least one cell, per player
            public int[] Returns;           // all Return events, per player
            public int ChasedReturns;       // saved returns (Chased): contract 24, they capture nothing
            public int ChasedCaptures;      // chased returns with cells: must stay 0 (contract 24)
            public int Cuts;
            public int SparkEliminations;
            public int EscapableSparkEliminations;
            public int TerritoryLostEliminations;
            public int Pockets;
            public int AttackStarts;        // entries into Attack mode
            public int DeliberateCuts;      // Cut events dealt while the attacker was in Attack mode on that victim
            public int DeliberateKills;     // Spark eliminations from such cuts
            public int[] Deaths;            // Spark eliminations per victim
            public int[] KillsBy;           // Spark eliminations per attacker
            public double Coverage;         // owned cells of all players / arena cells at the end, in percent
            public long[] AliveTicks;
            public long[] TrailingTicks;
            public long HeldTicks;          // ticks where an alive bot did not move (held against the border, R4)
            public bool[] AliveAtEnd;
            public int[] Ranks;
            public int Decisions;
            public double DecisionSeconds;
            public double MaxDecisionSeconds;
            public List<double> DecisionSamples = new List<double>();
        }

        /// <summary>
        /// Wraps a BotController: times every decision (a call during which DecisionCount moved) and checks that the
        /// call mutated nothing reachable from the SimView (fingerprint of every mutable field before and after).
        /// </summary>
        internal sealed class ProbeController : IController
        {
            public readonly BotController Bot;
            public int Decisions, AttackStarts;
            public double DecisionSeconds, MaxDecisionSeconds;
            public List<double> Samples;
            public string Violation;
            private readonly bool guard;

            public ProbeController(BotController bot, bool guardMutations, List<double> samples)
            {
                Bot = bot;
                guard = guardMutations;
                Samples = samples;
            }

            public double? DesiredHeading(SimView view, int playerIndex)
            {
                ulong before = guard ? Fingerprint(view) : 0UL;
                int d0 = Bot.DecisionCount;
                bool wasAttacking = Bot.Mode == BotMode.Attack;
                long t0 = Stopwatch.GetTimestamp();
                double? result = Bot.DesiredHeading(view, playerIndex);
                long t1 = Stopwatch.GetTimestamp();
                if (!wasAttacking && Bot.Mode == BotMode.Attack) AttackStarts++;
                if (Bot.DecisionCount != d0)
                {
                    double s = (t1 - t0) / (double)Stopwatch.Frequency;
                    Decisions++;
                    DecisionSeconds += s;
                    if (s > MaxDecisionSeconds) MaxDecisionSeconds = s;
                    Samples?.Add(s);
                }
                if (guard && Violation == null && Fingerprint(view) != before)
                    Violation = "player " + playerIndex + " mutated the view at t=" + view.Time.ToString("R", CultureInfo.InvariantCulture);
                if (result.HasValue && (double.IsNaN(result.Value) || double.IsInfinity(result.Value)))
                    Violation = Violation ?? "player " + playerIndex + " returned a non-finite heading";
                return result;
            }
        }

        /// <summary>Hash of every mutable field reachable from the view (grid and trail Versions stand for their content).</summary>
        internal static ulong Fingerprint(SimView view)
        {
            ulong h = 1469598103934665603UL;
            h = Mix(h, view.Grid.Version);
            Ring ring = view.Ring;
            if (ring != null)
            {
                h = Mix(h, ring.Pos.X);
                h = Mix(h, ring.Pos.Y);
                h = Mix(h, ring.SpawnTime);
            }
            for (int i = 0; i < view.PlayerCount; i++)
            {
                PlayerState p = view.Player(i);
                h = Mix(h, p.Pos.X);
                h = Mix(h, p.Pos.Y);
                h = Mix(h, p.PrevPos.X);
                h = Mix(h, p.PrevPos.Y);
                h = Mix(h, p.Cell);
                h = Mix(h, p.Heading);
                h = Mix(h, p.DesiredHeading);
                h = Mix(h, (p.Alive ? 1 : 0) | (p.Home ? 2 : 0) | (p.Charged ? 4 : 0) | (p.IsHuman ? 8 : 0));
                h = Mix(h, p.Trail.Version);
                h = Mix(h, p.Trail.Count);
                h = Mix(h, p.Pocket.Version);
                h = Mix(h, p.Captures + 31 * p.CutsMade + 961 * p.Kills + 29791 * p.PocketsMade);
                h = Mix(h, p.FinalCells);
                h = Mix(h, p.EliminatedAt);
                if (p.Spark != null)
                {
                    h = Mix(h, p.Spark.SCut);
                    h = Mix(h, p.Spark.TimeCut);
                    h = Mix(h, p.Spark.S);
                    h = Mix(h, p.Spark.PrevS);
                    h = Mix(h, p.Spark.Attacker);
                }
            }
            return h;
        }

        private static ulong Mix(ulong h, double v) => Mix(h, BitConverter.DoubleToInt64Bits(v));

        private static ulong Mix(ulong h, long v)
        {
            unchecked
            {
                h ^= (ulong)v;
                h *= 1099511628211UL;
                h ^= h >> 29;
            }
            return h;
        }

        /// <summary>Distinct, deterministic bot seed per round seed and player.</summary>
        internal static ulong BotSeed(ulong roundSeed, int player) => roundSeed * 7919UL + (ulong)player * 104729UL + 17UL;

        internal static BotPersonality[] Lineup(BotStyle[] styles)
        {
            var result = new BotPersonality[styles.Length];
            for (int i = 0; i < styles.Length; i++) result[i] = BotPersonality.Preset(styles[i]);
            return result;
        }

        /// <summary>
        /// Runs one full round with one BotController per player, the 10.1 invariants after every tick (fast check that
        /// fails with Assert.Fail on the first violation), the mutation guard on every controller call, and the metrics
        /// of section 9.
        /// </summary>
        internal static RoundStats RunRound(ulong seed, BotPersonality[] lineup, int humanIndex, bool lasso, int tickRate = 60,
                                            List<double> decisionSamples = null, bool borderRide = false)
        {
            int n = lineup.Length;
            var config = new SimConfig { Seed = seed, TickRate = tickRate, LassoEnabled = lasso };
            if (borderRide) config.BorderRide = BorderRideRule.On;   // rule v1.9 (BorderRideTests)
            var probes = new ProbeController[n];
            var controllers = new IController[n];
            for (int i = 0; i < n; i++)
            {
                probes[i] = new ProbeController(new BotController(lineup[i], BotSeed(seed, i)), true, decisionSamples);
                controllers[i] = probes[i];
            }
            var sim = new Simulation(config, controllers, new SimSetup { HumanIndex = humanIndex });
            var stats = new RoundStats
            {
                Seed = seed,
                Captures = new int[n],
                Returns = new int[n],
                AliveTicks = new long[n],
                TrailingTicks = new long[n],
                AliveAtEnd = new bool[n],
                Deaths = new int[n],
                KillsBy = new int[n],
            };
            var escapable = new bool[n];
            var deliberate = new bool[n];
            double closing = sim.Config.SparkSpeed - sim.Config.PawnSpeed;
            sim.EventRaised += e =>
            {
                switch (e.Type)
                {
                    case SimEventType.Return:
                        stats.Returns[e.Player]++;
                        if (e.Cells != null && e.Cells.Length > 0) stats.Captures[e.Player]++;
                        if (e.Chased)
                        {
                            stats.ChasedReturns++;
                            if (e.Cells == null || e.Cells.Length > 0) stats.ChasedCaptures++;
                        }
                        break;
                    case SimEventType.Cut:
                    {
                        // Section 9 reported metric: escapable when (L - s_cut) / (SparkSpeed - PawnSpeed) >
                        // 1.3 x D_home / PawnSpeed + ReactionDelay, evaluated at the Cut event.
                        stats.Cuts++;
                        deliberate[e.Player] = e.Other >= 0 && probes[e.Other].Bot.Mode == BotMode.Attack && probes[e.Other].Bot.AttackVictim == e.Player;
                        if (deliberate[e.Player]) stats.DeliberateCuts++;
                        PlayerState v = sim.Players[e.Player];
                        double dHome = GridQueries.NearestOwned(sim.Grid, v.Id, v.Pos, 100, out _, out double dh) ? dh : double.PositiveInfinity;
                        double catchTime = (v.Trail.Length - e.S) / closing;
                        escapable[e.Player] = catchTime > 1.3 * dHome / sim.Config.PawnSpeed + lineup[e.Player].ReactionDelay;
                        break;
                    }
                    case SimEventType.SparkCaught:
                        stats.SparkEliminations++;
                        stats.Deaths[e.Player]++;
                        if (e.Other >= 0) stats.KillsBy[e.Other]++;
                        if (deliberate[e.Player]) stats.DeliberateKills++;
                        if (escapable[e.Player]) stats.EscapableSparkEliminations++;
                        break;
                    case SimEventType.Eliminated:
                        if (e.Cause == EliminationCause.TerritoryLost) stats.TerritoryLostEliminations++;
                        break;
                    case SimEventType.LassoPocket:
                        stats.Pockets++;
                        break;
                }
            };

            while (!sim.Ended)
            {
                sim.Step();
                string broken = CheckInvariants(sim);
                if (broken != null) Assert.Fail("seed " + seed + " tick " + sim.Tick + ": " + broken);
                for (int i = 0; i < n; i++)
                {
                    if (probes[i].Violation != null) Assert.Fail("seed " + seed + ": " + probes[i].Violation);
                    PlayerState p = sim.Players[i];
                    if (!p.Alive) continue;
                    stats.AliveTicks[i]++;
                    if (!p.Home) stats.TrailingTicks[i]++;
                    if (p.Pos == p.PrevPos) stats.HeldTicks++;
                }
            }

            stats.Reason = sim.Result.Reason;
            stats.EndTime = sim.Result.EndTime;
            stats.Ranks = (int[])sim.Result.Ranks.Clone();
            long owned = 0;
            for (int i = 0; i < n; i++)
            {
                owned += sim.Grid.CountOf(sim.Players[i].Id);
                stats.AliveAtEnd[i] = sim.Players[i].Alive;
                stats.Decisions += probes[i].Decisions;
                stats.AttackStarts += probes[i].AttackStarts;
                stats.DecisionSeconds += probes[i].DecisionSeconds;
                stats.MaxDecisionSeconds = Math.Max(stats.MaxDecisionSeconds, probes[i].MaxDecisionSeconds);
            }
            stats.Coverage = 100.0 * owned / sim.Grid.ArenaCellCount;
            return stats;
        }

        /// <summary>
        /// The contract 10.1 invariants (same list as SimTestKit.AssertInvariants, written without per-tick NUnit
        /// constraint objects so 50 full rounds stay fast): no NaN, cells sum &lt;= arena cells, Home == (owner(Cell) ==
        /// Id) for alive players, trail empty iff home, trail end == Pos for trailing players, spark S &lt;= trail length
        /// + 1e-6, EventCapHits == 0. Returns null when they hold, else a description.
        /// </summary>
        internal static string CheckInvariants(Simulation sim)
        {
            OwnerGrid g = sim.Grid;
            long sum = 0;
            for (int i = 0; i < sim.Players.Count; i++)
            {
                PlayerState p = sim.Players[i];
                if (double.IsNaN(p.Pos.X) || double.IsNaN(p.Pos.Y) || double.IsNaN(p.Heading)) return "player " + i + ": NaN state";
                sum += g.CountOf(p.Id);
                if (p.Trail.IsEmpty != p.Home) return "player " + i + ": trail empty iff home";
                if (p.Alive)
                {
                    if ((g.Cells[p.Cell] == p.Id) != p.Home) return "player " + i + ": Home != (owner(Cell) == Id)";
                    if (!p.Home && Vec2d.Distance(p.Trail.Points[p.Trail.Count - 1], p.Pos) > 1e-9) return "player " + i + ": trail end != Pos";
                }
                if (p.Spark != null)
                {
                    if (double.IsNaN(p.Spark.S)) return "player " + i + ": NaN spark";
                    if (p.Spark.S > p.Trail.Length + 1e-6) return "player " + i + ": spark S > trail length";
                }
            }
            if (sum > g.ArenaCellCount) return "cells sum > arena cells";
            if (sim.EventCapHits != 0) return "EventCapHits = " + sim.EventCapHits;
            return null;
        }

        /// <summary>Aggregated section 9 metrics over a set of rounds (asserted and reported values).</summary>
        internal sealed class Summary
        {
            public int Rounds;
            public double[] MeanCaptures;
            public double CutShare, SparkKillShare, TimeUpShare, MeanCoverage;
            public double EscapableShare;          // escapable spark eliminations / spark eliminations
            public double[] TrailingShare;         // trailing ticks / alive ticks per player
            public double[] AliveAtEndShare, FirstShare;
            public double MeanDecisionMs, P99DecisionMs, MaxDecisionMs;
            public int SparkEliminations, EscapableSparkEliminations, Pockets, TerritoryLost;
            public int Cuts, AttackStarts, DeliberateCuts, DeliberateKills;
            public int ChasedReturns, ChasedCaptures;
            public long HeldTicks;
            public int[] Deaths, KillsBy;
            public double WallSeconds;

            public string Format(string title)
            {
                var sb = new StringBuilder();
                CultureInfo ci = CultureInfo.InvariantCulture;
                sb.Append(title).Append(" (").Append(Rounds).Append(" rounds, ").Append(WallSeconds.ToString("F1", ci)).Append(" s)\n");
                sb.Append("  captures per bot: ");
                for (int i = 0; i < MeanCaptures.Length; i++) sb.Append(MeanCaptures[i].ToString("F2", ci)).Append(' ');
                sb.Append("\n  cut share ").Append(CutShare.ToString("P0", ci))
                  .Append(", spark-kill share ").Append(SparkKillShare.ToString("P0", ci))
                  .Append(", TimeUp share ").Append(TimeUpShare.ToString("P0", ci))
                  .Append(", mean coverage ").Append(MeanCoverage.ToString("F1", ci)).Append(" %\n");
                sb.Append("  spark eliminations ").Append(SparkEliminations).Append(" (escapable ").Append(EscapableSparkEliminations)
                  .Append(" = ").Append(EscapableShare.ToString("P1", ci)).Append("), territory-lost ").Append(TerritoryLost)
                  .Append(", pockets ").Append(Pockets).Append(", held ticks ").Append(HeldTicks).Append('\n');
                sb.Append("  cuts ").Append(Cuts).Append(" (deliberate ").Append(DeliberateCuts).Append(" from ").Append(AttackStarts).Append(" attacks), deliberate kills ").Append(DeliberateKills)
                  .Append(", deaths per player ").Append(string.Join(",", Deaths)).Append(", kills per player ").Append(string.Join(",", KillsBy)).Append('\n');
                sb.Append("  saved (chased) returns ").Append(ChasedReturns).Append(", of which with cells ").Append(ChasedCaptures).Append('\n');
                sb.Append("  trailing share: ");
                for (int i = 0; i < TrailingShare.Length; i++) sb.Append(TrailingShare[i].ToString("P0", ci)).Append(' ');
                sb.Append("\n  alive at end: ");
                for (int i = 0; i < AliveAtEndShare.Length; i++) sb.Append(AliveAtEndShare[i].ToString("P0", ci)).Append(' ');
                sb.Append("\n  first: ");
                for (int i = 0; i < FirstShare.Length; i++) sb.Append(FirstShare[i].ToString("P0", ci)).Append(' ');
                sb.Append("\n  decision cost: mean ").Append(MeanDecisionMs.ToString("F4", ci)).Append(" ms, p99 ")
                  .Append(P99DecisionMs.ToString("F4", ci)).Append(" ms, max ").Append(MaxDecisionMs.ToString("F3", ci)).Append(" ms\n");
                return sb.ToString();
            }
        }

        internal static Summary Summarize(List<RoundStats> rounds, List<double> samples, double wallSeconds)
        {
            int n = rounds[0].Captures.Length;
            var s = new Summary
            {
                Rounds = rounds.Count,
                MeanCaptures = new double[n],
                TrailingShare = new double[n],
                AliveAtEndShare = new double[n],
                FirstShare = new double[n],
                Deaths = new int[n],
                KillsBy = new int[n],
                WallSeconds = wallSeconds,
            };
            var alive = new long[n];
            var trailing = new long[n];
            int cutRounds = 0, killRounds = 0, timeUp = 0, decisions = 0;
            double decisionSeconds = 0.0, maxDecision = 0.0;
            foreach (RoundStats r in rounds)
            {
                for (int i = 0; i < n; i++)
                {
                    s.MeanCaptures[i] += r.Captures[i];
                    alive[i] += r.AliveTicks[i];
                    trailing[i] += r.TrailingTicks[i];
                    if (r.AliveAtEnd[i]) s.AliveAtEndShare[i] += 1;
                    if (r.Ranks[i] == 1) s.FirstShare[i] += 1;
                    s.Deaths[i] += r.Deaths[i];
                    s.KillsBy[i] += r.KillsBy[i];
                }
                s.Cuts += r.Cuts;
                s.DeliberateCuts += r.DeliberateCuts;
                s.AttackStarts += r.AttackStarts;
                s.HeldTicks += r.HeldTicks;
                s.DeliberateKills += r.DeliberateKills;
                s.ChasedReturns += r.ChasedReturns;
                s.ChasedCaptures += r.ChasedCaptures;
                if (r.Cuts > 0) cutRounds++;
                if (r.SparkEliminations > 0) killRounds++;
                if (r.Reason == RoundEndReason.TimeUp) timeUp++;
                s.MeanCoverage += r.Coverage;
                s.SparkEliminations += r.SparkEliminations;
                s.EscapableSparkEliminations += r.EscapableSparkEliminations;
                s.Pockets += r.Pockets;
                s.TerritoryLost += r.TerritoryLostEliminations;
                decisions += r.Decisions;
                decisionSeconds += r.DecisionSeconds;
                maxDecision = Math.Max(maxDecision, r.MaxDecisionSeconds);
            }
            int count = rounds.Count;
            for (int i = 0; i < n; i++)
            {
                s.MeanCaptures[i] /= count;
                s.TrailingShare[i] = alive[i] > 0 ? trailing[i] / (double)alive[i] : 0.0;
                s.AliveAtEndShare[i] /= count;
                s.FirstShare[i] /= count;
            }
            s.CutShare = cutRounds / (double)count;
            s.SparkKillShare = killRounds / (double)count;
            s.TimeUpShare = timeUp / (double)count;
            s.MeanCoverage /= count;
            s.EscapableShare = s.SparkEliminations > 0 ? s.EscapableSparkEliminations / (double)s.SparkEliminations : 0.0;
            s.MeanDecisionMs = decisions > 0 ? 1000.0 * decisionSeconds / decisions : 0.0;
            s.MaxDecisionMs = 1000.0 * maxDecision;
            if (samples != null && samples.Count > 0)
            {
                samples.Sort();
                s.P99DecisionMs = 1000.0 * samples[Math.Min(samples.Count - 1, (int)(0.99 * samples.Count))];
            }
            return s;
        }

        internal static Summary RunSeeds(int seeds, BotPersonality[] lineup, int humanIndex, bool lasso, out List<RoundStats> rounds,
                                         bool borderRide = false)
        {
            rounds = new List<RoundStats>();
            var samples = new List<double>();
            var watch = Stopwatch.StartNew();
            for (int k = 1; k <= seeds; k++) rounds.Add(RunRound((ulong)k, lineup, humanIndex, lasso, 60, samples, borderRide));
            watch.Stop();
            return Summarize(rounds, samples, watch.Elapsed.TotalSeconds);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Contract 10.1 Bots: seeded bot-only rounds

        [TestCase(true)]
        [TestCase(false)]
        public void Bots_SeededBotOnlyRoundsMeetSection9Targets(bool lasso)
        {
            string title = "Bot-only rounds, lasso " + (lasso ? "on" : "off");
#if UNITY_5_3_OR_NEWER
            // Unity (Mono, Debug): 10 seeds, asserting only no exception and the invariants (checked every tick in RunRound).
            Summary s = RunSeeds(10, Lineup(BotOnlyLineup), -1, lasso, out List<RoundStats> rounds);
            TestContext.WriteLine(s.Format(title + " (Unity)"));
            Assert.AreEqual(10, rounds.Count);
            Assert.AreEqual(0, s.ChasedCaptures, "contract 24: a chased (saved) return never captures");
#else
            Summary s = RunSeeds(50, Lineup(BotOnlyLineup), -1, lasso, out List<RoundStats> rounds);
            TestContext.WriteLine(s.Format(title));
            Assert.AreEqual(50, rounds.Count);
            Assert.That(s.WallSeconds, Is.LessThan(60.0), "50 rounds must run under 60 s in the dotnet loop");
            for (int i = 0; i < BotOnlyLineup.Length; i++)
            {
                double required = BotOnlyLineup[i] == BotStyle.Greedy ? 4.0 : 5.0;
                Assert.That(s.MeanCaptures[i], Is.GreaterThanOrEqualTo(required), "average captures of player " + i + " (" + BotOnlyLineup[i] + ")");
            }
            Assert.That(s.CutShare, Is.GreaterThanOrEqualTo(0.85), "share of matches with a cut");
            Assert.That(s.SparkKillShare, Is.InRange(0.35, 0.85), "share of matches with at least one Spark elimination");
            Assert.That(s.MeanCoverage, Is.InRange(30.0, 85.0), "average total coverage at the end (%)");
            Assert.That(s.TimeUpShare, Is.GreaterThanOrEqualTo(0.40), "share of matches reaching TimeUp");
            Assert.That(s.MeanDecisionMs, Is.LessThan(0.2), "mean decision cost (ms)");
            // Section 9 "never steer outward into the border on purpose": no bot is ever held against the rim (R4 hold).
            Assert.AreEqual(0L, s.HeldTicks, "ticks where a bot pushed into the border and was held");
            // Contract 24: saved returns happen in these rounds and none of them captures.
            Assert.That(s.ChasedReturns, Is.GreaterThan(0), "saved (chased) returns occur");
            Assert.AreEqual(0, s.ChasedCaptures, "a chased (saved) return never captures");
#endif
        }

        /// <summary>
        /// Gate A perf figure: wall time of one Simulation.Step (event engine + the four BotControllers polled inside it)
        /// during bot-only rounds at 60 Hz, lasso spawns on. Plain BotControllers, no probe wrapper; the invariant check
        /// runs outside the timed region. Only ticks that start with all four players alive are sampled ("4-player tick").
        /// The bound only catches an algorithmic regression (the 60 Hz frame budget is 16.7 ms).
        /// </summary>
        [Test]
        [Category("Perf")]
        public void Bots_Perf_FourPlayerTickCostDuringABotRound()
        {
            BotPersonality[] lineup = Lineup(BotOnlyLineup);
            // Warm-up (JIT, pooled capture buffers) on a round that is not measured.
            Simulation warm = NewPlainBotRound(99UL, lineup);
            for (int k = 0; k < 600 && !warm.Ended; k++) warm.Step();

            const int rounds = 3;
            var samples = new List<double>();
            double totalUs = 0.0;
            int returnTicks = 0;
            double returnTickUs = 0.0;
            for (int r = 1; r <= rounds; r++)
            {
                Simulation sim = NewPlainBotRound((ulong)r, lineup);
                while (!sim.Ended)
                {
                    bool allAlive = true;
                    for (int i = 0; i < sim.Players.Count; i++) allAlive &= sim.Players[i].Alive;
                    long t0 = Stopwatch.GetTimestamp();
                    sim.Step();
                    long t1 = Stopwatch.GetTimestamp();
                    string broken = CheckInvariants(sim);
                    if (broken != null) Assert.Fail("seed " + r + " tick " + sim.Tick + ": " + broken);
                    if (!allAlive) continue;
                    double us = (t1 - t0) * 1e6 / Stopwatch.Frequency;
                    samples.Add(us);
                    totalUs += us;
                    bool returned = false;
                    foreach (SimEvent e in sim.LastEvents) returned |= e.Type == SimEventType.Return;
                    if (returned)
                    {
                        returnTicks++;
                        returnTickUs += us;
                    }
                }
            }
            Assert.That(samples.Count, Is.GreaterThan(rounds * 1000), "4-player ticks sampled");
            samples.Sort();
            double mean = totalUs / samples.Count;
            double p50 = samples[samples.Count / 2];
            double p99 = samples[Math.Min(samples.Count - 1, (int)(0.99 * samples.Count))];
            double max = samples[samples.Count - 1];
            CultureInfo ci = CultureInfo.InvariantCulture;
            TestContext.WriteLine("4-player tick (60 Hz, 4 bots, lasso on, " + rounds + " rounds, " + samples.Count + " ticks): mean "
                                  + mean.ToString("F1", ci) + " us, p50 " + p50.ToString("F1", ci) + " us, p99 " + p99.ToString("F1", ci)
                                  + " us, max " + max.ToString("F1", ci) + " us; ticks with a Return " + returnTicks + ", mean "
                                  + (returnTicks > 0 ? returnTickUs / returnTicks : 0.0).ToString("F1", ci) + " us");
#if UNITY_5_3_OR_NEWER
            const double boundUs = 1500.0;   // Editor Mono, Debug code optimization
#else
            const double boundUs = 400.0;    // dotnet Debug build, machine shared with other jobs
#endif
            Assert.That(mean, Is.LessThan(boundUs), "mean 4-player tick cost (us)");
        }

        private static Simulation NewPlainBotRound(ulong seed, BotPersonality[] lineup)
        {
            var controllers = new IController[lineup.Length];
            for (int i = 0; i < lineup.Length; i++) controllers[i] = new BotController(lineup[i], BotSeed(seed, i));
            var config = new SimConfig { Seed = seed, TickRate = 60, LassoEnabled = true };
            return new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
        }
        // ------------------------------------------------------------------------------------------------------------
        // Focused FSM tests: 60 Hz unless stated, real turn rate (540 deg/s), scripted opponents, invariants every tick

        private static Vec2d V(double x, double y) => new Vec2d(x, y);

        /// <summary>Default R2 layout (discs at (+/-16, +/-16)): player 0 is the bot, the others orbit inside their discs.</summary>
        private static Simulation OneBotLayout(BotPersonality bp, out BotController bot, double roundDuration = 90.0,
                                               int tickRate = 60, ulong seed = 7)
        {
            bot = new BotController(bp, seed);
            double d = Tuning.StartDiscOffset;
            Vec2d[] starts = { V(-d, -d), V(d, -d), V(d, d), V(-d, d) };
            var controllers = new IController[4];
            controllers[0] = bot;
            for (int i = 1; i < 4; i++) controllers[i] = new HomeCirclerController(starts[i]);
            var config = new SimConfig { Seed = seed, TickRate = tickRate, RoundDuration = roundDuration, LassoEnabled = false };
            return new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
        }

        private static BotPersonality Preset(BotStyle style, double maxTrailLength = double.NaN)
        {
            BotPersonality p = BotPersonality.Preset(style);
            if (!double.IsNaN(maxTrailLength)) p.MaxTrailLength = maxTrailLength;
            return p;
        }

        /// <summary>One Step, then the 10.1 invariants.</summary>
        private static void Tick(Simulation sim)
        {
            sim.Step();
            string broken = CheckInvariants(sim);
            if (broken != null) Assert.Fail("tick " + sim.Tick + ": " + broken);
        }

        private static void StepUntilTick(Simulation sim, long tick)
        {
            while (!sim.Ended && sim.Tick < tick) Tick(sim);
        }

        [TestCase(30)]
        [TestCase(60)]
        [TestCase(144)]
        public void Bots_DecisionsEveryTenthOfASecondOfSimTime(int rate)
        {
            Simulation sim = OneBotLayout(Preset(BotStyle.Balanced), out BotController bot, 90.0, rate);
            StepUntilTick(sim, 3 * rate);   // calls at Time = k / rate for k < 3 rate: decision indices 0 .. 29
            Assert.IsTrue(sim.Players[0].Alive);
            Assert.AreEqual(30, bot.DecisionCount, "one decision per 0.1 s of sim time, whatever the tick rate");
        }

        private static BotController[] Bots(ulong seedBase)
        {
            var bots = new BotController[4];
            for (int i = 0; i < 4; i++) bots[i] = new BotController(BotPersonality.Preset(BotOnlyLineup[i]), seedBase + (ulong)i);
            return bots;
        }

        private static ulong RunFor(BotController[] bots, double seconds)
        {
            var controllers = new IController[bots.Length];
            for (int i = 0; i < bots.Length; i++) controllers[i] = bots[i];
            var sim = new Simulation(new SimConfig { Seed = 5 }, controllers, new SimSetup { HumanIndex = -1 });
            while (!sim.Ended && sim.Time < seconds - 1e-9) Tick(sim);
            return sim.StateHash();
        }

        [Test]
        public void Bots_DeterministicFromSeedAndResetForANewRound()
        {
            BotController[] bots = Bots(100);
            ulong first = RunFor(bots, 20.0);
            ulong reused = RunFor(bots, 20.0);           // same instances, new Simulation: they reset and re-seed
            ulong fresh = RunFor(Bots(100), 20.0);
            ulong otherSeed = RunFor(Bots(200), 20.0);
            Assert.AreEqual(first, fresh, "same seeds and view give the same round");
            Assert.AreEqual(first, reused, "a controller reused for a new round behaves like a fresh one");
            Assert.AreNotEqual(first, otherSeed, "the bot seeds matter");
        }

        /// <summary>Records each new excursion plan at the decision that made it and checks the section 9 geometry.</summary>
        private sealed class PlanRecorder : IController
        {
            public readonly BotController Bot;
            public readonly List<string> Failures = new List<string>();
            public int Plans;
            private readonly List<Vec2d> scratch = new List<Vec2d>();
            private Vec2d lastFirst = V(double.NaN, double.NaN);

            public PlanRecorder(BotController bot)
            {
                Bot = bot;
            }

            public double? DesiredHeading(SimView view, int playerIndex)
            {
                int d0 = Bot.DecisionCount;
                double? heading = Bot.DesiredHeading(view, playerIndex);
                if (Bot.DecisionCount == d0 || Bot.Mode != BotMode.Home) return heading;
                Bot.CopyPlan(scratch);
                if (scratch.Count != 3 || scratch[0] == lastFirst) return heading;
                lastFirst = scratch[0];
                Plans++;
                Check(view, playerIndex);
                return heading;
            }

            private void Check(SimView view, int index)
            {
                SimConfig c = view.Config;
                BotPersonality bp = Bot.Personality;
                byte id = view.Player(index).Id;
                double inset = c.ArenaMargin + BotController.PlanBorderMargin;
                Vec2d p1 = scratch[0], p2 = scratch[1], r = scratch[2], e = Bot.EdgePoint;
                string at = "player " + index + " t=" + view.Time.ToString("F2", CultureInfo.InvariantCulture) + ": ";
                foreach (Vec2d p in scratch)
                {
                    if (view.Arena.SignedDistance(p) > -inset + 1e-9) Failures.Add(at + "plan point " + p + " outside the clamped arena");
                }
                if (view.Grid.OwnerAt(p1) == id) Failures.Add(at + "first plan point is own land");
                if (view.Grid.OwnerAt(r) != id) Failures.Add(at + "R is not own land");
                double depth = Vec2d.Distance(p1, e);
                if (depth > bp.MaxOut + 1e-6) Failures.Add(at + "depth " + depth + " > MaxOut");
                bool clamped1 = Math.Abs(view.Arena.SignedDistance(p1) + inset) < 1e-6;
                bool clamped2 = Math.Abs(view.Arena.SignedDistance(p2) + inset) < 1e-6;
                if (clamped1) return;
                Vec2d dir = (p1 - e) / depth;
                double bestDot = -2.0;
                for (int k = 0; k < 8; k++) bestDot = Math.Max(bestDot, Vec2d.Dot(dir, Vec2d.FromAngle(k * Math.PI / 4.0)));
                if (bestDot < 1.0 - 1e-9) Failures.Add(at + "excursion axis is not one of the 8 directions");
                if (view.Time < c.RoundDuration - 30.0 && depth < bp.MinOut - 1e-6) Failures.Add(at + "depth " + depth + " < MinOut");
                if (clamped2) return;
                Vec2d leg = p2 - p1;
                double width = leg.Length;
                if (Math.Abs(Vec2d.Dot(leg, dir)) > 1e-6 * Math.Max(1.0, width)) Failures.Add(at + "side leg not perpendicular to the axis");
                if (width < 0.6 * depth - 1e-6 || width > 1.2 * depth + 1e-6) Failures.Add(at + "width " + width + " not in [0.6, 1.2] x depth " + depth);
            }
        }

        [Test]
        public void Bots_PlansStartAtTheEdgePointAndStayInsideTheClampedArena()
        {
            int plans = 0;
            var failures = new List<string>();
            for (ulong seed = 1; seed <= 3; seed++)
            {
                var recorders = new PlanRecorder[4];
                var controllers = new IController[4];
                for (int i = 0; i < 4; i++)
                {
                    recorders[i] = new PlanRecorder(new BotController(BotPersonality.Preset(BotOnlyLineup[i]), BotSeed(seed, i)));
                    controllers[i] = recorders[i];
                }
                var sim = new Simulation(new SimConfig { Seed = seed }, controllers, new SimSetup { HumanIndex = -1 });
                while (!sim.Ended) Tick(sim);
                foreach (PlanRecorder r in recorders)
                {
                    plans += r.Plans;
                    failures.AddRange(r.Failures);
                }
            }
            Assert.That(plans, Is.GreaterThan(100), "plans checked");
            Assert.AreEqual(0, failures.Count, string.Join("\n", failures));
        }

        [TestCase(30.0, true)]
        [TestCase(1000.0, false)]
        public void Bots_ReturnTriggerTrailLongerThanMaxTrailLength(double maxTrailLength, bool expectReturn)
        {
            Simulation sim = OneBotLayout(Preset(BotStyle.Balanced, maxTrailLength), out BotController bot);
            // A 39.4 u trail whose head is 3.8 u from the bot's disc, far from every other player.
            var trail = new[] { V(-12.4, -16), V(8, -16), V(8, -14), V(-9, -14) };
            sim.BeforeTick += s =>
            {
                if (s.Tick == 12) s.DebugSetTrail(0, trail);
            };
            StepUntilTick(sim, 12);
            Assert.AreEqual(BotMode.Home, bot.Mode, "planning at home before the trail is injected");
            Tick(sim);   // tick 12 is a decision tick (every 6 ticks at 60 Hz)
            Assert.AreEqual(expectReturn ? BotMode.Return : BotMode.Out, bot.Mode);
            if (!expectReturn) return;
            Assert.IsTrue(bot.TryGetTarget(out Vec2d target));
            Assert.AreEqual(sim.Players[0].Id, sim.Grid.OwnerAt(target), "the return target is an own cell (NearestOwned)");
            Assert.IsTrue(SimTestKit.RunUntil(sim, s => s.Players[0].Home, 5.0), "the bot gets home");
            Assert.IsTrue(sim.Players[0].Alive);
        }

        [Test]
        public void Bots_OwnSparkTriggersTheReturnAfterReactionDelay()
        {
            BotPersonality bp = Preset(BotStyle.Balanced, 1000.0);   // ReactionDelay 0.30
            Simulation sim = OneBotLayout(bp, out BotController bot);
            var log = new SimTestKit.EventLog(sim);
            var trail = new[] { V(-12.4, -16), V(6, -16), V(6, -14), V(-7, -14) };   // L = 33.4, head 5.7 u from home
            sim.BeforeTick += s =>
            {
                if (s.Tick == 12) s.DebugSetTrail(0, trail);
                if (s.Tick == 30) s.DebugForceCut(0, 1.0, -1);   // TimeCut = 0.5 s, the spark starts 32 u behind the head
            };
            double reactAt = 0.5 + bp.ReactionDelay;
            while (sim.Time < reactAt - 1e-9)
            {
                Tick(sim);
                Assert.AreNotEqual(BotMode.Return, bot.Mode, "the new spark is ignored for ReactionDelay (t=" + sim.Time + ")");
            }
            Tick(sim);   // the decision at t = TimeCut + ReactionDelay (tick 48)
            Assert.AreEqual(BotMode.Return, bot.Mode, "returns at the first decision at or after TimeCut + ReactionDelay");
            Assert.IsTrue(SimTestKit.RunUntil(sim, s => s.Players[0].Home || !s.Players[0].Alive, 8.0));
            Assert.IsTrue(sim.Players[0].Alive, "an escapable cut is survived");
            SimEvent ret = log.First(SimEventType.Return, 0);
            Assert.IsNotNull(ret);
            Assert.IsTrue(ret.Chased, "saved from the spark");
            Assert.AreEqual(0, ret.Cells.Length, "contract 24: saved, but the cut loop is lost");
        }

        [TestCase(16.0, false)]
        [TestCase(40.0, true)]
        public void Bots_ThreatOnlyFromVisibleEnemiesAndAfterReactionDelay(double senseRadius, bool expectReturn)
        {
            BotPersonality bp = Preset(BotStyle.Balanced, 1000.0);   // ThreatRadius 6, ReactionDelay 0.30
            bp.SenseRadius = senseRadius;
            Simulation sim = OneBotLayout(bp, out BotController bot);
            // The trail starts 4.47 u from player 1's disc center: its orbiting head (radius 1.5) is always within the
            // ThreatRadius of that exposed point, while staying more than 24 u from the bot's head.
            var trail = new[] { V(12, -14), V(-11, -12) };
            sim.BeforeTick += s =>
            {
                if (s.Tick == 12) s.DebugSetTrail(0, trail);
            };
            StepUntilTick(sim, 13);   // the tick-12 decision sees the threat (when visible) at t = 0.2
            Assert.AreEqual(BotMode.Out, bot.Mode);
            while (sim.Time < 0.2 + bp.ReactionDelay - 1e-9)
            {
                Tick(sim);
                Assert.AreNotEqual(BotMode.Return, bot.Mode, "a new threat is ignored for ReactionDelay");
            }
            Tick(sim);   // the decision at t = 0.5
            Assert.AreEqual(expectReturn ? BotMode.Return : BotMode.Out, bot.Mode,
                            expectReturn ? "a visible enemy near the trail triggers the return" : "an enemy beyond SenseRadius is invisible");
        }

        [TestCase(5.5, true)]
        [TestCase(30.0, false)]
        public void Bots_RoundTimeTriggerUsesTheDistanceHome(double roundDuration, bool expectReturn)
        {
            Simulation sim = OneBotLayout(Preset(BotStyle.Balanced, 1000.0), out BotController bot, roundDuration);
            // Head 20.4 u from the nearest own cell: at t = 0.2, 0.2 + 20.4 / 6 + 2 = 5.6 s.
            var trail = new[] { V(-12.4, -16), V(8, -16) };
            sim.BeforeTick += s =>
            {
                if (s.Tick == 12) s.DebugSetTrail(0, trail);
            };
            StepUntilTick(sim, 12);
            Assert.AreEqual(BotMode.Home, bot.Mode, "a short plan still fits in the round at t = 0");
            Tick(sim);
            Assert.AreEqual(expectReturn ? BotMode.Return : BotMode.Out, bot.Mode);
        }

        /// <summary>
        /// Player 0 (the victim) has its disc far west and gets a 20.4 u trail running east at y = 0.0625, then keeps going
        /// east (it never flees). Player 1 (the bot) sits at home 5 u above the trail head.
        /// </summary>
        private static Simulation AttackScene(BotPersonality bp, int humanIndex, out BotController bot, out SimTestKit.EventLog log)
        {
            var sb = new SimTestKit.SimBuilder(60, false);
            sb.Config.TurnRateDeg = Tuning.TurnRateDeg;
            sb.HumanIndex = humanIndex;
            sb.AddDisc(V(-24, 0), 3.5, V(-24, 0), 0.0, new ConstantHeadingController(0.0));
            bot = new BotController(bp, 21);
            sb.AddDisc(V(4, 5), 3.5, V(4, 5), -0.5 * Math.PI, bot);
            Simulation sim = sb.Build();
            log = new SimTestKit.EventLog(sim);
            sim.BeforeTick += s =>
            {
                if (s.Tick == 1) s.DebugSetTrail(0, new[] { V(-20.4, 0.0625), V(0, 0.0625) });
            };
            return sim;
        }

        [Test]
        public void Bots_AttackAimsAtTheLethalSampleThenCutsAndKills()
        {
            BotPersonality bp = Preset(BotStyle.Balanced);
            bp.AttackChance = 1.0;
            bp.AttackRadius = 11.0;
            Simulation sim = AttackScene(bp, -1, out BotController bot, out SimTestKit.EventLog log);
            bool attacked = false;
            while (!sim.Ended && sim.Time < 5.0 && sim.Players[0].Alive)
            {
                Tick(sim);
                if (bot.AttackVictim == 0) attacked = true;
            }
            Assert.IsTrue(attacked, "the bot commits to an intercept on the victim's trail");
            SimEvent cut = log.Single(SimEventType.Cut, 0);
            Assert.AreEqual(1, cut.Other, "the bot made the cut");
            SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
            Assert.AreEqual(1, caught.Other);
            Assert.AreEqual(1, sim.Players[1].Kills);
            Assert.IsTrue(sim.Players[1].Alive);
        }

        [TestCase(1.0, 1.0, true)]
        [TestCase(1.0, 0.0, false)]
        [TestCase(0.0, 1.0, false)]
        public void Bots_AttackChanceAndHumanAttackScaleGateTheAttack(double attackChance, double humanScale, bool expectAttack)
        {
            BotPersonality bp = Preset(BotStyle.Balanced);
            bp.AttackChance = attackChance;
            bp.AttackRadius = 11.0;
            bp.HumanAttackScale = humanScale;
            Simulation sim = AttackScene(bp, 0, out BotController bot, out _);   // the victim is the human
            bool attacked = false;
            while (!sim.Ended && sim.Time < 2.0)
            {
                Tick(sim);
                if (bot.AttackVictim == 0) attacked = true;
            }
            Assert.AreEqual(expectAttack, attacked);
        }

        /// <summary>
        /// At the tick-6 decision (t = 0.1 s) the victim's most recent sample is (-0.8, 0), its escape time E_v is about
        /// 1.26 s, and the bot is 5.1 .. 6.3 u from that sample (within AttackRadius) with a heading within 54 degrees of
        /// it, so T is 0.86 .. 1.16 s and no sample is lethal (C = (1.3 + 6 T) / 4.8 &gt;= 1.34 s &gt; E_v - 0.2). The victim's
        /// trail starts trailLength u west of the origin (trailLength + 0.5 u at the decision). Returns the bot after that
        /// decision.
        /// </summary>
        private static BotController NonLethalScene(BotStyle style, double attackChance, double trailLength, ulong seed, out Simulation sim)
        {
            BotPersonality bp = Preset(style);
            bp.AttackChance = attackChance;
            bp.AttackRadius = 11.0;
            var sb = new SimTestKit.SimBuilder(60, false);
            sb.Config.TurnRateDeg = Tuning.TurnRateDeg;
            sb.AddDisc(V(-6, -9), 3.5, V(-6, -9), 0.0, new ConstantHeadingController(0.0));
            var bot = new BotController(bp, seed);
            double towardSample = (V(-0.8, 0) - V(2, 5)).Angle();
            sb.AddDisc(V(2, 5), 3.5, V(2, 5), towardSample, bot);
            Simulation built = sb.Build();
            built.BeforeTick += s =>
            {
                if (s.Tick == 1) s.DebugSetTrail(0, new[] { V(-trailLength, 0), V(0, 0) });   // runs east, 7.6 u from home
            };
            StepUntilTick(built, 7);   // through the decision of tick 6
            Assert.IsTrue(built.Players[0].Alive && !built.Players[0].Home && built.Players[0].Spark == null);
            sim = built;
            return bot;
        }

        /// <summary>
        /// Contract 24: a sample that is not lethal is still worth a cut (it denies the victim's capture), for every style,
        /// but only on a victim trail of at least DenialMinTrail = 6 u. AttackChance 2 makes the denial draw certain for
        /// every style (2 x 0.6 and 2 x 1.0 are &gt;= 1). A 4 u trail (4.5 u at the decision) is left alone. (This replaces
        /// the v1.3 test Bots_HarassmentCutsAreAggressiveOnly: the Aggressive-only harassment cut became the denial cut.)
        /// </summary>
        [TestCase(BotStyle.Aggressive, 6.0, true)]
        [TestCase(BotStyle.Balanced, 6.0, true)]
        [TestCase(BotStyle.Greedy, 6.0, true)]
        [TestCase(BotStyle.Cautious, 6.0, true)]
        [TestCase(BotStyle.Aggressive, 4.0, false)]
        [TestCase(BotStyle.Balanced, 4.0, false)]
        public void Bots_DenialCutsNeedASixUnitTrailWhenNoSampleIsLethal(BotStyle style, double trailLength, bool expectAttack)
        {
            BotController bot = NonLethalScene(style, 2.0, trailLength, 4, out Simulation sim);
            Assert.AreEqual(expectAttack, bot.AttackVictim == 0);
            if (!expectAttack) return;
            Assert.IsTrue(bot.TryGetTarget(out Vec2d target));
            double sTop = sim.Players[0].Trail.Length - sim.Config.HeadGrace - 0.3;
            Assert.That(Vec2d.Distance(target, sim.Players[0].Trail.PointAt(sTop)), Is.LessThan(0.15),
                        "aims at the largest reachable sample (the most recent exposed point)");
        }

        /// <summary>
        /// Contract 24: the denial draw succeeds with probability AttackChance x 0.6, or AttackChance x 1.0 for an
        /// Aggressive bot (one draw per enemy exit). Measured on 300 bot seeds of the non-lethal scene (6 u trail).
        /// </summary>
        [TestCase(BotStyle.Balanced, 0.5, 0.30)]
        [TestCase(BotStyle.Greedy, 1.0, 0.60)]
        [TestCase(BotStyle.Aggressive, 0.5, 0.50)]
        public void Bots_DenialDrawProbabilityIsAttackChanceTimesTheStyleScale(BotStyle style, double attackChance, double expected)
        {
            const int seeds = 300;
            int attacks = 0;
            for (int k = 0; k < seeds; k++)
            {
                BotController bot = NonLethalScene(style, attackChance, 6.0, 1000UL + (ulong)k, out _);
                if (bot.AttackVictim == 0) attacks++;
            }
            double share = attacks / (double)seeds;
            TestContext.WriteLine(style + " AttackChance " + attackChance + ": denial attacks in " + attacks + " / " + seeds);
            Assert.That(share, Is.EqualTo(expected).Within(0.1), "denial attack share");
        }

        [TestCase(1.0, true)]
        [TestCase(0.0, false)]
        public void Bots_ChargedBotCurlsALassoPocketWhenTheDrawSucceeds(double lassoChance, bool expectPocket)
        {
            BotPersonality bp = Preset(BotStyle.Balanced);
            bp.LassoChance = lassoChance;
            Simulation sim = OneBotLayout(bp, out BotController bot, 90.0, 60, 5);
            sim.DebugSetCharged(0, true);
            var log = new SimTestKit.EventLog(sim);
            var plan = new List<Vec2d>();
            bool curled = false;
            while (!sim.Ended && sim.Time < 15.0 - 1e-9)
            {
                Tick(sim);
                bot.CopyPlan(plan);
                if (bot.Mode == BotMode.Out && plan.Count == 4) curled = true;   // [Q1, Q2, Q3, R]: the curl plan
            }
            Assert.IsTrue(sim.Players[0].Alive);
            Assert.AreEqual(expectPocket, curled, "a curl is planned only after a successful LassoChance draw");
            SimEvent pocket = log.First(SimEventType.LassoPocket, 0);
            if (!expectPocket) return;   // a charged bot may still close a pocket by chance; only the curl is deliberate
            Assert.IsNotNull(pocket, "the curl closed a pocket");
            Assert.AreEqual(1, sim.Players[0].PocketsMade);
            int after = log.IndexOf(pocket);
            SimEvent ret = null;
            for (int k = after + 1; k < log.All.Count && ret == null; k++)
            {
                if (log.All[k].Type == SimEventType.Return && log.All[k].Player == 0) ret = log.All[k];
            }
            Assert.IsNotNull(ret, "the bot brings the pocket home");
            Assert.That(ret.Cells.Length, Is.GreaterThan(0));
        }

        /// <summary>
        /// Section 9 "avoid crossing own trail when uncharged": an uncharged crossing loop-erases the capture (R8), so a
        /// lone bot returning from its excursions never crosses its own trail (no LassoCrossNoCharge) and every return
        /// captures something.
        /// </summary>
        [TestCase(5UL)]
        [TestCase(6UL)]
        public void Bots_UnchargedBotNeverCrossesItsOwnTrail(ulong seed)
        {
            Simulation sim = OneBotLayout(Preset(BotStyle.Balanced), out BotController bot, 90.0, 60, seed);
            var log = new SimTestKit.EventLog(sim);
            while (!sim.Ended && sim.Time < 45.0 - 1e-9) Tick(sim);
            Assert.IsTrue(sim.Players[0].Alive);
            Assert.AreEqual(0, log.Count(SimEventType.LassoCrossNoCharge, 0), "own-trail crossings:\n" + log.Dump());
            // Every real excursion (longer than 0.5 s; shorter ones are flickers through a notch of the edge) captures.
            int excursions = 0;
            double exitTime = double.NaN;
            foreach (SimEvent e in log.All)
            {
                if (e.Player != 0) continue;
                if (e.Type == SimEventType.Exit) exitTime = e.Time;
                if (e.Type != SimEventType.Return || !(e.Time - exitTime > 0.5)) continue;
                excursions++;
                Assert.That(e.Cells.Length, Is.GreaterThan(0), "the excursion that ended at t=" + e.Time + " captured nothing");
            }
            Assert.That(excursions, Is.GreaterThanOrEqualTo(8), "excursions made");
        }
        [TestCase(false, true)]
        [TestCase(true, false)]
        public void Bots_TakesTheRingOnlyWhenSafe(bool enemyNearRing, bool expectRing)
        {
            var sb = new SimTestKit.SimBuilder(60, false);
            sb.Config.TurnRateDeg = Tuning.TurnRateDeg;
            var bot = new BotController(BotPersonality.Preset(BotStyle.Balanced), 9);
            sb.AddDisc(V(-16, -16), 3.5, V(-16, -16), 0.0, bot);
            // Near: the orbiting head of player 1 stays within 2.7 .. 5.7 u of the ring (ThreatRadius 6) and is visible.
            sb.AddIdle(enemyNearRing ? V(-8, -8) : V(16, 16));
            Simulation sim = sb.Build();
            var log = new SimTestKit.EventLog(sim);
            Vec2d ring = V(-11, -11);   // 7.07 u from the bot's head, outside both discs
            sim.BeforeTick += s =>
            {
                if (s.Tick == 1) s.DebugPlaceRing(ring);
            };
            bool wentForRing = false;
            while (sim.Time < 3.0 - 1e-9)
            {
                Tick(sim);
                if (bot.Mode == BotMode.Ring) wentForRing = true;
            }
            Assert.AreEqual(expectRing, wentForRing);
            if (!expectRing) return;
            SimEvent picked = log.Single(SimEventType.RingPicked, 0);
            Assert.IsNotNull(picked);
            Assert.IsTrue(sim.Players[0].Charged);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Section 9 reported metrics (not asserted): the human-proxy fixture

        /// <summary>
        /// Section 9 human-proxy fixture: player 0 = BotController(Balanced with ReactionDelay 0.45, SenseRadius 12,
        /// AttackChance 0.3) flagged as the human (HumanIndex 0) against the three presets, 50 seeds. Targets (reported in
        /// the A5 report, not asserted): alive at the end in 35 % to 75 % of rounds, first in 15 % to 45 %. Explicit: run
        /// it with --filter "TestCategory=BotReport". Asserts only the invariants (every tick) and that 50 rounds ran.
        /// </summary>
        [Explicit, Category("BotReport")]
        [TestCase(true)]
        [TestCase(false)]
        public void BotsReport_HumanProxyFixture(bool lasso)
        {
            BotPersonality proxy = BotPersonality.Preset(BotStyle.Balanced);
            proxy.ReactionDelay = 0.45;
            proxy.SenseRadius = 12;
            proxy.AttackChance = 0.3;
            var lineup = new[] { proxy, BotPersonality.Preset(BotStyle.Balanced), BotPersonality.Preset(BotStyle.Greedy), BotPersonality.Preset(BotStyle.Aggressive) };
            Summary s = RunSeeds(50, lineup, 0, lasso, out List<RoundStats> rounds);
            TestContext.WriteLine(s.Format("Human-proxy fixture, lasso " + (lasso ? "on" : "off")));
            TestContext.WriteLine("  proxy alive at end " + s.AliveAtEndShare[0].ToString("P0", CultureInfo.InvariantCulture)
                                  + " (target 35-75 %), first " + s.FirstShare[0].ToString("P0", CultureInfo.InvariantCulture) + " (target 15-45 %)");
            Assert.AreEqual(50, rounds.Count);
        }
    }
}