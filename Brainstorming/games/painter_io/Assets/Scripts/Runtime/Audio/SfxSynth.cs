// Owned by BI since wave B-2 (written by B5). Contract 16: every sound of the game is synthesized here at startup (no audio
// assets). The biome slots (exit, return, fill, cut, tension loop, caught, loop lost) are wrapped by LiquidSfx (ISfxClipSet,
// contract 25.2); LoopLost is the contract 24 sound of a saved chased return (no capture).
// Pure C# DSP in doubles with deterministic noise, plus one Unity entry point (CreateClip). The sound design brief is
// "liquid and glossy, soft and pleasant": sine voices with pitch glides (bubbles and drops), band-passed noise, short
// envelopes and gentle low-pass filtering; no square or saw waves. Every one-shot is normalized to PeakTarget and ends on
// an exact zero; the spark tension loop is normalized too and joins seamlessly instead (it is played with loop = true and
// its pitch, hence its pulse rate, follows TensionPitch).
// Wave C (audio package), feel-04: phone speakers play nothing under about 400 Hz, so the gloop and the splat bend their low
// voices (AddDrivenVoice: asymmetric tanh, drive 2.5) and the splat gets a mid splash; the lose jingle is doubled an octave
// up with richer partials and a little more drive, as loud as the win jingle on a phone. Every clip loses at most 4 dB
// through a 400 Hz 24 dB/oct high-pass (WaveC_AudioTests).
using System;
using UnityEngine;

namespace PainterIO.Runtime
{
    /// <summary>The procedural clips of contract 16 (index = clip slot).</summary>
    public enum SfxId
    {
        ExitPlop = 0,
        ReturnGloop = 1,
        FillSwell = 2,
        CutSnap = 3,
        SparkLoop = 4,
        CaughtSplat = 5,
        RingChime = 6,
        LassoZip = 7,
        ToastTick = 8,
        UiClick = 9,
        CountdownTick = 10,
        WinJingle = 11,
        LoseJingle = 12,
        LoopLost = 13,
    }

    public static class SfxSynth
    {
        /// <summary>Sample rate of every clip (mono).</summary>
        public const int SampleRate = 44100;

        /// <summary>Number of SfxId values.</summary>
        public const int ClipCount = 14;

        /// <summary>Every clip is normalized to this absolute peak.</summary>
        public const float PeakTarget = 0.89f;

        /// <summary>Hard ceiling asserted by the tests.</summary>
        public const float PeakLimit = 0.95f;

        /// <summary>Length of the seamless spark tension loop (every tonal component is a multiple of 1 / 0.5 s = 2 Hz).</summary>
        public const double SparkLoopSeconds = 0.5;

        /// <summary>Pulses per loop at pitch 1 (4 pulses per second).</summary>
        public const int SparkLoopPulses = 2;

        /// <summary>At or beyond this SparkCatchEta (seconds) the tension loop sits at its base pitch and volume.</summary>
        public const double TensionFarEta = 4.0;

        public const float TensionBasePitch = 1f;
        public const float TensionTopPitch = 1.9f;
        public const float TensionBaseVolume = 0.55f;
        public const float TensionTopVolume = 1f;

        private const double TwoPi = 2.0 * Math.PI;

        private static readonly double[] Durations =
        {
            0.16,               // ExitPlop
            0.34,               // ReturnGloop
            0.55,               // FillSwell (FillDuration 0.35 s plus a tail)
            0.18,               // CutSnap
            SparkLoopSeconds,   // SparkLoop
            0.50,               // CaughtSplat
            0.90,               // RingChime
            0.42,               // LassoZip
            0.09,               // ToastTick
            0.07,               // UiClick
            0.13,               // CountdownTick
            1.50,               // WinJingle
            1.40,               // LoseJingle
            0.62,               // LoopLost
        };

        /// <summary>Duration of a clip in seconds.</summary>
        public static double DurationOf(SfxId id)
        {
            return Durations[(int)id];
        }

        /// <summary>Exact sample count of a clip: round(DurationOf(id) * SampleRate).</summary>
        public static int SampleCount(SfxId id)
        {
            return (int)Math.Round(Durations[(int)id] * SampleRate);
        }

        /// <summary>True for the clip played with loop = true (the spark tension loop).</summary>
        public static bool IsLoop(SfxId id)
        {
            return id == SfxId.SparkLoop;
        }

        /// <summary>Synthesizes one clip (deterministic: the same samples on every call and platform).</summary>
        public static float[] Generate(SfxId id)
        {
            var b = new double[SampleCount(id)];
            switch (id)
            {
                case SfxId.ExitPlop: return ExitPlop(b);
                case SfxId.ReturnGloop: return ReturnGloop(b);
                case SfxId.FillSwell: return FillSwell(b);
                case SfxId.CutSnap: return CutSnap(b);
                case SfxId.SparkLoop: return SparkLoop(b);
                case SfxId.CaughtSplat: return CaughtSplat(b);
                case SfxId.RingChime: return RingChime(b);
                case SfxId.LassoZip: return LassoZip(b);
                case SfxId.ToastTick: return ToastTick(b);
                case SfxId.UiClick: return UiClick(b);
                case SfxId.CountdownTick: return CountdownTick(b);
                case SfxId.WinJingle: return WinJingle(b);
                case SfxId.LoseJingle: return LoseJingle(b);
                case SfxId.LoopLost: return LoopLost(b);
                default: throw new ArgumentOutOfRangeException(nameof(id), id, "unknown clip");
            }
        }

        /// <summary>Generate(id) as a mono AudioClip named "pio_&lt;id&gt;" (non-streamed).</summary>
        public static AudioClip CreateClip(SfxId id)
        {
            return SfxClipSamples.CreateClip("pio_" + id, Generate(id), SampleRate);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Spark tension loop parameters (contract 16: pitch and rate rise as SimView.SparkCatchEta drops).

        /// <summary>0 when the catch is far (eta &gt;= TensionFarEta, +inf or NaN), 1 when imminent (eta &lt;= 0), linear between.</summary>
        public static float TensionCloseness(double eta)
        {
            if (double.IsNaN(eta) || eta >= TensionFarEta) return 0f;
            if (eta <= 0.0) return 1f;
            return (float)(1.0 - eta / TensionFarEta);
        }

        /// <summary>Playback pitch of the loop: 1 when far, up to 1.9 when imminent (non-increasing in eta).</summary>
        public static float TensionPitch(double eta)
        {
            double k = TensionCloseness(eta);
            return (float)(TensionBasePitch + (TensionTopPitch - TensionBasePitch) * Math.Pow(k, 1.6));
        }

        /// <summary>Pulses per second heard at TensionPitch(eta): 4 when far, 7.6 when imminent (non-increasing in eta).</summary>
        public static float TensionRate(double eta)
        {
            return (float)(SparkLoopPulses / SparkLoopSeconds) * TensionPitch(eta);
        }

        /// <summary>Loop volume factor: 0.55 when far, 1 when imminent (non-increasing in eta).</summary>
        public static float TensionVolume(double eta)
        {
            return TensionBaseVolume + (TensionTopVolume - TensionBaseVolume) * TensionCloseness(eta);
        }

        // ------------------------------------------------------------------------------------------------------------
        // The clips.

        // A water drop leaving the puddle: a small bubble whose pitch jumps up while it rings out.
        private static float[] ExitPlop(double[] b)
        {
            AddVoice(b, 0.0, 520, 1350, 0.03, 0.0015, 0.032, 1.0, 2.0, 0.10, 0.6);
            AddVoice(b, 0.0, 170, 250, 0.02, 0.001, 0.02, 0.35);
            LowPass(b, 5200, false);
            return Finish(b, 0.03, 0.0, false);
        }

        // The pearl merging back: a big low bubble, a smaller one right after, and a soft body.
        private static float[] ReturnGloop(double[] b)
        {
            AddVoice(b, 0.0, 240, 540, 0.07, 0.003, 0.075, 1.0, 2.0, 0.32, 0.5);
            AddVoice(b, 0.055, 420, 800, 0.04, 0.002, 0.05, 0.7, 2.0, 0.15, 0.5);
            AddDrivenVoice(b, 0.0, 105, 150, 0.05, 0.004, 0.09, 0.26, 2.5, 0.2);
            LowPass(b, 3600, false);
            return Finish(b, 0.06, 1.3, false);
        }

        // The fill wave: a whoosh of band-passed noise sweeping up under a soft major chord that glides up a little.
        private static float[] FillSwell(double[] b)
        {
            int n = b.Length;
            double dur = (double)n / SampleRate;
            const double rise = 0.24;
            var noise = new NoiseSource(0xF111UL);
            var band = new Svf();
            double[] freqs = { 523.25, 659.25, 783.99, 1567.98 };
            double[] amps = { 0.20, 0.17, 0.15, 0.05 };
            var phases = new double[freqs.Length];
            for (int i = 0; i < n; i++)
            {
                double t = (double)i / SampleRate;
                double env = SwellEnvelope(t, rise, dur);
                double fc = 500.0 * Math.Pow(2600.0 / 500.0, t / dur);
                band.Process(noise.Next(), fc, 1.2, out _, out double bp, out _);
                double glide = 1.0 + 0.03 * t / dur;
                double pad = 0.0;
                for (int k = 0; k < freqs.Length; k++)
                {
                    phases[k] += TwoPi * freqs[k] * glide / SampleRate;
                    pad += amps[k] * Math.Sin(phases[k]);
                }
                b[i] = env * (0.55 * bp + pad);
            }
            LowPass(b, 7000, false);
            return Finish(b, 0.05, 0.0, false);
        }

        // The pinch of a thread: a bright, fast-falling pluck over a tiny high click and a short "tsk" of noise.
        private static float[] CutSnap(double[] b)
        {
            int n = b.Length;
            var noise = new NoiseSource(0xC07UL);
            var high = new Svf();
            var band = new Svf();
            for (int i = 0; i < n; i++)
            {
                double t = (double)i / SampleRate;
                double x = noise.Next();
                high.Process(x, 2500, 0.7, out _, out _, out double hp);
                band.Process(x, 5200, 2.0, out _, out double bp, out _);
                b[i] += 0.6 * hp * Math.Exp(-t / 0.003) + 0.35 * bp * Envelope(t, 0.0005, 0.015);
            }
            AddVoice(b, 0.0, 3400, 1500, 0.025, 0.0008, 0.03, 0.9, 1.48, 0.30, 0.6);
            AddVoice(b, 0.002, 900, 600, 0.03, 0.001, 0.045, 0.35);
            LowPass(b, 9000, false);
            return Finish(b, 0.04, 1.6, false);
        }

        // The retraction front racing up the thread: a fizzing band of noise with crackles, two soft heartbeat thumps per
        // loop (each with a glassy tick) and a quiet beating drone (330 / 334 Hz beat at 4 Hz, the pulse rate). Every
        // component is periodic over the loop (wrapped events, filters primed over one full pass), so it joins seamlessly.
        private static float[] SparkLoop(double[] b)
        {
            int n = b.Length;
            var noise = new NoiseSource(0x5BA4CUL);
            var white = new double[n];
            for (int i = 0; i < n; i++) white[i] = noise.Next();
            var fizz = new double[n];
            var band = new Svf();
            for (int pass = 0; pass < 2; pass++)
            {
                for (int i = 0; i < n; i++)
                {
                    band.Process(white[i], 3600, 1.4, out _, out double bp, out _);
                    if (pass == 1) fizz[i] = bp;
                }
            }

            var crackle = new double[n];
            var rnd = new NoiseSource(0xC4AC1EUL);
            for (int c = 0; c < 30; c++)
            {
                int at = Math.Min(n - 1, (int)(Unit(rnd) * n));
                double amp = 0.5 + 0.5 * Unit(rnd);
                double decay = 0.0015 + 0.0025 * Unit(rnd);
                int len = (int)(decay * 8.0 * SampleRate);
                for (int i = 0; i < len; i++) crackle[(at + i) % n] += amp * Math.Exp(-(double)i / SampleRate / decay);
            }

            int period = n / SparkLoopPulses;
            for (int i = 0; i < n; i++)
            {
                double sincePulse = (double)(i % period) / SampleRate;
                double level = 0.10 + 0.10 * Envelope(sincePulse, 0.002, 0.06) + 0.5 * crackle[i];
                double t = (double)i / SampleRate;
                b[i] = fizz[i] * level
                       + 0.07 * (Math.Sin(TwoPi * 330.0 * t) + Math.Sin(TwoPi * 334.0 * t))
                       + 0.035 * Math.Sin(TwoPi * 662.0 * t);
            }
            for (int k = 0; k < SparkLoopPulses; k++)
            {
                double at = k * SparkLoopSeconds / SparkLoopPulses;
                AddVoice(b, at, 190, 115, 0.04, 0.002, 0.045, 0.45, wrap: true);
                AddVoice(b, at, 1320, 1320, 0.001, 0.001, 0.012, 0.22, 2.0, 0.10, 0.5, wrap: true);
            }
            LowPass(b, 8000, true);
            return Finish(b, 0.0, 0.8, true);
        }

        // Caught: a wet burst of low-passed noise closing down, a sinking blob and a few droplets falling back.
        private static float[] CaughtSplat(double[] b)
        {
            int n = b.Length;
            var noise = new NoiseSource(0x5B1A7UL);
            var low = new Svf();
            for (int i = 0; i < n; i++)
            {
                double t = (double)i / SampleRate;
                double fc = 650.0 + 2400.0 * Math.Exp(-t / 0.06);
                low.Process(noise.Next(), fc, 0.9, out double lp, out _, out _);
                b[i] += lp * Envelope(t, 0.002, 0.09);
            }
            AddDrivenVoice(b, 0.0, 240, 70, 0.12, 0.003, 0.12, 0.55, 2.5, 0.2);
            AddNoiseBurst(b, 0.0, 1300, 1.0, 0.001, 0.05, 0.9, 0x5B1A8UL);
            var rnd = new NoiseSource(0xD80F5UL);
            for (int d = 0; d < 7; d++)
            {
                double at = 0.05 + 0.28 * Unit(rnd);
                double f0 = 600.0 + 400.0 * Unit(rnd);
                double ratio = 1.8 + 0.6 * Unit(rnd);
                double decay = 0.02 + 0.015 * Unit(rnd);
                AddVoice(b, at, f0, f0 * ratio, 0.02, 0.0015, decay, 0.45 * (1.0 - at / 0.4));
            }
            LowPass(b, 4000, false);
            return Finish(b, 0.08, 1.4, false);
        }

        // A glossy two-note bell (C6 then G6), slightly inharmonic partials, a hint of vibrato.
        private static float[] RingChime(double[] b)
        {
            AddBell(b, 0.0, 1046.5, 0.7, 0.32);
            AddBell(b, 0.075, 1567.98, 0.5, 0.36);
            LowPass(b, 9000, false);
            return Finish(b, 0.15, 0.0, false);
        }

        // The lasso closing: an accelerating train of tiny clicks over a rising swoop, ended by a bright bubble.
        private static float[] LassoZip(double[] b)
        {
            int n = b.Length;
            const double sweep = 0.30;
            var clicks = new double[n];
            double tc = 0.0, interval = 0.028;
            while (tc < sweep)
            {
                int at = (int)(tc * SampleRate);
                int len = (int)(0.0025 * 8.0 * SampleRate);
                for (int i = 0; i < len && at + i < n; i++) clicks[at + i] += Math.Exp(-(double)i / SampleRate / 0.0025);
                tc += interval;
                interval = Math.Max(0.007, interval * 0.86);
            }
            var noise = new NoiseSource(0x21FUL);
            var band = new Svf();
            double phase = 0.0;
            for (int i = 0; i < n; i++)
            {
                double t = (double)i / SampleRate;
                double u = Math.Min(1.0, t / sweep);
                double f = 380.0 * Math.Pow(1900.0 / 380.0, u);
                phase += TwoPi * f / SampleRate;
                double env;
                if (t < 0.02) env = 0.5 - 0.5 * Math.Cos(Math.PI * t / 0.02);
                else if (t < sweep) env = 1.0;
                else env = Math.Max(0.0, 1.0 - (t - sweep) / 0.06);
                band.Process(noise.Next(), 2500.0 + 3500.0 * u, 1.5, out _, out double bp, out _);
                b[i] += env * (0.35 * Math.Sin(phase) + 0.12 * Math.Sin(2.0 * phase)) + 0.5 * bp * clicks[i];
            }
            AddVoice(b, 0.31, 800, 1900, 0.02, 0.0015, 0.03, 0.6, 2.0, 0.10, 0.5);
            LowPass(b, 8000, false);
            return Finish(b, 0.06, 0.6, false);
        }

        // A light wooden tick for toasts.
        private static float[] ToastTick(double[] b)
        {
            AddVoice(b, 0.0, 1900, 1760, 0.004, 0.001, 0.016, 0.8, 2.4, 0.20, 0.5);
            LowPass(b, 6000, false);
            return Finish(b, 0.02, 0.0, false);
        }

        // A soft bubble pop for buttons and toggles.
        private static float[] UiClick(double[] b)
        {
            AddVoice(b, 0.0, 650, 1250, 0.012, 0.0012, 0.014, 1.0, 2.0, 0.10, 0.5);
            LowPass(b, 5000, false);
            return Finish(b, 0.015, 0.0, false);
        }

        // A clean marimba-like tick (E6 with its 4th partial and a soft octave below) for the last 10 s.
        private static float[] CountdownTick(double[] b)
        {
            AddVoice(b, 0.0, 1318.5, 1318.5, 0.001, 0.0015, 0.05, 0.8, 4.0, 0.18, 0.3);
            AddVoice(b, 0.0, 659.25, 659.25, 0.001, 0.002, 0.03, 0.2);
            LowPass(b, 7000, false);
            return Finish(b, 0.03, 0.0, false);
        }

        // Win: a rising C major arpeggio of liquid notes (each slides up into pitch), the last one held with a fifth
        // under it and a little sparkle on top.
        private static float[] WinJingle(double[] b)
        {
            double[] at = { 0.0, 0.10, 0.20 };
            double[] f = { 523.25, 659.25, 783.99 };
            for (int k = 0; k < at.Length; k++) AddVoice(b, at[k], f[k] * 0.88, f[k], 0.03, 0.004, 0.22, 0.55, 2.0, 0.25, 0.5);
            AddVoice(b, 0.32, 1046.5 * 0.88, 1046.5, 0.03, 0.004, 0.55, 0.7, 2.0, 0.25, 0.5, 0.004, 5.5);
            AddVoice(b, 0.32, 783.99 * 0.9, 783.99, 0.03, 0.006, 0.5, 0.3, 2.0, 0.15, 0.5);
            AddVoice(b, 0.40, 2093.0, 2093.0, 0.001, 0.003, 0.25, 0.12, 1.5, 0.30, 0.5);
            LowPass(b, 7000, false);
            return Finish(b, 0.3, 0.5, false);
        }

        // Lose: a gentle falling C minor line (G4, Eb4, C4), each note drooping into pitch, the last one sagging.
        private static float[] LoseJingle(double[] b)
        {
            double[] at = { 0.0, 0.17 };
            double[] f = { 392.0, 311.13 };
            for (int k = 0; k < at.Length; k++)
            {
                AddVoice(b, at[k], f[k] * 1.04, f[k], 0.05, 0.005, 0.22, 0.5, 3.0, 0.35, 0.5);
                AddVoice(b, at[k], f[k] * 2.08, f[k] * 2.0, 0.05, 0.005, 0.2, 0.55, 2.0, 0.4, 0.5);
            }
            AddVoice(b, 0.34, 261.63, 261.63 * 0.955, 0.7, 0.005, 0.55, 0.5, 3.0, 0.35, 0.5);
            AddVoice(b, 0.34, 523.25, 523.25 * 0.955, 0.7, 0.005, 0.5, 0.6, 2.0, 0.4, 0.5);
            AddVoice(b, 0.34, 392.0, 392.0 * 0.955, 0.7, 0.008, 0.45, 0.15);
            LowPass(b, 4000, false);
            return Finish(b, 0.3, 2.0, false);
        }

        // Loop lost (contract 24): the saved pearl merges home but the loop is gone. A soft descending double bloop (the
        // merge, sagging) over a faint evaporating fizz with a few tiny rising bubbles that fade out: gentle, not a failure
        // sting.
        private static float[] LoopLost(double[] b)
        {
            int n = b.Length;
            AddVoice(b, 0.0, 620, 330, 0.20, 0.004, 0.10, 0.75, 2.0, 0.12, 0.5);
            AddVoice(b, 0.13, 430, 235, 0.18, 0.004, 0.09, 0.5, 2.0, 0.08, 0.5);
            var noise = new NoiseSource(0x10057UL);
            var band = new Svf();
            for (int i = 0; i < n; i++)
            {
                double t = (double)i / SampleRate;
                band.Process(noise.Next(), 4200.0 - 1600.0 * Math.Min(1.0, t / 0.5), 1.6, out _, out double bp, out _);
                double env = t < 0.08 ? 0.5 - 0.5 * Math.Cos(Math.PI * t / 0.08) : Math.Exp(-(t - 0.08) / 0.16);
                b[i] += 0.16 * bp * env;
            }
            var rnd = new NoiseSource(0xE7A9UL);
            for (int d = 0; d < 6; d++)
            {
                double at = 0.14 + 0.32 * Unit(rnd);
                double f0 = 1300.0 + 900.0 * Unit(rnd);
                AddVoice(b, at, f0, f0 * 1.7, 0.015, 0.001, 0.012 + 0.01 * Unit(rnd), 0.16 * (1.0 - (at - 0.14) / 0.4));
            }
            LowPass(b, 6000, false);
            return Finish(b, 0.12, 0.6, false);
        }
        // ------------------------------------------------------------------------------------------------------------
        // DSP helpers.

        /// <summary>Raised-cosine attack then exponential decay (time constant decay).</summary>
        private static double Envelope(double t, double attack, double decay)
        {
            if (t < 0.0) return 0.0;
            if (t < attack) return 0.5 - 0.5 * Math.Cos(Math.PI * t / attack);
            return Math.Exp(-(t - attack) / decay);
        }

        private static double SwellEnvelope(double t, double rise, double duration)
        {
            if (t < rise)
            {
                double s = Math.Sin(0.5 * Math.PI * t / rise);
                return s * s;
            }
            double c = Math.Cos(0.5 * Math.PI * Math.Min(1.0, (t - rise) / (duration - rise)));
            return c * c;
        }

        /// <summary>
        /// Adds a sine voice from startSeconds: pitch glides exponentially from fStart to fEnd (95 % there after
        /// glideSeconds), raised-cosine attack then exponential decay, an optional partial (ratio x the fundamental's
        /// phase, so it follows the glide) with its own decay, optional vibrato. With wrap the voice is written modulo
        /// the buffer (loops).
        /// </summary>
        private static void AddVoice(double[] b, double startSeconds, double fStart, double fEnd, double glideSeconds,
                                     double attack, double decay, double amp, double partialRatio = 0.0,
                                     double partialAmp = 0.0, double partialDecayScale = 1.0, double vibratoDepth = 0.0,
                                     double vibratoHz = 0.0, bool wrap = false)
        {
            int start = (int)Math.Round(startSeconds * SampleRate);
            int length = (int)Math.Ceiling((attack + decay * 9.0) * SampleRate);
            length = wrap ? Math.Min(length, b.Length) : Math.Min(length, b.Length - start);
            double tau = Math.Max(glideSeconds / 3.0, 1e-5);
            double partialDecay = Math.Max(decay * partialDecayScale, 1e-5);
            double phase = 0.0;
            for (int i = 0; i < length; i++)
            {
                double t = (double)i / SampleRate;
                double f = fEnd + (fStart - fEnd) * Math.Exp(-t / tau);
                if (vibratoDepth > 0.0) f *= 1.0 + vibratoDepth * Math.Sin(TwoPi * vibratoHz * t);
                phase += TwoPi * f / SampleRate;
                double v = Envelope(t, attack, decay) * Math.Sin(phase);
                if (partialAmp != 0.0) v += partialAmp * Envelope(t, attack, partialDecay) * Math.Sin(partialRatio * phase);
                int k = start + i;
                if (wrap) k %= b.Length;
                if (k < 0 || k >= b.Length) continue;
                b[k] += amp * v;
            }
        }

        /// <summary>
        /// Adds a sine voice (AddVoice without a partial) bent by an asymmetric tanh: a drive about 2.5 and a small bias
        /// give the voice 2nd to 4th harmonics, which a phone speaker plays when it cannot play the fundamental (feel-04).
        /// The bent voice peaks at amp and still starts and ends on zero.
        /// </summary>
        private static void AddDrivenVoice(double[] b, double startSeconds, double fStart, double fEnd, double glideSeconds,
                                           double attack, double decay, double amp, double drive, double bias)
        {
            var v = new double[b.Length];
            AddVoice(v, startSeconds, fStart, fEnd, glideSeconds, attack, decay, 1.0);
            Bend(v, drive, bias);
            for (int i = 0; i < b.Length; i++) b[i] += amp * v[i];
        }

        /// <summary>Asymmetric tanh in place (0 stays 0, |x| &lt;= 1 maps into [-1, 1]).</summary>
        private static void Bend(double[] v, double drive, double bias)
        {
            double off = Math.Tanh(drive * bias);
            double norm = Math.Max(Math.Tanh(drive * (1.0 + bias)) - off, off - Math.Tanh(drive * (bias - 1.0)));
            for (int i = 0; i < v.Length; i++) v[i] = (Math.Tanh(drive * (v[i] + bias)) - off) / norm;
        }

        /// <summary>
        /// count short band-passed noise ticks (1 to 3 ms each, center 0.75x to 1.25x) between from and from + span
        /// seconds, denser at the start: the 1.5 to 3 kHz click layer a phone speaker plays (feel-04).
        /// </summary>
        private static void AddTicks(double[] b, double from, double span, int count, ulong seed, double amp, double center, double q)
        {
            var rnd = new NoiseSource(seed);
            var src = new NoiseSource(seed ^ 0x5DEECE66DUL);
            for (int c = 0; c < count; c++)
            {
                double u = Unit(rnd);
                double at = from + span * u * u;
                double a = amp * (0.5 + 0.5 * Unit(rnd)) * (1.0 - 0.5 * u);
                double decay = 0.001 + 0.002 * Unit(rnd);
                double fc = center * (0.75 + 0.5 * Unit(rnd));
                int start = (int)Math.Round(at * SampleRate);
                int len = (int)(decay * 9.0 * SampleRate);
                var band = new Svf();
                for (int i = 0; i < len && start + i < b.Length; i++)
                {
                    band.Process(src.Next(), fc, q, out _, out double bp, out _);
                    b[start + i] += a * bp * Math.Exp(-(double)i / SampleRate / decay);
                }
            }
        }

        /// <summary>A burst of band-passed noise (center Hz, Q) from startSeconds with an attack / decay envelope.</summary>
        private static void AddNoiseBurst(double[] b, double startSeconds, double center, double q, double attack, double decay,
                                          double amp, ulong seed)
        {
            var noise = new NoiseSource(seed);
            var band = new Svf();
            int start = (int)Math.Round(startSeconds * SampleRate);
            int length = Math.Min((int)Math.Ceiling((attack + decay * 9.0) * SampleRate), b.Length - start);
            for (int i = 0; i < length; i++)
            {
                double t = (double)i / SampleRate;
                band.Process(noise.Next(), center, q, out _, out double bp, out _);
                b[start + i] += amp * bp * Envelope(t, attack, decay);
            }
        }

        private static void AddBell(double[] b, double at, double f, double amp, double decay)
        {
            AddVoice(b, at, f, f, 0.001, 0.003, decay, amp, 2.0, 0.35, 0.55, 0.002, 6.0);
            AddVoice(b, at, f * 2.76, f * 2.76, 0.001, 0.002, decay * 0.35, amp * 0.22);
            AddVoice(b, at, f * 5.4, f * 5.4, 0.001, 0.001, decay * 0.15, amp * 0.08);
        }

        /// <summary>12 dB/octave low-pass (state-variable filter, Q 0.707) in place; circular primes it over one pass (loops).</summary>
        private static void LowPass(double[] b, double cutoff, bool circular)
        {
            var svf = new Svf();
            if (circular)
            {
                for (int i = 0; i < b.Length; i++) svf.Process(b[i], cutoff, 0.7071, out _, out _, out _);
            }
            for (int i = 0; i < b.Length; i++)
            {
                svf.Process(b[i], cutoff, 0.7071, out double lp, out _, out _);
                b[i] = lp;
            }
        }

        /// <summary>
        /// Fades (one-shots: 0.8 ms raised-cosine fade in, raised-cosine fade out ending on an exact zero), optional
        /// tanh saturation (drive &gt; 0, a soft glossy squeeze of the transients), then normalization to PeakTarget.
        /// </summary>
        private static float[] Finish(double[] b, double fadeOutSeconds, double drive, bool loop)
        {
            int n = b.Length;
            if (!loop && n >= 4)
            {
                int fadeIn = Math.Max(1, Math.Min(n / 4, (int)(0.0008 * SampleRate)));
                for (int i = 0; i < fadeIn; i++) b[i] *= 0.5 - 0.5 * Math.Cos(Math.PI * i / fadeIn);
                int fadeOut = Math.Max(2, Math.Min(n / 2, (int)Math.Round(fadeOutSeconds * SampleRate)));
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
            double scale = peak > 1e-12 ? PeakTarget / peak : 0.0;
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

        private static double Unit(NoiseSource rnd)
        {
            return rnd.Next() * 0.5 + 0.5;
        }

        /// <summary>xorshift64 white noise in [-1, 1), deterministic per seed.</summary>
        private sealed class NoiseSource
        {
            private ulong state;

            public NoiseSource(ulong seed)
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

            public void Process(double x, double cutoff, double q, out double lp, out double bp, out double hp)
            {
                double fc = Math.Min(Math.Max(cutoff, 10.0), SampleRate * 0.45);
                double g = Math.Tan(Math.PI * fc / SampleRate);
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
