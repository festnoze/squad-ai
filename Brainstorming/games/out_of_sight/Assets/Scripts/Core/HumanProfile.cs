using System;
using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// HUMANAUDIT (docs/next/progress/HUMANAUDIT.md): the optional "human" profile of the level audit
    /// ("-profile human"; the default profile, "strict", is the audit as it was). The strict audit finds the earliest
    /// schedule a perfect player could run: it dodges a cone with a 0.4 s hop, freezes 0.2 s, and sets off the very sample a
    /// cone turns away. The human profile keeps every rule of the strict audit and adds what a human player cannot do:
    /// <list type="bullet">
    /// <item>reaction: a move from rest starts only once both its cells have been unseen (at the audit's margin) for
    /// <see cref="ReactionTime"/>, and a doorway an inhabitant opened is crossed only <see cref="ReactionTime"/> after it
    /// opened (<see cref="ReactionMask"/>);</item>
    /// <item>no sub-second freeze: every run of still samples lasts at least <see cref="MinPause"/>;</item>
    /// <item>no micro-dash: a run of moves that starts from rest covers at least <see cref="MinMoveCells"/> cells before it
    /// stops or freezes (an in-place action such as opening a door or hiding may follow a single cell);</item>
    /// <item>no lamp flicker: two toggles never follow each other directly (a toggled lamp waits, moves or acts first).</item>
    /// </list>
    /// No speed margin: the audit's cell costs are whole samples tied to the replay (the rock plan, the load model), and the
    /// reaction delay already slows every start. The search applies these rules; <see cref="Breaches"/> checks a schedule
    /// against them (the audit's consistency check and the EditMode tests).
    /// </summary>
    public static class HumanProfile
    {
        /// <summary>The profile names of the "-profile" flag.</summary>
        public const string Strict = "strict";
        public const string Human = "human";

        /// <summary>The time a human needs to react to a cone turning away or to a door opening.</summary>
        public const float ReactionTime = 0.3f;

        /// <summary>The shortest still run a human holds (no sub-second freeze).</summary>
        public const float MinPause = 1.0f;

        /// <summary>
        /// The fewest cells a run of moves from rest covers before it stops or freezes (no micro-dash). The audit's search
        /// tracks this with one bit, so it supports exactly 2; <see cref="Breaches"/> takes any value.
        /// </summary>
        public const int MinMoveCells = 2;

        /// <summary>One step of a schedule as the human rules read it.</summary>
        public enum Step
        {
            /// <summary>A move of one cell.</summary>
            Move,
            /// <summary>The end of a run that costs samples (the office chair's glide, the rocking chair's rock).</summary>
            Stop,
            /// <summary>Still, not hidden.</summary>
            Still,
            /// <summary>The lamp switches itself.</summary>
            Toggle,
            /// <summary>Any other in-place action: an opening, a hide, a leave, time hidden in a wardrobe.</summary>
            Action,
        }

        /// <summary>A breach of the human rules: the index of the step that ends the run, the kind, the run's length.</summary>
        public struct Breach
        {
            public int Index;
            /// <summary>"freeze" (a still run under the minimum), "dash" (a run of moves under the minimum) or "flicker".</summary>
            public string Kind;
            /// <summary>Samples for a freeze, cells for a dash, 2 for a flicker.</summary>
            public int Length;
        }

        /// <summary>Parses the "-profile" value: true for "human", false for "strict" (or no value); false on anything else.</summary>
        public static bool TryParse(string value, out bool human)
        {
            human = false;
            if (string.IsNullOrEmpty(value) || string.Equals(value, Strict, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
            if (string.Equals(value, Human, StringComparison.OrdinalIgnoreCase))
            {
                human = true;
                return true;
            }
            return false;
        }

        /// <summary>A duration in whole samples of <paramref name="sampleSeconds"/>.</summary>
        public static int Samples(float seconds, float sampleSeconds)
        {
            return Mathf.Max(0, Mathf.RoundToInt(seconds / sampleSeconds));
        }

        /// <summary>
        /// The door mask a human may act on at sample <paramref name="t"/>: <paramref name="mask"/> without the leaves an
        /// inhabitant opened in the last <paramref name="reactionSamples"/> samples (<paramref name="autoOpen"/>[s] is the mask
        /// of the inhabitant leaves open at sample s, growing with s; null when no inhabitant opens a leaf).
        /// </summary>
        public static int ReactionMask(int mask, int[] autoOpen, int t, int reactionSamples)
        {
            if (autoOpen == null || reactionSamples <= 0 || t < 0 || t >= autoOpen.Length)
            {
                return mask;
            }
            int before = t - reactionSamples >= 0 ? autoOpen[t - reactionSamples] : 0;
            int fresh = autoOpen[t] & ~before; // MUTATION:HUMAN_REACTION_DOOR
            return mask & ~fresh;
        }

        /// <summary>
        /// The breaches of the human rules in a schedule given as steps and their lengths in samples (both of the same count;
        /// the start of the schedule is not a step). A still run is every consecutive <see cref="Step.Still"/> step, a run of
        /// moves every consecutive <see cref="Step.Move"/> step. Empty when the schedule is human.
        /// </summary>
        public static List<Breach> Breaches(IList<Step> steps, IList<int> samples, int minPauseSamples, int minMoveCells)
        {
            if (steps == null || samples == null || steps.Count != samples.Count)
            {
                throw new ArgumentException("steps and samples must have the same count");
            }
            var found = new List<Breach>();
            int i = 0;
            while (i < steps.Count)
            {
                Step kind = steps[i];
                int j = i;
                int length = 0;
                while (j < steps.Count && steps[j] == kind && (kind == Step.Still || kind == Step.Move))
                {
                    length += kind == Step.Still ? samples[j] : 1;
                    j++;
                }
                if (kind == Step.Still)
                {
                    if (length < minPauseSamples) // MUTATION:HUMAN_FREEZE
                    {
                        found.Add(new Breach { Index = j - 1, Kind = "freeze", Length = length });
                    }
                    i = j;
                    continue;
                }
                if (kind == Step.Move)
                {
                    // A run of moves too short to be a human dash, ended by a stop or a freeze (an action or the exit is fine).
                    bool stops = j < steps.Count && (steps[j] == Step.Still || steps[j] == Step.Stop);
                    if (length < minMoveCells && stops)
                    {
                        found.Add(new Breach { Index = j - 1, Kind = "dash", Length = length });
                    }
                    i = j;
                    continue;
                }
                if (kind == Step.Toggle && i + 1 < steps.Count && steps[i + 1] == Step.Toggle)
                {
                    found.Add(new Breach { Index = i + 1, Kind = "flicker", Length = 2 });
                }
                i++;
            }
            return found;
        }
    }
}
