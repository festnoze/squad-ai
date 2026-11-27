// Owned by BI since wave B-2 (written by B5). EditMode checks of contract 16 (+ 24 loop lost, 25.2 clip sets) (audio and haptics): every procedural clip has its expected length, no
// NaN, a peak at most 0.95 and a clean start and end (the tension loop joins seamlessly instead); synthesis is
// deterministic; the tension pitch, pulse rate and volume rise monotonically as SparkCatchEta drops; the scope rules;
// Haptics.Pulse never throws; and a Sfx without a GameDirector hears the DemoScenario round, a short round's countdown
// and an attract match with the expected cues and haptics. No test writes PlayerPrefs.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;
using Object = UnityEngine.Object;

namespace PainterIO.Tests
{
    public class SfxTests
    {
        private const float Frame = 1f / 60f;

        private static IEnumerable<SfxId> AllClips()
        {
            foreach (SfxId id in Enum.GetValues(typeof(SfxId))) yield return id;
        }

        [Test]
        public void Sfx_EveryClipHasItsExpectedLengthNoNaNAndAPeakAtMost095()
        {
            Assert.AreEqual(SfxSynth.ClipCount, Enum.GetValues(typeof(SfxId)).Length);
            foreach (SfxId id in AllClips())
            {
                float[] data = SfxSynth.Generate(id);
                int expected = (int)Math.Round(SfxSynth.DurationOf(id) * SfxSynth.SampleRate);
                Assert.AreEqual(expected, data.Length, id + " length");
                Assert.AreEqual(SfxSynth.SampleCount(id), data.Length, id + " SampleCount");
                Assert.That(SfxSynth.DurationOf(id), Is.InRange(0.05, 2.0), id + " duration (short envelopes)");
                float peak = 0f;
                double sumSq = 0.0;
                for (int i = 0; i < data.Length; i++)
                {
                    float x = data[i];
                    Assert.IsFalse(float.IsNaN(x) || float.IsInfinity(x), id + " sample " + i + " is " + x);
                    peak = Math.Max(peak, Math.Abs(x));
                    sumSq += (double)x * x;
                }
                Assert.That(peak, Is.LessThanOrEqualTo(SfxSynth.PeakLimit), id + " peak");
                Assert.That(peak, Is.LessThanOrEqualTo(0.95f), id + " peak");
                Assert.That(peak, Is.GreaterThan(0.5f), id + " is not silent");
                Assert.That(Math.Sqrt(sumSq / data.Length), Is.GreaterThan(0.05), id + " rms");
            }
        }

        [Test]
        public void Sfx_OneShotsStartAndEndOnSilenceAndTheLoopJoinsSeamlessly()
        {
            foreach (SfxId id in AllClips())
            {
                float[] data = SfxSynth.Generate(id);
                if (SfxSynth.IsLoop(id))
                {
                    float maxStep = 0f;
                    for (int i = 1; i < data.Length; i++) maxStep = Math.Max(maxStep, Math.Abs(data[i] - data[i - 1]));
                    float wrapStep = Math.Abs(data[0] - data[data.Length - 1]);
                    Assert.That(wrapStep, Is.LessThanOrEqualTo(maxStep * 0.5f), id + ": the wrap is no harder than the loop's own steps");
                    continue;
                }
                Assert.That(Math.Abs(data[0]), Is.LessThan(1e-4f), id + " first sample (no click at the start)");
                Assert.That(Math.Abs(data[data.Length - 1]), Is.LessThan(1e-4f), id + " last sample (no click at the end)");
            }
            Assert.IsTrue(SfxSynth.IsLoop(SfxId.SparkLoop));
            Assert.AreEqual((int)Math.Round(SfxSynth.SparkLoopSeconds * SfxSynth.SampleRate), SfxSynth.SampleCount(SfxId.SparkLoop));
        }

        [Test]
        public void Sfx_SynthesisIsDeterministic()
        {
            foreach (SfxId id in AllClips())
            {
                float[] a = SfxSynth.Generate(id);
                float[] b = SfxSynth.Generate(id);
                Assert.AreEqual(a.Length, b.Length, id.ToString());
                for (int i = 0; i < a.Length; i++)
                {
                    if (a[i] != b[i]) Assert.Fail(id + " differs at sample " + i);
                }
            }
        }

        [Test]
        public void Sfx_ClipsBecomeMonoAudioClipsOfTheExpectedLength()
        {
            foreach (SfxId id in AllClips())
            {
                AudioClip clip = SfxSynth.CreateClip(id);
                try
                {
                    Assert.IsNotNull(clip, id.ToString());
                    Assert.AreEqual(1, clip.channels, id + " channels");
                    Assert.AreEqual(SfxSynth.SampleRate, clip.frequency, id + " frequency");
                    Assert.AreEqual(SfxSynth.SampleCount(id), clip.samples, id + " samples");
                    Assert.AreEqual("pio_" + id, clip.name);
                }
                finally
                {
                    if (clip != null) Object.DestroyImmediate(clip);
                }
            }
        }

        [Test]
        public void Sfx_TensionPitchRateAndVolumeRiseMonotonicallyAsEtaDrops()
        {
            float prevPitch = float.MaxValue, prevRate = float.MaxValue, prevVolume = float.MaxValue;
            for (int k = 0; k <= 800; k++)
            {
                double eta = k * 0.01;   // 0 .. 8 s, ascending: every parameter must be non-increasing
                float pitch = SfxSynth.TensionPitch(eta);
                float rate = SfxSynth.TensionRate(eta);
                float volume = SfxSynth.TensionVolume(eta);
                Assert.IsFalse(float.IsNaN(pitch) || float.IsNaN(rate) || float.IsNaN(volume), "eta " + eta);
                Assert.That(pitch, Is.LessThanOrEqualTo(prevPitch), "pitch at eta " + eta);
                Assert.That(rate, Is.LessThanOrEqualTo(prevRate), "rate at eta " + eta);
                Assert.That(volume, Is.LessThanOrEqualTo(prevVolume), "volume at eta " + eta);
                prevPitch = pitch;
                prevRate = rate;
                prevVolume = volume;
            }
            // Strictly rising over the useful range, bounded at both ends.
            Assert.That(SfxSynth.TensionPitch(0.5), Is.GreaterThan(SfxSynth.TensionPitch(1.0)));
            Assert.That(SfxSynth.TensionPitch(1.0), Is.GreaterThan(SfxSynth.TensionPitch(2.0)));
            Assert.That(SfxSynth.TensionPitch(2.0), Is.GreaterThan(SfxSynth.TensionPitch(3.5)));
            Assert.That(SfxSynth.TensionRate(0.5), Is.GreaterThan(SfxSynth.TensionRate(2.0)));
            Assert.That(SfxSynth.TensionVolume(0.5), Is.GreaterThan(SfxSynth.TensionVolume(2.0)));
            Assert.AreEqual(SfxSynth.TensionTopPitch, SfxSynth.TensionPitch(0.0), 1e-5f);
            Assert.AreEqual(SfxSynth.TensionTopPitch, SfxSynth.TensionPitch(-1.0), 1e-5f, "a negative eta is imminent");
            Assert.AreEqual(SfxSynth.TensionBasePitch, SfxSynth.TensionPitch(double.PositiveInfinity), 1e-6f, "no spark");
            Assert.AreEqual(SfxSynth.TensionBasePitch, SfxSynth.TensionPitch(double.NaN), 1e-6f, "NaN is treated as far");
            Assert.AreEqual(SfxSynth.TensionBaseVolume, SfxSynth.TensionVolume(double.PositiveInfinity), 1e-6f);
            Assert.AreEqual(SfxSynth.TensionTopVolume, SfxSynth.TensionVolume(0.0), 1e-6f);
            Assert.AreEqual(4f, SfxSynth.TensionRate(double.PositiveInfinity), 1e-5f, "base pulse rate 4 per second");
            Assert.That(SfxSynth.TensionRate(0.0), Is.EqualTo(4f * SfxSynth.TensionTopPitch).Within(1e-4f));
        }

        [Test]
        public void Sfx_ScopeRulesFollowContract16()
        {
            // Live round: the human's events at full volume wherever they are; bot events on screen only, at -12 dB.
            Assert.AreEqual(0f, SfxScope.EventGainDb(true, true, false));
            Assert.AreEqual(0f, SfxScope.EventGainDb(true, true, true));
            Assert.AreEqual(-12f, SfxScope.EventGainDb(true, false, true));
            Assert.IsNull(SfxScope.EventGainDb(true, false, false));
            // Menu (attract) and after the human's elimination: on-screen events only, at -18 dB.
            Assert.AreEqual(-18f, SfxScope.EventGainDb(false, false, true));
            Assert.AreEqual(-18f, SfxScope.EventGainDb(false, true, true));
            Assert.IsNull(SfxScope.EventGainDb(false, true, false));
            Assert.IsNull(SfxScope.EventGainDb(false, false, false));
            Assert.AreEqual(0.25f, SfxScope.RateLimitSeconds);
            Assert.That(SfxScope.DbToGain(-12f), Is.EqualTo(0.2512f).Within(1e-3f));
            Assert.That(SfxScope.DbToGain(-18f), Is.EqualTo(0.1259f).Within(1e-3f));
            Assert.AreEqual(1f, SfxScope.DbToGain(0f), 1e-6f);

            Assert.IsTrue(SfxScope.IsScopedType(SimEventType.Exit));
            Assert.IsTrue(SfxScope.IsScopedType(SimEventType.Return));
            Assert.IsTrue(SfxScope.IsScopedType(SimEventType.Cut));
            Assert.IsTrue(SfxScope.IsScopedType(SimEventType.Eliminated));
            Assert.IsFalse(SfxScope.IsScopedType(SimEventType.LassoPocket));
            Assert.IsFalse(SfxScope.IsScopedType(SimEventType.RingPicked));
            Assert.IsFalse(SfxScope.IsScopedType(SimEventType.RoundEnded));

            foreach (SfxId id in AllClips())
            {
                float v = Sfx.BaseVolume(id);
                Assert.That(v, Is.InRange(0.1f, 1f), id + " base volume");
            }
        }

        [Test]
        public void Haptics_PulseNeverThrowsAndUsesTheContractDurations()
        {
            Assert.AreEqual(60, Haptics.CutReceivedMs);
            Assert.AreEqual(30, Haptics.CutDealtMs);
            Assert.AreEqual(120, Haptics.CaughtMs);
            Assert.AreEqual(40, Haptics.SavedReturnMs);
            Assert.AreEqual(20, Haptics.CaptureMs);
            foreach (int ms in new[] { 0, -5, 1, 20, 60, 120, Haptics.MaxPulseMs + 1, int.MaxValue, int.MinValue })
            {
                Assert.DoesNotThrow(() => Haptics.Pulse(ms), "Pulse(" + ms + ")");
            }
            Assert.IsFalse(Haptics.Disabled, "a no-op platform never disables haptics");
        }

        [Test]
        public void Sfx_UiClickAndToastTickAreDecidedInEveryStateAndRateLimited()
        {
            Sfx sfx = Sfx.Create(null);
            try
            {
                Assert.AreSame(sfx, Sfx.Instance);
                var cues = new List<SfxCue>();
                sfx.CuePlayed += c => cues.Add(c);
                Sfx.PlayUiClick();
                Sfx.PlayUiClick();   // same instant: dropped
                Assert.AreEqual(1, cues.Count);
                Assert.AreEqual(SfxId.UiClick, cues[0].Id);
                Assert.AreEqual(-1, cues[0].Player);
                sfx.Tick(0.05f);
                Sfx.PlayUiClick();
                Sfx.PlayToastTick();
                Assert.AreEqual(3, cues.Count);
                Assert.AreEqual(SfxId.ToastTick, cues[2].Id);
                if (Application.isBatchMode)
                {
                    Assert.IsTrue(sfx.HardMuted, "batchmode is muted");
                    foreach (SfxCue c in cues) Assert.IsFalse(c.Audible, "nothing plays in batchmode");
                }
            }
            finally
            {
                Destroy(sfx);
            }
            Assert.IsNull(Sfx.Instance, "Teardown clears the instance");
            Assert.DoesNotThrow(Sfx.PlayUiClick, "no-op without a Sfx");
        }

        [Test]
        public void Sfx_DemoRoundPlaysTheHumanCuesAndHapticsInOrder()
        {
            Sfx sfx = Sfx.Create(null);
            try
            {
                GameSession session = DemoScenario.CreateSession(out DemoScenario.Monitor monitor);
                var cues = new List<SfxCue>();
                var cueTicks = new List<long>();
                var pulses = new List<int>();
                sfx.CuePlayed += c =>
                {
                    cues.Add(c);
                    cueTicks.Add(session.Sim.Tick);
                };
                sfx.HapticPulsed += ms => pulses.Add(ms);
                sfx.Attach(session, GameState.Playing);

                var chasePitches = new List<List<float>>();
                bool wasChased = false;
                int frames = 0;
                while (session.Sim.Tick < DemoScenario.EndTick && !session.Sim.Ended)
                {
                    session.Advance(Frame);
                    sfx.Tick(Frame);
                    if (sfx.TensionActive)
                    {
                        if (!wasChased) chasePitches.Add(new List<float>());
                        chasePitches[chasePitches.Count - 1].Add(sfx.TensionPitch);
                    }
                    wasChased = sfx.TensionActive;
                    Assert.Less(++frames, 5000, "runaway");
                }
                monitor.Finish();
                Assert.IsTrue(monitor.Evaluate(out List<string> failures), string.Join("; ", failures));

                // The human's full-volume cues, in order.
                var human = new List<SfxId>();
                for (int k = 0; k < cues.Count; k++)
                {
                    if (cues[k].Player == DemoScenario.Human && cues[k].GainDb >= -6f) human.Add(cues[k].Id);
                }
                // v1.4 story: clean capture (gloop + swell), saved chase (gloop + loop lost, no swell), pocket, fatal cut.
                SfxId[] expected =
                {
                    SfxId.ExitPlop, SfxId.ReturnGloop, SfxId.FillSwell,
                    SfxId.ExitPlop, SfxId.CutSnap, SfxId.SparkLoop, SfxId.ReturnGloop, SfxId.LoopLost,
                    SfxId.ExitPlop, SfxId.LassoZip, SfxId.CutSnap, SfxId.SparkLoop, SfxId.CaughtSplat,
                };
                AssertSubsequence(expected, human, "human cues");
                Assert.AreEqual(1, Count(human, SfxId.CaughtSplat), "one splat for the human's death");
                Assert.AreEqual(1, Count(human, SfxId.FillSwell), "the swell plays only for the clean capture");
                Assert.AreEqual(1, Count(human, SfxId.LoopLost), "contract 24: one loop lost for the saved chased return");
                Assert.AreEqual(0, Count(human, SfxId.CountdownTick), "no countdown in a 15 s round of 90");
                int lost = human.IndexOf(SfxId.LoopLost);
                Assert.AreEqual(SfxId.ReturnGloop, human[lost - 1], "the pearl merges (gloop) right before the loop lost sound");

                // Haptics: capture, cut received, saved return (no capture), cut received, caught.
                CollectionAssert.AreEqual(new[] { Haptics.CaptureMs, Haptics.CutReceivedMs, Haptics.SavedReturnMs, Haptics.CutReceivedMs, Haptics.CaughtMs },
                                          pulses, "haptic pulses " + string.Join(",", pulses));

                // Tension: two chases, each rising in pitch as the spark closes in.
                Assert.AreEqual(2, chasePitches.Count, "two chases");
                foreach (List<float> chase in chasePitches)
                {
                    Assert.That(chase.Count, Is.GreaterThan(5));
                    Assert.That(chase[chase.Count - 1], Is.GreaterThan(chase[0]), "pitch rises during a chase");
                    Assert.That(chase[chase.Count - 1], Is.GreaterThan(1.2f));
                }
                Assert.IsFalse(sfx.TensionActive, "no tension after the death");

                // After the death only on-screen spectator cues at -18 dB may play (no human, no haptics).
                for (int k = 0; k < cues.Count; k++)
                {
                    if (cueTicks[k] <= monitor.CaughtTick) continue;
                    Assert.That(cues[k].GainDb, Is.LessThanOrEqualTo(-18f), "after the death: " + cues[k].Id + " at tick " + cueTicks[k]);
                }
            }
            finally
            {
                Destroy(sfx);
            }
        }

        [Test]
        public void Sfx_CountdownTicksOncePerSecondOverTheLastTenSecondsThenOneJingle()
        {
            Sfx sfx = Sfx.Create(null);
            try
            {
                var config = new SimConfig { TickRate = 60, LassoEnabled = false, RoundDuration = 13.0 };
                var controllers = new IController[4];
                for (int i = 0; i < controllers.Length; i++) controllers[i] = new HomeCirclerController(StartOf(i));
                var session = new GameSession(config, new SimSetup { HumanIndex = 0 }, controllers, false);
                var cues = new List<SfxCue>();
                var cueTimes = new List<double>();
                sfx.CuePlayed += c =>
                {
                    cues.Add(c);
                    cueTimes.Add(session.Sim.Time);
                };
                sfx.Attach(session, GameState.Playing);
                int frames = 0;
                while (!session.Sim.Ended)
                {
                    session.Advance(Frame);
                    sfx.Tick(Frame);
                    Assert.Less(++frames, 5000, "runaway");
                }
                var ticks = new List<int>();
                for (int k = 0; k < cues.Count; k++)
                {
                    if (cues[k].Id == SfxId.CountdownTick) ticks.Add(k);
                }
                Assert.AreEqual(Sfx.CountdownSeconds, ticks.Count, "one tick per second over the last 10 s");
                for (int n = 0; n < ticks.Count; n++)
                {
                    int secondsLeft = Sfx.CountdownSeconds - n;
                    double t = cueTimes[ticks[n]];
                    Assert.That(t, Is.InRange(config.RoundDuration - secondsLeft - 0.05, config.RoundDuration - secondsLeft + 0.05),
                                "tick for " + secondsLeft + " s left at sim time " + t);
                    float pitch = secondsLeft <= Sfx.CountdownUrgentSeconds ? Sfx.CountdownUrgentPitch : 1f;
                    Assert.AreEqual(pitch, cues[ticks[n]].Pitch, 1e-6f, "pitch at " + secondsLeft + " s left");
                }

                int before = cues.Count;
                sfx.SetAttachedState(GameState.Results);
                sfx.SetAttachedState(GameState.Results);
                Assert.AreEqual(before + 1, cues.Count, "the jingle plays once");
                SfxId jingle = cues[cues.Count - 1].Id;
                Assert.IsTrue(jingle == SfxId.WinJingle || jingle == SfxId.LoseJingle, jingle.ToString());
                Assert.AreEqual(session.Sim.RankOf(0) == 1 ? SfxId.WinJingle : SfxId.LoseJingle, jingle);
            }
            finally
            {
                Destroy(sfx);
            }
        }

        [Test]
        public void Sfx_AttractMatchOnlyPlaysQuietSpectatorCues()
        {
            Sfx sfx = Sfx.Create(null);
            try
            {
                GameSession session = GameSession.CreateAttract(4242UL);
                var cues = new List<SfxCue>();
                var pulses = new List<int>();
                sfx.CuePlayed += c => cues.Add(c);
                sfx.HapticPulsed += ms => pulses.Add(ms);
                sfx.Attach(session, GameState.Menu);
                for (int f = 0; f < 60 * 25; f++)
                {
                    session.Advance(Frame);
                    sfx.Tick(Frame);
                    Assert.IsFalse(sfx.TensionActive, "no tension loop in attract");
                }
                foreach (SfxCue c in cues)
                {
                    Assert.AreEqual(SfxScope.SpectatorGainDb, c.GainDb, c.Id + " in attract");
                    Assert.AreNotEqual(SfxId.CountdownTick, c.Id);
                    Assert.AreNotEqual(SfxId.SparkLoop, c.Id);
                }
                Assert.AreEqual(0, pulses.Count, "no haptics in attract");
                sfx.SetAttachedState(GameState.Results);
                Assert.IsFalse(cues.Exists(c => c.Id == SfxId.WinJingle || c.Id == SfxId.LoseJingle), "no jingle for an attract match");
            }
            finally
            {
                Destroy(sfx);
            }
        }

        [Test]
        public void Sfx_EveryBiomeClipSetBuildsItsSlots()
        {
            foreach (BiomeId biome in new[] { BiomeId.Liquid, BiomeId.Fire, BiomeId.Electric })
            {
                ISfxClipSet set = Sfx.CreateClipSet(biome);
                Assert.AreEqual(biome, set.Biome);
                set.Build(SfxSynth.SampleRate);
                var owned = new List<AudioClip>();
                try
                {
                    foreach (SfxId id in AllClips())
                    {
                        AudioClip clip = Sfx.SlotClip(set, id);
                        if (!Sfx.IsBiomeSlot(id))
                        {
                            Assert.IsNull(clip, id + " is shared, not a biome slot");
                            continue;
                        }
                        Assert.IsNotNull(clip, biome + " " + id);
                        Assert.That(clip.samples, Is.GreaterThan(SfxSynth.SampleRate / 50), biome + " " + id + " length");
                        owned.Add(clip);
                    }
                    Assert.IsNotNull(set.LoopLost, biome + " has the contract 24 loop lost sound");
                    if (set.Ambient != null) owned.Add(set.Ambient);
                }
                finally
                {
                    foreach (AudioClip c in owned) Object.DestroyImmediate(c);
                }
            }
            Assert.IsTrue(Sfx.IsBiomeSlot(SfxId.LoopLost));
            Assert.IsFalse(Sfx.IsBiomeSlot(SfxId.UiClick), "UI sounds are shared by every biome");
            Assert.IsFalse(Sfx.IsBiomeSlot(SfxId.WinJingle));
        }

        [Test]
        public void Sfx_CuesDoNotDependOnTheBiome()
        {
            // The scope rules and the cue order are the same in every biome; only the clips change.
            Sfx sfx = Sfx.Create(null);
            try
            {
                BiomeTheme.SetCurrent(BiomeId.Electric);
                var cues = new List<SfxCue>();
                sfx.CuePlayed += c => cues.Add(c);
                Sfx.PlayUiClick();
                Assert.AreEqual(1, cues.Count);
                if (Application.isBatchMode) Assert.IsNull(sfx.CurrentSet, "hard-muted: no clip set is ever built");
                else Assert.AreEqual(BiomeId.Electric, sfx.CurrentSet.Biome, "the set follows BiomeTheme.Changed");
            }
            finally
            {
                BiomeTheme.SetCurrent(BiomeId.Liquid);
                Destroy(sfx);
            }
        }
        // ------------------------------------------------------------------------------------------------------------

        private static void Destroy(Sfx sfx)
        {
            if (sfx == null) return;
            sfx.Teardown();
            Object.DestroyImmediate(sfx.gameObject);
        }

        private static Vec2d StartOf(int i)
        {
            double d = Tuning.StartDiscOffset;
            switch (i)
            {
                case 0: return new Vec2d(-d, -d);
                case 1: return new Vec2d(d, -d);
                case 2: return new Vec2d(d, d);
                default: return new Vec2d(-d, d);
            }
        }

        private static int Count(List<SfxId> list, SfxId id)
        {
            int n = 0;
            foreach (SfxId x in list)
            {
                if (x == id) n++;
            }
            return n;
        }

        private static void AssertSubsequence(SfxId[] expected, List<SfxId> actual, string what)
        {
            int k = 0;
            foreach (SfxId id in actual)
            {
                if (k < expected.Length && id == expected[k]) k++;
            }
            Assert.AreEqual(expected.Length, k, what + ": expected the subsequence " + string.Join(",", expected)
                                                + " in " + string.Join(",", actual) + " (matched " + k + ")");
        }
    }
}
