using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// BIGBUTTONS (docs/next/progress/BIGBUTTONS.md): the touch layout of the fail, win and end panels' buttons. While
    /// <see cref="TouchLayout.Active"/> holds, each panel's button row becomes a bottom bar: anchored to the bottom of the
    /// screen just above its safe area, with taller and wider plates and bigger labels (the primary action still first,
    /// larger and bold). The fail panel's text lines keep their places above the bar. STARSANIM: the win panel's and end
    /// screen's lines (the title, the hero stars, the time, the record line, the hints) form one centred column in both
    /// layouts (HudWinStars.cs), lifted clear of the bar and of the safe area; this file only asks for it again. Without
    /// touch, the rows are exactly the PC rows (<see cref="PlaceButtons"/>).
    /// </summary>
    public sealed partial class Hud
    {
        // The bottom bar (1920 x 1080 reference units). The win row (580 + 2 x 470 + 2 x 32 = 1584) fits a 4:3 tablet's
        // 1663 unit wide canvas with about 40 to spare on each side; its plates are 190 to 210 units tall, about a fifth of
        // a phone's height in landscape (966 units at 20:9). Its top (238 above the bottom edge plus the safe area) stays
        // under the fail panel's hint (its box ends at -140) and, STARSANIM, under the win column's lowest box (HudWinStars.cs
        // lifts the column when a short canvas or a bottom safe inset brings the bar up).
        private const float TouchPanelPrimaryWidth = 580f;
        private const float TouchPanelPrimaryHeight = 210f;
        private const float TouchPanelButtonWidth = 470f;
        private const float TouchPanelButtonHeight = 190f;
        private const float TouchPanelGap = 32f;
        private const float TouchPanelBottom = 28f;
        private const int TouchPanelPrimaryFontSize = 64;
        private const int TouchPanelFontSize = 54;
        // The menu button's label size (MenuButton): the PC size of every secondary panel button.
        private const int PanelFontSize = 42;

        private readonly TouchLayout.Watch panelTouch = new TouchLayout.Watch();
        // The safe area's bottom margin in reference units, read when the touch layout is applied (zero in the PC layout).
        private float panelSafeBottom;

        /// <summary>BIGBUTTONS: the panels' buttons are laid out for touch now (a bottom bar).</summary>
        public bool TouchLayoutOn => panelTouch.Touch;

        /// <summary>Lays the panels' buttons out again when the touch layout switch says so (<see cref="TouchLayout.Watch"/>).</summary>
        private void RefreshPanelLayout()
        {
            if (panelTouch.Changed())
            {
                ApplyPanelLayout();
            }
        }

        /// <summary>
        /// Every panel's row for the current layout, shown or not (so the fail and win primaries always share one size), and
        /// the win column (STARSANIM: lifted for the bar's top and the safe area, HudWinStars.cs). The win row follows its next
        /// level the way <see cref="ShowWin(float, bool)"/> placed it.
        /// </summary>
        private void ApplyPanelLayout()
        {
            panelSafeBottom = panelTouch.Touch ? TouchLayout.SafeInsets().z : 0f;
            if (FailRetryButton != null && FailMenuButton != null)
            {
                PlaceRow(FailRetryButton, FailMenuButton);
            }
            PlaceWinRow();
            if (EndReplayButton != null && EndButton != null)
            {
                PlaceButtons(EndButton, EndReplayButton, EndButton);
            }
            LayoutWinColumn();
        }

        /// <summary>
        /// The win row: Next level, Replay and Menu with a next level; otherwise Replay and Menu close up into a centred row
        /// (Next level, hidden then, keeps the primary size alone).
        /// </summary>
        private void PlaceWinRow()
        {
            if (WinReplayButton == null || WinMenuButton == null || WinNextLevelButton == null)
            {
                return;
            }
            if (winNextOn)
            {
                PlaceRow(WinNextLevelButton, WinReplayButton, WinMenuButton);
            }
            else
            {
                PlaceButtons(WinNextLevelButton, WinNextLevelButton);
                PlaceButtons(null, WinReplayButton, WinMenuButton);
            }
        }

        /// <summary>A panel button's plate width for the current layout.</summary>
        private float PanelWidth(bool primary) => panelTouch.Touch
            ? primary ? TouchPanelPrimaryWidth : TouchPanelButtonWidth
            : primary ? PanelPrimaryWidth : PanelButtonWidth;

        /// <summary>A panel button's plate height for the current layout.</summary>
        private float PanelHeight(bool primary) => panelTouch.Touch
            ? primary ? TouchPanelPrimaryHeight : TouchPanelButtonHeight
            : primary ? PanelPrimaryHeight : PanelButtonHeight;

        /// <summary>The gap between two plates of a row for the current layout.</summary>
        private float PanelGap => panelTouch.Touch ? TouchPanelGap : PanelButtonGap;

        /// <summary>Sets a panel button's label size for its role and the current layout (PC: 50 primary, 42 otherwise).</summary>
        private void SizePanelLabel(Button button, bool primary)
        {
            Text label = button.GetComponentInChildren<Text>(true);
            if (label != null)
            {
                label.fontSize = panelTouch.Touch
                    ? primary ? TouchPanelPrimaryFontSize : TouchPanelFontSize
                    : primary ? PanelPrimaryFontSize : PanelFontSize;
            }
        }

        /// <summary>
        /// Places one plate of a row: in the PC layout centred on the panel at <see cref="PanelButtonY"/>; in the touch
        /// layout its bottom edge <see cref="TouchPanelBottom"/> above the screen's bottom edge plus the safe area.
        /// <paramref name="centerX"/> is the plate's centre from the panel's centre.
        /// </summary>
        private void PlacePanelButton(Button button, float centerX, float width, float height)
        {
            if (panelTouch.Touch)
            {
                TouchLayout.Place((RectTransform)button.transform, new Vector2(0.5f, 0f),
                    new Vector2(centerX, TouchPanelBottom + panelSafeBottom), new Vector2(width, height));
            }
            else
            {
                Place((RectTransform)button.transform, new Vector2(0.5f, 0.5f), new Vector2(centerX, PanelButtonY), new Vector2(width, height));
            }
        }
    }
}
