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
    /// level earns three stars; "New stars!" shows on the first win and not on a second equal one; the save holds the count
    /// under the record key; the level select's first card lights three stars and its total line reads "3 / 90".
    /// STARSANIM (docs/next/progress/STARSANIM.md): the stars are the win panel's hero, centred under the title and above
    /// the time, the record line, the hint and every button; their reveal (empty slots popping in, then each earned star
    /// filling one by one with a chime, a burst of sparkles and a shake) settles within about 1.9 s; a skip press completes
    /// it at once with a single chime; a refresh never replays it; a one star win fills once and ticks twice.
    /// CONFETTI (STARSANIM.md "Confetti"): a three star result fires one confetti shower with its party popper as the third
    /// star lands (none before it), drawn under the buttons and never catching a raycast; a refresh never fires it again;
    /// Replay stops it; a skip on a three star result fires it at once; it ends by itself; a one star result never fires it.
    /// STAR3D: the earned stars settle untinted (<see cref="WinStarsView.FilledTint"/>, the 3D sprite has its own gold).
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

        /// <summary>Waits (rendered frames, unscaled time) until <paramref name="until"/> holds or <paramref name="seconds"/> pass.</summary>
        private static IEnumerator Frames(Func<bool> until, float seconds)
        {
            float end = Time.realtimeSinceStartup + seconds;
            while (!until() && Time.realtimeSinceStartup < end)
            {
                yield return null;
            }
        }

        [UnityTest]
        public IEnumerator Step76a_QuickWinEarnsThreeHeroStarsRevealedOneByOneAndSavesThem()
        {
            Strings.SetLanguage(Strings.French);
            string difficulty = Game.Difficulty.Id;
            string recordId = Game.Def.RecordId;
            float reference = Stars.Reference(Game.Def, difficulty);
            Assert.Greater(reference, 0f, "premise: the first level has a route to judge against");
            Assert.AreEqual(0, SaveStore.Current.StarsOf(recordId, difficulty), "premise: the test save starts with no stars");
            Sfx sfx = main.Sfx;
            Assert.IsNotNull(sfx, "premise: Main built no Sfx");
            Assert.IsNotNull(sfx.StarChimes, "the star chimes were not synthesized");
            Assert.AreEqual(3, sfx.StarChimes.Length, "one chime per star");
            Assert.Greater(sfx.StarChimes[2].length, sfx.StarChimes[0].length, "the third chime (the chord) does not ring longer");
            int chimes = sfx.StarChimesPlayed;
            WinConfettiView confetti = Hud.WinConfetti;
            Assert.IsNotNull(confetti, "premise: the HUD built no confetti");
            Assert.IsNotNull(sfx.ConfettiPop, "the party popper was not synthesized");
            int bursts = confetti.Bursts;
            int pops = sfx.ConfettiPopsPlayed;

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
            WinStarsView view = Hud.WinStars;
            Assert.AreEqual(3, view.Count);
            Assert.IsTrue(view.Revealing, "the reveal did not start");
            Assert.IsTrue(Hud.StarsAnimating, "the HUD does not report the reveal (the ad would not wait for it)");
            Assert.AreEqual(0, view.FillsFired, "a star filled at the panel's first frame");
            Assert.Less(view.Slots[2].rectTransform.localScale.x, 1f, "the last slot is already full size at the first frame");
            Assert.That(view.Duration, Is.InRange(1.2f, 2.2f), "the reveal is not about two seconds long");

            // The first star fills: its chime (the lowest), its sparkles, the gold star shown.
            // (A frame longer than the 0.4 s between two fills may catch two at once: the checks hold for any count.)
            yield return Frames(() => view.FillsFired >= 1, 2f);
            Assert.GreaterOrEqual(view.FillsFired, 1, "the first star never filled");
            Assert.AreEqual(chimes + view.FillsFired, sfx.StarChimesPlayed, "each fill did not chime once");
            Assert.AreEqual(view.FillsFired - 1, sfx.LastStarChime, "the chimes do not follow the stars (star 1, 2, 3)");
            Assert.IsTrue(view.Images[0].enabled, "the first gold star does not show");
            Assert.GreaterOrEqual(view.LiveSparkles, 8, "the first fill sent out no burst of sparkles");
            if (view.FillsFired == 1)
            {
                Assert.IsFalse(view.Images[2].enabled, "the third star filled with the first");
            }
            if (view.FillsFired < 3)
            {
                Assert.IsFalse(Hud.ConfettiPlaying, "the confetti burst before the third star");
                Assert.AreEqual(bursts, confetti.Bursts, "the confetti fired before the third star");
            }

            // CONFETTI: the third star lands, and the shower bursts with it (one, with one party popper).
            yield return Frames(() => view.FillsFired >= 3, 3f);
            Assert.AreEqual(3, view.FillsFired, "premise: the third star never filled");
            Assert.AreEqual(bursts + 1, confetti.Bursts, "the third star did not fire the confetti exactly once");
            Assert.IsTrue(Hud.ConfettiPlaying, "the confetti does not fall after the third star");
            Assert.AreEqual(pops + 1, sfx.ConfettiPopsPlayed, "the confetti did not pop exactly once");
            Assert.IsTrue(confetti.Canvas.enabled, "the confetti's canvas is off while it falls");
            Assert.That(confetti.PieceCount, Is.InRange(60, 120), "the shower is not 60 to 120 pieces");
            Assert.That(confetti.Duration, Is.InRange(2.5f, 3.6f), "the shower does not last about three seconds");
            Texture atlas = confetti.Images[0].sprite.texture;
            foreach (Image piece in confetti.Images)
            {
                Assert.IsFalse(piece.raycastTarget, $"{piece.name} catches raycasts (it would block the buttons)");
                Assert.AreSame(atlas, piece.sprite.texture, $"{piece.name} is not in the confetti atlas (one draw call)");
            }
            int under = confetti.Root.GetSiblingIndex();
            foreach (Button button in new[] { Hud.WinNextLevelButton, Hud.WinReplayButton, Hud.WinMenuButton })
            {
                Transform group = button.transform;
                while (group.parent != null && group.parent != confetti.Root.parent)
                {
                    group = group.parent;
                }
                Assert.Less(under, group.GetSiblingIndex(), $"the confetti draws over {button.name}");
            }

            // The reveal settles within its timeline: three fills, three rising chimes, every star at scale 1 in gold.
            yield return Frames(() => !view.Revealing, 3f);
            Assert.IsFalse(view.Revealing, "the reveal never settled");
            Assert.IsFalse(view.Skipped, "the reveal counts as skipped");
            Assert.AreEqual(3, view.FillsFired, "not every earned star filled");
            Assert.AreEqual(0, view.MissesFired, "a three star win ticked an empty star");
            Assert.AreEqual(chimes + 3, sfx.StarChimesPlayed, "three fills did not play three chimes");
            Assert.AreEqual(2, sfx.LastStarChime, "the last fill did not play the third chime (the chord)");
            Assert.AreEqual(0, view.LiveSparkles, "sparkles outlived the reveal");
            for (int i = 0; i < 3; i++)
            {
                Assert.IsTrue(view.Images[i].enabled, $"star {i + 1} is not shown");
                Assert.AreEqual(1f, view.Images[i].rectTransform.localScale.x, 1e-4f, $"star {i + 1} did not settle at scale 1");
                Assert.AreEqual(WinStarsView.FilledTint, view.Images[i].color, $"star {i + 1} is not shown in its own gold");
                Assert.AreEqual(1f, view.Slots[i].rectTransform.localScale.x, 1e-4f, $"slot {i + 1} did not settle at scale 1");
            }

            // Layout (reference units): the hero at the centre, under the title, above the time, the record line, the hint and
            // every button; the middle star the biggest.
            Canvas.ForceUpdateCanvases();
            var root = (RectTransform)Hud.GetComponent<Canvas>().transform;
            Rect row = LocalRect(root, view.Root);
            Assert.AreEqual(0f, row.center.x, 1f, "the star row is not centred horizontally");
            Assert.Greater(row.width, 400f, "the star row is not a hero (too small)");
            Assert.Greater(view.Images[1].rectTransform.rect.width, view.Images[0].rectTransform.rect.width, "the middle star is not the biggest");
            Rect title = LocalRect(root, Hud.Labels["WinPanelTitle"].rectTransform);
            Rect body = LocalRect(root, Hud.Labels["WinPanelBody"].rectTransform);
            Assert.Less(row.yMax, title.yMin + 1f, "the stars are not under the title");
            Assert.Greater(row.yMin, body.yMax, "the stars are not above the time");
            Assert.Greater(row.yMin, LocalRect(root, Hud.Labels["WinStarsNew"].rectTransform).yMax, "the stars are not above \"New stars!\"");
            foreach (Button button in new[] { Hud.WinNextLevelButton, Hud.WinReplayButton, Hud.WinMenuButton })
            {
                Rect b = LocalRect(root, (RectTransform)button.transform);
                Assert.Greater(row.yMin, b.yMax, $"the stars are not above {button.name}");
            }
            if (Menu.RecordLine.BestRect != null)
            {
                Rect best = LocalRect(root, Menu.RecordLine.BestRect);
                Assert.IsFalse(row.Overlaps(best), "the stars overlap the record line");
                Assert.Less(best.yMax, body.yMin + 1f, "the record line is not under the time");
            }
            Assert.Greater(row.yMin, LocalRect(root, Hud.Labels["WinPanelAction"].rectTransform).yMax, "the stars are not above the hint line");

            // A refresh (a language round trip, RecordLine asking again) keeps the settled row: no replay.
            Strings.SetLanguage(Strings.English);
            Strings.SetLanguage(Strings.French);
            Hud.ShowWinStars(3, true, false);
            yield return null;
            Assert.IsFalse(view.Revealing, "a refresh replayed the reveal");
            Assert.AreEqual(chimes + 3, sfx.StarChimesPlayed, "a refresh chimed again");
            Assert.AreEqual(bursts + 1, confetti.Bursts, "a refresh fired the confetti again");
            Assert.AreEqual(pops + 1, sfx.ConfettiPopsPlayed, "a refresh popped again");

            // A second, equal win: the count stays, and it is no longer new. A skip press completes its reveal at once, with
            // exactly one chime (the third star's), on the next frame. CONFETTI: Replay stops the first win's shower.
            Hud.WinReplayButton.onClick.Invoke();
            yield return Until(() => Game.State == PlayState.Playing, 10);
            Assert.IsFalse(Hud.WinStarsVisible, "the star row stayed up after the replay");
            Assert.IsFalse(confetti.Playing, "the confetti kept falling after Replay");
            Assert.IsFalse(confetti.Canvas.enabled, "the confetti's canvas stayed on after Replay");
            Assert.AreEqual(0, confetti.LivePieces, "confetti pieces stayed on screen after Replay");
            yield return WinCurrentLevel();
            Assert.AreEqual(3, Menu.RecordLine.LastStars);
            Assert.IsFalse(Menu.RecordLine.LastStarsNew, "an equal star count counts as new");
            Assert.IsTrue(Hud.WinStarsVisible, "the star row is not shown on the second win");
            Assert.IsFalse(Hud.WinStarsNewVisible, "\"Nouvelles étoiles !\" shows on an equal win");
            Assert.IsTrue(view.Revealing, "premise: the second win's reveal did not start");
            Assert.IsFalse(Hud.ConfettiPlaying, "the second win's confetti fell before its third star");
            int before = sfx.StarChimesPlayed;
            int burstsBefore = confetti.Bursts;
            InputReader.InjectSkipPress();
            yield return null;
            Assert.IsFalse(view.Revealing, "a skip press did not complete the reveal");
            Assert.IsTrue(view.Skipped, "the completed reveal does not count as skipped");
            Assert.IsFalse(Hud.StarsAnimating);
            for (int i = 0; i < 3; i++)
            {
                Assert.IsTrue(view.Images[i].enabled && view.Images[i].color == WinStarsView.FilledTint, $"star {i + 1} is not filled after the skip");
            }
            yield return null;
            yield return null;
            // CONFETTI: the skip on a three star result fires the shower at once (with the chime it owes, the next frame).
            Assert.AreEqual(burstsBefore + 1, confetti.Bursts, "the skip on a three star result did not fire the confetti once");
            Assert.IsTrue(Hud.ConfettiPlaying, "the confetti does not fall after the skip");
            yield return new WaitForSecondsRealtime(0.5f);
            Assert.AreEqual(before + 1, sfx.StarChimesPlayed, "the skip did not chime exactly once");
            Assert.AreEqual(2, sfx.LastStarChime, "the skip's chime is not the highest earned star's");
            Assert.IsTrue(Hud.WinVisible, "the skip left the win panel");
            Assert.Greater(confetti.LivePieces, 30, "the shower shows too few pieces half a second in");

            // The shower ends by itself within its length: every piece gone, its canvas off, the panel still up.
            yield return Frames(() => !confetti.Playing, 4.5f);
            Assert.IsFalse(confetti.Playing, "the confetti never ended");
            Assert.AreEqual(0, confetti.LivePieces, "confetti pieces outlived the shower");
            Assert.IsFalse(confetti.Canvas.enabled, "the confetti's canvas stayed on after the shower");
            Assert.AreEqual(burstsBefore + 1, confetti.Bursts, "the confetti fired again by itself");
            Assert.IsTrue(Hud.WinVisible, "the win panel went with the confetti");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// STARSANIM: a one star result (shown for the same win, as RecordLine would show a slow win's) fills the first star
        /// with the lowest chime, leaves the other two empty with a soft tick each, and settles with them empty.
        /// </summary>
        [UnityTest]
        public IEnumerator Step76c_OneStarFillsOnceAndTicksTheEmptyStars()
        {
            Strings.SetLanguage(Strings.French);
            yield return WinCurrentLevel();
            Assert.IsTrue(Hud.WinStarsVisible, "premise: the star row is not shown");
            Sfx sfx = main.Sfx;
            Hud.CompleteStarsAnimation();
            yield return null;
            int chimes = sfx.StarChimesPlayed;
            int dulls = sfx.StarDullsPlayed;
            WinConfettiView confetti = Hud.WinConfetti;
            Assert.IsNotNull(confetti, "premise: the HUD built no confetti");
            Hud.ShowWinStars(1, false, false);
            // CONFETTI: the new count's reveal stops the three star result's shower, and a one star result never fires one.
            Assert.IsFalse(Hud.ConfettiPlaying, "the three star confetti outlived the new one star result");
            int bursts = confetti.Bursts;
            int pops = sfx.ConfettiPopsPlayed;
            WinStarsView view = Hud.WinStars;
            Assert.AreEqual(1, view.Count, "premise: the row does not hold one star");
            Assert.IsTrue(view.Revealing, "a new count did not start its reveal");
            yield return Frames(() => !view.Revealing, 3f);
            Assert.IsFalse(view.Revealing, "the one star reveal never settled");
            Assert.AreEqual(1, view.FillsFired, "a one star win did not fill exactly one star");
            Assert.AreEqual(2, view.MissesFired, "the two empty stars did not tick");
            Assert.AreEqual(chimes + 1, sfx.StarChimesPlayed, "a one star win did not chime exactly once");
            Assert.AreEqual(0, sfx.LastStarChime, "the one star's chime is not the first");
            Assert.AreEqual(dulls + 2, sfx.StarDullsPlayed, "the empty stars did not tick twice");
            Assert.IsTrue(view.Images[0].enabled && view.Images[0].color == WinStarsView.FilledTint, "the earned star is not shown");
            Assert.IsFalse(view.Images[1].enabled, "the second star filled on a one star win");
            Assert.IsFalse(view.Images[2].enabled, "the third star filled on a one star win");
            Assert.IsTrue(view.Slots[1].enabled && view.Slots[2].enabled, "the empty slots do not show");
            // A skip after the settle owes nothing either: still no confetti, no pop.
            Hud.CompleteStarsAnimation();
            yield return null;
            yield return null;
            Assert.AreEqual(bursts, confetti.Bursts, "a one star result fired the confetti");
            Assert.AreEqual(pops, sfx.ConfettiPopsPlayed, "a one star result popped the party popper");
            Assert.IsFalse(Hud.ConfettiPlaying, "confetti falls on a one star result");
            Assert.AreEqual(0, confetti.LivePieces, "confetti pieces show on a one star result");
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
            Assert.AreEqual(90, select.StarsPossible, "the line-up does not hold 90 stars");
            Assert.AreEqual(3, select.StarsEarned, "the total does not count the win's stars");
            Assert.AreEqual(string.Format(Strings.StarsTotal, 3, 90), select.StarsLineText, "the total line is wrong");
            StringAssert.Contains("3 / 90", select.StarsLineText);

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
