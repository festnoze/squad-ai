using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// A polaroid found (or dropped back) in the world, PRD 5.5. The transform
    /// origin is the center of the frame; the picture bobs and turns slowly to
    /// catch the eye. Interacting hands the photo to the player's placer.
    ///
    /// The item builds itself from its own numbers, not from authored data: the
    /// two picture quads sit at symmetric local offsets, so the z mirror cannot
    /// show there. It shows in the two places that read design space anyway, the
    /// bob phase seed and the idle spin, and both go through DesignSpace.
    /// </summary>
    public sealed class PhotoItem : MonoBehaviour, IInteractable
    {
        // Geometry, PRD 5.5.
        private const float FrameWidth = 0.72f;
        private const float FrameHeight = 0.82f;
        private const float FrameDepth = 0.035f;
        private const float PictureWidth = 0.66f;
        private const float PictureHeight = 0.76f;
        private const float PictureOffset = 0.019f;
        private const float TriggerRadius = 0.6f;

        // Idle motion, PRD 5.5. The spin speed is in radians per second and the
        // phase seed weights apply to a DESIGN position; both are mirrored
        // where they are used, never here.
        private const float BobSpeed = 1.6f;
        private const float BobAmplitude = 0.07f;
        private const float SpinSpeed = 0.8f;
        private const float PhaseSeedX = 2.1f;
        private const float PhaseSeedZ = 1.3f;

        // The rendered snap can land well after the item was built (the studio
        // renders one photo at a time), so the texture is re-polled, PRD 5.5.
        private const float SnapPollSeconds = 0.5f;

        // PRD 5.5 and D2, verbatim, deliberately without accents.
        private const string FullHandsPrompt = "Mains pleines : posez (clic gauche) ou reposez (F) votre photo";

        // One shared quad mesh for every polaroid in the game: the picture size
        // is a constant, so a mesh per item would buy nothing.
        private static Mesh _pictureMesh;

        private string _defId = "";
        private bool _started;
        private bool _built;
        private Transform _visual;
        private Material _pictureMaterial;
        private float _bobPhase;
        /// Idle spin, in design-space radians. Mirrored only where it is used.
        private float _spin;
        private float _snapTimer;

        public string DefId { get { return _defId; } }

        /// <summary>Names the photo this item carries. Call it right after
        /// AddComponent, before the end of the frame.</summary>
        public void Setup(string defId)
        {
            _defId = defId == null ? "" : defId;
            // Setup normally lands before Start; when it lands after (a caller
            // that re-uses an item) the visual is built now instead of never.
            TryBuild();
        }

        private void OnEnable()
        {
            Groups.Add(this, Groups.PhotoItem);
        }

        private void OnDisable()
        {
            // Retiring the item deactivates it, and that is what must take it
            // out of the registry, exactly as a destroy would (PRD 10).
            Groups.Remove(this, Groups.PhotoItem);
        }

        private void Start()
        {
            _started = true;
            TryBuild();
        }

        private void OnDestroy()
        {
            // The picture material belongs to this item alone (it carries this
            // photo's texture), so it dies with it. Materials.Solid returns a
            // cached shared material and is never destroyed here.
            if (_pictureMaterial != null && Application.isPlaying)
            {
                Destroy(_pictureMaterial);
            }
            _pictureMaterial = null;
        }

        private void Update()
        {
            if (!_built)
            {
                return;
            }

            float dt = Time.deltaTime;
            _bobPhase = Mathf.Repeat(_bobPhase + dt * BobSpeed, Mathf.PI * 2f);
            // The spin is authored in design space (PRD 5.5: spin += dt * 0.8
            // about +y), so its sign goes through the one mirror like every
            // other rotation instead of being negated by hand here.
            _spin = Mathf.Repeat(_spin + SpinSpeed * dt, Mathf.PI * 2f);
            _visual.localPosition = new Vector3(0f, Mathf.Sin(_bobPhase) * BobAmplitude, 0f);
            _visual.localRotation = Quaternion.Euler(0f, DesignSpace.YawToUnityDegrees(_spin), 0f);

            _snapTimer += dt;
            if (_snapTimer > SnapPollSeconds)
            {
                _snapTimer = 0f;
                AdoptSnap();
            }
        }

        public void Interact(PlayerController player)
        {
            if (player == null)
            {
                return;
            }
            PhotoPlacer placer = player.Placer;
            if (placer != null && placer.Hold(_defId))
            {
                Rewind.Retire(gameObject);
            }
        }

        public string PromptText(PlayerController player)
        {
            PhotoPlacer placer = player == null ? null : player.Placer;
            if (placer != null && !string.IsNullOrEmpty(placer.HeldId))
            {
                return FullHandsPrompt;
            }
            return "E : prendre la photo « " + Title() + " »";
        }

        private string Title()
        {
            PhotoDef def = PhotoDefs.GetDef(_defId);
            if (def != null && !string.IsNullOrEmpty(def.Title))
            {
                return def.Title;
            }
            return _defId;
        }

        private void TryBuild()
        {
            if (_built || !_started || string.IsNullOrEmpty(_defId))
            {
                return;
            }
            Build();
        }

        private void Build()
        {
            _built = true;

            // The interaction ray tests World and Interact and keeps the
            // closest hit, so the trigger lives on this object (Interact layer)
            // while the meshes live on children (World layer, no collider).
            gameObject.layer = Layers.Interact;
            SphereCollider trigger = gameObject.AddComponent<SphereCollider>();
            trigger.isTrigger = true;
            trigger.radius = TriggerRadius;
            trigger.center = Vector3.zero;

            // PRD 5.5 seeds the phase from the DESIGN position (x * 2.1 +
            // z * 1.3). The mirror is its own inverse, so ToUnity is also the
            // way back from this Unity position to the design one it was
            // authored as; without it two items mirrored about z would swap
            // phases with the original game.
            Vector3 designPosition = DesignSpace.ToUnity(transform.position);
            _bobPhase = Mathf.Repeat(designPosition.x * PhaseSeedX + designPosition.z * PhaseSeedZ, Mathf.PI * 2f);

            GameObject visual = new GameObject("Visual");
            visual.layer = Layers.World;
            visual.transform.SetParent(transform, false);
            _visual = visual.transform;

            BuildFrame();
            BuildPictureMaterial();
            // Back to back, each facing away from the frame, so the polaroid
            // reads from either side.
            BuildPicture("PictureFront", -PictureOffset, Quaternion.identity);
            BuildPicture("PictureBack", PictureOffset, Quaternion.Euler(0f, 180f, 0f));
        }

        private void BuildFrame()
        {
            GameObject frame = GameObject.CreatePrimitive(PrimitiveType.Cube);
            frame.name = "Frame";
            frame.layer = Layers.World;
            // A primitive ships with a collider and the polaroid must not be
            // solid: it hovers, and one solid frame would carry the player or a
            // crate. Disabling bites at once, the destroy only at the end of the
            // frame, and a physics step can fall in between. This is not a
            // removal from the world, so it does not go through Rewind.Retire:
            // the collider never existed for the player.
            Collider spare = frame.GetComponent<Collider>();
            if (spare != null)
            {
                spare.enabled = false;
                Destroy(spare);
            }
            frame.transform.SetParent(_visual, false);
            frame.transform.localScale = new Vector3(FrameWidth, FrameHeight, FrameDepth);
            MeshRenderer renderer = frame.GetComponent<MeshRenderer>();
            if (renderer != null)
            {
                renderer.sharedMaterial = Materials.Solid("frame");
            }
        }

        private void BuildPictureMaterial()
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Unlit");
            if (shader == null)
            {
                shader = Shader.Find("Unlit/Texture");
            }
            if (shader == null)
            {
                // Same reason as Materials.FindShader: a URP project always
                // ships these, so a miss means the pipeline is absent or the
                // shader was stripped. Say it loudly rather than hand out
                // blank polaroids.
                Debug.LogError("PhotoItem: shader not found: Universal Render Pipeline/Unlit");
                return;
            }
            _pictureMaterial = new Material(shader);
            _pictureMaterial.name = "PhotoItemPicture";
            // mainTexture routes to _BaseMap on a URP shader and to _MainTex on
            // a built-in one, so it is the one assignment that fits both.
            _pictureMaterial.mainTexture = PhotoSnaps.GetTexture(_defId);
        }

        private void AdoptSnap()
        {
            if (_pictureMaterial == null)
            {
                return;
            }
            Texture2D snap = PhotoSnaps.GetTexture(_defId);
            if (_pictureMaterial.mainTexture != snap)
            {
                _pictureMaterial.mainTexture = snap;
            }
        }

        private void BuildPicture(string pictureName, float localZ, Quaternion localRotation)
        {
            GameObject picture = new GameObject(pictureName);
            picture.layer = Layers.World;
            picture.transform.SetParent(_visual, false);
            picture.transform.localPosition = new Vector3(0f, 0f, localZ);
            picture.transform.localRotation = localRotation;
            MeshFilter filter = picture.AddComponent<MeshFilter>();
            filter.sharedMesh = PictureMesh();
            MeshRenderer renderer = picture.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = _pictureMaterial;
        }

        /// <summary>
        /// The picture quad, built by hand rather than taken from
        /// PrimitiveType.Quad: the winding, the normal and the uv corners have
        /// to be known exactly or the snap prints mirrored or upside down. It
        /// lies in the xy plane facing -z (Unity's own quad convention), with
        /// uv (0, 0) at the bottom left as seen from the front.
        /// </summary>
        private static Mesh PictureMesh()
        {
            if (_pictureMesh != null)
            {
                return _pictureMesh;
            }
            float hw = PictureWidth * 0.5f;
            float hh = PictureHeight * 0.5f;
            Mesh mesh = new Mesh();
            mesh.name = "PhotoItemPictureQuad";
            // Kept out of the asset garbage collector: no scene object owns it,
            // and an unload of unused assets would otherwise take it away.
            mesh.hideFlags = HideFlags.HideAndDontSave;
            mesh.vertices = new Vector3[]
            {
                new Vector3(-hw, -hh, 0f),
                new Vector3(hw, -hh, 0f),
                new Vector3(-hw, hh, 0f),
                new Vector3(hw, hh, 0f)
            };
            mesh.uv = new Vector2[]
            {
                new Vector2(0f, 0f),
                new Vector2(1f, 0f),
                new Vector2(0f, 1f),
                new Vector2(1f, 1f)
            };
            mesh.normals = new Vector3[]
            {
                new Vector3(0f, 0f, -1f),
                new Vector3(0f, 0f, -1f),
                new Vector3(0f, 0f, -1f),
                new Vector3(0f, 0f, -1f)
            };
            // Clockwise seen from -z, which is what Unity calls front facing.
            mesh.triangles = new int[] { 0, 2, 3, 0, 3, 1 };
            mesh.RecalculateBounds();
            _pictureMesh = mesh;
            return mesh;
        }
    }
}
