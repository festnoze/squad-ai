using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Rendering;

namespace Meuble
{
    /// <summary>Everything one built level owns. Nothing about a level lives anywhere else.</summary>
    public sealed class LevelInstance
    {
        public LevelDef Def;
        public GameObject Root;
        public FurnitureController Furniture;
        public readonly List<Inhabitant> Inhabitants = new List<Inhabitant>();
        public readonly List<Vision> Visions = new List<Vision>();
        public readonly List<VisionConeView> Cones = new List<VisionConeView>();

        // ----- M2 (docs/CONTRACT_M2.md 5) -----
        /// <summary>The decoys, in level order: decoy i of the data has Id i + 1.</summary>
        public readonly List<Decoy> Decoys = new List<Decoy>();
        /// <summary>The NavMesh planner of this level (StraightPlanner once torn down).</summary>
        public IPathPlanner Planner = StraightPlanner.Instance;

        public bool IsSilentAt(Vector3 p) => Def != null && Def.IsSilentFloor(p);

        // ----- M3 (docs/CONTRACT_M3.md 1 and 9) -----
        /// <summary>The root of every model visual this level instantiated (ModelKit), in build order.</summary>
        public readonly List<GameObject> ModelVisuals = new List<GameObject>();
        /// <summary>Every element whose data names a model but got the procedural visual: "what (id)". The probe fails on any.</summary>
        public readonly List<string> ModelFallbacks = new List<string>();

        public void Clear()
        {
            Root = null;
            Furniture = null;
            Inhabitants.Clear();
            Visions.Clear();
            Cones.Clear();
            Decoys.Clear();
            ModelVisuals.Clear();
            ModelFallbacks.Clear();
        }
    }

    /// <summary>
    /// Builds a level from its <see cref="LevelDef"/> and tears it down (PRD 6.1, 8.3, docs/CONTRACT_M2.md 6).
    /// Works in play mode and in edit mode (the level audit builds levels in an editor scene).
    ///
    /// Build order: rooms (floors, walls, doors, windows), exit, rugs, props, decoys, the player, then
    /// Physics.SyncTransforms, the runtime NavMesh, and only then the inhabitants, which plan with it.
    /// </summary>
    public static class LevelBuilder
    {
        private static readonly Color Outside = new Color32(0x5E, 0x7D, 0x4A, 0xFF);
        private static readonly Color WindowPane = new Color32(0xBF, 0xE3, 0xF5, 0xFF);
        private static readonly Color Trim = new Color32(0xF7, 0xF4, 0xEE, 0xFF);
        private static readonly Color DoorWood = new Color32(0x8C, 0x6A, 0x4A, 0xFF);
        // A wood already used by the books and the table: never red, and no new material.
        private static readonly Color DecoyWood = new Color32(0x8C, 0x5A, 0x36, 0xFF);

        private const float ExitBlockerDistance = Tuning.ExitBlockerDistance;
        private const float ExitBlockerHeight = Tuning.ExitBlockerHeight;
        private const float RugHeight = Tuning.RugHeight;
        private const float NavBoundsBottom = Tuning.NavBoundsBottom;
        private const float NavBoundsTop = Tuning.NavBoundsTop;
        private const float GardenSize = Tuning.GardenSize;
        // Thickness of the floor colliders that feed the NavMesh (top face at y = 0).
        private const float FloorSlab = 0.1f;

        // M3 look (docs/CONTRACT_M3.md 6): built here, tuned by the look pass. Wanted in Tuning (integrator) as
        // BaseboardHeight, BaseboardDepth and WindowPaneEmission; private until they land there.
        // A baseboard is a strip along the bottom of every wall face, in the trim colour (no new material).
        private const float BaseboardHeight = Tuning.BaseboardHeight;
        // As deep as the door posts stand proud of the wall face (0.015 m), so the two meet flush.
        private const float BaseboardDepth = Tuning.BaseboardDepth;
        // The pane colour times this (sRGB) is above 1 in linear: only the window feeds the bloom.
        private const float WindowPaneEmission = Tuning.WindowPaneEmission;

        public static LevelInstance Build(LevelDef def)
        {
            // Runtime NavMesh data survives scene reloads between PlayMode tests: start from none.
            NavMesh.RemoveAllNavMeshData();
            Physics.IgnoreLayerCollision(Layers.Player, Layers.Furniture, false);

            var level = new LevelInstance { Def = def, Root = new GameObject("Level " + def.Id) };
            Transform root = level.Root.transform;
            var fader = level.Root.AddComponent<WallFader>();
            BuildFloors(def, root);
            BuildWalls(def, root, fader);
            BuildExit(level, def, root);
            BuildExitBlocker(def, root);
            for (int i = 0; i < def.Rugs.Count; i++)
            {
                BuildRug(level, def.Rugs[i], i, root);
            }
            foreach (PropDef prop in def.Props)
            {
                GameObject go = PrimitiveKit.Group(root, prop.Name, prop.Position, prop.Yaw);
                go.layer = prop.Occluder ? Layers.Occluder : 0;
                // M3: a model is a visual only. The procedural parts keep exactly their colliders, collider-only.
                GameObject model = Model(level, prop.Model, "prop " + prop.Name, go.transform, prop.Size, ModelFit.Box,
                    new ModelPaint { Red = FurnitureKit.AccentOf(prop) });
                FurnitureKit.Build(prop, go.transform, go.layer, model == null);
            }
            Color playerColor = LevelJson.ParseColor(def.Player.Color, Color.red);
            for (int i = 0; i < def.Decoys.Count; i++)
            {
                level.Decoys.Add(BuildDecoy(level, def, def.Decoys[i], i + 1, playerColor, root));
            }
            BodyDef body = def.PlayerBody();
            level.Furniture = BuildPlayer(level, def.Player, body, root);
            fader.Target = level.Furniture.transform;

            Physics.SyncTransforms();
            Rect interior = def.InteriorBounds();
            var bounds = new Bounds(
                new Vector3(interior.center.x, (NavBoundsBottom + NavBoundsTop) * 0.5f, interior.center.y),
                new Vector3(interior.width, NavBoundsTop - NavBoundsBottom, interior.height));
            // The level data is the cache key: a restart of the same level reuses its NavMesh.
            NavPlanner planner = NavPlanner.Build(root, bounds, LevelJson.Serialize(def));
            if (!planner.HasData || !planner.Covers(def.Player.Position))
            {
                Debug.LogError($"[LevelBuilder] level {def.Id}: the runtime NavMesh is missing or does not reach the spawn ({planner.SourceCount} sources)");
            }
            level.Planner = planner;

            foreach (InhabitantDef inhabitantDef in def.Inhabitants)
            {
                Inhabitant inhabitant = BuildInhabitant(level, inhabitantDef, root, level.Planner);
                level.Inhabitants.Add(inhabitant);
                Vision vision = inhabitant.gameObject.AddComponent<Vision>();
                vision.Owner = inhabitant;
                level.Visions.Add(vision);
                var coneGo = new GameObject("VisionCone " + inhabitantDef.Name);
                coneGo.transform.SetParent(root, false);
                VisionConeView cone = coneGo.AddComponent<VisionConeView>();
                cone.Owner = inhabitant;
                cone.Vision = vision;
                cone.TargetHeight = body.Size.y - Tuning.SampleInset;
                cone.Init();
                level.Cones.Add(cone);
            }
            Physics.SyncTransforms();
            return level;
        }

        /// <summary>PRD 8.4: DestroyImmediate on the level objects, then every registry is cleared.</summary>
        public static void Teardown(LevelInstance level)
        {
            if (level == null)
            {
                return;
            }
            if (level.Root != null)
            {
                Object.DestroyImmediate(level.Root);
            }
            (level.Planner as NavPlanner)?.Remove();
            level.Planner = StraightPlanner.Instance;
            level.Clear();
            Physics.SyncTransforms();
        }

        // ----- Floors -----

        private static void BuildFloors(LevelDef def, Transform root)
        {
            int floor = Layers.Floor;
            List<RoomDef> rooms = def.AllRooms();
            bool single = rooms.Count == 1;
            for (int i = 0; i < rooms.Count; i++)
            {
                RoomDef room = rooms[i];
                Color color = LevelJson.ParseColor(room.FloorColor, Color.gray);
                string name = single ? "Floor" : "Floor " + RoomName(room, i);
                var center = new Vector3(room.X, 0f, room.Z);
                if (room.IsSoft)
                {
                    // Carpet look: matte, a darker border and the field inset by a band.
                    FloorQuad(root, name, center, new Vector2(room.SizeX, room.SizeZ), PrimitiveKit.Lit(color * 0.82f, 0f), floor);
                    const float band = 0.3f;
                    if (room.SizeX > 2f * band && room.SizeZ > 2f * band)
                    {
                        FloorQuad(root, name + " Field", center + Vector3.up * 0.002f, new Vector2(room.SizeX - 2f * band, room.SizeZ - 2f * band),
                            PrimitiveKit.Lit(color, 0f), floor);
                    }
                }
                else
                {
                    FloorQuad(root, name, center, new Vector2(room.SizeX, room.SizeZ), PrimitiveKit.Lit(color, 0.35f), floor);
                }
                // The room floor feeds the NavMesh (the ground slab does not).
                var slab = new GameObject(name + " Collider") { layer = floor };
                slab.transform.SetParent(root, false);
                var collider = slab.AddComponent<BoxCollider>();
                collider.center = center + new Vector3(0f, -FloorSlab * 0.5f, 0f);
                collider.size = new Vector3(room.SizeX, FloorSlab, room.SizeZ);
            }
            Rect interior = def.InteriorBounds();
            float size = Mathf.Max(GardenSize, Mathf.Max(interior.width, interior.height) + 20f);
            var mid = new Vector3(interior.center.x, 0f, interior.center.y);
            PrimitiveKit.Part(root, "Garden", PrimitiveKit.QuadMesh, mid + new Vector3(0f, -0.02f, 0f), Quaternion.Euler(90f, 0f, 0f),
                new Vector3(size, size, 1f), PrimitiveKit.Lit(Outside, 0.05f), floor).GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            // One slab under everything, indoors and out, so the chair never falls through a door. It is on
            // the Default layer: no NavMesh source, so no island of NavMesh appears outside the house.
            var ground = new GameObject("GroundCollider") { layer = 0 };
            ground.transform.SetParent(root, false);
            var box = ground.AddComponent<BoxCollider>();
            box.center = mid + new Vector3(0f, -0.1f, 0f);
            box.size = new Vector3(size, 0.2f, size);
        }

        private static GameObject FloorQuad(Transform parent, string name, Vector3 center, Vector2 size, Material material, int layer)
        {
            GameObject go = PrimitiveKit.Part(parent, name, PrimitiveKit.QuadMesh, center, Quaternion.Euler(90f, 0f, 0f),
                new Vector3(size.x, size.y, 1f), material, layer);
            go.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            return go;
        }

        private static string RoomName(RoomDef room, int index) => room.Id ?? "Room " + (index + 1);

        // ----- Walls -----

        /// <summary>All room sides that stand on one wall center line, and the openings cut in it.</summary>
        private sealed class WallLine
        {
            public bool AlongX;
            public float Line;
            public readonly List<RoomSide> Sides = new List<RoomSide>();
            public readonly List<(float from, float to, OpeningDef door, bool interior)> Gaps = new List<(float, float, OpeningDef, bool)>();
            public readonly List<(float along, OpeningDef window, RoomSide side)> Windows = new List<(float, OpeningDef, RoomSide)>();

            public bool HasBothFacings
            {
                get
                {
                    bool plus = false, minus = false;
                    foreach (RoomSide s in Sides)
                    {
                        plus |= s.Outward > 0f;
                        minus |= s.Outward < 0f;
                    }
                    return plus && minus;
                }
            }
        }

        private static WallLine LineOf(List<WallLine> lines, RoomSide side)
        {
            foreach (WallLine l in lines)
            {
                if (l.AlongX == side.AlongX && Mathf.Abs(l.Line - side.Line) < 1e-3f)
                {
                    return l;
                }
            }
            return null;
        }

        private static void BuildWalls(LevelDef def, Transform root, WallFader fader)
        {
            List<RoomDef> rooms = def.AllRooms();
            bool single = rooms.Count == 1;
            float t = def.WallThickness();
            int occluder = Layers.Occluder;

            var lines = new List<WallLine>();
            foreach (RoomSide side in def.Sides())
            {
                WallLine line = LineOf(lines, side);
                if (line == null)
                {
                    line = new WallLine { AlongX = side.AlongX, Line = side.Line };
                    lines.Add(line);
                }
                line.Sides.Add(side);
            }
            foreach (OpeningDef door in def.Doors)
            {
                List<RoomSide> on = def.SidesOf(door, out float along);
                WallLine line = on.Count > 0 ? LineOf(lines, on[0]) : null;
                if (line == null)
                {
                    Debug.LogError($"[LevelBuilder] level {def.Id}: a door does not lie on a wall");
                    continue;
                }
                line.Gaps.Add((along - door.Width * 0.5f, along + door.Width * 0.5f, door, on.Count > 1));
            }
            foreach (OpeningDef window in def.Windows)
            {
                List<RoomSide> on = def.SidesOf(window, out float along);
                WallLine line = on.Count > 0 ? LineOf(lines, on[0]) : null;
                if (line != null)
                {
                    line.Windows.Add((along, window, on[0]));
                }
            }

            foreach (WallLine line in lines)
            {
                BuildWallLine(def, rooms, line, single, t, occluder, root, fader);
            }
        }

        /// <summary>
        /// One wall line. Its local frame has its origin on the center line, +x along the wall and +z toward
        /// the outside: for a line that faces one way only (every M1 wall) this is exactly the M1 frame, so
        /// level 1 builds as before. A shared line takes the frame of a +x or +z wall and gets two faces.
        /// </summary>
        private static void BuildWallLine(LevelDef def, List<RoomDef> rooms, WallLine line, bool single, float t, int occluder,
            Transform root, WallFader fader)
        {
            bool shared = line.HasBothFacings;
            float outward = shared ? 1f : line.Sides[0].Outward;
            float yaw = line.AlongX ? (outward > 0f ? 0f : 180f) : (outward > 0f ? 90f : -90f);
            Vector3 along = Quaternion.Euler(0f, yaw, 0f) * Vector3.right;
            Vector3 normal = Quaternion.Euler(0f, yaw, 0f) * Vector3.forward;

            // Solid extent: x walls run past the interior by one thickness at each end to close the corners,
            // z walls cover the interior span only (the M1 layout).
            var runs = new List<Vector2>();
            float h = 0f;
            foreach (RoomSide s in line.Sides)
            {
                runs.Add(line.AlongX ? new Vector2(s.From, s.To) : new Vector2(s.From - t, s.To + t));
                h = Mathf.Max(h, rooms[s.Room].WallHeight);
            }
            runs = Merge(runs);
            float worldMin = runs[0].x;
            float worldMax = runs[runs.Count - 1].y;
            float mid = (worldMin + worldMax) * 0.5f;
            Vector3 center = line.AlongX ? new Vector3(mid, 0f, line.Line) : new Vector3(line.Line, 0f, mid);
            float sign = Vector3.Dot(line.AlongX ? Vector3.right : Vector3.forward, along); // world along axis to local x

            // Faces in local coordinates: one per room side, on that room's side of the wall.
            var faces = new List<Face>();
            foreach (RoomSide s in line.Sides)
            {
                float a = (s.From - mid) * sign;
                float b = (s.To - mid) * sign;
                RoomDef r = rooms[s.Room];
                // The face looks into its room: local -z when the room lies opposite the local outside.
                float facing = Mathf.Sign(Vector3.Dot(normal, (line.AlongX ? Vector3.forward : Vector3.right) * -s.Outward));
                faces.Add(new Face
                {
                    From = Mathf.Min(a, b),
                    To = Mathf.Max(a, b),
                    Side = facing,
                    Material = PrimitiveKit.Lit(LevelJson.ParseColor(r.WallColor, Color.white), 0.1f),
                    Shared = shared && OverlapsOtherFacing(line, s),
                });
            }

            string name = WallName(line, rooms, single);
            GameObject wallRoot = PrimitiveKit.Group(root, name, center, yaw);
            wallRoot.layer = occluder;
            Transform wt = wallRoot.transform;
            Material cap = PrimitiveKit.Lit(LevelJson.ParseColor(rooms[line.Sides[0].Room].WallColor, Color.white) * 0.72f, 0.1f);

            var boards = new List<Board>();
            var gaps = new List<(float from, float to, OpeningDef door, bool interior)>();
            foreach ((float from, float to, OpeningDef door, bool interior) g in line.Gaps)
            {
                float a = (g.from - mid) * sign;
                float b = (g.to - mid) * sign;
                gaps.Add((Mathf.Min(a, b), Mathf.Max(a, b), g.door, g.interior));
            }
            gaps.Sort((x, y) => x.from.CompareTo(y.from));

            foreach (Vector2 run in runs)
            {
                float ra = (run.x - mid) * sign;
                float rb = (run.y - mid) * sign;
                float runFrom = Mathf.Min(ra, rb);
                float runTo = Mathf.Max(ra, rb);
                float cursor = runFrom;
                foreach ((float from, float to, OpeningDef door, bool interior) in gaps)
                {
                    if (to <= runFrom || from >= runTo)
                    {
                        continue;
                    }
                    WallSegment(wt, cursor, from, 0f, h, t, faces, occluder, fader, wallRoot.transform, normal, boards);
                    WallSegment(wt, from, to, door.Top, h, t, faces, occluder, fader, wallRoot.transform, normal, boards);
                    // The face toward the outside of an outer door decides where its leaf opens.
                    float leafSide = interior ? 0f : -FaceSideAt(faces, (from + to) * 0.5f);
                    DoorDecor(wt, from, to, door, t, leafSide, interior && shared ? fader : null, normal);
                    if (interior)
                    {
                        Threshold(wt, from, to, t, rooms[line.Sides[0].Room]);
                    }
                    cursor = to;
                }
                WallSegment(wt, cursor, runTo, 0f, h, t, faces, occluder, fader, wallRoot.transform, normal, boards);

                // Top cap: a thin strip that gives the dollhouse walls a readable thickness from above.
                GameObject top = PrimitiveKit.Part(wt, "Cap", PrimitiveKit.QuadMesh, new Vector3((runFrom + runTo) * 0.5f, h, 0f),
                    Quaternion.Euler(90f, 0f, 0f), new Vector3(runTo - runFrom, t, 1f), cap, occluder);
                MeshRenderer capRenderer = top.GetComponent<MeshRenderer>();
                capRenderer.shadowCastingMode = ShadowCastingMode.Off;
                // M3.1 B1: EVERY cap fades with the wall plane, outer walls too. The camera sees through the back of
                // an outer wall's inward face, but its cap faces up: drawn, it would lie across the frame between the
                // camera and the chair (and mark the x-ray stencil). Renderer only: the collider stays.
                fader.Add(capRenderer, wt.position, normal);
            }
            Baseboards(wt, boards, t, fader);

            foreach ((float alongWorld, OpeningDef window, RoomSide side) in line.Windows)
            {
                float local = (alongWorld - mid) * sign;
                WindowDecor(wt, local, window, t, FaceSideAt(faces, local));
            }
        }

        private struct Face
        {
            public float From;
            public float To;
            /// <summary>-1: the face is on the local -z side and looks toward -z (the M1 inner face); +1 the other side.</summary>
            public float Side;
            public Material Material;
            /// <summary>On a shared stretch: hidden by the <see cref="WallFader"/> when it stands between camera and player.</summary>
            public bool Shared;
        }

        private static bool OverlapsOtherFacing(WallLine line, RoomSide side)
        {
            foreach (RoomSide o in line.Sides)
            {
                if (o.Outward != side.Outward && Mathf.Min(o.To, side.To) - Mathf.Max(o.From, side.From) > 1e-3f)
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>The side of the face that covers a local abscissa (-1 when none does, the M1 inner side).</summary>
        private static float FaceSideAt(List<Face> faces, float local)
        {
            foreach (Face f in faces)
            {
                if (local >= f.From - 1e-3f && local <= f.To + 1e-3f)
                {
                    return f.Side;
                }
            }
            return -1f;
        }

        private static string WallName(WallLine line, List<RoomDef> rooms, bool single)
        {
            if (single)
            {
                return "Wall " + line.Sides[0].Side;
            }
            var parts = new List<string>();
            foreach (RoomSide s in line.Sides)
            {
                parts.Add(RoomName(rooms[s.Room], s.Room) + " " + s.Side);
            }
            return "Wall " + string.Join(" / ", parts);
        }

        private static List<Vector2> Merge(List<Vector2> spans)
        {
            spans.Sort((a, b) => a.x.CompareTo(b.x));
            var merged = new List<Vector2>();
            foreach (Vector2 s in spans)
            {
                if (merged.Count > 0 && s.x <= merged[merged.Count - 1].y + 1e-3f)
                {
                    Vector2 last = merged[merged.Count - 1];
                    merged[merged.Count - 1] = new Vector2(last.x, Mathf.Max(last.y, s.y));
                }
                else
                {
                    merged.Add(s);
                }
            }
            return merged;
        }

        /// <summary>
        /// One solid piece of wall between two local abscissas and two heights: a box collider on the
        /// Occluder layer, and a single sided quad on each face that covers it (PRD 3.1 dollhouse walls).
        /// </summary>
        private static void WallSegment(Transform wall, float from, float to, float bottom, float top, float thickness,
            List<Face> faces, int layer, WallFader fader, Transform frame, Vector3 normal, List<Board> boards)
        {
            if (to - from < 1e-3f || top - bottom < 1e-3f)
            {
                return;
            }
            var seg = new GameObject("Segment") { layer = layer };
            seg.transform.SetParent(wall, false);
            seg.transform.localPosition = new Vector3((from + to) * 0.5f, (bottom + top) * 0.5f, 0f);
            var box = seg.AddComponent<BoxCollider>();
            box.size = new Vector3(to - from, top - bottom, thickness);
            // Each visible face covers only its room's interior span; a corner overlap is hidden by the other wall.
            foreach (Face f in faces)
            {
                float vFrom = Mathf.Max(from, f.From);
                float vTo = Mathf.Min(to, f.To);
                if (vTo - vFrom <= 1e-3f)
                {
                    continue;
                }
                Quaternion rotation = f.Side < 0f ? Quaternion.identity : Quaternion.Euler(0f, 180f, 0f);
                GameObject face = PrimitiveKit.Part(wall, "Face", PrimitiveKit.QuadMesh,
                    new Vector3((vFrom + vTo) * 0.5f, (bottom + top) * 0.5f, f.Side * thickness * 0.5f), rotation,
                    new Vector3(vTo - vFrom, top - bottom, 1f), f.Material, layer);
                MeshRenderer renderer = face.GetComponent<MeshRenderer>();
                // A single sided quad casts shadows from both sides only when asked to.
                renderer.shadowCastingMode = ShadowCastingMode.TwoSided;
                Vector3 faceNormal = frame.TransformDirection(new Vector3(0f, 0f, f.Side));
                if (f.Shared)
                {
                    // The face plane, its normal pointing into the room the face looks at.
                    fader.Add(renderer, face.transform.position, faceNormal);
                }
                if (bottom < 1e-3f)
                {
                    boards.Add(new Board
                    {
                        Box = new Bounds(new Vector3((vFrom + vTo) * 0.5f, BaseboardHeight * 0.5f, f.Side * (thickness * 0.5f + BaseboardDepth * 0.5f)),
                            new Vector3(vTo - vFrom, BaseboardHeight, BaseboardDepth)),
                        Side = f.Side,
                        Shared = f.Shared,
                    });
                }
            }
        }

        /// <summary>One baseboard stretch of a wall: a box in the wall frame, the face side it stands on.</summary>
        private struct Board
        {
            public Bounds Box;
            public float Side;
            public bool Shared;
        }

        /// <summary>
        /// M3 baseboards, standing on the floor against the faces, in the trim material. Decor only: no collider,
        /// layer Default, no shadow. M3.1 N5: one renderer per wall and face side (every stretch of the side in one
        /// mesh, cached by geometry); the side of a shared wall fades with its face plane.
        /// </summary>
        private static void Baseboards(Transform wall, List<Board> boards, float thickness, WallFader fader)
        {
            foreach (float side in new[] { -1f, 1f })
            {
                foreach (bool shared in new[] { false, true })
                {
                    var boxes = new List<Bounds>();
                    foreach (Board b in boards)
                    {
                        if (b.Side == side && b.Shared == shared)
                        {
                            boxes.Add(b.Box);
                        }
                    }
                    if (boxes.Count == 0)
                    {
                        continue;
                    }
                    GameObject go = PrimitiveKit.Part(wall, "Baseboards", PrimitiveKit.BoxesMesh(boxes), Vector3.zero, Quaternion.identity,
                        Vector3.one, PrimitiveKit.Lit(Trim, 0.3f), 0);
                    MeshRenderer renderer = go.GetComponent<MeshRenderer>();
                    renderer.shadowCastingMode = ShadowCastingMode.Off;
                    if (shared)
                    {
                        fader.Add(renderer, wall.TransformPoint(new Vector3(0f, 0f, side * thickness * 0.5f)),
                            wall.TransformDirection(new Vector3(0f, 0f, side)));
                    }
                }
            }
        }

        /// <summary>
        /// Door frame decor: two posts and a head. An outer door also gets its leaf, standing open toward the
        /// outside (<paramref name="leafSide"/> is the local z side of the outside), hinged on the far post.
        /// </summary>
        private static void DoorDecor(Transform wall, float from, float to, OpeningDef door, float t, float leafSide, WallFader fader, Vector3 normal)
        {
            Material trim = PrimitiveKit.Lit(Trim, 0.3f);
            const float post = 0.06f;
            var parts = new List<GameObject>
            {
                PrimitiveKit.Box(wall, "DoorPostA", new Vector3(from + post * 0.5f, door.Top * 0.5f, 0f), new Vector3(post, door.Top, t + 0.03f), trim, 0, false),
                PrimitiveKit.Box(wall, "DoorPostB", new Vector3(to - post * 0.5f, door.Top * 0.5f, 0f), new Vector3(post, door.Top, t + 0.03f), trim, 0, false),
                PrimitiveKit.Box(wall, "DoorHead", new Vector3((from + to) * 0.5f, door.Top + post * 0.5f, 0f), new Vector3(to - from, post, t + 0.03f), trim, 0, false),
            };
            if (leafSide != 0f)
            {
                float width = to - from - 2f * post;
                PrimitiveKit.Box(wall, "DoorLeaf", new Vector3(to - post - 0.025f, (door.Top - 0.02f) * 0.5f, leafSide * (t * 0.5f + width * 0.5f)),
                    new Vector3(0.05f, door.Top - 0.02f, width), PrimitiveKit.Lit(DoorWood, 0.35f), 0, false);
            }
            if (fader != null)
            {
                // The frame of a shared doorway goes with its wall: hidden when the wall center plane
                // stands between the camera and the player.
                foreach (GameObject part in parts)
                {
                    fader.Add(part.GetComponent<MeshRenderer>(), wall.position, normal);
                }
            }
        }

        /// <summary>The floor of a doorway between two rooms, so no grass shows in the wall band.</summary>
        private static void Threshold(Transform wall, float from, float to, float t, RoomDef room)
        {
            GameObject go = PrimitiveKit.Part(wall, "Threshold", PrimitiveKit.QuadMesh, new Vector3((from + to) * 0.5f, 0.001f, 0f),
                Quaternion.Euler(90f, 0f, 0f), new Vector3(to - from, t + 0.02f, 1f),
                PrimitiveKit.Lit(LevelJson.ParseColor(room.FloorColor, Color.gray) * (room.IsSoft ? 0.82f : 1f), room.IsSoft ? 0f : 0.35f), Layers.Floor);
            go.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            // The doorway floor joins the NavMesh of the two rooms.
            var slab = new GameObject("ThresholdCollider") { layer = Layers.Floor };
            slab.transform.SetParent(wall, false);
            var collider = slab.AddComponent<BoxCollider>();
            collider.center = new Vector3((from + to) * 0.5f, -FloorSlab * 0.5f, 0f);
            collider.size = new Vector3(to - from, FloorSlab, t + 0.02f);
        }

        /// <summary>
        /// A decorative window on the face side <paramref name="side"/> (-1 is the M1 inner side). The frame is
        /// made of single sided strips facing the room, like the wall itself: from outside the dollhouse the
        /// wall disappears and so does its window, instead of leaving a frame floating.
        /// </summary>
        private static void WindowDecor(Transform wall, float center, OpeningDef window, float t, float side)
        {
            float w = window.Width;
            float hgt = window.Top - window.Bottom;
            float y = (window.Top + window.Bottom) * 0.5f;
            Quaternion rotation = side < 0f ? Quaternion.identity : Quaternion.Euler(0f, 180f, 0f);
            float z = side * (t * 0.5f + 0.004f);
            GameObject pane = PrimitiveKit.Part(wall, "WindowPane", PrimitiveKit.QuadMesh, new Vector3(center, y, z), rotation,
                new Vector3(w, hgt, 1f), PrimitiveKit.Emissive(WindowPane, WindowPaneEmission), 0);
            pane.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            Material trim = PrimitiveKit.Lit(Trim, 0.3f);
            const float f = 0.08f;
            float fz = side * (t * 0.5f + 0.008f);
            Strip(wall, "FrameTop", new Vector3(center, window.Top, fz), new Vector2(w + f, f), trim, rotation);
            Strip(wall, "FrameSill", new Vector3(center, window.Bottom, fz), new Vector2(w + 2.5f * f, f * 1.3f), trim, rotation);
            Strip(wall, "FrameL", new Vector3(center - w * 0.5f, y, fz), new Vector2(f, hgt), trim, rotation);
            Strip(wall, "FrameR", new Vector3(center + w * 0.5f, y, fz), new Vector2(f, hgt), trim, rotation);
            Strip(wall, "Mullion", new Vector3(center, y, fz), new Vector2(0.045f, hgt), trim, rotation);
            Strip(wall, "Transom", new Vector3(center, y + hgt * 0.15f, fz), new Vector2(w, 0.045f), trim, rotation);
        }

        private static void Strip(Transform wall, string name, Vector3 localCenter, Vector2 size, Material material, Quaternion rotation)
        {
            GameObject strip = PrimitiveKit.Part(wall, name, PrimitiveKit.QuadMesh, localCenter, rotation,
                new Vector3(size.x, size.y, 1f), material, 0);
            strip.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
        }

        // ----- Exit -----

        private static void BuildExit(LevelInstance level, LevelDef def, Transform root)
        {
            ZoneDef e = def.Exit;
            Color color = LevelJson.ParseColor(e.Color, Color.green);
            if (!string.IsNullOrEmpty(e.Model))
            {
                // M3: the doormat model, its red carpet in the exit colour. No collider, as the procedural one.
                GameObject group = PrimitiveKit.Group(root, "Doormat", new Vector3(e.X, 0f, e.Z));
                group.layer = 0;
                if (Model(level, e.Model, "exit doormat", group.transform, new Vector3(e.SizeX, DoormatHeight, e.SizeZ), ModelFit.Box,
                        new ModelPaint { Red = color }) != null)
                {
                    return;
                }
                Object.DestroyImmediate(group);
            }
            GameObject mat = PrimitiveKit.Box(root, "Doormat", new Vector3(e.X, DoormatHeight * 0.5f, e.Z), new Vector3(e.SizeX, DoormatHeight, e.SizeZ),
                PrimitiveKit.Lit(color, 0.05f), 0, false);
            mat.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
        }

        private const float DoormatHeight = 0.012f;

        /// <summary>
        /// M3: the model visual of an element whose data names one (<paramref name="id"/>), under
        /// <paramref name="parent"/>. Null when the data names none, or when the model failed (ModelKit logged one
        /// warning): the element is then recorded as a fallback and the caller builds its procedural visual.
        /// </summary>
        private static GameObject Model(LevelInstance level, string id, string what, Transform parent, Vector3 box, ModelFit fit,
            ModelPaint paint)
        {
            if (string.IsNullOrEmpty(id))
            {
                return null;
            }
            GameObject model = ModelKit.Instantiate(id, parent, box, fit, paint);
            if (model != null)
            {
                level.ModelVisuals.Add(model);
            }
            else if (!ModelKit.Disabled)
            {
                level.ModelFallbacks.Add($"{what} ({id})");
            }
            return model;
        }

        /// <summary>
        /// An invisible U of box colliders (layer Default: it stops the player only, it is no occluder and no
        /// NavMesh source) standing <see cref="ExitBlockerDistance"/> outside the outer door nearest the exit,
        /// so a chair that crosses the doormat while seen cannot drive out into the garden.
        /// </summary>
        private static void BuildExitBlocker(LevelDef def, Transform root)
        {
            float t = def.WallThickness();
            OpeningDef best = null;
            RoomSide bestSide = default;
            float bestAlong = 0f;
            float bestDistance = float.MaxValue;
            var exit = new Vector2(def.Exit.X, def.Exit.Z);
            foreach (OpeningDef door in def.Doors)
            {
                List<RoomSide> on = def.SidesOf(door, out float along);
                if (on.Count != 1)
                {
                    continue;
                }
                RoomSide s = on[0];
                var point = s.AlongX ? new Vector2(along, s.Line) : new Vector2(s.Line, along);
                float d = (point - exit).magnitude;
                if (d < bestDistance)
                {
                    best = door;
                    bestSide = s;
                    bestAlong = along;
                    bestDistance = d;
                }
            }
            if (best == null)
            {
                return;
            }
            // Frame of the blocker: +z outward from the house, +x along the wall, origin on the outer face.
            Vector3 outwardAxis = (bestSide.AlongX ? Vector3.forward : Vector3.right) * bestSide.Outward;
            Vector3 origin = bestSide.AlongX
                ? new Vector3(bestAlong, 0f, bestSide.Line)
                : new Vector3(bestSide.Line, 0f, bestAlong);
            origin += outwardAxis * (t * 0.5f);
            var go = new GameObject("ExitBlocker") { layer = 0 };
            go.transform.SetParent(root, false);
            go.transform.SetPositionAndRotation(origin, Quaternion.LookRotation(outwardAxis, Vector3.up));
            const float panel = 0.1f;
            float span = best.Width + 2f * panel + 0.4f;
            AddBox(go, new Vector3(0f, ExitBlockerHeight * 0.5f, ExitBlockerDistance + panel * 0.5f), new Vector3(span, ExitBlockerHeight, panel));
            for (int k = -1; k <= 1; k += 2)
            {
                AddBox(go, new Vector3(k * (span - panel) * 0.5f, ExitBlockerHeight * 0.5f, (ExitBlockerDistance + panel) * 0.5f),
                    new Vector3(panel, ExitBlockerHeight, ExitBlockerDistance + panel));
            }
        }

        private static void AddBox(GameObject go, Vector3 center, Vector3 size)
        {
            var box = go.AddComponent<BoxCollider>();
            box.center = center;
            box.size = size;
        }

        // ----- Rugs and decoys -----

        /// <summary>A flat rug, no collider (it is a silent floor, not an obstacle): a border and a field.</summary>
        private static void BuildRug(LevelInstance level, RugDef rug, int index, Transform root)
        {
            GameObject go = PrimitiveKit.Group(root, "Rug " + (index + 1), rug.Position, rug.Yaw);
            go.layer = 0;
            Color color = LevelJson.ParseColor(rug.Color, new Color32(0x5B, 0x93, 0xD9, 0xFF));
            // M3: the rug model, its red carpet in the rug colour. A rug has no collider either way.
            if (Model(level, rug.Model, "rug " + (index + 1), go.transform, new Vector3(rug.SizeX, RugHeight, rug.SizeZ), ModelFit.Box,
                    new ModelPaint { Red = color }) != null)
            {
                return;
            }
            GameObject border = PrimitiveKit.Box(go.transform, "Border", new Vector3(0f, RugHeight * 0.5f, 0f),
                new Vector3(rug.SizeX, RugHeight, rug.SizeZ), PrimitiveKit.Lit(color * 0.8f, 0f), 0, false);
            border.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            const float band = 0.1f;
            if (rug.SizeX > 2f * band && rug.SizeZ > 2f * band)
            {
                GameObject field = PrimitiveKit.Part(go.transform, "Field", PrimitiveKit.QuadMesh, new Vector3(0f, RugHeight + 0.001f, 0f),
                    Quaternion.Euler(90f, 0f, 0f), new Vector3(rug.SizeX - 2f * band, rug.SizeZ - 2f * band, 1f), PrimitiveKit.Lit(color, 0f), 0);
                field.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            }
        }

        /// <summary>
        /// A decoy: the furniture of its kind (<see cref="FurnitureKit.Body"/>, M4: any body kind, sized by its kind's
        /// <see cref="BodyDef"/> unless the data gives a size) in its own color (never the player's), one box collider
        /// on the Furniture layer (it stops the chair and the NavMesh, it never hides anything).
        /// </summary>
        private static Decoy BuildDecoy(LevelInstance level, LevelDef def, DecoyDef d, int id, Color playerColor, Transform root)
        {
            int layer = Layers.Furniture;
            Vector3 size = def.DecoySize(d);
            var go = new GameObject("Decoy " + id) { layer = layer };
            go.transform.SetParent(root, false);
            go.transform.SetPositionAndRotation(d.Position, Quaternion.Euler(0f, d.Yaw, 0f));
            var box = go.AddComponent<BoxCollider>();
            box.center = new Vector3(0f, size.y * 0.5f, 0f);
            box.size = size;
            Color color = LevelJson.ParseColor(d.Color, DecoyWood);
            if (Same(color, playerColor))
            {
                color = DecoyWood;
            }
            var visual = new GameObject("Visual") { layer = layer };
            visual.transform.SetParent(go.transform, false);
            string kind = BodyKinds.Of(d.Kind);
            // M3: the decoy model keeps the decoy colour on its main material and on any red. The decoy's only
            // collider is the box on its root, so with a model nothing procedural is built. M4: with no model named,
            // a body other than the chair shows its body's model (BodyKinds.DefaultModel).
            string modelId = !string.IsNullOrEmpty(d.Model) ? d.Model : BodyKinds.DefaultModel(kind);
            GameObject model = Model(level, modelId, "decoy " + id, visual.transform, size, ModelFit.Box, new ModelPaint { Main = color, Red = color });
            if (model == null && !FurnitureKit.Body(kind, visual.transform, size, color, layer))
            {
                PrimitiveKit.Box(visual.transform, "Body", new Vector3(0f, size.y * 0.5f, 0f), size, PrimitiveKit.Lit(color, 0.35f), layer, false);
            }
            var decoy = go.AddComponent<Decoy>();
            decoy.Id = id;
            decoy.Kind = kind;
            decoy.Pose = new FurniturePose(d.Position, d.Yaw);
            decoy.Size = size;
            return decoy;
        }

        private static bool Same(Color a, Color b)
        {
            Color32 x = a;
            Color32 y = b;
            return x.r == y.r && x.g == y.g && x.b == y.b;
        }

        // ----- Actors -----

        /// <summary>The name of the player's GameObject: "Chair" for the chair (M1 to M3), "Player &lt;kind&gt;" for the M4 bodies.</summary>
        public static string PlayerObjectName(BodyDef body)
        {
            return body.Kind == BodyKinds.Chair ? "Chair" : "Player " + body.Kind;
        }

        /// <summary>
        /// The player furniture, built from its body (docs/CONTRACT_M4.md 2, amendment 9.5): <see cref="BodyDef"/> is
        /// the one size source. The controller is created at the body's radius and height, the visual is built for the
        /// body's size (the data's model, else the body's model, else the procedural visual of the kind), Size is set
        /// to the body's size, and only then <see cref="FurnitureController.SetBody"/> runs: SetBody finds a visual
        /// already built for its current Size. A lamp body gets its <see cref="LampLight"/>.
        /// </summary>
        private static FurnitureController BuildPlayer(LevelInstance level, SpawnDef spawn, BodyDef body, Transform root)
        {
            int layer = Layers.Player;
            var go = new GameObject(PlayerObjectName(body)) { layer = layer };
            go.transform.SetParent(root, false);
            go.transform.SetPositionAndRotation(spawn.Position, Quaternion.Euler(0f, spawn.Yaw, 0f));
            var cc = go.AddComponent<CharacterController>();
            cc.radius = body.Radius;
            cc.height = body.Size.y;
            cc.center = new Vector3(0f, body.Size.y * 0.5f, 0f);
            cc.skinWidth = 0.02f;
            cc.minMoveDistance = 0f;
            cc.stepOffset = 0.05f;
            cc.slopeLimit = 45f;
            var visual = new GameObject("Visual") { layer = layer };
            visual.transform.SetParent(go.transform, false);
            Color color = LevelJson.ParseColor(spawn.Color, Color.red);
            // M3: the player model in the player colour (PRD 7.2: no other object is red). The player's only
            // collider is its CharacterController, so the procedural visual (no collider) is simply not built.
            string modelId = !string.IsNullOrEmpty(spawn.Model) ? spawn.Model : BodyKinds.DefaultModel(body.Kind);
            if (Model(level, modelId, "player", visual.transform, body.Size, ModelFit.Box, new ModelPaint { Main = color, Red = color }) == null)
            {
                FurnitureKit.Body(body.Kind, visual.transform, body.Size, color, layer);
            }
            var furniture = go.AddComponent<FurnitureController>();
            furniture.Visual = visual.transform;
            furniture.Size = body.Size;
            furniture.Kind = body.Kind;
            if (body.HasLight)
            {
                furniture.Lamp = go.AddComponent<LampLight>();
            }
            furniture.SetBody(body);
            furniture.Teleport(spawn.Position, spawn.Yaw);
            return furniture;
        }

        private static Inhabitant BuildInhabitant(LevelInstance level, InhabitantDef def, Transform root, IPathPlanner planner)
        {
            int layer = Layers.Inhabitant;
            var go = new GameObject(def.Name) { layer = layer };
            go.transform.SetParent(root, false);
            var capsule = go.AddComponent<CapsuleCollider>();
            capsule.radius = Tuning.InhabitantRadius;
            capsule.height = Tuning.InhabitantHeight;
            capsule.center = new Vector3(0f, Tuning.InhabitantHeight * 0.5f, 0f);

            // M3 (docs/CONTRACT_M3.md 5): the rigged model, its eyes at Tuning.EyeHeight, driven by InhabitantRig.
            // It replaces the whole procedural body; the capsule collider above stays.
            if (!string.IsNullOrEmpty(def.Model))
            {
                var modelVisual = new GameObject("Visual") { layer = layer };
                modelVisual.transform.SetParent(go.transform, false);
                var box = new Vector3(2f * Tuning.InhabitantRadius, Tuning.InhabitantHeight, 2f * Tuning.InhabitantRadius);
                GameObject model = Model(level, def.Model, "inhabitant " + def.Name, modelVisual.transform, box, ModelFit.Uniform, default);
                if (model != null)
                {
                    var rigged = go.AddComponent<Inhabitant>();
                    rigged.Visual = modelVisual.transform;
                    rigged.Init(def, planner);
                    InhabitantRig rig = null;
                    try
                    {
                        rig = InhabitantRig.Attach(rigged, model, ModelCatalog.Lookup(def.Model));
                    }
                    catch (System.Exception e)
                    {
                        Debug.LogError($"[LevelBuilder] InhabitantRig.Attach threw for {def.Name}: {e}");
                    }
                    if (rig != null)
                    {
                        return rigged;
                    }
                    // An undriven model would stand frozen in its import pose: fall back to the procedural body
                    // (integrator fix after the M3 rig report). M3.1 S3: the gate sees it, a fallback like any other.
                    Debug.LogWarning($"[LevelBuilder] no rig for {def.Name}: procedural body instead of {def.Model}");
                    level.ModelVisuals.Remove(model);
                    level.ModelFallbacks.Add($"inhabitant {def.Name} ({def.Model}): no rig");
                    InhabitantRig leftover = go.GetComponent<InhabitantRig>();
                    if (leftover != null)
                    {
                        Object.DestroyImmediate(leftover);
                    }
                    Object.DestroyImmediate(rigged);
                }
                Object.DestroyImmediate(modelVisual);
            }

            Color bodyColor = LevelJson.ParseColor(def.BodyColor, Color.blue);
            Color skin = LevelJson.ParseColor(def.HeadColor, new Color(0.9f, 0.75f, 0.6f));
            Material body = PrimitiveKit.Lit(bodyColor, 0.2f);
            Material head = PrimitiveKit.Lit(skin, 0.3f);
            Material nose = PrimitiveKit.Lit(skin * 0.88f, 0.3f);
            // Same off white as the window trim: one material less (PRD 7.4 budget).
            Material white = PrimitiveKit.Lit(Trim, 0.3f);
            Material pupil = PrimitiveKit.Lit(new Color(0.06f, 0.06f, 0.08f), 0.7f);

            var visual = new GameObject("Visual") { layer = layer };
            visual.transform.SetParent(go.transform, false);
            Transform v = visual.transform;
            GameObject torso = PrimitiveKit.Part(v, "Body", PrimitiveKit.CapsuleMesh(0.22f, 1.45f, 12, 3), Vector3.zero, Quaternion.identity,
                Vector3.one, body, layer);

            Transform armL = PrimitiveKit.Group(v, "ArmL", new Vector3(-0.27f, 1.3f, 0f)).transform;
            Transform armR = PrimitiveKit.Group(v, "ArmR", new Vector3(0.27f, 1.3f, 0f)).transform;
            Mesh armMesh = PrimitiveKit.CapsuleMesh(0.06f, 0.62f, 8, 2);
            PrimitiveKit.Part(armL, "Mesh", armMesh, new Vector3(0f, -0.62f, 0f), Quaternion.identity, Vector3.one, body, layer);
            PrimitiveKit.Part(armR, "Mesh", armMesh, new Vector3(0f, -0.62f, 0f), Quaternion.identity, Vector3.one, body, layer);

            Transform headPivot = PrimitiveKit.Group(v, "Head", new Vector3(0f, Tuning.EyeHeight, 0f)).transform;
            PrimitiveKit.Part(headPivot, "Skull", PrimitiveKit.SphereMesh(14, 10), Vector3.zero, Quaternion.identity,
                Vector3.one * 0.3f, head, layer);
            // The nose shows where the head points (PRD 7.1).
            PrimitiveKit.Box(headPivot, "Nose", new Vector3(0f, -0.03f, 0.16f), new Vector3(0.06f, 0.07f, 0.1f), nose, layer, false);
            var eyes = new Transform[2];
            for (int i = 0; i < 2; i++)
            {
                float x = i == 0 ? -0.065f : 0.065f;
                Transform eye = PrimitiveKit.Group(headPivot, i == 0 ? "EyeL" : "EyeR", new Vector3(x, 0.035f, 0.115f)).transform;
                PrimitiveKit.Part(eye, "White", PrimitiveKit.SphereMesh(8, 6), Vector3.zero, Quaternion.identity, Vector3.one * 0.075f, white, layer);
                PrimitiveKit.Part(eye, "Pupil", PrimitiveKit.SphereMesh(8, 6), new Vector3(0f, 0f, 0.028f), Quaternion.identity,
                    Vector3.one * 0.032f, pupil, layer);
                eyes[i] = eye;
            }

            var inhabitant = go.AddComponent<Inhabitant>();
            inhabitant.Visual = v;
            inhabitant.Body = torso.transform;
            inhabitant.HeadPivot = headPivot;
            inhabitant.ArmLeft = armL;
            inhabitant.ArmRight = armR;
            inhabitant.Eyes = eyes;
            inhabitant.Init(def, planner);
            return inhabitant;
        }
    }
}
