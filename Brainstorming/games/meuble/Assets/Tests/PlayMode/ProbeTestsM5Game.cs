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
    /// The M5 game probe, wave 5A (docs/CONTRACT_M5.md 3, 12 and 16; CONTRACT_M5_v3.md 3, 4, 15.1, 15.2, 15.5 and 15.6), on the
    /// real Boot scene under GameRules.M4, with the game agent's test levels (never in levels.json):
    /// <list type="bullet">
    /// <item>36b to 36f, doors (test_m5_game_door: rooms a, b, c and d in a ring, a and b joined only by the closed leaf
    /// "porte" swinging into b): the hint in reach, a door push (DOORAUTO, in place of E) opens in exactly 30 moving steps,
    /// a real push toward the door only after its confirm time (36c2), refused while moving, a leaf seen
    /// swinging is a catch while the chair itself is hidden, a station walk unchanged by an opening and an investigation
    /// through the opened doorway.</item>
    /// <item>37b to 37g, people (test_m5_game_people: a dreamer who sits on the sofa, a watchful one, the dog): separate
    /// memories and suspicions, every slot after a carry, a taken seat as a standing dwell, each personality's range,
    /// angle, hearing, suspicion gain and tolerance in the rules, either suspicion at 1 loses, the intro card (and, wave
    /// 5A.1, its people block clear of the furniture on every level that lists people).</item>
    /// <item>37h (wave 5A.1, critique m7; test_m5_game_patterns: a pingpong hurried one, a wandering teen, a looping granny
    /// and the looping dog): the station of every visit in play is the pattern's, and every turn over 30 deg of every
    /// personality comes after the same 0.6 s telegraph.</item>
    /// <item>38b to 38f, the dog (test_m5_game_dog): the bark at the dog and a human looking toward it, the cooldown, a
    /// still chair seen by the dog changes nothing, the dog never catches nor counts for the exit, the Dog eye.</item>
    /// <item>38g (wave 5A.1, critique M3; the watchers' test_m5_watchers_dog, read only): a sleeping dog sees nothing, the
    /// awake one does.</item>
    /// <item>38h and 38i (CONTRACT_M5 20, test_m5_game_dog): after its bark the dog runs to the chair and pins it, and the
    /// human it calls puts it back (one discovery when out of place, nothing when in place).</item>
    /// <item>Wave 5B. 42b to 42f, the robot (test_m5_game_robot: Robi there and back along z = -2, a sitter on the chair, a
    /// witness): a contact shoves 0.25 m in 0.5 s (moving, input ignored), seen while shoved is caught (and bumps), the
    /// fixed timeline then the reversal, no shove while pinned, the hum masks a hop at 2.4 m but not at 2.6 m and never a
    /// creak, and its volume follows the furniture's distance to the robot.</item>
    /// <item>43b, the rocking chair (test_m5_game_rock): 40 rock steps after a stop, 20 after a careful one, each with a creak
    /// as long as the rock, seen rocking is caught, sat on it never rocks.</item>
    /// <item>44b to 44h, the load (test_m5_game_load: a vase on the chair, two humans, the dog, a 1.2 m wall): the fall's
    /// 6 m crash and its clue, the clue's one discovery and its put-away, the dog never finds it, the balance gauge and the
    /// vase's sway in the furniture frame, the vase inside the sample box, the clue never in a wall.</item>
    /// </list>
    /// Every wait counts game fixed steps (GameState.FixedStepped) under a real time guard, never rendered frames; every
    /// scenario asserts its premise first, so it cannot pass for the wrong reason.
    /// </summary>
    public sealed class ProbeTestsM5Game
    {
        private const float Dt = Tuning.FixedStep;
        private const string DoorLevel = "test_m5_game_door";
        private const string DogLevel = "test_m5_game_dog";
        private const string PeopleLevel = "test_m5_game_people";
        private const string PatternsLevel = "test_m5_game_patterns";
        private const string SleepLevel = "test_m5_watchers_dog";

        private static int DoorSteps => Mathf.RoundToInt(Tuning.DoorOpenTime / Dt);
        private static int GraceSteps => Mathf.RoundToInt(Tuning.CaughtGrace / Dt);
        private static int CooldownSteps => Mathf.RoundToInt(Tuning.BarkCooldown / Dt);
        private static int TelegraphSteps => Mathf.RoundToInt(Tuning.TelegraphDuration / Dt);
        private static int WakeSteps => Mathf.RoundToInt(Tuning.WakeTelegraph / Dt);

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

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(to - from);

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

        private IEnumerator Restart()
        {
            Game.Restart();
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: playing after the restart");
            yield return Steps(2);
        }

        private Vision VisionOf(Inhabitant h) => Game.Level.Visions.Find(v => v != null && v.Owner == h);

        private Inhabitant TheDog => Game.Level.Inhabitants.FirstOrDefault(h => h != null && h.IsDog);

        private int CountNoises(NoiseKind kind) => noises.Count(e => e.Kind == kind);

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

        /// <summary>
        /// What the furniture's samples would give, seen from <paramref name="h"/>'s eye with this range and half angle, in a
        /// room with no occluder between them (the test positions are chosen so): any sample in the cone.
        /// </summary>
        private bool Predict(Inhabitant h, float range, float halfAngle)
        {
            var samples = new Vector3[Tuning.SampleCount];
            Chair.GetSamplePoints(samples);
            return samples.Any(s => VisionMath.IsInCone(h.EyePosition, h.EyeForward, s, range, halfAngle));
        }

        // =====================================================================================================
        // ----- 36: doors (CONTRACT_M5_v3 3, 15.1, 15.2) -----
        // =====================================================================================================

        // test_m5_game_door: porte at (0, 0.25) on the wall x = 0, 1 m wide, hinged at z = -0.25, swinging into b (x > 0).
        // The chair spawns at (-0.5, 0.25) in a, in reach. The inhabitant's stations: (3, 0.25) in b facing the door, then
        // (-3, 4.6) in c facing the north wall; with porte closed its walks go round through d.
        private static readonly Vector3 SpawnA = new Vector3(-0.5f, 0f, 0.25f);
        private static readonly Vector3 FirstStation = new Vector3(3.0f, 0f, 0.25f);

        private DoorLeaf Porte()
        {
            Assert.AreEqual(1, Game.Level.Leaves.Count, "premise: the door level has one leaf");
            DoorLeaf porte = Game.Level.Leaves[0];
            Assert.AreEqual("porte", porte.Id, "premise: the leaf is porte");
            return porte;
        }

        /// <summary>Freezes the inhabitant where it stands facing east (away from porte), so nothing sees or hears.</summary>
        private void PinAwayFromTheDoor()
        {
            Inhabitant h = Game.MainInhabitant;
            h.Pin(h.Routine.Position, 90f);
        }

        /// <summary>
        /// Step 36b (CONTRACT_M5_v3 15.2): hud.door shows while a closed leaf is in reach of the furniture, hides out of reach,
        /// during the opening and for an open leaf, and never shows on a level without leaves.
        /// </summary>
        [UnityTest]
        public IEnumerator Step36b_DoorHintShowsInReachOfAClosedLeaf()
        {
            yield return Load(DoorLevel);
            PinAwayFromTheDoor();
            DoorLeaf porte = Porte();
            yield return Steps(2);
            Assert.IsFalse(porte.Open, "premise: porte starts closed");
            Assert.IsTrue(porte.InReach(Chair), "premise: the spawn is in reach of porte");
            Assert.AreSame(porte, Game.DoorInReach, "the leaf in reach is not porte");
            Assert.IsTrue(Hud.DoorHintVisible, "no door hint in reach of a closed leaf");
            Assert.IsTrue(Hud.Labels.TryGetValue("DoorHintLine", out Text line) && line.text == Strings.HudDoor, "the hint does not carry hud.door");

            Chair.Teleport(new Vector3(-1.6f, 0f, 0.25f), 90f);
            yield return Steps(1);
            Assert.IsFalse(porte.InReach(Chair), "premise: 1.6 m from the door is out of reach");
            Assert.IsFalse(Hud.DoorHintVisible, "the door hint shows out of reach");
            Assert.IsNull(Game.DoorInReach);

            Chair.Teleport(SpawnA, 90f);
            yield return Steps(1);
            Assert.IsTrue(Hud.DoorHintVisible, "the door hint did not come back in reach");

            InputReader.InjectDoorPush();
            yield return Until(() => porte.Open, 3);
            Assert.IsTrue(porte.Open, "premise: the door push opened porte");
            Assert.IsFalse(Hud.DoorHintVisible, "the door hint shows during the opening");
            yield return Until(() => !porte.Swinging && !Chair.ActionActive, DoorSteps + 5);
            yield return Steps(2);
            Assert.IsFalse(Hud.DoorHintVisible, "the door hint shows for an open leaf");
            Assert.IsNull(Game.DoorInReach, "an open leaf is still in reach");

            yield return Load("level1");
            Assert.AreEqual(0, Game.Level.Leaves.Count, "premise: level1 has no leaf");
            Assert.IsFalse(Hud.DoorHintVisible, "the door hint shows on a level without leaves");
            AssertClean();
        }

        /// <summary>
        /// Step 36c (CONTRACT_M5_v3 15.2): a door push in reach (DOORAUTO: InputReader.InjectDoorPush, a push already held for
        /// its confirm time, in place of the E press) opens the leaf in exactly 30 moving steps, the push step being the first;
        /// the furniture does not travel; the leaf is in the open mask from its first swing step, swings with its 4 samples on
        /// all 30 steps (wave 5A.1, critique m5: the 30th at the open angle), and is open, without samples, from the next step;
        /// the swing sound plays once. With the floor lamp, E switches the lamp out of reach and in reach alike (DOORAUTO: E is
        /// only the lamp's, the door stays closed), and the door push in reach opens the door and leaves the lamp alone.
        /// </summary>
        [UnityTest]
        public IEnumerator Step36c_EOpensTheLeafInExactlyThirtyMovingSteps()
        {
            yield return Load(DoorLevel);
            PinAwayFromTheDoor();
            DoorLeaf porte = Porte();
            yield return Steps(3);
            Assert.IsFalse(Chair.IsMoving, "premise: the chair is still");
            Assert.IsTrue(porte.InReach(Chair), "premise: in reach");
            Assert.IsFalse(Game.Seen, "premise: unseen");
            Assert.AreEqual(0, Game.Level.OpenMask, "premise: no leaf open");
            Vector3 at = Chair.transform.position;
            float yaw = Chair.Yaw;
            int doors = Game.Sfx.DoorsPlayed;
            int opens = Game.DoorOpenCount;

            var moving = new List<bool>();
            var samples = new List<int>();
            var swinging = new List<bool>();
            var masks = new List<int>();
            var external = new List<bool>();
            float travel = 0f;
            void Watch()
            {
                moving.Add(Chair.IsMoving);
                samples.Add(porte.Samples.Length);
                swinging.Add(porte.Swinging);
                masks.Add(Game.Level.OpenMask);
                external.Add(Chair.Action == FurnitureController.BodyAction.External);
                travel = Mathf.Max(travel, Planar(Chair.transform.position, at));
            }
            Game.FixedStepped += Watch;
            InputReader.InjectDoorPush();
            yield return Until(() => moving.Count >= DoorSteps + 10, DoorSteps + 15);
            Game.FixedStepped -= Watch;

            Assert.AreEqual(0, moving.IndexOf(true), "the opening did not start on the push step");
            int run = moving.TakeWhile(m => m).Count();
            Assert.AreEqual(DoorSteps, run, $"the opening is {run} moving steps, not {DoorSteps}");
            Assert.IsFalse(moving.Skip(run).Any(m => m), "the furniture still moves after the opening");
            for (int k = 0; k < run; k++)
            {
                Assert.IsTrue(external[k], $"step {k + 1} of the opening is not the external action");
                Assert.AreEqual(1, masks[k] & 1, $"porte is not in the open mask on step {k + 1}");
                Assert.IsTrue(swinging[k], $"porte is not swinging on step {k + 1} of the opening");
                Assert.AreEqual(Tuning.LeafSampleCount, samples[k], $"leaf samples on step {k + 1} of the opening");
            }
            int sampled = samples.Take(run).Count(n => n == Tuning.LeafSampleCount);
            Assert.AreEqual(DoorSteps, sampled, $"the leaf is sampled on {sampled} steps of its swing, not {DoorSteps}");
            for (int k = run; k < samples.Count; k++)
            {
                Assert.IsFalse(swinging[k], $"porte still swings on step {k + 1}, after the opening");
                Assert.AreEqual(0, samples[k], $"leaf samples on step {k + 1}, after the opening");
                Assert.AreEqual(1, masks[k] & 1, $"porte left the open mask on step {k + 1}");
            }
            Assert.AreEqual(DoorSteps, porte.SwingSteps, "the swing is not stepped once per fixed step");
            Assert.IsTrue(porte.Open && !porte.Swinging, "porte is not open after the opening");
            Assert.AreEqual(Tuning.DoorSwingDegrees, porte.Angle, 1e-3f);
            Assert.Less(travel, 1e-4f, "the furniture travelled during the opening");
            Assert.AreEqual(yaw, Chair.Yaw, 1e-3f, "the furniture turned during the opening");
            Assert.AreEqual(opens + 1, Game.DoorOpenCount, "one door opened");
            Assert.AreEqual(doors + 1, Game.Sfx.DoorsPlayed, "the swing sound did not play once");
            Assert.AreEqual(0, CountNoises(NoiseKind.Hop) + CountNoises(NoiseKind.Creak), "the opening made a noise event");
            Assert.AreEqual(PlayState.Playing, Game.State);

            // A push by an open leaf: nothing (no door to open, and the chair has no body action).
            InputReader.InjectDoorPush();
            yield return Steps(3);
            Assert.IsFalse(Chair.ActionActive, "a push by an open leaf started an action");
            Assert.AreEqual(opens + 1, Game.DoorOpenCount);

            // The floor lamp: E switches it out of reach; DOORAUTO: in reach of a closed leaf too (E is the lamp's only), and
            // the door push is the door's.
            yield return Restart();
            PinAwayFromTheDoor();
            porte = Porte();
            Chair.SetBody(BodyDef.For("floor_lamp"));
            Chair.Teleport(new Vector3(-1.8f, 0f, 0.25f), 90f);
            yield return Steps(2);
            Assert.IsNotNull(Chair.Lamp, "premise: the floor lamp has its light");
            Assert.IsFalse(porte.InReach(Chair), "premise: out of reach");
            int toggles = Chair.ToggleCount;
            InputReader.InjectAction();
            yield return Until(() => Chair.ToggleCount != toggles, 3);
            Assert.AreEqual(toggles + 1, Chair.ToggleCount, "E out of reach of any leaf did not switch the lamp");
            Assert.IsFalse(porte.Open, "E out of reach opened the door");
            yield return Until(() => !Chair.ActionActive, StepsFor(1f));
            yield return Steps(2);
            Chair.Teleport(SpawnA, 90f);
            yield return Steps(2);
            Assert.IsTrue(porte.InReach(Chair), "premise: the lamp is in reach");
            InputReader.InjectAction();
            yield return Until(() => Chair.ToggleCount != toggles + 1, 3);
            Assert.AreEqual(toggles + 2, Chair.ToggleCount, "E in reach of a closed leaf did not switch the lamp");
            Assert.IsFalse(porte.Open || porte.Swinging, "E opened the door: it is the lamp's only now");
            yield return Until(() => !Chair.ActionActive, StepsFor(1f));
            yield return Steps(2);
            InputReader.InjectDoorPush();
            yield return Until(() => porte.Open, 3);
            Assert.IsTrue(porte.Open, "the door push in reach did not open the door");
            Assert.AreEqual(toggles + 2, Chair.ToggleCount, "the door push switched the lamp");
            Assert.AreEqual(FurnitureController.BodyAction.External, Chair.Action, "the opening is not the external action");
            yield return Until(() => !Chair.ActionActive, DoorSteps + 5);
            AssertClean();
        }

        /// <summary>
        /// Step 36d (CONTRACT_M5_v3 15.2): a door push (injected, DOORAUTO) in reach while moving does nothing: the leaf stays
        /// closed, no action starts, the furniture drives on (the push is the door's, so no body action either). Still in reach,
        /// the push then opens it. A real push never comes to this: it brakes first (36c2).
        /// </summary>
        [UnityTest]
        public IEnumerator Step36d_EIsRefusedWhileMoving()
        {
            yield return Load(DoorLevel);
            PinAwayFromTheDoor();
            DoorLeaf porte = Porte();
            Chair.Teleport(new Vector3(-0.5f, 0f, -0.9f), 0f);
            yield return Steps(2);
            Assert.IsFalse(porte.InReach(Chair), "premise: the run starts out of reach");
            Chair.ScriptedDirection = Vector3.forward;
            yield return Until(() => porte.InReach(Chair) && Chair.transform.position.z >= -0.05f, StepsFor(3f));
            Assert.IsTrue(porte.InReach(Chair), "premise: the run reached the door");
            Assert.IsTrue(Chair.IsMoving, "premise: moving in reach");
            Assert.Greater(Chair.PlanarSpeed, 0.5f, "premise: moving at speed");
            int opens = Game.DoorOpenCount;
            Vector3 before = Chair.transform.position;
            bool action = false;
            bool stillMoving = true;
            void Watch()
            {
                action |= Chair.ActionActive;
                stillMoving &= Chair.IsMoving;
            }
            Game.FixedStepped += Watch;
            InputReader.InjectDoorPush();
            yield return Steps(5);
            Game.FixedStepped -= Watch;
            Assert.IsFalse(porte.Open || porte.Swinging, "a push while moving opened the door");
            Assert.IsFalse(action, "a push while moving started an action");
            Assert.IsTrue(stillMoving, "a refused push stopped the furniture");
            Assert.AreEqual(opens, Game.DoorOpenCount);
            Assert.Greater(Planar(Chair.transform.position, before), 0.1f, "the furniture did not drive on");

            Chair.ScriptedDirection = null;
            yield return Steps(3);
            Assert.IsFalse(Chair.IsMoving, "premise: stopped");
            Assert.IsTrue(porte.InReach(Chair), "premise: stopped in reach");
            InputReader.InjectDoorPush();
            yield return Until(() => porte.Open, 3);
            Assert.IsTrue(porte.Open, "control: still in reach, the push did not open the door");
            yield return Until(() => !Chair.ActionActive, DoorSteps + 5);
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 36c2 (task DOORAUTO): a real push of the move input (FurnitureController.ScriptedDirection, as a key or a stick
        /// gives it) toward porte from its doorway opens it: GameState.DoorPushDirection points into porte's wall; a push along
        /// the wall (90 degrees) or 60 degrees off never opens it; a push shorter than the confirm time opens nothing and the
        /// chair never moved; a push held for the confirm steps holds the chair still (not moving, no travel, no turn) and the
        /// opening begins on the next step, the same 30 step external action as the E press of M5.
        /// </summary>
        [UnityTest]
        public IEnumerator Step36c2_PushTowardTheDoorOpensItAfterTheConfirmTime()
        {
            yield return Load(DoorLevel);
            PinAwayFromTheDoor();
            DoorLeaf porte = Porte();
            int confirm = FurnitureController.DoorPushConfirmSteps(Dt);
            Assert.AreEqual(8, confirm, "premise: the confirm time is 8 fixed steps");
            yield return Steps(2);
            Assert.IsTrue(porte.InReach(Chair) && !Chair.IsMoving, "premise: the chair waits still in reach of porte");
            Assert.IsTrue(Game.DoorPushDirection.HasValue, "no push direction in reach of a closed leaf");
            Vector3 into = Game.DoorPushDirection.Value;
            Assert.Less((into - Vector3.right).magnitude, 1e-4f, $"the push direction {into} does not point into porte's wall from room a");
            int opens = Game.DoorOpenCount;

            // Along the wall, and 60 degrees off: never an opening, whatever the hold.
            foreach (float off in new[] { 90f, 60f })
            {
                Chair.Teleport(SpawnA, 90f);
                yield return Steps(2);
                Chair.ScriptedDirection = Quaternion.Euler(0f, -off, 0f) * into;
                yield return Steps(confirm * 3);
                Chair.ScriptedDirection = null;
                yield return Steps(3);
                Assert.IsFalse(porte.Open || porte.Swinging, $"a push {off} degrees off the door opened it");
                Assert.AreEqual(opens, Game.DoorOpenCount, $"a push {off} degrees off counted an opening");
            }

            // Too short: nothing opens, and the held chair never moved.
            Chair.Teleport(SpawnA, 90f);
            yield return Steps(2);
            Vector3 at = Chair.transform.position;
            float yaw = Chair.Yaw;
            bool moved = false;
            void WatchShort() => moved |= Chair.IsMoving || Chair.ActionActive;
            Game.FixedStepped += WatchShort;
            Chair.ScriptedDirection = into;
            yield return Steps(confirm - 3);
            Chair.ScriptedDirection = null;
            yield return Steps(3);
            Game.FixedStepped -= WatchShort;
            Assert.IsFalse(porte.Open || porte.Swinging, "a push shorter than the confirm time opened the door");
            Assert.IsFalse(moved, "the chair moved or acted during a short push toward the door");
            Assert.Less(Planar(Chair.transform.position, at), 1e-4f, "the short push moved the chair toward the door");

            // Held: still for the confirm steps, then the opening on the next step, for exactly DoorOpenTime.
            var moving = new List<bool>();
            var acting = new List<bool>();
            float travel = 0f;
            void Watch()
            {
                moving.Add(Chair.IsMoving);
                acting.Add(Chair.ActionActive && Chair.Action == FurnitureController.BodyAction.External);
                travel = Mathf.Max(travel, Planar(Chair.transform.position, at));
                if (Chair.ActionActive)
                {
                    Chair.ScriptedDirection = null;
                }
            }
            Game.FixedStepped += Watch;
            Chair.ScriptedDirection = into;
            yield return Until(() => acting.Count >= confirm + DoorSteps + 5, confirm + DoorSteps + 10);
            Game.FixedStepped -= Watch;
            Chair.ScriptedDirection = null;
            Assert.AreEqual(confirm, acting.IndexOf(true), $"the opening began on push step {acting.IndexOf(true) + 1}, not {confirm + 1}");
            Assert.IsFalse(moving.Take(confirm).Any(m => m), "the chair moved while the push was being confirmed");
            Assert.AreEqual(DoorSteps, acting.Skip(confirm).TakeWhile(a => a).Count(), "the pushed opening is not exactly DoorOpenTime");
            Assert.IsTrue(porte.Open, "the held push did not open porte");
            Assert.AreEqual(opens + 1, Game.DoorOpenCount, "the held push did not count one opening");
            Assert.Less(travel, 1e-4f, "the chair travelled toward the door during the push or the opening");
            Assert.AreEqual(yaw, Chair.Yaw, 1e-3f, "the chair turned during the push or the opening");
            Assert.IsNull(Game.DoorPushDirection, "an open leaf still offers a push direction");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 36e (CONTRACT_M5_v3 15.2): a watcher in room a looks at porte; the chair stands in reach in room b, hidden from it
        /// by the wall whatever the leaf does. E opens the door: the watcher never sees the chair's own samples, but it sees the
        /// swinging leaf's, and that is the furniture seen moving: caught after the 0.2 s grace, the eye in alarm meanwhile.
        /// </summary>
        [UnityTest]
        public IEnumerator Step36e_LeafSeenSwingingIsCaughtWhileTheChairIsHidden()
        {
            yield return Load(DoorLevel);
            DoorLeaf porte = Porte();
            Inhabitant h = Game.MainInhabitant;
            var eye = new Vector3(-2.5f, 0f, 1.0f);
            h.Pin(eye, YawToward(eye, porte.Geometry.Center));
            Chair.Teleport(new Vector3(0.3f, 0f, 1.0f), 0f);
            yield return Steps(3);
            Assert.IsTrue(porte.InReach(Chair), "premise: in reach from room b, outside the swing sector");
            Assert.IsFalse(Game.Seen, "premise: the watcher sees the chair");
            var chairSamples = new Vector3[Tuning.SampleCount];
            Chair.GetSamplePoints(chairSamples);
            porte.PoseAt(Tuning.DoorSwingDegrees);
            bool seenThroughDoorway = Vision.Test(h.EyePosition, h.EyeForward, chairSamples, Tuning.ViewRange, Tuning.ViewHalfAngle, null);
            bool leafVisibleOpen = porte.Geometry.Samples(45f).Any(s => VisionMath.IsInCone(h.EyePosition, h.EyeForward, s, 10f, 55f));
            porte.PoseAt(0f);
            Assert.IsFalse(seenThroughDoorway, "premise: with the doorway open the watcher would see the chair itself");
            Assert.IsTrue(leafVisibleOpen, "premise: the swinging leaf is out of the watcher's cone");

            var chairSeen = new List<bool>();
            var leafSeen = new List<bool>();
            var eyes = new List<HudEye>();
            var states = new List<PlayState>();
            Vision vision = VisionOf(h);
            void Watch()
            {
                chairSeen.Add(vision.SeesPlayer);
                leafSeen.Add(Game.LeafSeen);
                eyes.Add(Game.EyeState);
                states.Add(Game.State);
            }
            Game.FixedStepped += Watch;
            InputReader.InjectDoorPush();
            yield return Until(() => Game.State != PlayState.Playing, DoorSteps + 10);
            Game.FixedStepped -= Watch;
            Assert.IsTrue(porte.Open, "premise: the opening began");
            Assert.AreEqual(PlayState.Caught, Game.State, "a leaf seen swinging is not a catch");
            Assert.AreEqual(LoseReason.SeenMoving, Game.LoseReason);
            int caught = states.IndexOf(PlayState.Caught);
            Debug.Log($"[Step36e] leaf seen on steps {string.Join(",", leafSeen.Select((s, i) => s ? (i + 1).ToString() : null).Where(s => s != null))}, caught on step {caught + 1}");
            Assert.IsFalse(chairSeen.Take(caught + 1).Any(s => s), "the watcher saw the chair itself: the catch is not the leaf's");
            Assert.GreaterOrEqual(caught, GraceSteps - 1, "caught before the grace");
            Assert.Less(caught, DoorSteps, "caught after the swing");
            for (int k = caught - GraceSteps + 1; k <= caught; k++)
            {
                Assert.IsTrue(leafSeen[k], $"the leaf was not seen on step {k + 1}, inside the grace that caught");
                Assert.AreEqual(HudEye.Alarm, eyes[k], $"the eye is not in alarm on step {k + 1} while the swinging leaf is seen");
            }
            Assert.AreEqual(GraceSteps - 1, caught - leafSeen.IndexOf(true), "not caught exactly one grace after the leaf was first seen");
            AssertClean();
        }

        private static string Trace(InhabitantRoutine r)
        {
            return $"({r.Position.x:0.0000}, {r.Position.z:0.0000}) yaw {r.BodyYaw:0.00} head {r.HeadYaw:0.00} {r.LastActivity} {r.Mode} st {r.StationIndex} v {r.VisitIndex} tg {r.TelegraphCount}";
        }

        private static bool BackAtFirst(InhabitantRoutine r) => r.VisitIndex >= 2 && r.StationIndex == 0 && r.InDwell;

        private static bool AtSecond(InhabitantRoutine r) => r.VisitIndex == 1 && r.StationIndex == 1 && r.InDwell;

        /// <summary>
        /// Step 36f (CONTRACT_M5_v3 15.1): the station walks are frozen with the authored leaves. The inhabitant's walk back
        /// from room c goes round through d; opened while it dwells in c, porte would make a shorter way through a, yet the
        /// walk is identical, step by step, to the one of a run where the door stays closed. Then the chair, moved out of place
        /// in a in line with the doorway, is discovered from b: the investigation plans with the current leaves and walks
        /// through the opened doorway.
        /// </summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator Step36f_StationWalkUnchangedByAnOpeningAndAnInvestigationThroughIt()
        {
            yield return Load(DoorLevel);
            // A chair left still creaks at 25 s (CONTRACT_M2 3.3) and alerts the inhabitant in run A only (run B moves it):
            // the creak is not what this step compares, so it is off for both runs.
            Game.Rules.Creak = false;
            Assert.AreEqual(1, Game.Level.Inhabitants.Count, "premise: one inhabitant");
            Assert.GreaterOrEqual(Game.MainInhabitant.Routine.FrozenWalkCount, 2, "premise: the station walks are frozen at load");

            // Run A: the door stays closed. Both runs record from the first step after their restart.
            Game.Restart();
            var a = new List<Vector3>();
            var traceA = new List<string>();
            void RecordA()
            {
                a.Add(Game.MainInhabitant.Routine.Position);
                traceA.Add(Trace(Game.MainInhabitant.Routine));
            }
            Game.FixedStepped += RecordA;
            yield return Run(StepsFor(60f), () => BackAtFirst(Game.MainInhabitant.Routine) || Game.State != PlayState.Playing, 8f);
            Game.FixedStepped -= RecordA;
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: run A ended");
            Assert.IsTrue(BackAtFirst(Game.MainInhabitant.Routine), "premise: run A never came back to its first station");
            Assert.AreEqual(0, Game.DiscoveryCount, "premise: run A discovered the chair");
            Assert.AreEqual(0, Game.AlertCount, "premise: something alerted the inhabitant in run A");
            float maxZ = a.Max(p => p.z);
            Assert.Greater(maxZ, 4.5f, "premise: the walks never reached room c");

            // Run B: porte opens while the inhabitant dwells in c, then the chair moves out of place in a.
            Game.Restart();
            var b = new List<Vector3>();
            var traceB = new List<string>();
            int discovered = -1;
            void RecordB()
            {
                b.Add(Game.MainInhabitant.Routine.Position);
                traceB.Add(Trace(Game.MainInhabitant.Routine));
                if (discovered < 0 && Game.DiscoveryCount > 0)
                {
                    discovered = b.Count - 1;
                }
            }
            Game.FixedStepped += RecordB;
            yield return Run(StepsFor(40f), () => AtSecond(Game.MainInhabitant.Routine) || Game.State != PlayState.Playing, 8f);
            InhabitantRoutine r = Game.MainInhabitant.Routine;
            Assert.IsTrue(AtSecond(r), "premise: the inhabitant never dwelt in room c");
            DoorLeaf porte = Porte();
            yield return Steps(2);
            Assert.IsTrue(porte.InReach(Chair) && !Chair.IsMoving && !Game.Seen, "premise: the chair waits unseen in reach of porte");
            InputReader.InjectDoorPush();
            yield return Until(() => porte.Open && !porte.Swinging && !Chair.ActionActive, DoorSteps + 5);
            Assert.IsTrue(porte.Open, "premise: porte did not open");
            Chair.ScriptedDirection = Vector3.left;
            yield return Until(() => Chair.transform.position.x <= -1.75f, StepsFor(3f));
            Chair.ScriptedDirection = null;
            yield return Steps(2);
            Assert.LessOrEqual(Chair.transform.position.x, -1.7f, "premise: the chair did not reach its spot in a");
            Assert.AreEqual(1, r.StationIndex, "premise: the inhabitant left room c before the chair was in place");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: the opening or the move was seen");
            Assert.AreEqual(0, Game.DiscoveryCount, "premise: discovered too early");
            yield return Run(StepsFor(40f), () => Game.DiscoveryCount > 0 || Game.State != PlayState.Playing, 8f);
            Assert.AreEqual(PlayState.Playing, Game.State, $"run B ended ({Game.LoseReason})");
            Assert.GreaterOrEqual(discovered, 0, "the chair out of place in line with the opened doorway was never discovered");

            // The walk back is the frozen one: identical to run A up to the discovery.
            // The discovery comes from room b, near the first station: the compared span covers the walk back from c round
            // through d into b, where a re-planned walk (through a and the opened doorway) would differ from its first step.
            int compared = Mathf.Min(discovered, a.Count);
            Vector3 last = b[compared - 1];
            Debug.Log($"[Step36f] {compared} steps compared, the last at ({last.x:0.00}, {last.z:0.00}); run A {a.Count} steps");
            Assert.IsTrue(last.x > 0.05f && last.z < 2.0f, $"premise: the compared span ends before the walk back reached room b ({last})");
            Assert.Less(Planar(last, FirstStation), 1.5f, "premise: the compared span does not cover the walk back");
            for (int k = 0; k < compared; k++)
            {
                if (Planar(a[k], b[k]) >= 1e-4f)
                {
                    for (int j = Mathf.Max(0, k - 40); j <= k; j++)
                    {
                        Debug.Log($"[Step36f] step {j + 1}: A {traceA[j]} | B {traceB[j]}");
                    }
                }
                Assert.Less(Planar(a[k], b[k]), 1e-4f, $"step {k + 1}: the routine moved differently after the opening ({b[k]} instead of {a[k]})");
            }

            // The investigation walks through the opened doorway (the current leaves), never round through d.
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode, "the discovery did not send the inhabitant to the chair");
            var path = new List<Vector3> { r.Position };
            void RecordPath() => path.Add(Game.MainInhabitant.Routine.Position);
            Game.FixedStepped += RecordPath;
            yield return Run(StepsFor(25f), () => r.Mode == InhabitantMode.Carrying || Chair.Carried || Game.State != PlayState.Playing, 4f);
            Game.FixedStepped -= RecordPath;
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.IsTrue(r.Mode == InhabitantMode.Carrying || Chair.Carried, $"the inhabitant never reached the chair (mode {r.Mode})");
            bool crossed = false;
            for (int k = 1; k < path.Count; k++)
            {
                Assert.Less(path[k].z, 2.05f, "the investigation went round through the other rooms");
                if (path[k - 1].x > 0f != path[k].x > 0f)
                {
                    crossed = true;
                    Assert.That(path[k].z, Is.InRange(-0.25f, 0.75f), "the investigation crossed the wall outside the doorway");
                }
            }
            Assert.IsTrue(crossed, "the investigation never went through porte");
            AssertClean();
        }

        // =====================================================================================================
        // ----- 37: people (CONTRACT_M5 3, CONTRACT_M5_v3 4 and 15.6) -----
        // =====================================================================================================

        // test_m5_game_people: a 13 x 9 m room. "Un" (dreamer) starts sitting on the sofa "Canape" at (-3, 3.6); "Deux"
        // (watchful) walks from (0.5, 2) to a sit station on the same sofa; the dog dwells at (5, 3.5) facing the north wall.
        // The chair spawns at (2, -1).

        private Inhabitant Un => Game.Level.Inhabitants[0];
        private Inhabitant Deux => Game.Level.Inhabitants[1];

        private IEnumerator LoadPeople(string first = null, string second = null, bool keep = true)
        {
            yield return Load(PeopleLevel);
            Assert.AreEqual(3, Game.Level.Inhabitants.Count, "premise: two humans and the dog");
            Assert.IsNotNull(TheDog, "premise: the dog");
            if (!keep)
            {
                Game.Def.Inhabitants[0].Personality = first;
                Game.Def.Inhabitants[1].Personality = second;
                yield return Restart();
            }
        }

        /// <summary>Freezes the dog at its station facing the north wall (it sees nothing of the tests).</summary>
        private void PinTheDog()
        {
            Inhabitant dog = TheDog;
            dog.Pin(dog.Routine.Position, 0f);
        }

        /// <summary>
        /// Step 37b (CONTRACT_M5_v3 4): each human has its own memory and suspicion. Only Un sees the chair out of place: its
        /// suspicion rises by its own gain, Deux's stays 0 and its observation is NotSeen; then only Deux sees it: its suspicion
        /// rises by its own gain and Un's keeps its value. Neither discovery moves a slot.
        /// </summary>
        [UnityTest]
        public IEnumerator Step37b_SeparateMemoriesAndSuspicions()
        {
            yield return LoadPeople();
            PinTheDog();
            Inhabitant un = Un, deux = Deux;
            Assert.AreEqual(PersonalityDef.Dreamer, un.Routine.Personality.Id, "premise: Un is the dreamer");
            Assert.AreEqual(PersonalityDef.Watchful, deux.Routine.Personality.Id, "premise: Deux is the watchful one");
            Vector3 spawn = Game.Def.Player.Position;
            var unAt = new Vector3(-1.0f, 0f, -3.5f);
            var deuxAt = new Vector3(5.0f, 0f, -1.0f);
            var displaced = new Vector3(-1.0f, 0f, 0.5f);
            deux.Pin(deuxAt, 90f);
            Chair.Teleport(displaced, 0f);
            un.Pin(unAt, YawToward(unAt, displaced), 0f, true);
            yield return Until(() => Game.DiscoveryCount > 0, GraceSteps + 5);
            Assert.AreEqual(1, Game.DiscoveryCount, "Un did not discover the displaced chair");
            float unGain = Tuning.SuspicionPerDiscovery * un.Routine.Personality.SuspicionFactor;
            Assert.AreEqual(unGain, Game.SuspicionOf(un).Value, 1e-4f, "Un's suspicion is not its own gain");
            Assert.AreEqual(0f, Game.SuspicionOf(deux).Value, 1e-6f, "Deux's suspicion moved with Un's discovery");
            Assert.AreEqual(Observation.NotSeen, Game.LastObservationOf(deux), "Deux observed what it did not see");
            Assert.Less(Planar(Game.MemoryOf(un).PlayerSlot.Position, spawn), 1e-3f, "a discovery moved Un's slot");
            Assert.Less(Planar(Game.MemoryOf(deux).PlayerSlot.Position, spawn), 1e-3f, "Deux's slot moved");

            un.Pin(unAt, YawToward(unAt, displaced) + 180f);
            var other = new Vector3(3.0f, 0f, 1.5f);
            Chair.Teleport(other, 0f);
            deux.Pin(deuxAt, YawToward(deuxAt, other), 0f, true);
            yield return Until(() => Game.DiscoveryCount > 1, GraceSteps + 5);
            Assert.AreEqual(2, Game.DiscoveryCount, "Deux did not discover the displaced chair");
            float deuxGain = Tuning.SuspicionPerDiscovery * deux.Routine.Personality.SuspicionFactor;
            Assert.AreEqual(deuxGain, Game.SuspicionOf(deux).Value, 1e-4f, "Deux's suspicion is not its own gain");
            // Back in Routine, Un's suspicion only decays (PRD 4.4); Deux's discovery adds nothing to it.
            float unNow = Game.SuspicionOf(un).Value;
            Assert.LessOrEqual(unNow, unGain + 1e-6f, "Un's suspicion rose with Deux's discovery");
            Assert.Greater(unNow, unGain - 0.05f, "premise: Un's suspicion decayed too much to tell");
            Assert.AreEqual(Mathf.Max(unNow, deuxGain), Game.MaxSuspicion, 1e-4f, "the HUD suspicion is not the highest one");
            Assert.AreEqual(0f, Game.SuspicionOf(TheDog).Value, 1e-6f, "the dog has a suspicion");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 37c (CONTRACT_M5_v3 4): Deux confirms the chair nudged within its tolerance (its slot moves there, Un's does
        /// not); Un finds it far away and carries it back to its own slot; after the put down every slot is the put down pose.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step37c_EverySlotUpdatedAfterACarry()
        {
            yield return LoadPeople();
            PinTheDog();
            Inhabitant un = Un, deux = Deux;
            Vector3 spawn = Game.Def.Player.Position;
            var deuxAt = new Vector3(5.0f, 0f, -1.0f);
            Vector3 nudged = spawn + Vector3.forward * 0.4f;
            Assert.Less(0.4f, deux.Routine.Personality.Tolerance, "premise: the nudge is within Deux's tolerance");
            var unAt = new Vector3(-1.0f, 0f, -3.5f);
            un.Pin(unAt, 180f);
            Chair.Teleport(nudged, 0f);
            deux.Pin(deuxAt, YawToward(deuxAt, nudged), 0f, true);
            yield return Steps(3);
            Assert.AreEqual(Observation.Confirmed, Game.LastObservationOf(deux), "premise: Deux confirms the nudged chair");
            Assert.Less(Planar(Game.MemoryOf(deux).PlayerSlot.Position, nudged), 0.05f, "premise: Deux's slot took the nudged pose");
            Assert.Less(Planar(Game.MemoryOf(un).PlayerSlot.Position, spawn), 0.05f, "Un's slot moved with Deux's sighting");

            deux.Pin(deuxAt, 90f);
            var displaced = new Vector3(-1.0f, 0f, 0.5f);
            Chair.Teleport(displaced, 0f);
            un.Pin(unAt, YawToward(unAt, displaced), 0f, true);
            bool carried = false;
            bool released = false;
            Vector3 putDown = Vector3.zero;
            void Watch()
            {
                carried |= Chair.Carried;
                if (carried && !Chair.Carried && !released)
                {
                    released = true;
                    putDown = YawMath.Planar(Chair.transform.position);
                }
            }
            Game.FixedStepped += Watch;
            yield return Run(StepsFor(60f), () => released || Game.State != PlayState.Playing, 4f);
            Game.FixedStepped -= Watch;
            Assert.AreEqual(PlayState.Playing, Game.State, $"the level ended ({Game.LoseReason})");
            Assert.IsTrue(carried && released, "premise: Un never carried the chair back");
            Assert.Less(Planar(putDown, spawn), 0.1f, "premise: put down at Un's slot");
            Assert.Greater(Planar(putDown, nudged), 0.3f, "premise: Deux remembered another pose");
            for (int i = 0; i < Game.Level.Inhabitants.Count; i++)
            {
                Inhabitant h = Game.Level.Inhabitants[i];
                Assert.Less(Planar(Game.MemoryOf(h).PlayerSlot.Position, putDown), 0.05f, $"inhabitant {i} ({h.Routine.Personality.Id}) does not remember the put down pose");
            }
            AssertClean();
        }

        /// <summary>
        /// Step 37d (CONTRACT_M5_v3 15.6): one seat registry per level. Un sits on the sofa from the start; Deux comes to its own
        /// sit station on the same sofa while Un holds it: Deux's dwell is a standing one (not sitting, not lowered, its
        /// standing eye, at its station), and the sofa stays Un's.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step37d_TakenSeatIsAStandingDwell()
        {
            yield return LoadPeople();
            PinTheDog();
            Inhabitant un = Un, deux = Deux;
            StationDef deuxSit = Game.Def.Inhabitants[1].Stations[1];
            Assert.AreEqual("Canape", deuxSit.Sit, "premise: Deux's second station sits on the sofa");
            Assert.AreEqual("Canape", Game.Def.Inhabitants[0].Stations[0].Sit, "premise: Un's first station sits on the sofa");
            Assert.AreSame(Game.Level.Seats, un.Routine.Seats, "Un does not use the level's seat registry");
            Assert.AreSame(Game.Level.Seats, deux.Routine.Seats, "Deux does not use the level's seat registry");
            Assert.AreEqual(0, un.Routine.SeatOwner, "Un's seat owner is not its index");
            Assert.AreEqual(1, deux.Routine.SeatOwner, "Deux's seat owner is not its index");
            yield return Until(() => un.Routine.IsSitting, StepsFor(2f));
            Assert.IsTrue(un.Routine.IsSitting, "premise: Un never sat");
            Assert.AreEqual(0, Game.Level.Seats.SitterOf("Canape"), "the sofa is not Un's in the level's registry");

            yield return Run(StepsFor(20f), () => deux.Routine.StationIndex == 1 && deux.Routine.InDwell || Game.State != PlayState.Playing, 2f);
            Assert.AreEqual(PlayState.Playing, Game.State, $"the level ended ({Game.LoseReason})");
            Assert.IsTrue(deux.Routine.StationIndex == 1 && deux.Routine.InDwell, "premise: Deux never reached its sit station");
            Assert.IsTrue(un.Routine.IsSitting, "premise: Un no longer sits");
            float standing = deux.Routine.Personality.EyeHeight;
            int dwellSteps = 0;
            bool sat = false, lowered = false, held = false, moved = false;
            float worstEye = 0f;
            void Watch()
            {
                InhabitantRoutine r = deux.Routine;
                if (!(r.StationIndex == 1 && r.InDwell))
                {
                    return;
                }
                dwellSteps++;
                sat |= r.IsSitting;
                lowered |= r.IsLowered;
                held |= r.HeldSeat != null;
                moved |= Planar(r.Position, deuxSit.Position) > 0.05f;
                worstEye = Mathf.Max(worstEye, Mathf.Abs(r.EyeHeight - standing));
            }
            Game.FixedStepped += Watch;
            yield return Until(() => !(deux.Routine.StationIndex == 1 && deux.Routine.InDwell), StepsFor(deuxSit.Dwell + 3f));
            Game.FixedStepped -= Watch;
            Assert.GreaterOrEqual(dwellSteps, StepsFor(deuxSit.Dwell) - 5, "premise: Deux's dwell was too short to tell");
            Assert.IsFalse(sat, "Deux sat on a seat Un holds");
            Assert.IsFalse(lowered, "Deux lowered on a taken seat");
            Assert.IsFalse(held, "Deux claimed a taken seat");
            Assert.IsFalse(moved, "Deux left its station for the seat");
            Assert.Less(worstEye, 1e-4f, "Deux's eye left its standing height on a taken seat");
            Assert.AreEqual(0, Game.Level.Seats.SitterOf("Canape"), "the sofa changed hands");
            AssertClean();
        }

        /// <summary>
        /// Step 37e (CONTRACT_M5 3): for each human personality, the rules use its range and half angle (the vision of the
        /// furniture), its hearing factor (a bark heard within 6 m times the factor, not beyond), its suspicion gain and its
        /// tolerance (confirmed within it, discovered beyond it, and the ghost's ring and the decoy rings drawn at it).
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step37e_EachPersonalityRangeAngleHearingGainAndToleranceApplied()
        {
            yield return LoadPeople();
            string[] ids =
            {
                PersonalityDef.Default, PersonalityDef.Dreamer, PersonalityDef.Watchful, PersonalityDef.Hurried, PersonalityDef.Granny,
                PersonalityDef.Teen, PersonalityDef.Tidy,
            };
            foreach (string id in ids)
            {
                Game.Def.Inhabitants[0].Personality = id;
                PersonalityDef p = PersonalityDef.For(id);
                yield return SightOf(id, p);
                yield return HearingOf(id, p, true);
                yield return HearingOf(id, p, false);
                yield return ToleranceOf(id, p, false);
                yield return ToleranceOf(id, p, true);
            }
            AssertClean();
        }

        /// <summary>Freezes Deux and the dog facing walls, away from every position of the personality checks.</summary>
        private void PinTheOthers()
        {
            Deux.Pin(new Vector3(6.0f, 0f, 4.0f), 0f);
            PinTheDog();
        }

        private IEnumerator SightOf(string id, PersonalityDef p)
        {
            yield return Restart();
            PinTheOthers();
            Inhabitant un = Un;
            Assert.AreEqual(id, un.Routine.Personality.Id, $"premise: Un is not {id}");
            var eyeAt = new Vector3(-6.0f, 0f, 0f);
            un.Pin(eyeAt, 90f);
            Vision v = VisionOf(un);
            PersonalityDef standard = PersonalityDef.For(PersonalityDef.Default);

            // Range: just inside and just outside, straight ahead.
            foreach (float d in new[] { p.ViewRange - 0.4f, p.ViewRange + 0.4f })
            {
                Chair.Teleport(eyeAt + Vector3.right * d, 0f);
                yield return Steps(1);
                bool expected = Predict(un, p.ViewRange, p.HalfAngle);
                Assert.AreEqual(d < p.ViewRange, expected, $"{id}: premise: the range check at {d:0.0} m is not decided by the range");
                Assert.AreEqual(p.ViewRange, v.Range, 1e-4f, $"{id}: the vision range is not the personality's");
                Assert.AreEqual(expected, v.SeesPlayer, $"{id}: seen at {d:0.0} m with a {p.ViewRange} m range");
                if (p.ViewRange < standard.ViewRange - 0.5f && !expected)
                {
                    Assert.IsTrue(Predict(un, standard.ViewRange, standard.HalfAngle), $"{id}: premise: the default range would not see it either");
                }
            }

            // Half angle: the last bearing (at 3 m, toward the south east) it still sees, and the next degree.
            int inside = -1;
            for (int beta = 0; beta <= 89; beta++)
            {
                Chair.Teleport(eyeAt + YawMath.Forward(90f + beta) * 3f, 0f);
                if (Predict(un, p.ViewRange, p.HalfAngle))
                {
                    inside = beta;
                }
            }
            Assert.That(inside, Is.InRange((int)p.HalfAngle - 15, (int)p.HalfAngle + 5), $"{id}: premise: the cone edge is not near the half angle");
            foreach (int beta in new[] { inside, inside + 1 })
            {
                Chair.Teleport(eyeAt + YawMath.Forward(90f + beta) * 3f, 0f);
                yield return Steps(1);
                bool expected = beta == inside;
                Assert.AreEqual(p.HalfAngle, v.HalfAngle, 1e-4f, $"{id}: the vision half angle is not the personality's");
                Assert.AreEqual(expected, v.SeesPlayer, $"{id}: seen at {beta} deg off with a {p.HalfAngle} deg half angle");
                if (Math.Abs(p.HalfAngle - standard.HalfAngle) > 2f && (p.HalfAngle < standard.HalfAngle) != expected)
                {
                    Assert.AreNotEqual(expected, Predict(un, standard.ViewRange, standard.HalfAngle), $"{id}: premise: the default angle would decide the same");
                }
            }
        }

        private IEnumerator HearingOf(string id, PersonalityDef p, bool within)
        {
            yield return Restart();
            PinTheOthers();
            Inhabitant un = Un;
            Inhabitant dog = TheDog;
            Assert.AreEqual(id, un.Routine.Personality.Id, $"premise: Un is not {id}");
            float radius = Tuning.BarkRadius * p.HearingFactor;
            float d = within ? radius - 0.3f : radius + 0.3f;
            var dogAt = new Vector3(0f, 0f, -3.5f);
            dog.Pin(dogAt, 0f);
            Vector3 unAt = dogAt + Vector3.left * d;
            un.Pin(unAt, 270f, 0f, true);
            Chair.Teleport(new Vector3(0f, 0f, -1.0f), 90f);
            yield return Steps(2);
            Assert.IsTrue(VisionOf(dog).SeesPlayer, $"{id}: premise: the dog does not see the chair");
            Assert.IsFalse(Game.Seen, $"{id}: premise: a human sees the chair");
            int alerts = Game.AlertCount;
            int barks = Game.BarkCount;
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Game.BarkCount > barks || Game.State != PlayState.Playing, GraceSteps + 5);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(barks + 1, Game.BarkCount, $"{id}: premise: the dog did not bark");
            Assert.AreEqual(PlayState.Playing, Game.State, $"{id}: premise: the bark run was caught");
            Assert.AreEqual(within ? alerts + 1 : alerts, Game.AlertCount, $"{id}: a bark {d:0.00} m away with a {radius:0.00} m hearing radius");
            Assert.AreEqual(within ? InhabitantMode.Alerted : InhabitantMode.Routine, un.Routine.Mode, $"{id}: the listener's mode after a bark {d:0.00} m away");
            if (within)
            {
                Assert.Less(Planar(un.Routine.AlertSource, dogAt), 1e-3f, $"{id}: the listener does not look toward the bark");
            }
        }

        private IEnumerator ToleranceOf(string id, PersonalityDef p, bool outside)
        {
            yield return Restart();
            PinTheOthers();
            Inhabitant un = Un;
            Assert.AreEqual(id, un.Routine.Personality.Id, $"premise: Un is not {id}");
            Assert.AreEqual(p.Tolerance, Game.MemoryOf(un).Tolerance, 1e-6f, $"{id}: the memory's tolerance is not the personality's");
            Vector3 slot = Game.MemoryOf(un).PlayerSlot.Position;
            Assert.Less(Planar(slot, Game.Def.Player.Position), 1e-3f, $"{id}: premise: the slot is the spawn");
            float off = outside ? p.Tolerance + 0.05f : p.Tolerance - 0.05f;
            Vector3 chairAt = slot + Vector3.right * off;
            var unAt = new Vector3(slot.x, 0f, -4.0f);
            Chair.Teleport(chairAt, 0f);
            un.Pin(unAt, YawToward(unAt, chairAt), 0f, true);
            int discoveries = Game.DiscoveryCount;
            yield return Steps(GraceSteps + 3);
            Assert.IsTrue(VisionOf(un).SeesPlayer || Game.DiscoveryCount > discoveries, $"{id}: premise: Un does not see the chair");
            if (outside)
            {
                Assert.AreEqual(discoveries + 1, Game.DiscoveryCount, $"{id}: {off:0.00} m off its slot is no discovery with a {p.Tolerance} m tolerance");
                Assert.AreEqual(Tuning.SuspicionPerDiscovery * p.SuspicionFactor, Game.SuspicionOf(un).Value, 1e-4f, $"{id}: the suspicion gain");
                // M5 5B.1 (critique m14): the ghost's ring and the decoy rings show the tolerance of the seer that judges.
                Assert.IsTrue(Game.OutOfPlace, $"{id}: premise: the chair is not out of place");
                Assert.AreEqual(p.Tolerance, Game.Ghost.DecoyRingRadius, 1e-5f, $"{id}: the decoy rings are not the seer's tolerance");
                if (!Game.AtDecoy)
                {
                    Assert.IsTrue(Game.Ghost.Visible, $"{id}: premise: no ghost out of place");
                    Assert.AreEqual(p.Tolerance, Game.Ghost.RingRadius, 1e-5f, $"{id}: the ghost's ring is not the seer's tolerance");
                }
            }
            else
            {
                Assert.AreEqual(discoveries, Game.DiscoveryCount, $"{id}: {off:0.00} m off its slot is a discovery with a {p.Tolerance} m tolerance");
                Assert.AreEqual(Observation.Confirmed, Game.LastObservationOf(un), $"{id}: {off:0.00} m off its slot is not confirmed");
                Assert.AreEqual(0f, Game.SuspicionOf(un).Value, 1e-6f);
            }
        }

        /// <summary>
        /// Step 37f (CONTRACT_M5_v3 4): either human's suspicion at 1 loses, and the loss names that human; the other one's
        /// suspicion stays its own. With both at default (0.34 a discovery): two given discoveries, then a real third.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step37f_EitherSuspicionAtOneLoses()
        {
            foreach (int loser in new[] { 1, 0 })
            {
                yield return LoadPeople(null, null, false);
                PinTheDog();
                Inhabitant who = Game.Level.Inhabitants[loser];
                Inhabitant other = Game.Level.Inhabitants[1 - loser];
                Assert.AreEqual(PersonalityDef.Default, who.Routine.Personality.Id, "premise: default personalities");
                Assert.AreEqual(PersonalityDef.Default, other.Routine.Personality.Id, "premise: default personalities");
                Vector3 whoAt = loser == 1 ? new Vector3(5.0f, 0f, -1.0f) : new Vector3(-1.0f, 0f, -3.5f);
                Vector3 otherAt = loser == 1 ? new Vector3(-1.0f, 0f, -3.5f) : new Vector3(5.0f, 0f, -1.0f);
                other.Pin(otherAt, loser == 1 ? 180f : 90f);
                Game.SuspicionOf(who).AddDiscovery();
                Game.SuspicionOf(who).AddDiscovery();
                Assert.AreEqual(2f * Tuning.SuspicionPerDiscovery, Game.SuspicionOf(who).Value, 1e-4f, "premise: two discoveries given");
                Assert.AreEqual(PlayState.Playing, Game.State, "premise: 0.68 does not lose");
                Vector3 displaced = loser == 1 ? new Vector3(2.0f, 0f, 1.5f) : new Vector3(-1.0f, 0f, 0.5f);
                Chair.Teleport(displaced, 0f);
                who.Pin(whoAt, YawToward(whoAt, displaced), 0f, true);
                yield return Until(() => Game.State != PlayState.Playing, GraceSteps + 5);
                Assert.AreEqual(PlayState.Caught, Game.State, $"inhabitant {loser} reached a suspicion of 1 and nothing happened");
                Assert.AreEqual(LoseReason.Suspicion, Game.LoseReason);
                Assert.AreSame(who, Game.LostTo, $"the loss does not name inhabitant {loser}");
                Assert.AreEqual(0f, Game.SuspicionOf(other).Value, 1e-6f, "the other one's suspicion moved");
                Assert.IsTrue(Hud.SuspicionFailVisible, "the suspicion fail panel does not show");
            }
            AssertClean();
        }

        /// <summary>
        /// Step 37g (CONTRACT_M5 3, 16.10): the intro card lists the people with the level title: intro.here with the names
        /// joined by ", ", then one line per person with its name and trait, the dog included; it fades with the card. A level
        /// of default inhabitants lists nobody. Wave 5A.1 (critique m13): on every level of levels.json that lists people
        /// (and this one), the people plate covers neither the player's furniture at its start view nor the card's text, and
        /// stays on the screen.
        /// </summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator Step37g_IntroCardNamesThePeople()
        {
            yield return LoadPeople();
            Assert.IsTrue(Hud.PeopleVisible, "the intro card does not list the people");
            Assert.AreEqual(1f, Hud.TitleCardAlpha, 1e-3f, "premise: the title card shows");
            IReadOnlyList<string> lines = Hud.PeopleShown;
            Assert.AreEqual(4, lines.Count, "the names line and one line per person");
            // Levels v2 (C3b, LEVELS_V2 D22): the names line lists the data names; each person line is hud.person (the data
            // name, then the personality label) and the trait.
            string[] dataNames = Game.Def.Inhabitants.Select(h => h.Name).ToArray();
            Assert.AreEqual(3, dataNames.Length, "premise: three inhabitants");
            Assert.AreEqual(string.Format(Strings.IntroHere, string.Join(", ", dataNames)), lines[0], "the names line");
            (string name, string trait)[] people =
            {
                (Hud.PersonTitle(dataNames[0], Strings.PersonDreamer, false), Strings.PersonDreamerTrait),
                (Hud.PersonTitle(dataNames[1], Strings.PersonWatchful, false), Strings.PersonWatchfulTrait),
                (Hud.PersonTitle(dataNames[2], Strings.PersonDog, true), Strings.PersonDogTrait),
            };
            for (int i = 0; i < people.Length; i++)
            {
                StringAssert.Contains(people[i].name, lines[i + 1], $"person line {i + 1} has no name");
                StringAssert.Contains(people[i].trait, lines[i + 1], $"person line {i + 1} has no trait");
            }
            Assert.IsTrue(Hud.Labels.TryGetValue("PeopleHere", out Text here) && here.text == lines[0], "the names label");
            Assert.IsTrue(Hud.Labels.TryGetValue("PeopleList", out Text list), "premise: the first person column label");
            Assert.IsTrue(Hud.Labels.TryGetValue("PeopleList2", out Text list2), "premise: the second person column label");
            string columns = (list.enabled ? list.text : "") + "\n" + (list2.enabled ? list2.text : "");
            for (int i = 1; i < lines.Count; i++)
            {
                Assert.AreEqual(1, Occurrences(columns, lines[i]), $"person line {i} is not shown exactly once in the person columns");
            }
            Assert.IsTrue(Hud.Labels.TryGetValue("LevelName", out Text title), "premise: the level name label");
            Assert.IsTrue(here.transform.IsChildOf(title.transform.parent), "the people are not on the intro card (they would not fade with it)");
            Assert.IsTrue(list.transform.IsChildOf(here.transform.parent) && list2.transform.IsChildOf(here.transform.parent), "the person columns are not in the people block");
            foreach (string line in lines)
            {
                Assert.IsFalse(line.Contains("\u2014"), "an em-dash in the intro card");
            }
            yield return PeopleClearOfTheFurniture(PeopleLevel);

            // Every level of levels.json: a level that lists people has its plate clear of the furniture and the text.
            int listed = 0;
            foreach (string id in Game.LevelOrder.ToList())
            {
                yield return Load(id);
                if (!Hud.PeopleVisible)
                {
                    Assert.AreEqual(0, Hud.PeopleShown.Count, $"{id}: people listed but the block is hidden");
                    continue;
                }
                listed++;
                yield return PeopleClearOfTheFurniture(id);
            }
            Assert.GreaterOrEqual(listed, 4, "premise: fewer than four levels of levels.json list people (levels 8, 12, 14 and 16 do)");

            yield return Load("level1");
            Assert.IsFalse(Hud.PeopleVisible, "the intro card lists people on a level of default inhabitants");
            Assert.AreEqual(0, Hud.PeopleShown.Count);
            AssertClean();
        }

        private static int Occurrences(string text, string part)
        {
            int count = 0;
            for (int at = text.IndexOf(part, StringComparison.Ordinal); at >= 0; at = text.IndexOf(part, at + part.Length, StringComparison.Ordinal))
            {
                count++;
            }
            return count;
        }

        private static readonly Vector3[] Corners = new Vector3[4];

        /// <summary>The screen rect (pixels, y up) of a HUD text: its label's row, as wide as the text it draws (centred).</summary>
        private Rect TextScreenRect(string label)
        {
            Assert.IsTrue(Hud.Labels.TryGetValue(label, out Text text), $"premise: HUD label {label} missing");
            text.rectTransform.GetWorldCorners(Corners);
            Rect row = Rect.MinMaxRect(Corners[0].x, Corners[0].y, Corners[2].x, Corners[2].y);
            float width = Mathf.Min(row.width, text.preferredWidth * Hud.ScaleFactor);
            return new Rect(row.center.x - width * 0.5f, row.yMin, width, row.height);
        }

        /// <summary>The screen rect (pixels, y up) of the player furniture's drawn bounds, through the game camera.</summary>
        private Rect FurnitureScreenRect()
        {
            Camera view = Hud.View;
            Assert.IsNotNull(view, "premise: the HUD has the game camera");
            Renderer[] renderers = Chair.GetComponentsInChildren<Renderer>().Where(r => r.enabled && r.gameObject.activeInHierarchy).ToArray();
            Assert.Greater(renderers.Length, 0, "premise: the furniture draws nothing");
            Bounds b = renderers[0].bounds;
            foreach (Renderer r in renderers)
            {
                b.Encapsulate(r.bounds);
            }
            float xMin = float.MaxValue, yMin = float.MaxValue, xMax = float.MinValue, yMax = float.MinValue;
            for (int i = 0; i < 8; i++)
            {
                Vector3 corner = new Vector3((i & 1) == 0 ? b.min.x : b.max.x, (i & 2) == 0 ? b.min.y : b.max.y, (i & 4) == 0 ? b.min.z : b.max.z);
                Vector3 p = view.WorldToScreenPoint(corner);
                Assert.Greater(p.z, 0f, "premise: a corner of the furniture is behind the camera");
                xMin = Mathf.Min(xMin, p.x);
                xMax = Mathf.Max(xMax, p.x);
                yMin = Mathf.Min(yMin, p.y);
                yMax = Mathf.Max(yMax, p.y);
            }
            return Rect.MinMaxRect(xMin, yMin, xMax, yMax);
        }

        /// <summary>
        /// Wave 5A.1 (critique m13), on the loaded level at its start view, card shown: the people plate is on the screen and
        /// overlaps neither the player's furniture (its drawn bounds) nor the game title, the level name or the hint.
        /// </summary>
        private IEnumerator PeopleClearOfTheFurniture(string id)
        {
            yield return null;
            yield return null;
            Assert.IsTrue(Hud.PeopleVisible, $"{id}: premise: the intro card lists no people");
            Assert.AreEqual(1f, Hud.TitleCardAlpha, 1e-3f, $"{id}: premise: the card is not fully shown");
            Rect plate = Hud.PeopleScreenRect;
            Rect screen = new Rect(0f, 0f, Screen.width, Screen.height);
            Assert.IsTrue(plate.width > 10f && plate.height > 10f, $"{id}: premise: the people plate {plate} has no size");
            Assert.IsTrue(plate.xMin >= -0.5f && plate.yMin >= -0.5f && plate.xMax <= screen.width + 0.5f && plate.yMax <= screen.height + 0.5f,
                $"{id}: the people plate {plate} leaves the screen {screen}");
            Rect furniture = FurnitureScreenRect();
            Assert.IsTrue(furniture.width > 1f && furniture.height > 1f && furniture.Overlaps(screen), $"{id}: premise: the furniture {furniture} is not on the screen");
            Debug.Log($"[Step37g] {id}: people plate {plate}, furniture {furniture}, screen {screen.width} x {screen.height}");
            Assert.IsFalse(plate.Overlaps(furniture), $"{id}: the people plate {plate} covers the player's furniture {furniture}");
            foreach (string label in new[] { "Title", "LevelName", "Hint" })
            {
                Rect text = TextScreenRect(label);
                Assert.IsFalse(plate.Overlaps(text), $"{id}: the people plate {plate} covers the card's {label} {text}");
            }
        }

        /// <summary>One inhabitant's routine, step by step (Step 37h).</summary>
        private sealed class RoutineTrace
        {
            public readonly List<RoutineActivity> Activity = new List<RoutineActivity>();
            public readonly List<float> Body = new List<float>();
            public readonly List<float> Head = new List<float>();
            public readonly List<int> Telegraphs = new List<int>();
            /// <summary>Each dwell start: the visit, the station and where the routine stands.</summary>
            public readonly List<(int visit, int station, Vector3 at)> Dwells = new List<(int, int, Vector3)>();
            public bool WasInDwell;

            public void Record(InhabitantRoutine r)
            {
                Activity.Add(r.LastActivity);
                Body.Add(r.BodyYaw);
                Head.Add(r.HeadYaw);
                Telegraphs.Add(r.TelegraphCount);
                if (r.InDwell && !WasInDwell)
                {
                    Dwells.Add((r.VisitIndex, r.StationIndex, r.Position));
                }
                WasInDwell = r.InDwell;
            }
        }

        /// <summary>
        /// Step 37h (CONTRACT_M5 3 and 12 step 37, 16.7; wave 5A.1, critique m7), in play on test_m5_game_patterns: a hurried
        /// one ping-pongs over 4 stations, a teen wanders over 4 with a seed, a granny and the dog loop over 3, the chair stays
        /// in place (no creak). Over 10 visits or more of each patterned human, every dwell starts at the station
        /// RoutinePatterns' StationOrder gives for its visit (built from the level data, so a pattern or a seed the routine
        /// lost shows), visits counted one by one; and for every personality present, every body or head turn over 30 deg comes
        /// right after one telegraph of exactly 30 steps, and every telegraph lasts 30 steps.
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step37h_PatternsAndTelegraphsInPlay()
        {
            yield return Load(PatternsLevel);
            // A chair left still creaks at 25 s and alerts whoever hears it: an alert turn is not a routine turn.
            Game.Rules.Creak = false;
            List<InhabitantDef> defs = Game.Def.Inhabitants;
            int count = Game.Level.Inhabitants.Count;
            Assert.AreEqual(4, count, "premise: four inhabitants");
            int pingpong = defs.FindIndex(d => d.Pattern == RoutinePatterns.PingPong);
            int wander = defs.FindIndex(d => d.Pattern == RoutinePatterns.Wander);
            Assert.GreaterOrEqual(pingpong, 0, "premise: a pingpong inhabitant");
            Assert.GreaterOrEqual(wander, 0, "premise: a wandering inhabitant");
            Assert.IsFalse(Game.Level.Inhabitants[pingpong].IsDog || Game.Level.Inhabitants[wander].IsDog, "premise: both patterned inhabitants are humans");
            Assert.AreNotEqual(0, defs[wander].Seed, "premise: the wanderer has its own seed");
            var ids = new string[count];
            for (int i = 0; i < count; i++)
            {
                InhabitantRoutine r = Game.Level.Inhabitants[i].Routine;
                ids[i] = r.Personality.Id;
                string expected = defs[i].Kind == PersonalityDef.Dog ? PersonalityDef.Dog : PersonalityDef.For(defs[i].Personality).Id;
                Assert.AreEqual(expected, ids[i], $"inhabitant {i}: premise: its personality");
                Assert.AreEqual(RoutinePatterns.Normalize(defs[i].Pattern), r.Pattern, $"{ids[i]}: the routine's pattern is not its level's");
                Assert.AreEqual(defs[i].Seed, r.Seed, $"{ids[i]}: the routine's seed is not its level's");
            }
            Assert.AreEqual(count, ids.Distinct().Count(), "premise: one inhabitant per personality");

            var traces = new RoutineTrace[count];
            for (int i = 0; i < count; i++)
            {
                traces[i] = new RoutineTrace();
            }
            void Watch()
            {
                for (int i = 0; i < count; i++)
                {
                    traces[i].Record(Game.Level.Inhabitants[i].Routine);
                }
            }
            const int Visits = 11;
            Game.FixedStepped += Watch;
            yield return Run(StepsFor(180f), () => traces[pingpong].Dwells.Count >= Visits && traces[wander].Dwells.Count >= Visits
                || Game.State != PlayState.Playing, 8f);
            Game.FixedStepped -= Watch;
            Assert.AreEqual(PlayState.Playing, Game.State, $"premise: the level ended ({Game.LoseReason})");
            Assert.AreEqual(0, Game.AlertCount, "premise: something alerted an inhabitant (its turns would not be routine turns)");
            Assert.AreEqual(0, Game.DiscoveryCount, "premise: the chair was discovered");
            for (int i = 0; i < count; i++)
            {
                Assert.AreEqual(InhabitantMode.Routine, Game.Level.Inhabitants[i].Routine.Mode, $"{ids[i]}: premise: left its routine");
            }

            // The station of every visit, against the order built from the level data.
            for (int i = 0; i < count; i++)
            {
                InhabitantDef def = defs[i];
                var order = new StationOrder(def.Pattern, def.Stations.Count, def.StartStation, def.Seed);
                List<(int visit, int station, Vector3 at)> dwells = traces[i].Dwells;
                Assert.GreaterOrEqual(dwells.Count, i == pingpong || i == wander ? Visits : 3, $"{ids[i]}: premise: too few visits watched");
                Assert.AreEqual(0, dwells[0].visit, $"{ids[i]}: premise: the watch did not start in the first dwell");
                for (int k = 0; k < dwells.Count; k++)
                {
                    (int visit, int station, Vector3 at) = dwells[k];
                    Assert.AreEqual(k, visit, $"{ids[i]}: dwell {k + 1} is visit {visit}: a visit was skipped or repeated");
                    Assert.AreEqual(order.StationOf(visit), station, $"{ids[i]} ({RoutinePatterns.Normalize(def.Pattern)}): visit {visit} dwells at station {station}");
                    Assert.Less(Planar(at, def.Stations[station].Position), 0.05f, $"{ids[i]}: visit {visit} dwells away from station {station}");
                }
                Debug.Log($"[Step37h] {ids[i]} {RoutinePatterns.Normalize(def.Pattern)}: stations {string.Join(",", dwells.Select(d => d.station))}");
            }
            // The check tells the patterns apart: a lost pattern (a loop) or a lost seed (0) gives other stations.
            int[] Stations(string pattern, InhabitantDef def, int seed, int visits)
            {
                var order = new StationOrder(pattern, def.Stations.Count, def.StartStation, seed);
                return Enumerable.Range(0, visits).Select(order.StationOf).ToArray();
            }
            int seenPing = traces[pingpong].Dwells.Count, seenWander = traces[wander].Dwells.Count;
            CollectionAssert.AreNotEqual(Stations(RoutinePatterns.Loop, defs[pingpong], 0, seenPing), Stations(RoutinePatterns.PingPong, defs[pingpong], 0, seenPing),
                "premise: over the watched visits pingpong and loop give the same stations");
            int[] wandered = Stations(RoutinePatterns.Wander, defs[wander], defs[wander].Seed, seenWander);
            CollectionAssert.AreNotEqual(Stations(RoutinePatterns.Loop, defs[wander], 0, seenWander), wandered, "premise: over the watched visits wander and loop give the same stations");
            CollectionAssert.AreNotEqual(Stations(RoutinePatterns.Wander, defs[wander], 0, seenWander), wandered, "premise: over the watched visits the seed changes nothing");

            // The telegraph, the same for every personality: every turn over 30 deg right after one telegraph of 30 steps.
            for (int i = 0; i < count; i++)
            {
                RoutineTrace t = traces[i];
                int n = t.Activity.Count;
                int bodyTurns = 0, headTurns = 0, telegraphs = 0;
                for (int s = 1; s < n; s++)
                {
                    RoutineActivity a = t.Activity[s];
                    if (a == t.Activity[s - 1])
                    {
                        continue;
                    }
                    int e = s;
                    while (e + 1 < n && t.Activity[e + 1] == a)
                    {
                        e++;
                    }
                    if (e == n - 1)
                    {
                        break;
                    }
                    if (a == RoutineActivity.Telegraph)
                    {
                        telegraphs++;
                        Assert.AreEqual(TelegraphSteps, e - s + 1, $"{ids[i]}: a telegraph of {e - s + 1} steps (step {s})");
                        continue;
                    }
                    if (a != RoutineActivity.TurningBody && a != RoutineActivity.TurningHead)
                    {
                        continue;
                    }
                    float turn = a == RoutineActivity.TurningBody
                        ? Mathf.Abs(Mathf.DeltaAngle(t.Body[s - 1], t.Body[e]))
                        : Mathf.Abs(t.Head[e] - t.Head[s - 1]);
                    if (turn <= Tuning.TelegraphMinTurn + 0.5f || s <= TelegraphSteps)
                    {
                        continue;
                    }
                    for (int j = s - TelegraphSteps; j < s; j++)
                    {
                        Assert.AreEqual(RoutineActivity.Telegraph, t.Activity[j], $"{ids[i]}: the {a} of {turn:0.0} deg at step {s} is not after 30 telegraph steps (step {j} is {t.Activity[j]})");
                    }
                    Assert.AreEqual(t.Telegraphs[s - TelegraphSteps - 1] + 1, t.Telegraphs[s - TelegraphSteps], $"{ids[i]}: the telegraph before the turn at step {s} did not start 30 steps before it");
                    Assert.AreEqual(t.Telegraphs[s - TelegraphSteps], t.Telegraphs[s - 1], $"{ids[i]}: more than one telegraph in the 30 steps before the turn at step {s}");
                    if (a == RoutineActivity.TurningBody)
                    {
                        bodyTurns++;
                    }
                    else
                    {
                        headTurns++;
                    }
                }
                bool glances = defs[i].Stations.Any(st => st.Glances.Any(g => Mathf.Abs(g.Yaw) > Tuning.TelegraphMinTurn + 1f));
                Debug.Log($"[Step37h] {ids[i]}: {telegraphs} telegraphs of {TelegraphSteps} steps, {bodyTurns} body and {headTurns} head turns over 30 deg checked over {n} steps");
                Assert.GreaterOrEqual(bodyTurns, 3, $"{ids[i]}: premise: too few body turns over 30 deg to tell");
                if (glances)
                {
                    Assert.GreaterOrEqual(headTurns, 2, $"{ids[i]}: premise: its glances over 30 deg never turned the head");
                }
            }
            AssertClean();
        }

        // =====================================================================================================
        // ----- 38: the dog (CONTRACT_M5_v3 4 and 15.5) -----
        // =====================================================================================================

        // test_m5_game_dog: a 12 x 8 m room; the human at (-5, 3) facing the north wall, the dog at (0, 0) facing east; the
        // chair spawns at (2.5, 0), in the dog's view; the exit at (3.5, -3.45).
        private static readonly Vector3 DogAt = new Vector3(0f, 0f, 0f);

        private Inhabitant Human => Game.Level.Inhabitants[0];

        private IEnumerator LoadDog()
        {
            yield return Load(DogLevel);
            Assert.AreEqual(2, Game.Level.Inhabitants.Count, "premise: a human and the dog");
            Assert.IsFalse(Human.IsDog, "premise: inhabitant 0 is the human");
            Assert.IsTrue(Game.Level.Inhabitants[1].IsDog, "premise: inhabitant 1 is the dog");
            PersonalityDef dog = TheDog.Routine.Personality;
            Assert.IsTrue(dog.Barks && !dog.CountsForCatch && !dog.CountsForExit && !dog.Memory && !dog.Hears, "premise: the dog's row");
            Assert.AreEqual(Tuning.DogEyeHeight, TheDog.Routine.EyeHeight, 1e-4f, "premise: the dog's eye");
        }

        /// <summary>Freezes the human far away facing the north wall: it neither sees, hears nor observes anything.</summary>
        private void PinTheHumanAway()
        {
            Human.Pin(new Vector3(-5.0f, 0f, 3.5f), 0f);
        }

        /// <summary>
        /// Step 38b (CONTRACT_M5_v3 4): seen moving by the dog for the 0.2 s grace, the dog barks once, at the dog (6 m, a Bark
        /// noise event), and a human in Routine within its hearing turns its look toward the bark; the bark is no catch.
        /// </summary>
        [UnityTest]
        public IEnumerator Step38b_DogSeesMovingBarksOnceAtTheDogAndAHumanLooks()
        {
            yield return LoadDog();
            Inhabitant dog = TheDog;
            Inhabitant human = Human;
            dog.Pin(DogAt, 90f);
            var humanAt = new Vector3(0.5f, 0f, 1.6f);
            human.Pin(humanAt, 0f, 0f, true);
            var start = new Vector3(2.5f, 0f, 0f);
            Chair.Teleport(start, 180f);
            yield return Steps(3);
            Assert.IsTrue(VisionOf(dog).SeesPlayer, "premise: the dog sees the chair");
            Assert.IsFalse(Game.Seen, "premise: the human sees the chair");
            Assert.IsTrue(Game.SeenByDog, "premise: SeenByDog");
            Assert.AreEqual(0, Game.BarkCount, "premise: no bark for a still chair");
            Assert.AreEqual(InhabitantMode.Routine, human.Routine.Mode, "premise: the human is in Routine");
            Assert.LessOrEqual(Planar(humanAt, DogAt), Tuning.BarkRadius * human.Routine.HearingFactor - 0.5f, "premise: the human is within hearing of the dog");
            Assert.Greater(Planar(humanAt, start), Tuning.HopNoiseRadius + 0.3f, "premise: the human hears the chair's hops");
            int alerts = Game.AlertCount;
            int barksPlayed = Game.Sfx.BarksPlayed;
            int moved = 0;
            int barkStep = -1;
            void Watch()
            {
                if (Chair.IsMoving)
                {
                    moved++;
                }
                if (barkStep < 0 && Game.BarkCount > 0)
                {
                    barkStep = moved;
                }
            }
            Game.FixedStepped += Watch;
            Chair.ScriptedDirection = Vector3.back;
            yield return Until(() => Game.BarkCount > 0, GraceSteps + 5);
            Chair.ScriptedDirection = null;
            yield return Steps(1);
            Game.FixedStepped -= Watch;
            Assert.AreEqual(1, Game.BarkCount, "seen moving by the dog for the grace: no single bark");
            Assert.AreEqual(GraceSteps, barkStep, "the bark did not come exactly after the grace of seen moving");
            Assert.AreEqual(1, CountNoises(NoiseKind.Bark), "not one Bark noise event");
            NoiseEvent bark = LastNoise(NoiseKind.Bark);
            Assert.AreEqual(Tuning.BarkRadius, bark.Radius, 1e-5f, "the bark radius");
            Assert.Less(Planar(bark.Position, DogAt), 1e-3f, "the bark is not at the dog");
            Assert.Greater(Planar(bark.Position, Chair.transform.position), 2f, "premise: the bark at the dog is far from the chair");
            Assert.Less(Planar(Game.LastBarkAt, DogAt), 1e-3f, "LastBarkAt is not the dog");
            Assert.AreEqual(barksPlayed + 1, Game.Sfx.BarksPlayed, "the bark sound did not play once");
            Assert.AreEqual(PlayState.Playing, Game.State, "a bark is a catch");
            Assert.AreEqual(alerts + 1, Game.AlertCount, "the human did not hear the bark");
            Assert.AreEqual(InhabitantMode.Alerted, human.Routine.Mode, "the human is not alerted by the bark");
            Assert.Less(Planar(human.Routine.AlertSource, DogAt), 1e-3f, "the human does not look toward the bark");
            float toward = YawToward(humanAt, DogAt);
            yield return Until(() => Mathf.Abs(Mathf.DeltaAngle(human.Routine.EyeYaw, toward)) < 3f, StepsFor(3f));
            Assert.Less(Mathf.Abs(Mathf.DeltaAngle(human.Routine.EyeYaw, toward)), 3f, "the human's look never turned toward the dog");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 38c (CONTRACT_M5_v3 4 and 15.5): the chair keeps moving in the dog's view: the first bark comes after the grace,
        /// then the accumulator is held at 0 for the 3 s cooldown, so the second one comes exactly a cooldown and a grace later.
        /// </summary>
        [UnityTest]
        public IEnumerator Step38c_NoSecondBarkWithinTheCooldown()
        {
            yield return LoadDog();
            Inhabitant dog = TheDog;
            dog.Pin(DogAt, 90f);
            PinTheHumanAway();
            Chair.Teleport(new Vector3(2.5f, 0f, 0f), 0f);
            yield return Steps(3);
            Assert.IsTrue(VisionOf(dog).SeesPlayer, "premise: the dog sees the chair");
            Assert.IsFalse(Game.Seen, "premise: the human sees the chair");
            var barks = new List<int>();
            int step = 0;
            int firstMoving = -1;
            bool alwaysMoving = true;
            bool alwaysSeen = true;
            float heldWorst = 0f;
            float angle = 0f;
            void Watch()
            {
                step++;
                if (Game.BarkCount > barks.Count)
                {
                    barks.Add(step);
                }
                if (firstMoving < 0 && Chair.IsMoving)
                {
                    firstMoving = step;
                }
                alwaysMoving &= firstMoving < 0 || Chair.IsMoving;
                alwaysSeen &= VisionOf(dog).SeesPlayer;
                if (barks.Count == 1 && step > barks[0] && step <= barks[0] + CooldownSteps)
                {
                    heldWorst = Mathf.Max(heldWorst, Game.DogSeenMoving(dog));
                }
                angle += 120f * Dt;
                Chair.ScriptedDirection = YawMath.Forward(angle);
            }
            Chair.ScriptedDirection = Vector3.forward;
            Game.FixedStepped += Watch;
            yield return Until(() => barks.Count >= 2, CooldownSteps + 4 * GraceSteps);
            Game.FixedStepped -= Watch;
            Chair.ScriptedDirection = null;
            Assert.IsTrue(alwaysMoving, "premise: the chair stopped during the run");
            Assert.IsTrue(alwaysSeen, "premise: the dog lost sight of the chair");
            Assert.AreEqual(2, barks.Count, "premise: the dog did not bark twice");
            Assert.That(firstMoving, Is.InRange(1, 2), "premise: the chair did not start moving at once");
            Assert.AreEqual(GraceSteps, barks[0] - firstMoving + 1, "the first bark is not one grace after the chair started moving in view");
            Assert.AreEqual(CooldownSteps + GraceSteps, barks[1] - barks[0], "the second bark is not one cooldown and one grace after the first");
            Assert.AreEqual(0f, heldWorst, 1e-6f, "the dog's accumulator ran during the cooldown");
            Assert.AreEqual(PlayState.Playing, Game.State, "the barks caught the chair");
            AssertClean();
        }

        /// <summary>
        /// Step 38d (CONTRACT_M5_v3 4 and 15.5): a still chair seen by the dog, even far out of place, changes nothing: no bark,
        /// no discovery, no suspicion, no alert, no investigation, its accumulator at 0; the dog is never the last seer; the eye
        /// shows the dog's.
        /// </summary>
        [UnityTest]
        public IEnumerator Step38d_StillChairSeenByTheDogChangesNothing()
        {
            yield return LoadDog();
            Inhabitant dog = TheDog;
            dog.Pin(DogAt, 90f, 0f, true);
            PinTheHumanAway();
            Vector3 slot = Game.MemoryOf(Human).PlayerSlot.Position;
            var away = new Vector3(3.5f, 0f, 1.5f);
            Chair.Teleport(away, 30f);
            yield return Steps(2);
            Assert.Greater(Planar(away, slot), 1.5f, "premise: the chair is far out of place");
            Assert.IsTrue(VisionOf(dog).SeesPlayer, "premise: the dog sees the chair");
            Assert.IsFalse(Game.Seen, "premise: the human sees the chair");
            Vector3 dogSlot = Game.MemoryOf(dog).PlayerSlot.Position;
            int alerts = Game.AlertCount;
            bool allDog = true;
            float accumulated = 0f;
            void Watch()
            {
                allDog &= Game.EyeState == HudEye.Dog && Hud.Eye == HudEye.Dog;
                accumulated = Mathf.Max(accumulated, Game.DogSeenMoving(dog));
            }
            Game.FixedStepped += Watch;
            yield return Steps(StepsFor(2f));
            Game.FixedStepped -= Watch;
            Assert.IsTrue(VisionOf(dog).SeesPlayer, "premise: the dog stopped seeing the chair");
            Assert.AreEqual(0, Game.BarkCount, "the dog barked at a still chair");
            Assert.AreEqual(0, Game.DiscoveryCount, "the dog discovered a displaced chair");
            Assert.AreEqual(alerts, Game.AlertCount, "something was alerted");
            Assert.AreEqual(0f, accumulated, 1e-6f, "the dog's accumulator ran for a still chair");
            Assert.AreEqual(Observation.NotSeen, Game.LastObservationOf(dog), "the dog observed the chair");
            Assert.AreEqual(0f, Game.SuspicionOf(dog).Value, 1e-6f, "the dog has a suspicion");
            Assert.AreEqual(0f, Game.MaxSuspicion, 1e-6f, "a suspicion rose");
            Assert.AreEqual(InhabitantMode.Routine, dog.Routine.Mode, "the dog left its routine");
            Assert.AreSame(Human, Game.LastSeer, "the dog is the last seer");
            Assert.Less(Planar(Game.MemoryOf(dog).PlayerSlot.Position, dogSlot), 1e-4f, "the dog's slot moved");
            Assert.IsTrue(allDog, "the eye is not the dog's while only the dog sees the chair");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 38e (CONTRACT_M5_v3 4): the chair drives from its spawn onto the exit in the dog's view the whole way: the dog
        /// barks but never catches (the caught rule never accumulates), discovers nothing, and does not count for the exit: the
        /// level is won while it watches.
        /// </summary>
        [UnityTest]
        public IEnumerator Step38e_DogNeverCatchesNorCountsForTheExit()
        {
            yield return LoadDog();
            Assert.IsTrue(Game.Rules.ExitOnlyUnseen, "premise: the exit counts only unseen");
            Inhabitant dog = TheDog;
            dog.Pin(DogAt, 90f);
            PinTheHumanAway();
            yield return Steps(2);
            Vector3 exit = new Vector3(Game.Def.Exit.X, 0f, Game.Def.Exit.Z);
            float worstSeenMoving = 0f;
            bool dogWatched = true;
            bool humanSaw = false;
            int stepsMoving = 0;
            void Watch()
            {
                if (Game.State != PlayState.Playing && Game.State != PlayState.Won)
                {
                    return;
                }
                worstSeenMoving = Mathf.Max(worstSeenMoving, Game.SeenMoving);
                if (Chair.IsMoving)
                {
                    stepsMoving++;
                    dogWatched &= VisionOf(dog).SeesPlayer;
                }
                humanSaw |= Game.Seen;
            }
            Game.FixedStepped += Watch;
            yield return Until(() =>
            {
                Chair.ScriptedDirection = YawMath.Planar(exit - Chair.transform.position).normalized;
                return Game.State != PlayState.Playing;
            }, StepsFor(6f));
            Game.FixedStepped -= Watch;
            Chair.ScriptedDirection = null;
            Assert.IsFalse(humanSaw, "premise: the human saw the chair");
            Assert.IsTrue(dogWatched, "premise: the dog lost sight of the chair on the way");
            Assert.Greater(stepsMoving, 4 * GraceSteps, "premise: the drive was too short");
            Assert.GreaterOrEqual(Game.BarkCount, 1, "premise: the dog never barked at the moving chair");
            Assert.AreEqual(0f, worstSeenMoving, 1e-6f, "the dog's sighting ran the caught rule");
            Assert.AreEqual(PlayState.Won, Game.State, $"the chair reached the exit in the dog's view and the level was not won ({Game.State}, {Game.LoseReason})");
            Assert.AreEqual(0, Game.DiscoveryCount, "the dog discovered the chair");
            AssertClean();
        }

        /// <summary>
        /// Step 38f (CONTRACT_M5_v3 15.5): HudEye.Dog shows when only the dog sees the chair, with its own sprite whose shape
        /// differs from every other eye (the dog ears); a human seeing the chair in place wins (Calm), the dog seeing it move
        /// alone stays Dog, nobody is Closed.
        /// </summary>
        [UnityTest]
        public IEnumerator Step38f_DogEyeShowsWithItsOwnShape()
        {
            yield return LoadDog();
            Inhabitant dog = TheDog;
            Inhabitant human = Human;
            dog.Pin(DogAt, 90f);
            var humanAt = new Vector3(2.5f, 0f, -3.0f);
            Vector3 chairAt = Game.Def.Player.Position;
            human.Pin(humanAt, YawToward(humanAt, chairAt) + 180f, 0f, true);
            yield return Steps(2);
            Assert.IsTrue(VisionOf(dog).SeesPlayer && !Game.Seen, "premise: only the dog sees the chair");
            Assert.AreEqual(HudEye.Dog, Game.EyeState, "only the dog sees: not the dog eye");
            Assert.AreEqual(HudEye.Dog, Hud.Eye);
            Assert.IsTrue(Hud.EyeOpen, "the dog eye is not an open eye");
            Assert.AreSame(ProceduralArt.EyeDog, Hud.EyeSprite, "the dog eye's sprite");

            const int w = 96, h = 56;
            float[] dogShape = ProceduralArt.EyeCoverage(HudEye.Dog, w, h);
            foreach (HudEye other in new[] { HudEye.Closed, HudEye.Calm, HudEye.Alarm })
            {
                float[] shape = ProceduralArt.EyeCoverage(other, w, h);
                int differ = 0;
                for (int i = 0; i < shape.Length; i++)
                {
                    differ += Mathf.Abs(shape[i] - dogShape[i]) > 0.5f ? 1 : 0;
                }
                Assert.Greater(differ, w * h * 3 / 100, $"the dog eye has the shape of the {other} eye ({differ} pixels differ)");
                Assert.AreNotSame(Hud.SpriteOf(other), ProceduralArt.EyeDog);
            }

            human.Pin(humanAt, YawToward(humanAt, chairAt), 0f, true);
            yield return Steps(2);
            Assert.IsTrue(Game.Seen && VisionOf(dog).SeesPlayer, "premise: both see the chair");
            Assert.AreEqual(Observation.Confirmed, Game.LastObservationOf(human), "premise: the human finds the chair in place");
            Assert.AreEqual(HudEye.Calm, Hud.Eye, "a human seeing the chair in place does not win over the dog");

            human.Pin(humanAt, YawToward(humanAt, chairAt) + 180f, 0f, true);
            Chair.ScriptedDirection = Vector3.forward;
            yield return Steps(4);
            Assert.IsTrue(Chair.IsMoving && !Game.Seen && Game.SeenByDog, "premise: only the dog sees the chair move");
            Assert.AreEqual(HudEye.Dog, Hud.Eye, "seen moving by the dog alone is not the dog eye");
            Chair.ScriptedDirection = null;
            yield return Steps(2);

            dog.Pin(DogAt, 270f);
            yield return Steps(2);
            Assert.IsFalse(Game.Seen || Game.SeenByDog, "premise: nobody sees the chair");
            Assert.AreEqual(HudEye.Closed, Hud.Eye, "nobody sees: not closed");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 38g (CONTRACT_M5_v3 4 and 15.5, step 38 of v3 11; wave 5A.1, critique M3): a sleeping dog sees nothing. On the
        /// watchers' test_m5_watchers_dog the dog starts asleep at (0, 1.5) facing south, the chair 3 m ahead. The chair drives
        /// in circles in front of it for the whole sleep, its wake telegraph included: on every one of those fixed steps the
        /// chair moves and its samples are in the dog's cone, unoccluded (what the awake dog would see), yet the dog's Vision
        /// does not see it, Game.SeenByDog is false, the HUD eye is Closed and no bark comes. The control: on its first awake
        /// step, still facing south (its departure telegraph), the dog sees the moving chair, the eye is the dog's, and it
        /// barks once the grace has passed.
        /// </summary>
        [UnityTest]
        public IEnumerator Step38g_SleepingDogSeesNothing()
        {
            yield return Load(SleepLevel);
            Assert.AreEqual(1, Game.Level.Inhabitants.Count, "premise: the dog alone");
            Inhabitant dog = TheDog;
            Assert.IsNotNull(dog, "premise: the fixture's inhabitant is the dog");
            InhabitantRoutine r = dog.Routine;
            Vision vision = VisionOf(dog);
            Assert.IsNotNull(vision, "premise: the dog has its vision");
            Assert.IsTrue(r.Asleep, "premise: the dog starts asleep");
            Assert.IsTrue(Game.Def.Inhabitants[0].Stations[r.StationIndex].Sleep, "premise: the dog is at its sleep station");
            Assert.AreEqual(HudEye.Closed, Hud.Eye, "premise: the eye starts closed");
            Assert.AreEqual(0, Game.BarkCount, "premise: no bark yet");

            var samples = new Vector3[Tuning.SampleCount];
            bool InTheDogsView()
            {
                Chair.GetSamplePoints(samples);
                return Vision.Test(dog.EyePosition, dog.EyeForward, samples, r.ViewRange * Chair.SightRangeFactor, r.HalfAngle, null);
            }
            float angle = 0f;
            void Drive()
            {
                angle += 120f * Dt;
                Chair.ScriptedDirection = YawMath.Forward(angle);
            }
            Chair.ScriptedDirection = Vector3.forward;
            Game.FixedStepped += Drive;
            yield return Steps(2);
            Assert.IsTrue(r.Asleep, "premise: the dog woke before the watch");
            Assert.IsTrue(Chair.IsMoving, "premise: the chair does not move");

            int asleep = 0, waking = 0, still = 0, outOfView = 0, seen = 0, seenByDog = 0, notClosed = 0;
            string firstFault = null;
            int awake = 0;
            bool controlInView = false, controlSees = false, controlByDog = false;
            HudEye controlEye = HudEye.Closed;
            int barksAtWake = -1;
            void Watch()
            {
                if (r.Asleep)
                {
                    asleep++;
                    waking += r.IsTelegraphing ? 1 : 0;
                    still += Chair.IsMoving ? 0 : 1;
                    outOfView += InTheDogsView() ? 0 : 1;
                    bool sees = vision.SeesPlayer;
                    bool byDog = Game.SeenByDog;
                    bool closed = Game.EyeState == HudEye.Closed && Hud.Eye == HudEye.Closed;
                    seen += sees ? 1 : 0;
                    seenByDog += byDog ? 1 : 0;
                    notClosed += closed ? 0 : 1;
                    if (firstFault == null && (sees || byDog || !closed || Game.BarkCount > 0))
                    {
                        firstFault = $"asleep step {asleep}: SeesPlayer {sees}, SeenByDog {byDog}, eye {Game.EyeState} / {Hud.Eye}, barks {Game.BarkCount}";
                    }
                    return;
                }
                awake++;
                if (awake == 1)
                {
                    controlInView = Chair.IsMoving && InTheDogsView();
                    controlSees = vision.SeesPlayer;
                    controlByDog = Game.SeenByDog;
                    controlEye = Hud.Eye;
                    barksAtWake = Game.BarkCount;
                }
            }
            Game.FixedStepped += Watch;
            yield return Until(() => awake >= GraceSteps + 2 || Game.State != PlayState.Playing, StepsFor(2.6f + 2f));
            Game.FixedStepped -= Watch;
            Game.FixedStepped -= Drive;
            Chair.ScriptedDirection = null;
            Debug.Log($"[Step38g] {asleep} asleep steps watched ({waking} of the wake telegraph), then {awake} awake; control: sees {controlSees}, eye {controlEye}, barks {Game.BarkCount}");
            Assert.AreEqual(PlayState.Playing, Game.State, "the run ended");
            Assert.Greater(asleep, StepsFor(1.5f), "premise: too short a sleep was watched");
            Assert.GreaterOrEqual(waking, WakeSteps - 1, "premise: the wake telegraph was not watched");
            Assert.AreEqual(0, still, "premise: the chair stopped during the sleep");
            Assert.AreEqual(0, outOfView, "premise: the chair left the cone the awake dog would see it in");
            Assert.IsNull(firstFault, "a sleeping dog sees: " + firstFault);
            Assert.AreEqual(0, seen, "the sleeping dog's Vision saw the chair");
            Assert.AreEqual(0, seenByDog, "SeenByDog while the dog sleeps");
            Assert.AreEqual(0, notClosed, "the HUD eye is not closed while only a sleeping dog faces the chair");

            Assert.GreaterOrEqual(awake, GraceSteps + 2, "premise: the dog never woke");
            Assert.IsTrue(controlInView, "premise: on its first awake step the moving chair is not in the dog's view");
            Assert.AreEqual(0, barksAtWake, "a bark before the dog woke");
            Assert.IsTrue(controlSees, "control: awake, the dog does not see the moving chair in its cone");
            Assert.IsTrue(controlByDog, "control: awake, SeenByDog is false");
            Assert.AreEqual(HudEye.Dog, controlEye, "control: awake, the eye is not the dog's");
            Assert.AreEqual(1, Game.BarkCount, "control: awake and seeing the chair move for the grace, the dog did not bark once");
            AssertClean();
        }

        /// <summary>The human in a reactive pin far away, facing the north wall: it sees nothing but can be sent.</summary>
        private Vector3 PinTheHumanAwayReactive()
        {
            var humanAt = new Vector3(-5.0f, 0f, 3.5f);
            Human.Pin(humanAt, 0f, 0f, true);
            return humanAt;
        }

        /// <summary>Moves the chair in the dog's view until the dog barks, then stops it; asserts the premise of one bark.</summary>
        private IEnumerator MoveUntilTheDogBarks(Vector3 direction)
        {
            Assert.IsTrue(VisionOf(TheDog).SeesPlayer, "premise: the dog sees the chair");
            Assert.IsFalse(Game.Seen, "premise: the human sees the chair");
            Assert.AreEqual(InhabitantMode.Routine, TheDog.Routine.Mode, "premise: the dog is in its routine");
            Assert.IsFalse(TheDog.Routine.Asleep, "premise: the dog is awake");
            Chair.ScriptedDirection = direction;
            yield return Until(() => Game.BarkCount > 0 || Game.State != PlayState.Playing, GraceSteps + 5);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: the run was caught");
            Assert.AreEqual(1, Game.BarkCount, "premise: the dog did not bark");
        }

        /// <summary>
        /// Step 38h (CONTRACT_M5 20, the product owner's "the dog does nothing when it detects you", then DOGCARRY's "when it
        /// catches you, it brings you back like a human would"): the chair, far out of place and in the awake dog's view only,
        /// moves for the grace. The dog barks and runs to it ("!" over it), pins it next to itself (the move input does nothing,
        /// the dog hold line shows, not the sat-on one) and barks at it (sounds only: no new bark of the rule, no new noise
        /// event). After Tuning.DogGripTime it grips it and drags it back itself: no human is called (the human, pinned far
        /// away, never investigates), the dog is the carrier, the chair follows its carry anchor (the move input does nothing),
        /// and the human makes his discovery (one, his suspicion rises) as if he had come. The chair is put down on the human's
        /// slot; the dog barks once, wags, and goes back to its routine; the move input works again; the level is still playing.
        /// </summary>
        [UnityTest]
        public IEnumerator Step38h_DogPinsTheChairAndDragsItBackItself()
        {
            yield return LoadDog();
            Inhabitant dog = TheDog;
            Inhabitant human = Human;
            PinTheHumanAwayReactive();
            Vector3 slot = Game.MemoryOf(human).PlayerSlot.Position;
            var away = new Vector3(3.5f, 0f, 1.5f);
            Chair.Teleport(away, 0f);
            yield return Steps(3);
            Assert.Greater(Planar(away, slot), Game.MemoryOf(human).Tolerance + 0.5f, "premise: the chair is not far out of place");
            int barksPlayed = Game.Sfx.BarksPlayed;
            yield return MoveUntilTheDogBarks(Vector3.forward);
            yield return Steps(1);
            Assert.AreSame(dog, Game.HoldingDog, "the bark did not send the dog to the chair");
            Assert.IsTrue(dog.Routine.Running, "the dog is not running to the chair");
            Assert.AreEqual(InhabitantMode.Investigating, dog.Routine.Mode, "the running dog is not in the investigating mode");
            Assert.IsFalse(Game.HeldByDog, "the chair was held before the dog got there");
            Assert.IsFalse(Chair.Pinned, "the chair was pinned before the dog got there");

            bool humanSent = false;
            void WatchHuman() => humanSent |= human.Routine.Mode == InhabitantMode.Investigating || Game.DogCaller != null;
            Game.FixedStepped += WatchHuman;

            Vector3 dogFrom = dog.Routine.Position;
            int stepsRunning = fixedSteps;
            yield return Until(() => Game.HeldByDog, StepsFor(5f));
            stepsRunning = fixedSteps - stepsRunning;
            Assert.IsTrue(Game.HeldByDog, "the dog never got to the chair");
            float reach = Tuning.InvestigateReach + Tuning.CarryReachMargin;
            Assert.LessOrEqual(Planar(dog.Routine.Position, Chair.transform.position), reach + 1e-3f, "the dog holds the chair from afar");
            float run = Planar(dogFrom, dog.Routine.Position);
            Assert.Greater(run / (stepsRunning * Dt), Tuning.ChairMaxSpeed, $"the dog ran {run:0.00} m in {stepsRunning * Dt:0.00} s: not faster than the chair");
            Assert.IsTrue(Chair.Pinned, "the held chair is not pinned");
            Assert.AreEqual(1, Game.DogHoldCount, "not one hold");
            Assert.IsFalse(Game.DraggedByDog, "the dog dragged the chair without gripping it first");
            yield return null;
            Assert.AreEqual(Inhabitant.MarkerKind.Exclamation, dog.Marker, "no \"!\" over the dog that holds the chair");

            // The grip beat: pinned, the move input does nothing (shorter than DogGripTime, so the drag has not begun).
            Vector3 heldAt = Chair.transform.position;
            bool everMoving = false;
            void Held() => everMoving |= Chair.IsMoving;
            Game.FixedStepped += Held;
            Chair.ScriptedDirection = Vector3.back;
            yield return Steps(Mathf.Max(1, StepsFor(Tuning.DogGripTime * 0.4f)));
            Chair.ScriptedDirection = null;
            Game.FixedStepped -= Held;
            Assert.IsTrue(Game.HeldByDog && !Game.DraggedByDog, "premise: the grip beat ended early");
            Assert.Less(Planar(Chair.transform.position, heldAt), 1e-3f, "the held chair moved");
            Assert.IsFalse(everMoving, "the held chair was moving");
            Assert.IsTrue(Hud.DogHoldVisible, "the dog hold line does not show");
            Assert.IsFalse(Hud.SatOnVisible, "the sat-on line shows for the dog's hold");
            Assert.AreEqual(1, Game.BarkCount, "the hold's barks counted as barks of the rule");
            Assert.AreEqual(1, CountNoises(NoiseKind.Bark), "the hold's barks are noise events");
            Assert.GreaterOrEqual(Game.Sfx.BarksPlayed - barksPlayed, 2, "the dog does not bark at the chair it holds");
            Assert.AreEqual(0, Game.DiscoveryCount, "premise: a discovery before the dog gripped the chair");

            // The drag: the dog is the carrier, nobody is called, the human's discovery is made at the grip.
            yield return Until(() => Game.DraggedByDog || Game.State != PlayState.Playing, StepsFor(Tuning.DogGripTime + 1f));
            Assert.AreEqual(PlayState.Playing, Game.State, $"the grip lost the level ({Game.LoseReason})");
            Assert.IsTrue(Game.DraggedByDog, "the dog never dragged the chair");
            Assert.AreSame(dog, Game.Carrier, "the dragging dog is not the carrier");
            Assert.IsNull(Game.DogCaller, "a human was called although the dog drags the chair");
            Assert.AreEqual(1, Game.DogDragCount, "not one drag");
            Assert.AreEqual(0, Game.DogDragFallbackCount, "the dog fell back on a human in an open room");
            Assert.AreEqual(1, Game.DiscoveryCount, "the drag is not the human's one discovery");
            Assert.AreEqual(1, Game.DogHoldDiscoveryCount, "the discovery is not the hold's");
            Assert.Greater(Game.SuspicionOf(human).Value, 0.2f, "the human's suspicion did not rise");

            float worstFollow = 0f;
            float highest = 0f;
            int carriedSteps = 0;
            void Drag()
            {
                if (!Chair.Carried || dog.Routine.LastActivity != RoutineActivity.Carrying)
                {
                    return;
                }
                carriedSteps++;
                worstFollow = Mathf.Max(worstFollow, Planar(Chair.transform.position, dog.Routine.CarryAnchor));
                highest = Mathf.Max(highest, Chair.transform.position.y - Game.Level.Floor.OnFloor(YawMath.Planar(Chair.transform.position)).y);
            }
            Game.FixedStepped += Drag;
            Chair.ScriptedDirection = Vector3.left;
            yield return Until(() => Game.HoldingDog == null || Game.State != PlayState.Playing, StepsFor(40f));
            Chair.ScriptedDirection = null;
            Game.FixedStepped -= Drag;
            Game.FixedStepped -= WatchHuman;
            Assert.AreEqual(PlayState.Playing, Game.State, $"the drag lost the level ({Game.LoseReason})");
            Assert.IsNull(Game.HoldingDog, "the hold never ended");
            Assert.Greater(carriedSteps, StepsFor(0.5f), "premise: the drag was too short to watch");
            Assert.Less(worstFollow, 2f * Tuning.DogDragSpeed * Dt + 0.01f, "the dragged chair left the dog's mouth (the input or physics moved it)");
            Assert.Less(highest, Tuning.CarryHeight, "the dog lifted the chair like a human instead of dragging it");
            Assert.IsFalse(humanSent, "a human was sent to the chair the dog dragged");
            Assert.AreEqual(1, Game.CarryCount, "the dog did not carry the chair back");
            Assert.AreEqual(1, Game.DiscoveryCount, "the put back cost another discovery");
            Assert.AreEqual(0, Game.DogCallCount, "a human was called");
            Assert.Less(Planar(Chair.transform.position, slot), 0.05f, "the chair is not back at the human's slot");
            Assert.Less(Mathf.Abs(Mathf.DeltaAngle(Game.MemoryOf(human).PlayerSlot.Yaw, Chair.Yaw)), 0.5f, "the chair is not back at the slot's yaw");
            Assert.IsFalse(Chair.Carried, "the chair is still carried");
            Assert.IsFalse(Chair.Pinned, "the dog did not let go");
            Assert.IsFalse(Game.HeldByDog, "still held after the put down");
            Assert.IsFalse(Game.DraggedByDog, "still dragged after the put down");
            yield return Until(() => dog.Routine.Mode == InhabitantMode.Routine, StepsFor(Tuning.DogWagTime + 1f));
            Assert.AreEqual(InhabitantMode.Routine, dog.Routine.Mode, "the dog did not go back to its routine");
            Assert.IsFalse(dog.Routine.Running, "the dog still runs");
            Assert.AreNotEqual(InhabitantMode.Investigating, human.Routine.Mode, "the human investigates");
            yield return null;
            Assert.IsFalse(Hud.DogHoldVisible, "the dog hold line still shows");

            Vector3 back = Chair.transform.position;
            Chair.ScriptedDirection = Vector3.back;
            yield return Steps(GraceSteps - 2);
            Chair.ScriptedDirection = null;
            Assert.Greater(Planar(Chair.transform.position, back), 0.01f, "the chair stays stuck after the drag");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 38i (CONTRACT_M5 20, DOGCARRY): the dog sees the chair move but it stays within the human's tolerance of its
        /// slot. The dog runs and pins it; at the grip, the chair is in place for the human: no drag, nobody called, no
        /// discovery, no suspicion, no carry; the dog lets go and goes back to its routine.
        /// </summary>
        [UnityTest]
        public IEnumerator Step38i_DogHoldOfAChairInPlaceCostsNothing()
        {
            yield return LoadDog();
            Inhabitant dog = TheDog;
            Inhabitant human = Human;
            PinTheHumanAwayReactive();
            Vector3 slot = Game.MemoryOf(human).PlayerSlot.Position;
            yield return MoveUntilTheDogBarks(Vector3.right);
            Assert.Less(Planar(Chair.transform.position, slot), Game.MemoryOf(human).Tolerance - 0.3f, "premise: the chair left its place");
            yield return Until(() => Game.HeldByDog, StepsFor(5f));
            Assert.IsTrue(Game.HeldByDog && Chair.Pinned, "the dog never held the chair");
            bool dragged = false;
            void Watch() => dragged |= Game.DraggedByDog || Chair.Carried || Game.DogCaller != null;
            Game.FixedStepped += Watch;
            yield return Until(() => Game.HoldingDog == null || Game.State != PlayState.Playing, StepsFor(Tuning.DogGripTime + 2f));
            Game.FixedStepped -= Watch;
            Assert.AreEqual(PlayState.Playing, Game.State, $"the hold lost the level ({Game.LoseReason})");
            Assert.IsNull(Game.HoldingDog, "the hold never ended");
            Assert.IsFalse(dragged, "a chair in place was dragged, carried, or a human was called");
            Assert.AreEqual(0, Game.DogDragCount, "a chair in place was dragged");
            Assert.AreEqual(0, Game.DogCallCount, "a human was called");
            Assert.AreEqual(0, Game.DiscoveryCount, "a chair in place cost a discovery");
            Assert.AreEqual(0f, Game.MaxSuspicion, 1e-6f, "a chair in place raised a suspicion");
            Assert.AreEqual(0, Game.CarryCount, "a chair in place was carried");
            Assert.IsFalse(Chair.Pinned, "the dog did not let go");
            Assert.AreEqual(InhabitantMode.Routine, dog.Routine.Mode, "the dog did not go back to its routine");
            Assert.AreNotEqual(InhabitantMode.Investigating, human.Routine.Mode, "the human was sent");
            AssertClean();
        }

        // =====================================================================================================
        // ----- 42: the robot (CONTRACT_M5 4, 16.8) -----
        // =====================================================================================================

        // test_m5_game_robot: a 10 x 8 m room. The chair spawns at (0, 2) facing +z, and Assis sits on it (its seat home is the
        // spawn) after a 1 s dwell at (-3.5, 3). Temoin dwells at (4, -0.5). The robot Robi runs there and back between
        // (-4, -2) and (4, -2) at 0.4 m/s, from (-4, -2) at time 0.
        private const string RobotLevel = "test_m5_game_robot";

        private static int PushSteps => Mathf.RoundToInt(Tuning.RobotPushTime / Dt);

        private Inhabitant Assis => Game.Level.Inhabitants[0];

        private Inhabitant Temoin => Game.Level.Inhabitants[1];

        private Robot TheRobot()
        {
            Assert.AreEqual(1, Game.Robots.Count, "premise: the level has one robot");
            Robot robot = Game.Robots[0];
            Assert.IsNotNull(robot, "premise: the robot exists");
            Assert.IsTrue(Game.Level.Robots.Contains(robot), "the robot is not listed in LevelInstance.Robots");
            return robot;
        }

        private IEnumerator LoadRobot()
        {
            yield return Load(RobotLevel);
            Assert.AreEqual(2, Game.Level.Inhabitants.Count, "premise: Assis and Temoin");
            TheRobot();
        }

        /// <summary>Freezes both inhabitants facing the north wall, far from the robot's line: nobody sees, hears or sits.</summary>
        private void PinRobotWatchersAway()
        {
            Assis.Pin(new Vector3(-4.0f, 0f, 3.5f), 0f);
            Temoin.Pin(new Vector3(4.0f, 0f, 3.5f), 0f);
        }

        /// <summary>Puts the chair on the robot's way, facing its heading, its near face <paramref name="gap"/> ahead of the robot's disc.</summary>
        private Vector3 ChairAheadOf(Robot robot, float gap)
        {
            Vector3 heading = robot.Path.ForwardAt(Game.RobotTime);
            Vector3 at = YawMath.Planar(robot.Position) + heading * (Tuning.RobotRadius + gap + Chair.SampleSize.z * 0.5f);
            Chair.Teleport(at, YawMath.YawOf(heading));
            return at;
        }

        /// <summary>
        /// A test block (a furniture-layer box: it stops the chair and hides nothing) touching the chair's front along
        /// <paramref name="heading"/>, so a shove that way cannot move the chair. The caller destroys it.
        /// </summary>
        private GameObject BlockAhead(Vector3 heading)
        {
            var block = GameObject.CreatePrimitive(PrimitiveType.Cube);
            block.name = "TestShoveBlock";
            block.layer = Layers.Furniture;
            block.transform.SetPositionAndRotation(
                YawMath.Planar(Chair.transform.position) + heading * (Chair.Body.Radius + 0.005f + 0.25f) + Vector3.up * 0.5f,
                Quaternion.LookRotation(heading));
            block.transform.localScale = new Vector3(1.2f, 1f, 0.5f);
            Physics.SyncTransforms();
            return block;
        }

        /// <summary>
        /// Step 42b (CONTRACT_M5 4, 16.8): the robot runs into the still chair: one contact, one accepted shove. From the next
        /// step, exactly round(RobotPushTime / dt) (25) steps slide the chair 0.01 m each along the robot's heading (0.25 m in
        /// all), every one of them a shove step and moving, a move key held meanwhile changing nothing; on the step after,
        /// the chair is still. Nobody sees it: no catch. Then shoved into a block it cannot move: the 25 shove steps are still
        /// moving (the shove is moving through the push action, not through travel), and the step after is still.
        /// </summary>
        [UnityTest]
        public IEnumerator Step42b_ContactShovesAQuarterMetreInHalfASecondMoving()
        {
            yield return LoadRobot();
            Robot robot = TheRobot();
            PinRobotWatchersAway();
            yield return Steps(2);
            Vector3 heading = robot.Path.ForwardAt(Game.RobotTime);
            Assert.Greater(heading.x, 0.99f, "premise: the robot heads +x");
            Vector3 start = ChairAheadOf(robot, 0.05f);
            Assert.AreEqual(0, Game.RobotContactCount, "premise: no contact yet");
            Assert.AreEqual(25, PushSteps, "premise: a shove is 25 steps");
            var positions = new List<Vector3>();
            var shoving = new List<bool>();
            var moving = new List<bool>();
            int contactStep = -1;
            int step = 0;
            void Watch()
            {
                step++;
                if (contactStep < 0 && Game.RobotContactCount > 0)
                {
                    contactStep = step;
                }
                if (contactStep < 0)
                {
                    return;
                }
                positions.Add(Chair.transform.position);
                shoving.Add(Game.Shoving);
                moving.Add(Game.FurnitureMoving);
                int k = step - contactStep;
                // A move key held in the middle of the shove: the input is ignored.
                Chair.ScriptedDirection = k >= 4 && k < 15 ? Vector3.back : (Vector3?)null;
            }
            Game.FixedStepped += Watch;
            yield return Until(() => contactStep >= 0 && step >= contactStep + PushSteps + 3, StepsFor(2f));
            Game.FixedStepped -= Watch;
            Chair.ScriptedDirection = null;
            Assert.GreaterOrEqual(contactStep, 1, "the robot never touched the chair");
            Assert.AreEqual(1, Game.RobotContactCount, "not one contact");
            Assert.AreEqual(1, Game.ShoveCount, "the contact did not shove the still chair once");
            Assert.Less(Planar(positions[0], start), 1e-4f, "the chair moved before the shove");
            Assert.IsFalse(shoving[0], "the contact step itself is a shove step");
            for (int k = 1; k <= PushSteps; k++)
            {
                Assert.IsTrue(shoving[k], $"shove step {k} is not a shove step");
                Assert.IsTrue(moving[k], $"shove step {k} is not moving");
                Vector3 d = YawMath.Planar(positions[k] - positions[k - 1]);
                Assert.AreEqual(Tuning.RobotPushDistance / PushSteps, Vector3.Dot(d, heading), 1e-3f, $"shove step {k} did not slide 0.01 m along the heading");
                Assert.Less(Vector3.Cross(d, heading).magnitude, 1e-3f, $"shove step {k} slid off the heading (the held key moved it)");
            }
            Vector3 total = YawMath.Planar(positions[PushSteps] - positions[0]);
            Assert.AreEqual(Tuning.RobotPushDistance, Vector3.Dot(total, heading), 0.005f, "the shove is not 0.25 m");
            Assert.IsFalse(shoving[PushSteps + 1], "the shove lasted more than 0.5 s");
            Assert.IsFalse(moving[PushSteps + 1], "the chair is not still on the step after the shove");
            Assert.Less(Planar(positions[PushSteps + 1], positions[PushSteps]), 1e-4f, "the chair kept sliding after the shove");
            Assert.Less((Game.LastShoveDirection - heading).magnitude, 1e-3f, "the shove is not along the robot's heading");
            Assert.AreEqual(PlayState.Playing, Game.State, "an unseen shove was caught");

            // 2. Shoved into a block: no travel, still moving on every shove step.
            yield return Restart();
            robot = TheRobot();
            PinRobotWatchersAway();
            yield return Steps(2);
            heading = robot.Path.ForwardAt(Game.RobotTime);
            Assert.Greater(heading.x, 0.99f, "premise: the robot heads +x again");
            start = ChairAheadOf(robot, 0.05f);
            GameObject block = BlockAhead(heading);
            var blockedMoving = new List<bool>();
            var blockedShoving = new List<bool>();
            var blockedAt = new List<Vector3>();
            int blockedContact = -1;
            int blockedStep = 0;
            void WatchBlocked()
            {
                blockedStep++;
                if (blockedContact < 0 && Game.RobotContactCount > 0)
                {
                    blockedContact = blockedStep;
                }
                if (blockedContact >= 0)
                {
                    blockedMoving.Add(Game.FurnitureMoving);
                    blockedShoving.Add(Game.Shoving);
                    blockedAt.Add(Chair.transform.position);
                }
            }
            Game.FixedStepped += WatchBlocked;
            yield return Until(() => blockedContact >= 0 && blockedStep >= blockedContact + PushSteps + 3, StepsFor(2f));
            Game.FixedStepped -= WatchBlocked;
            UnityEngine.Object.Destroy(block);
            Assert.GreaterOrEqual(blockedContact, 1, "blocked: the robot never touched the chair");
            Assert.AreEqual(1, Game.ShoveCount, "blocked: the contact did not shove the chair once");
            Assert.Less(Planar(blockedAt[PushSteps], blockedAt[0]), 0.02f, "premise: the block did not stop the shove");
            for (int k = 1; k <= PushSteps; k++)
            {
                Assert.IsTrue(blockedShoving[k], $"blocked: shove step {k} is not a shove step");
                Assert.IsTrue(blockedMoving[k], $"blocked: shove step {k} into the block is not moving");
            }
            Assert.IsFalse(blockedShoving[PushSteps + 1] || blockedMoving[PushSteps + 1], "blocked: the chair is not still after the shove");
            Assert.AreEqual(PlayState.Playing, Game.State, "an unseen blocked shove was caught");
            AssertClean();
        }

        /// <summary>
        /// Step 42c (CONTRACT_M5 4, PRD 4.8, 19): being shoved is moving, even against a block that stops the slide: Temoin
        /// watches the still chair (seen, no catch), the robot runs into it, and the chair, which cannot move, is caught on the
        /// grace-th shove step (the 10th), seen on every one of them. The contact plays the bump once.
        /// </summary>
        [UnityTest]
        public IEnumerator Step42c_SeenWhileShovedIsCaught()
        {
            yield return LoadRobot();
            Robot robot = TheRobot();
            Assis.Pin(new Vector3(-4.0f, 0f, 3.5f), 0f);
            yield return Steps(2);
            Vector3 at = ChairAheadOf(robot, 0.05f);
            // A block touching the chair's front: the shove cannot move it, so only the push action makes it moving.
            GameObject block = BlockAhead(robot.Path.ForwardAt(Game.RobotTime));
            var eye = at + new Vector3(0.6f, 0f, 3.0f);
            Temoin.Pin(eye, YawToward(eye, at));
            yield return Steps(1);
            Assert.IsTrue(Game.Seen, "premise: Temoin sees the chair");
            Assert.IsFalse(Game.FurnitureMoving, "premise: the chair is still");
            Assert.AreEqual(0, Game.RobotContactCount, "premise: no contact yet");
            int bumps = Game.Sfx.BumpsPlayed;
            int shoveSteps = 0;
            bool seenEach = true;
            void Watch()
            {
                if (Game.Shoving)
                {
                    shoveSteps++;
                    seenEach &= Game.Seen;
                }
            }
            Game.FixedStepped += Watch;
            yield return Until(() => Game.State != PlayState.Playing, StepsFor(2f));
            Game.FixedStepped -= Watch;
            UnityEngine.Object.Destroy(block);
            Assert.AreEqual(1, Game.ShoveCount, "premise: the robot did not shove the chair");
            Assert.Less(Planar(Chair.transform.position, at), 0.02f, "premise: the block did not stop the shove");
            Assert.IsTrue(seenEach, "premise: Temoin lost sight of the shoved chair");
            Assert.AreEqual(PlayState.Caught, Game.State, "the chair shoved in Temoin's view was not caught");
            Assert.AreEqual(LoseReason.SeenMoving, Game.LoseReason);
            Assert.AreEqual(GraceSteps, shoveSteps, "the catch did not come after the grace of the shove");
            Assert.AreEqual(1, Game.RobotContactCount, "premise: not one contact");
            Assert.AreEqual(bumps + 1, Game.Sfx.BumpsPlayed, "the robot's contact did not play the bump once");
            AssertClean();
        }

        /// <summary>
        /// Step 42d (CONTRACT_M5 4): until its contact the robot keeps to its fixed timeline (a fresh RobotPath of its def at
        /// RobotTime, on every step); at the contact it reverses once, at that time: it now runs its loop backwards, turned
        /// round, and goes back the way it came, away from the chair, with no second contact.
        /// </summary>
        [UnityTest]
        public IEnumerator Step42d_TheRobotKeepsItsTimelineThenReverses()
        {
            yield return LoadRobot();
            Robot robot = TheRobot();
            PinRobotWatchersAway();
            var fresh = new RobotPath(Game.Def.Robots[0]);
            float worst = 0f;
            int checkedSteps = 0;
            void Timeline()
            {
                if (Game.RobotContactCount == 0)
                {
                    worst = Mathf.Max(worst, Planar(robot.Position, fresh.PositionAt(Game.RobotTime)));
                    worst = Mathf.Max(worst, Mathf.Abs(Mathf.DeltaAngle(robot.Yaw, fresh.HeadingAt(Game.RobotTime))) * 1e-3f);
                    checkedSteps++;
                }
            }
            Game.FixedStepped += Timeline;
            yield return Steps(StepsFor(1f));
            float yawBefore = robot.Yaw;
            Vector3 chairAt = ChairAheadOf(robot, 0.05f);
            yield return Until(() => Game.RobotContactCount > 0, StepsFor(1f));
            Game.FixedStepped -= Timeline;
            Assert.AreEqual(1, Game.RobotContactCount, "the robot never touched the chair");
            Assert.Greater(checkedSteps, StepsFor(1f) - 2, "premise: the timeline was not watched");
            Assert.Less(worst, 1e-4f, "before its contact the robot left its fixed timeline");
            Assert.AreEqual(1, robot.Path.ReverseCount, "the robot did not reverse once");
            Assert.AreEqual(Game.RobotTime, robot.Path.LastReverseTime, 1e-4f, "the robot did not reverse at the contact");
            Assert.AreEqual(-1, robot.Path.DirectionAt(Game.RobotTime), "the robot does not run its loop backwards");
            Assert.AreEqual(180f, Mathf.Abs(Mathf.DeltaAngle(yawBefore, robot.Yaw)), 1f, "the robot did not turn round");
            Vector3 contactAt = robot.Position;
            yield return Steps(StepsFor(1f));
            Assert.AreEqual(1, Game.RobotContactCount, "a second contact");
            Assert.Less(robot.Position.x, contactAt.x - 0.35f, "the robot did not go back the way it came");
            Assert.Greater(Planar(robot.Position, Chair.transform.position), Planar(contactAt, chairAt) + 0.5f, "the robot did not move away from the chair");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 42e (CONTRACT_M5 4, 16.8): no shove while pinned. The robot's loop is moved through the seat home (a test edit:
        /// the validator keeps it 1 m away), Assis sits on the chair, and the robot runs into it: a contact and a reversal, but
        /// no shove, and the pinned chair never moves.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step42e_NoShoveWhilePinned()
        {
            yield return Load(RobotLevel);
            RobotDef def = Game.Def.Robots[0];
            def.Loop[0].X = -4.5f;
            def.Loop[0].Z = 2.0f;
            def.Loop[1].X = 4.5f;
            def.Loop[1].Z = 2.0f;
            yield return Restart();
            Robot robot = TheRobot();
            Temoin.Pin(new Vector3(4.0f, 0f, -3.5f), 180f);
            Assert.AreEqual(2.0f, robot.Path.PositionAt(0f).z, 1e-4f, "premise: the robot runs through the seat home");
            yield return Run(StepsFor(14f), () => Chair.Pinned || Game.RobotContactCount > 0, 4f);
            Assert.AreEqual(0, Game.RobotContactCount, "premise: the robot came before the sit");
            Assert.IsTrue(Chair.Pinned, "premise: Assis never sat on the chair");
            Vector3 seat = Chair.transform.position;
            int moving = 0;
            void Watch()
            {
                if (Game.FurnitureMoving || Game.Shoving || Chair.IsMoving)
                {
                    moving++;
                }
            }
            Game.FixedStepped += Watch;
            yield return Run(StepsFor(10f), () => Game.RobotContactCount > 0, 4f);
            Assert.AreEqual(1, Game.RobotContactCount, "the robot never reached the pinned chair");
            Assert.IsTrue(Chair.Pinned, "premise: the chair was not pinned at the contact");
            yield return Steps(PushSteps + 5);
            Game.FixedStepped -= Watch;
            Assert.IsTrue(Chair.Pinned, "premise: Assis stood up during the watch");
            Assert.AreEqual(0, Game.ShoveCount, "the pinned chair was shoved");
            Assert.AreEqual(0, moving, "the pinned chair moved");
            Assert.Less(Planar(Chair.transform.position, seat), 1e-4f, "the pinned chair left its seat");
            Assert.AreEqual(1, robot.Path.ReverseCount, "the robot did not reverse at the pinned chair");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 42f (CONTRACT_M5 4, PRD 4.8): the hum. With the robot all but standing still (a test edit of its speed), the
        /// chair's first hop lands about 2.4 m from it: masked (no Hop noise event, a NoiseMasked one, Temoin 1.4 m away hears
        /// nothing); about 2.6 m away it is emitted and heard. A creak 1.4 m from the robot is never masked: it is emitted and
        /// alerts a listener. Every rebuilt level gives its robot one hum source (looping the hum), whose volume follows the
        /// furniture's distance to the robot (<see cref="OutOfSight.Sfx.HumVolumeAt"/>), full near it and silent past the rolloff.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step42f_TheHumMasksAHopAtTwoPointFourNotTwoPointSixNeverACreak()
        {
            yield return Load(RobotLevel);
            Game.Def.Robots[0].Speed = 1e-4f;
            yield return HopNearTheRobot(true);
            yield return HopNearTheRobot(false);

            yield return Restart();
            Robot robot = TheRobot();
            Assis.Pin(new Vector3(-4.0f, 0f, 3.5f), 0f);
            Vector3 hum = YawMath.Planar(robot.Position);
            Vector3 chairAt = hum + new Vector3(1.0f, 0f, 1.0f);
            Chair.Teleport(chairAt, 0f);
            Vector3 listenerAt = chairAt + new Vector3(4.0f, 0f, 1.0f);
            Temoin.Pin(listenerAt, 90f, 0f, true);
            yield return Steps(2);
            Assert.IsTrue(Hearing.IsMasked(NoiseKind.Hop, chairAt, new[] { robot.Position }), "premise: a hop there would be masked");
            Assert.LessOrEqual(Planar(listenerAt, chairAt), Tuning.CreakRadius - 0.5f, "premise: the listener is within the creak's radius");
            Assert.IsFalse(Game.Seen, "premise: nobody sees the chair");
            int alerts = Game.AlertCount;
            int masked = Game.MaskedNoiseCount;
            int creaks = CountNoises(NoiseKind.Creak);
            yield return Run(StepsFor(Tuning.CreakStartDelay + Tuning.CreakFillTime + 1f), () => Game.CreakCount > 0, 8f);
            Assert.AreEqual(1, Game.CreakCount, "premise: the chair never creaked");
            Assert.AreEqual(creaks + 1, CountNoises(NoiseKind.Creak), "the hum masked the creak");
            NoiseEvent creak = LastNoise(NoiseKind.Creak);
            Assert.Less(Planar(creak.Position, chairAt), 1e-3f, "premise: the creak is not at the chair");
            Assert.LessOrEqual(Planar(creak.Position, robot.Position), Tuning.RobotHumRadius - 1f, "premise: the creak is not well inside the hum");
            Assert.AreEqual(masked, Game.MaskedNoiseCount, "a noise was masked during the creak");
            Assert.AreEqual(alerts + 1, Game.AlertCount, "the listener did not hear the creak");
            Assert.AreEqual(InhabitantMode.Alerted, Temoin.Routine.Mode, "the creak did not alert the listener");

            // The hum follows the furniture: near the robot, then past the rolloff, then half way (north east of the robot,
            // behind Temoin and Assis).
            Vector3 away = new Vector3(1f, 0f, 1f).normalized;
            foreach (float d in new[] { 0.8f, Tuning.SfxHumMaxDistance + 0.5f, 3.5f })
            {
                Chair.Teleport(hum + away * d, 0f);
                yield return Steps(2);
                AssertHum(robot);
            }
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: the hum checks ended the run");
            AssertClean();
        }

        /// <summary>The robot's hum source loops the hum at the volume of the furniture's planar distance to the robot.</summary>
        private void AssertHum(Robot robot)
        {
            AudioSource source = OutOfSight.Sfx.HumOf(robot);
            Assert.IsNotNull(source, "the robot has no hum source");
            Assert.AreSame(Game.Sfx.Hum, source.clip, "the robot's source does not play the hum");
            Assert.IsTrue(source.loop, "the hum does not loop");
            float d = Planar(robot.Position, Chair.transform.position);
            float expected = OutOfSight.Sfx.HumVolumeAt(d);
            Assert.AreEqual(expected, source.volume, 1e-4f, $"the hum's volume with the furniture {d:0.00} m from the robot");
            if (d < Tuning.SfxHumMaxDistance - 0.1f)
            {
                Assert.Greater(source.volume, 0f, $"the hum is silent with the furniture {d:0.00} m from the robot");
            }
            if (d >= Tuning.SfxHumMaxDistance)
            {
                Assert.AreEqual(0f, source.volume, 1e-6f, $"the hum is heard with the furniture {d:0.00} m from the robot");
            }
        }

        private IEnumerator HopNearTheRobot(bool near)
        {
            int humSources = Game.Sfx.HumSourcesAdded;
            yield return Restart();
            Robot robot = TheRobot();
            Assert.AreEqual(humSources + 1, Game.Sfx.HumSourcesAdded, "the rebuilt level's robot did not get one hum source");
            Assert.Less(robot.Path.Speed, 1e-3f, "premise: the robot stands still");
            Assis.Pin(new Vector3(-4.0f, 0f, 3.5f), 0f);
            Vector3 hum = YawMath.Planar(robot.Position);
            // From rest at full stick the chair's first hop lands 0.187 m on (12 steps of 6 m/s2): at 2.40 m, or at 2.60 m.
            float startOffset = near ? 2.21f : 2.41f;
            Chair.Teleport(hum + Vector3.right * startOffset, 90f);
            Vector3 listenerAt = hum + new Vector3(startOffset + 0.2f, 0f, 1.4f);
            Temoin.Pin(listenerAt, 0f, 0f, true);
            yield return Steps(2);
            AssertHum(robot);
            Assert.IsFalse(Game.Seen, "premise: nobody sees the chair");
            Assert.AreEqual(InhabitantMode.Routine, Temoin.Routine.Mode, "premise: the listener is in Routine");
            var masked = new List<NoiseEvent>();
            void OnMasked(NoiseEvent e) => masked.Add(e);
            Game.NoiseMasked += OnMasked;
            int hops = CountNoises(NoiseKind.Hop);
            int alerts = Game.AlertCount;
            int maskedBefore = Game.MaskedNoiseCount;
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => masked.Count > 0 || CountNoises(NoiseKind.Hop) > hops, StepsFor(1f));
            Chair.ScriptedDirection = null;
            Game.NoiseMasked -= OnMasked;
            bool wasMasked = masked.Count > 0;
            Assert.IsTrue(wasMasked || CountNoises(NoiseKind.Hop) > hops, "premise: the chair never hopped");
            NoiseEvent hop = wasMasked ? masked[0] : LastNoise(NoiseKind.Hop);
            Assert.AreEqual(NoiseKind.Hop, hop.Kind, "premise: the first masked noise is not the hop");
            float d = Planar(hop.Position, robot.Position);
            if (near)
            {
                Assert.That(d, Is.InRange(2.3f, 2.49f), "premise: the first hop is not about 2.4 m from the robot");
            }
            else
            {
                Assert.That(d, Is.InRange(2.51f, 2.7f), "premise: the first hop is not about 2.6 m from the robot");
            }
            Assert.LessOrEqual(Planar(hop.Position, listenerAt), Tuning.HopNoiseRadius - 0.1f, "premise: the listener is within the hop's radius");
            Assert.AreEqual(near, wasMasked, $"a hop {d:0.000} m from the robot");
            Assert.AreEqual(near ? hops : hops + 1, CountNoises(NoiseKind.Hop), $"the Hop noise events of a hop {d:0.000} m from the robot");
            Assert.AreEqual(near ? maskedBefore + 1 : maskedBefore, Game.MaskedNoiseCount, "MaskedNoiseCount");
            Assert.AreEqual(near ? alerts : alerts + 1, Game.AlertCount, $"the listener and a hop {d:0.000} m from the robot");
            Assert.AreEqual(near ? InhabitantMode.Routine : InhabitantMode.Alerted, Temoin.Routine.Mode, $"the listener's mode after a hop {d:0.000} m from the robot");
        }

        // =====================================================================================================
        // ----- 43: the rocking chair (CONTRACT_M5 5, 16.9) -----
        // =====================================================================================================

        // test_m5_game_rock: a 10 x 8 m room; the rocking chair spawns at (0, -2) facing +z, Mamie sits on it for 4 s after a
        // 1 s dwell at (-3.5, -3); Temoin dwells at (3.5, 3).
        private const string RockLevel = "test_m5_game_rock";

        private Inhabitant Mamie => Game.Level.Inhabitants[0];

        private Inhabitant RockWitness => Game.Level.Inhabitants[1];

        /// <summary>
        /// Step 43b (CONTRACT_M5 5, 16.9): unseen, a stop rocks the rocking chair for round(RockTime / dt) (40) moving steps, a
        /// careful stop for round(RockCarefulTime / dt) (20), with no travel, each playing the runners' creak once for as long
        /// as the rock (the careful one its own shorter clip); seen rocking is caught (on the grace-th rock step,
        /// the witness turned toward it on the step it came to rest); sat on, it never rocks in the rules, nor when its sitter
        /// stands up.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step43b_SeenRockingIsCaughtAndSatOnDoesNotRock()
        {
            yield return Load(RockLevel);
            Assert.IsTrue(Chair.Body != null && Chair.Body.Rocks, "premise: the player is the rocking chair");
            Assert.AreEqual(BodyKinds.RockingChair, Chair.Kind, "premise: the rocking chair's kind");
            Mamie.Pin(new Vector3(-4.0f, 0f, 3.5f), 0f);
            RockWitness.Pin(new Vector3(3.5f, 0f, 3.5f), 0f);
            yield return Steps(2);
            yield return RockAfterAStop(false);
            yield return RockAfterAStop(true);
            Assert.AreEqual(2, Game.RockCount, "premise: two rocks");

            // Seen rocking: the witness turns toward the chair on the step it comes to rest.
            Vector3 eye = new Vector3(3.0f, 0f, 0.5f);
            RockWitness.Pin(eye, 0f);
            yield return Steps(2);
            Assert.IsFalse(Game.Seen, "premise: the witness sees the chair before the stop");
            int rocks = Game.RockCount;
            bool turned = false;
            int rockSteps = 0;
            int caughtOn = -1;
            Vector3 restAt = Vector3.zero;
            float travel = 0f;
            void Watch()
            {
                if (!turned)
                {
                    if (Game.RockCount > rocks)
                    {
                        turned = true;
                        restAt = Chair.transform.position;
                        RockWitness.Pin(eye, YawToward(eye, restAt));
                    }
                    return;
                }
                if (caughtOn < 0 && Chair.ActionActive)
                {
                    rockSteps++;
                    travel = Mathf.Max(travel, Planar(Chair.transform.position, restAt));
                    if (Game.State == PlayState.Caught)
                    {
                        caughtOn = rockSteps;
                    }
                }
            }
            Game.FixedStepped += Watch;
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(StepsFor(0.4f));
            Chair.ScriptedDirection = null;
            yield return Until(() => Game.State != PlayState.Playing, StepsFor(2f));
            Game.FixedStepped -= Watch;
            Assert.IsTrue(turned, "premise: the chair never came to rest");
            Assert.AreEqual(PlayState.Caught, Game.State, "the rocking chair rocked in the witness's view and was not caught");
            Assert.AreEqual(LoseReason.SeenMoving, Game.LoseReason);
            Assert.AreEqual(GraceSteps, caughtOn, "the catch did not come on the grace-th rock step");
            Assert.Less(travel, 1e-4f, "the rocking chair travelled while it rocked");

            // Sat on: Mamie sits on it for 4 s, then stands up; the chair never rocks.
            yield return Restart();
            RockWitness.Pin(new Vector3(3.5f, 0f, 3.5f), 0f);
            yield return Run(StepsFor(15f), () => Chair.Pinned, 4f);
            Assert.IsTrue(Chair.Pinned, "premise: Mamie never sat on the rocking chair");
            bool action = false;
            bool moving = false;
            int free = 0;
            void WatchSit()
            {
                action |= Chair.ActionActive;
                moving |= Game.FurnitureMoving || Chair.IsMoving;
                if (!Chair.Pinned)
                {
                    free++;
                }
            }
            Game.FixedStepped += WatchSit;
            yield return Run(StepsFor(12f), () => free >= StepsFor(1.5f), 4f);
            Game.FixedStepped -= WatchSit;
            Assert.GreaterOrEqual(free, StepsFor(1.5f), "premise: Mamie never stood up");
            Assert.AreEqual(0, Game.RockCount, "the rocking chair rocked under its sitter or when she stood up");
            Assert.IsFalse(action, "the sat-on rocking chair had an action");
            Assert.IsFalse(moving, "the sat-on rocking chair moved");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// The chair drives +x for 0.4 s and stops, unseen: it rocks once, for the full or the careful rock, without travel, and
        /// the runners' creak plays once, the clip as long as that rock.
        /// </summary>
        private IEnumerator RockAfterAStop(bool careful)
        {
            int rocks = Game.RockCount;
            int creaks = Game.Sfx.RockCreaksPlayed;
            bool started = false;
            bool ended = false;
            int rockSteps = 0;
            int stillSteps = 0;
            float travel = 0f;
            Vector3 restAt = Vector3.zero;
            void Watch()
            {
                if (!started)
                {
                    if (Game.RockCount > rocks)
                    {
                        started = true;
                        restAt = Chair.transform.position;
                    }
                    return;
                }
                if (ended)
                {
                    return;
                }
                if (Chair.ActionActive)
                {
                    rockSteps++;
                    stillSteps += Game.FurnitureMoving ? 0 : 1;
                    travel = Mathf.Max(travel, Planar(Chair.transform.position, restAt));
                }
                else
                {
                    ended = true;
                }
            }
            Chair.ScriptedCareful = careful;
            Chair.ScriptedDirection = Vector3.right;
            Game.FixedStepped += Watch;
            yield return Steps(StepsFor(0.4f));
            Chair.ScriptedDirection = null;
            yield return Until(() => ended, StepsFor(1.5f));
            Game.FixedStepped -= Watch;
            Chair.ScriptedCareful = null;
            string which = careful ? "careful" : "full";
            Assert.IsTrue(started, $"{which}: the rocking chair did not rock after its stop");
            Assert.IsTrue(ended, $"{which}: the rock never ended");
            Assert.AreEqual(rocks + 1, Game.RockCount, $"{which}: not one rock");
            float rockTime = careful ? Tuning.RockCarefulTime : Tuning.RockTime;
            Assert.AreEqual(Mathf.RoundToInt(rockTime / Dt), rockSteps, $"{which}: the rock's steps");
            Assert.AreEqual(creaks + 1, Game.Sfx.RockCreaksPlayed, $"{which}: the rock did not play its creak once");
            AudioClip creak = Game.Sfx.LastRockCreak;
            Assert.IsNotNull(creak, $"{which}: no rock creak clip");
            Assert.AreSame(careful ? Game.Sfx.RockCreakCareful : Game.Sfx.RockCreak, creak, $"{which}: the rock played the other rock's creak");
            Assert.AreEqual(rockTime, creak.length, 0.01f, $"{which}: the creak does not last the rock");
            Assert.AreEqual(0, stillSteps, $"{which}: a rock step is not moving");
            Assert.Less(travel, 1e-4f, $"{which}: the rocking chair travelled while it rocked");
            Assert.AreEqual(PlayState.Playing, Game.State);
            yield return Steps(2);
        }

        // =====================================================================================================
        // ----- 44: the load (CONTRACT_M5 6, 16.5) -----
        // =====================================================================================================

        // test_m5_game_load: a 12 x 8 m room; the chair carries a vase from (-3, 0) facing +x; Un and Deux dwell by the north
        // wall at x -5 and 5, the dog at (0, -3.5); a 1.2 m high wall, the Muret, stands at (3, 2) along x.
        private const string LoadLevel = "test_m5_game_load";

        private IEnumerator LoadTheLoad()
        {
            yield return Load(LoadLevel);
            Assert.AreEqual(3, Game.Level.Inhabitants.Count, "premise: Un, Deux and the dog");
            Assert.IsNotNull(TheDog, "premise: the dog");
            Assert.IsNotNull(Game.Load, "the level's load has no rule");
            Assert.IsNotNull(Game.LoadView, "the level's load has no visual");
            Assert.AreEqual(LoadView.Vase, Game.LoadView.Kind, "premise: a vase");
            Assert.IsTrue(Game.LoadView.transform.IsChildOf(Chair.Visual), "the vase does not ride on the furniture's visual");
            Assert.IsTrue(Game.CarryingLoad, "premise: the vase is carried");
        }

        private void PinLoadWatchersAway()
        {
            Un.Pin(new Vector3(-5.5f, 0f, 3.5f), 0f);
            Deux.Pin(new Vector3(5.5f, 0f, 3.5f), 0f);
            TheDog.Pin(new Vector3(0f, 0f, -3.5f), 180f);
        }

        /// <summary>
        /// Drives the chair at full stick along <paramref name="way"/> for 1 s, then back until the vase falls (a full-speed
        /// reversal: |dv| reaches 1.8 m/s). Records the chair's planar velocity and position of every step.
        /// </summary>
        private IEnumerator DropTheVase(Vector3 way, List<Vector2> velocities, List<Vector3> positions)
        {
            int step = 0;
            void Watch()
            {
                step++;
                Vector3 v = Chair.Velocity;
                velocities.Add(new Vector2(v.x, v.z));
                positions.Add(Chair.transform.position);
                Chair.ScriptedDirection = step < StepsFor(1f) ? way : -way;
            }
            Chair.ScriptedDirection = way;
            Game.FixedStepped += Watch;
            yield return Until(() => Game.CrashCount > 0, StepsFor(2.5f));
            Game.FixedStepped -= Watch;
            Chair.ScriptedDirection = null;
            Assert.AreEqual(1, Game.CrashCount, "premise: the full-speed reversal did not drop the vase");
        }

        /// <summary>
        /// Step 44b (CONTRACT_M5 6, 16.5): a full-speed reversal drops the vase on the step its kinematic rule says
        /// (LoadBalance.FirstFall of the chair's own velocities): one crash, a Crash noise event of 6 m at the clue, which lies
        /// on the floor ahead (the way the chair was going) under the level root, named after the load; the carried vase is
        /// hidden, the sample box is the chair's again, the crash sound plays. A listener 3.5 m away is alerted toward the
        /// clue, one 7 m away is not. The chair goes on without a load: no second crash.
        /// </summary>
        [UnityTest]
        public IEnumerator Step44b_TheFallMakesASixMetreCrashAndLeavesAClue()
        {
            yield return LoadTheLoad();
            PinLoadWatchersAway();
            var nearAt = new Vector3(-1.2f, 0f, 3.5f);
            var farAt = new Vector3(5.5f, 0f, 3.5f);
            Un.Pin(nearAt, 0f, 0f, true);
            Deux.Pin(farAt, 0f, 0f, true);
            yield return Steps(2);
            int alerts = Game.AlertCount;
            int crashesPlayed = Game.Sfx.CrashesPlayed;
            var velocities = new List<Vector2>();
            var positions = new List<Vector3>();
            yield return DropTheVase(Vector3.right, velocities, positions);
            Assert.AreEqual(velocities.Count - 1, LoadBalance.FirstFall(velocities), "the vase did not fall on the step its rule says");
            Assert.IsTrue(Game.Load.Fallen && !Game.CarryingLoad, "the load has not fallen");
            Assert.AreEqual(0f, Game.LoadExtraHeight, 1e-6f, "the sample box still has the vase");
            Assert.AreEqual(1, CountNoises(NoiseKind.Crash), "not one Crash noise event");
            NoiseEvent crash = LastNoise(NoiseKind.Crash);
            Assert.AreEqual(6f, crash.Radius, 1e-5f, "the crash is not a 6 m noise");
            Assert.AreEqual(Tuning.CrashRadius, Hearing.RadiusOf(NoiseKind.Crash), 1e-6f);
            Assert.Less(Planar(crash.Position, Game.ClueAt), 1e-3f, "the crash is not at the clue");
            Vector3 fellFrom = positions[positions.Count - 1];
            Assert.Greater(Vector3.Dot(YawMath.Planar(Game.ClueAt - fellFrom), Vector3.right), 0.3f, "the vase did not fly on the way the chair was going");
            Assert.IsTrue(Game.ClueActive, "no clue");
            Assert.IsTrue(Game.LoadView.ClueActive && Game.LoadView.Fallen, "the load's view shows no clue");
            GameObject clue = Game.LoadView.Clue;
            Assert.IsNotNull(clue, "no clue object");
            Assert.AreEqual(LoadView.CluePrefix + LoadView.Vase, clue.name, "the clue's name");
            Assert.IsTrue(clue.transform.IsChildOf(Game.Level.Root.transform), "the clue is not under the level root");
            Assert.IsFalse(clue.transform.IsChildOf(Chair.transform), "the clue rides on the chair");
            Assert.Less(Planar(clue.transform.position, Game.ClueAt), 1e-3f, "the clue is not where the vase fell");
            Assert.IsFalse(Game.LoadView.Carried.gameObject.activeSelf, "the vase is still on the chair");
            float spread = ClueVertices(clue).Max(v => Planar(v, clue.transform.position));
            Assert.Greater(spread, 0.1f, "premise: the clue has no spread");
            Assert.LessOrEqual(spread, Tuning.ClueSpreadRadius, "the clue spreads farther than ClueSpreadRadius, the wall clearance");
            Assert.AreEqual(crashesPlayed + 1, Game.Sfx.CrashesPlayed, "the crash sound did not play once");
            Assert.LessOrEqual(Planar(nearAt, Game.ClueAt), Tuning.CrashRadius - 1f, "premise: Un is not within the crash");
            Assert.Greater(Planar(farAt, Game.ClueAt), Tuning.CrashRadius + 0.5f, "premise: Deux is within the crash");
            Assert.AreEqual(alerts + 1, Game.AlertCount, "not one listener alerted by the crash");
            Assert.AreEqual(InhabitantMode.Alerted, Un.Routine.Mode, "the crash did not alert Un");
            Assert.Less(Planar(Un.Routine.AlertSource, Game.ClueAt), 1e-3f, "Un does not look toward the crash");
            Assert.AreEqual(InhabitantMode.Routine, Deux.Routine.Mode, "the crash alerted Deux, 7 m away");
            // The chair drives on, unseen (Un, alerted, would turn toward it).
            Un.Pin(nearAt, 0f);
            yield return Steps(5);
            Chair.ScriptedDirection = Vector3.left;
            yield return Steps(StepsFor(0.6f));
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(StepsFor(0.4f));
            Chair.ScriptedDirection = null;
            yield return Steps(2);
            Assert.AreEqual(1, Game.CrashCount, "a second crash without a load");
            Assert.AreEqual(1, CountNoises(NoiseKind.Crash), "a second Crash noise event");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 44c (CONTRACT_M5 6): the clue costs one discovery and the finder puts it away. After the fall (unseen), the
        /// chair goes back to its place; Un and Deux turn toward the clue at once: one discovery only (Un's, the first in
        /// order: its suspicion rises, Deux's does not), Un walks to the clue, puts it away within reach, and the clue goes on
        /// that very step; no discovery after.
        /// </summary>
        [UnityTest]
        public IEnumerator Step44c_TheClueCostsOneDiscoveryAndTheFinderPutsItAway()
        {
            yield return LoadTheLoad();
            PinLoadWatchersAway();
            yield return Steps(2);
            yield return DropTheVase(Vector3.right, new List<Vector2>(), new List<Vector3>());
            Assert.AreEqual(0, Game.DiscoveryCount, "premise: a discovery before anyone saw the clue");
            Chair.Teleport(Game.Def.Player.Position, Game.Def.Player.Yaw);
            Vector3 clue = Game.ClueAt;
            Vector3 point = clue + Vector3.up * Tuning.ClueSampleHeight;
            Vector3 unAt = clue + new Vector3(-2.5f, 0f, 2.0f);
            Vector3 deuxAt = clue + new Vector3(2.5f, 0f, 2.0f);
            Un.Pin(unAt, YawToward(unAt, clue), 0f, true);
            Deux.Pin(deuxAt, YawToward(deuxAt, clue), 0f, true);
            yield return Until(() => Game.ClueFinder != null, 3);
            Assert.AreSame(Un, Game.ClueFinder, "the first watcher (in order) to see the clue is not its finder");
            Assert.IsTrue(VisionOf(Deux).SeesPoint(point), "premise: Deux sees the clue too");
            Assert.AreEqual(1, Game.DiscoveryCount, "the clue did not cost one discovery");
            Assert.AreEqual(1, Game.ClueDiscoveryCount);
            Assert.AreEqual(Tuning.SuspicionPerDiscovery * Un.Routine.Personality.SuspicionFactor, Game.SuspicionOf(Un).Value, 1e-4f, "the finder's suspicion");
            Assert.AreEqual(0f, Game.SuspicionOf(Deux).Value, 1e-6f, "the clue cost Deux a discovery too");
            Assert.AreEqual(InhabitantMode.Investigating, Un.Routine.Mode, "the finder is not on its way to the clue");
            bool putAwayStep = false;
            bool goneThatStep = false;
            float reach = -1f;
            int maxDiscoveries = 0;
            void Watch()
            {
                maxDiscoveries = Mathf.Max(maxDiscoveries, Game.DiscoveryCount);
                if (Un.Routine.JustPutAway && !putAwayStep)
                {
                    putAwayStep = true;
                    goneThatStep = !Game.ClueActive && Game.LoadView.Clue == null;
                    reach = Planar(Un.Routine.Position, clue);
                }
            }
            Game.FixedStepped += Watch;
            yield return Until(() => Game.PutAwayCount > 0, StepsFor(15f));
            Game.FixedStepped -= Watch;
            Assert.AreEqual(1, Game.PutAwayCount, "the finder never put the clue away");
            Assert.IsTrue(putAwayStep, "premise: no put-away step was seen");
            Assert.IsTrue(goneThatStep, "the clue did not go on the step it was put away");
            Assert.LessOrEqual(reach, Tuning.InvestigateReach + 0.05f, "the clue was put away from afar");
            Assert.AreEqual(1, maxDiscoveries, "the walk to the clue cost another discovery");
            Assert.IsFalse(Game.ClueActive || Game.LoadView.ClueActive, "the clue is still there");
            Assert.IsNull(GameObject.Find(LoadView.CluePrefix + LoadView.Vase), "the clue object is still active");
            Assert.IsNull(Game.ClueFinder, "the finder is still sent to the clue");
            yield return Steps(StepsFor(1.5f));
            Assert.AreEqual(1, Game.DiscoveryCount, "a discovery after the clue was put away");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 44d (CONTRACT_M5 6, CONTRACT_M5_v3 15.5): a watcher without memory never finds the clue: the awake dog faces it
        /// and sees it for 1.5 s: no discovery, nobody sent, the clue stays. Then Deux turns toward it: one discovery, and Deux
        /// is the finder.
        /// </summary>
        [UnityTest]
        public IEnumerator Step44d_TheDogNeverFindsTheClue()
        {
            yield return LoadTheLoad();
            PinLoadWatchersAway();
            yield return Steps(2);
            yield return DropTheVase(Vector3.right, new List<Vector2>(), new List<Vector3>());
            Chair.Teleport(Game.Def.Player.Position, Game.Def.Player.Yaw);
            Vector3 clue = Game.ClueAt;
            Vector3 point = clue + Vector3.up * Tuning.ClueSampleHeight;
            Vector3 dogAt = clue + new Vector3(0.5f, 0f, -2.0f);
            TheDog.Pin(dogAt, YawToward(dogAt, clue), 0f, true);
            yield return Steps(2);
            Assert.IsFalse(TheDog.Routine.Asleep, "premise: the dog is awake");
            Assert.IsTrue(VisionOf(TheDog).SeesPoint(point), "premise: the dog sees the clue");
            yield return Steps(StepsFor(1.5f));
            Assert.AreEqual(0, Game.DiscoveryCount, "the dog's sight of the clue cost a discovery");
            Assert.IsNull(Game.ClueFinder, "the dog was sent to the clue");
            Assert.AreNotEqual(InhabitantMode.Investigating, TheDog.Routine.Mode, "the dog went to the clue");
            Assert.IsTrue(Game.ClueActive, "the clue went without a finder");
            Vector3 deuxAt = clue + new Vector3(2.5f, 0f, 2.0f);
            Deux.Pin(deuxAt, YawToward(deuxAt, clue), 0f, true);
            yield return Until(() => Game.ClueFinder != null, 3);
            Assert.AreSame(Deux, Game.ClueFinder, "Deux saw the clue and is not its finder");
            Assert.AreEqual(1, Game.DiscoveryCount, "Deux's sight of the clue did not cost one discovery");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 44e (CONTRACT_M5 6, 16.5, 18, 19 m13): the balance gauge (hud.balance) shows with a load, to the left of the creak
        /// gauge: it shows |dv| over the fall threshold on every step and is red exactly above BalanceWarning (0.9): calm
        /// through a careful start and stop and through a full-speed straight start and stop (0.83: the vase holds), red
        /// through a 70 deg turn at full speed (0.96: the vase still holds), hidden once the vase fell, and on a level without a
        /// load. The chair faces +x (yaw 90), so the furniture frame is not the world's: on every carried step the vase's
        /// visual tilt is LoadBalance.SwayTiltLocal of the chair's yaw (CONTRACT_M5 12, step 44), leaning after the full start,
        /// and upright once it fell.
        /// </summary>
        [UnityTest]
        public IEnumerator Step44e_TheBalanceGaugeShowsAndTurnsRed()
        {
            yield return LoadTheLoad();
            PinLoadWatchersAway();
            yield return Steps(2);
            Assert.AreEqual(90f, Mathf.Repeat(Chair.Yaw, 360f), 0.5f, "premise: the chair does not face +x");
            Assert.IsTrue(Hud.BalanceVisible, "no balance gauge with a load");
            Assert.IsTrue(Hud.Labels.TryGetValue("BalanceLabel", out Text label) && label.text == Strings.HudBalance, "the gauge does not carry hud.balance");
            Assert.AreEqual(0f, Hud.BalanceShown, 1e-6f, "the gauge is not empty at rest");
            Assert.IsFalse(Hud.BalanceRed, "the gauge is red at rest");
            Rect balance = Hud.BalanceScreenRect;
            Rect creakRect = Hud.CreakScreenRect;
            Assert.Greater(creakRect.width, 0f, "premise: the creak gauge shows");
            Assert.IsFalse(balance.Overlaps(creakRect), "the balance gauge covers the creak gauge");
            Assert.LessOrEqual(balance.xMax, creakRect.xMin + 1e-3f, $"the balance gauge {balance} is not left of the creak gauge {creakRect}");
            Assert.IsTrue(balance.xMin >= 0f && balance.yMin >= 0f && balance.xMax <= Screen.width, $"the balance gauge {balance} leaves the screen");
            float mismatch = 0f;
            int redWrong = 0;
            float peak = 0f;
            bool red = false;
            bool redColour = false;
            float tiltMismatch = 0f;
            int carriedSteps = 0;
            float tiltPeak = 0f;
            float worldGap = 0f;
            void Watch()
            {
                if (!Game.CarryingLoad)
                {
                    return;
                }
                float ratio = Game.Load.Ratio;
                peak = Mathf.Max(peak, ratio);
                mismatch = Mathf.Max(mismatch, Mathf.Abs(Hud.BalanceShown - Mathf.Clamp01(ratio)));
                redWrong += Hud.BalanceRed != ratio > Tuning.BalanceWarning ? 1 : 0;
                red |= Hud.BalanceRed;
                Color c = Hud.BalanceFillColor;
                redColour |= Hud.BalanceRed && c.r > 0.9f && c.g < 0.4f;
                Vector2 local = Game.Load.SwayTiltLocal(Chair.Yaw);
                tiltMismatch = Mathf.Max(tiltMismatch, (Game.LoadView.Tilt - local).magnitude);
                tiltPeak = Mathf.Max(tiltPeak, Game.LoadView.Tilt.magnitude);
                worldGap = Mathf.Max(worldGap, (Game.Load.SwayTilt - local).magnitude);
                carriedSteps++;
            }
            Game.FixedStepped += Watch;

            // 1. A careful start and stop: part way, calm.
            Chair.ScriptedCareful = true;
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(StepsFor(1f));
            Chair.ScriptedDirection = null;
            yield return Steps(StepsFor(0.6f));
            Chair.ScriptedCareful = null;
            Assert.That(peak, Is.InRange(0.3f, Tuning.BalanceWarning), "premise: a careful start and stop does not fill the gauge part way");
            Assert.IsFalse(red, "the gauge turned red through a careful start and stop");

            // 2. A full-speed straight start and stop: the vase holds; red only if it passes the warning.
            Chair.Teleport(Game.Def.Player.Position, Game.Def.Player.Yaw);
            yield return Steps(StepsFor(0.6f));
            Assert.IsTrue(Game.CarryingLoad, "premise: the careful run dropped the vase");
            peak = 0f;
            tiltPeak = 0f;
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(StepsFor(1f));
            Chair.ScriptedDirection = null;
            yield return Steps(StepsFor(0.6f));
            Assert.IsTrue(Game.CarryingLoad, "premise: a straight full-speed start and stop dropped the vase");
            Assert.That(peak, Is.InRange(0.75f, 1f), "premise: the full-speed start and stop does not fill the gauge most of the way");
            Assert.Greater(tiltPeak, 1f, "the vase never leaned after the full-speed start");
            float straightPeak = peak;

            // 3. Full speed, then a 70 deg turn: |dv| = 2 x 1.5 x sin 35 deg = 1.72, past the warning, under the fall.
            Chair.Teleport(Game.Def.Player.Position, Game.Def.Player.Yaw);
            yield return Steps(StepsFor(0.6f));
            peak = 0f;
            red = false;
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(StepsFor(0.8f));
            Chair.ScriptedDirection = YawMath.Forward(90f - 70f);
            yield return Steps(StepsFor(0.6f));
            Chair.ScriptedDirection = null;
            yield return Steps(StepsFor(0.6f));
            Game.FixedStepped -= Watch;
            Assert.IsTrue(Game.CarryingLoad, "premise: the 70 deg turn at full speed dropped the vase");
            Assert.Greater(peak, Tuning.BalanceWarning, "premise: the 70 deg turn did not pass the warning");
            Assert.IsTrue(red, $"the gauge never turned red above {Tuning.BalanceWarning}");
            Assert.IsTrue(redColour, "the red gauge is not drawn red");
            Assert.AreEqual(0, redWrong, $"the gauge was red below the warning or calm above it (straight start and stop at {straightPeak:0.00})");
            Assert.Less(mismatch, 1e-4f, "the gauge does not show |dv| over the fall threshold");
            Assert.Greater(carriedSteps, StepsFor(5f), "premise: too few carried steps were watched");
            Assert.Greater(worldGap, 1f, "premise: at yaw 90 the furniture frame and the world frame gave the same tilt");
            Assert.Less(tiltMismatch, 1e-4f, "the vase's tilt is not LoadBalance.SwayTiltLocal of the chair's yaw");
            Assert.IsTrue(Hud.BalanceVisible, "the gauge hid while the vase holds");
            yield return DropTheVase(Vector3.left, new List<Vector2>(), new List<Vector3>());
            yield return Steps(1);
            Assert.IsFalse(Game.CarryingLoad, "premise: the vase did not fall");
            Assert.AreEqual(Vector2.zero, Game.LoadView.Tilt, "the fallen vase's view still leans");
            Assert.IsFalse(Hud.BalanceVisible, "the gauge still shows once the vase fell");
            yield return Load("level1");
            Assert.IsNull(Game.Load, "premise: level1 has a load");
            Assert.IsFalse(Hud.BalanceVisible, "the gauge shows on a level without a load");
            AssertClean();
        }

        /// <summary>The world positions of every vertex of the clue's meshes.</summary>
        private static List<Vector3> ClueVertices(GameObject clue)
        {
            var points = new List<Vector3>();
            foreach (MeshFilter f in clue.GetComponentsInChildren<MeshFilter>(true))
            {
                Assert.IsNotNull(f.sharedMesh, "premise: a clue part has no mesh");
                Assert.IsTrue(f.sharedMesh.isReadable, "premise: a clue mesh is not readable");
                foreach (Vector3 v in f.sharedMesh.vertices)
                {
                    points.Add(f.transform.TransformPoint(v));
                }
            }
            Assert.Greater(points.Count, 0, "premise: the clue has no vertex");
            return points;
        }

        /// <summary>
        /// Step 44h (CONTRACT_M5 6; critique m15): the clue never lands in a wall. The chair reverses at full speed with the
        /// east wall just ahead: the throw ahead (the way it was going) is cut short by the wall, so the vase falls behind the
        /// chair instead, away from the wall, its centre at least <see cref="GameState.ClueClearance"/> (the clue's spread)
        /// from it and every part of the clue inside the room.
        /// </summary>
        [UnityTest]
        public IEnumerator Step44h_TheClueFallsAwayFromAWallInTheWay()
        {
            yield return LoadTheLoad();
            PinLoadWatchersAway();
            Vector3 spawn = Game.Def.Player.Position;
            Assert.IsTrue(Physics.Raycast(spawn + Vector3.up * Tuning.ClueProbeHeight, Vector3.right, out RaycastHit hit, 12f, Layers.ChairBlockerMask,
                QueryTriggerInteraction.Ignore), "premise: no east wall");
            float face = hit.point.x;
            Assert.Greater(face, 5f, "premise: something stands between the spawn and the east wall");
            Assert.GreaterOrEqual(GameState.ClueClearance, Tuning.ClueSpreadRadius, "the wall clearance is less than the clue's spread");
            // 1 s of full speed then the reversal travel about 1.48 m before the fall: it falls about 0.45 m from the face.
            Chair.Teleport(new Vector3(face - 1.93f, 0f, spawn.z), 90f);
            yield return Steps(StepsFor(0.6f));
            var positions = new List<Vector3>();
            yield return DropTheVase(Vector3.right, new List<Vector2>(), positions);
            Vector3 fellFrom = positions[positions.Count - 1];
            float ahead = face - fellFrom.x;
            Assert.Greater(ahead, 0.24f, "premise: the chair ran into the wall before the fall");
            Assert.Less(ahead - GameState.ClueClearance, Tuning.ClueThrowDistance, "premise: the wall does not cut the throw ahead short");
            Vector3 clueAt = Game.ClueAt;
            Assert.Less(clueAt.x, fellFrom.x - 0.2f, $"the vase did not fall behind the chair, away from the wall (fell from {fellFrom.x:0.00}, lies at {clueAt.x:0.00})");
            Assert.LessOrEqual(clueAt.x, face - GameState.ClueClearance + 1e-3f, "the clue's centre is nearer the wall than its spread");
            GameObject clue = Game.LoadView.Clue;
            Assert.IsNotNull(clue, "no clue object");
            float reach = ClueVertices(clue).Max(v => v.x);
            Assert.Less(reach, face, $"the clue pokes into the wall (reaches x {reach:0.000}, face {face:0.000})");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertClean();
        }

        /// <summary>
        /// Step 44f (CONTRACT_M5 16.5): the load is inside the sample box. Behind the 1.2 m Muret the chair itself is hidden
        /// from Deux (its own five samples), but the box grown by the vase's 0.25 m is seen: the furniture is seen, and seen
        /// moving it is caught. The same chair without a load (a test edit) is not seen there.
        /// </summary>
        [UnityTest]
        public IEnumerator Step44f_TheLoadIsInsideTheSampleBox()
        {
            yield return LoadTheLoad();
            PinLoadWatchersAway();
            var chairAt = new Vector3(3.0f, 0f, 1.6f);
            var eyeAt = new Vector3(3.0f, 0f, 3.6f);
            Chair.Teleport(chairAt, 0f);
            Deux.Pin(eyeAt, 180f);
            yield return Steps(2);
            Vision v = VisionOf(Deux);
            var plain = new Vector3[Tuning.SampleCount];
            Chair.GetSamplePoints(plain);
            Assert.IsFalse(Vision.Test(Deux.EyePosition, Deux.EyeForward, plain, v.Range, v.HalfAngle, null), "premise: the Muret does not hide the chair itself");
            Assert.AreEqual(Tuning.LoadHeight, v.ExtraHeight, 1e-6f, "the sample box did not grow by the load's height");
            Assert.AreEqual(plain[3].y + Tuning.LoadHeight, v.Samples[3].y, 1e-4f, "a top sample did not rise by the load's height");
            Assert.AreEqual(plain[0].y + 0.5f * Tuning.LoadHeight, v.Samples[0].y, 1e-4f, "the centre sample did not rise by half the load's height");
            Assert.IsTrue(v.SeesPlayer, "the vase above the Muret is not the furniture seen");
            Assert.IsTrue(Game.Seen, "Game.Seen ignores the vase");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: seen and still is no catch");
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Game.State != PlayState.Playing, GraceSteps + 5);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Caught, Game.State, "the vase seen moving above the Muret was not caught");
            Assert.AreEqual(LoseReason.SeenMoving, Game.LoseReason);

            yield return Load(LoadLevel);
            Game.Def.Player.Load = null;
            yield return Restart();
            Assert.IsNull(Game.Load, "premise: the load was not removed");
            Assert.IsNull(Game.LoadView, "premise: a load view without a load");
            Assert.IsFalse(Hud.BalanceVisible, "the balance gauge shows without a load");
            PinLoadWatchersAway();
            Chair.Teleport(chairAt, 0f);
            Deux.Pin(eyeAt, 180f);
            yield return Steps(2);
            v = VisionOf(Deux);
            Assert.AreEqual(0f, v.ExtraHeight, 1e-6f, "the sample box grew without a load");
            Assert.IsFalse(v.SeesPlayer, "the chair without a load is seen behind the Muret");
            AssertClean();
        }
    }
}
