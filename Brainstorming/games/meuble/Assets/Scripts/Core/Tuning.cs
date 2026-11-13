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
    }
}
