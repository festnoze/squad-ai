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

        // ----- Levels v2: the order migration (docs/levels_v2/LEVELS_V2.md 7) -----

        /// <summary>The rev 2 play order (22 levels), shipped until ACT3A reordered act 3 (levels.json rev 3).</summary>
        private static readonly string[] Rev2Order =
        {
            "level1", "level2", "level3", "level4", "level5", "level6", "level7",
            "level8", "level9", "level12", "level11", "level15", "level13", "level14", "level18", "level17",
            "level19", "level21", "level20", "level22", "level25", "level24",
        };

        /// <summary>
        /// The v2 manifest the worked cases of section 7 are written for: rev 2, the 24 v1 ids as previous, the rev 2 order and
        /// its acts. levels.json moved on to rev 3 (ACT3A), so this one is built here and handed to the store through
        /// <see cref="SaveStore.ManifestOverride"/> (set again after every <see cref="SaveStore.ResetForTests"/>): the cases
        /// keep checking the v1 to v2 migration exactly as shipped.
        /// </summary>
        private static ManifestDef V2Manifest()
        {
            var m = new ManifestDef { Rev = 2, Levels = new List<string>(Rev2Order), Previous = Levels(1, 24) };
            m.Acts.Add(new ActDef { From = 0, NameKey = "act1.name" });
            m.Acts.Add(new ActDef { From = 7, NameKey = "act2.name" });
            m.Acts.Add(new ActDef { From = 16, NameKey = "act3.name" });
            SaveStore.ManifestOverride = m;
            Assert.AreEqual(2, m.Rev, "premise: the v2 order (rev 2)");
            Assert.AreEqual(24, m.Previous.Count, "premise: previous lists the 24 v1 ids");
            for (int n = 1; n <= 24; n++)
            {
                Assert.AreEqual("level" + n, m.Previous[n - 1], "premise: previous is the v1 order");
            }
            // The relative order the worked cases rely on (LV12 may still insert level25 before level24).
            string[] chain = { "level9", "level12", "level11", "level15", "level13", "level14", "level18", "level17", "level19", "level21", "level20" };
            for (int k = 1; k < chain.Length; k++)
            {
                Assert.AreEqual(m.Levels.IndexOf(chain[k - 1]) + 1, m.Levels.IndexOf(chain[k]), $"premise: {chain[k]} follows {chain[k - 1]} in the v2 order");
            }
            foreach (string cut in new[] { "level10", "level16", "level23" })
            {
                CollectionAssert.DoesNotContain(m.Levels, cut, "premise: the cut levels are not listed");
            }
            return m;
        }

        /// <summary>
        /// The shipped manifest's own consistency (LEVELS_V2.md 7): every listed level and every act start is distinct and
        /// inside the order, the acts start at 0 and climb, and each act name resolves in Strings in both languages.
        /// </summary>
        [Test]
        public void Manifest_v2_acts_and_lists_are_consistent()
        {
            ManifestDef m = LevelLoader.LoadManifestDef();
            Assert.GreaterOrEqual(m.Rev, 2, "premise: levels.json is a v2 manifest (rev 2 or later)");
            Assert.AreEqual(m.Levels.Count, new HashSet<string>(m.Levels).Count, "a level is listed twice in the play order");
            Assert.AreEqual(m.Previous.Count, new HashSet<string>(m.Previous).Count, "a level is listed twice in previous");
            Assert.GreaterOrEqual(m.Acts.Count, 1, "the manifest has no act");
            Assert.AreEqual(0, m.Acts[0].From, "the first act does not start at the first level");
            for (int a = 0; a < m.Acts.Count; a++)
            {
                ActDef act = m.Acts[a];
                Assert.IsNotNull(act, $"act {a + 1} is null");
                Assert.That(act.From, Is.InRange(0, m.Levels.Count - 1), $"act {a + 1} starts outside the play order");
                if (a > 0)
                {
                    Assert.Greater(act.From, m.Acts[a - 1].From, $"act {a + 1} does not start after act {a}");
                }
                Assert.IsFalse(string.IsNullOrEmpty(act.NameKey), $"act {a + 1} has no name key");
                foreach (string language in new[] { Strings.French, Strings.English })
                {
                    Assert.AreNotEqual(act.NameKey, Strings.Get(act.NameKey, language), $"Strings has no {act.NameKey} in {language}");
                }
            }
        }

        private static List<string> Levels(int from, int to)
        {
            var ids = new List<string>();
            for (int n = from; n <= to; n++)
            {
                ids.Add("level" + n);
            }
            return ids;
        }

        /// <summary>A v1 save (no "order", no "unlocked") with these wins.</summary>
        private static string V1Save(List<string> won) => Json(1, won.Count == 0 ? "" : "\"" + string.Join("\", \"", won) + "\"", "");

        private static void AssertPlayable(ManifestDef m, string id, bool expected, string why)
        {
            int i = m.Levels.IndexOf(id);
            Assert.GreaterOrEqual(i, 0, $"premise: {id} is listed");
            Assert.AreEqual(expected, SaveStore.IsUnlocked(m.Levels, i), $"{id}: {why}");
        }

        private static Regex MigratedLog(int rev, int added) =>
            new Regex("^" + Regex.Escape($"[SaveStore] progress migrated to order rev {rev}: +{added} unlocked") + "$");

        /// <summary>
        /// Worked case 1: won level1 to level10. level12 (slot 10) opens after level9, level11 opens through Unlocked (its v1
        /// predecessor level10 is won), level15 stays locked. The mutation killer of MIGRATE_PREDECESSOR (with "j" for "j -
        /// 1" nothing joins Unlocked) and of UNLOCK_MIGRATED (level11 stays locked).
        /// </summary>
        [Test]
        public void Migration_case1_won_level1_to_level10_opens_level12_and_level11()
        {
            ManifestDef m = V2Manifest();
            List<string> won = Levels(1, 10);
            File.WriteAllText(path, V1Save(won));
            LogAssert.Expect(LogType.Log, MigratedLog(2, 1));

            SaveStore.Load();
            Assert.AreEqual(SaveLoadStatus.Loaded, SaveStore.LastLoad, "premise: the v1 save loads");
            Assert.AreEqual(2, SaveStore.Current.Order, "the save was not migrated to rev 2");
            CollectionAssert.AreEqual(new[] { "level11" }, SaveStore.Current.Unlocked, "the migration opened the wrong levels");
            CollectionAssert.AreEqual(won, SaveStore.Current.Won, "the migration changed Won");
            Assert.AreEqual(1, SaveStore.WriteCount, "the migrated save was not written once");
            SaveData disk = ReadBack(path);
            Assert.AreEqual(2, disk.Order, "the migration is not on disk");
            CollectionAssert.AreEqual(new[] { "level11" }, disk.Unlocked);
            Assert.AreEqual(SaveData.CurrentVersion, disk.Version, "the save version must stay 1");

            for (int n = 1; n <= 9; n++)
            {
                AssertPlayable(m, "level" + n, true, "a won level is locked");
            }
            AssertPlayable(m, "level12", true, "slot 10 does not open after level9");
            AssertPlayable(m, "level11", true, "level11 (playable in v1: level10 won) does not open through Unlocked");
            AssertPlayable(m, "level15", false, "level15 opened (level11 not won, never playable in v1)");
            AssertPlayable(m, "level13", false, "level13 opened");
            AssertPlayable(m, "level14", false, "level14 opened");
            Assert.AreEqual("level12", SaveStore.FirstUnwonLevel(m.Levels), "Jouer does not start the first unwon playable level");
        }

        /// <summary>
        /// Worked case 2: won level1 to level17 (not level18). level18 opens after level14, level17 is won and stays open
        /// although level18 (its new predecessor) is not won, level19 opens after level17. The mutation killer of
        /// UNLOCK_WON (level17 is not in Unlocked: only its win opens it).
        /// </summary>
        [Test]
        public void Migration_case2_won_level1_to_level17_keeps_level17_open_after_level18()
        {
            ManifestDef m = V2Manifest();
            List<string> won = Levels(1, 17);
            File.WriteAllText(path, V1Save(won));
            LogAssert.Expect(LogType.Log, MigratedLog(2, 1));

            SaveStore.Load();
            Assert.AreEqual(2, SaveStore.Current.Order);
            CollectionAssert.AreEqual(new[] { "level18" }, SaveStore.Current.Unlocked);
            CollectionAssert.DoesNotContain(SaveStore.Current.Unlocked, "level17", "premise: level17 is open only through its win");
            CollectionAssert.DoesNotContain(SaveStore.Current.Won, "level18", "premise: level18 is not won");

            AssertPlayable(m, "level18", true, "level18 does not open after level14");
            AssertPlayable(m, "level17", true, "a won level locked behind the unwon level18");
            AssertPlayable(m, "level19", true, "level19 does not open after the won level17");
            AssertPlayable(m, "level21", false, "level21 opened (level19 not won)");
            AssertPlayable(m, "level20", false, "level20 opened");
            AssertPlayable(m, "level22", false, "level22 opened");
            AssertPlayable(m, "level24", false, "level24 opened");
            Assert.AreEqual("level18", SaveStore.FirstUnwonLevel(m.Levels));
        }

        /// <summary>Worked case 3: a fresh save opens only level1, starts at rev 2 and never migrates, even once written.</summary>
        [Test]
        public void Migration_case3_a_fresh_save_opens_only_level1_and_never_migrates()
        {
            ManifestDef m = V2Manifest();
            var logs = new List<string>();
            Application.LogCallback onLog = (condition, stack, type) => logs.Add(condition);
            Application.logMessageReceived += onLog;
            try
            {
                SaveStore.Load();
                Assert.AreEqual(SaveLoadStatus.Fresh, SaveStore.LastLoad);
                Assert.AreEqual(2, SaveStore.Current.Order, "a fresh save does not start at the manifest's revision");
                Assert.IsEmpty(SaveStore.Current.Unlocked);
                Assert.IsEmpty(Directory.GetFiles(dir), "loading a missing save wrote something");
                Assert.IsTrue(SaveStore.IsUnlocked(m.Levels, 0), "level1 is locked on a fresh save");
                for (int i = 1; i < m.Levels.Count; i++)
                {
                    Assert.IsFalse(SaveStore.IsUnlocked(m.Levels, i), $"{m.Levels[i]} is open on a fresh save");
                }
                Assert.AreEqual("level1", SaveStore.FirstUnwonLevel(m.Levels));

                // Its first write holds the revision, so the next load has nothing to migrate.
                SaveStore.RecordWin("level1", 9f);
                Assert.AreEqual(2, ReadBack(path).Order, "a fresh save was written without its revision");
                SaveStore.ResetForTests();
                SaveStore.PathOverride = path;
                SaveStore.ManifestOverride = m;
                SaveStore.Load();
                Assert.AreEqual(0, SaveStore.WriteCount, "loading a rev 2 save wrote it");
                Assert.IsEmpty(SaveStore.Current.Unlocked, "a rev 2 save was migrated");
            }
            finally
            {
                Application.logMessageReceived -= onLog;
            }
            Assert.IsFalse(logs.Exists(l => l.Contains("progress migrated")), "a fresh save ran the migration: " + string.Join(" | ", logs));
        }

        /// <summary>Worked case 4: a migrated save loaded again changes nothing and writes nothing.</summary>
        [Test]
        public void Migration_case4_a_migrated_save_loaded_again_changes_nothing_and_writes_nothing()
        {
            ManifestDef m = V2Manifest();
            File.WriteAllText(path, V1Save(Levels(1, 10)));
            LogAssert.Expect(LogType.Log, MigratedLog(2, 1));
            SaveStore.Load();
            Assert.AreEqual(1, SaveStore.WriteCount, "premise: the first load migrated and wrote the save");
            string migrated = File.ReadAllText(path);
            string bak = File.ReadAllText(path + SaveStore.BakSuffix);

            var logs = new List<string>();
            Application.LogCallback onLog = (condition, stack, type) => logs.Add(condition);
            SaveStore.ResetForTests();
            SaveStore.PathOverride = path;
            SaveStore.ManifestOverride = m;
            Application.logMessageReceived += onLog;
            try
            {
                SaveStore.Load();
            }
            finally
            {
                Application.logMessageReceived -= onLog;
            }
            Assert.AreEqual(SaveLoadStatus.Loaded, SaveStore.LastLoad);
            Assert.AreEqual(0, SaveStore.WriteCount, "a migrated save was written again");
            Assert.AreEqual(migrated, File.ReadAllText(path), "a migrated save changed on the second load");
            Assert.AreEqual(bak, File.ReadAllText(path + SaveStore.BakSuffix), "the .bak changed on the second load");
            CollectionAssert.AreEqual(new[] { "level11" }, SaveStore.Current.Unlocked);
            Assert.AreEqual(2, SaveStore.Current.Order);
            Assert.IsFalse(logs.Exists(l => l.Contains("progress migrated")), "the migration ran twice: " + string.Join(" | ", logs));
        }

        /// <summary>A save already migrated to rev 2 ("order": 2) with these wins.</summary>
        /// <summary>The rev 3 manifest (ACT3A) as shipped until rev 4 swapped cards 4 and 11; handed to the store.</summary>
        private static ManifestDef Rev3Manifest()
        {
            var m = new ManifestDef
            {
                Rev = 3,
                Levels = new List<string>
                {
                    "level1", "level2", "level3", "level4", "level5", "level6", "level7",
                    "level8", "level9", "level12", "level11", "level15", "level13", "level14", "level18", "level17",
                    "level25", "level19", "level22", "level24",
                },
                Previous = new List<string>(Rev2Order),
            };
            m.Acts.Add(new ActDef { From = 0, NameKey = "act1.name" });
            m.Acts.Add(new ActDef { From = 7, NameKey = "act2.name" });
            m.Acts.Add(new ActDef { From = 16, NameKey = "act3.name" });
            SaveStore.ManifestOverride = m;
            return m;
        }

        private static string Rev2Save(IEnumerable<string> won) =>
            "{ \"version\": 1, \"order\": 2, \"won\": [\"" + string.Join("\", \"", won) + "\"] }";

        /// <summary>
        /// ACT3A (levels.json rev 3, previous = the rev 2 order): act 3 now opens on level25, then level19, level22 and the
        /// finale level24; level21 and level20 are parked. A rev 2 save that won the first 16 cards (up to level17) could play
        /// level19 next; after the migration level19 stays open through Unlocked although its new predecessor level25 is not
        /// won, level25 opens after level17, and Jouer starts the new opener. A rev 2 save deep into act 3 (level19 and level21
        /// won) loses nothing either: level22 opens after level19, and the parked level20 never joins Unlocked.
        /// </summary>
        [Test]
        public void Migration_rev3_a_rev2_save_keeps_its_next_level_open_after_the_act3_reorder()
        {
            // levels.json moved on to rev 4 (cards 4 and 11 swapped, 2026-11-24), so the rev 3 manifest is built here.
            ManifestDef m = Rev3Manifest();
            Assert.AreEqual(3, m.Rev, "premise: the rev 3 manifest");
            CollectionAssert.AreEqual(Rev2Order, m.Previous, "premise: previous is the rev 2 order");
            CollectionAssert.AreEqual(new[] { "level25", "level19", "level22", "level24" }, m.Levels.GetRange(16, m.Levels.Count - 16),
                "premise: the rev 3 act 3");
            List<string> won = new List<string>(Rev2Order).GetRange(0, 16);
            File.WriteAllText(path, Rev2Save(won));
            LogAssert.Expect(LogType.Log, MigratedLog(3, 1));

            SaveStore.Load();
            Assert.AreEqual(SaveLoadStatus.Loaded, SaveStore.LastLoad, "premise: the rev 2 save loads");
            Assert.AreEqual(3, SaveStore.Current.Order, "the save was not migrated to rev 3");
            CollectionAssert.AreEqual(new[] { "level19" }, SaveStore.Current.Unlocked, "the migration opened the wrong levels");
            CollectionAssert.AreEqual(won, SaveStore.Current.Won, "the migration changed Won");
            Assert.AreEqual(3, ReadBack(path).Order, "the migration is not on disk");
            AssertPlayable(m, "level25", true, "the new act 3 opener does not open after level17");
            AssertPlayable(m, "level19", true, "level19 (playable in rev 2) is locked behind the unwon level25");
            AssertPlayable(m, "level22", false, "level22 opened (level19 not won)");
            AssertPlayable(m, "level24", false, "the finale opened");
            Assert.AreEqual("level25", SaveStore.FirstUnwonLevel(m.Levels), "Jouer does not start the new act 3 opener");

            SaveStore.ResetForTests();
            SaveStore.ManifestOverride = m;
            string deep = Path.Combine(dir, "deep.json");
            SaveStore.PathOverride = deep;
            List<string> deepWon = new List<string>(Rev2Order).GetRange(0, 18);
            File.WriteAllText(deep, Rev2Save(deepWon));
            LogAssert.Expect(LogType.Log, MigratedLog(3, 0));
            SaveStore.Load();
            Assert.AreEqual(3, SaveStore.Current.Order);
            Assert.IsEmpty(SaveStore.Current.Unlocked, "the parked level20 (playable in rev 2) joined Unlocked");
            AssertPlayable(m, "level25", true, "level25 does not open after level17");
            AssertPlayable(m, "level22", true, "level22 does not open after the won level19");
            AssertPlayable(m, "level24", false, "the finale opened before level22 was won");
        }

        [Test]
        public void Unlocked_of_the_wrong_type_is_a_parse_problem_like_won()
        {
            Assert.IsNull(SaveData.Parse("{ \"version\": 1, \"unlocked\": \"level11\" }", out string problem), "a string unlocked was accepted");
            Assert.AreEqual("unlocked is not a list", problem);
            Assert.IsNull(SaveData.Parse("{ \"version\": 1, \"unlocked\": { \"level11\": true } }", out problem), "an object unlocked was accepted");
            Assert.AreEqual("unlocked is not a list", problem);
            Assert.IsNull(SaveData.Parse("{ \"version\": 1, \"unlocked\": [\"level11\", 3] }", out problem), "a number in unlocked was accepted");
            StringAssert.StartsWith("unlocked holds a", problem);

            SaveData missing = SaveData.Parse("{ \"version\": 1 }", out problem);
            Assert.IsNotNull(missing, problem);
            Assert.IsEmpty(missing.Unlocked, "a missing unlocked is not empty");
            SaveData nulls = SaveData.Parse("{ \"version\": 1, \"unlocked\": null }", out problem);
            Assert.IsNotNull(nulls, problem);
            Assert.IsEmpty(nulls.Unlocked);
            SaveData twice = SaveData.Parse("{ \"version\": 1, \"unlocked\": [\"level11\", \"level11\", \"\"] }", out problem);
            Assert.IsNotNull(twice, problem);
            CollectionAssert.AreEqual(new[] { "level11" }, twice.Unlocked, "an id listed twice (or an empty one) was kept");

            // Through the store: a wrong-typed unlocked is a corrupt save (set aside as .bad, the .bak is tried).
            string bad = "{ \"version\": 1, \"won\": [\"level1\"], \"unlocked\": 7 }";
            File.WriteAllText(path, bad);
            Assert.DoesNotThrow(SaveStore.Load);
            Assert.AreEqual(SaveLoadStatus.Reset, SaveStore.LastLoad, "a wrong-typed unlocked was loaded");
            Assert.AreEqual(bad, File.ReadAllText(path + SaveStore.BadSuffix));
            Assert.IsEmpty(SaveStore.Current.Won);
        }

        [Test]
        public void Order_missing_or_malformed_reads_as_1_and_round_trips()
        {
            foreach (string order in new[] { null, "0", "-3", "\"2\"", "2.5", "null", "true", "99999999999" })
            {
                string json = order == null ? "{ \"version\": 1 }" : "{ \"version\": 1, \"order\": " + order + " }";
                SaveData data = SaveData.Parse(json, out string problem);
                Assert.IsNotNull(data, $"order {order ?? "missing"} failed the save: {problem}");
                Assert.AreEqual(1, data.Order, $"order {order ?? "missing"} does not read as 1");
            }
            SaveData three = SaveData.Parse("{ \"version\": 1, \"order\": 3 }", out string p);
            Assert.IsNotNull(three, p);
            Assert.AreEqual(3, three.Order);

            var save = new SaveData { Order = 2 };
            save.Unlocked.Add("level11");
            save.RecordWin("level1", 4f);
            string text = save.ToJson();
            StringAssert.Contains("\"order\": 2", text);
            StringAssert.Contains("\"unlocked\"", text);
            StringAssert.Contains("\"version\": 1", text, "the save version must stay 1");
            SaveData back = SaveData.Parse(text, out p);
            Assert.IsNotNull(back, p);
            Assert.AreEqual(2, back.Order);
            CollectionAssert.AreEqual(new[] { "level11" }, back.Unlocked);
            CollectionAssert.AreEqual(new[] { "level1" }, back.Won);
        }

        /// <summary>The migration only ever adds to Unlocked: Won and Best (cut levels and old record keys included) stay.</summary>
        [Test]
        public void MigrateOrder_never_shrinks_Won_or_Best_and_runs_once()
        {
            ManifestDef m = V2Manifest();
            var save = new SaveData();
            save.Won.AddRange(Levels(1, 10));
            save.Won.Add("level16");
            save.Won.Add("level23");
            save.Best["level1"] = 5f;
            save.Best["level10"] = 9f;
            save.Best["level16@difficile"] = 3f;
            save.Best["level6~1"] = 4f;
            var wonBefore = new List<string>(save.Won);
            var bestBefore = new Dictionary<string, float>(save.Best);
            Assert.AreEqual(1, save.Order, "premise: a save without order is rev 1");

            Assert.IsTrue(save.MigrateOrder(m.Rev, m.Previous, m.Levels), "the first migration reported no change");
            CollectionAssert.AreEqual(wonBefore, save.Won, "the migration changed Won");
            CollectionAssert.AreEquivalent(bestBefore, save.Best, "the migration changed Best");
            Assert.AreEqual(2, save.Order);
            // level11 (after level10) and level17 (after level16) were playable in v1; level17 is listed, level24 after
            // level23 too; the cut level10, level16 and level23 never join (not listed).
            CollectionAssert.AreEquivalent(new[] { "level11", "level17", "level24" }, save.Unlocked);

            var unlockedBefore = new List<string>(save.Unlocked);
            Assert.IsFalse(save.MigrateOrder(m.Rev, m.Previous, m.Levels), "a second migration reported a change");
            CollectionAssert.AreEqual(unlockedBefore, save.Unlocked, "a second migration changed Unlocked");
            Assert.IsFalse(new SaveData().MigrateOrder(1, m.Previous, m.Levels), "a rev 1 save migrated to rev 1");
            Assert.IsFalse(new SaveData { Order = 3 }.MigrateOrder(2, m.Previous, m.Levels), "a newer save was migrated back");
        }

        /// <summary>MigrateOrder on small lists: the previous rule (index 0 or the predecessor in previous won), listed ids only.</summary>
        [Test]
        public void MigrateOrder_opens_what_the_previous_order_opened_and_is_still_listed()
        {
            var previous = new List<string> { "a", "b", "c", "x", "d" };
            var current = new List<string> { "a", "d", "b", "c", "e" };
            var save = new SaveData();
            save.Won.Add("a");
            save.Won.Add("c");
            Assert.IsFalse(save.IsUnlocked(current, 2), "premise: b (after the unwon d) is locked before the migration");
            Assert.IsTrue(save.MigrateOrder(2, previous, current));
            // a: won (skipped); b: after the won a; c: won (skipped); x: after the won c but not listed; d: after x, not won.
            CollectionAssert.AreEqual(new[] { "b" }, save.Unlocked);
            Assert.IsTrue(save.IsUnlocked(current, 2), "b, playable in the previous order, is locked behind the unwon d");

            var fresh = new SaveData();
            Assert.IsTrue(fresh.MigrateOrder(2, previous, current));
            CollectionAssert.AreEqual(new[] { "a" }, fresh.Unlocked, "index 0 of the previous order is the only level a v1 save with no win could play");
            Assert.IsTrue(new SaveData().MigrateOrder(2, null, current), "a manifest without previous still stamps the revision");
        }
    }
}
