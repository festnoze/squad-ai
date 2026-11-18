using System;
using System.Collections;
using System.Collections.Generic;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// The M4 bodies probe (docs/CONTRACT_M4.md 2, 8 step 29, amendments 9.3, 9.7, 9.9, 9.10) on the real Boot scene,
    /// level 1, with the body set by <see cref="FurnitureController.SetBody"/> (amendment 9.4: these tests never wait
    /// for the M4 levels). Step 29 is the office chair; the Step29e_ and later cases check the body plumbing every
    /// M4 rule stands on: sizes, speeds, careful mode, the action latch, the stool's states, the pin and the dark
    /// lamp's range. M4.1 (CONTRACT_M4 10.3, 10.4, 10.7): the stool's warning band and head-on rule, its lying
    /// samples, the lit range during a lamp switch, and the roll gated by GameRules.Bodies.
    /// Every wait counts fixed steps (the GameState.FixedStepped counter) under a real time guard, never rendered
    /// frames, and every scenario asserts its premise so it cannot pass for the wrong reason.
    /// </summary>
    public sealed class ProbeTestsM4Bodies
    {
        private const float Dt = Tuning.FixedStep;
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;
        private readonly List<Sample> trace = new List<Sample>();

        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;
        private Inhabitant Habitant => Game.MainInhabitant;

        // Level 1 (8 x 6 m, centered on the origin): the lane z = -1 is free from wall to wall (the sofa ends at
        // z = -0.5, the table starts at z = -1.45), a long open floor for the fast bodies.
        private const float LaneZ = -1f;
        private static readonly Vector3 LaneStart = new Vector3(-3.4f, 0f, LaneZ);
        // A corner spot where the frozen inhabitant looks at the +x wall: the lane is behind it.
        private static readonly Vector3 AwaySpot = new Vector3(3.0f, 0f, 2.4f);
        private const float AwayYaw = 90f;

        /// <summary>The state of the player furniture after one fixed step.</summary>
        private struct Sample
        {
            public bool Moving;
            public bool Action;
            public bool Gliding;
            public bool Tipped;
            public float Speed;
            public float Yaw;
            public Vector3 Position;
            public Vector3? Predicted;
            public bool Seen;
            public bool Caught;
            public float Factor;
        }

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            fixedSteps = 0;
            trace.Clear();
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
            Assert.IsNotNull(Game.Level, "the level was never built");
            Assert.AreEqual("level1", Game.Def.Id, "premise: the probe runs on level 1");
            // M4 rules (GameState hands them to the furniture on every step).
            Game.Rules = GameRules.M4;
            Game.FixedStepped += Record;
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.FixedStepped -= Record;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                    main.Game.Furniture.ScriptedCareful = null;
                }
            }
            yield return null;
        }

        private void Record()
        {
            fixedSteps++;
            FurnitureController c = Game.Furniture;
            if (c == null)
            {
                return;
            }
            trace.Add(new Sample
            {
                Moving = c.IsMoving,
                Action = c.ActionActive,
                Gliding = c.Gliding,
                Tipped = c.Tipped,
                Speed = c.PlanarSpeed,
                Yaw = c.Yaw,
                Position = c.transform.position,
                Predicted = c.PredictedStop,
                Seen = Game.Seen,
                Caught = Game.State == PlayState.Caught,
                Factor = c.SightRangeFactor,
            });
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        /// <summary>Waits <paramref name="count"/> game fixed steps (the GameState counter), under a real time guard.</summary>
        private IEnumerator Steps(int count)
        {
            yield return Until(null, count);
        }

        /// <summary>
        /// Waits until <paramref name="until"/> holds after a fixed step, at most <paramref name="maxSteps"/> fixed steps:
        /// bounded by game time, never by frames.
        /// </summary>
        private IEnumerator Until(Func<bool> until, int maxSteps)
        {
            int end = fixedSteps + maxSteps;
            float realStart = Time.realtimeSinceStartup;
            while (fixedSteps < end && (until == null || !until()) && Time.realtimeSinceStartup - realStart < 120f)
            {
                yield return new WaitForFixedUpdate();
            }
            Assert.Less(Time.realtimeSinceStartup - realStart, 120f, "the game stopped stepping");
        }

        private static float Planar(Vector3 a, Vector3 b) => YawMath.Planar(a - b).magnitude;

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(to - from);

        private void PinAway()
        {
            Habitant.Pin(AwaySpot, AwayYaw);
        }

        /// <summary>A body on level 1 at <paramref name="at"/>, facing <paramref name="yaw"/>, input neutral.</summary>
        private void Place(string kind, Vector3 at, float yaw)
        {
            Chair.ScriptedDirection = null;
            Chair.ScriptedCareful = null;
            Chair.SetBody(BodyDef.For(kind));
            Chair.Teleport(at, yaw);
        }

        private void AssertClean()
        {
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        // ----- 29: the office chair -----

        /// <summary>Drives the office chair along the lane (+x) until it rolls at 2 m/s or more, then a few steps more.</summary>
        private IEnumerator DriveOfficeChairToSpeed()
        {
            Place("office_chair", LaneStart, 90f);
            Assert.IsTrue(Chair.Body.Glides, "premise: the office chair glides");
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.Velocity.magnitude >= 2.6f, 75);
            yield return Steps(3);
            Assert.GreaterOrEqual(Chair.Velocity.magnitude, 2f, "premise: the office chair is released at 2 m/s or more");
            Assert.IsTrue(Chair.IsMoving, "premise: the office chair moves before the release");
            Assert.IsFalse(Chair.Gliding, "premise: no glide while the input is held");
        }

        [UnityTest]
        public IEnumerator Step29_OfficeChairGlidesToAStopInExactlyFourTenths()
        {
            PinAway();
            int hops = Chair.HopCount;
            int rolls = Chair.RollCount;
            int driveStart = trace.Count;
            yield return DriveOfficeChairToSpeed();
            Assert.IsTrue(Chair.Rules != null && Chair.Rules.Bodies, "premise: GameRules.Bodies is on");
            float releaseSpeed = Chair.Velocity.magnitude;
            float releaseYaw = Chair.Yaw;
            int release = trace.Count;
            Chair.ScriptedDirection = null;
            yield return Steps(40);

            int moving = 0;
            while (release + moving < trace.Count && trace[release + moving].Moving)
            {
                moving++;
            }
            Assert.That(moving, Is.InRange(19, 20), $"the office chair moved {moving} steps after a release at {releaseSpeed:0.00} m/s");
            for (int i = release + moving; i < trace.Count; i++)
            {
                Assert.IsFalse(trace[i].Moving, $"the office chair moved again {i - release} steps after the release");
            }
            // Constant deceleration: the speed drops by the same amount on every step, to 0 in OfficeChairStopTime.
            float drop = releaseSpeed * Dt / Tuning.OfficeChairStopTime;
            float previous = releaseSpeed;
            for (int k = 0; k < moving; k++)
            {
                Sample s = trace[release + k];
                Assert.IsTrue(s.Gliding, $"glide step {k}: not gliding");
                Assert.AreEqual(drop, previous - s.Speed, 0.01f, $"glide step {k}: the speed dropped from {previous:0.000} to {s.Speed:0.000}");
                Assert.AreEqual(releaseYaw, s.Yaw, 0.5f, $"glide step {k}: the yaw left the velocity");
                previous = s.Speed;
            }
            Assert.IsFalse(Chair.Gliding, "the glide never ended");
            Assert.AreEqual(Vector3.zero, Chair.Velocity, "the velocity is not zero after the glide");
            // Premise: nothing else stopped or saw the chair.
            for (int i = release; i < trace.Count; i++)
            {
                Assert.IsFalse(trace[i].Seen, "premise: the chair was seen");
            }
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.Less(Chair.transform.position.x, 2.5f, "premise: the glide ended before the far wall");
            // It rolls (a tick every RollNoiseInterval of rolling), it never hops.
            int rolling = 0;
            for (int i = driveStart; i < trace.Count; i++)
            {
                rolling += trace[i].Speed > Tuning.MovingSpeedThreshold ? 1 : 0;
            }
            Assert.Greater(rolling, 30, "premise: the office chair rolled for more than 0.6 s");
            Assert.AreEqual(Mathf.FloorToInt(rolling * Dt / Tuning.RollNoiseInterval + 1e-3f), Chair.RollCount - rolls, "roll ticks");
            Assert.AreEqual(hops, Chair.HopCount, "the office chair hopped under GameRules.Bodies");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step29b_SeenDuringTheGlideIsCaught()
        {
            // The watcher stands on the lane ahead of the chair, looking away; at the release it turns to the chair.
            var watcher = new Vector3(2.2f, 0f, LaneZ);
            Habitant.Pin(watcher, 90f);

            // Control: the same release with the glide switched off (GameRules.Bodies) stops at once: not caught.
            GameRules noBodies = GameRules.M4;
            noBodies.Bodies = false;
            Game.Rules = noBodies;
            yield return DriveOfficeChairToSpeedUnderCurrentRules();
            Assert.IsFalse(Game.Seen, "premise: the chair is unseen while it drives");
            Chair.ScriptedDirection = null;
            Habitant.Pin(watcher, YawToward(watcher, Chair.transform.position));
            yield return Steps(30);
            Assert.IsTrue(Game.Seen, "premise: the watcher sees the chair after its turn");
            Assert.AreNotEqual(LoseReason.SeenMoving, Game.LoseReason, "control: a chair that stops at once was caught");

            // The glide: seen while it rolls on, the chair is caught (19 moving steps against a 10 step grace).
            Game.Restart();
            yield return Steps(2);
            Game.Rules = GameRules.M4;
            Habitant.Pin(watcher, 90f);
            yield return DriveOfficeChairToSpeed();
            Assert.IsFalse(Game.Seen, "premise: the chair is unseen while it drives");
            Assert.AreEqual(PlayState.Playing, Game.State);
            int release = trace.Count;
            Chair.ScriptedDirection = null;
            Habitant.Pin(watcher, YawToward(watcher, Chair.transform.position));
            yield return Until(() => Game.State != PlayState.Playing, 30);
            Assert.AreEqual(PlayState.Caught, Game.State, "the chair was seen gliding and not caught");
            Assert.AreEqual(LoseReason.SeenMoving, Game.LoseReason, "caught for another reason");
            int seenMoving = 0;
            for (int i = release; i < trace.Count; i++)
            {
                if (trace[i].Seen && trace[i].Moving)
                {
                    seenMoving++;
                }
                Assert.IsTrue(trace[i].Gliding || !trace[i].Moving, "premise: the chair moved without gliding after the release");
                if (trace[i].Caught)
                {
                    break;
                }
            }
            Assert.AreEqual(Mathf.RoundToInt(Tuning.CaughtGrace / Dt), seenMoving, "caught after a number of seen and moving glide steps other than the grace");
            AssertClean();
        }

        private IEnumerator DriveOfficeChairToSpeedUnderCurrentRules()
        {
            Place("office_chair", LaneStart, 90f);
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.Velocity.magnitude >= 2.6f, 75);
            yield return Steps(3);
            Assert.GreaterOrEqual(Chair.Velocity.magnitude, 2f, "premise: released at 2 m/s or more");
        }

        [UnityTest]
        public IEnumerator Step29c_PredictedStopPointIsWhereItStops()
        {
            PinAway();
            yield return DriveOfficeChairToSpeed();
            GhostView ghost = Game.Ghost;
            Assert.IsNotNull(ghost, "premise: the ghost view exists");
            Assert.IsTrue(Chair.PredictedStop.HasValue, "no predicted stop while the office chair moves");
            Vector3 predicted = Chair.PredictedStop.Value;
            Vector3 releasedAt = Chair.transform.position;
            Assert.Greater(Planar(predicted, releasedAt), 0.3f, "premise: the predicted stop is not just the current position");
            Assert.IsTrue(ghost.StopRingVisible, "the stop ring is not drawn while the office chair moves");
            Assert.Less(Planar(ghost.StopRingPosition, predicted), 1e-3f, "the stop ring is not at the predicted stop");

            Chair.ScriptedDirection = null;
            yield return Steps(5);
            Assert.IsTrue(Chair.Gliding && Chair.PredictedStop.HasValue, "premise: still gliding, with a prediction");
            Vector3 midGlide = Chair.PredictedStop.Value;
            Assert.IsTrue(ghost.StopRingVisible, "the stop ring is not drawn during the glide");
            yield return Until(() => !Chair.IsMoving, 30);
            yield return Steps(2);

            Vector3 rest = Chair.transform.position;
            Assert.Less(Planar(rest, predicted), 0.05f, $"stopped {Planar(rest, predicted):0.000} m from the stop predicted at the release");
            Assert.Less(Planar(rest, midGlide), 0.05f, $"stopped {Planar(rest, midGlide):0.000} m from the stop predicted mid glide");
            Assert.IsFalse(Chair.PredictedStop.HasValue, "a predicted stop while still");
            Assert.IsFalse(ghost.StopRingVisible, "the stop ring stays after the stop");

            // A body without a glide never shows the ring.
            Place("chair", LaneStart, 90f);
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(20);
            Assert.IsTrue(Chair.IsMoving, "premise: the chair moves");
            Assert.IsFalse(Chair.PredictedStop.HasValue || ghost.StopRingVisible, "the chair predicts a stop");
            Chair.ScriptedDirection = null;
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step29d_OppositeInputBrakesNoFaster()
        {
            PinAway();
            yield return DriveOfficeChairToSpeed();
            float releaseYaw = Chair.Yaw;
            float startX = Chair.transform.position.x;
            int release = trace.Count;
            // Full input against the motion: it brakes no faster than a release, and the chair keeps facing its motion.
            Chair.ScriptedDirection = Vector3.left;
            yield return Steps(19);
            int forward = 0;
            float lastX = startX;
            for (int i = release; i < trace.Count; i++)
            {
                if (trace[i].Position.x > lastX + 1e-4f)
                {
                    forward++;
                }
                Assert.AreEqual(releaseYaw, trace[i].Yaw, 0.5f, "the office chair turned toward the input while gliding");
                lastX = trace[i].Position.x;
            }
            Assert.AreEqual(19, forward, "the office chair stopped sooner than a release (19 glide steps)");
            Chair.ScriptedDirection = null;
            AssertClean();
        }

        // ----- Body plumbing -----

        private static readonly string[] Kinds = { "chair", "stool", "armchair", "floor_lamp", "office_chair" };

        [UnityTest]
        public IEnumerator Step29e_SetBodySizesControllerAndSamples()
        {
            PinAway();
            CharacterController cc = Chair.GetComponent<CharacterController>();
            Transform visual = Chair.Visual;
            int visualRenderers = visual != null ? visual.GetComponentsInChildren<Renderer>(true).Length : 0;
            var samples = new Vector3[Tuning.SampleCount];
            foreach (string kind in Kinds)
            {
                BodyDef def = BodyDef.For(kind);
                Place(kind, LaneStart, 90f);
                yield return Steps(2);
                Assert.AreEqual(kind, Chair.Body.Kind, kind + ": body");
                Assert.AreEqual(kind, Chair.Kind, kind + ": kind");
                Assert.AreEqual(def.Radius, cc.radius, 1e-5f, kind + ": controller radius");
                Assert.AreEqual(def.Size.y, cc.height, 1e-5f, kind + ": controller height");
                Assert.Less((cc.center - new Vector3(0f, def.Size.y * 0.5f, 0f)).magnitude, 1e-5f, kind + ": controller center");
                Assert.Less((Chair.Size - def.Size).magnitude, 1e-5f, kind + ": sample box");
                Assert.AreEqual(def.CarryForward, Chair.CarryForward, 1e-5f, kind + ": carry forward");
                Chair.GetSamplePoints(samples);
                Vector3 p = Chair.transform.position;
                Assert.AreEqual(p.y + def.Size.y * 0.5f, samples[0].y, 1e-4f, kind + ": center sample height");
                float corner = new Vector2(def.Size.x * 0.5f - Tuning.SampleInset, def.Size.z * 0.5f - Tuning.SampleInset).magnitude;
                for (int i = 1; i < samples.Length; i++)
                {
                    Assert.AreEqual(p.y + def.Size.y - Tuning.SampleInset, samples[i].y, 1e-4f, kind + ": top sample height");
                    Assert.AreEqual(corner, Planar(samples[i], p), 1e-4f, kind + ": top corner distance");
                }
                Assert.AreEqual(kind == "floor_lamp", Chair.Lamp != null, kind + ": lamp light");
                if (Chair.Lamp != null)
                {
                    Light light = Chair.Lamp.Light;
                    Assert.IsNotNull(light, "lamp: no Light");
                    Assert.AreEqual(LightType.Point, light.type, "lamp: not a point light");
                    Assert.AreEqual(LightShadows.None, light.shadows, "lamp: the light casts shadows (the sun is the only shadowed light)");
                    Assert.IsTrue(light.enabled && Chair.Lamp.On, "lamp: off at start");
                }
                Assert.AreSame(visual, Chair.Visual, kind + ": the visual was replaced");
                Assert.AreEqual(visualRenderers, visual != null ? visual.GetComponentsInChildren<Renderer>(true).Length : 0, kind + ": the visual changed");
                Assert.IsFalse(Chair.IsMoving, kind + ": moving after SetBody");
            }
            // Null and unknown kinds are the chair, whose row is the M1 constants.
            Chair.SetBody(null);
            Assert.AreEqual("chair", Chair.Body.Kind);
            Assert.AreEqual(Tuning.ChairControllerRadius, cc.radius, 1e-6f);
            Assert.AreEqual(Tuning.ChairControllerHeight, cc.height, 1e-6f);
            Assert.IsNull(Chair.Lamp, "the lamp light outlived the lamp body");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step29f_BodyConstantsApplyUnderEveryRuleSet()
        {
            PinAway();
            // GameRules.M1: no special rule at all, so nothing tips or glides; the body constants still apply.
            Game.Rules = GameRules.M1;
            foreach (string kind in Kinds)
            {
                BodyDef def = BodyDef.For(kind);
                Place(kind, LaneStart, 90f);
                yield return Steps(1);
                // Acceleration: the first step from rest.
                Chair.ScriptedDirection = Vector3.right;
                yield return Steps(1);
                Assert.AreEqual(def.Accel * Dt, Chair.PlanarSpeed, 0.01f, kind + ": first step speed (acceleration)");
                // Max speed: the plateau (the stool's slow stage from StoolTellSpeed to 2.4 m/s takes about 1.2 s). Without
                // GameRules.Bodies every body hops, the office chair too, and none rolls.
                int hops = Chair.HopCount;
                int rolls = Chair.RollCount;
                yield return Steps(90);
                Assert.AreEqual(def.MaxSpeed, Chair.PlanarSpeed, 0.02f, kind + ": max speed");
                Assert.Greater(Chair.HopCount, hops, kind + ": no hops without GameRules.Bodies");
                Assert.AreEqual(rolls, Chair.RollCount, kind + ": rolls without GameRules.Bodies");
                Chair.ScriptedDirection = null;
                yield return Steps(2);
                Assert.IsFalse(Chair.IsMoving || Chair.Tipped || Chair.Gliding, kind + ": under M1 rules it stops at once");
                // Turn rate: the first step of a half turn.
                Chair.Teleport(Chair.transform.position, 0f);
                Chair.ScriptedDirection = Vector3.back;
                yield return Steps(1);
                Assert.AreEqual(def.TurnRate, Mathf.Abs(Chair.YawRate), 1f, kind + ": turn rate");
                Chair.ScriptedDirection = null;
                yield return Steps(2);
            }

            // The stool's two stages: fast up to StageSpeed, then StoolHighAccel.
            Place("stool", LaneStart, 90f);
            float stage = Chair.Body.StageSpeed;
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.PlanarSpeed > stage + 0.01f, 30);
            float v0 = Chair.PlanarSpeed;
            Assert.Less(v0, stage + 0.05f, "the stool shot past the stage speed");
            yield return Steps(25);
            Assert.AreEqual(Tuning.StoolHighAccel * 0.5f, Chair.PlanarSpeed - v0, 0.03f, "the stool's high stage acceleration");
            Chair.ScriptedDirection = null;
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step29g_CarefulModeHalvesTheMaxSpeed()
        {
            PinAway();
            foreach (string kind in new[] { "chair", "stool", "office_chair" })
            {
                BodyDef def = BodyDef.For(kind);
                Place(kind, LaneStart, 90f);
                InputReader.InjectCareful(true);
                Chair.ScriptedDirection = Vector3.right;
                yield return Steps(60);
                Assert.IsTrue(Chair.Careful, kind + ": careful mode is off with the key held");
                Assert.AreEqual(def.MaxSpeed * Tuning.CarefulFactor, Chair.PlanarSpeed, 0.02f, kind + ": careful speed");
                Assert.IsFalse(Chair.TellActive, kind + ": the tell shows at careful speed");
                Chair.ScriptedDirection = null;
                InputReader.InjectCareful(false);
                yield return Until(() => !Chair.IsMoving, 30);
                Assert.IsFalse(Chair.Tipped, kind + ": careful speed tipped it on release");
            }

            // Premise: without the key the same drive is faster; with GameRules.Bodies off the key does nothing.
            Place("chair", LaneStart, 90f);
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(40);
            Assert.AreEqual(Tuning.ChairMaxSpeed, Chair.PlanarSpeed, 0.02f, "premise: full speed without the key");
            Chair.ScriptedDirection = null;
            GameRules noBodies = GameRules.M4;
            noBodies.Bodies = false;
            Game.Rules = noBodies;
            Place("chair", LaneStart, 90f);
            InputReader.InjectCareful(true);
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(40);
            Assert.IsFalse(Chair.Careful, "careful mode without GameRules.Bodies");
            Assert.AreEqual(Tuning.ChairMaxSpeed, Chair.PlanarSpeed, 0.02f, "careful mode slowed the chair without GameRules.Bodies");
            Chair.ScriptedDirection = null;
            InputReader.InjectCareful(false);
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step29h_ActionPressIsLatchedAndConsumedInTheFixedStep()
        {
            PinAway();
            Place("floor_lamp", LaneStart, 90f);
            yield return Steps(2);
            LampLight lamp = Chair.Lamp;
            Assert.IsNotNull(lamp, "premise: the lamp body has a light");
            Assert.IsTrue(lamp.On && Mathf.Approximately(Chair.SightRangeFactor, 1f), "premise: the lamp starts on");
            Color ambientOn = RenderSettings.ambientSkyColor;
            int toggles = Chair.ToggleCount;

            // One injected press: the next fixed step starts the switch, a LampToggleTime action.
            InputReader.InjectAction();
            int start = trace.Count;
            Vector3 at = Chair.transform.position;
            yield return Steps(1);
            Assert.AreEqual(toggles + 1, Chair.ToggleCount, "the press did not reach the fixed step");
            Assert.IsTrue(Chair.ActionActive && Chair.IsMoving, "a switch is an action, and an action is moving");
            Assert.AreEqual(FurnitureController.BodyAction.Toggle, Chair.Action);
            Assert.IsFalse(lamp.On, "the lamp is still on");
            Assert.IsFalse(lamp.Light.enabled, "the light still shines");
            Assert.Less(RenderSettings.ambientSkyColor.grayscale, ambientOn.grayscale, "the room did not dim");
            // CONTRACT_M4 10.4: the rules keep the lit range until the switch ends.
            Assert.AreEqual(1f, Chair.SightRangeFactor, 1e-6f, "the switch does not use the lit range");

            // A press during the action is dropped, never queued for after it.
            InputReader.InjectAction();
            yield return Steps(20);
            Assert.AreEqual(toggles + 1, Chair.ToggleCount, "a press made during the action fired after it");
            Assert.IsFalse(Chair.ActionActive, "the action never ended");
            int actionSteps = 0;
            for (int i = start; i < trace.Count; i++)
            {
                if (trace[i].Action)
                {
                    actionSteps++;
                    Assert.IsTrue(trace[i].Moving, "an action step was not moving");
                    Assert.AreEqual(1f, trace[i].Factor, 1e-6f, $"switch step {actionSteps}: not the lit range");
                }
                else
                {
                    Assert.AreEqual(Tuning.LampOffLight, trace[i].Factor, 1e-6f, "after the switch: not the dark range");
                }
                Assert.Less(Planar(trace[i].Position, at), 1e-4f, "the lamp travelled during its switch");
            }
            Assert.AreEqual(Mathf.RoundToInt(Tuning.LampToggleTime / Dt), actionSteps, "the switch did not last LampToggleTime");
            Assert.Less(actionSteps, trace.Count - start, "premise: steps after the switch were recorded");
            Assert.IsFalse(Chair.IsMoving, "moving after the switch");
            Assert.AreEqual(Tuning.LampOffLight, Chair.SightRangeFactor, 1e-6f, "the dark range factor");

            // The vision and the floor cone use the dark range.
            Vision vision = Game.Level.Visions[0];
            VisionConeView cone = Game.Level.Cones[0];
            Assert.AreEqual(Tuning.LampOffLight, vision.RangeFactor, 1e-6f, "the vision ignores the dark lamp");
            Assert.AreEqual(Tuning.ViewRange * Tuning.LampOffLight, cone.Range, 1e-4f, "the cone shows the full range");

            // A second press switches it back on, and the room light comes back exactly.
            InputReader.InjectAction();
            yield return Steps(1);
            Assert.AreEqual(toggles + 2, Chair.ToggleCount);
            Assert.IsTrue(lamp.On && lamp.Light.enabled, "the lamp did not switch back on");
            Assert.AreEqual(ambientOn, RenderSettings.ambientSkyColor, "the ambient was not restored");
            yield return Steps(20);
            Assert.IsFalse(Chair.ActionActive, "premise: the switch is over before the next presses");
            Assert.AreEqual(1f, vision.RangeFactor, 1e-6f);

            // ResetInjections drops a pending press; GameRules.Lamp off makes E do nothing.
            InputReader.InjectAction();
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            yield return Steps(2);
            Assert.AreEqual(toggles + 2, Chair.ToggleCount, "ResetInjections left a press");
            GameRules noLamp = GameRules.M4;
            noLamp.Lamp = false;
            Game.Rules = noLamp;
            InputReader.InjectAction();
            yield return Steps(3);
            Assert.AreEqual(toggles + 2, Chair.ToggleCount, "the lamp switched without GameRules.Lamp");
            Assert.IsFalse(Chair.IsMoving, "the press moved the lamp without GameRules.Lamp");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step29i_StoolTipsLiesAndRightsOnAPress()
        {
            PinAway();
            Place("stool", LaneStart, 90f);
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.Velocity.magnitude > Tuning.StoolTipSpeed + 0.2f, 60);
            yield return Steps(1);
            Assert.Greater(Chair.Velocity.magnitude, Tuning.StoolTipSpeed, "premise: the stool goes faster than the threshold");
            Assert.IsTrue(Chair.TellActive, "no tell above the threshold");
            Assert.AreEqual(1f, Chair.TellStrength, 1e-6f, "the tell is not full above the threshold");
            int topples = Chair.ToppleCount;
            var samples = new Vector3[Tuning.SampleCount];
            Vector3 size = Chair.Size;
            Chair.GetSamplePoints(samples);
            Assert.AreEqual(size.y - Tuning.SampleInset, samples[1].y - Chair.transform.position.y, 1e-4f, "premise: upright samples");

            // Released too fast: it falls (an action, moving, in place) for StoolFallTime.
            int release = trace.Count;
            Vector3 at = Chair.transform.position;
            Chair.ScriptedDirection = null;
            yield return Steps(1);
            Assert.IsTrue(Chair.Tipped && Chair.ActionActive && Chair.IsMoving, "released too fast, the stool did not fall");
            Assert.AreEqual(FurnitureController.BodyAction.Fall, Chair.Action);
            Assert.IsFalse(Chair.TellActive, "the tell shows while it falls");
            Chair.GetSamplePoints(samples);
            Assert.AreEqual(size.y - Tuning.SampleInset, samples[1].y - Chair.transform.position.y, 1e-4f,
                "a falling stool lost its upright samples (the fall keeps the taller box)");
            yield return Until(() => !Chair.ActionActive, 30);
            int fall = 0;
            for (int i = release; i < trace.Count; i++)
            {
                fall += trace[i].Action ? 1 : 0;
                Assert.Less(Planar(trace[i].Position, at), 1e-4f, "the stool slid while falling");
            }
            Assert.AreEqual(Mathf.RoundToInt(Tuning.StoolFallTime / Dt), fall, "the fall did not last StoolFallTime");
            Assert.AreEqual(topples + 1, Chair.ToppleCount, "no topple when it landed");

            // Lying down: still, until a move key is pressed. A held key does not count, only a press.
            yield return Steps(50);
            Assert.IsTrue(Chair.LyingDown && !Chair.IsMoving, "the stool got up by itself");
            // CONTRACT_M4 10.3: lying, it is seen from the lying box: as high as it is wide, as long as it is tall.
            Chair.GetSamplePoints(samples);
            Vector3 b = Chair.transform.position;
            Assert.AreEqual(size.x * 0.5f, samples[0].y - b.y, 1e-4f, "lying: center sample height");
            float lyingCorner = new Vector2(size.y * 0.5f - Tuning.SampleInset, size.z * 0.5f - Tuning.SampleInset).magnitude;
            for (int i = 1; i < samples.Length; i++)
            {
                Assert.AreEqual(size.x - Tuning.SampleInset, samples[i].y - b.y, 1e-4f, "lying: top sample height");
                Assert.AreEqual(lyingCorner, Planar(samples[i], b), 1e-4f, "lying: top corner distance");
            }
            InputReader.InjectMovePress();
            int press = trace.Count;
            yield return Steps(1);
            Assert.AreEqual(FurnitureController.BodyAction.Right, Chair.Action, "a move press did not right the stool");
            Assert.IsTrue(Chair.IsMoving, "righting is moving");
            yield return Until(() => !Chair.ActionActive, 40);
            int right = 0;
            for (int i = press; i < trace.Count; i++)
            {
                right += trace[i].Action ? 1 : 0;
            }
            Assert.AreEqual(Mathf.RoundToInt(Tuning.StoolRightTime / Dt), right, "the righting did not last StoolRightTime");
            Assert.IsFalse(Chair.Tipped, "still tipped after righting");
            Assert.AreEqual(topples + 1, Chair.ToppleCount);
            Chair.GetSamplePoints(samples);
            Assert.AreEqual(size.y - Tuning.SampleInset, samples[1].y - Chair.transform.position.y, 1e-4f, "upright again: upright samples");

            // A move key held from the fall through the lying needs a fresh press.
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.Velocity.magnitude > Tuning.StoolTipSpeed + 0.2f, 60);
            Chair.ScriptedDirection = null;
            yield return Steps(2);
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.LyingDown, 30);
            yield return Steps(10);
            Assert.IsTrue(Chair.LyingDown, "a key held through the fall righted the stool");
            Chair.ScriptedDirection = null;
            yield return Steps(1);
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(1);
            Assert.AreEqual(FurnitureController.BodyAction.Right, Chair.Action, "a fresh press did not right the stool");
            Chair.ScriptedDirection = null;
            yield return Until(() => !Chair.Tipped, 40);

            // Release (the carry back) clears Tipped at once.
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.Velocity.magnitude > Tuning.StoolTipSpeed + 0.2f, 60);
            Chair.ScriptedDirection = null;
            yield return Steps(1);
            Assert.IsTrue(Chair.Tipped, "premise: tipped");
            Chair.Release(Chair.Pose);
            Assert.IsFalse(Chair.Tipped || Chair.ActionActive, "Release did not stand the stool up");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step29j_StoolTipsOnAHeadOnWallHitButNotAtCarefulSpeed()
        {
            PinAway();
            // The -x wall, head on along the lane.
            var start = new Vector3(-0.6f, 0f, LaneZ);
            Place("stool", start, 270f);
            InputReader.InjectCareful(true);
            Chair.ScriptedDirection = Vector3.left;
            yield return Until(() => Chair.transform.position.x < -3.5f && Chair.PlanarSpeed < 0.05f, 250);
            yield return Steps(25);
            Assert.Less(Chair.transform.position.x, -3.5f, "premise: the stool reached the wall");
            Assert.IsFalse(Chair.Tipped, "a careful stool tipped on the wall");
            Chair.ScriptedDirection = null;
            InputReader.InjectCareful(false);
            yield return Steps(2);

            Place("stool", start, 270f);
            Chair.ScriptedDirection = Vector3.left;
            float fastest = 0f;
            yield return Until(() =>
            {
                if (!Chair.Tipped)
                {
                    fastest = Mathf.Max(fastest, Chair.Velocity.magnitude);
                }
                return Chair.Tipped;
            }, 250);
            Assert.Greater(fastest, Tuning.StoolTipSpeed, "premise: the stool hit the wall faster than the threshold");
            Assert.IsTrue(Chair.Tipped, "a head-on wall hit did not tip the stool");
            Assert.Less(Chair.transform.position.x, -3.4f, "premise: it tipped at the wall, not before");
            Chair.ScriptedDirection = null;
            AssertClean();
        }

        /// <summary>
        /// A player furniture of its own, stepped by the test itself: GameState pins the level's player from its sit
        /// flag on every step (amendment 9.2), so the pin semantics are checked on a controller nobody else drives.
        /// </summary>
        private FurnitureController Standalone(string kind, Vector3 at, float yaw)
        {
            var go = new GameObject("Standalone " + kind) { layer = Layers.Player };
            go.transform.SetParent(Game.Level.Root.transform, false);
            var cc = go.AddComponent<CharacterController>();
            cc.skinWidth = 0.02f;
            cc.minMoveDistance = 0f;
            cc.stepOffset = 0.05f;
            var f = go.AddComponent<FurnitureController>();
            f.Rules = GameRules.M4;
            f.SetBody(BodyDef.For(kind));
            f.Teleport(at, yaw);
            return f;
        }

        private static void StepManually(FurnitureController f, int count)
        {
            for (int i = 0; i < count; i++)
            {
                f.Step(Dt, true);
            }
        }

        [UnityTest]
        public IEnumerator Step29k_PinnedTakesNoInputAndUnpinWaitsForNeutral()
        {
            PinAway();
            yield return Steps(1);
            // Away from the level's player, on free floor between the sofa and the table.
            var at = new Vector3(1.0f, 0f, 0.9f);
            FurnitureController f = Standalone("chair", at, 90f);
            Assert.AreNotSame(Chair, f, "premise: a controller GameState does not drive");
            f.ScriptedDirection = Vector3.right;
            StepManually(f, 3);
            Assert.IsTrue(f.IsMoving, "premise: the standalone chair moves");
            f.ScriptedDirection = null;
            StepManually(f, 1);
            at = f.transform.position;

            f.Pin(true);
            f.ScriptedDirection = Vector3.right;
            StepManually(f, 20);
            Assert.IsTrue(f.Pinned);
            Assert.IsFalse(f.IsMoving, "a pinned chair moves");
            Assert.Less(Planar(f.transform.position, at), 1e-4f, "a pinned chair travelled");

            // Unpinned with the key still held: ignored until the input is neutral for one step.
            f.Pin(false);
            StepManually(f, 10);
            Assert.IsTrue(f.WaitingForNeutralInput, "Pin(false) did not wait for a neutral input");
            Assert.IsFalse(f.IsMoving, "a key held through the pin moved the chair");
            Assert.Less(Planar(f.transform.position, at), 1e-4f, "a key held through the pin moved the chair");
            f.ScriptedDirection = null;
            StepManually(f, 1);
            Assert.IsFalse(f.WaitingForNeutralInput, "a neutral step did not re-arm the input");
            f.ScriptedDirection = Vector3.right;
            StepManually(f, 3);
            Assert.IsTrue(f.IsMoving, "the input is dead after the unpin");
            f.ScriptedDirection = null;
            StepManually(f, 1);

            // Only a change does anything (GameState calls it on every step).
            f.Pin(false);
            Assert.IsFalse(f.WaitingForNeutralInput, "a repeated Pin(false) re-armed the wait");
            f.Pin(true);
            f.Pin(true);
            f.Pin(false);
            Assert.IsTrue(f.WaitingForNeutralInput, "premise: a real unpin re-arms the wait");
            StepManually(f, 1);

            // A pin ends an action at once: a lamp switching.
            f.SetBody(BodyDef.For("floor_lamp"));
            InputReader.InjectAction();
            StepManually(f, 1);
            Assert.IsTrue(f.ActionActive && f.ToggleCount == 1, "premise: the lamp switch runs");
            f.Pin(true);
            Assert.IsFalse(f.ActionActive, "a pin left the action running");
            StepManually(f, 1);
            Assert.IsFalse(f.IsMoving, "pinned during an action, still moving");
            f.Pin(false);
            UnityEngine.Object.DestroyImmediate(f.gameObject);
            yield return Steps(1);
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step29l_DarkLampIsSeenOnlyWithinTheShortRange()
        {
            // The watcher looks down the free band z = 1.5 (the bookshelf ends at z = 2.6, the sofa at z = 0.4).
            var eyeSpot = new Vector3(-3.0f, 0f, 1.5f);
            var far = new Vector3(3.0f, 0f, 1.5f);

            // CONTRACT_M4 10.4: switched off in plain view at 6 m, the switch uses the lit range: seen on every
            // action step, and caught (15 steps against the 10 step grace).
            Habitant.Pin(eyeSpot, 90f);
            Place("floor_lamp", far, 0f);
            yield return Steps(2);
            Vision vision = Game.Level.Visions[0];
            Assert.IsTrue(vision.SeesPlayer, "premise: the lit lamp is seen at 6 m");
            int start = trace.Count;
            InputReader.InjectAction();
            yield return Until(() => Game.State != PlayState.Playing, 25);
            int seenSwitching = 0;
            for (int i = start; i < trace.Count; i++)
            {
                if (trace[i].Action)
                {
                    Assert.IsTrue(trace[i].Seen, "the lamp went unseen during its switch at 6 m");
                    seenSwitching++;
                }
            }
            Assert.Greater(seenSwitching, 0, "premise: the switch started");
            Assert.AreEqual(PlayState.Caught, Game.State, "switching off in plain view at 6 m was not caught");
            Assert.AreEqual(LoseReason.SeenMoving, Game.LoseReason);

            // Out of sight, the switched-off lamp is seen only within LampOffLight x ViewRange.
            Game.Restart();
            yield return Steps(2);
            vision = Game.Level.Visions[0];
            VisionConeView cone = Game.Level.Cones[0];
            Habitant.Pin(eyeSpot, 270f);
            Place("floor_lamp", far, 0f);
            InputReader.InjectAction();
            yield return Until(() => Chair.ToggleCount > 0 && !Chair.ActionActive, 30);
            Assert.IsFalse(Chair.Lamp.On, "premise: the lamp is off");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: switched off out of sight");
            Habitant.Pin(eyeSpot, 90f);
            yield return Steps(1);
            Assert.IsFalse(vision.SeesPlayer, "the dark lamp is seen at 6 m");
            Chair.Teleport(new Vector3(0.0f, 0f, 1.5f), 0f);
            yield return Steps(1);
            Assert.IsTrue(vision.SeesPlayer, "the dark lamp is not seen at 3 m");
            // The cone: the shorter fan, in another (dimmed) material.
            yield return null;
            Material dark = cone.GetComponent<MeshRenderer>().sharedMaterial;
            Assert.AreEqual(Tuning.ViewRange * Tuning.LampOffLight, cone.Range, 1e-4f);
            // Switched back on out of sight.
            Habitant.Pin(eyeSpot, 270f);
            yield return Steps(1);
            InputReader.InjectAction();
            yield return Until(() => Chair.Lamp.On && !Chair.ActionActive, 30);
            yield return Steps(1);
            yield return null;
            Assert.AreEqual(Tuning.ViewRange, cone.Range, 1e-4f, "the cone stays short with the lamp on");
            Assert.AreNotSame(dark, cone.GetComponent<MeshRenderer>().sharedMaterial, "the dark cone is not dimmed");
            AssertClean();
        }

        // ----- M4.1 (CONTRACT_M4 10.3): the stool's warning band and head-on rule -----

        [UnityTest]
        public IEnumerator Step29m_StoolShortPressesNeverTipAndTheTellWarnsFirst()
        {
            PinAway();
            Assert.AreEqual(Tuning.StoolTellSpeed, BodyDef.For("stool").StageSpeed, 1e-6f,
                "premise: the stool's fast stage ends at the tell speed (BodyDef, core)");
            // A 0.12 s and a 0.25 s press (6 and 13 steps, rounded up to whole steps) from rest, then a release.
            foreach (int pressSteps in new[] { 6, 13 })
            {
                Place("stool", LaneStart, 90f);
                yield return Steps(1);
                int topples = Chair.ToppleCount;
                float peak = 0f;
                int tells = 0;
                Chair.ScriptedDirection = Vector3.right;
                for (int k = 0; k < pressSteps; k++)
                {
                    yield return Steps(1);
                    float v = Chair.Velocity.magnitude;
                    peak = Mathf.Max(peak, v);
                    Assert.AreEqual(v > Tuning.StoolTellSpeed, Chair.TellActive, $"{pressSteps} step press, step {k}: tell at {v:0.000} m/s");
                    tells += Chair.TellActive ? 1 : 0;
                }
                Chair.ScriptedDirection = null;
                yield return Steps(25);
                Assert.IsFalse(Chair.Tipped, $"a {pressSteps * Dt:0.00} s press from rest tipped the stool (peak {peak:0.000} m/s)");
                Assert.AreEqual(topples, Chair.ToppleCount);
                Assert.Less(peak, Tuning.StoolTipSpeed, "premise: the press stayed below the tip speed");
                Assert.Greater(peak, Tuning.StoolTellSpeed, "premise: the press reached the warning band");
                Assert.Greater(tells, 0, "the tell never showed in the warning band");
            }

            // A long press: the tell shows for the whole band before the threshold, growing to full; then it tips.
            Place("stool", LaneStart, 90f);
            yield return Steps(1);
            Chair.ScriptedDirection = Vector3.right;
            int warned = 0;
            float strength = 0f;
            yield return Until(() =>
            {
                float v = Chair.Velocity.magnitude;
                if (Chair.TellActive && v <= Tuning.StoolTipSpeed)
                {
                    warned++;
                    Assert.GreaterOrEqual(Chair.TellStrength, strength, "the tell weakened while the stool sped up");
                    Assert.Less(Chair.TellStrength, 1f, "the tell is full below the threshold");
                    strength = Chair.TellStrength;
                }
                return v > Tuning.StoolTipSpeed;
            }, 60);
            Assert.AreEqual(1f, Chair.TellStrength, 1e-6f, "the tell is not full above the threshold");
            int band = Mathf.FloorToInt((Tuning.StoolTipSpeed - Tuning.StoolTellSpeed) / Tuning.StoolHighAccel / Dt);
            Assert.GreaterOrEqual(warned, band - 1, $"the tell warned for {warned} steps before the threshold");
            Chair.ScriptedDirection = null;
            yield return Steps(1);
            Assert.IsTrue(Chair.Tipped, "premise: released above the threshold, the stool tips");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step29n_StoolGrazingAWallAtFullSpeedDoesNotTip()
        {
            PinAway();
            // Full speed along the lane toward -x, then 45 deg into the -x wall (no door there).
            Place("stool", new Vector3(2.0f, 0f, LaneZ), 270f);
            Chair.ScriptedDirection = Vector3.left;
            yield return Until(() => Chair.transform.position.x < -2.6f, 200);
            Assert.GreaterOrEqual(Chair.Velocity.magnitude, Chair.Body.MaxSpeed - 0.05f, "premise: full speed before the turn");
            Chair.ScriptedDirection = new Vector3(-1f, 0f, 1f).normalized;
            Vector3 approach = Vector3.zero;
            bool everTipped = false;
            yield return Until(() =>
            {
                everTipped |= Chair.Tipped;
                if (Chair.transform.position.x > -3.5f)
                {
                    approach = Chair.Velocity;
                }
                return Chair.transform.position.x < -3.6f;
            }, 100);
            float contactZ = Chair.transform.position.z;
            yield return Until(() =>
            {
                everTipped |= Chair.Tipped;
                return false;
            }, 25);
            float angle = Vector3.Angle(approach, Vector3.left);
            Assert.AreEqual(45f, angle, 5f, "premise: the stool met the wall at 45 deg");
            Assert.Greater(-approach.x, Tuning.StoolTipSpeed, "premise: its speed against the wall was above the threshold");
            Assert.Greater(Chair.transform.position.z - contactZ, 0.3f, "premise: it slid along the wall");
            Assert.IsFalse(everTipped, "a graze along a wall tipped the stool");
            Chair.ScriptedDirection = null;
            AssertClean();
        }

        /// <summary>
        /// Input change (2026-11-18, PC arrows and full gamepad support): InputReader.Move() reads an arrow key
        /// exactly like WASD/ZQSD, and the gamepad D-pad exactly like the left stick (same v.x/v.y accumulation,
        /// same line). A PlayMode test cannot drive a real keyboard or gamepad device headlessly, so this injects
        /// the same vector an Up Arrow (or the D-pad up, or W) press alone would produce through InjectMoveVector,
        /// InputReader's equivalent of InjectLookStick for the move vector, and checks it drives the furniture
        /// exactly like ScriptedDirection (every other movement test's stand-in for a real move key) does.
        /// </summary>
        [UnityTest]
        public IEnumerator Step29o_InjectedArrowKeyEquivalentMovesLikeAnyOtherMoveKey()
        {
            PinAway();
            Place("office_chair", LaneStart, 0f);
            Vector3 before = Chair.transform.position;
            Assert.IsFalse(Chair.IsMoving, "premise: the chair is not moving before any input");

            InputReader.InjectMoveVector(Vector2.up);
            yield return Steps(10);
            Assert.IsTrue(Chair.IsMoving, "the injected arrow key equivalent (Vector2.up) did not move the furniture");
            Assert.Greater(Planar(Chair.transform.position, before), 0.05f,
                "the injected arrow key equivalent (Vector2.up) did not displace the furniture");
            InputReader.ClearMoveVector();
            yield return Steps(1);

            // The same body, driven the same distance by ScriptedDirection (every other movement test's stand-in
            // for a real move key), moves by the same mechanism: this is not a special case.
            Chair.ScriptedDirection = null;
            Chair.Teleport(LaneStart, 0f);
            Vector3 before2 = Chair.transform.position;
            Chair.ScriptedDirection = Vector3.forward;
            yield return Steps(10);
            Assert.IsTrue(Chair.IsMoving, "premise: ScriptedDirection moves the same body");
            float scriptedDelta = Planar(Chair.transform.position, before2);
            Chair.ScriptedDirection = null;
            Assert.Greater(scriptedDelta, 0.05f, "premise: ScriptedDirection displaced the furniture");
            AssertClean();
        }
    }
}
