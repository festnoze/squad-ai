using System;
using System.IO;
using Meuble.Core;
using NUnit.Framework;

namespace Meuble.Tests
{
    /// <summary>
    /// M7 (docs/CONTRACT_M7.md 1.4 and 1.6): the Qualité option in the save (the platform default, Moyen on mobile and
    /// Haut on PC, for a save without a choice; a round trip of each tier; the version stays 1) and the Android save,
    /// driven through SaveStore's replace hook on a real temporary folder: without File.Replace the .tmp is written,
    /// the current file copied to the .bak (overwritten), the target replaced; a load with the main file missing takes
    /// the .tmp, then the .bak. Every case starts from <see cref="SaveStore.ResetForTests"/> and checks its premise.
    /// </summary>
    public sealed class AndroidM7Tests
    {
        private string dir;
        private string path;

        [SetUp]
        public void SetUp()
        {
            SaveStore.ResetForTests();
            dir = Path.Combine(Path.GetTempPath(), "meuble_android_tests_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            path = Path.Combine(dir, SaveStore.FileName);
            SaveStore.PathOverride = path;
        }

        [TearDown]
        public void TearDown()
        {
            SaveStore.ResetForTests();
            try
            {
                Directory.Delete(dir, true);
            }
            catch (Exception)
            {
                // A leftover temporary folder is harmless.
            }
        }

        private static string Json(string won) => "{ \"version\": 1, \"won\": [" + won + "], \"best\": {} }";

        private static SaveData ReadBack(string file)
        {
            Assert.IsTrue(File.Exists(file), $"no file at {file}");
            SaveData data = SaveData.Parse(File.ReadAllText(file), out string problem);
            Assert.IsNotNull(data, $"{file} does not parse: {problem}");
            return data;
        }

        // ----- Qualité (1.4) -----

        /// <summary>The mutation killer of QUALITY_PLATFORM_DEFAULT: Moyen on Android, Haut on PC (the PC look and probe).</summary>
        [Test]
        public void Quality_defaults_to_Moyen_on_mobile_and_Haut_on_PC()
        {
            SaveOptions fresh = SaveOptions.Default();
            Assert.IsNull(fresh.Quality, "premise: a fresh options object holds no quality choice");
            Assert.AreNotEqual(SaveOptions.QualityMedium, SaveOptions.QualityHigh, "premise: two distinct tiers");
            Assert.AreEqual(SaveOptions.QualityMedium, fresh.QualityFor(true), "the mobile default is not Moyen");
            Assert.AreEqual(SaveOptions.QualityHigh, fresh.QualityFor(false), "the PC default is not Haut");
            Assert.AreEqual(SaveOptions.QualityHigh, SaveOptions.DefaultQuality(false));
            Assert.AreEqual(SaveOptions.QualityMedium, SaveOptions.DefaultQuality(true));
            // An unknown value is no choice: the platform default again, after a clamp and after a parse.
            var odd = new SaveOptions { Quality = "ultra" };
            Assert.AreEqual(SaveOptions.QualityHigh, odd.QualityFor(false));
            Assert.IsNull(odd.Clamped().Quality, "an unknown tier survived the clamp");
            SaveData parsed = SaveData.Parse("{ \"version\": 1, \"options\": { \"quality\": 3 } }", out string problem);
            Assert.IsNotNull(parsed, problem);
            Assert.AreEqual(SaveOptions.QualityMedium, parsed.Options.QualityFor(true), "a malformed quality did not fall back");
        }

        [Test]
        public void Quality_round_trips_through_the_save_and_an_old_save_gets_the_platform_default()
        {
            // An M6 save (options without "quality") loads with no choice, and the version stays 1.
            File.WriteAllText(path, "{ \"version\": 1, \"won\": [\"level1\"], \"best\": {}, \"options\": { \"sensitivity\": 1.5, \"volume\": 40, \"cone\": \"never\" } }");
            SaveStore.Load();
            Assert.AreEqual(SaveLoadStatus.Loaded, SaveStore.LastLoad, "premise: the M6 save loads");
            Assert.IsNull(SaveStore.Options.Quality);
            Assert.AreEqual(SaveOptions.QualityHigh, SaveStore.Options.QualityFor(false));
            Assert.AreEqual(SaveOptions.QualityMedium, SaveStore.Options.QualityFor(true));
            Assert.AreEqual(40, SaveStore.Options.Volume, "premise: the other options were read");

            // No choice is written as no field at all (the file stays an M6 file).
            SaveStore.Save();
            StringAssert.DoesNotContain("quality", File.ReadAllText(path), "a missing choice was written out");

            foreach (string tier in new[] { SaveOptions.QualityLow, SaveOptions.QualityMedium, SaveOptions.QualityHigh })
            {
                SaveOptions o = SaveStore.Options;
                SaveStore.SetOptions(new SaveOptions { Sensitivity = o.Sensitivity, Volume = o.Volume, Cone = o.Cone, Quality = tier });
                SaveStore.ResetForTests();
                SaveStore.PathOverride = path;
                SaveStore.Load();
                Assert.AreEqual(SaveLoadStatus.Loaded, SaveStore.LastLoad);
                Assert.AreEqual(tier, SaveStore.Options.Quality, $"{tier} did not survive a save and a load");
                Assert.AreEqual(tier, SaveStore.Options.QualityFor(true), "a chosen tier must win over the platform default");
                Assert.AreEqual(1.5f, SaveStore.Options.Sensitivity, 1e-6f, "the quality change lost the sensitivity");
                Assert.AreEqual(SaveOptions.ConeNever, SaveStore.Options.Cone, "the quality change lost the cone option");
                Assert.AreEqual(SaveData.CurrentVersion, ReadBack(path).Version);
            }
            Assert.AreEqual(1, SaveData.CurrentVersion, "the save version must stay 1");
            CollectionAssert.AreEqual(new[] { "level1" }, SaveStore.Current.Won);

            // The Qualité button's cycle.
            Assert.AreEqual(SaveOptions.QualityMedium, SaveOptions.NextQuality(SaveOptions.QualityLow));
            Assert.AreEqual(SaveOptions.QualityHigh, SaveOptions.NextQuality(SaveOptions.QualityMedium));
            Assert.AreEqual(SaveOptions.QualityLow, SaveOptions.NextQuality(SaveOptions.QualityHigh));
        }

        // ----- The Android save (1.6) -----

        /// <summary>The mutation killer of ANDROID_BAK_COPY.</summary>
        [Test]
        public void Without_File_Replace_the_save_writes_the_tmp_copies_the_bak_then_replaces_the_target()
        {
            string tmp = path + SaveStore.TmpSuffix;
            string bak = path + SaveStore.BakSuffix;
            SaveStore.Load();
            SaveStore.RecordWin("level1", 12.5f);
            Assert.IsTrue(File.Exists(path), "premise: the first win was written");
            Assert.IsFalse(File.Exists(bak), "premise: a first write keeps no .bak");
            string first = File.ReadAllText(path);

            int calls = 0;
            bool tmpHeldTheNewSave = false;
            bool targetStillOld = false;
            SaveStore.ReplaceForTests = (source, destination, backup) =>
            {
                calls++;
                // At the replace, the .tmp is already written and the target untouched.
                SaveData pending = File.Exists(source) ? SaveData.Parse(File.ReadAllText(source), out _) : null;
                tmpHeldTheNewSave = pending != null && pending.Won.Contains("level2");
                targetStillOld = File.ReadAllText(destination) == first;
                throw new PlatformNotSupportedException("no File.Replace here (test)");
            };
            SaveStore.RecordWin("level2", 20f);
            Assert.AreEqual(1, calls, "premise: the replacement was attempted once (not supported: no retry)");
            Assert.IsTrue(tmpHeldTheNewSave, "the .tmp was not written before the replacement");
            Assert.IsTrue(targetStillOld, "premise: the target was touched before the replacement");
            Assert.IsTrue(File.Exists(bak), "the fallback kept no .bak of the previous save");
            Assert.AreEqual(first, File.ReadAllText(bak), "the .bak is not the previous save");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, ReadBack(path).Won, "the target was not replaced");
            Assert.IsFalse(File.Exists(tmp), "the .tmp was left behind");
            Assert.IsFalse(SaveStore.InMemory);

            // The next write overwrites the .bak with the save it replaces.
            string second = File.ReadAllText(path);
            SaveStore.RecordWin("level3", 30f);
            Assert.AreEqual(2, calls);
            Assert.AreEqual(second, File.ReadAllText(bak), "the .bak was not overwritten by the next write");
            CollectionAssert.AreEqual(new[] { "level1", "level2", "level3" }, ReadBack(path).Won);
            Assert.AreEqual(3, SaveStore.WriteCount);
        }

        [Test]
        public void A_load_with_the_main_file_missing_takes_the_tmp_then_the_bak()
        {
            string tmp = path + SaveStore.TmpSuffix;
            string bak = path + SaveStore.BakSuffix;
            // A kill between the delete and the move of the fallback: the .tmp holds the newest save, the .bak the one before.
            File.WriteAllText(tmp, Json("\"level1\", \"level2\""));
            File.WriteAllText(bak, Json("\"level1\""));
            Assert.IsFalse(File.Exists(path), "premise: the main file is missing");
            SaveStore.Load();
            Assert.AreEqual(SaveLoadStatus.FromTmp, SaveStore.LastLoad, "the .tmp was not taken first");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, SaveStore.Current.Won);
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, ReadBack(path).Won, "the .tmp was not moved into place");

            // A kill before the .tmp was complete: the .bak.
            File.Delete(path);
            File.WriteAllText(tmp, "{ \"version\": 1, \"won\": [\"lev");
            SaveStore.ResetForTests();
            SaveStore.PathOverride = path;
            SaveStore.Load();
            Assert.AreEqual(SaveLoadStatus.FromBackup, SaveStore.LastLoad, "a truncated .tmp was not passed over for the .bak");
            CollectionAssert.AreEqual(new[] { "level1" }, SaveStore.Current.Won);
            CollectionAssert.AreEqual(new[] { "level1" }, ReadBack(path).Won, "the .bak was not written back as the save");
            Assert.IsFalse(SaveStore.InMemory);
        }
    }
}
