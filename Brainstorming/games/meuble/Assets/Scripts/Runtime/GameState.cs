using System;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    public enum PlayState
    {
        Playing,
        Caught,
        Won,
    }

    public enum LoseReason
    {
        None,
        SeenMoving,
        Suspicion,
    }

    /// <summary>
    /// Owns the level and every rule (PRD 4, 6.2; docs/CONTRACT_M2.md 3). One FixedUpdate drives every
    /// gameplay system in the fixed order of contract 3.6, so a fixed step is a single, deterministic unit:
    /// 1 furniture, 2 inhabitants, 3 vision of the player furniture, 4 win then the caught rule, 5 memory and
    /// suspicion, 6 investigations and the carry, 7 noise (hops, then the creak gauge), 8 suspicion decay,
    /// 9 HUD, then <see cref="FixedStepped"/>. The rule switches (<see cref="Rules"/>) are read on every step.
    ///
    /// M4 (docs/CONTRACT_M4.md 2, 3 and amendments 9.1 to 9.3, 9.8, 9.9), in the same order: 1 the furniture reads
    /// <see cref="Rules"/> and its body; 2 every routine gets its seat hook and the body's carry distance before it
    /// steps; 5 a sitting is resolved first (on the player: the furniture snaps to the seat home and is pinned, and every
    /// player slot becomes that pose; on nothing: a pratfall, one discovery), then a tipped stool is observed lying
    /// down; 6 an inhabitant in Routine who sees the switched-off lamp comes to switch it on; 7 the topple, the click
    /// and the roll are noise events (the roll is silent on a silent floor) and the creak gauge pauses while the
    /// furniture is pinned; 9 the body's hints, the sat-on line and the seat ghost of a sit-on-player approach.
    ///
    /// M5 wave 5A (docs/CONTRACT_M5.md 3 and 16; CONTRACT_M5_v3.md 3, 4 and 15.1 to 15.6), in the same order:
    /// 1 the furniture (E in reach of a closed leaf goes to the door through <see cref="FurnitureController.ActionKeyClaimed"/>:
    /// a 0.6 s external action, the leaf's swing begins), then every swinging leaf steps once (the press step is the
    /// swing's first step, so the leaf reaches its open angle on the action's 30th step, sampled on all 30, and the swing
    /// ends at the start of the next step); 2 inhabitants, built by the level builder through
    /// RoutineFactory with the level's one seat registry, their frozen station walks and an investigate planner on the
    /// current door mask (GameState never replaces any of them); 3 vision with each watcher's own range, angle and eye
    /// (asleep: nothing), plus the samples of a swinging leaf; 4 win (only watchers that count for the exit), the caught
    /// rule (only watchers that count for the catch: never the dog; a swinging leaf they see is the furniture seen
    /// moving), then each dog's bark accumulator (seen moving by the awake dog for the grace: a bark, then 3 s of
    /// cooldown with the accumulator held at 0; gated by Rules.Hearing); 5 memory and suspicion with each personality's
    /// tolerance and gain, never for the dog; 6 investigations, carries and the lamp, never by the dog; 7 noise, heard
    /// through each listener's hearing factor (the dog hears nothing), the bark at the dog retargeting like a creak;
    /// 9 the HUD eye (Alarm, then Calm when a human sees, then Dog when only the dog sees, then Closed) and the door hint.
    ///
    /// M5 wave 5B (docs/CONTRACT_M5.md 4, 5, 6, 16.5, 16.8, 16.9 and 18), in the same order: 1 the furniture steps (a shove
    /// is its own push action, begun by a robot contact on an earlier step: it slides RobotPushDistance over RobotPushTime
    /// along the robot's heading, input ignored, moving through the action like any other; <see cref="Shoving"/> reads it
    /// after the step), then the rocking chair's rock when it comes to rest (an external action of RockTime, RockCarefulTime
    /// when careful; never inside an action, a pin or a carry), then the load's kinematic rule (<see cref="Load"/>, a
    /// <see cref="LoadBalance"/> fed with the furniture's planar velocity of the step; its fall drops a clue on the floor);
    /// 2 after the inhabitants, every robot steps along its fixed timeline, and a robot whose disc begins to overlap the
    /// furniture's footprint shoves it (<c>furniture.BeginPush</c>, from the next step: refused while pinned, carried, lying
    /// or in an action) and reverses either way; 3 with a load the sample box is Tuning.LoadHeight taller; 4 the furniture is
    /// moving by its own predicate only (a push step is moving through its action); 5 a watcher with memory that sees the clue costs
    /// one discovery and is sent to put it away (<see cref="InhabitantRoutine.BeginPutAway"/>); 6 the clue goes on the step
    /// it is put away (<see cref="InhabitantRoutine.JustPutAway"/>); 7 every noise goes through the robot's hum
    /// (<see cref="Hearing.IsMasked"/>: hops, rolls and clicks within RobotHumRadius of a robot are not emitted), and the
    /// fall is a Crash at the clue; 9 the balance gauge.
    ///
    /// The dog's hold (docs/CONTRACT_M5.md 20): in step 6, after the carry, a dog that barked runs to the furniture, pins
    /// it next to it (step 5 keeps the pin with a sitter's) and barks at it, and the nearest free human comes to put it
    /// back as after a discovery (<see cref="StepDogHold"/>); 9 the hold line and the bark loop.
    /// </summary>
    public sealed class GameState : MonoBehaviour
    {
        public string LevelId = "level1";
        public Hud Hud;
        public Sfx Sfx;
        public OrbitCamera Camera;

        /// <summary>M2.1: the ghost of the remembered pose (built by Main, kept across levels).</summary>
        public GhostView Ghost;

        /// <summary>M3: the title and pause menus (built by Main). Without it, a pause press only toggles Paused.</summary>
        public Menu Menu;

        public PlayState State { get; private set; } = PlayState.Playing;
        public LevelInstance Level { get; private set; }
        public LevelDef Def { get; private set; }
        public CaughtRule Rule { get; } = new CaughtRule();

        /// <summary>Simulated time since the level started, in fixed steps (the win time).</summary>
        public float Elapsed { get; private set; }

        /// <summary>Number of fixed steps simulated since the level started.</summary>
        public int Steps { get; private set; }

        /// <summary>
        /// The furniture's own samples are seen by a watcher that counts for the catch (every inhabitant of M1 to M4; since
        /// M5 never the dog, see <see cref="SeenByDog"/>).
        /// </summary>
        public bool Seen { get; private set; }
        public float SeenMoving => Rule.SeenMoving;
        public int Restarts { get; private set; }

        public event Action<PlayState> StateChanged;

        // ----- M2 (docs/CONTRACT_M2.md 5) -----

        /// <summary>
        /// Rule switches, read on every fixed step (3.7). Defaults to M4 (docs/CONTRACT_M4.md 6): the M1 probe keeps
        /// M1 and the M2 probe keeps M2 by setting their own.
        /// </summary>
        public GameRules Rules = GameRules.M4;
        public LoseReason LoseReason { get; private set; }

        /// <summary>Highest suspicion across the inhabitants (the HUD bar).</summary>
        public float MaxSuspicion { get; private set; }
        public CreakGauge Creak { get; } = new CreakGauge();

        /// <summary>Every noise event emitted (hops on a hard floor, creaks), before it reaches the inhabitants.</summary>
        public event Action<NoiseEvent> Noise;

        /// <summary>The play order of levels.json (a single level when the file is missing).</summary>
        public IReadOnlyList<string> LevelOrder => Manifest;

        /// <summary>The level after the current one in levels.json, or null.</summary>
        public string NextLevelId
        {
            get
            {
                List<string> order = Manifest;
                int i = order.IndexOf(LevelId);
                return i >= 0 && i + 1 < order.Count ? order[i + 1] : null;
            }
        }

        public bool HasNextLevel => NextLevelId != null;

        /// <summary>M3: the current level is the last entry of levels.json (its win shows the end screen).</summary>
        public bool IsLastLevel
        {
            get
            {
                List<string> order = Manifest;
                return order.Count > 0 && order[order.Count - 1] == LevelId;
            }
        }

        /// <summary>M3: the first entry of levels.json, where the title screen and Play start.</summary>
        public string FirstLevelId
        {
            get
            {
                List<string> order = Manifest;
                return order.Count > 0 ? order[0] : LevelId;
            }
        }

        // Statistics since the level started (probe, tests, designer route replay).
        public int DiscoveryCount { get; private set; }
        public int AlertCount { get; private set; }
        public int CreakCount { get; private set; }
        public int CarryCount { get; private set; }

        /// <summary>Fixed steps on which an inhabitant saw the player chair and a decoy explained it.</summary>
        public int ExplainedByDecoySteps { get; private set; }

        /// <summary>The inhabitant who carries (or is about to carry) the furniture, or null.</summary>
        public Inhabitant Carrier => carrier >= 0 && Level != null && carrier < Level.Inhabitants.Count ? Level.Inhabitants[carrier] : null;

        /// <summary>The inhabitant whose suspicion reached 1 (lose reason Suspicion), or null.</summary>
        public Inhabitant LostTo { get; private set; }

        /// <summary>True on the fixed step a creak fired (tests).</summary>
        public bool CreakedThisStep { get; private set; }

        /// <summary>Investigations given up because the inhabitant could not reach the chair (no path).</summary>
        public int GiveUpCount { get; private set; }

        /// <summary>M2.1: the HUD eye state of the last step (closed, calm, alarm).</summary>
        public HudEye EyeState { get; private set; }

        /// <summary>
        /// M2.1: the inhabitant who last saw the chair (an observing sighting), whose remembered pose the ghost
        /// shows. The first inhabitant until anyone has seen it (every slot starts at the spawn).
        /// </summary>
        public Inhabitant LastSeer => Level != null && Level.Inhabitants.Count > 0
            ? Level.Inhabitants[Mathf.Clamp(lastSeer, 0, Level.Inhabitants.Count - 1)]
            : null;

        /// <summary>True when the chair stands more than DisplacementTolerance from the last seer's remembered pose.</summary>
        public bool OutOfPlace { get; private set; }

        /// <summary>M2.2: true when the chair stands within DisplacementTolerance of a decoy of its kind (a safe spot).</summary>
        public bool AtDecoy { get; private set; }

        // ----- M4 (docs/CONTRACT_M4.md 2 and 3), statistics since the level started -----

        /// <summary>Sittings on the player furniture (it was home in time).</summary>
        public int SatOnPlayerCount { get; private set; }

        /// <summary>Sittings on nothing (the seat was not home): each one is also a discovery.</summary>
        public int PratfallCount { get; private set; }

        /// <summary>Times an inhabitant switched the lamp back on.</summary>
        public int SwitchOnCount { get; private set; }

        /// <summary>Topple, click and roll noise events emitted (rugs and soft rooms silence a roll).</summary>
        public int ToppleNoiseCount { get; private set; }
        public int ClickNoiseCount { get; private set; }
        public int RollNoiseCount { get; private set; }

        // ----- M5 probe hooks (docs/CONTRACT_M5.md 16.12). ShoveCount, CrashCount and ClueActive are wave 5B's. -----

        /// <summary>Barks since the level started (CONTRACT_M5_v3 4: the dog saw the furniture moving for the grace).</summary>
        public int BarkCount { get; private set; }

        /// <summary>Wave 5B: robot shoves of the furniture accepted since the level started (CONTRACT_M5 4, 16.8).</summary>
        public int ShoveCount { get; private set; }

        /// <summary>Wave 5B: loads that fell since the level started (CONTRACT_M5 6, 16.5), each a crash and a clue.</summary>
        public int CrashCount { get; private set; }

        /// <summary>Wave 5B: a fallen load's clue lies on the floor, until an inhabitant puts it away.</summary>
        public bool ClueActive { get; private set; }

        // ----- M5 wave 5A (docs/CONTRACT_M5_v3.md 3, 4, 15.2 and 15.5) -----

        /// <summary>An awake dog sees the furniture's samples or a swinging leaf's on this step (the HUD's Dog eye).</summary>
        public bool SeenByDog { get; private set; }

        /// <summary>A watcher that counts for the catch sees a sample of a swinging leaf on this step (seen moving).</summary>
        public bool LeafSeen { get; private set; }

        /// <summary>Doors the player opened since the level started (E in reach, the opening began).</summary>
        public int DoorOpenCount { get; private set; }

        /// <summary>Where the last bark was emitted (planar: at the dog).</summary>
        public Vector3 LastBarkAt { get; private set; }

        /// <summary>The fixed step (<see cref="Steps"/>) of the last bark, -1 before the first one.</summary>
        public int LastBarkStep { get; private set; } = -1;

        /// <summary>The leaf the action key would open now (a closed leaf in reach, the nearest), or null.</summary>
        public DoorLeaf DoorInReach => Level != null ? NearestClosedLeafInReach(Level.Furniture) : null;

        /// <summary>The seconds a dog's bark accumulator has seen the furniture moving (0 during its cooldown).</summary>
        public float DogSeenMoving(Inhabitant dog)
        {
            int i = IndexOf(dog);
            return i >= 0 && i < barkRules.Length ? barkRules[i].SeenMoving : 0f;
        }

        /// <summary>Fixed steps left in a dog's bark cooldown (0 when it may bark).</summary>
        public int BarkCooldownSteps(Inhabitant dog)
        {
            int i = IndexOf(dog);
            return i >= 0 && i < barkCooldowns.Length ? barkCooldowns[i] : 0;
        }

        // ----- CONTRACT_M5 20: the dog's hold -----

        /// <summary>The dog running to the furniture after its bark, or holding it, or null.</summary>
        public Inhabitant HoldingDog => holdDog >= 0 && Level != null && holdDog < Level.Inhabitants.Count ? Level.Inhabitants[holdDog] : null;

        /// <summary>The dog stands next to the furniture and pins it, until a human puts it back.</summary>
        public bool HeldByDog => dogHolding;

        /// <summary>The human the dog's hold sent to put the furniture back, or null.</summary>
        public Inhabitant DogCaller => holdCaller >= 0 && Level != null && holdCaller < Level.Inhabitants.Count ? Level.Inhabitants[holdCaller] : null;

        /// <summary>Since the level started: runs begun after a bark, holds (the dog reached and pinned the furniture), humans
        /// sent by a hold, and the discoveries those humans made on arrival.</summary>
        public int DogRunCount { get; private set; }
        public int DogHoldCount { get; private set; }
        public int DogCallCount { get; private set; }
        public int DogHoldDiscoveryCount { get; private set; }

        /// <summary>The watcher saw a sample of a swinging leaf on the last step (any watcher, the dog included).</summary>
        public bool SeesLeaf(Inhabitant inhabitant)
        {
            int i = IndexOf(inhabitant);
            return i >= 0 && i < seesLeaf.Length && seesLeaf[i];
        }

        // ----- M5 wave 5B (docs/CONTRACT_M5.md 4, 5, 6, 16.5, 16.8 and 16.9): the robot, the rock and the load -----

        /// <summary>The level's robot vacuums (LevelInstance.Robots), stepped by GameState in step 2.</summary>
        public IReadOnlyList<Robot> Robots => robots;

        /// <summary>
        /// The time on the robots' timelines: fixed steps since the level was built, times dt. The robots never wait for the
        /// player (CONTRACT_M5 4: the timeline is fixed), so it is the inhabitants' time, and the audit's.
        /// </summary>
        public float RobotTime { get; private set; }

        /// <summary>Contacts of a robot with the player furniture since the level started: each one reverses the robot.</summary>
        public int RobotContactCount { get; private set; }

        /// <summary>
        /// This fixed step is a step of an accepted shove: the furniture's push action ran in step 1 (read after its step, so
        /// the contact step itself is not one, and the RobotPushTime / dt steps after it are).
        /// </summary>
        public bool Shoving { get; private set; }

        /// <summary>The furniture was moving on the last fixed step as the rules saw it (its own predicate).</summary>
        public bool FurnitureMoving { get; private set; }

        /// <summary>The planar direction of the last accepted shove (unit).</summary>
        public Vector3 LastShoveDirection { get; private set; }

        /// <summary>Noises the robots' hum masked since the level started: hops, rolls and clicks not emitted.</summary>
        public int MaskedNoiseCount { get; private set; }

        /// <summary>A noise the robots' hum masked (it reaches no inhabitant and <see cref="Noise"/> does not see it).</summary>
        public event Action<NoiseEvent> NoiseMasked;

        /// <summary>
        /// The load's rule (CONTRACT_M5 16.5, a kinematic rule like the creak gauge: GameState steps it once per fixed step
        /// with the furniture's planar velocity), null when the level puts no load on the player.
        /// </summary>
        public LoadBalance Load { get; private set; }

        /// <summary>The load's visual on the furniture (its sway, then its clue on the floor), null without a load.</summary>
        public LoadView LoadView { get; private set; }

        /// <summary>The furniture carries a load that has not fallen.</summary>
        public bool CarryingLoad => Load != null && !Load.Fallen;

        /// <summary>The height the furniture's sample box grows by now: Tuning.LoadHeight while it carries a load (16.5).</summary>
        public float LoadExtraHeight => CarryingLoad ? Tuning.LoadHeight : 0f;

        /// <summary>Where the fallen load lies, on the floor (its clue).</summary>
        public Vector3 ClueAt { get; private set; }

        /// <summary>Discoveries a clue cost since the level started (one per fall at most).</summary>
        public int ClueDiscoveryCount { get; private set; }

        /// <summary>Clues an inhabitant put away since the level started.</summary>
        public int PutAwayCount { get; private set; }

        /// <summary>The inhabitant on its way to put the clue away, or null.</summary>
        public Inhabitant ClueFinder => clueFinder >= 0 && Level != null && clueFinder < Level.Inhabitants.Count ? Level.Inhabitants[clueFinder] : null;

        /// <summary>Rocks of the rocking chair since the level started (CONTRACT_M5 5, 16.9).</summary>
        public int RockCount { get; private set; }

        /// <summary>The inhabitant sitting on the player furniture (which is then pinned), or null.</summary>
        public Inhabitant Sitter
        {
            get
            {
                if (Level == null)
                {
                    return null;
                }
                foreach (Inhabitant h in Level.Inhabitants)
                {
                    if (h != null && h.Routine != null && h.Routine.SittingOnPlayer)
                    {
                        return h;
                    }
                }
                return null;
            }
        }

        /// <summary>M4.1: the furniture's visual is still sliding onto the seat home after a sit on the player.</summary>
        public bool SeatSettling
        {
            get
            {
                SeatSettleView settle = Level != null && Level.Furniture != null ? Level.Furniture.GetComponent<SeatSettleView>() : null;
                return settle != null && settle.Active;
            }
        }

        /// <summary>
        /// M4.1 (CONTRACT_M4 10.7): how long the furniture's visual takes to slide onto the seat home (presentation;
        /// wanted in Tuning as SeatSettleTime).
        /// </summary>
        public const float SeatSettleTime = 0.3f;

        /// <summary>The seat home a "sit": "player" inhabitant is walking to (its ghost shows), or null.</summary>
        public FurniturePose? SeatApproach { get; private set; }

        /// <summary>True when an inhabitant in Routine saw the switched-off lamp and is on its way to switch it on.</summary>
        public bool SwitchOnPending(Inhabitant inhabitant)
        {
            int i = IndexOf(inhabitant);
            return i >= 0 && i < switchingOn.Length && switchingOn[i];
        }

        public SuspicionMeter SuspicionOf(Inhabitant inhabitant)
        {
            int i = IndexOf(inhabitant);
            return i >= 0 ? meters[i] : null;
        }

        public FurnitureMemory MemoryOf(Inhabitant inhabitant)
        {
            int i = IndexOf(inhabitant);
            return i >= 0 ? memories[i] : null;
        }

        /// <summary>What the inhabitant's memory made of the player chair on the last step (NotSeen when it did not observe).</summary>
        public Observation LastObservationOf(Inhabitant inhabitant)
        {
            int i = IndexOf(inhabitant);
            return i >= 0 ? observations[i] : Observation.NotSeen;
        }

        /// <summary>Loads a level of Resources/Levels and starts it. The current level stays if the new one fails to load.</summary>
        // ----- M6 gameplay (docs/CONTRACT_M6.md 2.5 to 2.7) -----

        /// <summary>M6: where the player furniture stands with a wardrobe.</summary>
        public enum WardrobeStage
        {
            None,
            /// <summary>The Tuning.WardrobeActionTime entry action (moving), still visible.</summary>
            Entering,
            /// <summary>Hidden inside (FurnitureController.Hidden).</summary>
            Hidden,
            /// <summary>The Tuning.WardrobeActionTime exit action (moving), visible again in front of the wardrobe.</summary>
            Leaving,
        }

        /// <summary>M6: the furniture's wardrobe stage.</summary>
        public WardrobeStage Wardrobe { get; private set; }

        /// <summary>M6: the wardrobe entered (from the entry press to the end of the exit action), or null.</summary>
        public PropDef WardrobeProp { get; private set; }

        /// <summary>M6: the wardrobe the furniture may enter from where it stands now (WardrobeRule.CanEnter), or null.</summary>
        public PropDef WardrobeInReach => Level != null ? WardrobeFor(Level.Furniture) : null;

        /// <summary>M6: entries completed (hidden), and exits begun, since the level started.</summary>
        public int HideCount { get; private set; }
        public int LeaveCount { get; private set; }

        /// <summary>M6: discoveries of a remembered spot seen empty while the furniture was hidden.</summary>
        public int EmptySpotCount { get; private set; }

        /// <summary>M6: door memory Suspects (a leaf seen in another state than remembered), and doors put back.</summary>
        public int DoorSuspectCount { get; private set; }
        public int DoorPutBackCount { get; private set; }

        /// <summary>M6: leaves opened by an inhabitant on its walk (openedByInhabitants).</summary>
        public int HouseholdDoorOpenCount { get; private set; }

        /// <summary>M6: an inhabitant's door memory (null without one: the level's doorMemory off, or no memory).</summary>
        public DoorMemory DoorMemoryOf(Inhabitant inhabitant)
        {
            int i = IndexOf(inhabitant);
            return i >= 0 && i < doorMemories.Length ? doorMemories[i] : null;
        }

        /// <summary>M6: the leaf index an inhabitant is on its way to put back, or -1.</summary>
        public int DoorFixOf(Inhabitant inhabitant)
        {
            int i = IndexOf(inhabitant);
            return i >= 0 && i < doorFixers.Length ? doorFixers[i] : -1;
        }

        private DoorMemory[] doorMemories = new DoorMemory[0];
        private int[] doorFixers = new int[0];
        private int householdLeaves;
        private DoorLeaf householdDoorThisStep;
        private readonly List<PropDef> wardrobes = new List<PropDef>();
        private readonly Vector3[] spotSamples = new Vector3[Tuning.SampleCount];

        /// <summary>M7 (CONTRACT_M7 4.1): the difficulty the current level was built with (Normal before any level).</summary>
        public DifficultyDef Difficulty { get; private set; } = DifficultyDef.For(DifficultyDef.Normal);

        /// <summary>M7: the difficulty id the next level build uses, the saved option (SaveData.options.difficulty).</summary>
        private static string SavedDifficulty()
        {
            return SaveStore.Options.DifficultyId;
        }

        public void LoadLevel(string id)
        {
            LevelDef def = LevelLoader.Load(id);
            TeardownLevel();
            LevelId = id;
            Def = def;
            BuildLevel();
        }

        /// <summary>After a win: the next level of levels.json (Enter). Does nothing on the last level.</summary>
        public void NextLevel()
        {
            string next = NextLevelId;
            if (next != null)
            {
                LoadLevel(next);
                // M8 touch redesign: the win panel freed the mouse cursor for its buttons (Menu.OnWinScreen); back in
                // a level, a player recaptures it (a no-op in the editor, same as every other CaptureCursor call).
                Menu?.CaptureCursor();
            }
        }

        /// <summary>Raised at the end of every fixed step, after every rule ran (the probe records from it).</summary>
        public event Action FixedStepped;

        // A creak warning shows the last CreakWarning seconds of the fill (3.3). M7: of the difficulty's fill time.
        private float WarningStart => Creak.WarningStart;

        private static readonly GameRules NoRules = GameRules.M1;

        private int lastHopCount;
        private int[] lastTelegraphCounts = new int[0];
        private List<string> manifest;

        // Per inhabitant, in the order of Level.Inhabitants.
        private Vision[] visions = new Vision[0];
        private FurnitureMemory[] memories = new FurnitureMemory[0];
        private SuspicionMeter[] meters = new SuspicionMeter[0];
        private Observation[] observations = new Observation[0];
        private bool[] seesPlayer = new bool[0];
        private bool[] resolved = new bool[0];
        private Vector3[] investigateTargets = new Vector3[0];
        private readonly List<FurniturePose> sameKindDecoys = new List<FurniturePose>();
        private int lastSeer;

        // The carry: who carries, since when, and from which pose the pick up lifts the furniture.
        private int carrier = -1;
        private int carrySteps;
        private int putDownSteps;
        private Vector3 carryFrom;
        private float carryFromYaw;

        // Sound cues of the current step.
        private bool hoppedThisStep;
        private bool hopSilent;
        private bool putDownThisStep;

        // M4: the furniture's event counters at the last step, and this step's cues.
        private int lastToppleCount;
        private int lastToggleCount;
        private int lastRollCount;
        private bool toppledThisStep;
        private bool clickedThisStep;
        private bool rolledThisStep;
        // M4.1 (CONTRACT_M4 10.6): the furniture stands on a rug or in a soft room this step: none of its noises is heard.
        private bool floorSilent;
        private bool switchedOnThisStep;
        private int pratfallThisStep = -1;
        private Func<bool>[] seatHooks = new Func<bool>[0];
        // Per inhabitant: on its way to switch the lamp on (GameState called BeginSwitchOn).
        private bool[] switchingOn = new bool[0];

        // M5: per inhabitant, a swinging leaf seen this step; per dog, its bark accumulator and cooldown (fixed steps).
        private bool[] seesLeaf = new bool[0];
        private CaughtRule[] barkRules = new CaughtRule[0];
        private int[] barkCooldowns = new int[0];
        // M5: this step's cues: the dogs that bark (emitted with the noise, step 7) and the leaf whose opening began.
        private readonly List<int> barksThisStep = new List<int>();
        private DoorLeaf doorOpenedThisStep;

        // CONTRACT_M5 20: the dog running to or holding the furniture (-1 when none), where it runs, whether it holds, the
        // human it called (-1), the steps with nobody to call, the steps to the next bark of the hold, this step's bark,
        // and whether a sitter pins the furniture (StepSitting).
        private int holdDog = -1;
        private Vector3 holdTarget;
        private bool dogHolding;
        private int holdCaller = -1;
        private int holdWaitSteps;
        private int holdBarkSteps;
        private bool holdBarkThisStep;
        private bool sitPinned;

        // M5 wave 5B: the robots, their planar positions this step (the hum) and whether each one touched the furniture on the
        // last step (a contact is the first step of an overlap); the fixed steps of the robot timeline.
        private readonly List<Robot> robots = new List<Robot>();
        private readonly List<Vector3> robotPositions = new List<Vector3>();
        private bool[] robotTouching = new bool[0];
        private int robotSteps;
        // The rocking chair: the last step travelled (a rest after it starts a rock).
        private bool rockArmed;
        // The load: its velocities of the last window (the direction of a fall), the clue's state.
        private readonly Queue<Vector2> loadHistory = new Queue<Vector2>();
        private bool clueFound;
        private int clueFinder = -1;
        // This step's 5B cues.
        private bool contactThisStep;
        private Vector3 contactAt;
        private bool crashThisStep;
        private bool rockedThisStep;
        // The time of the rock begun this step (RockTime, or RockCarefulTime): its creak lasts as long.
        private float rockTime;
        private bool hopMasked;
        private bool rollMasked;

        public FurnitureController Furniture => Level?.Furniture;
        public Inhabitant MainInhabitant => Level != null && Level.Inhabitants.Count > 0 ? Level.Inhabitants[0] : null;

        private List<string> Manifest => manifest ??= LevelLoader.LoadManifest(LevelId);

        public void Begin()
        {
            LevelDef def = LevelLoader.Load(LevelId);
            TeardownLevel();
            Def = def;
            BuildLevel();
        }

        /// <summary>PRD 6.2: instant restart, the level is torn down and rebuilt. It keeps the current level.</summary>
        public void Restart()
        {
            if (Def == null)
            {
                Begin();
                return;
            }
            TeardownLevel();
            BuildLevel();
            Restarts++;
            // M8 touch redesign: the fail or win panel may have freed the mouse cursor for its buttons; back in the
            // level, a player recaptures it (a no-op in the editor, same as every other CaptureCursor call).
            Menu?.CaptureCursor();
        }

        private void TeardownLevel()
        {
            if (Level != null)
            {
                LevelBuilder.Teardown(Level);
                Level = null;
            }
            Sfx?.SetTension(false, 0f);
            Sfx?.SetRattle(false, 0f);
        }

        private void BuildLevel()
        {
            // M7 (CONTRACT_M7 4.1): every level is built and played at the saved difficulty, read here on each load and
            // restart (a change in the Options page applies from the next one). RoutineFactory reads Current for the
            // watchers; the grace and the creak are set below; the record of a win goes under this difficulty.
            Difficulty = DifficultyDef.For(SavedDifficulty());
            DifficultyDef.Current = Difficulty;
            Level = LevelBuilder.Build(Def);
            Rule.Reset();
            Rule.Grace = Difficulty.CaughtGrace; // MUTATION:DIFFICULTY_GRACE
            Creak.Reset();
            Creak.FillTime = Difficulty.CreakFillTime;
            State = PlayState.Playing;
            LoseReason = LoseReason.None;
            LostTo = null;
            Elapsed = 0f;
            Steps = 0;
            Seen = false;
            MaxSuspicion = 0f;
            DiscoveryCount = 0;
            AlertCount = 0;
            CreakCount = 0;
            CarryCount = 0;
            ExplainedByDecoySteps = 0;
            CreakedThisStep = false;
            GiveUpCount = 0;
            EyeState = HudEye.Closed;
            OutOfPlace = false;
            AtDecoy = false;
            lastSeer = 0;
            carrier = -1;
            lastHopCount = 0;
            if (Def.Player != null && !string.IsNullOrEmpty(Def.Player.Kind))
            {
                Level.Furniture.Kind = Def.Player.Kind;
            }
            Level.Furniture.CreakTremble = 0f;
            // M4: the furniture is new, its counters start where they stand.
            SatOnPlayerCount = 0;
            PratfallCount = 0;
            SwitchOnCount = 0;
            ToppleNoiseCount = 0;
            ClickNoiseCount = 0;
            RollNoiseCount = 0;
            SeatApproach = null;
            pratfallThisStep = -1;
            // M5: the doors and the dog start afresh with the level.
            BarkCount = 0;
            DoorOpenCount = 0;
            SeenByDog = false;
            LeafSeen = false;
            LastBarkAt = Vector3.zero;
            LastBarkStep = -1;
            barksThisStep.Clear();
            doorOpenedThisStep = null;
            // CONTRACT_M5 20: no hold yet.
            holdDog = -1;
            dogHolding = false;
            holdCaller = -1;
            holdWaitSteps = 0;
            holdBarkSteps = 0;
            holdBarkThisStep = false;
            sitPinned = false;
            DogRunCount = 0;
            DogHoldCount = 0;
            DogCallCount = 0;
            DogHoldDiscoveryCount = 0;
            Level.Furniture.ActionKeyClaimed = ClaimActionKey;
            lastToppleCount = Level.Furniture.ToppleCount;
            lastToggleCount = Level.Furniture.ToggleCount;
            lastRollCount = Level.Furniture.RollCount;
            Level.Furniture.Rules = Rules ?? NoRules;
            // M5 wave 5B: the robots, the rock and the load start afresh with the level.
            ShoveCount = 0;
            CrashCount = 0;
            ClueActive = false;
            RobotContactCount = 0;
            MaskedNoiseCount = 0;
            ClueDiscoveryCount = 0;
            PutAwayCount = 0;
            RockCount = 0;
            Shoving = false;
            FurnitureMoving = false;
            LastShoveDirection = Vector3.zero;
            rockArmed = false;
            clueFound = false;
            clueFinder = -1;
            ClueAt = Vector3.zero;
            contactThisStep = false;
            crashThisStep = false;
            rockedThisStep = false;
            hopMasked = false;
            rollMasked = false;
            BuildRobots();
            BuildLoad();
            // M6: the wardrobe, the door memories and the doors the household opens start afresh with the level.
            Wardrobe = WardrobeStage.None;
            WardrobeProp = null;
            HideCount = 0;
            LeaveCount = 0;
            EmptySpotCount = 0;
            DoorSuspectCount = 0;
            DoorPutBackCount = 0;
            HouseholdDoorOpenCount = 0;
            householdDoorThisStep = null;
            wardrobes.Clear();
            wardrobes.AddRange(Def.Wardrobes());
            householdLeaves = Def.HouseholdLeafMask();

            int n = Level.Inhabitants.Count;
            seatHooks = new Func<bool>[n];
            switchingOn = new bool[n];
            for (int i = 0; i < n; i++)
            {
                int index = i;
                seatHooks[i] = () => PlayerSeatIsHome(index);
            }
            lastTelegraphCounts = new int[n];
            visions = new Vision[n];
            memories = new FurnitureMemory[n];
            meters = new SuspicionMeter[n];
            observations = new Observation[n];
            seesPlayer = new bool[n];
            resolved = new bool[n];
            investigateTargets = new Vector3[n];
            seesLeaf = new bool[n];
            barkRules = new CaughtRule[n];
            barkCooldowns = new int[n];
            for (int i = 0; i < n; i++)
            {
                barkRules[i] = new CaughtRule(Difficulty.CaughtGrace);
            }
            // 3.1: the household knows where its chair belongs (the spawn pose), and every decoy slot is
            // fixed at the decoy pose from level start.
            var decoyPoses = new List<FurniturePose>();
            var decoyKinds = new List<string>();
            foreach (Decoy decoy in Level.Decoys)
            {
                decoyPoses.Add(decoy != null ? decoy.Pose : default);
                decoyKinds.Add(decoy != null ? decoy.Kind : string.Empty);
            }
            sameKindDecoys.Clear();
            var ringCenters = new List<Vector3>();
            for (int d = 0; d < decoyPoses.Count; d++)
            {
                if (string.Equals(decoyKinds[d], Level.Furniture.Kind, StringComparison.OrdinalIgnoreCase))
                {
                    sameKindDecoys.Add(decoyPoses[d]);
                    ringCenters.Add(decoyPoses[d].Position);
                }
            }
            Ghost?.SetDecoyRings(ringCenters);
            var spawn = new FurniturePose(Def.Player.Position, Def.Player.Yaw);
            for (int i = 0; i < n; i++)
            {
                Inhabitant inhabitant = Level.Inhabitants[i];
                visions[i] = Level.Visions.Find(v => v != null && v.Owner == inhabitant);
                // M5 (CONTRACT_M5 3): each memory notices with its personality's tolerance, each meter gains with its factor.
                PersonalityDef p = PersonalityOf(inhabitant);
                memories[i] = new FurnitureMemory(spawn, decoyPoses, decoyKinds, Level.Furniture.Kind, p.Tolerance);
                meters[i] = new SuspicionMeter { GainFactor = p.SuspicionFactor };
            }
            // M6 (CONTRACT_M6 2.6): with the level's doorMemory, each inhabitant with a memory knows the authored leaves.
            doorMemories = new DoorMemory[n];
            doorFixers = new int[n];
            var authored = new List<bool>();
            foreach (DoorLeaf leaf in Level.Leaves)
            {
                authored.Add(leaf != null && leaf.Open);
            }
            for (int i = 0; i < n; i++)
            {
                doorFixers[i] = -1;
                doorMemories[i] = Def.DoorMemory && PersonalityOf(Level.Inhabitants[i]).Memory ? new DoorMemory(authored) : null;
            }
            // M2.1: the ghost shows the first observer's memory until anyone has seen the chair (never the dog's).
            lastSeer = FirstObserver();

            if (Camera != null)
            {
                Level.Furniture.CameraYaw = () => Camera.Yaw;
                Camera.SetTarget(Level.Furniture, Def.Player.Yaw);
            }
            WireRoutines(Rules ?? NoRules);
            if (Hud != null)
            {
                Hud.ShowLevel(Def);
                // M5 (CONTRACT_M5 3, 16.10): the intro card lists the people of the level with its title.
                var people = new List<PersonalityDef>();
                foreach (Inhabitant h in Level.Inhabitants)
                {
                    people.Add(PersonalityOf(h));
                }
                Hud.ShowPeopleOf(people);
                GameRules rules = Rules ?? NoRules;
                Hud.SetGauges(rules.Creak, rules.DisplacementMemory);
                Hud.SetBodyHints(rules.Bodies, rules.Lamp && Level.Furniture.Body != null && Level.Furniture.Body.HasLight);
            }
            Ghost?.Hide();
            Ghost?.ShowRings(false);
            Ghost?.ShowSeat(null);
            Ghost?.ShowStopRing(null);
            StateChanged?.Invoke(State);
        }

        /// <summary>
        /// M4 (amendments 9.2, 9.3, 9.9): every routine's seat hook (a routine rebuilt by Inhabitant.Init gets it back
        /// on the next step), the carry distance of the furniture's body, and the Sitting switch.
        /// </summary>
        private void WireRoutines(GameRules rules)
        {
            List<Inhabitant> inhabitants = Level.Inhabitants;
            float carryForward = Level.Furniture.Body != null ? Level.Furniture.Body.CarryForward : Tuning.CarryForward;
            for (int i = 0; i < inhabitants.Count && i < seatHooks.Length; i++)
            {
                InhabitantRoutine routine = inhabitants[i].Routine;
                if (routine == null)
                {
                    continue;
                }
                if (routine.SeatOccupied == null)
                {
                    routine.SeatOccupied = seatHooks[i];
                }
                routine.CarryForward = carryForward;
                routine.SittingEnabled = rules.Sitting;
                // M5: the memory and the meter follow the routine's personality (a routine rebuilt by Inhabitant.Init too).
                // The seat registry, the investigate planner and the floor stay as RoutineFactory set them.
                PersonalityDef p = routine.Personality;
                if (i < memories.Length && memories[i] != null)
                {
                    memories[i].Tolerance = p.Tolerance;
                }
                if (i < meters.Length && meters[i] != null)
                {
                    meters[i].GainFactor = p.SuspicionFactor;
                }
            }
        }

        // ----- M5: personalities, doors and the dog (docs/CONTRACT_M5.md 3; CONTRACT_M5_v3.md 3, 4, 15.2, 15.5) -----

        /// <summary>The personality an inhabitant's routine runs with (the default row without a routine).</summary>
        private static PersonalityDef PersonalityOf(Inhabitant inhabitant)
        {
            return inhabitant != null && inhabitant.Routine != null ? inhabitant.Routine.Personality : PersonalityDef.For(null);
        }

        /// <summary>The first inhabitant with a memory (the dog has none), 0 when there is none.</summary>
        private int FirstObserver()
        {
            for (int i = 0; i < Level.Inhabitants.Count; i++)
            {
                if (PersonalityOf(Level.Inhabitants[i]).Memory)
                {
                    return i;
                }
            }
            return 0;
        }

        /// <summary>The nearest closed leaf the furniture can open from where it stands (DoorLeaf.InReach), or null.</summary>
        private DoorLeaf NearestClosedLeafInReach(FurnitureController furniture)
        {
            if (Level == null || furniture == null)
            {
                return null;
            }
            DoorLeaf best = null;
            float bestDistance = float.MaxValue;
            foreach (DoorLeaf leaf in Level.Leaves)
            {
                if (leaf == null || leaf.Open || !leaf.InReach(furniture))
                {
                    continue;
                }
                float d = YawMath.Planar(furniture.transform.position - leaf.Geometry.Center).magnitude;
                if (d < bestDistance)
                {
                    bestDistance = d;
                    best = leaf;
                }
            }
            return best;
        }

        /// <summary>
        /// CONTRACT_M5_v3 15.2, the furniture's action key hook (called inside its step, once per E press it consumes while
        /// upright and in no action): a closed leaf in reach takes E before the body action (the lamp switch). The door
        /// opens only when the furniture accepts the 0.6 s external action (still, upright, not pinned, not carried);
        /// otherwise E does nothing at all. With no closed leaf in reach, E is the body's.
        /// </summary>
        private bool ClaimActionKey()
        {
            if (Level == null || State != PlayState.Playing)
            {
                return false;
            }
            FurnitureController furniture = Level.Furniture;
            if (furniture.Hidden)
            {
                // M6 (CONTRACT_M6 2.5): E inside the wardrobe leaves it: visible again in front of it, a brisk moving
                // action (Tuning.WardrobeActionTime). M7 polish: the doors swing open at once (PlayWardrobeDoors),
                // on this same step, instead of waiting for the action to end.
                if (furniture.BeginExternalAction(Tuning.WardrobeActionTime))
                {
                    furniture.SetHidden(false);
                    PlayWardrobeDoors(WardrobeProp, false, furniture);
                    Wardrobe = WardrobeStage.Leaving;
                    LeaveCount++;
                }
                return true;
            }
            DoorLeaf leaf = NearestClosedLeafInReach(furniture);
            if (leaf == null)
            {
                // M6: no closed leaf in reach: a wardrobe the furniture fits in, standing in front of it, takes E.
                PropDef wardrobe = WardrobeFor(furniture);
                if (wardrobe == null)
                {
                    return false;
                }
                if (furniture.BeginExternalAction(Tuning.WardrobeActionTime))
                {
                    WardrobeProp = wardrobe;
                    PlayWardrobeDoors(wardrobe, true, furniture);
                    Wardrobe = WardrobeStage.Entering;
                }
                return true;
            }
            if (furniture.BeginExternalAction(Tuning.DoorOpenTime))
            {
                leaf.BeginOpen();
                DoorOpenCount++;
                doorOpenedThisStep = leaf;
            }
            return true;
        }

        /// <summary>
        /// Step 1, after the furniture: every swinging leaf advances one fixed step. The E press step is the swing's first
        /// step, so the leaf reaches its open angle on the 30th and last step of the opening action and has its samples on
        /// all 30 steps (CONTRACT_M5_v3 15.2, wave 5A.1 critique m5; the audit's opening samples end at 90 deg); its next
        /// Step only ends the swing. The level's open mask counts the leaf from its first swing step
        /// (LevelInstance.OpenMask), like the audit's mask | bit.
        /// </summary>
        private void StepLeaves(float dt)
        {
            foreach (DoorLeaf leaf in Level.Leaves)
            {
                if (leaf != null && leaf.Swinging)
                {
                    leaf.Step(dt);
                }
            }
        }

        /// <summary>
        /// Step 4, after the caught rule (CONTRACT_M5_v3 4 and 15.5): each awake dog has its own accumulator with the caught
        /// rule's grace. Seen moving by the dog (the furniture or a swinging leaf) for the grace, it barks (emitted with the
        /// noise, step 7), then its accumulator is held at 0 for <see cref="Tuning.BarkCooldown"/>. No hearing, no bark.
        /// A bark is never a catch.
        /// </summary>
        private void StepBarks(GameRules rules, bool moving, float dt)
        {
            List<Inhabitant> inhabitants = Level.Inhabitants;
            for (int i = 0; i < inhabitants.Count && i < barkRules.Length; i++)
            {
                if (!PersonalityOf(inhabitants[i]).Barks)
                {
                    continue;
                }
                if (barkCooldowns[i] > 0)
                {
                    barkCooldowns[i]--;
                    barkRules[i].Reset();
                    continue;
                }
                if (!rules.Hearing)
                {
                    barkRules[i].Reset();
                    continue;
                }
                if (barkRules[i].Step(seesPlayer[i] || seesLeaf[i], moving, dt))
                {
                    barkRules[i].Reset();
                    barkCooldowns[i] = Mathf.RoundToInt(Tuning.BarkCooldown / dt);
                    barksThisStep.Add(i);
                }
            }
        }

        /// <summary>Step 7: this step's barks, each a noise event at its dog (CONTRACT_M5_v3 4).</summary>
        private void EmitBarks()
        {
            FurnitureController furniture = Level.Furniture;
            foreach (int i in barksThisStep)
            {
                Vector3 at = YawMath.Planar(Level.Inhabitants[i].Routine.Position); // MUTATION:BARK_AT
                BarkCount++;
                LastBarkAt = at;
                LastBarkStep = Steps;
                EmitUnlessMasked(new NoiseEvent(at, Hearing.RadiusOf(NoiseKind.Bark), NoiseKind.Bark));
            }
        }

        // ----- 6. CONTRACT_M5 20: the dog's hold -----

        /// <summary>
        /// Step 6, after the investigations and the carry (CONTRACT_M5 20). A bark of this step (<see cref="StepBarks"/>) sends
        /// its dog running to the furniture (<see cref="InhabitantRoutine.BeginRun"/>), one hold at a time, with the memory rule
        /// on and the furniture neither hidden nor carried. A furniture that moved on before the dog got there is chased from
        /// where the dog stopped; one the dog cannot reach ends the run. Within InvestigateReach + CarryReachMargin the dog
        /// holds it: the furniture is pinned (<see cref="ApplyPin"/>, as when sat on), the dog barks at it every
        /// <see cref="Tuning.DogHoldBarkInterval"/> (a sound, not a noise event), and the nearest human free to come (memory,
        /// Routine or Alerted, not frozen, on no other errand) is sent to it with <see cref="InhabitantRoutine.Investigate"/>.
        /// Its arrival is <see cref="StepInvestigations"/>': out of place for its memory, one discovery and the carry back to its
        /// slot, as always; in place, nothing. The hold ends when the furniture is put down, when the called human goes back to
        /// its routine without a carry (in place, or no path: it accepts the furniture where it stands), when nobody could be
        /// sent for <see cref="Tuning.DogHoldMaxWait"/>, or when the dog is interrupted; the dog then resumes its routine.
        /// </summary>
        private void StepDogHold(GameRules rules, float dt)
        {
            FurnitureController furniture = Level.Furniture;
            List<Inhabitant> inhabitants = Level.Inhabitants;
            if (holdDog < 0)
            {
                if (!rules.DisplacementMemory || furniture.Hidden || furniture.Carried)
                {
                    return;
                }
                foreach (int i in barksThisStep)
                {
                    InhabitantRoutine dog = inhabitants[i].Routine;
                    Vector3 target = YawMath.Planar(furniture.transform.position);
                    dog.BeginRun(target); // MUTATION:DOG_RUN
                    if (dog.Running)
                    {
                        holdDog = i;
                        holdTarget = target;
                        dogHolding = false;
                        holdCaller = -1;
                        holdWaitSteps = 0;
                        DogRunCount++;
                        return;
                    }
                }
                return;
            }
            InhabitantRoutine d = holdDog < inhabitants.Count ? inhabitants[holdDog].Routine : null;
            if (d == null || !d.Running || d.Mode != InhabitantMode.Investigating || furniture.Hidden)
            {
                // The dog was interrupted (a pin, a startle), or the furniture went into a wardrobe.
                EndHold();
                return;
            }
            Vector3 at = YawMath.Planar(furniture.transform.position);
            float reach = Tuning.InvestigateReach + Tuning.CarryReachMargin;
            if (!dogHolding)
            {
                if (furniture.Carried || !d.ReachedTarget)
                {
                    if (furniture.Carried)
                    {
                        // A human already carries it back: nothing left to hold.
                        EndHold();
                    }
                    return;
                }
                if (YawMath.Planar(at - d.Position).magnitude > reach)
                {
                    if (YawMath.Planar(holdTarget - d.Position).magnitude > reach)
                    {
                        // No way to where it was: the dog gives up.
                        EndHold();
                        return;
                    }
                    // It moved on meanwhile: after it again.
                    holdTarget = at;
                    d.BeginRun(at);
                    return;
                }
                dogHolding = true; // MUTATION:DOG_HOLD
                DogHoldCount++;
                holdBarkSteps = 0;
                ApplyPin(furniture);
            }
            if (putDownThisStep)
            {
                // Put back where it belongs: the dog lets go.
                EndHold();
                return;
            }
            if (furniture.Carried || carrier >= 0)
            {
                // On its way back in a human's hands: the dog waits, quiet.
                return;
            }
            if (--holdBarkSteps <= 0)
            {
                holdBarkThisStep = true;
                holdBarkSteps = Mathf.Max(1, Mathf.RoundToInt(Tuning.DogHoldBarkInterval / dt));
            }
            if (holdCaller >= 0)
            {
                if (holdCaller < inhabitants.Count && inhabitants[holdCaller].Routine.Mode == InhabitantMode.Investigating)
                {
                    return;
                }
                // Back to its routine without a carry: it found the furniture in place, or could not reach it and accepted it.
                EndHold();
                return;
            }
            int best = -1;
            float bestDistance = float.MaxValue;
            for (int i = 0; i < inhabitants.Count; i++)
            {
                InhabitantRoutine h = inhabitants[i].Routine;
                bool busy = (i < switchingOn.Length && switchingOn[i]) || i == clueFinder || (i < doorFixers.Length && doorFixers[i] >= 0);
                if (h == null || !h.Personality.Memory || !CanObserve(h) || busy)
                {
                    continue;
                }
                float distance = YawMath.Planar(h.Position - at).magnitude;
                if (distance < bestDistance)
                {
                    bestDistance = distance;
                    best = i;
                }
            }
            if (best >= 0)
            {
                InhabitantRoutine h = inhabitants[best].Routine;
                h.Investigate(at); // MUTATION:DOG_CALL
                if (h.Mode == InhabitantMode.Investigating)
                {
                    holdCaller = best;
                    investigateTargets[best] = at;
                    resolved[best] = false;
                    holdWaitSteps = 0;
                    DogCallCount++;
                    return;
                }
            }
            if (++holdWaitSteps >= Mathf.RoundToInt(Tuning.DogHoldMaxWait / dt))
            {
                // Nobody could come: the dog gives up.
                EndHold();
            }
        }

        /// <summary>CONTRACT_M5 20: the hold (or the run) is over: the dog resumes its routine and lets the furniture go.</summary>
        private void EndHold()
        {
            if (holdDog >= 0 && holdDog < Level.Inhabitants.Count)
            {
                InhabitantRoutine d = Level.Inhabitants[holdDog].Routine;
                if (d != null && d.Running)
                {
                    d.CancelInvestigation();
                }
            }
            holdDog = -1;
            dogHolding = false;
            holdCaller = -1;
            holdWaitSteps = 0;
            ApplyPin(Level.Furniture);
        }

        /// <summary>
        /// The furniture is pinned while a sitter sits on it (M4) or while the dog holds it and no human carries it
        /// (CONTRACT_M5 20). Only a change calls <see cref="FurnitureController.Pin"/>.
        /// </summary>
        private void ApplyPin(FurnitureController furniture)
        {
            bool pinned = sitPinned || (dogHolding && !furniture.Carried);
            if (furniture.Pinned != pinned)
            {
                // Pin(false) re-arms the neutral input wait (amendment 9.3): a key held through the pin is ignored.
                furniture.Pin(pinned);
            }
        }

        // ----- M5 wave 5B: the robots (docs/CONTRACT_M5.md 4, 16.8) -----

        /// <summary>
        /// The level's robots, as the level builder listed them (LevelInstance.Robots, one per <see cref="LevelDef.Robots"/>
        /// entry, built by Robot.Create under the level root). Each one stands where its timeline starts (time 0).
        /// </summary>
        private void BuildRobots()
        {
            robots.Clear();
            robotPositions.Clear();
            robotSteps = 0;
            RobotTime = 0f;
            foreach (Robot listed in Level.Robots)
            {
                if (listed != null)
                {
                    robots.Add(listed);
                }
            }
            robotTouching = new bool[robots.Count];
            foreach (Robot robot in robots)
            {
                robotPositions.Add(YawMath.Planar(robot.Path.PositionAt(0f)));
            }
        }

        /// <summary>
        /// Step 2, after the inhabitants: every robot goes to its timeline's pose at <see cref="RobotTime"/> (it never waits:
        /// won, caught or not). A robot whose disc begins to overlap the furniture's footprint (RobotPath.Overlaps, on this
        /// step and not on the last one) makes a contact (<see cref="Contact"/>). Robots are no inhabitants' concern: no
        /// collider, never seen, never an occluder.
        /// </summary>
        private void StepRobots(FurnitureController furniture, bool playing, float dt)
        {
            if (robots.Count == 0)
            {
                return;
            }
            robotSteps++;
            float t = robotSteps * dt;
            RobotTime = t;
            for (int k = 0; k < robots.Count; k++)
            {
                Robot robot = robots[k];
                if (robot == null)
                {
                    continue;
                }
                RobotPath path = robot.Path;
                Vector3 at = YawMath.Planar(path.PositionAt(t));
                robot.SetPose(Level.Floor.OnFloor(at), path.HeadingAt(t));
                robotPositions[k] = at;
                bool touching = RobotPath.Overlaps(at, furniture.Pose, furniture.SampleSize); // MUTATION:ROBOT_CONTACT
                touching &= !furniture.Hidden;
                bool begins = touching && !robotTouching[k];
                robotTouching[k] = touching;
                if (begins)
                {
                    Contact(robot, furniture, t, at, playing);
                }
            }
        }

        /// <summary>
        /// CONTRACT_M5 4 and 16.8, a robot's contact with the furniture: while playing, the furniture is shoved by
        /// RobotPushDistance over RobotPushTime along the robot's heading (against it when the furniture's centre is behind
        /// the robot: the player ran into its back), through <c>furniture.BeginPush</c>, which refuses during any action (a
        /// shove under way included) and while lying; never while pinned or carried. The push runs inside the furniture's own
        /// steps from the next one, and a pin or a carry ends it there. Accepted or not, the robot reverses its loop.
        /// </summary>
        private void Contact(Robot robot, FurnitureController furniture, float t, Vector3 at, bool playing)
        {
            RobotPath path = robot.Path;
            Vector3 heading = path.ForwardAt(t);
            Vector3 toFurniture = YawMath.Planar(furniture.transform.position) - at;
            Vector3 direction = Vector3.Dot(toFurniture, heading) >= 0f ? heading : -heading;
            RobotContactCount++;
            contactThisStep = true;
            contactAt = at;
            bool free = playing && !furniture.Pinned && !furniture.Carried;
            if (free && furniture.BeginPush(direction, Tuning.RobotPushDistance, Tuning.RobotPushTime))
            {
                ShoveCount++;
                LastShoveDirection = direction;
            }
            path.Reverse(t);
            robot.SetPose(Level.Floor.OnFloor(YawMath.Planar(path.PositionAt(t))), path.HeadingAt(t));
        }

        /// <summary>
        /// CONTRACT_M5 4: the noise is emitted unless the robots' hum masks it (<see cref="Hearing.IsMasked"/>: a hop, a roll
        /// or a click within RobotHumRadius of a robot). True when it was emitted.
        /// </summary>
        private bool EmitUnlessMasked(NoiseEvent e)
        {
            if (HumMasks(e.Kind, e.Position))
            {
                MaskedNoiseCount++;
                NoiseMasked?.Invoke(e);
                return false;
            }
            Emit(e);
            return true;
        }

        /// <summary>The robots' hum masks a noise of <paramref name="kind"/> made at <paramref name="at"/> (planar positions of this step).</summary>
        private bool HumMasks(NoiseKind kind, Vector3 at)
        {
            NoiseKind heard = kind; // MUTATION:GAME_HUM_CREAK
            bool masked = Hearing.IsMasked(heard, at, robotPositions); // MUTATION:GAME_HUM_NONE
            return masked;
        }

        // ----- M5 wave 5B: the rocking chair (docs/CONTRACT_M5.md 5, 16.9) -----

        /// <summary>
        /// Step 1, after the furniture: the rocking chair comes to rest on the first step at or below both moving thresholds
        /// after a step above them, measured on its travel (a shove's slide included) and its yaw only; a step inside an action
        /// (a shove is the push action), a pin or a carry never comes to rest. It then rocks: an external action (moving, input
        /// ignored) of RockTime, or RockCarefulTime when careful mode is held at that moment, from the next step; the visual
        /// pitches by RockDegrees (<see cref="RockView"/>) and the runners creak for the rock's time. Gated by Rules.Bodies.
        /// Sat on, it never rocks in the rules.
        /// </summary>
        private void StepRock(GameRules rules, FurnitureController furniture, Vector3 stepFrom, float dt)
        {
            bool held = furniture.Pinned || furniture.Carried;
            float travel = dt > 0f ? YawMath.Planar(furniture.transform.position - stepFrom).magnitude / dt : 0f;
            bool travelled = !held && MotionRule.IsMoving(travel, furniture.YawRate);
            bool rests = rockArmed && !travelled && !held && !furniture.ActionActive;
            rockArmed = travelled;
            BodyDef body = furniture.Body;
            bool rocks = body != null && body.Rocks; // MUTATION:ROCK_STOP
            if (!rests || !rocks || !rules.Bodies || State != PlayState.Playing)
            {
                return;
            }
            float time = furniture.Careful ? Tuning.RockCarefulTime : Tuning.RockTime; // MUTATION:ROCK_CAREFUL
            if (!furniture.BeginExternalAction(time))
            {
                return;
            }
            RockCount++;
            rockedThisStep = true;
            rockTime = time;
            RockView view = furniture.GetComponent<RockView>();
            if (view == null)
            {
                view = furniture.gameObject.AddComponent<RockView>();
            }
            view.Begin(furniture, time, Tuning.RockDegrees);
        }

        // ----- M5 wave 5B: the load (docs/CONTRACT_M5.md 6, 16.5) -----

        /// <summary>
        /// The load of <c>player.load</c> (a known kind; never on the rocking chair nor the floor lamp, as the validator says):
        /// a fresh <see cref="LoadBalance"/>, and its <see cref="OutOfSight.LoadView"/>, the one the level builder hung on the
        /// furniture's visual (LevelInstance.LoadView, CONTRACT_M5 18). A level with a load and no view is a builder defect:
        /// it is logged as an error, and the rule runs without a visual.
        /// </summary>
        private void BuildLoad()
        {
            Load = null;
            LoadView = null;
            loadHistory.Clear();
            FurnitureController furniture = Level.Furniture;
            string kind = Def.Player != null ? Def.Player.Load : null;
            BodyDef body = furniture.Body;
            if (string.IsNullOrEmpty(kind) || !OutOfSight.LoadView.IsKind(kind) || (body != null && (body.Rocks || body.HasLight)))
            {
                return;
            }
            Load = new LoadBalance();
            LoadView = Level.LoadView;
            if (LoadView == null)
            {
                Debug.LogError($"[GameState] level {LevelId} carries the load '{kind}' but the level builder made no LoadView for it");
            }
            int window = Mathf.RoundToInt(Tuning.LoadWindow / Time.fixedDeltaTime);
            for (int i = 0; i <= window; i++)
            {
                loadHistory.Enqueue(Vector2.zero);
            }
        }

        /// <summary>
        /// Step 1, after the furniture: the load's rule steps with the furniture's planar velocity of this step (a shove's slide
        /// is the push action's velocity); on the step it falls, the fall. The visual sways with
        /// <see cref="LoadBalance.SwayTiltLocal"/> in the furniture's frame, upright once the load fell.
        /// </summary>
        private void StepLoad(FurnitureController furniture, float dt)
        {
            if (Load == null)
            {
                return;
            }
            if (!Load.Fallen && State == PlayState.Playing)
            {
                Vector3 fv = furniture.Velocity;
                Vector2 v = new Vector2(fv.x, fv.z); // MUTATION:LOAD_VELOCITY
                Load.Step(dt, v);
                loadHistory.Enqueue(v);
                loadHistory.Dequeue();
                // v(t - window): the head of the kept window, as in LoadBalance.
                Vector2 change = v - loadHistory.Peek();
                if (Load.JustFell)
                {
                    Fall(furniture, change);
                }
            }
            if (LoadView != null)
            {
                LoadView.SetTilt(CarryingLoad ? Load.SwayTiltLocal(furniture.Yaw) : Vector2.zero); // MUTATION:LOAD_SWAY
            }
        }

        /// <summary>
        /// CONTRACT_M5 6: the load falls. It lands on the floor beside the furniture, thrown against the velocity change (the
        /// furniture changed speed under it), a crash (a noise at the clue in step 7) and a clue no one has found yet. The
        /// furniture goes on without it.
        /// </summary>
        private void Fall(FurnitureController furniture, Vector2 change)
        {
            CrashCount++;
            crashThisStep = true;
            ClueAt = ClueLanding(furniture, change);
            ClueActive = true;
            clueFound = false;
            clueFinder = -1;
            if (LoadView != null)
            {
                LoadView.SpawnClue(ClueAt);
            }
        }

        /// <summary>
        /// Where the fallen load lies: from the furniture's centre, against the velocity change, past the footprint's edge by
        /// Tuning.ClueThrowDistance, its centre kept <see cref="ClueClearance"/> (at least the clue's spread) short of a wall or
        /// a furniture in the way, on the floor. When something in the way cuts the throw short, the clue falls on the
        /// opposite side, away from the wall, if there is more room there.
        /// </summary>
        private Vector3 ClueLanding(FurnitureController furniture, Vector2 change)
        {
            Vector3 fall = new Vector3(-change.x, 0f, -change.y);
            if (fall.sqrMagnitude < 1e-8f)
            {
                fall = YawMath.Forward(furniture.Yaw);
            }
            fall.Normalize();
            float wanted = EdgeAlong(furniture, fall) + Tuning.ClueThrowDistance;
            float distance = ClueRoom(furniture, fall, wanted);
            if (distance < wanted - ClueRoomEpsilon)
            {
                float back = ClueRoom(furniture, -fall, wanted);
                if (back > distance)
                {
                    fall = -fall;
                    distance = back;
                }
            }
            Vector3 at = YawMath.Planar(furniture.transform.position) + fall * Mathf.Max(0f, distance);
            return Level.Floor.OnFloor(at);
        }

        // A throw counts as cut short below its wanted distance by more than this (float rounding only), metres.
        private const float ClueRoomEpsilon = 1e-4f;

        /// <summary>The clue's centre stays this far from a wall or a furniture: its spread, and never less than ClueWallMargin.</summary>
        public static float ClueClearance => Mathf.Max(Tuning.ClueWallMargin, Tuning.ClueSpreadRadius);

        /// <summary>The distance from the furniture's centre to its footprint's edge along the planar unit <paramref name="way"/>.</summary>
        private static float EdgeAlong(FurnitureController furniture, Vector3 way)
        {
            Vector3 local = YawMath.Rotate(way, -furniture.Yaw);
            Vector3 size = furniture.SampleSize;
            return Mathf.Abs(local.x) * size.x * 0.5f + Mathf.Abs(local.z) * size.z * 0.5f;
        }

        /// <summary>
        /// How far along the planar unit <paramref name="way"/> the clue's centre may land, up to <paramref name="wanted"/>:
        /// <see cref="ClueClearance"/> short of the first wall or other furniture in the way.
        /// </summary>
        private static float ClueRoom(FurnitureController furniture, Vector3 way, float wanted)
        {
            float distance = wanted;
            Vector3 origin = furniture.transform.position + Vector3.up * Tuning.ClueProbeHeight;
            RaycastHit[] hits = Physics.RaycastAll(origin, way, wanted + ClueClearance, Layers.ChairBlockerMask, QueryTriggerInteraction.Ignore);
            foreach (RaycastHit hit in hits)
            {
                if (hit.collider != null && !hit.collider.transform.IsChildOf(furniture.transform))
                {
                    distance = Mathf.Min(distance, hit.distance - ClueClearance);
                }
            }
            return distance;
        }

        /// <summary>
        /// Step 5, after the memory: the clue is one more sample for the watchers with memory that can observe (Routine or
        /// Alerted, not frozen). The first one that sees it costs one discovery (the clue's only one; suspicion 1 loses as
        /// usual) and is sent to put it away; one that refuses (the dog has no memory and is never asked) leaves it to the
        /// next. Nobody else looks while the finder is on its way.
        /// </summary>
        private void StepClue()
        {
            if (!ClueActive || clueFinder >= 0)
            {
                return;
            }
            List<Inhabitant> inhabitants = Level.Inhabitants;
            Vector3 point = ClueAt + Vector3.up * Tuning.ClueSampleHeight;
            for (int i = 0; i < inhabitants.Count && i < visions.Length; i++)
            {
                InhabitantRoutine routine = inhabitants[i].Routine;
                Vision vision = visions[i];
                if (routine == null || vision == null || !routine.Personality.Memory || !CanObserve(routine) || !vision.SeesPoint(point))
                {
                    continue;
                }
                if (!clueFound)
                {
                    clueFound = true;
                    ClueDiscoveryCount++;
                    DiscoveryCount++;
                    meters[i].AddDiscovery(); // MUTATION:CLUE_DISCOVERY
                    Sfx?.PlayHein(PanToward(inhabitants[i].transform.position));
                    if (meters[i].Lost || meters[i].Value >= Tuning.SuspicionLose)
                    {
                        Lose(LoseReason.Suspicion, i);
                        return;
                    }
                }
                routine.BeginPutAway(YawMath.Planar(ClueAt));
                if (routine.Mode == InhabitantMode.Investigating)
                {
                    clueFinder = i;
                    return;
                }
            }
        }

        /// <summary>
        /// Step 6: the clue goes on the step its finder puts it away (<see cref="InhabitantRoutine.JustPutAway"/>); a finder
        /// interrupted on its way (a startle, a pin) leaves it on the floor for the next one, at no new discovery.
        /// </summary>
        private void StepPutAway()
        {
            if (clueFinder < 0)
            {
                return;
            }
            InhabitantRoutine routine = clueFinder < Level.Inhabitants.Count ? Level.Inhabitants[clueFinder].Routine : null;
            if (routine != null && routine.JustPutAway)
            {
                if (LoadView != null)
                {
                    LoadView.ClearClue();
                }
                ClueActive = false;
                PutAwayCount++;
                clueFinder = -1;
            }
            else if (routine == null || routine.Mode != InhabitantMode.Investigating)
            {
                clueFinder = -1;
            }
        }

        /// <summary>
        /// Step 9: the door hint shows while a closed leaf is in reach of a furniture that may open it (playing, upright,
        /// not pinned, not carried, in no action).
        /// </summary>
        private bool DoorHintWanted(FurnitureController furniture)
        {
            return State == PlayState.Playing && Level.Leaves.Count > 0 && !furniture.Carried && !furniture.Pinned && !furniture.Tipped
                && !furniture.ActionActive && !furniture.Hidden && NearestClosedLeafInReach(furniture) != null;
        }

        /// <summary>M6: the wardrobe prompt shows while hidden (and still), or in front of a wardrobe E would enter.</summary>
        private bool HideHintWanted(FurnitureController furniture)
        {
            if (wardrobes.Count == 0 || State != PlayState.Playing || furniture.Carried || furniture.Pinned || furniture.Tipped || furniture.ActionActive)
            {
                return false;
            }
            return furniture.Hidden || (NearestClosedLeafInReach(furniture) == null && WardrobeFor(furniture) != null);
        }

        /// <summary>
        /// M4 (CONTRACT_M4 3, amendment 9.2): the seat hook of inhabitant <paramref name="i"/>, read at its moment of
        /// sitting. True when the player body is a seat, stands on the floor (not carried, not lying on its side), and
        /// its center is within <see cref="Tuning.SeatHomeTolerance"/> of the seat home.
        /// </summary>
        private bool PlayerSeatIsHome(int i)
        {
            FurnitureController furniture = Level != null ? Level.Furniture : null;
            if (furniture == null || i < 0 || i >= Level.Inhabitants.Count)
            {
                return false;
            }
            BodyDef body = furniture.Body;
            if (body == null || !body.IsSeat || furniture.Carried || furniture.Tipped || furniture.Hidden)
            {
                return false;
            }
            Vector3 home = Level.Inhabitants[i].Routine.SeatHome.Position;
            float off = YawMath.Planar(furniture.transform.position - home).magnitude;
            return off <= Tuning.SeatHomeTolerance; // MUTATION:SIT_CHECK
        }

        /// <summary>
        /// M3 (docs/CONTRACT_M3.md 6): while true, no fixed step rule runs at all (the title screen and the
        /// pause menu). Time.timeScale is untouched, so rendering and the menus keep animating. The audio
        /// listener pauses with the game; the UI click ignores the listener pause (Sfx).
        /// </summary>
        public bool Paused
        {
            get => GamePause.IsPaused;
            set
            {
                GamePause.IsPaused = value;
                AudioListener.pause = value;
            }
        }

        private void FixedUpdate()
        {
            if (Paused /*MUTATION:PAUSE*/ || Level == null || Level.Furniture == null)
            {
                return;
            }
            float dt = Time.fixedDeltaTime;
            GameRules rules = Rules ?? NoRules;
            FurnitureController furniture = Level.Furniture;
            List<Inhabitant> inhabitants = Level.Inhabitants;
            bool playing = State == PlayState.Playing;
            CreakedThisStep = false;
            putDownThisStep = false;
            switchedOnThisStep = false;
            pratfallThisStep = -1;
            barksThisStep.Clear();
            holdBarkThisStep = false;
            doorOpenedThisStep = null;
            householdDoorThisStep = null;
            contactThisStep = false;
            crashThisStep = false;
            rockedThisStep = false;
            hopMasked = false;
            rollMasked = false;

            // 1. The furniture: driven by input, or following its carrier. M4: it reads the rule switches itself.
            // M5: E in reach of a closed leaf begins its opening inside this step (ClaimActionKey); then the leaves swing.
            // M5 wave 5B: a shove is the furniture's own push action (begun by a contact in step 2 of an earlier step), so it
            // runs inside furniture.Step; Shoving reads it after the step. Then the rock and the load.
            furniture.Rules = rules;
            Vector3 stepFrom = furniture.transform.position;
            if (furniture.Carried)
            {
                FollowCarrier(dt);
            }
            else
            {
                furniture.Step(dt, playing);
            }
            Shoving = furniture.Pushing;
            StepLeaves(dt);
            StepWardrobe(furniture);
            StepRock(rules, furniture, stepFrom, dt);
            StepLoad(furniture, dt);

            // 2. Inhabitants, each with its seat hook, the body's carry distance and the Sitting switch (M4).
            // M5 wave 5B: then the robots, and their contacts with the furniture.
            WireRoutines(rules);
            for (int i = 0; i < inhabitants.Count; i++)
            {
                inhabitants[i].Step(dt);
            }
            StepHouseholdDoors();
            StepRobots(furniture, playing, dt);

            // 3. Vision of the player furniture, for every inhabitant. M2.1 (11.3): a decoy explains the chair
            // whether or not it is seen, so decoys need no raycast at all.
            // M5: each watcher with its own range, angle and eye (Vision); during a swing, the leaf samples too. Each rule
            // counts its own watchers: the catch and the exit only humans, the bark only the dog.
            bool seen = false;
            bool seenForExit = false;
            bool leafSeen = false;
            bool dogSees = false;
            // M5 wave 5B (16.5): with a load the sample box is the load's height taller.
            float loadHeight = LoadExtraHeight;
            for (int i = 0; i < inhabitants.Count; i++)
            {
                Vision vision = visions[i];
                bool sees = vision != null && vision.Step(furniture, loadHeight);
                bool seesSwing = vision != null && vision.StepLeaves(Level.Leaves); // MUTATION:LEAF_JOIN
                seesPlayer[i] = sees;
                seesLeaf[i] = seesSwing;
                PersonalityDef p = PersonalityOf(inhabitants[i]);
                bool catches = p.CountsForCatch; // MUTATION:DOG_CATCH
                if (catches)
                {
                    seen |= sees;
                    leafSeen |= seesSwing;
                }
                seenForExit |= sees && p.CountsForExit;
                dogSees |= (sees || seesSwing) && p.Barks;
            }
            Seen = seen;
            LeafSeen = leafSeen;
            SeenByDog = dogSees;

            // 4. Exit and win, then the caught rule (win first, as in M1).
            // M5 wave 5B (CONTRACT_M5 4, 16.8, 19): a step of a shove is moving through the push action (FurnitureController's
            // predicate counts any action), so the furniture's own predicate is the whole rule.
            FurnitureMoving = furniture.IsMoving;
            if (playing)
            {
                Steps++;
                Elapsed = Steps * dt;
                Vector3 center = furniture.transform.position;
                bool exitCounts = Def.Exit.Contains(center) && !furniture.Carried && !furniture.Hidden && (!rules.ExitOnlyUnseen || !seenForExit);
                // M4: a furniture pinned under a sitter never moves (FurnitureController), so it is never caught.
                bool moving = furniture.IsMoving /*MUTATION:SATON_MOVING*/ && !furniture.Carried;
                if (exitCounts)
                {
                    Win();
                }
                else if (Rule.Step(seen || leafSeen, moving, dt))
                {
                    // M5 (CONTRACT_M5_v3 15.2): a leaf seen swinging is the furniture seen moving.
                    Lose(LoseReason.SeenMoving, -1);
                }
                if (State == PlayState.Playing)
                {
                    StepBarks(rules, moving, dt);
                }
            }

            // 5. M4: the moment of sitting (the pin, the slots, a pratfall's discovery), then memory: observation,
            // discoveries, suspicion, possibly a lose.
            StepSitting();
            if (State == PlayState.Playing && rules.DisplacementMemory)
            {
                StepMemory();
            }
            else
            {
                Array.Clear(observations, 0, observations.Length);
            }
            // M5 wave 5B: a fallen load's clue seen by a watcher with memory.
            if (State == PlayState.Playing)
            {
                StepClue();
            }
            // M6: door memory, on a level that turns it on.
            if (State == PlayState.Playing && rules.DisplacementMemory && Def.DoorMemory)
            {
                StepDoorMemory();
            }

            // 6. Investigations and the carry, then the lamp switch-on (M4). M5 wave 5B: then a clue put away.
            if (State == PlayState.Playing)
            {
                StepInvestigations();
                // CONTRACT_M5 20: the dog's run and hold, after the carry (a put down ends it).
                if (State == PlayState.Playing)
                {
                    StepDogHold(rules, dt);
                }
                StepLamp(rules);
                StepPutAway();
                StepDoorPutBack();
            }

            // 7. Noise: hop events, M4's topple, click and roll (all silent on a rug or in a soft room), then the creak gauge.
            floorSilent = Level.IsSilentAt(furniture.transform.position);
            int hops = furniture.HopCount;
            hoppedThisStep = hops != lastHopCount;
            lastHopCount = hops;
            hopSilent = hoppedThisStep && floorSilent;
            int topples = furniture.ToppleCount;
            toppledThisStep = topples != lastToppleCount;
            lastToppleCount = topples;
            int toggles = furniture.ToggleCount;
            clickedThisStep = toggles != lastToggleCount;
            lastToggleCount = toggles;
            int rolls = furniture.RollCount;
            rolledThisStep = rolls != lastRollCount;
            lastRollCount = rolls;
            if (State == PlayState.Playing)
            {
                StepNoise(rules, FurnitureMoving, dt);
            }
            bool warning = State == PlayState.Playing && rules.Creak && Creak.Warning && !furniture.Carried;
            float progress = warning ? Mathf.Clamp01((Creak.Value - WarningStart) / (1f - WarningStart)) : 0f;
            furniture.CreakTremble = warning ? 0.35f + 0.65f * progress : 0f;

            // 8. Suspicion decay, only for inhabitants in Routine or Alerted.
            float max = 0f;
            for (int i = 0; i < inhabitants.Count; i++)
            {
                if (State == PlayState.Playing && rules.DisplacementMemory && InCalmMode(inhabitants[i].Routine)) // MUTATION:DECAY
                {
                    meters[i].Step(dt);
                }
                max = Mathf.Max(max, meters[i].Value);
            }
            MaxSuspicion = max;

            // 9. HUD, ghost and sounds.
            EyeState = ComputeEye(rules, furniture, FurnitureMoving);
            UpdateGhost(rules, furniture);
            if (Hud != null)
            {
                Hud.SetEye(EyeState, State == PlayState.Playing ? Rule.SeenMoving : 0f);
                Hud.SetGauges(rules.Creak, rules.DisplacementMemory);
                Hud.SetCreak(rules.Creak ? Creak.Value : 0f, warning);
                Hud.SetSuspicion(MaxSuspicion);
                // M4: the hints of the current body only, and the sat-on line while pinned. M4.1 (10.3): the tipped line
                // while the stool lies on its side.
                Hud.SetBodyHints(rules.Bodies, rules.Lamp && furniture.Body != null && furniture.Body.HasLight);
                Hud.SetSatOn(State == PlayState.Playing && furniture.Pinned && sitPinned);
                // CONTRACT_M5 20: the dog's hold line.
                Hud.SetDogHold(State == PlayState.Playing && dogHolding && furniture.Pinned && !sitPinned);
                Hud.SetTipped(State == PlayState.Playing && furniture.LyingDown && !furniture.Carried);
                // M5 (CONTRACT_M5_v3 15.2): E opens the door in reach.
                Hud.ShowDoorHint(DoorHintWanted(furniture));
                // M6 (CONTRACT_M6 2.5): E hides in the wardrobe in front, or leaves it.
                bool pad = InputReader.LastInputWasGamepad;
                string hide = furniture.Hidden ? (pad ? Strings.HudLeavePad : Strings.HudLeave) : (pad ? Strings.HudHidePad : Strings.HudHide);
                Hud.ShowHideHint(HideHintWanted(furniture), hide);
                // M5 wave 5B (CONTRACT_M5 6, 16.5): the balance gauge, while a load is carried.
                Hud.SetBalance(CarryingLoad ? Load.Ratio : 0f, State == PlayState.Playing && CarryingLoad);
            }
            Sfx?.SetTension(warning, progress);
            PlaySounds();
            FixedStepped?.Invoke();
        }

        /// <summary>
        /// M3: Escape or gamepad Start toggles the pause first, so a second press resumes. While paused (pause
        /// menu or title screen), and on the frame a menu closed (its Enter must not also act on the game),
        /// neither R nor Enter does anything, and injected presses are dropped as a real key press would be.
        /// </summary>
        private void Update()
        {
            if (InputReader.PausePressed())
            {
                TogglePause();
            }
            if (Paused || (Menu != null && Menu.ClosedThisFrame))
            {
                InputReader.DiscardGameplayPresses();
                return;
            }
            if (InputReader.RestartPressed())
            {
                Restart();
            }
            else if (State == PlayState.Won && Hud != null && Hud.EndVisible)
            {
                // M3.1: on the end screen, Enter (and gamepad A) is the UI submit of its selected button, and
                // nothing else. Read here as well, the same press could also reach Jouer on the title it opens.
                InputReader.DiscardGameplayPresses();
            }
            else if (State == PlayState.Won && (HasNextLevel || IsLastLevel) && InputReader.NextLevelPressed())
            {
                if (HasNextLevel)
                {
                    NextLevel();
                }
                else
                {
                    FinishGame();
                }
            }
        }

        /// <summary>M3: the pause press. The title screen ignores it (Play is the only way into the game).</summary>
        private void TogglePause()
        {
            if (Menu == null)
            {
                Paused = !Paused;
            }
            else if (!Menu.TitleOpen)
            {
                Menu.SetPaused(!Menu.PauseOpen);
            }
        }

        /// <summary>
        /// M3: back from the end screen. The title in a player; the first level again in the editor, where the title
        /// never shows by itself (docs/CONTRACT_M3.md 6). M3.1: the end screen's button calls it (Enter submits that
        /// button); Update calls it only when the HUD is missing.
        /// </summary>
        public void FinishGame()
        {
            if (Menu != null)
            {
                Menu.ReturnToTitle();
            }
            else
            {
                LoadLevel(FirstLevelId);
            }
        }

        // ----- 1. The carried furniture -----

        /// <summary>
        /// The carried furniture follows <see cref="InhabitantRoutine.CarryAnchor"/>. The pick up lifts it from
        /// where it stood to the anchor over <see cref="Tuning.PickUpDuration"/>, and the put down lowers it to
        /// the return pose over <see cref="Tuning.PutDownDuration"/>, so it never pops.
        /// </summary>
        private void FollowCarrier(float dt)
        {
            FurnitureController furniture = Level.Furniture;
            Inhabitant carrierInhabitant = Carrier;
            if (carrierInhabitant == null)
            {
                furniture.Release(furniture.Pose);
                return;
            }
            InhabitantRoutine routine = carrierInhabitant.Routine;
            carrySteps++;
            Vector3 anchor = routine.CarryAnchor;
            float yaw = routine.BodyYaw;
            Vector3 position = anchor;
            if (routine.LastActivity == RoutineActivity.PuttingDown)
            {
                putDownSteps++;
                float t = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(putDownSteps * dt / Tuning.PutDownDuration));
                FurniturePose back = routine.CarryReturnPose;
                // M5 (CONTRACT_M5_v3 15.4): lowered onto the floor height where it is put back (Release puts it there).
                position = Vector3.Lerp(anchor, Level.Floor.OnFloor(YawMath.Planar(back.Position)), t);
                yaw = Mathf.LerpAngle(yaw, back.Yaw, t);
            }
            else
            {
                float t = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(carrySteps * dt / Tuning.PickUpDuration));
                position = Vector3.Lerp(carryFrom, anchor, t);
                yaw = Mathf.LerpAngle(carryFromYaw, yaw, t);
            }
            furniture.FollowCarrier(position, yaw);
        }

        // ----- 5. Memory -----

        private static bool InCalmMode(InhabitantRoutine routine)
        {
            InhabitantMode mode = routine.Mode;
            return mode == InhabitantMode.Routine || mode == InhabitantMode.Alerted;
        }

        /// <summary>3.1: only inhabitants in Routine or Alerted that are not frozen pinned observe.</summary>
        private static bool CanObserve(InhabitantRoutine routine)
        {
            return InCalmMode(routine) && !routine.IsFrozen;
        }

        private void StepMemory()
        {
            FurnitureController furniture = Level.Furniture;
            List<Inhabitant> inhabitants = Level.Inhabitants;
            // A carried furniture is never observed.
            if (furniture.Carried)
            {
                Array.Clear(observations, 0, observations.Length);
                foreach (FurnitureMemory memory in memories)
                {
                    memory.ResetGrace();
                }
                return;
            }
            FurniturePose pose = furniture.Pose;
            // M4 (CONTRACT_M4 2.1): a stool lying on its side is out of place wherever it lies.
            bool lyingDown = furniture.Tipped;
            for (int i = 0; i < inhabitants.Count; i++)
            {
                InhabitantRoutine routine = inhabitants[i].Routine;
                // M5 (CONTRACT_M5_v3 15.5): the dog has no memory: it never observes, never discovers, is never the last seer.
                if (!CanObserve(routine) || !routine.Personality.Memory)
                {
                    // The grace only measures an unbroken sighting (FurnitureMemory.ResetGrace).
                    memories[i].ResetGrace();
                    observations[i] = Observation.NotSeen;
                    continue;
                }
                // M6 (CONTRACT_M6 2.5): hidden in a wardrobe, the furniture is never seen; its remembered spot may be seen empty.
                Observation observation = furniture.Hidden
                    ? memories[i].ObserveEmptySpot(SeesSpot(i), Time.fixedDeltaTime)
                    : memories[i].Observe(seesPlayer[i], pose, Time.fixedDeltaTime, lyingDown);
                observations[i] = observation;
                if (observation != Observation.NotSeen)
                {
                    lastSeer = i;
                }
                if (observation == Observation.ExplainedByDecoy)
                {
                    ExplainedByDecoySteps++;
                }
                else if (observation == Observation.Discovery)
                {
                    DiscoveryCount++;
                    meters[i].AddDiscovery();
                    Sfx?.PlayHein(PanToward(inhabitants[i].transform.position));
                    if (meters[i].Lost || meters[i].Value >= Tuning.SuspicionLose)
                    {
                        Lose(LoseReason.Suspicion, i);
                        return;
                    }
                    resolved[i] = false;
                    // M6: an empty spot is investigated where it was remembered.
                    Vector3 target = furniture.Hidden ? YawMath.Planar(memories[i].PlayerSlot.Position) : pose.Position;
                    if (furniture.Hidden)
                    {
                        EmptySpotCount++;
                    }
                    investigateTargets[i] = target;
                    routine.Investigate(target);
                }
            }
        }

        // ----- 5. M4: sitting (docs/CONTRACT_M4.md 3, amendment 9.2) -----

        /// <summary>
        /// Resolves this step's moments of sitting, then makes the pin follow the level triggered
        /// <see cref="InhabitantRoutine.SittingOnPlayer"/> flags (released on the first StandingUp step).
        /// </summary>
        private void StepSitting()
        {
            FurnitureController furniture = Level.Furniture;
            List<Inhabitant> inhabitants = Level.Inhabitants;
            bool sitting = false;
            for (int i = 0; i < inhabitants.Count; i++)
            {
                InhabitantRoutine routine = inhabitants[i].Routine;
                if (routine.JustSat && State == PlayState.Playing)
                {
                    if (routine.LastSitResult == SitResult.OnPlayer)
                    {
                        SitOnPlayer(routine);
                    }
                    else if (routine.LastSitResult == SitResult.Pratfall)
                    {
                        Pratfall(i);
                    }
                }
                sitting |= routine.SittingOnPlayer;
            }
            // CONTRACT_M5 20: the dog's hold pins it too.
            sitPinned = sitting;
            ApplyPin(furniture);
        }

        /// <summary>
        /// The player furniture was home in time: the sitter settles it under itself (it snaps to the seat home, the
        /// sitter's position while seated), and the whole household now remembers it there.
        /// </summary>
        private void SitOnPlayer(InhabitantRoutine routine)
        {
            FurnitureController furniture = Level.Furniture;
            var seat = new FurniturePose(YawMath.Planar(routine.SeatHome.Position), routine.SeatHome.Yaw);
            Vector3 from = furniture.transform.position;
            float fromYaw = furniture.Yaw;
            furniture.Teleport(seat.Position, seat.Yaw);
            // M4.1 (CONTRACT_M4 10.7): the rule pose snaps, the visual slides there over SeatSettleTime.
            SeatSettleView settle = furniture.GetComponent<SeatSettleView>();
            if (settle == null)
            {
                settle = furniture.gameObject.AddComponent<SeatSettleView>();
            }
            settle.Begin(furniture, from, fromYaw, SeatSettleTime);
            for (int k = 0; k < memories.Length; k++)
            {
                memories[k].SetPlayerSlot(seat);
            }
            SatOnPlayerCount++;
        }

        /// <summary>Sat on nothing: the pratfall is one discovery (+0.34), and suspicion 1 loses as usual.</summary>
        private void Pratfall(int i)
        {
            PratfallCount++;
            DiscoveryCount++;
            pratfallThisStep = i;
            meters[i].AddDiscovery();
            if (meters[i].Lost || meters[i].Value >= Tuning.SuspicionLose)
            {
                Lose(LoseReason.Suspicion, i);
            }
        }

        // ----- 6. Investigations and the carry -----

        private void StepInvestigations()
        {
            FurnitureController furniture = Level.Furniture;
            List<Inhabitant> inhabitants = Level.Inhabitants;
            for (int i = 0; i < inhabitants.Count; i++)
            {
                InhabitantRoutine routine = inhabitants[i].Routine;
                if (!routine.Personality.Memory)
                {
                    // CONTRACT_M5 20: the dog's run is StepDogHold's, never an investigation.
                    continue;
                }
                if (routine.Mode != InhabitantMode.Investigating)
                {
                    resolved[i] = false;
                }
                else if (routine.ReachedTarget && !resolved[i])
                {
                    resolved[i] = true;
                    float reach = Tuning.InvestigateReach + Tuning.CarryReachMargin;
                    float distance = YawMath.Planar(furniture.transform.position - routine.Position).magnitude;
                    bool free = carrier < 0 && !furniture.Carried && !furniture.Hidden;
                    if (free && distance <= reach && i == holdCaller && dogHolding)
                    {
                        // CONTRACT_M5 20: the human the dog called finds the held furniture. Out of place for its memory: the
                        // usual discovery (suspicion 1 loses as usual), then the carry back below. In place: nothing to put
                        // back; it goes back to its routine and StepDogHold ends the hold.
                        if (!memories[i].OutOfPlace(furniture.Pose, furniture.Tipped)) // MUTATION:DOG_CALL_FINDS
                        {
                            routine.CancelInvestigation();
                            continue;
                        }
                        DiscoveryCount++;
                        DogHoldDiscoveryCount++;
                        meters[i].AddDiscovery();
                        Sfx?.PlayHein(PanToward(inhabitants[i].transform.position));
                        if (meters[i].Lost || meters[i].Value >= Tuning.SuspicionLose)
                        {
                            Lose(LoseReason.Suspicion, i);
                            return;
                        }
                    }
                    if (free && distance <= reach)
                    {
                        // The furniture is still where it was found: carry it back to where it belongs.
                        carrier = i;
                        routine.BeginCarry(memories[i].PlayerSlot);
                    }
                    else
                    {
                        if (!furniture.Hidden && YawMath.Planar(investigateTargets[i] - routine.Position).magnitude > reach)
                        {
                            // M2.1 (11.4): the inhabitant never got to where the chair was (no path). It gives
                            // up and accepts the chair where it is now, instead of rediscovering it at once.
                            memories[i].SetPlayerSlot(furniture.Pose);
                            GiveUpCount++;
                        }
                        // Otherwise the furniture moved away (or someone else already carries it).
                        routine.CancelInvestigation();
                    }
                }
            }

            if (carrier < 0)
            {
                return;
            }
            InhabitantRoutine c = inhabitants[carrier].Routine;
            if (!furniture.Carried)
            {
                if (c.IsCarrying || c.JustPickedUp)
                {
                    // The pick up starts: attach the furniture where it stands. M5 (CONTRACT_M5_v3 15.4): on the floor height
                    // there (a platform), so the lift starts where the furniture is drawn.
                    carryFrom = Level.Floor.OnFloor(YawMath.Planar(furniture.transform.position));
                    carryFromYaw = furniture.Yaw;
                    carrySteps = 0;
                    putDownSteps = 0;
                    CarryCount++;
                    furniture.FollowCarrier(carryFrom, carryFromYaw);
                }
                else if (c.Mode != InhabitantMode.Carrying && c.Mode != InhabitantMode.Investigating)
                {
                    // The carry never started (a Pin cancelled it): free the reservation.
                    carrier = -1;
                }
                return;
            }
            if (c.JustPutDown)
            {
                FurniturePose back = c.CarryReturnPose;
                furniture.Release(back);
                // M2.1 (11.4): the whole household now remembers the chair where it was put back.
                for (int i = 0; i < memories.Length; i++)
                {
                    memories[i].SetPlayerSlot(furniture.Pose);
                }
                carrier = -1;
                putDownThisStep = true;
            }
            else if (!c.IsCarrying)
            {
                // The carry was cancelled (a Pin cancels any mode): the furniture drops where it is.
                furniture.Release(furniture.Pose);
                carrier = -1;
            }
        }

        // ----- 6. M4: the lamp (docs/CONTRACT_M4.md 2.3, amendment 9.1) -----

        /// <summary>
        /// An inhabitant in Routine who sees the switched-off lamp (Vision applies the dark range) and finds it where
        /// it belongs walks over and switches it on; out of place, the memory's discovery and carry back come first.
        /// The lamp comes on at the end of the beat if it is still within reach.
        /// </summary>
        private void StepLamp(GameRules rules)
        {
            FurnitureController furniture = Level.Furniture;
            LampLight lamp = furniture.Lamp;
            List<Inhabitant> inhabitants = Level.Inhabitants;
            bool anyPending = false;
            for (int i = 0; i < inhabitants.Count; i++)
            {
                InhabitantRoutine routine = inhabitants[i].Routine;
                if (routine.JustSwitchedOn)
                {
                    switchingOn[i] = false;
                    float reach = Tuning.InvestigateReach + Tuning.CarryReachMargin;
                    bool near = YawMath.Planar(furniture.transform.position - routine.Position).magnitude <= reach;
                    if (rules.Lamp && lamp != null && !lamp.On && near && !furniture.Carried)
                    {
                        lamp.SetOn(true);
                        SwitchOnCount++;
                        switchedOnThisStep = true;
                    }
                }
                else if (switchingOn[i] && routine.Mode != InhabitantMode.Investigating)
                {
                    // Interrupted (a startle, a pin): no longer on its way.
                    switchingOn[i] = false;
                }
                anyPending |= switchingOn[i];
            }
            if (!rules.Lamp || lamp == null || lamp.On || furniture.Carried || anyPending)
            {
                return;
            }
            for (int i = 0; i < inhabitants.Count; i++)
            {
                InhabitantRoutine routine = inhabitants[i].Routine;
                // M5: the dog never switches the lamp on (no memory).
                if (!seesPlayer[i] || routine.Mode != InhabitantMode.Routine || routine.IsFrozen || !routine.Personality.Memory)
                {
                    continue;
                }
                Observation o = observations[i];
                if (rules.DisplacementMemory && o != Observation.Confirmed && o != Observation.ExplainedByDecoy)
                {
                    continue;
                }
                switchingOn[i] = true;
                routine.BeginSwitchOn(YawMath.Planar(furniture.transform.position));
                return;
            }
        }

        // ----- 7. Noise -----

        private void StepNoise(GameRules rules, bool moving, float dt)
        {
            FurnitureController furniture = Level.Furniture;
            Vector3 source = YawMath.Planar(furniture.transform.position);
            // 3.2: a hop landing is a noise event, except on a silent floor (rug or soft room).
            // M5 wave 5B (CONTRACT_M5 4): every noise goes through the robots' hum; hops, clicks and rolls within its radius
            // are not emitted (and not counted), topples, creaks, barks and crashes always are.
            if (rules.Hearing && hoppedThisStep && !furniture.Carried && !hopSilent)
            {
                hopMasked = !EmitUnlessMasked(new NoiseEvent(source, Tuning.HopNoiseRadius, NoiseKind.Hop));
            }
            // M4 (CONTRACT_M4 2.1 to 2.4): the topple (it alerts like a hop, in Routine only), the click and the roll.
            // M4.1 (10.6): like the hop, each of them is silent on a rug or in a soft room.
            if (rules.Hearing && !furniture.Carried && !floorSilent)
            {
                if (toppledThisStep) // MUTATION:TOPPLE_NOISE
                {
                    ToppleNoiseCount++;
                    EmitUnlessMasked(new NoiseEvent(source, Tuning.ToppleNoiseRadius, NoiseKind.Topple));
                }
                if (clickedThisStep && EmitUnlessMasked(new NoiseEvent(source, Tuning.LampClickRadius, NoiseKind.Click)))
                {
                    ClickNoiseCount++;
                }
                if (rolledThisStep)
                {
                    rollMasked = !EmitUnlessMasked(new NoiseEvent(source, Tuning.RollNoiseRadius, NoiseKind.Roll));
                    if (!rollMasked)
                    {
                        RollNoiseCount++;
                    }
                }
            }
            // 3.3: the creak gauge. A creak is a loud noise event at the furniture. The gauge takes the level
            // time at the start of this step (Elapsed already counts it), so 5 s + 20 s creaks at 25.00 s.
            // M4: it pauses while the furniture is pinned under a sitter. M5 wave 5B: a shove is moving.
            float stepStart = (Steps - 1) * dt;
            if (rules.Creak && Creak.Step(dt, moving, furniture.Carried, stepStart, furniture.Pinned))
            {
                CreakCount++;
                CreakedThisStep = true;
                float creakRadius = furniture.Hidden ? Tuning.CreakRadius * Tuning.WardrobeCreakFactor : Tuning.CreakRadius; // MUTATION:MUFFLED_CREAK
                EmitUnlessMasked(new NoiseEvent(source, creakRadius, NoiseKind.Creak));
            }
            // M5: the barks decided in step 4, at their dogs (StepBarks already checked Rules.Hearing).
            EmitBarks();
            // M5 wave 5B (CONTRACT_M5 6): the load's fall, a crash at the clue that retargets like a creak.
            if (crashThisStep && rules.Hearing)
            {
                EmitUnlessMasked(new NoiseEvent(YawMath.Planar(ClueAt), Hearing.RadiusOf(NoiseKind.Crash), NoiseKind.Crash));
            }
        }

        /// <summary>
        /// 3.2: every inhabitant within the radius hears the event. Hearing triggers an alert only in mode
        /// Routine, or Alerted for a creak; frozen pinned inhabitants never hear.
        /// M5 (CONTRACT_M5 3, CONTRACT_M5_v3 15.5): the radius is scaled by each listener's hearing factor (the dog's is 0:
        /// it hears nothing), and an Alerted listener retargets on every kind of <see cref="Hearing.RetargetsAlerted"/> (a
        /// creak, a bark, a crash).
        /// </summary>
        private void Emit(NoiseEvent e)
        {
            Noise?.Invoke(e);
            List<Inhabitant> inhabitants = Level.Inhabitants;
            for (int i = 0; i < inhabitants.Count; i++)
            {
                InhabitantRoutine routine = inhabitants[i].Routine;
                if (routine.IsFrozen)
                {
                    continue;
                }
                float factor = routine.HearingFactor;
                if (factor <= 0f)
                {
                    continue;
                }
                InhabitantMode mode = routine.Mode;
                bool accepts = mode == InhabitantMode.Routine || (mode == InhabitantMode.Alerted && Hearing.RetargetsAlerted(e.Kind));
                if (accepts && Hearing.Hears(routine.Position, e, factor))
                {
                    routine.Alert(e.Position, e.Kind);
                    AlertCount++;
                }
            }
        }

        // ----- 9. Readability (M2.1, 11.6) -----

        /// <summary>
        /// Closed when unseen. Calm only when every inhabitant who sees the chair observes it and finds it in
        /// place (Confirmed) or explained by a decoy (M2.2, S1). Alarm otherwise: seen moving, seen out of place
        /// (Suspect, Discovery), or seen by an inhabitant who does not observe (investigating, carrying,
        /// startled, frozen pinned). Without the memory rule (M1), a seen and still chair is calm.
        /// M5 (CONTRACT_M5_v3 15.5): those are the humans (the watchers that count for the catch); a swinging leaf they see
        /// is seen moving. When only the dog sees, the eye is the dog's. Precedence: Alarm, Calm, Dog, Closed.
        /// </summary>
        private HudEye ComputeEye(GameRules rules, FurnitureController furniture, bool moving)
        {
            if (!Seen && !LeafSeen)
            {
                return SeenByDog ? HudEye.Dog : HudEye.Closed;
            }
            if ((State == PlayState.Playing && moving) || !Seen)
            {
                return HudEye.Alarm;
            }
            if (!rules.DisplacementMemory)
            {
                return HudEye.Calm;
            }
            List<Inhabitant> inhabitants = Level.Inhabitants;
            for (int i = 0; i < seesPlayer.Length && i < inhabitants.Count; i++)
            {
                PersonalityDef p = PersonalityOf(inhabitants[i]);
                if (!seesPlayer[i] || !p.CountsForCatch)
                {
                    continue;
                }
                Observation o = observations[i];
                if (o != Observation.Confirmed && o != Observation.ExplainedByDecoy)
                {
                    return HudEye.Alarm;
                }
            }
            return HudEye.Calm;
        }

        /// <summary>
        /// While the chair is on the floor and out of place: the rings around the decoys of its kind (the safe
        /// spots), and the ghost at the last seer's remembered pose unless a decoy already explains the chair.
        /// M4.1 (CONTRACT_M4 10.3): a stool on its side is out of place wherever it lies, but its ghost and rings are
        /// hidden: the HUD's tipped line says what to do (get up) instead of pointing at a place.
        /// </summary>
        private void UpdateGhost(GameRules rules, FurnitureController furniture)
        {
            OutOfPlace = false;
            AtDecoy = false;
            bool playing = State == PlayState.Playing;
            // M5 5B.1 (m14): the rings show the tolerance of the seer that judges (the tidy 0.4 m, the watchful 0.5 m).
            float tolerance = memories.Length > 0 ? memories[Mathf.Clamp(lastSeer, 0, memories.Length - 1)].Tolerance : Tuning.DisplacementTolerance;
            if (rules.DisplacementMemory && memories.Length > 0 && playing && !furniture.Carried)
            {
                FurniturePose here = furniture.Pose;
                FurnitureMemory seer = memories[Mathf.Clamp(lastSeer, 0, memories.Length - 1)];
                FurniturePose slot = seer.PlayerSlot;
                // M4: a stool lying on its side is out of place wherever it lies, and no decoy explains it.
                // M5: with the last seer's own tolerance (CONTRACT_M5 3: the tidy one notices 0.4 m).
                OutOfPlace = !FurnitureMemory.WithinTolerance(here, slot, seer.Tolerance) || furniture.Tipped;
                foreach (FurniturePose decoy in sameKindDecoys)
                {
                    AtDecoy |= !furniture.Tipped && FurnitureMemory.WithinTolerance(here, decoy, seer.Tolerance);
                }
            }
            bool lying = furniture.Tipped;
            Ghost?.ShowRings(OutOfPlace && !lying, tolerance);
            if (OutOfPlace && !AtDecoy && !lying)
            {
                // The product owner's 2026-11-18 report: the ghost copies the furniture's own visual, whatever its kind.
                Ghost?.Show(memories[Mathf.Clamp(lastSeer, 0, memories.Length - 1)].PlayerSlot, furniture.Size, furniture.Visual, tolerance);
            }
            else
            {
                Ghost?.Hide();
            }

            // M4 (CONTRACT_M4 3): the seat ghost and ring at the seat home, from the start of a sit-on-player walk until
            // the moment of sitting.
            SeatApproach = null;
            if (playing && rules.Sitting)
            {
                foreach (Inhabitant h in Level.Inhabitants)
                {
                    if (h != null && h.Routine != null && h.Routine.SitTargetsPlayer)
                    {
                        SeatApproach = h.Routine.SeatHome;
                        break;
                    }
                }
            }
            Ghost?.ShowSeat(SeatApproach, furniture.Size);
            // The office chair's stop ring (CONTRACT_M4 2.4) is drawn by FurnitureController from PredictedStop.
        }

        // ----- Win and lose -----

        private void Win()
        {
            State = PlayState.Won;
            Level.Furniture.CreakTremble = 0f;
            // Audio overhaul: the win jingle (the music fades out under it, MusicPlayer).
            Sfx?.PlayWin();
            if (IsLastLevel)
            {
                // M3: after the last level of levels.json, the win panel is the end screen.
                Hud?.ShowEnd(Elapsed);
                Menu?.OnEndScreen();
            }
            else
            {
                Hud?.ShowWin(Elapsed, HasNextLevel);
                // M8 touch redesign: Next level/Replay/Menu need a visible mouse cursor to be clickable.
                Menu?.OnWinScreen();
            }
            StateChanged?.Invoke(State);
        }

        private void Lose(LoseReason reason, int inhabitantIndex)
        {
            State = PlayState.Caught;
            LoseReason = reason;
            LostTo = inhabitantIndex >= 0 ? Level.Inhabitants[inhabitantIndex] : null;
            Level.Furniture.CreakTremble = 0f;
            foreach (Inhabitant inhabitant in Level.Inhabitants)
            {
                inhabitant.Startle(Level.Furniture.transform.position);
            }
            Sfx?.PlayCaught();
            Hud?.ShowFail(reason);
            // M8 touch redesign: Retry/Menu need a visible mouse cursor to be clickable; Retry is selected on the
            // next frame so Enter and gamepad A submit it too (docs/CONTRACT_M3.md 6, S2's pattern for the fail panel).
            Menu?.OnFailScreen();
            StateChanged?.Invoke(State);
        }

        // ----- Sounds -----

        // ----- M6 gameplay: the wardrobe, door memory, the doors the household opens (docs/CONTRACT_M6.md 2.5 to 2.7) -----

        /// <summary>
        /// M6 (CONTRACT_M6 2.5): the first wardrobe of the level (level order) that a furniture of its size (plus its load's
        /// height) fits in and whose entry zone holds its centre (WardrobeRule.CanEnter), or null. A tipped, carried or pinned
        /// furniture never enters.
        /// </summary>
        private PropDef WardrobeFor(FurnitureController furniture)
        {
            if (furniture == null || wardrobes.Count == 0 || furniture.Hidden || furniture.Tipped || furniture.Carried || furniture.Pinned)
            {
                return null;
            }
            Vector3 at = YawMath.Planar(furniture.transform.position);
            foreach (PropDef w in wardrobes)
            {
                if (WardrobeRule.CanEnter(w, at, furniture.Size, LoadExtraHeight))
                {
                    return w;
                }
            }
            return null;
        }

        /// <summary>
        /// M7 polish, presentation only: starts <paramref name="wardrobe"/>'s door animation (<see
        /// cref="WardrobeDoors.Begin"/>) the instant the entry or exit action starts, found by its index in
        /// <see cref="wardrobes"/> (the same order <see cref="LevelDef.Wardrobes"/> built <see
        /// cref="LevelInstance.Wardrobes"/> in). Does nothing for an index out of range or a wardrobe shown by a
        /// model visual (its WardrobeDoors entry is null).
        /// </summary>
        private void PlayWardrobeDoors(PropDef wardrobe, bool entering, FurnitureController furniture)
        {
            int index = wardrobes.IndexOf(wardrobe);
            if (index < 0 || Level == null || index >= Level.Wardrobes.Count)
            {
                return;
            }
            WardrobeDoors doors = Level.Wardrobes[index];
            if (doors != null)
            {
                doors.Begin(entering, furniture);
            }
            // Audio overhaul: the doors swing open now; they shut when the action ends (StepWardrobe).
            Sfx?.PlayWardrobe(PanToward(furniture.transform.position), true);
        }

        /// <summary>
        /// Step 1, after the furniture: the entry action ended (its 25 steps ran; ActionActive is false from the step after
        /// its last one): the furniture is hidden from this step on, before any vision. An entry cut short by a pin or a carry
        /// hides nothing. The exit action ended: the wardrobe is left.
        /// </summary>
        private void StepWardrobe(FurnitureController furniture)
        {
            if (Wardrobe != WardrobeStage.None && Wardrobe != WardrobeStage.Hidden && !furniture.ActionActive)
            {
                // Audio overhaul: the entry or exit action ended, the wardrobe's doors shut.
                Sfx?.PlayWardrobe(PanToward(furniture.transform.position), false);
            }
            if (Wardrobe == WardrobeStage.Entering && !furniture.ActionActive)
            {
                if (State == PlayState.Playing && !furniture.Carried && !furniture.Pinned)
                {
                    furniture.SetHidden(true);
                    Wardrobe = WardrobeStage.Hidden;
                    HideCount++;
                }
                else
                {
                    Wardrobe = WardrobeStage.None;
                    WardrobeProp = null;
                }
            }
            else if (Wardrobe == WardrobeStage.Leaving && !furniture.ActionActive)
            {
                Wardrobe = WardrobeStage.None;
                WardrobeProp = null;
            }
        }

        /// <summary>
        /// M6 (CONTRACT_M6 2.5): inhabitant <paramref name="i"/> sees its remembered spot: the sample box of the furniture's
        /// size at its player slot (on the floor there) is inside its view (its own range, no lamp factor, and half angle,
        /// unoccluded).
        /// </summary>
        private bool SeesSpot(int i)
        {
            Vision vision = i < visions.Length ? visions[i] : null;
            if (vision == null)
            {
                return false;
            }
            FurniturePose slot = memories[i].PlayerSlot;
            Vector3 floorAt = Level.Floor.OnFloor(YawMath.Planar(slot.Position));
            VisionMath.SamplePoints(floorAt, slot.Yaw, Level.Furniture.Size, Tuning.SampleInset, spotSamples);
            return vision.SeesAny(spotSamples);
        }

        /// <summary>
        /// Step 5, after the clue (CONTRACT_M6 2.6, the level's doorMemory and the memory rule on): every inhabitant with a door
        /// memory that observes this step (Routine or Alerted, not frozen) looks at each leaf whose state differs from its
        /// memory (Vision.SeesLeafBody: the leaf's 4 samples at its current angle). The first sighting of a mismatch is a
        /// Suspect: one discovery's gain on its own meter (suspicion 1 loses), the "hein ?". A mismatch it sees (a Suspect, or
        /// one already noticed) sends it to put the leaf back (InhabitantRoutine.BeginPutAway toward the door) unless someone is
        /// already on the way to that leaf.
        /// </summary>
        private void StepDoorMemory()
        {
            List<Inhabitant> inhabitants = Level.Inhabitants;
            for (int i = 0; i < inhabitants.Count && i < doorMemories.Length; i++)
            {
                DoorMemory memory = doorMemories[i];
                InhabitantRoutine routine = inhabitants[i].Routine;
                Vision vision = i < visions.Length ? visions[i] : null;
                if (memory == null || routine == null || vision == null || !routine.Personality.Memory)
                {
                    continue;
                }
                for (int k = 0; k < Level.Leaves.Count && k < memory.Count; k++)
                {
                    DoorLeaf leaf = Level.Leaves[k];
                    // A leaf as remembered changes nothing: no ray for it.
                    if (leaf == null || !CanObserve(routine) || !memory.Differs(k, leaf.Open))
                    {
                        continue;
                    }
                    DoorSighting sighting = memory.Observe(k, vision.SeesLeafBody(leaf), leaf.Open);
                    if (sighting == DoorSighting.Suspect)
                    {
                        DoorSuspectCount++;
                        DiscoveryCount++;
                        meters[i].AddDiscovery(); // MUTATION:DOOR_SUSPECT
                        Sfx?.PlayHein(PanToward(inhabitants[i].transform.position));
                        if (meters[i].Lost || meters[i].Value >= Tuning.SuspicionLose)
                        {
                            Lose(LoseReason.Suspicion, i);
                            return;
                        }
                    }
                    if ((sighting == DoorSighting.Suspect || sighting == DoorSighting.Known) && DoorFixer(k) < 0)
                    {
                        routine.BeginPutAway(DoorApproach(leaf.Geometry, routine.Position));
                        if (routine.Mode == InhabitantMode.Investigating)
                        {
                            doorFixers[i] = k;
                        }
                    }
                }
            }
        }

        /// <summary>The inhabitant on its way to put leaf <paramref name="leaf"/> back, or -1.</summary>
        private int DoorFixer(int leaf)
        {
            for (int i = 0; i < doorFixers.Length; i++)
            {
                if (doorFixers[i] == leaf)
                {
                    return i;
                }
            }
            return -1;
        }

        /// <summary>
        /// M6: where an inhabitant at <paramref name="from"/> walks to put a leaf back: on its side of the wall, on the doorway
        /// axis, Tuning.InhabitantDoorReach from the wall centre line (exactly on the line, the side the leaf does not swing into).
        /// </summary>
        private static Vector3 DoorApproach(DoorGeometry g, Vector3 from)
        {
            Vector3 normal = g.AlongX ? Vector3.forward : Vector3.right;
            float side = Vector3.Dot(YawMath.Planar(from - g.Center), normal);
            float sign = Mathf.Abs(side) > 1e-4f ? Mathf.Sign(side) : -Mathf.Sign(Vector3.Dot(g.Into, normal));
            return YawMath.Planar(g.Center) + normal * (sign * DoorStopDistance(g, sign));
        }

        /// <summary>
        /// M6 (CONTRACT_M6 2.7): how far from a leaf's wall centre line an inhabitant on the side of sign <paramref name="side"/>
        /// (the sign of its offset along the wall normal +z or +x) stops: Tuning.InhabitantDoorReach on the side the leaf does
        /// not swing into, and the door width plus Tuning.InhabitantRadius on the swing side (out of the leaf's sweep).
        /// </summary>
        public static float DoorStopDistance(DoorGeometry g, float side)
        {
            float into = g.AlongX ? g.Into.z : g.Into.x;
            return side * into > 0f ? g.Width + Tuning.InhabitantRadius : Tuning.InhabitantDoorReach;
        }

        /// <summary>
        /// Step 6, after the clue's put-away: an inhabitant sent to a leaf puts it back on the last step of its put-away beat
        /// (InhabitantRoutine.JustPutAway): the leaf swings back to the state its memory holds (DoorLeaf.BeginClose, or
        /// BeginOpen made by the household), and every door memory of the level remembers that state. Interrupted on its way
        /// (a startle, a pin, an alert never: it is Investigating), it gives the leaf up for the next one who sees it.
        /// </summary>
        private void StepDoorPutBack()
        {
            List<Inhabitant> inhabitants = Level.Inhabitants;
            for (int i = 0; i < inhabitants.Count && i < doorFixers.Length; i++)
            {
                int k = doorFixers[i];
                if (k < 0)
                {
                    continue;
                }
                InhabitantRoutine routine = inhabitants[i].Routine;
                if (routine != null && routine.JustPutAway && k < Level.Leaves.Count && doorMemories[i] != null)
                {
                    DoorLeaf leaf = Level.Leaves[k];
                    bool open = doorMemories[i].RemembersOpen(k);
                    if (open)
                    {
                        leaf.BeginOpen(true);
                    }
                    else
                    {
                        leaf.BeginClose();
                    }
                    if (leaf.Open == open)
                    {
                        RememberDoor(k, open);
                        DoorPutBackCount++;
                        householdDoorThisStep = leaf;
                    }
                    doorFixers[i] = -1;
                }
                else if (routine == null || routine.Mode != InhabitantMode.Investigating)
                {
                    doorFixers[i] = -1;
                }
            }
        }

        /// <summary>M6: the household changed leaf <paramref name="leaf"/>: every door memory of the level remembers it so.</summary>
        private void RememberDoor(int leaf, bool open)
        {
            foreach (DoorMemory memory in doorMemories)
            {
                memory?.Remember(leaf, open);
            }
        }

        /// <summary>
        /// Step 2, after the inhabitants (CONTRACT_M6 2.7): an inhabitant whose walk in progress reaches a closed leaf that
        /// carries openedByInhabitants (<see cref="WalkReachesLeaf"/>, on the walk's remaining corners) stops: its routine
        /// holds the next Tuning.InhabitantDoorStop (30 steps, InhabitantRoutine.Hold), while the leaf swings open from the
        /// next step (30 steps, made by the household: no samples), then it walks through; the leaf stays open, and every door
        /// memory remembers it open. Inhabitants in level order, leaves in leaf order, one leaf per inhabitant and step.
        /// </summary>
        private void StepHouseholdDoors()
        {
            if (householdLeaves == 0)
            {
                return;
            }
            List<Inhabitant> inhabitants = Level.Inhabitants;
            for (int i = 0; i < inhabitants.Count; i++)
            {
                InhabitantRoutine routine = inhabitants[i].Routine;
                if (routine == null || routine.Holding || routine.WalkCorners(walkCorners) == 0)
                {
                    continue;
                }
                for (int k = 0; k < Level.Leaves.Count; k++)
                {
                    DoorLeaf leaf = Level.Leaves[k];
                    if (leaf == null || (householdLeaves & (1 << k)) == 0 || leaf.Open || leaf.Swinging)
                    {
                        continue;
                    }
                    if (!WalkReachesLeaf(leaf.Geometry, routine.Position, walkCorners))
                    {
                        continue;
                    }
                    routine.Hold(Tuning.InhabitantDoorStop); // MUTATION:DOOR_STOP
                    leaf.BeginOpen(true);
                    HouseholdDoorOpenCount++;
                    householdDoorThisStep = leaf;
                    RememberDoor(k, true);
                    break;
                }
            }
        }

        private readonly List<Vector3> walkCorners = new List<Vector3>();

        /// <summary>
        /// M6 (CONTRACT_M6 2.7), the rule the audit replays, once per fixed step after the walk's move: follow the polyline
        /// from <paramref name="position"/> through <paramref name="corners"/> (the walk's remaining corners,
        /// InhabitantRoutine.WalkCorners) to its first point on the leaf's wall centre line inside the opening (within half the
        /// door width of the opening centre); true when there is one and the inhabitant stands at most
        /// <see cref="DoorStopDistance"/> from it (planar), on its side of the wall (0.5 m on the side the leaf does not swing
        /// into, width + 0.25 m on the swing side). A crossing of the same wall line outside the opening is another doorway.
        /// </summary>
        public static bool WalkReachesLeaf(DoorGeometry g, Vector3 position, IReadOnlyList<Vector3> corners)
        {
            if (g == null || corners == null)
            {
                return false;
            }
            float side = g.AlongX ? position.z - g.Line : position.x - g.Line;
            Vector3 a = YawMath.Planar(position);
            for (int c = 0; c < corners.Count; c++)
            {
                Vector3 b = YawMath.Planar(corners[c]);
                float sa = g.AlongX ? a.z - g.Line : a.x - g.Line;
                float sb = g.AlongX ? b.z - g.Line : b.x - g.Line;
                if (sa * sb <= 0f && !(sa == 0f && sb == 0f))
                {
                    Vector3 crossing = a + (b - a) * (sa / (sa - sb));
                    float along = g.AlongX ? crossing.x : crossing.z;
                    if (Mathf.Abs(along - g.Along) <= g.Width * 0.5f)
                    {
                        float distance = YawMath.Planar(crossing - position).magnitude;
                        return distance <= DoorStopDistance(g, side); // MUTATION:HOUSEHOLD_CROSS
                    }
                }
                a = b;
            }
            return false;
        }

        private void PlaySounds()
        {
            if (Sfx == null)
            {
                return;
            }
            if (hoppedThisStep)
            {
                // M5 wave 5B: a hop the robots' hum masked is felt, not heard (the silent floor's soft hop).
                if (hopSilent || hopMasked)
                {
                    Sfx.PlaySoftHop();
                }
                else
                {
                    Sfx.PlayHop();
                }
            }
            for (int i = 0; i < Level.Inhabitants.Count; i++)
            {
                int count = Level.Inhabitants[i].Routine.TelegraphCount;
                if (count != lastTelegraphCounts[i])
                {
                    lastTelegraphCounts[i] = count;
                    // M5: the dog's telegraph (a wake, a turn) is a sniff, not the human "hm ?".
                    if (PersonalityOf(Level.Inhabitants[i]).Barks)
                    {
                        Sfx.PlaySniff(PanToward(Level.Inhabitants[i].transform.position));
                    }
                    else
                    {
                        Sfx.PlayHm(PanToward(Level.Inhabitants[i].transform.position));
                    }
                }
            }
            // M5: the door's swing (a sound, not a noise event) and the barks.
            if (doorOpenedThisStep != null)
            {
                Sfx.PlayDoor(PanToward(doorOpenedThisStep.Geometry.Center));
            }
            if (householdDoorThisStep != null)
            {
                Sfx.PlayDoor(PanToward(householdDoorThisStep.Geometry.Center));
            }
            foreach (int i in barksThisStep)
            {
                if (i < Level.Inhabitants.Count)
                {
                    Sfx.PlayBark(PanToward(Level.Inhabitants[i].transform.position));
                }
            }
            // CONTRACT_M5 20: the dog barks at the furniture it holds (a sound only).
            Inhabitant holding = HoldingDog;
            if (holdBarkThisStep && holding != null)
            {
                Sfx.PlayBark(PanToward(holding.transform.position));
            }
            if (CreakedThisStep)
            {
                Sfx.PlayCreak();
            }
            if (putDownThisStep)
            {
                Sfx.PlayThump(PanToward(Level.Furniture.transform.position));
            }
            // M4: the bodies' sounds and the pratfall.
            FurnitureController furniture = Level.Furniture;
            float pan = PanToward(furniture.transform.position);
            if (toppledThisStep)
            {
                Sfx.PlayTopple(pan, floorSilent);
            }
            if (clickedThisStep || switchedOnThisStep)
            {
                Sfx.PlayClick(pan);
            }
            if (rolledThisStep)
            {
                Sfx.PlayRoll(floorSilent || rollMasked);
            }
            // M5 wave 5B: the load's crash, the rocking chair's creak, the robot's bump.
            if (crashThisStep)
            {
                Sfx.PlayCrash(PanToward(ClueAt));
            }
            if (rockedThisStep)
            {
                Sfx.PlayRockCreak(pan, rockTime);
            }
            if (contactThisStep)
            {
                Sfx.PlayBump(PanToward(contactAt));
            }
            if (pratfallThisStep >= 0 && pratfallThisStep < Level.Inhabitants.Count)
            {
                Sfx.PlayPratfall(PanToward(Level.Inhabitants[pratfallThisStep].transform.position));
            }
            // M4.1 (CONTRACT_M4 10.3): the tell grows from the tell speed (1.0 m/s) to full at the tip speed (1.3 m/s).
            bool rattle = State == PlayState.Playing && furniture.TellActive;
            const float band = Tuning.StoolTipSpeed - Tuning.StoolTellSpeed;
            Sfx.SetRattle(rattle, Mathf.Clamp01((furniture.PlanarSpeed - Tuning.StoolTellSpeed) / band));
        }

        private float PanToward(Vector3 position)
        {
            if (Camera == null)
            {
                return 0f;
            }
            Vector3 local = Camera.transform.InverseTransformPoint(position);
            return Mathf.Clamp(local.x / Mathf.Max(1f, local.magnitude), -1f, 1f);
        }

        private int IndexOf(Inhabitant inhabitant)
        {
            if (Level == null || inhabitant == null)
            {
                return -1;
            }
            int i = Level.Inhabitants.IndexOf(inhabitant);
            return i >= 0 && i < meters.Length ? i : -1;
        }
    }

    /// <summary>
    /// M4.1 (docs/CONTRACT_M4.md 10.7): when an inhabitant sits on the player furniture, its rule pose snaps to the seat
    /// home (GameState teleports it), and this slides its visual there from where it stood over the given time, eased.
    /// It runs after the LateUpdate of FurnitureController (which places the visual at the rule pose), keeps whatever
    /// offset the controller added (hop, tremble) and only replaces the base pose. It stops by itself when the furniture
    /// is moved again. Added on demand to the furniture's own GameObject: no Transform is created (probe step 09).
    /// </summary>
    [DefaultExecutionOrder(50)]
    public sealed class SeatSettleView : MonoBehaviour
    {
        private FurnitureController furniture;
        private Vector3 from;
        private float fromYaw;
        private Vector3 to;
        private float toYaw;
        private float elapsed;
        private float duration;

        /// <summary>True while the visual is still on its way to the seat home.</summary>
        public bool Active => furniture != null && elapsed < duration;

        /// <summary>The base pose the visual was given on the last frame (tests).</summary>
        public Vector3 VisualBase { get; private set; }

        public void Begin(FurnitureController target, Vector3 fromPosition, float fromYawDegrees, float seconds)
        {
            furniture = target;
            from = fromPosition;
            fromYaw = fromYawDegrees;
            to = target.transform.position;
            toYaw = target.Yaw;
            elapsed = 0f;
            duration = Mathf.Max(1e-3f, seconds);
            VisualBase = from;
            if (YawMath.Planar(to - from).sqrMagnitude < 1e-8f && Mathf.Abs(Mathf.DeltaAngle(fromYaw, toYaw)) < 1e-3f)
            {
                // Already home: nothing to slide.
                elapsed = duration;
                VisualBase = to;
            }
        }

        private void LateUpdate()
        {
            if (!Active || furniture.Visual == null)
            {
                return;
            }
            if ((furniture.transform.position - to).sqrMagnitude > 1e-8f)
            {
                // Moved since (released and driven, carried): the controller owns the visual again.
                elapsed = duration;
                return;
            }
            if (!GamePause.IsPaused)
            {
                elapsed += Time.deltaTime;
            }
            float t = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(elapsed / duration));
            Transform visual = furniture.Visual;
            Vector3 offset = visual.position - to;
            Vector3 basePosition = Vector3.Lerp(from, to, t);
            float yaw = Mathf.LerpAngle(fromYaw, toYaw, t);
            VisualBase = basePosition;
            visual.SetPositionAndRotation(basePosition + offset, Quaternion.Euler(0f, yaw - toYaw, 0f) * visual.rotation);
        }
    }

    /// <summary>
    /// M5 wave 5B (docs/CONTRACT_M5.md 5): the rocking chair's rock, visual only. The visual pitches about its base (the
    /// runners' contact under the seat) around its own right axis, front down first, swinging <see cref="Tuning.RockSwings"/>
    /// times by at most <see cref="Tuning.RockDegrees"/> and decaying to upright at the end of the rock. Like
    /// <see cref="SeatSettleView"/> it runs after FurnitureController's LateUpdate (which places the visual every frame) and
    /// adds its pitch to the pose the controller set. A pin or a carry stops it. Added on demand to the furniture's own
    /// GameObject: no Transform is created.
    /// </summary>
    [DefaultExecutionOrder(50)]
    public sealed class RockView : MonoBehaviour
    {
        private FurnitureController furniture;
        private float elapsed;
        private float duration;
        private float degrees;

        /// <summary>True while the visual rocks.</summary>
        public bool Active => furniture != null && elapsed < duration;

        /// <summary>The pitch added on the last frame, degrees (positive: the front dips).</summary>
        public float Pitch { get; private set; }

        public void Begin(FurnitureController target, float seconds, float amplitude)
        {
            furniture = target;
            elapsed = 0f;
            duration = Mathf.Max(1e-3f, seconds);
            degrees = amplitude;
            Pitch = 0f;
        }

        /// <summary>The pitch at <paramref name="progress"/> (0 to 1) of a rock of <paramref name="amplitude"/> degrees.</summary>
        public static float PitchAt(float progress, float amplitude)
        {
            float x = Mathf.Clamp01(progress);
            float decay = (1f - x) * (1f - x);
            return amplitude * decay * Mathf.Sin(2f * Mathf.PI * Tuning.RockSwings * x);
        }

        private void LateUpdate()
        {
            if (!Active || furniture.Visual == null)
            {
                Pitch = 0f;
                return;
            }
            if (furniture.Pinned || furniture.Carried)
            {
                elapsed = duration;
                Pitch = 0f;
                return;
            }
            if (!GamePause.IsPaused)
            {
                elapsed += Time.deltaTime;
            }
            Pitch = PitchAt(elapsed / duration, degrees);
            Transform visual = furniture.Visual;
            visual.rotation = visual.rotation * Quaternion.Euler(Pitch, 0f, 0f);
        }
    }
}
