using System;
using Meuble.Core;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// The player furniture (PRD 3.2, 3.3). A CharacterController moved only from <see cref="Step"/>, which
    /// GameState calls once per fixed step. Releasing the input zeroes the velocity on that same step.
    /// The visual child interpolates between fixed poses and hops; the collider never hops.
    ///
    /// M4 (docs/CONTRACT_M4.md 2, amendments 9.3, 9.5, 9.7, 9.9): the body comes from a <see cref="BodyDef"/>
    /// (<see cref="SetBody"/>, the single runtime path). Its constants (size, radius, speed, acceleration, turn
    /// rate) always apply; only the special rules are gated: <see cref="GameRules.Bodies"/> gates the stool tip,
    /// the office chair glide and careful mode, <see cref="GameRules.Lamp"/> gates the lamp switch and its dark
    /// range. An action (a stool falling or righting itself, a lamp switch) counts as moving
    /// (<see cref="MotionRule.IsMoving(float, float, bool)"/>), and the body does not travel during it.
    ///
    /// M5 (docs/CONTRACT_M5_v3.md 15.2 and 15.4, CONTRACT_M5 16.12): an action started from outside
    /// (<see cref="BeginExternalAction"/>, the door opening), the E key claimed by the game before the body action
    /// (<see cref="ActionKeyClaimed"/>), and the floor height (<see cref="Floor"/>) that <see cref="Teleport"/> and
    /// <see cref="Release"/> put the furniture on. 5A.1 m16: on a ramp the visual lies on the slope (its pitch along the
    /// facing, its roll across it, about the footprint centre); the sample box stays upright.
    ///
    /// M5 wave 5B (docs/CONTRACT_M5.md 4, 16.8 and 18): the robot's shove, <see cref="BeginPush"/>, an action that travels
    /// at a constant velocity (MotionProfile.BeginPush semantics) until any collider stops it; and <see cref="RampFrame"/>,
    /// the visual's ramp frame for any footprint, which GhostView shares.
    /// </summary>
    [RequireComponent(typeof(CharacterController))]
    public sealed class FurnitureController : MonoBehaviour
    {
        public Transform Visual;
        public Vector3 Size = new Vector3(0.45f, 0.90f, 0.45f);

        /// <summary>Camera yaw used to turn stick input into a world direction. Set by GameState.</summary>
        public Func<float> CameraYaw;

        /// <summary>World space direction that replaces device input when set (probe and tests).</summary>
        public Vector3? ScriptedDirection;

        /// <summary>M4: replaces the careful input (Left Shift, left trigger, InputReader.InjectCareful) when set (replays).</summary>
        public bool? ScriptedCareful;

        public bool IsMoving { get; private set; }
        public Vector3 Velocity { get; private set; }
        public float Yaw { get; private set; }
        public float PlanarSpeed { get; private set; }
        public float YawRate { get; private set; }

        /// <summary>
        /// Increments each time the hop lands (drives the hop tick sound). The office chair rolls instead under
        /// GameRules.Bodies (no hops); without it, it hops like the chair.
        /// </summary>
        public int HopCount { get; private set; }

        // ----- M4 API (docs/CONTRACT_M4.md section 6, amendment 9.3) -----

        /// <summary>What the body is doing besides travelling. Anything but None counts as moving.</summary>
        public enum BodyAction
        {
            None,
            /// <summary>The stool tips over (StoolFallTime).</summary>
            Fall,
            /// <summary>The stool rights itself (StoolRightTime).</summary>
            Right,
            /// <summary>The lamp is switched on or off (LampToggleTime).</summary>
            Toggle,
            /// <summary>M5: an action started from outside with no input, such as opening a door (DoorOpenTime).</summary>
            External,
            /// <summary>
            /// M5 wave 5B (CONTRACT_M5 4, 16.8, 18): the robot's shove (<see cref="BeginPush"/>, RobotPushTime): the only
            /// action that travels, at a constant velocity, until a collider stops it.
            /// </summary>
            Push,
        }

        /// <summary>
        /// M5 (docs/CONTRACT_M5_v3.md 15.2, CONTRACT_M5 16.12): starts an action that counts as moving
        /// (<see cref="ActionActive"/>), with no input, for round(<paramref name="duration"/> / dt) steps: the door
        /// opening, DoorOpenTime (30 steps). True when it starts. It is refused (false, and nothing changes) unless the
        /// furniture is still (not moving on its last step, not gliding, no tip pending), upright, not pinned, not
        /// carried and in no other action, or when the duration is not positive.
        ///
        /// Called between two fixed steps, the action covers the next round(duration / dt) steps. Called from
        /// <see cref="ActionKeyClaimed"/> (inside <see cref="Step"/>), the step of the E press is its first step, as for
        /// the lamp switch. Input and presses are ignored during it, as for every action; when it ends, a held key drives
        /// again on the next step (no neutral step, unlike the pin). A pin or a carry ends it at once.
        /// </summary>
        public bool BeginExternalAction(float duration)
        {
            Init();
            bool still = !IsMoving && !Gliding && !pendingTip; // MUTATION:EXTERNAL_STILL
            bool free = !Tipped && !Pinned && !Carried && !ActionActive;
            if (!(duration > 0f) || !still || !free)
            {
                return false;
            }
            Velocity = Vector3.zero;
            ClearMotionState();
            StartAction(BodyAction.External, duration, lastDt);
            return true;
        }

        /// <summary>
        /// M5 wave 5B (docs/CONTRACT_M5.md 4, 16.8 and 18): the robot's shove, with the semantics of
        /// <see cref="MotionProfile.BeginPush"/>. The furniture travels at a constant velocity of
        /// <paramref name="distance"/> / <paramref name="time"/> along the planar <paramref name="direction"/> for the next
        /// round(<paramref name="time"/> / dt) steps (a 0.25 m shove in 0.5 s is 25 steps of 0.01 m), with its yaw unchanged.
        /// It is an action (<see cref="ActionActive"/>, <see cref="BodyAction.Push"/>): it counts as moving, input and presses
        /// are ignored, and it neither hops nor rolls (the robot slides it). True when it starts.
        ///
        /// It may start while the furniture drives or glides: the drive and any glide end at once. It is refused (false, and
        /// nothing changes) during any action (a fall, a righting, a switch, an external action such as the rock or a door,
        /// another push), while the stool is tipped, pinned or carried, and for a zero direction, distance or time.
        ///
        /// Any collider stops it (CONTRACT_M5 16.8, "blocked by any collider"): from the step a wall, a prop or anything solid
        /// stands against the push direction, the furniture stays where that collider stopped it, and the action runs on to
        /// its end, still moving. When the push ends the furniture is still: a held key drives again from rest on the next
        /// step (no neutral step), and an office chair does not glide. A pin or a carry ends it at once.
        /// </summary>
        public bool BeginPush(Vector3 direction, float distance, float time)
        {
            Init();
            Vector3 d = YawMath.Planar(direction);
            bool free = !ActionActive && !Tipped && !Pinned && !Carried; // MUTATION:PUSH_FREE
            if (!free || !(time > 0f) || !(distance > 0f) || d.sqrMagnitude < 1e-8f)
            {
                return false;
            }
            pushVelocity = d.normalized * (distance / time);
            ClearMotionState();
            StartAction(BodyAction.Push, time, lastDt);
            return true;
        }

        /// <summary>M5 wave 5B: true on every step of a push (<see cref="BeginPush"/>), as <see cref="ActionActive"/> counts them.</summary>
        public bool Pushing => ActionActive && Action == BodyAction.Push;

        /// <summary>
        /// M5 (docs/CONTRACT_M5_v3.md 15.2: a door in reach takes E before the body action), set by GameState. Called
        /// once for each action press (E, gamepad X) consumed by a step that takes input, while the furniture is upright
        /// and in no action (moving or not: the hook decides). True means the press goes to the game (a door): the body
        /// action (the lamp switch) does not happen. The press is consumed either way, so it never fires later. The hook
        /// may call <see cref="BeginExternalAction"/>: the step of the press is then the first step of that action, and
        /// the body does not travel on it. Null: every press is the body's.
        /// </summary>
        public Func<bool> ActionKeyClaimed;

        /// <summary>
        /// M5 (docs/CONTRACT_M5_v3.md 15.4): the level's floor heights, set by the level builder; FloorMap.Flat (0
        /// everywhere) by default, and null reads as Flat. <see cref="Teleport"/> and <see cref="Release"/> put the
        /// furniture at <c>Floor.HeightAt(x, z)</c>; the CharacterController then keeps it on a platform or a ramp. The
        /// sample points, the camera center and the visual follow the transform, so they stand on that floor too.
        /// GhostView reads it for the memory ghost, the seat ghost, the stop ring and the decoy rings.
        /// </summary>
        public FloorMap Floor
        {
            get => floor;
            set => floor = value ?? FloorMap.Flat;
        }

        private FloorMap floor = FloorMap.Flat;

        public BodyDef Body { get; private set; } = BodyDef.For("chair");

        /// <summary>
        /// Careful mode: max speed times CarefulFactor. Set on every step from the input (Left Shift or the gamepad
        /// left trigger, InputReader.InjectCareful, or <see cref="ScriptedCareful"/>), under GameRules.Bodies only.
        /// </summary>
        public bool Careful { get; set; }

        /// <summary>The stool is not upright: from the start of its fall to the end of its righting.</summary>
        public bool Tipped { get; private set; }

        /// <summary>Sat on (CONTRACT_M4 3): no input, never moving. See <see cref="Pin"/>.</summary>
        public bool Pinned { get; private set; }

        /// <summary>
        /// True on every step of an action (fall, righting, switch, M5 external action, M5 wave 5B push), from the step it starts for its
        /// whole duration (round(duration / dt) steps: a 0.3 s switch is 15). It turns false at the start of the step
        /// after the last one.
        /// </summary>
        public bool ActionActive { get; private set; }

        /// <summary>
        /// The stool's tell (CONTRACT_M4 10.3): it goes faster than StoolTellSpeed, the start of the warning band below
        /// the StoolTipSpeed threshold. It leans back and rattles, more and more up to the threshold. Not while careful
        /// mode holds it at its cap, which is below the threshold.
        /// </summary>
        public bool TellActive { get; private set; }

        /// <summary>How strong the tell is: 0 at StoolTellSpeed and below, 1 at StoolTipSpeed and above.</summary>
        public float TellStrength { get; private set; }

        /// <summary>Increments when a falling stool lands (the step after its fall), the Topple noise.</summary>
        public int ToppleCount { get; private set; }

        /// <summary>Increments when a lamp switch starts (the Click noise).</summary>
        public int ToggleCount { get; private set; }

        /// <summary>
        /// Increments every RollNoiseInterval of rolling (office chair, under GameRules.Bodies), whatever the floor:
        /// GameState decides silence.
        /// </summary>
        public int RollCount { get; private set; }

        /// <summary>The light of a lamp body (created by <see cref="SetBody"/>), null for other bodies.</summary>
        public LampLight Lamp;

        /// <summary>The rule switches, set by GameState and read in <see cref="Step"/>. Null means none.</summary>
        public GameRules Rules = GameRules.M4;

        /// <summary>
        /// Office chair, while it moves: where it comes to rest if the input is released now (or where the glide in
        /// progress ends), walls aside. Null otherwise. Planar (y 0), as every rule position; drawn by
        /// GhostView.ShowStopRing, which puts the ring on the floor height there (M5).
        /// </summary>
        public Vector3? PredictedStop { get; private set; }

        /// <summary>The action in progress (None when <see cref="ActionActive"/> is false).</summary>
        public BodyAction Action { get; private set; }

        /// <summary>The stool lies on its side, still, until a move key is pressed.</summary>
        public bool LyingDown => Tipped && Action == BodyAction.None;

        /// <summary>The office chair glides: released (or braked against its motion) and still rolling.</summary>
        public bool Gliding { get; private set; }

        /// <summary>The carry anchor distance for this body (GameState passes it to the carrier's routine).</summary>
        public float CarryForward => Body.CarryForward;

        /// <summary>The max speed of the current step: the body's, halved in careful mode.</summary>
        public float MaxSpeed => Body.MaxSpeed * (Careful ? Tuning.CarefulFactor : 1f);

        /// <summary>
        /// What every inhabitant's ViewRange is multiplied by for this furniture's sample points: LampOffLight for
        /// a lamp body whose light is off under GameRules.Lamp, 1 otherwise (Vision.Step). CONTRACT_M4 10.4: during
        /// the switch itself the rules use the lit range, whichever way it goes (the light changes visually at the
        /// start), so a switch seen for its whole duration is caught.
        /// </summary>
        public float SightRangeFactor
        {
            get
            {
                if (!Body.HasLight || Lamp == null || Rules == null || !Rules.Lamp)
                {
                    return 1f;
                }
                if (Action == BodyAction.Toggle) return 1f; // MUTATION:TOGGLE_LIT
                return Lamp.RangeFactor;
            }
        }

        /// <summary>
        /// The box the vision samples come from: the body size, or, while the stool lies on its side (CONTRACT_M4
        /// 10.3), the lying box: as long as the stool is tall, as high as it is wide. Its fall and its righting keep
        /// the upright box, the taller one, so a stool going down or up in sight is never hidden by its own motion.
        /// </summary>
        public Vector3 SampleSize => LyingDown ? new Vector3(Size.y, Size.x, Size.z) : Size;

        /// <summary>
        /// Gives the furniture a body: the controller radius, height and center, the sample box
        /// (<see cref="Size"/>), the kind, the speeds, and the lamp light for a lamp body. The visual is left as the
        /// level builder made it. Resets the motion and any action; a lamp starts switched on.
        /// </summary>
        public void SetBody(BodyDef body)
        {
            Init();
            Body = body ?? BodyDef.For(null);
            Kind = Body.Kind;
            Size = Body.Size;
            controller.radius = Body.Radius;
            controller.height = Body.Size.y;
            controller.center = new Vector3(0f, Body.Size.y * 0.5f, 0f);

            Velocity = Vector3.zero;
            PlanarSpeed = 0f;
            YawRate = 0f;
            IsMoving = false;
            ClearMotionState();
            Tipped = false;
            Action = BodyAction.None;
            ActionActive = false;
            hopTime = 0f;
            rollTime = 0f;

            if (Body.HasLight)
            {
                if (Lamp == null)
                {
                    var go = new GameObject("LampLight") { layer = gameObject.layer };
                    go.transform.SetParent(transform, false);
                    Lamp = go.AddComponent<LampLight>();
                }
                Lamp.SetOn(true);
                Lamp.Init(Body.Size.y);
            }
            else if (Lamp != null)
            {
                Lamp.SetOn(true);
                DestroyImmediate(Lamp.gameObject);
                Lamp = null;
            }
            Physics.SyncTransforms();
        }

        /// <summary>
        /// Sat on (CONTRACT_M4 3, amendment 9.2): while pinned there is no input, the furniture never moves, and an
        /// action in progress ends at once. Pin(false) re-arms the neutral input wait, as after a release. Only a
        /// change does anything, so GameState may call it on every step with a level-triggered flag.
        /// </summary>
        public void Pin(bool on)
        {
            Init();
            if (on == Pinned)
            {
                return;
            }
            Pinned = on;
            if (on)
            {
                CompleteAction();
                Velocity = Vector3.zero;
                PlanarSpeed = 0f;
                YawRate = 0f;
                IsMoving = false;
                Careful = false;
                ClearMotionState();
            }
            else
            {
                WaitingForNeutralInput = true;
            }
        }

        // ----- M2 (docs/CONTRACT_M2.md 3.3, 3.4, 5) -----

        /// <summary>The player furniture is furniture 0 of a level (decoys come after it).</summary>
        public int Id => 0;
        public string Kind = "chair";

        /// <summary>True while an inhabitant carries the furniture back (from the pick up to the put down).</summary>
        public bool Carried { get; private set; }

        /// <summary>
        /// Creak warning tremble, 0 (none) to 1 (full), set by GameState on every fixed step. It shakes the
        /// visual child only: the transform never moves, so the tremble never counts as motion (3.3).
        /// </summary>
        public float CreakTremble;

        /// <summary>The pose as the rules see it: base position on the floor and yaw.</summary>
        public FurniturePose Pose => new FurniturePose(YawMath.Planar(transform.position), Yaw);

        /// <summary>
        /// Carried: the furniture base goes to <paramref name="anchor"/> with <paramref name="yaw"/>. The
        /// controller is disabled (the carried chair goes where the carrier goes), the velocity is zero, a
        /// carried furniture is never moving (3.5) and never hops. The interpolation poses advance, so the
        /// visual glides between fixed steps instead of stepping at 50 Hz. M4: an action in progress ends at once
        /// (a tipped stool stays tipped until the put down).
        /// </summary>
        public void FollowCarrier(Vector3 anchor, float yaw)
        {
            Init();
            Carried = true;
            CompleteAction();
            ClearMotionState();
            if (controller.enabled)
            {
                controller.enabled = false;
            }
            transform.SetPositionAndRotation(anchor, Quaternion.Euler(0f, yaw, 0f));
            Yaw = yaw;
            Velocity = Vector3.zero;
            PlanarSpeed = 0f;
            YawRate = 0f;
            IsMoving = false;
            hopTime = 0f;
            previousPose = currentPose;
            previousYaw = currentYaw;
            currentPose = anchor;
            currentYaw = yaw;
        }

        /// <summary>
        /// Put down: the furniture stands on the floor at <paramref name="pose"/>, controller enabled. M2.1
        /// (docs/CONTRACT_M2.md 11.5): the move input is then ignored until it has been neutral for one fixed
        /// step, so a key held through the carry never moves the chair right after the put down. M4: the carrier
        /// puts a tipped stool down upright. M5: on the floor height of <see cref="Floor"/> at the pose (its y is ignored).
        /// </summary>
        public void Release(FurniturePose pose)
        {
            Carried = false;
            Teleport(YawMath.Planar(pose.Position), pose.Yaw);
            Action = BodyAction.None;
            ActionActive = false;
            Tipped = false;
            WaitingForNeutralInput = true;
        }

        /// <summary>True from a release (or an unpin) until the move input has been neutral for one fixed step.</summary>
        public bool WaitingForNeutralInput { get; private set; }

        // Tuning.GlideEpsilon: below this remaining glide time the glide is over (float sums of 0.02 s steps).
        // Tuning.BlockedFraction: a wall stops the furniture when it travels less than half (squared: a quarter) of
        // the intended distance.
        // Presentation only (not in Tuning): the stool's rattle while the tell shows.
        private const float RattleDegrees = 1.5f;
        private const float RattleLift = 0.006f;
        // How fast the tell lean follows TellStrength (per second, visual smoothing only; the strength itself rises
        // from 0 to 1 over the 0.25 s of the warning band).
        private const float LeanResponse = 14f;
        // M5 (5A.1 m16), presentation only: below this rise per metre (or ramp length, or head height) the floor under the
        // footprint counts as flat and the visual stays upright.
        private const float SlopeEpsilon = 1e-4f;

        private CharacterController controller;
        private Vector3 previousPose;
        private float previousYaw;
        private Vector3 currentPose;
        private float currentYaw;
        private float hopTime;
        private float visualHopTime;
        private bool hopping;
        private float rollTime;

        // M4 motion state.
        private bool previousWishActive;
        private bool pendingTip;
        private Vector3 moveVelocity;
        private float wallHitInto;
        private float glideSpeed0;
        private float glideRemaining;
        private Vector3 glideDirection;
        private int actionSteps;
        private int actionStepsLeft;
        private int actionStepsDone;
        private float leanBlend;
        private bool stopRingShown;
        // M5: the dt of the last Step, so an action begun from outside counts the same steps as one begun inside.
        private float lastDt = Tuning.FixedStep;
        // M5 wave 5B: the push's planar velocity (zero once a collider stopped it), and whether a collider stood against
        // the push during the current Move (OnControllerColliderHit).
        private Vector3 pushVelocity;
        private bool pushBlocked;

        /// <summary>Center of the bounds, at the fixed step pose.</summary>
        public Vector3 Center => transform.position + new Vector3(0f, Size.y * 0.5f, 0f);

        /// <summary>Interpolated center of the furniture without the hop, for the camera.</summary>
        public Vector3 VisualCenter => interpolatedPosition + new Vector3(0f, Size.y * 0.5f, 0f);

        private Vector3 interpolatedPosition;

        private void Awake()
        {
            Init();
        }

        /// <summary>Idempotent setup (also called by LevelBuilder, since Awake does not run in edit mode builds).</summary>
        public void Init()
        {
            if (controller != null)
            {
                return;
            }
            controller = GetComponent<CharacterController>();
            Yaw = transform.eulerAngles.y;
            currentPose = previousPose = interpolatedPosition = transform.position;
            currentYaw = previousYaw = Yaw;
        }

        /// <summary>
        /// Places the furniture (probe, tests, put down). The motion stops; a tipped stool stays tipped (only
        /// <see cref="Release"/> rights it) and an action in progress goes on. M5 (docs/CONTRACT_M5_v3.md 15.4): the
        /// furniture stands on the floor, at <c>Floor.HeightAt(x, z)</c>; the y of <paramref name="position"/> is ignored.
        /// </summary>
        public void Teleport(Vector3 position, float yaw)
        {
            Init();
            float y = Floor.HeightAt(position.x, position.z); // MUTATION:FLOOR_Y
            position = new Vector3(position.x, y, position.z);
            controller.enabled = false;
            transform.SetPositionAndRotation(position, Quaternion.Euler(0f, yaw, 0f));
            controller.enabled = true;
            Physics.SyncTransforms();
            Yaw = yaw;
            Velocity = Vector3.zero;
            IsMoving = false;
            hopTime = 0f;
            ClearMotionState();
            currentPose = previousPose = interpolatedPosition = position;
            currentYaw = previousYaw = yaw;
            // A teleport (probe, tests) re-arms the input at once; Release sets the wait after its teleport.
            WaitingForNeutralInput = false;
        }

        /// <summary>One fixed step. With <paramref name="allowInput"/> false the furniture takes no input.</summary>
        public void Step(float dt, bool allowInput)
        {
            Init();
            if (dt > 0f)
            {
                lastDt = dt;
            }
            bool bodies = Rules != null && Rules.Bodies;
            bool lampRule = Rules != null && Rules.Lamp;
            wallHitInto = 0f;

            // Presses are consumed on every step, used or not, so a stale press never fires later.
            bool actionPress = InputReader.ActionPressed();
            bool movePress = InputReader.MovePressed();

            // An action that has run all its steps ends at the start of the next step.
            if (ActionActive && actionStepsLeft <= 0)
            {
                CompleteAction();
            }

            Vector3 startPosition = transform.position;
            float startYaw = Yaw;

            if (Pinned)
            {
                // Sat on: no input at all, never moving.
                Velocity = Vector3.zero;
                Careful = false;
                previousWishActive = false;
                ClearMotionState();
                EndStep(dt, startPosition, startYaw, bodies);
                return;
            }

            Vector3 wish = allowInput ? ReadWish() : Vector3.zero;
            if (!allowInput)
            {
                actionPress = false;
                movePress = false;
            }
            if (WaitingForNeutralInput)
            {
                // After a put down or an unpin: a held key is ignored; one neutral step re-arms the input.
                if (wish.sqrMagnitude < 1e-4f)
                {
                    WaitingForNeutralInput = false;
                }
                wish = Vector3.zero;
                actionPress = false;
                movePress = false;
            }
            bool wishActive = wish.sqrMagnitude >= 1e-4f;
            bool wishEdge = wishActive && !previousWishActive;
            previousWishActive = wishActive;
            Careful = bodies && allowInput && (ScriptedCareful ?? InputReader.CarefulHeld());

            if (ActionActive)
            {
                // Falling, righting, switching or an external action: the body does not travel, and input and presses
                // are ignored. M5 wave 5B: a push travels at its constant velocity, until a collider stops it.
                Velocity = Action == BodyAction.Push ? pushVelocity : Vector3.zero; // MUTATION:PUSH_SLIDE
                pendingTip = false;
            }
            else if (Tipped)
            {
                // CONTRACT_M4 2.1: lying on its side until a move key is pressed, then it rights itself.
                Velocity = Vector3.zero;
                if (movePress || wishEdge)
                {
                    StartAction(BodyAction.Right, Tuning.StoolRightTime, dt);
                }
            }
            else if (actionPress && ActionKeyClaimedByGame())
            {
                // M5 (v3 15.2): the press went to the game (a door in reach), not to the body. When the hook began an
                // action (BeginExternalAction), this step is its first one: the body does not travel.
                if (ActionActive)
                {
                    Velocity = Vector3.zero;
                    pendingTip = false;
                }
                else
                {
                    Drive(wish, wishActive, allowInput, bodies, dt);
                }
            }
            else if (actionPress && Body.HasLight && lampRule && Lamp != null)
            {
                // CONTRACT_M4 2.3: E switches the lamp, a 0.2 s action.
                Velocity = Vector3.zero;
                ClearMotionState();
                Lamp.Toggle();
                ToggleCount++;
                StartAction(BodyAction.Toggle, Tuning.LampToggleTime, dt);
            }
            else
            {
                Drive(wish, wishActive, allowInput, bodies, dt);
            }

            // A still furniture does not call Move at all. Move depenetrates the controller from any overlap,
            // so an inhabitant walking through a still chair would shove it, and a shoved chair is a
            // moving chair: the player would be caught for being bumped (found by the probe bot). The
            // small down push of a moving furniture keeps it grounded and never counts as motion.
            if (Velocity.sqrMagnitude > 0f)
            {
                moveVelocity = Velocity;
                pushBlocked = false;
                Vector3 moveFrom = transform.position;
                controller.Move(Velocity * dt + Vector3.down * (2f * dt));
                if (Pushing && pushBlocked)
                {
                    StopPushAtCollider(moveFrom, dt);
                }
            }
            transform.rotation = Quaternion.Euler(0f, Yaw, 0f);
            EndStep(dt, startPosition, startYaw, bodies);
        }

        /// <summary>
        /// M5 wave 5B (CONTRACT_M5 16.8): a collider stood against the push during this step's Move. The furniture keeps the
        /// travel it made up to it (this step's velocity is what it really travelled) and travels no more for the rest of the
        /// push, which still runs to its end: a shove blocked by any collider stops there, it never slides along it.
        /// </summary>
        private void StopPushAtCollider(Vector3 moveFrom, float dt)
        {
            pushVelocity = Vector3.zero;
            Velocity = dt > 0f ? YawMath.Planar(transform.position - moveFrom) / dt : Vector3.zero;
        }

        /// <summary>M5: asks <see cref="ActionKeyClaimed"/> whether this action press goes to the game (once per press).</summary>
        private bool ActionKeyClaimedByGame()
        {
            bool claimed = ActionKeyClaimed != null && ActionKeyClaimed(); // MUTATION:E_CLAIM
            return claimed;
        }

        /// <summary>Travel: the stool tip on release, the office chair glide, or plain driving (M1).</summary>
        private void Drive(Vector3 wish, bool wishActive, bool allowInput, bool bodies, float dt)
        {
            float speed = Velocity.magnitude;
            bool tips = bodies && Body.Tips; // MUTATION:STOOL_TIP
            bool glides = bodies && Body.Glides; // MUTATION:GLIDE
            if (tips && (pendingTip || (allowInput && !wishActive && speed > Tuning.StoolTipSpeed)))
            {
                // CONTRACT_M4 2.1: released too fast, or a head-on wall hit on the last step: the stool tips over.
                StartFall(dt);
                return;
            }
            pendingTip = false;
            if (glides && speed > Tuning.MovingSpeedThreshold && (!wishActive || Vector3.Dot(wish, Velocity) < 0f))
            {
                // CONTRACT_M4 2.4: released, the office chair slows to 0 in exactly OfficeChairStopTime at a constant
                // deceleration (velocity first, then the move). Input against the motion brakes no faster.
                if (!Gliding)
                {
                    Gliding = true;
                    glideSpeed0 = speed;
                    glideRemaining = Tuning.OfficeChairStopTime;
                    glideDirection = Velocity / speed;
                }
                glideRemaining -= dt;
                if (glideRemaining <= Tuning.GlideEpsilon)
                {
                    Velocity = Vector3.zero;
                    Gliding = false;
                }
                else
                {
                    Velocity = glideDirection * (glideSpeed0 * glideRemaining / Tuning.OfficeChairStopTime);
                    // It turns with its velocity, not with the input.
                    Yaw = Mathf.MoveTowardsAngle(Yaw, YawMath.YawOf(glideDirection), Body.TurnRate * dt);
                }
                return;
            }
            Gliding = false;
            if (!wishActive)
            {
                // PRD 3.2: no inertia, the furniture stops on the step where the input is released.
                Velocity = Vector3.zero;
                return;
            }
            wish = Vector3.ClampMagnitude(wish, 1f);
            Vector3 next = Vector3.MoveTowards(Velocity, wish * MaxSpeed, Body.Accel * dt);
            // The stool's two stages: fast up to StageSpeed, then AccelHigh (+inf stage for every other body).
            float cap = Mathf.Max(speed + Body.AccelHigh * dt, Body.StageSpeed);
            if (next.magnitude > cap)
            {
                next = next.normalized * cap;
            }
            Velocity = next;
            Yaw = Mathf.MoveTowardsAngle(Yaw, YawMath.YawOf(wish), Body.TurnRate * dt);
        }

        /// <summary>The measures of the step, the moving predicate, hops and rolls, and the interpolation poses.</summary>
        private void EndStep(float dt, Vector3 startPosition, float startYaw, bool bodies)
        {
            Vector3 delta = YawMath.Planar(transform.position - startPosition);
            PlanarSpeed = dt > 0f ? delta.magnitude / dt : 0f;
            YawRate = dt > 0f ? Mathf.DeltaAngle(startYaw, Yaw) / dt : 0f;
            IsMoving = !Pinned && MotionRule.IsMoving(PlanarSpeed, YawRate, ActionActive);
            // A wall stops the furniture: keep the velocity consistent with what really happened.
            if (dt > 0f && delta.sqrMagnitude < (Velocity * dt).sqrMagnitude * Tuning.BlockedFraction)
            {
                Velocity = delta / dt;
                if (Gliding)
                {
                    float v = Velocity.magnitude;
                    if (v < 1e-3f || glideRemaining <= Tuning.GlideEpsilon)
                    {
                        Velocity = Vector3.zero;
                        Gliding = false;
                    }
                    else
                    {
                        // Slowed by the wall, the glide still ends on time.
                        glideDirection = Velocity / v;
                        glideSpeed0 = v * Tuning.OfficeChairStopTime / glideRemaining;
                    }
                }
            }
            // CONTRACT_M4 2.1 and 10.3: a head-on wall hit (within StoolHeadOnDegrees of the wall normal) faster than
            // the threshold against the wall tips the stool on the next step. A graze along a wall never does.
            if (bodies && Body.Tips && !Tipped && !ActionActive && wallHitInto > Tuning.StoolTipSpeed)
            {
                pendingTip = true;
            }
            // CONTRACT_M4 10.3: the warning band. The tell starts at StoolTellSpeed and is full at StoolTipSpeed. Careful
            // mode caps the stool at 1.2 m/s, inside the band but below the threshold it can never reach: no warning
            // there (a constant rattle would punish the player who obeys "Maj pour aller doucement").
            bool tellable = bodies && Body.Tips && !Tipped && !Pinned;
            float speedNow = Velocity.magnitude;
            bool safeCareful = Careful && MaxSpeed < Tuning.StoolTipSpeed && speedNow <= MaxSpeed + 1e-3f;
            TellActive = tellable && !safeCareful && speedNow > Tuning.StoolTellSpeed; // MUTATION:TELL_SPEED
            TellStrength = TellActive ? Mathf.Clamp01((speedNow - Tuning.StoolTellSpeed) / (Tuning.StoolTipSpeed - Tuning.StoolTellSpeed)) : 0f;

            // Hops (and their sound) only while the body really travels or turns: an action is not a hop. Under
            // GameRules.Bodies the office chair rolls: a roll tick every RollNoiseInterval of rolling instead of hops.
            // M5 wave 5B: a push travels, but the robot slides the furniture: no hop and no roll tick on its steps.
            bool rolls = bodies && Body.Glides;
            hopping = !rolls && !ActionActive && MotionRule.IsMoving(PlanarSpeed, YawRate); // MUTATION:PUSH_HOP
            if (hopping)
            {
                float before = hopTime;
                hopTime += dt;
                if (Mathf.Floor(hopTime * Tuning.HopFrequency / Mathf.PI) > Mathf.Floor(before * Tuning.HopFrequency / Mathf.PI))
                {
                    HopCount++;
                }
            }
            else
            {
                hopTime = 0f;
            }
            if (rolls && !ActionActive && PlanarSpeed > Tuning.MovingSpeedThreshold)
            {
                float before = rollTime;
                rollTime += dt;
                if (Mathf.Floor((rollTime + Tuning.GlideEpsilon) / Tuning.RollNoiseInterval) > Mathf.Floor((before + Tuning.GlideEpsilon) / Tuning.RollNoiseInterval))
                {
                    RollCount++;
                }
            }
            else
            {
                rollTime = 0f;
            }

            if (ActionActive)
            {
                actionStepsLeft--;
                actionStepsDone++;
            }

            PredictedStop = PredictStop(bodies, dt);
            ShowStopRing();

            previousPose = currentPose;
            previousYaw = currentYaw;
            currentPose = transform.position;
            currentYaw = Yaw;
        }

        /// <summary>
        /// Where the office chair comes to rest from now, with the same steps as the glide itself. None during an action: M5
        /// wave 5B, a push ends still, it never glides.
        /// </summary>
        private Vector3? PredictStop(bool bodies, float dt)
        {
            if (!bodies || !Body.Glides || Pinned || Carried || ActionActive || PlanarSpeed <= Tuning.MovingSpeedThreshold)
            {
                return null;
            }
            float speed = Velocity.magnitude;
            if (speed <= 0f)
            {
                return null;
            }
            float v0 = Gliding ? glideSpeed0 : speed;
            float remaining = Gliding ? glideRemaining : Tuning.OfficeChairStopTime;
            Vector3 direction = Gliding ? glideDirection : Velocity / speed;
            return YawMath.Planar(transform.position) + direction * GlideDistance(v0, remaining, dt);
        }

        /// <summary>The distance the glide still covers: the sum of the steps <see cref="Drive"/> will make.</summary>
        private static float GlideDistance(float speed0, float remaining, float dt)
        {
            float distance = 0f;
            if (dt <= 0f)
            {
                return 0f;
            }
            for (int guard = 0; guard < 10000; guard++)
            {
                remaining -= dt;
                if (remaining <= Tuning.GlideEpsilon)
                {
                    break;
                }
                distance += speed0 * remaining / Tuning.OfficeChairStopTime * dt;
            }
            return distance;
        }

        /// <summary>The stop ring of GhostView follows PredictedStop, only for the level's own player furniture.</summary>
        private void ShowStopRing()
        {
            if (!PredictedStop.HasValue && !stopRingShown)
            {
                return;
            }
            GhostView ghost = PlayerGhost();
            if (ghost != null)
            {
                ghost.ShowStopRing(PredictedStop);
            }
            stopRingShown = PredictedStop.HasValue;
        }

        private GhostView PlayerGhost()
        {
            GameState game = Main.Instance != null ? Main.Instance.Game : null;
            return game != null && game.Furniture == this ? game.Ghost : null;
        }

        private void StartFall(float dt)
        {
            Velocity = Vector3.zero;
            ClearMotionState();
            Tipped = true;
            StartAction(BodyAction.Fall, Tuning.StoolFallTime, dt);
        }

        /// <summary>An action of <paramref name="duration"/>, active from this step on for round(duration / dt) steps.</summary>
        private void StartAction(BodyAction action, float duration, float dt)
        {
            Action = action;
            actionSteps = Mathf.Max(1, Mathf.RoundToInt(duration / Mathf.Max(dt, 1e-4f)));
            actionStepsLeft = actionSteps;
            actionStepsDone = 0;
            ActionActive = true;
        }

        /// <summary>Ends the action in progress now: a fall lands (the topple), a righting stands the stool up.</summary>
        private void CompleteAction()
        {
            if (!ActionActive)
            {
                return;
            }
            switch (Action)
            {
                case BodyAction.Fall:
                    ToppleCount++;
                    break;
                case BodyAction.Right:
                    Tipped = false;
                    break;
                case BodyAction.Push:
                    // M5 wave 5B (MotionProfile.BeginPush): the push ends still, so the next step starts from rest.
                    Velocity = Vector3.zero; // MUTATION:PUSH_STILL
                    break;
            }
            Action = BodyAction.None;
            ActionActive = false;
            actionStepsLeft = 0;
        }

        /// <summary>Drops the glide, a pending tip, the tell and the predicted stop.</summary>
        private void ClearMotionState()
        {
            Gliding = false;
            pendingTip = false;
            TellActive = false;
            TellStrength = 0f;
            PredictedStop = null;
            ShowStopRing();
        }

        /// <summary>
        /// The stool's head-on hit: the velocity against the hit normal, kept at its largest over the move, for hits
        /// within StoolHeadOnDegrees of head-on only (CONTRACT_M4 10.3). The hit normal points out of the wall, toward
        /// the stool: the wall's inward normal. M5 wave 5B: during a push, a side hit whose face stands against the push
        /// direction (more than <see cref="Tuning.PushBlockedDot"/>) stops the push (<see cref="StopPushAtCollider"/>); the
        /// floor, a ramp (a normal within 30 degrees of up) and a wall the push only runs along never do.
        /// </summary>
        private void OnControllerColliderHit(ControllerColliderHit hit)
        {
            Vector3 n = YawMath.Planar(hit.normal);
            Vector3 v = YawMath.Planar(moveVelocity);
            float speed = v.magnitude;
            if (n.sqrMagnitude < 0.25f || speed < 1e-4f)
            {
                return;
            }
            if (Pushing && -Vector3.Dot(v / speed, n.normalized) > Tuning.PushBlockedDot) // MUTATION:PUSH_BLOCK
            {
                pushBlocked = true;
            }
            float into = -Vector3.Dot(v, n.normalized);
            bool headOn = into >= speed * Mathf.Cos(Tuning.StoolHeadOnDegrees * Mathf.Deg2Rad);
            if (headOn && into > wallHitInto)
            {
                wallHitInto = into;
            }
        }

        private Vector3 ReadWish()
        {
            if (ScriptedDirection.HasValue)
            {
                return YawMath.Planar(ScriptedDirection.Value);
            }
            Vector2 input = InputReader.Move();
            if (input.sqrMagnitude < 1e-4f)
            {
                return Vector3.zero;
            }
            float camYaw = CameraYaw != null ? CameraYaw() : 0f;
            Vector3 forward = YawMath.Forward(camYaw);
            Vector3 right = YawMath.Forward(camYaw + 90f);
            return forward * input.y + right * input.x;
        }

        /// <summary>
        /// Fills a length 5 array with the sample points of PRD 4.1, at the fixed step pose, from <see cref="SampleSize"/>
        /// (the lying box while the stool lies on its side). M5: the base is the transform, which stands on the floor
        /// height of <see cref="Floor"/> (Teleport and Release put it there, the CharacterController keeps it there on a
        /// platform or a ramp), so the samples add the floor height of the furniture's planar position. The box is
        /// rigid and upright: one floor height for all five points. 5A.1 m16: on a ramp only the visual lies on the slope
        /// (<see cref="LateUpdate"/>); the box stays upright, so the rules are the same on a ramp as before.
        /// </summary>
        public void GetSamplePoints(Vector3[] output)
        {
            VisionMath.SamplePoints(transform.position, Yaw, SampleSize, Tuning.SampleInset, output);
        }

        /// <summary>
        /// M4 (amendment 9.7): the action key and the move presses are latched every rendered frame and consumed by
        /// the next fixed step. A press made during an action, a pin or a carry is dropped.
        /// </summary>
        private void Update()
        {
            if (GamePause.IsPaused)
            {
                return;
            }
            InputReader.LatchPresses(ActionActive || Pinned || Carried);
        }

        private void LateUpdate()
        {
            if (Visual == null)
            {
                return;
            }
            if (GamePause.IsPaused)
            {
                // CONTRACT_M3 6: paused, the visual holds the last fixed step pose (alpha 1), with no hop and no
                // tremble: real time goes on, so anything read from it would keep moving the chair. M5 (5A.1 m16): on
                // its ramp slope, as when it runs.
                interpolatedPosition = currentPose;
                float heldTip = TipAngle(1f);
                Quaternion heldFrame = Quaternion.Euler(0f, currentYaw, 0f);
                float heldLift = 0f;
                GroundFrame(currentPose, currentYaw, ref heldFrame, ref heldLift);
                Vector3 heldBase = currentPose + Vector3.up * heldLift;
                Visual.SetPositionAndRotation(heldBase + heldFrame * TipOffset(heldTip), heldFrame * Quaternion.Euler(0f, 0f, -heldTip));
                return;
            }
            float alpha = Mathf.Clamp01((Time.time - Time.fixedTime) / Time.fixedDeltaTime);
            Vector3 position = Vector3.Lerp(previousPose, currentPose, alpha);
            interpolatedPosition = position;
            float yaw = Mathf.LerpAngle(previousYaw, currentYaw, alpha);
            // The hop is rendered at frame rate but only while the furniture really travels or turns.
            visualHopTime = hopping ? hopTime + alpha * Time.fixedDeltaTime : 0f;
            float hop = Tuning.HopHeight * Mathf.Abs(Mathf.Sin(visualHopTime * Tuning.HopFrequency));
            float rock = Tuning.HopRockDegrees * Mathf.Sin(visualHopTime * Tuning.HopFrequency);
            Vector3 jitter = Vector3.zero;
            float pitch = 0f;
            if (CreakTremble > 0f && !IsMoving)
            {
                // Creak warning (3.3): at most CreakTrembleDistance and CreakTrembleDegrees. Each axis is scaled
                // by 1/sqrt(2), so the combined offset and the combined tilt both stay within their bound.
                float k = Mathf.Clamp01(CreakTremble) * 0.7071f;
                float t = Time.time;
                jitter = new Vector3(Mathf.Sin(t * 61f), 0f, Mathf.Sin(t * 47f + 1.3f)) * (Tuning.CreakTrembleDistance * k);
                rock += Mathf.Sin(t * 53f) * Tuning.CreakTrembleDegrees * k;
                pitch = Mathf.Sin(t * 67f + 0.7f) * Tuning.CreakTrembleDegrees * k;
            }

            // M4.1 stool tell: from StoolTellSpeed it leans back and rattles, fully at StoolTipSpeed (visual only).
            leanBlend = Mathf.MoveTowards(leanBlend, TellStrength, LeanResponse * Time.deltaTime);
            if (leanBlend > 0f)
            {
                float t = Time.time;
                pitch -= Tuning.StoolLeanDegrees * leanBlend;
                rock += Mathf.Sin(t * 71f) * RattleDegrees * leanBlend;
                jitter += Vector3.up * (RattleLift * leanBlend * Mathf.Abs(Mathf.Sin(t * 83f)));
            }

            float tip = TipAngle(alpha);
            Quaternion rotation = Quaternion.Euler(pitch, yaw, rock);
            // M5 (5A.1 m16): on a ramp the visual lies on the slope, turned about its footprint centre (the hop, the
            // creak and the tell then rock it in that frame). Off every ramp the frame is the yaw alone, as before.
            Quaternion ground = Quaternion.Euler(0f, yaw, 0f);
            float lift = 0f;
            if (GroundFrame(position, yaw, ref ground, ref lift)) // MUTATION:VISUAL_SLOPE
            {
                rotation = ground * Quaternion.Euler(pitch, 0f, rock);
                position += Vector3.up * lift;
            }
            if (tip > 0f)
            {
                rotation *= Quaternion.Euler(0f, 0f, -tip);
                position += ground * TipOffset(tip);
            }
            Visual.SetPositionAndRotation(position + jitter + Vector3.up * hop, rotation);
        }

        /// <summary>
        /// M5 (5A.1 m16, CONTRACT_M5_v3 15.4): the frame the visual stands in at the base point <paramref name="basePoint"/>
        /// and <paramref name="yaw"/>. On a ramp of <see cref="Floor"/> it is the floor plane under the footprint
        /// (<see cref="SampleSize"/>): its pitch is the slope along the facing, its roll the slope across it, its heading
        /// stays <paramref name="yaw"/>, and it turns about the footprint centre. True then, with
        /// <paramref name="frame"/> and <paramref name="lift"/> set; false (both untouched) on a flat floor, off every
        /// ramp and while carried (held upright).
        /// <para>The plane is fitted to the footprint's four corners on the ramp's surface carried flat past its foot (0)
        /// and its head (its platform's height): the frame tips smoothly as the furniture rolls over the foot or the head,
        /// and only a ramp the base point stands on (between its two sides) tilts it, so a platform edge or the floor
        /// beside a ramp never does. <paramref name="lift"/> raises the base to the corners' mean height where it is
        /// higher (the foot of a ramp: front on the slope, back on the floor); on the slope itself the base already
        /// stands there and the lift is 0.</para>
        /// The rules never read this: the sample box, the center and the camera stay upright on the transform.
        /// </summary>
        private bool GroundFrame(Vector3 basePoint, float yaw, ref Quaternion frame, ref float lift)
        {
            if (Carried)
            {
                return false;
            }
            return RampFrame(floor, basePoint, yaw, SampleSize, ref frame, ref lift);
        }

        /// <summary>
        /// M5 wave 5B (the 5A.1 m16 follow-up): the frame of the furniture visual on a ramp (<see cref="GroundFrame"/>) for
        /// any footprint, so GhostView lays the memory ghost and the seat ghost on the slope the same way. On a ramp of
        /// <paramref name="floor"/> under the base point <paramref name="basePoint"/>, the plane fitted to the four corners
        /// of the footprint (<paramref name="footprint"/> x and z, turned by <paramref name="yaw"/>) on the ramp's surface
        /// carried flat past its foot and its head: true, with <paramref name="frame"/> (its heading stays the yaw, its
        /// pitch and roll follow the slope) and <paramref name="lift"/> (how far the base rises to the corners' mean height
        /// where that is above <paramref name="basePoint"/>.y). False, with both untouched, on a null or flat floor, off
        /// every ramp, and where the whole footprint lies before the foot or past the head.
        /// </summary>
        public static bool RampFrame(FloorMap floor, Vector3 basePoint, float yaw, Vector3 footprint, ref Quaternion frame, ref float lift)
        {
            if (floor == null || floor.IsFlat || floor.Level.Ramps == null)
            {
                return false;
            }
            Vector3 forward = YawMath.Forward(yaw);
            Vector3 right = YawMath.Forward(yaw + 90f);
            float halfDepth = Mathf.Max(footprint.z * 0.5f, 0.01f);
            float halfWidth = Mathf.Max(footprint.x * 0.5f, 0.01f);
            foreach (RampDef r in floor.Level.Ramps)
            {
                if (r == null || r.Length <= SlopeEpsilon)
                {
                    continue;
                }
                float head = floor.HeadHeight(r);
                Vector3 local = YawMath.Rotate(new Vector3(basePoint.x - r.X, 0f, basePoint.z - r.Z), -r.Yaw);
                if (Mathf.Abs(head) <= SlopeEpsilon || Mathf.Abs(local.x) > r.Width * 0.5f + SlopeEpsilon)
                {
                    continue;
                }
                // The plane through the four footprint corners (exact on the slope, the corners' best fit over a kink).
                Vector3 toFront = forward * halfDepth;
                Vector3 toRight = right * halfWidth;
                float frontRight = RampSurface(r, head, basePoint + toFront + toRight);
                float frontLeft = RampSurface(r, head, basePoint + toFront - toRight);
                float backRight = RampSurface(r, head, basePoint - toFront + toRight);
                float backLeft = RampSurface(r, head, basePoint - toFront - toRight);
                float along = (frontRight + frontLeft - backRight - backLeft) / (4f * halfDepth);
                float across = (frontRight + backRight - frontLeft - backLeft) / (4f * halfWidth);
                if (Mathf.Abs(along) <= SlopeEpsilon && Mathf.Abs(across) <= SlopeEpsilon)
                {
                    // The footprint lies wholly before the foot or past the head: flat there.
                    continue;
                }
                Vector3 up = Vector3.up - forward * along - right * across;
                frame = Quaternion.LookRotation(forward + Vector3.up * along, up);
                lift = Mathf.Max(0f, (frontRight + frontLeft + backRight + backLeft) * 0.25f - basePoint.y);
                return true;
            }
            return false;
        }

        /// <summary>The height of a ramp's surface at a planar point, carried flat past its foot (0) and its head.</summary>
        private static float RampSurface(RampDef r, float head, Vector3 p)
        {
            Vector3 local = YawMath.Rotate(new Vector3(p.x - r.X, 0f, p.z - r.Z), -r.Yaw);
            return head * Mathf.Clamp01((local.z + r.Length * 0.5f) / r.Length);
        }

        /// <summary>The stool's visual tip angle in degrees (0 upright, 90 on its side) at <paramref name="alpha"/> of the step.</summary>
        private float TipAngle(float alpha)
        {
            if (!Tipped)
            {
                return 0f;
            }
            float p = actionSteps > 0 ? Mathf.Clamp01((actionStepsDone - 1 + alpha) / actionSteps) : 1f;
            switch (Action)
            {
                case BodyAction.Fall:
                    // It accelerates as it falls.
                    return 90f * p * p;
                case BodyAction.Right:
                    return 90f * (1f - Mathf.SmoothStep(0f, 1f, p));
                default:
                    return 90f;
            }
        }

        /// <summary>
        /// The visual's offset (in the yaw frame) for a tip of <paramref name="degrees"/>: it rolls onto its right
        /// side about its right bottom edge, and slides so that it ends centered on its base.
        /// </summary>
        private Vector3 TipOffset(float degrees)
        {
            if (degrees <= 0f)
            {
                return Vector3.zero;
            }
            float hx = Size.x * 0.5f;
            var pivot = new Vector3(hx, 0f, 0f);
            Vector3 offset = pivot - Quaternion.Euler(0f, 0f, -degrees) * pivot;
            offset.x -= (hx + Size.y * 0.5f) * (degrees / 90f);
            return offset;
        }

        private void OnDestroy()
        {
            if (stopRingShown)
            {
                GameState game = Main.Instance != null ? Main.Instance.Game : null;
                if (game != null && game.Ghost != null)
                {
                    game.Ghost.ShowStopRing(null);
                }
                stopRingShown = false;
            }
        }
    }
}
