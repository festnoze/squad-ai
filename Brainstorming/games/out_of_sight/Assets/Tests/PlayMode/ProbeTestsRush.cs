using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Levels v2 (docs/levels_v2/LEVELS_V2.md R2 and 10.1, task C7): the rush counter-route probe, on the real Boot scene
    /// at Normal. For every level listed in levels.json, none of these rushes may win:
    /// <list type="bullet">
    /// <item>(a) the designer route with every wait removed: each waypoint departs on the step the previous one is
    /// reached (RouteReplayer, waitsRemoved), its careful legs and actions kept;</item>
    /// <item>(b) on a level whose player carries a load: a full-speed start that drops the load at the spawn (full input
    /// toward the route's first waypoint away from the spawn, reversed every <see cref="ShakeHalfPeriod"/> s until the
    /// load falls), then (a) from where it stands;</item>
    /// <item>(c) the NavMesh path from the spawn to the exit centre (the level's planner, leaves as they are at the start)
    /// at full input, never careful, never stopping: the body's max speed.</item>
    /// </list>
    /// A rush "loses" when the run ends caught, stuck or timed out: only a win counts. Exemptions live in
    /// <see cref="Exemptions"/>, each with its reason. The probe logs and writes a per-level table (Build/levels_v2/
    /// rush_probe.txt) and lists every surviving rush with its time. Every run asserts its premise (the body moved; the
    /// load fell), so a driver that never drives cannot pass.
    /// The Slow fixture runs every listed level (up to 3 runs each); <see cref="Rush01_Level5AndLevel8RushesLose"/> and the
    /// control <see cref="Rush00_WithNobodyHomeTheRushesWin"/> are the short checks of the probe itself.
    /// </summary>
    public sealed class ProbeTestsRush
    {
        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();

        /// <summary>The variants, in table order.</summary>
        private const char WaitsRemoved = 'a';
        private const char DropThenRush = 'b';
        private const char StraightPath = 'c';
        private static readonly char[] Variants = { WaitsRemoved, DropThenRush, StraightPath };

        /// <summary>
        /// Rushes allowed to win, keyed "level/variant", with the reason (LEVELS_V2 10.1: levels 1 and 2, the "straight
        /// path" variant only). Level 1 is NOT exempt: LEVELS_V2 D11 changed its window dwell so its full-speed rush loses.
        /// </summary>
        private static readonly Dictionary<string, string> Exemptions = new Dictionary<string, string>
        {
            ["level2/c"] = "gentle by design (LEVELS_V2 10.1): the hallway teaches the rug, its lone watcher is not meant to stop a straight dash",
        };

        /// <summary>(b): the full-speed start turns back every this many seconds of game time until the load falls.</summary>
        private const float ShakeHalfPeriod = 0.6f;
        /// <summary>(b): game seconds the drop may take before the run counts as a premise failure (the load never fell).</summary>
        private const float DropBudget = 8f;
        /// <summary>(c): the cap is the path length at this pessimistic speed (m/s) + RouteReplayer.CapAfterRoute.</summary>
        private const float CapSpeed = 0.5f;
        /// <summary>A rush whose top speed stays under this (m/s) never drove: a premise failure, not a loss.</summary>
        private const float MovedSpeed = 0.3f;

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
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = id,
                Language = o.Language, Walls = o.Walls, WallOpacity = o.WallOpacity,
            });
        }

        /// <summary>One rush of one level.</summary>
        private sealed class Run
        {
            public string Level;
            public char Variant;
            /// <summary>Why the variant does not apply to the level (no load, no NavMesh path), or null.</summary>
            public string NotApplicable;
            public RouteReplayer.Result Result;
            /// <summary>What the run did besides the replay (the drop of (b), the path length of (c)).</summary>
            public string Extra = "";
            /// <summary>A premise the run broke (it never drove, the load never fell), or null.</summary>
            public string Premise;
            public string Exemption;
            public int Errors;

            public string Key => Level + "/" + Variant;
            public bool Won => NotApplicable == null && Result != null && Result.Won;

            public string Cell
            {
                get
                {
                    if (NotApplicable != null)
                    {
                        return "n/a";
                    }
                    if (Result == null)
                    {
                        return "lost before the rush (" + Extra + ")";
                    }
                    RouteReplayer.Result r = Result;
                    string how = r.Won
                        ? "WON"
                        : r.TimedOut ? "lost (timed out)"
                        : r.Stalled ? "lost (stalled)"
                        : string.Format(CultureInfo.InvariantCulture, "lost ({0}, {1})", r.State, r.Reason);
                    return string.Format(CultureInfo.InvariantCulture, "{0} at {1:0.0} s, wp {2}/{3}{4}", how, r.Time, r.Waypoint, r.Waypoints,
                        Exemption != null && r.Won ? " [exempt]" : "");
                }
            }

            public override string ToString()
            {
                return string.Format(CultureInfo.InvariantCulture, "{0} ({1}): {2}{3}{4}{5}{6}", Level, Variant,
                    NotApplicable != null ? "n/a, " + NotApplicable : Cell,
                    Extra.Length > 0 ? "; " + Extra : "",
                    Premise != null ? "; PREMISE: " + Premise : "",
                    Errors > 0 ? $"; {Errors} error(s) logged" : "",
                    Result != null ? "; " + Result : "");
            }
        }

        /// <summary>Loads <paramref name="id"/> fresh at Normal under the default (M4) rules.</summary>
        private IEnumerator LoadFresh(string id)
        {
            SetDifficulty(DifficultyDef.Normal);
            Game.LoadLevel(id);
            Game.Rules = GameRules.M4;
            yield return new WaitForFixedUpdate();
            Assert.AreEqual(id, Game.LevelId, "premise: the level was loaded");
            Assert.AreEqual(PlayState.Playing, Game.State, id + ": premise: the level is playing");
            Assert.AreEqual(DifficultyDef.Normal, Game.Difficulty.Id, id + ": premise: the level runs at Normal");
        }

        /// <summary>
        /// Plays variant <paramref name="variant"/> on the level the game has loaded (fresh) and adds its row to
        /// <paramref name="runs"/>. Never asserts: the caller reads the rows.
        /// </summary>
        private IEnumerator RunVariant(char variant, List<Run> runs)
        {
            var run = new Run { Level = Game.LevelId, Variant = variant };
            runs.Add(run);
            Exemptions.TryGetValue(run.Key, out run.Exemption);
            int errorsBefore = errors.Count;
            List<RouteStepDef> route = Game.Def.DesignerRoute;
            if (!Game.Started)
            {
                // Levels v2 (C3a): the probe drives from the first step, as the replayer does.
                Game.ReleaseStart();
            }
            switch (variant)
            {
                case WaitsRemoved:
                {
                    if (route == null || route.Count < 2)
                    {
                        run.NotApplicable = "no designerRoute";
                        run.Premise = "a listed level has no designerRoute (LevelAudit -writeRoutes writes it)";
                        break;
                    }
                    var r = new RouteReplayer.Result();
                    yield return RouteReplayer.Replay(Game, 0f, r, Tuning.PlaythroughTimeScale, null, true);
                    run.Result = r;
                    break;
                }
                case DropThenRush:
                {
                    if (Game.Load == null)
                    {
                        run.NotApplicable = "no load";
                        break;
                    }
                    if (route == null || route.Count < 2)
                    {
                        run.NotApplicable = "no designerRoute";
                        run.Premise = "a listed level has no designerRoute (LevelAudit -writeRoutes writes it)";
                        break;
                    }
                    Vector3 spawn = YawMath.Planar(Game.Furniture.transform.position);
                    Vector3 dir = DropDirection(spawn, route);
                    int crashes0 = Game.CrashCount;
                    float t0 = Game.Elapsed;
                    float dropAt = -1f;
                    float dropDistance = 0f;
                    void Shake()
                    {
                        FurnitureController f = Game.Furniture;
                        if (Game.State != PlayState.Playing || f.Pinned || Game.CrashCount > crashes0)
                        {
                            if (dropAt < 0f && Game.CrashCount > crashes0)
                            {
                                dropAt = Game.Elapsed;
                                dropDistance = YawMath.Planar(f.transform.position - spawn).magnitude;
                            }
                            f.ScriptedDirection = null;
                            return;
                        }
                        f.ScriptedCareful = false;
                        bool forward = Mathf.Repeat(Game.Elapsed - t0, 2f * ShakeHalfPeriod) < ShakeHalfPeriod;
                        f.ScriptedDirection = forward ? dir : -dir;
                    }
                    Game.FixedStepped += Shake;
                    try
                    {
                        yield return RouteReplayer.RunFor(Game, DropBudget, () => Game.CrashCount > crashes0 || Game.State != PlayState.Playing,
                            Tuning.PlaythroughTimeScale);
                    }
                    finally
                    {
                        Game.FixedStepped -= Shake;
                        Game.Furniture.ScriptedDirection = null;
                        Game.Furniture.ScriptedCareful = null;
                    }
                    if (dropAt < 0f && Game.CrashCount > crashes0)
                    {
                        dropAt = Game.Elapsed;
                        dropDistance = YawMath.Planar(Game.Furniture.transform.position - spawn).magnitude;
                    }
                    run.Extra = dropAt >= 0f
                        ? string.Format(CultureInfo.InvariantCulture, "load dropped at {0:0.0} s, {1:0.00} m from the spawn", dropAt, dropDistance)
                        : string.Format(CultureInfo.InvariantCulture, "no drop within {0} s ({1}, {2})", DropBudget, Game.State, Game.LoseReason);
                    if (Game.State != PlayState.Playing)
                    {
                        // Caught (or anything else) during the drop: the rush lost before it started.
                        break;
                    }
                    if (dropAt < 0f)
                    {
                        run.Premise = $"the full-speed start never dropped the load within {DropBudget} s";
                        break;
                    }
                    var r = new RouteReplayer.Result();
                    yield return RouteReplayer.Replay(Game, 0f, r, Tuning.PlaythroughTimeScale, null, true);
                    run.Result = r;
                    break;
                }
                case StraightPath:
                {
                    var planner = Game.Level.Planner as IAreaMaskPlanner;
                    var corners = new List<Vector3>();
                    Vector3 from = YawMath.Planar(Game.Furniture.transform.position);
                    var exit = new Vector3(Game.Def.Exit.X, 0f, Game.Def.Exit.Z);
                    if (planner == null)
                    {
                        run.NotApplicable = "no NavMesh planner";
                        run.Premise = "the level has no NavMesh planner";
                        break;
                    }
                    if (!planner.TryPlan(from, exit, corners, Game.Level.AreaMask()))
                    {
                        run.NotApplicable = "no NavMesh path to the exit with the leaves as authored";
                        break;
                    }
                    float length = 0f;
                    Vector3 last = from;
                    var path = new List<RouteStepDef>();
                    foreach (Vector3 c in corners)
                    {
                        length += YawMath.Planar(c - last).magnitude;
                        last = c;
                        path.Add(new RouteStepDef { X = c.x, Z = c.z, At = 0f, Careful = false });
                    }
                    run.Extra = string.Format(CultureInfo.InvariantCulture, "path {0:0.0} m, {1} corners", length, corners.Count);
                    var r = new RouteReplayer.Result();
                    yield return RouteReplayer.Replay(Game, 0f, r, Tuning.PlaythroughTimeScale, path, true,
                        length / CapSpeed + RouteReplayer.CapAfterRoute);
                    run.Result = r;
                    break;
                }
            }
            if (run.Result != null && run.Premise == null && run.Result.TopSpeed < MovedSpeed && !run.Result.Won)
            {
                run.Premise = string.Format(CultureInfo.InvariantCulture, "the rush never drove (top speed {0:0.00} m/s)", run.Result.TopSpeed);
            }
            run.Errors = errors.Count - errorsBefore;
            Debug.Log("[Rush] " + run);
        }

        /// <summary>(b): toward the first route waypoint at least 0.5 m from the spawn (the way the route leaves), else the exit.</summary>
        private Vector3 DropDirection(Vector3 spawn, List<RouteStepDef> route)
        {
            foreach (RouteStepDef s in route)
            {
                Vector3 to = YawMath.Planar(new Vector3(s.X, 0f, s.Z) - spawn);
                if (to.magnitude >= 0.5f)
                {
                    return to.normalized;
                }
            }
            Vector3 exit = YawMath.Planar(new Vector3(Game.Def.Exit.X, 0f, Game.Def.Exit.Z) - spawn);
            return exit.sqrMagnitude > 1e-6f ? exit.normalized : Vector3.forward;
        }

        /// <summary>Plays every variant of <paramref name="levels"/>, each from a fresh load, into <paramref name="runs"/>.</summary>
        private IEnumerator PlayAll(IEnumerable<string> levels, IEnumerable<char> variants, List<Run> runs)
        {
            foreach (string id in levels)
            {
                foreach (char v in variants)
                {
                    yield return LoadFresh(id);
                    yield return RunVariant(v, runs);
                }
            }
        }

        /// <summary>The per-level table (win/lose per variant), then every surviving rush with its time.</summary>
        private static string Table(List<Run> runs)
        {
            var sb = new StringBuilder();
            sb.AppendLine("Rush counter-route probe (LEVELS_V2 R2, task C7), Normal. a = waits removed, b = load dropped at the spawn then a, "
                          + "c = NavMesh path at max speed.");
            sb.AppendLine("level   | a | b | c");
            foreach (IGrouping<string, Run> level in runs.GroupBy(r => r.Level))
            {
                sb.Append(level.Key.PadRight(7)).Append(" | ");
                sb.AppendLine(string.Join(" | ", Variants.Select(v =>
                {
                    Run run = level.FirstOrDefault(r => r.Variant == v);
                    return run == null ? "-" : run.Cell + (run.Premise != null ? " PREMISE: " + run.Premise : "");
                })));
            }
            List<Run> surviving = runs.Where(r => r.Won).ToList();
            sb.AppendLine(surviving.Count == 0 ? "Surviving rushes: none." : "Surviving rushes:");
            foreach (Run r in surviving)
            {
                sb.AppendLine(string.Format(CultureInfo.InvariantCulture, "  {0} ({1}) won at {2:0.0} s{3}", r.Level, r.Variant, r.Result.Time,
                    r.Exemption != null ? " [exempt: " + r.Exemption + "]" : ""));
            }
            foreach (KeyValuePair<string, string> e in Exemptions.Where(e => runs.Any(r => r.Key == e.Key && !r.Won)))
            {
                sb.AppendLine($"  exemption {e.Key} unused: that rush lost");
            }
            return sb.ToString();
        }

        /// <summary>The failures of <paramref name="runs"/>: non-exempt wins and broken premises.</summary>
        private static List<string> Failures(List<Run> runs)
        {
            var failures = new List<string>();
            foreach (Run r in runs)
            {
                if (r.Won && r.Exemption == null)
                {
                    failures.Add(string.Format(CultureInfo.InvariantCulture, "{0} ({1}): the rush WON at {2:0.0} s ({3})", r.Level, r.Variant,
                        r.Result.Time, r.Extra));
                }
                if (r.Premise != null)
                {
                    failures.Add($"{r.Level} ({r.Variant}): premise: {r.Premise}");
                }
            }
            return failures;
        }

        private static void WriteTable(string table, string file)
        {
            try
            {
                string dir = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Build", "levels_v2"));
                Directory.CreateDirectory(dir);
                File.WriteAllText(Path.Combine(dir, file), table);
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Rush] could not write the table: " + e.Message);
            }
        }

        /// <summary>
        /// The probe over every level listed in levels.json at Normal: no rush (a, b, c) wins, except the documented
        /// exemptions, and every run keeps its premise. The table is logged and written to Build/levels_v2/rush_probe.txt.
        /// </summary>
        [UnityTest]
        [Category("Slow")]
        [Timeout(7200000)]
        public IEnumerator Rush02_NoRushWinsOnAnyListedLevel()
        {
            List<string> levels = Game.LevelOrder.ToList();
            Assert.Greater(levels.Count, 0, "premise: levels.json lists no level");
            var runs = new List<Run>();
            yield return PlayAll(levels, Variants, runs);
            Assert.AreEqual(levels.Count * Variants.Length, runs.Count, "premise: a level was skipped");
            string table = Table(runs);
            Debug.Log("[Rush] table\n" + table);
            WriteTable(table, "rush_probe.txt");
            List<string> failures = Failures(runs);
            Assert.IsEmpty(failures, string.Join("\n", failures) + "\n" + table);
        }

        /// <summary>
        /// The known facts on the v1 data (step 35b, level 5's rush is sat on or caught; step 45e, level 8's rushed route is
        /// caught by the swinging leaf): the probe's rushes lose there too. Not Slow: it checks the probe itself.
        /// </summary>
        [UnityTest]
        [Timeout(1800000)]
        public IEnumerator Rush01_Level5AndLevel8RushesLose()
        {
            var runs = new List<Run>();
            foreach (string id in new[] { "level5", "level8" })
            {
                CollectionAssert.Contains(Game.LevelOrder.ToList(), id, "premise: " + id + " is listed in levels.json");
            }
            yield return PlayAll(new[] { "level5", "level8" }, Variants, runs);
            string table = Table(runs);
            Debug.Log("[Rush01] table\n" + table);
            Assert.IsTrue(runs.Any(r => r.Level == "level5" && r.Variant == WaitsRemoved && r.Result != null), "premise: level5 (a) ran");
            Assert.IsTrue(runs.Any(r => r.Level == "level8" && r.Variant == WaitsRemoved && r.Result != null), "premise: level8 (a) ran");
            List<string> failures = Failures(runs);
            Assert.IsEmpty(failures, string.Join("\n", failures) + "\n" + table);
        }

        /// <summary>
        /// L16EASY (2026-11-23): level17 (card 16, the chair with the vase) was made more forgiving (Hugo removed, wider
        /// windows). The short probe on that level alone: no rush (a, b, c) wins and every run keeps its premise. Not Slow.
        /// </summary>
        [UnityTest]
        [Timeout(1800000)]
        public IEnumerator Rush03_Level17RushesLose()
        {
            var runs = new List<Run>();
            CollectionAssert.Contains(Game.LevelOrder.ToList(), "level17", "premise: level17 is listed in levels.json");
            yield return PlayAll(new[] { "level17" }, Variants, runs);
            string table = Table(runs);
            Debug.Log("[Rush03] table\n" + table);
            Assert.IsTrue(runs.Any(r => r.Level == "level17" && r.Variant == WaitsRemoved && r.Result != null), "premise: level17 (a) ran");
            List<string> failures = Failures(runs);
            Assert.IsEmpty(failures, string.Join("\n", failures) + "\n" + table);
        }

        /// <summary>
        /// ACT3B (2026-11-24): level24 (card 20 since levels.json rev 3, the finale) was rebuilt as a chair level with metronome watchers. The short
        /// probe on that level alone: no rush (a, b, c) wins and every run keeps its premise. Not Slow.
        /// </summary>
        [UnityTest]
        [Timeout(1800000)]
        public IEnumerator Rush04_Level24RushesLose()
        {
            var runs = new List<Run>();
            CollectionAssert.Contains(Game.LevelOrder.ToList(), "level24", "premise: level24 is listed in levels.json");
            yield return PlayAll(new[] { "level24" }, Variants, runs);
            string table = Table(runs);
            Debug.Log("[Rush04] table\n" + table);
            Assert.IsTrue(runs.Any(r => r.Level == "level24" && r.Variant == WaitsRemoved && r.Result != null), "premise: level24 (a) ran");
            List<string> failures = Failures(runs);
            Assert.IsEmpty(failures, string.Join("\n", failures) + "\n" + table);
        }

        /// <summary>
        /// ACT3A (2026-11-24, docs/next/LEVEL_REVIEW.md 3 card 21 and R4): level25 (The Showroom, the act 3 opener since
        /// levels.json rev 3) let rush (a) win at 15.5 s through Nina's front-door window. Nina's door station was retimed so
        /// that window is too short for the waits-removed dash. The short probe on that level alone: no rush (a, b, c) wins
        /// and every run keeps its premise. Not Slow.
        /// </summary>
        [UnityTest]
        [Timeout(1800000)]
        public IEnumerator Rush04_Level25RushesLose()
        {
            var runs = new List<Run>();
            CollectionAssert.Contains(Game.LevelOrder.ToList(), "level25", "premise: level25 is listed in levels.json");
            yield return PlayAll(new[] { "level25" }, Variants, runs);
            string table = Table(runs);
            Debug.Log("[Rush04] table\n" + table);
            Assert.IsTrue(runs.Any(r => r.Level == "level25" && r.Variant == WaitsRemoved && r.Result != null), "premise: level25 (a) ran");
            List<string> failures = Failures(runs);
            Assert.IsEmpty(failures, string.Join("\n", failures) + "\n" + table);
        }

        /// <summary>
        /// Control: with nobody home (the level's inhabitants and robots removed, then rebuilt), the drivers reach the
        /// exit: level 1's (a) and (c) and level 5's (a) (the armchair route, no sitter to wait for) win, and the first load
        /// level of level11, level13, level17 drops its load in (b) and still wins. A "lost" in
        /// the probe is then the household's doing, not a driver that never arrives.
        /// </summary>
        [UnityTest]
        [Timeout(1800000)]
        public IEnumerator Rush00_WithNobodyHomeTheRushesWin()
        {
            var runs = new List<Run>();
            foreach (var (id, v) in new[] { ("level1", WaitsRemoved), ("level1", StraightPath), ("level5", WaitsRemoved) })
            {
                yield return LoadFresh(id);
                yield return EmptyHouse();
                yield return RunVariant(v, runs);
            }
            string loadLevel = null;
            foreach (string id in new[] { "level11", "level13", "level17" })
            {
                yield return LoadFresh(id);
                if (Game.Load != null)
                {
                    loadLevel = id;
                    break;
                }
            }
            Assert.IsNotNull(loadLevel, "premise: none of level11, level13, level17 gives the player a load");
            yield return EmptyHouse();
            Assert.IsNotNull(Game.Load, "premise: the rebuilt load level still has its load");
            yield return RunVariant(DropThenRush, runs);
            string table = Table(runs);
            Debug.Log("[Rush00] table\n" + table);
            foreach (Run r in runs)
            {
                Assert.IsNull(r.NotApplicable, $"{r.Level} ({r.Variant}): premise: the variant applies ({r.NotApplicable})");
                Assert.IsNull(r.Premise, $"{r.Level} ({r.Variant}): premise: {r.Premise}");
                Assert.IsTrue(r.Won, $"{r.Level} ({r.Variant}) with nobody home did not win: {r}");
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>Removes the current level's inhabitants and robots from its definition and rebuilds it.</summary>
        private IEnumerator EmptyHouse()
        {
            string id = Game.LevelId;
            Game.Def.Inhabitants.Clear();
            Game.Def.Robots?.Clear();
            Game.Restart();
            Game.Rules = GameRules.M4;
            yield return new WaitForFixedUpdate();
            Assert.AreEqual(id, Game.LevelId, "premise: the restart kept the level");
            Assert.AreEqual(0, Game.Level.Inhabitants.Count, id + ": premise: nobody home after the rebuild");
            Assert.AreEqual(PlayState.Playing, Game.State, id + ": premise: the empty level is playing");
        }
    }
}
