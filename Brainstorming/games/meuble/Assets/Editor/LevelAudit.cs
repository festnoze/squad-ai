using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using Meuble.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Meuble.Editor
{
    /// <summary>
    /// Level audit (PRD 10.3, docs/CONTRACT_M2.md 6 and 11.7), against the real built level, its real
    /// colliders, its runtime NavMesh and the real routine, in edit mode:
    /// 1. every walk between consecutive stations has a complete NavMesh path;
    /// 2. the level stays within the budgets of PRD 7.4 (renderers, materials, triangles per furniture);
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
        // 180 s horizon.
        private const int HorizonSamples = 1800;
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
        // Largest shift tried when measuring the slack (3 s).
        private const int SlackProbe = 30;
        // The wait rule counts the time spent within this distance of where the wait began (M2.2): a 0.5 m
        // step out and back does not restart the clock; only leaving this radius does.
        private const float WaitAnchorRadius = 1f;
        // Start delay sweep (M2.2): the player starts acting every this many samples (1 s) over one loop.
        private const int SweepEvery = 10;
        // Self-test fixtures that must fail: Resources/Levels/test_*.json, never listed in levels.json, each named
        // after the one rule that must make it fail (see Fixtures). Other test_*.json files (probe levels of other
        // agents) are not audit fixtures.
        public const string FixturePrefix = "test_";

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
            public bool Pass => Failures.Count == 0;
        }

        /// <summary>The level ids of levels.json, in play order.</summary>
        public static List<string> ManifestLevels()
        {
            string path = Path.Combine(LevelsFolder, LevelManifest.FileName + ".json");
            return File.Exists(path) ? LevelManifest.Parse(File.ReadAllText(path)) : new List<string>();
        }

        /// <summary>
        /// Design aid: "-auditLevels id1,id2" audits these level files instead of levels.json (fixtures and levels not in
        /// the manifest included), and "-skipFixtures" skips the self-test. verify.sh uses neither.
        /// </summary>
        public const string LevelsFlag = "-auditLevels";
        public const string SkipFixturesFlag = "-skipFixtures";
        /// <summary>Design aid: "-skipSweep" skips the start delay sweep (a warning only).</summary>
        public const string SkipSweepFlag = "-skipSweep";
        private static bool skipSweep;
        /// <summary>Design aid: "-debugSamples 20,40" prints what is seen at these samples.</summary>
        public const string DebugSamplesFlag = "-debugSamples";
        private static List<int> debugSamples = new List<int>();

        /// <summary>Batch entry point: audits every level of levels.json, exits 0 when all pass.</summary>
        public static void RunBatch()
        {
            string[] args = Environment.GetCommandLineArgs();
            bool write = Array.IndexOf(args, WriteRoutesFlag) >= 0;
            skipSweep = Array.IndexOf(args, SkipSweepFlag) >= 0;
            int dbg = Array.IndexOf(args, DebugSamplesFlag);
            debugSamples = new List<int>();
            if (dbg >= 0 && dbg + 1 < args.Length)
            {
                foreach (string part in args[dbg + 1].Split(','))
                {
                    debugSamples.Add(int.Parse(part, CultureInfo.InvariantCulture));
                }
            }
            int at = Array.IndexOf(args, LevelsFlag);
            List<string> only = at >= 0 && at + 1 < args.Length ? new List<string>(args[at + 1].Split(',')) : null;
            int code = RunAll(write, only, Array.IndexOf(args, SkipFixturesFlag) < 0);
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static int RunAll(bool writeRoutes)
        {
            return RunAll(writeRoutes, null, true);
        }

        private static int RunAll(bool writeRoutes, List<string> only, bool fixtures)
        {
            int code = 0;
            try
            {
                List<string> ids = only ?? ManifestLevels();
                if (ids.Count == 0)
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
                    if (writeRoutes && r.Pass && r.Route != null)
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
                if (fixtures && !RunFixtures())
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
            foreach (InhabitantDef inhabitant in def.Inhabitants)
            {
                int n = inhabitant.Stations.Count;
                for (int i = 0; i < n; i++)
                {
                    Vector3 a = inhabitant.Stations[i].Position;
                    Vector3 b = inhabitant.Stations[(i + 1) % n].Position;
                    string label = $"{inhabitant.Name} marche {i + 1} -> {(i + 1) % n + 1}";
                    if (!level.Planner.TryPlan(a, b, corners))
                    {
                        result.Failures.Add($"{label} ({a.x}, {a.z}) -> ({b.x}, {b.z}) : aucun chemin NavMesh complet");
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
            // M3 (docs/CONTRACT_M3.md 9): every material slot counts, and skinned meshes count their triangles.
            Probe.RenderCount count = Probe.CountRenderers(level.Root.GetComponentsInChildren<Renderer>(false));
            int renderers = count.Renderers;
            HashSet<Material> materials = count.Materials;
            result.Notes.Add($"budgets : {renderers} renderers (max {BudgetRenderers}), {materials.Count} materiaux (max {BudgetMaterials}), "
                + $"{count.MaterialSlots} emplacements, {count.Triangles} triangles, {level.ModelVisuals.Count} modeles");
            if (renderers > BudgetRenderers)
            {
                result.Failures.Add($"{renderers} renderers, au dessus du budget de {BudgetRenderers}");
            }
            if (materials.Count > BudgetMaterials)
            {
                result.Failures.Add($"{materials.Count} materiaux, au dessus du budget de {BudgetMaterials}");
            }
            foreach (Inhabitant inhabitant in level.Inhabitants)
            {
                long t = Probe.TrianglesUnder(inhabitant.transform);
                int bones = Probe.BonesUnder(inhabitant.transform);
                if (t > Tuning.BudgetInhabitantTriangles)
                {
                    result.Failures.Add($"habitant {inhabitant.name} : {t} triangles, au dessus du budget de {Tuning.BudgetInhabitantTriangles}");
                }
                if (bones > Tuning.BudgetInhabitantBones)
                {
                    result.Failures.Add($"habitant {inhabitant.name} : {bones} os, au dessus du budget de {Tuning.BudgetInhabitantBones}");
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
                if (triangles > BudgetFurnitureTriangles)
                {
                    result.Failures.Add($"meuble {child.name} : {triangles} triangles, au dessus du budget de {BudgetFurnitureTriangles}");
                }
            }
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
            public bool Glides;
            public bool Tips;
            public bool Lamp;

            public static BodyModel Of(BodyDef body)
            {
                float speed = body.MaxSpeed * (body.Tips ? Tuning.CarefulFactor : 1f);
                return new BodyModel
                {
                    Body = body,
                    Radius = body.Radius,
                    Height = body.Size.y,
                    MoveSamples = CellSamples(body, speed),
                    FullSpeedMoveSamples = CellSamples(body, body.MaxSpeed),
                    RingRadius = ChairRingRadius * TopHalfDiagonal(body.Size) / TopHalfDiagonal(BodyDef.For(BodyKinds.Chair).Size),
                    MoveNoiseRadius = Hearing.RadiusOf(body.Glides ? NoiseKind.Roll : NoiseKind.Hop),
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

        /// <summary>Everything the search reads, precomputed over the whole horizon.</summary>
        private sealed class World
        {
            public LevelDef Def;
            public BodyModel Body;
            public List<RoomDef> Rooms;
            public int Count;
            public Vector3[] Center;
            public int[] Room;
            public int[] I;
            public int[] J;
            public (int nx, int nz)[] Size;
            public Dictionary<(int, int, int), int> Index;
            public bool[] Walkable;
            /// <summary>In place at the spawn (the slot before any sit on the player).</summary>
            public bool[] InPlace;
            public bool[] Explained;
            public bool[] InExit;
            public List<int>[] Neighbors;
            public int Samples;
            public int Inhabitants;
            /// <summary>[sample, cell]: seen by any inhabitant, as sampled, the light on (every body but a dark lamp).</summary>
            public bool[,] Seen;
            /// <summary>[sample, cell]: seen at any sample within the margin.</summary>
            public bool[,] SeenWide;
            /// <summary>M4 lamp: the same with the lamp switched off (the range is LampOffLight times the view range).</summary>
            public bool[,] SeenDark;
            public bool[,] SeenDarkWide;
            /// <summary>[sample, inhabitant]: planar position.</summary>
            public Vector3[,] Position;
            public int Start;
            public bool NeedDecoy;
            /// <summary>Samples of the first routine loop (the horizon when it never loops).</summary>
            public int LoopSamples;

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
            /// <summary>[sample]: the player is sat on (pinned): the creak gauge pauses.</summary>
            public bool[] Pinned;
            /// <summary>[sample]: index in <see cref="InPlaceBySlot"/> of the player's slot (0, the spawn, until a sit on the player).</summary>
            public int[] Slot;
            public readonly List<bool[]> InPlaceBySlot = new List<bool[]>();
            /// <summary>The pose of each slot: the spawn, then every seat home the player was sat on at.</summary>
            public readonly List<Vector3> SlotHomes = new List<Vector3>();

            public bool InPlaceAt(int k, int s)
            {
                return InPlaceBySlot[Slot[Mathf.Clamp(s, 0, Samples - 1)]][k];
            }

            public bool SeenAt(bool dark, int s, int k, bool wide)
            {
                return dark ? (wide ? SeenDarkWide : SeenDark)[s, k] : (wide ? SeenWide : Seen)[s, k];
            }

            public bool ForcedAt(int s, bool wide)
            {
                return wide ? ForcedWide[s] : Forced[s];
            }

            public bool InSeatCell(int k, int s, bool wide)
            {
                int seat = wide ? ForcedSeatWide[s] : ForcedSeat[s];
                return seat >= 0 && SeatCells[seat].Contains(k);
            }
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
        }

        private struct Node
        {
            public int Cell;
            public int T;
            public int Parent;
            public int Moves;
            /// <summary>Samples spent within <see cref="WaitAnchorRadius"/> of <see cref="Anchor"/> since it was set.</summary>
            public int Run;
            public int Anchor;
            public float Gauge;
            public bool Flag;
            public Act Act;
            /// <summary>M4: the lamp is switched off.</summary>
            public bool Off;
            /// <summary>M4: arrived by a move and not stopped yet (only for a body whose stop costs samples).</summary>
            public bool Motion;
            /// <summary>M4: the stool lies on its side (full speed search only).</summary>
            public bool Lying;
            public bool Move => Act == Act.Move;
        }

        private static void CheckSchedule(LevelDef def, LevelInstance level, Result result)
        {
            World w = BuildWorld(def, level, true);
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
            if (Array.IndexOf(w.Forced, true) >= 0)
            {
                result.Notes.Add("assis sur le joueur (presence au siege, de l'instant de l'assise a la fin de l'epingle) : " + Intervals(w.Forced, HorizonSamples));
            }
            var strict = new SearchOptions { NeedDecoy = w.NeedDecoy };
            List<Node> nodes = Search(w, strict, out int goal);
            if (goal < 0)
            {
                result.Failures.Add($"aucun horaire du depart a la sortie en {HorizonSamples * SampleSeconds:0} s{(w.NeedDecoy ? " qui se serve d'un leurre" : "")} : " +
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
                result.Route = Route(w, path);
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
            foreach (int sample in debugSamples)
            {
                result.Notes.Add(SeenMap(w, sample));
            }
            if (!skipSweep)
            {
                Sweep(w, result);
            }
            if (path.Count > 0)
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
                    List<Node> fullNodes = Search(w, new SearchOptions { FullSpeed = true }, out int fullSpeed);
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
                    List<Node> litNodes = Search(w, new SearchOptions { Toggles = false }, out int lit);
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
                    // CONTRACT_M4 10.5: darkness is not a free pass: the loop passes within the dark range of the lamp's
                    // path at least once (there, a careless lamp is seen and switched on).
                    float darkRange = Tuning.ViewRange * Tuning.LampOffLight;
                    float nearest = float.MaxValue;
                    int when = -1;
                    for (int s = 0; s < HorizonSamples; s++)
                    {
                        for (int h = 0; h < w.Inhabitants; h++)
                        {
                            foreach (Node n in path)
                            {
                                float d = YawMath.Planar(w.Position[s, h] - w.Center[n.Cell]).magnitude;
                                if (d < nearest)
                                {
                                    nearest = d;
                                    when = s;
                                }
                            }
                        }
                    }
                    string near = string.Format(CultureInfo.InvariantCulture, "{0:0.0} m du chemin de la lampe a {1:0.0} s (portee dans le noir {2:0.0} m)",
                        nearest, when * SampleSeconds, darkRange);
                    if (nearest > darkRange)
                    {
                        result.Failures.Add("lecon dark : l'habitant ne passe jamais a portee dans le noir du chemin de la lampe (au plus pres " + near + ") : le noir est un passe-droit");
                    }
                    else
                    {
                        result.Notes.Add("lecon dark : l'habitant passe a " + near + " : le noir ne suffit pas, il faut choisir le moment");
                    }
                    return;
                }
                case LevelDef.LessonGlide:
                {
                    List<Node> naiveNodes = Search(w, new SearchOptions { StopSamples = 0, NeedDecoy = w.NeedDecoy }, out int naive);
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
                    List<Node> freeNodes = Search(free, new SearchOptions { NeedDecoy = free.NeedDecoy }, out int freeGoal);
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
                default:
                    result.Failures.Add($"lecon '{def.Lesson}' inconnue");
                    return;
            }
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
                    if (s < w.Samples && (w.SeenAt(m.Off, s, m.Cell, false) || w.ForcedAt(s, false)))
                    {
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
                List<Node> n = Search(world, o, out int g);
                if (g >= 0)
                {
                    found.Add(what + " (" + Summary(world, PathTo(n, g)) + ")");
                }
            }
            Try("sans plafond d'attente", w, new SearchOptions { MaxRun = HorizonSamples, NeedDecoy = w.NeedDecoy });
            foreach (int cap in new[] { 90, 100, 120 })
            {
                Try(string.Format(CultureInfo.InvariantCulture, "avec un plafond de {0:0} s", cap * SampleSeconds), w, new SearchOptions { MaxRun = cap, NeedDecoy = w.NeedDecoy });
            }
            Try("sans bruit", w, new SearchOptions { Noise = false, NeedDecoy = w.NeedDecoy });
            Try("sans grincement", w, new SearchOptions { GaugeCap = float.MaxValue, NeedDecoy = w.NeedDecoy });
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
                        char ch = here ? '!' : !w.Walkable[k] ? '#' : w.Seen[s, k] ? 'x' : '.';
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
                bool stopHere = n.Act == Act.Stop || n.Act == Act.Toggle || (n.Act == Act.Still && path[i - 1].Act == Act.Move);
                if (stopHere)
                {
                    Vector3 c = w.Center[n.Cell];
                    sb.Append(string.Format(CultureInfo.InvariantCulture, " ; {0} ({1:0.##}, {2:0.##}) a {3:0.0} s",
                        n.Act == Act.Toggle ? "interrupteur" : "arret", c.x, c.z, path[i - 1].T * SampleSeconds));
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
            var failing = new List<string>();
            for (int d = 0; d < w.LoopSamples; d += SweepEvery)
            {
                List<Node> nodes = Search(w, new SearchOptions { Delay = d }, out int goal);
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
                SweepEvery * SampleSeconds, w.LoopSamples * SampleSeconds, failing.Count, result.WorstDelay, result.WorstDelayTime, result.SweepLongestWait));
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
        }

        private static readonly FixtureRule[] Fixtures =
        {
            new FixtureRule
            {
                Rule = "wait", Strict = "attente de 8 s au plus", Relaxed = "attente illimitee",
                StrictOptions = () => new SearchOptions(), RelaxedOptions = () => new SearchOptions { MaxRun = HorizonSamples },
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
        };

        /// <summary>The ids of the self-test fixtures, in order.</summary>
        public static List<string> FixtureIds()
        {
            var ids = new List<string>();
            foreach (FixtureRule f in Fixtures)
            {
                ids.Add(FixturePrefix + f.Rule);
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
            bool ok = true;
            var sb = new StringBuilder();
            sb.AppendLine($"[LevelAudit] Auto-test : {Fixtures.Length} niveaux qui doivent echouer, chacun pour sa regle");
            foreach (FixtureRule rule in Fixtures)
            {
                string id = FixturePrefix + rule.Rule;
                string file = Path.Combine(LevelsFolder, id + ".json");
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
                try
                {
                    Physics.SyncTransforms();
                    World w = BuildWorld(def, level, true);
                    Search(w, rule.StrictOptions(), out int strict);
                    World relaxedWorld = rule.RelaxedWithoutSitting ? BuildWorld(def, level, false) : w;
                    List<Node> nodes = Search(relaxedWorld, rule.RelaxedOptions(), out int loose);
                    if (strict >= 0)
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
                        centers.Add(new Vector3(room.MinX + (i + 0.5f) * cell, 0f, room.MinZ + (j + 0.5f) * cell));
                        rooms.Add(r);
                        iis.Add(i);
                        jjs.Add(j);
                    }
                }
            }
            int n = w.Count = centers.Count;
            w.Center = centers.ToArray();
            w.Room = rooms.ToArray();
            w.I = iis.ToArray();
            w.J = jjs.ToArray();
            w.Walkable = new bool[n];
            w.Explained = new bool[n];
            w.InExit = new bool[n];
            BodyModel body = w.Body;
            float cr = body.Radius;
            string kind = body.Body.Kind;
            foreach (DecoyDef d in def.Decoys)
            {
                w.NeedDecoy |= BodyKinds.Of(d.Kind) == kind;
            }
            for (int k = 0; k < n; k++)
            {
                Vector3 c = w.Center[k];
                w.Walkable[k] = !Physics.CheckCapsule(c + Vector3.up * (cr + 0.05f), c + Vector3.up * (body.Height - cr),
                    cr, Layers.ChairBlockerMask, QueryTriggerInteraction.Ignore);
                foreach (DecoyDef d in def.Decoys)
                {
                    bool sameKind = BodyKinds.Of(d.Kind) == kind;
                    w.Explained[k] |= sameKind && YawMath.Planar(c - d.Position).magnitude <= ExplainedRadius;
                }
                w.InExit[k] = def.Exit.Contains(c);
            }
            w.InPlace = InPlaceAround(w, def.Player.Position);
            w.InPlaceBySlot.Add(w.InPlace);
            w.SlotHomes.Add(YawMath.Planar(def.Player.Position));

            // Neighbors: 4-connected inside a room, and across a doorway between two rooms, each move swept
            // by the body's capsule so a door jamb or a thin prop between two cells is never crossed.
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
                    if (w.Index.TryGetValue((w.Room[k], w.I[k] + di, w.J[k] + dj), out int o) && w.Walkable[o] && Clear(body, w.Center[k], w.Center[o]))
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
                            && Mathf.Abs(at - along) <= door.Width * 0.5f - cr + 1e-3f && Clear(body, w.Center[a], w.Center[b]))
                        {
                            w.Neighbors[a].Add(b);
                            w.Neighbors[b].Add(a);
                        }
                    }
                }
            }
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

            // The routine, stepped exactly as the game steps it, sampled over the whole horizon (no loop
            // assumed: what the search sees is what the game plays). The seat check (SeatOccupied null) always
            // finds the player home: the search forces it there.
            var routines = new List<InhabitantRoutine>();
            foreach (InhabitantDef inhabitant in def.Inhabitants)
            {
                routines.Add(new InhabitantRoutine(inhabitant.Stations, inhabitant.StartStation, level.Planner) { SittingEnabled = sitting });
            }
            int samples = w.Samples = HorizonSamples + MarginSamples + 1;
            w.LoopSamples = HorizonSamples;
            w.Inhabitants = routines.Count;
            w.Seen = new bool[samples, n];
            w.SeenDark = new bool[samples, n];
            w.Position = new Vector3[samples, routines.Count];
            w.Forced = new bool[samples];
            w.ForcedSeat = new int[samples];
            w.Pinned = new bool[samples];
            w.Slot = new int[samples];
            var rings = new Vector3[n][];
            float top = body.Height - Tuning.SampleInset;
            for (int k = 0; k < n; k++)
            {
                rings[k] = new Vector3[RingCount + 1];
                rings[k][0] = w.Center[k] + Vector3.up * (body.Height * 0.5f);
                for (int a = 0; a < RingCount; a++)
                {
                    rings[k][a + 1] = w.Center[k] + YawMath.Forward(a * 360f / RingCount) * body.RingRadius + Vector3.up * top;
                }
            }
            bool lamp = body.Lamp;
            float darkRange = Tuning.ViewRange * Tuning.LampOffLight;
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
                if (w.LoopSamples == HorizonSamples && routines.Count > 0 && routines[0].LoopsCompleted >= 1)
                {
                    w.LoopSamples = s;
                }
                for (int i = 0; i < routines.Count; i++)
                {
                    InhabitantRoutine r = routines[i];
                    w.Position[s, i] = YawMath.Planar(r.Position);
                    Vector3 eye = r.EyePosition;
                    Vector3 forward = r.EyeForward;
                    for (int k = 0; k < n; k++)
                    {
                        if (!w.Walkable[k] || (w.Seen[s, k] && (!lamp || w.SeenDark[s, k])))
                        {
                            continue;
                        }
                        foreach (Vector3 p in rings[k])
                        {
                            if (VisionMath.IsInCone(eye, forward, p, Tuning.ViewRange, Tuning.ViewHalfAngle) && !Vision.Occluded(eye, p))
                            {
                                w.Seen[s, k] = true;
                                // CONTRACT_M4 2.3: switched off, the lamp's own samples are seen within the dark range only.
                                if (lamp && VisionMath.IsInCone(eye, forward, p, darkRange, Tuning.ViewHalfAngle))
                                {
                                    w.SeenDark[s, k] = true;
                                }
                                if (!lamp || w.SeenDark[s, k])
                                {
                                    break;
                                }
                            }
                        }
                    }
                }
            }
            SetMargin(w, MarginSamples);
            return w;
        }

        /// <summary>Recomputes every table dilated by the margin (sight, dark sight, the sitter's pin) for a new margin.</summary>
        private static void SetMargin(World w, int margin)
        {
            w.Margin = margin;
            int samples = w.Samples;
            w.SeenWide = Dilate(w.Seen, samples, w.Count, margin);
            w.SeenDarkWide = Dilate(w.SeenDark, samples, w.Count, margin);
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

        /// <summary>Cells whose center stands within <see cref="InPlaceRadius"/> of <paramref name="home"/>.</summary>
        private static bool[] InPlaceAround(World w, Vector3 home)
        {
            var inPlace = new bool[w.Count];
            for (int k = 0; k < w.Count; k++)
            {
                inPlace[k] = YawMath.Planar(w.Center[k] - home).magnitude <= InPlaceRadius;
            }
            return inPlace;
        }

        /// <summary>The slot index of a seat home (a new slot the first time); slot 0 is the spawn.</summary>
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
            w.InPlaceBySlot.Add(InPlaceAround(w, home));
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
            w.SeatHomes.Add(home);
            w.SeatCells.Add(cells);
            return w.SeatHomes.Count - 1;
        }

        private static bool[,] Dilate(bool[,] seen, int samples, int n, int margin)
        {
            var wide = new bool[samples, n];
            for (int s = 0; s < samples; s++)
            {
                for (int k = 0; k < n; k++)
                {
                    bool any = false;
                    for (int q = Mathf.Max(0, s - margin); q <= Mathf.Min(samples - 1, s + margin) && !any; q++)
                    {
                        any = seen[q, k];
                    }
                    wide[s, k] = any;
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
        private static bool StillOk(World w, SearchOptions o, bool dark, bool lying, int k, int s, bool wide)
        {
            if (w.ForcedAt(s, wide) && !w.InSeatCell(k, s, wide))
            {
                return false;
            }
            if (!w.SeenAt(dark, s, k, wide))
            {
                return true;
            }
            if (lying || (w.Body.Lamp && dark))
            {
                return false;
            }
            return w.InPlaceAt(k, s) || (o.Decoys && w.Explained[k]);
        }

        /// <summary>Moving at cells a and b on sample s: in the horizon, unseen at both, and not where a sitter forces the player still.</summary>
        private static bool MovingOk(World w, bool dark, int s, int a, int b, bool wide)
        {
            return s >= 0 && s < w.Samples && !w.SeenAt(dark, s, a, wide) && !w.SeenAt(dark, s, b, wide) && !w.ForcedAt(s, wide);
        }

        /// <summary>
        /// A noise of <paramref name="radius"/> at <paramref name="p"/> on sample s reaches an inhabitant (radius plus the
        /// hearing margin), at that sample or, when <paramref name="wide"/>, within the margin. CONTRACT_M4 10.6: every
        /// furniture noise (hop, topple, click, roll) is silent on a rug or a soft floor.
        /// </summary>
        private static bool Heard(World w, Vector3 p, int s, float radius, bool wide)
        {
            if (w.Def.IsSilentFloor(p))
            {
                return false;
            }
            float reach = radius + NoiseMargin;
            int from = wide ? Mathf.Max(0, s - w.Margin) : s;
            int to = wide ? Mathf.Min(w.Samples - 1, s + w.Margin) : s;
            for (int r = from; r <= to; r++)
            {
                for (int i = 0; i < w.Inhabitants; i++)
                {
                    if (YawMath.Planar(w.Position[r, i] - p).magnitude <= reach)
                    {
                        return true;
                    }
                }
            }
            return false;
        }

        /// <summary>Samples of the travel over one cell under these options.</summary>
        private static int TravelSamples(World w, SearchOptions o)
        {
            return o.FullSpeed && w.Body.Tips ? w.Body.FullSpeedMoveSamples : w.Body.MoveSamples;
        }

        /// <summary>Samples a stop costs at the end of a run: the office chair's glide, the stool's fall at full speed, else none.</summary>
        private static int StopCost(World w, SearchOptions o)
        {
            if (w.Body.Glides)
            {
                return o.StopSamples;
            }
            return o.FullSpeed && w.Body.Tips ? FallSamples : 0;
        }

        /// <summary>
        /// A move from k to dest leaving at sample t (plus <paramref name="shift"/>): a lying stool rights itself first
        /// (moving, at k), then the travel, moving at both cells and never heard.
        /// </summary>
        private static bool CheckMove(World w, SearchOptions o, Node from, int k, int dest, int t, int shift, bool wide)
        {
            int right = from.Lying ? RightSamples : 0;
            int travel = TravelSamples(w, o);
            for (int q = 1; q <= right; q++)
            {
                if (!MovingOk(w, from.Off, t + q + shift, k, k, wide))
                {
                    return false;
                }
            }
            for (int q = 1; q <= travel; q++)
            {
                int s = t + right + q + shift;
                if (!MovingOk(w, from.Off, s, k, dest, wide)
                    || (o.Noise && Heard(w, Vector3.Lerp(w.Center[k], w.Center[dest], q / (float)travel), s, w.Body.MoveNoiseRadius, wide)))
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>
        /// The stop at the end of a run (CONTRACT_M4 5): the office chair glides <see cref="SearchOptions.StopSamples"/>
        /// samples (moving, rolling); the stool at full speed falls (moving) and the topple is heard on any floor.
        /// </summary>
        private static bool CheckStop(World w, SearchOptions o, Node from, int k, int t, int shift, bool wide)
        {
            int length = StopCost(w, o);
            for (int q = 1; q <= length; q++)
            {
                int s = t + q + shift;
                if (!MovingOk(w, from.Off, s, k, k, wide))
                {
                    return false;
                }
                if (!o.Noise)
                {
                    continue;
                }
                if (w.Body.Glides && Heard(w, w.Center[k], s, Hearing.RadiusOf(NoiseKind.Roll), wide))
                {
                    return false;
                }
                if (!w.Body.Glides && q == length && Heard(w, w.Center[k], s, Hearing.RadiusOf(NoiseKind.Topple), wide))
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
        private static bool CheckToggle(World w, SearchOptions o, Node from, int k, int t, int shift, bool wide)
        {
            const bool dark = false;
            for (int q = 1; q <= ToggleSamples; q++)
            {
                int s = t + q + shift;
                if (!MovingOk(w, dark, s, k, k, wide) || (o.Noise && Heard(w, w.Center[k], s, Hearing.RadiusOf(NoiseKind.Click), wide)))
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
        }

        /// <summary>
        /// Breadth first over time from the start delay: each sample holds, per (cell, wait anchor, explained-once flag,
        /// M4 lamp off, in motion, lying), the Pareto front of (run near the anchor, gauge, moves). The first sample
        /// where a state stands unseen in the exit wins; among its states, the one with the fewest moves. Returns the
        /// node list; <paramref name="goal"/> is -1 when no schedule exists.
        /// </summary>
        private static List<Node> Search(World w, SearchOptions options, out int goal)
        {
            goal = -1;
            var nodes = new List<Node>();
            int start = options.Delay;
            if (w.Start < 0 || start >= HorizonSamples)
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
            // The delay measures the routine phase the attempt starts at: the gauge starts empty. (A chair that
            // really stood at spawn that long creaks there, in place, which is harmless but makes the
            // inhabitant look: the deterministic routine of this search cannot model that look.)
            const float gauge0 = 0f;
            var layers = new Dictionary<long, List<int>>[HorizonSamples + 1];
            long Key(Node n) => (((((long)n.Cell * w.Count + n.Anchor) * 2 + (n.Flag ? 1 : 0)) * 2 + (n.Off ? 1 : 0)) * 2 + (n.Motion ? 1 : 0)) * 2 + (n.Lying ? 1 : 0);
            var first = new Node { Cell = w.Start, Anchor = w.Start, T = start, Parent = -1, Gauge = gauge0, Act = Act.Start };
            nodes.Add(first);
            layers[start] = new Dictionary<long, List<int>> { { Key(first), new List<int> { 0 } } };

            void Offer(Node n)
            {
                Dictionary<long, List<int>> layer = layers[n.T] ?? (layers[n.T] = new Dictionary<long, List<int>>());
                long key = Key(n);
                if (!layer.TryGetValue(key, out List<int> front))
                {
                    layer[key] = front = new List<int>(2);
                }
                foreach (int idx in front)
                {
                    Node o = nodes[idx];
                    if (o.Run <= n.Run && o.Gauge <= n.Gauge + 1e-6f && o.Moves <= n.Moves)
                    {
                        return;
                    }
                }
                front.RemoveAll(idx => n.Run <= nodes[idx].Run && n.Gauge <= nodes[idx].Gauge + 1e-6f && n.Moves <= nodes[idx].Moves);
                nodes.Add(n);
                front.Add(nodes.Count - 1);
            }

            for (int t = start; t < HorizonSamples && goal < 0; t++)
            {
                Dictionary<long, List<int>> current = layers[t];
                layers[t] = null;
                if (current == null)
                {
                    continue;
                }
                foreach (KeyValuePair<long, List<int>> entry in current)
                {
                    foreach (int idx in entry.Value)
                    {
                        Node n = nodes[idx];
                        if (t > start && w.InExit[n.Cell] && !w.SeenAt(n.Off, t, n.Cell, true) && (n.Flag || !options.NeedDecoy)
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
                foreach (KeyValuePair<long, List<int>> entry in current)
                {
                    foreach (int idx in entry.Value)
                    {
                        Node n = nodes[idx];
                        int k = n.Cell;
                        // Still (a furniture still in motion must stop first). Sat on, the creak gauge pauses.
                        if (!n.Motion)
                        {
                            float filled = n.Gauge + (t + 1 >= creakDelay && !w.Pinned[t + 1] ? fill : 0f);
                            if (n.Run + 1 <= options.MaxRun && filled < options.GaugeCap && StillOk(w, options, n.Off, n.Lying, k, t + 1, true))
                            {
                                bool explained = options.Decoys && !n.Lying && !(w.Body.Lamp && n.Off) && w.Seen[t + 1, k] && w.Explained[k] && !w.InPlaceAt(k, t + 1);
                                Offer(new Node
                                {
                                    Cell = k, T = t + 1, Parent = idx, Moves = n.Moves, Run = n.Run + 1, Anchor = n.Anchor,
                                    Gauge = filled, Flag = n.Flag || explained, Act = Act.Still, Off = n.Off, Lying = n.Lying,
                                });
                            }
                        }
                        if (t < start + w.Margin)
                        {
                            continue;
                        }
                        if (n.Motion)
                        {
                            if (t + stopCost <= HorizonSamples && n.Run + stopCost <= options.MaxRun && CheckStop(w, options, n, k, t, 0, true))
                            {
                                Offer(new Node
                                {
                                    Cell = k, T = t + stopCost, Parent = idx, Moves = n.Moves, Run = n.Run + stopCost, Anchor = n.Anchor,
                                    Gauge = Mathf.Max(0f, n.Gauge - stopCost * drain), Flag = n.Flag, Act = Act.Stop, Off = n.Off,
                                    Lying = !w.Body.Glides,
                                });
                            }
                        }
                        else if (toggles && t + ToggleSamples <= HorizonSamples && n.Run + ToggleSamples <= options.MaxRun && CheckToggle(w, options, n, k, t, 0, true))
                        {
                            Offer(new Node
                            {
                                Cell = k, T = t + ToggleSamples, Parent = idx, Moves = n.Moves, Run = n.Run + ToggleSamples, Anchor = n.Anchor,
                                Gauge = Mathf.Max(0f, n.Gauge - ToggleSamples * drain), Flag = n.Flag, Act = Act.Toggle, Off = !n.Off, Lying = n.Lying,
                            });
                        }
                        int length = travel + (n.Lying ? RightSamples : 0);
                        if (t + length > HorizonSamples)
                        {
                            continue;
                        }
                        foreach (int o in w.Neighbors[k])
                        {
                            if (!CheckMove(w, options, n, k, o, t, 0, true)
                                || (!tracksMotion && !StillOk(w, options, n.Off, false, o, t + length, true)))
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
                            });
                        }
                    }
                }
            }
            return nodes;
        }

        private static List<Node> PathTo(List<Node> nodes, int goal)
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
        private static bool ValidShifted(World w, SearchOptions o, List<Node> path, int shift)
        {
            for (int i = 1; i < path.Count; i++)
            {
                Node a = path[i - 1];
                Node b = path[i];
                switch (b.Act)
                {
                    case Act.Move:
                        if (!CheckMove(w, o, a, a.Cell, b.Cell, a.T, shift, false))
                        {
                            return false;
                        }
                        continue;
                    case Act.Stop:
                        if (!CheckStop(w, o, a, a.Cell, a.T, shift, false))
                        {
                            return false;
                        }
                        continue;
                    case Act.Toggle:
                        if (!CheckToggle(w, o, a, a.Cell, a.T, shift, false))
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
                if (s >= w.Samples || !StillOk(w, o, b.Off, b.Lying, b.Cell, s, false))
                {
                    return false;
                }
            }
            Node last = path[path.Count - 1];
            int end = last.T + shift;
            return end >= 0 && end < w.Samples && !w.SeenAt(last.Off, end, last.Cell, false);
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
            for (int i = 1; i < path.Count; i++)
            {
                Node n = path[i];
                Node prev = path[i - 1];
                peak = Mathf.Max(peak, n.Gauge);
                longest = Mathf.Max(longest, n.Run);
                toggles += n.Act == Act.Toggle ? 1 : 0;
                stops += n.Act == Act.Stop ? 1 : 0;
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
                    explained += w.Seen[n.T, n.Cell] && w.Explained[n.Cell] && !w.InPlaceAt(n.Cell, n.T) ? 1 : 0;
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
                + (toggles > 0 ? $", {toggles} interrupteur(s)" : "") + (stops > 0 ? $", {stops} arret(s) glisse(s)" : "")
                + (pinned > 0 ? string.Format(CultureInfo.InvariantCulture, ", assis dessus {0:0.0} s", pinned * SampleSeconds) : ""));
        }

        /// <summary>
        /// The schedule as a designerRoute (docs/CONTRACT_M2.md 4): one waypoint per run of at most
        /// <see cref="RouteStride"/> straight moves, timed at the departure of the run, then the exit center. M4: a lamp
        /// switch is a step with the "toggle" action at the cell it happens on; a stool's steps are all careful.
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
                if (!next.Move)
                {
                    i++;
                    continue;
                }
                int depart = path[i].T;
                int j = i + 1;
                Vector3 step = w.Center[path[j].Cell] - w.Center[path[i].Cell];
                while (j + 1 < path.Count && j - i < RouteStride && path[j + 1].Move
                       && (w.Center[path[j + 1].Cell] - w.Center[path[j].Cell] - step).sqrMagnitude < 1e-6f)
                {
                    j++;
                }
                Vector3 c = w.Center[path[j].Cell];
                route.Add(new RouteStepDef { X = Round(c.x, 100f), Z = Round(c.z, 100f), At = Round(depart * SampleSeconds, 10f), Careful = careful });
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
                    || a[i].Careful != b[i].Careful || a[i].Action != b[i].Action)
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>Writes the route into the level file, keeping the rest of the file as it is written.</summary>
        public static void WriteRoute(string file, List<RouteStepDef> route)
        {
            string text = File.ReadAllText(file);
            string F(float v) => v.ToString("0.0#", CultureInfo.InvariantCulture);
            var sb = new StringBuilder();
            sb.Append("\"designerRoute\": [\n");
            for (int i = 0; i < route.Count; i++)
            {
                RouteStepDef r = route[i];
                string extra = (r.Careful ? ", \"careful\": true" : "") + (r.Action != null ? $", \"action\": \"{r.Action}\"" : "");
                sb.Append($"    {{ \"x\": {F(r.X)}, \"z\": {F(r.Z)}, \"at\": {F(r.At)}{extra} }}");
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
            int samples = HorizonSamples;
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
                        else if (w.Explained[k])
                        {
                            ch = 'c';
                        }
                        else
                        {
                            int unseen = 0;
                            for (int s = 0; s < samples; s++)
                            {
                                unseen += w.Seen[s, k] ? 0 : 1;
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
