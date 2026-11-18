using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M5 house data (docs/CONTRACT_M5_v3.md 2, 3, 4, 15.2, 15.4, 15.10; CONTRACT_M5.md 3, 6, 16.5 to 16.7): FloorMap,
    /// DoorGeometry and every M5 validator rule, each with a failing case and its passing case. The base fixture is a valid
    /// two room house with a closed leaf, a platform and its ramp, a human and a dog; each negative test breaks one rule.
    /// Wave 5B (CONTRACT_M5 4 to 6, 8, 10, 16.5, 16.8): the robot's loop (with a robot added to the base), the rocking chair
    /// body, no load on it, and the robot, rock, load and final lessons.
    /// </summary>
    public sealed class LevelDataM5Tests
    {
        private const string Folder = "Assets/Resources/Levels/";
        private const float Eps = 1e-4f;

        private static LevelDef Load(string id) => LevelJson.Parse(File.ReadAllText(Folder + id + ".json"));

        /// <summary>
        /// Room a: x in [-4.05, -0.05]; room b: x in [0.05, 6.05]; both z in [-2, 2], walls 0.1 thick, the shared wall line
        /// x = 0. Door 1, (0, 1.25), carries the closed leaf "porte" hinged at its lower z end (z = 0.75), swinging into b:
        /// its sector is the quarter disc x in [0, 1], z in [0.75, 1.75]. Door 2 is the exit door in a's -x wall. In b, the
        /// platform "Mezzanine" (x in [4.55, 6.05], 0.8 m) and its ramp rising +x from x = 2.15 to its west edge (z in
        /// [-0.85, 0.35], axis z = -0.25 on b's 0.5 m cell grid).
        /// </summary>
        private static LevelDef Base()
        {
            var level = new LevelDef
            {
                Id = "test",
                Rooms = new List<RoomDef>
                {
                    new RoomDef { Id = "a", X = -2.05f, Z = 0f, SizeX = 4f, SizeZ = 4f, WallHeight = 2.7f, WallThickness = 0.1f, Floor = "hard" },
                    new RoomDef { Id = "b", X = 3.05f, Z = 0f, SizeX = 6f, SizeZ = 4f, WallHeight = 2.7f, WallThickness = 0.1f, Floor = "hard" },
                },
                Doors = new List<OpeningDef>
                {
                    new OpeningDef { X = 0f, Z = 1.25f, Width = 1f, Top = 2.1f, Leaf = "closed", Hinge = "start", Id = "porte", Swing = "b" },
                    new OpeningDef { X = -4.1f, Z = -1.25f, Width = 1f, Top = 2.1f },
                },
                Platforms = new List<PlatformDef> { new PlatformDef { Name = "Mezzanine", X = 5.3f, Z = 0f, SizeX = 1.5f, SizeZ = 4f, Height = 0.8f } },
                Ramps = new List<RampDef> { new RampDef { X = 3.35f, Z = -0.25f, Width = 1.2f, Length = 2.4f, Yaw = 90f, Platform = "Mezzanine" } },
                Player = new SpawnDef { Kind = "chair", X = -2f, Z = 0f, Yaw = 90f, SizeX = 0.45f, SizeY = 0.9f, SizeZ = 0.45f, Color = "#D7263D" },
                Exit = new ZoneDef { X = -3.55f, Z = -1.25f, SizeX = 0.9f, SizeZ = 0.9f },
                Props = new List<PropDef> { new PropDef { Name = "Crate", Kind = "box", X = -3.3f, Z = 1.5f, SizeX = 0.6f, SizeY = 0.8f, SizeZ = 0.6f } },
                Inhabitants = new List<InhabitantDef>
                {
                    new InhabitantDef
                    {
                        Name = "H",
                        Personality = "watchful",
                        Stations = new List<StationDef>
                        {
                            new StationDef { X = -2f, Z = 1f, Facing = 0f, Dwell = 2f },
                            new StationDef { X = 3f, Z = -1.4f, Facing = 90f, Dwell = 2f },
                        },
                    },
                    new InhabitantDef
                    {
                        Name = "Rex",
                        Kind = "dog",
                        Stations = new List<StationDef>
                        {
                            new StationDef { X = -2.5f, Z = -1.5f, Facing = 0f, Dwell = 5f, Sleep = true },
                            new StationDef { X = 2.5f, Z = 1.5f, Facing = 180f, Dwell = 2f },
                        },
                    },
                },
            };
            level.ResolveSeats();
            return level;
        }

        private static OpeningDef Porte(LevelDef l) => l.Doors[0];

        /// <summary>One issue must contain every fragment. Fragments hold no number formatted by the culture.</summary>
        private static void AssertRejected(LevelDef level, params string[] fragments)
        {
            level.ResolveSeats();
            List<string> issues = LevelValidator.Validate(level);
            bool found = issues.Exists(issue => System.Array.TrueForAll(fragments, f => issue.Contains(f)));
            Assert.IsTrue(found, $"no issue contains [{string.Join(", ", fragments)}]; issues: " + string.Join(" | ", issues));
        }

        /// <summary>No issue contains the fragment (the passing case of a rule).</summary>
        private static void AssertNoIssue(LevelDef level, string fragment)
        {
            level.ResolveSeats();
            List<string> issues = LevelValidator.Validate(level);
            Assert.IsFalse(issues.Exists(i => i.Contains(fragment)), $"an issue contains '{fragment}': " + string.Join(" | ", issues));
        }

        private static void AssertValid(LevelDef level, string what)
        {
            level.ResolveSeats();
            List<string> issues = LevelValidator.Validate(level);
            Assert.IsEmpty(issues, what + ": " + string.Join("\n", issues));
        }

        // ----- The fixture -----

        [Test]
        public void Base_house_fixture_is_valid()
        {
            AssertValid(Base(), "the base fixture");
        }

        [Test]
        public void House_and_audit_fixtures_are_valid()
        {
            foreach (string id in new[] { "test_m5_house_door", "test_m5_house_split", "test_m5_house_mock8", "test_m5_audit_door",
                         "test_m5_audit_split", "test_m5_audit_pet", "test_m5_audit_cross", "test_m5_audit_house", "test_m5_audit_house2" })
            {
                Assert.IsTrue(File.Exists(Folder + id + ".json"), id + " is missing");
                LevelDef l = Load(id);
                Assert.AreEqual(id, l.Id, "the id inside the file matches its name");
                AssertValid(l, id);
            }
            List<string> order = LevelManifest.Parse(File.ReadAllText(Folder + "levels.json"));
            foreach (string id in new[] { "test_m5_house_door", "test_m5_house_split", "test_m5_house_mock8" })
            {
                CollectionAssert.DoesNotContain(order, id, id + " is a test level: never in the play order");
            }
        }

        [Test]
        public void Mock8_house_has_8_rooms_corridors_of_1_2_m_two_leaves_a_platform_and_a_ramp()
        {
            LevelDef l = Load("test_m5_house_mock8");
            Assert.AreEqual(8, l.AllRooms().Count);
            Assert.AreEqual(2, l.LeafDoors().Count);
            Assert.AreEqual(1, l.Platforms.Count);
            Assert.AreEqual(1, l.Ramps.Count);
            Assert.AreEqual(2, l.AllRooms().FindAll(r => Mathf.Abs(Mathf.Min(r.SizeX, r.SizeZ) - 1.2f) < Eps).Count, "two 1.2 m corridors");
            // The character budget's worst case (CONTRACT_M5 16.11): three humans and a dog in their personalities' looks.
            Assert.AreEqual(3, l.Inhabitants.FindAll(h => h.Kind != PersonalityDef.Dog).Count, "three humans");
            Assert.AreEqual(1, l.Inhabitants.FindAll(h => h.Kind == PersonalityDef.Dog).Count, "and a dog");
            Assert.IsTrue(l.Inhabitants.TrueForAll(h => string.IsNullOrEmpty(h.Model) && string.IsNullOrEmpty(h.BodyColor)),
                "every inhabitant wears its personality's model and tint");
        }

        [Test]
        public void Leaves_round_trip_through_json()
        {
            LevelDef l = Load("test_m5_house_door");
            string once = LevelJson.Serialize(l);
            LevelDef back = LevelJson.Parse(once);
            Assert.AreEqual(once, LevelJson.Serialize(back));
            Assert.AreEqual("closed", back.Doors[0].Leaf);
            Assert.AreEqual("start", back.Doors[0].Hinge);
            Assert.AreEqual("porte", back.Doors[0].Id);
            Assert.AreEqual("b", back.Doors[0].Swing);
            Assert.IsTrue(back.Doors[0].HasLeaf && !back.Doors[2].HasLeaf);
            CollectionAssert.AreEqual(new[] { back.Doors[0], back.Doors[1] }, back.LeafDoors(), "leaf doors in level order");
            LevelDef split = Load("test_m5_house_split");
            LevelDef splitBack = LevelJson.Parse(LevelJson.Serialize(split));
            Assert.AreEqual("Mezzanine", splitBack.Ramps[0].Platform);
            Assert.AreEqual(0.8f, splitBack.Platforms[0].Height, Eps);
        }

        // ----- FloorMap (CONTRACT_M5_v3 15.4) -----

        [Test]
        public void FloorMap_gives_the_platform_height_on_it_the_ramp_slope_along_it_and_0_elsewhere()
        {
            LevelDef l = Base();
            var map = new FloorMap(l);
            Assert.IsFalse(map.IsFlat, "premise: the base has a platform");
            Assert.AreEqual(0.8f, map.HeightAt(5.3f, 0f), Eps, "on the platform");
            Assert.AreEqual(0.8f, map.HeightAt(4.55f, 1.5f), Eps, "on the platform edge (edges included)");
            Assert.AreEqual(0.8f, map.HeightAt(6.05f, -2f), Eps, "on the platform corner");
            Assert.AreEqual(0f, map.HeightAt(4.5f, 1.5f), Eps, "beside the platform");
            Assert.AreEqual(0f, map.HeightAt(-2f, 0f), Eps, "in the other room");
            // The ramp: its X, Z is its centre, it rises +x (yaw 90) from its foot (x = 2.15) to its head (x = 4.55).
            Assert.AreEqual(0f, map.HeightAt(2.15f, -0.25f), Eps, "at the foot");
            Assert.AreEqual(0.4f, map.HeightAt(3.35f, -0.25f), Eps, "half way up");
            Assert.AreEqual(0.8f * 1.8f / 2.4f, map.HeightAt(3.95f, 0.3f), Eps, "three quarters up, near a side");
            Assert.AreEqual(0.8f, map.HeightAt(4.55f, -0.25f), Eps, "at the head, flush with the platform");
            Assert.AreEqual(0f, map.HeightAt(3.35f, 0.45f), Eps, "beside the ramp");
            Assert.AreEqual(0f, map.HeightAt(2.05f, -0.25f), Eps, "before the foot");
            // A ramp rising +z (yaw 0) and one rising -x (yaw 270) toward their platforms.
            l.Ramps[0] = new RampDef { X = 8f, Z = -5f, Width = 1f, Length = 2f, Yaw = 0f, Platform = "Mezzanine" };
            Assert.AreEqual(0.6f, map.HeightAt(8f, -4.5f), Eps, "yaw 0: three quarters up toward +z");
            l.Ramps[0] = new RampDef { X = 1f, Z = 0f, Width = 1f, Length = 2f, Yaw = 270f, Platform = "Mezzanine" };
            Assert.AreEqual(0.2f, map.HeightAt(1.5f, 0f), Eps, "yaw 270: a quarter up toward -x");
            l.Ramps[0].Platform = "Nope";
            Assert.AreEqual(0f, map.HeightAt(1.5f, 0f), Eps, "a ramp to no platform rises to nothing");
        }

        [Test]
        public void FloorMap_reads_the_level_live_and_the_flat_floor_is_0()
        {
            Assert.AreEqual(0f, FloorMap.Flat.HeightAt(5.3f, 0f), Eps);
            Assert.IsTrue(FloorMap.Flat.IsFlat);
            Assert.IsNull(FloorMap.Flat.Level);
            LevelDef l = Base();
            FloorMap cached = l.Floor;
            Assert.AreSame(cached, l.Floor, "LevelDef.Floor is built once");
            Assert.AreSame(l, cached.Level);
            Assert.AreEqual(0.8f, l.FloorHeightAt(5.3f, 0f), Eps, "FloorHeightAt reads the floor");
            l.Platforms.Add(new PlatformDef { Name = "Late", X = -2f, Z = 0f, SizeX = 1f, SizeZ = 1f, Height = 0.6f });
            Assert.AreEqual(0.6f, cached.HeightAt(-2f, 0f), Eps, "a platform added after the first read is seen");
            Assert.AreEqual(new Vector3(-2f, 0.6f, 0f), cached.OnFloor(new Vector3(-2f, 5f, 0f)), "OnFloor replaces the height");
            l.Platforms.Clear();
            l.Ramps.Clear();
            Assert.IsTrue(cached.IsFlat, "no platform and no ramp: flat");
            Assert.AreEqual(0f, cached.HeightAt(5.3f, 0f), Eps);
        }

        [Test]
        public void FloorMap_slope_and_head_height_of_a_ramp()
        {
            LevelDef l = Base();
            Assert.AreEqual(0.8f, l.Floor.HeadHeight(l.Ramps[0]), Eps);
            Assert.AreEqual(Mathf.Atan2(0.8f, 2.4f) * Mathf.Rad2Deg, l.Floor.SlopeOf(l.Ramps[0]), 1e-3f);
            Assert.AreSame(l.Platforms[0], FloorMap.PlatformOf(l, l.Ramps[0]));
        }

        // ----- DoorGeometry (CONTRACT_M5_v3 15.2) -----

        private static void AssertVector(Vector3 expected, Vector3 actual, string what, float tolerance = 1e-4f)
        {
            Assert.Less((expected - actual).magnitude, tolerance, $"{what}: expected {expected}, got {actual}");
        }

        [Test]
        public void Door_closed_pose_fills_the_opening_centred_on_the_wall_line()
        {
            LevelDef l = Base();
            var g = new DoorGeometry(l, Porte(l));
            Assert.IsTrue(g.Valid);
            Assert.IsFalse(g.AlongX, "the shared wall x = 0 runs along z");
            AssertVector(new Vector3(0f, 0f, 0.75f), g.Hinge, "hinge start: the lower z end");
            AssertVector(Vector3.forward, g.AlongDirection, "closed leaf direction");
            AssertVector(Vector3.right, g.Into, "into the swing room b");
            Assert.AreEqual(1, g.SwingRoom, "room b");
            AssertVector(new Vector3(0f, 0f, 1.25f), g.Center, "door centre");
            Pose closed = g.Pose(0f, out Vector3 size);
            float height = 2.1f - Tuning.LeafTopGap;
            AssertVector(new Vector3(1f, height, Tuning.LeafThickness), size, "leaf size");
            AssertVector(new Vector3(0f, height * 0.5f, 1.25f), closed.position, "closed centre");
            AssertVector(Vector3.forward, closed.rotation * Vector3.right, "local x along the leaf");
            AssertVector(Vector3.up, closed.rotation * Vector3.up, "upright");
        }

        [Test]
        public void Door_open_pose_stands_in_the_swing_room_from_the_hinge_and_hinge_end_mirrors_it()
        {
            LevelDef l = Base();
            var g = new DoorGeometry(l, Porte(l));
            float height = 2.1f - Tuning.LeafTopGap;
            Pose open = g.Pose(Tuning.DoorSwingDegrees, out Vector3 _);
            AssertVector(new Vector3(0.5f, height * 0.5f, 0.75f), open.position, "open centre: half the width into b from the hinge");
            AssertVector(Vector3.right, open.rotation * Vector3.right, "open leaf along +x");
            Pose half = g.Pose(45f, out Vector3 _);
            AssertVector(new Vector3(0.5f * Mathf.Sin(45f * Mathf.Deg2Rad), height * 0.5f, 0.75f + 0.5f * Mathf.Cos(45f * Mathf.Deg2Rad)), half.position, "45 deg");
            Porte(l).Hinge = "end";
            var e = new DoorGeometry(l, Porte(l));
            AssertVector(new Vector3(0f, 0f, 1.75f), e.Hinge, "hinge end: the upper z end");
            AssertVector(Vector3.back, e.AlongDirection, "toward the hinge start");
            AssertVector(new Vector3(0.5f, height * 0.5f, 1.75f), e.Pose(90f, out Vector3 _).position, "open from the end");
            AssertVector(new Vector3(0f, height * 0.5f, 1.25f), e.Pose(0f, out Vector3 _).position, "the closed pose is the same");
            Porte(l).Hinge = "start";
            Porte(l).Swing = "a";
            var a = new DoorGeometry(l, Porte(l));
            AssertVector(Vector3.left, a.Into, "swing into a");
            AssertVector(new Vector3(-0.5f, height * 0.5f, 0.75f), a.Pose(90f, out Vector3 _).position, "open into a");
        }

        [Test]
        public void Door_samples_are_the_inset_corners_of_the_leaf_mid_plane_at_its_angle()
        {
            LevelDef l = Base();
            var g = new DoorGeometry(l, Porte(l));
            float inset = Tuning.LeafSampleInset;
            float top = 2.1f - Tuning.LeafTopGap - inset;
            Vector3[] closed = g.Samples(0f);
            Assert.AreEqual(Tuning.LeafSampleCount, closed.Length);
            AssertVector(new Vector3(0f, inset, 0.75f + inset), closed[0], "near low");
            AssertVector(new Vector3(0f, top, 0.75f + inset), closed[1], "near high");
            AssertVector(new Vector3(0f, inset, 1.75f - inset), closed[2], "far low");
            AssertVector(new Vector3(0f, top, 1.75f - inset), closed[3], "far high");
            Vector3[] open = g.Samples(90f);
            AssertVector(new Vector3(inset, inset, 0.75f), open[0], "open near low");
            AssertVector(new Vector3(1f - inset, top, 0.75f), open[3], "open far high");
            var buffer = new Vector3[Tuning.LeafSampleCount];
            g.Samples(30f, buffer);
            Vector3[] at30 = g.Samples(30f);
            for (int i = 0; i < buffer.Length; i++)
            {
                AssertVector(at30[i], buffer[i], "buffer form " + i);
                Pose pose = g.Pose(30f, out Vector3 _);
                Vector3 local = Quaternion.Inverse(pose.rotation) * (buffer[i] - pose.position);
                Assert.AreEqual(0f, local.z, 1e-4f, "a sample lies on the leaf's mid plane");
            }
        }

        [Test]
        public void Door_swing_sector_is_the_quarter_disc_of_radius_the_width_in_the_swing_room()
        {
            LevelDef l = Base();
            var g = new DoorGeometry(l, Porte(l));
            Assert.IsTrue(g.InSwingSector(new Vector3(0.5f, 0f, 1.25f)), "in front of the opening in b");
            Assert.IsTrue(g.InSwingSector(new Vector3(0.95f, 0f, 0.8f)), "near the open pose");
            Assert.IsFalse(g.InSwingSector(new Vector3(-0.5f, 0f, 1.25f)), "in room a");
            Assert.IsFalse(g.InSwingSector(new Vector3(0.9f, 0f, 1.6f)), "beyond the radius");
            Assert.IsFalse(g.InSwingSector(new Vector3(0.5f, 0f, 0.6f)), "below the hinge");
            Assert.AreEqual(0f, g.DistanceToSector(new Vector3(0.3f, 0f, 1f)), Eps);
            Assert.AreEqual(0.5f, g.DistanceToSector(new Vector3(0f, 0f, 2.25f)), Eps, "past the closed leaf's free end");
            Assert.AreEqual(0.3f, g.DistanceToSector(new Vector3(-0.3f, 0f, 1f)), Eps, "behind the wall line");
            Assert.IsTrue(g.SectorOverlapsDisc(new Vector3(1.1f, 0f, 1.25f), Tuning.InhabitantRadius), "a station 0.21 m from the arc");
            Assert.IsFalse(g.SectorOverlapsDisc(new Vector3(1.2f, 0f, 1.25f), Tuning.InhabitantRadius), "a station 0.3 m from the arc");
            Assert.IsTrue(g.SectorOverlapsRect(new Vector3(0.4f, 0f, 1.25f), 0.45f, 0.45f, 0f), "a chair in the sector");
            Assert.IsFalse(g.SectorOverlapsRect(new Vector3(-0.5f, 0f, 1.25f), 0.45f, 0.45f, 0f), "a chair in room a");
            Assert.IsFalse(g.SectorOverlapsRect(new Vector3(0.225f, 0f, 0.5f), 0.45f, 0.45f, 0f), "a chair touching the hinge line from below");
            Assert.IsTrue(g.SectorOverlapsRect(new Vector3(0.9f, 0f, 1.7f), 0.45f, 0.45f, 0f), "a chair whose corner enters the arc");
            Assert.IsFalse(g.SectorOverlapsRect(new Vector3(0.9f, 0f, 1.7f), 0.45f, 0.45f, 45f), "the same chair turned 45 deg stays clear of it");
        }

        [Test]
        public void Door_reach_needs_the_distance_and_a_footprint_outside_the_sector()
        {
            LevelDef l = Base();
            var g = new DoorGeometry(l, Porte(l));
            var chair = new Vector3(0.45f, 0.9f, 0.45f);
            Assert.IsTrue(g.InReach(new Vector3(-0.5f, 0f, 1.25f), chair, 0f), "0.5 m away in room a");
            Assert.IsTrue(g.InReach(new Vector3(-0.5f, 0f, 1.25f), chair, 37f), "no facing condition");
            Assert.IsTrue(g.InReach(new Vector3(-0.8f, 0f, 1.5f), chair, 0f), "0.84 m away");
            Assert.IsFalse(g.InReach(new Vector3(-0.9f, 0f, 1.25f), chair, 0f), "0.9 m away: beyond DoorReach");
            Assert.IsFalse(g.InReach(new Vector3(0.6f, 0f, 1.25f), chair, 0f), "in the swing sector");
            Assert.IsTrue(g.InReach(new Vector3(0.3f, 0f, 0.5f), chair, 0f), "in b below the hinge, outside the sector");
            Porte(l).Leaf = "open";
            Assert.IsTrue(new DoorGeometry(l, Porte(l)).InReach(new Vector3(-0.5f, 0f, 1.25f), chair, 0f), "reach is geometry only");
        }

        [Test]
        public void Door_nav_boxes_cover_the_doorway_through_the_wall_and_the_open_leaf_from_the_wall_face()
        {
            LevelDef l = Base();
            var g = new DoorGeometry(l, Porte(l));
            g.DoorwayBox(out Vector3 center, out Quaternion rotation, out Vector3 size);
            AssertVector(new Vector3(0f, center.y, 1.25f), center, "doorway box centre");
            Assert.Less(center.y - size.y * 0.5f, 0f, "the doorway box holds the floor");
            Assert.Greater(center.y + size.y * 0.5f, 0f, "the doorway box holds the floor");
            AssertVector(Vector3.forward, rotation * Vector3.right, "along the wall");
            Assert.AreEqual(1f, size.x, Eps, "the opening's width");
            Assert.AreEqual(0.1f + 2f * Tuning.DoorAreaOverhang, size.z, Eps, "through the wall and its overhang");
            g.OpenLeafBox(out center, out rotation, out size);
            float from = 0.05f;
            float to = 1f + Tuning.NavAgentRadius;
            AssertVector(new Vector3((from + to) * 0.5f, center.y, 0.75f), center, "open leaf box centre");
            Assert.AreEqual(to - from, size.z, Eps, "from the wall face to past the free end");
            Assert.AreEqual(Tuning.LeafThickness + 2f * Tuning.NavAgentRadius, size.x, Eps, "the leaf grown by the agent radius");
            Assert.AreEqual(0f, g.DistanceToLeaf(new Vector3(0.5f, 0f, 0.75f), 90f), Eps, "on the open leaf");
            Assert.AreEqual(0.3f - Tuning.LeafThickness * 0.5f, g.DistanceToLeaf(new Vector3(0.5f, 0f, 1.05f), 90f), Eps, "beside it");
        }

        // ----- Validator: leaves (CONTRACT_M5_v3 3, 15.2, 15.10) -----

        [Test]
        public void Leaf_hinge_swing_and_id_only_on_doors()
        {
            LevelDef l = Base();
            l.Windows.Add(new OpeningDef { X = -2.05f, Z = -2.05f, Width = 1f, Bottom = 0.9f, Top = 2.1f, Leaf = "closed" });
            AssertRejected(l, "window 1 has a leaf, hinge, swing or id");
            l = Base();
            l.Doors[1].Hinge = "start";
            AssertRejected(l, "door 2 has a hinge, swing or id but no leaf");
            AssertNoIssue(Base(), "only doors carry them");
            AssertNoIssue(Base(), "but no leaf");
        }

        [Test]
        public void Leaf_needs_a_unique_id()
        {
            LevelDef l = Base();
            Porte(l).Id = null;
            AssertRejected(l, "door 1 has a leaf but no id");
            l = Base();
            l.Doors[1].Leaf = "open";
            l.Doors[1].Id = "porte";
            l.Doors[1].Swing = "a";
            AssertRejected(l, "door id 'porte' is used twice");
            l.Doors[1].Id = "sortie";
            AssertNoIssue(l, "is used twice");
            AssertNoIssue(l, "no id");
        }

        [Test]
        public void Leaf_value_and_hinge_are_known_values()
        {
            LevelDef l = Base();
            Porte(l).Leaf = "ajar";
            AssertRejected(l, "door 1 leaf 'ajar' is neither open nor closed");
            l = Base();
            Porte(l).Hinge = "middle";
            AssertRejected(l, "door 1 hinge 'middle' is neither start nor end");
            l = Base();
            Porte(l).Hinge = "end";
            Porte(l).Leaf = "open";
            AssertNoIssue(l, "is neither");
        }

        [Test]
        public void Leaf_needs_a_swing_room_on_either_side_of_it()
        {
            LevelDef l = Base();
            Porte(l).Swing = null;
            AssertRejected(l, "door 1 has a leaf but no swing room");
            Porte(l).Swing = "c";
            AssertRejected(l, "door 1 swings into 'c', which is not a room on either side of it");
            Porte(l).Swing = "a";
            AssertNoIssue(l, "swing room");
            AssertNoIssue(l, "not a room on either side");
        }

        [Test]
        public void At_most_two_leaves_per_level()
        {
            LevelDef l = Base();
            l.Doors[1].Leaf = "open";
            l.Doors[1].Id = "sortie";
            l.Doors[1].Swing = "a";
            AssertNoIssue(l, "door leaves: at most");
            l.Doors.Add(new OpeningDef { X = 0f, Z = -1.25f, Width = 1f, Top = 2.1f, Leaf = "closed", Id = "trois", Swing = "a" });
            AssertRejected(l, "3 door leaves: at most 2 per level");
        }

        [Test]
        public void Swing_sector_is_free_of_props_decoys_rugs_stations_seat_homes_and_the_spawn()
        {
            LevelDef l = Base();
            l.Props.Add(new PropDef { Name = "Stool", Kind = "box", X = 0.5f, Z = 1.25f, SizeX = 0.3f, SizeY = 0.5f, SizeZ = 0.3f });
            AssertRejected(l, "door 1 (porte) swing sector overlaps prop Stool");
            l.Props[1].X = -0.5f;
            AssertNoIssue(l, "swing sector overlaps prop");

            l = Base();
            l.Decoys.Add(new DecoyDef { Kind = "chair", X = 0.5f, Z = 1f, Color = "#8C5A36" });
            AssertRejected(l, "swing sector overlaps decoy 1");

            l = Base();
            l.Rugs.Add(new RugDef { X = 0.6f, Z = 1.2f, SizeX = 0.4f, SizeZ = 0.4f });
            AssertRejected(l, "swing sector overlaps rug 1");
            l.Rugs[0].X = 1.8f;
            AssertNoIssue(l, "swing sector overlaps rug");

            l = Base();
            l.Inhabitants[0].Stations[1].X = 1.1f;
            l.Inhabitants[0].Stations[1].Z = 1.25f;
            AssertRejected(l, "swing sector overlaps inhabitant H station 2");
            l.Inhabitants[0].Stations[1].X = 1.2f;
            AssertNoIssue(l, "swing sector overlaps inhabitant");

            l = Base();
            l.Inhabitants[0].Stations[1] = new StationDef
            {
                X = 1.1f, Z = 1.25f, Facing = 90f, Dwell = 2f, Sit = StationDef.SitOnPlayer, Seat = new SeatDef { X = 0.6f, Z = 1.25f, Yaw = 90f },
            };
            AssertRejected(l, "swing sector overlaps the seat home of inhabitant H station 2");

            l = Base();
            l.Player.X = 0.5f;
            l.Player.Z = 1.2f;
            AssertRejected(l, "swing sector overlaps the player spawn");
        }

        // ----- Validator: the split level (CONTRACT_M5_v3 2, 15.4; CONTRACT_M5 16.6) -----

        [Test]
        public void Platform_is_named_inside_a_room_and_between_the_height_bounds()
        {
            LevelDef l = Base();
            l.Platforms[0].Height = 0.4f;
            AssertRejected(l, "platform Mezzanine height", "is outside");
            l.Platforms[0].Height = 1.2f;
            AssertRejected(l, "platform Mezzanine height", "is outside");
            l.Platforms[0].Height = Tuning.PlatformMaxHeight;
            AssertNoIssue(l, "is outside");
            l = Base();
            l.Platforms[0].X = 5.5f;
            AssertRejected(l, "platform Mezzanine is not inside a room");
            l = Base();
            l.Platforms.Add(new PlatformDef { X = -2f, Z = -1f, SizeX = 1f, SizeZ = 1f, Height = 0.6f });
            AssertRejected(l, "has no name: a ramp names its platform");
            l.Platforms[1].Name = "Mezzanine";
            AssertRejected(l, "platform name Mezzanine is used twice");
            l.Platforms[1].Name = "Balcon";
            AssertNoIssue(l, "is used twice");
            AssertNoIssue(l, "not inside a room");
        }

        [Test]
        public void Platforms_and_ramps_never_overlap()
        {
            LevelDef l = Base();
            l.Platforms.Add(new PlatformDef { Name = "Over", X = 5f, Z = 1.5f, SizeX = 1f, SizeZ = 1f, Height = 0.6f });
            AssertRejected(l, "platform Mezzanine and platform Over overlap: no walkable surface above another");
            l = Base();
            l.Ramps.Add(new RampDef { X = 5.3f, Z = 0f, Width = 1.2f, Length = 2f, Yaw = 0f, Platform = "Mezzanine" });
            AssertRejected(l, "platform Mezzanine and ramp 2 overlap");
            AssertNoIssue(Base(), "overlap: no walkable surface");
        }

        [Test]
        public void Ramp_names_a_platform_turns_by_right_angles_and_rises_at_most_20_degrees()
        {
            LevelDef l = Base();
            l.Ramps[0].Platform = "Nope";
            AssertRejected(l, "ramp 1 leads to 'Nope', which is not a platform of the level");
            l = Base();
            l.Ramps[0].Yaw = 45f;
            AssertRejected(l, "ramp 1 yaw", "is not a multiple of 90");
            l = Base();
            l.Ramps[0].Yaw = -270f;
            AssertNoIssue(l, "is not a multiple of 90");
            l = Base();
            l.Ramps[0].Length = 1.6f;
            l.Ramps[0].X = 3.75f;
            AssertRejected(l, "ramp 1 rises", "deg: at most");
            AssertNoIssue(Base(), "rises");
        }

        [Test]
        public void Ramp_is_flush_at_its_head_and_at_its_foot()
        {
            LevelDef l = Base();
            l.Ramps[0].X = 3.25f;
            AssertRejected(l, "ramp 1 head is not flush with the edge of platform Mezzanine facing it");
            l = Base();
            l.Ramps[0].Z = 1.6f;
            AssertRejected(l, "ramp 1 head is not flush", "Mezzanine");
            l = Base();
            l.Platforms.Add(new PlatformDef { Name = "Step", X = 1.8f, Z = -0.25f, SizeX = 0.7f, SizeZ = 1.2f, Height = 0.6f });
            AssertRejected(l, "ramp 1 foot is not on the floor");
            AssertNoIssue(Base(), "is not flush");
            AssertNoIssue(Base(), "foot is not on the floor");
        }

        [Test]
        public void Ramp_and_corridor_widths_follow_the_body()
        {
            LevelDef l = Base();
            l.Ramps[0].Width = 1f;
            AssertRejected(l, "ramp 1 is", "m wide: the chair needs at least");
            l = Base();
            l.Rooms.Add(new RoomDef { Id = "c", X = -2.05f, Z = 2.6f, SizeX = 4f, SizeZ = 1f, WallHeight = 2.7f, WallThickness = 0.1f });
            l.Doors.Add(new OpeningDef { X = -2.05f, Z = 2.05f, Width = 1f, Top = 2.1f });
            AssertRejected(l, "room c is", "m wide: a corridor is at least");
            l.Rooms[2].SizeZ = 1.2f;
            l.Rooms[2].Z = 2.7f;
            AssertNoIssue(l, "a corridor is at least");
            Assert.AreEqual(Tuning.PassageWidth, LevelValidator.PassageWidth(BodyDef.For("chair")), Eps);
            Assert.AreEqual(Tuning.ArmchairPassageWidth, LevelValidator.PassageWidth(BodyDef.For("armchair")), Eps);
        }

        private static void Armchair(LevelDef l)
        {
            BodyDef body = BodyDef.For("armchair");
            l.Player.Kind = "armchair";
            l.Player.SizeX = body.Size.x;
            l.Player.SizeY = body.Size.y;
            l.Player.SizeZ = body.Size.z;
        }

        [Test]
        public void Armchair_ramp_is_1_5_m_wide_with_its_axis_on_the_audit_cell_grid()
        {
            LevelDef l = Base();
            Armchair(l);
            AssertRejected(l, "ramp 1 is", "m wide: the armchair needs at least");
            l.Ramps[0].Width = 1.5f;
            AssertNoIssue(l, "ramp 1");
            l.Ramps[0].Z = 0f;
            AssertRejected(l, "ramp 1: the armchair's ramp has its axis on a line of audit cell centres");
            l = Base();
            l.Ramps[0].Z = 0f;
            AssertNoIssue(l, "ramp 1:");
        }

        [Test]
        public void No_platform_or_ramp_over_a_door_threshold()
        {
            LevelDef l = Base();
            l.Platforms.Add(new PlatformDef { Name = "Landing", X = 0.8f, Z = -1.25f, SizeX = 1.4f, SizeZ = 1f, Height = 0.6f });
            AssertNoIssue(l, "threshold");
            l.Doors.Add(new OpeningDef { X = 0f, Z = -1.25f, Width = 1f, Top = 2.1f });
            AssertRejected(l, "platform Landing stands over the threshold of door 3");
        }

        [Test]
        public void Nothing_straddles_two_heights_or_lies_on_a_ramp()
        {
            LevelDef l = Base();
            l.Props.Add(new PropDef { Name = "Edge", Kind = "box", X = 4.55f, Z = 1.5f, SizeX = 0.6f, SizeY = 0.5f, SizeZ = 0.6f });
            AssertRejected(l, "prop Edge straddles the edge of platform Mezzanine");
            l.Props[1].X = 5.3f;
            AssertNoIssue(l, "straddles");
            l = Base();
            l.Decoys.Add(new DecoyDef { Kind = "chair", X = 3.35f, Z = -0.25f, Color = "#8C5A36" });
            AssertRejected(l, "decoy 1 lies on ramp 1");
            l = Base();
            l.Rugs.Add(new RugDef { X = 4.6f, Z = 1.5f, SizeX = 0.6f, SizeZ = 0.6f });
            AssertRejected(l, "rug 1 straddles the edge of platform Mezzanine");
            l = Base();
            l.Inhabitants[0].Stations[1].X = 4.5f;
            l.Inhabitants[0].Stations[1].Z = 1.5f;
            AssertRejected(l, "inhabitant H station 2 straddles");
            l.Inhabitants[0].Stations[1].X = 5.3f;
            AssertNoIssue(l, "station 2 straddles");
            l = Base();
            l.Player.X = 3f;
            l.Player.Z = -0.3f;
            AssertRejected(l, "player spawn lies on ramp 1");
            l = Base();
            l.Exit.X = 3f;
            l.Exit.Z = -0.3f;
            AssertRejected(l, "exit zone lies on ramp 1");
        }

        // ----- Validator: watchers (CONTRACT_M5 3, 16.7; CONTRACT_M5_v3 4, 15.6, 15.10) -----

        private static InhabitantDef Human(string name, float x, float z)
        {
            return new InhabitantDef { Name = name, Stations = new List<StationDef> { new StationDef { X = x, Z = z, Dwell = 2f } } };
        }

        [Test]
        public void At_most_three_humans_and_one_dog()
        {
            LevelDef l = Base();
            l.Inhabitants.Add(Human("H2", -2.5f, -0.5f));
            l.Inhabitants.Add(Human("H3", -1.5f, -0.5f));
            AssertNoIssue(l, "humans: at most");
            l.Inhabitants.Add(Human("H4", -3f, 0.5f));
            AssertRejected(l, "4 humans: at most 3 per level");
            l = Base();
            var second = Human("Rex2", -1.5f, -1.5f);
            second.Kind = "dog";
            l.Inhabitants.Add(second);
            AssertRejected(l, "2 dogs: at most one per level");
        }

        [Test]
        public void Kind_personality_and_pattern_are_known()
        {
            LevelDef l = Base();
            l.Inhabitants[0].Kind = "cat";
            AssertRejected(l, "inhabitant H kind 'cat' is neither human nor dog");
            l.Inhabitants[0].Kind = "human";
            AssertNoIssue(l, "is neither human nor dog");
            l.Inhabitants[0].Personality = "grumpy";
            AssertRejected(l, "inhabitant H personality 'grumpy' is not one of");
            l.Inhabitants[0].Personality = "dog";
            AssertRejected(l, "inhabitant H has the dog personality but is not of kind dog");
            l.Inhabitants[0].Personality = "tidy";
            AssertNoIssue(l, "personality");
            l.Inhabitants[0].Pattern = "random";
            AssertRejected(l, "inhabitant H pattern 'random' is not one of");
            l.Inhabitants[0].Pattern = "pingpong";
            AssertNoIssue(l, "pattern");
        }

        [Test]
        public void Seed_only_with_wander_and_each_pattern_has_enough_stations()
        {
            LevelDef l = Base();
            l.Inhabitants[0].Seed = 5;
            AssertRejected(l, "inhabitant H has a seed but its pattern is loop");
            l.Inhabitants[0].Pattern = "wander";
            AssertRejected(l, "inhabitant H wanders over 2 stations: wander needs 3 or more");
            l.Inhabitants[0].Stations.Add(new StationDef { X = -3f, Z = -0.5f, Dwell = 2f });
            AssertNoIssue(l, "inhabitant H");
            l = Base();
            l.Inhabitants[0].Pattern = "pingpong";
            l.Inhabitants[0].Stations.RemoveAt(1);
            AssertRejected(l, "inhabitant H ping-pongs over 1 station: pingpong needs 2 or more");
            l.Inhabitants[0].Stations.Add(new StationDef { X = -3f, Z = -0.5f, Dwell = 2f });
            AssertNoIssue(l, "ping-pongs");
            l.Inhabitants[0].Seed = -1;
            l.Inhabitants[0].Pattern = "wander";
            l.Inhabitants[0].Stations.Add(new StationDef { X = -3f, Z = 0.5f, Dwell = 2f });
            AssertRejected(l, "inhabitant H seed -1 is negative");
        }

        [Test]
        public void Only_a_dog_sleeps_and_a_dog_never_sits_nor_glances()
        {
            LevelDef l = Base();
            l.Inhabitants[0].Stations[0].Sleep = true;
            AssertRejected(l, "inhabitant H station 1 sleeps: only a dog sleeps");
            AssertNoIssue(Base(), "sleeps");
            l = Base();
            l.Inhabitants[1].Stations[1].Sit = "Crate";
            AssertRejected(l, "inhabitant Rex station 2 sits: a dog never sits");
            l = Base();
            l.Inhabitants[1].Stations[1].Glances.Add(new GlanceDef { Offset = 0.5f, Yaw = 30f, Hold = 0.5f });
            AssertRejected(l, "inhabitant Rex station 2 glances: a dog has no glances");
            l.Inhabitants[1].Kind = null;
            AssertNoIssue(l, "glances: a dog");
        }

        [Test]
        public void A_prop_named_by_a_sit_has_a_unique_name()
        {
            LevelDef l = Base();
            l.Props.Add(new PropDef { Name = "Sofa", Kind = "sofa", X = -2f, Z = -1.5f, SizeX = 1.6f, SizeY = 0.85f, SizeZ = 0.8f });
            l.Inhabitants[0].Stations[0] = new StationDef { X = -2f, Z = -0.95f, Facing = 0f, Dwell = 2f, Sit = "Sofa" };
            AssertNoIssue(l, "props are named");
            l.Props.Add(new PropDef { Name = "Sofa", Kind = "box", X = 3f, Z = 1.5f, SizeX = 0.5f, SizeY = 0.5f, SizeZ = 0.5f });
            AssertRejected(l, "2 props are named Sofa: a prop named by a sit has a unique name");
            l.Inhabitants[0].Stations[0].Sit = null;
            AssertNoIssue(l, "props are named");
        }

        // ----- Validator: lessons, route, load -----

        [Test]
        public void Lesson_door_pet_and_split_need_their_mechanic()
        {
            LevelDef l = Base();
            l.Lesson = LevelDef.LessonDoor;
            AssertNoIssue(l, "lesson");
            Porte(l).Leaf = "open";
            AssertRejected(l, "lesson door needs a closed leaf");
            l = Base();
            l.Lesson = LevelDef.LessonPet;
            AssertNoIssue(l, "lesson");
            l.Inhabitants.RemoveAt(1);
            AssertRejected(l, "lesson pet needs a dog");
            l = Base();
            l.Lesson = LevelDef.LessonSplit;
            AssertNoIssue(l, "lesson");
            l.Ramps.Clear();
            l.Platforms.Clear();
            AssertRejected(l, "lesson split needs a platform");
        }

        [Test]
        public void Route_open_names_a_leaf_of_the_level()
        {
            LevelDef l = Base();
            l.DesignerRoute.Add(new RouteStepDef { X = -0.5f, Z = 1.25f, At = 0.5f, Action = RouteStepDef.ActionOpen, Door = "porte" });
            AssertNoIssue(l, "designer route");
            l.DesignerRoute[0].Door = "nope";
            AssertRejected(l, "designer route waypoint 1 opens door 'nope', which is not a leaf of the level");
            l.DesignerRoute[0].Door = null;
            AssertRejected(l, "designer route waypoint 1 opens door ''");
            l.DesignerRoute[0] = new RouteStepDef { X = -0.5f, Z = 1.25f, At = 0.5f, Door = "porte" };
            AssertRejected(l, "designer route waypoint 1 names door 'porte' but its action is not open");
            l.DesignerRoute[0] = new RouteStepDef { X = -0.5f, Z = 1.25f, At = 0.5f, Action = "kick" };
            AssertRejected(l, "designer route waypoint 1 action 'kick' is neither toggle nor rightup");
        }

        [Test]
        public void Load_is_a_known_kind_and_never_on_the_floor_lamp()
        {
            LevelDef l = Base();
            l.Player.Load = "vase";
            AssertNoIssue(l, "load");
            l.Player.Load = "anvil";
            AssertRejected(l, "player load 'anvil' is not one of vase, books, plant");
            l = Base();
            BodyDef lamp = BodyDef.For("floor_lamp");
            l.Player.Kind = "floor_lamp";
            l.Player.SizeX = lamp.Size.x;
            l.Player.SizeY = lamp.Size.y;
            l.Player.SizeZ = lamp.Size.z;
            AssertNoIssue(l, "load");
            l.Player.Load = "books";
            AssertRejected(l, "player load 'books' on the floor_lamp: the floor lamp carries no load");
        }

        // ----- Validator, wave 5B: the robot (CONTRACT_M5 4, 16.8) -----

        /// <summary>
        /// The base fixture with a robot in room b: a triangle along b's south wall, clear of the ramp (z from -0.85), the
        /// platform (x from 4.55) and the leaf's swing sector (x in [0, 1], z in [0.75, 1.75]), and far from the spawn, the
        /// exit and every seat home (both in room a).
        /// </summary>
        private static LevelDef WithRobot()
        {
            LevelDef l = Base();
            l.Robots.Add(new RobotDef
            {
                Name = "Robi",
                Loop = new List<PointDef> { Point(1f, -1.6f), Point(4f, -1.6f), Point(1f, -1.1f) },
            });
            return l;
        }

        private static PointDef Point(float x, float z) => new PointDef { X = x, Z = z };

        private static RobotDef Robi(LevelDef l) => l.Robots[0];

        [Test]
        public void Robot_fixture_is_valid_and_round_trips_through_json()
        {
            LevelDef l = WithRobot();
            AssertValid(l, "the base fixture with its robot");
            l.Lesson = LevelDef.LessonRobot;
            AssertValid(l, "a robot lesson with its robot");
            LevelDef back = LevelJson.Parse(LevelJson.Serialize(l));
            Assert.AreEqual(1, back.Robots.Count);
            Assert.AreEqual("Robi", back.Robots[0].Name);
            Assert.AreEqual(3, back.Robots[0].Loop.Count);
            Assert.AreEqual(4f, back.Robots[0].Loop[1].X, Eps);
            AssertValid(back, "the robot read back");
        }

        [Test]
        public void House_robot_fixture_crosses_a_doorway_without_a_leaf()
        {
            const string id = "test_m5_house_robot";
            Assert.IsTrue(File.Exists(Folder + id + ".json"), id + " is missing");
            LevelDef l = Load(id);
            Assert.AreEqual(id, l.Id, "the id inside the file matches its name");
            AssertValid(l, id);
            CollectionAssert.DoesNotContain(LevelManifest.Parse(File.ReadAllText(Folder + "levels.json")), id, "a test level");
            Assert.AreEqual(1, l.Robots.Count);
            Assert.AreEqual(LevelDef.LessonRobot, l.Lesson);
            Assert.AreEqual("vase", l.Player.Load, "the chair carries a vase (probe step 39l builds the robot and the load)");
            RobotDef robot = l.Robots[0];
            Assert.AreEqual("a", l.RoomAt(robot.Loop[0].Position).Id, "premise: the loop starts in room a");
            Assert.AreEqual("b", l.RoomAt(robot.Loop[1].Position).Id, "premise: and turns back in room b");
            // The same loop one metre north crosses the shared wall where it has no doorway.
            robot.Loop[0].Z = 0f;
            robot.Loop[1].Z = 0f;
            AssertRejected(l, "robot Robi segment 1 (waypoint 1 to 2) runs into a wall");
        }

        [Test]
        public void At_most_one_robot_per_level()
        {
            LevelDef l = WithRobot();
            AssertNoIssue(l, "robots: at most");
            l.Robots.Add(new RobotDef { Name = "Robo", Loop = new List<PointDef> { Point(1f, -1.6f), Point(1.8f, -1.6f) } });
            AssertRejected(l, "2 robots: at most one per level");
        }

        [Test]
        public void Robot_loop_needs_two_waypoints_distinct_neighbours_a_start_index_and_a_speed_not_negative()
        {
            LevelDef l = WithRobot();
            Robi(l).Loop.RemoveRange(1, 2);
            AssertRejected(l, "robot Robi has 1 waypoint: a loop needs at least 2");
            Robi(l).Loop.Add(Point(4f, -1.6f));
            AssertNoIssue(l, "robot Robi");

            l = WithRobot();
            Robi(l).Start = 3;
            AssertRejected(l, "robot Robi start 3 is not a waypoint index");
            Robi(l).Start = -1;
            AssertRejected(l, "robot Robi start -1 is not a waypoint index");
            Robi(l).Start = 2;
            AssertNoIssue(l, "is not a waypoint index");

            l = WithRobot();
            Robi(l).Loop.Insert(1, Point(1f, -1.6f));
            AssertRejected(l, "robot Robi waypoints 1 and 2 coincide");

            l = WithRobot();
            Robi(l).Speed = -0.5f;
            AssertRejected(l, "robot Robi speed", "is negative");
            Robi(l).Speed = 0.6f;
            AssertNoIssue(l, "is negative");

            l = WithRobot();
            Robi(l).Name = null;
            Robi(l).Loop.RemoveAt(2);
            Robi(l).Loop.RemoveAt(1);
            AssertRejected(l, "robot #1 has 1 waypoint");
        }

        [Test]
        public void Robot_loop_runs_into_no_wall_and_never_leaves_the_house()
        {
            // Through the solid wall between a and b (x = 0, no doorway at z = -1).
            LevelDef l = WithRobot();
            Robi(l).Loop = new List<PointDef> { Point(-1f, -1f), Point(1f, -1f) };
            AssertRejected(l, "robot Robi segment 1 (waypoint 1 to 2) runs into a wall");
            // Through a doorway without a leaf: the disc passes between the jambs (z in [-1.75, -0.75], radius 0.17).
            l.Doors.Add(new OpeningDef { X = 0f, Z = -1.25f, Width = 1f, Top = 2.1f });
            Robi(l).Loop = new List<PointDef> { Point(-1f, -1.25f), Point(1f, -1.25f) };
            AssertNoIssue(l, "runs into a wall");
            // The same doorway 0.1 m from its jamb: the disc touches the wall.
            Robi(l).Loop = new List<PointDef> { Point(-1f, -0.85f), Point(1f, -0.85f) };
            AssertRejected(l, "robot Robi segment 1", "runs into a wall");
            // Through the doorway of the closed leaf: its swing sector covers the doorway's mouth.
            l = WithRobot();
            Robi(l).Loop = new List<PointDef> { Point(-1f, 1.25f), Point(1.5f, 1.25f) };
            AssertRejected(l, "robot Robi segment 1", "runs into a wall");
            AssertRejected(l, "robot Robi segment 1", "enters the swing sector of door 1 (porte)");
            // Out of the house through the exit door, and a disc grazing the outer wall.
            l = WithRobot();
            Robi(l).Loop = new List<PointDef> { Point(-3f, -1.25f), Point(-4.5f, -1.25f) };
            AssertRejected(l, "robot Robi segment 1", "runs into a wall");
            l = WithRobot();
            Robi(l).Loop[0].Z = -1.9f;
            AssertRejected(l, "robot Robi segment 1", "runs into a wall");
            Robi(l).Loop[0].Z = -1.83f;
            Robi(l).Loop[1].Z = -1.83f;
            AssertNoIssue(l, "runs into a wall");
        }

        [Test]
        public void Robot_loop_stays_on_the_floor_level()
        {
            LevelDef l = WithRobot();
            Robi(l).Loop[1].X = 4.5f;
            AssertRejected(l, "robot Robi segment 1 (waypoint 1 to 2) leaves the floor level: it touches platform Mezzanine");
            Robi(l).Loop[1].X = 4.35f;
            AssertNoIssue(l, "platform Mezzanine");
            l = WithRobot();
            Robi(l).Loop[2] = Point(3f, -0.75f);
            AssertRejected(l, "leaves the floor level: it touches ramp 1");
            Robi(l).Loop[2] = Point(3f, -1.05f);
            AssertNoIssue(l, "leaves the floor level");
        }

        [Test]
        public void Robot_loop_keeps_its_radius_from_props_and_decoys()
        {
            // The crate in room a covers x in [-3.6, -3.0], z in [1.2, 1.8].
            LevelDef l = WithRobot();
            Robi(l).Loop = new List<PointDef> { Point(-2.9f, 1f), Point(-2.9f, 1.6f) };
            AssertRejected(l, "robot Robi segment 1 (waypoint 1 to 2) touches prop Crate");
            Robi(l).Loop = new List<PointDef> { Point(-2.8f, 1f), Point(-2.8f, 1.6f) };
            AssertNoIssue(l, "touches prop");
            // A decoy chair at (1.5, -0.9) covers x from 1.275 and z down to -1.125; segment 2 passes 0.02 m below its corner.
            l = WithRobot();
            l.Decoys.Add(new DecoyDef { Kind = "chair", X = 1.5f, Z = -0.9f, Color = "#8C5A36" });
            AssertRejected(l, "robot Robi segment 2 (waypoint 2 to 3) touches decoy 1");
            l.Decoys[0].Z = -0.5f;
            AssertNoIssue(l, "touches decoy");
        }

        [Test]
        public void Robot_loop_stays_out_of_leaf_swing_sectors_and_off_the_leaf()
        {
            // The sector of "porte": the quarter disc of radius 1 about the hinge (0, 0.75), in b.
            LevelDef l = WithRobot();
            Robi(l).Loop = new List<PointDef> { Point(1.05f, 1.25f), Point(3f, 1.25f) };
            AssertRejected(l, "robot Robi segment 1 (waypoint 1 to 2) enters the swing sector of door 1 (porte)");
            Robi(l).Loop[0].X = 1.1f;
            AssertNoIssue(l, "swing sector");
            // Below the hinge line: 0.2 m from the sector is clear of it, but the open leaf (0.04 m thick along z = 0.75)
            // is then 0.18 m away; at 0.18 m from the sector it is 0.16 m away, inside the robot's radius.
            l = WithRobot();
            Robi(l).Loop = new List<PointDef> { Point(0.5f, 0.55f), Point(2f, 0.55f) };
            AssertNoIssue(l, "robot Robi segment 1");
            Robi(l).Loop = new List<PointDef> { Point(0.5f, 0.57f), Point(2f, 0.57f) };
            AssertNoIssue(l, "swing sector");
            AssertRejected(l, "robot Robi segment 1 (waypoint 1 to 2) touches the leaf of door 1 (porte)");
        }

        [Test]
        public void Robot_loop_keeps_one_metre_from_the_spawn_the_seat_homes_and_the_exit()
        {
            // The spawn in b, 0.78 m from segment 3, then 1.3 m away.
            LevelDef l = WithRobot();
            l.Player.X = 1.5f;
            l.Player.Z = -0.4f;
            AssertRejected(l, "robot Robi passes", "m from the player spawn: at least 1 m");
            l.Player.Z = 0.2f;
            AssertNoIssue(l, "from the player spawn");

            // The exit zone in b: 0.66 m from segment 3, then 1.16 m away.
            l = WithRobot();
            l.Exit.X = 1.5f;
            l.Exit.Z = 0f;
            AssertRejected(l, "robot Robi passes", "m from the exit zone: at least 1 m");
            l.Exit.Z = 0.5f;
            AssertNoIssue(l, "from the exit zone");

            // A seat home in b, 0.5 m from segment 3, then 1.3 m away (its station 0.5 m in front of it, facing its yaw).
            l = WithRobot();
            l.Inhabitants[0].Stations[1] = new StationDef
            {
                X = 1.5f, Z = -0.15f, Facing = 0f, Dwell = 2f, Sit = StationDef.SitOnPlayer, Seat = new SeatDef { X = 1.5f, Z = -0.65f, Yaw = 0f },
            };
            AssertRejected(l, "robot Robi passes", "m from the seat home of inhabitant H station 2: at least 1 m");
            l.Inhabitants[0].Stations[1] = new StationDef
            {
                X = 1.5f, Z = 0.7f, Facing = 0f, Dwell = 2f, Sit = StationDef.SitOnPlayer, Seat = new SeatDef { X = 1.5f, Z = 0.2f, Yaw = 0f },
            };
            AssertNoIssue(l, "from the seat home");
            AssertNoIssue(l, "seat home");
        }

        [Test]
        public void Disc_free_space_and_segment_distance_helpers()
        {
            LevelDef l = Base();
            List<Rect> free = LevelValidator.DiscFreeSpace(l, l.AllRooms(), 0.2f);
            Assert.AreEqual(2, free.Count, "two rooms; the only doorway between them has a leaf and the other one is outer");
            Assert.AreEqual(-3.85f, free[0].xMin, Eps);
            Assert.AreEqual(1.8f, free[0].yMax, Eps);
            l.Doors.Add(new OpeningDef { X = 0f, Z = -1.25f, Width = 1f, Top = 2.1f });
            free = LevelValidator.DiscFreeSpace(l, l.AllRooms(), 0.2f);
            Assert.AreEqual(3, free.Count, "a doorway without a leaf between two rooms adds its band");
            Assert.AreEqual(-0.25f, free[2].xMin, Eps, "the band through the wall: the wall line less the thickness and the radius");
            Assert.AreEqual(0.25f, free[2].xMax, Eps);
            Assert.AreEqual(-1.55f, free[2].yMin, Eps, "the doorway's width less the radius at each jamb");
            Assert.AreEqual(-0.95f, free[2].yMax, Eps);
            Assert.IsTrue(LevelValidator.SegmentCovered(free, new Vector3(-2f, 0f, -1.25f), new Vector3(2f, 0f, -1.25f)));
            Assert.IsFalse(LevelValidator.SegmentCovered(free, new Vector3(-2f, 0f, -0.5f), new Vector3(2f, 0f, -0.5f)));
            Assert.IsFalse(LevelValidator.SegmentCovered(free, new Vector3(-9f, 0f, 0f), new Vector3(-8f, 0f, 0f)), "outside every room");
            Assert.AreEqual(0.5f, LevelValidator.DistanceToRect(new Vector3(1.5f, 0f, 0f), Vector3.zero, 2f, 1f, 0f), Eps);
            Assert.AreEqual(1f, LevelValidator.DistanceToRect(new Vector3(1.5f, 0f, 0f), Vector3.zero, 2f, 1f, 90f), Eps, "turned 90 deg");
            Assert.AreEqual(0f, LevelValidator.DistanceToRect(new Vector3(0.2f, 0f, 0.1f), Vector3.zero, 2f, 1f, 0f), Eps, "inside");
            var corner = new Vector3(6f, 0f, 2f);
            Assert.AreEqual(Mathf.Sqrt(2f), LevelValidator.SegmentDistance(new Vector3(0f, 0f, 0f), new Vector3(4f, 0f, 0f),
                p => DistanceToSquare(p, corner)), 1e-3f, "the nearest point of a segment to a square");
            Assert.AreEqual(1f, LevelValidator.SegmentDistance(new Vector3(0f, 0f, 1f), new Vector3(0f, 0f, 9f),
                p => p.magnitude), 1e-3f, "an end is the nearest point");
        }

        private static float DistanceToSquare(Vector3 p, Vector3 center) => LevelValidator.DistanceToRect(p, center, 2f, 2f, 0f);

        // ----- Validator, wave 5B: the rocking chair, the load and the lessons (CONTRACT_M5 5, 6, 8, 10, 16.5) -----

        private const string RockingChair = BodyKinds.RockingChair;

        private static void Rocking(LevelDef l)
        {
            BodyDef body = BodyDef.For(RockingChair);
            Assert.AreEqual(RockingChair, body.Kind, "premise: core's BodyDef has the rocking_chair row");
            Assert.IsTrue(body.Rocks, "premise: the rocking chair rocks");
            l.Player.Kind = RockingChair;
            l.Player.SizeX = body.Size.x;
            l.Player.SizeY = body.Size.y;
            l.Player.SizeZ = body.Size.z;
            l.Player.Model = null;
        }

        [Test]
        public void Rocking_chair_is_a_known_body_with_its_body_size()
        {
            LevelDef l = Base();
            Rocking(l);
            AssertValid(l, "a rocking chair player at its body size");
            l.Decoys.Add(new DecoyDef { Kind = RockingChair, X = -1f, Z = -1.4f, Yaw = 90f, Color = "#8C5A36" });
            AssertNoIssue(l, "is not a furniture body");
            AssertNoIssue(l, "decoy 1");
            l.Player.SizeX = 0.45f;
            AssertRejected(l, "player size", "disagrees with the rocking_chair body size");
        }

        [Test]
        public void No_load_on_the_rocking_chair()
        {
            LevelDef l = Base();
            Rocking(l);
            AssertNoIssue(l, "load");
            l.Player.Load = "vase";
            AssertRejected(l, "player load 'vase' on the rocking_chair: the rocking chair carries no load");
            l = Base();
            l.Player.Load = "vase";
            AssertNoIssue(l, "carries no load");
        }

        [Test]
        public void Lesson_robot_rock_and_load_need_their_mechanic()
        {
            LevelDef l = Base();
            l.Lesson = LevelDef.LessonRobot;
            AssertRejected(l, "lesson robot needs a robot");
            l = WithRobot();
            l.Lesson = LevelDef.LessonRobot;
            AssertNoIssue(l, "lesson");

            l = Base();
            l.Lesson = LevelDef.LessonRock;
            AssertRejected(l, "lesson rock needs a body that rocks (the rocking chair), not the chair");
            Rocking(l);
            AssertNoIssue(l, "lesson");

            l = Base();
            l.Lesson = LevelDef.LessonLoad;
            AssertRejected(l, "lesson load needs a load on the player");
            l.Player.Load = "books";
            AssertNoIssue(l, "lesson");
        }

        [Test]
        public void Lesson_final_needs_three_mechanics_and_mechanics_are_listed_in_order()
        {
            // The base has a closed leaf, a dog and a platform: door, pet and split.
            LevelDef l = Base();
            CollectionAssert.AreEqual(new[] { "door", "pet", "split" }, LevelValidator.MechanicsOf(l));
            l.Lesson = LevelDef.LessonFinal;
            AssertNoIssue(l, "lesson");
            l.Inhabitants.RemoveAt(1);
            AssertRejected(l, "lesson final needs at least 3 of door, pet, split, robot, rock and load; the level has door, split");
            l.Player.Load = "plant";
            AssertNoIssue(l, "lesson");
            CollectionAssert.AreEqual(new[] { "door", "split", "load" }, LevelValidator.MechanicsOf(l));

            l = WithRobot();
            Rocking(l);
            CollectionAssert.AreEqual(new[] { "door", "pet", "split", "robot", "rock" }, LevelValidator.MechanicsOf(l));
            Porte(l).Leaf = "open";
            l.Inhabitants.RemoveAt(1);
            l.Ramps.Clear();
            l.Platforms.Clear();
            l.Robots.Clear();
            l.Lesson = LevelDef.LessonFinal;
            AssertRejected(l, "lesson final needs at least 3", "the level has rock");
            Assert.AreEqual(0, LevelValidator.MechanicsOf(new LevelDef()).Count, "an empty level has none");
            Assert.AreEqual(3, LevelValidator.FinalMechanics);
        }
    }
}
