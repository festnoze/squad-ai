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
    /// M7 new levels probe, designer C (levels 23 and 24), on the real Boot scene, as steps 45 and 56a: the routes the audit
    /// wrote (LevelAudit -writeRoutes) win through RouteReplayer at the standard offsets (-0.2, 0 and +0.2 s), the
    /// designerRoute at Normal and the designerRouteHard at Difficile (set through the saved options, as step 64b), with no
    /// discovery, no alert, no creak, no bark, no robot contact and no error logged.
    /// Step 58C1/C2: level 23 "Upstairs, Downstairs" (lesson wardrobe): the route hides in the wardrobe and comes out, and
    /// the household opens the hall door on its own; no remembered spot is ever seen empty.
    /// Step 58C3/C4: level 24 "The Great Escape" (lesson final): the route opens the bedroom door itself and wins.
    /// A level does not need to be in levels.json to load: GameState.LoadLevel reads it by id from Resources/Levels.
    /// </summary>
    public sealed class ProbeTestsM7LevelsC
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
        /// Replays the level's route for <paramref name="difficulty"/> at every offset. <paramref name="lesson"/> checks the
        /// level's own premise once loaded; <paramref name="extra"/> adds the level's own checks of one run (baseline counts
        /// taken just before the replay are passed in).
        /// </summary>
        private IEnumerator ReplayAt(string id, string difficulty, string tag, Action lesson,
            Func<RouteReplayer.Result, int, int, string, IEnumerable<string>> extra)
        {
            SetDifficulty(difficulty);
            var failures = new List<string>();
            foreach (float offset in Offsets)
            {
                int errorsBefore = errors.Count;
                Game.LoadLevel(id);
                Game.Rules = GameRules.M4;
                yield return new WaitForFixedUpdate();
                Assert.AreEqual(id, Game.LevelId, "premise: the level was loaded");
                Assert.AreEqual(PlayState.Playing, Game.State, id + ": premise: the level is playing");
                Assert.AreEqual(difficulty, Game.Difficulty.Id, id + ": premise: the level runs at " + difficulty);
                lesson();
                List<RouteStepDef> route = difficulty == DifficultyDef.Difficile ? Game.Def.DesignerRouteHard : Game.Def.DesignerRoute;
                Assert.IsNotNull(route, id + ": premise: no route for " + difficulty + " (LevelAudit -writeRoutes writes it)");
                Assert.GreaterOrEqual(route.Count, 2, id + ": premise: no route for " + difficulty + " (LevelAudit -writeRoutes writes it)");
                int emptySpots0 = Game.EmptySpotCount;
                int householdOpens0 = Game.HouseholdDoorOpenCount;
                var r = new RouteReplayer.Result();
                yield return RouteReplayer.Replay(Game, offset, r, Tuning.PlaythroughTimeScale, route);
                Debug.Log("[" + tag + "] " + r);
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
                if (r.RobotContacts != 0 || r.OpenFailures != 0)
                {
                    failures.Add($"{label}: {r.RobotContacts} robot contacts, {r.OpenFailures} presses given up (all must be 0)");
                }
                failures.AddRange(extra(r, emptySpots0, householdOpens0, label));
                if (errors.Count != errorsBefore)
                {
                    failures.Add($"{label}: error(s) logged: {string.Join(" | ", errors.Skip(errorsBefore))}");
                }
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }

        // ----- level 23: Upstairs, Downstairs (wardrobe) -----

        private void Level23Premise()
        {
            Assert.AreEqual(LevelDef.LessonWardrobe, Game.Def.Lesson, "premise: level 23 teaches the wardrobe");
            Assert.IsTrue(Game.Def.DoorMemory, "premise: level 23 has door memory on");
            Assert.IsTrue(Game.Def.Doors.Exists(d => d.OpenedByInhabitants), "premise: level 23 has a door the household opens");
        }

        private IEnumerable<string> Level23Checks(RouteReplayer.Result r, int emptySpots0, int householdOpens0, string label)
        {
            if (r.Hides < 1 || r.Leaves < 1)
            {
                yield return $"{label}: {r.Hides} hides, {r.Leaves} leaves: the route must hide in the wardrobe and come out";
            }
            if (Game.EmptySpotCount != emptySpots0)
            {
                yield return $"{label}: a remembered spot was seen empty {Game.EmptySpotCount - emptySpots0} time(s)";
            }
            if (Game.HouseholdDoorOpenCount - householdOpens0 < 1)
            {
                yield return $"{label}: the household never opened the hall door";
            }
        }

        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step58C1_Level23RouteWins()
        {
            yield return ReplayAt("level23", DifficultyDef.Normal, "Step58C1", Level23Premise, Level23Checks);
        }

        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step58C2_Level23RouteWinsHard()
        {
            yield return ReplayAt("level23", DifficultyDef.Difficile, "Step58C2", Level23Premise, Level23Checks);
        }

        // ----- level 24: The Great Escape (final) -----

        private void Level24Premise()
        {
            Assert.AreEqual(LevelDef.LessonFinal, Game.Def.Lesson, "premise: level 24 is the finale");
            Assert.IsTrue(Game.Def.Doors.Exists(d => d.Id == "porte_chambre"), "premise: level 24 has the closed bedroom door");
        }

        private IEnumerable<string> Level24Checks(RouteReplayer.Result r, int emptySpots0, int householdOpens0, string label)
        {
            if (r.Opens < 1)
            {
                yield return $"{label}: the route never opened a door (the bedroom door is closed)";
            }
        }

        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step58C3_Level24RouteWins()
        {
            yield return ReplayAt("level24", DifficultyDef.Normal, "Step58C3", Level24Premise, Level24Checks);
        }

        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step58C4_Level24RouteWinsHard()
        {
            yield return ReplayAt("level24", DifficultyDef.Difficile, "Step58C4", Level24Premise, Level24Checks);
        }
    }
}
