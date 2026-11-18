using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M5 probe step 41 (docs/CONTRACT_M5_v3.md 6, 15.7 and 15.10, CONTRACT_M5 16.10): the level select and the save,
    /// on the real Boot scene. Wins are real: every inhabitant is pinned far outside the house, the chair waits a chosen
    /// number of fixed steps (the win time), then is teleported onto the doormat and the game's own exit rule wins.
    /// Locking is tested with <see cref="SaveStore.UnlockAll"/> off (the editor turns it on at boot). Every wait counts
    /// fixed steps (WaitForFixedUpdate keeps running while the game is paused), and every scenario asserts its premise.
    /// </summary>
    public sealed class ProbeTestsM5Ui
    {
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private readonly List<string> tempDirs = new List<string>();

        private Main main;
        private GameState Game => main.Game;
        private Menu Menu => main.Menu;
        private Hud Hud => main.Hud;
        private LevelSelect Select => main.Menu.LevelSelect;
        private RecordLine Record => main.Menu.RecordLine;
        private FurnitureController Chair => Game.Furniture;
        private IReadOnlyList<string> Order => Game.LevelOrder;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            tempDirs.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            yield return WaitForMain(null);
            Assert.IsNotNull(Menu, "premise: Main built no Menu");
            Assert.IsNotNull(Select, "premise: the Menu built no level select");
            Assert.IsNotNull(Record, "premise: the Menu built no record line");
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            Cursor.lockState = CursorLockMode.None;
            foreach (string dir in tempDirs)
            {
                try
                {
                    Directory.Delete(dir, true);
                }
                catch (Exception)
                {
                    // A leftover temporary folder is harmless.
                }
            }
            yield return null;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        private IEnumerator WaitForMain(Main previous)
        {
            int guard = 0;
            while ((Main.Instance == null || Main.Instance == previous || Main.Instance.Game == null || Main.Instance.Game.Level == null)
                && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.AreNotSame(previous, main, "the Boot scene was not reloaded");
            Assert.IsNotNull(Game.Level, "the level was never built");
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static IEnumerator Until(Func<bool> until, int maxSteps)
        {
            for (int i = 0; i < maxSteps && !until(); i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static GameObject Selected => EventSystem.current != null ? EventSystem.current.currentSelectedGameObject : null;

        private string NewTempDir()
        {
            string dir = Path.Combine(Path.GetTempPath(), "outofsight_ui_tests_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            tempDirs.Add(dir);
            return dir;
        }

        /// <summary>
        /// A real win of the current level: every inhabitant pinned far outside the house (nobody sees anything), the
        /// chair still for <paramref name="waitSteps"/> fixed steps, then onto the doormat; the exit rule wins.
        /// </summary>
        private IEnumerator WinNow(int waitSteps)
        {
            Assert.AreEqual(PlayState.Playing, Game.State, $"premise: {Game.LevelId} is not being played");
            Assert.IsFalse(Game.Paused, "premise: the game is paused");
            for (int i = 0; i < Game.Level.Inhabitants.Count; i++)
            {
                Game.Level.Inhabitants[i].Pin(new Vector3(90f + 5f * i, 0f, 90f), 0f);
            }
            yield return Steps(waitSteps);
            ZoneDef exit = Game.Def.Exit;
            Chair.Teleport(new Vector3(exit.X, 0f, exit.Z), Chair.Yaw);
            yield return Until(() => Game.State != PlayState.Playing, 20);
            Assert.AreEqual(PlayState.Won, Game.State, $"premise: {Game.LevelId} was not won");
        }

        private void OpenSelect()
        {
            if (!Menu.TitleOpen)
            {
                Menu.ShowTitle();
            }
            Menu.LevelsButton.onClick.Invoke();
            Assert.IsTrue(Menu.LevelSelectOpen, "Niveaux did not open the level select");
            Assert.IsTrue(Select.IsOpen);
        }

        private static string Seconds(float seconds) => Strings.FormatSeconds(seconds);

        private static SaveData ReadSaveFile()
        {
            string file = SaveStore.FilePath;
            Assert.IsTrue(File.Exists(file), $"no save file at {file}");
            SaveData data = SaveData.Parse(File.ReadAllText(file), out string problem);
            Assert.IsNotNull(data, $"the save file does not parse: {problem}");
            return data;
        }

        private static readonly Vector3[] Corners = new Vector3[4];

        /// <summary>The screen rect of a Screen Space Overlay element (its world corners are pixels).</summary>
        private static Rect ScreenRect(RectTransform rect)
        {
            rect.GetWorldCorners(Corners);
            return Rect.MinMaxRect(Corners[0].x, Corners[0].y, Corners[2].x, Corners[2].y);
        }

        private void AssertNoOverlap(RectTransform mine, string what, params (string name, RectTransform rect)[] others)
        {
            Rect r = ScreenRect(mine);
            Assert.Greater(r.width, 1f, $"premise: the {what} has no size");
            Assert.IsTrue(r.yMin >= 0f && r.yMax <= Screen.height && r.xMin >= 0f && r.xMax <= Screen.width,
                $"the {what} {r} leaves the screen ({Screen.width} x {Screen.height})");
            foreach ((string name, RectTransform rect) in others)
            {
                Assert.IsNotNull(rect, $"premise: {name} missing");
                Rect o = ScreenRect(rect);
                Assert.IsFalse(r.Overlaps(o), $"the {what} {r} overlaps {name} {o}");
            }
        }

        private RectTransform HudLabel(string name)
        {
            Assert.IsTrue(Hud.Labels.TryGetValue(name, out Text text), $"premise: HUD label {name} missing");
            return text.rectTransform;
        }

        // ----- 41: the cards -----

        [UnityTest]
        public IEnumerator Step41_CardsFollowTheLevelOrder()
        {
            Assert.GreaterOrEqual(Order.Count, 2, "premise: levels.json lists at least two levels");
            Assert.IsNotNull(Menu.LevelsButton, "the title has no Niveaux button");
            Assert.IsTrue(Menu.Labels.TryGetValue("LevelsLabel", out Text levels) && levels.text == Strings.TitleLevels, "Niveaux label");
            Menu.ShowTitle();
            Assert.IsTrue(Menu.TitlePageShown, "premise: the title page shows");

            // Niveaux sits between Jouer and Quitter, on screen and in the keyboard order.
            float play = ((RectTransform)Menu.PlayButton.transform).anchoredPosition.y;
            float middle = ((RectTransform)Menu.LevelsButton.transform).anchoredPosition.y;
            float quit = ((RectTransform)Menu.QuitButton.transform).anchoredPosition.y;
            Assert.IsTrue(play > middle && middle > quit, $"Niveaux is not between Jouer and Quitter ({play}, {middle}, {quit})");
            Assert.AreEqual(Menu.LevelsButton, Menu.PlayButton.navigation.selectOnDown, "down from Jouer is not Niveaux");
            // M7: Options sits between Niveaux and Quitter, so Quitter is last.
            Assert.AreEqual(Menu.TitleOptionsButton, Menu.LevelsButton.navigation.selectOnDown, "down from Niveaux is not Options");
            Assert.AreEqual(Menu.QuitButton, Menu.TitleOptionsButton.navigation.selectOnDown, "down from Options is not Quitter");
            Assert.AreEqual(Menu.PlayButton, Menu.LevelsButton.navigation.selectOnUp);

            OpenSelect();
            // One rendered frame: the canvas lays the cards out.
            yield return null;
            Assert.IsTrue(Menu.TitleOpen, "the level select closed the title (the game would run under it)");
            Assert.IsFalse(Menu.TitlePageShown, "the title page shows under the level select");
            Assert.IsTrue(Game.Paused, "the game runs under the level select");
            Assert.IsFalse(Hud.Visible, "the HUD shows under the level select");
            Assert.IsTrue(Menu.Labels.TryGetValue("SelectTitle", out Text header) && header.text == Strings.TitleLevels, "the select's title");
            Assert.IsTrue(Menu.Labels.TryGetValue("SelectBackLabel", out Text back) && back.text == Strings.SelectBack, "Retour label");

            Assert.AreEqual(Order.Count, Select.CardCount, "one card per entry of levels.json");
            Rect screen = Rect.MinMaxRect(0f, 0f, Screen.width, Screen.height);
            var rects = new List<Rect>();
            for (int i = 0; i < Order.Count; i++)
            {
                LevelSelect.Card card = Select.Cards[i];
                Assert.AreEqual(Order[i], card.LevelId, $"card {i + 1} is not level {Order[i]}");
                Assert.AreEqual((i + 1).ToString(), card.Number.text, $"card {i + 1} number");
                string key = Order[i] + ".name";
                Assert.AreNotEqual(key, Strings.Get(key), $"premise: Strings has no {key}");
                Assert.AreEqual(Strings.Get(key), card.Name.text, $"card {i + 1} name");
                Assert.IsTrue(card.Best.enabled, $"card {i + 1}: no best time line (UnlockAll in the editor)");
                Assert.AreEqual(Strings.SelectNone, card.Best.text, $"card {i + 1}: a fresh save shows a best time");
                Rect r = ScreenRect((RectTransform)card.Button.transform);
                Assert.IsTrue(screen.Contains(r.min) && screen.Contains(r.max), $"card {i + 1} {r} leaves the screen");
                foreach (Rect other in rects)
                {
                    Assert.IsFalse(r.Overlaps(other), $"card {i + 1} {r} overlaps another card {other}");
                }
                rects.Add(r);
                if (i > 0)
                {
                    bool sameRow = i % Tuning.LevelSelectColumns != 0;
                    Rect previous = rects[i - 1];
                    Assert.IsTrue(sameRow ? r.center.x > previous.center.x : r.center.y < previous.center.y,
                        $"card {i + 1} is not laid out in rows of {Tuning.LevelSelectColumns}");
                }
            }
            Rect backRect = ScreenRect((RectTransform)Select.BackButton.transform);
            foreach (Rect r in rects)
            {
                Assert.IsFalse(r.Overlaps(backRect), "a card overlaps Retour");
            }
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Locking and unlocking through real wins; the mutation killer of "a locked level is playable" (LevelSelect,
        /// MUTATION:LOCKED_PLAYABLE).
        /// </summary>
        [UnityTest]
        public IEnumerator Step41_LockedLevelsUnlockThroughRealWins()
        {
            Assert.GreaterOrEqual(Order.Count, 3, "premise: levels.json lists at least three levels");
            Assert.IsEmpty(SaveStore.Current.Won, "premise: the boot did not start on a fresh save");
            SaveStore.UnlockAll = false;

            OpenSelect();
            Assert.IsTrue(Select.IsPlayable(0), "the first level is locked on a fresh save");
            Assert.IsTrue(Select.Cards[0].Button.interactable);
            for (int i = 1; i < Order.Count; i++)
            {
                LevelSelect.Card card = Select.Cards[i];
                Assert.IsFalse(Select.IsPlayable(i), $"level {i + 1} is playable on a fresh save");
                Assert.IsFalse(card.Button.interactable, $"card {i + 1} is interactable while locked");
                Assert.IsTrue(card.Locked.enabled, $"card {i + 1} does not say it is locked");
                Assert.AreEqual(Strings.SelectLocked, card.Locked.text);
                Assert.AreEqual(Navigation.Mode.None, card.Button.navigation.mode, $"the keyboard can reach locked card {i + 1}");
            }
            Assert.AreEqual(Select.Cards[0].Button, Menu.DefaultButton, "the first unlocked card is not the default selection");

            // A press on a locked card does nothing, through the UI submit and through the click event alike.
            string titleLevel = Game.LevelId;
            ExecuteEvents.Execute(Select.Cards[1].Button.gameObject, new BaseEventData(EventSystem.current), ExecuteEvents.submitHandler);
            Select.Cards[1].Button.onClick.Invoke();
            Select.Choose(1);
            yield return Steps(3);
            Assert.IsTrue(Menu.LevelSelectOpen, "a locked card closed the level select");
            Assert.AreEqual(titleLevel, Game.LevelId, "a locked card loaded its level");
            Assert.IsTrue(Game.Paused);

            // Win level 1 for real: level 2 unlocks, level 3 stays locked.
            Menu.CloseLevelSelect();
            Menu.Play();
            Assert.AreEqual(Order[0], Game.LevelId, "premise: Jouer did not start level 1");
            yield return WinNow(15);
            float first = Game.Elapsed;
            CollectionAssert.Contains(SaveStore.Current.Won, Order[0], "the win of level 1 was not recorded");
            Menu.ShowTitle();
            OpenSelect();
            Assert.IsTrue(Select.Cards[1].Button.interactable, "winning level 1 did not unlock level 2");
            Assert.IsFalse(Select.Cards[1].Locked.enabled);
            Assert.AreEqual(string.Format(Strings.SelectBest, Seconds(first)), Select.Cards[0].Best.text, "card 1 does not show its best time");
            Assert.IsFalse(Select.Cards[2].Button.interactable, "winning level 1 unlocked level 3");
            Assert.AreEqual(Select.Cards[1].Button, Select.Cards[0].Button.navigation.selectOnRight, "right from card 1 is not card 2");

            // An unlocked card loads its level and closes the menus.
            Select.Cards[1].Button.onClick.Invoke();
            Assert.IsFalse(Menu.LevelSelectOpen, "the card did not close the level select");
            Assert.IsFalse(Menu.IsOpen, "the card did not close the title");
            Assert.IsFalse(Game.Paused, "the chosen level is paused");
            Assert.IsTrue(Hud.Visible);
            Assert.AreEqual(Order[1], Game.LevelId, "card 2 did not load level 2");
            Assert.AreEqual(PlayState.Playing, Game.State);
            yield return WinNow(15);
            Menu.ShowTitle();
            OpenSelect();
            Assert.IsTrue(Select.Cards[2].Button.interactable, "winning level 2 did not unlock level 3");
            if (Order.Count > 3)
            {
                Assert.IsFalse(Select.Cards[3].Button.interactable, "winning level 2 unlocked level 4");
            }
            SaveData disk = ReadSaveFile();
            CollectionAssert.AreEqual(new[] { Order[0], Order[1] }, disk.Won, "the save file does not hold both wins");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        // ----- 41b: Jouer -----

        [UnityTest]
        public IEnumerator Step41b_PlayStartsTheFirstUnwonLevel()
        {
            Assert.GreaterOrEqual(Order.Count, 3, "premise: levels.json lists at least three levels");
            SaveStore.UnlockAll = false;
            Game.LoadLevel(Order[1]);
            yield return Steps(2);

            Menu.ShowTitle();
            Menu.PlayButton.onClick.Invoke();
            Assert.AreEqual(Order[0], Game.LevelId, "Jouer on a fresh save does not start level 1");
            yield return WinNow(10);

            Menu.ShowTitle();
            Menu.PlayButton.onClick.Invoke();
            Assert.AreEqual(Order[1], Game.LevelId, "Jouer does not start the first level not won");
            Assert.IsFalse(Game.Paused);

            // Every level won: the last one.
            foreach (string id in Order)
            {
                SaveStore.RecordWin(id, 30f);
            }
            Menu.ShowTitle();
            Assert.AreEqual(TitleCameraTour.LevelId, Game.LevelId, "premise: the title is not over the title house (M7 title camera)");
            Menu.PlayButton.onClick.Invoke();
            Assert.AreEqual(Order[Order.Count - 1], Game.LevelId, "Jouer with every level won does not start the last level");
            yield return Steps(2);
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        // ----- 41c: best times only improve -----

        /// <summary>The PlayMode killer of "a slower best time overwrites" (SaveData, MUTATION:SLOWER_BEST).</summary>
        [UnityTest]
        public IEnumerator Step41c_BestTimeOnlyImproves()
        {
            Menu.ShowTitle();
            Menu.Play();
            string level = Game.LevelId;
            Assert.AreEqual(Order[0], level, "premise: Jouer started level 1");

            yield return WinNow(40);
            float first = Game.Elapsed;
            Assert.IsTrue(SaveStore.TryGetBest(level, out float best), "the first win recorded no best time");
            Assert.AreEqual(first, best, 1e-4f);
            Assert.IsTrue(Record.NewBestShown, "the first win is not a new record");
            Assert.AreEqual(first, ReadSaveFile().Best[level], 1e-4f, "the first best time is not on disk");

            Game.Restart();
            yield return WinNow(90);
            float slower = Game.Elapsed;
            Assert.Greater(slower, first + 0.5f, "premise: the second win is not slower");
            Assert.IsTrue(SaveStore.TryGetBest(level, out best));
            Assert.AreEqual(first, best, 1e-4f, "a slower win replaced the best time");
            Assert.AreEqual(first, ReadSaveFile().Best[level], 1e-4f, "a slower win replaced the best time on disk");
            Assert.IsTrue(Record.Shown);
            Assert.IsFalse(Record.NewBestShown, "a slower win shows Nouveau record");
            Assert.AreEqual(string.Format(Strings.WinBest, Seconds(first)), Record.BestText, "the record line does not show the kept best");

            Game.Restart();
            yield return WinNow(5);
            float faster = Game.Elapsed;
            Assert.Less(faster, first - 0.3f, "premise: the third win is not faster");
            Assert.IsTrue(SaveStore.TryGetBest(level, out best));
            Assert.AreEqual(faster, best, 1e-4f, "a faster win did not replace the best time");
            Assert.AreEqual(faster, ReadSaveFile().Best[level], 1e-4f, "the faster best time is not on disk");
            Assert.IsTrue(Record.NewBestShown, "a faster win is not a new record");
            Assert.AreEqual(string.Format(Strings.WinBest, Seconds(faster)), Record.BestText);

            OpenSelect();
            Assert.AreEqual(string.Format(Strings.SelectBest, Seconds(faster)), Select.Cards[0].Best.text, "the card does not show the best time");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        // ----- 41d: the record line -----

        [UnityTest]
        public IEnumerator Step41d_RecordLineOnTheWinPanelAndTheEndScreen()
        {
            Assert.IsTrue(Game.HasNextLevel, "premise: the start level has a next level");
            Assert.IsFalse(Record.Shown, "premise: a record line before any win");
            Assert.IsTrue(Record.transform.IsChildOf(Hud.WinPanel), "the record line is not under the win panel");

            yield return WinNow(20);
            Assert.IsTrue(Hud.WinVisible && Hud.WinNextVisible, "premise: the win panel offers the next level");
            Assert.IsTrue(Record.Shown, "no record line under the win panel");
            Assert.IsFalse(Record.OnEndScreen);
            Assert.AreEqual(string.Format(Strings.WinBest, Seconds(Game.Elapsed)), Record.BestText, "the record line text");
            Assert.IsTrue(Record.NewBestShown, "the first win does not say Nouveau record");
            Assert.AreEqual(Strings.WinNewBest, Record.NewBestText);
            yield return null;
            AssertNoOverlap(Record.BestRect, "record line", ("the win title", HudLabel("WinPanelTitle")), ("the win time", HudLabel("WinPanelBody")),
                ("the win action", HudLabel("WinPanelAction")), ("win.next", HudLabel("WinNext")), ("Nouveau record", Record.NewBestRect));
            AssertNoOverlap(Record.NewBestRect, "new record line", ("the win time", HudLabel("WinPanelBody")),
                ("the win action", HudLabel("WinPanelAction")), ("win.next", HudLabel("WinNext")));

            // Any other state hides it.
            Game.Restart();
            Assert.IsFalse(Record.Shown, "the record line outlived the win");
            Assert.IsFalse(Record.HasRecord);

            // The end screen after the last level shows it too, below its button.
            string last = Order[Order.Count - 1];
            Game.LoadLevel(last);
            yield return Steps(2);
            Assert.IsTrue(Game.IsLastLevel, "premise: the last level of levels.json is up");
            yield return WinNow(10);
            Assert.IsTrue(Hud.EndVisible, "premise: the end screen is not up");
            Assert.IsTrue(Record.Shown, "no record line on the end screen");
            Assert.IsTrue(Record.OnEndScreen);
            Assert.AreEqual(string.Format(Strings.WinBest, Seconds(Game.Elapsed)), Record.BestText);
            Assert.IsTrue(Record.NewBestShown);
            yield return null;
            AssertNoOverlap(Record.BestRect, "end record line", ("the end body", HudLabel("WinPanelBody")), ("the end time", HudLabel("EndTime")),
                ("the end action", HudLabel("WinPanelAction")), ("the end button", (RectTransform)Hud.EndButton.transform));
            AssertNoOverlap(Record.NewBestRect, "end new record line", ("the end time", HudLabel("EndTime")),
                ("the end button", (RectTransform)Hud.EndButton.transform));
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        // ----- 41e: Retour -----

        [UnityTest]
        public IEnumerator Step41e_BackReturnsToTheTitle()
        {
            Menu.ShowTitle();
            yield return Until(() => Selected == Menu.PlayButton.gameObject, 5);
            Assert.AreEqual(Menu.PlayButton.gameObject, Selected, "premise: Jouer is selected on the title");

            OpenSelect();
            Assert.IsFalse(Menu.TitlePageShown);
            Assert.AreEqual(Select.Cards[0].Button, Menu.DefaultButton, "the first unlocked card is not the default selection");
            yield return Until(() => Selected == Select.Cards[0].Button.gameObject, 5);
            Assert.AreEqual(Select.Cards[0].Button.gameObject, Selected, "the first unlocked card is not selected on open");
            Navigation nav = Select.Cards[0].Button.navigation;
            Assert.AreEqual(Navigation.Mode.Explicit, nav.mode, "the cards' navigation is not explicit");
            Assert.AreEqual(Select.Cards[1].Button, nav.selectOnRight, "right from card 1 is not card 2");
            Selectable below = Select.CardCount > Tuning.LevelSelectColumns ? Select.Cards[Tuning.LevelSelectColumns].Button : (Selectable)Select.BackButton;
            Assert.AreEqual(below, nav.selectOnDown, "down from card 1 is not the card below it (or Retour)");
            Assert.AreEqual(Select.Cards[0].Button, Select.BackButton.navigation.selectOnDown, "down from Retour is not the first card");

            // Escape opens no pause over the level select.
            InputReader.InjectPausePress();
            yield return Steps(3);
            Assert.IsFalse(Menu.PauseOpen, "a pause press opened the pause menu over the level select");
            Assert.IsTrue(Menu.LevelSelectOpen, "a pause press closed the level select");
            Assert.IsTrue(Game.Paused);

            // Escape or gamepad B (an injected back press): the title, on Niveaux.
            InputReader.InjectBack();
            yield return Until(() => !Menu.LevelSelectOpen, 10);
            Assert.IsFalse(Menu.LevelSelectOpen, "a back press did not close the level select");
            Assert.IsFalse(Select.IsOpen);
            Assert.IsTrue(Menu.TitleOpen, "a back press closed the title");
            Assert.IsTrue(Menu.TitlePageShown, "the title page does not show after a back press");
            Assert.IsFalse(Menu.PauseOpen);
            Assert.IsTrue(Game.Paused, "the game runs after a back press");
            yield return Until(() => Selected == Menu.LevelsButton.gameObject, 5);
            Assert.AreEqual(Menu.LevelsButton.gameObject, Selected, "Niveaux is not selected after Retour");

            // Retour does the same.
            OpenSelect();
            Select.BackButton.onClick.Invoke();
            Assert.IsFalse(Menu.LevelSelectOpen, "Retour did not close the level select");
            Assert.IsTrue(Menu.TitleOpen && Menu.TitlePageShown, "Retour did not show the title page");

            // Control: a back press on the title page changes nothing, and Jouer still starts the game.
            InputReader.InjectBack();
            yield return Steps(3);
            Assert.IsTrue(Menu.TitleOpen && Menu.TitlePageShown, "a back press on the title page closed it");
            Menu.PlayButton.onClick.Invoke();
            Assert.IsFalse(Menu.IsOpen, "control: Jouer does not start the game");
            Assert.IsFalse(Game.Paused);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        // ----- 41f: an unusable save at boot -----

        private IEnumerator RebootWith(string file)
        {
            SaveStore.PathOverride = file;
            Main previous = main;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            yield return WaitForMain(previous);
            yield return Steps(2);
        }

        [UnityTest]
        public IEnumerator Step41f_CorruptSaveAtBootStartsFresh()
        {
            string file = Path.Combine(NewTempDir(), SaveStore.FileName);
            const string corrupt = "{ \"version\": 1, \"won\": [\"lev";
            File.WriteAllText(file, corrupt);
            yield return RebootWith(file);

            Assert.AreEqual(file, SaveStore.FilePath, "premise: the boot did not keep the injected save path");
            Assert.AreEqual(0, main.FailedSteps, "a build step of Main failed on a corrupt save");
            Assert.AreEqual(SaveLoadStatus.Reset, SaveStore.LastLoad, "the corrupt save was not set aside");
            Assert.IsEmpty(SaveStore.Current.Won, "the game did not start fresh");
            Assert.IsFalse(File.Exists(file), "the corrupt save is still in place");
            Assert.AreEqual(corrupt, File.ReadAllText(file + SaveStore.BadSuffix), "the corrupt save was not kept as .bad");
            Assert.IsFalse(SaveStore.InMemory, "a corrupt save stopped the session from saving");
            Assert.AreEqual(PlayState.Playing, Game.State);

            // The fresh save drives the level select, and the next win writes it.
            SaveStore.UnlockAll = false;
            OpenSelect();
            Assert.IsTrue(Select.Cards[0].Button.interactable);
            Assert.IsFalse(Select.Cards[1].Button.interactable, "a corrupt save unlocked level 2");
            Menu.CloseLevelSelect();
            Menu.Play();
            yield return WinNow(5);
            SaveData disk = ReadSaveFile();
            CollectionAssert.AreEqual(new[] { Order[0] }, disk.Won);
            Assert.AreEqual(SaveData.CurrentVersion, disk.Version);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        [UnityTest]
        public IEnumerator Step41f_NewerSaveAtBootIsRestoredFromBak()
        {
            Assert.GreaterOrEqual(Order.Count, 2, "premise: levels.json lists at least two levels");
            string file = Path.Combine(NewTempDir(), SaveStore.FileName);
            string newer = "{ \"version\": 2, \"won\": [\"" + Order[0] + "\", \"" + Order[1] + "\"], \"best\": {} }";
            string backup = "{ \"version\": 1, \"won\": [\"" + Order[0] + "\"], \"best\": { \"" + Order[0] + "\": 7.5 } }";
            File.WriteAllText(file, newer);
            File.WriteAllText(file + SaveStore.BakSuffix, backup);
            yield return RebootWith(file);

            Assert.AreEqual(file, SaveStore.FilePath, "premise: the boot did not keep the injected save path");
            Assert.AreEqual(0, main.FailedSteps);
            Assert.AreEqual(SaveLoadStatus.FromBackup, SaveStore.LastLoad, "a newer save with a good backup was not restored from it");
            CollectionAssert.AreEqual(new[] { Order[0] }, SaveStore.Current.Won);
            Assert.AreEqual(newer, File.ReadAllText(file + SaveStore.BadSuffix), "the newer save was not kept as .bad");
            CollectionAssert.AreEqual(new[] { Order[0] }, ReadSaveFile().Won, "the save file does not hold the restored data");

            // The restored progress is the one played: Jouer starts level 2, the card shows the restored best time.
            SaveStore.UnlockAll = false;
            OpenSelect();
            Assert.IsTrue(Select.Cards[1].Button.interactable, "the restored win did not unlock level 2");
            Assert.AreEqual(string.Format(Strings.SelectBest, Seconds(7.5f)), Select.Cards[0].Best.text);
            Menu.CloseLevelSelect();
            Menu.PlayButton.onClick.Invoke();
            Assert.AreEqual(Order[1], Game.LevelId, "Jouer does not continue the restored progress");
            yield return Steps(2);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// CONTRACT_M5 17 (m12): the save file is missing and the .tmp of an interrupted write holds the progress (a
        /// process kill in the delete-then-move fallback, every save's branch on Android). The boot restores it.
        /// </summary>
        [UnityTest]
        public IEnumerator Step41f_MissingSaveAtBootIsRestoredFromTmp()
        {
            Assert.GreaterOrEqual(Order.Count, 2, "premise: levels.json lists at least two levels");
            string file = Path.Combine(NewTempDir(), SaveStore.FileName);
            string pending = "{ \"version\": 1, \"won\": [\"" + Order[0] + "\"], \"best\": { \"" + Order[0] + "\": 6.5 } }";
            File.WriteAllText(file + SaveStore.TmpSuffix, pending);
            Assert.IsFalse(File.Exists(file), "premise: the save file is missing");
            yield return RebootWith(file);

            Assert.AreEqual(file, SaveStore.FilePath, "premise: the boot did not keep the injected save path");
            Assert.AreEqual(0, main.FailedSteps);
            Assert.AreEqual(SaveLoadStatus.FromTmp, SaveStore.LastLoad, "a missing save was not restored from the .tmp of the interrupted write");
            CollectionAssert.AreEqual(new[] { Order[0] }, SaveStore.Current.Won);
            Assert.IsFalse(File.Exists(file + SaveStore.TmpSuffix), "the restored .tmp was left behind");
            CollectionAssert.AreEqual(new[] { Order[0] }, ReadSaveFile().Won, "the save file does not hold the restored data");
            Assert.IsFalse(SaveStore.InMemory, "a restored save stopped the session from saving");

            // The restored progress is the one played: level 2 is open, the card shows the restored best time.
            SaveStore.UnlockAll = false;
            OpenSelect();
            Assert.IsTrue(Select.Cards[1].Button.interactable, "the restored win did not unlock level 2");
            Assert.AreEqual(string.Format(Strings.SelectBest, Seconds(6.5f)), Select.Cards[0].Best.text);
            Menu.CloseLevelSelect();
            Menu.PlayButton.onClick.Invoke();
            Assert.AreEqual(Order[1], Game.LevelId, "Jouer does not continue the restored progress");
            yield return Steps(2);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        // ----- 41g: the editor never touches the real save -----

        [UnityTest]
        public IEnumerator Step41g_EditorRunNeverTouchesTheRealSave()
        {
            string expected = Path.Combine(Application.temporaryCachePath, SaveStore.TestFileName);
            string real = Path.Combine(Application.persistentDataPath, SaveStore.FileName);
            Assert.AreNotEqual(real, expected, "premise: the test and real paths differ");
            Assert.AreEqual(expected, SaveStore.PathOverride, "the editor boot did not point the save at the test file");
            Assert.AreEqual(expected, SaveStore.FilePath);
            Assert.IsTrue(SaveStore.UnlockAll, "the editor boot did not unlock every level");
            Assert.AreEqual(SaveLoadStatus.Fresh, SaveStore.LastLoad, "the editor boot did not start on a fresh test save");
            string realBefore = File.Exists(real) ? File.ReadAllText(real) : null;
            DateTime realTime = File.Exists(real) ? File.GetLastWriteTimeUtc(real) : DateTime.MinValue;

            string level = Game.LevelId;
            yield return WinNow(5);
            Assert.IsTrue(File.Exists(expected), "the win was not written to the test save");
            CollectionAssert.Contains(ReadSaveFile().Won, level);
            Assert.AreEqual(realBefore, File.Exists(real) ? File.ReadAllText(real) : null, "a win in the editor changed the real save");
            Assert.AreEqual(realTime, File.Exists(real) ? File.GetLastWriteTimeUtc(real) : DateTime.MinValue, "a win in the editor wrote the real save");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }
    }
}
