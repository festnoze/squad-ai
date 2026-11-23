using System;
using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestRunner;
using UnityEngine.TestTools;

[assembly: TestRunCallback(typeof(OutOfSight.Tests.HeldStartTestRun))]

namespace OutOfSight.Tests
{
    /// <summary>
    /// Levels v2 (docs/levels_v2/LEVELS_V2.md 6, task C3a): the PlayMode suite runs with the held start off, so every
    /// existing step keeps t = 0 at the build (GameState.HoldStart). Set before the run and again before each test (a test
    /// that wants the hold turns it on itself); the default comes back after the run.
    /// Next, idea 6 (task FOCUS): the same for the pause on a focus loss (GameState.AutoPause), so an editor window losing
    /// focus during a run never pauses a test's level (TestRunCallback allows one assembly attribute, hence one callback
    /// for both; ProbeTestsFocusPause turns it on itself).
    /// </summary>
    public sealed class HeldStartTestRun : ITestRunCallback
    {
        public void RunStarted(NUnit.Framework.Interfaces.ITest testsToRun)
        {
            GameState.HoldStart = false;
            GameState.AutoPause = false;
        }

        public void RunFinished(NUnit.Framework.Interfaces.ITestResult testResults)
        {
            GameState.ResetHoldStart();
            GameState.ResetAutoPause();
        }

        public void TestStarted(NUnit.Framework.Interfaces.ITest test)
        {
            GameState.HoldStart = false;
            GameState.AutoPause = false;
        }

        public void TestFinished(NUnit.Framework.Interfaces.ITestResult result)
        {
        }
    }

    /// <summary>
    /// Levels v2 task C3a on the real Boot scene under GameRules.M4 (docs/levels_v2/wave1/code_features.json, "Start on
    /// first input (held start)" and "Door only an inhabitant opens"):
    /// <list type="bullet">
    /// <item>HeldStart01 (test_m5_game_robot: two watchers and a robot; AUTOSTART): under a held card the world runs from
    /// the build exactly as with the hold off (same routine poses and robot positions after 3 s, FixedStepped every step),
    /// while the player's clock and creak wait and the chair stays put; the careful key and the camera stick alone do not
    /// start it, nor a move input while paused (the world is frozen too); the first step with a move input is step 1 of
    /// the clock, the world counting on from where it was; a restart holds again and the action key alone starts it; the
    /// next level holds again.</item>
    /// <item>HeldStart02 (level1, level8): the designer route replayed with the hold on, released at the replay's first
    /// sample (RouteReplayer) right after the build, ends on the same step, state and time as with the hold off.</item>
    /// <item>HeldStart03 (test_v2_locked_door: test_m6_gameplay_dooropen with porte "playerLocked" and the chair spawning in
    /// its reach): E there begins no action and leaves porte closed, the HUD query reports the locked leaf, and the
    /// household's walk still opens it.</item>
    /// <item>HeldStart04 (task STARTFIX and AUTOSTART; level7 and level2, whose spawn stands in the watcher's cone at t = 0):
    /// a start press made on the build is dropped; under the held card nobody sees the chair although the same watcher
    /// sees it with the hold off; the start press (Space, Enter, gamepad A) then starts the clock with no move: the chair
    /// never moves, turns, creaks or acts, the watcher sees it still on exactly the steps it does with the hold off, and
    /// it is never caught.</item>
    /// <item>HeldStart05 (task STARTFIX, touch): an orbit drag does not start a held level, a tap outside the buttons does,
    /// with no move.</item>
    /// <item>HeldStart06 (AUTOSTART, test_m5_game_robot): before the first input the chair is out of play: put in the
    /// robot's way, the robot runs into it and reverses but never shoves it, nobody discovers it out of place, nothing
    /// is lost; the first input then starts the clock as usual.</item>
    /// </list>
    /// Every wait counts fixed steps (WaitForFixedUpdate) or game time under a real time guard.
    /// </summary>
    public sealed class ProbeTestsHeldStart
    {
        private const float Dt = Tuning.FixedStep;
        private const string RobotLevel = "test_m5_game_robot";
        private const string LockedLevel = "test_v2_locked_door";
        private static readonly string[] ReplayLevels = { "level1", "level8" };

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            GameState.HoldStart = false;
            GamePause.IsPaused = false;
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
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
            Assert.IsTrue(Game.Started, "premise: the suite's boot is not held (HeldStartTestRun)");
            GamePause.IsPaused = false;
            Game.Rules = GameRules.M4;
            yield return FixedSteps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            GamePause.IsPaused = false;
            // Back to the suite's value (HeldStartTestRun), never to the player's default.
            GameState.HoldStart = false;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null && main.Game.Furniture != null)
            {
                main.Game.Furniture.ScriptedDirection = null;
                main.Game.Furniture.ScriptedCareful = null;
            }
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

        private void AssertClean()
        {
            Assert.AreEqual(0, exceptions, "errors were logged: " + string.Join(" | ", logged));
        }

        private static IEnumerator FixedSteps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static float Planar(Vector3 a, Vector3 b) => YawMath.Planar(a - b).magnitude;

        /// <summary>Builds <paramref name="id"/> with the hold on and checks it waits.</summary>
        private void LoadHeld(string id)
        {
            GameState.HoldStart = true;
            Game.LoadLevel(id);
            Game.Rules = GameRules.M4;
            Assert.AreEqual(id, Game.Def.Id, "premise: the level loaded");
            Assert.AreEqual(PlayState.Playing, Game.State, id + ": premise: playing");
            Assert.IsFalse(Game.Started, id + ": a build with the hold on started at once");
            Assert.AreEqual(0, Game.Steps, id + ": a held build has steps");
            Assert.AreEqual(0, Game.WorldSteps, id + ": a fresh build has world steps");
        }

        /// <summary>The planar position of every robot, in level order.</summary>
        private List<Vector3> RobotPositions()
        {
            var positions = new List<Vector3>();
            foreach (Robot robot in Game.Robots)
            {
                positions.Add(YawMath.Planar(robot.transform.position));
            }
            return positions;
        }

        /// <summary>The pose of every routine (planar position, body and head yaw, station, activity), in level order.</summary>
        private List<string> RoutinePoses()
        {
            var poses = new List<string>();
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                InhabitantRoutine r = h.Routine;
                poses.Add(string.Format(System.Globalization.CultureInfo.InvariantCulture, "{0}: ({1:0.00000}, {2:0.00000}) body {3:0.000} head {4:0.000} station {5} {6}",
                    h.name, r.Position.x, r.Position.z, r.BodyYaw, r.HeadYaw, r.StationIndex, r.LastActivity));
            }
            return poses;
        }

        /// <summary>
        /// HeldStart01 (AUTOSTART): under a held card the world runs from the build as with the hold off, the player's
        /// clock and creak wait and the chair stays put; the careful key, the camera stick and a paused move do not start;
        /// the first move step is step 1 of the clock (the world goes on counting from the build); a restart and the next
        /// level hold again, and the action key alone starts too.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator HeldStart01_TheWorldRunsUnderTheCardAndTheFirstInputStartsTheClock()
        {
            int held = Mathf.RoundToInt(3f / Dt);

            // The reference: the same level with the hold off, the chair left alone for the same 3 s.
            GameState.HoldStart = false;
            Game.LoadLevel(RobotLevel);
            Game.Rules = GameRules.M4;
            Assert.IsTrue(Game.Started, "premise: the hold is off");
            List<string> posesStart = RoutinePoses();
            List<Vector3> robotsStart = RobotPositions();
            yield return FixedSteps(held);
            List<string> posesOff = RoutinePoses();
            List<Vector3> robotsOff = RobotPositions();
            Assert.AreEqual(held, Game.WorldSteps, "premise: with the hold off the world counts every step");
            Assert.AreEqual(held, Game.Steps, "premise: with the hold off the clock counts from the build");
            bool worldMoved = posesStart.Count != posesOff.Count;
            for (int k = 0; k < posesStart.Count && k < posesOff.Count; k++)
            {
                worldMoved |= posesStart[k] != posesOff[k];
            }
            for (int k = 0; k < robotsStart.Count; k++)
            {
                worldMoved |= Planar(robotsStart[k], robotsOff[k]) > 1e-3f;
            }
            Assert.IsTrue(worldMoved, "premise: neither a routine nor a robot moved in 3 s");

            LoadHeld(RobotLevel);
            Assert.GreaterOrEqual(Game.Robots.Count, 1, "premise: the level has a robot");
            Assert.GreaterOrEqual(Game.Level.Inhabitants.Count, 2, "premise: the level has two watchers");
            Vector3 chair0 = Chair.transform.position;
            float yaw0 = Chair.Yaw;
            int stepped = 0;
            void OnStep() => stepped++;
            int started = 0;
            void OnStarted() => started++;
            Game.FixedStepped += OnStep;
            Game.LevelStarted += OnStarted;
            try
            {
                // 3 s of fixed steps with no input at all: the world runs, the player waits.
                yield return FixedSteps(held);
                Assert.IsFalse(Game.Started, "the level started with no input");
                Assert.AreEqual(held, Game.WorldSteps, "held: the world did not run every step");
                Assert.AreEqual(held, stepped, "held: FixedStepped was not raised every step");
                Assert.AreEqual(0, Game.Steps, "held: the clock counted steps");
                Assert.AreEqual(0f, Game.Elapsed, "held: Elapsed advanced");
                Assert.AreEqual(PlayState.Playing, Game.State, "held: the level ended");
                Assert.AreEqual(0f, Game.Creak.Value, "held: the creak gauge filled");
                Assert.AreEqual(0, Game.CreakCount, "held: a creak fired");
                Assert.AreEqual(held * Dt, Game.RobotTime, 1e-5f, "held: the robot timeline waited for the player");
                CollectionAssert.AreEqual(posesOff, RoutinePoses(), "held: the routines do not run as with the hold off");
                List<Vector3> robotsHeld = RobotPositions();
                for (int k = 0; k < robotsOff.Count; k++)
                {
                    Assert.Less(Planar(robotsHeld[k], robotsOff[k]), 1e-4f, $"held: robot {k} is not where it is with the hold off");
                }
                Assert.Less(Planar(Chair.transform.position, chair0), 1e-6f, "held: the chair moved");
                Assert.AreEqual(yaw0, Chair.Yaw, 1e-4f, "held: the chair turned");

                // The careful key and the camera stick alone do not start the player.
                InputReader.InjectCareful(true);
                InputReader.InjectLookStick(new Vector2(1f, 0f));
                yield return FixedSteps(10);
                Assert.IsFalse(Game.Started, "the careful key or the camera stick started the level");
                Assert.AreEqual(0, Game.Steps);
                Assert.Less(Planar(Chair.transform.position, chair0), 1e-6f, "held: the careful key moved the chair");
                InputReader.InjectCareful(false);
                InputReader.ClearLookStick();

                // Paused, a move input does not start it and the world stops; the first step after the resume starts it.
                Game.Paused = true;
                int world = Game.WorldSteps;
                float robotTime = Game.RobotTime;
                List<string> posesPaused = RoutinePoses();
                InputReader.InjectMoveVector(Vector2.up);
                yield return FixedSteps(10);
                Assert.IsFalse(Game.Started, "a move input started a paused level");
                Assert.AreEqual(0, Game.Steps);
                Assert.AreEqual(world, Game.WorldSteps, "paused under the card: the world ran");
                Assert.AreEqual(robotTime, Game.RobotTime, "paused under the card: the robot timeline advanced");
                CollectionAssert.AreEqual(posesPaused, RoutinePoses(), "paused under the card: a routine moved");
                Game.Paused = false;
                stepped = 0;
                yield return FixedSteps(1);
                Assert.IsTrue(Game.Started, "the first move input did not start the level");
                Assert.AreEqual(1, started, "LevelStarted was not raised exactly once");
                Assert.AreEqual(1, Game.Steps, "the first input step is not step 1");
                Assert.AreEqual(1, stepped, "the first input step did not run in full");
                Assert.AreEqual(world + 1, Game.WorldSteps, "the world did not go on from where it was");
                Assert.AreEqual(Dt, Game.Elapsed, 1e-6f, "Elapsed does not count from the first input");
                Assert.Greater(Planar(Chair.transform.position, chair0), 1e-5f, "the chair did not move on the first input step");
                yield return FixedSteps(9);
                Assert.AreEqual(10, Game.Steps);
                Assert.AreEqual(10 * Dt, Game.Elapsed, 1e-5f);
                Assert.AreEqual((world + 10) * Dt, Game.RobotTime, 1e-5f, "the robot timeline does not count from the build");
                Assert.Greater(Planar(Chair.transform.position, chair0), 0.02f, "the chair did not drive after the start");
                InputReader.ClearMoveVector();
            }
            finally
            {
                Game.FixedStepped -= OnStep;
                Game.LevelStarted -= OnStarted;
                Game.Paused = false;
                InputReader.ClearMoveVector();
            }

            // A restart holds again; then the action key alone starts it (a chair has no body action).
            Game.Restart();
            Assert.IsFalse(Game.Started, "a restart did not hold again");
            Assert.AreEqual(0, Game.Steps);
            Assert.AreEqual(0, Game.WorldSteps, "a restart kept the world's steps");
            Assert.AreEqual(0f, Game.Elapsed);
            yield return FixedSteps(5);
            Assert.AreEqual(0, Game.Steps, "the restarted level's clock ran with no input");
            Assert.AreEqual(5, Game.WorldSteps, "the restarted level's world waited");
            InputReader.InjectAction();
            yield return FixedSteps(1);
            Assert.IsTrue(Game.Started, "the action key did not start the level");
            Assert.AreEqual(1, Game.Steps, "the action step is not step 1");

            // The next level holds as well.
            Game.LoadLevel("level1");
            Assert.IsFalse(Game.Started, "loading the next level did not hold");
            yield return FixedSteps(3);
            Assert.AreEqual(0, Game.Steps);
            AssertClean();
        }

        /// <summary>
        /// HeldStart02: a designer route replayed with the hold on (RouteReplayer releases it at its first sample, right
        /// after the build: AUTOSTART runs the world under the card, so a later release would replay against a world that
        /// is ahead) wins on the same exit step, with the same time and counters, as with the hold off.
        /// </summary>
        [UnityTest]
        [Timeout(1200000)]
        public IEnumerator HeldStart02_ReplayWithTheHoldWinsOnTheSameStep()
        {
            var failures = new List<string>();
            foreach (string id in ReplayLevels)
            {
                GameState.HoldStart = false;
                Game.LoadLevel(id);
                Game.Rules = GameRules.M4;
                Assert.IsTrue(Game.Started, id + ": premise: the hold is off");
                Assert.GreaterOrEqual(Game.Def.DesignerRoute.Count, 2, id + ": premise: no designerRoute");
                var off = new RouteReplayer.Result();
                yield return RouteReplayer.Replay(Game, 0f, off, Tuning.PlaythroughTimeScale);
                int offSteps = Game.Steps;
                Debug.Log($"[HeldStart02] hold off, exit step {offSteps}: {off}");

                LoadHeld(id);
                var on = new RouteReplayer.Result();
                yield return RouteReplayer.Replay(Game, 0f, on, Tuning.PlaythroughTimeScale);
                int onSteps = Game.Steps;
                Debug.Log($"[HeldStart02] hold on, exit step {onSteps}, world step {Game.WorldSteps}: {on}");
                if (Game.WorldSteps < onSteps)
                {
                    failures.Add($"{id}: the world ran {Game.WorldSteps} steps behind the player's {onSteps}");
                }

                if (off.State != PlayState.Won)
                {
                    failures.Add($"{id}: premise: the route does not win with the hold off ({off.State}, {off.Reason}) after {off.Time:0.00} s");
                }
                if (on.State != off.State || onSteps != offSteps || Mathf.Abs(on.Time - off.Time) > 1e-4f)
                {
                    failures.Add($"{id}: hold on ended {on.State} on step {onSteps} ({on.Time:0.00} s), hold off {off.State} on step {offSteps} ({off.Time:0.00} s)");
                }
                if (on.Discoveries != off.Discoveries || on.Alerts != off.Alerts || on.Creaks != off.Creaks || on.Opens != off.Opens
                    || on.Waypoint != off.Waypoint)
                {
                    failures.Add($"{id}: the counters differ: on {on} | off {off}");
                }
            }
            GameState.HoldStart = false;
            CollectionAssert.IsEmpty(failures, string.Join("\n", failures));
            AssertClean();
        }

        /// <summary>
        /// HeldStart03: a push toward a playerLocked leaf in reach (task DOORAUTO, in place of E; and E itself) begins no action
        /// and leaves it closed (it is not the leaf in reach, it offers no push direction, so a real push only drives into
        /// it; the locked query reports it, the door hint stays hidden); the household's walk still opens it.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator HeldStart03_PlayerLockedLeafIgnoresEAndOpensForTheHousehold()
        {
            Game.LoadLevel(LockedLevel);
            Game.Rules = GameRules.M4;
            Assert.AreEqual(LockedLevel, Game.Def.Id, "premise: the level loaded");
            Assert.IsTrue(Game.Started, "premise: the hold is off");
            CollectionAssert.IsEmpty(LevelValidator.Validate(Game.Def), "premise: the fixture validates");
            Assert.AreEqual(1, Game.Level.Leaves.Count, "premise: one leaf");
            DoorLeaf porte = Game.Level.Leaves[0];
            OpeningDef def = Game.Def.LeafDoors()[0];
            Assert.IsTrue(def.PlayerLocked && def.OpenedByInhabitants, "premise: porte is playerLocked and opened by inhabitants");
            yield return FixedSteps(2);
            Assert.IsFalse(porte.Open, "premise: porte starts closed");
            Assert.IsTrue(porte.InReach(Chair), "premise: the spawn is in reach of porte");
            Assert.IsNull(Game.DoorInReach, "a playerLocked leaf is offered to a door push");
            Assert.IsNull(Game.DoorPushDirection, "a playerLocked leaf offers a push direction");
            Assert.AreSame(porte, Game.LockedLeafInReach, "the locked query does not report porte");
            Assert.IsTrue(Game.LockedDoorHintWanted, "the locked hint is not wanted in reach of porte");
            Assert.IsFalse(main.Hud.DoorHintVisible, "the door hint shows for a locked leaf");

            Vector3 at = Chair.transform.position;
            int opens = Game.DoorOpenCount;
            bool acted = false;
            void Watch() => acted |= Chair.ActionActive;
            Game.FixedStepped += Watch;
            try
            {
                for (int press = 0; press < 3; press++)
                {
                    InputReader.InjectAction();
                    InputReader.InjectDoorPush();
                    yield return FixedSteps(5);
                }
            }
            finally
            {
                Game.FixedStepped -= Watch;
            }
            Assert.IsFalse(acted, "a push or E began an action at a playerLocked leaf");
            Assert.IsFalse(porte.Open || porte.Swinging, "a push or E opened a playerLocked leaf");
            Assert.AreEqual(opens, Game.DoorOpenCount, "a player opening was counted");
            Assert.Less(Planar(Chair.transform.position, at), 1e-5f, "the chair moved");
            Assert.AreEqual(PlayState.Playing, Game.State);

            // The household's walk (station 0 in b, then station 1 in a through porte) still opens it.
            Inhabitant h = Game.MainInhabitant;
            float realStart = Time.realtimeSinceStartup;
            float cap = Game.Elapsed + 20f;
            Time.timeScale = 4f;
            try
            {
                while (!(porte.Open && h.Routine.Position.x < -0.5f) && Game.Elapsed < cap && Time.realtimeSinceStartup - realStart < 120f)
                {
                    yield return null;
                }
            }
            finally
            {
                Time.timeScale = 1f;
            }
            Assert.IsTrue(porte.Open, "the household's walk did not open the playerLocked leaf");
            Assert.IsTrue(porte.SwungByHousehold, "porte was not opened by the household");
            Assert.AreEqual(1, Game.HouseholdDoorOpenCount, "not exactly one household opening");
            Assert.AreEqual(opens, Game.DoorOpenCount, "a player opening was counted");
            Assert.Less(h.Routine.Position.x, -0.5f, "the inhabitant did not walk through");
            Assert.IsNull(Game.LockedLeafInReach, "an open leaf is still reported locked");
            Assert.IsFalse(Game.LockedDoorHintWanted, "the locked hint is wanted for an open leaf");
            AssertClean();
        }

        /// <summary>The levels whose spawn a watcher sees at t = 0 (docs/next/progress/STARTFIX.md, static sight model).</summary>
        private static readonly string[] SeenSpawnLevels = { "level7", "level2" };

        /// <summary>
        /// HeldStart04 (STARTFIX, AUTOSTART): a start press made before the build is dropped by it. Under the held card the
        /// watcher that sees the spawn with the hold off never sees the chair (the furniture is out of play), the eye stays
        /// closed and no cone shows the alarm. Then the start press alone starts the clock with no move: from there the
        /// watcher sees the chair still on exactly the world steps it does with the hold off, and for 4 s the chair never
        /// moves, turns, creaks or acts, and the level is never lost.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator HeldStart04_StartPressReleasesWithoutMovingUnderAWatcher()
        {
            int held = Mathf.RoundToInt(1f / Dt);
            int after = Mathf.RoundToInt(4f / Dt);
            foreach (string id in SeenSpawnLevels)
            {
                // The reference: with the hold off, the chair left alone, whether a watcher sees it on each world step.
                GameState.HoldStart = false;
                Game.LoadLevel(id);
                Game.Rules = GameRules.M4;
                Assert.IsTrue(Game.Started, id + ": premise: the hold is off");
                var seenOff = new List<bool>();
                void Record() => seenOff.Add(Game.Seen);
                Game.FixedStepped += Record;
                try
                {
                    yield return FixedSteps(held + 1 + after);
                }
                finally
                {
                    Game.FixedStepped -= Record;
                }
                Assert.Contains(true, seenOff.GetRange(0, held), id + ": premise: with the hold off no watcher sees the spawn in the first second (STARTFIX.md)");

                // A press made on the frame the level is built (the Enter or A of Play or Next level) never starts it.
                InputReader.InjectStartPress();
                LoadHeld(id);
                var seenOn = new List<bool>();
                int eyeOpen = 0;
                int coneAlarm = 0;
                void Watch()
                {
                    seenOn.Add(Game.Seen);
                    if (!Game.Started)
                    {
                        eyeOpen += Game.EyeState != HudEye.Closed ? 1 : 0;
                        foreach (Vision v in Game.Level.Visions)
                        {
                            coneAlarm += v != null && v.SeesPlayer ? 1 : 0;
                        }
                    }
                }
                Game.FixedStepped += Watch;
                try
                {
                    yield return FixedSteps(held);
                    Assert.IsFalse(Game.Started, id + ": a start press made before the build started the level");
                    Assert.AreEqual(0, Game.Steps, id + ": the held level's clock ran");
                    Assert.AreEqual(held, Game.WorldSteps, id + ": the world did not run under the card");
                }
                finally
                {
                    Game.FixedStepped -= Watch;
                }
                Assert.IsFalse(seenOn.Contains(true), id + ": a watcher saw the chair before the first input");
                Assert.AreEqual(0, eyeOpen, id + ": the eye opened before the first input");
                Assert.AreEqual(0, coneAlarm, id + ": a cone saw the chair before the first input");

                Vector3 chair0 = Chair.transform.position;
                float yaw0 = Chair.Yaw;
                int toggles0 = Chair.ToggleCount;
                int movingSteps = 0;
                int actingSteps = 0;
                void WatchStarted()
                {
                    seenOn.Add(Game.Seen);
                    movingSteps += Chair.IsMoving || Game.FurnitureMoving ? 1 : 0;
                    actingSteps += Chair.ActionActive ? 1 : 0;
                }
                Game.FixedStepped += WatchStarted;
                try
                {
                    InputReader.InjectStartPress();
                    yield return FixedSteps(1);
                    Assert.IsTrue(Game.Started, id + ": the start press did not start the level");
                    Assert.AreEqual(1, Game.Steps, id + ": the start press step is not step 1");
                    Assert.AreEqual(held + 1, Game.WorldSteps, id + ": the start press step is not the world's next step");
                    Assert.IsFalse(InputReader.StartPressPending, id + ": the start press was not consumed");
                    yield return FixedSteps(after);
                }
                finally
                {
                    Game.FixedStepped -= WatchStarted;
                }
                // From the start on, the same world and the same still chair: the same sightings as with the hold off.
                int compared = Mathf.Min(seenOn.Count, seenOff.Count);
                Assert.Greater(compared, held, id + ": premise: too few steps recorded");
                CollectionAssert.AreEqual(seenOff.GetRange(held, compared - held), seenOn.GetRange(held, compared - held),
                    id + ": after the start press the chair is not seen as it is with the hold off");
                Assert.AreEqual(0, movingSteps, id + ": a step after a start press counted as moving");
                Assert.AreEqual(0, actingSteps, id + ": the start press began an action");
                Assert.AreEqual(toggles0, Chair.ToggleCount, id + ": the start press toggled something");
                Assert.Less(Planar(Chair.transform.position, chair0), 1e-5f, id + ": the chair drifted after a start press");
                Assert.AreEqual(yaw0, Chair.Yaw, 1e-4f, id + ": the chair turned after a start press");
                Assert.AreEqual(0, Game.CreakCount, id + ": a creak fired with no move");
                Assert.AreEqual(0f, Game.SeenMoving, 1e-6f, id + ": the caught clock ran on a still chair");
                Assert.AreEqual(PlayState.Playing, Game.State, id + ": seen still after a start press, the level was lost");
            }
            AssertClean();
        }

        /// <summary>
        /// HeldStart05 (STARTFIX, touch): with the touch controls up, an orbit drag on the right half does not start a held
        /// level; a tap there (down, then up a frame later, in place) does, and the chair does not move.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator HeldStart05_TouchTapStartsAndAnOrbitDragDoesNot()
        {
            InputReader.ForceTouchUI = true;
            LoadHeld(SeenSpawnLevels[0]);
            yield return null;
            yield return null;
            Vector3 chair0 = Chair.transform.position;
            Vector2 at = new Vector2(Screen.width * 0.75f, Screen.height * 0.5f);

            // A drag: the orbit, never a start.
            InputReader.InjectTouch(0, at);
            yield return null;
            for (int i = 1; i <= 5; i++)
            {
                InputReader.InjectTouch(0, at + new Vector2(40f * i, 0f));
                yield return null;
            }
            InputReader.ReleaseTouch(0);
            yield return null;
            yield return FixedSteps(5);
            Assert.IsFalse(Game.Started, "an orbit drag started the held level");
            Assert.AreEqual(0, Game.Steps);

            // A tap in place: the start.
            InputReader.InjectTouch(0, at);
            yield return null;
            InputReader.ReleaseTouch(0);
            yield return null;
            yield return FixedSteps(2);
            Assert.IsTrue(Game.Started, "a tap outside the buttons did not start the held level");
            Assert.Less(Planar(Chair.transform.position, chair0), 1e-5f, "the chair moved after a tap start");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// HeldStart06 (AUTOSTART): before the first input the chair is out of play. Put (teleported, as a test may) on the
        /// robot's timeline 1.5 s ahead of it, away from its spawn: the robot runs into it and reverses, the chair is never
        /// shoved and never moves, nobody discovers it out of place, the level is not lost and the clock has not started.
        /// The first move input then starts the clock as usual.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator HeldStart06_OutOfPlayBeforeTheFirstInput()
        {
            LoadHeld(RobotLevel);
            Assert.GreaterOrEqual(Game.Robots.Count, 1, "premise: the level has a robot");
            yield return FixedSteps(2);
            Robot robot = Game.Robots[0];
            Vector3 ahead = YawMath.Planar(robot.Path.PositionAt(Game.RobotTime + 1.5f));
            Chair.Teleport(ahead, Chair.Yaw);
            Vector3 at = Chair.transform.position;
            int contacts = Game.RobotContactCount;
            int seen = 0;
            void Watch() => seen += Game.Seen ? 1 : 0;
            Game.FixedStepped += Watch;
            try
            {
                int guard = 0;
                while (Game.RobotContactCount == contacts && guard++ < Mathf.RoundToInt(6f / Dt))
                {
                    yield return new WaitForFixedUpdate();
                }
                Assert.Greater(Game.RobotContactCount, contacts, "premise: the robot never reached the chair put in its way");
                // Long enough for an accepted shove to have run (RobotPushTime) and for a watcher's discovery grace.
                yield return FixedSteps(Mathf.RoundToInt(2f / Dt));
            }
            finally
            {
                Game.FixedStepped -= Watch;
            }
            Assert.IsFalse(Game.Started, "the robot's contact started the level");
            Assert.AreEqual(0, Game.ShoveCount, "the robot shoved the chair before the first input");
            Assert.Less(Planar(Chair.transform.position, at), 1e-5f, "the chair moved before the first input");
            Assert.AreEqual(0, seen, "a watcher saw the chair before the first input");
            Assert.AreEqual(0, Game.DiscoveryCount, "the chair was discovered out of place before the first input");
            Assert.AreEqual(0f, Game.MaxSuspicion, 1e-6f, "suspicion rose before the first input");
            Assert.AreEqual(0, Game.Steps, "the clock ran before the first input");
            Assert.AreEqual(PlayState.Playing, Game.State, "the level ended before the first input");

            InputReader.InjectMoveVector(Vector2.up);
            try
            {
                yield return FixedSteps(1);
                Assert.IsTrue(Game.Started, "the first move input did not start the level");
                Assert.AreEqual(1, Game.Steps, "the first input step is not step 1");
            }
            finally
            {
                InputReader.ClearMoveVector();
            }
            AssertClean();
        }
    }
}
