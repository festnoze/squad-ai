// Owned by BI (wave B-2), by the audio package since wave C: B5's liquid clips moved behind ISfxClipSet (contract 25.2).
// The synthesis itself stays in SfxSynth (deterministic, pure C#); this set only builds and holds the AudioClips of the
// biome slots. Wave C: ISplitSfxClipSet, so Sfx can synthesize the set on a worker thread and make the clips later.
using System;
using System.Diagnostics;
using UnityEngine;

namespace PainterIO.Runtime
{
    public class LiquidSfx : ISplitSfxClipSet
    {
        public virtual BiomeId Biome => BiomeId.Liquid;

        public AudioClip Exit { get; protected set; }
        public AudioClip Return { get; protected set; }
        public AudioClip Fill { get; protected set; }
        public AudioClip Cut { get; protected set; }
        public AudioClip TensionLoop { get; protected set; }
        public AudioClip Caught { get; protected set; }
        public AudioClip LoopLost { get; protected set; }
        public AudioClip Ambient { get; protected set; }

        /// <summary>
        /// Builds every slot now: BuildSlot of each slot of Synthesize(sampleRate). A clip that fails stays null and is
        /// logged; the others still play.
        /// </summary>
        public virtual void Build(int sampleRate)
        {
            SfxClipSamples samples = Synthesize(sampleRate);
            for (int k = 0; k < SfxClipSamples.SlotCount; k++) BuildSlot(samples, (SfxSlot)k);
        }

        /// <summary>
        /// The liquid samples (always at SfxSynth.SampleRate: the DSP is written for 44.1 kHz). Pure C#, thread-safe; the
        /// liquid set has no ambience.
        /// </summary>
        public virtual SfxClipSamples Synthesize(int sampleRate)
        {
            var samples = new SfxClipSamples(BiomeId.Liquid, SfxSynth.SampleRate);
            Stopwatch watch = Stopwatch.StartNew();
            for (int k = 0; k < SfxClipSamples.SlotCount; k++)
            {
                var slot = (SfxSlot)k;
                SfxId? id = LiquidId(slot);
                if (!id.HasValue) continue;
                try
                {
                    samples.Set(slot, SfxSynth.Generate(id.Value));
                }
                catch (Exception e)
                {
                    samples.SetError(slot, e.ToString());
                }
            }
            samples.SynthMilliseconds = watch.ElapsedMilliseconds;
            return samples;
        }

        /// <summary>Main thread: the AudioClip of one liquid slot ("pio_&lt;SfxId&gt;", like SfxSynth.CreateClip).</summary>
        public virtual void BuildSlot(SfxClipSamples samples, SfxSlot slot)
        {
            if (samples == null) return;
            SfxId? id = LiquidId(slot);
            Assign(slot, id.HasValue ? samples.MakeClip(slot, "pio_" + id.Value) : null);
        }

        /// <summary>The SfxSynth clip of a liquid slot (null for the ambience: the liquid set has none).</summary>
        public static SfxId? LiquidId(SfxSlot slot)
        {
            switch (slot)
            {
                case SfxSlot.Exit: return SfxId.ExitPlop;
                case SfxSlot.Return: return SfxId.ReturnGloop;
                case SfxSlot.Fill: return SfxId.FillSwell;
                case SfxSlot.Cut: return SfxId.CutSnap;
                case SfxSlot.TensionLoop: return SfxId.SparkLoop;
                case SfxSlot.Caught: return SfxId.CaughtSplat;
                case SfxSlot.LoopLost: return SfxId.LoopLost;
                default: return null;
            }
        }

        /// <summary>Stores the clip of a slot.</summary>
        protected void Assign(SfxSlot slot, AudioClip clip)
        {
            switch (slot)
            {
                case SfxSlot.Exit: Exit = clip; break;
                case SfxSlot.Return: Return = clip; break;
                case SfxSlot.Fill: Fill = clip; break;
                case SfxSlot.Cut: Cut = clip; break;
                case SfxSlot.TensionLoop: TensionLoop = clip; break;
                case SfxSlot.Caught: Caught = clip; break;
                case SfxSlot.LoopLost: LoopLost = clip; break;
                default: Ambient = clip; break;
            }
        }
    }
}
