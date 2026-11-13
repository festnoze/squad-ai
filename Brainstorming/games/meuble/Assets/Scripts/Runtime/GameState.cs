using System;
using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;

namespace Meuble
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
            }
        }

        /// <summary>Raised at the end of every fixed step, after every rule ran (the probe records from it).</summary>
        public event Action FixedStepped;

        // A creak warning shows the last CreakWarning seconds of the fill (3.3).
        private const float WarningStart = 1f - Tuning.CreakWarning / Tuning.CreakFillTime;

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
            Level = LevelBuilder.Build(Def);
            Rule.Reset();
            Creak.Reset();
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
            lastToppleCount = Level.Furniture.ToppleCount;
            lastToggleCount = Level.Furniture.ToggleCount;
            lastRollCount = Level.Furniture.RollCount;
            Level.Furniture.Rules = Rules ?? NoRules;

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
                memories[i] = new FurnitureMemory(spawn, decoyPoses, decoyKinds, Level.Furniture.Kind);
                meters[i] = new SuspicionMeter();
            }

            if (Camera != null)
            {
                Level.Furniture.CameraYaw = () => Camera.Yaw;
                Camera.SetTarget(Level.Furniture, Def.Player.Yaw);
            }
            WireRoutines(Rules ?? NoRules);
            if (Hud != null)
            {
                Hud.ShowLevel(Def);
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
            }
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
            if (body == null || !body.IsSeat || furniture.Carried || furniture.Tipped)
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

            // 1. The furniture: driven by input, or following its carrier. M4: it reads the rule switches itself.
            furniture.Rules = rules;
            if (furniture.Carried)
            {
                FollowCarrier(dt);
            }
            else
            {
                furniture.Step(dt, playing);
            }

            // 2. Inhabitants, each with its seat hook, the body's carry distance and the Sitting switch (M4).
            WireRoutines(rules);
            for (int i = 0; i < inhabitants.Count; i++)
            {
                inhabitants[i].Step(dt);
            }

            // 3. Vision of the player furniture, for every inhabitant. M2.1 (11.3): a decoy explains the chair
            // whether or not it is seen, so decoys need no raycast at all.
            bool seen = false;
            for (int i = 0; i < inhabitants.Count; i++)
            {
                Vision vision = visions[i];
                bool sees = vision != null && vision.Step(furniture);
                seesPlayer[i] = sees;
                seen |= sees;
            }
            Seen = seen;

            // 4. Exit and win, then the caught rule (win first, as in M1).
            if (playing)
            {
                Steps++;
                Elapsed = Steps * dt;
                Vector3 center = furniture.transform.position;
                bool exitCounts = Def.Exit.Contains(center) && !furniture.Carried && (!rules.ExitOnlyUnseen || !seen);
                // M4: a furniture pinned under a sitter never moves (FurnitureController), so it is never caught.
                bool moving = furniture.IsMoving /*MUTATION:SATON_MOVING*/ && !furniture.Carried;
                if (exitCounts)
                {
                    Win();
                }
                else if (Rule.Step(seen, moving, dt))
                {
                    Lose(LoseReason.SeenMoving, -1);
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

            // 6. Investigations and the carry, then the lamp switch-on (M4).
            if (State == PlayState.Playing)
            {
                StepInvestigations();
                StepLamp(rules);
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
                StepNoise(rules, dt);
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
            EyeState = ComputeEye(rules, furniture);
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
                Hud.SetSatOn(State == PlayState.Playing && furniture.Pinned);
                Hud.SetTipped(State == PlayState.Playing && furniture.LyingDown && !furniture.Carried);
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
                position = Vector3.Lerp(anchor, YawMath.Planar(back.Position), t);
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
                if (!CanObserve(routine))
                {
                    // The grace only measures an unbroken sighting (FurnitureMemory.ResetGrace).
                    memories[i].ResetGrace();
                    observations[i] = Observation.NotSeen;
                    continue;
                }
                Observation observation = memories[i].Observe(seesPlayer[i], pose, Time.fixedDeltaTime, lyingDown);
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
                    investigateTargets[i] = pose.Position;
                    routine.Investigate(pose.Position);
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
            if (furniture.Pinned != sitting)
            {
                // Pin(false) re-arms the neutral input wait (amendment 9.3): a key held through the dwell is ignored.
                furniture.Pin(sitting);
            }
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
                if (routine.Mode != InhabitantMode.Investigating)
                {
                    resolved[i] = false;
                }
                else if (routine.ReachedTarget && !resolved[i])
                {
                    resolved[i] = true;
                    float reach = Tuning.InvestigateReach + Tuning.CarryReachMargin;
                    float distance = YawMath.Planar(furniture.transform.position - routine.Position).magnitude;
                    bool free = carrier < 0 && !furniture.Carried;
                    if (free && distance <= reach)
                    {
                        // The furniture is still where it was found: carry it back to where it belongs.
                        carrier = i;
                        routine.BeginCarry(memories[i].PlayerSlot);
                    }
                    else
                    {
                        if (YawMath.Planar(investigateTargets[i] - routine.Position).magnitude > reach)
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
                    // The pick up starts: attach the furniture where it stands.
                    carryFrom = YawMath.Planar(furniture.transform.position);
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
                if (!seesPlayer[i] || routine.Mode != InhabitantMode.Routine || routine.IsFrozen)
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

        private void StepNoise(GameRules rules, float dt)
        {
            FurnitureController furniture = Level.Furniture;
            Vector3 source = YawMath.Planar(furniture.transform.position);
            // 3.2: a hop landing is a noise event, except on a silent floor (rug or soft room).
            if (rules.Hearing && hoppedThisStep && !furniture.Carried && !hopSilent)
            {
                Emit(new NoiseEvent(source, Tuning.HopNoiseRadius, NoiseKind.Hop));
            }
            // M4 (CONTRACT_M4 2.1 to 2.4): the topple (it alerts like a hop, in Routine only), the click and the roll.
            // M4.1 (10.6): like the hop, each of them is silent on a rug or in a soft room.
            if (rules.Hearing && !furniture.Carried && !floorSilent)
            {
                if (toppledThisStep) // MUTATION:TOPPLE_NOISE
                {
                    ToppleNoiseCount++;
                    Emit(new NoiseEvent(source, Tuning.ToppleNoiseRadius, NoiseKind.Topple));
                }
                if (clickedThisStep)
                {
                    ClickNoiseCount++;
                    Emit(new NoiseEvent(source, Tuning.LampClickRadius, NoiseKind.Click));
                }
                if (rolledThisStep)
                {
                    RollNoiseCount++;
                    Emit(new NoiseEvent(source, Tuning.RollNoiseRadius, NoiseKind.Roll));
                }
            }
            // 3.3: the creak gauge. A creak is a loud noise event at the furniture. The gauge takes the level
            // time at the start of this step (Elapsed already counts it), so 5 s + 20 s creaks at 25.00 s.
            // M4: it pauses while the furniture is pinned under a sitter.
            float stepStart = (Steps - 1) * dt;
            if (rules.Creak && Creak.Step(dt, furniture.IsMoving, furniture.Carried, stepStart, furniture.Pinned))
            {
                CreakCount++;
                CreakedThisStep = true;
                Emit(new NoiseEvent(source, Tuning.CreakRadius, NoiseKind.Creak));
            }
        }

        /// <summary>
        /// 3.2: every inhabitant within the radius hears the event. Hearing triggers an alert only in mode
        /// Routine, or Alerted for a creak; frozen pinned inhabitants never hear.
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
                InhabitantMode mode = routine.Mode;
                bool accepts = mode == InhabitantMode.Routine || (mode == InhabitantMode.Alerted && e.Kind == NoiseKind.Creak);
                if (accepts && Hearing.Hears(routine.Position, e))
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
        /// </summary>
        private HudEye ComputeEye(GameRules rules, FurnitureController furniture)
        {
            if (!Seen)
            {
                return HudEye.Closed;
            }
            if (State == PlayState.Playing && furniture.IsMoving)
            {
                return HudEye.Alarm;
            }
            if (!rules.DisplacementMemory)
            {
                return HudEye.Calm;
            }
            for (int i = 0; i < seesPlayer.Length; i++)
            {
                if (!seesPlayer[i])
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
            if (rules.DisplacementMemory && memories.Length > 0 && playing && !furniture.Carried)
            {
                FurniturePose here = furniture.Pose;
                FurniturePose slot = memories[Mathf.Clamp(lastSeer, 0, memories.Length - 1)].PlayerSlot;
                // M4: a stool lying on its side is out of place wherever it lies, and no decoy explains it.
                OutOfPlace = !FurnitureMemory.WithinTolerance(here, slot) || furniture.Tipped;
                foreach (FurniturePose decoy in sameKindDecoys)
                {
                    AtDecoy |= !furniture.Tipped && FurnitureMemory.WithinTolerance(here, decoy);
                }
            }
            bool lying = furniture.Tipped;
            Ghost?.ShowRings(OutOfPlace && !lying);
            if (OutOfPlace && !AtDecoy && !lying)
            {
                Ghost?.Show(memories[Mathf.Clamp(lastSeer, 0, memories.Length - 1)].PlayerSlot, furniture.Size);
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
            if (IsLastLevel)
            {
                // M3: after the last level of levels.json, the win panel is the end screen.
                Hud?.ShowEnd(Elapsed);
                Menu?.OnEndScreen();
            }
            else
            {
                Hud?.ShowWin(Elapsed, HasNextLevel);
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
            StateChanged?.Invoke(State);
        }

        // ----- Sounds -----

        private void PlaySounds()
        {
            if (Sfx == null)
            {
                return;
            }
            if (hoppedThisStep)
            {
                if (hopSilent)
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
                    Sfx.PlayHm(PanToward(Level.Inhabitants[i].transform.position));
                }
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
                Sfx.PlayRoll(floorSilent);
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
}
