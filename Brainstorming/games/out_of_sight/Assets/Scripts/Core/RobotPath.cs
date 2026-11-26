using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5.md 4 and 16.8, PRD 4.8): the robot vacuum's timeline, pure and deterministic. The robot follows
    /// the closed loop of its waypoints (the last one leads back to the first; two waypoints are a there-and-back) along
    /// straight segments at <see cref="Speed"/> (<see cref="RobotDef.Speed"/>, or <see cref="Tuning.RobotSpeed"/> when 0). At
    /// time 0 it is on waypoint <see cref="StartIndex"/>, heading for the next one.
    ///
    /// <see cref="Reverse"/> makes it travel the loop backwards from where it is at that time (after a contact with the
    /// player furniture): the timeline is a list of legs, each starting at a time and a position on the loop with a
    /// direction, so <see cref="PositionAt"/> and <see cref="HeadingAt"/> answer for any time, before or after a reversal.
    /// Without a reversal (the audit) the timeline is fixed: <see cref="PositionAt"/>(t + <see cref="Period"/>) equals
    /// <see cref="PositionAt"/>(t).
    ///
    /// Positions are planar (y 0): the robot runs on the floor level only (the validator). Headings use the YawMath
    /// convention (0 faces +z, 90 faces +x).
    /// </summary>
    public sealed class RobotPath
    {
        private struct Leg
        {
            public double T0;  // the time the leg starts
            public double S0;  // the arc position at T0, in [0, Length)
            public int Dir;    // +1 along the loop, -1 backwards
        }

        private readonly Vector3[] points;
        // cumulative[i]: the arc length from waypoint 0 to waypoint i along the loop; cumulative[n] is the Length.
        private readonly double[] cumulative;
        private readonly List<Leg> legs = new List<Leg>();

        /// <summary>The path of <paramref name="def"/>; a null def or loop is a robot standing at the origin.</summary>
        public RobotPath(RobotDef def)
        {
            var list = new List<Vector3>();
            if (def != null && def.Loop != null)
            {
                foreach (PointDef p in def.Loop)
                {
                    if (p != null)
                    {
                        list.Add(new Vector3(p.X, 0f, p.Z));
                    }
                }
            }
            points = list.ToArray();
            int n = points.Length;
            cumulative = new double[n + 1];
            for (int i = 0; i < n; i++)
            {
                Vector3 a = points[i];
                Vector3 b = points[(i + 1) % n];
                cumulative[i + 1] = cumulative[i] + (b - a).magnitude;
            }
            Speed = def != null && def.Speed > 0f ? def.Speed : Tuning.RobotSpeed;
            StartIndex = n == 0 ? 0 : Mathf.Clamp(def.Start, 0, n - 1);
            legs.Add(new Leg { T0 = 0d, S0 = n == 0 ? 0d : Wrap(cumulative[StartIndex]), Dir = 1 });
        }

        /// <summary>The waypoints of the loop, planar.</summary>
        public IReadOnlyList<Vector3> Points => points;

        /// <summary>The travel speed, m/s.</summary>
        public float Speed { get; }

        /// <summary>The waypoint the robot is on at time 0.</summary>
        public int StartIndex { get; }

        /// <summary>The length of the closed loop, metres.</summary>
        public float Length => (float)cumulative[cumulative.Length - 1];

        /// <summary>The time of one full loop, seconds (0 for a loop of no length).</summary>
        public float Period => Length > 0f ? Length / Speed : 0f;

        /// <summary>The number of reversals so far.</summary>
        public int ReverseCount => legs.Count - 1;

        /// <summary>The time of the last reversal, or 0 when there is none.</summary>
        public float LastReverseTime => (float)legs[legs.Count - 1].T0;

        /// <summary>
        /// Makes the robot travel the loop in the other direction from its position at <paramref name="t"/>. A later
        /// reversal already recorded (after <paramref name="t"/>) is dropped first, so the timeline stays one ordered list.
        /// </summary>
        public void Reverse(float t)
        {
            double at = t;
            while (legs.Count > 1 && legs[legs.Count - 1].T0 > at)
            {
                legs.RemoveAt(legs.Count - 1);
            }
            Leg leg = LegAt(at);
            legs.Add(new Leg { T0 = at, S0 = ArcOn(leg, at), Dir = -leg.Dir }); // MUTATION:ROBOT_REVERSE
        }

        /// <summary>+1 when the robot travels the loop forward at <paramref name="t"/>, -1 when it travels it backwards.</summary>
        public int DirectionAt(float t) => LegAt(t).Dir;

        /// <summary>The robot's position at <paramref name="t"/> (planar).</summary>
        public Vector3 PositionAt(float t)
        {
            int n = points.Length;
            if (n == 0)
            {
                return Vector3.zero;
            }
            if (Length <= 1e-6f)
            {
                return points[0];
            }
            double s = ArcOn(LegAt(t), t);
            int i = SegmentForward(s);
            double length = cumulative[i + 1] - cumulative[i];
            float f = length > 0d ? (float)((s - cumulative[i]) / length) : 0f;
            return Vector3.Lerp(points[i], points[(i + 1) % n], Mathf.Clamp01(f));
        }

        /// <summary>
        /// The unit planar direction the robot travels at <paramref name="t"/>: along its segment, reversed when it runs
        /// backwards. On a waypoint it is the direction of the segment it leaves by. Zero for a loop of no length.
        /// </summary>
        public Vector3 ForwardAt(float t)
        {
            int n = points.Length;
            if (n == 0 || Length <= 1e-6f)
            {
                return Vector3.zero;
            }
            Leg leg = LegAt(t);
            double s = ArcOn(leg, t);
            if (leg.Dir > 0)
            {
                int i = SegmentForward(s);
                return (points[(i + 1) % n] - points[i]).normalized;
            }
            int j = SegmentBackward(s);
            return (points[j] - points[(j + 1) % n]).normalized;
        }

        /// <summary>The robot's heading at <paramref name="t"/>, degrees (YawMath), the yaw of <see cref="ForwardAt"/>; 0 when it has none.</summary>
        public float HeadingAt(float t)
        {
            Vector3 f = ForwardAt(t);
            return f.sqrMagnitude > 0f ? YawMath.YawOf(f) : 0f;
        }

        /// <summary>
        /// True when the robot's disc (<paramref name="robotRadius"/>, <see cref="Tuning.RobotRadius"/> by default) at
        /// <paramref name="robot"/> overlaps the footprint of a furniture at <paramref name="pose"/>: the rectangle of
        /// <paramref name="size"/>.x by <paramref name="size"/>.z centred on the pose and turned by its yaw (planar; the
        /// heights are ignored). Touching exactly is not an overlap.
        /// </summary>
        public static bool Overlaps(Vector3 robot, FurniturePose pose, Vector3 size, float robotRadius = Tuning.RobotRadius)
        {
            Vector3 local = YawMath.Rotate(YawMath.Planar(robot - pose.Position), -pose.Yaw);
            float hx = Mathf.Abs(size.x) * 0.5f;
            float hz = Mathf.Abs(size.z) * 0.5f;
            float dx = local.x - Mathf.Clamp(local.x, -hx, hx);
            float dz = local.z - Mathf.Clamp(local.z, -hz, hz);
            return dx * dx + dz * dz < robotRadius * robotRadius;
        }

        // ----- The timeline -----

        /// <summary>The leg in force at <paramref name="t"/>: the last one starting at or before it (the first one before time 0).</summary>
        private Leg LegAt(double t)
        {
            for (int i = legs.Count - 1; i > 0; i--)
            {
                if (legs[i].T0 <= t)
                {
                    return legs[i];
                }
            }
            return legs[0];
        }

        private double ArcOn(Leg leg, double t)
        {
            return Wrap(leg.S0 + leg.Dir * Speed * (t - leg.T0));
        }

        /// <summary>An arc position into [0, Length).</summary>
        private double Wrap(double s)
        {
            double length = cumulative[cumulative.Length - 1];
            if (length <= 1e-9d)
            {
                return 0d;
            }
            double r = s % length;
            if (r < 0d)
            {
                r += length;
            }
            return r >= length ? 0d : r;
        }

        /// <summary>The segment i with cumulative[i] &lt;= s &lt; cumulative[i + 1] (a segment of no length is never chosen).</summary>
        private int SegmentForward(double s)
        {
            int n = points.Length;
            for (int i = 0; i < n; i++)
            {
                if (s < cumulative[i + 1] && cumulative[i + 1] > cumulative[i])
                {
                    return i;
                }
            }
            return LastSegment();
        }

        /// <summary>
        /// The segment j with cumulative[j] &lt; s &lt;= cumulative[j + 1], the one a robot running backwards is on (at
        /// arc 0 it is the last segment, which ends on waypoint 0).
        /// </summary>
        private int SegmentBackward(double s)
        {
            if (s <= 0d)
            {
                return LastSegment();
            }
            int n = points.Length;
            for (int j = 0; j < n; j++)
            {
                if (s <= cumulative[j + 1] && cumulative[j + 1] > cumulative[j])
                {
                    return j;
                }
            }
            return LastSegment();
        }

        /// <summary>The last segment of some length.</summary>
        private int LastSegment()
        {
            for (int j = points.Length - 1; j >= 0; j--)
            {
                if (cumulative[j + 1] > cumulative[j])
                {
                    return j;
                }
            }
            return 0;
        }
    }
}
