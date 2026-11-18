using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M5B watchers probe (docs/CONTRACT_M5.md 4, 6, 16.5, 16.8, 16.11, 16.12 and 17): the robot vacuum's visual (step 42w),
    /// the load's visual and its clue (step 44w; on a split level, step 44x), and the deferred 5A items: the floor cone on a split level (m14, step 37w),
    /// the dog's fan as a superset of what it sees (m20, step 38w) and the unmerged character slots (CONTRACT_M5 19, step 37x).
    ///
    /// Fixtures: test_m5_watchers_floor (a 0.6 m platform with two ramps), test_m5_watchers_cover (an awake dog and a watchful
    /// human behind a 0.5 m low wall and a 1.8 m wardrobe), test_m5_watchers_people (three humans and a dog). Every scenario
    /// asserts its premise first; waits are bounded by game time.
    /// </summary>
    public sealed class ProbeTestsM5BWatchers
    {
        private const float Dt = Tuning.FixedStep;
        private const string PeopleLevel = "test_m5_watchers_people";
        private const string FloorLevel = "test_m5_watchers_floor";
        private const string CoverLevel = "test_m5_watchers_cover";
        private const string DogLevel = "test_m5_watchers_dog";

        /// <summary>The fan floats this far above the floor (VisionConeView.FloorLift).</summary>
        private const float FloorLift = 0.015f;

        /// <summary>The floor fixture's platform: x in [-0.5, 0.5], all of z, 0.6 m high.</summary>
        private const float PlatformHeight = 0.6f;
        private const float PlatformHalfX = 0.5f;

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;
        private readonly List<Object> scratch = new List<Object>();

        private Main main;
        private GameState Game => main.Game;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            fixedSteps = 0;
            ModelKit.Disabled = false;
            GamePause.IsPaused = false;
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            GamePause.IsPaused = false;
            Game.Rules = GameRules.M1;
            Game.FixedStepped += CountStep;
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            GamePause.IsPaused = false;
            Application.logMessageReceived -= OnLog;
            foreach (Object o in scratch)
            {
                if (o != null)
                {
                    Object.Destroy(o);
                }
            }
            scratch.Clear();
            if (main != null && main.Game != null)
            {
                main.Game.FixedStepped -= CountStep;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                }
            }
            yield return null;
        }

        private void CountStep() => fixedSteps++;

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private IEnumerator Load(string id)
        {
            Game.LoadLevel(id);
            Game.Rules = GameRules.M1;
            yield return Steps(2);
            Assert.AreEqual(id, Game.Def.Id, "premise: the fixture did not load");
        }

        private Transform Scratch(string name)
        {
            var go = new GameObject(name);
            scratch.Add(go);
            return go.transform;
        }

        private VisionConeView ConeOf(Inhabitant h) => Game.Level.Cones.Find(c => c != null && c.Owner == h);

        /// <summary>Pins <paramref name="h"/> and lets the fixed step and one rendered frame rebuild its cone.</summary>
        private IEnumerator PinAndSettle(Inhabitant h, Vector3 at, float yaw)
        {
            h.Pin(at, yaw);
            yield return Steps(2);
            yield return null;
            yield return null;
        }

        private static float Planar(Vector3 a, Vector3 b) => YawMath.Planar(a - b).magnitude;

        /// <summary>m15: lets frames pass until the robot's drawn body stands on its rule pose (bounded by 3 s of real time).</summary>
        private static IEnumerator SettleBody(Robot robot, string label)
        {
            float realStart = Time.realtimeSinceStartup;
            while ((Planar(robot.Body.position, robot.Position) > 1e-4f || Mathf.Abs(Mathf.DeltaAngle(robot.VisualYaw, robot.Yaw)) > 0.01f)
                && Time.realtimeSinceStartup - realStart < 3f)
            {
                yield return null;
            }
            Assert.Less(Planar(robot.Body.position, robot.Position), 1e-4f, label + ": the drawn body never reached the pose");
            Assert.AreEqual(0f, Mathf.DeltaAngle(robot.VisualYaw, robot.Yaw), 0.01f, label + ": the drawn body never turned to the heading");
        }

        // ----- 42w: the robot vacuum's visual -----

        /// <summary>
        /// Robot.Create (CONTRACT_M5 4, 16.8, 16.12) builds the robot's path from its RobotDef and poses it where the path
        /// starts; it is a disc of RobotRadius and RobotHeight with no collider, on no occluder or NavMesh source layer, in 3
        /// material slots; it follows SetPose (position and heading, its light at its front) along its path, and its light
        /// pulses while the game runs.
        /// </summary>
        [UnityTest]
        public IEnumerator Step42w_RobotVisualFollowsSetPoseWithoutCollider()
        {
            var def = new RobotDef
            {
                Name = "Robo",
                Loop = new List<PointDef> { new PointDef { X = 0f, Z = 0f }, new PointDef { X = 2f, Z = 0f }, new PointDef { X = 2f, Z = 2f } },
            };
            Transform level = Scratch("Robot level");
            Robot robot = Robot.Create(def, level);
            Assert.IsNotNull(robot, "Robot.Create returned nothing");
            Assert.AreSame(def, robot.Def, "the robot keeps its def");
            Assert.IsNotNull(robot.Path, "the robot has no path");
            Assert.AreEqual(2f + 2f + Mathf.Sqrt(8f), robot.Path.Length, 1e-4f, "premise: the path is the def's loop");
            Assert.AreEqual(Tuning.RobotSpeed, robot.Path.Speed, 1e-6f, "premise: the default speed");
            Assert.AreSame(level, robot.transform.parent, "the robot is not under its parent");
            Assert.Less(Planar(robot.Position, robot.Path.PositionAt(0f)), 1e-4f, "the robot does not start where its path starts");
            Assert.AreEqual(robot.Path.HeadingAt(0f), robot.Yaw, 1e-3f, "the robot does not start along its path");

            // A visual only.
            Assert.IsEmpty(robot.GetComponentsInChildren<Collider>(true), "the robot carries a collider");
            foreach (Transform t in robot.GetComponentsInChildren<Transform>(true))
            {
                Assert.AreNotEqual(Layers.Occluder, t.gameObject.layer, $"{t.name} is an occluder");
                Assert.AreEqual(0, Layers.NavMeshSourceMask & (1 << t.gameObject.layer), $"{t.name} is on a NavMesh source layer");
            }
            Renderer[] renderers = robot.GetComponentsInChildren<Renderer>(true);
            Assert.GreaterOrEqual(renderers.Length, 2, "premise: the robot draws a body and a light");
            Assert.AreEqual(3, ModelKit.SlotsUnder(robot.transform), "the robot's material slots (shell, bumper, light)");
            foreach (Renderer r in renderers)
            {
                foreach (Material m in r.sharedMaterials)
                {
                    Assert.IsNotNull(m, $"{r.name}: an empty slot");
                    Color? palette = PrimitiveKit.PaletteOf(m);
                    Assert.IsFalse(palette.HasValue && ModelMath.IsRed(palette.Value), $"{r.name} is red (PRD 7.2)");
                }
            }

            // Its size, posed at the origin facing +z.
            robot.SetPose(Vector3.zero, 0f);
            float radius = 0f;
            float top = 0f;
            float bottom = float.MaxValue;
            foreach (MeshFilter f in robot.GetComponentsInChildren<MeshFilter>(true))
            {
                Matrix4x4 m = f.transform.localToWorldMatrix;
                foreach (Vector3 v in f.sharedMesh.vertices)
                {
                    Vector3 p = m.MultiplyPoint3x4(v);
                    radius = Mathf.Max(radius, YawMath.Planar(p).magnitude);
                    top = Mathf.Max(top, p.y);
                    bottom = Mathf.Min(bottom, p.y);
                }
            }
            Debug.Log($"[Step42w] robot: radius {radius:0.000} m, height {top:0.000} m, {ModelKit.SlotsUnder(robot.transform)} slots");
            Assert.That(radius, Is.EqualTo(Tuning.RobotRadius).Within(0.004f), "the robot's disc is not RobotRadius wide");
            Assert.That(top, Is.EqualTo(Tuning.RobotHeight).Within(0.003f), "the robot is not RobotHeight tall");
            Assert.GreaterOrEqual(bottom, -1e-4f, "the robot sinks into the floor");

            // It follows SetPose along its path: the root (the rule pose) at once; the drawn shell on the position and the
            // light ahead along the heading once the body has caught up (m15: it turns at a capped rate).
            Renderer shell = renderers.First(r => r.name == "Shell");
            Assert.IsNotNull(robot.Body, "the robot has no drawn body");
            Assert.IsTrue(shell.transform.IsChildOf(robot.Body) && robot.StatusLight.IsChildOf(robot.Body), "the shell and the light are not on the body");
            int poses = robot.PoseCount;
            foreach (float t in new[] { 0f, 1.3f, 4.2f, 7.5f, 11f })
            {
                Vector3 at = robot.Path.PositionAt(t);
                float heading = robot.Path.HeadingAt(t);
                robot.SetPose(at, heading);
                Assert.Less(Planar(robot.transform.position, at), 1e-4f, $"t {t}: the robot is not at its pose");
                Assert.AreEqual(0f, Mathf.DeltaAngle(heading, robot.transform.eulerAngles.y), 0.01f, $"t {t}: the root is not along its heading");
                yield return SettleBody(robot, $"t {t}");
                Assert.Less(Planar(shell.bounds.center, at), 1e-3f, $"t {t}: the shell is not drawn at the pose");
                Vector3 ahead = YawMath.Planar(robot.StatusLight.position - robot.Position).normalized;
                Assert.Greater(Vector3.Dot(ahead, robot.Path.ForwardAt(t)), 0.999f, $"t {t}: the robot's front is not along its path");
            }
            Assert.AreEqual(poses + 5, robot.PoseCount, "SetPose calls were not counted");
            robot.SetPose(new Vector3(1.5f, 0f, -0.7f), 135f);
            Assert.Less(Planar(robot.Position, new Vector3(1.5f, 0f, -0.7f)), 1e-4f, "an arbitrary pose");
            Assert.AreEqual(135f, robot.Yaw, 1e-4f);
            yield return SettleBody(robot, "an arbitrary pose");
            Assert.Greater(Vector3.Dot(YawMath.Planar(robot.StatusLight.position - robot.Position).normalized, YawMath.Forward(135f)), 0.999f,
                "the light is not at the front of an arbitrary pose");
            Physics.SyncTransforms();
            Assert.IsEmpty(Physics.OverlapSphere(robot.Position + Vector3.up * 0.05f, Tuning.RobotRadius)
                .Where(c => c.transform.IsChildOf(robot.transform)), "a collider stands where the robot is");

            // m15: posed once per fixed step as GameState does, along +x then reversed at a loop end. The drawn body never
            // turns faster than RobotTurnRate (the 180 degree reversal is seen mid-turn), stays within one step's travel of
            // the rule pose, on its line, and settles on the new heading.
            var start = new Vector3(-1f, 0f, 3f);
            robot.SetPose(start, 90f);
            yield return SettleBody(robot, "the drive's start");
            float speed = Tuning.RobotSpeed;
            float flipAt = 0.6f;
            int driven = 0;
            System.Action drive = () =>
            {
                driven++;
                float time = driven * Dt;
                float x = time < flipAt ? speed * time : speed * flipAt - speed * (time - flipAt);
                robot.SetPose(start + Vector3.right * x, time < flipAt ? 90f : 270f);
            };
            Game.FixedStepped += drive;
            float turnCap = Tuning.RobotTurnRate;
            float lastYaw = robot.VisualYaw;
            float lastDt = -1f;
            float worstTurn = 0f;
            int midTurn = 0;
            int readings = 0;
            float driveStart = Time.realtimeSinceStartup;
            try
            {
                while (driven * Dt < flipAt + 1.2f && Time.realtimeSinceStartup - driveStart < 20f)
                {
                    yield return null;
                    readings++;
                    float yawNow = robot.VisualYaw;
                    float bodyYaw = robot.Body.eulerAngles.y;
                    Assert.AreEqual(0f, Mathf.DeltaAngle(yawNow, bodyYaw), 0.01f, "the body is not drawn at its visual yaw");
                    // The change since the last reading is the last frame's LateUpdate, which turned by its own deltaTime.
                    if (lastDt >= 0f)
                    {
                        float turn = Mathf.Abs(Mathf.DeltaAngle(lastYaw, yawNow));
                        worstTurn = Mathf.Max(worstTurn, turn - turnCap * lastDt);
                        Assert.LessOrEqual(turn, turnCap * lastDt + 0.5f, $"the body turned {turn:0.0} deg in a frame of {lastDt:0.000} s");
                    }
                    float off = Mathf.Abs(Mathf.DeltaAngle(yawNow, robot.Yaw));
                    midTurn += off > 10f && off < 170f ? 1 : 0;
                    // Drawn last frame one step behind; this frame's fixed steps may have moved the root since.
                    Assert.LessOrEqual(Planar(robot.Body.position, robot.Position), speed * (2f * Dt + Time.deltaTime) + 1e-4f,
                        "the body lags the rule pose by more than its interpolation");
                    Assert.AreEqual(start.z, robot.Body.position.z, 1e-4f, "the body leaves its line");
                    lastYaw = yawNow;
                    lastDt = Time.deltaTime;
                }
            }
            finally
            {
                Game.FixedStepped -= drive;
            }
            Debug.Log($"[Step42w] the drive: {driven} poses, {readings} frames, {midTurn} seen mid-turn, worst turn over the cap {worstTurn:0.00} deg");
            Assert.GreaterOrEqual(driven * Dt, flipAt + 1.2f, "premise: the drive did not run past the reversal (game time stalled)");
            Assert.AreEqual(270f, robot.Yaw, 1e-4f, "premise: the rule pose reversed");
            Assert.Greater(midTurn, 0, "the body flipped 180 degrees within one frame at the reversal");
            Assert.AreEqual(0f, Mathf.DeltaAngle(robot.VisualYaw, 270f), 0.5f, "the body never settled on the reversed heading");

            // The light pulses while the game runs (visual only).
            Vector3 scale = robot.StatusLight.localScale;
            float realStart = Time.realtimeSinceStartup;
            bool pulsed = false;
            while (!pulsed && Time.realtimeSinceStartup - realStart < 3f)
            {
                yield return null;
                pulsed = (robot.StatusLight.localScale - scale).sqrMagnitude > 1e-4f;
            }
            Assert.IsTrue(pulsed, "the robot's light never pulses");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        // ----- 44w: the load's visual and its clue -----

        /// <summary>
        /// LoadView (CONTRACT_M5 6, 16.5): each kind sits on the top of the player chair's box, inside its footprint, exactly
        /// LoadHeight tall, over the chair's backrest rail (its highest part), with no collider; SetTilt leans it around its
        /// base toward the furniture's right (x) and front (y) by the vector's length; SpawnClue leaves its broken version on
        /// the floor where asked, under the level root (the furniture moving away leaves it there), and hides the carried
        /// one; ClearClue takes the clue away and Restore puts the load back. Decor colours, never red, 3 slots at most.
        /// </summary>
        [UnityTest]
        public IEnumerator Step44w_LoadSitsOnTopTiltsAndBreaks()
        {
            FurnitureController chair = Game.Furniture;
            Assert.IsNotNull(chair, "premise: no player furniture");
            Assert.AreEqual(BodyKinds.Chair, chair.Kind ?? BodyKinds.Chair, "premise: the Boot level's furniture is a chair");
            Transform visual = chair.Visual;
            Assert.IsNotNull(visual, "premise: the chair has no Visual");
            Vector3 size = chair.Size;
            Assert.Greater(size.y, 0.5f, "premise: the chair's box");
            Vector3 home = chair.transform.position;
            float yaw = chair.transform.eulerAngles.y;
            foreach (string kind in LoadView.Kinds)
            {
                chair.Teleport(home, yaw);
                yield return Steps(1);
                yield return null;
                LoadView view = LoadView.Create(kind, visual, size);
                Assert.IsNotNull(view, kind + ": no view");
                scratch.Add(view.gameObject);
                Assert.AreEqual(kind, view.Kind);
                Assert.IsTrue(view.transform.IsChildOf(visual), kind + ": not on the furniture");
                Assert.AreEqual(visual.gameObject.layer, view.gameObject.layer, kind + ": not on the furniture's layer");
                Assert.IsEmpty(view.GetComponentsInChildren<Collider>(true), kind + ": the load carries a collider");
                Assert.AreEqual(size.y, view.transform.localPosition.y, 1e-5f, kind + ": its base is not on the box top");
                // A chair's highest part is its backrest rail, on its -z side.
                Assert.Less(view.transform.localPosition.z, -0.05f, kind + ": not over the chair's backrest rail");

                // On the top, inside the footprint, LoadHeight tall (every vertex, in the furniture's frame).
                float low = float.MaxValue;
                float high = float.MinValue;
                float outside = 0f;
                int slots = 0;
                foreach (MeshFilter f in view.Carried.GetComponentsInChildren<MeshFilter>(true))
                {
                    Matrix4x4 m = visual.worldToLocalMatrix * f.transform.localToWorldMatrix;
                    foreach (Vector3 v in f.sharedMesh.vertices)
                    {
                        Vector3 p = m.MultiplyPoint3x4(v);
                        low = Mathf.Min(low, p.y);
                        high = Mathf.Max(high, p.y);
                        outside = Mathf.Max(outside, Mathf.Abs(p.x) - size.x * 0.5f, Mathf.Abs(p.z) - size.z * 0.5f);
                    }
                    MeshRenderer r = f.GetComponent<MeshRenderer>();
                    Assert.IsTrue(r != null && r.enabled, $"{kind}: {f.name} is not drawn");
                    slots += r.sharedMaterials.Length;
                    foreach (Material mat in r.sharedMaterials)
                    {
                        Color? palette = PrimitiveKit.PaletteOf(mat);
                        Assert.IsTrue(palette.HasValue, $"{kind}: {f.name} is not a palette material");
                        Assert.IsFalse(ModelMath.IsRed(palette.Value), $"{kind}: {f.name} is red (PRD 7.2)");
                    }
                }
                Debug.Log($"[Step44w] {kind}: from {low:0.000} to {high:0.000} m (box top {size.y}), {outside:0.000} m past the footprint, {slots} slots");
                Assert.That(low, Is.EqualTo(size.y).Within(0.005f), kind + ": the load does not sit on the box top");
                Assert.LessOrEqual(high, size.y + Tuning.LoadHeight + 0.002f, kind + ": the load rises past the sample box (LoadHeight)");
                Assert.GreaterOrEqual(high, size.y + Tuning.LoadHeight - 0.01f, kind + ": the load is shorter than LoadHeight");
                Assert.LessOrEqual(outside, 0.002f, kind + ": the load overhangs the footprint");
                Assert.That(slots, Is.InRange(1, 3), kind + ": material slots");

                // The tilt: around the base, toward +x for x, toward +z for y, by the vector's length.
                view.SetTilt(new Vector2(10f, 0f));
                Vector3 up = visual.InverseTransformDirection(view.Carried.up);
                Assert.That(Vector3.Angle(Vector3.up, up), Is.EqualTo(10f).Within(0.01f), kind + ": tilt angle");
                Assert.Greater(up.x, 0.15f, kind + ": a tilt x does not lean to the right");
                Assert.AreEqual(0f, up.z, 1e-4f, kind + ": a tilt x leans forward or back");
                view.SetTilt(new Vector2(0f, -8f));
                up = visual.InverseTransformDirection(view.Carried.up);
                Assert.That(Vector3.Angle(Vector3.up, up), Is.EqualTo(8f).Within(0.01f), kind + ": tilt angle");
                Assert.Less(up.z, -0.1f, kind + ": a tilt y below 0 does not lean back");
                Assert.AreEqual(0f, up.x, 1e-4f, kind + ": a tilt y leans sideways");
                Assert.Less((view.Carried.position - view.transform.position).magnitude, 1e-5f, kind + ": the tilt does not pivot on the base");
                view.SetTilt(new Vector2(3f, 4f));
                Assert.That(Quaternion.Angle(Quaternion.identity, view.Carried.localRotation), Is.EqualTo(5f).Within(0.01f), kind + ": a diagonal tilt");
                Assert.AreEqual(new Vector2(3f, 4f), view.Tilt);
                view.SetTilt(Vector2.zero);

                // The fall: the clue on the floor, the carried one hidden.
                Assert.IsFalse(view.ClueActive, kind + ": premise: a clue before the fall");
                Vector3 at = home + chair.transform.right * 0.7f;
                GameObject clue = view.SpawnClue(at);
                Assert.IsNotNull(clue, kind + ": no clue");
                Assert.IsTrue(view.ClueActive && view.Fallen, kind + ": the clue is not active");
                StringAssert.StartsWith(LoadView.CluePrefix, clue.name);
                Assert.IsFalse(clue.transform.IsChildOf(chair.transform), kind + ": the clue rides on the furniture");
                Assert.IsTrue(clue.transform.IsChildOf(Game.Level.Root.transform), kind + ": the clue is not under the level root");
                Assert.IsFalse(view.Carried.GetComponentsInChildren<Renderer>(true).Any(r => r.enabled && r.gameObject.activeInHierarchy),
                    kind + ": the carried load still shows");
                Renderer[] pieces = clue.GetComponentsInChildren<Renderer>(true).Where(r => r.enabled && r.gameObject.activeInHierarchy).ToArray();
                Assert.Greater(pieces.Length, 0, kind + ": the clue draws nothing");
                Assert.IsEmpty(clue.GetComponentsInChildren<Collider>(true), kind + ": the clue carries a collider");
                Bounds b = LoadView.BoundsOf(clue.transform);
                Assert.Less(Planar(b.center, at), 0.3f, kind + ": the clue is not where it fell");
                Assert.Less(b.max.y - at.y, 0.2f, kind + ": the clue stands up instead of lying on the floor");
                Assert.GreaterOrEqual(b.min.y - at.y, -0.002f, kind + ": the clue sinks into the floor");
                Assert.Greater(Mathf.Max(b.size.x, b.size.z), 0.25f, kind + ": the pieces are not scattered");
                Vector3 clueAt = clue.transform.position;
                chair.Teleport(home + chair.transform.right * -0.4f, yaw);
                yield return Steps(2);
                yield return null;
                Assert.Less((clue.transform.position - clueAt).magnitude, 1e-5f, kind + ": the clue moved with the furniture");
                view.ClearClue();
                Assert.IsFalse(view.ClueActive, kind + ": the clue stayed after ClearClue");
                Assert.IsNull(view.Clue);
                yield return null;
                Assert.IsTrue(clue == null, kind + ": the cleared clue was not destroyed");
                view.Restore();
                Assert.IsFalse(view.Fallen);
                Assert.IsTrue(view.Carried.GetComponentsInChildren<Renderer>(true).Any(r => r.enabled && r.gameObject.activeInHierarchy),
                    kind + ": Restore does not show the load");
                Object.Destroy(view.gameObject);
                yield return null;
            }
            Assert.IsNull(LoadView.Create("piano", visual, size), "an unknown kind makes a load");
            logged.RemoveAll(l => l.Contains("[LoadView] no load 'piano'"));
            chair.Teleport(home, yaw);
            yield return Steps(1);
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        // ----- 44x: the clue on a split level (m15) -----

        /// <summary>
        /// Critique m15 (CONTRACT_M5 19): on the floor fixture (a 0.6 m platform 1 m wide, two 2 m ramps), the vase's clue lies
        /// on one floor surface. Dropped at the platform's edge it stays on the platform; dropped beside the platform it stays
        /// on the floor, out of the platform's side; dropped on a ramp it lies on the slope (tilted by the slope, not moved).
        /// Every vertex of every piece lies on or just above the floor under it, never inside it nor floating past an edge.
        /// Each case asserts its premise: a clue laid flat at the caller's point would cross the edge, or the slope there.
        /// </summary>
        [UnityTest]
        public IEnumerator Step44x_ClueLiesOnTheRampAndStaysOnThePlatform()
        {
            yield return Load(FloorLevel);
            FurnitureController chair = Game.Furniture;
            Assert.IsNotNull(chair, "premise: no player furniture");
            FloorMap floor = Game.Def.Floor;
            Assert.IsFalse(floor.IsFlat, "premise: the fixture has a platform");
            Assert.AreSame(floor.Level, chair.Floor.Level, "premise: the furniture stands on the fixture's floor");
            LoadView view = LoadView.Create(LoadView.Vase, chair.Visual, chair.Size);
            Assert.IsNotNull(view, "premise: no vase");
            scratch.Add(view.gameObject);
            float slope = Mathf.Atan2(PlatformHeight, 2f) * Mathf.Rad2Deg;
            var cases = new[]
            {
                (name: "the platform's edge", at: new Vector3(PlatformHalfX - 0.05f, PlatformHeight, -2.2f), height: PlatformHeight, ramp: false),
                (name: "beside the platform", at: new Vector3(-PlatformHalfX - 0.05f, 0f, -2.2f), height: 0f, ramp: false),
                (name: "the ramp", at: new Vector3(-1.5f, PlatformHeight * 0.5f, 0f), height: PlatformHeight * 0.5f, ramp: true),
            };
            foreach (var c in cases)
            {
                Assert.AreEqual(c.height, floor.HeightAt(c.at), 1e-4f, $"{c.name}: premise: the floor height there");
                GameObject clue = view.SpawnClue(c.at);
                Assert.IsNotNull(clue, c.name + ": no clue");
                float spread = 0f;
                float low = float.MaxValue;
                float high = float.MinValue;
                int vertices = 0;
                foreach (MeshFilter f in clue.GetComponentsInChildren<MeshFilter>(true))
                {
                    Matrix4x4 m = f.transform.localToWorldMatrix;
                    foreach (Vector3 v in f.sharedMesh.vertices)
                    {
                        Vector3 p = m.MultiplyPoint3x4(v);
                        float above = p.y - floor.HeightAt(p);
                        low = Mathf.Min(low, above);
                        high = Mathf.Max(high, above);
                        spread = Mathf.Max(spread, Planar(p, clue.transform.position));
                        vertices++;
                    }
                }
                Vector3 rest = clue.transform.position;
                float tilt = Vector3.Angle(Vector3.up, clue.transform.up);
                Debug.Log($"[Step44x] {c.name}: dropped at {c.at}, rests at {rest} ({Planar(rest, c.at):0.000} m away), tilt {tilt:0.0} deg, "
                    + $"spread {spread:0.000} m, vertices from {low:0.000} to {high:0.000} m over the floor");
                Assert.Greater(vertices, 20, c.name + ": premise: the clue's pieces");
                Assert.Greater(spread, 0.2f, c.name + ": premise: the clue is scattered");
                if (c.ramp)
                {
                    // Premise: laid flat there, the uphill pieces would sink into the slope by about spread * tan(slope).
                    Assert.Greater(spread * Mathf.Tan(slope * Mathf.Deg2Rad), 0.05f, c.name + ": premise: the slope under the spread");
                    Assert.Less(Planar(rest, c.at), 1e-3f, c.name + ": the clue moved off a slope it fits on");
                    Assert.AreEqual(slope, tilt, 0.5f, c.name + ": the clue does not lie in the slope's frame");
                }
                else
                {
                    // Premise: laid flat at the caller's point, its spread would cross the platform's edge (x = +-0.5).
                    float edge = c.at.x > 0f ? PlatformHalfX : -PlatformHalfX;
                    Assert.Less(Mathf.Abs(c.at.x - edge), spread, c.name + ": premise: the spread crosses the edge");
                    Assert.AreEqual(c.height, floor.HeightAt(rest), 1e-4f, c.name + ": the clue left the surface it fell on");
                    Assert.AreEqual(c.height, rest.y, 1e-3f, c.name + ": the clue does not rest on that surface");
                    Assert.LessOrEqual(Planar(rest, c.at), Tuning.ClueSearchRadius + 1e-4f, c.name + ": the clue moved too far");
                    Assert.Less(tilt, 0.1f, c.name + ": a clue on a level surface is tilted");
                }
                Assert.GreaterOrEqual(low, -0.005f, c.name + ": a piece sinks into the floor");
                Assert.Less(high, 0.2f, c.name + ": a piece floats over the floor (past an edge)");
                view.ClearClue();
                view.Restore();
                yield return null;
            }
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        // ----- 37w: the floor cone on a split level (m14) -----

        /// <summary>
        /// Critique m14: a watcher on the floor looking across the floor fixture's 0.6 m platform. Its fan's straight
        /// apex-to-rim triangles would pass under the platform (the premise); now every ray is cut every ConeRadialStep, and
        /// at every sampled point of every triangle of its grid the fan lies on or above the floor under it (never inside the
        /// platform; a triangle that joins the end of a ray cut short, by a wall here, to the longer ray beside it may dip a few
        /// centimetres where that end meets a height change, bounded at 0.1 m),
        /// exactly on the platform top over its middle, and exactly on the floor farther than three sample spacings from any
        /// height change (a sample is raised only by the floor within 1.5 spacings). The outline is the M1 fan's. On a flat level
        /// the fan is the M1 fan (one sample per ray, 41 vertices).
        /// </summary>
        [UnityTest]
        public IEnumerator Step37w_ConeFollowsThePlatformTop()
        {
            yield return Load(FloorLevel);
            Inhabitant man = Game.Level.Inhabitants.Single();
            FloorMap floor = Game.Def.Floor;
            Assert.IsFalse(floor.IsFlat, "premise: the fixture has a platform");
            Assert.AreEqual(PlatformHeight, floor.HeightAt(0f, 1f), 1e-4f, "premise: the platform's height");
            var at = new Vector3(-3.2f, 0f, -2.0f);
            yield return PinAndSettle(man, at, 90f);
            Assert.AreEqual(0f, man.Routine.FloorHeight, 1e-4f, "premise: the man stands on the floor");
            VisionConeView cone = ConeOf(man);
            Assert.IsNotNull(cone, "premise: no cone");
            Assert.IsFalse(cone.Hidden, "premise: the cone is hidden");
            int radial = Mathf.CeilToInt(man.Routine.ViewRange / Tuning.ConeRadialStep);
            Assert.AreEqual(radial, cone.Radial, "the rays are not cut every ConeRadialStep of the range");

            // Premise: the central ray crosses the platform, and the M1 apex-to-rim triangle would pass under its top there.
            Vector3[] outline = cone.Vertices;
            int n = outline.Length - 1;
            Vector3 apex = outline[0];
            Vector3 rim = outline[1 + n / 2];
            Assert.Greater(rim.x, PlatformHalfX + 0.5f, "premise: the central ray does not cross the platform");
            float chord = Mathf.Lerp(apex.y, rim.y, (0f - apex.x) / (rim.x - apex.x));
            Assert.Less(chord, PlatformHeight - 0.3f, "premise: an apex-to-rim triangle would not pass under the platform");
            Assert.AreEqual(FloorLift, apex.y, 1e-4f, "the apex is not on the floor");

            Mesh mesh = cone.FanMesh;
            Vector3[] v = mesh.vertices;
            int[] t = mesh.triangles;
            Assert.AreEqual(1 + n * radial, v.Length, "the mesh's vertices");
            // The outline is the M1 fan's: each ray's last sample is its rim, at the ray's reach, and its samples run along it.
            for (int i = 0; i < n; i++)
            {
                Vector3 dir = YawMath.Forward(man.VisualEyeYaw - cone.HalfAngle + 2f * cone.HalfAngle * i / (n - 1));
                float reach = cone.RayReach(man.VisualEyePosition, dir, cone.Range, floor);
                Assert.AreEqual(reach, Planar(outline[1 + i], apex), 1e-3f, $"ray {i}: the rim is not at the ray's reach");
                Assert.Less(Planar(v[cone.MeshIndex(i, radial)], outline[1 + i]), 1e-4f, $"ray {i}: the last sample is not the rim");
                for (int s = 1; s <= radial; s++)
                {
                    Vector3 q = v[cone.MeshIndex(i, s)];
                    Assert.Less(Vector3.Cross(dir, YawMath.Planar(q - apex)).magnitude, 1e-3f, $"ray {i} sample {s} is off its ray");
                }
            }
            var weights = new[]
            {
                new Vector3(1f / 3f, 1f / 3f, 1f / 3f), new Vector3(0.6f, 0.2f, 0.2f), new Vector3(0.2f, 0.6f, 0.2f), new Vector3(0.2f, 0.2f, 0.6f),
                new Vector3(0.45f, 0.45f, 0.1f), new Vector3(0.1f, 0.45f, 0.45f), new Vector3(0.45f, 0.1f, 0.45f),
            };
            // A regular sample advanced along its ray; a repeated rim (a ray cut short) does not. The triangles of regular
            // samples make the fan's grid; a triangle that joins a repeated rim spans to the longer ray beside it.
            var regular = new bool[v.Length];
            regular[0] = true;
            for (int i = 0; i < n; i++)
            {
                for (int s = 1; s <= radial; s++)
                {
                    int k = cone.MeshIndex(i, s);
                    regular[k] = cone.SampleDistance(k) > (s - 1) * cone.Spacing + 1e-4f;
                }
            }
            float worstEdge = 0f;
            int edgeTriangles = 0;
            float worstUnder = 0f;
            Vector3 worstAt = default;
            float worstTop = 0f;
            float worstFlat = 0f;
            int onTop = 0;
            int onFlat = 0;
            int samples = 0;
            for (int i = 0; i + 2 < t.Length; i += 3)
            {
                bool grid = regular[t[i]] && regular[t[i + 1]] && regular[t[i + 2]];
                edgeTriangles += grid ? 0 : 1;
                foreach (Vector3 w in weights)
                {
                    Vector3 p = v[t[i]] * w.x + v[t[i + 1]] * w.y + v[t[i + 2]] * w.z;
                    float ground = floor.HeightAt(p.x, p.z);
                    float under = ground + FloorLift - p.y;
                    if (!grid)
                    {
                        worstEdge = Mathf.Max(worstEdge, under);
                    }
                    else if (under > worstUnder)
                    {
                        worstUnder = under;
                        worstAt = p;
                    }
                    samples++;
                    if (Mathf.Abs(p.x) <= PlatformHalfX - 0.3f && Mathf.Abs(p.z) < 2.8f)
                    {
                        onTop++;
                        worstTop = Mathf.Max(worstTop, Mathf.Abs(p.y - (PlatformHeight + FloorLift)));
                    }
                    float d = Planar(p, apex);
                    if (FlatAround(floor, p, 3f * Mathf.Max(cone.Spacing, d * cone.RayStep)))
                    {
                        onFlat++;
                        worstFlat = Mathf.Max(worstFlat, Mathf.Abs(p.y - (ground + FloorLift)));
                    }
                }
            }
            Debug.Log($"[Step37w] cone over the platform: {radial} samples per ray, {v.Length} vertices, {t.Length / 3} triangles; "
                + $"{samples} points: worst {worstUnder:0.0000} m under the floor (at {worstAt}), {onTop} on the platform top (off by {worstTop:0.0000}), "
                + $"{onFlat} on flat floor (off by {worstFlat:0.0000}); {edgeTriangles} triangles join a ray cut short, worst {worstEdge:0.0000} m under");
            Assert.Greater(onTop, 20, "premise: few points of the fan over the platform's middle");
            Assert.Greater(onFlat, 200, "premise: few points of the fan on flat floor");
            Assert.LessOrEqual(worstUnder, 0.003f, $"the fan passes {worstUnder:0.000} m under the floor at {worstAt}");
            Assert.LessOrEqual(worstEdge, 0.1f, $"a triangle joining a ray cut short passes {worstEdge:0.000} m under the floor");
            Assert.LessOrEqual(worstTop, 0.003f, "the fan is not on the platform top over its middle");
            Assert.LessOrEqual(worstFlat, 0.003f, "the fan floats over flat floor");

            // A flat level keeps the M1 fan.
            yield return Load(DogLevel);
            VisionConeView flat = Game.Level.Cones.First(c => c != null);
            Assert.AreEqual(1, flat.Radial, "a flat level cuts its rays");
            Assert.AreEqual(Tuning.ConeRayCount + 1, flat.FanMesh.vertexCount, "a flat level's fan is not the M1 fan");
            Assert.AreEqual((Tuning.ConeRayCount - 1) * 3, flat.FanMesh.triangles.Length, "a flat level's fan triangles");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        /// <summary>True when the floor is level within <paramref name="radius"/> of <paramref name="p"/> (a 5 x 5 grid).</summary>
        private static bool FlatAround(FloorMap floor, Vector3 p, float radius)
        {
            float h = floor.HeightAt(p.x, p.z);
            for (int i = -2; i <= 2; i++)
            {
                for (int j = -2; j <= 2; j++)
                {
                    if (Mathf.Abs(floor.HeightAt(p.x + radius * i / 2f, p.z + radius * j / 2f) - h) > 1e-4f)
                    {
                        return false;
                    }
                }
            }
            return true;
        }

        // ----- 38w: the dog's fan is a superset of what it sees (m20) -----

        /// <summary>
        /// Critique m20: the dog's eye (0.35 m) is below the chair's top (0.87 m), so behind the cover fixture's 0.5 m low wall
        /// it sees a chair's top up to about 4.5 m away while its far ray (aimed at the top 6 m away) hits the wall at 1.3 m
        /// (the premise). Along every ray of every fan (the dog's, and a human's as the control), no furniture top in its cone
        /// is seen farther than the ray reaches; a 1.8 m wardrobe still ends the rays it covers; and every chair placed in the
        /// room with any sample seen has a seen sample inside (or within 0.3 m of) the fan.
        /// </summary>
        [UnityTest]
        public IEnumerator Step38w_DogFanCoversWhatItSees()
        {
            yield return Load(CoverLevel);
            Inhabitant dog = Game.Level.Inhabitants.Single(h => h.IsDog);
            Inhabitant human = Game.Level.Inhabitants.Single(h => !h.IsDog);
            Assert.IsFalse(dog.Routine.Asleep, "premise: the dog is awake");
            yield return PinAndSettle(dog, new Vector3(0f, 0f, -3.5f), 0f);
            yield return PinAndSettle(human, new Vector3(-4.5f, 0f, -3.5f), 0f);
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: the level ended");
            Vector3 eye = dog.Routine.EyePosition;
            Assert.AreEqual(Tuning.DogEyeHeight, eye.y, 1e-4f, "premise: the dog's eye");
            VisionConeView dogCone = ConeOf(dog);
            float top = dogCone.TargetHeight;
            Assert.Greater(top, eye.y + 0.3f, "premise: the dog looks up at the chair's top");

            // Premise: the far ray of the M1 fan stops on the low wall.
            Vector3 far = new Vector3(eye.x, top, eye.z + dogCone.Range);
            Assert.IsTrue(Physics.Raycast(eye, (far - eye).normalized, out RaycastHit wall, (far - eye).magnitude, Layers.OccluderMask,
                QueryTriggerInteraction.Ignore), "premise: the far ray clears the low wall");
            Assert.Less(Planar(wall.point, eye), 1.5f, "premise: the far ray does not stop on the low wall");
            Vector3 behind = new Vector3(0f, top, -0.5f);
            Assert.IsTrue(VisionMath.IsInCone(eye, dog.Routine.EyeForward, behind, dogCone.Range, dogCone.HalfAngle) && !Vision.Occluded(eye, behind),
                "premise: the dog does not see a chair top 3 m away behind the low wall");

            int checkedRays = 0;
            int seenBeyondOldReach = 0;
            foreach (Inhabitant h in new[] { dog, human })
            {
                VisionConeView cone = ConeOf(h);
                Assert.IsFalse(cone.Hidden, $"premise: {h.name}'s cone is hidden");
                Vector3 e = h.Routine.EyePosition;
                Vector3 forward = h.Routine.EyeForward;
                Vector3[] fan = cone.Vertices;
                int n = fan.Length - 1;
                float half = cone.HalfAngle;
                float range = cone.Range;
                float worst = 0f;
                string worstRay = null;
                for (int i = 0; i < n; i++)
                {
                    Vector3 dir = YawMath.Forward(h.VisualEyeYaw - half + 2f * half * i / (n - 1));
                    float reach = Planar(fan[1 + i], fan[0]);
                    float farthest = 0f;
                    for (float d = 0.2f; d <= range; d += 0.05f)
                    {
                        Vector3 q = new Vector3(e.x, 0f, e.z) + dir * d;
                        q.y = Game.Def.Floor.HeightAt(q.x, q.z) + cone.TargetHeight;
                        if (Physics.CheckBox(new Vector3(q.x, 0.5f, q.z), new Vector3(0.05f, 0.5f, 0.05f), Quaternion.identity, Layers.OccluderMask))
                        {
                            continue; // inside a prop or a wall: no furniture stands there
                        }
                        if (VisionMath.IsInCone(e, forward, q, range, half) && !Vision.Occluded(e, q))
                        {
                            farthest = d;
                        }
                    }
                    if (h == dog && farthest > 2f && Mathf.Abs(dir.x * 2f) < 1.3f)
                    {
                        seenBeyondOldReach++;
                    }
                    if (farthest - reach > worst)
                    {
                        worst = farthest - reach;
                        worstRay = $"ray {i}: a top seen at {farthest:0.00} m, the fan reaches {reach:0.00} m";
                    }
                    checkedRays++;
                }
                Debug.Log($"[Step38w] {h.name}: worst shortfall {worst:0.000} m ({worstRay ?? "none"})");
                Assert.LessOrEqual(worst, 0.06f, $"{h.name}'s fan ends short of a top it sees: {worstRay}");
            }
            Assert.AreEqual(2 * Tuning.ConeRayCount, checkedRays, "premise: every ray checked");
            Assert.Greater(seenBeyondOldReach, 3, "premise: the dog sees few tops behind the low wall");

            // The wardrobe (taller than the top) still ends the dog's rays it covers.
            Vector3 toWardrobe = new Vector3(3f, 0f, 0.5f) - YawMath.Planar(eye);
            Assert.Less(toWardrobe.magnitude, dogCone.Range - 0.5f, "premise: the wardrobe is in the dog's range");
            float wardrobeReach = dogCone.RayReach(eye, toWardrobe.normalized, dogCone.Range, Game.Def.Floor);
            Debug.Log($"[Step38w] the ray at the wardrobe's centre ({toWardrobe.magnitude:0.00} m) reaches {wardrobeReach:0.00} m");
            Assert.Less(wardrobeReach, toWardrobe.magnitude - 0.1f, "a ray at the 1.8 m wardrobe goes past its near face");

            // Real chairs: whenever a sample is seen, a seen sample lies in the fan.
            var samples = new Vector3[Tuning.SampleCount];
            var visible = new bool[Tuning.SampleCount];
            Vector3 chairSize = Game.Furniture.Size;
            int seenChairs = 0;
            float worstChair = 0f;
            string worstChairAt = null;
            foreach (Inhabitant h in new[] { dog, human })
            {
                VisionConeView cone = ConeOf(h);
                for (float x = -5.5f; x <= 5.5f; x += 0.25f)
                {
                    for (float z = -4.6f; z <= 4.6f; z += 0.25f)
                    {
                        var at = new Vector3(x, 0f, z);
                        if (Physics.CheckBox(at + Vector3.up * (chairSize.y * 0.5f), chairSize * 0.5f, Quaternion.identity, Layers.OccluderMask))
                        {
                            continue;
                        }
                        VisionMath.SamplePoints(at, 0f, chairSize, Tuning.SampleInset, samples);
                        if (!Vision.Test(h.Routine.EyePosition, h.Routine.EyeForward, samples, cone.Range, cone.HalfAngle, visible))
                        {
                            continue;
                        }
                        seenChairs++;
                        float best = float.MaxValue;
                        for (int s = 0; s < samples.Length; s++)
                        {
                            if (visible[s])
                            {
                                best = Mathf.Min(best, DistanceToFan(cone.Vertices, samples[s]));
                            }
                        }
                        if (best > worstChair)
                        {
                            worstChair = best;
                            worstChairAt = $"{h.name}, chair at ({x:0.00}, {z:0.00})";
                        }
                    }
                }
            }
            Debug.Log($"[Step38w] {seenChairs} chairs seen; the worst lies {worstChair:0.000} m outside the fan ({worstChairAt ?? "none"})");
            Assert.Greater(seenChairs, 100, "premise: few chairs seen");
            Assert.LessOrEqual(worstChair, 0.3f, $"a seen chair lies {worstChair:0.00} m outside the fan ({worstChairAt})");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        /// <summary>The planar distance from <paramref name="p"/> to the fan (apex and rim): 0 inside.</summary>
        private static float DistanceToFan(Vector3[] fan, Vector3 p)
        {
            var q = new Vector2(p.x, p.z);
            var a = new Vector2(fan[0].x, fan[0].z);
            float best = float.MaxValue;
            for (int i = 1; i + 1 < fan.Length; i++)
            {
                var b = new Vector2(fan[i].x, fan[i].z);
                var c = new Vector2(fan[i + 1].x, fan[i + 1].z);
                best = Mathf.Min(best, DistanceToTriangle(q, a, b, c));
                if (best <= 0f)
                {
                    return 0f;
                }
            }
            return best;
        }

        private static float DistanceToTriangle(Vector2 p, Vector2 a, Vector2 b, Vector2 c)
        {
            float d1 = Cross(b - a, p - a);
            float d2 = Cross(c - b, p - b);
            float d3 = Cross(a - c, p - c);
            bool negative = d1 < 0f || d2 < 0f || d3 < 0f;
            bool positive = d1 > 0f || d2 > 0f || d3 > 0f;
            if (!(negative && positive))
            {
                return 0f;
            }
            return Mathf.Min(Segment(p, a, b), Mathf.Min(Segment(p, b, c), Segment(p, c, a)));
        }

        private static float Cross(Vector2 u, Vector2 w) => u.x * w.y - u.y * w.x;

        private static float Segment(Vector2 p, Vector2 a, Vector2 b)
        {
            Vector2 ab = b - a;
            float t = ab.sqrMagnitude > 1e-12f ? Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude) : 0f;
            return (p - (a + ab * t)).magnitude;
        }

        // ----- 37x: unmerged character slots (CONTRACT_M5 17 and 19) -----

        /// <summary>
        /// CONTRACT_M5 19 (m4: the character slot merge is removed): the people fixture with the three humans of the most slots
        /// (watchful, teen, tidy) and the dog. Every character draws its catalog prefab's own skinned mesh with exactly the
        /// prefab's slots (none merged, none dropped), the clothes take the tint alone, and the level still holds its draw call
        /// budget (material slots), counted here independently of the probe.
        /// </summary>
        [UnityTest]
        public IEnumerator Step37x_CharacterSlotsAreTheCatalogSlotsWithinTheBudget()
        {
            string[] worst = { PersonalityDef.Watchful, PersonalityDef.Teen, PersonalityDef.Tidy };
            yield return Load(PeopleLevel);
            List<InhabitantDef> humans = Game.Def.Inhabitants.Where(d => d.Kind != PersonalityDef.Dog).ToList();
            Assert.AreEqual(3, humans.Count, "premise: three humans");
            for (int i = 0; i < humans.Count; i++)
            {
                humans[i].Personality = worst[i];
            }
            Game.Restart();
            Game.Rules = GameRules.M1;
            yield return Steps(2);
            yield return null;
            Assert.AreEqual(4, Game.Level.Inhabitants.Count, "premise: three humans and the dog");
            var perCharacter = new List<string>();
            int characterSlots = 0;
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                Assert.IsNotNull(h.Rig, $"premise: {h.name} shows no model");
                Assert.IsTrue(h.Tint.HasValue, $"premise: {h.name} has no tint");
                SkinnedMeshRenderer skin = h.Rig.Skin;
                SkinnedMeshRenderer prefab = h.Rig.Entry.prefab.GetComponentInChildren<SkinnedMeshRenderer>(true);
                Assert.IsNotNull(skin, $"premise: {h.name} is not skinned");
                Assert.IsNotNull(prefab, $"premise: {h.name}'s catalog prefab is not skinned");
                if (h.Rig.IsPet)
                {
                    Assert.AreSame(prefab.sharedMesh, skin.sharedMesh, $"{h.name} does not draw the catalog prefab's mesh");
                }
                else
                {
                    Assert.IsTrue(CharacterLook.UsesProjection(prefab.sharedMesh, skin.sharedMesh), $"{h.name} uses the wrong projected mesh");
                }
                Assert.AreEqual(prefab.sharedMaterials.Length, skin.sharedMaterials.Length, $"{h.name}: slots merged or dropped");
                Assert.AreEqual(skin.sharedMesh.subMeshCount, skin.sharedMaterials.Length, $"{h.name}: slots and submeshes differ");
                Material tint = PrimitiveKit.Lit(h.Tint.Value);
                int clothes = 0;
                foreach ((Renderer r, int slot, string name) in ModelKit.SourceSlots(h.Rig.Model, h.Rig.Entry))
                {
                    bool isClothes = ModelKit.PartOf(name, h.Rig.Entry.IsPet) == ModelKit.CharacterPart.Clothes;
                    clothes += isClothes ? 1 : 0;
                    Assert.AreEqual(isClothes, r.sharedMaterials[slot] == tint, $"{h.name}: {name} and the tint");
                }
                Assert.Greater(clothes, 0, $"premise: {h.name} has a clothes slot");
                int slots = ModelKit.SlotsUnder(h.transform);
                characterSlots += slots;
                perCharacter.Add(h.Personality.Id + " " + slots);
            }
            Renderer[] drawn = Game.Level.Root.GetComponentsInChildren<Renderer>(false);
            int slotsHere = drawn.Where(r => r.enabled && r.gameObject.activeInHierarchy).Sum(r => r.sharedMaterials.Length);
            bool house = Game.Def.AllRooms().Count >= Tuning.HouseBudgetRooms;
            int budget = house ? Tuning.BudgetHouseRenderers : Tuning.BudgetRenderers;
            Debug.Log($"[Step37x] watchful, teen, tidy and the dog: {characterSlots} character slots ({string.Join(", ", perCharacter)}); "
                + $"level draw calls {slotsHere} of {budget}");
            Assert.AreEqual(slotsHere, Probe.CountRenderers(drawn).MaterialSlots, "Probe.CountRenderers does not count every slot");
            Assert.LessOrEqual(slotsHere, budget, "the level's draw calls (material slots) exceed the budget");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }
    }
}
