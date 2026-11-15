using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using Meuble.Core;
using Unity.Collections;
using Unity.Jobs;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Debug = UnityEngine.Debug;

namespace Meuble.Editor
{
    /// <summary>
    /// Level audit (PRD 10.3, docs/CONTRACT_M2.md 6 and 11.7), against the real built level, its real
    /// colliders, its runtime NavMesh and the real routine, in edit mode:
    /// 1. every walk between consecutive stations has a complete NavMesh path;
    /// 2. the level stays within the budgets of PRD 7.4 (draw calls as material slots, materials, triangles per furniture);
    /// 3. a time-expanded search finds a schedule from spawn to exit under the M2 rules (amendment 11.7):
    ///    0.5 m cells, 0.1 s samples, 180 s, the deterministic routine planning with the level NavPlanner.
    ///    The schedule is never seen while moving, never seen still out of place (unless a decoy of the
    ///    player's kind explains the chair), never moves on a hard floor within earshot of an inhabitant,
    ///    keeps the creak gauge below 1, and never spends more than <see cref="Tuning.AuditMaxWait"/> within
    ///    1 m of where a wait began, spawn included (M2.2: a step out and back does not restart the clock).
    ///    Sight and hearing are dilated by a margin in time, so the schedule survives a global shift; the
    ///    audit prints the shift it really survives (its slack). A level with decoys must have a schedule
    ///    explained by a decoy at least once, and none at all with the decoys switched off (M2.2).
    /// 4. start delays (M2.2): wherever in the routine loop the player starts acting, a schedule exists.
    /// 5. the map of the house: what each cell sees, and the schedule.
    /// Then a self-test: the fixtures Resources/Levels/test_wait, test_noise, test_creak, test_tip, test_dark and test_sit
    /// must fail under their strict setting and pass under their relaxed one, each for its own rule.
    ///
    /// M4 (docs/CONTRACT_M4.md 5, amendments 9.1 and 9.11): the search is body aware. The player body gives the move
    /// samples (careful speed for the stool, which then never tips), the capsule, the ring of samples and the noise of
    /// travel (a roll for the office chair). Every office chair stop costs <see cref="Tuning.AuditStopSamples"/> moving
    /// samples (the glide). The lamp is a state bit with two seen tables (lit, dark); a toggle costs 2 moving samples and a
    /// click heard on any floor, and the lamp is never seen at all. A "sit": "player" approach and sitting force the
    /// player onto its seat (the pin pauses the creak gauge and counts against the wait cap), and after a sit on the
    /// player its slot is the seat home. Each level's lesson must be required (<see cref="CheckLesson"/>).
    /// With "-writeRoutes" (or the menu item), the schedule of every passing level is written to its file as
    /// its designerRoute. Only the levels named in Resources/Levels/levels.json are audited.
    ///
    /// M5 performance (docs/CONTRACT_M5.md 16.3). The results of levels 1 to 7 and of the M2/M4 fixtures are unchanged;
    /// only the cost is:
    /// - sight goes through an occlusion cache keyed by the quantized eye position and the door mask, whose value is
    ///   the visibility of every ring point ignoring the cone; misses are cast in batches with RaycastCommand, and the
    ///   cone (range, half angle, yaw) is a cone test only (<see cref="SightCache"/>);
    /// - hearing goes through noise tables, Heard[sample, point] per noise class with the hearing margin applied, so a
    ///   move costs table lookups (<see cref="NoiseTable"/>);
    /// - the search keeps the exact same state order (so the same schedules) on pooled, allocation free layers;
    /// - the start delay sweep and the slack report run only for levels 1 to 7, or behind "-sweep" and "-slack";
    /// - every level prints its seconds, expanded nodes and cast rays, warns above Tuning.AuditLevelWarnSeconds, and
    ///   fails deterministically above Tuning.AuditNodeCap nodes or Tuning.AuditRayCap rays (never on seconds).
    /// Flags (after -executeMethod): "-auditLevels id1,id2", "-fixtures test_a,test_b", "-skipFixtures", "-sweep",
    /// "-slack" (see <see cref="RunOptions"/>).
    ///
    /// M5 wave 5A (CONTRACT_M5 10 and 16, CONTRACT_M5_v3 8 and 15.1 to 15.5, 15.10):
    /// - every routine is built by RoutineFactory (personality, pattern, seats, frozen walks); the loop is the longest
    ///   routine's period, and a wanderer means no sweep;
    /// - sight is per watcher (its eye, range and half angle; a sleeping eye sees nothing): the moving table holds the humans
    ///   and the awake dog (a bark is forbidden), the still tables only the humans, one per tolerance class with its own in
    ///   place and explained radii;
    /// - hearing is per listener (its hearing factor; the dog hears nothing);
    /// - doors: one table per mask of open closed leaves, walkability and moves per mask (the leaves posed by DoorLeaf.PoseAt:
    ///   a closed leaf blocks its doorway, an open leaf only what it occupies), the opening as a 6 sample action in the mask
    ///   after it with the leaf samples at each swing angle, the reach cells of every leaf (robust to the replay's release);
    /// - the split level: cells stand at FloorMap's height and a move needs a continuous floor (a ramp, never an edge);
    /// - every pair of humans stays 0.6 m apart and crosses; the habits of the personalities are warnings;
    /// - the lessons door, pet and split are table edits, with the fixtures test_door, test_pet, test_cross and test_split.
    ///
    /// M5 wave 5A.1 (CONTRACT_M5 17):
    /// - the draw call budget counts material slots, not renderers (16.11; the renderers are still printed), and each vision
    ///   cone counts the material of the colour it shows in play, the dog's own included (<see cref="DrawBudgets"/>);
    /// - the dark lesson's free pass check uses only the watchers with memory, each with its own dark range, and names the
    ///   watcher (<see cref="DarkFreePass"/>);
    /// - one fixture per rule, the audit agent's own test levels: test_m5_audit_darkpass, test_m5_audit_drawcalls and
    ///   test_m5_audit_conecolours.
    ///
    /// M5 wave 5B (CONTRACT_M5 4, 5, 6, 10, 16.5, 16.8, 16.9 and 18; the game's rules as GameState plays them):
    /// - the robot: its timeline is fixed (RobotPath.PositionAt at sample s, the game's k * dt at step 5 s; an audited schedule
    ///   never touches it, so it never reverses). A sample is forbidden within the contact zone (RobotPath.Overlaps widened:
    ///   the robot radius, the footprint's half diagonal, the replay's 0.1 m release and, in the search, the robot's travel
    ///   over the margin), along every move (the whole segment), at every still, stop, toggle and opening, and at the spawn
    ///   during the start delay. The hum (Hearing.IsMaskable) clears a noise table bit only when the robot stands within
    ///   RobotHumRadius minus that travel of the point at every sample of the margin window (<see cref="ApplyHumMasking"/>);
    /// - the rock: a rocking body costs <see cref="World.RockSamples"/> unseen moving samples at every stop (MotionProfile.RockSteps),
    ///   searched at full speed; a run starts (or turns) at the body's cell samples and goes on straight a little faster, and the
    ///   designerRoute chains the waypoints of a run so the replay never rests (and rocks) in the middle of one;
    /// - the load: the search state gains the recent wish history (<see cref="LoadModel"/>, MotionProfile and LoadBalance),
    ///   careful legs are searched beside full speed ones and written "careful", a schedule whose velocity profile drops the load
    ///   is invalid, and the sample box grows by Tuning.LoadHeight. The furniture triangle budget counts the load on its own;
    /// - the lessons robot (the hum binds, or the schedule computed without the robot collides with it), rock (the schedule
    ///   computed without the rock is seen rocking), load (the schedule computed without the load rule drops it) and final (at
    ///   least three of the six mechanic checks bind), with the fixtures test_robot, test_rock, test_load and
    ///   test_m5_levels_robotblock (the contact zone).
    /// </summary>
    public static class LevelAudit
    {
        public const string LevelsFolder = "Assets/Resources/Levels";
        public const string WriteRoutesFlag = "-writeRoutes";

        // PRD 7.4 budgets (the built player probe checks the same numbers).
        private const int BudgetRenderers = Tuning.BudgetRenderers;
        private const int BudgetMaterials = Tuning.BudgetMaterials;
        private const int BudgetFurnitureTriangles = Tuning.BudgetFurnitureTriangles;

        // Schedule search (amendment 11.7). Wanted in Tuning.cs under these names with an Audit prefix.
        // One sample is 5 fixed steps (0.1 s).
        private const int SampleSteps = 5;
        private const float SampleSeconds = SampleSteps * Tuning.FixedStep;
        // 180 s horizon for levels 1 to 7 and the M2/M4 fixtures (World.Horizon; CONTRACT_M5 10: 300 s for the others).
        private const int HorizonSamples = 1800;
        private static readonly int HorizonSamplesM5 = Mathf.RoundToInt(Tuning.AuditHorizonM5 / SampleSeconds);
        // A 0.5 m move takes 0.4 s (1.25 m/s, under the 1.5 m/s top speed and its acceleration).
        private const int MoveSamples = 4;
        // Sight and hearing are dilated by 0.3 s each way: the schedule survives a 0.3 s global shift.
        private const int MarginSamples = 3;
        // Seen still within this distance of the spawn is "in place" (the remembered slot can drift by the
        // 0.1 m release tolerance of a replay, so 0.3 + 0.3 stays under the 0.75 m tolerance).
        private const float InPlaceRadius = 0.3f;
        // Seen still within this distance of a decoy is explained (0.75 m minus the release and a margin).
        private const float ExplainedRadius = 0.6f;
        // Hearing margin added to HopNoiseRadius (amendment 11.7: + 0.25 m).
        private const float NoiseMargin = 0.25f;
        // The creak gauge stays below this (the replay waits a little longer than the plan).
        private const float GaugeCap = 0.85f;
        // The chair seen from any yaw, stopped within 0.1 m of a cell center: its center sample and a ring
        // of 8 top samples of this radius around the cell center. M4: other bodies scale it by the half diagonal
        // of their top samples.
        private const float ChairRingRadius = 0.33f;
        private const int RingCount = 8;
        // M4 (CONTRACT_M4 10.1): a furniture whose cell center is within this of a seat home is on it: the sit check's
        // tolerance (Tuning.SeatHomeTolerance, 0.75 m) minus the 0.1 m release of a replay and a 0.25 m margin.
        private const float ReleaseTolerance = 0.1f;
        private const float SeatPresenceMargin = 0.25f;
        private const float SeatPresenceRadius = Tuning.SeatHomeTolerance - ReleaseTolerance - SeatPresenceMargin;
        // Slack report (CONTRACT_M4 10.7): the largest margin tried, in samples.
        private const int SlackReportMax = 15;
        // M4 actions, in samples: the stool's fall and righting, the lamp's switch.
        private static readonly int FallSamples = Mathf.RoundToInt(Tuning.StoolFallTime / SampleSeconds);
        private static readonly int RightSamples = Mathf.RoundToInt(Tuning.StoolRightTime / SampleSeconds);
        private static readonly int ToggleSamples = Mathf.RoundToInt(Tuning.LampToggleTime / SampleSeconds);
        // A designerRoute waypoint covers at most this many straight cell moves.
        private const int RouteStride = 2;
        // M5 (CONTRACT_M5 16.3): the still radii of a tolerance class are derived from it as M2 derived 0.3 m and 0.6 m from
        // 0.75 m: explained within the tolerance minus the release and this margin, in place within half of that.
        private const float ToleranceMargin = 0.05f;
        // M5 test_cross (CONTRACT_M5_v3 15.10): the separation the fixture's relaxed setting accepts.
        private const float RelaxedSeparation = 0.3f;
        // M5 (CONTRACT_M5_v3 15.3): the opening of a leaf, in samples (Tuning.AuditOpenSamples, 0.6 s).
        private const int OpenSamples = Tuning.AuditOpenSamples;
        // M5 (CONTRACT_M5_v3 15.4, CONTRACT_M5 16.6): a move's floor is sampled this many times for the continuity rule.
        private const int FloorProbeSteps = 10;
        // A wait cap that never binds (a run never exceeds the horizon): "no wait cap".
        private const int UnlimitedRun = int.MaxValue / 4;
        // Largest shift tried when measuring the slack (3 s).
        private const int SlackProbe = 30;
        // The wait rule counts the time spent within this distance of where the wait began (M2.2): a 0.5 m
        // step out and back does not restart the clock; only leaving this radius does.
        private const float WaitAnchorRadius = 1f;
        // Start delay sweep (M2.2): the player starts acting every this many samples (1 s) over one loop. CONTRACT_M5
        // 10: every Tuning.AuditSweepStep (3 s) on the other levels.
        private const int SweepEvery = 10;
        private static readonly int SweepEveryM5 = Mathf.Max(1, Mathf.RoundToInt(Tuning.AuditSweepStep / SampleSeconds));
        // The levels and fixtures audited under the M4 rules (180 s, a 1 s sweep), whose results M5 keeps unchanged.
        private static readonly HashSet<string> LegacyLevels = new HashSet<string>
        {
            "level1", "level2", "level3", "level4", "level5", "level6", "level7",
        };
        private static readonly HashSet<string> LegacyFixtures = new HashSet<string>
        {
            "test_wait", "test_noise", "test_creak", "test_tip", "test_dark", "test_sit",
        };
        // Sight: the occlusion cache quantizes the eye to this (CONTRACT_M5 16.3: 0.01 m, y included).
        private const float EyeQuantum = 0.01f;
        // Sight: at most this many rays per RaycastCommand batch, and samples are processed in chunks of at most this
        // many rays (memory stays bounded whatever the level size).
        private const int RayBatch = 1 << 16;
        // Self-test fixtures that must fail: Resources/Levels/test_*.json, never listed in levels.json, each named
        // after the one rule that must make it fail (see Fixtures). Other test_*.json files (probe levels of other
        // agents) are not audit fixtures.
        public const string FixturePrefix = "test_";
        // M5 wave 5B: a level that expands more nodes than this prints the nodes of each of its searches in its cost line.
        private const long HeavyLevelNodes = 10000000;
        // M5 wave 5B (CONTRACT_M5 16.5): the load rule's window in fixed steps (Tuning.LoadWindow over the fixed step, 25).
        private static readonly int LoadWindowSteps = Mathf.RoundToInt(Tuning.LoadWindow / Tuning.FixedStep);
        // The wish samples the load model keeps: the window (5 samples), a glide (at most 4) and the time to top speed (at most
        // 4), so re-simulating them from rest gives the exact velocities of the last window.
        private const int LoadHistorySamples = 13;
        // LoadBalance's own rounding margin: a change of exactly the threshold falls.
        private const float LoadEpsilon = 1e-4f;

        public sealed class Result
        {
            public string LevelId;
            public readonly List<string> Failures = new List<string>();
            public readonly List<string> Notes = new List<string>();
            public string Map;
            public float Total;
            public float LongestWait;
            public float SlackEarly;
            public float SlackLate;
            public List<RouteStepDef> Route;
            public float WorstDelay = -1f;
            public float WorstDelayTime;
            public float SweepLongestWait;
            /// <summary>CONTRACT_M4 10.7: the largest margin (samples) with a schedule.</summary>
            public int SlackSamples;
            /// <summary>CONTRACT_M5 16.3: the wall clock seconds of this level's audit (printed, warned, never enforced).</summary>
            public float RuntimeSeconds;
            /// <summary>CONTRACT_M5 16.3: the search nodes expanded for this level, every search included (capped).</summary>
            public long Nodes;
            /// <summary>CONTRACT_M5 16.3: the occlusion rays cast for this level (capped).</summary>
            public long Rays;
            public bool Pass => Failures.Count == 0;
        }

        /// <summary>The level ids of levels.json, in play order.</summary>
        public static List<string> ManifestLevels()
        {
            string path = Path.Combine(LevelsFolder, LevelManifest.FileName + ".json");
            return File.Exists(path) ? LevelManifest.Parse(File.ReadAllText(path)) : new List<string>();
        }

        /// <summary>"-auditLevels id1,id2": audits these level files instead of levels.json (fixtures and levels not in
        /// the manifest included). The self-test still runs unless "-skipFixtures" or "-fixtures" says otherwise.</summary>
        public const string LevelsFlag = "-auditLevels";
        /// <summary>"-fixtures test_a,test_b": runs only these self-test fixtures. Without "-auditLevels", no level runs.</summary>
        public const string FixturesFlag = "-fixtures";
        public const string SkipFixturesFlag = "-skipFixtures";
        /// <summary>"-sweep": the start delay sweep on every audited level (by default only on levels 1 to 7).</summary>
        public const string SweepFlag = "-sweep";
        /// <summary>"-slack": the slack report on every audited level (by default only on levels 1 to 7).</summary>
        public const string SlackFlag = "-slack";
        /// <summary>Design aid: "-skipSweep" skips the start delay sweep even on levels 1 to 7 (a warning only).</summary>
        public const string SkipSweepFlag = "-skipSweep";
        /// <summary>Design aid: "-debugSamples 20,40" prints what is seen at these samples.</summary>
        public const string DebugSamplesFlag = "-debugSamples";
        /// <summary>Design aid: "-checkSight" recomputes the sight tables ray by ray (no cache, no batch) and prints the
        /// differences with the cached tables, which must be none.</summary>
        public const string CheckSightFlag = "-checkSight";

        /// <summary>One batch run's command line (CONTRACT_M5 16.3). Ids are comma separated.</summary>
        private sealed class RunOptions
        {
            /// <summary>The levels to audit; null means levels.json.</summary>
            public List<string> Levels;
            /// <summary>The fixtures to run; null means every fixture.</summary>
            public List<string> Fixtures;
            public bool SkipFixtures;
            public bool Sweep;
            public bool Slack;
            public bool SkipSweep;
            public bool CheckSight;
            public bool WriteRoutes;
            public List<int> DebugSamples = new List<int>();

            public static RunOptions Parse(string[] args)
            {
                List<string> Ids(string flag)
                {
                    int at = Array.IndexOf(args, flag);
                    if (at < 0)
                    {
                        return null;
                    }
                    var ids = new List<string>();
                    if (at + 1 < args.Length && !args[at + 1].StartsWith("-", StringComparison.Ordinal))
                    {
                        foreach (string part in args[at + 1].Split(','))
                        {
                            if (part.Trim().Length > 0)
                            {
                                ids.Add(part.Trim());
                            }
                        }
                    }
                    return ids;
                }
                bool Has(string flag) => Array.IndexOf(args, flag) >= 0;
                var o = new RunOptions
                {
                    Levels = Ids(LevelsFlag),
                    Fixtures = Ids(FixturesFlag),
                    SkipFixtures = Has(SkipFixturesFlag),
                    Sweep = Has(SweepFlag),
                    Slack = Has(SlackFlag),
                    SkipSweep = Has(SkipSweepFlag),
                    CheckSight = Has(CheckSightFlag),
                    WriteRoutes = Has(WriteRoutesFlag),
                };
                foreach (string part in Ids(DebugSamplesFlag) ?? new List<string>())
                {
                    o.DebugSamples.Add(int.Parse(part, CultureInfo.InvariantCulture));
                }
                // Naming fixtures without levels runs only those fixtures.
                if (o.Levels == null && o.Fixtures != null)
                {
                    o.Levels = new List<string>();
                }
                return o;
            }
        }

        /// <summary>The options of the run in progress (the menu items use the defaults).</summary>
        private static RunOptions run = new RunOptions();

        /// <summary>Batch entry point: audits every level of levels.json, exits 0 when all pass.</summary>
        public static void RunBatch()
        {
            run = RunOptions.Parse(Environment.GetCommandLineArgs());
            int code = RunAll(run);
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static int RunAll(bool writeRoutes)
        {
            run = new RunOptions { WriteRoutes = writeRoutes };
            return RunAll(run);
        }

        private static int RunAll(RunOptions options)
        {
            int code = 0;
            try
            {
                List<string> ids = options.Levels ?? ManifestLevels();
                if (ids.Count == 0 && options.Levels == null)
                {
                    Debug.LogError($"[LevelAudit] no level listed in {LevelsFolder}/{LevelManifest.FileName}.json");
                    code = 1;
                }
                foreach (string id in ids)
                {
                    string file = Path.Combine(LevelsFolder, id + ".json");
                    if (!File.Exists(file))
                    {
                        Debug.LogError($"[LevelAudit] Niveau {id} : fichier {file} absent");
                        code = 1;
                        continue;
                    }
                    Result r = Run(LevelJson.Parse(File.ReadAllText(file)));
                    if (options.WriteRoutes && r.Pass && r.Route != null)
                    {
                        WriteRoute(file, r.Route);
                        r.Notes.Add($"designerRoute ecrite dans {file} ({r.Route.Count} points)");
                    }
                    Debug.Log(Format(r));
                    if (!r.Pass)
                    {
                        code = 1;
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[LevelAudit] audit threw: " + e);
                code = 1;
            }
            try
            {
                if (!options.SkipFixtures && !RunFixtures(options.Fixtures))
                {
                    code = 1;
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[LevelAudit] self-test threw: " + e);
                code = 1;
            }
            return code;
        }

        [MenuItem("Meuble/Audit Levels")]
        public static void RunFromMenu()
        {
            if (EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
            {
                RunAll(false);
            }
        }

        [MenuItem("Meuble/Audit Levels and Write Designer Routes")]
        public static void RunAndWriteFromMenu()
        {
            if (EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
            {
                RunAll(true);
                AssetDatabase.Refresh();
            }
        }

        public static string Format(Result r)
        {
            var sb = new StringBuilder();
            sb.AppendLine($"[LevelAudit] Niveau {r.LevelId} : {(r.Pass ? "aucun defaut" : r.Failures.Count + " defaut(s)")}");
            foreach (string f in r.Failures)
            {
                sb.AppendLine("  [DEFAUT] " + f);
            }
            foreach (string n in r.Notes)
            {
                sb.AppendLine("  [info] " + n);
            }
            if (!string.IsNullOrEmpty(r.Map))
            {
                sb.AppendLine(r.Map);
            }
            return sb.ToString();
        }

        public static Result Run(LevelDef def)
        {
            var result = new Result { LevelId = def.Id };
            var clock = Stopwatch.StartNew();
            Budget.Begin();
            try
            {
                foreach (string issue in LevelValidator.Validate(def))
                {
                    result.Failures.Add("validator: " + issue);
                }
                if (result.Failures.Count > 0)
                {
                    return result;
                }

                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                LevelInstance level = LevelBuilder.Build(def);
                try
                {
                    Physics.SyncTransforms();
                    CheckWalks(def, level, result);
                    CheckBudgets(def, level, result);
                    CheckSchedule(def, level, result);
                }
                finally
                {
                    LevelBuilder.Teardown(level);
                }
                return result;
            }
            finally
            {
                Budget.End(result, clock);
            }
        }

        /// <summary>
        /// CONTRACT_M5 16.3: the deterministic budget of one level or fixture, the nodes expanded by every search and the
        /// rays cast for its sight, each with its cap. A capped search finds no schedule, and the level fails for the cap
        /// (never for its seconds, which are only printed and warned). The level's occlusion cache lives here too.
        /// </summary>
        private static class Budget
        {
            public static long Nodes;
            public static long Rays;
            public static bool NodesExhausted;
            public static bool RaysExhausted;
            /// <summary>M5 wave 5B: one search created more than Tuning.AuditSearchNodeCap nodes (the memory guard).</summary>
            public static bool SearchTooLarge;
            public static SightCache Sight;
            /// <summary>The most nodes one search of this level created (memory follows it).</summary>
            public static long Created;
            /// <summary>M5 wave 5B: the nodes each search of this level expanded, in order (the cost line prints them on a heavy level).</summary>
            public static readonly List<long> PerSearch = new List<long>();
            /// <summary>M5 wave 5B: the most load states one load model of this level interned (0 without a load).</summary>
            public static int LoadStates;

            public static void Begin()
            {
                Nodes = 0;
                Rays = 0;
                NodesExhausted = false;
                RaysExhausted = false;
                SearchTooLarge = false;
                Sight = null;
                Created = 0;
                LoadStates = 0;
                PerSearch.Clear();
            }

            /// <summary>Counts one expanded node; false (and exhausted for the rest of the level) past the cap.</summary>
            public static bool Expand()
            {
                if (NodesExhausted || ++Nodes > Tuning.AuditNodeCap)
                {
                    NodesExhausted = true;
                    return false;
                }
                return true;
            }

            /// <summary>Reserves rays before a batch is cast; false (and exhausted) when the batch would pass the cap.</summary>
            public static bool Cast(int rays)
            {
                if (RaysExhausted || Rays + rays > Tuning.AuditRayCap)
                {
                    RaysExhausted = true;
                    return false;
                }
                Rays += rays;
                return true;
            }

            /// <summary>The defects of an exhausted budget, or null.</summary>
            public static string Defect()
            {
                if (RaysExhausted)
                {
                    return string.Format(CultureInfo.InvariantCulture,
                        "budget de l'audit epuise : plus de {0} rayons (Tuning.AuditRayCap) : la vue du niveau n'est pas calculee", Tuning.AuditRayCap);
                }
                if (SearchTooLarge)
                {
                    return string.Format(CultureInfo.InvariantCulture,
                        "budget de l'audit epuise : une recherche cree plus de {0} noeuds (Tuning.AuditSearchNodeCap, la memoire) : aucun horaire n'est garanti", Tuning.AuditSearchNodeCap);
                }
                if (NodesExhausted)
                {
                    return string.Format(CultureInfo.InvariantCulture,
                        "budget de l'audit epuise : plus de {0} noeuds developpes (Tuning.AuditNodeCap) : aucun horaire n'est garanti", Tuning.AuditNodeCap);
                }
                return null;
            }

            /// <summary>Records the level's cost in the result: the runtime note, its warning, and the budget defect.</summary>
            public static void End(Result result, Stopwatch clock)
            {
                result.RuntimeSeconds = (float)clock.Elapsed.TotalSeconds;
                result.Nodes = Nodes;
                result.Rays = Rays;
                string defect = Defect();
                if (defect != null)
                {
                    result.Failures.Add(defect);
                }
                result.Notes.Add(RuntimeLine(result));
                if (result.RuntimeSeconds > Tuning.AuditLevelWarnSeconds)
                {
                    result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                        "AVERTISSEMENT temps : {0:0.0} s, au dessus de {1:0} s (Tuning.AuditLevelWarnSeconds ; jamais un defaut)",
                        result.RuntimeSeconds, Tuning.AuditLevelWarnSeconds));
                }
                Sight = null;
            }

            public static string RuntimeLine(Result result)
            {
                return string.Format(CultureInfo.InvariantCulture,
                    "temps : {0:0.0} s, {1} noeuds developpes (plafond {2}, au plus {3} crees par recherche), {4} rayons (plafond {5})",
                    result.RuntimeSeconds, result.Nodes, Tuning.AuditNodeCap, Created, result.Rays, Tuning.AuditRayCap)
                    + (LoadStates > 0 ? $", {LoadStates} etats de charge" : "")
                    + (result.Nodes > HeavyLevelNodes ? ", par recherche : " + string.Join(" ", PerSearch.ConvertAll(x => x.ToString(CultureInfo.InvariantCulture))) : "");
            }
        }

        // ----- 1. Walks -----

        private static void CheckWalks(LevelDef def, LevelInstance level, Result result)
        {
            if (!(level.Planner is NavPlanner nav) || !nav.HasData)
            {
                result.Failures.Add("pas de NavMesh : le planificateur du niveau n'est pas un NavPlanner construit");
                return;
            }
            result.Notes.Add($"NavMesh : {NavPlanner.CountTriangles()} triangles, {nav.SourceCount} sources");
            var corners = new List<Vector3>();
            // CONTRACT_M5 16.7: every ordered pair of stations the pattern can produce (n for a loop, 2 (n - 1) for pingpong,
            // n (n - 1) for wander), planned with every leaf closed: no station walk may need a leaf (they are frozen).
            int closed = AllLeavesClosedMask(def);
            bool leaves = closed != RoutineFactory.AllAreas;
            foreach (InhabitantDef inhabitant in def.Inhabitants)
            {
                foreach (Vector2Int pair in RoutinePatterns.ReachablePairs(inhabitant.Pattern, inhabitant.Stations.Count))
                {
                    Vector3 a = inhabitant.Stations[pair.x].Position;
                    Vector3 b = inhabitant.Stations[pair.y].Position;
                    string label = $"{inhabitant.Name} marche {pair.x + 1} -> {pair.y + 1}";
                    if (!(leaves ? nav.TryPlan(a, b, corners, closed) : level.Planner.TryPlan(a, b, corners)))
                    {
                        result.Failures.Add($"{label} ({a.x}, {a.z}) -> ({b.x}, {b.z}) : aucun chemin NavMesh complet"
                            + (leaves ? " avec toutes les portes a battant fermees" : ""));
                    }
                    else if (corners.Count > 1)
                    {
                        result.Notes.Add($"{label} contourne un obstacle : {corners.Count - 1} coin(s)");
                    }
                }
            }
        }

        // ----- 2. Budgets (PRD 7.4) -----

        private static void CheckBudgets(LevelDef def, LevelInstance level, Result result)
        {
            result.Failures.AddRange(DrawBudgets(def, level, true, true, result.Notes));
            for (int i = 0; i < level.Inhabitants.Count; i++)
            {
                Inhabitant inhabitant = level.Inhabitants[i];
                long t = Probe.TrianglesUnder(inhabitant.transform);
                int bones = Probe.BonesUnder(inhabitant.transform);
                // CONTRACT_M5_v3 15.5: a pet (its rig's catalog entry has the kind "pet", the way Probe counts bones) may have
                // Tuning.BudgetPetBones bones; humans keep the M3 limit. A procedural body has no rig and no bone.
                bool pet = inhabitant.Rig != null && inhabitant.Rig.IsPet;
                int boneBudget = pet ? Tuning.BudgetPetBones : Tuning.BudgetInhabitantBones;
                if (t > Tuning.BudgetInhabitantTriangles)
                {
                    result.Failures.Add($"habitant {inhabitant.name} : {t} triangles, au dessus du budget de {Tuning.BudgetInhabitantTriangles}");
                }
                if (bones > boneBudget)
                {
                    result.Failures.Add($"habitant {inhabitant.name} : {bones} os, au dessus du budget de {boneBudget}");
                }
            }
            var furniture = new HashSet<string>();
            foreach (PropDef prop in def.Props)
            {
                furniture.Add(prop.Name);
            }
            foreach (Transform child in level.Root.transform)
            {
                bool isFurniture = furniture.Contains(child.name) || child.GetComponent<Decoy>() != null
                    || (level.Furniture != null && child == level.Furniture.transform);
                if (!isFurniture)
                {
                    continue;
                }
                long triangles = Probe.TrianglesUnder(child);
                // M5 wave 5B (CONTRACT_M5 6): the load is a separate object on top of the player furniture, counted on its own.
                LoadView load = level.LoadView;
                if (load != null && level.Furniture != null && child == level.Furniture.transform && load.transform.IsChildOf(child))
                {
                    long carried = Probe.TrianglesUnder(load.transform);
                    triangles -= carried;
                    result.Notes.Add($"charge {load.Kind} : {carried} triangles, comptee a part du meuble {child.name} ({triangles} triangles), budget de {BudgetFurnitureTriangles} chacun");
                    if (carried > BudgetFurnitureTriangles)
                    {
                        result.Failures.Add($"charge {load.Kind} : {carried} triangles, au dessus du budget de {BudgetFurnitureTriangles}");
                    }
                }
                if (triangles > BudgetFurnitureTriangles)
                {
                    result.Failures.Add($"meuble {child.name} : {triangles} triangles, au dessus du budget de {BudgetFurnitureTriangles}");
                }
            }
        }

        /// <summary>
        /// The draw call and material budgets of a built level (PRD 7.4 v1.7, CONTRACT_M5 9, 16.11 and 17), one line in
        /// <paramref name="notes"/> and the failures returned.
        /// <list type="bullet">
        /// <item>Draw calls: with <paramref name="slots"/> (the rule) every material slot of an active renderer is a draw call
        /// (M3 counts every slot, CONTRACT_M5 16.11), compared with <see cref="Tuning.BudgetRenderers"/> or, for a house of
        /// <see cref="Tuning.HouseBudgetRooms"/> rooms or more, <see cref="Tuning.BudgetHouseRenderers"/>. The renderers are
        /// still printed. Without it (the relaxed setting of the test_m5_audit_drawcalls fixture) the renderers are compared,
        /// as before wave 5A.1.</item>
        /// <item>Materials: see <see cref="CountDraws"/>, compared with <see cref="Tuning.BudgetMaterials"/> or
        /// <see cref="Tuning.BudgetHouseMaterials"/>, or with <paramref name="materialBudget"/> when it is positive (the
        /// test_m5_audit_conecolours fixture).</item>
        /// </list>
        /// </summary>
        private static List<string> DrawBudgets(LevelDef def, LevelInstance level, bool slots, bool coneColours, List<string> notes,
            int materialBudget = 0)
        {
            var failures = new List<string>();
            DrawCount count = CountDraws(level, coneColours);
            int drawCalls = slots ? count.Slots : count.Renderers; // MUTATION:AUDIT_DRAW_CALLS
            // CONTRACT_M5 9: a house of Tuning.HouseBudgetRooms rooms or more has the house budgets.
            bool house = def.AllRooms().Count >= Tuning.HouseBudgetRooms;
            int budgetDrawCalls = house ? Tuning.BudgetHouseRenderers : BudgetRenderers;
            int budgetMaterials = materialBudget > 0 ? materialBudget : house ? Tuning.BudgetHouseMaterials : BudgetMaterials;
            notes?.Add($"budgets : {count.Slots} emplacements (draw calls, max {budgetDrawCalls}), {count.Renderers} renderers, "
                + $"{count.Materials} materiaux (max {budgetMaterials}, un par couleur de cone), {count.Triangles} triangles, {level.ModelVisuals.Count} modeles");
            if (drawCalls > budgetDrawCalls)
            {
                failures.Add(slots
                    ? $"{drawCalls} emplacements de materiau (draw calls), au dessus du budget de {budgetDrawCalls}"
                    : $"{drawCalls} renderers, au dessus du budget de {budgetDrawCalls}");
            }
            if (count.Materials > budgetMaterials)
            {
                failures.Add($"{count.Materials} materiaux, au dessus du budget de {budgetMaterials}");
            }
            return failures;
        }

        /// <summary>What the budgets of a built level count (<see cref="CountDraws"/>).</summary>
        private sealed class DrawCount
        {
            public int Renderers;
            /// <summary>The material slots of the active renderers: the draw calls (CONTRACT_M5 16.11).</summary>
            public int Slots;
            public int Materials;
            public long Triangles;
        }

        /// <summary>
        /// The active renderers of a built level, their material slots and triangles (M3, docs/CONTRACT_M3.md 9: every slot
        /// counts, skinned meshes count their triangles), and its distinct materials. A vision cone is built with the calm
        /// material and takes its colour only in play (VisionConeView.LateUpdate), so with <paramref name="coneColours"/> (the
        /// rule, CONTRACT_M5 17) each active cone counts the material of the colour it shows at rest instead: the humans' calm
        /// fan, and the dog's own colour when a dog exists. A dark lamp swaps every fan's colour at once, so it adds none.
        /// Without it every cone counts the calm material it is built with, as before wave 5A.1.
        /// </summary>
        private static DrawCount CountDraws(LevelInstance level, bool coneColours)
        {
            Renderer[] all = level.Root.GetComponentsInChildren<Renderer>(false);
            Probe.RenderCount count = Probe.CountRenderers(all);
            // The materials of every renderer but the active cones, then one per cone colour shown in play.
            var others = new List<Renderer>();
            var cones = new List<VisionConeView>();
            foreach (Renderer r in all)
            {
                VisionConeView cone = r.GetComponent<VisionConeView>();
                if (cone != null && r.enabled && r.gameObject.activeInHierarchy)
                {
                    cones.Add(cone);
                }
                else
                {
                    others.Add(r);
                }
            }
            HashSet<Material> materials = Probe.CountRenderers(others).Materials;
            foreach (VisionConeView cone in cones)
            {
                bool dog = coneColours && cone.Owner != null && cone.Owner.IsDog; // MUTATION:AUDIT_CONE_COLOURS
                materials.Add(PrimitiveKit.UnlitTransparent(VisionConeView.ConeColor(dog, false, false)));
            }
            return new DrawCount { Renderers = count.Renderers, Slots = count.MaterialSlots, Materials = materials.Count, Triangles = count.Triangles };
        }

        // ----- 3. The schedule (amendment 11.7, CONTRACT_M4 5 and amendment 9.11) -----

        /// <summary>
        /// The player body as the search sees it (CONTRACT_M4 5: move samples and ring radius per body). Everything
        /// comes from <see cref="BodyDef"/>; the chair gives exactly the M2 numbers (4 samples a cell, ring 0.33 m).
        /// </summary>
        private sealed class BodyModel
        {
            public BodyDef Body;
            public float Radius;
            public float Height;
            /// <summary>Samples to cross a cell at the replay's speed: careful speed for a body that tips.</summary>
            public int MoveSamples;
            /// <summary>The stool without careful mode (the "careful" lesson and the tip fixture).</summary>
            public int FullSpeedMoveSamples;
            public float RingRadius;
            /// <summary>The noise of travel: a hop, or a roll for the office chair (both silent on a rug).</summary>
            public float MoveNoiseRadius;
            public NoiseKind MoveNoiseKind;
            public bool Glides;
            public bool Tips;
            public bool Lamp;
            /// <summary>M5 wave 5B: the body rocks at every stop (the rocking chair, CONTRACT_M5 5 and 16.9).</summary>
            public bool Rocks;
            /// <summary>M5 wave 5B: samples a careful leg takes over a cell (the load's careful legs, CONTRACT_M5 16.5).</summary>
            public int CarefulMoveSamples;
            /// <summary>
            /// M5 wave 5B: samples a rocking body takes over a cell when it goes on straight in motion (its top speed, rounded
            /// down): a run starts or turns at <see cref="MoveSamples"/>, then the plan keeps a little ahead of the furniture, so
            /// the replay never arrives early at a waypoint of a run (an early arrival is a rest, and a rest is a rock).
            /// </summary>
            public int ContinueSamples;
            /// <summary>M5 wave 5B (CONTRACT_M5 16.5): the sample box grows by the carried load's height (0 without a load).</summary>
            public float LoadHeight;
            /// <summary>
            /// M5 wave 5B (CONTRACT_M5 16.5): a full speed start from rest drops a load (the office chair's 2.8 m/s): with a load
            /// such a body is searched on careful legs only (a full leg could only follow a careful one and never stop again).
            /// </summary>
            public bool FullStartDropsLoad;

            /// <summary>The height of the sample box: the body's, plus the load it carries.</summary>
            public float SampleHeight => Height + LoadHeight;

            public static BodyModel Of(BodyDef body)
            {
                float speed = body.MaxSpeed * (body.Tips ? Tuning.CarefulFactor : 1f);
                return new BodyModel
                {
                    Body = body,
                    Rocks = body.Rocks,
                    FullStartDropsLoad = LoadBalance.FirstFall(MotionProfile.Synthesize(body, false,
                        new List<Vector2>(new Vector2[2 * LoadWindowSteps]).ConvertAll(_ => Vector2.up))) >= 0,
                    CarefulMoveSamples = CellSamples(body, body.MaxSpeed * Tuning.CarefulFactor),
                    ContinueSamples = Mathf.Max(1, Mathf.FloorToInt(Tuning.AuditCellSize / body.MaxSpeed / SampleSeconds + 1e-3f)),
                    Radius = body.Radius,
                    Height = body.Size.y,
                    MoveSamples = CellSamples(body, speed),
                    FullSpeedMoveSamples = CellSamples(body, body.MaxSpeed),
                    RingRadius = ChairRingRadius * TopHalfDiagonal(body.Size) / TopHalfDiagonal(BodyDef.For(BodyKinds.Chair).Size),
                    MoveNoiseRadius = Hearing.RadiusOf(body.Glides ? NoiseKind.Roll : NoiseKind.Hop),
                    MoveNoiseKind = body.Glides ? NoiseKind.Roll : NoiseKind.Hop,
                    Glides = body.Glides,
                    Tips = body.Tips,
                    Lamp = body.HasLight,
                };
            }
        }

        /// <summary>
        /// Samples a cell takes at <paramref name="maxSpeed"/>: a <see cref="RouteStride"/> cell leg from rest, driven
        /// as FurnitureController drives it (acceleration, the stool's two stages, velocity then move), shared by its
        /// cells and rounded up. The chair gives 4 (0.37 s a cell), the M2 value.
        /// </summary>
        private static int CellSamples(BodyDef body, float maxSpeed)
        {
            float dt = Tuning.FixedStep;
            float leg = RouteStride * Tuning.AuditCellSize;
            float v = 0f;
            float x = 0f;
            int steps = 0;
            while (x < leg && steps < 100000)
            {
                float next = Mathf.Min(v + body.Accel * dt, maxSpeed);
                float cap = Mathf.Max(v + body.AccelHigh * dt, body.StageSpeed);
                v = Mathf.Min(next, cap);
                x += v * dt;
                steps++;
            }
            float perCell = steps * dt / RouteStride;
            return Mathf.Max(1, Mathf.CeilToInt(perCell / SampleSeconds - 1e-3f));
        }

        /// <summary>Half diagonal of the top sample square of a body (PRD 4.1 samples, inset included).</summary>
        private static float TopHalfDiagonal(Vector3 size)
        {
            return new Vector2(size.x * 0.5f - Tuning.SampleInset, size.z * 0.5f - Tuning.SampleInset).magnitude;
        }

        /// <summary>One inhabitant as the audit's sight and hearing read it (its <see cref="PersonalityDef"/>, CONTRACT_M5 3).</summary>
        private sealed class Watcher
        {
            public string Name;
            public PersonalityDef Personality;
            /// <summary>
            /// A human: it counts for the catch and the exit and remembers (a still chair seen out of place is a discovery).
            /// The dog is not: its sighting of the moving chair is a bark (forbidden), its sighting of a still chair is free
            /// (CONTRACT_M5_v3 8).
            /// </summary>
            public bool Human;
            /// <summary>The view range before any lamp factor, and the cone's half angle.</summary>
            public float Range;
            public float HalfAngle;
            /// <summary>Scales every noise radius it hears; 0 hears nothing (the dog).</summary>
            public float HearingFactor;
            /// <summary>The index of its tolerance class in <see cref="World.Classes"/> (-1 for the dog).</summary>
            public int Class = -1;
        }

        /// <summary>
        /// The still rules of one displacement tolerance (CONTRACT_M5 16.3: at most 3 per level). A still chair seen by a
        /// human of this tolerance must be in place (within <see cref="InPlaceRadius"/> of its slot) or explained (within
        /// <see cref="ExplainedRadius"/> of a decoy of its kind). Both radii are derived from the tolerance as M2 derived
        /// 0.3 m and 0.6 m from 0.75 m.
        /// </summary>
        private sealed class ToleranceClass
        {
            public float Tolerance;
            public float InPlaceRadius;
            public float ExplainedRadius;
            /// <summary>[cell]: within the explained radius of a decoy of the player's kind.</summary>
            public bool[] Explained;
            /// <summary>[slot][cell]: in place for that slot (the spawn, then the seat homes the player was sat on at).</summary>
            public readonly List<bool[]> InPlaceBySlot = new List<bool[]>();
            /// <summary>[mask][sample * Count + cell]: seen still by a human of this class, as sampled and dilated.</summary>
            public bool[][] Seen, SeenWide, SeenDark, SeenDarkWide;

            public bool SeenAt(bool dark, int mask, int index, bool wide)
            {
                return (dark ? (wide ? SeenDarkWide : SeenDark) : (wide ? SeenWide : Seen))[mask][index];
            }
        }

        /// <summary>A door leaf as the audit reads it (CONTRACT_M5_v3 3, 15.2, 15.3).</summary>
        private sealed class Leaf
        {
            public OpeningDef Door;
            public DoorGeometry Geometry;
            /// <summary>Authored closed: the player may open it; its bit in a mask says it is open.</summary>
            public bool Closed;
            /// <summary>The bit of a closed leaf in the masks (0 for an authored open leaf, always open).</summary>
            public int Bit;
            /// <summary>Its NavMesh area (Tuning.DoorAreaBase plus its index among the leaves).</summary>
            public int Area;
            /// <summary>The cells from which the player can open it (<see cref="ReachableFrom"/>).</summary>
            public readonly List<int> Reach = new List<int>();
            /// <summary>A box around every pose of the leaf: a ray that misses it sees the same thing whatever the mask.</summary>
            public Bounds Swing;
            /// <summary>[q - 1]: the leaf's sample points at the swing angle of opening sample q.</summary>
            public Vector3[][] Samples;
        }

        /// <summary>Everything the search reads, precomputed over the whole horizon.</summary>
        private sealed class World
        {
            public LevelDef Def;
            public BodyModel Body;
            public List<RoomDef> Rooms;
            public int Count;
            /// <summary>[cell]: the cell center on the floor (M5: at the floor height of FloorMap, CONTRACT_M5_v3 15.4).</summary>
            public Vector3[] Center;
            public int[] Room;
            public int[] I;
            public int[] J;
            public (int nx, int nz)[] Size;
            public Dictionary<(int, int, int), int> Index;
            public bool[] Walkable;
            /// <summary>[cell]: explained for at least one tolerance class (the map's "c").</summary>
            public bool[] ExplainedAny;
            public bool[] InExit;
            public List<int>[] Neighbors;
            /// <summary>The first directed edge of each cell: edge EdgeStart[k] + j goes from k to Neighbors[k][j].</summary>
            public int[] EdgeStart;
            public int Edges;
            public int Samples;
            /// <summary>The search horizon in samples: 180 s for levels 1 to 7 and the M2/M4 fixtures, else 300 s.</summary>
            public int Horizon = HorizonSamples;
            /// <summary>The start delay sweep's step in samples (1 s for levels 1 to 7, Tuning.AuditSweepStep otherwise).</summary>
            public int SweepEvery = LevelAudit.SweepEvery;
            public int Inhabitants;
            /// <summary>[inhabitant]: personality, role and tolerance class.</summary>
            public Watcher[] Watchers;
            /// <summary>The tolerance classes of the humans, in first-seen order (one for levels 1 to 7).</summary>
            public readonly List<ToleranceClass> Classes = new List<ToleranceClass>();
            /// <summary>
            /// [mask][sample * Count + cell]: seen moving, by a human or the awake dog (CONTRACT_M5_v3 8), as sampled, the light
            /// on (every body but a dark lamp). On levels 1 to 7 (one class, no dog) the still table of the class is this one.
            /// </summary>
            public bool[][] MoveSeen;
            public bool[][] MoveSeenWide;
            /// <summary>M4 lamp: the same with the lamp switched off (the range is LampOffLight times each watcher's range).</summary>
            public bool[][] MoveDark;
            public bool[][] MoveDarkWide;
            /// <summary>[sample, inhabitant]: planar position.</summary>
            public Vector3[,] Position;
            /// <summary>[sample * Inhabitants + inhabitant]: the vision eye and its forward, as stepped (sight and its checks).</summary>
            public Vector3[] Eye;
            public Vector3[] Forward;
            /// <summary>[sample * Inhabitants + inhabitant]: the eye is closed (a sleeping dog sees nothing).</summary>
            public bool[] Asleep;
            /// <summary>[cell]: the sample points of a body stopped at the cell (center, then the ring), as the sight sees it.</summary>
            public Vector3[][] Rings;
            public int Start;
            public bool NeedDecoy;
            /// <summary>Samples of the longest routine's first loop (the horizon when it never loops; 0 with a wanderer: no sweep).</summary>
            public int LoopSamples;
            /// <summary>The level has a wandering routine: it never loops, so there is no start delay sweep (CONTRACT_M5 16.3).</summary>
            public bool Wanders;
            /// <summary>CONTRACT_M5 16.3: the noise tables built so far, per noise class and points (travel, 0 for the cells).</summary>
            public readonly Dictionary<(NoiseKind kind, int travel, bool hum), NoiseTable> Noise = new Dictionary<(NoiseKind, int, bool), NoiseTable>();
            /// <summary>[inhabitant]: the hearing factor that scales every noise radius it hears (0: it hears nothing).</summary>
            public float[] HearingFactor;

            // ----- M5 wave 5B: the robot, the rock and the load (CONTRACT_M5 4 to 6, 16.5, 16.8, 16.9) -----
            /// <summary>The robots of the level (at most one, the validator says).</summary>
            public int Robots;
            public readonly List<RobotPath> RobotPaths = new List<RobotPath>();
            /// <summary>[sample * Robots + robot]: the robot's planar position on its fixed timeline (no reversal ever).</summary>
            public Vector3[] RobotAt;
            /// <summary>The fastest robot's speed, m/s: its travel over the margin widens the contact zone and narrows the hum.</summary>
            public float RobotSpeed;
            /// <summary>The contact zone before that travel: RobotRadius, the footprint's half diagonal and the replay's release.</summary>
            public float ContactBase;
            /// <summary>The spawn, planar: the furniture stands there until the start delay ends.</summary>
            public Vector3 Spawn;
            /// <summary>The samples a stop costs a rocking body (MotionProfile.RockSteps in samples, 8), else 0.</summary>
            public int RockSamples;
            /// <summary>The player carries a load (CONTRACT_M5 6, 16.5): the load rule and the grown sample box apply.</summary>
            public bool HasLoad;

            /// <summary>The load models built so far, per leg lengths, careful base and stop cost (their states are shared by searches).</summary>
            public readonly Dictionary<(int, bool, int, int), LoadModel> LoadModels = new Dictionary<(int, bool, int, int), LoadModel>();

            /// <summary>The robot's travel over the current margin, metres.</summary>
            public float RobotTravel => RobotSpeed * Margin * SampleSeconds;

            // ----- M5 doors (CONTRACT_M5_v3 3, 15.1 to 15.3) -----
            /// <summary>Every leaf of the level, open or closed, in level order.</summary>
            public readonly List<Leaf> Leaves = new List<Leaf>();
            /// <summary>The closed leaves, bit i of a mask for the i-th one (at most Tuning.MaxLeavesPerLevel).</summary>
            public readonly List<Leaf> Closed = new List<Leaf>();
            /// <summary>The number of masks: 2 to the number of closed leaves; mask 0 is the level as authored.</summary>
            public int Masks = 1;
            /// <summary>[edge]: the closed leaf whose doorway this edge crosses, or -1.</summary>
            public int[] EdgeLeaf;
            /// <summary>
            /// [mask][cell]: the body standing there would overlap a leaf in that mask's poses (an open leaf against the end of
            /// its opening, CONTRACT_M5_v3 15.3); null on a level without leaves.
            /// </summary>
            public bool[][] Blocked;
            /// <summary>[mask][edge]: the body's sweep along this move meets a leaf in that mask's poses; null without leaves.</summary>
            public bool[][] EdgeBlocked;
            /// <summary>
            /// [closed leaf][q - 1][sample * Masks + mask]: a sample of the leaf at opening sample q is seen by a moving watcher
            /// in the mask after the opening (CONTRACT_M5_v3 15.3), as sampled and dilated.
            /// </summary>
            public bool[][][] LeafSeen, LeafSeenWide;
            /// <summary>[sample * Inhabitants + inhabitant]: the inhabitant sits (granny's habit, CONTRACT_M5 16.7).</summary>
            public bool[] Sits;
            /// <summary>[cell]: the bits of the closed leaves the player can open from that cell (null without closed leaves).</summary>
            public int[] ReachBits;

            /// <summary>A shallow copy for a lesson variant: it shares every table it does not replace.</summary>
            public World Clone()
            {
                return (World)MemberwiseClone();
            }

            /// <summary>A leaf sample of opening sample q (1 based) seen at s, the mask being the one after the opening.</summary>
            public bool LeafSeenAt(int leaf, int q, int s, int mask, bool wide)
            {
                return (wide ? LeafSeenWide : LeafSeen)[leaf][q - 1][s * Masks + mask];
            }

            // ----- M4 sitting (CONTRACT_M4 3, 5, amendment 9.11) -----
            /// <summary>The routines sit (false: every sit station is a plain dwell, the "sit" fixture's relaxed world).</summary>
            public bool Sitting;
            /// <summary>Samples by which sight, hearing and the sitter's pin are dilated each way (3: 0.3 s).</summary>
            public int Margin = MarginSamples;
            /// <summary>CONTRACT_M4 10.1: the first sample at which an inhabitant sits on the player, or -1.</summary>
            public int FirstSit = -1;
            /// <summary>
            /// [sample]: an inhabitant sits on the player (CONTRACT_M4 10.1: from the moment of sitting, when the game checks
            /// the seat, to the end of the pin). The player must be on the seat: a pratfall is a discovery.
            /// </summary>
            public bool[] Forced;
            public bool[] ForcedWide;
            /// <summary>[sample]: index in <see cref="SeatCells"/> of the seat that sample forces, or -1.</summary>
            public int[] ForcedSeat;
            public int[] ForcedSeatWide;
            public readonly List<Vector3> SeatHomes = new List<Vector3>();
            public readonly List<HashSet<int>> SeatCells = new List<HashSet<int>>();
            /// <summary>The same cells as a per cell flag, for the search.</summary>
            public readonly List<bool[]> SeatCellFlags = new List<bool[]>();
            /// <summary>[sample]: the player is sat on (pinned): the creak gauge pauses.</summary>
            public bool[] Pinned;
            /// <summary>[sample]: index of the player's slot (0, the spawn, until a sit on the player) in each class's InPlaceBySlot.</summary>
            public int[] Slot;
            /// <summary>The pose of each slot: the spawn, then every seat home the player was sat on at.</summary>
            public readonly List<Vector3> SlotHomes = new List<Vector3>();

            /// <summary>In place for the tolerance class at sample s.</summary>
            public bool InPlaceAt(ToleranceClass c, int k, int s)
            {
                return c.InPlaceBySlot[Slot[Mathf.Clamp(s, 0, Samples - 1)]][k];
            }

            /// <summary>Seen moving at (s, k) in that mask: a human or the awake dog sees it.</summary>
            public bool MovingSeen(bool dark, int mask, int s, int k, bool wide)
            {
                return (dark ? (wide ? MoveDarkWide : MoveDark) : (wide ? MoveSeenWide : MoveSeen))[mask][s * Count + k];
            }

            /// <summary>Seen at (s, k) in that mask by a human (the exit counts only unseen by them).</summary>
            public bool HumanSeen(bool dark, int mask, int s, int k, bool wide)
            {
                int index = s * Count + k;
                for (int c = 0; c < Classes.Count; c++)
                {
                    if (Classes[c].SeenAt(dark, mask, index, wide))
                    {
                        return true;
                    }
                }
                return false;
            }

            /// <summary>
            /// M2.2: the still chair at (s, k), lit and as sampled, is seen by a human class for which it is out of place but
            /// explained by a decoy (the "explained once" flag and its count).
            /// </summary>
            public bool ExplainedAt(int mask, int k, int s)
            {
                int index = s * Count + k;
                foreach (ToleranceClass c in Classes)
                {
                    if (c.Seen[mask][index] && c.Explained[k] && !InPlaceAt(c, k, s))
                    {
                        return true;
                    }
                }
                return false;
            }

            public bool ForcedAt(int s, bool wide)
            {
                return wide ? ForcedWide[s] : Forced[s];
            }

            public bool InSeatCell(int k, int s, bool wide)
            {
                int seat = wide ? ForcedSeatWide[s] : ForcedSeat[s];
                return seat >= 0 && SeatCellFlags[seat][k];
            }

            /// <summary>The cell is free in that mask (the body there overlaps no leaf as the mask poses them).</summary>
            public bool FreeIn(int mask, int k)
            {
                return Blocked == null || !Blocked[mask][k];
            }

            /// <summary>
            /// The directed edge is passable in that mask: its doorway's leaf is open, the sweep meets no leaf and both ends
            /// are free.
            /// </summary>
            public bool EdgeOpen(int mask, int edge, int k, int o)
            {
                int leaf = EdgeLeaf == null ? -1 : EdgeLeaf[edge];
                return (leaf < 0 || (mask & Closed[leaf].Bit) != 0) && (EdgeBlocked == null || !EdgeBlocked[mask][edge])
                    && FreeIn(mask, k) && FreeIn(mask, o);
            }
        }

        /// <summary>
        /// CONTRACT_M5 16.3: the occlusion cache of one level. The key is the eye quantized to <see cref="EyeQuantum"/> (y
        /// included) and the door mask; the value is which sample points are visible from that eye, ignoring the cone, so
        /// range, half angle and yaw cost a cone test only and a dwelling, turning or glancing eye costs no ray at all. A value
        /// is filled lazily: a point is cast the first time a cone needs it, from the exact eye that created the entry, and the
        /// missing points are cast in batches with RaycastCommand. A ray of a mask other than 0 that misses every leaf's swing
        /// box is the same in every mask: it is read from (and cast for) the mask 0 entry of the same eye. The points are the
        /// cell rings, then the samples of the closed leaves (a leaf never hides its own samples).
        /// </summary>
        private sealed class SightCache
        {
            /// <summary>[cell * Ring + a], then the leaf samples: every point the sight ever looks at.</summary>
            public readonly Vector3[] Points;
            public readonly int Ring;
            /// <summary>Poses the leaves for a mask with one closed leaf's collider off (-1: none), before a batch is cast.</summary>
            public Action<int, int> Pose;
            private readonly int ringPoints;
            private readonly int[] owner;
            private readonly List<Bounds> swings;
            private readonly int words;
            private readonly Dictionary<(int, int, int, int), int> index = new Dictionary<(int, int, int, int), int>();
            private readonly List<Vector3> eyes = new List<Vector3>();
            private readonly List<int> masks = new List<int>();
            private readonly List<int> bases = new List<int>();
            private readonly List<ulong[]> known = new List<ulong[]>();
            private readonly List<ulong[]> visible = new List<ulong[]>();
            private readonly List<ulong[]> shared = new List<ulong[]>();
            private readonly List<int> pendingEntry = new List<int>();
            private readonly List<int> pendingPoint = new List<int>();

            public SightCache(Vector3[][] cellRings, List<Vector3> extra, List<int> extraOwner, List<Bounds> swingBoxes)
            {
                Ring = cellRings.Length > 0 ? cellRings[0].Length : 1;
                ringPoints = cellRings.Length * Ring;
                Points = new Vector3[ringPoints + extra.Count];
                for (int k = 0; k < cellRings.Length; k++)
                {
                    for (int a = 0; a < Ring; a++)
                    {
                        Points[k * Ring + a] = cellRings[k][a];
                    }
                }
                for (int i = 0; i < extra.Count; i++)
                {
                    Points[ringPoints + i] = extra[i];
                }
                owner = extraOwner.ToArray();
                swings = swingBoxes;
                words = (Points.Length + 63) >> 6;
            }

            public int Entries => eyes.Count;
            public int Pending => pendingEntry.Count;

            /// <summary>True when this cache was built for these sample points (the same body on the same grid, the same leaves).</summary>
            public bool Matches(Vector3[][] cellRings, List<Vector3> extra)
            {
                if (cellRings.Length * Ring + extra.Count != Points.Length || (cellRings.Length > 0 && cellRings[0].Length != Ring))
                {
                    return false;
                }
                for (int k = 0; k < cellRings.Length; k++)
                {
                    for (int a = 0; a < Ring; a++)
                    {
                        if (cellRings[k][a] != Points[k * Ring + a])
                        {
                            return false;
                        }
                    }
                }
                for (int i = 0; i < extra.Count; i++)
                {
                    if (extra[i] != Points[ringPoints + i])
                    {
                        return false;
                    }
                }
                return true;
            }

            /// <summary>The entry of an eye and a door mask, created (empty) the first time.</summary>
            public int Entry(Vector3 eye, int mask)
            {
                var key = (Mathf.RoundToInt(eye.x / EyeQuantum), Mathf.RoundToInt(eye.y / EyeQuantum), Mathf.RoundToInt(eye.z / EyeQuantum), mask);
                if (index.TryGetValue(key, out int e))
                {
                    return e;
                }
                int baseEntry = mask == 0 ? -1 : Entry(eye, 0);
                e = eyes.Count;
                index[key] = e;
                eyes.Add(mask == 0 ? eye : eyes[baseEntry]);
                masks.Add(mask);
                bases.Add(mask == 0 ? e : baseEntry);
                known.Add(new ulong[words]);
                visible.Add(new ulong[words]);
                shared.Add(mask == 0 ? null : new ulong[words]);
                return e;
            }

            public bool Visible(int e, int point)
            {
                ulong bit = 1UL << (point & 63);
                ulong[] s = shared[e];
                if (s != null && (s[point >> 6] & bit) != 0)
                {
                    return Visible(bases[e], point);
                }
                return (visible[e][point >> 6] & bit) != 0;
            }

            /// <summary>True when a point of the cell is already known visible from the entry and inside this cone.</summary>
            public bool AnyKnownVisible(int e, int first, int count, Vector3 eye, Vector3 forward, float range, float halfAngle)
            {
                ulong[] k = known[e];
                for (int p = first; p < first + count; p++)
                {
                    if ((k[p >> 6] & (1UL << (p & 63))) != 0 && Visible(e, p) && VisionMath.IsInCone(eye, forward, Points[p], range, halfAngle))
                    {
                        return true;
                    }
                }
                return false;
            }

            /// <summary>Queues the point for a ray unless the entry knows it already (or it sits on the eye: always visible).</summary>
            public void Need(int e, int point)
            {
                ulong bit = 1UL << (point & 63);
                if ((known[e][point >> 6] & bit) != 0)
                {
                    return;
                }
                known[e][point >> 6] |= bit;
                if (masks[e] != 0 && !CrossesSwing(eyes[e], Points[point]))
                {
                    shared[e][point >> 6] |= bit;
                    Need(bases[e], point);
                    return;
                }
                if ((Points[point] - eyes[e]).magnitude < 1e-4f)
                {
                    visible[e][point >> 6] |= bit; // Vision.Occluded: a point on the eye is never occluded
                    return;
                }
                pendingEntry.Add(e);
                pendingPoint.Add(point);
            }

            /// <summary>The segment from the eye to the point may meet a leaf in some pose.</summary>
            private bool CrossesSwing(Vector3 eye, Vector3 point)
            {
                Vector3 d = point - eye;
                float distance = d.magnitude;
                foreach (Bounds box in swings)
                {
                    if (box.Contains(eye) || box.Contains(point)
                        || (distance > 1e-6f && box.IntersectRay(new Ray(eye, d / distance), out float at) && at <= distance))
                    {
                        return true;
                    }
                }
                return false;
            }

            /// <summary>
            /// Casts every queued point, as Vision.Occluded casts it (from the entry's eye toward the point, up to the point,
            /// against the occluders, triggers ignored), in RaycastCommand batches, one group per (mask, leaf left out) with
            /// the leaves posed for it. False when the ray budget is spent.
            /// </summary>
            public bool Flush()
            {
                int count = pendingEntry.Count;
                if (count == 0)
                {
                    return true;
                }
                if (!Budget.Cast(count))
                {
                    pendingEntry.Clear();
                    pendingPoint.Clear();
                    return false;
                }
                // Group by (mask, leaf left out), keeping the queue order inside a group.
                var groups = new SortedDictionary<long, List<int>>();
                for (int i = 0; i < count; i++)
                {
                    int point = pendingPoint[i];
                    int exclude = point >= ringPoints ? owner[point - ringPoints] : -1;
                    long group = (long)masks[pendingEntry[i]] * 64 + exclude + 1;
                    if (!groups.TryGetValue(group, out List<int> members))
                    {
                        groups[group] = members = new List<int>();
                    }
                    members.Add(i);
                }
                var query = new QueryParameters(Layers.OccluderMask, false, QueryTriggerInteraction.Ignore, Physics.queriesHitBackfaces);
                int batch = Mathf.Min(count, RayBatch);
                var commands = new NativeArray<RaycastCommand>(batch, Allocator.Persistent);
                var hits = new NativeArray<RaycastHit>(batch, Allocator.Persistent);
                bool posed = false;
                try
                {
                    foreach (KeyValuePair<long, List<int>> group in groups)
                    {
                        int mask = (int)(group.Key / 64);
                        int exclude = (int)(group.Key % 64) - 1;
                        if (Pose != null && (posed || mask != 0 || exclude >= 0))
                        {
                            Pose(mask, exclude);
                            posed = true;
                        }
                        List<int> members = group.Value;
                        for (int from = 0; from < members.Count; from += batch)
                        {
                            int size = Mathf.Min(batch, members.Count - from);
                            for (int i = 0; i < size; i++)
                            {
                                int at = members[from + i];
                                Vector3 eye = eyes[pendingEntry[at]];
                                Vector3 d = Points[pendingPoint[at]] - eye;
                                float distance = d.magnitude;
                                commands[i] = new RaycastCommand(eye, d / distance, query, distance);
                            }
                            NativeArray<RaycastCommand> slice = size == batch ? commands : commands.GetSubArray(0, size);
                            NativeArray<RaycastHit> results = size == batch ? hits : hits.GetSubArray(0, size);
                            RaycastCommand.ScheduleBatch(slice, results, 64, 1, default(JobHandle)).Complete();
                            for (int i = 0; i < size; i++)
                            {
                                if (results[i].colliderInstanceID == 0)
                                {
                                    int at = members[from + i];
                                    int point = pendingPoint[at];
                                    visible[pendingEntry[at]][point >> 6] |= 1UL << (point & 63);
                                }
                            }
                        }
                    }
                }
                finally
                {
                    commands.Dispose();
                    hits.Dispose();
                    if (posed)
                    {
                        Pose(0, -1); // the level as built
                    }
                }
                pendingEntry.Clear();
                pendingPoint.Clear();
                return true;
            }
        }

        /// <summary>
        /// CONTRACT_M5 16.3: Heard[sample, point] for one noise class over a fixed set of points: the cell centers (a glide, a
        /// topple, a click) or the travel points of every directed edge (a move: the point q / travel of the way, as
        /// <see cref="CheckMove"/> places it). The narrow table sets a bit when a listener stands within the class radius
        /// (times its hearing factor) plus the hearing margin at that sample and the point is not on a silent floor; the wide
        /// table ORs the narrow rows over the world's margin. It is exactly <see cref="Heard"/>, read in a table.
        /// </summary>
        private sealed class NoiseTable
        {
            public NoiseKind Kind;
            /// <summary>Samples per cell move for the edge tables; 0 for the cell centers.</summary>
            public int Travel;
            public int Points;
            public int Words;
            public ulong[] Narrow;
            public ulong[] Wide;
            private int wideMargin = -1;
            /// <summary>M5 wave 5B: the narrow rows before the hum masked them (null when the hum masks nothing here).</summary>
            public ulong[] Raw;
            /// <summary>The position of every point (kept only for the hum masking).</summary>
            public Vector3[] Position;
            private int humMargin = -1;

            public bool HeardWide(int s, int point)
            {
                return (Wide[s * Words + (point >> 6)] & (1UL << (point & 63))) != 0;
            }

            public static NoiseTable Build(World w, NoiseKind kind, int travel, bool hum)
            {
                int n = w.Count;
                var t = new NoiseTable { Kind = kind, Travel = travel };
                t.Points = travel == 0 ? n : w.Edges * travel;
                t.Words = (t.Points + 63) >> 6;
                var position = new Vector3[t.Points];
                var silent = new bool[t.Points];
                // How far a cell's points stand from its center, for the conservative listener filter below.
                var extent = new float[n];
                for (int k = 0; k < n; k++)
                {
                    if (travel == 0)
                    {
                        position[k] = w.Center[k];
                        continue;
                    }
                    List<int> next = w.Neighbors[k];
                    for (int j = 0; j < next.Count; j++)
                    {
                        int o = next[j];
                        extent[k] = Mathf.Max(extent[k], (w.Center[o] - w.Center[k]).magnitude);
                        for (int q = 1; q <= travel; q++)
                        {
                            position[(w.EdgeStart[k] + j) * travel + q - 1] = Vector3.Lerp(w.Center[k], w.Center[o], q / (float)travel);
                        }
                    }
                }
                for (int p = 0; p < t.Points; p++)
                {
                    silent[p] = w.Def.IsSilentFloor(position[p]);
                }
                float radius = Hearing.RadiusOf(kind);
                t.Narrow = new ulong[w.Samples * t.Words];
                for (int r = 0; r < w.Samples; r++)
                {
                    int row = r * t.Words;
                    for (int i = 0; i < w.Inhabitants; i++)
                    {
                        float factor = w.HearingFactor[i];
                        if (factor <= 0f)
                        {
                            continue;
                        }
                        float reach = radius * factor + NoiseMargin;
                        Vector3 listener = w.Position[r, i];
                        for (int k = 0; k < n; k++)
                        {
                            if (YawMath.Planar(listener - w.Center[k]).magnitude > reach + extent[k] + 1e-3f)
                            {
                                continue;
                            }
                            int first = travel == 0 ? k : w.EdgeStart[k] * travel;
                            int last = travel == 0 ? k + 1 : w.EdgeStart[k + 1] * travel;
                            for (int p = first; p < last; p++)
                            {
                                if (!silent[p] && YawMath.Planar(listener - position[p]).magnitude <= reach)
                                {
                                    t.Narrow[row + (p >> 6)] |= 1UL << (p & 63);
                                }
                            }
                        }
                    }
                }
                if (hum)
                {
                    t.Position = position;
                    t.Raw = (ulong[])t.Narrow.Clone();
                    t.humMargin = w.Margin;
                    ApplyHumMasking(w, t);
                }
                t.Widen(w);
                return t;
            }

            /// <summary>The wide rows for the world's current margin (rebuilt when the margin changes).</summary>
            public void Widen(World w)
            {
                if (Raw != null && humMargin != w.Margin)
                {
                    // The hum's window is the margin: a new margin masks again from the unmasked rows.
                    Narrow = (ulong[])Raw.Clone();
                    humMargin = w.Margin;
                    ApplyHumMasking(w, this);
                    Wide = null;
                }
                if (wideMargin == w.Margin && Wide != null)
                {
                    return;
                }
                wideMargin = w.Margin;
                Wide = new ulong[Narrow.Length];
                for (int s = 0; s < w.Samples; s++)
                {
                    int lo = Mathf.Max(0, s - w.Margin);
                    int hi = Mathf.Min(w.Samples - 1, s + w.Margin);
                    int row = s * Words;
                    for (int q = lo; q <= hi; q++)
                    {
                        int src = q * Words;
                        for (int x = 0; x < Words; x++)
                        {
                            Wide[row + x] |= Narrow[src + x];
                        }
                    }
                }
            }
        }

        /// <summary>
        /// The robot's hum (CONTRACT_M5 4 and 16.8): a hop, a roll or a click (Hearing.IsMaskable) made near a robot is not
        /// emitted, which clears bits of the narrow table. The audit masks a point at a sample only when the robot stands within
        /// Tuning.RobotHumRadius minus its travel over the margin of it at every sample of the margin window
        /// (<see cref="HumMasked"/>), so the schedule keeps the hum when it is shifted. Without a robot it changes nothing.
        /// </summary>
        private static void ApplyHumMasking(World w, NoiseTable table)
        {
            if (table.Position == null || w.Robots == 0 || !Hearing.IsMaskable(table.Kind))
            {
                return;
            }
            for (int s = 0; s < w.Samples; s++)
            {
                int row = s * table.Words;
                for (int x = 0; x < table.Words; x++)
                {
                    ulong bits = table.Narrow[row + x];
                    for (int b = 0; bits != 0UL && b < 64; b++)
                    {
                        ulong bit = 1UL << b;
                        if ((bits & bit) == 0UL)
                        {
                            continue;
                        }
                        bits &= ~bit;
                        int p = (x << 6) + b;
                        if (p < table.Points && HumMasked(w, table.Kind, table.Position[p], s))
                        {
                            table.Narrow[row + x] &= ~bit;
                        }
                    }
                }
            }
        }

        /// <summary>
        /// CONTRACT_M5 16.8: a noise of <paramref name="kind"/> at <paramref name="p"/> on sample s is masked by the hum in the
        /// audit: maskable (Hearing.IsMaskable), and at every sample of the margin window around s some robot stands within
        /// Tuning.RobotHumRadius minus its travel over the margin of it (planar).
        /// </summary>
        private static bool HumMasked(World w, NoiseKind kind, Vector3 p, int s)
        {
            if (w.Robots == 0 || !Hearing.IsMaskable(kind))
            {
                return false;
            }
            float reach = Tuning.RobotHumRadius - w.RobotTravel; // MUTATION:AUDIT_HUM
            int lo = Mathf.Max(0, s - w.Margin);
            int hi = Mathf.Min(w.Samples - 1, s + w.Margin);
            for (int q = lo; q <= hi; q++)
            {
                bool near = false;
                for (int r = 0; r < w.Robots && !near; r++)
                {
                    near = YawMath.Planar(p - w.RobotAt[q * w.Robots + r]).magnitude <= reach;
                }
                if (!near)
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>The robot's hum applies to this search: the level has a robot and neither the robot nor its hum is off.</summary>
        private static bool HumOn(World w, SearchOptions o)
        {
            return w.Robots > 0 && o.Robots && o.Hum;
        }

        /// <summary>The noise table of a class over the cell centers (travel 0) or the travel points of the moves.</summary>
        private static NoiseTable NoiseFor(World w, NoiseKind kind, int travel, bool hum = false)
        {
            // A table the hum cannot touch is the same with it or without it.
            hum &= w.Robots > 0 && Hearing.IsMaskable(kind);
            if (!w.Noise.TryGetValue((kind, travel, hum), out NoiseTable table))
            {
                table = NoiseTable.Build(w, kind, travel, hum);
                w.Noise[(kind, travel, hum)] = table;
            }
            table.Widen(w);
            return table;
        }

        /// <summary>The kind of transition that led to a node.</summary>
        private enum Act : byte
        {
            Start,
            Still,
            Move,
            /// <summary>The end of a run: the office chair's glide, or the stool's fall at full speed.</summary>
            Stop,
            /// <summary>The lamp switches itself off or on (E).</summary>
            Toggle,
            /// <summary>M5: the player opens a closed leaf (E, CONTRACT_M5_v3 15.3).</summary>
            Open,
        }

        /// <summary>
        /// One search node, 24 bytes (a search may create tens of millions): the cell, the anchor, the time, the moves, the
        /// run and the load state are stored as ushort behind int properties (<see cref="BuildWorld"/> checks that the grid and
        /// the horizon fit), the flags as bits of one byte.
        /// </summary>
        private struct Node
        {
            public int Parent;
            public float Gauge;
            private ushort cell;
            private ushort t;
            private ushort moves;
            private ushort run;
            private ushort anchor;
            private ushort load;
            public Act Act;
            /// <summary>M5: the open closed leaves, one bit each (CONTRACT_M5_v3 15.3).</summary>
            public byte Mask;
            private byte bits;

            public int Cell { get => cell; set => cell = (ushort)value; }
            public int T { get => t; set => t = (ushort)value; }
            public int Moves { get => moves; set => moves = (ushort)value; }
            /// <summary>Samples spent within <see cref="WaitAnchorRadius"/> of <see cref="Anchor"/> since it was set.</summary>
            public int Run { get => run; set => run = (ushort)value; }
            public int Anchor { get => anchor; set => anchor = (ushort)value; }
            /// <summary>
            /// M5 wave 5B: with a load, the <see cref="LoadModel"/> state (the recent wish history, 0 at rest); for a rocking body
            /// in motion, 1 plus the direction it arrived in (0 otherwise). Always 0 on the other levels.
            /// </summary>
            public int Load { get => load; set => load = (ushort)value; }
            /// <summary>The schedule was explained by a decoy at least once.</summary>
            public bool Flag { get => (bits & 1) != 0; set => SetBit(1, value); }
            /// <summary>M4: the lamp is switched off.</summary>
            public bool Off { get => (bits & 2) != 0; set => SetBit(2, value); }
            /// <summary>M4: arrived by a move and not stopped yet (only for a body whose stop costs samples).</summary>
            public bool Motion { get => (bits & 4) != 0; set => SetBit(4, value); }
            /// <summary>M4: the stool lies on its side (full speed search only).</summary>
            public bool Lying { get => (bits & 8) != 0; set => SetBit(8, value); }
            /// <summary>M5 wave 5B: arrived by a careful leg (the careful key held: the stool's, or a load's careful leg).</summary>
            public bool Careful { get => (bits & 16) != 0; set => SetBit(16, value); }
            public bool Move => Act == Act.Move;

            private void SetBit(int bit, bool value)
            {
                bits = value ? (byte)(bits | bit) : (byte)(bits & ~bit);
            }
        }

        private static void CheckSchedule(LevelDef def, LevelInstance level, Result result)
        {
            World w = BuildWorld(def, level, true);
            if (Budget.RaysExhausted)
            {
                return; // the budget defect says why (Budget.End)
            }
            if (run.CheckSight)
            {
                result.Notes.Add(CheckSight(w, level));
            }
            if (Array.IndexOf(w.Forced, true) >= 0)
            {
                foreach (HashSet<int> cells in w.SeatCells)
                {
                    if (cells.Count == 0)
                    {
                        result.Failures.Add("aucune case libre a moins de " + SeatPresenceRadius.ToString("0.0#", CultureInfo.InvariantCulture)
                            + " m d'une place assise du joueur : le meuble ne peut pas y etre");
                    }
                }
            }
            result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                "corps {0} : {1} echantillons par case ({2:0.00} m/s){3}, anneau {4:0.00} m, bruit de deplacement {5:0.0} m{6}{7}",
                w.Body.Body.Kind, w.Body.MoveSamples, Tuning.AuditCellSize / (w.Body.MoveSamples * SampleSeconds),
                w.Body.Tips ? $" en mode prudent ({w.Body.FullSpeedMoveSamples} a pleine vitesse)" : "",
                w.Body.RingRadius, w.Body.MoveNoiseRadius,
                w.Body.Glides ? $", arret glisse {Tuning.AuditStopSamples} echantillons" : "",
                w.Body.Lamp ? ", lampe : jamais vue, deux tables de vue" : ""));
            DescribeMechanics(w, result);
            if (Array.IndexOf(w.Forced, true) >= 0)
            {
                result.Notes.Add("assis sur le joueur (presence au siege, de l'instant de l'assise a la fin de l'epingle) : " + Intervals(w.Forced, w.Horizon));
            }
            DescribeWatchers(w, result);
            CheckLeaves(w, result);
            result.Failures.AddRange(CheckSeparation(w, Separation, result.Notes));
            ToleranceWarnings(w, result);
            HabitWarnings(w, result);
            var strict = new SearchOptions { NeedDecoy = w.NeedDecoy };
            NodeList nodes = Search(w, strict, out int goal);
            if (goal < 0)
            {
                result.Failures.Add($"aucun horaire du depart a la sortie en {w.Horizon * SampleSeconds:0} s{(w.NeedDecoy ? " qui se serve d'un leurre" : "")} : " +
                                    "jamais vu en mouvement, jamais vu deplace sans leurre, jamais entendu, grincement sous 1, " +
                                    $"jamais plus de {Tuning.AuditMaxWait:0} s a moins de {WaitAnchorRadius:0} m du meme endroit");
            }
            if (goal < 0)
            {
                Diagnose(def, level, w, result);
            }
            List<Node> path = goal >= 0 ? PathTo(nodes, goal) : new List<Node>();
            if (path.Count > 0)
            {
                Describe(w, strict, path, result);
                DescribeMechanicsOnPath(w, path, result);
                result.Route = Route(w, path);
                if (w.Closed.Count > 0)
                {
                    // CONTRACT_M5 8: the "open" steps the designerRoute gets (-writeRoutes).
                    var opens = new List<string>();
                    foreach (RouteStepDef step in result.Route)
                    {
                        if (step.Action == RouteStepDef.ActionOpen)
                        {
                            opens.Add(string.Format(CultureInfo.InvariantCulture, "{0} en ({1:0.##}, {2:0.##}) a {3:0.0} s", step.Door, step.X, step.Z, step.At));
                        }
                    }
                    result.Notes.Add($"route : {result.Route.Count} points, ouvertures : {(opens.Count > 0 ? string.Join(" ; ", opens) : "aucune")}");
                }
                if (!SameRoute(def.DesignerRoute, result.Route))
                {
                    result.Notes.Add($"la designerRoute du fichier differe de cet horaire (elle reste valable si la sonde 20 la gagne) ; {WriteRoutesFlag} la remplace");
                }
            }
            if (w.NeedDecoy)
            {
                // M2.2 (d): with the decoys switched off (they still stand there, they explain nothing), the
                // level must have no schedule at all. Otherwise "the decoys are required" is only a claim.
                Search(w, new SearchOptions { Decoys = false }, out int without);
                if (without >= 0)
                {
                    result.Failures.Add("sans l'explication des leurres, un horaire existe encore : les leurres ne sont pas necessaires");
                }
                else
                {
                    result.Notes.Add("leurres eteints : aucun horaire, les leurres sont necessaires");
                }
            }
            CheckLesson(def, level, w, path, result);
            foreach (int sample in run.DebugSamples)
            {
                result.Notes.Add(SeenMap(w, sample));
            }
            // CONTRACT_M5 16.3: the sweep and the slack report are design data. They run on levels 1 to 7 as in M4, and on
            // any other level only behind -sweep and -slack.
            bool legacy = LegacyLevels.Contains(def.Id);
            if ((legacy && !run.SkipSweep) || run.Sweep)
            {
                Sweep(w, result);
            }
            if (path.Count > 0 && (legacy || run.Slack))
            {
                SlackReport(w, result);
            }
            result.Map = Map(w, path);
        }

        /// <summary>
        /// Amendment 9.11: the level's lesson is required. dark: no schedule with the lamp always on. careful: no
        /// schedule at full stool speed (every stop from a run tips it). glide: the schedule that ignores the glide is
        /// seen gliding (the stop samples bind). sit: moving the seat home 2 m away changes the schedule.
        /// </summary>
        private static void CheckLesson(LevelDef def, LevelInstance level, World w, List<Node> path, Result result)
        {
            switch (def.Lesson)
            {
                case null:
                    return;
                case LevelDef.LessonCareful:
                    NodeList fullNodes = Search(w, new SearchOptions { FullSpeed = true }, out int fullSpeed);
                    if (fullSpeed >= 0)
                    {
                        result.Failures.Add("lecon careful : un horaire existe aussi a pleine vitesse, sans le mode prudent : la lecon n'est pas requise ("
                            + Summary(w, PathTo(fullNodes, fullSpeed)) + ")");
                    }
                    else
                    {
                        result.Notes.Add("lecon careful : a pleine vitesse (chaque arret renverse le tabouret), aucun horaire : le mode prudent est requis");
                    }
                    return;
                case LevelDef.LessonDark:
                {
                    NodeList litNodes = Search(w, new SearchOptions { Toggles = false }, out int lit);
                    if (lit >= 0)
                    {
                        result.Failures.Add("lecon dark : un horaire existe aussi la lampe toujours allumee : la lecon n'est pas requise ("
                            + Summary(w, PathTo(litNodes, lit)) + ")");
                    }
                    else
                    {
                        result.Notes.Add("lecon dark : lampe toujours allumee, aucun horaire : le noir est requis");
                    }
                    if (path.Count == 0)
                    {
                        return;
                    }
                    string pass = DarkFreePass(w, path, true, out string text);
                    if (pass != null)
                    {
                        result.Failures.Add(pass);
                    }
                    else
                    {
                        result.Notes.Add(text);
                    }
                    return;
                }
                case LevelDef.LessonGlide:
                {
                    NodeList naiveNodes = Search(w, new SearchOptions { StopSamples = 0, NeedDecoy = w.NeedDecoy }, out int naive);
                    if (naive < 0)
                    {
                        result.Failures.Add("lecon glide : aucun horaire meme en ignorant la glissade");
                        return;
                    }
                    List<Node> naivePath = PathTo(naiveNodes, naive);
                    int caught = FirstSeenGlide(w, naivePath);
                    if (caught < 0)
                    {
                        result.Failures.Add("lecon glide : l'horaire qui ignore la glissade n'est jamais vu en glissant : les arrets ne contraignent rien");
                    }
                    else
                    {
                        result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                            "lecon glide : sortie a {0:0.0} s avec les {1} echantillons d'arret, a {2:0.0} s sans ; l'horaire qui ignore la glissade est vu en glissant a {3:0.0} s : les arrets sont requis",
                            path.Count > 0 ? path[path.Count - 1].T * SampleSeconds : float.NaN, Tuning.AuditStopSamples,
                            naivePath[naivePath.Count - 1].T * SampleSeconds, caught * SampleSeconds));
                    }
                    return;
                }
                case LevelDef.LessonSit:
                {
                    if (path.Count == 0)
                    {
                        return; // no schedule at all: already a defect
                    }
                    if (w.FirstSit < 0)
                    {
                        result.Failures.Add("lecon sit : aucun habitant ne s'assoit sur le joueur pendant l'horaire");
                        return;
                    }
                    // CONTRACT_M4 10.1: the lesson cannot be skipped: with sitting disabled, no schedule reaches the exit
                    // before the first sitting.
                    World free = BuildWorld(def, level, false);
                    NodeList freeNodes = Search(free, new SearchOptions { NeedDecoy = free.NeedDecoy }, out int freeGoal);
                    float sitAt = w.FirstSit * SampleSeconds;
                    string earliest = freeGoal >= 0
                        ? string.Format(CultureInfo.InvariantCulture, "{0:0.0} s", freeNodes[freeGoal].T * SampleSeconds)
                        : "jamais";
                    if (freeGoal >= 0 && freeNodes[freeGoal].T <= w.FirstSit)
                    {
                        result.Failures.Add(string.Format(CultureInfo.InvariantCulture,
                            "lecon sit : sans s'asseoir, la sortie est atteinte a {0}, avant la premiere assise a {1:0.0} s : la lecon peut etre evitee", earliest, sitAt));
                    }
                    else
                    {
                        result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                            "lecon sit : premiere assise a {0:0.0} s ; sans s'asseoir, sortie au plus tot {1} : la lecon ne peut pas etre evitee", sitAt, earliest));
                    }
                    return;
                }
                case LevelDef.LessonDoor:
                case LevelDef.LessonPet:
                case LevelDef.LessonSplit:
                {
                    bool binds = LessonBinds(w, level, def.Lesson, out string text, out bool premise);
                    if (binds)
                    {
                        result.Notes.Add(text);
                    }
                    else
                    {
                        result.Failures.Add(text);
                    }
                    return;
                }
                case LevelDef.LessonFinal:
                {
                    // CONTRACT_M5 10: at least three of the level's mechanic checks bind (door, pet, split, robot, rock, load).
                    var binding = new List<string>();
                    foreach (string lesson in new[] { LevelDef.LessonDoor, LevelDef.LessonPet, LevelDef.LessonSplit,
                                 LevelDef.LessonRobot, LevelDef.LessonRock, LevelDef.LessonLoad })
                    {
                        bool binds = MechanicBinds(w, level, lesson, out string text, out bool premise);
                        result.Notes.Add("lecon final, " + text);
                        if (binds)
                        {
                            binding.Add(lesson);
                        }
                    }
                    string which = binding.Count > 0 ? string.Join(", ", binding) : "aucune";
                    if (binding.Count < 3)
                    {
                        result.Failures.Add($"lecon final : {binding.Count} verification(s) contraignent ({which}), il en faut au moins 3");
                    }
                    else
                    {
                        result.Notes.Add($"lecon final : {binding.Count} verifications contraignent ({which})");
                    }
                    return;
                }
                case LevelDef.LessonRobot:
                case LevelDef.LessonRock:
                case LevelDef.LessonLoad:
                {
                    bool binds = MechanicBinds(w, level, def.Lesson, out string text, out bool premise);
                    if (binds)
                    {
                        result.Notes.Add(text);
                    }
                    else
                    {
                        result.Failures.Add(text);
                    }
                    return;
                }
                default:
                    result.Failures.Add($"lecon '{def.Lesson}' inconnue");
                    return;
            }
        }

        /// <summary>
        /// CONTRACT_M4 10.5, CONTRACT_M5 16.3 and 17 (m1): darkness is not a free pass. Some watcher that can switch a dark
        /// lamp on (one with <see cref="PersonalityDef.Memory"/>: GameState never lets the dog do it) passes within its own
        /// dark range (its view range times <see cref="Tuning.LampOffLight"/>, as Vision scales it) of the lamp's path at least
        /// once; there, a careless lamp is seen and switched on. The approach nearest to a watcher's own range is printed
        /// with that watcher's name. With <paramref name="strict"/> false (the relaxed setting of the test_m5_audit_darkpass
        /// fixture) every watcher counts, the dog included, with the default range, as before wave 5A.1. Returns the
        /// failure, or null with the note in <paramref name="text"/>.
        /// </summary>
        private static string DarkFreePass(World w, List<Node> path, bool strict, out string text)
        {
            text = null;
            // Each approach is measured against its own watcher's range; in double, so that with a single range the order is
            // exactly the order of the distances (levels 1 to 7 keep their nearest sample).
            double best = double.MaxValue;
            float nearest = 0f;
            float range = 0f;
            int when = -1;
            int who = -1;
            for (int s = 0; s < w.Horizon; s++)
            {
                for (int h = 0; h < w.Inhabitants; h++)
                {
                    if (strict && !w.Watchers[h].Personality.Memory) // MUTATION:AUDIT_DARK_MEMORY
                    {
                        continue;
                    }
                    float darkRange = (strict ? w.Watchers[h].Range : Tuning.ViewRange) * Tuning.LampOffLight; // MUTATION:AUDIT_DARK_RANGE
                    foreach (Node n in path)
                    {
                        float d = YawMath.Planar(w.Position[s, h] - w.Center[n.Cell]).magnitude;
                        if ((double)d - darkRange < best)
                        {
                            best = (double)d - darkRange;
                            nearest = d;
                            range = darkRange;
                            when = s;
                            who = h;
                        }
                    }
                }
            }
            if (who < 0)
            {
                return "lecon dark : aucun habitant n'a de memoire, personne ne rallume la lampe : le noir est un passe-droit";
            }
            string near = string.Format(CultureInfo.InvariantCulture, "{0} passe a {1:0.0} m du chemin de la lampe a {2:0.0} s (sa portee dans le noir {3:0.0} m)",
                w.Watchers[who].Name, nearest, when * SampleSeconds, range);
            if (best > 0d)
            {
                return "lecon dark : aucun habitant qui rallume la lampe ne passe a sa portee dans le noir du chemin de la lampe (au plus pres : "
                    + near + ") : le noir est un passe-droit";
            }
            text = "lecon dark : " + near + " : le noir ne suffit pas, il faut choisir le moment";
            return null;
        }

        /// <summary>
        /// The first sample (or -1) at which a schedule found without the glide is seen during a glide: after every run
        /// that ends in a stop, <see cref="Tuning.AuditStopSamples"/> samples at the stop cell must be unseen. A run that
        /// ends in the exit is not counted (the level is won as the chair enters).
        /// </summary>
        private static int FirstSeenGlide(World w, List<Node> path)
        {
            for (int i = 1; i < path.Count; i++)
            {
                Node m = path[i];
                bool stops = m.Move && (i + 1 >= path.Count || !path[i + 1].Move);
                if (!stops || w.InExit[m.Cell])
                {
                    continue;
                }
                for (int q = 1; q <= Tuning.AuditStopSamples; q++)
                {
                    int s = m.T + q;
                    if (s < w.Samples && (w.MovingSeen(m.Off, m.Mask, s, m.Cell, false) || w.ForcedAt(s, false)))
                    {
                        return s;
                    }
                }
            }
            return -1;
        }

        /// <summary>
        /// CONTRACT_M5 5 and 16.9: the first sample (or -1) at which a schedule found without the rock is seen rocking: after
        /// every move that ends in a stop, <paramref name="samples"/> samples at the stop cell must be unseen moving (and not
        /// where a sitter forces the player). A run that ends in the exit is not counted (the level is won as it enters).
        /// <paramref name="at"/> is the stop cell.
        /// </summary>
        private static int FirstSeenStop(World w, List<Node> path, int samples, out int at)
        {
            at = -1;
            for (int i = 1; i < path.Count; i++)
            {
                Node m = path[i];
                bool stops = m.Move && (i + 1 >= path.Count || !path[i + 1].Move);
                if (!stops || w.InExit[m.Cell])
                {
                    continue;
                }
                for (int q = 1; q <= samples; q++)
                {
                    int s = m.T + q;
                    if (s < w.Samples && (w.MovingSeen(m.Off, m.Mask, s, m.Cell, false) || w.ForcedAt(s, false)))
                    {
                        at = m.Cell;
                        return s;
                    }
                }
            }
            return -1;
        }

        /// <summary>
        /// For a level with no schedule: which single rule, relaxed, gives one (the wait cap, hearing, the creak gauge,
        /// sitting). A note for the designer; the defect stands.
        /// </summary>
        private static void Diagnose(LevelDef def, LevelInstance level, World w, Result result)
        {
            var found = new List<string>();
            void Try(string what, World world, SearchOptions o)
            {
                NodeList n = Search(world, o, out int g);
                if (g >= 0)
                {
                    found.Add(what + " (" + Summary(world, PathTo(n, g)) + ")");
                }
            }
            Try("sans plafond d'attente", w, new SearchOptions { MaxRun = UnlimitedRun, NeedDecoy = w.NeedDecoy });
            foreach (int cap in new[] { 90, 100, 120 })
            {
                Try(string.Format(CultureInfo.InvariantCulture, "avec un plafond de {0:0} s", cap * SampleSeconds), w, new SearchOptions { MaxRun = cap, NeedDecoy = w.NeedDecoy });
            }
            Try("sans bruit", w, new SearchOptions { Noise = false, NeedDecoy = w.NeedDecoy });
            Try("sans grincement", w, new SearchOptions { GaugeCap = float.MaxValue, NeedDecoy = w.NeedDecoy });
            // M5 wave 5B: the new mechanics, one at a time (only on the levels that have them).
            if (w.Robots > 0)
            {
                Try("sans le robot (ni zone de contact ni ronronnement)", w, new SearchOptions { Robots = false, NeedDecoy = w.NeedDecoy });
            }
            if (w.RockSamples > 0)
            {
                Try("sans la bascule", w, new SearchOptions { Rock = false, NeedDecoy = w.NeedDecoy });
            }
            if (w.HasLoad)
            {
                Try("sans la regle de la charge", w, new SearchOptions { LoadRule = false, NeedDecoy = w.NeedDecoy });
            }
            if (Array.IndexOf(w.Forced, true) >= 0)
            {
                Try("personne ne s'assoit", BuildWorld(def, level, false), new SearchOptions { NeedDecoy = w.NeedDecoy });
            }
            result.Notes.Add(found.Count == 0 ? "diagnostic : aucune regle seule relachee ne donne d'horaire" : "diagnostic : un horaire existe " + string.Join(" ; ", found));
        }

        /// <summary>Design aid: the cells seen at one sample (x seen, d seen only lit, . unseen, # blocked, h heard within the hop radius).</summary>
        private static string SeenMap(World w, int s)
        {
            var sb = new StringBuilder();
            sb.Append(string.Format(CultureInfo.InvariantCulture, "vue a {0:0.0} s (x vu, . non vu, # bloque, ! habitant) :", s * SampleSeconds)).AppendLine();
            for (int r = 0; r < w.Rooms.Count; r++)
            {
                for (int j = w.Size[r].nz - 1; j >= 0; j--)
                {
                    sb.Append("    ");
                    for (int i = 0; i < w.Size[r].nx; i++)
                    {
                        int k = w.Index[(r, i, j)];
                        bool here = false;
                        for (int h = 0; h < w.Inhabitants; h++)
                        {
                            here |= YawMath.Planar(w.Position[s, h] - w.Center[k]).magnitude < 0.36f;
                        }
                        char ch = here ? '!' : !w.Walkable[k] ? '#' : w.MovingSeen(false, 0, s, k, false) ? 'x' : '.';
                        sb.Append(ch).Append(' ');
                    }
                    sb.AppendLine();
                }
                sb.AppendLine();
            }
            return sb.ToString();
        }

        /// <summary>The true runs of a per-sample flag, as "a-b s" in game time, up to <paramref name="until"/> samples (the first six).</summary>
        private static string Intervals(bool[] flags, int until)
        {
            var parts = new List<string>();
            int start = -1;
            for (int s = 0; s <= Mathf.Min(until, flags.Length - 1) && parts.Count < 6; s++)
            {
                bool on = flags[s] && s < until;
                if (on && start < 0)
                {
                    start = s;
                }
                else if (!on && start >= 0)
                {
                    parts.Add(string.Format(CultureInfo.InvariantCulture, "{0:0.0}-{1:0.0} s", start * SampleSeconds, s * SampleSeconds));
                    start = -1;
                }
            }
            return parts.Count > 0 ? string.Join(", ", parts) : "jamais";
        }

        /// <summary>A schedule in one line: its exit time and where it stops or acts, for the lesson defects.</summary>
        private static string Summary(World w, List<Node> path)
        {
            var sb = new StringBuilder();
            int longest = 0;
            foreach (Node n in path)
            {
                longest = Mathf.Max(longest, n.Run);
            }
            sb.Append(string.Format(CultureInfo.InvariantCulture, "sortie a {0:0.0} s, attente max {1:0.0} s", path[path.Count - 1].T * SampleSeconds, longest * SampleSeconds));
            for (int i = 1; i < path.Count; i++)
            {
                Node n = path[i];
                bool stopHere = n.Act == Act.Stop || n.Act == Act.Toggle || n.Act == Act.Open || (n.Act == Act.Still && path[i - 1].Act == Act.Move);
                if (stopHere)
                {
                    Vector3 c = w.Center[n.Cell];
                    sb.Append(string.Format(CultureInfo.InvariantCulture, " ; {0} ({1:0.##}, {2:0.##}) a {3:0.0} s",
                        n.Act == Act.Toggle ? "interrupteur" : n.Act == Act.Open ? "porte" : "arret", c.x, c.z, path[i - 1].T * SampleSeconds));
                }
            }
            return sb.ToString();
        }

        /// <summary>
        /// CONTRACT_M4 10.7 (playtest data, not a gate): the largest margin, in samples each way, for which a schedule
        /// still exists. The audit's own margin is <see cref="MarginSamples"/>.
        /// </summary>
        private static void SlackReport(World w, Result result)
        {
            int best = w.Margin;
            for (int m = w.Margin + 1; m <= SlackReportMax; m++)
            {
                SetMargin(w, m);
                Search(w, new SearchOptions { NeedDecoy = w.NeedDecoy }, out int goal);
                if (goal < 0)
                {
                    break;
                }
                best = m;
            }
            SetMargin(w, MarginSamples);
            result.SlackSamples = best;
            result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                "marge maximale : un horaire existe encore avec {0} echantillons de marge de chaque cote ({1:0.0} s ; l'audit en exige {2}){3}",
                best, best * SampleSeconds, MarginSamples, best >= SlackReportMax ? ", au moins" : ""));
        }

        /// <summary>
        /// M2.2 (b): the player may start acting at any moment of the routine loop. For every start delay d
        /// (every second of the first loop), a schedule from spawn must exist whose waits after d stay within
        /// the limit. Prints the delay that takes longest to get out.
        /// </summary>
        private static void Sweep(World w, Result result)
        {
            if (w.Wanders)
            {
                result.Notes.Add("departs retardes : pas de balayage, une routine erre (wander) et ne boucle jamais (CONTRACT_M5 16.3)");
                return;
            }
            var failing = new List<string>();
            for (int d = 0; d < w.LoopSamples; d += w.SweepEvery)
            {
                NodeList nodes = Search(w, new SearchOptions { Delay = d }, out int goal);
                if (goal < 0)
                {
                    failing.Add((d * SampleSeconds).ToString("0", CultureInfo.InvariantCulture));
                    continue;
                }
                List<Node> path = PathTo(nodes, goal);
                float took = (path[path.Count - 1].T - d) * SampleSeconds;
                int longest = 0;
                foreach (Node n in path)
                {
                    longest = Mathf.Max(longest, n.Run);
                }
                result.SweepLongestWait = Mathf.Max(result.SweepLongestWait, longest * SampleSeconds);
                if (took > result.WorstDelayTime)
                {
                    result.WorstDelayTime = took;
                    result.WorstDelay = d * SampleSeconds;
                }
            }
            if (failing.Count > 0)
            {
                // Reported, not a defect (integrator decision, 2026-11-12): the PRD gate asks that no cell of the
                // schedule requires waiting more than 8 s, which the main schedule satisfies. Every start delay
                // being clean is stricter than the PRD; the numbers go to the playtest instead (README).
                result.Notes.Add($"AVERTISSEMENT depart retarde : aucun horaire sans attente de plus de 8 s quand le joueur commence a {string.Join(", ", failing)} s (boucle de {w.LoopSamples * SampleSeconds:0.0} s)");
            }
            result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                "departs retardes (toutes les {0:0} s sur la boucle de {1:0.0} s) : {2} en echec, pire depart a {3:0} s (sortie {4:0.0} s plus tard), attente la plus longue {5:0.0} s",
                w.SweepEvery * SampleSeconds, w.LoopSamples * SampleSeconds, failing.Count, result.WorstDelay, result.WorstDelayTime, result.SweepLongestWait));
        }

        /// <summary>CONTRACT_M5_v3 15.10: the minimum distance between two humans at every sample (Tuning.WatcherSeparation).</summary>
        private static float Separation => Tuning.WatcherSeparation; // MUTATION:AUDIT_SEPARATION

        /// <summary>
        /// M5 levels name their watchers (personality, range, half angle, hearing, tolerance), so the report says what the
        /// search assumed. Levels 1 to 7 (one default human) print nothing new.
        /// </summary>
        private static void DescribeWatchers(World w, Result result)
        {
            bool plain = Array.TrueForAll(w.Watchers, x => x.Human && x.Personality.Id == PersonalityDef.Default);
            if (plain)
            {
                return;
            }
            var parts = new List<string>();
            foreach (Watcher x in w.Watchers)
            {
                parts.Add(string.Format(CultureInfo.InvariantCulture, "{0} ({1}{2}, {3:0.#} m, {4:0} deg{5})", x.Name, x.Personality.Id,
                    x.Human ? "" : ", voit en mouvement seulement", x.Range, x.HalfAngle,
                    x.Human ? string.Format(CultureInfo.InvariantCulture, ", ouie x{0:0.0#}, tolerance {1:0.0#} m", x.HearingFactor, w.Classes[x.Class].Tolerance) : ""));
            }
            result.Notes.Add("habitants : " + string.Join(", ", parts) + string.Format(CultureInfo.InvariantCulture,
                " ; {0} classe(s) de tolerance, {1} table(s) de portes", w.Classes.Count, w.Masks));
        }

        /// <summary>CONTRACT_M5_v3 15.3: the reach cells of every closed leaf, and a closed leaf no walkable cell reaches fails.</summary>
        private static void CheckLeaves(World w, Result result)
        {
            foreach (Leaf leaf in w.Closed)
            {
                if (leaf.Reach.Count == 0)
                {
                    result.Failures.Add($"porte {leaf.Door.Id} fermee sans case d'atteinte praticable (DoorGeometry.InReach) : elle ne peut pas s'ouvrir");
                    continue;
                }
                var cells = new List<string>();
                foreach (int k in leaf.Reach)
                {
                    cells.Add(string.Format(CultureInfo.InvariantCulture, "({0:0.##}, {1:0.##})", w.Center[k].x, w.Center[k].z));
                }
                result.Notes.Add($"porte {leaf.Door.Id} : {leaf.Reach.Count} case(s) d'atteinte : {string.Join(" ", cells)}");
            }
        }

        /// <summary>
        /// CONTRACT_M5_v3 15.10 and CONTRACT_M5 10: every pair of humans stays at least <paramref name="minimum"/> apart at
        /// every sample of the horizon, and humans who share a level cross (share a room at the same sample at least once).
        /// Notes the closest approach of every pair; returns the failures.
        /// </summary>
        private static List<string> CheckSeparation(World w, float minimum, List<string> notes)
        {
            var failures = new List<string>();
            var humans = new List<int>();
            for (int i = 0; i < w.Inhabitants; i++)
            {
                if (w.Watchers[i].Human)
                {
                    humans.Add(i);
                }
            }
            for (int x = 0; x < humans.Count; x++)
            {
                for (int y = x + 1; y < humans.Count; y++)
                {
                    int a = humans[x];
                    int b = humans[y];
                    float closest = float.MaxValue;
                    int when = -1;
                    bool crossed = false;
                    for (int s = 0; s < w.Horizon; s++)
                    {
                        float d = YawMath.Planar(w.Position[s, a] - w.Position[s, b]).magnitude;
                        if (d < closest)
                        {
                            closest = d;
                            when = s;
                        }
                        if (!crossed)
                        {
                            RoomDef room = w.Def.RoomAt(w.Position[s, a]);
                            crossed = room != null && room == w.Def.RoomAt(w.Position[s, b]);
                        }
                    }
                    string pair = $"{w.Watchers[a].Name} et {w.Watchers[b].Name}";
                    notes.Add(string.Format(CultureInfo.InvariantCulture, "{0} : au plus pres {1:0.00} m a {2:0.0} s{3}", pair, closest, when * SampleSeconds,
                        crossed ? ", se croisent" : ""));
                    if (closest < minimum)
                    {
                        failures.Add(string.Format(CultureInfo.InvariantCulture, "{0} passent a {1:0.00} m l'un de l'autre a {2:0.0} s (au moins {3:0.0#} m)",
                            pair, closest, when * SampleSeconds, minimum));
                    }
                    if (!crossed)
                    {
                        failures.Add(string.Format(CultureInfo.InvariantCulture, "{0} ne se croisent jamais : jamais dans la meme piece au meme instant en {1:0} s",
                            pair, w.Horizon * SampleSeconds));
                    }
                }
            }
            return failures;
        }

        /// <summary>
        /// CONTRACT_M5 16.3: a tolerance below the M2 one (tidy, watchful) leaves almost no room off the cell grid. A spawn
        /// that is not within the class's in place radius of a walkable cell center, or a decoy that is not within its
        /// explained radius of one, is a warning (a schedule then never stays still in sight of those humans there).
        /// </summary>
        private static void ToleranceWarnings(World w, Result result)
        {
            foreach (ToleranceClass c in w.Classes)
            {
                if (c.Tolerance >= Tuning.DisplacementTolerance)
                {
                    continue;
                }
                bool Near(Vector3 p, float radius)
                {
                    for (int k = 0; k < w.Count; k++)
                    {
                        if (w.Walkable[k] && YawMath.Planar(w.Center[k] - p).magnitude <= radius)
                        {
                            return true;
                        }
                    }
                    return false;
                }
                if (!Near(w.Def.Player.Position, c.InPlaceRadius))
                {
                    result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                        "AVERTISSEMENT tolerance {0:0.0#} m : le depart ({1:0.##}, {2:0.##}) n'est a moins de {3:0.0##} m d'aucun centre de case : vu immobile, il n'est jamais a sa place",
                        c.Tolerance, w.Def.Player.X, w.Def.Player.Z, c.InPlaceRadius));
                }
                for (int i = 0; i < w.Def.Decoys.Count; i++)
                {
                    DecoyDef d = w.Def.Decoys[i];
                    if (BodyKinds.Of(d.Kind) == w.Body.Body.Kind && !Near(d.Position, c.ExplainedRadius))
                    {
                        result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                            "AVERTISSEMENT tolerance {0:0.0#} m : le leurre {1} ({2:0.##}, {3:0.##}) n'est a moins de {4:0.0##} m d'aucun centre de case : il n'explique rien",
                            c.Tolerance, i + 1, d.X, d.Z, c.ExplainedRadius));
                    }
                }
            }
        }

        /// <summary>
        /// CONTRACT_M5 16.7: the habits of the personalities are data, checked as warnings: dreamer dwells average 4 s or
        /// more; watchful glances in every dwell of 2 s or more; granny sits at least once in any 60 s; hurried dwells average
        /// 2 s or less; teen dwells average 3 s or more, with glances under 30 deg.
        /// </summary>
        private static void HabitWarnings(World w, Result result)
        {
            for (int i = 0; i < w.Inhabitants; i++)
            {
                InhabitantDef h = w.Def.Inhabitants[i];
                string id = w.Watchers[i].Personality.Id;
                float average = 0f;
                foreach (StationDef st in h.Stations)
                {
                    average += st.Dwell / Mathf.Max(1, h.Stations.Count);
                }
                void Warn(string what)
                {
                    result.Notes.Add($"AVERTISSEMENT habitude ({h.Name}, {id}) : {what}");
                }
                switch (id)
                {
                    case PersonalityDef.Dreamer when average < 4f:
                        Warn(string.Format(CultureInfo.InvariantCulture, "attente moyenne {0:0.0} s, sous 4 s", average));
                        break;
                    case PersonalityDef.Hurried when average > 2f:
                        Warn(string.Format(CultureInfo.InvariantCulture, "attente moyenne {0:0.0} s, au dessus de 2 s", average));
                        break;
                    case PersonalityDef.Teen:
                        if (average < 3f)
                        {
                            Warn(string.Format(CultureInfo.InvariantCulture, "attente moyenne {0:0.0} s, sous 3 s", average));
                        }
                        if (h.Stations.Exists(st => st.Glances.Exists(g => Mathf.Abs(g.Yaw) >= 30f)))
                        {
                            Warn("un coup d'oeil de 30 deg ou plus");
                        }
                        break;
                    case PersonalityDef.Watchful:
                        for (int k = 0; k < h.Stations.Count; k++)
                        {
                            if (h.Stations[k].Dwell >= 2f && h.Stations[k].Glances.Count == 0)
                            {
                                Warn($"la station {k + 1} attend {h.Stations[k].Dwell:0.0} s sans coup d'oeil");
                            }
                        }
                        break;
                    case PersonalityDef.Granny:
                    {
                        int window = Mathf.RoundToInt(60f / SampleSeconds);
                        int last = -1;
                        int gap = 0;
                        for (int s = 0; s < w.Horizon; s++)
                        {
                            if (w.Sits[s * w.Inhabitants + i])
                            {
                                gap = Mathf.Max(gap, s - last - 1);
                                last = s;
                            }
                        }
                        gap = Mathf.Max(gap, w.Horizon - last - 1);
                        if (gap > window)
                        {
                            Warn(string.Format(CultureInfo.InvariantCulture, "{0:0} s sans s'asseoir (au plus 60 s)", gap * SampleSeconds));
                        }
                        break;
                    }
                }
            }
        }

        /// <summary>
        /// The M5 lesson checks (CONTRACT_M5 10, 16.3, 16.6; CONTRACT_M5_v3 8), each a table edit, never a rebuilt level:
        /// door, no schedule with every leaf locked; pet, no schedule if the dog saw from 1.6 m; split, no schedule with the
        /// platform and ramp cells barred. True when the check binds; <paramref name="premise"/> is false when the level lacks
        /// the mechanic.
        /// </summary>
        private static bool LessonBinds(World w, LevelInstance level, string lesson, out string text, out bool premise)
        {
            premise = true;
            World world = w;
            var options = new SearchOptions { NeedDecoy = w.NeedDecoy };
            string relaxed;
            string why;
            switch (lesson)
            {
                case LevelDef.LessonDoor:
                    premise = w.Closed.Count > 0;
                    options.Doors = false;
                    relaxed = "toutes les portes verrouillees";
                    why = "il faut ouvrir une porte";
                    break;
                case LevelDef.LessonPet:
                    premise = Array.Exists(w.Watchers, x => !x.Human);
                    if (premise)
                    {
                        world = DogEyeVariant(w, level);
                    }
                    relaxed = "l'oeil du chien a " + Tuning.EyeHeight.ToString("0.0#", CultureInfo.InvariantCulture) + " m";
                    why = "le couvert bas est requis";
                    break;
                default:
                    options.Barred = PlatformCells(w);
                    premise = Array.IndexOf(options.Barred, true) >= 0;
                    relaxed = "plateforme et rampe interdites";
                    why = "la mezzanine est requise";
                    break;
            }
            if (!premise)
            {
                text = $"lecon {lesson} : le niveau n'a pas la mecanique ({relaxed} ne change rien)";
                return false;
            }
            NodeList nodes = Search(world, options, out int goal);
            if (goal >= 0)
            {
                text = $"lecon {lesson} : un horaire existe aussi avec {relaxed} : la lecon n'est pas requise (" + Summary(world, PathTo(nodes, goal)) + ")";
                return false;
            }
            text = $"lecon {lesson} : {relaxed}, aucun horaire : {why}";
            return true;
        }

        /// <summary>
        /// One mechanic check of CONTRACT_M5 10, by lesson: door, pet and split (<see cref="LessonBinds"/>), robot
        /// (<see cref="RobotBinds"/>), rock (<see cref="RockBinds"/>) and load (<see cref="LoadBinds"/>). True when it binds;
        /// <paramref name="premise"/> is false when the level lacks the mechanic.
        /// </summary>
        private static bool MechanicBinds(World w, LevelInstance level, string lesson, out string text, out bool premise)
        {
            switch (lesson)
            {
                case LevelDef.LessonRobot:
                    return RobotBinds(w, out text, out premise);
                case LevelDef.LessonRock:
                    return RockBinds(w, out text, out premise);
                case LevelDef.LessonLoad:
                    return LoadBinds(w, out text, out premise);
                default:
                    return LessonBinds(w, level, lesson, out text, out premise);
            }
        }

        /// <summary>
        /// CONTRACT_M5 10, lesson robot, as table edits: the hum binds (no schedule with the hum switched off), or the robot
        /// binds (the schedule computed without the robot, neither its contact zone nor its hum, collides with it on its
        /// timeline: RobotPath.Overlaps of the robot's disc and the footprint, see <see cref="FirstContact"/>). The text says
        /// which.
        /// </summary>
        private static bool RobotBinds(World w, out string text, out bool premise)
        {
            premise = w.Robots > 0;
            if (!premise)
            {
                text = "lecon robot : le niveau n'a pas la mecanique (aucun robot)";
                return false;
            }
            NodeList quietNodes = Search(w, new SearchOptions { Hum = false, NeedDecoy = w.NeedDecoy }, out int quiet);
            if (quiet < 0)
            {
                text = "lecon robot : ronronnement coupe, aucun horaire : le ronronnement est requis (le robot contraint par son bruit)";
                return true;
            }
            string quietSummary = Summary(w, PathTo(quietNodes, quiet));
            NodeList freeNodes = Search(w, new SearchOptions { Robots = false, NeedDecoy = w.NeedDecoy }, out int free);
            if (free < 0)
            {
                text = "lecon robot : un horaire existe ronronnement coupe (" + quietSummary + ") mais aucun sans le robot (incoherence de l'audit)";
                return false;
            }
            List<Node> freePath = PathTo(freeNodes, free);
            int hit = FirstContact(w, freePath, out float closest, out int when);
            if (hit >= 0)
            {
                text = string.Format(CultureInfo.InvariantCulture,
                    "lecon robot : l'horaire calcule sans le robot le heurte a {0:0.0} s ({1}) : le robot est requis (le robot contraint par le contact) ; ronronnement coupe, un horaire existe ({2}) ; contre-route : {3}",
                    hit * SampleSeconds, Summary(w, freePath), quietSummary, RouteJson(Route(w, freePath)));
                return true;
            }
            text = string.Format(CultureInfo.InvariantCulture,
                "lecon robot : un horaire existe aussi ronronnement coupe ({0}), et l'horaire calcule sans le robot ne le touche jamais (au plus pres {1:0.00} m a {2:0.0} s) : la lecon n'est pas requise",
                quietSummary, closest, when * SampleSeconds);
            return false;
        }

        /// <summary>
        /// CONTRACT_M5 10 and 16.9, lesson rock: the schedule computed without the rock is seen rocking (during the
        /// <see cref="World.RockSamples"/> samples after one of its stops).
        /// </summary>
        private static bool RockBinds(World w, out string text, out bool premise)
        {
            premise = w.RockSamples > 0;
            if (!premise)
            {
                text = "lecon rock : le niveau n'a pas la mecanique (le meuble ne bascule pas)";
                return false;
            }
            NodeList naiveNodes = Search(w, new SearchOptions { Rock = false, NeedDecoy = w.NeedDecoy }, out int naive);
            if (naive < 0)
            {
                text = "lecon rock : aucun horaire meme sans la bascule";
                return false;
            }
            List<Node> naivePath = PathTo(naiveNodes, naive);
            int caught = FirstSeenStop(w, naivePath, w.RockSamples, out int cell);
            if (caught < 0)
            {
                text = "lecon rock : l'horaire calcule sans la bascule n'est jamais vu en basculant (" + Summary(w, naivePath) + ") : les arrets ne contraignent rien";
                return false;
            }
            text = string.Format(CultureInfo.InvariantCulture,
                "lecon rock : l'horaire calcule sans la bascule (sortie a {0:0.0} s) est vu en basculant a {1:0.0} s, arret en ({2:0.##}, {3:0.##}) : la bascule est requise ; contre-route : {4}",
                naivePath[naivePath.Count - 1].T * SampleSeconds, caught * SampleSeconds, w.Center[cell].x, w.Center[cell].z, RouteJson(Route(w, naivePath)));
            return true;
        }

        /// <summary>
        /// CONTRACT_M5 10 and 16.5, lesson load: the schedule computed without the load rule (full speed, the load never falls)
        /// drops the load when its velocity profile (<see cref="PathLoadFall"/>, MotionProfile and LoadBalance) is simulated.
        /// </summary>
        private static bool LoadBinds(World w, out string text, out bool premise)
        {
            premise = w.HasLoad;
            if (!premise)
            {
                text = "lecon load : le niveau n'a pas la mecanique (aucune charge)";
                return false;
            }
            NodeList naiveNodes = Search(w, new SearchOptions { LoadRule = false, NeedDecoy = w.NeedDecoy }, out int naive);
            if (naive < 0)
            {
                text = "lecon load : aucun horaire meme sans la regle de la charge";
                return false;
            }
            List<Node> naivePath = PathTo(naiveNodes, naive);
            float fall = PathLoadFall(w, naivePath, out float peak);
            if (fall < 0f)
            {
                text = string.Format(CultureInfo.InvariantCulture,
                    "lecon load : l'horaire calcule sans la regle de la charge la garde (ecart de vitesse au plus {0:0.00} m/s sur {1:0.0} s, sous {2:0.0}) ({3}) : la lecon n'est pas requise",
                    peak, Tuning.LoadWindow, Tuning.LoadFallDeltaV, Summary(w, naivePath));
                return false;
            }
            text = string.Format(CultureInfo.InvariantCulture,
                "lecon load : l'horaire calcule sans la regle de la charge (sortie a {0:0.0} s) la fait tomber a {1:0.00} s (ecart de vitesse {2:0.00} m/s sur {3:0.0} s) : la conduite prudente est requise ; contre-route : {4}",
                naivePath[naivePath.Count - 1].T * SampleSeconds, fall, peak, Tuning.LoadWindow, RouteJson(Route(w, naivePath)));
            return true;
        }

        /// <summary>
        /// The first sample (or -1) at which a schedule touches a robot on its fixed timeline: RobotPath.Overlaps of the robot's
        /// disc and the footprint (the body's size), the furniture at its planned place (the spawn until the schedule starts,
        /// then along each move, facing where it goes, as the controller turns to its input). <paramref name="closest"/> is the
        /// nearest planar distance between the robot and the furniture's center, at <paramref name="when"/>.
        /// </summary>
        private static int FirstContact(World w, List<Node> path, out float closest, out int when)
        {
            closest = float.MaxValue;
            when = -1;
            if (w.Robots == 0 || path.Count == 0)
            {
                return -1;
            }
            Vector3 size = w.Body.Body.Size;
            float yaw = w.Def.Player.Yaw;
            int hit = -1;
            float nearest = float.MaxValue;
            int nearestAt = -1;
            bool Touches(int s, Vector3 at)
            {
                if (s < 0 || s >= w.Samples)
                {
                    return false;
                }
                bool touching = false;
                for (int r = 0; r < w.Robots; r++)
                {
                    Vector3 robot = w.RobotAt[s * w.Robots + r];
                    float d = YawMath.Planar(robot - at).magnitude;
                    if (d < nearest)
                    {
                        nearest = d;
                        nearestAt = s;
                    }
                    touching |= RobotPath.Overlaps(robot, new FurniturePose(at, yaw), size);
                }
                return touching;
            }
            for (int s = 0; s <= path[0].T; s++)
            {
                if (Touches(s, w.Spawn) && hit < 0)
                {
                    hit = s;
                }
            }
            for (int i = 1; i < path.Count; i++)
            {
                Node a = path[i - 1];
                Node b = path[i];
                Vector3 from = YawMath.Planar(w.Center[a.Cell]);
                Vector3 to = YawMath.Planar(w.Center[b.Cell]);
                int right = b.Move && a.Lying ? RightSamples : 0;
                int length = b.T - a.T;
                if (b.Move && (to - from).sqrMagnitude > 1e-6f)
                {
                    yaw = YawMath.YawOf(to - from);
                }
                for (int q = 1; q <= length; q++)
                {
                    float f = b.Move ? Mathf.Clamp01((q - right) / (float)Mathf.Max(1, length - right)) : 1f;
                    if (Touches(a.T + q, Vector3.Lerp(from, to, f)) && hit < 0)
                    {
                        hit = a.T + q;
                    }
                }
            }
            closest = nearest;
            when = nearestAt;
            return hit;
        }

        /// <summary>
        /// The wishes of a schedule, five fixed steps a sample, as the replay drives it (CONTRACT_M5 16.5): every move a cell
        /// direction at full or careful stick (a lying stool's righting first, without input), every other sample no input (a
        /// still, a stop, a toggle, an opening). It starts at rest at the schedule's first sample.
        /// </summary>
        private static List<MotionWish> PathWishes(World w, List<Node> path)
        {
            var wishes = new List<MotionWish>();
            for (int i = 1; i < path.Count; i++)
            {
                Node a = path[i - 1];
                Node b = path[i];
                int length = b.T - a.T;
                int right = b.Move && a.Lying ? RightSamples : 0;
                for (int q = 0; q < length; q++)
                {
                    MotionWish wish = b.Move && q >= right
                        ? new MotionWish(LoadModel.DirVector(DirIndex(w, a.Cell, b.Cell)), b.Careful)
                        : MotionWish.None();
                    for (int step = 0; step < SampleSteps; step++)
                    {
                        wishes.Add(wish);
                    }
                }
            }
            return wishes;
        }

        /// <summary>
        /// CONTRACT_M5 16.5: the game time (s) at which the load falls along a schedule's velocity profile (MotionProfile from
        /// rest, then LoadBalance.FirstFall), or -1 when it holds; <paramref name="peak"/> is the largest change over the window.
        /// </summary>
        private static float PathLoadFall(World w, List<Node> path, out float peak)
        {
            Vector2[] velocities = MotionProfile.Synthesize(w.Body.Body, PathWishes(w, path));
            peak = LoadBalance.PeakOf(velocities);
            int fall = LoadBalance.FirstFall(velocities);
            return fall < 0 ? -1f : path[0].T * SampleSeconds + (fall + 1) * Tuning.FixedStep;
        }

        /// <summary>The level's load model for a search's leg lengths, careful base and stop cost (built once, then shared).</summary>
        private static LoadModel LoadModelFor(World w, int travel, bool carefulBase, int altTravel, int stopCost)
        {
            var key = (travel, carefulBase, altTravel, stopCost);
            if (!w.LoadModels.TryGetValue(key, out LoadModel model))
            {
                model = new LoadModel(w.Body.Body, travel, carefulBase, altTravel, stopCost, OpenSamples, RightSamples);
                w.LoadModels[key] = model;
            }
            Budget.LoadStates = Math.Max(Budget.LoadStates, model.Count);
            return model;
        }

        /// <summary>The cell direction of a move: 0 toward +x, 1 toward -x, 2 toward +z, 3 toward -z.</summary>
        private static int DirIndex(World w, int k, int o)
        {
            Vector3 d = w.Center[o] - w.Center[k];
            return Mathf.Abs(d.x) >= Mathf.Abs(d.z) ? (d.x > 0f ? 0 : 1) : (d.z > 0f ? 2 : 3);
        }

        /// <summary>
        /// M5 wave 5B: what the search assumes about the robot, the rock and the load, one note each (only on the levels that
        /// have them, so the other levels print nothing new).
        /// </summary>
        private static void DescribeMechanics(World w, Result result)
        {
            if (w.Robots > 0)
            {
                var loops = new List<string>();
                foreach (RobotPath p in w.RobotPaths)
                {
                    loops.Add(string.Format(CultureInfo.InvariantCulture, "{0:0.00} m/s, boucle de {1:0.0} s", p.Speed, p.Period));
                }
                result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                    "robot ({0}) : trajet fixe ; zone de contact {1:0.00} m (rayon {2:0.00} + demi-diagonale {3:0.00} + relache {4:0.0} + course sur la marge {5:0.00}), sur chaque deplacement, chaque arret et au depart ; ronronnement a {6:0.00} m ({7:0.0} moins la course) sur toute la fenetre de marge",
                    string.Join(" ; ", loops), w.ContactBase + w.RobotTravel, Tuning.RobotRadius, w.ContactBase - Tuning.RobotRadius - ReleaseTolerance,
                    ReleaseTolerance, w.RobotTravel, Tuning.RobotHumRadius - w.RobotTravel, Tuning.RobotHumRadius));
            }
            if (w.RockSamples > 0)
            {
                result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                    "bascule : chaque arret coute {0} echantillons vus en mouvement (pleine vitesse) ; {1} echantillons par case au depart et dans un virage, {2} en continuant tout droit ; la designerRoute enchaine les points d'une meme course",
                    w.RockSamples, w.Body.MoveSamples, w.Body.ContinueSamples));
            }
            if (w.HasLoad)
            {
                result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                    "charge {0} : tombe quand la vitesse change de {1:0.0} m/s en {2:0.0} s (MotionProfile et LoadBalance sur l'historique des {3} derniers echantillons) ; jambes prudentes {4}({5} echantillons par case){6} ; boite de vue plus haute de {7:0.00} m",
                    w.Def.Player.Load, Tuning.LoadFallDeltaV, Tuning.LoadWindow, LoadHistorySamples,
                    w.Body.Tips || w.Body.FullStartDropsLoad ? "seulement " : "permises ",
                    w.Body.Tips ? w.Body.MoveSamples : w.Body.CarefulMoveSamples,
                    w.Body.Tips ? "" : w.Body.FullStartDropsLoad ? ", un depart a pleine vitesse la fait tomber" : $", pleine vitesse {w.Body.MoveSamples}",
                    w.Body.LoadHeight));
            }
        }

        /// <summary>
        /// M5 wave 5B: what the found schedule does with the robot, the rock and the load: the nearest approach to the robot and
        /// the noises its hum masks, the rocks, and the load simulated along the schedule (a fall is an internal defect: the
        /// search refused it).
        /// </summary>
        private static void DescribeMechanicsOnPath(World w, List<Node> path, Result result)
        {
            if (w.Robots > 0)
            {
                int contact = FirstContact(w, path, out float closest, out int when);
                int masked = 0;
                for (int i = 1; i < path.Count; i++)
                {
                    Node a = path[i - 1];
                    Node b = path[i];
                    if (!b.Move)
                    {
                        continue;
                    }
                    int right = a.Lying ? RightSamples : 0;
                    int travel = b.T - a.T - right;
                    for (int q = 1; q <= travel; q++)
                    {
                        Vector3 p = Vector3.Lerp(w.Center[a.Cell], w.Center[b.Cell], q / (float)travel);
                        int s = a.T + right + q;
                        masked += Heard(w, p, s, w.Body.MoveNoiseKind, false, false) && !Heard(w, p, s, w.Body.MoveNoiseKind, false, true) ? 1 : 0;
                    }
                }
                result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                    "robot : l'horaire passe au plus pres a {0:0.00} m de lui a {1:0.0} s{2} ; {3} echantillon(s) de deplacement entendus sans le ronronnement, masques par lui",
                    closest, when * SampleSeconds, contact >= 0 ? string.Format(CultureInfo.InvariantCulture, ", CONTACT a {0:0.0} s", contact * SampleSeconds) : "", masked));
                if (contact >= 0)
                {
                    result.Failures.Add(string.Format(CultureInfo.InvariantCulture,
                        "l'horaire trouve touche le robot a {0:0.0} s (incoherence interne de l'audit)", contact * SampleSeconds));
                }
            }
            if (w.HasLoad)
            {
                float fall = PathLoadFall(w, path, out float peak);
                int careful = 0;
                foreach (Node n in path)
                {
                    careful += n.Move && n.Careful ? 1 : 0;
                }
                if (fall >= 0f)
                {
                    result.Failures.Add(string.Format(CultureInfo.InvariantCulture,
                        "l'horaire trouve fait tomber la charge a {0:0.00} s (ecart {1:0.00} m/s ; incoherence interne de l'audit)", fall, peak));
                }
                else
                {
                    result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                        "charge : tenue sur tout l'horaire (ecart de vitesse au plus {0:0.00} m/s sur {1:0.0} s, sous {2:0.0}), {3} deplacement(s) de case prudent(s)",
                        peak, Tuning.LoadWindow, Tuning.LoadFallDeltaV, careful));
                }
            }
        }

        /// <summary>
        /// CONTRACT_M5 16.6: the cells of the platforms and ramps (inside a platform's rectangle, a ramp's footprint, or
        /// anywhere the floor is raised), barred to the player by the "split" lesson.
        /// </summary>
        private static bool[] PlatformCells(World w)
        {
            var barred = new bool[w.Count];
            for (int k = 0; k < w.Count; k++)
            {
                Vector3 c = w.Center[k];
                barred[k] = c.y > 1e-3f;
                foreach (PlatformDef p in w.Def.Platforms)
                {
                    barred[k] |= Mathf.Abs(c.x - p.X) <= p.SizeX * 0.5f && Mathf.Abs(c.z - p.Z) <= p.SizeZ * 0.5f;
                }
                foreach (RampDef r in w.Def.Ramps)
                {
                    Vector3 local = YawMath.Rotate(YawMath.Planar(c) - new Vector3(r.X, 0f, r.Z), -r.Yaw);
                    barred[k] |= Mathf.Abs(local.x) <= r.Width * 0.5f && Mathf.Abs(local.z) <= r.Length * 0.5f;
                }
            }
            return barred;
        }

        // ----- Self-test: fixtures that must fail (M2.2 c, M4 amendment 9.11) -----

        /// <summary>One self-test fixture: the strict search must find nothing, the relaxed one (only its rule relaxed) must find a schedule.</summary>
        private sealed class FixtureRule
        {
            public string Rule;
            public string Strict;
            public string Relaxed;
            public Func<SearchOptions> StrictOptions;
            public Func<SearchOptions> RelaxedOptions;
            /// <summary>The relaxed search runs in a world where nobody sits (the "sit" fixture).</summary>
            public bool RelaxedWithoutSitting;
            /// <summary>What the fixture's level must have for its rule to apply, or null when it has it.</summary>
            public Func<LevelDef, string> Premise;
            /// <summary>M5: the strict search runs on this variant of the world with these options (a table edit).</summary>
            public Func<World, LevelInstance, (World, SearchOptions)> StrictVariant;
            /// <summary>
            /// M5: a fixture about a check rather than a schedule: the failures of that check under the strict (true) or the
            /// relaxed (false) setting. The strict setting must fail, the relaxed one must pass.
            /// </summary>
            public Func<World, bool, List<string>> Check;
            /// <summary>
            /// M5 wave 5A.1: a check on the built level alone (the budgets), as <see cref="Check"/>, with no world built.
            /// </summary>
            public Func<LevelDef, LevelInstance, bool, List<string>> LevelCheck;
            /// <summary>
            /// M5 wave 5A.1: the fixture's id (and file name) when it is not "test_" + <see cref="Rule"/>: the audit agent's
            /// own fixtures are test levels of its own, test_m5_audit_* (CONTRACT_M5 11).
            /// </summary>
            public string Id;
        }

        /// <summary>The fixture's id: <see cref="FixtureRule.Id"/>, or "test_" + its rule.</summary>
        private static string FixtureId(FixtureRule rule)
        {
            return rule.Id ?? FixturePrefix + rule.Rule;
        }

        /// <summary>The fixture's level file: Resources/Levels/{id}.json (the levels agent writes the M5 ones).</summary>
        private static string FixtureFile(FixtureRule rule)
        {
            return Path.Combine(LevelsFolder, FixtureId(rule) + ".json");
        }

        private static readonly FixtureRule[] Fixtures =
        {
            new FixtureRule
            {
                Rule = "wait", Strict = "attente de 8 s au plus", Relaxed = "attente illimitee",
                StrictOptions = () => new SearchOptions(), RelaxedOptions = () => new SearchOptions { MaxRun = UnlimitedRun },
            },
            new FixtureRule
            {
                Rule = "noise", Strict = "bruit", Relaxed = "sans bruit",
                StrictOptions = () => new SearchOptions(), RelaxedOptions = () => new SearchOptions { Noise = false },
            },
            new FixtureRule
            {
                Rule = "creak", Strict = "grincement", Relaxed = "sans grincement",
                StrictOptions = () => new SearchOptions(), RelaxedOptions = () => new SearchOptions { GaugeCap = float.MaxValue },
            },
            new FixtureRule
            {
                Rule = "tip", Strict = "pleine vitesse, chaque arret renverse le tabouret", Relaxed = "mode prudent",
                StrictOptions = () => new SearchOptions { FullSpeed = true }, RelaxedOptions = () => new SearchOptions(),
                Premise = l => l.PlayerBody().Tips ? null : "le corps du joueur ne se renverse pas",
            },
            new FixtureRule
            {
                Rule = "dark", Strict = "lampe toujours allumee", Relaxed = "la lampe peut s'eteindre",
                StrictOptions = () => new SearchOptions { Toggles = false }, RelaxedOptions = () => new SearchOptions(),
                Premise = l => l.PlayerBody().HasLight ? null : "le corps du joueur n'a pas de lumiere",
            },
            new FixtureRule
            {
                Rule = "sit", Strict = "on s'assoit sur le joueur", Relaxed = "personne ne s'assoit",
                StrictOptions = () => new SearchOptions(), RelaxedOptions = () => new SearchOptions(), RelaxedWithoutSitting = true,
                Premise = l => l.Inhabitants.Exists(h => h.Stations.Exists(s => s.SitsOnPlayer)) ? null : "aucune station ne s'assoit sur le joueur",
            },
            // ----- M5 (CONTRACT_M5 10, CONTRACT_M5_v3 8 and 15.10) -----
            new FixtureRule
            {
                Rule = "door", Strict = "toutes les portes verrouillees", Relaxed = "la porte peut s'ouvrir",
                StrictVariant = (w, level) => (w, new SearchOptions { Doors = false }), RelaxedOptions = () => new SearchOptions(),
                Premise = l => l.Doors.Exists(d => d.Leaf == "closed") ? null : "aucune porte a battant fermee",
            },
            new FixtureRule
            {
                Rule = "pet", Strict = "le chien voit a 1.6 m", Relaxed = "le chien voit a 0.35 m",
                StrictVariant = (w, level) => (DogEyeVariant(w, level), new SearchOptions()), RelaxedOptions = () => new SearchOptions(),
                Premise = l => l.Inhabitants.Exists(h => h.Kind == PersonalityDef.Dog) ? null : "aucun chien",
            },
            new FixtureRule
            {
                Rule = "cross", Strict = "deux humains a 0.6 m au moins", Relaxed = "a 0.3 m au moins",
                Check = (w, strict) => CheckSeparation(w, strict ? Separation : RelaxedSeparation, new List<string>()),
                Premise = l => l.Inhabitants.FindAll(h => h.Kind != PersonalityDef.Dog).Count >= 2 ? null : "moins de deux humains",
            },
            new FixtureRule
            {
                Rule = "split", Strict = "plateforme et rampes interdites", Relaxed = "plateforme et rampes permises",
                StrictVariant = (w, level) => (w, new SearchOptions { Barred = PlatformCells(w) }), RelaxedOptions = () => new SearchOptions(),
                Premise = l => l.Platforms.Count > 0 ? null : "aucune plateforme",
            },
            // ----- M5 wave 5A.1 (CONTRACT_M5 17): the audit agent's own fixtures, one per rule of the fix wave -----
            new FixtureRule
            {
                Rule = "darkpass", Id = "test_m5_audit_darkpass",
                Strict = "seuls les habitants avec memoire, chacun a sa portee dans le noir",
                Relaxed = "tous les habitants, chien compris, a la portee par defaut",
                Check = DarkPassCheck,
                Premise = l => !l.PlayerBody().HasLight ? "le corps du joueur n'a pas de lumiere"
                    : !l.Inhabitants.Exists(h => h.Kind == PersonalityDef.Dog) ? "aucun chien"
                    : !l.Inhabitants.Exists(h => PersonalityDef.ForInhabitant(h).Memory && PersonalityDef.ForInhabitant(h).ViewRange < Tuning.ViewRange)
                        ? "aucun habitant avec memoire a portee plus courte que la portee par defaut" : null,
            },
            new FixtureRule
            {
                Rule = "drawcalls", Id = "test_m5_audit_drawcalls",
                Strict = "un draw call par emplacement de materiau", Relaxed = "un draw call par renderer",
                LevelCheck = (def, level, strict) => DrawBudgets(def, level, strict, true, null),
            },
            new FixtureRule
            {
                // The level is held to the materials it is built with (its cones all calm): only the dog's colour in play can
                // push it over. An exact count against the 24 budget would break on any palette change elsewhere.
                Rule = "conecolours", Id = "test_m5_audit_conecolours",
                Strict = "un materiau par couleur de cone, celle du chien comprise", Relaxed = "chaque cone compte le materiau calme de sa construction",
                LevelCheck = (def, level, strict) => DrawBudgets(def, level, true, strict, null, CountDraws(level, false).Materials),
                Premise = l => !l.Inhabitants.Exists(h => h.Kind == PersonalityDef.Dog) ? "aucun chien"
                    : !l.Inhabitants.Exists(h => h.Kind != PersonalityDef.Dog) ? "aucun humain (son cone calme)" : null,
            },
            // ----- M5 wave 5B (CONTRACT_M5 4, 5, 6, 10, 16.5, 16.8, 16.9): the levels agent's fixtures -----
            new FixtureRule
            {
                Rule = "robot", Strict = "le ronronnement du robot ne masque rien", Relaxed = "le ronronnement masque les petits bruits pres du robot",
                StrictOptions = () => new SearchOptions { Hum = false }, RelaxedOptions = () => new SearchOptions(),
                Premise = l => l.Robots != null && l.Robots.Count > 0 ? null : "aucun robot",
            },
            new FixtureRule
            {
                Rule = "rock", Strict = "chaque arret coute la bascule", Relaxed = "sans la bascule",
                StrictOptions = () => new SearchOptions(), RelaxedOptions = () => new SearchOptions { Rock = false },
                Premise = l => l.PlayerBody().Rocks ? null : "le corps du joueur ne bascule pas",
            },
            new FixtureRule
            {
                Rule = "load", Strict = "la regle de la charge", Relaxed = "sans la regle de la charge (pleine vitesse, la charge ne tombe jamais)",
                StrictOptions = () => new SearchOptions(), RelaxedOptions = () => new SearchOptions { LoadRule = false },
                Premise = l => !string.IsNullOrEmpty(l.Player?.Load) ? null : "le joueur ne porte rien",
            },
            new FixtureRule
            {
                Rule = "robotcontact", Id = "test_m5_levels_robotblock",
                Strict = "la zone de contact du robot", Relaxed = "sans robot (ni zone de contact ni ronronnement)",
                StrictOptions = () => new SearchOptions(), RelaxedOptions = () => new SearchOptions { Robots = false },
                Premise = l => l.Robots != null && l.Robots.Count > 0 ? null : "aucun robot",
            },
        };

        /// <summary>
        /// The test_m5_audit_darkpass fixture (CONTRACT_M5 17, m1): the dark lesson's free pass check on the fixture's
        /// schedule. Its only watcher within the default dark range of the lamp's path is the dog or a watcher beyond its
        /// own dark range, so the check must fail strict and pass relaxed. No schedule is a failure under both.
        /// </summary>
        private static List<string> DarkPassCheck(World w, bool strict)
        {
            NodeList nodes = Search(w, new SearchOptions { NeedDecoy = w.NeedDecoy }, out int goal);
            if (goal < 0)
            {
                return new List<string> { "aucun horaire : le chemin de la lampe n'existe pas" };
            }
            string failure = DarkFreePass(w, PathTo(nodes, goal), strict, out _);
            return failure != null ? new List<string> { failure } : new List<string>();
        }

        /// <summary>The ids of the self-test fixtures, in order.</summary>
        public static List<string> FixtureIds()
        {
            var ids = new List<string>();
            foreach (FixtureRule f in Fixtures)
            {
                ids.Add(FixtureId(f));
            }
            return ids;
        }

        /// <summary>
        /// Every fixture is a level built so that exactly one rule makes it impossible: "test_wait" (the only way needs
        /// a 9.5 s wait), "test_noise" (the only way passes behind an inhabitant on a hard floor), "test_creak" (the only
        /// way stops too much for the creak gauge), and M4: "test_tip" (the stool at full speed tips at every stop),
        /// "test_dark" (the lamp must cross a room dark), "test_sit" (a sitter pins the player longer than the wait
        /// cap allows). Each must have no schedule under its strict setting, and must get one when only its own rule is
        /// relaxed: the audit can fail, and fails for that reason. Returns false when a fixture misbehaves.
        /// </summary>
        public static bool RunFixtures()
        {
            return RunFixtures(null);
        }

        /// <summary>The self-test restricted to <paramref name="only"/> (fixture ids; null runs every fixture).</summary>
        private static bool RunFixtures(List<string> only)
        {
            bool ok = true;
            var sb = new StringBuilder();
            var selected = new List<FixtureRule>();
            foreach (FixtureRule rule in Fixtures)
            {
                if (only == null || only.Contains(FixtureId(rule)))
                {
                    selected.Add(rule);
                }
            }
            sb.AppendLine($"[LevelAudit] Auto-test : {selected.Count} niveaux qui doivent echouer, chacun pour sa regle");
            if (only != null)
            {
                foreach (string id in only)
                {
                    if (!FixtureIds().Contains(id))
                    {
                        ok = false;
                        sb.AppendLine($"  [DEFAUT] {id} : pas un niveau d'auto-test (connus : {string.Join(", ", FixtureIds())})");
                    }
                }
            }
            foreach (FixtureRule rule in selected)
            {
                string id = FixtureId(rule);
                string file = FixtureFile(rule);
                if (!File.Exists(file))
                {
                    ok = false;
                    sb.AppendLine($"  [DEFAUT] {id} : fichier {file} absent");
                    continue;
                }
                LevelDef def = LevelJson.Parse(File.ReadAllText(file));
                List<string> issues = LevelValidator.Validate(def);
                string premise = rule.Premise?.Invoke(def);
                if (issues.Count > 0 || premise != null)
                {
                    ok = false;
                    sb.AppendLine(issues.Count > 0 ? $"  [DEFAUT] {id} : niveau invalide : {issues[0]}" : $"  [DEFAUT] {id} : {premise}");
                    continue;
                }
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                LevelInstance level = LevelBuilder.Build(def);
                var clock = Stopwatch.StartNew();
                Budget.Begin();
                try
                {
                    Physics.SyncTransforms();
                    // A level check (the budgets) needs no world: none is built for it.
                    World w = rule.LevelCheck != null ? null : BuildWorld(def, level, true);
                    int strict = -1;
                    int loose = -1;
                    NodeList nodes = null;
                    List<string> strictFailures = null;
                    List<string> looseFailures = null;
                    if (rule.LevelCheck != null)
                    {
                        strictFailures = rule.LevelCheck(def, level, true);
                        looseFailures = rule.LevelCheck(def, level, false);
                    }
                    else if (!Budget.RaysExhausted && rule.Check != null)
                    {
                        strictFailures = rule.Check(w, true);
                        looseFailures = rule.Check(w, false);
                    }
                    else if (!Budget.RaysExhausted)
                    {
                        (World strictWorld, SearchOptions strictOptions) = rule.StrictVariant != null ? rule.StrictVariant(w, level) : (w, rule.StrictOptions());
                        Search(strictWorld, strictOptions, out strict);
                        World relaxedWorld = rule.RelaxedWithoutSitting ? BuildWorld(def, level, false) : w;
                        nodes = Search(relaxedWorld, rule.RelaxedOptions(), out loose);
                    }
                    string exhausted = Budget.Defect();
                    if (exhausted != null)
                    {
                        ok = false;
                        sb.AppendLine($"  [DEFAUT] {id} : {exhausted}");
                    }
                    else if (strictFailures != null)
                    {
                        if (strictFailures.Count == 0)
                        {
                            ok = false;
                            sb.AppendLine($"  [DEFAUT] {id} : l'audit ne trouve aucun defaut ({rule.Strict}) alors que ce niveau doit echouer");
                        }
                        else if (looseFailures.Count > 0)
                        {
                            ok = false;
                            sb.AppendLine($"  [DEFAUT] {id} : echoue, mais aussi sans la regle {rule.Rule} ({rule.Relaxed}) : {looseFailures[0]}");
                        }
                        else
                        {
                            sb.AppendLine($"  [ok] {id} : {strictFailures[0]} ({rule.Strict}) ; sans la regle {rule.Rule} ({rule.Relaxed}), aucun defaut");
                        }
                    }
                    else if (strict >= 0)
                    {
                        ok = false;
                        sb.AppendLine($"  [DEFAUT] {id} : l'audit trouve un horaire ({rule.Strict}) alors que ce niveau doit echouer");
                    }
                    else if (loose < 0)
                    {
                        ok = false;
                        sb.AppendLine($"  [DEFAUT] {id} : echoue, mais aussi sans la regle {rule.Rule} ({rule.Relaxed}) : il n'echoue pas pour la bonne raison");
                    }
                    else
                    {
                        sb.AppendLine(string.Format(CultureInfo.InvariantCulture, "  [ok] {0} : aucun horaire ({1}) ; sans la regle {2} ({3}), sortie a {4:0.0} s",
                            id, rule.Strict, rule.Rule, rule.Relaxed, nodes[loose].T * SampleSeconds));
                    }
                }
                finally
                {
                    LevelBuilder.Teardown(level);
                    var cost = new Result { LevelId = id, RuntimeSeconds = (float)clock.Elapsed.TotalSeconds, Nodes = Budget.Nodes, Rays = Budget.Rays };
                    sb.AppendLine($"  [temps] {id} : {Budget.RuntimeLine(cost)}");
                    Budget.Sight = null;
                }
            }
            if (ok)
            {
                Debug.Log(sb.ToString());
            }
            else
            {
                Debug.LogError(sb.ToString());
            }
            return ok;
        }

        private static World BuildWorld(LevelDef def, LevelInstance level, bool sitting)
        {
            float cell = Tuning.AuditCellSize;
            var w = new World { Def = def, Rooms = def.AllRooms(), Index = new Dictionary<(int, int, int), int>(), Sitting = sitting };
            w.Body = BodyModel.Of(def.PlayerBody());
            // M5 wave 5B: a load (never on the rocking chair nor the floor lamp, as GameState carries it) grows the sample box and
            // brings the load rule; a rocking body pays its rock at every stop (CONTRACT_M5 5, 6, 16.5, 16.9).
            BodyDef playerBody = w.Body.Body;
            w.HasLoad = def.Player != null && !string.IsNullOrEmpty(def.Player.Load) && LoadView.IsKind(def.Player.Load)
                && !playerBody.Rocks && !playerBody.HasLight;
            w.Body.LoadHeight = w.HasLoad ? Tuning.LoadHeight : 0f;
            w.RockSamples = playerBody.Rocks ? (MotionProfile.RockSteps(playerBody, false) + SampleSteps - 1) / SampleSteps : 0;
            w.Spawn = YawMath.Planar(def.Player.Position);
            // CONTRACT_M5 10: 300 s and a 3 s sweep step for every level but 1 to 7 and the M2/M4 fixtures.
            bool legacy = LegacyLevels.Contains(def.Id) || LegacyFixtures.Contains(def.Id);
            w.Horizon = legacy ? HorizonSamples : HorizonSamplesM5;
            w.SweepEvery = legacy ? SweepEvery : SweepEveryM5;
            var centers = new List<Vector3>();
            var rooms = new List<int>();
            var iis = new List<int>();
            var jjs = new List<int>();
            w.Size = new (int, int)[w.Rooms.Count];
            for (int r = 0; r < w.Rooms.Count; r++)
            {
                RoomDef room = w.Rooms[r];
                int nx = Mathf.Max(1, Mathf.RoundToInt(room.SizeX / cell));
                int nz = Mathf.Max(1, Mathf.RoundToInt(room.SizeZ / cell));
                w.Size[r] = (nx, nz);
                for (int i = 0; i < nx; i++)
                {
                    for (int j = 0; j < nz; j++)
                    {
                        w.Index[(r, i, j)] = centers.Count;
                        float x = room.MinX + (i + 0.5f) * cell;
                        float z = room.MinZ + (j + 0.5f) * cell;
                        // CONTRACT_M5_v3 15.4: the cell stands on the floor (a platform's height, a ramp's slope, else 0).
                        centers.Add(new Vector3(x, def.FloorHeightAt(x, z), z));
                        rooms.Add(r);
                        iis.Add(i);
                        jjs.Add(j);
                    }
                }
            }
            int n = w.Count = centers.Count;
            if (n > ushort.MaxValue || w.Horizon + 1000 > ushort.MaxValue)
            {
                throw new InvalidOperationException($"{def.Id}: {n} cells or a {w.Horizon} sample horizon do not fit a search node (ushort)");
            }
            w.Center = centers.ToArray();
            w.Room = rooms.ToArray();
            w.I = iis.ToArray();
            w.J = jjs.ToArray();
            w.Walkable = new bool[n];
            w.ExplainedAny = new bool[n];
            w.InExit = new bool[n];
            BodyModel body = w.Body;
            float cr = body.Radius;
            string kind = body.Body.Kind;
            foreach (DecoyDef d in def.Decoys)
            {
                w.NeedDecoy |= BodyKinds.Of(d.Kind) == kind;
            }

            // The watchers and their tolerance classes (CONTRACT_M5 3 and 16.3).
            int h = w.Inhabitants = def.Inhabitants.Count;
            w.Watchers = new Watcher[h];
            for (int i = 0; i < h; i++)
            {
                PersonalityDef p = PersonalityDef.ForInhabitant(def.Inhabitants[i]);
                w.Watchers[i] = new Watcher { Name = def.Inhabitants[i].Name, Personality = p, Human = p.CountsForCatch };
                if (w.Watchers[i].Human)
                {
                    w.Watchers[i].Class = ClassOf(w, p.Tolerance);
                }
            }
            if (w.Classes.Count == 0)
            {
                ClassOf(w, Tuning.DisplacementTolerance); // nobody remembers: the still rules never apply, but they exist
            }

            // The leaves (CONTRACT_M5_v3 3, 15.2): their colliders are left out of walkability, which the masks decide.
            CollectLeaves(w, def);
            var leafColliders = new List<Collider>();
            if (level.Root != null)
            {
                foreach (DoorLeaf leaf in level.Root.GetComponentsInChildren<DoorLeaf>(true))
                {
                    foreach (Collider c in leaf.GetComponentsInChildren<Collider>(true))
                    {
                        if (c.enabled)
                        {
                            leafColliders.Add(c);
                            c.enabled = false;
                        }
                    }
                }
            }
            var leafEdges = new List<(int a, int b, int leaf)>();
            try
            {
                for (int k = 0; k < n; k++)
                {
                    Vector3 c = w.Center[k];
                    w.Walkable[k] = !Physics.CheckCapsule(c + Vector3.up * (cr + 0.05f), c + Vector3.up * (body.Height - cr),
                        cr, Layers.ChairBlockerMask, QueryTriggerInteraction.Ignore);
                    w.InExit[k] = def.Exit.Contains(c);
                }

                // Neighbors: 4-connected inside a room, and across a doorway between two rooms, each move swept
                // by the body's capsule so a door jamb or a thin prop between two cells is never crossed. M5: the floor along
                // a move must be continuous (CONTRACT_M5 16.6: a ramp, never a platform edge).
                w.Neighbors = new List<int>[n];
                for (int k = 0; k < n; k++)
                {
                    w.Neighbors[k] = new List<int>(4);
                }
                for (int k = 0; k < n; k++)
                {
                    if (!w.Walkable[k])
                    {
                        continue;
                    }
                    foreach ((int di, int dj) in new[] { (1, 0), (0, 1) })
                    {
                        if (w.Index.TryGetValue((w.Room[k], w.I[k] + di, w.J[k] + dj), out int o) && w.Walkable[o] && Clear(body, w.Center[k], w.Center[o])
                            && FloorContinuous(def, w.Center[k], w.Center[o]))
                        {
                            w.Neighbors[k].Add(o);
                            w.Neighbors[o].Add(k);
                        }
                    }
                }
                float t = def.WallThickness();
                foreach (OpeningDef door in def.Doors)
                {
                    List<RoomSide> sides = def.SidesOf(door, out float along);
                    if (sides.Count != 2)
                    {
                        continue;
                    }
                    int closedLeaf = w.Closed.FindIndex(l => l.Door == door);
                    for (int a = 0; a < n; a++)
                    {
                        if (!w.Walkable[a] || w.Room[a] != sides[0].Room)
                        {
                            continue;
                        }
                        for (int b = 0; b < n; b++)
                        {
                            if (!w.Walkable[b] || w.Room[b] != sides[1].Room)
                            {
                                continue;
                            }
                            Vector3 d = w.Center[b] - w.Center[a];
                            float across = sides[0].AlongX ? Mathf.Abs(d.z) : Mathf.Abs(d.x);
                            float sideways = sides[0].AlongX ? Mathf.Abs(d.x) : Mathf.Abs(d.z);
                            float at = sides[0].AlongX ? w.Center[a].x : w.Center[a].z;
                            if (sideways < 1e-3f && across >= t - 1e-3f && across <= cell + t + 1e-3f
                                && Mathf.Abs(at - along) <= door.Width * 0.5f - cr + 1e-3f && Clear(body, w.Center[a], w.Center[b])
                                && FloorContinuous(def, w.Center[a], w.Center[b]))
                            {
                                w.Neighbors[a].Add(b);
                                w.Neighbors[b].Add(a);
                                if (closedLeaf >= 0)
                                {
                                    leafEdges.Add((a, b, closedLeaf));
                                }
                            }
                        }
                    }
                }
            }
            finally
            {
                foreach (Collider c in leafColliders)
                {
                    c.enabled = true;
                }
            }
            // Directed edges in neighbor order: the noise tables index the travel points of a move by edge.
            w.EdgeStart = new int[n + 1];
            for (int k = 0; k < n; k++)
            {
                w.EdgeStart[k + 1] = w.EdgeStart[k] + w.Neighbors[k].Count;
            }
            w.Edges = w.EdgeStart[n];
            SetUpMasks(w, level, leafEdges);
            RoomDef spawnRoom = def.RoomAt(def.Player.Position);
            w.Start = -1;
            float best = float.MaxValue;
            for (int k = 0; k < n; k++)
            {
                float dist = YawMath.Planar(w.Center[k] - def.Player.Position).magnitude;
                if (w.Walkable[k] && spawnRoom != null && w.Rooms[w.Room[k]] == spawnRoom && dist < best)
                {
                    best = dist;
                    w.Start = k;
                }
            }

            // The still rules of every tolerance class: explained by a decoy of the player's kind, in place at the spawn.
            w.SlotHomes.Add(YawMath.Planar(def.Player.Position));
            foreach (ToleranceClass c in w.Classes)
            {
                c.Explained = new bool[n];
                for (int k = 0; k < n; k++)
                {
                    foreach (DecoyDef d in def.Decoys)
                    {
                        bool sameKind = BodyKinds.Of(d.Kind) == kind;
                        c.Explained[k] |= sameKind && YawMath.Planar(w.Center[k] - d.Position).magnitude <= c.ExplainedRadius;
                    }
                    w.ExplainedAny[k] |= c.Explained[k];
                }
                c.InPlaceBySlot.Add(InPlaceAround(w, def.Player.Position, c.InPlaceRadius));
            }

            // The routines, built as the game builds them (RoutineFactory, CONTRACT_M5_v3 15.6) and stepped exactly as the
            // game steps them, sampled over the whole horizon (no loop assumed: what the search sees is what the game
            // plays). The seat check (SeatOccupied null) always finds the player home: the search forces it there.
            var routines = new List<InhabitantRoutine>();
            var seats = new SeatRegistry();
            int stationAreas = StationAreaMask(w);
            for (int i = 0; i < h; i++)
            {
                InhabitantRoutine routine = RoutineFactory.Create(def.Inhabitants[i], def, level.Planner, level.Planner, seats, i, stationAreas);
                routine.SittingEnabled = sitting;
                routines.Add(routine);
                w.Watchers[i].Range = routine.ViewRange;
                w.Watchers[i].HalfAngle = routine.HalfAngle;
                w.Watchers[i].HearingFactor = routine.HearingFactor;
                w.Wanders |= RoutinePatterns.Normalize(def.Inhabitants[i].Pattern) == RoutinePatterns.Wander;
            }
            int samples = w.Samples = w.Horizon + MarginSamples + 1;
            w.LoopSamples = w.Horizon;
            w.Position = new Vector3[samples, h];
            w.Eye = new Vector3[samples * h];
            w.Forward = new Vector3[samples * h];
            w.Asleep = new bool[samples * h];
            w.Sits = new bool[samples * h];
            w.HearingFactor = new float[h];
            for (int i = 0; i < h; i++)
            {
                w.HearingFactor[i] = w.Watchers[i].HearingFactor;
            }
            w.Forced = new bool[samples];
            w.ForcedSeat = new int[samples];
            w.Pinned = new bool[samples];
            w.Slot = new int[samples];
            // M5 wave 5B (CONTRACT_M5 4, 16.8): the robots' fixed timelines, at the game's time of each sample (step 5 s, k * dt).
            if (def.Robots != null)
            {
                foreach (RobotDef robot in def.Robots)
                {
                    if (robot != null)
                    {
                        var robotPath = new RobotPath(robot);
                        w.RobotPaths.Add(robotPath);
                        w.RobotSpeed = Mathf.Max(w.RobotSpeed, robotPath.Speed);
                    }
                }
            }
            w.Robots = w.RobotPaths.Count;
            w.RobotAt = new Vector3[samples * w.Robots];
            for (int s = 0; s < samples; s++)
            {
                for (int r = 0; r < w.Robots; r++)
                {
                    w.RobotAt[s * w.Robots + r] = YawMath.Planar(w.RobotPaths[r].PositionAt(s * SampleSteps * Tuning.FixedStep));
                }
            }
            w.ContactBase = Tuning.RobotRadius + new Vector2(playerBody.Size.x, playerBody.Size.z).magnitude * 0.5f + ReleaseTolerance;
            var rings = w.Rings = new Vector3[n][];
            // CONTRACT_M5 16.5: with a load, the top samples rise by its height and the center by half of it (Vision.Step).
            float top = body.SampleHeight - Tuning.SampleInset;
            for (int k = 0; k < n; k++)
            {
                rings[k] = new Vector3[RingCount + 1];
                rings[k][0] = w.Center[k] + Vector3.up * (body.SampleHeight * 0.5f);
                for (int a = 0; a < RingCount; a++)
                {
                    rings[k][a + 1] = w.Center[k] + YawMath.Forward(a * 360f / RingCount) * body.RingRadius + Vector3.up * top;
                }
            }
            var period = new int[h];
            for (int i = 0; i < h; i++)
            {
                period[i] = -1;
            }
            int slot = 0;
            for (int s = 0; s < samples; s++)
            {
                bool forced = false;
                bool pinned = false;
                int seat = -1;
                void Watch()
                {
                    foreach (InhabitantRoutine r in routines)
                    {
                        if (r.SittingOnPlayer && r.JustSat)
                        {
                            // CONTRACT_M4 3: after a sit on the player, the player's slot is the seat home.
                            slot = SlotOf(w, r.SeatHome.Position);
                        }
                        // CONTRACT_M4 10.1: the game checks the seat at the moment of sitting, not during the approach.
                        // From that moment to the end of the pin the player must be on the seat.
                        if (r.SittingOnPlayer) // MUTATION:AUDIT_SIT_MOMENT
                        {
                            forced = true;
                            seat = SeatOf(w, r.SeatHome.Position);
                        }
                        pinned |= r.SittingOnPlayer;
                    }
                }
                if (s == 0)
                {
                    Watch();
                }
                else
                {
                    for (int step = 0; step < SampleSteps; step++)
                    {
                        foreach (InhabitantRoutine r in routines)
                        {
                            r.Step(Tuning.FixedStep);
                        }
                        Watch();
                    }
                }
                w.Forced[s] = forced;
                w.ForcedSeat[s] = seat;
                if (forced && w.FirstSit < 0)
                {
                    w.FirstSit = s;
                }
                w.Pinned[s] = pinned;
                w.Slot[s] = slot;
                for (int i = 0; i < h; i++)
                {
                    InhabitantRoutine r = routines[i];
                    if (period[i] < 0 && LoopDone(r, def.Inhabitants[i]))
                    {
                        period[i] = s;
                    }
                    w.Position[s, i] = YawMath.Planar(r.Position);
                    w.Eye[s * h + i] = r.EyePosition;
                    w.Forward[s * h + i] = r.EyeForward;
                    w.Asleep[s * h + i] = r.Asleep;
                    w.Sits[s * h + i] = r.IsSitting;
                }
            }
            // CONTRACT_M5 16.3: the loop is the longest routine's period; a wanderer never loops (no sweep).
            if (w.Wanders)
            {
                w.LoopSamples = 0;
            }
            else
            {
                for (int i = 0; i < h; i++)
                {
                    w.LoopSamples = i == 0 ? (period[i] < 0 ? w.Horizon : period[i]) : Mathf.Max(w.LoopSamples, period[i] < 0 ? w.Horizon : period[i]);
                }
            }
            ShareStillTables(w);
            ComputeSight(w, level, false);
            ComputeLeafSight(w, level);
            SetMargin(w, MarginSamples);
            return w;
        }

        /// <summary>The routine has done one full period: a loop is back at its start (M4), pingpong has come back there and back.</summary>
        private static bool LoopDone(InhabitantRoutine r, InhabitantDef def)
        {
            if (RoutinePatterns.Normalize(def.Pattern) == RoutinePatterns.PingPong)
            {
                return r.InDwell && r.VisitIndex >= Mathf.Max(1, 2 * (def.Stations.Count - 1));
            }
            return r.LoopsCompleted >= 1;
        }

        /// <summary>The tolerance class of a tolerance, added the first time (CONTRACT_M5 16.3: one per distinct tolerance).</summary>
        private static int ClassOf(World w, float tolerance)
        {
            for (int c = 0; c < w.Classes.Count; c++)
            {
                if (w.Classes[c].Tolerance == tolerance)
                {
                    return c;
                }
            }
            // The M2 radii for the M2 tolerance exactly; the same derivation for the others.
            bool m2 = tolerance == Tuning.DisplacementTolerance;
            float explained = tolerance - ReleaseTolerance - ToleranceMargin;
            w.Classes.Add(new ToleranceClass
            {
                Tolerance = tolerance,
                ExplainedRadius = m2 ? ExplainedRadius : explained,
                InPlaceRadius = m2 ? InPlaceRadius : explained * 0.5f,
            });
            return w.Classes.Count - 1;
        }

        /// <summary>
        /// On a level whose watchers are all humans of one tolerance (levels 1 to 7), the still table of that class is the
        /// moving table itself; otherwise every class gets its own tables.
        /// </summary>
        private static void ShareStillTables(World w)
        {
            int masks = w.Masks;
            int size = w.Samples * w.Count;
            bool[][] Tables()
            {
                var tables = new bool[masks][];
                for (int m = 0; m < masks; m++)
                {
                    tables[m] = new bool[size];
                }
                return tables;
            }
            // Without a lamp nothing is ever dark: the dark tables are the lit ones (half the memory, the same answers).
            bool lamp = w.Body.Lamp;
            w.MoveSeen = Tables();
            w.MoveDark = lamp ? Tables() : w.MoveSeen;
            bool shared = w.Classes.Count == 1 && Array.TrueForAll(w.Watchers, x => x.Human);
            foreach (ToleranceClass c in w.Classes)
            {
                c.Seen = shared ? w.MoveSeen : Tables();
                c.SeenDark = shared ? w.MoveDark : lamp ? Tables() : c.Seen;
            }
        }

        /// <summary>The leaves of the level, in level order; closed ones get a mask bit (CONTRACT_M5_v3 15.3).</summary>
        private static void CollectLeaves(World w, LevelDef def)
        {
            foreach (OpeningDef door in def.Doors)
            {
                if (string.IsNullOrEmpty(door.Leaf))
                {
                    continue;
                }
                var leaf = new Leaf
                {
                    Door = door,
                    Geometry = new DoorGeometry(def, door),
                    Closed = door.Leaf == "closed",
                    Area = Tuning.DoorAreaBase + w.Leaves.Count,
                };
                // Every pose of the leaf lies in its quarter disc of radius the width, hinged at either end, on either side.
                Vector3 c = leaf.Geometry.Center;
                c.y = def.FloorHeightAt(c.x, c.z);
                leaf.Swing = new Bounds(c + Vector3.up * (door.Top * 0.5f), new Vector3(door.Width * 2f + 0.2f, door.Top + 0.2f, door.Width * 2f + 0.2f));
                w.Leaves.Add(leaf);
                if (leaf.Closed)
                {
                    leaf.Bit = 1 << w.Closed.Count;
                    w.Closed.Add(leaf);
                }
            }
            w.Masks = 1 << w.Closed.Count;
        }

        /// <summary>
        /// The per mask rules (CONTRACT_M5_v3 15.3): a closed leaf blocks its doorway's moves until it is open; every leaf,
        /// posed as the mask poses it (DoorLeaf.PoseAt: closed in place, open against the end of its opening), blocks the
        /// cells the body would overlap and the moves whose sweep would meet it, measured on the real colliders as the M2
        /// walkability is (the body's capsule, the 0.98 sweep radius of <see cref="Clear"/> for both); then the reach cells
        /// of every closed leaf. Only what the open leaf occupies is blocked, never its whole swing sector, which holds the
        /// doorway itself (the sector is the validator's clearance zone and the reach exclusion).
        /// </summary>
        private static void SetUpMasks(World w, LevelInstance level, List<(int a, int b, int leaf)> leafEdges)
        {
            if (w.Leaves.Count == 0)
            {
                return;
            }
            w.EdgeLeaf = new int[w.Edges];
            for (int e = 0; e < w.Edges; e++)
            {
                w.EdgeLeaf[e] = -1;
            }
            foreach ((int a, int b, int leaf) in leafEdges)
            {
                w.EdgeLeaf[w.EdgeStart[a] + w.Neighbors[a].IndexOf(b)] = leaf;
                w.EdgeLeaf[w.EdgeStart[b] + w.Neighbors[b].IndexOf(a)] = leaf;
            }
            BodyModel body = w.Body;
            float sweep = body.Radius * 0.98f;
            w.Blocked = new bool[w.Masks][];
            w.EdgeBlocked = new bool[w.Masks][];
            try
            {
                for (int m = 0; m < w.Masks; m++)
                {
                    PoseLeaves(w, level, m, -1);
                    bool[] cells = w.Blocked[m] = new bool[w.Count];
                    bool[] edges = w.EdgeBlocked[m] = new bool[w.Edges];
                    for (int k = 0; k < w.Count; k++)
                    {
                        // The walkability and the neighbours were measured with every leaf collider off: a hit now is a leaf.
                        Vector3 c = w.Center[k];
                        cells[k] = w.Walkable[k] && Physics.CheckCapsule(c + Vector3.up * (body.Radius + 0.05f), c + Vector3.up * (body.Height - body.Radius),
                            sweep, Layers.ChairBlockerMask, QueryTriggerInteraction.Ignore);
                    }
                    for (int k = 0; k < w.Count; k++)
                    {
                        List<int> next = w.Neighbors[k];
                        for (int j = 0; j < next.Count; j++)
                        {
                            edges[w.EdgeStart[k] + j] = !Clear(body, w.Center[k], w.Center[next[j]]);
                        }
                    }
                }
            }
            finally
            {
                PoseLeaves(w, level, 0, -1); // the level as built
            }
            Vector3 size = body.Body.Size;
            foreach (Leaf leaf in w.Closed)
            {
                for (int k = 0; k < w.Count; k++)
                {
                    if (w.Walkable[k] && w.FreeIn(0, k) && w.FreeIn(leaf.Bit, k) && ReachableFrom(leaf, w.Center[k], size, body.Radius))
                    {
                        leaf.Reach.Add(k);
                    }
                }
                leaf.Samples = new Vector3[OpenSamples][];
                for (int q = 1; q <= OpenSamples; q++)
                {
                    leaf.Samples[q - 1] = leaf.Geometry.Samples(Tuning.DoorSwingDegrees * q / OpenSamples) ?? new Vector3[0];
                }
            }
            w.ReachBits = new int[w.Count];
            foreach (Leaf leaf in w.Closed)
            {
                foreach (int k in leaf.Reach)
                {
                    w.ReachBits[k] |= leaf.Bit;
                }
            }
        }

        // The replay releases the furniture within this of a waypoint (RouteReplayer), so a reach cell holds for every
        // position that close to its center.
        private static readonly Vector3[] ReleaseOffsets =
        {
            Vector3.zero, new Vector3(ReleaseTolerance, 0f, 0f), new Vector3(-ReleaseTolerance, 0f, 0f),
            new Vector3(0f, 0f, ReleaseTolerance), new Vector3(0f, 0f, -ReleaseTolerance),
        };

        /// <summary>
        /// A reach cell (CONTRACT_M5_v3 15.2, DoorGeometry.InReach): from the cell center and from every point within the
        /// replay's release of it, at every right angle yaw (no facing condition, and a replay arrives at any of them), the
        /// leaf is in reach. A point the furniture cannot stand on, because its body would cross the wall line where the closed
        /// leaf or the wall stops it, is skipped: the release never puts it there.
        /// </summary>
        private static bool ReachableFrom(Leaf leaf, Vector3 center, Vector3 size, float radius)
        {
            DoorGeometry g = leaf.Geometry;
            float stop = radius + Tuning.LeafThickness * 0.5f;
            float side = Vector3.Dot(YawMath.Planar(center - g.Hinge), g.Into);
            foreach (Vector3 offset in ReleaseOffsets)
            {
                Vector3 p = center + offset;
                float across = Vector3.Dot(YawMath.Planar(p - g.Hinge), g.Into);
                if (offset != Vector3.zero && Mathf.Abs(across) < stop && Mathf.Abs(across) < Mathf.Abs(side))
                {
                    continue;
                }
                for (int yaw = 0; yaw < 360; yaw += 90)
                {
                    if (!g.InReach(p, size, yaw))
                    {
                        return false;
                    }
                }
            }
            return true;
        }

        /// <summary>
        /// The NavMesh areas the station walks are planned with (CONTRACT_M5_v3 15.1): every area but the closed leaves'
        /// (RoutineFactory.AllAreas when there is none).
        /// </summary>
        private static int StationAreaMask(World w)
        {
            if (w.Closed.Count == 0)
            {
                return RoutineFactory.AllAreas;
            }
            int mask = RoutineFactory.AllAreas;
            foreach (Leaf leaf in w.Closed)
            {
                mask &= ~(1 << leaf.Area);
            }
            return mask;
        }

        /// <summary>The NavMesh areas with every leaf closed (the station walk check, CONTRACT_M5 16.7).</summary>
        private static int AllLeavesClosedMask(LevelDef def)
        {
            int mask = RoutineFactory.AllAreas;
            int leaves = 0;
            foreach (OpeningDef door in def.Doors)
            {
                if (!string.IsNullOrEmpty(door.Leaf))
                {
                    mask &= ~(1 << (Tuning.DoorAreaBase + leaves++));
                }
            }
            return mask;
        }

        /// <summary>
        /// CONTRACT_M5 16.6: the floor along a move is continuous with a slope of at most Tuning.RampMaxSlope (a ramp); a
        /// height discontinuity (a platform edge) forbids it. Always true on a flat level.
        /// </summary>
        private static bool FloorContinuous(LevelDef def, Vector3 a, Vector3 b)
        {
            float step = YawMath.Planar(b - a).magnitude / FloorProbeSteps;
            float rise = Mathf.Tan(Tuning.RampMaxSlope * Mathf.Deg2Rad) * step + 0.01f;
            float previous = def.FloorHeightAt(a.x, a.z);
            for (int i = 1; i <= FloorProbeSteps; i++)
            {
                Vector3 p = Vector3.Lerp(a, b, i / (float)FloorProbeSteps);
                float height = def.FloorHeightAt(p.x, p.z);
                if (Mathf.Abs(height - previous) > rise)
                {
                    return false;
                }
                previous = height;
            }
            return true;
        }

        /// <summary>
        /// Fills the sight tables from the stepped eyes, per watcher and per mask (CONTRACT_M5 16.3, CONTRACT_M5_v3 8). A cell
        /// is seen at a sample when one of its sample points is in a watcher's cone (its own range and half angle) and not
        /// occluded; switched off, the lamp's own samples are seen within each watcher's dark range only (CONTRACT_M4 2.3). A
        /// sleeping eye sees nothing. Every awake watcher writes the moving table; humans also write their class's still
        /// table. Occlusion comes from the level's <see cref="SightCache"/>: samples are processed in chunks, the chunk's
        /// missing rays are cast in one go, then the chunk is evaluated. <paramref name="moveOnly"/> recomputes only the moving
        /// table (a lesson variant: the still tables are kept).
        /// </summary>
        private static void ComputeSight(World w, LevelInstance level, bool moveOnly)
        {
            int n = w.Count;
            int h = w.Inhabitants;
            bool lamp = w.Body.Lamp;
            SightCache cache = CacheFor(w, level);
            int ring = cache.Ring;
            // Every sample point of a cell lies within this of the cell's center sample (Rings[k][0]): a cell farther than the
            // range plus this from the eye has no point in the cone (VisionMath.IsInCone rejects past the range first).
            float reachBound = Mathf.Sqrt(w.Body.RingRadius * w.Body.RingRadius + Mathf.Pow(w.Body.SampleHeight * 0.5f - Tuning.SampleInset, 2f)) + 1e-3f;
            var entries = new int[w.Samples * h];
            for (int mask = 0; mask < w.Masks; mask++)
            {
                bool[] move = w.MoveSeen[mask];
                bool[] moveDark = w.MoveDark[mask];
                int from = 0;
                for (int s = 0; s < w.Samples; s++)
                {
                    // Collect: the points this sample's cones need and the cache does not know yet.
                    for (int i = 0; i < h; i++)
                    {
                        int at = s * h + i;
                        if (w.Asleep[at])
                        {
                            continue;
                        }
                        Vector3 eye = w.Eye[at];
                        Vector3 forward = w.Forward[at];
                        float range = w.Watchers[i].Range;
                        float halfAngle = w.Watchers[i].HalfAngle;
                        int e = entries[at] = cache.Entry(eye, mask);
                        for (int k = 0; k < n; k++)
                        {
                            if (!w.Walkable[k] || (w.Rings[k][0] - eye).magnitude > range + reachBound)
                            {
                                continue;
                            }
                            int b = k * ring;
                            if (!lamp && cache.AnyKnownVisible(e, b, ring, eye, forward, range, halfAngle))
                            {
                                continue;
                            }
                            for (int a = 0; a < ring; a++)
                            {
                                if (VisionMath.IsInCone(eye, forward, cache.Points[b + a], range, halfAngle))
                                {
                                    cache.Need(e, b + a);
                                }
                            }
                        }
                    }
                    if (cache.Pending < RayBatch && s + 1 < w.Samples)
                    {
                        continue;
                    }
                    if (!cache.Flush())
                    {
                        return; // the ray budget is spent: the level fails for it (Budget.End)
                    }
                    // Evaluate the chunk.
                    for (int q = from; q <= s; q++)
                    {
                        for (int i = 0; i < h; i++)
                        {
                            int at = q * h + i;
                            if (w.Asleep[at])
                            {
                                continue;
                            }
                            Watcher watcher = w.Watchers[i];
                            bool[] still = !moveOnly && watcher.Human ? w.Classes[watcher.Class].Seen[mask] : null;
                            bool[] stillDark = !moveOnly && watcher.Human ? w.Classes[watcher.Class].SeenDark[mask] : null;
                            Vector3 eye = w.Eye[at];
                            Vector3 forward = w.Forward[at];
                            float range = watcher.Range;
                            float halfAngle = watcher.HalfAngle;
                            float darkRange = range * Tuning.LampOffLight;
                            int e = entries[at];
                            for (int k = 0; k < n; k++)
                            {
                                int index = q * n + k;
                                bool done = move[index] && (!lamp || moveDark[index]) && (still == null || (still[index] && (!lamp || stillDark[index])));
                                if (!w.Walkable[k] || done || (w.Rings[k][0] - eye).magnitude > range + reachBound)
                                {
                                    continue;
                                }
                                int b = k * ring;
                                bool seen = false;
                                bool dark = false;
                                for (int a = 0; a < ring; a++)
                                {
                                    Vector3 p = cache.Points[b + a];
                                    if (VisionMath.IsInCone(eye, forward, p, range, halfAngle) && cache.Visible(e, b + a))
                                    {
                                        seen = true;
                                        // CONTRACT_M4 2.3: switched off, the lamp's own samples are seen within the dark range only.
                                        dark |= lamp && VisionMath.IsInCone(eye, forward, p, darkRange, halfAngle);
                                        if (!lamp || dark)
                                        {
                                            break;
                                        }
                                    }
                                }
                                if (seen)
                                {
                                    move[index] = true;
                                    moveDark[index] |= dark;
                                    if (still != null)
                                    {
                                        still[index] = true;
                                        stillDark[index] |= dark;
                                    }
                                }
                            }
                        }
                    }
                    from = s + 1;
                }
            }
        }

        /// <summary>The level's occlusion cache for this world's sample points (the cell rings, then every leaf sample).</summary>
        private static SightCache CacheFor(World w, LevelInstance level)
        {
            var extra = new List<Vector3>();
            var owner = new List<int>();
            for (int l = 0; l < w.Closed.Count; l++)
            {
                Leaf leaf = w.Closed[l];
                foreach (Vector3[] points in leaf.Samples)
                {
                    foreach (Vector3 p in points)
                    {
                        extra.Add(p);
                        owner.Add(l);
                    }
                }
            }
            SightCache cache = Budget.Sight;
            if (cache == null || !cache.Matches(w.Rings, extra))
            {
                cache = Budget.Sight = new SightCache(w.Rings, extra, owner, w.Closed.ConvertAll(l => l.Swing));
            }
            cache.Pose = (mask, exclude) => PoseLeaves(w, level, mask, exclude);
            return cache;
        }

        /// <summary>
        /// Poses every leaf of the level for a mask with <see cref="DoorLeaf.PoseAt"/> (the one pose DoorLeaf, the validator
        /// and the audit share, DoorGeometry.Pose: closed in place, open against the end of its opening), switches off the
        /// colliders of the excluded closed leaf (a leaf never hides its own samples) and keeps the others on; PoseAt syncs
        /// the physics. Mask 0 with no exclusion is the level as built (authored open leaves open, the others closed).
        /// </summary>
        private static void PoseLeaves(World w, LevelInstance level, int mask, int exclude)
        {
            if (w.Leaves.Count == 0)
            {
                return;
            }
            foreach (DoorLeaf view in level.Leaves)
            {
                Leaf leaf = view != null ? w.Leaves.Find(l => l.Door.Id == view.Id) : null;
                if (leaf == null)
                {
                    continue;
                }
                bool open = !leaf.Closed || (mask & leaf.Bit) != 0;
                bool on = exclude < 0 || w.Closed.IndexOf(leaf) != exclude;
                foreach (Collider c in view.GetComponentsInChildren<Collider>(true))
                {
                    c.enabled = on;
                }
                view.PoseAt(open ? Tuning.DoorSwingDegrees : 0f);
            }
        }

        /// <summary>
        /// CONTRACT_M5_v3 15.2 and 15.3: during an opening the leaf's samples at each sample's swing angle join the chair's.
        /// [q - 1][mask * Samples + s]: a sample of the leaf at opening sample q is seen at s by a moving watcher (humans and
        /// the awake dog), occluded in the mask after the opening, the leaf itself left out.
        /// </summary>
        private static void ComputeLeafSight(World w, LevelInstance level)
        {
            if (w.Closed.Count == 0)
            {
                return;
            }
            int h = w.Inhabitants;
            SightCache cache = CacheFor(w, level);
            int first = w.Count * cache.Ring;
            w.LeafSeen = new bool[w.Closed.Count][][];
            for (int l = 0; l < w.Closed.Count; l++)
            {
                w.LeafSeen[l] = new bool[OpenSamples][];
                for (int q = 0; q < OpenSamples; q++)
                {
                    w.LeafSeen[l][q] = new bool[w.Samples * w.Masks];
                }
            }
            for (int pass = 0; pass < 2; pass++)
            {
                int point = first;
                for (int l = 0; l < w.Closed.Count; l++)
                {
                    Leaf leaf = w.Closed[l];
                    for (int q = 0; q < OpenSamples; q++)
                    {
                        int count = leaf.Samples[q].Length;
                        for (int mask = 0; mask < w.Masks; mask++)
                        {
                            if ((mask & leaf.Bit) == 0)
                            {
                                continue;
                            }
                            for (int s = 0; s < w.Samples; s++)
                            {
                                for (int i = 0; i < h; i++)
                                {
                                    int at = s * h + i;
                                    if (w.Asleep[at])
                                    {
                                        continue;
                                    }
                                    Vector3 eye = w.Eye[at];
                                    int e = cache.Entry(eye, mask);
                                    for (int j = 0; j < count; j++)
                                    {
                                        if (!VisionMath.IsInCone(eye, w.Forward[at], cache.Points[point + j], w.Watchers[i].Range, w.Watchers[i].HalfAngle))
                                        {
                                            continue;
                                        }
                                        if (pass == 0)
                                        {
                                            cache.Need(e, point + j);
                                        }
                                        else if (cache.Visible(e, point + j))
                                        {
                                            w.LeafSeen[l][q][s * w.Masks + mask] = true;
                                        }
                                    }
                                }
                            }
                        }
                        point += count;
                    }
                }
                if (pass == 0 && !cache.Flush())
                {
                    return;
                }
            }
        }

        /// <summary>
        /// A lesson variant as a table edit (CONTRACT_M5 16.3): the same world with every dog's eye raised to the human eye
        /// height ("pet": no schedule if the dog saw from 1.6 m). Only the moving tables are recomputed; the still tables, the
        /// noise and the routines are the world's.
        /// </summary>
        private static World DogEyeVariant(World w, LevelInstance level)
        {
            World v = w.Clone();
            int h = w.Inhabitants;
            v.Eye = (Vector3[])w.Eye.Clone();
            for (int i = 0; i < h; i++)
            {
                Watcher watcher = w.Watchers[i];
                if (watcher.Human)
                {
                    continue;
                }
                float lift = Tuning.EyeHeight - watcher.Personality.EyeHeight;
                for (int s = 0; s < w.Samples; s++)
                {
                    v.Eye[s * h + i] += Vector3.up * lift;
                }
            }
            int size = w.Samples * w.Count;
            v.MoveSeen = new bool[w.Masks][];
            v.MoveDark = w.Body.Lamp ? new bool[w.Masks][] : v.MoveSeen;
            for (int m = 0; m < w.Masks; m++)
            {
                v.MoveSeen[m] = new bool[size];
                if (w.Body.Lamp)
                {
                    v.MoveDark[m] = new bool[size];
                }
            }
            ComputeSight(v, level, true);
            ComputeLeafSight(v, level);
            SetMargin(v, w.Margin);
            return v;
        }

        /// <summary>
        /// Design aid ("-checkSight"): the sight tables recomputed as M4 computed them, one Physics.Raycast per point from the
        /// exact eye of every sample (mask 0, every watcher), compared with the cached moving table. None is expected.
        /// </summary>
        private static string CheckSight(World w, LevelInstance level)
        {
            int n = w.Count;
            int h = w.Inhabitants;
            bool lamp = w.Body.Lamp;
            int seenDiff = 0;
            int darkDiff = 0;
            long rays = 0;
            int first = -1;
            for (int s = 0; s < w.Samples; s++)
            {
                for (int k = 0; k < n; k++)
                {
                    bool seen = false;
                    bool dark = false;
                    for (int i = 0; i < h && w.Walkable[k] && !(seen && (!lamp || dark)); i++)
                    {
                        if (w.Asleep[s * h + i])
                        {
                            continue;
                        }
                        Vector3 eye = w.Eye[s * h + i];
                        Vector3 forward = w.Forward[s * h + i];
                        float range = w.Watchers[i].Range;
                        float halfAngle = w.Watchers[i].HalfAngle;
                        foreach (Vector3 p in w.Rings[k])
                        {
                            if (VisionMath.IsInCone(eye, forward, p, range, halfAngle) && ++rays > 0 && !Vision.Occluded(eye, p))
                            {
                                seen = true;
                                dark |= lamp && VisionMath.IsInCone(eye, forward, p, range * Tuning.LampOffLight, halfAngle);
                                if (!lamp || dark)
                                {
                                    break;
                                }
                            }
                        }
                    }
                    if (seen != w.MoveSeen[0][s * n + k])
                    {
                        seenDiff++;
                        first = first < 0 ? s : first;
                    }
                    if (lamp && dark != w.MoveDark[0][s * n + k])
                    {
                        darkDiff++;
                        first = first < 0 ? s : first;
                    }
                }
            }
            return string.Format(CultureInfo.InvariantCulture,
                "controle de la vue (-checkSight) : {0} ecart(s) de vue et {1} de vue dans le noir sur {2} cases-echantillons{3} ; {4} rayons directs contre {5} rayons du cache ({6} yeux)",
                seenDiff, darkDiff, (long)w.Samples * n, first >= 0 ? string.Format(CultureInfo.InvariantCulture, ", le premier a {0:0.0} s", first * SampleSeconds) : "",
                rays, Budget.Rays, Budget.Sight != null ? Budget.Sight.Entries : 0);
        }

        /// <summary>Recomputes every table dilated by the margin (sight, dark sight, the leaves, the sitter's pin) for a new margin.</summary>
        private static void SetMargin(World w, int margin)
        {
            w.Margin = margin;
            int samples = w.Samples;
            w.MoveSeenWide = new bool[w.Masks][];
            w.MoveDarkWide = w.MoveDark == w.MoveSeen ? w.MoveSeenWide : new bool[w.Masks][];
            for (int m = 0; m < w.Masks; m++)
            {
                w.MoveSeenWide[m] = Dilate(w.MoveSeen[m], samples, w.Count, margin);
                if (w.MoveDarkWide != w.MoveSeenWide)
                {
                    w.MoveDarkWide[m] = Dilate(w.MoveDark[m], samples, w.Count, margin);
                }
            }
            foreach (ToleranceClass c in w.Classes)
            {
                if (c.Seen == w.MoveSeen)
                {
                    c.SeenWide = w.MoveSeenWide;
                    c.SeenDarkWide = w.MoveDarkWide;
                    continue;
                }
                c.SeenWide = new bool[w.Masks][];
                c.SeenDarkWide = c.SeenDark == c.Seen ? c.SeenWide : new bool[w.Masks][];
                for (int m = 0; m < w.Masks; m++)
                {
                    c.SeenWide[m] = Dilate(c.Seen[m], samples, w.Count, margin);
                    if (c.SeenDarkWide != c.SeenWide)
                    {
                        c.SeenDarkWide[m] = Dilate(c.SeenDark[m], samples, w.Count, margin);
                    }
                }
            }
            if (w.LeafSeen != null)
            {
                w.LeafSeenWide = new bool[w.Closed.Count][][];
                for (int l = 0; l < w.Closed.Count; l++)
                {
                    w.LeafSeenWide[l] = new bool[OpenSamples][];
                    for (int q = 0; q < OpenSamples; q++)
                    {
                        w.LeafSeenWide[l][q] = Dilate(w.LeafSeen[l][q], samples, w.Masks, margin);
                    }
                }
            }
            foreach (NoiseTable table in w.Noise.Values)
            {
                table.Widen(w);
            }
            w.ForcedWide = new bool[samples];
            w.ForcedSeatWide = new int[samples];
            for (int s = 0; s < samples; s++)
            {
                w.ForcedSeatWide[s] = -1;
                for (int q = Mathf.Max(0, s - margin); q <= Mathf.Min(samples - 1, s + margin); q++)
                {
                    if (w.Forced[q])
                    {
                        w.ForcedWide[s] = true;
                        if (w.ForcedSeatWide[s] < 0)
                        {
                            w.ForcedSeatWide[s] = w.ForcedSeat[q];
                        }
                    }
                }
            }
        }

        /// <summary>Cells whose center stands within <paramref name="radius"/> of <paramref name="home"/>.</summary>
        private static bool[] InPlaceAround(World w, Vector3 home, float radius)
        {
            var inPlace = new bool[w.Count];
            for (int k = 0; k < w.Count; k++)
            {
                inPlace[k] = YawMath.Planar(w.Center[k] - home).magnitude <= radius;
            }
            return inPlace;
        }

        /// <summary>The slot index of a seat home (a new slot the first time, for every class); slot 0 is the spawn.</summary>
        private static int SlotOf(World w, Vector3 home)
        {
            home = YawMath.Planar(home);
            for (int i = 1; i < w.SlotHomes.Count; i++)
            {
                if ((w.SlotHomes[i] - home).sqrMagnitude < 1e-6f)
                {
                    return i;
                }
            }
            w.SlotHomes.Add(home);
            foreach (ToleranceClass c in w.Classes)
            {
                c.InPlaceBySlot.Add(InPlaceAround(w, home, c.InPlaceRadius));
            }
            return w.SlotHomes.Count - 1;
        }

        /// <summary>The index of a seat home in <see cref="World.SeatHomes"/> (added with its cells the first time).</summary>
        private static int SeatOf(World w, Vector3 home)
        {
            home = YawMath.Planar(home);
            for (int i = 0; i < w.SeatHomes.Count; i++)
            {
                if ((w.SeatHomes[i] - home).sqrMagnitude < 1e-6f)
                {
                    return i;
                }
            }
            var cells = new HashSet<int>();
            for (int k = 0; k < w.Count; k++)
            {
                if (w.Walkable[k] && YawMath.Planar(w.Center[k] - home).magnitude <= SeatPresenceRadius)
                {
                    cells.Add(k);
                }
            }
            var flags = new bool[w.Count];
            foreach (int k in cells)
            {
                flags[k] = true;
            }
            w.SeatHomes.Add(home);
            w.SeatCells.Add(cells);
            w.SeatCellFlags.Add(flags);
            return w.SeatHomes.Count - 1;
        }

        /// <summary>[sample * n + cell] true when the cell is true at any sample within the margin (clamped to the table).</summary>
        private static bool[] Dilate(bool[] seen, int samples, int n, int margin)
        {
            var wide = new bool[samples * n];
            for (int s = 0; s < samples; s++)
            {
                int lo = Mathf.Max(0, s - margin);
                int hi = Mathf.Min(samples - 1, s + margin);
                int row = s * n;
                for (int q = lo; q <= hi; q++)
                {
                    int src = q * n;
                    for (int k = 0; k < n; k++)
                    {
                        wide[row + k] |= seen[src + k];
                    }
                }
            }
            return wide;
        }

        private static bool Clear(BodyModel body, Vector3 a, Vector3 b)
        {
            float cr = body.Radius;
            Vector3 bottom = Vector3.up * (cr + 0.05f);
            Vector3 top = Vector3.up * (body.Height - cr);
            Vector3 d = b - a;
            return !Physics.CapsuleCast(a + bottom, a + top, cr * 0.98f, d.normalized, d.magnitude, Layers.ChairBlockerMask, QueryTriggerInteraction.Ignore);
        }

        /// <summary>
        /// Still at a cell on a sample: where a sitter forces it (CONTRACT_M4 5), and unseen, in place, or explained.
        /// A dark lamp is never seen (CONTRACT_M4 10.5: a lit, still lamp follows the furniture rules); a stool lying on
        /// its side is out of place wherever it is.
        /// </summary>
        private static bool StillOk(World w, SearchOptions o, bool dark, bool lying, int k, int s, bool wide, int mask)
        {
            if (w.ForcedAt(s, wide) && !w.InSeatCell(k, s, wide))
            {
                return false;
            }
            // M5 (CONTRACT_M5 16.3): every human class that sees it still must find it in place or explained by its own
            // tolerance; the dog's sighting of a still chair is free.
            int index = s * w.Count + k;
            foreach (ToleranceClass c in w.Classes)
            {
                if (!c.SeenAt(dark, mask, index, wide))
                {
                    continue;
                }
                if (lying || (w.Body.Lamp && dark))
                {
                    return false;
                }
                if (!(w.InPlaceAt(c, k, s) || (o.Decoys && c.Explained[k])))
                {
                    return false;
                }
            }
            return RobotFree(w, o, s, w.Center[k], w.Center[k], wide);
        }

        /// <summary>
        /// CONTRACT_M5 4 and 16.8: on sample s (in the table), the furniture somewhere on the segment from a to b (a still, a
        /// stop, a toggle or an opening: a point) is out of every robot's contact zone: RobotRadius, the footprint's half
        /// diagonal and the replay's release, plus, when <paramref name="wide"/> (the search), the robot's travel over the
        /// margin, so a shifted schedule never touches it either. True without a robot or with the robots off.
        /// </summary>
        private static bool RobotFree(World w, SearchOptions o, int s, Vector3 a, Vector3 b, bool wide)
        {
            if (w.Robots == 0 || !o.Robots)
            {
                return true;
            }
            float zone = w.ContactBase + (wide ? w.RobotTravel : 0f);
            Vector3 pa = YawMath.Planar(a);
            Vector3 ab = YawMath.Planar(b) - pa;
            float length2 = ab.sqrMagnitude;
            for (int r = 0; r < w.Robots; r++)
            {
                Vector3 robot = w.RobotAt[s * w.Robots + r];
                float f = length2 > 1e-8f ? Mathf.Clamp01(Vector3.Dot(robot - pa, ab) / length2) : 0f;
                bool inside = YawMath.Planar(robot - (pa + ab * f)).magnitude < zone; // MUTATION:AUDIT_ROBOT_CONTACT
                if (inside)
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>
        /// Moving at cells a and b on sample s: in the horizon, unseen at both by any watcher (a human, or the dog, whose bark
        /// would break determinism, CONTRACT_M5_v3 8), and not where a sitter forces the player still.
        /// </summary>
        private static bool MovingOk(World w, bool dark, int s, int a, int b, bool wide, int mask)
        {
            return s >= 0 && s < w.Samples && !w.MovingSeen(dark, mask, s, a, wide) && !w.MovingSeen(dark, mask, s, b, wide) && !w.ForcedAt(s, wide);
        }

        /// <summary>
        /// CONTRACT_M5_v3 15.2 and 15.3: the player opens closed leaf <paramref name="leaf"/> from cell k, leaving at sample t
        /// (plus <paramref name="shift"/>): a Tuning.AuditOpenSamples action that counts as moving, checked in the mask after
        /// the opening (the collider leaves at the first swing step), and the leaf's samples at each sample's swing angle
        /// unseen by every moving watcher. The swing makes a sound but no noise event.
        /// </summary>
        private static bool CheckOpen(World w, SearchOptions o, Node from, int k, int leaf, int t, int shift, bool wide)
        {
            int after = from.Mask | w.Closed[leaf].Bit;
            if (!w.FreeIn(after, k))
            {
                return false; // the open leaf would stand where the furniture stands
            }
            for (int q = 1; q <= OpenSamples; q++)
            {
                int s = t + q + shift;
                if (!MovingOk(w, from.Off, s, k, k, wide, after) || w.LeafSeenAt(leaf, q, s, after, wide)
                    || !RobotFree(w, o, s, w.Center[k], w.Center[k], wide))
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>
        /// A noise of class <paramref name="kind"/> at <paramref name="p"/> on sample s reaches an inhabitant (its radius times
        /// the listener's hearing factor, plus the hearing margin), at that sample or, when <paramref name="wide"/>, within the
        /// margin. CONTRACT_M4 10.6: every furniture noise (hop, topple, click, roll) is silent on a rug or a soft floor. The
        /// search reads the same predicate from the noise tables (<see cref="NoiseTable"/>); this direct form checks a found
        /// schedule (narrow, shifted).
        /// </summary>
        private static bool Heard(World w, Vector3 p, int s, NoiseKind kind, bool wide, bool hum)
        {
            if (w.Def.IsSilentFloor(p))
            {
                return false;
            }
            float radius = Hearing.RadiusOf(kind);
            int from = wide ? Mathf.Max(0, s - w.Margin) : s;
            int to = wide ? Mathf.Min(w.Samples - 1, s + w.Margin) : s;
            for (int r = from; r <= to; r++)
            {
                // M5 wave 5B: a noise the robot's hum masks at r is not emitted at r (the noise tables' rule).
                if (hum && HumMasked(w, kind, p, r))
                {
                    continue;
                }
                for (int i = 0; i < w.Inhabitants; i++)
                {
                    float factor = w.HearingFactor[i];
                    if (factor > 0f && YawMath.Planar(w.Position[r, i] - p).magnitude <= radius * factor + NoiseMargin)
                    {
                        return true;
                    }
                }
            }
            return false;
        }

        /// <summary>The noise tables one search reads (its wide tables); null when that noise is off or never made.</summary>
        private sealed class Ears
        {
            /// <summary>The travel points of every move (a hop, or a roll for a gliding body).</summary>
            public NoiseTable Move;
            /// <summary>The glide at a stop.</summary>
            public NoiseTable Roll;
            /// <summary>The stool's fall at a stop.</summary>
            public NoiseTable Topple;
            /// <summary>The lamp's switch.</summary>
            public NoiseTable Click;
            /// <summary>
            /// M5 wave 5B: the travel points of the other leg length (<see cref="AltTravel"/>): a load's careful legs, or a rocking
            /// body going on straight in motion; null when the search has only one.
            /// </summary>
            public NoiseTable Alt;

            public static Ears For(World w, SearchOptions o, int travel, int stopCost, bool toggles, int altTravel)
            {
                var ears = new Ears();
                if (!o.Noise)
                {
                    return ears;
                }
                // M5 wave 5B: the robot's hum masks the hops, rolls and clicks near it (CONTRACT_M5 4, 16.8).
                bool hum = HumOn(w, o);
                ears.Move = NoiseFor(w, w.Body.MoveNoiseKind, travel, hum);
                if (altTravel > 0)
                {
                    ears.Alt = NoiseFor(w, w.Body.MoveNoiseKind, altTravel, hum);
                }
                if (stopCost > 0)
                {
                    if (w.Body.Glides)
                    {
                        ears.Roll = NoiseFor(w, NoiseKind.Roll, 0, hum);
                    }
                    else if (w.Body.Tips)
                    {
                        ears.Topple = NoiseFor(w, NoiseKind.Topple, 0);
                    }
                }
                if (toggles)
                {
                    ears.Click = NoiseFor(w, NoiseKind.Click, 0, hum);
                }
                return ears;
            }
        }

        /// <summary>Samples of the travel over one cell under these options.</summary>
        private static int TravelSamples(World w, SearchOptions o)
        {
            if (CarefulOnly(w, o))
            {
                return w.Body.CarefulMoveSamples;
            }
            return o.FullSpeed && w.Body.Tips ? w.Body.FullSpeedMoveSamples : w.Body.MoveSamples;
        }

        /// <summary>
        /// M5 wave 5B: every leg of this search is careful beyond the stool's: a body whose full start drops its load, under the
        /// load rule (CONTRACT_M5 16.5).
        /// </summary>
        private static bool CarefulOnly(World w, SearchOptions o)
        {
            return LoadRuleOn(w, o) && w.Body.FullStartDropsLoad && !w.Body.Tips;
        }

        /// <summary>
        /// M5 wave 5B: the samples of the search's other leg length, or 0: a careful leg when the load rule applies (a stool's
        /// legs are all careful already, and so are those of a body whose full start drops the load), or a rocking body going
        /// on straight in motion.
        /// </summary>
        private static int AltTravel(World w, SearchOptions o)
        {
            if (LoadRuleOn(w, o))
            {
                return w.Body.Tips || w.Body.FullStartDropsLoad ? 0 : w.Body.CarefulMoveSamples;
            }
            return RockDirections(w, o) ? w.Body.ContinueSamples : 0;
        }

        /// <summary>CONTRACT_M5 16.5: the load rule applies to this search (a load, and the rule not switched off).</summary>
        private static bool LoadRuleOn(World w, SearchOptions o)
        {
            return w.HasLoad && o.LoadRule;
        }

        /// <summary>
        /// A rocking body (rocking in this search or not, so the "rock" lesson's schedule has the same speeds): a node it
        /// reaches by a move remembers the direction it arrived in, and a move on in that direction is the faster leg.
        /// </summary>
        private static bool RockDirections(World w, SearchOptions o)
        {
            return w.RockSamples > 0 && !w.Body.Glides && !w.Body.Tips && !LoadRuleOn(w, o);
        }

        /// <summary>
        /// Samples a stop costs at the end of a run: the office chair's glide, the stool's fall at full speed, M5 wave 5B the
        /// rocking chair's rock (CONTRACT_M5 5, 16.9), else none.
        /// </summary>
        private static int StopCost(World w, SearchOptions o)
        {
            if (w.Body.Glides)
            {
                return o.StopSamples;
            }
            if (w.RockSamples > 0 && o.Rock)
            {
                int rock = w.RockSamples; // MUTATION:AUDIT_ROCK
                return rock;
            }
            return o.FullSpeed && w.Body.Tips ? FallSamples : 0;
        }

        /// <summary>
        /// A move from k to dest (its <paramref name="j"/>-th neighbor) leaving at sample t (plus <paramref name="shift"/>) over
        /// <paramref name="travel"/> samples: a lying stool rights itself first (moving, at k), then the travel, moving at both
        /// cells, out of every robot's contact zone along the whole way, and never heard. With <paramref name="table"/> (the
        /// search, wide: the travel points of this leg length) the noise is a table lookup; without, the direct predicate.
        /// </summary>
        private static bool CheckMove(World w, SearchOptions o, NoiseTable table, Node from, int k, int j, int dest, int t, int shift, bool wide, int travel)
        {
            int right = from.Lying ? RightSamples : 0;
            for (int q = 1; q <= right; q++)
            {
                if (!MovingOk(w, from.Off, t + q + shift, k, k, wide, from.Mask) || !RobotFree(w, o, t + q + shift, w.Center[k], w.Center[k], wide))
                {
                    return false;
                }
            }
            int edge = table != null ? (w.EdgeStart[k] + j) * travel - 1 : 0;
            bool hum = HumOn(w, o);
            for (int q = 1; q <= travel; q++)
            {
                int s = t + right + q + shift;
                if (!MovingOk(w, from.Off, s, k, dest, wide, from.Mask) || !RobotFree(w, o, s, w.Center[k], w.Center[dest], wide))
                {
                    return false;
                }
                if (o.Noise && (table != null
                        ? table.HeardWide(s, edge + q)
                        : Heard(w, Vector3.Lerp(w.Center[k], w.Center[dest], q / (float)travel), s, w.Body.MoveNoiseKind, wide, hum)))
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>
        /// The stop at the end of a run (CONTRACT_M4 5): the office chair glides <see cref="SearchOptions.StopSamples"/>
        /// samples (moving, rolling); the stool at full speed falls (moving) and the topple is heard on any floor; M5 wave 5B,
        /// the rocking chair rocks (moving, in place, silent: its creak is a sound, not a noise event). Out of every robot's
        /// contact zone throughout.
        /// </summary>
        private static bool CheckStop(World w, SearchOptions o, Ears ears, Node from, int k, int t, int shift, bool wide)
        {
            int length = StopCost(w, o);
            bool hum = HumOn(w, o);
            for (int q = 1; q <= length; q++)
            {
                int s = t + q + shift;
                if (!MovingOk(w, from.Off, s, k, k, wide, from.Mask) || !RobotFree(w, o, s, w.Center[k], w.Center[k], wide))
                {
                    return false;
                }
                if (!o.Noise)
                {
                    continue;
                }
                if (w.Body.Glides && (ears != null ? ears.Roll.HeardWide(s, k) : Heard(w, w.Center[k], s, NoiseKind.Roll, wide, hum)))
                {
                    return false;
                }
                if (w.Body.Tips && q == length && (ears != null ? ears.Topple.HeardWide(s, k) : Heard(w, w.Center[k], s, NoiseKind.Topple, wide, false)))
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>
        /// The lamp switches itself (CONTRACT_M4 2.3, 10.4): a Tuning.LampToggleTime action that counts as moving, seen at
        /// the lit range whatever the direction (the rules use the lit range until the action ends), and a click.
        /// </summary>
        private static bool CheckToggle(World w, SearchOptions o, Ears ears, Node from, int k, int t, int shift, bool wide)
        {
            const bool dark = false;
            bool hum = HumOn(w, o);
            for (int q = 1; q <= ToggleSamples; q++)
            {
                int s = t + q + shift;
                if (!MovingOk(w, dark, s, k, k, wide, from.Mask) || !RobotFree(w, o, s, w.Center[k], w.Center[k], wide)
                    || (o.Noise && (ears != null ? ears.Click.HeardWide(s, k) : Heard(w, w.Center[k], s, NoiseKind.Click, wide, hum))))
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>What a search requires. Each constraint can be relaxed to prove that it is the one that binds.</summary>
        private sealed class SearchOptions
        {
            /// <summary>The sample the player starts acting at (the chair stood at spawn until then).</summary>
            public int Delay;
            public int MaxRun = Mathf.RoundToInt(Tuning.AuditMaxWait / SampleSeconds);
            public bool Noise = true;
            public float GaugeCap = LevelAudit.GaugeCap;
            public bool Decoys = true;
            /// <summary>The schedule must be explained by a decoy at least once.</summary>
            public bool NeedDecoy;
            /// <summary>M4: the stool without careful mode: full speed, and every stop from a run tips it.</summary>
            public bool FullSpeed;
            /// <summary>M4: the lamp may switch itself off and on.</summary>
            public bool Toggles = true;
            /// <summary>M4: the office chair's glide at every stop, in samples (Tuning.AuditStopSamples).</summary>
            public int StopSamples = Tuning.AuditStopSamples;
            /// <summary>M5: the player may open the closed leaves (false: every leaf locked, the "door" lesson).</summary>
            public bool Doors = true;
            /// <summary>M5: [cell] cells barred to the player (the "split" lesson bars the platforms and ramps), or null.</summary>
            public bool[] Barred;
            /// <summary>M5 wave 5B: the robots exist (false: no contact zone and no hum, the "robot" lesson's schedule without it).</summary>
            public bool Robots = true;
            /// <summary>M5 wave 5B: the robot's hum masks the hops, rolls and clicks near it (false: it masks nothing).</summary>
            public bool Hum = true;
            /// <summary>M5 wave 5B: a rocking body rocks at every stop (false: it stops like the chair, the "rock" lesson).</summary>
            public bool Rock = true;
            /// <summary>
            /// M5 wave 5B: the load rule (false: full speed legs only and the load never falls, the "load" lesson); the grown
            /// sample box stays.
            /// </summary>
            public bool LoadRule = true;
        }

        /// <summary>
        /// CONTRACT_M5 16.5 (the load, a kinematic rule) for the search: the search state gains the recent velocity. A state is
        /// a recent wish history, one symbol a sample (none, or a cell direction at full or careful stick), the last
        /// <see cref="LoadHistorySamples"/> samples kept; histories are interned by what they mean for the future (the planar
        /// velocities of the last load window, and the glide, tip and action flags, as <see cref="MotionProfile"/> leaves them
        /// when it re-simulates the kept history from rest), so equivalent histories share one state. An act (a still sample, a
        /// stop, an opening, a leg) appends its samples; it is refused (-1) when LoadBalance's change over the window reaches
        /// Tuning.LoadFallDeltaV on one of its steps. State 0 is the load at rest. Transitions are cached per state and act.
        /// A leg of mode 0 is the search's own (careful for a stool), mode 1 a careful leg.
        /// </summary>
        private sealed class LoadModel
        {
            public const int ActStill = 0;
            public const int ActStop = 1;
            public const int ActOpen = 2;
            private const int ActMoveBase = 3;
            private const int Acts = ActMoveBase + 4 * 2 * 2;
            private const int Unknown = int.MinValue;
            /// <summary>States beyond this are refused (the search state stores the state as a ushort).</summary>
            private const int MaxStates = 65535;

            private readonly BodyDef body;
            private readonly int[] travel = new int[2];
            private readonly bool[] careful = new bool[2];
            private readonly int stop;
            private readonly int open;
            private readonly int right;
            private readonly List<byte[]> history = new List<byte[]>();
            private readonly List<int[]> next = new List<int[]>();
            private readonly Dictionary<string, int> ids = new Dictionary<string, int>();
            /// <summary>The acts the search can play from some node (a superset is safe: it only makes the dominance stricter).</summary>
            private readonly List<int> acts = new List<int>();
            /// <summary>The closure's size limit: beyond it there is no cross-state dominance.</summary>
            private const int MaxClosed = 3000;
            /// <summary>[a * closed + b]: a simulates b (<see cref="Dominates"/>), over the first <see cref="closed"/> states.</summary>
            private bool[] simulation;
            private int closed;

            public LoadModel(BodyDef body, int travel0, bool careful0, int travel1, int stop, int open, int right)
            {
                this.body = body;
                travel[0] = travel0;
                careful[0] = careful0;
                travel[1] = travel1;
                careful[1] = true;
                this.stop = stop;
                this.open = open;
                this.right = right;
                acts.Add(ActStill);
                acts.Add(ActOpen);
                if (stop > 0)
                {
                    acts.Add(ActStop);
                }
                for (int dir = 0; dir < 4; dir++)
                {
                    for (int mode = 0; mode < (travel1 > 0 ? 2 : 1); mode++)
                    {
                        acts.Add(Move(dir, mode, false));
                        if (body.Tips && !careful0)
                        {
                            acts.Add(Move(dir, mode, true)); // a stool searched at full speed lies after its stops
                        }
                    }
                }
                Intern(new byte[0]);
                Close();
            }

            /// <summary>The states interned so far.</summary>
            public int Count => history.Count;

            /// <summary>
            /// State <paramref name="a"/> is at least as free as state <paramref name="b"/>: every act sequence the load survives
            /// from b it also survives from a (the greatest simulation over the closed state space, <see cref="Close"/>). A search
            /// node with state a, no more run, gauge and moves than one with state b, everything else equal, dominates it. Without
            /// a closed space (too many states), only a state dominates itself.
            /// </summary>
            public bool Dominates(int a, int b)
            {
                if (a == b)
                {
                    return true;
                }
                return simulation != null && a < closed && b < closed && simulation[a * closed + b];
            }

            /// <summary>
            /// Interns every state the acts reach from rest (a breadth first closure, at most <see cref="MaxClosed"/> states), then
            /// computes the greatest simulation by refinement: a pair holds while every act b survives, a survives too, into a
            /// pair that holds.
            /// </summary>
            private void Close()
            {
                for (int s = 0; s < history.Count && history.Count <= MaxClosed; s++)
                {
                    foreach (int act in acts)
                    {
                        Step(s, act);
                    }
                }
                if (history.Count > MaxClosed)
                {
                    return; // no dominance: still exact, only slower
                }
                int n = closed = history.Count;
                var holds = new bool[n * n];
                for (int i = 0; i < holds.Length; i++)
                {
                    holds[i] = true;
                }
                bool changed = true;
                while (changed)
                {
                    changed = false;
                    for (int a = 0; a < n; a++)
                    {
                        for (int b = 0; b < n; b++)
                        {
                            if (a == b || !holds[a * n + b])
                            {
                                continue;
                            }
                            foreach (int act in acts)
                            {
                                int nb = next[b][act];
                                if (nb < 0)
                                {
                                    continue;
                                }
                                int na = next[a][act];
                                if (na < 0 || (na != nb && !holds[na * n + nb]))
                                {
                                    holds[a * n + b] = false;
                                    changed = true;
                                    break;
                                }
                            }
                        }
                    }
                }
                simulation = holds;
            }

            /// <summary>The act of a leg toward cell direction <paramref name="dir"/> (<see cref="DirIndex"/>) in mode 0 or 1.</summary>
            public static int Move(int dir, int mode, bool lying) => ActMoveBase + (dir * 2 + mode) * 2 + (lying ? 1 : 0);

            /// <summary>The planar unit vector (x, z) of a cell direction.</summary>
            public static Vector2 DirVector(int dir)
            {
                switch (dir)
                {
                    case 0: return new Vector2(1f, 0f);
                    case 1: return new Vector2(-1f, 0f);
                    case 2: return new Vector2(0f, 1f);
                    default: return new Vector2(0f, -1f);
                }
            }

            /// <summary>The state after <paramref name="act"/> from <paramref name="state"/>, or -1 when the load falls during it.</summary>
            public int Step(int state, int act)
            {
                int[] row = next[state];
                if (row[act] == Unknown)
                {
                    row[act] = Compute(state, act);
                }
                return row[act];
            }

            private int Compute(int state, int act)
            {
                var samples = new List<byte>(history[state]);
                int first = samples.Count;
                switch (act)
                {
                    case ActStill:
                        samples.Add(0);
                        break;
                    case ActStop:
                        Repeat(samples, 0, stop);
                        break;
                    case ActOpen:
                        Repeat(samples, 0, open);
                        break;
                    default:
                    {
                        int code = act - ActMoveBase;
                        bool lying = (code & 1) != 0;
                        int mode = (code >> 1) & 1;
                        int dir = code >> 2;
                        if (lying)
                        {
                            Repeat(samples, 0, right);
                        }
                        Repeat(samples, (byte)(1 + dir * 2 + (careful[mode] ? 1 : 0)), travel[mode]);
                        break;
                    }
                }
                Vector2[] v = Simulate(samples, out _);
                float threshold = Tuning.LoadFallDeltaV - LoadEpsilon; // MUTATION:AUDIT_LOAD
                for (int i = first * SampleSteps; i < v.Length; i++)
                {
                    Vector2 before = i >= LoadWindowSteps ? v[i - LoadWindowSteps] : Vector2.zero;
                    if ((v[i] - before).magnitude >= threshold)
                    {
                        return -1;
                    }
                }
                int keep = Mathf.Min(samples.Count, LoadHistorySamples);
                byte[] kept = samples.GetRange(samples.Count - keep, keep).ToArray();
                return Count >= MaxStates ? -1 : Intern(kept);
            }

            private static void Repeat(List<byte> samples, byte symbol, int count)
            {
                for (int i = 0; i < count; i++)
                {
                    samples.Add(symbol);
                }
            }

            /// <summary>Re-simulates a wish history from rest (five fixed steps a sample): the velocity of every step.</summary>
            private Vector2[] Simulate(List<byte> samples, out MotionProfile profile)
            {
                profile = new MotionProfile(body);
                var v = new Vector2[samples.Count * SampleSteps];
                for (int i = 0; i < samples.Count; i++)
                {
                    byte symbol = samples[i];
                    MotionWish wish = symbol == 0 ? MotionWish.None() : new MotionWish(DirVector((symbol - 1) >> 1), ((symbol - 1) & 1) != 0);
                    for (int step = 0; step < SampleSteps; step++)
                    {
                        v[i * SampleSteps + step] = profile.Step(wish);
                    }
                }
                return v;
            }

            /// <summary>The state of a kept history: an existing one with the same future, or a new one.</summary>
            private int Intern(byte[] kept)
            {
                var list = new List<byte>(kept);
                Vector2[] v = Simulate(list, out MotionProfile profile);
                var key = new StringBuilder();
                for (int i = 0; i < LoadWindowSteps; i++)
                {
                    int at = v.Length - LoadWindowSteps + i;
                    Vector2 x = at >= 0 ? v[at] : Vector2.zero;
                    key.Append(Mathf.RoundToInt(x.x * 1000f)).Append(',').Append(Mathf.RoundToInt(x.y * 1000f)).Append(';');
                }
                key.Append(profile.Gliding ? 'g' : '-').Append(profile.Tipped ? 't' : '-').Append(profile.ActionActive ? 'a' : '-')
                    .Append(kept.Length > 0 && kept[kept.Length - 1] != 0 ? 'w' : '-');
                string text = key.ToString();
                if (ids.TryGetValue(text, out int id))
                {
                    return id;
                }
                id = history.Count;
                ids[text] = id;
                history.Add(kept);
                var row = new int[Acts];
                for (int i = 0; i < Acts; i++)
                {
                    row[i] = Unknown;
                }
                next.Add(row);
                return id;
            }
        }

        /// <summary>
        /// The nodes of one search, in creation order (a node's index is its id; Parent links them). Stored in fixed blocks so
        /// a search of tens of millions of nodes never copies them into a doubled array (the editor shares a machine with
        /// little free memory): its memory is its node count, give or take one block.
        /// </summary>
        private sealed class NodeList
        {
            private const int BlockBits = 16;
            private const int BlockSize = 1 << BlockBits;
            private const int BlockMask = BlockSize - 1;
            private Node[][] items = new Node[8][];
            /// <summary>[node]: the next node of the same front in its layer, or -1.</summary>
            private int[][] next = new int[8][];
            public int Count;

            public Node this[int i] => items[i >> BlockBits][i & BlockMask];

            /// <summary>The next node of the same front in its layer, or -1.</summary>
            public int Next(int i) => next[i >> BlockBits][i & BlockMask];

            public void SetNext(int i, int value) => next[i >> BlockBits][i & BlockMask] = value;

            public int Add(Node n)
            {
                int block = Count >> BlockBits;
                if (block == items.Length)
                {
                    Array.Resize(ref items, block * 2);
                    Array.Resize(ref next, block * 2);
                }
                if (items[block] == null)
                {
                    // The first block starts small: most searches (lessons, sweeps, fixtures) create a few thousand nodes.
                    int size = block == 0 ? 1024 : BlockSize;
                    items[block] = new Node[size];
                    next[block] = new int[size];
                }
                else if (block == 0 && Count == items[0].Length)
                {
                    int size = Math.Min(BlockSize, Count * 2);
                    Array.Resize(ref items[0], size);
                    Array.Resize(ref next[0], size);
                }
                items[block][Count & BlockMask] = n;
                next[block][Count & BlockMask] = -1;
                return Count++;
            }
        }

        /// <summary>
        /// One time layer of the search: its states in first-offer order, each holding its Pareto front as a list of node
        /// indices (linked through <see cref="NodeList.Next"/>) in insertion order. M4 kept a Dictionary of Lists, which
        /// enumerates in insertion order and whose RemoveAll keeps the order: this layer enumerates identically, so the
        /// search offers, keeps and returns the same nodes as M4, with no allocation per state.
        /// </summary>
        private sealed class Layer
        {
            public long[] Keys = new long[64];
            public int[] Head = new int[64];
            public int[] Tail = new int[64];
            public int Count;
            private int[] position = new int[64];
            private int[] table = new int[128];
            private int mask = 127;

            /// <summary>The slot of a state, added (with an empty front) the first time.</summary>
            public int Slot(long key)
            {
                int h = Hash(key) & mask;
                for (int v = table[h]; v != 0; v = table[h])
                {
                    if (Keys[v - 1] == key)
                    {
                        return v - 1;
                    }
                    h = (h + 1) & mask;
                }
                if (Count == Keys.Length)
                {
                    Array.Resize(ref Keys, Count * 2);
                    Array.Resize(ref Head, Count * 2);
                    Array.Resize(ref Tail, Count * 2);
                    Array.Resize(ref position, Count * 2);
                }
                Keys[Count] = key;
                Head[Count] = -1;
                Tail[Count] = -1;
                position[Count] = h;
                table[h] = ++Count;
                if (Count * 2 > table.Length)
                {
                    Grow();
                }
                return Count - 1;
            }

            /// <summary>Empties the layer for reuse, clearing only the table cells it used.</summary>
            public void Clear()
            {
                for (int i = 0; i < Count; i++)
                {
                    table[position[i]] = 0;
                }
                Count = 0;
            }

            private void Grow()
            {
                table = new int[table.Length * 2];
                mask = table.Length - 1;
                for (int i = 0; i < Count; i++)
                {
                    int h = Hash(Keys[i]) & mask;
                    while (table[h] != 0)
                    {
                        h = (h + 1) & mask;
                    }
                    table[h] = i + 1;
                    position[i] = h;
                }
            }

            private static int Hash(long key)
            {
                return (int)(((ulong)key * 0x9E3779B97F4A7C15UL) >> 33);
            }
        }

        private static readonly Stack<Layer> LayerPool = new Stack<Layer>();

        private static Layer RentLayer()
        {
            return LayerPool.Count > 0 ? LayerPool.Pop() : new Layer();
        }

        private static void ReturnLayer(Layer layer)
        {
            layer.Clear();
            LayerPool.Push(layer);
        }

        /// <summary>
        /// Breadth first over time from the start delay: each sample holds, per (cell, wait anchor, explained-once flag,
        /// M4 lamp off, in motion, lying), the Pareto front of (run near the anchor, gauge, moves). The first sample
        /// where a state stands unseen in the exit wins; among its states, the one with the fewest moves. Returns the
        /// node list; <paramref name="goal"/> is -1 when no schedule exists (or when the level's node budget is spent).
        /// </summary>
        private static NodeList Search(World w, SearchOptions options, out int goal)
        {
            goal = -1;
            var nodes = new NodeList();
            long nodesBefore = Budget.Nodes;
            int start = options.Delay;
            int horizon = w.Horizon;
            if (w.Start < 0 || start >= horizon || Budget.NodesExhausted || Budget.RaysExhausted || (options.Barred != null && options.Barred[w.Start]))
            {
                return nodes;
            }
            int creakDelay = Mathf.RoundToInt(Tuning.CreakStartDelay / SampleSeconds);
            float fill = SampleSeconds / Tuning.CreakFillTime;
            float drain = SampleSeconds / Tuning.CreakDrainTime;
            int stopCost = StopCost(w, options);
            bool tracksMotion = stopCost > 0;
            bool toggles = w.Body.Lamp && options.Toggles;
            int travel = TravelSamples(w, options);
            // M5 wave 5B: a second leg length (a load's careful legs, or a rocking body going on straight in motion), the load
            // model, and the direction a rocking body in motion arrived in (CONTRACT_M5 16.5, 16.9).
            int altTravel = AltTravel(w, options);
            bool carefulLegs = LoadRuleOn(w, options) && altTravel > 0;
            bool rockDirections = RockDirections(w, options);
            bool carefulBase = (w.Body.Tips && !options.FullSpeed) || CarefulOnly(w, options);
            LoadModel load = LoadRuleOn(w, options) ? LoadModelFor(w, travel, carefulBase, altTravel, stopCost) : null;
            // The rocking body's direction is part of the state; the load state is not: it enters the dominance instead.
            bool descriptors = rockDirections;
            int legs = altTravel > 0 ? 2 : 1;
            Ears ears = Ears.For(w, options, travel, stopCost, toggles, altTravel);
            // CONTRACT_M5 16.8: the furniture stands at the spawn until the start delay ends, out of every robot's contact zone.
            for (int s = 0; s <= start && w.Robots > 0; s++)
            {
                if (!RobotFree(w, options, s, w.Spawn, w.Spawn, true))
                {
                    return nodes;
                }
            }
            // CONTRACT_M5 16.3 (cost): a search that cannot reach the exit even without the wait cap, the creak gauge and the
            // decoy flag finds nothing, so it is answered by that much smaller reachability first (exact: a superset of
            // every schedule). The lesson checks and the self-test, which expect no schedule, no longer walk the whole horizon.
            if (!(load != null
                    ? ReachableLoaded(w, options, ears, travel, stopCost, toggles, altTravel, load)
                    : Reachable(w, options, ears, travel, stopCost, toggles, altTravel)))
            {
                return nodes;
            }
            // The delay measures the routine phase the attempt starts at: the gauge starts empty. (A chair that
            // really stood at spawn that long creaks there, in place, which is harmless but makes the
            // inhabitant look: the deterministic routine of this search cannot model that look.)
            const float gauge0 = 0f;
            var layers = new Layer[horizon + 1];
            // Memos of the checks that depend only on (time, cell, edge, lamp off, lying): every node of a layer that stands
            // on the same cell shares them. A stamp of t + 1 marks an entry computed for layer t.
            int masks = w.Masks;
            var stillStamp = new int[w.Count * 4 * masks];
            var stillMemo = new bool[w.Count * 4 * masks];
            var moveStamp = new int[Math.Max(1, w.Edges) * 4 * masks * legs];
            var moveMemo = new bool[Math.Max(1, w.Edges) * 4 * masks * legs];
            bool doors = options.Doors && w.Closed.Count > 0;
            long BaseKey(Node n) => ((((((long)n.Cell * w.Count + n.Anchor) * 2 + (n.Flag ? 1 : 0)) * 2 + (n.Off ? 1 : 0)) * 2 + (n.Motion ? 1 : 0)) * 2 + (n.Lying ? 1 : 0))
                * masks + n.Mask;
            // M5 wave 5B: a rocking body's direction in motion is part of the state; the other levels keep the M4 key exactly.
            long Key(Node n) => descriptors ? BaseKey(n) * 65536L + n.Load : BaseKey(n);
            // M5 wave 5B: with a load, a node dominates another of its state only if its load state is at least as free.
            bool Freer(Node a, Node b) => load == null || load.Dominates(a.Load, b.Load);

            // Keeps n unless a node of its state dominates or equals it; drops the nodes it dominates or equals, in order.
            void Offer(Node n)
            {
                Layer layer = layers[n.T] ?? (layers[n.T] = RentLayer());
                int slot = layer.Slot(Key(n));
                for (int i = layer.Head[slot]; i >= 0; i = nodes.Next(i))
                {
                    Node kept = nodes[i];
                    if (kept.Run <= n.Run && kept.Gauge <= n.Gauge + 1e-6f && kept.Moves <= n.Moves && Freer(kept, n))
                    {
                        return;
                    }
                }
                int previous = -1;
                for (int i = layer.Head[slot]; i >= 0;)
                {
                    int after = nodes.Next(i);
                    Node kept = nodes[i];
                    if (n.Run <= kept.Run && n.Gauge <= kept.Gauge + 1e-6f && n.Moves <= kept.Moves && Freer(n, kept))
                    {
                        if (previous < 0)
                        {
                            layer.Head[slot] = after;
                        }
                        else
                        {
                            nodes.SetNext(previous, after);
                        }
                        if (layer.Tail[slot] == i)
                        {
                            layer.Tail[slot] = previous;
                        }
                    }
                    else
                    {
                        previous = i;
                    }
                    i = after;
                }
                int idx = nodes.Add(n);
                if (nodes.Count > Tuning.AuditSearchNodeCap)
                {
                    // The memory guard: the search stops at its next expansion, and the level fails for it (Budget.Defect).
                    Budget.SearchTooLarge = true;
                    Budget.NodesExhausted = true;
                }
                if (layer.Tail[slot] < 0)
                {
                    layer.Head[slot] = idx;
                }
                else
                {
                    nodes.SetNext(layer.Tail[slot], idx);
                }
                layer.Tail[slot] = idx;
            }

            Offer(new Node { Cell = w.Start, Anchor = w.Start, T = start, Parent = -1, Gauge = gauge0, Act = Act.Start });
            try
            {
                for (int t = start; t < horizon && goal < 0; t++)
                {
                    Layer current = layers[t];
                    layers[t] = null;
                    if (current == null)
                    {
                        continue;
                    }
                    try
                    {
                        for (int slot = 0; slot < current.Count; slot++)
                        {
                            for (int idx = current.Head[slot]; idx >= 0; idx = nodes.Next(idx))
                            {
                                Node n = nodes[idx];
                                if (t > start && w.InExit[n.Cell] && !w.HumanSeen(n.Off, n.Mask, t, n.Cell, true) && (n.Flag || !options.NeedDecoy)
                                    && (goal < 0 || n.Moves < nodes[goal].Moves || (n.Moves == nodes[goal].Moves && n.Gauge < nodes[goal].Gauge)))
                                {
                                    goal = idx;
                                }
                            }
                        }
                        if (goal >= 0)
                        {
                            break;
                        }
                        for (int slot = 0; slot < current.Count; slot++)
                        {
                            for (int idx = current.Head[slot]; idx >= 0; idx = nodes.Next(idx))
                            {
                                if (!Budget.Expand())
                                {
                                    goal = -1;
                                    return nodes;
                                }
                                Node n = nodes[idx];
                                int k = n.Cell;
                                // Still (a furniture still in motion must stop first). Sat on, the creak gauge pauses.
                                if (!n.Motion)
                                {
                                    float filled = n.Gauge + (t + 1 >= creakDelay && !w.Pinned[t + 1] ? fill : 0f);
                                    int still = ((k * 2 + (n.Off ? 1 : 0)) * 2 + (n.Lying ? 1 : 0)) * masks + n.Mask;
                                    if (stillStamp[still] != t + 1)
                                    {
                                        stillStamp[still] = t + 1;
                                        stillMemo[still] = StillOk(w, options, n.Off, n.Lying, k, t + 1, true, n.Mask);
                                    }
                                    // M5 wave 5B: with a load, a still sample is a sample without input (the instant stop).
                                    int stillLoad = load != null && stillMemo[still] ? load.Step(n.Load, LoadModel.ActStill) : 0;
                                    if (n.Run + 1 <= options.MaxRun && filled < options.GaugeCap && stillMemo[still] && stillLoad >= 0)
                                    {
                                        bool explained = options.Decoys && !n.Lying && !(w.Body.Lamp && n.Off) && w.ExplainedAt(n.Mask, k, t + 1);
                                        Offer(new Node
                                        {
                                            Cell = k, T = t + 1, Parent = idx, Moves = n.Moves, Run = n.Run + 1, Anchor = n.Anchor,
                                            Gauge = filled, Flag = n.Flag || explained, Act = Act.Still, Off = n.Off, Lying = n.Lying, Mask = n.Mask,
                                            Load = stillLoad,
                                        });
                                    }
                                }
                                if (t < start + w.Margin)
                                {
                                    continue;
                                }
                                if (n.Motion)
                                {
                                    int stopLoad = 0;
                                    if (t + stopCost <= horizon && n.Run + stopCost <= options.MaxRun && CheckStop(w, options, ears, n, k, t, 0, true)
                                        && (load == null || (stopLoad = load.Step(n.Load, LoadModel.ActStop)) >= 0))
                                    {
                                        Offer(new Node
                                        {
                                            Cell = k, T = t + stopCost, Parent = idx, Moves = n.Moves, Run = n.Run + stopCost, Anchor = n.Anchor,
                                            Gauge = Mathf.Max(0f, n.Gauge - stopCost * drain), Flag = n.Flag, Act = Act.Stop, Off = n.Off,
                                            Lying = w.Body.Tips, Mask = n.Mask, Load = stopLoad,
                                        });
                                    }
                                }
                                else if (toggles && t + ToggleSamples <= horizon && n.Run + ToggleSamples <= options.MaxRun
                                         && CheckToggle(w, options, ears, n, k, t, 0, true))
                                {
                                    Offer(new Node
                                    {
                                        Cell = k, T = t + ToggleSamples, Parent = idx, Moves = n.Moves, Run = n.Run + ToggleSamples, Anchor = n.Anchor,
                                        Gauge = Mathf.Max(0f, n.Gauge - ToggleSamples * drain), Flag = n.Flag, Act = Act.Toggle, Off = !n.Off, Lying = n.Lying,
                                        Mask = n.Mask, Load = n.Load,
                                    });
                                }
                                // M5: open a closed leaf in reach (E acts only on a still, upright furniture, CONTRACT_M5_v3 15.2).
                                if (doors && !n.Motion && !n.Lying && w.ReachBits[k] != 0 && t + OpenSamples <= horizon && n.Run + OpenSamples <= options.MaxRun)
                                {
                                    for (int l = 0; l < w.Closed.Count; l++)
                                    {
                                        int bit = w.Closed[l].Bit;
                                        if ((w.ReachBits[k] & bit) == 0 || (n.Mask & bit) != 0 || !CheckOpen(w, options, n, k, l, t, 0, true))
                                        {
                                            continue;
                                        }
                                        int openLoad = load != null ? load.Step(n.Load, LoadModel.ActOpen) : 0;
                                        if (openLoad < 0)
                                        {
                                            continue;
                                        }
                                        Offer(new Node
                                        {
                                            Cell = k, T = t + OpenSamples, Parent = idx, Moves = n.Moves, Run = n.Run + OpenSamples, Anchor = n.Anchor,
                                            Gauge = Mathf.Max(0f, n.Gauge - OpenSamples * drain), Flag = n.Flag, Act = Act.Open, Off = n.Off,
                                            Mask = (byte)(n.Mask | bit), Load = openLoad,
                                        });
                                    }
                                }
                                List<int> around = w.Neighbors[k];
                                for (int j = 0; j < around.Count; j++)
                                {
                                    int o = around[j];
                                    int edge = w.EdgeStart[k] + j;
                                    int dir = descriptors || load != null ? DirIndex(w, k, o) : 0;
                                    // A rocking body that arrived by a move and goes on straight takes the faster leg (leg 1), else
                                    // the body's (leg 0). Only a node reached by a move carries a direction.
                                    bool straight = rockDirections && n.Act == Act.Move && n.Load == dir + 1;
                                    for (int leg = 0; leg < legs; leg++)
                                    {
                                        if (rockDirections && (leg == 1) != straight)
                                        {
                                            continue;
                                        }
                                        int legTravel = leg == 0 ? travel : altTravel;
                                        int length = legTravel + (n.Lying ? RightSamples : 0);
                                        if (t + length > horizon)
                                        {
                                            continue;
                                        }
                                        int move = (((edge * 2 + (n.Off ? 1 : 0)) * 2 + (n.Lying ? 1 : 0)) * masks + n.Mask) * legs + leg;
                                        if (moveStamp[move] != t + 1)
                                        {
                                            moveStamp[move] = t + 1;
                                            moveMemo[move] = w.EdgeOpen(n.Mask, edge, k, o) && (options.Barred == null || !options.Barred[o])
                                                && CheckMove(w, options, leg == 0 ? ears.Move : ears.Alt, n, k, j, o, t, 0, true, legTravel)
                                                && (tracksMotion || StillOk(w, options, n.Off, false, o, t + length, true, n.Mask));
                                        }
                                        if (!moveMemo[move])
                                        {
                                            continue;
                                        }
                                        // M5 wave 5B: the load must hold over the leg; a rocking body remembers where it goes.
                                        int moveLoad = load != null ? load.Step(n.Load, LoadModel.Move(dir, leg, n.Lying)) : rockDirections ? dir + 1 : 0;
                                        if (moveLoad < 0)
                                        {
                                            continue;
                                        }
                                        // Leaving the anchor's radius ends the wait; moving inside it is still waiting there.
                                        bool away = YawMath.Planar(w.Center[o] - w.Center[n.Anchor]).magnitude > WaitAnchorRadius + 1e-3f;
                                        int run = away ? 0 : n.Run + length;
                                        if (run > options.MaxRun)
                                        {
                                            continue;
                                        }
                                        Offer(new Node
                                        {
                                            Cell = o, T = t + length, Parent = idx, Moves = n.Moves + 1, Run = run, Anchor = away ? o : n.Anchor,
                                            Gauge = Mathf.Max(0f, n.Gauge - length * drain), Flag = n.Flag, Act = Act.Move, Off = n.Off, Motion = tracksMotion,
                                            Mask = n.Mask, Load = moveLoad, Careful = carefulBase || (carefulLegs && leg == 1),
                                        });
                                    }
                                }
                            }
                        }
                    }
                    finally
                    {
                        ReturnLayer(current);
                    }
                }
                return nodes;
            }
            finally
            {
                for (int t = 0; t < layers.Length; t++)
                {
                    if (layers[t] != null)
                    {
                        ReturnLayer(layers[t]);
                        layers[t] = null;
                    }
                }
                Budget.Created = Math.Max(Budget.Created, nodes.Count);
                Budget.PerSearch.Add(Budget.Nodes - nodesBefore);
                Budget.LoadStates = Math.Max(Budget.LoadStates, load != null ? load.Count : 0);
            }
        }

        /// <summary>
        /// The search's relaxation: breadth first over (cell, lamp off, lying, in motion, door mask) per sample, with every
        /// move, stop, toggle and opening checked exactly as <see cref="Search"/> checks them, but without the wait cap, the
        /// creak gauge and the explained-once flag. Every schedule is a path of this graph, so false proves there is none.
        /// </summary>
        private static bool Reachable(World w, SearchOptions options, Ears ears, int travel, int stopCost, bool toggles, int altTravel)
        {
            int start = options.Delay;
            int horizon = w.Horizon;
            int masks = w.Masks;
            int states = w.Count * 8 * masks;
            bool tracksMotion = stopCost > 0;
            bool doors = options.Doors && w.Closed.Count > 0;
            // M5 wave 5B: both leg lengths are tried wherever the search may use them (the load is not tracked: a superset).
            bool rockDirections = RockDirections(w, options);
            int legs = altTravel > 0 ? 2 : 1;
            int reach = Math.Max(Math.Max(Math.Max(travel, altTravel) + RightSamples, stopCost), Math.Max(ToggleSamples, OpenSamples)) + 1;
            var ring = new bool[reach + 1][];
            for (int i = 0; i < ring.Length; i++)
            {
                ring[i] = new bool[states];
            }
            int State(int k, bool off, bool lying, bool motion, int mask) => (((k * 2 + (off ? 1 : 0)) * 2 + (lying ? 1 : 0)) * 2 + (motion ? 1 : 0)) * masks + mask;
            void Mark(int t, int state)
            {
                if (t <= horizon)
                {
                    ring[t % ring.Length][state] = true;
                }
            }
            Mark(start, State(w.Start, false, false, false, 0));
            for (int t = start; t < horizon; t++)
            {
                bool[] layer = ring[t % ring.Length];
                for (int state = 0; state < states; state++)
                {
                    if (!layer[state])
                    {
                        continue;
                    }
                    int mask = state % masks;
                    int rest = state / masks;
                    bool motion = (rest & 1) != 0;
                    bool lying = (rest & 2) != 0;
                    bool off = (rest & 4) != 0;
                    int k = rest >> 3;
                    if (t > start && w.InExit[k] && !w.HumanSeen(off, mask, t, k, true))
                    {
                        return true;
                    }
                    var n = new Node { Cell = k, T = t, Off = off, Lying = lying, Motion = motion, Mask = (byte)mask };
                    if (!motion && StillOk(w, options, off, lying, k, t + 1, true, mask))
                    {
                        Mark(t + 1, State(k, off, lying, false, mask));
                    }
                    if (t < start + w.Margin)
                    {
                        continue;
                    }
                    if (motion)
                    {
                        if (t + stopCost <= horizon && CheckStop(w, options, ears, n, k, t, 0, true))
                        {
                            Mark(t + stopCost, State(k, off, w.Body.Tips, false, mask));
                        }
                    }
                    else if (toggles && t + ToggleSamples <= horizon && CheckToggle(w, options, ears, n, k, t, 0, true))
                    {
                        Mark(t + ToggleSamples, State(k, !off, lying, false, mask));
                    }
                    if (doors && !motion && !lying && w.ReachBits[k] != 0 && t + OpenSamples <= horizon)
                    {
                        for (int l = 0; l < w.Closed.Count; l++)
                        {
                            int bit = w.Closed[l].Bit;
                            if ((w.ReachBits[k] & bit) != 0 && (mask & bit) == 0 && CheckOpen(w, options, n, k, l, t, 0, true))
                            {
                                Mark(t + OpenSamples, State(k, off, false, false, mask | bit));
                            }
                        }
                    }
                    List<int> around = w.Neighbors[k];
                    for (int j = 0; j < around.Count; j++)
                    {
                        int o = around[j];
                        for (int leg = 0; leg < legs; leg++)
                        {
                            // A rocking body goes on straight (leg 1) only after a move: in motion when it rocks, anywhere
                            // otherwise (the direction and the last act are not tracked here: a superset).
                            if (leg == 1 && rockDirections && tracksMotion && !motion)
                            {
                                continue;
                            }
                            int legTravel = leg == 0 ? travel : altTravel;
                            int length = legTravel + (lying ? RightSamples : 0);
                            if (t + length > horizon)
                            {
                                continue;
                            }
                            if (w.EdgeOpen(mask, w.EdgeStart[k] + j, k, o) && (options.Barred == null || !options.Barred[o])
                                && CheckMove(w, options, leg == 0 ? ears.Move : ears.Alt, n, k, j, o, t, 0, true, legTravel)
                                && (tracksMotion || StillOk(w, options, off, false, o, t + length, true, mask)))
                            {
                                Mark(t + length, State(o, off, false, tracksMotion, mask));
                            }
                        }
                    }
                }
                Array.Clear(layer, 0, states);
            }
            return false;
        }

        /// <summary>
        /// M5 wave 5B: <see cref="Reachable"/> with the load tracked exactly (CONTRACT_M5 16.5): each state of the relaxation
        /// carries the load states that reach it, the ones another of them dominates (<see cref="LoadModel.Dominates"/>)
        /// dropped. Every move, stop and opening is checked once per state and sample, then for each load state its load
        /// transition. Every schedule is still a path of this graph, so false proves there is none.
        /// </summary>
        private static bool ReachableLoaded(World w, SearchOptions options, Ears ears, int travel, int stopCost, bool toggles, int altTravel,
            LoadModel load)
        {
            int start = options.Delay;
            int horizon = w.Horizon;
            int masks = w.Masks;
            bool tracksMotion = stopCost > 0;
            bool doors = options.Doors && w.Closed.Count > 0;
            int legs = altTravel > 0 ? 2 : 1;
            int reach = Math.Max(Math.Max(Math.Max(travel, altTravel) + RightSamples, stopCost), Math.Max(ToggleSamples, OpenSamples)) + 1;
            var ring = new Dictionary<int, List<int>>[reach + 1];
            for (int i = 0; i < ring.Length; i++)
            {
                ring[i] = new Dictionary<int, List<int>>();
            }
            var pool = new Stack<List<int>>();
            int State(int k, bool off, bool lying, bool motion, int mask) => (((k * 2 + (off ? 1 : 0)) * 2 + (lying ? 1 : 0)) * 2 + (motion ? 1 : 0)) * masks + mask;
            void Mark(int t, int state, int loadState)
            {
                if (t > horizon || loadState < 0)
                {
                    return;
                }
                Dictionary<int, List<int>> layer = ring[t % ring.Length];
                if (!layer.TryGetValue(state, out List<int> held))
                {
                    held = pool.Count > 0 ? pool.Pop() : new List<int>();
                    layer[state] = held;
                }
                foreach (int other in held)
                {
                    if (load.Dominates(other, loadState))
                    {
                        return;
                    }
                }
                held.RemoveAll(other => load.Dominates(loadState, other));
                held.Add(loadState);
            }
            Mark(start, State(w.Start, false, false, false, 0), 0);
            var keys = new List<int>();
            for (int t = start; t < horizon; t++)
            {
                Dictionary<int, List<int>> layer = ring[t % ring.Length];
                keys.Clear();
                keys.AddRange(layer.Keys);
                foreach (int state in keys)
                {
                    List<int> held = layer[state];
                    int mask = state % masks;
                    int rest = state / masks;
                    bool motion = (rest & 1) != 0;
                    bool lying = (rest & 2) != 0;
                    bool off = (rest & 4) != 0;
                    int k = rest >> 3;
                    if (t > start && w.InExit[k] && !w.HumanSeen(off, mask, t, k, true))
                    {
                        return true;
                    }
                    var n = new Node { Cell = k, T = t, Off = off, Lying = lying, Motion = motion, Mask = (byte)mask };
                    if (!motion && StillOk(w, options, off, lying, k, t + 1, true, mask))
                    {
                        foreach (int ls in held)
                        {
                            Mark(t + 1, State(k, off, lying, false, mask), load.Step(ls, LoadModel.ActStill));
                        }
                    }
                    if (t >= start + w.Margin)
                    {
                        if (motion)
                        {
                            if (t + stopCost <= horizon && CheckStop(w, options, ears, n, k, t, 0, true))
                            {
                                foreach (int ls in held)
                                {
                                    Mark(t + stopCost, State(k, off, w.Body.Tips, false, mask), load.Step(ls, LoadModel.ActStop));
                                }
                            }
                        }
                        else if (toggles && t + ToggleSamples <= horizon && CheckToggle(w, options, ears, n, k, t, 0, true))
                        {
                            foreach (int ls in held)
                            {
                                Mark(t + ToggleSamples, State(k, !off, lying, false, mask), ls);
                            }
                        }
                        if (doors && !motion && !lying && w.ReachBits[k] != 0 && t + OpenSamples <= horizon)
                        {
                            for (int l = 0; l < w.Closed.Count; l++)
                            {
                                int bit = w.Closed[l].Bit;
                                if ((w.ReachBits[k] & bit) != 0 && (mask & bit) == 0 && CheckOpen(w, options, n, k, l, t, 0, true))
                                {
                                    foreach (int ls in held)
                                    {
                                        Mark(t + OpenSamples, State(k, off, false, false, mask | bit), load.Step(ls, LoadModel.ActOpen));
                                    }
                                }
                            }
                        }
                        List<int> around = w.Neighbors[k];
                        for (int j = 0; j < around.Count; j++)
                        {
                            int o = around[j];
                            int dir = DirIndex(w, k, o);
                            for (int leg = 0; leg < legs; leg++)
                            {
                                int legTravel = leg == 0 ? travel : altTravel;
                                int length = legTravel + (lying ? RightSamples : 0);
                                if (t + length > horizon)
                                {
                                    continue;
                                }
                                if (w.EdgeOpen(mask, w.EdgeStart[k] + j, k, o) && (options.Barred == null || !options.Barred[o])
                                    && CheckMove(w, options, leg == 0 ? ears.Move : ears.Alt, n, k, j, o, t, 0, true, legTravel)
                                    && (tracksMotion || StillOk(w, options, off, false, o, t + length, true, mask)))
                                {
                                    foreach (int ls in held)
                                    {
                                        Mark(t + length, State(o, off, false, tracksMotion, mask), load.Step(ls, LoadModel.Move(dir, leg, lying)));
                                    }
                                }
                            }
                        }
                    }
                }
                foreach (List<int> held in layer.Values)
                {
                    held.Clear();
                    pool.Push(held);
                }
                layer.Clear();
            }
            return false;
        }

        private static List<Node> PathTo(NodeList nodes, int goal)
        {
            var path = new List<Node>();
            for (int i = goal; i >= 0; i = nodes[i].Parent)
            {
                path.Add(nodes[i]);
            }
            path.Reverse();
            return path;
        }

        /// <summary>The schedule shifted by <paramref name="shift"/> samples, checked against what is really seen and heard.</summary>
        /// <summary>The closed leaf an opening step opened (the bit its mask gained).</summary>
        private static int OpenedLeaf(World w, Node before, Node after)
        {
            int bit = after.Mask & ~before.Mask;
            return w.Closed.FindIndex(l => l.Bit == bit);
        }

        private static bool ValidShifted(World w, SearchOptions o, List<Node> path, int shift)
        {
            for (int i = 1; i < path.Count; i++)
            {
                Node a = path[i - 1];
                Node b = path[i];
                switch (b.Act)
                {
                    case Act.Move:
                        // The leg's own length (a careful leg, a rocking body going on straight), less a lying stool's righting.
                        if (!CheckMove(w, o, null, a, a.Cell, -1, b.Cell, a.T, shift, false, b.T - a.T - (a.Lying ? RightSamples : 0)))
                        {
                            return false;
                        }
                        continue;
                    case Act.Stop:
                        if (!CheckStop(w, o, null, a, a.Cell, a.T, shift, false))
                        {
                            return false;
                        }
                        continue;
                    case Act.Toggle:
                        if (!CheckToggle(w, o, null, a, a.Cell, a.T, shift, false))
                        {
                            return false;
                        }
                        continue;
                    case Act.Open:
                        if (!CheckOpen(w, o, a, a.Cell, OpenedLeaf(w, a, b), a.T, shift, false))
                        {
                            return false;
                        }
                        continue;
                }
                int s = b.T + shift;
                if (s < 0)
                {
                    continue; // still at spawn before the level starts
                }
                if (s >= w.Samples || !StillOk(w, o, b.Off, b.Lying, b.Cell, s, false, b.Mask))
                {
                    return false;
                }
            }
            Node last = path[path.Count - 1];
            int end = last.T + shift;
            return end >= 0 && end < w.Samples && !w.HumanSeen(last.Off, last.Mask, end, last.Cell, false);
        }

        private static void Describe(World w, SearchOptions o, List<Node> path, Result result)
        {
            result.Total = path[path.Count - 1].T * SampleSeconds;
            int longest = 0;
            int explained = 0;
            int heardNear = 0;
            float peak = 0f;
            int moves = 0;
            int toggles = 0;
            int stops = 0;
            int pinned = 0;
            int opens = 0;
            for (int i = 1; i < path.Count; i++)
            {
                Node n = path[i];
                Node prev = path[i - 1];
                peak = Mathf.Max(peak, n.Gauge);
                longest = Mathf.Max(longest, n.Run);
                toggles += n.Act == Act.Toggle ? 1 : 0;
                stops += n.Act == Act.Stop ? 1 : 0;
                opens += n.Act == Act.Open ? 1 : 0;
                if (n.Move)
                {
                    moves++;
                    int length = n.T - prev.T;
                    for (int q = 1; q <= length; q++)
                    {
                        Vector3 p = Vector3.Lerp(w.Center[prev.Cell], w.Center[n.Cell], q / (float)length);
                        int s = prev.T + q;
                        bool near = false;
                        for (int h = 0; h < w.Inhabitants; h++)
                        {
                            near |= YawMath.Planar(w.Position[s, h] - p).magnitude <= w.Body.MoveNoiseRadius;
                        }
                        heardNear += near && w.Def.IsSilentFloor(p) ? 1 : 0;
                    }
                    continue;
                }
                if (n.Act == Act.Still)
                {
                    explained += w.ExplainedAt(n.Mask, n.Cell, n.T) ? 1 : 0;
                    pinned += w.Pinned[n.T] ? 1 : 0;
                }
            }
            result.LongestWait = longest * SampleSeconds;
            int early = 0;
            int late = 0;
            for (int m = 1; m <= SlackProbe && ValidShifted(w, o, path, -m); m++)
            {
                early = m;
            }
            for (int m = 1; m <= SlackProbe && ValidShifted(w, o, path, m); m++)
            {
                late = m;
            }
            result.SlackEarly = early * SampleSeconds;
            result.SlackLate = late * SampleSeconds;
            if (!ValidShifted(w, o, path, 0))
            {
                result.Failures.Add("l'horaire trouve n'est pas valide sans decalage (incoherence interne de l'audit)");
            }
            result.Notes.Add(string.Format(CultureInfo.InvariantCulture,
                "horaire : sortie a {0:0.0} s, attente la plus longue {1:0.0} s (max {2:0} s), marge {3:0.0} s en avance / {4:0.0} s en retard, " +
                "{5} deplacements de case, grincement au plus {6:0.00}, {7} echantillons expliques par un leurre, {8} echantillons sur tapis a portee d'oreille",
                result.Total, result.LongestWait, Tuning.AuditMaxWait, result.SlackEarly, result.SlackLate, moves, peak, explained, heardNear)
                + (toggles > 0 ? $", {toggles} interrupteur(s)" : "")
                + (stops > 0 ? (w.RockSamples > 0 && !w.Body.Glides ? $", {stops} bascule(s)" : $", {stops} arret(s) glisse(s)") : "")
                + (pinned > 0 ? string.Format(CultureInfo.InvariantCulture, ", assis dessus {0:0.0} s", pinned * SampleSeconds) : "")
                + (opens > 0 ? $", {opens} porte(s) ouverte(s)" : ""));
        }

        /// <summary>
        /// The schedule as a designerRoute (docs/CONTRACT_M2.md 4): one waypoint per run of at most
        /// <see cref="RouteStride"/> straight moves, timed at the departure of the run, then the exit center. M4: a lamp
        /// switch is a step with the "toggle" action at the cell it happens on; a stool's steps are all careful. M5 wave 5B: a
        /// load's careful legs are "careful" (a waypoint never mixes careful and full speed moves), and a rocking body's
        /// waypoint that goes on from the last one without stopping takes the last one's "at", so the replay never waits (and
        /// rests, and rocks) in the middle of a run.
        /// </summary>
        private static List<RouteStepDef> Route(World w, List<Node> path)
        {
            var route = new List<RouteStepDef>();
            bool careful = w.Body.Tips;
            int i = 0;
            while (i < path.Count - 1)
            {
                Node next = path[i + 1];
                if (next.Act == Act.Toggle)
                {
                    Vector3 here = w.Center[path[i].Cell];
                    route.Add(new RouteStepDef
                    {
                        X = Round(here.x, 100f), Z = Round(here.z, 100f), At = Round(path[i].T * SampleSeconds, 10f),
                        Action = RouteStepDef.ActionToggle, Careful = careful,
                    });
                    i++;
                    continue;
                }
                if (next.Act == Act.Open)
                {
                    // M5 (CONTRACT_M5 8): "open" presses E at the cell, naming the leaf.
                    Vector3 here = w.Center[path[i].Cell];
                    route.Add(new RouteStepDef
                    {
                        X = Round(here.x, 100f), Z = Round(here.z, 100f), At = Round(path[i].T * SampleSeconds, 10f),
                        Action = RouteStepDef.ActionOpen, Door = w.Closed[OpenedLeaf(w, path[i], next)].Door.Id, Careful = careful,
                    });
                    i++;
                    continue;
                }
                if (!next.Move)
                {
                    i++;
                    continue;
                }
                int depart = path[i].T;
                int j = i + 1;
                Vector3 step = w.Center[path[j].Cell] - w.Center[path[i].Cell];
                while (j + 1 < path.Count && j - i < RouteStride && path[j + 1].Move && path[j + 1].Careful == next.Careful
                       && (w.Center[path[j + 1].Cell] - w.Center[path[j].Cell] - step).sqrMagnitude < 1e-6f)
                {
                    j++;
                }
                Vector3 c = w.Center[path[j].Cell];
                float at = Round(depart * SampleSeconds, 10f);
                if (w.Body.Rocks && path[i].Move && route.Count > 0)
                {
                    at = route[route.Count - 1].At; // the run goes on: no wait, no rest, no rock
                }
                route.Add(new RouteStepDef { X = Round(c.x, 100f), Z = Round(c.z, 100f), At = at, Careful = careful || next.Careful });
                i = j;
            }
            float last = route.Count > 0 ? route[route.Count - 1].At : 0f;
            route.Add(new RouteStepDef { X = w.Def.Exit.X, Z = w.Def.Exit.Z, At = last, Careful = careful });
            return route;
        }

        private static float Round(float v, float scale) => Mathf.Round(v * scale) / scale;

        private static bool SameRoute(List<RouteStepDef> a, List<RouteStepDef> b)
        {
            if (a == null || b == null || a.Count != b.Count)
            {
                return false;
            }
            for (int i = 0; i < a.Count; i++)
            {
                if (Mathf.Abs(a[i].X - b[i].X) > 1e-3f || Mathf.Abs(a[i].Z - b[i].Z) > 1e-3f || Mathf.Abs(a[i].At - b[i].At) > 1e-3f
                    || a[i].Careful != b[i].Careful || a[i].Action != b[i].Action || a[i].Door != b[i].Door)
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>One designerRoute step as <see cref="WriteRoute"/> writes it.</summary>
        private static string RouteStepJson(RouteStepDef r)
        {
            string F(float v) => v.ToString("0.0#", CultureInfo.InvariantCulture);
            string extra = (r.Careful ? ", \"careful\": true" : "") + (r.Action != null ? $", \"action\": \"{r.Action}\"" : "")
                + (r.Door != null ? $", \"door\": \"{r.Door}\"" : "");
            return $"{{ \"x\": {F(r.X)}, \"z\": {F(r.Z)}, \"at\": {F(r.At)}{extra} }}";
        }

        /// <summary>
        /// M5 wave 5B: a route on one line, as a designerRoute array (the counter-routes of the rock, load and robot lessons, for
        /// the levels agent's replays).
        /// </summary>
        private static string RouteJson(List<RouteStepDef> route)
        {
            return "[" + string.Join(", ", route.ConvertAll(RouteStepJson)) + "]";
        }

        /// <summary>Writes the route into the level file, keeping the rest of the file as it is written.</summary>
        public static void WriteRoute(string file, List<RouteStepDef> route)
        {
            string text = File.ReadAllText(file);
            var sb = new StringBuilder();
            sb.Append("\"designerRoute\": [\n");
            for (int i = 0; i < route.Count; i++)
            {
                sb.Append("    " + RouteStepJson(route[i]));
                sb.Append(i + 1 < route.Count ? ",\n" : "\n");
            }
            sb.Append("  ]");
            var existing = new Regex("\"designerRoute\"\\s*:\\s*\\[[^\\]]*\\]", RegexOptions.Singleline);
            if (existing.IsMatch(text))
            {
                text = existing.Replace(text, sb.ToString(), 1);
            }
            else
            {
                var inhabitants = new Regex("(?m)^(\\s*)\"inhabitants\"\\s*:");
                Match m = inhabitants.Match(text);
                if (!m.Success)
                {
                    throw new InvalidOperationException("no \"inhabitants\" key to insert the route before in " + file);
                }
                text = text.Substring(0, m.Index) + m.Groups[1].Value + sb + ",\n" + text.Substring(m.Index);
            }
            LevelDef check = LevelJson.Parse(text);
            if (check.DesignerRoute.Count != route.Count)
            {
                throw new InvalidOperationException("the written route does not read back in " + file);
            }
            File.WriteAllText(file, text);
        }

        // ----- 4. Map -----

        private static string Map(World w, List<Node> path)
        {
            var onPath = new HashSet<int>();
            foreach (Node n in path)
            {
                onPath.Add(n.Cell);
            }
            int samples = w.Horizon;
            var sb = new StringBuilder();
            sb.AppendLine("  carte (haut = +z) : # bloque, 0-9 = part du temps non vue (! sous 25 %), c case expliquee par un leurre, * horaire, S depart, E sortie");
            for (int r = 0; r < w.Rooms.Count; r++)
            {
                if (w.Rooms.Count > 1)
                {
                    sb.AppendLine($"  piece {w.Rooms[r].Id ?? (r + 1).ToString()} :");
                }
                for (int j = w.Size[r].nz - 1; j >= 0; j--)
                {
                    sb.Append("    ");
                    for (int i = 0; i < w.Size[r].nx; i++)
                    {
                        int k = w.Index[(r, i, j)];
                        char ch;
                        if (!w.Walkable[k])
                        {
                            ch = '#';
                        }
                        else if (k == w.Start)
                        {
                            ch = 'S';
                        }
                        else if (w.InExit[k])
                        {
                            ch = 'E';
                        }
                        else if (onPath.Contains(k))
                        {
                            ch = '*';
                        }
                        else if (w.ExplainedAny[k])
                        {
                            ch = 'c';
                        }
                        else
                        {
                            int unseen = 0;
                            for (int s = 0; s < samples; s++)
                            {
                                unseen += w.MovingSeen(false, 0, s, k, false) ? 0 : 1;
                            }
                            float f = unseen / (float)samples;
                            ch = f < Tuning.AuditMinUnseenFraction ? '!' : (char)('0' + Mathf.Min(9, Mathf.FloorToInt(f * 10f)));
                        }
                        sb.Append(ch).Append(' ');
                    }
                    sb.AppendLine();
                }
            }
            return sb.ToString();
        }

        // ----- Screenshots of the built levels (a tool, not a check) -----

        /// <summary>
        /// Batch tool: builds every level of levels.json in an editor scene and renders two views of each to
        /// TestResults/shots-world (a top view of the whole house and the start view of the orbit camera,
        /// with the wall fader applied), so the generated rooms can be looked at without a player build.
        /// </summary>
        public static void ShootLevels()
        {
            int code = 0;
            try
            {
                string dir = Path.Combine("TestResults", "shots-world");
                Directory.CreateDirectory(dir);
                foreach (string id in ManifestLevels())
                {
                    LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelsFolder, id + ".json")));
                    EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                    LevelInstance level = LevelBuilder.Build(def);
                    try
                    {
                        var sun = new GameObject("Sun").AddComponent<Light>();
                        sun.type = LightType.Directional;
                        sun.color = new Color(1f, 0.9f, 0.76f);
                        sun.intensity = 1.35f;
                        sun.shadows = LightShadows.Soft;
                        sun.transform.rotation = Quaternion.Euler(48f, 28f, 0f);
                        RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Trilight;
                        RenderSettings.ambientSkyColor = new Color(0.62f, 0.64f, 0.70f);
                        RenderSettings.ambientEquatorColor = new Color(0.52f, 0.47f, 0.42f);
                        RenderSettings.ambientGroundColor = new Color(0.30f, 0.25f, 0.21f);
                        var cam = new GameObject("ShotCamera").AddComponent<Camera>();
                        cam.clearFlags = CameraClearFlags.SolidColor;
                        cam.backgroundColor = new Color(0.15f, 0.16f, 0.19f);
                        cam.fieldOfView = 55f;
                        cam.nearClipPlane = 0.05f;
                        cam.farClipPlane = 80f;
                        var fader = level.Root.GetComponent<WallFader>();
                        // The very first render of a fresh editor comes out uniformly tinted while the
                        // shaders warm up: render once into a texture and throw it away (batch mode has no
                        // back buffer, so a camera never renders without a target here).
                        var warm = new RenderTexture(64, 64, 24);
                        cam.targetTexture = warm;
                        cam.Render();
                        cam.targetTexture = null;
                        UnityEngine.Object.DestroyImmediate(warm);

                        Rect b = def.InteriorBounds();
                        var center = new Vector3(b.center.x, 0f, b.center.y);
                        float span = Mathf.Max(b.width, b.height);
                        Shoot(cam, fader, center + new Vector3(0f, span * 1.25f, -span * 0.55f), Quaternion.Euler(65f, 0f, 0f), Path.Combine(dir, id + "_top.png"));

                        Vector3 focus = def.Player.Position + Vector3.up * (def.Player.SizeY * 0.5f + Tuning.CameraTargetHeight);
                        Quaternion orbit = Quaternion.Euler(Tuning.PitchDefault, def.Player.Yaw, 0f);
                        Shoot(cam, fader, focus - orbit * Vector3.forward * Tuning.OrbitDistance, orbit, Path.Combine(dir, id + "_start.png"));
                    }
                    finally
                    {
                        LevelBuilder.Teardown(level);
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[LevelAudit] shots threw: " + e);
                code = 1;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static void Shoot(Camera cam, WallFader fader, Vector3 position, Quaternion rotation, string file)
        {
            cam.transform.SetPositionAndRotation(position, rotation);
            if (fader != null)
            {
                fader.Apply(position);
            }
            var rt = new RenderTexture(1280, 720, 24);
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
            tex.Apply();
            File.WriteAllBytes(file, tex.EncodeToPNG());
            RenderTexture.active = null;
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(rt);
            UnityEngine.Object.DestroyImmediate(tex);
            Debug.Log($"[LevelAudit] shot {file} (faces hidden: {(fader != null ? fader.HiddenCount : 0)})");
        }
    }
}
