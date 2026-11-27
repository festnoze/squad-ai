// Owned by traits-verify (wave D-1): adversarial verification of the biome traits (docs/BIOME_TRAITS.md, contract 27).
// Attacks, in the order of the verification brief:
//   1. classic bit-identity (null traits, all-disabled sets with invalid parameters, every trait at a neutral parameter);
//   2. a trait switched off has no side effect on the others (disabled == removed, inert traits leave the rest
//      bit-identical, order and duplicates do not matter, each config trait touches only its own SimConfig fields);
//   3. Core has no biome concept and any trait combination runs (all eight together, mixed and random sets);
//   4. determinism and invariants of every biome set, with independent oracles checked on every tick: the Propagation
//      ring (exact cells), the Coalescence hole postcondition, the R11 cut geometry under ArcReach, the spark closed form
//      on the BASE pawn speed, the Conduction / Inertia step limits, and "Propagation never triggers a return";
//   5. the section 2 edge cases as scripted scenarios (home claimant's head disc, ArcReach at the HeadGrace boundary,
//      RingInterval with the lasso off, config traits on the cloned config only).
// Pure NUnit + PainterIO.Core (no UnityEngine), NUnit 3.5 features only.
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class TraitsAuditTests
    {
#if UNITY_5_3_OR_NEWER
        // Editor Mono is several times slower than the dotnet loop: shorter rounds and fewer cases (dotnet runs them all).
        private const double LongRound = 20.0;
        private const double ShortRound = 8.0;
#else
        private const double LongRound = 90.0;
        private const double ShortRound = 30.0;
#endif

        /// <summary>Every trait enabled at a parameter that changes nothing (ScorchedEarth is inert without a filler).</summary>
        private const string NeutralKey =
            "Inertia(540);Coalescence(0);SparkSpeed(1.8);Propagation(4,0);ScorchedEarth(15);Conduction(1);ArcReach(1);RingInterval(15)";

        // kill-core (wave D-2): the v1.1 default sets (section 3 + section 7 kill rewards) run through the same audits.
        private static readonly string[] BiomeNames = { "Liquide", "Feu", "Electricite", "Liquide v1.1", "Feu v1.1", "Electricite v1.1" };

        private static RuleTraits Biome(string name)
        {
            switch (name)
            {
                case "Liquide": return TraitTestKit.Liquid;
                case "Feu": return TraitTestKit.Fire;
                case "Liquide v1.1": return TraitTestKit.LiquidV11;
                case "Feu v1.1": return TraitTestKit.FireV11;
                case "Electricite v1.1": return TraitTestKit.ElectricV11;
                default: return TraitTestKit.Electric;
            }
        }

        private static Simulation Bots(ulong seed, RuleTraits traits, bool lasso, int rate, double duration)
        {
            return TraitTestKit.BotRound(seed, traits, lasso, rate, -1, duration);
        }

        // ============================================================================================================
        // 1. Classic bit-identity
        // ============================================================================================================

        /// <summary>
        /// The rolling hash of the pre-trait baseline row (seed 1, 60 Hz, lasso on, no human) must come out of a null
        /// trait set, of the parsed "classic" variants and of a set whose eight specs are all disabled with parameters
        /// that would be invalid if enabled (kept but inert: no validation, no config change, no behaviour, no salt).
        /// </summary>
        [Test]
        public void TraitsAudit_1_NullParsedAndDisabledInvalidSetsAreBitIdenticalToClassic()
        {
            const ulong expected = 0x8CB763231AC73608UL;
            var disabled = new RuleTraits(new[]
            {
                new TraitSpec(TraitId.Inertia, -5.0, double.NaN, false), new TraitSpec(TraitId.Coalescence, -1.0, double.NaN, false),
                new TraitSpec(TraitId.SparkSpeed, 0.5, double.NaN, false), new TraitSpec(TraitId.Propagation, -1.0, 999.0, false),
                new TraitSpec(TraitId.ScorchedEarth, -1.0, double.NaN, false), new TraitSpec(TraitId.Conduction, 0.0, double.NaN, false),
                new TraitSpec(TraitId.ArcReach, -3.0, double.NaN, false), new TraitSpec(TraitId.RingInterval, -1.0, double.NaN, false),
            });
            Assert.AreEqual(8, disabled.Specs.Count);
            Assert.IsTrue(disabled.IsClassic);
            Assert.AreEqual("", disabled.ToKey());
            Assert.AreEqual(0, TraitRegistry.CreateBehaviours(disabled).Count);
            foreach (TraitId id in TraitDefaults.All)
            {
                Assert.IsFalse(disabled.Has(id), id + " disabled");
                Assert.IsNull(disabled.Get(id), id + " disabled");
            }
            Assert.IsTrue(RuleTraits.Parse(" CLASSIC ").IsClassic);
            Assert.IsTrue(RuleTraits.Parse(";;").IsClassic, "only empty tokens");

            var variants = new List<KeyValuePair<string, RuleTraits>>
            {
                new KeyValuePair<string, RuleTraits>("all disabled, invalid parameters", disabled),
#if !UNITY_5_3_OR_NEWER
                new KeyValuePair<string, RuleTraits>("null", null),
                new KeyValuePair<string, RuleTraits>("Parse(\";;\")", RuleTraits.Parse(";;")),
#endif
            };
            foreach (KeyValuePair<string, RuleTraits> v in variants)
            {
                var controllers = new IController[4];
                for (int i = 0; i < 4; i++)
                    controllers[i] = new BotController(BotPersonality.Preset(TraitTestKit.Lineup[i]), BotTests.BotSeed(1UL, i));
                var config = new SimConfig { Seed = 1UL, TickRate = 60, LassoEnabled = true, Traits = v.Value };
                var sim = new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
                Assert.IsTrue(sim.View.Traits.IsClassic, v.Key);
                Assert.AreEqual(expected.ToString("X16"), TraitTestKit.RollingRoundHash(sim, 30, false).ToString("X16"),
                                v.Key + ": must reproduce the pre-trait rolling hash");
            }
        }

        private static IEnumerable<object[]> NeutralCases()
        {
#if UNITY_5_3_OR_NEWER
            yield return new object[] { 60, 11UL };
#else
            foreach (int rate in CrossRates)
            {
                yield return new object[] { rate, 11UL };
                yield return new object[] { rate, 12UL };
            }
#endif
        }

        /// <summary>
        /// All eight traits enabled at once, each at a parameter that changes nothing, must evolve exactly like the classic
        /// round (positions, headings, trails, sparks, grid, every event with its time and cells) for a full bot round with
        /// the lasso on: the trait plumbing itself (speed factor hook, AugmentCapture with no addition, OnEliminated,
        /// EndOfTick, TraitTime switching, the cloned config) has no side effect. Only the hash salt differs.
        /// </summary>
        [TestCaseSource(nameof(NeutralCases))]
        public void TraitsAudit_1_AllEightTraitsAtNeutralParametersEvolveExactlyLikeClassic(int rate, ulong seed)
        {
            RuleTraits neutral = RuleTraits.Parse(NeutralKey);
            Assert.AreEqual(8, neutral.EnabledCount);
            Simulation classic = Bots(seed, RuleTraits.Classic, true, rate, LongRound);
            Simulation traited = Bots(seed, neutral, true, rate, LongRound);
            Assert.AreEqual(4, TraitRegistry.CreateBehaviours(traited.Config.Traits).Count, "the four behaviours are attached");
            Assert.AreNotEqual(classic.StateHash(), traited.StateHash(), "an enabled trait salts the hash");
            int ticks = AssertSameEvolution("neutral traits " + rate + " Hz seed " + seed, classic, traited, false);
            Assert.That(ticks, Is.GreaterThan(100));
        }

        // ============================================================================================================
        // 2. Switching a trait off has no side effect on the others
        // ============================================================================================================

        private static IEnumerable<object[]> BiomeTraitPairs()
        {
            foreach (string biome in BiomeNames)
            {
                foreach (TraitSpec s in Biome(biome).Specs)
                {
#if UNITY_5_3_OR_NEWER
                    if (biome != "Feu" && biome != "Feu v1.1") continue;
#endif
                    // v1.1 sets: only their kill reward is new (the section 3 traits are covered by the rows above).
                    if (biome.EndsWith("v1.1", StringComparison.Ordinal) && (int)s.Id < (int)TraitId.KillInheritance) continue;
                    yield return new object[] { biome, (int)s.Id };
                }
            }
        }

        /// <summary>
        /// For every trait of every biome set: the set with that trait DISABLED (spec kept, Enabled = false, via With) and
        /// the set WITHOUT that spec are the same round (same key, same SimConfig after ApplyConfig, same behaviours,
        /// identical StateHash every tick of a bot round with the lasso on), and the remaining traits are all still
        /// applied with their own parameters.
        /// </summary>
        [TestCaseSource(nameof(BiomeTraitPairs))]
        public void TraitsAudit_2_DisablingOneTraitOfABiomeEqualsRemovingItAndKeepsTheOthers(string biome, int traitId)
        {
            var id = (TraitId)traitId;
            RuleTraits set = Biome(biome);
            RuleTraits off = set.With(new TraitSpec(id, double.NaN, double.NaN, false));
            var rest = new List<TraitSpec>();
            foreach (TraitSpec s in set.Specs)
            {
                if (s.Id != id) rest.Add(s);
            }
            var minus = new RuleTraits(rest);
            Assert.IsFalse(off.Has(id));
            Assert.AreEqual(set.EnabledCount - 1, off.EnabledCount);
            Assert.AreEqual(minus.ToKey(), off.ToKey(), "a disabled spec leaves the key");
            foreach (TraitSpec s in minus.Specs)
            {
                Assert.IsTrue(off.Has(s.Id), s.Id + " stays enabled when " + id + " is switched off");
                Assert.AreEqual(s.P1, off.Get(s.Id).P1, s.Id + " keeps its P1");
                Assert.AreEqual(s.P2, off.Get(s.Id).P2, s.Id + " keeps its P2");
            }

            Simulation a = Bots(41UL, off, true, 60, ShortRound);
            Simulation b = Bots(41UL, minus, true, 60, ShortRound);
            AssertConfigFollowsTraits(off, a.Config, biome + " - " + id + " (disabled)");
            AssertConfigFollowsTraits(minus, b.Config, biome + " - " + id + " (removed)");
            Assert.AreEqual(BehaviourIds(minus), BehaviourIds(off));
            AssertSameEvolution(biome + " with " + id + " disabled vs removed", a, b, true);
        }

        /// <summary>
        /// Each trait alone equals the full catalogue with only that trait enabled (the seven disabled specs, with invalid
        /// parameters, are inert): same config, same behaviours, identical StateHash every tick.
        /// </summary>
        [Test]
        public void TraitsAudit_2_EachTraitAloneEqualsTheCatalogueWithOnlyItEnabled()
        {
            foreach (TraitId id in TraitDefaults.All)
            {
#if UNITY_5_3_OR_NEWER
                if (id != TraitId.Propagation && id != TraitId.Conduction) continue;
#endif
                var specs = new List<TraitSpec>();
                foreach (TraitId other in TraitDefaults.All)
                    specs.Add(other == id ? new TraitSpec(other) : new TraitSpec(other, -7.0, -7.0, false));
                var catalogue = new RuleTraits(specs);
                RuleTraits alone = TraitTestKit.One(id);
                Assert.AreEqual(alone.ToKey(), catalogue.ToKey(), id.ToString());
                Simulation a = Bots(43UL, alone, true, 60, ShortRound);
                Simulation b = Bots(43UL, catalogue, true, 60, ShortRound);
                AssertConfigFollowsTraits(catalogue, b.Config, id + " in the catalogue");
                AssertSameEvolution(id + " alone vs catalogue with only " + id, a, b, true);
            }
        }

        /// <summary>
        /// Traits that cannot act leave the others bit-identical: ScorchedEarth alone (nothing fills cells) evolves like
        /// classic; Feu minus Propagation (SparkSpeed + ScorchedEarth) evolves like SparkSpeed(2.1) alone; RingInterval
        /// with the lasso option off changes nothing, alone and inside the Electricite set; Liquide minus Coalescence is
        /// Inertia alone, and Coalescence(0) inside Liquide is Inertia alone too.
        /// </summary>
        [Test]
        public void TraitsAudit_2_InertTraitsLeaveTheRestBitIdentical()
        {
            int[] rates =
#if UNITY_5_3_OR_NEWER
                { 60 };
#else
                { 30, 144 };
#endif
            foreach (int rate in rates)
            {
                AssertSameEvolution("ScorchedEarth alone vs classic " + rate, Bots(51UL, TraitTestKit.One(TraitId.ScorchedEarth), true, rate, ShortRound),
                                    Bots(51UL, RuleTraits.Classic, true, rate, ShortRound), false);
                AssertSameEvolution("Feu - Propagation vs SparkSpeed(2.1) " + rate,
                                    Bots(52UL, RuleTraits.Parse("SparkSpeed(2.1);ScorchedEarth(15)"), true, rate, ShortRound),
                                    Bots(52UL, TraitTestKit.One(TraitId.SparkSpeed, 2.1), true, rate, ShortRound), false);
                AssertSameEvolution("RingInterval alone, lasso off, vs classic " + rate,
                                    Bots(53UL, TraitTestKit.One(TraitId.RingInterval), false, rate, ShortRound),
                                    Bots(53UL, RuleTraits.Classic, false, rate, ShortRound), false);
                AssertSameEvolution("Electricite, lasso off, vs Electricite - RingInterval " + rate,
                                    Bots(54UL, TraitTestKit.Electric, false, rate, ShortRound),
                                    Bots(54UL, RuleTraits.Parse("SparkSpeed(1.5);Conduction(1.3);ArcReach(1.4)"), false, rate, ShortRound), false);
                AssertSameEvolution("Liquide with Coalescence(0) vs Inertia(420) " + rate,
                                    Bots(55UL, RuleTraits.Parse("Inertia(420);Coalescence(0)"), true, rate, ShortRound),
                                    Bots(55UL, TraitTestKit.One(TraitId.Inertia, 420), true, rate, ShortRound), false);
            }
            // Sanity: RingInterval does act with the lasso on (a ring at t = 10 s instead of 15 s).
            Simulation on = Bots(53UL, TraitTestKit.One(TraitId.RingInterval), true, 60, 12.0);
            var log = new EventLog(on);
            RunUntilTime(on, 11.0, false);
            Assert.That(log.Count(SimEventType.RingSpawned), Is.GreaterThanOrEqualTo(1), "lasso on: the first ring comes at 10 s");
        }

        /// <summary>The order in which specs are given and earlier duplicates never matter (canonical TraitId order).</summary>
        [Test]
        public void TraitsAudit_2_SpecOrderAndDuplicatesDoNotMatter()
        {
            var shuffled = new RuleTraits(new[]
            {
                new TraitSpec(TraitId.ScorchedEarth, 3.0), new TraitSpec(TraitId.Propagation, 2.0, 2.0),
                new TraitSpec(TraitId.SparkSpeed, 2.1), new TraitSpec(TraitId.Propagation, 4.0, 1.0),
                new TraitSpec(TraitId.ScorchedEarth, 15.0),
            });
            RuleTraits fire = TraitTestKit.Fire;
            Assert.AreEqual(fire, shuffled, "last duplicate wins, canonical order");
            Assert.AreEqual(fire.ToKey(), shuffled.ToKey());
            Assert.AreEqual(fire.GetHashCode(), shuffled.GetHashCode());
            AssertSameEvolution("Feu canonical vs shuffled with duplicates", Bots(61UL, fire, true, 60, ShortRound),
                                Bots(61UL, shuffled, true, 60, ShortRound), true);

            Assert.IsFalse(new RuleTraits(new[] { new TraitSpec(TraitId.Propagation), new TraitSpec(TraitId.Propagation, double.NaN, double.NaN, false) })
                           .Has(TraitId.Propagation), "a later 'off' overrides an earlier 'on'");
            Assert.IsTrue(new RuleTraits(new[] { new TraitSpec(TraitId.Propagation, double.NaN, double.NaN, false), new TraitSpec(TraitId.Propagation) })
                          .Has(TraitId.Propagation), "a later 'on' overrides an earlier 'off'");
        }

        /// <summary>
        /// Each config trait rewrites only its own SimConfig fields (Inertia: TurnRateDeg; SparkSpeed: SparkSpeedFactor;
        /// ArcReach: ContactScale; RingInterval: LassoFirstSpawn and LassoRespawn) and each behaviour trait none: every
        /// other public field of the round's config equals the classic round's (reflection over all public fields).
        /// </summary>
        [Test]
        public void TraitsAudit_2_EachConfigTraitTouchesOnlyItsOwnFields()
        {
            var own = new Dictionary<TraitId, string[]>
            {
                { TraitId.Inertia, new[] { "TurnRateDeg" } },
                { TraitId.SparkSpeed, new[] { "SparkSpeedFactor" } },
                { TraitId.ArcReach, new[] { "ContactScale" } },
                { TraitId.RingInterval, new[] { "LassoFirstSpawn", "LassoRespawn" } },
            };
            SimConfig classic = Bots(1UL, RuleTraits.Classic, true, 60, 90.0).Config;
            FieldInfo[] fields = typeof(SimConfig).GetFields(BindingFlags.Public | BindingFlags.Instance);
            Assert.That(fields.Length, Is.GreaterThanOrEqualTo(30), "every Tuning entry + Seed + Traits + ContactScale");
            foreach (TraitId id in TraitDefaults.All)
            {
                SimConfig cfg = Bots(1UL, TraitTestKit.One(id, OddValue(id)), true, 60, 90.0).Config;
                own.TryGetValue(id, out string[] mine);
                foreach (FieldInfo f in fields)
                {
                    if (f.Name == "Traits") continue;
                    bool isMine = mine != null && Array.IndexOf(mine, f.Name) >= 0;
                    object expectedValue = isMine ? (object)OddValue(id) : f.GetValue(classic);
                    Assert.AreEqual(expectedValue, f.GetValue(cfg), id + " alone: SimConfig." + f.Name);
                }
                Assert.AreEqual(TraitDefaults.KindOf(id) == TraitKind.Config, mine != null, id + ": config traits are exactly the four");
            }
        }

        /// <summary>A valid, non-default, non-neutral P1 per trait (so a leak into another field would show).</summary>
        private static double OddValue(TraitId id)
        {
            switch (id)
            {
                case TraitId.Inertia: return 377.0;
                case TraitId.Coalescence: return 3.25;
                case TraitId.SparkSpeed: return 2.375;
                case TraitId.Propagation: return 3.5;
                case TraitId.ScorchedEarth: return 7.5;
                case TraitId.Conduction: return 1.125;
                case TraitId.ArcReach: return 1.3125;
                case TraitId.KillInheritance: return 0.625;   // kill-core (wave D-2): Share must stay in [0, 1]
                case TraitId.KillSpeedBoost: return 0.15;
                case TraitId.KillShield: return 2.5;
                default: return 11.5;
            }
        }

        // ============================================================================================================
        // 3. No biome in Core; any trait can be combined with any other
        // ============================================================================================================

        /// <summary>
        /// Structural proof that no trait can test a biome: the Core assembly has no type, field, property, method or
        /// parameter whose name mentions a biome (the BiomeId type lives in the Runtime assembly, which Core cannot see).
        /// </summary>
        [Test]
        public void TraitsAudit_3_CoreAssemblyHasNoBiomeConcept()
        {
            Assembly core = typeof(Simulation).Assembly;
            var offenders = new List<string>();
            const BindingFlags all = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static
                                     | BindingFlags.DeclaredOnly;
            foreach (Type t in core.GetTypes())
            {
                if (Mentions(t.FullName)) offenders.Add("type " + t.FullName);
                foreach (MemberInfo m in t.GetMembers(all))
                {
                    if (Mentions(m.Name)) offenders.Add(t.Name + "." + m.Name);
                    if (m is MethodBase mb)
                    {
                        foreach (ParameterInfo p in mb.GetParameters())
                        {
                            if (Mentions(p.Name) || Mentions(p.ParameterType.FullName)) offenders.Add(t.Name + "." + m.Name + "(" + p.Name + ")");
                        }
                    }
                    if (m is FieldInfo fi && Mentions(fi.FieldType.FullName)) offenders.Add(t.Name + "." + m.Name + " : " + fi.FieldType.Name);
                }
            }
            Assert.AreEqual(0, offenders.Count, "Core must not know biomes: " + string.Join(", ", offenders.ToArray()));
        }

        private static bool Mentions(string name)
        {
            if (string.IsNullOrEmpty(name)) return false;
            string n = name.ToLowerInvariant();
            return n.Contains("biome") || n.Contains("liquid") || n.Contains("electric") || n.Contains("feu") || n.Contains("fire");
        }

        private static IEnumerable<object[]> AnyCombinationCases()
        {
            yield return new object[] { "all eight", "Inertia;Coalescence;SparkSpeed;Propagation;ScorchedEarth;Conduction;ArcReach;RingInterval", 30 };
            yield return new object[] { "Liquide + Feu", TraitTestKit.LiquidKey + ";" + TraitTestKit.FireKey, 60 };
#if !UNITY_5_3_OR_NEWER
            yield return new object[] { "Feu + Electricite", TraitTestKit.FireKey + ";" + TraitTestKit.ElectricKey, 144 };
            yield return new object[] { "Liquide + Electricite", TraitTestKit.LiquidKey + ";" + TraitTestKit.ElectricKey, 30 };
            var rng = new Rng(0xA0D17UL);
            for (int k = 0; k < 6; k++)
            {
                var specs = new List<TraitSpec>();
                foreach (TraitId id in TraitDefaults.All)
                {
                    if (rng.NextDouble() < 0.5) continue;
                    specs.Add(RandomSpec(id, rng));
                }
                if (specs.Count == 0) specs.Add(RandomSpec(TraitId.Propagation, rng));
                int rate = CrossRates[k % CrossRates.Length];
                yield return new object[] { "random " + k, new RuleTraits(specs).ToKey(), rate };
            }
#endif
        }

        private static TraitSpec RandomSpec(TraitId id, Rng rng)
        {
            switch (id)
            {
                case TraitId.Inertia: return new TraitSpec(id, rng.Range(300.0, 700.0));
                case TraitId.Coalescence: return new TraitSpec(id, rng.Range(0.5, 12.0));
                case TraitId.SparkSpeed: return new TraitSpec(id, rng.Range(1.2, 2.6));
                case TraitId.Propagation: return new TraitSpec(id, (1 + (int)rng.Range(0.0, 30.0)) / 6.0, 1 + (int)rng.Range(0.0, 2.0));
                case TraitId.ScorchedEarth: return new TraitSpec(id, rng.Range(1.0, 20.0));
                case TraitId.Conduction: return new TraitSpec(id, rng.Range(0.7, 1.45));
                case TraitId.ArcReach: return new TraitSpec(id, rng.Range(0.8, 1.6));
                // kill-core (wave D-2): the section 7 kill rewards.
                case TraitId.KillInheritance: return new TraitSpec(id, rng.Range(0.2, 1.0));
                case TraitId.KillSpeedBoost: return new TraitSpec(id, rng.Range(0.05, 0.3), rng.Range(0.1, 0.5));
                case TraitId.KillShield: return new TraitSpec(id, rng.Range(0.5, 6.0));
                default: return new TraitSpec(id, rng.Range(4.0, 20.0));
            }
        }

        /// <summary>
        /// Any trait can go to any biome: the eight together, unions of two biome sets (SparkSpeed duplicates: the last
        /// wins) and seeded random subsets with random valid parameters all build, round-trip through their key, keep every
        /// audit invariant every tick and are deterministic (same seed, same hash).
        /// </summary>
        [TestCaseSource(nameof(AnyCombinationCases))]
        public void TraitsAudit_3_AnyTraitCombinationRunsWithInvariantsAndIsDeterministic(string name, string key, int rate)
        {
            RuleTraits traits = RuleTraits.Parse(key);
            Assert.AreEqual(traits, RuleTraits.Parse(traits.ToKey()), name + ": key round trip");
            Simulation sim = Bots(71UL + (ulong)key.Length, traits, true, rate, ShortRound);
            Simulation twin = Bots(71UL + (ulong)key.Length, traits, true, rate, ShortRound);
            AssertConfigFollowsTraits(traits, sim.Config, name);
            var audit = new Auditor(sim);
            int ticks = 0;
            while (!sim.Ended)
            {
                audit.Step();
                twin.Step();
                if (++ticks % 15 == 0 || sim.Ended) Assert.AreEqual(sim.StateHash(), twin.StateHash(), name + ": same seed, same hash at tick " + sim.Tick);
            }
            Assert.IsTrue(twin.Ended);
            TestContext.WriteLine(name + " [" + traits + "] " + rate + " Hz: " + audit.Summary());
        }

        // ============================================================================================================
        // 4. Determinism and oracle invariants of every biome set
        // ============================================================================================================

        private static IEnumerable<object[]> BiomeRuns()
        {
            foreach (string biome in BiomeNames)
            {
#if UNITY_5_3_OR_NEWER
                yield return new object[] { biome, 60, true };
#else
                yield return new object[] { biome, 30, false };
                yield return new object[] { biome, 60, true };
                yield return new object[] { biome, 144, true };
#endif
            }
        }

        /// <summary>
        /// A full bot round per biome set, rate and lasso option, with every audit oracle on every tick (see Auditor) and a
        /// twin round compared by StateHash every 15 ticks. Each oracle must actually have been exercised where it applies
        /// (growth instants for Feu, cuts for every set, isolated unchased returns for Liquide).
        /// </summary>
        [TestCaseSource(nameof(BiomeRuns))]
        public void TraitsAudit_4_BiomeSetsKeepEveryOracleAndAreDeterministic(string biome, int rate, bool lasso)
        {
            RuleTraits traits = Biome(biome);
            ulong seed = 80UL + (ulong)rate + (lasso ? 7UL : 0UL);
            Simulation sim = Bots(seed, traits, lasso, rate, LongRound);
            Simulation twin = Bots(seed, traits, lasso, rate, LongRound);
            var audit = new Auditor(sim);
            int ticks = 0;
            while (!sim.Ended)
            {
                audit.Step();
                twin.Step();
                if (++ticks % 15 == 0 || sim.Ended) Assert.AreEqual(sim.StateHash(), twin.StateHash(), biome + ": same seed, same hash at tick " + sim.Tick);
            }
            Assert.IsTrue(twin.Ended);
            Assert.AreEqual(0, sim.EventCapHits, "EventCapHits");
            TestContext.WriteLine(biome + " " + rate + " Hz lasso " + lasso + ": " + audit.Summary());
            Assert.That(audit.MotionChecks, Is.GreaterThan(1000), "motion oracle exercised");
            if (traits.Has(TraitId.Propagation)) Assert.That(audit.GrowthInstants, Is.GreaterThan(0), "Propagation oracle exercised");
            if (traits.Has(TraitId.Coalescence)) Assert.That(audit.HoleChecks, Is.GreaterThan(0), "Coalescence postcondition exercised");
        }

        /// <summary>
        /// R10 / R11 under ArcReach over many bot rounds (cuts are rare in one round): every cut point is within the scaled
        /// ContactRadius of the attacker's head at the cut instant, is PointAt(s_cut), and lies outside the HeadGrace zone;
        /// the spark then runs on the BASE pawn speed (Electricite set, plus a stronger ArcReach(1.6) alone).
        /// </summary>
        [Test]
        public void TraitsAudit_4_ArcReachCutsFollowR11OverManyRounds()
        {
            // Bots rarely cut in the first 30 s, so the rounds are full length (dotnet) or the Unity LongRound.
#if UNITY_5_3_OR_NEWER
            const int seeds = 1, minimumCuts = 0;
#else
            const int seeds = 6, minimumCuts = 6;
#endif
            int cuts = 0, sparks = 0;
            foreach (RuleTraits traits in new[] { TraitTestKit.Electric, TraitTestKit.One(TraitId.ArcReach, 1.6) })
            {
                for (int k = 0; k < seeds; k++)
                {
                    int rate = CrossRates[k % CrossRates.Length];
                    Simulation sim = Bots(300UL + (ulong)k, traits, k % 2 == 0, rate, LongRound);
                    var audit = new Auditor(sim);
                    while (!sim.Ended) audit.Step();
                    cuts += audit.CutChecks;
                    sparks += audit.SparkChecks;
                }
            }
            TestContext.WriteLine("ArcReach rounds: " + cuts + " cuts checked, " + sparks + " spark ticks checked");
            Assert.That(cuts, Is.GreaterThanOrEqualTo(minimumCuts), "the cut oracle was exercised");
        }

        // ============================================================================================================
        // 5. Section 2 edge cases (scripted)
        // ============================================================================================================

        /// <summary>
        /// Propagation spares the cells under a HOME claimant's own head: player 0 walks North / South on the last column of
        /// its land [-10, -2] x [-4, 4] and is at (-2.0625, -2.9375) at t = 4. The 7 cells of the first neutral column whose
        /// centers lie within HeadRadius stay neutral, the other 57 grow, the player stays home, at every rate.
        /// </summary>
        [Test]
        public void TraitsAudit_5_PropagationSparesTheHomeClaimantsOwnHeadDisc()
        {
            Func<int, Simulation> build = rate =>
            {
                var sb = new SimBuilder(rate);
                sb.Config.Traits = TraitTestKit.One(TraitId.Propagation);
                sb.AddRect(-10, -4, -2, 4, V(-2 - H, -3 + H), North, Legs((North, 6), (South, 6), (North, 6), (South, 6), (North, 6)));
                sb.AddIdle(IdleCorners[2]);
                return sb.Build();
            };
            TraitTestKit.CrossRate("Propagation home head disc", build, 4.0, run =>
            {
                Simulation sim = run.Sim;
                Assert.That(sim.Time, Is.EqualTo(4.0).Within(1e-9));
                PlayerState p = sim.Players[0];
                Assert.IsTrue(p.Home, "the claimant is home on its edge column");
                AssertNear(V(-2 - H, -3 + H), p.Pos, 1e-9, "head at t = 4");
                SimEvent grew = run.Log.Single(SimEventType.TerritoryGrew, 0);
                int[] column = TraitTestKit.RectCells(sim.Grid, -1.95, -4, -1.9, 4);
                Assert.AreEqual(64, column.Length);
                int spared = 0;
                foreach (int c in column)
                {
                    Vec2d center = sim.Grid.CellCenter(c % sim.Grid.Size, c / sim.Grid.Size);
                    bool under = Vec2d.Distance(center, p.Pos) <= sim.Config.HeadRadius;
                    Assert.AreEqual(under ? OwnerGrid.Neutral : (byte)1, sim.Grid.Cells[c], run.Rate + " Hz: column cell at y = " + center.Y);
                    Assert.AreEqual(!under, TraitTestKit.Contains(grew.Cells, c));
                    if (under) spared++;
                }
                Assert.AreEqual(7, spared, "the head disc covers 7 cells of the column");
            });
        }

        /// <summary>
        /// ArcReach at the HeadGrace boundary (R11): the victim trails East on y = H, the attacker passes it head-on, home on
        /// its strip, 0.8 u to the side (0.63 &lt; 0.8 &lt; 0.882). The attacker meets the end of the EXPOSED part while it
        /// is still beside the protected last 1 u, so s_cut = L(t) - HeadGrace, the contact distance is exactly
        /// ContactRadius = 0.882, the cut is at t = (9 - sqrt(0.882^2 - 0.64)) / 12 at every rate, and the classic round
        /// never cuts.
        /// </summary>
        [Test]
        public void TraitsAudit_5_ArcReachCutAtTheHeadGraceBoundaryFollowsR11()
        {
            double dx = Math.Sqrt(0.882 * 0.882 - 0.64);
            double tCut = (9.0 - dx) / 12.0;
            double sCut = 8.0 + 6.0 * tCut - 1.0;
            TraitTestKit.CrossRate("ArcReach grace boundary", rate => PassBy(rate, TraitTestKit.One(TraitId.ArcReach)), 1.5, run =>
            {
                SimEvent cut = run.Log.Single(SimEventType.Cut, 0);
                Assert.AreEqual(1, cut.Other);
                Assert.That(cut.Time, Is.EqualTo(tCut).Within(1e-6), run.Rate + " Hz cut time");
                Assert.That(cut.S, Is.EqualTo(sCut).Within(1e-6), run.Rate + " Hz: s_cut = L(t) - HeadGrace");
                AssertNear(V(-10 + sCut, H), cut.Point, 1e-6, run.Rate + " Hz: cut point");
                Vec2d attacker = V(6.0 - 6.0 * cut.Time, H - 0.8);
                Assert.That(Vec2d.Distance(attacker, cut.Point), Is.EqualTo(0.882).Within(1e-6), "contact at exactly ContactRadius");
                Assert.That(Vec2d.Distance(attacker, V(-2.0 + 6.0 * cut.Time, H)), Is.GreaterThan(0.9), "heads never touched");
            });
            Simulation classic = PassBy(60, RuleTraits.Classic);
            var log = new EventLog(classic);
            RunUntilTime(classic, 1.5);
            Assert.AreEqual(0, log.Count(SimEventType.Cut), "classic: 0.8 u is out of reach");
        }

        private static Simulation PassBy(int rate, RuleTraits traits)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-28, 20, -24, 24, V(-26 + H, 22 + H), East, new ConstantHeadingController(East));
            sb.AddRect(-12, -1, 12, -0.5, V(6, H - 0.8), West, new ConstantHeadingController(West));
            Simulation sim = sb.Build();
            sim.DebugSetTrail(0, new[] { V(-10, H), V(-2, H) });
            Assert.IsTrue(sim.Players[1].Home, "the attacker cuts from home");
            return sim;
        }

        /// <summary>
        /// Config traits act on the round's CLONED config only: the caller's SimConfig (every public field) and its
        /// RuleTraits (reference and value) are untouched by the constructor and by a played round, later changes to the
        /// caller's object never leak into the round, and mutating the TraitSpec objects given to a RuleTraits never
        /// changes that RuleTraits.
        /// </summary>
        [Test]
        public void TraitsAudit_5_ConfigTraitsActOnTheClonedConfigOnly()
        {
            FieldInfo[] fields = typeof(SimConfig).GetFields(BindingFlags.Public | BindingFlags.Instance);
            foreach (KeyValuePair<string, RuleTraits> set in TraitTestKit.AllSets())
            {
                var caller = new SimConfig
                {
                    Seed = 5UL, TickRate = 60, TurnRateDeg = 0.0, SparkSpeedFactor = 1.7, LassoFirstSpawn = 12.0, LassoRespawn = 13.0,
                    LassoEnabled = true, Traits = set.Value,
                };
                RuleTraits callerTraits = caller.Traits;
                RuleTraits callerCopy = callerTraits.Clone();
                var before = new object[fields.Length];
                for (int k = 0; k < fields.Length; k++) before[k] = fields[k].GetValue(caller);

                var controllers = new IController[] { new HomeCirclerController(IdleCorners[0]), new HomeCirclerController(IdleCorners[2]) };
                var sim = new Simulation(caller, controllers, new SimSetup
                {
                    StartPositions = new[] { IdleCorners[0], IdleCorners[2] }, HumanIndex = -1,
                });
                StepN(sim, 30);
                for (int k = 0; k < fields.Length; k++)
                    Assert.AreEqual(before[k], fields[k].GetValue(caller), set.Key + ": caller's SimConfig." + fields[k].Name);
                Assert.AreSame(callerTraits, caller.Traits, set.Key);
                Assert.AreEqual(callerCopy, caller.Traits, set.Key + ": caller's RuleTraits value");
                Assert.AreNotSame(caller, sim.Config);
                if (!callerTraits.IsClassic) Assert.AreNotSame(callerTraits, sim.Config.Traits, set.Key + ": the round deep-copies the traits");
                AssertConfigFollowsTraits(set.Value, sim.Config, set.Key, caller);

                // Later changes to the caller's object never reach the round.
                caller.TurnRateDeg = 999.0;
                caller.SparkSpeedFactor = 5.0;
                caller.ContactScale = 3.0;
                caller.Traits = RuleTraits.Classic;
                AssertConfigFollowsTraits(set.Value, sim.Config, set.Key + " after the caller changed", (SimConfig)null);
                Assert.AreEqual(set.Value, sim.Config.Traits);
            }

            // The specs given to a RuleTraits are copied.
            var given = new TraitSpec(TraitId.SparkSpeed, 2.1);
            var traits = new RuleTraits(new[] { given });
            given.P1 = 9.0;
            given.Enabled = false;
            Assert.IsTrue(traits.Has(TraitId.SparkSpeed));
            Assert.AreEqual(2.1, traits.Get(TraitId.SparkSpeed).P1);
        }

        // ============================================================================================================
        // Helpers
        // ============================================================================================================

        private static string BehaviourIds(RuleTraits traits)
        {
            var sb = new StringBuilder();
            foreach (ISimTrait t in TraitRegistry.CreateBehaviours(traits)) sb.Append(t.Id).Append(' ');
            return sb.ToString();
        }

        private static void AssertConfigFollowsTraits(RuleTraits traits, SimConfig cfg, string label)
        {
            AssertConfigFollowsTraits(traits, cfg, label, new SimConfig());
        }

        /// <summary>The round's config: each config trait's field holds its P1, every other one the caller's value.</summary>
        private static void AssertConfigFollowsTraits(RuleTraits traits, SimConfig cfg, string label, SimConfig caller)
        {
            SimConfig basis = caller ?? new SimConfig { TurnRateDeg = 0.0, SparkSpeedFactor = 1.7, LassoFirstSpawn = 12.0, LassoRespawn = 13.0 };
            TraitSpec s;
            s = traits?.Get(TraitId.Inertia);
            Assert.AreEqual(s != null ? s.P1 : basis.TurnRateDeg, cfg.TurnRateDeg, label + ": TurnRateDeg");
            s = traits?.Get(TraitId.SparkSpeed);
            Assert.AreEqual(s != null ? s.P1 : basis.SparkSpeedFactor, cfg.SparkSpeedFactor, label + ": SparkSpeedFactor");
            s = traits?.Get(TraitId.ArcReach);
            Assert.AreEqual(s != null ? s.P1 : 1.0, cfg.ContactScale, label + ": ContactScale");
            s = traits?.Get(TraitId.RingInterval);
            Assert.AreEqual(s != null ? s.P1 : basis.LassoFirstSpawn, cfg.LassoFirstSpawn, label + ": LassoFirstSpawn");
            Assert.AreEqual(s != null ? s.P1 : basis.LassoRespawn, cfg.LassoRespawn, label + ": LassoRespawn");
            Assert.AreEqual(Tuning.PawnSpeed, cfg.PawnSpeed, label + ": no trait changes the base PawnSpeed");
            Assert.AreEqual(cfg.SparkSpeedFactor * cfg.PawnSpeed, cfg.SparkSpeed, label + ": spark speed on the BASE pawn speed");
            Assert.AreEqual((cfg.HeadRadius + cfg.TrailHalfWidth) * cfg.ContactScale, cfg.ContactRadius, label + ": ContactRadius");
        }

        /// <summary>
        /// Steps a and b together until both ended and fails at the first tick whose state differs: positions, headings,
        /// cells, flags, trails, sparks, pockets, counters, ring, every event (type, players, cause, chased, exact time,
        /// cells), the grid every 30 ticks and at the end; with sameHash, StateHash too. Returns the tick count.
        /// </summary>
        internal static int AssertSameEvolution(string label, Simulation a, Simulation b, bool sameHash)
        {
            int ticks = 0;
            while (!a.Ended || !b.Ended)
            {
                if (a.Ended != b.Ended) Assert.Fail(label + ": one round ended first, at tick " + a.Tick);
                a.Step();
                b.Step();
                ticks++;
                bool full = ticks % 30 == 0 || a.Ended;
                string diff = Difference(a, b, full);
                if (diff != null) Assert.Fail(label + ": tick " + a.Tick + ": " + diff);
                if (sameHash && full && a.StateHash() != b.StateHash()) Assert.Fail(label + ": StateHash differs at tick " + a.Tick);
                if (ticks > 2000000) Assert.Fail(label + ": no end");
            }
            Assert.AreEqual(0, a.EventCapHits, label + ": EventCapHits");
            Assert.AreEqual(0, b.EventCapHits, label + ": EventCapHits");
            if (a.Result != null && b.Result != null)
            {
                Assert.AreEqual(a.Result.Reason, b.Result.Reason, label);
                Assert.AreEqual(a.Result.Ranks, b.Result.Ranks, label);
            }
            return ticks;
        }

        private static string Difference(Simulation a, Simulation b, bool grid)
        {
            if (a.Tick != b.Tick || a.Ended != b.Ended) return "Tick / Ended";
            for (int i = 0; i < a.Players.Count; i++)
            {
                PlayerState p = a.Players[i], q = b.Players[i];
                string who = "player " + i + " ";
                if (p.Pos != q.Pos) return who + "Pos " + p.Pos + " vs " + q.Pos;
                if (p.Heading != q.Heading) return who + "Heading";
                if (p.Cell != q.Cell || p.Alive != q.Alive || p.Home != q.Home || p.Charged != q.Charged) return who + "cell / flags";
                if (p.Trail.Count != q.Trail.Count || p.Trail.Length != q.Trail.Length) return who + "trail";
                if ((p.Spark == null) != (q.Spark == null)) return who + "spark presence";
                if (p.Spark != null && (p.Spark.S != q.Spark.S || p.Spark.SCut != q.Spark.SCut || p.Spark.TimeCut != q.Spark.TimeCut)) return who + "spark";
                if (p.Pocket.Count != q.Pocket.Count) return who + "pocket";
                if (p.Captures != q.Captures || p.CutsMade != q.CutsMade || p.Kills != q.Kills || p.PocketsMade != q.PocketsMade) return who + "counters";
            }
            if ((a.Ring == null) != (b.Ring == null)) return "ring presence";
            if (a.Ring != null && a.Ring.Pos != b.Ring.Pos) return "ring position";
            if (a.NextRingTime != b.NextRingTime && a.Config.LassoEnabled) return "NextRingTime";
            IReadOnlyList<SimEvent> ea = a.LastEvents, eb = b.LastEvents;
            if (ea.Count != eb.Count) return "event count " + ea.Count + " vs " + eb.Count + "\n" + TraitTestKit.Dump(ea) + "vs\n" + TraitTestKit.Dump(eb);
            for (int k = 0; k < ea.Count; k++)
            {
                SimEvent x = ea[k], y = eb[k];
                if (x.Type != y.Type || x.Player != y.Player || x.Other != y.Other || x.Cause != y.Cause || x.Chased != y.Chased
                    || x.Time != y.Time || x.Point != y.Point || x.S != y.S || !SameCells(x.Cells, y.Cells))
                    return "event " + k + ": " + x + " vs " + y;
            }
            if (grid)
            {
                byte[] ga = a.Grid.Cells, gb = b.Grid.Cells;
                for (int c = 0; c < ga.Length; c++)
                {
                    if (ga[c] != gb[c]) return "grid cell " + c;
                }
            }
            return null;
        }

        // ============================================================================================================
        // The per-tick auditor (independent oracles)
        // ============================================================================================================

        /// <summary>
        /// Steps a simulation and checks, after every tick, TraitTestKit.AssertTraitInvariants plus:
        /// - motion: each tick's step length is PawnSpeed x Dt x SpeedMultiplier at tick start x (Conduction factor when the
        ///   cell was own at tick start) exactly away from the rim (at most that near it), and the heading turned by at most
        ///   TurnRateRad x Dt (SpeedMultiplier: kill-core, wave D-2);
        /// - sparks: S = SCut + Spark.Speed x (Time - TimeCut), Spark.Speed = SparkSpeedFactor x BASE PawnSpeed x the victim's
        ///   SpeedMultiplier at the cut (exactly the base without KillSpeedBoost; Conduction never speeds a spark);
        /// - cuts (R10 / R11, ArcReach): the attacker's head at the cut time is within ContactRadius of the cut point, the
        ///   cut point is Trail.PointAt(s_cut) and s_cut &lt;= L(t) - HeadGrace;
        /// - Propagation: TerritoryGrew only at interval crossings, after the event-loop events and before RingSpawned, and
        ///   its cells equal an independent ring oracle run on the grid rebuilt as it was just before the growth (neutral,
        ///   one claimant, not under a live head, not scorched, not on or next to the claimant's own trail raster);
        ///   with ScorchedEarth the grown cells were neutral before the tick; a Return in the next tick never enters a cell
        ///   grown for that player at that instant (Propagation never triggers its owner's return);
        /// - Coalescence: after a tick whose only grid change is one unchased Return, the returner's territory encloses no
        ///   neutral hole smaller than MaxHoleArea that still has an unscorched cell.
        /// </summary>
        private sealed class Auditor
        {
            private readonly Simulation sim;
            private readonly RuleTraits traits;
            private readonly int n;
            private readonly bool[] ownAtStart, aliveAtStart;
            private readonly double[] headingAtStart, multiplierAtStart;   // multiplier: kill-core (KillSpeedBoost, 7.1)
            private readonly double homeFactor;
            private byte[] gridBefore;
            private List<int>[] grownLastTick;
            private bool grewLastTick;

            public int MotionChecks, SparkChecks, CutChecks, GrowthInstants, GrownCells, ReturnAfterGrowthChecks, HoleChecks;
            public int ScorchSpared, HeadSpared, TrailSpared;

            public Auditor(Simulation sim)
            {
                this.sim = sim;
                traits = sim.View.Traits;
                n = sim.Players.Count;
                ownAtStart = new bool[n];
                aliveAtStart = new bool[n];
                headingAtStart = new double[n];
                multiplierAtStart = new double[n];
                homeFactor = ConductionTrait.HomeSpeedFactorOf(traits);
                gridBefore = new byte[sim.Grid.Cells.Length];
            }

            public string Summary()
            {
                return "motion " + MotionChecks + ", sparks " + SparkChecks + ", cuts " + CutChecks + ", growth instants " + GrowthInstants
                       + " (" + GrownCells + " cells; spared: " + HeadSpared + " under heads, " + TrailSpared + " by own trails, "
                       + ScorchSpared + " scorched), returns after growth " + ReturnAfterGrowthChecks + ", hole postconditions " + HoleChecks;
            }

            public void Step()
            {
                double t0 = sim.Time;
                for (int i = 0; i < n; i++)
                {
                    PlayerState p = sim.Players[i];
                    aliveAtStart[i] = p.Alive;
                    ownAtStart[i] = p.Alive && sim.Grid.Cells[p.Cell] == p.Id;
                    headingAtStart[i] = p.Heading;
                    multiplierAtStart[i] = p.SpeedMultiplier;
                }
                Buffer.BlockCopy(sim.Grid.Cells, 0, gridBefore, 0, gridBefore.Length);
                sim.Step();
                TraitTestKit.AssertTraitInvariants(sim);
                if (sim.Ended) return;   // the state froze at an in-tick instant: the per-tick formulas do not apply
                CheckMotion();
                CheckSparks();
                CheckCuts(t0);
                CheckReturnsAfterGrowth();
                CheckPropagation(t0);
                CheckCoalescence();
            }

            private string At => "tick " + sim.Tick + " (t = " + TraitTestKit.F(sim.Time) + "): ";

            private void CheckMotion()
            {
                SimConfig c = sim.Config;
                double margin = c.ArenaMargin + 1.0;
                double maxTurn = c.TurnRateRad * c.Dt;
                for (int i = 0; i < n; i++)
                {
                    PlayerState p = sim.Players[i];
                    if (!aliveAtStart[i] || !p.Alive) continue;
                    // kill-core (7.1): PawnSpeed x SpeedMultiplier (at tick start) x Conduction when home.
                    double expected = c.PawnSpeed * c.Dt * multiplierAtStart[i] * (ownAtStart[i] ? homeFactor : 1.0);
                    double moved = Vec2d.Distance(p.PrevPos, p.Pos);
                    bool inside = sim.Arena.SignedDistance(p.PrevPos) < -margin && sim.Arena.SignedDistance(p.Pos) < -margin;
                    if (inside && Math.Abs(moved - expected) > 1e-9)
                        Assert.Fail(At + "player " + i + " moved " + moved + ", expected " + expected + " (own at start " + ownAtStart[i] + ")");
                    if (moved > expected + 1e-9) Assert.Fail(At + "player " + i + " moved " + moved + " > " + expected);
                    if (c.TurnRateDeg > 0.0)
                    {
                        double turned = Math.Abs(Wrap(p.Heading - headingAtStart[i]));
                        if (turned > maxTurn + 1e-9) Assert.Fail(At + "player " + i + " turned " + turned + " > " + maxTurn);
                    }
                    MotionChecks++;
                }
            }

            private void CheckSparks()
            {
                double baseSpeed = sim.Config.SparkSpeedFactor * Tuning.PawnSpeed;
                for (int i = 0; i < n; i++)
                {
                    PlayerState p = sim.Players[i];
                    if (!p.Alive || p.Spark == null) continue;
                    // kill-core (7.1): the spark runs at Spark.Speed, fixed at the cut to the BASE spark speed x the victim's
                    // SpeedMultiplier then (at tick start or end: a boost and a cut can share a tick); never Conduction.
                    double speed = p.Spark.Speed;
                    bool spawnedThisTick = p.Spark.TimeCut >= sim.Time - sim.Config.Dt - 1e-9;
                    bool atStart = Math.Abs(speed - baseSpeed * multiplierAtStart[i]) <= 1e-12;
                    bool atEnd = Math.Abs(speed - baseSpeed * p.SpeedMultiplier) <= 1e-12;
                    if (spawnedThisTick && !atStart && !atEnd)
                        Assert.Fail(At + "spark of player " + i + " spawned at speed " + speed + ", expected " + baseSpeed + " x " + p.SpeedMultiplier);
                    if (!traits.Has(TraitId.KillSpeedBoost) && speed != baseSpeed)
                        Assert.Fail(At + "spark of player " + i + " at speed " + speed + " without KillSpeedBoost (base " + baseSpeed + ")");
                    double s = p.Spark.SCut + speed * (sim.Time - p.Spark.TimeCut);
                    if (Math.Abs(p.Spark.S - s) > 1e-9) Assert.Fail(At + "spark of player " + i + " at " + p.Spark.S + ", closed form " + s);
                    SparkChecks++;
                }
            }

            private void CheckCuts(double t0)
            {
                SimConfig c = sim.Config;
                foreach (SimEvent e in sim.LastEvents)
                {
                    if (e.Type != SimEventType.Cut) continue;
                    PlayerState a = sim.Players[e.Other], v = sim.Players[e.Player];
                    double u = (e.Time - t0) / c.Dt;
                    if (u < -1e-9 || u > 1.0 + 1e-9) Assert.Fail(At + "cut time outside the tick: " + e);
                    if (a.Alive && aliveAtStart[e.Other])
                    {
                        Vec2d head = Vec2d.Lerp(a.PrevPos, a.Pos, u);
                        double d = Vec2d.Distance(head, e.Point);
                        if (d > c.ContactRadius + 1e-6) Assert.Fail(At + "cut point " + d + " from the attacker's head > ContactRadius " + c.ContactRadius);
                    }
                    if (v.Alive && !v.Home && v.Spark != null && v.Spark.SCut == e.S && v.Spark.TimeCut == e.Time)
                    {
                        double lt = v.Trail.Length - (1.0 - u) * Vec2d.Distance(v.PrevPos, v.Pos);
                        if (e.S > lt - c.HeadGrace + 1e-6) Assert.Fail(At + "s_cut " + e.S + " inside the HeadGrace zone (L(t) = " + lt + ")");
                        if (Vec2d.Distance(v.Trail.PointAt(e.S), e.Point) > 1e-9) Assert.Fail(At + "cut point is not PointAt(s_cut)");
                    }
                    CutChecks++;
                }
            }

            private void CheckReturnsAfterGrowth()
            {
                if (!grewLastTick) return;
                grewLastTick = false;
                foreach (SimEvent e in sim.LastEvents)
                {
                    if (e.Type != SimEventType.Return) continue;
                    List<int> grown = grownLastTick[e.Player];
                    if (grown.Count == 0) continue;
                    PlayerState p = sim.Players[e.Player];
                    Vec2d dir = (p.Pos - p.PrevPos).Normalized();
                    if (!sim.Grid.TryCellOf(e.Point + dir * 1e-7, out int i, out int j)) continue;
                    int entered = sim.Grid.Index(i, j);
                    if (grown.BinarySearch(entered) >= 0)
                        Assert.Fail(At + "player " + e.Player + " returned into a cell Propagation grew for it at the previous tick");
                    ReturnAfterGrowthChecks++;
                }
            }

            private void CheckPropagation(double t0)
            {
                TraitSpec spec = traits.Get(TraitId.Propagation);
                var grown = new List<int>[n];
                for (int i = 0; i < n; i++) grown[i] = new List<int>();
                IReadOnlyList<SimEvent> events = sim.LastEvents;
                int lastOther = -1, firstGrow = -1, lastGrow = -1, firstRing = int.MaxValue, prevPlayer = -1;
                for (int k = 0; k < events.Count; k++)
                {
                    SimEvent e = events[k];
                    if (e.Type == SimEventType.TerritoryGrew)
                    {
                        if (firstGrow < 0) firstGrow = k;
                        lastGrow = k;
                        if (e.Player <= prevPlayer) Assert.Fail(At + "TerritoryGrew not one per player in player order");
                        prevPlayer = e.Player;
                        grown[e.Player].AddRange(e.Cells);
                    }
                    else if (e.Type == SimEventType.RingSpawned) firstRing = Math.Min(firstRing, k);
                    else lastOther = k;
                }
                if (spec == null)
                {
                    if (firstGrow >= 0) Assert.Fail(At + "TerritoryGrew without Propagation");
                    return;
                }
                if (firstGrow >= 0 && (firstGrow < lastOther || lastGrow > firstRing))
                    Assert.Fail(At + "TerritoryGrew must come after the event-loop events and before RingSpawned\n" + TraitTestKit.Dump(events));

                double interval = spec.P1, now = sim.Time;
                int rings = (int)Math.Round(spec.P2);
                bool crossed = rings > 0 && Math.Floor(now / interval + 1e-9) > Math.Floor(t0 / interval + 1e-9);
                if (!crossed)
                {
                    if (firstGrow >= 0) Assert.Fail(At + "TerritoryGrew outside an interval crossing");
                    return;
                }

                OwnerGrid g = sim.Grid;
                int size = g.Size;
                byte[] work = (byte[])g.Cells.Clone();
                for (int i = 0; i < n; i++)
                {
                    foreach (int c in grown[i])
                    {
                        if (work[c] != sim.Players[i].Id) Assert.Fail(At + "grown cell not owned by its player");
                        if (traits.Has(TraitId.ScorchedEarth) && gridBefore[c] != OwnerGrid.Neutral)
                            Assert.Fail(At + "grown cell was not neutral before the tick (owner " + gridBefore[c] + ")");
                        work[c] = OwnerGrid.Neutral;
                    }
                }

                // Cells under live heads.
                var blocked = new bool[work.Length];
                double r = sim.Config.HeadRadius;
                foreach (PlayerState p in sim.Players)
                {
                    if (!p.Alive) continue;
                    blocked[p.Cell] = true;
                    if (!g.TryCellOf(p.Pos, out int hi, out int hj)) continue;
                    for (int j = Math.Max(0, hj - 6); j <= Math.Min(size - 1, hj + 6); j++)
                    {
                        for (int i = Math.Max(0, hi - 6); i <= Math.Min(size - 1, hi + 6); i++)
                        {
                            if (Vec2d.Distance(g.CellCenter(i, j), p.Pos) <= r) blocked[g.Index(i, j)] = true;
                        }
                    }
                }

                // Each trailing claimant's own trail raster and its 4-neighbours.
                var band = new bool[n][];
                var scratch = new List<int>();
                for (int i = 0; i < n; i++)
                {
                    PlayerState p = sim.Players[i];
                    if (!p.Alive || p.Home || p.Trail.Count == 0) continue;
                    var raster = new CellMask(size);
                    IReadOnlyList<Vec2d> pts = p.Trail.Points;
                    if (pts.Count >= 2) GridRaster.RasterPolyline(g, pts, raster);
                    if (g.TryCellOf(pts[pts.Count - 1], out int ei, out int ej)) raster.Set(g.Index(ei, ej));
                    if (g.TryCellOf(pts[0], out int si, out int sj)) raster.Set(g.Index(si, sj));
                    raster.CopyIndices(scratch);
                    var b = new bool[work.Length];
                    foreach (int c in scratch)
                    {
                        int ci = c % size, cj = c / size;
                        b[c] = true;
                        if (ci + 1 < size) b[c + 1] = true;
                        if (ci > 0) b[c - 1] = true;
                        if (cj + 1 < size) b[c + size] = true;
                        if (cj > 0) b[c - size] = true;
                    }
                    band[i] = b;
                }

                var expected = new List<int>[n];
                for (int i = 0; i < n; i++) expected[i] = new List<int>();
                for (int ring = 0; ring < rings; ring++)
                {
                    var add = new List<KeyValuePair<int, byte>>();
                    for (int c = 0; c < work.Length; c++)
                    {
                        if (work[c] != OwnerGrid.Neutral) continue;
                        int ci = c % size, cj = c / size;
                        byte claim = 0;
                        bool contested = false;
                        if (ci + 1 < size) Claim(work[c + 1], ref claim, ref contested);
                        if (ci > 0) Claim(work[c - 1], ref claim, ref contested);
                        if (cj + 1 < size) Claim(work[c + size], ref claim, ref contested);
                        if (cj > 0) Claim(work[c - size], ref claim, ref contested);
                        if (claim == 0 || contested) continue;
                        if (blocked[c])
                        {
                            HeadSpared++;
                            continue;
                        }
                        if (sim.View.ScorchEndTime(c) > now)
                        {
                            ScorchSpared++;
                            continue;
                        }
                        if (band[claim - 1] != null && band[claim - 1][c])
                        {
                            TrailSpared++;
                            continue;
                        }
                        add.Add(new KeyValuePair<int, byte>(c, claim));
                    }
                    if (add.Count == 0) break;
                    foreach (KeyValuePair<int, byte> kv in add)
                    {
                        work[kv.Key] = kv.Value;
                        expected[kv.Value - 1].Add(kv.Key);
                    }
                }
                for (int i = 0; i < n; i++)
                {
                    expected[i].Sort();
                    if (!SameCells(expected[i].ToArray(), grown[i].ToArray()))
                        Assert.Fail(At + "player " + i + " grew " + grown[i].Count + " cells, the ring oracle expects " + expected[i].Count);
                    GrownCells += grown[i].Count;
                }
                GrowthInstants++;
                grownLastTick = grown;
                grewLastTick = true;
            }

            private void Claim(byte owner, ref byte claim, ref bool contested)
            {
                if (owner == OwnerGrid.Neutral || owner == OwnerGrid.Void || owner > n) return;
                if (claim == 0) claim = owner;
                else if (claim != owner) contested = true;
            }

            private void CheckCoalescence()
            {
                TraitSpec spec = traits.Get(TraitId.Coalescence);
                if (spec == null || traits.Has(TraitId.Propagation)) return;
                SimEvent ret = null;
                foreach (SimEvent e in sim.LastEvents)
                {
                    if (e.Type == SimEventType.Eliminated || e.Type == SimEventType.TerritoryGrew) return;
                    if (e.Type != SimEventType.Return) continue;
                    if (ret != null) return;
                    ret = e;
                }
                if (ret == null || ret.Chased) return;

                OwnerGrid g = sim.Grid;
                int size = g.Size;
                byte id = sim.Players[ret.Player].Id;
                byte[] cells = g.Cells;
                double cellArea = g.CellSize * g.CellSize;
                var seen = new bool[cells.Length];
                var stack = new Stack<int>();
                for (int seed = 0; seed < cells.Length; seed++)
                {
                    if (cells[seed] != OwnerGrid.Neutral || seen[seed]) continue;
                    // Only components next to the returner's land can be its holes.
                    int si = seed % size, sj = seed / size;
                    bool nextToLand = (si + 1 < size && cells[seed + 1] == id) || (si > 0 && cells[seed - 1] == id)
                                      || (sj + 1 < size && cells[seed + size] == id) || (sj > 0 && cells[seed - size] == id);
                    if (!nextToLand) continue;
                    int count = 0;
                    bool enclosed = true, unscorched = false;
                    seen[seed] = true;
                    stack.Push(seed);
                    while (stack.Count > 0)
                    {
                        int c = stack.Pop();
                        count++;
                        if (!(sim.View.ScorchEndTime(c) > ret.Time)) unscorched = true;
                        int ci = c % size, cj = c / size;
                        for (int d = 0; d < 4; d++)
                        {
                            int ni = ci + (d == 0 ? 1 : d == 1 ? -1 : 0), nj = cj + (d == 2 ? 1 : d == 3 ? -1 : 0);
                            if (ni < 0 || nj < 0 || ni >= size || nj >= size)
                            {
                                enclosed = false;
                                continue;
                            }
                            int nc = nj * size + ni;
                            byte o = cells[nc];
                            if (o == id) continue;
                            if (o != OwnerGrid.Neutral)
                            {
                                enclosed = false;
                                continue;
                            }
                            if (!seen[nc])
                            {
                                seen[nc] = true;
                                stack.Push(nc);
                            }
                        }
                    }
                    if (enclosed && unscorched && count * cellArea < spec.P1)
                        Assert.Fail(At + "player " + ret.Player + " returned unchased but still encloses a neutral hole of " + count
                                    + " cells (" + count * cellArea + " u^2 < " + spec.P1 + ")");
                }
                HoleChecks++;
            }

            private static double Wrap(double a)
            {
                while (a > Math.PI) a -= 2.0 * Math.PI;
                while (a < -Math.PI) a += 2.0 * Math.PI;
                return a;
            }
        }
    }
}
