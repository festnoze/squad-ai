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

        /// <summary>Unity's built-in unit cube, fetched once and shared by every block.</summary>
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

        private bool showMesh = true;
        private MeshRenderer meshRenderer;
        private bool built;

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

        public static ErasableBlock Create(Vector3 size, string color, float emissive = 0f, string[] extraGroups = null, bool canCarve = true)
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

            BoxCollider box = gameObject.AddComponent<BoxCollider>();
            box.size = BlockSize;

            // The size lives on the mesh child as a scale so the block's own
            // transform stays unscaled: the carve samples and the collider both
            // read BlockSize directly.
            GameObject visual = new GameObject("Mesh");
            visual.layer = Layers.World;
            visual.transform.SetParent(transform, false);
            visual.transform.localScale = BlockSize;
            MeshFilter filter = visual.AddComponent<MeshFilter>();
            filter.sharedMesh = CubeMesh();
            meshRenderer = visual.AddComponent<MeshRenderer>();
            meshRenderer.sharedMaterial = Materials.Solid(ColorKey, Emissive);
            meshRenderer.enabled = showMesh;
        }

        private static Mesh CubeMesh()
        {
            if (cubeMesh == null)
            {
                // 1 x 1 x 1 centered on the origin, so the mesh child only
                // needs BlockSize as its scale.
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
            for (int i = 0; i < pieces.Count; i++)
            {
                ErasableBlock fragment = Create(pieces[i].size, ColorKey, Emissive, ExtraGroups, Carvable);
                fragment.ShowMesh = ShowMesh;
                fragment.transform.SetParent(parent, false);
                fragment.transform.SetPositionAndRotation(transform.TransformPoint(pieces[i].center), transform.rotation);
                Rewind.NoticeSpawn(fragment.gameObject);
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
