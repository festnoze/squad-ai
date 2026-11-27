using System;
using System.Collections.Generic;
using System.Linq;
using PainterIO.Runtime;

static class P
{
    const int R = 44100;
    // Base volumes from Sfx.BaseVolumes (index = SfxId)
    static readonly float[] Base = { 0.42f, 0.48f, 0.40f, 0.75f, 0.42f, 0.80f, 0.50f, 0.60f, 0.32f, 0.45f, 0.50f, 0.62f, 0.58f, 0.50f };

    static double[] KWeight(float[] x)
    {
        // BS.1770 K-weighting, coefficients designed for fs (pyloudnorm formulas)
        double fs = R;
        // stage 1: high shelf
        double G = 3.999843853973347, Q = 0.7071752369554196, fc = 1681.974450955533;
        double A = Math.Pow(10, G / 40.0), w0 = 2 * Math.PI * fc / fs, alpha = Math.Sin(w0) / (2 * Q);
        double b0 = A * ((A + 1) + (A - 1) * Math.Cos(w0) + 2 * Math.Sqrt(A) * alpha);
        double b1 = -2 * A * ((A - 1) + (A + 1) * Math.Cos(w0));
        double b2 = A * ((A + 1) + (A - 1) * Math.Cos(w0) - 2 * Math.Sqrt(A) * alpha);
        double a0 = (A + 1) - (A - 1) * Math.Cos(w0) + 2 * Math.Sqrt(A) * alpha;
        double a1 = 2 * ((A - 1) - (A + 1) * Math.Cos(w0));
        double a2 = (A + 1) - (A - 1) * Math.Cos(w0) - 2 * Math.Sqrt(A) * alpha;
        var y = Biquad(x.Select(v => (double)v).ToArray(), b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0);
        // stage 2: high pass
        double fc2 = 38.13547087602444, Q2 = 0.5003270373238773;
        double w2 = 2 * Math.PI * fc2 / fs, al2 = Math.Sin(w2) / (2 * Q2);
        double hb0 = (1 + Math.Cos(w2)) / 2, hb1 = -(1 + Math.Cos(w2)), hb2 = (1 + Math.Cos(w2)) / 2;
        double ha0 = 1 + al2, ha1 = -2 * Math.Cos(w2), ha2 = 1 - al2;
        return Biquad(y, hb0 / ha0, hb1 / ha0, hb2 / ha0, ha1 / ha0, ha2 / ha0);
    }

    static double[] Biquad(double[] x, double b0, double b1, double b2, double a1, double a2)
    {
        var y = new double[x.Length]; double x1 = 0, x2 = 0, y1 = 0, y2 = 0;
        for (int i = 0; i < x.Length; i++) { double v = b0 * x[i] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2; x2 = x1; x1 = x[i]; y2 = y1; y1 = v; y[i] = v; }
        return y;
    }

    static double MaxWindowLufs(double[] k, double win)
    {
        int w = Math.Max(1, (int)(win * R)); if (w > k.Length) w = k.Length;
        double s = 0; for (int i = 0; i < w; i++) s += k[i] * k[i];
        double best = s;
        for (int i = w; i < k.Length; i++) { s += k[i] * k[i] - k[i - w] * k[i - w]; if (s > best) best = s; }
        double ms = best / w; return -0.691 + 10 * Math.Log10(ms + 1e-20);
    }

    static (double centroid, double hf4k, double hf8k, double[] bands) Spectrum(float[] x)
    {
        int N = 2048; var acc = new double[N / 2];
        int frames = 0;
        for (int start = 0; start + N <= Math.Max(x.Length, N); start += N / 2)
        {
            var re = new double[N]; var im = new double[N];
            for (int i = 0; i < N; i++) { int j = start + i; double v = j < x.Length ? x[j] : 0; double wnd = 0.5 - 0.5 * Math.Cos(2 * Math.PI * i / (N - 1)); re[i] = v * wnd; }
            FFT(re, im);
            for (int b = 0; b < N / 2; b++) acc[b] += re[b] * re[b] + im[b] * im[b];
            frames++;
            if (start + N >= x.Length) break;
        }
        double tot = 0, cen = 0, h4 = 0, h8 = 0;
        for (int b = 1; b < N / 2; b++) { double f = b * (double)R / N; tot += acc[b]; cen += f * acc[b]; if (f > 4000) h4 += acc[b]; if (f > 8000) h8 += acc[b]; }
        // 12 octave-ish log bands from 60 Hz to 16 kHz
        var edges = new double[13]; for (int i = 0; i <= 12; i++) edges[i] = 60 * Math.Pow(16000.0 / 60, i / 12.0);
        var bands = new double[12];
        for (int b = 1; b < N / 2; b++) { double f = b * (double)R / N; for (int k = 0; k < 12; k++) if (f >= edges[k] && f < edges[k + 1]) bands[k] += acc[b]; }
        for (int k = 0; k < 12; k++) bands[k] = 10 * Math.Log10(bands[k] / tot + 1e-9);
        return (cen / tot, h4 / tot, h8 / tot, bands);
    }

    static void FFT(double[] re, double[] im)
    {
        int n = re.Length;
        for (int i = 1, j = 0; i < n; i++) { int bit = n >> 1; for (; (j & bit) != 0; bit >>= 1) j ^= bit; j ^= bit; if (i < j) { (re[i], re[j]) = (re[j], re[i]); (im[i], im[j]) = (im[j], im[i]); } }
        for (int len = 2; len <= n; len <<= 1)
        {
            double ang = -2 * Math.PI / len; double wr = Math.Cos(ang), wi = Math.Sin(ang);
            for (int i = 0; i < n; i += len)
            {
                double cr = 1, ci = 0;
                for (int j = 0; j < len / 2; j++)
                {
                    double ur = re[i + j], ui = im[i + j];
                    double vr = re[i + j + len / 2] * cr - im[i + j + len / 2] * ci, vi = re[i + j + len / 2] * ci + im[i + j + len / 2] * cr;
                    re[i + j] = ur + vr; im[i + j] = ui + vi; re[i + j + len / 2] = ur - vr; im[i + j + len / 2] = ui - vi;
                    double nr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = nr;
                }
            }
        }
    }

    static Dictionary<string, double[]> bandsOf = new Dictionary<string, double[]>();

    static void Report(string name, float[] x, double playGain, bool loop)
    {
        double peak = x.Max(v => Math.Abs((double)v));
        double rms = Math.Sqrt(x.Sum(v => (double)v * v) / x.Length);
        var k = KWeight(x);
        double l100 = MaxWindowLufs(k, 0.1), l400 = MaxWindowLufs(k, 0.4); var ph = KWeight(Phone(x)); double lph = MaxWindowLufs(ph, 0.1);
        var sp = Spectrum(x);
        bandsOf[name] = sp.bands;
        double g = 20 * Math.Log10(playGain);
        string seam = "";
        if (loop) { var diffs = new List<double>(); for (int i = 1; i < x.Length; i++) diffs.Add(Math.Abs(x[i] - x[i - 1])); diffs.Sort(); double jump = Math.Abs(x[0] - x[x.Length - 1]); int rank = diffs.FindIndex(v => v >= jump); seam = $" seamJump={jump:0.0000} p50diff={diffs[diffs.Count / 2]:0.0000} p99diff={diffs[(int)(diffs.Count * 0.99)]:0.0000} jumpPercentile={(rank < 0 ? 100.0 : 100.0 * rank / diffs.Count):0.0}"; }
        Console.WriteLine($"{name,-22} dur={x.Length / (double)R:0.00}s peak={peak:0.00} rmsDb={20 * Math.Log10(rms):0.0} L100={l100:0.0} L400={l400:0.0} play(L100+gain)={l100 + g:0.0} phonePlay={lph + g:0.0} phoneLoss={l100 - lph:0.0}dB cen={sp.centroid:0}Hz hf>4k={sp.hf4k * 100:0}% hf>8k={sp.hf8k * 100:0}%{seam}");
    }

    static float[] Phone(float[] x)
    {
        // small phone speaker: 4th order high pass at 400 Hz (two Butterworth biquads)
        double fc = 400, fs = R, Q = 0.7071;
        double w = 2 * Math.PI * fc / fs, al = Math.Sin(w) / (2 * Q);
        double b0 = (1 + Math.Cos(w)) / 2, b1 = -(1 + Math.Cos(w)), b2 = b0, a0 = 1 + al, a1 = -2 * Math.Cos(w), a2 = 1 - al;
        var y = Biquad(x.Select(v => (double)v).ToArray(), b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0);
        y = Biquad(y, b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0);
        return y.Select(v => (float)v).ToArray();
    }
    static double Dist(double[] a, double[] b) { double s = 0; for (int i = 0; i < a.Length; i++) s += (a[i] - b[i]) * (a[i] - b[i]); return Math.Sqrt(s / a.Length); }

    static void Main()
    {
        Console.WriteLine("=== Liquid / shared (SfxSynth) ===");
        foreach (SfxId id in Enum.GetValues(typeof(SfxId)))
        {
            float gain = Base[(int)id];
            if (id == SfxId.SparkLoop) gain *= 0.55f;
            Report("L." + id, SfxSynth.Generate(id), gain, id == SfxId.SparkLoop);
        }
        Console.WriteLine("=== Fire ===");
        int[] fireSlot = { 0, 1, 2, 3, 4, 5, 13, -1 };
        foreach (FireSfx.Clip c in Enum.GetValues(typeof(FireSfx.Clip)))
        {
            int s = fireSlot[(int)c]; float gain = s >= 0 ? Base[s] : 0.22f; if (s == 4) gain *= 0.55f;
            Report("F." + c, FireSfx.Generate(c, R), gain, FireSfx.IsLoop(c));
        }
        Console.WriteLine("=== Electric ===");
        foreach (ElectricSfx.Clip c in Enum.GetValues(typeof(ElectricSfx.Clip)))
        {
            int s = fireSlot[(int)c]; float gain = s >= 0 ? Base[s] : 0.22f; if (s == 4) gain *= 0.55f;
            Report("E." + c, ElectricSfx.Synthesize(c, R), gain, ElectricSfx.IsLoop(c));
        }
        Console.WriteLine("=== Spectral distance between biomes per slot (rms dB over 12 log bands) ===");
        string[] L = { "L.ExitPlop", "L.ReturnGloop", "L.FillSwell", "L.CutSnap", "L.SparkLoop", "L.CaughtSplat", "L.LoopLost" };
        string[] F = { "F.Pop", "F.Fwump", "F.Whoosh", "F.Ignite", "F.FuseHiss", "F.Burst", "F.Fizzle" };
        string[] E = { "E.Exit", "E.Return", "E.Fill", "E.Cut", "E.TensionLoop", "E.Caught", "E.LoopLost" };
        for (int i = 0; i < L.Length; i++)
            Console.WriteLine($"{L[i],-16} L-F={Dist(bandsOf[L[i]], bandsOf[F[i]]):0.0} L-E={Dist(bandsOf[L[i]], bandsOf[E[i]]):0.0} F-E={Dist(bandsOf[F[i]], bandsOf[E[i]]):0.0}");
        Console.WriteLine("=== Band profiles (dB rel total) 60..16k ===");
        foreach (var kv in bandsOf) Console.WriteLine($"{kv.Key,-22} " + string.Join(" ", kv.Value.Select(v => v.ToString("0").PadLeft(4))));
    }
}


