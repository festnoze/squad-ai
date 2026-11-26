using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// SPECTATOR (docs/next/progress/SPECTATOR.md) on the real Boot scene under GameRules.M4:
    /// <list type="bullet">
    /// <item>Spectator01 (level7, whose spawn stands in a watcher's cone at t = 0): a level built with GameState.Spectator
    /// never starts; with a move input and a start press for 3 s the chair stays put, nobody sees it, the clock and the
    /// creak never run, the level is neither won nor lost (not even with the chair put on the exit), nothing is saved,
    /// while the inhabitants still move and the intro card goes on the first input. The HUD shows the spectator tag and
    /// the pause menu offers the level select.</item>
    /// <item>Spectator02 (level1): the free camera flies straight through a wall (no collision), and a level built without
    /// spectator mode hands the camera back to the orbit camera.</item>
    /// </list>
    /// </summary>
    public sealed class ProbeTestsSpectator
    {
        private const float Dt = Tuning.FixedStep;
        private const string WatchedLevel = "level7";
        private const string FlyLevel = "level1";

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
            GameState.HoldStart = false;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Spectator = false;
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

        private static IEnumerator FixedSteps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private void LoadSpectator(string id)
        {
            Game.Spectator = true;
            Game.LoadLevel(id);
            Game.Rules = GameRules.M4;
            Assert.AreEqual(id, Game.Def.Id, "premise: the level loaded");
            Assert.AreEqual(PlayState.Playing, Game.State, id + ": premise: playing");
            Assert.IsFalse(Game.Started, id + ": a spectator level started at the build");
        }

        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Spectator01_FurnitureOutOfPlayWorldRuns()
        {
            LoadSpectator(WatchedLevel);
            Assert.IsTrue(main.Hud.SpectatorShown, "the HUD does not show the spectator tag");
            Assert.IsTrue(main.Hud.CardHeld, "the intro card is not up at the build");

            Vector3 chair0 = Chair.transform.position;
            float yaw0 = Chair.Yaw;
            var people0 = new List<Vector3>();
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                people0.Add(h.transform.position);
            }
            int seen = 0;
            int coneAlarm = 0;
            int moving = 0;
            void Watch()
            {
                // A watcher seeing a household door swing (LeafSeen, the dog's SeenByDog) is not a sighting of the chair.
                seen += Game.Seen ? 1 : 0;
                moving += Chair.IsMoving || Game.FurnitureMoving ? 1 : 0;
                foreach (Vision v in Game.Level.Visions)
                {
                    coneAlarm += v != null && v.SeesPlayer ? 1 : 0;
                }
            }
            Game.FixedStepped += Watch;
            int steps = Mathf.RoundToInt(3f / Dt);
            try
            {
                // Every input that would start a played level: a move, a start press, the action key.
                InputReader.InjectMoveVector(new Vector2(0.3f, 1f));
                InputReader.InjectStartPress();
                InputReader.InjectAction();
                yield return FixedSteps(steps);
            }
            finally
            {
                Game.FixedStepped -= Watch;
                InputReader.ClearMoveVector();
            }

            Assert.IsFalse(Game.Started, "a spectator level started on an input");
            Assert.IsTrue(Game.SpectatorCardDismissed, "the first input did not drop the intro card");
            Assert.IsFalse(main.Hud.CardHeld, "the intro card is still held after the first input");
            Assert.AreEqual(0, Game.Steps, "the clock ran in spectator mode");
            Assert.GreaterOrEqual(Game.WorldSteps, steps, "the world did not run in spectator mode");
            Assert.AreEqual(0, seen, "a watcher saw the chair in spectator mode");
            Assert.AreEqual(0, coneAlarm, "a cone saw the chair in spectator mode");
            Assert.AreEqual(0, moving, "the chair moved in spectator mode");
            Assert.Less(YawMath.Planar(Chair.transform.position - chair0).magnitude, 0.01f, "the chair left its spawn");
            Assert.Less(Mathf.Abs(Mathf.DeltaAngle(yaw0, Chair.Yaw)), 0.5f, "the chair turned");
            Assert.AreEqual(0f, Game.Creak.Value, 1e-4f, "the creak gauge filled in spectator mode");
            Assert.AreEqual(PlayState.Playing, Game.State, "a spectator level ended");
            Assert.AreEqual(0, Game.DiscoveryCount, "a discovery in spectator mode");

            float moved = 0f;
            for (int i = 0; i < people0.Count; i++)
            {
                moved = Mathf.Max(moved, Vector3.Distance(people0[i], Game.Level.Inhabitants[i].transform.position));
            }
            Assert.Greater(moved, 0.2f, "no inhabitant moved in spectator mode");

            // The chair put on the exit: still no win (the exit counts only once started, and Win refuses a spectator).
            if (Game.Def.Exit != null)
            {
                Chair.transform.position = new Vector3(Game.Def.Exit.X, Chair.transform.position.y, Game.Def.Exit.Z);
                yield return FixedSteps(10);
                Assert.AreEqual(PlayState.Playing, Game.State, "a spectator level was won on the exit");
            }

            // Nothing saved: no win, no record, no stars.
            Assert.IsFalse(SaveStore.IsWon(WatchedLevel), "a spectator session saved a win");
            Assert.IsFalse(SaveStore.TryGetBest(Game.Def.RecordId, SaveStore.Options.DifficultyId, out _), "a spectator session saved a record");
            Assert.AreEqual(0, SaveStore.Current.StarsOf(Game.Def.RecordId, SaveStore.Options.DifficultyId), "a spectator session saved stars");

            // The pause menu offers the level select instead of the main menu.
            if (main.Menu != null && !main.Menu.TitleOpen)
            {
                InputReader.InjectPausePress();
                yield return null;
                yield return null;
                Assert.IsTrue(main.Menu.PauseOpen, "the pause press opened no pause menu in spectator mode");
                Assert.AreEqual(Strings.PauseLevels, main.Menu.Labels["MainMenuLabel"].text, "the pause menu does not offer the level select");
                main.Menu.SetPaused(false);
                yield return null;
            }

            // A restart stays in spectator mode.
            Game.Restart();
            Assert.IsTrue(Game.Spectator, "a restart left spectator mode");
            Assert.IsFalse(Game.Started, "a restarted spectator level started");
            AssertClean();
        }

        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Spectator02_FreeCameraFliesThroughAWall()
        {
            LoadSpectator(FlyLevel);
            SpectatorCamera free = main.Camera.GetComponent<SpectatorCamera>();
            Assert.IsNotNull(free, "no free camera on the game camera");
            Assert.IsTrue(free.Active, "the free camera is not active");
            Assert.IsFalse(main.OrbitCamera.enabled, "the orbit camera still drives the camera");

            // A wall near the spawn: the first horizontal hit (not the chair, not a person) that faces sideways.
            Vector3 start = Chair.transform.position + Vector3.up * 1.6f;
            bool found = false;
            Vector3 direction = Vector3.forward;
            float wallDistance = 0f;
            for (int k = 0; k < 16 && !found; k++)
            {
                Vector3 d = Quaternion.Euler(0f, k * 22.5f, 0f) * Vector3.forward;
                RaycastHit[] hits = Physics.RaycastAll(start, d, 8f, ~0, QueryTriggerInteraction.Ignore);
                System.Array.Sort(hits, (a, b) => a.distance.CompareTo(b.distance));
                foreach (RaycastHit hit in hits)
                {
                    if (hit.distance < 0.6f || Mathf.Abs(hit.normal.y) > 0.3f
                        || hit.collider.GetComponentInParent<FurnitureController>() != null
                        || hit.collider.GetComponentInParent<Inhabitant>() != null)
                    {
                        continue;
                    }
                    found = true;
                    direction = d;
                    wallDistance = hit.distance;
                    break;
                }
            }
            Assert.IsTrue(found, "premise: no wall within 8 m of the spawn");

            float yaw = Mathf.Atan2(direction.x, direction.z) * Mathf.Rad2Deg;
            free.SetPose(start, yaw, 0f);
            InputReader.InjectMoveVector(new Vector2(0f, 1f));
            float target = wallDistance + 0.8f;
            float until = Time.realtimeSinceStartup + 30f;
            while (Vector3.Dot(main.Camera.transform.position - start, direction) < target && Time.realtimeSinceStartup < until)
            {
                yield return null;
            }
            InputReader.ClearMoveVector();
            Vector3 end = main.Camera.transform.position;
            Assert.GreaterOrEqual(Vector3.Dot(end - start, direction), target, "the free camera stopped at the wall");
            Assert.IsTrue(Physics.Linecast(start, end, ~0, QueryTriggerInteraction.Ignore), "premise: no collider between the start and the end");
            Assert.Less(Mathf.Abs(end.y - start.y), 0.05f, "a level flight changed height");

            // A level built without spectator mode hands the camera back.
            Game.Spectator = false;
            Game.LoadLevel(FlyLevel);
            yield return null;
            Assert.IsFalse(free.Active, "the free camera stayed active in a played level");
            Assert.IsTrue(main.OrbitCamera.enabled, "the orbit camera was not handed back");
            Assert.IsFalse(main.Hud.SpectatorShown, "the spectator tag stayed in a played level");
            Assert.IsTrue(Game.Started, "a played level with the hold off did not start");
            AssertClean();
        }

        private void AssertClean()
        {
            Assert.AreEqual(0, exceptions, "errors were logged: " + string.Join(" | ", logged));
        }
    }
}
