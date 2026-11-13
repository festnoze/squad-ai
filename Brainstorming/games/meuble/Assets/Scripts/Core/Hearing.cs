using UnityEngine;

namespace Meuble.Core
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
        /// The radius each kind of noise is emitted with (Tuning; docs/CONTRACT_M4.md section 2): hop 2.0 m,
        /// creak 7 m, topple 3.5 m, click 2.5 m, roll 1.2 m. One source for GameState and the level audit.
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
                default:
                    return Tuning.HopNoiseRadius;
            }
        }

        /// <summary>
        /// True when this kind of noise retargets an inhabitant that is already Alerted: only a Creak
        /// (PRD 4.5). Every other kind, the M4 ones included, alerts in Routine only, like a hop.
        /// </summary>
        public static bool RetargetsAlerted(NoiseKind kind)
        {
            return kind == NoiseKind.Creak;
        }
    }
}
