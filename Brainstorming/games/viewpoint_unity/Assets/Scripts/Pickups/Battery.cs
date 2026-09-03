using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Collectible battery. The origin is the BASE of the battery so level data
    /// can place it directly on a floor. A battery duplicated out of a photo uses
    /// this very same component: a copy is a normal battery.
    ///
    /// A SEALED battery ("pile plombee") is worth exactly as much to a teleporter,
    /// but film does not print it: it stays out of the "copyable_battery" group
    /// the camera reads, so framing it copies nothing. It says so without a word,
    /// in the language the ground already speaks: it is leaden grey instead of
    /// amber, and it is inert (it neither bobs nor turns while the others do).
    /// </summary>
    public sealed class Battery : MonoBehaviour, IInteractable
    {
        // Every number below comes from PRD 5.4.
        private const float BodyRadius = 0.16f;
        private const float BodyHeight = 0.5f;
        private const float BodyY = 0.35f;
        private const float TipRadius = 0.06f;
        private const float TipHeight = 0.08f;
        private const float TipY = 0.64f;
        private const float TriggerRadius = 0.55f;
        private const float BobSpeed = 2f;
        private const float BobBase = 0.08f;
        private const float BobAmplitude = 0.06f;
        private const float SpinSpeed = 1.2f;

        // Phase hash from the world position: batteries dropped on a grid must not
        // bob in unison, so x and z are weighted by two unrelated factors.
        private const float PhaseWeightX = 1.7f;
        private const float PhaseWeightZ = 2.3f;

        private bool _isSealed;
        private Transform _visual;
        private Renderer _bodyRenderer;
        private Renderer _tipRenderer;
        private float _bobPhase;
        private float _spin;
        private bool _registered;
        private bool _copyableRegistered;

        public bool IsSealed { get { return _isSealed; } }

        /// <summary>
        /// Level data calls this for the batteries listed under "sealed_batteries".
        /// The caller may run it before or after Awake, so it re-applies the look
        /// and the group membership rather than assuming an order.
        /// </summary>
        public void Setup(bool isSealed)
        {
            _isSealed = isSealed;
            ApplyLook();
            SyncGroups();
        }

        private void Awake()
        {
            Build();
        }

        private void Start()
        {
            // The world position is only final once the builder has moved us, which
            // happens after Awake; Start is the first moment the hash is meaningful.
            Vector3 world = transform.position;
            _bobPhase = Mathf.Repeat(world.x * PhaseWeightX + world.z * PhaseWeightZ, Mathf.PI * 2f);
        }

        private void OnEnable()
        {
            _registered = true;
            Groups.Add(this, Groups.Battery);
            if (!_isSealed)
            {
                // The only group the camera reads: a leaden battery is invisible to film.
                Groups.Add(this, Groups.CopyableBattery);
                _copyableRegistered = true;
            }
        }

        private void OnDisable()
        {
            _registered = false;
            Groups.Remove(this, Groups.Battery);
            if (_copyableRegistered)
            {
                Groups.Remove(this, Groups.CopyableBattery);
                _copyableRegistered = false;
            }
        }

        private void Update()
        {
            if (_isSealed)
            {
                // Dead weight: no float, no spin. Seen next to a live battery, the
                // difference is immediate.
                return;
            }
            if (_visual == null)
            {
                return;
            }
            float dt = Time.deltaTime;
            _bobPhase = Mathf.Repeat(_bobPhase + dt * BobSpeed, Mathf.PI * 2f);
            Vector3 local = _visual.localPosition;
            local.y = BobBase + Mathf.Sin(_bobPhase) * BobAmplitude;
            _visual.localPosition = local;
            _spin += dt * SpinSpeed;
            // The spin is authored in design space, so its sign goes through the
            // one mirror like every other rotation.
            _visual.localRotation = Quaternion.Euler(0f, DesignSpace.YawToUnityDegrees(_spin), 0f);
        }

        public void Interact(PlayerController player)
        {
            GameState.Instance.CollectBattery(_isSealed);
            // A physically placed battery lives inside a rigid shell: retire the
            // shell, not just the battery, or an empty physics husk would remain.
            Transform parent = transform.parent;
            Rigidbody shell = parent != null ? parent.GetComponent<Rigidbody>() : null;
            if (shell != null)
            {
                Rewind.Retire(shell.gameObject);
            }
            else
            {
                Rewind.Retire(gameObject);
            }
        }

        public string PromptText(PlayerController player)
        {
            return _isSealed ? "E : ramasser la pile plombee" : "E : ramasser la pile";
        }

        private void Build()
        {
            // The interaction ray only sees the Interact layer, and the component it
            // looks for sits on the trigger object itself (PRD 15.3).
            gameObject.layer = Layers.Interact;

            GameObject visualGo = new GameObject("Visual");
            _visual = visualGo.transform;
            _visual.SetParent(transform, false);

            _bodyRenderer = SpawnPart(
                _visual, PrimitiveType.Cylinder, "Body",
                new Vector3(0f, BodyY, 0f),
                // Unity's cylinder primitive is 2 units tall with a radius of 0.5.
                new Vector3(BodyRadius * 2f, BodyHeight * 0.5f, BodyRadius * 2f));
            _tipRenderer = SpawnPart(
                _visual, PrimitiveType.Cylinder, "Tip",
                new Vector3(0f, TipY, 0f),
                new Vector3(TipRadius * 2f, TipHeight * 0.5f, TipRadius * 2f));
            ApplyLook();

            SphereCollider trigger = gameObject.AddComponent<SphereCollider>();
            trigger.isTrigger = true;
            trigger.radius = TriggerRadius;
            trigger.center = new Vector3(0f, BodyY, 0f);
        }

        private void ApplyLook()
        {
            if (_bodyRenderer == null || _tipRenderer == null)
            {
                return;
            }
            _bodyRenderer.sharedMaterial = _isSealed
                ? Materials.Solid("battery_sealed")
                : Materials.Solid("battery", 0.8f);
            _tipRenderer.sharedMaterial = Materials.Solid(_isSealed ? "sealed_dark" : "battery_tip");
        }

        /// Keeps the copyable group in step when Setup lands after OnEnable.
        private void SyncGroups()
        {
            if (!_registered)
            {
                return;
            }
            if (_isSealed && _copyableRegistered)
            {
                Groups.Remove(this, Groups.CopyableBattery);
                _copyableRegistered = false;
            }
            else if (!_isSealed && !_copyableRegistered)
            {
                Groups.Add(this, Groups.CopyableBattery);
                _copyableRegistered = true;
            }
        }

        private static Renderer SpawnPart(Transform parent, PrimitiveType shape, string name, Vector3 localPosition, Vector3 localScale)
        {
            GameObject go = GameObject.CreatePrimitive(shape);
            go.name = name;
            Collider col = go.GetComponent<Collider>();
            if (col != null)
            {
                // CreatePrimitive always attaches a collider; these parts are pure
                // decoration and the trigger is the only collider wanted. Disabling
                // bites at once, the destroy only at the end of the frame.
                col.enabled = false;
                UnityEngine.Object.Destroy(col);
            }
            Transform t = go.transform;
            t.SetParent(parent, false);
            t.localPosition = localPosition;
            t.localScale = localScale;
            return go.GetComponent<Renderer>();
        }
    }
}
