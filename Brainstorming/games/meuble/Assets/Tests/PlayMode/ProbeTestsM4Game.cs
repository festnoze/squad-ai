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
    /// The M4 game probe (docs/CONTRACT_M4.md 8 and amendments 9.1, 9.2, 9.4, 9.10) on the real Boot scene, under
    /// GameRules.M4: step 28 (the stool) and step 30 (the lamp) on level 1 with <see cref="FurnitureController.SetBody"/>,
    /// steps 31 to 33 (sitting) on the test level test_m4_game_sit (never listed in levels.json): a sitter whose seat
    /// home is the chair's spawn on a rug, a watcher, and a sofa.
    ///
    /// As in the M1 to M3 probes, every wait counts fixed steps or is bounded by game time (with a real time guard),
    /// never by rendered frames; every scenario asserts its premise first, so it cannot pass for the wrong reason;
    /// Time.timeScale is restored in a finally and in the TearDown.
    /// </summary>
    public sealed class ProbeTestsM4Game
    {
        private const float Dt = Tuning.FixedStep;
        private const string SitLevel = "test_m4_game_sit";
        private const float EyeTolerance = 0.03f;
        private const float HeadTolerance = 5f;

        // test_m4_game_sit: the sitter's sit station, its seat home (the chair's spawn, on a rug), and its first station.
        private static readonly Vector3 SitStation = new Vector3(0f, 0f, -1.2f);
        private static readonly Vector3 SeatHome = new Vector3(0f, 0f, -1.85f);
        private static readonly Vector3 FirstStation = new Vector3(-3f, 0f, -1.2f);
        // Where the chair hides from the sitter for the whole approach, the fall and the look (bearing 270 from the
        // sit station, 79 deg off the fall's facing): the "missing chair".
        private static readonly Vector3 HidingSpot = new Vector3(-3.6f, 0f, -1.2f);
        // Where the chair is pulled to during the back turn, on the rug: 1.15 m from the seat home, 78 deg off the facing
        // of the fall there, and bearing 250 from the sit station, 70 deg off the end of the look at the empty seat.
        // The sample corners spread about 14 deg at that distance; seen from above, the cone's reach on the floor is
        // narrower than 55 deg (a corner 0.3 to 0.7 m below the eye), so neither the turn, the fall nor the look has it.
        private static readonly Vector3 PulledTo = new Vector3(-1.128f, 0f, -1.61f);

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;
        private readonly List<NoiseEvent> noises = new List<NoiseEvent>();

        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Furniture => Game.Furniture;
        private Inhabitant Habitant => Game.MainInhabitant;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            fixedSteps = 0;
            noises.Clear();
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
            // This file is the M4 game probe: every M4 rule is on (GameState.Rules defaults to M4).
            Game.Rules = GameRules.M4;
            Game.FixedStepped += CountStep;
            Game.Noise += OnNoise;
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
                main.Game.Noise -= OnNoise;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                    main.Game.Furniture.ScriptedCareful = null;
                }
            }
            yield return null;
        }

        private void CountStep() => fixedSteps++;

        private void OnNoise(NoiseEvent e) => noises.Add(e);

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        private void AssertNoErrors()
        {
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        /// <summary>A bound: enough fixed steps to cover <paramref name="seconds"/>.</summary>
        private static int StepsFor(float seconds) => Mathf.CeilToInt(seconds / Dt);

        /// <summary>
        /// An exact duration in fixed steps: rounded, since 0.3f / 0.02f is 15.000001 in float and its ceiling would
        /// be 16 (the rules run their timers the same way).
        /// </summary>
        private static int StepsOf(float seconds) => Mathf.RoundToInt(seconds / Dt);

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(to - from);

        private static float Planar(Vector3 a, Vector3 b) => YawMath.Planar(a - b).magnitude;

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

        /// <summary>One fixed step at a time until <paramref name="until"/> holds (checked after each step), at most <paramref name="maxSteps"/>.</summary>
        private static IEnumerator StepUntil(Func<bool> until, int maxSteps, Action perStep = null)
        {
            for (int i = 0; i < maxSteps && !until(); i++)
            {
                yield return new WaitForFixedUpdate();
                perStep?.Invoke();
            }
        }

        private void UseBody(string kind)
        {
            Furniture.SetBody(BodyDef.For(kind));
            Assert.AreEqual(kind, Furniture.Body.Kind, $"premise: SetBody did not give the {kind} body");
        }

        /// <summary>Frozen pins (no sight memory, no hearing) every inhabitant but <paramref name="except"/> where it stands, facing <paramref name="yaw"/>.</summary>
        private void FreezeOthers(Inhabitant except, float yaw)
        {
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                if (h != except)
                {
                    h.Pin(h.Routine.Position, yaw);
                }
            }
        }

        private int CountNoises(NoiseKind kind)
        {
            int n = 0;
            foreach (NoiseEvent e in noises)
            {
                n += e.Kind == kind ? 1 : 0;
            }
            return n;
        }

        private NoiseEvent LastNoise(NoiseKind kind)
        {
            for (int i = noises.Count - 1; i >= 0; i--)
            {
                if (noises[i].Kind == kind)
                {
                    return noises[i];
                }
            }
            Assert.Fail($"no {kind} noise event");
            return default;
        }

        // =====================================================================================================
        // ----- 28: the stool (CONTRACT_M4 2.1) -----
        // =====================================================================================================

        // Level 1: the stool runs along z = -2.2 toward +x from here, reaching 2.4 m/s near x = -1.2 (clear floor).
        private static readonly Vector3 StoolRunStart = new Vector3(-3.0f, 0f, -2.2f);

        /// <summary>
        /// Drives the stool from <see cref="StoolRunStart"/> toward +x to full speed, recording the tell on every step,
        /// then releases the input. Returns where it tipped. A reactive listener faces away at <paramref name="listener"/>.
        /// </summary>
        private IEnumerator RunAndRelease(Vector3 listener, Action<Vector3> tipped, List<(float speed, bool tell, bool rattle)> tell = null)
        {
            UseBody("stool");
            Furniture.Teleport(StoolRunStart, 90f);
            Habitant.Pin(listener, 90f, 0f, true);
            yield return Steps(2);
            Assert.IsFalse(Game.Seen, "premise: the listener faces away from the run");
            int alertsBefore = Game.AlertCount;
            float nearest = float.MaxValue;
            Furniture.ScriptedDirection = Vector3.right;
            yield return StepUntil(() => Furniture.PlanarSpeed >= Furniture.Body.MaxSpeed - 0.05f && Furniture.transform.position.x >= -1.2f,
                StepsFor(3f), () =>
                {
                    nearest = Mathf.Min(nearest, Planar(Furniture.transform.position, listener));
                    tell?.Add((Furniture.PlanarSpeed, Furniture.TellActive, Game.Sfx.RattleActive));
                    Assert.IsFalse(Game.Seen, "the listener saw the stool run");
                });
            Assert.GreaterOrEqual(Furniture.PlanarSpeed, Furniture.Body.MaxSpeed - 0.05f, "premise: the stool never reached full speed");
            Assert.IsFalse(Furniture.Tipped, "the stool tipped while the input was held on a clear floor");
            Assert.Greater(nearest, Tuning.HopNoiseRadius, "premise: the run passes within hop range of the listener");
            Assert.AreEqual(alertsBefore, Game.AlertCount, "premise: a hop of the run was heard");
            Furniture.ScriptedDirection = null;
            yield return Steps(1);
            Assert.IsTrue(Furniture.Tipped, $"released at {Furniture.Body.MaxSpeed} m/s, the stool did not tip");
            tipped(YawMath.Planar(Furniture.transform.position));
        }

        /// <summary>
        /// Step 28: released at full speed the stool tips; its fall lasts 0.3 s and counts as moving; then a Topple
        /// noise event of radius 3.5 m alerts an inhabitant in Routine 3.3 m away. The tell (and its rattle) shows on
        /// exactly the steps above 1.3 m/s.
        /// </summary>
        [UnityTest]
        public IEnumerator Step28_StoolTipsWhenReleasedFastAndIsHeard()
        {
            var listener = new Vector3(1.9f, 0f, -1.0f);
            Vector3 tipAt = default;
            var tell = new List<(float speed, bool tell, bool rattle)>();
            int topples = Furniture.ToppleCount;
            int played = Game.Sfx.TopplesPlayed;
            yield return RunAndRelease(listener, p => tipAt = p, tell);
            int alertsBefore = Game.AlertCount;
            int falling = 0;
            int toppleStep = -1;
            for (int k = 0; k < StepsFor(Tuning.StoolFallTime) + 10; k++)
            {
                yield return new WaitForFixedUpdate();
                if (Furniture.IsMoving)
                {
                    falling++;
                    Assert.Less(Planar(Furniture.transform.position, tipAt), 1e-3f, "the falling stool travelled");
                }
                if (toppleStep < 0 && Furniture.ToppleCount != topples)
                {
                    toppleStep = k;
                }
            }
            float d = Planar(tipAt, listener);
            Debug.Log($"[Step28] tipped at ({tipAt.x:0.00}, {tipAt.z:0.00}), {d:0.00} m from the listener; fall {falling} moving steps, topple on step {toppleStep}");
            Assert.LessOrEqual(d, Tuning.ToppleNoiseRadius - 0.1f, "premise: the listener must be within the topple radius");
            // The release step is the fall's first step (counted by RunAndRelease's caller as already past).
            Assert.AreEqual(StepsOf(Tuning.StoolFallTime) - 1, falling, 0, "the fall does not count as moving for 0.3 s");
            Assert.IsFalse(Furniture.IsMoving, "the stool lying on its side still counts as moving");
            Assert.AreEqual(topples + 1, Furniture.ToppleCount, "one topple");
            Assert.AreEqual(1, CountNoises(NoiseKind.Topple), "one Topple noise event");
            NoiseEvent e = LastNoise(NoiseKind.Topple);
            Assert.AreEqual(Tuning.ToppleNoiseRadius, e.Radius, 1e-5f, "topple radius");
            Assert.Less(Planar(e.Position, tipAt), 0.05f, "the topple is not where the stool fell");
            Assert.AreEqual(alertsBefore + 1, Game.AlertCount, "the topple was not heard within 3.5 m");
            Assert.AreEqual(InhabitantMode.Alerted, Habitant.Mode, "the listener in Routine is not alerted by the topple");
            Assert.AreEqual(played + 1, Game.Sfx.TopplesPlayed, "the topple sound did not play once");

            // M4.1 (CONTRACT_M4 10.3): the tell is a warning band. It shows on every step clearly above the tell speed
            // (1.0 m/s), so it is on for the 0.25 s climb to the tip speed (1.3 m/s), and on none clearly below.
            int above = 0, below = 0, band = 0;
            foreach ((float speed, bool on, bool rattle) in tell)
            {
                Assert.AreEqual(on, rattle, $"the rattle loop does not follow the tell at {speed:0.00} m/s");
                if (speed > Tuning.StoolTellSpeed + 0.02f)
                {
                    above++;
                    band += speed < Tuning.StoolTipSpeed ? 1 : 0;
                    Assert.IsTrue(on, $"no tell at {speed:0.00} m/s");
                }
                else if (speed < Tuning.StoolTellSpeed - 0.02f)
                {
                    below++;
                    Assert.IsFalse(on, $"the tell shows at {speed:0.00} m/s");
                }
            }
            Assert.Greater(above, 20, "premise: too few steps above the tell speed");
            Assert.GreaterOrEqual(below, 2, "premise: too few steps below the tell speed");
            Assert.GreaterOrEqual(band, StepsOf(0.25f) - 2, "the warning band (tell on, below the tip speed) is shorter than 0.25 s");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertNoErrors();
        }

        /// <summary>Step 28b: the same topple 3.9 m or more away is not heard (the event still fires).</summary>
        [UnityTest]
        public IEnumerator Step28b_StoolToppleUnheardBeyondItsRadius()
        {
            var listener = new Vector3(2.6f, 0f, -0.6f);
            Vector3 tipAt = default;
            yield return RunAndRelease(listener, p => tipAt = p);
            int alertsBefore = Game.AlertCount;
            yield return Steps(StepsFor(Tuning.StoolFallTime) + 10);
            float d = Planar(tipAt, listener);
            Assert.GreaterOrEqual(d, Tuning.ToppleNoiseRadius + 0.1f, "premise: the listener must be beyond the topple radius");
            Assert.AreEqual(1, CountNoises(NoiseKind.Topple), "premise: the topple noise event fired");
            Assert.AreEqual(alertsBefore, Game.AlertCount, $"a topple {d:0.00} m away was heard");
            Assert.AreEqual(InhabitantMode.Routine, Habitant.Mode);
            AssertNoErrors();
        }

        /// <summary>Step 28c: in careful mode the stool never passes 1.2 m/s, never shows the tell and never tips on release.</summary>
        [UnityTest]
        public IEnumerator Step28c_CarefulStoolNeverTips()
        {
            UseBody("stool");
            Furniture.Teleport(StoolRunStart, 90f);
            Habitant.Pin(new Vector3(2.2f, 0f, -0.7f), 90f);
            yield return Steps(2);
            int topples = Furniture.ToppleCount;
            InputReader.InjectCareful(true);
            Furniture.ScriptedDirection = Vector3.right;
            float top = 0f;
            bool tell = false, careful = false;
            for (int k = 0; k < StepsFor(2f); k++)
            {
                yield return new WaitForFixedUpdate();
                top = Mathf.Max(top, Furniture.PlanarSpeed);
                tell |= Furniture.TellActive;
                careful |= Furniture.Careful;
            }
            Assert.IsTrue(careful, "premise: careful mode never engaged");
            Assert.Greater(top, Tuning.StoolTipSpeed * Tuning.CarefulFactor * 1.5f, "premise: the careful stool barely moved");
            Assert.LessOrEqual(top, Furniture.Body.MaxSpeed * Tuning.CarefulFactor + 1e-3f, "careful mode is faster than half speed");
            Assert.Less(top, Tuning.StoolTipSpeed, "careful mode reaches the tip speed");
            // M4.1: careful speed (1.2 m/s) is inside the warning band (from 1.0 m/s), so the tell may show; it never tips.
            Debug.Log($"[Step28c] careful top speed {top:0.00} m/s, tell shown {tell}");
            Furniture.ScriptedDirection = null;
            yield return Steps(StepsFor(Tuning.StoolFallTime) + 10);
            Assert.IsFalse(Furniture.Tipped, "the careful stool tipped on release");
            Assert.AreEqual(topples, Furniture.ToppleCount);
            Assert.AreEqual(0, CountNoises(NoiseKind.Topple), "a topple noise in careful mode");
            AssertNoErrors();
        }

        /// <summary>
        /// Step 28d: a head-on wall hit tips the stool while the input is still held, at full speed; the same wall hit
        /// at careful speed does not.
        /// </summary>
        [UnityTest]
        public IEnumerator Step28d_StoolHeadOnWallHitTips()
        {
            UseBody("stool");
            Habitant.Pin(new Vector3(2.2f, 0f, -0.7f), 90f);
            var start = new Vector3(0.5f, 0f, -1.2f);

            // Careful: it reaches the wall slower than the threshold and stays up.
            Furniture.Teleport(start, 270f);
            yield return Steps(2);
            InputReader.InjectCareful(true);
            Furniture.ScriptedDirection = Vector3.left;
            float lastX = float.MaxValue;
            int still = 0;
            yield return StepUntil(() => still >= 10 || Furniture.Tipped, StepsFor(6f), () =>
            {
                float x = Furniture.transform.position.x;
                still = Mathf.Abs(x - lastX) < 1e-4f ? still + 1 : 0;
                lastX = x;
            });
            Assert.GreaterOrEqual(still, 10, "premise: the careful stool never reached the wall");
            Assert.Less(Furniture.transform.position.x, -3.4f, "premise: stopped before the wall");
            Assert.IsFalse(Furniture.Tipped, "a careful wall hit tipped the stool");
            Furniture.ScriptedDirection = null;
            InputReader.InjectCareful(false);
            yield return Steps(3);

            // Full speed: it tips on the hit, with the input still held.
            Furniture.Teleport(start, 270f);
            yield return Steps(2);
            int topples = Furniture.ToppleCount;
            float top = 0f;
            Furniture.ScriptedDirection = Vector3.left;
            yield return StepUntil(() => Furniture.Tipped, StepsFor(5f), () => top = Mathf.Max(top, Furniture.PlanarSpeed));
            Assert.IsTrue(Furniture.Tipped, "a head-on wall hit at speed did not tip the stool");
            Assert.IsNotNull(Furniture.ScriptedDirection, "premise: the input is still held");
            Assert.Greater(top, Tuning.StoolTipSpeed + 0.3f, $"premise: the stool hit the wall at only {top:0.00} m/s");
            Assert.Less(Furniture.transform.position.x, -3.4f, "premise: the stool tipped before the wall");
            yield return Steps(StepsFor(Tuning.StoolFallTime) + 5);
            Assert.AreEqual(topples + 1, Furniture.ToppleCount, "the wall tip did not topple");
            Assert.AreEqual(1, CountNoises(NoiseKind.Topple), "no Topple noise for the wall tip");
            Furniture.ScriptedDirection = null;
            AssertNoErrors();
        }

        /// <summary>
        /// Step 28e: a tipped stool lies still on its side, not moving, until a move key is pressed (2 s without one);
        /// the press rights it in 0.4 s, which counts as moving, without travelling.
        /// </summary>
        [UnityTest]
        public IEnumerator Step28e_TippedStoolStaysDownUntilAKey()
        {
            Vector3 tipAt = default;
            yield return RunAndRelease(new Vector3(2.2f, 0f, 0.6f), p => tipAt = p);
            Habitant.Pin(new Vector3(2.2f, 0f, 0.6f), 90f);
            yield return Steps(StepsFor(Tuning.StoolFallTime) + 5);
            Assert.IsTrue(Furniture.Tipped, "premise: the stool is down");
            Assert.IsFalse(FurnitureMemory.WithinTolerance(Furniture.Pose, Game.MemoryOf(Habitant).PlayerSlot),
                "premise: the stool lies away from where it belongs (its ghost would show)");
            Vector3 lying = Furniture.transform.position;
            for (int k = 0; k < StepsFor(2f); k++)
            {
                yield return new WaitForFixedUpdate();
                Assert.IsTrue(Furniture.Tipped, $"the stool got up by itself after {k * Dt:0.00} s");
                Assert.IsFalse(Furniture.IsMoving, "a stool lying still counts as moving");
                Assert.IsFalse(Furniture.ActionActive, "an action runs on a stool lying still");
                // M4.1 (CONTRACT_M4 10.3): the HUD says how to get up, and no ghost points at a place meanwhile.
                Assert.IsTrue(main.Hud.TippedVisible, "no tipped line on the HUD while the stool lies");
                Assert.IsFalse(Game.Ghost.Visible, "the remembered-pose ghost shows while the stool lies");
                Assert.IsFalse(Game.Ghost.RingsVisible, "the decoy rings show while the stool lies");
            }
            Assert.Less(Planar(Furniture.transform.position, lying), 1e-4f, "the lying stool moved");
            Assert.IsTrue(main.Hud.Labels.TryGetValue("TippedLine", out UnityEngine.UI.Text line) && line.text == Strings.HudTipped,
                "the tipped line does not carry hud.tipped");

            InputReader.InjectMovePress();
            int righting = 0;
            yield return StepUntil(() => !Furniture.Tipped && !Furniture.ActionActive, StepsFor(Tuning.StoolRightTime) + 15, () =>
            {
                if (Furniture.IsMoving)
                {
                    righting++;
                }
            });
            Assert.IsFalse(Furniture.Tipped, "a move key did not right the stool");
            Assert.AreEqual(StepsOf(Tuning.StoolRightTime), righting, 0, "the righting does not count as moving for 0.4 s");
            Assert.Less(Planar(Furniture.transform.position, lying), 1e-3f, "the righting moved the stool");
            yield return Steps(2);
            Assert.IsFalse(Furniture.IsMoving, "the righted stool keeps moving");
            Assert.IsFalse(main.Hud.TippedVisible, "the tipped line outlived the righting");
            Assert.IsTrue(Game.Ghost.Visible, "upright and out of place, the ghost does not come back");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertNoErrors();
        }

        /// <summary>
        /// Step 28f: tipped within 0.75 m of where it belongs, the stool lying down is still out of place: seen, it is
        /// Suspect for the grace, then a discovery.
        /// </summary>
        [UnityTest]
        public IEnumerator Step28f_StoolSeenLyingDownIsOutOfPlace()
        {
            UseBody("stool");
            Vector3 spawn = Game.Def.Player.Position;
            Furniture.Teleport(new Vector3(-1.0f, 0f, spawn.z), 270f);
            Habitant.Pin(new Vector3(2.2f, 0f, 0.6f), 90f);
            yield return Steps(2);
            Furniture.ScriptedDirection = Vector3.left;
            yield return StepUntil(() => Furniture.transform.position.x <= spawn.x + 0.42f, StepsFor(3f));
            Assert.Greater(Furniture.PlanarSpeed, Tuning.StoolTipSpeed + 0.2f, "premise: too slow to tip");
            Furniture.ScriptedDirection = null;
            yield return Steps(StepsFor(Tuning.StoolFallTime) + 5);
            Assert.IsTrue(Furniture.Tipped, "premise: the stool did not tip");
            FurnitureMemory memory = Game.MemoryOf(Habitant);
            Assert.IsTrue(FurnitureMemory.WithinTolerance(Furniture.Pose, memory.PlayerSlot),
                "premise: upright, the stool would stand where it belongs");
            Assert.AreEqual(0, Game.DiscoveryCount);

            var eye = new Vector3(0.2f, 0f, -2.0f);
            Habitant.Pin(eye, YawToward(eye, Furniture.transform.position), 0f, true);
            int grace = Mathf.RoundToInt(Tuning.DiscoveryGrace / Dt);
            for (int k = 1; k < grace; k++)
            {
                yield return new WaitForFixedUpdate();
                Assert.IsTrue(Game.Seen, "premise: the inhabitant sees the stool lying down");
                Assert.AreEqual(Observation.Suspect, Game.LastObservationOf(Habitant), $"not Suspect after {k * Dt:0.00} s lying in sight");
                Assert.IsTrue(Game.OutOfPlace, "a stool lying down is not out of place");
                Assert.AreEqual(0, Game.DiscoveryCount, "a discovery before the grace");
            }
            yield return Steps(1);
            Assert.AreEqual(1, Game.DiscoveryCount, "seen lying down for the grace, the stool is no discovery");
            Assert.AreEqual(InhabitantMode.Investigating, Habitant.Mode, "the discovery does not send the inhabitant to the stool");
            AssertNoErrors();
        }

        // =====================================================================================================
        // ----- 30: the floor lamp (CONTRACT_M4 2.3, amendment 9.1) -----
        // =====================================================================================================

        // Level 1: from the lamp at the spawn, a clear line 15 deg left of +x (between the sofa and the table).
        private static readonly Vector3 LampLine = new Vector3(Mathf.Cos(15f * Mathf.Deg2Rad), 0f, Mathf.Sin(15f * Mathf.Deg2Rad));

        private Vector3 LampAt => YawMath.Planar(Furniture.transform.position);

        /// <summary>Switches the lamp with an injected E press while every inhabitant is frozen facing away.</summary>
        private IEnumerator ToggleUnseen(bool expectOn)
        {
            Habitant.Pin(LampAt + LampLine * 6f, YawToward(LampAt, LampAt + LampLine * 7f));
            yield return Steps(1);
            Assert.IsFalse(Game.Seen, "premise: the lamp is switched where nobody looks");
            int toggles = Furniture.ToggleCount;
            InputReader.InjectAction();
            yield return StepUntil(() => Furniture.ToggleCount != toggles && !Furniture.ActionActive, StepsFor(Tuning.LampToggleTime) + 20);
            Assert.AreEqual(toggles + 1, Furniture.ToggleCount, "E did not switch the lamp");
            Assert.AreEqual(expectOn, Furniture.Lamp.On, "the lamp is not in the state the switch should give");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: the switch was seen");
        }

        /// <summary>
        /// Step 30: switched on, the lamp is seen at 6 m (premise); switched off, every inhabitant's range for it is
        /// 0.4 x 10 = 4 m: not seen at 6 m, seen at 3 m.
        /// </summary>
        [UnityTest]
        public IEnumerator Step30_DarkLampIsSeenOnlyUpClose()
        {
            UseBody("floor_lamp");
            Assert.IsNotNull(Furniture.Lamp, "premise: the lamp body has no light");
            Assert.IsTrue(Furniture.Lamp.On, "premise: the lamp starts switched on");
            Vision vision = Game.Level.Visions.Find(v => v != null && v.Owner == Habitant);
            Assert.IsNotNull(vision);
            Vector3 lamp = LampAt;

            Habitant.Pin(lamp + LampLine * 6f, YawToward(lamp + LampLine * 6f, lamp));
            yield return Steps(2);
            Assert.IsTrue(Game.Seen, "premise: switched on, the lamp must be seen at 6 m");
            Assert.AreEqual(1f, vision.RangeFactor, 1e-5f);

            yield return ToggleUnseen(false);
            Habitant.Pin(lamp + LampLine * 6f, YawToward(lamp + LampLine * 6f, lamp));
            yield return Steps(2);
            Assert.AreEqual(Tuning.LampOffLight, vision.RangeFactor, 1e-5f, "the dark lamp does not scale the range");
            Assert.IsFalse(Game.Seen, "switched off, the lamp is seen at 6 m");
            Habitant.Pin(lamp + LampLine * 4.5f, YawToward(lamp + LampLine * 4.5f, lamp));
            yield return Steps(2);
            Assert.IsFalse(Game.Seen, "switched off, the lamp is seen at 4.5 m (range 4 m)");
            Habitant.Pin(lamp + LampLine * 3f, YawToward(lamp + LampLine * 3f, lamp));
            yield return Steps(2);
            Assert.IsTrue(Game.Seen, "switched off, the lamp is not seen at 3 m");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertNoErrors();
        }

        /// <summary>Step 30b: the switch's click is a noise event of radius 2.5 m: heard at 2.3 m, not at 2.8 m.</summary>
        [UnityTest]
        public IEnumerator Step30b_LampClickHeardWithinItsRadius()
        {
            UseBody("floor_lamp");
            Vector3 lamp = LampAt;
            int clicks = Game.Sfx.ClicksPlayed;
            foreach ((float distance, bool heard) in new[] { (2.3f, true), (2.8f, false) })
            {
                Vector3 at = lamp + Vector3.right * distance;
                Habitant.Pin(at, 90f, 0f, true);
                yield return Steps(2);
                Assert.IsFalse(Game.Seen, "premise: the listener faces away from the lamp");
                Assert.AreEqual(InhabitantMode.Routine, Habitant.Mode, "premise: the listener is in Routine");
                int alerts = Game.AlertCount;
                int events = CountNoises(NoiseKind.Click);
                InputReader.InjectAction();
                yield return Steps(3);
                Assert.AreEqual(events + 1, CountNoises(NoiseKind.Click), "the switch made no Click noise event");
                NoiseEvent e = LastNoise(NoiseKind.Click);
                Assert.AreEqual(Tuning.LampClickRadius, e.Radius, 1e-5f, "click radius");
                Assert.Less(Planar(e.Position, lamp), 0.05f, "the click is not at the lamp");
                Assert.AreEqual(heard ? alerts + 1 : alerts, Game.AlertCount, $"click at {distance} m: heard {!heard}");
                yield return Steps(StepsFor(Tuning.LampToggleTime) + 2);
                Assert.AreEqual(PlayState.Playing, Game.State);
            }
            Assert.AreEqual(clicks + 2, Game.Sfx.ClicksPlayed, "the click sound did not play on each switch");
            AssertNoErrors();
        }

        /// <summary>
        /// Step 30c: an inhabitant in Routine who cannot see the dark lamp (6 m) does nothing; at 3 m it sees it, walks
        /// over and switches it on after a 0.5 s beat, with no discovery (the lamp is where it belongs).
        /// </summary>
        [UnityTest]
        public IEnumerator Step30c_InhabitantWhoSeesTheDarkLampSwitchesItOn()
        {
            UseBody("floor_lamp");
            Vector3 lamp = LampAt;
            yield return ToggleUnseen(false);
            int clickEvents = CountNoises(NoiseKind.Click);
            int clicks = Game.Sfx.ClicksPlayed;

            Habitant.Pin(lamp + LampLine * 6f, YawToward(lamp + LampLine * 6f, lamp), 0f, true);
            yield return Steps(StepsFor(1f));
            Assert.IsFalse(Game.Seen, "premise: the dark lamp is out of sight at 6 m");
            Assert.IsFalse(Game.SwitchOnPending(Habitant), "an inhabitant who never saw the dark lamp comes to switch it on");
            Assert.AreEqual(InhabitantMode.Routine, Habitant.Mode);

            Habitant.Pin(lamp + LampLine * 3f, YawToward(lamp + LampLine * 3f, lamp), 0f, true);
            yield return Steps(2);
            Assert.IsTrue(Game.Seen, "premise: the dark lamp is in sight at 3 m");
            Assert.IsTrue(Game.SwitchOnPending(Habitant), "seeing the dark lamp did not send the inhabitant to it");
            Assert.AreEqual(InhabitantMode.Investigating, Habitant.Mode);

            // Per step: the beat in front of the lamp, and where the inhabitant stands when the lamp comes on.
            int beat = 0;
            int walked = 0;
            float reachAtSwitch = -1f;
            bool beatThenOn = false;
            RoutineActivity previous = RoutineActivity.Idle;
            InhabitantRoutine routine = Habitant.Routine;
            void OnStep()
            {
                beat += routine.LastActivity == RoutineActivity.SwitchingOn ? 1 : 0;
                walked += routine.LastActivity == RoutineActivity.Walking ? 1 : 0;
                if (reachAtSwitch < 0f && Furniture.Lamp.On)
                {
                    reachAtSwitch = Planar(routine.Position, lamp);
                    beatThenOn = previous == RoutineActivity.SwitchingOn || routine.LastActivity == RoutineActivity.SwitchingOn;
                }
                previous = routine.LastActivity;
            }
            Game.FixedStepped += OnStep;
            try
            {
                yield return Run(StepsFor(12f), () => Furniture.Lamp.On || Game.State != PlayState.Playing, 2f);
            }
            finally
            {
                Game.FixedStepped -= OnStep;
            }
            Debug.Log($"[Step30c] switched on at {Game.Elapsed:0.00} s, {reachAtSwitch:0.00} m from the lamp, beat {beat} steps, walked {walked} steps");
            Assert.IsTrue(Furniture.Lamp.On, "the lamp was never switched back on");
            Assert.AreEqual(1, Game.SwitchOnCount);
            Assert.Greater(walked, StepsFor(1f), "premise: the inhabitant did not walk over to the lamp");
            Assert.AreEqual(StepsOf(Tuning.LampSwitchOnTime), beat, 0, "the switch-on beat does not last 0.5 s");
            Assert.IsTrue(beatThenOn, "the lamp did not come on at the end of the beat");
            Assert.LessOrEqual(reachAtSwitch, Tuning.InvestigateReach + Tuning.CarryReachMargin, "switched on from too far");
            Assert.Less(Planar(LampAt, lamp), 1e-3f, "the lamp moved");
            Assert.AreEqual(0, Game.DiscoveryCount, "a lamp where it belongs, switched off, is a discovery");
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.AreEqual(clickEvents, CountNoises(NoiseKind.Click), "the inhabitant's switch made a noise event");
            Assert.AreEqual(clicks + 1, Game.Sfx.ClicksPlayed, "no click sound for the inhabitant's switch");
            AssertNoErrors();
        }

        /// <summary>
        /// Step 30e (CONTRACT_M4 10.4): the switch is a 0.3 s action that counts as moving, and during it the lamp is
        /// seen at the lit range whatever the direction. A watcher at 6 m sees the lit lamp: switching it off there is
        /// caught. And from the dark (unseen at 6 m), switching it on there is caught too.
        /// </summary>
        [UnityTest]
        public IEnumerator Step30e_ToggleInSightIsCaught()
        {
            foreach (bool switchOff in new[] { true, false })
            {
                if (!switchOff)
                {
                    Game.Restart();
                    Game.Rules = GameRules.M4;
                    yield return Steps(2);
                }
                UseBody("floor_lamp");
                Vector3 lamp = LampAt;
                if (!switchOff)
                {
                    yield return ToggleUnseen(false);
                }
                Vision vision = Game.Level.Visions.Find(v => v != null && v.Owner == Habitant);
                Vector3 at = lamp + LampLine * 6f;
                Habitant.Pin(at, YawToward(at, lamp));
                yield return Steps(2);
                string what = switchOff ? "switching the lit lamp off" : "switching the dark lamp on";
                Assert.AreEqual(switchOff, Game.Seen, switchOff ? "premise: the lit lamp must be seen at 6 m" : "premise: the dark lamp must be unseen at 6 m");
                Assert.AreEqual(PlayState.Playing, Game.State);
                Assert.AreEqual(StepsOf(0.3f), StepsOf(Tuning.LampToggleTime), "premise: the toggle is no longer 0.3 s");

                int toggles = Furniture.ToggleCount;
                bool litRange = true;
                int actionSteps = 0;
                InputReader.InjectAction();
                yield return StepUntil(() => Game.State != PlayState.Playing, StepsOf(Tuning.LampToggleTime) + 10, () =>
                {
                    if (Furniture.ActionActive)
                    {
                        actionSteps++;
                        litRange &= Mathf.Abs(vision.RangeFactor - 1f) < 1e-5f;
                    }
                });
                Debug.Log($"[Step30e] {what}: {Game.State} ({Game.LoseReason}) after {actionSteps} action steps");
                Assert.AreEqual(toggles + 1, Furniture.ToggleCount, $"premise: {what} never started");
                Assert.AreEqual(!switchOff, Furniture.Lamp.On, $"{what}: the light did not change at the start");
                Assert.IsTrue(litRange, $"{what}: the range was not the lit range during the switch");
                Assert.AreEqual(PlayState.Caught, Game.State, $"{what} in sight at 6 m was not caught");
                Assert.AreEqual(LoseReason.SeenMoving, Game.LoseReason);
                Assert.LessOrEqual(actionSteps, StepsOf(Tuning.CaughtGrace) + 1, $"{what}: caught later than the grace");
                Assert.Less(StepsOf(Tuning.CaughtGrace), StepsOf(Tuning.LampToggleTime), "premise: the switch is not longer than the grace");
            }
            AssertNoErrors();
        }

        /// <summary>
        /// Step 30f (CONTRACT_M4 2.3, 10.4): a dark lamp that is also out of place is first a discovery and a carry back,
        /// and only then, once seen where it belongs, switched on.
        /// </summary>
        [UnityTest]
        public IEnumerator Step30f_OutOfPlaceDarkLamp()
        {
            UseBody("floor_lamp");
            Vector3 home = Game.Def.Player.Position;
            Vector3 displaced = home + new Vector3(1.2f, 0f, 0f);
            Vector3 post = new Vector3(home.x + 0.6f, 0f, 0.6f);
            // Set up out of sight and out of earshot: frozen inhabitants neither see nor hear.
            Habitant.Pin(new Vector3(2.2f, 0f, -0.7f), 90f);
            Furniture.Teleport(displaced, 0f);
            yield return Steps(1);
            yield return ToggleUnseen(false);
            Assert.Less(Planar(LampAt, displaced), 1e-3f);
            Assert.Greater(Planar(displaced, home), Tuning.DisplacementTolerance, "premise: the lamp is not out of place");
            Assert.LessOrEqual(Planar(post, displaced), Tuning.ViewRange * Tuning.LampOffLight - 0.5f, "premise: the post is beyond the dark range");
            Assert.LessOrEqual(Planar(post, home), Tuning.ViewRange * Tuning.LampOffLight - 0.5f, "premise: the home is beyond the dark range");

            Habitant.Pin(post, 180f, 0f, true);
            int discoveredAt = -1, carriedAt = -1, putDownAt = -1, pendingAt = -1, onAt = -1;
            bool offUntilOn = true;
            Vector3 onPosition = default;
            InhabitantRoutine routine = Habitant.Routine;
            void OnStep()
            {
                int now = fixedSteps;
                if (discoveredAt < 0 && Game.DiscoveryCount > 0)
                {
                    discoveredAt = now;
                }
                if (carriedAt < 0 && Furniture.Carried)
                {
                    carriedAt = now;
                }
                if (carriedAt >= 0 && putDownAt < 0 && !Furniture.Carried)
                {
                    putDownAt = now;
                }
                if (pendingAt < 0 && Game.SwitchOnPending(Habitant))
                {
                    pendingAt = now;
                }
                if (onAt < 0 && Furniture.Lamp.On)
                {
                    onAt = now;
                    onPosition = LampAt;
                }
                offUntilOn &= onAt >= 0 || !Furniture.Lamp.On;
            }
            Game.FixedStepped += OnStep;
            try
            {
                yield return Run(StepsFor(45f), () => Furniture.Lamp.On || Game.State != PlayState.Playing, 3f);
            }
            finally
            {
                Game.FixedStepped -= OnStep;
            }
            Debug.Log($"[Step30f] discovery at step {discoveredAt}, carried {carriedAt}, put down {putDownAt}, sent to switch {pendingAt}, on {onAt}");
            Assert.AreEqual(PlayState.Playing, Game.State, $"lost ({Game.LoseReason})");
            Assert.GreaterOrEqual(discoveredAt, 0, "the out-of-place dark lamp was never discovered");
            Assert.Greater(carriedAt, discoveredAt, "no carry after the discovery");
            Assert.Greater(putDownAt, carriedAt, "the carry never ended");
            Assert.Greater(pendingAt, putDownAt, "the inhabitant came to switch the lamp on before carrying it back");
            Assert.Greater(onAt, pendingAt, "the lamp was never switched on after the carry");
            Assert.IsTrue(offUntilOn, "the lamp came on before the switch-on");
            Assert.Less(Planar(onPosition, home), 0.05f, "the lamp was not switched on where it belongs");
            Assert.AreEqual(1, Game.DiscoveryCount, "the switch-on is a second discovery");
            Assert.AreEqual(1, Game.CarryCount);
            Assert.AreEqual(1, Game.SwitchOnCount);
            AssertNoErrors();
        }

        /// <summary>
        /// Step 28g (CONTRACT_M4 10.6): on a rug every furniture noise is silent. On test_m4_game_sit's rug, a stool
        /// toppling 2.4 m from a listener in Routine (within 3.5 m) and a lamp switched 2.1 m from it (within 2.5 m) make no
        /// noise event and alert nobody; the topple is still heard by the player, muffled.
        /// </summary>
        [UnityTest]
        public IEnumerator Step28g_RugSilencesToppleAndClick()
        {
            yield return LoadSitLevel();
            Watcher.Pin(Watcher.Routine.Position, 90f);
            var rug = new Vector3(-0.5f, 0f, -1.6f);
            var listener = new Vector3(-0.5f, 0f, 0.8f);
            Assert.IsTrue(Game.Level.IsSilentAt(rug), "premise: no rug there");
            Assert.IsFalse(Game.Level.IsSilentAt(new Vector3(-2.5f, 0f, -1.6f)), "premise: the run starts on the hard floor");

            UseBody("stool");
            Furniture.Teleport(new Vector3(-2.5f, 0f, -1.6f), 90f);
            Sitter.Pin(listener, 0f, 0f, true);
            yield return Steps(2);
            Assert.IsFalse(Game.Seen, "premise: the listener faces away");
            Assert.Greater(Planar(listener, new Vector3(-1.4f, 0f, -1.6f)), Tuning.HopNoiseRadius, "premise: the hard floor hops are in earshot");
            int topples = Furniture.ToppleCount;
            int played = Game.Sfx.TopplesPlayed;
            Furniture.ScriptedDirection = Vector3.right;
            yield return StepUntil(() => Furniture.transform.position.x >= rug.x - 0.05f, StepsFor(4f));
            Assert.Greater(Furniture.PlanarSpeed, Tuning.StoolTipSpeed + 0.2f, "premise: too slow to tip");
            Assert.IsTrue(Game.Level.IsSilentAt(Furniture.transform.position), "premise: the release is not on the rug");
            Furniture.ScriptedDirection = null;
            yield return Steps(StepsOf(Tuning.StoolFallTime) + 5);
            Assert.AreEqual(topples + 1, Furniture.ToppleCount, "premise: the stool did not topple");
            Assert.LessOrEqual(Planar(Furniture.transform.position, listener), Tuning.ToppleNoiseRadius - 0.3f, "premise: the topple is beyond its radius");
            Assert.AreEqual(0, CountNoises(NoiseKind.Topple), "a topple on a rug made a noise event");
            foreach (NoiseEvent e in noises)
            {
                Assert.IsFalse(e.Kind == NoiseKind.Hop && Game.Level.IsSilentAt(e.Position), "a hop on the rug made a noise event");
            }
            Assert.AreEqual(0, Game.AlertCount, "a topple on a rug was heard");
            Assert.AreEqual(played + 1, Game.Sfx.TopplesPlayed, "the player does not hear the muffled topple");

            UseBody("floor_lamp");
            Furniture.Teleport(rug + new Vector3(0f, 0f, 0.3f), 0f);
            yield return Steps(1);
            Assert.IsTrue(Game.Level.IsSilentAt(Furniture.transform.position), "premise: the lamp is not on the rug");
            Assert.LessOrEqual(Planar(Furniture.transform.position, listener), Tuning.LampClickRadius - 0.3f, "premise: the click is beyond its radius");
            int toggles = Furniture.ToggleCount;
            InputReader.InjectAction();
            yield return Steps(StepsOf(Tuning.LampToggleTime) + 3);
            Assert.AreEqual(toggles + 1, Furniture.ToggleCount, "premise: the lamp was not switched");
            Assert.AreEqual(0, CountNoises(NoiseKind.Click), "a click on a rug made a noise event");
            Assert.AreEqual(0, Game.AlertCount, "a click on a rug was heard");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertNoErrors();
        }

        // =====================================================================================================
        // ----- 31 to 33: sitting (CONTRACT_M4 3, amendment 9.2) on test_m4_game_sit -----
        // =====================================================================================================

        private Inhabitant Sitter => Game.Level.Inhabitants.Find(h => h.name == "Assis");
        private Inhabitant Watcher => Game.Level.Inhabitants.Find(h => h.name == "Temoin");

        private IEnumerator LoadSitLevel()
        {
            int before = exceptions;
            Game.LoadLevel(SitLevel);
            Game.Rules = GameRules.M4;
            yield return Steps(2);
            Assert.AreEqual(SitLevel, Game.LevelId);
            Assert.AreEqual(before, exceptions, $"{SitLevel} logged errors at boot: " + string.Join(" | ", logged));
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.IsNotNull(Sitter, "premise: no sitter");
            Assert.IsNotNull(Watcher, "premise: no watcher");
            Assert.Less(Planar(Furniture.transform.position, SeatHome), 1e-3f, "premise: the chair starts at its seat home");
            Assert.IsTrue(Furniture.Body.IsSeat, "premise: the chair is a seat");
            Assert.IsTrue(Game.Level.IsSilentAt(SeatHome) && Game.Level.IsSilentAt(PulledTo), "premise: the seat home is on the rug");
        }

        private static InhabitantRig AssertRigged(Inhabitant h)
        {
            Assert.IsNotNull(h.Rig, $"premise: '{h.name}' has no rigged model");
            Assert.IsNotNull(h.Rig.Head, "premise: no head bone");
            Assert.IsNotNull(h.Rig.SitState, "premise: the model has no _Sitting clip");
            return h.Rig;
        }

        private static M4Watcher Watch(Action late)
        {
            var go = new GameObject("M4Watcher");
            var watcher = go.AddComponent<M4Watcher>();
            watcher.Late = late;
            return watcher;
        }

        private static void Unwatch(M4Watcher watcher)
        {
            if (watcher != null)
            {
                watcher.Late = null;
                UnityEngine.Object.Destroy(watcher.gameObject);
            }
        }

        private struct SitRecord
        {
            public RoutineActivity Activity;
            public float Eye;
            public bool Sitting;
            public InhabitantMode Mode;
            public Vector3 Position;
        }

        // test_m4_game_prop: the sofa's center (the prop seat home, LevelDef.ResolveSeats) and its seat front station.
        private const string PropLevel = "test_m4_game_prop";
        private static readonly Vector3 SofaCenter = new Vector3(1.5f, 0f, 1.6f);
        private static readonly Vector3 SofaFront = new Vector3(1.5f, 0f, 0.85f);
        // The floor cone's apex follows the model's eyes during the sit-down within this (CONTRACT_M4 10.2).
        private const float ApexTolerance = 0.1f;
        // The rule slide onto the seat: at most a seat front's 0.8 m over the 25 steps of the sit-down, plus margin.
        private const float SlideStepMax = 0.05f;

        /// <summary>
        /// Step 31, on real data (CONTRACT_M4 3, 10.2): the prop level is loaded through LevelJson, so the seat home of a
        /// "sit": "Sofa" station is the sofa's center. At the moment of sitting the routine slides from the seat front to
        /// that center over the 0.5 s sit-down, with no step jump, while the eye lowers to 1.15 m; through that sit-down
        /// the floor cone's apex (the visual eye) follows the model's eyes within 0.1 m. Seated, the routine's eye, the
        /// visual eye and the model's eyes on the head bone are at 1.15 m, the head along the eye forward. Standing up is a
        /// full 0.6 s telegraph with the eye still low, then a 0.5 s interpolated rise.
        /// </summary>
        [UnityTest]
        public IEnumerator Step31_SittingOnAPropLowersTheEye()
        {
            int before = exceptions;
            Game.LoadLevel(PropLevel);
            Game.Rules = GameRules.M4;
            yield return Steps(2);
            Assert.AreEqual(PropLevel, Game.LevelId);
            Assert.AreEqual(before, exceptions, $"{PropLevel} logged errors at boot: " + string.Join(" | ", logged));
            StationDef sitStation = Game.Def.Inhabitants[0].Stations[1];
            Assert.AreEqual("Sofa", sitStation.Sit, "premise: the station sits on the sofa");
            Assert.IsTrue(sitStation.PropSeat.HasValue, "premise: LevelJson did not resolve the prop seat");
            Assert.Less(Planar(sitStation.PropSeat.Value.Position, SofaCenter), 1e-3f, "the resolved prop seat is not the sofa's center");
            Inhabitant h = Sitter;
            InhabitantRig rig = AssertRigged(h);
            InhabitantRoutine routine = h.Routine;

            var records = new List<SitRecord>();
            int satRecord = -1;
            float worstSlideStep = 0f;
            Vector3 lastPosition = routine.Position;
            void OnStep()
            {
                if (routine.JustSat && satRecord < 0)
                {
                    satRecord = records.Count;
                }
                if (satRecord >= 0 && records.Count - satRecord < StepsOf(Tuning.SitEyeRiseTime) + 2)
                {
                    worstSlideStep = Mathf.Max(worstSlideStep, Planar(routine.Position, lastPosition));
                }
                lastPosition = routine.Position;
                records.Add(new SitRecord { Activity = routine.LastActivity, Eye = routine.EyeHeight, Sitting = routine.IsSitting, Mode = routine.Mode, Position = routine.Position });
            }

            // Per rendered frame: the eyes' offset from the cone apex, in the eye's own frame. Standing it is a fixed
            // offset (the model's eyes stand ahead of the rule point); through the sit-down it must not drift by more
            // than 0.1 m from that, or the cone would leave the face.
            float worstEye = 0f, worstVisual = 0f, worstHead = 0f, worstApex = 0f;
            int seatedFrames = 0, standFrames = 0, sitDownFrames = 0, standingFrames = 0;
            Vector3 standingOffset = Vector3.zero;
            bool sitClip = true;
            Vector3 EyeOffset()
            {
                Vector3 d = YawMath.Planar(rig.EyePosition - h.VisualEyePosition);
                return Quaternion.Euler(0f, -h.VisualEyeYaw, 0f) * d;
            }
            void Late()
            {
                RoutineActivity a = routine.LastActivity;
                bool standing = !h.SeatedPose && rig.Tilt == 0f && Planar(routine.Position, SofaFront) < 0.01f
                    && (a == RoutineActivity.TurningBody || a == RoutineActivity.Waiting || a == RoutineActivity.Idle);
                if (standing && satRecord < 0)
                {
                    standingOffset += EyeOffset();
                    standingFrames++;
                }
                if (satRecord >= 0 && a == RoutineActivity.Sitting && routine.EyeHeight > Tuning.SitEyeHeight + 1e-4f && standingFrames > 0)
                {
                    sitDownFrames++;
                    worstApex = Mathf.Max(worstApex, (EyeOffset() - standingOffset / standingFrames).magnitude);
                }
                if (routine.IsSitting && a != RoutineActivity.Telegraph && Mathf.Abs(routine.EyeHeight - Tuning.SitEyeHeight) < 1e-4f
                    && Mathf.Abs(h.VisualEyeHeight - Tuning.SitEyeHeight) < 1e-4f)
                {
                    seatedFrames++;
                    worstEye = Mathf.Max(worstEye, Mathf.Abs(rig.EyePosition.y - Tuning.SitEyeHeight));
                    worstVisual = Mathf.Max(worstVisual, Mathf.Abs(h.VisualEyePosition.y - Tuning.SitEyeHeight));
                    worstHead = Mathf.Max(worstHead, Vector3.Angle(rig.Head.forward, YawMath.Forward(h.VisualEyeYaw)));
                    sitClip &= rig.CurrentClip == InhabitantRig.Clip.Sit && rig.SeatFitActive;
                }
                if (a == RoutineActivity.StandingUp && rig.CurrentClip == InhabitantRig.Clip.Stand)
                {
                    standFrames++;
                }
            }
            M4Watcher watcher = Watch(Late);
            Game.FixedStepped += OnStep;
            try
            {
                yield return Run(StepsFor(15f), () => records.Count > 0 && records[records.Count - 1].Activity != RoutineActivity.StandingUp
                    && records.Exists(r => r.Activity == RoutineActivity.StandingUp), 1f);
            }
            finally
            {
                Game.FixedStepped -= OnStep;
                Unwatch(watcher);
            }

            int firstStand = records.FindIndex(r => r.Activity == RoutineActivity.StandingUp);
            Vector3 standingMean = standingFrames > 0 ? standingOffset / standingFrames : Vector3.zero;
            Debug.Log($"[Step31] sat at record {satRecord}, stood up at {firstStand} of {records.Count}; slide step max {worstSlideStep:0.000} m; " +
                $"apex drift {worstApex:0.000} m over {sitDownFrames} sit-down frames (standing offset {standingMean.magnitude:0.000} m, {standingFrames} frames); " +
                $"eye {worstEye:0.000} m off, visual {worstVisual:0.0000}, head {worstHead:0.0} deg over {seatedFrames} frames, {standFrames} stand frames");
            Assert.GreaterOrEqual(satRecord, 0, "the inhabitant never sat on the sofa");
            Assert.AreEqual(SitResult.OnProp, routine.LastSitResult, "a prop sit is not OnProp");
            Assert.AreEqual(0, Game.SatOnPlayerCount);
            Assert.IsFalse(Furniture.Pinned, "a prop sit pinned the player");
            Assert.Less(Planar(routine.SeatHome.Position, SofaCenter), 1e-3f, "the prop's seat home is not the sofa's center");

            // The sit-down: the routine slides from the seat front onto the sofa's center, the eye lowers, no jump.
            Assert.Less(Planar(records[satRecord - 1].Position, SofaFront), 0.05f, "premise: the moment of sitting is not at the seat front");
            Assert.LessOrEqual(worstSlideStep, SlideStepMax, $"the routine jumped {worstSlideStep:0.000} m in one step at the moment of sitting");
            Assert.IsTrue(records.Exists(r => r.Sitting && Planar(r.Position, SofaCenter) < 1e-3f), "seated, the routine is not on the sofa's center");
            Assert.Less(records[satRecord].Eye, Tuning.EyeHeight - 1e-3f, "the eye did not start lowering at the moment of sitting");
            Assert.Greater(records[satRecord].Eye, Tuning.SitEyeHeight + 1e-3f, "the eye dropped to 1.15 m in one step");
            Assert.IsTrue(records.Exists(r => r.Sitting && Mathf.Abs(r.Eye - Tuning.SitEyeHeight) < 1e-4f), "the eye never reached 1.15 m");
            Assert.Greater(standingFrames, 5, "premise: too few standing frames at the seat front to measure the eyes' offset");
            Assert.Greater(sitDownFrames, 5, "premise: too few sit-down frames");
            Assert.LessOrEqual(worstApex, ApexTolerance, $"during the sit-down the cone's apex left the model's eyes by {worstApex:0.000} m");

            // Seated.
            Assert.Greater(seatedFrames, 20, "premise: too few seated frames");
            Assert.LessOrEqual(worstVisual, 1e-3f, "the visual eye (floor cone) is not at 1.15 m while seated");
            Assert.LessOrEqual(worstEye, EyeTolerance, $"the model's eyes are {worstEye:0.000} m away from 1.15 m while seated");
            Assert.LessOrEqual(worstHead, HeadTolerance, $"seated, the head left the eye forward by {worstHead:0.0} deg");
            Assert.IsTrue(sitClip, "seated, the rig does not play _Sitting with its seat fit");

            // Standing up: a full telegraph right before it, still seated and low, then the interpolated rise.
            Assert.Greater(firstStand, satRecord, "the inhabitant never stood up");
            int tele = StepsOf(Tuning.TelegraphDuration);
            for (int k = firstStand - tele; k < firstStand; k++)
            {
                Assert.AreEqual(RoutineActivity.Telegraph, records[k].Activity, $"standing up is not telegraphed (record {k - firstStand})");
                Assert.AreEqual(Tuning.SitEyeHeight, records[k].Eye, 1e-4f, "the eye rose during the stand up telegraph");
            }
            Assert.AreNotEqual(RoutineActivity.Telegraph, records[firstStand - tele - 1].Activity, "premise: the telegraph is longer than 0.6 s");
            Assert.Less(records[firstStand].Eye, Tuning.SitEyeHeight + 0.1f, "the eye jumped up on the first stand up step");
            int rise = 0;
            for (int k = firstStand; k < records.Count && records[k].Activity == RoutineActivity.StandingUp; k++)
            {
                rise++;
                if (k > firstStand)
                {
                    Assert.GreaterOrEqual(records[k].Eye, records[k - 1].Eye - 1e-5f, "the eye went down while standing up");
                }
            }
            Assert.AreEqual(StepsOf(Tuning.SitEyeRiseTime), rise, 0, "the stand up does not last 0.5 s");
            Assert.AreEqual(Tuning.EyeHeight, routine.EyeHeight, 1e-4f, "the eye is not back at 1.6 m");
            Assert.Greater(standFrames, 0, "the rig never played _Standing");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertNoErrors();
        }

        /// <summary>
        /// Runs the sit level until the sitter's moment of sitting (or <paramref name="maxSeconds"/>), calling
        /// <paramref name="perStep"/> at the end of every step before it, inside the fixed step (exact timing, as the
        /// designer route replay drives). A step handler must not throw: it adds to <see cref="violations"/>, asserted after.
        /// </summary>
        private IEnumerator UntilSat(float maxSeconds, Action perStep = null)
        {
            InhabitantRoutine routine = Sitter.Routine;
            bool sat = false;
            violations.Clear();
            void OnStep()
            {
                sat |= routine.JustSat;
                if (!sat)
                {
                    perStep?.Invoke();
                }
            }
            void OnSat()
            {
                if (routine.JustSat && satStep < 0)
                {
                    satStep = fixedSteps;
                }
            }
            satStep = -1;
            Game.FixedStepped += OnStep;
            Game.FixedStepped += OnSat;
            try
            {
                yield return Run(StepsFor(maxSeconds), () => sat || Game.State != PlayState.Playing, 2f);
            }
            finally
            {
                Game.FixedStepped -= OnStep;
                Game.FixedStepped -= OnSat;
            }
            Assert.IsEmpty(violations, string.Join(" | ", violations));
            Assert.IsTrue(sat, $"the sitter never reached the moment of sitting ({Game.State}, {Game.LoseReason})");
        }

        // The fixed step count (fixedSteps) of the sitter's moment of sitting.
        private int satStep = -1;

        private readonly List<string> violations = new List<string>();

        private void Check(bool condition, string message)
        {
            if (!condition && violations.Count < 5)
            {
                violations.Add($"t={Game.Elapsed:0.00} s: {message}");
            }
        }

        /// <summary>
        /// Step 32: the chair is home: the sitter sits on it. It is pinned for the dwell: held input does not move it,
        /// it never counts as moving and is not caught although a second inhabitant watches it, the creak gauge stays
        /// constant, every slot is the seat home and the HUD says so. After the release (the first stand up step) a held
        /// key is ignored until the input has been neutral for a step.
        /// </summary>
        [UnityTest]
        public IEnumerator Step32_SatOnFurnitureIsPinnedNotCaughtNotCreaking()
        {
            yield return LoadSitLevel();
            InhabitantRoutine routine = Sitter.Routine;
            Assert.IsTrue(Game.Seen, "premise: the watcher sees the chair at its seat home");
            float gaugeBefore = -1f;
            bool ghost = false;
            yield return UntilSat(15f, () =>
            {
                ghost |= Game.SeatApproach.HasValue && Planar(Game.SeatApproach.Value.Position, SeatHome) < 1e-3f;
                if (Game.Elapsed > Tuning.CreakStartDelay + 0.5f)
                {
                    gaugeBefore = Game.Creak.Value;
                }
            });
            Assert.AreEqual(SitResult.OnPlayer, routine.LastSitResult, "the chair at its seat home was not sat on");
            Assert.IsTrue(ghost, "no seat ghost at the seat home during the approach");
            // M4.1 (CONTRACT_M4 10.7): the seat ghost is warm, the memory ghost cyan; they never read alike.
            Color seatColor = Game.Ghost.SeatGhostColor, memoryColor = Game.Ghost.MemoryGhostColor;
            Assert.Greater(seatColor.r, seatColor.b + 0.3f, $"the seat ghost is not warm ({seatColor})");
            Assert.Greater(memoryColor.b, memoryColor.r + 0.3f, $"premise: the memory ghost is not cyan ({memoryColor})");
            Assert.Greater(gaugeBefore, 0f, "premise: the creak gauge was not filling before the sitting");
            yield return Steps(1);
            Assert.IsTrue(Furniture.Pinned, "sat on, the furniture is not pinned");
            Assert.AreSame(Sitter, Game.Sitter);
            Assert.AreEqual(1, Game.SatOnPlayerCount);
            Assert.IsTrue(main.Hud.SatOnVisible, "no sat-on line on the HUD");
            Assert.IsFalse(Game.SeatApproach.HasValue, "the seat ghost still shows once seated");
            Assert.Less(Planar(Furniture.transform.position, SeatHome), 1e-3f, "the furniture is not at the seat home");
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                Assert.Less(Planar(Game.MemoryOf(h).PlayerSlot.Position, SeatHome), 1e-3f, $"{h.name}'s slot is not the seat home");
            }

            // Pinned, with a key held and a watcher looking: never moving, never caught, the gauge constant.
            Vector3 pinnedAt = Furniture.transform.position;
            float gauge = Game.Creak.Value;
            Furniture.ScriptedDirection = Vector3.right;
            int watched = 0;
            for (int k = 0; k < StepsFor(2.5f); k++)
            {
                yield return new WaitForFixedUpdate();
                Assert.IsTrue(Furniture.Pinned, $"the pin ended after {k * Dt:0.00} s");
                Assert.IsFalse(Furniture.IsMoving, "a pinned furniture counts as moving");
                Assert.Less(Planar(Furniture.transform.position, pinnedAt), 1e-5f, "held input moved the pinned furniture");
                Assert.AreEqual(PlayState.Playing, Game.State, "caught while sat on");
                Assert.AreEqual(gauge, Game.Creak.Value, "the creak gauge moved while sat on");
                Assert.AreEqual(0f, Game.SeenMoving, "seen moving while sat on");
                watched += Game.Seen ? 1 : 0;
            }
            Assert.Greater(watched, StepsFor(2f), "premise: the watcher does not see the sat-on furniture");
            Assert.AreEqual(Observation.Confirmed, Game.LastObservationOf(Watcher), "the watcher does not find the sat-on chair in place");

            // The release, with the key still held: ignored until one neutral step.
            Watcher.Pin(Watcher.Routine.Position, 90f);
            yield return StepUntil(() => !Furniture.Pinned, StepsFor(5f));
            Assert.IsFalse(Furniture.Pinned, "never released");
            Assert.AreEqual(RoutineActivity.StandingUp, routine.LastActivity, "the pin did not release on the first stand up step");
            Assert.IsFalse(main.Hud.SatOnVisible, "the sat-on line outlived the pin");
            for (int k = 0; k < 10; k++)
            {
                yield return new WaitForFixedUpdate();
                Assert.Less(Planar(Furniture.transform.position, pinnedAt), 1e-5f, "a key held through the release moved the furniture");
                Assert.IsFalse(Furniture.IsMoving);
            }
            Furniture.ScriptedDirection = null;
            yield return Steps(1);
            Furniture.ScriptedDirection = Vector3.right;
            yield return Steps(3);
            Furniture.ScriptedDirection = null;
            Assert.Greater(Planar(Furniture.transform.position, pinnedAt), 0.01f, "after a neutral step the input still does nothing");
            yield return Steps(2);
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.AreEqual(0, Game.DiscoveryCount);
            AssertNoErrors();
        }

        /// <summary>
        /// The pratfall and its look, from the moment of sitting: one discovery (+0.34), the 1 s fall on the floor at the
        /// seat home, the stand up, then an Alerted look at the empty seat for 2 s, the eye on the seat home.
        /// </summary>
        private IEnumerator AssertPratfallThenLook()
        {
            InhabitantRoutine routine = Sitter.Routine;
            Assert.AreEqual(SitResult.Pratfall, routine.LastSitResult, "no pratfall without the chair");
            Assert.AreEqual(1, Game.PratfallCount);
            Assert.AreEqual(1, Game.DiscoveryCount, "the pratfall is not one discovery");
            Assert.AreEqual(Tuning.SuspicionPerDiscovery, Game.SuspicionOf(Sitter).Value, 1e-3f, "the pratfall is not +0.34");
            Assert.IsFalse(Furniture.Pinned, "a pratfall pinned the furniture");
            Assert.GreaterOrEqual(satStep, 0, "premise: the moment of sitting was not recorded");
            int fallEnd = -1, looking = 0;
            float worstLook = 0f;
            bool alerted = false;
            int played = Game.Sfx.PratfallsPlayed;
            yield return StepUntil(() => alerted && routine.Mode != InhabitantMode.Alerted, StepsFor(8f), () =>
            {
                if (fallEnd < 0 && routine.LastActivity != RoutineActivity.Pratfall)
                {
                    fallEnd = fixedSteps;
                }
                if (routine.Mode == InhabitantMode.Alerted)
                {
                    alerted = true;
                    if (routine.LastActivity == RoutineActivity.Looking)
                    {
                        looking++;
                        float toward = YawToward(routine.Position, SeatHome);
                        worstLook = Mathf.Max(worstLook, Mathf.Abs(Mathf.DeltaAngle(routine.EyeYaw, toward)));
                    }
                }
                Assert.AreEqual(PlayState.Playing, Game.State, "the pratfall lost the level");
            });
            int fall = fallEnd - satStep;
            Debug.Log($"[Step33] fall {fall} steps, look {looking} steps, eye within {worstLook:0.0} deg of the seat, {Game.DiscoveryCount} discovery");
            Assert.AreEqual(StepsOf(Tuning.PratfallTime), fall, 0, "the pratfall does not last 1 s");
            Assert.IsTrue(alerted, "no Alerted look after the pratfall");
            Assert.AreEqual(StepsOf(Tuning.AlertLookDuration), looking, 1, "the look at the empty seat does not hold 2 s");
            Assert.LessOrEqual(worstLook, 15f, "the look is not at the empty seat");
            Assert.AreEqual(1, Game.DiscoveryCount, "more than the pratfall's discovery");
            Assert.AreEqual(0, Game.SatOnPlayerCount);
            Assert.AreEqual(played, Game.Sfx.PratfallsPlayed, "a second pratfall sound after the moment of sitting");
        }

        /// <summary>Step 33: the chair is missing at the moment of sitting: a pratfall, one discovery, then the look.</summary>
        [UnityTest]
        public IEnumerator Step33_MissingChairIsAPratfall()
        {
            yield return LoadSitLevel();
            Watcher.Pin(Watcher.Routine.Position, 90f);
            Furniture.Teleport(HidingSpot, 0f);
            int sounds = Game.Sfx.PratfallsPlayed;
            yield return UntilSat(15f, () => Check(!Game.Seen, "premise: the hidden chair was seen"));
            Assert.Greater(Planar(Furniture.transform.position, SeatHome), Tuning.SeatHomeTolerance, "premise: the chair is home");
            yield return Steps(1);
            Assert.AreEqual(sounds + 1, Game.Sfx.PratfallsPlayed, "no pratfall sound");
            yield return AssertPratfallThenLook();
            AssertNoErrors();
        }

        /// <summary>
        /// Step 33b, the classic gag: the chair waits at its seat home during the whole approach (seen, in place), and is
        /// driven 1.09 m away on the rug during the back turn (out of sight, silent): the check at the moment of sitting
        /// finds no seat.
        /// </summary>
        [UnityTest]
        public IEnumerator Step33b_ChairPulledAwayDuringTheBackTurn()
        {
            yield return LoadSitLevel();
            Watcher.Pin(Watcher.Routine.Position, 90f);
            InhabitantRoutine routine = Sitter.Routine;
            bool seenHome = false, pulling = false, pulledDuringTurn = false;
            Vector3 toPulled = (PulledTo - SeatHome).normalized;
            yield return UntilSat(15f, () =>
            {
                seenHome |= Game.Seen && Game.LastObservationOf(Sitter) == Observation.Confirmed;
                bool atStation = Planar(routine.Position, SitStation) < 0.01f && routine.SitTargetsPlayer;
                if (!pulling && atStation && routine.LastActivity == RoutineActivity.Telegraph)
                {
                    pulling = true;
                    Furniture.ScriptedDirection = toPulled;
                }
                if (pulling)
                {
                    Check(!Game.Seen, "premise: the chair was seen while pulled away");
                    pulledDuringTurn |= Furniture.IsMoving && (routine.LastActivity == RoutineActivity.Telegraph || routine.LastActivity == RoutineActivity.TurningBody);
                    if (Planar(Furniture.transform.position, PulledTo) < 0.05f)
                    {
                        Furniture.ScriptedDirection = null;
                    }
                }
            });
            Furniture.ScriptedDirection = null;
            Assert.IsTrue(seenHome, "premise: the sitter never saw the chair home during its approach");
            Assert.IsTrue(pulledDuringTurn, "premise: the chair was not pulled during the back turn");
            Assert.AreEqual(0, Game.AlertCount, "premise: the pull on the rug was heard");
            Assert.Greater(Planar(Furniture.transform.position, SeatHome), Tuning.SeatHomeTolerance, "premise: the chair is still home");
            yield return AssertPratfallThenLook();
            AssertNoErrors();
        }

        /// <summary>Step 33c: away during the approach, pushed back home during the back turn: the sitter sits on it.</summary>
        [UnityTest]
        public IEnumerator Step33c_ChairPushedBackInTime()
        {
            yield return LoadSitLevel();
            Watcher.Pin(Watcher.Routine.Position, 90f);
            InhabitantRoutine routine = Sitter.Routine;
            Furniture.Teleport(HidingSpot, 0f);
            bool away = false, back = false;
            yield return UntilSat(15f, () =>
            {
                Check(!(Game.Seen && !back), "premise: the hidden chair was seen");
                bool atStation = Planar(routine.Position, SitStation) < 0.01f && routine.SitTargetsPlayer;
                away |= routine.LastActivity == RoutineActivity.Walking && Planar(Furniture.transform.position, SeatHome) > Tuning.SeatHomeTolerance;
                if (!back && atStation && routine.LastActivity == RoutineActivity.Telegraph)
                {
                    back = true;
                    Furniture.Teleport(SeatHome, 0f);
                }
            });
            Assert.IsTrue(away, "premise: the chair was home during the approach");
            Assert.IsTrue(back, "premise: the chair was never pushed back");
            Assert.AreEqual(SitResult.OnPlayer, routine.LastSitResult, "the chair pushed back in time was not sat on");
            yield return Steps(1);
            Assert.IsTrue(Furniture.Pinned);
            Assert.AreEqual(0, Game.PratfallCount);
            Assert.AreEqual(0, Game.DiscoveryCount);
            AssertNoErrors();
        }

        /// <summary>
        /// Step 33d: the seat check's tolerance is 0.75 m. The chair is put 0.6, 0.7, 0.8, then 0.9 m from its seat home
        /// at the start of the arrival telegraph (bearing 197 from the sit station: out of the cone through the turn):
        /// 0.6 and 0.7 m are sat on, 0.8 and 0.9 m are a pratfall. Sat on, the chair's rule pose snaps to the seat home and
        /// its visual slides there over 0.3 s (CONTRACT_M4 10.7).
        /// </summary>
        [UnityTest]
        public IEnumerator Step33d_SeatCheckToleranceIs075()
        {
            var cases = new[] { (0.6f, SitResult.OnPlayer), (0.7f, SitResult.OnPlayer), (0.8f, SitResult.Pratfall), (0.9f, SitResult.Pratfall) };
            foreach ((float off, SitResult expected) in cases)
            {
                yield return LoadSitLevel();
                Watcher.Pin(Watcher.Routine.Position, 90f);
                InhabitantRoutine routine = Sitter.Routine;
                Vector3 spot = SeatHome + YawMath.Forward(210f) * off;
                bool moved = false;
                yield return UntilSat(15f, () =>
                {
                    bool atStation = Planar(routine.Position, SitStation) < 0.01f && routine.SitTargetsPlayer;
                    if (!moved && atStation && routine.LastActivity == RoutineActivity.Telegraph)
                    {
                        moved = true;
                        Furniture.Teleport(spot, 0f);
                    }
                    Check(!moved || !Game.Seen, "premise: the moved chair was seen before the moment of sitting");
                });
                Assert.IsTrue(moved, "premise: the chair was never moved");
                Assert.AreEqual(off, Planar(spot, SeatHome), 1e-3f);
                Assert.AreEqual(expected, routine.LastSitResult, $"a chair {off} m from its seat home");
                yield return Steps(1);
                if (expected == SitResult.OnPlayer)
                {
                    Assert.IsTrue(Furniture.Pinned, "sat on, not pinned");
                    Assert.Less(Planar(Furniture.transform.position, SeatHome), 1e-3f, "the sat-on chair's rule pose did not snap to the seat home");
                    Assert.AreEqual(0, Game.DiscoveryCount);
                    Assert.IsTrue(Game.SeatSettling, "the chair's visual did not start sliding onto the seat home");
                    float first = -1f, last = -1f;
                    M4Watcher w = Watch(() =>
                    {
                        float d = Planar(Furniture.Visual.position, SeatHome);
                        if (first < 0f)
                        {
                            first = d;
                        }
                        last = d;
                    });
                    try
                    {
                        yield return Run(StepsFor(GameState.SeatSettleTime + 0.2f), null, 1f);
                    }
                    finally
                    {
                        Unwatch(w);
                    }
                    Debug.Log($"[Step33d] {off} m: the visual starts {first:0.000} m from the seat home and ends {last:0.0000} m from it");
                    Assert.Greater(first, 0.5f * off, "the chair's visual jumped onto the seat home");
                    Assert.Less(last, 1e-3f, "the chair's visual never reached the seat home");
                    Assert.IsFalse(Game.SeatSettling, "the visual slide lasts longer than 0.3 s");
                }
                else
                {
                    Assert.IsFalse(Furniture.Pinned);
                    Assert.AreEqual(1, Game.PratfallCount);
                    Assert.IsFalse(Game.SeatSettling, "a pratfall moved the chair's visual");
                }
            }
            AssertNoErrors();
        }

        // =====================================================================================================
        // ----- The HUD hints of the current body (CONTRACT_M4 2) -----
        // =====================================================================================================

        /// <summary>Step 30d: the HUD shows the careful hint for every body under the Bodies rule, the lamp hint for the lamp only.</summary>
        [UnityTest]
        public IEnumerator Step30d_HudShowsTheHintsOfTheCurrentBody()
        {
            Assert.IsTrue(main.Hud.CarefulHintVisible, "no careful hint under the M4 rules");
            Assert.IsFalse(main.Hud.LampHintVisible, "a lamp hint for the chair");
            UseBody("floor_lamp");
            yield return Steps(1);
            Assert.IsTrue(main.Hud.CarefulHintVisible && main.Hud.LampHintVisible, "the lamp body lacks its hints");
            UseBody("stool");
            yield return Steps(1);
            Assert.IsTrue(main.Hud.CarefulHintVisible);
            Assert.IsFalse(main.Hud.LampHintVisible, "the stool shows the lamp hint");
            Game.Rules = GameRules.M2;
            yield return Steps(1);
            Assert.IsFalse(main.Hud.CarefulHintVisible || main.Hud.LampHintVisible, "M4 hints under the M2 rules");
            Assert.IsTrue(main.Hud.Labels.TryGetValue("CarefulHintLabel", out UnityEngine.UI.Text careful) && careful.text == Strings.HudCareful);
            Assert.IsTrue(main.Hud.Labels.TryGetValue("LampHintLabel", out UnityEngine.UI.Text lamp) && lamp.text == Strings.HudLamp);
            Assert.IsTrue(main.Hud.Labels.TryGetValue("SatOnLine", out UnityEngine.UI.Text satOn) && satOn.text == Strings.HudSatOn);
            AssertNoErrors();
        }
    }

    /// <summary>Calls <see cref="Late"/> in LateUpdate after the inhabitants (order 0): the pose that gets rendered.</summary>
    [DefaultExecutionOrder(200)]
    public sealed class M4Watcher : MonoBehaviour
    {
        public Action Late;

        private void LateUpdate()
        {
            Late?.Invoke();
        }
    }
}
