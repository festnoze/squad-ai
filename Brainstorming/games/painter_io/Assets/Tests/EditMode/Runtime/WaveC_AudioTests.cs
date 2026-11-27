// Owned by the audio package (wave C). EditMode checks of the wave C audio fixes:
// - robust-03 / perf-07: the clip sets synthesized on a worker thread (ISplitSfxClipSet + SfxClipSetLoader, the path Sfx
//   uses for the other biomes at startup) have exactly the samples of the synchronous Build, deterministically, and a set
//   still loading is finished at once when its biome is picked;
// - feel-04: every clip keeps enough energy between 500 Hz and 4 kHz for a phone speaker (the docs/waveC/feel
//   audio_analyze measure: K-weighted loudness over the loudest 100 ms, before and after a 400 Hz 24 dB/oct high-pass):
//   at most 4 dB lost for a one-shot and 6 dB for a loop, win and lose jingles within 3 dB of each other, the fire fwump
//   and the electric return at least 12 dB apart (12-band profile), plus the clip constraints of every biome set (no NaN,
//   peak at most 0.95, one-shots end on an exact zero, loops join seamlessly);
// - feel-13: the human's elimination by territory loss pulses the 120 ms caught haptic once; a bot's pulses nothing.
// No test writes PlayerPrefs.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;
using Object = UnityEngine.Object;

namespace PainterIO.Tests
{
    public class WaveC_AudioTests
    {
        private const int Rate = SfxSynth.SampleRate;
        private const float Frame = 1f / 60f;

        private static readonly BiomeId[] Biomes = { BiomeId.Liquid, BiomeId.Fire, BiomeId.Electric };

        // ------------------------------------------------------------------------------------------------------------
        // robust-03 / perf-07: background synthesis.

        [Test]
        public void WaveC_EverySetIsSplitAndItsWorkerSamplesHashLikeTheSynchronousGenerators()
        {
            foreach (BiomeId biome in Biomes)
            {
                var split = Sfx.CreateClipSet(biome) as ISplitSfxClipSet;
                Assert.IsNotNull(split, biome + " implements ISplitSfxClipSet");
                SfxClipSamples worker = Task.Run(() => split.Synthesize(Rate)).Result;
                Assert.AreEqual(biome, worker.Biome);
                Assert.AreEqual(Rate, worker.SampleRate);
                for (int k = 0; k < SfxClipSamples.SlotCount; k++) Assert.IsNull(worker.ErrorOf((SfxSlot)k), biome + " " + (SfxSlot)k);
                Assert.AreEqual(GeneratorHash(biome), worker.Hash(), biome + ": worker samples == the synchronous generators");
                Assert.AreEqual(worker.Hash(), split.Synthesize(Rate).Hash(), biome + ": deterministic");
            }
        }

        [Test]
        public void WaveC_SetsSynthesizedInParallelOnWorkersAreIdentical()
        {
            // Three sets on three workers at once, twice: no shared mutable state between the synthesizers.
            var expected = new ulong[Biomes.Length];
            for (int i = 0; i < Biomes.Length; i++) expected[i] = GeneratorHash(Biomes[i]);
            for (int round = 0; round < 2; round++)
            {
                var tasks = new Task<SfxClipSamples>[Biomes.Length * 2];
                for (int i = 0; i < tasks.Length; i++)
                {
                    var split = (ISplitSfxClipSet)Sfx.CreateClipSet(Biomes[i % Biomes.Length]);
                    tasks[i] = Task.Run(() => split.Synthesize(Rate));
                }
                Task.WaitAll(tasks);
                for (int i = 0; i < tasks.Length; i++)
                {
                    Assert.AreEqual(expected[i % Biomes.Length], tasks[i].Result.Hash(), Biomes[i % Biomes.Length] + " round " + round);
                }
            }
        }

        [Test]
        public void WaveC_BackgroundBuiltFireAndElectricSetsHaveTheSamplesOfBuild()
        {
            var loader = new SfxClipSetLoader(BiomeTheme.Count);
            var background = new ISfxClipSet[BiomeTheme.Count];
            var owned = new List<AudioClip>();
            try
            {
                foreach (BiomeId biome in new[] { BiomeId.Fire, BiomeId.Electric })
                {
                    Assert.IsTrue(loader.Start((int)biome, (ISplitSfxClipSet)Sfx.CreateClipSet(biome), Rate), biome + " starts");
                    Assert.IsTrue(loader.IsPending((int)biome));
                }
                Assert.IsFalse(loader.IsPending((int)BiomeId.Liquid));
                Assert.IsFalse(loader.Start((int)BiomeId.Fire, new FireSfx(), Rate), "a busy index refuses a second set");

                // The main thread pumps one Step per "frame": at most one clip per call.
                var watch = Stopwatch.StartNew();
                int steps = 0;
                while (loader.AnyPending)
                {
                    ISfxClipSet done = loader.Step(out int index);
                    steps++;
                    if (done != null)
                    {
                        Assert.IsNull(background[index], "each set completes once");
                        background[index] = done;
                        Assert.IsNotNull(loader.LastSamples);
                        Assert.AreEqual((BiomeId)index, loader.LastSamples.Biome);
                    }
                    else Thread.Sleep(1);
                    Assert.Less(watch.ElapsedMilliseconds, 60000, "the background sets never completed");
                }
                Assert.That(steps, Is.GreaterThanOrEqualTo(2 * SfxClipSamples.SlotCount), "one clip per Step");

                foreach (BiomeId biome in new[] { BiomeId.Fire, BiomeId.Electric })
                {
                    ISfxClipSet bg = background[(int)biome];
                    Assert.IsNotNull(bg, biome + " completed");
                    owned.AddRange(ClipsOf(bg));
                    ISfxClipSet sync = Sfx.CreateClipSet(biome);
                    sync.Build(Rate);
                    owned.AddRange(ClipsOf(sync));
                    AudioClip[] a = ClipsOf(sync), b = ClipsOf(bg);
                    for (int k = 0; k < SfxClipSamples.SlotCount; k++)
                    {
                        string what = biome + " " + (SfxSlot)k;
                        Assert.IsNotNull(a[k], what + " (Build)");
                        Assert.IsNotNull(b[k], what + " (background)");
                        Assert.AreEqual(a[k].name, b[k].name, what + " name");
                        Assert.AreEqual(a[k].samples, b[k].samples, what + " length");
                        Assert.AreEqual(a[k].frequency, b[k].frequency, what + " rate");
                        Assert.AreEqual(1, b[k].channels, what + " mono");
                        var da = new float[a[k].samples];
                        var db = new float[b[k].samples];
                        if (a[k].GetData(da, 0) && b[k].GetData(db, 0))
                        {
                            Assert.AreEqual(SfxClipSamples.HashOf(da), SfxClipSamples.HashOf(db), what + ": same samples as Build");
                        }
                    }
                }
            }
            finally
            {
                foreach (AudioClip c in loader.Abandon()) owned.Add(c);
                DestroyAll(owned);
            }
        }

        [Test]
        public void WaveC_APendingSetPickedEarlyIsFinishedAtOnce()
        {
            var loader = new SfxClipSetLoader(BiomeTheme.Count);
            var owned = new List<AudioClip>();
            try
            {
                Assert.IsTrue(loader.Start((int)BiomeId.Electric, new ElectricSfx(), Rate));
                ISfxClipSet set = loader.Finish((int)BiomeId.Electric);   // the player picked Electricite right away
                Assert.IsNotNull(set);
                owned.AddRange(ClipsOf(set));
                Assert.IsFalse(loader.IsPending((int)BiomeId.Electric));
                Assert.IsFalse(loader.AnyPending);
                foreach (AudioClip c in ClipsOf(set)) Assert.IsNotNull(c, "every electric slot, the ambience included");
                Assert.IsNull(loader.Finish((int)BiomeId.Electric), "nothing pending any more");
                Assert.IsNull(loader.Step(out int index));
                Assert.AreEqual(-1, index);

                // Abandon (Sfx.Teardown) returns the clips a half-assembled set already made.
                Assert.IsTrue(loader.Start((int)BiomeId.Fire, new FireSfx(), Rate));
                Assert.AreEqual(0, loader.SlotsBuilt((int)BiomeId.Fire));
                var watch = Stopwatch.StartNew();
                while (loader.SlotsBuilt((int)BiomeId.Fire) < 3)
                {
                    int before = loader.SlotsBuilt((int)BiomeId.Fire);
                    Assert.IsNull(loader.Step(out _));
                    int after = loader.SlotsBuilt((int)BiomeId.Fire);
                    Assert.That(after - before, Is.InRange(0, 1), "at most one clip per Step");
                    if (after == before) Thread.Sleep(1);
                    Assert.Less(watch.ElapsedMilliseconds, 60000, "the fire set never produced clips");
                }
                List<AudioClip> partial = loader.Abandon();
                owned.AddRange(partial);
                Assert.AreEqual(3, partial.Count, "the three clips made so far");
                Assert.IsFalse(loader.AnyPending, "Abandon forgets the pending sets");
                Assert.AreEqual(-1, loader.SlotsBuilt((int)BiomeId.Fire));
            }
            finally
            {
                foreach (AudioClip c in loader.Abandon()) owned.Add(c);
                DestroyAll(owned);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // feel-04: phone speakers.

        [Test]
        public void WaveC_EveryClipKeepsItsLoudnessThroughAPhoneSpeaker()
        {
            var failures = new List<string>();
            foreach (Named c in AllClips())
            {
                double loss = PhoneLossDb(c.Samples);
                double limit = c.Loop ? 6.0 : 4.0;
                if (loss > limit) failures.Add(c.Name + " loses " + loss.ToString("0.0") + " dB (limit " + limit + ")");
            }
            Assert.IsEmpty(failures, string.Join("; ", failures));
        }

        [Test]
        public void WaveC_WinAndLoseJinglesAreEquallyLoudOnFullRangeAndOnAPhone()
        {
            float[] win = SfxSynth.Generate(SfxId.WinJingle), lose = SfxSynth.Generate(SfxId.LoseJingle);
            double gWin = 20.0 * Math.Log10(Sfx.BaseVolume(SfxId.WinJingle)), gLose = 20.0 * Math.Log10(Sfx.BaseVolume(SfxId.LoseJingle));
            double full = Math.Abs((MaxWindowLoudness(KWeight(win)) + gWin) - (MaxWindowLoudness(KWeight(lose)) + gLose));
            double phone = Math.Abs((MaxWindowLoudness(KWeight(Phone(win))) + gWin) - (MaxWindowLoudness(KWeight(Phone(lose))) + gLose));
            Assert.That(full, Is.LessThanOrEqualTo(3.0), "full-range loudness difference (dB)");
            Assert.That(phone, Is.LessThanOrEqualTo(3.0), "phone loudness difference (dB)");
        }

        [Test]
        public void WaveC_FireFwumpAndElectricReturnStayDistinct()
        {
            float[] fwump = FireSfx.Generate(FireSfx.Clip.Fwump, Rate);
            float[] thunk = ElectricSfx.Synthesize(ElectricSfx.Clip.Return, Rate);
            double full = ProfileDistance(BandProfile(fwump), BandProfile(thunk));
            double phone = ProfileDistance(BandProfile(Phone(fwump)), BandProfile(Phone(thunk)));
            Assert.That(full, Is.GreaterThanOrEqualTo(12.0), "12-band profile distance (dB)");
            Assert.That(phone, Is.GreaterThanOrEqualTo(12.0), "12-band profile distance after the phone high-pass (dB)");
        }

        [Test]
        public void WaveC_EveryBiomeClipIsCleanAndEveryLoopJoinsSeamlessly()
        {
            foreach (Named c in AllClips())
            {
                float[] x = c.Samples;
                float peak = 0f;
                double sum = 0.0, maxStep = 0.0;
                for (int i = 0; i < x.Length; i++)
                {
                    Assert.IsFalse(float.IsNaN(x[i]) || float.IsInfinity(x[i]), c.Name + " sample " + i);
                    peak = Math.Max(peak, Math.Abs(x[i]));
                    if (i == 0) continue;
                    double step = Math.Abs(x[i] - x[i - 1]);
                    sum += step;
                    maxStep = Math.Max(maxStep, step);
                }
                Assert.That(peak, Is.LessThanOrEqualTo(SfxSynth.PeakLimit), c.Name + " peak");
                Assert.That(peak, Is.GreaterThan(0.5f), c.Name + " is normalized");
                if (c.Loop)
                {
                    double join = Math.Abs(x[0] - x[x.Length - 1]);
                    Assert.That(join, Is.LessThanOrEqualTo(maxStep * 0.5), c.Name + ": the wrap is no harder than the loop's own steps");
                    Assert.That(join, Is.LessThan(sum / (x.Length - 1) * 6.0 + 1e-3), c.Name + ": join vs mean step");
                }
                else
                {
                    Assert.That(Math.Abs(x[0]), Is.LessThan(1e-4f), c.Name + " starts on silence");
                    Assert.AreEqual(0f, x[x.Length - 1], c.Name + " ends on an exact zero");
                }
            }
            Assert.AreEqual((int)Math.Round(4.0 * Rate), ElectricSfx.Synthesize(ElectricSfx.Clip.Ambient, Rate).Length, "the hum keeps its 4 s loop");
        }

        // ------------------------------------------------------------------------------------------------------------
        // feel-13: territory loss haptic.

        [Test]
        public void WaveC_HumanTerritoryLostEliminationPulsesTheCaughtHapticOnce()
        {
            List<int> pulses = RunTerritoryLoss(1, false, out List<SfxCue> cues, out SimEvent elim);
            Assert.IsNotNull(elim, "the scenario eliminates player 1");
            Assert.AreEqual(EliminationCause.TerritoryLost, elim.Cause);
            CollectionAssert.AreEqual(new[] { Haptics.CaughtMs }, pulses, "exactly one 120 ms pulse: " + string.Join(",", pulses));
            Assert.AreEqual(1, cues.FindAll(c => c.Id == SfxId.CaughtSplat && c.Player == 1 && c.GainDb >= -6f).Count, "one splat");
        }

        [Test]
        public void WaveC_BotTerritoryLostEliminationPulsesNothing()
        {
            // The human is an idle third player far away: the bot's death is only spectated.
            List<int> pulses = RunTerritoryLoss(2, true, out _, out SimEvent elim);
            Assert.IsNotNull(elim);
            Assert.AreEqual(EliminationCause.TerritoryLost, elim.Cause);
            Assert.IsEmpty(pulses, "no haptic for a bot's elimination: " + string.Join(",", pulses));

            // The human is the capturer: the capture pulse only, never the caught pulse.
            pulses = RunTerritoryLoss(0, false, out _, out elim);
            Assert.IsNotNull(elim);
            CollectionAssert.DoesNotContain(pulses, Haptics.CaughtMs, "pulses " + string.Join(",", pulses));
            CollectionAssert.Contains(pulses, Haptics.CaptureMs);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Helpers.

        /// <summary>
        /// The R9 territory-loss scenario (RulesTests.R9_ZeroCellsEliminatesWithFinalCellsBeforeTheCapture) as a live
        /// GameSession heard by a Sfx: player 0 returns with a trail enclosing all of player 1's territory at t = 0.349 s.
        /// human is the session's human index; withIdle adds an idle third player far away. Returns the haptic pulses.
        /// </summary>
        private static List<int> RunTerritoryLoss(int human, bool withIdle, out List<SfxCue> cues, out SimEvent elimination)
        {
            const double h = SimTestKit.H;
            var starts = new List<Vec2d> { SimTestKit.V(-4, h), SimTestKit.V(7 + h, -2.4375) };
            var headings = new List<double> { SimTestKit.West, SimTestKit.North };
            var controllers = new List<IController> { new ConstantHeadingController(SimTestKit.West), new ConstantHeadingController(SimTestKit.North) };
            Vec2d idle = SimTestKit.IdleCorners[0];
            if (withIdle)
            {
                starts.Add(idle);
                headings.Add(0.0);
                controllers.Add(new HomeCirclerController(idle));
            }
            var setup = new SimSetup
            {
                PlayerCount = starts.Count,
                StartPositions = starts.ToArray(),
                StartHeadings = headings.ToArray(),
                Territory = g =>
                {
                    SimTestKit.FillRect(g, 1, -8, -8, 0, 8);
                    SimTestKit.FillRect(g, 2, 6, -3, 9, 3);
                    if (withIdle) g.FillDisc(idle, Tuning.StartDiscRadius, 3);
                },
                HumanIndex = human,
            };
            var session = new GameSession(SimTestKit.Config(60), setup, controllers.ToArray(), false);
            session.Sim.DebugSetTrail(0, new[] { SimTestKit.V(0, 6 + h), SimTestKit.V(10 + h, 6 + h), SimTestKit.V(10 + h, -6 + h), SimTestKit.V(2.0925, -6 + h) });

            Sfx sfx = Sfx.Create(null);
            var pulses = new List<int>();
            var heard = new List<SfxCue>();
            SimEvent elim = null;
            try
            {
                sfx.CuePlayed += c => heard.Add(c);
                sfx.HapticPulsed += ms => pulses.Add(ms);
                session.EventRaised += e =>
                {
                    if (e.Type == SimEventType.Eliminated && e.Player == 1) elim = e;
                };
                sfx.Attach(session, GameState.Playing);
                for (int f = 0; f < 60 && session.Sim.Time < 0.6 && !session.IsClosed; f++)
                {
                    session.Advance(Frame);
                    sfx.Tick(Frame);
                }
            }
            finally
            {
                sfx.Teardown();
                Object.DestroyImmediate(sfx.gameObject);
            }
            cues = heard;
            elimination = elim;
            return pulses;
        }

        private struct Named
        {
            public string Name;
            public float[] Samples;
            public bool Loop;
        }

        private static IEnumerable<Named> AllClips()
        {
            foreach (SfxId id in Enum.GetValues(typeof(SfxId)))
                yield return new Named { Name = "L." + id, Samples = SfxSynth.Generate(id), Loop = SfxSynth.IsLoop(id) };
            foreach (FireSfx.Clip c in Enum.GetValues(typeof(FireSfx.Clip)))
                yield return new Named { Name = "F." + c, Samples = FireSfx.Generate(c, Rate), Loop = FireSfx.IsLoop(c) };
            foreach (ElectricSfx.Clip c in Enum.GetValues(typeof(ElectricSfx.Clip)))
                yield return new Named { Name = "E." + c, Samples = ElectricSfx.Synthesize(c, Rate), Loop = ElectricSfx.IsLoop(c) };
        }

        /// <summary>The hash a set's samples must have: its synchronous generators chained in slot order.</summary>
        private static ulong GeneratorHash(BiomeId biome)
        {
            var s = new SfxClipSamples(biome, Rate);
            for (int k = 0; k < SfxClipSamples.SlotCount; k++)
            {
                switch (biome)
                {
                    case BiomeId.Fire:
                        s.Set((SfxSlot)k, FireSfx.Generate((FireSfx.Clip)k, Rate));
                        break;
                    case BiomeId.Electric:
                        s.Set((SfxSlot)k, ElectricSfx.Synthesize((ElectricSfx.Clip)k, Rate));
                        break;
                    default:
                        SfxId? id = LiquidSfx.LiquidId((SfxSlot)k);
                        s.Set((SfxSlot)k, id.HasValue ? SfxSynth.Generate(id.Value) : null);
                        break;
                }
            }
            return s.Hash();
        }

        private static AudioClip[] ClipsOf(ISfxClipSet set)
        {
            return new[] { set.Exit, set.Return, set.Fill, set.Cut, set.TensionLoop, set.Caught, set.LoopLost, set.Ambient };
        }

        private static void DestroyAll(List<AudioClip> clips)
        {
            var seen = new HashSet<AudioClip>();
            foreach (AudioClip c in clips)
            {
                if (c != null && seen.Add(c)) Object.DestroyImmediate(c);
            }
            clips.Clear();
        }

        // The measure of docs/waveC/feel/tools/audio_analyze (BS.1770 K-weighting, loudest 100 ms window, small phone
        // speaker = two 400 Hz Butterworth high-pass biquads, 12 log bands from 60 Hz to 16 kHz).

        /// <summary>Loudness lost (dB) through the phone high-pass.</summary>
        private static double PhoneLossDb(float[] x)
        {
            return MaxWindowLoudness(KWeight(x)) - MaxWindowLoudness(KWeight(Phone(x)));
        }

        private static double[] KWeight(float[] x)
        {
            double fs = Rate;
            double gain = 3.999843853973347, q = 0.7071752369554196, fc = 1681.974450955533;
            double a = Math.Pow(10, gain / 40.0), w0 = 2 * Math.PI * fc / fs, alpha = Math.Sin(w0) / (2 * q);
            double b0 = a * ((a + 1) + (a - 1) * Math.Cos(w0) + 2 * Math.Sqrt(a) * alpha);
            double b1 = -2 * a * ((a - 1) + (a + 1) * Math.Cos(w0));
            double b2 = a * ((a + 1) + (a - 1) * Math.Cos(w0) - 2 * Math.Sqrt(a) * alpha);
            double a0 = (a + 1) - (a - 1) * Math.Cos(w0) + 2 * Math.Sqrt(a) * alpha;
            double a1 = 2 * ((a - 1) - (a + 1) * Math.Cos(w0));
            double a2 = (a + 1) - (a - 1) * Math.Cos(w0) - 2 * Math.Sqrt(a) * alpha;
            double[] y = Biquad(ToDouble(x), b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0);
            double fc2 = 38.13547087602444, q2 = 0.5003270373238773;
            double w2 = 2 * Math.PI * fc2 / fs, al2 = Math.Sin(w2) / (2 * q2);
            double hb0 = (1 + Math.Cos(w2)) / 2, hb1 = -(1 + Math.Cos(w2)), hb2 = (1 + Math.Cos(w2)) / 2;
            double ha0 = 1 + al2, ha1 = -2 * Math.Cos(w2), ha2 = 1 - al2;
            return Biquad(y, hb0 / ha0, hb1 / ha0, hb2 / ha0, ha1 / ha0, ha2 / ha0);
        }

        private static float[] Phone(float[] x)
        {
            double fc = 400, fs = Rate, q = 0.7071;
            double w = 2 * Math.PI * fc / fs, al = Math.Sin(w) / (2 * q);
            double b0 = (1 + Math.Cos(w)) / 2, b1 = -(1 + Math.Cos(w)), b2 = b0, a0 = 1 + al, a1 = -2 * Math.Cos(w), a2 = 1 - al;
            double[] y = Biquad(ToDouble(x), b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0);
            y = Biquad(y, b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0);
            var r = new float[y.Length];
            for (int i = 0; i < y.Length; i++) r[i] = (float)y[i];
            return r;
        }

        private static double[] ToDouble(float[] x)
        {
            var d = new double[x.Length];
            for (int i = 0; i < x.Length; i++) d[i] = x[i];
            return d;
        }

        private static double[] Biquad(double[] x, double b0, double b1, double b2, double a1, double a2)
        {
            var y = new double[x.Length];
            double x1 = 0, x2 = 0, y1 = 0, y2 = 0;
            for (int i = 0; i < x.Length; i++)
            {
                double v = b0 * x[i] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
                x2 = x1;
                x1 = x[i];
                y2 = y1;
                y1 = v;
                y[i] = v;
            }
            return y;
        }

        private static double MaxWindowLoudness(double[] k)
        {
            int w = Math.Max(1, (int)(0.1 * Rate));
            if (w > k.Length) w = k.Length;
            double s = 0;
            for (int i = 0; i < w; i++) s += k[i] * k[i];
            double best = s;
            for (int i = w; i < k.Length; i++)
            {
                s += k[i] * k[i] - k[i - w] * k[i - w];
                if (s > best) best = s;
            }
            return -0.691 + 10 * Math.Log10(best / w + 1e-20);
        }

        private static double[] BandProfile(float[] x)
        {
            const int n = 2048;
            var acc = new double[n / 2];
            for (int start = 0; start + n <= Math.Max(x.Length, n); start += n / 2)
            {
                var re = new double[n];
                var im = new double[n];
                for (int i = 0; i < n; i++)
                {
                    int j = start + i;
                    double v = j < x.Length ? x[j] : 0;
                    re[i] = v * (0.5 - 0.5 * Math.Cos(2 * Math.PI * i / (n - 1)));
                }
                Fft(re, im);
                for (int b = 0; b < n / 2; b++) acc[b] += re[b] * re[b] + im[b] * im[b];
                if (start + n >= x.Length) break;
            }
            var edges = new double[13];
            for (int i = 0; i <= 12; i++) edges[i] = 60 * Math.Pow(16000.0 / 60, i / 12.0);
            var bands = new double[12];
            double total = 0;
            for (int b = 1; b < n / 2; b++)
            {
                double f = b * (double)Rate / n;
                total += acc[b];
                for (int k = 0; k < 12; k++)
                {
                    if (f >= edges[k] && f < edges[k + 1]) bands[k] += acc[b];
                }
            }
            for (int k = 0; k < 12; k++) bands[k] = 10 * Math.Log10(bands[k] / total + 1e-9);
            return bands;
        }

        private static void Fft(double[] re, double[] im)
        {
            int n = re.Length;
            for (int i = 1, j = 0; i < n; i++)
            {
                int bit = n >> 1;
                for (; (j & bit) != 0; bit >>= 1) j ^= bit;
                j ^= bit;
                if (i < j)
                {
                    double tr = re[i]; re[i] = re[j]; re[j] = tr;
                    double ti = im[i]; im[i] = im[j]; im[j] = ti;
                }
            }
            for (int len = 2; len <= n; len <<= 1)
            {
                double ang = -2 * Math.PI / len, wr = Math.Cos(ang), wi = Math.Sin(ang);
                for (int i = 0; i < n; i += len)
                {
                    double cr = 1, ci = 0;
                    for (int j = 0; j < len / 2; j++)
                    {
                        int p = i + j, q = i + j + len / 2;
                        double vr = re[q] * cr - im[q] * ci, vi = re[q] * ci + im[q] * cr;
                        re[q] = re[p] - vr;
                        im[q] = im[p] - vi;
                        re[p] += vr;
                        im[p] += vi;
                        double nr = cr * wr - ci * wi;
                        ci = cr * wi + ci * wr;
                        cr = nr;
                    }
                }
            }
        }

        private static double ProfileDistance(double[] a, double[] b)
        {
            double s = 0;
            for (int i = 0; i < a.Length; i++) s += (a[i] - b[i]) * (a[i] - b[i]);
            return Math.Sqrt(s / a.Length);
        }
    }
}
