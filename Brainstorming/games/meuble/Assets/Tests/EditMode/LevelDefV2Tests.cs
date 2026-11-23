using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Levels v2 schema (docs/levels_v2/LEVELS_V2.md 6, row C1): parse and round trip of every new field (rev, requires,
    /// pace, viaChecks, litZones, lighting, playerLocked, glanceEvery), the glanceEvery expansion against a copy of level18
    /// Odile's hand-written glances (test_v2_schema_odile), every new validator rule with a failing and a passing case, and
    /// the full manifest (ManifestDef, ParseFull). Data model and validation only: the audit and the runtime are other tasks.
    /// </summary>
    public sealed class LevelDefV2Tests
    {
        private const string Folder = "Assets/Resources/Levels/";
        private const float Eps = 1e-4f;

        private static LevelDef Load(string id) => LevelJson.Parse(File.ReadAllText(Folder + id + ".json"));

        /// <summary>
        /// A valid two room house (the M5 base without its platform and dog): room a x in [-4.05, -0.05], room b x in
        /// [0.05, 6.05], both z in [-2, 2]; door 1 at (0, 1.25) carries the closed leaf "porte" swinging into b; door 2 is
        /// the exit door in a's -x wall; a chair player, one human H.
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
                            new StationDef { X = 3f, Z = -1.4f, Facing = 90f, Dwell = 20f },
                        },
                    },
                },
            };
            level.ResolveSeats();
            return level;
        }

        private static OpeningDef Porte(LevelDef l) => l.Doors[0];
        private static StationDef Long(LevelDef l) => l.Inhabitants[0].Stations[1];

        /// <summary>The player becomes a body of <paramref name="kind"/>, at its body size.</summary>
        private static void SetBody(LevelDef l, string kind)
        {
            Vector3 size = BodyDef.For(kind).Size;
            l.Player.Kind = kind;
            l.Player.SizeX = size.x;
            l.Player.SizeY = size.y;
            l.Player.SizeZ = size.z;
        }

        private static InhabitantDef Dog() => new InhabitantDef
        {
            Name = "Rex",
            Kind = "dog",
            Stations = new List<StationDef>
            {
                new StationDef { X = 2.5f, Z = 1.5f, Facing = 180f, Dwell = 20f },
                new StationDef { X = 4.5f, Z = 1.5f, Facing = 180f, Dwell = 2f },
            },
        };

        private static RobotDef Robot() => new RobotDef
        {
            Name = "Robi",
            Loop = new List<PointDef> { new PointDef { X = 1f, Z = -1.6f }, new PointDef { X = 4f, Z = -1.6f } },
        };

        private static List<string> Issues(LevelDef level)
        {
            level.ExpandGlances();
            level.ResolveSeats();
            return LevelValidator.Validate(level);
        }

        /// <summary>One issue must contain every fragment. Fragments hold no number formatted by the culture.</summary>
        private static void AssertRejected(LevelDef level, params string[] fragments)
        {
            List<string> issues = Issues(level);
            bool found = issues.Exists(issue => System.Array.TrueForAll(fragments, f => issue.Contains(f)));
            Assert.IsTrue(found, $"no issue contains [{string.Join(", ", fragments)}]; issues: " + string.Join(" | ", issues));
        }

        /// <summary>No issue contains the fragment (the passing case of a rule).</summary>
        private static void AssertNoIssue(LevelDef level, string fragment)
        {
            List<string> issues = Issues(level);
            Assert.IsFalse(issues.Exists(i => i.Contains(fragment)), $"an issue contains '{fragment}': " + string.Join(" | ", issues));
        }

        private static void AssertValid(LevelDef level, string what)
        {
            List<string> issues = Issues(level);
            Assert.IsEmpty(issues, what + ": " + string.Join("\n", issues));
        }

        /// <summary>A floor lamp level that uses every v2 field, valid.</summary>
        private static LevelDef Full()
        {
            LevelDef l = Base();
            SetBody(l, BodyKinds.FloorLamp);
            l.Rev = 2;
            l.RequiredLessons = new List<string> { LevelDef.LessonDoor, LevelDef.LessonExitWatch, LevelDef.LessonLit };
            l.Pace = new PaceDef { MinShare = 0.25f, MaxShare = 0.4f, MinPauses = 3, MaxPause = 6f };
            l.ViaChecks = new List<ViaCheckDef>
            {
                new ViaCheckDef { Name = "porte", X = 1f, Z = 1.25f, SizeX = 1f, SizeZ = 1f },
                new ViaCheckDef { Name = "fond", X = 5f, Z = -1f, SizeX = 1f, SizeZ = 1f, MaxRatio = 2f, Avoid = true },
            };
            l.LitZones = new List<LitZoneDef> { new LitZoneDef { Name = "plafonnier", X = 3f, Z = 0f, SizeX = 1f, SizeZ = 1f } };
            l.Lighting = LevelDef.LightingNight;
            l.Doors.Insert(1, new OpeningDef { X = 0f, Z = -1.25f, Width = 1f, Top = 2.1f, Leaf = "closed", Hinge = "start", Id = "cuisine", Swing = "b",
                OpenedByInhabitants = true, PlayerLocked = true });
            Long(l).GlanceEvery = new GlanceEveryDef { Start = 2f, Period = 6f, Hold = 3f, Yaw = 60f, Alternate = true, Count = 3 };
            Long(l).Glances.Add(new GlanceDef { Offset = 5f, Yaw = -30f, Hold = 0.5f });
            l.ExpandGlances();
            return l;
        }

        // ----- Parse and round trip -----

        [Test]
        public void Base_and_full_fixtures_are_valid()
        {
            AssertValid(Base(), "the base fixture");
            AssertValid(Full(), "the fixture with every v2 field");
        }

        [Test]
        public void Default_v2_fields_write_nothing_and_old_keys_stay()
        {
            string json = LevelJson.Serialize(Base());
            foreach (string key in new[] { "\"rev\"", "\"requires\"", "\"pace\"", "\"viaChecks\"", "\"litZones\"", "\"lighting\"",
                         "\"playerLocked\"", "\"glanceEvery\"", "\"maxRatio\"", "\"avoid\"", "\"generated\"" })
            {
                Assert.IsFalse(json.Contains(key), key + " is written by a level that does not use it");
            }
            Assert.IsTrue(json.Contains("\"glances\""), "a station without glanceEvery keeps its glances list as before");
            LevelDef back = LevelJson.Parse(json);
            Assert.AreEqual(0, back.Rev);
            Assert.AreEqual("test", back.RecordId, "rev 0 records under the bare id");
            Assert.IsEmpty(back.RequiredLessons);
            Assert.IsNull(back.Pace);
            Assert.IsEmpty(back.ViaChecks);
            Assert.IsEmpty(back.LitZones);
            Assert.IsNull(back.Lighting);
            Assert.IsFalse(back.Doors[0].PlayerLocked);
            Assert.IsNull(Long(back).GlanceEvery);
        }

        [Test]
        public void Every_v2_field_parses_from_its_json_key_and_round_trips()
        {
            JObject o = JObject.Parse(LevelJson.Serialize(Base()));
            o["rev"] = 1;
            o["requires"] = new JArray("door", "exitwatch");
            o["pace"] = new JObject { ["minShare"] = 0.25, ["maxPause"] = 6.0 };
            o["viaChecks"] = new JArray(new JObject { ["name"] = "porte", ["x"] = 1.0, ["z"] = 1.25, ["sizeX"] = 1.0, ["sizeZ"] = 1.0 },
                new JObject { ["name"] = "fond", ["x"] = 5.0, ["z"] = -1.0, ["sizeX"] = 1.0, ["sizeZ"] = 1.0, ["maxRatio"] = 2.0, ["avoid"] = true });
            o["litZones"] = new JArray(new JObject { ["name"] = "plafonnier", ["x"] = 3.0, ["z"] = 0.0, ["sizeX"] = 1.0, ["sizeZ"] = 1.5 });
            o["lighting"] = "night";
            o["doors"][0]["playerLocked"] = true;
            JObject station = (JObject)o["inhabitants"][0]["stations"][1];
            station.Remove("glances");
            station["glanceEvery"] = new JObject { ["start"] = 1.0, ["period"] = 5.0, ["hold"] = 2.0, ["yaw"] = -40.0, ["alternate"] = true, ["count"] = 3 };

            LevelDef l = LevelJson.Parse(o.ToString());
            Assert.AreEqual(1, l.Rev);
            Assert.AreEqual("test~1", l.RecordId);
            CollectionAssert.AreEqual(new[] { "door", "exitwatch" }, l.RequiredLessons);
            Assert.AreEqual(0.25f, l.Pace.MinShare.Value, Eps);
            Assert.IsNull(l.Pace.MaxShare, "a pace key left out stays null");
            Assert.IsNull(l.Pace.MinPauses);
            Assert.AreEqual(6f, l.Pace.MaxPause.Value, Eps);
            Assert.AreEqual(2, l.ViaChecks.Count);
            Assert.AreEqual(ViaCheckDef.DefaultMaxRatio, l.ViaChecks[0].MaxRatio, Eps, "maxRatio defaults to 1.5");
            Assert.IsFalse(l.ViaChecks[0].Avoid);
            Assert.AreEqual(2f, l.ViaChecks[1].MaxRatio, Eps);
            Assert.IsTrue(l.ViaChecks[1].Avoid);
            Assert.IsTrue(l.ViaChecks[0].Contains(new Vector3(1.4f, 0f, 1.7f)) && !l.ViaChecks[0].Contains(new Vector3(1.6f, 0f, 1.25f)));
            Assert.AreEqual("plafonnier", l.LitZones[0].Name);
            Assert.AreEqual(1.5f, l.LitZones[0].SizeZ, Eps);
            Assert.IsTrue(l.LitZones[0].Contains(new Vector3(3.5f, 0f, 0.75f)) && !l.LitZones[0].Contains(new Vector3(3f, 0f, 0.8f)));
            Assert.AreEqual("night", l.Lighting);
            Assert.IsTrue(l.Doors[0].PlayerLocked);
            Assert.IsFalse(l.Doors[1].PlayerLocked);
            GlanceEveryDef ge = Long(l).GlanceEvery;
            Assert.AreEqual(3, ge.Count);
            Assert.IsTrue(ge.Alternate);
            Assert.AreEqual(3, Long(l).Glances.Count, "glanceEvery expands at parse time");

            string once = LevelJson.Serialize(l);
            JObject written = JObject.Parse(once);
            Assert.AreEqual(1, (int)written["rev"]);
            Assert.IsNull(written["viaChecks"][0]["maxRatio"], "the default maxRatio is not written");
            Assert.IsNull(written["viaChecks"][0]["avoid"], "avoid false is not written");
            Assert.IsNull(written["pace"]["maxShare"], "a pace key left out is not written");
            Assert.IsNull(written["doors"][1]["playerLocked"], "playerLocked false is not written");
            JObject writtenStation = (JObject)written["inhabitants"][0]["stations"][1];
            Assert.IsNull(writtenStation["glances"], "the compact form is kept: no generated glance is written");
            Assert.AreEqual(5f, (float)writtenStation["glanceEvery"]["period"], Eps);
            Assert.AreEqual(once, LevelJson.Serialize(LevelJson.Parse(once)), "lossless round trip");
            Assert.AreEqual(3, Long(l).Glances.Count, "serializing puts the generated glances back");
        }

        [Test]
        public void Full_fixture_round_trips_with_mixed_glances()
        {
            LevelDef l = Full();
            List<GlanceDef> glances = Long(l).Glances;
            // Explicit 5 s glance merged with the generated 2, 8, 14 s ones, sorted; alternate flips every odd one.
            Assert.AreEqual(4, glances.Count);
            CollectionAssert.AreEqual(new[] { 2f, 5f, 8f, 14f }, glances.ConvertAll(g => g.Offset));
            CollectionAssert.AreEqual(new[] { 60f, -30f, -60f, 60f }, glances.ConvertAll(g => g.Yaw));
            CollectionAssert.AreEqual(new[] { true, false, true, true }, glances.ConvertAll(g => g.Generated));

            string once = LevelJson.Serialize(l);
            JObject station = (JObject)JObject.Parse(once)["inhabitants"][0]["stations"][1];
            Assert.AreEqual(1, ((JArray)station["glances"]).Count, "only the explicit glance is written next to glanceEvery");
            LevelDef back = LevelJson.Parse(once);
            Assert.AreEqual(4, Long(back).Glances.Count, "parse expands once: no doubled glance");
            Assert.AreEqual(once, LevelJson.Serialize(back));
            AssertValid(back, "the full fixture read back");
            Assert.AreEqual(2, back.Rev);
            Assert.IsTrue(back.Doors[1].PlayerLocked);
        }

        [Test]
        public void ExpandGlances_is_idempotent_and_follows_the_dwell()
        {
            LevelDef l = Base();
            Long(l).GlanceEvery = new GlanceEveryDef { Start = 1f, Period = 4f, Hold = 1f, Yaw = 30f };
            l.ExpandGlances();
            // No count: as many as fit, the largest n with 1 + 4 n <= 20: 4.
            Assert.AreEqual(4, Long(l).Glances.Count);
            l.ExpandGlances();
            Assert.AreEqual(4, Long(l).Glances.Count, "a second call replaces the generated glances");
            Long(l).Dwell = 9f;
            l.ExpandGlances();
            Assert.AreEqual(2, Long(l).Glances.Count, "a shorter dwell fits fewer glances");
            Long(l).GlanceEvery = null;
            l.ExpandGlances();
            Assert.IsEmpty(Long(l).Glances, "removing glanceEvery removes its glances");
        }

        // ----- glanceEvery against level18 Odile (copy: test_v2_schema_odile) -----

        [Test]
        public void GlanceEvery_expansion_equals_Odile_hand_written_glances()
        {
            string json = File.ReadAllText(Folder + "test_v2_schema_odile.json");
            LevelDef hand = LevelJson.Parse(json);
            Assert.AreEqual("test_v2_schema_odile", hand.Id, "the id inside the file matches its name");
            AssertValid(hand, "the hand-written copy");
            InhabitantDef odile = hand.Inhabitants.Find(h => h.Name == "Odile");
            Assert.IsNotNull(odile, "premise: the copy has Odile");
            int index = odile.Stations.FindIndex(s => s.Glances.Count == 34);
            Assert.GreaterOrEqual(index, 0, "premise: one of Odile's stations has 34 hand-written glances");
            List<GlanceDef> expected = odile.Stations[index].Glances;
            Assert.IsFalse(expected.Exists(g => g.Generated), "premise: hand-written glances are not generated");

            JObject o = JObject.Parse(json);
            JArray inhabitants = (JArray)o["inhabitants"];
            JObject station = null;
            foreach (JToken h in inhabitants)
            {
                if ((string)h["name"] == "Odile")
                {
                    station = (JObject)h["stations"][index];
                }
            }
            station.Remove("glances");
            station["glanceEvery"] = new JObject { ["start"] = 2.0, ["period"] = 9.0, ["hold"] = 5.0, ["yaw"] = -80.0, ["count"] = 34 };
            string compactJson = o.ToString();
            LevelDef compact = LevelJson.Parse(compactJson);
            List<GlanceDef> got = compact.Inhabitants.Find(h => h.Name == "Odile").Stations[index].Glances;
            Assert.AreEqual(expected.Count, got.Count);
            for (int k = 0; k < expected.Count; k++)
            {
                Assert.AreEqual(expected[k].Offset, got[k].Offset, Eps, $"glance {k + 1} offset");
                Assert.AreEqual(expected[k].Yaw, got[k].Yaw, Eps, $"glance {k + 1} yaw");
                Assert.AreEqual(expected[k].Hold, got[k].Hold, Eps, $"glance {k + 1} hold");
            }
            AssertValid(compact, "the compact copy");

            string once = LevelJson.Serialize(compact);
            JObject written = null;
            foreach (JToken h in (JArray)JObject.Parse(once)["inhabitants"])
            {
                if ((string)h["name"] == "Odile")
                {
                    written = (JObject)h["stations"][index];
                }
            }
            Assert.IsNull(written["glances"], "the round trip keeps the compact form");
            Assert.AreEqual(34, (int)written["glanceEvery"]["count"]);
            Assert.AreEqual(once, LevelJson.Serialize(LevelJson.Parse(once)));

            // Without a count the dwell is filled: 2 + 35 x 9 = 317 <= 320, one glance more than the hand-written list.
            station["glanceEvery"] = new JObject { ["start"] = 2.0, ["period"] = 9.0, ["hold"] = 5.0, ["yaw"] = -80.0 };
            List<GlanceDef> filled = LevelJson.Parse(o.ToString()).Inhabitants.Find(h => h.Name == "Odile").Stations[index].Glances;
            Assert.AreEqual(35, filled.Count);
            Assert.AreEqual(299f, filled[33].Offset, Eps);
            Assert.AreEqual(308f, filled[34].Offset, Eps);
        }

        // ----- Validator: rev, requires -----

        [Test]
        public void Rev_must_not_be_negative()
        {
            LevelDef l = Base();
            l.Rev = -1;
            AssertRejected(l, "rev -1 is negative");
            l.Rev = 1;
            AssertNoIssue(l, "rev ");
            Assert.AreEqual("test~1", l.RecordId);
        }

        [Test]
        public void Requires_ids_are_known_at_most_five_and_listed_once()
        {
            LevelDef l = Base();
            l.RequiredLessons = new List<string> { "speed" };
            AssertRejected(l, "requires id 'speed' is not one of", "careful", "exitwatch", "lit");
            l.RequiredLessons = new List<string> { LevelDef.LessonExitWatch };
            AssertNoIssue(l, "requires");

            l.RequiredLessons = new List<string> { "exitwatch", "door", "careful", "dark", "glide", "sit" };
            AssertRejected(l, "requires lists 6 ids: at most 5");
            l.RequiredLessons.RemoveAt(5);
            AssertNoIssue(l, "requires lists");

            l.RequiredLessons = new List<string> { "door", "door" };
            AssertRejected(l, "requires id 'door' is listed twice");
            l.RequiredLessons = new List<string> { "door" };
            AssertNoIssue(l, "listed twice");
        }

        [Test]
        public void Every_new_lesson_id_is_accepted_and_the_old_ones_keep_their_order()
        {
            CollectionAssert.AreEqual(new[] { "careful", "sit", "dark", "glide" }, System.Linq.Enumerable.Take(LevelDef.Lessons, 4));
            CollectionAssert.IsSubsetOf(new[] { "door", "pet", "split", "robot", "rock", "load", "final", "wardrobe",
                "rug", "hum", "contact", "household", "decoy", "exitwatch", "lit" }, LevelDef.Lessons);
            // A new id is a lesson too, with the same prerequisite.
            LevelDef l = Base();
            l.Lesson = LevelDef.LessonHum;
            AssertRejected(l, "lesson hum needs a robot");
            l.Robots.Add(Robot());
            AssertNoIssue(l, "lesson hum");
        }

        [Test]
        public void Requires_hum_and_contact_need_a_robot()
        {
            LevelDef l = Base();
            l.RequiredLessons = new List<string> { LevelDef.LessonHum, LevelDef.LessonContact };
            AssertRejected(l, "requires hum needs a robot");
            AssertRejected(l, "requires contact needs a robot");
            l.Robots.Add(Robot());
            AssertNoIssue(l, "requires hum");
            AssertNoIssue(l, "requires contact");
        }

        [Test]
        public void Requires_household_needs_a_leaf_inhabitants_open()
        {
            LevelDef l = Base();
            l.RequiredLessons = new List<string> { LevelDef.LessonHousehold };
            AssertRejected(l, "requires household needs a door leaf that inhabitants open");
            Porte(l).OpenedByInhabitants = true;
            AssertNoIssue(l, "requires household");
        }

        [Test]
        public void Requires_decoy_needs_a_decoy_of_the_player_kind()
        {
            LevelDef l = Base();
            l.RequiredLessons = new List<string> { LevelDef.LessonDecoy };
            AssertRejected(l, "requires decoy needs a decoy of the player's kind (chair)");
            l.Decoys.Add(new DecoyDef { Kind = BodyKinds.Stool, X = 4f, Z = 0.5f });
            AssertRejected(l, "requires decoy needs a decoy of the player's kind");
            l.Decoys.Add(new DecoyDef { Kind = BodyKinds.Chair, X = 5f, Z = 0.5f });
            AssertNoIssue(l, "requires decoy");
        }

        [Test]
        public void Requires_lit_needs_lit_zones_and_the_floor_lamp()
        {
            LevelDef l = Base();
            SetBody(l, BodyKinds.FloorLamp);
            l.RequiredLessons = new List<string> { LevelDef.LessonLit };
            AssertRejected(l, "requires lit needs lit zones");
            l.LitZones.Add(new LitZoneDef { Name = "z", X = 3f, Z = 0f, SizeX = 1f, SizeZ = 1f });
            AssertNoIssue(l, "requires lit");
            SetBody(l, BodyKinds.Chair);
            AssertRejected(l, "requires lit needs the floor lamp body, not the chair");
        }

        [Test]
        public void Requires_exitwatch_needs_an_exit()
        {
            LevelDef l = Base();
            l.RequiredLessons = new List<string> { LevelDef.LessonExitWatch };
            AssertNoIssue(l, "requires exitwatch");
            l.Exit = null;
            AssertRejected(l, "requires exitwatch needs an exit zone");
        }

        [Test]
        public void Requires_pet_needs_a_dog()
        {
            LevelDef l = Base();
            l.RequiredLessons = new List<string> { LevelDef.LessonPet };
            AssertRejected(l, "requires pet needs a dog");
            l.Inhabitants.Add(Dog());
            AssertNoIssue(l, "requires pet");
        }

        [Test]
        public void Requires_wardrobe_needs_a_wardrobe_the_body_fits()
        {
            LevelDef l = Base();
            l.RequiredLessons = new List<string> { LevelDef.LessonWardrobe };
            l.Props.Add(new PropDef { Name = "Armoire", Kind = WardrobeRule.Kind, X = 5f, Z = 1.7f, Yaw = 180f, SizeX = Tuning.WardrobeSizeX,
                SizeY = Tuning.WardrobeSizeY, SizeZ = Tuning.WardrobeSizeZ });
            AssertRejected(l, "requires wardrobe needs a wardrobe and a body that fits in it", "not the chair");
            SetBody(l, BodyKinds.Stool);
            AssertNoIssue(l, "requires wardrobe");
            l.Props.RemoveAt(1);
            AssertRejected(l, "requires wardrobe needs a wardrobe");
        }

        [Test]
        public void Requires_door_needs_a_closed_leaf_the_player_may_open()
        {
            LevelDef l = Base();
            l.RequiredLessons = new List<string> { LevelDef.LessonDoor };
            AssertNoIssue(l, "requires door");
            Porte(l).OpenedByInhabitants = true;
            Porte(l).PlayerLocked = true;
            AssertRejected(l, "requires door needs a closed leaf the player may open");
            Porte(l).PlayerLocked = false;
            Porte(l).OpenedByInhabitants = false;
            Porte(l).Leaf = "open";
            AssertRejected(l, "requires door needs a closed leaf");
        }

        [Test]
        public void Requires_rug_needs_a_rug_or_a_soft_room()
        {
            LevelDef l = Base();
            l.RequiredLessons = new List<string> { LevelDef.LessonRug };
            AssertRejected(l, "requires rug needs a rug or a soft room");
            l.Rugs.Add(new RugDef { X = 3f, Z = -0.5f, SizeX = 2f, SizeZ = 0.8f });
            AssertNoIssue(l, "requires rug");
            l.Rugs.Clear();
            l.Rooms[1].Floor = RoomDef.SoftFloor;
            AssertNoIssue(l, "requires rug");
        }

        [Test]
        public void Requires_reuses_the_old_lesson_prerequisites()
        {
            LevelDef l = Base();
            l.RequiredLessons = new List<string> { LevelDef.LessonCareful };
            AssertRejected(l, "requires careful needs a body that tips (the stool), not the chair");
            SetBody(l, BodyKinds.Stool);
            AssertNoIssue(l, "requires careful");
        }

        // ----- Validator: pace -----

        [Test]
        public void Pace_values_are_in_range()
        {
            LevelDef l = Base();
            l.Pace = new PaceDef { MinShare = 0.25f, MaxShare = 0.4f, MinPauses = 3, MaxPause = Tuning.AuditMaxWait };
            AssertNoIssue(l, "pace");
            l.Pace = new PaceDef();
            AssertNoIssue(l, "pace");

            l.Pace = new PaceDef { MinShare = -0.1f };
            AssertRejected(l, "pace minShare", "is outside 0 to 1");
            l.Pace = new PaceDef { MaxShare = 1.2f };
            AssertRejected(l, "pace maxShare", "is outside 0 to 1");
            l.Pace = new PaceDef { MinShare = 0.5f, MaxShare = 0.4f };
            AssertRejected(l, "pace minShare", "is above maxShare");
            l.Pace = new PaceDef { MinShare = 0.4f, MaxShare = 0.4f };
            AssertNoIssue(l, "pace");
            l.Pace = new PaceDef { MinPauses = -1 };
            AssertRejected(l, "pace minPauses -1 is negative");
            l.Pace = new PaceDef { MinPauses = 0 };
            AssertNoIssue(l, "pace");
            l.Pace = new PaceDef { MaxPause = 0f };
            AssertRejected(l, "pace maxPause", "is outside (0,");
            l.Pace = new PaceDef { MaxPause = Tuning.AuditMaxWait + 0.5f };
            AssertRejected(l, "pace maxPause", "is outside (0,");
        }

        // ----- Validator: via checks -----

        [Test]
        public void Via_checks_lie_inside_a_room_have_unique_names_and_number_at_most_two()
        {
            LevelDef l = Base();
            l.ViaChecks.Add(new ViaCheckDef { Name = "v1", X = 3f, Z = 0f, SizeX = 1f, SizeZ = 1f });
            AssertNoIssue(l, "via check");
            l.ViaChecks[0].X = 0f; // straddles the shared wall
            AssertRejected(l, "via check v1", "is not inside a room");
            l.ViaChecks[0].X = 3f;

            l.ViaChecks.Add(new ViaCheckDef { Name = "v1", X = 5f, Z = 0f, SizeX = 1f, SizeZ = 1f });
            AssertRejected(l, "via check name v1 is used twice");
            l.ViaChecks[1].Name = "v2";
            AssertNoIssue(l, "via check");
            l.ViaChecks.Add(new ViaCheckDef { Name = "v3", X = -2f, Z = -1f, SizeX = 1f, SizeZ = 1f });
            AssertRejected(l, "3 via checks: at most 2");
            l.ViaChecks.RemoveAt(2);

            l.ViaChecks[1].Name = null;
            AssertRejected(l, "has no name");
            l.ViaChecks[1].Name = "v2";
            l.ViaChecks[1].SizeX = 0f;
            AssertRejected(l, "via check v2 has a non positive size");
            l.ViaChecks[1].SizeX = 1f;
            l.ViaChecks[1].MaxRatio = 0.9f;
            AssertRejected(l, "via check v2 maxRatio", "is below 1");
            l.ViaChecks[1].MaxRatio = 1f;
            AssertNoIssue(l, "via check");
        }

        // ----- Validator: lit zones -----

        [Test]
        public void Lit_zones_lie_inside_one_room_clear_of_the_exit_at_most_four_on_a_lamp_level()
        {
            LevelDef l = Base();
            SetBody(l, BodyKinds.FloorLamp);
            l.LitZones.Add(new LitZoneDef { Name = "z1", X = 3f, Z = 0f, SizeX = 1f, SizeZ = 1f });
            AssertNoIssue(l, "lit zone");
            l.LitZones[0].X = 0f;
            AssertRejected(l, "lit zone z1", "is not inside one room");
            l.LitZones[0].X = -3.55f;
            l.LitZones[0].Z = -1.25f;
            AssertRejected(l, "lit zone z1 overlaps the exit zone");
            l.LitZones[0].X = -2.5f;
            l.LitZones[0].Z = 1f;
            AssertNoIssue(l, "lit zone");
            l.LitZones[0].SizeZ = 0f;
            AssertRejected(l, "lit zone z1 has a non positive size");
            l.LitZones[0].SizeZ = 1f;

            for (int i = 2; i <= 5; i++)
            {
                l.LitZones.Add(new LitZoneDef { Name = "z" + i, X = 0.6f + i, Z = -1f, SizeX = 0.8f, SizeZ = 0.8f });
            }
            AssertRejected(l, "5 lit zones: at most 4");
            l.LitZones.RemoveAt(4);
            AssertNoIssue(l, "lit zone");

            SetBody(l, BodyKinds.Chair);
            AssertRejected(l, "lit zones on a chair level");
        }

        // ----- Validator: lighting, playerLocked -----

        [Test]
        public void Lighting_is_day_or_night()
        {
            LevelDef l = Base();
            l.Lighting = "dusk";
            AssertRejected(l, "lighting 'dusk' is not one of day, night");
            l.Lighting = LevelDef.LightingNight;
            AssertNoIssue(l, "lighting");
            l.Lighting = LevelDef.LightingDay;
            AssertNoIssue(l, "lighting");
        }

        [Test]
        public void PlayerLocked_needs_a_closed_leaf_that_inhabitants_open()
        {
            LevelDef l = Base();
            Porte(l).PlayerLocked = true;
            AssertRejected(l, "door 1 is playerLocked: it needs a closed leaf");
            Porte(l).OpenedByInhabitants = true;
            AssertNoIssue(l, "playerLocked");
            Porte(l).Leaf = "open";
            AssertRejected(l, "door 1 is playerLocked: it needs a closed leaf (leaf 'open')");
            Porte(l).Leaf = "closed";
            l.Windows.Add(new OpeningDef { X = 3f, Z = -2.05f, Width = 1f, Bottom = 0.9f, Top = 2f, PlayerLocked = true });
            AssertRejected(l, "window 1 is playerLocked");
            l.Windows[0].PlayerLocked = false;
            AssertNoIssue(l, "playerLocked");
        }

        // ----- Validator: glanceEvery -----

        [Test]
        public void GlanceEvery_period_leaves_room_for_two_head_turns()
        {
            Assert.AreEqual(7f, LevelValidator.GlanceEveryMinPeriod(5f, -80f), Eps, "5 + 2 x (0.6 + 80 / 200)");
            LevelDef l = Base();
            Long(l).GlanceEvery = new GlanceEveryDef { Start = 1f, Period = 6.9f, Hold = 5f, Yaw = 80f };
            AssertRejected(l, "inhabitant H station 2 glanceEvery period", "two head turns");
            Long(l).GlanceEvery.Period = 7f;
            AssertNoIssue(l, "glanceEvery");
            Long(l).GlanceEvery.Period = 0f;
            AssertRejected(l, "glanceEvery needs a start and a hold not negative and a positive period");
        }

        [Test]
        public void GlanceEvery_yaw_is_within_the_head_limit()
        {
            LevelDef l = Base();
            Long(l).GlanceEvery = new GlanceEveryDef { Period = 9f, Hold = 2f, Yaw = -85f };
            AssertRejected(l, "glanceEvery yaw -85 exceeds the head limit");
            Long(l).GlanceEvery.Yaw = -80f;
            AssertNoIssue(l, "glanceEvery");
        }

        [Test]
        public void GlanceEvery_fits_in_the_dwell()
        {
            LevelDef l = Base();
            Long(l).GlanceEvery = new GlanceEveryDef { Start = 2f, Period = 6f, Hold = 2f, Yaw = 40f, Count = 4 };
            AssertRejected(l, "glanceEvery runs past the dwell");
            Long(l).GlanceEvery.Count = 3; // 2 + 3 x 6 = 20 = dwell
            AssertNoIssue(l, "glanceEvery");
            Long(l).GlanceEvery.Count = 0;
            AssertRejected(l, "glanceEvery count 0 is below 1");
            Long(l).GlanceEvery.Count = null;
            Long(l).GlanceEvery.Start = 25f;
            AssertRejected(l, "glanceEvery fits no glance in the dwell");
        }

        [Test]
        public void GlanceEvery_is_never_on_a_dog()
        {
            LevelDef l = Base();
            l.Inhabitants.Add(Dog());
            l.Inhabitants[1].Stations[0].GlanceEvery = new GlanceEveryDef { Period = 9f, Hold = 2f, Yaw = 40f };
            AssertRejected(l, "inhabitant Rex station 1 glanceEvery: a dog has no glances");
            l.Inhabitants[1].Stations[0].GlanceEvery = null;
            AssertNoIssue(l, "glanceEvery");
        }

        // ----- Manifest -----

        [Test]
        public void ParseFull_reads_rev_previous_and_acts_and_Parse_still_returns_the_list()
        {
            const string json = "{ \"rev\": 2, \"previous\": [\"level1\", \"level10\"], \"levels\": [\"level1\", \"level2\", \"level3\"], "
                + "\"acts\": [{ \"from\": 0, \"nameKey\": \"act1.name\" }, { \"from\": 2, \"nameKey\": \"act2.name\" }], \"note\": \"ignored\" }";
            ManifestDef m = LevelManifest.ParseFull(json);
            Assert.AreEqual(2, m.Rev);
            CollectionAssert.AreEqual(new[] { "level1", "level10" }, m.Previous);
            CollectionAssert.AreEqual(new[] { "level1", "level2", "level3" }, m.Levels);
            Assert.AreEqual(2, m.Acts.Count);
            Assert.AreEqual(2, m.Acts[1].From);
            Assert.AreEqual("act2.name", m.Acts[1].NameKey);
            CollectionAssert.AreEqual(new[] { "level1", "level2", "level3" }, LevelManifest.Parse(json), "Parse returns the play order");

            ManifestDef v1 = LevelManifest.ParseFull("{ \"levels\": [\"level1\"] }");
            Assert.AreEqual(1, v1.Rev, "a manifest without rev is rev 1");
            Assert.IsEmpty(v1.Previous);
            Assert.IsEmpty(v1.Acts);
            CollectionAssert.AreEqual(new[] { "level1" }, v1.Levels);

            string shipped = File.ReadAllText(Folder + LevelManifest.FileName + ".json");
            CollectionAssert.AreEqual(LevelManifest.Parse(shipped), LevelManifest.ParseFull(shipped).Levels, "both read the shipped manifest alike");
        }

        // ----- Shipped files -----

        [Test]
        public void Every_shipped_level_file_and_the_title_house_still_load_validate_and_round_trip()
        {
            var ids = new List<string>();
            foreach (string path in Directory.GetFiles(Folder, "level*.json"))
            {
                string id = Path.GetFileNameWithoutExtension(path);
                if (id != LevelManifest.FileName)
                {
                    ids.Add(id);
                }
            }
            Assert.GreaterOrEqual(ids.Count, 24, "premise: the 24 v1 level files are on disk");
            foreach (string id in ids)
            {
                LevelDef l = Load(id);
                Assert.IsNotNull(l, id);
                AssertValid(l, id);
                string once = LevelJson.Serialize(l);
                Assert.AreEqual(once, LevelJson.Serialize(LevelJson.Parse(once)), id + " round trip");
            }
            // The title background is never played: it must load and round trip, and no v2 rule may add an issue to it.
            LevelDef title = Load("title_house");
            Assert.IsNotNull(title, "title_house");
            string titleJson = LevelJson.Serialize(title);
            Assert.AreEqual(titleJson, LevelJson.Serialize(LevelJson.Parse(titleJson)), "title_house round trip");
            List<string> titleIssues = Issues(title);
            Debug.Log($"[LevelDefV2Tests] title_house validator issues: {titleIssues.Count}" + (titleIssues.Count > 0 ? ": " + string.Join(" | ", titleIssues) : ""));
            foreach (string fragment in new[] { "rev ", "requires", "pace ", "via check", "lit zone", "lighting", "playerLocked", "glanceEvery" })
            {
                Assert.IsFalse(titleIssues.Exists(i => i.Contains(fragment)), $"title_house gets a v2 issue ({fragment}): " + string.Join(" | ", titleIssues));
            }
        }
    }
}
