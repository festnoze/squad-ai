using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// One fixed step of input for <see cref="MotionProfile"/>: a planar world direction (x, z; zero is no input, as the
    /// controller's ScriptedDirection) and the careful flag (Left Shift held).
    /// </summary>
    public struct MotionWish
    {
        /// <summary>The planar world direction, (x, z). Shorter than 0.01 is no input; longer than 1 is clamped to 1.</summary>
        public Vector2 Direction;
        public bool Careful;

        public MotionWish(Vector2 direction, bool careful = false)
        {
            Direction = direction;
            Careful = careful;
        }

        /// <summary>True when the direction is an input (the controller's dead zone: a squared length of 1e-4).</summary>
        public bool Active => Direction.sqrMagnitude >= MotionProfile.WishDeadZone;

        /// <summary>No input.</summary>
        public static MotionWish None(bool careful = false) => new MotionWish(Vector2.zero, careful);

        /// <summary>Toward a planar direction (x, z).</summary>
        public static MotionWish Toward(Vector2 direction, bool careful = false) => new MotionWish(direction, careful);

        /// <summary>Toward a yaw (YawMath convention: 0 faces +z, 90 faces +x), at full stick.</summary>
        public static MotionWish TowardYaw(float yaw, bool careful = false)
        {
            Vector3 f = YawMath.Forward(yaw);
            return new MotionWish(new Vector2(f.x, f.z), careful);
        }
    }

    /// <summary>A sequence of <see cref="MotionWish"/> built in seconds of fixed steps, for <see cref="MotionProfile.Synthesize(BodyDef, IList{MotionWish}, float, bool)"/>.</summary>
    public sealed class MotionScript : List<MotionWish>
    {
        public readonly float Dt;

        public MotionScript(float dt = Tuning.FixedStep)
        {
            Dt = dt > 0f ? dt : Tuning.FixedStep;
        }

        /// <summary>round(seconds / dt) steps, at least one for a positive duration.</summary>
        public int StepsOf(float seconds) => seconds > 0f ? Mathf.Max(1, Mathf.RoundToInt(seconds / Dt)) : 0;

        /// <summary>Appends <paramref name="steps"/> steps of <paramref name="wish"/>.</summary>
        public MotionScript Repeat(MotionWish wish, int steps)
        {
            for (int i = 0; i < steps; i++)
            {
                Add(wish);
            }
            return this;
        }

        /// <summary>Holds a planar direction (x, z) for <paramref name="seconds"/>.</summary>
        public MotionScript Hold(Vector2 direction, float seconds, bool careful = false) => Repeat(MotionWish.Toward(direction, careful), StepsOf(seconds));

        /// <summary>Holds a yaw at full stick for <paramref name="seconds"/>.</summary>
        public MotionScript HoldYaw(float yaw, float seconds, bool careful = false) => Repeat(MotionWish.TowardYaw(yaw, careful), StepsOf(seconds));

        /// <summary>No input for <paramref name="seconds"/> (careful still held when <paramref name="careful"/>).</summary>
        public MotionScript Release(float seconds, bool careful = false) => Repeat(MotionWish.None(careful), StepsOf(seconds));
    }

    /// <summary>
    /// M5 (docs/CONTRACT_M5.md 16.5): a pure synthesis of the driving rules of FurnitureController, step for step: the
    /// planar velocity of every fixed step for a sequence of wishes. It feeds the load targets (<see cref="LoadBalance"/>),
    /// the samples per cell, the slide samples and the audit's <c>load</c> lesson; probe step 44 compares it with the
    /// real controller (within 0.05 m/s).
    ///
    /// The rules, as FurnitureController.Step and Drive apply them (walls, pins, carries, presses and the
    /// neutral-input wait aside):
    /// - careful mode (under GameRules.Bodies only) caps the speed at the body's max speed times
    ///   <see cref="Tuning.CarefulFactor"/>;
    /// - with input: the velocity moves toward wish times max speed by Accel * dt (the wish clamped to length 1), capped
    ///   at max(speed + AccelHigh * dt, StageSpeed) (the stool's two stages; +inf stage for the other bodies); the yaw
    ///   turns toward the wish at TurnRate;
    /// - without input: the M1 instant stop (velocity zero on the release step);
    /// - the office chair (Glides, under GameRules.Bodies): released, or with input against its motion, faster than
    ///   <see cref="Tuning.MovingSpeedThreshold"/>, it glides to rest in <see cref="Tuning.OfficeChairStopTime"/> at a
    ///   constant deceleration, turning with its velocity;
    /// - the stool (Tips, under GameRules.Bodies): released faster than <see cref="Tuning.StoolTipSpeed"/> it falls (an
    ///   action of <see cref="Tuning.StoolFallTime"/>), lies still until the next input edge, then rights itself (an
    ///   action of <see cref="Tuning.StoolRightTime"/>) and drives again on the step the righting ends;
    /// - an action (the fall, the righting, <see cref="BeginAction"/>, <see cref="BeginPush"/>) covers round(duration / dt)
    ///   steps, ignores the input and counts as moving.
    /// The rock of the rocking chair is not synthesized: in play it is GameState.StepRock's rule (CONTRACT_M5 18: one still
    /// rest step, then FurnitureController.BeginExternalAction of RockTime, or RockCarefulTime when careful), and a replay
    /// models it with <see cref="BeginAction"/> and <see cref="RockSteps"/>.
    /// </summary>
    public sealed class MotionProfile
    {
        /// <summary>The controller's input dead zone: a wish of a squared length below this is no input.</summary>
        public const float WishDeadZone = 1e-4f;

        // A guard for the loops of the static helpers (steps), far above any body's time to top speed or to rest.
        private const int StepGuard = 100000;

        private enum ActionKind
        {
            None,
            Fall,
            Right,
            Other,
            Push,
        }

        private Vector3 velocity;
        private bool previousWishActive;
        private float glideSpeed0;
        private float glideRemaining;
        private Vector3 glideDirection;
        private ActionKind action;
        private int actionStepsLeft;
        private Vector3 pushVelocity;

        /// <param name="body">The body; null is the chair.</param>
        /// <param name="dt">The fixed step; 0 or below is <see cref="Tuning.FixedStep"/>.</param>
        /// <param name="bodies">GameRules.Bodies: careful mode, the glide and the tip (on in every level from 4).</param>
        /// <param name="yaw">The starting yaw (degrees, YawMath convention).</param>
        public MotionProfile(BodyDef body, float dt = Tuning.FixedStep, bool bodies = true, float yaw = 0f)
        {
            Body = body ?? BodyDef.For(null);
            Dt = dt > 0f ? dt : Tuning.FixedStep;
            Bodies = bodies;
            Yaw = yaw;
        }

        public BodyDef Body { get; }
        public float Dt { get; }
        public bool Bodies { get; }

        /// <summary>The planar velocity of the last step, (x, z) in m/s: what the controller travels on that step.</summary>
        public Vector2 Velocity => new Vector2(velocity.x, velocity.z);

        /// <summary>The planar speed of the last step (m/s).</summary>
        public float Speed => velocity.magnitude;

        /// <summary>The yaw after the last step (degrees, as Mathf.MoveTowardsAngle leaves it, like the controller's Yaw).</summary>
        public float Yaw { get; private set; }

        /// <summary>The yaw change of the last step, in degrees per second.</summary>
        public float YawRate { get; private set; }

        /// <summary>Careful mode on the last step (the wish's flag, under GameRules.Bodies only).</summary>
        public bool Careful { get; private set; }

        /// <summary>The max speed of the last step: the body's, times CarefulFactor in careful mode.</summary>
        public float MaxSpeed => MaxSpeedOf(Body, Careful, true);

        /// <summary>The office chair glides (released, or braked against its motion, and still rolling).</summary>
        public bool Gliding { get; private set; }

        /// <summary>The stool is not upright: from the start of its fall to the end of its righting.</summary>
        public bool Tipped { get; private set; }

        /// <summary>An action covers the last step (a fall, a righting, an external action or a push).</summary>
        public bool ActionActive => action != ActionKind.None;

        /// <summary>The last step was a step of a push (<see cref="BeginPush"/>).</summary>
        public bool Pushing => action == ActionKind.Push;

        /// <summary>The moving predicate of the last step (MotionRule.IsMoving with the action).</summary>
        public bool IsMoving { get; private set; }

        /// <summary>The number of steps taken.</summary>
        public int StepCount { get; private set; }

        /// <summary>Stool falls so far.</summary>
        public int FallCount { get; private set; }

        /// <summary>The max speed of a body (careful mode only under GameRules.Bodies).</summary>
        public static float MaxSpeedOf(BodyDef body, bool careful, bool bodies = true)
        {
            BodyDef b = body ?? BodyDef.For(null);
            return b.MaxSpeed * (careful && bodies ? Tuning.CarefulFactor : 1f); // MUTATION:MOTION_CAREFUL
        }

        /// <summary>
        /// Starts an action with no input and no travel, for the next round(<paramref name="duration"/> / dt) steps (at
        /// least one): a rock, a door opening, a lamp switch. As FurnitureController.BeginExternalAction, it is refused
        /// (false, nothing changes) unless the furniture is still (not moving on its last step, not gliding), upright and
        /// in no other action, or when the duration is not positive.
        /// </summary>
        public bool BeginAction(float duration)
        {
            if (!(duration > 0f) || IsMoving || Gliding || Tipped || ActionActive)
            {
                return false;
            }
            velocity = Vector3.zero;
            StartAction(ActionKind.Other, duration);
            return true;
        }

        /// <summary>
        /// M5 (CONTRACT_M5 4, 16.8): the robot's shove: a constant velocity of <paramref name="distance"/> /
        /// <paramref name="time"/> along the planar <paramref name="direction"/> (x, z) for the next round(time / dt) steps,
        /// input ignored, moving. Any glide ends. Refused (false) during another action, while tipped, or for a zero
        /// direction, distance or time. When it ends the furniture is still.
        /// </summary>
        public bool BeginPush(Vector2 direction, float distance, float time)
        {
            if (ActionActive || Tipped || !(time > 0f) || !(distance > 0f) || direction.sqrMagnitude < 1e-8f)
            {
                return false;
            }
            Vector2 d = direction.normalized;
            pushVelocity = new Vector3(d.x, 0f, d.y) * (distance / time);
            Gliding = false;
            StartAction(ActionKind.Push, time);
            return true;
        }

        /// <summary>One fixed step with <paramref name="wish"/>. Returns the planar velocity of the step, (x, z).</summary>
        public Vector2 Step(MotionWish wish)
        {
            float dt = Dt;
            // An action that has run all its steps ends at the start of the next step.
            if (ActionActive && actionStepsLeft <= 0)
            {
                CompleteAction();
            }
            float startYaw = Yaw;
            var w = new Vector3(wish.Direction.x, 0f, wish.Direction.y);
            bool wishActive = w.sqrMagnitude >= WishDeadZone;
            bool wishEdge = wishActive && !previousWishActive;
            previousWishActive = wishActive;
            Careful = Bodies && wish.Careful;

            if (ActionActive)
            {
                // Input is ignored; the body does not travel, except along a push.
                velocity = action == ActionKind.Push ? pushVelocity : Vector3.zero;
            }
            else if (Tipped)
            {
                // Lying on its side until an input edge, then it rights itself.
                velocity = Vector3.zero;
                if (wishEdge)
                {
                    StartAction(ActionKind.Right, Tuning.StoolRightTime);
                }
            }
            else
            {
                Drive(w, wishActive, dt);
            }

            YawRate = Mathf.DeltaAngle(startYaw, Yaw) / dt;
            IsMoving = MotionRule.IsMoving(velocity.magnitude, YawRate, ActionActive);
            if (ActionActive)
            {
                actionStepsLeft--;
            }
            StepCount++;
            return Velocity;
        }

        /// <summary>FurnitureController.Drive without walls: the stool tip, the office chair glide, or plain driving.</summary>
        private void Drive(Vector3 wish, bool wishActive, float dt)
        {
            float speed = velocity.magnitude;
            bool tips = Bodies && Body.Tips;
            bool glides = Bodies && Body.Glides; // MUTATION:MOTION_GLIDE
            if (tips && !wishActive && speed > Tuning.StoolTipSpeed)
            {
                // Released too fast: the stool tips over.
                velocity = Vector3.zero;
                Gliding = false;
                Tipped = true;
                FallCount++;
                StartAction(ActionKind.Fall, Tuning.StoolFallTime);
                return;
            }
            if (glides && speed > Tuning.MovingSpeedThreshold && (!wishActive || Vector3.Dot(wish, velocity) < 0f))
            {
                // The glide: to rest in exactly OfficeChairStopTime at a constant deceleration.
                if (!Gliding)
                {
                    Gliding = true;
                    glideSpeed0 = speed;
                    glideRemaining = Tuning.OfficeChairStopTime;
                    glideDirection = velocity / speed;
                }
                glideRemaining -= dt;
                if (glideRemaining <= Tuning.GlideEpsilon)
                {
                    velocity = Vector3.zero;
                    Gliding = false;
                }
                else
                {
                    velocity = glideDirection * (glideSpeed0 * glideRemaining / Tuning.OfficeChairStopTime);
                    Yaw = Mathf.MoveTowardsAngle(Yaw, YawMath.YawOf(glideDirection), Body.TurnRate * dt);
                }
                return;
            }
            Gliding = false;
            if (!wishActive)
            {
                // PRD 3.2: no inertia, the furniture stops on the step where the input is released.
                velocity = Vector3.zero;
                return;
            }
            wish = Vector3.ClampMagnitude(wish, 1f);
            Vector3 next = Vector3.MoveTowards(velocity, wish * MaxSpeedOf(Body, Careful, Bodies), Body.Accel * dt);
            // The stool's two stages: fast up to StageSpeed, then AccelHigh (+inf stage for every other body).
            float cap = Mathf.Max(speed + Body.AccelHigh * dt, Body.StageSpeed);
            if (next.magnitude > cap)
            {
                next = next.normalized * cap;
            }
            velocity = next;
            Yaw = Mathf.MoveTowardsAngle(Yaw, YawMath.YawOf(wish), Body.TurnRate * dt);
        }

        private void StartAction(ActionKind kind, float duration)
        {
            action = kind;
            actionStepsLeft = Mathf.Max(1, Mathf.RoundToInt(duration / Mathf.Max(Dt, 1e-4f)));
        }

        private void CompleteAction()
        {
            if (action == ActionKind.Right)
            {
                Tipped = false;
            }
            if (action == ActionKind.Push)
            {
                velocity = Vector3.zero;
            }
            action = ActionKind.None;
            actionStepsLeft = 0;
        }

        // ----- Static helpers -----

        /// <summary>
        /// The planar velocity (x, z) of every step for <paramref name="wishes"/> (planar directions; zero is no input), all
        /// with the same careful flag, from rest, under GameRules.Bodies.
        /// </summary>
        public static Vector2[] Synthesize(BodyDef body, bool careful, IList<Vector2> wishes, float dt = Tuning.FixedStep)
        {
            var profile = new MotionProfile(body, dt);
            int n = wishes != null ? wishes.Count : 0;
            var result = new Vector2[n];
            for (int i = 0; i < n; i++)
            {
                result[i] = profile.Step(new MotionWish(wishes[i], careful));
            }
            return result;
        }

        /// <summary>The planar velocity (x, z) of every step for <paramref name="wishes"/>, each with its own careful flag, from rest.</summary>
        public static Vector2[] Synthesize(BodyDef body, IList<MotionWish> wishes, float dt = Tuning.FixedStep, bool bodies = true)
        {
            var profile = new MotionProfile(body, dt, bodies);
            int n = wishes != null ? wishes.Count : 0;
            var result = new Vector2[n];
            for (int i = 0; i < n; i++)
            {
                result[i] = profile.Step(wishes[i]);
            }
            return result;
        }

        /// <summary>
        /// The distance the body still travels after a release at the max speed of its mode (straight, after reaching that
        /// speed): 0 for the M1 instant stop, the glide's distance for the office chair (0.532 m at full speed, 0.266 m
        /// careful), 0 for a stool released above its tip speed (it falls where it is).
        /// </summary>
        public static float StopDistance(BodyDef body, bool careful, float dt = Tuning.FixedStep, bool bodies = true)
        {
            MotionProfile p = AtTopSpeed(body, careful, dt, bodies);
            float distance = 0f;
            var none = MotionWish.None(careful);
            for (int guard = 0; guard < StepGuard; guard++)
            {
                p.Step(none);
                if (p.Speed <= 0f)
                {
                    break;
                }
                distance += p.Speed * p.Dt;
            }
            return distance;
        }

        /// <summary>
        /// The steps after a release at the max speed of the body's mode on which it still travels or turns (the moving
        /// predicate without actions): 0 for the instant stop, 19 for the office chair's 0.4 s glide, 0 for a stool that
        /// tips (its fall is an action, not a slide).
        /// </summary>
        public static int SlideSteps(BodyDef body, bool careful, float dt = Tuning.FixedStep, bool bodies = true)
        {
            MotionProfile p = AtTopSpeed(body, careful, dt, bodies);
            var none = MotionWish.None(careful);
            int steps = 0;
            for (int guard = 0; guard < StepGuard; guard++)
            {
                p.Step(none);
                if (!MotionRule.IsMoving(p.Speed, p.YawRate))
                {
                    break;
                }
                steps++;
            }
            return steps;
        }

        /// <summary>
        /// <see cref="SlideSteps"/> in audit samples of <see cref="Tuning.MotionSampleSteps"/> fixed steps, rounded up:
        /// 4 for the office chair (Tuning.AuditStopSamples), 0 for every other body.
        /// </summary>
        public static int SlideSamples(BodyDef body, bool careful, float dt = Tuning.FixedStep, bool bodies = true)
        {
            int steps = SlideSteps(body, careful, dt, bodies);
            return (steps + Tuning.MotionSampleSteps - 1) / Tuning.MotionSampleSteps;
        }

        /// <summary>
        /// M5 (CONTRACT_M5 5, 16.9): the steps of the rock after the body comes to rest: round(RockTime / dt), or
        /// round(RockCarefulTime / dt) after a careful stop; 0 for a body that does not rock.
        /// </summary>
        public static int RockSteps(BodyDef body, bool careful, float dt = Tuning.FixedStep)
        {
            if (body == null || !body.Rocks)
            {
                return 0;
            }
            float step = dt > 0f ? dt : Tuning.FixedStep;
            return Mathf.RoundToInt((careful ? Tuning.RockCarefulTime : Tuning.RockTime) / step);
        }

        /// <summary>A profile driven straight (+z) from rest until it reaches the max speed of its mode.</summary>
        private static MotionProfile AtTopSpeed(BodyDef body, bool careful, float dt, bool bodies)
        {
            var p = new MotionProfile(body, dt, bodies);
            var go = MotionWish.Toward(Vector2.up, careful);
            float top = MaxSpeedOf(p.Body, careful, bodies);
            for (int guard = 0; guard < StepGuard; guard++)
            {
                p.Step(go);
                if (p.Speed >= top - 1e-4f)
                {
                    break;
                }
            }
            return p;
        }
    }
}
