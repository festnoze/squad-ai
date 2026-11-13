using UnityEngine;

namespace Meuble.Core
{
    /// <summary>The "moving" predicate of PRD 3.3, the single source of truth for the caught rule.</summary>
    public static class MotionRule
    {
        /// <summary>
        /// M4 (PRD 3.3 amendment, docs/CONTRACT_M4.md section 2): an action in progress (a stool falling or
        /// righting itself, a lamp toggle) counts as moving whatever the speed. Being sat on is not an action: a
        /// pinned furniture passes false and does not move, so it is not moving. With
        /// <paramref name="actionActive"/> false this is <see cref="IsMoving(float, float)"/>.
        /// </summary>
        public static bool IsMoving(float planarSpeed, float yawRateDegPerSecond, bool actionActive)
        {
            return actionActive || IsMoving(planarSpeed, yawRateDegPerSecond);
        }

        /// <summary>Moving when planar speed is above 0.05 m/s or the yaw rate is above 3 deg/s.</summary>
        public static bool IsMoving(float planarSpeed, float yawRateDegPerSecond)
        {
            return planarSpeed > Tuning.MovingSpeedThreshold
                || Mathf.Abs(yawRateDegPerSecond) > Tuning.MovingYawRateThreshold;
        }

        /// <summary>Same predicate measured over one step from two poses. The vertical axis is ignored.</summary>
        public static bool IsMoving(Vector3 previousPosition, float previousYaw, Vector3 position, float yaw, float dt)
        {
            if (dt <= 0f)
            {
                return false;
            }
            float planarSpeed = YawMath.Planar(position - previousPosition).magnitude / dt;
            float yawRate = Mathf.DeltaAngle(previousYaw, yaw) / dt;
            return IsMoving(planarSpeed, yawRate);
        }
    }
}
