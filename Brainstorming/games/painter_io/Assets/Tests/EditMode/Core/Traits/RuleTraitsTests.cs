// Owned by traits-core (wave D-1), updated by kill-core (wave D-2: 11 traits). docs/BIOME_TRAITS.md section 4: RuleTraits
// (key round trip, duplicates, disabled specs), TraitSpec, TraitDefaults and TraitRegistry (config traits on the cloned
// config, behaviours in id order).
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    public class RuleTraitsTests
    {
        [Test]
        public void RuleTraits_BiomeSetsRoundTripThroughTheirKey()
        {
            Assert.AreEqual("Inertia(420,0);Coalescence(2,0)", TraitTestKit.Liquid.ToKey());
            Assert.AreEqual("SparkSpeed(2.1,0);Propagation(4,1);ScorchedEarth(15,0)", TraitTestKit.Fire.ToKey());
            Assert.AreEqual("SparkSpeed(1.5,0);Conduction(1.3,0);ArcReach(1.4,0);RingInterval(10,0)", TraitTestKit.Electric.ToKey());
            foreach (RuleTraits set in new[] { TraitTestKit.Liquid, TraitTestKit.Fire, TraitTestKit.Electric, RuleTraits.Classic })
            {
                string key = set.ToKey();
                RuleTraits back = RuleTraits.Parse(key);
                Assert.AreEqual(key, back.ToKey(), "round trip of \"" + key + "\"");
                Assert.AreEqual(set, back, "value equality after the round trip of \"" + key + "\"");
                foreach (TraitId id in TraitDefaults.All) Assert.AreEqual(set.Has(id), back.Has(id), key + " Has(" + id + ")");
            }
        }

        [Test]
        public void RuleTraits_EverySingleTraitAndOddParametersRoundTrip()
        {
            var rng = new Rng(42);
            foreach (TraitId id in TraitDefaults.All)
            {
                RuleTraits one = TraitTestKit.One(id);
                Assert.AreEqual(one.ToKey(), RuleTraits.Parse(one.ToKey()).ToKey(), id.ToString());
                // Awkward doubles survive the round trip exactly ("R" format).
                double p1 = id == TraitId.SparkSpeed ? 1.0 + rng.NextDouble() + 1e-9
                    : id == TraitId.KillInheritance ? rng.NextDouble() * 0.999 + 1e-9   // Share in [0, 1] (wave D-2)
                    : rng.NextDouble() * 50.0 + 1e-9;
                double p2 = id == TraitId.Propagation ? 3.0 : rng.NextDouble() / 3.0;
                var odd = new RuleTraits(new[] { new TraitSpec(id, p1, p2) });
                RuleTraits back = RuleTraits.Parse(odd.ToKey());
                Assert.AreEqual(p1, back.Get(id).P1, id + " P1 exact");
                Assert.AreEqual(p2, back.Get(id).P2, id + " P2 exact");
            }
        }

        [Test]
        public void RuleTraits_ParseAcceptsClassicNamesNumbersBareIdsAndOneParameter()
        {
            Assert.AreSame(RuleTraits.Classic, RuleTraits.Parse(null));
            Assert.AreSame(RuleTraits.Classic, RuleTraits.Parse(""));
            Assert.AreSame(RuleTraits.Classic, RuleTraits.Parse("  classic "));
            Assert.AreSame(RuleTraits.Classic, RuleTraits.Parse("CLASSIC"));
            RuleTraits t = RuleTraits.Parse(" propagation ; sparkspeed(1.5) ;6(1.2,0);; ");
            Assert.AreEqual("SparkSpeed(1.5,0);Propagation(4,1);Conduction(1.2,0)", t.ToKey());
            Assert.AreEqual(TraitDefaults.PropagationInterval, t.Get(TraitId.Propagation).P1);
            Assert.AreEqual(TraitDefaults.PropagationRings, t.Get(TraitId.Propagation).P2);
        }

        [TestCase("Gravity(1,0)")]
        [TestCase("Inertia(abc)")]
        [TestCase("Inertia(1,2,3)")]
        [TestCase("Inertia(420")]
        [TestCase("SparkSpeed(1.0)")]
        [TestCase("Propagation(0,1)")]
        [TestCase("Propagation(4,-1)")]
        [TestCase("Conduction(0)")]
        [TestCase("ArcReach(-1)")]
        [TestCase("99")]
        public void RuleTraits_ParseRejectsUnknownIdsBadNumbersAndInvalidParameters(string key)
        {
            Assert.Throws<FormatException>(() => RuleTraits.Parse(key));
        }

        [Test]
        public void RuleTraits_LastSpecOfAnIdWinsAndDisabledSpecsAreKeptButInert()
        {
            var t = new RuleTraits(new[]
            {
                new TraitSpec(TraitId.RingInterval, 7.0),
                new TraitSpec(TraitId.Inertia, 300.0),
                new TraitSpec(TraitId.Inertia, 400.0),
                new TraitSpec(TraitId.Coalescence, 2.0),
                new TraitSpec(TraitId.Coalescence, 2.0, double.NaN, false),
            });
            Assert.AreEqual(3, t.Specs.Count, "one spec per id");
            Assert.AreEqual(TraitId.Inertia, t.Specs[0].Id, "ascending id order");
            Assert.AreEqual(TraitId.Coalescence, t.Specs[1].Id);
            Assert.AreEqual(TraitId.RingInterval, t.Specs[2].Id);
            Assert.AreEqual(400.0, t.Get(TraitId.Inertia).P1, "the last spec of an id wins");
            Assert.IsFalse(t.Has(TraitId.Coalescence), "the last Coalescence spec is disabled");
            Assert.IsNull(t.Get(TraitId.Coalescence));
            Assert.IsFalse(t.Specs[1].Enabled, "disabled spec kept");
            Assert.AreEqual("Inertia(400,0);RingInterval(7,0)", t.ToKey(), "key lists enabled traits only");
            Assert.AreEqual(2, t.EnabledCount);
            Assert.IsFalse(t.IsClassic);
            // A disabled spec may hold invalid parameters (it is inert); an enabled one may not.
            var inert = new RuleTraits(new[] { new TraitSpec(TraitId.SparkSpeed, 0.5, double.NaN, false) });
            Assert.IsTrue(inert.IsClassic);
            Assert.Throws<ArgumentException>(() => new RuleTraits(new[] { new TraitSpec(TraitId.SparkSpeed, 0.5) }));
            Assert.Throws<ArgumentException>(() => new RuleTraits(new TraitSpec[] { null }));
            Assert.Throws<ArgumentException>(() => new RuleTraits(new[] { new TraitSpec { Id = (TraitId)42 } }));
        }

        [Test]
        public void RuleTraits_NaNParametersTakeTheDefaultsAndSpecsAreCopied()
        {
            var given = new TraitSpec { Id = TraitId.Propagation, P1 = 2.0 };   // P2 left at NaN
            var t = new RuleTraits(new[] { given });
            Assert.AreEqual(2.0, t.Get(TraitId.Propagation).P1);
            Assert.AreEqual(TraitDefaults.PropagationRings, t.Get(TraitId.Propagation).P2);
            given.P1 = 99.0;
            given.Enabled = false;
            Assert.AreEqual(2.0, t.Get(TraitId.Propagation).P1, "the set keeps its own copy");
            Assert.IsTrue(t.Has(TraitId.Propagation));

            RuleTraits w = t.With(new TraitSpec(TraitId.Propagation, 3.0, 2.0, false));
            Assert.IsFalse(w.Has(TraitId.Propagation), "With replaces the spec of its id");
            Assert.IsTrue(t.Has(TraitId.Propagation), "the original set is unchanged");
        }

        [Test]
        public void TraitDefaults_CatalogueMatchesSection2()
        {
            Assert.AreEqual(new[] { TraitId.Inertia, TraitId.Coalescence, TraitId.SparkSpeed, TraitId.Propagation, TraitId.ScorchedEarth,
                                    TraitId.Conduction, TraitId.ArcReach, TraitId.RingInterval,
                                    TraitId.KillInheritance, TraitId.KillSpeedBoost, TraitId.KillShield }, TraitDefaults.All,
                            "section 2 catalogue + the section 7 kill rewards (wave D-2)");
            Assert.AreEqual(420.0, TraitDefaults.P1(TraitId.Inertia));
            Assert.AreEqual(2.0, TraitDefaults.P1(TraitId.Coalescence));
            Assert.AreEqual(2.1, TraitDefaults.P1(TraitId.SparkSpeed));
            Assert.AreEqual(4.0, TraitDefaults.P1(TraitId.Propagation));
            Assert.AreEqual(1.0, TraitDefaults.P2(TraitId.Propagation));
            Assert.AreEqual(15.0, TraitDefaults.P1(TraitId.ScorchedEarth));
            Assert.AreEqual(1.30, TraitDefaults.P1(TraitId.Conduction));
            Assert.AreEqual(1.40, TraitDefaults.P1(TraitId.ArcReach));
            Assert.AreEqual(10.0, TraitDefaults.P1(TraitId.RingInterval));
            var config = new[] { TraitId.Inertia, TraitId.SparkSpeed, TraitId.ArcReach, TraitId.RingInterval };
            foreach (TraitId id in TraitDefaults.All)
            {
                bool isConfig = Array.IndexOf(config, id) >= 0;
                Assert.AreEqual(isConfig ? TraitKind.Config : TraitKind.Behaviour, TraitDefaults.KindOf(id), id.ToString());
                Assert.AreEqual(isConfig, TraitRegistry.Create(id) == null, id + ": behaviour traits have an ISimTrait");
                if (!isConfig) Assert.AreEqual(id, TraitRegistry.Create(id).Id);
                Assert.IsNotNull(TraitDefaults.ParameterName(id, 1));
            }
        }

        [Test]
        public void TraitRegistry_ConfigTraitsRewriteOnlyTheirFieldsOfTheRoundsClonedConfig()
        {
            var all = new List<TraitSpec>();
            foreach (TraitId id in TraitDefaults.All) all.Add(new TraitSpec(id));
            var traits = new RuleTraits(all);
            var caller = new SimConfig { Traits = traits, LassoEnabled = true };
            var sim = new Simulation(caller, new IController[] { null, null });
            SimConfig c = sim.Config;
            Assert.AreEqual(420.0, c.TurnRateDeg, "Inertia");
            Assert.AreEqual(2.1, c.SparkSpeedFactor, "SparkSpeed");
            Assert.AreEqual(1.4, c.ContactScale, "ArcReach");
            Assert.AreEqual((Tuning.HeadRadius + Tuning.TrailHalfWidth) * 1.4, c.ContactRadius, 1e-15, "ArcReach contact radius");
            Assert.AreEqual(10.0, c.LassoFirstSpawn, "RingInterval first spawn");
            Assert.AreEqual(10.0, c.LassoRespawn, "RingInterval respawn");
            Assert.AreEqual(10.0, sim.NextRingTime, "the ring clock starts from the trait value");
            Assert.AreEqual(Tuning.PawnSpeed, c.PawnSpeed, "base pawn speed untouched");
            Assert.AreEqual(Tuning.HeadGrace, c.HeadGrace);
            Assert.AreEqual(Tuning.PawnSpeed * 2.1, c.SparkSpeed, 1e-12, "spark speed on the BASE pawn speed");
            // The caller's object keeps its values (the Simulation works on a clone).
            Assert.AreEqual(Tuning.TurnRateDeg, caller.TurnRateDeg);
            Assert.AreEqual(Tuning.SparkSpeedFactor, caller.SparkSpeedFactor);
            Assert.AreEqual(1.0, caller.ContactScale);
            Assert.AreEqual(Tuning.LassoFirstSpawn, caller.LassoFirstSpawn);
            Assert.AreEqual(traits.ToKey(), sim.View.Traits.ToKey());
            Assert.AreNotSame(traits, sim.View.Traits, "SimConfig.Clone deep-copies the traits");

            List<ISimTrait> behaviours = TraitRegistry.CreateBehaviours(traits);
            Assert.AreEqual(7, behaviours.Count, "4 section 2 behaviours + the 3 kill rewards (wave D-2)");
            Assert.AreEqual(TraitId.Coalescence, behaviours[0].Id, "TraitId order");
            Assert.AreEqual(TraitId.Propagation, behaviours[1].Id);
            Assert.AreEqual(TraitId.ScorchedEarth, behaviours[2].Id);
            Assert.AreEqual(TraitId.Conduction, behaviours[3].Id);
            Assert.AreEqual(TraitId.KillInheritance, behaviours[4].Id);
            Assert.AreEqual(TraitId.KillSpeedBoost, behaviours[5].Id);
            Assert.AreEqual(TraitId.KillShield, behaviours[6].Id);
            Assert.AreEqual(0, TraitRegistry.CreateBehaviours(RuleTraits.Classic).Count);
            Assert.AreEqual(0, TraitRegistry.CreateBehaviours(null).Count);
        }

        [Test]
        public void SimConfig_CloneDeepCopiesTheTraitsAndKeepsValueEquality()
        {
            var cfg = new SimConfig { Traits = TraitTestKit.Fire, ContactScale = 1.25 };
            SimConfig copy = cfg.Clone();
            Assert.AreNotSame(cfg.Traits, copy.Traits);
            Assert.AreEqual(cfg.Traits, copy.Traits);
            Assert.AreEqual(1.25, copy.ContactScale);
            Assert.AreSame(RuleTraits.Classic, new SimConfig { Traits = null }.Clone().Traits, "null traits clone to Classic");
        }
    }
}
