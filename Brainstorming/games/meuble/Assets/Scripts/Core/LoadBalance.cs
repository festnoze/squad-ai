using System.Collections.Generic;
using UnityEngine;

namespace Meuble.Core
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5.md 16.5, option A; PRD 3.4): the load on the player furniture, a KINEMATIC rule. Fed once per
    /// fixed step with the furniture's planar velocity v, it keeps the last <see cref="Tuning.LoadWindow"/> (0.5 s) and
    /// measures <see cref="DeltaV"/> = |v(t) - v(t - window)|; the load falls (<see cref="Fallen"/>, latched until
    /// <see cref="Reset"/>) on the first step where DeltaV reaches <see cref="Tuning.LoadFallDeltaV"/> (1.8 m/s). Before
    /// the first step the furniture is at rest, so v(t - window) is zero for the first 0.5 s. With fixed steps of dt,
    /// v(t - window) is the velocity of round(window / dt) steps before (25).
    ///
    /// What falls and what holds (CONTRACT_M5 16.5, checked in CoreM5BLoadTests through <see cref="MotionProfile"/>): a
    /// 90 deg turn at full chair speed (2.12), any full-speed reversal, the office chair's full start or full glide
    /// (2.8) and the careful U-turns of the stool and the office chair fall; the chair's straight starts and stops (1.5),
    /// every careful straight move, a careful 90 deg chair turn (1.06), a careful chair reversal (1.5) and the robot's
    /// shove (0.5) hold.
    ///
    /// <see cref="SwayTilt"/> is the VISUAL only, and decides nothing: a damped spring (<see cref="Tuning.LoadSwaySpring"/>
    /// K, <see cref="Tuning.LoadSwayDamping"/> C) driven by the velocity change a = dv / dt, with
    /// tiltAcc = -K tilt - C rate - K G a (G = <see cref="Tuning.LoadSwayGain"/>, degrees per m/s2 of the steady lean), so
    /// the load leans against its acceleration: about 18 deg at the peak after the chair's full stop.
    /// </summary>
    public sealed class LoadBalance
    {
        // Rounding margin only: a change of exactly the threshold (the armchair's full reversal, 0.9 to -0.9) falls
        // despite the float error of a diagonal magnitude. Not a tuning value. Public for the level audit (M5 5B.1 m6).
        public const float Epsilon = 1e-4f;

        // The kept samples (time, velocity), oldest first from head; the first is the rest at time 0.
        private readonly List<double> times = new List<double>();
        private readonly List<Vector2> velocities = new List<Vector2>();
        private int head;
        private double time;
        private Vector2 previous;

        public LoadBalance()
        {
            Reset();
        }

        /// <summary>|v(t) - v(t - LoadWindow)| on the last step, m/s.</summary>
        public float DeltaV { get; private set; }

        /// <summary>DeltaV over LoadFallDeltaV: what the balance gauge shows (1 is the fall).</summary>
        public float Ratio => DeltaV / Tuning.LoadFallDeltaV;

        /// <summary>The load fell: latched from the step DeltaV reached the threshold until <see cref="Reset"/>.</summary>
        public bool Fallen { get; private set; }

        /// <summary>True for exactly the step the load fell.</summary>
        public bool JustFell { get; private set; }

        /// <summary>The step (1 for the first) the load fell on; -1 while it holds.</summary>
        public int FallStep { get; private set; } = -1;

        /// <summary>The largest DeltaV since the last <see cref="Reset"/>.</summary>
        public float PeakDeltaV { get; private set; }

        /// <summary>The planar velocity of the last step (x, z).</summary>
        public Vector2 Velocity { get; private set; }

        /// <summary>The steps taken since the last <see cref="Reset"/>.</summary>
        public int StepCount { get; private set; }

        /// <summary>The time since the last <see cref="Reset"/>, seconds.</summary>
        public float Time => (float)time;

        /// <summary>
        /// The visual lean of the load, in degrees, as a planar world vector (x, z): its direction is where the top of the
        /// load leans, its length the angle. Visual only (CONTRACT_M5 16.5). See <see cref="SwayTiltLocal"/>.
        /// </summary>
        public Vector2 SwayTilt { get; private set; }

        /// <summary>The rate of <see cref="SwayTilt"/>, degrees per second.</summary>
        public Vector2 SwayRate { get; private set; }

        /// <summary>
        /// <see cref="SwayTilt"/> in the frame of a furniture of yaw <paramref name="yaw"/>: x to its right, y to its front.
        /// </summary>
        public Vector2 SwayTiltLocal(float yaw)
        {
            Vector3 local = YawMath.Rotate(new Vector3(SwayTilt.x, 0f, SwayTilt.y), -yaw);
            return new Vector2(local.x, local.z);
        }

        /// <summary>Back to a load at rest on a furniture at rest: no history, no sway, not fallen.</summary>
        public void Reset()
        {
            times.Clear();
            velocities.Clear();
            head = 0;
            time = 0d;
            times.Add(0d);
            velocities.Add(Vector2.zero);
            previous = Vector2.zero;
            Velocity = Vector2.zero;
            DeltaV = 0f;
            PeakDeltaV = 0f;
            Fallen = false;
            JustFell = false;
            FallStep = -1;
            StepCount = 0;
            SwayTilt = Vector2.zero;
            SwayRate = Vector2.zero;
        }

        /// <summary>
        /// One fixed step: the furniture's planar velocity <paramref name="planarVelocity"/> (x, z) over the step of
        /// <paramref name="dt"/>. A dt of 0 or below does nothing.
        /// </summary>
        public void Step(float dt, Vector2 planarVelocity)
        {
            JustFell = false;
            if (!(dt > 0f))
            {
                return;
            }
            time += dt;
            StepCount++;
            times.Add(time);
            velocities.Add(planarVelocity);

            // v(t - window): the newest sample at or before t - window, half a step of tolerance for the float step sums.
            double cutoff = time - Tuning.LoadWindow + 0.5 * dt; // MUTATION:LOAD_WINDOW
            while (head + 1 < times.Count && times[head + 1] <= cutoff)
            {
                head++;
            }
            Compact();
            DeltaV = (planarVelocity - velocities[head]).magnitude;
            if (DeltaV > PeakDeltaV)
            {
                PeakDeltaV = DeltaV;
            }
            float threshold = Tuning.LoadFallDeltaV; // MUTATION:LOAD_FALL
            if (!Fallen && DeltaV >= threshold - Epsilon)
            {
                Fallen = true;
                JustFell = true;
                FallStep = StepCount;
            }

            // The visual sway: a damped spring driven by the velocity change (semi-implicit Euler).
            Vector2 accel = (planarVelocity - previous) / dt;
            Vector2 tiltAcc = -Tuning.LoadSwaySpring * SwayTilt - Tuning.LoadSwayDamping * SwayRate
                              - Tuning.LoadSwaySpring * Tuning.LoadSwayGain * accel;
            SwayRate += tiltAcc * dt;
            SwayTilt += SwayRate * dt;
            previous = planarVelocity;
            Velocity = planarVelocity;
        }

        /// <summary>Drops the samples older than the reference, so the history never grows past the window.</summary>
        private void Compact()
        {
            if (head < 64)
            {
                return;
            }
            times.RemoveRange(0, head);
            velocities.RemoveRange(0, head);
            head = 0;
        }

        /// <summary>
        /// Feeds a velocity profile (one planar velocity per step of <paramref name="dt"/>, from rest) to a fresh load and
        /// returns the index of the step it falls on, or -1 when it holds to the end.
        /// </summary>
        public static int FirstFall(IList<Vector2> velocities, float dt = Tuning.FixedStep)
        {
            var load = new LoadBalance();
            int n = velocities != null ? velocities.Count : 0;
            for (int i = 0; i < n; i++)
            {
                load.Step(dt, velocities[i]);
                if (load.JustFell)
                {
                    return i;
                }
            }
            return -1;
        }

        /// <summary>The largest DeltaV of a velocity profile (one planar velocity per step of <paramref name="dt"/>, from rest).</summary>
        public static float PeakOf(IList<Vector2> velocities, float dt = Tuning.FixedStep)
        {
            var load = new LoadBalance();
            int n = velocities != null ? velocities.Count : 0;
            for (int i = 0; i < n; i++)
            {
                load.Step(dt, velocities[i]);
            }
            return load.PeakDeltaV;
        }
    }
}
