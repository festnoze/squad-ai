using UnityEngine;

namespace Meuble.Core
{
    /// <summary>
    /// Suspicion of one inhabitant (PRD 4.4, docs/CONTRACT_M2.md 3.1). Each discovery adds
    /// <see cref="Tuning.SuspicionPerDiscovery"/>; the level is lost when the value reaches
    /// <see cref="Tuning.SuspicionLose"/>. The value is not clamped at the top: three discoveries read 1.02.
    /// Whether the meter may decay on a step (only in Routine or Alerted) is decided by GameState, not here.
    /// </summary>
    public sealed class SuspicionMeter
    {
        // 0.34 + 0.34 + 0.34 after some decay can land a hair under 1 in float: the epsilon keeps "reaches 1" exact.
        private const float Epsilon = 1e-4f;

        public float Value { get; private set; }

        /// <summary>Latched: once lost, the meter is frozen until <see cref="Reset"/>.</summary>
        public bool Lost { get; private set; }

        public void AddDiscovery()
        {
            if (Lost)
            {
                return;
            }
            Value += Tuning.SuspicionPerDiscovery;
            if (Value >= Tuning.SuspicionLose - Epsilon)
            {
                Lost = true;
            }
        }

        /// <summary>Decays by <see cref="Tuning.SuspicionDecayPerSecond"/> over one fixed step, clamped at 0.</summary>
        public void Step(float dt)
        {
            if (Lost || dt <= 0f)
            {
                return;
            }
            Value = Mathf.Max(0f, Value - Tuning.SuspicionDecayPerSecond * dt);
        }

        public void Reset()
        {
            Value = 0f;
            Lost = false;
        }
    }
}
