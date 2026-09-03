using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// The camera pickup. Grabbing it loads the level film into GameState: each
    /// shot (left click with empty hands) captures the framed lavender world into
    /// a new photo. The origin is the base of the pedestal it floats over.
    /// </summary>
    public sealed class CameraItem : MonoBehaviour, IInteractable
    {
        // Every number below comes from PRD 5.6.
        private static readonly Vector3 BodySize = new Vector3(0.55f, 0.34f, 0.28f);
        private static readonly Vector3 FlashSize = new Vector3(0.12f, 0.08f, 0.1f);
        private const float BodyY = 0.55f;
        private const float LensRadius = 0.11f;
        private const float LensHeight = 0.14f;
        private const float LensForward = -0.2f; // design space, -z is forward
        private const float FlashX = 0.18f;
        private const float FlashY = 0.76f;
        private const float TriggerRadius = 0.6f;
        private const float BobSpeed = 1.8f;
        private const float BobBase = 0.06f;
        private const float BobAmplitude = 0.05f;
        private const float SpinSpeed = 1f;

        // Phase hash from the world position, as for the batteries (PRD 5.4).
        private const float PhaseWeightX = 1.3f;
        private const float PhaseWeightZ = 2.7f;

        private int _films = 1;
        private Transform _visual;
        private float _bobPhase;
        private float _spin;

        /// How much film this level hands out. Only the prompt reads it, so the
        /// call order against Awake does not matter.
        public void Setup(int films)
        {
            _films = films;
        }

        private void Awake()
        {
            Build();
        }

        private void Start()
        {
            // The world position is only final once the builder has moved us.
            Vector3 world = transform.position;
            _bobPhase = Mathf.Repeat(world.x * PhaseWeightX + world.z * PhaseWeightZ, Mathf.PI * 2f);
        }

        private void OnEnable()
        {
            Groups.Add(this, Groups.CameraItem);
        }

        private void OnDisable()
        {
            Groups.Remove(this, Groups.CameraItem);
        }

        private void Update()
        {
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
            GameState.Instance.AddFilms(_films);
            Rewind.Retire(gameObject);
        }

        public string PromptText(PlayerController player)
        {
            return string.Format("E : prendre l'appareil photo (pellicule : {0})", _films);
        }

        private void Build()
        {
            // The interaction ray only sees the Interact layer, and the component it
            // looks for sits on the trigger object itself (PRD 15.3).
            gameObject.layer = Layers.Interact;

            GameObject visualGo = new GameObject("Visual");
            _visual = visualGo.transform;
            _visual.SetParent(transform, false);

            Renderer body = SpawnPart(
                _visual, PrimitiveType.Cube, "Body",
                DesignSpace.ToUnity(new Vector3(0f, BodyY, 0f)),
                BodySize);
            body.sharedMaterial = Materials.Solid("battery_tip");

            Renderer lens = SpawnPart(
                _visual, PrimitiveType.Cylinder, "Lens",
                DesignSpace.ToUnity(new Vector3(0f, BodyY, LensForward)),
                // Unity's cylinder primitive is 2 units tall with a radius of 0.5.
                new Vector3(LensRadius * 2f, LensHeight * 0.5f, LensRadius * 2f));
            // A quarter turn about x lays the cylinder axis along the view axis.
            lens.transform.localRotation = Quaternion.Euler(90f, 0f, 0f);
            lens.sharedMaterial = Materials.Solid("teal", 0.4f);

            Renderer flash = SpawnPart(
                _visual, PrimitiveType.Cube, "Flash",
                DesignSpace.ToUnity(new Vector3(FlashX, FlashY, 0f)),
                FlashSize);
            flash.sharedMaterial = Materials.Solid("accent");

            SphereCollider trigger = gameObject.AddComponent<SphereCollider>();
            trigger.isTrigger = true;
            trigger.radius = TriggerRadius;
            trigger.center = new Vector3(0f, BodyY, 0f);
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
