using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace Meuble
{
    /// <summary>
    /// M2.1 readability (docs/CONTRACT_M2.md 11.6): a translucent ghost of the chair at the pose the
    /// inhabitant who last saw it remembers, inside a floor ring of radius DisplacementTolerance; and, M2.2, a
    /// ring of the same radius around every decoy of the player's kind: the safe spots. GameState shows the
    /// rings while the chair is out of place, and the ghost while it is out of place and no decoy explains it.
    ///
    /// Budget (PRD 7.4): two renderers (the ghost with its ring, and every decoy ring in one mesh) sharing one
    /// pale cyan transparent material, a color the red and yellow vision cones never use. Built once at boot
    /// under Main and kept across levels: the object count never changes (probe step 09).
    ///
    /// M4 (docs/CONTRACT_M4.md 2.4 and 3): two more renderers, each shown and hidden on its own and never by
    /// <see cref="Show"/> or <see cref="Hide"/>: the seat ghost at the home of a seat an inhabitant is about to sit
    /// on (ShowSeat), and the office chair's predicted stop point, a small ring with a cross
    /// (<see cref="ShowStopRing"/>, driven by FurnitureController). M4.1 (CONTRACT_M4 10.7): the seat ghost has its own
    /// warm amber material, so "someone will sit here" never reads as the cyan "this is where it belongs"; the stop
    /// ring keeps the cyan material. The seat ghost shows only during a sit-on-player approach, so its material counts
    /// in the budgets of PRD 7.4 only then.
    /// </summary>
    public sealed class GhostView : MonoBehaviour
    {
        private static readonly Color GhostColor = new Color(0.55f, 0.93f, 1f, 0.42f);
        // M4.1: warm amber, far from the cyan memory ghost and from the cones' yellow and red at a glance.
        private static readonly Color SeatColor = new Color(1f, 0.6f, 0.22f, 0.5f);
        private const int RingSegments = 48;
        private const float RingWidth = 0.05f;
        private const float RingHeight = 0.02f;

        /// <summary>True while the ghost (and its ring) shows.</summary>
        public bool Visible => meshRenderer != null && meshRenderer.enabled;

        /// <summary>True while the decoy rings show.</summary>
        public bool RingsVisible => ringsRenderer != null && ringsRenderer.enabled && RingCount > 0;

        /// <summary>Number of decoy rings of the current level.</summary>
        public int RingCount { get; private set; }

        public FurniturePose Pose { get; private set; }

        private Mesh mesh;
        private MeshRenderer meshRenderer;
        private Mesh ringsMesh;
        private MeshRenderer ringsRenderer;
        private Vector3 builtSize = new Vector3(-1f, -1f, -1f);

        // M4: the seat ghost (its own object, so Show and Hide never touch it) and the office chair's stop ring.
        private Mesh seatMesh;
        private MeshRenderer seatRenderer;
        private Transform seatTransform;
        private Vector3 seatBuiltSize = new Vector3(-1f, -1f, -1f);
        private Mesh stopMesh;
        private MeshRenderer stopRenderer;
        private Transform stopTransform;

        public void Init()
        {
            if (mesh != null)
            {
                return;
            }
            Material material = PrimitiveKit.UnlitTransparent(GhostColor);
            mesh = new Mesh { name = "Ghost" };
            gameObject.AddComponent<MeshFilter>().sharedMesh = mesh;
            meshRenderer = gameObject.AddComponent<MeshRenderer>();
            Setup(meshRenderer, material);

            // The decoy rings live in world space: a sibling, so they do not follow the ghost.
            var rings = new GameObject("DecoyRings");
            rings.transform.SetParent(transform.parent, false);
            rings.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            ringsMesh = new Mesh { name = "DecoyRings" };
            rings.AddComponent<MeshFilter>().sharedMesh = ringsMesh;
            ringsRenderer = rings.AddComponent<MeshRenderer>();
            Setup(ringsRenderer, material);

            // M4: built here at boot with the rest, so the object count never changes across levels (step 09).
            var seat = new GameObject("SeatGhost");
            seat.transform.SetParent(transform.parent, false);
            seatTransform = seat.transform;
            seatMesh = new Mesh { name = "SeatGhost" };
            seat.AddComponent<MeshFilter>().sharedMesh = seatMesh;
            seatRenderer = seat.AddComponent<MeshRenderer>();
            Setup(seatRenderer, PrimitiveKit.UnlitTransparent(SeatColor));

            var stop = new GameObject("StopRing");
            stop.transform.SetParent(transform.parent, false);
            stopTransform = stop.transform;
            stopMesh = new Mesh { name = "StopRing" };
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var triangles = new List<int>();
            AddRing(Vector3.zero, StopRingRadius, StopRingWidth, vertices, normals, triangles);
            // A short cross in the middle marks the exact point.
            AddBar(new Vector3(StopMarkLength, RingHeight, StopRingWidth * 0.5f), vertices, normals, triangles);
            AddBar(new Vector3(StopRingWidth * 0.5f, RingHeight, StopMarkLength), vertices, normals, triangles);
            stopMesh.SetVertices(vertices);
            stopMesh.SetNormals(normals);
            stopMesh.SetTriangles(triangles, 0);
            stopMesh.RecalculateBounds();
            stop.AddComponent<MeshFilter>().sharedMesh = stopMesh;
            stopRenderer = stop.AddComponent<MeshRenderer>();
            Setup(stopRenderer, material);
        }

        private static void Setup(MeshRenderer renderer, Material material)
        {
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            renderer.enabled = false;
        }

        /// <summary>Shows the ghost of a chair of <paramref name="size"/> at <paramref name="pose"/>.</summary>
        public void Show(FurniturePose pose, Vector3 size)
        {
            Init();
            if ((size - builtSize).sqrMagnitude > 1e-6f)
            {
                Rebuild(size);
            }
            Pose = pose;
            transform.SetPositionAndRotation(YawMath.Planar(pose.Position), Quaternion.Euler(0f, pose.Yaw, 0f));
            if (!meshRenderer.enabled)
            {
                meshRenderer.enabled = true;
            }
        }

        public void Hide()
        {
            if (meshRenderer != null && meshRenderer.enabled)
            {
                meshRenderer.enabled = false;
            }
        }

        /// <summary>The decoy rings of a new level, one per position (decoys of the player's kind).</summary>
        public void SetDecoyRings(IReadOnlyList<Vector3> centers)
        {
            Init();
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var triangles = new List<int>();
            foreach (Vector3 c in centers)
            {
                AddRing(YawMath.Planar(c), vertices, normals, triangles);
            }
            RingCount = centers.Count;
            ringsMesh.Clear();
            ringsMesh.SetVertices(vertices);
            ringsMesh.SetNormals(normals);
            ringsMesh.SetTriangles(triangles, 0);
            ringsMesh.RecalculateBounds();
            ShowRings(false);
        }

        public void ShowRings(bool show)
        {
            show &= RingCount > 0;
            if (ringsRenderer != null && ringsRenderer.enabled != show)
            {
                ringsRenderer.enabled = show;
            }
        }

        /// <summary>The chair of FurnitureKit.Chair (seat, four legs, backrest) and the tolerance ring, in one mesh.</summary>
        private void Rebuild(Vector3 size)
        {
            builtSize = size;
            BuildGhost(mesh, size, Tuning.DisplacementTolerance);
        }

        /// <summary>A ghost chair of <paramref name="size"/> inside a floor ring of <paramref name="ringRadius"/>, into <paramref name="target"/>.</summary>
        private static void BuildGhost(Mesh target, Vector3 size, float ringRadius)
        {
            float seatTop = size.y * 0.53f;
            const float seat = 0.05f;
            const float leg = 0.05f;
            const float back = 0.05f;
            float lx = size.x * 0.5f - leg * 0.5f - 0.01f;
            float lz = size.z * 0.5f - leg * 0.5f - 0.01f;
            float legHeight = seatTop - seat;
            float backHeight = size.y - seatTop;
            var boxes = new List<(Vector3 center, Vector3 size)>
            {
                (new Vector3(0f, seatTop - seat * 0.5f, 0f), new Vector3(size.x, seat, size.z)),
                (new Vector3(-lx, legHeight * 0.5f, lz), new Vector3(leg, legHeight, leg)),
                (new Vector3(lx, legHeight * 0.5f, lz), new Vector3(leg, legHeight, leg)),
                (new Vector3(-lx, legHeight * 0.5f, -lz), new Vector3(leg, legHeight, leg)),
                (new Vector3(lx, legHeight * 0.5f, -lz), new Vector3(leg, legHeight, leg)),
                (new Vector3(0f, seatTop + backHeight * 0.5f, -size.z * 0.5f + back * 0.5f), new Vector3(size.x, backHeight, back)),
            };
            Mesh box = PrimitiveKit.BoxMesh;
            Vector3[] boxVertices = box.vertices;
            Vector3[] boxNormals = box.normals;
            int[] boxTriangles = box.triangles;

            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var triangles = new List<int>();
            foreach ((Vector3 center, Vector3 s) in boxes)
            {
                int start = vertices.Count;
                for (int i = 0; i < boxVertices.Length; i++)
                {
                    vertices.Add(center + Vector3.Scale(boxVertices[i], s));
                    normals.Add(boxNormals[i]);
                }
                foreach (int t in boxTriangles)
                {
                    triangles.Add(start + t);
                }
            }
            AddRing(Vector3.zero, ringRadius, RingWidth, vertices, normals, triangles);

            target.Clear();
            target.SetVertices(vertices);
            target.SetNormals(normals);
            target.SetTriangles(triangles, 0);
            target.RecalculateBounds();
        }

        /// <summary>A flat band on the floor, centered on DisplacementTolerance (the material is double sided).</summary>
        private static void AddRing(Vector3 center, List<Vector3> vertices, List<Vector3> normals, List<int> triangles)
        {
            AddRing(center, Tuning.DisplacementTolerance, RingWidth, vertices, normals, triangles);
        }

        /// <summary>A flat band on the floor of <paramref name="radius"/> and <paramref name="width"/>.</summary>
        private static void AddRing(Vector3 center, float radius, float width, List<Vector3> vertices, List<Vector3> normals, List<int> triangles)
        {
            int ringStart = vertices.Count;
            float inner = radius - width * 0.5f;
            float outer = radius + width * 0.5f;
            for (int i = 0; i <= RingSegments; i++)
            {
                Vector3 d = YawMath.Forward(360f * i / RingSegments);
                vertices.Add(center + d * inner + Vector3.up * RingHeight);
                vertices.Add(center + d * outer + Vector3.up * RingHeight);
                normals.Add(Vector3.up);
                normals.Add(Vector3.up);
            }
            for (int i = 0; i < RingSegments; i++)
            {
                int a = ringStart + i * 2;
                triangles.Add(a);
                triangles.Add(a + 2);
                triangles.Add(a + 1);
                triangles.Add(a + 1);
                triangles.Add(a + 2);
                triangles.Add(a + 3);
            }
        }

        /// <summary>A flat floor quad of half extents <paramref name="half"/> (x and z) at height half.y, centered on the origin.</summary>
        private static void AddBar(Vector3 half, List<Vector3> vertices, List<Vector3> normals, List<int> triangles)
        {
            int a = vertices.Count;
            vertices.Add(new Vector3(-half.x, half.y, -half.z));
            vertices.Add(new Vector3(-half.x, half.y, half.z));
            vertices.Add(new Vector3(half.x, half.y, half.z));
            vertices.Add(new Vector3(half.x, half.y, -half.z));
            for (int i = 0; i < 4; i++)
            {
                normals.Add(Vector3.up);
            }
            triangles.Add(a);
            triangles.Add(a + 1);
            triangles.Add(a + 2);
            triangles.Add(a);
            triangles.Add(a + 2);
            triangles.Add(a + 3);
        }

        private void OnDestroy()
        {
            DestroyMesh(mesh);
            DestroyMesh(ringsMesh);
            DestroyMesh(seatMesh);
            DestroyMesh(stopMesh);
        }

        private static void DestroyMesh(Mesh m)
        {
            if (m == null)
            {
                return;
            }
            if (Application.isPlaying)
            {
                Destroy(m);
            }
            else
            {
                DestroyImmediate(m);
            }
        }

        // ----- M4 (docs/CONTRACT_M4.md 2.4, 3 and amendment 9.3). Independent of Show/Hide: GameState's per-step
        // Hide does not erase them. -----

        // Not in Tuning (presentation only). The stop ring is small: about the office chair's footprint.
        private const float StopRingRadius = 0.3f;
        private const float StopRingWidth = 0.04f;
        // Half length of each bar of the cross at the stop point.
        private const float StopMarkLength = 0.08f;
        // The seat ghost's size when nobody gives one and no player furniture exists: the chair.
        private static readonly Vector3 DefaultSeatSize = new Vector3(0.45f, Tuning.ChairControllerHeight, 0.45f);

        /// <summary>True while the seat ghost (and its SeatHomeTolerance ring) shows.</summary>
        public bool SeatVisible => seatRenderer != null && seatRenderer.enabled;

        /// <summary>M4.1: the seat ghost's material color (warm), and the memory ghost's (cyan), for tests.</summary>
        public Color SeatGhostColor => seatRenderer != null && seatRenderer.sharedMaterial != null ? ColorOf(seatRenderer.sharedMaterial) : SeatColor;
        public Color MemoryGhostColor => meshRenderer != null && meshRenderer.sharedMaterial != null ? ColorOf(meshRenderer.sharedMaterial) : GhostColor;

        private static Color ColorOf(Material m)
        {
            return m.HasProperty("_BaseColor") ? m.GetColor("_BaseColor") : m.color;
        }

        /// <summary>The seat home the seat ghost stands at (meaningful while <see cref="SeatVisible"/>).</summary>
        public FurniturePose SeatPose { get; private set; }

        /// <summary>True while the predicted stop ring shows.</summary>
        public bool StopRingVisible => stopRenderer != null && stopRenderer.enabled;

        /// <summary>The floor point the stop ring marks (meaningful while <see cref="StopRingVisible"/>).</summary>
        public Vector3 StopRingPosition { get; private set; }

        /// <summary>
        /// Seat ghost and ring at a seat home while a sit-on-player approach runs; null hides it. The ghost has the
        /// size of the current player furniture (the chair's without one).
        /// </summary>
        public void ShowSeat(FurniturePose? seat)
        {
            FurnitureController player = Main.Instance != null && Main.Instance.Game != null ? Main.Instance.Game.Furniture : null;
            ShowSeat(seat, player != null ? player.Size : DefaultSeatSize);
        }

        /// <summary>Seat ghost of a furniture of <paramref name="size"/>, inside a SeatHomeTolerance ring; null hides it.</summary>
        public void ShowSeat(FurniturePose? seat, Vector3 size)
        {
            Init();
            if (!seat.HasValue)
            {
                if (seatRenderer.enabled)
                {
                    seatRenderer.enabled = false;
                }
                return;
            }
            if ((size - seatBuiltSize).sqrMagnitude > 1e-6f)
            {
                seatBuiltSize = size;
                BuildGhost(seatMesh, size, Tuning.SeatHomeTolerance);
            }
            FurniturePose pose = seat.Value;
            SeatPose = pose;
            seatTransform.SetPositionAndRotation(YawMath.Planar(pose.Position), Quaternion.Euler(0f, pose.Yaw, 0f));
            if (!seatRenderer.enabled)
            {
                seatRenderer.enabled = true;
            }
        }

        /// <summary>The office chair's predicted stop ring; null hides it.</summary>
        public void ShowStopRing(Vector3? point)
        {
            Init();
            if (!point.HasValue)
            {
                if (stopRenderer.enabled)
                {
                    stopRenderer.enabled = false;
                }
                return;
            }
            StopRingPosition = YawMath.Planar(point.Value);
            stopTransform.SetPositionAndRotation(StopRingPosition, Quaternion.identity);
            if (!stopRenderer.enabled)
            {
                stopRenderer.enabled = true;
            }
        }
    }
}
