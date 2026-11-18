using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text.RegularExpressions;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 6 and 15.7, CONTRACT_M5 16.11): the save file on a real temporary folder. The path
    /// choice (the "probe writes the real save" mutation), the atomic write (first write, Replace with its .bak, the
    /// retries, the delete-then-move fallback of Android), the read (a corrupt, zero, missing or newer version recovered
    /// from the .bak, else set aside as .bad), a missing file recovered from the .tmp then the .bak and the .tmp never
    /// deleted once the target is gone (CONTRACT_M5 17, m12), the in-memory session after an IO error (a locked or
    /// read-only file), the best time that only improves (the "a slower best time overwrites" mutation), unlocking and
    /// Jouer's level.
    /// Every case starts from <see cref="SaveStore.ResetForTests"/> and a fresh folder, and checks its premise first.
    /// </summary>
    public sealed class SaveM5Tests
    {
        private const string Persistent = "C:/outofsight/persistent";
        private const string Temp = "C:/outofsight/temp";

        private string dir;
        private string path;

        [SetUp]
        public void SetUp()
        {
            SaveStore.ResetForTests();
            dir = Path.Combine(Path.GetTempPath(), "outofsight_save_tests_" + Guid.NewGuid().ToString("N"));
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
                foreach (string file in Directory.GetFiles(dir))
                {
                    File.SetAttributes(file, FileAttributes.Normal);
                }
                Directory.Delete(dir, true);
            }
            catch (Exception)
            {
                // A leftover temporary folder is harmless.
            }
        }

        private static string Json(int version, string won, string best) =>
            "{ \"version\": " + version + ", \"won\": [" + won + "], \"best\": {" + best + "} }";

        private static SaveData ReadBack(string file)
        {
            Assert.IsTrue(File.Exists(file), $"no file at {file}");
            SaveData data = SaveData.Parse(File.ReadAllText(file), out string problem);
            Assert.IsNotNull(data, $"{file} does not parse: {problem}");
            return data;
        }

        // ----- Paths -----

        /// <summary>The mutation killer of "the probe writes the real save" (CONTRACT_M5 16.11).</summary>
        [Test]
        public void Probe_save_never_points_at_the_real_file()
        {
            string real = Path.Combine(Persistent, SaveStore.FileName);
            string test = Path.Combine(Temp, SaveStore.TestFileName);
            Assert.AreNotEqual(real, test, "premise: the two paths differ");
            Assert.IsTrue(SaveStore.IsTestRun(false, true, false), "a built player under --probe is not a test run");
            Assert.AreEqual(test, SaveStore.ChoosePath(false, true, false, Persistent, Temp), "a built player under --probe writes the real save");
            Assert.AreEqual(test, SaveStore.ChoosePath(false, true, true, Persistent, Temp), "--probe --look writes the real save");
            Assert.AreEqual(test, SaveStore.ChoosePath(true, true, false, Persistent, Temp), "the editor under --probe writes the real save");
        }

        [Test]
        public void ChoosePath_gives_the_real_file_only_to_a_plain_built_player()
        {
            string real = Path.Combine(Persistent, SaveStore.FileName);
            string test = Path.Combine(Temp, SaveStore.TestFileName);
            int realCount = 0;
            foreach (bool editor in new[] { false, true })
            {
                foreach (bool probe in new[] { false, true })
                {
                    foreach (bool look in new[] { false, true })
                    {
                        bool plain = !editor && !probe && !look;
                        string chosen = SaveStore.ChoosePath(editor, probe, look, Persistent, Temp);
                        Assert.AreEqual(plain ? real : test, chosen, $"editor={editor} probe={probe} look={look}");
                        realCount += chosen == real ? 1 : 0;
                    }
                }
            }
            Assert.AreEqual(1, realCount, "exactly one of the 8 runs may touch the real save");
        }

        [Test]
        public void The_editor_default_path_is_the_test_file()
        {
            Assert.IsTrue(Application.isEditor, "premise: an editor run");
            string chosen = SaveStore.DefaultPath();
            Assert.AreEqual(Path.Combine(Application.temporaryCachePath, SaveStore.TestFileName), chosen);
            Assert.AreNotEqual(Path.Combine(Application.persistentDataPath, SaveStore.FileName), chosen, "the editor points at the real save");
        }

        [Test]
        public void Boot_in_the_editor_points_at_a_fresh_test_file()
        {
            SaveStore.PathOverride = null;
            string expected = Path.Combine(Application.temporaryCachePath, SaveStore.TestFileName);
            Directory.CreateDirectory(Application.temporaryCachePath);
            File.WriteAllText(expected, Json(1, "\"level1\"", "\"level1\": 4.0"));
            File.WriteAllText(expected + SaveStore.BakSuffix, Json(1, "\"level1\"", ""));
            Assert.IsTrue(File.Exists(expected), "premise: a leftover test save");

            SaveStore.Boot();
            Assert.AreEqual(expected, SaveStore.PathOverride, "the editor boot does not point at the test file");
            Assert.IsFalse(File.Exists(expected), "the boot kept the previous run's test save");
            Assert.IsFalse(File.Exists(expected + SaveStore.BakSuffix), "the boot kept the previous run's .bak");
            Assert.IsTrue(SaveStore.UnlockAll, "the editor does not unlock every level");
            Assert.AreEqual(SaveLoadStatus.Fresh, SaveStore.LastLoad);
            Assert.IsEmpty(SaveStore.Current.Won);
        }

        [Test]
        public void Boot_keeps_a_path_a_test_injected()
        {
            File.WriteAllText(path, Json(1, "\"level1\"", "\"level1\": 4.0"));
            SaveStore.Boot();
            Assert.AreEqual(path, SaveStore.PathOverride);
            Assert.IsTrue(File.Exists(path), "the boot deleted an injected save");
            Assert.AreEqual(SaveLoadStatus.Loaded, SaveStore.LastLoad);
            CollectionAssert.AreEqual(new[] { "level1" }, SaveStore.Current.Won);
        }

        // ----- Writes -----

        [Test]
        public void First_write_creates_the_file_with_no_backup()
        {
            Assert.IsFalse(File.Exists(path), "premise: no save yet");
            SaveStore.Load();
            Assert.AreEqual(SaveLoadStatus.Fresh, SaveStore.LastLoad);
            Assert.IsEmpty(Directory.GetFiles(dir), "loading a missing save wrote something");

            SaveStore.RecordWin("level1", 12.5f);
            SaveData data = ReadBack(path);
            Assert.AreEqual(SaveData.CurrentVersion, data.Version);
            CollectionAssert.AreEqual(new[] { "level1" }, data.Won);
            Assert.AreEqual(12.5f, data.Best["level1"], 1e-4f);
            Assert.IsFalse(File.Exists(path + SaveStore.BakSuffix), "a first write made a backup of nothing");
            Assert.IsFalse(File.Exists(path + SaveStore.TmpSuffix), "the .tmp was left behind");
            Assert.IsFalse(SaveStore.InMemory);
            Assert.AreEqual(1, SaveStore.WriteCount);
        }

        [Test]
        public void Next_write_replaces_the_file_and_keeps_the_previous_one_as_bak()
        {
            SaveStore.Load();
            SaveStore.RecordWin("level1", 12.5f);
            Assert.IsTrue(File.Exists(path), "premise: the first win was written");
            string first = File.ReadAllText(path);

            SaveStore.RecordWin("level2", 20f);
            Assert.IsTrue(File.Exists(path + SaveStore.BakSuffix), "File.Replace kept no backup");
            Assert.AreEqual(first, File.ReadAllText(path + SaveStore.BakSuffix), "the .bak is not the previous save");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, ReadBack(path).Won);
            Assert.IsFalse(File.Exists(path + SaveStore.TmpSuffix), "the .tmp was left behind");
            Assert.AreEqual(2, SaveStore.WriteCount);

            // And it loads back as it was written.
            SaveStore.ResetForTests();
            SaveStore.PathOverride = path;
            SaveStore.Load();
            Assert.AreEqual(SaveLoadStatus.Loaded, SaveStore.LastLoad);
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, SaveStore.Current.Won);
            Assert.AreEqual(20f, SaveStore.Current.Best["level2"], 1e-4f);
        }

        /// <summary>CONTRACT_M5_v3 15.7: 3 tries, 50 ms apart, before the fallback.</summary>
        [Test]
        public void A_busy_file_is_replaced_on_the_third_try()
        {
            SaveStore.Load();
            SaveStore.RecordWin("level1", 12.5f);
            Assert.IsTrue(File.Exists(path), "premise: the first win was written");
            int calls = 0;
            SaveStore.ReplaceForTests = (source, destination, backup) =>
            {
                calls++;
                if (calls < Tuning.SaveReplaceTries)
                {
                    throw new IOException("busy (test)");
                }
                File.Replace(source, destination, backup);
            };
            var watch = Stopwatch.StartNew();
            SaveStore.RecordWin("level2", 20f);
            watch.Stop();
            Assert.AreEqual(Tuning.SaveReplaceTries, calls, "File.Replace was not tried three times");
            Assert.GreaterOrEqual(watch.ElapsedMilliseconds, (Tuning.SaveReplaceTries - 1) * Tuning.SaveReplaceRetryMs - 10,
                "the tries were not 50 ms apart");
            Assert.IsTrue(File.Exists(path + SaveStore.BakSuffix), "the third try did not run File.Replace");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, ReadBack(path).Won);
            Assert.IsFalse(SaveStore.InMemory);
        }

        /// <summary>CONTRACT_M5_v3 15.7: Android (M6) has no File.Replace; the delete-then-move branch writes the save.</summary>
        [Test]
        public void Without_File_Replace_the_save_falls_back_to_delete_then_move()
        {
            SaveStore.Load();
            SaveStore.RecordWin("level1", 12.5f);
            Assert.IsTrue(File.Exists(path), "premise: the first win was written");
            int calls = 0;
            SaveStore.ReplaceForTests = (source, destination, backup) =>
            {
                calls++;
                throw new PlatformNotSupportedException("no File.Replace here (test)");
            };
            SaveStore.RecordWin("level2", 20f);
            Assert.AreEqual(1, calls, "premise: the replacement was attempted (and not retried: it is not supported)");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, ReadBack(path).Won, "the fallback did not write the save");
            Assert.IsFalse(File.Exists(path + SaveStore.TmpSuffix), "the fallback left the .tmp behind");
            Assert.IsFalse(SaveStore.InMemory, "the fallback gave up");
            Assert.AreEqual(2, SaveStore.WriteCount);
        }

        [Test]
        public void Every_failed_replace_still_ends_in_delete_then_move()
        {
            SaveStore.Load();
            SaveStore.RecordWin("level1", 12.5f);
            Assert.IsTrue(File.Exists(path), "premise: the first win was written");
            int calls = 0;
            SaveStore.ReplaceForTests = (source, destination, backup) =>
            {
                calls++;
                throw new IOException("busy (test)");
            };
            SaveStore.RecordWin("level2", 20f);
            Assert.AreEqual(Tuning.SaveReplaceTries, calls);
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, ReadBack(path).Won, "the fallback did not write the save");
            Assert.IsFalse(SaveStore.InMemory);
        }

        /// <summary>
        /// CONTRACT_M5 17 (m12): a scanner holds the fresh .tmp through the three File.Replace tries, the fallback deletes
        /// the target and its move fails on the lock. The .tmp is then the only copy of the save: it must survive, even
        /// once the scanner lets go (this one lets go the moment SaveStore reports the failed write, before SaveStore
        /// decides about the .tmp), and the next load restores it.
        /// </summary>
        [Test]
        public void A_locked_tmp_in_the_fallback_is_kept_and_restored_at_the_next_load()
        {
            string tmp = path + SaveStore.TmpSuffix;
            SaveStore.Load();
            SaveStore.RecordWin("level1", 12.5f);
            Assert.IsTrue(File.Exists(path), "premise: the first win was written");
            Assert.IsFalse(File.Exists(path + SaveStore.BakSuffix), "premise: a first write keeps no .bak");
            FileStream scanner = null;
            bool released = false;
            int calls = 0;
            SaveStore.ReplaceForTests = (source, destination, backup) =>
            {
                calls++;
                if (scanner == null)
                {
                    scanner = new FileStream(source, FileMode.Open, FileAccess.Read, FileShare.None);
                }
                throw new IOException("busy (test)");
            };
            Application.LogCallback onLog = (condition, stack, type) =>
            {
                if (scanner != null && !released && type == LogType.Warning && condition.Contains("cannot write"))
                {
                    scanner.Dispose();
                    released = true;
                }
            };
            Application.logMessageReceived += onLog;
            try
            {
                Assert.DoesNotThrow(() => SaveStore.RecordWin("level2", 20f));
            }
            finally
            {
                Application.logMessageReceived -= onLog;
                scanner?.Dispose();
            }
            Assert.AreEqual(Tuning.SaveReplaceTries, calls, "premise: File.Replace was not tried three times");
            Assert.IsTrue(released, "premise: the write did not fail while the scanner held the .tmp");
            Assert.IsTrue(SaveStore.InMemory, "premise: the failed move did not switch the session to memory");
            Assert.IsFalse(File.Exists(path), "premise: the fallback did not delete the target before its move failed");
            Assert.IsTrue(File.Exists(tmp), "the .tmp was deleted once the target was gone: the save is lost");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, ReadBack(tmp).Won, "the .tmp does not hold the last save");

            // The next launch restores it.
            SaveStore.ResetForTests();
            SaveStore.PathOverride = path;
            Assert.DoesNotThrow(SaveStore.Load);
            Assert.AreEqual(SaveLoadStatus.FromTmp, SaveStore.LastLoad, "the next load did not restore the .tmp");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, SaveStore.Current.Won);
            Assert.AreEqual(20f, SaveStore.Current.Best["level2"], 1e-4f);
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, ReadBack(path).Won, "the restored save is not back in place");
            Assert.IsFalse(File.Exists(tmp), "the restored .tmp was left behind");
            Assert.IsFalse(SaveStore.InMemory);
        }

        /// <summary>
        /// A File.Replace that sets the target aside as .bak and then fails to move the .tmp in (ReplaceFile's
        /// ERROR_UNABLE_TO_MOVE_REPLACEMENT) leaves no target: no point in trying again, the move finishes the write.
        /// </summary>
        [Test]
        public void A_replace_that_set_the_target_aside_is_finished_by_the_move()
        {
            SaveStore.Load();
            SaveStore.RecordWin("level1", 12.5f);
            Assert.IsTrue(File.Exists(path), "premise: the first win was written");
            string first = File.ReadAllText(path);
            int calls = 0;
            SaveStore.ReplaceForTests = (source, destination, backup) =>
            {
                calls++;
                File.Move(destination, backup);
                throw new IOException("unable to move the replacement (test)");
            };
            SaveStore.RecordWin("level2", 20f);
            Assert.AreEqual(1, calls, "File.Replace was tried again with no target left");
            Assert.AreEqual(first, File.ReadAllText(path + SaveStore.BakSuffix), "premise: the target was not set aside as .bak");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, ReadBack(path).Won, "the move did not finish the write");
            Assert.IsFalse(File.Exists(path + SaveStore.TmpSuffix), "the .tmp was left behind");
            Assert.IsFalse(SaveStore.InMemory);
            Assert.AreEqual(2, SaveStore.WriteCount);
        }

        // ----- Reads -----

        [Test]
        public void A_missing_file_starts_fresh_and_writes_nothing()
        {
            SaveStore.Load();
            Assert.AreEqual(SaveLoadStatus.Fresh, SaveStore.LastLoad);
            Assert.IsEmpty(SaveStore.Current.Won);
            Assert.IsEmpty(Directory.GetFiles(dir));
            Assert.IsFalse(SaveStore.InMemory);
        }

        private static IEnumerable<TestCaseData> Unusable()
        {
            yield return new TestCaseData("{ \"version\": 1, \"won\": [\"lev").SetName("Unusable_truncated_json_is_recovered_from_bak");
            yield return new TestCaseData("not json at all").SetName("Unusable_garbage_is_recovered_from_bak");
            yield return new TestCaseData("").SetName("Unusable_empty_file_is_recovered_from_bak");
            yield return new TestCaseData(Json(0, "\"level5\"", "")).SetName("Unusable_version_0_is_recovered_from_bak");
            yield return new TestCaseData("{ \"won\": [\"level5\"], \"best\": {} }").SetName("Unusable_missing_version_is_recovered_from_bak");
            yield return new TestCaseData(Json(2, "\"level5\"", "\"level5\": 1.0")).SetName("Unusable_newer_version_is_recovered_from_bak");
        }

        [TestCaseSource(nameof(Unusable))]
        public void Unusable_file_is_recovered_from_its_bak(string content)
        {
            string bak = Json(1, "\"level1\", \"level2\"", "\"level1\": 9.5");
            File.WriteAllText(path, content);
            File.WriteAllText(path + SaveStore.BakSuffix, bak);
            Assert.IsNull(SaveData.Parse(content, out _), "premise: the file is unusable");

            Assert.DoesNotThrow(SaveStore.Load);
            Assert.AreEqual(SaveLoadStatus.FromBackup, SaveStore.LastLoad, "the .bak was not used");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, SaveStore.Current.Won);
            Assert.AreEqual(9.5f, SaveStore.Current.Best["level1"], 1e-4f);
            Assert.AreEqual(content, File.ReadAllText(path + SaveStore.BadSuffix), "the unusable file was not kept as .bad");
            Assert.AreEqual(bak, File.ReadAllText(path + SaveStore.BakSuffix), "the good .bak was changed");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, ReadBack(path).Won, "the save file does not hold the recovered data");
            Assert.IsFalse(SaveStore.InMemory);
        }

        private static IEnumerable<TestCaseData> UnusableWithoutBackup()
        {
            yield return new TestCaseData("not json at all", null).SetName("Corrupt_without_bak_goes_to_bad_and_starts_fresh");
            yield return new TestCaseData("not json at all", "{ broken").SetName("Corrupt_with_a_corrupt_bak_goes_to_bad_and_starts_fresh");
            yield return new TestCaseData(Json(2, "\"level5\"", ""), null).SetName("Newer_without_bak_goes_to_bad_and_starts_fresh");
            yield return new TestCaseData(Json(2, "\"level5\"", ""), Json(7, "", "")).SetName("Newer_with_a_newer_bak_goes_to_bad_and_starts_fresh");
        }

        [TestCaseSource(nameof(UnusableWithoutBackup))]
        public void Unusable_file_without_a_usable_bak_goes_to_bad_and_starts_fresh(string content, string bak)
        {
            File.WriteAllText(path, content);
            if (bak != null)
            {
                File.WriteAllText(path + SaveStore.BakSuffix, bak);
            }
            File.WriteAllText(path + SaveStore.BadSuffix, "an older bad file");
            Assert.IsNull(SaveData.Parse(content, out _), "premise: the file is unusable");

            Assert.DoesNotThrow(SaveStore.Load);
            Assert.AreEqual(SaveLoadStatus.Reset, SaveStore.LastLoad);
            Assert.IsEmpty(SaveStore.Current.Won, "the save did not start fresh");
            Assert.IsFalse(File.Exists(path), "the unusable file is still in place");
            Assert.AreEqual(content, File.ReadAllText(path + SaveStore.BadSuffix), "the .bad does not hold the unusable file (an older .bad must be replaced)");
            Assert.IsFalse(SaveStore.InMemory, "a corrupt file must not stop the session from saving");

            // The fresh save is written over nothing.
            SaveStore.RecordWin("level1", 3f);
            SaveData data = ReadBack(path);
            CollectionAssert.AreEqual(new[] { "level1" }, data.Won);
            Assert.AreEqual(SaveData.CurrentVersion, data.Version);
        }

        // ----- A missing file: the .tmp, then the .bak (CONTRACT_M5 17, m12) -----

        /// <summary>The .tmp of an interrupted write is the newest save: it wins over an older .bak and is moved into place.</summary>
        [Test]
        public void A_missing_file_with_a_good_tmp_is_restored_from_it_before_the_bak()
        {
            string tmpJson = Json(1, "\"level1\", \"level2\"", "\"level2\": 8.0");
            string bakJson = Json(1, "\"level1\"", "\"level1\": 9.5");
            File.WriteAllText(path + SaveStore.TmpSuffix, tmpJson);
            File.WriteAllText(path + SaveStore.BakSuffix, bakJson);
            Assert.IsFalse(File.Exists(path), "premise: the save file is missing");
            Assert.IsNotNull(SaveData.Parse(tmpJson, out _), "premise: the .tmp parses");
            Assert.IsNotNull(SaveData.Parse(bakJson, out _), "premise: the .bak parses too");

            Assert.DoesNotThrow(SaveStore.Load);
            Assert.AreEqual(SaveLoadStatus.FromTmp, SaveStore.LastLoad, "the .tmp was not restored");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, SaveStore.Current.Won, "the older .bak was preferred to the .tmp");
            Assert.AreEqual(8f, SaveStore.Current.Best["level2"], 1e-4f);
            Assert.AreEqual(tmpJson, File.ReadAllText(path), "the .tmp was not moved into place as it was");
            Assert.IsFalse(File.Exists(path + SaveStore.TmpSuffix), "the restored .tmp was left behind");
            Assert.AreEqual(bakJson, File.ReadAllText(path + SaveStore.BakSuffix), "the .bak was changed");
            Assert.IsFalse(File.Exists(path + SaveStore.BadSuffix), "a missing file was taken for a corrupt one");
            Assert.IsFalse(SaveStore.InMemory);

            // The session saves as usual from there: File.Replace keeps the restored save as the .bak.
            SaveStore.RecordWin("level3", 4f);
            CollectionAssert.AreEqual(new[] { "level1", "level2", "level3" }, ReadBack(path).Won);
            Assert.AreEqual(tmpJson, File.ReadAllText(path + SaveStore.BakSuffix), "the restored save did not become the .bak");
        }

        private static IEnumerable<TestCaseData> MissingWithBackup()
        {
            yield return new TestCaseData((string)null).SetName("Missing_file_without_tmp_is_restored_from_bak");
            yield return new TestCaseData("{ \"version\": 1, \"won\": [\"lev").SetName("Missing_file_with_a_truncated_tmp_is_restored_from_bak");
            yield return new TestCaseData("").SetName("Missing_file_with_an_empty_tmp_is_restored_from_bak");
            yield return new TestCaseData(Json(2, "\"level5\"", "")).SetName("Missing_file_with_a_newer_tmp_is_restored_from_bak");
        }

        [TestCaseSource(nameof(MissingWithBackup))]
        public void Missing_file_is_restored_from_its_bak(string tmpContent)
        {
            string bakJson = Json(1, "\"level1\", \"level2\"", "\"level1\": 9.5");
            if (tmpContent != null)
            {
                File.WriteAllText(path + SaveStore.TmpSuffix, tmpContent);
                Assert.IsNull(SaveData.Parse(tmpContent, out _), "premise: the .tmp is unusable");
            }
            File.WriteAllText(path + SaveStore.BakSuffix, bakJson);
            Assert.IsFalse(File.Exists(path), "premise: the save file is missing");

            Assert.DoesNotThrow(SaveStore.Load);
            Assert.AreEqual(SaveLoadStatus.FromBackup, SaveStore.LastLoad, "the .bak was not used");
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, SaveStore.Current.Won);
            Assert.AreEqual(9.5f, SaveStore.Current.Best["level1"], 1e-4f);
            CollectionAssert.AreEqual(new[] { "level1", "level2" }, ReadBack(path).Won, "the save file does not hold the recovered data");
            Assert.AreEqual(bakJson, File.ReadAllText(path + SaveStore.BakSuffix), "the .bak was changed");
            Assert.IsFalse(File.Exists(path + SaveStore.TmpSuffix), "a .tmp was left behind");
            Assert.IsFalse(File.Exists(path + SaveStore.BadSuffix), "a missing file was taken for a corrupt one");
            Assert.IsFalse(SaveStore.InMemory);
            Assert.AreEqual(1, SaveStore.WriteCount, "the recovered data was not written back once");
        }

        [Test]
        public void A_missing_file_without_a_usable_tmp_or_bak_starts_fresh()
        {
            File.WriteAllText(path + SaveStore.TmpSuffix, "not json at all");
            File.WriteAllText(path + SaveStore.BakSuffix, "{ broken");
            Assert.IsFalse(File.Exists(path), "premise: the save file is missing");

            Assert.DoesNotThrow(SaveStore.Load);
            Assert.AreEqual(SaveLoadStatus.Fresh, SaveStore.LastLoad);
            Assert.IsEmpty(SaveStore.Current.Won);
            Assert.IsFalse(File.Exists(path), "an unusable .tmp or .bak was restored");
            Assert.AreEqual("{ broken", File.ReadAllText(path + SaveStore.BakSuffix), "the .bak was changed by the load");
            Assert.IsFalse(File.Exists(path + SaveStore.BadSuffix));
            Assert.IsFalse(SaveStore.InMemory, "unusable leftovers must not stop the session from saving");

            SaveStore.RecordWin("level1", 3f);
            CollectionAssert.AreEqual(new[] { "level1" }, ReadBack(path).Won, "the fresh save was not written");
            Assert.IsFalse(File.Exists(path + SaveStore.TmpSuffix), "the .tmp was left behind");
        }

        /// <summary>A .tmp that exists but cannot be read is an IO error: in memory, the .bak is not used, nothing is touched.</summary>
        [Test]
        public void A_locked_tmp_on_read_with_the_file_missing_runs_in_memory_and_touches_nothing()
        {
            string tmp = path + SaveStore.TmpSuffix;
            string tmpJson = Json(1, "\"level1\", \"level2\"", "");
            string bakJson = Json(1, "\"level1\"", "");
            File.WriteAllText(tmp, tmpJson);
            File.WriteAllText(path + SaveStore.BakSuffix, bakJson);
            using (new FileStream(tmp, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            {
                Assert.DoesNotThrow(SaveStore.Load);
                Assert.AreEqual(SaveLoadStatus.ReadError, SaveStore.LastLoad, "premise: the locked .tmp could be read");
                Assert.IsTrue(SaveStore.InMemory);
                Assert.DoesNotThrow(() => SaveStore.RecordWin("level3", 5f));
            }
            Assert.DoesNotThrow(() => SaveStore.RecordWin("level4", 6f));
            Assert.IsFalse(File.Exists(path), "a session that could not read the .tmp wrote a save");
            Assert.AreEqual(tmpJson, File.ReadAllText(tmp), "the .tmp was changed");
            Assert.AreEqual(bakJson, File.ReadAllText(path + SaveStore.BakSuffix), "the .bak was changed");
            Assert.AreEqual(0, SaveStore.WriteCount);
        }

        /// <summary>
        /// A scanner that lets the .tmp be read but not moved: the session plays the restored progress in memory, the
        /// .tmp stays as it was, and the next run moves it into place.
        /// </summary>
        [Test]
        public void A_tmp_that_cannot_be_moved_into_place_is_played_in_memory_and_kept()
        {
            string tmp = path + SaveStore.TmpSuffix;
            string tmpJson = Json(1, "\"level1\", \"level2\"", "\"level2\": 8.0");
            File.WriteAllText(tmp, tmpJson);
            using (new FileStream(tmp, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                Assert.DoesNotThrow(SaveStore.Load);
                Assert.IsFalse(File.Exists(path), "premise: the .tmp was moved while a scanner held it");
                Assert.AreEqual(SaveLoadStatus.FromTmp, SaveStore.LastLoad, "the readable .tmp was not restored");
                CollectionAssert.AreEqual(new[] { "level1", "level2" }, SaveStore.Current.Won, "the session does not play the restored progress");
                Assert.IsTrue(SaveStore.InMemory, "a .tmp that could not be moved did not switch the session to memory");
                Assert.DoesNotThrow(() => SaveStore.RecordWin("level3", 5f));
            }
            Assert.IsFalse(File.Exists(path));
            Assert.AreEqual(tmpJson, File.ReadAllText(tmp), "the .tmp was changed");

            SaveStore.ResetForTests();
            SaveStore.PathOverride = path;
            SaveStore.Load();
            Assert.AreEqual(SaveLoadStatus.FromTmp, SaveStore.LastLoad, "the next run did not restore the .tmp");
            Assert.AreEqual(tmpJson, File.ReadAllText(path), "the next run did not move the .tmp into place");
            Assert.IsFalse(SaveStore.InMemory);
        }

        // ----- IO errors: in memory, never an exception, never an overwrite -----

        [Test]
        public void A_locked_file_on_read_runs_in_memory_and_is_never_overwritten()
        {
            File.WriteAllText(path, Json(1, "\"level1\"", "\"level1\": 9.5"));
            string before = File.ReadAllText(path);
            using (new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            {
                Assert.DoesNotThrow(SaveStore.Load);
                Assert.AreEqual(SaveLoadStatus.ReadError, SaveStore.LastLoad, "premise: the locked file could be read");
                Assert.IsTrue(SaveStore.InMemory);
                Assert.DoesNotThrow(() => SaveStore.RecordWin("level2", 5f));
            }
            // The lock is gone, but the session still never writes: its progress may be partial.
            Assert.DoesNotThrow(() => SaveStore.RecordWin("level3", 6f));
            Assert.AreEqual(before, File.ReadAllText(path), "a session that could not read the save overwrote it");
            Assert.IsFalse(File.Exists(path + SaveStore.TmpSuffix));
            Assert.IsFalse(File.Exists(path + SaveStore.BakSuffix));
            Assert.IsFalse(File.Exists(path + SaveStore.BadSuffix), "a locked file was taken for a corrupt one");
            CollectionAssert.Contains(SaveStore.Current.Won, "level3", "the session lost its wins in memory");
        }

        [Test]
        public void A_locked_file_on_write_runs_in_memory_without_an_exception()
        {
            SaveStore.Load();
            SaveStore.RecordWin("level1", 12.5f);
            Assert.IsTrue(File.Exists(path), "premise: the first win was written");
            string before = File.ReadAllText(path);
            using (new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            {
                Assert.DoesNotThrow(() => SaveStore.RecordWin("level2", 20f));
                Assert.IsTrue(SaveStore.InMemory, "a failed write did not switch the session to memory");
            }
            Assert.DoesNotThrow(() => SaveStore.RecordWin("level3", 21f));
            Assert.AreEqual(before, File.ReadAllText(path), "the save changed after a failed write");
            Assert.IsFalse(File.Exists(path + SaveStore.TmpSuffix), "the .tmp of the failed write was left behind");
            CollectionAssert.AreEqual(new[] { "level1", "level2", "level3" }, SaveStore.Current.Won);
        }

        [Test]
        public void A_read_only_file_on_write_runs_in_memory_without_an_exception()
        {
            SaveStore.Load();
            SaveStore.RecordWin("level1", 12.5f);
            Assert.IsTrue(File.Exists(path), "premise: the first win was written");
            string before = File.ReadAllText(path);
            File.SetAttributes(path, FileAttributes.ReadOnly);
            Assert.DoesNotThrow(() => SaveStore.RecordWin("level2", 20f));
            Assert.IsTrue(SaveStore.InMemory, "a write onto a read-only save did not switch the session to memory");
            Assert.AreEqual(before, File.ReadAllText(path), "a read-only save was overwritten");
            Assert.IsFalse(File.Exists(path + SaveStore.TmpSuffix), "the .tmp of the failed write was left behind");
        }

        // ----- Best times, the Recorded event -----

        /// <summary>The mutation killer of "a slower best time overwrites" (v3 6: replaced only by a strictly lower time).</summary>
        [Test]
        public void A_slower_time_never_replaces_the_best()
        {
            SaveStore.Load();
            RecordResult first = SaveStore.RecordWin("level1", 12f);
            Assert.IsTrue(first.NewBest, "the first time is not a record");
            Assert.AreEqual(12f, first.Best, 1e-4f);
            Assert.Less(first.PreviousBest, 0f, "a first win has a previous best");

            RecordResult slower = SaveStore.RecordWin("level1", 15f);
            Assert.IsFalse(slower.NewBest, "a slower time is a record");
            Assert.AreEqual(12f, slower.Best, 1e-4f, "a slower time replaced the best");
            Assert.AreEqual(12f, slower.PreviousBest, 1e-4f);
            Assert.AreEqual(12f, ReadBack(path).Best["level1"], 1e-4f, "a slower time replaced the best on disk");

            RecordResult equal = SaveStore.RecordWin("level1", 12f);
            Assert.IsFalse(equal.NewBest, "an equal time is a record (strictly lower only)");

            RecordResult faster = SaveStore.RecordWin("level1", 10f);
            Assert.IsTrue(faster.NewBest, "a faster time is not a record");
            Assert.AreEqual(10f, faster.Best, 1e-4f);
            Assert.AreEqual(12f, faster.PreviousBest, 1e-4f);
            Assert.AreEqual(10f, ReadBack(path).Best["level1"], 1e-4f, "the faster time is not on disk");
            CollectionAssert.AreEqual(new[] { "level1" }, SaveStore.Current.Won, "a level was listed twice in won");
        }

        [Test]
        public void RecordWin_saves_before_raising_Recorded()
        {
            SaveStore.Load();
            int raised = 0;
            bool writtenFirst = false;
            RecordResult seen = default;
            SaveStore.Recorded += result =>
            {
                raised++;
                seen = result;
                writtenFirst = File.Exists(path);
            };
            SaveStore.RecordWin("level1", 7f);
            Assert.AreEqual(1, raised, "Recorded was not raised once");
            Assert.IsTrue(seen.NewBest);
            Assert.AreEqual(7f, seen.Best, 1e-4f);
            Assert.IsTrue(writtenFirst, "Recorded was raised before the save was written");
        }

        [Test]
        public void A_throwing_Recorded_subscriber_never_escapes_SaveStore()
        {
            SaveStore.Load();
            int after = 0;
            SaveStore.Recorded += result => throw new InvalidOperationException("subscriber bug (test)");
            SaveStore.Recorded += result => after++;
            LogAssert.Expect(LogType.Exception, new Regex("subscriber bug"));
            Assert.DoesNotThrow(() => SaveStore.RecordWin("level1", 3f));
            Assert.AreEqual(1, after, "a throwing subscriber stopped the next one");
            Assert.IsTrue(File.Exists(path));
        }

        [Test]
        public void ResetForTests_clears_every_static()
        {
            int raised = 0;
            SaveStore.UnlockAll = true;
            SaveStore.Recorded += result => raised++;
            SaveStore.ReplaceForTests = (a, b, c) => { };
            SaveStore.Load();
            SaveStore.RecordWin("level1", 3f);
            Assert.AreEqual(1, raised, "premise: the subscriber was called");

            SaveStore.ResetForTests();
            Assert.IsNull(SaveStore.PathOverride);
            Assert.IsFalse(SaveStore.UnlockAll);
            Assert.IsNotNull(SaveStore.Current);
            Assert.IsEmpty(SaveStore.Current.Won);
            Assert.IsEmpty(SaveStore.Current.Best);
            Assert.IsFalse(SaveStore.InMemory);
            Assert.AreEqual(SaveLoadStatus.None, SaveStore.LastLoad);
            Assert.AreEqual(0, SaveStore.WriteCount);
            Assert.IsNull(SaveStore.ReplaceForTests);
            SaveStore.PathOverride = path;
            SaveStore.RecordWin("level2", 3f);
            Assert.AreEqual(1, raised, "a Recorded subscriber survived the reset");
        }

        // ----- Unlocking and Jouer -----

        [Test]
        public void A_level_unlocks_when_the_previous_one_is_won_or_under_UnlockAll()
        {
            var order = new List<string> { "a", "b", "c" };
            SaveStore.Load();
            Assert.IsTrue(SaveStore.IsUnlocked(order, 0), "the first level is locked");
            Assert.IsFalse(SaveStore.IsUnlocked(order, 1), "a level unlocked with nothing won");
            Assert.IsFalse(SaveStore.IsUnlocked(order, 2));
            Assert.IsFalse(SaveStore.IsUnlocked(order, -1));
            Assert.IsFalse(SaveStore.IsUnlocked(order, 3));

            SaveStore.RecordWin("a", 5f);
            Assert.IsTrue(SaveStore.IsUnlocked(order, 1), "winning a did not unlock b");
            Assert.IsFalse(SaveStore.IsUnlocked(order, 2), "winning a unlocked c");

            SaveStore.UnlockAll = true;
            Assert.IsTrue(SaveStore.IsUnlocked(order, 2), "UnlockAll left c locked");
            Assert.IsFalse(SaveStore.IsUnlocked(order, 3), "UnlockAll unlocked a level past the end");
        }

        [Test]
        public void Jouer_starts_the_first_unlocked_level_not_won()
        {
            var order = new List<string> { "a", "b", "c" };
            SaveStore.Load();
            Assert.AreEqual("a", SaveStore.FirstUnwonLevel(order), "a fresh save does not start on the first level");
            SaveStore.RecordWin("a", 5f);
            Assert.AreEqual("b", SaveStore.FirstUnwonLevel(order));
            SaveStore.RecordWin("c", 5f);
            Assert.AreEqual("b", SaveStore.FirstUnwonLevel(order), "a gap in the wins was skipped");
            SaveStore.RecordWin("b", 5f);
            Assert.AreEqual("c", SaveStore.FirstUnwonLevel(order), "every level won does not start on the last level");

            SaveStore.ResetForTests();
            SaveStore.PathOverride = Path.Combine(dir, "only_b.json");
            SaveStore.Load();
            Assert.IsEmpty(SaveStore.Current.Won, "premise: a fresh save");
            SaveStore.RecordWin("b", 5f);
            Assert.AreEqual("a", SaveStore.FirstUnwonLevel(order), "only b won: a is the first level not won");
            Assert.IsNull(SaveStore.FirstUnwonLevel(new List<string>()));
        }
    }
}
