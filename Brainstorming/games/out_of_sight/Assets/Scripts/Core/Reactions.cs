using System;
using System.Collections.Generic;

namespace OutOfSight.Core
{
    /// <summary>
    /// Idea 7 (BUBBLES): the moments an inhabitant (or a robot) says a short comic line in a speech bubble over its head.
    /// GameState raises them (<c>GameState.Reacted</c>, <c>GameState.RobotBumped</c>); the near miss is detected by the
    /// bubbles view itself from the visions. The sentinel's metronome glances raise nothing: a near miss needs a walk.
    /// </summary>
    public enum ReactionKind
    {
        /// <summary>A walking cone swept over the furniture while it stood still, then lost it: nothing seen wrong.</summary>
        NearMiss,
        /// <summary>The furniture was noticed out of place (a discovery of the displacement memory).</summary>
        Noticed,
        /// <summary>The remembered spot was found empty while the furniture hides in a wardrobe.</summary>
        SpotEmpty,
        /// <summary>The carrier put the furniture back on its slot.</summary>
        PutBack,
        /// <summary>A sitter sat on the player furniture (Granny has her own lines).</summary>
        SatOn,
        /// <summary>The dog barks: at the moving furniture, and while it pins it.</summary>
        DogBark,
        /// <summary>The human the dog called is on its way.</summary>
        DogCall,
        /// <summary>The catch: the fail panel's "VU !" moment, said by the inhabitant that saw it.</summary>
        Caught,
        /// <summary>An inhabitant opened a household door on its walk (openedByInhabitants).</summary>
        DoorOpened,
        /// <summary>A robot vacuum ran into the furniture.</summary>
        RobotBump,
        /// <summary>DOGCARRY: the dog grips the furniture and starts dragging it home (the dog's own lines only).</summary>
        DogDrag,
        /// <summary>NEWFURN: a fallen banana pot called this human, who drops everything and comes to look.</summary>
        Summoned,
    }

    /// <summary>
    /// Idea 7 (BUBBLES): the text tables of the reactions, read from <see cref="Strings"/>. A line's key is
    /// <c>react.&lt;kind&gt;.&lt;personality&gt;.&lt;n&gt;</c>: the kind id of <see cref="KindId"/>, a personality id of
    /// <see cref="PersonalityDef"/> (or <see cref="Robot"/> for a robot), and n from 1 up. A personality without lines for a
    /// kind falls back on the <see cref="PersonalityDef.Default"/> lines of that kind. The index is built once from
    /// <see cref="Strings.Keys"/>, so adding a variant is adding one string; the choice itself is the caller's seeded random
    /// (<see cref="Pick"/>), so tests are deterministic. Nothing here allocates after the first call.
    /// </summary>
    public static class Reactions
    {
        public const string Prefix = "react.";
        public const string Robot = "robot";
        /// <summary>The variant count every (kind, personality) pair with lines must have (the test checks it).</summary>
        public const int MinVariants = 3;
        public const int MaxVariants = 6;
        /// <summary>The most words a line may have (the test checks it): a bubble is read in a glance.</summary>
        public const int MaxWords = 5;

        private static readonly string[] KindIds =
        {
            "nearMiss", "noticed", "spotEmpty", "putBack", "satOn", "dogBark", "dogCall", "caught", "doorOpened", "robotBump", "dogDrag", "summoned",
        };

        private static readonly string[] Empty = new string[0];
        private static Dictionary<string, string[]> index;

        /// <summary>Every kind, in enum order.</summary>
        public static readonly ReactionKind[] AllKinds = (ReactionKind[])Enum.GetValues(typeof(ReactionKind));

        /// <summary>The key segment of a kind ("nearMiss", "noticed", ...).</summary>
        public static string KindId(ReactionKind kind)
        {
            int k = (int)kind;
            return k >= 0 && k < KindIds.Length ? KindIds[k] : KindIds[0];
        }

        /// <summary>
        /// The keys of the lines of <paramref name="kind"/> for <paramref name="personality"/> (null: default), in variant order;
        /// the default personality's lines when it has none of its own; empty when nobody has any.
        /// </summary>
        public static string[] Keys(ReactionKind kind, string personality)
        {
            Dictionary<string, string[]> table = Index;
            string own = KindId(kind) + "." + (string.IsNullOrEmpty(personality) ? PersonalityDef.Default : personality);
            if (table.TryGetValue(own, out string[] keys) && keys.Length > 0)
            {
                return keys;
            }
            string fallback = KindId(kind) + "." + PersonalityDef.Default;
            return table.TryGetValue(fallback, out keys) ? keys : Empty;
        }

        /// <summary>The number of variants <see cref="Keys"/> gives (0: this kind has no line for anyone).</summary>
        public static int Count(ReactionKind kind, string personality)
        {
            return Keys(kind, personality).Length;
        }

        /// <summary>True when <paramref name="personality"/> has lines of its own for <paramref name="kind"/> (no fallback).</summary>
        public static bool HasOwn(ReactionKind kind, string personality)
        {
            return Index.TryGetValue(KindId(kind) + "." + (personality ?? PersonalityDef.Default), out string[] keys) && keys.Length > 0;
        }

        /// <summary>
        /// One line of <paramref name="kind"/> for <paramref name="personality"/> in the current language, chosen with
        /// <paramref name="random"/> (<see cref="Random.Next(int)"/> once), never the variant <paramref name="avoid"/> when there
        /// are at least two. Null when the kind has no line. The returned string is the table's own instance: no allocation.
        /// </summary>
        public static string Pick(ReactionKind kind, string personality, Random random, int avoid, out int variant)
        {
            string[] keys = Keys(kind, personality);
            variant = -1;
            if (keys.Length == 0)
            {
                return null;
            }
            variant = random != null ? random.Next(keys.Length) : 0;
            if (keys.Length > 1 && variant == avoid)
            {
                variant = (variant + 1) % keys.Length;
            }
            return Strings.Get(keys[variant]);
        }

        /// <summary><see cref="Pick(ReactionKind, string, Random, int, out int)"/> with nothing to avoid.</summary>
        public static string Pick(ReactionKind kind, string personality, Random random)
        {
            return Pick(kind, personality, random, -1, out _);
        }

        /// <summary>Every (kind id, personality) pair that has lines, as "kind.personality" (tests).</summary>
        public static IEnumerable<string> Groups => Index.Keys;

        private static Dictionary<string, string[]> Index => index ?? (index = Build());

        /// <summary>Tests: rebuilds the index (after the Strings table changed in a test, never in the game).</summary>
        public static void Rebuild()
        {
            index = null;
        }

        private static Dictionary<string, string[]> Build()
        {
            var lists = new Dictionary<string, SortedList<int, string>>();
            foreach (string key in Strings.Keys)
            {
                if (!key.StartsWith(Prefix, StringComparison.Ordinal))
                {
                    continue;
                }
                // react.<kind>.<personality>.<n>
                string[] parts = key.Split('.');
                if (parts.Length != 4 || !int.TryParse(parts[3], out int n))
                {
                    continue;
                }
                string group = parts[1] + "." + parts[2];
                if (!lists.TryGetValue(group, out SortedList<int, string> list))
                {
                    list = new SortedList<int, string>();
                    lists[group] = list;
                }
                list[n] = key;
            }
            var built = new Dictionary<string, string[]>(lists.Count);
            foreach (KeyValuePair<string, SortedList<int, string>> entry in lists)
            {
                var keys = new string[entry.Value.Count];
                entry.Value.Values.CopyTo(keys, 0);
                built[entry.Key] = keys;
            }
            return built;
        }
    }
}
