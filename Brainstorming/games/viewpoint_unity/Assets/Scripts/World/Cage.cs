using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// A barred cage (PRD section 5.3). ONE static body: breaking a cage
    /// removes the whole thing at once, and the point the breakable test reads
    /// is this transform, the volumetric center of the cage.
    ///
    /// Visuals are bars with gaps, so the loot inside stays visible, while
    /// collision is four full thin walls: neither the player nor the
    /// interaction ray passes between the bars. The lens does (section 7.3),
    /// which is how a steel cage is beaten.
    ///
    /// The cage is not photographable: a lattice copied as a solid block would
    /// seal its own copied battery inside.
    /// </summary>
    public sealed class Cage : MonoBehaviour
    {
        /// Collision walls are 0.12 thick and inset 0.06, so their outer face
        /// is flush with the face of the cage.
        const float WallThickness = 0.12f;
        const float WallInset = 0.06f;

        /// One bar every half meter along a face, two spans minimum.
        const float BarSpan = 0.5f;
        const float BarThickness = 0.07f;
        const float RailThickness = 0.1f;

        /// Rails sit just under the top edge and just above the bottom one.
        const float RailInset = 0.06f;

        /// Full extents of the cage, kept for the tests and the audit.
        public Vector3 CageSize = Vector3.one;

        /// Palette key the cage was painted with, kept for the same reason.
        public string CageColor = "battery_tip";

        /// Steel: no placement ever breaks it, so it stays out of "breakable".
        public bool Sealed;

        public bool HasRoof = true;

        /// <summary>
        /// Builds a complete cage centered on its own origin. The object comes
        /// back INACTIVE and unparented: the caller places it and enables it,
        /// because the group registration happens on enable and must see the
        /// final value of Sealed.
        /// </summary>
        public static Cage Create(Vector3 size, bool erasable, bool roof, bool isSealed)
        {
            GameObject go = new GameObject("Cage");
            go.SetActive(false);
            go.layer = Layers.World;

            Cage cage = go.AddComponent<Cage>();
            cage.CageSize = size;
            cage.Sealed = isSealed;
            cage.HasRoof = roof;

            // Steel is never lavender: the original folds "and not sealed" into
            // this choice, and repeating it here keeps a hand written
            // definition that declares both readable as steel.
            bool lavender = erasable && !isSealed;
            cage.CageColor = lavender ? "erasable" : (isSealed ? "sealed" : "battery_tip");
            cage.Build(Materials.Solid(cage.CageColor, lavender ? 0.25f : 0f));
            return cage;
        }

        void OnEnable()
        {
            // "cage" is what the world knows about; "breakable" is what a
            // placement may remove. A steel cage is in the first group only.
            Groups.Add(this, Groups.Cage);
            if (!Sealed)
            {
                Groups.Add(this, Groups.Breakable);
            }
        }

        void OnDisable()
        {
            Groups.Remove(this, Groups.Cage);
            if (!Sealed)
            {
                Groups.Remove(this, Groups.Breakable);
            }
        }

        void Build(Material material)
        {
            Vector3 size = CageSize;
            float halfX = size.x * 0.5f - WallInset;
            float halfZ = size.z * 0.5f - WallInset;

            AddWall(new Vector3(halfX, 0f, 0f), new Vector3(WallThickness, size.y, size.z), false, material);
            AddWall(new Vector3(-halfX, 0f, 0f), new Vector3(WallThickness, size.y, size.z), false, material);
            AddWall(new Vector3(0f, 0f, halfZ), new Vector3(size.x, size.y, WallThickness), true, material);
            AddWall(new Vector3(0f, 0f, -halfZ), new Vector3(size.x, size.y, WallThickness), true, material);

            if (HasRoof)
            {
                AddCollider(new Vector3(size.x, WallThickness, size.z), new Vector3(0f, size.y * 0.5f - WallInset, 0f));
                AddBox("Roof", new Vector3(size.x, 0.1f, size.z), new Vector3(0f, size.y * 0.5f - 0.05f, 0f), material);
            }
        }

        /// One face: a full invisible wall for physics, then the bars and the
        /// two rails that make it read as a cage.
        void AddWall(Vector3 offset, Vector3 wall, bool alongX, Material material)
        {
            AddCollider(wall, offset);

            float span = alongX ? wall.x : wall.z;
            int barCount = Mathf.Max((int)(span / BarSpan), 2);
            for (int i = 0; i <= barCount; i++)
            {
                float t = -span * 0.5f + span * (float)i / (float)barCount;
                Vector3 along = alongX ? new Vector3(t, 0f, 0f) : new Vector3(0f, 0f, t);
                AddBox("Bar", new Vector3(BarThickness, wall.y, BarThickness), offset + along, material);
            }

            Vector3 railSize = alongX
                ? new Vector3(span, RailThickness, RailThickness)
                : new Vector3(RailThickness, RailThickness, span);
            AddBox("Rail", railSize, offset + new Vector3(0f, wall.y * 0.5f - RailInset, 0f), material);
            AddBox("Rail", railSize, offset + new Vector3(0f, -wall.y * 0.5f + RailInset, 0f), material);
        }

        /// Several box colliders on the same GameObject: four walls and a roof,
        /// but a single body.
        void AddCollider(Vector3 size, Vector3 designCenter)
        {
            BoxCollider box = gameObject.AddComponent<BoxCollider>();
            box.size = size;
            box.center = DesignSpace.ToUnity(designCenter);
        }

        /// Decoration only. The cage is symmetric, so the mirror on z changes
        /// nothing here, but authored offsets go through it like every other
        /// position rather than being special cased.
        void AddBox(string name, Vector3 size, Vector3 designLocalPos, Material material)
        {
            GameObject box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.layer = Layers.World;

            // CreatePrimitive hands out a collider; the walls above are the
            // only collision a cage has. This runs while the cage is being
            // built, never on a live world object. Disabling comes first
            // because Destroy only bites at the end of the frame, and a bar
            // that collides for one frame is a bar the player can stand on.
            Collider extra = box.GetComponent<Collider>();
            if (extra != null)
            {
                extra.enabled = false;
                if (Application.isPlaying)
                {
                    UnityEngine.Object.Destroy(extra);
                }
                else
                {
                    UnityEngine.Object.DestroyImmediate(extra);
                }
            }

            box.transform.SetParent(transform, false);
            box.transform.localPosition = DesignSpace.ToUnity(designLocalPos);
            box.transform.localScale = size;
            box.GetComponent<MeshRenderer>().sharedMaterial = material;
        }
    }
}
