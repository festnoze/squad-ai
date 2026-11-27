// Owned by traits-core (wave D-1), extended by kill-core (wave D-2: v1.1 default sets, kill invariants). Shared helpers of
// the biome trait tests (docs/BIOME_TRAITS.md sections 6 and 7). Pure NUnit + PainterIO.Core (no UnityEngine), NUnit 3.5
// features only.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    public static class TraitTestKit
    {
        // ------------------------------------------------------------------------------------------------------------
        // The default biome sets of docs/BIOME_TRAITS.md section 3. The one editable table lives in the Runtime
        // (BiomeTraitTable); Core knows no biome, so the tests carry this copy of the section 3 values.

        public const string LiquidKey = "Inertia(420,0);Coalescence(2,0)";
        public const string FireKey = "SparkSpeed(2.1,0);Propagation(4,1);ScorchedEarth(15,0)";
        public const string ElectricKey = "SparkSpeed(1.5,0);Conduction(1.3,0);ArcReach(1.4,0);RingInterval(10,0)";

        public static RuleTraits Liquid => new RuleTraits(new[]
        {
            new TraitSpec(TraitId.Inertia, 420), new TraitSpec(TraitId.Coalescence, 2.0),
        });

        public static RuleTraits Fire => new RuleTraits(new[]
        {
            new TraitSpec(TraitId.Propagation, 4.0, 1), new TraitSpec(TraitId.SparkSpeed, 2.1), new TraitSpec(TraitId.ScorchedEarth, 15),
        });

        public static RuleTraits Electric => new RuleTraits(new[]
        {
            new TraitSpec(TraitId.Conduction, 1.30), new TraitSpec(TraitId.ArcReach, 1.40), new TraitSpec(TraitId.SparkSpeed, 1.5),
            new TraitSpec(TraitId.RingInterval, 10),
        });

        // ------------------------------------------------------------------------------------------------------------
        // kill-core (wave D-2): the CURRENT default table, docs/BIOME_TRAITS.md v1.1 = section 3 + section 7 (Feu +
        // KillInheritance, Electricite + KillSpeedBoost, Liquide + KillShield). Liquid / Fire / Electric above stay the
        // section 3 sets (the D-1 audits reason on them). The Runtime BiomeTraitTable defaults must equal these keys.

        public const string LiquidV11Key = "Inertia(420,0);Coalescence(2,0);KillShield(3,0)";
        public const string FireV11Key = "SparkSpeed(2.1,0);Propagation(4,1);ScorchedEarth(15,0);KillInheritance(1,0)";
        public const string ElectricV11Key = "SparkSpeed(1.5,0);Conduction(1.3,0);ArcReach(1.4,0);RingInterval(10,0);KillSpeedBoost(0.1,0.3)";

        public static RuleTraits LiquidV11 => Liquid.With(new TraitSpec(TraitId.KillShield, 3.0));

        public static RuleTraits FireV11 => Fire.With(new TraitSpec(TraitId.KillInheritance, 1.0));

        public static RuleTraits ElectricV11 => Electric.With(new TraitSpec(TraitId.KillSpeedBoost, 0.10, 0.30));

        /// <summary>
        /// The D-1 balance proposals (docs/waveD/traits-core.json, not applied): Liquide Inertia 480, Feu SparkSpeed 2.3,
        /// on top of the v1.1 sets.
        /// </summary>
        public static RuleTraits LiquidV11Proposal => LiquidV11.With(new TraitSpec(TraitId.Inertia, 480.0));

        public static RuleTraits FireV11Proposal => FireV11.With(new TraitSpec(TraitId.SparkSpeed, 2.3));

        /// <summary>Named trait sets: classic, each trait alone (defaults), each biome default set (section 3, then v1.1).</summary>
        public static List<KeyValuePair<string, RuleTraits>> AllSets()
        {
            var sets = new List<KeyValuePair<string, RuleTraits>>
            {
                new KeyValuePair<string, RuleTraits>("Classic", RuleTraits.Classic),
            };
            foreach (TraitId id in TraitDefaults.All)
                sets.Add(new KeyValuePair<string, RuleTraits>(id + " alone", new RuleTraits(new[] { new TraitSpec(id) })));
            sets.Add(new KeyValuePair<string, RuleTraits>("Liquide", Liquid));
            sets.Add(new KeyValuePair<string, RuleTraits>("Feu", Fire));
            sets.Add(new KeyValuePair<string, RuleTraits>("Electricite", Electric));
            sets.Add(new KeyValuePair<string, RuleTraits>("Liquide v1.1", LiquidV11));
            sets.Add(new KeyValuePair<string, RuleTraits>("Feu v1.1", FireV11));
            sets.Add(new KeyValuePair<string, RuleTraits>("Electricite v1.1", ElectricV11));
            return sets;
        }

        public static RuleTraits One(TraitId id, double p1 = double.NaN, double p2 = double.NaN)
        {
            return new RuleTraits(new[] { new TraitSpec(id, p1, p2) });
        }

        // ------------------------------------------------------------------------------------------------------------
        // Bot rounds

        internal static readonly BotStyle[] Lineup = { BotStyle.Balanced, BotStyle.Balanced, BotStyle.Greedy, BotStyle.Aggressive };

        /// <summary>A bot-only round (or with HumanIndex 0 standing for a human slot) with the given traits.</summary>
        public static Simulation BotRound(ulong seed, RuleTraits traits, bool lasso, int tickRate = 60, int humanIndex = -1,
                                          double roundDuration = 90.0)
        {
            var controllers = new IController[Lineup.Length];
            for (int i = 0; i < Lineup.Length; i++)
                controllers[i] = new BotController(BotPersonality.Preset(Lineup[i]), BotTests.BotSeed(seed, i));
            var config = new SimConfig
            {
                Seed = seed, TickRate = tickRate, LassoEnabled = lasso, Traits = traits, RoundDuration = roundDuration,
            };
            return new Simulation(config, controllers, new SimSetup { HumanIndex = humanIndex });
        }

        /// <summary>FNV-style fold of StateHash every 'every' ticks and at the end of a full round.</summary>
        public static ulong RollingRoundHash(Simulation sim, int every, bool checkInvariants)
        {
            ulong h = 1469598103934665603UL;
            while (!sim.Ended)
            {
                sim.Step();
                if (checkInvariants) AssertTraitInvariants(sim);
                if (sim.Tick % every == 0 || sim.Ended)
                {
                    unchecked
                    {
                        h ^= sim.StateHash();
                        h *= 1099511628211UL;
                    }
                }
            }
            return h;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Invariants (contract 10.1 list + the trait additions), cheap enough for every tick of full rounds.

        /// <summary>
        /// BotTests.CheckInvariants (no NaN, cells sum, Home == owner(Cell) == Id, trail empty iff home, trail end == Pos,
        /// spark S &lt;= L + 1e-6, EventCapHits == 0) plus, for the events of the last Step: Cells ascending and distinct
        /// for Return / Eliminated / LassoPocket / TerritoryGrew, chased returns empty, TerritoryGrew cells owned by
        /// their player right after the tick and stamped with the tick end time, and scorched cells always neutral.
        /// Fails the test on the first violation.
        /// </summary>
        public static void AssertTraitInvariants(Simulation sim)
        {
            string broken = BotTests.CheckInvariants(sim);
            if (broken != null) Assert.Fail("tick " + sim.Tick + ": " + broken);
            AssertKillInvariants(sim);
            IReadOnlyList<SimEvent> events = sim.LastEvents;
            for (int k = 0; k < events.Count; k++)
            {
                SimEvent e = events[k];
                if (e.Type == SimEventType.Return || e.Type == SimEventType.Eliminated || e.Type == SimEventType.LassoPocket
                    || e.Type == SimEventType.TerritoryGrew || e.Type == SimEventType.TerritoryInherited)
                {
                    if (e.Cells == null) Assert.Fail("tick " + sim.Tick + ": null Cells in " + e);
                    for (int c = 1; c < e.Cells.Length; c++)
                    {
                        if (e.Cells[c] <= e.Cells[c - 1]) Assert.Fail("tick " + sim.Tick + ": Cells not ascending in " + e);
                    }
                }
                if (e.Type == SimEventType.Return && e.Chased && e.Cells.Length != 0)
                    Assert.Fail("tick " + sim.Tick + ": a chased return captured " + e.Cells.Length + " cells");
                if (e.Type == SimEventType.TerritoryGrew)
                {
                    if (e.Cells.Length == 0) Assert.Fail("tick " + sim.Tick + ": empty TerritoryGrew");
                    if (Math.Abs(e.Time - sim.Time) > 1e-12) Assert.Fail("tick " + sim.Tick + ": TerritoryGrew not at the tick end time: " + e);
                    byte id = sim.Players[e.Player].Id;
                    for (int c = 0; c < e.Cells.Length; c++)
                    {
                        if (sim.Grid.Cells[e.Cells[c]] != id) Assert.Fail("tick " + sim.Tick + ": grown cell not owned by its player: " + e);
                    }
                }
                if (e.Type == SimEventType.Eliminated && sim.View.Traits.Has(TraitId.ScorchedEarth))
                {
                    for (int c = 0; c < e.Cells.Length; c++)
                    {
                        int cell = e.Cells[c];
                        if (sim.Grid.Cells[cell] == OwnerGrid.Neutral && !sim.View.IsScorched(cell) && sim.Time < e.Time + sim.View.Traits.Get(TraitId.ScorchedEarth).P1 - 1e-9)
                            Assert.Fail("tick " + sim.Tick + ": a freed neutral cell is not scorched right after the elimination");
                    }
                }
            }
        }

        /// <summary>
        /// kill-core (docs/BIOME_TRAITS.md section 7): state invariants of the kill rewards, after every tick.
        /// - Spark implies ExitWasCut; ExitWasCut implies trailing; without KillShield, ExitWasCut == (Spark != null)
        ///   (the classic meaning); a shielded player has no spark; dead players carry no flag and no shield.
        /// - SpeedMultiplier is exactly 1 without KillSpeedBoost, else within [1, 1 + Cap]; every spark has Speed &gt; 0.
        /// - The kill events appear only with their trait: TerritoryInherited (KillInheritance, non-empty, killer alive),
        ///   SpeedBoosted (KillSpeedBoost, Value = the killer's multiplier), ShieldStarted / ShieldEnded (KillShield);
        ///   each kill event follows the victim's Eliminated event of the same instant.
        /// </summary>
        public static void AssertKillInvariants(Simulation sim)
        {
            RuleTraits traits = sim.View.Traits;
            bool boost = traits.Has(TraitId.KillSpeedBoost), shield = traits.Has(TraitId.KillShield);
            double cap = boost ? 1.0 + traits.Get(TraitId.KillSpeedBoost).P2 : 1.0;
            for (int i = 0; i < sim.Players.Count; i++)
            {
                PlayerState p = sim.Players[i];
                string who = "tick " + sim.Tick + " player " + i + ": ";
                if (p.Spark != null && !p.ExitWasCut) Assert.Fail(who + "a spark without ExitWasCut");
                if (p.ExitWasCut && p.Home) Assert.Fail(who + "ExitWasCut while home");
                if (!shield && p.ExitWasCut != (p.Spark != null)) Assert.Fail(who + "ExitWasCut != has a spark without KillShield");
                if (p.Shielded && p.Spark != null) Assert.Fail(who + "a shielded trail carries a spark");
                if (!p.Alive && (p.Shielded || p.ExitWasCut)) Assert.Fail(who + "a dead player keeps a shield or ExitWasCut");
                if (p.Shielded && !shield) Assert.Fail(who + "shielded without KillShield");
                if (!boost && p.SpeedMultiplier != 1.0) Assert.Fail(who + "SpeedMultiplier " + p.SpeedMultiplier + " without KillSpeedBoost");
                if (p.SpeedMultiplier < 1.0 || p.SpeedMultiplier > cap + 1e-12) Assert.Fail(who + "SpeedMultiplier " + p.SpeedMultiplier + " outside [1, " + cap + "]");
                if (p.Spark != null && !(p.Spark.Speed > 0.0)) Assert.Fail(who + "spark speed not set");
            }
            IReadOnlyList<SimEvent> events = sim.LastEvents;
            for (int k = 0; k < events.Count; k++)
            {
                SimEvent e = events[k];
                string at = "tick " + sim.Tick + ": " + e + ": ";
                switch (e.Type)
                {
                    case SimEventType.TerritoryInherited:
                        if (!traits.Has(TraitId.KillInheritance)) Assert.Fail(at + "without KillInheritance");
                        if (e.Cells == null || e.Cells.Length == 0) Assert.Fail(at + "empty inheritance");
                        break;
                    case SimEventType.SpeedBoosted:
                        if (!boost) Assert.Fail(at + "without KillSpeedBoost");
                        if (!(e.Value > 1.0) || e.Value > cap + 1e-12) Assert.Fail(at + "Value " + e.Value);
                        break;
                    case SimEventType.ShieldStarted:
                        if (!shield) Assert.Fail(at + "without KillShield");
                        if (!(e.Value > e.Time)) Assert.Fail(at + "the shield ends before it starts");
                        break;
                    case SimEventType.ShieldEnded:
                        if (!shield) Assert.Fail(at + "without KillShield");
                        if (Math.Abs(e.Value - e.Time) > 1e-9) Assert.Fail(at + "ShieldEnded not at its end time " + e.Value);
                        break;
                    default:
                        continue;
                }
                if (e.Type == SimEventType.ShieldEnded) continue;
                bool afterKill = false;
                for (int j = 0; j < k && !afterKill; j++)
                {
                    SimEvent d = events[j];
                    afterKill = d.Type == SimEventType.Eliminated && d.Player == e.Other && d.Cause == EliminationCause.Spark && d.Other == e.Player
                                && d.Time == e.Time;
                }
                if (!afterKill) Assert.Fail(at + "a kill reward without the victim's Spark elimination before it");
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Cross-rate protocol (contract 10.0 item 3) extended to TerritoryGrew cells.

        public sealed class Run
        {
            public int Rate;
            public Simulation Sim;
            public SimTestKit.EventLog Log;
        }

        /// <summary>
        /// Runs build(rate) at 30, 60 and 144 Hz until runUntil with the trait invariants every tick, calls check, and
        /// asserts identical outcomes: SimTestKit.AssertSameOutcome (events, times within 1e-6 s, Return / LassoPocket
        /// cells, ranks) plus identical Cells for TerritoryGrew, Eliminated and TerritoryInherited. Returns the three runs
        /// (30, 60, 144).
        /// </summary>
        public static List<Run> CrossRate(string label, Func<int, Simulation> build, double runUntil, Action<Run> check = null,
                                          Action<Simulation> beforeTick = null)
        {
            var runs = new List<Run>();
            foreach (int rate in SimTestKit.CrossRates)
            {
                Simulation sim = build(rate);
                if (beforeTick != null) sim.BeforeTick += beforeTick;
                var log = new SimTestKit.EventLog(sim);
                int guard = 0;
                while (!sim.Ended && sim.Time < runUntil - 1e-9)
                {
                    sim.Step();
                    AssertTraitInvariants(sim);
                    if (++guard > 1000000) Assert.Fail("run did not terminate");
                }
                var run = new Run { Rate = rate, Sim = sim, Log = log };
                check?.Invoke(run);
                runs.Add(run);
            }
            var reference = new SimTestKit.Outcome(runs[0].Rate, runs[0].Log, runs[0].Sim);
            for (int r = 1; r < runs.Count; r++)
            {
                var other = new SimTestKit.Outcome(runs[r].Rate, runs[r].Log, runs[r].Sim);
                SimTestKit.AssertSameOutcome(reference, other, label);
                for (int k = 0; k < reference.Events.Count; k++)
                {
                    SimEvent x = reference.Events[k], y = other.Events[k];
                    if (x.Type == SimEventType.TerritoryGrew || x.Type == SimEventType.Eliminated || x.Type == SimEventType.TerritoryInherited)
                    {
                        Assert.IsTrue(SimTestKit.SameCells(x.Cells, y.Cells), label + " (" + runs[0].Rate + " Hz vs " + runs[r].Rate
                                      + " Hz): Cells of event " + k + " " + x.Type + " differ (" + x.Cells.Length + " vs " + y.Cells.Length + ")");
                    }
                }
            }
            return runs;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Grid helpers

        /// <summary>Cell indices whose center lies in [x0, x1] x [y0, y1] (ascending).</summary>
        public static int[] RectCells(OwnerGrid g, double x0, double y0, double x1, double y1)
        {
            var list = new List<int>();
            for (int j = 0; j < g.Size; j++)
            {
                double y = g.CellCenter(0, j).Y;
                if (y < y0 || y > y1) continue;
                for (int i = 0; i < g.Size; i++)
                {
                    double x = g.CellCenter(i, 0).X;
                    if (x >= x0 && x <= x1 && g.Cells[g.Index(i, j)] != OwnerGrid.Void) list.Add(g.Index(i, j));
                }
            }
            return list.ToArray();
        }

        public static void SetCells(OwnerGrid g, int[] cells, byte owner)
        {
            for (int k = 0; k < cells.Length; k++) g.Set(cells[k], owner);
        }

        public static bool Contains(int[] sortedCells, int cell) => Array.BinarySearch(sortedCells, cell) >= 0;

        public static int CountIn(int[] sortedCells, int[] subset)
        {
            int n = 0;
            for (int k = 0; k < subset.Length; k++)
            {
                if (Contains(sortedCells, subset[k])) n++;
            }
            return n;
        }

        public static int CountOwned(OwnerGrid g, int[] cells, byte owner)
        {
            int n = 0;
            for (int k = 0; k < cells.Length; k++)
            {
                if (g.Cells[cells[k]] == owner) n++;
            }
            return n;
        }

        /// <summary>
        /// Independent oracle of one Propagation ring on a grid copy: neutral non-Void cells with exactly one distinct
        /// player owner (1..players) among their 4-neighbours, minus the excluded cells. Returns (cell, owner) sorted by
        /// cell.
        /// </summary>
        public static List<KeyValuePair<int, byte>> OracleRing(byte[] cells, int size, int players, Func<int, bool> excluded)
        {
            var result = new List<KeyValuePair<int, byte>>();
            for (int c = 0; c < cells.Length; c++)
            {
                if (cells[c] != OwnerGrid.Neutral || (excluded != null && excluded(c))) continue;
                int i = c % size, j = c / size;
                byte claim = 0;
                bool contested = false;
                int[] ns = { i + 1 < size ? c + 1 : -1, i > 0 ? c - 1 : -1, j + 1 < size ? c + size : -1, j > 0 ? c - size : -1 };
                foreach (int nIdx in ns)
                {
                    if (nIdx < 0) continue;
                    byte o = cells[nIdx];
                    if (o == OwnerGrid.Neutral || o == OwnerGrid.Void || o > players) continue;
                    if (claim == 0) claim = o;
                    else if (claim != o) contested = true;
                }
                if (claim != 0 && !contested) result.Add(new KeyValuePair<int, byte>(c, claim));
            }
            return result;
        }

        public static string F(double v) => v.ToString("0.###", CultureInfo.InvariantCulture);

        public static string Dump(IEnumerable<SimEvent> events)
        {
            var sb = new StringBuilder();
            foreach (SimEvent e in events) sb.Append("  ").Append(e).Append('\n');
            return sb.ToString();
        }
    }
}
