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

        // V-PROP-04, the rangefinder. Look decisions, no part of PRD 5.6, and
        // none of them touches BodySize, LensRadius, LensForward, FlashX/Y,
        // TriggerRadius or the bob: every pinned number above stands.
        //
        // The leatherette wrap sits just below the body's centre, so the metal
        // top plate stays visible above it the way it does on a real body.
        private const float WrapProud = 0.012f;
        private const float WrapHeight = 0.15f;
        private const float WrapDrop = 0.04f;

        // The bezel round the barrel, standing slightly ahead of the glass.
        private const float BezelProud = 0.028f;
        private const float BezelThickness = 0.022f;
        private const float BezelForward = 0.012f;

        // The viewfinder window, on the opposite side of the top plate from the
        // flash so the camera is asymmetric front-on.
        private static readonly Vector3 FinderSize = new Vector3(0.09f, 0.055f, 0.05f);
        private const float FinderX = 0.17f;
        private const float FinderY = 0.72f;

        /// <summary>
        /// The viewfinder glass, emissive but well under the lens's 0.4: it is a
        /// window catching light, not a second lens. PRD_VISUAL V-POST-01 lists
        /// the camera LENS among the things meant to bloom, and a finder as
        /// bright as the lens would make the camera read as two-eyed.
        /// </summary>
        private const float FinderEnergy = 0.12f;

        // The shutter release, on the flash side so the right hand finds it.
        private const float ShutterRadius = 0.028f;
        private const float ShutterHeight = 0.035f;
        private const float ShutterX = 0.09f;
        private const float ShutterY = 0.735f;
        private const float ShutterForward = -0.06f;

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

            // V-PROP-04: a beveled body, not a box. Built at its REAL SIZE and
            // left at unit scale, because a scaled unit cube stretches the
            // chamfer per axis (BodySize is 0.55 x 0.34 x 0.28, so it would come
            // out three different widths) and skews the normals that
            // Viewpoint/Surface lights and samples triplanar from.
            Renderer body = SpawnMesh(
                _visual, "Body",
                DesignSpace.ToUnity(new Vector3(0f, BodyY, 0f)),
                ProceduralMeshes.BeveledBox(BodySize),
                // Falls back to the scaled primitive if the mesh cannot be
                // built: a camera that looks like a box is still a camera the
                // player can pick up, and a null mesh draws nothing at all.
                PrimitiveType.Cube, BodySize);
            body.sharedMaterial = Materials.Solid("battery_tip");

            // The leatherette wrap: a darker, grainier band around the body's
            // waist, which is the one detail that makes a small dark box read as
            // a CAMERA rather than as a brick. Slightly proud of the body so it
            // catches its own highlight, and inset on the axis the lens sticks
            // out of so it cannot fight the barrel.
            Renderer wrap = SpawnMesh(
                _visual, "Leatherette",
                DesignSpace.ToUnity(new Vector3(0f, BodyY - WrapDrop, 0f)),
                ProceduralMeshes.BeveledBox(new Vector3(
                    BodySize.x + WrapProud, WrapHeight, BodySize.z + WrapProud)),
                PrimitiveType.Cube,
                new Vector3(BodySize.x + WrapProud, WrapHeight, BodySize.z + WrapProud));
            wrap.sharedMaterial = Materials.Solid("sealed_dark");

            Renderer lens = SpawnPart(
                _visual, PrimitiveType.Cylinder, "Lens",
                DesignSpace.ToUnity(new Vector3(0f, BodyY, LensForward)),
                // Unity's cylinder primitive is 2 units tall with a radius of 0.5.
                new Vector3(LensRadius * 2f, LensHeight * 0.5f, LensRadius * 2f));
            // A quarter turn about x lays the cylinder axis along the view axis.
            lens.transform.localRotation = Quaternion.Euler(90f, 0f, 0f);
            lens.sharedMaterial = Materials.Solid("teal", 0.4f);

            // The chromed bezel round the barrel. A flat ring standing on the
            // lens axis, so it needs the same quarter turn about x the barrel
            // takes. Steel style, so it catches the sky reflection V-LIGHT-02
            // set up in Tier 1: a ring of bright metal round a glowing teal
            // disc is what makes the front of this thing read as an OPTIC.
            Mesh bezelMesh = ProceduralMeshes.Ring(
                LensRadius, LensRadius + BezelProud, BezelThickness, 24);
            if (bezelMesh != null)
            {
                GameObject bezel = new GameObject("Bezel");
                bezel.transform.SetParent(_visual, false);
                bezel.transform.localPosition =
                    DesignSpace.ToUnity(new Vector3(0f, BodyY, LensForward - BezelForward));
                bezel.transform.localRotation = Quaternion.Euler(90f, 0f, 0f);
                bezel.transform.localScale = Vector3.one;
                bezel.AddComponent<MeshFilter>().sharedMesh = bezelMesh;
                bezel.AddComponent<MeshRenderer>().sharedMaterial = Materials.Solid("sealed");
            }

            // The viewfinder window, offset to the side the flash is NOT on, so
            // the top of the camera reads as asymmetric the way a rangefinder
            // does. Emissive teal like the lens, faintly: it is glass.
            Renderer finder = SpawnMesh(
                _visual, "Viewfinder",
                DesignSpace.ToUnity(new Vector3(-FinderX, FinderY, LensForward * 0.55f)),
                ProceduralMeshes.BeveledBox(FinderSize, 0.006f),
                PrimitiveType.Cube, FinderSize);
            finder.sharedMaterial = Materials.Solid("teal", FinderEnergy);

            // The shutter button, on top, on the same side as the flash so the
            // right hand falls on it.
            Renderer shutter = SpawnPart(
                _visual, PrimitiveType.Cylinder, "Shutter",
                DesignSpace.ToUnity(new Vector3(ShutterX, ShutterY, ShutterForward)),
                new Vector3(ShutterRadius * 2f, ShutterHeight * 0.5f, ShutterRadius * 2f));
            shutter.sharedMaterial = Materials.Solid("accent_dark");

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

        /// <summary>
        /// A generated mesh at its REAL SIZE and unit scale, with the scaled
        /// primitive as a fallback when the mesh cannot be built.
        ///
        /// The unit scale is the point. <see cref="SpawnPart"/> scales a unit
        /// primitive, which is fine for a cylinder but wrong for anything
        /// beveled: a per-axis scale stretches the chamfer into three different
        /// widths and skews the interpolated normals, and Viewpoint/Surface both
        /// lights from those normals and samples its maps triplanar. The
        /// fallback deliberately accepts that stretch, because a camera drawn as
        /// a plain box is still a camera and a null mesh is nothing at all.
        /// </summary>
        private static Renderer SpawnMesh(Transform parent, string name, Vector3 localPosition,
            Mesh mesh, PrimitiveType fallbackShape, Vector3 fallbackScale)
        {
            if (mesh == null)
            {
                return SpawnPart(parent, fallbackShape, name, localPosition, fallbackScale);
            }

            GameObject go = new GameObject(name);
            Transform t = go.transform;
            t.SetParent(parent, false);
            t.localPosition = localPosition;
            t.localScale = Vector3.one;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            return go.AddComponent<MeshRenderer>();
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
