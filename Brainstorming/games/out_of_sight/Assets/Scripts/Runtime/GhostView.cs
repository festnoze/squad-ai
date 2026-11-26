using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
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
    /// <see cref="Show(FurniturePose, Vector3, float)"/> or <see cref="Hide"/>: the seat ghost at the home of a seat an inhabitant is about to sit
    /// on (ShowSeat), and the office chair's predicted stop point, a small ring with a cross
    /// (<see cref="ShowStopRing"/>, driven by FurnitureController). M4.1 (CONTRACT_M4 10.7): the seat ghost has its own
    /// warm amber material, so "someone will sit here" never reads as the cyan "this is where it belongs"; the stop
    /// ring keeps the cyan material. The seat ghost shows only during a sit-on-player approach, so its material counts
    /// in the budgets of PRD 7.4 only then.
    ///
    /// M5 (docs/CONTRACT_M5_v3.md 15.4): the memory ghost, the seat ghost, the stop ring and the decoy rings stand on
    /// the floor height at their planar position (<see cref="Floor"/>), so they sit on a platform or a ramp. M5 wave 5B: on a
    /// ramp the memory ghost and the seat ghost also lie on the slope, as the furniture visual does
    /// (<see cref="FurnitureController.RampFrame"/>); the stop ring and the decoy rings stay level. M5 5B.1 (CONTRACT_M5 3):
    /// the memory ring and the decoy rings take the tolerance of the seer that judges the furniture (tidy 0.4 m, watchful
    /// 0.5 m, default 0.75 m), passed by GameState to <see cref="Show(FurniturePose, Vector3, Transform, float)"/> and <see cref="ShowRings"/>.
    ///
    /// The memory ghost copies the real player furniture body's own meshes (the product owner's 2026-11-18 report: it
    /// used to draw a chair for every kind), <see cref="Show(FurniturePose, Vector3, Transform, float)"/>, GameState
    /// passing FurnitureController.Visual: whatever the kind, a model from the ModelCatalog or a procedural FurnitureKit
    /// body alike, skipping a carried load (LoadView). Only a bare size with no furniture behind it (direct callers,
    /// tests) still draws the chair's own boxes.
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

        /// <summary>M5 5B.1: the radius of the memory ghost's ring as last built (the seer's tolerance).</summary>
        public float RingRadius { get; private set; } = Tuning.DisplacementTolerance;

        /// <summary>M5 5B.1: the radius of the decoy rings as last built (the seer's tolerance).</summary>
        public float DecoyRingRadius { get; private set; } = Tuning.DisplacementTolerance;

        /// <summary>
        /// M5: the floor heights everything here stands on. Null (the default) reads the player furniture's
        /// <see cref="FurnitureController.Floor"/> (set by the level builder), or a flat floor without a player.
        /// </summary>
        public FloorMap Floor;

        private Mesh mesh;
        private MeshRenderer meshRenderer;
        private Mesh ringsMesh;
        private MeshRenderer ringsRenderer;
        private Vector3 builtSize = new Vector3(-1f, -1f, -1f);
        // The furniture Visual the memory ghost's mesh was last copied from (null: the chair's own boxes).
        private Transform builtVisual;
        // The decoys' planar centres of the current level, kept so the rings can be rebuilt at another radius.
        private readonly List<Vector3> decoyCenters = new List<Vector3>();

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

        /// <summary>
        /// <see cref="Show(FurniturePose, Vector3, Transform, float)"/> with no real furniture to copy: the chair's own
        /// boxes, as before the fix below (direct callers with a bare size, no FurnitureController behind it).
        /// </summary>
        public void Show(FurniturePose pose, Vector3 size, float tolerance = Tuning.DisplacementTolerance)
        {
            Show(pose, size, null, tolerance);
        }

        /// <summary>
        /// Shows the ghost of the real player furniture body under <paramref name="furnitureVisual"/> (FurnitureController.Visual:
        /// its own meshes, a model from the ModelCatalog or a procedural FurnitureKit body alike, a carried load skipped) at
        /// <paramref name="pose"/>, inside a ring of <paramref name="tolerance"/> (the seer's; DisplacementTolerance by
        /// default). Null, or a visual with no readable mesh under it, falls back to the chair's own boxes at
        /// <paramref name="size"/> (the product owner's 2026-11-18 report: the start ghost was always a chair).
        /// </summary>
        public void Show(FurniturePose pose, Vector3 size, Transform furnitureVisual, float tolerance = Tuning.DisplacementTolerance)
        {
            Init();
            if ((size - builtSize).sqrMagnitude > 1e-6f || Mathf.Abs(tolerance - RingRadius) > 1e-6f || furnitureVisual != builtVisual)
            {
                Rebuild(size, furnitureVisual, tolerance);
            }
            Pose = pose;
            PlaceOnFloor(transform, pose, size);
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
            decoyCenters.Clear();
            decoyCenters.AddRange(centers);
            RingCount = centers.Count;
            BuildDecoyRings(DecoyRingRadius);
            ShowRings(false);
        }

        /// <summary>
        /// Shows or hides the decoy rings; shown, at <paramref name="tolerance"/> (the seer's; DisplacementTolerance by
        /// default), rebuilt when it changed.
        /// </summary>
        public void ShowRings(bool show, float tolerance = Tuning.DisplacementTolerance)
        {
            // Rebuilt whenever they are asked for, even on a level without decoys, so DecoyRingRadius always names the
            // seer that judges now.
            if (show && Mathf.Abs(tolerance - DecoyRingRadius) > 1e-6f)
            {
                BuildDecoyRings(tolerance);
            }
            show &= RingCount > 0;
            if (ringsRenderer != null && ringsRenderer.enabled != show)
            {
                ringsRenderer.enabled = show;
            }
        }

        /// <summary>One ring of <paramref name="radius"/> on the floor at every decoy of the level, in one mesh.</summary>
        private void BuildDecoyRings(float radius)
        {
            DecoyRingRadius = radius;
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var triangles = new List<int>();
            foreach (Vector3 c in decoyCenters)
            {
                AddRing(OnFloor(c), radius, RingWidth, vertices, normals, triangles);
            }
            ringsMesh.Clear();
            ringsMesh.SetVertices(vertices);
            ringsMesh.SetNormals(normals);
            ringsMesh.SetTriangles(triangles, 0);
            ringsMesh.RecalculateBounds();
        }

        /// <summary>The real furniture body under <paramref name="visual"/> (or the chair's own boxes without one) and the tolerance ring, in one mesh.</summary>
        private void Rebuild(Vector3 size, Transform visual, float tolerance)
        {
            builtSize = size;
            builtVisual = visual;
            RingRadius = tolerance;
            BuildGhost(mesh, size, tolerance, visual);
        }

        /// <summary>
        /// A ghost of <paramref name="size"/> inside a floor ring of <paramref name="ringRadius"/>, into <paramref name="target"/>:
        /// the real furniture body under <paramref name="visual"/> (<see cref="AddVisualMeshes"/>) when it has at least one
        /// readable mesh, else the chair's own boxes (<see cref="AddChairBoxes"/>).
        /// </summary>
        private static void BuildGhost(Mesh target, Vector3 size, float ringRadius, Transform visual)
        {
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var triangles = new List<int>();
            if (!AddVisualMeshes(visual, vertices, normals, triangles))
            {
                AddChairBoxes(size, vertices, normals, triangles);
            }
            AddRing(Vector3.zero, ringRadius, RingWidth, vertices, normals, triangles);

            target.Clear();
            target.SetVertices(vertices);
            target.SetNormals(normals);
            target.SetTriangles(triangles, 0);
            target.RecalculateBounds();
        }

        /// <summary>
        /// The chair of FurnitureKit.Chair: the fallback shape with no real furniture to copy. Soft movers (2026-11-20): the
        /// rounded chair (SoftBodies.Chair: seat, legs, posts, rails and stretchers), as the player's chair now draws it.
        /// </summary>
        private static void AddChairBoxes(Vector3 size, List<Vector3> vertices, List<Vector3> normals, List<int> triangles)
        {
            foreach (SoftBodies.Piece piece in SoftBodies.Chair(size))
            {
                Matrix4x4 m = piece.Matrix;
                Vector3[] v = piece.Mesh.vertices;
                Vector3[] n = piece.Mesh.normals;
                int start = vertices.Count;
                for (int i = 0; i < v.Length; i++)
                {
                    vertices.Add(m.MultiplyPoint3x4(v[i]));
                    normals.Add(m.MultiplyVector(n[i]));
                }
                foreach (int t in piece.Mesh.triangles)
                {
                    triangles.Add(start + t);
                }
            }
        }

        /// <summary>
        /// The real furniture body's own meshes, in <paramref name="visual"/>'s local frame (the frame FurnitureKit and
        /// ModelKit build it in: x and z centered, y from the floor up, matching <see cref="AddChairBoxes"/>'s own frame):
        /// every MeshFilter under it with a readable mesh, skipping a carried load's own meshes (LoadView.Create parents them
        /// under a LoadView component, never the furniture body). False, nothing added, without <paramref name="visual"/> or
        /// without one readable mesh under it, so the caller falls back to the chair's own boxes.
        /// </summary>
        private static bool AddVisualMeshes(Transform visual, List<Vector3> vertices, List<Vector3> normals, List<int> triangles)
        {
            if (visual == null)
            {
                return false;
            }
            bool any = false;
            Matrix4x4 toLocal = visual.worldToLocalMatrix;
            foreach (MeshFilter filter in visual.GetComponentsInChildren<MeshFilter>(true))
            {
                Mesh source = filter.sharedMesh;
                if (source == null || !source.isReadable || filter.GetComponentInParent<LoadView>(true) != null)
                {
                    continue;
                }
                Matrix4x4 m = toLocal * filter.transform.localToWorldMatrix;
                Matrix4x4 normalMatrix = m.inverse.transpose;
                bool mirrored = m.determinant < 0f;
                int start = vertices.Count;
                Vector3[] v = source.vertices;
                Vector3[] n = source.normals;
                for (int i = 0; i < v.Length; i++)
                {
                    vertices.Add(m.MultiplyPoint3x4(v[i]));
                    normals.Add(i < n.Length ? normalMatrix.MultiplyVector(n[i]).normalized : Vector3.up);
                }
                for (int sub = 0; sub < source.subMeshCount; sub++)
                {
                    int[] t = source.GetTriangles(sub);
                    for (int i = 0; i + 2 < t.Length; i += 3)
                    {
                        triangles.Add(start + t[i]);
                        triangles.Add(start + (mirrored ? t[i + 2] : t[i + 1]));
                        triangles.Add(start + (mirrored ? t[i + 1] : t[i + 2]));
                    }
                }
                any = true;
            }
            return any;
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
            FurnitureController player = PlayerFurniture();
            ShowSeat(seat, player != null ? player.Size : DefaultSeatSize);
        }

        private static FurnitureController PlayerFurniture()
        {
            return Main.Instance != null && Main.Instance.Game != null ? Main.Instance.Game.Furniture : null;
        }

        /// <summary>M5: <see cref="Floor"/>, else the player furniture's, else a flat floor.</summary>
        private FloorMap CurrentFloor()
        {
            if (Floor != null)
            {
                return Floor;
            }
            FurnitureController player = PlayerFurniture();
            return player != null ? player.Floor : FloorMap.Flat;
        }

        /// <summary>M5: the planar point <paramref name="p"/> raised to the floor height there (its own y is ignored).</summary>
        private Vector3 OnFloor(Vector3 p)
        {
            return new Vector3(p.x, CurrentFloor().HeightAt(p.x, p.z), p.z); // MUTATION:GHOST_FLOOR
        }

        /// <summary>
        /// M5 wave 5B (the 5A.1 m16 follow-up): a ghost of a furniture of <paramref name="size"/> at <paramref name="pose"/>
        /// stands on the floor height there, and on a ramp it lies on the slope like the furniture visual: the same frame
        /// (<see cref="FurnitureController.RampFrame"/>, fitted to its footprint about its centre), so the memory ghost and the
        /// seat ghost never stand upright half buried in a ramp. Off every ramp the frame is the yaw alone, as before.
        /// </summary>
        private void PlaceOnFloor(Transform target, FurniturePose pose, Vector3 size)
        {
            Vector3 at = OnFloor(pose.Position);
            Quaternion frame = Quaternion.Euler(0f, pose.Yaw, 0f);
            float lift = 0f;
            if (FurnitureController.RampFrame(CurrentFloor(), at, pose.Yaw, size, ref frame, ref lift)) // MUTATION:GHOST_SLOPE
            {
                at += Vector3.up * lift;
            }
            target.SetPositionAndRotation(at, frame);
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
                // The seat ghost keeps the chair's own boxes (M4.1's warm amber "someone will sit here", unaffected by the fix above).
                BuildGhost(seatMesh, size, Tuning.SeatHomeTolerance, null);
            }
            FurniturePose pose = seat.Value;
            SeatPose = pose;
            PlaceOnFloor(seatTransform, pose, size);
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
            StopRingPosition = OnFloor(point.Value);
            stopTransform.SetPositionAndRotation(StopRingPosition, Quaternion.identity);
            if (!stopRenderer.enabled)
            {
                stopRenderer.enabled = true;
            }
        }
    }
}
