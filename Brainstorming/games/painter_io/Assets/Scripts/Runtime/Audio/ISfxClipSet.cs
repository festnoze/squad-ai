// Owned by BI (wave B-2), by the audio package since wave C. Contract 25.2: the biome-specific sounds, one implementation
// per biome (LiquidSfx, FireSfx, ElectricSfx). Sfx plays the current biome's set; the UI sounds (clicks, toast ticks,
// countdown, ring chime, lasso zip, jingles) are shared by every biome and stay in Sfx. Clips are synthesized at startup
// (no audio assets) and Sfx destroys them when it is torn down.
// Wave C (robust-03, perf-07), additive to 25.2: every set also implements ISplitSfxClipSet, which splits Build in two so
// Sfx can synthesize the sets of the other biomes on a worker thread at startup (Synthesize: pure C#, thread-safe) and make
// their AudioClips on the main thread later (BuildSlot, one clip at a time). Build(rate) is exactly every BuildSlot of
// Synthesize(rate), so both paths give the same samples.
// Wave D-2 (traits-infra, docs/BIOME_TRAITS.md section 5), additive: the optional Grow clip (the human's own territory
// growth from Propagation, played at -18 dB). It is the extra slot SfxSlot.Grow, after the eight base slots: SlotCount
// (and SfxClipSamples.Hash) still cover the eight base slots only; AllSlotCount counts the extra slot too, and Build /
// the background loader make it last.
using System;
using UnityEngine;

namespace PainterIO.Runtime
{
    public interface ISfxClipSet
    {
        BiomeId Biome { get; }

        /// <summary>The pearl leaves its territory (liquid: droplet plop).</summary>
        AudioClip Exit { get; }

        /// <summary>The pearl merges back home (liquid: gloop).</summary>
        AudioClip Return { get; }

        /// <summary>The fill wave of a capture (liquid: swell).</summary>
        AudioClip Fill { get; }

        /// <summary>A thread is cut (liquid: snap).</summary>
        AudioClip Cut { get; }

        /// <summary>The human's chase loop (seamless; Sfx raises its pitch as SparkCatchEta drops).</summary>
        AudioClip TensionLoop { get; }

        /// <summary>The spark catches the human (liquid: splat).</summary>
        AudioClip Caught { get; }

        /// <summary>Contract 24: a saved chased return captures nothing; this soft sound replaces the fill swell.</summary>
        AudioClip LoopLost { get; }

        /// <summary>Background ambience loop (null for Liquid).</summary>
        AudioClip Ambient { get; }

        /// <summary>
        /// Wave D-2 (optional, BIOME_TRAITS 5): the human's own territory growth (Propagation): a soft creep / crackle that
        /// Sfx plays at -18 dB, rate limited. Null when the set has none.
        /// </summary>
        AudioClip Grow { get; }

        /// <summary>Synthesizes the clips (called once by Sfx; sampleRate is SfxSynth.SampleRate).</summary>
        void Build(int sampleRate);
    }

    /// <summary>The eight slots of a clip set, in ISfxClipSet order (index into SfxClipSamples).</summary>
    public enum SfxSlot
    {
        Exit = 0,
        Return = 1,
        Fill = 2,
        Cut = 3,
        TensionLoop = 4,
        Caught = 5,
        LoopLost = 6,
        Ambient = 7,

        /// <summary>Wave D-2: the optional Grow clip, an extra slot after the eight base slots (outside SlotCount and Hash).</summary>
        Grow = 8,
    }

    /// <summary>
    /// Wave C, additive to contract 25.2: a clip set whose Build is split in two. Synthesize is pure C# (no UnityEngine
    /// API, no shared mutable state), so a worker thread may run it; BuildSlot makes one AudioClip from its samples and
    /// must run on the main thread. Build(rate) equals BuildSlot of every slot of Synthesize(rate).
    /// </summary>
    public interface ISplitSfxClipSet : ISfxClipSet
    {
        /// <summary>The samples of every slot (thread-safe, deterministic; a slot that fails keeps its error instead).</summary>
        SfxClipSamples Synthesize(int sampleRate);

        /// <summary>Main thread: makes the AudioClip of one slot from samples (a failed or empty slot stays null, logged).</summary>
        void BuildSlot(SfxClipSamples samples, SfxSlot slot);
    }

    /// <summary>
    /// The raw samples of one clip set (wave C). Pure data with no UnityEngine object, so a worker thread can fill it; the
    /// AudioClips are made from it on the main thread (ISplitSfxClipSet.BuildSlot).
    /// </summary>
    public sealed class SfxClipSamples
    {
        /// <summary>Number of base SfxSlot values (Exit .. Ambient): the slots of contract 25.2 and of Hash().</summary>
        public const int SlotCount = 8;

        /// <summary>Wave D-2: base slots plus the extra slots (SfxSlot.Grow); Build and the loader make all of them.</summary>
        public const int AllSlotCount = 9;

        private const ulong FnvOffset = 14695981039346656037UL;
        private const ulong FnvPrime = 1099511628211UL;

        private readonly float[][] data = new float[AllSlotCount][];
        private readonly string[] errors = new string[AllSlotCount];

        public SfxClipSamples(BiomeId biome, int sampleRate)
        {
            Biome = biome;
            SampleRate = sampleRate;
        }

        public BiomeId Biome { get; }

        /// <summary>Sample rate of every slot (mono).</summary>
        public int SampleRate { get; }

        /// <summary>Wall-clock milliseconds the synthesis took (log only).</summary>
        public long SynthMilliseconds { get; set; }

        /// <summary>The samples of a slot; null when the set has no such clip (Liquid Ambient) or its synthesis failed.</summary>
        public float[] Get(SfxSlot slot)
        {
            return data[(int)slot];
        }

        public void Set(SfxSlot slot, float[] samples)
        {
            data[(int)slot] = samples;
        }

        /// <summary>Why the synthesis of a slot failed, null when it did not.</summary>
        public string ErrorOf(SfxSlot slot)
        {
            return errors[(int)slot];
        }

        public void SetError(SfxSlot slot, string error)
        {
            errors[(int)slot] = error;
        }

        /// <summary>
        /// FNV-1a 64 over every base slot's sample bit patterns (slot order, empty slots included): a determinism check.
        /// The extra slots (Grow) are not included, so the wave C hashes stay valid.
        /// </summary>
        public ulong Hash()
        {
            ulong h = FnvOffset;
            for (int k = 0; k < SlotCount; k++) h = HashOf(data[k], h);
            return h;
        }

        /// <summary>FNV-1a 64 of a sample buffer's length and bit patterns, chained from h (null hashes as length -1).</summary>
        public static ulong HashOf(float[] samples, ulong h = FnvOffset)
        {
            h = Mix(h, samples != null ? samples.Length : -1);
            if (samples == null) return h;
            for (int i = 0; i < samples.Length; i++) h = Mix(h, BitConverter.SingleToInt32Bits(samples[i]));
            return h;
        }

        /// <summary>Main thread: a mono AudioClip of samples (throws when Unity refuses it).</summary>
        public static AudioClip CreateClip(string name, float[] samples, int sampleRate)
        {
            if (samples == null || samples.Length == 0) throw new InvalidOperationException("no samples for " + name);
            AudioClip clip = AudioClip.Create(name, samples.Length, 1, sampleRate, false);
            if (clip == null) throw new InvalidOperationException("AudioClip.Create returned null for " + name);
            if (!clip.SetData(samples, 0)) throw new InvalidOperationException("AudioClip.SetData failed for " + name);
            return clip;
        }

        /// <summary>
        /// Main thread: the AudioClip of one slot named name, or null (logged as an error) when its synthesis failed or
        /// Unity refused it. A slot the set does not have (no samples, no error) is null without a log.
        /// </summary>
        public AudioClip MakeClip(SfxSlot slot, string name)
        {
            string error = ErrorOf(slot);
            float[] samples = Get(slot);
            if (error == null && samples == null) return null;
            try
            {
                if (error != null) throw new InvalidOperationException(error);
                return CreateClip(name, samples, SampleRate);
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] Sfx clip " + name + " failed: " + e.Message);
                return null;
            }
        }

        private static ulong Mix(ulong h, int value)
        {
            uint v = unchecked((uint)value);
            for (int b = 0; b < 4; b++)
            {
                h ^= (v >> (8 * b)) & 0xFFUL;
                h *= FnvPrime;
            }
            return h;
        }
    }
}
