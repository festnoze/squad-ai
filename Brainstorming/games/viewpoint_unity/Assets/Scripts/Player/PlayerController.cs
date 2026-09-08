using System;
using UnityEngine;
using UnityEngine.Rendering.Universal;

namespace Viewpoint
{
    /// <summary>
    /// First person controller: movement, mouse look and the interaction ray
    /// (PRD section 8). The transform origin is at the FEET, the camera sits at
    /// the eye, and the PhotoPlacer is a child of the camera with an identity
    /// transform: that is what makes the camera transform the placement anchor.
    /// </summary>
    [RequireComponent(typeof(CharacterController))]
    public sealed class PlayerController : MonoBehaviour
    {
        public const float WalkSpeed = 5f;
        public const float SprintSpeed = 8f;
        public const float Accel = 12f;
        public const float JumpVelocity = 6.5f;
        public const float Gravity = 14f;
        public const float MouseSensitivity = 0.0022f;
        public const float InteractRange = 1.7f;
        public const float EyeHeight = 1.62f;

        /// Pitch clamp of the original, in radians (PRD section 8).
        public const float MaxPitch = 1.45f;

        /// <summary>
        /// Vertical fov of the player camera. Public because the HUD derives the
        /// raised-picture and viewfinder square from it together with
        /// PhotoMath.PhotoFovDeg (PRD 12.2); a second literal 75 in the UI is
        /// exactly the drift that would break the illusion silently.
        /// </summary>
        public const float CameraFov = 75f;
        private const float CameraNear = 0.05f;
        private const float CameraFar = 400f;

        // Collider of PRD section 4.3: a capsule spanning the feet to 1.75 m.
        private const float ControllerRadius = 0.35f;
        private const float ControllerHeight = 1.75f;
        private const float ControllerSlopeLimit = 45f;
        private const float ControllerStepOffset = 0.3f;
        private const float ControllerSkinWidth = 0.03f;

        /// <summary>
        /// Downward bias added to every grounded sweep. CharacterController only
        /// reports isGrounded from the sweep it just performed, so a purely
        /// horizontal move over flat ground would lose the contact every step.
        /// </summary>
        private const float GroundStick = 0.05f;

        /// <summary>
        /// The ground probe sphere is kept this far inside the capsule so the
        /// cast never starts already overlapping the floor (which would report a
        /// zero distance and a zero normal).
        /// </summary>
        private const float GroundProbeInset = 0.05f;

        /// <summary>
        /// How far under the feet the probe still calls it ground. This is the
        /// floor_snap_length of the original (0.1) plus the skin width: it is
        /// what keeps a walk down the 33 degree stairs ramp from turning into a
        /// series of hops.
        /// </summary>
        private const float GroundProbeReach = 0.13f;

        // ---- Camera feel (PRD_VISUAL 4.9, V-ANIM-01) -------------------------
        //
        // Everything in this block is PRESENTATION, and every number of it lives
        // on the CAMERA transform. That is the whole safety argument of the
        // feature and it deserves saying once, here, because it looks backwards
        // at first: the PhotoPlacer is a child of the camera at identity, so a
        // bob, a landing dip or a roll moves the picture AND the placement
        // anchor together. The "picture equals placement" identity therefore
        // holds by construction rather than by correction, exactly as it does in
        // Viewfinder (PRD_VISUAL section 7, the head-bob risk row). Nothing here
        // may ever be animated on the placer, and nothing here may ever be
        // compensated for on the placer.
        //
        // What must never follow from any of it: a change of WHEN something
        // happens. No collider, no group, no counter, no event and no held id
        // moves by a frame; only the look of the camera lags.

        /// <summary>
        /// Vertical amplitude of the walking bob, in metres: V-ANIM-01's "2 cm",
        /// read as an amplitude, so the eye travels 4 cm from trough to crest at
        /// a walk. Halved at full sprint (<see cref="BobSprintScale"/>).
        /// </summary>
        private const float BobAmplitude = 0.02f;

        /// <summary>
        /// Bob frequency at exactly <see cref="WalkSpeed"/>, in hertz. It scales
        /// with the ground speed from there, so a sprint bobs faster rather than
        /// keeping a walking cadence under a running body, and a body creeping
        /// along at a fraction of the walk speed bobs slower.
        /// </summary>
        private const float BobHz = 1.8f;

        /// Amplitude factor at full sprint: the bob is halved, not doubled.
        private const float BobSprintScale = 0.5f;

        /// <summary>
        /// Seconds the bob amplitude takes to travel the whole 2 cm, in either
        /// direction. It exists so stopping is not a snap: the phase keeps
        /// running while the amplitude falls, so the eye slides back to the eye
        /// height instead of jumping there from wherever the sine was.
        ///
        /// It also has to land on EXACTLY zero, not merely on something small,
        /// which is why the fade is a MoveTowards and not an exponential: a
        /// standing player must measure 1.62 m to the last bit.
        /// verify-player.ps1 allows 0.1 m of slack and would pass either way,
        /// but the smoke probe measures placements against the eye with
        /// tolerances as tight as 0.01 m, and those are worth keeping exact
        /// rather than merely inside a margin.
        /// </summary>
        private const float BobFadeSeconds = 0.15f;

        /// <summary>
        /// Ground speed under which the player counts as standing still, in
        /// m/s. It exists for exactness and not for feel: releasing the keys
        /// leaves <see cref="_velocity"/> decaying by the Accel lerp, which
        /// approaches zero without ever reaching it for a good ten seconds, so
        /// without a deadband the target amplitude stays a positive nothing, the
        /// fade never lands on 0f and the phase creeps on forever. Five
        /// centimetres a second is a body that is not walking by any measure,
        /// and on the far side of it the bob is EXACTLY zero rather than
        /// thirty nanometres.
        /// </summary>
        private const float BobStopSpeed = 0.05f;

        /// Degrees of vertical fov the sprint adds on top of <see cref="CameraFov"/>.
        private const float FovSprintBoost = 2f;

        /// Seconds the fov takes to cross those two degrees, in either direction.
        private const float FovBoostSeconds = 0.25f;

        /// Peak depth of the landing dip, in metres (V-ANIM-01's "3 cm").
        private const float DipDepth = 0.03f;

        /// A drop shorter than this does not dip: V-ANIM-01's "more than 1 m".
        private const float DipFallMeters = 1f;

        /// <summary>
        /// Rate of the dip's decay, in reciprocal seconds. The dip is the
        /// critically damped impulse response written in closed form,
        ///
        ///     offset(t) = -DipDepth * u * exp(1 - u),   u = DipFrequency * t
        ///
        /// which peaks at exactly -DipDepth when u = 1, i.e. 45 ms after the
        /// landing, and is back inside a tenth of a millimetre by u = 10.
        /// The closed form is deliberate: an integrated spring at this stiffness
        /// needs dt below about 1/DipFrequency to stay stable, and one long
        /// frame would then throw the camera through the floor. This shape is
        /// exact at any frame rate.
        /// </summary>
        private const float DipFrequency = 22f;

        /// Where the dip is over: u = 10 is 0.45 s and 0.04 mm of residue.
        private const float DipEndPhase = 10f;

        /// Maximum roll lag on a quick yaw, in degrees (V-ANIM-01's "1.5 degree").
        private const float RollMaxDegrees = 1.5f;

        /// <summary>
        /// Yaw rate that earns the full <see cref="RollMaxDegrees"/>, in degrees
        /// per second. 400 deg/s is a genuine flick: at the 0.0022 rad per count
        /// of <see cref="MouseSensitivity"/> it takes about 3200 mouse counts a
        /// second, which is a hand crossing a mouse mat in a tenth of a second.
        /// Ordinary aiming stays well under a degree of roll.
        /// </summary>
        private const float RollFullRateDegrees = 400f;

        /// <summary>
        /// Time constant of the yaw-rate low pass, in seconds. This single stage
        /// is what makes the roll a LAG rather than a mirror of the mouse: the
        /// tilt builds over about a tenth of a second and unwinds over three
        /// tenths, which is the whole effect.
        /// </summary>
        private const float RollLagSeconds = 0.09f;

        /// <summary>
        /// Under this many degrees the roll is set to EXACTLY zero, which is
        /// what lets a settled camera carry no roll at all and this class stop
        /// writing the camera's rotation entirely (see <see cref="_rollWritten"/>).
        /// A five hundredth of a degree is three hundredths of a pixel on a
        /// 1080p frame at this fov, so nothing is lost by rounding it away.
        /// </summary>
        private const float RollSnapDegrees = 0.002f;

        /// Steeper than the slope limit is a wall, not a floor.
        private static readonly float MinFloorNormalY = Mathf.Cos(ControllerSlopeLimit * Mathf.Deg2Rad);

        private static readonly float MaxPitchDegrees = MaxPitch * Mathf.Rad2Deg;

        /// <summary>
        /// Fired once when the player falls below the kill plane of the level.
        /// Losing costs the whole level: Main rebuilds it from its definition.
        /// </summary>
        public event Action FellOut;

        public UnityEngine.Camera Camera
        {
            get { return _camera; }
        }

        public PhotoPlacer Placer
        {
            get { return _placer; }
        }

        /// <summary>
        /// False cuts input and movement: menus, fades, rewind, after a fall.
        /// </summary>
        public bool ControlEnabled { get; set; }

        /// <summary>
        /// True while the camera is raised to the eye: the HUD frames what the
        /// shot would capture, and the shutter answers only in this state.
        /// </summary>
        public bool Viewfinder { get; private set; }

        /// <summary>
        /// Prompt of whatever interactable the crosshair currently points at,
        /// polled by Main for the HUD. Empty when nothing is in reach.
        /// </summary>
        public string InteractPrompt { get; private set; }

        /// <summary>
        /// The port of the original's is_on_floor(), which the probes of PRD
        /// section 17.3 read at stages 1, 6 and 18. CharacterController.isGrounded
        /// only answers for the sweep it last ran, so a body that was just
        /// teleported (or that has not stepped since the controls came back)
        /// would report a stale flag: the short probe under the feet settles it.
        /// </summary>
        public bool IsGrounded
        {
            get
            {
                EnsureRig();
                if (_controller.isGrounded)
                {
                    return true;
                }
                float drop;
                return GroundBelow(out drop);
            }
        }

        /// <summary>
        /// Velocity in UNITY space. Rewind playback zeroes it when it drops the
        /// body back onto an older sample, otherwise the fall it was in the
        /// middle of would resume the moment the controls come back.
        /// </summary>
        public Vector3 Velocity
        {
            get { return _velocity; }
            set { _velocity = value; }
        }

        private UnityEngine.Camera _camera;
        private PhotoPlacer _placer;
        private CharacterController _controller;
        private Transform _levelRoot;

        private Vector3 _velocity;
        private float _yawDegrees;
        private float _pitchDegrees;

        /// Spawn pose in DESIGN space, converted only when the body is placed.
        private Vector3 _spawnDesign;
        private float _spawnYaw;
        private float _killY = -10f;

        private IInteractable _interactTarget;
        private Component _interactOwner;

        /// <summary>
        /// A jump pressed during a render frame with no fixed step would be lost
        /// otherwise: the press is latched here and spent by the next step.
        /// </summary>
        private bool _jumpQueued;

        /// True between falling below killY and the level being rebuilt.
        private bool _fell;

        // ---- Camera feel state, all of it presentation -----------------------

        /// <summary>
        /// Horizontal speed the body ACTUALLY covered on the last physics step,
        /// in m/s, measured on the transform rather than read from
        /// <see cref="_velocity"/>. The difference matters: the velocity is the
        /// INTENT, and a player leaning into a wall keeps a full 5 m/s of it
        /// while going nowhere at all. A head bob on a body that is not moving
        /// is exactly the artefact V-ANIM-01's acceptance ("a walking player's
        /// view moves gently") does not describe.
        /// </summary>
        private float _groundSpeed;

        /// The grounded verdict of the last physics step, as the bob's gate.
        private bool _groundedLast = true;

        private float _bobPhase;
        private float _bobAmplitude;
        private float _bobOffset;

        private bool _dipActive;
        private float _dipElapsed;
        private float _dipOffset;

        private float _rollDegrees;

        /// <summary>
        /// True while this class has a roll written into the camera's local
        /// rotation. It is what lets the camera feel keep its hands off that
        /// rotation entirely while the roll is zero: with no roll the rotation
        /// stays bit for bit what <see cref="ApplyLook"/> and
        /// <see cref="SetLook"/> wrote, so nothing here can fight them or drift
        /// against them, and one frame of writing is enough to take a roll back
        /// off again.
        /// </summary>
        private bool _rollWritten;

        private float _yawRateDegrees;
        private float _yawSeen;

        private float _fovDegrees = CameraFov;

        /// <summary>
        /// Whether the body was on the ground at the last step, and how high it
        /// was when the descent began. <see cref="_fallTracked"/> is the honest
        /// part: a fall is only a fall when the feet LEFT a floor they were
        /// standing on, so a body dropped into the air by <see cref="Teleport"/>
        /// (the spawn drop of every level, rewind playback, and every probe
        /// stance) is being placed rather than falling and earns no landing dip.
        /// </summary>
        private bool _wasGrounded = true;
        private bool _fallTracked;
        private float _fallApexY;

        private void Awake()
        {
            InteractPrompt = "";
            EnsureRig();
        }

        /// <summary>
        /// Builds (or adopts) the collider, the camera and the placer. Idempotent
        /// and called from every public entry point, because Main may call
        /// Setup before this component has had its own Awake.
        /// </summary>
        private void EnsureRig()
        {
            if (_controller == null)
            {
                _controller = GetComponent<CharacterController>();
                if (_controller == null)
                {
                    _controller = gameObject.AddComponent<CharacterController>();
                }
                _controller.radius = ControllerRadius;
                _controller.height = ControllerHeight;
                _controller.center = new Vector3(0f, ControllerHeight * 0.5f, 0f);
                _controller.slopeLimit = ControllerSlopeLimit;
                _controller.stepOffset = ControllerStepOffset;
                _controller.skinWidth = ControllerSkinWidth;
                // The default 0.001 would swallow the small steps of a lerped
                // start and make the first frames of a walk feel sticky.
                _controller.minMoveDistance = 0f;
                gameObject.layer = Layers.Player;
            }

            if (_camera == null)
            {
                _camera = GetComponentInChildren<UnityEngine.Camera>(true);
                if (_camera == null)
                {
                    GameObject cameraObject = new GameObject("Camera");
                    cameraObject.transform.SetParent(transform, false);
                    _camera = cameraObject.AddComponent<UnityEngine.Camera>();
                }
                Transform cameraTransform = _camera.transform;
                cameraTransform.SetParent(transform, false);
                cameraTransform.localPosition = new Vector3(0f, EyeHeight, 0f);
                cameraTransform.localRotation = Quaternion.identity;
                cameraTransform.localScale = Vector3.one;
                _camera.fieldOfView = CameraFov;
                _camera.nearClipPlane = CameraNear;
                _camera.farClipPlane = CameraFar;
                // The snap studio lives on its own layer far under the world and
                // must never appear in the game view (PRD section 15.6).
                _camera.cullingMask = ~Layers.PhotoStudioMask;

                ApplyCameraRendering(_camera);

                _camera.gameObject.layer = Layers.Player;
                _camera.gameObject.tag = "MainCamera";
            }

            if (_placer == null)
            {
                _placer = GetComponentInChildren<PhotoPlacer>(true);
                if (_placer == null)
                {
                    GameObject placerObject = new GameObject("Placer");
                    placerObject.transform.SetParent(_camera.transform, false);
                    _placer = placerObject.AddComponent<PhotoPlacer>();
                }
                Transform placerTransform = _placer.transform;
                placerTransform.SetParent(_camera.transform, false);
                placerTransform.localPosition = Vector3.zero;
                placerTransform.localRotation = Quaternion.identity;
                placerTransform.localScale = Vector3.one;
            }
        }

        /// <summary>
        /// Turns on everything the visual upgrade renders THROUGH this camera
        /// (PRD_VISUAL V-PIPE-01, V-PIPE-04, V-POST-01 to V-POST-03, V-SNAP-01).
        ///
        /// The line that matters most here is renderPostProcessing, and its
        /// absence is worth a paragraph because it cost an entire tier. URP's
        /// UniversalAdditionalCameraData defaults it to FALSE, and
        /// UniversalRenderer gates BOTH the uber post pass and the colour grading
        /// LUT on it. A camera built from code therefore renders no bloom, no
        /// vignette, no colour adjustments, no tonemapping and no HDR grading,
        /// however carefully those are authored in the volume profiles - and no
        /// SMAA either, since that runs in the same post chain. Every number of
        /// PRD_VISUAL 4.2 was correct in its asset and inert on screen until this
        /// flag was set. Nothing in the harness could see it: the game built, ran,
        /// threw nothing and photographed itself quite happily.
        ///
        /// It also has to be true for the picture identity of PRD_VISUAL 3.4. The
        /// studio camera enables post for itself, so leaving it off HERE would
        /// make the polaroid tonally different from the world it promises, which
        /// is worse than both cameras having no post at all.
        ///
        /// allowHDR and allowMSAA are left untouched at the component default
        /// (both true). They are opt-OUT flags, and writing false to either would
        /// throw away the HDR grading and the 4x MSAA the render pipeline asset
        /// now pays for.
        ///
        /// Isolated exactly as every step of Main.Awake is: this runs inside
        /// Awake, and an exception here would cancel the REST of EnsureRig,
        /// leaving the camera without its layer and tag and the PhotoPlacer (the
        /// placement anchor the whole game rests on) never built. A run whose
        /// active pipeline is not URP degrades to "no post", never to "no player".
        /// </summary>
        private static void ApplyCameraRendering(UnityEngine.Camera camera)
        {
            try
            {
                // Adds the component when it is missing, which is the case here:
                // this camera is built from code with AddComponent, so nothing
                // ever attached one.
                UniversalAdditionalCameraData data = camera.GetUniversalAdditionalCameraData();
                data.renderPostProcessing = true;

                // SMAA on TOP of the pipeline's MSAA. MSAA samples COVERAGE, so
                // it only ever fixes geometry silhouettes: the specular rim of a
                // lavender wall and the emissive edge of a charged battery are
                // shading, and they crawl straight through it. SMAA runs on the
                // resolved image and catches exactly those.
                //
                // Only on the desktop tier. PRD_VISUAL V-PIPE-01 gives the mobile
                // tier "MSAA 2, no SMAA", and Mobile_RPAsset is authored that way,
                // so applying SMAA unconditionally here would quietly overrule the
                // asset on every mobile build. The active pipeline asset is the
                // thing that knows which tier is running, so ask IT rather than
                // reading a platform define: a desktop build with the mobile asset
                // selected must behave like the mobile tier.
                UniversalRenderPipelineAsset pipeline = UniversalRenderPipeline.asset;
                bool desktopTier = pipeline == null || pipeline.msaaSampleCount >= 4;
                data.antialiasing = desktopTier
                    ? AntialiasingMode.SubpixelMorphologicalAntiAliasing
                    : AntialiasingMode.None;
                data.antialiasingQuality = AntialiasingQuality.High;
            }
            catch (Exception e)
            {
                // This log DOES trip verify-player.ps1, which greps the whole
                // player log for the bare word "Exception" and fails on a hit,
                // and that is the intended behaviour rather than an oversight.
                //
                // The catch exists so a run without URP still gets a PLAYER, not
                // so the failure can pass quietly: if this fires, post-processing
                // is off, and with it bloom, vignette, colour adjustments, HDR
                // grading and SMAA. That is the entire visual tier gone, on a
                // build that would otherwise start, run, throw nothing and
                // photograph itself looking merely a bit flat. Exactly the class
                // of silent failure this harness exists to catch, so it is left
                // loud on purpose. Keep the exception in the message.
                Debug.LogWarning("[PlayerController] Camera post-processing unavailable, "
                    + "the visual tier is inert: " + e);
            }
        }

        public void Setup(Transform levelRoot)
        {
            EnsureRig();
            _levelRoot = levelRoot;
            _placer.Setup(levelRoot);
        }

        /// <summary>
        /// Spawn pose of the level. The position and the yaw arrive in DESIGN
        /// space, straight from the level definition.
        /// </summary>
        public void SetSpawn(Vector3 pos, float yaw, float killY)
        {
            _spawnDesign = pos;
            _spawnYaw = yaw;
            _killY = killY;
            Respawn();
        }

        public void Respawn()
        {
            EnsureRig();
            Teleport(DesignSpace.ToUnity(_spawnDesign));
            _yawDegrees = DesignSpace.YawToUnityDegrees(_spawnYaw);
            _pitchDegrees = 0f;
            transform.localRotation = Quaternion.Euler(0f, _yawDegrees, 0f);
            _camera.transform.localRotation = Quaternion.identity;
            _velocity = Vector3.zero;
            _fell = false;
            Viewfinder = false;
            _jumpQueued = false;
            _interactTarget = null;
            _interactOwner = null;
            InteractPrompt = "";
        }

        /// <summary>
        /// Moves the body without a sweep, in UNITY space. The controller keeps
        /// its own copy of the pose, so it has to be off while the transform is
        /// written. Rewind playback and the probes both go through here.
        /// </summary>
        public void Teleport(Vector3 position)
        {
            EnsureRig();
            bool wasEnabled = _controller.enabled;
            _controller.enabled = false;
            transform.position = position;
            _controller.enabled = wasEnabled;
            _velocity = Vector3.zero;
            // A teleported body has no history: the bob, the dip and the roll
            // are settled HERE and not over the next few frames, because the
            // probes place a stance and measure it in the same frame. Anything
            // left mid swing would be measured as the world's geometry.
            ClearCameraFeel();
        }

        /// <summary>
        /// Aims the view. Yaw turns the body, pitch tilts the camera, both in
        /// degrees and in UNITY signs: a positive pitch looks DOWN.
        /// </summary>
        public void SetLook(float yawDegrees, float pitchDegrees)
        {
            EnsureRig();
            _yawDegrees = yawDegrees;
            _pitchDegrees = Mathf.Clamp(pitchDegrees, -MaxPitchDegrees, MaxPitchDegrees);
            transform.localRotation = Quaternion.Euler(0f, _yawDegrees, 0f);
            _camera.transform.localRotation = Quaternion.Euler(_pitchDegrees, 0f, 0f);
            // LAST, and after the yaw is stored: an aim written from outside is
            // not a turn of the head, so it earns no roll lag, and clearing the
            // feel here is also what stops the yaw JUMP of a rewind sample or a
            // probe stance from reading as a flick of the mouse.
            ClearCameraFeel();
        }

        private void Update()
        {
            EnsureRig();
            if (!ControlEnabled)
            {
                // The original polls the jump inside _physics_process, which is
                // gated the same way: a press swallowed by a menu must not be
                // spent the moment play resumes.
                _jumpQueued = false;
                // Rewind playback and the probes write the pose directly while
                // the controls are off. Reading it back here means the next look
                // starts from where they left the view, not from a stale angle.
                ReadLookFromTransform();
                return;
            }

            if (ViewpointInput.JumpPressed)
            {
                _jumpQueued = true;
            }
            ApplyLook();
            ApplyActions();
        }

        private void ApplyLook()
        {
            // The look answers only while the cursor is captured, as in the
            // original. Main locks it when play starts and frees it in menus.
            if (Cursor.lockState != CursorLockMode.Locked && !ViewpointInput.SimulatedInput)
            {
                return;
            }
            Vector2 look = ViewpointInput.LookDelta;
            if (look.sqrMagnitude <= 0f)
            {
                return;
            }
            // Mirrored space: moving the mouse right turns the view right, which
            // is a POSITIVE yaw in Unity where the original used a negative one.
            _yawDegrees += look.x * MouseSensitivity * Mathf.Rad2Deg;
            // The Input System reports y upwards, and a positive pitch on the
            // camera looks down: pushing the mouse up must lower the angle.
            _pitchDegrees -= look.y * MouseSensitivity * Mathf.Rad2Deg;
            _pitchDegrees = Mathf.Clamp(_pitchDegrees, -MaxPitchDegrees, MaxPitchDegrees);
            transform.localRotation = Quaternion.Euler(0f, _yawDegrees, 0f);
            _camera.transform.localRotation = Quaternion.Euler(_pitchDegrees, 0f, 0f);
        }

        private void ReadLookFromTransform()
        {
            _yawDegrees = transform.localEulerAngles.y;
            float pitch = _camera.transform.localEulerAngles.x;
            if (pitch > 180f)
            {
                pitch -= 360f;
            }
            _pitchDegrees = pitch;
        }

        private void ApplyActions()
        {
            if (ViewpointInput.InteractPressed)
            {
                TryInteract();
            }
            if (ViewpointInput.PlacePressed)
            {
                if (HandFull)
                {
                    _placer.Place();
                }
                else
                {
                    // The shutter only answers through the viewfinder: aim first
                    // (right click), shoot second.
                    CapturePhoto();
                }
            }
            if (ViewpointInput.RaisePressed)
            {
                if (HandFull)
                {
                    _placer.RaiseToggle();
                }
                else
                {
                    ToggleViewfinder();
                }
            }
            if (ViewpointInput.DropPressed)
            {
                _placer.Drop();
            }
            if (ViewpointInput.WheelDown)
            {
                _placer.RotateHeld(1);
            }
            if (ViewpointInput.WheelUp)
            {
                _placer.RotateHeld(-1);
            }
        }

        private void TryInteract()
        {
            if (_interactTarget != null && Alive(_interactOwner))
            {
                _interactTarget.Interact(this);
                return;
            }
            GameState state = GameState.Instance;
            if (state == null || state.CarriedBatteries <= 0)
            {
                return;
            }
            string kind = state.DropBattery();
            if (!string.IsNullOrEmpty(kind))
            {
                SpawnDroppedBattery(kind == "sealed");
            }
        }

        private void FixedUpdate()
        {
            if (!ControlEnabled)
            {
                return;
            }
            EnsureRig();
            float dt = Time.fixedDeltaTime;
            Vector3 stepStart = transform.position;

            bool grounded = _controller.isGrounded;
            if (!grounded && _velocity.y <= 0f && GroundBelow(out _))
            {
                grounded = true;
            }

            if (!grounded)
            {
                _velocity.y -= Gravity * dt;
            }
            else if (_jumpQueued)
            {
                _velocity.y = JumpVelocity;
            }
            else if (_velocity.y < 0f)
            {
                // What the slide of the original does on landing.
                _velocity.y = 0f;
            }
            _jumpQueued = false;

            Vector2 move = ViewpointInput.MoveVector;
            Vector3 direction = transform.right * move.x + transform.forward * move.y;
            direction.y = 0f;
            if (direction.sqrMagnitude > 0.000001f)
            {
                direction = direction.normalized;
            }
            else
            {
                direction = Vector3.zero;
            }
            float speed = ViewpointInput.SprintHeld ? SprintSpeed : WalkSpeed;
            Vector3 target = direction * speed;
            float blend = Mathf.Min(Accel * dt, 1f);
            _velocity.x = Mathf.Lerp(_velocity.x, target.x, blend);
            _velocity.z = Mathf.Lerp(_velocity.z, target.z, blend);

            Vector3 motion = _velocity * dt;
            if (grounded && _velocity.y <= 0f)
            {
                motion.y -= GroundStick;
            }
            CollisionFlags flags = _controller.Move(motion);
            if ((flags & CollisionFlags.Above) != 0 && _velocity.y > 0f)
            {
                // move_and_slide drops the part of the velocity that goes into
                // a surface, so a jump into a ceiling ends there. Without this
                // the climb would survive the impact and the body would hang
                // under the ceiling until gravity ate the whole 6.5.
                _velocity.y = 0f;
            }

            if (grounded && !_controller.isGrounded && _velocity.y <= 0f)
            {
                // Walking down a ramp faster than the stick can follow: land back
                // on it instead of taking off. Nothing happens over a void, so a
                // step off a ledge still falls from where it left.
                float drop;
                if (GroundBelow(out drop) && drop > 0.001f)
                {
                    _controller.Move(Vector3.down * drop);
                }
            }

            // Everything the camera feel of V-ANIM-01 needs to know about this
            // step, read off the step itself once it is finished. It is only
            // ever READ by the presentation in LateUpdate: not one line below
            // moves a collider, a group, a counter or an event.
            NoticeStep(stepStart, grounded, dt);

            // Falling out is losing: Main rebuilds the whole level, so control is
            // cut here and the event fires once, not on every frame of the fall.
            if (transform.position.y < _killY && !_fell)
            {
                _fell = true;
                ControlEnabled = false;
                _velocity = Vector3.zero;
                Action fellOut = FellOut;
                if (fellOut != null)
                {
                    fellOut();
                }
                return;
            }

            // The camera cannot stay at the eye once the hands are full or the
            // film is spent, whatever route emptied them.
            if (Viewfinder && (HandFull || Films <= 0))
            {
                Viewfinder = false;
            }

            UpdateInteractTarget();
        }

        /// <summary>
        /// Distance the feet may still drop before they touch a floor, when one
        /// stands within reach under them.
        /// </summary>
        private bool GroundBelow(out float drop)
        {
            drop = 0f;
            float sphereRadius = ControllerRadius - GroundProbeInset;
            Vector3 origin = transform.position + Vector3.up * (ControllerRadius + GroundProbeInset);
            // The bottom of that sphere starts this high above the feet.
            float clearance = GroundProbeInset * 2f;
            RaycastHit hit;
            if (!Physics.SphereCast(origin, sphereRadius, Vector3.down, out hit,
                clearance + GroundProbeReach, Layers.WorldMask, QueryTriggerInteraction.Ignore))
            {
                return false;
            }
            if (hit.normal.y < MinFloorNormalY)
            {
                return false;
            }
            drop = Mathf.Max(hit.distance - clearance, 0f);
            return true;
        }

        // ---- Camera feel (PRD_VISUAL 4.9, V-ANIM-01) -------------------------

        /// <summary>
        /// Records what the physics step just did, for the camera to comment on
        /// in <see cref="LateUpdate"/>: the horizontal ground speed, the
        /// grounded verdict, and the one event that starts a landing dip.
        ///
        /// <paramref name="grounded"/> is the verdict from the TOP of the step,
        /// so a landing is seen on the step after the touch, twenty
        /// milliseconds late. That is deliberate rather than tolerated: it is
        /// the only reading where the body is already resting on the floor when
        /// the drop height is measured, and a fiftieth of a second on a dip that
        /// takes 45 ms to reach its 3 cm is not visible.
        /// </summary>
        private void NoticeStep(Vector3 stepStart, bool grounded, float dt)
        {
            Vector3 stepped = transform.position - stepStart;
            stepped.y = 0f;
            _groundSpeed = dt > 0f ? stepped.magnitude / dt : 0f;
            _groundedLast = grounded;

            if (!grounded)
            {
                if (_wasGrounded)
                {
                    // The feet just left a floor they were standing on: this is
                    // a fall, and its height is measured from the apex, so a
                    // jump straight up (1.51 m of climb from JumpVelocity
                    // against Gravity) lands with the same weight as a step off
                    // a 1.51 m ledge, which is what it is.
                    _fallTracked = true;
                    _fallApexY = transform.position.y;
                }
                else if (_fallTracked)
                {
                    _fallApexY = Mathf.Max(_fallApexY, transform.position.y);
                }
            }
            else
            {
                if (!_wasGrounded && _fallTracked
                    && _fallApexY - transform.position.y > DipFallMeters)
                {
                    _dipActive = true;
                    _dipElapsed = 0f;
                }
                _fallTracked = false;
            }
            _wasGrounded = grounded;
        }

        /// <summary>
        /// Walks the camera feel and writes it. In LateUpdate because the camera
        /// is the last thing in a frame that should move: every Update has run,
        /// so <see cref="ApplyLook"/> has already written the look this offset
        /// is added to.
        ///
        /// Note what that ordering means for an action taken this frame: a
        /// Place, a Capture or an interaction ray reads the camera as it stood
        /// at the END of the previous frame, which is a coherent pose and not a
        /// half-applied one. The action itself still happens on exactly the
        /// frame the input arrived.
        ///
        /// Scaled Time.deltaTime and not the unscaled one Hud.Fade uses, and the
        /// two are right for opposite reasons. A fade has to keep going while
        /// something slows the game; this camera is a comment on a walk that is
        /// itself on the physics clock, so it has to slow with it. And nothing
        /// can freeze mid swing anyway: the feel is CLEARED whenever control is
        /// off, which is every menu, fade, rewind and fall in the game.
        /// </summary>
        private void LateUpdate()
        {
            if (_camera == null)
            {
                return;
            }
            if (!ControlEnabled)
            {
                // Control is off in menus, in fades, during a rewind and after a
                // fall. In every one of those the pose is either being rewritten
                // from outside or hidden behind a dimmed screen, so the feel is
                // cut rather than eased out: an exact eye and an exact anchor
                // are worth more here than two centimetres of smoothness on a
                // frame the player is not walking through.
                ClearCameraFeel();
                return;
            }
            AdvanceCameraFeel(Time.deltaTime);
            WriteCameraFeel();
        }

        private void AdvanceCameraFeel(float dt)
        {
            if (dt <= 0f)
            {
                return;
            }

            float walkBlend = Mathf.Clamp01(_groundSpeed / WalkSpeed);
            float sprintBlend = Mathf.Clamp01((_groundSpeed - WalkSpeed) / (SprintSpeed - WalkSpeed));

            // ---- Bob. Airborne it fades out: a jump is not a footstep. Below
            // the deadband it is exactly nothing: a standing player's eye has
            // to measure 1.62 m, not 1.62 m and a rounding error.
            bool walking = _groundedLast && _groundSpeed > BobStopSpeed;
            float targetAmplitude = walking
                ? BobAmplitude * walkBlend * Mathf.Lerp(1f, BobSprintScale, sprintBlend)
                : 0f;
            _bobAmplitude = Mathf.MoveTowards(_bobAmplitude, targetAmplitude,
                (BobAmplitude / BobFadeSeconds) * dt);
            if (_bobAmplitude <= 0f)
            {
                // Exactly zero, and the phase back to a zero crossing so the
                // next step out starts from the eye height rather than from
                // wherever the sine had got to.
                _bobAmplitude = 0f;
                _bobPhase = 0f;
                _bobOffset = 0f;
            }
            else
            {
                float hz = BobHz * Mathf.Min(_groundSpeed / WalkSpeed, SprintSpeed / WalkSpeed);
                _bobPhase += hz * 2f * Mathf.PI * dt;
                if (_bobPhase > 2f * Mathf.PI)
                {
                    _bobPhase -= 2f * Mathf.PI;
                }
                _bobOffset = Mathf.Sin(_bobPhase) * _bobAmplitude;
            }

            // ---- Landing dip, in closed form (see DipFrequency).
            if (_dipActive)
            {
                _dipElapsed += dt;
                float u = DipFrequency * _dipElapsed;
                if (u >= DipEndPhase)
                {
                    _dipActive = false;
                    _dipOffset = 0f;
                }
                else
                {
                    _dipOffset = -DipDepth * u * Mathf.Exp(1f - u);
                }
            }

            // ---- Roll lag. The yaw rate is low passed and then mapped, which
            // is what makes the tilt trail the mouse instead of tracking it.
            float yawDelta = Mathf.DeltaAngle(_yawSeen, _yawDegrees);
            _yawSeen = _yawDegrees;
            float instantRate = yawDelta / dt;
            _yawRateDegrees = Mathf.Lerp(_yawRateDegrees, instantRate,
                1f - Mathf.Exp(-dt / RollLagSeconds));
            // Sign: a yaw to the RIGHT is positive in this mirrored space, and a
            // positive roll about the camera's forward axis tips the top of the
            // head to its right, so the view leans INTO the turn. This is not a
            // design-space rotation and does not go through DesignSpace: it is
            // authored in the screen convention it is felt in, so the README's
            // "every rotation sign inverts under the mirror" does not apply.
            _rollDegrees = Mathf.Clamp(_yawRateDegrees / RollFullRateDegrees, -1f, 1f)
                * RollMaxDegrees;
            if (Mathf.Abs(_rollDegrees) < RollSnapDegrees)
            {
                _rollDegrees = 0f;
            }

            // ---- Sprint fov, and the one place the picture identity outranks
            // the feel. The HUD derives the raised-picture and viewfinder square
            // from the CONSTANT CameraFov (Hud.SquareSide: height * tan(50/2) /
            // tan(75/2)), so a camera running at 77 degrees would frame a
            // 2.7 percent smaller share of the screen than the square promises:
            // the square would advertise more than the shot captures, on the two
            // states whose whole job is to show exactly what will be placed.
            // So while that square is up the fov is pinned to CameraFov, and
            // pinned INSTANTLY rather than eased: a two degree cut on the frame
            // a picture rises or a viewfinder opens is hidden by the picture and
            // the four dim panels appearing over it, whereas easing would leave
            // the square measurably wrong for a quarter of a second. Lowering
            // eases back up to the sprint width with the square already gone.
            bool squareUp = Viewfinder || (_placer != null && _placer.Raised);
            if (squareUp)
            {
                _fovDegrees = CameraFov;
            }
            else
            {
                _fovDegrees = Mathf.MoveTowards(_fovDegrees,
                    CameraFov + (FovSprintBoost * sprintBlend),
                    (FovSprintBoost / FovBoostSeconds) * dt);
            }
        }

        /// <summary>
        /// Puts the current offsets on the camera. The eye height itself is
        /// never touched: the local position is EyeHeight plus offsets that are
        /// exactly 0f at rest, so a standing player measures 1.62 m to the bit.
        /// </summary>
        private void WriteCameraFeel()
        {
            Transform t = _camera.transform;
            t.localPosition = new Vector3(0f, EyeHeight + _bobOffset + _dipOffset, 0f);

            if (_rollDegrees != 0f || _rollWritten)
            {
                // Composed from _pitchDegrees, which is this class's own record
                // of the look, so a long roll cannot accumulate the rounding
                // error that re-reading the transform every frame would. With no
                // roll to write, the rotation is left exactly as ApplyLook and
                // SetLook left it.
                t.localRotation = Quaternion.Euler(_pitchDegrees, 0f, _rollDegrees);
                _rollWritten = _rollDegrees != 0f;
            }

            if (_camera.fieldOfView != _fovDegrees)
            {
                _camera.fieldOfView = _fovDegrees;
            }
        }

        /// <summary>
        /// Settles the whole camera feel on the spot and writes the settled
        /// pose, so the eye is at the eye, the roll is off and the fov is the
        /// pinned 75 the HUD square is derived from. Called by
        /// <see cref="Teleport"/>, by <see cref="SetLook"/> and on every frame
        /// control is off.
        /// </summary>
        private void ClearCameraFeel()
        {
            if (_camera == null)
            {
                return;
            }
            _bobAmplitude = 0f;
            _bobPhase = 0f;
            _bobOffset = 0f;
            _dipActive = false;
            _dipElapsed = 0f;
            _dipOffset = 0f;
            _rollDegrees = 0f;
            _yawRateDegrees = 0f;
            _yawSeen = _yawDegrees;
            _fovDegrees = CameraFov;
            _groundSpeed = 0f;
            // A body placed by hand is not a body in flight: whatever it does
            // next, the drop it may be in the middle of is not a fall it took.
            _wasGrounded = false;
            _fallTracked = false;
            WriteCameraFeel();
        }

        /// <summary>
        /// Casts the interaction ray and publishes the prompt. Public because the
        /// probes need the answer without running a physics step.
        /// </summary>
        public void UpdateInteractTarget()
        {
            EnsureRig();
            _interactTarget = null;
            _interactOwner = null;
            InteractPrompt = "";

            Vector3 from = _camera.transform.position;
            Vector3 direction = _camera.transform.forward;
            RaycastHit hit;
            // Closest hit only, triggers included: solid world in front of a
            // trigger blocks the reach, which is what keeps a caged battery out
            // of reach through the bars.
            if (Physics.Raycast(from, direction, out hit, InteractRange,
                Layers.WorldMask | Layers.InteractMask, QueryTriggerInteraction.Collide))
            {
                IInteractable candidate = hit.collider.GetComponentInParent<IInteractable>();
                Component owner = candidate as Component;
                if (candidate != null && Alive(owner))
                {
                    _interactTarget = candidate;
                    _interactOwner = owner;
                    InteractPrompt = candidate.PromptText(this);
                }
            }

            if (_interactTarget == null && CarriedBatteries > 0)
            {
                InteractPrompt = "E : reposer une pile";
            }
        }

        /// <summary>
        /// Takes a photo with the camera. The film ALWAYS captures something: the
        /// frame content, possibly empty, over a painted sky backdrop. The empty
        /// photo is a tool (it pierces the world when placed), not a failure, so
        /// the film is always consumed. The new photo lands straight in hand,
        /// raised.
        /// </summary>
        public bool CapturePhoto()
        {
            EnsureRig();
            if (HandFull || Films <= 0 || !Viewfinder)
            {
                return false;
            }
            // The camera transform is the anchor, so its inverse is what maps the
            // world into photo space.
            PhotoDef def = PhotoCapture.Capture(_camera.transform.worldToLocalMatrix);
            Viewfinder = false;
            GameState state = GameState.Instance;
            if (state != null)
            {
                state.UseFilm();
            }
            string id = PhotoDefs.RegisterDynamic(def);
            PhotoSnaps.Request(id);
            _placer.Hold(id);
            _placer.RaiseToggle();
            return true;
        }

        /// <summary>
        /// Raises the camera to the eye, or lowers it. Only possible with empty
        /// hands and film left; returns the new state.
        /// </summary>
        public bool ToggleViewfinder()
        {
            EnsureRig();
            if (HandFull || Films <= 0)
            {
                Viewfinder = false;
            }
            else
            {
                Viewfinder = !Viewfinder;
            }
            return Viewfinder;
        }

        /// <summary>
        /// Puts one battery back on the ground, in front of the player. A battery
        /// keeps its nature through the hands: what goes down leaden comes back
        /// leaden. The counter is spent by the caller.
        /// </summary>
        public void SpawnDroppedBattery(bool isSealed)
        {
            Vector3 forward = transform.forward;
            forward.y = 0f;
            forward = forward.sqrMagnitude > 0.0001f ? forward.normalized : Vector3.forward;

            // Built inactive, exactly like the original builds the node before it
            // enters the tree: Setup decides the groups the battery registers in,
            // and its idle phase is read from the position, so both must be set
            // before OnEnable runs.
            GameObject batteryObject = new GameObject("Battery");
            batteryObject.SetActive(false);
            if (_levelRoot != null)
            {
                batteryObject.transform.SetParent(_levelRoot, false);
            }
            Battery battery = batteryObject.AddComponent<Battery>();
            battery.Setup(isSealed);
            batteryObject.transform.position = transform.position + forward * 1.2f + new Vector3(0f, 0.05f, 0f);
            batteryObject.SetActive(true);
            Rewind.NoticeSpawn(batteryObject);

            // LAST, AND DELIBERATELY LAST, for the reason Battery.Interact gives
            // about its own burst. Everything above is the gameplay event: the
            // cell exists, at its position, in its groups, known to the rewind.
            // The dust ring of V-VFX-04 is a comment on that event, and a
            // battery cannot tell on its own that it was dropped rather than
            // built with the level (Battery.NoticeDropped says why the caller
            // has to be the one to know), so this is its single call site in the
            // game. It is idempotent and a leaden cell ignores it.
            battery.NoticeDropped();
        }

        private bool HandFull
        {
            get { return _placer != null && !string.IsNullOrEmpty(_placer.HeldId); }
        }

        private static int Films
        {
            get
            {
                GameState state = GameState.Instance;
                return state == null ? 0 : state.CameraFilms;
            }
        }

        private static int CarriedBatteries
        {
            get
            {
                GameState state = GameState.Instance;
                return state == null ? 0 : state.CarriedBatteries;
            }
        }

        /// <summary>
        /// A retired interactable is deactivated, not destroyed, so being alive
        /// is being non null AND active.
        /// </summary>
        private static bool Alive(Component component)
        {
            return component != null && component.gameObject.activeInHierarchy;
        }
    }
}
