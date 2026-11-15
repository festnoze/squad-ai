using System.Collections.Generic;
using UnityEngine;

namespace Meuble.Core
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5.md 3 and 16.7): the station order of a routine.
    /// <list type="bullet">
    /// <item><c>loop</c> (default, null and unknown too): the M1 cycle, start, start + 1, ... modulo n.</item>
    /// <item><c>pingpong</c>: there and back, 0, 1, ..., n - 1, n - 2, ..., 1, 0, 1, ... from the start station, going up
    /// first; the direction is part of the state.</item>
    /// <item><c>wander</c>: the next station is drawn by <see cref="WanderNext"/>, starting from x = seed, among the n - 1
    /// stations other than the current one (n of 3 or more, validator).</item>
    /// </list>
    /// Draws are indexed by visit: visit 0 is the start station (the level starts in its dwell), and the k-th visit is
    /// always the same station (<see cref="StationOrder"/>), whatever interrupted the routine.
    /// </summary>
    public static class RoutinePatterns
    {
        public const string Loop = "loop";
        public const string PingPong = "pingpong";
        public const string Wander = "wander";

        public static readonly string[] All = { Loop, PingPong, Wander };

        /// <summary>A known pattern id as is; null, empty and unknown ids give <see cref="Loop"/>.</summary>
        public static string Normalize(string pattern)
        {
            return pattern == PingPong || pattern == Wander ? pattern : Loop;
        }

        /// <summary>
        /// Advances the generator, x = (1103515245 x + 12345) and 0x7FFFFFFF, then draws the next station among the
        /// n - 1 others: an index at or above <paramref name="current"/> is shifted by one. Requires n of 3 or more
        /// (with n = 2 it alternates, with n = 1 it stays on 0).
        /// </summary>
        public static int WanderNext(ref int x, int current, int n)
        {
            x = (int)((1103515245L * x + 12345L) & 0x7FFFFFFF);
            if (n < 2)
            {
                return 0;
            }
            int next = (x >> 16) % (n - 1);
            return next >= current ? next + 1 : next;
        }

        /// <summary>
        /// Every ordered pair (from, to) of stations the pattern can produce, in a fixed order: n pairs for a loop,
        /// 2 (n - 1) for pingpong, n (n - 1) for wander (CONTRACT_M5 16.7). The routine freezes the walk of each one, and
        /// the audit checks each one against closed leaves. With one station, the loop gives the empty walk (0, 0).
        /// </summary>
        public static List<Vector2Int> ReachablePairs(string pattern, int n)
        {
            var pairs = new List<Vector2Int>();
            if (n <= 0)
            {
                return pairs;
            }
            switch (Normalize(pattern))
            {
                case PingPong:
                    for (int i = 0; i + 1 < n; i++)
                    {
                        pairs.Add(new Vector2Int(i, i + 1));
                        pairs.Add(new Vector2Int(i + 1, i));
                    }
                    break;
                case Wander:
                    for (int i = 0; i < n; i++)
                    {
                        for (int j = 0; j < n; j++)
                        {
                            if (i != j)
                            {
                                pairs.Add(new Vector2Int(i, j));
                            }
                        }
                    }
                    break;
                default:
                    for (int i = 0; i < n; i++)
                    {
                        pairs.Add(new Vector2Int(i, (i + 1) % n));
                    }
                    break;
            }
            return pairs;
        }
    }

    /// <summary>
    /// The station of every visit of one routine's pattern (CONTRACT_M5 16.7). Visits are drawn in order and kept, so
    /// <see cref="StationOf"/> gives the same station for a visit however often it is asked: a resume or an
    /// interruption reuses the station already drawn for its visit and never advances the draws. Deterministic: the
    /// same pattern, count, start and seed give the same order in the game, the audit and the tests.
    /// </summary>
    public sealed class StationOrder
    {
        private readonly List<int> visits = new List<int>();
        private int x;
        private int direction = 1;

        public string Pattern { get; }
        public int Count { get; }
        public int Seed { get; }

        /// <param name="pattern">"loop", "pingpong" or "wander"; null or unknown is a loop.</param>
        /// <param name="count">The number of stations.</param>
        /// <param name="start">The start station, visit 0.</param>
        /// <param name="seed">The wander seed, in [0, 2^31 - 1]; ignored by the other patterns.</param>
        public StationOrder(string pattern, int count, int start, int seed)
        {
            Pattern = RoutinePatterns.Normalize(pattern);
            Count = Mathf.Max(count, 0);
            Seed = seed;
            x = seed; // MUTATION:WANDER_SEED
            visits.Add(Count > 0 ? Mathf.Clamp(start, 0, Count - 1) : 0);
        }

        /// <summary>The station of visit <paramref name="visit"/> (0 is the start station; a negative visit reads as 0).</summary>
        public int StationOf(int visit)
        {
            if (visit < 0)
            {
                visit = 0;
            }
            while (visits.Count <= visit)
            {
                visits.Add(Next(visits[visits.Count - 1]));
            }
            return visits[visit];
        }

        /// <summary>The number of visits drawn so far, the start included.</summary>
        public int Drawn => visits.Count;

        private int Next(int current)
        {
            if (Count <= 1)
            {
                return 0;
            }
            switch (Pattern)
            {
                case RoutinePatterns.PingPong:
                {
                    int next = current + direction;
                    if (next < 0 || next >= Count)
                    {
                        direction = -direction;
                        next = current + direction;
                    }
                    return next;
                }
                case RoutinePatterns.Wander:
                    return RoutinePatterns.WanderNext(ref x, current, Count);
                default:
                    return (current + 1) % Count;
            }
        }
    }
}
