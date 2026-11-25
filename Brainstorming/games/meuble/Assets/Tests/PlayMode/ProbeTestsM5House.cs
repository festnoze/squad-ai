using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// The M5 house probe, wave 5A (docs/CONTRACT_M5_v3.md 15.1 to 15.4 and 15.8, CONTRACT_M5.md 16.6 and 16.11), on the real
    /// Boot scene with the house's test levels.
    /// <list type="bullet">
    /// <item>Step 36 and 36l to 36n (doors, test_m5_house_door): the leaf poses, the collider and occlusion swap, the samples
    /// on all 30 steps of the swing, the leaf never moving with its wall (M9 doors rule), the area-mask paths over the one NavMesh.</item>
    /// <item>Step 36o (level 8, wave 5A.1; DOORFADE): an open leaf between the camera and the chair stays drawn while its wall stands (no box rule).</item>
    /// <item>Step 39 and 39e to 39g (the split level, test_m5_house_split): the ramp is climbable and the railing blocks; eyes,
    /// samples and plans add the floor height; a chair on the platform behind its edge is hidden from a low eye below.</item>
    /// <item>Step 39h: the renderer combining of the level builder on every manifest level and the 8 room mock, before and
    /// after; the PRD 7.4 draw call budgets counted as material slots on every manifest level and on the 8 room mock
    /// (CONTRACT_M5 16.11 and 17; wave 5B cut the mock under the house budget: bookshelves, shared baseboards and faces, panes).</item>
    /// <item>Step 43r (wave 5B): the procedural rocking chair (CONTRACT_M5 5).</item>
    /// <item>Step 39l (wave 5B, test_m5_house_robot): the robot and the load build with the level (one Robot per RobotDef with
    /// its path, on the floor, no collider; one LoadView on the furniture's Visual; the cones aim at the load's top), a restart
    /// rebuilds exactly one of each, and a rocking chair player and decoy build their procedural visual.</item>
    /// <item>Step 39i: the camera's zoom bound; step 39j: the mock house's inhabitants (personality models, the shared seat
    /// registry, frozen station walks with the authored leaves) and every station walk its patterns produce.</item>
    /// </list>
    /// Leaf swings are stepped here, synchronously within one frame, so nothing else steps them in between. Every wait counts
    /// game fixed steps (GameState.FixedStepped) under a real time guard, never rendered frames, and every scenario asserts
    /// its premise first.
    /// </summary>
    public sealed class ProbeTestsM5House
    {
        private const float Dt = Tuning.FixedStep;
        // v3 15.4: the CharacterController rests a few centimetres above its floor once it moved.
        private const float FloorTolerance = 0.05f;
        private const string DoorLevel = "test_m5_house_door";
        private const string SplitLevel = "test_m5_house_split";
        private const string MockLevel = "test_m5_house_mock8";
        private const string RobotLevel = "test_m5_house_robot";
        private const float PlatformHeight = 0.8f;

        private static int DoorSteps => Mathf.RoundToInt(Tuning.DoorOpenTime / Dt);

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;

        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            fixedSteps = 0;
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
            Game.Rules = GameRules.M4;
            Game.FixedStepped += Record;
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            LevelBuilder.CombineRenderers = true;
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.FixedStepped -= Record;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                    main.Game.Furniture.ScriptedCareful = null;
                }
            }
            yield return null;
        }

        private void Record()
        {
            fixedSteps++;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        private void AssertClean()
        {
            Assert.AreEqual(0, exceptions, "errors were logged: " + string.Join(" | ", logged));
        }

        private IEnumerator Steps(int count)
        {
            yield return Until(null, count);
        }

        /// <summary>Waits until <paramref name="until"/> holds after a fixed step, at most <paramref name="maxSteps"/> game steps.</summary>
        private IEnumerator Until(Func<bool> until, int maxSteps)
        {
            int end = fixedSteps + maxSteps;
            float realStart = Time.realtimeSinceStartup;
            while (fixedSteps < end && (until == null || !until()) && Time.realtimeSinceStartup - realStart < 120f)
            {
                yield return new WaitForFixedUpdate();
            }
            Assert.Less(Time.realtimeSinceStartup - realStart, 120f, "the game stopped stepping");
        }

        private IEnumerator Load(string id)
        {
            Game.LoadLevel(id);
            Assert.AreEqual(id, Game.Def.Id, "premise: the level loaded");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: playing");
            yield return Steps(2);
        }

        /// <summary>Freezes the first inhabitant at its first station, facing the way the fixture has it (away from the tests).</summary>
        private void PinAway()
        {
            StationDef s = Game.Def.Inhabitants[0].Stations[0];
            Game.MainInhabitant.Pin(s.Position, s.Facing);
        }

        private static void AssertPose(Transform t, Pose pose, string what)
        {
            Assert.Less((t.position - pose.position).magnitude, 1e-3f, $"{what}: position {t.position} instead of {pose.position}");
            Assert.Less(Quaternion.Angle(t.rotation, pose.rotation), 0.1f, $"{what}: rotation");
        }

        /// <summary>Steps a leaf through its whole swing within this frame; returns the number of steps.</summary>
        private static int Swing(DoorLeaf leaf, Action<DoorLeaf> eachStep = null)
        {
            int steps = 0;
            while (leaf.Swinging && steps < 1000)
            {
                leaf.Step(Dt);
                steps++;
                eachStep?.Invoke(leaf);
            }
            return steps;
        }

        // ----- 36: leaves (CONTRACT_M5_v3 15.1, 15.2) -----

        // test_m5_house_door: rooms a (x < 0) and b (x > 0) joined only by the closed leaf "porte" at (0, 0.25), hinged at
        // z = -0.25 and swinging into b; b and c joined by the leaf "ouverte", authored open.
        private static readonly Vector3 EyeInA = new Vector3(-1.5f, 1.2f, 0.25f);
        private static readonly Vector3 PointInB = new Vector3(1.5f, 0.8f, 0.25f);
        // A sight line in b that crosses the open pose of "porte" (x in [0, 1] at z = -0.25).
        private static readonly Vector3 SideFrom = new Vector3(0.5f, 1.0f, -1.5f);
        private static readonly Vector3 SideTo = new Vector3(0.5f, 1.0f, 1.0f);

        [UnityTest]
        public IEnumerator Step36_LeafPosesAndTheColliderAndOcclusionSwap()
        {
            yield return Load(DoorLevel);
            PinAway();
            LevelInstance level = Game.Level;
            Assert.AreEqual(2, level.Leaves.Count, "premise: the fixture has two leaves");
            DoorLeaf porte = level.Leaves[0];
            DoorLeaf ouverte = level.Leaves[1];
            Assert.AreEqual("porte", porte.Id);
            Assert.AreEqual("ouverte", ouverte.Id);
            Assert.AreEqual(Tuning.DoorAreaBase, porte.Area, "leaf 0 uses the first door area");
            Assert.AreEqual(Tuning.DoorAreaBase + 1, ouverte.Area, "leaf 1 the next one");

            // Closed: in its closed pose, a collider on the Occluder layer, no samples.
            Assert.IsFalse(porte.Open || porte.Swinging, "premise: porte starts closed");
            Pose closed = porte.Geometry.Pose(0f, out Vector3 size);
            AssertPose(porte.transform, closed, "closed leaf");
            AssertPose(porte.Collider.transform, closed, "closed collider");
            Assert.AreEqual(Layers.Occluder, porte.Collider.gameObject.layer, "the leaf is an occluder");
            Assert.IsTrue(porte.Collider.enabled && porte.Collider.gameObject.activeInHierarchy, "the closed leaf has its collider");
            Assert.Less((porte.Collider.size - size).magnitude, 1e-4f, "the collider is the leaf box");
            Assert.AreEqual(0, porte.Samples.Length, "a closed leaf has no samples");
            Assert.IsTrue(Vision.Occluded(EyeInA, PointInB), "the closed leaf hides room b from room a through its doorway");
            Assert.IsFalse(Vision.Occluded(SideFrom, SideTo), "premise: nothing stands yet where the open leaf will");

            // Authored open: in its open pose, still a collider and an occluder, no samples.
            Assert.IsTrue(ouverte.Open && !ouverte.Swinging, "ouverte is authored open");
            AssertPose(ouverte.transform, ouverte.Geometry.Pose(Tuning.DoorSwingDegrees, out Vector3 _), "authored open leaf");
            AssertPose(ouverte.Collider.transform, ouverte.Geometry.Pose(Tuning.DoorSwingDegrees, out Vector3 _), "authored open collider");
            Assert.IsTrue(ouverte.Collider.enabled, "an open leaf keeps its collider");
            Assert.AreEqual(0, ouverte.Samples.Length, "an open leaf has no samples");

            // The swing: 30 steps, the collider and the samples follow the angle. The leaf is sampled on all 30 steps of its
            // swing, the 30th at the open angle; the swing ends at the start of the next step (v3 15.2, wave 5A.1 m5).
            porte.BeginOpen();
            Assert.IsTrue(porte.Open && porte.Swinging, "BeginOpen starts the swing");
            Assert.AreEqual(Tuning.LeafSampleCount, porte.Samples.Length, "the samples join from the start of the swing");
            var swinging = new List<bool>();
            var sampled = new List<int>();
            var angles = new List<float>();
            int steps = Swing(porte, leaf =>
            {
                swinging.Add(leaf.Swinging);
                sampled.Add(leaf.Samples.Length);
                angles.Add(leaf.Angle);
                Pose now = leaf.Geometry.Pose(leaf.Angle, out Vector3 _);
                AssertPose(leaf.transform, now, $"leaf at {leaf.Angle:0.#} deg");
                AssertPose(leaf.Collider.transform, now, $"collider at {leaf.Angle:0.#} deg");
                if (leaf.Swinging)
                {
                    Vector3[] expected = leaf.Geometry.Samples(leaf.Angle);
                    Assert.AreEqual(Tuning.LeafSampleCount, leaf.Samples.Length, "4 samples during the swing");
                    for (int i = 0; i < expected.Length; i++)
                    {
                        Assert.Less((leaf.Samples[i] - expected[i]).magnitude, 1e-4f, $"sample {i} at {leaf.Angle:0.#} deg");
                    }
                }
            });
            Assert.AreEqual(DoorSteps + 1, steps, "the swing lasts DoorOpenTime in fixed steps and ends at the start of the next one");
            for (int k = 0; k < DoorSteps; k++)
            {
                Assert.IsTrue(swinging[k], $"porte is not swinging after swing step {k + 1}");
                Assert.AreEqual(Tuning.LeafSampleCount, sampled[k], $"porte has no samples on swing step {k + 1}");
            }
            Assert.AreEqual(Tuning.DoorSwingDegrees, angles[DoorSteps - 1], 1e-3f, "the 30th swing step reaches the open angle");
            Assert.Less(angles[DoorSteps - 2], Tuning.DoorSwingDegrees - 1f, "premise: the 29th swing step is short of the open angle");
            Assert.IsFalse(swinging[DoorSteps], "the swing did not end at the start of the step after the 30th");
            Assert.AreEqual(0, sampled[DoorSteps], "the leaf keeps its samples after its 30 swing steps");
            Assert.IsTrue(porte.Open && !porte.Swinging, "open after the swing");
            Assert.AreEqual(Tuning.DoorSwingDegrees, porte.Angle, 1e-3f);
            Assert.AreEqual(DoorSteps, porte.SwingSteps, "the step that ends the swing is not a swing step");
            Assert.AreEqual(0, porte.Samples.Length, "an open leaf has no samples");

            // Open: the collider stands in the open pose and still occludes there; the doorway is clear.
            Pose open = porte.Geometry.Pose(Tuning.DoorSwingDegrees, out Vector3 _);
            AssertPose(porte.Collider.transform, open, "open collider");
            Assert.IsTrue(porte.Collider.enabled, "an open leaf keeps its collider");
            Assert.IsFalse(Vision.Occluded(EyeInA, PointInB), "the open leaf no longer hides the doorway");
            Assert.IsTrue(Vision.Occluded(SideFrom, SideTo), "the open leaf occludes in its open pose");
            Assert.IsTrue(Physics.CheckBox(open.position, new Vector3(0.3f, 0.3f, 0.01f), open.rotation, Layers.ChairBlockerMask,
                QueryTriggerInteraction.Ignore), "the open leaf blocks the player in its open pose");

            // A leaf never closes again and BeginOpen does nothing on an open leaf.
            porte.BeginOpen();
            Assert.IsFalse(porte.Swinging, "BeginOpen on an open leaf does nothing");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step36l_LeafMovesOnlyWithItsWall()
        {
            yield return Load(DoorLevel);
            LevelInstance level = Game.Level;
            var fader = level.Root.GetComponent<WallFader>();
            Assert.IsNotNull(fader, "premise: the level has its wall fader");
            DoorLeaf porte = level.Leaves[0];
            DoorLeaf ouverte = level.Leaves[1];
            Assert.Greater(Chair.transform.position.x, 0.1f, "premise: the player is in room b (x > 0)");
            Assert.Less(Chair.transform.position.z, 2f, "premise: the player is in room b (z < 2.05)");
            ShadowCastingMode shown = ShadowCastingMode.On;
            Assert.AreEqual(Layers.Occluder, porte.Renderer.gameObject.layer, "premise: the leaf is drawn on the Occluder layer");
            SaveOptions o = SaveStore.Options;
            // DOORFADE (2026-11-24, replaces the M9 doors rule): a door leaf goes out of the way exactly when its wall's plane
            // separates the camera from the player (any look but off), and never for its box alone.
            Vector3[] eyes = { new Vector3(-3f, 2.5f, 0.25f), new Vector3(3f, 2.5f, 0.25f), new Vector3(-3f, 2.5f, 3f), new Vector3(2f, 2.5f, 5f) };
            Vector3 player = fader.Target.position;
            bool Separated(DoorLeaf leaf, Vector3 eye)
            {
                Assert.IsTrue(fader.PlaneOf(leaf.Renderer, out Vector3 lp, out Vector3 ln), "premise: the leaf is registered with its wall");
                return Vector3.Dot(eye - lp, ln) * Vector3.Dot(player - lp, ln) < 0f;
            }
            foreach (string walls in new[] { SaveOptions.WallsLowered, SaveOptions.WallsSeeThrough, SaveOptions.WallsBoth, SaveOptions.WallsNone })
            {
                SaveStore.SetOptions(new SaveOptions
                {
                    Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty,
                    Language = o.Language, Walls = walls, WallOpacity = o.WallOpacity,
                });
                for (int open = 0; open < 2; open++)
                {
                    foreach (Vector3 eye in eyes)
                    {
                        fader.Apply(eye);
                        bool off = walls == SaveOptions.WallsNone;
                        bool porteGoes = !off && Separated(porte, eye);
                        bool ouverteGoes = !off && Separated(ouverte, eye);
                        Assert.AreEqual(porteGoes ? ShadowCastingMode.ShadowsOnly : shown, porte.Renderer.shadowCastingMode,
                            $"{walls}: the leaf does not follow its wall for the camera at {eye} (open {open})");
                        Assert.AreEqual(ouverteGoes ? ShadowCastingMode.ShadowsOnly : shown, ouverte.Renderer.shadowCastingMode,
                            $"{walls}: the open leaf does not follow its wall for the camera at {eye}");
                        Assert.AreEqual(porteGoes ? 0f : 1f, fader.LevelOf(porte.Renderer), 1e-4f, $"{walls}: the leaf level at {eye}");
                    }
                    if (open == 0 && !porte.Open)
                    {
                        porte.BeginOpen();
                        Swing(porte);
                    }
                }
            }
            // The wall it stands in still moves: the camera in a, the player in b, the cap of the wall x = 0 is out of the way.
            bool wallMoved = false;
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty,
                Language = o.Language, Walls = SaveOptions.WallsSeeThrough, WallOpacity = o.WallOpacity,
            });
            foreach (MeshRenderer r in level.Root.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (r.name == "Cap" && fader.PlaneOf(r, out Vector3 point, out Vector3 normal) && Mathf.Abs(Mathf.Abs(normal.x) - 1f) < 1e-3f
                    && Mathf.Abs(point.x) < 0.01f)
                {
                    fader.Apply(eyes[0]);
                    wallMoved |= r.shadowCastingMode == ShadowCastingMode.ShadowsOnly;
                }
            }
            Assert.IsTrue(wallMoved, "the wall x = 0 no longer gets out of the way around its leaf");
            SaveStore.SetOptions(o);
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step36m_AreaMaskPathsOverTheOneNavMesh()
        {
            yield return Load(DoorLevel);
            LevelInstance level = Game.Level;
            var nav = level.Planner as NavPlanner;
            Assert.IsNotNull(nav, "premise: the level plans on its NavMesh");
            Assert.IsTrue(nav.HasData, "premise: the NavMesh is built");
            int triangles = NavPlanner.CountTriangles();
            DoorLeaf porte = level.Leaves[0];
            var corners = new List<Vector3>();
            var inA = new Vector3(-2.05f, 0f, 0.25f);
            var inB = new Vector3(2.05f, 0f, -0.75f);
            var inC = new Vector3(2.05f, 0f, 4.5f);

            int doorBit = 1 << Tuning.DoorAreaBase;
            Assert.AreEqual(1 << 1, level.OpenMask, "only the authored open leaf is open");
            Assert.AreEqual(RoutineFactory.AllAreas & ~doorBit, level.AreaMask(), "the closed leaf's area is out of the mask");
            Assert.IsTrue(nav.TryPlan(inA, inB, corners, NavMesh.AllAreas), "premise: with every area, the doorway joins a and b");
            Assert.IsFalse(nav.TryPlan(inA, inB, corners, level.AreaMask()), "a closed leaf blocks the plan");
            Assert.IsFalse(level.PlannerFor(level.OpenMask).TryPlan(inA, inB, corners), "PlannerFor the current leaves: blocked");
            Assert.IsTrue(level.PlannerFor(0b11).TryPlan(inA, inB, corners), "PlannerFor a mask with porte open: allowed");
            Assert.IsTrue(level.PlannerFor(level.OpenMask).TryPlan(inB, inC, corners), "an open leaf's doorway is allowed");
            Assert.IsFalse(level.PlannerFor(0).TryPlan(inB, inC, corners), "the same doorway with that leaf closed is not");
            Assert.IsFalse(level.InvestigatePlanner.TryPlan(inA, inB, corners), "investigations plan with the current leaves");
            Assert.IsFalse(level.StationPlanner.TryPlan(inA, inB, corners), "station walks plan with the authored leaves");

            // No path crosses the leaf's open pose (a Not Walkable box in the one NavMesh, closed or open).
            var around0 = new Vector3(0.5f, 0f, -1.2f);
            var around1 = new Vector3(0.5f, 0f, 0.7f);
            Assert.IsTrue(level.PlannerFor(0b11).TryPlan(around0, around1, corners), "premise: b is connected around the open pose");
            AssertClearOfLeaf(porte, around0, corners, "a walk across the open pose");

            porte.BeginOpen();
            Swing(porte);
            Assert.AreEqual(0b11, level.OpenMask, "both leaves open");
            Assert.AreEqual(RoutineFactory.AllAreas, level.AreaMask(), "every area once every leaf is open");
            Assert.IsTrue(level.InvestigatePlanner.TryPlan(inA, inB, corners), "an opened leaf allows the plan");
            AssertCrossesDoorway(inA, corners, -0.25f, 0.75f);
            Assert.IsFalse(level.StationPlanner.TryPlan(inA, inB, corners), "station walks stay frozen with the authored leaves");
            Assert.IsTrue(level.InvestigatePlanner.TryPlan(around0, around1, corners));
            AssertClearOfLeaf(porte, around0, corners, "a walk across the open pose, the leaf open");
            Assert.AreSame(nav, level.Planner, "the planner is the same");
            Assert.AreEqual(triangles, NavPlanner.CountTriangles(), "the NavMesh is never rebuilt for a door");
            AssertClean();
        }

        /// <summary>The polyline from <paramref name="from"/> through <paramref name="corners"/> crosses x = 0 within the opening.</summary>
        private static void AssertCrossesDoorway(Vector3 from, List<Vector3> corners, float zMin, float zMax)
        {
            Vector3 a = from;
            bool crossed = false;
            foreach (Vector3 b in corners)
            {
                if (a.x < 0f != b.x < 0f)
                {
                    float t = a.x / (a.x - b.x);
                    float z = Mathf.Lerp(a.z, b.z, t);
                    Assert.IsTrue(z > zMin && z < zMax, $"the path crosses the wall at z = {z:0.00}, outside the doorway");
                    crossed = true;
                }
                a = b;
            }
            Assert.IsTrue(crossed, "premise: the path goes from a to b");
        }

        /// <summary>Every point of the polyline keeps 0.1 m from the leaf's open pose (the NavMesh box keeps about the agent radius).</summary>
        private static void AssertClearOfLeaf(DoorLeaf leaf, Vector3 from, List<Vector3> corners, string what)
        {
            Vector3 a = from;
            float closest = float.MaxValue;
            foreach (Vector3 b in corners)
            {
                for (int i = 0; i <= 20; i++)
                {
                    closest = Mathf.Min(closest, leaf.Geometry.DistanceToLeaf(Vector3.Lerp(a, b, i / 20f), Tuning.DoorSwingDegrees));
                }
                a = b;
            }
            Assert.Greater(closest, 0.1f, $"{what} passes {closest:0.00} m from the open leaf");
            Assert.Greater(corners.Count, 1, $"premise: {what} turns around the leaf");
        }

        [UnityTest]
        public IEnumerator Step36n_ReachIsDistanceAndFootprintAndNeedsAClosedLeaf()
        {
            yield return Load(DoorLevel);
            PinAway();
            DoorLeaf porte = Game.Level.Leaves[0];
            Assert.AreEqual("chair", Chair.Kind, "premise: the chair");
            // From room a, 0.5 m from the doorway centre (0, 0.25): in reach, whatever the yaw.
            Chair.Teleport(new Vector3(-0.5f, 0f, 0.25f), 0f);
            Assert.IsTrue(porte.InReach(Chair), "0.5 m from the door in room a");
            Chair.Teleport(new Vector3(-0.5f, 0f, 0.25f), 133f);
            Assert.IsTrue(porte.InReach(Chair), "no facing condition");
            Chair.Teleport(new Vector3(-0.95f, 0f, 0.25f), 0f);
            Assert.IsFalse(porte.InReach(Chair), "0.95 m: beyond DoorReach");
            Chair.Teleport(new Vector3(0.5f, 0f, 0.25f), 0f);
            Assert.IsFalse(porte.InReach(Chair), "in the swing sector in room b");
            Chair.Teleport(new Vector3(-0.5f, 0f, 0.25f), 0f);
            porte.BeginOpen();
            Assert.IsFalse(porte.InReach(Chair), "an opening leaf is no longer in reach");
            Swing(porte);
            Assert.IsFalse(porte.InReach(Chair), "an open leaf is never in reach");
            Chair.Teleport(Game.Def.Player.Position, Game.Def.Player.Yaw);
            yield return Steps(2);
            AssertClean();
        }

        /// <summary>The top samples of the chair (1 to 4, as the probe's start view) that <paramref name="collider"/> hides from the eye.</summary>
        private int TopSamplesHiddenBy(Collider collider, Vector3 eye)
        {
            var samples = new Vector3[Tuning.SampleCount];
            Chair.GetSamplePoints(samples);
            int hidden = 0;
            for (int i = 1; i < samples.Length; i++)
            {
                Vector3 to = samples[i] - eye;
                if (collider.Raycast(new Ray(eye, to.normalized), out RaycastHit _, to.magnitude))
                {
                    hidden++;
                }
            }
            return hidden;
        }

        /// <summary>Lets frames render until the wall fader ran (LateUpdate) for the camera where it stands now.</summary>
        private IEnumerator Frames()
        {
            yield return Steps(2);
            yield return null;
            yield return null;
        }

        /// <summary>
        /// Step 36o (wave 5A.1, critique m15): level 8, porte_cuisine open, the chair at the designer route point (1.25, 3.75)
        /// just past the doorway, the camera at the spawn's yaw (90): the open leaf stands between the camera and the chair.
        /// M9 doors rule (product owner, 2026-11-19): doors never fade, sink or hide, so the leaf stays drawn whole there
        /// (it used to fade by its box rule), and with the camera on the other side of the chair too.
        /// </summary>
        [UnityTest]
        public IEnumerator Step36o_OpenLeafBetweenTheCameraAndTheChairStaysDrawn()
        {
            yield return Load("level8");
            LevelInstance level = Game.Level;
            DoorLeaf porte = null;
            foreach (DoorLeaf leaf in level.Leaves)
            {
                if (leaf != null && leaf.Id == "porte_cuisine")
                {
                    porte = leaf;
                }
            }
            Assert.IsNotNull(porte, "premise: level 8 has the leaf porte_cuisine");
            Assert.IsFalse(porte.Open, "premise: porte_cuisine starts closed");
            Assert.AreEqual(ShadowCastingMode.On, porte.Renderer.shadowCastingMode, "premise: the closed leaf is drawn at the start view");
            // Paul frozen in the salon facing east, away from the cuisine and the doorway.
            StationDef salon = Game.Def.Inhabitants[0].Stations[1];
            Game.MainInhabitant.Pin(salon.Position, 90f);
            OrbitCamera orbit = Game.Camera;
            Camera cam = orbit != null ? orbit.GetComponent<Camera>() : null;
            Assert.IsNotNull(cam, "premise: the orbit camera renders");
            Assert.AreSame(Camera.main, cam, "premise: the wall fader clears the view of the orbit camera");

            porte.BeginOpen();
            Swing(porte);
            Assert.IsTrue(porte.Open && !porte.Swinging, "premise: porte_cuisine is open");
            var routePoint = new Vector3(1.25f, 0f, 3.75f);
            Chair.Teleport(routePoint, 180f);
            orbit.SetView(Game.Def.Player.Yaw, Tuning.PitchDefault);
            yield return Frames();

            Vector3 eye = cam.transform.position;
            Assert.AreEqual(90f, Game.Def.Player.Yaw, 1e-3f, "premise: the spawn yaw (the default camera yaw) is 90");
            Assert.Less(eye.x, porte.transform.position.x - 0.5f, "premise: the camera stands west of the open leaf");
            Assert.Less(eye.z, 4.45f, "premise: the camera is on the cuisine side of the leaf's wall (its plane does not fade it)");
            int behind = TopSamplesHiddenBy(porte.Collider, eye);
            Assert.Greater(behind, 0, "premise: the open leaf stands between the camera and the chair");
            Assert.AreEqual(ShadowCastingMode.On, porte.Renderer.shadowCastingMode,
                $"the open leaf in front of {behind} top sample(s) of the chair is faded (doors never move)");
            Assert.IsTrue(porte.Renderer.enabled && porte.Renderer.gameObject.activeInHierarchy, "the leaf is no longer drawn");
            Assert.AreEqual(1f, Game.Level.Root.GetComponent<WallFader>().LevelOf(porte.Renderer), 1e-4f, "the leaf does not stand whole");
            TestContext.WriteLine("[Step36o] camera " + eye + ", the drawn leaf stands in front of " + behind + " top samples");

            // Control: the camera east of the chair (yaw 270), the leaf behind the chair: it shows.
            orbit.SetView(270f, Tuning.PitchDefault);
            yield return Frames();
            eye = cam.transform.position;
            Assert.Greater(eye.x, routePoint.x, "premise: the camera stands east of the chair");
            Assert.AreEqual(0, TopSamplesHiddenBy(porte.Collider, eye), "premise: the leaf is behind the chair");
            Assert.AreEqual(ShadowCastingMode.On, porte.Renderer.shadowCastingMode, "the leaf behind the chair is faded");

            orbit.SetView(Game.Def.Player.Yaw, Tuning.PitchDefault);
            Chair.Teleport(Game.Def.Player.Position, Game.Def.Player.Yaw);
            yield return Steps(2);
            AssertClean();
        }

        // ----- 39: the split level (CONTRACT_M5_v3 15.4, CONTRACT_M5 16.6) -----

        // test_m5_house_split: the platform "Mezzanine" x in [-4, 1], z in [0.5, 3], 0.8 m; its ramp rises +z from z = -1.9
        // to z = 0.5 on x in [-0.85, 0.35]. Railings: the edge z = 0.5 beside the ramp head, the edge x = 1, both ramp sides.
        // The inhabitant stands on the platform at (-3.25, 2.25), facing the west wall.

        [UnityTest]
        public IEnumerator Step39_RampIsClimbableAndTheRailingBlocks()
        {
            yield return Load(SplitLevel);
            PinAway();
            LevelInstance level = Game.Level;
            Transform root = level.Root.transform;
            Transform platform = root.Find("Platform Mezzanine");
            Transform ramp = root.Find("Ramp 1");
            Assert.IsNotNull(platform, "premise: the platform is built");
            Assert.IsNotNull(ramp, "premise: the ramp is built");
            Assert.AreEqual(Layers.Occluder, platform.gameObject.layer, "a platform is an occluder");
            Assert.AreEqual(Layers.Occluder, ramp.gameObject.layer, "a ramp is an occluder");
            var wedge = ramp.GetComponent<MeshCollider>();
            Assert.IsTrue(wedge != null && wedge.convex, "a ramp is a convex wedge");
            Assert.AreEqual(0f, wedge.bounds.min.y, 1e-3f, "the ramp is flush at its foot");
            Assert.AreEqual(PlatformHeight, wedge.bounds.max.y, 1e-3f, "the ramp is flush at its head");
            var railings = new List<Transform>();
            foreach (Transform child in root)
            {
                if (child.name.StartsWith("Railing", StringComparison.Ordinal) && child.GetComponent<BoxCollider>() != null)
                {
                    railings.Add(child);
                }
            }
            Assert.AreEqual(5, railings.Count, "two spans beside the ramp head, the edge x = 1 and both ramp sides");
            foreach (Transform r in railings)
            {
                Assert.AreEqual(Layers.Furniture, r.gameObject.layer, $"{r.name} blocks the player and the NavMesh but never a sight ray");
            }

            // Climb: from before the foot, straight up the ramp onto the platform.
            Chair.Teleport(new Vector3(-0.25f, 0f, -2.4f), 0f);
            yield return Steps(2);
            Assert.AreEqual(0f, Chair.transform.position.y, FloorTolerance, "premise: the chair starts on the floor");
            Chair.ScriptedDirection = Vector3.forward;
            yield return Until(() => Chair.transform.position.z > 1.3f, 500);
            Chair.ScriptedDirection = null;
            yield return Steps(5);
            Vector3 top = Chair.transform.position;
            Assert.Greater(top.z, 1.2f, $"the chair did not climb the ramp onto the platform (stopped at {top})");
            Assert.AreEqual(PlatformHeight, top.y, FloorTolerance, "the chair stands on the platform top");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: nobody saw it");

            // The railing on the edge x = 1: the chair stops against it and never falls.
            Chair.ScriptedDirection = Vector3.right;
            float lowest = float.MaxValue;
            yield return Until(() =>
            {
                lowest = Mathf.Min(lowest, Chair.transform.position.y);
                return false;
            }, 150);
            Chair.ScriptedDirection = null;
            yield return Steps(5);
            Vector3 stopped = Chair.transform.position;
            Assert.Greater(stopped.x, 0.3f, "premise: the chair drove toward the edge");
            Assert.Less(stopped.x, 1f - Tuning.RailingThickness - Tuning.ChairControllerRadius + 0.05f, "the railing stops the chair at the edge");
            Assert.AreEqual(PlatformHeight, stopped.y, FloorTolerance, "the chair is still on the platform");
            Assert.Greater(lowest, PlatformHeight - FloorTolerance, "the chair never fell off the platform");

            // The railing beside the ramp head (edge z = 0.5, x < -0.85): the chair stops on the platform.
            Chair.Teleport(new Vector3(-2.5f, 0f, 1.5f), 180f);
            Assert.AreEqual(PlatformHeight, Chair.transform.position.y, 1e-4f, "premise: teleported onto the platform");
            yield return Steps(2);
            Chair.ScriptedDirection = Vector3.back;
            lowest = float.MaxValue;
            yield return Until(() =>
            {
                lowest = Mathf.Min(lowest, Chair.transform.position.y);
                return false;
            }, 150);
            Chair.ScriptedDirection = null;
            yield return Steps(5);
            Assert.Greater(Chair.transform.position.z, 0.5f + Tuning.RailingThickness + Tuning.ChairControllerRadius - 0.05f, "the edge railing stops the chair");
            Assert.Greater(lowest, PlatformHeight - FloorTolerance, "the chair never fell off the platform edge");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: nobody saw it");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step39e_EyesSamplesAndPlansAddTheFloorHeight()
        {
            yield return Load(SplitLevel);
            LevelInstance level = Game.Level;
            Assert.AreSame(Game.Def.Floor, level.Floor, "the level instance reads the level's floor");
            Assert.AreSame(Game.Def.Floor, Chair.Floor, "the builder gave the furniture the level's floor");

            // The inhabitant stands on the platform: its eye and its vision eye add the platform height.
            Inhabitant h = Game.MainInhabitant;
            Vector3 at = h.Routine.Position;
            Assert.AreEqual(PlatformHeight, Game.Def.FloorHeightAt(at.x, at.z), 1e-4f, "premise: the inhabitant stands on the platform");
            Assert.AreEqual(PlatformHeight + h.Routine.EyeHeight, h.EyePosition.y, 1e-3f, "the eye adds the floor height");

            // The furniture's samples on the platform add its height.
            Chair.Teleport(new Vector3(-1.5f, 0f, 1.5f), 0f);
            var samples = new Vector3[Tuning.SampleCount];
            Chair.GetSamplePoints(samples);
            Assert.AreEqual(PlatformHeight + Chair.Size.y * 0.5f, samples[0].y, 1e-3f, "the centre sample on the platform");
            Assert.AreEqual(PlatformHeight + Chair.Size.y - Tuning.SampleInset, samples[1].y, 1e-3f, "a top sample on the platform");

            // The props, the doormat and the spawn stand on their floor; the NavMesh plans up the ramp onto the platform.
            var nav = level.Planner as NavPlanner;
            Assert.IsNotNull(nav, "premise: the NavMesh planner");
            Assert.AreSame(Game.Def.Floor, nav.Floor, "the planner samples from the level's floor");
            var onPlatform = new Vector3(-2.5f, 0f, 1.75f);
            Assert.AreEqual(PlatformHeight + NavPlanner.SampleLift, nav.Lift(onPlatform).y, 1e-4f, "a platform point is sampled from its height + 0.5");
            var corners = new List<Vector3>();
            var floorStart = new Vector3(2.5f, 0f, -2f);
            Assert.IsTrue(nav.TryPlan(floorStart, onPlatform, corners), "a walk from the floor up the ramp onto the platform");
            Assert.Less(YawMath.Planar(corners[corners.Count - 1] - onPlatform).magnitude, 1e-4f, "it ends at the platform point");
            // The platform is reached only by its ramp: the walk crosses the middle of the ramp (x in [-0.85, 0.35]).
            bool viaRamp = false;
            Vector3 a = floorStart;
            foreach (Vector3 b in corners)
            {
                for (int i = 0; i <= 40; i++)
                {
                    Vector3 p = Vector3.Lerp(a, b, i / 40f);
                    viaRamp |= p.x > -0.85f && p.x < 0.35f && p.z > -1.5f && p.z < 0f;
                }
                a = b;
            }
            Assert.IsTrue(viaRamp, "the walk climbs the ramp: " + string.Join(" ", corners));
            Assert.IsTrue(nav.Covers(onPlatform), "the platform top is on the NavMesh");
            Chair.Teleport(Game.Def.Player.Position, Game.Def.Player.Yaw);
            yield return Steps(2);
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step39f_ChairOnThePlatformBehindItsEdgeIsHiddenFromALowEyeBelow()
        {
            yield return Load(SplitLevel);
            PinAway();
            Transform root = Game.Level.Root.transform;
            var platform = root.Find("Platform Mezzanine").GetComponent<BoxCollider>();
            Assert.IsNotNull(platform, "premise: the platform collider");

            // The chair on the platform, 2 m behind its edge z = 0.5.
            Chair.Teleport(new Vector3(-2.5f, 0f, 2.5f), 0f);
            var samples = new Vector3[Tuning.SampleCount];
            Chair.GetSamplePoints(samples);
            Assert.AreEqual(PlatformHeight + Chair.Size.y * 0.5f, samples[0].y, 1e-3f, "premise: the chair stands on the platform");
            var visible = new bool[samples.Length];

            // A low eye (the dog's) on the floor, 0.5 m in front of the edge, looking at it.
            var lowEye = new Vector3(-2.5f, Tuning.DogEyeHeight, 0f);
            Assert.IsFalse(Vision.Test(lowEye, Vector3.forward, samples, 6f, 70f, visible), "the platform edge hides the chair from a low eye below");
            // Controls: a standing eye on the platform sees it, and without the platform the low eye sees it.
            var highEye = new Vector3(-2.5f, PlatformHeight + Tuning.EyeHeight, 1.2f);
            Assert.IsTrue(Vision.Test(highEye, Vector3.forward, samples, 10f, 55f, visible), "control: an eye on the platform sees the chair");
            platform.enabled = false;
            Physics.SyncTransforms();
            bool seenWithout = Vision.Test(lowEye, Vector3.forward, samples, 6f, 70f, visible);
            platform.enabled = true;
            Physics.SyncTransforms();
            Assert.IsTrue(seenWithout, "control: without the platform the low eye sees the chair (nothing else hides it)");
            Chair.Teleport(Game.Def.Player.Position, Game.Def.Player.Yaw);
            yield return Steps(2);
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step39g_PropsDecoysAndTheSpawnStandOnTheirFloor()
        {
            // A platform under a prop, a decoy, a rug and the spawn, in code (the split fixture keeps them on the floor).
            yield return Load(SplitLevel);
            LevelDef def = Game.Def;
            def.Props.Add(new PropDef { Name = "TestCrate", Kind = "box", X = -2.5f, Z = 2.5f, SizeX = 0.5f, SizeY = 0.5f, SizeZ = 0.5f });
            def.Decoys.Add(new DecoyDef { Kind = "chair", X = -1.5f, Z = 2.5f, Color = "#8C5A36" });
            def.Rugs.Add(new RugDef { X = -1.5f, Z = 1.2f, SizeX = 0.8f, SizeZ = 0.6f, Color = "#2E6DB4" });
            float spawnX = def.Player.X;
            float spawnZ = def.Player.Z;
            def.Player.X = 0.5f;
            def.Player.Z = 1.8f;
            try
            {
                Game.Restart();
                yield return Steps(2);
                Transform root = Game.Level.Root.transform;
                Assert.AreEqual(PlatformHeight, root.Find("TestCrate").position.y, 1e-4f, "the prop stands on the platform");
                Assert.AreEqual(PlatformHeight, Game.Level.Decoys[Game.Level.Decoys.Count - 1].transform.position.y, 1e-4f, "the decoy too");
                Assert.AreEqual(PlatformHeight, root.Find("Rug " + def.Rugs.Count).position.y, 1e-4f, "the rug too");
                Assert.AreEqual(PlatformHeight, Chair.transform.position.y, FloorTolerance, "the spawn too");
                Assert.Less(root.Find("Doormat").position.y, 0.05f, "the doormat on the floor stays on the floor");
            }
            finally
            {
                def.Props.RemoveAt(def.Props.Count - 1);
                def.Decoys.RemoveAt(def.Decoys.Count - 1);
                def.Rugs.RemoveAt(def.Rugs.Count - 1);
                def.Player.X = spawnX;
                def.Player.Z = spawnZ;
            }
            Game.Restart();
            yield return Steps(2);
            AssertClean();
        }

        // ----- 39h: budgets (CONTRACT_M5_v3 15.8, CONTRACT_M5 9 and 16.11) -----

        /// <summary>Every collider of the level as (type, name, layer, bounds, trigger, enabled), sorted (as step 23).</summary>
        private List<string> ColliderSet()
        {
            var set = new List<string>();
            foreach (Collider c in Game.Level.Root.GetComponentsInChildren<Collider>(true))
            {
                Bounds b = c.bounds;
                set.Add(string.Format(CultureInfo.InvariantCulture, "{0} {1} L{2} c({3:0.000},{4:0.000},{5:0.000}) s({6:0.000},{7:0.000},{8:0.000}) t{9} e{10}",
                    c.GetType().Name, c.name, c.gameObject.layer, b.center.x, b.center.y, b.center.z, b.size.x, b.size.y, b.size.z,
                    c.isTrigger, c.enabled && c.gameObject.activeInHierarchy));
            }
            set.Sort(StringComparer.Ordinal);
            return set;
        }

        /// <summary>
        /// The distinct materials drawn under the level root, the vision cones excepted: a cone's material follows its
        /// watcher's state at that step (a dog asleep or awake, calm or alarmed), which combining never touches.
        /// </summary>
        private List<string> DecorMaterialNames()
        {
            var names = new HashSet<string>();
            foreach (Renderer r in Game.Level.Root.GetComponentsInChildren<Renderer>(false))
            {
                if (!r.enabled || !r.gameObject.activeInHierarchy || r.GetComponentInParent<VisionConeView>() != null)
                {
                    continue;
                }
                foreach (Material m in r.sharedMaterials)
                {
                    names.Add(m != null ? m.name : "null");
                }
            }
            var sorted = new List<string>(names);
            sorted.Sort(StringComparer.Ordinal);
            return sorted;
        }

        [UnityTest]
        public IEnumerator Step39h_CombinedRenderersKeepCollidersMaterialsAndFades()
        {
            // Every manifest level (levels 1 to 7 first, then the M5 houses of the wave) and the 8 room mock.
            var levels = new List<string>(Game.LevelOrder);
            Assert.GreaterOrEqual(levels.Count, 7, "premise: levels.json lists levels 1 to 7");
            var m4Levels = new HashSet<string>(levels.GetRange(0, 7));
            levels.Add(MockLevel);
            var table = new List<string>();
            int mockSlots = -1;
            int mockBudget = 0;
            try
            {
                foreach (string id in levels)
                {
                    LevelBuilder.CombineRenderers = false;
                    Game.LoadLevel(id);
                    yield return Steps(2);
                    Probe.RenderCount before = Probe.CountRenderers(Game.Level.Root.GetComponentsInChildren<Renderer>(false));
                    List<string> collidersBefore = ColliderSet();
                    List<string> materialsBefore = DecorMaterialNames();
                    int fadesBefore = Game.Level.Root.GetComponent<WallFader>().Count;

                    LevelBuilder.CombineRenderers = true;
                    Game.Restart();
                    yield return Steps(2);
                    LevelInstance level = Game.Level;
                    Probe.RenderCount after = Probe.CountRenderers(level.Root.GetComponentsInChildren<Renderer>(false));
                    List<string> collidersAfter = ColliderSet();
                    int fadesAfter = level.Root.GetComponent<WallFader>().Count;
                    CollectionAssert.AreEqual(collidersBefore, collidersAfter, $"{id}: combining changed a collider");
                    CollectionAssert.AreEqual(materialsBefore, DecorMaterialNames(), $"{id}: combining changed the materials");
                    Assert.Less(after.Renderers, before.Renderers, $"{id}: combining saved no renderer");
                    Assert.LessOrEqual(fadesAfter, fadesBefore, $"{id}: combining added fade entries");
                    Assert.Greater(fadesAfter, 0, $"{id}: premise: walls fade");

                    // Every combined decor renderer keeps its UVs in metres, and every Lit one shows its detail texture at its tile
                    // (the window panes are unlit and plain).
                    var block = new MaterialPropertyBlock();
                    int combined = 0;
                    foreach (MeshRenderer r in level.Root.GetComponentsInChildren<MeshRenderer>(false))
                    {
                        MeshFilter f = r.GetComponent<MeshFilter>();
                        if (r.transform.parent != level.Root.transform || f == null || f.sharedMesh == null || f.sharedMesh.name != "Boxes")
                        {
                            continue;
                        }
                        combined++;
                        // WINDOWS3D (2026-11-24): the 3D windows' frames of one wall line combine, drawn with the wall material,
                        // their UVs the walnut image's own (the GLB's), never in metres; no property block.
                        if (r.name == LevelBuilder.WindowFrameName)
                        {
                            Assert.IsTrue(WallArray.IsWallMaterial(r.sharedMaterial), $"{id}: the window frames are not drawn with the wall material");
                            Assert.IsFalse(r.HasPropertyBlock(), $"{id}: the window frames carry a property block");
                            continue;
                        }
                        Assert.AreEqual(1f, PrimitiveKit.MetresPerUv(r, 0), 1e-3f, $"{id}: {r.name}: combined UVs are not in metres");
                        // Walls 4 (WallArray): a wall of the wall material shows the finishes its vertices name, no block.
                        if (WallArray.IsWallMaterial(r.sharedMaterial))
                        {
                            Assert.IsNotEmpty(WallArray.SurfacesOf(f.sharedMesh), $"{id}: {r.name}: a combined wall names no finish");
                            Assert.IsFalse(r.HasPropertyBlock(), $"{id}: {r.name}: a combined wall carries a property block");
                            continue;
                        }
                        if (PrimitiveKit.PaletteOf(r.sharedMaterial) == null)
                        {
                            Assert.AreEqual("WindowPane", r.name, $"{id}: only the window panes combine with an unlit material");
                            continue;
                        }
                        r.GetPropertyBlock(block, 0);
                        Assert.IsFalse(block.isEmpty, $"{id}: {r.name}: the combined renderer shows no detail");
                    }
                    Assert.Greater(combined, 3, $"{id}: premise: combined decor renderers");

                    // Wave 5B (CONTRACT_M5 17): every procedural bookshelf draws its frame and its books one renderer per material,
                    // and every pane of the house is one renderer.
                    foreach (PropDef prop in Game.Def.Props)
                    {
                        if (prop.Kind != "bookshelf" || !string.IsNullOrEmpty(prop.Model))
                        {
                            continue;
                        }
                        MeshRenderer[] parts = level.Root.transform.Find(prop.Name).GetComponentsInChildren<MeshRenderer>(false);
                        var bookMaterials = new HashSet<Material>();
                        int frames = 0;
                        foreach (MeshRenderer part in parts)
                        {
                            if (part.name == "Frame")
                            {
                                frames++;
                                continue;
                            }
                            Assert.IsTrue(part.name.StartsWith("Books ", StringComparison.Ordinal), $"{id}: bookshelf {prop.Name} draws {part.name}");
                            Assert.IsTrue(bookMaterials.Add(part.sharedMaterial), $"{id}: bookshelf {prop.Name} draws two book renderers of {part.sharedMaterial.name}");
                        }
                        Assert.AreEqual(1, frames, $"{id}: bookshelf {prop.Name} draws its frame as one renderer");
                        Assert.Greater(bookMaterials.Count, 1, $"{id}: premise: bookshelf {prop.Name} has books of several colours");
                    }
                    // WINDOWS3D (2026-11-24, replacing the M7 panes): every window is the 3D model, one glass renderer per
                    // window (its own object space for the glass shader, its own transparent sort) with the one shared glass
                    // material, and the frames of one wall line one renderer of the wall material; frame and glass go with their
                    // wall line (registered with its rule, the glass marked for its own see-through copy). No flat pane is left.
                    // Visual only: a ray through each window's middle, across the wall, still hits the wall's own collider.
                    Assert.IsNotNull(WindowModel.Usable, $"{id}: premise: the 3D window model is usable (Resources/{WindowModel.ResourcePath})");
                    int glasses = 0;
                    var frameLines = new HashSet<string>();
                    var paneFader = level.Root.GetComponent<WallFader>();
                    foreach (MeshRenderer r in level.Root.GetComponentsInChildren<MeshRenderer>(false))
                    {
                        Assert.AreNotEqual("WindowPane", r.name, $"{id}: a flat window pane is still drawn");
                        if (r.name == LevelBuilder.WindowGlassName)
                        {
                            glasses++;
                            Assert.AreSame(WindowModel.Usable.glassMaterial, r.sharedMaterial, $"{id}: a window glass is not the shared glass material");
                            Assert.IsTrue(paneFader.PlaneOf(r, out _, out _), $"{id}: a window glass does not go with its wall");
                            Assert.IsTrue(paneFader.IsGlass(r), $"{id}: a window glass is not marked as glass for its see-through copy");
                            Assert.IsEmpty(r.GetComponentsInChildren<Collider>(true), $"{id}: a window glass carries a collider");
                            Vector3 across = r.transform.forward;
                            Vector3 middle = r.bounds.center;
                            bool walled = false;
                            foreach (RaycastHit hit in Physics.RaycastAll(middle - across * 0.5f, across, 1f, Layers.OccluderMask, QueryTriggerInteraction.Ignore))
                            {
                                walled |= hit.collider.name == "Segment";
                            }
                            Assert.IsTrue(walled, $"{id}: no wall collider behind the window at {middle}: the window must stay visual only");
                        }
                        else if (r.name == LevelBuilder.WindowFrameName)
                        {
                            Assert.IsTrue(paneFader.PlaneOf(r, out Vector3 framePoint, out Vector3 frameNormal), $"{id}: a window frame does not go with its wall");
                            Assert.IsTrue(frameLines.Add(framePoint.ToString("F3") + " " + frameNormal.ToString("F3") + " " + paneFader.IsOuter(r)),
                                $"{id}: two window frame renderers go with the same wall line");
                            Assert.IsEmpty(r.GetComponentsInChildren<Collider>(true), $"{id}: a window frame carries a collider");
                        }
                    }
                    Assert.AreEqual(Game.Def.Windows.Count, glasses, $"{id}: not one glass per window");
                    Assert.AreEqual(Game.Def.Windows.Count > 0, frameLines.Count > 0, $"{id}: the windows draw no frame");

                    // A shared wall's faces and baseboards fade with its centre plane (a wall root's plane), so the parts of one
                    // material on both sides of a wall line are one renderer: no two share a material and a plane.
                    var walls = new List<Transform>();
                    foreach (Transform child in level.Root.transform)
                    {
                        if (child.name.StartsWith("Wall ", StringComparison.Ordinal))
                        {
                            walls.Add(child);
                        }
                    }
                    var fader = level.Root.GetComponent<WallFader>();
                    var planes = new HashSet<string>();
                    int faded = 0;
                    foreach (MeshRenderer r in level.Root.GetComponentsInChildren<MeshRenderer>(false))
                    {
                        if ((r.name != "Face" && r.name != "Baseboards") || !fader.PlaneOf(r, out Vector3 point, out Vector3 normal))
                        {
                            continue;
                        }
                        faded++;
                        Transform wall = walls.Find(w => Mathf.Abs(Vector3.Dot(normal, w.position - point)) < 1e-3f
                            && Mathf.Abs(Mathf.Abs(Vector3.Dot(normal, w.forward)) - 1f) < 1e-4f);
                        Assert.IsNotNull(wall, $"{id}: {r.name} fades with a plane through no wall line's centre ({point}, {normal})");
                        Assert.IsTrue(planes.Add(r.name + " " + r.sharedMaterial.name + " " + wall.name),
                            $"{id}: two {r.name} renderers of {r.sharedMaterial.name} fade with the centre plane of {wall.name}");
                    }
                    if (Game.Def.AllRooms().Count > 1)
                    {
                        Assert.Greater(faded, 0, $"{id}: premise: shared wall faces fade");
                    }

                    // PRD 7.4 counts draw calls as material slots (CONTRACT_M5 16.11 and 17): at most BudgetRenderers on a level
                    // below HouseBudgetRooms rooms, BudgetHouseRenderers on a house, asserted on every manifest level. The distinct
                    // materials are asserted on levels 1 to 7 and measured on the houses (the audit and the built player check
                    // them in play, where the cones count too). The 8 room mock is asserted after the loop (wave 5B, CONTRACT_M5
                    // 17: its slots decided the house figure).
                    int rooms = Game.Def.AllRooms().Count;
                    bool house = rooms >= Tuning.HouseBudgetRooms;
                    int drawCallBudget = house ? Tuning.BudgetHouseRenderers : Tuning.BudgetRenderers;
                    int materialBudget = house ? Tuning.BudgetHouseMaterials : Tuning.BudgetMaterials;
                    Assert.GreaterOrEqual(after.MaterialSlots, after.Renderers, $"{id}: premise: every renderer has a material slot");
                    // M7 walls pass: the see-through walls' one material (drawn by the wall fader, no renderer of its own) counts
                    // whatever the Walls option, as the probe counts it: the budget holds in the worst look.
                    if (fadesAfter > 0)
                    {
                        after.Materials.Add(WallFader.GhostMaterial);
                    }
                    if (id == MockLevel)
                    {
                        mockSlots = after.MaterialSlots;
                        mockBudget = drawCallBudget;
                    }
                    else
                    {
                        Assert.LessOrEqual(after.MaterialSlots, drawCallBudget,
                            $"{id}: {after.MaterialSlots} material slots (draw calls) over the {drawCallBudget} budget");
                    }
                    if (m4Levels.Contains(id))
                    {
                        Assert.LessOrEqual(after.Materials.Count, Tuning.BudgetMaterials, $"{id}: materials");
                    }
                    table.Add($"{id} ({rooms} rooms, {Game.Def.Inhabitants.Count} inhabitants): material slots (draw calls) {before.MaterialSlots} -> "
                        + $"{after.MaterialSlots} (budget {drawCallBudget}), renderers {before.Renderers} -> {after.Renderers}, materials "
                        + $"{after.Materials.Count} (budget {materialBudget}), fades {fadesBefore} -> {fadesAfter}");
                }
            }
            finally
            {
                LevelBuilder.CombineRenderers = true;
            }
            Assert.Greater(mockSlots, 0, "premise: the 8 room mock was measured");
            table.Add($"{MockLevel}: {mockSlots} material slots (draw calls) against the house budget {mockBudget}");
            Debug.Log("[Step39h] " + string.Join(" | ", table));
            TestContext.WriteLine("[Step39h] " + string.Join(" | ", table));
            // Wave 5B (CONTRACT_M5 17): the 8 room worst case (3 humans and a dog) fits the house budget once its slots are cut.
            Assert.LessOrEqual(mockSlots, mockBudget, $"{MockLevel}: {mockSlots} material slots (draw calls) over the house budget {mockBudget}");
            Game.LoadLevel(levels[0]);
            yield return Steps(2);
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step39j_MockHouseStationWalksPlanThroughDoorsAndUpTheRamp()
        {
            yield return Load(MockLevel);
            LevelInstance level = Game.Level;

            // The builder's inhabitants (CONTRACT_M5 3 and 16.12, v3 15.1 and 15.6): each wears its personality's model and
            // shares the level's seat registry as owner i; its station walks are frozen with the authored leaves, every
            // other walk plans with the leaves as they are; a dog's capsule is dog sized.
            Assert.AreEqual(Game.Def.Inhabitants.Count, level.Inhabitants.Count, "premise: every inhabitant is built");
            Assert.AreNotEqual(RoutineFactory.AllAreas, level.StationAreaMask, "premise: the mock has a closed leaf");
            CollectionAssert.IsEmpty(level.ModelFallbacks, "every model of the mock is drawn");
            int dogs = 0;
            for (int i = 0; i < level.Inhabitants.Count; i++)
            {
                Inhabitant h = level.Inhabitants[i];
                InhabitantDef def = Game.Def.Inhabitants[i];
                Assert.IsTrue(string.IsNullOrEmpty(def.Model), $"premise: {def.Name} names no model");
                Assert.IsNotNull(h.Rig, $"{def.Name} is rigged");
                Assert.AreEqual(Inhabitant.ModelIdOf(def), h.Rig.Entry.id, $"{def.Name} wears its personality's model");
                Assert.AreSame(level.Seats, h.Routine.Seats, $"{def.Name} shares the level's seat registry");
                Assert.AreEqual(i, h.Routine.SeatOwner, $"{def.Name} claims seats as owner {i}");
                Assert.AreEqual(level.StationAreaMask, h.Routine.StationAreaMask, $"{def.Name}'s station walks use the authored leaves");
                Assert.AreSame(level.InvestigatePlanner, h.Routine.InvestigatePlanner, $"{def.Name}'s other walks plan with the leaves as they are");
                Assert.AreSame(Game.Def.Floor, h.Routine.Floor, $"{def.Name} stands on the level's floor");
                var capsule = h.GetComponent<CapsuleCollider>();
                if (h.IsDog)
                {
                    dogs++;
                    Assert.AreEqual(Tuning.DogCapsuleHeight, capsule.height, 1e-4f, "the dog's capsule is dog sized");
                    Assert.AreEqual(Tuning.DogCapsuleRadius, capsule.radius, 1e-4f);
                }
                else
                {
                    Assert.AreEqual(Tuning.InhabitantHeight, capsule.height, 1e-4f, $"{def.Name}'s capsule is human sized");
                }
            }
            Assert.AreEqual(1, dogs, "premise: the mock has its dog");

            var nav = level.Planner as NavPlanner;
            Assert.IsNotNull(nav, "premise: the mock plans on its NavMesh");
            var corners = new List<Vector3>();
            var report = new List<string>();
            // The ramp and the platform of the mock: the ramp x in [-5.85, -4.65], z from 2.1 (foot) to 3.9 (head).
            var beforeFoot = new Vector3(-5.25f, 0f, 1.8f);
            var onRamp = new Vector3(-5.25f, 0f, 3.0f);
            var onPlatform = new Vector3(-5.25f, 0f, 4.6f);
            report.Add($"covers: before foot {nav.Covers(beforeFoot)}, ramp {nav.Covers(onRamp)}, platform {nav.Covers(onPlatform)}");
            report.Add($"foot to ramp {nav.TryPlan(beforeFoot, onRamp, corners)}, ramp to platform {nav.TryPlan(onRamp, onPlatform, corners)}");
            NavMeshTriangulation tri = NavMesh.CalculateTriangulation();
            int high = 0;
            foreach (Vector3 v in tri.vertices)
            {
                if (v.y > 0.45f && v.x < -1.9f && v.z > 3.8f)
                {
                    high++;
                }
            }
            report.Add($"NavMesh vertices on the platform: {high}");
            foreach (float z in new[] { 4.4f, 4.6f, 4.9f })
            {
                foreach (float x in new[] { -5.6f, -5.25f, -4.9f, -4.5f, -4.0f, -3.5f, -2.5f })
                {
                    var p = new Vector3(x, 0f, z);
                    Vector3 lifted = nav.Lift(p);
                    string hit = NavMesh.SamplePosition(lifted, out NavMeshHit h, 1f, NavMesh.AllAreas)
                        ? string.Format(CultureInfo.InvariantCulture, "({0:0.00},{1:0.00},{2:0.00})", h.position.x, h.position.y, h.position.z) : "none";
                    report.Add(string.Format(CultureInfo.InvariantCulture, "p({0},{1}) snap {2} plan {3}", x, z, hit, nav.TryPlan(onPlatform, p, corners)));
                }
            }
            var failures = new List<string>();
            foreach (InhabitantDef h in Game.Def.Inhabitants)
            {
                foreach (Vector2Int pair in RoutinePatterns.ReachablePairs(h.Pattern, h.Stations.Count))
                {
                    Vector3 a = h.Stations[pair.x].Position;
                    Vector3 b = h.Stations[pair.y].Position;
                    if (pair.x != pair.y && !level.StationPlanner.TryPlan(a, b, corners))
                    {
                        failures.Add($"{h.Name} {pair.x + 1} -> {pair.y + 1}");
                    }
                }
            }
            TestContext.WriteLine("[Step39j] " + string.Join(" | ", report));
            CollectionAssert.IsEmpty(failures, "station walks without a path (" + string.Join(" | ", report) + ")");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step39i_CameraZoomBoundScalesWithTheHouse()
        {
            OrbitCamera cam = Game.Camera;
            Assert.IsNotNull(cam, "premise: the orbit camera");
            foreach (string id in new List<string>(Game.LevelOrder).GetRange(0, 7))
            {
                Game.LoadLevel(id);
                // 2026-11-24: every house zooms out until it is seen whole (Tuning.CameraWholeHouseFit), small ones included.
                Assert.AreEqual(OrbitCamera.MaxDistanceFor(Game.Def), cam.MaxDistance, 1e-4f, $"{id} zooms out to its whole house");
            }
            yield return Load(MockLevel);
            Rect interior = Game.Def.InteriorBounds();
            float side = Mathf.Max(interior.width, interior.height);
            Assert.Greater(side, Tuning.CameraHouseReferenceSide, "premise: the mock house is larger than any M4 level");
            float expected = Mathf.Clamp(Mathf.Max(Tuning.OrbitDistanceMax * side / Tuning.CameraHouseReferenceSide, side * Tuning.CameraWholeHouseFit),
                Tuning.OrbitDistanceMax, Tuning.CameraMaxDistanceHouse);
            Assert.AreEqual(expected, cam.MaxDistance, 1e-4f, "the zoom bound scales with the house");
            Assert.Greater(cam.MaxDistance, Tuning.OrbitDistanceMax);
            Assert.AreEqual(Tuning.CameraMaxDistanceHouse, OrbitCamera.MaxDistanceFor(new LevelDef
            {
                Rooms = new List<RoomDef> { new RoomDef { X = 0f, Z = 0f, SizeX = 60f, SizeZ = 4f, WallHeight = 2.7f, WallThickness = 0.1f } },
            }), 1e-4f, "capped at CameraMaxDistanceHouse");
            AssertClean();
        }

        // ----- 43r: the procedural rocking chair (CONTRACT_M5 5, wave 5B) -----

        [UnityTest]
        public IEnumerator Step43r_ProceduralRockingChairIsOneRendererOnCurvedRunnersWithinItsBox()
        {
            // The body's size (CONTRACT_M5 5): the procedural visual stands in for a missing model, for the player and the decoys.
            BodyDef body = BodyDef.For(BodyKinds.RockingChair);
            Assert.AreEqual(BodyKinds.RockingChair, body.Kind, "premise: core's rocking_chair row");
            Vector3 size = body.Size;
            var holder = new GameObject("RockingChairProbe");
            try
            {
                var color = new Color32(0xD7, 0x26, 0x3D, 0xFF);
                Assert.IsTrue(FurnitureKit.Body(BodyKinds.RockingChair, holder.transform, size, color, Layers.Player), "a known procedural body");
                MeshRenderer[] renderers = holder.GetComponentsInChildren<MeshRenderer>(true);
                Assert.AreEqual(1, renderers.Length, "one renderer, one draw call");
                Assert.AreEqual(1, renderers[0].sharedMaterials.Length, "one material slot");
                // M7 real colours (CONTRACT_M7 5): this probe colour is the player's own red, so the rocking chair shows the
                // owner's red image (PrimitiveKit.PlayerMaterial).
                Assert.AreSame(PrimitiveKit.PlayerMaterial(color), renderers[0].sharedMaterial, "in its own colour");
                Assert.AreEqual(Layers.Player, renderers[0].gameObject.layer);
                Assert.AreEqual(0, holder.GetComponentsInChildren<Collider>(true).Length, "a body visual has no collider");
                Mesh mesh = renderers[0].GetComponent<MeshFilter>().sharedMesh;
                // Soft movers (2026-11-20): runners 2 x 76, seat 58, front legs 2 x 16, posts 2 x 22, back panel 44, arms 2 x 22.
                Assert.AreEqual(374, ModelKit.Triangles(mesh), "the rounded rocking chair");
                Assert.LessOrEqual(Probe.TrianglesUnder(holder.transform), Tuning.BudgetFurnitureTriangles, "PRD 7.4 furniture triangles");
                Assert.AreEqual(1f, PrimitiveKit.MetresPerUv(renderers[0], 0), 1e-3f, "UVs in metres");
                var block = new MaterialPropertyBlock();
                renderers[0].GetPropertyBlock(block, 0);
                Assert.IsFalse(block.isEmpty, "it shows its wood");

                // Within its box (x and z centred, y from the floor up), touching the floor.
                Bounds b = mesh.bounds;
                const float tolerance = 0.01f;
                Assert.LessOrEqual(b.max.x, size.x * 0.5f + tolerance);
                Assert.GreaterOrEqual(b.min.x, -size.x * 0.5f - tolerance);
                Assert.LessOrEqual(b.max.z, size.z * 0.5f + tolerance);
                Assert.GreaterOrEqual(b.min.z, -size.z * 0.5f - tolerance);
                Assert.LessOrEqual(b.max.y, size.y + tolerance);
                Assert.AreEqual(0f, b.min.y, tolerance, "it stands on the floor");
                Assert.Greater(b.max.y, size.y * 0.9f, "its back reaches its height");

                // The runners curve: under the seat they touch the floor, at both ends they rise by RockerRise.
                Vector3[] vertices = mesh.vertices;
                float Lowest(float zFrom, float zTo)
                {
                    float y = float.MaxValue;
                    foreach (Vector3 v in vertices)
                    {
                        if (v.z >= zFrom && v.z <= zTo)
                        {
                            y = Mathf.Min(y, v.y);
                        }
                    }
                    return y;
                }
                float middle = Lowest(-0.05f, 0.05f);
                Assert.AreEqual(0f, middle, tolerance, "the runners touch the floor at the middle");
                Assert.Greater(Lowest(size.z * 0.5f - 0.06f, size.z), FurnitureKit.RockerRise * 0.5f, "the front of the runners rises");
                Assert.Greater(Lowest(-size.z, -size.z * 0.5f + 0.06f), FurnitureKit.RockerRise * 0.5f, "the back of the runners rises");

                // Its back stands on -z, as the chair's (the bodies face +z).
                float backZ = 0f;
                int high = 0;
                foreach (Vector3 v in vertices)
                {
                    if (v.y > size.y * 0.85f)
                    {
                        backZ += v.z;
                        high++;
                    }
                }
                Assert.Greater(high, 0, "premise: vertices near the top");
                Assert.Less(backZ / high, -0.1f, "the back is on -z");

                // An unknown kind still builds nothing.
                Assert.IsFalse(FurnitureKit.Body("hammock", holder.transform, size, color, 0));
            }
            finally
            {
                Object.DestroyImmediate(holder);
            }
            yield return null;
            AssertClean();
        }

        // ----- 39l: the robot and the load build with the level (CONTRACT_M5 4, 6, 16.5, 16.8 and 16.12, wave 5B) -----

        /// <summary>The components of type T under the level root, counted (a duplicate would show).</summary>
        private int CountUnderLevel<T>() where T : Component => Game.Level.Root.GetComponentsInChildren<T>(true).Length;

        [UnityTest]
        public IEnumerator Step39l_RobotAndLoadBuildWithTheLevelAndTheRockingChairShowsItsVisual()
        {
            // test_m5_house_robot: the robot Robi from (-2.5, -1) in room a to (2.5, -1) in room b through a leafless doorway, and
            // the chair (spawn (2.8, 0.8) in room b) carrying a vase. Checked right after the build, before the game steps it.
            Game.LoadLevel(RobotLevel);
            Assert.AreEqual(RobotLevel, Game.Def.Id, "premise: the level loaded");
            LevelDef def = Game.Def;
            Assert.AreEqual(1, def.Robots.Count, "premise: the fixture has one robot");
            Assert.AreEqual(LoadView.Vase, def.Player.Load, "premise: the chair carries a vase");
            Assert.IsTrue(def.Floor.IsFlat, "premise: a flat level (the floor is y = 0)");
            LevelInstance level = Game.Level;
            Transform root = level.Root.transform;

            // The robot: one per RobotDef, its path built from its def, standing where the path starts, on the floor.
            Assert.AreEqual(def.Robots.Count, level.Robots.Count, "one Robot per RobotDef");
            Assert.AreEqual(1, CountUnderLevel<Robot>(), "and no other robot under the level");
            Robot robot = level.Robots[0];
            Assert.IsNotNull(robot, "the robot was built");
            Assert.AreSame(def.Robots[0], robot.Def, "built from its def");
            Assert.AreSame(root, robot.transform.parent, "under the level root (torn down with it)");
            RobotPath path = robot.Path;
            Assert.IsNotNull(path, "it carries its path");
            Assert.AreEqual(def.Robots[0].Loop.Count, path.Points.Count, "the path has the loop's waypoints");
            for (int k = 0; k < path.Points.Count; k++)
            {
                Assert.Less((path.Points[k] - def.Robots[0].Loop[k].Position).magnitude, 1e-5f, "waypoint " + k);
            }
            Assert.AreEqual(Tuning.RobotSpeed, path.Speed, 1e-5f, "the fixture's speed 0 means the default speed");
            Vector3 start = def.Robots[0].Loop[def.Robots[0].Start].Position;
            Assert.Less((robot.Position - path.PositionAt(0f)).magnitude, 1e-4f, "posed where its path starts");
            Assert.Less((YawMath.Planar(robot.Position) - start).magnitude, 1e-4f, "on its start waypoint");
            Assert.AreEqual(def.Floor.HeightAt(start.x, start.z), robot.Position.y, 1e-4f, "on the floor");
            Assert.AreEqual(0f, Mathf.DeltaAngle(path.HeadingAt(0f), robot.transform.eulerAngles.y), 0.1f, "heading for the next waypoint");
            // No collider (no NavMesh source, no obstacle), not an occluder: the Default layer everywhere (16.8).
            Assert.AreEqual(0, robot.GetComponentsInChildren<Collider>(true).Length, "the robot has no collider");
            foreach (Transform t in robot.GetComponentsInChildren<Transform>(true))
            {
                Assert.AreEqual(0, t.gameObject.layer, t.name + " is on the Default layer");
            }
            Assert.Greater(robot.GetComponentsInChildren<MeshRenderer>(true).Length, 0, "the robot is drawn");

            // The load: one LoadView of the data's kind on the furniture's Visual (it follows the hops and the jitter).
            FurnitureController chair = Game.Furniture;
            Assert.AreEqual(1, chair.GetComponentsInChildren<LoadView>(true).Length, "one load view on the furniture");
            Assert.AreEqual(1, CountUnderLevel<LoadView>(), "and no other under the level");
            LoadView view = level.LoadView;
            Assert.IsNotNull(view, "the level lists its load view");
            Assert.AreSame(chair.GetComponentInChildren<LoadView>(true), view, "the one on the furniture");
            Assert.AreEqual(LoadView.Vase, view.Kind, "the data's kind");
            Assert.IsTrue(view.transform.IsChildOf(chair.Visual), "on the furniture's Visual");
            Assert.Less((view.BodySize - chair.Size).magnitude, 1e-5f, "at the body's size");
            Assert.IsFalse(view.Fallen, "carried at the start");
            Assert.IsFalse(view.ClueActive, "no clue at the start");
            Assert.AreEqual(0, view.GetComponentsInChildren<Collider>(true).Length, "the load is a visual only");
            Bounds carried = view.CarriedBounds;
            Assert.Greater(carried.size.y, 0f, "premise: the carried object is drawn");
            Assert.AreEqual(chair.transform.position.y + chair.Size.y, carried.min.y, 0.02f, "it stands on the box top");
            Assert.AreEqual(chair.transform.position.y + chair.Size.y + Tuning.LoadHeight, carried.max.y, 0.02f, "LoadHeight tall");

            // The cones aim at the load's top: the sample box grows by LoadHeight (16.5).
            BodyDef body = def.PlayerBody();
            Assert.Greater(level.Cones.Count, 0, "premise: a cone");
            foreach (VisionConeView cone in level.Cones)
            {
                Assert.AreEqual(body.Size.y - Tuning.SampleInset + Tuning.LoadHeight, cone.TargetHeight, 1e-4f, "the cone aims at the load's top");
            }

            // A restart rebuilds exactly one robot and one load; the old ones went with the old level.
            Game.Restart();
            Assert.IsTrue(robot == null, "the old robot was destroyed with its level");
            Assert.IsTrue(view == null, "the old load view too");
            Assert.AreEqual(1, Game.Level.Robots.Count, "one robot after a restart");
            Assert.AreEqual(1, CountUnderLevel<Robot>(), "and only one under the level");
            Assert.AreEqual(1, CountUnderLevel<LoadView>(), "one load view after a restart");
            Assert.IsNotNull(Game.Level.LoadView, "listed again");
            Assert.AreNotSame(path, Game.Level.Robots[0].Path, "a new path: no reversal survives a restart");
            yield return Steps(2);
            Assert.AreEqual(1, CountUnderLevel<Robot>(), "the game builds no robot of its own");
            Assert.AreEqual(1, CountUnderLevel<LoadView>(), "nor a load view");

            // Controls: without a load there is no view and the cones aim at the body's top. And a rocking chair player and a
            // rocking chair decoy (in room b, clear of the robot's loop) show the procedural rocking chair (no Kenney model).
            string load = def.Player.Load;
            string kind = def.Player.Kind;
            int decoys = def.Decoys.Count;
            try
            {
                def.Player.Load = null;
                def.Player.Kind = BodyKinds.RockingChair;
                def.Decoys.Add(new DecoyDef { Kind = BodyKinds.RockingChair, X = 1.0f, Z = 1.0f, Color = "#8C5A36" });
                Game.Restart();
                BodyDef rocking = BodyDef.For(BodyKinds.RockingChair);
                Assert.IsTrue(rocking.Rocks, "premise: core's rocking_chair row");
                Assert.IsTrue(string.IsNullOrEmpty(rocking.Model), "premise: no Kenney rocking chair, so the procedural visual");
                FurnitureController player = Game.Furniture;
                Assert.AreEqual(BodyKinds.RockingChair, player.Kind, "the player is the rocking chair");
                Assert.Less((player.Size - rocking.Size).magnitude, 1e-5f, "at its body's size");
                Assert.IsNull(Game.Level.LoadView, "no load, no view");
                Assert.AreEqual(0, CountUnderLevel<LoadView>(), "no load view anywhere");
                Transform visual = player.Visual.Find("RockingChair");
                Assert.IsNotNull(visual, "the player shows the procedural rocking chair");
                Color red = LevelJson.ParseColor(def.Player.Color, Color.red);
                // M7 real colours (CONTRACT_M7 5): the player's own furniture shows the owner's red image (PrimitiveKit.PlayerMaterial).
                Assert.AreSame(PrimitiveKit.PlayerMaterial(red), visual.GetComponent<MeshRenderer>().sharedMaterial, "in the player colour");
                Assert.AreEqual(Layers.Player, visual.gameObject.layer, "on the player layer");
                Decoy decoy = Game.Level.Decoys[Game.Level.Decoys.Count - 1];
                Assert.AreEqual(BodyKinds.RockingChair, decoy.Kind, "the decoy is a rocking chair");
                Assert.Less((decoy.Size - rocking.Size).magnitude, 1e-5f, "sized by its kind");
                Assert.IsNotNull(decoy.transform.Find("Visual/RockingChair"), "the decoy shows the procedural rocking chair");
                CollectionAssert.IsEmpty(Game.Level.ModelFallbacks, "no model is named, so nothing falls back");
                foreach (VisionConeView cone in Game.Level.Cones)
                {
                    Assert.AreEqual(rocking.Size.y - Tuning.SampleInset, cone.TargetHeight, 1e-4f, "without a load the cone aims at the body's top");
                }
                Assert.AreEqual(1, Game.Level.Robots.Count, "the robot builds whatever the body");
                yield return Steps(2);
            }
            finally
            {
                def.Player.Load = load;
                def.Player.Kind = kind;
                def.Decoys.RemoveRange(decoys, def.Decoys.Count - decoys);
            }
            Game.Restart();
            Assert.AreEqual(1, CountUnderLevel<LoadView>(), "the vase is back");
            yield return Steps(2);
            AssertClean();
        }
    }
}
