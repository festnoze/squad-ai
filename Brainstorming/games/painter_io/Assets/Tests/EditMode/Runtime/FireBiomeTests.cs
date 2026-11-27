// Owned by FIRE (wave B-2, phase 2). EditMode checks of the Feu biome's pure parts (contract 25.2, 25.3, 25.5): the fire
// sound set (FireSfx) synthesizes every clip with its expected length, no NaN, a peak at most SfxSynth.PeakLimit, a clean
// start and an exact zero at the end of the one-shots, seamless loops (fuse hiss, crackle ambience) and deterministic
// samples; it fills every biome slot including the ambience; and the FireFx particle cap is the contract's 200.
// The shaders and the look are judged on player screenshots (DevShot / probe), not here.
using System;
using NUnit.Framework;
using PainterIO.Runtime;
using UnityEngine;
using Object = UnityEngine.Object;

namespace PainterIO.Tests
{
    public class FireBiomeTests
    {
        private static FireSfx.Clip[] AllClips()
        {
            return (FireSfx.Clip[])Enum.GetValues(typeof(FireSfx.Clip));
        }

        [Test]
        public void Fire_SfxClipsHaveTheirLengthNoNaNAndAPeakAtMostTheLimit()
        {
            Assert.AreEqual(FireSfx.ClipCount, AllClips().Length);
            foreach (FireSfx.Clip c in AllClips())
            {
                float[] x = FireSfx.Generate(c, SfxSynth.SampleRate);
                Assert.AreEqual(FireSfx.SampleCount(c, SfxSynth.SampleRate), x.Length, c + " length");
                Assert.That(x.Length, Is.GreaterThan(SfxSynth.SampleRate / 50), c + " is not trivially short");
                float peak = 0f;
                foreach (float v in x)
                {
                    Assert.IsFalse(float.IsNaN(v) || float.IsInfinity(v), c + " has a NaN or infinite sample");
                    peak = Mathf.Max(peak, Mathf.Abs(v));
                }
                Assert.That(peak, Is.LessThanOrEqualTo(SfxSynth.PeakLimit), c + " peak");
                Assert.That(peak, Is.GreaterThan(0.5f), c + " is normalized, not silent");
                if (!FireSfx.IsLoop(c))
                {
                    Assert.That(Mathf.Abs(x[0]), Is.LessThan(0.05f), c + " starts cleanly");
                    Assert.AreEqual(0f, x[x.Length - 1], c + " ends on an exact zero");
                }
            }
        }

        [Test]
        public void Fire_LoopsJoinSeamlessly()
        {
            foreach (FireSfx.Clip c in new[] { FireSfx.Clip.FuseHiss, FireSfx.Clip.Crackle })
            {
                Assert.IsTrue(FireSfx.IsLoop(c));
                float[] x = FireSfx.Generate(c, SfxSynth.SampleRate);
                // The step across the loop point is no larger than the steps the clip already makes inside itself.
                double sum = 0.0;
                for (int i = 1; i < x.Length; i++) sum += Math.Abs(x[i] - x[i - 1]);
                double meanStep = sum / (x.Length - 1);
                double join = Math.Abs(x[0] - x[x.Length - 1]);
                Assert.That(join, Is.LessThan(meanStep * 6.0 + 1e-3), c + " join step " + join + " vs mean step " + meanStep);
            }
            Assert.AreEqual(0.5, FireSfx.DurationOf(FireSfx.Clip.FuseHiss), 1e-9, "the fuse hiss loops like the liquid spark loop");
        }

        [Test]
        public void Fire_SfxIsDeterministic()
        {
            foreach (FireSfx.Clip c in AllClips())
            {
                float[] a = FireSfx.Generate(c, SfxSynth.SampleRate);
                float[] b = FireSfx.Generate(c, SfxSynth.SampleRate);
                CollectionAssert.AreEqual(a, b, c + " is deterministic");
            }
        }

        [Test]
        public void Fire_ClipSetFillsEverySlotAndHasAnAmbience()
        {
            var set = new FireSfx();
            Assert.AreEqual(BiomeId.Fire, set.Biome);
            set.Build(SfxSynth.SampleRate);
            AudioClip[] clips = { set.Exit, set.Return, set.Fill, set.Cut, set.TensionLoop, set.Caught, set.LoopLost, set.Ambient };
            try
            {
                foreach (AudioClip clip in clips) Assert.IsNotNull(clip);
                Assert.AreEqual(FireSfx.SampleCount(FireSfx.Clip.Whoosh, SfxSynth.SampleRate), set.Fill.samples);
                Assert.That(set.Fill.length, Is.GreaterThan(BiomeTheme.Get(BiomeId.Fire).FillDuration), "the whoosh covers the fire fill");
                Assert.AreEqual(SfxSynth.SampleRate, set.Ambient.frequency);
            }
            finally
            {
                foreach (AudioClip clip in clips) if (clip != null) Object.DestroyImmediate(clip);
            }
            Assert.IsInstanceOf<FireSfx>(Sfx.CreateClipSet(BiomeId.Fire));
        }

        [Test]
        public void Fire_EffectsRespectTheParticleCap()
        {
            Assert.That(FireFx.MaxParticles, Is.LessThanOrEqualTo(200), "contract 25.5 particle cap");
            Assert.AreEqual(1.0f, FireFx.EmberCoolSeconds, 1e-6f, "contract 25.3: embers cool to ash over 1 s");
            Assert.AreEqual(typeof(FireFx), BiomeFx.ComponentTypeOf(BiomeId.Fire));
        }
    }
}
