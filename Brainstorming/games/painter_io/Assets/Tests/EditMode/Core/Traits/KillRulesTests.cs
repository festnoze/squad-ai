// Owned by kill-core (wave D-2). docs/BIOME_TRAITS.md section 7.1: the core rules made explicit by the kill rewards
// (PlayerState.SpeedMultiplier, Spark.Speed fixed at the cut, ExitWasCut, the exact shield end), their neutrality in classic
// rounds (bit-identical simulation), the catalogue / key / event additions, and the v1.1 biome default sets in bot rounds
// (invariants every tick, EventCapHits == 0, determinism, the rewards actually happen).
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class KillRulesTests
    {
#if UNITY_5_3_OR_NEWER
        private const double BotRoundSeconds = 30.0;
        private const int BotSeeds = 1;
#else
        private const double BotRoundSeconds = 90.0;
        private const int BotSeeds = 6;
#endif

        // ------------------------------------------------------------------------------------------------------------
        // Catalogue, keys, events

        [Test]
        public void KillRules_CatalogueKeysAndValidation()
        {
            Assert.AreEqual(9, (int)TraitId.KillInheritance);
            Assert.AreEqual(10, (int)TraitId.KillSpeedBoost);
            Assert.AreEqual(11, (int)TraitId.KillShield);
            Assert.AreEqual(1.0, TraitDefaults.P1(TraitId.KillInheritance));
            Assert.AreEqual(0.10, TraitDefaults.P1(TraitId.KillSpeedBoost));
            Assert.AreEqual(0.30, TraitDefaults.P2(TraitId.KillSpeedBoost));
            Assert.AreEqual(3.0, TraitDefaults.P1(TraitId.KillShield));
            Assert.AreEqual("Cap", TraitDefaults.ParameterName(TraitId.KillSpeedBoost, 2));
            foreach (TraitId id in new[] { TraitId.KillInheritance, TraitId.KillSpeedBoost, TraitId.KillShield })
            {
                Assert.AreEqual(TraitKind.Behaviour, TraitDefaults.KindOf(id));
                Assert.IsTrue(TraitRegistry.Create(id) is IKillTrait, id + " is a kill trait");
            }
            Assert.IsTrue(TraitRegistry.Create(TraitId.KillSpeedBoost) is ISpeedTrait, "KillSpeedBoost raises the reachable speed");

            Assert.AreEqual(TraitTestKit.LiquidV11Key, TraitTestKit.LiquidV11.ToKey());
            Assert.AreEqual(TraitTestKit.FireV11Key, TraitTestKit.FireV11.ToKey());
            Assert.AreEqual(TraitTestKit.ElectricV11Key, TraitTestKit.ElectricV11.ToKey());
            foreach (string key in new[] { TraitTestKit.LiquidV11Key, TraitTestKit.FireV11Key, TraitTestKit.ElectricV11Key })
                Assert.AreEqual(key, RuleTraits.Parse(key).ToKey(), "round trip");
            Assert.AreEqual("KillSpeedBoost(0.2,0.5)", RuleTraits.Parse("killspeedboost(0.2, 0.5)").ToKey());
            Assert.AreEqual("KillInheritance(1,0);KillShield(3,0)", RuleTraits.Parse("11;9").ToKey(), "numeric ids, canonical order");
        }

        [TestCase("KillInheritance(1.5)")]
        [TestCase("KillInheritance(-0.1)")]
        [TestCase("KillSpeedBoost(-0.1)")]
        [TestCase("KillSpeedBoost(0.1,-0.1)")]
        [TestCase("KillShield(-1)")]
        [TestCase("12")]
        public void KillRules_ParseRejectsInvalidKillParameters(string key)
        {
            Assert.Throws<FormatException>(() => RuleTraits.Parse(key));
        }

        [Test]
        public void KillRules_NewEventTypesAreAppendedAtTheEnd()
        {
            Assert.AreEqual(10, (int)SimEventType.RoundEnded, "the contract 5.5 values are unchanged");
            Assert.AreEqual(11, (int)SimEventType.TerritoryGrew);
            Assert.AreEqual(12, (int)SimEventType.TerritoryInherited);
            Assert.AreEqual(13, (int)SimEventType.SpeedBoosted);
            Assert.AreEqual(14, (int)SimEventType.ShieldStarted);
            Assert.AreEqual(15, (int)SimEventType.ShieldEnded);
            Assert.AreEqual(16, (int)SimEventType.TerritorySevered, "rule v1.5 (contract 29), appended after the kill events");
            Assert.AreEqual(17, (int)SimEventType.InheritanceBridged, "rule v1.6 (contract 30), appended after TerritorySevered");
            Assert.AreEqual(18, Enum.GetValues(typeof(SimEventType)).Length);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Classic: every new rule is neutral

        private static Simulation ClassicRound(ulong seed, int rate, bool lasso, RuleTraits traits, bool follows)
        {
            var controllers = new IController[4];
            for (int i = 0; i < 4; i++)
                controllers[i] = new BotController(BotPersonality.Preset(TraitTestKit.Lineup[i]), BotTests.BotSeed(seed, i));
            var config = new SimConfig { Seed = seed, TickRate = rate, LassoEnabled = lasso, SparkFollowsVictimSpeed = follows };
            if (traits != null) config.Traits = traits;
            return new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
        }

        [Test]
        public void KillRules_ClassicRoundsReproduceThePreTraitHashWhateverSparkFollowsVictimSpeed()
        {
            // TraitsClassicTests pins seven rows with the default config; here the 7.1 switch must not matter either.
            // Rule v1.5 (contract 29): with the default SeveredTerritory (Neutral) the seed 1 round is C042710F17995DCB (it
            // was the pre-trait 8CB763231AC73608, still the value with SeveredTerritory = Off, pinned in TraitsClassicTests).
            // Rule v1.8 (contract 32): C042710F17995DCB is now the value with SingleDomain = Off; the default is
            // TraitsClassicTests.ClassicSeed1V18.
            Assert.AreEqual(TraitsClassicTests.ClassicSeed1V18.ToString("X16"),
                            TraitTestKit.RollingRoundHash(ClassicRound(1UL, 60, true, null, false), 30, false).ToString("X16"),
                            "SparkFollowsVictimSpeed = false, classic");
            Assert.AreEqual(TraitsClassicTests.ClassicSeed1V18.ToString("X16"),
                            TraitTestKit.RollingRoundHash(ClassicRound(1UL, 60, true, null, true), 30, false).ToString("X16"),
                            "SparkFollowsVictimSpeed = true (default), classic");
        }

        private static IEnumerable<object[]> NeutralCases()
        {
#if UNITY_5_3_OR_NEWER
            yield return new object[] { 60, 21UL };
#else
            foreach (int rate in CrossRates)
            {
                yield return new object[] { rate, 21UL };
                yield return new object[] { rate, 22UL };
            }
#endif
        }

        /// <summary>
        /// The three kill traits enabled at parameters that change nothing (Share 0, PerKill 0, Duration 0) evolve exactly
        /// like the classic round: kills happen, the hook plumbing runs, and nothing else changes (only the hash salt).
        /// </summary>
        [TestCaseSource(nameof(NeutralCases))]
        public void KillRules_KillTraitsAtNeutralParametersEvolveExactlyLikeClassic(int rate, ulong seed)
        {
            RuleTraits neutral = RuleTraits.Parse("KillInheritance(0);KillSpeedBoost(0,0);KillShield(0)");
            Simulation classic = ClassicRound(seed, rate, true, RuleTraits.Classic, true);
            Simulation traited = ClassicRound(seed, rate, true, neutral, true);
            var kills = new EventLog(classic);
            int ticks = TraitsAuditTests.AssertSameEvolution("neutral kill traits " + rate + " Hz seed " + seed, classic, traited, false);
            Assert.That(ticks, Is.GreaterThan(100));
            TestContext.WriteLine(rate + " Hz seed " + seed + ": " + kills.Count(SimEventType.SparkCaught) + " kills in the compared rounds");
        }

        [Test]
        public void KillRules_ClassicSparksRunAtExactlyTheConfiguredSparkSpeed()
        {
            // A real cut (R11, step c) and a forced one: Spark.Speed is bit-identical to SimConfig.SparkSpeed.
            var b = new SimBuilder(60);
            b.AddRect(-6, -3, 0, 3, V(-1 + H, H), East, new ConstantHeadingController(East));
            b.AddRect(2, 12, 6, 16, V(4 + H, H + 0.63 + 12.0), South, new ConstantHeadingController(South));
            b.AddIdle(IdleCorners[2]);
            Simulation sim = b.Build();
            var log = new EventLog(sim);
            RunUntilTime(sim, 2.05);
            Assert.AreEqual(1, log.Count(SimEventType.Cut, 0));
            PlayerState v = sim.Players[0];
            Assert.AreEqual(sim.Config.SparkSpeed, v.Spark.Speed, "real cut");
            Assert.IsTrue(v.ExitWasCut, "a spark sets ExitWasCut");
            Assert.AreEqual(1.0, v.SpeedMultiplier);
            Assert.IsFalse(v.Shielded);

            Simulation forced = KillShieldlessChase(60);
            Assert.AreEqual(forced.Config.SparkSpeed, forced.Players[0].Spark.Speed, "DebugForceCut");
            Assert.AreEqual(forced.Config.SparkSpeed, forced.Config.SparkSpeedOf(1.0), "SparkSpeedOf(1) is exact");
        }

        private static Simulation KillShieldlessChase(int rate)
        {
            var sb = new SimBuilder(rate);
            sb.AddRect(-28, 20, -24, 24, V(-26 + H, 22 + H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[2]);
            Simulation sim = sb.Build();
            KillTestKit.ForceChase(sim, 0, 1, V(-10, H), 10.0, 1.013);
            return sim;
        }

        // ------------------------------------------------------------------------------------------------------------
        // ExitWasCut (v1.4 restated as a flag)

        /// <summary>
        /// Player 0 owns [-6, 0] x [-3, 3] and is teleported to a trail (3 + d, H) -> (d, H) heading West, d >= 0: its head
        /// re-enters its land at x = 0 at t = d / 6 (d = 0: at u = 0 of the first tick). Player 1 idles.
        /// </summary>
        private static Simulation Homecoming(int rate, double d)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-6, -3, 0, 3, V(-1 + H, H), West, new ConstantHeadingController(West));
            b.AddIdle(IdleCorners[2]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(3 + d, H), V(d, H) });
            return sim;
        }

        [Test]
        public void KillRules_ExitWasCutIsSetByTheSparkAndClearedAtTheReturn()
        {
            Simulation sim = Homecoming(60, 0.5);
            Assert.IsFalse(sim.Players[0].ExitWasCut);
            sim.DebugForceCut(0, 0.5, 1);
            Assert.IsTrue(sim.Players[0].ExitWasCut, "set when the spark spawns");
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.2);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.IsTrue(ret.Chased);
            Assert.AreEqual(0, ret.Cells.Length);
            Assert.IsFalse(sim.Players[0].ExitWasCut, "cleared at the return");
            Assert.IsNull(sim.Players[0].Spark);

            // DebugSetTrail starts a new exit: the flag goes with the spark.
            Simulation again = Homecoming(60, 0.5);
            again.DebugForceCut(0, 0.5, 1);
            again.DebugSetTrail(0, new[] { V(5 + H, 5 + H), V(6 + H, 5 + H) });
            Assert.IsFalse(again.Players[0].ExitWasCut);
        }

        [TestCase(30)]
        [TestCase(60)]
        [TestCase(144)]
        public void KillRules_TheR14CrossTickCancellationClearsExitWasCutAndTheReturnIsUnchased(int rate)
        {
            // The head sits on its land's edge (x = 0) moving West: the return is at u = 0 of the first tick, the same
            // instant as the forced cut. R14 (24.1): the spark spawned less than eps before the return is cancelled, the
            // CutsMade credit is taken back, and ExitWasCut is cleared with it: the return is unchased.
            Simulation sim = Homecoming(rate, 0.0);
            sim.DebugForceCut(0, 1.0, 1);
            Assert.IsTrue(sim.Players[0].ExitWasCut);
            Assert.AreEqual(1, sim.Players[1].CutsMade);
            var log = new EventLog(sim);
            sim.Step();
            AssertInvariants(sim);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.AreEqual(0.0, ret.Time, 1e-12);
            Assert.IsFalse(ret.Chased, "unchased: the flag was cleared with the spark");
            Assert.IsFalse(sim.Players[0].ExitWasCut);
            Assert.AreEqual(0, sim.Players[1].CutsMade, "credit taken back");
        }

        // ------------------------------------------------------------------------------------------------------------
        // The v1.1 biome default sets in bot rounds

        private static IEnumerable<object[]> V11Sets()
        {
            yield return new object[] { "Liquide v1.1", TraitTestKit.LiquidV11Key, (int)TraitId.KillShield };
            yield return new object[] { "Feu v1.1", TraitTestKit.FireV11Key, (int)TraitId.KillInheritance };
            yield return new object[] { "Electricite v1.1", TraitTestKit.ElectricV11Key, (int)TraitId.KillSpeedBoost };
        }

        /// <summary>
        /// Each v1.1 default set (section 3 + section 7) in full bot rounds, lasso off and on: the trait invariants and the
        /// kill invariants every tick (EventCapHits == 0 included), a twin round with the same hash, and its kill reward
        /// actually firing over the seeds (Feu: TerritoryInherited, Electricite: SpeedBoosted, Liquide: ShieldStarted).
        /// </summary>
        [TestCaseSource(nameof(V11Sets))]
        public void KillRules_V11BiomeSetsKeepEveryInvariantAndTheirRewardFires(string name, string key, int rewardTrait)
        {
            RuleTraits traits = RuleTraits.Parse(key);
            SimEventType reward = rewardTrait == (int)TraitId.KillInheritance ? SimEventType.TerritoryInherited
                : rewardTrait == (int)TraitId.KillSpeedBoost ? SimEventType.SpeedBoosted : SimEventType.ShieldStarted;
            int rewards = 0, kills = 0, extinguished = 0;
            for (int k = 0; k < BotSeeds; k++)
            {
                bool lasso = k % 2 == 1;
                ulong seed = 900UL + (ulong)k;
                Simulation sim = TraitTestKit.BotRound(seed, traits, lasso, 60, k % 3 == 0 ? 0 : -1, BotRoundSeconds);
                Simulation twin = TraitTestKit.BotRound(seed, traits, lasso, 60, k % 3 == 0 ? 0 : -1, BotRoundSeconds);
                sim.EventRaised += e =>
                {
                    if (e.Type == reward) rewards++;
                    if (e.Type == SimEventType.SparkCaught) kills++;
                    if (e.Type == SimEventType.ShieldStarted && e.Chased) extinguished++;
                };
                int ticks = 0;
                while (!sim.Ended)
                {
                    sim.Step();
                    twin.Step();
                    TraitTestKit.AssertTraitInvariants(sim);
                    if (++ticks % 15 == 0 || sim.Ended) Assert.AreEqual(sim.StateHash(), twin.StateHash(), name + ": same seed, same hash at tick " + sim.Tick);
                }
                Assert.IsTrue(twin.Ended);
                Assert.AreEqual(0, sim.EventCapHits, name + ": EventCapHits");
            }
            TestContext.WriteLine(name + ": " + BotSeeds + " rounds, " + kills + " kills, " + rewards + " " + reward + " events, "
                                  + extinguished + " sparks extinguished by a shield");
#if !UNITY_5_3_OR_NEWER
            Assert.That(rewards, Is.GreaterThan(0), name + ": the kill reward fired in bot rounds");
#endif
        }

        [Test]
        public void KillRules_KillTraitStateIsHashedOnlyWithKillTraits()
        {
            // The D-1 sets keep their hashes: no kill trait, no kill state in the hash. With a kill trait the multiplier is
            // part of the hash (a changed multiplier changes the hash).
            Simulation fire = TraitTestKit.BotRound(5UL, TraitTestKit.Fire, false);
            Simulation fireTwin = TraitTestKit.BotRound(5UL, TraitTestKit.Fire, false);
            fireTwin.Players[2].SpeedMultiplier = 1.1;   // never happens without KillSpeedBoost; proves the hash gate only
            fireTwin.Players[2].ShieldEnd = 3.0;
            Assert.AreEqual(fire.StateHash(), fireTwin.StateHash(), "no kill trait: the kill state is not hashed (D-1 hashes kept)");

            Simulation boost = TraitTestKit.BotRound(5UL, TraitTestKit.One(TraitId.KillSpeedBoost), false);
            ulong before = boost.StateHash();
            boost.Players[2].SpeedMultiplier = 1.1;
            Assert.AreNotEqual(before, boost.StateHash(), "the multiplier is hashed with a kill trait");
            boost.Players[2].SpeedMultiplier = 1.0;
            boost.Players[2].ShieldEnd = 3.0;
            Assert.AreNotEqual(before, boost.StateHash(), "the shield is hashed with a kill trait");
        }
    }
}
