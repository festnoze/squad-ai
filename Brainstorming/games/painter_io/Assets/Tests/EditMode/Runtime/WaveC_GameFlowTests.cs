// Owned by game-flow (wave C). EditMode checks of the wave C game-flow fixes:
// - rules-01: the self-crossing lesson (TutorialOverlay Bubble.SelfCross, key tut.selfcross, SaveData.TutSelfCrossDone);
// - rules-05: the tutorial lesson timers count only the time a bubble is really on screen (CountsAsVisible);
// - robust-04: GameDirector.SleepTimeoutFor and the Android pause frame rate.
// No test writes PlayerPrefs: every test runs with SaveData.MemoryOnly on (setters only touch the in-memory cache) and
// every session is a non-persisting one (CountsForStats false). The overlay is driven through TickCore with explicit
// inputs, so no GameDirector is needed.
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;
using Bubble = PainterIO.Runtime.TutorialOverlay.Bubble;

namespace PainterIO.Tests
{
    public class WaveC_GameFlowTests
    {
        private const float Frame = 1f / 30f;
        private const int Human = 0;
        private const int Bot = 1;

        private UiRoot ui;
        private GameSession session;

        [SetUp]
        public void SetUp()
        {
            SaveData.MemoryOnly = true;
            // A known tutorial state: the exit and lasso lessons are done, the cut and self-crossing ones are not.
            SaveData.TutExitDone = true;
            SaveData.TutLassoDone = true;
            SaveData.TutCutDone = false;
            SaveData.TutSelfCrossDone = false;
        }

        [TearDown]
        public void TearDown()
        {
            if (session != null) session.Close();
            session = null;
            if (ui != null) Object.DestroyImmediate(ui.gameObject);
            ui = null;
            SaveData.MemoryOnly = false;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Helpers.

        private TutorialOverlay Overlay()
        {
            ui = UiRoot.Create(null);
            Assert.IsNotNull(ui.Tutorial, "the tutorial overlay is built");
            session = GameSession.CreateRound(4242UL, false);
            session.CountsForStats = false;   // never persists a flag
            ui.Tutorial.Bind(session);
            return ui.Tutorial;
        }

        private static TutorialOverlay.TickInputs Playing(bool hasSpark = false)
        {
            return new TutorialOverlay.TickInputs { Live = true, HumanAlive = true, HumanHasSpark = hasSpark };
        }

        private static void Run(TutorialOverlay t, float seconds, TutorialOverlay.TickInputs k)
        {
            int frames = Mathf.CeilToInt(seconds / Frame);
            for (int i = 0; i < frames; i++) t.TickCore(Frame, k);
        }

        private void Send(TutorialOverlay t, SimEventType type, int player, bool chased = false, int[] cells = null)
        {
            var e = new SimEvent { Type = type, Player = player, Chased = chased, Cells = cells ?? new int[0] };
            t.OnSimEvent(session, e);
        }

        private void CrossThenReturn(TutorialOverlay t, bool chased)
        {
            Send(t, SimEventType.Exit, Human);
            Send(t, SimEventType.LassoCrossNoCharge, Human);
            Send(t, SimEventType.Return, Human, chased, chased ? new int[0] : new[] { 10, 11, 12 });
        }

        // ------------------------------------------------------------------------------------------------------------
        // rules-01: strings and saved flag.

        [Test]
        public void WaveC_Strings_SelfCrossLineInBothLanguages()
        {
            Assert.AreEqual("Recroiser ton fil ouvre ta boucle : rentre sans le recroiser pour tout peindre.",
                            Strings.Get("tut.selfcross", Strings.French));
            Assert.AreEqual("Crossing your own thread breaks the loop: come home without crossing it to paint it all.",
                            Strings.Get("tut.selfcross", Strings.English));
            foreach (int lang in new[] { Strings.French, Strings.English })
                Assert.IsFalse(Strings.Get("tut.selfcross", lang).IndexOf((char)0x2014) >= 0, "no em dash");
        }

        [Test]
        public void WaveC_SaveData_TutSelfCrossDoneIsCachedWithoutWritingPlayerPrefsInMemoryOnlyMode()
        {
            const string key = SaveData.Prefix + "TutSelfCrossDone";
            bool hadKey = PlayerPrefs.HasKey(key);
            int stored = PlayerPrefs.GetInt(key, -7);

            SaveData.TutSelfCrossDone = true;
            Assert.IsTrue(SaveData.TutSelfCrossDone);
            SaveData.TutSelfCrossDone = false;
            Assert.IsFalse(SaveData.TutSelfCrossDone);
            SaveData.TutSelfCrossDone = true;
            SaveData.Flush();
            Assert.AreEqual(hadKey, PlayerPrefs.HasKey(key), "MemoryOnly never creates the key");
            Assert.AreEqual(stored, PlayerPrefs.GetInt(key, -7), "MemoryOnly never writes the key");

            SaveData.MemoryOnly = false;   // drops the cache: the stored value comes back
            Assert.AreEqual(hadKey && stored != 0, SaveData.TutSelfCrossDone, "back to the PlayerPrefs value");
            SaveData.MemoryOnly = true;
        }

        // ------------------------------------------------------------------------------------------------------------
        // rules-01: the self-crossing bubble.

        [Test]
        public void WaveC_SelfCross_UnchasedReturnAfterAnUnchargedCrossingShowsTheBubbleOnce()
        {
            TutorialOverlay t = Overlay();
            Send(t, SimEventType.Exit, Human);
            Send(t, SimEventType.LassoCrossNoCharge, Human);
            Assert.IsTrue(t.SelfCrossPending, "the crossing arms the lesson");
            Run(t, 0.5f, Playing());
            Assert.AreEqual(Bubble.None, t.WantedBubble, "nothing is shown at the crossing itself (R8 and R16 untouched)");

            Send(t, SimEventType.Return, Human, false, new[] { 3, 4 });
            Assert.IsFalse(t.SelfCrossPending);
            t.TickCore(Frame, Playing());
            Assert.AreEqual(Bubble.SelfCross, t.WantedBubble, "the next unchased return explains the lost loop");
            Run(t, 1f, Playing());
            Assert.AreEqual(Bubble.SelfCross, t.ShownBubble);
            Assert.IsFalse(t.SelfCrossLessonDone, "not read yet after 1 s");

            Run(t, 2f, Playing());
            Assert.IsTrue(t.SelfCrossLessonDone, "2.5 s on screen: learnt");
            Run(t, 1.2f, Playing());
            Assert.AreNotEqual(Bubble.SelfCross, t.WantedBubble, "hidden after 4.0 s of visible time");

            // A second occurrence in the same session shows nothing.
            CrossThenReturn(t, false);
            Assert.IsFalse(t.SelfCrossPending);
            Run(t, 0.5f, Playing());
            Assert.AreEqual(Bubble.None, t.WantedBubble, "never twice in a session");
            Assert.IsFalse(SaveData.TutSelfCrossDone, "a non-persisting session never saves the flag");
        }

        [Test]
        public void WaveC_SelfCross_ChasedReturnShowsNothing()
        {
            TutorialOverlay t = Overlay();
            CrossThenReturn(t, true);
            Assert.IsFalse(t.SelfCrossPending, "the chased return drops the lesson");
            Run(t, 0.5f, Playing());
            Assert.AreEqual(Bubble.None, t.WantedBubble, "the saved toast already explains the loss");

            // It is not re-armed by the chase: the next crossing arms it again.
            CrossThenReturn(t, false);
            t.TickCore(Frame, Playing());
            Assert.AreEqual(Bubble.SelfCross, t.WantedBubble);
        }

        [Test]
        public void WaveC_SelfCross_SavedFlagSuppressesTheLesson()
        {
            SaveData.TutSelfCrossDone = true;
            TutorialOverlay t = Overlay();
            CrossThenReturn(t, false);
            Assert.IsFalse(t.SelfCrossPending);
            Run(t, 0.5f, Playing());
            Assert.AreEqual(Bubble.None, t.WantedBubble, "a step whose flag is set never shows again");
        }

        [Test]
        public void WaveC_SelfCross_ABotCrossingDoesNothing()
        {
            TutorialOverlay t = Overlay();
            Send(t, SimEventType.Exit, Human);
            Send(t, SimEventType.LassoCrossNoCharge, Bot);
            Assert.IsFalse(t.SelfCrossPending, "only the human's crossings count");
            Send(t, SimEventType.Return, Bot, false, new[] { 1 });
            Send(t, SimEventType.Return, Human, false, new[] { 2 });
            Run(t, 0.5f, Playing());
            Assert.AreEqual(Bubble.None, t.WantedBubble);
        }

        [Test]
        public void WaveC_SelfCross_AnExitBetweenTheCrossingAndTheReturnCancelsIt()
        {
            TutorialOverlay t = Overlay();
            Send(t, SimEventType.LassoCrossNoCharge, Human);
            Assert.IsTrue(t.SelfCrossPending);
            Send(t, SimEventType.Exit, Human);
            Assert.IsFalse(t.SelfCrossPending, "a new exit cancels the pending lesson");
            Send(t, SimEventType.Return, Human, false, new[] { 2 });
            Run(t, 0.5f, Playing());
            Assert.AreEqual(Bubble.None, t.WantedBubble);
        }

        [Test]
        public void WaveC_SelfCross_SparkCatchAndEliminationCancelIt()
        {
            TutorialOverlay t = Overlay();
            Send(t, SimEventType.LassoCrossNoCharge, Human);
            Send(t, SimEventType.SparkCaught, Human);
            Assert.IsFalse(t.SelfCrossPending, "caught: cancelled");

            CrossThenReturn(t, false);
            Run(t, 0.5f, Playing());
            Assert.AreEqual(Bubble.SelfCross, t.WantedBubble);
            Send(t, SimEventType.Eliminated, Human);
            Run(t, 0.5f, Playing());
            Assert.AreNotEqual(Bubble.SelfCross, t.WantedBubble, "eliminated: hidden");
        }

        [Test]
        public void WaveC_SelfCross_ANewExitHidesTheBubbleOnlyOnceItWasRead()
        {
            TutorialOverlay t = Overlay();
            CrossThenReturn(t, false);
            Run(t, 1f, Playing());
            Send(t, SimEventType.Exit, Human);   // an edge flicker or a quick new excursion
            t.TickCore(Frame, Playing());
            Assert.AreEqual(Bubble.SelfCross, t.WantedBubble, "kept before it could be read");
            Run(t, 2f, Playing());
            Assert.IsTrue(t.SelfCrossLessonDone);
            Assert.AreEqual(Bubble.SelfCross, t.WantedBubble, "still within its 4.0 s");
            Send(t, SimEventType.Exit, Human);
            t.TickCore(Frame, Playing());
            Assert.AreNotEqual(Bubble.SelfCross, t.WantedBubble, "read: a new exit hides it");
        }

        [Test]
        public void WaveC_SelfCross_PriorityBelowCutAndLasso()
        {
            SaveData.TutLassoDone = false;
            TutorialOverlay t = Overlay();
            CrossThenReturn(t, false);
            t.TickCore(Frame, Playing(true));
            Assert.AreEqual(Bubble.SelfCross, t.WantedBubble);

            Send(t, SimEventType.RingPicked, Human);
            t.TickCore(Frame, Playing(true));
            Assert.AreEqual(Bubble.Lasso, t.WantedBubble, "Lasso > SelfCross");

            Send(t, SimEventType.Cut, Human);
            t.TickCore(Frame, Playing(true));
            Assert.AreEqual(Bubble.Cut, t.WantedBubble, "Cut > Lasso > SelfCross");
        }

        [Test]
        public void WaveC_SelfCross_TimerStopsWhileTheBubbleIsHidden()
        {
            TutorialOverlay t = Overlay();
            CrossThenReturn(t, false);
            Run(t, 1f, Playing());
            TutorialOverlay.TickInputs paused = Playing();
            paused.Paused = true;
            Run(t, 6f, paused);
            Assert.AreEqual(Bubble.None, t.WantedBubble, "hidden while paused");
            Assert.IsFalse(t.SelfCrossLessonDone, "the pause does not count");
            t.TickCore(Frame, Playing());
            Assert.AreEqual(Bubble.SelfCross, t.WantedBubble, "comes back after the pause");
        }

        // ------------------------------------------------------------------------------------------------------------
        // rules-05: the first-cut lesson counts only real on-screen time.

        [Test]
        public void WaveC_CountsAsVisible_OnlyWhenWantedShownAndFadedIn()
        {
            Assert.IsTrue(TutorialOverlay.CountsAsVisible(Bubble.Cut, Bubble.Cut, 1f));
            Assert.IsTrue(TutorialOverlay.CountsAsVisible(Bubble.Cut, Bubble.Cut, 0.95f));
            Assert.IsFalse(TutorialOverlay.CountsAsVisible(Bubble.Cut, Bubble.None, 1f), "paused, ready gate or death beat");
            Assert.IsFalse(TutorialOverlay.CountsAsVisible(Bubble.Cut, Bubble.Cut, 0.5f), "still fading in");
            Assert.IsFalse(TutorialOverlay.CountsAsVisible(Bubble.Cut, Bubble.Cut, 0.94f));
            Assert.IsFalse(TutorialOverlay.CountsAsVisible(Bubble.Exit, Bubble.Cut, 1f), "another text still on screen");
            Assert.IsFalse(TutorialOverlay.CountsAsVisible(Bubble.None, Bubble.None, 0f));
            Assert.IsTrue(TutorialOverlay.CountsAsVisible(Bubble.SelfCross, Bubble.SelfCross, 1f));
        }

        [Test]
        public void WaveC_CutLesson_HiddenTimeNeverCounts()
        {
            TutorialOverlay t = Overlay();
            Send(t, SimEventType.Exit, Human);
            Send(t, SimEventType.Cut, Human);

            var hidden = new List<TutorialOverlay.TickInputs>();
            TutorialOverlay.TickInputs k = Playing(true);
            k.Paused = true;
            hidden.Add(k);
            k = Playing(true);
            k.AwaitingStart = true;   // the ready gate after a pause
            hidden.Add(k);
            k = Playing(true);
            k.InBeat = true;          // the death beat
            hidden.Add(k);
            foreach (TutorialOverlay.TickInputs h in hidden)
            {
                Run(t, 3f, h);
                Assert.AreEqual(Bubble.None, t.WantedBubble);
                Assert.AreEqual(0f, t.CutVisibleSeconds, 1e-6f, "hidden time does not count");
                Assert.IsFalse(t.CutLessonDone, "3 s behind the pause panel, the gate or the beat do not consume the lesson");
            }
            Assert.IsFalse(SaveData.TutCutDone, "nothing saved");

            Run(t, 1f, Playing(true));
            Assert.AreEqual(Bubble.Cut, t.WantedBubble);
            Assert.IsFalse(t.CutLessonDone, "1 s on screen");
            Assert.That(t.CutVisibleSeconds, Is.LessThan(1f), "the fade-in does not count either");
            Run(t, 2f, Playing(true));
            Assert.IsTrue(t.CutLessonDone, "2.5 s really on screen");
            Assert.AreEqual(Bubble.Cut, t.WantedBubble, "the bubble stays until home or eliminated");
            Assert.IsFalse(SaveData.TutCutDone, "a non-persisting session never saves the flag");
        }

        [Test]
        public void WaveC_CutLesson_ChasedReturnStillMarksItDone()
        {
            TutorialOverlay t = Overlay();
            Send(t, SimEventType.Exit, Human);
            Send(t, SimEventType.Cut, Human);
            TutorialOverlay.TickInputs paused = Playing(true);
            paused.Paused = true;
            Run(t, 0.5f, paused);
            Send(t, SimEventType.Return, Human, true);
            Assert.IsTrue(t.CutLessonDone, "a chased return home completes the lesson (unchanged)");
            t.TickCore(Frame, Playing());
            Assert.AreNotEqual(Bubble.Cut, t.WantedBubble, "home: hidden");
        }

        // ------------------------------------------------------------------------------------------------------------
        // robust-04: sleep timeout and Android frame rate.

        [Test]
        public void WaveC_SleepTimeoutFor_NeverSleepOnlyWhilePlayingAndNotPaused()
        {
            Assert.AreEqual(SleepTimeout.NeverSleep, GameDirector.SleepTimeoutFor(GameState.Playing, false));
            Assert.AreEqual(SleepTimeout.SystemSetting, GameDirector.SleepTimeoutFor(GameState.Playing, true), "pause panel");
            Assert.AreEqual(SleepTimeout.SystemSetting, GameDirector.SleepTimeoutFor(GameState.Menu, false));
            Assert.AreEqual(SleepTimeout.SystemSetting, GameDirector.SleepTimeoutFor(GameState.Menu, true));
            Assert.AreEqual(SleepTimeout.SystemSetting, GameDirector.SleepTimeoutFor(GameState.Results, false));
            Assert.AreEqual(SleepTimeout.SystemSetting, GameDirector.SleepTimeoutFor(GameState.Boot, false));
        }

        [Test]
        public void WaveC_AndroidTargetFrameRate_ThirtyWhilePausedUnlessFpsIsGiven()
        {
            Assert.AreEqual(60, GameDirector.AndroidTargetFrameRate(0, false));
            Assert.AreEqual(30, GameDirector.AndroidTargetFrameRate(0, true));
            Assert.AreEqual(30, GameDirector.AndroidTargetFrameRate(-1, true));
            Assert.AreEqual(144, GameDirector.AndroidTargetFrameRate(144, false), "-fps wins");
            Assert.AreEqual(144, GameDirector.AndroidTargetFrameRate(144, true), "-fps wins while paused too");
        }
    }
}
