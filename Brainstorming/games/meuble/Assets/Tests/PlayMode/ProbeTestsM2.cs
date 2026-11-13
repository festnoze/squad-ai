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
    /// The M2 probe (docs/CONTRACT_M2.md 10, steps 13 to 21, and the M2.1 tests of 11.9 as Step13b_ and the
    /// like, since M3 owns steps 22 and up) on the real Boot scene, under GameRules.M2.
    /// As in the M1 probe, every wait counts fixed steps or is bounded by game time, never by rendered
    /// frames, and every scenario asserts its premise so it cannot pass for the wrong reason.
    /// </summary>
    public sealed class ProbeTestsM2
    {
        private const float Dt = Tuning.FixedStep;
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;

        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;
        private Inhabitant Habitant => Game.MainInhabitant;

        // Level 1 spots (PRD 6.3 coordinates): station 3, in front of the window.
        private static readonly Vector3 WindowSpot = new Vector3(0f, 0f, -2.3f);

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            fixedSteps = 0;
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
            // This file is the M2 probe: every M2 rule is on (docs/CONTRACT_M2.md 3.7).
            Game.Rules = GameRules.M2;
            Game.FixedStepped += CountStep;
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            Time.timeScale = 1f;
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

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(to - from);

        private static float Planar(Vector3 a, Vector3 b) => YawMath.Planar(a - b).magnitude;

        /// <summary>
        /// Runs the game at <paramref name="scale"/> until <paramref name="until"/> holds or
        /// <paramref name="maxSteps"/> fixed steps have run: bounded by game time, never by frames.
        /// <paramref name="perFrame"/> runs once per rendered frame (visual checks only).
        /// </summary>
        private IEnumerator Run(int maxSteps, Func<bool> until, float scale, Action perFrame = null)
        {
            int end = fixedSteps + maxSteps;
            float realStart = Time.realtimeSinceStartup;
            Time.timeScale = scale;
            try
            {
                while (fixedSteps < end && (until == null || !until()) && Time.realtimeSinceStartup - realStart < 150f)
                {
                    yield return null;
                    perFrame?.Invoke();
                }
            }
            finally
            {
                Time.timeScale = 1f;
            }
        }

        private static int StepsFor(float seconds) => Mathf.CeilToInt(seconds / Dt);

        /// <summary>Loads a level of levels.json under the M2 rules and asserts it booted with zero errors.</summary>
        private IEnumerator LoadLevel(string id)
        {
            CollectionAssert.Contains(Game.LevelOrder, id, $"levels.json does not list {id}");
            int before = exceptions;
            Game.LoadLevel(id);
            Game.Rules = GameRules.M2;
            yield return Steps(2);
            Assert.AreEqual(id, Game.LevelId);
            Assert.AreEqual(before, exceptions, $"{id} logged errors at boot: " + string.Join(" | ", logged));
            Assert.AreEqual(PlayState.Playing, Game.State, $"{id} is not Playing after boot");
        }

        /// <summary>Frozen pins every inhabitant but <paramref name="except"/> where it stands, facing away from a point.</summary>
        private void FreezeOthers(Inhabitant except, Vector3 awayFrom)
        {
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                if (except == null || h != except)
                {
                    Vector3 at = h.Routine.Position;
                    h.Pin(at, YawToward(awayFrom, at));
                }
            }
        }

        // ----- Routine recording and the telegraph analysis -----

        private struct Record
        {
            public RoutineActivity Activity;
            public InhabitantMode Mode;
            public float Body;
            public float Head;
            public float EyeYaw;
            public Vector3 Position;
        }

        private static Record Snapshot(InhabitantRoutine r) => new Record
        {
            Activity = r.LastActivity, Mode = r.Mode, Body = r.BodyYaw, Head = r.HeadYaw, EyeYaw = r.EyeYaw, Position = r.Position,
        };

        /// <summary>
        /// From record <paramref name="from"/> (the step of the noise): a full telegraph, no turn before it
        /// ends, then the eye forward within 15 deg of <paramref name="source"/> while Alerted.
        /// </summary>
        private static void AssertTelegraphThenLook(List<Record> records, int from, Vector3 source, string what)
        {
            int tele = -1;
            for (int k = from; k < records.Count; k++)
            {
                if (records[k].Activity == RoutineActivity.Telegraph)
                {
                    tele = k;
                    break;
                }
            }
            Assert.GreaterOrEqual(tele, 0, $"{what}: the inhabitant never telegraphed");
            int end = tele;
            while (end < records.Count && records[end].Activity == RoutineActivity.Telegraph)
            {
                end++;
            }
            Assert.GreaterOrEqual((end - tele) * Dt, Tuning.TelegraphDuration - 1e-3f,
                $"{what}: the telegraph lasted only {(end - tele) * Dt:0.00} s");
            for (int k = from; k < end; k++)
            {
                float turned = Mathf.Abs(Mathf.DeltaAngle(records[from].Body, records[k].Body)) + Mathf.Abs(records[k].Head - records[from].Head);
                Assert.Less(turned, 1e-3f, $"{what}: the inhabitant turned before the telegraph ended (record {k})");
            }
            float best = 180f;
            bool alerted = false;
            for (int k = end; k < records.Count; k++)
            {
                if (records[k].Mode != InhabitantMode.Alerted)
                {
                    continue;
                }
                alerted = true;
                float toward = YawMath.YawOf(YawMath.Planar(source - records[k].Position));
                best = Mathf.Min(best, Mathf.Abs(Mathf.DeltaAngle(records[k].EyeYaw, toward)));
            }
            Assert.IsTrue(alerted, $"{what}: the inhabitant never became Alerted");
            Assert.LessOrEqual(best, 15f, $"{what}: the eye never came within 15 deg of the source (best {best:0.0} deg)");
        }

        // ----- 13 and 14 -----

        /// <summary>
        /// Step 13: a reactive pin at station 3 sees the chair at spawn (Confirmed), is pinned away, the chair
        /// is driven 1.2 m, the pin turns back: a discovery within one step. Leaves the inhabitant investigating.
        /// </summary>
        private IEnumerator DiscoverDisplacedChair()
        {
            Vector3 spawn = Chair.transform.position;
            Assert.Less(Planar(spawn, Game.Def.Player.Position), 0.05f, "premise: the chair is at spawn");
            Assert.Greater(Planar(spawn, WindowSpot), Tuning.HopNoiseRadius, "premise: the inhabitant must stand beyond the hop radius");

            Habitant.Pin(WindowSpot, YawToward(WindowSpot, spawn), 0f, true);
            yield return Steps(2);
            Assert.IsFalse(Habitant.Routine.IsFrozen, "a reactive pin must not be frozen");
            Assert.IsTrue(Game.Seen, "premise: the inhabitant sees the chair at spawn");
            Assert.AreEqual(Observation.Confirmed, Game.LastObservationOf(Habitant), "the chair at spawn is where it belongs");
            Assert.AreEqual(0f, Game.SuspicionOf(Habitant).Value, 1e-6f);
            Assert.AreEqual(InhabitantMode.Routine, Habitant.Mode);
            Assert.AreEqual(HudEye.Calm, main.Hud.Eye, "seen in place and still: the eye must be calm");
            Assert.IsFalse(main.Game.Ghost.Visible, "the ghost shows while the chair is in place");

            Habitant.Pin(WindowSpot, YawToward(WindowSpot, spawn) + 180f, 0f, true);
            yield return Steps(1);
            Assert.IsFalse(Game.Seen, "premise: pinned away, the inhabitant no longer sees the chair");

            bool everSeen = false;
            bool everReacted = false;
            Chair.ScriptedDirection = Vector3.forward;
            int guard = 0;
            while (Planar(Chair.transform.position, spawn) < 1.2f && guard++ < 150)
            {
                yield return new WaitForFixedUpdate();
                everSeen |= Game.Seen;
                everReacted |= Habitant.Mode != InhabitantMode.Routine;
            }
            Chair.ScriptedDirection = null;
            yield return Steps(2);
            Vector3 displaced = Chair.transform.position;
            Assert.GreaterOrEqual(Planar(displaced, spawn), 1.2f, "the chair was not driven 1.2 m");
            Assert.Greater(Planar(displaced, WindowSpot), Tuning.HopNoiseRadius, "premise: the hops stay beyond the hop radius");
            Assert.IsFalse(everSeen, "the inhabitant pinned away saw the chair move");
            Assert.IsFalse(everReacted, "the inhabitant reacted to hops out of range");
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.AreEqual(0, Game.DiscoveryCount, "a discovery while unseen");

            Habitant.Pin(WindowSpot, YawToward(WindowSpot, displaced), 0f, true);
            // M2.1 (11.1): seen out of place for 0.18 s is Suspect, 0.20 s is the discovery.
            int grace = Mathf.RoundToInt(Tuning.DiscoveryGrace / Dt);
            for (int k = 1; k < grace; k++)
            {
                yield return new WaitForFixedUpdate();
                Assert.IsTrue(Game.Seen, "premise: pinned back, the inhabitant sees the displaced chair");
                Assert.AreEqual(0, Game.DiscoveryCount, $"a discovery after only {k * Dt:0.00} s out of place");
                Assert.AreEqual(Observation.Suspect, Game.LastObservationOf(Habitant), $"not Suspect after {k * Dt:0.00} s out of place");
                Assert.AreEqual(HudEye.Alarm, main.Hud.Eye, "a suspect sighting must show the alarm eye");
                Assert.IsTrue(main.Game.Ghost.Visible, "the ghost is hidden while the chair is out of place");
                Assert.Less(Planar(main.Game.Ghost.Pose.Position, spawn), 0.05f, "the ghost is not at the remembered pose");
            }
            yield return Steps(1);
            Assert.AreEqual(1, Game.DiscoveryCount, $"no discovery after {grace * Dt:0.00} s out of place");
            Assert.AreEqual(Tuning.SuspicionPerDiscovery, Game.SuspicionOf(Habitant).Value, 1e-3f, "suspicion after one discovery");
            Assert.AreEqual(InhabitantMode.Investigating, Habitant.Mode, "the inhabitant does not investigate");
            Assert.AreEqual(PlayState.Playing, Game.State);
            // M2.2 (S1): seen by an inhabitant who investigates is not harmless: the eye stays in alarm.
            yield return Steps(1);
            Assert.IsTrue(Game.Seen, "premise: the investigating inhabitant sees the chair");
            Assert.AreEqual(HudEye.Alarm, main.Hud.Eye, "seen by an investigating inhabitant, the eye must be in alarm");
        }

        [UnityTest]
        public IEnumerator Step13_Memory()
        {
            yield return DiscoverDisplacedChair();
        }

        /// <summary>A planner with no path to one point (the investigated chair), the inner planner elsewhere.</summary>
        private sealed class NoPathTo : IPathPlanner
        {
            private readonly Vector3 blocked;
            private readonly IPathPlanner inner;

            public NoPathTo(Vector3 blocked, IPathPlanner inner)
            {
                this.blocked = blocked;
                this.inner = inner ?? StraightPlanner.Instance;
            }

            public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
            {
                corners.Clear();
                return YawMath.Planar(to - blocked).magnitude > 0.5f && inner.TryPlan(from, to, corners);
            }
        }

        /// <summary>
        /// M2.1 (11.4): when the inhabitant cannot reach the displaced chair (no path), it gives up and accepts
        /// it where it stands. Without that rule it rediscovers the chair after every grace and loses the level.
        /// </summary>
        [UnityTest]
        public IEnumerator Step13b_NoPathInvestigationGivesUp()
        {
            var displaced = new Vector3(-3.2f, 0f, -0.8f);
            Chair.Teleport(displaced, 0f);
            Habitant.Init(Game.Def.Inhabitants[0], new NoPathTo(displaced, Game.Level.Planner));
            Habitant.Pin(WindowSpot, YawToward(WindowSpot, displaced), 0f, true);
            yield return Steps(1);
            Assert.IsTrue(Game.Seen, "premise: the inhabitant sees the displaced chair");
            yield return Run(StepsFor(4f), () => Game.State != PlayState.Playing, 1f);
            Assert.AreEqual(PlayState.Playing, Game.State, $"an unreachable chair lost the level ({Game.LoseReason})");
            Assert.AreEqual(1, Game.DiscoveryCount, "the inhabitant rediscovered the chair it could not reach");
            Assert.AreEqual(1, Game.GiveUpCount, "the investigation with no path did not give up");
            Assert.Less(Planar(Game.MemoryOf(Habitant).PlayerSlot.Position, displaced), 0.05f, "the slot did not take the chair pose");
            Assert.AreEqual(Observation.Confirmed, Game.LastObservationOf(Habitant), "after giving up the chair is where it belongs");
            Assert.AreEqual(InhabitantMode.Routine, Habitant.Mode);
            Assert.AreEqual(Tuning.SuspicionPerDiscovery, Game.SuspicionOf(Habitant).Value, 0.1f, "suspicion of the one discovery");
            Assert.IsFalse(main.Game.Ghost.Visible, "the ghost still shows after giving up");
        }

        /// <summary>The grace measures an unbroken sighting: 0.18 s, a look away, 0.18 s again is no discovery.</summary>
        [UnityTest]
        public IEnumerator Step13c_DiscoveryGraceNeedsAnUnbrokenSighting()
        {
            var displaced = new Vector3(-3.2f, 0f, -0.8f);
            Chair.Teleport(displaced, 0f);
            float toward = YawToward(WindowSpot, displaced);
            int almost = Mathf.RoundToInt(Tuning.DiscoveryGrace / Dt) - 1;
            for (int round = 0; round < 3; round++)
            {
                Habitant.Pin(WindowSpot, toward, 0f, true);
                yield return Steps(almost);
                Assert.IsTrue(Game.Seen, "premise: seen out of place");
                Habitant.Pin(WindowSpot, toward + 180f, 0f, true);
                yield return Steps(1);
                Assert.IsFalse(Game.Seen, "premise: looking away");
            }
            Assert.AreEqual(0, Game.DiscoveryCount, "three sightings of 0.18 s, each broken, made a discovery");
            Habitant.Pin(WindowSpot, toward, 0f, true);
            yield return Steps(almost + 1);
            Assert.AreEqual(1, Game.DiscoveryCount, "an unbroken 0.20 s sighting made no discovery");
        }


        /// <summary>
        /// M2.2 (S4): the discovery grace measures an unbroken observation. An inhabitant that stops observing
        /// mid grace (frozen pinned, or investigating) while still seeing the chair must not carry the timer
        /// over: back to observing, it needs the full 0.20 s again.
        /// </summary>
        [UnityTest]
        public IEnumerator Step13d_GraceResetsWhenTheObserverStopsObserving()
        {
            var displaced = new Vector3(-3.2f, 0f, -0.8f);
            Chair.Teleport(displaced, 0f);
            float toward = YawToward(WindowSpot, displaced);
            int almost = Mathf.RoundToInt(Tuning.DiscoveryGrace / Dt) - 1;
            for (int round = 0; round < 2; round++)
            {
                Habitant.Pin(WindowSpot, toward, 0f, true);
                yield return Steps(almost);
                Assert.AreEqual(Observation.Suspect, Game.LastObservationOf(Habitant), "premise: 0.18 s out of place");
                if (round == 0)
                {
                    // Frozen pinned, still looking at the chair: it sees, it does not observe.
                    Habitant.Pin(WindowSpot, toward);
                }
                else
                {
                    // Investigating (walking to the chair, which stays in view): it does not observe.
                    Habitant.Routine.Investigate(displaced);
                    Assert.AreEqual(InhabitantMode.Investigating, Habitant.Mode, "premise: investigating");
                }
                yield return Steps(3);
                Assert.IsTrue(Game.Seen, "premise: the chair stays in sight while the inhabitant does not observe");
                Assert.AreEqual(Observation.NotSeen, Game.LastObservationOf(Habitant), "premise: no observation");
            }
            Assert.AreEqual(0, Game.DiscoveryCount, "a discovery although no sighting lasted 0.20 s");
            Habitant.Pin(WindowSpot, toward, 0f, true);
            yield return Steps(almost);
            Assert.AreEqual(0, Game.DiscoveryCount, "the grace timer carried over a step without observation");
            yield return Steps(1);
            Assert.AreEqual(1, Game.DiscoveryCount, "an unbroken 0.20 s observation made no discovery");
        }

        /// <summary>
        /// M2.2 (S5), level 3: while the chair is out of place, a ring marks every decoy of its kind; at a decoy
        /// the chair is explained, so the ghost hides (and no inhabitant can discover it there).
        /// </summary>
        [UnityTest]
        public IEnumerator Step13e_DecoySpotHidesTheGhost()
        {
            yield return LoadLevel("level3");
            Vector3 spawn = Chair.transform.position;
            int sameKind = 0;
            DecoyDef near = null;
            foreach (DecoyDef d in Game.Def.Decoys)
            {
                if (string.Equals(d.Kind, Chair.Kind, StringComparison.OrdinalIgnoreCase))
                {
                    sameKind++;
                    // The decoy farthest from the spawn: beside it, the chair is surely out of place.
                    if (near == null || Planar(d.Position, spawn) > Planar(near.Position, spawn))
                    {
                        near = d;
                    }
                }
            }
            Assert.Greater(sameKind, 0, "premise: level 3 has decoys of the player's kind");
            Assert.IsFalse(main.Game.Ghost.RingsVisible, "decoy rings show while the chair is in place");
            Assert.AreEqual(sameKind, main.Game.Ghost.RingCount, "one ring per decoy of the player's kind");

            // Out of place, away from every decoy: ghost and rings.
            Vector3 away = spawn;
            bool found = false;
            for (int i = 0; i < 16 && !found; i++)
            {
                Vector3 p = spawn + YawMath.Forward(i * 22.5f) * 1.5f;
                bool clear = IsStandable(p);
                foreach (DecoyDef d in Game.Def.Decoys)
                {
                    clear &= Planar(p, d.Position) > Tuning.DisplacementTolerance + 0.2f;
                }
                if (clear)
                {
                    away = p;
                    found = true;
                }
            }
            Assert.IsTrue(found, "premise: no standing spot 1.5 m from the spawn away from every decoy");
            FreezeOthers(null, away);
            Chair.Teleport(away, Chair.Yaw);
            yield return Steps(2);
            Assert.IsTrue(Game.OutOfPlace, "premise: out of place");
            Assert.IsFalse(Game.AtDecoy);
            Assert.IsTrue(main.Game.Ghost.Visible, "no ghost while out of place");
            Assert.IsTrue(main.Game.Ghost.RingsVisible, "no decoy rings while out of place");

            // Next to a decoy (within tolerance, beside it): explained, so no ghost; the rings stay.
            Vector3 beside = near.Position + YawMath.Forward(near.Yaw + 90f) * 0.5f;
            Chair.Teleport(beside, near.Yaw);
            yield return Steps(2);
            Assert.IsTrue(Game.OutOfPlace, "premise: still out of place");
            Assert.IsTrue(Game.AtDecoy, "premise: within tolerance of a decoy");
            Assert.IsFalse(main.Game.Ghost.Visible, "the ghost shows although a decoy explains the chair");
            Assert.IsTrue(main.Game.Ghost.RingsVisible, "the rings hide at a decoy");

            // Back in place: nothing.
            Chair.Teleport(spawn, Game.Def.Player.Yaw);
            yield return Steps(2);
            Assert.IsFalse(Game.OutOfPlace);
            Assert.IsFalse(main.Game.Ghost.Visible || main.Game.Ghost.RingsVisible, "ghost or rings in place");
        }

        [UnityTest]
        public IEnumerator Step14_CarryBack()
        {
            yield return DiscoverDisplacedChair();
            FurniturePose remembered = Game.MemoryOf(Habitant).PlayerSlot;
            Assert.Less(Planar(remembered.Position, Game.Def.Player.Position), 0.05f, "premise: the remembered pose is the spawn");

            bool carried = false;
            bool released = false;
            bool movedWhileCarried = false;
            float worstGap = 0f;
            int carriedSteps = 0;
            Vector3 releasePosition = Vector3.zero;
            float releaseYaw = 0f;
            void Watch()
            {
                if (Chair.Carried)
                {
                    carried = true;
                    carriedSteps++;
                    // Scripted input during the carry: it must have no effect.
                    Chair.ScriptedDirection = Vector3.right;
                    movedWhileCarried |= Chair.IsMoving;
                    InhabitantRoutine r = Habitant.Routine;
                    if (r.LastActivity == RoutineActivity.Carrying)
                    {
                        // One step of lag at CarrySpeed at most: the furniture follows the anchor, not the input.
                        worstGap = Mathf.Max(worstGap, (Chair.transform.position - r.CarryAnchor).magnitude);
                    }
                }
                else if (carried && !released)
                {
                    released = true;
                    Chair.ScriptedDirection = null;
                    releasePosition = Chair.transform.position;
                    releaseYaw = Chair.Yaw;
                }
            }
            Game.FixedStepped += Watch;
            yield return Run(StepsFor(60f), () => Game.State != PlayState.Playing || (released && Habitant.Mode == InhabitantMode.Routine), 4f);
            Game.FixedStepped -= Watch;
            Chair.ScriptedDirection = null;

            Assert.AreEqual(PlayState.Playing, Game.State, $"the level ended during the carry ({Game.LoseReason})");
            Assert.IsTrue(carried, $"the inhabitant never picked the chair up (mode {Habitant.Mode}, activity {Habitant.Routine.LastActivity})");
            Assert.IsTrue(released, "the inhabitant never put the chair down");
            Assert.AreEqual(1, Game.CarryCount);
            Assert.Greater(carriedSteps, StepsFor(Tuning.PickUpDuration + Tuning.PutDownDuration) - 2, "the carry was too short to be real");
            Assert.IsFalse(movedWhileCarried, "a carried chair counted as moving");
            Assert.LessOrEqual(worstGap, Tuning.CarrySpeed * Dt * 2f + 1e-3f, $"the carried chair left its carrier's anchor by {worstGap:0.000} m");
            Assert.LessOrEqual(Planar(releasePosition, remembered.Position), 0.1f, "put down away from the remembered pose");
            Assert.LessOrEqual(Mathf.Abs(Mathf.DeltaAngle(releaseYaw, remembered.Yaw)), 5f, "put down at the wrong yaw");
            Assert.LessOrEqual(Planar(Chair.transform.position, remembered.Position), 0.1f, "the chair moved after the put down");
            Assert.AreEqual(InhabitantMode.Routine, Habitant.Mode, "the inhabitant did not resume");
            Assert.LessOrEqual(Planar(Game.MemoryOf(Habitant).PlayerSlot.Position, remembered.Position), 0.1f, "the carrier's slot is not the put down pose");
        }

        /// <summary>
        /// M2.2 (S4), on the test level with two inhabitants (not in levels.json): after a put down, every
        /// inhabitant remembers the chair where it was put down, not only the carrier.
        /// </summary>
        [UnityTest]
        public IEnumerator Step14c_PutDownUpdatesEveryInhabitant()
        {
            int before = exceptions;
            Game.LoadLevel("test_two_inhabitants");
            Game.Rules = GameRules.M2;
            yield return Steps(2);
            Assert.AreEqual(before, exceptions, "the test level logged errors: " + string.Join(" | ", logged));
            Assert.AreEqual(2, Game.Level.Inhabitants.Count, "premise: two inhabitants");
            CollectionAssert.DoesNotContain(Game.LevelOrder, "test_two_inhabitants", "the test level must not be played");
            Inhabitant carrier = Game.Level.Inhabitants[0];
            Inhabitant other = Game.Level.Inhabitants[1];
            Vector3 spawn = Chair.transform.position;
            var otherSpot = new Vector3(-0.8f, 0f, -0.2f);

            // The other inhabitant alone sees the chair 0.5 m off its spawn: in place, its slot moves there.
            Vector3 nudged = spawn + Vector3.forward * 0.5f;
            carrier.Pin(WindowSpot, YawToward(WindowSpot, spawn) + 180f);
            Chair.Teleport(nudged, 0f);
            other.Pin(otherSpot, YawToward(otherSpot, nudged), 0f, true);
            yield return Steps(2);
            Assert.AreEqual(Observation.Confirmed, Game.LastObservationOf(other), "premise: the other inhabitant confirms the nudged chair");
            Assert.Less(Planar(Game.MemoryOf(other).PlayerSlot.Position, nudged), 0.05f, "premise: its slot took the nudged pose");
            Assert.Less(Planar(Game.MemoryOf(carrier).PlayerSlot.Position, spawn), 0.05f, "premise: the carrier still remembers the spawn");

            // The other one freezes; the carrier finds the chair far away and carries it back to the spawn.
            other.Pin(otherSpot, YawToward(otherSpot, nudged) + 180f);
            var displaced = new Vector3(-3.2f, 0f, -0.6f);
            Chair.Teleport(displaced, 0f);
            carrier.Pin(WindowSpot, YawToward(WindowSpot, displaced), 0f, true);
            bool carried = false;
            bool released = false;
            Vector3 putDown = Vector3.zero;
            void Watch()
            {
                carried |= Chair.Carried;
                if (carried && !Chair.Carried && !released)
                {
                    released = true;
                    putDown = Chair.transform.position;
                }
            }
            Game.FixedStepped += Watch;
            yield return Run(StepsFor(60f), () => released || Game.State != PlayState.Playing, 4f);
            Game.FixedStepped -= Watch;
            Assert.AreEqual(PlayState.Playing, Game.State, $"the level ended ({Game.LoseReason})");
            Assert.IsTrue(carried && released, "premise: the carrier never carried the chair back");
            Assert.Less(Planar(putDown, spawn), 0.1f, "premise: put down at the carrier's remembered pose");
            Assert.Greater(Planar(nudged, putDown), 0.4f, "premise: the other inhabitant remembered another pose");
            Assert.Less(Planar(Game.MemoryOf(carrier).PlayerSlot.Position, putDown), 0.05f, "the carrier's slot is not the put down pose");
            Assert.Less(Planar(Game.MemoryOf(other).PlayerSlot.Position, putDown), 0.05f,
                "the other inhabitant's slot is not the put down pose");
        }

        /// <summary>M2.1 (11.5): a key held from the carry through the put down never moves the chair.</summary>
        [UnityTest]
        public IEnumerator Step14b_KeyHeldThroughCarry()
        {
            yield return DiscoverDisplacedChair();
            bool carried = false;
            bool released = false;
            bool movedAfter = false;
            int afterRelease = 0;
            Vector3 putDown = Vector3.zero;
            void Watch()
            {
                if (Chair.Carried)
                {
                    carried = true;
                    Chair.ScriptedDirection = Vector3.right;
                }
                else if (carried)
                {
                    if (!released)
                    {
                        released = true;
                        putDown = Chair.transform.position;
                    }
                    afterRelease++;
                    movedAfter |= Chair.IsMoving || Planar(Chair.transform.position, putDown) > 1e-4f;
                }
            }
            Game.FixedStepped += Watch;
            yield return Run(StepsFor(60f), () => Game.State != PlayState.Playing || afterRelease >= 25, 4f);
            Game.FixedStepped -= Watch;
            Assert.IsTrue(carried, "premise: the chair was never carried");
            Assert.IsTrue(released, "premise: the chair was never put down");
            Assert.AreEqual(PlayState.Playing, Game.State, $"the held key got the level lost ({Game.LoseReason})");
            Assert.IsFalse(movedAfter, "a key held through the carry moved the chair after the put down");
            Assert.IsTrue(Chair.WaitingForNeutralInput, "the held key re-armed the input");

            // One neutral step re-arms the input: the next press moves the chair (3 steps, under the grace).
            Chair.ScriptedDirection = null;
            yield return Steps(1);
            Assert.IsFalse(Chair.WaitingForNeutralInput, "a neutral step did not re-arm the input");
            Chair.ScriptedDirection = Vector3.right;
            yield return Steps(3);
            Chair.ScriptedDirection = null;
            Assert.Greater(Planar(Chair.transform.position, putDown), 0.01f, "premise: the re-armed input does not move the chair");
            Assert.AreEqual(PlayState.Playing, Game.State);
        }

        // ----- 15 -----

        /// <summary>
        /// Drives the chair along <paramref name="direction"/> until its first hop landing and releases the
        /// input on that very step, then records the inhabitant for four seconds.
        /// </summary>
        private IEnumerator HopOnce(Vector3 direction, List<Record> records, Action<int, Vector3, bool> onHop, List<NoiseEvent> hopEvents)
        {
            int startHops = Chair.HopCount;
            bool hopped = false;
            void OnNoise(NoiseEvent e)
            {
                if (e.Kind == NoiseKind.Hop)
                {
                    hopEvents.Add(e);
                }
            }
            void Watch()
            {
                records.Add(Snapshot(Habitant.Routine));
                if (!hopped && Chair.HopCount > startHops)
                {
                    hopped = true;
                    Chair.ScriptedDirection = null;
                    onHop(records.Count - 1, Chair.transform.position, Game.Level.IsSilentAt(Chair.transform.position));
                }
            }
            Game.Noise += OnNoise;
            Game.FixedStepped += Watch;
            Chair.ScriptedDirection = direction;
            yield return Run(60, () => hopped, 1f);
            Chair.ScriptedDirection = null;
            yield return Run(StepsFor(4f), null, 1f);
            Game.FixedStepped -= Watch;
            Game.Noise -= OnNoise;
            Assert.IsTrue(hopped, "premise: the chair never hopped");
        }

        [UnityTest]
        public IEnumerator Step15_NoiseLure()
        {
            // Hard floor (level 1): the inhabitant 1.5 m away, facing away, hears the first hop.
            Vector3 spawn = Chair.transform.position;
            Vector3 spot = spawn + Vector3.right * 1.5f;
            Assert.IsFalse(Game.Level.IsSilentAt(spawn), "premise: level 1 spawn is a hard floor");
            Habitant.Pin(spot, YawToward(spot, spawn) + 180f, 0f, true);
            yield return Steps(2);
            Assert.IsFalse(Game.Seen, "premise: facing away");

            var records = new List<Record>();
            var hops = new List<NoiseEvent>();
            int hopRecord = -1;
            Vector3 hopAt = Vector3.zero;
            bool hopSilent = true;
            yield return HopOnce(Vector3.forward, records, (k, p, silent) => { hopRecord = k; hopAt = p; hopSilent = silent; }, hops);
            Assert.IsFalse(hopSilent, "premise: the hop landed on a hard floor");
            Assert.Less(Planar(hopAt, spot), Tuning.HopNoiseRadius, "premise: the hop is within the hop radius");
            Assert.AreEqual(1, hops.Count, "exactly one Hop noise event (the input is released on the first hop)");
            Assert.Less(Planar(hops[0].Position, hopAt), 0.05f, "the Hop event is not at the chair");
            AssertTelegraphThenLook(records, hopRecord, hops[0].Position, "hard floor hop");
            Assert.AreEqual(PlayState.Playing, Game.State, $"lost after the lure ({Game.LoseReason})");
            Assert.AreEqual(0, Game.DiscoveryCount, "a chair within tolerance of its place is not a discovery");

            // Rug (level 2): the same hop makes no noise and gets no reaction.
            yield return LoadLevel("level2");
            LevelDef def = Game.Def;
            Assert.IsNotEmpty(def.Rugs, "premise: level 2 has rugs");
            RugDef rug = def.Rugs[0];
            foreach (RugDef r in def.Rugs)
            {
                if (Mathf.Max(r.SizeX, r.SizeZ) > Mathf.Max(rug.SizeX, rug.SizeZ))
                {
                    rug = r;
                }
            }
            Vector3 center = new Vector3(rug.X, 0f, rug.Z);
            Vector3 along = YawMath.Forward(rug.Yaw + (rug.SizeX >= rug.SizeZ ? 90f : 0f));
            Assert.GreaterOrEqual(Mathf.Max(rug.SizeX, rug.SizeZ) * 0.5f, 0.35f, "premise: the rug is long enough for one hop");
            Vector3 start = center - along * 0.15f;
            Assert.IsTrue(Game.Level.IsSilentAt(start) && Game.Level.IsSilentAt(center + along * 0.15f), "premise: the hop path is on the rug");
            Chair.Teleport(start, YawMath.YawOf(along));
            Vector3 rugSpot = FindSpotAround(start, 1.5f, along);
            FreezeOthers(Habitant, start);
            Habitant.Pin(rugSpot, YawToward(rugSpot, start) + 180f, 0f, true);
            yield return Steps(2);
            Assert.IsFalse(Game.Seen, "premise: nobody sees the chair on the rug");

            records.Clear();
            hops.Clear();
            yield return HopOnce(along, records, (k, p, silent) => { hopRecord = k; hopAt = p; hopSilent = silent; }, hops);
            Assert.IsTrue(hopSilent, "premise broken: the hop did not land on the rug");
            Assert.Less(Planar(hopAt, rugSpot), Tuning.HopNoiseRadius, "premise: the inhabitant is within the hop radius");
            Assert.AreEqual(0, hops.Count, "a hop on a rug made a noise event");
            for (int k = hopRecord; k < records.Count; k++)
            {
                Assert.AreEqual(InhabitantMode.Routine, records[k].Mode, $"the inhabitant reacted to a hop on a rug (record {k})");
                Assert.AreNotEqual(RoutineActivity.Telegraph, records[k].Activity, $"the inhabitant telegraphed after a hop on a rug (record {k})");
                Assert.Less(Mathf.Abs(Mathf.DeltaAngle(records[k].EyeYaw, records[hopRecord].EyeYaw)), 1e-3f, "the inhabitant turned after a hop on a rug");
            }
            Assert.AreEqual(0, Game.AlertCount);
            Assert.AreEqual(PlayState.Playing, Game.State);
        }

        /// <summary>
        /// A point <paramref name="distance"/> from <paramref name="from"/>, inside a room with a margin and
        /// clear of walls and props: perpendicular to <paramref name="along"/> first, then any of 16 directions.
        /// </summary>
        private Vector3 FindSpotAround(Vector3 from, float distance, Vector3 along)
        {
            float baseYaw = YawMath.YawOf(along);
            var yaws = new List<float> { baseYaw + 90f, baseYaw - 90f };
            for (int i = 0; i < 16; i++)
            {
                yaws.Add(baseYaw + i * 22.5f);
            }
            foreach (float yaw in yaws)
            {
                Vector3 p = from + YawMath.Forward(yaw) * distance;
                if (IsStandable(p))
                {
                    return p;
                }
            }
            Assert.Fail($"premise: no standing spot {distance} m from ({from.x:0.00}, {from.z:0.00})");
            return from;
        }

        private bool IsStandable(Vector3 p)
        {
            const float margin = 0.35f;
            RoomDef room = Game.Def.RoomAt(p);
            if (room == null)
            {
                return false;
            }
            foreach (Vector3 o in new[] { Vector3.right, Vector3.left, Vector3.forward, Vector3.back })
            {
                if (Game.Def.RoomAt(p + o * margin) != room)
                {
                    return false;
                }
            }
            return !Physics.CheckCapsule(p + Vector3.up * 0.3f, p + Vector3.up * 1.5f, Tuning.InhabitantRadius, Layers.OccluderMask,
                QueryTriggerInteraction.Ignore);
        }

        // ----- 16 and 17 -----

        [UnityTest]
        public IEnumerator Step16_CreakAlerts()
        {
            Vector3 spawn = Chair.transform.position;
            var spot = new Vector3(1.5f, 0f, -0.5f);
            float distance = Planar(spot, spawn);
            Assert.That(distance, Is.InRange(4.9f, 5.1f), "premise: the inhabitant stands 5 m away");
            Assert.Less(distance, Tuning.CreakRadius, "premise: inside the creak radius");
            Habitant.Pin(spot, YawToward(spot, spawn) + 180f, 0f, true);
            yield return Steps(1);
            Assert.IsFalse(Game.Seen, "premise: facing away");

            var records = new List<Record>();
            float creakAt = -1f;
            int creakRecord = -1;
            Vector3 creakSource = Vector3.zero;
            float warningFrom = -1f;
            bool flashed = false;
            bool transformMoved = false;
            float worstTremble = 0f;
            float worstTilt = 0f;
            Vector3 chairStart = Chair.transform.position;
            void OnNoise(NoiseEvent e)
            {
                if (e.Kind == NoiseKind.Creak && creakAt < 0f)
                {
                    creakAt = Game.Elapsed;
                    creakSource = e.Position;
                }
            }
            void Watch()
            {
                records.Add(Snapshot(Habitant.Routine));
                if (creakAt >= 0f && creakRecord < 0)
                {
                    creakRecord = records.Count - 1;
                }
                if (Game.Creak.Warning)
                {
                    if (warningFrom < 0f)
                    {
                        warningFrom = Game.Elapsed;
                    }
                    flashed |= main.Hud.CreakFlashing;
                }
                transformMoved |= Chair.IsMoving || (Chair.transform.position - chairStart).sqrMagnitude > 1e-10f;
            }
            void Tremble()
            {
                if (!Game.Creak.Warning || Chair.Visual == null)
                {
                    return;
                }
                worstTremble = Mathf.Max(worstTremble, (Chair.Visual.position - Chair.transform.position).magnitude);
                worstTilt = Mathf.Max(worstTilt, Vector3.Angle(Chair.Visual.up, Vector3.up));
            }
            Game.Noise += OnNoise;
            Game.FixedStepped += Watch;
            yield return Run(StepsFor(35f), () => creakRecord >= 0 && records.Count - creakRecord > StepsFor(5f), 8f, Tremble);
            Game.FixedStepped -= Watch;
            Game.Noise -= OnNoise;

            Assert.GreaterOrEqual(creakAt, 0f, "the still chair never creaked in 35 s");
            Assert.AreEqual(Tuning.CreakStartDelay + Tuning.CreakFillTime, creakAt, Dt * 1.5f, "creak time");
            Assert.AreEqual(Tuning.CreakStartDelay + Tuning.CreakFillTime - Tuning.CreakWarning, warningFrom, Dt * 2.5f, "warning start");
            Assert.IsTrue(flashed, "the HUD creak gauge never flashed during the warning");
            Assert.IsFalse(transformMoved, "the chair transform moved: the tremble must stay on the visual");
            Assert.LessOrEqual(worstTremble, Tuning.CreakTrembleDistance + 1e-4f, "tremble offset too large");
            Assert.LessOrEqual(worstTilt, Tuning.CreakTrembleDegrees + 0.05f, "tremble tilt too large");
            Assert.Less(Planar(creakSource, chairStart), 0.05f, "the creak is not at the chair");
            AssertTelegraphThenLook(records, creakRecord, chairStart, "creak in range");
            Assert.AreEqual(PlayState.Playing, Game.State, $"lost after the creak ({Game.LoseReason})");
            Assert.AreEqual(0, Game.DiscoveryCount, "a chair where it belongs is not a discovery");
            Assert.AreEqual(0f, Game.SuspicionOf(Habitant).Value, 1e-6f);
        }

        [UnityTest]
        public IEnumerator Step17_CreakOutOfRange()
        {
            string chosen = null;
            Vector3 spot = Vector3.zero;
            foreach (string id in new[] { "level2", "level3" })
            {
                if (!new List<string>(Game.LevelOrder).Contains(id))
                {
                    continue;
                }
                yield return LoadLevel(id);
                if (TryFarSpot(Chair.transform.position, out spot))
                {
                    chosen = id;
                    break;
                }
            }
            Assert.IsNotNull(chosen, "premise: no standing spot about 9 m from the spawn in level 2 or 3 (are they in levels.json?)");
            Vector3 spawn = Chair.transform.position;
            Assert.Greater(Planar(spot, spawn), Tuning.CreakRadius + 0.5f, "premise: out of the creak radius");
            FreezeOthers(Habitant, spawn);
            Habitant.Pin(spot, YawToward(spot, spawn) + 180f, 0f, true);
            yield return Steps(1);

            var records = new List<Record>();
            float creakAt = -1f;
            int creakRecord = -1;
            Vector3 creakSource = Vector3.zero;
            void OnNoise(NoiseEvent e)
            {
                if (e.Kind == NoiseKind.Creak && creakAt < 0f)
                {
                    creakAt = Game.Elapsed;
                    creakSource = e.Position;
                }
            }
            void Watch()
            {
                records.Add(Snapshot(Habitant.Routine));
                if (creakAt >= 0f && creakRecord < 0)
                {
                    creakRecord = records.Count - 1;
                }
            }
            Game.Noise += OnNoise;
            Game.FixedStepped += Watch;
            yield return Run(StepsFor(35f), () => creakRecord >= 0 && records.Count - creakRecord > StepsFor(4f), 8f);
            Game.FixedStepped -= Watch;
            Game.Noise -= OnNoise;

            Assert.GreaterOrEqual(creakAt, 0f, $"premise: the creak never fired ({chosen})");
            Assert.Less(Planar(creakSource, spawn), 0.05f, "the creak is not at the chair");
            Assert.Greater(Planar(spot, creakSource), Tuning.CreakRadius, "premise: the listener is out of range");
            for (int k = creakRecord; k < records.Count; k++)
            {
                Assert.AreEqual(InhabitantMode.Routine, records[k].Mode, $"the inhabitant 9 m away reacted to the creak (record {k})");
                Assert.AreNotEqual(RoutineActivity.Telegraph, records[k].Activity, $"the inhabitant 9 m away telegraphed (record {k})");
                Assert.Less(Mathf.Abs(Mathf.DeltaAngle(records[k].EyeYaw, records[creakRecord].EyeYaw)), 1e-3f, "the inhabitant 9 m away turned");
            }
            Assert.AreEqual(0, Game.AlertCount, "an alert was delivered");
            Assert.AreEqual(PlayState.Playing, Game.State);
        }

        /// <summary>A standing spot inside a room as close to 9 m from <paramref name="from"/> as possible, beyond the creak radius.</summary>
        private bool TryFarSpot(Vector3 from, out Vector3 spot)
        {
            spot = Vector3.zero;
            float bestScore = float.MaxValue;
            bool found = false;
            foreach (RoomDef room in Game.Def.AllRooms())
            {
                for (float x = room.X - room.SizeX * 0.5f; x <= room.X + room.SizeX * 0.5f; x += 0.25f)
                {
                    for (float z = room.Z - room.SizeZ * 0.5f; z <= room.Z + room.SizeZ * 0.5f; z += 0.25f)
                    {
                        var p = new Vector3(x, 0f, z);
                        float d = Planar(p, from);
                        if (d < Tuning.CreakRadius + 1f)
                        {
                            continue;
                        }
                        float score = Mathf.Abs(d - 9f);
                        if (score < bestScore && IsStandable(p))
                        {
                            bestScore = score;
                            spot = p;
                            found = true;
                        }
                    }
                }
            }
            return found;
        }

        // ----- 18 -----

        [UnityTest]
        public IEnumerator Step18_NeverCreaks()
        {
            // Frozen at station 1, facing the bookshelf: far from the loop, and blind to it.
            var far = new Vector3(-1.5f, 0f, 2.2f);
            Habitant.Pin(far, 0f);
            Vector3 s = Chair.transform.position;
            Vector3[] loop = { s + new Vector3(0f, 0f, 1f), s + new Vector3(1f, 0f, 1f), s + new Vector3(1f, 0f, 0f), s };
            int next = 0;
            int total = 0;
            int moving = 0;
            int creaks = 0;
            bool warning = false;
            bool everSeen = false;
            float maxGauge = 0f;
            float driven = 0f;
            Vector3 last = s;
            void OnNoise(NoiseEvent e)
            {
                if (e.Kind == NoiseKind.Creak)
                {
                    creaks++;
                }
            }
            void Drive()
            {
                if (Game.State != PlayState.Playing)
                {
                    Chair.ScriptedDirection = null;
                    return;
                }
                total++;
                moving += Chair.IsMoving ? 1 : 0;
                warning |= Game.Creak.Warning;
                everSeen |= Game.Seen;
                maxGauge = Mathf.Max(maxGauge, Game.Creak.Value);
                driven += Planar(Chair.transform.position, last);
                last = Chair.transform.position;
                Vector3 to = YawMath.Planar(loop[next] - Chair.transform.position);
                if (to.magnitude < 0.12f)
                {
                    next = (next + 1) % loop.Length;
                    to = YawMath.Planar(loop[next] - Chair.transform.position);
                }
                Chair.ScriptedDirection = to.normalized;
            }
            Game.Noise += OnNoise;
            Game.FixedStepped += Drive;
            Chair.ScriptedDirection = Vector3.forward;
            yield return Run(StepsFor(60f), () => Game.State != PlayState.Playing, 8f);
            Game.FixedStepped -= Drive;
            Game.Noise -= OnNoise;
            Chair.ScriptedDirection = null;

            Assert.AreEqual(PlayState.Playing, Game.State, $"the level ended ({Game.LoseReason})");
            Assert.GreaterOrEqual(total * Dt, 60f - 1e-3f, "premise: less than 60 s of driving");
            Assert.GreaterOrEqual(moving, (int)(total * 0.95f), $"premise: the chair moved only {moving} of {total} steps");
            Assert.Greater(driven, 60f, $"premise: the chair drove only {driven:0.0} m in 60 s");
            Assert.IsFalse(everSeen, "premise: the frozen inhabitant saw the loop");
            Assert.AreEqual(0, creaks, "a chair that keeps moving creaked");
            Assert.IsFalse(warning, "the creak warning came on");
            Assert.Less(maxGauge, 0.05f, $"the creak gauge rose to {maxGauge:0.00} while moving");
            Assert.AreEqual(0, Game.AlertCount, "a frozen inhabitant heard the hops");
        }

        // ----- 19 -----

        [UnityTest]
        public IEnumerator Step19_ExitOnlyUnseen()
        {
            ZoneDef exit = Game.Def.Exit;
            var exitCenter = new Vector3(exit.X, 0f, exit.Z);
            // Frozen at station 2, staring at the doormat: it never observes nor hears, it only sees.
            var spot = new Vector3(1.2f, 0f, 1.4f);
            Habitant.Pin(spot, YawToward(spot, exitCenter));
            Chair.Teleport(new Vector3(exit.X - exit.SizeX * 0.5f - 0.05f, 0f, exit.Z), 90f);
            yield return Steps(2);
            Assert.IsTrue(Game.Seen, "premise: the chair is seen at the doormat");
            Assert.IsFalse(exit.Contains(Chair.transform.position), "premise: the chair starts outside the exit");

            Chair.ScriptedDirection = Vector3.right;
            int guard = 0;
            while (!exit.Contains(Chair.transform.position) && guard++ < 30 && Game.State == PlayState.Playing)
            {
                yield return new WaitForFixedUpdate();
            }
            Chair.ScriptedDirection = null;
            Assert.IsTrue(exit.Contains(Chair.transform.position), "premise: the chair never entered the exit");
            Assert.AreEqual(PlayState.Playing, Game.State, "entering the exit while seen ended the level");
            yield return Steps(10);
            Assert.IsTrue(exit.Contains(Chair.transform.position));
            Assert.IsTrue(Game.Seen, "premise: still seen on the doormat");
            Assert.AreEqual(PlayState.Playing, Game.State, "the exit counted while seen");
            Assert.IsFalse(main.Hud.WinVisible);

            Habitant.Pin(spot, YawToward(spot, exitCenter) + 180f);
            yield return Steps(1);
            Assert.IsFalse(Game.Seen, "premise: the inhabitant looks away");
            Assert.AreEqual(PlayState.Won, Game.State, "unseen on the doormat did not win");
            Assert.IsTrue(main.Hud.WinVisible, "win panel hidden");
        }

        /// <summary>
        /// M2.1 (11.9) step 19 in the real case: an observing inhabitant sees the chair reach the exit. No win,
        /// a discovery after the grace, and the chair is carried back to where it belongs.
        /// </summary>
        [UnityTest]
        public IEnumerator Step19b_ExitWhileSeenIsCarriedBack()
        {
            ZoneDef exit = Game.Def.Exit;
            var exitCenter = new Vector3(exit.X, 0f, exit.Z);
            Vector3 home = Game.Def.Player.Position;
            var spot = new Vector3(1.2f, 0f, 1.4f);
            Habitant.Pin(spot, YawToward(spot, exitCenter), 0f, true);
            Chair.Teleport(new Vector3(exit.X - exit.SizeX * 0.5f - 0.05f, 0f, exit.Z), 90f);
            Chair.ScriptedDirection = Vector3.right;
            int guard = 0;
            while (!exit.Contains(Chair.transform.position) && guard++ < 30 && Game.State == PlayState.Playing)
            {
                yield return new WaitForFixedUpdate();
            }
            Chair.ScriptedDirection = null;
            Assert.IsTrue(exit.Contains(Chair.transform.position), "premise: the chair never entered the exit");
            Assert.IsTrue(Game.Seen, "premise: the chair is seen on the doormat");
            Assert.AreEqual(PlayState.Playing, Game.State, "reaching the exit while seen ended the level");

            bool won = false;
            bool carried = false;
            bool released = false;
            Vector3 putDown = Vector3.zero;
            void Watch()
            {
                won |= Game.State == PlayState.Won;
                if (Chair.Carried)
                {
                    carried = true;
                }
                else if (carried && !released)
                {
                    released = true;
                    putDown = Chair.transform.position;
                }
            }
            Game.FixedStepped += Watch;
            yield return Run(StepsFor(60f), () => Game.State != PlayState.Playing || (released && Habitant.Mode == InhabitantMode.Routine), 4f);
            Game.FixedStepped -= Watch;
            Assert.IsFalse(won, "the chair won while seen on the doormat");
            Assert.AreEqual(PlayState.Playing, Game.State, $"the level ended ({Game.LoseReason})");
            Assert.AreEqual(1, Game.DiscoveryCount, "the chair on the doormat was not discovered");
            Assert.IsTrue(carried, "the chair was never carried back");
            Assert.IsTrue(released, "the chair was never put down");
            Assert.LessOrEqual(Planar(putDown, home), 0.1f, "the chair was not put back where it belongs");
            Assert.IsFalse(exit.Contains(Chair.transform.position));
        }

        /// <summary>After a win with a next level, Enter loads it (win.next on the panel, Update reads the key).</summary>
        [UnityTest]
        public IEnumerator Step20b_EnterLoadsNextLevel()
        {
            Assert.IsTrue(Game.HasNextLevel, "premise: level 1 has a next level in levels.json");
            string next = Game.NextLevelId;
            ZoneDef exit = Game.Def.Exit;
            var exitCenter = new Vector3(exit.X, 0f, exit.Z);
            Vector3 at = Habitant.Routine.Position;
            Habitant.Pin(at, YawToward(exitCenter, at));
            Chair.Teleport(new Vector3(exit.X - exit.SizeX * 0.5f - 0.3f, 0f, exit.Z), 90f);
            Chair.ScriptedDirection = Vector3.right;
            int guard = 0;
            while (Game.State == PlayState.Playing && guard++ < 60)
            {
                yield return new WaitForFixedUpdate();
            }
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Won, Game.State, "premise: level 1 was not won");
            Assert.IsTrue(main.Hud.WinNextVisible, "the win panel does not show win.next");
            yield return Steps(5);
            Assert.AreEqual("level1", Game.LevelId, "a level loaded without Enter");

            InputReader.InjectNextLevelPress();
            guard = 0;
            while (Game.LevelId == "level1" && guard++ < 25)
            {
                yield return new WaitForFixedUpdate();
            }
            Assert.AreEqual(next, Game.LevelId, "Enter did not load the next level");
            Assert.AreEqual(next, Game.Def.Id);
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.IsFalse(main.Hud.WinVisible, "the win panel is still shown");
            Assert.AreEqual(0, exceptions, "errors while loading the next level: " + string.Join(" | ", logged));
        }

        // ----- 20 -----

        private sealed class RouteResult
        {
            public PlayState State;
            public float Time;
            public int Discoveries;
            public int Alerts;
            public int Creaks;
            public int Explained;
            public bool RugNearInhabitant;
            public int Waypoint;
            public int Waypoints;
            public LoseReason Reason;
        }

        /// <summary>
        /// Replays the level's designerRoute (docs/CONTRACT_M2.md 4): at game time "at", drive straight
        /// toward (x, z) at full input; release the input when within 0.1 m; then wait for the next "at".
        /// When the next "at" has already passed, the next leg starts on the same step (no stop).
        /// The input is decided at the end of each fixed step, so the replay does not depend on timeScale.
        /// </summary>
        private IEnumerator ReplayRoute(RouteResult result, float offset = 0f)
        {
            List<RouteStepDef> route = Game.Def.DesignerRoute;
            int k = 0;
            bool driving = false;
            result.Waypoints = route.Count;
            void Drive()
            {
                if (Game.State != PlayState.Playing)
                {
                    Chair.ScriptedDirection = null;
                    return;
                }
                if (Chair.IsMoving && Game.Level.IsSilentAt(Chair.transform.position))
                {
                    foreach (Inhabitant h in Game.Level.Inhabitants)
                    {
                        result.RugNearInhabitant |= Planar(h.Routine.Position, Chair.transform.position) <= Tuning.HopNoiseRadius;
                    }
                }
                while (k < route.Count)
                {
                    RouteStepDef w = route[k];
                    if (!driving)
                    {
                        if (Game.Elapsed < Mathf.Max(0f, w.At + offset) - 1e-4f)
                        {
                            Chair.ScriptedDirection = null;
                            return;
                        }
                        driving = true;
                    }
                    Vector3 to = YawMath.Planar(new Vector3(w.X, 0f, w.Z) - Chair.transform.position);
                    if (to.magnitude > 0.1f)
                    {
                        Chair.ScriptedDirection = to.normalized;
                        return;
                    }
                    driving = false;
                    k++;
                }
                Chair.ScriptedDirection = null;
            }
            Game.FixedStepped += Drive;
            yield return Run(StepsFor(150f), () => Game.State != PlayState.Playing, 8f);
            Game.FixedStepped -= Drive;
            Chair.ScriptedDirection = null;
            result.State = Game.State;
            result.Reason = Game.LoseReason;
            result.Time = Game.Elapsed;
            result.Discoveries = Game.DiscoveryCount;
            result.Alerts = Game.AlertCount;
            result.Creaks = Game.CreakCount;
            result.Explained = Game.ExplainedByDecoySteps;
            result.Waypoint = k;
        }

        /// <summary>
        /// M2.1 (11.8): every designer route wins with every "at" shifted by -0.2 s, 0 and +0.2 s, with no
        /// discovery, no alert and no creak.
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step20_DesignerRoutes()
        {
            var failures = new List<string>();
            var runs = new List<(string id, float offset)>();
            foreach (string level in new[] { "level1", "level2", "level3" })
            {
                foreach (float shift in new[] { -0.2f, 0f, 0.2f })
                {
                    runs.Add((level, shift));
                }
            }
            foreach ((string level, float offset) in runs)
            {
                string id = level;
                if (!new List<string>(Game.LevelOrder).Contains(id))
                {
                    failures.Add($"{id}: not listed in levels.json");
                    continue;
                }
                int errorsBefore = exceptions;
                bool loaded = true;
                try
                {
                    Game.LoadLevel(id);
                    Game.Rules = GameRules.M2;
                }
                catch (Exception e)
                {
                    loaded = false;
                    failures.Add($"{id}: does not load: {e.Message}");
                }
                if (!loaded)
                {
                    continue;
                }
                yield return Steps(1);
                if (exceptions != errorsBefore)
                {
                    failures.Add($"{id}: {exceptions - errorsBefore} error(s) at boot: {string.Join(" | ", logged)}");
                }
                if (Game.Def.DesignerRoute == null || Game.Def.DesignerRoute.Count == 0)
                {
                    failures.Add($"{id}: no designerRoute");
                    continue;
                }
                var result = new RouteResult();
                yield return ReplayRoute(result, offset);
                id = $"{level} (offset {offset:+0.0;-0.0;0} s)";
                Debug.Log($"[Probe] {id} designer route: {result.State} ({result.Reason}) after {result.Time:0.0} s, waypoint {result.Waypoint}/{result.Waypoints}, " +
                          $"{result.Discoveries} discoveries, {result.Alerts} alerts, {result.Creaks} creaks, {result.Explained} explained steps, rug near inhabitant {result.RugNearInhabitant}");
                if (result.State != PlayState.Won)
                {
                    failures.Add($"{id}: the route did not win ({result.State}, {result.Reason}) after {result.Time:0.0} s, waypoint {result.Waypoint}/{result.Waypoints}");
                }
                if (result.Discoveries != 0 || result.Alerts != 0 || result.Creaks != 0)
                {
                    failures.Add($"{id}: {result.Discoveries} discoveries, {result.Alerts} alerts, {result.Creaks} creaks (all must be 0)");
                }
                if (id.StartsWith("level2") && !result.RugNearInhabitant)
                {
                    failures.Add($"{id}: the route never crossed a rug within 2 m of an inhabitant");
                }
                if (id.StartsWith("level3") && result.Explained == 0)
                {
                    failures.Add($"{id}: the route never got an ExplainedByDecoy observation");
                }
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }

        // ----- 21 -----

        [UnityTest]
        public IEnumerator Step21_SuspicionLose()
        {
            Vector3[] spots = { new Vector3(-3.2f, 0f, -0.8f), new Vector3(-2.4f, 0f, -1.4f), new Vector3(-3.4f, 0f, 0.6f) };
            for (int k = 0; k < spots.Length; k++)
            {
                Assert.Greater(Planar(spots[k], Game.Def.Player.Position), Tuning.DisplacementTolerance, "premise: away from the slot");
                // Teleport plus re-pin: the Pin cancels the investigation of the previous discovery. M2.1: one
                // incident gives one discovery, and an incident lasts while the chair stays in sight out of
                // place, so the re-pin first looks away for one step to end it.
                if (k > 0)
                {
                    Habitant.Pin(WindowSpot, YawToward(WindowSpot, spots[k]) + 180f, 0f, true);
                    yield return Steps(1);
                    Assert.IsFalse(Game.Seen, "premise: looking away ends the incident");
                }
                Chair.Teleport(spots[k], 0f);
                Habitant.Pin(WindowSpot, YawToward(WindowSpot, spots[k]), 0f, true);
                int waited = 0;
                while (Game.DiscoveryCount < k + 1 && Game.State == PlayState.Playing && waited < 30)
                {
                    yield return new WaitForFixedUpdate();
                    waited++;
                }
                Assert.IsTrue(Game.Seen, $"premise: discovery {k + 1}, the chair is seen");
                Assert.AreEqual(Mathf.RoundToInt(Tuning.DiscoveryGrace / Dt), waited, $"discovery {k + 1} did not take the grace");
                Assert.AreEqual(k + 1, Game.DiscoveryCount, $"discovery {k + 1} not counted");
                if (k < spots.Length - 1)
                {
                    Assert.AreEqual(PlayState.Playing, Game.State, $"lost after {k + 1} discoveries");
                    Assert.AreEqual(Tuning.SuspicionPerDiscovery * (k + 1), Game.SuspicionOf(Habitant).Value, 0.01f, $"suspicion after {k + 1}");
                    Assert.AreEqual(InhabitantMode.Investigating, Habitant.Mode);
                }
            }
            Assert.AreEqual(PlayState.Caught, Game.State, "three discoveries in a row did not lose");
            Assert.AreEqual(LoseReason.Suspicion, Game.LoseReason);
            Assert.AreSame(Habitant, Game.LostTo, "the startled inhabitant is not the one who reached 1");
            Assert.GreaterOrEqual(Game.MaxSuspicion, Tuning.SuspicionLose - 1e-3f);
            Assert.IsTrue(Habitant.Routine.IsStartled, "the inhabitant is not startled");
            Assert.IsTrue(main.Hud.FailVisible, "fail panel hidden");
            Assert.IsTrue(main.Hud.SuspicionFailVisible, "the fail panel does not show the suspicion reason");
            Assert.AreEqual(Strings.FailSuspicionTitle, main.Hud.FailTitleText);
            Assert.AreEqual(Strings.FailSuspicionBody, main.Hud.FailBodyText);
            yield return null;
            Assert.AreEqual(0f, main.Hud.TitleCardAlpha, "title card still visible over the fail panel");

            // Restart keeps the level and brings back the M1 fail strings for the next catch.
            Game.Restart();
            yield return Steps(2);
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.AreEqual(LoseReason.None, Game.LoseReason);
            Assert.AreEqual(0f, Game.MaxSuspicion);
            Assert.IsFalse(main.Hud.FailVisible);
        }
    
        /// <summary>M2.1 (11.9): suspicion decays in Routine and Alerted, never while investigating.</summary>
        [UnityTest]
        public IEnumerator Step21b_SuspicionDecaysOnlyInRoutineOrAlerted()
        {
            var displaced = new Vector3(-3.2f, 0f, -0.8f);
            Chair.Teleport(displaced, 0f);
            float toward = YawToward(WindowSpot, displaced);
            Habitant.Pin(WindowSpot, toward, 0f, true);
            int guard = 0;
            while (Game.DiscoveryCount == 0 && guard++ < 30)
            {
                yield return new WaitForFixedUpdate();
            }
            Assert.AreEqual(1, Game.DiscoveryCount, "premise: one discovery");
            SuspicionMeter meter = Game.SuspicionOf(Habitant);

            // Investigating: no decay.
            Assert.AreEqual(InhabitantMode.Investigating, Habitant.Mode, "premise: investigating");
            float before = meter.Value;
            yield return Steps(25);
            Assert.AreEqual(InhabitantMode.Investigating, Habitant.Mode, "premise: still investigating");
            Assert.AreEqual(before, meter.Value, 1e-6f, "suspicion decayed while investigating");

            // Routine (a reactive pin looking away): decay at SuspicionDecayPerSecond.
            Habitant.Pin(WindowSpot, toward + 180f, 0f, true);
            yield return Steps(1);
            Assert.AreEqual(InhabitantMode.Routine, Habitant.Mode, "premise: back in Routine");
            before = meter.Value;
            yield return Steps(50);
            Assert.AreEqual(before - Tuning.SuspicionDecayPerSecond * 50 * Dt, meter.Value, 1e-4f, "no decay in Routine");

            // Alerted (a noise straight ahead, so the look turns nothing toward the chair): decay too.
            Habitant.Routine.Alert(WindowSpot + YawMath.Forward(toward + 180f) * 2f, NoiseKind.Hop);
            yield return Steps(1);
            Assert.AreEqual(InhabitantMode.Alerted, Habitant.Mode, "premise: alerted");
            before = meter.Value;
            yield return Steps(50);
            Assert.AreEqual(InhabitantMode.Alerted, Habitant.Mode, "premise: still alerted");
            Assert.AreEqual(before - Tuning.SuspicionDecayPerSecond * 50 * Dt, meter.Value, 1e-4f, "no decay while alerted");
            Assert.AreEqual(1, Game.DiscoveryCount, "premise: no new discovery");
        }
}
}
