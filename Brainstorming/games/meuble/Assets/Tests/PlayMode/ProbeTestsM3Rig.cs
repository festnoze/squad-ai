using System;
using System.Collections;
using System.Collections.Generic;
using Meuble.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace Meuble.Tests
{
    /// <summary>
    /// Probe step 24 (docs/CONTRACT_M3.md 5 and 9): the rigged inhabitant. Runs the real Boot scene and the real
    /// level builder, so the model, the catalog entry and <see cref="InhabitantRig.Attach"/> are the game's own.
    ///
    /// Every scenario first asserts its premise (a SkinnedMeshRenderer under the inhabitant, a bound rig), so a
    /// null stub cannot pass. Visual measurements are taken by <see cref="RigWatcher"/> in a LateUpdate that runs
    /// after every other one: exactly the pose that gets rendered, after the animation and the rig's overrides.
    /// Waits are bounded by fixed steps or game time, never by rendered frames.
    /// </summary>
    public sealed class ProbeTestsM3Rig
    {
        private const float Dt = Tuning.FixedStep;
        private const float HeadTolerance = 5f;
        private const float EyeHeightTolerance = 0.03f;
        // Independent of the catalog's eye data: the tip of the head bone (Head_end, top of the skull) stands about
        // 0.10 m above the eyes on both GLBs. A wrong eye centroid in the catalog scales the whole model and fails here.
        private const string HeadTipBone = "Head_end";
        private const float HeadTipAboveEyesMin = 0.04f;
        private const float HeadTipAboveEyesMax = 0.18f;
        private const float WeightAfterFade = 0.9f;
        // "After the cross fade": the fade is 0.15 s; a sample counts once its clip was wanted for this long.
        private const float SettleSeconds = 0.3f;
        private const int SettleFrames = 3;

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;

        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;
        private Inhabitant Habitant => Game.MainInhabitant;

        // Level 1, station 3 in front of the window (PRD 6.3 coordinates), and a chair spot it sees (step 13b).
        private static readonly Vector3 WindowSpot = new Vector3(0f, 0f, -2.3f);
        private static readonly Vector3 DisplacedChair = new Vector3(-3.2f, 0f, -0.8f);

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
            // The title screen is never up in an editor run (CONTRACT_M3 6); a stale pause would freeze every step.
            GamePause.IsPaused = false;
            Game.Rules = GameRules.M1;
            Game.FixedStepped += CountStep;
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
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

        /// <summary>
        /// Runs the game at <paramref name="scale"/> until <paramref name="until"/> holds or <paramref name="maxSteps"/>
        /// fixed steps ran: bounded by game time (with a real time guard), never by frames.
        /// </summary>
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

        private static RigWatcher Watch(Action late)
        {
            var go = new GameObject("RigWatcher");
            var watcher = go.AddComponent<RigWatcher>();
            watcher.Late = late;
            return watcher;
        }

        private static RigWatcher WatchBeforeHud(Action late)
        {
            var go = new GameObject("RigWatcherBeforeHud");
            var watcher = go.AddComponent<RigWatcherBeforeHud>();
            watcher.Late = late;
            return watcher;
        }

        private static void Unwatch(RigWatcher watcher)
        {
            if (watcher != null)
            {
                watcher.Late = null;
                UnityEngine.Object.Destroy(watcher.gameObject);
            }
        }

        /// <summary>The premise of every step 24 scenario: a real skinned model with a bound rig.</summary>
        private static InhabitantRig AssertRigged(Inhabitant h, string where)
        {
            Assert.IsNotNull(h, $"{where}: no inhabitant");
            SkinnedMeshRenderer[] skins = h.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            Assert.Greater(skins.Length, 0, $"{where}: premise broken, no SkinnedMeshRenderer under '{h.name}' (the model was never attached)");
            InhabitantRig rig = h.Rig;
            Assert.IsNotNull(rig, $"{where}: '{h.name}' has a skinned model but no InhabitantRig");
            Assert.IsNotNull(rig.Head, $"{where}: the rig found no head bone");
            Assert.IsNotNull(rig.Animation, $"{where}: the model has no Animation component");
            Assert.IsNotNull(rig.Entry, $"{where}: the rig has no catalog entry");
            Assert.AreNotEqual(Vector3.zero, rig.Entry.eyeLocal, $"{where}: catalog entry '{rig.Entry.id}' has no eyeLocal");
            return rig;
        }

        private static float Weight(InhabitantRig rig, InhabitantRig.Clip clip)
        {
            AnimationState s = clip == InhabitantRig.Clip.Walk ? rig.WalkState : clip == InhabitantRig.Clip.Jump ? rig.JumpState : rig.IdleState;
            return s != null && s.enabled ? s.weight : 0f;
        }

        private static bool IsWalking(RoutineActivity a) => a == RoutineActivity.Walking || a == RoutineActivity.Carrying;

        /// <summary>Horizontal direction of the model's eyes seen from the head bone (independent of the rig's calibration).</summary>
        private static Vector3 EyeDirection(InhabitantRig rig) => YawMath.Planar(rig.EyePosition - rig.Head.position);

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

        // ----- 24 -----

        /// <summary>Every inhabitant of every level is a rigged model, with the Animation set up as the contract says.</summary>
        [UnityTest]
        public IEnumerator Step24_RigOnEveryInhabitant()
        {
            int rigs = 0;
            foreach (string id in Game.LevelOrder)
            {
                int before = exceptions;
                Game.LoadLevel(id);
                Game.Rules = GameRules.M1;
                    yield return Steps(2);
                Assert.AreEqual(before, exceptions, $"{id} logged errors at boot: " + string.Join(" | ", logged));
                foreach (Inhabitant h in Game.Level.Inhabitants)
                {
                    string where = $"{id}/{h.name}";
                    InhabitantRig rig = AssertRigged(h, where);
                    rigs++;
                    Assert.IsNull(h.HeadPivot, $"{where}: the procedural head was built next to the model");
                    Assert.IsNull(h.Body, $"{where}: the procedural body was built next to the model");
                    Assert.IsTrue(rig.CalibratedFromBindPose, $"{where}: the head calibration did not come from the bind pose");
                    Animation anim = rig.Animation;
                    Assert.IsFalse(anim.playAutomatically, $"{where}: playAutomatically is still on");
                    Assert.AreEqual(AnimationCullingType.AlwaysAnimate, anim.cullingType, $"{where}: culling type");
                    Assert.IsNotNull(rig.IdleState, $"{where}: no clip ending with _Idle");
                    Assert.IsNotNull(rig.WalkState, $"{where}: no clip ending with _Walk");
                    Assert.IsNotNull(rig.JumpState, $"{where}: no clip ending with _Jump");
                    StringAssert.EndsWith("_Jump", rig.JumpClipName, $"{where}: Jump matched another clip");
                    Assert.AreEqual(WrapMode.Loop, rig.IdleState.wrapMode, $"{where}: Idle must loop");
                    Assert.AreEqual(WrapMode.Loop, rig.WalkState.wrapMode, $"{where}: Walk must loop");
                    Assert.AreEqual(WrapMode.ClampForever, rig.JumpState.wrapMode, $"{where}: Jump must play once and hold");
                    Assert.AreEqual(Layers.Inhabitant, rig.Skin.gameObject.layer, $"{where}: the skinned mesh is not on the Inhabitant layer (x-ray)");
                }
            }
            Assert.Greater(rigs, 0, "premise: no inhabitant in any level");
        }

        /// <summary>
        /// A full routine loop of level 1 (time scaled, bounded by game time). In every rendered frame: the head bone
        /// looks along the interpolated eye forward within 5 deg, and so do the model's eyes; after each cross fade the
        /// clip of the activity has a weight above 0.9; while dwelling the eyes are at 1.6 m. Per fixed step: the
        /// footsteps count while walking, twice per walk cycle, and never while not walking.
        /// </summary>
        [UnityTest]
        public IEnumerator Step24_LoopDrivesClipsHeadAndFootsteps()
        {
            Inhabitant h = Habitant;
            InhabitantRig rig = AssertRigged(h, "level1");
            InhabitantRoutine routine = h.Routine;

            float worstHead = 0f, worstEye = 0f, worstEyeHeight = 0f, maxGlance = 0f;
            float lowTop = float.MaxValue, highTop = float.MinValue;
            Transform headTip = FindDeep(rig.Head, HeadTipBone);
            Assert.IsNotNull(headTip, $"premise: no {HeadTipBone} bone under the head");
            float worstWalkWeight = 1f, worstIdleWeight = 1f;
            int frames = 0, eyeSamples = 0, heightSamples = 0, walkSamples = 0, idleSamples = 0;
            string headWhere = "", walkWhere = "", idleWhere = "";
            InhabitantRig.Clip wanted = InhabitantRig.Clip.None;
            float wantedSince = 0f;
            int wantedFrames = 0;
            void Late()
            {
                frames++;
                RoutineActivity a = routine.LastActivity;
                Vector3 eyeForward = YawMath.Forward(h.VisualEyeYaw);
                float head = Vector3.Angle(rig.Head.forward, eyeForward);
                if (head > worstHead)
                {
                    worstHead = head;
                    headWhere = $"{a} at t={Game.Elapsed:0.00} s (head yaw {routine.HeadYaw:0})";
                }
                maxGlance = Mathf.Max(maxGlance, Mathf.Abs(routine.HeadYaw));
                if (rig.Tilt == 0f)
                {
                    // The telegraph roll swings the eyes sideways around the forward axis: measured without it.
                    worstEye = Mathf.Max(worstEye, Vector3.Angle(EyeDirection(rig), eyeForward));
                    eyeSamples++;
                }
                if (a == RoutineActivity.TurningBody || a == RoutineActivity.TurningHead)
                {
                    // A turn keeps whichever clip it follows (a corner turn keeps the stride): no expectation.
                    return;
                }
                InhabitantRig.Clip clip = IsWalking(a) ? InhabitantRig.Clip.Walk : InhabitantRig.Clip.Idle;
                if (clip != wanted)
                {
                    wanted = clip;
                    wantedSince = Time.time;
                    wantedFrames = 0;
                }
                wantedFrames++;
                if (Time.time - wantedSince < SettleSeconds || wantedFrames < SettleFrames)
                {
                    return;
                }
                if (clip == InhabitantRig.Clip.Walk)
                {
                    walkSamples++;
                    float w = Weight(rig, InhabitantRig.Clip.Walk);
                    if (w < worstWalkWeight)
                    {
                        worstWalkWeight = w;
                        walkWhere = $"t={Game.Elapsed:0.00} s, idle weight {Weight(rig, InhabitantRig.Clip.Idle):0.00}";
                    }
                }
                else if (routine.InDwell)
                {
                    idleSamples++;
                    float w = Weight(rig, InhabitantRig.Clip.Idle);
                    if (w < worstIdleWeight)
                    {
                        worstIdleWeight = w;
                        idleWhere = $"{a} at t={Game.Elapsed:0.00} s, walk weight {Weight(rig, InhabitantRig.Clip.Walk):0.00}";
                    }
                    if (rig.Tilt == 0f)
                    {
                        float eyeHeight = rig.EyePosition.y - h.Visual.position.y;
                        worstEyeHeight = Mathf.Max(worstEyeHeight, Mathf.Abs(eyeHeight - Tuning.EyeHeight));
                        float top = headTip.position.y - h.Visual.position.y;
                        lowTop = Mathf.Min(lowTop, top);
                        highTop = Mathf.Max(highTop, top);
                        heightSamples++;
                    }
                }
            }

            int walkingSteps = 0, walkingFootsteps = 0, idleFootsteps = 0, idleSteps = 0;
            float walked = 0f;
            int lastCount = h.FootstepCount;
            Vector3 lastPosition = routine.Position;
            void OnStep()
            {
                int delta = h.FootstepCount - lastCount;
                lastCount = h.FootstepCount;
                if (IsWalking(routine.LastActivity))
                {
                    walkingSteps++;
                    walkingFootsteps += delta;
                    walked += YawMath.Planar(routine.Position - lastPosition).magnitude;
                }
                else
                {
                    idleSteps++;
                    idleFootsteps += delta;
                }
                lastPosition = routine.Position;
            }

            RigWatcher watcher = Watch(Late);
            Game.FixedStepped += OnStep;
            float realStart = Time.realtimeSinceStartup;
            Time.timeScale = 4f;
            try
            {
                while (routine.LoopsCompleted < 1 && Game.Elapsed < 120f && Time.realtimeSinceStartup - realStart < 150f)
                {
                    yield return null;
                }
            }
            finally
            {
                Time.timeScale = 1f;
                Game.FixedStepped -= OnStep;
                Unwatch(watcher);
            }

            float cycles = walked / rig.WalkCycleDistance;
            Debug.Log($"[Step24] loop {Game.Elapsed:0.0} s, {frames} frames: head {worstHead:0.00} deg ({headWhere}), eyes {worstEye:0.00} deg, " +
                $"max glance {maxGlance:0} deg, Walk weight min {worstWalkWeight:0.000} ({walkSamples}), Idle weight min {worstIdleWeight:0.000} ({idleSamples}), " +
                $"eye height off by {worstEyeHeight:0.000} m, skull top {lowTop:0.000}-{highTop:0.000} m, " +
                $"footsteps {walkingFootsteps} walking / {idleFootsteps} not, {cycles:0.00} cycles over {walked:0.00} m");
            Assert.AreEqual(PlayState.Playing, Game.State, "the still chair got the level lost");
            Assert.GreaterOrEqual(routine.LoopsCompleted, 1, "the routine never completed a loop");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
            // Premises: the loop has head glances (a head that followed the body would fail), walks and dwells.
            Assert.GreaterOrEqual(maxGlance, 30f, "premise: no head glance of 30 deg or more in the loop");
            Assert.Greater(frames, 100, "premise: too few rendered frames");
            Assert.Greater(walkSamples, 20, "premise: too few settled walking frames");
            Assert.Greater(idleSamples, 20, "premise: too few settled dwelling frames");
            Assert.Greater(eyeSamples, 50, "premise: too few frames without the telegraph roll");
            Assert.Greater(heightSamples, 20, "premise: too few dwelling frames to measure the eye height");

            Assert.LessOrEqual(worstHead, HeadTolerance, $"the head bone left the eye forward by {worstHead:0.0} deg ({headWhere})");
            Assert.LessOrEqual(worstEye, HeadTolerance, $"the model's eyes left the eye forward by {worstEye:0.0} deg");
            Assert.Greater(worstWalkWeight, WeightAfterFade, $"Walk weight {worstWalkWeight:0.00} while walking ({walkWhere})");
            Assert.Greater(worstIdleWeight, WeightAfterFade, $"Idle weight {worstIdleWeight:0.00} while dwelling ({idleWhere})");
            Assert.LessOrEqual(worstEyeHeight, EyeHeightTolerance, $"the model's eyes are {worstEyeHeight:0.000} m away from {Tuning.EyeHeight} m");
            Assert.That(lowTop - Tuning.EyeHeight, Is.GreaterThanOrEqualTo(HeadTipAboveEyesMin),
                $"the top of the skull stands at {lowTop:0.000} m, too low for eyes at {Tuning.EyeHeight} m (model scale?)");
            Assert.That(highTop - Tuning.EyeHeight, Is.LessThanOrEqualTo(HeadTipAboveEyesMax),
                $"the top of the skull stands at {highTop:0.000} m, too high for eyes at {Tuning.EyeHeight} m (model scale, or a wrong eye centroid in the catalog?)");

            Assert.Greater(walkingSteps, 0, "premise: the loop has no walk");
            Assert.Greater(walkingFootsteps, 0, "no footstep while walking");
            Assert.AreEqual(0, idleFootsteps, $"{idleFootsteps} footsteps over {idleSteps} steps without walking");
            Assert.AreEqual(2f * cycles, walkingFootsteps, 2f, $"{walkingFootsteps} footsteps over {cycles:0.0} walk cycles ({walked:0.0} m): expected two per cycle");
        }

        /// <summary>Paused: every clip at speed 0 and the whole pose held; resumed: the clip runs again.</summary>
        [UnityTest]
        public IEnumerator Step24_PauseStopsTheAnimation()
        {
            Inhabitant h = Habitant;
            InhabitantRig rig = AssertRigged(h, "level1");
            InhabitantRoutine routine = h.Routine;
            int walkingFor = 0;
            void OnStep() => walkingFor = IsWalking(routine.LastActivity) ? walkingFor + 1 : 0;
            Game.FixedStepped += OnStep;
            yield return Run(StepsFor(60f), () => walkingFor >= StepsFor(0.5f), 4f);
            Game.FixedStepped -= OnStep;
            Assert.GreaterOrEqual(walkingFor, StepsFor(0.5f), $"premise: the inhabitant never walked for 0.5 s ({routine.LastActivity})");
            yield return null;
            yield return null;
            AnimationState walk = rig.WalkState;
            Assert.AreEqual(InhabitantRig.Clip.Walk, rig.CurrentClip, "premise: walking plays Walk");
            Assert.Greater(walk.speed, 0f, "premise: the walk clip runs before the pause");

            GamePause.IsPaused = true;
            yield return null;
            yield return null;
            float elapsed = Game.Elapsed;
            float walkTime = walk.time;
            int footsteps = h.FootstepCount;
            Vector3 visual = h.Visual.position;
            Quaternion head = rig.Head.rotation;
            Vector3 palm = FindDeep(rig.Model.transform, "Palm.L").position;
            yield return Steps(50);
            for (int i = 0; i < 5; i++)
            {
                yield return null;
            }
            foreach (AnimationState s in rig.Animation)
            {
                Assert.AreEqual(0f, s.speed, $"clip {s.name} runs at speed {s.speed} while paused");
            }
            Assert.AreEqual(elapsed, Game.Elapsed, "a fixed step ran while paused");
            Assert.AreEqual(walkTime, walk.time, 1e-5f, "the walk clip advanced while paused");
            Assert.AreEqual(footsteps, h.FootstepCount, "a footstep while paused");
            Assert.Less((h.Visual.position - visual).magnitude, 1e-5f, "the body moved while paused");
            Assert.Less(Quaternion.Angle(head, rig.Head.rotation), 0.01f, "the head moved while paused");
            Assert.Less((FindDeep(rig.Model.transform, "Palm.L").position - palm).magnitude, 1e-4f, "the arm moved while paused");

            GamePause.IsPaused = false;
            int resumeSteps = fixedSteps;
            yield return Run(StepsFor(0.5f), null, 1f);
            Assert.Greater(fixedSteps, resumeSteps, "no fixed step after resuming");
            AnimationState current = rig.CurrentClip == InhabitantRig.Clip.Walk ? rig.WalkState : rig.IdleState;
            Assert.Greater(current.speed, 0f, $"clip {current.name} still at speed 0 after resuming");
            Assert.IsTrue(Mathf.Abs(walk.time - walkTime) > 1e-3f || rig.CurrentClip != InhabitantRig.Clip.Walk,
                "the walk clip did not advance after resuming");
        }

        /// <summary>
        /// The "?" (alerted, standing) and "!" (investigating, walking) markers float above the head bone, wherever
        /// the clip moves it. Measured after the inhabitant's LateUpdate and before the HUD's, which may slide a
        /// marker down in screen space to clear the gauges (CONTRACT_M3 6).
        /// </summary>
        [UnityTest]
        public IEnumerator Step24_MarkersFollowTheHeadBone()
        {
            Game.Rules = GameRules.M2;
            Inhabitant h = Habitant;
            InhabitantRig rig = AssertRigged(h, "level1");
            Transform marker = FindDeep(h.transform, "Marker");
            Assert.IsNotNull(marker, "premise: the inhabitant has no Marker");
            float worstSide = 0f, lowAbove = float.MaxValue, highAbove = float.MinValue;
            int question = 0, exclamation = 0;
            void Late()
            {
                if (h.Marker == Inhabitant.MarkerKind.None)
                {
                    return;
                }
                Vector3 d = marker.position - rig.Head.position;
                worstSide = Mathf.Max(worstSide, YawMath.Planar(d).magnitude);
                lowAbove = Mathf.Min(lowAbove, d.y);
                highAbove = Mathf.Max(highAbove, d.y);
                if (h.Marker == Inhabitant.MarkerKind.Question)
                {
                    question++;
                }
                else if (IsWalking(h.Routine.LastActivity))
                {
                    exclamation++;
                }
            }
            RigWatcher watcher = WatchBeforeHud(Late);
            try
            {
                // "?": a creak heard behind the inhabitant, then "!": the chair displaced in its view.
                h.Routine.Alert(h.Routine.Position - YawMath.Forward(h.Routine.BodyYaw) * 2f, NoiseKind.Creak);
                yield return Run(StepsFor(1.5f), null, 1f);
                Chair.Teleport(DisplacedChair, 0f);
                h.Pin(WindowSpot, YawToward(WindowSpot, DisplacedChair), 0f, true);
                yield return Run(StepsFor(6f), () => h.Mode == InhabitantMode.Investigating && IsWalking(h.Routine.LastActivity) && exclamation > 30, 2f);
            }
            finally
            {
                Unwatch(watcher);
            }
            Debug.Log($"[Step24] markers: {question} frames of ?, {exclamation} of ! while walking, off axis {worstSide:0.000} m, " +
                $"{lowAbove:0.00}-{highAbove:0.00} m above the head bone");
            Assert.Greater(question, 10, "premise: the alerted inhabitant never showed the ?");
            Assert.Greater(exclamation, 10, "premise: the investigating inhabitant never walked with the !");
            Assert.LessOrEqual(worstSide, 0.02f, $"a marker drifted {worstSide:0.000} m sideways from the head bone");
            Assert.That(lowAbove, Is.GreaterThanOrEqualTo(0.35f), $"a marker came down to {lowAbove:0.00} m above the head bone");
            Assert.That(highAbove, Is.LessThanOrEqualTo(0.8f), $"a marker rose to {highAbove:0.00} m above the head bone");
        }

        /// <summary>
        /// M3.1 (critique N1): the model frowns. Two brow boxes hang on the head bone with the model's own darkest
        /// material (no new material) on the Inhabitant layer (x-ray like the rest of the model); flat in the routine,
        /// inner ends down while investigating.
        /// </summary>
        [UnityTest]
        public IEnumerator Step24_BrowsFrownWhileInvestigating()
        {
            Game.Rules = GameRules.M2;
            Inhabitant h = Habitant;
            InhabitantRig rig = AssertRigged(h, "level1");
            Transform[] brows = { rig.BrowLeft, rig.BrowRight };
            var skinMaterials = new List<Material>(rig.Skin.sharedMaterials);
            foreach (Transform brow in brows)
            {
                Assert.IsNotNull(brow, "premise: the model has no brows");
                Assert.IsTrue(brow.IsChildOf(rig.Head), $"{brow.name} is not on the head bone");
                var renderer = brow.GetComponent<MeshRenderer>();
                Assert.IsNotNull(renderer, $"{brow.name} has no MeshRenderer");
                Assert.IsTrue(renderer.enabled && brow.gameObject.activeInHierarchy, $"{brow.name} is hidden");
                CollectionAssert.Contains(skinMaterials, renderer.sharedMaterial, $"{brow.name} brings a new material");
                Assert.AreEqual(Layers.Inhabitant, brow.gameObject.layer, $"{brow.name} is not on the Inhabitant layer (x-ray)");
            }
            Assert.IsFalse(h.Frowning, "premise: frowning at level start");
            yield return Run(StepsFor(0.5f), null, 1f);
            float flatLeft = Mathf.DeltaAngle(0f, rig.BrowLeft.localEulerAngles.z);
            float flatRight = Mathf.DeltaAngle(0f, rig.BrowRight.localEulerAngles.z);
            float aboveEyes = rig.BrowLeft.position.y - rig.EyePosition.y;

            Chair.Teleport(DisplacedChair, 0f);
            h.Pin(WindowSpot, YawToward(WindowSpot, DisplacedChair), 0f, true);
            int investigating = 0;
            void OnStep() => investigating = h.Mode == InhabitantMode.Investigating ? investigating + 1 : 0;
            Game.FixedStepped += OnStep;
            yield return Run(StepsFor(6f), () => investigating >= StepsFor(0.4f), 1f);
            Game.FixedStepped -= OnStep;
            Assert.GreaterOrEqual(investigating, StepsFor(0.4f), $"premise: never investigating for 0.4 s (mode {h.Mode})");
            yield return null;
            float frownLeft = Mathf.DeltaAngle(0f, rig.BrowLeft.localEulerAngles.z);
            float frownRight = Mathf.DeltaAngle(0f, rig.BrowRight.localEulerAngles.z);
            Debug.Log($"[Step24] brows: flat {flatLeft:0.0} / {flatRight:0.0} deg, {aboveEyes:0.000} m above the eyes; " +
                $"investigating {frownLeft:0.0} / {frownRight:0.0} deg");

            Assert.That(aboveEyes, Is.InRange(0.01f, 0.05f), $"the brows stand {aboveEyes:0.000} m above the eyes");
            Assert.That(flatLeft, Is.InRange(-1f, 10f), $"left brow tilted {flatLeft:0.0} deg in the routine");
            Assert.That(flatRight, Is.InRange(-10f, 1f), $"right brow tilted {flatRight:0.0} deg in the routine");
            Assert.IsTrue(h.Frowning, "investigating but not frowning");
            // Inner ends down: the left brow (on -x) rolls negative, the right one positive.
            Assert.LessOrEqual(frownLeft, -18f, $"left brow at {frownLeft:0.0} deg while investigating");
            Assert.GreaterOrEqual(frownRight, 18f, $"right brow at {frownRight:0.0} deg while investigating");
        }

        /// <summary>
        /// A carry back on level 1 (M2 rules): while carrying, both hands reach forward to the chair (the arms are set
        /// absolutely over the Walk clip, which swings them at the sides); while picking up, the spine bends forward.
        /// </summary>
        [UnityTest]
        public IEnumerator Step24_CarryArmsAndBend()
        {
            Game.Rules = GameRules.M2;
            Inhabitant h = Habitant;
            InhabitantRig rig = AssertRigged(h, "level1");
            Transform palmL = FindDeep(rig.Model.transform, "Palm.L");
            Transform palmR = FindDeep(rig.Model.transform, "Palm.R");
            Assert.IsNotNull(palmL, "premise: no Palm.L bone");
            Assert.IsNotNull(palmR, "premise: no Palm.R bone");
            Assert.IsNotNull(rig.Spine, "premise: no spine bone");

            Chair.Teleport(DisplacedChair, 0f);
            h.Pin(WindowSpot, YawToward(WindowSpot, DisplacedChair), 0f, true);
            yield return Steps(1);
            Assert.IsTrue(Game.Seen, "premise: the inhabitant sees the displaced chair");

            InhabitantRoutine routine = h.Routine;
            float carrySince = -1f, bendSince = -1f;
            float worstReach = float.MaxValue, maxLean = 0f, carryLean = 0f;
            float lowHand = float.MaxValue, highHand = float.MinValue;
            int carrySamples = 0, bendSamples = 0;
            void Late()
            {
                RoutineActivity a = routine.LastActivity;
                carrySince = a == RoutineActivity.Carrying ? (carrySince < 0f ? Time.time : carrySince) : -1f;
                bool bending = a == RoutineActivity.PickingUp || a == RoutineActivity.PuttingDown;
                bendSince = bending ? (bendSince < 0f ? Time.time : bendSince) : -1f;
                Quaternion toBody = Quaternion.Inverse(Quaternion.Euler(0f, h.Visual.eulerAngles.y, 0f));
                if (carrySince >= 0f && Time.time - carrySince >= 0.4f)
                {
                    foreach (Transform palm in new[] { palmL, palmR })
                    {
                        Vector3 local = toBody * (palm.position - h.Visual.position);
                        worstReach = Mathf.Min(worstReach, local.z);
                        lowHand = Mathf.Min(lowHand, local.y);
                        highHand = Mathf.Max(highHand, local.y);
                    }
                    // The bend must not outlive the pick up (no clip keys the spine to undo it).
                    carryLean = Mathf.Max(carryLean, Vector3.Angle(rig.Spine.up, Vector3.up));
                    carrySamples++;
                }
                if (bendSince >= 0f && Time.time - bendSince >= 0.25f)
                {
                    maxLean = Mathf.Max(maxLean, Vector3.Angle(rig.Spine.up, Vector3.up));
                    bendSamples++;
                }
            }
            RigWatcher watcher = Watch(Late);
            try
            {
                yield return Run(StepsFor(40f), () => Game.State != PlayState.Playing || (Game.CarryCount > 0 && !h.Routine.IsCarrying), 2f);
            }
            finally
            {
                Unwatch(watcher);
            }
            Debug.Log($"[Step24] carry: hands at least {worstReach:0.00} m ahead, height {lowHand:0.00}-{highHand:0.00} m ({carrySamples} frames), " +
                $"spine lean {maxLean:0.0} deg bending ({bendSamples} frames), {carryLean:0.0} deg carrying");
            Assert.AreEqual(PlayState.Playing, Game.State, $"the level ended during the carry ({Game.LoseReason})");
            Assert.AreEqual(1, Game.CarryCount, $"premise: no carry (mode {h.Mode}, activity {routine.LastActivity})");
            Assert.Greater(carrySamples, 5, "premise: too few settled carrying frames");
            Assert.Greater(bendSamples, 2, "premise: too few settled bending frames");
            Assert.GreaterOrEqual(worstReach, 0.25f, $"a hand fell back to {worstReach:0.00} m in front of the body while carrying");
            Assert.That(lowHand, Is.GreaterThan(0.6f), $"a hand dropped to {lowHand:0.00} m while carrying");
            Assert.That(highHand, Is.LessThan(1.5f), $"a hand rose to {highHand:0.00} m while carrying");
            Assert.GreaterOrEqual(maxLean, 20f, $"the spine leaned only {maxLean:0.0} deg while picking up or putting down");
            Assert.LessOrEqual(carryLean, 12f, $"the spine still leans {carryLean:0.0} deg while carrying, after the pick up");
        }
    }

    /// <summary>Runs a callback in a LateUpdate after every other one: measures the pose that gets rendered.</summary>
    [DefaultExecutionOrder(32000)]
    public class RigWatcher : MonoBehaviour
    {
        public Action Late;

        protected void LateUpdate()
        {
            Late?.Invoke();
        }
    }

    /// <summary>The same, after the inhabitants (order 0) but before the HUD (order 400), which clamps the markers.</summary>
    [DefaultExecutionOrder(200)]
    public sealed class RigWatcherBeforeHud : RigWatcher
    {
    }
}
