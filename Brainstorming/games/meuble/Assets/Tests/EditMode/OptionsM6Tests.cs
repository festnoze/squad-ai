using OutOfSight.Core;
using NUnit.Framework;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M6 (docs/CONTRACT_M6.md 2.1): SaveOptions defaults, clamping (the "OPTIONS_STEP_ROUND" and
    /// "OPTIONS_CONE_FALLBACK" mutations), a round trip through SaveStore, and an old save (no "options" key)
    /// loading with defaults. SaveStore tests reset it first and restore it in TearDown (AudioListener.volume is
    /// global state other EditMode tests must never inherit).
    /// </summary>
    public sealed class OptionsM6Tests
    {
        [SetUp]
        public void SetUp()
        {
            SaveStore.ResetForTests();
        }

        [TearDown]
        public void TearDown()
        {
            SaveStore.ResetForTests();
        }

        [Test]
        public void Default_IsSensitivity1Volume80ConeAlways()
        {
            SaveOptions o = SaveOptions.Default();
            Assert.AreEqual(1.0f, o.Sensitivity, 1e-6f);
            Assert.AreEqual(80, o.Volume);
            Assert.AreEqual(SaveOptions.ConeAlways, o.Cone);
            Assert.IsFalse(o.HidesCone, "the default must show the floor cones");
        }

        [Test]
        public void Clamped_RoundsToTheNearestStep()
        {
            // 1.1 is between the 0.25 steps 1.00 and 1.25; nearest is 1.00. MUTATION:OPTIONS_STEP_ROUND (Round to
            // Floor or Ceil) rounds this to 1.00 or 1.25 differently from a value that is exactly on the boundary.
            var o = new SaveOptions { Sensitivity = 1.1f, Volume = 74, Cone = SaveOptions.ConeAlways };
            SaveOptions clamped = o.Clamped();
            Assert.AreEqual(1.0f, clamped.Sensitivity, 1e-4f, "1.1 should round down to the 1.00 step");
            Assert.AreEqual(70, clamped.Volume, "74 should round down to the 70 step");

            // A value just past the midpoint rounds up instead, which only Round (not Floor or Ceil) gets right for
            // both cases at once.
            var o2 = new SaveOptions { Sensitivity = 1.13f, Volume = 76, Cone = SaveOptions.ConeAlways };
            SaveOptions clamped2 = o2.Clamped();
            Assert.AreEqual(1.25f, clamped2.Sensitivity, 1e-4f, "1.13 should round up to the 1.25 step");
            Assert.AreEqual(80, clamped2.Volume, "76 should round up to the 80 step");
        }

        [Test]
        public void Clamped_ClampsOutOfRangeToTheBounds()
        {
            var high = new SaveOptions { Sensitivity = 9f, Volume = 500, Cone = SaveOptions.ConeAlways };
            SaveOptions clampedHigh = high.Clamped();
            Assert.AreEqual(2.0f, clampedHigh.Sensitivity, 1e-6f);
            Assert.AreEqual(100, clampedHigh.Volume);

            var low = new SaveOptions { Sensitivity = -5f, Volume = -40, Cone = SaveOptions.ConeAlways };
            SaveOptions clampedLow = low.Clamped();
            Assert.AreEqual(0.25f, clampedLow.Sensitivity, 1e-6f);
            Assert.AreEqual(0, clampedLow.Volume);
        }

        [Test]
        public void Clamped_InvalidConeFallsBackToAlways()
        {
            // MUTATION:OPTIONS_CONE_FALLBACK: skipping the fallback would let "never" survive even malformed, or let a
            // garbage string through unclamped.
            var garbage = new SaveOptions { Cone = "sometimes" };
            Assert.AreEqual(SaveOptions.ConeAlways, garbage.Clamped().Cone);

            var never = new SaveOptions { Cone = SaveOptions.ConeNever };
            Assert.AreEqual(SaveOptions.ConeNever, never.Clamped().Cone, "a valid \"never\" must survive clamping");
        }

        [Test]
        public void Parse_MissingOptionsIsDefault()
        {
            // An old save (version 1, no "options" key at all): SaveData.Parse must still succeed, with defaults.
            string json = "{ \"version\": 1, \"won\": [], \"best\": {} }";
            SaveData data = SaveData.Parse(json, out string problem);
            Assert.IsNotNull(data, $"an old save without options must still parse: {problem}");
            Assert.AreEqual(1.0f, data.Options.Sensitivity, 1e-6f);
            Assert.AreEqual(80, data.Options.Volume);
            Assert.AreEqual(SaveOptions.ConeAlways, data.Options.Cone);
        }

        [Test]
        public void Parse_MalformedOptionsFallsBackFieldByField()
        {
            // "sensitivity" the wrong type, "volume" out of range, "cone" unrecognised: every field falls back or
            // clamps on its own; the save as a whole still parses.
            string json = "{ \"version\": 1, \"won\": [], \"best\": {}, "
                + "\"options\": { \"sensitivity\": \"fast\", \"volume\": 999, \"cone\": \"sometimes\" } }";
            SaveData data = SaveData.Parse(json, out string problem);
            Assert.IsNotNull(data, $"a malformed options object must never fail the whole save: {problem}");
            Assert.AreEqual(1.0f, data.Options.Sensitivity, 1e-6f, "a non-numeric sensitivity keeps the default");
            Assert.AreEqual(100, data.Options.Volume, "999 clamps to the 100 bound");
            Assert.AreEqual(SaveOptions.ConeAlways, data.Options.Cone);
        }

        [Test]
        public void Parse_ValidOptionsRoundTripThroughJson()
        {
            var options = new SaveOptions { Sensitivity = 1.5f, Volume = 30, Cone = SaveOptions.ConeNever };
            var data = new SaveData { Options = options };
            string json = data.ToJson();
            SaveData parsed = SaveData.Parse(json, out string problem);
            Assert.IsNotNull(parsed, $"premise: a valid save must parse: {problem}");
            Assert.AreEqual(1.5f, parsed.Options.Sensitivity, 1e-6f);
            Assert.AreEqual(30, parsed.Options.Volume);
            Assert.AreEqual(SaveOptions.ConeNever, parsed.Options.Cone);
            Assert.IsTrue(parsed.Options.HidesCone);
        }

        // ----- Audio overhaul: the Music option (docs/audio/AUDIO_REPORT.md 5) -----

        [Test]
        public void Music_DefaultsAndOldSavesGetTheDefault()
        {
            Assert.AreEqual(Tuning.MusicDefault, SaveOptions.Default().Music);
            Assert.AreEqual(70, Tuning.MusicDefault, "the documented default");
            // A save from before the Music option (an options object without "music"): the default, nothing else moves.
            string json = "{ \"version\": 1, \"won\": [], \"best\": {}, \"options\": { \"sensitivity\": 1.5, \"volume\": 30, \"cone\": \"never\" } }";
            SaveData data = SaveData.Parse(json, out string problem);
            Assert.IsNotNull(data, $"an options object without music must parse: {problem}");
            Assert.AreEqual(Tuning.MusicDefault, data.Options.Music);
            Assert.AreEqual(30, data.Options.Volume, "the volume is kept");
            // No options at all: the default too.
            SaveData old = SaveData.Parse("{ \"version\": 1 }", out problem);
            Assert.IsNotNull(old, problem);
            Assert.AreEqual(Tuning.MusicDefault, old.Options.Music);
        }

        [Test]
        public void Music_ClampsRoundsAndRoundTrips()
        {
            Assert.AreEqual(70, new SaveOptions { Music = 74 }.Clamped().Music, "74 rounds to the 70 step");
            Assert.AreEqual(80, new SaveOptions { Music = 76 }.Clamped().Music, "76 rounds to the 80 step");
            Assert.AreEqual(100, new SaveOptions { Music = 500 }.Clamped().Music);
            Assert.AreEqual(0, new SaveOptions { Music = -5 }.Clamped().Music);
            SaveData wrongType = SaveData.Parse("{ \"version\": 1, \"options\": { \"music\": \"loud\" } }", out string problem);
            Assert.IsNotNull(wrongType, problem);
            Assert.AreEqual(Tuning.MusicDefault, wrongType.Options.Music, "a non-numeric music keeps the default");
            var data = new SaveData { Options = new SaveOptions { Music = 40 } };
            SaveData parsed = SaveData.Parse(data.ToJson(), out problem);
            Assert.IsNotNull(parsed, problem);
            Assert.AreEqual(40, parsed.Options.Music);
            StringAssert.Contains("\"music\": 40", data.ToJson(), "the saved key");
        }

        [Test]
        public void SaveStore_SetOptions_RoundTripsThroughLoad()
        {
            string dir = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "outofsight_options_tests_" + System.Guid.NewGuid().ToString("N"));
            System.IO.Directory.CreateDirectory(dir);
            try
            {
                SaveStore.PathOverride = System.IO.Path.Combine(dir, SaveStore.FileName);
                SaveStore.SetOptions(new SaveOptions { Sensitivity = 0.75f, Volume = 40, Cone = SaveOptions.ConeNever });
                Assert.AreEqual(0.75f, SaveStore.Options.Sensitivity, 1e-6f, "premise: SetOptions applied in memory");

                // A fresh load (as a new session would do) must read back exactly what was saved.
                SaveStore.Load();
                Assert.AreEqual(0.75f, SaveStore.Options.Sensitivity, 1e-6f);
                Assert.AreEqual(40, SaveStore.Options.Volume);
                Assert.AreEqual(SaveOptions.ConeNever, SaveStore.Options.Cone);

                SaveStore.ResetOptions();
                SaveStore.Load();
                Assert.AreEqual(1.0f, SaveStore.Options.Sensitivity, 1e-6f, "Par défaut did not reset the saved sensitivity");
                Assert.AreEqual(80, SaveStore.Options.Volume);
                Assert.AreEqual(SaveOptions.ConeAlways, SaveStore.Options.Cone);
            }
            finally
            {
                try
                {
                    System.IO.Directory.Delete(dir, true);
                }
                catch (System.Exception)
                {
                    // A leftover temp folder is harmless.
                }
            }
        }
    }
}
