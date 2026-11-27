// Owned by the wave C "ui" package. EditMode checks of the wave C UI fixes: CanvasScaler Expand and the layouts it must keep
// apart at every aspect (robust-01, robust-08), the toast layout with the leaderboard open (rules-02), the attract cover
// timing (rules-11), the results line stack (feel-11), the menu scrim, opaque card faces and outlined rival chevron
// (feel-06, visuals-hud-contrast-over-bright-beds) and the preview repaint budget (perf-08). No test writes PlayerPrefs.
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Runtime;
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Tests
{
    public class WaveC_UiTests
    {
        /// <summary>The checked screens: 9:16, 20:9, 21:9, tablet 3:4, landscape, plus 432 x 960 and 1080 x 1200.</summary>
        private static readonly Vector2[] Screens =
        {
            new Vector2(540f, 960f), new Vector2(1080f, 2400f), new Vector2(1080f, 2520f), new Vector2(1200f, 1600f),
            new Vector2(1280f, 720f), new Vector2(432f, 960f), new Vector2(540f, 1200f), new Vector2(1080f, 1200f),
        };

        // ------------------------------------------------------------------------------------------------------------
        // robust-01 / robust-08: Expand.

        [Test]
        public void WaveC_CanvasExpandKeepsTheWholeDesignBoxAtEveryAspect()
        {
            Assert.AreEqual(UnityEngine.UI.CanvasScaler.ScreenMatchMode.Expand, UiKit.ScreenMatch);
            AssertSize(new Vector2(1080f, 1920f), UiKit.CanvasSizeFor(540f, 960f), "9:16 unchanged");
            AssertSize(new Vector2(1080f, 2400f), UiKit.CanvasSizeFor(1080f, 2400f), "20:9 taller, same width");
            AssertSize(new Vector2(1080f, 2520f), UiKit.CanvasSizeFor(1080f, 2520f), "21:9");
            AssertSize(new Vector2(1440f, 1920f), UiKit.CanvasSizeFor(1200f, 1600f), "tablet 3:4 wider");
            AssertSize(new Vector2(1280f * 1920f / 720f, 1920f), UiKit.CanvasSizeFor(1280f, 720f), "landscape");
            AssertSize(new Vector2(1080f, 1920f), UiKit.CanvasSizeFor(0f, 0f), "unknown screen");
            foreach (Vector2 s in Screens)
            {
                Vector2 c = UiKit.CanvasSizeFor(s.x, s.y);
                Assert.That(c.x, Is.GreaterThanOrEqualTo(UiKit.RefWidth - 1e-3f), s + " width");
                Assert.That(c.y, Is.GreaterThanOrEqualTo(UiKit.RefHeight - 1e-3f), s + " height");
            }
        }

        [Test]
        public void WaveC_CardRowScalesOnlyWhenTheSafeAreaIsNarrower()
        {
            Assert.AreEqual(1f, MenuScreen.CardRowScale(1080f), 1e-6f);
            Assert.AreEqual(1f, MenuScreen.CardRowScale(MenuScreen.CardRowWidth + MenuScreen.CardRowMargin), 1e-6f);
            Assert.AreEqual((900f - 32f) / 962f, MenuScreen.CardRowScale(900f), 1e-5f, "a horizontal inset shrinks the row");
            Assert.AreEqual(1f, MenuScreen.CardRowScale(0f), 1e-6f, "unknown width");
            Assert.AreEqual(1f, MenuScreen.CardRowScale(float.NaN), 1e-6f);
            // The row covers the selected card scaled up with its rim: 2 x (320 + (145 + 7) x 1.06) = 962.
            float halfRow = MenuScreen.CardSpacing + (MenuScreen.CardWidth * 0.5f + MenuScreen.CardRim) * MenuScreen.SelectedCardScale;
            Assert.AreEqual(MenuScreen.CardRowWidth * 0.5f, halfRow, 0.5f);
        }

        [Test]
        public void WaveC_MenuResultsAndPauseLayoutsStayApartAtTheCheckedAspects()
        {
            foreach (Vector2 s in Screens)
            {
                Vector2 c = UiKit.CanvasSizeFor(s.x, s.y);
                float unitsPerPixel = c.x / s.x;

                // Menu: the title (TopCenter) stays above the 'Biome' label (BottomCenter) with room to spare.
                float titleBottom = c.y - (MenuScreen.TitleYFor(c.y) + MenuScreen.TitleHeight * 0.5f);
                float labelTop = MenuScreen.CardsY + MenuScreen.CardHeight * 0.5f + 52f + MenuScreen.BiomeLabelHeight * 0.5f;
                Assert.That(titleBottom - labelTop, Is.GreaterThanOrEqualTo(60f), s + " title vs Biome label");
                // Every card rim at least 8 px from the screen edge.
                float halfRow = MenuScreen.CardRowWidth * 0.5f * MenuScreen.CardRowScale(c.x);
                Assert.That((c.x * 0.5f - halfRow) / unitsPerPixel, Is.GreaterThanOrEqualTo(8f), s + " card rim to the edge (px)");

                // Results: the lowest line of a full stack (2-line cause, 2-line WHY, 2-line stats, tag) stays above REJOUER.
                ResultsScreen.LineStack stack = ResultsScreen.StackLines(132f, 120f, 104f);
                float replayTopFromTop = -(c.y - (ResultsScreen.ReplayY + ResultsScreen.ReplaySize.y * 0.5f + 6f));
                Assert.That(stack.Bottom, Is.GreaterThan(replayTopFromTop), s + " results stack vs REJOUER");

                // Pause: the title stays below the HUD timer.
                float timerBottomFromCenter = c.y * 0.5f - (Hud.TopBarY + Hud.TopBarHeight * 0.5f);
                float titleTop = PausePanel.TitleY + PausePanel.TitleHeight * 0.5f;
                Assert.That(timerBottomFromCenter - titleTop, Is.GreaterThanOrEqualTo(100f), s + " pause title vs HUD timer");
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // rules-02: toasts.

        [Test]
        public void WaveC_ToastLayoutNeverScalesBelowTheMinimumAndAlwaysFits()
        {
            var widths = new List<float> { 600f, 800f, 966f, 1080f, 1440f, 3413f };
            for (float tw = 300f; tw <= 3200f; tw += 100f)
            {
                foreach (float sw in widths)
                {
                    foreach (bool board in new[] { false, true })
                    {
                        Hud.ToastPlacement p = Hud.ToastLayout(sw, tw, board);
                        string at = "safe " + sw + " toast " + tw + " board " + board;
                        Assert.That(p.Scale, Is.GreaterThanOrEqualTo(Hud.MinToastScale - 1e-6f), at);
                        Assert.That(p.Scale, Is.LessThanOrEqualTo(1f + 1e-6f), at);
                        Rect r = p.Bounds;
                        Assert.That(r.xMin, Is.GreaterThanOrEqualTo(-sw * 0.5f + 16f - 1e-3f), at + " left edge on screen");
                        Assert.That(r.xMax, Is.LessThanOrEqualTo(sw * 0.5f - 16f + 1e-3f), at + " right edge on screen");
                        if (p.Wrap)
                        {
                            Assert.AreEqual(1f, p.Scale, 1e-6f, at);
                            Assert.AreEqual(sw - Hud.ToastWrapMargin, p.Size.x, 1e-3f, at);
                            Assert.AreEqual(Hud.ToastWrapHeight, p.Size.y, 1e-3f, at);
                            Assert.That(tw * Hud.MinToastScale, Is.GreaterThan(sw - Hud.ToastSideMargin), at + " wraps only when needed");
                        }
                        else Assert.AreEqual(tw, p.Size.x, 1e-3f, at);
                        if (!board) Assert.AreEqual(new Vector2(0f, Hud.ToastY), p.Position, at);
                    }
                }
            }
        }

        [Test]
        public void WaveC_ToastLayoutNeverOverlapsTheOpenBoard()
        {
            foreach (float sw in new[] { 600f, 966f, 1080f, 1440f, 3413f })
            {
                Rect board = Hud.BoardRect(sw);
                Assert.AreEqual(sw * 0.5f - Hud.BoardRight, board.xMax, 1e-3f);
                Assert.AreEqual(-Hud.BoardTop, board.yMax, 1e-3f);
                Assert.AreEqual(-Hud.BoardTop - Hud.BoardHeight, board.yMin, 1e-3f);
                for (float tw = 300f; tw <= 3200f; tw += 50f)
                {
                    Hud.ToastPlacement p = Hud.ToastLayout(sw, tw, true);
                    Assert.IsFalse(p.Bounds.Overlaps(board), "safe " + sw + " toast " + tw + " covers the board");
                }
            }
            // Portrait phone: a toast moves just below the board, centered.
            Hud.ToastPlacement below = Hud.ToastLayout(1080f, 700f, true);
            Assert.AreEqual(0f, below.Position.x, 1e-4f, "centered");
            Assert.AreEqual(Hud.BoardRect(1080f).yMin - Hud.ToastGap - Hud.ToastHeight * 0.5f, below.Position.y, 1e-3f);
            // Landscape: a short toast clears the board on the right and keeps its usual height.
            Hud.ToastPlacement wide = Hud.ToastLayout(3413f, 900f, true);
            Assert.AreEqual(new Vector2(0f, Hud.ToastY), wide.Position);
        }

        [Test]
        public void WaveC_ToastLayoutAvoidsTheTutorialBubbleBelowTheBoard()
        {
            // The bubble spans -470 .. -660 (BubbleY -560, 180 high, plus its shadow): the toast goes below it.
            Hud.ToastPlacement p = Hud.ToastLayout(1080f, 700f, true, -470f, -660f);
            Rect r = p.Bounds;
            Assert.That(r.yMax, Is.LessThanOrEqualTo(-660f - Hud.ToastGap + 1e-3f), "below the bubble");
            Assert.IsFalse(r.Overlaps(Hud.BoardRect(1080f)));
            // No bubble: just below the board.
            Hud.ToastPlacement q = Hud.ToastLayout(1080f, 700f, true, float.NaN, float.NaN);
            Assert.That(q.Bounds.yMax, Is.EqualTo(Hud.BoardRect(1080f).yMin - Hud.ToastGap).Within(1e-3f));
        }

        [Test]
        public void WaveC_TheSavedLineStaysReadable()
        {
            // The FR saved line is about 1214 units wide: on a 1080 canvas it stays on one line at 0.857 (was 0.38 left of
            // the open board); text height 44 x 0.857 = 37.7 units, 18.9 px at 960 px height.
            Hud.ToastPlacement p = Hud.ToastLayout(1080f, 1214f, true);
            Assert.IsFalse(p.Wrap);
            Assert.AreEqual(1040f / 1214f, p.Scale, 1e-4f);
            // On a narrow safe width (966 units, the old match 0.5 canvas of a 432 x 960 window) it wraps instead of shrinking.
            Hud.ToastPlacement n = Hud.ToastLayout(966f, 1214f, true);
            Assert.IsTrue(n.Wrap);
            Assert.AreEqual(1f, n.Scale, 1e-6f);
        }

        // ------------------------------------------------------------------------------------------------------------
        // rules-11: attract cover.

        [Test]
        public void WaveC_AttractCoverRisesWhileEndedHoldsThenFallsAfterTheRestart()
        {
            const float dt = 1f / 60f;
            float a = 0f;
            float inf = float.PositiveInfinity;
            Assert.AreEqual(0f, MenuScreen.AttractCoverAlpha(false, inf, 0f, dt), 1e-6f, "playing: clear");
            a = MenuScreen.AttractCoverAlpha(true, inf, a, 0.1f);
            Assert.AreEqual(0.17f, a, 1e-4f, "0.85 over 0.5 s");
            for (int k = 0; k < 60; k++) a = MenuScreen.AttractCoverAlpha(true, inf, a, dt);
            Assert.AreEqual(MenuScreen.AttractCoverMax, a, 1e-5f, "reaches 0.85");
            for (int k = 0; k < 90; k++) a = MenuScreen.AttractCoverAlpha(true, inf, a, dt);
            Assert.AreEqual(MenuScreen.AttractCoverMax, a, 1e-5f, "holds while ended");
            // Restart: hold for 0.2 s, then fall to 0 over 0.5 s, never in one frame.
            float t = 0f;
            float prev = a;
            for (int k = 1; k <= 11; k++)   // up to 0.183 s after the restart
            {
                t = k * dt;
                a = MenuScreen.AttractCoverAlpha(false, t, a, dt);
                Assert.AreEqual(prev, a, 1e-6f, "holds during the restart delay (t " + t + ")");
            }
            int frames = 0;
            while (a > 0f && frames < 1000)
            {
                t += dt;
                float next = MenuScreen.AttractCoverAlpha(false, t, a, dt);
                Assert.That(a - next, Is.LessThanOrEqualTo(MenuScreen.AttractCoverMax * dt / MenuScreen.AttractCoverFadeSeconds + 1e-5f), "no pop");
                a = next;
                frames++;
            }
            Assert.AreEqual(0f, a, 1e-6f);
            Assert.That(frames, Is.InRange(29, 32), "about 0.5 s at 60 fps");
        }

        [Test]
        public void WaveC_AttractCoverSealsBeforeTheRestartSoTheSwapIsNeverSeen()
        {
            const float dt = 1f / 60f;
            float a = 0f, ended = 0f;
            float sealAt = GameSession.AttractRestartDelay - MenuScreen.AttractCoverSealLead;
            while (ended + dt < sealAt - 1e-3f)
            {
                ended += dt;
                a = MenuScreen.AttractCoverAlpha(true, ended, float.PositiveInfinity, a, dt);
            }
            Assert.AreEqual(MenuScreen.AttractCoverMax, a, 1e-5f, "0.85 until the seal starts");
            float prev = a;
            while (ended < GameSession.AttractRestartDelay - 0.1f)
            {
                ended += dt;
                a = MenuScreen.AttractCoverAlpha(true, ended, float.PositiveInfinity, a, dt);
                Assert.That(a - prev, Is.LessThanOrEqualTo(0.15f * dt / MenuScreen.AttractCoverSealSeconds + 1e-5f), "smooth seal");
                prev = a;
            }
            Assert.AreEqual(1f, a, 1e-5f, "opaque before the attract restart");
            // After the restart the opaque cover holds, then fades the new match in without a jump.
            float t = 0f;
            for (int k = 0; k < 11; k++)
            {
                t += dt;
                a = MenuScreen.AttractCoverAlpha(false, 0f, t, a, dt);
            }
            Assert.AreEqual(1f, a, 1e-5f);
            int frames = 0;
            while (a > 0f && frames < 1000)
            {
                t += dt;
                float next = MenuScreen.AttractCoverAlpha(false, 0f, t, a, dt);
                Assert.That(a - next, Is.LessThanOrEqualTo(MenuScreen.AttractCoverMax * dt / MenuScreen.AttractCoverFadeSeconds + 1e-5f));
                a = next;
                frames++;
            }
            Assert.That(frames, Is.InRange(34, 38), "about 0.6 s at 60 fps");
        }

        // ------------------------------------------------------------------------------------------------------------
        // feel-11: results stack.

        [Test]
        public void WaveC_ResultsStackLeavesNoEmptyWhySlot()
        {
            // Caught round: two-line cause (48 px font), no WHY, one-line stats.
            ResultsScreen.LineStack s = ResultsScreen.StackLines(131f, 0f, 52f);
            float causeBottom = s.CauseY - 131f * 0.5f;
            float statsTop = s.StatsY + 52f * 0.5f;
            Assert.AreEqual(ResultsScreen.CauseTop - 131f * 0.5f, s.CauseY, 1e-3f, "the cause top is fixed");
            Assert.AreEqual(ResultsScreen.LineGap, causeBottom - statsTop, 1e-3f);
            Assert.That(causeBottom - statsTop, Is.LessThanOrEqualTo(80f), "no band over 40 px at 960 px height");
            // With a WHY line the stats move down by exactly its height plus one gap.
            ResultsScreen.LineStack w = ResultsScreen.StackLines(131f, 60f, 52f);
            Assert.That(w.WhyY, Is.LessThan(w.CauseY));
            Assert.That(w.StatsY, Is.LessThan(w.WhyY));
            Assert.AreEqual(60f + ResultsScreen.LineGap, s.StatsY - w.StatsY, 1e-3f);
            Assert.AreEqual(w.StatsY - 52f * 0.5f - ResultsScreen.TagGap - ResultsScreen.TagHeight * 0.5f, w.TagY, 1e-3f);
            Assert.AreEqual(880f, ResultsScreen.ParagraphWidth, 1e-6f);
            Assert.AreEqual(0.86f, ResultsScreen.DimAlpha, 1e-6f);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Built hierarchy: feel-06, chevron, perf-08.

        [Test]
        public void WaveC_BuiltUiHasTheScrimCoverOpaqueFacesAndOutlinedChevron()
        {
            BiomeId saved = BiomeTheme.Current.Id;
            BiomeTheme.SetCurrent(BiomeId.Liquid);
            UiRoot ui = UiRoot.Create(null);
            try
            {
                MenuScreen menu = ui.Menu;
                Assert.IsNotNull(menu);
                Transform canvas = menu.CanvasRect;
                Assert.AreEqual("AttractCover", canvas.GetChild(0).name, "the cover is the first sibling (over the world, under the shades)");
                Image cover = canvas.GetChild(0).GetComponent<Image>();
                Assert.IsFalse(cover.raycastTarget);
                Assert.AreEqual(0f, menu.AttractCoverValue, 1e-6f);

                Transform scrim = menu.Safe.GetChild(0);
                Assert.AreEqual("CardsScrim", scrim.name, "the scrim is drawn before every content element");
                Image scrimImg = scrim.GetComponent<Image>();
                Assert.IsFalse(scrimImg.raycastTarget);
                Assert.AreEqual(MenuScreen.ScrimAlpha, scrimImg.color.a, 1e-4f);
                Assert.AreEqual(Image.Type.Sliced, scrimImg.type);
                Assert.AreEqual(UiKit.SoftBandFeatherPixels, scrimImg.sprite.border.y, 1e-3f, "feathered bottom");
                Assert.AreEqual(UiKit.SoftBandFeatherPixels, scrimImg.sprite.border.w, 1e-3f, "feathered top");

                menu.Tick(1f / 60f);
                for (int i = 0; i < BiomeTheme.Count; i++)
                {
                    Transform face = menu.Safe.Find("CardRow/BiomeCard" + i + "/Face");
                    Assert.IsNotNull(face, "card " + i + " in the CardRow");
                    if ((BiomeId)i == BiomeId.Liquid) continue;
                    Assert.AreEqual(1f, face.GetComponent<Image>().color.a, 1e-6f, "unselected card face is opaque");
                }

                Transform chevron = ui.Hud.Safe.Find("RivalArea/Chevron");
                Assert.IsNotNull(chevron);
                Assert.AreEqual(Hud.ChevronSize, ((RectTransform)chevron).sizeDelta);
                Assert.AreEqual(Hud.ChevronAlpha, chevron.GetComponent<Image>().color.a, 1e-4f);
                Outline o = chevron.GetComponent<Outline>();
                Assert.IsNotNull(o, "navy outline");
                Assert.AreEqual(0.8f, o.effectColor.a, 1e-4f);
                Assert.AreEqual(new Vector2(2f, -2f), o.effectDistance);

                Image dim = ui.Results.CanvasRect.GetChild(0).GetComponent<Image>();
                Assert.AreEqual(ResultsScreen.DimAlpha, dim.color.a, 1e-4f, "darker results dim");
            }
            finally
            {
                Object.DestroyImmediate(ui.gameObject);
                BiomeTheme.SetCurrent(saved);
            }
        }

        [Test]
        public void WaveC_OnlyTheSelectedPreviewAnimatesAt15PerSecond()
        {
            BiomeId saved = BiomeTheme.Current.Id;
            BiomeTheme.SetCurrent(BiomeId.Fire);
            UiRoot ui = UiRoot.Create(null);
            try
            {
                MenuScreen menu = ui.Menu;
                Assert.IsTrue(menu.Visible, "the menu shows at boot");
                var before = new int[BiomeTheme.Count];
                for (int i = 0; i < before.Length; i++)
                {
                    before[i] = menu.PreviewPaintCount((BiomeId)i);
                    Assert.AreEqual(1, before[i], "one still frame painted at creation");
                }
                for (int k = 0; k < 60; k++) menu.Tick(1f / 60f);
                Assert.AreEqual(15, menu.PreviewPaintCount(BiomeId.Fire) - before[(int)BiomeId.Fire], "selected: 15 paints in 1 s");
                Assert.AreEqual(0, menu.PreviewPaintCount(BiomeId.Liquid) - before[(int)BiomeId.Liquid], "unselected: still");
                Assert.AreEqual(0, menu.PreviewPaintCount(BiomeId.Electric) - before[(int)BiomeId.Electric], "unselected: still");

                // A new selection: the old card repaints once (its still frame), the new one animates.
                int fire = menu.PreviewPaintCount(BiomeId.Fire), elec = menu.PreviewPaintCount(BiomeId.Electric);
                BiomeTheme.SetCurrent(BiomeId.Electric);
                for (int k = 0; k < 60; k++) menu.Tick(1f / 60f);
                Assert.AreEqual(1, menu.PreviewPaintCount(BiomeId.Fire) - fire, "the deselected card keeps one still frame");
                Assert.AreEqual(15, menu.PreviewPaintCount(BiomeId.Electric) - elec);

                byte[] mask = BiomePreview.CornerMask;
                Assert.AreSame(mask, BiomePreview.CornerMask, "the corner mask is computed once");
                Assert.AreEqual(0, mask[0], "corner pixel transparent");
                Assert.AreEqual(255, mask[(BiomePreview.Height / 2) * BiomePreview.Width + BiomePreview.Width / 2], "center opaque");
            }
            finally
            {
                Object.DestroyImmediate(ui.gameObject);
                BiomeTheme.SetCurrent(saved);
            }
        }

        private static void AssertSize(Vector2 expected, Vector2 actual, string message)
        {
            Assert.AreEqual(expected.x, actual.x, 0.01f, message + " (width)");
            Assert.AreEqual(expected.y, actual.y, 0.01f, message + " (height)");
        }
    }
}
