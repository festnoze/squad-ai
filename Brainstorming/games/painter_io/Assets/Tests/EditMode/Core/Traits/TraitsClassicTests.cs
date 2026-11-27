// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md sections 1 and 6: with every trait off, the simulation is
// bit-identical to the one before traits existed (classic equality). The whole existing Core suite runs with the default
// SimConfig, whose Traits is RuleTraits.Classic, so it is the main classic-equality test; these tests pin the hashes.
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    public class TraitsClassicTests
    {
        /// <summary>
        /// Rolling StateHash (every 30 ticks and at the end) of full bot rounds, recorded with the Core of Gate C (before
        /// any trait code existed). Columns: seed, tick rate, lasso spawns, human index, hash.
        /// </summary>
        private static readonly object[] Baselines =
        {
            new object[] { 1UL, 60, true, -1, 0x8CB763231AC73608UL },
            new object[] { 2UL, 60, true, -1, 0x2D4E3923E8FC07DCUL },
            new object[] { 3UL, 60, false, -1, 0x20109E29FF4E9FECUL },
            new object[] { 4UL, 60, true, 0, 0x99AEBACD711C7E8FUL },
            new object[] { 5UL, 30, true, -1, 0xB7018354A8617813UL },
            new object[] { 6UL, 144, true, -1, 0x22707E7EDD9ED472UL },
            new object[] { 7UL, 60, false, 0, 0xE109EA10426D1F29UL },
        };

        private static ulong Rolling(ulong seed, int rate, bool lasso, int human, RuleTraits traits)
        {
            BotStyle[] styles = TraitTestKit.Lineup;
            var controllers = new IController[4];
            for (int i = 0; i < 4; i++)
                controllers[i] = new BotController(BotPersonality.Preset(styles[i]), seed * 7919UL + (ulong)i * 104729UL + 17UL);
            var config = new SimConfig { Seed = seed, TickRate = rate, LassoEnabled = lasso };
            if (traits != null) config.Traits = traits;
            var sim = new Simulation(config, controllers, new SimSetup { HumanIndex = human });
            return TraitTestKit.RollingRoundHash(sim, 30, false);
        }

        [TestCaseSource(nameof(Baselines))]
        public void TraitsClassic_BotRoundHashesEqualThePreTraitBaseline(ulong seed, int rate, bool lasso, int human, ulong expected)
        {
#if UNITY_5_3_OR_NEWER
            // Unity (Editor Mono): the two first rows only, to keep the EditMode run short; dotnet checks all seven.
            if (seed > 2UL) return;
#endif
            Assert.AreEqual(expected.ToString("X16"), Rolling(seed, rate, lasso, human, null).ToString("X16"),
                            "default SimConfig (Traits = Classic) must reproduce the pre-trait hash");
            Assert.AreEqual(expected.ToString("X16"), Rolling(seed, rate, lasso, human, RuleTraits.Parse("classic")).ToString("X16"),
                            "RuleTraits.Parse(\"classic\")");
        }

        [Test]
        public void TraitsClassic_EveryTraitDisabledIsClassic()
        {
            var specs = new List<TraitSpec>();
            foreach (TraitId id in TraitDefaults.All) specs.Add(new TraitSpec(id, double.NaN, double.NaN, false));
            var allOff = new RuleTraits(specs);
            Assert.AreEqual(TraitDefaults.All.Count, allOff.Specs.Count, "disabled specs are kept (11 traits since wave D-2)");
            Assert.IsTrue(allOff.IsClassic);
            Assert.AreEqual("", allOff.ToKey());
            Assert.AreEqual(0x8CB763231AC73608UL.ToString("X16"), Rolling(1UL, 60, true, -1, allOff).ToString("X16"),
                            "a set whose traits are all disabled is bit-identical to classic");
        }

        [Test]
        public void TraitsClassic_DefaultConfigIsClassicAndTheRoundConfigIsUntouched()
        {
            var config = new SimConfig();
            Assert.AreSame(RuleTraits.Classic, config.Traits);
            Assert.AreEqual(1.0, config.ContactScale);
            Assert.AreEqual(config.HeadRadius + config.TrailHalfWidth, config.ContactRadius, "x 1.0 is exact");

            var sim = new Simulation(config, new IController[] { null, null });
            Assert.AreEqual(0, TraitRegistry.CreateBehaviours(sim.Config.Traits).Count, "no behaviour trait in a classic round");
            Assert.IsTrue(sim.View.Traits.IsClassic);
            Assert.AreEqual(Tuning.TurnRateDeg, sim.Config.TurnRateDeg);
            Assert.AreEqual(Tuning.SparkSpeedFactor, sim.Config.SparkSpeedFactor);
            Assert.AreEqual(Tuning.LassoFirstSpawn, sim.Config.LassoFirstSpawn);
            Assert.AreEqual(Tuning.LassoRespawn, sim.Config.LassoRespawn);
            Assert.AreEqual(1.0, sim.Config.ContactScale);
            Assert.AreEqual(Tuning.LassoFirstSpawn, sim.NextRingTime);
            Assert.AreEqual(Tuning.PawnSpeed, sim.View.HomeSpeed, "no Conduction: home speed is PawnSpeed");
            Assert.IsFalse(sim.View.IsScorched(sim.Players[0].Cell));
            Assert.AreEqual(double.NegativeInfinity, sim.View.ScorchEndTime(sim.Players[0].Cell));
        }

        [Test]
        public void TraitsClassic_AnEnabledTraitSaltsTheHashEvenWhenTheStateIsTheSame()
        {
            // Inertia at the classic turn rate changes nothing in the evolution, only the hash salt (the trait key).
            Simulation classic = TraitTestKit.BotRound(3UL, RuleTraits.Classic, true);
            Simulation salted = TraitTestKit.BotRound(3UL, TraitTestKit.One(TraitId.Inertia, Tuning.TurnRateDeg), true);
            Assert.AreNotEqual(classic.StateHash(), salted.StateHash(), "an enabled trait salts the hash");
            for (int k = 0; k < 600; k++)
            {
                classic.Step();
                salted.Step();
            }
            for (int i = 0; i < 4; i++)
            {
                Assert.AreEqual(classic.Players[i].Pos, salted.Players[i].Pos, "same evolution, player " + i);
                Assert.AreEqual(classic.Players[i].OwnedCells(classic.Grid), salted.Players[i].OwnedCells(salted.Grid));
            }
            Assert.AreNotEqual(classic.StateHash(), salted.StateHash());
        }
    }
}
