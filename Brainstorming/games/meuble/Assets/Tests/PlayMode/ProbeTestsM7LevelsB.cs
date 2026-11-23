using System;
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
    /// M7 new levels probe, designer B (levels 21 and 22), on the real Boot scene.
    /// Step 58b: each level's designerRoute (LevelAudit -writeRoutes at Normal) wins at Normal and its designerRouteHard
    /// wins at Difficile, through RouteReplayer at the standard offsets (-0.2, 0 and +0.2 s, as steps 45, 56a and 64b),
    /// with no discovery, no alert, no creak, no bark, no load fall, no robot contact and no error logged, and plays the
    /// level's lesson: level 21 climbs the catwalk (split), level 22 hides in a wardrobe and comes out (wardrobe) without a
    /// remembered spot ever seen empty. The level is loaded by id (LevelLoader reads Resources/Levels/&lt;id&gt;.json), so a
    /// level not yet listed in levels.json still runs.
    /// </summary>
    public sealed class ProbeTestsM7LevelsB
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

        /// <summary>
        /// Replays the route of <paramref name="id"/> for <paramref name="difficulty"/> (designerRoute at Normal,
        /// designerRouteHard at Difficile) at the three offsets; <paramref name="lesson"/> adds a failure when a run did not
        /// play the level's lesson.
        /// </summary>
        private IEnumerator ReplayRoute(string id, string difficulty, Action<RouteReplayer.Result, List<string>> lesson)
        {
            bool hard = difficulty == DifficultyDef.Difficile;
            var failures = new List<string>();
            SetDifficulty(difficulty);
            foreach (float offset in Offsets)
            {
                int errorsBefore = errors.Count;
                Game.LoadLevel(id);
                Game.Rules = GameRules.M4;
                yield return new WaitForFixedUpdate();
                Assert.AreEqual(id, Game.LevelId, "premise: the level was loaded");
                Assert.AreEqual(PlayState.Playing, Game.State, id + ": premise: the level is playing");
                Assert.AreEqual(difficulty, Game.Difficulty.Id, id + ": premise: the level runs at " + difficulty);
                List<RouteStepDef> route = hard ? Game.Def.DesignerRouteHard : Game.Def.DesignerRoute;
                Assert.IsNotNull(route, id + ": premise: no route for " + difficulty + " (LevelAudit -writeRoutes writes it)");
                Assert.GreaterOrEqual(route.Count, 2, id + ": premise: no route for " + difficulty + " (LevelAudit -writeRoutes writes it)");
                int emptySpots0 = Game.EmptySpotCount;
                var r = new RouteReplayer.Result();
                yield return RouteReplayer.Replay(Game, offset, r, Tuning.PlaythroughTimeScale, route);
                Debug.Log("[Step58b] " + r + " at " + difficulty);
                string label = r.Label + " at " + difficulty;
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
                if (Game.EmptySpotCount != emptySpots0)
                {
                    failures.Add($"{label}: a remembered spot was seen empty {Game.EmptySpotCount - emptySpots0} time(s)");
                }
                if (errors.Count != errorsBefore)
                {
                    failures.Add($"{label}: error(s) logged: {string.Join(" | ", errors.Skip(errorsBefore))}");
                }
                lesson(r, failures);
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }

        /// <summary>Level 21 "La passerelle" (lesson split; levels v2: split + decoy, LEVELS_V2 10.1): the route climbs the
        /// catwalk and parks at least once among the decoy office chairs (one decoy-explained stop).</summary>
        private void Level21Lesson(RouteReplayer.Result r, List<string> failures)
        {
            Assert.AreEqual(LevelDef.LessonSplit, Game.Def.Lesson, "premise: level 21 teaches the split");
            // Levels v2: decoy office chairs at empty desks. A failure, not a premise, so the replay of the file as it
            // stands still reports (level21 is still the v1 file: RULEFIX/LV10 escalated, LEVELS6 reworking it).
            if (!Game.Def.Decoys.Exists(d => BodyKinds.Of(d.Kind) == BodyKinds.OfficeChair))
            {
                failures.Add($"{r.Label}: level 21 has no decoy office chair (the v2 catwalk parks among decoys, LEVELS_V2 10.1)");
            }
            if (r.TopY < Tuning.PlatformMinHeight - 0.05f)
            {
                failures.Add($"{r.Label}: the route never climbed the catwalk (top {r.TopY:0.00} m)");
            }
            if (r.Explained < 1)
            {
                failures.Add($"{r.Label}: no decoy ever explained the office chair: the route never parks among the decoys");
            }
        }

        /// <summary>Level 22 "Des cadavres dans le placard" (lesson wardrobe): the route hides in a wardrobe and comes out.</summary>
        private void Level22Lesson(RouteReplayer.Result r, List<string> failures)
        {
            Assert.AreEqual(LevelDef.LessonWardrobe, Game.Def.Lesson, "premise: level 22 teaches the wardrobe");
            Assert.IsTrue(Game.Def.DoorMemory, "premise: level 22 has door memory on");
            if (r.Hides < 1 || r.Leaves < 1 || r.OpenFailures != 0)
            {
                failures.Add($"{r.Label}: {r.Hides} hides, {r.Leaves} leaves, {r.OpenFailures} presses given up: the route must hide and come out");
            }
        }

        [UnityTest, Timeout(900000)]
        public IEnumerator Step58b1_Level21RouteWinsNormal() { yield return ReplayRoute("level21", DifficultyDef.Normal, Level21Lesson); }

        [UnityTest, Timeout(900000)]
        public IEnumerator Step58b2_Level21RouteWinsDifficile() { yield return ReplayRoute("level21", DifficultyDef.Difficile, Level21Lesson); }

        [UnityTest, Timeout(900000)]
        public IEnumerator Step58b3_Level22RouteWinsNormal() { yield return ReplayRoute("level22", DifficultyDef.Normal, Level22Lesson); }

        [UnityTest, Timeout(900000)]
        public IEnumerator Step58b4_Level22RouteWinsDifficile() { yield return ReplayRoute("level22", DifficultyDef.Difficile, Level22Lesson); }
    }
}
