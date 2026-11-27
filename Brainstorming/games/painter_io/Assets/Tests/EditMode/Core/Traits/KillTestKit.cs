// Owned by kill-core (wave D-2). Shared helpers of the kill reward tests (docs/BIOME_TRAITS.md section 7). Pure NUnit +
// PainterIO.Core (no UnityEngine), NUnit 3.5 features only.
using PainterIO.Core;

namespace PainterIO.Tests
{
    internal static class KillTestKit
    {
        /// <summary>
        /// The victim trails East on y = from.Y over 'length' u (DebugSetTrail; its controller must keep heading East) and
        /// gets a spark of 'killer' now, placed so that the spark reaches its head 'catchIn' seconds later (closed form with
        /// the victim's SpeedMultiplier and SimConfig.SparkSpeedOf, as the Simulation fixes it at the cut).
        /// </summary>
        public static void ForceChase(Simulation sim, int victim, int killer, Vec2d from, double length, double catchIn)
        {
            sim.DebugSetTrail(victim, new[] { from, from + new Vec2d(length, 0.0) });
            PlayerState v = sim.Players[victim];
            double closing = sim.Config.SparkSpeedOf(v.SpeedMultiplier) - sim.Config.PawnSpeed * v.SpeedMultiplier;
            sim.DebugForceCut(victim, length - catchIn * closing, killer);
        }

        /// <summary>ForceChase at the first tick with Time &gt;= time (a multiple of 1/6 s in the cross-rate tests).</summary>
        public static void ForceChaseAt(Simulation sim, double time, int victim, int killer, Vec2d from, double length, double catchIn)
        {
            bool done = false;
            sim.BeforeTick += s =>
            {
                if (done || s.Time < time - 1e-9) return;
                done = true;
                ForceChase(s, victim, killer, from, length, catchIn);
            };
        }

        /// <summary>
        /// At the first tick with Time &gt;= time, the victim is teleported to a 2 u trail starting at 'far' and gets a spark
        /// of 'killer' beyond its head: it is caught at that tick start + EventEpsilonSeconds (a kill of 'killer').
        /// </summary>
        public static void ForceKillAt(Simulation sim, double time, int victim, int killer, Vec2d far)
        {
            bool done = false;
            sim.BeforeTick += s =>
            {
                if (done || s.Time < time - 1e-9) return;
                done = true;
                s.DebugSetTrail(victim, new[] { far, far + new Vec2d(2.0, 0.0) });
                s.DebugForceCut(victim, 3.0, killer);
            };
        }
    }
}
