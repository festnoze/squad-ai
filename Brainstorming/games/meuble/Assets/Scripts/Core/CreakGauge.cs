using UnityEngine;

namespace Meuble.Core
{
    /// <summary>
    /// Creak gauge of the player furniture (PRD 4.6, docs/CONTRACT_M2.md 3.3). It fills from 0 to 1 in
    /// <see cref="Tuning.CreakFillTime"/> while the furniture is still, drains from 1 to 0 in
    /// <see cref="Tuning.CreakDrainTime"/> while it moves, and creaks (then resets to 0) when it reaches 1.
    /// It does nothing while the furniture is carried, while it is paused (sat on, M4), or during the first
    /// <see cref="Tuning.CreakStartDelay"/> seconds of the level.
    /// </summary>
    public sealed class CreakGauge
    {
        // 1000 steps of 0.02 s add up to 0.99999 in float: the epsilon makes "20 s still creaks" land on step 1000.
        private const float Epsilon = 1e-4f;

        /// <summary>Gauge value at which the warning starts: the last <see cref="Tuning.CreakWarning"/> seconds.</summary>
        private const float WarningStart = 1f - Tuning.CreakWarning / Tuning.CreakFillTime;

        /// <summary>From 0 to 1.</summary>
        public float Value { get; private set; }

        /// <summary>True when the last step filled the gauge: still, not carried, after the start delay.</summary>
        public bool Filling { get; private set; }

        /// <summary>True during the last <see cref="Tuning.CreakWarning"/> seconds of filling before a creak.</summary>
        public bool Warning => Filling && Value >= WarningStart - Epsilon;

        /// <summary>Seconds left before the creak while filling; float.PositiveInfinity otherwise.</summary>
        public float SecondsToCreak => Filling ? Mathf.Max(0f, 1f - Value) * Tuning.CreakFillTime : float.PositiveInfinity;

        /// <summary>
        /// M4 (docs/CONTRACT_M4.md section 3, amendment 9.11): <paramref name="paused"/> (sat on, hidden later)
        /// freezes the gauge exactly like being carried: no fill, no drain, no warning, no creak, and the value is
        /// kept for when the pause ends. With <paramref name="paused"/> false this is the four argument Step.
        /// </summary>
        public bool Step(float dt, bool moving, bool carried, float levelTime, bool paused)
        {
            return Step(dt, moving, carried || paused, levelTime); // MUTATION:PAUSED (a mutation drops "|| paused")
        }

        /// <summary>
        /// Advances one fixed step and returns true on the step the furniture creaks.
        /// <paramref name="moving"/> is the <see cref="MotionRule"/> predicate of this step.
        /// <paramref name="levelTime"/> is the level time at the start of this step (the play time before it), so
        /// a furniture still from the level start fills on the steps that start at 5.00 s and creaks on the
        /// step that ends at 25.00 s.
        /// </summary>
        public bool Step(float dt, bool moving, bool carried, float levelTime)
        {
            Filling = false;
            if (carried || dt <= 0f || levelTime < Tuning.CreakStartDelay - Epsilon)
            {
                return false;
            }
            if (moving)
            {
                Value = Mathf.Max(0f, Value - dt / Tuning.CreakDrainTime);
                return false;
            }
            Filling = true;
            Value += dt / Tuning.CreakFillTime;
            if (Value >= 1f - Epsilon)
            {
                Value = 0f;
                return true;
            }
            return false;
        }

        public void Reset()
        {
            Value = 0f;
            Filling = false;
        }
    }
}
