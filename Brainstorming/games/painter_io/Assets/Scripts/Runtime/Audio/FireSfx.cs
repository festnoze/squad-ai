// Owned by FIRE (wave B-2, phase 2). Contract 25.2 / 25.3: the Feu biome's sounds, synthesized at startup (no audio
// assets), behind ISfxClipSet. Sfx plays them through the same cues as the liquid set (and raises the tension loop's
// pitch and volume as the spark closes in, so the fuse hiss rises in pitch by itself).
//   Exit        pop        a small ignition puff: band-passed noise burst over a low thump
//   Return      fwump      a soft low whoomp (the fireball rejoins its fire)
//   Fill        whoosh     the spreading fire: a roaring noise sweep with crackles, over FillDuration 0.6 s plus a tail
//   Cut         ignite     the fuse is lit: a match-strike scratch, then a flare of hiss
//   TensionLoop fuse hiss  seamless 0.5 s loop: sizzling hiss with two surges per loop and random crackles
//   Caught      burst      an explosive burst: noise closing down, a low boom, falling debris crackles
//   LoopLost    fizzle     contract 24: the saved fuse fizzles out (falling hiss, sputters, a soft sagging tone)
//   Ambient     crackle    seamless 4 s loop: a quiet low roar of embers with random crackles and snaps
//   Grow        spread     wave D-2 (optional Grow slot): flames licking outward, a soft rising roar with thin crackles
// Pure C# DSP in doubles with deterministic noise (the same samples on every call and platform). Every one-shot ends on
// an exact zero; every clip is normalized to SfxSynth.PeakTarget; the loops join seamlessly (wrapped events, filters
// primed over one full pass).
// Wave C (audio package): ISplitSfxClipSet (Synthesize on a worker thread, BuildSlot on the main thread; robust-03), and
// feel-04: the pop, the fwump and the burst bend their low voices (asymmetric tanh, drive 2.5) and add a 1.5 to 3 kHz tick
// layer, so a phone speaker (nothing under about 400 Hz) still plays them (at most 4 dB lost, docs/waveC/feel).
using System;
using UnityEngine;

namespace PainterIO.Runtime
{
    public class FireSfx : ISplitSfxClipSet
    {
        /// <summary>The fire clips (index = slot of this set).</summary>
        public enum Clip
        {
            Pop = 0,
            Fwump = 1,
            Whoosh = 2,
            Ignite = 3,
            FuseHiss = 4,
            Burst = 5,
            Fizzle = 6,
            Crackle = 7,
            Spread = 8,   // wave D-2: the optional Grow slot (SfxSlot.Grow)
        }

        /// <summary>Number of Clip values (slot k is Clip k, the extra Grow slot included).</summary>
        public const int ClipCount = 9;

        /// <summary>Length of the seamless fuse hiss loop (two surges per loop, like the liquid spark loop's pulses).</summary>
        public const double FuseLoopSeconds = 0.5;

        /// <summary>Length of the seamless crackle ambience loop.</summary>
        public const double AmbientLoopSeconds = 4.0;

        private const double TwoPi = 2.0 * Math.PI;

        private static readonly double[] Durations =
        {
            0.16,                 // Pop
            0.34,                 // Fwump
            0.85,                 // Whoosh (FireTheme.FillDuration 0.6 s plus a tail)
            0.26,                 // Ignite
            FuseLoopSeconds,      // FuseHiss
            0.62,                 // Burst
            0.62,                 // Fizzle
            AmbientLoopSeconds,   // Crackle
            0.62,                 // Spread
        };

        public BiomeId Biome => BiomeId.Fire;

        public AudioClip Exit { get; private set; }
        public AudioClip Return { get; private set; }
        public AudioClip Fill { get; private set; }
        public AudioClip Cut { get; private set; }
        public AudioClip TensionLoop { get; private set; }
        public AudioClip Caught { get; private set; }
        public AudioClip LoopLost { get; private set; }
        public AudioClip Ambient { get; private set; }
        public AudioClip Grow { get; private set; }

        /// <summary>
        /// Builds the nine clips now (the eight base slots and Grow): BuildSlot of each slot of Synthesize(sampleRate) (a
        /// clip that fails stays null and is logged; the others still play).
        /// </summary>
        public void Build(int sampleRate)
        {
            SfxClipSamples samples = Synthesize(sampleRate);
            for (int k = 0; k < SfxClipSamples.AllSlotCount; k++) BuildSlot(samples, (SfxSlot)k);
        }

        /// <summary>The samples of the nine clips (pure C#, thread-safe; slot k is Clip k).</summary>
        public SfxClipSamples Synthesize(int sampleRate)
        {
            int rate = sampleRate >= 8000 ? sampleRate : SfxSynth.SampleRate;
            var samples = new SfxClipSamples(BiomeId.Fire, rate);
            System.Diagnostics.Stopwatch watch = System.Diagnostics.Stopwatch.StartNew();
            for (int k = 0; k < SfxClipSamples.AllSlotCount; k++)
            {
                try
                {
                    samples.Set((SfxSlot)k, Generate((Clip)k, rate));
                }
                catch (Exception e)
                {
                    samples.SetError((SfxSlot)k, e.ToString());
                }
            }
            samples.SynthMilliseconds = watch.ElapsedMilliseconds;
            return samples;
        }

        /// <summary>Main thread: the AudioClip "pio_fire_&lt;Clip&gt;" of one slot.</summary>
        public void BuildSlot(SfxClipSamples samples, SfxSlot slot)
        {
            if (samples == null) return;
            AudioClip clip = samples.MakeClip(slot, "pio_fire_" + (Clip)(int)slot);
            switch (slot)
            {
                case SfxSlot.Exit: Exit = clip; break;
                case SfxSlot.Return: Return = clip; break;
                case SfxSlot.Fill: Fill = clip; break;
                case SfxSlot.Cut: Cut = clip; break;
                case SfxSlot.TensionLoop: TensionLoop = clip; break;
                case SfxSlot.Caught: Caught = clip; break;
                case SfxSlot.LoopLost: LoopLost = clip; break;
                case SfxSlot.Grow: Grow = clip; break;
                default: Ambient = clip; break;
            }
        }

        /// <summary>Duration of a clip in seconds.</summary>
        public static double DurationOf(Clip c)
        {
            return Durations[(int)c];
        }

        /// <summary>Exact sample count of a clip at a sample rate.</summary>
        public static int SampleCount(Clip c, int sampleRate)
        {
            return (int)Math.Round(Durations[(int)c] * sampleRate);
        }

        /// <summary>True for the clips played with loop = true (the fuse hiss and the ambience).</summary>
        public static bool IsLoop(Clip c)
        {
            return c == Clip.FuseHiss || c == Clip.Crackle;
        }

        /// <summary>Synthesizes one clip (deterministic).</summary>
        public static float[] Generate(Clip c, int sampleRate)
        {
            if (sampleRate < 8000) throw new ArgumentOutOfRangeException(nameof(sampleRate), sampleRate, "sample rate too low");
            var s = new Synth(sampleRate, SampleCount(c, sampleRate));
            switch (c)
            {
                case Clip.Pop: return s.Pop();
                case Clip.Fwump: return s.Fwump();
                case Clip.Whoosh: return s.Whoosh();
                case Clip.Ignite: return s.Ignite();
                case Clip.FuseHiss: return s.FuseHiss();
                case Clip.Burst: return s.Burst();
                case Clip.Fizzle: return s.Fizzle();
                case Clip.Crackle: return s.Crackle();
                case Clip.Spread: return s.Spread();
                default: throw new ArgumentOutOfRangeException(nameof(c), c, "unknown fire clip");
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // The synthesizer of one clip.

        private sealed class Synth
        {
            private readonly int rate;
            private readonly double[] b;

            public Synth(int sampleRate, int samples)
            {
                rate = sampleRate;
                b = new double[samples];
            }

            private int N => b.Length;

            private double T(int i) => (double)i / rate;

            // A small ignition puff: a band-passed burst, a low thump bent so a phone speaker hears it (feel-04), tiny
            // crackles and a 1.5 to 3 kHz tick layer.
            public float[] Pop()
            {
                var noise = new Noise(0xF1E0UL);
                var band = new Svf();
                for (int i = 0; i < N; i++)
                {
                    double t = T(i);
                    band.Process(noise.Next(), 1700.0 - 700.0 * Math.Min(1.0, t / 0.08), 0.9, rate, out _, out double bp, out _);
                    b[i] += 1.1 * bp * Env(t, 0.001, 0.03);
                }
                DrivenVoice(0.0, 190, 95, 0.05, 0.002, 0.035, 0.32, 2.5, 0.2);
                Click(0.012, 0.35, 0.0015, 0xC1UL);
                Click(0.034, 0.2, 0.001, 0xC2UL);
                Ticks(0.0, 0.05, 3, 0xF1E1UL, 0.4, 2200, 1.3);
                LowPass(7000, false);
                return Finish(0.03, 1.2, false);
            }

            // A soft whoomp: band-passed noise opening then closing over a bent low tone (feel-04: the body sits between
            // 400 Hz and 1.5 kHz, where a phone plays it), a few soft ticks. Darker than the electric thunk: a 24 dB/oct
            // low-pass keeps it airy, without the electric sparks.
            public float[] Fwump()
            {
                var noise = new Noise(0xF00FUL);
                var band = new Svf();
                for (int i = 0; i < N; i++)
                {
                    double t = T(i);
                    double fc = 520.0 + 1000.0 * Math.Exp(-Math.Pow((t - 0.07) / 0.06, 2.0));
                    band.Process(noise.Next(), fc, 0.9, rate, out _, out double bp, out _);
                    b[i] += 1.6 * bp * Env(t, 0.02, 0.09);
                }
                DrivenVoice(0.0, 95, 150, 0.08, 0.012, 0.1, 0.3, 2.5, 0.2);
                Ticks(0.03, 0.08, 3, 0xF010UL, 0.25, 1800, 1.2);
                LowPass(2600, false);
                LowPass(2600, false);
                return Finish(0.08, 1.0, false);
            }

            // The spreading fire: a roaring sweep that swells over the fill, a low rumble and crackles thickening.
            public float[] Whoosh()
            {
                double dur = (double)N / rate;
                var noise = new Noise(0xF111EUL);
                var band = new Svf();
                var low = new Svf();
                for (int i = 0; i < N; i++)
                {
                    double t = T(i);
                    double env = Swell(t, 0.34, dur);
                    double x = noise.Next();
                    double fc = 380.0 * Math.Pow(2600.0 / 380.0, Math.Min(1.0, t / 0.55));
                    band.Process(x, fc, 0.75, rate, out _, out double bp, out _);
                    low.Process(x, 260.0, 0.7, rate, out double lp, out _, out _);
                    b[i] += env * (0.85 * bp + 0.9 * lp);
                }
                var rnd = new Noise(0xC4A5UL);
                for (int k = 0; k < 34; k++)
                {
                    double at = 0.04 + 0.7 * Math.Sqrt(Unit(rnd));
                    Click(at, (0.15 + 0.3 * Unit(rnd)) * Swell(at, 0.34, dur), 0.001 + 0.002 * Unit(rnd), 0xA000UL + (ulong)k);
                }
                LowPass(8000, false);
                return Finish(0.08, 1.1, false);
            }

            // The fuse is lit: a match-strike scratch (grainy high noise), then a flare of hiss.
            public float[] Ignite()
            {
                var noise = new Noise(0x1617EUL);
                var high = new Svf();
                var band = new Svf();
                var grain = new Noise(0x6A1EUL);
                double g = 0.0;
                for (int i = 0; i < N; i++)
                {
                    double t = T(i);
                    double x = noise.Next();
                    if (i % Math.Max(1, rate / 900) == 0) g = 0.4 + 0.6 * Math.Abs(grain.Next());
                    high.Process(x, 3200, 0.8, rate, out _, out _, out double hp);
                    band.Process(x, 1900 + 2200 * Math.Min(1.0, t / 0.1), 1.1, rate, out _, out double bp, out _);
                    double scratch = t < 0.055 ? hp * g * (0.5 - 0.5 * Math.Cos(Math.PI * t / 0.055)) : hp * g * Math.Exp(-(t - 0.055) / 0.012);
                    double flare = bp * Env(t - 0.04, 0.03, 0.09);
                    b[i] += 0.7 * scratch + 0.75 * flare;
                }
                Click(0.05, 0.6, 0.002, 0x5EUL);
                Voice(0.045, 220, 140, 0.05, 0.003, 0.05, 0.35);
                LowPass(10000, false);
                return Finish(0.05, 1.4, false);
            }

            // Seamless fuse hiss: a sizzling high band with two surges per loop, random crackles and a faint sputter.
            public float[] FuseHiss()
            {
                var noise = new Noise(0xF05EUL);
                var white = new double[N];
                for (int i = 0; i < N; i++) white[i] = noise.Next();
                var hiss = new double[N];
                var band = new Svf();
                var band2 = new Svf();
                for (int pass = 0; pass < 2; pass++)
                {
                    for (int i = 0; i < N; i++)
                    {
                        band.Process(white[i], 5200, 1.1, rate, out _, out double bp, out _);
                        band2.Process(white[i], 2300, 1.6, rate, out _, out double bp2, out _);
                        if (pass == 1) hiss[i] = bp + 0.45 * bp2;
                    }
                }
                var crackle = new double[N];
                var rnd = new Noise(0xC7AC4UL);
                for (int c = 0; c < 38; c++)
                {
                    int at = Math.Min(N - 1, (int)(Unit(rnd) * N));
                    double amp = (Unit(rnd) < 0.5 ? -1.0 : 1.0) * (0.4 + 0.6 * Unit(rnd));
                    double decay = 0.0008 + 0.002 * Unit(rnd);
                    int len = (int)(decay * 8.0 * rate);
                    for (int i = 0; i < len; i++) crackle[(at + i) % N] += amp * Math.Exp(-(double)i / rate / decay) * white[(at * 7 + i) % N];
                }
                const int surges = 2;
                int period = N / surges;
                for (int i = 0; i < N; i++)
                {
                    double since = (double)(i % period) / rate;
                    double level = 0.55 + 0.45 * Env(since, 0.012, 0.09);
                    b[i] = hiss[i] * level + 0.9 * crackle[i];
                }
                for (int k = 0; k < surges; k++)
                {
                    double at = k * FuseLoopSeconds / surges;
                    Voice(at, 150, 95, 0.03, 0.002, 0.03, 0.35, wrap: true);
                }
                LowPass(11000, true);
                return Finish(0.0, 0.9, true);
            }

            // Caught: an explosive burst, a low boom and debris crackles falling off.
            public float[] Burst()
            {
                var noise = new Noise(0xB0A5UL);
                var low = new Svf();
                for (int i = 0; i < N; i++)
                {
                    double t = T(i);
                    double fc = 900.0 + 5600.0 * Math.Exp(-t / 0.07);
                    low.Process(noise.Next(), fc, 0.85, rate, out double lp, out _, out _);
                    b[i] += 1.2 * lp * Env(t, 0.002, 0.12);
                }
                DrivenVoice(0.0, 78, 38, 0.18, 0.003, 0.2, 0.7, 2.5, 0.2);
                Ticks(0.0, 0.12, 6, 0xB0A6UL, 0.4, 3000, 1.2);
                var rnd = new Noise(0xDEB5UL);
                for (int k = 0; k < 22; k++)
                {
                    double at = 0.04 + 0.5 * Unit(rnd) * Unit(rnd) + 0.02 * k / 22.0;
                    Click(at, (0.12 + 0.35 * Unit(rnd)) * Math.Exp(-at / 0.3), 0.001 + 0.003 * Unit(rnd), 0xD000UL + (ulong)k);
                }
                LowPass(9000, false);
                return Finish(0.1, 1.5, false);
            }

            // Loop lost: the saved fuse fizzles out (a falling sputtering hiss) over a soft sagging tone.
            public float[] Fizzle()
            {
                var noise = new Noise(0xF122EUL);
                var band = new Svf();
                var gate = new Noise(0x6A7EUL);
                double g = 1.0;
                int gateStep = Math.Max(1, rate / 60);
                for (int i = 0; i < N; i++)
                {
                    double t = T(i);
                    if (i % gateStep == 0) g = Unit(gate) < 0.25 + 0.5 * Math.Min(1.0, t / 0.5) ? 0.25 : 1.0;
                    band.Process(noise.Next(), 3600.0 * Math.Pow(900.0 / 3600.0, Math.Min(1.0, t / 0.55)), 1.3, rate, out _, out double bp, out _);
                    double env = t < 0.03 ? 0.5 - 0.5 * Math.Cos(Math.PI * t / 0.03) : Math.Exp(-(t - 0.03) / 0.2);
                    b[i] += 0.9 * bp * env * g;
                }
                Voice(0.0, 430, 255, 0.3, 0.006, 0.14, 0.4, 2.0, 0.12, 0.5);
                Voice(0.14, 330, 200, 0.25, 0.006, 0.12, 0.3);
                LowPass(6500, false);
                return Finish(0.12, 0.7, false);
            }

            // Seamless crackle ambience: a quiet low roar breathing once per loop, crackles and a few snaps (wrapped).
            public float[] Crackle()
            {
                var noise = new Noise(0xA3B1EUL);
                var white = new double[N];
                for (int i = 0; i < N; i++) white[i] = noise.Next();
                var roar = new double[N];
                var low = new Svf();
                var low2 = new Svf();
                for (int pass = 0; pass < 2; pass++)
                {
                    for (int i = 0; i < N; i++)
                    {
                        low.Process(white[i], 170, 0.7, rate, out double lp, out _, out _);
                        low2.Process(lp, 170, 0.7, rate, out double lp2, out _, out _);
                        if (pass == 1) roar[i] = lp2;
                    }
                }
                var pops = new double[N];
                var rnd = new Noise(0xC3AC1EUL);
                const int count = 30;
                for (int c = 0; c < count; c++)
                {
                    int at = Math.Min(N - 1, (int)(Unit(rnd) * N));
                    bool snap = Unit(rnd) < 0.15;
                    double amp = snap ? 0.9 + 0.1 * Unit(rnd) : 0.2 + 0.55 * Unit(rnd);
                    double decay = snap ? 0.006 + 0.004 * Unit(rnd) : 0.0015 + 0.004 * Unit(rnd);
                    int len = (int)(decay * 8.0 * rate);
                    int burst = snap ? 3 : 1 + (int)(Unit(rnd) * 2.0);
                    for (int r = 0; r < burst; r++)
                    {
                        int start = at + (int)(r * (0.006 + 0.01 * Unit(rnd)) * rate);
                        double a = amp * (r == 0 ? 1.0 : 0.5);
                        for (int i = 0; i < len; i++) pops[(start + i) % N] += a * Math.Exp(-(double)i / rate / decay) * white[(start * 13 + i * 3) % N];
                    }
                }
                var band = new Svf();
                var popsF = new double[N];
                for (int pass = 0; pass < 2; pass++)
                {
                    for (int i = 0; i < N; i++)
                    {
                        band.Process(pops[i], 2800, 0.8, rate, out _, out double bp, out _);
                        if (pass == 1) popsF[i] = bp;
                    }
                }
                double roarPeak = Peak(roar);
                double scale = roarPeak > 1e-12 ? 0.32 / roarPeak : 0.0;
                for (int i = 0; i < N; i++)
                {
                    double t = T(i);
                    double breath = 0.75 + 0.25 * Math.Sin(TwoPi * t / AmbientLoopSeconds);
                    b[i] = roar[i] * scale * breath + popsF[i];
                }
                return Finish(0.0, 0.8, true);
            }

            // Spread (wave D-2, the optional Grow slot): the fire licks outward over new ground. A soft roar of
            // band-passed noise rising and opening, thin crackles thickening then thinning out, no low thump (it plays at
            // -18 dB under the game, so it must not mask anything).
            public float[] Spread()
            {
                double dur = (double)N / rate;
                var noise = new Noise(0x5E2EADUL);
                var band = new Svf();
                var high = new Svf();
                for (int i = 0; i < N; i++)
                {
                    double t = T(i);
                    double env = Swell(t, 0.24, dur);
                    double x = noise.Next();
                    band.Process(x, 700.0 * Math.Pow(2400.0 / 700.0, Math.Min(1.0, t / 0.45)), 0.9, rate, out _, out double bp, out _);
                    high.Process(x, 3800.0, 1.6, rate, out _, out double bp2, out _);
                    b[i] += env * (0.9 * bp + 0.25 * bp2);
                }
                var rnd = new Noise(0x5E2EAEUL);
                for (int k = 0; k < 18; k++)
                {
                    double at = 0.03 + 0.5 * Unit(rnd);
                    Click(at, (0.12 + 0.25 * Unit(rnd)) * Swell(at, 0.24, dur), 0.001 + 0.0015 * Unit(rnd), 0xB100UL + (ulong)k);
                }
                LowPass(7000, false);
                return Finish(0.08, 0.9, false);
            }

            // ---- DSP helpers ---------------------------------------------------------------------------------------

            private static double Env(double t, double attack, double decay)
            {
                if (t < 0.0) return 0.0;
                if (t < attack) return 0.5 - 0.5 * Math.Cos(Math.PI * t / attack);
                return Math.Exp(-(t - attack) / decay);
            }

            private static double Swell(double t, double rise, double duration)
            {
                if (t < 0.0) return 0.0;
                if (t < rise)
                {
                    double s = Math.Sin(0.5 * Math.PI * t / rise);
                    return s * s;
                }
                double c = Math.Cos(0.5 * Math.PI * Math.Min(1.0, (t - rise) / Math.Max(1e-6, duration - rise)));
                return c * c;
            }

            // A sine voice gliding exponentially from fStart to fEnd, raised-cosine attack and exponential decay, with an
            // optional partial; wrap writes it modulo the buffer (loops).
            private void Voice(double startSeconds, double fStart, double fEnd, double glideSeconds, double attack, double decay,
                               double amp, double partialRatio = 0.0, double partialAmp = 0.0, double partialDecayScale = 1.0,
                               bool wrap = false)
            {
                int start = (int)Math.Round(startSeconds * rate);
                int length = (int)Math.Ceiling((attack + decay * 9.0) * rate);
                length = wrap ? Math.Min(length, N) : Math.Min(length, N - start);
                double tau = Math.Max(glideSeconds / 3.0, 1e-5);
                double partialDecay = Math.Max(decay * partialDecayScale, 1e-5);
                double phase = 0.0;
                for (int i = 0; i < length; i++)
                {
                    double t = (double)i / rate;
                    double f = fEnd + (fStart - fEnd) * Math.Exp(-t / tau);
                    phase += TwoPi * f / rate;
                    double v = Env(t, attack, decay) * Math.Sin(phase);
                    if (partialAmp != 0.0) v += partialAmp * Env(t, attack, partialDecay) * Math.Sin(partialRatio * phase);
                    int k = start + i;
                    if (wrap) k %= N;
                    if (k < 0 || k >= N) continue;
                    b[k] += amp * v;
                }
            }

            // A sine voice (Voice without a partial) bent by an asymmetric tanh: a drive about 2.5 and a small bias add
            // 2nd to 4th harmonics, which a phone speaker plays when it cannot play the fundamental (feel-04).
            private void DrivenVoice(double startSeconds, double fStart, double fEnd, double glideSeconds, double attack,
                                     double decay, double amp, double drive, double bias)
            {
                double[] keep = (double[])b.Clone();
                Array.Clear(b, 0, N);
                Voice(startSeconds, fStart, fEnd, glideSeconds, attack, decay, 1.0);
                double off = Math.Tanh(drive * bias);
                double norm = Math.Max(Math.Tanh(drive * (1.0 + bias)) - off, off - Math.Tanh(drive * (bias - 1.0)));
                for (int i = 0; i < N; i++) b[i] = keep[i] + amp * (Math.Tanh(drive * (b[i] + bias)) - off) / norm;
            }

            // count short band-passed noise ticks (1 to 3 ms, center 0.75x to 1.25x) between from and from + span
            // seconds, denser at the start: the 1.5 to 3 kHz click layer a phone speaker plays (feel-04).
            private void Ticks(double from, double span, int count, ulong seed, double amp, double center, double q)
            {
                var rnd = new Noise(seed);
                var src = new Noise(seed ^ 0x5DEECE66DUL);
                for (int c = 0; c < count; c++)
                {
                    double u = Unit(rnd);
                    double at = from + span * u * u;
                    double a = amp * (0.5 + 0.5 * Unit(rnd)) * (1.0 - 0.5 * u);
                    double decay = 0.001 + 0.002 * Unit(rnd);
                    double fc = center * (0.75 + 0.5 * Unit(rnd));
                    int start = (int)Math.Round(at * rate);
                    int len = (int)(decay * 9.0 * rate);
                    var band = new Svf();
                    for (int i = 0; i < len && start + i < N; i++)
                    {
                        band.Process(src.Next(), fc, q, rate, out _, out double bp, out _);
                        b[start + i] += a * bp * Math.Exp(-(double)i / rate / decay);
                    }
                }
            }

            // A crackle: a few milliseconds of high-passed noise with a sharp decay.
            private void Click(double atSeconds, double amp, double decay, ulong seed)
            {
                var noise = new Noise(seed);
                var high = new Svf();
                int start = (int)Math.Round(atSeconds * rate);
                int length = (int)Math.Ceiling(decay * 9.0 * rate);
                for (int i = 0; i < length; i++)
                {
                    int k = start + i;
                    if (k < 0 || k >= N) break;
                    high.Process(noise.Next(), 1800, 0.7, rate, out _, out _, out double hp);
                    b[k] += amp * hp * Math.Exp(-(double)i / rate / decay);
                }
            }

            private void LowPass(double cutoff, bool circular)
            {
                var svf = new Svf();
                if (circular)
                {
                    for (int i = 0; i < N; i++) svf.Process(b[i], cutoff, 0.7071, rate, out _, out _, out _);
                }
                for (int i = 0; i < N; i++)
                {
                    svf.Process(b[i], cutoff, 0.7071, rate, out double lp, out _, out _);
                    b[i] = lp;
                }
            }

            // One-shots: 0.8 ms fade in and a raised-cosine fade out ending on an exact zero; optional tanh drive; then
            // normalization to SfxSynth.PeakTarget.
            private float[] Finish(double fadeOutSeconds, double drive, bool loop)
            {
                int n = N;
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
                double scale = peak > 1e-12 ? SfxSynth.PeakTarget / peak : 0.0;
                var output = new float[n];
                for (int i = 0; i < n; i++) output[i] = (float)(b[i] * scale);
                if (!loop && n > 0) output[n - 1] = 0f;
                return output;
            }

            private static double Peak(double[] x)
            {
                double peak = 0.0;
                for (int i = 0; i < x.Length; i++)
                {
                    double a = Math.Abs(x[i]);
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

        /// <summary>Topology-preserving state-variable filter (Zavalishin), stable under per-sample cutoff changes.</summary>
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
