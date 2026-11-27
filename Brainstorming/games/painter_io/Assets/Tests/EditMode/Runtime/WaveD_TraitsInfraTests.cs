// Owned by traits-infra (wave D-2). EditMode checks of docs/BIOME_TRAITS.md section 5 (Runtime architecture) with the
// section 3 + 7 default table:
// - BiomeTraitTable's default lines equal the keys the Core tests reason on (TraitTestKit.LiquidV11Key / FireV11Key /
//   ElectricV11Key), so the two copies cannot drift;
// - the trait matrix text (parse, canonical form, SetAssigned, parameters of a moved trait);
// - the resolution order: table -> SaveData.TraitMatrix -> command line (-classic, -traits, -trait) -> BiomeRulesOn, and
//   the scripted resolution (classic unless flags) of the probe and DevShot;
// - SaveData: BiomeRulesOn default true and not a tuning change, a modified matrix is (TuningModified), ResetTraitMatrix;
// - GameSession.CreateRound / CreateAttract carry the selected biome's traits, RefreshAttractTraits restarts the attract
//   match only when its traits change; the demo stays classic by default (hash 246577239DE179C4) and runs traited with
//   -traits default (deterministic, EvaluateTraited);
// - Sfx: the Grow clip and the kill reward cues play for the live human only, Grow at -18 dB and rate limited.
// No test writes PlayerPrefs (SaveData.MemoryOnly) and every LaunchArgs.Reload is undone.
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;
using Object = UnityEngine.Object;

namespace PainterIO.Tests
{
    public class WaveD_TraitsInfraTests
    {
        private const ulong ClassicDemoHash = 0x246577239DE179C4UL;
        private static readonly BiomeId[] Biomes = { BiomeId.Liquid, BiomeId.Fire, BiomeId.Electric };

        [SetUp]
        public void SetUp()
        {
            SaveData.MemoryOnly = true;
            SaveData.TraitMatrix = "";
            SaveData.BiomeRulesOn = true;
            SaveData.ResetTestSettings();
            SaveData.Biome = (int)BiomeId.Liquid;
            LaunchArgs.Reload(new[] { "PainterIO.exe" });
        }

        [TearDown]
        public void TearDown()
        {
            LaunchArgs.Reload();
            SaveData.MemoryOnly = false;
        }

        // ------------------------------------------------------------------------------------------------------------
        // The table.

        [Test]
        public void WaveD_DefaultLinesEqualTheCoreTestKeys()
        {
            Assert.AreEqual(TraitTestKit.LiquidV11Key, BiomeTraitTable.DefaultKey(BiomeId.Liquid));
            Assert.AreEqual(TraitTestKit.FireV11Key, BiomeTraitTable.DefaultKey(BiomeId.Fire));
            Assert.AreEqual(TraitTestKit.ElectricV11Key, BiomeTraitTable.DefaultKey(BiomeId.Electric));
            Assert.AreEqual(TraitTestKit.LiquidV11, BiomeTraitTable.Defaults(BiomeId.Liquid));
            Assert.AreEqual(TraitTestKit.FireV11, BiomeTraitTable.Defaults(BiomeId.Fire));
            Assert.AreEqual(TraitTestKit.ElectricV11, BiomeTraitTable.Defaults(BiomeId.Electric));
            // Section 7: each kill reward belongs to exactly one biome.
            Assert.AreEqual(1 << (int)BiomeId.Fire, BiomeTraitTable.DefaultMask(TraitId.KillInheritance));
            Assert.AreEqual(1 << (int)BiomeId.Electric, BiomeTraitTable.DefaultMask(TraitId.KillSpeedBoost));
            Assert.AreEqual(1 << (int)BiomeId.Liquid, BiomeTraitTable.DefaultMask(TraitId.KillShield));
            Assert.AreEqual((1 << (int)BiomeId.Fire) | (1 << (int)BiomeId.Electric), BiomeTraitTable.DefaultMask(TraitId.SparkSpeed));
            foreach (TraitId id in TraitDefaults.All)
            {
                Assert.AreNotEqual(0, BiomeTraitTable.DefaultMask(id), id + " belongs to at least one biome");
            }
        }

        [Test]
        public void WaveD_MatrixTextParsesAndCanonicalizes()
        {
            Assert.AreEqual("", BiomeTraitTable.CanonicalMatrix(null));
            Assert.AreEqual("", BiomeTraitTable.CanonicalMatrix(""));
            Assert.AreEqual("", BiomeTraitTable.CanonicalMatrix("Inertia=L;SparkSpeed=EF"), "rows equal to the table vanish");
            Assert.AreEqual("SparkSpeed=LFE;KillShield=-", BiomeTraitTable.CanonicalMatrix(" killshield = - ; 3=efl ; Nope=L ; Inertia=X"));
            Dictionary<TraitId, int> m = BiomeTraitTable.ParseMatrix("KillShield=F;Conduction=LE");
            Assert.AreEqual(2, m.Count);
            Assert.AreEqual(1 << (int)BiomeId.Fire, m[TraitId.KillShield]);
            Assert.AreEqual("Conduction=LE;KillShield=F", BiomeTraitTable.FormatMatrix(m), "ascending id");

            // Moving a trait: KillShield to Feu (from Liquide); SparkSpeed into Liquide takes TraitDefaults' factor.
            RuleTraits fire = BiomeTraitTable.FromMatrix(BiomeId.Fire, "KillShield=F");
            RuleTraits liquid = BiomeTraitTable.FromMatrix(BiomeId.Liquid, "KillShield=F;SparkSpeed=LFE");
            Assert.IsTrue(fire.Has(TraitId.KillShield));
            Assert.AreEqual(3.0, fire.Get(TraitId.KillShield).P1);
            Assert.IsFalse(liquid.Has(TraitId.KillShield));
            Assert.AreEqual(TraitDefaults.SparkSpeedFactor, liquid.Get(TraitId.SparkSpeed).P1);
            Assert.AreEqual(1.5, BiomeTraitTable.FromMatrix(BiomeId.Electric, "SparkSpeed=LFE").Get(TraitId.SparkSpeed).P1, "Electricite keeps its own 1.5");
            Assert.AreEqual(BiomeTraitTable.Defaults(BiomeId.Electric), BiomeTraitTable.FromMatrix(BiomeId.Electric, "KillShield=F"));
        }

        [Test]
        public void WaveD_SetAssignedWritesTheCanonicalMatrixAndMarksTheTuning()
        {
            Assert.IsFalse(SaveData.TuningModified);
            int changes = 0;
            System.Action count = () => changes++;
            SaveData.Changed += count;
            try
            {
                BiomeTraitTable.SetAssigned(TraitId.Propagation, BiomeId.Liquid, true);
                Assert.AreEqual("Propagation=LF", SaveData.TraitMatrix);
                Assert.IsTrue(BiomeTraitTable.IsAssigned(TraitId.Propagation, BiomeId.Liquid));
                Assert.IsTrue(SaveData.TraitMatrixModified);
                Assert.IsTrue(SaveData.TuningModified, "a modified matrix is a test setting");
                Assert.IsTrue(BiomeTraitTable.Resolve(BiomeId.Liquid).Has(TraitId.Propagation));

                BiomeTraitTable.SetAssigned(TraitId.Propagation, BiomeId.Liquid, false);
                Assert.AreEqual("", SaveData.TraitMatrix, "back to the table: the canonical text is empty");
                Assert.IsFalse(SaveData.TuningModified);

                BiomeTraitTable.SetAssigned(TraitId.KillShield, BiomeId.Liquid, false);
                Assert.AreEqual("KillShield=-", SaveData.TraitMatrix);
                SaveData.ResetTraitMatrix();
                Assert.AreEqual("", SaveData.TraitMatrix);
                Assert.IsTrue(BiomeTraitTable.IsAssigned(TraitId.KillShield, BiomeId.Liquid));
                Assert.That(changes, Is.GreaterThanOrEqualTo(4), "every write raises SaveData.Changed");

                SaveData.TraitMatrix = "garbage;;Inertia=Q";
                Assert.AreEqual("", SaveData.TraitMatrix, "the setter canonicalizes");
            }
            finally
            {
                SaveData.Changed -= count;
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Resolution.

        [Test]
        public void WaveD_ResolveFollowsTableMatrixCommandLineThenTheMasterSwitch()
        {
            foreach (BiomeId b in Biomes) Assert.AreEqual(BiomeTraitTable.Defaults(b), BiomeTraitTable.Resolve(b), b + " defaults");

            SaveData.TraitMatrix = "KillInheritance=FE";
            Assert.IsTrue(BiomeTraitTable.Resolve(BiomeId.Electric).Has(TraitId.KillInheritance), "the matrix over the table");

            LaunchArgs.Reload(new[] { "PainterIO.exe", "-trait", "KillInheritance=0", "-trait", "Coalescence=1" });
            RuleTraits e = BiomeTraitTable.Resolve(BiomeId.Electric);
            Assert.IsFalse(e.Has(TraitId.KillInheritance), "-trait over the matrix");
            Assert.IsTrue(e.Has(TraitId.Coalescence));
            Assert.AreEqual(TraitDefaults.CoalescenceMaxHoleArea, e.Get(TraitId.Coalescence).P1);

            LaunchArgs.Reload(new[] { "PainterIO.exe", "-traits", "Propagation(2,2)" });
            Assert.AreEqual("Propagation(2,2)", BiomeTraitTable.Resolve(BiomeId.Liquid).ToKey(), "-traits is the exact set, any biome");
            LaunchArgs.Reload(new[] { "PainterIO.exe", "-traits", "default" });
            Assert.AreEqual(TraitTestKit.ElectricV11Key, BiomeTraitTable.Resolve(BiomeId.Electric).ToKey(), "-traits default ignores the saved matrix");
            LaunchArgs.Reload(new[] { "PainterIO.exe", "-traits", "default", "-classic" });
            Assert.IsTrue(BiomeTraitTable.Resolve(BiomeId.Fire).IsClassic, "-classic wins");

            LaunchArgs.Reload(new[] { "PainterIO.exe" });
            SaveData.BiomeRulesOn = false;
            Assert.IsFalse(SaveData.TraitMatrix.Length == 0, "matrix still saved");
            foreach (BiomeId b in Biomes) Assert.IsTrue(BiomeTraitTable.Resolve(b).IsClassic, b + ": Regles classiques");
            SaveData.TraitMatrix = "";
            Assert.IsFalse(SaveData.TuningModified, "BiomeRulesOn = false is a normal option, not a tuning change");
        }

        [Test]
        public void WaveD_ScriptedSessionsAreClassicUnlessTheCommandLineSaysOtherwise()
        {
            SaveData.TraitMatrix = "Propagation=LFE";
            foreach (BiomeId b in Biomes) Assert.IsTrue(BiomeTraitTable.ResolveScripted(b).IsClassic, b + ": never the saved options");
            LaunchArgs.Reload(new[] { "PainterIO.exe", "-traits", "default", "-trait", "KillInheritance=0" });
            Assert.AreEqual("SparkSpeed(2.1,0);Propagation(4,1);ScorchedEarth(15,0)", BiomeTraitTable.ResolveScripted(BiomeId.Fire).ToKey());
            LaunchArgs.Reload(new[] { "PainterIO.exe", "-trait", "ArcReach=1" });
            Assert.AreEqual("ArcReach(1.4,0)", BiomeTraitTable.ResolveScripted(BiomeId.Liquid).ToKey(), "-trait on top of classic");
        }

        [Test]
        public void WaveD_LaunchArgsParseTheTraitFlags()
        {
            LaunchArgs.Reload(new[] { "PainterIO.exe", "-CLASSIC", "-traits", "SparkSpeed(1.5);Conduction", "-trait", "killshield=off",
                                      "-trait", "7=1", "-trait", "Nope=1", "-trait", "Inertia=maybe" });
            Assert.IsTrue(LaunchArgs.Classic);
            Assert.AreEqual("SparkSpeed(1.5);Conduction", LaunchArgs.TraitsKey);
            Assert.AreEqual(2, LaunchArgs.TraitToggles.Count);
            Assert.AreEqual(TraitId.KillShield, LaunchArgs.TraitToggles[0].Key);
            Assert.IsFalse(LaunchArgs.TraitToggles[0].Value);
            Assert.AreEqual(TraitId.ArcReach, LaunchArgs.TraitToggles[1].Key);
            Assert.IsTrue(LaunchArgs.TraitToggles[1].Value);
            StringAssert.Contains("Nope=1", LaunchArgs.TraitArgsError, "the first bad -trait is reported");
            Assert.IsTrue(LaunchArgs.HasTraitArgs);
            Assert.IsTrue(LaunchArgs.HasTuningOverride, "an explicit trait set is a tuning override (stats not saved)");

            LaunchArgs.Reload(new[] { "PainterIO.exe", "-traits", "Bogus(1)" });
            Assert.IsNull(LaunchArgs.TraitsKey);
            StringAssert.Contains("Bogus", LaunchArgs.TraitArgsError);
            LaunchArgs.Reload(new[] { "PainterIO.exe", "-classic" });
            Assert.IsFalse(LaunchArgs.HasTuningOverride, "-classic is a normal option");
            LaunchArgs.Reload(new[] { "PainterIO.exe", "-traits", "default" });
            Assert.IsFalse(LaunchArgs.HasTuningOverride, "-traits default is the biome's own rules");
            LaunchArgs.Reload(new[] { "PainterIO.exe" });
            Assert.IsFalse(LaunchArgs.HasTraitArgs);
            Assert.IsNull(LaunchArgs.TraitArgsError);
        }

        [Test]
        public void WaveD_ComposeAppliesTheOverridesInOrder()
        {
            RuleTraits fire = BiomeTraitTable.Defaults(BiomeId.Fire);
            Assert.AreSame(RuleTraits.Classic, BiomeTraitTable.Compose(fire, BiomeId.Fire, true, "default", null));
            Assert.AreEqual(fire, BiomeTraitTable.Compose(fire, BiomeId.Fire, false, "not a key (", null), "a bad key keeps the set");
            var toggles = new List<KeyValuePair<TraitId, bool>>
            {
                new KeyValuePair<TraitId, bool>(TraitId.KillInheritance, false),
                new KeyValuePair<TraitId, bool>(TraitId.KillShield, true),
                new KeyValuePair<TraitId, bool>(TraitId.SparkSpeed, true),
            };
            RuleTraits r = BiomeTraitTable.Compose(fire, BiomeId.Fire, false, null, toggles);
            Assert.AreEqual("SparkSpeed(2.1,0);Propagation(4,1);ScorchedEarth(15,0);KillShield(3,0)", r.ToKey(), "an enabled trait keeps its parameters");
        }

        // ------------------------------------------------------------------------------------------------------------
        // Sessions.

        [Test]
        public void WaveD_RoundsAndTheAttractCarryTheSelectedBiomesTraits()
        {
            foreach (BiomeId b in Biomes)
            {
                SaveData.Biome = (int)b;
                GameSession round = GameSession.CreateRound(7UL, false);
                GameSession attract = GameSession.CreateAttract(7UL);
                try
                {
                    Assert.AreEqual(BiomeTraitTable.DefaultKey(b), round.Traits.ToKey(), b + " round");
                    Assert.AreEqual(BiomeTraitTable.DefaultKey(b), attract.Traits.ToKey(), b + " attract");
                    Assert.AreEqual(Tuning.SparkSpeedFactor, GameSession.RoundConfig(7UL, false).SparkSpeedFactor, "config traits apply to the sim's clone only");
                }
                finally
                {
                    round.Close();
                    attract.Close();
                }
            }
            SaveData.BiomeRulesOn = false;
            GameSession classic = GameSession.CreateRound(7UL, false);
            Assert.IsTrue(classic.Traits.IsClassic, "Regles classiques");
            classic.Close();
            Assert.IsTrue(GameSession.RoundConfig(7UL, true, null).Traits.IsClassic);
        }

        [Test]
        public void WaveD_TheAttractRestartsOnlyWhenItsTraitsChange()
        {
            GameSession attract = GameSession.CreateAttract(11UL);
            try
            {
                int restarts = 0;
                attract.Restarted += s => restarts++;
                Simulation first = attract.Sim;
                Assert.IsFalse(attract.RefreshAttractTraits(), "same traits: no restart");
                Assert.AreSame(first, attract.Sim);

                SaveData.Biome = (int)BiomeId.Electric;
                Assert.IsTrue(attract.RefreshAttractTraits());
                Assert.AreEqual(1, restarts);
                Assert.AreNotSame(first, attract.Sim);
                Assert.AreEqual(TraitTestKit.ElectricV11Key, attract.Traits.ToKey());
                Assert.AreSame(attract.Sim, attract.Runner.Sim);

                SaveData.BiomeRulesOn = false;
                Assert.IsTrue(attract.RefreshAttractTraits());
                Assert.IsTrue(attract.Traits.IsClassic);
                Assert.IsFalse(attract.RefreshAttractTraits());
                Assert.AreEqual(2, restarts);

                GameSession round = GameSession.CreateRound(3UL, false);
                Assert.IsFalse(round.RefreshAttractTraits(), "real rounds keep their traits");
                round.Close();
            }
            finally
            {
                attract.Close();
            }
        }

        [Test]
        public void WaveD_TheDemoIsClassicByDefaultAndRunsTraitedWithTheFlags()
        {
            SaveData.TraitMatrix = "Propagation=LFE";
            GameSession demo = DemoScenario.CreateSession(out DemoScenario.Monitor monitor, BiomeId.Fire);
            Assert.IsTrue(demo.Traits.IsClassic, "the probe and DevShot run classic by default");
            Assert.AreEqual(ClassicDemoHash, RunToEnd(demo.Sim, monitor), "the classic probe hash");
            Assert.IsTrue(monitor.Evaluate(out List<string> failures), string.Join("; ", failures));
            demo.Close();

            LaunchArgs.Reload(new[] { "PainterIO.exe", "-traits", "default" });
            var hashes = new HashSet<ulong>();
            foreach (BiomeId b in Biomes)
            {
                ulong first = 0;
                for (int run = 0; run < 2; run++)
                {
                    GameSession s = DemoScenario.CreateSession(out DemoScenario.Monitor m, b);
                    var shots = new DemoScenario.TraitShots(s.Sim);
                    Assert.AreEqual(BiomeTraitTable.DefaultKey(b), s.Traits.ToKey());
                    ulong hash = RunToEnd(s.Sim, m);
                    Assert.IsTrue(m.EvaluateTraited(out List<string> traitedFailures), b + ": " + string.Join("; ", traitedFailures));
                    Assert.That(new List<string>(shots.Planned), Has.Member("reward"), b + ": the killer's reward is planned");
                    shots.Detach();
                    s.Close();
                    if (run == 0) first = hash;
                    else Assert.AreEqual(first, hash, b + " is deterministic");
                }
                Assert.AreNotEqual(ClassicDemoHash, first, b + ": the traits changed the round");
                hashes.Add(first);
            }
            Assert.AreEqual(3, hashes.Count, "one hash per biome");
        }

        [Test]
        public void WaveD_TraitShotsAreNeverPlannedInAClassicRound()
        {
            Simulation sim = DemoScenario.CreateSimulation(out DemoScenario.Monitor monitor);
            var shots = new DemoScenario.TraitShots(sim);
            RunToEnd(sim, monitor);
            Assert.AreEqual(0, shots.PendingCount);
            Assert.IsEmpty(new List<string>(shots.Planned));
        }

        // ------------------------------------------------------------------------------------------------------------
        // Sounds.

        [Test]
        public void WaveD_GrowAndKillRewardCuesPlayForTheLiveHumanOnly()
        {
            Sfx sfx = Sfx.Create(null);
            GameSession session = DemoScenario.CreateSession(out DemoScenario.Monitor _, null, RuleTraits.Classic);
            try
            {
                var cues = new List<SfxCue>();
                var pulses = new List<int>();
                sfx.CuePlayed += c => cues.Add(c);
                sfx.HapticPulsed += ms => pulses.Add(ms);
                sfx.Attach(session, GameState.Playing);

                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.TerritoryGrew, Player = 1, Cells = new[] { 5 } });
                Assert.AreEqual(0, cues.Count, "a bot's growth is silent");
                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.TerritoryGrew, Player = 0, Cells = new[] { 5, 6 } });
                Assert.AreEqual(1, cues.Count);
                Assert.AreEqual(SfxId.GrowCreep, cues[0].Id);
                Assert.AreEqual(Sfx.GrowGainDb, cues[0].GainDb);
                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.TerritoryGrew, Player = 0, Cells = new[] { 7 } });
                Assert.AreEqual(1, cues.Count, "rate limited");
                for (int k = 0; k < 9; k++) sfx.Tick(0.25f);   // Tick clamps each step to 0.25 s: 2.25 s in all
                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.TerritoryGrew, Player = 0, Cells = new[] { 8 } });
                Assert.AreEqual(2, cues.Count, "again after the rate limit");

                cues.Clear();
                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.TerritoryInherited, Player = 0, Other = 2, Cells = new[] { 9 } });
                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.SpeedBoosted, Player = 0, Other = 2, Value = 1.2 });
                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.ShieldStarted, Player = 0, Other = 2, Value = 9.0 });
                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.ShieldEnded, Player = 0, Value = 9.0 });
                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.TerritoryInherited, Player = 3, Other = 0, Cells = new[] { 9 } });
                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.ShieldStarted, Player = 3, Other = 1, Value = 9.0 });
                Assert.AreEqual(4, cues.Count, "the human's four reward cues, none for a bot");
                Assert.AreEqual(SfxId.KillInherit, cues[0].Id);
                Assert.AreEqual(0f, cues[0].GainDb);
                Assert.AreEqual(SfxId.SpeedUp, cues[1].Id);
                Assert.AreEqual(1.1f, cues[1].Pitch, 1e-4f, "pitched up per speed level");
                Assert.AreEqual(SfxId.ShieldShimmer, cues[2].Id);
                Assert.AreEqual(SfxId.ShieldShimmer, cues[3].Id);
                Assert.AreEqual(Sfx.ShieldEndGainDb, cues[3].GainDb);
                Assert.AreEqual(Sfx.ShieldEndPitch, cues[3].Pitch, 1e-6f);
                CollectionAssert.AreEqual(new[] { Haptics.CaptureMs }, pulses, "the inherited land pulses like a capture");
                foreach (SfxCue c in cues) Assert.AreEqual(0, c.Player);

                // In the menu (attract) nothing of this plays.
                cues.Clear();
                GameSession attract = GameSession.CreateAttract(5UL);
                sfx.Attach(attract, GameState.Menu);
                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.ShieldStarted, Player = 0, Other = 1, Value = 9.0 });
                sfx.HandleEventForTests(new SimEvent { Type = SimEventType.TerritoryGrew, Player = 0, Cells = new[] { 5 } });
                Assert.AreEqual(0, cues.Count);
                attract.Close();
            }
            finally
            {
                session.Close();
                sfx.Teardown();
                Object.DestroyImmediate(sfx.gameObject);
            }
        }

        [Test]
        public void WaveD_EveryClipSetHasItsGrowClipAndTheWaveCHashesStay()
        {
            foreach (BiomeId b in Biomes)
            {
                ISfxClipSet set = Sfx.CreateClipSet(b);
                set.Build(SfxSynth.SampleRate);
                try
                {
                    Assert.IsNotNull(set.Grow, b + " Grow");
                    Assert.AreSame(set.Grow, Sfx.SlotClip(set, SfxId.GrowCreep));
                    Assert.That(set.Grow.length, Is.InRange(0.3f, 1.0f), b + " Grow length");
                    var split = (ISplitSfxClipSet)Sfx.CreateClipSet(b);
                    SfxClipSamples samples = split.Synthesize(SfxSynth.SampleRate);
                    Assert.IsNotNull(samples.Get(SfxSlot.Grow), b + " Grow samples");
                    Assert.IsNull(samples.ErrorOf(SfxSlot.Grow));
                    // Hash() covers the eight base slots only: a Grow change never moves the wave C hashes.
                    float[] keep = samples.Get(SfxSlot.Grow);
                    ulong before = samples.Hash();
                    samples.Set(SfxSlot.Grow, new float[] { 0f, 0.5f, 0f });
                    Assert.AreEqual(before, samples.Hash());
                    samples.Set(SfxSlot.Grow, keep);
                }
                finally
                {
                    foreach (AudioClip c in new[] { set.Exit, set.Return, set.Fill, set.Cut, set.TensionLoop, set.Caught, set.LoopLost, set.Ambient, set.Grow })
                    {
                        if (c != null) Object.DestroyImmediate(c);
                    }
                }
            }
            Assert.IsTrue(Sfx.IsBiomeSlot(SfxId.GrowCreep));
            foreach (SfxId id in new[] { SfxId.KillInherit, SfxId.SpeedUp, SfxId.ShieldShimmer }) Assert.IsFalse(Sfx.IsBiomeSlot(id), id + " is shared");
        }

        // ------------------------------------------------------------------------------------------------------------

        private static ulong RunToEnd(Simulation sim, DemoScenario.Monitor monitor)
        {
            ulong hash = 0;
            while (sim.Tick < DemoScenario.EndTick && !sim.Ended) sim.Step();
            if (sim.Tick == DemoScenario.EndTick) hash = sim.StateHash();
            monitor.Finish();
            return hash;
        }
    }
}
