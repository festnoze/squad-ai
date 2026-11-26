using UnityEngine;

namespace OutOfSight.Core
{
    public enum NoiseKind
    {
        Hop,
        Creak,
        // M4 (docs/CONTRACT_M4.md section 2): they behave like Hop. They alert an inhabitant in Routine only;
        // an Alerted inhabitant ignores them, and only a Creak retargets it.
        Topple,
        Click,
        Roll,
        // M5 (docs/CONTRACT_M5.md): a dog's bark (at the dog) and a fallen load's crash. Both retarget like a creak.
        Bark,
        Crash,
    }

    /// <summary>A noise heard by every inhabitant within <see cref="Radius"/> of <see cref="Position"/>.</summary>
    public struct NoiseEvent
    {
        public Vector3 Position;
        public float Radius;
        public NoiseKind Kind;

        public NoiseEvent(Vector3 position, float radius, NoiseKind kind)
        {
            Position = position;
            Radius = radius;
            Kind = kind;
        }
    }

    /// <summary>Hearing (PRD 4.5, docs/CONTRACT_M2.md 3.2). Walls do not block sound in M2.</summary>
    public static class Hearing
    {
        // Rounding margin only: a listener authored exactly on the radius hears despite float error.
        private const float Epsilon = 1e-4f;

        /// <summary>True when the planar distance from the listener to the source is at most the radius (inclusive).</summary>
        public static bool Hears(Vector3 listener, NoiseEvent e)
        {
            if (e.Radius < 0f)
            {
                return false;
            }
            return YawMath.Planar(listener - e.Position).magnitude <= e.Radius + Epsilon;
        }

        /// <summary>
        /// M5 (CONTRACT_M5 3): <see cref="Hears(Vector3, NoiseEvent)"/> for a listener whose personality scales every noise
        /// radius by <paramref name="factor"/> (1 for default, 0.5 for the hurried, 0.4 for the teen). A factor of 0 or
        /// below (the dog) hears nothing; a factor of 1 is the M2 rule exactly.
        /// </summary>
        public static bool Hears(Vector3 listener, NoiseEvent e, float factor)
        {
            if (e.Radius < 0f || factor <= 0f)
            {
                return false;
            }
            return YawMath.Planar(listener - e.Position).magnitude <= e.Radius * factor + Epsilon;
        }

        /// <summary>
        /// M5 (CONTRACT_M5 4, PRD 4.8): the robot's hum. A noise of a maskable kind (<see cref="IsMaskable"/>: a hop, a roll
        /// or a click) made at <paramref name="at"/> is masked, so no noise event is emitted, when the planar distance to
        /// any robot of <paramref name="robots"/> is at most <see cref="Tuning.RobotHumRadius"/> (2.5 m, inclusive). A
        /// topple, a creak, a crash and a bark are never masked. Null or empty robots mask nothing. The one rule for
        /// GameState and the level audit.
        /// </summary>
        public static bool IsMasked(NoiseKind kind, Vector3 at, System.Collections.Generic.IReadOnlyList<Vector3> robots)
        {
            if (robots == null || !IsMaskable(kind))
            {
                return false;
            }
            float hum = Tuning.RobotHumRadius; // MUTATION:HUM_NONE
            for (int i = 0; i < robots.Count; i++)
            {
                if (YawMath.Planar(at - robots[i]).magnitude <= hum)
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// M5 (CONTRACT_M5 4): the kinds the robot's hum can mask, the small noises of travel and of the lamp switch: Hop,
        /// Roll and Click. Topple, Creak, Crash and Bark are always heard.
        /// </summary>
        public static bool IsMaskable(NoiseKind kind)
        {
            switch (kind)
            {
                case NoiseKind.Hop:
                case NoiseKind.Roll:
                case NoiseKind.Click:
                    return true;
                default:
                    return false; // MUTATION:HUM_CREAK
            }
        }

        /// <summary>
        /// The radius each kind of noise is emitted with (Tuning; docs/CONTRACT_M4.md section 2): hop 2.0 m,
        /// creak 7 m, topple 3.5 m, click 2.5 m, roll 1.2 m; M5 bark 6 m and crash 6 m. One source for GameState and the
        /// level audit.
        /// </summary>
        public static float RadiusOf(NoiseKind kind)
        {
            switch (kind)
            {
                case NoiseKind.Creak:
                    return Tuning.CreakRadius;
                case NoiseKind.Topple:
                    return Tuning.ToppleNoiseRadius;
                case NoiseKind.Click:
                    return Tuning.LampClickRadius;
                case NoiseKind.Roll:
                    return Tuning.RollNoiseRadius;
                case NoiseKind.Bark:
                    return Tuning.BarkRadius;
                case NoiseKind.Crash:
                    return Tuning.CrashRadius;
                default:
                    return Tuning.HopNoiseRadius;
            }
        }

        /// <summary>
        /// True when this kind of noise retargets an inhabitant that is already Alerted: a Creak (PRD 4.5), and since M5 a
        /// dog's Bark and a fallen load's Crash, which alert like a creak (CONTRACT_M5_v3 4, CONTRACT_M5 6). Every other
        /// kind (hop, topple, click, roll) alerts in Routine only. The one rule for InhabitantRoutine.Alert and GameState.
        /// </summary>
        public static bool RetargetsAlerted(NoiseKind kind)
        {
            return kind == NoiseKind.Creak || kind == NoiseKind.Bark || kind == NoiseKind.Crash;
        }
    }
}
