using System;
using System.IO;
using System.Text;
using System.Threading;
using Meuble.Core;
using UnityEngine;

namespace Meuble
{
    /// <summary>How the last <see cref="SaveStore.Load"/> went (tests and the probe read it).</summary>
    public enum SaveLoadStatus
    {
        /// <summary>Load has not run since the last reset.</summary>
        None,
        /// <summary>No save file and no usable .tmp or .bak: a fresh save.</summary>
        Fresh,
        /// <summary>The save file was read.</summary>
        Loaded,
        /// <summary>
        /// The .bak was read and written back as the save file: the save file was corrupt or newer (it went to .bad),
        /// or it was missing and no usable .tmp was left.
        /// </summary>
        FromBackup,
        /// <summary>The save file and its .bak were both unusable: the file went to .bad and the save starts fresh.</summary>
        Reset,
        /// <summary>The file could not be read (an IO error): the session runs in memory and never writes.</summary>
        ReadError,
        /// <summary>
        /// The save file was missing and the .tmp of an interrupted write parsed: it was moved into place (CONTRACT_M5
        /// 17, m12). When that move fails the session plays the restored data in memory and the .tmp stays for the next run.
        /// </summary>
        FromTmp,
    }

    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 6 and 15.7, CONTRACT_M5 16.11): the save file, { "version": 1, "won": [...],
    /// "best": {...} } (<see cref="SaveData"/>). Static: Main calls <see cref="Boot"/> once at start.
    /// - Paths: only a built player run with neither --probe nor --look touches the real file
    ///   (persistentDataPath/meuble_save.json, <see cref="ChoosePath"/>). The editor and --look use
    ///   temporaryCachePath/meuble_save_test.json, --probe its shot folder; that file is deleted at boot.
    /// - Writes: the .tmp is written and flushed to disk, then File.Replace swaps it in and keeps the previous file
    ///   as .bak (3 tries, 50 ms apart); when Replace keeps failing, or there is no file yet, the target is deleted
    ///   and the .tmp moved. An IO error after all that makes the session run in memory (a warning; nothing is
    ///   overwritten from then on). Once the target is gone the .tmp is never deleted: it may hold the only copy of
    ///   the save (CONTRACT_M5 17, m12).
    /// - Reads: a parse failure, a missing or 0 version, or a version above 1 is corrupt. The .bak is tried; if it is
    ///   unusable too, the file moves to .bad (an older .bad is replaced) and the save starts fresh. A missing file is
    ///   an interrupted write (a process kill in the delete-then-move fallback, or a failed move after the target was
    ///   gone): the .tmp is tried, then the .bak, and the first that parses is restored (the .tmp is moved into place,
    ///   the .bak is written back through Save and kept), with a warning; with neither, the save starts fresh. An IO
    ///   error on read, of the file or of a .tmp or .bak tried, makes the session run in memory without ever saving,
    ///   so real progress is never overwritten.
    /// - No exception ever leaves SaveStore: every failure is a warning (a Recorded subscriber's own exception is
    ///   logged as an exception, never rethrown).
    /// </summary>
    public static class SaveStore
    {
        public const string FileName = "meuble_save.json";
        public const string TestFileName = "meuble_save_test.json";
        public const string TmpSuffix = ".tmp";
        public const string BakSuffix = ".bak";
        public const string BadSuffix = ".bad";

        /// <summary>Tests and the probe point the save at another file; null uses <see cref="DefaultPath"/>.</summary>
        public static string PathOverride;

        /// <summary>Every level unlocked (the editor and --probe).</summary>
        public static bool UnlockAll;

        /// <summary>The loaded save; never null.</summary>
        public static SaveData Current { get; private set; } = new SaveData();

        /// <summary>Raised after every <see cref="RecordWin"/> (after the save was written).</summary>
        public static event Action<RecordResult> Recorded;

        /// <summary>The session runs in memory: an IO error on read or write, nothing is written any more.</summary>
        public static bool InMemory { get; private set; }

        /// <summary>How the last load went.</summary>
        public static SaveLoadStatus LastLoad { get; private set; }

        /// <summary>The last problem met (a parse or IO error), or null.</summary>
        public static string LastProblem { get; private set; }

        /// <summary>Successful writes since the last reset (tests).</summary>
        public static int WriteCount { get; private set; }

        /// <summary>
        /// Tests only: stands in for File.Replace(source, destination, backup), to drive the delete-then-move fallback
        /// (Android, M6) and the retries. Null uses File.Replace. Cleared by <see cref="ResetForTests"/>.
        /// </summary>
        public static Action<string, string, string> ReplaceForTests;

        /// <summary>The file in use: <see cref="PathOverride"/>, or the path <see cref="ChoosePath"/> gives this run.</summary>
        public static string FilePath => PathOverride ?? DefaultPath();

        /// <summary>
        /// True when this run must never touch the real save: the editor, --probe or --look. Pure; the
        /// "the probe writes the real save" mutation lives here.
        /// </summary>
        public static bool IsTestRun(bool editor, bool probe, bool look)
        {
            if (probe) return true; // MUTATION:PROBE_REAL_SAVE
            return editor || look;
        }

        /// <summary>
        /// The save path, pure: the real one (<paramref name="persistentDir"/>/meuble_save.json) only for a built player
        /// run with neither --probe nor --look; otherwise <paramref name="tempDir"/>/meuble_save_test.json.
        /// </summary>
        public static string ChoosePath(bool editor, bool probe, bool look, string persistentDir, string tempDir)
        {
            bool test = IsTestRun(editor, probe, look);
            return Path.Combine((test ? tempDir : persistentDir) ?? string.Empty, test ? TestFileName : FileName);
        }

        /// <summary>"--look" is on the command line (the look agent's screenshots).</summary>
        public static bool LookRequested => Array.IndexOf(Environment.GetCommandLineArgs(), "--look") >= 0;

        /// <summary>The folder of this run's test save: the probe's shot folder under --probe, else temporaryCachePath.</summary>
        public static string TestDir()
        {
            if (Probe.Requested)
            {
                // The probe's own folder (Probe.Start): verify.sh checks the save lands under it (v3 15.10).
                return Probe.ArgValue("--shot") ?? Path.Combine(Application.persistentDataPath, "probe");
            }
            return Application.temporaryCachePath;
        }

        /// <summary>The path of this run when nothing overrides it (never the real file in the editor).</summary>
        public static string DefaultPath()
        {
            return ChoosePath(Application.isEditor, Probe.Requested, LookRequested, Application.persistentDataPath, TestDir());
        }

        /// <summary>
        /// Main, at boot: in the editor and under --probe or --look, the save points at the test file, which is deleted
        /// (with its .tmp, .bak and .bad) so every such run starts fresh; every level is unlocked in the editor and
        /// under --probe. A path a test injected before the boot is kept as it is, file included (a test drives a
        /// corrupt save at boot that way). Then the save is loaded.
        /// </summary>
        public static void Boot()
        {
            try
            {
                bool editor = Application.isEditor;
                bool probe = Probe.Requested;
                bool look = LookRequested;
                UnlockAll = editor || probe;
                if (PathOverride == null && IsTestRun(editor, probe, look))
                {
                    PathOverride = ChoosePath(editor, probe, look, Application.persistentDataPath, TestDir());
                    DeleteWithSiblings(PathOverride);
                }
            }
            catch (Exception e)
            {
                Warn("boot: " + e.Message);
            }
            Load();
        }

        /// <summary>Reads the save file (see the class summary). Never throws.</summary>
        public static void Load()
        {
            InMemory = false;
            LastProblem = null;
            try
            {
                LoadCore();
            }
            catch (Exception e)
            {
                // Defensive: LoadCore handles every expected failure itself.
                Current = new SaveData();
                InMemory = true;
                LastLoad = SaveLoadStatus.ReadError;
                Warn("load failed, running in memory: " + e.Message);
            }
        }

        private static void LoadCore()
        {
            string path = FilePath;
            if (!TryRead(path, out string text, out string readError))
            {
                Current = new SaveData();
                InMemory = true;
                LastLoad = SaveLoadStatus.ReadError;
                Warn($"cannot read {path} ({readError}): running in memory, nothing will be saved this session");
                return;
            }
            if (text == null)
            {
                RecoverMissing(path);
                return;
            }
            SaveData data = SaveData.Parse(text, out string problem);
            if (data != null)
            {
                Current = data;
                LastLoad = SaveLoadStatus.Loaded;
                return;
            }

            // Corrupt or newer: the .bak first.
            string bak = path + BakSuffix;
            if (!TryRead(bak, out string bakText, out string bakError))
            {
                // The backup exists but cannot be read: touch nothing, never save this session.
                Current = new SaveData();
                InMemory = true;
                LastLoad = SaveLoadStatus.ReadError;
                Warn($"{path} is unusable ({problem}) and its backup cannot be read ({bakError}): running in memory");
                return;
            }
            SaveData backup = bakText != null ? SaveData.Parse(bakText, out _) : null;

            // Either way the unusable file goes to .bad: left in place, the next File.Replace would turn it into the
            // .bak and destroy the good backup.
            if (!MoveToBad(path))
            {
                Current = backup ?? new SaveData();
                InMemory = true;
                LastLoad = SaveLoadStatus.ReadError;
                Warn($"{path} is unusable ({problem}) and cannot be set aside: running in memory");
                return;
            }
            if (backup != null)
            {
                Current = backup;
                LastLoad = SaveLoadStatus.FromBackup;
                Warn($"{path} is unusable ({problem}): restored from {bak}, the bad file is kept as {path + BadSuffix}");
                // The save file again holds the recovered data (the .bak stays as it was).
                Save();
                return;
            }
            Current = new SaveData();
            LastLoad = SaveLoadStatus.Reset;
            Warn($"{path} is unusable ({problem}) and has no usable backup: kept as {path + BadSuffix}, starting fresh");
        }

        /// <summary>
        /// The save file is missing (CONTRACT_M5 17, m12). A write interrupted once the target was gone (a process kill
        /// between the delete and the move, a move that failed, a File.Replace that set the target aside as .bak but
        /// could not move the .tmp in) leaves the newest save in the .tmp and the previous one in the .bak. The .tmp is
        /// tried first (it is always the newer of the two), then the .bak; the first that parses is restored with a
        /// warning. A .tmp or .bak that exists but cannot be read is an IO error: in memory, nothing touched.
        /// </summary>
        private static void RecoverMissing(string path)
        {
            string tmp = path + TmpSuffix;
            if (!TryRead(tmp, out string tmpText, out string tmpError))
            {
                Current = new SaveData();
                InMemory = true;
                LastLoad = SaveLoadStatus.ReadError;
                Warn($"{path} is missing and {tmp} cannot be read ({tmpError}): running in memory, nothing will be saved this session");
                return;
            }
            string tmpProblem = null;
            SaveData fromTmp = tmpText != null ? SaveData.Parse(tmpText, out tmpProblem) : null; // MUTATION:TMP_RESTORE
            if (fromTmp != null)
            {
                Current = fromTmp;
                LastLoad = SaveLoadStatus.FromTmp;
                // The .tmp already holds the data: moving it into place never truncates the only copy, as a rewrite would.
                if (!PromoteTmp(tmp, path))
                {
                    InMemory = true;
                    Warn($"{path} is missing: restored from {tmp}, which cannot be moved into place ({LastProblem}): running in memory, the .tmp is kept for the next run");
                    return;
                }
                WriteCount++;
                Warn($"{path} was missing (an interrupted write): restored from {tmp}");
                return;
            }

            string bak = path + BakSuffix;
            if (!TryRead(bak, out string bakText, out string bakError))
            {
                Current = new SaveData();
                InMemory = true;
                LastLoad = SaveLoadStatus.ReadError;
                Warn($"{path} is missing and {bak} cannot be read ({bakError}): running in memory, nothing will be saved this session");
                return;
            }
            string bakProblem = null;
            SaveData fromBak = bakText != null ? SaveData.Parse(bakText, out bakProblem) : null; // MUTATION:MISSING_BAK
            if (fromBak != null)
            {
                Current = fromBak;
                LastLoad = SaveLoadStatus.FromBackup;
                Warn(tmpText != null
                    ? $"{path} was missing and {tmp} is unusable ({tmpProblem}): restored from {bak}"
                    : $"{path} was missing (an interrupted write): restored from {bak}");
                // The save file again holds the recovered data (the .bak stays as it was).
                Save();
                return;
            }

            Current = new SaveData();
            LastLoad = SaveLoadStatus.Fresh;
            if (tmpText != null || bakText != null)
            {
                // Left in place: the next write overwrites the .tmp, and a later File.Replace the .bak.
                Warn($"{path} is missing and neither {tmp} ({tmpProblem ?? "none"}) nor {bak} ({bakProblem ?? "none"}) is usable: starting fresh");
            }
        }

        /// <summary>Moves the restored .tmp to the missing save path. False on an IO error (the .tmp is then left as it is).</summary>
        private static bool PromoteTmp(string tmp, string path)
        {
            try
            {
                File.Move(tmp, path);
                return true;
            }
            catch (Exception e)
            {
                LastProblem = e.GetType().Name + ": " + e.Message;
                return false;
            }
        }

        /// <summary>Writes <see cref="Current"/> (see the class summary). Does nothing while in memory. Never throws.</summary>
        public static void Save()
        {
            if (InMemory)
            {
                return;
            }
            string path = null;
            string tmp = null;
            try
            {
                path = FilePath;
                tmp = path + TmpSuffix;
                string dir = Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(dir))
                {
                    Directory.CreateDirectory(dir);
                }
                byte[] bytes = new UTF8Encoding(false).GetBytes(Current.ToJson());
                using (var stream = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
                {
                    stream.Write(bytes, 0, bytes.Length);
                    stream.Flush(true);
                }
                if (!TryReplace(tmp, path))
                {
                    // No file yet, or Replace kept failing (Android has no File.Replace): delete, then move.
                    if (File.Exists(path))
                    {
                        File.Delete(path);
                    }
                    File.Move(tmp, path);
                }
                WriteCount++;
            }
            catch (Exception e)
            {
                InMemory = true;
                LastProblem = e.GetType().Name + ": " + e.Message;
                Warn($"cannot write {path} ({LastProblem}): running in memory, nothing more is saved this session");
                // Once the target is gone (deleted by the fallback, or set aside as .bak by a File.Replace that failed
                // half way), the .tmp may hold the only copy of the save: it stays, and the next Load restores it
                // (CONTRACT_M5 17, m12). File.Exists is false on any error, so a doubt keeps the .tmp.
                if (File.Exists(path)) // MUTATION:TMP_KEPT
                {
                    TryDelete(tmp);
                }
            }
        }

        /// <summary>
        /// Records a win (the level joins the won list; its best time is replaced only by a strictly lower one), saves,
        /// then raises <see cref="Recorded"/>. Never throws.
        /// </summary>
        public static RecordResult RecordWin(string levelId, float seconds)
        {
            RecordResult result = default;
            try
            {
                result = Current.RecordWin(levelId, seconds);
            }
            catch (Exception e)
            {
                Warn("cannot record the win: " + e.Message);
                return result;
            }
            Save();
            Action<RecordResult> recorded = Recorded;
            if (recorded != null)
            {
                foreach (Delegate subscriber in recorded.GetInvocationList())
                {
                    try
                    {
                        ((Action<RecordResult>)subscriber)(result);
                    }
                    catch (Exception e)
                    {
                        // A subscriber's bug is logged, never thrown out of SaveStore.
                        Debug.LogException(e);
                    }
                }
            }
            return result;
        }

        /// <summary>Level index i of <paramref name="order"/> may be played: every level under UnlockAll, else the save's rule.</summary>
        public static bool IsUnlocked(System.Collections.Generic.IReadOnlyList<string> order, int index)
        {
            if (order == null || index < 0 || index >= order.Count)
            {
                return false;
            }
            return UnlockAll || Current.IsUnlocked(order, index);
        }

        /// <summary>True when the save holds a win of <paramref name="levelId"/>.</summary>
        public static bool IsWon(string levelId) => levelId != null && Current.Won != null && Current.Won.Contains(levelId);

        /// <summary>The best time of a level, or false when it has none.</summary>
        public static bool TryGetBest(string levelId, out float seconds)
        {
            seconds = 0f;
            return levelId != null && Current.Best != null && Current.Best.TryGetValue(levelId, out seconds);
        }

        /// <summary>
        /// Jouer's level: the first level of <paramref name="order"/> that is unlocked but not won (level 1 on a fresh
        /// save), or the last level when every one is won. Null for an empty order.
        /// </summary>
        public static string FirstUnwonLevel(System.Collections.Generic.IReadOnlyList<string> order)
        {
            if (order == null || order.Count == 0)
            {
                return null;
            }
            for (int i = 0; i < order.Count; i++)
            {
                if (IsUnlocked(order, i) && !IsWon(order[i]))
                {
                    return order[i];
                }
            }
            return order[order.Count - 1];
        }

        /// <summary>Clears Current, PathOverride, UnlockAll, every Recorded subscriber and every flag (every PlayMode TearDown).</summary>
        public static void ResetForTests()
        {
            Current = new SaveData();
            PathOverride = null;
            UnlockAll = false;
            Recorded = null;
            InMemory = false;
            LastLoad = SaveLoadStatus.None;
            LastProblem = null;
            WriteCount = 0;
            ReplaceForTests = null;
        }

        // ----- File helpers -----

        /// <summary>
        /// Reads a file: true with null text when it does not exist, true with its text when read, false on an IO error.
        /// </summary>
        private static bool TryRead(string path, out string text, out string error)
        {
            text = null;
            error = null;
            try
            {
                if (!File.Exists(path))
                {
                    return true;
                }
                text = File.ReadAllText(path, Encoding.UTF8);
                return true;
            }
            catch (FileNotFoundException)
            {
                return true;
            }
            catch (DirectoryNotFoundException)
            {
                return true;
            }
            catch (Exception e)
            {
                error = e.GetType().Name + ": " + e.Message;
                LastProblem = error;
                return false;
            }
        }

        /// <summary>
        /// File.Replace(tmp, path, path.bak) when the target exists, up to <see cref="Tuning.SaveReplaceTries"/> times
        /// <see cref="Tuning.SaveReplaceRetryMs"/> apart. False when there is no target, when a failed try left no target
        /// (it went to .bak), or when every try failed.
        /// </summary>
        private static bool TryReplace(string tmp, string path)
        {
            if (!File.Exists(path))
            {
                return false;
            }
            for (int attempt = 1; attempt <= Tuning.SaveReplaceTries; attempt++)
            {
                try
                {
                    if (ReplaceForTests != null)
                    {
                        ReplaceForTests(tmp, path, path + BakSuffix);
                    }
                    else
                    {
                        File.Replace(tmp, path, path + BakSuffix);
                    }
                    return true;
                }
                catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
                {
                    // A transient lock (an antivirus, a backup tool): wait, then try again.
                    LastProblem = e.GetType().Name + ": " + e.Message;
                    if (!File.Exists(path))
                    {
                        // File.Replace set the target aside as .bak but could not move the .tmp in: nothing is left to
                        // replace, the move of the fallback finishes the write.
                        return false;
                    }
                    if (attempt < Tuning.SaveReplaceTries)
                    {
                        Thread.Sleep(Tuning.SaveReplaceRetryMs);
                    }
                }
                catch (Exception e)
                {
                    // Not supported on this platform (Android): no point in trying again.
                    LastProblem = e.GetType().Name + ": " + e.Message;
                    return false;
                }
            }
            return false;
        }

        /// <summary>Moves an unusable save to .bad, replacing an older .bad. False on an IO error.</summary>
        private static bool MoveToBad(string path)
        {
            try
            {
                string bad = path + BadSuffix;
                if (File.Exists(bad))
                {
                    File.Delete(bad);
                }
                File.Move(path, bad);
                return true;
            }
            catch (Exception e)
            {
                LastProblem = e.GetType().Name + ": " + e.Message;
                return false;
            }
        }

        private static void DeleteWithSiblings(string path)
        {
            TryDelete(path);
            TryDelete(path + TmpSuffix);
            TryDelete(path + BakSuffix);
            TryDelete(path + BadSuffix);
        }

        private static void TryDelete(string path)
        {
            if (string.IsNullOrEmpty(path))
            {
                return;
            }
            try
            {
                if (File.Exists(path))
                {
                    File.Delete(path);
                }
            }
            catch (Exception e)
            {
                Warn($"cannot delete {path}: {e.Message}");
            }
        }

        private static void Warn(string message)
        {
            Debug.LogWarning("[SaveStore] " + message);
        }
    }
}
