using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using OutOfSight.Core;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M8 room types (docs/m8/ROOMS_PLAN.md 2 and 5): the optional room field "type", its inference from the room id when it
    /// is missing, the optional "lightWall" field, their JSON and their validation.
    /// </summary>
    public sealed class LevelDataM8RoomTypeTests
    {
        private const string Folder = "Assets/Resources/Levels/";

        private static LevelDef Load(string id) => LevelJson.Parse(File.ReadAllText(Folder + id + ".json"));

        [Test]
        public void Every_id_of_the_plan_table_infers_its_type()
        {
            var table = new Dictionary<string, string>
            {
                { "sdb", RoomTypes.Bathroom }, { "salle_de_bain", RoomTypes.Bathroom }, { "bain", RoomTypes.Bathroom },
                { "cuisine", RoomTypes.Kitchen }, { "cafet", RoomTypes.Kitchen }, { "cafeteria", RoomTypes.Kitchen }, { "office", RoomTypes.Kitchen },
                { "salle", RoomTypes.Dining }, { "salle_a_manger", RoomTypes.Dining },
                { "salon", RoomTypes.Living }, { "sejour", RoomTypes.Living }, { "veranda", RoomTypes.Living },
                { "chambre", RoomTypes.Bedroom }, { "boudoir", RoomTypes.Bedroom },
                { "bureau", RoomTypes.Study }, { "direction", RoomTypes.Study }, { "bibliotheque", RoomTypes.Study }, { "archives", RoomTypes.Study },
                { "reunion", RoomTypes.Study }, { "openspace", RoomTypes.Study }, { "plateau", RoomTypes.Study },
                { "entree", RoomTypes.Hall }, { "vestibule", RoomTypes.Hall }, { "accueil", RoomTypes.Hall }, { "hall", RoomTypes.Hall },
                { "couloir", RoomTypes.Corridor }, { "galerie", RoomTypes.Corridor },
            };
            foreach (KeyValuePair<string, string> row in table)
            {
                Assert.AreEqual(row.Value, RoomTypes.Infer(row.Key), $"'{row.Key}'");
            }
        }

        [Test]
        public void Inference_ignores_case_and_accents_and_reads_prefixes()
        {
            Assert.AreEqual(RoomTypes.Kitchen, RoomTypes.Infer("CUISINE"));
            Assert.AreEqual(RoomTypes.Hall, RoomTypes.Infer("Entrée"));
            Assert.AreEqual(RoomTypes.Living, RoomTypes.Infer("Séjour"));
            Assert.AreEqual(RoomTypes.Corridor, RoomTypes.Infer("couloir_est"));
            Assert.AreEqual(RoomTypes.Corridor, RoomTypes.Infer("galerie_est"));
            Assert.AreEqual(RoomTypes.Corridor, RoomTypes.Infer("couloirs"), "couloir* is a stem");
            Assert.AreEqual(RoomTypes.Bedroom, RoomTypes.Infer("chambre2"));
            Assert.AreEqual(RoomTypes.Bedroom, RoomTypes.Infer("chambre_parents"));
            Assert.AreEqual(RoomTypes.Bathroom, RoomTypes.Infer("sdb-haut"));
            Assert.AreEqual(RoomTypes.Bathroom, RoomTypes.Infer("salle_de_bains"), "the longer key wins over 'salle'");
            Assert.AreEqual(RoomTypes.Dining, RoomTypes.Infer("salle_est"));
        }

        [Test]
        public void Unknown_or_missing_ids_are_other()
        {
            Assert.AreEqual(RoomTypes.Other, RoomTypes.Infer(null));
            Assert.AreEqual(RoomTypes.Other, RoomTypes.Infer(""));
            Assert.AreEqual(RoomTypes.Other, RoomTypes.Infer("mezzanine"));
            Assert.AreEqual(RoomTypes.Other, RoomTypes.Infer("passage"));
            Assert.AreEqual(RoomTypes.Other, RoomTypes.Infer("salonnette"), "a key followed by a letter is another word");
            Assert.AreEqual(RoomTypes.Other, RoomTypes.Infer("piece"));
        }

        [Test]
        public void Room_type_is_the_declared_one_else_the_inferred_one()
        {
            var room = new RoomDef { Id = "cuisine" };
            Assert.IsNull(room.DeclaredType, "premise: no type given");
            Assert.AreEqual(RoomTypes.Kitchen, room.Type, "inferred from the id");
            room.DeclaredType = RoomTypes.Dining;
            Assert.AreEqual(RoomTypes.Dining, room.Type, "the declared type wins over the id");
            room.Type = RoomTypes.Study;
            Assert.AreEqual(RoomTypes.Study, room.DeclaredType, "setting Type sets the declared type");
            room.Type = null;
            Assert.AreEqual(RoomTypes.Kitchen, room.Type, "cleared: inferred again");
            Assert.AreEqual(RoomTypes.Other, new RoomDef().Type, "an M1 room without id");
            Assert.AreEqual(RoomTypes.Other, RoomTypes.Of(null));
        }

        [Test]
        public void Level_json_reads_the_type_and_light_wall_and_omits_the_defaults()
        {
            LevelDef l = Load("level4");
            string plain = LevelJson.Serialize(l);
            Assert.IsFalse(plain.Contains("\"type\""), "no type given: none written");
            Assert.IsFalse(plain.Contains("\"lightWall\""), "no light wall given: none written");
            Assert.AreEqual(plain, LevelJson.Serialize(LevelJson.Parse(plain)), "premise: lossless round trip");

            l.Rooms[0].Type = RoomTypes.Living;
            l.Rooms[1].LightWall = "-x";
            string json = LevelJson.Serialize(l);
            StringAssert.Contains("\"type\": \"living\"", json);
            StringAssert.Contains("\"lightWall\": \"-x\"", json);
            LevelDef back = LevelJson.Parse(json);
            Assert.AreEqual(RoomTypes.Living, back.Rooms[0].DeclaredType);
            Assert.AreEqual(RoomTypes.Living, back.Rooms[0].Type);
            Assert.AreEqual("-x", back.Rooms[1].LightWall);
            Assert.AreEqual(json, LevelJson.Serialize(back), "lossless round trip with a type");

            LevelDef parsed = LevelJson.Parse(plain.Replace("\"id\": \"salon\",", "\"id\": \"salon\",\n      \"type\": \"study\","));
            Assert.AreEqual(RoomTypes.Study, parsed.AllRooms().Find(r => r.Id == "salon").Type, "a type in the file is read");
        }

        [Test]
        public void Validator_accepts_every_type_and_light_wall_and_the_defaults()
        {
            LevelDef l = Load("level4");
            Assert.IsEmpty(LevelValidator.Validate(l), "premise: level4 is valid without a type");
            foreach (string type in RoomTypes.All)
            {
                l.Rooms[0].Type = type;
                Assert.IsEmpty(LevelValidator.Validate(l), $"the type '{type}' should be valid");
            }
            foreach (string wall in RoomDef.LightWalls)
            {
                l.Rooms[0].LightWall = wall;
                Assert.IsEmpty(LevelValidator.Validate(l), $"the light wall '{wall}' should be valid");
            }
        }

        [Test]
        public void Validator_rejects_an_unknown_type_or_light_wall()
        {
            LevelDef l = Load("level4");
            l.Rooms[0].Type = "garage";
            Assert.That(LevelValidator.Validate(l), Has.Some.Contains("type 'garage'"));
            l.Rooms[0].Type = "Kitchen";
            Assert.That(LevelValidator.Validate(l), Has.Some.Contains("type 'Kitchen'"), "types are lower case");
            l.Rooms[0].Type = null;
            l.Rooms[0].LightWall = "north";
            Assert.That(LevelValidator.Validate(l), Has.Some.Contains("light wall 'north'"));
        }

        [Test]
        public void Every_room_of_the_manifest_levels_gets_a_known_type()
        {
            List<string> order = LevelManifest.Parse(File.ReadAllText(Folder + "levels.json"));
            int typed = 0;
            foreach (string id in order)
            {
                foreach (RoomDef r in Load(id).AllRooms())
                {
                    Assert.IsTrue(RoomTypes.IsKnown(r.Type), $"{id}: room {r.Id} has the type '{r.Type}'");
                    // Levels v2: a room may declare its type in the file (level25's "reserve" declares "other" on
                    // purpose); only an undeclared named room must be in the inference table.
                    if (r.Id != null && string.IsNullOrEmpty(r.DeclaredType))
                    {
                        Assert.AreNotEqual(RoomTypes.Other, r.Type, $"{id}: room {r.Id} is not in the inference table");
                    }
                    if (r.Id != null)
                    {
                        typed++;
                    }
                }
            }
            // The survey had 106 rooms over 24 levels; the 22 levels of v2 hold about 90. At least two named rooms per level.
            Assert.Greater(typed, 2 * order.Count, "premise: the rooms of the manifest levels are checked");
        }
    }
}
