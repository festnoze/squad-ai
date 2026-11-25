using System;
using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Stars (idea 5, docs/next/progress/STARS.md), on the real Boot scene under GameRules.M2: a quick win of the first
    /// level earns three stars, shown beside the time of the win panel (above the button row, clear of the record line and
    /// of every button), revealed one after the other and settled within a second; "New stars!" shows on the first win and
    /// not on a second equal one; the save holds the count under the record key; the level select's first card lights three
    /// stars and its total line reads "3 / 66". Written static (not run in this wave): the step numbers follow Step 73.
    /// </summary>
    public sealed class ProbeTestsStars
    {
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private GameState Game => main.Game;
        private Menu Menu => main.Menu;
        private Hud Hud => main.Hud;
        private FurnitureController Chair => Game.Furniture;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            Assert.IsNotNull(Hud, "premise: Main built no HUD");
            Game.Rules = GameRules.M2;
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
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                }
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            Cursor.lockState = CursorLockMode.None;
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

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(to - from);

        /// <summary>Every inhabitant frozen facing away from the exit, the chair driven onto the doormat (ProbeTestsEndPanel's way).</summary>
        private IEnumerator WinCurrentLevel()
        {
            ZoneDef exit = Game.Def.Exit;
            var exitCenter = new Vector3(exit.X, 0f, exit.Z);
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                Vector3 at = h.Routine.Position;
                h.Pin(at, YawToward(exitCenter, at));
            }
            RoomDef room = Game.Def.RoomAt(exitCenter) ?? (Game.Def.AllRooms().Count > 0 ? Game.Def.AllRooms()[0] : null);
            Vector3 roomCenter = room != null ? new Vector3(room.X, 0f, room.Z) : Vector3.zero;
            Vector3 d = YawMath.Planar(exitCenter - roomCenter);
            Vector3 approach = Mathf.Abs(d.x) * (room != null ? room.SizeZ : 1f) >= Mathf.Abs(d.z) * (room != null ? room.SizeX : 1f)
                ? new Vector3(Mathf.Sign(d.x), 0f, 0f)
                : new Vector3(0f, 0f, Mathf.Sign(d.z));
            if (approach.sqrMagnitude == 0f)
            {
                approach = Vector3.right;
            }
            Chair.Teleport(exitCenter - approach * 0.9f, YawMath.YawOf(approach));
            Chair.ScriptedDirection = approach;
            yield return Until(() => Game.State != PlayState.Playing, 150);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Won, Game.State, $"premise: {Game.LevelId} was not won");
        }

        /// <summary>The rectangle of <paramref name="rect"/> in the local space of <paramref name="root"/> (reference units).</summary>
        private static Rect LocalRect(RectTransform root, RectTransform rect)
        {
            var corners = new Vector3[4];
            rect.GetWorldCorners(corners);
            Vector3 min = root.InverseTransformPoint(corners[0]);
            Vector3 max = root.InverseTransformPoint(corners[2]);
            return Rect.MinMaxRect(min.x, min.y, max.x, max.y);
        }

        [UnityTest]
        public IEnumerator Step76a_QuickWinEarnsThreeStarsBesideTheTimeAndSavesThem()
        {
            Strings.SetLanguage(Strings.French);
            string difficulty = Game.Difficulty.Id;
            string recordId = Game.Def.RecordId;
            float reference = Stars.Reference(Game.Def, difficulty);
            Assert.Greater(reference, 0f, "premise: the first level has a route to judge against");
            Assert.AreEqual(0, SaveStore.Current.StarsOf(recordId, difficulty), "premise: the test save starts with no stars");

            yield return WinCurrentLevel();
            Assert.LessOrEqual(Game.Elapsed, Stars.ThreeStarsUpTo(reference), "premise: the scripted win is a three star time");
            Assert.IsTrue(Hud.WinVisible, "premise: the win panel is not up");
            Assert.IsNotNull(Menu.RecordLine, "premise: no record line");
            Assert.AreEqual(3, Menu.RecordLine.LastStars, "the quick win did not earn three stars");
            Assert.IsTrue(Menu.RecordLine.LastStarsNew, "the first win is not a new best star count");
            Assert.AreEqual(3, SaveStore.Current.StarsOf(recordId, difficulty), "the stars are not in the save");
            Assert.IsTrue(SaveStore.Current.Stars.ContainsKey(DifficultyDef.RecordKey(recordId, difficulty)), "the stars are not under the record key");
            Assert.IsTrue(Hud.WinStarsVisible, "the star row is not shown on the win panel");
            Assert.IsTrue(Hud.WinStarsNewVisible, "\"Nouvelles étoiles !\" is not shown on the first win");
            Assert.AreEqual(3, Hud.WinStars.Count);
            Assert.IsTrue(Hud.WinStars.Revealing, "the reveal did not start");
            Assert.Less(Hud.WinStars.Images[2].rectTransform.localScale.x, 1f, "the last star is already full size at the first frame");

            // The reveal settles within a second (3 stars, 0.22 s apart, 0.35 s each: 0.79 s), every star at scale 1 in gold.
            float until = Time.realtimeSinceStartup + 2f;
            while (Hud.WinStars.Revealing && Time.realtimeSinceStartup < until)
            {
                yield return null;
            }
            Assert.IsFalse(Hud.WinStars.Revealing, "the reveal never settled");
            foreach (Image star in Hud.WinStars.Images)
            {
                Assert.AreEqual(1f, star.rectTransform.localScale.x, 1e-4f, "a star did not settle at scale 1");
                Assert.AreEqual(Stars.Gold, star.color, "a star is not gold");
            }

            // Layout (reference units): beside the time, above the button row, clear of the record line and of every button.
            Canvas.ForceUpdateCanvases();
            var root = (RectTransform)Hud.GetComponent<Canvas>().transform;
            Rect row = LocalRect(root, Hud.WinStars.Root);
            Rect body = LocalRect(root, Hud.Labels["WinPanelBody"].rectTransform);
            Assert.Less(Mathf.Abs(row.center.y - body.center.y), body.height, "the stars are not on the time's row");
            Assert.Greater(row.xMin, Hud.Labels["WinPanelBody"].preferredWidth * 0.5f, "the stars overlap the time's text");
            foreach (Button button in new[] { Hud.WinNextLevelButton, Hud.WinReplayButton, Hud.WinMenuButton })
            {
                Rect b = LocalRect(root, (RectTransform)button.transform);
                Assert.Greater(row.yMin, b.yMax, $"the stars are not above {button.name}");
            }
            if (Menu.RecordLine.BestRect != null)
            {
                Assert.IsFalse(row.Overlaps(LocalRect(root, Menu.RecordLine.BestRect)), "the stars overlap the record line");
            }
            Assert.Greater(row.yMin, LocalRect(root, Hud.Labels["WinPanelAction"].rectTransform).yMax, "the stars are not above the hint line");

            // A second, equal win: the count stays, and it is no longer new.
            Hud.WinReplayButton.onClick.Invoke();
            yield return Until(() => Game.State == PlayState.Playing, 10);
            Assert.IsFalse(Hud.WinStarsVisible, "the star row stayed up after the replay");
            yield return WinCurrentLevel();
            Assert.AreEqual(3, Menu.RecordLine.LastStars);
            Assert.IsFalse(Menu.RecordLine.LastStarsNew, "an equal star count counts as new");
            Assert.IsTrue(Hud.WinStarsVisible, "the star row is not shown on the second win");
            Assert.IsFalse(Hud.WinStarsNewVisible, "\"Nouvelles étoiles !\" shows on an equal win");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        [UnityTest]
        public IEnumerator Step76b_LevelSelectShowsTheCardStarsAndTheTotal()
        {
            Strings.SetLanguage(Strings.French);
            string difficulty = Game.Difficulty.Id;
            yield return WinCurrentLevel();
            Assert.AreEqual(3, SaveStore.Current.StarsOf(Game.Def.RecordId, difficulty), "premise: the win earned three stars");
            Hud.WinMenuButton.onClick.Invoke();
            yield return Until(() => Menu.TitleOpen, 20);
            Assert.IsTrue(Menu.TitleOpen, "premise: Menu did not come back to the title");
            Menu.OpenLevelSelect();
            yield return null;
            LevelSelect select = Menu.LevelSelect;
            Assert.IsNotNull(select, "premise: no level select");
            Assert.IsTrue(select.IsOpen, "premise: the level select did not open");
            Assert.AreEqual(72, select.StarsPossible, "the line-up does not hold 72 stars");
            Assert.AreEqual(3, select.StarsEarned, "the total does not count the win's stars");
            Assert.AreEqual(string.Format(Strings.StarsTotal, 3, 72), select.StarsLineText, "the total line is wrong");
            StringAssert.Contains("3 / 72", select.StarsLineText);

            LevelSelect.Card first = select.Cards[0];
            Assert.IsNotNull(first.Stars, "the card has no star row");
            Assert.AreEqual(3, first.Stars.Count, "the first card does not light three stars");
            Assert.IsTrue(first.Stars.Images[0].enabled, "the first card's stars are hidden");
            Assert.AreEqual(Stars.Gold, first.Stars.Images[2].color, "the third star of the first card is not gold");
            // The second card: playable (level 1 won), no stars yet: three faint stars.
            LevelSelect.Card second = select.Cards[1];
            Assert.IsTrue(select.IsPlayable(1), "premise: the second level is not unlocked after the first win");
            Assert.AreEqual(0, second.Stars.Count);
            Assert.IsTrue(second.Stars.Images[0].enabled, "the second card hides its empty stars");
            Assert.AreEqual(Stars.Empty, second.Stars.Images[0].color, "an unearned star is not faint");
            // A locked card hides its row.
            for (int i = 2; i < select.CardCount; i++)
            {
                if (!select.IsPlayable(i))
                {
                    Assert.IsFalse(select.Cards[i].Stars.Images[0].enabled, $"card {i + 1} is locked but shows stars");
                    break;
                }
            }
            // The card's stars sit right of its record line, inside the card.
            Canvas.ForceUpdateCanvases();
            var cardRect = (RectTransform)first.Button.transform;
            Rect stars = LocalRect(cardRect, first.Stars.Root);
            Rect best = LocalRect(cardRect, first.Best.rectTransform);
            Assert.GreaterOrEqual(stars.xMin, best.xMax - 1f, "the card's stars overlap its record text");
            Assert.LessOrEqual(stars.xMax, cardRect.rect.xMax, "the card's stars stick out of the card");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }
    }
}
