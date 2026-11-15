using Meuble.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace Meuble
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 3, 9, 15.1 and 15.2): one door leaf and its 0.6 s swing.
    /// <list type="bullet">
    /// <item>Its transform is the leaf box pose of <see cref="DoorGeometry.Pose"/> at the current angle: the collider
    /// (child "Solid", a BoxCollider on the Occluder layer) and the visual (child "Leaf", DoorWood) are centred on it. The
    /// level audit poses a leaf by setting this transform and toggles the colliders under it.</item>
    /// <item>Closed (0 deg) it fills its doorway: it blocks the player and every sight ray through it. It is never a
    /// NavMesh source; the one NavMesh gives its doorway the area <see cref="Area"/>, left out of a plan while closed.</item>
    /// <item><see cref="BeginOpen"/> starts the swing: <see cref="Tuning.DoorSwingDegrees"/> over
    /// <see cref="Tuning.DoorOpenTime"/> (30 fixed steps), stepped by GameState through <see cref="Step"/>. The collider
    /// moves with the leaf from the first step, and <see cref="Samples"/> holds the 4 leaf samples at the current angle
    /// only while it swings: on all 30 steps of the swing, the 30th at the open angle (v3 15.2). The swing ends at the
    /// start of the next <see cref="Step"/> (wave 5A.1, critique m5).</item>
    /// <item>Open, it keeps its collider and still occludes, in its open pose against the end of the opening.</item>
    /// <item>It fades with its wall's centre plane (WallFader), as a shared doorway's frame does, and also whenever a
    /// sight line from the camera to the player furniture crosses its box at its current pose (wave 5A.1, critique m15:
    /// an open leaf in the player's room never hides the furniture). Faded, it keeps casting its shadow.</item>
    /// </list>
    /// </summary>
    public sealed class DoorLeaf : MonoBehaviour
    {
        private static readonly Vector3[] None = new Vector3[0];

        public string Id;
        public DoorGeometry Geometry;
        /// <summary>The leaf's index among the level's leaves (LevelDef.LeafDoors order): its OpenMask bit and its area.</summary>
        public int Index;
        /// <summary>The leaf's collider (on the child "Solid").</summary>
        public BoxCollider Collider;
        /// <summary>The leaf's visual (the child "Leaf").</summary>
        public MeshRenderer Renderer;

        /// <summary>The NavMesh area of the leaf's doorway: <see cref="Tuning.DoorAreaBase"/> + <see cref="Index"/>.</summary>
        public int Area => Tuning.DoorAreaBase + Index;

        /// <summary>True from <see cref="BeginOpen"/> on (opening or open), or when authored open. A leaf never closes again.</summary>
        public bool Open { get; private set; }

        /// <summary>
        /// True during the swing: from <see cref="BeginOpen"/> through the last of its 30 steps, until the start of the next
        /// <see cref="Step"/>, so the leaf is sampled on all 30 steps of its swing (v3 15.2).
        /// </summary>
        public bool Swinging { get; private set; }

        /// <summary>0 closed, 1 open.</summary>
        public float SwingProgress { get; private set; }

        /// <summary>The current swing angle in degrees (0 closed, <see cref="Tuning.DoorSwingDegrees"/> open).</summary>
        public float Angle => SwingProgress * Tuning.DoorSwingDegrees;

        /// <summary>Fixed steps of the current or last swing (30 for a full one).</summary>
        public int SwingSteps { get; private set; }

        /// <summary>The leaf's sample points at the current angle while it swings; empty otherwise.</summary>
        public Vector3[] Samples { get; private set; } = None;

        /// <summary>
        /// Builds the leaf of <paramref name="door"/> (leaf <paramref name="index"/> of the level) under
        /// <paramref name="parent"/>, closed or open as authored, and registers its visual with the wall fader.
        /// </summary>
        public static DoorLeaf Create(LevelDef level, OpeningDef door, int index, Transform parent, Material material, WallFader fader)
        {
            var geometry = new DoorGeometry(level, door);
            int occluder = Layers.Occluder;
            var go = new GameObject("DoorLeaf " + door.Id) { layer = occluder };
            go.transform.SetParent(parent, false);
            var leaf = go.AddComponent<DoorLeaf>();
            leaf.Id = door.Id;
            leaf.Index = index;
            leaf.Geometry = geometry;
            geometry.Pose(0f, out Vector3 size);

            var solid = new GameObject("Solid") { layer = occluder };
            solid.transform.SetParent(go.transform, false);
            leaf.Collider = solid.AddComponent<BoxCollider>();
            leaf.Collider.size = size;

            GameObject visual = PrimitiveKit.Box(go.transform, "Leaf", Vector3.zero, size, material, occluder, false, Surface.Wood);
            leaf.Renderer = visual.GetComponent<MeshRenderer>();
            leaf.Renderer.shadowCastingMode = ShadowCastingMode.On;
            if (fader != null)
            {
                // The wall's centre plane: the leaf hides when that plane separates the camera from the player. Its box at
                // its current pose (this transform): the leaf hides when it stands between the camera and the player.
                Vector3 normal = geometry.AlongX ? Vector3.forward : Vector3.right;
                fader.Add(leaf.Renderer, geometry.Center, normal, go.transform, size);
            }

            bool open = door.Leaf == OpeningDef.LeafOpen;
            leaf.Open = open;
            leaf.SwingProgress = open ? 1f : 0f;
            leaf.PoseAt(leaf.Angle);
            leaf.UpdateSamples();
            return leaf;
        }

        /// <summary>A closed leaf the furniture can open from where it stands (DoorGeometry.InReach; no facing condition).</summary>
        public bool InReach(FurnitureController furniture)
        {
            if (furniture == null || Open || Geometry == null)
            {
                return false;
            }
            return Geometry.InReach(furniture.transform.position, furniture.Size, furniture.Yaw);
        }

        /// <summary>Starts the swing of a closed leaf (nothing when it is already open or opening).</summary>
        public void BeginOpen()
        {
            if (Open)
            {
                return;
            }
            Open = true;
            Swinging = true;
            SwingProgress = 0f;
            SwingSteps = 0;
            UpdateSamples();
        }

        /// <summary>
        /// One fixed step of the swing: the angle advances by dt / DoorOpenTime of the full swing. The 30th step reaches the
        /// open angle and keeps its samples there; the next call ends the swing (no pose change, no samples, not counted in
        /// <see cref="SwingSteps"/>), so a leaf has samples on all 30 steps of its swing (CONTRACT_M5_v3 15.2).
        /// </summary>
        public void Step(float dt)
        {
            if (!Swinging)
            {
                return;
            }
            if (SwingProgress >= 1f)
            {
                // The step after the 30th: the swing ended at the open angle on the previous step.
                Swinging = false;
                UpdateSamples();
                return;
            }
            SwingSteps++;
            SwingProgress = Mathf.Min(1f, SwingProgress + dt / Tuning.DoorOpenTime);
            // 30 steps of 0.02 s add up to 1 within float rounding: the last one reaches the open angle.
            if (SwingProgress >= 1f - 1e-3f)
            {
                SwingProgress = 1f; // MUTATION:LEAF_LAST_STEP
            }
            PoseAt(Angle);
            UpdateSamples();
        }

        /// <summary>
        /// Poses the leaf at a swing angle (the audit and the tests pose leaves with it): the transform, then its collider
        /// with it, then the physics is synced so the next ray sees the leaf where it is drawn.
        /// </summary>
        public void PoseAt(float degrees)
        {
            if (Geometry == null)
            {
                return;
            }
            Pose pose = Geometry.Pose(degrees, out Vector3 _);
            transform.SetPositionAndRotation(pose.position, pose.rotation);
            Pose solid = pose; // MUTATION:LEAF_COLLIDER
            if (Collider != null)
            {
                Collider.transform.SetPositionAndRotation(solid.position, solid.rotation);
            }
            Physics.SyncTransforms();
        }

        private void UpdateSamples()
        {
            bool sampled = Swinging; // MUTATION:LEAF_SAMPLES
            Samples = sampled && Geometry != null ? Geometry.Samples(Angle) : None;
        }
    }
}
