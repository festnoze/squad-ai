using System.Collections.Generic;
using System.IO;
using System.Reflection;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// docs/CONTRACT_M4.md section 2 and amendments 9.5, 9.6: the body table. The chair row must equal the M1
    /// constants field by field (gate step 34): every public field of BodyDef is checked, so a new field cannot
    /// slip past the test.
    /// </summary>
    public sealed class CoreM4BodyTests
    {
        private const string Level1Path = "Assets/Resources/Levels/level1.json";

        /// <summary>The M1 chair: Tuning's M1 constants, and the size and model of the level 1 player.</summary>
        private static Dictionary<string, object> ChairRow()
        {
            SpawnDef m1 = LevelJson.Parse(File.ReadAllText(Level1Path)).Player;
            Assert.AreEqual("chair", m1.Kind, "premise: level 1 plays the M1 chair");
            Assert.AreEqual(Tuning.ChairControllerHeight, m1.SizeY, "premise: the M1 chair box is the controller height");
            return new Dictionary<string, object>
            {
                { "Kind", "chair" },
                { "Size", new Vector3(m1.SizeX, Tuning.ChairControllerHeight, m1.SizeZ) },
                { "Radius", Tuning.ChairControllerRadius },
                { "MaxSpeed", Tuning.ChairMaxSpeed },
                { "Accel", Tuning.ChairAcceleration },
                { "AccelHigh", Tuning.ChairAcceleration },
                { "StageSpeed", float.PositiveInfinity },
                { "TurnRate", Tuning.ChairTurnRate },
                { "CarryForward", Tuning.CarryForward },
                { "Glides", false },
                { "Tips", false },
                { "HasLight", false },
                { "IsSeat", true },
                { "Model", m1.Model },
            };
        }

        private static Dictionary<string, object> Row(string kind, Vector3 size, float radius, float max, float accel, float accelHigh,
            float stage, float turn, float carry, bool glides, bool tips, bool light, bool seat, string model)
        {
            return new Dictionary<string, object>
            {
                { "Kind", kind }, { "Size", size }, { "Radius", radius }, { "MaxSpeed", max }, { "Accel", accel },
                { "AccelHigh", accelHigh }, { "StageSpeed", stage }, { "TurnRate", turn }, { "CarryForward", carry },
                { "Glides", glides }, { "Tips", tips }, { "HasLight", light }, { "IsSeat", seat }, { "Model", model },
            };
        }

        /// <summary>
        /// The first field whose value differs from <paramref name="expected"/> (exact equality: Vector3.Equals and
        /// float.Equals are exact), or a field the expectation does not cover; null when everything matches.
        /// </summary>
        private static string FirstMismatch(BodyDef body, Dictionary<string, object> expected)
        {
            FieldInfo[] fields = typeof(BodyDef).GetFields(BindingFlags.Public | BindingFlags.Instance);
            if (fields.Length != expected.Count)
            {
                return $"BodyDef has {fields.Length} public fields, the row lists {expected.Count}";
            }
            foreach (FieldInfo f in fields)
            {
                if (!expected.TryGetValue(f.Name, out object want))
                {
                    return $"field {f.Name} is not covered by the row";
                }
                object got = f.GetValue(body);
                if (!Equals(want, got))
                {
                    return $"{body.Kind}.{f.Name} is {Show(got)}, expected {Show(want)}";
                }
            }
            return null;
        }

        private static string Show(object o) => o is Vector3 v ? $"({v.x:R}, {v.y:R}, {v.z:R})" : o is float f ? f.ToString("R") : o?.ToString() ?? "null";

        [Test]
        public void Chair_row_equals_the_M1_constants_field_by_field()
        {
            Dictionary<string, object> row = ChairRow();
            Assert.IsNull(FirstMismatch(BodyDef.For("chair"), row));

            // Premise: the comparison catches a change in any field.
            BodyDef changed = BodyDef.For("chair");
            changed.Radius += 0.01f;
            StringAssert.Contains("Radius", FirstMismatch(changed, row));
            changed = BodyDef.For("chair");
            changed.Size = new Vector3(changed.Size.x, changed.Size.y, changed.Size.z + 1e-4f);
            StringAssert.Contains("Size", FirstMismatch(changed, row));
            changed = BodyDef.For("chair");
            changed.StageSpeed = 2f;
            StringAssert.Contains("StageSpeed", FirstMismatch(changed, row));
        }

        [Test]
        public void For_null_or_unknown_is_the_chair_and_a_new_instance_on_every_call()
        {
            Dictionary<string, object> row = ChairRow();
            foreach (string kind in new[] { null, "", "wardrobe", "chair", "lamp" })
            {
                BodyDef a = BodyDef.For(kind);
                BodyDef b = BodyDef.For(kind);
                Assert.AreNotSame(a, b, $"'{kind}': the same instance twice");
                Assert.IsNull(FirstMismatch(a, row), $"'{kind}' is not the chair");
            }
            BodyDef mine = BodyDef.For(null);
            mine.MaxSpeed = 99f;
            mine.Size = Vector3.one;
            Assert.IsNull(FirstMismatch(BodyDef.For(null), row), "a caller's change leaked into the next instance");
            BodyDef stool = BodyDef.For("stool");
            stool.Tips = false;
            Assert.IsTrue(BodyDef.For("stool").Tips, "a caller's change leaked into the next stool");
        }

        [Test]
        public void Body_table_matches_the_contract()
        {
            var rows = new[]
            {
                Row("stool", new Vector3(0.35f, 0.55f, 0.35f), 0.22f, 2.4f, 14f, Tuning.StoolHighAccel, Tuning.StoolTellSpeed, 540f, 0.45f,
                    false, true, false, true, "kenney.stool"),
                Row("armchair", new Vector3(0.85f, 1.05f, 0.85f), 0.45f, 0.9f, 6f, 6f, float.PositiveInfinity, 200f, 0.65f,
                    false, false, false, true, "kenney.armchair"),
                Row("floor_lamp", new Vector3(0.35f, 1.80f, 0.35f), 0.22f, 0.6f, 4f, 4f, float.PositiveInfinity, 180f, 0.40f,
                    false, false, true, false, "kenney.floorlamp"),
                Row("office_chair", new Vector3(0.55f, 1.00f, 0.55f), 0.30f, 2.8f, 8f, 8f, float.PositiveInfinity, 360f, 0.65f,
                    true, false, false, true, null),
            };
            foreach (Dictionary<string, object> row in rows)
            {
                string kind = (string)row["Kind"];
                Assert.IsNull(FirstMismatch(BodyDef.For(kind), row), kind);
            }
            // CONTRACT_M4 10.3: the fast stage ends at the tell speed, 1.0 m/s; the climb to the unchanged 1.3 m/s tip
            // speed at 1.2 m/s2 is 0.25 s of visible tell. Careful mode stays below the tip speed.
            BodyDef s = BodyDef.For("stool");
            Assert.AreEqual(1.0f, s.StageSpeed, "the fast stage must end at the tell speed");
            Assert.AreEqual(1.2f, s.AccelHigh);
            Assert.AreEqual(1.3f, Tuning.StoolTipSpeed, "the tip speed is unchanged");
            Assert.AreEqual(0.25f, (Tuning.StoolTipSpeed - s.StageSpeed) / s.AccelHigh, 1e-4f, "the tell band is not 0.25 s");
            Assert.Less(s.StageSpeed, Tuning.StoolTipSpeed, "no tell before the tip");
            Assert.Less(s.MaxSpeed * Tuning.CarefulFactor, Tuning.StoolTipSpeed, "careful mode would tip the stool");
            Assert.Greater(s.MaxSpeed, Tuning.StoolTipSpeed, "premise: full speed is above the tip threshold");
        }
    }

    /// <summary>docs/CONTRACT_M4.md sections 2 and 6: MotionRule, CreakGauge, FurnitureMemory, GameRules, Hearing.</summary>
    public sealed class CoreM4RulesTests
    {
        private const float Dt = Tuning.FixedStep;
        private static readonly int GraceSteps = Mathf.RoundToInt(Tuning.DiscoveryGrace / Dt);
        private static readonly int DelaySteps = Mathf.RoundToInt(Tuning.CreakStartDelay / Dt);

        // ----- MotionRule -----

        [Test]
        public void An_action_in_progress_is_moving_whatever_the_speed_and_otherwise_nothing_changes()
        {
            Assert.IsTrue(MotionRule.IsMoving(0f, 0f, true), "a topple, a righting or a toggle is moving");
            Assert.IsFalse(MotionRule.IsMoving(0f, 0f, false));
            int moving = 0;
            int still = 0;
            foreach (float speed in new[] { 0f, 0.04f, Tuning.MovingSpeedThreshold, 0.051f, 1f })
            {
                foreach (float yawRate in new[] { 0f, 2.9f, Tuning.MovingYawRateThreshold, 3.1f, -5f })
                {
                    bool m1 = MotionRule.IsMoving(speed, yawRate);
                    Assert.AreEqual(m1, MotionRule.IsMoving(speed, yawRate, false), $"speed {speed}, yaw rate {yawRate}");
                    Assert.IsTrue(MotionRule.IsMoving(speed, yawRate, true), $"speed {speed}, yaw rate {yawRate}");
                    moving += m1 ? 1 : 0;
                    still += m1 ? 0 : 1;
                }
            }
            Assert.Greater(moving, 0, "premise: the sweep has moving cases");
            Assert.Greater(still, 0, "premise: the sweep has still cases");
        }

        // ----- CreakGauge -----

        [Test]
        public void Paused_gauge_freezes_like_carried_and_resumes_where_it_stopped()
        {
            var paused = new CreakGauge();
            var control = new CreakGauge();
            int step = 0;
            // Still from the level start until the gauge is in its warning zone (0.9).
            int fill = Mathf.RoundToInt(0.9f * Tuning.CreakFillTime / Dt);
            for (int i = 0; i < DelaySteps + fill; i++, step++)
            {
                Assert.IsFalse(paused.Step(Dt, false, false, step * Dt, false));
                Assert.IsFalse(control.Step(Dt, false, false, step * Dt));
            }
            Assert.AreEqual(0.9f, paused.Value, 1e-3f, "premise: filled to 0.9");
            Assert.IsTrue(paused.Warning, "premise: in the warning zone");
            float frozen = paused.Value;

            // Sat on for 40 s (twice a full fill), still or moving: nothing moves.
            var unpaused = new CreakGauge();
            for (int i = 0; i < DelaySteps + fill; i++)
            {
                unpaused.Step(Dt, false, false, i * Dt);
            }
            int unpausedCreaks = 0;
            for (int i = 0; i < 2000; i++, step++)
            {
                // One moving step in five: unpaused, the gauge still gains 0.002 every five steps.
                bool moving = i % 5 == 0;
                Assert.IsFalse(paused.Step(Dt, moving, false, step * Dt, true), $"creaked while sat on (step {i})");
                Assert.AreEqual(frozen, paused.Value, $"the gauge changed while sat on (step {i})");
                Assert.IsFalse(paused.Filling);
                Assert.IsFalse(paused.Warning, "warning while sat on");
                Assert.AreEqual(float.PositiveInfinity, paused.SecondsToCreak);
                unpausedCreaks += unpaused.Step(Dt, moving, false, step * Dt, false) ? 1 : 0;
            }
            Assert.Greater(unpausedCreaks, 0, "premise: the same 40 s unpaused creak");

            // Released: it fills on from 0.9, and creaks exactly when a gauge that never paused does.
            int pausedSteps = 0;
            while (!paused.Step(Dt, false, false, step * Dt, false))
            {
                Assert.IsTrue(paused.Warning, "the warning is back on the first fill step");
                Assert.Less(++pausedSteps, 1000, "never creaked after the release");
                step++;
            }
            int controlSteps = 0;
            while (!control.Step(Dt, false, false, (DelaySteps + fill + controlSteps) * Dt))
            {
                Assert.Less(++controlSteps, 1000);
            }
            Assert.AreEqual(controlSteps, pausedSteps, "the pause changed the time left to the creak");
        }

        [Test]
        public void Unpaused_overload_is_step_for_step_the_M2_gauge()
        {
            var rng = new System.Random(7);
            var m2 = new CreakGauge();
            var m4 = new CreakGauge();
            int creaks = 0;
            for (int i = 0; i < 6000; i++)
            {
                bool moving = rng.NextDouble() < 0.2;
                bool carried = rng.NextDouble() < 0.05;
                bool a = m2.Step(Dt, moving, carried, i * Dt);
                bool b = m4.Step(Dt, moving, carried, i * Dt, false);
                Assert.AreEqual(a, b, $"step {i}");
                Assert.AreEqual(m2.Value, m4.Value, $"step {i}");
                Assert.AreEqual(m2.Warning, m4.Warning, $"step {i}");
                creaks += a ? 1 : 0;
            }
            Assert.Greater(creaks, 0, "premise: the sequence creaks");
        }

        // ----- FurnitureMemory -----

        private static readonly FurniturePose Spawn = new FurniturePose(new Vector3(1f, 0f, 1f), 0f);
        private static readonly FurniturePose DecoyStool = new FurniturePose(new Vector3(3f, 0f, 1f), 0f);

        private static FurnitureMemory StoolMemory() =>
            new FurnitureMemory(Spawn, new[] { DecoyStool }, new[] { "stool" }, "stool");

        private static void AssertIncident(FurnitureMemory m, FurniturePose at, string context)
        {
            for (int i = 1; i < GraceSteps; i++)
            {
                Assert.AreEqual(Observation.Suspect, m.Observe(true, at, Dt, true), $"{context}: {i * Dt:0.00} s lying down");
            }
            Assert.AreEqual(Observation.Discovery, m.Observe(true, at, Dt, true), $"{context}: {GraceSteps * Dt:0.00} s lying down");
            for (int i = 0; i < 30; i++)
            {
                Assert.AreEqual(Observation.Suspect, m.Observe(true, at, Dt, true), $"{context}: after the discovery");
            }
        }

        [Test]
        public void A_stool_seen_lying_down_is_out_of_place_wherever_it_is()
        {
            FurnitureMemory m = StoolMemory();
            // Premises: standing, the same poses are in place and explained.
            Assert.AreEqual(Observation.Confirmed, m.Observe(true, Spawn, Dt, false));
            Assert.AreEqual(Observation.ExplainedByDecoy, m.Observe(true, DecoyStool, Dt, false));

            AssertIncident(m, Spawn, "on its own slot");
            Assert.AreEqual(Spawn.Position, m.PlayerSlot.Position, "a lying stool must not become the slot");
            Assert.AreEqual(Observation.NotSeen, m.Observe(false, Spawn, Dt, true), "not seen ends the incident");
            AssertIncident(m, DecoyStool, "next to a decoy of its kind");
            Assert.AreEqual(Observation.Confirmed, m.Observe(true, Spawn, Dt, false), "righted on its slot");
            AssertIncident(m, new FurniturePose(new Vector3(-2f, 0f, 0f), 90f), "far from everything");
        }

        [Test]
        public void Observe_standing_is_the_M2_observation_step_for_step()
        {
            var rng = new System.Random(11);
            FurnitureMemory m2 = StoolMemory();
            FurnitureMemory m4 = StoolMemory();
            var seen = new HashSet<Observation>();
            for (int i = 0; i < 4000; i++)
            {
                bool visible = rng.NextDouble() < 0.8;
                // Mostly long stays at one of three poses, so incidents last past the grace.
                int where = (i / 40 + (rng.NextDouble() < 0.05 ? 1 : 0)) % 3;
                FurniturePose p = where == 0 ? Spawn : where == 1 ? DecoyStool : new FurniturePose(new Vector3(-2f, 0f, -1f), 0f);
                Observation a = m2.Observe(visible, p, Dt);
                Observation b = m4.Observe(visible, p, Dt, false);
                Assert.AreEqual(a, b, $"step {i}");
                Assert.AreEqual(m2.PlayerSlot.Position, m4.PlayerSlot.Position, $"step {i}");
                seen.Add(a);
            }
            foreach (Observation o in new[] { Observation.NotSeen, Observation.Confirmed, Observation.ExplainedByDecoy, Observation.Suspect })
            {
                Assert.IsTrue(seen.Contains(o), "premise: never observed " + o);
            }
        }

        // ----- GameRules and Hearing -----

        [Test]
        public void M4_rules_are_M2_plus_bodies_sitting_and_lamp_a_new_instance_each_call()
        {
            GameRules a = GameRules.M4;
            GameRules b = GameRules.M4;
            Assert.AreNotSame(a, b);
            Assert.IsTrue(a.DisplacementMemory && a.Hearing && a.Creak && a.ExitOnlyUnseen);
            Assert.IsTrue(a.Bodies && a.Sitting && a.Lamp);
            a.Sitting = false;
            Assert.IsTrue(GameRules.M4.Sitting && b.Sitting, "a caller's change leaked");
            GameRules m2 = GameRules.M2;
            Assert.IsFalse(m2.Bodies || m2.Sitting || m2.Lamp, "M2 gained an M4 rule");
            GameRules m1 = GameRules.M1;
            Assert.IsFalse(m1.Bodies || m1.Sitting || m1.Lamp || m1.DisplacementMemory || m1.Hearing || m1.Creak);
        }

        [Test]
        public void Noise_radii_and_who_retargets()
        {
            Assert.AreEqual(Tuning.HopNoiseRadius, Hearing.RadiusOf(NoiseKind.Hop));
            Assert.AreEqual(Tuning.CreakRadius, Hearing.RadiusOf(NoiseKind.Creak));
            Assert.AreEqual(3.5f, Hearing.RadiusOf(NoiseKind.Topple));
            Assert.AreEqual(2.5f, Hearing.RadiusOf(NoiseKind.Click));
            Assert.AreEqual(1.2f, Hearing.RadiusOf(NoiseKind.Roll));
            foreach (NoiseKind k in new[] { NoiseKind.Hop, NoiseKind.Topple, NoiseKind.Click, NoiseKind.Roll })
            {
                Assert.IsFalse(Hearing.RetargetsAlerted(k), k + " retargets");
            }
            Assert.IsTrue(Hearing.RetargetsAlerted(NoiseKind.Creak));
            var e = new NoiseEvent(Vector3.zero, Hearing.RadiusOf(NoiseKind.Topple), NoiseKind.Topple);
            Assert.IsTrue(Hearing.Hears(new Vector3(3.5f, 1.6f, 0f), e));
            Assert.IsFalse(Hearing.Hears(new Vector3(3.6f, 1.6f, 0f), e));
        }
    }

    /// <summary>
    /// docs/CONTRACT_M4.md section 3 and amendments 9.2, 9.3: sitting on a prop, on the player, the pratfall, the
    /// switch on, the per body carry, the rule switch, and the telegraph invariant extended to every new mode.
    /// Every scenario asserts its premise, so it cannot pass on nothing.
    /// </summary>
    public sealed class CoreM4RoutineTests
    {
        private const float Dt = Tuning.FixedStep;
        private static readonly int TelegraphSteps = Mathf.RoundToInt(Tuning.TelegraphDuration / Dt);
        private static readonly int SitSteps = Mathf.RoundToInt(Tuning.SitEyeRiseTime / Dt);
        private static readonly int PratfallSteps = Mathf.RoundToInt(Tuning.PratfallTime / Dt);
        private static readonly int SwitchSteps = Mathf.RoundToInt(Tuning.LampSwitchOnTime / Dt);
        private static readonly int LookSteps = Mathf.RoundToInt(Tuning.AlertLookDuration / Dt);

        // ----- Fixtures -----

        private static GlanceDef Glance(float offset, float yaw, float hold) => new GlanceDef { Offset = offset, Yaw = yaw, Hold = hold };

        private static StationDef Plain(float x, float z, float facing, float dwell, params GlanceDef[] glances)
        {
            var s = new StationDef { X = x, Z = z, Facing = facing, Dwell = dwell };
            s.Glances.AddRange(glances);
            return s;
        }

        private static StationDef OnProp(float x, float z, float facing, float dwell, string prop, params GlanceDef[] glances)
        {
            StationDef s = Plain(x, z, facing, dwell, glances);
            s.Sit = prop;
            return s;
        }

        private static StationDef OnPlayer(float x, float z, float facing, float dwell, float seatX, float seatZ, float seatYaw)
        {
            StationDef s = Plain(x, z, facing, dwell);
            s.Sit = InhabitantRoutine.PlayerSeat;
            s.Seat = new SeatDef { X = seatX, Z = seatZ, Yaw = seatYaw };
            return s;
        }

        /// <summary>
        /// A plain station, then a sofa seat reached with a 90 deg back turn, with one glance while seated. Read with
        /// LevelJson, like a real level, so the seat is resolved by LevelDef.ResolveSeats: the sofa center, 0.6 m
        /// behind the seat front (CONTRACT_M4 10.2).
        /// </summary>
        private const string PropLevelJson = @"{
  ""id"": ""core_m4_prop_sit"",
  ""props"": [ { ""name"": ""Sofa"", ""kind"": ""sofa"", ""x"": 0.0, ""z"": -0.6, ""yaw"": 0.0, ""sizeX"": 1.8, ""sizeY"": 0.8, ""sizeZ"": 0.8 } ],
  ""inhabitants"": [ {
    ""name"": ""Habitant"",
    ""startStation"": 0,
    ""stations"": [
      { ""x"": 3.0, ""z"": 0.0, ""facing"": 90.0, ""dwell"": 1.0 },
      { ""x"": 0.0, ""z"": 0.0, ""facing"": 0.0, ""dwell"": 2.0, ""sit"": ""Sofa"", ""glances"": [ { ""offset"": 0.5, ""yaw"": 60.0, ""hold"": 0.3 } ] }
    ]
  } ]
}";

        private static readonly Vector3 SofaCenter = new Vector3(0f, 0f, -0.6f);

        private static List<StationDef> PropLoop() => LevelJson.Parse(PropLevelJson).Inhabitants[0].Stations;

        /// <summary>Resolves the prop seats of hand-made stations against <paramref name="props"/>, as a real level does.</summary>
        private static List<StationDef> Resolved(List<StationDef> stations, params PropDef[] props)
        {
            var level = new LevelDef();
            level.Props.AddRange(props);
            level.Inhabitants.Add(new InhabitantDef { Name = "Habitant", Stations = stations });
            level.ResolveSeats();
            return stations;
        }

        private static PropDef Sofa(string name, float x, float z) =>
            new PropDef { Name = name, Kind = "sofa", X = x, Z = z, SizeX = 1.8f, SizeY = 0.8f, SizeZ = 0.8f };

        /// <summary>The largest slide from a seat front to its seat home that a valid level allows (CONTRACT_M4 10.2).</summary>
        private const float MaxSlide = 0.8f;

        /// <summary>A plain station, then the player's seat at the origin (facing +z), its front 0.5 m ahead of it.</summary>
        private static List<StationDef> PlayerLoop() => new List<StationDef>
        {
            Plain(3f, 0f, 90f, 1f),
            OnPlayer(0f, 0.5f, 0f, 2f, 0f, 0f, 0f),
        };

        private static readonly Vector3 PlayerSeatHome = Vector3.zero;

        private static List<StationDef> TwoPlain() => new List<StationDef>
        {
            Plain(0f, 0f, 0f, 3f),
            Plain(4f, 3f, 90f, 3f),
        };

        /// <summary>The stations of level 1 (a copy, so these tests do not depend on the level file).</summary>
        private static List<StationDef> Level1() => new List<StationDef>
        {
            Plain(-1.5f, 2.2f, 0f, 6f, Glance(3f, -70f, 1f)),
            Plain(1.2f, 1.4f, 180f, 3f, Glance(1f, 60f, 0.8f)),
            Plain(0f, -2.3f, 180f, 5f),
            Plain(2.2f, -0.7f, 180f, 4f, Glance(2f, -80f, 1f)),
        };

        /// <summary>
        /// Level 1's loop with a sofa seat (its center 0.6 m behind the sitter, resolved) and the player's seat (0.5 m
        /// behind the sitter, facing 180).
        /// </summary>
        private static List<StationDef> Mixed() => Resolved(new List<StationDef>
        {
            Plain(-1.5f, 2.2f, 0f, 3f, Glance(1f, -70f, 1f)),
            OnProp(1.2f, 1.4f, 180f, 2.5f, "sofa", Glance(0.5f, 60f, 0.5f)),
            OnPlayer(0f, -2.3f, 180f, 2f, 0f, -1.8f, 180f),
            Plain(2.2f, -0.7f, 180f, 2f, Glance(2f, -80f, 1f)),
        }, Sofa("sofa", 1.2f, 2.0f));

        /// <summary>Along x first, then along z.</summary>
        private sealed class LPlanner : IPathPlanner
        {
            public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
            {
                corners.Clear();
                Vector3 a = YawMath.Planar(from);
                Vector3 b = YawMath.Planar(to);
                var corner = new Vector3(b.x, 0f, a.z);
                if ((corner - a).sqrMagnitude > 1e-6f && (corner - b).sqrMagnitude > 1e-6f)
                {
                    corners.Add(corner);
                }
                corners.Add(b);
                return true;
            }
        }

        // ----- Recording -----

        private struct Rec
        {
            public Vector3 Pos;
            public float Body;
            public float Head;
            public float Eye;
            public Vector3 EyePos;
            public RoutineActivity Act;
            public InhabitantMode Mode;
            public bool Sitting;
            public bool OnPlayer;
            public bool JustSat;
            public SitResult Result;
            public bool Lowered;
            public bool Targets;
            public FurniturePose SeatHome;
            public bool SwitchedOn;
            public bool Reached;
            public bool InDwell;
            public bool Carrying;
            public bool PutDown;
            public int Station;
            public int Telegraphs;
            public Vector3 Anchor;
        }

        private static Rec Snap(InhabitantRoutine r) => new Rec
        {
            Pos = r.Position,
            Body = r.BodyYaw,
            Head = r.HeadYaw,
            Eye = r.EyeHeight,
            EyePos = r.EyePosition,
            Act = r.LastActivity,
            Mode = r.Mode,
            Sitting = r.IsSitting,
            OnPlayer = r.SittingOnPlayer,
            JustSat = r.JustSat,
            Result = r.LastSitResult,
            Lowered = r.IsLowered,
            Targets = r.SitTargetsPlayer,
            SeatHome = r.SeatHome,
            SwitchedOn = r.JustSwitchedOn,
            Reached = r.ReachedTarget,
            InDwell = r.InDwell,
            Carrying = r.IsCarrying,
            PutDown = r.JustPutDown,
            Station = r.StationIndex,
            Telegraphs = r.TelegraphCount,
            Anchor = r.CarryAnchor,
        };

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
            public int Index => Log.Count - 1;

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

            public List<Rec> Since(int index) => Log.GetRange(index, Log.Count - index);
        }

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

        private static int CountBefore(List<Rec> s, int index, RoutineActivity act)
        {
            int n = 0;
            for (int k = index - 1; k >= 0 && s[k].Act == act; k--)
            {
                n++;
            }
            return n;
        }

        private static Vector3 SourceAtEye(InhabitantRoutine r, float relativeYaw, float distance) =>
            r.Position + YawMath.Forward(r.EyeYaw + relativeYaw) * distance;

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(YawMath.Planar(to - from));

        // ----- The telegraph analyzer, extended to M4 -----

        /// <summary>
        /// The analyzer of RoutineM2Tests (yaw changes only during turns, every turn segment over 30 deg right after
        /// at least 0.6 s of telegraph, the head within its limit), extended to M4: motion only while walking,
        /// carrying or standing up, or while sitting down or falling on a step where the eye goes down too (the slide
        /// of CONTRACT_M4 10.2: no jump is whitelisted, and a sit or stand slide moves at most 0.8 m over 0.5 s); no
        /// body turn while lowered (a seated look is head only); the eye lowers only while sitting down or falling,
        /// rises only while standing up, and every stand up comes right after a full telegraph; never walking,
        /// carrying or switching on while lowered; seated with the eye down means on the seat home, and the pin flag
        /// means seated.
        /// Returns the first violation (null when none) and the number of turns over 30 deg.
        /// </summary>
        private static string FindViolation(List<Rec> s, out int large)
        {
            large = 0;
            for (int i = 1; i < s.Count; i++)
            {
                Rec a = s[i - 1];
                Rec b = s[i];
                if (b.Act == RoutineActivity.Startled)
                {
                    break;
                }
                float db = Mathf.Abs(Mathf.DeltaAngle(a.Body, b.Body));
                float dh = Mathf.Abs(Mathf.DeltaAngle(a.Head, b.Head));
                if (db >= 1e-3f && b.Act != RoutineActivity.TurningBody)
                {
                    return $"body yaw changed during {b.Act} at record {i}";
                }
                if (dh >= 1e-3f && !IsTurning(b.Act))
                {
                    return $"head yaw changed during {b.Act} at record {i}";
                }
                if (db >= 1e-3f && a.Lowered && b.Lowered)
                {
                    return $"body turned while lowered at record {i}";
                }
                float step = (b.Pos - a.Pos).magnitude;
                bool moved = step > 1e-6f;
                bool sitSlide = (b.Act == RoutineActivity.Sitting || b.Act == RoutineActivity.Pratfall) && b.Eye < a.Eye - 1e-5f;
                if (moved && b.Act != RoutineActivity.Walking && b.Act != RoutineActivity.Carrying && b.Act != RoutineActivity.StandingUp && !sitSlide)
                {
                    return $"moved during {b.Act} at record {i}";
                }
                if ((sitSlide || b.Act == RoutineActivity.StandingUp) && step > MaxSlide / SitSteps + 1e-4f)
                {
                    return $"slid {step:0.000} m in one step during {b.Act} at record {i} (at most {MaxSlide} m over {Tuning.SitEyeRiseTime} s)";
                }
                if (Mathf.Abs(b.Head) > Tuning.HeadYawLimit + 1e-3f)
                {
                    return $"head beyond its limit at record {i}";
                }
                if (Mathf.Abs(b.EyePos.y - b.Eye) > 1e-5f)
                {
                    return $"EyePosition does not use EyeHeight at record {i}";
                }
                if (b.Eye < Tuning.EyeHeight - 1e-4f && !b.Lowered)
                {
                    return $"eye low while not lowered at record {i}";
                }
                if (b.Eye > a.Eye + 1e-5f && b.Act != RoutineActivity.StandingUp)
                {
                    return $"eye rose during {b.Act} at record {i}";
                }
                if (b.Eye < a.Eye - 1e-5f && b.Act != RoutineActivity.Sitting && b.Act != RoutineActivity.Pratfall)
                {
                    return $"eye lowered during {b.Act} at record {i}";
                }
                if (b.Lowered && (b.Act == RoutineActivity.Walking || b.Act == RoutineActivity.Carrying || b.Act == RoutineActivity.PickingUp
                                  || b.Act == RoutineActivity.PuttingDown || b.Act == RoutineActivity.SwitchingOn))
                {
                    return $"{b.Act} while lowered at record {i}";
                }
                if (b.OnPlayer && !b.Sitting)
                {
                    return $"pin flag without sitting at record {i}";
                }
                if (b.Sitting && b.Eye <= Tuning.SitEyeHeight + 1e-5f
                    && (YawMath.Planar(b.Pos) - YawMath.Planar(b.SeatHome.Position)).sqrMagnitude > 1e-10f)
                {
                    return $"seated away from the seat home at record {i}";
                }
                if (b.Act == RoutineActivity.StandingUp && a.Act != RoutineActivity.StandingUp)
                {
                    int tele = CountBefore(s, i, RoutineActivity.Telegraph);
                    if (tele < TelegraphSteps)
                    {
                        return $"stand up at record {i} was preceded by only {tele * Dt:0.00} s of telegraph";
                    }
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
                    int tele = CountBefore(s, start, RoutineActivity.Telegraph);
                    if (tele * Dt < Tuning.TelegraphDuration - 1e-3f)
                    {
                        return $"{label} turn of {total:0.0} deg at record {start} was preceded by only {tele * Dt:0.00} s of telegraph";
                    }
                }
            }
            return null;
        }

        private static int AssertTelegraphs(List<Rec> s, string context)
        {
            string violation = FindViolation(s, out int large);
            Assert.IsNull(violation, context + ": " + violation);
            return large;
        }

        /// <summary>A clean sit on a seat 0.5 m behind, with <paramref name="telegraph"/> steps before the stand up.</summary>
        private static List<Rec> SyntheticSit(int telegraph)
        {
            var stand = new Vector3(0f, 0f, 0.5f);
            var seat = new FurniturePose(Vector3.zero, 0f);
            var s = new List<Rec>();
            Rec r = new Rec { Pos = stand, Eye = Tuning.EyeHeight, Act = RoutineActivity.Idle, SeatHome = seat };
            r.EyePos = r.Pos + Vector3.up * r.Eye;
            s.Add(r);
            for (int i = 1; i <= SitSteps; i++)
            {
                float t = (float)i / SitSteps;
                r = new Rec
                {
                    Pos = Vector3.Lerp(stand, seat.Position, t), Eye = Mathf.Lerp(Tuning.EyeHeight, Tuning.SitEyeHeight, t),
                    Act = RoutineActivity.Sitting, Sitting = true, Lowered = true, JustSat = i == 1, SeatHome = seat,
                };
                r.EyePos = r.Pos + Vector3.up * r.Eye;
                s.Add(r);
            }
            for (int i = 0; i < telegraph; i++)
            {
                r.Act = RoutineActivity.Telegraph;
                r.JustSat = false;
                s.Add(r);
            }
            for (int i = 1; i <= SitSteps; i++)
            {
                float t = (float)i / SitSteps;
                r = new Rec
                {
                    Pos = Vector3.Lerp(seat.Position, stand, t), Eye = Mathf.Lerp(Tuning.SitEyeHeight, Tuning.EyeHeight, t),
                    Act = RoutineActivity.StandingUp, Lowered = i < SitSteps, SeatHome = seat,
                };
                r.EyePos = r.Pos + Vector3.up * r.Eye;
                s.Add(r);
            }
            return s;
        }

        [Test]
        public void Analyzer_premise_catches_a_sit_jump_an_untelegraphed_stand_up_a_seated_body_turn_and_a_slide_while_seated()
        {
            // Records: 0 standing, 1 to SitSteps the sit down slide, then the stand up telegraph, then the stand up.
            int seated = SitSteps + 3;
            Assert.IsNull(FindViolation(SyntheticSit(TelegraphSteps), out _), "the clean sit");
            StringAssert.Contains("stand up", FindViolation(SyntheticSit(TelegraphSteps - 1), out _));

            // The M4 behavior that 10.2 removed: the body jumps onto the seat home at the moment of sitting.
            List<Rec> jump = SyntheticSit(TelegraphSteps);
            for (int i = 1; i <= SitSteps; i++)
            {
                Rec j = jump[i];
                j.Pos = j.SeatHome.Position;
                j.EyePos = j.Pos + Vector3.up * j.Eye;
                jump[i] = j;
            }
            StringAssert.Contains("in one step during Sitting", FindViolation(jump, out _));

            // A slide longer than 0.8 m over 0.5 s.
            List<Rec> far = SyntheticSit(TelegraphSteps);
            for (int i = 0; i <= SitSteps; i++)
            {
                Rec f = far[i];
                f.Pos = Vector3.Lerp(new Vector3(0f, 0f, MaxSlide + 0.1f), f.SeatHome.Position, (float)i / SitSteps);
                f.EyePos = f.Pos + Vector3.up * f.Eye;
                far[i] = f;
            }
            StringAssert.Contains("in one step during Sitting", FindViolation(far, out _));

            List<Rec> turned = SyntheticSit(TelegraphSteps);
            Rec t = turned[5];
            t.Act = RoutineActivity.TurningBody;
            t.Body = 10f;
            turned[5] = t;
            StringAssert.Contains("while lowered", FindViolation(turned, out _));

            List<Rec> slid = SyntheticSit(TelegraphSteps);
            Rec m = slid[seated];
            m.Pos += new Vector3(0.01f, 0f, 0f);
            m.EyePos = m.Pos + Vector3.up * m.Eye;
            slid[seated] = m;
            StringAssert.Contains("moved during Telegraph", FindViolation(slid, out _));

            List<Rec> walked = SyntheticSit(TelegraphSteps);
            Rec w = walked[seated];
            w.Act = RoutineActivity.Walking;
            walked[seated] = w;
            StringAssert.Contains("Walking while lowered", FindViolation(walked, out _));
        }

        /// <summary>
        /// CONTRACT_M4 10.2: from the moment of sitting (record <paramref name="sat"/>), over SitSteps records, the body
        /// slides from <paramref name="stand"/> to <paramref name="seat"/> with the same interpolation as the eye, so
        /// the rule eye never jumps; on the last of them it is on the seat home with the eye down. Returns the length.
        /// </summary>
        private static float AssertSlide(Recorder rec, int sat, Vector3 stand, Vector3 seat, string context)
        {
            Assert.GreaterOrEqual(rec.Log.Count, sat + SitSteps, context + ": premise: the sit down was recorded");
            float length = YawMath.Planar(seat - stand).magnitude;
            Assert.AreEqual(YawMath.Planar(stand), YawMath.Planar(rec.Log[sat - 1].Pos), context + ": premise: it stood at the seat front");
            for (int k = 0; k < SitSteps; k++)
            {
                Rec x = rec.Log[sat + k];
                float t = (k + 1f) / SitSteps;
                Assert.AreEqual(Mathf.Lerp(Tuning.EyeHeight, Tuning.SitEyeHeight, t), x.Eye, 1e-4f, $"{context}: eye at sit step {k}");
                Assert.AreEqual(x.Eye, x.EyePos.y, 1e-5f, context + ": EyePosition must use EyeHeight");
                Vector3 expected = Vector3.Lerp(YawMath.Planar(stand), YawMath.Planar(seat), t);
                Assert.Less((YawMath.Planar(x.Pos) - expected).magnitude, 1e-4f, $"{context}: the body is not where the slide puts it at sit step {k}");
                float step = (rec.Log[sat + k].Pos - rec.Log[sat + k - 1].Pos).magnitude;
                Assert.LessOrEqual(step, length / SitSteps + 1e-4f, $"{context}: jumped {step:0.000} m at sit step {k}");
            }
            Rec down = rec.Log[sat + SitSteps - 1];
            Assert.AreEqual(Tuning.SitEyeHeight, down.Eye, context + ": the eye is not down at the end of the sit down");
            Assert.Less((YawMath.Planar(down.Pos) - YawMath.Planar(seat)).magnitude, 1e-5f, context + ": not on the seat home at the end of the sit down");
            Assert.Greater(rec.Log[sat + SitSteps - 2].Eye, Tuning.SitEyeHeight + 1e-3f, context + ": lowered too early");
            return length;
        }

        // ----- Sitting on a prop (gate step 31) -----

        [Test]
        public void Sitting_on_a_prop_lowers_the_eye_holds_the_dwell_seated_and_stands_up_after_a_telegraph()
        {
            List<StationDef> stations = PropLoop();
            StationDef seat = stations[1];
            Assert.IsTrue(seat.PropSeat.HasValue, "premise: LevelJson resolved the prop seat");
            Assert.AreEqual(SofaCenter, seat.PropSeat.Value.Position, "premise: ResolveSeats gives the sofa center");
            float slide = YawMath.Planar(seat.Position - SofaCenter).magnitude;
            Assert.That(slide, Is.InRange(0.3f, MaxSlide), "premise: a valid seat front, 0.3 to 0.8 m from the prop center");
            var rec = new Recorder(new InhabitantRoutine(stations, 0));
            InhabitantRoutine r = rec.R;
            rec.StepUntil(x => x.JustSat, 3000, "the moment of sitting");
            int sat = rec.Index;

            // Premise: the back turn right before sitting was a large, telegraphed turn.
            Assert.AreEqual(RoutineActivity.TurningBody, rec.Log[sat - 1].Act, "premise: the back turn ends right before sitting");
            int turnStart = sat - 1;
            while (rec.Log[turnStart - 1].Act == RoutineActivity.TurningBody)
            {
                turnStart--;
            }
            Assert.AreEqual(90f, Mathf.Abs(Mathf.DeltaAngle(rec.Log[turnStart - 1].Body, rec.Log[sat - 1].Body)), 1e-2f, "premise: a 90 deg back turn");
            Assert.GreaterOrEqual(CountBefore(rec.Log, turnStart, RoutineActivity.Telegraph), TelegraphSteps, "the back turn was not telegraphed");

            Assert.AreEqual(SitResult.OnProp, r.LastSitResult);
            Assert.IsTrue(r.IsSitting);
            Assert.IsFalse(r.SittingOnPlayer, "a prop is not the player");
            Assert.AreEqual(RoutineActivity.Sitting, r.LastActivity);
            Assert.AreEqual(SofaCenter, r.SeatHome.Position, "the seat home of a prop is the prop center (CONTRACT_M4 10.2)");
            Assert.AreEqual(seat.Facing, r.SeatHome.Yaw, "facing the station's facing");
            Assert.AreEqual(0f, Mathf.DeltaAngle(seat.Facing, r.BodyYaw), 1e-3f, "seated facing the station facing");
            Assert.Less(YawMath.Planar(r.Position - seat.Position).magnitude, slide / SitSteps + 1e-4f, "jumped at the moment of sitting");

            // The body slides onto the sofa center while the eye lowers, over SitEyeRiseTime, exactly.
            rec.Step(SitSteps - 1);
            AssertSlide(rec, sat, seat.Position, SofaCenter, "prop sit");

            rec.StepUntil(x => !x.IsSitting, 1000, "the end of the sitting");
            int up = rec.Index;
            List<Rec> seated = rec.Log.GetRange(sat, up - sat);
            Assert.IsTrue(seated.TrueForAll(x => x.Sitting), "IsSitting dropped while seated");
            Assert.IsTrue(seated.GetRange(SitSteps - 1, seated.Count - SitSteps + 1).TrueForAll(x => x.Pos == SofaCenter), "left the seat while seated");
            Assert.IsTrue(seated.GetRange(SitSteps, seated.Count - SitSteps).TrueForAll(x => x.Eye == Tuning.SitEyeHeight), "the seated eye moved");
            Assert.IsTrue(seated.Exists(x => Mathf.Abs(x.Head - 60f) < 1e-3f), "the glance did not play while seated");
            Assert.IsTrue(seated.Exists(x => x.Act == RoutineActivity.Sitting && x.Head == 0f && !x.JustSat), "the seated waits read as Sitting");
            Assert.GreaterOrEqual(seated.Count, SitSteps + Mathf.RoundToInt(seat.Dwell / Dt) + TelegraphSteps, "the seated dwell is too short");

            // Standing up: a full telegraph while still seated (one "hm ?"), then the eye rises over SitEyeRiseTime.
            Assert.AreEqual(RoutineActivity.StandingUp, rec.Last.Act);
            Assert.AreEqual(TelegraphSteps, CountBefore(rec.Log, up, RoutineActivity.Telegraph), "standing up is not telegraphed");
            Assert.AreEqual(rec.Log[up - TelegraphSteps - 1].Telegraphs + 1, rec.Log[up - TelegraphSteps].Telegraphs, "the stand up telegraph did not count");
            rec.Step(SitSteps - 1);
            List<Rec> rise = rec.Log.GetRange(up, SitSteps);
            Assert.IsTrue(rise.TrueForAll(x => x.Act == RoutineActivity.StandingUp), "the stand up is not SitEyeRiseTime long");
            for (int k = 1; k < SitSteps; k++)
            {
                Assert.Greater(rise[k].Eye, rise[k - 1].Eye, "the eye does not rise steadily");
            }
            Assert.AreEqual(Tuning.EyeHeight, r.EyeHeight);
            Assert.IsFalse(r.IsLowered);
            Assert.AreEqual(seat.Position, r.Position, "stood up back at the seat front");
            rec.Step();
            Assert.AreNotEqual(RoutineActivity.StandingUp, r.LastActivity, "the stand up is longer than SitEyeRiseTime");

            rec.StepUntil(x => x.LoopsCompleted >= 1, 5000, "a full loop");
            Assert.AreEqual(1, rec.Log.FindAll(x => x.JustSat).Count, "JustSat must be true on exactly one step per sit");
            Assert.GreaterOrEqual(AssertTelegraphs(rec.Log, "prop sit"), 3);
        }

        // ----- Sitting on the player (gate step 32) -----

        [TestCase(true)]
        [TestCase(false)]
        public void Sit_on_the_player_when_occupied_pins_for_the_dwell_and_releases_on_the_first_stand_up_step(bool hook)
        {
            List<StationDef> stations = PlayerLoop();
            var rec = new Recorder(new InhabitantRoutine(stations, 0));
            InhabitantRoutine r = rec.R;
            int calls = 0;
            if (hook)
            {
                r.SeatOccupied = () =>
                {
                    calls++;
                    return true;
                };
            }
            Assert.IsFalse(r.SitTargetsPlayer, "premise: not on the way to the seat before the start");
            rec.StepUntil(x => x.SitTargetsPlayer, 2000, "the approach");
            int approach = rec.Index;
            Assert.IsTrue(rec.Log[approach - 1].InDwell && rec.Log[approach - 1].Station == 0, "the approach must start with the walk from station 0");
            Assert.IsFalse(rec.Last.InDwell);
            Assert.AreEqual(PlayerSeatHome, r.SeatHome.Position, "the seat ghost needs the seat home from the start of the walk");

            // An alert on the way does not end the approach.
            rec.Step(40);
            r.Alert(SourceAtEye(r, 120f, 2f), NoiseKind.Hop);
            Assert.AreEqual(InhabitantMode.Alerted, r.Mode, "premise: alerted on the way");
            rec.StepUntil(x => x.JustSat, 3000, "the moment of sitting");
            int sat = rec.Index;
            List<Rec> way = rec.Log.GetRange(approach, sat - approach);
            Assert.IsTrue(way.Exists(x => x.Mode == InhabitantMode.Alerted), "premise: the alert happened");
            Assert.IsTrue(way.TrueForAll(x => x.Targets && x.SeatHome.Position == PlayerSeatHome), "SitTargetsPlayer dropped during the approach");
            if (hook)
            {
                Assert.AreEqual(1, calls, "the seat is checked once, at the moment of sitting");
            }

            Assert.AreEqual(SitResult.OnPlayer, r.LastSitResult);
            Assert.IsTrue(r.SittingOnPlayer);
            Assert.IsTrue(r.IsSitting);
            Assert.IsFalse(r.SitTargetsPlayer, "the approach is over once seated");
            Assert.AreEqual(stations[1].Position, rec.Log[sat - 1].Pos, "premise: it stood at the seat front");
            rec.Step(SitSteps - 1);
            AssertSlide(rec, sat, stations[1].Position, PlayerSeatHome, "sit on the player");

            rec.StepUntil(x => x.LastActivity == RoutineActivity.StandingUp, 1000, "the stand up");
            int up = rec.Index;
            for (int i = sat; i < up; i++)
            {
                Assert.IsTrue(rec.Log[i].OnPlayer, $"the pin dropped before the stand up (record {i - sat} of the sitting)");
            }
            Assert.AreEqual(TelegraphSteps, CountBefore(rec.Log, up, RoutineActivity.Telegraph), "standing up is not telegraphed");
            Assert.IsFalse(rec.Last.OnPlayer, "the pin must release on the first stand up step");
            Assert.IsFalse(rec.Last.Sitting);
            rec.StepUntil(x => !x.IsLowered, 100, "standing");
            Assert.AreEqual(stations[1].Position, r.Position, "stood up back at the seat front");
            rec.StepUntil(x => x.LoopsCompleted >= 1, 5000, "the loop");
            Assert.AreEqual(1, rec.Log.FindAll(x => x.JustSat).Count, "JustSat must be true on exactly one step");
            Assert.IsFalse(rec.Since(up).Exists(x => x.OnPlayer), "the pin came back");
            if (hook)
            {
                Assert.AreEqual(1, calls, "the seat was checked again outside the moment of sitting");
            }
            AssertTelegraphs(rec.Log, "sit on the player");
        }

        // ----- The pratfall (gate step 33) -----

        /// <summary>
        /// <paramref name="pulledAway"/>: the chair is home during the walk and pulled away during the back turn (a
        /// pratfall). Otherwise the chair is away during the walk and pushed back in time during the back turn (a
        /// sit on the player). Either way the check happens at the moment of sitting, after the back turn.
        /// </summary>
        [TestCase(true)]
        [TestCase(false)]
        public void The_seat_check_happens_at_the_moment_of_sitting_after_the_back_turn(bool pulledAway)
        {
            List<StationDef> stations = PlayerLoop();
            var rec = new Recorder(new InhabitantRoutine(stations, 0));
            InhabitantRoutine r = rec.R;
            bool home = pulledAway;
            int calls = 0;
            r.SeatOccupied = () =>
            {
                calls++;
                return home;
            };
            rec.StepUntil(x => x.Position == stations[1].Position && x.LastActivity == RoutineActivity.Telegraph, 3000, "the back turn");
            Assert.AreEqual(0, calls, "premise: not checked before the back turn");
            home = !pulledAway;
            rec.StepUntil(x => x.JustSat, 500, "the moment of sitting");
            Assert.AreEqual(1, calls);
            Assert.AreEqual(pulledAway ? SitResult.Pratfall : SitResult.OnPlayer, r.LastSitResult);
            AssertTelegraphs(rec.Log, "seat check");
        }

        [Test]
        public void Empty_seat_is_a_pratfall_then_a_telegraphed_stand_up_then_an_alerted_look_at_the_seat_then_the_routine()
        {
            List<StationDef> stations = PlayerLoop();
            var rec = new Recorder(new InhabitantRoutine(stations, 0));
            InhabitantRoutine r = rec.R;
            r.SeatOccupied = () => false;
            rec.StepUntil(x => x.JustSat, 3000, "the moment of sitting");
            int fall = rec.Index;
            Assert.AreEqual(SitResult.Pratfall, r.LastSitResult);
            Assert.IsFalse(r.IsSitting, "sat on nothing");
            Assert.IsFalse(r.SittingOnPlayer);
            Assert.IsTrue(r.IsLowered);
            Assert.AreEqual(RoutineActivity.Pratfall, r.LastActivity);

            rec.StepUntil(x => x.Mode == InhabitantMode.Alerted, 1000, "the look");
            AssertSlide(rec, fall, stations[1].Position, PlayerSeatHome, "pratfall");
            List<Rec> s = rec.Log;
            int i = fall;
            Assert.AreEqual(PratfallSteps, CountLeading(s, i, RoutineActivity.Pratfall), "the fall is not PratfallTime long");
            Assert.IsTrue(s.GetRange(fall + SitSteps - 1, PratfallSteps - SitSteps + 1).TrueForAll(x => x.Pos == PlayerSeatHome),
                "the fall does not end where the seat should be");
            Assert.AreEqual(Tuning.SitEyeHeight, s[i + PratfallSteps - 1].Eye, 1e-4f, "the eye did not go down in the fall");
            i += PratfallSteps;
            Assert.AreEqual(TelegraphSteps, CountLeading(s, i, RoutineActivity.Telegraph), "standing back up is not telegraphed");
            i += TelegraphSteps;
            Assert.AreEqual(SitSteps, CountLeading(s, i, RoutineActivity.StandingUp), "the stand up is not SitEyeRiseTime long");
            i += SitSteps;
            Assert.AreEqual(stations[1].Position, s[i - 1].Pos, "stood back up at the seat front");
            Assert.AreEqual(Tuning.EyeHeight, s[i - 1].Eye);
            Assert.AreEqual(PlayerSeatHome, r.AlertSource, "the look is aimed at the seat");

            rec.StepUntil(x => x.LastActivity == RoutineActivity.Looking, 500, "the hold");
            int hold = rec.Index;
            Assert.AreEqual(0f, Mathf.DeltaAngle(r.EyeYaw, YawToward(r.Position, PlayerSeatHome)), 1e-2f, "not looking at the seat");
            Assert.Greater(Mathf.Abs(Mathf.DeltaAngle(r.BodyYaw, stations[1].Facing)), 30f, "premise: the seat is behind, a large look turn");
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 1000, "the end of the look");
            Assert.AreEqual(LookSteps, CountLeading(rec.Log, hold, RoutineActivity.Looking), "the look is not AlertLookDuration long");
            rec.StepUntil(x => !x.InDwell, 1000, "the end of the dwell");
            rec.StepUntil(x => x.InDwell, 5000, "the next station");
            Assert.AreEqual(0, r.StationIndex, "the routine did not resume");

            List<Rec> after = rec.Since(fall);
            Assert.IsFalse(after.Exists(x => x.Act == RoutineActivity.Sitting || x.Sitting), "sat down after a pratfall");
            Assert.IsFalse(rec.Log.Exists(x => x.OnPlayer), "pinned the player without sitting on it");
            Assert.AreEqual(1, rec.Log.FindAll(x => x.JustSat).Count, "JustSat must be true on exactly one step");
            Assert.GreaterOrEqual(AssertTelegraphs(rec.Log, "pratfall"), 4);
        }

        [Test]
        public void Shipped_levels_sit_on_the_prop_center_or_the_player_seat_and_slide_there_without_a_jump()
        {
            int props = 0;
            int players = 0;
            var lengths = new List<string>();
            foreach (string path in Directory.GetFiles("Assets/Resources/Levels", "*.json"))
            {
                string file = Path.GetFileName(path);
                if (file == LevelManifest.FileName + ".json")
                {
                    continue;
                }
                LevelDef level = LevelJson.Parse(File.ReadAllText(path));
                foreach (InhabitantDef h in level.Inhabitants)
                {
                    var sitStations = new HashSet<int>();
                    for (int i = 0; i < h.Stations.Count; i++)
                    {
                        if (!string.IsNullOrEmpty(h.Stations[i].Sit))
                        {
                            sitStations.Add(i);
                        }
                    }
                    if (sitStations.Count == 0)
                    {
                        continue;
                    }
                    // The routine as the audit steps it: no GameState, so a player seat counts as occupied.
                    var rec = new Recorder(new InhabitantRoutine(h.Stations, h.StartStation));
                    var done = new HashSet<int>();
                    int guard = 0;
                    while (done.Count < sitStations.Count)
                    {
                        Assert.Less(guard++, 40000, $"{file} {h.Name}: never sat at every sit station");
                        rec.Step();
                        if (!rec.R.JustSat || !done.Add(rec.R.StationIndex))
                        {
                            continue;
                        }
                        int sat = rec.Index;
                        StationDef st = h.Stations[rec.R.StationIndex];
                        string context = $"{file} {h.Name} station {rec.R.StationIndex}";
                        Vector3 seat;
                        if (st.SitsOnPlayer)
                        {
                            Assert.IsNotNull(st.Seat, context + ": a player sit without a seat home");
                            seat = new Vector3(st.Seat.X, 0f, st.Seat.Z);
                            players++;
                        }
                        else
                        {
                            PropDef prop = level.Props.Find(p => p.Name == st.Sit);
                            Assert.IsNotNull(prop, $"{context}: no prop named {st.Sit}");
                            seat = prop.Position;
                            props++;
                        }
                        Assert.Less((YawMath.Planar(rec.R.SeatHome.Position) - YawMath.Planar(seat)).magnitude, 1e-4f,
                            context + ": the seat home is not the prop center or the player seat");
                        rec.Step(SitSteps - 1);
                        float length = AssertSlide(rec, sat, st.Position, seat, context);
                        lengths.Add($"{context} ({st.Sit}): {length:0.00} m");
                    }
                }
            }
            TestContext.WriteLine("sit slides: " + string.Join("; ", lengths));
            Assert.Greater(props, 0, "premise: no shipped level sits on a prop");
            Assert.Greater(players, 0, "premise: no shipped level sits on the player");
        }

        // ----- Investigate, alert and switch on while seated -----

        [Test]
        public void Investigate_from_the_player_seat_stands_up_first_telegraphed_then_sits_again_on_resume()
        {
            List<StationDef> stations = PlayerLoop();
            var rec = new Recorder(new InhabitantRoutine(stations, 0));
            InhabitantRoutine r = rec.R;
            rec.StepUntil(x => x.JustSat, 3000, "the moment of sitting");
            rec.Step(40);
            Assert.IsTrue(r.SittingOnPlayer && r.EyeHeight == Tuning.SitEyeHeight, "premise: seated on the player, the eye down");
            int from = rec.Index;
            r.Investigate(new Vector3(3f, 0f, 0.5f));
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode);
            Assert.IsTrue(r.SittingOnPlayer, "the pin must hold until the stand up starts");
            rec.StepUntil(x => x.ReachedTarget, 3000, "the target");
            List<Rec> s = rec.Since(from + 1);
            Assert.AreEqual(TelegraphSteps, CountLeading(s, 0, RoutineActivity.Telegraph), "Investigate must stand up after a telegraph");
            Assert.IsTrue(s.GetRange(0, TelegraphSteps).TrueForAll(x => x.OnPlayer && x.Sitting), "the pin dropped during the stand up telegraph");
            Assert.AreEqual(SitSteps, CountLeading(s, TelegraphSteps, RoutineActivity.StandingUp));
            Assert.IsFalse(s[TelegraphSteps].OnPlayer, "the pin must release on the first stand up step");
            int firstWalk = s.FindIndex(x => x.Act == RoutineActivity.Walking);
            Assert.Greater(firstWalk, TelegraphSteps + SitSteps - 1, "walked before standing up");
            Assert.AreEqual(stations[1].Position, s[TelegraphSteps + SitSteps - 1].Pos, "the walk must start from the seat front");

            r.CancelInvestigation();
            rec.StepUntil(x => x.JustSat, 3000, "the sit after the resume");
            Assert.AreEqual(SitResult.OnPlayer, r.LastSitResult);
            Assert.AreEqual(2, rec.Log.FindAll(x => x.JustSat).Count);
            AssertTelegraphs(rec.Log, "investigate from the seat");
        }

        [Test]
        public void Alert_while_seated_turns_the_head_only_and_the_sitting_goes_on()
        {
            List<StationDef> stations = PropLoop();
            var rec = new Recorder(new InhabitantRoutine(stations, 0));
            InhabitantRoutine r = rec.R;
            rec.StepUntil(x => x.JustSat, 3000, "the moment of sitting");
            rec.Step(SitSteps + 1);
            Assert.AreEqual(RoutineActivity.Sitting, r.LastActivity, "premise: seated, in the wait before the glance");
            float body = r.BodyYaw;
            int from = rec.Index;
            r.Alert(SourceAtEye(r, 150f, 3f), NoiseKind.Topple);
            Assert.AreEqual(InhabitantMode.Alerted, r.Mode, "a topple alerts in Routine");
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the end of the alert");
            List<Rec> look = rec.Since(from);
            Assert.IsTrue(look.Exists(x => x.Act == RoutineActivity.Looking), "premise: it looked");
            Assert.IsTrue(look.Exists(x => Mathf.Abs(x.Head - Tuning.HeadYawLimit) < 1e-3f), "the head did not turn to its limit");
            Assert.IsTrue(look.TrueForAll(x => x.Body == body), "a seated inhabitant turned its body");
            Assert.IsTrue(look.TrueForAll(x => x.Sitting && x.Eye == Tuning.SitEyeHeight && x.Pos == SofaCenter), "left the seat during the look");

            // Premise: standing, the same alert turns the body.
            var standing = new InhabitantRoutine(stations, 0);
            standing.Step(Dt);
            float before = standing.BodyYaw;
            standing.Alert(SourceAtEye(standing, 150f, 3f), NoiseKind.Topple);
            // A telegraph (30 steps) and the look turn (about 20), then the hold: 100 steps is inside the hold.
            for (int i = 0; i < 100; i++)
            {
                standing.Step(Dt);
            }
            Assert.Greater(Mathf.Abs(Mathf.DeltaAngle(before, standing.BodyYaw)), 30f, "premise: standing, the look turns the body");

            // The M4 noises behave like a hop: ignored while alerted, only a creak retargets.
            r.Alert(SourceAtEye(r, 90f, 2f), NoiseKind.Click);
            Assert.AreEqual(InhabitantMode.Alerted, r.Mode, "a click alerts in Routine");
            Vector3 first = r.AlertSource;
            foreach (NoiseKind k in new[] { NoiseKind.Hop, NoiseKind.Topple, NoiseKind.Click, NoiseKind.Roll })
            {
                r.Alert(first + Vector3.right, k);
                Assert.AreEqual(first, r.AlertSource, k + " retargeted an alerted inhabitant");
            }
            r.Alert(first + Vector3.right, NoiseKind.Creak);
            Assert.AreEqual(first + Vector3.right, r.AlertSource, "a creak must retarget");
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the end of the second alert");
            rec.StepUntil(x => x.LoopsCompleted >= 1, 5000, "the loop");
            Assert.AreEqual(1, rec.Log.FindAll(x => x.JustSat).Count, "an alert made it sit twice");
            AssertTelegraphs(rec.Log, "alert while seated");
        }

        [Test]
        public void Alert_during_the_stand_up_gives_the_rest_of_it_a_fresh_telegraph()
        {
            var rec = new Recorder(new InhabitantRoutine(PropLoop(), 0));
            InhabitantRoutine r = rec.R;
            rec.StepUntil(x => x.LastActivity == RoutineActivity.StandingUp, 4000, "the stand up");
            rec.Step(8);
            Assert.IsTrue(r.EyeHeight > Tuning.SitEyeHeight + 0.05f && r.EyeHeight < Tuning.EyeHeight - 0.05f, "premise: half risen");
            r.Alert(SourceAtEye(r, 50f, 2f), NoiseKind.Hop);
            Assert.AreEqual(InhabitantMode.Alerted, r.Mode);
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 2000, "the end of the alert");
            rec.StepUntil(x => !x.IsLowered, 500, "standing");
            int risings = 0;
            for (int i = 1; i < rec.Log.Count; i++)
            {
                if (rec.Log[i].Act == RoutineActivity.StandingUp && rec.Log[i - 1].Act != RoutineActivity.StandingUp)
                {
                    risings++;
                    Assert.GreaterOrEqual(CountBefore(rec.Log, i, RoutineActivity.Telegraph), TelegraphSteps, $"the stand up at record {i} has no telegraph");
                }
            }
            Assert.AreEqual(2, risings, "premise: the alert split the stand up in two");
            AssertTelegraphs(rec.Log, "alert during the stand up");
        }

        // ----- Switch on (CONTRACT_M4 2.3, amendment 9.3) -----

        [Test]
        public void Switch_on_walks_to_the_lamp_holds_the_beat_raises_the_flag_once_then_resumes()
        {
            List<StationDef> stations = TwoPlain();
            var rec = new Recorder(new InhabitantRoutine(stations, 0, new LPlanner()));
            InhabitantRoutine r = rec.R;
            rec.StepUntil(x => x.LastActivity == RoutineActivity.Walking, 1000, "the walk");
            rec.Step(20);
            var lamp = new Vector3(1f, 0f, 3f);
            int from = rec.Index;
            r.BeginSwitchOn(lamp);
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode);
            r.Alert(SourceAtEye(r, 90f, 2f), NoiseKind.Creak);
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode, "switching on must ignore noise");
            rec.StepUntil(x => x.JustSwitchedOn, 3000, "the switch on");
            int on = rec.Index;
            List<Rec> s = rec.Since(from + 1);
            Assert.IsFalse(s.Exists(x => x.Reached), "a switch on must never set ReachedTarget (GameState would carry)");
            int beat = s.FindIndex(x => x.Act == RoutineActivity.SwitchingOn);
            Assert.Greater(beat, 0);
            Assert.AreEqual(SwitchSteps, CountLeading(s, beat, RoutineActivity.SwitchingOn), "the beat is not LampSwitchOnTime long");
            Assert.AreEqual(on - from - 1, beat + SwitchSteps - 1, "JustSwitchedOn is not on the last beat step");
            Assert.LessOrEqual(YawMath.Planar(lamp - s[beat].Pos).magnitude, Tuning.InvestigateReach + 1e-4f, "switched on out of reach");
            Assert.AreEqual(0f, Mathf.DeltaAngle(s[beat].Body + s[beat].Head, YawToward(s[beat].Pos, lamp)), 1e-2f, "not facing the lamp");
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode, "the beat step is still part of the switch on");
            rec.Step();
            Assert.AreEqual(InhabitantMode.Routine, r.Mode, "the routine resumes on the next step");
            Assert.IsFalse(r.JustSwitchedOn, "JustSwitchedOn lasted more than one step");
            rec.StepUntil(x => x.InDwell, 5000, "the station");
            Assert.AreEqual(1, r.StationIndex, "resumed at the wrong station");
            Assert.AreEqual(1, rec.Log.FindAll(x => x.SwitchedOn).Count);
            AssertTelegraphs(rec.Log, "switch on");
        }

        [Test]
        public void Switch_on_from_a_seat_stands_up_first_and_busy_inhabitants_ignore_it()
        {
            List<StationDef> stations = PropLoop();
            var rec = new Recorder(new InhabitantRoutine(stations, 0));
            InhabitantRoutine r = rec.R;
            rec.StepUntil(x => x.JustSat, 3000, "the moment of sitting");
            rec.Step(30);
            int from = rec.Index;
            r.BeginSwitchOn(new Vector3(0f, 0f, 3f));
            rec.StepUntil(x => x.JustSwitchedOn, 3000, "the switch on");
            List<Rec> s = rec.Since(from + 1);
            Assert.AreEqual(TelegraphSteps, CountLeading(s, 0, RoutineActivity.Telegraph), "must stand up after a telegraph");
            Assert.AreEqual(SitSteps, CountLeading(s, TelegraphSteps, RoutineActivity.StandingUp));
            rec.StepUntil(x => x.JustSat, 3000, "the sit after the resume");
            Assert.AreEqual(2, rec.Log.FindAll(x => x.JustSat).Count, "the replayed dwell did not sit");
            AssertTelegraphs(rec.Log, "switch on from the seat");

            // Busy, frozen or startled: refused.
            var busy = new InhabitantRoutine(TwoPlain(), 0);
            busy.Step(Dt);
            busy.Investigate(new Vector3(0f, 0f, 3f));
            busy.BeginSwitchOn(new Vector3(-3f, 0f, 0f));
            for (int i = 0; i < 400 && !busy.ReachedTarget; i++)
            {
                busy.Step(Dt);
                Assert.IsFalse(busy.JustSwitchedOn, "an investigating inhabitant switched on");
            }
            Assert.IsTrue(busy.ReachedTarget, "the investigation was replaced by the switch on");
            var frozen = new InhabitantRoutine(TwoPlain(), 0);
            frozen.Pin(Vector3.zero, 0f, 0f);
            frozen.BeginSwitchOn(Vector3.one);
            Assert.AreEqual(InhabitantMode.Routine, frozen.Mode);
            var startled = new InhabitantRoutine(TwoPlain(), 0);
            startled.Startle(Vector3.one);
            startled.BeginSwitchOn(Vector3.one);
            Assert.AreEqual(InhabitantMode.Startled, startled.Mode);
        }

        // ----- Carry per body -----

        [Test]
        public void CarryForward_per_body_sets_the_carry_goal_and_the_anchor()
        {
            var home = new FurniturePose(new Vector3(3f, 0f, -2f), 0f);
            var distances = new List<float>();
            foreach (float forward in new[] { Tuning.CarryForward, 0.65f })
            {
                var r = new InhabitantRoutine(TwoPlain(), 0) { CarryForward = forward };
                r.Step(Dt);
                r.Investigate(r.Position + Vector3.forward * 0.5f);
                Assert.IsFalse(r.ReachedTarget);
                for (int i = 0; i < 200 && !r.ReachedTarget; i++)
                {
                    r.Step(Dt);
                }
                Assert.IsTrue(r.ReachedTarget, "premise: reached");
                r.BeginCarry(home);
                int guard = 0;
                while (!r.JustPutDown)
                {
                    Assert.Less(guard++, 5000, "never put down");
                    r.Step(Dt);
                    Assert.AreEqual(forward, YawMath.Planar(r.CarryAnchor - r.Position).magnitude, 1e-4f, "the anchor is not CarryForward ahead");
                }
                Assert.That(YawMath.Planar(r.CarryAnchor - home.Position).magnitude, Is.LessThan(0.02f), $"{forward}: the held furniture is not put down home");
                float d = YawMath.Planar(r.Position - home.Position).magnitude;
                Assert.AreEqual(forward, d, 0.02f, "the carry goal is not CarryForward short of home");
                distances.Add(d);
            }
            Assert.Greater(distances[1] - distances[0], 0.15f, "premise: the two bodies carry at different distances");
        }

        // ----- Rule switch and M1 identity -----

        [Test]
        public void Sitting_off_makes_a_sit_station_a_plain_dwell_step_for_step()
        {
            foreach (bool player in new[] { false, true })
            {
                List<StationDef> withSit = player ? PlayerLoop() : PropLoop();
                List<StationDef> plain = player ? PlayerLoop() : PropLoop();
                plain[1].Sit = null;
                plain[1].Seat = null;
                var off = new InhabitantRoutine(withSit, 0) { SittingEnabled = false, SeatOccupied = () => false };
                var reference = new InhabitantRoutine(plain, 0);
                var on = new InhabitantRoutine(player ? PlayerLoop() : PropLoop(), 0);
                bool differs = false;
                for (int i = 0; i < 3000; i++)
                {
                    off.Step(Dt);
                    reference.Step(Dt);
                    on.Step(Dt);
                    string at = $"{(player ? "player" : "prop")} seat, step {i}";
                    Assert.AreEqual(reference.Position, off.Position, at);
                    Assert.AreEqual(reference.BodyYaw, off.BodyYaw, at);
                    Assert.AreEqual(reference.HeadYaw, off.HeadYaw, at);
                    Assert.AreEqual(reference.LastActivity, off.LastActivity, at);
                    Assert.AreEqual(reference.EyeHeight, off.EyeHeight, at);
                    Assert.IsFalse(off.JustSat || off.IsSitting || off.IsLowered || off.SitTargetsPlayer, at + ": sat with sitting off");
                    differs |= on.EyeHeight != reference.EyeHeight;
                }
                Assert.IsTrue(differs, "premise: with sitting on, the same loop sits");
            }
        }

        [TestCase(0)]
        [TestCase(2)]
        public void M1_routine_is_unchanged_and_never_sits(int start)
        {
            var reference = new M1ReferenceRoutine(Level1(), start);
            var r = new InhabitantRoutine(Level1(), start);
            int steps = 0;
            while (reference.LoopsCompleted < 2)
            {
                Assert.Less(steps++, 40000, "the reference routine never looped twice");
                reference.Step(Dt);
                r.Step(Dt);
                string at = $"step {steps}";
                Assert.AreEqual(reference.Position, r.Position, at + ": position");
                Assert.AreEqual(reference.BodyYaw, r.BodyYaw, at + ": body yaw");
                Assert.AreEqual(reference.HeadYaw, r.HeadYaw, at + ": head yaw");
                Assert.AreEqual(reference.LastActivity, r.LastActivity, at + ": activity");
                Assert.AreEqual(reference.InDwell, r.InDwell, at + ": in dwell");
                Assert.AreEqual(reference.StationIndex, r.StationIndex, at + ": station");
                Assert.AreEqual(reference.LoopsCompleted, r.LoopsCompleted, at + ": loops");
                Assert.AreEqual(reference.TelegraphCount, r.TelegraphCount, at + ": telegraph count");
                Assert.AreEqual(Tuning.EyeHeight, r.EyeHeight, at + ": eye height");
                Assert.AreEqual(reference.Position + Vector3.up * Tuning.EyeHeight, r.EyePosition, at + ": eye position");
                Assert.IsFalse(r.IsSitting || r.IsLowered || r.JustSat || r.SittingOnPlayer || r.SitTargetsPlayer, at + ": sat in M1");
                Assert.AreEqual(SitResult.None, r.LastSitResult, at);
            }
            Assert.Greater(steps, 1000, "premise: two loops are long");
            Assert.Greater(reference.TelegraphCount, 10, "premise: the loop has telegraphs");
            Assert.AreEqual(Tuning.CarryForward, YawMath.Planar(r.CarryAnchor - r.Position).magnitude, 1e-4f, "the default carry is the M1 chair's");
        }

        // ----- The invariant in every M4 mode -----

        [Test]
        public void Every_turn_over_30_deg_is_telegraphed_in_every_M4_mode()
        {
            int large = 0;
            int onProp = 0;
            int onPlayer = 0;
            int pratfalls = 0;
            int alertsLowered = 0;
            int alertsStandingUp = 0;
            int investigatesLowered = 0;
            int switchOns = 0;
            int switchOnsLowered = 0;
            int carries = 0;
            var kinds = new[] { NoiseKind.Hop, NoiseKind.Creak, NoiseKind.Topple, NoiseKind.Click, NoiseKind.Roll };
            for (int seed = 1; seed <= 16; seed++)
            {
                var rng = new System.Random(seed);
                IPathPlanner planner = seed % 2 == 0 ? (IPathPlanner)StraightPlanner.Instance : new LPlanner();
                var r = new InhabitantRoutine(Mixed(), seed % 4, planner);
                double homeOdds = 0.3 + 0.4 * (seed % 3) / 2.0;
                r.SeatOccupied = () => rng.NextDouble() < homeOdds;
                var rec = new Recorder(r);
                int sits = 0;
                for (int step = 0; step < 12000; step++)
                {
                    rec.Step();
                    bool inject = step < 9000;
                    if (r.JustSat)
                    {
                        sits++;
                        onProp += r.LastSitResult == SitResult.OnProp ? 1 : 0;
                        onPlayer += r.LastSitResult == SitResult.OnPlayer ? 1 : 0;
                        pratfalls += r.LastSitResult == SitResult.Pratfall ? 1 : 0;
                        Assert.AreNotEqual(SitResult.None, r.LastSitResult, $"seed {seed}: sat without a result");
                    }
                    switchOns += r.JustSwitchedOn ? 1 : 0;
                    if (r.Mode == InhabitantMode.Investigating && r.ReachedTarget)
                    {
                        if (inject && rng.NextDouble() < 0.6)
                        {
                            r.BeginCarry(new FurniturePose(RandomPoint(rng, r.Position, 1f, 4f), (float)(rng.NextDouble() * 360.0)));
                            carries++;
                        }
                        else
                        {
                            r.CancelInvestigation();
                        }
                    }
                    if (!inject)
                    {
                        continue;
                    }
                    double p = rng.NextDouble();
                    bool lowered = r.IsLowered;
                    bool calm = r.Mode == InhabitantMode.Routine || r.Mode == InhabitantMode.Alerted;
                    // Stand ups are short (0.5 s): alert them more often, so interrupted stand ups are exercised.
                    double alertOdds = r.LastActivity == RoutineActivity.StandingUp ? 0.05 : 0.008;
                    if (p < alertOdds)
                    {
                        InhabitantMode before = r.Mode;
                        RoutineActivity activity = r.LastActivity;
                        r.Alert(RandomPoint(rng, r.Position, 0.5f, 6f), kinds[rng.Next(kinds.Length)]);
                        if (before == InhabitantMode.Routine && r.Mode == InhabitantMode.Alerted)
                        {
                            alertsLowered += lowered ? 1 : 0;
                            alertsStandingUp += activity == RoutineActivity.StandingUp ? 1 : 0;
                        }
                    }
                    else if (p < alertOdds + 0.0025 && calm)
                    {
                        r.Investigate(RandomPoint(rng, r.Position, 0.3f, 5f));
                        Assert.AreEqual(InhabitantMode.Investigating, r.Mode, $"seed {seed}: Investigate refused");
                        investigatesLowered += lowered ? 1 : 0;
                    }
                    else if (p < alertOdds + 0.0045 && calm)
                    {
                        r.BeginSwitchOn(RandomPoint(rng, r.Position, 0.3f, 5f));
                        Assert.AreEqual(InhabitantMode.Investigating, r.Mode, $"seed {seed}: BeginSwitchOn refused");
                        switchOnsLowered += lowered ? 1 : 0;
                    }
                }
                // The routine itself keeps sitting after the injections stop, so it may end inside a pratfall look:
                // let that finish. A stuck mode fails here or on the run bound below.
                rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 1000,
                    $"seed {seed}: settling back into the routine (mode {r.Mode}, activity {r.LastActivity}, last sit {r.LastSitResult})");
                int run = 0;
                int longest = 0;
                foreach (Rec x in rec.Log)
                {
                    run = x.Mode == InhabitantMode.Alerted ? run + 1 : 0;
                    longest = Mathf.Max(longest, run);
                }
                Assert.Less(longest, 1500, $"seed {seed}: Alerted for {longest * Dt:0.0} s in a row");
                Assert.AreEqual(sits, rec.Log.FindAll(x => x.JustSat).Count, $"seed {seed}: JustSat is not one step per sit");
                large += AssertTelegraphs(rec.Log, $"seed {seed}");
            }
            TestContext.WriteLine($"coverage: {large} large turns, {onProp} prop sits, {onPlayer} sits on the player, {pratfalls} pratfalls, "
                + $"{alertsLowered} alerts while lowered ({alertsStandingUp} in a stand up), {investigatesLowered} investigations and "
                + $"{switchOnsLowered} switch ons from a seat, {switchOns} switch ons, {carries} carries");
            // Premises: the scenarios covered what they claim to cover.
            Assert.Greater(large, 300, "too few large turns: the check would pass on nothing");
            Assert.Greater(onProp, 10, "too few sits on a prop");
            Assert.Greater(onPlayer, 10, "too few sits on the player");
            Assert.Greater(pratfalls, 5, "too few pratfalls");
            Assert.Greater(alertsLowered, 5, "too few alerts while lowered");
            Assert.Greater(alertsStandingUp, 0, "no alert ever interrupted a stand up");
            Assert.Greater(investigatesLowered, 2, "too few investigations from a seat");
            Assert.Greater(switchOns, 5, "too few switch ons");
            Assert.Greater(switchOnsLowered, 0, "no switch on from a seat");
            Assert.Greater(carries, 5, "too few carries");
        }

        private static Vector3 RandomPoint(System.Random rng, Vector3 center, float min, float max)
        {
            float yaw = (float)(rng.NextDouble() * 360.0);
            float distance = min + (float)rng.NextDouble() * (max - min);
            return YawMath.Planar(center) + YawMath.Forward(yaw) * distance;
        }
    }
}
