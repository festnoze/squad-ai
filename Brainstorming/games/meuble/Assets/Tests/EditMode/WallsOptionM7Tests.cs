using NUnit.Framework;
using OutOfSight.Core;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M7 walls pass (product owner, 2026-11-19): the Walls option ("lowered", "seethrough", "both", "none") and the wall
    /// opacity option (10, 20, 35, 50 %): defaults for a new save and for an old one without the fields (lowered, 20 %),
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
        public void Default_IsLoweredAt20Percent()
        {
            SaveOptions o = SaveOptions.Default();
            Assert.AreEqual(SaveOptions.WallsLowered, o.Walls);
            Assert.AreEqual(20, o.WallOpacity);
            Assert.AreEqual(20, Tuning.WallOpacityDefault, "the documented default");
            Assert.IsFalse(o.WallOpacityApplies, "lowered does not use the opacity");
            StringAssert.Contains("\"walls\": \"lowered\"", new SaveData().ToJson(), "a new save writes the default look");
        }

        [Test]
        public void OldSaveWithoutTheFields_LoadsLoweredAt20Percent()
        {
            string json = "{ \"version\": 1, \"won\": [], \"best\": {}, \"options\": { \"sensitivity\": 1.5, \"volume\": 30, \"cone\": \"never\" } }";
            SaveData data = SaveData.Parse(json, out string problem);
            Assert.IsNotNull(data, problem);
            Assert.AreEqual(SaveOptions.WallsLowered, data.Options.Walls);
            Assert.AreEqual(20, data.Options.WallOpacity);
            Assert.AreEqual(30, data.Options.Volume, "the other options are kept");
            SaveData old = SaveData.Parse("{ \"version\": 1 }", out problem);
            Assert.IsNotNull(old, problem);
            Assert.AreEqual(SaveOptions.WallsLowered, old.Options.Walls);
            Assert.AreEqual(20, old.Options.WallOpacity);
        }

        [Test]
        public void SavedLook_IsKeptWhenItIsNotTheDefault()
        {
            // The "walls" key is always written: a save holding "both" chose it, so it is not overridden by the default.
            SaveData data = SaveData.Parse("{ \"version\": 1, \"options\": { \"walls\": \"both\", \"wallOpacity\": 20 } }", out string problem);
            Assert.IsNotNull(data, problem);
            Assert.AreEqual(SaveOptions.WallsBoth, data.Options.Walls);
            SaveData none = SaveData.Parse("{ \"version\": 1, \"options\": { \"walls\": \"none\" } }", out problem);
            Assert.IsNotNull(none, problem);
            Assert.AreEqual(SaveOptions.WallsNone, none.Options.Walls);
        }

        [Test]
        public void HandEditedValues_FallBackToLoweredAndTheNearestStep()
        {
            SaveData data = SaveData.Parse("{ \"version\": 1, \"options\": { \"walls\": \"glass\", \"wallOpacity\": 33 } }", out string problem);
            Assert.IsNotNull(data, problem);
            Assert.AreEqual(SaveOptions.WallsLowered, data.Options.Walls, "an unknown look is lowered");
            Assert.AreEqual(35, data.Options.WallOpacity, "33 % goes to the nearest step, 35 %");
            foreach (string walls in new[] { SaveOptions.WallsLowered, SaveOptions.WallsSeeThrough, SaveOptions.WallsBoth, SaveOptions.WallsNone })
            {
                Assert.AreEqual(walls, new SaveOptions { Walls = walls }.Clamped().Walls, walls + " is kept");
            }
            Assert.AreEqual(10, new SaveOptions { WallOpacity = -40 }.Clamped().WallOpacity);
            Assert.AreEqual(50, new SaveOptions { WallOpacity = 400 }.Clamped().WallOpacity);
            SaveData wrongType = SaveData.Parse("{ \"version\": 1, \"options\": { \"walls\": 3, \"wallOpacity\": \"dim\" } }", out problem);
            Assert.IsNotNull(wrongType, problem);
            Assert.AreEqual(SaveOptions.WallsLowered, wrongType.Options.Walls);
            Assert.AreEqual(20, wrongType.Options.WallOpacity);
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
                Assert.AreEqual(WallLook.Lowered, WallFader.CurrentLook, "a fresh save is lowered");
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
                SaveStore.ResetOptions();
                Assert.AreEqual(WallLook.Lowered, WallFader.CurrentLook, "Par défaut brings the walls back to lowered");
                Assert.AreEqual(20, SaveStore.Options.WallOpacity);
            }
            finally
            {
                SaveStore.PathOverride = null;
                System.IO.Directory.Delete(dir, true);
            }
        }
    }
}
