using System.Collections.Generic;
using System.Text.RegularExpressions;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// docs/CONTRACT_M2.md section 10, the routine items: alert, retarget, investigate then carry then put down
    /// then resume, the telegraph invariant in every mode, the reactive pin, and M1 unchanged with
    /// StraightPlanner. Every scenario asserts its premise, so it cannot pass on nothing.
    /// </summary>
    public sealed class RoutineM2Tests
    {
        private const float Dt = Tuning.FixedStep;
        private static readonly int TelegraphSteps = Mathf.RoundToInt(Tuning.TelegraphDuration / Dt);
        private static readonly int LookSteps = Mathf.RoundToInt(Tuning.AlertLookDuration / Dt);

        // ----- Fixtures -----

        private static StationDef Station(float x, float z, float facing, float dwell, params GlanceDef[] glances)
        {
            var s = new StationDef { X = x, Z = z, Facing = facing, Dwell = dwell };
            s.Glances.AddRange(glances);
            return s;
        }

        private static GlanceDef Glance(float offset, float yaw, float hold) => new GlanceDef { Offset = offset, Yaw = yaw, Hold = hold };

        /// <summary>The stations of level 1 (a copy, so these tests do not depend on the level file).</summary>
        private static List<StationDef> Level1() => new List<StationDef>
        {
            Station(-1.5f, 2.2f, 0f, 6f, Glance(3f, -70f, 1f)),
            Station(1.2f, 1.4f, 180f, 3f, Glance(1f, 60f, 0.8f)),
            Station(0f, -2.3f, 180f, 5f),
            Station(2.2f, -0.7f, 180f, 4f, Glance(2f, -80f, 1f)),
        };

        /// <summary>Another loop, with several glances per station and a start away from station 0.</summary>
        private static List<StationDef> Varied() => new List<StationDef>
        {
            Station(0f, 0f, 90f, 4f, Glance(0.5f, 45f, 0.5f), Glance(2.5f, -60f, 0.3f)),
            Station(3f, 2f, -135f, 2f, Glance(0f, 80f, 0f)),
            Station(-2f, 3f, 10f, 1.5f),
            Station(-1f, -2.5f, 200f, 3f, Glance(1f, -35f, 1f)),
        };

        /// <summary>Two stations whose walk is an L with the L planner: along x first, then along z.</summary>
        private static List<StationDef> TwoStations() => new List<StationDef>
        {
            Station(0f, 0f, 0f, 3f),
            Station(4f, 3f, 90f, 3f),
        };

        /// <summary>A multi-corner planner: along x first, then along z.</summary>
        private sealed class LPlanner : IPathPlanner
        {
            public int Calls;
            public int Bent;

            public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
            {
                Calls++;
                corners.Clear();
                Vector3 a = YawMath.Planar(from);
                Vector3 b = YawMath.Planar(to);
                var corner = new Vector3(b.x, 0f, a.z);
                if ((corner - a).sqrMagnitude > 1e-6f && (corner - b).sqrMagnitude > 1e-6f)
                {
                    corners.Add(corner);
                    Bent++;
                }
                corners.Add(b);
                return true;
            }
        }

        private sealed class FailingPlanner : IPathPlanner
        {
            public int Calls;

            public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
            {
                Calls++;
                corners.Clear();
                return false;
            }
        }

        /// <summary>No path to one point, a straight line everywhere else.</summary>
        private sealed class BlockedPlanner : IPathPlanner
        {
            private readonly Vector3 blocked;

            public BlockedPlanner(Vector3 blocked)
            {
                this.blocked = YawMath.Planar(blocked);
            }

            public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
            {
                if ((YawMath.Planar(to) - blocked).magnitude < 1e-3f)
                {
                    corners.Clear();
                    return false;
                }
                return StraightPlanner.Instance.TryPlan(from, to, corners);
            }
        }

        // ----- Recording -----

        private struct Rec
        {
            public Vector3 Pos;
            public float Body;
            public float Head;
            public RoutineActivity Act;
            public InhabitantMode Mode;
            public bool Carrying;
            public bool PickedUp;
            public bool PutDown;
            public bool Reached;
            public bool InDwell;
            public int Station;
            public Vector3 Anchor;
            public float Eye => Body + Head;
        }

        private static Rec Snap(InhabitantRoutine r) => new Rec
        {
            Pos = r.Position,
            Body = r.BodyYaw,
            Head = r.HeadYaw,
            Act = r.LastActivity,
            Mode = r.Mode,
            Carrying = r.IsCarrying,
            PickedUp = r.JustPickedUp,
            PutDown = r.JustPutDown,
            Reached = r.ReachedTarget,
            InDwell = r.InDwell,
            Station = r.StationIndex,
            Anchor = r.CarryAnchor,
        };

        /// <summary>Steps a routine and keeps one record per fixed step (record 0 is the pose before the first step).</summary>
        private sealed class Recorder
        {
            public readonly InhabitantRoutine R;
            public readonly List<Rec> Log = new List<Rec>();

            public Recorder(InhabitantRoutine r)
            {
                R = r;
                Log.Add(Snap(r));
            }

            public Rec Last => Log[Log.Count - 1];

            public void Step(int count = 1)
            {
                for (int i = 0; i < count; i++)
                {
                    R.Step(Dt);
                    Log.Add(Snap(R));
                }
            }

            public void StepUntil(System.Func<InhabitantRoutine, bool> done, int max, string what)
            {
                int guard = 0;
                while (!done(R))
                {
                    Assert.Less(guard++, max, "never happened: " + what);
                    Step();
                }
            }

            /// <summary>Steps until the routine has been walking for <paramref name="steps"/> steps in a row.</summary>
            public void UntilWalking(int steps)
            {
                int walking = 0;
                int guard = 0;
                while (walking < steps)
                {
                    Assert.Less(guard++, 20000, "the routine never walked");
                    Step();
                    walking = R.LastActivity == RoutineActivity.Walking ? walking + 1 : 0;
                }
            }

            public List<Rec> Since(int index) => Log.GetRange(index, Log.Count - index);
        }

        private static Vector3 SourceAtEye(InhabitantRoutine r, float relativeYaw, float distance) =>
            r.Position + YawMath.Forward(r.EyeYaw + relativeYaw) * distance;

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(YawMath.Planar(to - from));

        private static bool IsTurning(RoutineActivity a) => a == RoutineActivity.TurningBody || a == RoutineActivity.TurningHead;

        private static int CountLeading(List<Rec> s, int from, RoutineActivity act)
        {
            int n = 0;
            while (from + n < s.Count && s[from + n].Act == act)
            {
                n++;
            }
            return n;
        }

        // ----- The telegraph analyzer (the M1 one of CoreTests and probe step 07, extended) -----

        /// <summary>
        /// Checks, on one record per step: yaw changes only during turns, motion only while walking or carrying,
        /// the head within its limit, and every body or head turn segment over 30 deg immediately preceded by at
        /// least 0.6 s of Telegraph records. Body and head are cut into segments separately, as the probe does.
        /// Returns the number of turns over 30 deg found. Stops at the first Startled record.
        /// </summary>
        private static int AssertTelegraphs(List<Rec> s, string context)
        {
            string violation = FindViolation(s, out int large);
            Assert.IsNull(violation, context + ": " + violation);
            return large;
        }

        /// <summary>Returns the first violation found (null when there is none) and the number of large turns.</summary>
        private static string FindViolation(List<Rec> s, out int large)
        {
            large = 0;
            for (int i = 1; i < s.Count; i++)
            {
                if (s[i].Act == RoutineActivity.Startled)
                {
                    break;
                }
                float db = Mathf.Abs(Mathf.DeltaAngle(s[i - 1].Body, s[i].Body));
                float dh = Mathf.Abs(Mathf.DeltaAngle(s[i - 1].Head, s[i].Head));
                if (db >= 1e-3f && s[i].Act != RoutineActivity.TurningBody)
                {
                    return $"body yaw changed during {s[i].Act} at record {i}";
                }
                if (dh >= 1e-3f && !IsTurning(s[i].Act))
                {
                    return $"head yaw changed during {s[i].Act} at record {i}";
                }
                if ((s[i].Pos - s[i - 1].Pos).sqrMagnitude > 1e-12f && s[i].Act != RoutineActivity.Walking && s[i].Act != RoutineActivity.Carrying)
                {
                    return $"moved during {s[i].Act} at record {i}";
                }
                if (Mathf.Abs(s[i].Head) > Tuning.HeadYawLimit + 1e-3f)
                {
                    return $"head beyond its limit at record {i}";
                }
            }
            string body = Segments(s, x => x.Body, "body", ref large);
            return body ?? Segments(s, x => x.Head, "head", ref large);
        }

        private static string Segments(List<Rec> s, System.Func<Rec, float> yaw, string label, ref int large)
        {
            int i = 1;
            while (i < s.Count && s[i].Act != RoutineActivity.Startled)
            {
                if (Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i]))) < 1e-3f)
                {
                    i++;
                    continue;
                }
                int start = i;
                float total = 0f;
                while (i < s.Count && s[i].Act != RoutineActivity.Startled && Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i]))) >= 1e-3f)
                {
                    total += Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i])));
                    i++;
                }
                if (total > Tuning.TelegraphMinTurn)
                {
                    large++;
                    int tele = 0;
                    for (int k = start - 1; k >= 0 && s[k].Act == RoutineActivity.Telegraph; k--)
                    {
                        tele++;
                    }
                    if (tele * Dt < Tuning.TelegraphDuration - 1e-3f)
                    {
                        return $"{label} turn of {total:0.0} deg at record {start} was preceded by only {tele * Dt:0.00} s of telegraph";
                    }
                }
            }
            return null;
        }

        [Test]
        public void Analyzer_premise_catches_an_untelegraphed_turn_and_motion_outside_a_walk()
        {
            // The analyzer itself must be able to fail: a 40 deg turn with only 0.58 s of telegraph before it.
            var s = new List<Rec> { new Rec { Act = RoutineActivity.Idle } };
            for (int i = 0; i < TelegraphSteps - 1; i++)
            {
                s.Add(new Rec { Act = RoutineActivity.Telegraph });
            }
            for (int i = 1; i <= 10; i++)
            {
                s.Add(new Rec { Act = RoutineActivity.TurningBody, Body = 4f * i });
            }
            StringAssert.Contains("telegraph", FindViolation(s, out _));
            s.Insert(1, new Rec { Act = RoutineActivity.Telegraph });
            Assert.IsNull(FindViolation(s, out int large));
            Assert.AreEqual(1, large);
            s.Add(new Rec { Act = RoutineActivity.Looking, Body = 40f, Pos = Vector3.right });
            StringAssert.Contains("moved during Looking", FindViolation(s, out _));
        }

        // ----- M1 unchanged with StraightPlanner -----

        [TestCase(0)]
        [TestCase(1)]
        public void StraightPlanner_routine_is_step_for_step_identical_to_M1(int set)
        {
            List<StationDef> Stations() => set == 0 ? Level1() : Varied();
            int start = set == 0 ? 0 : 2;
            var reference = new M1ReferenceRoutine(Stations(), start);
            var m1Ctor = new InhabitantRoutine(Stations(), start);
            var m2Ctor = new InhabitantRoutine(Stations(), start, StraightPlanner.Instance);
            int steps = 0;
            while (reference.LoopsCompleted < 2)
            {
                Assert.Less(steps++, 40000, "the reference routine never looped twice");
                reference.Step(Dt);
                m1Ctor.Step(Dt);
                m2Ctor.Step(Dt);
                AssertSameAsM1(reference, m1Ctor, steps, "M1 constructor");
                AssertSameAsM1(reference, m2Ctor, steps, "M2 constructor with StraightPlanner");
            }
            Assert.Greater(steps, 1000, "premise: two loops are long");
            Assert.Greater(reference.TelegraphCount, 10, "premise: the loop has telegraphs");
            Assert.AreEqual(InhabitantMode.Routine, m2Ctor.Mode);
        }

        private static void AssertSameAsM1(M1ReferenceRoutine m1, InhabitantRoutine r, int step, string who)
        {
            string at = $"{who}, step {step}";
            Assert.AreEqual(m1.Position, r.Position, at + ": position");
            Assert.AreEqual(m1.BodyYaw, r.BodyYaw, at + ": body yaw");
            Assert.AreEqual(m1.HeadYaw, r.HeadYaw, at + ": head yaw");
            Assert.AreEqual(m1.LastActivity, r.LastActivity, at + ": activity");
            Assert.AreEqual(m1.InDwell, r.InDwell, at + ": in dwell");
            Assert.AreEqual(m1.StationIndex, r.StationIndex, at + ": station");
            Assert.AreEqual(m1.LoopsCompleted, r.LoopsCompleted, at + ": loops");
            Assert.AreEqual(m1.TelegraphCount, r.TelegraphCount, at + ": telegraph count");
        }

        // ----- Alert -----

        [Test]
        public void Alert_over_30_deg_telegraphs_turns_body_and_head_together_holds_and_resumes_the_plan_exactly()
        {
            var reference = new InhabitantRoutine(Level1(), 0);
            var rec = new Recorder(new InhabitantRoutine(Level1(), 0));
            InhabitantRoutine r = rec.R;
            int walking = 0;
            int guard = 0;
            while (walking < 10)
            {
                Assert.Less(guard++, 20000, "the routine never walked");
                reference.Step(Dt);
                rec.Step();
                walking = r.LastActivity == RoutineActivity.Walking ? walking + 1 : 0;
            }
            Assert.AreEqual(reference.Position, r.Position, "premise: the two routines run in lockstep");
            Vector3 pos0 = r.Position;
            float body0 = r.BodyYaw;
            float head0 = r.HeadYaw;
            int telegraphs0 = r.TelegraphCount;
            Assert.AreEqual(0f, head0, "premise: the head is centered while walking");

            Vector3 source = SourceAtEye(r, 170f, 3f);
            r.Alert(source, NoiseKind.Hop);
            Assert.AreEqual(InhabitantMode.Alerted, r.Mode);
            Assert.AreEqual(source, r.AlertSource);
            int from = rec.Log.Count;
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the alert ended");
            List<Rec> alert = rec.Since(from);

            // 1. One full telegraph, then body and head start on the same step.
            int tele = CountLeading(alert, 0, RoutineActivity.Telegraph);
            Assert.AreEqual(TelegraphSteps, tele, "look telegraph");
            Rec before = rec.Log[from + tele - 1];
            Rec first = alert[tele];
            Assert.Greater(Mathf.Abs(Mathf.DeltaAngle(before.Body, first.Body)), 1e-3f, "the body did not start with the look turn");
            Assert.Greater(Mathf.Abs(first.Head - before.Head), 1e-3f, "the head did not start together with the body");

            // 2. The hold: exactly AlertLookDuration, the eye on the source, the head at its limit.
            int look = alert.FindIndex(x => x.Act == RoutineActivity.Looking);
            Assert.Greater(look, tele, "no hold");
            Assert.AreEqual(LookSteps, CountLeading(alert, look, RoutineActivity.Looking), "hold length");
            for (int i = look; i < look + LookSteps; i++)
            {
                Assert.AreEqual(0f, Mathf.DeltaAngle(alert[i].Eye, YawToward(pos0, source)), 1e-2f, "the eye left the source during the hold");
                Assert.AreEqual(Tuning.HeadYawLimit, alert[i].Head, 1e-3f, "the head should take its full 80 deg, the body the rest");
                Assert.AreEqual(InhabitantMode.Alerted, alert[i].Mode);
            }

            // 3. The return: a telegraph (80 deg of head, 90 of body), then back to the saved pose.
            Assert.AreEqual(TelegraphSteps, CountLeading(alert, look + LookSteps, RoutineActivity.Telegraph), "return telegraph");
            foreach (Rec x in alert)
            {
                Assert.AreEqual(pos0, x.Pos, "the inhabitant moved during the alert");
            }
            Assert.AreEqual(0f, Mathf.DeltaAngle(body0, r.BodyYaw), 1e-3f, "body not back to the saved yaw");
            Assert.AreEqual(head0, r.HeadYaw, 1e-3f, "head not back to the saved yaw");
            Assert.AreEqual(telegraphs0 + 2, r.TelegraphCount, "one telegraph for the look, one for the return");

            // 4. The saved plan resumes exactly where it stopped: the same steps as the routine never alerted.
            for (int i = 1; i <= 3000; i++)
            {
                reference.Step(Dt);
                rec.Step();
                string at = $"{i} steps after the alert";
                Assert.AreEqual(reference.Position, r.Position, at);
                Assert.AreEqual(reference.BodyYaw, r.BodyYaw, at);
                Assert.AreEqual(reference.HeadYaw, r.HeadYaw, at);
                Assert.AreEqual(reference.LastActivity, r.LastActivity, at);
                Assert.AreEqual(reference.StationIndex, r.StationIndex, at);
                Assert.AreEqual(reference.InDwell, r.InDwell, at);
            }
            Assert.GreaterOrEqual(reference.LoopsCompleted, 1, "premise: the comparison covered a loop");
            Assert.GreaterOrEqual(AssertTelegraphs(rec.Log, "alert"), 10);
        }

        [Test]
        public void Alert_of_30_deg_or_less_turns_the_head_alone_without_a_telegraph()
        {
            var rec = new Recorder(new InhabitantRoutine(Level1(), 0));
            rec.UntilWalking(10);
            InhabitantRoutine r = rec.R;
            float body0 = r.BodyYaw;
            Vector3 source = SourceAtEye(r, 20f, 3f);
            r.Alert(source, NoiseKind.Creak);
            int from = rec.Log.Count;
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the alert ended");
            List<Rec> alert = rec.Since(from);
            Assert.AreEqual(RoutineActivity.TurningHead, alert[0].Act, "a small look starts at once");
            Assert.IsFalse(alert.Exists(x => x.Act == RoutineActivity.Telegraph), "no telegraph for a 20 deg look");
            Assert.IsTrue(alert.TrueForAll(x => x.Body == body0), "the body turned for a look within the head limit");
            int look = alert.FindIndex(x => x.Act == RoutineActivity.Looking);
            Assert.AreEqual(LookSteps, CountLeading(alert, look, RoutineActivity.Looking));
            Assert.AreEqual(20f, alert[look].Head, 1e-3f);
            Assert.AreEqual(0f, r.HeadYaw, 1e-3f);
            AssertTelegraphs(rec.Log, "small alert");
        }

        [Test]
        public void Hop_is_ignored_while_alerted()
        {
            var rec = new Recorder(new InhabitantRoutine(Level1(), 0));
            rec.UntilWalking(10);
            InhabitantRoutine r = rec.R;
            Vector3 pos0 = r.Position;
            Vector3 source1 = SourceAtEye(r, 120f, 3f);
            r.Alert(source1, NoiseKind.Hop);
            int from = rec.Log.Count;
            rec.Step(10);
            Assert.AreEqual(RoutineActivity.Telegraph, rec.Last.Act, "premise: in the look telegraph");
            Vector3 source2 = SourceAtEye(r, -100f, 3f);
            r.Alert(source2, NoiseKind.Hop);
            Assert.AreEqual(source1, r.AlertSource, "a hop retargeted during the telegraph");
            rec.StepUntil(x => x.LastActivity == RoutineActivity.Looking, 500, "the hold");
            rec.Step(50);
            r.Alert(source2, NoiseKind.Hop);
            Assert.AreEqual(source1, r.AlertSource, "a hop retargeted during the hold");
            Assert.AreEqual(InhabitantMode.Alerted, r.Mode);
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the alert ended");
            List<Rec> alert = rec.Since(from);
            Assert.AreEqual(TelegraphSteps, CountLeading(alert, 0, RoutineActivity.Telegraph), "the look telegraph was disturbed");
            Assert.AreEqual(LookSteps, alert.FindAll(x => x.Act == RoutineActivity.Looking).Count, "the hold restarted on a hop");
            foreach (Rec x in alert.FindAll(x => x.Act == RoutineActivity.Looking))
            {
                Assert.AreEqual(0f, Mathf.DeltaAngle(x.Eye, YawToward(pos0, source1)), 1e-2f, "the eye followed the hop");
            }
            AssertTelegraphs(rec.Log, "hop ignored");
        }

        [Test]
        public void Creak_retargets_an_alerted_inhabitant_with_its_own_telegraph_and_a_new_hold_then_returns_to_the_first_saved_pose()
        {
            var rec = new Recorder(new InhabitantRoutine(Level1(), 0));
            rec.UntilWalking(10);
            InhabitantRoutine r = rec.R;
            Vector3 pos0 = r.Position;
            float body0 = r.BodyYaw;
            float head0 = r.HeadYaw;
            Vector3 source1 = SourceAtEye(r, 60f, 3f);
            r.Alert(source1, NoiseKind.Hop);
            rec.StepUntil(x => x.LastActivity == RoutineActivity.Looking, 500, "the first hold");
            rec.Step(50);
            Assert.AreEqual(RoutineActivity.Looking, rec.Last.Act, "premise: in the hold");
            Vector3 source2 = pos0 + YawMath.Forward(body0 - 120f) * 3f;
            r.Alert(source2, NoiseKind.Creak);
            Assert.AreEqual(source2, r.AlertSource, "a creak must retarget");
            int from = rec.Log.Count;
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the alert ended");
            List<Rec> after = rec.Since(from);
            Assert.AreEqual(TelegraphSteps, CountLeading(after, 0, RoutineActivity.Telegraph), "the retarget turn has its own telegraph");
            Assert.IsTrue(IsTurning(after[TelegraphSteps].Act), "the retarget turn follows its telegraph");
            int look = after.FindIndex(x => x.Act == RoutineActivity.Looking);
            Assert.AreEqual(LookSteps, CountLeading(after, look, RoutineActivity.Looking), "the hold restarts in full");
            Assert.AreEqual(0f, Mathf.DeltaAngle(after[look].Eye, YawToward(pos0, source2)), 1e-2f, "the eye is not on the creak");
            Assert.AreEqual(0f, Mathf.DeltaAngle(body0, r.BodyYaw), 1e-3f, "not back to the pose saved by the first alert");
            Assert.AreEqual(head0, r.HeadYaw, 1e-3f);
            Assert.AreEqual(pos0, r.Position);
            AssertTelegraphs(rec.Log, "creak retarget");
        }

        [Test]
        public void Creak_during_the_look_telegraph_only_moves_the_target()
        {
            var rec = new Recorder(new InhabitantRoutine(Level1(), 0));
            rec.UntilWalking(10);
            InhabitantRoutine r = rec.R;
            Vector3 pos0 = r.Position;
            r.Alert(SourceAtEye(r, 120f, 3f), NoiseKind.Hop);
            int from = rec.Log.Count;
            int telegraphs = r.TelegraphCount;
            rec.Step(10);
            Assert.AreEqual(RoutineActivity.Telegraph, rec.Last.Act, "premise: in the look telegraph");
            Vector3 source2 = SourceAtEye(r, -90f, 4f);
            r.Alert(source2, NoiseKind.Creak);
            rec.StepUntil(x => x.LastActivity == RoutineActivity.Looking, 500, "the hold");
            List<Rec> alert = rec.Since(from);
            Assert.AreEqual(TelegraphSteps, CountLeading(alert, 0, RoutineActivity.Telegraph), "the telegraph was restarted or cut");
            Assert.AreEqual(telegraphs + 1, r.TelegraphCount, "a second telegraph was started");
            Assert.AreEqual(0f, Mathf.DeltaAngle(rec.Last.Eye, YawToward(pos0, source2)), 1e-2f, "the look does not aim at the creak");
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the alert ended");
            AssertTelegraphs(rec.Log, "creak during telegraph");
        }

        [Test]
        public void Creak_that_makes_an_untelegraphed_look_turn_large_stops_it_for_a_telegraph()
        {
            var rec = new Recorder(new InhabitantRoutine(Level1(), 0));
            rec.UntilWalking(10);
            InhabitantRoutine r = rec.R;
            Vector3 pos0 = r.Position;
            r.Alert(SourceAtEye(r, 25f, 3f), NoiseKind.Hop);
            int from = rec.Log.Count;
            rec.Step(3);
            Assert.IsTrue(rec.Since(from).TrueForAll(x => x.Act == RoutineActivity.TurningHead), "premise: a small look turns at once");
            Vector3 source2 = SourceAtEye(r, -140f, 3f);
            r.Alert(source2, NoiseKind.Creak);
            rec.Step();
            Assert.AreEqual(RoutineActivity.Telegraph, rec.Last.Act, "the turn grew past 30 deg without a telegraph");
            rec.StepUntil(x => x.LastActivity == RoutineActivity.Looking, 500, "the hold");
            Assert.AreEqual(0f, Mathf.DeltaAngle(rec.Last.Eye, YawToward(pos0, source2)), 1e-2f);
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the alert ended");
            AssertTelegraphs(rec.Log, "grown look");
        }

        [Test]
        public void Alert_during_a_telegraph_restarts_that_telegraph_in_full_on_resume()
        {
            var rec = new Recorder(new InhabitantRoutine(Level1(), 0));
            InhabitantRoutine r = rec.R;
            int run = 0;
            int guard = 0;
            while (run < 10)
            {
                Assert.Less(guard++, 20000);
                rec.Step();
                run = r.LastActivity == RoutineActivity.Telegraph ? run + 1 : 0;
            }
            // A 20 deg look: no telegraph of its own, so the one that follows is the restarted one.
            r.Alert(SourceAtEye(r, 20f, 3f), NoiseKind.Hop);
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the alert ended");
            int resume = rec.Log.Count;
            int telegraphs = r.TelegraphCount;
            rec.Step(TelegraphSteps + 1);
            List<Rec> after = rec.Since(resume);
            Assert.AreEqual(TelegraphSteps, CountLeading(after, 0, RoutineActivity.Telegraph), "the interrupted telegraph did not restart in full");
            Assert.IsTrue(IsTurning(after[TelegraphSteps].Act), "the turn did not follow the restarted telegraph");
            Assert.AreEqual(telegraphs + 1, r.TelegraphCount);
            AssertTelegraphs(rec.Log, "telegraph interrupted");
        }

        [TestCase(3, true)]
        [TestCase(26, false)]
        public void Alert_during_a_turn_gives_the_rest_a_fresh_telegraph_only_when_over_30_deg(int turnSteps, bool expectTelegraph)
        {
            // The departure from station 0 of level 1 is a 106.5 deg body turn (3.6 deg per step).
            var reference = new InhabitantRoutine(Level1(), 0);
            var rec = new Recorder(new InhabitantRoutine(Level1(), 0));
            InhabitantRoutine r = rec.R;
            int run = 0;
            int guard = 0;
            while (run < turnSteps)
            {
                Assert.Less(guard++, 20000);
                reference.Step(Dt);
                rec.Step();
                run = r.LastActivity == RoutineActivity.TurningBody ? run + 1 : 0;
            }
            while (reference.LastActivity != RoutineActivity.Walking)
            {
                reference.Step(Dt);
            }
            float finalYaw = reference.BodyYaw;
            float left = Mathf.Abs(Mathf.DeltaAngle(r.BodyYaw, finalYaw));
            Assert.AreEqual(expectTelegraph, left > Tuning.TelegraphMinTurn, $"premise: {left:0.0} deg left");

            r.Alert(SourceAtEye(r, 20f, 3f), NoiseKind.Hop);
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the alert ended");
            int resume = rec.Log.Count;
            rec.StepUntil(x => x.LastActivity == RoutineActivity.Walking, 500, "the walk");
            List<Rec> after = rec.Since(resume);
            int tele = CountLeading(after, 0, RoutineActivity.Telegraph);
            Assert.AreEqual(expectTelegraph ? TelegraphSteps : 0, tele, "telegraph before the rest of the turn");
            Assert.AreEqual(RoutineActivity.TurningBody, after[tele].Act);
            Assert.AreEqual(0f, Mathf.DeltaAngle(finalYaw, r.BodyYaw), 1e-3f, "the resumed turn does not end where the plan said");
            AssertTelegraphs(rec.Log, "turn interrupted");
        }

        // ----- Investigate, carry, put down, resume -----

        [Test]
        public void Investigate_then_carry_then_put_down_then_resume_in_order_along_planner_corners()
        {
            var planner = new LPlanner();
            var rec = new Recorder(new InhabitantRoutine(TwoStations(), 0, planner));
            InhabitantRoutine r = rec.R;
            rec.UntilWalking(20);
            Assert.AreEqual(0, r.StationIndex, "premise: walking from station 0 to station 1");
            Assert.Greater(planner.Bent, 0, "premise: the station walk is an L");

            // An alert is in progress (head at its limit) when the displaced furniture is seen.
            r.Alert(SourceAtEye(r, 150f, 3f), NoiseKind.Hop);
            rec.StepUntil(x => x.LastActivity == RoutineActivity.Looking, 500, "the hold");
            rec.Step(20);
            Assert.AreEqual(Tuning.HeadYawLimit, r.HeadYaw, 1e-3f, "premise: the head is turned");

            var target = new Vector3(-2f, 0f, 2.5f);
            var corner = new Vector3(-2f, 0f, r.Position.z);
            int bentBefore = planner.Bent;
            int investigate = rec.Log.Count;
            r.Investigate(target);
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode);
            Assert.IsFalse(r.ReachedTarget);
            Assert.AreEqual(bentBefore + 1, planner.Bent, "the investigation was not planned with the planner");
            r.Alert(SourceAtEye(r, 90f, 2f), NoiseKind.Creak);
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode, "an investigating inhabitant must ignore noise");
            rec.StepUntil(x => x.ReachedTarget, 3000, "the target");
            List<Rec> walk = rec.Since(investigate);

            // The head comes back to 0 together with the first telegraphed turn, before any step of walking.
            int tele = CountLeading(walk, 0, RoutineActivity.Telegraph);
            Assert.AreEqual(TelegraphSteps, tele, "the first beat of the investigation");
            Rec beat = walk[tele];
            Rec beforeBeat = rec.Log[investigate + tele - 1];
            Assert.Greater(Mathf.Abs(Mathf.DeltaAngle(beforeBeat.Body, beat.Body)), 1e-3f, "the body did not turn in the first beat");
            Assert.Greater(Mathf.Abs(beat.Head - beforeBeat.Head), 1e-3f, "the head did not come back in the first beat");
            int firstWalk = walk.FindIndex(x => x.Act == RoutineActivity.Walking);
            Assert.Greater(firstWalk, tele);
            Assert.IsTrue(walk.GetRange(firstWalk, walk.Count - firstWalk).TrueForAll(x => x.Head == 0f), "walked with the head turned");
            Assert.IsTrue(walk.Exists(x => (x.Pos - corner).sqrMagnitude < 1e-8f), "the walk did not follow the planner corner");
            float distance = YawMath.Planar(target - r.Position).magnitude;
            Assert.LessOrEqual(distance, Tuning.InvestigateReach + 1e-4f, "stopped out of reach");
            Assert.Greater(distance, Tuning.InvestigateReach - Tuning.WalkSpeed * Dt - 1e-4f, "did not stop as soon as within reach");
            Assert.AreEqual(0f, Mathf.DeltaAngle(r.BodyYaw, YawToward(r.Position, target)), 1e-2f, "not facing the target");
            Vector3 reachedAt = r.Position;
            rec.Step(10);
            Assert.AreEqual(reachedAt, r.Position, "the routine must idle once the target is reached");
            Assert.AreEqual(RoutineActivity.Idle, r.LastActivity);
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode);

            // Carry back.
            var home = new FurniturePose(new Vector3(3f, 0f, -1.5f), 45f);
            int carry = rec.Log.Count;
            r.BeginCarry(home);
            Assert.AreEqual(InhabitantMode.Carrying, r.Mode);
            Assert.IsTrue(r.IsCarrying, "IsCarrying is true from the start of the pick up");
            Assert.AreEqual(home.Position, r.CarryReturnPose.Position);
            Assert.AreEqual(home.Yaw, r.CarryReturnPose.Yaw);
            r.Alert(SourceAtEye(r, 90f, 2f), NoiseKind.Creak);
            Assert.AreEqual(InhabitantMode.Carrying, r.Mode, "a carrying inhabitant must ignore noise");
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 5000, "the end of the carry");
            // c[0] is the record before BeginCarry, c[1] the first step of the carry.
            List<Rec> c = rec.Since(carry - 1);

            int pickUp = c.FindIndex(x => x.Act == RoutineActivity.PickingUp);
            int carried = c.FindIndex(x => x.Act == RoutineActivity.Carrying);
            int putDown = c.FindIndex(x => x.Act == RoutineActivity.PuttingDown);
            int putDownEnd = c.FindIndex(x => x.PutDown);
            int resumed = c.FindIndex(x => x.Mode == InhabitantMode.Routine);
            Assert.AreEqual(1, pickUp, "the pick up starts on the first step");
            Assert.Less(pickUp, carried, "pick up, then carry");
            Assert.Less(carried, putDown, "carry, then put down");
            Assert.Less(putDown, putDownEnd);
            Assert.AreEqual(putDownEnd + 1, resumed, "the routine resumes on the step after the put down");
            Assert.AreEqual(Mathf.RoundToInt(Tuning.PickUpDuration / Dt), CountLeading(c, pickUp, RoutineActivity.PickingUp), "pick up length");
            Assert.AreEqual(Mathf.RoundToInt(Tuning.PutDownDuration / Dt), CountLeading(c, putDown, RoutineActivity.PuttingDown), "put down length");
            Assert.AreEqual(putDown + CountLeading(c, putDown, RoutineActivity.PuttingDown) - 1, putDownEnd, "JustPutDown is not on the last put down step");
            Assert.AreEqual(1, c.FindAll(x => x.PickedUp).Count, "JustPickedUp must be true on exactly one step");
            Assert.IsTrue(c[pickUp].PickedUp, "JustPickedUp is not on the first pick up step");
            Assert.AreEqual(1, c.FindAll(x => x.PutDown).Count, "JustPutDown must be true on exactly one step");
            for (int i = 1; i < putDownEnd; i++)
            {
                Assert.IsTrue(c[i].Carrying, $"IsCarrying dropped before the put down ended (record {i})");
                Assert.AreEqual(InhabitantMode.Carrying, c[i].Mode);
            }
            Assert.IsFalse(c[putDownEnd].Carrying, "IsCarrying must be false on the step the put down ends");
            Assert.AreEqual(InhabitantMode.Carrying, c[putDownEnd].Mode, "the put down step is still part of the carry");
            int fullSpeed = 0;
            for (int i = 1; i < c.Count; i++)
            {
                float stepLength = (c[i].Pos - c[i - 1].Pos).magnitude;
                if (c[i].Act == RoutineActivity.Carrying)
                {
                    Assert.LessOrEqual(stepLength, Tuning.CarrySpeed * Dt + 1e-5f, "faster than CarrySpeed");
                    fullSpeed += Mathf.Abs(stepLength - Tuning.CarrySpeed * Dt) < 1e-5f ? 1 : 0;
                }
            }
            Assert.Greater(fullSpeed, 50, "the carry did not walk at CarrySpeed");
            Rec end = c[putDownEnd];
            Assert.That(YawMath.Planar(end.Anchor - home.Position).magnitude, Is.LessThan(0.02f), "the held furniture does not arrive on its return position");
            Assert.AreEqual(Tuning.CarryHeight, end.Anchor.y, 1e-4f);

            // Resume: the alert had interrupted the walk to station 1, so the routine goes there and dwells.
            rec.StepUntil(x => x.InDwell, 5000, "the next dwell");
            Assert.AreEqual(1, r.StationIndex, "resumed at the wrong station");
            Assert.That((r.Position - TwoStations()[1].Position).magnitude, Is.LessThan(1e-4f));
            Assert.AreEqual(0f, Mathf.DeltaAngle(90f, r.BodyYaw), 1e-3f, "no arrival turn");
            Assert.GreaterOrEqual(AssertTelegraphs(rec.Log, "investigate and carry"), 8);
        }

        [Test]
        public void Investigation_without_a_path_reaches_at_once_and_cancels_into_the_routine()
        {
            var target = new Vector3(1f, 0f, 1f);
            var rec = new Recorder(new InhabitantRoutine(Level1(), 0, new BlockedPlanner(target)));
            InhabitantRoutine r = rec.R;
            rec.Step(100);
            Vector3 here = r.Position;
            r.Investigate(target);
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode);
            Assert.IsTrue(r.ReachedTarget, "no path: the investigation must stop at once");
            rec.Step(50);
            Assert.AreEqual(here, r.Position);
            Assert.AreEqual(RoutineActivity.Idle, r.LastActivity);
            r.CancelInvestigation();
            Assert.AreEqual(InhabitantMode.Routine, r.Mode);
            Assert.IsFalse(r.ReachedTarget);
            rec.StepUntil(x => x.LoopsCompleted >= 1, 20000, "a loop after the cancel");
            AssertTelegraphs(rec.Log, "no path");
        }

        [Test]
        public void Station_walks_follow_the_planner_corners_with_a_telegraphed_turn_per_large_corner()
        {
            var planner = new LPlanner();
            List<StationDef> stations = TwoStations();
            var rec = new Recorder(new InhabitantRoutine(stations, 0, planner));
            rec.StepUntil(x => x.InDwell && x.StationIndex == 1, 5000, "the arrival at station 1");
            Assert.Greater(planner.Bent, 0, "premise: the planner gave an L");
            var corner = new Vector3(4f, 0f, 0f);
            List<Rec> walk = rec.Log.FindAll(x => x.Act == RoutineActivity.Walking);
            Assert.Greater(walk.Count, 200, "premise: the walk happened");
            foreach (Rec x in walk)
            {
                Assert.IsTrue(Mathf.Abs(x.Pos.z) < 1e-5f || Mathf.Abs(x.Pos.x - 4f) < 1e-5f, $"off the planner path at {x.Pos}");
            }
            Assert.IsTrue(rec.Log.Exists(x => (x.Pos - corner).sqrMagnitude < 1e-8f), "the walk cut the corner");
            // Departure, corner and arrival are three 90 deg body turns, each right after a full telegraph.
            Assert.AreEqual(3, AssertTelegraphs(rec.Log, "L walk"));
            Assert.That((rec.R.Position - stations[1].Position).magnitude, Is.LessThan(1e-4f));
        }

        [Test]
        public void Station_walk_without_a_path_falls_back_to_a_straight_line_and_logs_an_error()
        {
            LogAssert.Expect(LogType.Error, new Regex(@"no path from .* to station 1 "));
            LogAssert.Expect(LogType.Error, new Regex(@"no path from .* to station 0 "));
            var planner = new FailingPlanner();
            List<StationDef> stations = TwoStations();
            var rec = new Recorder(new InhabitantRoutine(stations, 0, planner));
            rec.StepUntil(x => x.InDwell && x.StationIndex == 1, 5000, "the arrival at station 1");
            Assert.AreEqual(2, planner.Calls, "one planning per station walk");
            Assert.That((rec.R.Position - stations[1].Position).magnitude, Is.LessThan(1e-4f));
            Vector3 a = stations[0].Position;
            Vector3 dir = (stations[1].Position - a).normalized;
            int walking = 0;
            foreach (Rec x in rec.Log.FindAll(x => x.Act == RoutineActivity.Walking))
            {
                Vector3 off = x.Pos - a;
                Assert.Less((off - dir * Vector3.Dot(off, dir)).magnitude, 1e-4f, "the fallback walk is not straight");
                walking++;
            }
            Assert.Greater(walking, 100, "premise: the walk happened");
            LogAssert.NoUnexpectedReceived();
        }

        [Test]
        public void Cancelled_investigation_of_a_dwell_replays_that_dwell_in_full_without_counting_a_loop()
        {
            List<StationDef> stations = Level1();
            var rec = new Recorder(new InhabitantRoutine(stations, 0));
            InhabitantRoutine r = rec.R;
            rec.StepUntil(x => x.LoopsCompleted == 1, 20000, "one loop");
            rec.Step(20);
            Assert.IsTrue(r.InDwell && r.StationIndex == 0, "premise: dwelling at station 0");
            r.Investigate(new Vector3(0.5f, 0f, 2.2f));
            Assert.IsFalse(r.InDwell, "an investigation is not a dwell");
            rec.StepUntil(x => x.ReachedTarget, 3000, "the target");
            Assert.That((r.Position - stations[0].Position).magnitude, Is.GreaterThan(1f), "premise: it walked away from the station");
            r.CancelInvestigation();
            rec.StepUntil(x => x.InDwell, 3000, "the dwell again");
            Assert.AreEqual(0, r.StationIndex);
            Assert.That((r.Position - stations[0].Position).magnitude, Is.LessThan(1e-4f));
            Assert.AreEqual(0f, Mathf.DeltaAngle(stations[0].Facing, r.BodyYaw), 1e-3f, "no arrival turn");
            Assert.AreEqual(1, r.LoopsCompleted, "the replayed dwell counted as a new loop");
            int dwell = rec.Log.Count - 1;
            rec.StepUntil(x => !x.InDwell, 3000, "the end of the dwell");
            List<Rec> d = rec.Log.GetRange(dwell, rec.Log.Count - 1 - dwell);
            Assert.GreaterOrEqual(d.Count, Mathf.RoundToInt(stations[0].Dwell / Dt), "the dwell was not replayed in full");
            Assert.IsTrue(d.Exists(x => Mathf.Abs(x.Head + 70f) < 1e-3f), "the glance was not replayed");
            rec.StepUntil(x => x.LoopsCompleted == 2, 20000, "the next loop");
            AssertTelegraphs(rec.Log, "dwell resume");
        }

        [Test]
        public void Cancelled_investigation_of_a_walk_goes_on_to_the_station_it_was_walking_to()
        {
            List<StationDef> stations = Level1();
            var rec = new Recorder(new InhabitantRoutine(stations, 0, new LPlanner()));
            InhabitantRoutine r = rec.R;
            rec.UntilWalking(10);
            Assert.AreEqual(0, r.StationIndex, "premise: walking from station 0 to station 1");
            r.Investigate(r.Position + YawMath.Forward(r.BodyYaw - 90f) * 2f);
            rec.StepUntil(x => x.ReachedTarget, 3000, "the target");
            r.CancelInvestigation();
            rec.StepUntil(x => x.InDwell, 3000, "the next dwell");
            Assert.AreEqual(1, r.StationIndex);
            Assert.That((r.Position - stations[1].Position).magnitude, Is.LessThan(1e-4f));
            Assert.AreEqual(0f, Mathf.DeltaAngle(stations[1].Facing, r.BodyYaw), 1e-3f);
            AssertTelegraphs(rec.Log, "walk resume");
        }

        // ----- Pins and startle -----

        [Test]
        public void Reactive_pin_holds_reacts_and_returns_to_its_pose()
        {
            var r = new InhabitantRoutine(Level1(), 0, new LPlanner());
            var pin = new Vector3(1f, 0f, 1f);
            r.Pin(pin, 90f, 10f, true);
            Assert.IsTrue(r.IsPinned);
            Assert.IsFalse(r.IsFrozen);
            Assert.AreEqual(InhabitantMode.Routine, r.Mode);
            var rec = new Recorder(r);

            rec.Step(100);
            AssertHoldsPin(rec, pin, "before any reaction");

            r.Alert(SourceAtEye(r, 150f, 2f), NoiseKind.Hop);
            Assert.AreEqual(InhabitantMode.Alerted, r.Mode, "a reactive pin accepts Alert");
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the alert ended");
            Assert.IsTrue(rec.Log.Exists(x => x.Act == RoutineActivity.Looking), "premise: it looked");
            rec.Step(50);
            AssertHoldsPin(rec, pin, "after the alert");

            r.Investigate(new Vector3(3.5f, 0f, 3f));
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode, "a reactive pin accepts Investigate");
            rec.StepUntil(x => x.ReachedTarget, 3000, "the target");
            Assert.That((r.Position - pin).magnitude, Is.GreaterThan(1f), "premise: it walked away");
            r.BeginCarry(new FurniturePose(new Vector3(2f, 0f, -1.5f), 0f));
            rec.StepUntil(x => x.LastActivity == RoutineActivity.Pinned, 6000, "back on the pin after the carry");
            Assert.IsTrue(rec.Log.Exists(x => x.PutDown), "premise: it carried");
            rec.Step(100);
            AssertHoldsPin(rec, pin, "after the carry");

            r.Investigate(new Vector3(-1.5f, 0f, 2.5f));
            rec.StepUntil(x => x.ReachedTarget, 3000, "the second target");
            r.CancelInvestigation();
            rec.StepUntil(x => x.LastActivity == RoutineActivity.Pinned, 6000, "back on the pin after the cancel");
            rec.Step(100);
            AssertHoldsPin(rec, pin, "after the cancel");
            Assert.GreaterOrEqual(AssertTelegraphs(rec.Log, "reactive pin"), 6);
        }

        private static void AssertHoldsPin(Recorder rec, Vector3 pin, string when)
        {
            InhabitantRoutine r = rec.R;
            Assert.That((r.Position - pin).magnitude, Is.LessThan(1e-4f), when + ": position");
            Assert.AreEqual(0f, Mathf.DeltaAngle(90f, r.BodyYaw), 1e-3f, when + ": body yaw");
            Assert.AreEqual(10f, r.HeadYaw, 1e-3f, when + ": head yaw");
            Assert.AreEqual(RoutineActivity.Pinned, r.LastActivity, when + ": not holding");
            Assert.AreEqual(InhabitantMode.Routine, r.Mode, when);
            Rec previous = rec.Log[rec.Log.Count - 2];
            Assert.AreEqual(previous.Pos, r.Position, when + ": still moving");
            Assert.AreEqual(previous.Body, r.BodyYaw, when + ": still turning");
        }

        [Test]
        public void Frozen_pin_ignores_noise_and_investigation()
        {
            var r = new InhabitantRoutine(Level1(), 0);
            var at = new Vector3(0.5f, 0f, -0.5f);
            r.Pin(at, 45f, 0f);
            Assert.IsTrue(r.IsFrozen);
            Assert.IsTrue(r.IsPinned);
            r.Alert(at + Vector3.right, NoiseKind.Creak);
            Assert.AreEqual(InhabitantMode.Routine, r.Mode, "a frozen pin heard a creak");
            r.Investigate(at + Vector3.forward * 3f);
            Assert.AreEqual(InhabitantMode.Routine, r.Mode, "a frozen pin investigated");
            r.BeginCarry(new FurniturePose(at, 0f));
            Assert.IsFalse(r.IsCarrying);
            for (int i = 0; i < 200; i++)
            {
                r.Step(Dt);
                Assert.AreEqual(RoutineActivity.Pinned, r.LastActivity);
            }
            Assert.AreEqual(at, r.Position);
            Assert.AreEqual(45f, r.BodyYaw);
            Assert.AreEqual(0f, r.HeadYaw);
        }

        [Test]
        public void Pin_cancels_an_alert_an_investigation_and_a_carry()
        {
            var r = new InhabitantRoutine(Level1(), 0, new LPlanner());
            var rec = new Recorder(r);
            rec.UntilWalking(10);
            r.Alert(SourceAtEye(r, 150f, 2f), NoiseKind.Hop);
            rec.Step(40);
            Assert.AreEqual(InhabitantMode.Alerted, r.Mode, "premise: alerted");
            var pin = new Vector3(1f, 0f, 1f);
            r.Pin(pin, 90f, 10f, true);
            Assert.AreEqual(InhabitantMode.Routine, r.Mode, "Pin did not cancel the alert");
            rec.Step(60);
            AssertHoldsPin(rec, pin, "pin over an alert");

            r.Investigate(new Vector3(3.5f, 0f, 3f));
            rec.Step(40);
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode, "premise: investigating");
            r.Pin(pin, 90f, 10f, true);
            Assert.AreEqual(InhabitantMode.Routine, r.Mode, "Pin did not cancel the investigation");
            Assert.IsFalse(r.ReachedTarget);
            rec.Step(60);
            AssertHoldsPin(rec, pin, "pin over an investigation");

            // A new investigation right after a re-pin (probe step 21 does this three times).
            r.Investigate(new Vector3(3.5f, 0f, 3f));
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode, "a re-pinned inhabitant must investigate again");
            rec.StepUntil(x => x.ReachedTarget, 3000, "the target");
            r.BeginCarry(new FurniturePose(new Vector3(2f, 0f, -1.5f), 0f));
            rec.Step(40);
            Assert.IsTrue(r.IsCarrying, "premise: carrying");
            r.Pin(pin, 90f, 10f, true);
            Assert.IsFalse(r.IsCarrying, "Pin did not cancel the carry");
            Assert.AreEqual(InhabitantMode.Routine, r.Mode);
            int from = rec.Log.Count;
            rec.Step(60);
            Assert.IsFalse(rec.Since(from).Exists(x => x.PutDown || x.Carrying), "a cancelled carry still put down");
            AssertHoldsPin(rec, pin, "pin over a carry");
        }

        [Test]
        public void Startle_cancels_a_carry_and_ignores_everything_after()
        {
            var r = new InhabitantRoutine(Level1(), 0);
            var rec = new Recorder(r);
            rec.UntilWalking(10);
            r.Investigate(r.Position + YawMath.Forward(r.BodyYaw + 90f) * 2f);
            rec.StepUntil(x => x.ReachedTarget, 3000, "the target");
            r.BeginCarry(new FurniturePose(new Vector3(-1f, 0f, -1f), 0f));
            rec.Step(40);
            Assert.IsTrue(r.IsCarrying, "premise: carrying");
            Vector3 target = r.Position + YawMath.Forward(r.BodyYaw + 120f) * 3f;
            r.Startle(target);
            Assert.AreEqual(InhabitantMode.Startled, r.Mode);
            Assert.IsFalse(r.IsCarrying, "a startle must cancel the carry");
            r.Alert(target, NoiseKind.Creak);
            r.Investigate(target);
            r.CancelInvestigation();
            Assert.AreEqual(InhabitantMode.Startled, r.Mode, "a startled inhabitant reacted");
            Vector3 here = r.Position;
            rec.Step(100);
            Assert.AreEqual(here, r.Position, "a startled inhabitant moved");
            Assert.AreEqual(RoutineActivity.Startled, r.LastActivity);
            Assert.AreEqual(0f, Mathf.DeltaAngle(r.BodyYaw, YawToward(here, target)), 1e-2f, "not facing what startled it");
            AssertTelegraphs(rec.Log, "startle");
        }

        // ----- The invariant in every mode -----

        [Test]
        public void Every_turn_over_30_deg_is_telegraphed_in_every_mode()
        {
            int large = 0;
            int alertsInTelegraph = 0;
            int alertsInTurn = 0;
            int retargets = 0;
            int ignoredHops = 0;
            int carries = 0;
            int cancels = 0;
            int reactivePins = 0;
            var modes = new HashSet<InhabitantMode>();
            for (int seed = 1; seed <= 16; seed++)
            {
                var rng = new System.Random(seed);
                IPathPlanner planner = seed % 2 == 0 ? (IPathPlanner)StraightPlanner.Instance : new LPlanner();
                var r = new InhabitantRoutine(Level1(), seed % 4, planner);
                if (seed % 4 == 3)
                {
                    r.Pin(new Vector3(0.5f, 0f, 0.5f), (float)(rng.NextDouble() * 360.0 - 180.0), 20f, true);
                    reactivePins++;
                }
                var rec = new Recorder(r);
                int begun = 0;
                int picked = 0;
                int putDowns = 0;
                for (int step = 0; step < 12000; step++)
                {
                    rec.Step();
                    bool inject = step < 9000;
                    picked += r.JustPickedUp ? 1 : 0;
                    if (r.JustPutDown)
                    {
                        putDowns++;
                        Assert.IsTrue(rec.Log[rec.Log.Count - 2].Carrying, $"seed {seed}: put down without a carry");
                    }
                    Assert.AreEqual(r.Mode == InhabitantMode.Carrying && !r.JustPutDown, r.IsCarrying, $"seed {seed}: IsCarrying out of the carry");
                    modes.Add(r.Mode);
                    if (r.Mode == InhabitantMode.Investigating && r.ReachedTarget)
                    {
                        if (inject && rng.NextDouble() < 0.6)
                        {
                            r.BeginCarry(new FurniturePose(RandomPoint(rng, r.Position, 1f, 4f), (float)(rng.NextDouble() * 360.0)));
                            begun++;
                        }
                        else
                        {
                            r.CancelInvestigation();
                            cancels++;
                        }
                    }
                    if (!inject)
                    {
                        continue;
                    }
                    double p = rng.NextDouble();
                    if (p < 0.008)
                    {
                        NoiseKind kind = rng.NextDouble() < 0.5 ? NoiseKind.Hop : NoiseKind.Creak;
                        InhabitantMode before = r.Mode;
                        Vector3 previousSource = r.AlertSource;
                        RoutineActivity activity = r.LastActivity;
                        Vector3 source = RandomPoint(rng, r.Position, 0.5f, 6f);
                        r.Alert(source, kind);
                        if (before == InhabitantMode.Routine)
                        {
                            Assert.AreEqual(InhabitantMode.Alerted, r.Mode, $"seed {seed}: an alert was refused in Routine");
                            alertsInTelegraph += activity == RoutineActivity.Telegraph ? 1 : 0;
                            alertsInTurn += IsTurning(activity) ? 1 : 0;
                        }
                        else if (before == InhabitantMode.Alerted)
                        {
                            Assert.AreEqual(kind == NoiseKind.Hop ? previousSource : source, r.AlertSource, $"seed {seed}: {kind} while alerted");
                            retargets += kind == NoiseKind.Creak ? 1 : 0;
                            ignoredHops += kind == NoiseKind.Hop ? 1 : 0;
                        }
                        else
                        {
                            Assert.AreEqual(before, r.Mode, $"seed {seed}: noise changed the mode of a busy inhabitant");
                        }
                    }
                    else if (p < 0.011 && (r.Mode == InhabitantMode.Routine || r.Mode == InhabitantMode.Alerted))
                    {
                        r.Investigate(RandomPoint(rng, r.Position, 0.3f, 5f));
                        Assert.AreEqual(InhabitantMode.Investigating, r.Mode, $"seed {seed}: Investigate refused");
                    }
                }
                Assert.AreEqual(InhabitantMode.Routine, r.Mode, $"seed {seed}: never settled back into the routine");
                Assert.AreEqual(begun, picked, $"seed {seed}: JustPickedUp is not one step per carry");
                Assert.AreEqual(begun, putDowns, $"seed {seed}: JustPutDown is not one step per carry");
                carries += begun;
                large += AssertTelegraphs(rec.Log, $"seed {seed}");
            }
            // Premises: the scenarios covered what they claim to cover.
            Assert.Greater(large, 300, "too few large turns: the check would pass on nothing");
            Assert.Greater(alertsInTelegraph, 0, "no alert ever interrupted a telegraph");
            Assert.Greater(alertsInTurn, 0, "no alert ever interrupted a turn");
            Assert.Greater(retargets, 5, "too few creak retargets");
            Assert.Greater(ignoredHops, 5, "too few hops while alerted");
            Assert.Greater(carries, 10, "too few carries");
            Assert.Greater(cancels, 10, "too few cancelled investigations");
            Assert.Greater(reactivePins, 0);
            foreach (InhabitantMode m in new[] { InhabitantMode.Routine, InhabitantMode.Alerted, InhabitantMode.Investigating, InhabitantMode.Carrying })
            {
                Assert.IsTrue(modes.Contains(m), "mode never visited: " + m);
            }
        }

        private static Vector3 RandomPoint(System.Random rng, Vector3 center, float min, float max)
        {
            float yaw = (float)(rng.NextDouble() * 360.0);
            float distance = min + (float)rng.NextDouble() * (max - min);
            return YawMath.Planar(center) + YawMath.Forward(yaw) * distance;
        }
    }

    /// <summary>
    /// The M1 station cycle exactly as it shipped at the M1 gate (Core/InhabitantRoutine.cs of 2026-11-11), kept
    /// verbatim as the oracle of the "M1 behavior is unchanged with StraightPlanner" test. Do not edit.
    /// </summary>
    internal sealed class M1ReferenceRoutine
    {
        private enum Kind { Walk, Telegraph, TurnBody, TurnHead, Wait, DwellStart, DwellEnd }

        private struct Action
        {
            public Kind Kind;
            public Vector3 Target;
            public float Value;
            public int Station;
        }

        private readonly List<StationDef> stations;
        private readonly int startStation;
        private readonly Queue<Action> queue = new Queue<Action>();
        private float elapsed;
        private bool hasCurrent;
        private Action current;
        private bool started;
        private bool initialDwellSeen;

        public Vector3 Position { get; private set; }
        public float BodyYaw { get; private set; }
        public float HeadYaw { get; private set; }
        public RoutineActivity LastActivity { get; private set; } = RoutineActivity.Idle;
        public int StationIndex { get; private set; }
        public bool InDwell { get; private set; }
        public int LoopsCompleted { get; private set; }
        public int TelegraphCount { get; private set; }

        public M1ReferenceRoutine(List<StationDef> stations, int startStation)
        {
            this.stations = stations ?? new List<StationDef>();
            this.startStation = this.stations.Count == 0 ? 0 : Mathf.Clamp(startStation, 0, this.stations.Count - 1);
            if (this.stations.Count > 0)
            {
                StationDef s = this.stations[this.startStation];
                Position = s.Position;
                BodyYaw = s.Facing;
            }
            StationIndex = this.startStation;
        }

        public void Step(float dt)
        {
            if (stations.Count == 0)
            {
                LastActivity = RoutineActivity.Idle;
                return;
            }
            if (!started)
            {
                started = true;
                EnqueueDwell(startStation);
                EnqueueDeparture(startStation);
            }

            DrainInstantActions();
            if (!hasCurrent)
            {
                LastActivity = RoutineActivity.Idle;
                return;
            }
            bool done = Run(current, dt);
            if (done)
            {
                hasCurrent = false;
                DrainInstantActions();
            }
        }

        private void DrainInstantActions()
        {
            while (true)
            {
                if (!hasCurrent)
                {
                    if (queue.Count == 0)
                    {
                        int next = (StationIndex + 1) % stations.Count;
                        EnqueueArrival(next);
                        EnqueueDwell(next);
                        EnqueueDeparture(next);
                    }
                    current = queue.Dequeue();
                    hasCurrent = true;
                    elapsed = 0f;
                }
                if (current.Kind == Kind.DwellStart)
                {
                    StationIndex = current.Station;
                    InDwell = true;
                    if (current.Station == startStation)
                    {
                        if (initialDwellSeen)
                        {
                            LoopsCompleted++;
                        }
                        initialDwellSeen = true;
                    }
                    hasCurrent = false;
                    continue;
                }
                if (current.Kind == Kind.DwellEnd)
                {
                    InDwell = false;
                    hasCurrent = false;
                    continue;
                }
                return;
            }
        }

        private bool Run(Action a, float dt)
        {
            switch (a.Kind)
            {
                case Kind.Walk:
                {
                    LastActivity = RoutineActivity.Walking;
                    Position = Vector3.MoveTowards(Position, a.Target, Tuning.WalkSpeed * dt);
                    if ((Position - a.Target).sqrMagnitude < 1e-8f)
                    {
                        Position = a.Target;
                        return true;
                    }
                    return false;
                }
                case Kind.Telegraph:
                {
                    if (elapsed == 0f)
                    {
                        TelegraphCount++;
                    }
                    LastActivity = RoutineActivity.Telegraph;
                    elapsed += dt;
                    return elapsed >= a.Value - 1e-4f;
                }
                case Kind.Wait:
                {
                    LastActivity = RoutineActivity.Waiting;
                    elapsed += dt;
                    return elapsed >= a.Value - 1e-4f;
                }
                case Kind.TurnBody:
                {
                    LastActivity = RoutineActivity.TurningBody;
                    BodyYaw = Mathf.MoveTowardsAngle(BodyYaw, a.Value, Tuning.BodyTurnRate * dt);
                    if (Mathf.Abs(Mathf.DeltaAngle(BodyYaw, a.Value)) < 1e-3f)
                    {
                        BodyYaw = Normalize(a.Value);
                        return true;
                    }
                    return false;
                }
                case Kind.TurnHead:
                {
                    LastActivity = RoutineActivity.TurningHead;
                    HeadYaw = Mathf.MoveTowards(HeadYaw, a.Value, Tuning.HeadTurnRate * dt);
                    if (Mathf.Abs(HeadYaw - a.Value) < 1e-3f)
                    {
                        HeadYaw = a.Value;
                        return true;
                    }
                    return false;
                }
                default:
                    return true;
            }
        }

        private float plannedBodyYaw;
        private float plannedHeadYaw;
        private bool planInitialized;

        private void EnsurePlan()
        {
            if (!planInitialized)
            {
                plannedBodyYaw = BodyYaw;
                plannedHeadYaw = HeadYaw;
                planInitialized = true;
            }
        }

        private void EnqueueArrival(int index)
        {
            EnsurePlan();
            EnqueueBodyTurn(stations[index].Facing);
        }

        private void EnqueueDwell(int index)
        {
            EnsurePlan();
            StationDef s = stations[index];
            queue.Enqueue(new Action { Kind = Kind.DwellStart, Station = index });
            float t = 0f;
            foreach (GlanceDef g in s.Glances)
            {
                if (g.Offset > t + 1e-4f)
                {
                    queue.Enqueue(new Action { Kind = Kind.Wait, Value = g.Offset - t });
                    t = g.Offset;
                }
                t += EnqueueHeadTurn(Mathf.Clamp(g.Yaw, -Tuning.HeadYawLimit, Tuning.HeadYawLimit));
                if (g.Hold > 1e-4f)
                {
                    queue.Enqueue(new Action { Kind = Kind.Wait, Value = g.Hold });
                    t += g.Hold;
                }
                t += EnqueueHeadTurn(0f);
            }
            if (s.Dwell > t + 1e-4f)
            {
                queue.Enqueue(new Action { Kind = Kind.Wait, Value = s.Dwell - t });
            }
            queue.Enqueue(new Action { Kind = Kind.DwellEnd, Station = index });
        }

        private void EnqueueDeparture(int index)
        {
            EnsurePlan();
            int next = (index + 1) % stations.Count;
            Vector3 from = stations[index].Position;
            Vector3 to = stations[next].Position;
            Vector3 d = to - from;
            if (d.sqrMagnitude > 1e-6f)
            {
                EnqueueBodyTurn(YawMath.YawOf(d));
                queue.Enqueue(new Action { Kind = Kind.Walk, Target = to });
            }
        }

        private float EnqueueBodyTurn(float targetYaw)
        {
            float delta = Mathf.Abs(Mathf.DeltaAngle(plannedBodyYaw, targetYaw));
            float duration = 0f;
            if (delta > Tuning.TelegraphMinTurn)
            {
                queue.Enqueue(new Action { Kind = Kind.Telegraph, Value = Tuning.TelegraphDuration });
                duration += Tuning.TelegraphDuration;
            }
            if (delta > 1e-3f)
            {
                queue.Enqueue(new Action { Kind = Kind.TurnBody, Value = Normalize(targetYaw) });
                duration += delta / Tuning.BodyTurnRate;
            }
            plannedBodyYaw = Normalize(targetYaw);
            return duration;
        }

        private float EnqueueHeadTurn(float targetYaw)
        {
            float delta = Mathf.Abs(targetYaw - plannedHeadYaw);
            float duration = 0f;
            if (delta > Tuning.TelegraphMinTurn)
            {
                queue.Enqueue(new Action { Kind = Kind.Telegraph, Value = Tuning.TelegraphDuration });
                duration += Tuning.TelegraphDuration;
            }
            if (delta > 1e-3f)
            {
                queue.Enqueue(new Action { Kind = Kind.TurnHead, Value = targetYaw });
                duration += delta / Tuning.HeadTurnRate;
            }
            plannedHeadYaw = targetYaw;
            return duration;
        }

        private static float Normalize(float yaw)
        {
            return Mathf.Repeat(yaw + 180f, 360f) - 180f;
        }
    }
}
