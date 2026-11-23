using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>What one fixed step of the routine was spent on.</summary>
    public enum RoutineActivity
    {
        Idle,
        Walking,
        Telegraph,
        TurningBody,
        TurningHead,
        Waiting,
        Pinned,
        Startled,
        // M2 (docs/CONTRACT_M2.md 5).
        Looking,
        PickingUp,
        Carrying,
        PuttingDown,
        // M4 (docs/CONTRACT_M4.md sections 3 and 9).
        Sitting,
        StandingUp,
        Pratfall,
        SwitchingOn,
    }

    /// <summary>M4: the outcome of a sitting (docs/CONTRACT_M4.md section 3).</summary>
    public enum SitResult
    {
        None,
        OnPlayer,
        OnProp,
        Pratfall,
    }

    /// <summary>docs/CONTRACT_M2.md 3.4.</summary>
    public enum InhabitantMode
    {
        Routine,
        Alerted,
        Investigating,
        Carrying,
        Startled,
    }

    /// <summary>
    /// The inhabitant as pure logic: the station cycle of PRD 5.1 and the M2 modes of docs/CONTRACT_M2.md 3.4
    /// (alerted, investigating, carrying, reactive pin).
    ///
    /// Rules enforced here:
    /// - every body or head turn larger than <see cref="Tuning.TelegraphMinTurn"/> is preceded, immediately, by a
    ///   full <see cref="Tuning.TelegraphDuration"/> telegraph with no motion at all (PRD 4.3), in every mode
    ///   except Startled. The station cycle plans its telegraphs as in M1; on top of that, every turn checks at
    ///   its first step whether it needs one (its own size, or the size of the untelegraphed turn it would
    ///   extend when it follows another turn of the same component without a pause). That check is what keeps
    ///   the invariant through interruptions, resumes and retargets;
    /// - the body never rotates while walking: it turns toward the next corner first;
    /// - each action ends on a step boundary (the remainder of a step is dropped), so a telegraph covers a
    ///   whole number of steps and the probe can measure it exactly.
    ///
    /// Interpretation recorded in the README: when the glances of a station need more time than its dwell
    /// (station 2 of level 1: a 0.8 s hold plus two telegraphs in a 3 s dwell), the dwell is extended until
    /// the head is back to center. A glance is never cut short.
    ///
    /// M4 sitting (docs/CONTRACT_M4.md section 3, amendments 9.2 and 9.3). A station with <see cref="StationDef.Sit"/>
    /// is a sit station. Its position is the seat front, where the inhabitant stands, and its facing is the
    /// seated facing, so the arrival turn is the back turn (telegraphed when over 30 deg). The seat home is
    /// <see cref="StationDef.Seat"/> for "sit": "player", and the prop center (<see cref="StationDef.PropSeat"/>,
    /// CONTRACT_M4 10.2) for a prop; a station never resolved falls back to its own pose. The dwell of a sit station
    /// is: sit down (the moment of sitting is its first step: the seat check, <see cref="JustSat"/>; over
    /// <see cref="Tuning.SitEyeRiseTime"/> the body slides from the seat front to the seat home while the eye lowers,
    /// CONTRACT_M4 10.2: no jump), the dwell and
    /// glances seated, a telegraph, then stand up (the eye rises and the body goes back to the seat front over
    /// <see cref="Tuning.SitEyeRiseTime"/>). Dwell time and glance offsets count from the end of the sit down.
    /// Further rules: the eye never rises without a full telegraph right before (an interrupted stand up is
    /// telegraphed again); a lowered inhabitant (sitting, falling, standing up) looks with the head only and stands
    /// up first, telegraphed, before any walk, turn of the body, pick up or switch on.
    ///
    /// M5 (docs/CONTRACT_M5.md 3 and 16.7, CONTRACT_M5_v3 15.1 and 15.4 to 15.6), all inert with the defaults, so a
    /// routine built as in M4 behaves exactly as in M4:
    /// - <see cref="Personality"/>: walk speed, carry speed times its carry factor, the standing eye (every reset goes
    ///   back to it), range and angle; a personality that does not sit never sits, one that does not hear ignores
    ///   noises, one without memory never investigates, switches on or carries;
    /// - <see cref="Pattern"/> and <see cref="Seed"/>: the station order, indexed by visit (<see cref="VisitIndex"/>);
    /// - station walks are frozen per ordered pair with the station planner; every other walk plans with
    ///   <see cref="InvestigatePlanner"/> (or the station planner when null);
    /// - <see cref="Floor"/>: the eye and the carry anchor add the floor height;
    /// - <see cref="Seats"/>: a seat is claimed at the moment of sitting and released on the first stand-up step or a
    ///   reset; a seat held by someone else makes the visit a standing dwell;
    /// - <see cref="StationDef.Sleep"/>: <see cref="Asleep"/> for the whole dwell, which ends with a
    ///   <see cref="Tuning.WakeTelegraph"/> beat, eye still closed;
    /// - wave 5B: <see cref="BeginPutAway"/>, the walk to a fallen load's clue and its <see cref="Tuning.PutAwayTime"/> beat.
    /// </summary>
    public sealed class InhabitantRoutine
    {
        private enum Kind
        {
            // M1 station cycle.
            Walk,
            Telegraph,
            TurnBody,
            TurnHead,
            Wait,
            DwellStart,
            DwellEnd,
            // M2.
            TurnBoth,         // body to Value and head to Value2, at the same time
            TurnLook,         // body and head toward AlertSource (targets computed when it starts)
            FaceTarget,       // body toward Target (computed when it starts), head to 0
            Look,             // hold the alert look for Value seconds
            PickUp,
            PutDown,
            HoldPin,          // reactive pin: hold the pinned pose, never ends
            Reached,          // marker: the investigation walk is over, ReachedTarget becomes true
            EndAlert,         // marker: restore the plan the alert saved
            EndInvestigation, // marker, run at the start of the next step: resume after a carry
            // M4.
            SitDown,          // first step: the moment of sitting (the seat check); then the eye lowers
            StandUp,          // the eye rises and the body goes back to the stand point
            Fall,             // the pratfall: sat on nothing
            PratfallLook,     // marker: the Alerted look at the empty seat
            SwitchOn,         // the lamp beat (Value seconds), JustSwitchedOn on its last step
            // M5 (wave 5B).
            PutAway,          // the clue beat (Value seconds, read as PickingUp), JustPutAway on its last step
        }

        /// <summary>The <see cref="StationDef.Sit"/> value of a station whose seat is the player furniture.</summary>
        public const string PlayerSeat = "player";

        private const int PhaseStart = 0;
        private const int PhaseTelegraph = 1;
        private const int PhaseTurn = 2;

        /// <summary>
        /// Numerical margin under the telegraph threshold of the runtime check, so that a turn of exactly 30 deg,
        /// whose steps can sum to 30.00001, is still covered. Not a tuning value.
        /// </summary>
        private const float TurnEpsilon = 1e-3f;

        private struct Action
        {
            public Kind Kind;
            public Vector3 Target;
            public float Value;              // walk speed, duration, or the yaw target (head yaw for TurnHead)
            public float Value2;             // head yaw target of the two component turns
            public int Station;              // DwellStart and DwellEnd
            public int Goal;                 // station this action leads to, -1 outside the station cycle
            public int Visit;                // M5: the visit index of Goal (meaningful only when Goal >= 0)
            public RoutineActivity Activity; // Walk: Walking or Carrying
            public bool ReachStop;           // Walk: stop within InvestigateReach of the investigation target
            public int Phase;                // turns: start, telegraph, turn
            public Vector3 From;             // StandUp: the position when it started
            public float FromEye;            // StandUp: the eye height when it started
        }

        private readonly List<StationDef> stations;
        private readonly int startStation;
        private readonly IPathPlanner planner;
        private readonly List<Action> queue = new List<Action>();
        private readonly List<Vector3> corners = new List<Vector3>();
        private float elapsed;
        private bool hasCurrent;
        private Action current;
        private bool started;
        private bool initialDwellSeen;
        private Vector3 startleTarget;
        private InhabitantMode mode = InhabitantMode.Routine;

        // Station bookkeeping for the resume after an investigation (CONTRACT_M2 3.4 "Resume").
        private int stampGoal = -1;
        private int goalStation;
        private bool skipNextLoopCount;

        // What an Alert saved: the plan to resume, exactly where it stopped. The position does not change.
        private readonly List<Action> savedQueue = new List<Action>();
        private Action savedCurrent;
        private bool savedHasCurrent;
        private float savedElapsed;
        private float savedBodyYaw;
        private float savedHeadYaw;
        private float savedPlannedBodyYaw;
        private float savedPlannedHeadYaw;
        private bool savedPlanInitialized;

        private Vector3 investigateTarget;

        // M4 sitting.
        private bool lowered;       // from the moment of sitting (or of the pratfall) to the end of the stand up
        private Vector3 standPoint; // where the body stood when it sat, and where the stand up brings it back
        private bool sitResolved;   // the sit of the current visit to the goal station has happened
        private Vector3 pinPosition;
        private float pinBodyYaw;
        private float pinHeadYaw;

        // M5 (docs/CONTRACT_M5.md 3 and 16.7, CONTRACT_M5_v3 15.1, 15.5, 15.6).
        private PersonalityDef personality = PersonalityDef.For(null);
        private string pattern = RoutinePatterns.Loop;
        private int seed;
        private StationOrder order;      // built on first use from the pattern, the seed and the start station
        private int stampVisit;          // with stampGoal: the visit the queued actions lead to
        private int goalVisit;           // the visit of goalStation
        private int dwellVisit;          // the visit of the last DwellStart
        private readonly Dictionary<int, Vector3[]> stationWalks = new Dictionary<int, Vector3[]>(); // frozen, per ordered pair
        private string heldSeat;         // the seat this routine claimed in Seats, until it stands up
        private bool seatRefused;        // the current visit's seat was taken by someone else: a standing dwell
        private int seatDecidedVisit = -1; // the visit seatRefused was decided for (at the start of the walk there)
        private bool wakePending;        // a sleep dwell ended: the eye opens at the start of the next step
        private FloorMap floor = FloorMap.Flat;

        // Turn tracking, measured exactly as the probe analyzer measures it (one record per step).
        private float bodyRun;
        private float headRun;
        private bool bodyRunTelegraphed;
        private bool headRunTelegraphed;
        private float telegraphStreak;

        public Vector3 Position { get; private set; }
        public float BodyYaw { get; private set; }
        public float HeadYaw { get; private set; }
        public RoutineActivity LastActivity { get; private set; } = RoutineActivity.Idle;
        public bool IsTelegraphing => LastActivity == RoutineActivity.Telegraph;

        /// <summary>True for a frozen pin and for a reactive pin.</summary>
        public bool IsPinned { get; private set; }

        public bool IsStartled { get; private set; }
        public int StationIndex { get; private set; }
        public bool InDwell { get; private set; }

        /// <summary>Number of times the routine came back to its start station (one full loop each).</summary>
        public int LoopsCompleted { get; private set; }

        /// <summary>Increments on the first step of every telegraph (drives the "hm ?" sound).</summary>
        public int TelegraphCount { get; private set; }

        public float EyeYaw => BodyYaw + HeadYaw;
        /// <summary>
        /// The vision eye: <see cref="EyeHeight"/> above <see cref="Position"/> (1.6 m standing, 1.15 m seated, 0.35 m for
        /// the dog), plus the floor height under <see cref="Position"/> (M5, <see cref="Floor"/>, CONTRACT_M5_v3 15.4).
        /// </summary>
        public Vector3 EyePosition => Position + new Vector3(0f, EyeHeight + FloorHeight, 0f); // MUTATION:FLOOR_EYE

        /// <summary>M5: the floor height under <see cref="Position"/> (0 on a flat level).</summary>
        public float FloorHeight => floor.HeightAt(Position.x, Position.z);

        public Vector3 EyeForward => YawMath.Forward(EyeYaw);

        // ----- M2 state (docs/CONTRACT_M2.md 3.4 and 5) -----

        public InhabitantMode Mode => IsStartled ? InhabitantMode.Startled : mode;

        /// <summary>A frozen pin (M1 behavior): no motion, no reaction, no observation, no hearing.</summary>
        public bool IsFrozen { get; private set; }

        /// <summary>The investigation walk is over: GameState now calls BeginCarry or CancelInvestigation.</summary>
        public bool ReachedTarget { get; private set; }

        /// <summary>True from <see cref="BeginCarry"/> until the step the put down ends.</summary>
        public bool IsCarrying { get; private set; }

        /// <summary>True for exactly the step the pick up starts.</summary>
        public bool JustPickedUp { get; private set; }

        /// <summary>True for exactly the step the put down ends (IsCarrying is false on that step).</summary>
        public bool JustPutDown { get; private set; }

        // ----- M4 state (docs/CONTRACT_M4.md section 3, amendments 9.2 and 9.3) -----

        /// <summary>
        /// Seated on a prop or on the player: from the moment of sitting until the step before the first
        /// <see cref="RoutineActivity.StandingUp"/> step (the stand up telegraph is still seated). False during a
        /// pratfall, which sits on nothing.
        /// </summary>
        public bool IsSitting { get; private set; }

        /// <summary>
        /// Level triggered pin flag: seated on the player furniture. True from the moment of sitting
        /// (<see cref="SitResult.OnPlayer"/>) and released on the first <see cref="RoutineActivity.StandingUp"/> step.
        /// </summary>
        public bool SittingOnPlayer { get; private set; }

        /// <summary>
        /// The seat home of the sit station the routine is heading to or sitting at: <see cref="StationDef.Seat"/>
        /// for "sit": "player", the prop center for a prop (<see cref="StationDef.PropSeat"/>). Set from the start of
        /// the walk to that station, and
        /// kept afterwards. While seated, <see cref="Position"/> is this position once the sit down is over (it slides
        /// there over <see cref="Tuning.SitEyeRiseTime"/>, CONTRACT_M4 10.2).
        /// </summary>
        public FurniturePose SeatHome { get; private set; }

        // ----- M5 (docs/CONTRACT_M5.md 3, 16.7 and 16.12; CONTRACT_M5_v3 15.1, 15.4 to 15.6) -----
        // Set these before the first step; RoutineFactory.Create does it for the game, the audit and the tests.

        /// <summary>
        /// The personality: walk speed, carry factor, eye height, range and angle, roles (CONTRACT_M5 3). Never null:
        /// setting null gives the default row, which is the M1 to M4 inhabitant exactly. Setting it while standing also
        /// sets <see cref="EyeHeight"/> to the personality's eye.
        /// </summary>
        public PersonalityDef Personality
        {
            get => personality;
            set
            {
                personality = value ?? PersonalityDef.For(null);
                if (!lowered)
                {
                    EyeHeight = StandingEye;
                }
            }
        }

        /// <summary>"loop" (default), "pingpong" or "wander" (CONTRACT_M5 3, 16.7); null or unknown is a loop.</summary>
        public string Pattern
        {
            get => pattern;
            set
            {
                pattern = RoutinePatterns.Normalize(value);
                order = null;
            }
        }

        /// <summary>The wander seed, in [0, 2^31 - 1]; ignored by the other patterns.</summary>
        public int Seed
        {
            get => seed;
            set
            {
                seed = value;
                order = null;
            }
        }

        /// <summary>
        /// The index k of the station visit the routine is at or heading to: 0 is the start station (the level starts in
        /// its dwell), and k becomes k + 1 when the walk to the next station starts. Draws are indexed by visit
        /// (CONTRACT_M5 16.7): alerts, investigations, carries and resumes never change it, and a resume goes back to the
        /// station already drawn for it. <see cref="StationOfVisit"/> gives the station of any visit.
        /// </summary>
        public int VisitIndex => goalVisit;

        /// <summary>The station of visit <paramref name="visit"/> of this routine's pattern (the same every time it is asked).</summary>
        public int StationOfVisit(int visit)
        {
            if (stations.Count == 0)
            {
                return 0;
            }
            if (order == null)
            {
                order = new StationOrder(pattern, stations.Count, startStation, seed);
            }
            return order.StationOf(visit);
        }

        /// <summary>The floor heights the eye and the carry anchor add (CONTRACT_M5_v3 15.4); null means flat.</summary>
        public FloorMap Floor
        {
            get => floor;
            set => floor = value ?? FloorMap.Flat;
        }

        /// <summary>
        /// True while the inhabitant sleeps at a <see cref="StationDef.Sleep"/> station (the dog, CONTRACT_M5_v3 4 and
        /// 15.5): its eye is closed and it sees nothing. From the step its dwell starts to the end of the
        /// <see cref="Tuning.WakeTelegraph"/> beat that ends the dwell (eye still closed); the eye opens on the next
        /// step, before the departure turn and its own telegraph.
        /// </summary>
        public bool Asleep { get; private set; }

        /// <summary>
        /// The planner of every walk outside the station cycle (CONTRACT_M5_v3 15.1): investigations, the switch-on, the
        /// carry, both branches of the resume and the carry's approach yaw. Null means the station planner. In the game it
        /// plans with the current door mask; station walks never use it (they are frozen, see
        /// <see cref="FreezeStationWalks"/>).
        /// </summary>
        public IPathPlanner InvestigatePlanner { get; set; }

        /// <summary>
        /// The level's seat registry, shared by every routine of the level (CONTRACT_M5_v3 15.6). Null means every seat is
        /// free and nothing is claimed (M4, the EditMode tests).
        /// </summary>
        public SeatRegistry Seats { get; set; }

        /// <summary>This routine's id in <see cref="Seats"/> (its inhabitant index).</summary>
        public int SeatOwner { get; set; }

        /// <summary>The area mask the station walks were planned with (information for the audit; -1 is every area).</summary>
        public int StationAreaMask { get; set; } = -1;

        /// <summary>The personality's view range in metres, before any lamp factor: the one source for Vision and the audit.</summary>
        public float ViewRange => personality.ViewRange; // MUTATION:PERSONALITY_RANGE

        /// <summary>The personality's cone half angle in degrees.</summary>
        public float HalfAngle => personality.HalfAngle;

        /// <summary>The personality's noise radius factor (0 when it does not hear): pass it to Hearing.Hears.</summary>
        public float HearingFactor => personality.Hears ? personality.HearingFactor : 0f;

        /// <summary>
        /// The geometric sight test of this inhabitant (PRD 4.1, checks 1 and 2): asleep sees nothing; otherwise the
        /// point is in the cone of <see cref="EyePosition"/> and <see cref="EyeForward"/>, at the personality's range
        /// times <paramref name="rangeFactor"/> (the lamp) and its half angle. Occlusion stays the caller's.
        /// </summary>
        public bool InCone(Vector3 point, float rangeFactor = 1f)
        {
            return !Asleep && VisionMath.IsInCone(EyePosition, EyeForward, point, ViewRange * rangeFactor, HalfAngle);
        }

        /// <summary>The seat this routine holds in <see cref="Seats"/>, or null.</summary>
        public string HeldSeat => heldSeat;

        /// <summary>
        /// True for exactly the last step of the put-away beat (CONTRACT_M5 6, wave 5B): GameState removes the clue. False
        /// again on the next step, when the routine resumes.
        /// </summary>
        public bool JustPutAway { get; private set; }

        /// <summary>
        /// M5 (docs/CONTRACT_M5.md 6, wave 5B): a fallen load's clue was found. Like <see cref="BeginSwitchOn"/>: accepted in
        /// Routine and Alerted only, never by a personality without memory (the dog), and the mode is Investigating until
        /// it resumes. A lowered inhabitant stands up first (telegraphed); it walks to the clue with
        /// <see cref="InvestigatePlanner"/> (or the station planner when null), stopping within
        /// <see cref="Tuning.InvestigateReach"/> of it, faces it, picks it up for <see cref="Tuning.PutAwayTime"/>
        /// (<see cref="RoutineActivity.PickingUp"/>, but never <see cref="JustPickedUp"/> nor <see cref="IsCarrying"/>: it
        /// carries nothing), raises <see cref="JustPutAway"/> on the beat's last step, and resumes on the next step as after
        /// an investigation. It never sets <see cref="ReachedTarget"/>. Without a path it walks a straight line.
        /// </summary>
        public void BeginPutAway(Vector3 clue)
        {
            if (!BeginApproach(clue))
            {
                return;
            }
            Vector3 here = StandUpFirst();
            if (!WithinReachFrom(here))
            {
                if (!OtherPlanner.TryPlan(here, investigateTarget, corners) || corners.Count == 0)
                {
                    Debug.LogWarning($"[InhabitantRoutine] no path to the clue ({investigateTarget.x:0.00}, {investigateTarget.z:0.00}): straight line fallback");
                    corners.Clear();
                    corners.Add(investigateTarget);
                }
                EnqueuePath(here, WalkSpeed, RoutineActivity.Walking, true);
            }
            Enqueue(new Action { Kind = Kind.FaceTarget, Target = investigateTarget });
            Enqueue(new Action { Kind = Kind.PutAway, Value = Tuning.PutAwayTime });
            Enqueue(new Action { Kind = Kind.EndInvestigation });
        }

        /// <summary>True for exactly the step of the moment of sitting (whatever the <see cref="LastSitResult"/>).</summary>
        public bool JustSat { get; private set; }

        /// <summary>The outcome of the last moment of sitting; None before the first one.</summary>
        public SitResult LastSitResult { get; private set; }

        /// <summary>
        /// Eye height above the floor: the personality's eye standing (<see cref="Tuning.EyeHeight"/>, the dog's
        /// <see cref="Tuning.DogEyeHeight"/>), interpolated down to <see cref="Tuning.SitEyeHeight"/> over
        /// <see cref="Tuning.SitEyeRiseTime"/> from the moment of sitting (or of the pratfall), and back up over the same
        /// time during the stand up. Every reset (the stand up, Pin, Startle) goes back to the personality's eye.
        /// </summary>
        public float EyeHeight { get; private set; } = Tuning.EyeHeight;

        /// <summary>M5: the personality's standing eye height (CONTRACT_M5_v3 15.5).</summary>
        private float StandingEye => personality.EyeHeight; // MUTATION:DOG_EYE

        /// <summary>M5: the walk speed of the station cycle, the investigations and the resumes.</summary>
        private float WalkSpeed => personality.WalkSpeed;

        /// <summary>
        /// M5: the carry speed, times the personality's carry factor. DOGCARRY: the dog (carry factor 0, it never carries in
        /// its arms) drags the furniture at <see cref="Tuning.DogDragSpeed"/>.
        /// </summary>
        private float CarrySpeed => personality.Barks ? Tuning.DogDragSpeed : Tuning.CarrySpeed * personality.CarryFactor;

        /// <summary>DOGCARRY: how high the carried furniture is held: a human lifts it, the dog's mouth barely does.</summary>
        private float CarryLift => personality.Barks ? Tuning.DogDragLift : Tuning.CarryHeight;

        /// <summary>M5: sit stations sit only with sitting on and a personality that sits (never the dog).</summary>
        private bool CanSit => SittingEnabled && personality.Sits;

        /// <summary>M5 (CONTRACT_M5_v3 15.1): the planner of every walk that is not a station walk.</summary>
        private IPathPlanner OtherPlanner => InvestigatePlanner ?? planner;

        /// <summary>M5: the planner of the frozen station walks: the station planner, whatever InvestigatePlanner is.</summary>
        private IPathPlanner StationPlanner => planner; // MUTATION:FROZEN_WALK

        /// <summary>
        /// Set by GameState: true when the player's seat body is home at sitting time. Called once, at the moment of
        /// sitting of a "sit": "player" station. Null means occupied (the audit and EditMode tests).
        /// </summary>
        public System.Func<bool> SeatOccupied;

        /// <summary>Per body, set by GameState (CONTRACT_M4 9.3): the carry goal and <see cref="CarryAnchor"/> use it.</summary>
        public float CarryForward = Tuning.CarryForward;

        /// <summary>True for exactly the last step of the switch on beat: GameState turns the lamp on.</summary>
        public bool JustSwitchedOn { get; private set; }

        /// <summary>
        /// The <see cref="GameRules.Sitting"/> switch, set by GameState (amendment 9.9). False makes every sit station
        /// a plain dwell. Read when a dwell is planned. True by default, so the audit and tests sit.
        /// </summary>
        public bool SittingEnabled = true;

        /// <summary>
        /// The routine is on its way to a "sit": "player" station and has not sat yet: from the start of the walk
        /// there until the moment of sitting, through Alerted interruptions (the seat ghost telegraph, CONTRACT_M4
        /// section 3). False while investigating, carrying, pinned or startled. M5 (CONTRACT_M5_v3 15.6): false while
        /// another inhabitant holds the "player" seat in <see cref="Seats"/>, and for a visit whose seat was found taken
        /// (a standing dwell); never true for a personality that does not sit.
        /// </summary>
        public bool SitTargetsPlayer =>
            CanSit && started && !sitResolved && !seatRefused && !IsStartled && !IsFrozen && !IsPinned
            && (mode == InhabitantMode.Routine || mode == InhabitantMode.Alerted)
            && goalStation >= 0 && goalStation < stations.Count && IsPlayerSeat(stations[goalStation])
            && !TakenByRival(stations[goalStation]);

        /// <summary>The body is down: sitting, falling (pratfall) or standing up. Looks are head only.</summary>
        public bool IsLowered => lowered;

        public FurniturePose CarryReturnPose { get; private set; }
        /// <summary>
        /// Where the carried furniture is held: <see cref="CarryForward"/> ahead of the body, <see cref="Tuning.CarryHeight"/>
        /// above the floor under the inhabitant (M5, <see cref="Floor"/>). DOGCARRY: for the dog, its near edge is at the
        /// dog's snout (the body's CarryForward reaches it as it reaches a human's hands), <see cref="Tuning.DogDragLift"/> high.
        /// </summary>
        public Vector3 CarryAnchor => Position + YawMath.Forward(BodyYaw) * CarryForward + Vector3.up * (CarryLift + FloorHeight);

        /// <summary>
        /// DOGCARRY: the dog's happy beat right after it dropped the furniture it dragged home (still in the Carrying mode, the
        /// put down over, before the routine resumes). Presentation reads it (the wag).
        /// </summary>
        public bool IsWagging => personality.Barks && mode == InhabitantMode.Carrying && !IsCarrying && LastActivity == RoutineActivity.Looking;

        /// <summary>
        /// DOGCARRY: true when <see cref="BeginCarry"/> to <paramref name="returnPose"/> would find a path with
        /// <see cref="InvestigatePlanner"/> (the humans' planner) from where the body stands, instead of the straight line
        /// fallback. GameState asks it before the dog drags the furniture home (no path: a human is called, as before).
        /// </summary>
        public bool CanPlanCarry(FurniturePose returnPose)
        {
            Vector3 here = lowered ? standPoint : Position;
            Vector3 home = YawMath.Planar(returnPose.Position);
            Vector3 goal = home - YawMath.Forward(ApproachYaw(here, home)) * CarryForward;
            if (YawMath.Planar(goal - here).magnitude <= Tuning.InvestigateReach)
            {
                return true;
            }
            return OtherPlanner.TryPlan(here, goal, carryProbe) && carryProbe.Count > 0;
        }

        private readonly List<Vector3> carryProbe = new List<Vector3>();
        public Vector3 AlertSource { get; private set; }

        public InhabitantRoutine(List<StationDef> stations, int startStation)
            : this(stations, startStation, StraightPlanner.Instance)
        {
        }

        /// <summary>Station walks, investigations and carries are planned with <paramref name="planner"/>.</summary>
        public InhabitantRoutine(List<StationDef> stations, int startStation, IPathPlanner planner)
        {
            this.stations = stations ?? new List<StationDef>();
            this.planner = planner ?? StraightPlanner.Instance;
            this.startStation = this.stations.Count == 0 ? 0 : Mathf.Clamp(startStation, 0, this.stations.Count - 1);
            if (this.stations.Count > 0)
            {
                StationDef s = this.stations[this.startStation];
                Position = s.Position;
                BodyYaw = s.Facing;
                // M5: a level that starts in a sleep dwell starts asleep.
                Asleep = s.Sleep;
            }
            StationIndex = this.startStation;
            SetGoal(this.startStation, 0);
        }

        // ----- Commands -----

        /// <summary>
        /// Freezes the routine at a pose (M1, probe only). There is deliberately no unpin: the plan was made for
        /// the pose before the pin, so a pinned level is always restarted.
        /// </summary>
        public void Pin(Vector3 position, float bodyYaw, float headYaw)
        {
            Pin(position, bodyYaw, headYaw, false);
        }

        /// <summary>
        /// Pins the inhabitant at a pose, cancelling any alert, investigation or carry. A frozen pin
        /// (<paramref name="reactive"/> false) is the M1 pin. A reactive pin holds the pose in place of the
        /// station cycle but still accepts Alert and Investigate, then walks back to the pose and holds it again.
        /// </summary>
        public void Pin(Vector3 position, float bodyYaw, float headYaw, bool reactive)
        {
            CancelEverything();
            IsPinned = true;
            IsFrozen = !reactive;
            Position = YawMath.Planar(position);
            BodyYaw = bodyYaw;
            HeadYaw = Mathf.Clamp(headYaw, -Tuning.HeadYawLimit, Tuning.HeadYawLimit);
            pinPosition = Position;
            pinBodyYaw = BodyYaw;
            pinHeadYaw = HeadYaw;
            // The pose jumped: that is not a turn.
            ResetTurnTracking();
            if (reactive)
            {
                stampGoal = -1;
                Enqueue(new Action { Kind = Kind.HoldPin });
            }
        }

        /// <summary>Stops the routine for good and turns to face the target (PRD 5.2, Startled).</summary>
        public void Startle(Vector3 target)
        {
            CancelEverything();
            IsStartled = true;
            IsPinned = false;
            IsFrozen = false;
            startleTarget = target;
        }

        /// <summary>
        /// A noise was heard (CONTRACT_M2 3.2, 3.4). Accepted in Routine (any kind) and in Alerted, where only the kinds
        /// of <see cref="Hearing.RetargetsAlerted"/> retarget (a creak, and since M5 a bark or a crash): an alerted
        /// inhabitant ignores hops. M5: a personality that does not hear (the dog) ignores every noise.
        /// </summary>
        public void Alert(Vector3 source, NoiseKind kind)
        {
            if (IsStartled || IsFrozen || !personality.Hears)
            {
                return;
            }
            if (mode == InhabitantMode.Alerted)
            {
                if (!Hearing.RetargetsAlerted(kind))
                {
                    return;
                }
                AlertSource = source;
                RetargetAlert();
                return;
            }
            if (mode != InhabitantMode.Routine)
            {
                return;
            }
            EnsureStarted();
            BeginLook(source);
        }

        /// <summary>
        /// Saves the plan exactly where it stands and starts an Alerted look at <paramref name="source"/>: the look
        /// turn (head only while lowered), the hold, the turn back, then the saved plan.
        /// </summary>
        private void BeginLook(Vector3 source)
        {
            AlertSource = source;

            savedQueue.Clear();
            savedQueue.AddRange(queue);
            savedCurrent = current;
            savedHasCurrent = hasCurrent;
            savedElapsed = elapsed;
            savedBodyYaw = BodyYaw;
            savedHeadYaw = HeadYaw;
            savedPlannedBodyYaw = plannedBodyYaw;
            savedPlannedHeadYaw = plannedHeadYaw;
            savedPlanInitialized = planInitialized;

            mode = InhabitantMode.Alerted;
            ClearPlan();
            stampGoal = -1;
            Enqueue(new Action { Kind = Kind.TurnLook });
            EnqueueAlertTail();
        }

        /// <summary>
        /// Walks to a displaced furniture (CONTRACT_M2 3.4). Accepted in Routine and Alerted. Stops within
        /// <see cref="Tuning.InvestigateReach"/> of the target or at the end of the path, faces the target, and
        /// sets <see cref="ReachedTarget"/>; at once when there is no path.
        /// </summary>
        public void Investigate(Vector3 target)
        {
            if (!BeginApproach(target))
            {
                return;
            }
            // M4: a lowered inhabitant stands up first, telegraphed; the walk starts from where it stood.
            Vector3 here = StandUpFirst();
            if (WithinReachFrom(here))
            {
                Enqueue(new Action { Kind = Kind.FaceTarget, Target = investigateTarget });
                Enqueue(new Action { Kind = Kind.Reached });
                return;
            }
            if (!OtherPlanner.TryPlan(here, investigateTarget, corners))
            {
                if (queue.Count == 0)
                {
                    ReachedTarget = true;
                    return;
                }
                // Lowered: reached once standing.
                Enqueue(new Action { Kind = Kind.Reached });
                return;
            }
            EnqueuePath(here, WalkSpeed, RoutineActivity.Walking, true);
            Enqueue(new Action { Kind = Kind.FaceTarget, Target = investigateTarget });
            Enqueue(new Action { Kind = Kind.Reached });
        }

        /// <summary>
        /// M4 (docs/CONTRACT_M4.md 2.3, amendment 9.3): the lamp was seen switched off. Like an investigation to the
        /// lamp (accepted in Routine and Alerted, mode Investigating, a lowered inhabitant stands up first), but it
        /// never sets <see cref="ReachedTarget"/>: within <see cref="Tuning.InvestigateReach"/> of the lamp it faces
        /// it, holds a <see cref="Tuning.LampSwitchOnTime"/> beat (<see cref="RoutineActivity.SwitchingOn"/>),
        /// raises <see cref="JustSwitchedOn"/> on the beat's last step, and resumes on the next step like after a
        /// carry. Without a path it walks a straight line.
        /// </summary>
        public void BeginSwitchOn(Vector3 lampPosition)
        {
            if (!BeginApproach(lampPosition))
            {
                return;
            }
            Vector3 here = StandUpFirst();
            if (!WithinReachFrom(here))
            {
                if (!OtherPlanner.TryPlan(here, investigateTarget, corners) || corners.Count == 0)
                {
                    Debug.LogWarning($"[InhabitantRoutine] no path to the lamp ({investigateTarget.x:0.00}, {investigateTarget.z:0.00}): straight line fallback");
                    corners.Clear();
                    corners.Add(investigateTarget);
                }
                EnqueuePath(here, WalkSpeed, RoutineActivity.Walking, true);
            }
            Enqueue(new Action { Kind = Kind.FaceTarget, Target = investigateTarget });
            Enqueue(new Action { Kind = Kind.SwitchOn, Value = Tuning.LampSwitchOnTime });
            Enqueue(new Action { Kind = Kind.EndInvestigation });
        }

        /// <summary>
        /// The dog's run (CONTRACT_M5 20): true from <see cref="BeginRun"/> until the routine resumes (a cancel, a pin, a
        /// startle). The mode is Investigating all along, so the "!" marker shows.
        /// </summary>
        public bool Running { get; private set; }

        /// <summary>
        /// CONTRACT_M5 20: the dog saw the furniture moving and barked: it runs to <paramref name="target"/> at
        /// <see cref="Tuning.DogRunSpeed"/> with <see cref="InvestigatePlanner"/>, stops within
        /// <see cref="Tuning.InvestigateReach"/> of it, faces it and sets <see cref="ReachedTarget"/>, then stands there
        /// (the hold) until GameState calls <see cref="CancelInvestigation"/>, which resumes the routine as after an
        /// investigation. Accepted in Routine and Alerted (no memory needed), and again while running (a new target).
        /// Without a path, ReachedTarget at once. Turns are telegraphed as always.
        /// </summary>
        public void BeginRun(Vector3 target)
        {
            if (Running && mode == InhabitantMode.Investigating && !IsStartled && !IsFrozen)
            {
                investigateTarget = YawMath.Planar(target);
                ReachedTarget = false;
                ClearPlan();
                stampGoal = -1;
            }
            else if (!BeginApproach(target, true))
            {
                return;
            }
            Running = true;
            Vector3 here = StandUpFirst();
            if (!WithinReachFrom(here))
            {
                if (!OtherPlanner.TryPlan(here, investigateTarget, corners) || corners.Count == 0)
                {
                    ReachedTarget = queue.Count == 0;
                    if (!ReachedTarget)
                    {
                        Enqueue(new Action { Kind = Kind.Reached });
                    }
                    return;
                }
                EnqueuePath(here, Tuning.DogRunSpeed, RoutineActivity.Walking, true);
            }
            Enqueue(new Action { Kind = Kind.FaceTarget, Target = investigateTarget });
            Enqueue(new Action { Kind = Kind.Reached });
        }

        /// <summary>
        /// The common start of Investigate and BeginSwitchOn: accepted in Routine and Alerted only, and never by a
        /// personality without memory (the dog never investigates nor switches on, CONTRACT_M5_v3 4) unless
        /// <paramref name="anyone"/> (the dog's run, CONTRACT_M5 20). Drops the plan and the saved alert plan, and records
        /// where to resume.
        /// </summary>
        private bool BeginApproach(Vector3 target, bool anyone = false)
        {
            if (IsStartled || IsFrozen || (!personality.Memory && !anyone))
            {
                return false;
            }
            if (mode != InhabitantMode.Routine && mode != InhabitantMode.Alerted)
            {
                return false;
            }
            // Where to resume: an Alert in progress did not change the station bookkeeping, so the plan it saved
            // is described by the same goal station. A dwell interrupted here is replayed in full later, and that
            // replay does not count as a new loop.
            if (!IsPinned && InDwell)
            {
                skipNextLoopCount = true;
            }
            InDwell = false;
            savedQueue.Clear();
            savedHasCurrent = false;
            // M5: the dwell is dropped, so is any sleep.
            Asleep = false;
            wakePending = false;

            mode = InhabitantMode.Investigating;
            ReachedTarget = false;
            Running = false;
            investigateTarget = YawMath.Planar(target);
            ClearPlan();
            stampGoal = -1;
            return true;
        }

        /// <summary>
        /// When lowered, queues the stand up (a full telegraph, then the rise) and returns the stand point, where
        /// the next walk starts; otherwise queues nothing and returns <see cref="Position"/>.
        /// </summary>
        private Vector3 StandUpFirst()
        {
            if (!lowered)
            {
                return Position;
            }
            Enqueue(new Action { Kind = Kind.Telegraph, Value = Tuning.TelegraphDuration });
            Enqueue(new Action { Kind = Kind.StandUp, Value = Tuning.SitEyeRiseTime });
            return standPoint;
        }

        /// <summary>
        /// Picks the investigated furniture up and carries it back to <paramref name="returnPose"/>
        /// (CONTRACT_M2 3.4). Accepted only while investigating.
        /// </summary>
        public void BeginCarry(FurniturePose returnPose)
        {
            if (IsStartled || IsFrozen || mode != InhabitantMode.Investigating)
            {
                return;
            }
            mode = InhabitantMode.Carrying;
            IsCarrying = true;
            ReachedTarget = false;
            // DOGCARRY: the dog's run is over once it carries (a new bark during the drag or the wag starts no run).
            Running = false;
            CarryReturnPose = returnPose;
            ClearPlan();
            stampGoal = -1;

            Vector3 here = StandUpFirst();
            Vector3 home = YawMath.Planar(returnPose.Position);
            // M4: the goal is CarryForward (per body) short of home, so that CarryAnchor lands on home.
            Vector3 goal = home - YawMath.Forward(ApproachYaw(here, home)) * CarryForward;
            if (!OtherPlanner.TryPlan(here, goal, corners) || corners.Count == 0)
            {
                Debug.LogWarning($"[InhabitantRoutine] no carry path from ({here.x:0.00}, {here.z:0.00}) to ({goal.x:0.00}, {goal.z:0.00}): straight line fallback");
                corners.Clear();
                corners.Add(goal);
            }
            Enqueue(new Action { Kind = Kind.PickUp, Value = Tuning.PickUpDuration });
            EnqueuePath(here, CarrySpeed, RoutineActivity.Carrying, false);
            Enqueue(new Action { Kind = Kind.FaceTarget, Target = home });
            Enqueue(new Action { Kind = Kind.PutDown, Value = Tuning.PutDownDuration });
            if (personality.Barks)
            {
                // DOGCARRY: the dog dropped it home: a happy wag beat (IsWagging) before it resumes its routine.
                Enqueue(new Action { Kind = Kind.Look, Value = Tuning.DogWagTime });
            }
            Enqueue(new Action { Kind = Kind.EndInvestigation });
        }

        /// <summary>The investigated furniture moved away: resume the routine (CONTRACT_M2 3.4 "Resume").</summary>
        public void CancelInvestigation()
        {
            if (IsStartled || IsFrozen || mode != InhabitantMode.Investigating)
            {
                return;
            }
            ResumeAfterInvestigation();
        }

        // ----- Stepping -----

        public void Step(float dt)
        {
            JustPickedUp = false;
            JustPutDown = false;
            JustSat = false;
            JustSwitchedOn = false;
            JustPutAway = false;
            if (wakePending)
            {
                // The sleep dwell (and its wake telegraph) ended on the previous step: the eye opens now.
                wakePending = false;
                Asleep = false;
            }
            float bodyBefore = BodyYaw;
            float headBefore = HeadYaw;
            StepActions(dt);
            TrackTurns(bodyBefore, headBefore, dt);
        }

        private void StepActions(float dt)
        {
            if (IsStartled)
            {
                StepStartled(dt);
                return;
            }
            if (IsFrozen)
            {
                LastActivity = RoutineActivity.Pinned;
                return;
            }
            if (holdLeft > 0f)
            {
                // M6 (CONTRACT_M6 2.7): stopped in front of a door it opens; the walk resumes where it stopped.
                if (hasCurrent && current.Kind == Kind.Walk)
                {
                    LastActivity = RoutineActivity.Waiting;
                    holdLeft -= dt;
                    if (holdLeft < 1e-4f)
                    {
                        holdLeft = 0f;
                    }
                    return;
                }
                holdLeft = 0f;
            }
            EnsureStarted();
            DrainInstantActions(true);
            if (!hasCurrent)
            {
                LastActivity = RoutineActivity.Idle;
                return;
            }
            bool done = Run(ref current, dt);
            if (done)
            {
                hasCurrent = false;
                DrainInstantActions(false);
            }
        }

        private void StepStartled(float dt)
        {
            LastActivity = RoutineActivity.Startled;
            Vector3 to = YawMath.Planar(startleTarget - Position);
            if (to.sqrMagnitude > 1e-6f)
            {
                BodyYaw = Mathf.MoveTowardsAngle(BodyYaw, YawMath.YawOf(to), 720f * dt);
            }
            HeadYaw = Mathf.MoveTowards(HeadYaw, 0f, 400f * dt);
        }

        private bool CycleActive => mode == InhabitantMode.Routine && !IsPinned && started && stations.Count > 0;

        private void EnsureStarted()
        {
            if (started || IsPinned || mode != InhabitantMode.Routine || stations.Count == 0)
            {
                return;
            }
            started = true;
            // The level starts in the dwell of the start station (visit 0), already facing its direction.
            EnqueueVisit(startStation, 0, false);
            EnqueueDeparture(startStation, 0);
        }

        /// <summary>
        /// Pops the next action, executing zero duration markers on the way. At the end of a step
        /// (<paramref name="atStepStart"/> false) the resume after a carry waits for the next step, so the mode
        /// is still Carrying on the step the put down ends.
        /// </summary>
        private void DrainInstantActions(bool atStepStart)
        {
            while (true)
            {
                if (!hasCurrent)
                {
                    if (queue.Count == 0)
                    {
                        if (!CycleActive)
                        {
                            return;
                        }
                        // Refill: every station chunk ends with the walk to the next station, the one of the visit
                        // after the last dwell (M5: the pattern's order, CONTRACT_M5 16.7).
                        int visit = dwellVisit + 1;
                        int next = StationOfVisit(visit);
                        EnqueueVisit(next, visit, true);
                        EnqueueDeparture(next, visit);
                    }
                    current = queue[0];
                    queue.RemoveAt(0);
                    hasCurrent = true;
                    elapsed = 0f;
                    if (current.Goal >= 0)
                    {
                        SetGoal(current.Goal, current.Visit);
                    }
                    PrepareTurn(ref current);
                }
                switch (current.Kind)
                {
                    case Kind.DwellStart:
                    {
                        StationIndex = current.Station;
                        dwellVisit = current.Visit;
                        InDwell = true;
                        if (stations[current.Station].Sleep)
                        {
                            // M5: a sleep station closes the eye for the whole dwell (CONTRACT_M5_v3 4).
                            Asleep = true;
                            wakePending = false;
                        }
                        bool replay = skipNextLoopCount;
                        skipNextLoopCount = false;
                        if (current.Station == startStation)
                        {
                            // The level starts inside the start dwell: that one opens the first loop, it does not close it.
                            if (initialDwellSeen && !replay)
                            {
                                LoopsCompleted++;
                            }
                            initialDwellSeen = true;
                        }
                        hasCurrent = false;
                        continue;
                    }
                    case Kind.DwellEnd:
                        InDwell = false;
                        // The next visit to a sit station is a new approach.
                        sitResolved = false;
                        seatRefused = false;
                        if (Asleep)
                        {
                            // M5: the wake telegraph that ends a sleep dwell is over; the eye opens on the next step.
                            wakePending = true;
                        }
                        hasCurrent = false;
                        continue;
                    case Kind.PratfallLook:
                        // CONTRACT_M4 section 3: after the pratfall, an Alerted look at the empty seat, then resume.
                        hasCurrent = false;
                        BeginLook(SeatHome.Position);
                        continue;
                    case Kind.Reached:
                        ReachedTarget = true;
                        hasCurrent = false;
                        continue;
                    case Kind.EndAlert:
                        hasCurrent = false;
                        RestoreAlertPlan();
                        continue;
                    case Kind.EndInvestigation:
                        if (!atStepStart)
                        {
                            return;
                        }
                        hasCurrent = false;
                        ResumeAfterInvestigation();
                        continue;
                }
                if (IsTurn(current.Kind) && current.Phase == PhaseStart && TurnDone(current))
                {
                    // A turn with nothing left to turn takes no step.
                    hasCurrent = false;
                    continue;
                }
                if (current.Kind == Kind.StandUp && !lowered)
                {
                    // Already standing: nothing to rise.
                    hasCurrent = false;
                    continue;
                }
                return;
            }
        }

        private bool Run(ref Action a, float dt)
        {
            switch (a.Kind)
            {
                case Kind.Walk:
                {
                    LastActivity = a.Activity;
                    Position = Vector3.MoveTowards(Position, a.Target, a.Value * dt);
                    bool arrived = (Position - a.Target).sqrMagnitude < 1e-8f;
                    if (arrived)
                    {
                        Position = a.Target;
                    }
                    if (a.ReachStop && WithinReach())
                    {
                        // Close enough: the rest of the path is dropped, the inhabitant faces the target.
                        while (queue.Count > 0 && queue[0].Kind != Kind.FaceTarget)
                        {
                            queue.RemoveAt(0);
                        }
                        return true;
                    }
                    return arrived;
                }
                case Kind.Telegraph:
                {
                    if (elapsed == 0f)
                    {
                        TelegraphCount++;
                    }
                    LastActivity = RoutineActivity.Telegraph;
                    elapsed += dt;
                    return elapsed >= a.Value - 1e-4f;
                }
                case Kind.Wait:
                    return RunWait(ref a, dt);
                case Kind.SitDown:
                    return RunSitDown(ref a, dt);
                case Kind.Fall:
                    return RunFall(ref a, dt);
                case Kind.StandUp:
                    return RunStandUp(ref a, dt);
                case Kind.SwitchOn:
                {
                    LastActivity = RoutineActivity.SwitchingOn;
                    elapsed += dt;
                    if (elapsed >= a.Value - 1e-4f)
                    {
                        JustSwitchedOn = true;
                        return true;
                    }
                    return false;
                }
                case Kind.PutAway:
                {
                    // M5: bent over the clue, as for a pick up; nothing is carried.
                    LastActivity = RoutineActivity.PickingUp;
                    elapsed += dt;
                    if (elapsed >= a.Value - 1e-4f)
                    {
                        JustPutAway = true; // MUTATION:PUT_AWAY
                        return true;
                    }
                    return false;
                }
                case Kind.Look:
                {
                    LastActivity = RoutineActivity.Looking;
                    elapsed += dt;
                    return elapsed >= a.Value - 1e-4f;
                }
                case Kind.PickUp:
                {
                    if (elapsed == 0f)
                    {
                        JustPickedUp = true;
                    }
                    LastActivity = RoutineActivity.PickingUp;
                    elapsed += dt;
                    return elapsed >= a.Value - 1e-4f;
                }
                case Kind.PutDown:
                {
                    LastActivity = RoutineActivity.PuttingDown;
                    elapsed += dt;
                    if (elapsed >= a.Value - 1e-4f)
                    {
                        IsCarrying = false;
                        JustPutDown = true;
                        return true;
                    }
                    return false;
                }
                case Kind.HoldPin:
                    LastActivity = RoutineActivity.Pinned;
                    return false;
                case Kind.TurnBody:
                case Kind.TurnHead:
                case Kind.TurnBoth:
                case Kind.TurnLook:
                case Kind.FaceTarget:
                    return RunTurn(ref a, dt);
                default:
                    return true;
            }
        }

        // ----- Sitting (docs/CONTRACT_M4.md section 3, amendment 9.2) -----

        private static bool IsSitStation(StationDef s)
        {
            return s != null && !string.IsNullOrEmpty(s.Sit);
        }

        private static bool IsPlayerSeat(StationDef s)
        {
            return s != null && s.Sit == PlayerSeat;
        }

        /// <summary>
        /// The seat home of a sit station: its <see cref="StationDef.Seat"/> for the player, the prop center
        /// (<see cref="StationDef.PropSeat"/>, resolved by LevelDef.ResolveSeats) for a prop, else the station pose.
        /// </summary>
        private static FurniturePose SeatPoseOf(StationDef s)
        {
            if (IsPlayerSeat(s) && s.Seat != null)
            {
                return new FurniturePose(new Vector3(s.Seat.X, 0f, s.Seat.Z), s.Seat.Yaw);
            }
            if (s.PropSeat.HasValue)
            {
                return s.PropSeat.Value;
            }
            return new FurniturePose(YawMath.Planar(s.Position), s.Facing);
        }

        /// <summary>
        /// Records the station the routine is heading to, and the visit it belongs to (M5); a sit station also gives the
        /// seat home.
        /// </summary>
        private void SetGoal(int index, int visit)
        {
            goalStation = index;
            goalVisit = visit;
            if (started && visit != seatDecidedVisit && index >= 0 && index < stations.Count)
            {
                // The walk to a new visit starts now.
                DecideSeat(index, visit);
            }
            if (index >= 0 && index < stations.Count && IsSitStation(stations[index]))
            {
                SeatHome = SeatPoseOf(stations[index]);
            }
        }

        /// <summary>
        /// The first step of a sit down is the moment of sitting. A prop is always there; the player seat is checked
        /// through <see cref="SeatOccupied"/> (null means occupied). An empty player seat turns this action into the
        /// pratfall and replaces the rest of the dwell.
        /// </summary>
        private bool RunSitDown(ref Action a, float dt)
        {
            if (elapsed == 0f)
            {
                if (TakenByRival(stations[Mathf.Clamp(a.Station, 0, stations.Count - 1)]))
                {
                    // M5: someone else sat there after this visit was planned (during the back turn): the rest of
                    // the dwell is standing.
                    RefuseSeat(ref a);
                    return RunWait(ref a, dt);
                }
                if (!SitNow(ref a))
                {
                    return RunFall(ref a, dt);
                }
            }
            LastActivity = RoutineActivity.Sitting;
            elapsed += dt;
            if (elapsed >= a.Value - 1e-4f)
            {
                EyeHeight = Tuning.SitEyeHeight;
                Position = YawMath.Planar(SeatHome.Position);
                return true;
            }
            SlideDown(elapsed / a.Value);
            return false;
        }

        /// <summary>
        /// CONTRACT_M4 10.2: the body and the eye go down together. At <paramref name="t"/> (0 to 1) of the sit down,
        /// the eye is that far from <see cref="Tuning.EyeHeight"/> to <see cref="Tuning.SitEyeHeight"/> and the body
        /// that far from the stand point to the seat home: the rule eye never jumps.
        /// </summary>
        private void SlideDown(float t)
        {
            t = Mathf.Clamp01(t);
            EyeHeight = Mathf.Lerp(StandingEye, Tuning.SitEyeHeight, t);
            Position = Vector3.Lerp(standPoint, YawMath.Planar(SeatHome.Position), t);
        }

        /// <summary>The moment of sitting. Returns false for a pratfall (the action has become the fall).</summary>
        private bool SitNow(ref Action a)
        {
            StationDef s = stations[Mathf.Clamp(a.Station, 0, stations.Count - 1)];
            SeatHome = SeatPoseOf(s);
            standPoint = Position;
            lowered = true;
            sitResolved = true;
            JustSat = true;
            // No jump (CONTRACT_M4 10.2): the sit down (or the fall) slides the body to the seat home.
            bool onPlayer = IsPlayerSeat(s);
            if (onPlayer && !(SeatOccupied?.Invoke() ?? true))
            {
                LastSitResult = SitResult.Pratfall;
                // Nothing to sit on: the rest of the dwell is dropped. Fall, stand back up (telegraphed), look at
                // the empty seat, then the plan goes on after the dwell.
                a.Kind = Kind.Fall;
                a.Value = Tuning.PratfallTime;
                while (queue.Count > 0 && queue[0].Kind != Kind.DwellEnd)
                {
                    queue.RemoveAt(0);
                }
                queue.Insert(0, new Action { Kind = Kind.PratfallLook, Goal = a.Goal, Visit = a.Visit });
                queue.Insert(0, new Action { Kind = Kind.StandUp, Value = Tuning.SitEyeRiseTime, Goal = a.Goal, Visit = a.Visit });
                queue.Insert(0, new Action { Kind = Kind.Telegraph, Value = Tuning.TelegraphDuration, Goal = a.Goal, Visit = a.Visit });
                return false;
            }
            LastSitResult = onPlayer ? SitResult.OnPlayer : SitResult.OnProp;
            IsSitting = true;
            SittingOnPlayer = onPlayer;
            // M5 (CONTRACT_M5_v3 15.6): the seat is claimed at the moment of sitting, never by a pratfall.
            if (Seats != null && Seats.TryClaim(s.Sit, SeatOwner))
            {
                heldSeat = s.Sit;
            }
            return true;
        }

        // ----- The seat registry (M5, docs/CONTRACT_M5_v3.md 15.6) -----

        /// <summary>True when the seat of a sit station is held in <see cref="Seats"/> by another inhabitant.</summary>
        private bool TakenByRival(StationDef s)
        {
            if (Seats == null || !IsSitStation(s))
            {
                return false;
            }
            int sitter = Seats.SitterOf(s.Sit);
            return sitter >= 0 && sitter != SeatOwner;
        }

        /// <summary>
        /// The seat was taken between the plan and the moment of sitting: the sit down becomes a plain wait of the same
        /// length, and the stand-up telegraph and stand up at the end of the dwell are dropped. No claim, no
        /// <see cref="JustSat"/>, no lowered eye.
        /// </summary>
        private void RefuseSeat(ref Action a)
        {
            seatRefused = true;
            sitResolved = true;
            a.Kind = Kind.Wait;
            int end = queue.FindIndex(x => x.Kind == Kind.DwellEnd);
            if (end >= 2 && queue[end - 1].Kind == Kind.StandUp && queue[end - 2].Kind == Kind.Telegraph)
            {
                queue.RemoveRange(end - 2, 2);
            }
        }

        /// <summary>Frees the seat this routine holds, if any (the first stand-up step, Pin, Startle).</summary>
        private void ReleaseSeat()
        {
            if (heldSeat != null)
            {
                Seats?.Release(heldSeat, SeatOwner);
                heldSeat = null;
            }
        }

        /// <summary>
        /// The pratfall: the body slides onto the empty seat home and the eye goes down as for sitting, over the
        /// first <see cref="Tuning.SitEyeRiseTime"/> of the fall; the body then stays on the floor there.
        /// </summary>
        private bool RunFall(ref Action a, float dt)
        {
            LastActivity = RoutineActivity.Pratfall;
            elapsed += dt;
            SlideDown(elapsed / Tuning.SitEyeRiseTime);
            return elapsed >= a.Value - 1e-4f;
        }

        /// <summary>
        /// Stand up from wherever the body is: the eye rises to <see cref="Tuning.EyeHeight"/> and the body slides
        /// back to the stand point over <see cref="Tuning.SitEyeRiseTime"/>. Its first step ends the sitting and
        /// releases the pin. Always right after a full telegraph (the dwell plans it, StandUpFirst queues it, and
        /// RestoreAlertPlan puts it back in front of an interrupted stand up).
        /// </summary>
        private bool RunStandUp(ref Action a, float dt)
        {
            if (elapsed == 0f)
            {
                a.From = Position;
                a.FromEye = EyeHeight;
                IsSitting = false;
                SittingOnPlayer = false;
                // M5: the seat is free from the first stand-up step.
                ReleaseSeat();
            }
            LastActivity = RoutineActivity.StandingUp;
            elapsed += dt;
            if (elapsed >= a.Value - 1e-4f)
            {
                EyeHeight = StandingEye;
                Position = standPoint;
                lowered = false;
                return true;
            }
            float t = elapsed / a.Value;
            EyeHeight = Mathf.Lerp(a.FromEye, StandingEye, t);
            Position = Vector3.Lerp(a.From, standPoint, t);
            return false;
        }

        /// <summary>
        /// Back to standing at once (Pin, Startle): no sitting, no pin flag, the seat released, the personality's
        /// standing eye.
        /// </summary>
        private void ResetSitting()
        {
            IsSitting = false;
            SittingOnPlayer = false;
            lowered = false;
            sitResolved = false;
            seatRefused = false;
            ReleaseSeat();
            EyeHeight = StandingEye;
        }

        private bool RunWait(ref Action a, float dt)
        {
            // M4: the waits of a seated dwell read as Sitting.
            LastActivity = IsSitting ? RoutineActivity.Sitting : RoutineActivity.Waiting;
            elapsed += dt;
            return elapsed >= a.Value - 1e-4f;
        }

        // ----- Turns and their telegraph -----

        private static bool IsTurn(Kind k)
        {
            return k == Kind.TurnBody || k == Kind.TurnHead || k == Kind.TurnBoth || k == Kind.TurnLook || k == Kind.FaceTarget;
        }

        /// <summary>Resolves the targets of the turns that aim at something when they start.</summary>
        private void PrepareTurn(ref Action a)
        {
            a.Phase = PhaseStart;
            if (a.Kind == Kind.TurnLook)
            {
                LookTargets(out a.Value, out a.Value2);
            }
            else if (a.Kind == Kind.FaceTarget)
            {
                Vector3 d = YawMath.Planar(a.Target - Position);
                a.Value = d.sqrMagnitude > 1e-6f ? Normalize(YawMath.YawOf(d)) : BodyYaw;
                a.Value2 = 0f;
            }
        }

        /// <summary>Toward the alert source: the head up to its limit, the body for the rest.</summary>
        private void LookTargets(out float body, out float head)
        {
            Vector3 d = YawMath.Planar(AlertSource - Position);
            if (d.sqrMagnitude < 1e-6f)
            {
                body = BodyYaw;
                head = HeadYaw;
                return;
            }
            float relative = Mathf.DeltaAngle(BodyYaw, YawMath.YawOf(d));
            head = Mathf.Clamp(relative, -Tuning.HeadYawLimit, Tuning.HeadYawLimit);
            if (lowered)
            {
                // CONTRACT_M4 section 3: a seated (or fallen) inhabitant looks with the head only.
                body = BodyYaw;
                return;
            }
            float rest = relative - head;
            body = Mathf.Abs(rest) < 1e-4f ? BodyYaw : Normalize(BodyYaw + rest);
        }

        private void TurnRemaining(in Action a, out float body, out float head)
        {
            switch (a.Kind)
            {
                case Kind.TurnBody:
                    body = Mathf.Abs(Mathf.DeltaAngle(BodyYaw, a.Value));
                    head = 0f;
                    return;
                case Kind.TurnHead:
                    body = 0f;
                    head = Mathf.Abs(a.Value - HeadYaw);
                    return;
                default:
                    body = Mathf.Abs(Mathf.DeltaAngle(BodyYaw, a.Value));
                    head = Mathf.Abs(a.Value2 - HeadYaw);
                    return;
            }
        }

        private bool TurnDone(in Action a)
        {
            TurnRemaining(a, out float body, out float head);
            return body < 1e-3f && head < 1e-3f;
        }

        /// <summary>
        /// Whether a turn starting now needs a telegraph first: when it is over the threshold and the steps right
        /// before it are not a full telegraph, or when it extends, without a pause, an untelegraphed turn of the
        /// same component and the two together go over the threshold.
        /// </summary>
        private bool NeedsTelegraphAtStart(float run, bool runTelegraphed, float remaining)
        {
            if (remaining < 1e-3f)
            {
                return false;
            }
            bool fullTelegraphBefore = telegraphStreak >= Tuning.TelegraphDuration - 1e-3f;
            if (remaining > Tuning.TelegraphMinTurn - TurnEpsilon && !fullTelegraphBefore)
            {
                return true;
            }
            return run > 0f && !runTelegraphed && run + remaining > Tuning.TelegraphMinTurn - TurnEpsilon;
        }

        /// <summary>
        /// Whether a turn whose target changed while turning needs a telegraph now. It continues the turn already
        /// running, so only the size of the whole untelegraphed run matters.
        /// </summary>
        private bool NeedsTelegraphWhileTurning(float run, bool runTelegraphed, float remaining)
        {
            if (remaining < 1e-3f)
            {
                return false;
            }
            if (run > 0f)
            {
                return !runTelegraphed && run + remaining > Tuning.TelegraphMinTurn - TurnEpsilon;
            }
            return NeedsTelegraphAtStart(run, runTelegraphed, remaining);
        }

        private bool RunTurn(ref Action a, float dt)
        {
            if (a.Phase == PhaseStart)
            {
                TurnRemaining(a, out float rb, out float rh);
                bool telegraph = NeedsTelegraphAtStart(bodyRun, bodyRunTelegraphed, rb)
                                 || NeedsTelegraphAtStart(headRun, headRunTelegraphed, rh);
                a.Phase = telegraph ? PhaseTelegraph : PhaseTurn;
                elapsed = 0f;
            }
            if (a.Phase == PhaseTelegraph)
            {
                if (elapsed == 0f)
                {
                    TelegraphCount++;
                }
                LastActivity = RoutineActivity.Telegraph;
                elapsed += dt;
                if (elapsed >= Tuning.TelegraphDuration - 1e-4f)
                {
                    a.Phase = PhaseTurn;
                }
                return false;
            }
            switch (a.Kind)
            {
                case Kind.TurnBody:
                {
                    LastActivity = RoutineActivity.TurningBody;
                    BodyYaw = Mathf.MoveTowardsAngle(BodyYaw, a.Value, Tuning.BodyTurnRate * dt);
                    if (Mathf.Abs(Mathf.DeltaAngle(BodyYaw, a.Value)) < 1e-3f)
                    {
                        BodyYaw = Normalize(a.Value);
                        return true;
                    }
                    return false;
                }
                case Kind.TurnHead:
                {
                    LastActivity = RoutineActivity.TurningHead;
                    HeadYaw = Mathf.MoveTowards(HeadYaw, a.Value, Tuning.HeadTurnRate * dt);
                    if (Mathf.Abs(HeadYaw - a.Value) < 1e-3f)
                    {
                        HeadYaw = a.Value;
                        return true;
                    }
                    return false;
                }
                default:
                {
                    // Body and head at the same time (the alert look, its return, the first beat of a walk).
                    float bodyBefore = BodyYaw;
                    bool bodyDone = true;
                    bool headDone = true;
                    if (BodyYaw != a.Value)
                    {
                        BodyYaw = Mathf.MoveTowardsAngle(BodyYaw, a.Value, Tuning.BodyTurnRate * dt);
                        if (Mathf.Abs(Mathf.DeltaAngle(BodyYaw, a.Value)) < 1e-3f)
                        {
                            BodyYaw = a.Value;
                        }
                        else
                        {
                            bodyDone = false;
                        }
                    }
                    if (HeadYaw != a.Value2)
                    {
                        HeadYaw = Mathf.MoveTowards(HeadYaw, a.Value2, Tuning.HeadTurnRate * dt);
                        if (Mathf.Abs(HeadYaw - a.Value2) < 1e-3f)
                        {
                            HeadYaw = a.Value2;
                        }
                        else
                        {
                            headDone = false;
                        }
                    }
                    LastActivity = BodyYaw != bodyBefore ? RoutineActivity.TurningBody : RoutineActivity.TurningHead;
                    return bodyDone && headDone;
                }
            }
        }

        /// <summary>Records the turn runs of this step, exactly as the probe analyzer cuts its turn segments.</summary>
        private void TrackTurns(float bodyBefore, float headBefore, float dt)
        {
            bool fullTelegraphBefore = telegraphStreak >= Tuning.TelegraphDuration - 1e-3f;
            float db = Mathf.Abs(Mathf.DeltaAngle(bodyBefore, BodyYaw));
            if (db >= 1e-3f)
            {
                if (bodyRun <= 0f)
                {
                    bodyRunTelegraphed = fullTelegraphBefore;
                }
                bodyRun += db;
            }
            else
            {
                bodyRun = 0f;
            }
            float dh = Mathf.Abs(Mathf.DeltaAngle(headBefore, HeadYaw));
            if (dh >= 1e-3f)
            {
                if (headRun <= 0f)
                {
                    headRunTelegraphed = fullTelegraphBefore;
                }
                headRun += dh;
            }
            else
            {
                headRun = 0f;
            }
            telegraphStreak = LastActivity == RoutineActivity.Telegraph ? telegraphStreak + dt : 0f;
        }

        private void ResetTurnTracking()
        {
            bodyRun = 0f;
            headRun = 0f;
            bodyRunTelegraphed = false;
            headRunTelegraphed = false;
            telegraphStreak = 0f;
        }

        // ----- Mode transitions -----

        private void ClearPlan()
        {
            queue.Clear();
            hasCurrent = false;
            elapsed = 0f;
            holdLeft = 0f;
        }

        // ----- M6 (docs/CONTRACT_M6.md 2.7): the stop in front of a door the inhabitant opens -----

        private float holdLeft;

        /// <summary>M6: true while a <see cref="Hold"/> keeps the current walk stopped.</summary>
        public bool Holding => holdLeft > 0f;

        /// <summary>M6: the target of the walk in progress (the next corner), or null when the current action is no walk.</summary>
        public Vector3? WalkTarget => hasCurrent && current.Kind == Kind.Walk ? current.Target : (Vector3?)null;

        /// <summary>
        /// M6 (CONTRACT_M6 2.7): fills <paramref name="into"/> with the remaining corners of the walk in progress: the current
        /// walk's target, then the targets of the walks queued right after it (up to the first action that is no walk).
        /// Returns their count, 0 when the current action is no walk.
        /// </summary>
        public int WalkCorners(List<Vector3> into)
        {
            into.Clear();
            if (!hasCurrent || current.Kind != Kind.Walk)
            {
                return 0;
            }
            into.Add(current.Target);
            for (int i = 0; i < queue.Count && queue[i].Kind == Kind.Walk; i++)
            {
                into.Add(queue[i].Target);
            }
            return into.Count;
        }

        /// <summary>
        /// M6 (CONTRACT_M6 2.7): stops the walk in progress for the next round(<paramref name="seconds"/> / dt) steps
        /// (<see cref="RoutineActivity.Waiting"/>, no motion, no turn, every later action delayed by as much), then it walks on
        /// from where it stopped. Refused (nothing changes) unless the current action is a walk and the routine is neither
        /// startled nor frozen. Any new plan (an alert, an investigation, a pin) drops the hold.
        /// </summary>
        public void Hold(float seconds)
        {
            if (seconds > 0f && !IsStartled && !IsFrozen && hasCurrent && current.Kind == Kind.Walk)
            {
                holdLeft = seconds;
            }
        }

        private void CancelEverything()
        {
            mode = InhabitantMode.Routine;
            ReachedTarget = false;
            Running = false;
            IsCarrying = false;
            JustPickedUp = false;
            JustPutDown = false;
            JustPutAway = false;
            savedQueue.Clear();
            savedHasCurrent = false;
            ClearPlan();
            ResetSitting();
            // M5: a reset wakes a sleeper at once.
            Asleep = false;
            wakePending = false;
        }

        /// <summary>The rest of an alert after its look turn: hold, return to the saved pose, resume.</summary>
        private void EnqueueAlertTail()
        {
            Enqueue(new Action { Kind = Kind.Look, Value = Tuning.AlertLookDuration });
            Enqueue(new Action { Kind = Kind.TurnBoth, Value = savedBodyYaw, Value2 = savedHeadYaw });
            Enqueue(new Action { Kind = Kind.EndAlert });
        }

        /// <summary>
        /// A creak while alerted. During a telegraph or a turn it only moves the look target (the telegraph is
        /// not restarted); during the hold it starts a new look turn, telegraphed if over the threshold, and the
        /// hold restarts.
        /// </summary>
        private void RetargetAlert()
        {
            if (!hasCurrent)
            {
                // The look turn is still queued: it aims at the new source when it starts.
                return;
            }
            int phase = PhaseStart;
            float keptElapsed = 0f;
            if (IsTurn(current.Kind))
            {
                phase = current.Phase;
                keptElapsed = elapsed;
            }
            var look = new Action { Kind = Kind.TurnLook, Goal = -1 };
            PrepareTurn(ref look);
            look.Phase = phase;
            current = look;
            elapsed = phase == PhaseTelegraph ? keptElapsed : 0f;
            if (phase == PhaseTurn)
            {
                TurnRemaining(current, out float rb, out float rh);
                if (NeedsTelegraphWhileTurning(bodyRun, bodyRunTelegraphed, rb) || NeedsTelegraphWhileTurning(headRun, headRunTelegraphed, rh))
                {
                    current.Phase = PhaseTelegraph;
                    elapsed = 0f;
                }
            }
            queue.Clear();
            stampGoal = -1;
            EnqueueAlertTail();
        }

        /// <summary>Back to the plan the alert saved, exactly where it stopped.</summary>
        private void RestoreAlertPlan()
        {
            mode = InhabitantMode.Routine;
            queue.Clear();
            queue.AddRange(savedQueue);
            savedQueue.Clear();
            current = savedCurrent;
            hasCurrent = savedHasCurrent;
            elapsed = savedElapsed;
            plannedBodyYaw = savedPlannedBodyYaw;
            plannedHeadYaw = savedPlannedHeadYaw;
            planInitialized = savedPlanInitialized;
            if (hasCurrent)
            {
                if (current.Kind == Kind.Telegraph)
                {
                    // An interrupted telegraph restarts in full.
                    elapsed = 0f;
                }
                else if (IsTurn(current.Kind))
                {
                    // An interrupted turn decides again: a fresh telegraph when more than the threshold is left.
                    current.Phase = PhaseStart;
                    elapsed = 0f;
                }
                else if (current.Kind == Kind.StandUp)
                {
                    // M4: the eye never rises without a full telegraph right before. The stand up goes back to the
                    // queue and rises from wherever the eye is now.
                    queue.Insert(0, current);
                    current = new Action { Kind = Kind.Telegraph, Value = Tuning.TelegraphDuration, Goal = -1 };
                    elapsed = 0f;
                }
            }
        }

        /// <summary>
        /// After a carry or a cancelled investigation: a reactive pin walks back to its pose; otherwise the routine
        /// paths to the station it was dwelling at or walking to, then the arrival turn and a full dwell.
        /// </summary>
        private void ResumeAfterInvestigation()
        {
            mode = InhabitantMode.Routine;
            ReachedTarget = false;
            Running = false;
            ClearPlan();
            stampGoal = -1;
            Vector3 here = StandUpFirst();
            // The station the routine goes back to is a new visit: its sit (if any) happens again.
            sitResolved = false;
            if (IsPinned)
            {
                stampGoal = -1;
                if (!OtherPlanner.TryPlan(here, pinPosition, corners) || corners.Count == 0)
                {
                    Debug.LogWarning($"[InhabitantRoutine] no path back to the pinned pose ({pinPosition.x:0.00}, {pinPosition.z:0.00}): straight line fallback");
                    corners.Clear();
                    corners.Add(pinPosition);
                }
                EnqueuePath(here, WalkSpeed, RoutineActivity.Walking, false);
                Enqueue(new Action { Kind = Kind.TurnBoth, Value = pinBodyYaw, Value2 = pinHeadYaw });
                Enqueue(new Action { Kind = Kind.HoldPin });
                return;
            }
            if (stations.Count == 0)
            {
                return;
            }
            started = true;
            // M5 (CONTRACT_M5 16.7): back to the station already drawn for the current visit; the visit index does not
            // move. The walk back is not a station walk: it plans with the investigate planner (CONTRACT_M5_v3 15.1).
            int s = Mathf.Clamp(goalStation, 0, stations.Count - 1);
            int visit = goalVisit;
            stampGoal = s;
            stampVisit = visit;
            // The walk back starts now: the seat (if any) is decided again.
            DecideSeat(s, visit);
            PlanWalk(OtherPlanner, here, stations[s].Position, s, corners);
            EnqueuePath(here, WalkSpeed, RoutineActivity.Walking, false);
            EnqueueVisit(s, visit, true);
            EnqueueDeparture(s, visit);
        }

        private bool WithinReach()
        {
            return WithinReachFrom(Position);
        }

        private bool WithinReachFrom(Vector3 point)
        {
            return YawMath.Planar(point - investigateTarget).magnitude <= Tuning.InvestigateReach;
        }

        /// <summary>Yaw of the last segment of the path to <paramref name="home"/> (CONTRACT_M2 3.4, carry goal).</summary>
        private float ApproachYaw(Vector3 from, Vector3 home)
        {
            Vector3 d = Vector3.zero;
            if (OtherPlanner.TryPlan(from, home, corners) && corners.Count > 0)
            {
                Vector3 previous = corners.Count >= 2 ? corners[corners.Count - 2] : from;
                d = YawMath.Planar(corners[corners.Count - 1] - previous);
            }
            if (d.sqrMagnitude <= 1e-6f)
            {
                d = YawMath.Planar(home - from);
            }
            return d.sqrMagnitude > 1e-6f ? YawMath.YawOf(d) : BodyYaw;
        }

        // ----- Planning. Each Enqueue* call knows the pose the previous actions will leave. -----

        private float plannedBodyYaw;
        private float plannedHeadYaw;
        private bool planInitialized;

        private void Enqueue(Action a)
        {
            a.Goal = stampGoal;
            a.Visit = stampVisit;
            queue.Add(a);
        }

        private void EnsurePlan()
        {
            if (!planInitialized)
            {
                plannedBodyYaw = BodyYaw;
                plannedHeadYaw = HeadYaw;
                planInitialized = true;
            }
        }

        /// <summary>
        /// The visit <paramref name="visit"/> of station <paramref name="index"/>: the arrival turn (when
        /// <paramref name="arrival"/>), then the dwell. M5 (CONTRACT_M5_v3 15.6): a sit station whose seat another
        /// inhabitant holds in <see cref="Seats"/> right now is a plain standing dwell, with no back turn, no lowered eye
        /// and no stand-up telegraph.
        /// </summary>
        private void EnqueueVisit(int index, int visit, bool arrival)
        {
            EnsurePlan();
            stampGoal = index;
            stampVisit = visit;
            StationDef s = stations[index];
            if (seatDecidedVisit != visit)
            {
                DecideSeat(index, visit);
            }
            bool sitStation = CanSit && IsSitStation(s);
            // Taken at the start of the walk here, or taken now, on arrival.
            bool taken = sitStation && (seatRefused || TakenByRival(s));
            seatRefused = taken;
            if (arrival && !taken)
            {
                EnqueueBodyTurn(s.Facing);
            }
            EnqueueDwell(index, sitStation && !taken);
        }

        /// <summary>
        /// M5 (CONTRACT_M5_v3 15.6): at the start of the walk to a sit station (or of the walk back to it on a resume),
        /// a seat held by someone else makes that visit a standing dwell, and no seat ghost shows for it.
        /// </summary>
        private void DecideSeat(int index, int visit)
        {
            seatDecidedVisit = visit;
            StationDef s = stations[index];
            seatRefused = CanSit && IsSitStation(s) && TakenByRival(s);
        }

        /// <summary>
        /// The dwell of station <paramref name="index"/>: sit down when <paramref name="sit"/>, the glances, the rest of
        /// the dwell, then the stand up (telegraphed). M5: a sleep station ends with the
        /// <see cref="Tuning.WakeTelegraph"/> beat, eye still closed (CONTRACT_M5_v3 15.5).
        /// </summary>
        private void EnqueueDwell(int index, bool sit)
        {
            StationDef s = stations[index];
            Enqueue(new Action { Kind = Kind.DwellStart, Station = index });
            if (sit)
            {
                Enqueue(new Action { Kind = Kind.SitDown, Station = index, Value = Tuning.SitEyeRiseTime });
            }
            float t = 0f;
            foreach (GlanceDef g in s.Glances)
            {
                if (g.Offset > t + 1e-4f)
                {
                    Enqueue(new Action { Kind = Kind.Wait, Value = g.Offset - t });
                    t = g.Offset;
                }
                t += EnqueueHeadTurn(Mathf.Clamp(g.Yaw, -Tuning.HeadYawLimit, Tuning.HeadYawLimit));
                if (g.Hold > 1e-4f)
                {
                    Enqueue(new Action { Kind = Kind.Wait, Value = g.Hold });
                    t += g.Hold;
                }
                t += EnqueueHeadTurn(0f);
            }
            if (s.Dwell > t + 1e-4f)
            {
                Enqueue(new Action { Kind = Kind.Wait, Value = s.Dwell - t });
            }
            if (sit)
            {
                // Standing up is telegraphed (0.6 s), then the eye rises.
                Enqueue(new Action { Kind = Kind.Telegraph, Value = Tuning.TelegraphDuration });
                Enqueue(new Action { Kind = Kind.StandUp, Value = Tuning.SitEyeRiseTime });
            }
            if (s.Sleep)
            {
                // Waking: a full beat with the eye still closed, before the departure and its own telegraph.
                Enqueue(new Action { Kind = Kind.Telegraph, Value = Tuning.WakeTelegraph }); // MUTATION:WAKE
            }
            Enqueue(new Action { Kind = Kind.DwellEnd, Station = index });
        }

        /// <summary>
        /// The walk from station <paramref name="index"/> (visit <paramref name="visit"/>) to the station of the next
        /// visit, along its frozen corners: one turn per corner (telegraphed when over the threshold), then the segment.
        /// With StraightPlanner and a loop this is the M1 straight walk, action for action.
        /// </summary>
        private void EnqueueDeparture(int index, int visit)
        {
            EnsurePlan();
            int nextVisit = visit + 1;
            int next = StationOfVisit(nextVisit);
            stampGoal = next;
            stampVisit = nextVisit;
            Vector3 previous = stations[index].Position;
            float speed = WalkSpeed;
            foreach (Vector3 corner in StationWalk(index, next))
            {
                Vector3 d = corner - previous;
                if (d.sqrMagnitude > 1e-6f)
                {
                    EnqueueBodyTurn(YawMath.YawOf(d));
                    Enqueue(new Action { Kind = Kind.Walk, Target = corner, Value = speed, Activity = RoutineActivity.Walking });
                    previous = corner;
                }
            }
        }

        /// <summary>
        /// The frozen walk from station <paramref name="from"/> to station <paramref name="to"/> (CONTRACT_M5_v3 15.1):
        /// planned once per ordered pair with the station planner, then reused for the life of the routine. Neither
        /// <see cref="InvestigatePlanner"/> nor an opened door ever changes it.
        /// </summary>
        private Vector3[] StationWalk(int from, int to)
        {
            int key = from * stations.Count + to;
            if (!stationWalks.TryGetValue(key, out Vector3[] walk))
            {
                PlanWalk(StationPlanner, stations[from].Position, stations[to].Position, to, corners);
                walk = corners.ToArray();
                stationWalks[key] = walk;
            }
            return walk;
        }

        /// <summary>
        /// Plans every station walk the pattern can produce (<see cref="RoutinePatterns.ReachablePairs"/>), so they are
        /// all frozen before the first step (CONTRACT_M5 3, CONTRACT_M5_v3 15.1). RoutineFactory calls it once the
        /// pattern is set. Without it, each walk is frozen the first time it is walked, with the same station planner.
        /// </summary>
        public void FreezeStationWalks()
        {
            foreach (Vector2Int pair in RoutinePatterns.ReachablePairs(pattern, stations.Count))
            {
                StationWalk(pair.x, pair.y);
            }
        }

        /// <summary>The number of station walks planned so far (each ordered pair once).</summary>
        public int FrozenWalkCount => stationWalks.Count;

        /// <summary>
        /// Fills <paramref name="into"/> with a walk to station <paramref name="station"/> planned by
        /// <paramref name="with"/>; without a path, a straight line and one error.
        /// </summary>
        private static void PlanWalk(IPathPlanner with, Vector3 from, Vector3 to, int station, List<Vector3> into)
        {
            if (with.TryPlan(from, to, into))
            {
                if (into.Count == 0)
                {
                    into.Add(YawMath.Planar(to));
                }
                for (int i = 0; i < into.Count; i++)
                {
                    into[i] = YawMath.Planar(into[i]);
                }
                return;
            }
            Debug.LogError($"[InhabitantRoutine] no path from ({from.x:0.00}, {from.z:0.00}) to station {station} ({to.x:0.00}, {to.z:0.00}): straight line fallback");
            into.Clear();
            into.Add(YawMath.Planar(to));
        }

        /// <summary>
        /// A walk outside the station cycle (investigation, carry, return to a station or to a pin) along
        /// <see cref="corners"/>. Every turn also brings the head back to 0 and decides its own telegraph when it
        /// starts, so the first beat of the walk is also the one where the head comes back.
        /// </summary>
        private void EnqueuePath(Vector3 from, float speed, RoutineActivity activity, bool reachStop)
        {
            Vector3 previous = YawMath.Planar(from);
            float yaw = BodyYaw;
            bool turned = false;
            foreach (Vector3 raw in corners)
            {
                Vector3 corner = YawMath.Planar(raw);
                Vector3 d = corner - previous;
                if (d.sqrMagnitude <= 1e-6f)
                {
                    continue;
                }
                yaw = Normalize(YawMath.YawOf(d));
                Enqueue(new Action { Kind = Kind.TurnBoth, Value = yaw, Value2 = 0f });
                Enqueue(new Action { Kind = Kind.Walk, Target = corner, Value = speed, Activity = activity, ReachStop = reachStop });
                previous = corner;
                turned = true;
            }
            if (!turned)
            {
                // Nowhere to walk: still bring the head back to 0.
                Enqueue(new Action { Kind = Kind.TurnBoth, Value = BodyYaw, Value2 = 0f });
            }
            plannedBodyYaw = yaw;
            plannedHeadYaw = 0f;
            planInitialized = true;
        }

        /// <summary>Queues a telegraph when the turn exceeds the threshold, then the turn. Returns the planned duration.</summary>
        private float EnqueueBodyTurn(float targetYaw)
        {
            float delta = Mathf.Abs(Mathf.DeltaAngle(plannedBodyYaw, targetYaw));
            float duration = 0f;
            if (delta > Tuning.TelegraphMinTurn)
            {
                Enqueue(new Action { Kind = Kind.Telegraph, Value = Tuning.TelegraphDuration });
                duration += Tuning.TelegraphDuration;
            }
            if (delta > 1e-3f)
            {
                Enqueue(new Action { Kind = Kind.TurnBody, Value = Normalize(targetYaw) });
                duration += delta / Tuning.BodyTurnRate;
            }
            plannedBodyYaw = Normalize(targetYaw);
            return duration;
        }

        private float EnqueueHeadTurn(float targetYaw)
        {
            float delta = Mathf.Abs(targetYaw - plannedHeadYaw);
            float duration = 0f;
            if (delta > Tuning.TelegraphMinTurn)
            {
                Enqueue(new Action { Kind = Kind.Telegraph, Value = Tuning.TelegraphDuration });
                duration += Tuning.TelegraphDuration;
            }
            if (delta > 1e-3f)
            {
                Enqueue(new Action { Kind = Kind.TurnHead, Value = targetYaw });
                duration += delta / Tuning.HeadTurnRate;
            }
            plannedHeadYaw = targetYaw;
            return duration;
        }

        private static float Normalize(float yaw)
        {
            return Mathf.Repeat(yaw + 180f, 360f) - 180f;
        }
    }
}
