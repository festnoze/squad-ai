using System.Collections;
using System.Collections.Generic;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// PRD 10.2, the PlayMode probe. Runs the real Boot scene. Every wait is a count of fixed steps
    /// (WaitForFixedUpdate), never rendered frames: a headless run renders frames far faster than real time.
    /// </summary>
    public sealed class ProbeTests
    {
        private const float Dt = Tuning.FixedStep;
        private int exceptions;
        private readonly List<string> logged = new List<string>();

        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;
        private Inhabitant Habitant => Game.MainInhabitant;

        private static readonly Vector3 Spawn = new Vector3(-3.2f, 0f, -2.2f);

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
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
            // This file is the M1 probe: it measures the M1 core loop (docs/CONTRACT_M2.md 3.7).
            Game.Rules = GameRules.M1;
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

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(to - from);

        private static int CountObjects() =>
            Object.FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None).Length;

        // ----- 01 -----

        [UnityTest]
        public IEnumerator Step01_Boot()
        {
            yield return Steps(25);
            Assert.AreEqual(0, main.FailedSteps, "a build step of Main failed");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
            Assert.IsNotNull(Chair, "player furniture missing");
            Assert.IsNotNull(Habitant, "inhabitant missing");
            Assert.IsNotNull(main.Hud, "HUD missing");
            Assert.IsTrue(main.Hud.Labels.Count >= 10, "HUD labels missing");
            Assert.IsNotNull(main.Hud.Font, "HUD font missing");
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.That((Chair.transform.position - Spawn).magnitude, Is.LessThan(0.05f), "chair not at spawn");
            Assert.Greater(CountObjects(), 50, "the level looks empty");
        }

        // ----- 02 -----

        [UnityTest]
        public IEnumerator Step02_MoveUnseen()
        {
            Habitant.Pin(new Vector3(-1.5f, 0f, 2.2f), 0f);
            Vector3 start = Chair.transform.position;
            Chair.ScriptedDirection = Vector3.forward;
            bool everSeen = false;
            for (int i = 0; i < 50; i++)
            {
                yield return new WaitForFixedUpdate();
                everSeen |= Game.Seen;
            }
            Chair.ScriptedDirection = null;
            float moved = YawMath.Planar(Chair.transform.position - start).magnitude;
            Assert.That(moved, Is.InRange(1.3f, 1.6f), $"1 s of driving moved {moved:0.000} m");
            Assert.IsFalse(everSeen, "the inhabitant facing away saw the chair");
            Assert.AreEqual(PlayState.Playing, Game.State);
            // Stopping is exact: one step after release the chair no longer moves.
            yield return Steps(1);
            Vector3 stopped = Chair.transform.position;
            yield return Steps(5);
            Assert.That(YawMath.Planar(Chair.transform.position - stopped).magnitude, Is.LessThan(1e-4f));
            Assert.IsFalse(Chair.IsMoving);
        }

        // ----- 03 and 04 share the pose: the inhabitant at station 3 staring at the chair. -----

        private void PinStaringAtChair()
        {
            var eyeSpot = new Vector3(0f, 0f, -2.3f);
            Habitant.Pin(eyeSpot, YawToward(eyeSpot, Chair.transform.position));
        }

        [UnityTest]
        public IEnumerator Step03_StillWhileSeen()
        {
            PinStaringAtChair();
            yield return Steps(100);
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.IsTrue(Game.Seen, "the vision test does not see the chair");
            Assert.IsTrue(main.Hud.EyeOpen, "eye indicator closed while seen");
            Assert.AreEqual(0f, Game.SeenMoving);
        }

        [UnityTest]
        public IEnumerator Step04_Caught()
        {
            PinStaringAtChair();
            yield return Steps(5);
            Assert.IsTrue(Game.Seen, "precondition: the chair is seen");
            Chair.ScriptedDirection = Vector3.forward;
            int steps = 0;
            while (Game.State == PlayState.Playing && steps < 100)
            {
                yield return new WaitForFixedUpdate();
                steps++;
            }
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Caught, Game.State, "never caught");
            float t = steps * Dt;
            Assert.That(t, Is.InRange(0.20f - 1e-4f, 0.30f + 1e-4f), $"caught after {t:0.00} s");
            Assert.IsTrue(main.Hud.FailVisible, "fail panel hidden");
            Assert.IsTrue(Habitant.Routine.IsStartled, "inhabitant not startled");
            yield return null;
            Assert.AreEqual(0f, main.Hud.TitleCardAlpha, "title card still visible over the fail panel");
        }

        // ----- 05 -----

        [UnityTest]
        public IEnumerator Step05_Occluder()
        {
            // Chair against the +z wall beyond the bookshelf, inhabitant on the other side, looking along
            // the wall: the bookshelf is the only thing between them.
            Chair.Teleport(new Vector3(-3.05f, 0f, 2.68f), 0f);
            var eyeSpot = new Vector3(0.6f, 0f, 2.75f);
            Habitant.Pin(eyeSpot, -90f);
            yield return Steps(2);
            // Premise, so the step cannot pass for the wrong reason: every sample is inside the cone.
            var samples = new Vector3[5];
            Chair.GetSamplePoints(samples);
            foreach (Vector3 p in samples)
            {
                Assert.IsTrue(VisionMath.IsInCone(Habitant.EyePosition, Habitant.EyeForward, p, Tuning.ViewRange, Tuning.ViewHalfAngle),
                    "premise broken: a sample point is outside the cone, so the bookshelf proves nothing");
            }
            Chair.ScriptedDirection = Vector3.left;
            bool everSeen = false;
            for (int i = 0; i < 25; i++)
            {
                yield return new WaitForFixedUpdate();
                everSeen |= Game.Seen;
            }
            Chair.ScriptedDirection = null;
            Assert.IsTrue(Chair.transform.position.x < -3.2f, "the chair did not move");
            Assert.IsFalse(everSeen, "seen through the bookshelf");
            // And it is the bookshelf, not a wall, that blocks every sample.
            Chair.GetSamplePoints(samples);
            foreach (Vector3 p in samples)
            {
                Vector3 d = p - Habitant.EyePosition;
                Assert.IsTrue(Physics.Raycast(Habitant.EyePosition, d.normalized, out RaycastHit hit, d.magnitude, Layers.OccluderMask),
                    "a sample is not occluded at all");
                Transform t = hit.collider.transform;
                while (t.parent != null && t.parent.parent != null)
                {
                    t = t.parent;
                }
                Assert.AreEqual("Bookshelf", t.name, "the sample is hidden by something else than the bookshelf");
            }
            Assert.AreEqual(PlayState.Playing, Game.State);
        }

        // ----- 06 -----

        [UnityTest]
        public IEnumerator Step06_OutOfCone()
        {
            var eyeSpot = new Vector3(0f, 0f, -2.3f);
            float toChair = YawToward(eyeSpot, Chair.transform.position);
            Habitant.Pin(eyeSpot, toChair + 90f);
            yield return Steps(2);
            // Premise: in range and nothing in between, so only the cone can hide the chair.
            Vector3 center = Chair.Center;
            Assert.Less((center - Habitant.EyePosition).magnitude, Tuning.ViewRange);
            Assert.IsFalse(Vision.Occluded(Habitant.EyePosition, center), "premise broken: something occludes the chair");
            Chair.ScriptedDirection = Vector3.left;
            bool everSeen = false;
            for (int i = 0; i < 20; i++)
            {
                yield return new WaitForFixedUpdate();
                everSeen |= Game.Seen;
            }
            Chair.ScriptedDirection = null;
            Assert.IsFalse(everSeen, "seen at 90 deg");
            Assert.AreEqual(PlayState.Playing, Game.State);
        }

        // ----- 07 -----

        private struct Record
        {
            public float Body;
            public float Head;
            public RoutineActivity Activity;
        }

        [UnityTest]
        public IEnumerator Step07_Telegraph()
        {
            // A full loop takes about a minute of game time: run it at 8x, still one record per fixed step.
            var records = new List<Record>();
            InhabitantRoutine routine = Habitant.Routine;
            void OnStep() => records.Add(new Record { Body = routine.BodyYaw, Head = routine.HeadYaw, Activity = routine.LastActivity });
            Game.FixedStepped += OnStep;
            Time.timeScale = 8f;
            // Bounded by GAME time, never by frames: at 4000 fps a frame budget runs out before one loop.
            float realStart = Time.realtimeSinceStartup;
            while (routine.LoopsCompleted < 1 && Game.Elapsed < 120f && Time.realtimeSinceStartup - realStart < 120f)
            {
                yield return null;
            }
            Time.timeScale = 1f;
            Game.FixedStepped -= OnStep;
            Assert.AreEqual(PlayState.Playing, Game.State, "the still chair got the level lost");
            Assert.GreaterOrEqual(routine.LoopsCompleted, 1, "the routine never completed a loop");

            int large = Analyze(records, r => r.Body, RoutineActivity.TurningBody) + Analyze(records, r => r.Head, RoutineActivity.TurningHead);
            Assert.GreaterOrEqual(large, 6, $"only {large} turns above 30 deg found in a loop");
        }

        private static int Analyze(List<Record> s, System.Func<Record, float> yaw, RoutineActivity turning)
        {
            int large = 0;
            int i = 1;
            while (i < s.Count)
            {
                if (Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i]))) < 1e-3f)
                {
                    i++;
                    continue;
                }
                int start = i;
                float total = 0f;
                while (i < s.Count && Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i]))) >= 1e-3f)
                {
                    total += Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i])));
                    i++;
                }
                if (total > 30f)
                {
                    large++;
                    int tele = 0;
                    for (int k = start - 1; k >= 0 && s[k].Activity == RoutineActivity.Telegraph; k--)
                    {
                        tele++;
                    }
                    Assert.GreaterOrEqual(tele * Dt, 0.6f - 1e-3f,
                        $"{turning} of {total:0} deg at record {start} was preceded by only {tele * Dt:0.00} s of telegraph");
                }
            }
            return large;
        }

        // ----- 08 -----

        private IEnumerator DriveIntoExit()
        {
            ZoneDef exit = Game.Def.Exit;
            Chair.Teleport(new Vector3(exit.X - 0.9f, 0f, exit.Z), 90f);
            Chair.ScriptedDirection = Vector3.right;
            int guard = 0;
            while (Game.State == PlayState.Playing && guard++ < 100)
            {
                yield return new WaitForFixedUpdate();
            }
            Chair.ScriptedDirection = null;
        }

        [UnityTest]
        public IEnumerator Step08_Win()
        {
            yield return DriveIntoExit();
            Assert.AreEqual(PlayState.Won, Game.State);
            Assert.IsTrue(Game.Def.Exit.Contains(Chair.transform.position));
            Assert.IsTrue(main.Hud.WinVisible, "win panel hidden");
            Assert.IsFalse(main.Hud.FailVisible);
            yield return null;
            // Found by looking at a built player screenshot: the title card must never overlap a panel.
            Assert.AreEqual(0f, main.Hud.TitleCardAlpha, "title card still visible over the win panel");
        }

        // ----- 09 -----

        [UnityTest]
        public IEnumerator Step09_Restart()
        {
            yield return Steps(5);
            int baseline = CountObjects();

            // From Caught.
            PinStaringAtChair();
            Chair.ScriptedDirection = Vector3.forward;
            int guard = 0;
            while (Game.State == PlayState.Playing && guard++ < 100)
            {
                yield return new WaitForFixedUpdate();
            }
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Caught, Game.State, "precondition: caught");
            Game.Restart();
            yield return Steps(3);
            AssertFreshLevel(baseline, "after Caught");

            // From Won.
            yield return DriveIntoExit();
            Assert.AreEqual(PlayState.Won, Game.State, "precondition: won");
            Game.Restart();
            yield return Steps(3);
            AssertFreshLevel(baseline, "after Won");
        }

        // ----- 10 (beyond the PRD's nine): the level is winnable by a player who obeys the rules. -----

        /// <summary>
        /// A disciplined bot plays the real level from spawn, with no teleport: it follows a route and moves
        /// only while the eye indicator is closed and no inhabitant is telegraphing. It must reach the exit
        /// without ever being caught. This is the acceptance "playable from launch to win screen" checked
        /// with the game's own rules and timing, where the audit only checks a grid.
        /// </summary>
        [UnityTest]
        public IEnumerator Step10_DisciplinedBotWins()
        {
            Vector3[] route =
            {
                new Vector3(-3.3f, 0f, 0.85f), new Vector3(3.3f, 0f, 0.85f), new Vector3(3.3f, 0f, 2.3f), new Vector3(3.75f, 0f, 2.3f),
            };
            int next = 0;
            int movingSteps = 0;
            float worstSeenMoving = 0f;
            void Drive()
            {
                if (Game.State != PlayState.Playing)
                {
                    Chair.ScriptedDirection = null;
                    return;
                }
                worstSeenMoving = Mathf.Max(worstSeenMoving, Game.SeenMoving);
                Vector3 to = YawMath.Planar(route[next] - Chair.transform.position);
                if (to.magnitude < 0.12f && next < route.Length - 1)
                {
                    next++;
                    to = YawMath.Planar(route[next] - Chair.transform.position);
                }
                bool warned = Habitant.Routine.IsTelegraphing;
                bool go = !Game.Seen && !warned;
                Chair.ScriptedDirection = go ? to.normalized : (Vector3?)null;
                if (go)
                {
                    movingSteps++;
                }
            }
            Game.FixedStepped += Drive;
            Time.timeScale = 8f;
            float realStart = Time.realtimeSinceStartup;
            while (Game.State == PlayState.Playing && Game.Elapsed < 240f && Time.realtimeSinceStartup - realStart < 120f)
            {
                yield return null;
            }
            Time.timeScale = 1f;
            Game.FixedStepped -= Drive;
            Chair.ScriptedDirection = null;
            Debug.Log($"[Probe] disciplined bot: state {Game.State} after {Game.Elapsed:0.0} s of game time, " +
                      $"{movingSteps * Dt:0.0} s spent moving, worst seen-and-moving {worstSeenMoving:0.00} s, waypoint {next + 1}/{route.Length}");
            Assert.AreEqual(PlayState.Won, Game.State,
                $"the disciplined bot did not win: {Game.State} after {Game.Elapsed:0.0} s, waypoint {next + 1}/{route.Length}");
            // The bot stops on the step after the eye opens: at most one step seen while moving.
            Assert.LessOrEqual(worstSeenMoving, Dt + 1e-4f, "the eye indicator reached the bot later than one step");
        }

        /// <summary>
        /// Fairness (PRD 1.2 pillar 2): a bot with a human reaction time of 0.24 s, longer than the 0.2 s
        /// grace, must still win without being caught, by reading only what the player is shown: the
        /// telegraph and the floor cone (kept at a 15 deg margin, and ahead of a walking inhabitant).
        /// If this fails, getting caught is not the player's fault.
        /// </summary>
        [UnityTest]
        public IEnumerator Step11_HumanReactionBotWins()
        {
            Vector3[] route =
            {
                new Vector3(-3.3f, 0f, 0.85f), new Vector3(3.3f, 0f, 0.85f), new Vector3(3.3f, 0f, 2.3f), new Vector3(3.75f, 0f, 2.3f),
            };
            const int reactionSteps = 12;
            var decisions = new Queue<bool>();
            for (int i = 0; i < reactionSteps; i++)
            {
                decisions.Enqueue(false);
            }
            var samples = new Vector3[5];
            int next = 0;
            float worstSeenMoving = 0f;
            var trace = new Queue<string>();
            bool Danger()
            {
                InhabitantRoutine r = Habitant.Routine;
                if (r.IsTelegraphing)
                {
                    return true;
                }
                // The bot reads the floor fan, as a player does: a horizontal wedge from the inhabitant's
                // feet (not the true 3D cone, whose blind spot right under the eyes the player cannot see),
                // kept at a 15 deg margin and also projected 0.6 m ahead of a walking inhabitant.
                Chair.GetSamplePoints(samples);
                Vector3 eye = r.EyePosition;
                Vector3 ahead = r.LastActivity == RoutineActivity.Walking ? eye + YawMath.Forward(r.BodyYaw) * 0.6f : eye;
                foreach (Vector3 p in samples)
                {
                    foreach (Vector3 e in new[] { eye, ahead })
                    {
                        Vector3 flat = YawMath.Planar(p - e);
                        bool inWedge = flat.magnitude <= Tuning.ViewRange
                            && Mathf.Abs(Mathf.DeltaAngle(r.EyeYaw, YawMath.YawOf(flat))) <= Tuning.ViewHalfAngle + 15f;
                        if (inWedge && !Vision.Occluded(e, p))
                        {
                            return true;
                        }
                    }
                }
                return false;
            }
            void Drive()
            {
                if (Game.State != PlayState.Playing)
                {
                    Chair.ScriptedDirection = null;
                    return;
                }
                worstSeenMoving = Mathf.Max(worstSeenMoving, Game.SeenMoving);
                bool danger = Danger();
                decisions.Enqueue(!danger);
                bool go = decisions.Dequeue();
                InhabitantRoutine rr = Habitant.Routine;
                trace.Enqueue($"t={Game.Elapsed:0.00} chair=({Chair.transform.position.x:0.00},{Chair.transform.position.z:0.00}) moving={Chair.IsMoving} " +
                              $"seen={Game.Seen} sm={Game.SeenMoving:0.00} danger={danger} go={go} hab=({rr.Position.x:0.00},{rr.Position.z:0.00}) " +
                              $"body={rr.BodyYaw:0} head={rr.HeadYaw:0} act={rr.LastActivity}");
                if (trace.Count > 40)
                {
                    trace.Dequeue();
                }
                Vector3 to = YawMath.Planar(route[next] - Chair.transform.position);
                if (to.magnitude < 0.12f && next < route.Length - 1)
                {
                    next++;
                    to = YawMath.Planar(route[next] - Chair.transform.position);
                }
                Chair.ScriptedDirection = go ? to.normalized : (Vector3?)null;
            }
            Game.FixedStepped += Drive;
            Time.timeScale = 8f;
            float realStart = Time.realtimeSinceStartup;
            while (Game.State == PlayState.Playing && Game.Elapsed < 300f && Time.realtimeSinceStartup - realStart < 120f)
            {
                yield return null;
            }
            Time.timeScale = 1f;
            Game.FixedStepped -= Drive;
            Chair.ScriptedDirection = null;
            if (Game.State != PlayState.Won)
            {
                Debug.Log("[Probe] trace before the end:\n" + string.Join("\n", trace));
            }
            Debug.Log($"[Probe] human reaction bot: state {Game.State} after {Game.Elapsed:0.0} s of game time, " +
                      $"worst seen-and-moving {worstSeenMoving:0.00} s, waypoint {next + 1}/{route.Length}");
            Assert.AreEqual(PlayState.Won, Game.State,
                $"a player reacting in 0.24 s to the telegraph and the cone did not win: {Game.State} after {Game.Elapsed:0.0} s, " +
                $"waypoint {next + 1}/{route.Length}");
        }

        /// <summary>
        /// Regression of the bug the human reaction bot found: the inhabitant walking through a still chair
        /// shoved it, the shove counted as motion, and the player was caught for being bumped.
        /// </summary>
        [UnityTest]
        public IEnumerator Step12_InhabitantWalkingThroughStillChairDoesNotCatchIt()
        {
            // On the walk from station 2 to station 3, where the bot was standing when it got caught.
            var spot = new Vector3(1.05f, 0f, 0.86f);
            Chair.Teleport(spot, 0f);
            InhabitantRoutine routine = Habitant.Routine;
            bool walkedThrough = false;
            void Watch()
            {
                walkedThrough |= YawMath.Planar(routine.Position - spot).magnitude < Tuning.InhabitantRadius;
            }
            Game.FixedStepped += Watch;
            Time.timeScale = 8f;
            float realStart = Time.realtimeSinceStartup;
            // Until the inhabitant has walked from station 2 to station 3 past the chair. Level 1 starts at
            // station 3 since M2.1, so that walk ends the first loop (about 39 s): wait for it, by game time.
            while (!walkedThrough && Game.Elapsed < 60f && Time.realtimeSinceStartup - realStart < 90f && Game.State == PlayState.Playing)
            {
                yield return null;
            }
            Time.timeScale = 1f;
            Game.FixedStepped -= Watch;
            // The catch ends the level before the inhabitant reaches the spot, so it is asserted first.
            Assert.AreEqual(PlayState.Playing, Game.State, "the still chair was caught when the inhabitant walked into it");
            Assert.That(YawMath.Planar(Chair.transform.position - spot).magnitude, Is.LessThan(1e-3f), "the still chair was shoved");
            Assert.IsTrue(walkedThrough, "premise broken: the inhabitant never walked through the chair spot");
        }

        private void AssertFreshLevel(int baseline, string when)
        {
            Assert.AreEqual(PlayState.Playing, Game.State, when);
            Assert.That((Chair.transform.position - Spawn).magnitude, Is.LessThan(0.05f), when + ": chair not back at spawn");
            Assert.AreEqual(0f, Mathf.DeltaAngle(Chair.Yaw, 0f), 0.01f, when + ": chair yaw not reset");
            Assert.IsFalse(main.Hud.FailVisible || main.Hud.WinVisible, when + ": a panel is still shown");
            Assert.IsFalse(Habitant.Routine.IsStartled, when + ": the inhabitant is still startled");
            Assert.AreEqual(baseline, CountObjects(), when + ": object count differs from boot");
        }
    }
}
