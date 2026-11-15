using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using Meuble.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace Meuble.Tests
{
    /// <summary>
    /// M4.2 probe: the rigged inhabitant's feet keep their shape in every state (product owner: "les pieds de l'humain
    /// se deforment parfois").
    ///
    /// The Quaternius HumanArmature is an IK rig baked to FK: Foot.L and Foot.R are children of the root bone, not of the
    /// shins, and every clip places them where the shin ends. The foot vertices blend Foot.X with LowerLeg.X, so the
    /// moment a foot bone is not at the tip of its shin (LowerLeg.X_end), the ankle tears. Measured on the GLB: at most
    /// 0.006 m in every authored pose, 0.05 m mid cross fade, 0.20 to 0.45 m when "_Idle" (which keys no foot) holds the
    /// feet where the last Walk frame left them, and 0.054 m after "_Standing".
    ///
    /// Three measures, in a LateUpdate after every other one (the pose that renders):
    /// - the gap from each shin tip to its foot bone (the skeleton's own invariant);
    /// - the shape of the baked foot: the skinned foot vertices in the foot bone's frame, against the level-start Idle;
    /// - the foot bones' lossy scale against the level start (no scale written on a bone, no non-uniform parent).
    /// A frame is "settled" when the rig has wanted the same clip for twice the cross fade; cross fades get a looser
    /// bound. Every scenario asserts that it reached its states, and the "idle after a clip that keys the feet" case
    /// that the defect needs, so it cannot pass without visiting them.
    /// </summary>
    public sealed class ProbeTestsM42Rig
    {
        private const float Dt = Tuning.FixedStep;

        // Settled poses: authored at most 0.006 m (GLB forward kinematics); a stale foot is 0.054 m (after _Standing) to
        // 0.45 m (after a walk).
        private const float SettledGapMax = 0.02f;
        // During a cross fade the blended chain and the blended foot disagree a little: 0.05 m at worst on the GLB.
        private const float FadeGapMax = 0.08f;
        // The baked foot against the level-start Idle: legit ankle bending moves the blended ankle vertices up to 0.043 m
        // (mid jump); a stale foot after a walk moves them 0.18 to 0.42 m.
        private const float SettledShapeMax = 0.08f;
        private const float FadeShapeMax = 0.12f;
        // A foot bone's lossy scale never changes (no clip has a scale track, every fit is uniform).
        private const float ScaleDriftMax = 1e-3f;
        // "Settled": the clip has been wanted for twice the cross fade, and for a few frames.
        private const float SettleSeconds = 2f * Tuning.RigCrossFadeSeconds;
        private const int SettleFrames = 3;
        // The level-start reference must itself be a coherent pose.
        private const float ReferenceGapMax = 0.01f;

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;

        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;
        private Inhabitant Habitant => Game.MainInhabitant;

        // Level 1, station 3 in front of the window, and a chair spot it sees (as in step 24's carry).
        private static readonly Vector3 WindowSpot = new Vector3(0f, 0f, -2.3f);
        private static readonly Vector3 DisplacedChair = new Vector3(-3.2f, 0f, -0.8f);

        // test_m4_game_prop: a walk to the sofa, a sit, a stand up, a walk back.
        private const string PropLevel = "test_m4_game_prop";
        // test_m4_game_sit: the chair hidden from the sitter is a pratfall (as in step 33).
        private const string SitLevel = "test_m4_game_sit";
        private static readonly Vector3 HidingSpot = new Vector3(-3.6f, 0f, -1.2f);

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            fixedSteps = 0;
            GamePause.IsPaused = false;
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
            GamePause.IsPaused = false;
            Game.Rules = GameRules.M1;
            Game.FixedStepped += CountStep;
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            GamePause.IsPaused = false;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.FixedStepped -= CountStep;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                }
            }
            yield return null;
        }

        private void CountStep() => fixedSteps++;

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

        private static int StepsFor(float seconds) => Mathf.CeilToInt(seconds / Dt);

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(to - from);

        /// <summary>Runs the game at <paramref name="scale"/> until <paramref name="until"/> holds or <paramref name="maxSteps"/> fixed steps ran.</summary>
        private IEnumerator Run(int maxSteps, Func<bool> until, float scale)
        {
            int end = fixedSteps + maxSteps;
            float realStart = Time.realtimeSinceStartup;
            Time.timeScale = scale;
            try
            {
                while (fixedSteps < end && (until == null || !until()) && Time.realtimeSinceStartup - realStart < 150f)
                {
                    yield return null;
                }
            }
            finally
            {
                Time.timeScale = 1f;
            }
        }

        private static InhabitantRig AssertRigged(Inhabitant h, string where)
        {
            Assert.IsNotNull(h, $"{where}: no inhabitant");
            InhabitantRig rig = h.Rig;
            Assert.IsNotNull(rig, $"{where}: premise broken, '{h.name}' has no rigged model");
            Assert.IsNotNull(rig.Skin, $"{where}: no SkinnedMeshRenderer");
            Assert.IsNotNull(rig.Animation, $"{where}: no Animation component");
            Assert.IsNotNull(rig.IdleState, $"{where}: no _Idle clip");
            Assert.IsNotNull(rig.WalkState, $"{where}: no _Walk clip");
            return rig;
        }

        private static FootGauge Gauge(Inhabitant h, string where)
        {
            InhabitantRig rig = AssertRigged(h, where);
            var gauge = new FootGauge(rig, where);
            Assert.LessOrEqual(gauge.Gap(), ReferenceGapMax,
                $"{where}: premise broken, the level-start pose already has a foot {gauge.Gap():0.000} m off its shin");
            return gauge;
        }

        private static FootWatcher Watch(FootGauge gauge)
        {
            var go = new GameObject("FootWatcher");
            var watcher = go.AddComponent<FootWatcher>();
            watcher.Gauge = gauge;
            return watcher;
        }

        private static void Unwatch(FootWatcher watcher)
        {
            if (watcher != null)
            {
                watcher.Gauge = null;
                UnityEngine.Object.Destroy(watcher.gameObject);
            }
        }

        // ----- 24f: level 1, walk, idle, turns, telegraph, the carry back, the startle -----

        /// <summary>
        /// Level 1: a full routine loop (walks, dwells, corner and body turns, head glances, telegraphs), a carry back of
        /// the displaced chair (pick up, carry, put down, walk back) and a startle (the held Jump), then the dwells that
        /// follow each of them. In every rendered frame each foot stays on its shin and keeps its baked shape.
        /// </summary>
        [UnityTest]
        public IEnumerator Step24f_FeetKeepTheirShapeInEveryState()
        {
            Inhabitant h = Habitant;
            FootGauge gauge = Gauge(h, "level1");
            InhabitantRoutine routine = h.Routine;
            // The skin blends four bones in the quality level in use (the Mobile level, with two, never ships on Standalone).
            Assert.GreaterOrEqual((int)QualitySettings.skinWeights, (int)SkinWeights.FourBones,
                $"the current quality level '{QualitySettings.names[QualitySettings.GetQualityLevel()]}' skins with {QualitySettings.skinWeights}");
            Assert.IsTrue(gauge.Rig.Skin.quality == SkinQuality.Auto || gauge.Rig.Skin.quality == SkinQuality.Bone4,
                $"the inhabitant's skin quality is {gauge.Rig.Skin.quality}");

            FootWatcher watcher = Watch(gauge);
            float realStart = Time.realtimeSinceStartup;
            try
            {
                // 1. A full loop of the routine (M1 rules, as step 24).
                Time.timeScale = 4f;
                while (routine.LoopsCompleted < 1 && Game.Elapsed < 120f && Time.realtimeSinceStartup - realStart < 150f)
                {
                    yield return null;
                }
                Time.timeScale = 1f;
                Assert.GreaterOrEqual(routine.LoopsCompleted, 1, "premise: the routine never completed a loop");

                // 2. A carry back (M2 rules): the displaced chair seen from the window.
                Game.Rules = GameRules.M2;
                Chair.Teleport(DisplacedChair, 0f);
                h.Pin(WindowSpot, YawToward(WindowSpot, DisplacedChair), 0f, true);
                yield return Steps(1);
                Assert.IsTrue(Game.Seen, "premise: the inhabitant sees the displaced chair");
                yield return Run(StepsFor(40f), () => Game.State != PlayState.Playing || (Game.CarryCount > 0 && !routine.IsCarrying), 2f);
                Assert.AreEqual(1, Game.CarryCount, $"premise: no carry (mode {h.Mode}, activity {routine.LastActivity})");
                // The walk back to the pin and the hold there (Pinned: Idle).
                int idleBefore = gauge.SettledAfterWalk;
                yield return Run(StepsFor(10f), () => gauge.SettledAfterWalk >= idleBefore + 20 && routine.LastActivity == RoutineActivity.Pinned, 2f);
                Assert.GreaterOrEqual(gauge.SettledAfterWalk, idleBefore + 20, $"premise: no settled hold after the carry back ({routine.LastActivity})");

                // 3. The startle (terminal: the routine never leaves it), the Jump played once and held.
                h.Startle(routine.Position + YawMath.Forward(routine.BodyYaw + 90f) * 2f);
                yield return Run(StepsFor(2f), null, 1f);
            }
            finally
            {
                Time.timeScale = 1f;
                Unwatch(watcher);
            }

            Debug.Log("[Step24f] " + gauge.Report());
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
            gauge.AssertReached("walking", 20);
            gauge.AssertReached("idle", 20);
            gauge.AssertReached("turning", 3);
            gauge.AssertReached("telegraph", 3);
            gauge.AssertReached("carrying", 10);
            gauge.AssertReached("bending", 3);
            gauge.AssertReached("startled", 10);
            Assert.Greater(gauge.SettledAfterWalk, 20, "premise: too few settled idle frames after a walk (the case the defect needs)");
            gauge.AssertFeetHeld();
        }

        // ----- 24g: sitting on a prop and standing up -----

        /// <summary>
        /// test_m4_game_prop: the walk to the sofa, the sit-down, the seated hold, the stand up telegraph, the stand up
        /// ("_Standing" once, then held), the walk back and the dwell after it.
        /// </summary>
        [UnityTest]
        public IEnumerator Step24g_FeetKeepTheirShapeSittingAndStandingUp()
        {
            int before = exceptions;
            Game.LoadLevel(PropLevel);
            Game.Rules = GameRules.M4;
            yield return Steps(2);
            Assert.AreEqual(PropLevel, Game.LevelId);
            Assert.AreEqual(before, exceptions, $"{PropLevel} logged errors at boot: " + string.Join(" | ", logged));
            Inhabitant h = Habitant;
            FootGauge gauge = Gauge(h, PropLevel);
            Assert.IsNotNull(gauge.Rig.SitState, "premise: the model has no _Sitting clip");
            Assert.IsNotNull(gauge.Rig.StandState, "premise: the model has no _Standing clip");
            InhabitantRoutine routine = h.Routine;
            bool stood = false;
            int afterStand = 0;
            void OnStep()
            {
                stood |= routine.LastActivity == RoutineActivity.StandingUp;
                afterStand += stood && routine.LastActivity != RoutineActivity.StandingUp ? 1 : 0;
            }
            FootWatcher watcher = Watch(gauge);
            Game.FixedStepped += OnStep;
            try
            {
                // Sit, stand, then the walk back to station 0 and its 0.6 s dwell.
                yield return Run(StepsFor(30f), () => afterStand > 0 && gauge.SettledAfterStand >= 20, 1f);
            }
            finally
            {
                Game.FixedStepped -= OnStep;
                Unwatch(watcher);
            }

            Debug.Log("[Step24g] " + gauge.Report());
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
            Assert.AreEqual(SitResult.OnProp, routine.LastSitResult, "premise: the inhabitant did not sit on the sofa");
            Assert.IsTrue(stood, "premise: the inhabitant never stood up");
            gauge.AssertReached("walking", 20);
            gauge.AssertReached("seated", 40);
            gauge.AssertReached("standing up", 3);
            Assert.Greater(gauge.SettledAfterStand, 10, "premise: too few settled idle frames after the stand up");
            gauge.AssertFeetHeld();
        }

        // ----- 24h: the pratfall -----

        /// <summary>
        /// test_m4_game_sit with the chair hidden: the sit-down on nothing, the 1 s pratfall on the floor tilting back, the
        /// stand up, and the alerted look at the empty seat (standing, Idle) after it.
        /// </summary>
        [UnityTest]
        public IEnumerator Step24h_FeetKeepTheirShapeThroughAPratfall()
        {
            int before = exceptions;
            Game.LoadLevel(SitLevel);
            Game.Rules = GameRules.M4;
            yield return Steps(2);
            Assert.AreEqual(SitLevel, Game.LevelId);
            Assert.AreEqual(before, exceptions, $"{SitLevel} logged errors at boot: " + string.Join(" | ", logged));
            Inhabitant sitter = Game.Level.Inhabitants.Find(i => i.name == "Assis");
            Inhabitant watcherInhabitant = Game.Level.Inhabitants.Find(i => i.name == "Temoin");
            Assert.IsNotNull(sitter, "premise: no sitter");
            Assert.IsNotNull(watcherInhabitant, "premise: no watcher");
            FootGauge gauge = Gauge(sitter, SitLevel);
            InhabitantRoutine routine = sitter.Routine;
            watcherInhabitant.Pin(watcherInhabitant.Routine.Position, 90f);
            Chair.Teleport(HidingSpot, 0f);
            bool fell = false, alerted = false;
            void OnStep()
            {
                fell |= routine.LastActivity == RoutineActivity.Pratfall;
                alerted |= fell && routine.Mode == InhabitantMode.Alerted;
            }
            FootWatcher watcher = Watch(gauge);
            Game.FixedStepped += OnStep;
            try
            {
                yield return Run(StepsFor(25f), () => alerted && routine.Mode != InhabitantMode.Alerted && gauge.SettledAfterStand >= 20, 1f);
            }
            finally
            {
                Game.FixedStepped -= OnStep;
                Unwatch(watcher);
            }

            Debug.Log("[Step24h] " + gauge.Report());
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
            Assert.AreEqual(SitResult.Pratfall, routine.LastSitResult, "premise: no pratfall without the chair");
            Assert.IsTrue(fell, "premise: the pratfall never played");
            Assert.IsTrue(alerted, "premise: no alerted look after the pratfall");
            gauge.AssertReached("walking", 20);
            gauge.AssertReached("pratfall", 20);
            gauge.AssertReached("standing up", 3);
            Assert.Greater(gauge.SettledAfterStand, 20, "premise: too few settled idle frames after the stand up (the look)");
            gauge.AssertFeetHeld();
        }

        // ----- The gauge -----

        /// <summary>Per state, the worst foot measures over the settled frames and over the cross fades.</summary>
        private sealed class Stat
        {
            public int Frames;
            public int Settled;
            public float SettledGap;
            public float FadeGap;
            public float SettledShape;
            public float FadeShape;
            public string SettledGapWhere = "";
            public string SettledShapeWhere = "";
            public string FadeGapWhere = "";
            public string FadeShapeWhere = "";
        }

        /// <summary>
        /// The foot measures of one rigged inhabitant. Built on the level-start Idle, which is the reference of the baked
        /// foot shape (its own gap is checked by the caller).
        /// </summary>
        internal sealed class FootGauge
        {
            private const string FootLeft = "Foot.L";
            private const string FootRight = "Foot.R";
            private const string ShinTipLeft = "LowerLeg.L_end";
            private const string ShinTipRight = "LowerLeg.R_end";

            public InhabitantRig Rig { get; }
            public Inhabitant Owner { get; }
            private readonly string where;
            private readonly Transform[] feet;
            private readonly Transform[] shinTips;
            private readonly int[][] footVertices;
            private readonly Vector3[][] reference;
            private readonly Vector3[] referenceScale;
            private readonly Mesh baked = new Mesh();
            private readonly List<Vector3> vertices = new List<Vector3>();
            private readonly Dictionary<string, Stat> stats = new Dictionary<string, Stat>();

            private InhabitantRig.Clip clip = InhabitantRig.Clip.None;
            private float clipSince;
            private int clipFrames;
            private bool walked;
            private bool stoodUp;
            private float worstScaleDrift;
            private string scaleWhere = "";

            /// <summary>Settled idle frames (dwell, wait, look, pin) after the first walking frame.</summary>
            public int SettledAfterWalk { get; private set; }

            /// <summary>Settled idle frames (dwell, wait, look, pin) after the first stand up frame.</summary>
            public int SettledAfterStand { get; private set; }

            public FootGauge(InhabitantRig rig, string where)
            {
                Rig = rig;
                Owner = rig.Owner;
                this.where = where;
                Transform root = rig.Model.transform;
                feet = new[] { FindDeep(root, FootLeft), FindDeep(root, FootRight) };
                shinTips = new[] { FindDeep(root, ShinTipLeft), FindDeep(root, ShinTipRight) };
                for (int s = 0; s < 2; s++)
                {
                    Assert.IsNotNull(feet[s], $"{where}: premise broken, no foot bone {(s == 0 ? FootLeft : FootRight)}");
                    Assert.IsNotNull(shinTips[s], $"{where}: premise broken, no shin tip {(s == 0 ? ShinTipLeft : ShinTipRight)}");
                }
                SkinnedMeshRenderer skin = rig.Skin;
                Mesh mesh = skin.sharedMesh;
                BoneWeight[] weights = mesh.boneWeights;
                Assert.AreEqual(mesh.vertexCount, weights.Length, $"{where}: premise broken, the skinned mesh has no bone weights");
                footVertices = new int[2][];
                reference = new Vector3[2][];
                referenceScale = new Vector3[2];
                for (int s = 0; s < 2; s++)
                {
                    int bone = Array.IndexOf(skin.bones, feet[s]);
                    Assert.GreaterOrEqual(bone, 0, $"{where}: premise broken, {feet[s].name} does not skin the mesh");
                    var list = new List<int>();
                    for (int v = 0; v < weights.Length; v++)
                    {
                        if (WeightOf(weights[v], bone) > 1e-4f)
                        {
                            list.Add(v);
                        }
                    }
                    Assert.Greater(list.Count, 20, $"{where}: premise broken, only {list.Count} vertices on {feet[s].name}");
                    footVertices[s] = list.ToArray();
                    referenceScale[s] = feet[s].lossyScale;
                }
                Bake();
                for (int s = 0; s < 2; s++)
                {
                    reference[s] = FootFrame(s);
                    // The baked vertices are where the foot is drawn: a wrong space (the mesh node's scale of 100) would
                    // put them meters away from the bone.
                    float far = 0f;
                    Matrix4x4 toWorld = skin.transform.localToWorldMatrix;
                    foreach (int v in footVertices[s])
                    {
                        far = Mathf.Max(far, (toWorld.MultiplyPoint3x4(vertices[v]) - feet[s].position).magnitude);
                    }
                    Assert.Less(far, 0.3f, $"{where}: premise broken, a baked foot vertex lies {far:0.00} m from {feet[s].name}");
                }
            }

            private static float WeightOf(BoneWeight w, int bone)
            {
                float sum = 0f;
                sum += w.boneIndex0 == bone ? w.weight0 : 0f;
                sum += w.boneIndex1 == bone ? w.weight1 : 0f;
                sum += w.boneIndex2 == bone ? w.weight2 : 0f;
                sum += w.boneIndex3 == bone ? w.weight3 : 0f;
                return sum;
            }

            private void Bake()
            {
                // As ModelCatalogBuilder: with useScale the vertices are in the renderer's local space, and its full local to
                // world matrix places them (the constructor checks it).
                Rig.Skin.BakeMesh(baked, true);
                baked.GetVertices(vertices);
            }

            /// <summary>The foot's skinned vertices in the foot bone's frame, in meters (rotation and position only).</summary>
            private Vector3[] FootFrame(int side)
            {
                Matrix4x4 toWorld = Rig.Skin.transform.localToWorldMatrix;
                Quaternion inverse = Quaternion.Inverse(feet[side].rotation);
                Vector3 origin = feet[side].position;
                int[] ids = footVertices[side];
                var local = new Vector3[ids.Length];
                for (int i = 0; i < ids.Length; i++)
                {
                    local[i] = inverse * (toWorld.MultiplyPoint3x4(vertices[ids[i]]) - origin);
                }
                return local;
            }

            /// <summary>The larger distance from a shin tip to its foot bone (meters).</summary>
            public float Gap()
            {
                return Mathf.Max((shinTips[0].position - feet[0].position).magnitude, (shinTips[1].position - feet[1].position).magnitude);
            }

            /// <summary>The largest move of a foot vertex in its foot bone's frame since the level-start Idle (meters).</summary>
            private float Shape()
            {
                Bake();
                float worst = 0f;
                for (int s = 0; s < 2; s++)
                {
                    Vector3[] now = FootFrame(s);
                    for (int i = 0; i < now.Length; i++)
                    {
                        worst = Mathf.Max(worst, (now[i] - reference[s][i]).magnitude);
                    }
                }
                return worst;
            }

            private string StateOf()
            {
                InhabitantRoutine r = Owner.Routine;
                RoutineActivity a = r.LastActivity;
                if (a == RoutineActivity.Pratfall || Owner.PratfallBlend > 0f)
                {
                    return "pratfall";
                }
                if (a == RoutineActivity.StandingUp)
                {
                    return "standing up";
                }
                if (Owner.SeatedPose)
                {
                    return "seated";
                }
                switch (a)
                {
                    case RoutineActivity.Startled:
                        return "startled";
                    case RoutineActivity.Carrying:
                        return "carrying";
                    case RoutineActivity.PickingUp:
                    case RoutineActivity.PuttingDown:
                        return "bending";
                    case RoutineActivity.Walking:
                        return "walking";
                    case RoutineActivity.TurningBody:
                    case RoutineActivity.TurningHead:
                        return "turning";
                    case RoutineActivity.Telegraph:
                        return "telegraph";
                    default:
                        // Idle, Waiting, Looking, Pinned, SwitchingOn.
                        return "idle";
                }
            }

            /// <summary>One rendered frame, after the rig.</summary>
            public void Measure()
            {
                if (Rig == null || Owner == null || Owner.Routine == null)
                {
                    return;
                }
                if (Rig.CurrentClip != clip)
                {
                    clip = Rig.CurrentClip;
                    clipSince = Time.time;
                    clipFrames = 0;
                }
                clipFrames++;
                bool settled = Time.time - clipSince >= SettleSeconds && clipFrames >= SettleFrames;
                string state = StateOf();
                walked |= state == "walking" || state == "carrying";
                stoodUp |= state == "standing up";
                if (!stats.TryGetValue(state, out Stat stat))
                {
                    stat = new Stat();
                    stats[state] = stat;
                }
                stat.Frames++;
                float gap = Gap();
                float shape = Shape();
                string at = $"t={Time.time:0.00} s, clip {clip} for {Time.time - clipSince:0.00} s, {Owner.Routine.LastActivity}";
                if (settled)
                {
                    stat.Settled++;
                    if (gap > stat.SettledGap)
                    {
                        stat.SettledGap = gap;
                        stat.SettledGapWhere = at;
                    }
                    if (shape > stat.SettledShape)
                    {
                        stat.SettledShape = shape;
                        stat.SettledShapeWhere = at;
                    }
                    if (state == "idle" && walked)
                    {
                        SettledAfterWalk++;
                    }
                    if (state == "idle" && stoodUp)
                    {
                        SettledAfterStand++;
                    }
                }
                else
                {
                    if (gap > stat.FadeGap)
                    {
                        stat.FadeGap = gap;
                        stat.FadeGapWhere = at;
                    }
                    if (shape > stat.FadeShape)
                    {
                        stat.FadeShape = shape;
                        stat.FadeShapeWhere = at;
                    }
                }
                for (int s = 0; s < 2; s++)
                {
                    Vector3 scale = feet[s].lossyScale;
                    float drift = Mathf.Max(Mathf.Abs(scale.x / referenceScale[s].x - 1f),
                        Mathf.Max(Mathf.Abs(scale.y / referenceScale[s].y - 1f), Mathf.Abs(scale.z / referenceScale[s].z - 1f)));
                    if (drift > worstScaleDrift)
                    {
                        worstScaleDrift = drift;
                        scaleWhere = $"{feet[s].name} {scale} in {state}, {at}";
                    }
                }
            }

            public string Report()
            {
                var sb = new StringBuilder($"{where} feet per state (gap shin tip to foot bone, shape of the baked foot; settled | fade):");
                foreach (KeyValuePair<string, Stat> kv in stats)
                {
                    Stat s = kv.Value;
                    sb.Append($"\n  {kv.Key,-12} {s.Frames,5} frames ({s.Settled} settled): gap {s.SettledGap:0.000} | {s.FadeGap:0.000} m, " +
                        $"shape {s.SettledShape:0.000} | {s.FadeShape:0.000} m; worst settled gap at {s.SettledGapWhere}");
                }
                sb.Append($"\n  idle after a walk {SettledAfterWalk} settled frames, after a stand up {SettledAfterStand}; foot scale drift {worstScaleDrift:0.00000}");
                return sb.ToString();
            }

            public void AssertReached(string state, int minSettled)
            {
                stats.TryGetValue(state, out Stat stat);
                int settled = stat != null ? stat.Settled : 0;
                Assert.GreaterOrEqual(settled, minSettled, $"{where}: premise broken, only {settled} settled frames {state} (states: {string.Join(", ", stats.Keys)})");
            }

            public void AssertFeetHeld()
            {
                var bad = new List<string>();
                foreach (KeyValuePair<string, Stat> kv in stats)
                {
                    Stat s = kv.Value;
                    if (s.SettledGap > SettledGapMax)
                    {
                        bad.Add($"{kv.Key}: a foot stands {s.SettledGap:0.000} m off its shin (settled, max {SettledGapMax}) at {s.SettledGapWhere}");
                    }
                    if (s.FadeGap > FadeGapMax)
                    {
                        bad.Add($"{kv.Key}: a foot stands {s.FadeGap:0.000} m off its shin (cross fade, max {FadeGapMax}) at {s.FadeGapWhere}");
                    }
                    if (s.SettledShape > SettledShapeMax)
                    {
                        bad.Add($"{kv.Key}: the baked foot moved {s.SettledShape:0.000} m out of shape (settled, max {SettledShapeMax}) at {s.SettledShapeWhere}");
                    }
                    if (s.FadeShape > FadeShapeMax)
                    {
                        bad.Add($"{kv.Key}: the baked foot moved {s.FadeShape:0.000} m out of shape (cross fade, max {FadeShapeMax}) at {s.FadeShapeWhere}");
                    }
                }
                if (worstScaleDrift > ScaleDriftMax)
                {
                    bad.Add($"a foot bone's lossy scale drifted by {worstScaleDrift:0.0000} ({scaleWhere})");
                }
                Assert.IsEmpty(bad, $"{where}: the feet deform:\n" + string.Join("\n", bad));
            }

            private static Transform FindDeep(Transform root, string name)
            {
                if (root.name == name)
                {
                    return root;
                }
                for (int i = 0; i < root.childCount; i++)
                {
                    Transform t = FindDeep(root.GetChild(i), name);
                    if (t != null)
                    {
                        return t;
                    }
                }
                return null;
            }
        }
    }

    /// <summary>Measures the feet in a LateUpdate after every other one: the pose that gets rendered.</summary>
    [DefaultExecutionOrder(32000)]
    internal sealed class FootWatcher : MonoBehaviour
    {
        public ProbeTestsM42Rig.FootGauge Gauge;

        private void LateUpdate()
        {
            Gauge?.Measure();
        }
    }
}
