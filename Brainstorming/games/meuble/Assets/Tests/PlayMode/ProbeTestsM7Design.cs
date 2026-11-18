using System.Collections;
using System.Collections.Generic;
using System.Linq;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M7 design probe (docs/CONTRACT_M7.md 4.1 and 4.2), on the real Boot scene.
    /// Step 64a: switching the Difficulté option changes the live watcher parameters at the next level load (a restart
    /// counts): the routines' range, angle and hearing, every Vision's range, the caught grace, the dog's bark grace and the
    /// creak fill time are the Difficile ones after the restart, the Normal ones before it and again after switching back.
    /// The record of a win goes under the difficulty the level was built with.
    /// Step 64b: each level's designerRouteHard (LevelAudit -writeRoutes at Difficile) wins at Difficile through
    /// RouteReplayer at the standard offsets (-0.2, 0 and +0.2 s, as step 45), with no discovery, no alert, no creak, no bark,
    /// no load fall and no robot contact. The Normal routes keep their own replays (steps 20, 35, 45 and 56a).
    /// Every step asserts its premise first, so a level that does not run cannot pass.
    /// </summary>
    public sealed class ProbeTestsM7Design
    {
        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();

        /// <summary>CONTRACT_M5 12 (step 45): every route is replayed this much early, on time and late.</summary>
        private static readonly float[] Offsets = { -0.2f, 0f, 0.2f };

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
            yield return new WaitForFixedUpdate();
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            DifficultyDef.Current = null;
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

        /// <summary>The Options page's way: the saved options with only the difficulty changed.</summary>
        private static void SetDifficulty(string id)
        {
            SaveOptions o = SaveStore.Options;
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Cone = o.Cone, Quality = o.Quality, Difficulty = id,
            });
        }

        private IEnumerator LoadFresh(string id)
        {
            Game.LoadLevel(id);
            Game.Rules = GameRules.M4;
            yield return new WaitForFixedUpdate();
            Assert.AreEqual(id, Game.LevelId, "premise: the level was loaded");
            Assert.AreEqual(PlayState.Playing, Game.State, id + ": premise: the level is playing");
        }

        /// <summary>The live watcher parameters of the current level, one line per inhabitant, plus the grace and the creak.</summary>
        private struct Live
        {
            public float[] Range;
            public float[] Angle;
            public float[] Hearing;
            public float[] VisionRange;
            public float Grace;
            public float Fill;
        }

        private Live Read()
        {
            List<Inhabitant> people = Game.Level.Inhabitants;
            var live = new Live
            {
                Range = people.Select(h => h.Routine.ViewRange).ToArray(),
                Angle = people.Select(h => h.Routine.HalfAngle).ToArray(),
                Hearing = people.Select(h => h.Routine.HearingFactor).ToArray(),
                VisionRange = people.Select(h => Game.Level.Visions.Find(v => v != null && v.Owner == h)).Select(v => v != null ? v.Range : -1f).ToArray(),
                Grace = Game.Rule.Grace,
                Fill = Game.Creak.FillTime,
            };
            return live;
        }

        /// <summary>
        /// Step 64a: the option applies at the next level load (and restart), never in the middle of a level: the level keeps
        /// the difficulty it was built with, so its record and its rules always agree.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step64a_DifficultyAppliesAtTheNextLevelLoad()
        {
            const string id = "level16"; // a watchful, a hurried and a dog: every kind of watcher
            SetDifficulty(DifficultyDef.Normal);
            yield return LoadFresh(id);
            Assert.AreEqual(DifficultyDef.Normal, Game.Difficulty.Id, "premise: the default difficulty is Normal");
            Assert.GreaterOrEqual(Game.Level.Inhabitants.Count, 3, "premise: level16 has three watchers");
            yield return new WaitForFixedUpdate();
            Live normal = Read();
            Assert.AreEqual(Tuning.CaughtGrace, normal.Grace, 1e-6f, "Normal keeps the 0.2 s grace");
            Assert.AreEqual(Tuning.CreakFillTime, normal.Fill, 1e-6f, "Normal keeps the 20 s creak");

            SetDifficulty(DifficultyDef.Difficile);
            yield return new WaitForFixedUpdate();
            Live unchanged = Read();
            Assert.AreEqual(normal.Range, unchanged.Range, "the level in play keeps its difficulty until the next load");
            Assert.AreEqual(normal.Grace, unchanged.Grace, 1e-6f);
            Assert.AreEqual(DifficultyDef.Normal, Game.Difficulty.Id);

            Game.Restart();
            Game.Rules = GameRules.M4;
            yield return new WaitForFixedUpdate();
            yield return new WaitForFixedUpdate();
            Assert.AreEqual(DifficultyDef.Difficile, Game.Difficulty.Id, "a restart builds the level at the saved difficulty");
            Live hard = Read();
            for (int i = 0; i < normal.Range.Length; i++)
            {
                Assert.AreEqual(normal.Range[i] * Tuning.HardViewRangeFactor, hard.Range[i], 1e-3f, "routine range of watcher " + i);
                Assert.AreEqual(Mathf.Min(89f, normal.Angle[i] + Tuning.HardHalfAngleOffset), hard.Angle[i], 1e-3f, "half angle of watcher " + i);
                Assert.AreEqual(normal.Hearing[i] * Tuning.HardHearingFactor, hard.Hearing[i], 1e-3f, "hearing of watcher " + i);
                if (normal.VisionRange[i] > 0f && hard.VisionRange[i] > 0f)
                {
                    Assert.AreEqual(normal.VisionRange[i] * Tuning.HardViewRangeFactor, hard.VisionRange[i], 1e-3f,
                        "the Vision of watcher " + i + " sees with the routine's range");
                }
            }
            Assert.AreEqual(Tuning.HardCaughtGrace, hard.Grace, 1e-6f, "the caught grace is Difficile's");
            Assert.AreEqual(Tuning.HardCreakFillTime, hard.Fill, 1e-6f, "the creak fill is Difficile's");

            SetDifficulty(DifficultyDef.Facile);
            yield return LoadFresh(id);
            yield return new WaitForFixedUpdate();
            Live easy = Read();
            Assert.AreEqual(DifficultyDef.Facile, Game.Difficulty.Id, "a level load builds the level at the saved difficulty");
            for (int i = 0; i < normal.Range.Length; i++)
            {
                Assert.Less(easy.Range[i], normal.Range[i], "Facile sees less far, watcher " + i);
            }
            Assert.Greater(easy.Grace, normal.Grace, "Facile forgives longer");
            Assert.IsEmpty(errors, string.Join("\n", errors));
        }

        /// <summary>
        /// Step 64c: the Options page cycles the Difficulté row (Normal, Difficile, Facile) and saves it; the level select shows
        /// the record of the current difficulty only (a win goes under the difficulty its level was built with).
        /// </summary>
        [UnityTest]
        [Timeout(120000)]
        public IEnumerator Step64c_OptionCyclesAndTheSelectShowsTheDifficultyRecord()
        {
            Menu menu = main.Menu;
            Assert.IsNotNull(menu.OptionsDifficultyButton, "the Options page has no Difficulté row");
            Assert.AreEqual(DifficultyDef.Normal, SaveStore.Options.DifficultyId, "premise: Normal by default");
            menu.OptionsDifficultyButton.onClick.Invoke();
            Assert.AreEqual(DifficultyDef.Difficile, SaveStore.Options.DifficultyId, "Normal, then Difficile");
            Assert.IsTrue(menu.Labels.TryGetValue("OptionsDifficultyLabel", out UnityEngine.UI.Text label)
                && label.text == string.Format(Strings.OptionsDifficulty, Strings.DifficultyDifficile), "the row shows Difficile");
            menu.OptionsDifficultyButton.onClick.Invoke();
            Assert.AreEqual(DifficultyDef.Facile, SaveStore.Options.DifficultyId, "Difficile, then Facile");

            string first = Game.LevelOrder[0];
            SaveStore.RecordWin(first, 30f, DifficultyDef.Normal);
            SaveStore.RecordWin(first, 12.5f, DifficultyDef.Difficile);
            LevelSelect select = menu.LevelSelect;
            SetDifficulty(DifficultyDef.Difficile);
            select.Refresh();
            Assert.AreEqual(string.Format(Strings.SelectBest, Strings.FormatSeconds(12.5f)), select.Cards[0].Best.text, "the Difficile record");
            SetDifficulty(DifficultyDef.Normal);
            select.Refresh();
            Assert.AreEqual(string.Format(Strings.SelectBest, Strings.FormatSeconds(30f)), select.Cards[0].Best.text, "the Normal record");
            SetDifficulty(DifficultyDef.Facile);
            select.Refresh();
            Assert.AreEqual(Strings.SelectNone, select.Cards[0].Best.text, "no Facile record yet");
            yield return null;
        }

        // ----- 64b: the Difficile routes -----

        private IEnumerator ReplayHard(string id)
        {
            CollectionAssert.Contains(Game.LevelOrder.ToList(), id, "premise: " + id + " is listed in levels.json");
            var failures = new List<string>();
            SetDifficulty(DifficultyDef.Difficile);
            foreach (float offset in Offsets)
            {
                int errorsBefore = errors.Count;
                yield return LoadFresh(id);
                Assert.AreEqual(DifficultyDef.Difficile, Game.Difficulty.Id, id + ": premise: the level runs at Difficile");
                List<RouteStepDef> route = Game.Def.DesignerRouteHard;
                Assert.GreaterOrEqual(route.Count, 2, id + ": premise: no designerRouteHard (LevelAudit -writeRoutes writes it)");
                var r = new RouteReplayer.Result();
                yield return RouteReplayer.Replay(Game, offset, r, Tuning.PlaythroughTimeScale, route);
                Debug.Log("[Step64b] " + r);
                string label = r.Label + " at Difficile";
                if (r.State != PlayState.Won)
                {
                    failures.Add($"{label}: the route did not win ({r.State}, {r.Reason}) after {r.Time:0.0} s, waypoint {r.Waypoint}/{r.Waypoints}"
                                 + (r.TimedOut ? ", timed out" : "") + (r.Stalled ? ", stalled" : ""));
                }
                if (r.Discoveries != 0 || r.Alerts != 0 || r.Creaks != 0 || r.Barks != 0)
                {
                    failures.Add($"{label}: {r.Discoveries} discoveries, {r.Alerts} alerts, {r.Creaks} creaks, {r.Barks} barks (all must be 0)");
                }
                if (r.Crashes != 0 || (r.HasLoad && !r.LoadHeld) || r.RobotContacts != 0)
                {
                    failures.Add($"{label}: {r.Crashes} load falls, {r.RobotContacts} robot contacts (all must be 0)");
                }
                if (errors.Count != errorsBefore)
                {
                    failures.Add($"{label}: error(s) logged: {string.Join(" / ", errors.Skip(errorsBefore))}");
                }
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }

        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level01Hard() { yield return ReplayHard("level1"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level02Hard() { yield return ReplayHard("level2"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level03Hard() { yield return ReplayHard("level3"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level04Hard() { yield return ReplayHard("level4"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level05Hard() { yield return ReplayHard("level5"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level06Hard() { yield return ReplayHard("level6"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level07Hard() { yield return ReplayHard("level7"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level08Hard() { yield return ReplayHard("level8"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level09Hard() { yield return ReplayHard("level9"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level10Hard() { yield return ReplayHard("level10"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level11Hard() { yield return ReplayHard("level11"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level12Hard() { yield return ReplayHard("level12"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level13Hard() { yield return ReplayHard("level13"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level14Hard() { yield return ReplayHard("level14"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level15Hard() { yield return ReplayHard("level15"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level16Hard() { yield return ReplayHard("level16"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level17Hard() { yield return ReplayHard("level17"); }
        [UnityTest, Timeout(900000)] public IEnumerator Step64b_Level18Hard() { yield return ReplayHard("level18"); }
    }
}
