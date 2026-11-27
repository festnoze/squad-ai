// Owned by kill-verify (wave D-2): adversarial verification of the kill rewards (docs/BIOME_TRAITS.md section 7, v1.1).
// Attacks, in the order of the verification brief:
//   1. classic bit-identity: the new state never moves in classic rounds, and the kill traits present but disabled
//      (with invalid parameters, SparkFollowsVictimSpeed false) reproduce the pre-trait rolling hash;
//   2. each kill trait moved to every biome set: behaviour only (same applied config), deterministic, an independent
//      per-event oracle holds, and switching it off gives back the biome set bit for bit;
//   3. kill attribution: the cut retained by R11 (largest s_cut, ties to the lowest index), a killer captured to death
//      before or in the same group, two victims at once, a chain inside one group, transitive inheritance, and
//      TerritoryLost never rewarding;
//   4. KillInheritance against ScorchedEarth (Share 0.5), Propagation (same tick), a pending lasso pocket and the
//      trailing killer's head in the TimeUp group;
//   5. KillSpeedBoost: the HeadGrace check at 30 Hz uses the product of the maxima, the reachable step, and the spark
//      speed of a cut in the same group as the victim's own kill;
//   6. KillShield: the end on a tick boundary, HeadGrace at the end (a follower inside the grace never cuts, one just
//      outside cuts at the exact end), and the exact start (a catch of the killer within eps of its kill wins);
//   7. determinism and invariants: all eleven traits, the v1.1 sets and random kill parameters in bot rounds at 30, 60
//      and 144 Hz under the oracle (including s_cut <= L - HeadGrace at the cut instant at max speed).
// Pure NUnit + PainterIO.Core (no UnityEngine), NUnit 3.5 features only.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class KillTraitsAuditTests
    {
#if UNITY_5_3_OR_NEWER
        // Editor Mono is several times slower than the dotnet loop: shorter bot rounds and fewer cases.
        private const double BotSeconds = 8.0;
        private static readonly int[] BotRates = { 60 };
#else
        private const double BotSeconds = 45.0;
        private static readonly int[] BotRates = { 30, 60, 144 };
#endif

        private const double Eps = Tuning.EventEpsilonSeconds;

        private static RuleTraits AllKill => RuleTraits.Parse("KillInheritance;KillSpeedBoost;KillShield");

        private static RuleTraits AllEleven => RuleTraits.Parse(
            "Inertia(420);Coalescence(2);SparkSpeed(2.1);Propagation(4,1);ScorchedEarth(15);Conduction(1.3);ArcReach(1.4);"
            + "RingInterval(10);KillInheritance(1);KillSpeedBoost(0.1,0.3);KillShield(3)");

        private static RuleTraits BiomeSet(string name)
        {
            switch (name)
            {
                case "Liquide": return TraitTestKit.Liquid;
                case "Feu": return TraitTestKit.Fire;
                default: return TraitTestKit.Electric;
            }
        }

        // ============================================================================================================
        // The oracle: an independent reading of section 7 checked at every event and after every tick.
        // ============================================================================================================

        /// <summary>
        /// Follows a simulation through its events and checks section 7 independently of the trait code:
        /// - Cut: the victim is not shielded according to the announced shield events; the new spark runs at exactly
        ///   SparkSpeedOf(the victim's multiplier as announced by SpeedBoosted events).
        /// - Rewards: every reward follows a Spark elimination of the same step, its killer is alive when it is paid, the
        ///   inherited cells are freed cells now owned by the killer (round(Share x n) of them, never scorched), the boost
        ///   is min(1 + Cap, m + PerKill), the shield ends at max(previous end, t_kill + Duration) and leaves no spark.
        /// - After the tick: a kill whose killer is still alive (or died later than the kill) got every enabled reward that
        ///   could act; the multiplier only changed through SpeedBoosted, the shield only through its events, no shield
        ///   outlived its end, and every cut of the tick took s_cut &lt;= L(t_cut) - HeadGrace.
        /// </summary>
        internal sealed class KillOracle
        {
            private sealed class KillRecord
            {
                public int Victim, Killer;
                public double Time;
                public int[] Cells;
                public bool Inherited, Boosted, Shielded;
            }

            private struct CutRecord
            {
                public int Victim;
                public double Time, S;
            }

            private readonly Simulation sim;
            private readonly bool inherit, boost, shield;
            private readonly double share, perKill, cap, duration;
            private readonly double[] mult, shieldEnd, lastShieldTime, lastShieldValue, lastCutTime;
            private readonly int[] exitCuts;   // Cut events on the current exit (cleared by Exit, Return and elimination)
            private readonly List<KillRecord> kills = new List<KillRecord>();
            private readonly List<CutRecord> cuts = new List<CutRecord>();
            private double tickStart;

            public int Kills, Inherited, Boosts, ShieldsStarted, ShieldsEnded, Extinguished, CutsChecked, ReturnsChecked, LostLoops;

            public KillOracle(Simulation sim)
            {
                this.sim = sim;
                RuleTraits t = sim.View.Traits;
                TraitSpec i = t.Get(TraitId.KillInheritance), b = t.Get(TraitId.KillSpeedBoost), s = t.Get(TraitId.KillShield);
                inherit = i != null;
                share = inherit ? i.P1 : 0.0;
                boost = b != null;
                perKill = boost ? b.P1 : 0.0;
                cap = boost ? b.P2 : 0.0;
                shield = s != null;
                duration = shield ? s.P1 : 0.0;
                int n = sim.Players.Count;
                mult = new double[n];
                shieldEnd = new double[n];
                lastShieldTime = new double[n];
                lastShieldValue = new double[n];
                lastCutTime = new double[n];
                exitCuts = new int[n];
                for (int k = 0; k < n; k++)
                {
                    mult[k] = sim.Players[k].SpeedMultiplier;
                    shieldEnd[k] = sim.Players[k].ShieldEnd;
                    lastShieldTime[k] = double.NaN;
                    lastShieldValue[k] = double.NegativeInfinity;
                }
                for (int k = 0; k < n; k++) lastCutTime[k] = double.NaN;
                SyncDebugCuts();
                tickStart = sim.Time;
                // Registered after the test's own BeforeTick hooks, so it sees the Debug* calls they make.
                sim.BeforeTick += x =>
                {
                    tickStart = x.Time;
                    SyncDebugCuts();
                };
                sim.EventRaised += OnEvent;
            }

            /// <summary>
            /// Test hooks (DebugForceCut, DebugSetTrail) change exits without events: a spark that no Cut event announced
            /// counts as a cut of the current exit, and an exit no longer cut (a new trail) forgets its cuts.
            /// </summary>
            private void SyncDebugCuts()
            {
                for (int i = 0; i < sim.Players.Count; i++)
                {
                    PlayerState p = sim.Players[i];
                    if (p.Spark != null && !(p.Spark.TimeCut == lastCutTime[i]))
                    {
                        exitCuts[i]++;
                        lastCutTime[i] = p.Spark.TimeCut;
                    }
                    else if (!p.ExitWasCut && p.Spark == null) exitCuts[i] = 0;
                }
            }

            public string Summary => "kills " + Kills + ", inherited " + Inherited + ", boosts " + Boosts + ", shields " + ShieldsStarted
                                     + " (ended " + ShieldsEnded + ", extinguished " + Extinguished + "), cuts checked " + CutsChecked
                                     + ", returns checked " + ReturnsChecked + " (" + LostLoops + " lost loops without a spark)";

            private void Fail(string message)
            {
                Assert.Fail("kill oracle, tick " + sim.Tick + ": " + message);
            }

            private KillRecord Find(SimEvent e)
            {
                for (int k = 0; k < kills.Count; k++)
                {
                    KillRecord r = kills[k];
                    if (r.Victim == e.Other && r.Killer == e.Player && r.Time == e.Time) return r;
                }
                Fail("a reward without a Spark elimination of its victim at the same instant in this tick: " + e);
                return null;
            }

            private void OnEvent(SimEvent e)
            {
                string at = e + ": ";
                switch (e.Type)
                {
                    case SimEventType.Cut:
                    {
                        PlayerState v = sim.Players[e.Player];
                        if (shieldEnd[e.Player] > double.NegativeInfinity) Fail(at + "cut on a trail announced shielded until " + shieldEnd[e.Player]);
                        if (v.Shielded) Fail(at + "cut on a shielded player");
                        if (v.Spark == null) Fail(at + "no spark after the cut");
                        if (v.SpeedMultiplier != mult[e.Player]) Fail(at + "the victim's multiplier moved without SpeedBoosted");
                        double expected = sim.Config.SparkSpeedOf(mult[e.Player]);
                        if (v.Spark.Speed != expected) Fail(at + "Spark.Speed " + v.Spark.Speed + " != SparkSpeedOf(victim multiplier) " + expected);
                        cuts.Add(new CutRecord { Victim = e.Player, Time = e.Time, S = e.S });
                        exitCuts[e.Player]++;
                        lastCutTime[e.Player] = e.Time;
                        break;
                    }
                    case SimEventType.Exit:
                        exitCuts[e.Player] = 0;
                        break;
                    case SimEventType.Return:
                    {
                        // 7.1 "cut exits never capture", read from the events alone: a return is chased iff its exit was
                        // cut, except the R14 cancellation (a cut less than eps before the return) of the exit's FIRST cut.
                        int cutCount = exitCuts[e.Player];
                        exitCuts[e.Player] = 0;
                        double sinceCut = e.Time - lastCutTime[e.Player];
                        // The engine measures from the return's own u, which may lie up to eps after the group time: a
                        // gap right at eps is ambiguous and skipped.
                        if (cutCount > 0 && sinceCut >= 0.9 * Eps && sinceCut <= 1.1 * Eps) break;
                        bool closure = cutCount > 0 && sinceCut >= 0.0 && sinceCut < Eps;
                        bool expected = cutCount > 1 || (cutCount == 1 && !closure);
                        if (e.Chased != expected)
                            Fail(at + "Return.Chased " + e.Chased + " but the exit had " + cutCount + " cut(s), the last " + sinceCut + " s before");
                        if (e.Chased && sim.Players[e.Player].Captures < 0) Fail(at + "negative captures");
                        ReturnsChecked++;
                        if (e.Chased && e.Margin == 0.0) LostLoops++;
                        break;
                    }
                    case SimEventType.Eliminated:
                        exitCuts[e.Player] = 0;
                        shieldEnd[e.Player] = double.NegativeInfinity;
                        if (e.Cause == EliminationCause.Spark && e.Other >= 0)
                        {
                            Kills++;
                            kills.Add(new KillRecord { Victim = e.Player, Killer = e.Other, Time = e.Time, Cells = e.Cells });
                        }
                        break;
                    case SimEventType.TerritoryInherited:
                    {
                        KillRecord k = Find(e);
                        PlayerState killer = sim.Players[e.Player];
                        if (!inherit) Fail(at + "without KillInheritance");
                        if (!killer.Alive) Fail(at + "a dead killer inherits");
                        if (k.Inherited) Fail(at + "inherited twice");
                        k.Inherited = true;
                        Inherited++;
                        if (!IsSubset(e.Cells, k.Cells)) Fail(at + "inherited cells outside the victim's freed cells");
                        int keep = (int)Math.Floor(share * k.Cells.Length + 0.5);
                        if (e.Cells.Length != Math.Min(keep, k.Cells.Length))
                            Fail(at + e.Cells.Length + " cells inherited, round(Share x " + k.Cells.Length + ") = " + keep);
                        for (int c = 0; c < e.Cells.Length; c++)
                        {
                            if (sim.Grid.Cells[e.Cells[c]] != killer.Id) Fail(at + "an inherited cell is not the killer's");
                            if (sim.View.IsScorched(e.Cells[c])) Fail(at + "an inherited cell is scorched");
                        }
                        break;
                    }
                    case SimEventType.SpeedBoosted:
                    {
                        KillRecord k = Find(e);
                        PlayerState killer = sim.Players[e.Player];
                        if (!boost) Fail(at + "without KillSpeedBoost");
                        if (!killer.Alive) Fail(at + "a dead killer is boosted");
                        if (k.Boosted) Fail(at + "boosted twice for one kill");
                        double expected = Math.Min(1.0 + Math.Max(0.0, cap), mult[e.Player] + perKill);
                        if (e.Value != expected) Fail(at + "Value " + e.Value + " != min(1 + Cap, m + PerKill) " + expected);
                        if (killer.SpeedMultiplier != e.Value) Fail(at + "the multiplier is not the announced value");
                        mult[e.Player] = e.Value;
                        k.Boosted = true;
                        Boosts++;
                        break;
                    }
                    case SimEventType.ShieldStarted:
                    {
                        KillRecord k = Find(e);
                        PlayerState killer = sim.Players[e.Player];
                        if (!shield) Fail(at + "without KillShield");
                        if (!killer.Alive) Fail(at + "a dead killer is shielded");
                        double expected = Math.Max(shieldEnd[e.Player], e.Time + duration);
                        if (e.Value != expected) Fail(at + "end " + e.Value + " != max(previous end, t_kill + Duration) " + expected);
                        if (!killer.Shielded || killer.ShieldEnd != e.Value) Fail(at + "the killer's shield is not the announced one");
                        if (killer.Spark != null) Fail(at + "a spark survived the shield");
                        if (e.Chased)
                        {
                            Extinguished++;
                            if (!killer.ExitWasCut) Fail(at + "an extinguished spark must leave ExitWasCut set (the loop stays lost)");
                        }
                        shieldEnd[e.Player] = e.Value;
                        lastShieldTime[e.Player] = e.Time;
                        lastShieldValue[e.Player] = e.Value;
                        k.Shielded = true;
                        ShieldsStarted++;
                        break;
                    }
                    case SimEventType.ShieldEnded:
                        if (!shield) Fail(at + "without KillShield");
                        if (shieldEnd[e.Player] != e.Value) Fail(at + "ShieldEnded for an end the events never announced (" + shieldEnd[e.Player] + ")");
                        if (Math.Abs(e.Time - e.Value) > 1e-9) Fail(at + "not at its end time");
                        if (e.Time < tickStart - 1e-9) Fail(at + "a shield ended in a later tick than its end time");
                        if (sim.Players[e.Player].Shielded) Fail(at + "still shielded after ShieldEnded");
                        shieldEnd[e.Player] = double.NegativeInfinity;
                        ShieldsEnded++;
                        break;
                }
            }

            /// <summary>Call after every Step.</summary>
            public void Check()
            {
                double now = sim.Time;
                for (int i = 0; i < sim.Players.Count; i++)
                {
                    PlayerState p = sim.Players[i];
                    if (p.SpeedMultiplier != mult[i]) Fail("player " + i + ": multiplier " + p.SpeedMultiplier + " moved without SpeedBoosted");
                    if (p.Alive && p.ShieldEnd != shieldEnd[i]) Fail("player " + i + ": shield end " + p.ShieldEnd + " differs from its events " + shieldEnd[i]);
                    if (!sim.Ended && p.Alive && p.Shielded && p.ShieldEnd < now - 1e-9) Fail("player " + i + ": a shield outlived its end " + p.ShieldEnd);
                }
                for (int k = 0; k < kills.Count; k++)
                {
                    KillRecord r = kills[k];
                    PlayerState killer = sim.Players[r.Killer];
                    bool aliveAfter = killer.Alive || killer.EliminatedAt > r.Time;
                    if (!aliveAfter) continue;   // dead before the kill or at that instant: nothing is owed
                    string who = "kill of " + r.Victim + " by " + r.Killer + " at " + r.Time.ToString("R", CultureInfo.InvariantCulture) + ": ";
                    if (inherit && !r.Inherited && Math.Floor(share * r.Cells.Length + 0.5) > 0) Fail(who + "the surviving killer did not inherit");
                    if (boost && !r.Boosted && perKill > 0.0 && mult[r.Killer] != 1.0 + Math.Max(0.0, cap)) Fail(who + "no boost below the cap");
                    if (shield && !r.Shielded && duration > 0.0
                        && !(lastShieldTime[r.Killer] == r.Time && lastShieldValue[r.Killer] >= r.Time + duration))
                        Fail(who + "no shield");
                }
                kills.Clear();
                if (!sim.Ended)
                {
                    double span = now - tickStart;
                    for (int c = 0; c < cuts.Count; c++)
                    {
                        CutRecord cut = cuts[c];
                        PlayerState v = sim.Players[cut.Victim];
                        if (!v.Alive || v.Home || v.Spark == null || v.Spark.TimeCut != cut.Time || !(span > 0.0)) continue;
                        double moved = Vec2d.Distance(v.PrevPos, v.Pos);
                        double lengthAtCut = v.Trail.Length - moved * (now - cut.Time) / span;
                        if (cut.S > lengthAtCut - sim.Config.HeadGrace + 1e-6)
                            Fail("cut of " + cut.Victim + " at s " + cut.S + " inside HeadGrace (L at the cut " + lengthAtCut + ")");
                        CutsChecked++;
                    }
                }
                cuts.Clear();
            }
        }

        private sealed class AuditRun
        {
            public int Rate;
            public Simulation Sim;
            public EventLog Log;
            public KillOracle Oracle;
        }

        /// <summary>
        /// Runs build(rate) at 30, 60 and 144 Hz until runUntil with the trait invariants and the oracle every tick, calls
        /// check, and asserts identical outcomes: events, times within 1e-6 s, ranks, every event's Cells, Cut S, Value and
        /// Chased.
        /// </summary>
        private static List<AuditRun> CrossRateAudit(string label, Func<int, Simulation> build, double runUntil, Action<AuditRun> check)
        {
            var runs = new List<AuditRun>();
            foreach (int rate in CrossRates)
            {
                Simulation sim = build(rate);
                var oracle = new KillOracle(sim);
                var log = new EventLog(sim);
                int guard = 0;
                while (!sim.Ended && sim.Time < runUntil - 1e-9)
                {
                    sim.Step();
                    TraitTestKit.AssertTraitInvariants(sim);
                    oracle.Check();
                    if (++guard > 1000000) Assert.Fail(label + ": no end");
                }
                var run = new AuditRun { Rate = rate, Sim = sim, Log = log, Oracle = oracle };
                check?.Invoke(run);
                runs.Add(run);
            }
            var reference = new Outcome(runs[0].Rate, runs[0].Log, runs[0].Sim);
            for (int r = 1; r < runs.Count; r++)
            {
                var other = new Outcome(runs[r].Rate, runs[r].Log, runs[r].Sim);
                AssertSameOutcome(reference, other, label);
                string ctx = label + " (" + runs[0].Rate + " Hz vs " + runs[r].Rate + " Hz): event ";
                for (int k = 0; k < reference.Events.Count; k++)
                {
                    SimEvent x = reference.Events[k], y = other.Events[k];
                    if (!SameCells(x.Cells, y.Cells)) Assert.Fail(ctx + k + " " + x.Type + ": Cells differ");
                    if (Math.Abs(x.S - y.S) > 1e-6) Assert.Fail(ctx + k + " " + x.Type + ": S " + x.S + " vs " + y.S);
                    if (Math.Abs(x.Value - y.Value) > 1e-6) Assert.Fail(ctx + k + " " + x.Type + ": Value " + x.Value + " vs " + y.Value);
                    if (x.Chased != y.Chased) Assert.Fail(ctx + k + " " + x.Type + ": Chased differs");
                }
            }
            return runs;
        }

        private static string At(AuditRun run) => run.Rate + " Hz: ";

        private static void AssertNoReward(EventLog log, int player, string message)
        {
            Assert.AreEqual(0, log.Count(SimEventType.TerritoryInherited, player), message + ": TerritoryInherited\n" + log.Dump());
            Assert.AreEqual(0, log.Count(SimEventType.SpeedBoosted, player), message + ": SpeedBoosted");
            Assert.AreEqual(0, log.Count(SimEventType.ShieldStarted, player), message + ": ShieldStarted");
        }

        // ============================================================================================================
        // 1. Classic bit-identity
        // ============================================================================================================

        /// <summary>
        /// (a) Classic bot rounds at every rate: on every tick every player keeps SpeedMultiplier 1.0 and no shield,
        /// ExitWasCut equals "has a spark", every spark runs at exactly SimConfig.SparkSpeed (bit for bit) and no event
        /// has a trait type or a Value. (b) The three kill traits present but DISABLED with parameters that would be
        /// invalid, with SparkFollowsVictimSpeed false, reproduce the classic rolling hash (C042710F17995DCB since rule v1.5,
        /// the pre-trait 8CB763231AC73608 with SeveredTerritory = Off).
        /// </summary>
        [Test]
        public void KillAudit_1_ClassicRoundsNeverTouchTheKillStateAndKeepThePreTraitHash()
        {
            int sparkTicks = 0;
            // Rule v1.8 (contract 32) changed the seed 5 rounds (no spark any more in their first 45 s): seeds 6 and 7 are
            // added so the non-vacuity floor below still has sparks to check.
            foreach (ulong seed in new[] { 5UL, 6UL, 7UL })
            foreach (int rate in BotRates)
            {
                Simulation sim = TraitTestKit.BotRound(seed, RuleTraits.Classic, true, rate, -1, BotSeconds);
                double sparkSpeed = sim.Config.SparkSpeed;
                while (!sim.Ended)
                {
                    sim.Step();
                    for (int i = 0; i < sim.Players.Count; i++)
                    {
                        PlayerState p = sim.Players[i];
                        string who = rate + " Hz tick " + sim.Tick + " player " + i + ": ";
                        if (p.SpeedMultiplier != 1.0) Assert.Fail(who + "SpeedMultiplier " + p.SpeedMultiplier);
                        if (p.ShieldEnd != double.NegativeInfinity || p.Shielded) Assert.Fail(who + "shielded");
                        if (p.ExitWasCut != (p.Spark != null)) Assert.Fail(who + "ExitWasCut != has a spark");
                        if (p.Spark != null)
                        {
                            sparkTicks++;
                            if (p.Spark.Speed != sparkSpeed) Assert.Fail(who + "Spark.Speed " + p.Spark.Speed + " != SparkSpeed " + sparkSpeed);
                        }
                    }
                    IReadOnlyList<SimEvent> events = sim.LastEvents;
                    for (int k = 0; k < events.Count; k++)
                    {
                        // TerritorySevered (appended after the trait events) is the core rule v1.5 (contract 29), not a trait
                        // event: it belongs to classic rounds too.
                        bool traitType = events[k].Type >= SimEventType.TerritoryGrew && events[k].Type != SimEventType.TerritorySevered;
                        if (traitType || events[k].Value != 0.0)
                            Assert.Fail(rate + " Hz tick " + sim.Tick + ": trait event in a classic round: " + events[k]);
                    }
                }
            }
#if !UNITY_5_3_OR_NEWER
            Assert.That(sparkTicks, Is.GreaterThan(0), "the classic rounds had sparks to check");
#endif

            var disabled = new RuleTraits(new[]
            {
                new TraitSpec(TraitId.KillInheritance, -1.0, double.NaN, false), new TraitSpec(TraitId.KillSpeedBoost, -1.0, -1.0, false),
                new TraitSpec(TraitId.KillShield, -1.0, double.NaN, false),
            });
            Assert.IsTrue(disabled.IsClassic);
            Assert.AreEqual("", disabled.ToKey());
            var controllers = new IController[4];
            for (int i = 0; i < 4; i++)
                controllers[i] = new BotController(BotPersonality.Preset(TraitTestKit.Lineup[i]), BotTests.BotSeed(1UL, i));
            var config = new SimConfig { Seed = 1UL, TickRate = 60, LassoEnabled = true, Traits = disabled, SparkFollowsVictimSpeed = false };
            var round = new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
            Assert.AreEqual(0, round.KillTraitCount(), "no kill trait attached");
            // Rule v1.5 (contract 29): the default SeveredTerritory (Neutral) severs territory in this round, so the classic
            // rolling hash is C042710F17995DCB; with SeveredTerritory = Off it is the pre-trait 8CB763231AC73608
            // (TraitsClassicTests pins both). Rule v1.8 (contract 32): C042710F17995DCB is now the value with SingleDomain =
            // Off; the default is TraitsClassicTests.ClassicSeed1V18.
            Assert.AreEqual(TraitsClassicTests.ClassicSeed1V18.ToString("X16"), TraitTestKit.RollingRoundHash(round, 30, false).ToString("X16"),
                            "disabled kill traits must reproduce the classic rolling hash");
        }

        // ============================================================================================================
        // 2. Each kill trait moved to every biome
        // ============================================================================================================

        private static IEnumerable<object[]> MoveCases()
        {
            string[] biomes = { "Liquide", "Feu", "Electricite" };
            TraitId[] killIds = { TraitId.KillInheritance, TraitId.KillSpeedBoost, TraitId.KillShield };
            for (int b = 0; b < biomes.Length; b++)
            {
                for (int k = 0; k < killIds.Length; k++)
                {
#if UNITY_5_3_OR_NEWER
                    if (k != b) continue;   // Liquide + KillInheritance, Feu + KillSpeedBoost, Electricite + KillShield (all moved)
#endif
                    yield return new object[] { biomes[b], (int)killIds[k] };
                }
            }
        }

        /// <summary>
        /// For every kill trait and every section 3 biome set (the default table puts each kill trait in only one): the
        /// set plus the kill trait applies exactly the biome's config (kill traits are behaviour only), is deterministic
        /// (twin StateHash every 30 ticks), keeps the trait invariants and the kill oracle on every tick of a bot round,
        /// and the same set with the kill trait DISABLED evolves bit for bit like the biome set.
        /// </summary>
        [TestCaseSource(nameof(MoveCases))]
        public void KillAudit_2_EachKillTraitMovesToAnyBiomeAndSwitchesOffCleanly(string biome, int killId)
        {
            var id = (TraitId)killId;
            RuleTraits baseSet = BiomeSet(biome);
            RuleTraits moved = baseSet.With(new TraitSpec(id));
            RuleTraits off = moved.With(new TraitSpec(id, double.NaN, double.NaN, false));
            string label = biome + " + " + id;
            Assert.IsTrue(moved.Has(id), label);
            Assert.AreEqual(baseSet.EnabledCount + 1, moved.EnabledCount, label);
            Assert.AreEqual(baseSet.ToKey(), off.ToKey(), label + ": a disabled kill trait leaves the key");
            Assert.AreEqual(moved, RuleTraits.Parse(moved.ToKey()), label + ": key round trip");

            const ulong seed = 21UL;
            Simulation a = TraitTestKit.BotRound(seed, moved, true, 60, -1, BotSeconds);
            Simulation twin = TraitTestKit.BotRound(seed, moved, true, 60, -1, BotSeconds);
            Simulation reference = TraitTestKit.BotRound(seed, baseSet, true, 60, -1, BotSeconds);
            AssertSameAppliedConfig(reference.Config, a.Config, label);
            Assert.AreEqual(1, a.KillTraitCount(), label + ": one kill trait attached");

            var oracle = new KillOracle(a);
            while (!a.Ended || !twin.Ended)
            {
                if (a.Ended != twin.Ended) Assert.Fail(label + ": the twin ended at another tick");
                a.Step();
                twin.Step();
                TraitTestKit.AssertTraitInvariants(a);
                oracle.Check();
                if ((a.Tick % 30 == 0 || a.Ended) && a.StateHash() != twin.StateHash()) Assert.Fail(label + ": twin StateHash differs at tick " + a.Tick);
            }

            TraitsAuditTests.AssertSameEvolution(label + " (disabled) vs " + biome,
                                                 TraitTestKit.BotRound(seed, off, true, 60, -1, BotSeconds),
                                                 TraitTestKit.BotRound(seed, baseSet, true, 60, -1, BotSeconds), true);
        }

        /// <summary>Every public SimConfig field except Traits is equal (the applied config of two trait sets).</summary>
        private static void AssertSameAppliedConfig(SimConfig expected, SimConfig actual, string label)
        {
            foreach (FieldInfo f in typeof(SimConfig).GetFields(BindingFlags.Public | BindingFlags.Instance))
            {
                if (f.Name == nameof(SimConfig.Traits)) continue;
                Assert.AreEqual(f.GetValue(expected), f.GetValue(actual), label + ": SimConfig." + f.Name + " changed by a kill trait");
            }
        }

        // ============================================================================================================
        // 3. Kill attribution
        // ============================================================================================================

        /// <summary>The section 3 kill catch time: not a tick time at 30, 60 or 144 Hz.</summary>
        private const double KillTime = 1.013;

        /// <summary>
        /// Victim (player 0, land [-28, -24] x [20, 24]) trails East on y = H from x = -10 (L = 10 at t = 0). Players 1 and 2
        /// head North on x1 and x2 and come within ContactRadius of the line y = H at t = 0.5. With sharedPath, player 2
        /// starts trailing at player 1's start (its land is a disc far away) and moves in lockstep with it: its exposed
        /// trail stays 1.0 behind both heads, so neither cuts the other, and both touch the victim's trail at the same point
        /// at the same instant. Player 3 idles.
        /// </summary>
        private static Simulation TwoCutters(int rate, RuleTraits traits, double x1, double x2, bool sharedPath)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-28, 20, -24, 24, V(-26 + H, 22 + H), East, new ConstantHeadingController(East));
            double y0 = H - 0.63 - 6.0 * 0.5;
            sb.AddRect(x1 - 1.0625, y0 - 2.0, x1 + 0.9375, y0 + 0.75, V(x1, y0), North, new ConstantHeadingController(North));
            if (sharedPath) sb.AddDisc(IdleCorners[2], Tuning.StartDiscRadius, V(x2, y0), North, new ConstantHeadingController(North));
            else sb.AddRect(x2 - 1.0625, y0 - 2.0, x2 + 0.9375, y0 + 0.75, V(x2, y0), North, new ConstantHeadingController(North));
            sb.AddIdle(IdleCorners[1]);
            Simulation sim = sb.Build();
            sim.DebugSetTrail(0, new[] { V(-10, H), V(0, H) });
            return sim;
        }

        /// <summary>The spark spawned at s = 7.0625 at t = 0.5 (L = 13) reaches the head at t = 0.5 + 5.9375 / 4.8.</summary>
        private const double TwoCuttersCatch = 0.5 + 5.9375 / 4.8;

        [TestCase(false)]
        [TestCase(true)]
        public void KillAudit_3_OnlyTheCutterRetainedByR11IsRewarded(bool tie)
        {
            // Not a tie: player 1 touches at s = 4.0625, player 2 at s = 7.0625: the LARGEST s_cut wins (player 2, the
            // higher index, so "lowest index" would pick the wrong one). Tie: both touch s = 7.0625: the lowest index wins.
            int winner = tie ? 1 : 2, loser = tie ? 2 : 1;
            double x1 = tie ? -3 + H : -6 + H;
            CrossRateAudit("R11 attribution tie=" + tie, rate => TwoCutters(rate, AllKill, x1, -3 + H, tie), 2.0, run =>
            {
                string at = At(run) + (tie ? "tie: " : "largest s: ");
                Simulation sim = run.Sim;
                SimEvent cut = run.Log.Single(SimEventType.Cut, 0);
                Assert.AreEqual(winner, cut.Other, at + "the retained cutter");
                Assert.That(cut.Time, Is.EqualTo(0.5).Within(1e-9), at + "both contacts at t = 0.5");
                Assert.That(cut.S, Is.EqualTo(7 + H).Within(1e-9), at + "s_cut");
                SimEvent caught = run.Log.Single(SimEventType.SparkCaught, 0);
                Assert.AreEqual(winner, caught.Other, at + "the killer is Spark.Attacker");
                Assert.That(caught.Time, Is.EqualTo(TwoCuttersCatch + Eps).Within(1e-6), at + "catch");
                SimEvent dead = run.Log.Single(SimEventType.Eliminated, 0);
                Assert.AreEqual(1024, dead.Cells.Length);
                Assert.IsTrue(SameCells(dead.Cells, run.Log.Single(SimEventType.TerritoryInherited, winner).Cells), at + "the winner inherits");
                Assert.AreEqual(1.1, run.Log.Single(SimEventType.SpeedBoosted, winner).Value, 1e-12, at + "the winner is boosted");
                Assert.AreEqual(1, run.Log.Count(SimEventType.ShieldStarted, winner), at + "the winner is shielded");
                AssertNoReward(run.Log, loser, at + "the other cutter");
                Assert.AreEqual(1, sim.Players[winner].CutsMade);
                Assert.AreEqual(0, sim.Players[loser].CutsMade);
                Assert.AreEqual(1, sim.Players[winner].Kills);
                Assert.AreEqual(0, sim.Players[loser].Kills);
                Assert.AreEqual(1.0, sim.Players[loser].SpeedMultiplier);
                Assert.IsFalse(sim.View.IsShielded(loser));
                // Rule v1.6 (contract 30): the victim's trail was teleported away from its land (DebugSetTrail), so the kill
                // line does not reach the inherited land: no bridge, the single-domain rule severs it from the winner.
                Assert.AreEqual(0, run.Log.Count(SimEventType.InheritanceBridged), at + "no bridge");
                SimEvent severed = run.Log.Single(SimEventType.TerritorySevered, winner);
                Assert.AreEqual(-1, severed.Other, at + "severed by the single-domain rule");
                Assert.IsTrue(SameCells(dead.Cells, severed.Cells), at + "the inherited land is severed");
                Assert.AreEqual(1024, TraitTestKit.CountOwned(sim.Grid, dead.Cells, OwnerGrid.Neutral));
            });
        }

        /// <summary>A crosses x = 0 into its land at t = 2.0925 / 6 and its return encloses all of B's land (R9).</summary>
        private const double CaptureTime = 2.0925 / 6.0;

        /// <summary>
        /// A (player 0) returns at CaptureTime and encloses the whole land of B (player 1, home, heading North): B is
        /// eliminated by TerritoryLost. With catchIn &gt; 0, B's spark catches V (player 2, land [20, 24] x [-24, -20])
        /// catchIn seconds after t = 0. Player 3 idles.
        /// </summary>
        private static Simulation KillerCaptured(int rate, RuleTraits traits, double catchIn,
                                                 InheritanceBridgeRule bridge = InheritanceBridgeRule.Bridge)
        {
            var b = new SimBuilder(rate);
            b.Config.Traits = traits;
            b.Config.InheritanceBridge = bridge;
            // Rule v1.8 (contract 32): the pre-v1.6 island (InheritanceBridge = Off) needs SingleDomain = Off.
            if (bridge == InheritanceBridgeRule.Off) b.Config.SingleDomain = SingleDomainRule.Off;
            b.AddRect(-8, -8, 0, 8, V(-4, H), West, new ConstantHeadingController(West));
            b.AddRect(6, -3, 9, 3, V(7 + H, -2.4375), North, new ConstantHeadingController(North));
            b.AddRect(20, -24, 24, -20, V(22 + H, -22 + H), East, new ConstantHeadingController(East));
            b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 6 + H), V(10 + H, 6 + H), V(10 + H, -6 + H), V(2.0925, -6 + H) });
            if (catchIn > 0.0) KillTestKit.ForceChase(sim, 2, 1, V(-20 + H, 20 + H), 10.0, catchIn);
            return sim;
        }

        private static RuleTraits AllKillScorched => RuleTraits.Parse("ScorchedEarth;KillInheritance;KillSpeedBoost;KillShield");

        [Test]
        public void KillAudit_3_AKillerCapturedToDeathBeforeOrInTheSameGroupIsNotRewarded()
        {
            // (i) B dies (TerritoryLost) at CaptureTime, its spark catches V later: Kills credited (R12), nothing paid, the
            // land stays neutral and is scorched.
            CrossRateAudit("killer captured before", rate => KillerCaptured(rate, AllKillScorched, 0.6), 0.7, run =>
            {
                string at = At(run) + "before: ";
                Simulation sim = run.Sim;
                Assert.AreEqual(EliminationCause.TerritoryLost, run.Log.Single(SimEventType.Eliminated, 1).Cause, at);
                SimEvent dead = run.Log.Single(SimEventType.Eliminated, 2);
                Assert.AreEqual(1, dead.Other, at + "killed by B's spark");
                Assert.That(dead.Time, Is.EqualTo(0.6 + Eps).Within(1e-6));
                AssertNoReward(run.Log, 1, at + "dead killer");
                Assert.AreEqual(1, sim.Players[1].Kills, at + "Kills credited even if dead (R12)");
                Assert.AreEqual(dead.Cells.Length, TraitTestKit.CountOwned(sim.Grid, dead.Cells, OwnerGrid.Neutral), at + "neutral land");
                foreach (int c in dead.Cells) Assert.IsTrue(sim.View.IsScorched(c), at + "scorched");
            });

            // (ii) The catch lands 0.5 eps after A's return: one group. Step a eliminates B, step b kills V: B is dead
            // after the group, nothing is paid.
            CrossRateAudit("killer captured in the same group", rate => KillerCaptured(rate, AllKillScorched, CaptureTime - 0.5 * Eps), 0.5, run =>
            {
                string at = At(run) + "same group: ";
                Simulation sim = run.Sim;
                SimEvent lost = run.Log.Single(SimEventType.Eliminated, 1);
                SimEvent dead = run.Log.Single(SimEventType.Eliminated, 2);
                Assert.AreEqual(EliminationCause.TerritoryLost, lost.Cause, at);
                Assert.AreEqual(lost.Time, dead.Time, at + "one group");
                Assert.That(run.Log.IndexOf(lost), Is.LessThan(run.Log.IndexOf(dead)), at + "step a before step b");
                Assert.AreEqual(1, dead.Other);
                AssertNoReward(run.Log, 1, at + "killer eliminated in the same group");
                Assert.AreEqual(dead.Cells.Length, TraitTestKit.CountOwned(sim.Grid, dead.Cells, OwnerGrid.Neutral), at + "neutral land");
            });

            // (iii) Control: the kill comes first (t = 0.2). B inherits V's land, so A's capture of its own land no longer
            // eliminates it: its home cell is stolen, it exits and survives with the inherited land. Run with the pre-v1.6
            // island behaviour (InheritanceBridge = Off): under rule v1.6 the far inherited land (a forced cut makes no
            // bridge) is severed at once and A's capture then eliminates B, which would remove the control.
            CrossRateAudit("killer rewarded before the capture", rate => KillerCaptured(rate, AllKillScorched, 0.2, InheritanceBridgeRule.Off), 0.6, run =>
            {
                string at = At(run) + "control: ";
                Simulation sim = run.Sim;
                SimEvent dead = run.Log.Single(SimEventType.Eliminated, 2);
                SimEvent inherited = run.Log.Single(SimEventType.TerritoryInherited, 1);
                Assert.IsTrue(SameCells(dead.Cells, inherited.Cells), at + "B inherits V's land");
                Assert.AreEqual(0, run.Log.Count(SimEventType.Eliminated, 1), at + "the inheritance saved B from TerritoryLost");
                Assert.AreEqual(1, run.Log.Count(SimEventType.TerritoryStolen, 1), at + "its home cell was taken");
                Assert.IsTrue(sim.Players[1].Alive);
                Assert.IsFalse(sim.Players[1].Home, at + "B exited");
                Assert.AreEqual(dead.Cells.Length, sim.Grid.CountOf(sim.Players[1].Id), at + "B owns exactly the inherited land");
                foreach (int c in dead.Cells) Assert.IsFalse(sim.View.IsScorched(c), at + "inherited land is not scorched");
            });
        }

        [Test]
        public void KillAudit_3_ATerritoryLostEliminationNeverPaysAnyKillReward()
        {
            CrossRateAudit("TerritoryLost", rate => KillerCaptured(rate, AllKillScorched, -1.0), 0.5, run =>
            {
                string at = At(run);
                Simulation sim = run.Sim;
                SimEvent lost = run.Log.Single(SimEventType.Eliminated, 1);
                Assert.AreEqual(EliminationCause.TerritoryLost, lost.Cause, at);
                Assert.AreEqual(0, lost.Other, at + "A took the last cell");
                AssertNoReward(run.Log, 0, at + "the capturer");
                Assert.AreEqual(0, sim.Players[0].Kills, at + "not a kill");
                Assert.AreEqual(1.0, sim.Players[0].SpeedMultiplier, at);
                Assert.IsFalse(sim.View.IsShielded(0), at);
            });
        }

        /// <summary>
        /// The killer (player 0) circles at home in [-10, 0] x [-4, 4]; victims 1 ([0, 8] x [-4, 4]) and 2 ([10, 14] x
        /// [10, 14]) are caught by its sparks at the same instant (identical closed forms). Player 3 idles.
        /// </summary>
        private static Simulation TwoVictims(int rate, RuleTraits traits)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-10, -4, 0, 4, V(-5 + H, H), North, new HomeCirclerController(V(-5, 0)));
            sb.AddRect(0, -4, 8, 4, V(4 + H, H), East, new ConstantHeadingController(East));
            sb.AddRect(10, 10, 14, 14, V(12 + H, 12 + H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[1]);
            Simulation sim = sb.Build();
            KillTestKit.ForceChase(sim, 1, 0, V(-15 + H, -15 + H), 10.0, KillTime);
            KillTestKit.ForceChase(sim, 2, 0, V(-15 + H, -20 + H), 10.0, KillTime);
            return sim;
        }

        [Test]
        public void KillAudit_3_TwoVictimsAtOnceArePaidInKillOrderAndTheShieldStartsOnce()
        {
            CrossRateAudit("two victims", rate => TwoVictims(rate, AllKill), 1.2, run =>
            {
                string at = At(run);
                Simulation sim = run.Sim;
                SimEvent d1 = run.Log.Single(SimEventType.Eliminated, 1), d2 = run.Log.Single(SimEventType.Eliminated, 2);
                Assert.AreEqual(d1.Time, d2.Time, at + "one group");
                var order = new List<string>();
                int first = run.Log.IndexOf(run.Log.Single(SimEventType.SparkCaught, 1));
                for (int k = first; k < run.Log.All.Count && run.Log.All[k].Time == d1.Time; k++)
                    order.Add(run.Log.All[k].Type + "(" + run.Log.All[k].Player + "," + run.Log.All[k].Other + ")");
                // Rule v1.6 (contract 30): victim 1's land touches the killer's, victim 2's does not and a forced cut makes
                // no bridge, so it is severed right after its rewards (TerritorySevered, Other = -1).
                Assert.AreEqual(
                    "SparkCaught(1,0) Eliminated(1,0) SparkCaught(2,0) Eliminated(2,0) TerritoryInherited(0,1) SpeedBoosted(0,1) "
                    + "ShieldStarted(0,1) TerritoryInherited(0,2) SpeedBoosted(0,2) TerritorySevered(0,-1)", string.Join(" ", order),
                    at + "every elimination of the group, then the rewards in kill order and TraitId order");
                List<SimEvent> boosts = run.Log.Of(SimEventType.SpeedBoosted, 0);
                Assert.AreEqual(1.1, boosts[0].Value, 1e-12);
                Assert.AreEqual(1.2, boosts[1].Value, 1e-12, at + "the two kills stack");
                Assert.AreEqual(1.2, sim.Players[0].SpeedMultiplier, 1e-12);
                SimEvent shield = run.Log.Single(SimEventType.ShieldStarted, 0);
                Assert.AreEqual(d1.Time + 3.0, shield.Value, 1e-12, at + "one shield, t_kill + Duration");
                Assert.AreEqual(d1.Cells.Length, TraitTestKit.CountOwned(sim.Grid, d1.Cells, sim.Players[0].Id), at + "land of 1");
                Assert.IsTrue(SameCells(d2.Cells, run.Log.Single(SimEventType.TerritorySevered, 0).Cells), at + "land of 2 severed (v1.6)");
                Assert.AreEqual(d2.Cells.Length, TraitTestKit.CountOwned(sim.Grid, d2.Cells, OwnerGrid.Neutral), at + "land of 2 neutral");
                Assert.AreEqual(2, sim.Players[0].Kills);
            });
        }

        /// <summary>
        /// Player 0 (A) circles at home; player 2 (B, land [0, 8] x [-4, 4]) is chased by A's spark and player 1 (C, land
        /// [10, 14] x [10, 14]) by B's spark, both caught at the same instant. C has the lower index: step b eliminates it
        /// first, while B is still alive, then B. Player 3 idles.
        /// </summary>
        private static Simulation Chain(int rate, RuleTraits traits)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-10, -4, 0, 4, V(-5 + H, H), North, new HomeCirclerController(V(-5, 0)));
            sb.AddRect(10, 10, 14, 14, V(12 + H, 12 + H), East, new ConstantHeadingController(East));
            sb.AddRect(0, -4, 8, 4, V(4 + H, H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[1]);
            Simulation sim = sb.Build();
            KillTestKit.ForceChase(sim, 1, 2, V(-15 + H, -20 + H), 10.0, KillTime);
            KillTestKit.ForceChase(sim, 2, 0, V(-15 + H, -15 + H), 10.0, KillTime);
            return sim;
        }

        [Test]
        public void KillAudit_3_AChainInsideOneGroupPaysOnlyTheKillerAliveAfterTheGroup()
        {
            CrossRateAudit("chain", rate => Chain(rate, AllKillScorched), 1.2, run =>
            {
                string at = At(run);
                Simulation sim = run.Sim;
                SimEvent dc = run.Log.Single(SimEventType.Eliminated, 1), db = run.Log.Single(SimEventType.Eliminated, 2);
                Assert.AreEqual(dc.Time, db.Time, at + "one group");
                Assert.That(run.Log.IndexOf(dc), Is.LessThan(run.Log.IndexOf(db)), at + "C first, while its killer B is alive");
                Assert.AreEqual(2, dc.Other);
                Assert.AreEqual(0, db.Other);
                AssertNoReward(run.Log, 2, at + "B was alive at C's elimination but not after the group");
                Assert.IsTrue(SameCells(db.Cells, run.Log.Single(SimEventType.TerritoryInherited, 0).Cells), at + "A takes B's land only");
                Assert.AreEqual(1, run.Log.Count(SimEventType.SpeedBoosted, 0), at + "one boost for A");
                Assert.AreEqual(1, run.Log.Count(SimEventType.ShieldStarted, 0), at + "one shield for A");
                Assert.AreEqual(dc.Cells.Length, TraitTestKit.CountOwned(sim.Grid, dc.Cells, OwnerGrid.Neutral), at + "C's land is neutral");
                foreach (int c in dc.Cells) Assert.IsTrue(sim.View.IsScorched(c), at + "and scorched");
                Assert.AreEqual(1, sim.Players[2].Kills, at + "B's kill is still credited");
            });
        }

        /// <summary>
        /// K (player 0, land [-10, 0] x [-4, 4]) trails and is chased by X (player 2, idle at home) with a catch at t = 2.0;
        /// meanwhile K's spark kills V (player 1, land [0, 8] x [-4, 4]) at KillTime. Player 3 idles.
        /// </summary>
        private static Simulation Transitive(int rate, RuleTraits traits)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-10, -4, 0, 4, V(-5 + H, H), East, new ConstantHeadingController(East));
            sb.AddRect(0, -4, 8, 4, V(4 + H, H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[0]);
            sb.AddIdle(IdleCorners[2]);
            Simulation sim = sb.Build();
            KillTestKit.ForceChase(sim, 1, 0, V(-15 + H, -20 + H), 10.0, KillTime);
            KillTestKit.ForceChase(sim, 0, 2, V(-15 + H, -15 + H), 10.0, 2.0);
            return sim;
        }

        [Test]
        public void KillAudit_3_AChasedKillerKeepsItsInheritanceUntilItsOwnKillerTakesItAll()
        {
            CrossRateAudit("transitive inheritance", rate => Transitive(rate, RuleTraits.Parse("ScorchedEarth;KillInheritance")), 2.2, run =>
            {
                string at = At(run);
                Simulation sim = run.Sim;
                SimEvent first = run.Log.Single(SimEventType.TerritoryInherited, 0);
                SimEvent second = run.Log.Single(SimEventType.TerritoryInherited, 2);
                Assert.AreEqual(1, first.Other, at + "the chased killer K inherits V");
                Assert.AreEqual(0, second.Other, at + "X inherits K");
                Assert.That(second.Time, Is.EqualTo(2.0 + Eps).Within(1e-6));
                int[] kLand = TraitTestKit.RectCells(sim.Grid, -10, -4, 0, 4), vLand = TraitTestKit.RectCells(sim.Grid, 0, -4, 8, 4);
                Assert.AreEqual(kLand.Length + vLand.Length, second.Cells.Length, at + "K's land plus V's former land");
                // Rule v1.6 (contract 30): K inherits V's adjacent land (one domain); X's inheritance lies far from X's land
                // and X's spark was forced (no bridge): the single-domain rule severs all of it, plain neutral.
                Assert.AreEqual(0, run.Log.Count(SimEventType.TerritorySevered, 0), at + "K's domain stayed one piece");
                Assert.IsTrue(SameCells(second.Cells, run.Log.Single(SimEventType.TerritorySevered, 2).Cells), at + "X's inheritance is severed");
                Assert.AreEqual(vLand.Length, TraitTestKit.CountOwned(sim.Grid, vLand, OwnerGrid.Neutral), at + "V's former land is neutral");
                Assert.AreEqual(kLand.Length, TraitTestKit.CountOwned(sim.Grid, kLand, OwnerGrid.Neutral));
                foreach (int c in second.Cells) Assert.IsFalse(sim.View.IsScorched(c), at + "severed cells are never scorched");
            });
        }

        // ============================================================================================================
        // 4. KillInheritance against the other rules
        // ============================================================================================================

        /// <summary>
        /// Victim (player 0) owns [0, 8] x [-4, 4] and is teleported to a trail East on y = -15 + H (L = length) with a spark
        /// of the killer (player 1, home circling in [-10, 0] x [-4, 4]) that catches it at catchTime. Players 2, 3 idle.
        /// </summary>
        private static Simulation HomeKiller(int rate, RuleTraits traits, double catchTime, double length = 10.0, double fromX = -15 + H,
                                             InheritanceBridgeRule bridge = InheritanceBridgeRule.Bridge)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.Config.InheritanceBridge = bridge;
            // Rule v1.8 (contract 32): the pre-v1.6 island (InheritanceBridge = Off) needs SingleDomain = Off.
            if (bridge == InheritanceBridgeRule.Off) sb.Config.SingleDomain = SingleDomainRule.Off;
            sb.AddRect(0, -4, 8, 4, V(4 + H, H), East, new ConstantHeadingController(East));
            sb.AddRect(-10, -4, 0, 4, V(-5 + H, H), North, new HomeCirclerController(V(-5, 0)));
            sb.AddIdle(IdleCorners[2]);
            sb.AddIdle(IdleCorners[1]);
            Simulation sim = sb.Build();
            KillTestKit.ForceChase(sim, 0, 1, V(fromX, -15 + H), length, catchTime);
            return sim;
        }

        [Test]
        public void KillAudit_4_AShareKeepsTheRimScorchedAndPropagationNeverFillsIt()
        {
            // Share 0.5: the core of the land goes to the killer (owned, never scorched), the rim stays neutral and
            // scorched; the Propagation ring at t = 4 grows the killer's land (inherited core included) but never into a
            // scorched rim cell. With the pre-v1.6 island behaviour (InheritanceBridge = Off): under rule v1.6 the core,
            // which does not touch the killer's land, is severed at once (KillInheritanceTraitTests covers that case).
            RuleTraits traits = RuleTraits.Parse("Propagation(4,1);ScorchedEarth(15);KillInheritance(0.5)");
            CrossRateAudit("share + scorch + propagation", rate => HomeKiller(rate, traits, KillTime, 10.0, -15 + H, InheritanceBridgeRule.Off), 4.2, run =>
            {
                string at = At(run);
                Simulation sim = run.Sim;
                SimEvent dead = run.Log.Single(SimEventType.Eliminated, 0);
                SimEvent inherited = run.Log.Single(SimEventType.TerritoryInherited, 1);
                Assert.AreEqual(dead.Cells.Length / 2, inherited.Cells.Length, at + "round(0.5 x n)");
                SimEvent grew = run.Log.Single(SimEventType.TerritoryGrew, 1);
                Assert.That(grew.Time, Is.EqualTo(4.0).Within(1e-12));
                Assert.That(grew.Cells.Length, Is.GreaterThan(0));
                int rimLeft = 0;
                foreach (int c in dead.Cells)
                {
                    bool mine = TraitTestKit.Contains(inherited.Cells, c);
                    Assert.IsFalse(TraitTestKit.Contains(grew.Cells, c), at + "Propagation filled a freed cell (scorched or already owned)");
                    if (mine)
                    {
                        Assert.AreEqual(sim.Players[1].Id, sim.Grid.Cells[c], at + "inherited core");
                        Assert.IsFalse(sim.View.IsScorched(c), at + "the inherited core is not scorched");
                    }
                    else
                    {
                        Assert.AreEqual(OwnerGrid.Neutral, sim.Grid.Cells[c], at + "the rim stays neutral");
                        Assert.IsTrue(sim.View.IsScorched(c), at + "the rim is scorched");
                        rimLeft++;
                    }
                }
                Assert.AreEqual(dead.Cells.Length - inherited.Cells.Length, rimLeft);
                Assert.IsTrue(TraitTestKit.Contains(grew.Cells, CellIndex(sim.Grid, -10 - H, H)), at + "the killer's own land still grows");
            });
        }

        [Test]
        public void KillAudit_4_PropagationGrowsTheInheritedLandInTheSameTick()
        {
            // The kill lands in the last tick before t = 4 at every rate (3.995 + eps): the growth at that tick end already
            // starts from the inherited land (step 2 before step 3). Without the inheritance that cell stays neutral.
            RuleTraits traits = RuleTraits.Parse("Propagation(4,1);KillInheritance");
            CrossRateAudit("propagation same tick", rate => HomeKiller(rate, traits, 3.995, 25.0, -30 + H), 4.05, run =>
            {
                string at = At(run);
                Simulation sim = run.Sim;
                SimEvent inherited = run.Log.Single(SimEventType.TerritoryInherited, 1);
                SimEvent grew = run.Log.Single(SimEventType.TerritoryGrew, 1);
                // Same tick: the inheritance lies in the last tick before the growth instant (EventLog.Ticks cannot tell, the
                // Tick counter advances before the step 3 hooks run).
                Assert.That(inherited.Time, Is.GreaterThan(4.0 - 1.0 / run.Rate), at + "the kill is in the tick that ends at 4.0");
                Assert.That(run.Log.IndexOf(grew), Is.GreaterThan(run.Log.IndexOf(inherited)), at + "growth after the inheritance");
                int beyond = CellIndex(sim.Grid, 8 + H, H);
                Assert.IsTrue(TraitTestKit.Contains(grew.Cells, beyond), at + "the ring around the inherited land");
                Assert.AreEqual(sim.Players[1].Id, sim.Grid.Cells[beyond]);
            });
            Simulation control = HomeKiller(60, RuleTraits.Parse("Propagation(4,1)"), 3.995, 25.0, -30 + H);
            RunUntilTime(control, 4.05);
            Assert.AreEqual(OwnerGrid.Neutral, control.Grid.Cells[CellIndex(control.Grid, 8 + H, H)], "control: no inheritance, no growth there");
        }

        /// <summary>
        /// The S5 / S6 lasso path (SimTestKit.PocketScenario) with traits and two idle players: A (player 0, charged)
        /// closes a pocket at t = 3.5 over part of B's land (player 1, [6, 13] x [-6, -1]); its S leg runs through B's
        /// land from t = 4.344 to 4.677; it returns at x = 0 at PocketReturnTime. B is killed by A's spark at killAt
        /// (teleported far away, caught at that tick start).
        /// </summary>
        private static Simulation PocketKill(int rate, RuleTraits traits, double killAt,
                                             InheritanceBridgeRule bridge = InheritanceBridgeRule.Bridge)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.Config.InheritanceBridge = bridge;
            // Rule v1.8 (contract 32): the pre-v1.6 island (InheritanceBridge = Off) needs SingleDomain = Off.
            if (bridge == InheritanceBridgeRule.Off) sb.Config.SingleDomain = SingleDomainRule.Off;
            sb.AddRect(-12, -4, 0, 4, V(-1 + H, H), East,
                       Legs((East, 9), (South, 4), (West, 4), (North, 5), (East, 2), (South, 4), (West, 7)));
            sb.AddRect(6, -6, 13, -1, V(10.5, -3.5), West, new HomeCirclerController(V(10.5, -3.5)));
            sb.AddIdle(IdleCorners[1]);
            sb.AddIdle(IdleCorners[3]);
            Simulation sim = sb.Build();
            sim.DebugSetCharged(0, true);
            KillTestKit.ForceKillAt(sim, killAt, 1, 0, V(-20 + H, 20 + H));
            return sim;
        }

        [TestCase(5.0)]
        [TestCase(4.5)]
        public void KillAudit_4_APendingPocketOverInheritedLandCapturesOnlyWhatWasNotOwned(double killAt)
        {
            // 5.0: A is off B's land, it inherits and returns later at x = 0 with its pocket. 4.5: A's head is inside B's
            // land, so the inheritance returns it at that instant (7.2) with its trail and its pocket. Either way the
            // Return never lists a cell A already owned, and the whole pocket square ends up A's. With the pre-v1.6 island
            // behaviour (InheritanceBridge = Off): B's land does not touch A's and the forced kill makes no bridge, so under
            // rule v1.6 it would be severed at the kill (InheritanceBridgeTests covers the bridge and the severance).
            CrossRateAudit("pocket kill at " + killAt, rate => PocketKill(rate, TraitTestKit.One(TraitId.KillInheritance), killAt, InheritanceBridgeRule.Off), 5.9, run =>
            {
                string at = At(run);
                Simulation sim = run.Sim;
                Assert.AreEqual(1, run.Log.Count(SimEventType.LassoPocket, 0), at + "the pocket was made");
                SimEvent inherited = run.Log.Single(SimEventType.TerritoryInherited, 0);
                // At 4.5 the scripted path goes on after the same-instant return: it exits at x = 4 and comes back at x = 0
                // between two own regions (nothing enclosed, 0 cells). The first Return is the one with the pocket.
                SimEvent ret = run.Log.First(SimEventType.Return, 0);
                Assert.That(inherited.Time, Is.EqualTo(killAt).Within(1e-6));
                int[] pocketCells = run.Log.Single(SimEventType.LassoPocket, 0).Cells;
                Assert.AreEqual(pocketCells.Length - TraitTestKit.CountIn(inherited.Cells, pocketCells), TraitTestKit.CountIn(ret.Cells, pocketCells),
                                at + "every pocket cell that was not inherited is captured, no inherited one is listed");
                if (killAt < 4.677) Assert.AreEqual(inherited.Time, ret.Time, at + "returns at the inheritance instant");
                else Assert.That(ret.Time, Is.EqualTo(PocketReturnTime).Within(1e-6), at + "returns at x = 0");
                Assert.IsFalse(ret.Chased);
                Assert.That(ret.Cells.Length, Is.GreaterThan(0));
                int[] ownLand = TraitTestKit.RectCells(sim.Grid, -12, -4, 0, 4);
                foreach (int c in ret.Cells)
                {
                    Assert.IsFalse(TraitTestKit.Contains(inherited.Cells, c), at + "the Return lists an inherited (already owned) cell");
                    Assert.IsFalse(TraitTestKit.Contains(ownLand, c), at + "the Return lists a cell of A's land");
                }
                int[] square = TraitTestKit.RectCells(sim.Grid, 4.0625, -3.9375, 8.0625, 0.0625);
                Assert.AreEqual(square.Length, TraitTestKit.CountOwned(sim.Grid, square, sim.Players[0].Id), at + "the pocket square is A's");
                Assert.IsTrue(sim.Players[0].Home);
                Assert.AreEqual(0, sim.Players[0].Pocket.Count);
            });
        }

        [Test]
        public void KillAudit_4_AKillInTheTimeUpGroupStillReturnsTheTrailingKillerBeforeTheRoundEnds()
        {
            // RoundDuration 2.0, the impact at 2.0 - 0.5 eps fires at the final instant (R13 + R19 rule) in the TimeUp group,
            // with two idle survivors: the round ends by TimeUp, not LastSurvivor. The trailing killer is over the victim's
            // land then: its same-instant return must still be applied before RoundEnded.
            CrossRateAudit("TimeUp group", rate =>
            {
                var sb = new SimBuilder(rate);
                sb.Config.Traits = TraitTestKit.One(TraitId.KillInheritance);
                sb.Config.RoundDuration = 2.0;
                sb.AddRect(0, -4, 8, 4, V(4 + H, H), East, new ConstantHeadingController(East));
                sb.AddRect(-10, -4, 0, 4, V(-1 + H, 3 + H), North, Legs((North, 2), (East, 6), (South, 10)));
                sb.AddIdle(IdleCorners[2]);
                sb.AddIdle(IdleCorners[1]);
                Simulation sim = sb.Build();
                KillTestKit.ForceChase(sim, 0, 1, V(-15 + H, -15 + H), 10.0, 2.0 - 0.5 * Eps);
                return sim;
            }, 3.0, run =>
            {
                string at = At(run);
                Simulation sim = run.Sim;
                Assert.IsTrue(sim.Ended, at);
                Assert.AreEqual(RoundEndReason.TimeUp, sim.Result.Reason, at);
                SimEvent caught = run.Log.Single(SimEventType.SparkCaught, 0);
                SimEvent ret = run.Log.Single(SimEventType.Return, 1);
                SimEvent ended = run.Log.Single(SimEventType.RoundEnded);
                Assert.AreEqual(2.0, caught.Time, 1e-12, at + "the kill at the final instant");
                Assert.AreEqual(2.0, ret.Time, 1e-12, at + "the return at the final instant");
                Assert.That(run.Log.IndexOf(run.Log.Single(SimEventType.TerritoryInherited, 1)), Is.LessThan(run.Log.IndexOf(ret)));
                Assert.That(run.Log.IndexOf(ret), Is.LessThan(run.Log.IndexOf(ended)), at + "before the round end");
                Assert.IsFalse(ret.Chased);
                Assert.That(ret.Cells.Length, Is.GreaterThan(300), at + "the strip is captured");
                Assert.IsTrue(sim.Players[1].Home, at + "Home == (owner(Cell) == Id) at the end");
                Assert.AreEqual(sim.Grid.CountOf(sim.Players[1].Id), sim.Result.FinalCells[1]);
                Assert.AreEqual(1, sim.Result.Ranks[1]);
            });
        }

        // ============================================================================================================
        // 5. KillSpeedBoost
        // ============================================================================================================

        private static Simulation Idle30(RuleTraits traits, double headGrace)
        {
            var sb = new SimBuilder(30);
            sb.Config.HeadGrace = headGrace;
            sb.Config.Traits = traits;
            sb.AddIdle(IdleCorners[0]);
            sb.AddIdle(IdleCorners[2]);
            return sb.Build();
        }

        [Test]
        public void KillAudit_5_AtThirtyHertzTheHeadGraceCheckUsesTheProductOfTheMaxima()
        {
            double maxStep = 6.0 * 1.3 * 1.3 / 30.0;   // 0.338: the largest reachable step of Electricite v1.1 at 30 Hz
            Assert.IsNotNull(Idle30(TraitTestKit.ElectricV11, Tuning.HeadGrace), "default HeadGrace at 30 Hz");
            Assert.IsNotNull(Idle30(TraitTestKit.ElectricV11, maxStep + 1e-9), "just above the reachable step");
            Assert.Throws<ArgumentException>(() => Idle30(TraitTestKit.ElectricV11, maxStep - 1e-9), "just below the reachable step");
            Assert.IsNotNull(Idle30(TraitTestKit.Electric, 0.30), "Conduction alone: 0.26");
            Assert.IsNotNull(Idle30(TraitTestKit.One(TraitId.KillSpeedBoost), 0.30), "KillSpeedBoost alone: 0.26");
            Assert.Throws<ArgumentException>(() => Idle30(TraitTestKit.ElectricV11, 0.30), "both: 0.338, the factors multiply");
            Assert.IsNotNull(Idle30(TraitTestKit.Fire.With(new TraitSpec(TraitId.KillSpeedBoost)), 0.30), "moved to Feu: no Conduction");

            // The reachable step itself: four kills (the fourth at the cap), then a whole tick at home with Conduction.
            var sb = new SimBuilder(30);
            sb.Config.Traits = TraitTestKit.ElectricV11;
            sb.AddRect(-20, -3, 0, 3, V(-19 + H, H), East, new ConstantHeadingController(East));
            for (int k = 0; k < 4; k++)
                sb.AddRect(-20 + 6 * k, 10, -17 + 6 * k, 13, V(-18.5 + 6 * k, 11.5), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[2]);
            Simulation sim = sb.Build();
            for (int k = 0; k < 4; k++) KillTestKit.ForceKillAt(sim, 0.1 + 0.2 * k, 1 + k, 0, V(-20 + H + 6 * k, -12 + H));
            var oracle = new KillOracle(sim);
            while (sim.Time < 1.0 - 1e-9)
            {
                sim.Step();
                TraitTestKit.AssertTraitInvariants(sim);
                oracle.Check();
            }
            PlayerState killer = sim.Players[0];
            Assert.AreEqual(1.3, killer.SpeedMultiplier, 1e-12, "capped");
            Assert.AreEqual(3, oracle.Boosts, "three boosts, the fourth kill finds the cap");
            Assert.IsTrue(killer.Home);
            sim.Step();
            Assert.That(Vec2d.Distance(killer.PrevPos, killer.Pos), Is.EqualTo(maxStep).Within(1e-12), "PawnSpeed x 1.3 x 1.3 / 30");
            Assert.That(maxStep, Is.LessThan(sim.Config.HeadGrace));
        }

        /// <summary>
        /// Victim (player 0) is caught at KillTime by the killer (player 1), which trails East on y = H from x = -2 (exit at
        /// t = 0.15625); the enemy (player 2) heads North on x = 1 + H and touches the killer's trail at contactTime.
        /// Player 3 idles.
        /// </summary>
        private static Simulation KillerCrossed(int rate, RuleTraits traits, double catchIn, double contactTime, double enemyX)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-28, 20, -24, 24, V(-26 + H, 22 + H), East, new ConstantHeadingController(East));
            sb.AddRect(-10, -4, -2, 4, V(-3 + H, H), East, new ConstantHeadingController(East));
            double y0 = H - 0.63 - 6.0 * contactTime;
            sb.AddRect(enemyX - 2.0625, y0 - 2.0, enemyX + 1.9375, y0 + 0.75, V(enemyX, y0), North, new ConstantHeadingController(North));
            sb.AddIdle(IdleCorners[1]);
            Simulation sim = sb.Build();
            KillTestKit.ForceChase(sim, 0, 1, V(-15 + H, -15 + H), 10.0, catchIn);
            return sim;
        }

        [Test]
        public void KillAudit_5_ACutInTheSameGroupAsTheVictimsOwnKillUsesTheBoostedMultiplier()
        {
            // The killer kills at KillTime + eps and is touched 0.5 eps earlier: one group. Step b boosts it to 1.1, step c
            // spawns the spark: 7.1 fixes Spark.Speed at spawn from the multiplier at spawn, so 10.8 x 1.1.
            double contact = KillTime + 0.5 * Eps;
            CrossRateAudit("boost and cut in one group", rate => KillerCrossed(rate, TraitTestKit.One(TraitId.KillSpeedBoost), KillTime, contact, 1 + H), 1.2, run =>
            {
                string at = At(run);
                SimEvent boost = run.Log.Single(SimEventType.SpeedBoosted, 1);
                SimEvent cut = run.Log.Single(SimEventType.Cut, 1);
                Assert.AreEqual(boost.Time, cut.Time, at + "one group");
                Assert.That(run.Log.IndexOf(boost), Is.LessThan(run.Log.IndexOf(cut)), at + "step b before step c");
                Assert.That(cut.S, Is.EqualTo(3 + H).Within(1e-9));
                Assert.IsNotNull(run.Sim.Players[1].Spark);
                Assert.AreEqual(10.8 * 1.1, run.Sim.Players[1].Spark.Speed, 1e-12, at + "the spark follows the multiplier at spawn");
            });
            Simulation classic = KillerCrossed(60, RuleTraits.Classic, KillTime, contact, 1 + H);
            RunUntilTime(classic, 1.2);
            Assert.AreEqual(10.8, classic.Players[1].Spark.Speed, 1e-12, "classic: SparkSpeed");
        }

        // ============================================================================================================
        // 6. KillShield
        // ============================================================================================================

        [Test]
        public void KillAudit_6_AShieldEndingOnATickBoundaryCutsAtThatInstantAtEveryRate()
        {
            // Impact at 1.0 - eps: the kill is at 1.0 and the shield ends at 4.0, a tick boundary at 30, 60 and 144 Hz,
            // inside the enemy's contact with the killer's trail (3.95 to 4.16).
            CrossRateAudit("shield end on a tick boundary", rate => KillerCrossed(rate, TraitTestKit.One(TraitId.KillShield), 1.0 - Eps, 3.95, 5 + H), 4.3, run =>
            {
                string at = At(run);
                SimEvent started = run.Log.Single(SimEventType.ShieldStarted, 1);
                SimEvent ended = run.Log.Single(SimEventType.ShieldEnded, 1);
                SimEvent cut = run.Log.Single(SimEventType.Cut, 1);
                Assert.That(started.Time, Is.EqualTo(1.0).Within(1e-9), at + "kill on a tick boundary");
                Assert.That(ended.Time, Is.EqualTo(4.0).Within(1e-9), at + "end on a tick boundary");
                Assert.That(cut.Time, Is.EqualTo(ended.Time).Within(1e-9), at + "the head over the trail cuts at the end");
                Assert.That(run.Log.IndexOf(cut), Is.GreaterThan(run.Log.IndexOf(ended)));
                Assert.That(cut.S, Is.EqualTo(7 + H).Within(1e-9), at + "closest exposed point");
            });
        }

        /// <summary>
        /// K (player 0, land far NW) trails East on y = H from x = -20 (L = 10 at t = 0, head at x = -10 + 6 t). It kills
        /// player 1 at t = 0 (forced catch at the first tick start), so it is shielded until 3.0. At t = 1.0 the enemy E
        /// (player 2) is placed on K's trail line 'gap' behind K's head and runs East at the same speed: its head stays
        /// gap behind K's head on K's trail, at 1.0 - gap from the exposed part (HeadGrace 1.0). Player 3 idles.
        /// </summary>
        private static Simulation Follower(int rate, RuleTraits traits, double gap)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-28, 20, -24, 24, V(-26 + H, 22 + H), East, new ConstantHeadingController(East));
            sb.AddRect(10, 10, 14, 14, V(12 + H, 12 + H), East, new ConstantHeadingController(East));
            sb.AddRect(20, -24, 24, -20, V(22 + H, -22 + H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[3]);
            Simulation sim = sb.Build();
            sim.DebugSetTrail(0, new[] { V(-20, H), V(-10, H) });
            KillTestKit.ForceKillAt(sim, 0.0, 1, 0, V(-20 + H, -12 + H));
            bool placed = false;
            sim.BeforeTick += s =>
            {
                if (placed || s.Time < 1.0 - 1e-9) return;
                placed = true;
                double x = s.Players[0].Pos.X - gap;
                s.DebugSetTrail(2, new[] { V(x, H - 3.0), V(x, H) });
            };
            return sim;
        }

        [Test]
        public void KillAudit_6_AtTheShieldEndAHeadOverTheTrailCutsOnlyOutsideHeadGrace()
        {
            // gap 0.4: 0.6 from the exposed part, within ContactRadius 0.63: classic cuts at the placement (t = 1.0, s = L - 1);
            // shielded, the cut waits for the exact end (t = 3.0, s = L(3) - HeadGrace = 27).
            CrossRateAudit("follower 0.4", rate => Follower(rate, TraitTestKit.One(TraitId.KillShield), 0.4), 3.5, run =>
            {
                string at = At(run);
                SimEvent ended = run.Log.Single(SimEventType.ShieldEnded, 0);
                SimEvent cut = run.Log.Single(SimEventType.Cut, 0);
                Assert.That(ended.Time, Is.EqualTo(3.0).Within(1e-9), at + "kill at t = 0, Duration 3");
                Assert.AreEqual(2, cut.Other);
                Assert.That(cut.Time, Is.EqualTo(3.0).Within(1e-9), at + "the cut waits for the exact end");
                Assert.That(cut.S, Is.EqualTo(27.0).Within(1e-9), at + "s_cut = L - HeadGrace (the exposure end)");
            });
            Simulation classic = Follower(60, RuleTraits.Classic, 0.4);
            var log = new EventLog(classic);
            RunUntilTime(classic, 1.1);
            SimEvent classicCut = log.Single(SimEventType.Cut, 0);
            Assert.That(classicCut.Time, Is.EqualTo(1.0).Within(1e-9), "classic: the cut at the placement");
            Assert.That(classicCut.S, Is.EqualTo(15.0).Within(1e-9), "classic: s_cut = L(1) - HeadGrace");

            // gap 0.3: 0.7 from the exposed part: never a cut, shielded or not, before or after the end.
            foreach (RuleTraits traits in new[] { TraitTestKit.One(TraitId.KillShield), RuleTraits.Classic })
            {
                CrossRateAudit("follower 0.3 " + traits, rate => Follower(rate, traits, 0.3), 4.0, run =>
                {
                    Assert.AreEqual(0, run.Log.Count(SimEventType.Cut), At(run) + traits + ": a head inside HeadGrace never cuts\n" + run.Log.Dump());
                });
            }
        }

        /// <summary>
        /// V is caught by K's spark at KillTime; K trails and is chased by X (player 2, idle at home) with an impact at
        /// KillTime + delta. killerFirst: K is player 0 and V player 1 (else the reverse), so step b of a shared group
        /// eliminates K before or after V. Player 3 idles.
        /// </summary>
        private static Simulation KillerCaughtNearItsKill(int rate, RuleTraits traits, double delta, bool killerFirst)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-28, 20, -24, 24, V(-26 + H, 22 + H), East, new ConstantHeadingController(East));
            sb.AddRect(10, 10, 14, 14, V(12 + H, 12 + H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[2]);
            sb.AddIdle(IdleCorners[1]);
            Simulation sim = sb.Build();
            int k = killerFirst ? 0 : 1, v = 1 - k;
            KillTestKit.ForceChase(sim, v, k, V(-15 + H, -15 + H), 10.0, KillTime);
            KillTestKit.ForceChase(sim, k, 2, V(-15 + H, -20 + H), 10.0, KillTime + delta);
            return sim;
        }

        [TestCase(false)]
        [TestCase(true)]
        public void KillAudit_6_TheShieldStartsAtTheKillGroupAndASimultaneousCatchOfTheKillerWins(bool killerFirst)
        {
            // delta 0.5 eps: the killer's own catch is simultaneous with its kill (one group): it dies in step b, before or
            // after its victim depending on the indices, nothing is paid to it, and its killer X is paid. delta 3 eps: two
            // groups; the kill comes first, the shield extinguishes the spark about to catch the killer, which survives.
            int k = killerFirst ? 0 : 1, v = 1 - k;
            string order = killerFirst ? "killer first" : "victim first";
            CrossRateAudit("simultaneous catch, " + order, rate => KillerCaughtNearItsKill(rate, TraitTestKit.One(TraitId.KillShield), 0.5 * Eps, killerFirst), 1.2, run =>
            {
                string at = At(run) + order + ": ";
                SimEvent dv = run.Log.Single(SimEventType.Eliminated, v), dk = run.Log.Single(SimEventType.Eliminated, k);
                Assert.AreEqual(dv.Time, dk.Time, at + "one group");
                Assert.AreEqual(k, dv.Other, at + "V's killer is K");
                Assert.AreEqual(killerFirst, run.Log.IndexOf(dk) < run.Log.IndexOf(dv), at + "step b order follows the indices");
                AssertNoReward(run.Log, k, at + "the killer died in the group of its kill");
                Assert.AreEqual(1, run.Log.Count(SimEventType.ShieldStarted, 2), at + "X killed K and is shielded");
                Assert.IsFalse(run.Sim.Players[k].Alive);
                Assert.AreEqual(1, run.Sim.Players[k].Kills, at + "credited anyway (R12)");
            });
            CrossRateAudit("catch 3 eps later, " + order, rate => KillerCaughtNearItsKill(rate, TraitTestKit.One(TraitId.KillShield), 3.0 * Eps, killerFirst), 1.2, run =>
            {
                string at = At(run) + order + ": ";
                SimEvent shield = run.Log.Single(SimEventType.ShieldStarted, k);
                Assert.IsTrue(shield.Chased, at + "the spark 3 eps from the head was extinguished at the kill");
                Assert.AreEqual(0, run.Log.Count(SimEventType.SparkCaught, k), at + "the killer survives");
                Assert.IsTrue(run.Sim.Players[k].Alive);
                Assert.IsTrue(run.Sim.Players[k].ExitWasCut, at + "its loop stays lost");
                Assert.IsNull(run.Sim.Players[k].Spark);
            });
        }

        /// <summary>
        /// The pocket scenario with the S6 cutter (player 2 touches the loop's bottom leg at t = 4.0: A's spark would catch
        /// A at about 5.667 s, just before its return at PocketReturnTime). A kills B at t = 5.0 (B teleported far away and
        /// caught at that tick start). Player 3 idles.
        /// </summary>
        private static Simulation PocketCutKill(int rate, RuleTraits traits)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-12, -4, 0, 4, V(-1 + H, H), East,
                       Legs((East, 9), (South, 4), (West, 4), (North, 5), (East, 2), (South, 4), (West, 7)));
            sb.AddRect(6, -6, 13, -1, V(10.5, -3.5), West, new HomeCirclerController(V(10.5, -3.5)));
            sb.AddRect(3, -30, 7, -27, V(5 + H, -3.9375 - 0.63 - 24.0), North,
                       new HeadingScheduleController((0.0, North), (4.0 + 1.0 / 12.0, South)));
            sb.AddIdle(IdleCorners[1]);
            Simulation sim = sb.Build();
            sim.DebugSetCharged(0, true);
            KillTestKit.ForceKillAt(sim, 5.0, 1, 0, V(-20 + H, 20 + H));
            return sim;
        }

        [Test]
        public void KillAudit_6_AShieldSavesACutKillerButItsPendingPocketIsStillErased()
        {
            // 7.2 (Liquide): the chased killer loses its spark and survives, its loop stays lost (ExitWasCut) and the pending
            // lasso pocket of the cut exit is erased at the return. With KillInheritance too: rule v1.6 (contract 30), B's
            // land does not touch A's and a cut exit can never become a bridge, so the inherited land is severed at the
            // kill and no pocket cell ends up A's.
            CrossRateAudit("pocket of a cut exit", rate => PocketCutKill(rate, RuleTraits.Parse("KillInheritance;KillShield")), 5.9, run =>
            {
                string at = At(run);
                Simulation sim = run.Sim;
                Assert.AreEqual(2, run.Log.Single(SimEventType.Cut, 0).Other, at + "cut by the S6 cutter");
                SimEvent shield = run.Log.Single(SimEventType.ShieldStarted, 0);
                Assert.IsTrue(shield.Chased, at + "the spark was extinguished");
                Assert.AreEqual(0, run.Log.Count(SimEventType.SparkCaught, 0), at + "A survives");
                SimEvent ret = run.Log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(PocketReturnTime).Within(1e-6));
                Assert.IsTrue(ret.Chased, at + "a cut exit never captures");
                Assert.AreEqual(0, ret.Cells.Length);
                Assert.AreEqual(0.0, ret.Margin);
                Assert.AreEqual(0, sim.Players[0].Pocket.Count, at + "the pocket is erased");
                Assert.AreEqual(0, sim.Players[0].Captures);
                int[] pocket = run.Log.Single(SimEventType.LassoPocket, 0).Cells;
                int[] inherited = run.Log.Single(SimEventType.TerritoryInherited, 0).Cells;
                int inheritedInPocket = TraitTestKit.CountIn(inherited, pocket);
                Assert.That(inheritedInPocket, Is.GreaterThan(0));
                Assert.AreEqual(0, run.Log.Count(SimEventType.InheritanceBridged), at + "a cut exit makes no bridge");
                SimEvent severed = run.Log.Single(SimEventType.TerritorySevered, 0);
                Assert.IsTrue(SameCells(inherited, severed.Cells), at + "the inherited land is severed at the kill");
                Assert.AreEqual(0, TraitTestKit.CountOwned(sim.Grid, pocket, sim.Players[0].Id), at + "no pocket cell is A's");
            });
            Simulation classic = PocketCutKill(60, RuleTraits.Classic);
            var log = new EventLog(classic);
            RunUntilTime(classic, 5.9);
            Assert.AreEqual(1, log.Count(SimEventType.SparkCaught, 0), "classic: A is caught before its return");
        }
        /// <summary>
        /// K (player 0, land [-10, 0] x [-4, 4]) trails a U from its land edge: (0, 3 + H) East to x = 6 + 3e-7, South to
        /// y = H, then West home: it crosses x = 0 at t = 1 + 5e-8, 0.5 eps after the tick boundary t = 1. X (player 2)
        /// cut it at t = 0 (its spark would catch it at 0.8 s); K kills V (player 1) at t = 1/6, so KillShield(0.3)
        /// extinguishes that spark and the shield ends at 1/6 + 0.3. With reCut, Y (player 3) cuts K again at the start of
        /// the tick t = 1 (a spark 0.5 eps before the return: R14 cancels it as a cut at closure).
        /// </summary>
        private static Simulation ReCutAtClosure(int rate, bool reCut)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = TraitTestKit.One(TraitId.KillShield, 0.3);
            sb.AddRect(-10, -4, 0, 4, V(-5 + H, H), West, new ConstantHeadingController(West));
            sb.AddRect(10, 10, 14, 14, V(12 + H, 12 + H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[2]);
            sb.AddIdle(IdleCorners[1]);
            Simulation sim = sb.Build();
            double x0 = 6.0 + 6.0 * 0.5 * Eps;
            sim.DebugSetTrail(0, new[] { V(0, 3 + H), V(x0, 3 + H), V(x0, H) });
            sim.DebugForceCut(0, sim.Players[0].Trail.Length - 0.8 * 4.8, 2);
            KillTestKit.ForceKillAt(sim, 1.0 / 6.0, 1, 0, V(-20 + H, -12 + H));
            bool done = !reCut;
            sim.BeforeTick += s =>
            {
                if (done || s.Time < 1.0 - 1e-9) return;
                done = true;
                s.DebugForceCut(0, 2.0, 3);
            };
            return sim;
        }

        [TestCase(false)]
        [TestCase(true)]
        public void KillAudit_6_ACancelledReCutAtClosureDoesNotUncutAnExitThatWasCut(bool reCut)
        {
            // 7.1: a return with ExitWasCut captures nothing even if the spark was removed (KillShield). After the shield,
            // the exit can be cut again (kill-core reading); R14 then cancels that re-cut as a cut at closure. Cancelling a
            // cut must undo THAT cut only: the exit was already cut by X, so the return stays chased and captures nothing,
            // exactly as without the re-cut.
            CrossRateAudit("re-cut at closure " + reCut, rate => ReCutAtClosure(rate, reCut), 1.1, run =>
            {
                string at = At(run) + (reCut ? "re-cut: " : "no re-cut: ");
                Simulation sim = run.Sim;
                Assert.IsTrue(run.Log.Single(SimEventType.ShieldStarted, 0).Chased, at + "X's spark was extinguished");
                Assert.AreEqual(1, run.Log.Count(SimEventType.ShieldEnded, 0));
                SimEvent ret = run.Log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(1.0 + 0.5 * Eps).Within(1e-9), at + "return 0.5 eps after the tick boundary");
                Assert.IsTrue(ret.Chased, at + "the exit was cut by X: it must stay chased");
                Assert.AreEqual(0, ret.Cells.Length, at + "a cut exit never captures, whatever happened to a later cut");
                Assert.AreEqual(0.0, ret.Margin);
                Assert.IsTrue(sim.Players[0].Home);
                Assert.IsNull(sim.Players[0].Spark);
                Assert.IsFalse(sim.Players[0].ExitWasCut, at + "cleared at the return");
                Assert.AreEqual(0, sim.Players[3].CutsMade, at + "the cancelled re-cut is not credited");
                Assert.AreEqual(1, sim.Players[2].CutsMade, at + "X keeps its cut");
            });
        }

        // ============================================================================================================
        // 7. Determinism and invariants in bot rounds
        // ============================================================================================================

        private static IEnumerable<object[]> BotCases()
        {
            foreach (int rate in BotRates) yield return new object[] { rate };
        }

        /// <summary>Random valid kill parameters on top of a random biome set (seeded).</summary>
        private static RuleTraits RandomKillSet(ulong seed)
        {
            var rng = new Rng(seed * 2654435761UL + 99UL);
            string[] biomes = { "Liquide", "Feu", "Electricite" };
            RuleTraits set = BiomeSet(biomes[rng.NextInt(3)]);
            double[] shares = { 0.0, 0.37, 0.5, 1.0 };
            set = set.With(new TraitSpec(TraitId.KillInheritance, shares[rng.NextInt(shares.Length)]));
            set = set.With(new TraitSpec(TraitId.KillSpeedBoost, rng.Range(0.0, 0.3), rng.Range(0.0, 0.6)));
            set = set.With(new TraitSpec(TraitId.KillShield, rng.Range(0.0, 6.0)));
            return set;
        }

        /// <summary>
        /// A kill-rich bot round: four Aggressive bots (the balanced lineup of the balance report kills about once a
        /// round), lasso on, full round.
        /// </summary>
        private static Simulation AggressiveRound(ulong seed, RuleTraits traits, int rate)
        {
            var controllers = new IController[4];
            for (int i = 0; i < 4; i++) controllers[i] = new BotController(BotPersonality.Preset(BotStyle.Aggressive), BotTests.BotSeed(seed, i));
            var config = new SimConfig { Seed = seed, TickRate = rate, LassoEnabled = true, Traits = traits, RoundDuration = BotRoundSeconds };
            return new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
        }

#if UNITY_5_3_OR_NEWER
        private const double BotRoundSeconds = 20.0;
        private static readonly ulong[] OracleSeeds = { 3UL };
#else
        private const double BotRoundSeconds = 90.0;
        private static readonly ulong[] OracleSeeds = { 1UL, 2UL, 3UL, 4UL, 5UL, 6UL };
#endif

        /// <summary>
        /// All eleven traits together, the three v1.1 biome sets and a random kill parameter set, in full bot rounds (both
        /// the balanced lineup and four Aggressive bots, several seeds) with the lasso on: the trait invariants and the kill
        /// oracle on every tick (at 30 Hz with Electricite v1.1 and all eleven this includes s_cut &lt;= L - HeadGrace at the
        /// largest reachable speed), and a twin round with the same seed gives the same StateHash every 30 ticks (all
        /// eleven and the random set). In the dotnet loop every reward type must have fired and been checked.
        /// </summary>
        [TestCaseSource(nameof(BotCases))]
        public void KillAudit_7_EveryKillSetKeepsTheOracleAndIsDeterministicInBotRounds(int rate)
        {
            int kills = 0, inherited = 0, boosts = 0, shields = 0, ended = 0, extinguished = 0, cuts = 0;
            var report = new List<string>();
            foreach (ulong seed in OracleSeeds)
            {
                var sets = new List<KeyValuePair<string, RuleTraits>>
                {
                    new KeyValuePair<string, RuleTraits>("all eleven", AllEleven),
                    new KeyValuePair<string, RuleTraits>("Liquide v1.1", TraitTestKit.LiquidV11),
                    new KeyValuePair<string, RuleTraits>("Feu v1.1", TraitTestKit.FireV11),
                    new KeyValuePair<string, RuleTraits>("Electricite v1.1", TraitTestKit.ElectricV11),
                    new KeyValuePair<string, RuleTraits>("random kill parameters", RandomKillSet(seed)),
                };
                foreach (KeyValuePair<string, RuleTraits> s in sets)
                {
                    for (int lineup = 0; lineup < 2; lineup++)
                    {
                        string label = s.Key + " (" + s.Value.ToKey() + ") " + rate + " Hz seed " + seed + (lineup == 0 ? " balanced" : " aggressive");
                        bool twinCheck = s.Key == "all eleven" || s.Key == "random kill parameters";
                        Func<Simulation> make = () => lineup == 0
                            ? TraitTestKit.BotRound(seed, s.Value, true, rate, -1, BotRoundSeconds)
                            : AggressiveRound(seed, s.Value, rate);
                        Simulation a = make();
                        Simulation b = twinCheck ? make() : null;
                        var oracle = new KillOracle(a);
                        while (!a.Ended)
                        {
                            a.Step();
                            TraitTestKit.AssertTraitInvariants(a);
                            oracle.Check();
                            if (b != null)
                            {
                                b.Step();
                                if ((a.Tick % 30 == 0 || a.Ended) && a.StateHash() != b.StateHash()) Assert.Fail(label + ": twin StateHash differs at tick " + a.Tick);
                            }
                        }
                        if (b != null) Assert.IsTrue(b.Ended, label + ": the twin ended too");
                        kills += oracle.Kills;
                        inherited += oracle.Inherited;
                        boosts += oracle.Boosts;
                        shields += oracle.ShieldsStarted;
                        ended += oracle.ShieldsEnded;
                        extinguished += oracle.Extinguished;
                        cuts += oracle.CutsChecked;
                        if (oracle.Kills > 0) report.Add(label + ": " + oracle.Summary);
                    }
                }
            }
            string summary = rate + " Hz: kills " + kills + ", inherited " + inherited + ", boosts " + boosts + ", shields " + shields
                             + " (ended " + ended + ", extinguished " + extinguished + "), cuts checked " + cuts + "\n" + string.Join("\n", report);
#if !UNITY_5_3_OR_NEWER
            Assert.That(inherited, Is.GreaterThan(0), "no inheritance was checked: " + summary);
            Assert.That(boosts, Is.GreaterThan(0), "no boost was checked: " + summary);
            Assert.That(shields, Is.GreaterThan(0), "no shield was checked: " + summary);
            Assert.That(ended, Is.GreaterThan(0), "no shield end was checked: " + summary);
            Assert.That(cuts, Is.GreaterThan(20), "too few cuts checked: " + summary);
#endif
            Console.WriteLine(summary);
        }
    }
    /// <summary>Test-side helpers over the Simulation's internal kill plumbing, read through reflection (no InternalsVisibleTo).</summary>
    internal static class KillAuditSimExtensions
    {
        public static int KillTraitCount(this Simulation sim)
        {
            PropertyInfo p = typeof(Simulation).GetProperty("KillTraits", BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(p, "Simulation.KillTraits");
            return ((Array)p.GetValue(sim)).Length;
        }
    }
}
