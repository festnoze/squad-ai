using OutOfSight.Core;
using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// STARSANIM (docs/next/progress/STARSANIM.md): the win panel's and end screen's column with the stars as its hero, and
    /// the glue to their reveal (<see cref="WinStarsView"/>). One centred column in both layouts, from the top: the title, the
    /// three big stars, "New stars!", then four rows (win panel: the time, the record line, the hint, win.next; end screen:
    /// end.body, the time, the record line, the hint), then the buttons (PC: the centred row at <see cref="PanelButtonY"/>;
    /// touch: the bottom bar, HudTouchLayout.cs). The column keeps its spacing and moves up or down as a whole
    /// (<see cref="ColumnLift"/>): centred between the top of the screen and the buttons, always clear of the touch bar and
    /// of <see cref="Screen.safeArea"/>; it fits 16:9, 20:9, 21:9 (943 units high, the shortest) and 4:3 (1663 wide, the narrowest).
    /// The reveal plays once per win, in unscaled time; a tap, a click, Enter, Space or gamepad A completes it at once
    /// (<see cref="InputReader.SkipPressed"/>), and a menu opened over the panel settles it silently. The buttons are up and
    /// usable from the panel's first frame, keyboard and gamepad focus as before (Menu selects the end screen's Menu
    /// principal and the fail panel's Retry; the win panel selects nothing, Enter loads the next level through GameState).
    /// </summary>
    public sealed partial class Hud
    {
        // The column (reference units from the screen centre, before the lift). Text boxes never overlap one another, nor the
        // buttons: the tests compare the boxes, which are 1600 wide, so each line keeps a band of its own.
        private const float ColumnTitleY = 335f;
        private const float ColumnTitleHeight = 150f;
        // The middle star's centre (the box of the row: the side stars' centres are 16 lower, WinStarsView.MiddleRaise).
        private const float ColumnStarsY = 156f;
        private const float ColumnNewStarsY = 33f;
        private const float ColumnNewStarsHeight = 34f;
        private const int ColumnNewStarsSize = 30;
        private const float ColumnRow0Y = -18f;
        private const float ColumnRow0Height = 60f;
        private const float ColumnRow1Y = -75f;
        private const float ColumnRow2Y = -125f;
        private const float ColumnRow3Y = -175f;
        /// <summary>STARSANIM: the height of the column's rows 1 to 3 (the record line's box uses it too).</summary>
        public const float ColumnRowHeight = 46f;
        private const float ColumnTop = ColumnTitleY + ColumnTitleHeight * 0.5f;
        private const float ColumnBottom = ColumnRow3Y - ColumnRowHeight * 0.5f;
        // The least room between the column's lowest box and the touch bar's top, and the PC lift's ceiling (a 4:3 window
        // would otherwise float the column far above its buttons).
        private const float ColumnClearance = 12f;
        private const float ColumnPcLiftMax = 80f;
        private const float StarsTextWidth = 900f;

        // Stars (idea 5, docs/next/progress/STARS.md; STARSANIM): the hero row and the "New stars!" line under it.
        // RecordLine shows them once it recorded the win (ShowWinStars).
        private WinStarsView winStars;
        private Text winStarsNew;
        private float columnLift;
        private float columnLaidFor;

        /// <summary>STARSANIM: the win panel's hero star row (tests read its count, images, reveal state and timeline).</summary>
        public WinStarsView WinStars => winStars;

        /// <summary>The star row shows on screen: a visible win panel with stars set for the win just recorded.</summary>
        public bool WinStarsVisible => WinVisible && winStars != null && winStars.Shown;

        /// <summary>"New stars!" shows under the row (this win raised the saved count; it fades in after the last star).</summary>
        public bool WinStarsNewVisible => WinStarsVisible && winStarsNew != null && winStarsNew.enabled;

        /// <summary>STARSANIM: the stars' reveal is playing on the visible win panel (AdDirector waits for its end).</summary>
        public bool StarsAnimating => WinVisible && winStars != null && winStars.Revealing;

        /// <summary>STARSANIM: completes the reveal as a tap would (every earned star filled, one chime at most). Tests.</summary>
        public void CompleteStarsAnimation()
        {
            winStars?.Complete(true);
        }

        /// <summary>STARSANIM: bumped each time the column is laid out again (RecordLine follows it).</summary>
        public int WinLayoutStamp { get; private set; }

        /// <summary>STARSANIM: the record line's row in the column (under the time; under the end time on the end screen).</summary>
        public float RecordRowY(bool endScreen) => (endScreen ? ColumnRow2Y : ColumnRow1Y) + columnLift;

        /// <summary>Init: the hero row and "New stars!", both hidden until RecordLine shows them for a recorded win.</summary>
        private void BuildWinStars()
        {
            winStars = new WinStarsView(winCanvas.transform, "WinStars", OnStarFilled, OnStarMissed);
            winStarsNew = NewText(winCanvas.transform, "WinStarsNew", Strings.StarsNewBest, ColumnNewStarsSize, TextAnchor.MiddleCenter, Stars.Gold);
            winStarsNew.enabled = false;
        }

        /// <summary>
        /// Shows <paramref name="count"/> stars at the centre of the win panel (the end screen too) and starts their reveal,
        /// with "New stars!" under them when <paramref name="newBest"/>. Called by RecordLine once the win is recorded;
        /// ShowWin and HidePanels hide the row. STARSANIM: a second call for the same win and count (a refresh) keeps the
        /// row as it is, never replaying the reveal. <paramref name="endScreen"/> is kept for the callers: the column follows
        /// the panel's own state.
        /// </summary>
        public void ShowWinStars(int count, bool newBest, bool endScreen)
        {
            if (winStars == null)
            {
                return;
            }
            if (!winStars.Shown || winStars.Count != Mathf.Clamp(count, 0, Tuning.StarsPerLevel))
            {
                winStars.Set(count, true);
            }
            LayoutWinColumn();
            if (winStarsNew != null)
            {
                winStarsNew.text = Strings.StarsNewBest;
                winStarsNew.enabled = newBest;
                Color c = winStarsNew.color;
                c.a = winStars.AfterAlpha;
                winStarsNew.color = c;
            }
            ApplyCanvases();
        }

        private void HideWinStars()
        {
            winStars?.Hide();
            if (winStarsNew != null)
            {
                winStarsNew.enabled = false;
            }
        }

        /// <summary>
        /// Every frame (unscaled <paramref name="dt"/>): the column follows the canvas's height, and the reveal advances. A
        /// skip press completes it; a menu over the panel (the HUD hidden) settles it silently, so it never replays nor rings
        /// over the menu.
        /// </summary>
        private void UpdateWinStars(float dt)
        {
            if (!winOn || winStars == null)
            {
                return;
            }
            if (Mathf.Abs(CanvasUnitsHeight() - columnLaidFor) > 0.5f)
            {
                LayoutWinColumn();
            }
            if (!Visible)
            {
                if (winStars.Revealing || winStars.ChimeOwed)
                {
                    winStars.Silence();
                }
                return;
            }
            if (winStars.Revealing && InputReader.SkipPressed())
            {
                winStars.Complete(true);
            }
            winStars.Animate(dt);
            if (winStarsNew != null && winStarsNew.enabled)
            {
                Color c = winStarsNew.color;
                float a = winStars.AfterAlpha;
                if (c.a != a)
                {
                    c.a = a;
                    winStarsNew.color = c;
                }
            }
        }

        /// <summary>
        /// Places the column's lines and the star row for the current layout and canvas: the win panel's title, time, hint and
        /// win.next, or the end screen's title, end.body, time and hint (the record line follows through
        /// <see cref="RecordRowY"/> and <see cref="WinLayoutStamp"/>). Never touches the fail panel.
        /// </summary>
        private void LayoutWinColumn()
        {
            if (winCanvas == null)
            {
                return;
            }
            float height = CanvasUnitsHeight();
            columnLaidFor = height;
            columnLift = ColumnLift(height);
            float lift = columnLift;
            PlaceColumnText(winTitle, ColumnTitleY + lift, ColumnTitleHeight, 1600f);
            PlaceColumnText(winBody, ColumnRow0Y + lift, ColumnRow0Height, 1600f);
            winStars?.Place(ColumnStarsY + lift);
            PlaceColumnText(winStarsNew, ColumnNewStarsY + lift, ColumnNewStarsHeight, StarsTextWidth);
            PlaceColumnText(endTime, ColumnRow1Y + lift, ColumnRowHeight, 1600f);
            PlaceColumnText(winAction, (endOn ? ColumnRow3Y : ColumnRow2Y) + lift, ColumnRowHeight, 1600f);
            PlaceColumnText(winNext, ColumnRow3Y + lift, ColumnRowHeight, 1600f);
            WinLayoutStamp++;
        }

        private static void PlaceColumnText(Text text, float y, float height, float width)
        {
            if (text != null)
            {
                Place(text.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, y), new Vector2(width, height));
            }
        }

        /// <summary>
        /// How far the column moves up (reference units): centred between the top of the screen (under its safe area) and the
        /// buttons' top. Touch: never lower than <see cref="ColumnClearance"/> above the bottom bar (whose top rises with the
        /// safe area). PC: between 0 and <see cref="ColumnPcLiftMax"/> (26 at 21:9, 60 at 16:9).
        /// </summary>
        private float ColumnLift(float height)
        {
            float half = height * 0.5f;
            float columnMiddle = (ColumnTop + ColumnBottom) * 0.5f;
            if (panelTouch.Touch)
            {
                float top = half - TouchLayout.SafeInsets().w;
                float barTop = -half + TouchPanelBottom + panelSafeBottom + TouchPanelPrimaryHeight;
                float centred = (top + barTop) * 0.5f - columnMiddle;
                return Mathf.Max(centred, barTop + ColumnClearance - ColumnBottom);
            }
            float rowTop = PanelButtonY + PanelPrimaryHeight * 0.5f;
            return Mathf.Clamp((half + rowTop) * 0.5f - columnMiddle, 0f, ColumnPcLiftMax);
        }

        /// <summary>The HUD canvas's height in reference units (the CanvasScaler's), or the screen's before its first layout.</summary>
        private float CanvasUnitsHeight()
        {
            float h = ((RectTransform)transform).rect.height;
            return h > 100f ? h : TouchLayout.CanvasHeight();
        }

        /// <summary>The game's sounds (GameState's, else Main's), or null in a test HUD without them.</summary>
        private Sfx StarsSfx
        {
            get
            {
                if (Game != null && Game.Sfx != null)
                {
                    return Game.Sfx;
                }
                return Main.Instance != null ? Main.Instance.Sfx : null;
            }
        }

        /// <summary>A star filled: its chime, higher for each star, the third a chord.</summary>
        private void OnStarFilled(int index)
        {
            Sfx sfx = StarsSfx;
            if (sfx != null)
            {
                sfx.PlayStarChime(index);
            }
        }

        /// <summary>A star stayed empty: the soft dull tick.</summary>
        private void OnStarMissed(int index)
        {
            Sfx sfx = StarsSfx;
            if (sfx != null)
            {
                sfx.PlayStarDull();
            }
        }
    }
}
