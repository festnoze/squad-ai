using System.Collections.Generic;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// A box of the world that a photo may replace. Whether it actually can is
    /// the GROUND LANGUAGE, readable at a glance and never spelled out to the
    /// player (PRD 5.1):
    ///
    ///   grey / solid colors = permanent. A photo placed over it is ADDED to
    ///       it: the slab stays, the bridge lands on top. These blocks are in
    ///       the "photographable" group only.
    ///   pale and lavender   = ephemeral. The frame carves them. These are in
    ///       "photographable" AND "carvable".
    ///
    /// Carving is PARTIAL: instead of vanishing whole, the part of the volume
    /// caught in the frustum is cut out and the remainder survives as smaller
    /// blocks, themselves carvable.
    ///
    /// The cut is box-minus-box: the hole is the axis-aligned bounding box (in
    /// this block's local space) of the sampled frustum intersection, and the
    /// remainder decomposes into at most 6 slabs. The AABB over-approximates
    /// the hole when the photo is placed at an angle, which errs on the
    /// generous side for the player (the opening is at least as big as the
    /// frame). Sampling in local space also handles rotated blocks (the stairs
    /// ramp).
    /// </summary>
    public sealed class ErasableBlock : MonoBehaviour
    {
        public const float SampleSpacing = 0.15f;
        public const int MaxSteps = 36;
        public const float MinFragment = 0.08f;

        private static readonly string[] NoGroups = new string[0];

        /// <summary>
        /// Unity's built-in unit cube, fetched once and shared by every block
        /// that has to fall back on it (V-GEO-01 draws a beveled box instead).
        /// </summary>
        private static Mesh cubeMesh;

        public Vector3 BlockSize = Vector3.one;
        public string ColorKey = "erasable";

        /// <summary>
        /// Godot emission energy, passed straight to Materials.Solid: 0.25 for
        /// lavender, 0 for everything else (PRD 5.2).
        /// </summary>
        public float Emissive;

        public string[] ExtraGroups = NoGroups;

        /// <summary>
        /// False for the permanent half of the ground language: the block is
        /// still photographable, but no frame ever cuts it. Fragments inherit
        /// it.
        /// </summary>
        public bool Carvable = true;

        /// <summary>
        /// Sentinel for <see cref="Seed"/>. NaN is the only float a hash can
        /// never be taken for, and it never compares equal to itself, so a
        /// stale "already resolved" test is impossible to write by accident.
        /// </summary>
        public const float UnsetSeed = float.NaN;

        /// <summary>
        /// Per-instance seed for the Viewpoint/Surface shader (V-MAT-03): the
        /// tiny hue and value jitter that keeps two blocks of one palette color
        /// from being the same object twice. It is a FIELD, and not a hash of
        /// the position taken in the shader or at build time, for two reasons
        /// the PRD makes explicit:
        ///
        ///   - fragments of a carve INHERIT the parent's seed, and they sit at
        ///     new positions. Hashing their own position would give every
        ///     survivor a fresh color the instant a block is cut, which is
        ///     exactly the visible bug V-MAT-03 forbids;
        ///   - a retired block is deactivated and revived intact by the rewind,
        ///     never destroyed, so the seed has to survive that round trip. A
        ///     field on the component does; a static registry keyed on anything
        ///     transient does not.
        ///
        /// <see cref="UnsetSeed"/> means "derive it from the position", which
        /// only happens once the position means something (see ResolveSeed).
        /// </summary>
        public float Seed = UnsetSeed;

        /// <summary>
        /// Extra chamfer on the TOP edges only (PRD_VISUAL 4.6 V-GEO-04): the
        /// 6 cm rounded lip that makes a platform edge read as finished paving
        /// rather than as a cut. Zero means "no lip", which is the right answer
        /// for everything except the ground a player walks on: a crate or a
        /// lavender wall with a rounded top reads as soft, and this game's
        /// ephemeral matter needs to look like matter.
        ///
        /// Carve fragments deliberately do NOT inherit it. A fragment's top is
        /// usually a fresh CUT through the middle of a block, and a cut with a
        /// finished paved lip on it would be a lie about what just happened.
        /// </summary>
        public float TopBevel;

        /// <summary>
        /// How long a fresh carve fragment glows (PRD_VISUAL 4.8 V-VFX-02).
        /// This is the item's SANCTIONED FALLBACK duration: the whole fragment
        /// glows for 0.3 s rather than the full version's 0.6 s on the cut
        /// faces only. The full version needs the hole's six planes handed to
        /// the shader and a per face compare there; Viewpoint/Surface carries a
        /// single scalar _CutGlow and no plane list, so the full version is a
        /// shader change, not a change here, and the acceptance criterion is
        /// only that "a carve is legible as an event without obscuring the new
        /// opening".
        /// </summary>
        public const float CutGlowSeconds = 0.3f;

        /// <summary>
        /// The value pushed to the shader's _CutGlow, and the seconds of flash
        /// still to run. Both are PRESENTATION ONLY: nothing in this file waits
        /// on them. A carve fragment has its final size, collider, groups, seed
        /// and pose on the frame it is born, exactly as before Tier 4, and the
        /// glow merely lags the LOOK (the tier's central rule, and what the
        /// PlayMode probe measures one frame after a placement).
        /// </summary>
        private float cutGlow;

        private float cutGlowLeft;

        /// <summary>
        /// The shader's _Reveal (1 = fully resolved). Nothing animates it yet:
        /// it is carried here because a MaterialPropertyBlock is set WHOLE, so
        /// the dissolve of V-VFX-01 cannot be written by a second block on the
        /// same renderer without erasing this one's _Seed and _CutGlow. See
        /// <see cref="SetReveal"/>.
        /// </summary>
        private float reveal = 1f;

        private bool showMesh = true;
        private MeshRenderer meshRenderer;
        private bool built;

        /// <summary>
        /// The two Tier 4 floats of Viewpoint/Surface. Materials.cs publishes
        /// SeedId because the factory needs it; these two are only ever written
        /// per renderer, from here, so they live here.
        /// </summary>


        /// <summary>
        /// When false the block keeps collision and carvability but shows no
        /// box (the invisible stairs ramp). Fragments inherit it. Callers set
        /// it after Create, so the renderer is always built and merely
        /// disabled here rather than skipped.
        /// </summary>
        public bool ShowMesh
        {
            get { return showMesh; }
            set
            {
                showMesh = value;
                if (meshRenderer != null)
                {
                    meshRenderer.enabled = value;
                }
            }
        }

        /// <summary>
        /// The one factory every caller goes through. <paramref name="seed"/> is
        /// optional and LAST on purpose: LevelBuilder, PhotoContent and the
        /// EditMode suites all call this by position, and only a carve has a
        /// seed to hand down (V-MAT-03).
        /// </summary>
        public static ErasableBlock Create(Vector3 size, string color, float emissive = 0f, string[] extraGroups = null, bool canCarve = true, float seed = UnsetSeed, float topBevel = 0f)
        {
            GameObject go = new GameObject("ErasableBlock");
            // The groups are joined in OnEnable, which reads Carvable and
            // ExtraGroups: the object stays inactive until every field is set,
            // otherwise AddComponent would register it with the defaults.
            go.SetActive(false);
            go.layer = Layers.World;
            ErasableBlock block = go.AddComponent<ErasableBlock>();
            block.BlockSize = size;
            block.ColorKey = color;
            block.Emissive = emissive;
            block.ExtraGroups = extraGroups == null ? NoGroups : extraGroups;
            block.Carvable = canCarve;
            // Before Build, which pushes an already-known seed to the renderer
            // it is about to create.
            block.Seed = seed;
            // Also before Build, which bakes the lip into the mesh it picks.
            block.TopBevel = topBevel;
            block.Build();
            go.SetActive(true);
            return block;
        }

        // Everything the eye sees can be photographed; only the ephemeral half
        // of the language can be carved. Registering here and unregistering in
        // OnDisable is what lets the rewind graveyard take a block out of the
        // world without destroying it.
        private void OnEnable()
        {
            Groups.Add(this, Groups.Photographable);
            if (Carvable)
            {
                Groups.Add(this, Groups.Carvable);
            }
            string[] extras = Extras();
            for (int i = 0; i < extras.Length; i++)
            {
                if (!string.IsNullOrEmpty(extras[i]))
                {
                    Groups.Add(this, extras[i]);
                }
            }
        }

        private void OnDisable()
        {
            // Retiring a block is what puts it in the rewind graveyard, and it
            // is the one moment the flash must be CANCELLED rather than paused.
            // Undoing a carve retires the fragments and revives the parent, and
            // a fragment revived later (redo, or a second carve of the same
            // wall) would otherwise light up again for whatever was left of its
            // 0.3 s, which reads as a carve that never happened. Extinguished
            // here, so a block always comes back from the graveyard settled and
            // the rewind never replays the effect. Pushing the block while the
            // object is inactive is free: the renderer draws nothing until it is
            // active again, and it is already carrying the settled value then.
            if (cutGlowLeft > 0f)
            {
                cutGlowLeft = 0f;
                cutGlow = 0f;
                PushInstanceBlock();
            }

            Groups.Remove(this, Groups.Photographable);
            if (Carvable)
            {
                Groups.Remove(this, Groups.Carvable);
            }
            string[] extras = Extras();
            for (int i = 0; i < extras.Length; i++)
            {
                if (!string.IsNullOrEmpty(extras[i]))
                {
                    Groups.Remove(this, extras[i]);
                }
            }
        }

        /// <summary>
        /// ExtraGroups is a public field a caller may clear, and OnEnable runs on
        /// every rewind restore: a null array there would be a hard crash rather
        /// than a block with no extra groups.
        /// </summary>
        private string[] Extras()
        {
            return ExtraGroups == null ? NoGroups : ExtraGroups;
        }

        private void Build()
        {
            if (built)
            {
                return;
            }
            built = true;

            // The collider stays the EXACT box: the carve samples and the
            // physics stages of the probe both read BlockSize directly, and
            // V-GEO-01 chamfers the picture only.
            BoxCollider box = gameObject.AddComponent<BoxCollider>();
            box.size = BlockSize;

            GameObject visual = new GameObject("Mesh");
            visual.layer = Layers.World;
            visual.transform.SetParent(transform, false);
            MeshFilter filter = visual.AddComponent<MeshFilter>();

            // The bevel has to be UNIFORM IN WORLD SPACE. This used to draw the
            // builtin unit cube scaled by BlockSize, and a scaled unit cube
            // scales its chamfer with it: on a 4 x 0.2 x 4 platform a 2.5 cm
            // bevel would come out 10 cm on two axes and 0.5 cm on the third.
            // BeveledBox bakes the size into the mesh (its outer extents ARE
            // BlockSize), so the child stays at unit scale.
            //
            // Unit scale is what the Viewpoint/Surface shader needs too. It
            // samples its textures triplanar from WORLD POSITION, which does not
            // care about scale, but a non-uniform scale skews the interpolated
            // normals, and both the lighting and the triplanar normal blend read
            // those normals. A block left scaled would light wrongly on every
            // face and there would be nothing on screen naming the cause.
            // TopBevel is 0 for everything but the ground a player walks on, so
            // the default cache key is unchanged for every crate, wall and
            // fragment in the game and only platforms add a second entry.
            Mesh beveled = ProceduralMeshes.BeveledBox(BlockSize, 0.025f, TopBevel);
            if (beveled != null)
            {
                visual.transform.localScale = Vector3.one;
                filter.sharedMesh = beveled;
            }
            else
            {
                // A null mesh makes the whole world invisible, so the builtin
                // cube stays as the floor under this. The scale belongs to THIS
                // branch and to no other: mesh and scale are set together in
                // each branch so no later edit can leave a size-baked mesh
                // scaled by its own size, which would draw a block BlockSize
                // times too big instead of merely wrong.
                Debug.LogError("ErasableBlock: BeveledBox returned no mesh, falling back on the builtin cube.");
                visual.transform.localScale = BlockSize;
                filter.sharedMesh = CubeMesh();
            }

            meshRenderer = visual.AddComponent<MeshRenderer>();
            meshRenderer.sharedMaterial = Materials.Solid(ColorKey, Emissive);
            meshRenderer.enabled = showMesh;

            // A seed handed down by a carve is already final and can go to the
            // renderer now. One derived from a position cannot: Create builds
            // the object at the origin and every caller positions it AFTER, so
            // hashing here would give every block in the level the hash of
            // (0, 0, 0) and no jitter at all. That is what ResolveSeed is for.
            if (!float.IsNaN(Seed))
            {
                PushInstanceBlock();
            }
        }

        /// <summary>
        /// The first frame is the earliest moment a block's position is the one
        /// it will keep: LevelBuilder and PhotoContent both call Create and then
        /// place the object, and Create runs OnEnable before either. A block
        /// revived from the rewind graveyard already has its seed and this never
        /// runs twice, so the jitter survives a rewind unchanged.
        /// </summary>
        private void Start()
        {
            ResolveSeed();
        }

        /// <summary>
        /// Runs the carve flash down (V-VFX-02). Costs one early return per
        /// block per frame in the settled case, which is what a level of under a
        /// hundred renderers (PRD_VISUAL 3.3) can pay for.
        ///
        /// The obvious saving, switching the COMPONENT off while it has nothing
        /// to animate, is a trap in this file: `enabled = false` fires OnDisable,
        /// which is where a block leaves Groups.Photographable and
        /// Groups.Carvable. A settled block would quietly stop being
        /// photographable, and the design audit would still pass because the
        /// group is only read while playing.
        ///
        /// Unscaled, like Hud.Fade and for the same reason: the flash is
        /// presentation, and a stopped or slowed clock must not leave a fragment
        /// frozen at full lavender.
        /// </summary>
        private void Update()
        {
            if (cutGlowLeft <= 0f)
            {
                return;
            }

            cutGlowLeft -= Time.unscaledDeltaTime;
            if (cutGlowLeft <= 0f)
            {
                cutGlowLeft = 0f;
                cutGlow = 0f;
            }
            else
            {
                // Squared, so the flash drops fast and lingers faintly. The
                // shader multiplies this by CutGlowEnergy 1.7, so a linear ramp
                // would hold the whole fragment over V-POST-01's 1.05 bloom
                // threshold for the first two thirds of the 0.3 s and the bloom
                // would veil the very opening the carve just made. Squared, it
                // crosses back under in about 60 ms: bright enough to read as an
                // event, brief enough not to be a flare over the new hole.
                float left = cutGlowLeft / CutGlowSeconds;
                cutGlow = left * left;
            }

            PushInstanceBlock();
        }

        /// <summary>
        /// Lights the carve flash on a fragment that was just born. Sets shader
        /// state and NOTHING else: no collider, no group, no rewind event and no
        /// counter moves with it, so the frame a carve happens is identical to
        /// what it was before this tier.
        /// </summary>
        private void FlashCut()
        {
            cutGlow = 1f;
            cutGlowLeft = CutGlowSeconds;
            PushInstanceBlock();
        }

        /// <summary>
        /// The safe door for V-VFX-01's dissolve. A MaterialPropertyBlock is set
        /// WHOLE: a caller that writes _Reveal through a block of its own on this
        /// renderer erases _Seed (every carved fragment loses the jitter it
        /// inherited, V-MAT-03) and erases _CutGlow with it. Going through here
        /// keeps the one block this component owns.
        /// </summary>
        public void SetReveal(float value)
        {
            reveal = Mathf.Clamp01(value);
            PushInstanceBlock();
        }

        /// <summary>
        /// Gives the block a seed if it has none yet, from its CURRENT position,
        /// and pushes it to the renderer. Idempotent and public so a caller that
        /// positions a block itself can make the jitter final at once instead of
        /// waiting for the first frame.
        /// </summary>
        public void ResolveSeed()
        {
            if (float.IsNaN(Seed))
            {
                Seed = Materials.SeedFor(transform.position);
            }

            PushInstanceBlock();
        }

        /// <summary>
        /// Pushes every per-instance float through a MaterialPropertyBlock, which
        /// is what lets every block of one color keep sharing the ONE material
        /// Materials.Solid cached: a per-instance material would multiply the
        /// cache by the number of blocks and break the shared identity the
        /// picture studio relies on (PRD_VISUAL 3.4). The price is that this
        /// renderer opts out of SRP batching; a level holds under a hundred
        /// renderers (3.3), so it is affordable here and would not be in a
        /// bigger world.
        ///
        /// EVERY float goes out on EVERY call, and that is the whole point of
        /// there being one function. SetPropertyBlock replaces the block WHOLE:
        /// a second block carrying only _CutGlow would erase the _Seed this
        /// pushed, and every carve fragment would silently lose the color
        /// jitter it inherited from its parent (V-MAT-03) at the exact moment a
        /// carve made it visible. Anything new that this shader needs per
        /// renderer is added to this one block, never beside it.
        ///
        /// Named for the block and not for the seed since Tier 4, for the same
        /// reason.
        /// </summary>
        private void PushInstanceBlock()
        {
            if (meshRenderer == null)
            {
                return;
            }

            MaterialPropertyBlock block = new MaterialPropertyBlock();
            // NaN is the "no seed yet" sentinel of the FIELD and must never
            // reach the shader, which feeds _Seed into a frac() and into the
            // reveal noise: NaN there propagates into the albedo and paints the
            // block black or leaves it undefined per platform. Callers today all resolve the seed
            // first (Build only pushes a known one, ResolveSeed resolves before
            // pushing), so this only covers a future caller that pushes _Reveal
            // or _CutGlow between Create and the first Start: it renders one
            // frame with no jitter instead of one frame of nothing.
            block.SetFloat(Materials.SeedId, float.IsNaN(Seed) ? 0f : Seed);
            block.SetFloat(Materials.CutGlowId, cutGlow);
            block.SetFloat(Materials.RevealId, reveal);
            meshRenderer.SetPropertyBlock(block);
        }

        private static Mesh CubeMesh()
        {
            if (cubeMesh == null)
            {
                // 1 x 1 x 1 centered on the origin. Only the fallback branch of
                // Build uses it now, and that branch is the one that puts
                // BlockSize back on the child's scale.
                cubeMesh = Resources.GetBuiltinResource<Mesh>("Cube.fbx");
            }
            if (cubeMesh == null)
            {
                // Belt and braces: a null mesh would make the whole world
                // invisible, so fall back on the primitive's own cube.
                GameObject temp = GameObject.CreatePrimitive(PrimitiveType.Cube);
                cubeMesh = temp.GetComponent<MeshFilter>().sharedMesh;
                UnityEngine.Object.DestroyImmediate(temp);
            }
            return cubeMesh;
        }

        /// <summary>
        /// Carves the intersection with the photo frustum out of this block.
        /// <paramref name="anchorInverse"/> maps world space to the placement
        /// anchor. Returns true when the block was modified (fragmented or
        /// fully removed).
        /// </summary>
        public bool CarveWithFrustum(Matrix4x4 anchorInverse, float fovDeg, float aspect, float depth)
        {
            Matrix4x4 toAnchor = anchorInverse * transform.localToWorldMatrix;
            int stepsX = AxisSteps(BlockSize.x);
            int stepsY = AxisSteps(BlockSize.y);
            int stepsZ = AxisSteps(BlockSize.z);
            Vector3 spacing = new Vector3(
                BlockSize.x / (stepsX - 1),
                BlockSize.y / (stepsY - 1),
                BlockSize.z / (stepsZ - 1));
            Vector3 boxMin = -BlockSize * 0.5f;

            bool found = false;
            Vector3 lo = new Vector3(float.PositiveInfinity, float.PositiveInfinity, float.PositiveInfinity);
            Vector3 hi = new Vector3(float.NegativeInfinity, float.NegativeInfinity, float.NegativeInfinity);
            for (int ix = 0; ix < stepsX; ix++)
            {
                for (int iy = 0; iy < stepsY; iy++)
                {
                    for (int iz = 0; iz < stepsZ; iz++)
                    {
                        Vector3 local = boxMin + new Vector3(ix * spacing.x, iy * spacing.y, iz * spacing.z);
                        Vector3 inAnchor = toAnchor.MultiplyPoint3x4(local);
                        // PhotoMath reads design space (-z forward). The mirror
                        // is its own inverse, so ToUnity is also the way back
                        // from a Unity point to a design one.
                        Vector3 design = DesignSpace.ToUnity(inAnchor);
                        if (PhotoMath.PointInFrustum(design, fovDeg, aspect, 0f, depth))
                        {
                            found = true;
                            lo = Vector3.Min(lo, local);
                            hi = Vector3.Max(hi, local);
                        }
                    }
                }
            }
            if (!found)
            {
                return false;
            }

            // Grow by half a sample step so no film thinner than the sampling
            // grid survives along the hole borders.
            Vector3 holeMin = lo - spacing * 0.51f;
            Vector3 holeMax = hi + spacing * 0.51f;

            List<(Vector3 center, Vector3 size)> pieces = Decompose(BlockSize, holeMin, holeMax);
            Transform parent = transform.parent;
            // The survivors are the same matter as the block they came from, so
            // they inherit its seed (V-MAT-03): hashing their own new positions
            // would repaint the whole wall around the hole at the moment of the
            // cut. Resolved here rather than read raw, because a block carved in
            // the frame it was built in has not reached its Start yet.
            ResolveSeed();
            for (int i = 0; i < pieces.Count; i++)
            {
                ErasableBlock fragment = Create(pieces[i].size, ColorKey, Emissive, ExtraGroups, Carvable, Seed);
                fragment.ShowMesh = ShowMesh;
                fragment.transform.SetParent(parent, false);
                fragment.transform.SetPositionAndRotation(transform.TransformPoint(pieces[i].center), transform.rotation);
                Rewind.NoticeSpawn(fragment.gameObject);
                // LAST, and after the rewind already knows about the fragment:
                // the flash is the only thing in this loop that a reader may
                // reorder or delete without changing the game, and it says so by
                // sitting behind everything that cannot be (V-VFX-02).
                fragment.FlashCut();
            }
            Rewind.Retire(gameObject);
            return true;
        }

        /// <summary>
        /// Pure geometry: the box of the given size (centered on the origin)
        /// minus the hole AABB, decomposed into at most 6 slabs. Degenerate
        /// slabs thinner than MinFragment are dropped. Public and static for
        /// the tests.
        /// </summary>
        public static List<(Vector3 center, Vector3 size)> Decompose(Vector3 size, Vector3 holeMin, Vector3 holeMax)
        {
            Vector3 boxMin = -size * 0.5f;
            Vector3 boxMax = size * 0.5f;
            // Clamped first, so a hole entirely off the box collapses onto a
            // face and leaves the whole box as one piece.
            Vector3 lo = ClampComponents(holeMin, boxMin, boxMax);
            Vector3 hi = ClampComponents(holeMax, boxMin, boxMax);
            List<(Vector3 center, Vector3 size)> pieces = new List<(Vector3 center, Vector3 size)>();
            // Left / right of the hole, full height and thickness.
            PushPiece(pieces, boxMin, new Vector3(lo.x, boxMax.y, boxMax.z));
            PushPiece(pieces, new Vector3(hi.x, boxMin.y, boxMin.z), boxMax);
            // Below / above the hole, within its x span.
            PushPiece(pieces, new Vector3(lo.x, boxMin.y, boxMin.z), new Vector3(hi.x, lo.y, boxMax.z));
            PushPiece(pieces, new Vector3(lo.x, hi.y, boxMin.z), new Vector3(hi.x, boxMax.y, boxMax.z));
            // In front / behind the hole, within its x and y span.
            PushPiece(pieces, new Vector3(lo.x, lo.y, boxMin.z), new Vector3(hi.x, hi.y, lo.z));
            PushPiece(pieces, new Vector3(lo.x, lo.y, hi.z), new Vector3(hi.x, hi.y, boxMax.z));
            return pieces;
        }

        private static void PushPiece(List<(Vector3 center, Vector3 size)> pieces, Vector3 a, Vector3 b)
        {
            Vector3 pieceSize = b - a;
            if (pieceSize.x < MinFragment || pieceSize.y < MinFragment || pieceSize.z < MinFragment)
            {
                return;
            }
            pieces.Add(((a + b) * 0.5f, pieceSize));
        }

        private static Vector3 ClampComponents(Vector3 v, Vector3 min, Vector3 max)
        {
            return Vector3.Min(Vector3.Max(v, min), max);
        }

        private static int AxisSteps(float dim)
        {
            return Mathf.Clamp(Mathf.CeilToInt(dim / SampleSpacing) + 1, 2, MaxSteps);
        }
    }
}
