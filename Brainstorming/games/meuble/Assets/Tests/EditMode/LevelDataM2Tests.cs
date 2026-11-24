using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// docs/CONTRACT_M2.md 4 and 10 (level data): LevelDef v2, its helpers, every validator rule added in
    /// M2 (one negative test each, on a small two room level that is valid as built), levels.json, and the
    /// shipped levels 1 to 3.
    /// </summary>
    public sealed class LevelDataM2Tests
    {
        private const string Folder = "Assets/Resources/Levels/";

        private static LevelDef Load(string id) => LevelJson.Parse(File.ReadAllText(Folder + id + ".json"));

        /// <summary>
        /// The play order of levels v2 (docs/levels_v2/LEVELS_V2.md 3 and 7), manifest rev 3 (ACT3A, docs/next/LEVEL_REVIEW.md
        /// 5.3): 20 levels in three acts (7 + 9 + 4). The cut level10, level16 and level23 stay on disk unlisted (D2);
        /// level12 (The Dog) plays before level15 (D4); act 3 opens on level25 (The Showroom) and ends on the finale level24;
        /// level21 (The Catwalk) and level20 (Midnight Munchies) are parked out of the line-up, their files kept.
        /// </summary>
        private static readonly string[] PlayOrder =
        {
            "level1", "level2", "level3", "level11", "level5", "level6", "level7",
            "level8", "level9", "level12", "level4", "level15", "level13", "level14", "level18", "level17",
            "level25", "level19", "level22", "level24",
        };

        /// <summary>
        /// The play order of manifest rev 3 (20 levels), the "previous" list of rev 4 for the one-shot save migration. Rev 4
        /// (2026-11-24, user request) swaps card 4 and card 11: level4 played much harder than everything before it.
        /// </summary>
        private static readonly string[] Rev3Order =
        {
            "level1", "level2", "level3", "level4", "level5", "level6", "level7",
            "level8", "level9", "level12", "level11", "level15", "level13", "level14", "level18", "level17",
            "level25", "level19", "level22", "level24",
        };

        /// <summary>ACT3A (rev 3): the act 3 levels taken out of the line-up for now, their files kept on disk and valid.</summary>
        private static readonly string[] ParkedLevels = { "level21", "level20" };

        /// <summary>The first index of each act in <see cref="PlayOrder"/> (LEVELS_V2 3 and 7).</summary>
        private static readonly int[] ActStarts = { 0, 7, 16 };

        /// <summary>The levels cut in v2 (LEVELS_V2 5 "Cut levels", D2): never listed, their files kept and valid.</summary>
        private static readonly string[] CutLevels = { "level10", "level16", "level23" };

        /// <summary>
        /// Room a: x in [-4, 0], hard. Room b: x in [0.1, 4.1], soft. Both z in [-2, 2], walls 0.1 thick, so
        /// the shared wall line is x = 0.05. A doorway in it at z = 0, the exit door in b's +x wall.
        /// </summary>
        private static LevelDef TwoRooms()
        {
            return new LevelDef
            {
                Id = "test",
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
                Player = new SpawnDef { Kind = "chair", X = -3f, Z = -1f, SizeX = 0.45f, SizeY = 0.9f, SizeZ = 0.45f, Color = "#D7263D" },
                Exit = new ZoneDef { X = 3.5f, Z = 1f, SizeX = 0.9f, SizeZ = 0.9f },
                Rugs = new List<RugDef> { new RugDef { X = -2f, Z = 1f, SizeX = 1f, SizeZ = 0.6f, Yaw = 30f, Color = "#2E6DB4" } },
                Decoys = new List<DecoyDef> { new DecoyDef { Kind = "chair", X = -1f, Z = -1.2f, Yaw = 0f, Color = "#8C5A36" } },
                Props = new List<PropDef> { new PropDef { Name = "Box", Kind = "box", X = 2f, Z = -1.5f, SizeX = 0.6f, SizeY = 0.8f, SizeZ = 0.6f } },
                Inhabitants = new List<InhabitantDef>
                {
                    new InhabitantDef
                    {
                        Name = "H",
                        Stations = new List<StationDef>
                        {
                            new StationDef { X = -2f, Z = 0f, Facing = 0f, Dwell = 2f },
                            new StationDef { X = 2f, Z = 0.5f, Facing = 90f, Dwell = 2f },
                        },
                    },
                },
                DesignerRoute = new List<RouteStepDef>
                {
                    new RouteStepDef { X = -1f, Z = 0f, At = 0f },
                    new RouteStepDef { X = 2f, Z = 0f, At = 3f },
                },
            };
        }

        /// <summary>One issue must contain every fragment. Fragments hold no number: issues format floats in the current culture.</summary>
        private static void AssertRejected(LevelDef level, params string[] fragments)
        {
            List<string> issues = LevelValidator.Validate(level);
            bool found = issues.Exists(issue => System.Array.TrueForAll(fragments, f => issue.Contains(f)));
            Assert.IsTrue(found, $"no issue contains [{string.Join(", ", fragments)}]; issues: " + string.Join(" | ", issues));
        }

        // ----- The fixture itself, so every negative test below fails for its own reason -----

        [Test]
        public void Two_room_fixture_is_valid()
        {
            List<string> issues = LevelValidator.Validate(TwoRooms());
            Assert.IsEmpty(issues, string.Join("\n", issues));
        }

        // ----- JSON -----

        [Test]
        public void V2_round_trip_is_lossless()
        {
            LevelDef original = TwoRooms();
            string once = LevelJson.Serialize(original);
            LevelDef back = LevelJson.Parse(once);
            Assert.AreEqual(once, LevelJson.Serialize(back));
            Assert.AreEqual(2, back.Rooms.Count);
            Assert.AreEqual("soft", back.Rooms[1].Floor);
            Assert.AreEqual(2.1f, back.Rooms[1].X, 1e-5f);
            Assert.IsNull(back.Doors[0].Wall, "a v2 door has no wall name");
            Assert.AreEqual(0.05f, back.Doors[0].X, 1e-5f);
            Assert.AreEqual(30f, back.Rugs[0].Yaw, 1e-5f);
            Assert.AreEqual("#8C5A36", back.Decoys[0].Color);
            Assert.AreEqual(3f, back.DesignerRoute[1].At, 1e-5f);
            Assert.IsNull(back.Room, "a v2 level has no M1 room");
        }

        [Test]
        public void Shipped_v2_levels_round_trip()
        {
            foreach (string id in new[] { "level2", "level3" })
            {
                LevelDef original = Load(id);
                string once = LevelJson.Serialize(original);
                Assert.AreEqual(once, LevelJson.Serialize(LevelJson.Parse(once)), id);
            }
        }

        [Test]
        public void Door_top_defaults_to_2_1()
        {
            LevelDef l = LevelJson.Parse("{\"id\":\"x\",\"doors\":[{\"x\":0.05,\"z\":0,\"width\":1}]}");
            Assert.AreEqual(2.1f, l.Doors[0].Top, 1e-5f);
        }

        [Test]
        public void Manifest_lists_the_levels_in_play_order_and_each_is_valid()
        {
            List<string> ids = LevelManifest.Parse(File.ReadAllText(Folder + "levels.json"));
            // Levels v2 (LEVELS_V2 3 and 7), rev 3: 20 levels in the play order, none of the cut or parked ones.
            Assert.AreEqual(PlayOrder.Length, ids.Count, "the manifest count of levels: " + string.Join(", ", ids));
            CollectionAssert.AreEqual(PlayOrder, ids);
            foreach (string cut in CutLevels)
            {
                CollectionAssert.DoesNotContain(ids, cut, cut + " is cut in v2: it must not be listed");
            }
            foreach (string parked in ParkedLevels)
            {
                CollectionAssert.DoesNotContain(ids, parked, parked + " is parked (rev 3): it must not be listed");
                Assert.IsTrue(File.Exists(Folder + parked + ".json"), parked + ": the file of a parked level stays on disk");
                LevelDef level = Load(parked);
                Assert.AreEqual(parked, level.Id, "the id inside the file matches its name");
                List<string> issues = LevelValidator.Validate(level);
                Assert.IsEmpty(issues, parked + ": " + string.Join(", ", issues));
            }
            foreach (string id in ids)
            {
                LevelDef level = Load(id);
                Assert.AreEqual(id, level.Id, "the id inside the file matches its name");
                List<string> issues = LevelValidator.Validate(level);
                Assert.IsEmpty(issues, id + ": " + string.Join("\n", issues));
            }
        }

        [Test]
        public void Manifest_is_the_rev4_order_with_its_acts_and_the_rev3_order_as_previous()
        {
            // LEVELS_V2 7, ACT3A: rev 3, the 22 ids of the rev 2 order as "previous" (the one-shot save migration), the
            // three acts.
            ManifestDef m = LevelManifest.ParseFull(File.ReadAllText(Folder + "levels.json"));
            Assert.AreEqual(4, m.Rev, "levels.json rev");
            CollectionAssert.AreEqual(PlayOrder, m.Levels, "the rev 4 play order");
            CollectionAssert.AreEqual(Rev3Order, m.Previous, "previous is the rev 3 order");
            Assert.AreEqual(ActStarts.Length, m.Acts.Count, "three acts");
            for (int i = 0; i < ActStarts.Length; i++)
            {
                Assert.AreEqual(ActStarts[i], m.Acts[i].From, $"act {i + 1} starts at index {ActStarts[i]}");
                Assert.AreEqual($"act{i + 1}.name", m.Acts[i].NameKey, $"act {i + 1} name key");
                Assert.AreNotEqual(m.Acts[i].NameKey, Strings.Get(m.Acts[i].NameKey), $"act {i + 1}: name string missing");
            }
        }

        [Test]
        public void Cut_levels_stay_on_disk_valid_with_their_routes_and_unlisted()
        {
            // LEVELS_V2 D2: level10, level16 and level23 leave levels.json only; tests and fixtures still load them by id.
            List<string> order = LevelManifest.Parse(File.ReadAllText(Folder + "levels.json"));
            foreach (string id in CutLevels)
            {
                Assert.IsTrue(File.Exists(Folder + id + ".json"), id + ": the file of a cut level stays on disk");
                LevelDef l = Load(id);
                Assert.AreEqual(id, l.Id, "the id inside the file matches its name");
                List<string> issues = LevelValidator.Validate(l);
                Assert.IsEmpty(issues, id + ": " + string.Join("\n", issues));
                CollectionAssert.DoesNotContain(order, id, id + " is cut: it must not be listed");
                Assert.GreaterOrEqual(l.DesignerRoute.Count, 2, id + ": the archived file keeps its designer route");
                Assert.AreNotEqual(Strings.Get(l.NameKey), l.NameKey, id + ": the name string of a cut level stays");
            }
            // The archived rocking chair level (the wave 5B row of level10 before v2): its lesson moved to level15.
            LevelDef ten = Load("level10");
            Assert.AreEqual(BodyKinds.RockingChair, BodyKinds.Of(ten.Player.Kind), "level10: the rocking chair");
            Assert.AreEqual(LevelDef.LessonRock, ten.Lesson, "level10: the rock lesson");
        }

        [Test]
        public void Manifest_is_not_a_level()
        {
            Assert.Throws<Newtonsoft.Json.JsonSerializationException>(() => LevelJson.Parse(File.ReadAllText(Folder + "levels.json")),
                "levels.json must never be read as a level (the audit and the tests read only the files it names)");
        }

        // ----- M1 compatibility -----

        [Test]
        public void Level1_is_still_an_M1_level_and_valid()
        {
            LevelDef l = Load("level1");
            Assert.IsNotNull(l.Room);
            Assert.IsEmpty(l.Rooms);
            Assert.IsEmpty(l.Rugs);
            Assert.IsEmpty(l.Decoys);
            Assert.AreEqual(8f, l.Room.SizeX);
            Assert.AreEqual(0f, l.Room.X);
            Assert.AreEqual("+x", l.Doors[0].Wall);
            Assert.AreEqual("-z", l.Windows[0].Wall);
            List<RoomDef> rooms = l.AllRooms();
            Assert.AreEqual(1, rooms.Count);
            Assert.AreSame(l.Room, rooms[0]);
            Assert.IsEmpty(LevelValidator.Validate(l));
        }

        [Test]
        public void Level1_keeps_its_stations_start_and_props()
        {
            // CONTRACT_M2 11.8: level 1 may only change its startStation and props no walk crosses, and
            // any such change goes back into the PRD. M2.1 changed neither.
            LevelDef l = Load("level1");
            InhabitantDef h = l.Inhabitants[0];
            // Integrator decision (PRD v1.4, 6.3 M2 note): the inhabitant starts at station 3 (index 2),
            // looking out of the window, so the first move is possible at once: no dead time at spawn.
            Assert.AreEqual(2, h.StartStation);
            // Levels v2 (LEVELS_V2 D11, amendment of CONTRACT_M2 11.8 and PRD 6.3): the window station dwells 3.5 s (was 5),
            // so a full-speed rush cannot win level 1 without its first mid-route freeze.
            float[,] stations = { { -1.5f, 2.2f, 0f, 6f }, { 1.2f, 1.4f, 180f, 3f }, { 0f, -2.3f, 180f, 3.5f }, { 2.2f, -0.7f, 180f, 4f } };
            Assert.AreEqual(4, h.Stations.Count);
            for (int i = 0; i < 4; i++)
            {
                Assert.AreEqual(stations[i, 0], h.Stations[i].X, 1e-5f, $"station {i + 1} x");
                Assert.AreEqual(stations[i, 1], h.Stations[i].Z, 1e-5f, $"station {i + 1} z");
                Assert.AreEqual(stations[i, 2], h.Stations[i].Facing, 1e-5f, $"station {i + 1} facing");
                Assert.AreEqual(stations[i, 3], h.Stations[i].Dwell, 1e-5f, $"station {i + 1} dwell");
            }
            Assert.AreEqual(new Vector3(-0.75f, 0f, -0.05f), l.Props.Find(p => p.Name == "Sofa").Position);
            Assert.AreEqual(new Vector3(2.45f, 0f, -1.9f), l.Props.Find(p => p.Name == "Table").Position);
            Assert.AreEqual(new Vector3(-1.5f, 0f, 2.8f), l.Props.Find(p => p.Name == "Bookshelf").Position);
        }

        [Test]
        public void Every_shipped_designer_route_ends_at_its_exit_and_starts_after_the_level()
        {
            // M5 (CONTRACT_M5 8 and 16.2): every level of the play order has its route, levels 8 to 17 included.
            int checkedRoutes = 0;
            List<string> order = LevelManifest.Parse(File.ReadAllText(Folder + "levels.json"));
            foreach (string id in order)
            {
                LevelDef l = Load(id);
                checkedRoutes++;
                Assert.GreaterOrEqual(l.DesignerRoute.Count, 2, id + ": no designer route (LevelAudit with -writeRoutes writes it)");
                RouteStepDef last = l.DesignerRoute[l.DesignerRoute.Count - 1];
                Assert.IsTrue(l.Exit.Contains(new Vector3(last.X, 0f, last.Z)), id + ": the route does not end in the exit");
                // Probe step 20 replays every route 0.2 s early: the first leg must not start before the level.
                Assert.GreaterOrEqual(l.DesignerRoute[0].At, 0.2f - 1e-4f, id + ": the first leg starts too early to be shifted");
                if (l.Lesson == LevelDef.LessonDoor)
                {
                    // CONTRACT_M5 8: the door lesson's route opens a door (an "open" step the audit wrote, with its door id).
                    Assert.IsTrue(l.DesignerRoute.Exists(s => s.Action == RouteStepDef.ActionOpen && !string.IsNullOrEmpty(s.Door)),
                        id + ": the route of a door level opens no door");
                }
            }
            Assert.GreaterOrEqual(checkedRoutes, PlayOrder.Length, "premise: the routes of every level of the play order are checked");
        }

        [Test]
        public void Audit_fixtures_are_valid_levels_kept_out_of_the_play_order()
        {
            // M2.2: the level audit self-test needs one fixture per rule that must make it fail.
            List<string> order = LevelManifest.Parse(File.ReadAllText(Folder + "levels.json"));
            foreach (string rule in new[] { "wait", "noise", "creak" })
            {
                string id = "test_" + rule;
                Assert.IsTrue(File.Exists(Folder + id + ".json"), id + " is missing");
                LevelDef l = Load(id);
                Assert.AreEqual(id, l.Id);
                List<string> issues = LevelValidator.Validate(l);
                Assert.IsEmpty(issues, id + ": " + string.Join("\n", issues));
                CollectionAssert.DoesNotContain(order, id, id + " must never be played");
                Assert.IsEmpty(l.DesignerRoute, id + " has no route: it must have none");
            }
        }

        // ----- M5 wave 5B: levels 9, 11, 13, 15 and 17 (CONTRACT_M5 16.10, as retuned by levels v2) and their audit fixtures -----

        /// <summary>
        /// One row of the revised level table (CONTRACT_M5 16.10): the body, the load, the room count bounds, the lesson, the
        /// people as "personality:pattern" (a dog as "dog"), the robots, the closed leaves, whether a platform is required,
        /// and the decoys of the player's kind the level must have at least.
        /// </summary>
        private sealed class WaveBRow
        {
            public string Id;
            public string Body;
            public string Load;
            public int MinRooms;
            public int MaxRooms;
            public string Lesson;
            public string[] People;
            public int Robots;
            public int ClosedLeaves;
            public bool Platform;
            public int Decoys;
        }

        private static readonly WaveBRow[] WaveB =
        {
            // Levels v2 (LEVELS_V2 5): level9 loses its kitchen (3 rooms); level15 is rebuilt as the rocker level (4 rooms,
            // napping Rex and Mamie, no robot, D20); level10 is cut (Cut_levels_stay_on_disk_valid_with_their_routes_and_unlisted).
            new WaveBRow { Id = "level9", Body = BodyKinds.Chair, MinRooms = 3, MaxRooms = 3, Lesson = LevelDef.LessonRobot,
                People = new[] { "watchful:loop" }, Robots = 1 },
            new WaveBRow { Id = "level11", Body = BodyKinds.Chair, Load = "vase", MinRooms = 4, MaxRooms = 4, Lesson = LevelDef.LessonLoad,
                People = new[] { "tidy:loop" } },
            new WaveBRow { Id = "level13", Body = BodyKinds.OfficeChair, Load = "vase", MinRooms = 5, MaxRooms = 5, Lesson = LevelDef.LessonLoad,
                People = new[] { "hurried:pingpong", "watchful:loop" }, Decoys = 2 },
            new WaveBRow { Id = "level15", Body = BodyKinds.RockingChair, MinRooms = 4, MaxRooms = 4, Lesson = LevelDef.LessonRock,
                People = new[] { "dog", "granny:loop" } },
            new WaveBRow { Id = "level17", Body = BodyKinds.Chair, Load = "vase", MinRooms = 4, MaxRooms = 7, Lesson = LevelDef.LessonFinal,
                // L16EASY (2026-11-23): Hugo (teen:wander) removed to make level17 more forgiving.
                People = new[] { "dog", "granny:loop", "tidy:loop" }, Robots = 1, ClosedLeaves = 2, Platform = true },
        };

        /// <summary>The wave 5B audit fixtures (CONTRACT_M5 10): the robot's hum, its contact, the rock and the load.</summary>
        private static readonly string[] WaveBFixtures = { "test_robot", "test_m5_levels_robotblock", "test_rock", "test_load" };

        private static string PersonOf(InhabitantDef h)
        {
            return h.Kind == PersonalityDef.Dog ? PersonalityDef.Dog : (h.Personality ?? PersonalityDef.Default) + ":" + RoutinePatterns.Normalize(h.Pattern);
        }

        [Test]
        public void Wave5B_levels_follow_the_revised_level_table()
        {
            int checkedLevels = 0;
            foreach (WaveBRow row in WaveB)
            {
                Assert.IsTrue(File.Exists(Folder + row.Id + ".json"), row.Id + " is missing");
                LevelDef l = Load(row.Id);
                Assert.AreEqual(row.Id, l.Id, "the id inside the file matches its name");
                Assert.AreEqual(row.Body, BodyKinds.Of(l.Player.Kind), row.Id + ": the body of CONTRACT_M5 16.10");
                Assert.AreEqual(row.Load, l.Player.Load, row.Id + ": the load of CONTRACT_M5 16.10");
                int rooms = l.AllRooms().Count;
                Assert.IsTrue(rooms >= row.MinRooms && rooms <= row.MaxRooms, $"{row.Id}: {rooms} rooms, the table says {row.MinRooms} to {row.MaxRooms}");
                Assert.AreEqual(row.Lesson, l.Lesson, row.Id + ": the lesson of CONTRACT_M5 16.10");
                var people = l.Inhabitants.ConvertAll(PersonOf);
                people.Sort(System.StringComparer.Ordinal);
                CollectionAssert.AreEqual(row.People, people, row.Id + ": the people (personality:pattern) of CONTRACT_M5 16.10");
                Assert.AreEqual(row.Robots, l.Robots.Count, row.Id + ": robots");
                Assert.AreEqual(row.ClosedLeaves, l.Doors.FindAll(d => d.Leaf == OpeningDef.LeafClosed).Count, row.Id + ": closed leaves");
                Assert.AreEqual(row.Platform, l.Platforms.Count > 0 && l.Ramps.Count > 0, row.Id + ": a platform and its ramps");
                int decoys = l.Decoys.FindAll(d => BodyKinds.Of(d.Kind) == row.Body).Count;
                Assert.GreaterOrEqual(decoys, row.Decoys, row.Id + ": decoys of the player's kind");
                Assert.GreaterOrEqual(l.DesignerRoute.Count, 2, row.Id + ": no designer route (LevelAudit with -writeRoutes writes it)");
                foreach (InhabitantDef h in l.Inhabitants)
                {
                    if (h.Personality == PersonalityDef.Granny)
                    {
                        // CONTRACT_M5 16.10: granny sits (a habit the audit warns about, here a hard fact of the data).
                        Assert.IsTrue(h.Stations.Exists(s => !string.IsNullOrEmpty(s.Sit)), row.Id + ": granny never sits");
                    }
                }
                checkedLevels++;
            }
            // Level 9: "hard floors and rugs".
            LevelDef nine = Load("level9");
            Assert.IsTrue(nine.Rugs.Count > 0 && nine.AllRooms().Exists(r => !r.IsSoft), "level9: hard floors and rugs");
            Assert.AreEqual(WaveB.Length, checkedLevels, "premise: every wave 5B level still played in v2 is checked");
        }

        [Test]
        public void Wave5B_levels_are_valid_and_listed_at_their_v2_slot()
        {
            // Levels v2 (LEVELS_V2 3): the number order is gone; each wave 5B level still played sits at its slot of the v2
            // order (level15 after level11, level17 after level18) and validates.
            List<string> order = LevelManifest.Parse(File.ReadAllText(Folder + "levels.json"));
            foreach (WaveBRow row in WaveB)
            {
                LevelDef l = Load(row.Id);
                List<string> issues = LevelValidator.Validate(l);
                Assert.IsEmpty(issues, row.Id + ": " + string.Join("\n", issues));
                int slot = System.Array.IndexOf(PlayOrder, row.Id);
                Assert.GreaterOrEqual(slot, 0, "premise: " + row.Id + " is in the v2 play order");
                Assert.AreEqual(slot, order.IndexOf(row.Id), row.Id + " is not at its v2 slot in levels.json: " + string.Join(", ", order));
            }
        }

        [Test]
        public void Wave5B_audit_fixtures_are_valid_levels_kept_out_of_the_play_order()
        {
            List<string> order = LevelManifest.Parse(File.ReadAllText(Folder + "levels.json"));
            foreach (string id in WaveBFixtures)
            {
                Assert.IsTrue(File.Exists(Folder + id + ".json"), id + " is missing");
                LevelDef l = Load(id);
                Assert.AreEqual(id, l.Id);
                List<string> issues = LevelValidator.Validate(l);
                Assert.IsEmpty(issues, id + ": " + string.Join("\n", issues));
                CollectionAssert.DoesNotContain(order, id, id + " must never be played");
                Assert.IsEmpty(l.DesignerRoute, id + " has no route: it must have none");
            }
            // Each fixture has what its rule is about (the audit's premise).
            Assert.AreEqual(1, Load("test_robot").Robots.Count, "test_robot: one robot, whose hum binds");
            Assert.AreEqual(1, Load("test_m5_levels_robotblock").Robots.Count, "test_m5_levels_robotblock: one robot, whose contact binds");
            Assert.IsTrue(Load("test_rock").PlayerBody().Rocks, "test_rock: a body that rocks");
            Assert.AreEqual("vase", Load("test_load").Player.Load, "test_load: a load on the player");
            Assert.AreEqual(BodyKinds.Chair, BodyKinds.Of(Load("test_load").Player.Kind), "test_load: the chair (no glide, no tip, no rock)");
        }

        [Test]
        public void M1_door_resolves_to_its_named_wall()
        {
            LevelDef l = Load("level1");
            List<RoomSide> sides = l.SidesOf(l.Doors[0], out float along);
            Assert.AreEqual(1, sides.Count);
            Assert.AreEqual("+x", sides[0].Side);
            Assert.AreEqual(4.05f, sides[0].Line, 1e-5f);
            Assert.AreEqual(2.3f, along, 1e-5f);
        }

        // ----- Helpers -----

        [Test]
        public void AllRooms_returns_the_v2_rooms()
        {
            LevelDef l = TwoRooms();
            Assert.AreSame(l.Rooms, l.AllRooms());
            Assert.AreEqual(2, l.AllRooms().Count);
        }

        [Test]
        public void AllRooms_of_an_empty_level_is_empty()
        {
            Assert.IsEmpty(new LevelDef().AllRooms());
        }

        [Test]
        public void RoomAt_finds_each_room_and_null_elsewhere()
        {
            LevelDef l = TwoRooms();
            Assert.AreEqual("a", l.RoomAt(new Vector3(-1f, 0f, 1.9f)).Id);
            Assert.AreEqual("b", l.RoomAt(new Vector3(3f, 0f, -1.9f)).Id);
            Assert.IsNull(l.RoomAt(new Vector3(0.05f, 0f, 0f)), "the doorway in the wall band is in no room");
            Assert.IsNull(l.RoomAt(new Vector3(-5f, 0f, 0f)), "the garden is in no room");
            Assert.IsNull(l.RoomAt(new Vector3(1f, 0f, 2.2f)));
        }

        [Test]
        public void Shared_door_lies_on_two_sides_outer_door_on_one()
        {
            LevelDef l = TwoRooms();
            List<RoomSide> shared = l.SidesOf(l.Doors[0], out float along);
            Assert.AreEqual(2, shared.Count);
            Assert.AreEqual(0f, along, 1e-5f);
            Assert.AreNotEqual(shared[0].Room, shared[1].Room);
            Assert.AreEqual(1, l.SidesOf(l.Doors[1], out float outerAlong).Count);
            Assert.AreEqual(1f, outerAlong, 1e-5f);
        }

        [Test]
        public void IsSilentFloor_on_a_rotated_rug_and_not_beside_it()
        {
            LevelDef l = TwoRooms();
            RugDef rug = l.Rugs[0];
            Vector3 Local(float x, float z) => rug.Position + YawMath.Rotate(new Vector3(x, 0f, z), rug.Yaw);
            Assert.IsTrue(l.IsSilentFloor(rug.Position), "rug center");
            Assert.IsTrue(l.IsSilentFloor(Local(0.45f, 0.25f)), "inside the turned rug, near its corner");
            Assert.IsFalse(l.IsSilentFloor(Local(0.45f, 0.35f)), "just past its short side");
            Assert.IsFalse(l.IsSilentFloor(Local(0.55f, 0f)), "just past its long side");
            Assert.IsFalse(l.IsSilentFloor(rug.Position + new Vector3(0.45f, 0f, 0.25f)), "the unrotated corner is off the turned rug");
        }

        [Test]
        public void IsSilentFloor_in_a_soft_room_and_not_in_a_hard_room()
        {
            LevelDef l = TwoRooms();
            Assert.IsTrue(l.IsSilentFloor(new Vector3(3f, 0f, -1.5f)), "soft room");
            Assert.IsFalse(l.IsSilentFloor(new Vector3(-3f, 0f, -1.5f)), "hard room");
            Assert.IsFalse(l.IsSilentFloor(new Vector3(0.05f, 0f, 0f)), "doorway, in no room");
            l.Rooms[1].Floor = null;
            Assert.IsFalse(l.IsSilentFloor(new Vector3(3f, 0f, -1.5f)), "floor defaults to hard");
        }

        [Test]
        public void Level1_has_no_silent_floor()
        {
            LevelDef l = Load("level1");
            Assert.IsFalse(l.IsSilentFloor(l.Player.Position));
            Assert.IsFalse(l.IsSilentFloor(Vector3.zero));
        }

        [Test]
        public void Census_counts_the_player_and_the_decoys_by_kind()
        {
            LevelDef l = TwoRooms();
            l.Decoys.Add(new DecoyDef { Kind = "chair", X = -1f, Z = 1.5f });
            l.Decoys.Add(new DecoyDef { Kind = "stool", X = 2f, Z = 1.5f });
            Dictionary<string, int> census = l.Census();
            Assert.AreEqual(3, census["chair"]);
            Assert.AreEqual(1, census["stool"]);
            Assert.AreEqual(2, census.Count);
            Assert.AreEqual(1, Load("level1").Census()["chair"], "level 1: the player chair alone");
        }

        [Test]
        public void Decoy_size_defaults_to_the_player_size()
        {
            LevelDef l = TwoRooms();
            Assert.AreEqual(new Vector3(0.45f, 0.9f, 0.45f), l.DecoySize(l.Decoys[0]));
            l.Decoys[0].SizeY = 1.2f;
            Assert.AreEqual(1.2f, l.DecoySize(l.Decoys[0]).y, 1e-5f);
        }

        [Test]
        public void Interior_bounds_cover_both_rooms_and_the_wall_between()
        {
            Rect b = TwoRooms().InteriorBounds();
            Assert.AreEqual(-4f, b.xMin, 1e-5f);
            Assert.AreEqual(4.1f, b.xMax, 1e-5f);
            Assert.AreEqual(-2f, b.yMin, 1e-5f);
            Assert.AreEqual(2f, b.yMax, 1e-5f);
        }

        // ----- Validator: one test per M2 rule -----

        [Test]
        public void Validator_rejects_room_and_rooms_together()
        {
            LevelDef l = TwoRooms();
            l.Room = new RoomDef { SizeX = 8f, SizeZ = 6f, WallHeight = 2.7f, WallThickness = 0.1f };
            AssertRejected(l, "both room and rooms");
        }

        [Test]
        public void Validator_rejects_a_room_without_wall_thickness()
        {
            LevelDef l = TwoRooms();
            l.Rooms[0].WallThickness = 0f;
            AssertRejected(l, "non positive size");
        }

        [Test]
        public void Validator_rejects_an_unknown_floor()
        {
            LevelDef l = TwoRooms();
            l.Rooms[0].Floor = "carpet";
            AssertRejected(l, "neither hard nor soft");
        }

        [Test]
        public void Validator_rejects_rooms_of_different_wall_thickness()
        {
            LevelDef l = TwoRooms();
            l.Rooms[1].WallThickness = 0.2f;
            AssertRejected(l, "all rooms share one wall thickness");
        }

        [Test]
        public void Validator_rejects_a_room_id_used_twice()
        {
            LevelDef l = TwoRooms();
            l.Rooms[1].Id = "a";
            AssertRejected(l, "used twice");
        }

        [Test]
        public void Validator_rejects_overlapping_rooms()
        {
            LevelDef l = TwoRooms();
            l.Rooms[1].X = 1f;
            AssertRejected(l, "overlap");
        }

        [Test]
        public void Validator_rejects_adjacent_rooms_not_one_wall_thickness_apart()
        {
            LevelDef l = TwoRooms();
            l.Rooms[1].X = 2.15f; // 0.15 m apart: the two walls would cross
            AssertRejected(l, "separated by exactly one wall thickness");
            l.Rooms[1].X = 2.0f; // touching interiors, no wall at all
            AssertRejected(l, "separated by exactly one wall thickness");
        }

        [Test]
        public void Validator_accepts_rooms_far_enough_apart_for_two_walls()
        {
            LevelDef l = TwoRooms();
            l.Rooms[1].X = 2.4f; // 0.4 m apart: two separate walls, not adjacent
            Assert.That(LevelValidator.Validate(l), Has.None.Contains("separated by exactly one wall thickness"));
        }

        [Test]
        public void Validator_rejects_a_door_off_every_wall()
        {
            LevelDef l = TwoRooms();
            l.Doors[0].X = 0.5f;
            AssertRejected(l, "door 1", "does not lie on a wall");
        }

        [Test]
        public void Validator_rejects_a_door_running_past_the_end_of_its_wall()
        {
            LevelDef l = TwoRooms();
            l.Doors[1].Z = 1.8f;
            AssertRejected(l, "door 2", "runs past the end of the wall");
        }

        [Test]
        public void Validator_rejects_an_m1_door_on_a_multi_room_level()
        {
            LevelDef l = TwoRooms();
            l.Doors[1] = new OpeningDef { Wall = "+x", Center = 1f, Width = 1f, Top = 2.1f };
            AssertRejected(l, "only accepted on a single room level");
        }

        [Test]
        public void Validator_rejects_a_door_taller_than_the_wall()
        {
            LevelDef l = TwoRooms();
            l.Doors[0].Top = 3f;
            AssertRejected(l, "door 1", "above the wall height");
        }

        [Test]
        public void Validator_rejects_a_door_of_zero_width()
        {
            LevelDef l = TwoRooms();
            l.Doors[0].Width = 0f;
            AssertRejected(l, "door 1", "non positive width or height");
        }

        [Test]
        public void Validator_rejects_a_window_off_every_wall()
        {
            LevelDef l = TwoRooms();
            l.Windows.Add(new OpeningDef { X = -2f, Z = 0f, Width = 1f, Bottom = 0.9f, Top = 2f });
            AssertRejected(l, "window 1", "does not lie on a wall");
        }

        [Test]
        public void Validator_rejects_rooms_not_connected_through_doors()
        {
            LevelDef l = TwoRooms();
            l.Doors.RemoveAt(0);
            AssertRejected(l, "room b is not connected to room a through doors");
        }

        [Test]
        public void Validator_rejects_a_spawn_in_no_room()
        {
            LevelDef l = TwoRooms();
            l.Player.X = 0.05f;
            l.Player.Z = 0f;
            AssertRejected(l, "player spawn", "is not inside the room");
        }

        [Test]
        public void Validator_rejects_an_exit_across_a_wall()
        {
            LevelDef l = TwoRooms();
            l.Exit.X = 0.05f;
            AssertRejected(l, "exit zone", "is not inside the room");
        }

        [Test]
        public void Validator_rejects_a_station_in_no_room()
        {
            LevelDef l = TwoRooms();
            l.Inhabitants[0].Stations[1].X = 4.5f;
            AssertRejected(l, "station 2", "is not inside the room");
        }

        [Test]
        public void Validator_rejects_a_prop_in_no_room()
        {
            LevelDef l = TwoRooms();
            l.Props[0].X = 3.9f;
            AssertRejected(l, "prop Box is not inside a room");
        }

        [Test]
        public void Validator_rejects_a_turned_prop_that_sticks_out_of_its_room()
        {
            LevelDef l = TwoRooms();
            l.Props[0].X = 3.75f;
            l.Props[0].Z = -1f;
            l.Props[0].SizeX = 0.2f;
            l.Props[0].SizeZ = 1.2f;
            Assert.IsEmpty(LevelValidator.Validate(l), "premise: along z it fits");
            l.Props[0].Yaw = 90f;
            AssertRejected(l, "prop Box is not inside a room");
        }

        [Test]
        public void Validator_rejects_a_decoy_in_no_room()
        {
            LevelDef l = TwoRooms();
            l.Decoys[0].X = -3.9f;
            AssertRejected(l, "decoy 1", "is not inside a room");
        }

        [Test]
        public void Validator_rejects_a_rug_in_no_room()
        {
            LevelDef l = TwoRooms();
            l.Rugs[0].X = -3.7f;
            AssertRejected(l, "rug 1", "is not inside a room");
        }

        [Test]
        public void Validator_rejects_a_rug_of_zero_size()
        {
            LevelDef l = TwoRooms();
            l.Rugs[0].SizeZ = 0f;
            AssertRejected(l, "rug 1 has a non positive size");
        }

        [Test]
        public void Validator_rejects_a_station_inside_a_decoy()
        {
            LevelDef l = TwoRooms();
            l.Inhabitants[0].Stations[0].X = l.Decoys[0].X + 0.3f;
            l.Inhabitants[0].Stations[0].Z = l.Decoys[0].Z;
            AssertRejected(l, "is inside decoy 1");
        }

        [Test]
        public void Validator_rejects_a_decoy_of_the_player_color()
        {
            LevelDef l = TwoRooms();
            l.Decoys[0].Color = "#d7263d";
            AssertRejected(l, "decoy 1 has the player color");
        }

        [Test]
        public void Validator_rejects_a_decoy_overlapping_a_prop()
        {
            LevelDef l = TwoRooms();
            l.Decoys[0].X = 2.3f;
            l.Decoys[0].Z = -1.5f;
            AssertRejected(l, "decoy 1 overlaps prop Box");
        }

        [Test]
        public void Validator_rejects_a_spawn_overlapping_a_decoy()
        {
            LevelDef l = TwoRooms();
            l.Decoys[0].X = l.Player.X + 0.4f;
            l.Decoys[0].Z = l.Player.Z;
            AssertRejected(l, "player spawn overlaps decoy 1");
        }

        [Test]
        public void Validator_rejects_an_exit_overlapping_a_decoy()
        {
            LevelDef l = TwoRooms();
            l.Decoys[0].X = 3.5f;
            l.Decoys[0].Z = 1f;
            AssertRejected(l, "exit zone overlaps decoy 1");
        }

        [Test]
        public void Validator_rejects_a_route_waypoint_in_no_room()
        {
            LevelDef l = TwoRooms();
            l.DesignerRoute[1].X = 0.05f;
            AssertRejected(l, "designer route waypoint 2", "is not inside a room");
        }

        [Test]
        public void Validator_rejects_route_times_that_go_back()
        {
            LevelDef l = TwoRooms();
            l.DesignerRoute.Add(new RouteStepDef { X = 3f, Z = 0f, At = 2f });
            AssertRejected(l, "designer route waypoint 3", "is before the previous one");
        }

        // ----- Shipped levels 2 and 3: the lesson each one is built around -----

        [Test]
        public void Levels_2_and_3_have_two_rooms_joined_by_one_doorway()
        {
            foreach (string id in new[] { "level2", "level3" })
            {
                LevelDef l = Load(id);
                Assert.AreEqual(2, l.Rooms.Count, id);
                int interior = 0;
                int outer = 0;
                foreach (OpeningDef door in l.Doors)
                {
                    int sides = l.SidesOf(door, out _).Count;
                    interior += sides == 2 ? 1 : 0;
                    outer += sides == 1 ? 1 : 0;
                }
                Assert.AreEqual(1, interior, id + ": one doorway between the rooms");
                Assert.AreEqual(1, outer, id + ": one outer door, the exit");
                Assert.AreNotEqual(Strings.Get(l.NameKey), l.NameKey, id + ": name string missing");
                Assert.AreNotEqual(Strings.Get(l.HintKey), l.HintKey, id + ": hint string missing");
            }
        }

        [Test]
        public void Level2_is_hard_floored_with_a_rug_path_within_earshot_of_a_station()
        {
            LevelDef l = Load("level2");
            foreach (RoomDef room in l.Rooms)
            {
                Assert.IsFalse(room.IsSoft, "level 2 teaches rugs on a hard floor");
            }
            Assert.IsNotEmpty(l.Rugs);
            // A rug passes close behind a station: a hop there would be heard, the rug makes it silent.
            bool rugInEarshot = false;
            foreach (StationDef s in l.Inhabitants[0].Stations)
            {
                foreach (RugDef rug in l.Rugs)
                {
                    if (YawMath.Planar(rug.Position - s.Position).magnitude < Tuning.HopNoiseRadius)
                    {
                        rugInEarshot = true;
                    }
                }
            }
            Assert.IsTrue(rugInEarshot, "no rug within the hop noise radius of any station");
        }

        [Test]
        public void Level3_has_decoys_around_the_table_and_one_beside_the_doorway()
        {
            LevelDef l = Load("level3");
            PropDef table = l.Props.Find(p => p.Kind == "table" && p.Name == "Table");
            Assert.IsNotNull(table);
            int around = 0;
            foreach (DecoyDef d in l.Decoys)
            {
                Assert.AreEqual(l.Player.Kind, d.Kind, "decoys are of the player's kind");
                if (YawMath.Planar(d.Position - table.Position).magnitude < 1.5f)
                {
                    around++;
                }
            }
            Assert.GreaterOrEqual(around, 4, "several decoy chairs around the dining table");
            List<RoomSide> doorway = l.SidesOf(l.Doors.Find(d => l.SidesOf(d, out _).Count == 2), out float along);
            bool besideDoorway = l.Decoys.Exists(d => Mathf.Abs(d.X - doorway[0].Line) < 0.5f && Mathf.Abs(d.Z - along) < 1.2f);
            Assert.IsTrue(besideDoorway, "a decoy stands against the shared wall beside the doorway, hidden from the other room");
            Assert.AreEqual(l.Decoys.Count + 1, l.Census()["chair"]);
        }
    }
}
