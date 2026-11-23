using System.Collections.Generic;
using NUnit.Framework;
using OutOfSight.Core;
using S = OutOfSight.Core.HumanProfile.Step;

namespace OutOfSight.Tests
{
    /// <summary>
    /// HUMANAUDIT (docs/next/progress/HUMANAUDIT.md): the rules of the level audit's optional "human" profile, as
    /// <see cref="HumanProfile"/> states them (the audit's search applies them and checks its own schedule with
    /// <see cref="HumanProfile.Breaches"/>): the "-profile" values, the reaction to a door an inhabitant opened, and the
    /// breaches (a still run under one second, a one-cell dash that stops or freezes, two toggles in a row).
    /// </summary>
    public sealed class HumanProfileTests
    {
        private const int Pause = 10; // 1.0 s at 0.1 s samples

        private static List<HumanProfile.Breach> Check(S[] steps, int[] samples)
        {
            return HumanProfile.Breaches(steps, samples, Pause, HumanProfile.MinMoveCells);
        }

        [Test]
        public void Constants_AreTheDocumentedProfile()
        {
            Assert.AreEqual(0.3f, HumanProfile.ReactionTime, 1e-6f);
            Assert.AreEqual(1.0f, HumanProfile.MinPause, 1e-6f);
            Assert.AreEqual(2, HumanProfile.MinMoveCells, "the audit's search tracks the dash with one bit: it supports exactly 2");
            Assert.AreEqual(3, HumanProfile.Samples(HumanProfile.ReactionTime, 0.1f));
            Assert.AreEqual(Pause, HumanProfile.Samples(HumanProfile.MinPause, 0.1f));
        }

        [Test]
        public void TryParse_StrictByDefault_HumanOnRequest_RejectsTheRest()
        {
            Assert.IsTrue(HumanProfile.TryParse(null, out bool human));
            Assert.IsFalse(human);
            Assert.IsTrue(HumanProfile.TryParse("strict", out human));
            Assert.IsFalse(human);
            Assert.IsTrue(HumanProfile.TryParse("human", out human));
            Assert.IsTrue(human);
            Assert.IsTrue(HumanProfile.TryParse("HUMAN", out human));
            Assert.IsTrue(human);
            Assert.IsFalse(HumanProfile.TryParse("humain", out human));
            Assert.IsFalse(human);
        }

        [Test]
        public void ReactionMask_HidesALeafOpenedWithinTheReactionTime()
        {
            // Leaf bit 2 opens at sample 10, leaf bit 1 is the player's own (never in autoOpen).
            var autoOpen = new int[20];
            for (int s = 10; s < autoOpen.Length; s++)
            {
                autoOpen[s] = 2;
            }
            const int mask = 3;
            Assert.AreEqual(3, HumanProfile.ReactionMask(mask, autoOpen, 9, 3), "before it opens, nothing to hide");
            Assert.AreEqual(1, HumanProfile.ReactionMask(mask, autoOpen, 10, 3), "just opened: not reacted to yet");
            Assert.AreEqual(1, HumanProfile.ReactionMask(mask, autoOpen, 12, 3), "0.2 s after: not yet");
            Assert.AreEqual(3, HumanProfile.ReactionMask(mask, autoOpen, 13, 3), "0.3 s after: the human goes");
            Assert.AreEqual(3, HumanProfile.ReactionMask(mask, null, 10, 3), "no inhabitant door: unchanged");
            Assert.AreEqual(3, HumanProfile.ReactionMask(mask, autoOpen, 10, 0), "no reaction time: unchanged");
        }

        [Test]
        public void Breaches_HumanScheduleHasNone()
        {
            // Spawn freeze 1.2 s, two cells, freeze 1.0 s, three cells, toggle, freeze 2 s, toggle, a cell and an opening,
            // two cells into the exit.
            var steps = new[] { S.Still, S.Move, S.Move, S.Still, S.Move, S.Move, S.Move, S.Toggle, S.Still, S.Toggle, S.Move, S.Action, S.Move, S.Move };
            var samples = new[] { 12, 4, 4, 10, 4, 4, 4, 2, 20, 2, 4, 6, 4, 4 };
            CollectionAssert.IsEmpty(Check(steps, samples));
        }

        [Test]
        public void Breaches_SubSecondFreeze()
        {
            var steps = new[] { S.Still, S.Move, S.Move, S.Still, S.Still, S.Move, S.Move };
            var samples = new[] { 10, 4, 4, 5, 4, 4, 4 };
            List<HumanProfile.Breach> found = Check(steps, samples);
            Assert.AreEqual(1, found.Count);
            Assert.AreEqual("freeze", found[0].Kind);
            Assert.AreEqual(9, found[0].Length, "the still run is summed over its steps");
            Assert.AreEqual(4, found[0].Index, "the breach names the last step of the run");
        }

        [Test]
        public void Breaches_OneCellDashThatFreezesOrStops()
        {
            var freezes = Check(new[] { S.Still, S.Move, S.Still, S.Move, S.Move }, new[] { 10, 4, 10, 4, 4 });
            Assert.AreEqual(1, freezes.Count);
            Assert.AreEqual("dash", freezes[0].Kind);
            Assert.AreEqual(1, freezes[0].Length);

            var stops = Check(new[] { S.Move, S.Stop, S.Move, S.Move }, new[] { 4, 2, 4, 4 });
            Assert.AreEqual(1, stops.Count, "a glide stop after one cell is a dash too");
            Assert.AreEqual("dash", stops[0].Kind);
        }

        [Test]
        public void Breaches_OneCellBeforeAnActionOrIntoTheExitIsFine()
        {
            CollectionAssert.IsEmpty(Check(new[] { S.Still, S.Move, S.Action, S.Move, S.Move }, new[] { 10, 4, 6, 4, 4 }),
                "one cell to a door, then open it: human");
            CollectionAssert.IsEmpty(Check(new[] { S.Still, S.Move }, new[] { 10, 4 }), "one cell into the exit: human");
        }

        [Test]
        public void Breaches_BackToBackToggles()
        {
            List<HumanProfile.Breach> found = Check(new[] { S.Still, S.Toggle, S.Toggle, S.Move, S.Move }, new[] { 10, 2, 2, 4, 4 });
            Assert.AreEqual(1, found.Count);
            Assert.AreEqual("flicker", found[0].Kind);
            Assert.AreEqual(2, found[0].Index);
        }

        [Test]
        public void Breaches_RejectsMismatchedInput()
        {
            Assert.Throws<System.ArgumentException>(() => HumanProfile.Breaches(new[] { S.Move }, new int[0], Pause, 2));
        }
    }
}
