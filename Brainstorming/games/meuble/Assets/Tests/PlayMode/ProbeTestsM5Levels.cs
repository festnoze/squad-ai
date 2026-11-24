using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M5 levels probe (docs/CONTRACT_M5.md 8, 12 and 16.10, 16.11, CONTRACT_M5_v3 11 and 15.10), on the real Boot scene.
    ///
    /// Step 45 (levels 8 to 17; wave 5A: 8, 12, 14 and 16), one test per level under its own [Timeout]: the designer route
    /// the audit wrote (LevelAudit -writeRoutes) wins through RouteReplayer with every "at" shifted by -0.2 s, 0 and
    /// +0.2 s, with no discovery, no alert, no creak and no bark, and plays its level's lesson (step 45, 45b, 45c, 45d).
    /// The door level has counter-routes (step 45e): the same route rushed opens its door in the inhabitant's sight and is
    /// caught by the swinging leaf, and the route without its opening never gets past the closed leaf.
    /// Step 45a: the wave 5A levels boot in levels.json order with their body, lesson and people, and an idle player is
    /// never caught. Step 45f: the replayer's "open" retry path.
    /// Wave 5B (CONTRACT_M5 16.10): the designer routes of levels 9, 10, 11, 13, 15 and 17 (steps 45i to 45n; every
    /// designer route also keeps its load, if any, and never touches the robot), the counter-routes (step 45o, the robot
    /// collision on level 9; step 45p, the rock seen on level 10; step 45q, the vase dropped at full speed on level 11) and
    /// step 45r, the wave 5B levels boot with their body, lesson, people, robot and load.
    /// Step 40: the whole play order through the real level flow (Enter to the next level) at offset 0 and timeScale 8,
    /// the save checked after each win, ending on the end screen.
    /// Levels v2 (docs/levels_v2/LEVELS_V2.md 9): the replays of the cut level10 and level16 are deleted (45d, 45j), step
    /// 45m plays level15's rock, 45o uses level9's v2 lane, 45b is time-aware, 45g is redrawn for the v2 salon, and the
    /// order checks of 45a and 45r are gone (LevelDataM2Tests checks the v2 order). The level10 counter-route (45p) still
    /// loads the archived file by id.
    /// Every step asserts its premise first, so a level that does not run cannot pass.
    /// </summary>
    public sealed class ProbeTestsM5Levels
    {
        private Main main;
        private GameState Game => main.Game;
        private Hud Hud => main.Hud;
        private readonly List<string> errors = new List<string>();

        /// <summary>CONTRACT_M5 12 (step 45) and M2.1: every route is replayed this much early, on time and late.</summary>
        private static readonly float[] Offsets = { -0.2f, 0f, 0.2f };

        /// <summary>Levels v2 (docs/levels_v2/LEVELS_V2.md 3, D1): the play order holds 22 levels (7 + 9 + 6).</summary>
        private const int V2LevelCount = 22;

        /// <summary>The wave 5A levels still played in v2, with the body and the lesson of CONTRACT_M5 16.10 (level16 is cut,
        /// LEVELS_V2 D2).</summary>
        private static readonly (string id, string body, string lesson, int humans, int dogs)[] WaveA =
        {
            ("level8", BodyKinds.Chair, LevelDef.LessonDoor, 1, 0),
            ("level12", BodyKinds.Stool, LevelDef.LessonPet, 1, 1),
            ("level14", BodyKinds.Armchair, LevelDef.LessonSplit, 2, 0),
        };

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            ModelKit.Disabled = false;
            errors.Clear();
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
            yield return Steps(2);
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
                errors.Add(condition);
            }
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        /// <summary>Waits until <paramref name="condition"/> holds, at most <paramref name="seconds"/> of game time (Time.time).</summary>
        private static IEnumerator Until(Func<bool> condition, float seconds)
        {
            float end = Time.time + seconds;
            while (!condition() && Time.time < end)
            {
                yield return null;
            }
        }

        /// <summary>Loads <paramref name="id"/> fresh under the default (M4) rules and checks it is the level that runs.</summary>
        private IEnumerator LoadFresh(string id)
        {
            Game.LoadLevel(id);
            Game.Rules = GameRules.M4;
            yield return Steps(1);
            Assert.AreEqual(id, Game.LevelId, "premise: the level was loaded");
            Assert.AreEqual(PlayState.Playing, Game.State, id + ": premise: the level is playing");
        }

        // ----- 45: the designer routes of levels 8 to 17 -----

        /// <summary>
        /// Replays the designer route of <paramref name="id"/> at -0.2, 0 and +0.2 s (CONTRACT_M5 12, step 45): each run
        /// wins, with no discovery, no alert, no creak and no bark (the audit forbids a bark), no error logged, and passes
        /// <paramref name="lesson"/>, which adds a failure when the run did not play the level's lesson.
        /// </summary>
        private IEnumerator ReplayDesignerRoute(string id, Action<RouteReplayer.Result, List<string>> lesson, Action perStep = null)
        {
            CollectionAssert.Contains(Game.LevelOrder.ToList(), id, "premise: " + id + " is listed in levels.json");
            var failures = new List<string>();
            foreach (float offset in Offsets)
            {
                int errorsBefore = errors.Count;
                yield return LoadFresh(id);
                Assert.GreaterOrEqual(Game.Def.DesignerRoute.Count, 2, id + ": premise: no designerRoute (LevelAudit -writeRoutes writes it)");
                var r = new RouteReplayer.Result();
                // Levels v2: a time-aware check of the caller watches every fixed step of the replay (Step45b).
                if (perStep != null)
                {
                    Game.FixedStepped += perStep;
                }
                try
                {
                    yield return RouteReplayer.Replay(Game, offset, r, Tuning.PlaythroughTimeScale);
                }
                finally
                {
                    if (perStep != null)
                    {
                        Game.FixedStepped -= perStep;
                    }
                }
                Debug.Log("[Step45] " + r);
                string label = r.Label;
                if (r.State != PlayState.Won)
                {
                    failures.Add($"{label}: the route did not win ({r.State}, {r.Reason}) after {r.Time:0.0} s, waypoint {r.Waypoint}/{r.Waypoints}"
                                 + (r.TimedOut ? ", timed out" : "") + (r.Stalled ? ", stalled" : ""));
                }
                if (r.Discoveries != 0 || r.Alerts != 0 || r.Creaks != 0 || r.Barks != 0)
                {
                    failures.Add($"{label}: {r.Discoveries} discoveries, {r.Alerts} alerts, {r.Creaks} creaks, {r.Barks} barks (all must be 0)");
                }
                // Wave 5B (CONTRACT_M5 6, 16.5, 16.8): the replay is the final arbiter of the load, which must hold, and the
                // audit's contact zone keeps every designer route off the robot.
                if (r.Crashes != 0 || (r.HasLoad && !r.LoadHeld) || r.RobotContacts != 0)
                {
                    failures.Add($"{label}: {r.Crashes} load falls (load {(r.HasLoad ? (r.LoadHeld ? "held" : "fell") : "none")}), "
                                 + $"{r.RobotContacts} robot contacts (all must be 0)");
                }
                if (errors.Count != errorsBefore)
                {
                    failures.Add($"{label}: error(s) logged: {string.Join(" | ", errors.Skip(errorsBefore))}");
                }
                lesson(r, failures);
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }

        /// <summary>The first "open" step of the current level's designer route (its door id), or null.</summary>
        private string RouteDoor()
        {
            RouteStepDef open = Game.Def.DesignerRoute.FirstOrDefault(s => s.Action == RouteStepDef.ActionOpen);
            return open?.Door;
        }

        /// <summary>
        /// Step 45, level 8 "Les portes" (lesson door): the route opens its door, every press starts the opening (no retry
        /// given up), GameState counts the opening, and the leaf the route names is open at the end.
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step45_Level8Routes()
        {
            yield return ReplayDesignerRoute("level8", (r, failures) =>
            {
                string door = RouteDoor();
                Assert.IsNotNull(door, "premise: the route of level 8 has an open step");
                DoorLeaf leaf = Game.Level.Leaves.FirstOrDefault(l => l.Id == door);
                Assert.IsNotNull(leaf, $"premise: level 8 has the leaf {door} its route opens");
                if (r.Opens < 1 || r.DoorOpens < 1 || r.OpenFailures != 0 || !leaf.Open)
                {
                    failures.Add($"{r.Label}: {r.Opens} openings ({r.DoorOpens} counted by the game, {r.OpenFailures} given up), {door} open {leaf.Open}: "
                                 + "the route must open its door");
                }
            });
        }

        /// <summary>
        /// Step 45b, level 12 "Le chien" (lesson pet): the careful stool never tips nor runs past the tip speed, and the
        /// awake dog never barks (asserted for every run). 5A.1 (CONTRACT_M5 17), made time-aware by levels v2 (the v2 Rex
        /// turns on his spot instead of napping): the hint "les canapés te cachent de lui" is true: at every fixed step of
        /// every replay where the awake dog, as he stands and looks at that moment, has the stool in his room within his
        /// range and half angle, a sofa stands between him and the stool.
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step45b_Level12Routes()
        {
            int watched = 0;
            var uncovered = new List<string>();
            void Watch()
            {
                if (Game.State != PlayState.Playing)
                {
                    return;
                }
                watched += DogSightsWithoutASofa(uncovered);
            }
            yield return ReplayDesignerRoute("level12", (r, failures) =>
            {
                Assert.IsTrue(Game.Def.Inhabitants.Any(h => h.Kind == PersonalityDef.Dog), "premise: level 12 has a dog");
                if (r.Topples != 0 || r.TopSpeed > Tuning.StoolTipSpeed)
                {
                    failures.Add($"{r.Label}: the stool tipped ({r.Topples}) or went {r.TopSpeed:0.00} m/s, above {Tuning.StoolTipSpeed}");
                }
            }, Watch);
            Debug.Log($"[Step45b] {watched} steps with the stool in the awake dog's range and cone, {uncovered.Count} without a sofa between");
            Assert.Greater(watched, 0, "premise: the stool never stood in the awake dog's room within his range and cone (the sofa hides nothing)");
            Assert.IsEmpty(uncovered, "steps where the awake dog had the stool in range and cone with no sofa between them:\n"
                                      + string.Join("\n", uncovered.Take(12)));
        }

        /// <summary>
        /// One fixed step of the time-aware sofa check (Step 45b): for each awake dog of the running level, when the furniture
        /// is in the dog's room, within his view range and half angle around his eye yaw, returns 1 and, when no prop of kind
        /// "sofa" crosses the plan segment from the dog to the furniture, adds a line to <paramref name="uncovered"/> (a plan
        /// view test: the sofa is what hides the stool, CONTRACT_M5 17).
        /// </summary>
        private int DogSightsWithoutASofa(List<string> uncovered)
        {
            LevelDef def = Game.Def;
            Vector3 stool = YawMath.Planar(Game.Furniture.transform.position);
            RoomDef stoolRoom = def.RoomAt(stool);
            int inSight = 0;
            List<PropDef> sofas = def.Props.Where(p => p.Kind == "sofa" && p.Occluder).ToList();
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                if (h.Def.Kind != PersonalityDef.Dog || h.Routine.Asleep)
                {
                    continue;
                }
                Vector3 dog = YawMath.Planar(h.Routine.Position);
                Vector3 to = stool - dog;
                if (stoolRoom == null || def.RoomAt(dog) != stoolRoom || to.magnitude > h.Routine.ViewRange
                    || Mathf.Abs(Mathf.DeltaAngle(h.Routine.EyeYaw, YawMath.YawOf(to))) > h.Routine.HalfAngle)
                {
                    continue;
                }
                inSight++;
                if (!sofas.Any(sofa => SegmentCrossesFootprint(dog, stool, sofa)))
                {
                    uncovered.Add(string.Format(CultureInfo.InvariantCulture, "stool ({0:0.00}, {1:0.00}) at {2:0.00} s, dog at ({3:0.00}, {4:0.00}) looking {5:0}",
                        stool.x, stool.z, Game.Elapsed, dog.x, dog.z, h.Routine.EyeYaw));
                }
            }
            return inSight;
        }

        /// <summary>True when the plan segment a to b crosses the yawed footprint of <paramref name="prop"/>.</summary>
        private static bool SegmentCrossesFootprint(Vector3 a, Vector3 b, PropDef prop)
        {
            const int Steps = 200;
            for (int i = 0; i <= Steps; i++)
            {
                Vector3 q = Vector3.Lerp(a, b, i / (float)Steps) - prop.Position;
                Vector3 local = Quaternion.Euler(0f, -prop.Yaw, 0f) * q;
                if (Mathf.Abs(local.x) <= prop.SizeX * 0.5f && Mathf.Abs(local.z) <= prop.SizeZ * 0.5f)
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>CONTRACT_M5 17 (critique 5A M4): granny's first sit on the armchair comes at about 8 s, never after this
        /// game time (wave 5A had it at 27 s, a dead wait at the spawn).</summary>
        private const float Level14FirstSitBy = 10f;

        /// <summary>
        /// Step 45c, level 14 "La mezzanine" (lesson split): the armchair climbs onto the platform (its floor reaches the
        /// platform height), granny sits on it at its place and nobody falls. 5A.1 (CONTRACT_M5 17, critique 5A M4): her
        /// first sit comes early (by <see cref="Level14FirstSitBy"/> s), so the level does not open on a long dead wait.
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step45c_Level14Routes()
        {
            yield return ReplayDesignerRoute("level14", (r, failures) =>
            {
                Assert.IsNotEmpty(Game.Def.Platforms, "premise: level 14 has a platform");
                if (r.TopY < Tuning.PlatformMinHeight - 0.05f)
                {
                    failures.Add($"{r.Label}: the armchair never climbed the platform (highest floor {r.TopY:0.00} m)");
                }
                if (r.SatOn == 0 || !r.Pinned || r.Pratfalls != 0)
                {
                    failures.Add($"{r.Label}: sat on {r.SatOn} time(s), pinned {r.Pinned}, {r.Pratfalls} pratfalls (the armchair must be home in time)");
                }
                if (r.Pinned && (r.FirstSatAt < 0f || r.FirstSatAt > Level14FirstSitBy))
                {
                    failures.Add($"{r.Label}: granny first sat on the armchair at {r.FirstSatAt:0.0} s, after {Level14FirstSitBy} s (a dead wait at the spawn)");
                }
            });
        }

        /// <summary>
        /// Step 45h (CONTRACT_M5 17, critique 5A B1; PRD 7.2 "found instantly in any frame"): at the start view of each
        /// wave 5A level, once the WallFader ran, nothing drawn on the Occluder layer stands between the camera and the top
        /// of the player furniture (Probe.ChairBlockers, the check of the built player's start view). Control: level 14's
        /// bookshelf at its wave 5A height (2 m) hides the armchair from the same view, so the check sees that blocker.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step45h_WaveALevelsStartWithTheFurnitureInView()
        {
            var failures = new List<string>();
            foreach (var (id, _, _, _, _) in WaveA)
            {
                yield return LoadFresh(id);
                yield return StartView();
                Camera cam = Game.Camera.GetComponent<Camera>();
                Assert.IsNotNull(cam, id + ": premise: no camera");
                List<string> blockers = Probe.ChairBlockers(cam, Game.Furniture);
                Debug.Log($"[Step45h] {id}: camera {cam.transform.position}, blockers: {string.Join(" / ", blockers)}");
                foreach (string b in blockers)
                {
                    failures.Add($"{id}: start view: {b}");
                }
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));

            // Control: the bookshelf of level 14 back at 2 m, rebuilt from the same definition.
            yield return LoadFresh("level14");
            PropDef shelf = Game.Def.Props.FirstOrDefault(p => p.Name == "Etagere");
            Assert.IsNotNull(shelf, "premise: level 14 has its bookshelf");
            Assert.Less(shelf.SizeY, 2f, "premise: the bookshelf is lower than its wave 5A 2 m");
            shelf.SizeY = 2f;
            Game.Restart();
            yield return Steps(1);
            yield return StartView();
            List<string> control = Probe.ChairBlockers(Game.Camera.GetComponent<Camera>(), Game.Furniture);
            Assert.IsTrue(control.Any(b => b.Contains("(Etagere)")),
                "control: the 2 m bookshelf does not hide the armchair at the start view, so the check proves nothing: "
                + string.Join(" / ", control));
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>Lets the start camera settle (25 fixed steps) and the WallFader apply its position (two rendered frames),
        /// as ProbeTestsM3Models.Step22b does.</summary>
        private static IEnumerator StartView()
        {
            yield return Steps(25);
            yield return null;
            yield return null;
        }

        // Step 45d (the level16 replay) is deleted by levels v2: level16 is cut (LEVELS_V2 D2), its door beat moved to level20.

        /// <summary>
        /// Step 45e, the counter-routes of the door level (CONTRACT_M5 12; CONTRACT_M5_v3 15.2: a leaf seen swinging is seen
        /// moving). (1) The designer route of level 8 rushed, every wait removed: it reaches its door while the dreamer
        /// still looks at it from the kitchen, so the swinging leaf is seen and the chair is caught. Premises: the door
        /// really starts opening, and the chair itself was never seen before (only the leaf can give it away).
        /// (2) The same route without its "open" step does not win: the closed leaf keeps the chair on the spawn side, and
        /// no door opens.
        /// </summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator Step45e_Level8CounterRoutes()
        {
            // (1) The rush.
            yield return LoadFresh("level8");
            List<RouteStepDef> route = Game.Def.DesignerRoute;
            string door = RouteDoor();
            Assert.IsNotNull(door, "premise: the route of level 8 has an open step");
            Assert.Greater(route.First(s => s.Action == RouteStepDef.ActionOpen).At, 3f, "premise: the designer route waits before opening");
            foreach (RouteStepDef s in route)
            {
                s.At = 0f;
            }
            var rush = new RouteReplayer.Result();
            yield return RouteReplayer.Replay(Game, 0f, rush, Tuning.PlaythroughTimeScale);
            Debug.Log("[Step45e] rushed: " + rush);
            Assert.GreaterOrEqual(rush.Opens, 1, "premise: the rushed route never started opening its door");
            Assert.IsFalse(rush.SeenBeforeOpen, "premise: the rushed chair was seen before the opening (the leaf would not be what gives it away)");
            Assert.AreNotEqual(PlayState.Won, rush.State, "the rushed route won: an opening in sight went unseen");
            Assert.AreEqual(PlayState.Caught, rush.State, $"the rushed route was not caught ({rush.State}, {rush.Reason})");
            Assert.AreEqual(LoseReason.SeenMoving, rush.Reason, "the rush was not caught seen moving");
            Assert.IsTrue(rush.LeafSeen, "the dreamer never saw the swinging leaf");
            Assert.LessOrEqual(rush.Time, rush.FirstOpenAt + Tuning.DoorOpenTime + 0.5f,
                $"the catch came at {rush.Time:0.00} s, long after the opening at {rush.FirstOpenAt:0.00} s (not the leaf's)");

            // (2) No opening.
            yield return LoadFresh("level8");
            route = Game.Def.DesignerRoute;
            DoorLeaf leaf = Game.Level.Leaves.FirstOrDefault(l => l.Id == door);
            Assert.IsNotNull(leaf, $"premise: level 8 has the leaf {door}");
            int removed = route.RemoveAll(s => s.Action == RouteStepDef.ActionOpen);
            Assert.GreaterOrEqual(removed, 1, "premise: an open step was removed");
            Vector3 spawn = Game.Def.Player.Position;
            // The spawn side of the leaf: the sign of the furniture's offset across the wall line, measured at the spawn.
            float across(Vector3 p) => leaf.Geometry.AlongX ? p.z - leaf.Geometry.Line : p.x - leaf.Geometry.Line;
            float side = Mathf.Sign(across(spawn));
            float worst = float.MaxValue;
            void Watch()
            {
                worst = Mathf.Min(worst, across(Game.Furniture.transform.position) * side);
            }
            Game.FixedStepped += Watch;
            var closed = new RouteReplayer.Result();
            try
            {
                yield return RouteReplayer.Replay(Game, 0f, closed, Tuning.PlaythroughTimeScale);
            }
            finally
            {
                Game.FixedStepped -= Watch;
            }
            Debug.Log($"[Step45e] without its opening: {closed}, closest to the far side {worst:0.00} m");
            Assert.Greater(closed.TopSpeed, 0.5f, "premise: the chair never drove");
            Assert.AreNotEqual(PlayState.Won, closed.State, "the route won without opening its door");
            Assert.AreEqual(0, closed.Opens + closed.DoorOpens, "a door opened with no open step");
            Assert.IsFalse(leaf.Open, "the leaf opened by itself");
            Assert.Greater(worst, 0f, "the chair got past the closed leaf");
        }

        /// <summary>The hide of level 12's designer route the uncovered line leaves from (levels v2): behind the middle sofa.</summary>
        private static readonly Vector2 Level12SofaHide = new Vector2(7.25f, 7.25f);

        /// <summary>The uncovered line of level 12 (5A.1 M5, redrawn for the v2 salon): from the hide behind the middle sofa,
        /// west to the gap between the two sofas, south through it into the open salon in front of them, then straight
        /// east to the entree door and the exit; careful legs, so the stool never tips.</summary>
        private static readonly Vector2[] Level12UncoveredLine =
        {
            new Vector2(6.25f, 7.25f), new Vector2(6.25f, 6.25f), new Vector2(6.25f, 5.25f), new Vector2(7.25f, 5.25f),
            new Vector2(8.25f, 5.25f), new Vector2(9.25f, 5.25f), new Vector2(9.75f, 5.75f), new Vector2(10.75f, 5.75f),
            new Vector2(11.75f, 6.25f),
        };

        /// <summary>
        /// Step 45g, the counter-route of the dog level (CONTRACT_M5 17, critique 5A M5: the lesson has teeth). Redrawn for
        /// levels v2 (Rex no longer naps, he turns on his spot): the designer route up to its hide behind the middle sofa,
        /// then, instead of waiting there, the line through the gap between the sofas and east in front of them runs in the
        /// awake dog's sight: the dog barks, a human within his hearing radius of the bark turns toward it (an alert), and
        /// the run does not win: he sees the stool moving and catches it. Premises: the bark comes on the uncovered line
        /// (after it left the hide), no human saw the stool before the first bark (the bark is what turns him), the alert
        /// follows the bark, and the human alerted stood within Tuning.BarkRadius times his hearing factor of the bark.
        /// </summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator Step45g_Level12UncoveredCrossingBarksAndLoses()
        {
            yield return LoadFresh("level12");
            InhabitantDef dog = Game.Def.Inhabitants.FirstOrDefault(h => h.Kind == PersonalityDef.Dog);
            Assert.IsNotNull(dog, "premise: level 12 has a dog");
            Assert.IsFalse(dog.Stations[dog.StartStation].Sleep, "premise: the dog starts awake");
            List<RouteStepDef> route = Game.Def.DesignerRoute;
            Assert.GreaterOrEqual(route.Count, 2, "premise: level 12 has a designer route");
            int hide = route.FindIndex(s => Mathf.Abs(s.X - Level12SofaHide.x) < 0.01f && Mathf.Abs(s.Z - Level12SofaHide.y) < 0.01f);
            Assert.GreaterOrEqual(hide, 1, $"premise: the designer route of level 12 passes its hide behind the middle sofa {Level12SofaHide}");
            Vector2 end = Level12UncoveredLine[Level12UncoveredLine.Length - 1];
            Assert.IsTrue(Game.Def.Exit.Contains(new Vector3(end.x, 0f, end.y)), "premise: the uncovered line ends on the exit");
            // The designer route up to its hide, then the uncovered line at once (each leg departs as the previous one ends).
            route.RemoveRange(hide + 1, route.Count - hide - 1);
            float leaveAt = route[hide].At + 0.7f;
            float at = leaveAt;
            foreach (Vector2 p in Level12UncoveredLine)
            {
                route.Add(new RouteStepDef { X = p.x, Z = p.y, At = at, Careful = true });
                at += 0.1f;
            }

            int barks0 = Game.BarkCount;
            int alerts0 = Game.AlertCount;
            float firstBark = -1f;
            float firstAlert = -1f;
            bool seenBeforeBark = false;
            string alerted = null;
            float alertedDistance = -1f;
            float alertedRadius = -1f;
            Vector3 barkAt = Vector3.zero;
            void Watch()
            {
                if (firstBark < 0f && Game.BarkCount > barks0)
                {
                    firstBark = Game.Elapsed;
                    barkAt = Game.LastBarkAt;
                }
                seenBeforeBark |= firstBark < 0f && Game.Seen;
                if (firstAlert < 0f && Game.AlertCount > alerts0)
                {
                    firstAlert = Game.Elapsed;
                    foreach (Inhabitant h in Game.Level.Inhabitants)
                    {
                        if (h.Routine.Mode == InhabitantMode.Alerted && alerted == null)
                        {
                            alerted = h.Def.Name;
                            alertedDistance = YawMath.Planar(h.Routine.Position - barkAt).magnitude;
                            alertedRadius = Tuning.BarkRadius * h.Routine.HearingFactor;
                        }
                    }
                }
            }
            Game.FixedStepped += Watch;
            var r = new RouteReplayer.Result();
            try
            {
                yield return RouteReplayer.Replay(Game, 0f, r, Tuning.PlaythroughTimeScale);
            }
            finally
            {
                Game.FixedStepped -= Watch;
            }
            Debug.Log($"[Step45g] {r}; first bark at {firstBark:0.00} s, first alert at {firstAlert:0.00} s ({alerted}, "
                      + $"{alertedDistance:0.00} m from the bark, hears it within {alertedRadius:0.00} m), seen before the bark {seenBeforeBark}");
            Assert.Greater(r.TopSpeed, 0.3f, "premise: the stool never drove");
            Assert.GreaterOrEqual(r.Barks, 1, "the dog never barked at the stool crossing in front of the sofas");
            Assert.GreaterOrEqual(firstBark, leaveAt - 1e-3f, $"premise: the bark came at {firstBark:0.00} s, before the stool left its hide at {leaveAt:0.0} s (not the uncovered line's)");
            Assert.IsFalse(seenBeforeBark, "premise: a human saw the stool before the bark (the bark would not be what turns him)");
            Assert.GreaterOrEqual(r.Alerts, 1, "nobody heard the bark: no human turned");
            Assert.GreaterOrEqual(firstAlert, firstBark, "premise: the first alert came before the bark");
            Assert.IsNotNull(alerted, "premise: no human was alerted on the alert step");
            Assert.LessOrEqual(alertedDistance, alertedRadius + 1e-3f, $"premise: {alerted} heard the bark from beyond his radius");
            Assert.AreNotEqual(PlayState.Won, r.State, "the uncovered line won although the dog barked");
            Assert.AreEqual(PlayState.Caught, r.State, $"the uncovered line was not caught ({r.State}, {r.Reason}) after {r.Time:0.0} s");
            Assert.Greater(r.Time, firstAlert, "the catch came before the alert (not the turned human's)");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- 45a and 45f: boot and the replayer -----

        /// <summary>
        /// Step 45a (CONTRACT_M5 8, 16.2, 16.10; levels v2): levels.json lists levels 8, 12 and 14 (the v2 order is checked by
        /// LevelDataM2Tests, not here). Each one boots through GameState.LoadLevel with no error, with its body, its lesson,
        /// its humans and its dog, and 3 s of game time with no input leave it playing: an idle player at its spawn is never
        /// caught.
        /// </summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator Step45a_WaveALevelsBootAndAnIdlePlayerIsNeverCaught()
        {
            List<string> order = Game.LevelOrder.ToList();
            foreach (var level in WaveA)
            {
                Assert.GreaterOrEqual(order.IndexOf(level.id), 0, $"{level.id} is not listed in levels.json: {string.Join(", ", order)}");
            }
            var failures = new List<string>();
            foreach ((string id, string body, string lesson, int humans, int dogs) in WaveA)
            {
                int errorsBefore = errors.Count;
                Game.LoadLevel(id);
                yield return Steps(1);
                Assert.AreEqual(id, Game.LevelId, "premise: the level was loaded");
                Assert.IsNotNull(Game.Level, id + ": premise: the level was built");
                LevelDef def = Game.Def;
                if (def.Lesson != lesson || def.Player.Kind != body || Game.Furniture.Body.Kind != body)
                {
                    failures.Add($"{id}: lesson {def.Lesson} (wants {lesson}), body {def.Player.Kind} built as {Game.Furniture.Body.Kind} (wants {body})");
                }
                int dogCount = def.Inhabitants.Count(h => h.Kind == PersonalityDef.Dog);
                int humanCount = def.Inhabitants.Count - dogCount;
                if (humanCount != humans || dogCount != dogs)
                {
                    failures.Add($"{id}: {humanCount} human(s) and {dogCount} dog(s) (wants {humans} and {dogs})");
                }
                if (def.Inhabitants.Any(h => h.Kind != PersonalityDef.Dog && string.IsNullOrEmpty(h.Personality)))
                {
                    failures.Add($"{id}: a human without a personality");
                }
                if (Game.Level.Inhabitants.Count != def.Inhabitants.Count)
                {
                    failures.Add($"{id}: {Game.Level.Inhabitants.Count} inhabitants built for {def.Inhabitants.Count} in the data");
                }
                float start = Game.Elapsed;
                yield return RouteReplayer.RunFor(Game, 3f, () => Game.State != PlayState.Playing, Tuning.PlaythroughTimeScale);
                if (Game.State == PlayState.Playing)
                {
                    Assert.GreaterOrEqual(Game.Elapsed - start, 3f - 1e-3f, $"{id}: premise: 3 s of game time ran");
                }
                if (Game.State != PlayState.Playing)
                {
                    failures.Add($"{id}: an idle player at its spawn ended the level ({Game.State}, {Game.LoseReason}) at {Game.Elapsed:0.0} s");
                }
                if (errors.Count != errorsBefore)
                {
                    failures.Add($"{id}: error(s) logged: {string.Join(" | ", errors.Skip(errorsBefore))}");
                }
                Debug.Log($"[Step45a] {id}: {def.AllRooms().Count} rooms, {humanCount} human(s), {dogCount} dog(s), body {Game.Furniture.Body.Kind}, "
                          + $"lesson {def.Lesson}, {Game.State} at {Game.Elapsed:0.0} s");
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }

        /// <summary>
        /// Step 45f (CONTRACT_M5 8 and 16.11, CONTRACT_M5_v3 15.2): RouteReplayer's "open" step waits for the furniture to
        /// be still, presses E, and presses again when no action starts, at most RouteReplayer.MaxOpenPresses times; then it
        /// gives the step up and the route goes on. On level 1 (no leaf) an "open" step inserted while the designer route
        /// waits at the spawn starts nothing: every press is made, the step is given up once, no opening is counted, and the
        /// route still wins, so the step costs no time. Premise: the route waits long enough there.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step45f_ReplayerRetriesAnOpenThatStartsNothingThenGoesOn()
        {
            yield return LoadFresh("level1");
            List<RouteStepDef> route = Game.Def.DesignerRoute;
            Assert.GreaterOrEqual(route.Count, 3, "premise: level 1 has a designer route");
            Assert.IsEmpty(Game.Def.Doors.Where(d => !string.IsNullOrEmpty(d.Leaf)), "premise: level 1 has no leaf");
            // The route waits at the spawn before its first leg: the open step goes there, pressed from 0.2 s on.
            Assert.GreaterOrEqual(route[0].At, 1.5f, "premise: the route of level 1 waits 1.5 s at the spawn");
            SpawnDef spawn = Game.Def.Player;
            route.Insert(0, new RouteStepDef { X = spawn.X, Z = spawn.Z, At = 0.2f, Action = RouteStepDef.ActionOpen, Door = "none" });
            var r = new RouteReplayer.Result();
            yield return RouteReplayer.Replay(Game, 0f, r, Tuning.PlaythroughTimeScale);
            Debug.Log("[Step45f] " + r);
            Assert.AreEqual(RouteReplayer.MaxOpenPresses, r.OpenPresses, "every press of the open step is made, and no more");
            Assert.AreEqual(1, r.OpenFailures, "the open step is given up once");
            Assert.AreEqual(0, r.Opens, "no opening on a level without leaves");
            // A winning route stops as the furniture enters the exit, before its last waypoint or two (as in M4).
            Assert.Greater(r.Waypoint, 1, "the route went on past the open step");
            Assert.AreEqual(PlayState.Won, r.State, $"the route with an empty open step did not win ({r.State}, {r.Reason})");
            Assert.IsFalse(r.TimedOut || r.Stalled, "the run ended on its own");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- 45i to 45r: wave 5B (levels 9, 10, 11, 13, 15 and 17) -----

        /// <summary>The wave 5B levels (CONTRACT_M5 16.10, as retuned by levels v2), with their body, lesson, people, robots and
        /// load. level10 is cut (LEVELS_V2 D2) but still boots by id as an archived file; level15 is the v2 rocker level
        /// (Mamie and napping Rex, no robot).</summary>
        private static readonly (string id, string body, string lesson, int humans, int dogs, int robots, string load)[] WaveB =
        {
            ("level9", BodyKinds.Chair, LevelDef.LessonRobot, 1, 0, 1, null),
            ("level10", BodyKinds.RockingChair, LevelDef.LessonRock, 1, 0, 0, null),
            ("level11", BodyKinds.Chair, LevelDef.LessonLoad, 1, 0, 0, LoadView.Vase),
            ("level13", BodyKinds.OfficeChair, LevelDef.LessonLoad, 2, 0, 0, LoadView.Vase),
            ("level15", BodyKinds.RockingChair, LevelDef.LessonRock, 1, 1, 0, null),
            ("level17", BodyKinds.Chair, LevelDef.LessonFinal, 2, 1, 1, LoadView.Vase), // L16EASY: Mamie and Lea (Hugo removed)
        };

        /// <summary>
        /// Step 45i, level 9 "Le robot" (lesson robot, CONTRACT_M5 10 and 16.8): the route plays the hum: the robot's hum masks
        /// at least one of its noises (the north band is in Claire's earshot, on a hard floor).
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step45i_Level9Routes()
        {
            yield return ReplayDesignerRoute("level9", (r, failures) =>
            {
                Assert.AreEqual(1, Game.Robots.Count, "premise: level 9 has its robot");
                if (r.MaskedNoises < 1)
                {
                    failures.Add($"{r.Label}: the hum masked none of the route's noises: the route does not play the robot lesson");
                }
            });
        }

        // Step 45j (the level10 replay) is deleted by levels v2: level10 is cut (LEVELS_V2 D2), its rock lesson moved to
        // level15 (Step 45m).

        /// <summary>
        /// Step 45k, level 11 "Le vase" (lesson load, CONTRACT_M5 6 and 16.5): the vase rides on the chair to the exit (the
        /// replay is the load's final arbiter; checked for every route).
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step45k_Level11Routes()
        {
            yield return ReplayDesignerRoute("level11", (r, failures) =>
            {
                Assert.IsTrue(r.HasLoad, "premise: level 11 gives the chair its vase");
                Assert.AreEqual(LoadView.Vase, Game.LoadView.Kind, "premise: the load of level 11 is the vase");
            });
        }

        /// <summary>
        /// Step 45l, level 13 "Roulettes et vase" (lesson load): the vase rides on the office chair to the exit, and the
        /// office chair decoys explain it at least once.
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step45l_Level13Routes()
        {
            yield return ReplayDesignerRoute("level13", (r, failures) =>
            {
                Assert.IsTrue(r.HasLoad, "premise: level 13 gives the office chair its vase");
                Assert.IsTrue(Game.Furniture.Body.Glides, "premise: the body of level 13 glides");
                if (r.Explained < 1)
                {
                    failures.Add($"{r.Label}: no decoy ever explained the office chair: the route ignores its decoys");
                }
            });
        }

        /// <summary>Levels v2 (LEVELS_V2 5, level15): "every stop swings": the rocker route stops and rocks at least this often
        /// (the audit's route rocks 4 times; 3 leaves room for a stop merged by an offset).</summary>
        private const int Level15MinRocks = 3;

        /// <summary>
        /// Step 45m, level 15 "Chien qui dort" (levels v2 rebuild, lesson rock, D4 and D20): the rocking chair hops down the
        /// hall while napping Rex sleeps and rocks after its stops (at least <see cref="Level15MinRocks"/> times) with no rock
        /// seen and no bark (the run wins). Premises: the body rocks, the level has its dog and no robot.
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step45m_Level15Routes()
        {
            yield return ReplayDesignerRoute("level15", (r, failures) =>
            {
                Assert.AreEqual(0, Game.Robots.Count, "premise: level 15 has no robot in v2 (D20)");
                Assert.IsTrue(Game.Def.Inhabitants.Any(h => h.Kind == PersonalityDef.Dog), "premise: level 15 has its dog (Rex)");
                Assert.IsTrue(Game.Furniture.Body.Rocks, "premise: the body of level 15 rocks");
                if (r.Rocks < Level15MinRocks)
                {
                    failures.Add($"{r.Label}: {r.Rocks} rocks, the rocker route must rock at least {Level15MinRocks} times (every stop swings)");
                }
            });
        }

        /// <summary>
        /// Step 45n, level 17 "La maison" (lesson final, CONTRACT_M5 10): the route plays at least three of the house's
        /// mechanics: a door opened, the hum masking a noise, the mezzanine climbed, the vase carried to the exit.
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step45n_Level17Routes()
        {
            yield return ReplayDesignerRoute("level17", (r, failures) =>
            {
                Assert.IsTrue(r.HasLoad, "premise: level 17 gives the chair its vase");
                Assert.AreEqual(1, Game.Robots.Count, "premise: level 17 has its robot");
                var played = new List<string>();
                if (r.DoorOpens >= 1)
                {
                    played.Add("door");
                }
                if (r.MaskedNoises >= 1)
                {
                    played.Add("robot");
                }
                if (r.TopY >= Tuning.PlatformMinHeight - 0.05f)
                {
                    played.Add("split");
                }
                if (r.HasLoad && r.LoadHeld)
                {
                    played.Add("load");
                }
                if (played.Count < 3)
                {
                    failures.Add($"{r.Label}: the route plays {played.Count} mechanic(s) ({string.Join(", ", played)}), the final lesson needs 3");
                }
            });
        }

        /// <summary>
        /// Drives the furniture through <paramref name="legs"/> (planar x, z) at full input, careful when asked, from game time
        /// <paramref name="from"/>: straight at each point, released within 0.1 m, then no input. Runs until
        /// <paramref name="until"/> holds or game time reaches <paramref name="cap"/>; <paramref name="done"/>[0] is the game
        /// time the last point was reached (-1 when never).
        /// </summary>
        private IEnumerator DriveLegs(IList<Vector2> legs, float from, bool careful, Func<bool> until, float cap, float[] done)
        {
            int k = 0;
            done[0] = -1f;
            void Drive()
            {
                FurnitureController f = Game.Furniture;
                f.ScriptedCareful = careful;
                if (Game.State != PlayState.Playing || Game.Elapsed < from - 1e-4f || k >= legs.Count)
                {
                    f.ScriptedDirection = null;
                    return;
                }
                while (k < legs.Count)
                {
                    Vector3 to = YawMath.Planar(new Vector3(legs[k].x, 0f, legs[k].y) - f.transform.position);
                    if (to.magnitude > 0.1f)
                    {
                        f.ScriptedDirection = to.normalized;
                        return;
                    }
                    k++;
                }
                f.ScriptedDirection = null;
                done[0] = Game.Elapsed;
            }
            Game.FixedStepped += Drive;
            try
            {
                yield return RouteReplayer.RunUntil(Game, cap, until, Tuning.PlaythroughTimeScale, new bool[1]);
            }
            finally
            {
                Game.FixedStepped -= Drive;
                Game.Furniture.ScriptedDirection = null;
                Game.Furniture.ScriptedCareful = null;
            }
        }

        /// <summary>Replaces the current level's designer route with <paramref name="steps"/> (rows of x, z, at; full speed).</summary>
        private void SetRoute(float[,] steps)
        {
            List<RouteStepDef> route = Game.Def.DesignerRoute;
            route.Clear();
            for (int i = 0; i < steps.GetLength(0); i++)
            {
                route.Add(new RouteStepDef { X = steps[i, 0], Z = steps[i, 1], At = steps[i, 2] });
            }
        }

        /// <summary>Level 9's robot lane in levels v2 (LEVELS_V2 5, level9): the north band, z 8.25.</summary>
        private const float Level9LaneZ = 8.25f;

        /// <summary>The lane x from which level 9's designer route leaves the lane (the dodge east of the console): the wait
        /// of Step 45o is the route's first waypoint in the lane at or past it.</summary>
        private const float Level9LaneWaitMinX = 9.5f;

        /// <summary>
        /// Step 45o, the robot collision on level 9 (CONTRACT_M5 4, 12 and 16.8; redrawn for the v2 lane, z 8.25): the chair
        /// rides behind the robot in its hum along the north lane (the designer route up to the point where it dodges the
        /// bumper), then stays in the lane instead of dodging. The robot, coming back west from the lane's east end, touches
        /// the still chair: the chair is shoved once, RobotPushDistance along the robot's heading (west), every step of the
        /// shove counts as moving, and the robot reverses its loop (it heads east again). Premises: the robot starts east
        /// along z 8.25, the chair reached its wait while the level was playing and stood still for 0.5 s before the contact,
        /// and the robot was heading west at the contact.
        /// </summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator Step45o_Level9RobotCollisionShovesTheChairAndTheRobotTurnsBack()
        {
            yield return LoadFresh("level9");
            Assert.AreEqual(1, Game.Robots.Count, "premise: level 9 has one robot");
            Robot robot = Game.Robots[0];
            RobotPath path = robot.Path;
            Assert.Greater(path.ForwardAt(0f).x, 0.99f, "premise: the robot starts east along its lane");
            Assert.AreEqual(Level9LaneZ, path.PositionAt(0f).z, 0.01f, $"premise: the robot's lane runs at z {Level9LaneZ}");
            List<RouteStepDef> designer = Game.Def.DesignerRoute;
            int wait = designer.FindIndex(s => s.X >= Level9LaneWaitMinX - 1e-3f && Mathf.Abs(s.Z - Level9LaneZ) < 0.01f);
            Assert.GreaterOrEqual(wait, 1, "premise: the designer route of level 9 rides the lane to its dodge point");
            var lane = designer.GetRange(0, wait + 1);
            var waitAt = new Vector2(lane[wait].X, lane[wait].Z);
            int contacts0 = Game.RobotContactCount;
            int shoves0 = Game.ShoveCount;
            int reverses0 = path.ReverseCount;
            float contactAt = -1f;
            float shoveEndAt = -1f;
            float reachedAt = -1f;
            int still = 0;
            int stillAtContact = -1;
            int shoveSteps = 0;
            int movingShoveSteps = 0;
            int reversesAtEnd = reverses0;
            Vector3 before = Game.Furniture.transform.position;
            Vector3 after = before;
            Vector3 heading = Vector3.zero;
            Vector3 robotAtContact = Vector3.zero;
            Vector3 robotAfter = Vector3.zero;
            PlayState stateAtContact = PlayState.Playing;
            void Watch()
            {
                FurnitureController f = Game.Furniture;
                if (reachedAt < 0f && YawMath.Planar(f.transform.position - new Vector3(waitAt.x, 0f, waitAt.y)).magnitude < 0.15f)
                {
                    reachedAt = Game.Elapsed;
                }
                if (contactAt < 0f)
                {
                    if (Game.RobotContactCount > contacts0)
                    {
                        contactAt = Game.Elapsed;
                        stillAtContact = still;
                        heading = Game.LastShoveDirection;
                        robotAtContact = path.ForwardAt(Game.RobotTime);
                        stateAtContact = Game.State;
                        return;
                    }
                    still = f.IsMoving ? 0 : still + 1;
                    before = f.transform.position;
                    return;
                }
                if (shoveEndAt < 0f)
                {
                    if (Game.Shoving)
                    {
                        shoveSteps++;
                        movingShoveSteps += Game.FurnitureMoving ? 1 : 0;
                        return;
                    }
                    shoveEndAt = Game.Elapsed;
                    after = f.transform.position;
                    robotAfter = path.ForwardAt(Game.RobotTime);
                    reversesAtEnd = path.ReverseCount;
                }
            }
            var r = new RouteReplayer.Result();
            Game.FixedStepped += Watch;
            try
            {
                yield return RouteReplayer.Replay(Game, 0f, r, Tuning.PlaythroughTimeScale, lane);
            }
            finally
            {
                Game.FixedStepped -= Watch;
            }
            Vector3 moved = YawMath.Planar(after - before);
            Debug.Log($"[Step45o] {r}; wait {waitAt} reached at {reachedAt:0.00} s, contact at {contactAt:0.00} s after {stillAtContact} still steps, "
                      + $"robot heading {robotAtContact}, shove {shoveSteps} steps ({movingShoveSteps} moving) heading {heading}, moved {moved} "
                      + $"({moved.magnitude:0.000} m), robot reversals {reversesAtEnd - reverses0}, then heading {robotAfter}, {r.MaskedNoises} noises masked");
            Assert.GreaterOrEqual(reachedAt, 0f, $"premise: the chair never reached its wait in the robot's lane ({r.State}, {r.Reason})");
            Assert.GreaterOrEqual(contactAt, 0f, "the robot never touched the chair standing in its lane");
            Assert.AreEqual(PlayState.Playing, stateAtContact, "premise: the level ended before the contact");
            Assert.GreaterOrEqual(stillAtContact, 25, "premise: the chair was not still for 0.5 s before the contact");
            Assert.Less(robotAtContact.x, -0.99f, $"premise: the robot was not heading west at the contact ({robotAtContact})");
            Assert.AreEqual(1, Game.ShoveCount - shoves0, "the contact did not shove the chair exactly once");
            Assert.Less(heading.x, -0.99f, $"the shove was not along the robot's heading west ({heading})");
            Assert.AreEqual(Mathf.RoundToInt(Tuning.RobotPushTime / Time.fixedDeltaTime), shoveSteps, "the shove did not last RobotPushTime");
            Assert.AreEqual(shoveSteps, movingShoveSteps, "a step of the shove did not count as moving");
            Assert.GreaterOrEqual(shoveEndAt, 0f, "the shove never ended");
            Assert.AreEqual(-Tuning.RobotPushDistance, moved.x, 0.05f, $"the shove moved the chair {moved.x:0.000} m along x, not {-Tuning.RobotPushDistance} m (west)");
            Assert.AreEqual(0f, moved.z, 0.05f, "the shove moved the chair across the robot's heading");
            Assert.Greater(reversesAtEnd, reverses0, "the robot did not reverse its loop after the contact");
            Assert.Greater(robotAfter.x, 0.99f, "the robot does not head back east after the contact");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>
        /// The schedule the wave 5B audit finds on level 10 with the rock off: the counter-route its rock lesson prints
        /// ("lecon rock : ... contre-route : [...]", LevelAudit on level10, 2026-11-15). The chair stretches out of its home
        /// and back while Mamie looks away, stops at home (where, with the rock on, it rocks in her sight at 9.6 s), then
        /// runs to the veranda and the exit behind her back. A rocking chair's route chains the waypoints of a run (same
        /// "at"), which RouteReplayer drives without a stop. Step 45p replays it as the rock's counter-route. Rows are x, z,
        /// at. A new layout of level 10 needs a new one, copied from the same audit note.
        /// </summary>
        private static readonly float[,] Level10RouteWithoutTheRock =
        {
            { 5.75f, 5.75f, 6.2f }, { 5.75f, 5.25f, 6.8f }, { 6.25f, 5.25f, 6.8f }, { 6.25f, 6.25f, 6.8f }, { 5.75f, 6.25f, 6.8f },
            { 6.25f, 6.25f, 11.1f }, { 6.25f, 5.25f, 11.1f }, { 6.25f, 4.25f, 11.1f }, { 6.25f, 3.25f, 11.1f }, { 6.25f, 2.25f, 11.1f },
            { 6.25f, 1.25f, 11.1f }, { 7.25f, 1.25f, 11.1f }, { 8.25f, 1.25f, 11.1f }, { 9.25f, 1.25f, 11.1f }, { 10.25f, 1.25f, 11.1f },
            { 11.25f, 1.25f, 11.1f }, { 12.25f, 1.25f, 11.1f }, { 13.25f, 1.25f, 11.1f }, { 14.25f, 1.25f, 11.1f }, { 14.25f, 1.25f, 11.1f },
        };

        /// <summary>
        /// Step 45p, the rock seen on level 10 (CONTRACT_M5 10 and 12, lesson rock: the schedule computed without rocking is
        /// seen rocking). The schedule the audit finds with no rock wins with the rock switched off (GameRules.Bodies false,
        /// which on the rocking chair gates only the rock): it is a valid schedule of the level without the rock. With the
        /// rock on, the same schedule rocks after its stops and is caught seen moving, after its first rock: either seen
        /// during a rock (the audit's reading, which keeps the schedule's times) or seen in a move a rock delayed (the replay
        /// keeps steering through a rock, so a rock after an early stop pushes the next chained legs into the watcher's look;
        /// on the 2026-11-15 layout the rock after the first hop delays the return home into Mamie's look at 9.7 s).
        /// </summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator Step45p_Level10RouteWithoutTheRockIsSeenRocking()
        {
            // (1) The control: no rock.
            yield return LoadFresh("level10");
            if (Game.Def.LessonAdvisory)
            {
                // M6b waiver (CONTRACT_M6 5): no rock lesson binds on level 10, so its counter-route proves nothing.
                Assert.Pass("level 10's rock lesson is advisory (CONTRACT_M6 5)");
            }
            Assert.IsTrue(Game.Furniture.Body.Rocks, "premise: the body of level 10 rocks");
            Assert.IsFalse(Game.Furniture.Body.Glides || Game.Furniture.Body.Tips || Game.Furniture.Body.HasLight,
                "premise: GameRules.Bodies gates nothing else on the rocking chair");
            SetRoute(Level10RouteWithoutTheRock);
            Game.Rules.Bodies = false;
            var off = new RouteReplayer.Result();
            yield return RouteReplayer.Replay(Game, 0f, off, Tuning.PlaythroughTimeScale);
            Debug.Log("[Step45p] without the rock: " + off);
            Assert.AreEqual(0, off.Rocks, "premise: the chair rocked with GameRules.Bodies off");
            Assert.AreEqual(PlayState.Won, off.State, $"premise: the schedule found without the rock does not win without it ({off.State}, {off.Reason})");

            // (2) The rock on: the same schedule is seen rocking.
            yield return LoadFresh("level10");
            SetRoute(Level10RouteWithoutTheRock);
            Assert.IsEmpty(Game.Def.Doors.FindAll(d => d.Leaf == OpeningDef.LeafClosed), "premise: level 10 has no door to open, so its only External action is the rock");
            // What the run showed before the catch: the first rock, and whether a watcher saw the furniture during a rock.
            float firstRockAt = -1f;
            float seenRockingAt = -1f;
            void Watch()
            {
                FurnitureController f = Game.Furniture;
                if (Game.RockCount > 0 && firstRockAt < 0f)
                {
                    firstRockAt = Game.Elapsed;
                }
                bool rocking = Game.RockCount > 0 && f.ActionActive && f.Action == FurnitureController.BodyAction.External;
                if (seenRockingAt < 0f && Game.Seen && rocking)
                {
                    seenRockingAt = Game.Elapsed;
                }
            }
            Game.FixedStepped += Watch;
            var on = new RouteReplayer.Result();
            try
            {
                yield return RouteReplayer.Replay(Game, 0f, on, Tuning.PlaythroughTimeScale);
            }
            finally
            {
                Game.FixedStepped -= Watch;
            }
            Debug.Log($"[Step45p] with the rock: {on}; first rock at {firstRockAt:0.00} s, first seen during a rock at {seenRockingAt:0.00} s "
                      + (seenRockingAt >= 0f ? "(caught by a rock seen)" : "(caught in a move a rock delayed)"));
            Assert.GreaterOrEqual(on.Rocks, 1, "the rocking chair never rocked on the schedule");
            Assert.AreNotEqual(PlayState.Won, on.State, "the schedule found without the rock still wins with it: the rock lesson does not bind");
            Assert.AreEqual(PlayState.Caught, on.State, $"the schedule with the rock was not caught ({on.State}, {on.Reason})");
            Assert.AreEqual(LoseReason.SeenMoving, on.Reason, "the rocking chair was not caught seen moving");
            Assert.GreaterOrEqual(firstRockAt, 0f, "premise: no rock started during the run");
            Assert.Less(firstRockAt, on.Time, $"the catch at {on.Time:0.00} s came before the first rock at {firstRockAt:0.00} s: the rock did not cause it");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>
        /// The schedule the audit finds on level 11 with the load rule off: the counter-route its load lesson prints ("lecon
        /// load : ... contre-route : [...]", LevelAudit on level11; the wave 5A audit wrote the same one): at full speed
        /// through the bedroom door, down the corridor and across the kitchen, turning every corner at full speed. Step 45q
        /// replays it as the load's counter-route. Rows are x, z, at. A new layout of level 11 needs a new one, copied from
        /// the same audit note.
        /// </summary>
        private static readonly float[,] Level11RouteAtFullSpeed =
        {
            { 3.25f, 6.25f, 0.3f }, { 3.75f, 6.25f, 1.1f }, { 3.75f, 7.25f, 1.5f }, { 3.75f, 7.75f, 2.3f }, { 4.75f, 7.75f, 2.7f },
            { 5.25f, 7.75f, 3.5f }, { 5.25f, 6.75f, 3.9f }, { 5.25f, 5.75f, 4.7f }, { 5.25f, 4.75f, 5.5f }, { 5.25f, 3.75f, 6.3f },
            { 5.25f, 2.75f, 7.1f }, { 5.25f, 1.75f, 7.9f }, { 5.25f, 1.25f, 8.7f }, { 6.25f, 1.25f, 9.1f }, { 7.25f, 1.25f, 9.9f },
            { 8.25f, 1.25f, 10.7f }, { 9.25f, 1.25f, 11.5f }, { 10.25f, 1.25f, 12.3f }, { 11.25f, 1.25f, 13.1f }, { 11.25f, 1.75f, 13.9f },
            { 11.25f, 1.75f, 13.9f },
        };

        /// <summary>
        /// Step 45q, the vase dropped at full speed on level 11 (CONTRACT_M5 6, 12 and 16.5, lesson load). The schedule the
        /// audit finds with no load rule, replayed at full speed, drops the vase: on a corner (the velocity of the fall step
        /// is at least 60 deg from the velocity 0.5 s earlier, so a straight start or stop is not what drops it), with a
        /// crash, the load view fallen and the peak change of velocity past the threshold. The same legs in careful mode keep
        /// the vase over the same corners (premise: they drive past at least three of them).
        /// </summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator Step45q_Level11FullSpeedRouteDropsTheVase()
        {
            // (1) Full speed.
            yield return LoadFresh("level11");
            Assert.IsNotNull(Game.Load, "premise: level 11 gives the chair a load");
            Assert.IsTrue(Game.CarryingLoad, "premise: the vase rides at the start");
            SetRoute(Level11RouteAtFullSpeed);
            var history = new Queue<Vector3>();
            int window = Mathf.RoundToInt(Tuning.LoadWindow / Time.fixedDeltaTime);
            int crashes0 = Game.CrashCount;
            float fallAt = -1f;
            float turn = -1f;
            float peak = 0f;
            void Watch()
            {
                Vector3 v = YawMath.Planar(Game.Furniture.Velocity);
                history.Enqueue(v);
                while (history.Count > window + 1)
                {
                    history.Dequeue();
                }
                if (fallAt < 0f && Game.CrashCount > crashes0)
                {
                    fallAt = Game.Elapsed;
                    Vector3 then = history.Peek();
                    turn = then.sqrMagnitude > 0.01f && v.sqrMagnitude > 0.01f ? Vector3.Angle(then, v) : 0f;
                    peak = Game.Load.PeakDeltaV;
                }
            }
            Game.FixedStepped += Watch;
            var fast = new RouteReplayer.Result();
            try
            {
                yield return RouteReplayer.Replay(Game, 0f, fast, Tuning.PlaythroughTimeScale);
            }
            finally
            {
                Game.FixedStepped -= Watch;
            }
            Debug.Log($"[Step45q] full speed: {fast}; fall at {fallAt:0.00} s, turned {turn:0} deg over the window, peak dv {peak:0.00} m/s");
            Assert.Greater(fast.TopSpeed, 1.2f, "premise: the chair never drove at full speed");
            Assert.GreaterOrEqual(fast.Crashes, 1, "the full-speed schedule never dropped the vase");
            Assert.IsFalse(fast.LoadHeld, "the vase still rides after a crash");
            Assert.GreaterOrEqual(fallAt, 0f, "premise: the fall step was not seen");
            Assert.GreaterOrEqual(turn, 60f, $"the vase fell on a turn of {turn:0} deg over the window, not on a corner");
            Assert.GreaterOrEqual(peak, Tuning.LoadFallDeltaV, $"the peak change of velocity {peak:0.00} m/s is under the fall threshold");
            Assert.IsTrue(Game.LoadView != null && Game.LoadView.Fallen, "the load view does not show the fall");

            // (2) The same legs, careful: the vase holds over the corners.
            yield return LoadFresh("level11");
            SetRoute(Level11RouteAtFullSpeed);
            foreach (RouteStepDef s in Game.Def.DesignerRoute)
            {
                s.Careful = true;
            }
            var careful = new RouteReplayer.Result();
            yield return RouteReplayer.Replay(Game, 0f, careful, Tuning.PlaythroughTimeScale);
            Debug.Log($"[Step45q] careful: {careful}");
            Assert.GreaterOrEqual(careful.Waypoint, 7, "premise: the careful legs did not drive past three corners");
            Assert.Less(careful.TopSpeed, 1.0f, "premise: the careful legs ran at full speed");
            Assert.AreEqual(0, careful.Crashes, "the careful legs dropped the vase");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>
        /// Step 45r (CONTRACT_M5 16.10): the wave 5B levels boot through GameState.LoadLevel with no error, with their body,
        /// lesson, humans and dog, the robots of their data (built by the level, one per RobotDef) and their load (a riding
        /// LoadView of the right kind, or none); 3 s of game time with no input leave each one playing: an idle player at its
        /// spawn is never caught. Levels v2: no order check (the v2 order is LevelDataM2Tests'); the cut level10 boots by id.
        /// </summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator Step45r_WaveBLevelsBootWithRobotAndLoadAndAnIdlePlayerIsNeverCaught()
        {
            var failures = new List<string>();
            foreach ((string id, string body, string lesson, int humans, int dogs, int robots, string load) in WaveB)
            {
                int errorsBefore = errors.Count;
                Game.LoadLevel(id);
                yield return Steps(1);
                Assert.AreEqual(id, Game.LevelId, "premise: the level was loaded");
                Assert.IsNotNull(Game.Level, id + ": premise: the level was built");
                LevelDef def = Game.Def;
                if (def.Lesson != lesson || def.Player.Kind != body || Game.Furniture.Body.Kind != body)
                {
                    failures.Add($"{id}: lesson {def.Lesson} (wants {lesson}), body {def.Player.Kind} built as {Game.Furniture.Body.Kind} (wants {body})");
                }
                int dogCount = def.Inhabitants.Count(h => h.Kind == PersonalityDef.Dog);
                int humanCount = def.Inhabitants.Count - dogCount;
                if (humanCount != humans || dogCount != dogs || Game.Level.Inhabitants.Count != def.Inhabitants.Count)
                {
                    failures.Add($"{id}: {humanCount} human(s) and {dogCount} dog(s) (wants {humans} and {dogs}), {Game.Level.Inhabitants.Count} built");
                }
                int robotDefs = def.Robots != null ? def.Robots.Count : 0;
                if (robotDefs != robots || Game.Robots.Count != robots || Game.Level.Robots.Count != robots)
                {
                    failures.Add($"{id}: {robotDefs} robot(s) in the data, {Game.Level.Robots.Count} built, {Game.Robots.Count} stepped (wants {robots})");
                }
                string kind = Game.LoadView != null ? Game.LoadView.Kind : null;
                if (def.Player.Load != load || kind != load || (load != null) != Game.CarryingLoad)
                {
                    failures.Add($"{id}: load '{def.Player.Load}' in the data, view '{kind}', riding {Game.CarryingLoad} (wants '{load}')");
                }
                yield return RouteReplayer.RunFor(Game, 3f, () => Game.State != PlayState.Playing, Tuning.PlaythroughTimeScale);
                if (Game.State != PlayState.Playing)
                {
                    failures.Add($"{id}: an idle player at its spawn ended the level ({Game.State}, {Game.LoseReason}) at {Game.Elapsed:0.0} s");
                }
                else if (load != null && !Game.CarryingLoad)
                {
                    failures.Add($"{id}: the load fell from an idle player");
                }
                if (errors.Count != errorsBefore)
                {
                    failures.Add($"{id}: error(s) logged: {string.Join(" | ", errors.Skip(errorsBefore))}");
                }
                Debug.Log($"[Step45r] {id}: {def.AllRooms().Count} rooms, {humanCount} human(s), {dogCount} dog(s), {Game.Robots.Count} robot(s), "
                          + $"load '{kind}', body {Game.Furniture.Body.Kind}, lesson {def.Lesson}, {Game.State} at {Game.Elapsed:0.0} s");
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }

        // ----- 40: the full playthrough -----

        /// <summary>
        /// Step 40 (CONTRACT_M5 12, CONTRACT_M5_v3 11 and 15.10): the whole play order of levels.json (18 levels after M6b, 17 after wave
        /// 5B) through the real level flow. The editor boot starts the first level on a fresh test save; each
        /// level is played on its designer route at offset 0 with Time.timeScale = Tuning.PlaythroughTimeScale and must win
        /// with no discovery, alert or creak; the save then holds the level in "won" with its best time (in memory and in
        /// the test save file), and Enter loads the next level (never GameState.LoadLevel, never a restart). The last win
        /// shows the end screen. Each run is capped at its route end + 30 s of game time by RouteReplayer.
        /// </summary>
        [UnityTest]
        [Timeout(3600000)]
        public IEnumerator Step40_FullPlaythrough()
        {
            List<string> order = Game.LevelOrder.ToList();
            // Levels v2 (LEVELS_V2 3 and 7): the count comes from the manifest; it must be the 22 v2 levels, none of them cut.
            ManifestDef manifest = LevelLoader.LoadManifestDef();
            CollectionAssert.AreEqual(manifest.Levels, order, "premise: the game plays the manifest's order");
            Assert.AreEqual(V2LevelCount, order.Count, "premise: levels.json lists the levels of v2: " + string.Join(", ", order));
            foreach (string cut in new[] { "level10", "level16", "level23" })
            {
                CollectionAssert.DoesNotContain(order, cut, "premise: a cut level is listed");
            }
            Assert.AreEqual(order[0], Game.LevelId, "premise: the editor boot starts the first level");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: the first level is playing");
            Assert.IsEmpty(SaveStore.Current.Won, "premise: the boot did not start on a fresh save");
            Assert.IsEmpty(SaveStore.Current.Best, "premise: the fresh save has best times");
            string realSave = Path.GetFullPath(Path.Combine(Application.persistentDataPath, SaveStore.FileName));
            Assert.AreNotEqual(realSave, Path.GetFullPath(SaveStore.FilePath), "premise: the playthrough would write the real save");
            Assert.AreEqual(GameRules.M4.Bodies, Game.Rules.Bodies, "premise: the game runs its default (M4) rules");
            int restarts = Game.Restarts;
            float total = 0f;
            for (int i = 0; i < order.Count; i++)
            {
                string id = order[i];
                Assert.AreEqual(id, Game.LevelId, $"level {i + 1} of the play order is not the one running");
                Assert.AreEqual(PlayState.Playing, Game.State, id + ": the level does not start playing");
                Assert.Less(Game.Elapsed, 0.5f, id + ": the level did not start fresh");
                Assert.GreaterOrEqual(Game.Def.DesignerRoute.Count, 2, id + ": premise: no designerRoute");
                int errorsBefore = errors.Count;
                int writes = SaveStore.WriteCount;
                var r = new RouteReplayer.Result();
                yield return RouteReplayer.Replay(Game, 0f, r, Tuning.PlaythroughTimeScale);
                Debug.Log("[Step40] " + r);
                Assert.AreEqual(PlayState.Won, r.State, $"{id}: the designer route did not win ({r.State}, {r.Reason}) after {r.Time:0.0} s, "
                                                         + $"waypoint {r.Waypoint}/{r.Waypoints}");
                Assert.AreEqual(0, r.Discoveries + r.Alerts + r.Creaks,
                    $"{id}: {r.Discoveries} discoveries, {r.Alerts} alerts, {r.Creaks} creaks (all must be 0)");
                // Wave 5B: the load rides to the exit and the route never touches the robot.
                Assert.AreEqual(0, r.Crashes + r.RobotContacts, $"{id}: {r.Crashes} load falls, {r.RobotContacts} robot contacts (all must be 0)");
                Assert.IsTrue(!r.HasLoad || r.LoadHeld, id + ": the load fell during the designer route");
                CollectionAssert.IsEmpty(errors.Skip(errorsBefore).ToList(), id + ": error(s) logged");
                total += r.Time;

                // The save after the win: the level is won with its time as the best, in memory and in the file. Levels v2
                // (LEVELS_V2 7): the win under the bare id, the best time under the level's RecordId ("level6~1").
                CollectionAssert.Contains(SaveStore.Current.Won, id, id + ": the win is not in the save");
                Assert.AreEqual(i + 1, SaveStore.Current.Won.Count, id + ": the save does not hold exactly the levels won so far");
                string recordId = Game.Def.RecordId;
                Assert.IsTrue(SaveStore.TryGetBest(recordId, out float best), id + ": no best time in the save under " + recordId);
                Assert.AreEqual(r.Time, best, 1e-3f, id + ": the best time is not the time of the win");
                Assert.Greater(SaveStore.WriteCount, writes, id + ": the save file was not written after the win");
                Assert.IsTrue(File.Exists(SaveStore.FilePath), id + ": no save file at " + SaveStore.FilePath);
                StringAssert.Contains("\"" + id + "\"", File.ReadAllText(SaveStore.FilePath), id + ": the save file does not name the level");

                if (i + 1 < order.Count)
                {
                    Assert.IsTrue(Hud.WinNextVisible, id + ": the win panel does not offer the next level");
                    Assert.IsFalse(Hud.EndVisible, id + ": the end screen shows before the last level");
                    InputReader.InjectNextLevelPress();
                    string next = order[i + 1];
                    yield return Until(() => Game.LevelId == next, 5f);
                    Assert.AreEqual(next, Game.LevelId, id + ": Enter did not load the next level");
                    yield return Steps(1);
                }
            }
            Debug.Log(string.Format(CultureInfo.InvariantCulture, "[Step40] {0} levels won in {1:0.0} s of game time", order.Count, total));
            Assert.IsTrue(Game.IsLastLevel, "premise: the playthrough ends on the last level");
            Assert.AreEqual(PlayState.Won, Game.State);
            Assert.IsTrue(Hud.EndVisible, "the playthrough does not end on the end screen");
            Assert.IsFalse(Hud.WinNextVisible, "the end screen offers a next level");
            Assert.AreEqual(restarts, Game.Restarts, "a level was restarted during the playthrough");
            CollectionAssert.AreEquivalent(order, SaveStore.Current.Won, "the save does not hold every level won");
        }
    }
}
