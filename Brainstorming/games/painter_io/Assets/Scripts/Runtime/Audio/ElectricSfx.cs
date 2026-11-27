// Owned by ELEC (wave B-2, phase 2). Contract 25.4 sounds of the Électricité biome, synthesized at startup (no audio
// assets, deterministic, pure C# DSP in doubles like SfxSynth): a low mains hum ambience, a spark tick on exit, a power
// "thunk" on return, a crackle burst on fill, a zap on cut, a rising buzz tension loop (seamless; Sfx raises its pitch as
// SparkCatchEta drops), a discharge on catch and a fizzle for the contract 24 loop lost (the dead wire fizzles out).
// Buzzy tones are soft-clipped sines and band-limited harmonic stacks (no aliasing), crackles are short band-passed
// noise impulses. Every one-shot fades in and out to an exact zero and is normalized to SfxSynth.PeakTarget; the loops
// (tension, ambience) only contain components periodic over their length, so they join seamlessly.
// Wave C (audio package): Synthesize / BuildSlot of ISplitSfxClipSet (worker-thread synthesis, robust-03), and feel-04: the
// return thunk is driven harder with a 2 kHz contact click, and the ambience is a 120 Hz buzz with 240 to 960 Hz partials,
// so a phone speaker plays them (at most 4 dB lost for a one-shot, 6 dB for a loop).
using System;
using UnityEngine;

namespace PainterIO.Runtime
{
    public class ElectricSfx : LiquidSfx
    {
        /// <summary>The clips of the electric set (ElectricSfx.Synthesize).</summary>
        public enum Clip { Exit = 0, Return = 1, Fill = 2, Cut = 3, TensionLoop = 4, Caught = 5, LoopLost = 6, Ambient = 7 }

        /// <summary>Length of the seamless tension loop (every tonal component is a multiple of 2 Hz).</summary>
        public const double TensionLoopSeconds = 0.5;

        /// <summary>Length of the seamless ambience loop (every component is a multiple of 0.25 Hz).</summary>
        public const double AmbientLoopSeconds = 4.0;

        /// <summary>Peak of the ambience loop (softer than the one-shots; Sfx also plays it at Sfx.AmbientVolume).</summary>
        public const float AmbientPeak = 0.6f;

        private static readonly double[] Durations = { 0.14, 0.30, 0.48, 0.22, TensionLoopSeconds, 0.65, 0.62, AmbientLoopSeconds };

        private const double TwoPi = 2.0 * Math.PI;

        public override BiomeId Biome => BiomeId.Electric;

        /// <summary>
        /// The samples of the eight electric clips (pure C#, thread-safe; slot k is Clip k). LiquidSfx.Build makes the
        /// clips from them (a clip that fails stays null and is logged; the others still play).
        /// </summary>
        public override SfxClipSamples Synthesize(int sampleRate)
        {
            int rate = sampleRate > 8000 ? sampleRate : SfxSynth.SampleRate;
            var samples = new SfxClipSamples(BiomeId.Electric, rate);
            System.Diagnostics.Stopwatch watch = System.Diagnostics.Stopwatch.StartNew();
            for (int k = 0; k < SfxClipSamples.SlotCount; k++)
            {
                try
                {
                    samples.Set((SfxSlot)k, Synthesize((Clip)k, rate));
                }
                catch (Exception e)
                {
                    samples.SetError((SfxSlot)k, e.ToString());
                }
            }
            samples.SynthMilliseconds = watch.ElapsedMilliseconds;
            return samples;
        }

        /// <summary>Main thread: the AudioClip "pio_electric_&lt;Clip&gt;" of one slot.</summary>
        public override void BuildSlot(SfxClipSamples samples, SfxSlot slot)
        {
            if (samples == null) return;
            Assign(slot, samples.MakeClip(slot, "pio_electric_" + (Clip)(int)slot));
        }

        /// <summary>Duration of a clip in seconds.</summary>
        public static double DurationOf(Clip clip)
        {
            return Durations[(int)clip];
        }

        /// <summary>True for the clips played with loop = true.</summary>
        public static bool IsLoop(Clip clip)
        {
            return clip == Clip.TensionLoop || clip == Clip.Ambient;
        }

        /// <summary>Synthesizes one clip (deterministic: the same samples on every call and platform).</summary>
        public static float[] Synthesize(Clip clip, int sampleRate)
        {
            int rate = sampleRate > 8000 ? sampleRate : SfxSynth.SampleRate;
            var b = new double[(int)Math.Round(Durations[(int)clip] * rate)];
            var s = new Synth(rate);
            switch (clip)
            {
                case Clip.Exit: return s.ExitTick(b);
                case Clip.Return: return s.ReturnThunk(b);
                case Clip.Fill: return s.FillCrackle(b);
                case Clip.Cut: return s.CutZap(b);
                case Clip.TensionLoop: return s.TensionBuzz(b);
                case Clip.Caught: return s.CaughtDischarge(b);
                case Clip.LoopLost: return s.LoopLostFizzle(b);
                case Clip.Ambient: return s.AmbientHum(b);
                default: throw new ArgumentOutOfRangeException(nameof(clip), clip, "unknown clip");
            }
        }

        // ------------------------------------------------------------------------------------------------------------

        /// <summary>The DSP of the electric clips at one sample rate.</summary>
        private sealed class Synth
        {
            private readonly int rate;

            public Synth(int sampleRate)
            {
                rate = sampleRate;
            }

            // Exit: a short spark tick and a buzzy blip that jumps up (the orb leaves the field).
            public float[] ExitTick(double[] b)
            {
                AddBuzz(b, 0.0, 520, 1500, 0.04, 0.0008, 0.03, 0.8, 2.5);
                AddBuzz(b, 0.0, 180, 240, 0.02, 0.001, 0.02, 0.3, 1.2);
                AddCrackle(b, 0.0, 0.004, 1, 0xE7171UL, 0.5, 5200, 2.0);
                LowPass(b, 7500, false);
                return Finish(b, 0.03, 0.8, false, SfxSynth.PeakTarget);
            }

            // Return: a power connect, a low thunk with a short buzzy rise and bright sparks. Feel-04: the thunk is driven
            // hard (odd harmonics up to about 1 kHz) and a 2 kHz click marks the contact, so a phone speaker plays it;
            // the 4 to 6 kHz sparks keep it distinct from the fire fwump.
            public float[] ReturnThunk(double[] b)
            {
                AddBuzz(b, 0.0, 150, 85, 0.06, 0.002, 0.075, 0.55, 3.0);
                AddBuzz(b, 0.01, 380, 820, 0.05, 0.002, 0.05, 0.7, 3.0);
                AddCrackle(b, 0.0, 0.08, 9, 0x2E7UL, 0.6, 4800, 1.6);
                AddCrackle(b, 0.0, 0.03, 3, 0x2E8UL, 0.45, 2200, 1.4);
                LowPass(b, 8000, false);
                return Finish(b, 0.06, 1.2, false, SfxSynth.PeakTarget);
            }

            // Fill: a crackle burst (dense band-passed impulses thinning out) over a bright zap rising with the discharge
            // and a short 120 Hz buzz swell.
            public float[] FillCrackle(double[] b)
            {
                int n = b.Length;
                double dur = (double)n / rate;
                AddCrackle(b, 0.0, 0.30, 70, 0xF111EUL, 1.0, 3800, 1.4);
                AddCrackle(b, 0.02, 0.22, 25, 0xF1A2EUL, 0.6, 7200, 2.2);
                double phase = 0.0, phaseB = 0.0;
                for (int i = 0; i < n; i++)
                {
                    double t = (double)i / rate;
                    double env = Swell(t, 0.06, Math.Min(dur, 0.36));
                    double f = 300.0 * Math.Pow(1300.0 / 300.0, Math.Min(1.0, t / 0.25));
                    phase += TwoPi * f / rate;
                    phaseB += TwoPi * 120.0 / rate;
                    double zap = Math.Tanh(3.0 * Math.Sin(phase)) * 0.18;
                    double buzz = Harmonics(phaseB, 8) * 0.22;
                    b[i] += env * (zap + buzz);
                }
                LowPass(b, 8000, false);
                return Finish(b, 0.08, 2.2, false, SfxSynth.PeakTarget);
            }

            // Cut: a zap, a fast buzzy sweep down with a white snap at the impact.
            public float[] CutZap(double[] b)
            {
                int n = b.Length;
                var noise = new Noise(0xC0751UL);
                var high = new Svf();
                for (int i = 0; i < n; i++)
                {
                    double t = (double)i / rate;
                    high.Process(noise.Next(), 3000, 0.7, rate, out _, out _, out double hp);
                    b[i] += 0.8 * hp * Math.Exp(-t / 0.006);
                }
                AddBuzz(b, 0.0, 3200, 240, 0.07, 0.0005, 0.055, 1.0, 3.5);
                AddBuzz(b, 0.0, 1600, 160, 0.09, 0.0008, 0.07, 0.4, 2.0);
                AddCrackle(b, 0.01, 0.12, 8, 0xC07AUL, 0.4, 5000, 2.0);
                LowPass(b, 10000, false);
                return Finish(b, 0.05, 1.6, false, SfxSynth.PeakTarget);
            }

            // Tension loop: a rising buzz. A 110 Hz band-limited saw (55 cycles per loop) and a quiet 880 Hz whine, pulsed
            // twice per loop (4 Hz at pitch 1, like the liquid loop), with wrapped crackles. Seamless.
            public float[] TensionBuzz(double[] b)
            {
                int n = b.Length;
                const int pulses = 2;
                int period = n / pulses;
                var crackle = new double[n];
                AddCrackleWrapped(crackle, 26, 0x7E45UL, 4200, 1.5);
                for (int i = 0; i < n; i++)
                {
                    double t = (double)i / rate;
                    double since = (double)(i % period) / rate;
                    double pulse = 0.55 + 0.45 * Envelope(since, 0.004, 0.07);
                    double saw = Harmonics(TwoPi * 110.0 * t, 14);
                    double whine = Math.Sin(TwoPi * 880.0 * t) * 0.06 + Math.Sin(TwoPi * 1762.0 * t) * 0.025;
                    double hum = Math.Sin(TwoPi * 220.0 * t) * 0.12;
                    b[i] = pulse * (0.32 * saw + hum) + whine + 0.55 * crackle[i];
                }
                LowPass(b, 6500, true);
                return Finish(b, 0.0, 0.9, true, SfxSynth.PeakTarget);
            }

            // Caught: the discharge. A burst of noise closing down, a heavy buzzy drop and a crackle tail.
            public float[] CaughtDischarge(double[] b)
            {
                int n = b.Length;
                var noise = new Noise(0xD15CUL);
                var low = new Svf();
                for (int i = 0; i < n; i++)
                {
                    double t = (double)i / rate;
                    double fc = 400.0 + 6000.0 * Math.Exp(-t / 0.05);
                    low.Process(noise.Next(), fc, 0.9, rate, out double lp, out _, out _);
                    b[i] += 0.9 * lp * Envelope(t, 0.001, 0.08);
                }
                AddBuzz(b, 0.0, 900, 55, 0.18, 0.001, 0.13, 1.0, 2.8);
                AddBuzz(b, 0.0, 120, 45, 0.2, 0.002, 0.16, 0.6, 1.3);
                AddCrackle(b, 0.05, 0.45, 30, 0xCA7CUL, 0.6, 4500, 1.8);
                LowPass(b, 7000, false);
                return Finish(b, 0.1, 1.5, false, SfxSynth.PeakTarget);
            }

            // Loop lost (contract 24): the dead wire fizzles out. Thinning, fading crackles over a soft power-down whine.
            public float[] LoopLostFizzle(double[] b)
            {
                int n = b.Length;
                double phase = 0.0;
                for (int i = 0; i < n; i++)
                {
                    double t = (double)i / rate;
                    double f = 120.0 + 620.0 * Math.Exp(-t / 0.18);
                    phase += TwoPi * f / rate;
                    double env = t < 0.03 ? 0.5 - 0.5 * Math.Cos(Math.PI * t / 0.03) : Math.Exp(-(t - 0.03) / 0.22);
                    b[i] += env * (Math.Tanh(1.8 * Math.Sin(phase)) * 0.35 + Math.Sin(2.0 * phase) * 0.08);
                }
                var thin = new double[n];
                AddCrackle(thin, 0.0, 0.5, 40, 0xF122UL, 0.7, 5000, 2.0);
                for (int i = 0; i < n; i++)
                {
                    double t = (double)i / rate;
                    b[i] += thin[i] * Math.Exp(-t / 0.2);
                }
                LowPass(b, 6500, false);
                return Finish(b, 0.12, 1.8, false, SfxSynth.PeakTarget);
            }

            // Ambience: a low transformer buzz (120 Hz with its 240 / 360 / 480 / 600 Hz partials and a faint upper
            // stack, feel-04: a phone speaker cannot play 120 Hz, but it plays the partials, so the hum is still heard)
            // breathing slowly, a faint high buzz and rare soft crackles. Every component is periodic over the 4 s loop
            // (120 Hz is 480 cycles), so it joins seamlessly.
            public float[] AmbientHum(double[] b)
            {
                int n = b.Length;
                double len = (double)n / rate;
                var white = new Noise(0xA3B1EUL);
                var raw = new double[n];
                for (int i = 0; i < n; i++) raw[i] = white.Next();
                var buzz = new double[n];
                var band = new Svf();
                for (int pass = 0; pass < 2; pass++)
                {
                    for (int i = 0; i < n; i++)
                    {
                        band.Process(raw[i], 3200, 3.0, rate, out _, out double bp, out _);
                        if (pass == 1) buzz[i] = bp;
                    }
                }
                var crackle = new double[n];
                AddCrackleWrapped(crackle, 9, 0xA3C2UL, 3600, 1.4);
                double[] harm = { 120.0, 240.0, 360.0, 480.0, 600.0, 720.0, 840.0, 960.0 };
                double[] amp = { 0.40, 0.55, 0.50, 0.50, 0.40, 0.25, 0.16, 0.11 };
                double[] phase = { 0.0, 1.9, 4.1, 0.7, 2.8, 5.3, 1.2, 3.6 };   // spread: t = 0 is not a common zero crossing
                for (int i = 0; i < n; i++)
                {
                    double t = (double)i / rate;
                    double breathe = 0.85 + 0.15 * Math.Sin(TwoPi * t / len) + 0.05 * Math.Sin(TwoPi * 3.0 * t / len);
                    double hum = 0.0;
                    for (int k = 0; k < harm.Length; k++) hum += amp[k] * Math.Sin(TwoPi * harm[k] * t + phase[k]);
                    double hiss = buzz[i] * (0.05 + 0.04 * Math.Sin(TwoPi * 2.0 * t / len + 1.0));
                    b[i] = breathe * hum * 0.5 + hiss + 0.25 * crackle[i];
                }
                LowPass(b, 4000, true);
                return Finish(b, 0.0, 0.0, true, AmbientPeak);
            }

            // ---------------------------------------------------------------------------------------------------------
            // DSP helpers.

            /// <summary>Band-limited saw of the given phase: sum of sin(k phase) / k, k = 1..count.</summary>
            private static double Harmonics(double phase, int count)
            {
                double s = 0.0;
                for (int k = 1; k <= count; k++) s += Math.Sin(k * phase) / k;
                return s * 0.6;
            }

            private static double Envelope(double t, double attack, double decay)
            {
                if (t < 0.0) return 0.0;
                if (t < attack) return 0.5 - 0.5 * Math.Cos(Math.PI * t / attack);
                return Math.Exp(-(t - attack) / decay);
            }

            private static double Swell(double t, double rise, double duration)
            {
                if (t < rise)
                {
                    double s = Math.Sin(0.5 * Math.PI * t / rise);
                    return s * s;
                }
                double c = Math.Cos(0.5 * Math.PI * Math.Min(1.0, (t - rise) / Math.Max(1e-6, duration - rise)));
                return c * c;
            }

            /// <summary>
            /// A buzzy voice from startSeconds: pitch glides exponentially from fStart to fEnd (95 % after glideSeconds),
            /// raised-cosine attack then exponential decay, soft-clipped sine (drive 1 = almost pure, 4 = square-ish).
            /// </summary>
            private void AddBuzz(double[] b, double startSeconds, double fStart, double fEnd, double glideSeconds,
                                 double attack, double decay, double amp, double drive)
            {
                int start = (int)Math.Round(startSeconds * rate);
                int length = Math.Min((int)Math.Ceiling((attack + decay * 9.0) * rate), b.Length - start);
                double tau = Math.Max(glideSeconds / 3.0, 1e-5);
                double norm = Math.Tanh(drive);
                double phase = 0.0;
                for (int i = 0; i < length; i++)
                {
                    double t = (double)i / rate;
                    double f = fEnd + (fStart - fEnd) * Math.Exp(-t / tau);
                    phase += TwoPi * f / rate;
                    b[start + i] += amp * Envelope(t, attack, decay) * Math.Tanh(drive * Math.Sin(phase)) / norm;
                }
            }

            /// <summary>
            /// count short band-passed noise impulses (crackles) between from and from + span seconds, denser at the
            /// start, each one a few milliseconds long, deterministic per seed.
            /// </summary>
            private void AddCrackle(double[] b, double from, double span, int count, ulong seed, double amp, double center, double q)
            {
                var rnd = new Noise(seed);
                var src = new Noise(seed ^ 0x5DEECE66DUL);
                for (int c = 0; c < count; c++)
                {
                    double u = Unit(rnd);
                    double at = from + span * u * u;
                    double a = amp * (0.4 + 0.6 * Unit(rnd)) * (1.0 - 0.6 * u);
                    double decay = 0.0006 + 0.0018 * Unit(rnd);
                    double fc = center * (0.6 + 0.8 * Unit(rnd));
                    int start = (int)(at * rate);
                    int len = (int)(decay * 9.0 * rate);
                    var band = new Svf();
                    for (int i = 0; i < len && start + i < b.Length; i++)
                    {
                        band.Process(src.Next(), fc, q, rate, out _, out double bp, out _);
                        b[start + i] += a * bp * Math.Exp(-(double)i / rate / decay) * 2.5;
                    }
                }
            }

            /// <summary>Crackles written modulo the buffer (loops).</summary>
            private void AddCrackleWrapped(double[] b, int count, ulong seed, double center, double q)
            {
                int n = b.Length;
                var rnd = new Noise(seed);
                var src = new Noise(seed ^ 0x9E3779B97F4A7C15UL);
                for (int c = 0; c < count; c++)
                {
                    int start = Math.Min(n - 1, (int)(Unit(rnd) * n));
                    double a = 0.4 + 0.6 * Unit(rnd);
                    double decay = 0.0008 + 0.002 * Unit(rnd);
                    double fc = center * (0.6 + 0.8 * Unit(rnd));
                    int len = Math.Min(n, (int)(decay * 9.0 * rate));
                    var band = new Svf();
                    for (int i = 0; i < len; i++)
                    {
                        band.Process(src.Next(), fc, q, rate, out _, out double bp, out _);
                        b[(start + i) % n] += a * bp * Math.Exp(-(double)i / rate / decay) * 2.5;
                    }
                }
            }

            /// <summary>12 dB/octave low-pass in place; circular primes it over one pass (loops).</summary>
            private void LowPass(double[] b, double cutoff, bool circular)
            {
                var svf = new Svf();
                if (circular)
                {
                    for (int i = 0; i < b.Length; i++) svf.Process(b[i], cutoff, 0.7071, rate, out _, out _, out _);
                }
                for (int i = 0; i < b.Length; i++)
                {
                    svf.Process(b[i], cutoff, 0.7071, rate, out double lp, out _, out _);
                    b[i] = lp;
                }
            }

            /// <summary>
            /// One-shots: 0.8 ms raised-cosine fade in and a raised-cosine fade out ending on an exact zero. Then optional
            /// tanh saturation (drive &gt; 0) and normalization to peak.
            /// </summary>
            private float[] Finish(double[] b, double fadeOutSeconds, double drive, bool loop, float peakTarget)
            {
                int n = b.Length;
                if (!loop && n >= 4)
                {
                    int fadeIn = Math.Max(1, Math.Min(n / 4, (int)(0.0008 * rate)));
                    for (int i = 0; i < fadeIn; i++) b[i] *= 0.5 - 0.5 * Math.Cos(Math.PI * i / fadeIn);
                    int fadeOut = Math.Max(2, Math.Min(n / 2, (int)Math.Round(fadeOutSeconds * rate)));
                    int from = n - fadeOut;
                    for (int i = 0; i < fadeOut; i++) b[from + i] *= 0.5 + 0.5 * Math.Cos(Math.PI * i / (fadeOut - 1));
                }
                double peak = Peak(b);
                if (peak > 1e-12 && drive > 0.0)
                {
                    double norm = Math.Tanh(drive);
                    for (int i = 0; i < n; i++) b[i] = Math.Tanh(drive * b[i] / peak) / norm;
                    peak = Peak(b);
                }
                double scale = peak > 1e-12 ? peakTarget / peak : 0.0;
                var output = new float[n];
                for (int i = 0; i < n; i++) output[i] = (float)(b[i] * scale);
                return output;
            }

            private static double Peak(double[] b)
            {
                double peak = 0.0;
                for (int i = 0; i < b.Length; i++)
                {
                    double a = Math.Abs(b[i]);
                    if (a > peak) peak = a;
                }
                return peak;
            }

            private static double Unit(Noise rnd)
            {
                return rnd.Next() * 0.5 + 0.5;
            }
        }

        /// <summary>xorshift64 white noise in [-1, 1), deterministic per seed.</summary>
        private sealed class Noise
        {
            private ulong state;

            public Noise(ulong seed)
            {
                state = seed != 0UL ? seed : 0x9E3779B97F4A7C15UL;
            }

            public double Next()
            {
                state ^= state << 13;
                state ^= state >> 7;
                state ^= state << 17;
                return (state >> 11) * (2.0 / 9007199254740992.0) - 1.0;
            }
        }

        /// <summary>Topology-preserving state-variable filter (Zavalishin): stable under per-sample cutoff changes.</summary>
        private struct Svf
        {
            private double ic1, ic2;

            public void Process(double x, double cutoff, double q, int rate, out double lp, out double bp, out double hp)
            {
                double fc = Math.Min(Math.Max(cutoff, 10.0), rate * 0.45);
                double g = Math.Tan(Math.PI * fc / rate);
                double k = 1.0 / q;
                double a1 = 1.0 / (1.0 + g * (g + k));
                double a2 = g * a1;
                double a3 = g * a2;
                double v3 = x - ic2;
                double v1 = a1 * ic1 + a2 * v3;
                double v2 = ic2 + a2 * ic1 + a3 * v3;
                ic1 = 2.0 * v1 - ic1;
                ic2 = 2.0 * v2 - ic2;
                lp = v2;
                bp = v1;
                hp = x - k * v1 - v2;
            }
        }
    }
}
