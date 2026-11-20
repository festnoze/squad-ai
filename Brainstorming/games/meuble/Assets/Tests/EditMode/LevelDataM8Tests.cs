using System.IO;
using System.Linq;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M8 room objects (docs/m8/ROOMS_PLAN.md 3), level data: the ten kinds are known prop kinds with a drawn size, every
    /// kind of the shipped levels and fixtures is known, an unknown kind is rejected, and the throwaway test_rooms level
    /// (every M8 kind) validates without being in the play order.
    /// </summary>
    public sealed class LevelDataM8Tests
    {
        private const string Folder = "Assets/Resources/Levels/";

        private static LevelDef Load(string id) => LevelJson.Parse(File.ReadAllText(Folder + id + ".json"));

        [Test]
        public void The_ten_room_objects_are_known_kinds_with_a_drawn_size()
        {
            CollectionAssert.AreEqual(new[]
            {
                "bathtub", "washbasin", "toilet", "kitchen_sink", "stove", "fridge", "coffee_table", "tv_unit", "bed", "nightstand",
            }, PropKinds.RoomObjects, "the kind ids of ROOMS_PLAN 3, as written");
            foreach (string kind in PropKinds.RoomObjects)
            {
                Assert.IsTrue(PropKinds.IsKnown(kind), kind);
                Vector3 size = PropKinds.DefaultSize(kind);
                Assert.IsTrue(size.x > 0f && size.y > 0f && size.z > 0f, kind + ": no default size");
            }
            Assert.AreEqual(new Vector3(1.6f, 0.55f, 2.0f), PropKinds.DefaultSize(PropKinds.Bed), "the bed is drawn for the M2 'Lit' sofa box");
            Assert.AreEqual(Vector3.zero, PropKinds.DefaultSize(PropKinds.Sofa), "an M2 kind has no M8 default size");
            Assert.IsTrue(PropKinds.IsKnown(null) && PropKinds.IsKnown(""), "no kind is the M1 plain box");
            Assert.IsFalse(PropKinds.IsKnown("kitchensink"));
        }

        [Test]
        public void Every_shipped_prop_kind_is_known()
        {
            foreach (string path in Directory.GetFiles(Folder, "*.json"))
            {
                if (Path.GetFileNameWithoutExtension(path) == LevelManifest.FileName)
                {
                    continue;
                }
                LevelDef level = LevelJson.Parse(File.ReadAllText(path));
                foreach (PropDef prop in level.Props)
                {
                    Assert.IsTrue(PropKinds.IsKnown(prop.Kind), $"{Path.GetFileName(path)}: prop {prop.Name} kind '{prop.Kind}'");
                }
            }
        }

        [Test]
        public void An_unknown_prop_kind_is_rejected_and_test_rooms_validates()
        {
            LevelDef rooms = Load("test_rooms");
            Assert.IsEmpty(LevelValidator.Validate(rooms), "test_rooms");
            CollectionAssert.IsSubsetOf(PropKinds.RoomObjects, rooms.Props.Select(p => p.Kind).ToList(), "premise: test_rooms has every M8 kind");
            Assert.IsFalse(LevelManifest.Parse(File.ReadAllText(Folder + LevelManifest.FileName + ".json")).Contains("test_rooms"),
                "test_rooms is a throwaway level, never in the play order");

            rooms.Props.First(p => p.Kind == PropKinds.Stove).Kind = "cooker";
            Assert.IsTrue(LevelValidator.Validate(rooms).Any(i => i.Contains("kind 'cooker' is not a prop kind")), "a typo is caught");
        }
    }
}
