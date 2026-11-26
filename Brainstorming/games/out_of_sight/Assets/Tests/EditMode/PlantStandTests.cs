using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// NEWFURN (docs/next/progress/NEWFURN.md): the plant stand body ("la sellette") and its banana pot. The row (slow, heavy,
    /// not a seat), its faster creak and slower hops (BodyRules), the banana pot's height, fall and audit refusal (LoadKinds),
    /// what drops the pot on the plant stand (MotionProfile and LoadBalance), the validator's load rules, and the fallen pot's
    /// irrevocable call (SummonRule, InhabitantRoutine.BeginSummon).
    /// </summary>
    public sealed class PlantStandTests
    {
        private const float Dt = Tuning.FixedStep;
        private static readonly int Window = Mathf.RoundToInt(Tuning.LoadWindow / Dt);
        private static readonly Vector2 East = new Vector2(1f, 0f);
        private static readonly Vector2 North = new Vector2(0f, 1f);
        private static readonly Vector2 West = new Vector2(-1f, 0f);

        private static BodyDef Stand => BodyDef.For(BodyKinds.PlantStand);

        // ----- The row -----

        [Test]
        public void The_plant_stand_is_a_known_slow_heavy_body_that_is_no_seat()
        {
            BodyDef b = Stand;
            Assert.AreEqual(BodyKinds.PlantStand, b.Kind, "falls back to another body");
            Assert.IsTrue(BodyKinds.IsKnown(BodyKinds.PlantStand));
            CollectionAssert.Contains(BodyKinds.All, BodyKinds.PlantStand);
            Assert.AreEqual(new Vector3(Tuning.PlantStandWidth, Tuning.PlantStandHeight, Tuning.PlantStandWidth), b.Size);
            Assert.AreEqual(Tuning.PlantStandMaxSpeed, b.MaxSpeed, 1e-6f);
            Assert.AreEqual(Tuning.PlantStandAccel, b.Accel, 1e-6f);
            Assert.AreEqual(b.Accel, b.AccelHigh, 1e-6f, "one stage only");
            Assert.IsTrue(float.IsPositiveInfinity(b.StageSpeed));
            Assert.Less(b.MaxSpeed, BodyDef.For(BodyKinds.Chair).MaxSpeed * 0.6f, "not noticeably slower than the chair");
            Assert.IsFalse(b.IsSeat || b.Tips || b.Glides || b.HasLight || b.Rocks, "a plain heavy walker");
            Assert.IsNull(b.Model, "procedural (FurnitureKit.PlantStand)");
            Assert.IsNull(BodyKinds.DefaultModel(BodyKinds.PlantStand));
            Assert.GreaterOrEqual(b.Radius, 0.5f * b.Size.x, "the controller covers the footprint");
            Assert.AreEqual(BodyKinds.PlantStand, GripDef.For(BodyKinds.PlantStand).Kind, "its own grip");
        }

        [Test]
        public void A_cell_takes_the_plant_stand_far_longer_than_the_chair()
        {
            float stand = SecondsToTravel(Stand, 0.5f);
            float chair = SecondsToTravel(BodyDef.For(BodyKinds.Chair), 0.5f);
            Assert.Greater(stand, 1.6f * chair, $"a 0.5 m cell: {stand:0.00} s against the chair's {chair:0.00} s");
            Assert.That(stand, Is.InRange(0.7f, 0.85f), "about 0.76 s from rest");
        }

        private static float SecondsToTravel(BodyDef body, float metres)
        {
            var p = new MotionProfile(body);
            float x = 0f;
            int steps = 0;
            while (x < metres && steps < 10000)
            {
                x += p.Step(MotionWish.Toward(North)).magnitude * Dt;
                steps++;
            }
            return steps * Dt;
        }

        // ----- The creak and the hops (BodyRules) -----

        [Test]
        public void The_plant_stand_creaks_forty_percent_sooner_at_every_difficulty_and_the_others_do_not()
        {
            foreach (string id in new[] { DifficultyDef.Facile, DifficultyDef.Normal, DifficultyDef.Difficile })
            {
                float fill = DifficultyDef.For(id).CreakFillTime;
                Assert.AreEqual(fill * Tuning.PlantStandCreakFactor, BodyRules.CreakFillTime(Stand, fill), 1e-4f, id);
                Assert.Greater(BodyRules.CreakFillTime(Stand, fill), Tuning.CreakWarning, id + ": the creak needs its warning");
                foreach (string kind in BodyKinds.All)
                {
                    if (kind != BodyKinds.PlantStand)
                    {
                        Assert.AreEqual(fill, BodyRules.CreakFillTime(BodyDef.For(kind), fill), 1e-6f, kind + " changed at " + id);
                    }
                }
            }
            Assert.AreEqual(12f, BodyRules.CreakFillTime(Stand, Tuning.CreakFillTime), 1e-4f, "Normal: 12 s");
            Assert.AreEqual(Tuning.CreakWarning, BodyRules.CreakFillTime(Stand, 1f), 1e-6f, "never under the warning");
        }

        [Test]
        public void A_still_plant_stand_creaks_after_its_own_fill_time()
        {
            var gauge = new CreakGauge { FillTime = BodyRules.CreakFillTime(Stand, Tuning.CreakFillTime) };
            int steps = 0;
            float t = 0f;
            while (!gauge.Step(Dt, false, false, t) && steps < 100000)
            {
                t += Dt;
                steps++;
            }
            Assert.AreEqual(Tuning.CreakStartDelay + 12f, (steps + 1) * Dt, 2f * Dt, "the first creak");
        }

        [Test]
        public void The_plant_stand_hops_slower_and_every_other_body_keeps_the_hop_rate()
        {
            Assert.AreEqual(Tuning.PlantStandHopFrequency, BodyRules.HopFrequency(Stand), 1e-6f);
            Assert.Less(BodyRules.HopFrequency(Stand), Tuning.HopFrequency, "heavier thumps");
            foreach (string kind in BodyKinds.All)
            {
                if (kind != BodyKinds.PlantStand)
                {
                    Assert.AreEqual(Tuning.HopFrequency, BodyRules.HopFrequency(BodyDef.For(kind)), 1e-6f, kind);
                }
            }
            Assert.AreEqual(Tuning.HopFrequency, BodyRules.HopFrequency(null), 1e-6f);
        }

        // ----- The banana pot (LoadKinds) -----

        [Test]
        public void The_banana_pot_is_taller_falls_sooner_and_calls_and_the_vase_is_unchanged()
        {
            Assert.IsTrue(LoadKinds.IsKind(LoadKinds.Banana));
            Assert.AreEqual(Tuning.BananaLoadHeight, LoadKinds.HeightOf(LoadKinds.Banana), 1e-6f);
            Assert.AreEqual(Tuning.BananaFallDeltaV, LoadKinds.FallDeltaVOf(LoadKinds.Banana), 1e-6f);
            Assert.AreEqual(Tuning.BananaFallDeltaV - (Tuning.LoadFallDeltaV - Tuning.AuditLoadDeltaV), LoadKinds.AuditDeltaVOf(LoadKinds.Banana), 1e-6f);
            Assert.IsTrue(LoadKinds.CallsNearestHuman(LoadKinds.Banana));
            foreach (string kind in new[] { LoadKinds.Vase, LoadKinds.Books, LoadKinds.Plant })
            {
                Assert.AreEqual(Tuning.LoadHeight, LoadKinds.HeightOf(kind), 1e-6f, kind);
                Assert.AreEqual(Tuning.LoadFallDeltaV, LoadKinds.FallDeltaVOf(kind), 1e-6f, kind);
                Assert.AreEqual(Tuning.AuditLoadDeltaV, LoadKinds.AuditDeltaVOf(kind), 1e-6f, kind);
                Assert.IsFalse(LoadKinds.CallsNearestHuman(kind), kind + " calls someone");
            }
            Assert.AreEqual(Tuning.LoadFallDeltaV, new LoadBalance().Threshold, 1e-6f, "the default load is a vase's");
            var banana = new LoadBalance(LoadKinds.FallDeltaVOf(LoadKinds.Banana));
            banana.Step(Dt, new Vector2(0f, 0.5f));
            Assert.AreEqual(0.5f / Tuning.BananaFallDeltaV, banana.Ratio, 1e-5f, "the balance gauge reads the pot's own threshold");
        }

        [Test]
        public void The_banana_pot_rides_only_on_the_plant_stand_which_carries_nothing_else()
        {
            Assert.IsTrue(LoadKinds.Fits(LoadKinds.Banana, BodyKinds.PlantStand));
            foreach (string kind in BodyKinds.All)
            {
                if (kind != BodyKinds.PlantStand)
                {
                    Assert.IsFalse(LoadKinds.Fits(LoadKinds.Banana, kind), "a banana pot on the " + kind);
                }
            }
            Assert.IsFalse(LoadKinds.Fits(LoadKinds.Vase, BodyKinds.PlantStand), "a vase on the plant stand");
            Assert.IsTrue(LoadKinds.Fits(LoadKinds.Vase, BodyKinds.Chair));
            CollectionAssert.Contains(LevelValidator.LoadKinds, LoadKinds.Banana);

            LevelDef level = Level30();
            Assert.AreEqual(BodyKinds.PlantStand, level.PlayerBody().Kind, "premise: level30 plays the plant stand");
            Assert.AreEqual(LoadKinds.Banana, level.Player.Load, "premise: with its banana pot");
            Assert.IsEmpty(LevelValidator.Validate(level), "level30 is valid");
            level.Player.Load = LoadKinds.Vase;
            Assert.IsTrue(LevelValidator.Validate(level).Exists(i => i.Contains("carries only its banana pot")), "a vase on the plant stand passed");
            level = Level30();
            level.Player.Kind = BodyKinds.Chair;
            level.Player.SizeX = level.Player.SizeZ = 0.45f;
            level.Player.SizeY = 0.9f;
            Assert.IsTrue(LevelValidator.Validate(level).Exists(i => i.Contains("rides only on the plant stand")), "a banana pot on a chair passed");
        }

        private static LevelDef Level30() => LevelJson.Parse(File.ReadAllText(Path.Combine("Assets", "Resources", "Levels", "level30.json")));

        // ----- What drops the pot on the plant stand (MotionProfile and LoadBalance at the pot's threshold) -----

        private static int FallOf(MotionScript script)
        {
            return LoadBalance.FirstFall(MotionProfile.Synthesize(Stand, script, Dt), LoadKinds.FallDeltaVOf(LoadKinds.Banana), Dt);
        }

        private static float PeakOf(MotionScript script) => LoadBalance.PeakOf(MotionProfile.Synthesize(Stand, script, Dt));

        [Test]
        public void Straight_starts_and_stops_at_full_speed_keep_the_pot()
        {
            var script = new MotionScript().Hold(East, 1.5f).Release(0.6f).Hold(East, 0.4f).Release(0.6f);
            Assert.AreEqual(-1, FallOf(script), "a straight start or stop dropped the pot");
            Assert.Less(PeakOf(script), LoadKinds.AuditDeltaVOf(LoadKinds.Banana), "under the audit's refusal too");
        }

        [Test]
        public void A_full_speed_turn_or_reversal_drops_the_pot_and_careful_ones_keep_it()
        {
            Assert.GreaterOrEqual(FallOf(new MotionScript().Hold(East, 1f).Hold(North, 1f)), 0, "a full speed 90 deg turn kept the pot");
            Assert.GreaterOrEqual(FallOf(new MotionScript().Hold(East, 1f).Hold(West, 1f)), 0, "a full speed reversal kept the pot");
            Assert.AreEqual(-1, FallOf(new MotionScript().Hold(East, 1f, true).Hold(North, 1f, true)), "a careful 90 deg turn dropped the pot");
            Assert.AreEqual(-1, FallOf(new MotionScript().Hold(East, 1f, true).Hold(West, 1f, true)), "a careful reversal dropped the pot");
            // Braking before a corner: a stop of 0.4 s, then on at full speed, holds.
            Assert.AreEqual(-1, FallOf(new MotionScript().Hold(East, 1f).Release(0.4f).Hold(North, 1f)), "a braked corner dropped the pot");
            // The same profiles at the vase's threshold: the vase would never fall at the plant stand's speeds.
            Assert.AreEqual(-1, LoadBalance.FirstFall(MotionProfile.Synthesize(Stand, new MotionScript().Hold(East, 1f).Hold(North, 1f), Dt)),
                "premise: the vase's threshold is out of reach of the plant stand");
            Assert.Greater(Window, 0);
        }

        // ----- The irrevocable call (SummonRule, InhabitantRoutine.BeginSummon) -----

        /// <summary>A planner that plans a fixed L (x first, then z) or nothing.</summary>
        private sealed class LPlanner : IPathPlanner
        {
            public bool Fails;
            public bool StopsShort;

            public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
            {
                corners.Clear();
                if (Fails)
                {
                    return false;
                }
                corners.Add(new Vector3(to.x, 0f, from.z));
                corners.Add(StopsShort ? new Vector3(to.x, 0f, Mathf.Lerp(from.z, to.z, 0.5f)) : new Vector3(to.x, 0f, to.z));
                return true;
            }
        }

        [Test]
        public void The_walking_distance_follows_the_path_and_the_nearest_free_human_comes()
        {
            var scratch = new List<Vector3>();
            var l = new LPlanner();
            Assert.AreEqual(7f, SummonRule.WalkDistance(l, Vector3.zero, new Vector3(3f, 0f, 4f), scratch), 1e-4f, "the L's length, not the 5 m straight line");
            Assert.AreEqual(5f, SummonRule.WalkDistance(null, Vector3.zero, new Vector3(3f, 0f, 4f), scratch), 1e-4f, "no planner: the straight line");
            l.StopsShort = true;
            Assert.AreEqual(7f, SummonRule.WalkDistance(l, Vector3.zero, new Vector3(3f, 0f, 4f), scratch), 1e-4f, "a path short of the pot adds the rest");
            l.Fails = true;
            Assert.IsTrue(float.IsPositiveInfinity(SummonRule.WalkDistance(l, Vector3.zero, new Vector3(3f, 0f, 4f), scratch)), "no path at all");

            Assert.AreEqual(1, SummonRule.Nearest(new[] { 6f, 2f, 3f }, new[] { true, true, true }));
            Assert.AreEqual(2, SummonRule.Nearest(new[] { 6f, 2f, 3f }, new[] { true, false, true }), "someone busy is skipped");
            Assert.AreEqual(0, SummonRule.Nearest(new[] { 2f, 2f }, new[] { true, true }), "a tie goes to the lower index");
            Assert.AreEqual(1, SummonRule.Nearest(new[] { float.PositiveInfinity, 40f }, new[] { true, true }), "no distance limit, but a path is needed");
            Assert.AreEqual(-1, SummonRule.Nearest(new[] { 1f }, new[] { false }), "nobody free");
            Assert.AreEqual(-1, SummonRule.Nearest(new float[0], new bool[0]));
        }

        private static List<StationDef> Dwell() => new List<StationDef> { M5.Plain(0f, 0f, 0f, 60f), M5.Plain(-4f, 0f, 0f, 2f) };

        [Test]
        public void The_called_human_walks_looks_around_picks_the_pot_up_and_nothing_calls_it_off()
        {
            InhabitantRoutine r = RoutineFactory.Create(M5.DefOf(PersonalityDef.Tidy, Dwell()), null, StraightPlanner.Instance);
            r.Step(Dt);
            Assert.IsTrue(SummonRule.MayCome(r), "premise: free to come");
            var pot = new Vector3(4f, 0f, 0f);
            Assert.IsTrue(r.BeginSummon(pot), "the call was refused");
            Assert.IsTrue(r.Summoned);
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode);
            Assert.IsFalse(SummonRule.MayCome(r), "a called human is not free for another call");

            // Irrevocable: a cancel, a noise, a sighting, a lamp or another call change nothing.
            r.CancelInvestigation();
            r.Alert(new Vector3(-3f, 0f, 0f), NoiseKind.Creak);
            r.Investigate(new Vector3(0f, 0f, -3f));
            r.BeginSwitchOn(new Vector3(0f, 0f, 3f));
            Assert.IsFalse(r.BeginSummon(new Vector3(-4f, 0f, 0f)), "a second call replaced the first");
            Assert.IsTrue(r.Summoned && r.Mode == InhabitantMode.Investigating, "the call was called off");

            float leftmost = 0f;
            float rightmost = 0f;
            bool walked = false;
            int guard = 0;
            while (!r.JustPutAway)
            {
                Assert.Less(guard++, 3000, "never picked the pot up");
                r.Step(Dt);
                walked |= r.LastActivity == RoutineActivity.Walking;
                leftmost = Mathf.Min(leftmost, r.HeadYaw);
                rightmost = Mathf.Max(rightmost, r.HeadYaw);
                Assert.AreEqual(InhabitantMode.Investigating, r.Mode, "the call ended early");
                if (guard % 50 == 0)
                {
                    r.CancelInvestigation();
                }
            }
            Assert.IsTrue(walked, "it walked to the pot");
            Assert.LessOrEqual(YawMath.Planar(r.Position - pot).magnitude, Tuning.InvestigateReach + 1e-3f, "it stopped within reach of the pot");
            Assert.AreEqual(-Tuning.SummonLookYaw, leftmost, 0.5f, "it looked to one side");
            Assert.AreEqual(Tuning.SummonLookYaw, rightmost, 0.5f, "and to the other");
            Assert.AreEqual(RoutineActivity.PickingUp, r.LastActivity, "the pick up is the last beat");

            r.Step(Dt);
            Assert.IsFalse(r.Summoned, "still called after the pick up");
            Assert.AreEqual(InhabitantMode.Routine, r.Mode, "resumes its routine");
        }

        [Test]
        public void The_dog_never_comes_and_a_busy_human_is_not_free()
        {
            InhabitantRoutine dog = RoutineFactory.Create(M5.DefOf(PersonalityDef.Dog, Dwell()), null, StraightPlanner.Instance);
            dog.Step(Dt);
            Assert.IsFalse(SummonRule.MayCome(dog), "the dog is free to come");
            Assert.IsFalse(dog.BeginSummon(new Vector3(3f, 0f, 0f)), "the dog answered the call");
            Assert.IsFalse(dog.Summoned);

            InhabitantRoutine busy = RoutineFactory.Create(M5.DefOf(PersonalityDef.Granny, Dwell()), null, StraightPlanner.Instance);
            busy.Step(Dt);
            busy.Investigate(new Vector3(0f, 0f, 3f));
            Assert.IsFalse(SummonRule.MayCome(busy), "an investigating human is free to come");
            Assert.IsFalse(busy.BeginSummon(new Vector3(3f, 0f, 0f)), "the call replaced an investigation");

            InhabitantRoutine alerted = RoutineFactory.Create(M5.DefOf(PersonalityDef.Hurried, Dwell()), null, StraightPlanner.Instance);
            alerted.Step(Dt);
            alerted.Alert(new Vector3(-3f, 0f, 0f), NoiseKind.Hop);
            Assert.AreEqual(InhabitantMode.Alerted, alerted.Mode, "premise");
            Assert.IsTrue(SummonRule.MayCome(alerted), "an alerted human may come");
            Assert.IsTrue(alerted.BeginSummon(new Vector3(3f, 0f, 0f)), "an alerted human refused the call");
        }
    }
}
