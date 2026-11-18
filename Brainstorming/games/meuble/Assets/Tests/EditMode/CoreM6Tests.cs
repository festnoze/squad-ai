using System.Collections.Generic;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M6 gameplay, pure logic (docs/CONTRACT_M6.md 2.5 and 2.6): the door memory, the wardrobe fit and entry rules, and the
    /// remembered spot seen empty.
    /// </summary>
    public sealed class CoreM6Tests
    {
        private const float Dt = Tuning.FixedStep;

        // ----- DoorMemory (2.6) -----

        [Test]
        public void DoorMemory_remembers_the_authored_leaves_and_a_mismatch_is_one_suspect()
        {
            var memory = new DoorMemory(new List<bool> { false, true });
            Assert.AreEqual(2, memory.Count);
            Assert.IsFalse(memory.RemembersOpen(0), "leaf 0 is authored closed");
            Assert.IsTrue(memory.RemembersOpen(1), "leaf 1 is authored open");

            Assert.AreEqual(DoorSighting.NotSeen, memory.Observe(0, false, true), "an unseen leaf is not seen");
            Assert.IsFalse(memory.Noticed(0), "an unseen mismatch is not noticed");
            Assert.AreEqual(DoorSighting.Confirmed, memory.Observe(0, true, false), "seen as remembered");
            Assert.AreEqual(DoorSighting.Confirmed, memory.Observe(1, true, true), "seen as remembered (open)");

            Assert.IsTrue(memory.Differs(0, true), "premise: open differs from the memory of leaf 0");
            Assert.AreEqual(DoorSighting.Suspect, memory.Observe(0, true, true), "the first sighting of a mismatch is a Suspect");
            Assert.IsTrue(memory.Noticed(0));
            Assert.AreEqual(DoorSighting.Known, memory.Observe(0, true, true), "a mismatch already noticed gives no new Suspect");
            Assert.AreEqual(DoorSighting.Known, memory.Observe(0, true, true));
            Assert.IsFalse(memory.RemembersOpen(0), "seeing a mismatch never changes the memory");

            memory.Remember(0, false);
            Assert.IsFalse(memory.Noticed(0), "a put back clears the notice");
            Assert.AreEqual(DoorSighting.Confirmed, memory.Observe(0, true, false));
            Assert.AreEqual(DoorSighting.Suspect, memory.Observe(0, true, true), "a new change is a new Suspect");

            memory.Remember(0, true);
            Assert.IsTrue(memory.RemembersOpen(0), "a door the household opened is remembered open");
            Assert.AreEqual(DoorSighting.Confirmed, memory.Observe(0, true, true));
            Assert.AreEqual(DoorSighting.NotSeen, memory.Observe(5, true, true), "out of range is never seen");
        }

        // ----- The wardrobe (2.5) -----

        private static PropDef Wardrobe(float x, float z, float yaw)
        {
            return new PropDef
            {
                Name = "Armoire", Kind = WardrobeRule.Kind, X = x, Z = z, Yaw = yaw,
                SizeX = Tuning.WardrobeSizeX, SizeY = Tuning.WardrobeSizeY, SizeZ = Tuning.WardrobeSizeZ,
            };
        }

        [Test]
        public void Wardrobe_fits_the_stool_and_the_floor_lamp_only()
        {
            Assert.IsTrue(WardrobeRule.Fits(BodyDef.For(BodyKinds.Stool).Size, 0f), "the stool fits");
            Assert.IsTrue(WardrobeRule.Fits(BodyDef.For(BodyKinds.FloorLamp).Size, 0f), "the floor lamp fits");
            Assert.IsTrue(WardrobeRule.Fits(BodyDef.For(BodyKinds.Stool).Size, Tuning.LoadHeight), "the stool with a load fits");
            Assert.IsFalse(WardrobeRule.Fits(BodyDef.For(BodyKinds.Chair).Size, 0f), "the chair does not fit");
            Assert.IsFalse(WardrobeRule.Fits(BodyDef.For(BodyKinds.OfficeChair).Size, 0f), "the office chair does not fit");
            Assert.IsFalse(WardrobeRule.Fits(BodyDef.For(BodyKinds.Armchair).Size, 0f), "the armchair does not fit");
            Assert.IsFalse(WardrobeRule.Fits(BodyDef.For(BodyKinds.RockingChair).Size, 0f), "the rocking chair does not fit");
            Assert.IsFalse(WardrobeRule.Fits(new Vector3(0.35f, 1.7f, 0.35f), 0.25f), "too tall with its load");
        }

        [Test]
        public void Wardrobe_entry_zone_is_the_strip_in_front_of_its_front_face()
        {
            // Yaw 180: the front faces -z; the front face lies at z = 3.65 - 0.3 = 3.35.
            PropDef w = Wardrobe(0f, 3.65f, 180f);
            Vector3 front = WardrobeRule.Front(w);
            Assert.AreEqual(0f, front.x, 1e-5f);
            Assert.AreEqual(-1f, front.z, 1e-5f, "the front is local +z, YawMath.Forward(yaw)");
            Assert.IsTrue(WardrobeRule.InFront(w, new Vector3(0f, 0f, 2.95f)), "0.4 m in front, centred");
            Assert.IsTrue(WardrobeRule.InFront(w, new Vector3(0.49f, 0f, 2.80f)), "0.55 m in front, near the side");
            Assert.IsFalse(WardrobeRule.InFront(w, new Vector3(0f, 0f, 2.70f)), "0.65 m in front is too far");
            Assert.IsFalse(WardrobeRule.InFront(w, new Vector3(0.6f, 0f, 3.0f)), "beside the front, not in front of it");
            Assert.IsFalse(WardrobeRule.InFront(w, new Vector3(0f, 0f, 4.2f)), "behind the wardrobe");
            Assert.IsTrue(WardrobeRule.CanEnter(w, new Vector3(0f, 0f, 2.95f), BodyDef.For(BodyKinds.Stool).Size, 0f));
            Assert.IsFalse(WardrobeRule.CanEnter(w, new Vector3(0f, 0f, 2.95f), BodyDef.For(BodyKinds.Chair).Size, 0f), "a chair never enters");
            Vector3 entry = WardrobeRule.EntryCenter(w);
            Assert.AreEqual(3.35f - Tuning.WardrobeReach * 0.5f, entry.z, 1e-4f);
        }

        // ----- The remembered spot seen empty (2.5) -----

        [Test]
        public void Empty_spot_is_a_suspect_then_one_discovery_until_the_furniture_is_seen()
        {
            var spawn = new FurniturePose(new Vector3(1f, 0f, 1f), 0f);
            var memory = new FurnitureMemory(spawn, null, null, BodyKinds.Stool);
            int graceSteps = Mathf.RoundToInt(Tuning.DiscoveryGrace / Dt);
            Assert.AreEqual(Observation.NotSeen, memory.ObserveEmptySpot(false, Dt), "a spot not seen is nothing");
            for (int k = 1; k < graceSteps; k++)
            {
                Assert.AreEqual(Observation.Suspect, memory.ObserveEmptySpot(true, Dt), $"step {k} of the grace is a Suspect");
            }
            Assert.AreEqual(Observation.Discovery, memory.ObserveEmptySpot(true, Dt), "the empty spot is a discovery after the grace");
            Assert.IsTrue(memory.SpotKnownEmpty);
            for (int k = 0; k < 3 * graceSteps; k++)
            {
                Assert.AreEqual(Observation.NotSeen, memory.ObserveEmptySpot(true, Dt), "a spot known empty gives nothing more");
            }
            // The furniture seen again (in place) ends it; hidden again, the spot gives a new discovery.
            Assert.AreEqual(Observation.Confirmed, memory.Observe(true, spawn, Dt));
            Assert.IsFalse(memory.SpotKnownEmpty, "seen again, the spot is no longer known empty");
            Observation last = Observation.NotSeen;
            for (int k = 0; k < graceSteps; k++)
            {
                last = memory.ObserveEmptySpot(true, Dt);
            }
            Assert.AreEqual(Observation.Discovery, last, "a new hiding seen gives a new discovery");
            // A glimpse shorter than the grace, then unseen: no discovery (the grace measures an unbroken sighting).
            memory.SetPlayerSlot(spawn);
            Assert.AreEqual(Observation.Suspect, memory.ObserveEmptySpot(true, Dt));
            Assert.AreEqual(Observation.NotSeen, memory.ObserveEmptySpot(false, Dt));
            Assert.AreEqual(Observation.Suspect, memory.ObserveEmptySpot(true, Dt), "the grace restarted");
        }
    }
}
