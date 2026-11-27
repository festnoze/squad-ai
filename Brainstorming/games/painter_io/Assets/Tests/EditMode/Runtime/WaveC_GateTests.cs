// Owned by the wave C final gate. EditMode checks of the small fixes the gate made while resolving the packages' needs:
// the menu title band on tall screens (ui open issue) and the tutorial bubble lookup used by the HUD toasts (ui need).
// No test writes PlayerPrefs.
using NUnit.Framework;
using PainterIO.Runtime;
using UnityEngine;

namespace PainterIO.Tests
{
    public class WaveC_GateTests
    {
        [Test]
        public void WaveC_Gate_TitleStaysPutAt9x16AndCentersTheBandOnTallScreens()
        {
            Assert.AreEqual(MenuScreen.TitleY, MenuScreen.TitleYFor(1920f), 1e-4f, "9:16 unchanged (Gate B layout)");
            Assert.AreEqual(MenuScreen.TitleY, MenuScreen.TitleYFor(1500f), 1e-4f, "shorter safe area (notch insets, landscape) unchanged");
            Assert.AreEqual(MenuScreen.TitleY, MenuScreen.TitleYFor(0f), 1e-4f, "unknown height");
            Assert.AreEqual(MenuScreen.TitleY, MenuScreen.TitleYFor(float.NaN), 1e-4f, "unknown height");
            Assert.AreEqual(MenuScreen.TitleY + 240f, MenuScreen.TitleYFor(2400f), 1e-3f, "20:9: half of the 480 extra units");

            // On every tall canvas the title keeps at least the 9:16 distance to the 'Biome' label, and the gap above the
            // title grows by the same amount as the gap below it.
            float labelTopFromBottom = MenuScreen.CardsY + MenuScreen.CardHeight * 0.5f + 52f + MenuScreen.BiomeLabelHeight * 0.5f;
            float gapAt916 = 1920f - (MenuScreen.TitleY + MenuScreen.TitleHeight * 0.5f) - labelTopFromBottom;
            foreach (float h in new[] { 2133f, 2400f, 2520f })
            {
                float y = MenuScreen.TitleYFor(h);
                float gapBelow = h - (y + MenuScreen.TitleHeight * 0.5f) - labelTopFromBottom;
                Assert.That(gapBelow, Is.GreaterThanOrEqualTo(gapAt916 - 1e-3f), h + ": title vs Biome label");
                Assert.AreEqual(y - MenuScreen.TitleY, gapBelow - gapAt916, 1e-3f, h + ": extra height split above and below");
            }
        }

        [Test]
        public void WaveC_Gate_TutorialBubbleIsExposedForTheToastAvoidance()
        {
            UiRoot ui = UiRoot.Create(null);
            try
            {
                TutorialOverlay tut = ui.Tutorial;
                Assert.IsNotNull(tut);
                Assert.IsNotNull(tut.BubbleRect, "Hud reads the bubble rect through TutorialOverlay, not by child name");
                Assert.AreEqual(TutorialOverlay.BubbleWidth, tut.BubbleRect.sizeDelta.x, 1e-3f);
                Assert.AreEqual(TutorialOverlay.BubbleY, tut.BubbleRect.anchoredPosition.y, 1e-3f);
                Assert.AreEqual(0f, tut.BubbleAlpha, 1e-6f, "hidden at creation");
            }
            finally
            {
                Object.DestroyImmediate(ui.gameObject);
            }
        }
    }
}
