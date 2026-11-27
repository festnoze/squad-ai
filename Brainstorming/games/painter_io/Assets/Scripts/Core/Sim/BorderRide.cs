// Rule v1.9 (contract 33, designer request "border ride"): a head that runs along the arena boundary for more than
// SimConfig.BorderRideDelay seconds of sim time rides it at BorderRideFactor times its speed and, without a new steering
// input, keeps following the boundary around every corner. Called from EventResolver.BeginTick (section 6 step 1) only when
// SimConfig.BorderRide is On; with Off nothing here runs and the simulation is bit-identical to the one before v1.9.
using System;

namespace PainterIO.Core
{
    public static class BorderRide
    {
        /// <summary>
        /// A head is in contact with the boundary when its R4 step was constrained by the border (slide or hold), or when its
        /// end point lies within this distance (u) of the inset line (a head running exactly along the border, or stopped up
        /// to ArenaPolygon.MinBorderStep before it).
        /// </summary>
        public const double ContactTolerance = 0.02;

        /// <summary>
        /// A desired heading within this angle (radians, 20 degrees) of the one the ride last accepted is not a new input:
        /// the ride ignores it and keeps following the boundary (a held joystick wobbles by a few degrees).
        /// </summary>
        public const double InputTolerance = 20.0 * Math.PI / 180.0;

        /// <summary>A ride tick that advances less than this fraction of its step (a dead end) ends the ride.</summary>
        public const double MinProgress = 0.2;

        /// <summary>
        /// Section 6 step 1 motion of an alive player when the rule is on. step = the tick step of the normal motion
        /// (PawnSpeed x SpeedMultiplier x the behaviours' factor x Dt), hold = BorderHoldAngleRad, t0 / dt = the tick start
        /// time and length. Returns the full-step target and may set p.Heading (the boundary tangent while riding).
        /// - Chased (a spark on the trail): no ride, and no contact time accumulates (La Revanche keeps its 1.8x margin).
        /// - Riding: a new input that points into the interior by more than the hold angle (measured from the tangent) ends
        ///   the ride; a new input along or into the boundary keeps it (pushing along the boundary the other way reverses
        ///   it); otherwise the head follows the boundary for step x BorderRideFactor (Arena.FollowBorder). A ride that ends
        ///   moves normally for the whole tick, and the contact delay starts over.
        /// - Not riding: the R4 step; contact starts at the exact instant the straight path reaches the contact tolerance
        ///   (rate independent), and the ride starts at contact start + BorderRideDelay, inside the tick when it falls there
        ///   (the normal motion up to that instant, then the ride for the rest of the tick).
        /// </summary>
        internal static Vec2d Move(Simulation sim, PlayerState p, Vec2d a, double step, double hold, double t0, double dt)
        {
            SimConfig cfg = sim.Config;
            Arena arena = sim.Arena;
            if (p.Spark != null)
            {
                End(p);
                p.BorderContactStart = double.NaN;
                return arena.Step(a, Vec2d.FromAngle(p.Heading) * step, hold);
            }

            double rideStep = step * cfg.BorderRideFactor;
            if (p.BorderRiding)
            {
                if (KeepsRiding(arena, p, a, hold))
                {
                    Vec2d b = arena.FollowBorder(a, rideStep, p.BorderRideSign, out Vec2d dir);
                    if (Vec2d.Distance(a, b) >= MinProgress * rideStep)
                    {
                        if (dir.LengthSq > 0.0) p.Heading = dir.Angle();
                        return b;
                    }
                }
                End(p);
                p.BorderContactStart = double.NaN;
                return arena.Step(a, Vec2d.FromAngle(p.Heading) * step, hold);
            }

            Vec2d d = Vec2d.FromAngle(p.Heading) * step;
            Vec2d end = arena.Step(a, d, hold);
            if (!InContact(arena, a, d, end))
            {
                p.BorderContactStart = double.NaN;
                return end;
            }
            if (double.IsNaN(p.BorderContactStart)) p.BorderContactStart = t0 + dt * ContactFraction(arena, a, d);
            double rideAt = p.BorderContactStart + cfg.BorderRideDelay;
            if (!(rideAt < t0 + dt)) return end;

            // The ride starts inside this tick (or at its start when the delay ran out earlier, e.g. after a chase ended).
            double u = (rideAt - t0) / dt;
            if (u < 0.0) u = 0.0;
            if (u > 1.0) u = 1.0;
            Vec2d mid = u > 0.0 ? arena.Step(a, d * u, hold) : a;
            int sign = SlideSign(arena, mid, p);
            Vec2d target = arena.FollowBorder(mid, rideStep * (1.0 - u), sign, out Vec2d rideDir);
            p.BorderRiding = true;
            p.BorderRideSign = sign;
            p.BorderRideInput = p.DesiredHeading;
            p.BorderRideStart = rideAt < t0 ? t0 : rideAt;
            if (rideDir.LengthSq > 0.0) p.Heading = rideDir.Angle();
            return target;
        }

        /// <summary>Step 3: a ride never survives an elimination or a spark (the spark ends it at the cut, so from that tick on).</summary>
        internal static void EndOfTick(PlayerState p)
        {
            if (!p.BorderRiding) return;
            if (!p.Alive || p.Spark != null)
            {
                End(p);
                p.BorderContactStart = double.NaN;
            }
        }

        private static void End(PlayerState p)
        {
            p.BorderRiding = false;
            p.BorderRideSign = 0;
        }

        /// <summary>True when the step a -> end touched the boundary: constrained by R4, or ending within ContactTolerance of the line.</summary>
        private static bool InContact(Arena arena, Vec2d a, Vec2d d, Vec2d end)
        {
            if (end != a + d) return true;
            return arena.SignedDistance(end) + arena.Margin >= -ContactTolerance;
        }

        /// <summary>
        /// Tick fraction at which the straight path a + u d first reaches the contact tolerance (bisection, 60 halvings):
        /// 0 when already there at the tick start. It depends on the straight path only, so a head approaching the border
        /// at a constant heading gets the same contact instant at every tick rate.
        /// </summary>
        private static double ContactFraction(Arena arena, Vec2d a, Vec2d d)
        {
            double limit = -arena.Margin - ContactTolerance;
            if (arena.SignedDistance(a) >= limit) return 0.0;
            if (arena.SignedDistance(a + d) < limit) return 1.0;
            double lo = 0.0, hi = 1.0;
            for (int k = 0; k < 60; k++)
            {
                double mid = 0.5 * (lo + hi);
                if (!(mid > lo && mid < hi)) break;
                if (arena.SignedDistance(a + d * mid) >= limit) hi = mid;
                else lo = mid;
            }
            return hi;
        }

        /// <summary>Riding direction at the start: the side the desired heading leans to along the boundary (+1 when straight in).</summary>
        private static int SlideSign(Arena arena, Vec2d at, PlayerState p)
        {
            Vec2d tangent = arena.OutwardNormal(at).Perp();
            // |along| below 1e-9 counts as straight in (FromAngle(pi / 2) has an x of 6e-17, which must not pick a side).
            double along = Vec2d.Dot(Vec2d.FromAngle(p.DesiredHeading), tangent);
            if (Math.Abs(along) < 1e-9) along = Vec2d.Dot(Vec2d.FromAngle(p.Heading), tangent);
            return along < -1e-9 ? -1 : 1;
        }

        /// <summary>
        /// Rule v1.9 end on steering: a desired heading within InputTolerance of the accepted one is no new input (keep
        /// riding). A new one that points into the interior by more than the hold angle from the tangent ends the ride;
        /// otherwise it is accepted (and a push along the boundary the other way reverses the ride).
        /// </summary>
        private static bool KeepsRiding(Arena arena, PlayerState p, Vec2d a, double hold)
        {
            if (Math.Abs(Geo.WrapAngle(p.DesiredHeading - p.BorderRideInput)) <= InputTolerance) return true;
            Vec2d n = arena.OutwardNormal(a);
            Vec2d want = Vec2d.FromAngle(p.DesiredHeading);
            if (-Vec2d.Dot(want, n) > Math.Sin(hold)) return false;
            double along = Vec2d.Dot(want, n.Perp());
            if (along > 1e-9) p.BorderRideSign = 1;
            else if (along < -1e-9) p.BorderRideSign = -1;
            p.BorderRideInput = p.DesiredHeading;
            return true;
        }
    }
}
