using System.Collections.Generic;
using System.IO;
using System.Linq;
using Meuble.Core;
using Newtonsoft.Json;
using NUnit.Framework;
using UnityEngine;

namespace Meuble.Tests
{
    /// <summary>
    /// docs/CONTRACT_M4.md 2, 3, 4 and amendments 9.3, 9.5, 9.11 (level data): the player kind selects its BodyDef,
    /// which is the one size source; sit stations and seat homes; the lesson knob; the route step fields; the door
    /// clearance per body. Every negative rule has its own test, on a two room fixture that is valid as built for
    /// every body; the M1 to M3 levels and fixtures still validate.
    /// </summary>
    public sealed class LevelDataM4Tests
    {
        private const string Folder = "Assets/Resources/Levels/";

        private static LevelDef Load(string id) => LevelJson.Parse(File.ReadAllText(Folder + id + ".json"));

        private static readonly string[] OldLevels = { "level1", "level2", "level3" };
        private static readonly string[] OldFixtures = { "test_wait", "test_noise", "test_creak", "test_two_inhabitants" };

        /// <summary>The lesson each body's fixture carries (the chair carries none: null is accepted).</summary>
        private static string LessonOf(string kind)
        {
            switch (kind)
            {
                case BodyKinds.Stool: return LevelDef.LessonCareful;
                case BodyKinds.Armchair: return LevelDef.LessonSit;
                case BodyKinds.FloorLamp: return LevelDef.LessonDark;
                case BodyKinds.OfficeChair: return LevelDef.LessonGlide;
                default: return null;
            }
        }

        /// <summary>
        /// The M2 two room layout (room a: x in [-4, 0], hard; room b: x in [0.1, 4.1], soft; z in [-2, 2]; 1.0 m doors,
        /// exactly the armchair's clearance) with a player of <paramref name="kind"/> at its body size and model, a sofa
        /// and an armchair prop, a chair decoy, one station that sits on the sofa and, for a seat body, one that sits
        /// on the player (its seat home 0.5 m behind the station). The route uses the actions of the body.
        /// </summary>
        private static LevelDef Fixture(string kind)
        {
            BodyDef body = BodyDef.For(kind);
            var stations = new List<StationDef>
            {
                new StationDef { X = -2f, Z = 0f, Facing = 0f, Dwell = 2f },
                // The sofa's seat front: 0.65 m in front of its center, back to it (CONTRACT_M4 10.2).
                new StationDef { X = 2f, Z = 0.5f, Facing = 180f, Dwell = 2f, Sit = "Sofa" },
            };
            if (body.IsSeat)
            {
                // The seat front (the station) 0.5 m in front of the seat home along its yaw, facing that yaw.
                stations[0].Sit = StationDef.SitOnPlayer;
                stations[0].Seat = new SeatDef { X = -2f, Z = -0.5f, Yaw = 0f };
            }
            var route = new List<RouteStepDef>
            {
                new RouteStepDef { X = -1f, Z = 0f, At = 0.2f },
                new RouteStepDef { X = 2f, Z = 0f, At = 3f },
            };
            if (body.Tips)
            {
                route[0].Careful = true;
                route[1].Action = RouteStepDef.ActionRightUp;
            }
            if (body.HasLight)
            {
                route[0].Action = RouteStepDef.ActionToggle;
            }
            return new LevelDef
            {
                Id = "test_m4_" + kind,
                Lesson = LessonOf(kind),
                Rooms = new List<RoomDef>
                {
                    new RoomDef { Id = "a", X = -2f, Z = 0f, SizeX = 4f, SizeZ = 4f, WallHeight = 2.7f, WallThickness = 0.1f, Floor = "hard" },
                    new RoomDef { Id = "b", X = 2.1f, Z = 0f, SizeX = 4f, SizeZ = 4f, WallHeight = 2.7f, WallThickness = 0.1f, Floor = "soft" },
                },
                Doors = new List<OpeningDef>
                {
                    new OpeningDef { X = 0.05f, Z = 0f, Width = 1f, Top = 2.1f },
                    new OpeningDef { X = 4.15f, Z = 1f, Width = 1f, Top = 2.1f },
                },
                Player = new SpawnDef
                {
                    Kind = kind, Model = body.Model, X = -3f, Z = -1f,
                    SizeX = body.Size.x, SizeY = body.Size.y, SizeZ = body.Size.z, Color = "#D7263D",
                },
                Exit = new ZoneDef { X = 3.5f, Z = 1f, SizeX = 0.9f, SizeZ = 0.9f },
                Rugs = new List<RugDef> { new RugDef { X = -2f, Z = 1f, SizeX = 1f, SizeZ = 0.6f, Yaw = 30f, Color = "#2E6DB4" } },
                Decoys = new List<DecoyDef> { new DecoyDef { Kind = BodyKinds.Chair, Model = "kenney.chair", X = -1f, Z = -1.2f, Color = "#8C5A36" } },
                Props = new List<PropDef>
                {
                    new PropDef { Name = "Box", Kind = "box", X = 2f, Z = -1.5f, SizeX = 0.6f, SizeY = 0.8f, SizeZ = 0.6f },
                    new PropDef { Name = "Sofa", Kind = "sofa", Model = "kenney.sofa", X = 2f, Z = 1.15f, SizeX = 1.4f, SizeY = 0.85f, SizeZ = 0.7f },
                    new PropDef { Name = "Armchair", Kind = "armchair", Model = "kenney.armchair", X = -1f, Z = 1.3f, SizeX = 0.9f, SizeY = 0.95f, SizeZ = 0.85f },
                },
                Inhabitants = new List<InhabitantDef> { new InhabitantDef { Name = "H", Model = "quaternius.man", Stations = stations } },
                DesignerRoute = route,
            };
        }

        /// <summary>One issue must contain every fragment. Fragments hold no number: issues format floats in the current culture.</summary>
        private static void AssertRejected(LevelDef level, params string[] fragments)
        {
            List<string> issues = LevelValidator.Validate(level);
            bool found = issues.Exists(issue => System.Array.TrueForAll(fragments, f => issue.Contains(f)));
            Assert.IsTrue(found, $"no issue contains [{string.Join(", ", fragments)}]; issues: " + string.Join(" | ", issues));
        }

        private static void AssertNoIssueContains(LevelDef level, string fragment, string because)
        {
            List<string> issues = LevelValidator.Validate(level);
            Assert.IsFalse(issues.Exists(i => i.Contains(fragment)), because + ": " + string.Join(" | ", issues));
        }

        private static void SetPlayerSize(LevelDef level, Vector3 size)
        {
            level.Player.SizeX = size.x;
            level.Player.SizeY = size.y;
            level.Player.SizeZ = size.z;
        }

        // ----- The fixture, for every body: each negative test below fails for its own reason -----

        [Test]
        public void Fixture_is_valid_for_every_body()
        {
            // M5 wave 5B appends the rocking chair (CONTRACT_M5 5); the M4 bodies keep their order.
            CollectionAssert.AreEqual(new[] { "chair", "stool", "armchair", "floor_lamp", "office_chair", "rocking_chair" }, BodyKinds.All);
            foreach (string kind in BodyKinds.All)
            {
                LevelDef l = Fixture(kind);
                Assert.AreEqual(kind, l.PlayerBody().Kind, "premise: the player kind selects its body");
                List<string> issues = LevelValidator.Validate(l);
                Assert.IsEmpty(issues, kind + ": " + string.Join("\n", issues));
            }
        }

        // ----- Bodies and sizes (amendment 9.5: BodyDef.Size is the one size source) -----

        [Test]
        public void Body_sizes_are_the_contract_table()
        {
            Assert.AreEqual(new Vector3(0.45f, 0.90f, 0.45f), BodyDef.For("chair").Size);
            Assert.AreEqual(new Vector3(0.35f, 0.55f, 0.35f), BodyDef.For("stool").Size);
            Assert.AreEqual(new Vector3(0.85f, 1.05f, 0.85f), BodyDef.For("armchair").Size);
            Assert.AreEqual(new Vector3(0.35f, 1.80f, 0.35f), BodyDef.For("floor_lamp").Size);
            Assert.AreEqual(new Vector3(0.55f, 1.00f, 0.55f), BodyDef.For("office_chair").Size);
        }

        [Test]
        public void Old_levels_and_fixtures_are_chairs_of_the_chair_body_size_and_still_valid()
        {
            Vector3 chair = BodyDef.For(BodyKinds.Chair).Size;
            var ids = new List<string>(OldLevels);
            ids.AddRange(OldFixtures);
            foreach (string id in ids)
            {
                LevelDef l = Load(id);
                Assert.AreEqual(BodyKinds.Chair, l.Player.Kind, id);
                Assert.AreEqual(chair, l.Player.Size, id + ": the M1 to M3 chair size equals the chair body");
                Assert.AreEqual(BodyKinds.Chair, l.PlayerBody().Kind, id);
                Assert.IsNull(l.Lesson, id + " has no lesson");
                List<string> issues = LevelValidator.Validate(l);
                Assert.IsEmpty(issues, id + ": " + string.Join("\n", issues));
            }
        }

        [Test]
        public void Player_body_defaults_to_the_chair()
        {
            Assert.AreEqual(BodyKinds.Chair, new LevelDef().PlayerBody().Kind, "no player");
            LevelDef l = Fixture(BodyKinds.Chair);
            l.Player.Kind = null;
            Assert.AreEqual(BodyKinds.Chair, l.PlayerBody().Kind, "no kind");
            Assert.IsEmpty(LevelValidator.Validate(l), "a chair without a kind (M1 data) is valid");
        }

        [Test]
        public void Validator_rejects_a_player_size_that_disagrees_with_its_body()
        {
            LevelDef l = Fixture(BodyKinds.Stool);
            SetPlayerSize(l, BodyDef.For(BodyKinds.Chair).Size);
            AssertRejected(l, "player size", "disagrees with the stool body size");
        }

        [Test]
        public void Validator_rejects_a_player_without_a_size()
        {
            LevelDef l = Fixture(BodyKinds.OfficeChair);
            SetPlayerSize(l, Vector3.zero);
            AssertRejected(l, "player size", "disagrees with the office_chair body size");
        }

        [Test]
        public void Validator_rejects_an_unknown_player_kind()
        {
            LevelDef l = Fixture(BodyKinds.Chair);
            l.Player.Kind = "stoool";
            Assert.AreEqual(BodyKinds.Chair, l.PlayerBody().Kind, "premise: at run time an unknown kind is the chair");
            AssertRejected(l, "player kind 'stoool' is not a furniture body");
        }

        [Test]
        public void Validator_rejects_a_player_model_of_another_body()
        {
            LevelDef l = Fixture(BodyKinds.Stool);
            l.Player.Model = "kenney.chair";
            AssertRejected(l, "player model 'kenney.chair' is not the model of the stool body");
        }

        [Test]
        public void Validator_rejects_any_player_model_on_the_office_chair()
        {
            LevelDef l = Fixture(BodyKinds.OfficeChair);
            Assert.IsNull(l.Player.Model, "premise: the office chair has no model");
            l.Player.Model = "kenney.chair";
            AssertRejected(l, "player model", "office_chair body");
        }

        [Test]
        public void Validator_rejects_an_unknown_decoy_kind()
        {
            LevelDef l = Fixture(BodyKinds.Chair);
            l.Decoys[0].Kind = "bench";
            l.Decoys[0].Model = null;
            AssertRejected(l, "decoy 1 kind 'bench' is not a furniture body");
        }

        [Test]
        public void Validator_rejects_a_decoy_model_of_another_body()
        {
            LevelDef l = Fixture(BodyKinds.Chair);
            l.Decoys[0].Kind = BodyKinds.Stool;
            AssertRejected(l, "decoy 1 model 'kenney.chair' is not the model of the stool body");
        }

        [Test]
        public void Decoys_of_every_kind_take_their_body_size()
        {
            LevelDef l = Fixture(BodyKinds.Chair);
            foreach (string kind in BodyKinds.All)
            {
                var d = new DecoyDef { Kind = kind, X = -3.4f, Z = 1.4f };
                Assert.AreEqual(BodyDef.For(kind).Size, l.DecoySize(d), kind);
                d.SizeY = 1.2f;
                Assert.AreEqual(1.2f, l.DecoySize(d).y, 1e-5f, kind + ": a size the data gives still wins");
                Assert.AreEqual(BodyDef.For(kind).Size.x, l.DecoySize(d).x, 1e-5f, kind + ": per axis");
            }
            // The decoy size follows its own kind, not the player's.
            LevelDef stool = Fixture(BodyKinds.Stool);
            Assert.AreEqual(BodyDef.For(BodyKinds.Chair).Size, stool.DecoySize(stool.Decoys[0]), "a chair decoy beside a stool player");
            stool.Decoys.Add(new DecoyDef { Kind = BodyKinds.OfficeChair, X = -3.3f, Z = 1.5f, Color = "#8C5A36" });
            Assert.IsEmpty(LevelValidator.Validate(stool), "an office chair decoy without a model is valid (the procedural one)");
        }

        [Test]
        public void Default_models_are_the_body_models_except_the_chair()
        {
            Assert.IsNull(BodyKinds.DefaultModel(null), "the chair (M1 to M3 data without a model stays procedural)");
            Assert.IsNull(BodyKinds.DefaultModel(BodyKinds.Chair));
            Assert.AreEqual("kenney.stool", BodyKinds.DefaultModel(BodyKinds.Stool));
            Assert.AreEqual("kenney.armchair", BodyKinds.DefaultModel(BodyKinds.Armchair));
            Assert.AreEqual("kenney.floorlamp", BodyKinds.DefaultModel(BodyKinds.FloorLamp));
            Assert.IsNull(BodyKinds.DefaultModel(BodyKinds.OfficeChair), "no model: procedural");
            Assert.IsNull(BodyKinds.DefaultModel("bench"), "an unknown kind is not the chair's model either");
            Assert.IsTrue(BodyKinds.IsKnown(null));
            Assert.IsTrue(BodyKinds.IsKnown(""));
            Assert.IsFalse(BodyKinds.IsKnown("Stool"), "kinds are lower case, as BodyDef.For reads them");
        }

        // ----- Doors per body (amendment 9.11) -----

        [Test]
        public void Door_clearance_is_twice_the_radius_plus_a_margin()
        {
            Assert.AreEqual(0.66f, LevelValidator.DoorClearance(BodyDef.For(BodyKinds.Chair)), 1e-5f);
            Assert.AreEqual(1.0f, LevelValidator.DoorClearance(BodyDef.For(BodyKinds.Armchair)), 1e-5f, "a 0.45 m radius needs 1.0 m doors");
            Assert.AreEqual(0.54f, LevelValidator.DoorClearance(BodyDef.For(BodyKinds.Stool)), 1e-5f);
            Assert.AreEqual(0.70f, LevelValidator.DoorClearance(BodyDef.For(BodyKinds.OfficeChair)), 1e-5f);
        }

        [Test]
        public void Validator_rejects_a_door_too_narrow_for_the_body()
        {
            LevelDef chair = Fixture(BodyKinds.Chair);
            chair.Doors[0].Width = 0.9f;
            Assert.IsEmpty(LevelValidator.Validate(chair), "premise: a 0.9 m door lets the chair through");
            LevelDef armchair = Fixture(BodyKinds.Armchair);
            armchair.Doors[0].Width = 0.9f;
            AssertRejected(armchair, "door 1", "the armchair body needs at least");
        }

        [Test]
        public void Validator_rejects_a_spawn_closer_to_a_wall_than_the_body_radius()
        {
            LevelDef chair = Fixture(BodyKinds.Chair);
            chair.Player.X = -3.6f;
            Assert.IsEmpty(LevelValidator.Validate(chair), "premise: the chair (radius 0.28) fits 0.4 m from the wall");
            LevelDef armchair = Fixture(BodyKinds.Armchair);
            armchair.Player.X = -3.6f;
            AssertRejected(armchair, "player spawn", "is not inside the room");
        }

        // ----- Sitting (CONTRACT_M4 3) -----

        [Test]
        public void Validator_rejects_a_sit_on_a_missing_prop()
        {
            LevelDef l = Fixture(BodyKinds.Chair);
            l.Inhabitants[0].Stations[1].Sit = "Couch";
            AssertRejected(l, "station 2", "sits on 'Couch', which is not a prop of the level");
        }

        [Test]
        public void Validator_rejects_a_sit_on_the_player_without_a_seat_home()
        {
            LevelDef l = Fixture(BodyKinds.Armchair);
            l.Inhabitants[0].Stations[0].Seat = null;
            AssertRejected(l, "station 1", "sits on the player but has no seat home");
        }

        [Test]
        public void Validator_rejects_a_sit_on_a_player_body_that_is_not_a_seat()
        {
            LevelDef l = Fixture(BodyKinds.FloorLamp);
            Assert.IsFalse(BodyDef.For(BodyKinds.FloorLamp).IsSeat, "premise");
            l.Inhabitants[0].Stations[0].Sit = StationDef.SitOnPlayer;
            l.Inhabitants[0].Stations[0].Seat = new SeatDef { X = -2f, Z = -0.5f };
            AssertRejected(l, "station 1", "the floor_lamp body is not a seat");
        }

        [Test]
        public void Validator_rejects_a_seat_home_without_a_sit_on_the_player()
        {
            LevelDef l = Fixture(BodyKinds.Chair);
            l.Inhabitants[0].Stations[1].Seat = new SeatDef { X = 2f, Z = 0f, Yaw = 90f };
            AssertRejected(l, "station 2", "has a seat home but does not sit on the player");
        }

        [Test]
        public void Validator_rejects_a_seat_home_outside_every_room()
        {
            LevelDef l = Fixture(BodyKinds.Armchair);
            l.Inhabitants[0].Stations[0].Seat.X = 0.05f;
            AssertRejected(l, "station 1 seat home", "is not inside a room");
        }

        [Test]
        public void Validator_rejects_a_seat_home_on_a_prop()
        {
            LevelDef l = Fixture(BodyKinds.Armchair);
            l.Inhabitants[0].Stations[0].Seat.X = 2f;
            l.Inhabitants[0].Stations[0].Seat.Z = -1.4f;
            AssertRejected(l, "station 1 seat home overlaps prop Box");
        }

        [Test]
        public void Validator_rejects_a_player_seat_station_that_is_not_its_seat_front()
        {
            LevelDef l = Fixture(BodyKinds.Armchair);
            l.Inhabitants[0].Stations[0].Seat.Z = -1.5f;
            AssertRejected(l, "station 1 stands", "a seat front is");
            l = Fixture(BodyKinds.Armchair);
            l.Inhabitants[0].Stations[0].Seat.X = -2.4f;
            AssertRejected(l, "station 1 stands", "a seat front is");
            l = Fixture(BodyKinds.Armchair);
            l.Inhabitants[0].Stations[0].Seat.Z = 0.5f;
            AssertRejected(l, "station 1 stands", "a seat front is");
        }

        [Test]
        public void Validator_rejects_a_player_seat_station_that_does_not_face_the_seat_yaw()
        {
            LevelDef l = Fixture(BodyKinds.Armchair);
            l.Inhabitants[0].Stations[0].Facing = 180f;
            AssertRejected(l, "station 1 faces", "the station facing is the seated facing");
        }

        [Test]
        public void A_seat_front_follows_the_seat_yaw()
        {
            LevelDef l = Fixture(BodyKinds.Armchair);
            StationDef s = l.Inhabitants[0].Stations[0];
            s.Seat = new SeatDef { X = -2.5f, Z = 0f, Yaw = 90f };
            s.Facing = 450f;
            Assert.IsEmpty(LevelValidator.Validate(l), "a seat turned to +x with its front 0.5 m along +x, the facing mod 360");
        }

        [Test]
        public void Validator_rejects_a_prop_seat_station_too_far_from_the_prop()
        {
            LevelDef l = Fixture(BodyKinds.Chair);
            l.Inhabitants[0].Stations[1].Z = 0.2f;
            AssertRejected(l, "station 2 stands", "from the center of Sofa", "a seat front is");
        }

        [Test]
        public void Validator_rejects_a_prop_seat_station_too_close_to_the_prop()
        {
            LevelDef l = Fixture(BodyKinds.Chair);
            l.Props.Find(p => p.Name == "Sofa").Z = 0.75f;
            l.Props.Find(p => p.Name == "Sofa").SizeZ = 0.4f;
            AssertRejected(l, "station 2 stands", "from the center of Sofa", "a seat front is");
        }

        [Test]
        public void Validator_rejects_a_prop_seat_station_that_does_not_face_away_from_the_prop()
        {
            LevelDef l = Fixture(BodyKinds.Chair);
            l.Inhabitants[0].Stations[1].Facing = 0f;
            AssertRejected(l, "station 2 faces", "off facing away from Sofa");
            l.Inhabitants[0].Stations[1].Facing = 140f;
            AssertRejected(l, "station 2 faces", "off facing away from Sofa");
            l.Inhabitants[0].Stations[1].Facing = 155f;
            Assert.That(LevelValidator.Validate(l), Has.None.Contains("off facing away from Sofa"), "25 deg off is within the 30 deg tolerance");
        }

        [Test]
        public void Validator_rejects_a_prop_seat_station_beside_the_prop()
        {
            LevelDef l = Fixture(BodyKinds.Chair);
            StationDef s = l.Inhabitants[0].Stations[1];
            s.X = 2.65f;
            // 0.65 m beside and 0.65 m in front: 0.92 m away and 45 deg off.
            AssertRejected(l, "station 2", "from the center of Sofa");
            AssertRejected(l, "station 2 faces", "off facing away from Sofa");
        }

        [Test]
        public void A_prop_sit_resolves_its_seat_home_to_the_prop_center()
        {
            LevelDef built = Fixture(BodyKinds.Armchair);
            StationDef onSofa = built.Inhabitants[0].Stations[1];
            Assert.IsNull(onSofa.PropSeat, "premise: a level built in code is not resolved yet");
            built.ResolveSeats();
            PropDef sofa = built.Props.Find(p => p.Name == "Sofa");
            Assert.IsTrue(onSofa.PropSeat.HasValue);
            Assert.AreEqual(sofa.Position, onSofa.PropSeat.Value.Position, "the sitter sits on the sofa, not at the seat front");
            Assert.AreEqual(onSofa.Facing, onSofa.PropSeat.Value.Yaw, "facing the station's facing (the seated facing)");
            Assert.IsNull(built.Inhabitants[0].Stations[0].PropSeat, "a player seat is no prop seat");

            string json = LevelJson.Serialize(built);
            StringAssert.DoesNotContain("propSeat", json, "derived, never written");
            LevelDef parsed = LevelJson.Parse(json);
            Assert.AreEqual(sofa.Position, parsed.Inhabitants[0].Stations[1].PropSeat.Value.Position, "LevelJson.Parse resolves it");
            Assert.IsNull(parsed.Inhabitants[0].Stations[0].PropSeat);

            onSofa.Sit = null;
            built.ResolveSeats();
            Assert.IsNull(onSofa.PropSeat, "resolving again clears a station that no longer sits");
        }

        [Test]
        public void Sit_stations_name_the_sofa_or_the_player()
        {
            LevelDef l = Fixture(BodyKinds.Armchair);
            StationDef onPlayer = l.Inhabitants[0].Stations[0];
            StationDef onSofa = l.Inhabitants[0].Stations[1];
            Assert.IsTrue(onPlayer.SitsOnPlayer);
            Assert.AreEqual(new Vector3(-2f, 0f, -0.5f), onPlayer.Seat.Position);
            Assert.IsFalse(onSofa.SitsOnPlayer);
            Assert.AreEqual("Sofa", onSofa.Sit);
            Assert.IsFalse(new StationDef().SitsOnPlayer, "no sit by default");
        }

        // ----- The lesson knob (amendment 9.11) -----

        [Test]
        public void Lessons_are_careful_sit_dark_and_glide()
        {
            // M5 appends its lessons after the four of M4 (CONTRACT_M5 16.12); the M4 ones keep their order.
            CollectionAssert.AreEqual(new[] { "careful", "sit", "dark", "glide" }, System.Linq.Enumerable.Take(LevelDef.Lessons, 4));
            CollectionAssert.IsSubsetOf(new[] { "door", "pet", "split", "robot", "rock", "load", "final" }, LevelDef.Lessons);
            // Each one is accepted on the body it is about (the fixtures carry them).
            foreach (string kind in new[] { BodyKinds.Stool, BodyKinds.Armchair, BodyKinds.FloorLamp, BodyKinds.OfficeChair })
            {
                LevelDef l = Fixture(kind);
                Assert.IsNotNull(l.Lesson, "premise");
                Assert.IsEmpty(LevelValidator.Validate(l), kind + " with lesson " + l.Lesson);
            }
            LevelDef chair = Fixture(BodyKinds.Chair);
            chair.Lesson = LevelDef.LessonSit;
            Assert.IsEmpty(LevelValidator.Validate(chair), "sit is a lesson of any seat body");
        }

        [Test]
        public void Validator_rejects_an_unknown_lesson()
        {
            LevelDef l = Fixture(BodyKinds.Stool);
            l.Lesson = "speed";
            AssertRejected(l, "lesson 'speed' is not one of careful, sit, dark, glide");
        }

        [Test]
        public void Validator_rejects_lesson_careful_on_a_body_that_never_tips()
        {
            LevelDef l = Fixture(BodyKinds.Chair);
            l.Lesson = LevelDef.LessonCareful;
            AssertRejected(l, "lesson careful needs a body that tips", "not the chair");
        }

        [Test]
        public void Validator_rejects_lesson_dark_on_a_body_without_a_light()
        {
            LevelDef l = Fixture(BodyKinds.Armchair);
            l.Lesson = LevelDef.LessonDark;
            AssertRejected(l, "lesson dark needs a body with a light", "not the armchair");
        }

        [Test]
        public void Validator_rejects_lesson_glide_on_a_body_that_does_not_glide()
        {
            LevelDef l = Fixture(BodyKinds.Stool);
            l.Lesson = LevelDef.LessonGlide;
            AssertRejected(l, "lesson glide needs a body that glides", "not the stool");
        }

        [Test]
        public void Validator_rejects_lesson_sit_without_a_station_on_the_player()
        {
            LevelDef l = Fixture(BodyKinds.Armchair);
            l.Inhabitants[0].Stations[0].Sit = null;
            l.Inhabitants[0].Stations[0].Seat = null;
            AssertRejected(l, "lesson sit needs a station that sits on the player");
        }

        // ----- Route step fields (CONTRACT_M4 5, amendment 9.3) -----

        [Test]
        public void Validator_rejects_an_unknown_route_action()
        {
            LevelDef l = Fixture(BodyKinds.FloorLamp);
            l.DesignerRoute[1].Action = "jump";
            AssertRejected(l, "designer route waypoint 2 action 'jump' is neither toggle nor rightup");
        }

        [Test]
        public void Validator_rejects_a_toggle_on_a_body_without_a_light()
        {
            LevelDef l = Fixture(BodyKinds.Stool);
            l.DesignerRoute[0].Action = RouteStepDef.ActionToggle;
            AssertRejected(l, "designer route waypoint 1 toggles a light", "the stool body has none");
        }

        [Test]
        public void Validator_rejects_a_rightup_on_a_body_that_never_tips()
        {
            LevelDef l = Fixture(BodyKinds.OfficeChair);
            l.DesignerRoute[1].Action = RouteStepDef.ActionRightUp;
            AssertRejected(l, "designer route waypoint 2 rights the furniture up", "the office_chair body never tips");
        }

        [Test]
        public void Careful_steps_are_valid_on_every_body()
        {
            foreach (string kind in BodyKinds.All)
            {
                LevelDef l = Fixture(kind);
                l.DesignerRoute[1].Careful = true;
                Assert.IsEmpty(LevelValidator.Validate(l), kind + ": careful mode is for every body (CONTRACT_M4 2)");
            }
        }

        // ----- Levels 4 to 7 (CONTRACT_M4 4) and the audit fixtures (amendment 9.11) -----

        private static readonly (string id, string kind, string lesson)[] M4Levels =
        {
            ("level4", BodyKinds.Stool, LevelDef.LessonCareful),
            ("level5", BodyKinds.Armchair, LevelDef.LessonSit),
            ("level6", BodyKinds.FloorLamp, LevelDef.LessonDark),
            ("level7", BodyKinds.OfficeChair, LevelDef.LessonGlide),
        };

        [Test]
        public void Levels_4_to_7_have_one_body_and_its_lesson_each()
        {
            List<string> order = LevelManifest.Parse(File.ReadAllText(Folder + "levels.json"));
            foreach ((string id, string kind, string lesson) in M4Levels)
            {
                CollectionAssert.Contains(order, id, id + " is not played");
                LevelDef l = Load(id);
                Assert.AreEqual(id, l.Id);
                Assert.AreEqual(kind, l.Player.Kind, id + ": body");
                Assert.AreEqual(lesson, l.Lesson, id + ": lesson");
                Assert.AreEqual(BodyDef.For(kind).Size, l.Player.Size, id + ": the body size");
                Assert.AreEqual(BodyDef.For(kind).Model, l.Player.Model, id + ": the body's model");
                Assert.LessOrEqual(l.AllRooms().Count, 2, id + ": two rooms at most");
                Assert.AreEqual(id + ".name", l.NameKey);
                Assert.AreEqual(id + ".hint", l.HintKey);
                Assert.AreNotEqual(Strings.Get(l.NameKey), l.NameKey, id + ": name string missing");
                Assert.AreNotEqual(Strings.Get(l.HintKey), l.HintKey, id + ": hint string missing");
                foreach (InhabitantDef h in l.Inhabitants)
                {
                    Assert.AreEqual("quaternius.man", h.Model, $"{id} {h.Name}: the man (material budget)");
                }
                Assert.GreaterOrEqual(l.DesignerRoute.Count, 2, id + ": no designer route (LevelAudit -writeRoutes writes it)");
                List<string> issues = LevelValidator.Validate(l);
                Assert.IsEmpty(issues, id + ": " + string.Join("\n", issues));
            }
            // M5 (CONTRACT_M5 16.2): the manifest grows after level7; levels 1 to 7 keep the first seven places.
            Assert.AreEqual(new[] { "level1", "level2", "level3", "level4", "level5", "level6", "level7" }, order.Take(7).ToArray(), "the play order");
        }

        [Test]
        public void Level4_hides_the_stool_behind_low_props_and_sits_on_one()
        {
            LevelDef l = Load("level4");
            float stoolTop = BodyDef.For(BodyKinds.Stool).Size.y - Tuning.SampleInset;
            int low = l.Props.FindAll(p => (p.Kind == "sofa" || p.Kind == "table" || p.Kind == "counter") && p.SizeY < Tuning.EyeHeight && p.SizeY > stoolTop).Count;
            Assert.GreaterOrEqual(low, 3, "low props taller than the stool's top as cover");
            List<StationDef> stations = l.Inhabitants[0].Stations;
            StationDef onProp = stations.Find(s => !string.IsNullOrEmpty(s.Sit) && !s.SitsOnPlayer);
            Assert.IsNotNull(onProp, "one sit on a prop");
            Assert.AreEqual("sofa", l.Props.Find(p => p.Name == onProp.Sit).Kind);
            Assert.IsTrue(onProp.PropSeat.HasValue, "the prop seat is resolved on load");
            Assert.IsTrue(l.DesignerRoute.TrueForAll(s => s.Careful), "the stool's route is driven in careful mode");
        }

        [Test]
        public void Level5_sits_on_the_armchair_at_its_spawn()
        {
            LevelDef l = Load("level5");
            StationDef sit = l.Inhabitants[0].Stations.Find(s => s.SitsOnPlayer);
            Assert.IsNotNull(sit, "a sit on the player");
            Assert.AreEqual(l.Player.Position, sit.Seat.Position, "the seat home is the spawn: the armchair must be home in time");
            Assert.AreEqual(l.Player.Yaw, sit.Seat.Yaw, 1e-4f);
            foreach (OpeningDef door in l.Doors)
            {
                Assert.GreaterOrEqual(door.Width, LevelValidator.DoorClearance(BodyDef.For(BodyKinds.Armchair)) - 1e-4f, "doors fit the armchair");
            }
        }

        [Test]
        public void Level6_switches_the_lamp_off_on_its_route()
        {
            LevelDef l = Load("level6");
            Assert.IsTrue(l.DesignerRoute.Exists(s => s.Action == RouteStepDef.ActionToggle), "the route switches the lamp");
            Assert.AreEqual(2, l.AllRooms().Count, "a room to cross dark, and the lamp's room");
        }

        [Test]
        public void Level7_has_decoy_office_chairs_on_a_long_open_floor()
        {
            LevelDef l = Load("level7");
            Assert.GreaterOrEqual(l.Decoys.FindAll(d => d.Kind == BodyKinds.OfficeChair).Count, 2, "decoy office chairs");
            RoomDef floor = l.AllRooms()[0];
            Assert.GreaterOrEqual(Mathf.Max(floor.SizeX, floor.SizeZ), 8f, "a long floor");
            Assert.IsNull(l.Player.Model, "the office chair is procedural");
        }

        [Test]
        public void M4_audit_fixtures_are_valid_levels_kept_out_of_the_play_order()
        {
            List<string> order = LevelManifest.Parse(File.ReadAllText(Folder + "levels.json"));
            // CONTRACT_M4 10.1, 10.5: independent minimal fixtures (test_sit sits on a chair), not copies of levels 4 to 6.
            var bodies = new Dictionary<string, string> { { "tip", BodyKinds.Stool }, { "dark", BodyKinds.FloorLamp }, { "sit", BodyKinds.Chair } };
            foreach (KeyValuePair<string, string> rule in bodies)
            {
                string id = "test_" + rule.Key;
                Assert.IsTrue(File.Exists(Folder + id + ".json"), id + " is missing");
                LevelDef l = Load(id);
                Assert.AreEqual(id, l.Id);
                Assert.AreEqual(rule.Value, l.Player.Kind, id + ": its rule's body");
                List<string> issues = LevelValidator.Validate(l);
                Assert.IsEmpty(issues, id + ": " + string.Join("\n", issues));
                CollectionAssert.DoesNotContain(order, id, id + " must never be played");
                Assert.IsEmpty(l.DesignerRoute, id + " has no route: it must have none");
            }
            Assert.IsTrue(Load("test_sit").Inhabitants[0].Stations.Exists(s => s.SitsOnPlayer), "test_sit sits on the player");
            foreach ((string fixture, string level) in new[] { ("test_tip", "level4"), ("test_dark", "level6"), ("test_sit", "level5") })
            {
                Assert.AreNotEqual(LevelJson.Serialize(Load(level)).Length, LevelJson.Serialize(Load(fixture)).Length, fixture + " is a copy of " + level);
                Assert.AreNotEqual(Load(level).AllRooms()[0].SizeX, Load(fixture).AllRooms()[0].SizeX, fixture + " has the room of " + level);
            }
        }

        // ----- JSON -----

        [Test]
        public void M4_fields_round_trip()
        {
            LevelDef original = Fixture(BodyKinds.Stool);
            string once = LevelJson.Serialize(original);
            LevelDef back = LevelJson.Parse(once);
            Assert.AreEqual(once, LevelJson.Serialize(back));
            Assert.AreEqual(LevelDef.LessonCareful, back.Lesson);
            Assert.AreEqual(BodyKinds.Stool, back.Player.Kind);
            Assert.IsTrue(back.DesignerRoute[0].Careful);
            Assert.IsNull(back.DesignerRoute[0].Action);
            Assert.AreEqual(RouteStepDef.ActionRightUp, back.DesignerRoute[1].Action);
            Assert.IsFalse(back.DesignerRoute[1].Careful);
            StationDef sat = back.Inhabitants[0].Stations[0];
            Assert.AreEqual(StationDef.SitOnPlayer, sat.Sit);
            Assert.AreEqual(-2f, sat.Seat.X, 1e-6f);
            Assert.AreEqual(-0.5f, sat.Seat.Z, 1e-6f);
            Assert.AreEqual(0f, sat.Seat.Yaw, 1e-6f);
            Assert.AreEqual("Sofa", back.Inhabitants[0].Stations[1].Sit);
            Assert.IsNull(back.Inhabitants[0].Stations[1].Seat);
            Assert.AreEqual("armchair", back.Props.Find(p => p.Name == "Armchair").Kind);
            StringAssert.Contains("\"lesson\": \"careful\"", once, "camel case");
            StringAssert.Contains("\"careful\": true", once);
            StringAssert.Contains("\"sit\": \"player\"", once);
            StringAssert.Contains("\"seat\": {", once);
            LevelDef lamp = LevelJson.Parse(LevelJson.Serialize(Fixture(BodyKinds.FloorLamp)));
            Assert.AreEqual(RouteStepDef.ActionToggle, lamp.DesignerRoute[0].Action);
            Assert.AreEqual(LevelDef.LessonDark, lamp.Lesson);
        }

        [Test]
        public void Default_m4_fields_are_not_written_so_old_level_files_do_not_change()
        {
            foreach (string id in OldLevels)
            {
                string json = LevelJson.Serialize(Load(id));
                StringAssert.Contains("\"designerRoute\"", json, id + ": premise: the level has a route");
                foreach (string member in new[] { "\"careful\"", "\"action\"", "\"lesson\"", "\"sit\"", "\"seat\"" })
                {
                    StringAssert.DoesNotContain(member, json, $"{id}: a default {member} is written");
                }
            }
        }

        [Test]
        public void Route_steps_accept_only_their_fields()
        {
            LevelDef ok = LevelJson.Parse("{\"id\":\"x\",\"designerRoute\":[{\"x\":1,\"z\":2,\"at\":0.5,\"careful\":true,\"action\":\"toggle\"}]}");
            RouteStepDef s = ok.DesignerRoute[0];
            Assert.IsTrue(s.Careful);
            Assert.AreEqual("toggle", s.Action);
            Assert.Throws<JsonSerializationException>(() => LevelJson.Parse("{\"id\":\"x\",\"designerRoute\":[{\"x\":0,\"z\":0,\"at\":0,\"waitFor\":1}]}"),
                "CONTRACT_M4 10.7: waitFor is removed");
            Assert.Throws<JsonSerializationException>(() => LevelJson.Parse("{\"id\":\"x\",\"designerRoute\":[{\"x\":0,\"z\":0,\"at\":0,\"speed\":1}]}"),
                "amendment 9.3: no other field, LevelJson rejects unknown members");
            Assert.Throws<JsonSerializationException>(() => LevelJson.Parse("{\"id\":\"x\",\"inhabitants\":[{\"stations\":[{\"x\":0,\"z\":0,\"seat\":{\"x\":0,\"z\":0,\"pitch\":1}}]}]}"),
                "a seat home has x, z and yaw only");
        }
    }
}
