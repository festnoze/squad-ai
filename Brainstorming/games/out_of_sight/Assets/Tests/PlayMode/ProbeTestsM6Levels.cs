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
    /// M6 levels probe (docs/CONTRACT_M6.md 2.5 to 2.8 and 5), on the real Boot scene.
    /// Step 56a: level 18 "L'armoire" (lesson wardrobe). The designer route the audit wrote (LevelAudit -writeRoutes) wins
    /// through RouteReplayer at the standard offsets (-0.2, 0 and +0.2 s, as step 45), with no discovery, no alert, no creak
    /// and no bark, and plays the lesson: the stool hides in the wardrobe and comes out (the route's "hide" and "leave"),
    /// the household opens the kitchen door on its own, and no remembered spot is ever seen empty.
    /// </summary>
    public sealed class ProbeTestsM6Levels
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

        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step56a_Level18RouteWins()
        {
            const string id = "level18";
            CollectionAssert.Contains(Game.LevelOrder.ToList(), id, "premise: level18 is listed in levels.json");
            var failures = new List<string>();
            foreach (float offset in Offsets)
            {
                int errorsBefore = errors.Count;
                Game.LoadLevel(id);
                Game.Rules = GameRules.M4;
                yield return new WaitForFixedUpdate();
                Assert.AreEqual(id, Game.LevelId, "premise: the level was loaded");
                Assert.AreEqual(PlayState.Playing, Game.State, "premise: the level is playing");
                Assert.AreEqual(LevelDef.LessonWardrobe, Game.Def.Lesson, "premise: level 18 teaches the wardrobe");
                Assert.IsTrue(Game.Def.DoorMemory, "premise: level 18 has door memory on");
                Assert.IsTrue(Game.Def.Doors.Exists(d => d.OpenedByInhabitants), "premise: level 18 has a door the household opens");
                Assert.IsTrue(Game.Def.DesignerRoute.Exists(s => s.Action == RouteReplayer.ActionHide),
                    "premise: the route hides in the wardrobe (LevelAudit -writeRoutes writes it)");
                int emptySpots0 = Game.EmptySpotCount;
                int householdOpens0 = Game.HouseholdDoorOpenCount;
                var r = new RouteReplayer.Result();
                yield return RouteReplayer.Replay(Game, offset, r, Tuning.PlaythroughTimeScale);
                Debug.Log("[Step56a] " + r);
                if (r.State != PlayState.Won)
                {
                    failures.Add($"{r.Label}: the route did not win ({r.State}, {r.Reason}) after {r.Time:0.0} s, waypoint {r.Waypoint}/{r.Waypoints}");
                }
                if (r.Discoveries != 0 || r.Alerts != 0 || r.Creaks != 0 || r.Barks != 0)
                {
                    failures.Add($"{r.Label}: {r.Discoveries} discoveries, {r.Alerts} alerts, {r.Creaks} creaks, {r.Barks} barks (all must be 0)");
                }
                if (r.Hides < 1 || r.Leaves < 1 || r.OpenFailures != 0)
                {
                    failures.Add($"{r.Label}: {r.Hides} hides, {r.Leaves} leaves, {r.OpenFailures} presses given up: the route must hide and come out");
                }
                if (Game.EmptySpotCount != emptySpots0)
                {
                    failures.Add($"{r.Label}: a remembered spot was seen empty {Game.EmptySpotCount - emptySpots0} time(s)");
                }
                if (Game.HouseholdDoorOpenCount - householdOpens0 < 1)
                {
                    failures.Add($"{r.Label}: the household never opened the kitchen door");
                }
                if (errors.Count != errorsBefore)
                {
                    failures.Add($"{r.Label}: error(s) logged: {string.Join(" | ", errors.Skip(errorsBefore))}");
                }
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }

        /// <summary>
        /// Level 11's counter-route "drop at the spawn, then full speed" (CONTRACT_M5 19, M5): full speed from the spawn into
        /// a corner 1.5 m away (the vase falls there), then full speed through the bedroom door, down the corridor, along the
        /// living room lane behind the two bookcases and through the kitchen to the exit, never careful and never waiting.
        /// Rows are x, z. CARD4 (docs/next/progress/CARD4.md): the corridor now ends at the living room door (5.95, 4.75) and
        /// the kitchen is entered from the living room (11.25, 3.95); Lea dusts the living room bookshelf at (9.25, 8.15),
        /// about 5.5 m from the corner where the vase falls (her crash radius is 6 m).
        /// </summary>
        private static readonly float[,] Level11DropAtSpawn =
        {
            { 3.25f, 6.25f }, { 3.75f, 6.25f }, { 3.75f, 7.25f }, { 3.75f, 7.75f }, { 4.75f, 7.75f }, { 5.25f, 7.75f },
            { 5.25f, 6.75f }, { 5.25f, 5.75f }, { 5.25f, 4.75f }, { 6.25f, 4.75f }, { 7.25f, 4.75f }, { 8.25f, 4.75f },
            { 9.25f, 4.75f }, { 10.25f, 4.75f }, { 11.25f, 4.75f }, { 11.25f, 3.75f }, { 11.25f, 2.75f }, { 11.25f, 1.75f },
        };

        /// <summary>
        /// Step 57a, the vase drop costs something on level 11 (CONTRACT_M5 19 M5, open question 25: a fallen load costs one
        /// discovery, never the level by itself). The counter-route drops the vase near the spawn and then runs at full speed
        /// (no balance to keep any more): it must not win. Premises: the vase falls within 2.5 m of the spawn in the first
        /// 3 s, nobody saw the chair before the crash, the first alert follows the crash, and the alerted human has memory
        /// and stood within Tuning.CrashRadius times her hearing factor of the clue.
        /// </summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator Step57a_Level11VaseDropIsHeard()
        {
            yield return DropAtSpawnThenFullSpeed("level11", Level11DropAtSpawn);
        }

        /// <summary>
        /// Level 13's counter-route "drop at the spawn, then full speed" (L17HIDE, 2026-11-23): full speed from the office
        /// chair's spawn south (the vase falls on that full start, 0.5 s in, first run 2026-11-23), a hard turn west into the
        /// corner 1.5 m away, then the designer's
        /// own way at full speed (the south door of the direction office, the open-plan desks, the reception, the exit),
        /// never careful and never waiting. Rows are x, z. Level 13 is the "load" lesson level of the act; Claire stands
        /// 1 m from the spawn facing the north wall at the start, within her crash range.
        /// </summary>
        private static readonly float[,] Level13DropAtSpawn =
        {
            { 2.25f, 7.75f }, { 2.25f, 7.25f }, { 2.25f, 6.75f }, { 1.25f, 6.75f }, { 1.25f, 6.25f }, { 2.25f, 6.25f },
            { 2.25f, 5.25f }, { 2.25f, 4.75f }, { 1.25f, 4.75f }, { 1.25f, 3.75f }, { 1.25f, 3.25f }, { 2.25f, 3.25f },
            { 3.25f, 3.25f }, { 3.75f, 3.25f }, { 3.75f, 2.25f }, { 4.75f, 2.25f }, { 5.25f, 2.25f }, { 5.25f, 3.25f },
            { 6.25f, 3.25f }, { 6.75f, 3.25f }, { 6.75f, 2.25f }, { 6.75f, 1.25f }, { 7.75f, 1.25f }, { 8.75f, 1.25f },
            { 9.75f, 1.25f }, { 10.75f, 1.25f }, { 11.75f, 1.25f }, { 12.75f, 1.25f }, { 13.25f, 1.25f },
        };

        /// <summary>
        /// Step 57b, the same counter-route on level 13 (CONTRACT_M5 19 M5): the drop at the spawn then full speed must not
        /// win. Same premises as step 57a. L17HIDE (2026-11-23): retargeted from level17, where the vase no longer fell after
        /// the LEVELS6 rebuild (its start now seats Mamie on the chair, her "sit": "player" station, the likely cause); level
        /// 13 is the other shipped level, besides level 11 (step 57a), that carries the vase.
        /// </summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator Step57b_Level13VaseDropIsHeard()
        {
            yield return DropAtSpawnThenFullSpeed("level13", Level13DropAtSpawn);
        }

        private IEnumerator DropAtSpawnThenFullSpeed(string id, float[,] rows, int openRow = -1, string door = null)
        {
            Game.LoadLevel(id);
            Game.Rules = GameRules.M4;
            yield return new WaitForFixedUpdate();
            Assert.AreEqual(id, Game.LevelId, "premise: the level was loaded");
            Assert.IsTrue(Game.CarryingLoad, "premise: the vase rides at the start");
            Vector3 spawn = YawMath.Planar(Game.Def.Player.Position);
            List<RouteStepDef> route = Game.Def.DesignerRoute;
            route.Clear();
            for (int i = 0; i < rows.GetLength(0); i++)
            {
                route.Add(new RouteStepDef
                {
                    X = rows[i, 0], Z = rows[i, 1], At = 0.3f + 0.1f * i,
                    Action = i == openRow ? RouteStepDef.ActionOpen : null, Door = i == openRow ? door : null,
                });
            }
            int crashes0 = Game.CrashCount;
            int alerts0 = Game.AlertCount;
            float crashAt = -1f;
            float alertAt = -1f;
            Vector3 clue = Vector3.zero;
            bool seenBeforeCrash = false;
            string alerted = null;
            bool alertedRemembers = false;
            float alertedDistance = -1f;
            float alertedRadius = -1f;
            void Watch()
            {
                if (crashAt < 0f && Game.CrashCount > crashes0)
                {
                    crashAt = Game.Elapsed;
                    clue = YawMath.Planar(Game.ClueAt);
                }
                seenBeforeCrash |= crashAt < 0f && Game.Seen;
                if (alertAt < 0f && Game.AlertCount > alerts0)
                {
                    alertAt = Game.Elapsed;
                    foreach (Inhabitant h in Game.Level.Inhabitants)
                    {
                        if (h.Routine.Mode == InhabitantMode.Alerted && alerted == null)
                        {
                            alerted = h.Def.Name;
                            alertedRemembers = h.Routine.Personality.Memory;
                            alertedDistance = YawMath.Planar(h.Routine.Position - clue).magnitude;
                            alertedRadius = Tuning.CrashRadius * h.Routine.HearingFactor;
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
            float fromSpawn = YawMath.Planar(clue - spawn).magnitude;
            Debug.Log($"[Step57] {id}: {r}; crash at {crashAt:0.00} s, clue {fromSpawn:0.00} m from the spawn, first alert at "
                      + $"{alertAt:0.00} s ({alerted}, {alertedDistance:0.00} m from the clue, hears it within {alertedRadius:0.00} m)");
            Assert.Greater(r.TopSpeed, 1.2f, "premise: the chair never drove at full speed");
            Assert.GreaterOrEqual(crashAt, 0f, "premise: the vase never fell");
            Assert.Less(crashAt, 3f, $"premise: the vase fell at {crashAt:0.00} s, not at the start");
            Assert.LessOrEqual(fromSpawn, 2.5f, $"premise: the vase fell {fromSpawn:0.00} m from the spawn");
            Assert.IsFalse(seenBeforeCrash, "premise: a human saw the chair before the crash (the crash would not be what costs)");
            Assert.GreaterOrEqual(alertAt, crashAt, "nobody heard the crash: no alert after it");
            Assert.IsNotNull(alerted, "premise: no human was alerted on the alert step");
            Assert.IsTrue(alertedRemembers, $"premise: {alerted}, who heard the crash, has no memory");
            Assert.LessOrEqual(alertedDistance, alertedRadius + 1e-3f, $"premise: {alerted} heard the crash from beyond her radius");
            Assert.AreNotEqual(PlayState.Won, r.State, "the drop at the spawn then full speed won: the fallen vase cost nothing");
            Assert.AreNotEqual(PlayState.Playing, r.State, $"the counter-route neither won nor lost after {r.Time:0.0} s");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }
    }
}
