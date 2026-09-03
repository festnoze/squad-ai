using System;
using UnityEngine;

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

        private const float CameraFov = 75f;
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
