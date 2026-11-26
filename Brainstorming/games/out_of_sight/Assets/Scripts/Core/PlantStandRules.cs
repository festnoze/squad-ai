using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// NEWFURN (docs/next/progress/NEWFURN.md): the rules of a body that are not <see cref="BodyDef"/> members. BodyDef's member
    /// list is the contract table (CoreM5BBodyTests compares every member of a row), so the plant stand's extra traits live
    /// here, keyed by the body's kind: every other body keeps exactly its old numbers.
    /// </summary>
    public static class BodyRules
    {
        /// <summary>The factor on the difficulty's creak fill time: <see cref="Tuning.PlantStandCreakFactor"/> for the plant stand, 1 otherwise.</summary>
        public static float CreakFillFactor(BodyDef body)
        {
            return body != null && body.Kind == BodyKinds.PlantStand ? Tuning.PlantStandCreakFactor : 1f; // MUTATION:STAND_CREAK
        }

        /// <summary>
        /// The seconds the creak gauge of <paramref name="body"/> takes from 0 to 1 when the difficulty gives
        /// <paramref name="difficultyFill"/> (GameState sets CreakGauge.FillTime with it; the audit fills its gauge with it).
        /// Never under the warning, as CreakGauge.FillTime clamps it.
        /// </summary>
        public static float CreakFillTime(BodyDef body, float difficultyFill)
        {
            return Mathf.Max(Tuning.CreakWarning, difficultyFill * CreakFillFactor(body));
        }

        /// <summary>The hop rate (rad/s, the hop's sine): <see cref="Tuning.PlantStandHopFrequency"/> for the plant stand, else <see cref="Tuning.HopFrequency"/>.</summary>
        public static float HopFrequency(BodyDef body)
        {
            return body != null && body.Kind == BodyKinds.PlantStand ? Tuning.PlantStandHopFrequency : Tuning.HopFrequency;
        }
    }

    /// <summary>
    /// NEWFURN: the load kinds of <c>player.load</c> and what each one does. The vase, the books and the potted plant are the
    /// M5 loads (CONTRACT_M5 6, 16.5: <see cref="Tuning.LoadHeight"/> tall, they fall at <see cref="Tuning.LoadFallDeltaV"/>).
    /// The banana pot is the plant stand's own: taller (<see cref="Tuning.BananaLoadHeight"/>), it falls at a smaller jolt
    /// (<see cref="Tuning.BananaFallDeltaV"/>), and its fall calls the nearest human to it (<see cref="SummonRule"/>). It rides
    /// only on the plant stand (the validator says so), whose speed it is tuned for.
    /// </summary>
    public static class LoadKinds
    {
        public const string Vase = "vase";
        public const string Books = "books";
        public const string Plant = "plant";
        public const string Banana = "banana";

        /// <summary>Every load kind, the M5 ones first.</summary>
        public static readonly string[] All = { Vase, Books, Plant, Banana };

        /// <summary>True for a load kind.</summary>
        public static bool IsKind(string kind)
        {
            return kind == Vase || kind == Books || kind == Plant || kind == Banana;
        }

        /// <summary>How much taller the sample box grows while the load rides: BananaLoadHeight for the banana pot, else LoadHeight.</summary>
        public static float HeightOf(string kind)
        {
            return kind == Banana ? Tuning.BananaLoadHeight : Tuning.LoadHeight; // MUTATION:BANANA_HEIGHT
        }

        /// <summary>The velocity change over LoadWindow at which the load falls (m/s): BananaFallDeltaV for the banana pot, else LoadFallDeltaV.</summary>
        public static float FallDeltaVOf(string kind)
        {
            return kind == Banana ? Tuning.BananaFallDeltaV : Tuning.LoadFallDeltaV; // MUTATION:BANANA_FALL
        }

        /// <summary>
        /// The level audit's refusal for the load (M5 5B.1 m9): the fall threshold less the same margin the M5 loads keep
        /// (<see cref="Tuning.LoadFallDeltaV"/> - <see cref="Tuning.AuditLoadDeltaV"/>, 0.1 m/s), so a vase gives exactly
        /// AuditLoadDeltaV.
        /// </summary>
        public static float AuditDeltaVOf(string kind)
        {
            return FallDeltaVOf(kind) - (Tuning.LoadFallDeltaV - Tuning.AuditLoadDeltaV);
        }

        /// <summary>The load's fall calls the nearest human to it (the banana pot only).</summary>
        public static bool CallsNearestHuman(string kind)
        {
            return kind == Banana; // MUTATION:BANANA_CALLS
        }

        /// <summary>
        /// The load may ride on a body of <paramref name="bodyKind"/>: the banana pot only on the plant stand; the M5 loads on
        /// any body but the floor lamp and the rocking chair (the validator's M5 rule); the plant stand carries only its pot.
        /// </summary>
        public static bool Fits(string kind, string bodyKind)
        {
            string body = BodyKinds.Of(bodyKind);
            if (kind == Banana)
            {
                return body == BodyKinds.PlantStand;
            }
            return body != BodyKinds.FloorLamp && body != BodyKinds.RockingChair && body != BodyKinds.PlantStand;
        }
    }

    /// <summary>
    /// NEWFURN: the irrevocable call of a fallen banana pot (GameState.StepSummon). The nearest human by walking distance
    /// (the path the household's planner gives, through the doors as they are, from any room, with no distance limit) among
    /// those free to come (a human in Routine or Alerted, not frozen, with memory: never the dog) drops whatever it was doing
    /// and walks to the pot; nothing calls it off. Pure helpers, so the choice is testable without a scene.
    /// </summary>
    public static class SummonRule
    {
        /// <summary>The length of a walk from <paramref name="from"/> along <paramref name="corners"/> (planar), metres.</summary>
        public static float PathLength(Vector3 from, IList<Vector3> corners)
        {
            float length = 0f;
            Vector3 previous = YawMath.Planar(from);
            int n = corners != null ? corners.Count : 0;
            for (int i = 0; i < n; i++)
            {
                Vector3 corner = YawMath.Planar(corners[i]);
                length += (corner - previous).magnitude;
                previous = corner;
            }
            return length;
        }

        /// <summary>
        /// The walking distance from <paramref name="from"/> to <paramref name="to"/> with <paramref name="planner"/>
        /// (<paramref name="scratch"/> receives the corners): the path's length, plus the straight rest from its last corner when
        /// the planner stops short of the target; +infinity when there is no path at all. A null planner is the straight line.
        /// </summary>
        public static float WalkDistance(IPathPlanner planner, Vector3 from, Vector3 to, List<Vector3> scratch)
        {
            Vector3 a = YawMath.Planar(from);
            Vector3 b = YawMath.Planar(to);
            if (planner == null)
            {
                return (b - a).magnitude;
            }
            scratch.Clear();
            if (!planner.TryPlan(a, b, scratch))
            {
                return float.PositiveInfinity;
            }
            float length = PathLength(a, scratch);
            Vector3 end = scratch.Count > 0 ? YawMath.Planar(scratch[scratch.Count - 1]) : a;
            return length + (b - end).magnitude;
        }

        /// <summary>
        /// The index of the nearest eligible candidate: the smallest finite distance among those <paramref name="eligible"/>
        /// says may come, the lower index on a tie; -1 when nobody may come or nobody has a path.
        /// </summary>
        public static int Nearest(IList<float> distances, IList<bool> eligible)
        {
            int best = -1;
            float bestDistance = float.PositiveInfinity;
            int n = distances != null ? distances.Count : 0;
            for (int i = 0; i < n; i++)
            {
                if (eligible == null || i >= eligible.Count || !eligible[i])
                {
                    continue;
                }
                float d = distances[i];
                if (float.IsNaN(d) || float.IsInfinity(d))
                {
                    continue;
                }
                if (d < bestDistance) // MUTATION:SUMMON_NEAREST
                {
                    best = i;
                    bestDistance = d;
                }
            }
            return best;
        }

        /// <summary>
        /// May this routine answer the call now: a human with memory (the dog never comes), not startled nor frozen, in Routine
        /// or Alerted (one busy investigating, carrying, switching a lamp on or putting a clue away is not free yet).
        /// </summary>
        public static bool MayCome(InhabitantRoutine routine)
        {
            if (routine == null || routine.IsFrozen || routine.IsStartled || !routine.Personality.Memory)
            {
                return false;
            }
            InhabitantMode mode = routine.Mode;
            return mode == InhabitantMode.Routine || mode == InhabitantMode.Alerted;
        }
    }
}
