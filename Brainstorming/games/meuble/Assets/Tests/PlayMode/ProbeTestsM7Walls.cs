using System;
using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M7 walls pass (product owner reports of 2026-11-18 and 2026-11-19): the see-through walls, on the real Boot scene.
    /// <list type="bullet">
    /// <item>Step 70a: the floor continues under a faded shared wall: seen from above, no garden shows through its footprint
    /// (the floor used to open on the grass under a hidden wall).</item>
    /// <item>Step 70b: an outer wall fades as one, cap and door frames with it, whenever the camera is outside it, even with
    /// the player outside its plane too (its cap used to stay over a wall the camera saw through).</item>
    /// <item>Step 70c: a wall fades at once, comes back smoothly, and every transition ends.</item>
    /// <item>Step 70d: the inhabitants' plans between the rooms cross the walls only through their doorways, on levels 2, 12,
    /// 19 and 24 (the walls' look never touches the colliders the NavMesh is baked from).</item>
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
            yield return Frames(2);
            TestContext.WriteLine($"[Step70a] {walls} shared walls, {samples} footprint samples, {green} green");
            Assert.Greater(walls, 1, "premise: level12 has shared walls with a solid piece");
            Assert.Greater(samples, 20, "premise: the footprint samples are on screen");
            Assert.LessOrEqual(green, samples / 20, $"the garden shows through the footprint of a faded wall ({green} of {samples} samples)");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
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

                    // The door frames of an outer doorway are registered with their wall's outer rule and fade with its cap.
                    foreach (MeshRenderer r in Game.Level.Root.GetComponentsInChildren<MeshRenderer>(true))
                    {
                        if (r.name != "DoorFrame" || !fader.IsOuter(r) || !fader.PlaneOf(r, out Vector3 point, out Vector3 inward))
                        {
                            continue;
                        }
                        dummy.position = Game.Def.Player.Position;
                        fader.Apply(point - inward * 4f + Vector3.up * 5f);
                        Assert.IsTrue(Cut(r), $"{id}: an outer door frame stays solid over its wall faded from outside");
                        fader.Apply(point + inward * 1.5f + Vector3.up * 3f);
                        Assert.IsFalse(Cut(r), $"{id}: an outer door frame is faded with the camera inside its wall");
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
