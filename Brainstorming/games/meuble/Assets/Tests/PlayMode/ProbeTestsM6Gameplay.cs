using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace OutOfSight.Tests
{
    /// <summary>
    /// The M6 gameplay probe (docs/CONTRACT_M6.md 2.5 to 2.7), on the real Boot scene under GameRules.M4, with the gameplay
    /// agent's test levels (never in levels.json):
    /// <list type="bullet">
    /// <item>53a to 53c, the wardrobe (test_m6_gameplay_wardrobe: one room, the wardrobe "Armoire" against the north wall
    /// facing -z, a stool spawning at (3.2, -1.0), one watcher): entering and leaving, hidden means no samples and no catch,
    /// an entry seen is a catch after the grace, a chair does not fit; the muffled creak radius; the remembered spot seen
    /// empty.</item>
    /// <item>54a, door memory (test_m6_gameplay_doormemory: test_m5_game_door with "doorMemory"): a leaf seen open when
    /// remembered closed is a Suspect, the watcher walks to it, closes it and resumes; off on test_m5_game_door.</item>
    /// <item>55a, the doors the household opens (test_m6_gameplay_dooropen: test_m5_game_door with porte
    /// "openedByInhabitants"): the walk stops 0.6 s in front of porte while it swings, walks through, porte stays open;
    /// test_m5_game_door's porte keeps blocking as in M5.</item>
    /// </list>
    /// Every wait counts game fixed steps under a real time guard; every scenario asserts its premise first.
    /// </summary>
    public sealed class ProbeTestsM6Gameplay
    {
        private const float Dt = Tuning.FixedStep;
        private const string WardrobeLevel = "test_m6_gameplay_wardrobe";
        private const string DoorMemoryLevel = "test_m6_gameplay_doormemory";
        private const string DoorOpenLevel = "test_m6_gameplay_dooropen";
        private const string M5DoorLevel = "test_m5_game_door";

        private static int WardrobeSteps => Mathf.RoundToInt(Tuning.WardrobeActionTime / Dt);
        private static int DoorSteps => Mathf.RoundToInt(Tuning.DoorOpenTime / Dt);
        private static int StopSteps => Mathf.RoundToInt(Tuning.InhabitantDoorStop / Dt);
        private static int GraceSteps => Mathf.RoundToInt(Tuning.CaughtGrace / Dt);

        // test_m6_gameplay_wardrobe: the front face at z = 3.35; this point is 0.4 m in front of it, centred.
        private static readonly Vector3 Front = new Vector3(0f, 0f, 2.95f);
        private static readonly Vector3 Spawn = new Vector3(3.2f, 0f, -1.0f);

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;
        private readonly List<NoiseEvent> noises = new List<NoiseEvent>();

        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;
        private Hud Hud => main.Hud;

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
            Game.FixedStepped += Record;
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
                main.Game.FixedStepped -= Record;
                main.Game.Noise -= OnNoise;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                    main.Game.Furniture.ScriptedCareful = null;
                }
            }
            yield return null;
        }

        private void Record() => fixedSteps++;

        private void OnNoise(NoiseEvent e) => noises.Add(e);

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        private void AssertClean()
        {
            Assert.AreEqual(0, exceptions, "errors were logged: " + string.Join(" | ", logged));
        }

        private static int StepsFor(float seconds) => Mathf.CeilToInt(seconds / Dt);

        private static float Planar(Vector3 a, Vector3 b) => YawMath.Planar(a - b).magnitude;

        private IEnumerator Steps(int count)
        {
            yield return Until(null, count);
        }

        /// <summary>Waits until <paramref name="until"/> holds after a fixed step, at most <paramref name="maxSteps"/> game steps.</summary>
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

        /// <summary>Runs the game at <paramref name="scale"/> until <paramref name="until"/> holds or <paramref name="maxSteps"/> game steps ran.</summary>
        private IEnumerator Run(int maxSteps, Func<bool> until, float scale)
        {
            int end = fixedSteps + maxSteps;
            float realStart = Time.realtimeSinceStartup;
            Time.timeScale = scale;
            try
            {
                while (fixedSteps < end && (until == null || !until()) && Time.realtimeSinceStartup - realStart < 240f)
                {
                    yield return null;
                }
            }
            finally
            {
                Time.timeScale = 1f;
            }
            Assert.Less(Time.realtimeSinceStartup - realStart, 240f, "the game stopped stepping");
        }

        private IEnumerator Load(string id)
        {
            Game.LoadLevel(id);
            Game.Rules = GameRules.M4;
            Assert.AreEqual(id, Game.Def.Id, "premise: the level loaded");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: playing");
            yield return Steps(2);
        }

        private Vision VisionOf(Inhabitant h) => Game.Level.Visions.Find(v => v != null && v.Owner == h);

        private PropDef TheWardrobe()
        {
            PropDef w = Game.Def.Props.Find(p => p.Kind == WardrobeRule.Kind);
            Assert.IsNotNull(w, "premise: the level has a wardrobe");
            return w;
        }

        private string HideLine => Hud.Labels.TryGetValue("HideHintLine", out Text t) ? t.text : null;

        /// <summary>The stool in front of the wardrobe, then E: waits for the 25 step entry. Returns the moving flags recorded.</summary>
        private IEnumerator EnterWardrobe(List<bool> moving)
        {
            Chair.Teleport(Front, 0f);
            yield return Steps(2);
            Assert.AreSame(TheWardrobe(), Game.WardrobeInReach, "premise: the stool stands in front of the wardrobe");
            void Watch() => moving.Add(Chair.IsMoving);
            Game.FixedStepped += Watch;
            InputReader.InjectAction();
            yield return Until(() => Chair.Hidden, WardrobeSteps + 5);
            Game.FixedStepped -= Watch;
            Assert.IsTrue(Chair.Hidden, "the stool did not hide");
        }

        // =====================================================================================================
        // ----- 53: the wardrobe (CONTRACT_M6 2.5) -----
        // =====================================================================================================

        /// <summary>
        /// Step 53a: E in front of the wardrobe enters it in a 25 step moving action, then the stool is hidden: no visual, no
        /// sample, it cannot move, and a watcher looking at it sees nothing and never catches it; E leaves (visible, moving).
        /// An entry seen is a catch after the grace. A chair does not fit: E does nothing.
        /// </summary>
        [UnityTest]
        public IEnumerator Step53a_EnterAndLeaveTheWardrobe()
        {
            yield return Load(WardrobeLevel);
            Inhabitant h = Game.MainInhabitant;
            Assert.AreEqual(BodyKinds.Stool, Chair.Body.Kind, "premise: the player is the stool");
            // Frozen at (0, -1) facing -z: it sees neither the wardrobe nor the stool's spawn.
            h.Pin(new Vector3(0f, 0f, -1f), 180f);
            Chair.Teleport(Front, 0f);
            yield return Steps(2);
            Assert.IsFalse(Game.Seen, "premise: the entry is unseen");
            Assert.IsTrue(Hud.HideHintVisible, "no wardrobe prompt in front of the wardrobe");
            Assert.AreEqual(Strings.HudHide, HideLine, "the prompt is not hud hide");

            var moving = new List<bool>();
            yield return EnterWardrobe(moving);
            Assert.AreEqual(0, moving.IndexOf(true), "the entry did not start on the press step");
            int run = moving.TakeWhile(m => m).Count();
            Assert.AreEqual(WardrobeSteps, run, $"the entry is {run} moving steps, not {WardrobeSteps}");
            Assert.AreEqual(GameState.WardrobeStage.Hidden, Game.Wardrobe);
            Assert.AreEqual(1, Game.HideCount);
            Assert.IsFalse(Chair.Visual.gameObject.activeSelf, "the hidden stool is still drawn");
            yield return Steps(1);
            Assert.IsTrue(Hud.HideHintVisible, "no prompt while hidden");
            Assert.AreEqual(Strings.HudLeave, HideLine, "the prompt while hidden is not hud leave");

            // The watcher now looks straight at the stool's spot: it would see it if it were not hidden.
            h.Pin(new Vector3(0f, 0f, -1f), 0f);
            yield return Steps(1);
            var samples = new Vector3[Tuning.SampleCount];
            Chair.GetSamplePoints(samples);
            InhabitantRoutine r = h.Routine;
            Assert.IsTrue(Vision.Test(h.EyePosition, h.EyeForward, samples, r.ViewRange, r.HalfAngle, null),
                "premise: the watcher would see the stool's samples");
            Vector3 at = Chair.transform.position;
            Chair.ScriptedDirection = Vector3.back;
            bool seen = false;
            bool seesPlayer = false;
            void Look()
            {
                seen |= Game.Seen;
                seesPlayer |= VisionOf(h).SeesPlayer;
            }
            Game.FixedStepped += Look;
            yield return Steps(GraceSteps * 4);
            Game.FixedStepped -= Look;
            Chair.ScriptedDirection = null;
            Assert.IsFalse(seesPlayer, "the hidden stool has samples");
            Assert.IsFalse(seen, "the hidden stool was seen");
            Assert.AreEqual(PlayState.Playing, Game.State, "the hidden stool was caught");
            Assert.Less(Planar(Chair.transform.position, at), 1e-4f, "the hidden stool moved");
            Assert.IsTrue(Chair.Hidden);

            // E leaves: visible again, a 25 step moving action, here seen: a catch after the grace.
            InputReader.InjectAction();
            yield return Until(() => Game.State != PlayState.Playing, WardrobeSteps + 5);
            Assert.IsFalse(Chair.Hidden, "E did not leave the wardrobe");
            Assert.AreEqual(1, Game.LeaveCount);
            Assert.AreEqual(PlayState.Caught, Game.State, "the exit seen is not a catch");
            Assert.AreEqual(LoseReason.SeenMoving, Game.LoseReason);

            // An entry seen is a catch after the grace, never a hiding.
            Game.Restart();
            yield return Steps(2);
            h = Game.MainInhabitant;
            h.Pin(new Vector3(0f, 0f, -1f), 0f);
            Chair.Teleport(Front, 0f);
            yield return Steps(2);
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: playing after the restart");
            Assert.IsTrue(Game.Seen, "premise: the watcher sees the stool in front of the wardrobe");
            int pressStep = fixedSteps;
            InputReader.InjectAction();
            yield return Until(() => Game.State != PlayState.Playing, WardrobeSteps + 5);
            Assert.AreEqual(PlayState.Caught, Game.State, "the entry seen is not a catch");
            Assert.AreEqual(LoseReason.SeenMoving, Game.LoseReason);
            int caughtAfter = fixedSteps - pressStep;
            Assert.That(caughtAfter, Is.InRange(GraceSteps, GraceSteps + 1), $"caught {caughtAfter} steps after the press, not after the grace");
            Assert.IsFalse(Chair.Hidden, "a caught entry hid the stool");

            // A chair does not fit: E in front of the wardrobe does nothing.
            Game.Restart();
            yield return Steps(2);
            Game.MainInhabitant.Pin(new Vector3(0f, 0f, -1f), 180f);
            Chair.SetBody(BodyDef.For(BodyKinds.Chair));
            Chair.Teleport(Front, 0f);
            yield return Steps(2);
            Assert.IsTrue(WardrobeRule.InFront(TheWardrobe(), Chair.transform.position), "premise: the chair stands in front");
            Assert.IsNull(Game.WardrobeInReach, "a chair may enter the wardrobe");
            Assert.IsFalse(Hud.HideHintVisible, "the prompt shows for a chair");
            InputReader.InjectAction();
            yield return Steps(3);
            Assert.IsFalse(Chair.ActionActive, "E began an action for a chair");
            Assert.IsFalse(Chair.Hidden, "the chair hid");
            Assert.AreEqual(GameState.WardrobeStage.None, Game.Wardrobe);
            AssertClean();
        }

        /// <summary>
        /// Step 53b: hidden, the creak gauge still fills, and the creak is heard within half the creak radius: a listener at
        /// 4.95 m (inside 7 m, outside 3.5 m) is not alerted.
        /// </summary>
        [UnityTest]
        public IEnumerator Step53b_HiddenCreakIsMuffled()
        {
            yield return Load(WardrobeLevel);
            Inhabitant h = Game.MainInhabitant;
            // A listener in Routine (reactive pin) at (0, -2) facing -z: it sees nothing, it may hear.
            h.Pin(new Vector3(0f, 0f, -2f), 180f, 0f, true);
            yield return EnterWardrobe(new List<bool>());
            Vector3 source = YawMath.Planar(Chair.transform.position);
            Vector3 listener = h.Routine.Position;
            float factor = h.Routine.HearingFactor;
            Assert.IsTrue(Hearing.Hears(listener, new NoiseEvent(source, Tuning.CreakRadius, NoiseKind.Creak), factor),
                "premise: the listener would hear an open creak");
            Assert.IsFalse(Hearing.Hears(listener, new NoiseEvent(source, Tuning.CreakRadius * Tuning.WardrobeCreakFactor, NoiseKind.Creak), factor),
                "premise: the listener is outside the muffled radius");
            int creaks = Game.CreakCount;
            int alerts = Game.AlertCount;
            yield return Run(StepsFor(Tuning.CreakStartDelay + Tuning.CreakFillTime + 3f), () => Game.CreakCount > creaks, 20f);
            Assert.AreEqual(creaks + 1, Game.CreakCount, "the hidden stool never creaked");
            NoiseEvent creak = noises.Last(e => e.Kind == NoiseKind.Creak);
            Assert.AreEqual(Tuning.CreakRadius * Tuning.WardrobeCreakFactor, creak.Radius, 1e-4f, "the hidden creak is not muffled");
            Assert.AreEqual(alerts, Game.AlertCount, "the listener heard the muffled creak");
            Assert.AreEqual(InhabitantMode.Routine, h.Mode, "the listener reacted to the muffled creak");
            Assert.IsTrue(Chair.Hidden);
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 53c: hidden, the stool is never seen out of place, but a watcher with memory who sees its remembered spot (the
        /// spawn) empty gets a Suspect, then one discovery after the grace, and investigates the spot; it carries nothing, and
        /// the spot known empty gives no second discovery.
        /// </summary>
        [UnityTest]
        public IEnumerator Step53c_RememberedSpotSeenEmpty()
        {
            yield return Load(WardrobeLevel);
            Inhabitant h = Game.MainInhabitant;
            h.Pin(new Vector3(0f, 0f, -1f), 180f, 0f, true);
            yield return EnterWardrobe(new List<bool>());
            FurnitureMemory memory = Game.MemoryOf(h);
            Assert.Less(Planar(memory.PlayerSlot.Position, Spawn), 1e-3f, "premise: the remembered spot is the spawn");
            Assert.AreEqual(0, Game.EmptySpotCount);
            Assert.AreEqual(0, Game.DiscoveryCount);
            float suspicion = Game.SuspicionOf(h).Value;

            var seen = new List<Observation>();
            float nearest = float.MaxValue;
            void Watch()
            {
                seen.Add(Game.LastObservationOf(h));
                nearest = Mathf.Min(nearest, Planar(h.Routine.Position, Spawn));
            }
            Game.FixedStepped += Watch;
            // Facing +x: the spawn 3.2 m straight ahead, empty.
            h.Pin(new Vector3(0f, 0f, -1f), 90f, 0f, true);
            yield return Until(() => Game.EmptySpotCount > 0, GraceSteps + 10);
            Assert.AreEqual(1, Game.EmptySpotCount, "the empty spot gave no discovery");
            Assert.AreEqual(1, Game.DiscoveryCount);
            Assert.Greater(Game.SuspicionOf(h).Value, suspicion + 0.1f, "the empty spot did not raise the suspicion");
            int first = seen.FindIndex(o => o != Observation.NotSeen);
            Assert.AreEqual(Observation.Suspect, seen[first], "the empty spot is not first a Suspect");
            int suspects = seen.Skip(first).TakeWhile(o => o == Observation.Suspect).Count();
            Assert.AreEqual(GraceSteps - 1, suspects, "the discovery did not come after the grace");
            Assert.AreEqual(InhabitantMode.Investigating, h.Mode, "the watcher does not investigate the spot");

            yield return Until(() => h.Mode != InhabitantMode.Investigating, StepsFor(12f));
            Assert.AreNotEqual(InhabitantMode.Investigating, h.Mode, "the investigation never ended");
            Assert.LessOrEqual(nearest, Tuning.InvestigateReach + 0.05f, "the watcher did not walk to the spot");
            yield return Steps(StepsFor(4f));
            Game.FixedStepped -= Watch;
            Assert.AreEqual(1, Game.EmptySpotCount, "the spot known empty gave a second discovery");
            Assert.IsTrue(memory.SpotKnownEmpty);
            Assert.AreEqual(0, Game.CarryCount, "the hidden stool was carried");
            Assert.IsTrue(Chair.Hidden, "the stool left the wardrobe");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        // =====================================================================================================
        // ----- 54: door memory (CONTRACT_M6 2.6) -----
        // =====================================================================================================

        /// <summary>
        /// Step 54a: porte remembered closed, opened unseen by the chair; the memory watcher then sees it open: a
        /// Suspect (its suspicion rises), it walks to the door, closes it (30 steps, no samples, never a catch) and resumes;
        /// the door seen closed again gives nothing. On test_m5_game_door (no doorMemory) the same sighting gives nothing.
        /// </summary>
        [UnityTest]
        public IEnumerator Step54a_DoorMemoryPutsTheDoorBack()
        {
            yield return Load(DoorMemoryLevel);
            Inhabitant h = Game.MainInhabitant;
            DoorLeaf porte = Game.Level.Leaves[0];
            Vector3 station = new Vector3(3f, 0f, 0.25f);
            h.Pin(station, 90f);
            yield return Steps(2);
            DoorMemory memory = Game.DoorMemoryOf(h);
            Assert.IsNotNull(memory, "premise: the watcher has a door memory");
            Assert.IsFalse(memory.RemembersOpen(0), "premise: porte remembered closed");
            Assert.IsTrue(porte.InReach(Chair), "premise: the chair is in reach of porte");
            InputReader.InjectAction();
            yield return Until(() => porte.Open && !porte.Swinging && !Chair.ActionActive, DoorSteps + 5);
            yield return Steps(2);
            Assert.IsTrue(porte.Open, "premise: the chair opened porte");
            Assert.AreEqual(0, Game.DoorSuspectCount, "premise: nobody saw it");
            float suspicion = Game.SuspicionOf(h).Value;

            bool leafSeen = false;
            int sampled = 0;
            void Watch()
            {
                leafSeen |= Game.LeafSeen;
                sampled = Mathf.Max(sampled, porte.Samples.Length);
            }
            Game.FixedStepped += Watch;
            // In Routine (reactive pin) at its station, facing porte.
            h.Pin(station, 270f, 0f, true);
            yield return Until(() => Game.DoorSuspectCount > 0, 20);
            Assert.AreEqual(1, Game.DoorSuspectCount, "porte seen open gave no Suspect");
            Assert.Greater(Game.SuspicionOf(h).Value, suspicion + 0.1f, "the Suspect did not raise the suspicion");
            Assert.IsTrue(memory.Noticed(0));
            Assert.AreEqual(0, Game.DoorFixOf(h), "the watcher is not on its way to porte");
            Assert.AreEqual(InhabitantMode.Investigating, h.Mode);

            yield return Until(() => !porte.Open, StepsFor(12f));
            Assert.IsFalse(porte.Open, "porte was never put back");
            Assert.IsTrue(porte.Closing && porte.Swinging, "porte does not swing closed");
            Assert.AreEqual(1, Game.DoorPutBackCount);
            Assert.IsFalse(memory.RemembersOpen(0), "the memory is not closed after the put back");
            Assert.IsFalse(memory.Noticed(0));
            float reach = GameState.DoorStopDistance(porte.Geometry, 1f) + Tuning.InvestigateReach + 0.1f;
            Assert.LessOrEqual(h.Routine.Position.x, reach, "the watcher did not walk to porte");
            yield return Until(() => !porte.Swinging, DoorSteps + 5);
            Assert.AreEqual(0f, porte.Angle, 1e-3f, "porte is not closed");
            Assert.AreEqual(DoorSteps, porte.SwingSteps, "the closing is not 30 steps");
            yield return Until(() => h.Mode == InhabitantMode.Routine, 20);
            Assert.AreEqual(InhabitantMode.Routine, h.Mode, "the watcher did not resume");
            yield return Steps(StepsFor(4f));
            Game.FixedStepped -= Watch;
            Assert.AreEqual(1, Game.DoorSuspectCount, "porte closed again gave a Suspect");
            Assert.IsFalse(porte.Open);
            Assert.AreEqual(0, sampled, "the household's swing has samples");
            Assert.IsFalse(leafSeen, "the household's swing was seen as the furniture moving");
            Assert.AreEqual(PlayState.Playing, Game.State);

            // Opt-in: without doorMemory, the same sighting changes nothing.
            yield return Load(M5DoorLevel);
            h = Game.MainInhabitant;
            porte = Game.Level.Leaves[0];
            h.Pin(station, 90f);
            yield return Steps(2);
            Assert.IsNull(Game.DoorMemoryOf(h), "a level without doorMemory has a door memory");
            InputReader.InjectAction();
            yield return Until(() => porte.Open && !porte.Swinging && !Chair.ActionActive, DoorSteps + 5);
            h.Pin(station, 270f, 0f, true);
            yield return Steps(60);
            Assert.AreEqual(0, Game.DoorSuspectCount, "door memory without doorMemory");
            Assert.IsTrue(porte.Open, "porte was closed without doorMemory");
            AssertClean();
        }

        // =====================================================================================================
        // ----- 55: the doors the household opens (CONTRACT_M6 2.7) -----
        // =====================================================================================================

        /// <summary>
        /// Step 55a: the walk from b to a crosses porte (openedByInhabitants, closed): the inhabitant stops 1.25 m in front of
        /// it (the swing side), holds 30 steps while porte swings open (no samples), then walks through; porte stays open. On
        /// test_m5_game_door porte keeps blocking: the station walks leave its doorway out and it stays closed.
        /// </summary>
        [UnityTest]
        public IEnumerator Step55a_InhabitantOpensAnOptInDoor()
        {
            yield return Load(DoorOpenLevel);
            Inhabitant h = Game.MainInhabitant;
            DoorLeaf porte = Game.Level.Leaves[0];
            int bit = 1 << Tuning.DoorAreaBase;
            Assert.IsTrue(Game.Def.Doors[0].OpenedByInhabitants, "premise: porte is opened by inhabitants");
            Assert.IsFalse(porte.Open, "premise: porte starts closed");
            Assert.AreNotEqual(0, Game.Level.StationAreaMask & bit, "the station walks leave porte's doorway out");

            var positions = new List<Vector3>();
            var activities = new List<RoutineActivity>();
            var swinging = new List<bool>();
            var open = new List<bool>();
            int sampled = 0;
            bool leafSeen = false;
            void Watch()
            {
                positions.Add(h.Routine.Position);
                activities.Add(h.Routine.LastActivity);
                swinging.Add(porte.Swinging);
                open.Add(porte.Open);
                sampled = Mathf.Max(sampled, porte.Samples.Length);
                leafSeen |= Game.LeafSeen;
            }
            Game.FixedStepped += Watch;
            yield return Run(StepsFor(20f), () => porte.Open && h.Routine.Position.x < -0.5f, 4f);
            Game.FixedStepped -= Watch;
            int s0 = swinging.IndexOf(true);
            Assert.GreaterOrEqual(s0, 0, "porte never opened");
            float stop = GameState.DoorStopDistance(porte.Geometry, 1f);
            Vector3 p0 = positions[s0];
            Assert.That(p0.x, Is.InRange(stop - 0.1f, stop + 1e-3f), $"the inhabitant opened porte from x = {p0.x}, not {stop} m in front");
            Assert.Less(Mathf.Abs(p0.z - 0.25f), 0.3f, "the inhabitant is not in front of porte");
            Assert.Greater(positions.Count, s0 + StopSteps + 2, "premise: recorded past the stop");
            for (int k = 1; k <= StopSteps; k++)
            {
                Assert.Less(Planar(positions[s0 + k], p0), 1e-5f, $"the inhabitant moved on step {k} of its stop");
                Assert.AreEqual(RoutineActivity.Waiting, activities[s0 + k], $"step {k} of the stop is not a wait");
            }
            Assert.Greater(Planar(positions[s0 + StopSteps + 1], p0), 1e-4f, "the inhabitant did not walk on after its stop");
            for (int k = s0; k <= s0 + DoorSteps; k++)
            {
                Assert.IsTrue(swinging[k], $"porte does not swing on step {k - s0} of its opening");
            }
            Assert.IsFalse(swinging[s0 + DoorSteps + 1], "porte still swings after 30 steps");
            Assert.IsTrue(open.Skip(s0).All(o => o), "porte closed again");
            Assert.IsTrue(porte.Open && porte.SwungByHousehold, "porte is not open by the household");
            Assert.Less(h.Routine.Position.x, -0.5f, "the inhabitant did not walk through");
            Assert.AreEqual(1, Game.HouseholdDoorOpenCount);
            Assert.AreEqual(0, sampled, "the household's swing has samples");
            Assert.IsFalse(leafSeen, "the household's swing was seen as the furniture moving");
            Assert.AreEqual(PlayState.Playing, Game.State);

            // Not opted in: porte blocks as in M5.
            yield return Load(M5DoorLevel);
            h = Game.MainInhabitant;
            porte = Game.Level.Leaves[0];
            Assert.AreEqual(0, Game.Level.StationAreaMask & bit, "a door not opted in is in the station walks");
            yield return Run(StepsFor(30f), () => h.Routine.StationIndex == 1, 6f);
            Assert.AreEqual(1, h.Routine.StationIndex, "premise: the inhabitant reached its second station");
            Assert.IsFalse(porte.Open, "an inhabitant opened a door not opted in");
            Assert.AreEqual(0, Game.HouseholdDoorOpenCount);
            AssertClean();
        }
    }
}
