using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using OutOfSight.Core;

namespace OutOfSight.Tests
{
    /// <summary>
    /// DOORS (docs/next/progress/DOORS.md): LevelValidator.DoorwayIssues, no prop or decoy in the approach area of a door
    /// (the opening's width, <see cref="LevelValidator.DoorApproachDepth"/> deep into each room), and every shipped level
    /// file held to it.
    /// </summary>
    public sealed class DoorwayTests
    {
        private const string Folder = "Assets/Resources/Levels/";

        /// <summary>
        /// Levels another agent was reworking when the rule landed, each with a known offender. The test fails as soon as one
        /// of them is clear, so the entry is removed then and the list cannot rot.
        /// </summary>
        private static readonly string[] Pending = { };

        /// <summary>Room a: x in [-4, 0]. Room b: x in [0.1, 4.1]. Both z in [-2, 2]. A 1 m doorway at (0.05, 0).</summary>
        private static LevelDef TwoRooms()
        {
            return new LevelDef
            {
                Id = "doorway",
                Rooms = new List<RoomDef>
                {
                    new RoomDef { Id = "a", X = -2f, Z = 0f, SizeX = 4f, SizeZ = 4f, WallHeight = 2.7f, WallThickness = 0.1f },
                    new RoomDef { Id = "b", X = 2.1f, Z = 0f, SizeX = 4f, SizeZ = 4f, WallHeight = 2.7f, WallThickness = 0.1f },
                },
                Doors = new List<OpeningDef> { new OpeningDef { X = 0.05f, Z = 0f, Width = 1f, Top = 2.1f } },
            };
        }

        private static PropDef Sofa(float x, float z, float sizeX, float sizeZ, float yaw = 0f)
        {
            return new PropDef { Name = "Sofa", Kind = "sofa", X = x, Z = z, SizeX = sizeX, SizeY = 0.8f, SizeZ = sizeZ, Yaw = yaw };
        }

        [Test]
        public void A_sofa_in_front_of_the_doorway_is_reported()
        {
            LevelDef l = TwoRooms();
            l.Props.Add(Sofa(-0.6f, 0.3f, 1.6f, 0.6f, 90f)); // x from -0.9 to -0.3, 0.3 m off the wall face
            List<string> issues = LevelValidator.DoorwayIssues(l);
            Assert.AreEqual(1, issues.Count, string.Join(" | ", issues));
            StringAssert.Contains("door 1 approach in room a", issues[0]);
            StringAssert.Contains("prop Sofa", issues[0]);
        }

        [Test]
        public void A_decoy_in_front_of_the_doorway_is_reported()
        {
            LevelDef l = TwoRooms();
            l.Decoys.Add(new DecoyDef { Kind = "chair", X = 0.6f, Z = 0.2f });
            List<string> issues = LevelValidator.DoorwayIssues(l);
            Assert.AreEqual(1, issues.Count, string.Join(" | ", issues));
            StringAssert.Contains("door 1 approach in room b", issues[0]);
            StringAssert.Contains("decoy 1", issues[0]);
        }

        [Test]
        public void Furniture_beside_or_beyond_the_approach_is_clear()
        {
            LevelDef l = TwoRooms();
            l.Props.Add(Sofa(-0.5f, 1.0f, 0.6f, 1.0f));   // beside the opening: z from 0.5, the jamb, touching
            l.Props.Add(Sofa(-1.4f, 0f, 0.8f, 1.2f));    // beyond it: x up to -1.0, 1 m from the wall face, touching
            l.Props.Add(Sofa(1.6f, -1.5f, 1.0f, 0.6f));  // elsewhere in room b
            Assert.IsEmpty(LevelValidator.DoorwayIssues(l));
        }

        [Test]
        public void Every_level_file_keeps_its_doors_clear()
        {
            var failures = new List<string>();
            var files = new List<string>(Directory.GetFiles(Folder, "level*.json")) { Folder + "title_house.json" };
            foreach (string file in files)
            {
                string id = Path.GetFileNameWithoutExtension(file);
                if (id == "levels")
                {
                    continue;
                }
                List<string> issues = LevelValidator.DoorwayIssues(LevelJson.Parse(File.ReadAllText(file)));
                bool pending = System.Array.IndexOf(Pending, id) >= 0;
                if (pending && issues.Count == 0)
                {
                    failures.Add($"{id} is now clear: remove it from DoorwayTests.Pending");
                }
                else if (!pending && issues.Count > 0)
                {
                    failures.Add(id + ": " + string.Join("; ", issues));
                }
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }
    }
}
