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
    ///
    /// Since PRD_VISUAL 4.7 V-PROP-02 the frame is real paper rather than a
    /// scaled cube: a rounded rectangle with a hole in it, the wide caption
    /// border at the bottom, and the pictures recessed behind the hole. Two
    /// things carry that: the mesh (ProceduralMeshes.RoundedFrame) and the crop
    /// (ApplyPicture), and neither works without the other.
    /// </summary>
    public sealed class PhotoItem : MonoBehaviour, IInteractable
    {
        // Geometry, PRD 5.5.
        private const float FrameWidth = 0.72f;
        private const float FrameHeight = 0.82f;
        private const float FrameDepth = 0.035f;
        private const float PictureWidth = 0.66f;
        private const float PictureHeight = 0.76f;
        private const float TriggerRadius = 0.6f;

        // PRD_VISUAL 4.7 V-PROP-02, the polaroid as paper. The outer box above
        // is untouched: the silhouette, the footprint and the hover are all
        // exactly where PRD 5.5 puts them. What changes is that the paper is now
        // geometry instead of a scaled cube with a picture painted over it.
        //
        // 1.8 cm of corner radius on a 72 cm print is 2.5 percent of the width,
        // which is what a real instant print carries (2 mm on 88 mm). Small
        // enough to read as die-cut paper, large enough to see at 1.5 m, which is
        // the distance the item's acceptance criterion names.
        private const float CornerRadius = 0.018f;

        // How far the paper OVERLAPS the picture quad on every side. It is what
        // makes the aperture strictly smaller than the quad behind it, so no
        // grazing angle can open a seam at the rim and no filtering can show the
        // print's own edge. Deriving the aperture from this rather than from a
        // paper margin is deliberate: the overlap is then guaranteed by
        // construction instead of being a number someone has to check.
        private const float PaperTuck = 0.02f;

        // The print sits 3 mm behind the front face of the paper (V-PROP-02
        // asks for exactly that), which is the hairline shadow gap the item
        // wants: the print is BEHIND a lip instead of pasted on top of one, so
        // the darkening at the rim is geometry the sun and SSAO can find rather
        // than a line someone drew. It stays subtle at this depth, and subtle is
        // the brief - a hairline, not a mount.
        //
        // PRD 5.5 pins this offset at 0.019, which is 1.5 mm in FRONT of a 3.5 cm
        // deep frame, and a picture in front of the paper cannot have a hole to
        // sit in: V-PROP-02's number is the one that stands, and it is said out
        // loud here rather than diverged from quietly. Nothing but the look
        // depends on it - the quads keep their PRD size, their symmetry about z,
        // their texture and the frame they are inside of.
        private const float PictureRecess = 0.003f;
        private const float PictureOffset = (FrameDepth * 0.5f) - PictureRecess;

        // THE APERTURE, and its shape is not a free choice.
        //
        // PhotoSnaps paints the polaroid border straight onto the render, 24 px
        // on three sides and 48 at the bottom of a 512 square (PRD 6.9), scaled
        // with SnapSize. What is left in the middle is the PICTURE, and it is not
        // square: 696 by 660 at the shipped size, an aspect of 1.0545. That is
        // the ratio PhotoSnaps.cs calls "the same ratio that V-PROP-02 builds
        // to", and the reason it matters is the identity of gameplay PRD 6.9: the
        // polaroid shows the view the placed content will produce, and a picture
        // stretched by five percent is a picture that promises the wrong view.
        //
        // So the aperture is the picture quad minus the tuck in width, and its
        // height is DERIVED from the studio's own border constants. The two
        // cannot drift: changing SnapSize or either border moves this aperture
        // with it, and no number is written twice.
        //
        // The paper margins are what is left over, and ProceduralMeshes.
        // RoundedFrame decides how: side and top equal, the rest at the bottom.
        // At the shipped numbers that is 5 cm at the sides, 5 cm at the top and
        // 18.2 cm at the bottom, i.e. 22 percent of the height - which is, to
        // within a percent, a Polaroid 600.
        private const float ApertureWidth = PictureWidth - (PaperTuck * 2f);
        private const float ApertureHeight = ApertureWidth
            * ((float)(PhotoSnaps.SnapSize - PhotoSnaps.Border - PhotoSnaps.BottomBorder)
                / (PhotoSnaps.SnapSize - (2 * PhotoSnaps.Border)));

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

        /// <summary>
        /// The paper, PRD_VISUAL 4.7 V-PROP-02.
        ///
        /// It used to be a CreatePrimitive cube at localScale (0.72, 0.82,
        /// 0.035), which is the state the item records in one word: "a white
        /// box". It is now an instant print - rounded corners, a hole for the
        /// picture, the wide caption border at the bottom and an edge of its own
        /// that catches the light - built at real size and drawn at unit scale.
        ///
        /// Two things here are load bearing.
        ///
        /// NO SCALE. The mesh is real size and this transform stays at
        /// Vector3.one, which is what every generated mesh in this project does
        /// (BeveledBox says the same thing about the boxes it replaced). It is
        /// not a style rule: the corner arcs are the first normals a polaroid has
        /// that are not axis aligned, and a non-uniform scale leaves an
        /// axis-aligned face normal alone while skewing every one of those. It
        /// would also hand the corner a radius of 1.8 cm times 0.72 across x and
        /// 1.8 cm times 0.035 across z, which is not a radius at all.
        ///
        /// NO COLLIDER, and that is the whole reason this no longer goes through
        /// CreatePrimitive. The polaroid must not be solid: it hovers at 0.9 m,
        /// and a solid frame would carry the player or a crate. A primitive ships
        /// with one, so the old code had to disable it (which bites at once) and
        /// then destroy it (which only lands at the end of the frame, with room
        /// for a physics step in between). A bare MeshFilter and MeshRenderer
        /// never create the collider, so there is no window at all. This is not a
        /// removal from the world either, so it never involved Rewind.Retire: the
        /// collider never existed for the player.
        /// </summary>
        private void BuildFrame()
        {
            GameObject frame = new GameObject("Frame");
            frame.layer = Layers.World;
            frame.transform.SetParent(_visual, false);

            MeshFilter filter = frame.AddComponent<MeshFilter>();
            filter.sharedMesh = ProceduralMeshes.RoundedFrame(
                new Vector2(FrameWidth, FrameHeight),
                new Vector2(ApertureWidth, ApertureHeight),
                CornerRadius,
                FrameDepth);

            MeshRenderer renderer = frame.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = Materials.Solid("frame");
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
            ApplyPicture(PhotoSnaps.GetTexture(_defId));
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
                ApplyPicture(snap);
            }
        }

        /// <summary>
        /// Hands the quads a texture and crops them to the PICTURE inside it
        /// (PRD_VISUAL 4.7 V-PROP-02).
        ///
        /// The crop is the other half of making the frame paper. Every polaroid
        /// texture in this game carries the white border painted into its pixels
        /// (PhotoSnaps.PaintPolaroidBorder for a rendered snap, PhotoDefs.
        /// Thumbnail for the drawn fallback), because the picture is also shown
        /// raised in the HUD, where there is no paper to give it one. Show that
        /// texture whole behind a paper frame and the border appears twice: a
        /// painted white ring inside a white paper ring, which is the double
        /// mount nobody ever put a print in.
        ///
        /// So the aperture is mapped onto the picture window and nothing else.
        /// The quads keep the size PRD 5.5 gives them (0.66 x 0.76, both sides,
        /// symmetric about z) and the paper covers the 2 cm of tuck around the
        /// hole; the part it covers samples past the window into the painted
        /// border, which is white, clamped, and hidden. Nothing about WHAT the
        /// picture shows changes: the border was always covering those pixels.
        ///
        /// The three assignments below are the ones that fit both shaders this
        /// component can end up with: mainTexture routes to _BaseMap on a URP
        /// shader and to _MainTex on a built-in one, and mainTextureScale and
        /// mainTextureOffset route to that same property's _ST.
        /// </summary>
        private void ApplyPicture(Texture2D picture)
        {
            _pictureMaterial.mainTexture = picture;

            Vector2 windowMin, windowMax;
            PictureWindowUv(picture, out windowMin, out windowMax);
            Vector2 apertureMin, apertureMax;
            ApertureInQuadUv(out apertureMin, out apertureMax);

            // The one linear map that takes the aperture's corners in the quad's
            // own uv to the window's corners in the texture. Guarded on the
            // denominator only: an aperture of zero width would be a frame with
            // no hole, and dividing by it would hand the material a NaN scale,
            // which draws nothing and says nothing.
            Vector2 scale = new Vector2(
                (windowMax.x - windowMin.x) / Mathf.Max(apertureMax.x - apertureMin.x, 1e-4f),
                (windowMax.y - windowMin.y) / Mathf.Max(apertureMax.y - apertureMin.y, 1e-4f));
            _pictureMaterial.mainTextureScale = scale;
            _pictureMaterial.mainTextureOffset = new Vector2(
                windowMin.x - (scale.x * apertureMin.x),
                windowMin.y - (scale.y * apertureMin.y));
        }

        /// <summary>
        /// The aperture of the frame, expressed in the picture quad's own uv.
        ///
        /// The vertical half is the part worth reading twice: the aperture is NOT
        /// centred on the quad, because an instant print's border is wider at the
        /// bottom. Where exactly it sits is ProceduralMeshes.RoundedFrame's
        /// decision, and it is asked rather than recomputed here, so the picture
        /// cannot slide off the hole the day that rule changes.
        /// </summary>
        private static void ApertureInQuadUv(out Vector2 min, out Vector2 max)
        {
            float centerY = ProceduralMeshes.RoundedFrameApertureCenterY(
                new Vector2(FrameWidth, FrameHeight),
                new Vector2(ApertureWidth, ApertureHeight));

            float halfU = (ApertureWidth * 0.5f) / PictureWidth;
            min = new Vector2(
                0.5f - halfU,
                (centerY - (ApertureHeight * 0.5f) + (PictureHeight * 0.5f)) / PictureHeight);
            max = new Vector2(
                0.5f + halfU,
                (centerY + (ApertureHeight * 0.5f) + (PictureHeight * 0.5f)) / PictureHeight);
        }

        /// <summary>
        /// Where the picture lives inside a polaroid texture, in uv.
        ///
        /// There are exactly two layouts and they do NOT agree, which is why this
        /// reads the texture instead of assuming: the studio's snap keeps 24 px
        /// on three sides and 48 at the bottom of a 512 square, scaled by
        /// SnapSize, and its picture is 696 by 660; the drawn fallback of
        /// PhotoDefs uses 24 / 16 / 32 around a SQUARE 208 picture. Both are
        /// centred horizontally, which is what lets the back quad keep working
        /// after its 180 degree turn.
        ///
        /// Told apart by size, because that is data rather than a name, and the
        /// snap is tested first so that it wins should the two sizes ever meet:
        /// the snap is what the player looks at, and the fallback lives for half
        /// a second. The fallback's picture is square, so it comes out 5 percent
        /// too wide in an aperture built for the snap's ratio. That is the right
        /// way round to spend the error: the fallback is a drawn approximation
        /// shown while the real render is pending, and under -nographics there
        /// are no pixels for it to be wrong in.
        ///
        /// Anything else (no texture yet, or one this component did not expect)
        /// maps whole, which is what the polaroid did before V-PROP-02 and is
        /// never worse than blank.
        /// </summary>
        private static void PictureWindowUv(Texture texture, out Vector2 min, out Vector2 max)
        {
            min = Vector2.zero;
            max = Vector2.one;
            if (texture == null)
            {
                return;
            }

            if (texture.width == PhotoSnaps.SnapSize)
            {
                float side = PhotoSnaps.Border / (float)PhotoSnaps.SnapSize;
                float bottom = PhotoSnaps.BottomBorder / (float)PhotoSnaps.SnapSize;
                min = new Vector2(side, bottom);
                max = new Vector2(1f - side, 1f - side);
                return;
            }

            if (texture.width == PhotoDefs.ThumbSize)
            {
                // PhotoDefs measures its inset from the TOP of the image, and a
                // Texture2D stores row 0 at the BOTTOM (the thumbnail flips its
                // rows once on the way in), so the bottom margin here is what is
                // left under the picture and not ThumbInnerY.
                float size = PhotoDefs.ThumbSize;
                min = new Vector2(
                    PhotoDefs.ThumbInnerX / size,
                    (PhotoDefs.ThumbSize - PhotoDefs.ThumbInnerY - PhotoDefs.ThumbInnerSize) / size);
                max = new Vector2(
                    (PhotoDefs.ThumbInnerX + PhotoDefs.ThumbInnerSize) / size,
                    (PhotoDefs.ThumbSize - PhotoDefs.ThumbInnerY) / size);
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
        ///
        /// The uv still spans the whole quad 0 to 1. Which part of the texture
        /// that lands on is the MATERIAL's business since V-PROP-02, so this mesh
        /// stays one shared quad for every polaroid in the game while each item
        /// crops its own picture (see ApplyPicture).
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
