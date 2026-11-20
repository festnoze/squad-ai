using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M7 walls pass (product owner reports of 2026-11-18 and 2026-11-19): the see-through walls, on the real Boot scene.
    /// <list type="bullet">
    /// <item>Step 70a: the floor continues under a faded shared wall: seen from above, no garden shows through its footprint
    /// (the floor used to open on the grass under a hidden wall).</item>
    /// <item>Step 70b: an outer wall fades as one (its door frames never move, M9 doors rule) whenever the camera is outside it, even with
    /// the player outside its plane too (its cap used to stay over a wall the camera saw through).</item>
    /// <item>Step 70c: a wall fades at once, comes back smoothly, and every transition ends.</item>
    /// <item>Step 70d: the inhabitants' plans between the rooms cross the walls only through their doorways, on levels 2, 12,
    /// 19 and 24 (the walls' look never touches the colliders the NavMesh is baked from).</item>
    /// <item>Step 70e: an inhabitant behind a standing wall shows only as the flat x-ray silhouette.</item>
    /// <item>Step 70f: each look of the Walls option (lowered, see-through, both, off) moves the right parts, lowered doorways
    /// stand, the opacity option applies at once; step 70g: the two Options rows.</item>
    /// <item>Step 70h: a wall fixture's glow goes with its wall line (never left hanging over a lowered wall, never opaque over a
    /// see-through one) and comes back with it.</item>
    /// </list>
    /// </summary>
    public sealed class ProbeTestsM7Walls
    {
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private GameState Game => main.Game;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            LevelBuilder.CombineRenderers = true;
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            yield return Frames(3);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            Application.logMessageReceived -= OnLog;
            yield return null;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        private static IEnumerator Frames(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return null;
            }
        }

        private IEnumerator Load(string id)
        {
            Game.LoadLevel(id);
            Assert.AreEqual(id, Game.Def.Id, "premise: the level loaded");
            for (int i = 0; i < Game.Level.Inhabitants.Count; i++)
            {
                Game.Level.Inhabitants[i].Pin(new Vector3(90f + 5f * i, 0f, 90f), 0f);
            }
            yield return Frames(3);
        }

        private WallFader Fader => Game.Level.Root.GetComponent<WallFader>();

        /// <summary>The caps of the level (one per wall line, under its wall root).</summary>
        private List<MeshRenderer> Caps()
        {
            var caps = new List<MeshRenderer>();
            foreach (MeshRenderer r in Game.Level.Root.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (r.name == "Cap")
                {
                    caps.Add(r);
                }
            }
            return caps;
        }

        /// <summary>A faded part is drawn see-through: itself ShadowsOnly (it keeps its shadow), its copy translucent.</summary>
        private static bool Cut(Renderer r) => r.shadowCastingMode == ShadowCastingMode.ShadowsOnly;

        [UnityTest]
        public IEnumerator Step70a_FadedSharedWallKeepsTheFloorUnderItsFootprint()
        {
            yield return Load("level12");
            foreach (string walls in new[] { SaveOptions.WallsLowered, SaveOptions.WallsSeeThrough, SaveOptions.WallsBoth })
            {
                SetWalls(walls, Tuning.WallOpacityDefault);
                yield return Frames(2);
                NoGardenUnderCutSharedWalls(walls);
            }
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>The Walls option, set as the Options page does (the wall fader reads it at once).</summary>
        private static void SetWalls(string walls, int opacity)
        {
            SaveOptions o = SaveStore.Options;
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty,
                Language = o.Language, Walls = walls, WallOpacity = opacity,
            });
        }

        private void NoGardenUnderCutSharedWalls(string look)
        {
            WallFader fader = Fader;
            Camera cam = main.Camera;
            Vector3 player = Game.Furniture.transform.position;
            int width = 960;
            int height = 600;
            int walls = 0;
            int samples = 0;
            int green = 0;
            foreach (MeshRenderer cap in Caps())
            {
                if (fader.IsOuter(cap))
                {
                    continue;
                }
                Transform wall = cap.transform.parent;
                foreach (BoxCollider segment in wall.GetComponentsInChildren<BoxCollider>())
                {
                    Bounds b = segment.bounds;
                    if (segment.name != "Segment" || b.min.y > 0.01f || Mathf.Max(b.size.x, b.size.z) < 0.6f)
                    {
                        continue;
                    }
                    // Above the middle of the piece, on the side away from the player: the wall's plane separates them, it fades.
                    var middle = new Vector3(b.center.x, 0.001f, b.center.z);
                    float side = Mathf.Sign(Vector3.Dot(player - wall.position, wall.forward));
                    Vector3 eye = middle - wall.forward * (side * 1.2f) + Vector3.up * 6f;
                    cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(middle - eye));
                    fader.Apply(eye);
                    Assert.IsTrue(Cut(cap), $"premise: {wall.name} is faded from {eye}");
                    Color32[] pixels = RenderPixels(cam, width, height);
                    walls++;
                    Vector3 along = b.size.x > b.size.z ? Vector3.right * b.extents.x : Vector3.forward * b.extents.z;
                    for (int i = 1; i < 10; i++)
                    {
                        Vector3 point = middle + along * (i / 5f - 1f) * 0.9f;
                        Vector3 v = cam.WorldToViewportPoint(point);
                        int px = Mathf.RoundToInt(v.x * width);
                        int py = Mathf.RoundToInt(v.y * height);
                        if (v.z <= 0f || px < 1 || py < 1 || px >= width - 1 || py >= height - 1)
                        {
                            continue;
                        }
                        samples++;
                        Color32 c = pixels[py * width + px];
                        if (c.g > c.r + 20 && c.g > c.b + 20)
                        {
                            green++;
                        }
                    }
                    break;
                }
            }
            TestContext.WriteLine($"[Step70a] {look}: {walls} shared walls, {samples} footprint samples, {green} green");
            Assert.Greater(walls, 1, "premise: level12 has shared walls with a solid piece");
            Assert.Greater(samples, 20, "premise: the footprint samples are on screen");
            Assert.LessOrEqual(green, samples / 20, $"{look}: the garden shows through the footprint of a cut wall ({green} of {samples} samples)");
        }

        [UnityTest]
        public IEnumerator Step70b_OuterWallFadesAsOneWhateverThePlayerSide()
        {
            bool found = false;
            foreach (string id in new[] { "level2", "level6", "level9", "level10", "level12" })
            {
                yield return Load(id);
                WallFader fader = Fader;
                Transform savedTarget = fader.Target;
                FurnitureController savedFurniture = fader.Furniture;
                var dummy = new GameObject("WallTestTarget").transform;
                fader.Furniture = null;
                fader.Target = dummy;
                try
                {
                    foreach (MeshRenderer cap in Caps())
                    {
                        if (!fader.IsOuter(cap) || !fader.PlaneOf(cap, out Vector3 point, out Vector3 inward))
                        {
                            continue;
                        }
                        // A room of the house beyond this outer wall's plane: the player there is outside the plane too.
                        foreach (RoomDef room in Game.Def.AllRooms())
                        {
                            var centre = new Vector3(room.X, 0f, room.Z);
                            if (Vector3.Dot(centre - point, inward) > -0.5f)
                            {
                                continue;
                            }
                            found = true;
                            dummy.position = centre;
                            Vector3 outside = point - inward * 4f + Vector3.up * 5f;
                            fader.Apply(outside);
                            Assert.IsTrue(Cut(cap), $"{id}: the cap of {cap.transform.parent.name} stays solid while the camera sees through its wall "
                                + "(the player outside its plane too)");
                            Vector3 inside = point + inward * 2f + Vector3.up * 5f;
                            fader.Apply(inside);
                            Assert.IsFalse(Cut(cap), $"{id}: the cap of {cap.transform.parent.name} is faded with the camera inside it and "
                                + "the player on the same side of the camera's other walls");
                            break;
                        }
                    }

                    // M9 doors rule (product owner, 2026-11-19): the door frames of an outer doorway never move, in any look,
                    // while their wall's cap does.
                    foreach (MeshRenderer r in Game.Level.Root.GetComponentsInChildren<MeshRenderer>(true))
                    {
                        if (r.name != "DoorFrame" || !fader.IsOuter(r) || !fader.PlaneOf(r, out Vector3 point, out Vector3 inward))
                        {
                            continue;
                        }
                        dummy.position = Game.Def.Player.Position;
                        foreach (string walls in new[] { SaveOptions.WallsSeeThrough, SaveOptions.WallsBoth, SaveOptions.WallsLowered, SaveOptions.WallsNone })
                        {
                            SetWalls(walls, Tuning.WallOpacityDefault);
                            fader.Apply(point - inward * 4f + Vector3.up * 5f);
                            Assert.IsFalse(Cut(r), $"{id} {walls}: an outer door frame moved with its wall seen from outside");
                            Assert.AreEqual(1f, fader.LevelOf(r), 1e-4f, $"{id} {walls}: an outer door frame does not stand whole");
                            fader.Apply(point + inward * 1.5f + Vector3.up * 3f);
                            Assert.IsFalse(Cut(r), $"{id} {walls}: an outer door frame moved with the camera inside its wall");
                        }
                        SetWalls(SaveOptions.WallsSeeThrough, Tuning.WallOpacityDefault);
                    }
                }
                finally
                {
                    fader.Target = savedTarget;
                    fader.Furniture = savedFurniture;
                    Object.Destroy(dummy.gameObject);
                }
                if (found)
                {
                    break;
                }
            }
            yield return Frames(2);
            Assert.IsTrue(found, "premise: no level has a room beyond the plane of one of its outer walls");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        [UnityTest]
        public IEnumerator Step70c_WallsFadeAtOnceAndComeBackSmoothly()
        {
            yield return Load("level12");
            WallFader fader = Fader;
            OrbitCamera orbit = Game.Camera;
            Camera cam = main.Camera;
            Vector3 player = Game.Furniture.transform.position;
            float yaw = orbit.Yaw;
            int movingFrames = 0;
            int maxMoving = 0;
            // A slow full orbit, 6 degrees a frame: never a jump, so the walls animate.
            for (int step = 0; step < 60; step++)
            {
                orbit.SetView(yaw + 6f * step, orbit.Pitch);
                yield return null;
                Vector3 eye = cam.transform.position;
                if (fader.Moving > 0)
                {
                    movingFrames++;
                    maxMoving = Mathf.Max(maxMoving, fader.Moving);
                }
                // A wall the rule fades is never drawn solid, not even for a frame (only coming back is gradual).
                foreach (MeshRenderer cap in Caps())
                {
                    if (!fader.PlaneOf(cap, out Vector3 point, out Vector3 normal))
                    {
                        continue;
                    }
                    float camSide = Vector3.Dot(eye - point, normal);
                    bool rule = fader.IsOuter(cap) ? camSide < 0f : camSide * Vector3.Dot(player - point, normal) < 0f;
                    if (rule)
                    {
                        Assert.IsTrue(Cut(cap), $"step {step}: the cap of {cap.transform.parent.name} is drawn solid while its wall is faded");
                    }
                }
            }
            Assert.Greater(movingFrames, 0, "no wall ever faded or came back during a full orbit");
            float start = Time.realtimeSinceStartup;
            while (fader.Moving > 0 && Time.realtimeSinceStartup - start < 3f)
            {
                yield return null;
            }
            Assert.AreEqual(0, fader.Moving, "a wall transition never ends");
            TestContext.WriteLine($"[Step70c] {movingFrames} frames with walls moving, at most {maxMoving} parts at once");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        [UnityTest]
        public IEnumerator Step70d_PlansBetweenRoomsCrossWallsOnlyThroughDoorways()
        {
            int plans = 0;
            foreach (string id in new[] { "level2", "level12", "level19", "level24" })
            {
                yield return Load(id);
                var nav = Game.Level.Planner as NavPlanner;
                Assert.IsNotNull(nav, $"{id}: premise: the level plans on its NavMesh");
                // Every wall piece standing on the floor: a doorway is the gap between two of them (its lintel is higher).
                var walls = new List<Bounds>();
                foreach (BoxCollider c in Game.Level.Root.GetComponentsInChildren<BoxCollider>(true))
                {
                    if (c.name == "Segment" && c.gameObject.layer == Layers.Occluder && c.bounds.min.y < 0.1f)
                    {
                        walls.Add(c.bounds);
                    }
                }
                Assert.Greater(walls.Count, 4, $"{id}: premise: the walls stand on the floor");
                var points = new List<Vector3>();
                var offsets = new[] { Vector2.zero, new Vector2(0.3f, 0.3f), new Vector2(-0.3f, 0.3f), new Vector2(0.3f, -0.3f), new Vector2(-0.3f, -0.3f) };
                foreach (RoomDef room in Game.Def.AllRooms())
                {
                    foreach (Vector2 o in offsets)
                    {
                        var p = new Vector3(room.X + o.x * room.SizeX, 0f, room.Z + o.y * room.SizeZ);
                        if (nav.Covers(p))
                        {
                            points.Add(p);
                            break;
                        }
                    }
                }
                Assert.AreEqual(Game.Def.AllRooms().Count, points.Count, $"{id}: premise: a point of every room is on the NavMesh");
                var corners = new List<Vector3>();
                int levelPlans = 0;
                for (int i = 0; i < points.Count; i++)
                {
                    for (int j = i + 1; j < points.Count; j++)
                    {
                        if (!nav.TryPlan(points[i], points[j], corners, NavMesh.AllAreas))
                        {
                            continue;
                        }
                        levelPlans++;
                        Vector3 a = YawMath.Planar(points[i]);
                        foreach (Vector3 b in corners)
                        {
                            int steps = Mathf.Max(1, Mathf.CeilToInt((b - a).magnitude / 0.04f));
                            for (int k = 0; k <= steps; k++)
                            {
                                Vector3 q = Vector3.Lerp(a, b, k / (float)steps);
                                foreach (Bounds w in walls)
                                {
                                    if (q.x > w.min.x + 0.02f && q.x < w.max.x - 0.02f && q.z > w.min.z + 0.02f && q.z < w.max.z - 0.02f)
                                    {
                                        Assert.Fail($"{id}: the plan from {points[i]} to {points[j]} crosses a wall at {q} instead of a doorway");
                                    }
                                }
                            }
                            a = b;
                        }
                    }
                }
                Assert.GreaterOrEqual(levelPlans, points.Count - 1, $"{id}: premise: the rooms are joined by plans");
                plans += levelPlans;
            }
            TestContext.WriteLine($"[Step70d] {plans} plans between rooms, none through a wall");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Step 70e (product owner, 2026-11-19: "the humans show through the closed walls"): an inhabitant standing behind a
        /// standing wall, the camera on the other side (the player's), its vision cone hidden. Against the render without
        /// it, what the body adds over the wall is only the flat blue x-ray silhouette, never its own colours. The two renders
        /// are saved to TestResults/walls (xray_behind_wall.png, xray_behind_wall_empty.png).
        /// </summary>
        [UnityTest]
        public IEnumerator Step70e_InhabitantBehindAStandingWallShowsOnlyAsTheSilhouette()
        {
            yield return Load("level2");
            WallFader fader = Fader;
            FurnitureController chair = Game.Furniture;
            RoomDef home = Game.Def.RoomAt(chair.transform.position);
            RoomDef other = Game.Def.AllRooms().Find(r => r != home);
            Assert.IsNotNull(other, "premise: a second room");
            Vector3 chairAt = YawMath.Planar(chair.transform.position);
            var there = new Vector3(other.X, 0f, other.Z);
            Inhabitant h = Game.MainInhabitant;
            float viewYaw = YawMath.YawOf(there - chairAt);
            Game.Camera.SetView(viewYaw, 24f);
            h.Pin(there, viewYaw + 180f);
            foreach (VisionConeView cone in Game.Level.Cones)
            {
                cone.gameObject.SetActive(false);
            }
            yield return Frames(4);
            Camera cam = main.Camera;
            Vector3 eye = cam.transform.position;
            Vector3 chest = there + Vector3.up * 1.2f;
            // The wall nearest the inhabitant (the camera may stand outside the house, beyond a faded outer wall).
            Assert.IsTrue(Physics.Linecast(chest, eye, out RaycastHit hit, Layers.OccluderMask, QueryTriggerInteraction.Ignore),
                "premise: a wall stands between the camera and the inhabitant");
            Transform wall = hit.collider.transform.parent;
            Renderer cap = wall != null ? wall.Find("Cap")?.GetComponent<Renderer>() : null;
            Assert.IsNotNull(cap, $"premise: {hit.collider.name} belongs to a wall line with a cap");
            Assert.IsFalse(Cut(cap), $"premise: {wall.name} stands (not faded) for this camera");
            int width = 960;
            int height = Mathf.Max(1, Mathf.RoundToInt(960f * Screen.height / Mathf.Max(1, Screen.width)));
            fader.Apply(eye);
            Color32[] with = RenderPixels(cam, width, height, "xray_behind_wall.png");
            h.Pin(new Vector3(90f, 0f, 90f), 0f);
            yield return Frames(4);
            fader.Apply(cam.transform.position);
            Color32[] none = RenderPixels(cam, width, height, "xray_behind_wall_empty.png");

            Vector3 head = cam.WorldToViewportPoint(there + Vector3.up * 1.9f);
            Vector3 feet = cam.WorldToViewportPoint(there);
            Vector3 side = cam.WorldToViewportPoint(there + Vector3.up * 1.2f + cam.transform.right * 0.45f);
            float halfWidth = Mathf.Max(6f, Mathf.Abs(side.x - head.x) * width);
            var body = Rect.MinMaxRect(head.x * width - halfWidth, Mathf.Min(feet.y, head.y) * height - 4f, head.x * width + halfWidth,
                Mathf.Max(feet.y, head.y) * height + 4f);
            int blue = 0;
            int colour = 0;
            for (int y = Mathf.Max(0, (int)body.yMin); y < Mathf.Min(height, (int)body.yMax); y++)
            {
                for (int x = Mathf.Max(0, (int)body.xMin); x < Mathf.Min(width, (int)body.xMax); x++)
                {
                    Color32 a = with[y * width + x];
                    Color32 b = none[y * width + x];
                    if (Mathf.Max(Mathf.Abs(a.r - b.r), Mathf.Max(Mathf.Abs(a.g - b.g), Mathf.Abs(a.b - b.b))) < 26)
                    {
                        continue;
                    }
                    // The flat x-ray blue (ProjectSetup's silhouette colour over a wall, after the grade): about (120, 145, 215),
                    // far bluer and brighter than any skin, hair or clothes.
                    if (a.b > 170 && a.b - a.r > 60 && a.b - a.g > 40)
                    {
                        blue++;
                    }
                    else
                    {
                        colour++;
                    }
                }
            }
            TestContext.WriteLine($"[Step70e] behind {wall.name}: {blue} silhouette pixels, {colour} body coloured pixels in {body}");
            Assert.Greater(blue, 30, "premise: the x-ray silhouette shows the hidden body");
            Assert.LessOrEqual(colour, Mathf.Max(8, blue / 20), $"the inhabitant shows in its own colours through the standing wall ({colour} pixels)");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Step 70f (product owner, 2026-11-19): each look of the Walls option moves the right parts of a shared wall with a
        /// doorway, the camera on the far side of it from the player: lowered, the wall sinks (its cap and faces) while its
        /// door frame stays standing and the stubs show; see-through, the wall fades to the opacity option while its frame stays opaque (M9 doors rule) and
        /// the stubs hide; both, the same with the stubs shown; off, nothing moves, over a full orbit too. Each switch applies
        /// at once. The lowered doorway with an inhabitant walking through it is saved to TestResults/walls/doorway_lowered.png,
        /// the same view in the both look to doorway_both.png (the see-through copies drawn, so the two differ over the wall).
        /// </summary>
        [UnityTest]
        public IEnumerator Step70f_EachLookMovesTheRightPartsAndLoweredDoorwaysStand()
        {
            yield return Load("level12");
            WallFader fader = Fader;
            Camera cam = main.Camera;
            Vector3 player = Game.Furniture.transform.position;
            MeshRenderer cap = null;
            Renderer frame = null;
            Vector3 point = default;
            Vector3 normal = default;
            Vector3 door = default;
            float doorWidth = 0f;
            MeshRenderer[] renderers = Game.Level.Root.GetComponentsInChildren<MeshRenderer>(true);
            foreach (MeshRenderer c in Caps())
            {
                if (cap != null || fader.IsOuter(c) || !fader.PlaneOf(c, out Vector3 p, out Vector3 n))
                {
                    continue;
                }
                foreach (OpeningDef d in Game.Def.Doors)
                {
                    var at = new Vector3(d.X, 0f, d.Z);
                    if (!d.IsPointForm || Mathf.Abs(Vector3.Dot(at - p, n)) > 0.1f || Mathf.Abs(Vector3.Dot(player - p, n)) < 0.5f)
                    {
                        continue;
                    }
                    foreach (MeshRenderer r in renderers)
                    {
                        if (r.name == "DoorFrame" && fader.PlaneOf(r, out Vector3 fp, out Vector3 fn) && Mathf.Abs(Vector3.Dot(fp - p, n)) < 1e-3f
                            && Mathf.Abs(Mathf.Abs(Vector3.Dot(fn, n)) - 1f) < 1e-3f)
                        {
                            cap = c;
                            frame = r;
                            point = p;
                            normal = n;
                            door = at;
                            doorWidth = d.Width;
                        }
                    }
                }
            }
            Assert.IsNotNull(cap, "premise: level12 has a shared wall with a doorway, the player off its plane");
            float side = Mathf.Sign(Vector3.Dot(player - point, normal));
            Vector3 eye = door - normal * (side * 3.5f) + Vector3.up * 5f;
            IReadOnlyList<Renderer> stubs = fader.Stubs;
            Assert.Greater(stubs.Count, 0, "premise: the walls have their stub");

            SetWalls(SaveOptions.WallsLowered, 20);
            fader.Apply(eye);
            Assert.IsTrue(Cut(cap), "lowered: the wall between the camera and the player is lowered");
            Assert.IsFalse(Cut(frame), "lowered: its door frame stays standing, so the doorway reads");
            Assert.IsTrue(fader.IsDoor(frame), "premise: the frame is marked as a door part");
            Assert.AreEqual(0f, fader.AlphaOf(cap), "lowered: the wall shows nothing above its stub");
            // A shared wall's baseboards stand in its lowered wall (they fade with it in the other looks).
            Renderer boards = renderers.FirstOrDefault(r => r.name == "Baseboards" && fader.PlaneOf(r, out Vector3 bp, out Vector3 bn)
                && Mathf.Abs(Vector3.Dot(bp - point, normal)) < 1e-3f && Mathf.Abs(Mathf.Abs(Vector3.Dot(bn, normal)) - 1f) < 1e-3f);
            Assert.IsNotNull(boards, "premise: the wall with the doorway has its baseboards");
            Assert.IsTrue(fader.KeepsStandingWhenLowered(boards), "premise: the baseboards are marked to stand");
            Assert.IsFalse(Cut(boards), "lowered: the baseboards of the lowered wall do not stand");
            Assert.IsTrue(stubs.All(s => s.enabled), "lowered: the stubs show");

            SetWalls(SaveOptions.WallsSeeThrough, 20);
            fader.Apply(eye);
            Assert.IsTrue(Cut(cap), "see-through: the wall fades");
            Assert.IsFalse(Cut(frame), "see-through: its door frame fades with it (doors never move)");
            Assert.AreEqual(0.2f, fader.AlphaOf(cap), 1e-4f, "see-through: the wall shows at the opacity option");
            Assert.AreEqual(1f, fader.AlphaOf(frame), 1e-4f, "see-through: its frame stays opaque");
            Assert.IsTrue(Cut(boards), "see-through: the baseboards fade with their wall");
            Assert.IsTrue(stubs.All(s => !s.enabled), "see-through: no stub");
            SetWalls(SaveOptions.WallsSeeThrough, 50);
            fader.Apply(eye);
            Assert.AreEqual(0.5f, fader.AlphaOf(cap), 1e-4f, "a new opacity applies at once");
            SetWalls(SaveOptions.WallsSeeThrough, 10);
            fader.Apply(eye);
            Assert.AreEqual(0.1f, fader.AlphaOf(cap), 1e-4f, "a new opacity applies at once");

            SetWalls(SaveOptions.WallsBoth, 35);
            fader.Apply(eye);
            Assert.IsTrue(Cut(cap) && !Cut(frame), "both: the wall above its stub fades, its frame stands opaque");
            Assert.AreEqual(1f, fader.AlphaOf(frame), 1e-4f, "both: the frame stays opaque");
            Assert.AreEqual(0.35f, fader.AlphaOf(cap), 1e-4f, "both: at the opacity option");
            Assert.IsTrue(stubs.All(s => s.enabled), "both: the stubs show under the faded wall");

            SetWalls(SaveOptions.WallsNone, 20);
            fader.Apply(eye);
            Assert.IsFalse(Cut(cap) || Cut(frame), "off: the wall stays as it is");
            Assert.AreEqual(0, fader.HiddenCount, "off: no wall moves");
            Assert.IsTrue(stubs.All(s => !s.enabled), "off: no stub");
            OrbitCamera orbit = Game.Camera;
            float yaw = orbit.Yaw;
            for (int step = 0; step < 12; step++)
            {
                orbit.SetView(yaw + 30f * step, orbit.Pitch);
                yield return null;
                Assert.AreEqual(0, fader.HiddenCount, $"off: a wall moved at yaw {yaw + 30f * step}");
                Assert.AreEqual(0, fader.Moving, "off: a wall moved");
                Assert.IsTrue(Caps().All(c => !Cut(c)), "off: a cap is out of the way");
            }

            // The lowered doorway, an inhabitant walking through it.
            SetWalls(SaveOptions.WallsLowered, 20);
            Game.MainInhabitant.Pin(door, YawMath.YawOf(normal * -side));
            yield return Frames(3);
            cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(door + Vector3.up * 0.8f - eye));
            fader.Apply(eye);
            // A render by hand runs before this frame's LateUpdate: what shows of a moved part is queued by DrawFaded.
            fader.DrawFaded(cam);
            Color32[] lowered = RenderPixels(cam, 960, 600, "doorway_lowered.png");
            SetWalls(SaveOptions.WallsBoth, 20);
            fader.Apply(eye);
            fader.DrawFaded(cam);
            Color32[] both = RenderPixels(cam, 960, 600, "doorway_both.png");

            // Both shows the wall above its stub at 20 % where lowered shows what stood behind it: the two renders differ over
            // the wall on each side of the doorway, its frame left out (a render without the see-through copies only loses the
            // frame). Measured with the camera of the renders, before the orbit camera moves it again.
            Vector3 along = Vector3.Cross(Vector3.up, normal).normalized;
            long diff = 0;
            int pixels = 0;
            foreach (float sign in new[] { -1f, 1f })
            {
                float minX = float.MaxValue, minY = float.MaxValue, maxX = float.MinValue, maxY = float.MinValue;
                foreach (float a in new[] { doorWidth * 0.5f + 0.25f, doorWidth * 0.5f + 0.9f })
                {
                    foreach (float h in new[] { Tuning.WallStubHeight + 0.2f, 2.2f })
                    {
                        Vector3 v = cam.WorldToViewportPoint(door + along * (sign * a) + Vector3.up * h);
                        minX = Mathf.Min(minX, v.x * 960f);
                        maxX = Mathf.Max(maxX, v.x * 960f);
                        minY = Mathf.Min(minY, v.y * 600f);
                        maxY = Mathf.Max(maxY, v.y * 600f);
                    }
                }
                for (int y = Mathf.Max(0, (int)minY); y < Mathf.Min(600, (int)maxY); y++)
                {
                    for (int x = Mathf.Max(0, (int)minX); x < Mathf.Min(960, (int)maxX); x++)
                    {
                        Color32 a = lowered[y * 960 + x];
                        Color32 b = both[y * 960 + x];
                        diff += Mathf.Abs(a.r - b.r) + Mathf.Abs(a.g - b.g) + Mathf.Abs(a.b - b.b);
                        pixels++;
                    }
                }
            }
            float mean = pixels > 0 ? (float)diff / pixels : 0f;
            SetWalls(SaveOptions.WallsLowered, 20);
            yield return Frames(2);
            TestContext.WriteLine($"[Step70f] doorway lowered vs both: mean difference {mean:0.00} (of 765) over {pixels} pixels");
            Assert.Greater(pixels, 1000, "premise: the wall around the doorway is on screen");
            Assert.Greater(mean, 8f, "the doorway's Both render shows no see-through wall over the lowered one");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Step 70g: the Options page's Walls and Wall opacity rows, under the cone row: chained in order, each with its icon,
        /// cycling and saving their value, applied at once to the wall fader in play, the opacity row dimmed while the look
        /// ignores it, English and French labels, and the eleven rows still clear of the music credits on a 20:9 phone.
        /// </summary>
        [UnityTest]
        public IEnumerator Step70g_OptionsWallsRowsCycleApplyAndFit()
        {
            Menu menu = main.Menu;
            Assert.IsNotNull(menu, "premise: Main built no Menu");
            Button walls = menu.OptionsWallsButton;
            Button opacity = menu.OptionsWallOpacityButton;
            Assert.IsNotNull(walls, "the Options page has no Walls row");
            Assert.IsNotNull(opacity, "the Options page has no Wall opacity row");
            Assert.AreSame(walls, menu.OptionsConeButton.navigation.selectOnDown, "down from the cone row is not Walls");
            Assert.AreSame(opacity, walls.navigation.selectOnDown, "down from Walls is not Wall opacity");
            Assert.AreSame(menu.OptionsQualityButton, opacity.navigation.selectOnDown, "down from Wall opacity is not Quality");
            Assert.AreSame(walls, opacity.navigation.selectOnUp, "up from Wall opacity is not Walls");
            Assert.IsNotNull(walls.transform.Find("OptionsWallsIcon"), "the Walls row has no icon");
            Assert.IsNotNull(opacity.transform.Find("OptionsWallOpacityIcon"), "the Wall opacity row has no icon");
            Assert.IsTrue(menu.Labels.TryGetValue("OptionsWallsLabel", out Text wallsLabel), "the Walls row has no label");
            Assert.IsTrue(menu.Labels.TryGetValue("OptionsWallOpacityLabel", out Text opacityLabel), "the Wall opacity row has no label");

            menu.SetPaused(true);
            menu.OpenOptions();
            Assert.IsTrue(menu.OptionsOpen, "premise: Options opened from the pause menu");
            Assert.AreEqual(string.Format(Strings.OptionsWalls, Strings.OptionsWallsLowered), wallsLabel.text, "the row does not show the default");
            Assert.Less(opacityLabel.color.a, 1f, "the opacity row is not dimmed while the default (lowered) ignores it");
            walls.onClick.Invoke();
            Assert.AreEqual(SaveOptions.WallsSeeThrough, SaveStore.Options.Walls, "a click did not step the Walls option from lowered to see-through");
            walls.onClick.Invoke();
            Assert.AreEqual(SaveOptions.WallsBoth, SaveStore.Options.Walls, "a click did not step the Walls option from see-through to both");
            Assert.AreEqual(1f, opacityLabel.color.a, 1e-4f, "the opacity row is dimmed while both uses it");
            walls.onClick.Invoke();
            Assert.AreEqual(SaveOptions.WallsNone, SaveStore.Options.Walls, "a click did not step the Walls option from both to off");
            Assert.Less(opacityLabel.color.a, 1f, "the opacity row is not dimmed while the walls are off");
            walls.onClick.Invoke();
            Assert.AreEqual(SaveOptions.WallsLowered, SaveStore.Options.Walls, "a click did not step the Walls option from off to lowered");
            Assert.Less(opacityLabel.color.a, 1f, "the opacity row is not dimmed while the walls are lowered");
            walls.onClick.Invoke();
            Assert.AreEqual(SaveOptions.WallsSeeThrough, SaveStore.Options.Walls, "a click did not step the Walls option");
            Assert.AreEqual(string.Format(Strings.OptionsWalls, Strings.OptionsWallsSeeThrough), wallsLabel.text, "the row did not refresh");
            Assert.AreEqual(1f, opacityLabel.color.a, 1e-4f, "the opacity row stays dimmed while it applies");
            opacity.onClick.Invoke();
            Assert.AreEqual(35, SaveStore.Options.WallOpacity, "a click did not step the opacity");
            Assert.AreEqual(string.Format(Strings.OptionsWallOpacity, 35), opacityLabel.text);
            menu.OptionsVolumeButton.onClick.Invoke();
            Assert.AreEqual(SaveOptions.WallsSeeThrough, SaveStore.Options.Walls, "the Volume row reset the Walls option");
            Assert.AreEqual(35, SaveStore.Options.WallOpacity, "the Volume row reset the wall opacity");
            menu.CloseOptions();
            menu.SetPaused(false);
            yield return Frames(2);
            Assert.AreEqual(WallLook.SeeThrough, Fader.Look, "the wall fader did not take the new look at once");

            Assert.AreEqual("Walls: {0}", Strings.Get("options.walls", Strings.English));
            Assert.AreEqual("Murs : {0}", Strings.Get("options.walls", Strings.French));
            Assert.AreEqual("Wall opacity: {0}%", Strings.Get("options.wallOpacity", Strings.English));
            Assert.AreEqual("Opacité des murs : {0} %", Strings.Get("options.wallOpacity", Strings.French));
            CollectionAssert.AreEqual(new[] { "Lowered", "See-through", "Both", "Off" },
                new[] { "options.wallsLowered", "options.wallsSeeThrough", "options.wallsBoth", "options.wallsNone" }.Select(k => Strings.Get(k, Strings.English)));
            CollectionAssert.AreEqual(new[] { "Baissés", "Transparents", "Les deux", "Aucun" },
                new[] { "options.wallsLowered", "options.wallsSeeThrough", "options.wallsBoth", "options.wallsNone" }.Select(k => Strings.Get(k, Strings.French)));

            // Eleven rows: Retour still clears the music credits line at the bottom of a 20:9 phone (966 reference units).
            var back = (RectTransform)menu.OptionsBackButton.transform;
            float bottom = back.anchoredPosition.y - back.sizeDelta.y * back.pivot.y;
            Assert.Greater(bottom, -966f / 2f + 36f, "Retour runs into the music credits line on a 20:9 screen");
            var cone = (RectTransform)menu.OptionsConeButton.transform;
            var wallsRect = (RectTransform)walls.transform;
            Assert.GreaterOrEqual(cone.anchoredPosition.y - cone.sizeDelta.y * cone.pivot.y,
                wallsRect.anchoredPosition.y + wallsRect.sizeDelta.y * (1f - wallsRect.pivot.y), "the cone and Walls rows overlap");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Step 70h (review of the Walls option): a wall fixture's glow (RoomLights: sconce, tube, strip, reading light) goes with
        /// its wall line. On level12 (its kitchen strip and its sconces hang on walls), from the four high views around the
        /// player: lowered, see-through and both, no glow vertex hangs on the face of a wall line that is out of the way
        /// (above the 1 m the lamps on furniture stay under, within the fixtures' depth off the face), while every line that
        /// stands keeps the glows it carries with the walls off.
        /// </summary>
        [UnityTest]
        public IEnumerator Step70h_WallFixturesGoWithTheirWall()
        {
            yield return Load("level12");
            WallFader fader = Fader;
            RoomLights lights = Game.Level.Root.GetComponentInChildren<RoomLights>(true);
            Assert.IsNotNull(lights, "premise: level12 has its secondary lights");
            Assert.IsTrue(lights.Fixtures.Any(f => f.Style == RoomLights.Style.Strip || f.Style == RoomLights.Style.Sconce),
                "premise: level12 has wall fixtures");
            Vector3 player = Game.Furniture.transform.position;
            float t = Game.Def.WallThickness();
            var eyes = new List<Vector3>();
            for (int i = 0; i < 4; i++)
            {
                Quaternion orbit = Quaternion.Euler(48f, Game.Def.Player.Yaw + 90f * i, 0f);
                eyes.Add(player + Vector3.up * 0.5f - orbit * Vector3.forward * 9f);
            }
            List<MeshRenderer> caps = Caps();
            SetWalls(SaveOptions.WallsNone, 20);
            fader.Apply(eyes[0]);
            var carried = new Dictionary<MeshRenderer, int>();
            List<Vector3> rest = GlowVertices(lights);
            int onWalls = 0;
            foreach (MeshRenderer cap in caps)
            {
                carried[cap] = OnWallFace(rest, cap, fader, t);
                onWalls += carried[cap];
            }
            Assert.Greater(onWalls, 0, "premise: glow vertices hang on the wall faces with the walls off");

            int checkedOut = 0;
            foreach (string walls in new[] { SaveOptions.WallsLowered, SaveOptions.WallsSeeThrough, SaveOptions.WallsBoth })
            {
                SetWalls(walls, 20);
                foreach (Vector3 eye in eyes)
                {
                    fader.Apply(eye);
                    List<Vector3> glow = GlowVertices(lights);
                    foreach (MeshRenderer cap in caps)
                    {
                        int on = OnWallFace(glow, cap, fader, t);
                        if (fader.LevelOf(cap) < 1f)
                        {
                            checkedOut += carried[cap] > 0 ? 1 : 0;
                            Assert.AreEqual(0, on, $"{walls}: {on} glow vertices hang on {cap.transform.parent.name}, out of the way from {eye}");
                        }
                        else
                        {
                            Assert.AreEqual(carried[cap], on, $"{walls}: {cap.transform.parent.name} stands from {eye} but lost its fixtures");
                        }
                    }
                }
            }
            TestContext.WriteLine($"[Step70h] {onWalls} wall glow vertices, {checkedOut} views of a line with fixtures out of the way");
            Assert.Greater(checkedOut, 2, "premise: lines with fixtures get out of the way in these views");
            SetWalls(SaveOptions.WallsLowered, 20);
            yield return Frames(2);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>The world vertices of every glow renderer of the room lights, as drawn now.</summary>
        private static List<Vector3> GlowVertices(RoomLights lights)
        {
            var all = new List<Vector3>();
            foreach (MeshRenderer r in lights.Glows)
            {
                if (r == null || !r.enabled || r.forceRenderingOff)
                {
                    continue;
                }
                Matrix4x4 world = r.localToWorldMatrix;
                foreach (Vector3 v in r.GetComponent<MeshFilter>().sharedMesh.vertices)
                {
                    all.Add(world.MultiplyPoint3x4(v));
                }
            }
            return all;
        }

        /// <summary>
        /// The vertices on a face of the wall line of <paramref name="cap"/>: within its run (the cap's bounds along the line),
        /// at most the fixtures' depth (0.15 m) off either face, and higher than 1 m (a lamp on a table or a nightstand stays lower).
        /// </summary>
        private static int OnWallFace(List<Vector3> vertices, MeshRenderer cap, WallFader fader, float thickness)
        {
            if (!fader.PlaneOf(cap, out Vector3 point, out Vector3 normal))
            {
                return 0;
            }
            Bounds b = cap.bounds;
            bool alongX = Mathf.Abs(normal.z) > 0.5f;
            int n = 0;
            foreach (Vector3 v in vertices)
            {
                float a = alongX ? v.x : v.z;
                float lo = alongX ? b.min.x : b.min.z;
                float hi = alongX ? b.max.x : b.max.z;
                if (v.y > 1f && a > lo - 0.05f && a < hi + 0.05f && Mathf.Abs(Vector3.Dot(v - point, normal)) < thickness * 0.5f + 0.15f)
                {
                    n++;
                }
            }
            return n;
        }

        private static Color32[] RenderPixels(Camera cam, int width, int height, string file)
        {
            Color32[] pixels = RenderPixels(cam, width, height);
            string dir = System.IO.Path.Combine("TestResults", "walls");
            System.IO.Directory.CreateDirectory(dir);
            var texture = new Texture2D(width, height, TextureFormat.RGBA32, false);
            texture.SetPixels32(pixels);
            texture.Apply();
            System.IO.File.WriteAllBytes(System.IO.Path.Combine(dir, file), texture.EncodeToPNG());
            Object.Destroy(texture);
            return pixels;
        }

        private static Color32[] RenderPixels(Camera cam, int width, int height)
        {
            RenderTexture rt = RenderTexture.GetTemporary(width, height, 24);
            var request = new RenderPipeline.StandardRequest { destination = rt };
            Assert.IsTrue(RenderPipeline.SupportsRenderRequest(cam, request), "premise: the pipeline cannot render the camera to a texture");
            RenderPipeline.SubmitRenderRequest(cam, request);
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = rt;
            var texture = new Texture2D(width, height, TextureFormat.RGBA32, false);
            texture.ReadPixels(new Rect(0, 0, width, height), 0, 0);
            texture.Apply();
            RenderTexture.active = previous;
            RenderTexture.ReleaseTemporary(rt);
            Color32[] pixels = texture.GetPixels32();
            Object.Destroy(texture);
            return pixels;
        }
    }
}
