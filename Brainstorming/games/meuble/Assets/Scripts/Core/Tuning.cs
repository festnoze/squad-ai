namespace OutOfSight.Core
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
        /// <summary>
        /// The view's lowest pitch (negative: above the horizon). Sky ceiling (2026-11-20, GardenBackdrop): was 15; the arm
        /// stops at <see cref="OrbitArmPitchMin"/> and lower pitches only tilt the view up toward the sky (OrbitCamera.ArmPitchFor).
        /// </summary>
        public const float PitchMin = -10f;
        /// <summary>The arm's lowest pitch: the camera never sinks lower toward the floor (OrbitCamera.ArmPitchFor).</summary>
        public const float OrbitArmPitchMin = 5f;
        /// <summary>The arm eases onto <see cref="OrbitArmPitchMin"/> over this many degrees either side (a smooth stop, no kink).</summary>
        public const float OrbitArmPitchEase = 5f;
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

        /// <summary>The width (metres along x) of a bookshelf that the plain furniture budget covers.</summary>
        public const float BookshelfBudgetWidth = 1.6f;

        /// <summary>
        /// The triangle budget of one furniture piece of <paramref name="kind"/> and width <paramref name="sizeX"/>: the plain
        /// <see cref="BudgetFurnitureTriangles"/>, except a bookshelf, which gets it per <see cref="BookshelfBudgetWidth"/>
        /// of width (never less). Why: a bookshelf is a row of books along its whole width, so its content grows with its
        /// length, while every other piece keeps one shape whatever its size. A 5 m shelf gets 1250 triangles, which keeps it
        /// filled with books instead of stretching a 1.6 m shelf's few books over 5 m; the level budget
        /// (<see cref="BudgetLevelTriangles"/>) still bounds the whole level for mobile. The audit, the probe and the tests
        /// all read it here.
        /// </summary>
        public static int FurnitureTriangleBudget(string kind, float sizeX)
        {
            if (kind != "bookshelf" || sizeX <= BookshelfBudgetWidth)
            {
                return BudgetFurnitureTriangles;
            }
            return (int)System.Math.Floor(BudgetFurnitureTriangles * sizeX / BookshelfBudgetWidth);
        }

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
        // Sfx.cs. Audio overhaul (docs/audio/AUDIO_REPORT.md 4): each recorded role's mix is 10^((playback target -
        // AudioLibrary.ReferenceLufs) / 20), with ReferenceLufs -12. The playback target (at Volume 100 %) is the max
        // loudness over 100 ms for a one-shot and the integrated loudness for a loop, in LUFS, given after each value.
        // The M3.1 balance is kept (the old levels re-measured that way), the variants of a role are now matched by loudness.
        //
        // Audio overhaul, Request 2 (docs/audio/AUDIO_REPORT.md 4): every role below is a further -4 dB (x0.631) from the
        // M3.1 balance, music untouched (MusicTitleMix, MusicLevelMix), so the default mix sits more forward on the music and
        // less on the effects. The alert, the footsteps and the stingers are cut the same -4 dB as everything else and stay
        // clearly readable over the music (creak -17 vs the level loop's -33, a 16 dB margin; footstep -22, an 11 dB margin
        // at 1 m; caught and win -19, a 14 dB margin): the cut moves the whole effects bus, not the few cues that matter most.
        public const float SfxHopMix = 0.0997f;             // -32
        /// <summary>A hop on a rug or in a soft room: the muffled variants, felt more than heard.</summary>
        public const float SfxSoftHopMix = 0.0316f;         // -42
        public const float SfxPivotScrapeMix = 0.1584f;     // -28
        public const float SfxPickUpScrapeMix = 0.224f;     // -25
        public const float SfxCreakMix = 0.562f;            // -17, the loudest cue: the alert every inhabitant in range hears
        public const float SfxWarningCreakMix = 0.1413f;    // -29
        public const float SfxThumpMix = 0.501f;            // -18
        public const float SfxCaughtMix = 0.4467f;          // -19, both caught stings
        public const float SfxHeinMix = 0.501f;             // -18
        public const float SfxFootstepMix = 0.3161f;        // -22 within a metre (linear rolloff to 10 m)
        public const float SfxRoomToneMix = 0.01413f;       // -49 LUFS integrated
        public const float SfxClockMix = 0.00997f;          // -52 LUFS integrated
        public const float SfxUiClickMix = 0.0997f;         // -32
        /// <summary>The menu's selection tick, well under the click.</summary>
        public const float SfxUiHoverMix = 0.0499f;         // -38
        /// <summary>The win jingle, level with the caught stings.</summary>
        public const float SfxWinMix = 0.4467f;             // -19
        /// <summary>A room door opening, a little under the put-down thump.</summary>
        public const float SfxDoorMix = 0.3546f;            // -21
        /// <summary>The wardrobe's doors opening and shutting (the furniture's own move, inside or in front of it).</summary>
        public const float SfxWardrobeMix = 0.2511f;        // -24
        /// <summary>The fallen load's crash: as loud as a caught sting (heard 6 m away).</summary>
        public const float SfxCrashMix = 0.501f;            // -18
        /// <summary>The stool's topple: about as loud as a caught sting (the M4 synthesized level).</summary>
        public const float SfxToppleMix = 0.3981f;          // -20
        /// <summary>The floor lamp's switch, near the hop.</summary>
        public const float SfxLampClickMix = 0.1262f;       // -30
        /// <summary>The variation of a recorded one-shot without variants (door, wardrobe, crash, topple, lamp): pitch +- this.</summary>
        public const float SfxPitchJitter = 0.05f;

        // ----- Music (MusicPlayer.cs, docs/audio/AUDIO_REPORT.md 5) -----
        /// <summary>The title page loop at Music 100 %: -24 LUFS integrated, the cues of a menu are only clicks.</summary>
        public const float MusicTitleMix = 0.251f;
        /// <summary>
        /// The in-level loop at Music 100 %: -33 LUFS integrated. Request 2 of the audio overhaul lowers the effects
        /// instead of raising this past its headroom (AUDIO_REPORT.md 4): the level loop keeps this exact mix, and the
        /// effects moved down to it.
        /// </summary>
        public const float MusicLevelMix = 0.089f;
        /// <summary>Seconds of the crossfade between the title loop and the level loop.</summary>
        public const float MusicCrossfadeSeconds = 1.5f;
        /// <summary>The music under the pause menu: -6 dB.</summary>
        public const float MusicPauseDuck = 0.5f;
        /// <summary>Seconds to silence the music when a caught or win sting starts (the sting plays alone).</summary>
        public const float MusicStingFadeSeconds = 0.25f;
        /// <summary>Seconds for the music to come back after a duck (a retry, the next level, the pause closed).</summary>
        public const float MusicReturnSeconds = 1.5f;
        /// <summary>
        /// Seconds the music stays silent after a catch or a win (the stings last 1.1 s at most), before it comes back
        /// under the end panel at <see cref="MusicPauseDuck"/>.
        /// </summary>
        public const float MusicStingHoldSeconds = 2.5f;
        /// <summary>
        /// Seconds a running music loop may go without its source playing before the watchdog restarts it (an audio
        /// device change or an OS suspend stops every source behind the player's back).
        /// </summary>
        public const float MusicWatchdogSeconds = 1f;
        /// <summary>A loop that stopped this close to its end restarts from the start, not from where it stopped.</summary>
        public const float MusicRestartTailSeconds = 0.5f;
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
        // M7 lighting (CONTRACT_M7 1.1, polish round 2): a touch brighter and warmer for softer, more readable
        // shadows, and a bloom that clears the window and a lit lamp a little more generously.
        public const float LookSunIntensity = 1.42f;
        public const float LookBloomThreshold = 1.15f;
        public const float LookBloomIntensity = 0.72f;
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
        // Wood (furniture-scale, not floor-scale): 0.6m reads as grain streaks on a chair seat or wardrobe door
        // instead of a smooth near-flat crop (M7 texture pass, agent tex_wood).
        public const float DetailTileWood = 0.8f;
        public const float DetailTileParquet = 1.8f;
        public const float DetailTilePlaster = 2.0f;
        // M7 envcolour (CONTRACT_M7 5): the fabrics' images are fine weaves; in real colours their weave must read at
        // play distance, so they repeat a little smaller than the M4.2 grayscale details did (0.55, 0.45, 1.1).
        public const float DetailTileUpholstery = 0.4f;
        public const float DetailTileLinen = 0.35f;
        public const float DetailTileCarpet = 0.6f;
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
        // Task DOORAUTO (docs/next/progress/DOORAUTO.md): pushing the move input toward a closed leaf in reach (into its
        // wall), into a wardrobe's front from its entry zone, or out of it while hidden, replaces the E press. The push must
        // stay within PushConeDegrees of that direction, at least PushMinInput strong, for PushConfirmTime (8 fixed steps,
        // so sliding along a wall never opens a door). A push starts only with the furniture still (a moving one drives on
        // into the leaf, stops there, and a push starts then); it holds the furniture still, then the same action as the E
        // press begins (DoorOpenTime, WardrobeActionTime), so the audit's timings are unchanged.
        public const float PushConfirmTime = 0.16f;
        public const float PushConeDegrees = 45f;
        public const float PushMinInput = 0.3f;
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
        /// <summary>
        /// DOGBIG (product owner, 2026-11-21: "the dog reads too small"): the dog's MODEL (the Quaternius Husky) is drawn this
        /// many times the old Shiba's size, its eyes at <see cref="DogModelEyeHeight"/> (about 0.63 m tall at the ears, 0.76 m
        /// from snout to tail). Presentation only: the gameplay eye (<see cref="DogEyeHeight"/>, the vision cone's origin),
        /// the collider (<see cref="DogCapsuleRadius"/>, <see cref="DogCapsuleHeight"/>), the speeds and every reach stay as
        /// they were.
        /// </summary>
        public const float DogModelScale = 1.5f;
        /// <summary>DOGBIG: the eye height ModelKit fits the dog's model to (the catalog's target eye), metres.</summary>
        public const float DogModelEyeHeight = DogEyeHeight * DogModelScale;
        /// <summary>
        /// DOGBIG: the Resources name of the dog's fur texture (a base colour map painted on the Husky's UV0 atlas,
        /// Assets/Art/Characters/dog_fur_uv_template.png). While no such texture exists the dog keeps its plain tint; once it
        /// is dropped in (Assets/Art/Characters/Resources/DogFur.png) every slot of the dog's model shows it
        /// (ModelKit.ApplyPetFurMap), in game and in the title logo.
        /// </summary>
        public const string DogFurTextureResource = "DogFur";
        /// <summary>
        /// DOGBIG, presentation only: while the dog drags the furniture (and wags after the drop) its model steps back along
        /// its facing so its snout, which now reaches past the near edge of the held furniture, stays on that edge; the step
        /// eases in and out at this rate (1 per second).
        /// </summary>
        public const float DogHoldBackRate = 4f;
        /// <summary>
        /// GRIP (2026-11-22), presentation only (GripDef, GripMath): the dog's snout tip stands this far below its head bone
        /// with the head level (metres at the fitted model's size, before Tuning.DogHeadScale; measured on the GLB's rest pose:
        /// the tip 0.082 m ahead of the head bone and 0.010 m below it), and the head pitches down this many times the neck's
        /// bend when it lowers its head onto the point it bites (1: the muzzle continues the neck's curve).
        /// </summary>
        public const float DogSnoutDrop = 0.010f;
        public const float DogGripHeadFollow = 1f;
        /// <summary>
        /// GRIP, presentation only: how far the dog's model may step toward the furniture it bites while it is still on the
        /// floor (the pin and the grip, before the pick up brings it to the carry anchor), metres.
        /// </summary>
        public const float DogGripReachIn = 0.35f;
        /// <summary>
        /// DOGBIG (black Labrador, 2026-11-21), presentation only: the Husky model's pricked ears and curled tail are posed as a
        /// Labrador's every frame after its clip (InhabitantRig.PetPose): each ear hangs down beside the head, leaning out by
        /// DogEarOut and forward by DogEarForward (per unit down, in the head's frame); the tail hangs back and down
        /// (DogTailDroop down per unit back, in the body's frame), straightened DogTailWeight of the way so the clip's sway
        /// still shows.
        /// </summary>
        public const float DogEarOut = 0.35f;
        public const float DogEarForward = 0.15f;
        public const float DogTailDroop = 0.6f;
        public const float DogTailWeight = 0.85f;
        /// <summary>
        /// DOGBIG v3 (product owner, 2026-11-21: "the head is too small for its face to be seen"), presentation only: the dog's
        /// head bone is scaled this much (head, muzzle, eyes and ears; the neck blends in through the skin weights). v4: 1.45, with
        /// the rounder skull baked in the GLB (make_husky.py), about 1.5 times the original head.
        /// </summary>
        public const float DogHeadScale = 1.45f;
        /// <summary>
        /// DOGBIG v3, the bite (presentation only): from the pin to the drop the dog's head rolls DogBiteRollDegrees sideways
        /// and dips DogBitePitchDegrees onto the furniture's edge, its jaw (the "Jaw" joint added to the Husky) opens
        /// DogJawOpenDegrees; the pose eases in and out at DogBiteRate (1 per second).
        /// DOGFACE: the jaw 45 deg (was 30, no gap readable): the GLB's lower jaw is longer (hinge behind the mouth's corner),
        /// cut from the upper lip, and opens on the mouth's dark pink inside (make_husky.py v5).
        /// </summary>
        public const float DogBiteRollDegrees = 60f;
        public const float DogBitePitchDegrees = 15f;
        public const float DogJawOpenDegrees = 45f;
        public const float DogBiteRate = 6f;
        /// <summary>
        /// DOGBIG v3 ("the fur is not visible"): the fur map material's smoothness (a black coat's sheen; the palette
        /// characters use 0.25), and the fur map's mip bias (negative: a sharper mip at game distance, the strands kept).
        /// </summary>
        public const float DogFurSmoothness = 0.4f;
        public const float DogFurMipBias = -0.6f;
        public const float BarkRadius = 6f;
        public const float BarkCooldown = 3f;
        // The dog's hold (CONTRACT_M5 20): after its bark it runs to the furniture (faster than every body), pins it within
        // InvestigateReach + CarryReachMargin, barks at it every DogHoldBarkInterval (a sound, not a noise event) until a
        // human puts it back; DogHoldMaxWait with no human on the way and it gives up.
        public const float DogRunSpeed = 2.6f;
        public const float DogHoldBarkInterval = 0.8f;
        public const float DogHoldMaxWait = 6f;
        // DOGCARRY (the product owner's "when it catches you, it brings you back like a human would"): after DogGripTime of
        // its hold the dog itself drags the furniture back to the slot the nearest human remembers, by an edge in its mouth
        // (lifted DogDragLift instead of CarryHeight, a DogDragWobbleDegrees / DogDragBob wobble at DogDragWobbleHz), at
        // DogDragSpeed; it drops it, barks once and wags for DogWagTime, then resumes its routine.
        public const float DogGripTime = 0.6f;
        public const float DogDragSpeed = 0.8f;
        public const float DogDragLift = 0.06f;
        public const float DogDragWobbleDegrees = 6f;
        public const float DogDragBob = 0.03f;
        public const float DogDragWobbleHz = 2.5f;
        public const float DogWagTime = 0.8f;
        public const float WakeTelegraph = 0.6f;
        public static readonly UnityEngine.Color DogConeColor = new UnityEngine.Color(0.25f, 0.85f, 0.85f, 1f);
        // DOGBIG: 46 (the Shiba) to 50: the Husky's tail has 6 bones instead of 3 (same AnimalArmature rig otherwise), and
        // DOGBIG v3 added a "Jaw" joint for the bite.
        public const int BudgetPetBones = 50;
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
        public const float BalanceWarning = 0.9f; // M5 5B.1 (CONTRACT_M5 19 m13): red only near a real fall
        public const float CrashRadius = 6f;
        public const float PutAwayTime = 0.6f;
        // Houses, budgets and the camera (PRD 7.4 v1.7, CONTRACT_M5 9, 16.11).
        public const int BudgetHouseRenderers = 160;
        public const int BudgetHouseMaterials = 32;
        public const int HouseBudgetRooms = 5;
        /// <summary>The zoom's far bound cap (was 16; 40 since 2026-11-24 so the largest houses can be seen whole).</summary>
        public const float CameraMaxDistanceHouse = 40f;
        /// <summary>
        /// The zoom's far bound is at least the house's longest interior side times this (2026-11-24, user request: zoom out
        /// until every room is in view, from anywhere in the house, at the 55 degree field of view).
        /// </summary>
        public const float CameraWholeHouseFit = 1.6f;
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
        /// <summary>
        /// M7 walls pass (product owner 2026-11-19): the default of the wall opacity option (SaveOptions.WallOpacity, percent):
        /// the opacity a wall in the way fades to in the see-through and both modes (WallFader): light enough to see the
        /// room through it, enough to see the whole wall. Product owner, 2026-11-20: 10 % (was 20 %), with "both" as the default
        /// Walls mode (SaveOptions.Walls).
        /// </summary>
        public const int WallOpacityDefault = 10;
        /// <summary>
        /// M7 walls pass: the height of the solid stub every wall line keeps along its footprint (LevelBuilder), shown in the
        /// lowered and both modes: a lowered wall shows only this stub (and its standing door frames). Below the top of every
        /// player body, so a stub never hides the furniture's top from the camera. Metres.
        /// </summary>
        public const float WallStubHeight = 0.22f;
        /// <summary>M7 walls pass: seconds a wall takes to fade or sink out of the way, or to come back (WallFader).</summary>
        public const float WallFadeSeconds = 0.25f;
        /// <summary>
        /// M7 walls pass: a camera that moves farther than this in one frame jumped (SetView, a restart): the wall fader
        /// snaps instead of animating. Metres.
        /// </summary>
        public const float WallFadeSnapDistance = 1.5f;
        /// <summary>
        /// M9 near walls (product owner 2026-11-19): in the see-through and both looks, an outer wall line between the camera
        /// and the house whose quad covers more than this fraction of the screen (0 to 1) fades to nothing instead of the
        /// wall opacity option: even translucent, it veils the whole view (WallFader).
        /// </summary>
        public const float NearWallEnterCoverage = 0.2f;
        /// <summary>
        /// M9 near walls: a vanished outer wall comes back to the wall opacity option only once it covers less than this
        /// fraction of the screen (hysteresis under <see cref="NearWallEnterCoverage"/>: no flicker while the camera orbits).
        /// </summary>
        public const float NearWallExitCoverage = 0.14f;
        /// <summary>M9 near walls: seconds a near outer wall takes to fade from the wall opacity option to nothing, or back.</summary>
        public const float NearWallVanishSeconds = 0.3f;
        /// <summary>
        /// M7 walls pass: how far the closures at a wall line's ends and the caps over a crossing wall's band stand inside
        /// the wall's own faces and cap, so a standing wall's faces always win the depth test over them (no z-fighting).
        /// Metres.
        /// </summary>
        public const float WallClosureInset = 0.002f;

        // ----- M5 watchers (docs/CONTRACT_M5.md 3, 16.11; CONTRACT_M5_v3.md 4 and 15.5) -----
        /// <summary>
        /// Metres the dog walks per Walk clip cycle (InhabitantRig's stride for pets): the stance feet of the Shiba's
        /// "Walk" travel 2.7 native units per cycle (measured on the GLB from its IK foot bones), times its fit scale 0.130
        /// (its eyes, 2.69 native units high in Idle, at DogEyeHeight): 0.35 m. DOGBIG: the Husky's Walk clip is the Shiba's
        /// key for key (same IK foot tracks, same 1.042 s) and its eyes stand within 1 % of the Shiba's, so the stride grows
        /// with the model: 0.525 m, a bigger dog's longer, slower trot (2.7 cycles a second at 1.4 m/s).
        /// </summary>
        public const float DogWalkCycleMeters = 0.35f * DogModelScale;
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
        // Audio overhaul: 0.55 x 0.69 / 0.501 (SfxFootstepMix as it was before Request 2's -4 dB effects trim). Left as is:
        // the patter plays at gain x SfxFootstepMix like a human step, so Request 2's cut moved it down with every footstep
        // and the same gap under them holds.
        public const float DogPatterGain = 0.757f;
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
        /// <summary>
        /// The robot's hum, a loop on the robot: its volume (times the mix scale) and its rolloff distances, metres. Levels v2
        /// C8: silent from 3.5 m (it was 7 m), just past RobotHumRadius (2.5 m, the masking rule and the hum disc).
        /// </summary>
        public const float SfxHumVolume = 0.16f;
        public const float SfxHumMinDistance = 0.6f;
        public const float SfxHumMaxDistance = 3.5f;
        /// <summary>The fallen load's crash, as loud as the caught sting: it is heard 6 m away.</summary>
        public const float SfxCrashSynthVolume = 0.62f;
        /// <summary>The rocking chair's creak while it rocks, under the creak's 0.75.</summary>
        public const float SfxRockCreakSynthVolume = 0.4f;
        /// <summary>The rocking chair's rock creak; false mutes it entirely (muted then restored at the user's request, 2026-11-24).</summary>
        public const bool SfxRockCreakEnabled = true;
        /// <summary>The "hein ?" of a discovery (synthesized or vocal_huh): removed entirely at the user's request (2026-11-24);
        /// true restores it.</summary>
        public const bool SfxHeinEnabled = false;
        /// <summary>The human telegraph's "hm ?" before a turn or glance: removed at the user's request (2026-11-24); true
        /// restores it. The dog's sniff telegraph is unaffected.</summary>
        public const bool SfxHmEnabled = false;
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

        // ----- M5 5B.1 watchers (docs/CONTRACT_M5.md 19; critique m7, m15 and the 5B literals) -----
        /// <summary>The robot's status light pulses between these scales (visual only; its rate is RobotLightPulseRate).</summary>
        public const float RobotLightPulseMin = 0.75f;
        public const float RobotLightPulseMax = 1.15f;
        /// <summary>
        /// m15: the robot's drawn body turns toward its heading at most this fast, degrees a second (visual only; the rule pose
        /// stays RobotPath's): a loop end's 180 degree reversal takes a third of a second instead of one frame.
        /// </summary>
        public const float RobotTurnRate = 540f;
        /// <summary>m15: a pose this far from the last one (metres) is a teleport: the drawn body snaps to it.</summary>
        public const float RobotSnapDistance = 0.5f;
        /// <summary>M5B m14: a fan sample is raised to the floor of any other sample this many spacings away (diagonals included).</summary>
        public const float ConeDrapeReach = 1.5f;
        /// <summary>M5B m20: a fan recast past a cover aims this much nearer than the exact clearance over its edge, metres.</summary>
        public const float ConeClearMargin = 0.01f;
        /// <summary>
        /// m15: the fallen load's clue lies on one floor surface (the flat floor, a platform or one ramp's slope): a sample of
        /// its spread off that surface by more than this, metres, means it crosses an edge, and it is moved.
        /// </summary>
        public const float ClueSurfaceTolerance = 0.01f;
        /// <summary>m15: how far the clue may be moved to lie on one surface, metres (in ClueSearchStep rings).</summary>
        public const float ClueSearchRadius = 0.6f;
        public const float ClueSearchStep = 0.05f;

        // ----- M5 5B.1 game (docs/CONTRACT_M5.md 19; critique m15): the fallen load's landing. -----
        /// <summary>
        /// The planar radius of the largest clue around its centre (the books' and the plant's spread reach about 0.31 m):
        /// GameState keeps the clue's centre at least this far from a wall or a furniture in the way, metres.
        /// </summary>
        public const float ClueSpreadRadius = 0.32f;

        // ----- M5 5B.1 audit (docs/CONTRACT_M5.md 19; critique M2, M7 and m9) -----
        /// <summary>
        /// M2: a schedule the level audit finds fails when, in one stay within this of one of its own points (metres), it
        /// spends more than AuditMaxWait not moving: waiting by hops out and back (1.12 m L-hops restart the search's 1 m wait
        /// anchor) is still waiting.
        /// </summary>
        public const float AuditLoiterRadius = 1.5f;
        /// <summary>
        /// m9: the audit refuses a schedule whose velocity changes by this much over LoadWindow (m/s), under LoadFallDeltaV:
        /// twice probe 44's 0.05 m/s gap between MotionProfile and the controller.
        /// </summary>
        public const float AuditLoadDeltaV = 1.7f;
        /// <summary>M7: the audit's fidelity replay tests a move at intermediate positions this far apart (metres).</summary>
        public const float AuditFidelityStep = 0.1f;

        // ----- M6 gameplay (docs/CONTRACT_M6.md 2.5 to 2.7) -----
        /// <summary>The wardrobe prop's box, metres (w x h x d): 1.0 x 2.0 x 0.6.</summary>
        public const float WardrobeSizeX = 1.0f;
        public const float WardrobeSizeY = 2.0f;
        public const float WardrobeSizeZ = 0.6f;
        /// <summary>
        /// A body fits in the wardrobe when its width and depth are at most this (metres): the stool and the floor lamp
        /// (0.35), never the chair (0.45) nor the office chair (0.55).
        /// </summary>
        public const float WardrobeFitWidth = 0.40f;
        /// <summary>A body fits when its height (plus a load's) is at most this, metres: the floor lamp (1.80) fits.</summary>
        public const float WardrobeFitHeight = 1.85f;
        /// <summary>The furniture centre stands at most this far in front of the wardrobe's front face to enter it, metres.</summary>
        public const float WardrobeReach = 0.6f;
        /// <summary>
        /// Entering or leaving the wardrobe: an action of this many seconds, seen as moving. Shortened from the
        /// original 0.5 s (M7 polish: the PO reported a noticeable delay between the key press and the furniture
        /// disappearing) now that WardrobeDoors gives the player immediate visual feedback on the key press, so the
        /// action itself can be brisk. A shorter action only helps the player (CONTRACT_M6, the audit reads this same
        /// constant for both the entry and the exit action, so level 18 stays verified consistently).
        /// </summary>
        public const float WardrobeActionTime = 0.25f;
        /// <summary>
        /// M7 polish (WardrobeDoors), presentation only: each wardrobe door's ease-out swing from its outer hinge,
        /// in degrees. Never read by a rule; the wardrobe keeps its one whole-box collider throughout.
        /// </summary>
        public const float WardrobeDoorSwingDegrees = 100f;
        /// <summary>
        /// M7 polish (WardrobeDoors), presentation only: how far (metres) the furniture's visual slides along the
        /// wardrobe's own axis while entering or leaving, so it visibly slips through the open doors instead of
        /// popping in or out at the end of the action. Never moves the transform the rules read.
        /// </summary>
        public const float WardrobeSlideDistance = 0.3f;
        /// <summary>A creak made while hidden in the wardrobe is heard within CreakRadius times this (muffled).</summary>
        public const float WardrobeCreakFactor = 0.5f;
        /// <summary>An inhabitant opening a door stops this many seconds in front of it while the leaf swings.</summary>
        public const float InhabitantDoorStop = 0.6f;
        /// <summary>
        /// An inhabitant opens a closed opt-in leaf when its walk crosses the leaf's wall centre line within the opening and
        /// it stands at most this far from that line (metres) on the side the leaf does not swing into (on the swing side: the
        /// door width plus InhabitantRadius, out of the leaf's sweep); a door it puts back is approached at that distance too.
        /// </summary>
        public const float InhabitantDoorReach = 0.5f;

        // ----- M6 options (docs/CONTRACT_M6.md 2.1, 2.2 and 2.3) -----
        /// <summary>Camera sensitivity (2.1): multiplies the mouse and the right stick orbit rates.</summary>
        public const float SensitivityMin = 0.25f;
        public const float SensitivityMax = 2.0f;
        public const float SensitivityStep = 0.25f;
        public const float SensitivityDefault = 1.0f;
        /// <summary>Volume (2.1): AudioListener.volume, a percentage.</summary>
        public const int VolumeMin = 0;
        public const int VolumeMax = 100;
        public const int VolumeStep = 10;
        public const int VolumeDefault = 80;
        /// <summary>Music (audio overhaul): the music's own level under the Volume, a percentage. A save without it gets the default.</summary>
        public const int MusicMin = 0;
        public const int MusicMax = 100;
        public const int MusicStep = 10;
        public const int MusicDefault = 70;
        /// <summary>
        /// 2.3: the dashed outline drawn around an alerted watcher's cone: its width and its dash length (equal to the
        /// gap, a 50 percent duty cycle), metres.
        /// </summary>
        public const float ConeOutlineWidth = 0.05f;
        public const float ConeOutlineDash = 0.22f;

        // ----- M6 textures (docs/CONTRACT_M6.md 2.4, docs/M6_TEXTURES_RESEARCH.md): texture pass 2. -----
        // Metres covered by one repeat of each new detail texture, in world space (TextureLibrary.TileMetres).
        // M7 envcolour (CONTRACT_M7 5): grass.png in real colours, a little larger than 2.0 so the blades read as a lawn
        // rather than fine noise over the garden that fills a third of most start views.
        public const float DetailTileGrass = 2.5f;
        public const float DetailTileLacquer = 1.0f;
        public const float DetailTileMetal = 0.3f;
        public const float DetailTilePlastic = 0.2f;
        // M7 polish (smallprops agent): leaves (2.6 cm wide sprigs, 7-14 cm foliage balls) and soil (9-23 cm
        // discs) showed under half a texture repeat at 0.35/0.25, reading as a flat tinted blob at play
        // distance; shrunk so 2-3 repeats cross each prop and the Moss002/Ground104 grain actually reads.
        // M7 envcolour (CONTRACT_M7 5): in real colours each leaf of foliage.png must read as a leaf, not as noise: about
        // 12 leaves across the image, so a 0.3 m repeat gives leaves of about 2.5 cm; soil's grains likewise.
        public const float DetailTileFoliage = 0.3f;
        public const float DetailTileSoil = 0.25f;
        // Per-material smoothness and metallic of texture pass 2 (CONTRACT_M6 2.4: one fixed finish per surface,
        // read by PrimitiveKit.Lit at every call site that shows it; TextureLibrary.FinishOf is the one place that
        // holds them). Metallic defaults to 0 except Metal (brushed, Metal009).
        public const float GrassSmoothness = 0.2f;
        public const float LacquerSmoothness = 0.9f;
        public const float MetalSmoothness = 0.5f;
        public const float MetalMetallic = 0.9f;
        public const float PlasticSmoothness = 0.55f;
        public const float FoliageSmoothness = 0.25f;
        public const float SoilSmoothness = 0.08f;
        /// <summary>The window pane (2.4): no texture (Surface.Plain), but its own smoothness; metallic stays 0.</summary>
        public const float WindowPaneSmoothness = 0.95f;

        // ----- M7 touch (docs/CONTRACT_M7.md 1.5): the touch controls. Sizes in pixels of a 1080 pixel high screen. -----
        /// <summary>Camera degrees per pixel of orbit drag on the right half, times the sensitivity option.</summary>
        public const float TouchOrbitDegPerPixel = 0.15f;
        /// <summary>
        /// PINCH (2026-11-24): orbit zoom metres per pixel of change in the distance between two pinching fingers, on levels
        /// 1 to 7 (scaled with the zoom range like a wheel notch). 440 pixels sweep the whole 2.5 to 6 m range.
        /// </summary>
        public const float TouchPinchMetresPerPixel = 0.008f;
        /// <summary>PINCH: a second finger landing this soon after the first, the first not yet dragged, makes the two a pinch.</summary>
        public const float TouchPinchPairSeconds = 0.25f;
        /// <summary>How far the thumb travels from where it landed for a full stick.</summary>
        public const float TouchStickRadius = 120f;
        /// <summary>The careful and pause buttons' diameter (at least 140 px at 1080p too).</summary>
        public const float TouchButtonSize = 150f;
        /// <summary>
        /// Task DOORAUTO (the action button is gone; the lamp is switched by tapping it): a tap within this many pixels of
        /// the player lamp's projected box switches it, so a thin lamp is easy to hit with a thumb.
        /// </summary>
        public const float TouchLampTapMargin = 60f;

        // ----- M7 android (docs/CONTRACT_M7.md 1.4): the quality tiers (QualityTier). -----
        /// <summary>Bas renders at this fraction of the screen resolution; Moyen at 1 (both on Mobile_RPAsset).</summary>
        public const float QualityLowRenderScale = 0.75f;
        public const float QualityMediumRenderScale = 1f;
        /// <summary>Android target frame rate on Bas and Moyen, and on Haut (PC keeps its own setting).</summary>
        public const int QualityLowFrameRate = 30;
        public const int QualityHighFrameRate = 60;
        /// <summary>The priority of the global volume that turns bloom off on Bas, above the look's own volume (10).</summary>
        public const float QualityVolumePriority = 100f;

        // ----- M7 textures (docs/CONTRACT_M7.md 1.2): normal maps and the new Tile surface. -----
        /// <summary>Metres covered by one repeat of the kitchen and bathroom floor tile detail (Tiles049):
        /// a notch above the raw 0.5 so the mosaic's many thin grout lines repeat less densely at play
        /// distance (still clearly smaller-scaled than Parquet's 1.8 plank repeat).</summary>
        // M7 envcolour (CONTRACT_M7 5): tile.png holds 6 x 6 tiles; in real colours a 1.5 m repeat gives 25 cm kitchen
        // tiles, a pattern that reads at play distance instead of a fine mosaic.
        public const float DetailTileTile = 1.5f;
        /// <summary>Smoothness of a tiled floor (Surface.Tile): glazed ceramic, smoother than Parquet's 0.35.</summary>
        public const float TileSmoothness = 0.5f;
        // The modest _BumpScale of each surface's normal map (PrimitiveKit.Detail, TextureLibrary.BumpScaleOf): a
        // little higher for Metal (Metal009's brushed streaks read faintly at 1.0, M6_TEXTURES_RESEARCH.md), modest
        // everywhere else, Parquet included: it covers most of the frame on an ordinary room (the Step22d probe caps
        // how much noisier the textured view may read than the flat one), so its own faint grout seams (WoodFloor051)
        // stay at the same modest scale as Wood rather than the stronger compensation a smaller surface could take.
        // Wood furniture covers much less of the frame than the Parquet floor, so it can take the stronger
        // compensation the comment above declines for Parquet (M7 texture pass, agent tex_wood).
        public const float NormalScaleWood = 1.1f;
        // Parquet's own source normal (WoodFloor051) is as flat as Metal's, but the floor fills most of the frame,
        // so it gets only a small bump over the old baseline, not Metal's full compensation (M7 texture pass, agent tex_parquet).
        public const float NormalScaleParquet = 1.0f;
        public const float NormalScalePlaster = 0.7f;
        public const float NormalScaleUpholstery = 0.6f;
        public const float NormalScaleLinen = 0.85f;
        public const float NormalScaleCarpet = 0.75f;
        public const float NormalScaleGrass = 0.6f;
        // PaintedWood006C's own normal map is mostly flat (xy deviation mean ~6 of 127) but has a few sharp plank-seam
        // spikes (deviation up to ~121); at the baseline 1.0 those spikes risk pinpoint specular noise once combined
        // with LacquerSmoothness's tight 0.9 highlight, on the piece the player furniture must stay the clearest
        // thing in frame (PRD 7.2, M7 texture pass, agent tex_lacquer). Eased down, like Upholstery and Linen.
        public const float NormalScaleLacquer = 0.8f;
        // Metal009's own NormalGL is almost flat (xy std ~0.005-0.012 of 1.0: brushed metal is optically flat,
        // its streaks are mostly specular, not geometric), so a bump scale alone barely moved it. Re-derived the
        // normal map with a 3x gain on the source xy before the resize + renormalize (M7 texture pass, agent
        // tex_metal), then brought this scale back down from 2.0 so the combined relief grows but stays short of
        // noisy on the robot's body, the largest metal surface.
        public const float NormalScaleMetal = 1.5f;
        public const float NormalScaleTile = 1.0f;

        // ----- M7 envcolour (docs/CONTRACT_M7.md 5): real-colour textures (product owner, 2026-11-18). -----
        // One colour material per surface (PrimitiveKit.SurfaceMaterial, TextureLibrary.ColourFinishOf): the M4.2
        // surfaces, whose smoothness used to come from each palette material, get one finish each. The other surfaces
        // keep their M6 finish (GrassSmoothness and the rest above).
        public const float ColourWoodSmoothness = 0.3f;
        public const float ColourParquetSmoothness = 0.35f;
        public const float ColourPlasterSmoothness = 0.1f;
        public const float ColourUpholsterySmoothness = 0.1f;
        public const float ColourLinenSmoothness = 0.1f;
        public const float ColourCarpetSmoothness = 0f;
        /// <summary>The Lacquer colour material (the door leaves: painted wood, matte, as the DoorWood palette material was).</summary>
        public const float ColourDoorSmoothness = 0.35f;
        /// <summary>
        /// The player furniture (PrimitiveKit.PlayerMaterial): the owner's "vivid red painted metal" image. Painted metal:
        /// glossy, partly metallic so the highlights move, but mostly diffuse so the red reads in any light (PRD 7.2).
        /// Toned down from 0.8 / 0.35 (owner, 2026-11-19: "trop etincelant" while moving): the wider lobe of 0.7 and
        /// the lower F0 of 0.2 roughly halve the moving glint and the environment reflection, which stay visible.
        /// </summary>
        public const float PlayerSmoothness = 0.7f;
        public const float PlayerMetallic = 0.2f;

        // ----- Wall finishes (product owner request, 2026-11-19; tools/assets/make_wall_finishes.py). -----
        // Metres covered by one repeat, at a believable real scale: the two plasters' clouds and trowel or brush marks
        // span tens of centimetres (2 m, as the crepi); the grasscloth repeats two hung panels of 0.9 m; the printed
        // wallpaper's repeat is the 0.53 m width of a roll (two 26.5 cm stripes, 16 cm sprigs).
        public const float DetailTileSage = 2.0f;
        public const float DetailTileLimewash = 2.0f;
        public const float DetailTileGrasscloth = 1.8f;
        public const float DetailTileWallpaper = 0.53f;
        /// <summary>The _BumpScale of the wall finishes' normal maps: their relief is already set in the maps (xy rms 0.05 to 0.2).</summary>
        public const float NormalScaleWallFinish = 1.0f;
        /// <summary>The finishes are matte, as the crepi (ColourPlasterSmoothness).</summary>
        public const float ColourWallFinishSmoothness = 0.1f;
        /// <summary>
        /// Tiled walls (product owner request, 2026-11-19, docs/m9/FLOORS_WALLS.md): the product owner's two wall images
        /// are each a whole wall, tiles above a trim above paint, so each spans ONCE the height of every room's walls,
        /// from the floor (V = 0) to the top, and repeats only along the wall (its maps are clamped vertically). Square
        /// images, so the repeat along the wall is the same 2.7 m (never stretched): the white bathroom tiles are 27 cm
        /// squares (ten per repeat) over a trim at 0.99 to 1.03 m; the ivory subway tiles are 67.5 x 22.5 cm (a 3:1
        /// format, four per course) over a rounded trim at 1.09 to 1.13 m, just above a kitchen worktop.
        /// </summary>
        public const float TiledWallHeight = 2.7f;
        /// <summary>
        /// Walls 4 (docs/m9/FLOORS_WALLS.md section 7, found by the room by room check): mapped once over 2.7 m the tiles
        /// were far too big (27 cm bathroom squares, 67.5 x 22.5 cm subway tiles that read as breeze blocks). The tiled
        /// walls are now laid up the wall as bands (WallArray, shader OutOfSight/Wall Finishes): the paint from the floor to
        /// the trim (mirrored up and down, never stretched), the trim at <see cref="WhiteTileTrimHeight"/> or
        /// <see cref="SubwayTileTrimHeight"/>, then the image's tile field repeated in whole rows to the wall top. One
        /// image width in metres: ten 15 cm bathroom squares (1.5 m); four 30 x 10 cm subway tiles (1.2 m, seven courses
        /// per field, every other field shifted half a tile so the running bond never breaks).
        /// </summary>
        public const float DetailTileWhiteTile = 1.5f;
        public const float DetailTileSubwayTile = 1.2f;
        /// <summary>The bottom of the bathroom's trim above the floor: washbasin and bathtub rim height.</summary>
        public const float WhiteTileTrimHeight = 0.99f;
        /// <summary>The bottom of the kitchen's trim above the floor: just above a worktop.</summary>
        public const float SubwayTileTrimHeight = 1.09f;
        /// <summary>One material shows the glazed tiles and the paint under them: between the matte paint (0.1) and the glazed floor Tile (0.5).</summary>
        public const float TiledWallSmoothness = 0.3f;
        /// <summary>
        /// Printed and stone walls (product owner request, 2026-11-19, docs/m9/FLOORS_WALLS.md section 6): the product
        /// owner's three all-over wall images repeat both ways, one square repeat in metres, at a believable real scale.
        /// The travertine (no joint, cloudy, its pores in streaks) spans 1.2 m: pores of 1 to 4 cm, clouds of about 30 cm.
        /// The arches wallpaper is a 4 x 4 lattice: at 1.8 m its arches are 26 cm tall, 45 cm apart both ways, so six rows
        /// fill a 2.7 m wall exactly and every row sits at the same height in every room (a face's V is its height above
        /// the floor). The linen pinstripe has eight stripe pairs per repeat: at 1.2 m, one pair every 15 cm.
        /// </summary>
        public const float DetailTileTravertine = 1.2f;
        public const float DetailTileArches = 1.8f;
        public const float DetailTilePinstripe = 1.2f;
        /// <summary>The travertine is honed stone: a soft sheen, between the matte papers (0.1) and the glazed tiled walls (0.3).</summary>
        public const float TravertineSmoothness = 0.2f;
        /// <summary>
        /// Walls 4 (product owner request, 2026-11-19, docs/m9/FLOORS_WALLS.md section 7): two more all-over images. The
        /// quatrefoil wallpaper is an 8 x 8 lattice: at 1.35 m a quatrefoil every 16.9 cm, so sixteen rows fill a 2.7 m
        /// wall exactly. The sage fluted panel has 36 ribs per repeat: at 1.44 m, one rib every 4 cm (a real fluted panel).
        /// </summary>
        public const float DetailTileQuatrefoil = 1.35f;
        public const float DetailTileSageRibbed = 1.44f;
        /// <summary>The fluted panel is painted wood in a satin paint: the travertine's soft sheen.</summary>
        public const float SageRibbedSmoothness = 0.2f;

        // ----- M8 floor finishes (docs/m8/ROOMS_PLAN.md 4, product owner request, 2026-11-19;
        // tools/assets/make_floor_finishes.py). -----
        // Metres covered by one repeat, at a believable real scale: a marble slab is about 0.6 m; a herringbone
        // board pattern repeats every 0.6 to 0.8 m (two board lengths across the zigzag); wall-to-wall carpet loop
        // pile has no visible motif at 1 m (as DetailTileCarpet, the plain soft floor's own repeat).
        public const float DetailTileMarble = 0.6f;
        public const float DetailTileHerringbone = 0.7f;
        public const float DetailTileCarpetFinish = 1.0f;
        /// <summary>The _BumpScale of the three finishes' normal maps: their relief is already set in the maps (xy rms 0.06 to 0.18).</summary>
        public const float NormalScaleFloorFinish = 1.0f;
        /// <summary>Polished marble: glossier than a tiled floor (TileSmoothness 0.5).</summary>
        public const float MarbleSmoothness = 0.65f;
        /// <summary>Matte oak, as the default parquet's own colour finish (ColourParquetSmoothness).</summary>
        public const float HerringboneSmoothness = 0.35f;
        /// <summary>Matte, as the plain soft floor's own Carpet (ColourCarpetSmoothness).</summary>
        public const float CarpetFinishSmoothness = 0f;
        // M9 floors (2026-11-19, docs/m9/FLOORS_WALLS.md): metres per repeat, at a believable real scale. The light oak
        // repeats eight 25 cm wide boards (2 m); the verde four 0.8 m slabs (1.6 m); the product owner's small ivory
        // bathroom tiles are a 16 x 16 grid (7.5 cm tiles, 1.2 m) and the large teal ones a 4 x 4 grid (40 cm tiles,
        // 1.6 m). Their smoothness and _BumpScale reuse the parquet, marble and tile ones (TextureLibrary.FinishOf).
        public const float DetailTileLightOak = 2.0f;
        public const float DetailTileVerde = 1.6f;
        public const float DetailTileIvoryTile = 1.2f;
        public const float DetailTileTealTile = 1.6f;

        // ----- M7 design (docs/CONTRACT_M7.md 4.1): the difficulty table (DifficultyDef). Normal is the M6 game. -----
        // Facile only helps the player, Difficile only hinders (DifficultyM7Tests checks every knob both ways).
        /// <summary>Every watcher's view range is multiplied by this (the lamp factor applies on top).</summary>
        public const float EasyViewRangeFactor = 0.85f;
        public const float HardViewRangeFactor = 1.15f;
        /// <summary>Degrees added to every cone's half angle.</summary>
        public const float EasyHalfAngleOffset = -5f;
        public const float HardHalfAngleOffset = 5f;
        /// <summary>Every listener's hearing factor is multiplied by this. Difficile keeps 1: at 1.25 the rug and decoy lessons of levels 2 and 3 had no schedule.</summary>
        public const float EasyHearingFactor = 0.75f;
        public const float HardHearingFactor = 1.0f;
        /// <summary>Every suspicion gain is multiplied by this (Difficile: two discoveries lose).</summary>
        public const float EasySuspicionFactor = 0.75f;
        public const float HardSuspicionFactor = 1.5f;
        /// <summary>The caught rule's grace (and the dog's bark grace), in seconds: a whole number of fixed steps.</summary>
        public const float EasyCaughtGrace = 0.30f;
        public const float HardCaughtGrace = 0.14f;
        /// <summary>The creak gauge's fill time from 0 to 1 while still, in seconds.</summary>
        public const float EasyCreakFillTime = 25f;
        public const float HardCreakFillTime = 16f;

        // ----- M7 title camera (TitleCameraTour): the eye level tour of Resources/Levels/title_house.json behind the title. -----
        /// <summary>
        /// Camera height above the floor, in metres: a piece of furniture's eye level. MENUCAM (2026-11-23): 0.7 (was 1.0,
        /// lowered by 30 percent), then 0.55 at the user's request (45 percent under the original), under the window sills (0.9) and the counter tops; the waypoints' floor clearances are unchanged.
        /// </summary>
        public const float TitleTourHeight = 0.55f;
        /// <summary>Travel speed along the loop on straight stretches, in metres per second.</summary>
        public const float TitleTourSpeed = 0.5f;
        /// <summary>Fraction of <see cref="TitleTourSpeed"/> kept in the sharpest turn (a 90 degree turn over <see cref="TitleTourTurnProbe"/>).</summary>
        public const float TitleTourTurnSpeedFactor = 0.55f;
        /// <summary>Path distance ahead over which the turn rate is measured to slow down, in metres.</summary>
        public const float TitleTourTurnProbe = 1.2f;
        /// <summary>The view aims at points this far ahead along the path (and at half and one and a half times it), in metres.</summary>
        public const float TitleTourLookAhead = 1.4f;
        /// <summary>
        /// Degrees the view looks down from the horizontal. MENUCAM (2026-11-23): 5 (was 7), flattened with the lower height so
        /// the view axis still meets the floor about 8 m ahead (atan(0.7 * tan 7 degrees / 1.0) = 4.9): the same things framed.
        /// Then 4 with the 0.55 height (atan(0.55 * tan 7 degrees / 1.0) = 3.9). CEILING (2026-11-24): -4, a slight upward tilt at the
        /// user's request, so the new room ceilings read in the menu background (negative = looking up).
        /// </summary>
        public const float TitleTourPitch = -4f;
        /// <summary>Horizontal lens shift in normalized device units: the vanishing point sits right of centre, clear of the title column.</summary>
        public const float TitleTourLensShift = 0.3f;
        /// <summary>Spline samples per waypoint segment for the arc length table.</summary>
        public const int TitleTourSamplesPerSegment = 24;

        // ----- M7 level select (LevelSelect, LevelMiniature): the Levels page in the title page's style. -----
        /// <summary>Left edge of the card grid from the screen's left edge, in reference pixels (the title column sits left of it).</summary>
        public const float LevelSelectGridLeft = 640f;
        /// <summary>Right, top and bottom margins of the card grid, in reference pixels.</summary>
        public const float LevelSelectGridRight = 56f;
        public const float LevelSelectGridTop = 64f;
        public const float LevelSelectGridBottom = 64f;
        /// <summary>Gap between two cards, in reference pixels.</summary>
        public const float LevelSelectCardGap = 16f;
        /// <summary>Fraction of a card's height (from the top) taken by the level miniature.</summary>
        public const float LevelSelectMiniatureShare = 0.52f;
        /// <summary>Most watcher icons drawn on a card; more show as "+n".</summary>
        public const int LevelSelectMaxWatcherIcons = 5;
        /// <summary>Size of a level miniature texture, in pixels (drawn once per level, at twice this and box filtered).</summary>
        public const int LevelMiniatureWidth = 240;
        public const int LevelMiniatureHeight = 200;
        /// <summary>Empty border around the house in a miniature, in metres.</summary>
        public const float LevelMiniaturePadding = 0.5f;
        /// <summary>Thinnest wall line in a miniature, in final pixels (real walls are 0.1 m, too thin to see).</summary>
        public const float LevelMiniatureWallPixels = 2.2f;
        /// <summary>Radius of the player start dot in a miniature, in metres (never under 3.5 final pixels).</summary>
        public const float LevelMiniaturePlayerRadius = 0.38f;

        // ----- M7 title logo (TitleLogo): the red chair rendered once at a three-quarter angle, with a short high-sun shadow. -----
        /// <summary>Size of the baked logo frame, in pixels (rendered at twice this and averaged down).</summary>
        // Grown from 400 x 280 with the frame (2026-11-20, the wider pool of light) at the same 190.5 pixels per metre.
        // TITLESCALE (2026-11-23): from 438 x 290, 0.5 m wider on the left and 98 pixels taller on top (the frame's bottom
        // and the chair's place and size on screen kept) for the dog and the human at 1.5 times their old size.
        // TITLEMOVE2 (2026-11-24): from 533, 0.75 m wider on the RIGHT (the left edge, the chair's foot, the height and the
        // scale kept) for the chair's hops, twice as far again (1.56 m).
        public const int TitleLogoWidth = 676;
        public const int TitleLogoHeight = 388;
        /// <summary>Elevation of the high (about 11 am) sun above the logo's ground, in degrees: the shadow is height / tan of it.</summary>
        public const float TitleLogoSunElevation = 62f;
        /// <summary>Heading of the sun's travel on the logo's ground, in degrees from the camera's right toward its depth.</summary>
        public const float TitleLogoSunHeading = 24f;
        /// <summary>The chair's yaw in the logo's frame (180 faces the camera), in degrees.</summary>
        // 220 faced left; 140 (2026-11-21, the product owner's "face right") is its mirror, three-quarter to the right:
        // the same outline height (same gap above the title and below the top), the sun now on its side, not its front.
        public const float TitleLogoChairYaw = 140f;
        /// <summary>Intensity of the soft fill light in front of the chair (baked once): keeps the faces turned from the sun readable.</summary>
        public const float TitleLogoFillIntensity = 0.5f;
        /// <summary>Degrees the logo camera looks down.</summary>
        public const float TitleLogoPitch = 26f;
        /// <summary>Width of ground the orthographic logo camera frames, in metres, and the chair's distance from its left edge.</summary>
        // Widened from 1.8 for the pool of light (2026-11-19), which needs room to fade out inside the frame; then from 2.1
        // (inset 0.85, foot at 0.29) for the wider pool (2026-11-20): the chair keeps its place and size on screen.
        // TITLESCALE (2026-11-23): from 2.3 and 1.02, 0.5 m more floor on the left (the chair's place and size on screen
        // kept): room for the 1.5 times bigger dog's rump and the human's back while they hold the chair on its mark.
        // TITLEMOVE2 (2026-11-24): from 2.8, 0.75 m more floor on the right (the inset from the left edge kept): the chair,
        // hopped 1.56 m away, keeps its right edge about 16 units inside the frame.
        public const float TitleLogoFrameWidth = 3.55f;
        public const float TitleLogoChairInset = 1.52f;
        /// <summary>Where the chair's foot sits, as a fraction of the frame height from the bottom (raised so the pool's
        /// near edge fades out above the frame's bottom).</summary>
        // TITLESCALE: from 0.315 of 290 pixels, the same 91 pixels (53 reference units) of the taller frame.
        public const float TitleLogoFootHeight = 0.2352f;
        /// <summary>The pool of light on the floor: its centre along the shadow from the chair's foot and its radius, in
        /// metres, so it holds the whole short shadow; the fraction of the radius kept at full light before the falloff;
        /// and its opacity at full light over the title band.</summary>
        public const float TitleLogoPoolCentre = 0.12f;
        // Radius raised from 0.9 and core lowered from 0.45 (2026-11-19): a slightly larger pool with a wider soft rim;
        // then from 1.0 (2026-11-20, the product owner's "a little wider"), same core fraction and opacity.
        public const float TitleLogoPoolRadius = 1.15f;
        public const float TitleLogoPoolCore = 0.25f;
        // Lowered from 0.9 (2026-11-19): the pool read too bright; 70 % of the original opacity.
        public const float TitleLogoPoolAlpha = 0.63f;
        /// <summary>Intensity of the warm spot above the pool that lights the chair's seat (baked once, no runtime cost).</summary>
        // Lowered from 1.5 (2026-11-19) together with the pool's opacity.
        public const float TitleLogoSpotIntensity = 1.2f;
        /// <summary>Distance of the logo rig from the world origin, sideways to the sun: far outside every camera's far plane and shadow cascades.</summary>
        public const float TitleLogoRigDistance = 600f;
        /// <summary>The unnamed layer only the two logo cameras render.</summary>
        public const int TitleLogoLayer = 30;
        /// <summary>Shadow darkness at the chair's foot and at the tip of the shadow.</summary>
        public const float TitleLogoShadowNear = 0.95f;
        public const float TitleLogoShadowFar = 0.6f;
        /// <summary>The shadow's penumbra at its tip, in logo pixels (it starts sharp at the foot). Scaled down with the
        /// shorter midday shadow so it still reads as crisp near the feet.</summary>
        public const int TitleLogoShadowBlur = 6;
        /// <summary>Size of the logo on the title page (1920 x 1080 reference) and the offset of its left centre.</summary>
        // The chair in its pool is taller than the first logo (240 x 180): a little smaller, so chair and pool fit between
        // the top of a 20:9 phone and the title; the chair moved right (2026-11-19, the product owner's "a little to the right").
        // Grown with the frame (2026-11-20, from 232 x 162 at 128, 401): same scale, the chair's foot at the same point.
        // Raised by 1 unit (2026-11-20): the rounded chair's outline is a fraction of a unit taller, and its foot keeps
        // its 2 unit gap above the title's letters.
        // TITLESCALE (2026-11-23): from 254 x 168 at 109, 399 (the frame from y 315 to 483, the top of a 20:9 phone): the
        // frame grows 55 units to the left and up to 540, the top of a 16:9 screen, at the same 110.4 units per metre; its
        // bottom, the chair's foot (x 221.6, y 368) and so the chair, the letters and the menu do not move. On a 20:9 phone
        // the screen's own top edge crops the bigger human's head and shoulders (docs/next/progress/GRIP.md).
        // TITLEMOVE2 (2026-11-24): from 309.2, the frame's 0.75 m more on the right at the same 110.4 units per metre (its
        // left edge, height and centre line kept).
        public const float TitleLogoUiWidth = 392f;
        public const float TitleLogoUiHeight = 225f;
        public const float TitleLogoUiX = 53.8f;
        public const float TitleLogoUiY = 427.5f;
        // ----- Title logo loop (TitleLogo.Sample, 2026-11-20; reworked 2026-11-21): the chair hops off while the spot
        // looks away, gets caught in the light, and the house dog drags it home. -----
        /// <summary>Length of one loop of the title chair, in seconds, and the share of it spent perfectly still in the light.</summary>
        // From 10 s at 0.85 (2026-11-21): an 11 s act (it was 1.5 s), then the still pose held 15 s (the product owner's
        // minimum after the chair is back).
        // TITLEMOVE2 (2026-11-24): from 26 s, a 16.2 s act (the chair goes twice as far again, the pull home at the same
        // speed takes twice as long, the carriers turn round for 0.7 s), the still pose still held 15 s.
        public const float TitleLogoCycleSeconds = 31.2f;
        public const float TitleLogoStillFraction = 15f / 31.2f;
        /// <summary>Where in the loop the logo starts when it appears: inside the still part, so the first act comes 2.5 s in.</summary>
        public const float TitleLogoStartPhase = 12.5f / 31.2f;
        /// <summary>The chair's gentle hops to the right while the spot is away: how many, the floor each covers and the
        /// top of each (a lift of the chair's picture, no squash, no tilt), in metres; and the top of its single startled
        /// jump when the light catches it.</summary>
        // Low on purpose: the chair's top has about 8 reference units left under the top of a 20:9 phone.
        // TITLEMOVE (2026-11-23, product owner): the stride doubled from 0.13 (3 hops, same rhythm, 0.78 m away instead of
        // 0.39): the chair's right edge stays about 17 units inside the logo's frame (no frame change), and the carriers
        // bring it home at twice their old speed in the same 2.8 s (TitleLogo's DragStart to DragEnd).
        // TITLEMOVE2 (2026-11-24, product owner): twice as far again, 1.56 m: 4 hops of 0.39 m at the same pitch (three of
        // 0.52 m with the same low lift read as a skid), a little higher (from 0.045; the startle stays the highest jump).
        public const int TitleLogoChairHops = 4;
        public const float TitleLogoChairHopStride = 0.39f;
        public const float TitleLogoChairHopHeight = 0.05f;
        public const float TitleLogoChairStartle = 0.065f;
        /// <summary>How far the pool of light slides away to the left, in metres of floor, and the light left when it is away.</summary>
        public const float TitleLogoSpotDrift = 0.45f;
        public const float TitleLogoSpotAway = 0.12f;
        /// <summary>The dog dragging the chair home: the chair's tilt at the grab and in the tug's wobble (degrees), and its
        /// lift off the floor (metres; the in-game drag lifts 0.06 m, Tuning.DogDragLift).</summary>
        public const float TitleLogoDragWobble = 1.5f;
        public const float TitleLogoDragLift = 0.02f;
        /// <summary>The dog in the logo: where its body stands, sideways from the chair's foot, when it holds the chair on its
        /// mark (its snout at the chair's left edge), in metres; its yaw (90 faces right; a little more turns it toward the
        /// camera), in degrees.</summary>
        // DOGBIG: from -0.62 (the Shiba, snout 0.30 m ahead of its body on screen) to -0.67: the Husky at
        // TitleLogoDogScale reaches 0.355 m ahead, so its snout stays on the chair's left edge (0.32 m left of the foot).
        // TITLESCALE (2026-11-23): the 1.5 times bigger dog stands further left so its lowered snout bites the same spot
        // of the chair's left back leg (its head bends further down, so its reach grows less than 1.5 times): measured in the bake, its snout lands 0.274 m left of the chair's foot, as the 0.8 dog's did.
        public const float TitleLogoDogGrip = -0.808f;
        public const float TitleLogoDogYaw = 110f;
        /// <summary>
        /// DOGBIG: the logo's dog at this share of its in-game size (the Husky at 1.5 times the Shiba): 0.8, so 1.2 times the
        /// old logo dog. At full size its 0.72 m on screen would not fit between the frame's left edge and the chair (0.70 m)
        /// with its rump inside the frame; at 0.8 its rump stays about 0.1 m inside while it holds the chair on its mark.
        /// TITLESCALE (2026-11-23, product owner): 1.5 times bigger, 1.2 (the frame grew 0.5 m on the left for its rump).
        /// </summary>
        public const float TitleLogoDogScale = 1.2f;
        /// <summary>The dog's walk: the floor between two swaps of its two baked frames is half this stride; its bob, in
        /// metres; the floor over which it fades in and out at the frame's left edge, in metres; its wag, in degrees; and
        /// its shadow's darkness at full pool light.</summary>
        // DOGBIG: from 0.24 for the Shiba, times the logo dog's 1.2 growth. TITLESCALE: stride and bob times 1.5 (from
        // 0.29 and 0.01) with the dog.
        public const float TitleLogoDogStride = 0.435f;
        public const float TitleLogoDogBob = 0.015f;
        // TITLESCALE: from 0.35 (also the human's): the 1.5 times bigger dog's picture reaches about 0.49 m behind its feet, so
        // it turns opaque only once wholly inside the frame; it stays opaque where it backs off the chair (0.637 m in); and
        // the human's faster walk out (0.5 m more floor in the same time) still fades to nothing at the loop's end.
        public const float TitleLogoDogFade = 0.55f;
        public const float TitleLogoDogWag = 6f;
        public const float TitleLogoDogShadow = 0.7f;
        /// <summary>
        /// GRIP (2026-11-22): the logo dog bites the chair's left back leg this high (metres above the floor; it lowers its
        /// head to it, GripMath), the in-game dog's low grip instead of the old snout at its own height.
        /// </summary>
        public const float TitleLogoDogBiteHeight = 0.30f;
        /// <summary>
        /// GRIP (2026-11-22, product owner): the loops alternate, one with the dog, the next with a human who walks in from
        /// the left, puts his hands on the top of the chair's backrest (the in-game grip, GripDef) and pulls it home. The
        /// human at this share of his in-game size: at the full 1.74 m his head would leave the top of a 20:9 phone (the
        /// frame has 1.04 m of floor above the chair's foot); at 0.6 his head stays about 5 units under it.
        /// TITLESCALE (2026-11-23, product owner): 1.5 times bigger, 0.9. He no longer fits between the title's letters
        /// and the top of a 20:9 phone, so the frame now reaches the top of a 16:9 screen (where he shows whole) and on a
        /// phone the screen's top edge crops his head and shoulders, as a close camera would (GRIP.md).
        /// </summary>
        public const float TitleLogoHumanScale = 0.9f;
        /// <summary>The logo human's yaw (90 faces right; less turns him a little away from the camera, toward the chair's
        /// back), and how far his feet stand behind the middle of his two hands, metres.</summary>
        public const float TitleLogoHumanYaw = 85f;
        // TITLESCALE: from 0.30 at 0.6, where the rail was above his shoulders and his left hand at the end of his reach.
        // At 0.9 the rail is 0.29 m under his 1.22 m shoulders: 0.32 m keeps both elbows bent (wrists at 0.91 and 0.76 of
        // his 0.50 m arm) and the rail 0.13 m ahead of his belly.
        public const float TitleLogoHumanReach = 0.32f;
        /// <summary>Where the logo human's hands rest across the top rail of the chair's backrest (the chair's frame, x;
        /// the height and depth are GripDef's chair wrists): the right hand on the rail's near end, the left further along.</summary>
        public const float TitleLogoHumanRightX = 0.17f;
        public const float TitleLogoHumanLeftX = 0.03f;
        /// <summary>The logo human's walk bob, metres (none while he holds the chair: his picture then carries it).</summary>
        // TITLESCALE: times 1.5 with him (from 0.006).
        public const float TitleLogoHumanBob = 0.009f;
        /// <summary>
        /// TITLEMOVE2 (2026-11-24, product owner): the carriers turn round to leave through baked frames of the real model
        /// (no more mirrored picture). At the turn's middle the chest leads the hips by TitleLogo*TurnBend degrees (the dog's
        /// spine, the human's) and the head leads the chest by TitleLogo*TurnHead more, both easing in and out with the turn;
        /// the legs step through TitleLogoTurnSteps walk cycles, their stride damped to TitleLogoTurnStride of the walk's at
        /// the middle (short steps on the spot, not a walk in place).
        /// </summary>
        public const float TitleLogoDogTurnBend = 36f;
        public const float TitleLogoDogTurnHead = 24f;
        public const float TitleLogoHumanTurnBend = 26f;
        public const float TitleLogoHumanTurnHead = 18f;
        public const float TitleLogoTurnSteps = 1f;
        public const float TitleLogoTurnStride = 0.45f;

        // ----- M7 options page (Menu.BuildOptions, OptionsRow): the title page's left column style, reused. -----
        /// <summary>Left margin of the title and every row, in reference pixels (the title page's own margin).</summary>
        public const float OptionsMargin = 150f;
        /// <summary>Width of the dark translucent band behind the column, in reference pixels.</summary>
        public const float OptionsPanelWidth = 1180f;
        /// <summary>Size of a row's icon, and its inset from the row's left edge, in reference pixels.</summary>
        public const float OptionsIconSize = 52f;
        public const float OptionsIconInset = 14f;
        /// <summary>Left offset of a row's label text, clear of the icon, in reference pixels.</summary>
        public const float OptionsLabelOffset = 82f;
        /// <summary>M7 walls pass: the label opacity of a row whose value the current choices do not use (Wall opacity while the
        /// walls are lowered or off): dimmed, still selectable.</summary>
        public const float OptionsUnusedAlpha = 0.45f;
        /// <summary>Size of a row's decorative cycle arrows, and their inset from the row's right edge.</summary>
        public const float OptionsArrowSize = 26f;
        public const float OptionsArrowInset = 20f;

        // ----- M7 heads and clothes (CharacterLook): the product owner's head images and clothes on the human inhabitants. -----
        /// <summary>Resources name of the clothes atlas: shirt front and back over trousers front and back, in their real colours (sRGB, readable).</summary>
        public const string ClothesAtlasResource = "CharacterClothesAtlas";
        /// <summary>
        /// Clothes: the personality's colour on the shirt (its prints keep their real colours): a collar band over the
        /// shoulders and a band at the hem, fractions of the shirt's height from its top and from its hem.
        /// </summary>
        public const float ClothesCollarBand = 0.13f;
        public const float ClothesHemBand = 0.08f;
        /// <summary>Clothes: how much of the fabric's shading the bands keep (an exponent on the luminance ratio).</summary>
        public const float ClothesBandContrast = 0.5f;

        // ----- Stars (idea 5, docs/next/progress/STARS.md): three stars per level and difficulty (Stars.cs). -----
        // The reference is the audit's earliest exit for the played difficulty: the "at" of the last point of the level's
        // designerRoute (designerRouteHard at Difficile), plus StarsReferenceSlack. Why generous factors: the solver plays
        // a perfect schedule from the first fixed step, while a human reads the room, waits for a safe look-away and
        // arrives on the doormat 0.3 to 1.8 s after the last point's departure (docs/levels_v2/wave1/numbers.md 2).
        // Level 1 (route 11.6 s): 3 stars at or under 20.4 s, 2 stars under 34.0 s, 1 star for any win.
        /// <summary>Stars per level: the win panel's row and the level select's total (20 levels, 60 stars since levels.json rev 3).</summary>
        public const int StarsPerLevel = 3;
        /// <summary>Seconds added to the route's last point before the factors (the doormat arrival, the first look).</summary>
        public const float StarsReferenceSlack = 2f;
        /// <summary>Three stars at or under the reference times this.</summary>
        public const float StarsThreeFactor = 1.5f;
        /// <summary>Two stars under the reference times this (three under <see cref="StarsThreeFactor"/>); one star otherwise.</summary>
        public const float StarsTwoFactor = 2.5f;
        /// <summary>The win panel's reveal: seconds between two stars popping in, and the pop's own length (StarRow).</summary>
        public const float StarsRevealStagger = 0.22f;
        public const float StarsRevealSeconds = 0.35f;
    }
}
