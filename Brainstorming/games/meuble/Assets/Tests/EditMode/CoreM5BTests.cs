using System;
using System.Collections.Generic;
using System.Reflection;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>Shared helpers of the wave 5B core tests (docs/CONTRACT_M5.md 4, 5, 6, 16.5, 16.8, 16.9).</summary>
    internal static class M5B
    {
        public const float Dt = Tuning.FixedStep;
        public static readonly int WindowSteps = Mathf.RoundToInt(Tuning.LoadWindow / Dt);

        public static readonly Vector2 North = new Vector2(0f, 1f);
        public static readonly Vector2 East = new Vector2(1f, 0f);
        public static readonly Vector2 South = new Vector2(0f, -1f);

        /// <summary>The bodies a load may ride on (CONTRACT_M5 6 and 16.5: not the rocking chair, not the floor lamp).</summary>
        public static readonly string[] LoadBodies = { BodyKinds.Chair, BodyKinds.Stool, BodyKinds.Armchair, BodyKinds.OfficeChair };

        public static Vector2[] Profile(string kind, MotionScript script) => MotionProfile.Synthesize(BodyDef.For(kind), script, Dt);

        public static float Speed(Vector2 v) => v.magnitude;
    }

    /// <summary>docs/CONTRACT_M5.md 5 and 16.12: the rocking chair row, BodyDef.Rocks and BodyKinds.RockingChair.</summary>
    public sealed class CoreM5BBodyTests
    {
        /// <summary>Every public instance field and property of BodyDef, by name (Model aside: the integrator sets it later).</summary>
        private static Dictionary<string, object> Values(BodyDef b)
        {
            var values = new Dictionary<string, object>();
            foreach (FieldInfo f in typeof(BodyDef).GetFields(BindingFlags.Public | BindingFlags.Instance))
            {
                values[f.Name] = f.GetValue(b);
            }
            foreach (PropertyInfo p in typeof(BodyDef).GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                values[p.Name] = p.GetValue(b);
            }
            values.Remove("Model");
            return values;
        }

        private static string FirstMismatch(BodyDef b, Dictionary<string, object> expected)
        {
            Dictionary<string, object> got = Values(b);
            if (got.Count != expected.Count)
            {
                return $"BodyDef has {got.Count} public members besides Model, the row lists {expected.Count}";
            }
            foreach (KeyValuePair<string, object> kv in got)
            {
                if (!expected.TryGetValue(kv.Key, out object want))
                {
                    return $"member {kv.Key} is not covered by the row";
                }
                if (!Equals(want, kv.Value))
                {
                    return $"{b.Kind}.{kv.Key} is {kv.Value}, expected {want}";
                }
            }
            return null;
        }

        private static Dictionary<string, object> RockingRow() => new Dictionary<string, object>
        {
            { "Kind", "rocking_chair" }, { "Size", new Vector3(0.6f, 1.05f, 0.85f) }, { "Radius", 0.36f }, { "MaxSpeed", 1.2f },
            { "Accel", 6f }, { "AccelHigh", 6f }, { "StageSpeed", float.PositiveInfinity }, { "TurnRate", 240f },
            { "CarryForward", 0.65f }, { "Glides", false }, { "Tips", false }, { "HasLight", false }, { "IsSeat", true },
            { "Rocks", true },
        };

        [Test]
        public void Rocking_chair_row_matches_the_contract_member_by_member()
        {
            Assert.IsNull(FirstMismatch(BodyDef.For(BodyKinds.RockingChair), RockingRow()));
            string model = BodyDef.For(BodyKinds.RockingChair).Model;
            Assert.IsTrue(model == null || model.StartsWith("kenney.", StringComparison.Ordinal),
                $"the rocking chair is procedural (null) or a Kenney model, not '{model}'");

            // Premise: the comparison catches a change in the new flag and in a field.
            BodyDef changed = BodyDef.For(BodyKinds.RockingChair);
            changed.Rocks = false;
            StringAssert.Contains("Rocks", FirstMismatch(changed, RockingRow()));
            changed = BodyDef.For(BodyKinds.RockingChair);
            changed.TurnRate = 360f;
            StringAssert.Contains("TurnRate", FirstMismatch(changed, RockingRow()));
            // A caller's change never leaks into the next instance.
            Assert.IsTrue(BodyDef.For(BodyKinds.RockingChair).Rocks, "a caller's change leaked into the next rocking chair");
        }

        [Test]
        public void Only_the_rocking_chair_rocks_and_every_kind_is_a_known_body()
        {
            Assert.AreEqual("rocking_chair", BodyKinds.RockingChair);
            CollectionAssert.AreEqual(new[] { "chair", "stool", "armchair", "floor_lamp", "office_chair", "rocking_chair" }, BodyKinds.All,
                "the M4 order, then the rocking chair");
            foreach (string kind in BodyKinds.All)
            {
                BodyDef b = BodyDef.For(kind);
                Assert.AreEqual(kind, b.Kind, kind + " falls back to another body");
                Assert.IsTrue(BodyKinds.IsKnown(kind), kind);
                Assert.AreEqual(kind == BodyKinds.RockingChair, b.Rocks, kind + ": Rocks");
            }
            Assert.IsFalse(BodyDef.For(null).Rocks, "the default chair rocks");
            Assert.IsFalse(BodyDef.For("wardrobe").Rocks, "an unknown kind (the chair) rocks");
            Assert.AreEqual(BodyDef.For(BodyKinds.RockingChair).Model, BodyKinds.DefaultModel(BodyKinds.RockingChair),
                "a rocking chair without a model shows its body's model (or the procedural one)");
            // The rocking chair is a seat that drives like the armchair family: careful mode halves it, it never tips or glides.
            Assert.AreEqual(0.6f, MotionProfile.MaxSpeedOf(BodyDef.For(BodyKinds.RockingChair), true), 1e-6f);
        }
    }

    /// <summary>
    /// docs/CONTRACT_M5.md 16.5: MotionProfile against the body table, on the six bodies: acceleration and the stool's two
    /// stages, max speeds (full and careful), the M1 instant stop, the office chair glide, the stool tip and righting, the
    /// turn rate, actions and the push, and the stop distance and slide samples per body.
    /// </summary>
    public sealed class CoreM5BMotionTests
    {
        private const float Eps = 1e-4f;

        /// <summary>The straight speeds the body table gives, from rest, one per step (an independent 1D reading of the table).</summary>
        private static List<float> TableSpeeds(BodyDef b, bool careful, int steps)
        {
            float top = b.MaxSpeed * (careful ? Tuning.CarefulFactor : 1f);
            var speeds = new List<float>();
            float v = 0f;
            for (int i = 0; i < steps; i++)
            {
                float cap = Mathf.Max(v + b.AccelHigh * Dt, b.StageSpeed);
                v = Mathf.Min(Mathf.Min(v + b.Accel * Dt, top), cap);
                speeds.Add(v);
            }
            return speeds;
        }

        private const float Dt = M5B.Dt;

        [TestCase("chair")]
        [TestCase("stool")]
        [TestCase("armchair")]
        [TestCase("floor_lamp")]
        [TestCase("office_chair")]
        [TestCase("rocking_chair")]
        public void Straight_start_follows_the_body_table_full_and_careful(string kind)
        {
            BodyDef b = BodyDef.For(kind);
            Assert.AreEqual(kind, b.Kind, "premise: the body of the kind");
            foreach (bool careful in new[] { false, true })
            {
                const int steps = 150;
                Vector2[] v = M5B.Profile(kind, new MotionScript().Repeat(MotionWish.Toward(M5B.North, careful), steps));
                List<float> table = TableSpeeds(b, careful, steps);
                float top = b.MaxSpeed * (careful ? Tuning.CarefulFactor : 1f);
                Assert.AreEqual(top, table[steps - 1], Eps, "premise: the table reaches the top speed in 3 s");
                for (int i = 0; i < steps; i++)
                {
                    string at = $"{kind} careful {careful} step {i}";
                    Assert.AreEqual(table[i], v[i].magnitude, Eps, at + ": speed");
                    Assert.AreEqual(0f, v[i].x, Eps, at + ": straight along +z");
                    Assert.LessOrEqual(v[i].magnitude, top + Eps, at + ": over the top speed");
                }
                Assert.AreEqual(Mathf.Min(b.Accel * Dt, top), v[0].magnitude, Eps, kind + ": the first step is Accel * dt");
            }
        }

        [TestCase("chair")]
        [TestCase("stool")]
        [TestCase("armchair")]
        [TestCase("floor_lamp")]
        [TestCase("office_chair")]
        [TestCase("rocking_chair")]
        public void Release_is_the_instant_stop_the_glide_or_the_tip(string kind)
        {
            BodyDef b = BodyDef.For(kind);
            foreach (bool careful in new[] { false, true })
            {
                var p = new MotionProfile(b, Dt);
                for (int i = 0; i < 200; i++)
                {
                    p.Step(MotionWish.Toward(M5B.North, careful));
                }
                float v0 = p.Speed;
                Assert.AreEqual(MotionProfile.MaxSpeedOf(b, careful), v0, Eps, "premise: at top speed");
                string label = $"{kind} careful {careful}";
                if (b.Glides)
                {
                    // CONTRACT_M4 2.4: to rest in exactly OfficeChairStopTime at a constant deceleration.
                    int glide = Mathf.RoundToInt(Tuning.OfficeChairStopTime / Dt);
                    for (int j = 1; j < glide; j++)
                    {
                        p.Step(MotionWish.None(careful));
                        Assert.IsTrue(p.Gliding, $"{label}: glide step {j}");
                        Assert.AreEqual(v0 * (1f - j / (float)glide), p.Speed, 1e-3f, $"{label}: glide step {j}");
                        Assert.IsTrue(p.IsMoving, label);
                    }
                    p.Step(MotionWish.None(careful));
                    Assert.AreEqual(0f, p.Speed, label + ": the glide ends on time");
                    Assert.IsFalse(p.Gliding, label);
                }
                else if (b.Tips && v0 > Tuning.StoolTipSpeed)
                {
                    p.Step(MotionWish.None(careful));
                    Assert.AreEqual(0f, p.Speed, label + ": the stool falls where it is");
                    Assert.IsTrue(p.Tipped && p.ActionActive && p.IsMoving, label + ": the fall is an action, moving");
                    Assert.AreEqual(1, p.FallCount);
                }
                else
                {
                    p.Step(MotionWish.None(careful));
                    Assert.AreEqual(0f, p.Speed, label + ": PRD 3.2, zero on the release step");
                    Assert.IsFalse(p.IsMoving || p.Tipped || p.Gliding || p.ActionActive, label);
                }
            }
        }

        [TestCase("chair")]
        [TestCase("stool")]
        [TestCase("armchair")]
        [TestCase("floor_lamp")]
        [TestCase("office_chair")]
        [TestCase("rocking_chair")]
        public void Yaw_turns_toward_the_wish_at_the_body_turn_rate(string kind)
        {
            BodyDef b = BodyDef.For(kind);
            var p = new MotionProfile(b, Dt, true, 0f);
            float perStep = b.TurnRate * Dt;
            int steps = Mathf.CeilToInt(90f / perStep);
            for (int k = 1; k <= steps + 3; k++)
            {
                p.Step(MotionWish.TowardYaw(90f));
                Assert.AreEqual(Mathf.Min(k * perStep, 90f), p.Yaw, 1e-2f, $"{kind}: yaw after {k} steps");
                Assert.LessOrEqual(Mathf.Abs(p.YawRate), b.TurnRate + 1e-2f, kind);
            }
            Assert.AreEqual(90f, p.Yaw, 1e-3f, "premise: the turn finished");
        }

        [Test]
        public void Stop_distance_and_slide_samples_per_body()
        {
            foreach (string kind in BodyKinds.All)
            {
                BodyDef b = BodyDef.For(kind);
                foreach (bool careful in new[] { false, true })
                {
                    float d = MotionProfile.StopDistance(b, careful);
                    int steps = MotionProfile.SlideSteps(b, careful);
                    int samples = MotionProfile.SlideSamples(b, careful);
                    string label = $"{kind} careful {careful}";
                    if (b.Glides)
                    {
                        // 19 glide steps of v0 * remaining / 0.4: 9.5 steps of v0, so 0.532 m at 2.8 m/s and 0.266 m at 1.4 m/s.
                        float v0 = MotionProfile.MaxSpeedOf(b, careful);
                        Assert.AreEqual(v0 * Dt * 9.5f, d, 1e-3f, label + ": the glide distance");
                        Assert.AreEqual(19, steps, label);
                        Assert.AreEqual(Tuning.AuditStopSamples, samples, label + ": the M4 audit's glide cost");
                    }
                    else
                    {
                        Assert.AreEqual(0f, d, label + ": the instant stop (or the tip, where it is)");
                        Assert.AreEqual(0, steps, label);
                        Assert.AreEqual(0, samples, label);
                    }
                }
            }
            Assert.AreEqual(0.532f, MotionProfile.StopDistance(BodyDef.For(BodyKinds.OfficeChair), false), 1e-3f);
            // Under GameRules.Bodies off (levels 1 to 3), the office chair stops at once, as the chair.
            Assert.AreEqual(0f, MotionProfile.StopDistance(BodyDef.For(BodyKinds.OfficeChair), false, Dt, false));
            Assert.AreEqual(0, MotionProfile.SlideSamples(BodyDef.For(BodyKinds.OfficeChair), false, Dt, false));
        }

        [Test]
        public void Office_chair_glides_when_braked_against_its_motion_then_drives_back()
        {
            var p = new MotionProfile(BodyDef.For(BodyKinds.OfficeChair), Dt);
            for (int i = 0; i < 100; i++)
            {
                p.Step(MotionWish.Toward(M5B.North));
            }
            Assert.AreEqual(2.8f, p.Speed, Eps, "premise");
            int glideSteps = 0;
            while (p.Velocity.y >= 0f && glideSteps < 100)
            {
                p.Step(MotionWish.Toward(M5B.South));
                if (p.Gliding)
                {
                    glideSteps++;
                    Assert.Greater(p.Velocity.y, 0f, "input against the motion brakes no faster than the glide");
                }
                if (p.Speed == 0f)
                {
                    break;
                }
            }
            Assert.AreEqual(19, glideSteps, "the glide against the input");
            p.Step(MotionWish.Toward(M5B.South));
            Assert.AreEqual(-BodyDef.For(BodyKinds.OfficeChair).Accel * Dt, p.Velocity.y, Eps, "then it accelerates the other way");
        }

        [Test]
        public void Stool_lies_after_its_fall_until_an_input_edge_then_rights_itself_and_drives()
        {
            var p = new MotionProfile(BodyDef.For(BodyKinds.Stool), Dt);
            for (int i = 0; i < 200; i++)
            {
                p.Step(MotionWish.Toward(M5B.North));
            }
            Assert.Greater(p.Speed, Tuning.StoolTipSpeed, "premise: above the tip speed");
            int fall = Mathf.RoundToInt(Tuning.StoolFallTime / Dt);
            int right = Mathf.RoundToInt(Tuning.StoolRightTime / Dt);
            for (int i = 0; i < fall; i++)
            {
                p.Step(MotionWish.None());
                Assert.IsTrue(p.ActionActive && p.IsMoving && p.Tipped, $"fall step {i}");
            }
            for (int i = 0; i < 30; i++)
            {
                p.Step(MotionWish.None());
                Assert.IsFalse(p.ActionActive || p.IsMoving, "lying still");
                Assert.IsTrue(p.Tipped);
            }
            for (int i = 0; i < right; i++)
            {
                p.Step(MotionWish.Toward(M5B.East));
                Assert.IsTrue(p.ActionActive && p.IsMoving, $"righting step {i}: input ignored, moving");
                Assert.AreEqual(0f, p.Speed);
            }
            p.Step(MotionWish.Toward(M5B.East));
            Assert.IsFalse(p.Tipped || p.ActionActive, "upright");
            Assert.AreEqual(BodyDef.For(BodyKinds.Stool).Accel * Dt, p.Speed, Eps, "it drives on the step the righting ends");

            // Careful mode never reaches the tip speed: no fall.
            var c = new MotionProfile(BodyDef.For(BodyKinds.Stool), Dt);
            for (int i = 0; i < 200; i++)
            {
                c.Step(MotionWish.Toward(M5B.North, true));
            }
            c.Step(MotionWish.None(true));
            Assert.IsFalse(c.Tipped, "a careful stool tipped");
            Assert.AreEqual(0, c.FallCount);
        }

        [Test]
        public void Bodies_off_has_no_careful_mode_no_glide_and_no_tip()
        {
            foreach (string kind in new[] { BodyKinds.Stool, BodyKinds.OfficeChair, BodyKinds.Chair })
            {
                var p = new MotionProfile(BodyDef.For(kind), Dt, false);
                for (int i = 0; i < 200; i++)
                {
                    p.Step(MotionWish.Toward(M5B.North, true));
                }
                Assert.IsFalse(p.Careful, kind);
                Assert.AreEqual(BodyDef.For(kind).MaxSpeed, p.Speed, Eps, kind + ": careful is a Bodies rule");
                p.Step(MotionWish.None(true));
                Assert.AreEqual(0f, p.Speed, kind + ": the M1 stop");
                Assert.IsFalse(p.Tipped || p.Gliding, kind);
            }
        }

        [Test]
        public void Actions_ignore_the_input_and_the_push_is_a_constant_shove()
        {
            BodyDef rocking = BodyDef.For(BodyKinds.RockingChair);
            var p = new MotionProfile(rocking, Dt);
            p.Step(MotionWish.Toward(M5B.North));
            Assert.IsFalse(p.BeginAction(Tuning.RockTime), "refused while moving");
            p.Step(MotionWish.None());
            Assert.IsFalse(p.IsMoving, "premise: at rest");
            int rock = MotionProfile.RockSteps(rocking, false);
            Assert.AreEqual(40, rock, "CONTRACT_M5 12 step 43: 40 steps");
            Assert.AreEqual(20, MotionProfile.RockSteps(rocking, true), "20 when careful");
            Assert.AreEqual(0, MotionProfile.RockSteps(BodyDef.For(BodyKinds.Chair), false), "only the rocking chair rocks");
            Assert.IsTrue(p.BeginAction(rock * Dt));
            for (int i = 0; i < rock; i++)
            {
                p.Step(MotionWish.Toward(M5B.East));
                Assert.IsTrue(p.ActionActive && p.IsMoving, $"rock step {i}");
                Assert.AreEqual(0f, p.Speed, "input ignored");
            }
            p.Step(MotionWish.Toward(M5B.East));
            Assert.IsFalse(p.ActionActive);
            Assert.AreEqual(rocking.Accel * Dt, p.Speed, Eps, "drives again after the action");

            // The robot's shove: 0.25 m in 0.5 s at a constant 0.5 m/s, moving, input ignored, then still.
            var s = new MotionProfile(BodyDef.For(BodyKinds.Chair), Dt);
            s.Step(MotionWish.None());
            Assert.IsFalse(s.BeginPush(Vector2.zero, Tuning.RobotPushDistance, Tuning.RobotPushTime), "a push needs a direction");
            Assert.IsTrue(s.BeginPush(M5B.East, Tuning.RobotPushDistance, Tuning.RobotPushTime));
            Assert.IsFalse(s.BeginPush(M5B.East, Tuning.RobotPushDistance, Tuning.RobotPushTime), "no shove during an action");
            int pushSteps = Mathf.RoundToInt(Tuning.RobotPushTime / Dt);
            float travelled = 0f;
            for (int i = 0; i < pushSteps; i++)
            {
                s.Step(MotionWish.Toward(M5B.North));
                Assert.IsTrue(s.Pushing && s.IsMoving, $"push step {i}");
                Assert.AreEqual(0.5f, s.Velocity.x, Eps);
                Assert.AreEqual(0f, s.Velocity.y, Eps, "input ignored");
                travelled += s.Speed * Dt;
            }
            Assert.AreEqual(Tuning.RobotPushDistance, travelled, 1e-4f);
            s.Step(MotionWish.None());
            Assert.IsFalse(s.ActionActive || s.IsMoving, "still after the shove");
        }

        [Test]
        public void Synthesize_overloads_agree_and_the_script_counts_steps()
        {
            var script = new MotionScript().Hold(M5B.North, 0.5f, true).Release(0.1f, true).HoldYaw(90f, 0.3f, true);
            Assert.AreEqual(25 + 5 + 15, script.Count, "round(seconds / dt) steps each");
            var plain = new List<Vector2>();
            foreach (MotionWish w in script)
            {
                plain.Add(w.Direction);
            }
            BodyDef b = BodyDef.For(BodyKinds.OfficeChair);
            Vector2[] a = MotionProfile.Synthesize(b, script, Dt);
            Vector2[] c = MotionProfile.Synthesize(b, true, plain, Dt);
            Assert.AreEqual(a.Length, c.Length);
            for (int i = 0; i < a.Length; i++)
            {
                Assert.AreEqual(a[i], c[i], $"step {i}");
            }
            Assert.AreEqual(1.4f, a[24].magnitude, Eps, "premise: careful top speed reached");
            Assert.Greater(a[26].magnitude, 0f, "premise: the careful release glides");
        }
    }

    /// <summary>
    /// docs/CONTRACT_M5.md 16.5: the kinematic load rule. The targets run on MotionProfile velocity profiles of the real
    /// body table.
    /// </summary>
    public sealed class CoreM5BLoadTests
    {
        private const float Dt = M5B.Dt;

        private static LoadBalance Run(IList<Vector2> velocities)
        {
            var load = new LoadBalance();
            foreach (Vector2 v in velocities)
            {
                load.Step(Dt, v);
            }
            return load;
        }

        private static void AssertFalls(string what, string kind, MotionScript script, float minPeak)
        {
            Vector2[] v = M5B.Profile(kind, script);
            LoadBalance load = Run(v);
            Assert.IsTrue(load.Fallen, $"{what} ({kind}) holds: peak {load.PeakDeltaV:0.000} m/s");
            Assert.GreaterOrEqual(load.PeakDeltaV, minPeak - 1e-3f, what);
            Assert.AreEqual(LoadBalance.FirstFall(v, Dt) + 1, load.FallStep, what + ": FirstFall is the fall step");
        }

        private static void AssertHolds(string what, string kind, MotionScript script, float expectedPeak)
        {
            Vector2[] v = M5B.Profile(kind, script);
            LoadBalance load = Run(v);
            Assert.IsFalse(load.Fallen, $"{what} ({kind}) drops the load: peak {load.PeakDeltaV:0.000} m/s");
            Assert.AreEqual(expectedPeak, load.PeakDeltaV, 2e-3f, what + ": the peak change");
            Assert.AreEqual(-1, LoadBalance.FirstFall(v, Dt), what);
            Assert.AreEqual(load.PeakDeltaV, LoadBalance.PeakOf(v, Dt), 1e-6f, what);
        }

        // ----- Falls -----

        [Test]
        public void A_90_deg_turn_at_full_chair_speed_drops_the_load()
        {
            // Premise: the straight run before the turn holds.
            AssertHolds("the run before the turn", BodyKinds.Chair, new MotionScript().Hold(M5B.North, 1f), 1.5f);
            AssertFalls("a 90 deg turn at full speed", BodyKinds.Chair, new MotionScript().Hold(M5B.North, 1f).Hold(M5B.East, 1f), 2.12f);
        }

        [Test]
        public void Any_full_speed_reversal_drops_the_load()
        {
            foreach (string kind in M5B.LoadBodies)
            {
                MotionScript script = new MotionScript().Hold(M5B.North, 2f);
                if (kind == BodyKinds.OfficeChair)
                {
                    // Up to full speed without dropping it (careful first, then full: changes of 1.4 each).
                    script = new MotionScript().Hold(M5B.North, 1f, true).Hold(M5B.North, 1f);
                }
                Vector2[] before = M5B.Profile(kind, script);
                Assert.AreEqual(BodyDef.For(kind).MaxSpeed, before[before.Length - 1].magnitude, 1e-4f, kind + ": premise, at full speed");
                Assert.AreEqual(-1, LoadBalance.FirstFall(before, Dt), kind + ": premise, the run up holds");
                script.Hold(M5B.South, 1.5f);
                AssertFalls("a full-speed reversal", kind, script, 1.8f);
            }
        }

        [Test]
        public void The_office_chair_full_start_and_full_glide_drop_the_load()
        {
            AssertFalls("the full start", BodyKinds.OfficeChair, new MotionScript().Hold(M5B.North, 1.5f), 1.8f);
            // The glide alone: up to 2.8 m/s without dropping it, then release.
            MotionScript glide = new MotionScript().Hold(M5B.North, 1f, true).Hold(M5B.North, 1f);
            AssertHolds("the run up to full speed", BodyKinds.OfficeChair, glide, 1.4f);
            glide.Release(1f);
            AssertFalls("the full glide", BodyKinds.OfficeChair, glide, 2.8f);
        }

        [Test]
        public void Careful_U_turns_of_the_stool_and_the_office_chair_drop_the_load()
        {
            AssertFalls("a careful U-turn", BodyKinds.Stool, new MotionScript().Hold(M5B.North, 1f, true).Hold(M5B.South, 1f, true), 2.4f);
            AssertFalls("a careful U-turn", BodyKinds.OfficeChair,
                new MotionScript().Hold(M5B.North, 1f, true).Hold(M5B.South, 1.5f, true), 2.4f);
        }

        // ----- Holds -----

        [Test]
        public void The_chair_straight_starts_and_stops_hold()
        {
            AssertHolds("a full start and stop", BodyKinds.Chair, new MotionScript().Hold(M5B.North, 1f).Release(1f), 1.5f);
            AssertHolds("starts and stops, again and again", BodyKinds.Chair,
                new MotionScript().Hold(M5B.North, 0.3f).Release(0.3f).Hold(M5B.North, 0.3f).Release(1f).Hold(M5B.East, 0.5f).Release(1f), 1.5f);
        }

        [Test]
        public void Every_careful_straight_move_holds()
        {
            foreach (string kind in M5B.LoadBodies)
            {
                float top = MotionProfile.MaxSpeedOf(BodyDef.For(kind), true);
                AssertHolds("a careful start and stop", kind, new MotionScript().Hold(M5B.North, 1.5f, true).Release(1f, true), top);
            }
        }

        [Test]
        public void A_careful_90_deg_chair_turn_and_a_careful_chair_reversal_hold()
        {
            AssertHolds("a careful 90 deg turn", BodyKinds.Chair, new MotionScript().Hold(M5B.North, 1f, true).Hold(M5B.East, 1f, true),
                0.75f * Mathf.Sqrt(2f));
            AssertHolds("a careful reversal", BodyKinds.Chair, new MotionScript().Hold(M5B.North, 1f, true).Hold(M5B.South, 1f, true), 1.5f);
        }

        [Test]
        public void The_robot_shove_holds()
        {
            var p = new MotionProfile(BodyDef.For(BodyKinds.Chair), Dt);
            var v = new List<Vector2>();
            v.Add(p.Step(MotionWish.None()));
            Assert.IsTrue(p.BeginPush(M5B.East, Tuning.RobotPushDistance, Tuning.RobotPushTime), "premise");
            for (int i = 0; i < 60; i++)
            {
                v.Add(p.Step(MotionWish.None()));
            }
            Assert.AreEqual(0.5f, v[1].magnitude, 1e-4f, "premise: 0.25 m in 0.5 s");
            LoadBalance load = Run(v);
            Assert.IsFalse(load.Fallen);
            Assert.AreEqual(0.5f, load.PeakDeltaV, 1e-4f);
        }

        // ----- The rule -----

        [Test]
        public void DeltaV_compares_with_the_velocity_exactly_one_window_before()
        {
            Assert.AreEqual(25, M5B.WindowSteps, "premise: 0.5 s is 25 steps");
            var load = new LoadBalance();
            load.Step(Dt, new Vector2(1f, 0f));
            Assert.AreEqual(1f, load.DeltaV, 1e-6f, "against the rest before the first step");
            for (int k = 2; k <= 40; k++)
            {
                load.Step(Dt, Vector2.zero);
                float want = k == M5B.WindowSteps + 1 ? 1f : 0f;
                Assert.AreEqual(want, load.DeltaV, 1e-6f, $"step {k}: the impulse of step 1 is exactly 25 steps back on step 26 only");
            }
            Assert.AreEqual(40, load.StepCount);
            Assert.AreEqual(40 * Dt, load.Time, 1e-4f);
            Assert.AreEqual(1f, load.PeakDeltaV, 1e-6f);
        }

        [Test]
        public void The_fall_is_at_the_threshold_latched_until_reset_and_ratio_is_the_gauge()
        {
            var load = new LoadBalance();
            load.Step(Dt, new Vector2(0f, 1.79f));
            Assert.IsFalse(load.Fallen, "1.79 m/s holds");
            Assert.AreEqual(1.79f / Tuning.LoadFallDeltaV, load.Ratio, 1e-5f, "the gauge is DeltaV over the threshold");
            Assert.Less(load.Ratio, 1f);

            load.Reset();
            load.Step(Dt, new Vector2(0f, Tuning.LoadFallDeltaV));
            Assert.IsTrue(load.Fallen && load.JustFell, "a change of exactly the threshold falls");
            Assert.AreEqual(1, load.FallStep);
            Assert.AreEqual(1f, load.Ratio, 1e-5f);
            for (int i = 0; i < 100; i++)
            {
                load.Step(Dt, Vector2.zero);
                Assert.IsFalse(load.JustFell, "JustFell is one step");
                Assert.IsTrue(load.Fallen, "the fall is latched");
            }
            load.Reset();
            Assert.IsFalse(load.Fallen || load.JustFell);
            Assert.AreEqual(-1, load.FallStep);
            Assert.AreEqual(0f, load.DeltaV);
            Assert.AreEqual(Vector2.zero, load.SwayTilt);
            load.Step(Dt, new Vector2(0f, 1f));
            Assert.AreEqual(1f, load.DeltaV, 1e-6f, "the history restarts at rest");
            load.Step(0f, new Vector2(0f, 9f));
            Assert.AreEqual(1, load.StepCount, "a step of no time is ignored");
        }

        [Test]
        public void The_sway_leans_against_the_acceleration_settles_and_decides_nothing()
        {
            var load = new LoadBalance();
            // The chair's full start along +z: the load leans back (-z).
            Vector2[] start = M5B.Profile(BodyKinds.Chair, new MotionScript().Hold(M5B.North, 0.1f));
            foreach (Vector2 v in start)
            {
                load.Step(Dt, v);
            }
            Assert.Less(load.SwayTilt.y, -0.5f, "accelerating forward leans the load back");
            Assert.AreEqual(0f, load.SwayTilt.x, 1e-4f);
            // In the frame of a furniture facing +x (yaw 90), world -z is to its right.
            Vector2 local = load.SwayTiltLocal(90f);
            Assert.Greater(local.x, 0.5f, "world -z is the right of a furniture facing +x");
            Assert.AreEqual(0f, local.y, 1e-3f);
            // At constant speed it settles back.
            for (int i = 0; i < 250; i++)
            {
                load.Step(Dt, new Vector2(0f, 1.5f));
            }
            Assert.Less(load.SwayTilt.magnitude, 0.05f, "the spring settles at constant speed");
            // The full stop sways it hard (about 18 deg forward), and the rule still holds the load.
            float peak = 0f;
            for (int i = 0; i < 100; i++)
            {
                load.Step(Dt, Vector2.zero);
                peak = Mathf.Max(peak, load.SwayTilt.y);
            }
            Assert.Greater(peak, 10f, "a full stop throws the load forward");
            Assert.Less(peak, 25f);
            Assert.IsFalse(load.Fallen, "the sway decides nothing: the chair's stop holds");
        }
    }

    /// <summary>docs/CONTRACT_M5.md 4 and 16.8: the robot's timeline, its reversal and the contact test.</summary>
    public sealed class CoreM5BRobotTests
    {
        private static RobotDef Square(int start = 0, float speed = 0f)
        {
            var def = new RobotDef { Name = "Robot", Start = start, Speed = speed };
            def.Loop.Add(new PointDef { X = 0f, Z = 0f });
            def.Loop.Add(new PointDef { X = 2f, Z = 0f });
            def.Loop.Add(new PointDef { X = 2f, Z = 2f });
            def.Loop.Add(new PointDef { X = 0f, Z = 2f });
            return def;
        }

        private static void Near(Vector3 want, Vector3 got, string what)
        {
            Assert.Less((want - got).magnitude, 1e-4f, $"{what}: expected {want}, got {got}");
        }

        [Test]
        public void The_loop_timing_position_and_heading()
        {
            var path = new RobotPath(Square());
            Assert.AreEqual(Tuning.RobotSpeed, path.Speed, "a speed of 0 is the default 0.4 m/s");
            Assert.AreEqual(8f, path.Length, 1e-5f);
            Assert.AreEqual(20f, path.Period, 1e-4f);
            Near(new Vector3(0f, 0f, 0f), path.PositionAt(0f), "t 0 on the start waypoint");
            Assert.AreEqual(90f, path.HeadingAt(0f), 1e-3f, "heading for waypoint 1 (+x)");
            Near(new Vector3(1f, 0f, 0f), path.PositionAt(2.5f), "1 m along at 0.4 m/s");
            Near(new Vector3(2f, 0f, 0f), path.PositionAt(5f), "waypoint 1");
            Assert.AreEqual(0f, path.HeadingAt(5f), 1e-3f, "on a waypoint, the heading of the segment it leaves by");
            Near(new Vector3(2f, 0f, 1f), path.PositionAt(7.5f), "segment 1");
            Near(new Vector3(0f, 0f, 1f), path.PositionAt(17.5f), "the last segment, back to waypoint 0");
            Assert.AreEqual(180f, Mathf.Abs(path.HeadingAt(17.5f)), 1e-3f, "heading -z on the last segment");
            for (float t = 0f; t < 25f; t += 0.37f)
            {
                Near(path.PositionAt(t), path.PositionAt(t + path.Period), $"periodic at {t}");
                Near(path.PositionAt(t), path.PositionAt(t + 3f * path.Period), $"periodic at {t}");
            }

            var fast = new RobotPath(Square(2, 0.8f));
            Assert.AreEqual(10f, fast.Period, 1e-4f);
            Near(new Vector3(2f, 0f, 2f), fast.PositionAt(0f), "start on waypoint 2");
            Assert.AreEqual(-90f, fast.HeadingAt(0f), 1e-3f, "heading for waypoint 3 (-x)");
            Near(new Vector3(0f, 0f, 1.6f), fast.PositionAt(3f), "2.4 m from waypoint 2: 2 m to waypoint 3, then 0.4 m down the last segment");
            Assert.AreEqual(0, fast.ReverseCount);
        }

        [Test]
        public void Reverse_travels_the_loop_backwards_from_where_it_is()
        {
            var path = new RobotPath(Square());
            Near(new Vector3(1.5f, 0f, 0f), path.PositionAt(3.75f), "premise: without a reversal");
            path.Reverse(2.5f);
            Assert.AreEqual(1, path.ReverseCount);
            Assert.AreEqual(2.5f, path.LastReverseTime, 1e-6f);
            Near(new Vector3(0.4f, 0f, 0f), path.PositionAt(1f), "the past is unchanged");
            Near(new Vector3(1f, 0f, 0f), path.PositionAt(2.5f), "no jump at the reversal");
            Assert.AreEqual(1, path.DirectionAt(2.4f));
            Assert.AreEqual(-1, path.DirectionAt(2.6f));
            Near(new Vector3(0.5f, 0f, 0f), path.PositionAt(3.75f), "back toward waypoint 0");
            Assert.AreEqual(-90f, path.HeadingAt(3.75f), 1e-3f, "heading -x");
            Near(new Vector3(0f, 0f, 0f), path.PositionAt(5f), "waypoint 0");
            Assert.AreEqual(0f, path.HeadingAt(5f), 1e-3f, "backwards, it leaves waypoint 0 along the last segment (+z)");
            Near(new Vector3(0f, 0f, 1f), path.PositionAt(7.5f), "the last segment, backwards");

            // A second reversal goes forward again; the same reversals always give the same timeline.
            path.Reverse(7.5f);
            Near(new Vector3(0f, 0f, 0.6f), path.PositionAt(8.5f), "forward again, toward waypoint 0");
            var twin = new RobotPath(Square());
            twin.Reverse(2.5f);
            twin.Reverse(7.5f);
            for (float t = 0f; t < 30f; t += 0.13f)
            {
                Assert.AreEqual(path.PositionAt(t), twin.PositionAt(t), $"deterministic at {t}");
                Assert.AreEqual(path.HeadingAt(t), twin.HeadingAt(t), $"deterministic at {t}");
            }

            // A reversal at an earlier time drops the later ones.
            path.Reverse(3f);
            Assert.AreEqual(2, path.ReverseCount, "the 7.5 s reversal was dropped");
            Near(new Vector3(0.8f, 0f, 0f), path.PositionAt(3f), "the position at 3 s on the first reversed leg");
            Near(new Vector3(1.2f, 0f, 0f), path.PositionAt(4f), "forward again from 3 s");
        }

        [Test]
        public void Two_waypoints_go_there_and_back_and_degenerate_loops_stand_still()
        {
            var def = new RobotDef();
            def.Loop.Add(new PointDef { X = 0f, Z = 0f });
            def.Loop.Add(new PointDef { X = 1f, Z = 0f });
            var path = new RobotPath(def);
            Assert.AreEqual(2f, path.Length, 1e-5f);
            Near(new Vector3(0.5f, 0f, 0f), path.PositionAt(1.25f), "out");
            Assert.AreEqual(90f, path.HeadingAt(1.25f), 1e-3f);
            Near(new Vector3(0.5f, 0f, 0f), path.PositionAt(3.75f), "and back");
            Assert.AreEqual(-90f, path.HeadingAt(3.75f), 1e-3f);

            var none = new RobotPath(null);
            Assert.AreEqual(Vector3.zero, none.PositionAt(3f));
            Assert.AreEqual(0f, none.Length);
            Assert.AreEqual(0f, none.Period);
            var one = new RobotDef();
            one.Loop.Add(new PointDef { X = 1f, Z = 2f });
            var still = new RobotPath(one);
            Near(new Vector3(1f, 0f, 2f), still.PositionAt(7f), "a single waypoint");
            still.Reverse(1f);
            Near(new Vector3(1f, 0f, 2f), still.PositionAt(9f), "still there");
            Assert.AreEqual(Vector3.zero, still.ForwardAt(2f));
        }

        [Test]
        public void Overlaps_is_the_robot_disc_against_the_turned_footprint()
        {
            Vector3 chair = BodyDef.For(BodyKinds.Chair).Size;
            var pose = new FurniturePose(new Vector3(1f, 0f, 1f), 0f);
            float edge = chair.x * 0.5f + Tuning.RobotRadius;
            Assert.IsTrue(RobotPath.Overlaps(new Vector3(1f + edge - 0.01f, 0f, 1f), pose, chair), "just inside");
            Assert.IsFalse(RobotPath.Overlaps(new Vector3(1f + edge + 0.01f, 0f, 1f), pose, chair), "just outside");
            Assert.IsTrue(RobotPath.Overlaps(new Vector3(1f, 0.3f, 1f + edge - 0.01f), pose, chair), "heights are ignored");
            // Turned 45 deg, the corner reaches farther along x.
            float corner = chair.x * 0.5f * Mathf.Sqrt(2f) + Tuning.RobotRadius;
            var at = new Vector3(1f + corner - 0.01f, 0f, 1f);
            Assert.IsFalse(RobotPath.Overlaps(at, pose, chair), "premise: square on, the corner is not there");
            Assert.IsTrue(RobotPath.Overlaps(at, new FurniturePose(pose.Position, 45f), chair), "turned 45 deg, the corner touches");
        }
    }

    /// <summary>docs/CONTRACT_M5.md 4 and 12 (step 42): the robot's hum masks hops, rolls and clicks within 2.5 m only.</summary>
    public sealed class CoreM5BHearingTests
    {
        [Test]
        public void The_hum_masks_a_hop_a_roll_and_a_click_within_2_5_m_only()
        {
            var robots = new List<Vector3> { new Vector3(10f, 0f, 10f), new Vector3(0f, 0f, 0f) };
            foreach (NoiseKind kind in new[] { NoiseKind.Hop, NoiseKind.Roll, NoiseKind.Click })
            {
                Assert.IsTrue(Hearing.IsMasked(kind, new Vector3(2.4f, 0f, 0f), robots), kind + " at 2.4 m");
                Assert.IsTrue(Hearing.IsMasked(kind, new Vector3(0f, 0f, Tuning.RobotHumRadius), robots), kind + " at exactly 2.5 m");
                Assert.IsTrue(Hearing.IsMasked(kind, new Vector3(1.6f, 1.2f, 1.6f), robots), kind + ": planar distance (2.26 m), height ignored");
                Assert.IsFalse(Hearing.IsMasked(kind, new Vector3(2.6f, 0f, 0f), robots), kind + " at 2.6 m");
                Assert.IsTrue(Hearing.IsMasked(kind, new Vector3(11f, 0f, 9f), robots), kind + ": near any robot");
                Assert.IsFalse(Hearing.IsMasked(kind, Vector3.zero, null), kind + ": no robot list");
                Assert.IsFalse(Hearing.IsMasked(kind, Vector3.zero, new List<Vector3>()), kind + ": no robot");
                Assert.IsTrue(Hearing.IsMaskable(kind), kind.ToString());
            }
            Assert.AreEqual(2.5f, Tuning.RobotHumRadius, "the contract's hum radius");
        }

        [Test]
        public void Topple_creak_crash_and_bark_are_never_masked()
        {
            var robots = new List<Vector3> { Vector3.zero };
            Assert.IsTrue(Hearing.IsMasked(NoiseKind.Hop, Vector3.zero, robots), "premise: a hop on the robot is masked");
            foreach (NoiseKind kind in new[] { NoiseKind.Topple, NoiseKind.Creak, NoiseKind.Crash, NoiseKind.Bark })
            {
                Assert.IsFalse(Hearing.IsMasked(kind, Vector3.zero, robots), kind + " on the robot");
                Assert.IsFalse(Hearing.IsMasked(kind, new Vector3(1f, 0f, 0f), robots), kind + " at 1 m");
                Assert.IsFalse(Hearing.IsMaskable(kind), kind.ToString());
            }
            var maskable = new List<NoiseKind>();
            foreach (NoiseKind kind in Enum.GetValues(typeof(NoiseKind)))
            {
                if (Hearing.IsMaskable(kind))
                {
                    maskable.Add(kind);
                }
            }
            CollectionAssert.AreEquivalent(new[] { NoiseKind.Hop, NoiseKind.Roll, NoiseKind.Click }, maskable, "exactly the small noises");
        }
    }

    /// <summary>docs/CONTRACT_M5.md 6 and 12 (step 44): an inhabitant with memory puts a fallen load's clue away.</summary>
    public sealed class CoreM5BPutAwayTests
    {
        private const float Dt = M5B.Dt;
        private static readonly int PutAwaySteps = Mathf.RoundToInt(Tuning.PutAwayTime / Dt);

        /// <summary>A long dwell at the origin facing +z, then a far station.</summary>
        private static List<StationDef> Dwell() => new List<StationDef>
        {
            M5.Plain(0f, 0f, 0f, 30f),
            M5.Plain(-4f, 0f, 0f, 2f),
        };

        private struct Flags
        {
            public bool PutAway;
            public bool PickedUp;
            public bool Carrying;
            public bool Reached;
            public InhabitantMode Mode;
        }

        /// <summary>Steps until JustPutAway (bounded), recording the flags of every step after the command.</summary>
        private static List<Flags> RunPutAway(M5Recorder rec, int max)
        {
            var flags = new List<Flags>();
            for (int i = 0; i < max; i++)
            {
                rec.Step();
                InhabitantRoutine r = rec.R;
                flags.Add(new Flags { PutAway = r.JustPutAway, PickedUp = r.JustPickedUp, Carrying = r.IsCarrying, Reached = r.ReachedTarget, Mode = r.Mode });
                if (r.JustPutAway)
                {
                    return flags;
                }
            }
            Assert.Fail($"never put the clue away within {max} steps");
            return flags;
        }

        [Test]
        public void Put_away_walks_to_the_clue_faces_it_bends_for_0_6_s_and_resumes()
        {
            InhabitantRoutine r = RoutineFactory.Create(M5.Def(Dwell()), null, StraightPlanner.Instance);
            var rec = new M5Recorder(r);
            rec.Step(10);
            Assert.IsTrue(r.InDwell, "premise: in the start dwell");
            var clue = new Vector3(3f, 0f, 0f);
            int from = rec.Index;
            r.BeginPutAway(clue);
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode, "the put-away is an investigation");
            List<Flags> flags = RunPutAway(rec, 1000);
            List<M5Rec> log = rec.Since(from);

            Assert.IsTrue(log.Exists(x => x.Act == RoutineActivity.Walking), "it walked");
            float reach = YawMath.Planar(r.Position - clue).magnitude;
            Assert.LessOrEqual(reach, Tuning.InvestigateReach + 1e-3f, "it stops within reach of the clue");
            Assert.Greater(reach, Tuning.InvestigateReach - 0.1f, "it stops at reach, not on the clue");
            Assert.AreEqual(90f, Mathf.Repeat(r.BodyYaw + 360f, 360f), 0.5f, "it faces the clue");
            Assert.AreEqual(PutAwaySteps, M5.CountBefore(log, log.Count, RoutineActivity.PickingUp), "bent over the clue for PutAwayTime");
            Assert.AreEqual(1, flags.FindAll(f => f.PutAway).Count, "JustPutAway is one step");
            Assert.IsTrue(flags[flags.Count - 1].PutAway, "on the beat's last step");
            Assert.IsFalse(flags.Exists(f => f.PickedUp || f.Carrying || f.Reached), "it carries nothing and reaches no investigation");
            Assert.IsTrue(flags.TrueForAll(f => f.Mode == InhabitantMode.Investigating), "Investigating until it resumes");
            M5.AssertTelegraphs(log, "the put-away");

            // The next step it resumes, back to the station of its current visit.
            rec.Step();
            Assert.IsFalse(r.JustPutAway, "JustPutAway lasted one step");
            Assert.AreEqual(InhabitantMode.Routine, r.Mode, "resumes on the next step");
            rec.StepUntil(x => x.InDwell, 1500, "back in the dwell");
            Assert.AreEqual(0, r.StationIndex, "back to the station it was dwelling at");
            Assert.AreEqual(0, r.VisitIndex, "the visit does not move");
            Assert.Less(YawMath.Planar(r.Position).magnitude, 1e-3f);
            M5.AssertTelegraphs(rec.Since(from), "the put-away and the resume");
        }

        [Test]
        public void A_clue_within_reach_is_put_away_without_walking()
        {
            InhabitantRoutine r = RoutineFactory.Create(M5.Def(Dwell()), null, StraightPlanner.Instance);
            var rec = new M5Recorder(r);
            rec.Step(5);
            int from = rec.Index;
            r.BeginPutAway(new Vector3(0f, 0f, 0.5f));
            RunPutAway(rec, 200);
            List<M5Rec> log = rec.Since(from);
            Assert.IsFalse(log.Exists(x => x.Act == RoutineActivity.Walking), "no walk within reach");
            Assert.AreEqual(1 + PutAwaySteps, log.Count, "straight into the beat (already facing it)");
        }

        [Test]
        public void A_seated_inhabitant_stands_up_first()
        {
            InhabitantRoutine r = RoutineFactory.Create(M5.Def(M5.SofaLoop()), null, StraightPlanner.Instance);
            var rec = new M5Recorder(r);
            rec.StepUntil(x => x.IsSitting, 2000, "sitting on the sofa");
            rec.Step(M5.SitSteps + 2);
            Assert.IsTrue(r.IsSitting && r.IsLowered, "premise: seated");
            int from = rec.Index;
            r.BeginPutAway(new Vector3(3f, 0f, 2f));
            RunPutAway(rec, 2000);
            List<M5Rec> log = rec.Since(from);
            int firstWalk = log.FindIndex(x => x.Act == RoutineActivity.Walking);
            int standUp = log.FindIndex(x => x.Act == RoutineActivity.StandingUp);
            Assert.Greater(standUp, 0, "it stood up");
            Assert.Greater(firstWalk, standUp, "the stand up comes before the walk");
            Assert.GreaterOrEqual(M5.CountBefore(log, standUp, RoutineActivity.Telegraph), M5.TelegraphSteps, "the stand up is telegraphed");
            Assert.IsFalse(r.IsSitting || r.IsLowered);
            M5.AssertTelegraphs(log, "a seated put-away");
        }

        [Test]
        public void The_walk_plans_with_the_investigate_planner()
        {
            foreach (bool withInvestigate in new[] { true, false })
            {
                var station = new M5.LPlanner(true);
                var investigate = new M5.LPlanner(false);
                InhabitantRoutine r = RoutineFactory.Create(M5.Def(Dwell()), null, station, withInvestigate ? investigate : null, null, 0,
                    RoutineFactory.AllAreas);
                var rec = new M5Recorder(r);
                rec.Step(5);
                int stationCalls = station.Calls;
                int from = rec.Index;
                var clue = new Vector3(3f, 0f, 2f);
                r.BeginPutAway(clue);
                RunPutAway(rec, 1000);
                List<M5Rec> log = rec.Since(from);
                // z first (the investigate planner): it walks up x = 0 before going along x; x first: along z = 0 first.
                bool zFirst = log.Exists(x => Mathf.Abs(x.Pos.x) < 1e-3f && x.Pos.z > 1f);
                bool xFirst = log.Exists(x => Mathf.Abs(x.Pos.z) < 1e-3f && x.Pos.x > 1f);
                if (withInvestigate)
                {
                    Assert.IsTrue(zFirst && !xFirst, "the put-away walk did not use InvestigatePlanner");
                    Assert.AreEqual(1, investigate.Calls, "one plan for the walk to the clue");
                    Assert.AreEqual(stationCalls, station.Calls, "the station planner planned the put-away");
                }
                else
                {
                    Assert.IsTrue(xFirst && !zFirst, "premise: without InvestigatePlanner it is the station planner");
                    Assert.AreEqual(stationCalls + 1, station.Calls);
                }
            }
        }

        [Test]
        public void The_dog_or_a_personality_without_memory_refuses_and_so_does_a_busy_routine()
        {
            var clue = new Vector3(3f, 0f, 0f);
            InhabitantRoutine dog = RoutineFactory.Create(M5.DefOf(PersonalityDef.Dog, Dwell()), null, StraightPlanner.Instance);
            PersonalityDef forgetful = PersonalityDef.For(PersonalityDef.Tidy);
            forgetful.Memory = false;
            InhabitantRoutine human = RoutineFactory.Create(M5.Def(Dwell()), null, StraightPlanner.Instance);
            human.Personality = forgetful;
            foreach (InhabitantRoutine r in new[] { dog, human })
            {
                r.Step(Dt);
                r.BeginPutAway(clue);
                Assert.AreEqual(InhabitantMode.Routine, r.Mode, "refused without memory");
                for (int i = 0; i < 300; i++)
                {
                    r.Step(Dt);
                    Assert.IsFalse(r.JustPutAway, "put away without memory");
                    Assert.AreNotEqual(RoutineActivity.PickingUp, r.LastActivity);
                }
            }

            // Busy: an investigation in progress is not replaced.
            InhabitantRoutine busy = RoutineFactory.Create(M5.Def(Dwell()), null, StraightPlanner.Instance);
            busy.Step(Dt);
            busy.Investigate(new Vector3(0f, 0f, 3f));
            Assert.AreEqual(InhabitantMode.Investigating, busy.Mode, "premise");
            busy.BeginPutAway(clue);
            bool reached = false;
            for (int i = 0; i < 1000 && !reached; i++)
            {
                busy.Step(Dt);
                Assert.IsFalse(busy.JustPutAway, "the put-away replaced the investigation");
                reached = busy.ReachedTarget;
            }
            Assert.IsTrue(reached, "the investigation went on");

            // Alerted accepts it, as an investigation does.
            InhabitantRoutine alerted = RoutineFactory.Create(M5.Def(Dwell()), null, StraightPlanner.Instance);
            alerted.Step(Dt);
            alerted.Alert(new Vector3(-3f, 0f, 0f), NoiseKind.Hop);
            Assert.AreEqual(InhabitantMode.Alerted, alerted.Mode, "premise");
            alerted.BeginPutAway(clue);
            Assert.AreEqual(InhabitantMode.Investigating, alerted.Mode, "an alerted inhabitant puts it away");
            int guard = 0;
            while (!alerted.JustPutAway)
            {
                Assert.Less(guard++, 1000, "never put away after an alert");
                alerted.Step(Dt);
            }
        }
    }
}
