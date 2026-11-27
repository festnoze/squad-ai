// Owned by A4 (sim). Scripted controllers of contract 5.6 (tests, probe, attract fallbacks).
// The stateful ones (WaypointController, HomeCirclerController) keep per-player state, so one instance can serve several
// players, but each player then follows its own progress.
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>Always asks for the same heading (radians).</summary>
    public sealed class ConstantHeadingController : IController
    {
        private readonly double heading;

        public ConstantHeadingController(double heading)
        {
            this.heading = heading;
        }

        public double? DesiredHeading(SimView view, int playerIndex) => heading;
    }

    /// <summary>
    /// (time, heading) pairs, step function; an entry applies on the first tick with Time &gt;= time - 1e-9. Entries are
    /// sorted by time (stable). Before the first entry applies the controller returns null (keeps the current heading).
    /// Cross-rate tests (contract 10.0) use switch times that are multiples of 1/6 s with TurnRateDeg = 0.
    /// </summary>
    public sealed class HeadingScheduleController : IController
    {
        private readonly double[] times;
        private readonly double[] headings;

        public HeadingScheduleController(params (double time, double heading)[] schedule)
        {
            if (schedule == null) throw new ArgumentNullException(nameof(schedule));
            var order = new List<int>(schedule.Length);
            for (int k = 0; k < schedule.Length; k++) order.Add(k);
            // Stable sort by time (List.Sort is not stable: compare the original index on ties).
            order.Sort((a, b) =>
            {
                int c = schedule[a].time.CompareTo(schedule[b].time);
                return c != 0 ? c : a.CompareTo(b);
            });
            times = new double[schedule.Length];
            headings = new double[schedule.Length];
            for (int k = 0; k < order.Count; k++)
            {
                times[k] = schedule[order[k]].time;
                headings[k] = schedule[order[k]].heading;
            }
        }

        public double? DesiredHeading(SimView view, int playerIndex)
        {
            double now = view.Time;
            double? result = null;
            for (int k = 0; k < times.Length; k++)
            {
                if (now >= times[k] - 1e-9) result = headings[k];
                else break;
            }
            return result;
        }
    }

    /// <summary>
    /// Steers straight at each waypoint in turn; a waypoint is reached when the head is within 0.3 u of it. With a
    /// finite turn rate the head cannot turn tighter than r = PawnSpeed / TurnRate (0.64 u at 540 deg/s), so a waypoint
    /// approached from the side could be orbited forever without ever coming within 0.3 u: a waypoint that is within 2 r
    /// of the head and behind it (already passed) also counts as reached. With TurnRateDeg = 0 (the scripted tests)
    /// only the 0.3 u rule applies. After the last waypoint: with loop, starts over; otherwise returns null (keeps the
    /// last course).
    /// </summary>
    public sealed class WaypointController : IController
    {
        public const double ReachRadius = 0.3;

        private readonly Vec2d[] waypoints;
        private readonly bool loop;
        private readonly Dictionary<int, int> next = new Dictionary<int, int>();

        public WaypointController(IReadOnlyList<Vec2d> waypoints, bool loop = false)
        {
            if (waypoints == null) throw new ArgumentNullException(nameof(waypoints));
            this.waypoints = new Vec2d[waypoints.Count];
            for (int k = 0; k < waypoints.Count; k++) this.waypoints[k] = waypoints[k];
            this.loop = loop;
        }

        /// <summary>Index of the waypoint the player currently steers to (== count when done).</summary>
        public int NextIndex(int playerIndex) => next.TryGetValue(playerIndex, out int k) ? k : 0;

        public double? DesiredHeading(SimView view, int playerIndex)
        {
            if (waypoints.Length == 0) return null;
            PlayerState me = view.Player(playerIndex);
            Vec2d pos = me.Pos;
            double turnRate = view.Config.TurnRateRad;
            double passRadius = turnRate > 0.0 ? 2.0 * view.Config.PawnSpeed / turnRate : 0.0;
            Vec2d forward = Vec2d.FromAngle(me.Heading);
            int k = NextIndex(playerIndex);
            // Skip every waypoint already reached (bounded so a looping list of coincident points cannot spin).
            for (int guard = 0; guard <= waypoints.Length && k < waypoints.Length; guard++)
            {
                Vec2d rel = waypoints[k] - pos;
                double dist = rel.Length;
                bool reached = dist <= ReachRadius || (dist < passRadius && Vec2d.Dot(forward, rel) < 0.0);
                if (!reached) break;
                k++;
                if (k >= waypoints.Length && loop) k = 0;
            }
            next[playerIndex] = k;
            if (k >= waypoints.Length) return null;
            Vec2d to = waypoints[k] - pos;
            return to.LengthSq > 0.0 ? to.Angle() : (double?)null;
        }
    }

    /// <summary>
    /// Orbits counter-clockwise at 1.5 u around a center (normally its own start disc center), so it stays home forever
    /// with the default disc radius 3.5. The heading is the orbit tangent bent toward the orbit radius (proportional
    /// correction, capped at 90 degrees).
    /// </summary>
    public sealed class HomeCirclerController : IController
    {
        public const double OrbitRadius = 1.5;
        private const double Gain = 2.0;   // radians of correction per unit of radial error

        private readonly Vec2d center;

        public HomeCirclerController(Vec2d center)
        {
            this.center = center;
        }

        public double? DesiredHeading(SimView view, int playerIndex)
        {
            Vec2d rel = view.Player(playerIndex).Pos - center;
            double r = rel.Length;
            if (r < 1e-9) return view.Player(playerIndex).Heading;   // at the center: keep going, the orbit forms
            double tangent = rel.Angle() + 0.5 * Math.PI;
            double correction = Gain * (r - OrbitRadius);
            if (correction > 0.5 * Math.PI) correction = 0.5 * Math.PI;
            if (correction < -0.5 * Math.PI) correction = -0.5 * Math.PI;
            return Geo.WrapAngle(tangent + correction);
        }
    }

    /// <summary>Runtime human input: Desired is set from outside; returns Desired then leaves it as is.</summary>
    public sealed class ExternalController : IController
    {
        public double? Desired;

        public double? DesiredHeading(SimView view, int playerIndex) => Desired;
    }
}
