using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>PRD 10.1: unit tests of the pure logic.</summary>
    public sealed class VisionMathTests
    {
        private static readonly Vector3 Eye = new Vector3(0f, 1.6f, 0f);

        private static Vector3 AtAngle(float degrees, float distance)
        {
            // A point in the horizontal plane of the eye, rotated away from +z.
            return Eye + YawMath.Forward(degrees) * distance;
        }

        [Test]
        public void Point_ahead_in_range_is_in_cone()
        {
            Assert.IsTrue(VisionMath.IsInCone(Eye, Vector3.forward, AtAngle(0f, 5f), 10f, 55f));
        }

        [Test]
        public void Point_beyond_range_is_not_in_cone()
        {
            Assert.IsFalse(VisionMath.IsInCone(Eye, Vector3.forward, AtAngle(0f, 10.01f), 10f, 55f));
            Assert.IsTrue(VisionMath.IsInCone(Eye, Vector3.forward, AtAngle(0f, 10f), 10f, 55f), "exactly at range is inside");
        }

        [Test]
        public void Point_exactly_at_half_angle_is_inside()
        {
            Assert.IsTrue(VisionMath.IsInCone(Eye, Vector3.forward, AtAngle(55f, 4f), 10f, 55f));
            Assert.IsTrue(VisionMath.IsInCone(Eye, Vector3.forward, AtAngle(-55f, 4f), 10f, 55f));
        }

        [Test]
        public void Point_one_degree_past_half_angle_is_outside()
        {
            Assert.IsFalse(VisionMath.IsInCone(Eye, Vector3.forward, AtAngle(56f, 4f), 10f, 55f));
            Assert.IsFalse(VisionMath.IsInCone(Eye, Vector3.forward, AtAngle(-56f, 4f), 10f, 55f));
        }

        [Test]
        public void Point_behind_is_outside()
        {
            Assert.IsFalse(VisionMath.IsInCone(Eye, Vector3.forward, AtAngle(180f, 2f), 10f, 55f));
        }

        [Test]
        public void Point_directly_above_is_outside()
        {
            Assert.IsFalse(VisionMath.IsInCone(Eye, Vector3.forward, Eye + Vector3.up * 2f, 10f, 55f));
        }

        [Test]
        public void Cone_is_a_true_cone_not_two_separate_angles()
        {
            // 40 deg left and 40 deg down: each angle alone is inside 55, the 3D angle is ~54.4 (inside),
            // while 45 and 45 gives 60 (outside). Separate horizontal and vertical tests would accept both.
            Vector3 dir40 = Quaternion.Euler(40f, 40f, 0f) * Vector3.forward;
            Vector3 dir45 = Quaternion.Euler(45f, 45f, 0f) * Vector3.forward;
            Assert.IsTrue(VisionMath.IsInCone(Eye, Vector3.forward, Eye + dir40 * 3f, 10f, 55f));
            Assert.IsFalse(VisionMath.IsInCone(Eye, Vector3.forward, Eye + dir45 * 3f, 10f, 55f));
        }

        [Test]
        public void Sample_points_are_center_and_four_inset_top_corners()
        {
            var points = new Vector3[5];
            VisionMath.SamplePoints(new Vector3(1f, 0f, 2f), 0f, new Vector3(0.45f, 0.9f, 0.45f), 0.03f, points);
            Assert.That(points[0], Is.EqualTo(new Vector3(1f, 0.45f, 2f)).Using(Vector3EqualityComparer.Instance));
            for (int i = 1; i < 5; i++)
            {
                Assert.AreEqual(0.87f, points[i].y, 1e-5f);
                Assert.AreEqual(0.195f, Mathf.Abs(points[i].x - 1f), 1e-5f);
                Assert.AreEqual(0.195f, Mathf.Abs(points[i].z - 2f), 1e-5f);
            }
        }

        [Test]
        public void Sample_points_follow_the_furniture_yaw()
        {
            var points = new Vector3[5];
            // A long box turned 90 deg: its long side must now run along x.
            VisionMath.SamplePoints(Vector3.zero, 90f, new Vector3(0.2f, 1f, 1.0f), 0f, points);
            float maxX = 0f;
            for (int i = 1; i < 5; i++)
            {
                maxX = Mathf.Max(maxX, Mathf.Abs(points[i].x));
            }
            Assert.AreEqual(0.5f, maxX, 1e-4f);
        }
    }

    internal sealed class Vector3EqualityComparer : IEqualityComparer<Vector3>
    {
        public static readonly Vector3EqualityComparer Instance = new Vector3EqualityComparer();
        public bool Equals(Vector3 a, Vector3 b) => (a - b).sqrMagnitude < 1e-8f;
        public int GetHashCode(Vector3 v) => 0;
    }

    public sealed class MotionRuleTests
    {
        [Test]
        public void Speed_below_threshold_is_not_moving()
        {
            Assert.IsFalse(MotionRule.IsMoving(0.049f, 0f));
            Assert.IsFalse(MotionRule.IsMoving(0.05f, 0f), "the threshold itself is not above it");
        }

        [Test]
        public void Speed_above_threshold_is_moving()
        {
            Assert.IsTrue(MotionRule.IsMoving(0.051f, 0f));
        }

        [Test]
        public void Yaw_rate_below_threshold_is_not_moving()
        {
            Assert.IsFalse(MotionRule.IsMoving(0f, 2.9f));
            Assert.IsFalse(MotionRule.IsMoving(0f, -2.9f));
        }

        [Test]
        public void Rotation_only_is_moving()
        {
            Assert.IsTrue(MotionRule.IsMoving(0f, 3.1f));
            Assert.IsTrue(MotionRule.IsMoving(0f, -3.1f));
        }

        [Test]
        public void Pose_overload_measures_planar_speed_and_yaw_rate()
        {
            Assert.IsTrue(MotionRule.IsMoving(Vector3.zero, 0f, new Vector3(0.0012f, 0f, 0f), 0f, 0.02f), "0.06 m/s");
            Assert.IsFalse(MotionRule.IsMoving(Vector3.zero, 0f, new Vector3(0.0008f, 0f, 0f), 0f, 0.02f), "0.04 m/s");
            Assert.IsFalse(MotionRule.IsMoving(Vector3.zero, 0f, new Vector3(0f, 0.5f, 0f), 0f, 0.02f), "vertical motion never counts");
            Assert.IsTrue(MotionRule.IsMoving(Vector3.zero, 179f, Vector3.zero, -179f, 0.02f), "2 deg across the wrap is 100 deg/s");
        }
    }

    public sealed class CaughtRuleTests
    {
        private const float Dt = 0.02f;

        private static void Run(CaughtRule rule, bool seen, bool moving, float seconds)
        {
            int steps = Mathf.RoundToInt(seconds / Dt);
            for (int i = 0; i < steps; i++)
            {
                rule.Step(seen, moving, Dt);
            }
        }

        [Test]
        public void Seen_and_moving_018_then_hidden_is_not_caught_and_resets()
        {
            var rule = new CaughtRule();
            Run(rule, true, true, 0.18f);
            Assert.IsFalse(rule.Caught);
            Assert.Greater(rule.SeenMoving, 0.17f);
            rule.Step(false, true, Dt);
            Assert.IsFalse(rule.Caught);
            Assert.AreEqual(0f, rule.SeenMoving, "the timer resets on any step where either is false");
            // And the reset is real: another 0.18 s does not add up to a catch.
            Run(rule, true, true, 0.18f);
            Assert.IsFalse(rule.Caught);
        }

        [Test]
        public void Seen_and_moving_020_is_caught()
        {
            var rule = new CaughtRule();
            Run(rule, true, true, 0.18f);
            Assert.IsFalse(rule.Caught);
            Run(rule, true, true, 0.02f);
            Assert.IsTrue(rule.Caught);
        }

        [Test]
        public void Seen_and_still_for_10_s_is_not_caught()
        {
            var rule = new CaughtRule();
            Run(rule, true, false, 10f);
            Assert.IsFalse(rule.Caught);
            Assert.AreEqual(0f, rule.SeenMoving);
        }

        [Test]
        public void Moving_and_unseen_for_10_s_is_not_caught()
        {
            var rule = new CaughtRule();
            Run(rule, false, true, 10f);
            Assert.IsFalse(rule.Caught);
        }

        [Test]
        public void Reset_clears_a_catch()
        {
            var rule = new CaughtRule();
            Run(rule, true, true, 1f);
            Assert.IsTrue(rule.Caught);
            rule.Reset();
            Assert.IsFalse(rule.Caught);
            Assert.AreEqual(0f, rule.SeenMoving);
        }
    }

    public sealed class LevelDataTests
    {
        private const string Level1Path = "Assets/Resources/Levels/level1.json";

        private static LevelDef Level1() => LevelJson.Parse(File.ReadAllText(Level1Path));

        [Test]
        public void Level1_matches_the_prd_layout()
        {
            LevelDef l = Level1();
            Assert.AreEqual(8f, l.Room.SizeX);
            Assert.AreEqual(6f, l.Room.SizeZ);
            Assert.AreEqual(2.7f, l.Room.WallHeight, 1e-5f);
            Assert.AreEqual(-3.2f, l.Player.X, 1e-5f);
            Assert.AreEqual(-2.2f, l.Player.Z, 1e-5f);
            Assert.AreEqual(3.5f, l.Exit.X, 1e-5f);
            Assert.AreEqual(2.3f, l.Exit.Z, 1e-5f);
            Assert.AreEqual(1, l.Inhabitants.Count);
            Assert.AreEqual(4, l.Inhabitants[0].Stations.Count);
            Assert.AreEqual(3, l.Props.Count);
        }

        [Test]
        public void Level1_passes_the_validator()
        {
            List<string> issues = LevelValidator.Validate(Level1());
            Assert.IsEmpty(issues, string.Join("\n", issues));
        }

        [Test]
        public void Validator_rejects_a_spawn_outside_the_room()
        {
            LevelDef l = Level1();
            l.Player.X = 5f;
            Assert.That(LevelValidator.Validate(l), Has.Some.Contains("player spawn"));
        }

        [Test]
        public void Validator_rejects_an_exit_outside_the_room()
        {
            LevelDef l = Level1();
            l.Exit.X = 3.8f;
            Assert.That(LevelValidator.Validate(l), Has.Some.Contains("exit zone"));
        }

        [Test]
        public void Validator_rejects_a_station_outside_the_room()
        {
            LevelDef l = Level1();
            l.Inhabitants[0].Stations[2].Z = -2.9f;
            Assert.That(LevelValidator.Validate(l), Has.Some.Contains("not inside the room"));
        }

        [Test]
        public void Validator_rejects_a_station_inside_a_prop()
        {
            LevelDef l = Level1();
            PropDef sofa = l.Props.Find(p => p.Kind == "sofa");
            l.Inhabitants[0].Stations[1].X = sofa.X;
            l.Inhabitants[0].Stations[1].Z = sofa.Z;
            Assert.That(LevelValidator.Validate(l), Has.Some.Contains("inside prop Sofa"));
        }

        [Test]
        public void Validator_rejects_an_exit_overlapping_a_prop()
        {
            LevelDef l = Level1();
            PropDef table = l.Props.Find(p => p.Kind == "table");
            l.Exit.X = table.X;
            l.Exit.Z = table.Z;
            Assert.That(LevelValidator.Validate(l), Has.Some.Contains("exit zone overlaps prop Table"));
        }

        [Test]
        public void Rotated_rectangles_overlap_test()
        {
            // A 2 x 0.2 bar. Yaw 45 turns its long axis onto the (x, z) = (1, -1) diagonal.
            var bar = new Vector2(1f, 0.1f);
            var dot = new Vector2(0.05f, 0.05f);
            Assert.IsTrue(LevelValidator.RectsOverlap(Vector2.zero, bar, 45f, new Vector2(0.6f, -0.6f), dot, 0f), "on the turned bar");
            Assert.IsFalse(LevelValidator.RectsOverlap(Vector2.zero, bar, 45f, new Vector2(0.6f, 0.6f), dot, 0f), "across the turned bar");
            Assert.IsTrue(LevelValidator.RectsOverlap(Vector2.zero, bar, 0f, new Vector2(0.6f, 0f), dot, 0f), "on the straight bar");
            Assert.IsFalse(LevelValidator.RectsOverlap(Vector2.zero, bar, 0f, new Vector2(0.6f, 0.6f), dot, 0f), "beside the straight bar");
        }

        [Test]
        public void Level_json_round_trip_is_lossless()
        {
            LevelDef original = Level1();
            string once = LevelJson.Serialize(original);
            LevelDef back = LevelJson.Parse(once);
            string twice = LevelJson.Serialize(back);
            Assert.AreEqual(once, twice);
            Assert.AreEqual(original.Inhabitants[0].Stations[3].Glances[0].Yaw, back.Inhabitants[0].Stations[3].Glances[0].Yaw);
            Assert.AreEqual(original.Props.Count, back.Props.Count);
        }

        [Test]
        public void Level_json_rejects_unknown_members()
        {
            Assert.Throws<Newtonsoft.Json.JsonSerializationException>(() => LevelJson.Parse("{\"id\":\"x\",\"typo\":1}"));
        }

        // ----- M7 textures (docs/CONTRACT_M7.md 1.2): the floorFinish field. -----

        [Test]
        public void Validator_accepts_a_tile_floor_finish_on_a_hard_floor()
        {
            LevelDef l = Level1();
            l.Room.FloorFinish = RoomDef.TileFinish;
            Assert.IsEmpty(LevelValidator.Validate(l), "a tile finish on a hard floor should be valid");
        }

        [Test]
        public void Validator_rejects_an_unknown_floor_finish()
        {
            LevelDef l = Level1();
            l.Room.FloorFinish = "marble";
            Assert.That(LevelValidator.Validate(l), Has.Some.Contains("floor finish"));
        }

        [Test]
        public void Validator_rejects_a_tile_finish_on_a_soft_floor()
        {
            LevelDef l = Level1();
            l.Room.Floor = RoomDef.SoftFloor;
            l.Room.FloorFinish = RoomDef.TileFinish;
            Assert.That(LevelValidator.Validate(l), Has.Some.Contains("both soft and tiled"));
        }
    }

    public sealed class StringsTests
    {
        [Test]
        public void Strings_are_verbatim_from_the_prd()
        {
            // The game was renamed "Out of Sight"; English is the default language, French the second.
            Assert.AreEqual(Strings.English, Strings.Language, "premise: English is the default");
            Assert.AreEqual("Out of Sight", Strings.Get("title"));
            Assert.AreEqual("Don't Get Caught Moving", Strings.Get("title.tagline"));
            Assert.AreEqual("WASD/Arrows: move    Mouse: camera    R: restart    Esc: pause", Strings.Get("hud.controls"));
            Assert.AreEqual("Time: 37.4 s", string.Format(Strings.Get("win.body"), Strings.FormatSeconds(37.43f)));
            Assert.AreEqual("ZQSD/Flèches : avancer    Souris : caméra    R : recommencer    Échap : pause", Strings.Get("hud.controls", Strings.French));
            Assert.AreEqual("Temps : {0} s", Strings.Get("win.body", Strings.French));
            foreach (string key in new[] { "title", "level1.name", "level1.hint", "hud.controls", "fail.title", "fail.body",
                         "fail.action", "win.title", "win.body", "win.action" })
            {
                Assert.AreNotEqual(key, Strings.Get(key), key + " is missing");
                StringAssert.DoesNotContain("—", Strings.Get(key), "no em-dash (PRD 2)");
            }
        }
    }

    public sealed class InhabitantRoutineTests
    {
        private static List<StationDef> Level1Stations() =>
            LevelJson.Parse(File.ReadAllText("Assets/Resources/Levels/level1.json")).Inhabitants[0].Stations;

        private struct Sample
        {
            public float Body;
            public float Head;
            public RoutineActivity Activity;
        }

        private static List<Sample> RunOneLoop(InhabitantRoutine r)
        {
            var samples = new List<Sample>();
            int guard = 0;
            while (r.LoopsCompleted < 1 && guard++ < 20000)
            {
                r.Step(0.02f);
                samples.Add(new Sample { Body = r.BodyYaw, Head = r.HeadYaw, Activity = r.LastActivity });
            }
            Assert.Less(guard, 20000, "the routine never looped");
            return samples;
        }

        [Test]
        public void Every_turn_above_30_deg_is_preceded_by_a_full_telegraph()
        {
            var r = new InhabitantRoutine(Level1Stations(), 0);
            List<Sample> s = RunOneLoop(r);
            int turns = CheckTelegraphs(s, x => x.Body, RoutineActivity.TurningBody) + CheckTelegraphs(s, x => x.Head, RoutineActivity.TurningHead);
            // 4 station arrivals and 4 departures can be small, but the glances alone give 6 head turns.
            Assert.GreaterOrEqual(turns, 6, "too few large turns found: the check would pass on nothing");
        }

        private static int CheckTelegraphs(List<Sample> s, System.Func<Sample, float> yaw, RoutineActivity turning)
        {
            int large = 0;
            int i = 1;
            while (i < s.Count)
            {
                if (Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i]))) < 1e-3f)
                {
                    i++;
                    continue;
                }
                int start = i;
                float total = 0f;
                while (i < s.Count && Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i]))) >= 1e-3f)
                {
                    total += Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i])));
                    Assert.AreEqual(turning, s[i].Activity, "yaw changed outside a turn");
                    i++;
                }
                if (total > 30f)
                {
                    large++;
                    int tele = 0;
                    for (int k = start - 1; k >= 0 && s[k].Activity == RoutineActivity.Telegraph; k--)
                    {
                        tele++;
                    }
                    Assert.GreaterOrEqual(tele * 0.02f, 0.6f - 1e-3f, $"turn of {total:0} deg at step {start} had only {tele * 0.02f:0.00} s of telegraph");
                }
            }
            return large;
        }

        [Test]
        public void Body_never_turns_while_walking_and_head_stays_within_limits()
        {
            var r = new InhabitantRoutine(Level1Stations(), 0);
            float previousBody = r.BodyYaw;
            int guard = 0;
            while (r.LoopsCompleted < 1 && guard++ < 20000)
            {
                r.Step(0.02f);
                if (r.LastActivity == RoutineActivity.Walking)
                {
                    Assert.AreEqual(0f, Mathf.DeltaAngle(previousBody, r.BodyYaw), 1e-3f);
                }
                Assert.LessOrEqual(Mathf.Abs(r.HeadYaw), 80f + 1e-3f);
                previousBody = r.BodyYaw;
            }
        }

        [Test]
        public void Routine_visits_every_station_and_loops()
        {
            var r = new InhabitantRoutine(Level1Stations(), 0);
            var visited = new HashSet<int>();
            int guard = 0;
            while (r.LoopsCompleted < 1 && guard++ < 20000)
            {
                r.Step(0.02f);
                if (r.InDwell)
                {
                    visited.Add(r.StationIndex);
                }
            }
            Assert.AreEqual(1, r.LoopsCompleted);
            Assert.AreEqual(4, visited.Count);
            Assert.AreEqual(0, r.StationIndex);
            Assert.That((r.Position - new Vector3(-1.5f, 0f, 2.2f)).magnitude, Is.LessThan(1e-3f));
        }

        [Test]
        public void Pinned_routine_does_not_move()
        {
            var r = new InhabitantRoutine(Level1Stations(), 0);
            r.Pin(new Vector3(1f, 0f, 1f), 90f, 10f);
            for (int i = 0; i < 500; i++)
            {
                r.Step(0.02f);
            }
            Assert.AreEqual(new Vector3(1f, 0f, 1f), r.Position);
            Assert.AreEqual(90f, r.BodyYaw);
            Assert.AreEqual(10f, r.HeadYaw);
            Assert.AreEqual(100f, r.EyeYaw);
        }
    }
}
