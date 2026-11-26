using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// PLANTS2 (docs/next/progress/PLANTS2.md): a potted plant always stands close to a corner of its room, or at the end of
    /// a corridor, and never in a bathroom. Every level*.json and title_house.json is held to it.
    /// <para>Thresholds (the same as the PLANTS2 check script):</para>
    /// <list type="bullet">
    /// <item><see cref="NearWall"/>: the gap between the plant's footprint and the inner wall face, on an axis, is at most
    /// 0.35 m. A corner is near on both axes.</item>
    /// <item><see cref="CorridorRatio"/>: a room at least 2.5 times longer than it is wide is a corridor; a plant near the
    /// end wall (the long axis) stands at the corridor's end, whatever its gap to the side walls.</item>
    /// <item>A bathroom is a room whose id names one (sdb, bain, bath, wc, toilet, so "salle de bain" too) or a room that
    /// holds a bathroom fixture (bathtub, washbasin, toilet, shower): level14 calls its bathroom "salle".</item>
    /// </list>
    /// </summary>
    public sealed class PlantPlacementTests
    {
        private const string Folder = "Assets/Resources/Levels/";

        /// <summary>Largest gap, in metres, between the plant's footprint and a wall face for the plant to count as near it.</summary>
        public const float NearWall = 0.35f;

        /// <summary>A room whose long side is at least this many times its short side is a corridor.</summary>
        public const float CorridorRatio = 2.5f;

        private static readonly string[] BathroomIds = { "sdb", "bain", "bath", "wc", "toilet" };
        private static readonly string[] BathroomFixtures = { "bathtub", "washbasin", "toilet", "shower" };

        private static RoomDef RoomOf(LevelDef level, float x, float z)
        {
            foreach (RoomDef r in level.AllRooms())
            {
                if (Mathf.Abs(x - r.X) <= r.SizeX * 0.5f + 1e-4f && Mathf.Abs(z - r.Z) <= r.SizeZ * 0.5f + 1e-4f)
                {
                    return r;
                }
            }
            return null;
        }

        private static bool IsBathroom(LevelDef level, RoomDef room)
        {
            string id = (room.Id ?? "").ToLowerInvariant();
            foreach (string b in BathroomIds)
            {
                if (id.Contains(b))
                {
                    return true;
                }
            }
            foreach (PropDef p in level.Props)
            {
                if (p != null && System.Array.IndexOf(BathroomFixtures, p.Kind) >= 0 && RoomOf(level, p.X, p.Z) == room)
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>Empty when the plant is placed by the rule, else why not.</summary>
        public static string PlantIssue(LevelDef level, PropDef plant)
        {
            RoomDef r = RoomOf(level, plant.X, plant.Z);
            if (r == null)
            {
                return $"plant {plant.Name} at ({plant.X}, {plant.Z}) stands outside every room";
            }
            if (IsBathroom(level, r))
            {
                return $"plant {plant.Name} stands in the bathroom {r.Id}";
            }
            bool turned = Mathf.Abs(Mathf.DeltaAngle(plant.Yaw, 90f)) < 1f || Mathf.Abs(Mathf.DeltaAngle(plant.Yaw, 270f)) < 1f;
            float hx = (turned ? plant.SizeZ : plant.SizeX) * 0.5f;
            float hz = (turned ? plant.SizeX : plant.SizeZ) * 0.5f;
            float t = r.WallThickness * 0.5f;
            float gx = Mathf.Min(plant.X - hx - (r.X - r.SizeX * 0.5f + t), r.X + r.SizeX * 0.5f - t - (plant.X + hx));
            float gz = Mathf.Min(plant.Z - hz - (r.Z - r.SizeZ * 0.5f + t), r.Z + r.SizeZ * 0.5f - t - (plant.Z + hz));
            bool nearX = gx <= NearWall + 1e-3f;
            bool nearZ = gz <= NearWall + 1e-3f;
            bool longX = r.SizeX >= CorridorRatio * r.SizeZ;
            bool longZ = r.SizeZ >= CorridorRatio * r.SizeX;
            if ((nearX && nearZ) || (longX && nearX) || (longZ && nearZ))
            {
                return "";
            }
            return $"plant {plant.Name} at ({plant.X}, {plant.Z}) in {r.Id} is {gx:0.00} m / {gz:0.00} m from the walls: "
                + $"move it to a corner (both gaps at most {NearWall} m) or to a corridor end";
        }

        private static LevelDef Room(string id)
        {
            return new LevelDef
            {
                Id = "plants",
                Rooms = new List<RoomDef>
                {
                    new RoomDef { Id = id, X = 0f, Z = 0f, SizeX = 4f, SizeZ = 4f, WallHeight = 2.7f, WallThickness = 0.1f },
                    new RoomDef { Id = "couloir", X = 0f, Z = 2.75f, SizeX = 4f, SizeZ = 1.4f, WallHeight = 2.7f, WallThickness = 0.1f },
                },
            };
        }

        private static PropDef Plant(float x, float z)
        {
            return new PropDef { Name = "Plante", Kind = "plant", X = x, Z = z, SizeX = 0.5f, SizeY = 1.3f, SizeZ = 0.5f };
        }

        [Test]
        public void A_plant_in_a_corner_or_at_a_corridor_end_is_clear()
        {
            LevelDef l = Room("salon");
            Assert.AreEqual("", PlantIssue(l, Plant(-1.6f, -1.6f)));   // gaps 0.1 / 0.1
            Assert.AreEqual("", PlantIssue(l, Plant(1.4f, 1.4f)));     // gaps 0.3 / 0.3
            Assert.AreEqual("", PlantIssue(l, Plant(1.6f, 2.75f)));    // corridor end, mid-width
        }

        [Test]
        public void A_plant_off_the_corner_is_reported()
        {
            LevelDef l = Room("salon");
            StringAssert.Contains("from the walls", PlantIssue(l, Plant(0f, 0f)));
            StringAssert.Contains("from the walls", PlantIssue(l, Plant(-1.6f, 0.5f)));   // along one wall only
            StringAssert.Contains("from the walls", PlantIssue(l, Plant(0f, 2.75f)));     // middle of the corridor
        }

        [Test]
        public void A_plant_in_a_bathroom_is_reported()
        {
            StringAssert.Contains("bathroom", PlantIssue(Room("salle de bain"), Plant(-1.6f, -1.6f)));
            StringAssert.Contains("bathroom", PlantIssue(Room("sdb"), Plant(-1.6f, -1.6f)));
            LevelDef l = Room("salle");
            l.Props.Add(new PropDef { Name = "Baignoire", Kind = "bathtub", X = 1f, Z = -1f, SizeX = 1.7f, SizeY = 0.6f, SizeZ = 0.75f });
            StringAssert.Contains("bathroom", PlantIssue(l, Plant(-1.6f, -1.6f)));
        }

        [Test]
        public void Every_level_file_keeps_its_plants_in_corners()
        {
            var failures = new List<string>();
            var files = new List<string>(Directory.GetFiles(Folder, "level*.json")) { Folder + "title_house.json" };
            int plants = 0;
            foreach (string file in files)
            {
                string id = Path.GetFileNameWithoutExtension(file);
                if (id == "levels")
                {
                    continue;
                }
                LevelDef level = LevelJson.Parse(File.ReadAllText(file));
                foreach (PropDef p in level.Props)
                {
                    if (p == null || p.Kind != "plant")
                    {
                        continue;
                    }
                    plants++;
                    string issue = PlantIssue(level, p);
                    if (issue.Length > 0)
                    {
                        failures.Add(id + ": " + issue);
                    }
                }
            }
            Assert.Greater(plants, 0, "no plant found: the level folder or the plant kind moved");
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }

        /// <summary>Every played level holds at least this many plants (existing ones included).</summary>
        public const int MinPerLevel = 3;

        /// <summary>No room holds more than this many plants.</summary>
        public const int MaxPerRoom = 2;

        /// <summary>
        /// Played levels that cannot reach <see cref="MinPerLevel"/>, with the count they must keep. The test fails as soon
        /// as one of them reaches the minimum, so the entry is removed then and the list cannot rot.
        /// <list type="bullet">
        /// <item>level1, level5, level7: a single room, so <see cref="MaxPerRoom"/> caps them at 2.</item>
        /// <item>level18: four tiny rooms; every other corner is a doorway approach or a door leaf sweep, the bed, the
        /// buffet, the counter, the spawn, the exit mat or Odile's station.</item>
        /// <item>level15: no plant at all. The first plant brings two new materials (Colour Foliage, Colour Soil) and the
        /// level then has 25, over the audit's budget of 24.</item>
        /// <item>level25: 2 plants. Each plant costs 3 draw-call slots and a third one takes the level to 123, over the
        /// audit's budget of 120.</item>
        /// <item>level34, level35 (MAZES): the maze levels have no furniture at all, plants included (the product owner's
        /// request: nothing to hide behind).</item>
        /// </list>
        /// </summary>
        private static readonly Dictionary<string, int> Fewer = new Dictionary<string, int>
        {
            { "level1", 2 }, { "level5", 2 }, { "level7", 2 }, { "level18", 1 }, { "level15", 0 }, { "level25", 2 },
            { "level34", 0 }, { "level35", 0 },
        };

        [Test]
        public void Every_played_level_has_enough_plants_and_no_room_too_many()
        {
            var failures = new List<string>();
            foreach (string id in LevelManifest.Parse(File.ReadAllText(Folder + "levels.json")))
            {
                LevelDef level = LevelJson.Parse(File.ReadAllText(Folder + id + ".json"));
                var perRoom = new Dictionary<string, int>();
                int count = 0;
                foreach (PropDef p in level.Props)
                {
                    if (p == null || p.Kind != "plant")
                    {
                        continue;
                    }
                    count++;
                    RoomDef r = RoomOf(level, p.X, p.Z);
                    string key = r?.Id ?? "?";
                    perRoom[key] = perRoom.TryGetValue(key, out int n) ? n + 1 : 1;
                }
                foreach (KeyValuePair<string, int> kv in perRoom)
                {
                    if (kv.Value > MaxPerRoom)
                    {
                        failures.Add($"{id}: {kv.Value} plants in room {kv.Key}, at most {MaxPerRoom}");
                    }
                }
                if (Fewer.TryGetValue(id, out int min))
                {
                    if (count >= MinPerLevel)
                    {
                        failures.Add($"{id} now has {count} plants: remove it from PlantPlacementTests.Fewer");
                    }
                    else if (count < min)
                    {
                        failures.Add($"{id}: {count} plants, its exception keeps at least {min}");
                    }
                }
                else if (count < MinPerLevel)
                {
                    failures.Add($"{id}: {count} plants, at least {MinPerLevel} in a played level");
                }
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }
    }
}
