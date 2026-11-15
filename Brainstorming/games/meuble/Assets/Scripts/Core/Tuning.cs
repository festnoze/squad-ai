namespace Meuble.Core
{
    /// <summary>
    /// Every M1 constant of docs/PRD.md, in one place. Units: meters, seconds, degrees.
    /// A value changed here must be written back to the PRD (the PRD is the contract).
    /// </summary>
    public static class Tuning
    {
        // Simulation (PRD section 2).
        public const float FixedStep = 0.02f;

        // Camera (PRD 3.1).
        public const float OrbitDistance = 4.0f;
        public const float OrbitDistanceMin = 2.5f;
        public const float OrbitDistanceMax = 6.0f;
        public const float PitchMin = 15f;
        public const float PitchMax = 75f;
        public const float PitchDefault = 40f;
        public const float MouseSensitivity = 0.12f;
        public const float CameraTargetHeight = 0.5f;
        public const float CameraSmoothTime = 0.12f;

        // Chair movement (PRD 3.2).
        public const float ChairMaxSpeed = 1.5f;
        public const float ChairAcceleration = 10f;
        public const float ChairTurnRate = 360f;
        public const float ChairControllerRadius = 0.28f;
        public const float ChairControllerHeight = 0.90f;
        public const float HopHeight = 0.04f;
        public const float HopFrequency = 14f;
        public const float HopRockDegrees = 4f;

        // Moving predicate (PRD 3.3).
        public const float MovingSpeedThreshold = 0.05f;
        public const float MovingYawRateThreshold = 3f;

        // Vision (PRD 4.1).
        public const float EyeHeight = 1.60f;
        public const float ViewRange = 10f;
        public const float ViewHalfAngle = 55f;
        public const float SampleInset = 0.03f;
        public const int SampleCount = 5;

        // Caught rule (PRD 4.2).
        public const float CaughtGrace = 0.20f;

        // Fairness feedback (PRD 4.3).
        public const int ConeRayCount = 40;
        public const float TelegraphDuration = 0.6f;
        public const float TelegraphMinTurn = 30f;

        // Inhabitant routine (PRD 5.1).
        public const float WalkSpeed = 1.2f;
        public const float BodyTurnRate = 180f;
        public const float HeadTurnRate = 200f;
        public const float HeadYawLimit = 80f;

        /// <summary>
        /// Body radius of the inhabitant. Not given by the PRD: it only sizes the collider and the
        /// capsule sweep of the level audit (section 10.3).
        /// </summary>
        public const float InhabitantRadius = 0.25f;
        public const float InhabitantHeight = 1.75f;

        // Level audit (PRD 10.3).
        public const float AuditCellSize = 0.5f;
        public const float AuditMinUnseenFraction = 0.25f;

        // ----- M2 (docs/CONTRACT_M2.md section 2) -----

        // Displacement memory and suspicion (PRD 4.4).
        public const float DisplacementTolerance = 0.75f;
        /// <summary>UNUSED since M2.1: the tolerance is position only (CONTRACT_M2 section 11.2).</summary>
        public const float DisplacementToleranceYaw = 45f;
        public const float SuspicionPerDiscovery = 0.34f;
        public const float SuspicionDecayPerSecond = 0.02f;
        public const float SuspicionLose = 1f;
        /// <summary>M2.1: seen out of place this long (continuously) before it is a discovery.</summary>
        public const float DiscoveryGrace = 0.20f;

        // Hearing (PRD 4.5). Not given by the PRD: tuned in M2.
        public const float HopNoiseRadius = 2.0f;

        // Creak (PRD 4.6).
        public const float CreakFillTime = 20f;
        public const float CreakDrainTime = 10f;
        public const float CreakWarning = 3f;
        public const float CreakRadius = 7f;
        public const float CreakStartDelay = 5f;
        public const float AlertLookDuration = 2f;
        public const float CreakTrembleDistance = 0.012f;
        public const float CreakTrembleDegrees = 1.5f;

        // Investigate and carry back (PRD 4.4, 5.2).
        public const float InvestigateReach = 0.8f;
        /// <summary>BeginCarry when the furniture center is within InvestigateReach + this margin (CONTRACT_M2 3.4).</summary>
        public const float CarryReachMargin = 0.1f;
        public const float CarrySpeed = 1.0f;
        public const float PickUpDuration = 0.5f;
        public const float PutDownDuration = 0.5f;
        public const float CarryForward = 0.45f;
        public const float CarryHeight = 0.30f;

        // Navigation (PRD 11 M2: navmesh pathfinding).
        public const float NavAgentRadius = 0.25f;
        public const float NavAgentHeight = 1.75f;

        // Level audit extension (PRD 11 M2 gate).
        public const float AuditMaxWait = 8f;

        // Navigation details (runtime-world, M2).
        public const float NavAgentClimb = 0.1f;   // a 0.75 m table top must never become walkable
        public const float NavAgentSlope = 30f;
        public const float NavSnapDistance = 1f;
        public const float NavVoxelSize = 0.05f;   // radius / 5: the default 0.083 m bends the M1 walks
        public const float NavBoundsBottom = -0.5f;
        public const float NavBoundsTop = 3f;

        // Level geometry (runtime-world, M2).
        public const float DoorTopDefault = 2.1f;
        public const float ExitBlockerDistance = 0.6f;
        public const float ExitBlockerHeight = 2f;
        public const float RugHeight = 0.01f;
        public const float GardenSize = 40f;

        // Budgets of PRD 7.4, shared by the audit and the built player probe.
        public const int BudgetRenderers = 120;
        public const int BudgetMaterials = 24;
        public const int BudgetFurnitureTriangles = 400;
        public const int BudgetInhabitantTriangles = 3000;
        public const int BudgetInhabitantBones = 40;
        public const int BudgetLevelTriangles = 60000;

        // ----- M4 (docs/CONTRACT_M4.md section 9.6) -----
        public const float StoolTipSpeed = 1.3f;
        // M4.1 (CONTRACT_M4 10.3): the tell starts here and the fast stage ends here, 0.25 s below the tip speed.
        public const float StoolTellSpeed = 1.0f;
        // M4.1: a wall hit tips the stool only within this angle of head-on.
        public const float StoolHeadOnDegrees = 30f;
        // M4.1: FurnitureController's wall-blocked test and glide end, InputReader's trigger threshold.
        public const float BlockedFraction = 0.25f;
        public const float GlideEpsilon = 1e-4f;
        public const float TriggerHeld = 0.5f;
        public const float StoolHighAccel = 1.2f;
        public const float StoolFallTime = 0.3f;
        public const float StoolRightTime = 0.4f;
        public const float StoolLeanDegrees = 8f;
        public const float ToppleNoiseRadius = 3.5f;
        public const float LampOffLight = 0.4f;
        // M4.1 (CONTRACT_M4 10.4): 15 steps, so a toggle seen for its whole duration is caught with a margin.
        public const float LampToggleTime = 0.3f;
        public const float LampClickRadius = 2.5f;
        public const float LampSwitchOnTime = 0.5f;
        public const float OfficeChairStopTime = 0.4f;
        public const float RollNoiseRadius = 1.2f;
        public const float RollNoiseInterval = 0.3f;
        public const float CarefulFactor = 0.5f;
        public const float SitEyeHeight = 1.15f;
        public const float SitEyeRiseTime = 0.5f;
        public const float SeatHomeTolerance = 0.75f;
        public const float PratfallTime = 1.0f;
        public const int AuditStopSamples = 4;
        /// <summary>A door must be at least 2 x body radius + this wide (CONTRACT_M4 9.11).</summary>
        public const float DoorClearanceMargin = 0.1f;

        // ----- M3 presentation values (docs/CONTRACT_M3.md), moved here at integration -----
        // Sfx.cs
        public const float SfxHopMix = 0.27f;
        public const float SfxPivotScrapeMix = 0.31f;
        public const float SfxPickUpScrapeMix = 0.46f;
        public const float SfxCreakMix = 0.97f;
        public const float SfxWarningCreakMix = 0.31f;
        public const float SfxThumpMix = 0.92f;
        public const float SfxCaughtMix = 0.96f;
        public const float SfxHeinMix = 1f;
        public const float SfxFootstepMix = 0.69f;
        public const float SfxRoomToneMix = 0.062f;
        public const float SfxClockMix = 0.038f;
        public const float SfxUiClickMix = 0.48f;
        public const float SfxPivotYawRate = 180f;
        public const float SfxPivotMaxSpeed = 0.75f;
        // Sfx.cs, M4 synthesized cues (volumes before the mix scale)
        public const float SfxSoftRollVolume = 0.25f;
        public const float SfxRattleLoopSeconds = 1f;
        public const float SfxToppleSynthVolume = 0.62f;
        public const float SfxClickSynthVolume = 0.4f;
        public const float SfxRollSynthVolume = 0.24f;
        public const float SfxRattleSynthVolume = 0.22f;
        public const float SfxPratfallSynthVolume = 0.6f;
        // FootstepAudio.cs
        public const float FootstepCarryPitch = 0.92f;
        public const float FootstepPitchJitter = 0.06f;
        public const float FootstepVolumeJitter = 0.15f;
        // InhabitantRig.cs
        public const float RigCrossFadeSeconds = 0.15f;
        public const float RigTelegraphRollDegrees = 12f;
        public const float RigWalkCycleMeters = 1.6f;
        public const float RigFootContactCycle = 0.32f;
        public const float RigBendDegrees = 35f;
        public const float RigCarryUpperArmPitch = 50f;
        public const float RigCarryLowerArmPitch = 15f;
        public const float RigCarryArmSplay = 8f;
        public const float RigBrowFlat = 6f;
        public const float RigBrowFrown = -24f;
        public const float RigBrowFrownDrop = 0.006f;
        public const float RigPratfallDrop = 0.5f;
        public const float RigPratfallPitchDegrees = 28f;
        // Inhabitant.cs, the pratfall pose of the procedural body
        public const float PratfallInRate = 7f;
        public const float PratfallOutRate = 2.5f;
        public const float ProceduralPratfallDrop = 0.35f;
        public const float ProceduralPratfallArms = 95f;
        // Main.cs
        public const float LookSunIntensity = 1.3f;
        public const float LookBloomThreshold = 1.25f;
        public const float LookBloomIntensity = 0.55f;
        // OrbitCamera.cs
        public const float ShowcaseSpeed = 3f;
        public const float ShowcasePitch = 42f;
        public const float ShowcaseTilt = 14f;
        // LevelBuilder.cs
        public const float BaseboardHeight = 0.08f;
        public const float BaseboardDepth = 0.015f;
        public const float WindowPaneEmission = 1.6f;
        // ModelKit.cs
        public const float ModelSmoothness = 0.2f;

        // ----- M4.2 textures (TextureLibrary, PrimitiveKit.Detail, ModelKit) -----
        // Every detail texture is a linear grayscale multiplier of the palette colour with this exact mean, and
        // every URP Lit material's base colour is the palette colour divided by it (in linear): a renderer shows its
        // palette colour on average, with or without a detail. Highlights are capped at 1.0 (dark details on a flat
        // base), so the brightest texel is this mean times 1.0625: a sunlit trim stays under the bloom threshold.
        public const float DetailMean = 240f / 255f;
        // Metres covered by one repeat of each detail texture, in world space.
        public const float DetailTileWood = 1.0f;
        public const float DetailTileParquet = 1.8f;
        public const float DetailTilePlaster = 2.0f;
        public const float DetailTileUpholstery = 0.55f;
        public const float DetailTileLinen = 0.45f;
        public const float DetailTileCarpet = 0.7f;
        // The Kenney Furniture Kit's own UVs: a planar projection per face at 39.37 UV per native unit (inches per
        // metre), measured on every Kenney GLB of the project. Read by the M4.2 probe as a premise.
        public const float KenneyUvPerNativeUnit = 39.37f;
        // Tests (probe steps 22c to 22f): a texture's measured mean within this of DetailMean; a renderer's detail
        // repeat within this fraction of its surface's tile.
        public const float DetailMeanTolerance = 0.01f;
        public const float DetailTileTolerance = 0.1f;
            // ----- M5 (docs/CONTRACT_M5.md 13 and 16; v3 15.x) -----
        // Doors (v3 15.1, 15.2).
        public const int DoorAreaBase = 3;
        public const float LeafThickness = 0.04f;
        public const float LeafSampleInset = 0.1f;
        public const int LeafSampleCount = 4;
        public const float DoorSwingDegrees = 90f;
        public const float DoorReach = 0.85f;
        public const float DoorOpenTime = 0.6f;
        public const int MaxLeavesPerLevel = 2;
        // The split level (v3 15.4, v5 16.6).
        public const float PlatformMinHeight = 0.6f;
        public const float PlatformMaxHeight = 1.0f;
        public const float RampMaxSlope = 20f;
        public const float RailingHeight = 0.9f;
        public const float RailingThickness = 0.05f;
        public const float ArmchairPassageWidth = 1.5f;
        public const float PassageWidth = 1.2f;
        // The dog (v3 4, 15.5).
        public const float DogEyeHeight = 0.35f;
        public const float BarkRadius = 6f;
        public const float BarkCooldown = 3f;
        public const float WakeTelegraph = 0.6f;
        public static readonly UnityEngine.Color DogConeColor = new UnityEngine.Color(0.25f, 0.85f, 0.85f, 1f);
        public const int BudgetPetBones = 46;
        // Several inhabitants.
        public const float WatcherSeparation = 0.6f;
        public const int MaxHumans = 3;
        // The robot (CONTRACT_M5 4, 16.8).
        public const float RobotSpeed = 0.4f;
        public const float RobotRadius = 0.17f;
        public const float RobotHeight = 0.09f;
        public const float RobotHumRadius = 2.5f;
        public const float RobotPushDistance = 0.25f;
        public const float RobotPushTime = 0.5f;
        public const float RobotClearance = 1f;
        // The rocking chair (CONTRACT_M5 5, 16.9).
        public const float RockTime = 0.8f;
        public const float RockCarefulTime = 0.4f;
        public const float RockDegrees = 9f;
        // The load (CONTRACT_M5 6, 16.5: the kinematic rule; the spring is the visual sway only).
        public const float LoadWindow = 0.5f;
        public const float LoadFallDeltaV = 1.8f;
        public const float LoadHeight = 0.25f;
        public const float LoadSwayGain = 2.5f;
        public const float LoadSwaySpring = 80f;
        public const float LoadSwayDamping = 9f;
        public const float BalanceWarning = 0.75f;
        public const float CrashRadius = 6f;
        public const float PutAwayTime = 0.6f;
        // Houses, budgets and the camera (PRD 7.4 v1.7, CONTRACT_M5 9, 16.11).
        public const int BudgetHouseRenderers = 160;
        public const int BudgetHouseMaterials = 32;
        public const int HouseBudgetRooms = 5;
        public const float CameraMaxDistanceHouse = 16f;
        public const float FrameTimeFailMs = 33f;
        // The audit (CONTRACT_M5 16.3).
        public const int AuditOpenSamples = 6;
        public const float AuditHorizonM5 = 300f;
        public const float AuditLevelWarnSeconds = 240f;
        public const float AuditSweepStep = 3f;
        public const float PlaythroughTimeScale = 8f;

        // ----- M5 ui-save (CONTRACT_M5_v3 6 and 15.7, CONTRACT_M5 16.10): the save writes, the level select grid. -----
        /// <summary>File.Replace attempts before the delete-then-move fallback.</summary>
        public const int SaveReplaceTries = 3;
        /// <summary>Milliseconds between two File.Replace attempts.</summary>
        public const int SaveReplaceRetryMs = 50;
        /// <summary>Cards per row of the level select (3 rows of 6 hold the 17 levels).</summary>
        public const int LevelSelectColumns = 6;

        // ----- M5 audit (CONTRACT_M5 16.3): the deterministic budget of one level, set by the audit agent. -----
        /// <summary>
        /// Search nodes expanded per level, every search included; above it the level fails. Measured: worst M4 level 9.2
        /// million (level 3, sweep and slack included); a 6 room mock house with 4 watchers 8.5 million, with sweep and slack
        /// 9.4 million. Wave 5B: level 17 (7 rooms, 4 watchers, 2 closed leaves, a robot and a vase) 51 million over its main
        /// schedule, its pet lesson and its load lesson (22.8, 22.7 and 5.4 million); level 12 15 million. The memory of one
        /// search is bounded apart (<see cref="AuditSearchNodeCap"/>).
        /// </summary>
        public const int AuditNodeCap = 80000000;
        /// <summary>
        /// Occlusion rays cast per level (batched, cached); above it the level fails. Measured worst M4 level: 0.24 million
        /// (level 6). To revisit once levels 8 to 17 exist.
        /// </summary>
        public const int AuditRayCap = 20000000;

        // ----- M5 house (docs/CONTRACT_M5_v3.md 15.1 to 15.4, CONTRACT_M5.md 16.6 and 16.10) -----
        /// <summary>
        /// The longest interior side of the largest level of M1 to M4 (levels 6 and 7: 10 m). A house up to this side keeps
        /// the orbit zoom bound <see cref="OrbitDistanceMax"/>; a longer one scales it by its side over this, up to
        /// <see cref="CameraMaxDistanceHouse"/>.
        /// </summary>
        public const float CameraHouseReferenceSide = 10f;
        /// <summary>The gap between the top of a door leaf and its door head (the leaf never rubs the frame when it swings).</summary>
        public const float LeafTopGap = 0.01f;
        /// <summary>
        /// Extra depth of a leaf doorway's NavMesh area box beyond each wall face, so the area covers whole voxel rows of
        /// the threshold however the voxel grid falls (two NavVoxelSize).
        /// </summary>
        public const float DoorAreaOverhang = 0.1f;
        /// <summary>
        /// The validator's tolerance when it checks that a footprint does not straddle two floor heights or that a ramp end
        /// is flush (metres).
        /// </summary>
        public const float FloorFlushTolerance = 0.01f;
        /// <summary>
        /// The dog's capsule collider (the level builder): a dog sized body instead of the human 1.75 m by 0.25 m one, its top
        /// a little above its eye (Tuning.DogEyeHeight + 0.15).
        /// </summary>
        public const float DogCapsuleRadius = 0.2f;
        public const float DogCapsuleHeight = 0.5f;
        /// <summary>
        /// Wave 5A.1 (critique m15): the margin added on every side of a door leaf's box when the wall fader tests whether a
        /// sight line from the camera to the player furniture crosses it (the furniture is drawn a little beyond its sight
        /// points). Metres.
        /// </summary>
        public const float LeafFadeMargin = 0.05f;

        // ----- M5 watchers (docs/CONTRACT_M5.md 3, 16.11; CONTRACT_M5_v3.md 4 and 15.5) -----
        /// <summary>
        /// Metres the dog walks per Walk clip cycle (InhabitantRig's stride for pets): the stance feet of the Shiba's
        /// "Walk" travel 2.7 native units per cycle (measured on the GLB from its IK foot bones), times its fit scale 0.130
        /// (its eyes, 2.69 native units high in Idle, at DogEyeHeight). A small dog's quick patter: 4 cycles a second at 1.4 m/s.
        /// </summary>
        public const float DogWalkCycleMeters = 0.35f;
        /// <summary>Normalized Walk clip time of the dog's first foot contact (its hind feet land at 0.83 and 0.33).</summary>
        public const float DogFootContactCycle = 0.83f;
        /// <summary>The sleep "z" and the wake telegraph marker of a sleeping watcher, metres (the "?" is 0.34).</summary>
        public const float SleepMarkerSize = 0.3f;
        /// <summary>Blinks per second of the marker during the wake telegraph (the eye still closed).</summary>
        public const float WakeMarkerBlinkRate = 6f;
        /// <summary>
        /// The dog's alarm hue (CONTRACT_M5 17): while it sees the furniture its fan and chevron turn this vivid pure cyan,
        /// clearly apart from the softer <see cref="DogConeColor"/> of its calm fan. Yellow and red stay the humans' calm and
        /// alarm, deep blue the x-ray. Over every floor of a level with a dog, the calm and alarm fans differ at least as much
        /// as a human's (ModelM5Tests measures it in CIE Lab).
        /// </summary>
        public static readonly UnityEngine.Color DogConeAlarmColor = new UnityEngine.Color(0f, 1f, 1f, 1f);
        /// <summary>
        /// The dog's floor cone: the alpha of its calm fan (in DogConeColor) and of its alarm fan (in DogConeAlarmColor);
        /// humans: 0.20 and 0.30. The alarm is more opaque than a human's so it reads over the wood floors.
        /// </summary>
        public const float DogConeCalmAlpha = 0.20f;
        public const float DogConeAlarmAlpha = 0.5f;
        /// <summary>
        /// The dog's fan while a lamp is dark: its colour (calm or alarm) times this, as the humans' dimmer fans, at the dark
        /// calm alpha or the dark alarm alpha.
        /// </summary>
        public const float DogConeDarkShade = 0.8f;
        public const float DogConeDarkAlpha = 0.13f;
        public const float DogConeDarkAlarmAlpha = 0.36f;
        /// <summary>
        /// The dog's facing chevron while calm: DogConeColor times this (a deep teal); while it sees the furniture it takes
        /// DogConeAlarmColor. The two differ in lightness, as the humans' yellow and red chevrons differ in hue.
        /// </summary>
        public const float DogChevronCalmShade = 0.6f;
        /// <summary>The dog's synthesized patter (FootstepAudio): two paw ticks this far apart (seconds), variants, gain.</summary>
        public const float DogPatterGap = 0.055f;
        public const int DogPatterVariants = 3;
        public const float DogPatterGain = 0.55f;
        /// <summary>
        /// The character palette (CONTRACT_M5 16.11), sRGB on ModelMath's 1/64 grid: every human and the dog map onto these
        /// 8 shared colours, plus one clothes tint per personality (PersonalityDef.Tint), so 3 humans and a dog add at most 12
        /// materials. Index 0 is ModelMath.NearBlack; 1 and 3 are the M3 man's own skin and trousers as M4 quantised them, so a
        /// default inhabitant of levels 1 to 7 keeps exactly its M4 colours. Order: near-black, mid skin, light skin, denim,
        /// blond, grey, white, plum. None is red (PRD 7.2).
        /// </summary>
        public static readonly UnityEngine.Color[] CharacterPalette =
        {
            new UnityEngine.Color(12f / 64f, 12f / 64f, 12f / 64f, 1f),
            new UnityEngine.Color(23f / 64f, 19f / 64f, 17f / 64f, 1f),
            new UnityEngine.Color(42f / 64f, 35f / 64f, 26f / 64f, 1f),
            new UnityEngine.Color(16f / 64f, 19f / 64f, 25f / 64f, 1f),
            new UnityEngine.Color(32f / 64f, 27f / 64f, 13f / 64f, 1f),
            new UnityEngine.Color(34f / 64f, 34f / 64f, 34f / 64f, 1f),
            new UnityEngine.Color(55f / 64f, 55f / 64f, 55f / 64f, 1f),
            new UnityEngine.Color(29f / 64f, 14f / 64f, 20f / 64f, 1f),
        };

        // ----- M5 game (docs/CONTRACT_M5_v3.md 3 and 4): the synthesized door, bark and sniff (Sfx, times its mix scale). -----
        /// <summary>The door's swing (latch and hinge), near the put-down thump.</summary>
        public const float SfxDoorSynthVolume = 0.55f;
        /// <summary>The dog's bark: as loud as the caught sting, it is the dog's alarm.</summary>
        public const float SfxBarkSynthVolume = 0.6f;
        /// <summary>The dog's sniff, its telegraph: a little under the human "hm ?" (0.55) it replaces.</summary>
        public const float SfxSniffSynthVolume = 0.45f;

        // ----- M5 probe (CONTRACT_M5 9 and 17): the built player's frame time per level (Probe.FrameTimes). -----
        /// <summary>Rendered frames timed per level at its start view (median and 95th percentile; at least 60).</summary>
        public const int ProbeFrameSamples = 90;
        /// <summary>Frames let pass after the level card faded and before the timing starts.</summary>
        public const int ProbeFrameWarmup = 10;
        /// <summary>Real seconds the probe waits at most for the level card to fade (Hud: 4 s held, then 1 s fade).</summary>
        public const float ProbeCardWaitSeconds = 8f;

        // ----- M5B core (docs/CONTRACT_M5.md 16.5): MotionProfile's slide samples. -----
        /// <summary>
        /// Fixed steps per audit sample (0.1 s, the level audit's own sample): MotionProfile.SlideSamples rounds the
        /// slide steps up to it (the office chair's 19 glide steps are Tuning.AuditStopSamples, 4).
        /// </summary>
        public const int MotionSampleSteps = 5;

        // ----- M5B watchers (docs/CONTRACT_M5.md 4, 6, 16.8, 16.11 and 17; critique m14, m20) -----
        /// <summary>
        /// m14: on a level with a platform or a ramp each floor cone ray is cut every this many metres of its watcher's range
        /// (VisionConeView.Radial), so the fan lies on the platform top instead of passing under it.
        /// </summary>
        public const float ConeRadialStep = 0.25f;
        /// <summary>
        /// m20: the casts at most per cone ray when the eye is below the furniture top (the dog): each pass goes on past a
        /// cover lower than the top, toward the farthest top seen over it.
        /// </summary>
        public const int ConeSupersetPasses = 4;
        /// <summary>The robot vacuum's status light pulses this many times a second (visual only).</summary>
        public const float RobotLightPulseRate = 0.8f;
        /// <summary>
        /// CONTRACT_M5 17 (draw calls are material slots): when true, a tinted character's slots of one material and one detail
        /// merge into one (ModelKit.MergeSlots): watchful, teen, tidy and the dog draw 25 slots instead of 39 (brows included),
        /// level 17's granny, teen, tidy and dog 24 instead of 34. Off until probe step 22c reads a merged slot through
        /// ModelKit.SourceSlots and ModelKit.SourceMeshOf (it asserts the instance draws the catalog's own mesh).
        /// </summary>
        public static readonly bool CharacterSlotMerge = false;

        // ----- M5B game (docs/CONTRACT_M5.md 4, 5, 6, 16.5, 16.8 and 16.9): the robot, the rock and the load in play. -----
        /// <summary>The fallen load's clue is seen at this height above the floor (its one vision sample), metres.</summary>
        public const float ClueSampleHeight = 0.1f;
        /// <summary>The fallen load lands this far past the footprint's edge, along its fall (against the velocity change), metres.</summary>
        public const float ClueThrowDistance = 0.25f;
        /// <summary>A wall or a furniture in the way stops the fallen load this far short of it, metres.</summary>
        public const float ClueWallMargin = 0.15f;
        /// <summary>The height of the ray that finds what stops the fallen load, metres.</summary>
        public const float ClueProbeHeight = 0.3f;
        /// <summary>The rock's visual (GameState's rock): this many full swings, decaying to upright at the rock's end.</summary>
        public const float RockSwings = 1.5f;
        /// <summary>The robot's hum, a 3D loop on the robot: its volume (times the mix scale) and its rolloff distances, metres.</summary>
        public const float SfxHumVolume = 0.16f;
        public const float SfxHumMinDistance = 0.6f;
        public const float SfxHumMaxDistance = 7f;
        /// <summary>The fallen load's crash, as loud as the caught sting: it is heard 6 m away.</summary>
        public const float SfxCrashSynthVolume = 0.62f;
        /// <summary>The rocking chair's creak while it rocks, under the creak's 0.75.</summary>
        public const float SfxRockCreakSynthVolume = 0.4f;
        /// <summary>The robot bumping into the furniture (a soft thump), under the put-down thump's 0.6.</summary>
        public const float SfxBumpSynthVolume = 0.32f;

        // ----- M5B bodies (docs/CONTRACT_M5.md 4, 16.8 and 18): the robot's shove in FurnitureController.BeginPush. -----
        /// <summary>
        /// A collider stops a push (16.8, "blocked by any collider") when its face stands against the push direction by more
        /// than this: the cosine between the push and the hit's inward planar normal. 0.1 is about 6 degrees off parallel, so
        /// a wall the push runs along never stops it, and a wall it meets at any real angle does (no slide along it).
        /// </summary>
        public const float PushBlockedDot = 0.1f;

        // ----- M5B audit (docs/CONTRACT_M5.md 16.3 and 16.5): the memory guard of one search. -----
        /// <summary>
        /// Nodes one search of the level audit may create (about 28 bytes each, so about 1.1 GB); past it the level fails as for
        /// <see cref="AuditNodeCap"/>. Measured: the largest search of wave 5B (level 17's main schedule) creates 25.8 million.
        /// </summary>
        public const int AuditSearchNodeCap = 40000000;
    }
}
