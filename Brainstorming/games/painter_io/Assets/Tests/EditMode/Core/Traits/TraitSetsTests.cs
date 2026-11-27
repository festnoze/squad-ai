// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 6: each trait alone and all traits of each biome
// together, in bot rounds: no exception, invariants every tick (EventCapHits == 0 included), determinism (same seed, same
// hash). Under Unity the rounds are shortened (Editor Mono is several times slower than the dotnet loop).
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    public class TraitSetsTests
    {
#if UNITY_5_3_OR_NEWER
        private const double Duration = 30.0;
#else
        private const double Duration = 90.0;
#endif

        private static IEnumerable<object[]> Sets()
        {
            foreach (KeyValuePair<string, RuleTraits> set in TraitTestKit.AllSets())
                yield return new object[] { set.Key, set.Value.ToKey() };
        }

        [TestCaseSource(nameof(Sets))]
        public void TraitSets_BotRoundKeepsInvariantsAndIsDeterministic(string name, string key)
        {
            RuleTraits traits = RuleTraits.Parse(key);
            // Lasso on (RingInterval only acts with it), human slot 0 so the ring prefers its surroundings; seed per set.
            ulong seed = 101UL + (ulong)key.Length;
            Simulation a = TraitTestKit.BotRound(seed, traits, true, 60, 0, Duration);
            Simulation b = TraitTestKit.BotRound(seed, traits, true, 60, 0, Duration);
            var counts = new Dictionary<SimEventType, int>();
            a.EventRaised += e =>
            {
                counts.TryGetValue(e.Type, out int c);
                counts[e.Type] = c + 1;
            };
            int ticks = 0;
            while (!a.Ended)
            {
                a.Step();
                b.Step();
                TraitTestKit.AssertTraitInvariants(a);
                if (++ticks % 15 == 0 || a.Ended) Assert.AreEqual(a.StateHash(), b.StateHash(), name + ": same seed, same hash at tick " + a.Tick);
            }
            Assert.IsTrue(b.Ended);
            Assert.AreEqual(a.StateHash(), b.StateHash());
            Assert.AreEqual(0, a.EventCapHits, "EventCapHits");
            counts.TryGetValue(SimEventType.Return, out int returns);
            Assert.That(returns, Is.GreaterThan(0), name + ": the round was played (returns happened)");
            counts.TryGetValue(SimEventType.TerritoryGrew, out int grew);
            if (traits.Has(TraitId.Propagation)) Assert.That(grew, Is.GreaterThan(0), name + ": Propagation grows territories");
            else Assert.AreEqual(0, grew, name + ": TerritoryGrew only with Propagation");
            TestContext.WriteLine(name + " [" + traits + "]: " + ticks + " ticks, end " + a.Result.Reason + " at "
                                  + TraitTestKit.F(a.Result.EndTime) + " s, returns " + returns + ", grew " + grew);
        }

        [TestCase(30)]
        [TestCase(144)]
        public void TraitSets_BiomeSetsRunAtOtherTickRates(int rate)
        {
            foreach (RuleTraits traits in new[] { TraitTestKit.Liquid, TraitTestKit.Fire, TraitTestKit.Electric })
            {
                Simulation sim = TraitTestKit.BotRound(7UL, traits, true, rate, -1, Duration / 3.0);
                Simulation twin = TraitTestKit.BotRound(7UL, traits, true, rate, -1, Duration / 3.0);
                ulong h1 = TraitTestKit.RollingRoundHash(sim, 30, true);
                ulong h2 = TraitTestKit.RollingRoundHash(twin, 30, false);
                Assert.AreEqual(h1, h2, traits + " at " + rate + " Hz: deterministic");
            }
        }
    }
}
