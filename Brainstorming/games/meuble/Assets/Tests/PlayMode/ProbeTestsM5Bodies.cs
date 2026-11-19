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
    /// The M5 bodies probe, wave 5A (docs/CONTRACT_M5.md 16.12; CONTRACT_M5_v3.md 15.2 and 15.4), on the real Boot scene,
    /// level 1, with the body set by <see cref="FurnitureController.SetBody"/>, as the M4 bodies probe.
    /// Steps 36g to 36j: the external action a door opening stands on (<see cref="FurnitureController.BeginExternalAction"/>)
    /// and the E key claimed by the game before the body action (<see cref="FurnitureController.ActionKeyClaimed"/>).
    /// Step 36k: the back press of the level select (<see cref="InputReader.BackPressed"/>). Steps 39c and 39d: the floor
    /// height (<see cref="FurnitureController.Floor"/>, <see cref="GhostView.Floor"/>) on a platform of the house's
    /// <see cref="FloorMap"/>; their platform part needs the house FloorMap (a premise names it while it is a stub).
    /// Step 39k (5A.1 m16): on the split level's ramp the furniture visual lies on the slope about its footprint centre,
    /// tips gradually over the foot and the head, and the sample box of the rules stays upright.
    /// Wave 5B (CONTRACT_M5 4, 16.5, 16.8, 18): step 39m, the memory ghost and the seat ghost lie on the ramp slope like the
    /// visual (<see cref="FurnitureController.RampFrame"/>); step 42g, the robot's shove
    /// (<see cref="FurnitureController.BeginPush"/>: 0.25 m in 0.5 s, moving, stopped by a collider, refused when busy);
    /// step 44g, <see cref="MotionProfile"/> against the real controller on the same wishes, within 0.05 m/s, for the chair,
    /// the stool, the office chair and the rocking chair (its rock modelled as GameState starts it).
    /// Every wait counts fixed steps (the GameState.FixedStepped counter) under a real time guard, never rendered frames,
    /// and every scenario asserts its premise so it cannot pass for the wrong reason.
    /// </summary>
    public sealed class ProbeTestsM5Bodies
    {
        private const float Dt = Tuning.FixedStep;
        // Step 39 compares heights with this tolerance once the CharacterController has moved (v3 15.4: it rests a few
        // centimetres above its floor); a teleported, still furniture is exact.
        private const float FloorTolerance = 0.05f;

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;
        private readonly List<Sample> trace = new List<Sample>();
        private readonly List<GameObject> scratch = new List<GameObject>();

        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;
        private Inhabitant Habitant => Game.MainInhabitant;

        private static int DoorSteps => Mathf.RoundToInt(Tuning.DoorOpenTime / Dt);

        // Level 1 (8 x 6 m, centered on the origin): the lane z = -1 is free from wall to wall (the sofa ends at
        // z = -0.5, the table starts at z = -1.45).
        private const float LaneZ = -1f;
        private static readonly Vector3 LaneStart = new Vector3(-3.4f, 0f, LaneZ);
        // A corner spot where the frozen inhabitant looks at the +x wall: the lane and the left side are behind it.
        private static readonly Vector3 AwaySpot = new Vector3(3.0f, 0f, 2.4f);
        private const float AwayYaw = 90f;

        // The platform of the floor steps, on level 1's free left side (x -3.8 to -2.2, z -0.4 to 1.6): clear of the
        // sofa (x from -1.75), the bookshelf (z from 2.6) and the walls, behind the frozen inhabitant.
        private static readonly Vector3 PlatformCenter = new Vector3(-3.0f, 0f, 0.6f);
        private const float PlatformSizeX = 1.6f;
        private const float PlatformSizeZ = 2.0f;
        private const float PlatformHeight = 0.8f;
        // A point of the platform where a body starts its drive (+z, along the platform).
        private static readonly Vector3 OnPlatform = new Vector3(-3.0f, 0f, 0.0f);
        // Free floor beside the platform.
        private static readonly Vector3 OffPlatform = new Vector3(-3.0f, 0f, -2.0f);

        /// <summary>The state of the player furniture after one fixed step.</summary>
        private struct Sample
        {
            public bool Moving;
            public bool Action;
            public FurnitureController.BodyAction Kind;
            public bool Waiting;
            public Vector3 Position;
            public bool Seen;
            public bool Caught;
        }

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            fixedSteps = 0;
            trace.Clear();
            scratch.Clear();
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
            foreach (GameObject go in scratch)
            {
                if (go != null)
                {
                    UnityEngine.Object.DestroyImmediate(go);
                }
            }
            scratch.Clear();
            if (main != null && main.Game != null)
            {
                main.Game.FixedStepped -= Record;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                    main.Game.Furniture.ScriptedCareful = null;
                    main.Game.Furniture.ActionKeyClaimed = null;
                    main.Game.Furniture.Floor = null;
                }
                if (main.Game.Ghost != null)
                {
                    main.Game.Ghost.Floor = null;
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
                Kind = c.Action,
                Waiting = c.WaitingForNeutralInput,
                Position = c.transform.position,
                Seen = Game.Seen,
                Caught = Game.State == PlayState.Caught,
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
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" / ", logged));
        }

        /// <summary>How many consecutive recorded steps from <paramref name="start"/> ran an action.</summary>
        private int ActionRun(int start)
        {
            int run = 0;
            while (start + run < trace.Count && trace[start + run].Action)
            {
                run++;
            }
            return run;
        }

        /// <summary>
        /// A player furniture of its own, stepped by the test itself: GameState pins the level's player from its sit
        /// flags and releases a carried one with no carrier on every step, so the pin and the carry are checked on a
        /// controller nobody else drives.
        /// </summary>
        private FurnitureController Standalone(string kind, Vector3 at, float yaw)
        {
            var go = new GameObject("Standalone " + kind) { layer = Layers.Player };
            go.transform.SetParent(Game.Level.Root.transform, false);
            scratch.Add(go);
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

        // ----- 36g to 36j: the external action and the E key -----

        [UnityTest]
        public IEnumerator Step36g_ExternalActionIsMovingForExactlyThirtySteps()
        {
            Assert.AreEqual(30, DoorSteps, "premise: a door opening is 30 steps (DoorOpenTime 0.6 s at 50 Hz)");
            PinAway();
            Place("chair", LaneStart, 90f);
            yield return Steps(3);
            Assert.IsFalse(Chair.IsMoving || Chair.ActionActive, "premise: the chair is still and in no action");
            Vector3 at = Chair.transform.position;
            int start = trace.Count;
            Assert.IsTrue(Chair.BeginExternalAction(Tuning.DoorOpenTime), "a still, upright, free chair refused the external action");
            Assert.IsTrue(Chair.ActionActive, "the external action is not active at once");
            Assert.AreEqual(FurnitureController.BodyAction.External, Chair.Action);
            Assert.IsFalse(Chair.BeginExternalAction(Tuning.DoorOpenTime), "a second external action started over the first");
            yield return Steps(DoorSteps + 15);

            int run = ActionRun(start);
            Assert.AreEqual(DoorSteps, run, "the external action did not last exactly DoorOpenTime");
            Assert.Greater(trace.Count - start, run + 5, "premise: steps after the action were recorded");
            for (int i = start; i < trace.Count; i++)
            {
                bool inAction = i < start + run;
                Assert.AreEqual(inAction, trace[i].Moving, $"step {i - start}: moving is {trace[i].Moving} with the action {(inAction ? "on" : "over")}");
                Assert.AreEqual(inAction ? FurnitureController.BodyAction.External : FurnitureController.BodyAction.None, trace[i].Kind,
                    $"step {i - start}: the action");
                Assert.Less(Planar(trace[i].Position, at), 1e-4f, $"step {i - start}: the chair travelled during or after its external action");
                Assert.IsFalse(trace[i].Waiting, $"step {i - start}: the external action armed a neutral input wait");
            }
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: unseen, the action was not caught");

            // Seen during it: caught after the grace, for being seen moving (the action is moving for the rules too).
            var watcher = new Vector3(0.5f, 0f, LaneZ);
            Habitant.Pin(watcher, YawToward(watcher, Chair.transform.position));
            yield return Steps(15);
            Assert.IsTrue(Game.Seen, "premise: the watcher sees the chair");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: a still chair in sight is not caught");
            start = trace.Count;
            Assert.IsTrue(Chair.BeginExternalAction(Tuning.DoorOpenTime), "premise: the second external action started");
            yield return Until(() => Game.State != PlayState.Playing, DoorSteps + 5);
            Assert.AreEqual(PlayState.Caught, Game.State, "an external action in plain view was not caught");
            Assert.AreEqual(LoseReason.SeenMoving, Game.LoseReason, "caught for another reason");
            int seenMoving = 0;
            for (int i = start; i < trace.Count; i++)
            {
                Assert.IsTrue(trace[i].Action, "premise: a step outside the action before the catch");
                if (trace[i].Seen && trace[i].Moving)
                {
                    seenMoving++;
                }
                if (trace[i].Caught)
                {
                    break;
                }
            }
            Assert.AreEqual(Mathf.RoundToInt(Tuning.CaughtGrace / Dt), seenMoving, "caught after a number of seen action steps other than the grace");
            AssertClean();
        }

        /// <summary>Asserts a refusal that changes nothing: the action in progress (or none) stays as it was.</summary>
        private static void AssertRefused(FurnitureController f, string why)
        {
            FurnitureController.BodyAction before = f.Action;
            bool active = f.ActionActive;
            Assert.IsFalse(f.BeginExternalAction(Tuning.DoorOpenTime), "the external action started while " + why);
            Assert.AreEqual(before, f.Action, "a refused external action changed the action while " + why);
            Assert.AreEqual(active, f.ActionActive, "a refused external action changed ActionActive while " + why);
        }

        [UnityTest]
        public IEnumerator Step36h_ExternalActionIsRefusedUnlessStillUprightAndFree()
        {
            PinAway();

            // Moving: refused, and the drive goes on.
            Place("chair", LaneStart, 90f);
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(10);
            Assert.IsTrue(Chair.IsMoving, "premise: the chair moves");
            AssertRefused(Chair, "moving");
            float x = Chair.transform.position.x;
            yield return Steps(1);
            Assert.IsTrue(Chair.IsMoving && Chair.transform.position.x > x + 1e-3f, "a refused external action stopped the chair");
            Chair.ScriptedDirection = null;
            yield return Steps(2);
            Assert.IsFalse(Chair.IsMoving, "premise: the chair stopped");
            // Control: still, the same chair is accepted, so the refusal above was for moving.
            Assert.IsTrue(Chair.BeginExternalAction(Tuning.DoorOpenTime), "control: a still chair refused the external action");
            yield return Until(() => !Chair.ActionActive, DoorSteps + 5);
            Assert.IsFalse(Chair.ActionActive, "premise: the control action ended");

            // Gliding (the office chair after a release): refused, and the glide goes on.
            Place("office_chair", LaneStart, 90f);
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.Velocity.magnitude >= 2f, 75);
            Chair.ScriptedDirection = null;
            yield return Steps(3);
            Assert.IsTrue(Chair.Gliding, "premise: the office chair glides");
            AssertRefused(Chair, "gliding");
            yield return Steps(1);
            Assert.IsTrue(Chair.Gliding && Chair.IsMoving, "a refused external action stopped the glide");
            yield return Until(() => !Chair.IsMoving, 30);
            Assert.IsFalse(Chair.Gliding, "premise: the glide ended");

            // In a lamp switch: refused, and the switch keeps its LampToggleTime.
            Place("floor_lamp", LaneStart, 90f);
            yield return Steps(2);
            int toggles = Chair.ToggleCount;
            int start = trace.Count;
            InputReader.InjectAction();
            yield return Steps(1);
            Assert.AreEqual(FurnitureController.BodyAction.Toggle, Chair.Action, "premise: the lamp switches");
            AssertRefused(Chair, "in a lamp switch");
            yield return Until(() => !Chair.ActionActive, 20);
            Assert.AreEqual(Mathf.RoundToInt(Tuning.LampToggleTime / Dt), ActionRun(start), "a refused external action changed the switch's length");
            Assert.AreEqual(toggles + 1, Chair.ToggleCount);

            // The stool: falling (an action, tipped), then lying on its side (tipped, no action).
            Place("stool", LaneStart, 90f);
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.Velocity.magnitude > Tuning.StoolTipSpeed + 0.2f, 60);
            Chair.ScriptedDirection = null;
            yield return Steps(1);
            Assert.AreEqual(FurnitureController.BodyAction.Fall, Chair.Action, "premise: the stool falls");
            AssertRefused(Chair, "falling");
            yield return Until(() => Chair.LyingDown, 30);
            yield return Steps(2);
            Assert.IsTrue(Chair.LyingDown && !Chair.IsMoving, "premise: the stool lies still on its side");
            AssertRefused(Chair, "lying on its side");
            yield return Steps(5);
            Assert.IsTrue(Chair.LyingDown && !Chair.IsMoving, "a refused external action got the stool up");

            // Pinned and carried, on a controller of its own.
            var home = new Vector3(1.0f, 0f, 0.9f);
            FurnitureController f = Standalone("chair", home, 90f);
            StepManually(f, 2);
            Assert.IsFalse(f.IsMoving || f.ActionActive, "premise: the standalone chair is still");
            f.Pin(true);
            AssertRefused(f, "pinned");
            f.Pin(false);
            StepManually(f, 1);
            f.FollowCarrier(home + new Vector3(0f, 0.6f, 0.4f), 90f);
            Assert.IsTrue(f.Carried, "premise: carried");
            AssertRefused(f, "carried");
            f.Release(new FurniturePose(home, 90f));
            Assert.IsTrue(f.BeginExternalAction(Tuning.DoorOpenTime), "control: put down, the standalone chair refused the external action");
            // A pin or a carry ends it at once.
            f.Pin(true);
            Assert.IsFalse(f.ActionActive, "a pin left the external action running");
            f.Pin(false);
            StepManually(f, 1);
            Assert.IsTrue(f.BeginExternalAction(Tuning.DoorOpenTime), "premise: a second external action started");
            f.FollowCarrier(home + new Vector3(0f, 0.6f, 0.4f), 90f);
            Assert.IsFalse(f.ActionActive, "a carry left the external action running");
            f.Release(new FurniturePose(home, 90f));
            // A duration that is not positive starts nothing.
            Assert.IsFalse(f.BeginExternalAction(0f), "a zero duration started an action");
            Assert.IsFalse(f.BeginExternalAction(-1f), "a negative duration started an action");
            Assert.IsFalse(f.BeginExternalAction(float.NaN), "a NaN duration started an action");
            Assert.IsFalse(f.ActionActive);
            yield return Steps(1);
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step36i_HeldKeyIsIgnoredDuringItAndNeedsNoNeutralStepAfter()
        {
            PinAway();
            // The lamp, so an E press during the action would show as a switch.
            Place("floor_lamp", LaneStart, 90f);
            yield return Steps(2);
            Assert.IsTrue(Chair.Lamp != null && Chair.Lamp.On, "premise: the lamp is on");
            int toggles = Chair.ToggleCount;
            Vector3 at = Chair.transform.position;
            int start = trace.Count;
            Assert.IsTrue(Chair.BeginExternalAction(Tuning.DoorOpenTime), "premise: the external action started");
            // A move key held through the whole action, and an E press during it.
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(5);
            InputReader.InjectAction();
            yield return Until(() => !Chair.ActionActive, DoorSteps + 5);
            yield return Steps(3);
            Chair.ScriptedDirection = null;

            int run = ActionRun(start);
            Assert.AreEqual(DoorSteps, run, "the external action did not last exactly DoorOpenTime");
            for (int i = start; i < start + run; i++)
            {
                Assert.IsTrue(trace[i].Moving, $"action step {i - start}: not moving");
                Assert.Less(Planar(trace[i].Position, at), 1e-4f, $"action step {i - start}: the held key moved the lamp");
            }
            Assert.Greater(trace.Count, start + run, "premise: the step after the action was recorded");
            Sample after = trace[start + run];
            Assert.IsFalse(after.Waiting, "the external action armed a neutral input wait");
            Assert.IsTrue(after.Moving && after.Position.x > at.x + 1e-4f,
                "a key held through the external action did not drive on the first step after it (no neutral step is needed)");
            Assert.AreEqual(toggles, Chair.ToggleCount, "an E press made during the external action switched the lamp");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step36j_ClaimedActionKeyGoesToTheDoorNotTheLamp()
        {
            PinAway();
            Place("floor_lamp", LaneStart, 90f);
            yield return Steps(2);
            LampLight lamp = Chair.Lamp;
            Assert.IsTrue(lamp != null && lamp.On, "premise: the lamp is on");
            int toggles = Chair.ToggleCount;
            int asked = 0;

            // Not claimed: the press is the body's, and the lamp switches (M4).
            Chair.ActionKeyClaimed = () =>
            {
                asked++;
                return false;
            };
            yield return Steps(3);
            Assert.AreEqual(0, asked, "the hook was asked with no press");
            InputReader.InjectAction();
            yield return Steps(1);
            Assert.AreEqual(1, asked, "the hook was not asked exactly once for the press");
            Assert.AreEqual(toggles + 1, Chair.ToggleCount, "an unclaimed press did not switch the lamp");
            yield return Until(() => !Chair.ActionActive, 20);
            yield return Steps(2);
            Assert.AreEqual(1, asked, "the hook was asked again with no new press");

            // Claimed, with no action begun: nothing for the body, and the press is consumed (it never fires later).
            toggles = Chair.ToggleCount;
            bool lit = lamp.On;
            Chair.ActionKeyClaimed = () =>
            {
                asked++;
                return true;
            };
            InputReader.InjectAction();
            yield return Steps(1);
            Assert.AreEqual(2, asked, "the hook was not asked for the second press");
            Assert.AreEqual(toggles, Chair.ToggleCount, "a claimed press switched the lamp");
            Assert.IsFalse(Chair.ActionActive || Chair.IsMoving, "a claimed press with no action moved the lamp");
            Chair.ActionKeyClaimed = null;
            yield return Steps(5);
            Assert.AreEqual(toggles, Chair.ToggleCount, "the claimed press fired later");
            Assert.AreEqual(lit, lamp.On, "the lamp changed");

            // Claimed by a door: the hook begins the opening, and the step of the press is its first step.
            bool began = false;
            Chair.ActionKeyClaimed = () =>
            {
                asked++;
                began = Chair.BeginExternalAction(Tuning.DoorOpenTime);
                return true;
            };
            int start = trace.Count;
            InputReader.InjectAction();
            yield return Steps(1);
            Assert.AreEqual(3, asked, "the hook was not asked for the third press");
            Assert.IsTrue(began, "the opening begun from the hook was refused");
            Assert.AreEqual(FurnitureController.BodyAction.External, Chair.Action, "the hook's action is not running");
            Assert.IsTrue(trace[start].Action && trace[start].Moving, "the step of the press is not the first step of the opening");
            Assert.AreEqual(toggles, Chair.ToggleCount, "the door's press also switched the lamp");
            // A press made during the opening reaches neither the hook nor the lamp.
            InputReader.InjectAction();
            yield return Until(() => !Chair.ActionActive, DoorSteps + 5);
            yield return Steps(3);
            Assert.AreEqual(DoorSteps, ActionRun(start), "the opening begun from the hook did not last exactly DoorOpenTime");
            Assert.AreEqual(3, asked, "a press made during the opening reached the hook");
            Assert.AreEqual(toggles, Chair.ToggleCount, "a press made during the opening switched the lamp");
            Assert.AreEqual(lit, lamp.On, "the lamp changed");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step36k_BackPressCountsOnceAndIsNotPause()
        {
            yield return Steps(1);
            InputReader.ResetInjections();
            Assert.IsFalse(InputReader.BackPressed(), "premise: no back press pending");
            InputReader.InjectBack();
            Assert.IsTrue(InputReader.BackPressed(), "an injected back press was not read");
            Assert.IsFalse(InputReader.BackPressed(), "one back press counted twice");
            // Two presses are two, even in one frame.
            InputReader.InjectBack();
            Assert.IsTrue(InputReader.BackPressed(), "the first of two presses was lost");
            InputReader.InjectBack();
            Assert.IsTrue(InputReader.BackPressed(), "the second of two presses was lost");
            Assert.IsFalse(InputReader.BackPressed());
            // ResetInjections drops a pending press.
            InputReader.InjectBack();
            InputReader.ResetInjections();
            Assert.IsFalse(InputReader.BackPressed(), "ResetInjections left a back press");
            // Back and pause are two commands: the Menu decides what Escape means.
            InputReader.InjectBack();
            Assert.IsFalse(InputReader.PausePressed(), "a back press was read as a pause press");
            Assert.IsTrue(InputReader.BackPressed(), "reading the pause press consumed the back press");
            InputReader.InjectPausePress();
            Assert.IsFalse(InputReader.BackPressed(), "a pause press was read as a back press");
            Assert.IsTrue(InputReader.PausePressed(), "reading the back press consumed the pause press");
            InputReader.ResetInjections();
            AssertClean();
        }

        // ----- 39c and 39d: the floor height -----

        /// <summary>Level 1 parsed afresh (the running level's data and its cached floor stay untouched), with one platform.</summary>
        private static FloorMap PlatformMap()
        {
            var asset = Resources.Load<TextAsset>(LevelLoader.Folder + "/level1");
            Assert.IsNotNull(asset, "premise: level1.json is in Resources");
            LevelDef def = LevelJson.Parse(asset.text);
            def.Platforms.Add(new PlatformDef
            {
                Name = "TestPlatform",
                X = PlatformCenter.x,
                Z = PlatformCenter.z,
                SizeX = PlatformSizeX,
                SizeZ = PlatformSizeZ,
                Height = PlatformHeight,
            });
            return def.Floor;
        }

        /// <summary>
        /// The premise of the platform parts: the house's FloorMap gives the platform height on it and 0 beside it. Until
        /// the house agent fills Core/FloorMap.cs, the integrator's stub returns 0 everywhere and this premise fails.
        /// </summary>
        private static FloorMap RequirePlatformMap()
        {
            FloorMap map = PlatformMap();
            Assert.AreEqual(PlatformHeight, map.HeightAt(PlatformCenter.x, PlatformCenter.z), 1e-4f,
                "premise: FloorMap.HeightAt does not give the platform height (Core/FloorMap.cs is still the flat stub, house)");
            Assert.AreEqual(PlatformHeight, map.HeightAt(OnPlatform.x, OnPlatform.z), 1e-4f, "premise: the drive start is not on the platform");
            Assert.AreEqual(0f, map.HeightAt(OffPlatform.x, OffPlatform.z), 1e-4f, "premise: FloorMap.HeightAt is not 0 beside the platform");
            return map;
        }

        /// <summary>A solid platform (a Floor layer box) matching <see cref="PlatformMap"/>, so a body can drive on it.</summary>
        private GameObject SolidPlatform()
        {
            var go = new GameObject("TestPlatform") { layer = Layers.Floor };
            go.transform.SetParent(Game.Level.Root.transform, false);
            go.transform.position = new Vector3(PlatformCenter.x, PlatformHeight * 0.5f, PlatformCenter.z);
            var box = go.AddComponent<BoxCollider>();
            box.size = new Vector3(PlatformSizeX, PlatformHeight, PlatformSizeZ);
            scratch.Add(go);
            Physics.SyncTransforms();
            return go;
        }

        private static void AssertSamplesAt(Vector3[] samples, float floorY, Vector3 size, float tolerance, string what)
        {
            Assert.AreEqual(floorY + size.y * 0.5f, samples[0].y, tolerance, what + ": center sample height");
            for (int i = 1; i < samples.Length; i++)
            {
                Assert.AreEqual(floorY + size.y - Tuning.SampleInset, samples[i].y, tolerance, what + ": top sample height");
            }
        }

        [UnityTest]
        public IEnumerator Step39c_TeleportReleaseAndSamplesStandOnTheFloor()
        {
            PinAway();
            yield return Steps(1);
            var samples = new Vector3[Tuning.SampleCount];

            // A flat floor (levels 1 to 7): the furniture stands at 0 whatever height it is given; a null floor reads flat.
            Place("chair", LaneStart, 90f);
            Assert.AreEqual(0f, Chair.Floor.HeightAt(LaneStart.x, LaneStart.z), 1e-6f, "premise: level 1 is flat");
            Chair.Teleport(LaneStart + Vector3.up * 0.5f, 90f);
            Assert.AreEqual(0f, Chair.transform.position.y, 1e-5f, "Teleport kept the given height instead of the floor's");
            Chair.Release(new FurniturePose(LaneStart + Vector3.up * 0.4f, 90f));
            Assert.AreEqual(0f, Chair.transform.position.y, 1e-5f, "Release kept the pose's height instead of the floor's");
            Chair.Floor = null;
            Assert.IsNotNull(Chair.Floor, "a null floor is not read as flat");
            Chair.Teleport(LaneStart + Vector3.up * 0.3f, 90f);
            Assert.AreEqual(0f, Chair.transform.position.y, 1e-5f, "a null floor is not flat");
            yield return Steps(2);

            // A platform (the house's FloorMap): Teleport and Release put the furniture on it, and the samples follow.
            FloorMap map = RequirePlatformMap();
            Chair.Floor = map;
            Vector3 size = Chair.Size;
            Chair.Teleport(OnPlatform, 0f);
            Assert.AreEqual(PlatformHeight, Chair.transform.position.y, 1e-5f, "Teleport did not put the chair on the platform");
            Chair.GetSamplePoints(samples);
            AssertSamplesAt(samples, PlatformHeight, size, 1e-4f, "teleported on the platform");
            Assert.AreEqual(PlatformHeight + size.y * 0.5f, Chair.Center.y, 1e-4f, "the center is not on the platform");
            Chair.Teleport(OffPlatform, 0f);
            Assert.AreEqual(0f, Chair.transform.position.y, 1e-5f, "Teleport beside the platform did not put the chair on the floor");
            Chair.GetSamplePoints(samples);
            AssertSamplesAt(samples, 0f, size, 1e-4f, "teleported beside the platform");
            Chair.Release(new FurniturePose(OnPlatform, 0f));
            Assert.AreEqual(PlatformHeight, Chair.transform.position.y, 1e-5f, "Release did not put the chair down on the platform");
            Chair.Release(new FurniturePose(OffPlatform, 0f));
            Assert.AreEqual(0f, Chair.transform.position.y, 1e-5f, "Release beside the platform did not put the chair on the floor");

            // Driving on a solid platform: the CharacterController stays on its top, and the samples follow it.
            SolidPlatform();
            Chair.Teleport(OnPlatform, 0f);
            yield return Steps(2);
            Assert.IsFalse(Chair.WaitingForNeutralInput, "premise: the input is armed");
            float startZ = Chair.transform.position.z;
            float worstBase = 0f;
            float worstCenter = 0f;
            Chair.ScriptedDirection = Vector3.forward;
            yield return Until(() =>
            {
                Chair.GetSamplePoints(samples);
                float y = Chair.transform.position.y;
                worstBase = Mathf.Max(worstBase, Mathf.Abs(y - PlatformHeight));
                worstCenter = Mathf.Max(worstCenter, Mathf.Abs(samples[0].y - (PlatformHeight + size.y * 0.5f)));
                return false;
            }, 15);
            Chair.ScriptedDirection = null;
            yield return Steps(2);
            Assert.Greater(Chair.transform.position.z - startZ, 0.15f, "premise: the chair drove on the platform");
            Assert.Less(Chair.transform.position.z, PlatformCenter.z + PlatformSizeZ * 0.5f - 0.3f, "premise: the chair stayed on the platform");
            Assert.Less(worstBase, FloorTolerance, $"the chair left the platform height by {worstBase:0.000} m while driving on it");
            Assert.Less(worstCenter, FloorTolerance, $"the center sample left the platform height by {worstCenter:0.000} m while driving on it");
            Chair.GetSamplePoints(samples);
            AssertSamplesAt(samples, PlatformHeight, size, FloorTolerance, "after a drive on the platform");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step39d_GhostSeatStopRingAndDecoyRingsStandOnTheFloor()
        {
            PinAway();
            yield return Steps(1);
            GhostView ghost = Game.Ghost;
            Assert.IsNotNull(ghost, "premise: the ghost view exists");
            Transform parent = ghost.transform.parent;
            Transform seat = parent.Find("SeatGhost");
            Transform stop = parent.Find("StopRing");
            Transform rings = parent.Find("DecoyRings");
            Assert.IsTrue(seat != null && stop != null && rings != null, "premise: the seat ghost, the stop ring and the decoy rings exist");
            Vector3 size = Chair.Size;

            // A flat floor: everything stands at 0, whatever height it is given. Read at once: GameState redraws the
            // memory ghost and the seat ghost on every step.
            ghost.ShowStopRing(OnPlatform + Vector3.up * 0.5f);
            Assert.AreEqual(0f, stop.position.y, 1e-5f, "the stop ring kept the given height on a flat floor");
            ghost.ShowStopRing(null);
            ghost.ShowSeat(new FurniturePose(OnPlatform + Vector3.up * 0.5f, 0f), size);
            Assert.AreEqual(0f, seat.position.y, 1e-5f, "the seat ghost kept the given height on a flat floor");
            ghost.ShowSeat(null);
            ghost.Show(new FurniturePose(OnPlatform + Vector3.up * 0.5f, 0f), size);
            Assert.AreEqual(0f, ghost.transform.position.y, 1e-5f, "the memory ghost kept the given height on a flat floor");
            ghost.Hide();

            // A platform, read through the player furniture's floor (GhostView.Floor null).
            FloorMap map = RequirePlatformMap();
            Chair.Floor = map;
            ghost.Floor = null;
            ghost.ShowStopRing(PlatformCenter);
            Assert.IsTrue(ghost.StopRingVisible, "premise: the stop ring shows");
            Assert.AreEqual(PlatformHeight, ghost.StopRingPosition.y, 1e-5f, "the stop ring position is not on the platform");
            Assert.AreEqual(PlatformHeight, stop.position.y, 1e-5f, "the stop ring is not drawn on the platform");
            Assert.Less(Planar(stop.position, PlatformCenter), 1e-5f, "the stop ring left its planar point");
            ghost.ShowStopRing(OffPlatform);
            Assert.AreEqual(0f, stop.position.y, 1e-5f, "the stop ring beside the platform is not on the floor");
            ghost.ShowStopRing(null);

            ghost.ShowSeat(new FurniturePose(PlatformCenter, 30f), size);
            Assert.IsTrue(ghost.SeatVisible, "premise: the seat ghost shows");
            Assert.AreEqual(PlatformHeight, seat.position.y, 1e-5f, "the seat ghost is not on the platform");
            ghost.ShowSeat(new FurniturePose(OffPlatform, 30f), size);
            Assert.AreEqual(0f, seat.position.y, 1e-5f, "the seat ghost beside the platform is not on the floor");
            ghost.ShowSeat(null);

            ghost.Show(new FurniturePose(PlatformCenter, 0f), size);
            Assert.AreEqual(PlatformHeight, ghost.transform.position.y, 1e-5f, "the memory ghost is not on the platform");
            ghost.Show(new FurniturePose(OffPlatform, 0f), size);
            Assert.AreEqual(0f, ghost.transform.position.y, 1e-5f, "the memory ghost beside the platform is not on the floor");
            ghost.Hide();

            ghost.SetDecoyRings(new List<Vector3> { PlatformCenter, OffPlatform });
            Assert.AreEqual(2, ghost.RingCount, "premise: two decoy rings");
            Mesh mesh = rings.GetComponent<MeshFilter>().sharedMesh;
            float onTop = float.NegativeInfinity;
            float offTop = float.NegativeInfinity;
            int onCount = 0;
            int offCount = 0;
            foreach (Vector3 v in mesh.vertices)
            {
                Vector3 w = rings.TransformPoint(v);
                if (Planar(w, PlatformCenter) < 1f)
                {
                    onTop = Mathf.Max(onTop, w.y);
                    onCount++;
                }
                else if (Planar(w, OffPlatform) < 1f)
                {
                    offTop = Mathf.Max(offTop, w.y);
                    offCount++;
                }
            }
            Assert.IsTrue(onCount > 0 && onCount == offCount, $"premise: one ring around each center ({onCount} and {offCount} vertices)");
            Assert.AreEqual(PlatformHeight, onTop - offTop, 1e-4f, "the decoy ring on the platform is not raised by the platform height");
            ghost.SetDecoyRings(new List<Vector3>());

            // GhostView.Floor, when set, wins over the player furniture's.
            ghost.Floor = FloorMap.Flat;
            ghost.ShowStopRing(PlatformCenter);
            Assert.AreEqual(0f, stop.position.y, 1e-5f, "GhostView.Floor did not override the player furniture's floor");
            ghost.ShowStopRing(null);
            ghost.Floor = null;

            // The office chair gliding on a solid platform: its predicted stop ring stands on the platform.
            SolidPlatform();
            Place("office_chair", OnPlatform, 0f);
            Assert.AreEqual(PlatformHeight, Chair.transform.position.y, 1e-5f, "premise: the office chair stands on the platform");
            yield return Steps(2);
            Chair.ScriptedDirection = Vector3.forward;
            yield return Steps(10);
            Assert.IsTrue(Chair.IsMoving && Chair.PredictedStop.HasValue, "premise: the moving office chair predicts its stop");
            Assert.IsTrue(ghost.StopRingVisible, "premise: the stop ring shows");
            Vector3 predicted = Chair.PredictedStop.Value;
            Assert.AreEqual(PlatformHeight, map.HeightAt(predicted.x, predicted.z), 1e-4f, "premise: the predicted stop is on the platform");
            Assert.AreEqual(PlatformHeight, stop.position.y, 1e-5f, "the stop ring of a glide on the platform is not on it");
            Assert.Less(Planar(stop.position, predicted), 1e-3f, "the stop ring is not at the predicted stop");
            Chair.ScriptedDirection = null;
            yield return Until(() => !Chair.IsMoving, 40);
            yield return Steps(2);
            Assert.AreEqual(PlatformHeight, Chair.transform.position.y, FloorTolerance, "premise: the office chair glided on the platform top");
            Assert.IsFalse(ghost.StopRingVisible, "the stop ring stayed after the glide");
            AssertClean();
        }

        // ----- 39k: the visual follows the ramp slope (5A.1 m16) -----

        // test_m5_house_split: its one ramp rises +z from its foot z = -1.9 to its head z = 0.5, on x in [-0.85, 0.35], onto
        // the 0.8 m platform "Mezzanine" (x in [-4, 1], z in [0.5, 3]): a slope of atan(0.8 / 2.4), 18.4 degrees. Its
        // inhabitant stands on the platform at (-3.25, 2.25), facing the west wall, so the ramp is behind it.
        private const string SplitLevel = "test_m5_house_split";
        private const float RampX = -0.25f;
        private const float RampFootZ = -1.9f;
        private const float RampHeadZ = 0.5f;
        private const float RampMidZ = -0.7f;
        // A teleported, still visual is laid out exactly on its floor: this covers float error only.
        private const float VisualTolerance = 0.005f;
        // The angles of a teleported, still visual, in degrees.
        private const float AngleTolerance = 0.5f;

        /// <summary>A few rendered frames, so the furniture's LateUpdate has laid its visual out since the last fixed step.</summary>
        private static IEnumerator Rendered()
        {
            for (int i = 0; i < 3; i++)
            {
                yield return null;
            }
        }

        /// <summary>A point of the visual's base plane (local, y 0) in the world, scale aside.</summary>
        private Vector3 VisualBase(Vector3 local)
        {
            Transform v = Chair.Visual;
            return v.position + v.rotation * local;
        }

        /// <summary>How far a point of the visual's base plane stands above the level's floor right under it.</summary>
        private float AboveFloor(FloorMap floor, Vector3 local)
        {
            Vector3 p = VisualBase(local);
            return p.y - floor.HeightAt(p.x, p.z);
        }

        /// <summary>The visual's pitch in degrees: its forward axis above the horizontal (nose up is positive).</summary>
        private float VisualPitch => Mathf.Asin(Mathf.Clamp(Chair.Visual.forward.y, -1f, 1f)) * Mathf.Rad2Deg;

        /// <summary>The visual's roll in degrees: its right axis above the horizontal (right side up is positive).</summary>
        private float VisualRoll => Mathf.Asin(Mathf.Clamp(Chair.Visual.right.y, -1f, 1f)) * Mathf.Rad2Deg;

        /// <summary>The four bottom corners and the front and back edge middles of the footprint, local to the visual.</summary>
        private static Vector3[] FootprintPoints(Vector3 size)
        {
            float hx = size.x * 0.5f;
            float hz = size.z * 0.5f;
            return new[]
            {
                new Vector3(hx, 0f, hz), new Vector3(-hx, 0f, hz), new Vector3(hx, 0f, -hz), new Vector3(-hx, 0f, -hz),
                new Vector3(0f, 0f, hz), new Vector3(0f, 0f, -hz),
            };
        }

        /// <summary>The top samples of the rules stay level (the sample box is upright) and above the transform.</summary>
        private void AssertSampleBoxUpright(Vector3[] samples, string what)
        {
            Chair.GetSamplePoints(samples);
            float baseY = Chair.transform.position.y;
            Assert.AreEqual(baseY + Chair.Size.y * 0.5f, samples[0].y, 1e-4f, what + ": the centre sample left the upright box");
            for (int i = 1; i < samples.Length; i++)
            {
                Assert.AreEqual(baseY + Chair.Size.y - Tuning.SampleInset, samples[i].y, 1e-4f, what + ": a top sample left the upright box");
            }
        }

        [UnityTest]
        public IEnumerator Step39k_FurnitureVisualFollowsTheRampSlope()
        {
            Game.LoadLevel(SplitLevel);
            Assert.AreEqual(SplitLevel, Game.Def.Id, "premise: the split level loaded");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: playing");
            yield return Steps(2);
            StationDef station = Game.Def.Inhabitants[0].Stations[0];
            Habitant.Pin(station.Position, station.Facing);
            yield return Steps(1);
            FloorMap floor = Chair.Floor;
            Assert.AreSame(Game.Def.Floor, floor, "premise: the furniture reads the level's floor");
            Assert.AreEqual(1, Game.Def.Ramps.Count, "premise: the split level has one ramp");
            RampDef ramp = Game.Def.Ramps[0];
            float slope = floor.SlopeOf(ramp);
            Assert.AreEqual(Mathf.Atan2(0.8f, 2.4f) * Mathf.Rad2Deg, slope, 0.01f, "premise: the ramp rises 0.8 m over 2.4 m");
            float rise = Mathf.Tan(slope * Mathf.Deg2Rad);
            Vector3 uphill = YawMath.Forward(ramp.Yaw);
            Assert.Greater(uphill.z, 0.99f, "premise: the ramp rises toward +z");
            Assert.AreEqual(0.4f, floor.HeightAt(RampX, RampMidZ), 1e-4f, "premise: the ramp middle is half way up");
            Vector3 rampNormal = (Vector3.up - uphill * rise).normalized;
            var samples = new Vector3[Tuning.SampleCount];

            // Off the ramp the visual stays upright: on the floor, on the platform, on the floor beside the ramp, and on the
            // floor against the platform side (its footprint reaches under the platform edge: only a ramp tilts).
            var flatSpots = new[]
            {
                new Vector3(2.5f, 0f, -2.0f), new Vector3(-2.5f, 0f, 1.75f), new Vector3(1.0f, 0f, -1.0f), new Vector3(-2.5f, 0f, 0.35f),
            };
            foreach (Vector3 spot in flatSpots)
            {
                Place("chair", spot, 30f);
                yield return Steps(1);
                yield return Rendered();
                Assert.Less(Vector3.Angle(Chair.Visual.up, Vector3.up), 0.01f, $"the visual at {spot} off the ramp is not upright");
            }

            // On the ramp, whatever the yaw: the visual lies on the slope (its up is the ramp's normal, every footprint
            // point on the floor), its heading stays the yaw, and the sample box of the rules stays upright.
            foreach (float yaw in new[] { 0f, 180f, 90f, -90f, 45f, 200f })
            {
                Place("chair", new Vector3(RampX, 0f, RampMidZ), yaw);
                yield return Steps(1);
                yield return Rendered();
                string what = $"on the ramp at yaw {yaw}";
                Assert.AreEqual(0.4f, Chair.transform.position.y, 1e-4f, "premise: teleported " + what);
                Assert.Less(Vector3.Angle(Chair.Visual.up, rampNormal), AngleTolerance,
                    $"{what}: the visual up {Chair.Visual.up} is not the ramp normal {rampNormal} (upright: {Vector3.Angle(Chair.Visual.up, Vector3.up):0.0} degrees off it)");
                foreach (Vector3 local in FootprintPoints(Chair.Size))
                {
                    float above = AboveFloor(floor, local);
                    Assert.AreEqual(0f, above, VisualTolerance, $"{what}: the footprint point {local} is {above:0.000} m off the slope (negative sinks)");
                }
                float heading = YawMath.YawOf(YawMath.Planar(Chair.Visual.forward));
                Assert.Less(Mathf.Abs(Mathf.DeltaAngle(yaw, heading)), AngleTolerance, $"{what}: the visual turned to {heading}");
                AssertSampleBoxUpright(samples, what);
                Assert.AreEqual(0.4f + Chair.Size.y * 0.5f, Chair.Center.y, 1e-4f, what + ": the centre of the rules moved");
            }
            Place("chair", new Vector3(RampX, 0f, RampMidZ), 0f);
            yield return Steps(1);
            yield return Rendered();
            Assert.AreEqual(slope, VisualPitch, AngleTolerance, "facing uphill, the nose is not up by the slope");
            Assert.AreEqual(0f, VisualRoll, AngleTolerance, "facing uphill, the visual rolls");
            Place("chair", new Vector3(RampX, 0f, RampMidZ), 180f);
            yield return Steps(1);
            yield return Rendered();
            Assert.AreEqual(-slope, VisualPitch, AngleTolerance, "facing downhill, the nose is not down by the slope");
            Place("chair", new Vector3(RampX, 0f, RampMidZ), 90f);
            yield return Steps(1);
            yield return Rendered();
            Assert.AreEqual(0f, VisualPitch, AngleTolerance, "across the slope, the visual pitches");
            Assert.AreEqual(-slope, VisualRoll, AngleTolerance, "facing +x, the right side (downhill) is not down by the slope");

            // Over the foot and the head the visual tips gradually about its footprint: on the foot line its front edge is
            // on the slope and its back on the floor (about half the slope, both edges on the floor); on the head line it
            // eases over the crest (about half the slope) and never sinks.
            float halfDepth = Chair.Size.z * 0.5f;
            var front = new Vector3(0f, 0f, halfDepth);
            var back = new Vector3(0f, 0f, -halfDepth);
            Place("chair", new Vector3(RampX, 0f, RampFootZ), 0f);
            yield return Steps(1);
            yield return Rendered();
            Assert.AreEqual(0f, Chair.transform.position.y, 1e-4f, "premise: the foot line is on the floor");
            Assert.That(VisualPitch, Is.InRange(0.3f * slope, 0.7f * slope), $"on the foot line the visual pitches {VisualPitch:0.0} instead of about half the slope");
            Assert.AreEqual(0f, AboveFloor(floor, front), 0.01f, "on the foot line the front edge is off the slope");
            Assert.AreEqual(0f, AboveFloor(floor, back), 0.01f, "on the foot line the back edge is off the floor");
            Place("chair", new Vector3(RampX, 0f, RampHeadZ), 0f);
            yield return Steps(1);
            yield return Rendered();
            Assert.AreEqual(0.8f, Chair.transform.position.y, 1e-4f, "premise: the head line is at the platform height");
            Assert.That(VisualPitch, Is.InRange(0.3f * slope, 0.7f * slope), $"on the head line the visual pitches {VisualPitch:0.0} instead of about half the slope");
            Assert.Greater(AboveFloor(floor, front), -VisualTolerance, "on the head line the front edge sinks into the platform");
            Assert.Greater(AboveFloor(floor, back), -VisualTolerance, "on the head line the back edge sinks into the slope");

            // Driving up the ramp (the CharacterController, the interpolation and the hops): wherever the whole footprint
            // is on the slope, its front and back edges stand on it alike, and the sample box stays upright.
            Place("chair", new Vector3(RampX, 0f, RampFootZ - 0.5f), 0f);
            yield return Steps(2);
            Assert.IsFalse(Chair.WaitingForNeutralInput, "premise: the input is armed");
            int onSlope = 0;
            float worstTilt = 0f;
            float worstSink = 0f;
            float worstFloat = 0f;
            float worstBox = 0f;
            float zMin = RampFootZ + halfDepth + 0.05f;
            float zMax = RampHeadZ - halfDepth - 0.05f;
            Chair.ScriptedDirection = Vector3.forward;
            yield return Until(() =>
            {
                float z = Chair.Visual.position.z;
                if (Chair.IsMoving && z > zMin && z < zMax && Mathf.Abs(Chair.Visual.position.x - RampX) < 0.2f)
                {
                    onSlope++;
                    float f = AboveFloor(floor, front);
                    float b = AboveFloor(floor, back);
                    worstTilt = Mathf.Max(worstTilt, Mathf.Abs(f - b));
                    worstSink = Mathf.Min(worstSink, Mathf.Min(f, b));
                    worstFloat = Mathf.Max(worstFloat, Mathf.Max(f, b));
                    Chair.GetSamplePoints(samples);
                    for (int i = 2; i < samples.Length; i++)
                    {
                        worstBox = Mathf.Max(worstBox, Mathf.Abs(samples[i].y - samples[1].y));
                    }
                }
                return Chair.transform.position.z > 1.3f;
            }, 500);
            Chair.ScriptedDirection = null;
            yield return Steps(5);
            yield return Rendered();
            Assert.Greater(Chair.transform.position.z, 1.2f, $"premise: the chair climbed onto the platform (stopped at {Chair.transform.position})");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: nobody saw it");
            Assert.GreaterOrEqual(onSlope, 10, "premise: the chair was recorded on the slope while it drove up the ramp");
            Assert.Less(worstTilt, 0.02f, $"driving up, the front and back edges stood {worstTilt:0.000} m apart relative to the slope (an upright visual: {2f * halfDepth * rise:0.000})");
            Assert.Greater(worstSink, -0.02f, $"driving up, an edge sank {-worstSink:0.000} m into the slope");
            // The controller rests a few centimetres above its floor and the hop lifts the whole visual.
            Assert.Less(worstFloat, FloorTolerance + Tuning.HopHeight + 0.02f, $"driving up, an edge floated {worstFloat:0.000} m above the slope");
            Assert.Less(worstBox, 1e-4f, "driving up, the top samples of the rules were not level");
            // Still on the platform: upright, but for the creak tremble if the drive filled the gauge.
            Assert.Less(Vector3.Angle(Chair.Visual.up, Vector3.up), Tuning.CreakTrembleDegrees + AngleTolerance,
                "back on the flat platform, the visual is not upright again");
            AssertClean();
        }

        // ----- 39m: the memory ghost and the seat ghost follow the ramp slope (wave 5B, the 5A.1 m16 follow-up) -----

        /// <summary>
        /// Asserts a ghost (its base at the transform, built from y 0 up) lies on the slope at <paramref name="yaw"/>: its up is
        /// the ramp normal, its heading the yaw, and every footprint point stands on the floor under it.
        /// </summary>
        private static void AssertGhostOnSlope(Transform ghost, FloorMap floor, Vector3 rampNormal, Vector3 size, float yaw, string what)
        {
            Assert.Less(Vector3.Angle(ghost.up, rampNormal), AngleTolerance,
                $"{what}: its up {ghost.up} is not the ramp normal {rampNormal} ({Vector3.Angle(ghost.up, Vector3.up):0.0} degrees off upright)");
            float heading = YawMath.YawOf(YawMath.Planar(ghost.forward));
            Assert.Less(Mathf.Abs(Mathf.DeltaAngle(yaw, heading)), AngleTolerance, $"{what}: it turned to {heading}");
            foreach (Vector3 local in FootprintPoints(size))
            {
                Vector3 p = ghost.position + ghost.rotation * local;
                float above = p.y - floor.HeightAt(p.x, p.z);
                Assert.AreEqual(0f, above, VisualTolerance, $"{what}: the footprint point {local} is {above:0.000} m off the slope (negative sinks)");
            }
        }

        [UnityTest]
        public IEnumerator Step39m_MemoryAndSeatGhostsLieOnTheRampSlope()
        {
            Game.LoadLevel(SplitLevel);
            Assert.AreEqual(SplitLevel, Game.Def.Id, "premise: the split level loaded");
            yield return Steps(2);
            StationDef station = Game.Def.Inhabitants[0].Stations[0];
            Habitant.Pin(station.Position, station.Facing);
            yield return Steps(1);
            GhostView ghost = Game.Ghost;
            Assert.IsNotNull(ghost, "premise: the ghost view exists");
            Transform seat = ghost.transform.parent.Find("SeatGhost");
            Assert.IsNotNull(seat, "premise: the seat ghost exists");
            ghost.Floor = null;
            FloorMap floor = Chair.Floor;
            Assert.AreSame(Game.Def.Floor, floor, "premise: the furniture (so the ghosts) reads the level's floor");
            Assert.AreEqual(1, Game.Def.Ramps.Count, "premise: the split level has one ramp");
            RampDef ramp = Game.Def.Ramps[0];
            float slope = floor.SlopeOf(ramp);
            Assert.AreEqual(Mathf.Atan2(0.8f, 2.4f) * Mathf.Rad2Deg, slope, 0.01f, "premise: the ramp rises 0.8 m over 2.4 m");
            Vector3 uphill = YawMath.Forward(ramp.Yaw);
            Assert.Greater(uphill.z, 0.99f, "premise: the ramp rises toward +z");
            Vector3 rampNormal = (Vector3.up - uphill * Mathf.Tan(slope * Mathf.Deg2Rad)).normalized;
            Vector3 size = Chair.Size;
            var middle = new Vector3(RampX, 0f, RampMidZ);
            Assert.AreEqual(0.4f, floor.HeightAt(middle.x, middle.z), 1e-4f, "premise: the ramp middle is half way up");

            // On the ramp, whatever the yaw, both ghosts lie on the slope, the seat ghost with a size of its own. Read at once:
            // GameState redraws both ghosts on every step.
            var seatSize = new Vector3(0.6f, 1.05f, 0.85f);
            foreach (float yaw in new[] { 0f, 180f, 90f, -90f, 45f, 200f })
            {
                ghost.Show(new FurniturePose(middle + Vector3.up * 0.3f, yaw), size);
                Assert.IsTrue(ghost.Visible, "premise: the memory ghost shows");
                AssertGhostOnSlope(ghost.transform, floor, rampNormal, size, yaw, $"the memory ghost on the ramp at yaw {yaw}");
                ghost.ShowSeat(new FurniturePose(middle, yaw), seatSize);
                Assert.IsTrue(ghost.SeatVisible, "premise: the seat ghost shows");
                AssertGhostOnSlope(seat, floor, rampNormal, seatSize, yaw, $"the seat ghost on the ramp at yaw {yaw}");
            }
            ghost.Show(new FurniturePose(middle, 0f), size);
            float pitch = Mathf.Asin(Mathf.Clamp(ghost.transform.forward.y, -1f, 1f)) * Mathf.Rad2Deg;
            Assert.AreEqual(slope, pitch, AngleTolerance, "facing uphill, the memory ghost's nose is not up by the slope");

            // On the foot line it tips about half the slope, its front edge on the slope and its back edge on the floor.
            var foot = new Vector3(RampX, 0f, RampFootZ);
            ghost.ShowSeat(new FurniturePose(foot, 0f), size);
            float seatPitch = Mathf.Asin(Mathf.Clamp(seat.forward.y, -1f, 1f)) * Mathf.Rad2Deg;
            Assert.That(seatPitch, Is.InRange(0.3f * slope, 0.7f * slope), $"on the foot line the seat ghost pitches {seatPitch:0.0} instead of about half the slope");
            foreach (float z in new[] { size.z * 0.5f, -size.z * 0.5f })
            {
                Vector3 edge = seat.position + seat.rotation * new Vector3(0f, 0f, z);
                Assert.AreEqual(0f, edge.y - floor.HeightAt(edge.x, edge.z), 0.01f, $"on the foot line the seat ghost's edge at {z} is off the floor");
            }

            // Off the ramp both stay upright on the floor height there (the floor, the platform, beside the ramp).
            foreach (Vector3 spot in new[] { new Vector3(2.5f, 0f, -2.0f), new Vector3(-2.5f, 0f, 1.75f), new Vector3(1.0f, 0f, -1.0f) })
            {
                ghost.Show(new FurniturePose(spot, 30f), size);
                Assert.Less(Vector3.Angle(ghost.transform.up, Vector3.up), 0.01f, $"the memory ghost at {spot} off the ramp is not upright");
                Assert.AreEqual(floor.HeightAt(spot.x, spot.z), ghost.transform.position.y, 1e-4f, $"the memory ghost at {spot} is off the floor height");
                ghost.ShowSeat(new FurniturePose(spot, 30f), size);
                Assert.Less(Vector3.Angle(seat.up, Vector3.up), 0.01f, $"the seat ghost at {spot} off the ramp is not upright");
            }

            // GhostView.Floor wins: on a flat floor the ghost on the ramp's spot stands upright at 0.
            ghost.Floor = FloorMap.Flat;
            ghost.Show(new FurniturePose(middle, 0f), size);
            Assert.Less(Vector3.Angle(ghost.transform.up, Vector3.up), 0.01f, "on a flat GhostView.Floor the memory ghost is not upright");
            Assert.AreEqual(0f, ghost.transform.position.y, 1e-5f, "on a flat GhostView.Floor the memory ghost is not at 0");
            ghost.Floor = null;
            ghost.Hide();
            ghost.ShowSeat(null);
            yield return Steps(1);
            AssertClean();
        }

        /// <summary>
        /// The product owner's 2026-11-18 report: the memory ghost always drew a chair (6 boxes, 72 triangles), whatever
        /// the player furniture's own kind. On test_rock (a procedural rocking_chair, no model, 20 boxes, 240 triangles:
        /// not a chair) GhostView.Show now copies FurnitureController.Visual's own meshes, so the ghost's combined bounds
        /// span the same world size as the real furniture body, and its mesh carries the rocking chair's own triangles
        /// (240, plus the ring), not the chair's fallback (72, plus the ring: 168 total). A tiny ring tolerance keeps the
        /// ring well inside the body's own footprint, so it cannot pad the bounds and hide a wrong body shape.
        /// </summary>
        [UnityTest]
        public IEnumerator GhostCombinedBoundsMatchANonChairFurnitureBody()
        {
            Game.LoadLevel("test_rock");
            Assert.AreEqual("test_rock", Game.Def.Id, "premise: test_rock loaded");
            yield return Steps(2);
            FurnitureController furniture = Chair;
            Assert.AreNotEqual(BodyKinds.Chair, furniture.Kind, "premise: the player furniture of test_rock is not a chair");
            Assert.IsNotNull(furniture.Visual, "premise: the furniture has a visual");

            Bounds furnitureBounds = LoadView.BoundsOf(furniture.Visual);
            Assert.Greater(furnitureBounds.size.magnitude, 0.3f, "premise: the furniture body has a real size");

            GhostView ghost = Game.Ghost;
            ghost.Show(furniture.Pose, furniture.Size, furniture.Visual, 0.01f);
            Assert.IsTrue(ghost.Visible, "premise: the ghost shows");
            Bounds ghostBounds = ghost.GetComponent<MeshRenderer>().bounds;

            const float tolerance = 0.05f;
            Assert.AreEqual(furnitureBounds.size.x, ghostBounds.size.x, tolerance, "the ghost's width does not match the real rocking chair");
            Assert.AreEqual(furnitureBounds.size.y, ghostBounds.size.y, tolerance, "the ghost's height does not match the real rocking chair");
            Assert.AreEqual(furnitureBounds.size.z, ghostBounds.size.z, tolerance, "the ghost's depth does not match the real rocking chair");

            // The chair's own boxes (the bug) would be 6 boxes and a ring, 168 triangles; the real rocking chair's 20
            // boxes and the same ring are 336: well over the chair's fallback count either way.
            int ghostTriangles = ghost.GetComponent<MeshFilter>().sharedMesh.triangles.Length / 3;
            Assert.Greater(ghostTriangles, 200, "the ghost's mesh is too small to be the rocking chair's own shape (still the chair's boxes?)");
            ghost.Hide();
            AssertClean();
        }

        // ----- 42g: the robot's shove, FurnitureController.BeginPush (CONTRACT_M5 4, 16.8, 18) -----

        private static int PushSteps => Mathf.RoundToInt(Tuning.RobotPushTime / Dt);

        private static float PushStepDistance => Tuning.RobotPushDistance / PushSteps;

        /// <summary>Asserts a refused push that changes nothing: the action in progress (or none) stays as it was.</summary>
        private static void AssertPushRefused(FurnitureController f, string why)
        {
            FurnitureController.BodyAction before = f.Action;
            bool active = f.ActionActive;
            Assert.IsFalse(f.BeginPush(Vector3.right, Tuning.RobotPushDistance, Tuning.RobotPushTime), "the push started while " + why);
            Assert.AreEqual(before, f.Action, "a refused push changed the action while " + why);
            Assert.AreEqual(active, f.ActionActive, "a refused push changed ActionActive while " + why);
        }

        /// <summary>The planar travel of recorded step <paramref name="index"/> (from the step before, or from <paramref name="before"/>).</summary>
        private Vector3 TravelOf(int index, int start, Vector3 before)
        {
            Vector3 from = index > start ? trace[index - 1].Position : before;
            return YawMath.Planar(trace[index].Position - from);
        }

        /// <summary>
        /// Asserts the <see cref="PushSteps"/> recorded steps from <paramref name="start"/> are a free push along
        /// <paramref name="direction"/> (0.01 m each, nothing across it, each a Push action and moving), and the step after
        /// is still, free and travels nothing.
        /// </summary>
        private void AssertFreePush(int start, Vector3 before, Vector3 direction, string what)
        {
            Assert.GreaterOrEqual(trace.Count, start + PushSteps + 1, "premise: the step after the push was not recorded");
            Assert.AreEqual(PushSteps, ActionRun(start), what + ": the push did not last exactly RobotPushTime");
            for (int i = 0; i < PushSteps; i++)
            {
                Sample s = trace[start + i];
                Assert.IsTrue(s.Moving, $"{what}: push step {i + 1} is not moving");
                Assert.AreEqual(FurnitureController.BodyAction.Push, s.Kind, $"{what}: push step {i + 1}: the action");
                Vector3 d = TravelOf(start + i, start, before);
                Assert.AreEqual(PushStepDistance, Vector3.Dot(d, direction), 1e-3f, $"{what}: push step {i + 1} did not slide 0.01 m along the push");
                Assert.Less(Vector3.Cross(d, direction).magnitude, 1e-3f, $"{what}: push step {i + 1} slid off the push (the input or a drive moved it)");
            }
            Vector3 total = YawMath.Planar(trace[start + PushSteps - 1].Position - before);
            Assert.AreEqual(Tuning.RobotPushDistance, Vector3.Dot(total, direction), 0.005f, what + ": the push is not 0.25 m");
            Sample after = trace[start + PushSteps];
            Assert.IsFalse(after.Moving || after.Action, what + ": the furniture is not still and free on the step after the push");
            Assert.AreEqual(FurnitureController.BodyAction.None, after.Kind, what + ": an action on the step after the push");
            Assert.Less(TravelOf(start + PushSteps, start, before).magnitude, 1e-4f, what + ": the furniture kept travelling after the push");
        }

        /// <summary>The x of the inner face of the wall a ray from <paramref name="origin"/> toward +x meets first.</summary>
        private static float WallFaceX(Vector3 origin)
        {
            Assert.IsTrue(Physics.Raycast(origin, Vector3.right, out RaycastHit hit, 10f, Layers.OccluderMask, QueryTriggerInteraction.Ignore),
                "premise: no wall toward +x");
            Assert.Greater(hit.point.x, 3.5f, "premise: the ray met something before the +x wall");
            return hit.point.x;
        }

        /// <summary>
        /// Step 42g (CONTRACT_M5 4, 16.8, 18): <see cref="FurnitureController.BeginPush"/>. From rest, a 0.25 m push in 0.5 s
        /// is 25 steps of 0.01 m, each an action and moving, a held key ignored, no hop, the yaw kept; the step after is still.
        /// Driving, the push replaces the drive and the held key drives again from rest after it; gliding, it ends the glide,
        /// rolls no tick and ends still (no glide after). Any collider stops it: head-on the chair stops at the wall and stays
        /// there, obliquely it stops without sliding along the wall; either way it keeps its 25 moving steps. It is refused
        /// during any action (a push, an external action), while the stool falls or lies tipped, pinned or carried, and for a
        /// zero direction, distance or time; a pin or a carry ends it at once.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step42g_PushSlidesAQuarterMetreInHalfASecondStopsAtAColliderAndIsRefusedWhenBusy()
        {
            Assert.AreEqual(25, PushSteps, "premise: a shove is 25 steps (RobotPushTime 0.5 s at 50 Hz)");
            PinAway();

            // 1. From rest, with a key held through its middle.
            Place("chair", LaneStart, 90f);
            yield return Steps(3);
            Assert.IsFalse(Chair.IsMoving || Chair.ActionActive, "premise: the chair is still and in no action");
            Vector3 before = Chair.transform.position;
            int hops = Chair.HopCount;
            int start = trace.Count;
            Assert.IsTrue(Chair.BeginPush(Vector3.right * 3f, Tuning.RobotPushDistance, Tuning.RobotPushTime), "a still, upright, free chair refused the push");
            Assert.IsTrue(Chair.ActionActive && Chair.Pushing, "the push is not active at once");
            Assert.AreEqual(FurnitureController.BodyAction.Push, Chair.Action);
            AssertPushRefused(Chair, "pushed");
            AssertRefused(Chair, "pushed");
            int k = 0;
            void HoldKey()
            {
                k++;
                Chair.ScriptedDirection = k >= 3 && k < 19 ? Vector3.back : (Vector3?)null;
            }
            Game.FixedStepped += HoldKey;
            yield return Steps(PushSteps + 4);
            Game.FixedStepped -= HoldKey;
            Chair.ScriptedDirection = null;
            AssertFreePush(start, before, Vector3.right, "from rest");
            Assert.Less(Mathf.Abs(Mathf.DeltaAngle(90f, Chair.Yaw)), 1e-3f, "the push turned the chair");
            Assert.AreEqual(hops, Chair.HopCount, "the pushed chair hopped (the robot slides it)");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: unseen, the push was not caught");

            // 2. Driving at full speed: accepted; the push replaces the drive, then the held key drives again from rest.
            Place("chair", LaneStart, 90f);
            yield return Steps(2);
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(20);
            Assert.IsTrue(Chair.IsMoving && Chair.Velocity.magnitude > Tuning.ChairMaxSpeed - 0.01f, "premise: the chair drives at full speed");
            before = Chair.transform.position;
            start = trace.Count;
            Assert.IsTrue(Chair.BeginPush(Vector3.back, Tuning.RobotPushDistance, Tuning.RobotPushTime), "a driving chair refused the push");
            yield return Steps(PushSteps + 1);
            Assert.AreEqual(PushSteps, ActionRun(start), "driving: the push did not last exactly RobotPushTime");
            for (int i = 0; i < PushSteps; i++)
            {
                Vector3 d = TravelOf(start + i, start, before);
                Assert.AreEqual(PushStepDistance, -d.z, 1e-3f, $"driving: push step {i + 1} did not slide 0.01 m along the push");
                Assert.Less(Mathf.Abs(d.x), 1e-3f, $"driving: push step {i + 1} kept the drive (the held key moved it)");
            }
            Vector3 first = TravelOf(start + PushSteps, start, before);
            Chair.ScriptedDirection = null;
            Assert.IsTrue(trace[start + PushSteps].Moving && !trace[start + PushSteps].Action, "driving: the held key did not drive again after the push");
            Assert.AreEqual(Tuning.ChairAcceleration * Dt * Dt, first.x, 1e-3f, "driving: after the push the held key did not drive from rest");
            Assert.Less(Mathf.Abs(first.z), 1e-4f, "driving: the push's velocity outlived the push");

            // 3. Gliding (the office chair after a release): accepted; the glide ends at once, no roll tick, still after.
            Place("office_chair", LaneStart, 90f);
            yield return Steps(2);
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.Velocity.magnitude >= 2f, 75);
            Chair.ScriptedDirection = null;
            yield return Steps(3);
            Assert.IsTrue(Chair.Gliding && Chair.PredictedStop.HasValue, "premise: the office chair glides, its stop predicted");
            int rolls = Chair.RollCount;
            before = Chair.transform.position;
            start = trace.Count;
            Assert.IsTrue(Chair.BeginPush(Vector3.back, Tuning.RobotPushDistance, Tuning.RobotPushTime), "a gliding office chair refused the push");
            Assert.IsFalse(Chair.Gliding, "the push did not end the glide");
            Assert.IsFalse(Chair.PredictedStop.HasValue, "the push kept the glide's predicted stop");
            yield return Steps(PushSteps + 3);
            AssertFreePush(start, before, Vector3.back, "gliding");
            Assert.AreEqual(rolls, Chair.RollCount, "the pushed office chair rolled a tick (the robot slides it)");
            Assert.IsFalse(Chair.Gliding || Chair.IsMoving || Chair.PredictedStop.HasValue, "the office chair glides after the push");

            // 4. Head-on into the +x wall from 0.1 m: it stops at the wall, never in it, and stays there, moving for 25 steps.
            Place("chair", new Vector3(3.0f, 0f, LaneZ), 90f);
            float face = WallFaceX(Chair.Center);
            float radius = Chair.Body.Radius;
            Chair.Teleport(new Vector3(face - radius - 0.1f, 0f, LaneZ), 90f);
            yield return Steps(2);
            before = Chair.transform.position;
            start = trace.Count;
            Assert.IsTrue(Chair.BeginPush(Vector3.right, Tuning.RobotPushDistance, Tuning.RobotPushTime), "premise: the push toward the wall started");
            yield return Steps(PushSteps + 2);
            Assert.AreEqual(PushSteps, ActionRun(start), "head-on: a push stopped by the wall did not keep its 25 steps");
            for (int i = 0; i < PushSteps; i++)
            {
                Assert.IsTrue(trace[start + i].Moving, $"head-on: push step {i + 1} is not moving");
            }
            float stop = trace[start + PushSteps - 1].Position.x;
            Assert.LessOrEqual(stop, face - radius + 0.005f, $"head-on: the push went into the wall (stopped at {stop:0.000}, face {face:0.000})");
            Assert.Greater(stop - before.x, 0.06f, "head-on: the push did not reach the wall");
            int blocked = -1;
            for (int i = 0; i < PushSteps && blocked < 0; i++)
            {
                if (TravelOf(start + i, start, before).magnitude < PushStepDistance * 0.5f)
                {
                    blocked = i;
                }
            }
            Assert.Greater(blocked, 0, "premise: the wall never stopped the push");
            for (int i = blocked + 1; i <= PushSteps; i++)
            {
                Assert.Less(TravelOf(start + i, start, before).magnitude, 1e-4f, $"head-on: step {i + 1} travelled after the wall stopped the push");
            }
            Assert.IsFalse(trace[start + PushSteps].Moving, "head-on: the chair is not still after the push");

            // 5. Obliquely into the same wall from 0.03 m: it stops at the wall, without sliding along it.
            Chair.Teleport(new Vector3(face - radius - 0.03f, 0f, LaneZ), 90f);
            yield return Steps(2);
            before = Chair.transform.position;
            start = trace.Count;
            Vector3 oblique = new Vector3(1f, 0f, 1f).normalized;
            Assert.IsTrue(Chair.BeginPush(oblique, Tuning.RobotPushDistance, Tuning.RobotPushTime), "premise: the oblique push started");
            yield return Steps(PushSteps + 2);
            Assert.AreEqual(PushSteps, ActionRun(start), "oblique: a push stopped by the wall did not keep its 25 steps");
            Vector3 slid = YawMath.Planar(trace[start + PushSteps].Position - before);
            Assert.LessOrEqual(Chair.transform.position.x, face - radius + 0.005f, "oblique: the push went into the wall");
            Assert.Greater(slid.z, 0.003f, "premise: the oblique push did not move the chair before the wall");
            Assert.Less(slid.z, 0.05f, $"oblique: the chair slid {slid.z:0.000} m along the wall (a free slide is about 0.18 m)");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: nobody saw the pushes");

            // 6. Refused during an external action, which keeps its 30 steps.
            Place("chair", LaneStart, 90f);
            yield return Steps(2);
            start = trace.Count;
            Assert.IsTrue(Chair.BeginExternalAction(Tuning.DoorOpenTime), "premise: the external action started");
            AssertPushRefused(Chair, "in an external action");
            yield return Steps(DoorSteps + 3);
            Assert.AreEqual(DoorSteps, ActionRun(start), "a refused push changed the external action's length");
            Assert.Less(Planar(Chair.transform.position, LaneStart), 1e-4f, "a refused push moved the chair");

            // 7. The stool: refused while it falls (an action, tipped) and while it lies on its side (tipped, no action).
            Place("stool", LaneStart, 90f);
            yield return Steps(2);
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.Velocity.magnitude > Tuning.StoolTipSpeed + 0.2f, 60);
            Chair.ScriptedDirection = null;
            yield return Steps(1);
            Assert.AreEqual(FurnitureController.BodyAction.Fall, Chair.Action, "premise: the stool falls");
            AssertPushRefused(Chair, "falling");
            yield return Until(() => Chair.LyingDown, 30);
            yield return Steps(2);
            Assert.IsTrue(Chair.LyingDown && !Chair.IsMoving, "premise: the stool lies still on its side");
            Vector3 lying = Chair.transform.position;
            AssertPushRefused(Chair, "lying on its side");
            yield return Steps(5);
            Assert.IsTrue(Chair.LyingDown && !Chair.IsMoving, "a refused push got the stool up or moved it");
            Assert.Less(Planar(Chair.transform.position, lying), 1e-4f, "a refused push moved the lying stool");

            // 8. Pinned and carried, on a controller of its own; a pin or a carry ends a push at once.
            var home = new Vector3(1.0f, 0f, 0.9f);
            FurnitureController f = Standalone("chair", home, 90f);
            StepManually(f, 2);
            Assert.IsFalse(f.IsMoving || f.ActionActive, "premise: the standalone chair is still");
            f.Pin(true);
            AssertPushRefused(f, "pinned");
            f.Pin(false);
            StepManually(f, 1);
            f.FollowCarrier(home + new Vector3(0f, 0.6f, 0.4f), 90f);
            Assert.IsTrue(f.Carried, "premise: carried");
            AssertPushRefused(f, "carried");
            f.Release(new FurniturePose(home, 90f));
            Assert.IsTrue(f.BeginPush(Vector3.right, Tuning.RobotPushDistance, Tuning.RobotPushTime), "control: put down, the standalone chair refused the push");
            StepManually(f, 5);
            Assert.IsTrue(f.Pushing && f.IsMoving, "premise: the standalone chair is pushed");
            Assert.AreEqual(5f * PushStepDistance, f.transform.position.x - home.x, 1e-3f, "the standalone push did not slide 0.01 m a step");
            f.Pin(true);
            Assert.IsFalse(f.ActionActive || f.Pushing, "a pin left the push running");
            f.Pin(false);
            StepManually(f, 1);
            Assert.IsTrue(f.BeginPush(Vector3.right, Tuning.RobotPushDistance, Tuning.RobotPushTime), "premise: a second push started");
            f.FollowCarrier(home + new Vector3(0f, 0.6f, 0.4f), 90f);
            Assert.IsFalse(f.ActionActive || f.Pushing, "a carry left the push running");
            f.Release(new FurniturePose(home, 90f));
            // A zero (or vertical) direction, distance or time starts nothing.
            Assert.IsFalse(f.BeginPush(Vector3.zero, Tuning.RobotPushDistance, Tuning.RobotPushTime), "a zero direction started a push");
            Assert.IsFalse(f.BeginPush(Vector3.up, Tuning.RobotPushDistance, Tuning.RobotPushTime), "a vertical direction started a push");
            Assert.IsFalse(f.BeginPush(Vector3.right, 0f, Tuning.RobotPushTime), "a zero distance started a push");
            Assert.IsFalse(f.BeginPush(Vector3.right, Tuning.RobotPushDistance, 0f), "a zero time started a push");
            Assert.IsFalse(f.BeginPush(Vector3.right, Tuning.RobotPushDistance, float.NaN), "a NaN time started a push");
            Assert.IsFalse(f.ActionActive);
            yield return Steps(1);
            AssertClean();
        }

        // ----- 44g: MotionProfile against the real controller (CONTRACT_M5 16.5) -----

        /// <summary>What one comparison of <see cref="MotionProfile"/> with the controller saw.</summary>
        private sealed class ProfileRun
        {
            public int Steps;
            public float WorstError;
            public int WorstStep = -1;
            public string FirstActionMismatch;
            public string FirstMovingMismatch;
            public int ProfileRocks;
            public int GameRocks;
            public int ProfileFalls;
            public int ControllerFallSteps;
            public int GlideSteps;
            public int PushSteps;
            public int ActionSteps;
            public float YawSpan;
            public float WorstYaw;
            public string Failure;

            public override string ToString()
            {
                return $"{Steps} steps, worst {WorstError:0.0000} m/s at step {WorstStep}, rocks {ProfileRocks} (game {GameRocks}), falls {ProfileFalls}, "
                    + $"glide steps {GlideSteps}, push steps {PushSteps}, action steps {ActionSteps}, yaw span {YawSpan:0.0}, worst yaw {WorstYaw:0.000}";
            }
        }

        /// <summary>
        /// Drives the body of <paramref name="kind"/> from rest at <paramref name="at"/> (facing <paramref name="yaw"/>) on level
        /// 1 with <paramref name="script"/>, one wish a step (ScriptedDirection and ScriptedCareful), and steps a
        /// <see cref="MotionProfile"/> of the same body on the same wishes. The controller's velocity of a step is its measured
        /// planar travel over dt. The rock, which MotionProfile leaves to its caller, is modelled as GameState starts it (the
        /// 16.9 come-to-rest rule on travel and yaw, then an action of RockTime, RockCarefulTime when careful). After the step
        /// of index <paramref name="pushAfter"/> (if not negative), both begin the robot's shove along
        /// <paramref name="pushDirection"/>.
        /// </summary>
        private IEnumerator RunAgainstProfile(string kind, Vector3 at, float yaw, MotionScript script, int pushAfter, Vector3 pushDirection, ProfileRun run)
        {
            Place(kind, at, yaw);
            yield return Steps(3);
            Assert.IsFalse(Chair.IsMoving || Chair.ActionActive || Chair.Tipped, $"premise: the {kind} is still and upright");
            Assert.AreEqual(kind, Chair.Body.Kind, "premise: the body");
            var profile = new MotionProfile(Chair.Body, Dt, true, Chair.Yaw);
            int rocksBefore = Game.RockCount;
            float minYaw = 0f;
            float maxYaw = 0f;
            float startYaw = Chair.Yaw;
            Vector3 last = Chair.transform.position;
            bool armed = false;
            int i = 0;
            void Apply(MotionWish w)
            {
                Chair.ScriptedDirection = w.Active ? new Vector3(w.Direction.x, 0f, w.Direction.y) : (Vector3?)null;
                Chair.ScriptedCareful = w.Careful;
            }
            void OnStep()
            {
                if (i >= script.Count)
                {
                    return;
                }
                Vector3 p = Chair.transform.position;
                Vector3 travel = YawMath.Planar(p - last) / Dt;
                last = p;
                Vector2 expected = profile.Step(script[i]);
                float error = (new Vector2(travel.x, travel.z) - expected).magnitude;
                if (error > run.WorstError)
                {
                    run.WorstError = error;
                    run.WorstStep = i;
                }
                // The rock as GameState.StepRock starts it, inside this very step: the first step at or below both moving
                // thresholds after a step above them, measured on travel and yaw, outside every action; it covers the next
                // steps. Modelled before the action flags are compared, as GameState began it before this handler ran.
                bool travelled = MotionRule.IsMoving(profile.Speed, profile.YawRate);
                bool rests = armed && !travelled && !profile.ActionActive;
                armed = travelled;
                if (rests && profile.Body.Rocks)
                {
                    if (profile.BeginAction(profile.Careful ? Tuning.RockCarefulTime : Tuning.RockTime))
                    {
                        run.ProfileRocks++;
                    }
                    else if (run.Failure == null)
                    {
                        run.Failure = $"premise: the profile's rock was refused at step {i}";
                    }
                }
                run.WorstYaw = Mathf.Max(run.WorstYaw, Mathf.Abs(Mathf.DeltaAngle(profile.Yaw, Chair.Yaw)));
                float turned = Mathf.DeltaAngle(startYaw, Chair.Yaw);
                minYaw = Mathf.Min(minYaw, turned);
                maxYaw = Mathf.Max(maxYaw, turned);
                if (run.FirstActionMismatch == null && (profile.ActionActive != Chair.ActionActive || profile.Tipped != Chair.Tipped))
                {
                    run.FirstActionMismatch = $"step {i}: profile action {profile.ActionActive} tipped {profile.Tipped}, controller action {Chair.ActionActive} ({Chair.Action}) tipped {Chair.Tipped}";
                }
                if (run.FirstMovingMismatch == null && profile.IsMoving != Chair.IsMoving)
                {
                    run.FirstMovingMismatch = $"step {i}: profile moving {profile.IsMoving} at {profile.Speed:0.000} m/s, controller {Chair.IsMoving} at {travel.magnitude:0.000} m/s";
                }
                run.GlideSteps += profile.Gliding ? 1 : 0;
                run.PushSteps += profile.Pushing ? 1 : 0;
                run.ActionSteps += profile.ActionActive ? 1 : 0;
                run.ControllerFallSteps += Chair.Action == FurnitureController.BodyAction.Fall ? 1 : 0;
                if (i == pushAfter)
                {
                    bool modelled = profile.BeginPush(new Vector2(pushDirection.x, pushDirection.z), Tuning.RobotPushDistance, Tuning.RobotPushTime);
                    bool real = Chair.BeginPush(pushDirection, Tuning.RobotPushDistance, Tuning.RobotPushTime);
                    if (!modelled && run.Failure == null)
                    {
                        run.Failure = $"premise: the profile refused the push after step {i}";
                    }
                    if (!real && run.Failure == null)
                    {
                        run.Failure = $"the {kind} refused the push after step {i}";
                    }
                }
                i++;
                if (i < script.Count)
                {
                    Apply(script[i]);
                }
                else
                {
                    Chair.ScriptedDirection = null;
                    Chair.ScriptedCareful = null;
                }
            }
            Apply(script[0]);
            Game.FixedStepped += OnStep;
            yield return Until(() => i >= script.Count, script.Count + 5);
            Game.FixedStepped -= OnStep;
            Chair.ScriptedDirection = null;
            Chair.ScriptedCareful = null;
            run.Steps = i;
            run.ProfileFalls = profile.FallCount;
            run.GameRocks = Game.RockCount - rocksBefore;
            run.YawSpan = maxYaw - minYaw;
            Debug.Log($"[Step44g] {kind}: {run}");
            Assert.IsNull(run.Failure, run.Failure);
            Assert.AreEqual(script.Count, run.Steps, $"premise: the {kind}'s script did not run to its end");
            Assert.AreEqual(PlayState.Playing, Game.State, $"premise: the {kind} was caught");
        }

        /// <summary>Asserts a comparison run: every step's velocity within 0.05 m/s, and the actions and the moving predicate alike.</summary>
        private static void AssertProfileMatches(string kind, ProfileRun run)
        {
            Assert.LessOrEqual(run.WorstError, 0.05f, $"{kind}: the controller left MotionProfile by {run.WorstError:0.000} m/s at step {run.WorstStep} ({run})");
            Assert.IsNull(run.FirstActionMismatch, $"{kind}: the actions differ: {run.FirstActionMismatch}");
            Assert.IsNull(run.FirstMovingMismatch, $"{kind}: the moving predicate differs: {run.FirstMovingMismatch}");
            Assert.AreEqual(run.ProfileRocks, run.GameRocks, $"{kind}: GameState rocked {run.GameRocks} times, the modelled rule {run.ProfileRocks}");
        }

        /// <summary>
        /// Step 44g (CONTRACT_M5 16.5): MotionProfile is the driving rules of FurnitureController. On level 1's free floor, each
        /// body runs a script of wishes on the real controller and on a MotionProfile: every step's planar velocity agrees within
        /// 0.05 m/s, and so do the actions (falls, rightings, rocks, pushes) and the moving predicate. The chair starts, turns 90
        /// degrees at full speed, goes careful, reverses careful and starts again; the stool goes careful, stops, goes full,
        /// falls on release, rights itself on the next key and drives careful; the office chair glides on release, is shoved
        /// with a key held (ignored, then it drives from rest), glides careful, then brakes against its motion; the rocking chair
        /// rocks after a full stop (0.8 s) and after a careful one (0.4 s), is shoved and rocks after the shove, and a key held
        /// during the rock is ignored.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step44g_MotionProfileMatchesTheControllerForFourBodies()
        {
            PinAway();
            yield return Steps(1);

            // The chair, from (-3.4, -1) facing +x: its path stays in x -3.4 to -2.3, z -1.85 to -1.
            var chair = new MotionScript(Dt);
            chair.HoldYaw(90f, 0.6f).HoldYaw(180f, 0.4f).HoldYaw(180f, 0.3f, true).HoldYaw(0f, 0.3f, true).Release(0.2f).HoldYaw(270f, 0.3f).Release(0.2f);
            var chairRun = new ProfileRun();
            yield return RunAgainstProfile("chair", LaneStart, 90f, chair, -1, Vector3.zero, chairRun);
            Assert.Greater(chairRun.YawSpan, 80f, "premise: the chair did not turn 90 degrees");
            AssertProfileMatches("chair", chairRun);

            // The stool, along the lane: a careful run and stop, a full run released above StoolTipSpeed (it falls), then the
            // next key rights it and it drives careful.
            var stool = new MotionScript(Dt);
            stool.HoldYaw(90f, 0.5f, true).Release(0.2f, true).HoldYaw(90f, 0.6f).Release(0.5f).HoldYaw(270f, 0.6f, true).Release(0.2f, true);
            var stoolRun = new ProfileRun();
            yield return RunAgainstProfile("stool", LaneStart, 90f, stool, -1, Vector3.zero, stoolRun);
            Assert.AreEqual(1, stoolRun.ProfileFalls, "premise: the stool's script did not make it fall once");
            Assert.AreEqual(Mathf.RoundToInt(Tuning.StoolFallTime / Dt), stoolRun.ControllerFallSteps, "premise: the controller's stool did not fall for StoolFallTime");
            AssertProfileMatches("stool", stoolRun);

            // The office chair, along the lane: a full run and its glide, a shove from rest after it (step 59) with a careful key
            // held through it, a careful glide, a full run, then braking against the motion (a glide), and a last glide.
            var office = new MotionScript(Dt);
            office.HoldYaw(90f, 0.7f).Release(0.5f).HoldYaw(90f, 0.7f, true).Release(0.5f, true).HoldYaw(90f, 0.3f).HoldYaw(270f, 0.5f).Release(0.5f);
            var officeRun = new ProfileRun();
            yield return RunAgainstProfile("office_chair", LaneStart, 90f, office, 59, Vector3.right, officeRun);
            Assert.AreEqual(PushSteps, officeRun.PushSteps, "premise: the office chair was not shoved for 25 steps");
            Assert.Greater(officeRun.GlideSteps, 50, "premise: the office chair did not glide three times");
            AssertProfileMatches("office_chair", officeRun);

            // The rocking chair, along the lane: a full stop at step 30 (a rock of 40 steps), a careful stop at step 110 (20
            // steps), a shove after step 135 and its rock from step 162, a key held from step 190 (ignored until the rock ends),
            // and a last stop at step 210.
            var rocking = new MotionScript(Dt);
            rocking.HoldYaw(90f, 0.6f).Release(1.2f).HoldYaw(90f, 0.4f, true).Release(1.0f, true).Release(0.6f).HoldYaw(270f, 0.4f).Release(0.3f);
            var rockingRun = new ProfileRun();
            yield return RunAgainstProfile("rocking_chair", LaneStart, 90f, rocking, 135, Vector3.right, rockingRun);
            Assert.AreEqual(4, rockingRun.ProfileRocks, "premise: the rocking chair's script did not make four rocks");
            Assert.AreEqual(PushSteps, rockingRun.PushSteps, "premise: the rocking chair was not shoved for 25 steps");
            int rockSteps = 3 * Mathf.RoundToInt(Tuning.RockTime / Dt) + Mathf.RoundToInt(Tuning.RockCarefulTime / Dt);
            Assert.Greater(rockingRun.ActionSteps, rockSteps - Mathf.RoundToInt(Tuning.RockTime / Dt), "premise: the rocks were not modelled as actions");
            AssertProfileMatches("rocking_chair", rockingRun);
            AssertClean();
        }
    }
}
