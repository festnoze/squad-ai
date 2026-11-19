using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Rendering;

namespace OutOfSight
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

        // ----- M5 (docs/CONTRACT_M5.md 16.12, CONTRACT_M5_v3.md 9 and 15.1) -----
        /// <summary>The door leaves, in level order (LevelDef.LeafDoors): leaf k has OpenMask bit k and area DoorAreaBase + k.</summary>
        public readonly List<DoorLeaf> Leaves = new List<DoorLeaf>();

        /// <summary>
        /// Wave 5B (CONTRACT_M5 4, 16.8 and 16.12): the robots, robot i built from <c>Def.Robots[i]</c> by
        /// <see cref="Robot.Create"/>: each carries its <see cref="RobotPath"/> (<see cref="Robot.Path"/>) and stands where
        /// that path starts (time 0) until the game steps it. Empty on a level without a robot.
        /// </summary>
        public readonly List<Robot> Robots = new List<Robot>();

        /// <summary>
        /// M7 polish (CONTRACT_M6 2.5), presentation only: wardrobe k of <see cref="LevelDef.Wardrobes"/> has its door
        /// animation here at index k (<see cref="WardrobeDoors.Attach"/>), or null for a wardrobe shown by a model
        /// visual instead of the procedural doors. GameState plays it the instant the entry or exit action starts.
        /// </summary>
        public readonly List<WardrobeDoors> Wardrobes = new List<WardrobeDoors>();

        /// <summary>
        /// Wave 5B (CONTRACT_M5 6, 16.5 and 18): the view of the player's load (the builder makes it, on
        /// the furniture's Visual), or null on a level whose player carries none. It stays after a fall: it hides its
        /// carried object and owns the clue (<see cref="LoadView.SpawnClue"/>, <see cref="LoadView.ClearClue"/>).
        /// </summary>
        public LoadView LoadView;

        /// <summary>
        /// The one seat registry the level's routines share (CONTRACT_M5_v3 15.6): inhabitant i claims as owner i. Built with
        /// the level, so a restart starts with every seat free.
        /// </summary>
        public readonly SeatRegistry Seats = new SeatRegistry();

        /// <summary>The level's floor heights (LevelDef.Floor; flat without a level).</summary>
        public FloorMap Floor => Def != null ? Def.Floor : FloorMap.Flat;

        /// <summary>Bit k set when leaf k is open (or opening). Authored open leaves are open from the start.</summary>
        public int OpenMask
        {
            get
            {
                int mask = 0;
                for (int k = 0; k < Leaves.Count; k++)
                {
                    if (Leaves[k] != null && Leaves[k].Open)
                    {
                        mask |= 1 << k;
                    }
                }
                return mask;
            }
        }

        /// <summary>The OpenMask of the level as authored (the mask the frozen station walks are planned with).</summary>
        public int AuthoredOpenMask { get; internal set; }

        /// <summary>
        /// The NavMesh areas of the frozen station walks: every area but the doorways of the leaves authored closed
        /// (RoutineFactory.AllAreas on a level without a closed leaf).
        /// </summary>
        public int StationAreaMask => AreaMaskFor(AuthoredOpenMask | HouseholdMask);

        /// <summary>The NavMesh areas a plan may use now: every area but the doorways of the closed leaves.</summary>
        public int AreaMask() => AreaMaskFor(OpenMask | HouseholdMask);

        /// <summary>
        /// M6 (docs/CONTRACT_M6.md 2.7): the leaves an inhabitant opens on its walk (openedByInhabitants): their doorways are
        /// always in <see cref="StationAreaMask"/> and <see cref="AreaMask"/>, closed or not. 0 on every level before M6.
        /// </summary>
        public int HouseholdMask => Def != null ? Def.HouseholdLeafMask() : 0;

        /// <summary>The NavMesh areas of an open-leaf mask: every area but area DoorAreaBase + k of each leaf k not in it.</summary>
        public int AreaMaskFor(int openMask)
        {
            int mask = RoutineFactory.AllAreas;
            for (int k = 0; k < Leaves.Count; k++)
            {
                if ((openMask & (1 << k)) == 0)
                {
                    mask &= ~(1 << (Tuning.DoorAreaBase + k));
                }
            }
            return mask;
        }

        /// <summary>A planner over the level's one NavMesh restricted to the areas of an open-leaf mask.</summary>
        public IAreaMaskPlanner PlannerFor(int openMask)
        {
            return new MaskedPlanner(Planner as IAreaMaskPlanner, AreaMaskFor(openMask));
        }

        /// <summary>
        /// The frozen station walks' planner as one plain planner: the level's NavMesh with the authored leaves
        /// (<see cref="StationAreaMask"/>, CONTRACT_M5_v3 15.1); <see cref="Planner"/> itself on a level without a closed
        /// leaf. The builder hands RoutineFactory <see cref="Planner"/> and <see cref="StationAreaMask"/>, which plan the same.
        /// </summary>
        public IPathPlanner StationPlanner
        {
            get
            {
                int mask = StationAreaMask;
                return mask == RoutineFactory.AllAreas || !(Planner is IAreaMaskPlanner masked) ? Planner : new MaskedPlanner(masked, mask);
            }
        }

        /// <summary>
        /// The planner of every other walk (investigate, switch-on, carry, resume): the level's NavMesh with the leaves as
        /// they are when the walk is planned (<see cref="AreaMask"/> at each call).
        /// </summary>
        public IPathPlanner InvestigatePlanner => investigatePlanner ?? (investigatePlanner = new LiveMaskPlanner(this));

        private IPathPlanner investigatePlanner;

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
            Leaves.Clear();
            Robots.Clear();
            LoadView = null;
            Seats.Clear();
        }

        /// <summary>Plans with the level's current <see cref="AreaMask"/> (the leaves opened so far).</summary>
        private sealed class LiveMaskPlanner : IAreaMaskPlanner
        {
            private readonly LevelInstance level;

            public LiveMaskPlanner(LevelInstance level)
            {
                this.level = level;
            }

            public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
            {
                return TryPlan(from, to, corners, level.AreaMask());
            }

            public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners, int areaMask)
            {
                return level.Planner is IAreaMaskPlanner masked ? masked.TryPlan(from, to, corners, areaMask) : level.Planner.TryPlan(from, to, corners);
            }
        }
    }

    /// <summary>
    /// Builds a level from its <see cref="LevelDef"/> and tears it down (PRD 6.1, 8.3, docs/CONTRACT_M2.md 6).
    /// Works in play mode and in edit mode (the level audit builds levels in an editor scene).
    ///
    /// Build order: rooms (floors, walls, doors, windows), exit, rugs, props, decoys, the player, then
    /// Physics.SyncTransforms, the runtime NavMesh, and only then the inhabitants, which plan with it.
    ///
    /// M4.2 textures: hard floors and thresholds show parquet, soft ones and rugs carpet, wall faces and caps plaster,
    /// door frames, leaves, baseboards and window frames (painted) wood; the procedural inhabitant's clothes linen.
    /// The window pane stays plain (Surface.Plain). Quads and boxes use the sized meshes (UVs in metres). Wall finishes
    /// (2026-11-19): a room's "wallFinish" (sage, limewash, grasscloth, wallpaper) replaces the plaster on the room-facing
    /// faces of its walls (and their fills); caps and outside faces stay plaster.
    ///
    /// M6 (CONTRACT_M6 2.4): the garden now shows a grass detail (Surface.Grass) instead of staying plain; the window
    /// pane keeps no texture but gets its own smoothness (<see cref="Tuning.WindowPaneSmoothness"/>).
    ///
    /// M5 (docs/CONTRACT_M5_v3.md 15.1 to 15.4 and 15.8, CONTRACT_M5.md 16.6):
    /// <list type="bullet">
    /// <item>the split level: platforms (solid walkable occluders), ramps (convex wedge MeshColliders flush at both ends)
    /// and railings (not occluders, on the Furniture layer) on every platform edge and both ramp sides, except at the ramp
    /// foot and head and where an edge lies on a wall; props, decoys, rugs, the doormat and the spawn stand at the floor
    /// height (the furniture's Floor is set before its Teleport);</item>
    /// <item>the doors: one <see cref="DoorLeaf"/> per leaf door, built after the NavMesh (no leaf is a NavMesh source);
    /// the one NavMesh gets a door area box per leaf doorway and a Not Walkable box per open leaf pose;</item>
    /// <item>the inhabitants wear their personality's model and are built through RoutineFactory (Inhabitant.Init): their
    /// station walks frozen with the authored leaves (<see cref="LevelInstance.StationAreaMask"/>), every other walk planned
    /// with the current ones, the level's shared seat registry (<see cref="LevelInstance.Seats"/>), and their eyes on the
    /// level's floor;</item>
    /// <item>the budgets: static decor renderers are combined at level build (<see cref="CombineRenderers"/>) per key
    /// (material, layer, fade plane), with the surface and the shadow mode they carry: the faces and the door frames of a
    /// shared wall per fade plane (one WallFader entry each), every part that never fades (outer wall faces, outer door
    /// frames, window strips, outer baseboards) per material across the house, floors, thresholds, platforms, ramps and
    /// railings per material. A wall line's caps become one cap under its wall (same plane, same fade). Colliders never
    /// change.</item>
    /// <item>wave 5B (CONTRACT_M5 16.11 and 17, draw calls counted as material slots): a shared wall's faces and baseboards
    /// fade with its centre plane, as its door frames and its cap, so both sides of a line combine per material; the window
    /// panes combine across the house; a bookshelf combines its parts per material (FurnitureKit).</item>
    /// <item>M7 walls pass (see-through walls, see <see cref="WallFader"/>): every wall line is one fade unit (a shared line by
    /// its centre plane, an outer line whenever the camera is outside it), its cap, its door frames and its windows with it;
    /// an outer line also gets its outside faces, with its cap; the room floors continue under every wall footprint,
    /// combined with them; the fills and the closures keep a line solid where a crossing line is faded.</item>
    /// <item>wave 5B (CONTRACT_M5 4 to 6, 16.5, 16.8 and 16.12): one <see cref="Robot"/> per <see cref="RobotDef"/>, built
    /// after the NavMesh (no collider, Default layer: never a NavMesh source, an occluder or an obstacle) and listed in
    /// <see cref="LevelInstance.Robots"/>; the player's load view (the rule is GameState's, CONTRACT_M5 18) in
    /// <see cref="LevelInstance.LoadView"/>; the cones aim at the load's top (the sample box grows by
    /// <see cref="Tuning.LoadHeight"/>); the rocking chair body shows its procedural visual (no Kenney model).</item>
    /// </list>
    /// </summary>
    public static class LevelBuilder
    {
        /// <summary>
        /// M5 (CONTRACT_M5_v3 15.8): combine the static decor renderers at level build. Off builds every part as its own
        /// renderer, exactly as M4.2 did (the budget test measures both).
        /// </summary>
        public static bool CombineRenderers = true;

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
            var batch = new Batch(CombineRenderers, root);
            FloorMap floorMap = def.Floor;
            BuildFloors(def, root, batch);
            BuildWalls(def, root, fader, batch);
            BuildSplitLevel(def, root, batch);
            BuildExit(level, def, root);
            BuildExitBlocker(def, root);
            for (int i = 0; i < def.Rugs.Count; i++)
            {
                BuildRug(level, def, def.Rugs[i], i, root);
            }
            foreach (PropDef prop in def.Props)
            {
                GameObject go = PrimitiveKit.Group(root, prop.Name, floorMap.OnFloor(prop.Position), prop.Yaw);
                go.layer = prop.Occluder ? Layers.Occluder : 0;
                // M3: a model is a visual only. The procedural parts keep exactly their colliders, collider-only.
                GameObject model = Model(level, prop.Model, "prop " + prop.Name, go.transform, prop.Size, ModelFit.Box,
                    new ModelPaint { Red = FurnitureKit.AccentOf(prop) });
                FurnitureKit.Build(prop, go.transform, go.layer, model == null, CombineRenderers);
                if (WardrobeRule.IsWardrobe(prop))
                {
                    // M7 polish: one entry per LevelDef.Wardrobes() wardrobe, in the same order, so GameState can
                    // index into it the way it already indexes its own PropDef list (null for a model visual).
                    level.Wardrobes.Add(WardrobeDoors.Attach(go.transform));
                }
            }
            Color playerColor = LevelJson.ParseColor(def.Player.Color, Color.red);
            for (int i = 0; i < def.Decoys.Count; i++)
            {
                level.Decoys.Add(BuildDecoy(level, def, def.Decoys[i], i + 1, playerColor, root));
            }
            BodyDef body = def.PlayerBody();
            level.Furniture = BuildPlayer(level, def, def.Player, body, root);
            fader.Target = level.Furniture.transform;
            fader.Furniture = level.Furniture;
            batch.Flush(root, fader);

            Physics.SyncTransforms();
            Rect interior = def.InteriorBounds();
            var bounds = new Bounds(
                new Vector3(interior.center.x, (NavBoundsBottom + NavBoundsTop) * 0.5f, interior.center.y),
                new Vector3(interior.width, NavBoundsTop - NavBoundsBottom, interior.height));
            // The level data is the cache key: a restart of the same level reuses its NavMesh. M5: the leaf doorways and
            // the open leaf poses are extra sources of that one NavMesh, never rebuilt for a door.
            NavPlanner planner = NavPlanner.Build(root, bounds, LevelJson.Serialize(def), LeafNavSources(def));
            planner.Floor = floorMap;
            if (!planner.HasData || !planner.Covers(def.Player.Position))
            {
                Debug.LogError($"[LevelBuilder] level {def.Id}: the runtime NavMesh is missing or does not reach the spawn ({planner.SourceCount} sources)");
            }
            level.Planner = planner;
            BuildLeaves(level, def, root, fader);
            level.AuthoredOpenMask = level.OpenMask;
            BuildRobots(level, def, root);
            float coneTop = ConeTargetHeight(def, body);

            for (int index = 0; index < def.Inhabitants.Count; index++)
            {
                InhabitantDef inhabitantDef = def.Inhabitants[index];
                Inhabitant inhabitant = BuildInhabitant(level, inhabitantDef, index, root);
                level.Inhabitants.Add(inhabitant);
                Vision vision = inhabitant.gameObject.AddComponent<Vision>();
                vision.Owner = inhabitant;
                level.Visions.Add(vision);
                var coneGo = new GameObject("VisionCone " + inhabitantDef.Name);
                coneGo.transform.SetParent(root, false);
                VisionConeView cone = coneGo.AddComponent<VisionConeView>();
                cone.Owner = inhabitant;
                cone.Vision = vision;
                cone.TargetHeight = coneTop;
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

        private static void BuildFloors(LevelDef def, Transform root, Batch batch)
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
                    FloorQuad(batch, root, name, center, new Vector2(room.SizeX, room.SizeZ), PrimitiveKit.Lit(color * 0.82f, 0f), floor, Surface.Carpet);
                    const float band = 0.3f;
                    if (room.SizeX > 2f * band && room.SizeZ > 2f * band)
                    {
                        FloorQuad(batch, root, name + " Field", center + Vector3.up * 0.002f, new Vector2(room.SizeX - 2f * band, room.SizeZ - 2f * band),
                            PrimitiveKit.Lit(color, 0f), floor, Surface.Carpet);
                    }
                }
                else if (room.IsTile)
                {
                    // M7 (CONTRACT_M7 1.2): kitchen and bathroom floors, visual only (still a hard, non silent floor).
                    // LitSurface, not Lit: Tile's own fixed finish (TextureLibrary.FinishOf) must never be silently
                    // overridden by an unrelated Lit(color, ...) call for the same colour (PrimitiveKit.Lit caches by
                    // colour alone, and this floor's colour is also a common wall colour at its own, different,
                    // smoothness: CONTRACT_M6 2.4's reasoning for Grass, Lacquer, Metal, Plastic, Foliage and Soil).
                    FloorQuad(batch, root, name, center, new Vector2(room.SizeX, room.SizeZ), PrimitiveKit.LitSurface(color, Surface.Tile), floor, Surface.Tile);
                }
                else
                {
                    FloorQuad(batch, root, name, center, new Vector2(room.SizeX, room.SizeZ), PrimitiveKit.Lit(color, 0.35f), floor, Surface.Parquet);
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
            // M6 (CONTRACT_M6 2.4): the garden shows a grass detail (Grass001) instead of staying plain.
            PrimitiveKit.Part(root, "Garden", PrimitiveKit.QuadMesh, mid + new Vector3(0f, -0.02f, 0f), Quaternion.Euler(90f, 0f, 0f),
                new Vector3(size, size, 1f), PrimitiveKit.LitSurface(Outside, Surface.Grass), floor, Surface.Grass)
                .GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            // One slab under everything, indoors and out, so the chair never falls through a door. It is on
            // the Default layer: no NavMesh source, so no island of NavMesh appears outside the house.
            var ground = new GameObject("GroundCollider") { layer = 0 };
            ground.transform.SetParent(root, false);
            var box = ground.AddComponent<BoxCollider>();
            box.center = mid + new Vector3(0f, -0.1f, 0f);
            box.size = new Vector3(size, 0.2f, size);
        }

        private static void FloorQuad(Batch batch, Transform parent, string name, Vector3 center, Vector2 size, Material material, int layer,
            Surface surface)
        {
            batch.Add(parent, name, PrimitiveKit.QuadMeshSized(size), center, Quaternion.Euler(90f, 0f, 0f), new Vector3(size.x, size.y, 1f),
                material, layer, surface, ShadowCastingMode.Off, FloorScope, FloorName);
        }

        // The combine scopes and names of the static decor (CONTRACT_M5_v3 15.8). The key is (material, layer, fade plane), with
        // the surface and the shadow mode a renderer carries: parts that never fade combine across the house, parts that
        // fade combine per fade plane (one WallFader entry each).
        private const string FloorScope = "Floor";
        private const string FloorName = "Floor";
        private const string FaceScope = "Face";
        private const string DoorFrameScope = "DoorFrame";
        private const string TrimScope = "Trim";
        private const string BaseboardScope = "Baseboards";
        private const string PaneScope = "WindowPane";

        private static string RoomName(RoomDef room, int index) => room.Id ?? "Room " + (index + 1);

        // ----- M5: the split level (docs/CONTRACT_M5_v3.md 2 and 15.4, CONTRACT_M5.md 16.6) -----

        /// <summary>
        /// Platforms (solid boxes on the Occluder layer: walkable, NavMesh sources, their sides hide what is below their
        /// edge), ramps (convex wedge MeshColliders from y = 0 at the foot to the platform top at the head, occluders too) and
        /// railings (box colliders on the Furniture layer: they stop the player and the NavMesh, never a sight ray).
        /// </summary>
        private static void BuildSplitLevel(LevelDef def, Transform root, Batch batch)
        {
            if (def.Floor.IsFlat)
            {
                return;
            }
            int occluder = Layers.Occluder;
            var railings = new List<Railing>();
            for (int i = 0; i < def.Platforms.Count; i++)
            {
                PlatformDef p = def.Platforms[i];
                if (p == null || p.SizeX <= 0f || p.SizeZ <= 0f || p.Height <= 0f)
                {
                    continue;
                }
                var size = new Vector3(p.SizeX, p.Height, p.SizeZ);
                var go = new GameObject("Platform " + (p.Name ?? (i + 1).ToString())) { layer = occluder };
                go.transform.SetParent(root, false);
                go.transform.localPosition = new Vector3(p.X, p.Height * 0.5f, p.Z);
                go.AddComponent<BoxCollider>().size = size;
                batch.Add(go.transform, "Visual", PrimitiveKit.BoxMeshSized(size), Vector3.zero, Quaternion.identity, size,
                    RaisedMaterial(def, p.Color, p.X, p.Z), occluder, Surface.Parquet, ShadowCastingMode.On, RaisedScope, RaisedScope);
                PlatformRailings(def, p, railings);
            }
            for (int i = 0; i < def.Ramps.Count; i++)
            {
                RampDef r = def.Ramps[i];
                PlatformDef p = FloorMap.PlatformOf(def, r);
                if (r == null || p == null || p.Height <= 0f || r.Length <= 0f || r.Width <= 0f)
                {
                    continue;
                }
                Mesh wedge = PrimitiveKit.WedgeMesh(r.Width, r.Length, p.Height);
                var go = new GameObject("Ramp " + (i + 1)) { layer = occluder };
                go.transform.SetParent(root, false);
                go.transform.SetLocalPositionAndRotation(new Vector3(r.X, 0f, r.Z), Quaternion.Euler(0f, r.Yaw, 0f));
                var collider = go.AddComponent<MeshCollider>();
                collider.sharedMesh = wedge;
                collider.convex = true;
                batch.Add(go.transform, "Visual", wedge, Vector3.zero, Quaternion.identity, Vector3.one,
                    RaisedMaterial(def, p.Color, p.X, p.Z), occluder, Surface.Parquet, ShadowCastingMode.On, RaisedScope, RaisedScope);
                RampRailings(def, r, p.Height, railings);
            }
            Material trim = PrimitiveKit.Lit(Trim, 0.3f);
            int furniture = Layers.Furniture;
            for (int k = 0; k < railings.Count; k++)
            {
                Railing rail = railings[k];
                var go = new GameObject("Railing " + (k + 1)) { layer = furniture };
                go.transform.SetParent(root, false);
                go.transform.SetLocalPositionAndRotation(rail.Center, rail.Rotation);
                go.AddComponent<BoxCollider>().size = rail.Size;
                batch.Add(go.transform, "Visual", PrimitiveKit.BoxMeshSized(rail.Size), Vector3.zero, Quaternion.identity, rail.Size, trim, 0,
                    Surface.Wood, ShadowCastingMode.On, RailingScope, RailingScope);
            }
        }

        private const string RaisedScope = "Raised";
        private const string RailingScope = "Railing";

        /// <summary>One railing box: its centre, rotation and size (along the edge on local z or x as built).</summary>
        private struct Railing
        {
            public Vector3 Center;
            public Quaternion Rotation;
            public Vector3 Size;
        }

        /// <summary>The material of a platform or ramp: its own colour, else the floor colour of the room it stands in.</summary>
        private static Material RaisedMaterial(LevelDef def, string color, float x, float z)
        {
            RoomDef room = def.RoomAt(new Vector3(x, 0f, z));
            Color floorColor = LevelJson.ParseColor(room?.FloorColor, Color.gray);
            return PrimitiveKit.Lit(LevelJson.ParseColor(color, floorColor), 0.35f);
        }

        /// <summary>True when a line (x = c for a z-running line, z = c for an x-running line) is a wall face of the room.</summary>
        private static bool OnWall(RoomDef room, bool alongX, float c)
        {
            const float eps = 1e-3f;
            if (room == null)
            {
                return false;
            }
            return alongX
                ? Mathf.Abs(c - room.MinZ) < eps || Mathf.Abs(c - room.MaxZ) < eps
                : Mathf.Abs(c - room.MinX) < eps || Mathf.Abs(c - room.MaxX) < eps;
        }

        /// <summary>
        /// A railing on every edge of a platform, standing on its top just inside the edge, except an edge on a wall of its
        /// room and the span where a ramp head meets the edge.
        /// </summary>
        private static void PlatformRailings(LevelDef def, PlatformDef p, List<Railing> railings)
        {
            float t = Tuning.RailingThickness;
            float height = Tuning.RailingHeight;
            RoomDef room = def.RoomAt(new Vector3(p.X, 0f, p.Z));
            float minX = p.X - p.SizeX * 0.5f;
            float maxX = p.X + p.SizeX * 0.5f;
            float minZ = p.Z - p.SizeZ * 0.5f;
            float maxZ = p.Z + p.SizeZ * 0.5f;
            // (runs along x, the edge line, the span along it, the inward direction across it)
            var edges = new (bool alongX, float line, float from, float to, float inward)[]
            {
                (true, minZ, minX, maxX, 1f), (true, maxZ, minX, maxX, -1f), (false, minX, minZ, maxZ, 1f), (false, maxX, minZ, maxZ, -1f),
            };
            foreach ((bool alongX, float line, float from, float to, float inward) in edges)
            {
                if (OnWall(room, alongX, line))
                {
                    continue;
                }
                var spans = new List<Vector2> { new Vector2(from, to) };
                foreach (RampDef r in def.Ramps)
                {
                    if (r == null || r.Platform != p.Name)
                    {
                        continue;
                    }
                    Vector3 head = new Vector3(r.X, 0f, r.Z) + YawMath.Forward(r.Yaw) * (r.Length * 0.5f);
                    bool headAlongX = Mathf.Abs(YawMath.Forward(r.Yaw).z) > 0.5f; // uphill along z: the head edge runs along x
                    float headLine = headAlongX ? head.z : head.x;
                    if (headAlongX != alongX || Mathf.Abs(headLine - line) > 1e-3f)
                    {
                        continue;
                    }
                    float c = headAlongX ? head.x : head.z;
                    spans = Subtract(spans, c - r.Width * 0.5f, c + r.Width * 0.5f);
                }
                foreach (Vector2 span in spans)
                {
                    float length = span.y - span.x;
                    if (length < 1e-3f)
                    {
                        continue;
                    }
                    float mid = (span.x + span.y) * 0.5f;
                    float across = line + inward * t * 0.5f;
                    railings.Add(new Railing
                    {
                        Center = alongX ? new Vector3(mid, p.Height + height * 0.5f, across) : new Vector3(across, p.Height + height * 0.5f, mid),
                        Rotation = Quaternion.identity,
                        Size = alongX ? new Vector3(length, height, t) : new Vector3(t, height, length),
                    });
                }
            }
        }

        /// <summary>The spans less one interval.</summary>
        private static List<Vector2> Subtract(List<Vector2> spans, float from, float to)
        {
            var result = new List<Vector2>();
            foreach (Vector2 s in spans)
            {
                if (to <= s.x || from >= s.y)
                {
                    result.Add(s);
                    continue;
                }
                if (from > s.x)
                {
                    result.Add(new Vector2(s.x, from));
                }
                if (to < s.y)
                {
                    result.Add(new Vector2(to, s.y));
                }
            }
            return result;
        }

        /// <summary>
        /// A railing along both sides of a ramp, standing on the slope just inside its side, from the foot to the head (the
        /// foot and the head stay open), except a side on a wall of its room.
        /// </summary>
        private static void RampRailings(LevelDef def, RampDef r, float headHeight, List<Railing> railings)
        {
            float t = Tuning.RailingThickness;
            float height = Tuning.RailingHeight;
            RoomDef room = def.RoomAt(new Vector3(r.X, 0f, r.Z));
            Quaternion yaw = Quaternion.Euler(0f, r.Yaw, 0f);
            float slopeRad = Mathf.Atan2(headHeight, r.Length);
            float slope = slopeRad * Mathf.Rad2Deg;
            Quaternion pitch = Quaternion.Euler(-slope, 0f, 0f);
            Vector3 up = pitch * Vector3.up;
            // The rail's ends are perpendicular to the slope: it starts up the slope where its top end stands over the foot,
            // so nothing overhangs the floor in front of the ramp (an overhang there would cut the NavMesh at the foot).
            float full = Mathf.Sqrt(r.Length * r.Length + headHeight * headHeight);
            float start = Mathf.Min(full * 0.5f, height * Mathf.Tan(slopeRad));
            float run = full - start;
            float mid = (start + full) * 0.5f;
            Vector3 right = YawMath.Rotate(Vector3.right, r.Yaw);
            bool sideAlongX = Mathf.Abs(right.z) > 0.5f; // the side line runs along x when the ramp's right points along z
            foreach (float side in new[] { -1f, 1f })
            {
                Vector3 sideLine = new Vector3(r.X, 0f, r.Z) + right * (side * r.Width * 0.5f);
                if (OnWall(room, sideAlongX, sideAlongX ? sideLine.z : sideLine.x))
                {
                    continue;
                }
                // The middle of the rail's bottom edge on the slope, mid along it, then half its height up from the slope.
                var onSlope = new Vector3(side * (r.Width * 0.5f - t * 0.5f), mid * Mathf.Sin(slopeRad), -r.Length * 0.5f + mid * Mathf.Cos(slopeRad));
                Vector3 local = onSlope + up * (height * 0.5f);
                railings.Add(new Railing
                {
                    Center = new Vector3(r.X, 0f, r.Z) + yaw * local,
                    Rotation = yaw * pitch,
                    Size = new Vector3(t, height, run),
                });
            }
        }

        // ----- M5: the door leaves (docs/CONTRACT_M5_v3.md 3, 15.1 and 15.2) -----

        /// <summary>One <see cref="DoorLeaf"/> per leaf door, in level order, after the NavMesh: no leaf is a NavMesh source.</summary>
        private static void BuildLeaves(LevelInstance level, LevelDef def, Transform root, WallFader fader)
        {
            List<OpeningDef> doors = def.LeafDoors();
            if (doors.Count == 0)
            {
                return;
            }
            Material wood = PrimitiveKit.Lit(DoorWood, 0.35f);
            for (int i = 0; i < doors.Count; i++)
            {
                level.Leaves.Add(DoorLeaf.Create(def, doors[i], i, root, wood, fader));
            }
        }

        /// <summary>
        /// The NavMesh boxes of the leaves (CONTRACT_M5_v3 15.1): each leaf doorway gets the area Tuning.DoorAreaBase + its
        /// index through the wall thickness, and each leaf's open pose a Not Walkable box (no path crosses an open leaf).
        /// Null on a level without a leaf.
        /// </summary>
        public static List<NavMeshBuildSource> LeafNavSources(LevelDef def)
        {
            List<OpeningDef> doors = def.LeafDoors();
            if (doors.Count == 0)
            {
                return null;
            }
            var sources = new List<NavMeshBuildSource>();
            for (int i = 0; i < doors.Count; i++)
            {
                var geometry = new DoorGeometry(def, doors[i]);
                if (!geometry.Valid)
                {
                    continue;
                }
                geometry.DoorwayBox(out Vector3 center, out Quaternion rotation, out Vector3 size);
                sources.Add(new NavMeshBuildSource
                {
                    shape = NavMeshBuildSourceShape.ModifierBox,
                    size = size,
                    transform = Matrix4x4.TRS(center, rotation, Vector3.one),
                    area = Tuning.DoorAreaBase + i,
                });
                geometry.OpenLeafBox(out center, out rotation, out size);
                sources.Add(new NavMeshBuildSource
                {
                    shape = NavMeshBuildSourceShape.ModifierBox,
                    size = size,
                    transform = Matrix4x4.TRS(center, rotation, Vector3.one),
                    area = NotWalkableArea,
                });
            }
            return sources;
        }

        /// <summary>Unity's built-in "Not Walkable" NavMesh area.</summary>
        private const int NotWalkableArea = 1;

        // ----- M5: combining the static decor (docs/CONTRACT_M5_v3.md 15.8) -----

        /// <summary>
        /// The renderer combiner of one level build. Every static decor part goes through <see cref="Add"/>: off, it is built
        /// as its own renderer, as in M4.2; on, it joins the group of its key (material, layer, surface, shadow mode, scope
        /// and fade plane), and <see cref="Flush"/> draws each group as one renderer under the level root, registered once
        /// with the wall fader when its parts fade. Colliders never go through it.
        /// </summary>
        private sealed class Batch
        {
            private sealed class Group
            {
                public Material Material;
                public int Layer;
                public Surface Surface;
                public ShadowCastingMode Shadow;
                public string Name;
                public WallFader Fader;
                public Vector3 Point;
                public Vector3 Normal;
                public bool Outer;
                public readonly List<PrimitiveKit.CombinePart> Parts = new List<PrimitiveKit.CombinePart>();
            }

            private readonly bool enabled;
            private readonly Transform root;
            private readonly List<Group> groups = new List<Group>();
            private readonly Dictionary<string, Group> byKey = new Dictionary<string, Group>();

            public Batch(bool enabled, Transform root)
            {
                this.enabled = enabled;
                this.root = root;
            }

            /// <summary>
            /// One part: <paramref name="mesh"/> at a local pose under <paramref name="parent"/>. With a <paramref name="fader"/>
            /// it hides when the plane (<paramref name="point"/>, <paramref name="normal"/>) separates the camera from the player,
            /// or, <paramref name="outer"/> (M7 walls pass: an outer wall, <paramref name="normal"/> its inward normal), whenever
            /// the camera is on the outer side of that plane.
            /// </summary>
            public void Add(Transform parent, string name, Mesh mesh, Vector3 localPosition, Quaternion localRotation, Vector3 localScale,
                Material material, int layer, Surface surface, ShadowCastingMode shadow, string scope, string combinedName,
                WallFader fader = null, Vector3 point = default, Vector3 normal = default, bool outer = false)
            {
                if (!enabled)
                {
                    GameObject go = PrimitiveKit.Part(parent, name, mesh, localPosition, localRotation, localScale, material, layer, surface);
                    MeshRenderer renderer = go.GetComponent<MeshRenderer>();
                    renderer.shadowCastingMode = shadow;
                    if (fader != null)
                    {
                        Register(fader, renderer, point, normal, outer);
                    }
                    return;
                }
                // M7 real colours (CONTRACT_M7 5): grouped by the material the part will show (one per surface), so two
                // palette colours of one surface on one plane draw as one renderer.
                material = PrimitiveKit.ShownMaterial(material, surface, layer == Layers.Inhabitant);
                string key = Key(material, layer, surface, shadow, scope, fader != null, point, normal) + (fader != null && outer ? "|outer" : "");
                if (!byKey.TryGetValue(key, out Group group))
                {
                    group = new Group
                    {
                        Material = material,
                        Layer = layer,
                        Surface = surface,
                        Shadow = shadow,
                        Name = combinedName,
                        Fader = fader,
                        Point = point,
                        Normal = normal,
                        Outer = outer,
                    };
                    byKey[key] = group;
                    groups.Add(group);
                }
                Matrix4x4 local = root.worldToLocalMatrix * parent.localToWorldMatrix * Matrix4x4.TRS(localPosition, localRotation, localScale);
                group.Parts.Add(new PrimitiveKit.CombinePart { Mesh = mesh, Matrix = local });
            }

            private static string Key(Material material, int layer, Surface surface, ShadowCastingMode shadow, string scope, bool fades,
                Vector3 point, Vector3 normal)
            {
                string key = material.GetInstanceID() + "|" + layer + "|" + surface + "|" + shadow + "|" + scope;
                if (!fades)
                {
                    return key;
                }
                // The fade plane: its unit normal and its distance from the origin, rounded (parts of one plane give the
                // same key whatever point of the plane they name).
                Vector3 n = normal.normalized;
                System.Globalization.CultureInfo c = System.Globalization.CultureInfo.InvariantCulture;
                return key + "|fade " + n.x.ToString("0.###", c) + "," + n.y.ToString("0.###", c) + "," + n.z.ToString("0.###", c) + ","
                    + Vector3.Dot(n, point).ToString("0.###", c);
            }

            /// <summary>Draws every group as one renderer under the level root (nothing when the batch is off).</summary>
            public void Flush(Transform parent, WallFader fader)
            {
                foreach (Group g in groups)
                {
                    Mesh mesh = PrimitiveKit.CombinedMesh(g.Parts);
                    GameObject go = PrimitiveKit.Part(parent, g.Name, mesh, Vector3.zero, Quaternion.identity, Vector3.one, g.Material, g.Layer, g.Surface);
                    MeshRenderer renderer = go.GetComponent<MeshRenderer>();
                    renderer.shadowCastingMode = g.Shadow;
                    if (g.Fader != null)
                    {
                        Register(g.Fader, renderer, g.Point, g.Normal, g.Outer);
                    }
                }
                groups.Clear();
                byKey.Clear();
            }

            private static void Register(WallFader fader, Renderer renderer, Vector3 point, Vector3 normal, bool outer)
            {
                if (outer)
                {
                    fader.AddOuter(renderer, point, normal);
                }
                else
                {
                    fader.Add(renderer, point, normal);
                }
            }
        }

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

        private static void BuildWalls(LevelDef def, Transform root, WallFader fader, Batch batch)
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
                BuildWallLine(def, rooms, line, single, t, occluder, root, fader, batch);
            }
        }

        /// <summary>
        /// One wall line. Its local frame has its origin on the center line, +x along the wall and +z toward
        /// the outside: for a line that faces one way only (every M1 wall) this is exactly the M1 frame, so
        /// level 1 builds as before. A shared line takes the frame of a +x or +z wall and gets two faces.
        /// </summary>
        private static void BuildWallLine(LevelDef def, List<RoomDef> rooms, WallLine line, bool single, float t, int occluder,
            Transform root, WallFader fader, Batch batch)
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
                    Floor = BandFloor(r, out Surface floorSurface),
                    FloorSurface = floorSurface,
                    Surface = TextureLibrary.WallSurface(r.WallFinish),
                });
            }

            string name = WallName(line, rooms, single);
            GameObject wallRoot = PrimitiveKit.Group(root, name, center, yaw);
            wallRoot.layer = occluder;
            Transform wt = wallRoot.transform;
            Material cap = PrimitiveKit.Lit(LevelJson.ParseColor(rooms[line.Sides[0].Room].WallColor, Color.white) * 0.72f, 0.1f);

            var boards = new List<Board>();
            var caps = new List<PrimitiveKit.CombinePart>();
            var gaps = new List<(float from, float to, OpeningDef door, bool interior)>();
            foreach ((float from, float to, OpeningDef door, bool interior) g in line.Gaps)
            {
                float a = (g.from - mid) * sign;
                float b = (g.to - mid) * sign;
                gaps.Add((Mathf.Min(a, b), Mathf.Max(a, b), g.door, g.interior));
            }
            gaps.Sort((x, y) => x.from.CompareTo(y.from));

            // M7 walls pass (see-through walls, WallFader): the whole line is one fade unit. A shared line fades when its centre
            // plane separates the camera from the player; an outer line whenever the camera is on its outer side (its single
            // inward face is then seen from behind anyway), so its cap, its door frames and its closures never stay solid over
            // it. An outer line's inward faces need no entry: culled from outside, they are never drawn when the line fades;
            // its outside faces (with its cap) show it see-through from there.
            bool outerRule = !shared;
            Vector3 ruleNormal = shared ? normal : -normal;
            WallFader faceFader = shared ? fader : null;
            var localRuns = new List<Vector2>();
            foreach (Vector2 run in runs)
            {
                float ra = (run.x - mid) * sign;
                float rb = (run.y - mid) * sign;
                localRuns.Add(new Vector2(Mathf.Min(ra, rb), Mathf.Max(ra, rb)));
            }
            localRuns.Sort((x, y) => x.x.CompareTo(y.x));
            List<Vector2> spans = Spans(localRuns, t);
            List<Face> fills = Fills(faces, spans, t, shared);
            var surfaces = new List<Face>(faces);
            surfaces.AddRange(fills);
            void AddCap(Mesh mesh, Vector3 position, Quaternion rotation, Vector3 scale)
            {
                if (CombineRenderers)
                {
                    caps.Add(new PrimitiveKit.CombinePart { Mesh = mesh, Matrix = Matrix4x4.TRS(position, rotation, scale) });
                }
                else
                {
                    Cap(wt, mesh, position, rotation, scale, cap, occluder, fader, ruleNormal, outerRule);
                }
            }
            // M7 walls pass (see-through): an outer line also gets its outside faces, with its cap (same material, same
            // rule, no shadow): culled while it stands (the camera inside), they show its body once it fades from outside.
            System.Action<Mesh, Vector3, Quaternion, Vector3> outside = shared ? null : new System.Action<Mesh, Vector3, Quaternion, Vector3>(AddCap);

            foreach (Vector2 run in localRuns)
            {
                float runFrom = run.x;
                float runTo = run.y;
                float cursor = runFrom;
                foreach ((float from, float to, OpeningDef door, bool interior) in gaps)
                {
                    if (to <= runFrom || from >= runTo)
                    {
                        continue;
                    }
                    WallSegment(wt, cursor, from, 0f, h, t, surfaces, occluder, faceFader, wallRoot.transform, normal, boards, batch, shared, outside);
                    WallSegment(wt, from, to, door.Top, h, t, surfaces, occluder, faceFader, wallRoot.transform, normal, boards, batch, shared, outside);
                    // The face toward the outside of an outer door decides where its decorative leaf opens; a door with a
                    // real leaf (M5) has none.
                    float leafSide = interior || door.HasLeaf ? 0f : -FaceSideAt(faces, (from + to) * 0.5f);
                    DoorDecor(wt, from, to, door, t, leafSide, fader, ruleNormal, outerRule, batch, name);
                    if (interior)
                    {
                        Threshold(wt, from, to, t, rooms[line.Sides[0].Room], batch);
                    }
                    cursor = to;
                }
                WallSegment(wt, cursor, runTo, 0f, h, t, surfaces, occluder, faceFader, wallRoot.transform, normal, boards, batch, shared, outside);

                // Top cap: a thin strip that gives the dollhouse walls a readable thickness from above.
                AddCap(PrimitiveKit.QuadMeshSized(new Vector2(runTo - runFrom, t)), new Vector3((runFrom + runTo) * 0.5f, h, 0f),
                    Quaternion.Euler(90f, 0f, 0f), new Vector3(runTo - runFrom, t, 1f));
            }
            var doorways = new List<Vector2>();
            foreach ((float from, float to, OpeningDef _, bool _) in gaps)
            {
                doorways.Add(new Vector2(from, to));
            }
            Closures(wt, localRuns, spans, doorways, fills, h, t, occluder, faceFader, normal, batch, AddCap);
            // M5 (CONTRACT_M5_v3 15.8): the caps of one wall line share its plane and its material: one renderer, still
            // under the wall root and named "Cap", still fading with the wall plane (step 22b reads both). M7 walls pass: the
            // line's closures (Closures) are part of it.
            if (caps.Count > 0)
            {
                Cap(wt, PrimitiveKit.CombinedMesh(caps), Vector3.zero, Quaternion.identity, Vector3.one, cap, occluder, fader, ruleNormal, outerRule);
            }
            Baseboards(wt, boards, faceFader, batch);

            for (int w = 0; w < line.Windows.Count; w++)
            {
                (float alongWorld, OpeningDef window, RoomSide _) = line.Windows[w];
                float local = (alongWorld - mid) * sign;
                // M7 walls pass: a window of a shared line (on its outer stretch) fades with the line. On an outer line its
                // single sided strips face the room, culled from outside exactly when the line fades.
                WindowDecor(wt, local, window, t, FaceSideAt(faces, local), batch, TrimScope, faceFader, normal);
            }
        }

        /// <summary>
        /// A wall cap: M3.1 B1: EVERY cap fades with its wall, outer walls too. The camera sees through the back of an outer
        /// wall's inward face, but its cap faces up: drawn, it would lie across the frame between the camera and the chair
        /// (and mark the x-ray stencil). M7 walls pass: an outer wall's cap follows the outer rule (<paramref name="outer"/>,
        /// <paramref name="normal"/> inward). Renderer only: the collider stays.
        /// </summary>
        private static void Cap(Transform wall, Mesh mesh, Vector3 localPosition, Quaternion rotation, Vector3 localScale, Material material,
            int layer, WallFader fader, Vector3 normal, bool outer)
        {
            GameObject top = PrimitiveKit.Part(wall, "Cap", mesh, localPosition, rotation, localScale, material, layer, Surface.Plaster);
            MeshRenderer capRenderer = top.GetComponent<MeshRenderer>();
            capRenderer.shadowCastingMode = ShadowCastingMode.Off;
            if (outer)
            {
                fader.AddOuter(capRenderer, wall.position, normal);
            }
            else
            {
                fader.Add(capRenderer, wall.position, normal);
            }
        }

        /// <summary>
        /// M7 walls pass: the runs of a line (local, sorted) joined across every gap of at most one wall thickness, which is
        /// the band of a crossing wall: the stretch the line must still close once that crossing wall is faded.
        /// </summary>
        private static List<Vector2> Spans(List<Vector2> runs, float t)
        {
            var spans = new List<Vector2>();
            foreach (Vector2 r in runs)
            {
                if (spans.Count > 0 && r.x - spans[spans.Count - 1].y <= t + 1e-3f)
                {
                    Vector2 last = spans[spans.Count - 1];
                    spans[spans.Count - 1] = new Vector2(last.x, Mathf.Max(last.y, r.y));
                }
                else
                {
                    spans.Add(r);
                }
            }
            return spans;
        }

        /// <summary>
        /// M7 walls pass: the fills of a line, on each side that has a face: every stretch of a span that no face of that side
        /// covers, when it is at most one wall thickness (a crossing wall's band, a corner) or, on a shared line, whatever its
        /// length (the outer stretch of a line shared over part of its length gets its missing face, so the whole line is
        /// two faced and fades as one). Hidden inside the crossing wall while it stands, a fill keeps the line closed once that
        /// wall is faded, where the garden or the inside of the wall used to show.
        /// </summary>
        private static List<Face> Fills(List<Face> faces, List<Vector2> spans, float t, bool shared)
        {
            var fills = new List<Face>();
            foreach (float side in new[] { -1f, 1f })
            {
                var covered = new List<Vector2>();
                bool any = false;
                Face first = default;
                foreach (Face f in faces)
                {
                    if (f.Side == side)
                    {
                        covered.Add(new Vector2(f.From, f.To));
                        if (!any)
                        {
                            first = f;
                            any = true;
                        }
                    }
                }
                if (!any)
                {
                    continue;
                }
                covered = Merge(covered);
                foreach (Vector2 span in spans)
                {
                    float cursor = span.x;
                    foreach (Vector2 c in covered)
                    {
                        if (c.y <= cursor || c.x >= span.y)
                        {
                            continue;
                        }
                        AddFill(fills, cursor, c.x, first, t, shared, faces);
                        cursor = Mathf.Max(cursor, c.y);
                    }
                    AddFill(fills, cursor, span.y, first, t, shared, faces);
                }
            }
            return fills;
        }

        /// <summary>
        /// A fill over [from, to] on the side of <paramref name="like"/>, in its wall and floor materials, showing
        /// <see cref="FillSurface"/>.
        /// </summary>
        private static void AddFill(List<Face> fills, float from, float to, Face like, float t, bool shared, List<Face> faces)
        {
            if (to - from > 1e-3f && (shared || to - from <= t + 1e-3f))
            {
                like.From = from;
                like.To = to;
                like.Fill = true;
                like.Surface = FillSurface(faces, like.Side, from, to, t);
                fills.Add(like);
            }
        }

        /// <summary>
        /// Wall finishes (2026-11-19): the UV offset (metres) of a face piece over [from, to] of the wall's local x, from
        /// <paramref name="bottom"/> up, on side <paramref name="side"/>: U grows to the right of a viewer facing the piece
        /// (local +x on the -1 side, -x on the turned +1 side) and every piece of one side continues one U and one V.
        /// </summary>
        private static Vector2 WallUvOffset(float side, float from, float to, float bottom)
        {
            return new Vector2(side < 0f ? from : -to, bottom);
        }

        /// <summary>
        /// Wall finishes (2026-11-19): what a fill shows. A band fill (at most one wall thickness, inside a crossing wall or a
        /// corner) continues the finish of the face beside it on its side; a longer one is the outer stretch of a shared line,
        /// the outside of the house, so it keeps the crepi like every outside face.
        /// </summary>
        private static Surface FillSurface(List<Face> faces, float side, float from, float to, float t)
        {
            if (to - from > t + 1e-3f)
            {
                return Surface.Plaster;
            }
            foreach (Face f in faces)
            {
                if (f.Side == side && Mathf.Abs(f.To - from) < 1e-3f)
                {
                    return f.Surface;
                }
            }
            foreach (Face f in faces)
            {
                if (f.Side == side && Mathf.Abs(f.From - to) < 1e-3f)
                {
                    return f.Surface;
                }
            }
            return Surface.Plaster;
        }

        /// <summary>
        /// M7 walls pass: the floor material (and its surface) that continues under a wall of <paramref name="room"/>, as its
        /// doorway threshold shows it: the parquet, the tile, or a soft room's darker border.
        /// </summary>
        private static Material BandFloor(RoomDef room, out Surface surface)
        {
            surface = room.IsTile ? Surface.Tile : room.IsSoft ? Surface.Carpet : Surface.Parquet;
            Color color = LevelJson.ParseColor(room.FloorColor, Color.gray) * (room.IsSoft ? 0.82f : 1f);
            return room.IsTile ? PrimitiveKit.LitSurface(color, Surface.Tile) : PrimitiveKit.Lit(color, room.IsSoft ? 0f : 0.35f);
        }

        /// <summary>
        /// M7 walls pass: what keeps a line solid where a crossing line is faded, none of it a collider: its fills over the band
        /// of a crossing wall between two of its runs (full height, with its faces), a cap over that band just under the
        /// crossing wall's own (no z-fighting while both stand), and a closing quad at each end of a span, a hair inside the
        /// wall (Tuning.WallClosureInset), facing out along the line, unless a doorway opens there. The caps and the ends go
        /// with the line's cap.
        /// </summary>
        private static void Closures(Transform wall, List<Vector2> runs, List<Vector2> spans, List<Vector2> doorways, List<Face> fills, float h,
            float t, int layer, WallFader faceFader, Vector3 normal, Batch batch, System.Action<Mesh, Vector3, Quaternion, Vector3> cap)
        {
            bool Open(float at)
            {
                foreach (Vector2 d in doorways)
                {
                    if (at > d.x - 0.01f && at < d.y + 0.01f)
                    {
                        return true;
                    }
                }
                return false;
            }
            float inset = Tuning.WallClosureInset;
            for (int i = 0; i + 1 < runs.Count; i++)
            {
                float a = runs[i].y;
                float b = runs[i + 1].x;
                if (b - a <= 1e-3f || b - a > t + 1e-3f)
                {
                    continue;
                }
                cap(PrimitiveKit.QuadMeshSized(new Vector2(b - a, t)), new Vector3((a + b) * 0.5f, h - inset, 0f), Quaternion.Euler(90f, 0f, 0f),
                    new Vector3(b - a, t, 1f));
                foreach (Face f in fills)
                {
                    float from = Mathf.Max(a, f.From);
                    float to = Mathf.Min(b, f.To);
                    if (to - from <= 1e-3f)
                    {
                        continue;
                    }
                    Quaternion rotation = f.Side < 0f ? Quaternion.identity : Quaternion.Euler(0f, 180f, 0f);
                    // Wall finishes: U along the wall and V up, the pattern continued along the line (WallUvOffset).
                    batch.Add(wall, "Fill", PrimitiveKit.WallQuadMesh(new Vector2(to - from, h), WallUvOffset(f.Side, from, to, 0f)),
                        new Vector3((from + to) * 0.5f, h * 0.5f, f.Side * t * 0.5f),
                        rotation, new Vector3(to - from, h, 1f), f.Material, layer, f.Surface, ShadowCastingMode.TwoSided, FaceScope, "Face",
                        faceFader, wall.position, normal);
                }
            }
            Mesh end = PrimitiveKit.QuadMeshSized(new Vector2(t, h));
            foreach (Vector2 span in spans)
            {
                if (!Open(span.x + inset))
                {
                    cap(end, new Vector3(span.x + inset, h * 0.5f, 0f), Quaternion.Euler(0f, 90f, 0f), new Vector3(t, h, 1f));
                }
                if (!Open(span.y - inset))
                {
                    cap(end, new Vector3(span.y - inset, h * 0.5f, 0f), Quaternion.Euler(0f, -90f, 0f), new Vector3(t, h, 1f));
                }
            }
        }

        private struct Face
        {
            public float From;
            public float To;
            /// <summary>-1: the face is on the local -z side and looks toward -z (the M1 inner face); +1 the other side.</summary>
            public float Side;
            public Material Material;
            /// <summary>M7 walls pass: a fill (<see cref="Fills"/>), not a room's face: drawn as a face, no baseboard.</summary>
            public bool Fill;
            /// <summary>M7 walls pass: the floor (<see cref="BandFloor"/>) that continues under the wall on this side.</summary>
            public Material Floor;
            public Surface FloorSurface;
            /// <summary>
            /// Wall finishes (2026-11-19): what the face shows, its room's "wallFinish" (TextureLibrary.WallSurface; Plaster,
            /// the cream crepi, by default). A fill takes the finish of the face it continues.
            /// </summary>
            public Surface Surface;
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
        /// Occluder layer, and a single sided quad on each face that covers it (PRD 3.1 dollhouse walls). M7 walls pass
        /// (see-through walls): a piece standing on the floor also gets the floor under its footprint, the floor of the room on
        /// each side (<paramref name="twoSided"/>) or of its one room, combined with the room floors (no draw call): hidden
        /// while the wall stands, it keeps the floor whole under a faded wall, where the garden used to show. With
        /// <paramref name="outside"/> (an outer line) the piece's outside face goes there.
        /// </summary>
        private static void WallSegment(Transform wall, float from, float to, float bottom, float top, float thickness,
            List<Face> faces, int layer, WallFader fader, Transform frame, Vector3 normal, List<Board> boards, Batch batch, bool twoSided,
            System.Action<Mesh, Vector3, Quaternion, Vector3> outside)
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
                var faceCenter = new Vector3((vFrom + vTo) * 0.5f, (bottom + top) * 0.5f, f.Side * thickness * 0.5f);
                // A single sided quad casts shadows from both sides only when asked to. A shared line's faces fade with its
                // centre plane (wave 5B, CONTRACT_M5 17): the faces of one material on both sides of a line combine
                // (CONTRACT_M5_v3 15.8). The face plane and the centre plane separate the camera from the furniture alike: the
                // furniture never stands in the wall, and a camera within the wall sees a face's back, which is culled.
                // Wall finishes (2026-11-19): U along the wall and V up whatever the piece's proportions, continued across the
                // pieces of the line (beside and over a door), so a wallpaper's stripes stay upright and unbroken.
                batch.Add(wall, f.Fill ? "Fill" : "Face", PrimitiveKit.WallQuadMesh(new Vector2(vTo - vFrom, top - bottom),
                    WallUvOffset(f.Side, vFrom, vTo, bottom)), faceCenter, rotation,
                    new Vector3(vTo - vFrom, top - bottom, 1f), f.Material, layer, f.Surface, ShadowCastingMode.TwoSided,
                    FaceScope, "Face", fader, frame.position, normal); // MUTATION:FACE_PLANE
                if (bottom < 1e-3f && !f.Fill)
                {
                    boards.Add(new Board
                    {
                        Box = new Bounds(new Vector3((vFrom + vTo) * 0.5f, BaseboardHeight * 0.5f, f.Side * (thickness * 0.5f + BaseboardDepth * 0.5f)),
                            new Vector3(vTo - vFrom, BaseboardHeight, BaseboardDepth)),
                        Side = f.Side,
                    });
                }
                if (bottom < 1e-3f && f.Floor != null)
                {
                    // The floor under the wall: on a shared line each side's floor reaches the centre line; under an outer line
                    // the room's floor spans the whole footprint.
                    float width = twoSided ? thickness * 0.5f : thickness;
                    float z = twoSided ? f.Side * thickness * 0.25f : 0f;
                    batch.Add(wall, "WallFloor", PrimitiveKit.QuadMeshSized(new Vector2(vTo - vFrom, width)), new Vector3((vFrom + vTo) * 0.5f, 0.001f, z),
                        Quaternion.Euler(90f, 0f, 0f), new Vector3(vTo - vFrom, width, 1f), f.Floor, Layers.Floor, f.FloorSurface, ShadowCastingMode.Off,
                        FloorScope, FloorName);
                }
            }
            if (outside != null)
            {
                // An outer line's outside face, local +z: with its cap (see BuildWallLine).
                outside(PrimitiveKit.QuadMeshSized(new Vector2(to - from, top - bottom)), new Vector3((from + to) * 0.5f, (bottom + top) * 0.5f, thickness * 0.5f),
                    Quaternion.Euler(0f, 180f, 0f), new Vector3(to - from, top - bottom, 1f));
            }
        }

        /// <summary>One baseboard stretch of a wall: a box in the wall frame, the face side it stands on.</summary>
        private struct Board
        {
            public Bounds Box;
            public float Side;
        }

        /// <summary>
        /// M3 baseboards, standing on the floor against the faces, in the trim material. Decor only: no collider,
        /// layer Default, no shadow. M3.1 N5: one renderer per wall and face side (every stretch of the side in one
        /// mesh, cached by geometry). Wave 5B (CONTRACT_M5 17): combined, a shared wall's baseboards (<paramref name="fader"/>
        /// set) fade with its centre plane, as its faces, so both sides of a line are one renderer; an outer wall's never fade
        /// and combine with the other trim decor (M5, CONTRACT_M5_v3 15.8).
        /// </summary>
        private static void Baseboards(Transform wall, List<Board> boards, WallFader fader, Batch batch)
        {
            foreach (float side in new[] { -1f, 1f })
            {
                var boxes = new List<Bounds>();
                foreach (Board b in boards)
                {
                    if (b.Side == side)
                    {
                        boxes.Add(b.Box);
                    }
                }
                if (boxes.Count == 0)
                {
                    continue;
                }
                if (fader == null)
                {
                    batch.Add(wall, "Baseboards", PrimitiveKit.BoxesMesh(boxes), Vector3.zero, Quaternion.identity, Vector3.one,
                        PrimitiveKit.Lit(Trim, 0.3f), 0, Surface.Wood, ShadowCastingMode.Off, TrimScope, "Trim");
                    continue;
                }
                batch.Add(wall, "Baseboards", PrimitiveKit.BoxesMesh(boxes), Vector3.zero, Quaternion.identity, Vector3.one,
                    PrimitiveKit.Lit(Trim, 0.3f), 0, Surface.Wood, ShadowCastingMode.Off, BaseboardScope, "Baseboards", fader, wall.position,
                    wall.forward);
            }
        }

        /// <summary>
        /// Door frame decor: two posts and a head. An outer door also gets its leaf, standing open toward the
        /// outside (<paramref name="leafSide"/> is the local z side of the outside), hinged on the far post.
        /// </summary>
        private static void DoorDecor(Transform wall, float from, float to, OpeningDef door, float t, float leafSide, WallFader fader, Vector3 normal,
            bool outer, Batch batch, string wallName)
        {
            Material trim = PrimitiveKit.Lit(Trim, 0.3f);
            const float post = 0.06f;
            // The frame of a doorway goes with its wall (M7 walls pass: an outer doorway's too, with the outer rule, where it
            // used to float over a wall the camera sees through). The frames of one wall line combine (CONTRACT_M5_v3 15.8).
            string scope = DoorFrameScope;
            void Frame(string name, Vector3 center, Vector3 size)
            {
                batch.Add(wall, name, PrimitiveKit.BoxMeshSized(size), center, Quaternion.identity, size, trim, 0, Surface.Wood,
                    ShadowCastingMode.On, scope, "DoorFrame", fader, wall.position, normal, outer);
            }
            Frame("DoorPostA", new Vector3(from + post * 0.5f, door.Top * 0.5f, 0f), new Vector3(post, door.Top, t + 0.03f));
            Frame("DoorPostB", new Vector3(to - post * 0.5f, door.Top * 0.5f, 0f), new Vector3(post, door.Top, t + 0.03f));
            Frame("DoorHead", new Vector3((from + to) * 0.5f, door.Top + post * 0.5f, 0f), new Vector3(to - from, post, t + 0.03f));
            if (leafSide != 0f)
            {
                float width = to - from - 2f * post;
                var size = new Vector3(0.05f, door.Top - 0.02f, width);
                batch.Add(wall, "DoorLeaf", PrimitiveKit.BoxMeshSized(size),
                    new Vector3(to - post - 0.025f, (door.Top - 0.02f) * 0.5f, leafSide * (t * 0.5f + width * 0.5f)), Quaternion.identity, size,
                    PrimitiveKit.Lit(DoorWood, 0.35f), 0, Surface.Wood, ShadowCastingMode.On, scope, "DoorLeaf", fader, wall.position, normal, outer);
            }
        }

        /// <summary>The floor of a doorway between two rooms, so no grass shows in the wall band.</summary>
        private static void Threshold(Transform wall, float from, float to, float t, RoomDef room, Batch batch)
        {
            // M7 (CONTRACT_M7 1.2): a tiled room's doorway floor strip matches it, so no parquet seam shows in the gap.
            Surface surface = room.IsTile ? Surface.Tile : room.IsSoft ? Surface.Carpet : Surface.Parquet;
            Color color = LevelJson.ParseColor(room.FloorColor, Color.gray) * (room.IsSoft ? 0.82f : 1f);
            // LitSurface for Tile, as the room floor itself (BuildFloors): never a plain Lit(color, smoothness) call,
            // which would collide on colour alone with an unrelated wall or floor elsewhere at a different smoothness.
            Material material = room.IsTile ? PrimitiveKit.LitSurface(color, Surface.Tile) : PrimitiveKit.Lit(color, room.IsSoft ? 0f : 0.35f);
            batch.Add(wall, "Threshold", PrimitiveKit.QuadMeshSized(new Vector2(to - from, t + 0.02f)),
                new Vector3((from + to) * 0.5f, 0.001f, 0f), Quaternion.Euler(90f, 0f, 0f), new Vector3(to - from, t + 0.02f, 1f),
                material, Layers.Floor, surface, ShadowCastingMode.Off, FloorScope, FloorName);
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
        /// wall disappears and so does its window, instead of leaving a frame floating. M7 walls pass: on a shared line
        /// (<paramref name="fader"/> set) the window fades with the line's centre plane (<paramref name="normal"/>).
        /// </summary>
        private static void WindowDecor(Transform wall, float center, OpeningDef window, float t, float side, Batch batch, string scope,
            WallFader fader, Vector3 normal)
        {
            float w = window.Width;
            float hgt = window.Top - window.Bottom;
            float y = (window.Top + window.Bottom) * 0.5f;
            Quaternion rotation = side < 0f ? Quaternion.identity : Quaternion.Euler(0f, 180f, 0f);
            float z = side * (t * 0.5f + 0.004f);
            // Wave 5B (CONTRACT_M5 17): the panes of the outer walls never fade and share one material: combined, they are one
            // renderer. M6 (CONTRACT_M6 2.4): no texture (Surface.Plain), but its own smoothness (0.95).
            batch.Add(wall, "WindowPane", PrimitiveKit.QuadMeshSized(new Vector2(w, hgt)), new Vector3(center, y, z), rotation,
                new Vector3(w, hgt, 1f), PrimitiveKit.Emissive(WindowPane, WindowPaneEmission, Tuning.WindowPaneSmoothness, 0f), 0, Surface.Plain,
                ShadowCastingMode.Off, PaneScope, "WindowPane", fader, wall.position, normal);
            Material trim = PrimitiveKit.Lit(Trim, 0.3f);
            const float f = 0.08f;
            float fz = side * (t * 0.5f + 0.008f);
            void Strip(string name, Vector3 localCenter, Vector2 size)
            {
                // The strips of one window combine (CONTRACT_M5_v3 15.8).
                batch.Add(wall, name, PrimitiveKit.QuadMeshSized(size), localCenter, rotation, new Vector3(size.x, size.y, 1f), trim, 0, Surface.Wood,
                    ShadowCastingMode.Off, scope, "Trim", fader, wall.position, normal);
            }
            Strip("FrameTop", new Vector3(center, window.Top, fz), new Vector2(w + f, f));
            Strip("FrameSill", new Vector3(center, window.Bottom, fz), new Vector2(w + 2.5f * f, f * 1.3f));
            Strip("FrameL", new Vector3(center - w * 0.5f, y, fz), new Vector2(f, hgt));
            Strip("FrameR", new Vector3(center + w * 0.5f, y, fz), new Vector2(f, hgt));
            Strip("Mullion", new Vector3(center, y, fz), new Vector2(0.045f, hgt));
            Strip("Transom", new Vector3(center, y + hgt * 0.15f, fz), new Vector2(w, 0.045f));
        }

        // ----- Exit -----

        private static void BuildExit(LevelInstance level, LevelDef def, Transform root)
        {
            ZoneDef e = def.Exit;
            Color color = LevelJson.ParseColor(e.Color, Color.green);
            // M3: the doormat model, its red carpet in the exit colour. No collider, as the procedural one. M7 rug
            // image (product owner, 2026-11-18): same treatment as BuildRug/BuildRugImage, unchanged underneath it,
            // the picture sits on its own nested quad on top.
            GameObject group = PrimitiveKit.Group(root, "Doormat", new Vector3(e.X, def.FloorHeightAt(e.X, e.Z), e.Z));
            group.layer = 0;
            GameObject model = Model(level, e.Model, "exit doormat", group.transform, new Vector3(e.SizeX, DoormatHeight, e.SizeZ),
                ModelFit.Box, new ModelPaint { Red = color });
            if (model != null)
            {
                BuildRugImage(group.transform, model.transform, color, new Vector2(e.SizeX, e.SizeZ), DoormatHeight + 0.002f);
                return;
            }
            GameObject mat = PrimitiveKit.Box(group.transform, "Mat", new Vector3(0f, DoormatHeight * 0.5f, 0f),
                new Vector3(e.SizeX, DoormatHeight, e.SizeZ), PrimitiveKit.Lit(color, 0.05f), 0, false, Surface.Carpet);
            mat.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            BuildRugImage(group.transform, null, color, new Vector2(e.SizeX, e.SizeZ), DoormatHeight + 0.002f);
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

        /// <summary>
        /// A flat rug, no collider (it is a silent floor, not an obstacle): the model (or, as a fallback, a border
        /// and a field), unchanged, plus <see cref="BuildRugImage"/>'s own picture quad on top of it.
        /// </summary>
        private static void BuildRug(LevelInstance level, LevelDef def, RugDef rug, int index, Transform root)
        {
            GameObject go = PrimitiveKit.Group(root, "Rug " + (index + 1), def.Floor.OnFloor(rug.Position), rug.Yaw);
            go.layer = 0;
            Color color = LevelJson.ParseColor(rug.Color, new Color32(0x5B, 0x93, 0xD9, 0xFF));
            // M3: the rug model, its red carpet in the rug colour. A rug has no collider either way. M7 rug image
            // (product owner, 2026-11-18): BuildRugImage adds the picture, exactly once, on its own quad above
            // whatever the model (or the procedural border and field) already draws underneath it, unchanged.
            GameObject model = Model(level, rug.Model, "rug " + (index + 1), go.transform, new Vector3(rug.SizeX, RugHeight, rug.SizeZ),
                ModelFit.Box, new ModelPaint { Red = color });
            if (model != null)
            {
                BuildRugImage(go.transform, model.transform, color, new Vector2(rug.SizeX, rug.SizeZ), RugHeight + 0.002f);
                return;
            }
            GameObject border = PrimitiveKit.Box(go.transform, "Border", new Vector3(0f, RugHeight * 0.5f, 0f),
                new Vector3(rug.SizeX, RugHeight, rug.SizeZ), PrimitiveKit.Lit(color * 0.8f, 0f), 0, false, Surface.Carpet);
            border.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            const float band = 0.1f;
            if (rug.SizeX > 2f * band && rug.SizeZ > 2f * band)
            {
                var fieldSize = new Vector2(rug.SizeX - 2f * band, rug.SizeZ - 2f * band);
                GameObject field = PrimitiveKit.Part(go.transform, "Field", PrimitiveKit.QuadMeshSized(fieldSize), new Vector3(0f, RugHeight + 0.001f, 0f),
                    Quaternion.Euler(90f, 0f, 0f), new Vector3(fieldSize.x, fieldSize.y, 1f), PrimitiveKit.Lit(color, 0f), 0, Surface.Carpet);
                field.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            }
            BuildRugImage(go.transform, null, color, new Vector2(rug.SizeX, rug.SizeZ), RugHeight + 0.002f);
        }

        /// <summary>
        /// M7 rug image (product owner, 2026-11-18): the rug's or the doormat's own picture
        /// (Assets/Art/Environment/rug_modern_inset_border.png, <see cref="TextureLibrary.RugColour"/>), on a quad built
        /// at <paramref name="localHeight"/> above <paramref name="parent"/> (the rug's own unscaled group transform,
        /// never the model's: a non uniform fit scale would distort a size set directly here) and sized to
        /// <paramref name="size"/> (its SizeX, SizeZ), above everything else already drawn there. The literal
        /// <see cref="PrimitiveKit.QuadMesh"/> keeps its own unit UV (0 to 1), so <see cref="PrimitiveKit.RugDetail"/>
        /// shows the picture exactly once, stretched, never tiled. When <paramref name="modelRoot"/> is not null (the
        /// model succeeded), the quad is reparented under it keeping its world transform (its rotation here is always
        /// a right angle away from the model's own, so no shear results), so it counts as part of the model rather
        /// than a stray renderer beside it (ProbeTestsM3Models).
        /// </summary>
        private static void BuildRugImage(Transform parent, Transform modelRoot, Color color, Vector2 size, float localHeight)
        {
            GameObject image = PrimitiveKit.Part(parent, "Image", PrimitiveKit.QuadMesh, new Vector3(0f, localHeight, 0f),
                Quaternion.Euler(90f, 0f, 0f), new Vector3(size.x, size.y, 1f), PrimitiveKit.Lit(color, 0f), parent.gameObject.layer);
            image.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            if (modelRoot != null)
            {
                image.transform.SetParent(modelRoot, true);
            }
            PrimitiveKit.RugDetail(image.GetComponent<MeshRenderer>(), 0);
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
            go.transform.SetPositionAndRotation(def.Floor.OnFloor(d.Position), Quaternion.Euler(0f, d.Yaw, 0f));
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
                PrimitiveKit.Box(visual.transform, "Body", new Vector3(0f, size.y * 0.5f, 0f), size, PrimitiveKit.Lit(color, 0.35f), layer, false, Surface.Wood);
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
        private static FurnitureController BuildPlayer(LevelInstance level, LevelDef def, SpawnDef spawn, BodyDef body, Transform root)
        {
            int layer = Layers.Player;
            var go = new GameObject(PlayerObjectName(body)) { layer = layer };
            go.transform.SetParent(root, false);
            go.transform.SetPositionAndRotation(def.Floor.OnFloor(spawn.Position), Quaternion.Euler(0f, spawn.Yaw, 0f));
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
            // M5 (CONTRACT_M5_v3 15.4): the floor first, so Teleport (and every later Release) stands on it.
            furniture.Floor = def.Floor;
            furniture.Visual = visual.transform;
            furniture.Size = body.Size;
            furniture.Kind = body.Kind;
            if (body.HasLight)
            {
                furniture.Lamp = go.AddComponent<LampLight>();
            }
            furniture.SetBody(body);
            furniture.Teleport(spawn.Position, spawn.Yaw);
            level.LoadView = ApplyLoad(furniture, spawn.Load); // MUTATION:LOAD_BUILD
            return furniture;
        }

        // ----- Wave 5B: the robot and the load (CONTRACT_M5 4, 6, 16.5, 16.8 and 16.12) -----

        /// <summary>
        /// One <see cref="Robot"/> per <see cref="RobotDef"/> of the level, in its order, under the level root (torn down
        /// with it). <see cref="Robot.Create"/> builds its <see cref="RobotPath"/> and poses it where the path starts: the
        /// validator keeps every loop on floor level (never on a platform or a ramp), so time 0 stands on the floor. It is
        /// built after the NavMesh, has no collider and sits on the Default layer: no NavMesh source, no occluder, nothing an
        /// inhabitant or the furniture bumps into (16.8). The game steps it (GameState), the builder never does.
        /// </summary>
        private static void BuildRobots(LevelInstance level, LevelDef def, Transform root)
        {
            if (def.Robots == null)
            {
                return;
            }
            foreach (RobotDef robotDef in def.Robots)
            {
                if (robotDef == null)
                {
                    continue;
                }
                level.Robots.Add(Robot.Create(robotDef, root)); // MUTATION:ROBOT_BUILD
            }
        }

        /// <summary>
        /// The height above the floor the floor cones aim at (VisionConeView.TargetHeight): the top of the player's sample
        /// box, which grows by <see cref="Tuning.LoadHeight"/> with a load (16.5: a vase seen above a sofa is a furniture
        /// seen). It keeps that height after a fall, which still draws a superset of what is seen.
        /// </summary>
        public static float ConeTargetHeight(LevelDef def, BodyDef body)
        {
            float load = def.Player != null && !string.IsNullOrEmpty(def.Player.Load) ? Tuning.LoadHeight : 0f;
            return body.Size.y - Tuning.SampleInset + load; // MUTATION:LOAD_TARGET
        }

        /// <summary>
        /// The player's load view (CONTRACT_M5 6, and 18: the load rule lives in GameState, which sways this view, drops the
        /// clue and emits the crash). Returns the view, or null without a load. Called once the body is set and the
        /// furniture stands at its spawn.
        /// </summary>
        private static LoadView ApplyLoad(FurnitureController furniture, string kind)
        {
            if (furniture == null || string.IsNullOrEmpty(kind))
            {
                return null;
            }
            Transform visual = furniture.Visual != null ? furniture.Visual : furniture.transform;
            return LoadView.Create(kind, visual, furniture.Size);
        }

        /// <summary>
        /// One inhabitant, <paramref name="index"/> of the level's list (its seat owner id). M5 (CONTRACT_M5 3 and 16.12,
        /// CONTRACT_M5_v3 15.1, 15.4 and 15.6): it shows its personality's model (<see cref="Inhabitant.ModelIdOf"/>: an
        /// explicit model wins, a dog shows the dog), the rig tints its clothes; its routine comes from RoutineFactory
        /// through the full <see cref="Inhabitant.Init(InhabitantDef, LevelDef, IPathPlanner, IPathPlanner, SeatRegistry, int, int)"/>:
        /// the level's floor, its station walks frozen on the level's NavMesh with the authored leaves
        /// (<see cref="LevelInstance.StationAreaMask"/>), every other walk planned with the leaves as they are (on a level
        /// with leaves), and the level's shared seat registry. A dog's capsule is dog sized.
        /// </summary>
        private static Inhabitant BuildInhabitant(LevelInstance level, InhabitantDef def, int index, Transform root)
        {
            int layer = Layers.Inhabitant;
            var go = new GameObject(def.Name) { layer = layer };
            go.transform.SetParent(root, false);
            bool dog = PersonalityDef.ForInhabitant(def).Id == PersonalityDef.Dog;
            float capsuleRadius = dog ? Tuning.DogCapsuleRadius : Tuning.InhabitantRadius;
            float capsuleHeight = dog ? Tuning.DogCapsuleHeight : Tuning.InhabitantHeight;
            var capsule = go.AddComponent<CapsuleCollider>();
            capsule.radius = capsuleRadius;
            capsule.height = capsuleHeight;
            capsule.center = new Vector3(0f, capsuleHeight * 0.5f, 0f);
            IPathPlanner investigate = level.Leaves.Count > 0 ? level.InvestigatePlanner : null;
            void InitRoutine(Inhabitant h) => h.Init(def, level.Def, level.Planner, investigate, level.Seats, index, level.StationAreaMask);

            // M3 (docs/CONTRACT_M3.md 5): the rigged model, its eyes at Tuning.EyeHeight, driven by InhabitantRig.
            // It replaces the whole procedural body; the capsule collider above stays.
            string modelId = Inhabitant.ModelIdOf(def);
            if (!string.IsNullOrEmpty(modelId))
            {
                var modelVisual = new GameObject("Visual") { layer = layer };
                modelVisual.transform.SetParent(go.transform, false);
                var box = new Vector3(2f * Tuning.InhabitantRadius, Tuning.InhabitantHeight, 2f * Tuning.InhabitantRadius);
                GameObject model = Model(level, modelId, "inhabitant " + def.Name, modelVisual.transform, box, ModelFit.Uniform, default);
                if (model != null)
                {
                    var rigged = go.AddComponent<Inhabitant>();
                    rigged.Visual = modelVisual.transform;
                    InitRoutine(rigged);
                    InhabitantRig rig = null;
                    try
                    {
                        rig = InhabitantRig.Attach(rigged, model, ModelCatalog.Lookup(modelId));
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
                    Debug.LogWarning($"[LevelBuilder] no rig for {def.Name}: procedural body instead of {modelId}");
                    level.ModelVisuals.Remove(model);
                    level.ModelFallbacks.Add($"inhabitant {def.Name} ({modelId}): no rig");
                    InhabitantRig leftover = go.GetComponent<InhabitantRig>();
                    if (leftover != null)
                    {
                        Object.DestroyImmediate(leftover);
                    }
                    Object.DestroyImmediate(rigged);
                }
                Object.DestroyImmediate(modelVisual);
            }

            // M5: without a body colour, a personality's procedural body wears its clothes tint (default: blue, as before).
            Color bodyColor = LevelJson.ParseColor(def.BodyColor, Inhabitant.TintOf(def) ?? Color.blue);
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
                Vector3.one, body, layer, Surface.Linen);

            Transform armL = PrimitiveKit.Group(v, "ArmL", new Vector3(-0.27f, 1.3f, 0f)).transform;
            Transform armR = PrimitiveKit.Group(v, "ArmR", new Vector3(0.27f, 1.3f, 0f)).transform;
            Mesh armMesh = PrimitiveKit.CapsuleMesh(0.06f, 0.62f, 8, 2);
            PrimitiveKit.Part(armL, "Mesh", armMesh, new Vector3(0f, -0.62f, 0f), Quaternion.identity, Vector3.one, body, layer, Surface.Linen);
            PrimitiveKit.Part(armR, "Mesh", armMesh, new Vector3(0f, -0.62f, 0f), Quaternion.identity, Vector3.one, body, layer, Surface.Linen);

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
            InitRoutine(inhabitant);
            return inhabitant;
        }
    }
}
