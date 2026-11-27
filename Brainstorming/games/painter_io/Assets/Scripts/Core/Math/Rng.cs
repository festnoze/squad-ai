using System;

namespace PainterIO.Core
{
    /// <summary>
    /// xorshift64* generator (Vigna 2014: shifts 12, 25, 27, multiplier 0x2545F4914F6CDD1D). Integer arithmetic only,
    /// so the sequence is identical on every platform and runtime (contract 5.1, determinism rule of section 6).
    /// </summary>
    public sealed class Rng
    {
        /// <summary>Replacement for seed 0 (xorshift has an all-zero fixed point): the 64-bit golden ratio constant.</summary>
        public const ulong ZeroSeedReplacement = 0x9E3779B97F4A7C15UL;

        private const ulong Multiplier = 0x2545F4914F6CDD1DUL;
        private const double InvTwoPow53 = 1.0 / 9007199254740992.0; // 2^-53

        private ulong state;

        public Rng(ulong seed)
        {
            state = seed == 0UL ? ZeroSeedReplacement : seed;
        }

        /// <summary>Next raw 64-bit value.</summary>
        public ulong NextULong()
        {
            ulong x = state;
            x ^= x >> 12;
            x ^= x << 25;
            x ^= x >> 27;
            state = x;
            unchecked
            {
                return x * Multiplier;
            }
        }

        /// <summary>Uniform double in [0, 1) built from the top 53 bits (every value is exactly representable).</summary>
        public double NextDouble()
        {
            return (NextULong() >> 11) * InvTwoPow53;
        }

        /// <summary>
        /// Uniform integer in [0, maxExclusive) by multiply-shift on the top 32 bits (Lemire; bias below 2^-32 for
        /// the ranges used here). Throws ArgumentOutOfRangeException when maxExclusive &lt;= 0.
        /// </summary>
        public int NextInt(int maxExclusive)
        {
            if (maxExclusive <= 0) throw new ArgumentOutOfRangeException(nameof(maxExclusive), "must be > 0");
            ulong high = NextULong() >> 32;
            return (int)((high * (ulong)maxExclusive) >> 32);
        }

        /// <summary>Uniform double in [a, b) (a + (b - a) * NextDouble(); [b, a) when b &lt; a).</summary>
        public double Range(double a, double b)
        {
            return a + (b - a) * NextDouble();
        }
    }
}
