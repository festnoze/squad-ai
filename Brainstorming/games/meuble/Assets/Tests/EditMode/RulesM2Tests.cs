using System;
using System.Collections.Generic;
using Meuble.Core;
using NUnit.Framework;
using UnityEngine;

namespace Meuble.Tests
{
    /// <summary>
    /// docs/CONTRACT_M2.md 3.3 and 10: the creak gauge, driven like GameState drives it, one call per fixed
    /// step of 0.02 s with the level time at the start of the step. Step counts derive from Tuning, so with the
    /// PRD values: delay 250 steps, fill 1000, drain 500, warning from the 850th fill step.
    /// </summary>
    public sealed class RulesM2CreakGaugeTests
    {
        private const float Dt = Tuning.FixedStep;

        private static int StepsFor(float seconds) => Mathf.RoundToInt(seconds / Dt);

        private static readonly int DelaySteps = StepsFor(Tuning.CreakStartDelay);
        private static readonly int FillSteps = StepsFor(Tuning.CreakFillTime);
        private static readonly int DrainSteps = StepsFor(Tuning.CreakDrainTime);
        private static readonly int WarningFromFillStep = StepsFor(Tuning.CreakFillTime - Tuning.CreakWarning);
        private const float WarningLevel = 1f - Tuning.CreakWarning / Tuning.CreakFillTime;

        private sealed class Driver
        {
            public readonly CreakGauge Gauge = new CreakGauge();
            public int Steps;
            public int Creaks;

            public bool Step(bool moving, bool carried = false)
            {
                bool creak = Gauge.Step(Dt, moving, carried, Steps * Dt);
                Steps++;
                if (creak)
                {
                    Creaks++;
                }
                return creak;
            }

            /// <summary>Runs several steps and returns how many of them creaked.</summary>
            public int Run(int steps, bool moving, bool carried = false)
            {
                int creaks = 0;
                for (int i = 0; i < steps; i++)
                {
                    if (Step(moving, carried))
                    {
                        creaks++;
                    }
                }
                return creaks;
            }
        }

        [Test]
        public void Still_from_level_start_creaks_on_the_step_ending_at_25_s_not_one_early()
        {
            var d = new Driver();
            for (int i = 0; i < DelaySteps; i++)
            {
                Assert.IsFalse(d.Step(false), "no creak during the start delay");
                Assert.AreEqual(0f, d.Gauge.Value, $"the gauge filled before {Tuning.CreakStartDelay} s, at step {d.Steps}");
            }
            for (int i = 1; i < FillSteps; i++)
            {
                Assert.IsFalse(d.Step(false), $"creaked early, at fill step {i} of {FillSteps}");
            }
            Assert.AreEqual(1f - Dt / Tuning.CreakFillTime, d.Gauge.Value, 1e-4f, "premise: one step short of full");
            Assert.IsTrue(d.Step(false), "20 s of stillness after the delay creaks on this very step");
            Assert.AreEqual(DelaySteps + FillSteps, d.Steps);
            Assert.AreEqual(Tuning.CreakStartDelay + Tuning.CreakFillTime, d.Steps * Dt, 1e-3f, "the creak step ends at 25 s");
            Assert.AreEqual(1, d.Creaks);
        }

        [Test]
        public void An_accumulated_float_clock_creaks_on_the_same_step()
        {
            // GameState may sum dt instead of multiplying: 250 sums of 0.02f give 4.999996, still the 5 s mark.
            var g = new CreakGauge();
            float clock = 0f;
            int creakStep = -1;
            for (int step = 1; step <= DelaySteps + FillSteps + 10 && creakStep < 0; step++)
            {
                if (g.Step(Dt, false, false, clock))
                {
                    creakStep = step;
                }
                clock += Dt;
            }
            Assert.AreEqual(DelaySteps + FillSteps, creakStep);
        }

        [Test]
        public void Start_delay_blocks_fill_and_drain_and_ends_exactly_at_5_s()
        {
            var g = new CreakGauge();
            Assert.IsFalse(g.Step(Dt, false, false, Tuning.CreakStartDelay - Dt), "the step starting at 4.98 s");
            Assert.AreEqual(0f, g.Value, "nothing fills before the delay");
            Assert.IsFalse(g.Filling);
            Assert.IsTrue(float.IsPositiveInfinity(g.SecondsToCreak));
            g.Step(Dt, false, false, Tuning.CreakStartDelay);
            Assert.AreEqual(Dt / Tuning.CreakFillTime, g.Value, 1e-6f, "the step starting at 5.00 s fills");
            Assert.IsTrue(g.Filling);

            // Half fill it, then feed level times inside the delay: neither still nor moving changes it.
            for (int i = 1; i < FillSteps / 2; i++)
            {
                g.Step(Dt, false, false, 10f);
            }
            float half = g.Value;
            Assert.AreEqual(0.5f, half, 1e-4f, "premise: half full");
            for (int i = 0; i < 100; i++)
            {
                Assert.IsFalse(g.Step(Dt, true, false, 1f));
                Assert.IsFalse(g.Step(Dt, false, false, 1f));
            }
            Assert.AreEqual(half, g.Value, "the start delay neither fills nor drains");
        }

        [Test]
        public void Drain_empties_the_gauge_in_10_s_and_clamps_at_0()
        {
            var d = new Driver();
            d.Run(DelaySteps, false);
            Assert.AreEqual(0, d.Run(FillSteps - 1, false), "premise: no creak while filling to one step short of full");
            Assert.AreEqual(1f - Dt / Tuning.CreakFillTime, d.Gauge.Value, 1e-4f, "premise: about full");

            d.Run(DrainSteps - 1, true);
            float left = 1f - Dt / Tuning.CreakFillTime - (DrainSteps - 1) * Dt / Tuning.CreakDrainTime;
            Assert.AreEqual(left, d.Gauge.Value, 1e-4f, "drains by dt / 10 per moving step");
            Assert.Greater(d.Gauge.Value, 0f, "premise: not empty one step before 10 s");
            d.Step(true);
            Assert.AreEqual(0f, d.Gauge.Value, "empty after 10 s of motion, clamped at 0");

            Assert.AreEqual(0, d.Run(StepsFor(5f), true));
            Assert.AreEqual(0f, d.Gauge.Value, "moving on an empty gauge stays at 0");
            // Clamped, not negative: the next fill takes exactly 20 s again.
            Assert.AreEqual(0, d.Run(FillSteps - 1, false), "creaked early after a drain");
            Assert.IsTrue(d.Step(false), "creaked late after a drain: the gauge went below 0");
        }

        [Test]
        public void Moving_for_60_s_never_creaks_and_never_warns()
        {
            var d = new Driver();
            d.Run(DelaySteps, true);
            for (int i = 0; i < StepsFor(60f); i++)
            {
                Assert.IsFalse(d.Step(true), $"creaked while moving, at {d.Steps * Dt:0.00} s");
                Assert.IsFalse(d.Gauge.Warning);
                Assert.IsTrue(float.IsPositiveInfinity(d.Gauge.SecondsToCreak));
            }
            Assert.AreEqual(0f, d.Gauge.Value);

            // A player who keeps making progress: still for three quarters of the fill time (15 s), then moving
            // for the drain time (10 s), ten times over.
            var p = new Driver();
            p.Run(DelaySteps, false);
            float highest = 0f;
            for (int cycle = 0; cycle < 10; cycle++)
            {
                for (int i = 0; i < StepsFor(0.75f * Tuning.CreakFillTime); i++)
                {
                    Assert.IsFalse(p.Step(false), $"creaked in cycle {cycle}");
                    highest = Mathf.Max(highest, p.Gauge.Value);
                }
                Assert.AreEqual(0, p.Run(DrainSteps, true));
            }
            Assert.AreEqual(0.75f, highest, 1e-3f, "premise: each still stretch really filled the gauge");
        }

        [Test]
        public void A_creak_returns_true_once_resets_to_0_and_the_next_one_is_20_s_later()
        {
            var d = new Driver();
            d.Run(DelaySteps, false);
            Assert.AreEqual(0, d.Run(FillSteps - 1, false), "premise: no early creak");
            Assert.IsTrue(d.Step(false), "premise: the first creak");
            Assert.AreEqual(0f, d.Gauge.Value, "the gauge resets to 0 on the creak step");
            Assert.IsFalse(d.Gauge.Warning, "the warning ends with the creak");
            Assert.AreEqual(Tuning.CreakFillTime, d.Gauge.SecondsToCreak, 1e-3f);

            Assert.IsFalse(d.Step(false), "the creak fires once, not again on the next step");
            Assert.AreEqual(Dt / Tuning.CreakFillTime, d.Gauge.Value, 1e-6f, "and it refills from 0");
            Assert.AreEqual(0, d.Run(FillSteps - 2, false), "a second creak came early");
            Assert.IsTrue(d.Step(false), "the second creak comes exactly 20 s after the first");
            Assert.AreEqual(2, d.Creaks);
        }

        [Test]
        public void Carried_pauses_the_gauge_without_draining_it()
        {
            var d = new Driver();
            d.Run(DelaySteps, false);
            int half = FillSteps / 2;
            d.Run(half, false);
            float value = d.Gauge.Value;
            Assert.AreEqual(0.5f, value, 1e-4f, "premise: half full");
            for (int i = 0; i < StepsFor(30f); i++)
            {
                Assert.IsFalse(d.Step(i % 2 == 0, carried: true), "creaked while carried");
                Assert.AreEqual(value, d.Gauge.Value, "a carried furniture neither fills nor drains");
                Assert.IsFalse(d.Gauge.Filling);
                Assert.IsFalse(d.Gauge.Warning);
                Assert.IsTrue(float.IsPositiveInfinity(d.Gauge.SecondsToCreak));
            }
            Assert.AreEqual(0, d.Run(FillSteps - half - 1, false), "creaked early after the carry");
            Assert.IsTrue(d.Step(false), "the remaining 10 s finish exactly after the carry");
        }

        [Test]
        public void Warning_is_on_only_during_the_last_3_s_of_filling()
        {
            var d = new Driver();
            d.Run(DelaySteps, false);
            Assert.IsFalse(d.Gauge.Warning, "no warning during the start delay");
            for (int i = 1; i < WarningFromFillStep; i++)
            {
                d.Step(false);
                Assert.IsFalse(d.Gauge.Warning, $"warning too early, at {i * Dt:0.00} s of filling");
            }
            d.Step(false);
            Assert.IsTrue(d.Gauge.Warning, "the warning starts at 17 s of filling");
            Assert.AreEqual(Tuning.CreakWarning, d.Gauge.SecondsToCreak, 1e-3f);
            for (int i = WarningFromFillStep + 1; i < FillSteps; i++)
            {
                Assert.IsFalse(d.Step(false), "premise: no creak before 20 s");
                Assert.IsTrue(d.Gauge.Warning, $"warning dropped at {i * Dt:0.00} s of filling");
            }
            Assert.IsTrue(d.Step(false), "premise: the creak");
            Assert.IsFalse(d.Gauge.Warning, "the warning ends with the creak");
        }

        [Test]
        public void Warning_needs_a_still_furniture_that_is_not_carried()
        {
            var d = new Driver();
            d.Run(DelaySteps, false);
            d.Run(StepsFor(18f), false);
            Assert.IsTrue(d.Gauge.Warning, "premise: inside the warning");

            d.Step(true);
            Assert.GreaterOrEqual(d.Gauge.Value, WarningLevel, "premise: still above the warning level");
            Assert.IsFalse(d.Gauge.Warning, "a moving furniture is draining, not about to creak");
            Assert.IsTrue(float.IsPositiveInfinity(d.Gauge.SecondsToCreak));

            d.Step(false);
            Assert.IsTrue(d.Gauge.Warning, "still again: the warning resumes");

            d.Step(false, carried: true);
            Assert.IsFalse(d.Gauge.Warning, "a carried furniture does not tremble");
        }

        [Test]
        public void Seconds_to_creak_counts_down_while_filling()
        {
            var d = new Driver();
            d.Step(false);
            Assert.IsTrue(float.IsPositiveInfinity(d.Gauge.SecondsToCreak), "inside the start delay");
            d.Run(DelaySteps - 1, false);
            d.Step(false);
            Assert.AreEqual(Tuning.CreakFillTime - Dt, d.Gauge.SecondsToCreak, 1e-3f);
            d.Run(StepsFor(5f) - 1, false);
            Assert.AreEqual(Tuning.CreakFillTime - 5f, d.Gauge.SecondsToCreak, 1e-3f);
        }

        [Test]
        public void Reset_empties_the_gauge()
        {
            var d = new Driver();
            d.Run(DelaySteps + StepsFor(18f), false);
            Assert.IsTrue(d.Gauge.Warning, "premise: inside the warning");
            d.Gauge.Reset();
            Assert.AreEqual(0f, d.Gauge.Value);
            Assert.IsFalse(d.Gauge.Filling);
            Assert.IsFalse(d.Gauge.Warning);
            Assert.IsTrue(float.IsPositiveInfinity(d.Gauge.SecondsToCreak));
            Assert.AreEqual(0, d.Run(FillSteps - 1, false), "creaked early after a reset");
            Assert.IsTrue(d.Step(false));
        }
    }

    /// <summary>
    /// docs/CONTRACT_M2.md 3.1 as amended by 11: displacement memory, one slot per piece of furniture, a position
    /// only tolerance, decoys that explain whether or not they are seen, and a discovery grace of 0.2 s
    /// (10 fixed steps of 0.02 s with the PRD values).
    /// </summary>
    public sealed class RulesM2MemoryTests
    {
        private const float Dt = Tuning.FixedStep;
        private const float Tol = Tuning.DisplacementTolerance;
        private const string Chair = "chair";

        private static readonly int GraceSteps = Mathf.RoundToInt(Tuning.DiscoveryGrace / Dt);

        private static readonly FurniturePose Spawn = new FurniturePose(new Vector3(-3.2f, 0f, -2.2f), 20f);

        /// <summary>A unit planar direction that is not an axis, so distances mix both coordinates.</summary>
        private static readonly Vector3 Diagonal = new Vector3(0.6f, 0f, -0.8f);

        /// <summary>2 m from the spawn, far from both decoys.</summary>
        private static readonly FurniturePose OutOfPlace = Offset(Spawn, Diagonal * 2f, 0f);

        private static readonly FurniturePose DecoyA = new FurniturePose(new Vector3(1.5f, 0f, 1.0f), 90f);
        private static readonly FurniturePose DecoyB = new FurniturePose(new Vector3(-1.0f, 0f, 2.4f), -45f);

        private static FurniturePose Offset(FurniturePose p, Vector3 delta, float deltaYaw) =>
            new FurniturePose(p.Position + delta, p.Yaw + deltaYaw);

        private static FurnitureMemory Alone() => new FurnitureMemory(Spawn, new FurniturePose[0], new string[0], Chair);

        private static FurnitureMemory WithDecoys(FurniturePose[] poses, string[] kinds) =>
            new FurnitureMemory(Spawn, poses, kinds, Chair);

        private static FurnitureMemory WithDecoyA(string kind = Chair) => WithDecoys(new[] { DecoyA }, new[] { kind });

        private static void AssertPose(FurniturePose expected, FurniturePose actual, string message)
        {
            Assert.AreEqual(expected.Position.x, actual.Position.x, 1e-5f, message + " (x)");
            Assert.AreEqual(expected.Position.z, actual.Position.z, 1e-5f, message + " (z)");
            Assert.AreEqual(expected.Yaw, actual.Yaw, 1e-4f, message + " (yaw)");
        }

        /// <summary>Seen out of place: Suspect for 0.18 s, then Discovery on the step that reaches 0.20 s.</summary>
        private static void AssertSuspectThenDiscovery(FurnitureMemory m, FurniturePose at, string context)
        {
            for (int i = 1; i < GraceSteps; i++)
            {
                Assert.AreEqual(Observation.Suspect, m.Observe(true, at, Dt), $"{context}: {i * Dt:0.00} s out of place");
            }
            Assert.AreEqual(Observation.Discovery, m.Observe(true, at, Dt), $"{context}: {GraceSteps * Dt:0.00} s out of place");
        }

        private static void AssertAlways(Observation expected, FurnitureMemory m, FurniturePose at, int steps, string context)
        {
            for (int i = 0; i < steps; i++)
            {
                Assert.AreEqual(expected, m.Observe(true, at, Dt), $"{context}: step {i}");
            }
        }

        // ----- Tolerance: position only -----

        [Test]
        public void Tolerance_edges_are_inclusive_and_planar()
        {
            Assert.IsTrue(FurnitureMemory.WithinTolerance(Spawn, Offset(Spawn, Diagonal * (Tol - 0.01f), 0f)), "0.74 m is within");
            Assert.IsTrue(FurnitureMemory.WithinTolerance(Spawn, Offset(Spawn, Diagonal * Tol, 0f)), "exactly 0.75 m is within");
            Assert.IsFalse(FurnitureMemory.WithinTolerance(Spawn, Offset(Spawn, Diagonal * (Tol + 0.01f), 0f)), "0.76 m is not");
            Assert.IsTrue(FurnitureMemory.WithinTolerance(Spawn, Offset(Spawn, Vector3.up * 2f, 0f)), "height is ignored");
        }

        [Test]
        public void Tolerance_ignores_yaw()
        {
            Assert.IsTrue(FurnitureMemory.WithinTolerance(Spawn, Offset(Spawn, Vector3.zero, 90f)), "90 deg in place");
            Assert.IsTrue(FurnitureMemory.WithinTolerance(Spawn, Offset(Spawn, Vector3.zero, 180f)), "180 deg in place");
            Assert.IsTrue(FurnitureMemory.WithinTolerance(Spawn, Offset(Spawn, Diagonal * (Tol - 0.01f), 180f)), "0.74 m and turned around");
            Assert.IsFalse(FurnitureMemory.WithinTolerance(Spawn, Offset(Spawn, Diagonal * (Tol + 0.01f), 0f)), "0.76 m facing the same way");
        }

        // ----- Player slot -----

        [Test]
        public void First_sighting_at_spawn_is_confirmed_not_a_discovery()
        {
            FurnitureMemory m = Alone();
            AssertPose(Spawn, m.PlayerSlot, "the player slot is seeded at the spawn pose");
            Assert.AreEqual(Observation.Confirmed, m.Observe(true, Spawn, Dt));

            // The slot is the spawn pose, not "unset until first sighting": a first sighting 2 m away is suspect.
            AssertSuspectThenDiscovery(Alone(), OutOfPlace, "first sighting 2 m from the spawn");
        }

        [Test]
        public void A_90_deg_turn_in_place_is_confirmed()
        {
            FurnitureMemory m = Alone();
            FurniturePose turned = Offset(Spawn, Vector3.zero, 90f);
            AssertAlways(Observation.Confirmed, m, turned, 5 * GraceSteps, "turned 90 deg on the spot");
            AssertPose(turned, m.PlayerSlot, "the slot takes the seen yaw");
        }

        [Test]
        public void Not_seen_observes_nothing_and_keeps_the_slot()
        {
            FurnitureMemory m = Alone();
            for (int i = 0; i < 5 * GraceSteps; i++)
            {
                Assert.AreEqual(Observation.NotSeen, m.Observe(false, OutOfPlace, Dt));
            }
            AssertPose(Spawn, m.PlayerSlot, "an unseen move leaves the slot");
            AssertSuspectThenDiscovery(m, OutOfPlace, "seen later at the moved pose");
        }

        [Test]
        public void A_sighting_within_tolerance_updates_the_slot()
        {
            FurnitureMemory m = Alone();
            FurniturePose first = Offset(Spawn, Diagonal * (Tol - 0.05f), 60f);
            FurniturePose second = Offset(first, Diagonal * (Tol - 0.05f), 60f);
            Assert.IsFalse(FurnitureMemory.WithinTolerance(Spawn, second), "premise: the second pose is out of reach of the spawn");

            Assert.AreEqual(Observation.Confirmed, m.Observe(true, first, Dt));
            AssertPose(first, m.PlayerSlot, "the slot takes the pose it was last seen at");
            Assert.AreEqual(Observation.Confirmed, m.Observe(true, second, Dt), "only the updated slot makes this a confirmation");
            AssertPose(second, m.PlayerSlot, "the slot follows again");
        }

        [Test]
        public void Over_the_distance_tolerance_is_suspect_then_a_discovery()
        {
            AssertAlways(Observation.Confirmed, Alone(), Offset(Spawn, Diagonal * (Tol - 0.01f), 0f), 5 * GraceSteps, "0.74 m");
            AssertSuspectThenDiscovery(Alone(), Offset(Spawn, Diagonal * (Tol + 0.01f), 0f), "0.76 m");
        }

        [Test]
        public void A_discovery_keeps_the_slot_as_the_return_pose_and_creates_no_slot()
        {
            FurnitureMemory m = Alone();
            AssertSuspectThenDiscovery(m, OutOfPlace, "premise");
            AssertPose(Spawn, m.PlayerSlot, "the return pose is the remembered slot");
            Assert.AreEqual(Observation.NotSeen, m.Observe(false, OutOfPlace, Dt));
            // One slot per piece: the discovered pose is not learned, so the next incident there is suspect again.
            AssertSuspectThenDiscovery(m, OutOfPlace, "a discovery must not move or add a slot");
            AssertPose(Spawn, m.PlayerSlot, "still the remembered slot");
            Assert.AreEqual(Observation.Confirmed, m.Observe(true, Spawn, Dt), "back where it belongs");
        }

        [Test]
        public void Set_player_slot_moves_the_slot_and_ends_the_incident()
        {
            FurnitureMemory m = Alone();
            AssertAlways(Observation.Suspect, m, OutOfPlace, GraceSteps - 1, "premise: 0.18 s out of place");
            FurniturePose elsewhere = Offset(Spawn, -Diagonal * 2f, 30f);
            m.SetPlayerSlot(elsewhere);
            AssertPose(elsewhere, m.PlayerSlot, "SetPlayerSlot");
            AssertSuspectThenDiscovery(m, OutOfPlace, "a new slot starts a new incident");

            m.SetPlayerSlot(OutOfPlace);
            Assert.AreEqual(Observation.Confirmed, m.Observe(true, OutOfPlace, Dt), "the put down pose is where it belongs now");
            Assert.AreEqual(Observation.Suspect, m.Observe(true, Spawn, Dt), "the old slot is forgotten");
        }

        // ----- Discovery grace -----

        [Test]
        public void Out_of_place_for_0_18_s_is_suspect_and_0_20_s_is_a_discovery()
        {
            Assert.Greater(GraceSteps, 1, "premise: the grace spans several steps");
            Assert.AreEqual(Tuning.DiscoveryGrace, GraceSteps * Dt, 1e-5f, "premise: the grace is a whole number of steps");
            FurnitureMemory m = Alone();
            AssertSuspectThenDiscovery(m, OutOfPlace, "out of place");
            AssertPose(Spawn, m.PlayerSlot, "suspect steps never move the slot");
        }

        [Test]
        public void The_grace_counts_seconds_not_steps()
        {
            const float coarse = 0.05f;
            int steps = Mathf.RoundToInt(Tuning.DiscoveryGrace / coarse);
            Assert.AreNotEqual(GraceSteps, steps, "premise: a different step count than at 0.02 s");
            FurnitureMemory m = Alone();
            for (int i = 1; i < steps; i++)
            {
                Assert.AreEqual(Observation.Suspect, m.Observe(true, OutOfPlace, coarse), $"{i * coarse:0.00} s");
            }
            Assert.AreEqual(Observation.Discovery, m.Observe(true, OutOfPlace, coarse), "0.20 s in steps of 0.05 s");
        }

        [Test]
        public void A_one_step_unseen_gap_restarts_the_grace()
        {
            FurnitureMemory m = Alone();
            AssertAlways(Observation.Suspect, m, OutOfPlace, GraceSteps - 1, "premise: 0.18 s out of place");
            Assert.AreEqual(Observation.NotSeen, m.Observe(false, OutOfPlace, Dt));
            AssertSuspectThenDiscovery(m, OutOfPlace, "after a step unseen");
        }

        [Test]
        public void A_one_step_in_place_gap_restarts_the_grace()
        {
            FurnitureMemory m = Alone();
            AssertAlways(Observation.Suspect, m, OutOfPlace, GraceSteps - 1, "premise: 0.18 s out of place");
            Assert.AreEqual(Observation.Confirmed, m.Observe(true, Spawn, Dt));
            AssertSuspectThenDiscovery(m, OutOfPlace, "after a step in place");
        }

        [Test]
        public void A_one_step_explained_gap_restarts_the_grace()
        {
            FurnitureMemory m = WithDecoyA();
            Assert.IsFalse(FurnitureMemory.WithinTolerance(OutOfPlace, DecoyA), "premise: the out of place pose is not at the decoy");
            AssertAlways(Observation.Suspect, m, OutOfPlace, GraceSteps - 1, "premise: 0.18 s out of place");
            Assert.AreEqual(Observation.ExplainedByDecoy, m.Observe(true, DecoyA, Dt));
            AssertSuspectThenDiscovery(m, OutOfPlace, "after a step explained by a decoy");
        }

        [Test]
        public void Discovery_fires_once_per_incident()
        {
            FurnitureMemory m = Alone();
            int discoveries = 0;
            int firstAt = -1;
            for (int i = 1; i <= 50 * GraceSteps; i++)
            {
                // The chair even drifts while seen: still the same incident, still out of place.
                FurniturePose drifting = Offset(OutOfPlace, Diagonal * (0.001f * i), 0f);
                Observation o = m.Observe(true, drifting, Dt);
                Assert.That(o, Is.EqualTo(Observation.Suspect).Or.EqualTo(Observation.Discovery), $"step {i}");
                if (o == Observation.Discovery)
                {
                    discoveries++;
                    firstAt = firstAt < 0 ? i : firstAt;
                }
            }
            Assert.AreEqual(GraceSteps, firstAt, "premise: the discovery came at 0.20 s");
            Assert.AreEqual(1, discoveries, "one incident, one discovery, however long it lasts");

            Assert.AreEqual(Observation.NotSeen, m.Observe(false, OutOfPlace, Dt));
            AssertSuspectThenDiscovery(m, OutOfPlace, "a new incident gives a new discovery");
        }

        [Test]
        public void Reset_grace_restarts_the_timer_and_rearms_the_discovery()
        {
            FurnitureMemory m = Alone();
            AssertAlways(Observation.Suspect, m, OutOfPlace, GraceSteps - 1, "premise: 0.18 s out of place");
            m.ResetGrace();
            AssertSuspectThenDiscovery(m, OutOfPlace, "after ResetGrace");

            AssertAlways(Observation.Suspect, m, OutOfPlace, 3 * GraceSteps, "premise: the incident already gave its discovery");
            m.ResetGrace();
            AssertSuspectThenDiscovery(m, OutOfPlace, "ResetGrace ends the incident");
            AssertPose(Spawn, m.PlayerSlot, "ResetGrace never moves the slot");
        }

        // ----- Decoys -----

        [Test]
        public void A_decoy_of_the_same_kind_explains_the_chair_seen_or_not()
        {
            // Decoy vision is no longer an input: a decoy explains the chair whether or not it is seen.
            FurnitureMemory m = WithDecoyA();
            FurniturePose atDecoy = Offset(DecoyA, Diagonal * (Tol - 0.01f), 90f);
            Assert.IsFalse(FurnitureMemory.WithinTolerance(Spawn, atDecoy), "premise: far from the player slot");
            AssertAlways(Observation.ExplainedByDecoy, m, atDecoy, 50 * GraceSteps, "next to a decoy chair");
            AssertPose(Spawn, m.PlayerSlot, "an explained sighting leaves the player slot");
        }

        [Test]
        public void A_decoy_of_another_kind_does_not_explain_the_chair()
        {
            Assert.AreEqual(Observation.ExplainedByDecoy, WithDecoyA(Chair).Observe(true, DecoyA, Dt), "premise: a chair decoy explains");
            AssertSuspectThenDiscovery(WithDecoyA("stool"), DecoyA, "at a stool");
            Assert.AreEqual(Observation.ExplainedByDecoy, WithDecoyA("Chair").Observe(true, DecoyA, Dt), "kinds ignore case");
        }

        [Test]
        public void A_decoy_explains_only_within_its_position_tolerance()
        {
            Assert.AreEqual(Observation.ExplainedByDecoy, WithDecoyA().Observe(true, Offset(DecoyA, Diagonal * (Tol - 0.01f), 0f), Dt), "0.74 m");
            AssertSuspectThenDiscovery(WithDecoyA(), Offset(DecoyA, Diagonal * (Tol + 0.01f), 0f), "0.76 m from the decoy");
            Assert.AreEqual(Observation.ExplainedByDecoy, WithDecoyA().Observe(true, Offset(DecoyA, Vector3.zero, 90f), Dt), "turned 90 deg");
        }

        [Test]
        public void Each_decoy_has_its_own_slot()
        {
            FurnitureMemory m = WithDecoys(new[] { DecoyA, DecoyB }, new[] { Chair, Chair });
            Assert.AreEqual(Observation.ExplainedByDecoy, m.Observe(true, DecoyA, Dt), "at A");
            Assert.AreEqual(Observation.ExplainedByDecoy, m.Observe(true, DecoyB, Dt), "at B");
            var between = new FurniturePose((DecoyA.Position + DecoyB.Position) * 0.5f, 0f);
            Assert.IsFalse(FurnitureMemory.WithinTolerance(between, DecoyA) || FurnitureMemory.WithinTolerance(between, DecoyB),
                "premise: halfway is out of reach of both");
            Assert.AreEqual(Observation.Suspect, m.Observe(true, between, Dt), "two decoys do not make a region");
        }

        [Test]
        public void Decoy_slots_never_move()
        {
            var poses = new List<FurniturePose> { DecoyA };
            var m = new FurnitureMemory(Spawn, poses, new[] { Chair }, Chair);
            poses[0] = Spawn; // the caller's list is not the memory
            FurniturePose near = Offset(DecoyA, Diagonal * (Tol - 0.05f), 0f);
            FurniturePose further = Offset(near, Diagonal * (Tol - 0.05f), 0f);
            Assert.IsTrue(FurnitureMemory.WithinTolerance(near, further), "premise: each step is small");
            Assert.AreEqual(Observation.ExplainedByDecoy, m.Observe(true, near, Dt));
            AssertSuspectThenDiscovery(m, further, "a decoy slot does not follow the chair");
            AssertPose(Spawn, m.PlayerSlot, "the player slot is unchanged");
        }

        [Test]
        public void The_player_slot_comes_before_a_decoy()
        {
            FurniturePose decoyNearSpawn = Offset(Spawn, Diagonal * 0.6f, 0f);
            FurnitureMemory m = WithDecoys(new[] { decoyNearSpawn }, new[] { Chair });
            FurniturePose seen = Offset(Spawn, Diagonal * 0.4f, 0f);
            Assert.IsTrue(FurnitureMemory.WithinTolerance(seen, decoyNearSpawn), "premise: within both slots");
            Assert.AreEqual(Observation.Confirmed, m.Observe(true, seen, Dt));
            AssertPose(seen, m.PlayerSlot, "a confirmation updates the player slot");
        }

        [Test]
        public void Mismatched_decoy_lists_are_rejected()
        {
            Assert.Throws<ArgumentException>(() => new FurnitureMemory(Spawn, new[] { DecoyA }, new string[0], Chair));
            Assert.AreEqual(Observation.Confirmed, new FurnitureMemory(Spawn, null, null, Chair).Observe(true, Spawn, Dt),
                "no decoy at all: null lists are fine");
        }
    }

    /// <summary>docs/CONTRACT_M2.md 3.1 and 10: the suspicion meter, stepped in fixed steps of 0.02 s.</summary>
    public sealed class RulesM2SuspicionTests
    {
        private const float Dt = Tuning.FixedStep;

        private static void Decay(SuspicionMeter m, int steps)
        {
            for (int i = 0; i < steps; i++)
            {
                m.Step(Dt);
            }
        }

        [Test]
        public void Three_discoveries_lose_at_1_02()
        {
            Assert.Less(2f * Tuning.SuspicionPerDiscovery, Tuning.SuspicionLose, "premise: two discoveries are not enough");
            var m = new SuspicionMeter();
            Assert.AreEqual(0f, m.Value);
            Assert.IsFalse(m.Lost);
            m.AddDiscovery();
            Assert.AreEqual(Tuning.SuspicionPerDiscovery, m.Value, 1e-6f);
            Assert.IsFalse(m.Lost);
            m.AddDiscovery();
            Assert.AreEqual(2f * Tuning.SuspicionPerDiscovery, m.Value, 1e-6f);
            Assert.IsFalse(m.Lost, "two discoveries do not lose");
            m.AddDiscovery();
            Assert.AreEqual(3f * Tuning.SuspicionPerDiscovery, m.Value, 1e-5f, "1.02, not clamped");
            Assert.IsTrue(m.Lost, "three discoveries in a row lose");
        }

        [Test]
        public void Decay_is_0_02_per_second()
        {
            var m = new SuspicionMeter();
            m.AddDiscovery();
            Decay(m, 50);
            Assert.AreEqual(Tuning.SuspicionPerDiscovery - Tuning.SuspicionDecayPerSecond, m.Value, 1e-4f, "after 1 s");
            Decay(m, 450);
            Assert.AreEqual(Tuning.SuspicionPerDiscovery - 10f * Tuning.SuspicionDecayPerSecond, m.Value, 1e-4f, "after 10 s");
        }

        [Test]
        public void Decay_is_clamped_at_0()
        {
            var m = new SuspicionMeter();
            m.Step(Dt);
            Assert.AreEqual(0f, m.Value, "an empty meter stays at 0");
            m.AddDiscovery();
            Decay(m, Mathf.RoundToInt(30f / Dt));
            Assert.AreEqual(0f, m.Value, "decayed past 0 is exactly 0");
            m.AddDiscovery();
            Assert.AreEqual(Tuning.SuspicionPerDiscovery, m.Value, 1e-6f, "the meter did not go below 0");
        }

        [Test]
        public void Reaching_1_after_decay_still_loses_and_just_under_does_not()
        {
            // One discovery, 1 s of decay, two more: 0.32 + 0.68 = 1.00 (0.9999996 in float) loses.
            var exact = new SuspicionMeter();
            exact.AddDiscovery();
            Decay(exact, 50);
            exact.AddDiscovery();
            exact.AddDiscovery();
            Assert.AreEqual(Tuning.SuspicionLose, exact.Value, 1e-4f, "premise: the meter reads 1");
            Assert.IsTrue(exact.Lost, "reaching 1 loses");

            // One more step of decay: 0.9996, just under 1.
            var under = new SuspicionMeter();
            under.AddDiscovery();
            Decay(under, 51);
            under.AddDiscovery();
            under.AddDiscovery();
            Assert.Less(under.Value, Tuning.SuspicionLose, "premise: just under 1");
            Assert.IsFalse(under.Lost);

            // Ten seconds between discoveries: 0.14 + 0.68 = 0.82.
            var spaced = new SuspicionMeter();
            spaced.AddDiscovery();
            Decay(spaced, 500);
            spaced.AddDiscovery();
            spaced.AddDiscovery();
            Assert.IsFalse(spaced.Lost, "decay between discoveries saves the level");
        }

        [Test]
        public void Lost_is_latched_until_reset()
        {
            var m = new SuspicionMeter();
            m.AddDiscovery();
            m.AddDiscovery();
            m.AddDiscovery();
            Assert.IsTrue(m.Lost, "premise: lost");
            float value = m.Value;
            Decay(m, 500);
            Assert.IsTrue(m.Lost, "decay does not undo a loss");
            Assert.AreEqual(value, m.Value, "the meter freezes once lost");

            m.Reset();
            Assert.AreEqual(0f, m.Value);
            Assert.IsFalse(m.Lost);
            m.AddDiscovery();
            m.AddDiscovery();
            Assert.IsFalse(m.Lost, "a reset meter needs three discoveries again");
            m.AddDiscovery();
            Assert.IsTrue(m.Lost);
        }
    }

    /// <summary>docs/CONTRACT_M2.md 3.2 and 10: who hears a noise event.</summary>
    public sealed class RulesM2HearingTests
    {
        private static readonly Vector3 Source = new Vector3(1.3f, 0f, -0.7f);
        private static readonly Vector3 Diagonal = new Vector3(0.6f, 0f, 0.8f);

        [Test]
        public void Hop_radius_edge_is_inclusive()
        {
            var hop = new NoiseEvent(Source, Tuning.HopNoiseRadius, NoiseKind.Hop);
            Assert.IsTrue(Hearing.Hears(Source + Diagonal * (Tuning.HopNoiseRadius - 0.01f), hop), "just inside");
            Assert.IsTrue(Hearing.Hears(Source + Diagonal * Tuning.HopNoiseRadius, hop), "exactly on the radius");
            Assert.IsFalse(Hearing.Hears(Source + Diagonal * (Tuning.HopNoiseRadius + 0.01f), hop), "just outside");
            Assert.IsTrue(Hearing.Hears(Source, hop), "at the source");
        }

        [Test]
        public void Creak_radius_edge_is_inclusive()
        {
            var creak = new NoiseEvent(Source, Tuning.CreakRadius, NoiseKind.Creak);
            Assert.IsTrue(Hearing.Hears(Source - Diagonal * (Tuning.CreakRadius - 0.01f), creak), "just inside");
            Assert.IsTrue(Hearing.Hears(Source - Diagonal * Tuning.CreakRadius, creak), "exactly on the radius");
            Assert.IsFalse(Hearing.Hears(Source - Diagonal * (Tuning.CreakRadius + 0.01f), creak), "just outside");
            Assert.Greater(Tuning.CreakRadius, Tuning.HopNoiseRadius, "premise: a creak carries further than a hop");
            var hop = new NoiseEvent(Source, Tuning.HopNoiseRadius, NoiseKind.Hop);
            Assert.IsFalse(Hearing.Hears(Source - Diagonal * (Tuning.CreakRadius - 0.01f), hop), "the radius comes from the event");
        }

        [Test]
        public void Hearing_is_planar()
        {
            var hop = new NoiseEvent(Source, Tuning.HopNoiseRadius, NoiseKind.Hop);
            Vector3 earAbove = Source + Diagonal * (Tuning.HopNoiseRadius - 0.01f) + Vector3.up * Tuning.EyeHeight;
            Assert.Greater((earAbove - Source).magnitude, Tuning.HopNoiseRadius, "premise: out of range in 3D");
            Assert.IsTrue(Hearing.Hears(earAbove, hop), "height is ignored");
        }
    }

    /// <summary>docs/CONTRACT_M2.md 3.7: the rule switches.</summary>
    public sealed class RulesM2GameRulesTests
    {
        [Test]
        public void M1_is_all_off_and_M2_is_all_on()
        {
            GameRules m1 = GameRules.M1;
            Assert.IsFalse(m1.DisplacementMemory || m1.Hearing || m1.Creak || m1.ExitOnlyUnseen);
            GameRules m2 = GameRules.M2;
            Assert.IsTrue(m2.DisplacementMemory && m2.Hearing && m2.Creak && m2.ExitOnlyUnseen);
        }

        [Test]
        public void Each_call_returns_a_new_instance()
        {
            GameRules a = GameRules.M2;
            a.Creak = false;
            Assert.AreNotSame(a, GameRules.M2);
            Assert.IsTrue(GameRules.M2.Creak, "a test changing its copy must not change the next one");
            GameRules b = GameRules.M1;
            b.Hearing = true;
            Assert.IsFalse(GameRules.M1.Hearing);
        }
    }
}
