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
    /// Levels v2 task C9 (docs/levels_v2/LEVELS_V2.md D17): the loaded-sit probe, which gates Mamie's sit on the loaded chair
    /// in level 17. The sit-on-the-player rule (CONTRACT_M4 3, 10.7) and the load (CONTRACT_M5 6) were never tested together.
    /// On the fixture test_v2_loaded_sit (never listed in levels.json): the chair carries a vase at its spawn, and Mamie (a
    /// granny) stands in front of it with a "sit": "player" station whose seat home is the spawn, so she sits on it within
    /// 3 s, as in level 17's s0/s1 pair.
    /// <para>Every scenario asserts, through the snap to the seat home, the pin, the stand-up and 1.5 s after the release
    /// (longer than the load's 0.5 s window): the vase never falls (no crash, no Crash noise, no crash sound, no clue); every
    /// rendered frame while sat on, the vase is shown on the chair's visual, inside its footprint, on its top, upright; the
    /// level is not lost (no discovery, no pratfall). A fall is reported with its phase, its time from the moment of sitting
    /// and its |dv|, so the level 17 designer (LV9) can take the fallback. The test never fixes gameplay: it only measures.</para>
    /// <para>Scenario A is level 17's case (the chair untouched at the spawn, so the snap is zero). Scenario B puts the chair
    /// 0.35 m and 10 deg off its seat home first (inside the 0.75 m seat check), so the rule pose really snaps and the visual
    /// really slides under the vase.</para>
    /// As in the other probes, every wait counts fixed steps with a real time guard, every scenario asserts its premise
    /// first, and Time.timeScale is restored in the TearDown.
    /// </summary>
    public sealed class ProbeTestsLoadedSit
    {
        private const float Dt = Tuning.FixedStep;
        private const string LevelId = "test_v2_loaded_sit";

        // test_v2_loaded_sit: the chair's spawn, which is Mamie's seat home.
        private static readonly Vector3 SeatHome = new Vector3(-1f, 0f, -0.5f);
        private const float SeatYaw = 90f;
        // Mamie sits within this of the level start (the task's premise: level 17's s0/s1 pair).
        private const float SitDeadline = 3f;
        // How long the probe keeps watching after the stand-up: longer than the load's window, so a velocity change at the
        // release would still be seen.
        private const float AfterStandUp = 1.5f;
        // Scenario B: where the chair is put before the sit (behind Mamie, out of her cone, inside the seat check).
        private static readonly Vector3 OffSeat = new Vector3(-1f, 0f, -0.85f);
        private const float OffSeatYaw = 100f;
        // Visual tolerances: the vase's base keeps its carried place on the chair within these (no hop while pinned), metres.
        private const float PoseTolerance = 0.03f;
        private const float TopTolerance = 0.03f;
        // The carried vase's lean while sat on stays under this (the rule sway at rest), degrees.
        private const float MaxSeatedTilt = 2f;

        private enum Phase
        {
            Approach,
            Snap,
            Pinned,
            StandUp,
            After,
        }

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;
        private readonly List<NoiseEvent> noises = new List<NoiseEvent>();

        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;

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
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            // The sit must come within 3 s of the build: no held start (C3a), whatever the run's default.
            GameState.HoldStart = false;
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
            GameState.ResetHoldStart();
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

        private static int StepsFor(float seconds) => Mathf.CeilToInt(seconds / Dt);

        private static float Planar(Vector3 a, Vector3 b) => YawMath.Planar(a - b).magnitude;

        private IEnumerator Steps(int count)
        {
            int end = fixedSteps + count;
            float realStart = Time.realtimeSinceStartup;
            while (fixedSteps < end && Time.realtimeSinceStartup - realStart < 60f)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private Inhabitant Mamie => Game.Level.Inhabitants.Find(h => h != null && h.name == "Mamie");

        /// <summary>
        /// The fixture validates (LevelValidator, as parsed from Resources) and loads: one granny whose station 2 sits on
        /// the player at the spawn, the chair a seat carrying a vase whose view rides on the chair's visual.
        /// </summary>
        private IEnumerator LoadFixture()
        {
            var text = Resources.Load<TextAsset>("Levels/" + LevelId);
            Assert.IsNotNull(text, $"premise: no Resources/Levels/{LevelId}.json");
            LevelDef parsed = LevelJson.Parse(text.text);
            List<string> issues = LevelValidator.Validate(parsed);
            Assert.IsEmpty(issues, $"{LevelId} does not validate: " + string.Join(" | ", issues));

            int before = exceptions;
            Game.LoadLevel(LevelId);
            Game.Rules = GameRules.M4;
            Assert.AreEqual(LevelId, Game.Def.Id, "premise: the fixture loaded");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: playing");
            Assert.IsTrue(Game.Started, "premise: the level is held at its start");
            Assert.AreEqual(before, exceptions, $"{LevelId} logged errors at load: " + string.Join(" | ", logged));
            Assert.IsNotNull(Mamie, "premise: no Mamie");
            Assert.AreEqual(1, Game.Level.Inhabitants.Count, "premise: Mamie alone");
            StationDef sit = Game.Def.Inhabitants[0].Stations[1];
            Assert.IsTrue(sit.SitsOnPlayer, "premise: station 2 does not sit on the player");
            Assert.Less(Planar(sit.Seat.Position, SeatHome), 1e-4f, "premise: the seat home is not the spawn");
            Assert.Less(Planar(Game.Def.Player.Position, SeatHome), 1e-4f, "premise: the spawn moved");
            Assert.Less(Planar(Chair.transform.position, SeatHome), 1e-3f, "premise: the chair does not start at its seat home");
            Assert.IsTrue(Chair.Body.IsSeat, "premise: the chair is not a seat");
            Assert.IsNotNull(Game.Load, "premise: the load has no rule");
            Assert.IsNotNull(Game.LoadView, "premise: the load has no visual");
            Assert.AreEqual(LoadView.Vase, Game.LoadView.Kind, "premise: not a vase");
            Assert.IsTrue(Game.CarryingLoad, "premise: the vase is not carried");
            Assert.IsNotNull(Chair.Visual, "premise: the chair has no visual");
            Assert.IsTrue(Game.LoadView.transform.IsChildOf(Chair.Visual), "premise: the vase does not ride on the chair's visual");
            yield return Steps(2);
        }

        /// <summary>Scenario A, level 17's case: the chair untouched at its spawn, Mamie sits on it, the vase holds.</summary>
        [UnityTest]
        public IEnumerator LoadedSit_AtTheSpawn_TheVaseHoldsAndStaysOnTheChair()
        {
            yield return LoadFixture();
            yield return RunTheSit("A", false);
        }

        /// <summary>
        /// Scenario B: the chair 0.35 m and 10 deg off its seat home (inside the seat check, out of Mamie's cone): at the
        /// moment of sitting the rule pose snaps 0.35 m and the visual slides under the vase over 0.3 s; the vase holds.
        /// </summary>
        [UnityTest]
        public IEnumerator LoadedSit_SnappedHome_TheVaseHoldsThroughTheSlide()
        {
            yield return LoadFixture();
            Chair.Teleport(OffSeat, OffSeatYaw);
            yield return Steps(1);
            Assert.Less(Planar(Chair.transform.position, OffSeat), 1e-3f, "premise: the chair is not off its seat home");
            Assert.Less(Planar(OffSeat, SeatHome), Tuning.SeatHomeTolerance - 0.2f, "premise: the off-seat spot is outside the seat check");
            Assert.IsTrue(Game.CarryingLoad, "premise: the teleport dropped the vase");
            yield return RunTheSit("B", true);
        }

        /// <summary>
        /// Runs the sit and its aftermath, recording the load's |dv| per phase on every fixed step and the vase's visual on
        /// every rendered frame, then asserts. <paramref name="snapExpected"/> is true when the chair starts off its seat home.
        /// </summary>
        private IEnumerator RunTheSit(string tag, bool snapExpected)
        {
            Inhabitant mamie = Mamie;
            InhabitantRoutine routine = mamie.Routine;
            int crashesPlayed = Game.Sfx.CrashesPlayed;
            int crashNoises = noises.Count(e => e.Kind == NoiseKind.Crash);
            float start = Game.Elapsed;
            Vector3 fromPose = Chair.transform.position;

            // ----- per fixed step -----
            var peaks = new Dictionary<Phase, float>();
            var counts = new Dictionary<Phase, int>();
            foreach (Phase p in Enum.GetValues(typeof(Phase)))
            {
                peaks[p] = 0f;
                counts[p] = 0;
            }
            Phase phase = Phase.Approach;
            bool sat = false, standSeen = false, lost = false;
            float satAt = -1f;
            SitResult satResult = SitResult.None;
            int snapLeft = 0, afterSteps = 0;
            bool pinnedSeen = false;
            float worstDrift = 0f, worstSpeed = 0f;
            string fall = null;
            float fallDv = 0f;
            void OnStep()
            {
                if (Game.State != PlayState.Playing)
                {
                    lost = true;
                }
                if (!sat && routine.JustSat)
                {
                    sat = true;
                    satAt = Game.Elapsed;
                    satResult = routine.LastSitResult;
                    phase = Phase.Snap;
                    snapLeft = Mathf.RoundToInt(GameState.SeatSettleTime / Dt);
                }
                else if (phase == Phase.Snap)
                {
                    if (--snapLeft <= 0)
                    {
                        phase = Phase.Pinned;
                    }
                }
                if (sat && routine.LastActivity == RoutineActivity.StandingUp)
                {
                    phase = Phase.StandUp;
                    standSeen = true;
                }
                else if (standSeen)
                {
                    phase = Phase.After;
                    afterSteps++;
                }
                pinnedSeen |= Chair.Pinned;
                if (Game.Load != null)
                {
                    bool fellNow = Game.Load.JustFell;
                    if (Game.CarryingLoad || fellNow)
                    {
                        peaks[phase] = Mathf.Max(peaks[phase], Game.Load.DeltaV);
                    }
                    if (fellNow && fall == null)
                    {
                        fallDv = Game.Load.DeltaV;
                        string fromSit = sat ? $"{Game.Elapsed - satAt:+0.00;-0.00} s from the moment of sitting" : "before the sit";
                        fall = $"phase {phase}, t={Game.Elapsed - start:0.00} s ({fromSit}), fall step {Game.Load.FallStep}, " +
                            $"|dv| {fallDv:0.000} m/s (threshold {Tuning.LoadFallDeltaV}), activity {routine.LastActivity}, " +
                            $"pinned {Chair.Pinned}, chair velocity {Chair.Velocity.magnitude:0.000} m/s";
                    }
                }
                counts[phase]++;
                if (sat)
                {
                    worstDrift = Mathf.Max(worstDrift, Planar(Chair.transform.position, SeatHome));
                    worstSpeed = Mathf.Max(worstSpeed, YawMath.Planar(Chair.Velocity).magnitude);
                }
            }

            // ----- per rendered frame, after the seat settle view (order 50) -----
            LoadView view = Game.LoadView;
            Vector3 body = view.BodySize;
            // The vase's carried pose before the sit, in the visual's planar frame: the reference it must keep.
            Vector3 VaseInVisual() => Quaternion.Euler(0f, -Chair.Visual.eulerAngles.y, 0f) * (view.transform.position - Chair.Visual.position);
            Vector3 reference = VaseInVisual();
            float refOutside = Mathf.Max(Mathf.Abs(reference.x) - body.x * 0.5f, Mathf.Abs(reference.z) - body.z * 0.5f);
            int seatedFrames = 0, hiddenFrames = 0, detachedFrames = 0, outsideFrames = 0, offTopFrames = 0, settledFrames = 0;
            float worstTilt = 0f, worstOutside = 0f, worstMoved = 0f, worstTop = 0f, worstVisualOff = 0f;
            float minHead = float.MaxValue;
            Vector3 vaseLocal = Vector3.zero;
            bool slid = false;
            void Late()
            {
                if (!sat || !Game.CarryingLoad || Chair.Visual == null)
                {
                    return;
                }
                bool seated = routine.SittingOnPlayer && Chair.Pinned;
                if (!seated && !standSeen)
                {
                    return;
                }
                seatedFrames++;
                Transform carried = view.Carried;
                bool shown = carried != null && carried.gameObject.activeInHierarchy && !view.Fallen
                    && carried.GetComponentsInChildren<Renderer>(false).Any(r => r.enabled);
                hiddenFrames += shown ? 0 : 1;
                detachedFrames += view.transform.IsChildOf(Chair.Visual) ? 0 : 1;
                // The vase's base in the visual's planar frame: where it was carried before the sit (inside the footprint,
                // on the box top), not moved on the chair by the sit.
                Vector3 local = VaseInVisual();
                float outside = Mathf.Max(Mathf.Abs(local.x) - body.x * 0.5f, Mathf.Abs(local.z) - body.z * 0.5f);
                worstOutside = Mathf.Max(worstOutside, outside);
                float moved = YawMath.Planar(local - reference).magnitude;
                worstMoved = Mathf.Max(worstMoved, moved);
                outsideFrames += moved > PoseTolerance ? 1 : 0;
                float top = Mathf.Abs(local.y - reference.y);
                worstTop = Mathf.Max(worstTop, top);
                offTopFrames += top > TopTolerance ? 1 : 0;
                vaseLocal = local;
                worstTilt = Mathf.Max(worstTilt, view.Tilt.magnitude);
                SeatSettleView settle = Chair.GetComponent<SeatSettleView>();
                bool settling = settle != null && settle.Active;
                slid |= settling;
                if (!settling && seated)
                {
                    settledFrames++;
                    worstVisualOff = Mathf.Max(worstVisualOff, Planar(Chair.Visual.position, SeatHome));
                }
                if (seated && mamie.Rig != null && mamie.Rig.Head != null && carried != null)
                {
                    Vector3 vaseCentre = carried.position + Vector3.up * (Tuning.LoadHeight * 0.5f);
                    minHead = Mathf.Min(minHead, Vector3.Distance(vaseCentre, mamie.Rig.Head.position));
                }
            }

            var go = new GameObject("LoadedSitWatcher");
            LoadedSitWatcher watcher = go.AddComponent<LoadedSitWatcher>();
            watcher.Late = Late;
            Game.FixedStepped += OnStep;
            int cap = fixedSteps + StepsFor(15f);
            float realStart = Time.realtimeSinceStartup;
            try
            {
                while (fixedSteps < cap && !lost && afterSteps < StepsFor(AfterStandUp) && Time.realtimeSinceStartup - realStart < 180f)
                {
                    yield return new WaitForFixedUpdate();
                }
            }
            finally
            {
                Game.FixedStepped -= OnStep;
                watcher.Late = null;
                UnityEngine.Object.Destroy(go);
            }

            string dvLine = string.Join(", ", peaks.Select(kv => $"{kv.Key} {kv.Value:0.000} ({counts[kv.Key]} steps)"));
            string report = $"[LoadedSit:{tag}] sat at {satAt - start:0.00} s ({satResult}), snap {Planar(fromPose, SeatHome):0.000} m, " +
                $"peak |dv| per phase: {dvLine}; threshold {Tuning.LoadFallDeltaV} m/s; fall: {fall ?? "none"}; " +
                $"chair drift {worstDrift:0.0000} m and speed {worstSpeed:0.000} m/s after the sit; " +
                $"visual: {seatedFrames} frames, hidden {hiddenFrames}, detached {detachedFrames}, moved on the chair {outsideFrames} (worst {worstMoved:0.000} m), outside the footprint worst {worstOutside:0.000} m (before the sit {refOutside:0.000}), " +
                $"off top {offTopFrames} (worst {worstTop:0.000} m), tilt max {worstTilt:0.00} deg, settled visual off seat {worstVisualOff:0.0000} m ({settledFrames} frames), " +
                $"slide seen {slid}; vase base in the chair frame ({vaseLocal.x:0.000}, {vaseLocal.y:0.000}, {vaseLocal.z:0.000}); " +
                $"vase centre to Mamie's head min {(minHead == float.MaxValue ? "n/a" : minHead.ToString("0.000"))} m; " +
                $"state {Game.State} ({Game.LoseReason}), discoveries {Game.DiscoveryCount}, crashes {Game.CrashCount}";
            Debug.Log(report);
            TestContext.WriteLine(report);

            // Premises: the sit happened, on the player, in time, and the whole sequence was watched.
            Assert.IsTrue(sat, $"premise: Mamie never sat ({Game.State}, {Game.LoseReason}). {report}");
            Assert.AreEqual(SitResult.OnPlayer, satResult, $"premise: the sit was not on the player. {report}");
            Assert.LessOrEqual(satAt - start, SitDeadline, $"premise: Mamie did not sit within {SitDeadline} s. {report}");
            Assert.IsTrue(pinnedSeen, $"premise: the chair was never pinned. {report}");
            Assert.Greater(counts[Phase.Pinned], StepsFor(2f), $"premise: too few pinned steps. {report}");
            Assert.IsTrue(standSeen, $"premise: Mamie never stood up. {report}");
            Assert.GreaterOrEqual(afterSteps, StepsFor(AfterStandUp), $"premise: the watch stopped early after the stand-up. {report}");
            if (snapExpected)
            {
                Assert.Greater(Planar(fromPose, SeatHome), 0.3f, $"premise: no real snap. {report}");
                Assert.IsTrue(slid, $"premise: the visual never slid to the seat home. {report}");
            }

            // The vase holds: no fall, no crash, no noise, no sound, no clue.
            Assert.IsNull(fall, $"the vase fell: {fall}. {report}");
            Assert.IsTrue(Game.CarryingLoad, $"the vase is no longer carried. {report}");
            Assert.AreEqual(0, Game.CrashCount, $"a crash. {report}");
            Assert.AreEqual(crashNoises, noises.Count(e => e.Kind == NoiseKind.Crash), $"a Crash noise event. {report}");
            Assert.AreEqual(crashesPlayed, Game.Sfx.CrashesPlayed, $"the crash sound played. {report}");
            Assert.IsFalse(Game.ClueActive, $"a clue on the floor. {report}");
            Assert.IsNull(view.Clue, $"a clue object. {report}");
            foreach (Phase p in new[] { Phase.Snap, Phase.Pinned, Phase.StandUp, Phase.After })
            {
                Assert.Less(peaks[p], Tuning.LoadFallDeltaV, $"|dv| reached the fall threshold in phase {p}. {report}");
            }

            // The chair stays under the sitter: at the seat home from the snap on, never moving.
            Assert.Less(worstDrift, 1e-3f, $"the chair left its seat home after the sit. {report}");

            // The vase is shown on the chair on every frame while sat on (and through the stand-up and after).
            Assert.Greater(seatedFrames, 10, $"premise: too few rendered frames while sat on. {report}");
            Assert.AreEqual(0, hiddenFrames, $"the vase was hidden while sat on. {report}");
            Assert.AreEqual(0, detachedFrames, $"the vase left the chair's visual. {report}");
            Assert.AreEqual(0, outsideFrames, $"the vase moved on the chair. {report}");
            Assert.AreEqual(0, offTopFrames, $"the vase's base left the chair's top. {report}");
            Assert.LessOrEqual(worstTilt, MaxSeatedTilt, $"the vase leaned under the sitter. {report}");
            Assert.Greater(settledFrames, 0, $"premise: no settled frame while sat on. {report}");
            Assert.Less(worstVisualOff, 0.01f, $"settled, the chair's visual is not at the seat home under the sitter. {report}");

            // The level is not lost.
            Assert.IsFalse(lost, $"the level was lost. {report}");
            Assert.AreEqual(PlayState.Playing, Game.State, $"the level is not playing. {report}");
            Assert.AreEqual(0, Game.DiscoveryCount, $"a discovery. {report}");
            Assert.AreEqual(0, Game.PratfallCount, $"a pratfall. {report}");
            Assert.AreEqual(1, Game.SatOnPlayerCount, $"not sat on once. {report}");
            Assert.AreEqual(0, exceptions, "errors were logged: " + string.Join(" | ", logged));
        }
    }

    /// <summary>Calls <see cref="Late"/> on every rendered frame, after SeatSettleView (order 50) has placed the chair's visual.</summary>
    [DefaultExecutionOrder(300)]
    public sealed class LoadedSitWatcher : MonoBehaviour
    {
        public Action Late;

        private void LateUpdate()
        {
            Late?.Invoke();
        }
    }
}
