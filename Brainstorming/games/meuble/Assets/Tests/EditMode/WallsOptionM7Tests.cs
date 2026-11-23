using NUnit.Framework;
using OutOfSight.Core;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M7 walls pass (product owner, 2026-11-19): the Walls option ("lowered", "seethrough", "both", "none") and the wall
    /// opacity option (10, 20, 35, 50 %): defaults for a new save and for an old one without the fields (both, 10 % since
    /// the product owner's 2026-11-20 request; lowered at 20 % before), a save that stores the old defaults keeping them,
    /// the fallbacks of a hand edited value (the OPTIONS_WALLS_FALLBACK mutation), the cycles of the two Options rows, a
    /// round trip through the JSON and through SaveStore, and the look the wall fader reads from it at once.
    /// </summary>
    public sealed class WallsOptionM7Tests
    {
        [SetUp]
        public void SetUp()
        {
            SaveStore.ResetForTests();
            WallFader.LookOverride = null;
            WallFader.OpacityOverride = null;
        }

        [TearDown]
        public void TearDown()
        {
            SaveStore.ResetForTests();
        }

        [Test]
        public void Default_IsBothAt10Percent()
        {
            SaveOptions o = SaveOptions.Default();
            Assert.AreEqual(SaveOptions.WallsBoth, o.Walls);
            Assert.AreEqual(10, o.WallOpacity);
            Assert.AreEqual(10, Tuning.WallOpacityDefault, "the documented default");
            Assert.IsTrue(o.WallOpacityApplies, "both uses the opacity");
            string json = new SaveData().ToJson();
            StringAssert.Contains("\"walls\": \"both\"", json, "a new save writes the default look");
            StringAssert.Contains("\"wallOpacity\": 10", json, "a new save writes the default opacity");
        }

        [Test]
        public void OldSaveWithoutTheFields_LoadsBothAt10Percent()
        {
            string json = "{ \"version\": 1, \"won\": [], \"best\": {}, \"options\": { \"sensitivity\": 1.5, \"volume\": 30, \"cone\": \"never\" } }";
            SaveData data = SaveData.Parse(json, out string problem);
            Assert.IsNotNull(data, problem);
            Assert.AreEqual(SaveOptions.WallsBoth, data.Options.Walls);
            Assert.AreEqual(10, data.Options.WallOpacity);
            Assert.AreEqual(30, data.Options.Volume, "the other options are kept");
            SaveData old = SaveData.Parse("{ \"version\": 1 }", out problem);
            Assert.IsNotNull(old, problem);
            Assert.AreEqual(SaveOptions.WallsBoth, old.Options.Walls);
            Assert.AreEqual(10, old.Options.WallOpacity);
        }

        [Test]
        public void SavedLook_IsKeptWhenItIsNotTheDefault()
        {
            // The "walls" and "wallOpacity" keys are always written: a save holding the old defaults (lowered at 20 %) chose
            // them, so the new default does not override them.
            SaveData data = SaveData.Parse("{ \"version\": 1, \"options\": { \"walls\": \"lowered\", \"wallOpacity\": 20 } }", out string problem);
            Assert.IsNotNull(data, problem);
            Assert.AreEqual(SaveOptions.WallsLowered, data.Options.Walls);
            Assert.AreEqual(20, data.Options.WallOpacity);
            SaveData none = SaveData.Parse("{ \"version\": 1, \"options\": { \"walls\": \"none\" } }", out problem);
            Assert.IsNotNull(none, problem);
            Assert.AreEqual(SaveOptions.WallsNone, none.Options.Walls);
            Assert.AreEqual(10, none.Options.WallOpacity, "a missing opacity is the default");
            SaveData opacityOnly = SaveData.Parse("{ \"version\": 1, \"options\": { \"wallOpacity\": 50 } }", out problem);
            Assert.IsNotNull(opacityOnly, problem);
            Assert.AreEqual(SaveOptions.WallsBoth, opacityOnly.Options.Walls, "a missing look is the default");
            Assert.AreEqual(50, opacityOnly.Options.WallOpacity);
        }

        [Test]
        public void HandEditedValues_FallBackToBothAndTheNearestStep()
        {
            SaveData data = SaveData.Parse("{ \"version\": 1, \"options\": { \"walls\": \"glass\", \"wallOpacity\": 33 } }", out string problem);
            Assert.IsNotNull(data, problem);
            Assert.AreEqual(SaveOptions.WallsBoth, data.Options.Walls, "an unknown look is the default, both");
            Assert.AreEqual(35, data.Options.WallOpacity, "33 % goes to the nearest step, 35 %");
            foreach (string walls in new[] { SaveOptions.WallsLowered, SaveOptions.WallsSeeThrough, SaveOptions.WallsBoth, SaveOptions.WallsNone })
            {
                Assert.AreEqual(walls, new SaveOptions { Walls = walls }.Clamped().Walls, walls + " is kept");
            }
            Assert.AreEqual(10, new SaveOptions { WallOpacity = -40 }.Clamped().WallOpacity);
            Assert.AreEqual(50, new SaveOptions { WallOpacity = 400 }.Clamped().WallOpacity);
            SaveData wrongType = SaveData.Parse("{ \"version\": 1, \"options\": { \"walls\": 3, \"wallOpacity\": \"dim\" } }", out problem);
            Assert.IsNotNull(wrongType, problem);
            Assert.AreEqual(SaveOptions.WallsBoth, wrongType.Options.Walls);
            Assert.AreEqual(10, wrongType.Options.WallOpacity);
        }

        [Test]
        public void Rows_CycleEveryLookAndEveryOpacity()
        {
            string walls = SaveOptions.WallsLowered;
            var seen = new System.Collections.Generic.List<string> { walls };
            for (int i = 0; i < 3; i++)
            {
                walls = SaveOptions.NextWalls(walls);
                seen.Add(walls);
            }
            CollectionAssert.AreEqual(new[] { SaveOptions.WallsLowered, SaveOptions.WallsSeeThrough, SaveOptions.WallsBoth, SaveOptions.WallsNone }, seen);
            Assert.AreEqual(SaveOptions.WallsLowered, SaveOptions.NextWalls(walls), "after Off comes Lowered again");
            Assert.AreEqual(20, SaveOptions.NextWallOpacity(10), "after the default 10 % comes 20 %");
            Assert.AreEqual(35, SaveOptions.NextWallOpacity(20));
            Assert.AreEqual(50, SaveOptions.NextWallOpacity(35));
            Assert.AreEqual(10, SaveOptions.NextWallOpacity(50), "after 50 % comes 10 % again");
            Assert.IsTrue(new SaveOptions { Walls = SaveOptions.WallsSeeThrough }.WallOpacityApplies);
            Assert.IsTrue(new SaveOptions { Walls = SaveOptions.WallsBoth }.WallOpacityApplies);
            Assert.IsFalse(new SaveOptions { Walls = SaveOptions.WallsNone }.WallOpacityApplies);
        }

        [Test]
        public void SetOptions_RoundTripsAndTheFaderReadsItAtOnce()
        {
            string dir = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "outofsight_walls_tests_" + System.Guid.NewGuid().ToString("N"));
            System.IO.Directory.CreateDirectory(dir);
            try
            {
                SaveStore.PathOverride = System.IO.Path.Combine(dir, SaveStore.FileName);
                Assert.AreEqual(WallLook.Both, WallFader.CurrentLook, "a fresh save is both");
                Assert.AreEqual(0.1f, WallFader.CurrentOpacity, 1e-6f, "at 10 %");
                SaveStore.SetOptions(new SaveOptions { Walls = SaveOptions.WallsSeeThrough });
                Assert.AreEqual(WallLook.SeeThrough, WallFader.CurrentLook, "the fader reads see-through at once");
                SaveStore.SetOptions(new SaveOptions { Walls = SaveOptions.WallsBoth, WallOpacity = 35 });
                Assert.AreEqual(WallLook.Both, WallFader.CurrentLook, "the fader reads the new look at once");
                Assert.AreEqual(0.35f, WallFader.CurrentOpacity, 1e-6f, "and the new opacity");
                StringAssert.Contains("\"walls\": \"both\"", SaveStore.Current.ToJson(), "the saved key");
                StringAssert.Contains("\"wallOpacity\": 35", SaveStore.Current.ToJson(), "the saved key");
                SaveStore.Load();
                Assert.AreEqual(SaveOptions.WallsBoth, SaveStore.Options.Walls, "a fresh load reads the look back");
                Assert.AreEqual(35, SaveStore.Options.WallOpacity);
                SaveStore.SetOptions(new SaveOptions { Walls = SaveOptions.WallsNone });
                Assert.AreEqual(WallLook.None, WallFader.CurrentLook);
                SaveStore.SetOptions(new SaveOptions { Walls = SaveOptions.WallsLowered, WallOpacity = 50 });
                Assert.AreEqual(WallLook.Lowered, WallFader.CurrentLook);
                SaveStore.ResetOptions();
                Assert.AreEqual(WallLook.Both, WallFader.CurrentLook, "Par défaut brings the walls back to both");
                Assert.AreEqual(10, SaveStore.Options.WallOpacity, "Par défaut brings the opacity back to 10 %");
                SaveStore.Load();
                Assert.AreEqual(SaveOptions.WallsBoth, SaveStore.Options.Walls, "Par défaut saved the default look");
                Assert.AreEqual(10, SaveStore.Options.WallOpacity, "Par défaut saved the default opacity");
            }
            finally
            {
                SaveStore.PathOverride = null;
                System.IO.Directory.Delete(dir, true);
            }
        }
    }
}
