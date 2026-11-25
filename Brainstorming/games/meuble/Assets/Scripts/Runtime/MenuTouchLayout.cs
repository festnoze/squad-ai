using OutOfSight.Core;
using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// BIGBUTTONS (docs/next/progress/BIGBUTTONS.md): the touch layout of the menus. While <see cref="TouchLayout.Active"/>
    /// holds (a phone or tablet build, the -touch argument, a test's forced touch UI, or a finger last), the buttons grow
    /// to finger size (12 to 15 % of a phone's height in landscape) with bigger labels, and use the room they had left:
    /// <list type="bullet">
    /// <item>title page: a grid under the tagline, Jouer across the top, then Niveaux | Options and Crédits | Quitter; the
    /// author line moves to the bottom right corner; the Shop button (top right) grows too;</item>
    /// <item>pause menu: the same single column, much taller and wider, PAUSE moved up to make room;</item>
    /// <item>Options: two columns of tall rows (six, then five) instead of one column of eleven thin ones;</item>
    /// <item>Credits: a taller Retour, the scroll view a little shorter above it;</item>
    /// <item>Shop: <see cref="OutOfSight.ShopPage.SetTouchLayout"/>.</item>
    /// </list>
    /// Every left column keeps clear of the safe area (notch) and every bottom row of the bottom safe margin. The PC
    /// layout is remembered (<see cref="TouchLayout.Memory"/>) and put back exactly; names, labels and the up and down
    /// chains never change (the grids only add left and right links).
    /// </summary>
    public sealed partial class Menu
    {
        // The least room between the safe area's left edge and a column's left edge; the least room under a bottom row.
        private const float TouchSideGap = 40f;
        private const float TouchBottomMargin = 24f;
        // No touch row ever gets shorter than this, even on a screen shorter than a 21:9 phone.
        private const float TouchMinRowHeight = 96f;
        // A centred label's inset from its plate's sides.
        private const float TouchLabelInset = 16f;

        // Title page grid (1920 x 1080 reference, the column's left middle anchor): its top under the tagline (whose box
        // ends at y -3), three rows 126 high 20 apart, so its bottom (y -438) clears a 21:9 phone's bottom edge (-471);
        // two columns 430 wide 24 apart (Jouer spans both), well inside the title band (1240 wide).
        private const float TouchTitleTop = -20f;
        private const float TouchTitleRowHeight = 126f;
        private const float TouchTitleRowGap = 20f;
        private const float TouchTitleColumnWidth = 430f;
        private const float TouchTitleColumnGap = 24f;
        private const int TouchTitlePlayFontSize = 64;
        private const int TouchTitleFontSize = 56;
        // The author line in the bottom right corner (its PC place, bottom left, is under the grid's left column now).
        private const float TouchAuthorMargin = 40f;
        private const float TouchAuthorBottom = 22f;
        private static readonly Vector2 TouchShopButtonSize = new Vector2(420f, 116f);
        private const int TouchShopFontSize = 56;

        // Pause menu: PAUSE and its rule moved up, then the four buttons from y 190 down, 140 high 20 apart (bottom at
        // y -430), 680 wide so "Choix du niveau" (the spectator's Menu principal) fits at the bigger size.
        private const float TouchPauseTitleY = 318f;
        private const float TouchPauseRuleY = 228f;
        private const float TouchPauseTop = 190f;
        private const float TouchPauseButtonWidth = 680f;
        private const float TouchPauseButtonHeight = 140f;
        private const float TouchPauseGap = 20f;
        private const int TouchPauseFontSize = 60;
        private const float TouchColumnLabelLeft = 40f;
        private const float TouchColumnLabelRight = 24f;

        // Options: two columns 716 wide 28 apart (the right one ends at x 1610, inside a 4:3 tablet's 1663 unit canvas), six
        // rows 112 high 16 apart from y 350 (under the red rule) down to y -402, clear of the music credits line at the bottom
        // edge (its top 36 above it). The longest label, "Language / Langue : Français" at 38, fits between the bigger icon
        // and the arrows. The band widens behind both columns.
        private const float TouchOptionsTop = 350f;
        private const float TouchOptionsColumnWidth = 716f;
        private const float TouchOptionsColumnGap = 28f;
        private const float TouchOptionsRowHeight = 112f;
        private const float TouchOptionsRowGap = 16f;
        private const int TouchOptionsRows = 6;
        private const float TouchOptionsBottomClear = 52f;
        private const float TouchOptionsIconSize = 60f;
        private const float TouchOptionsIconInset = 16f;
        private const float TouchOptionsLabelOffset = 92f;
        private const float TouchOptionsArrowBand = 100f;
        private const int TouchOptionsFontSize = 38;
        // Par défaut and Retour keep the menu button's own label size (42) on PC: a little bigger than that.
        private const int TouchOptionsPlainFontSize = 46;
        private const float TouchBandWidth = 2400f;

        // Credits: Retour 480 x 112 (its centre at y -392, or higher above a bottom safe margin), the scroll view ending 14 above it.
        private static readonly Vector2 TouchCreditsBackSize = new Vector2(480f, 112f);
        private const float TouchCreditsBackY = -392f;
        private const float TouchCreditsGap = 14f;
        private const int TouchCreditsBackFontSize = 48;

        private readonly TouchLayout.Watch menuTouch = new TouchLayout.Watch();
        private readonly TouchLayout.Memory menuTouchMemory = new TouchLayout.Memory();

        /// <summary>BIGBUTTONS: the menus are laid out for touch now (bigger buttons, rearranged).</summary>
        public bool TouchLayoutOn => menuTouch.Touch;

        /// <summary>Lays the menus out again when the touch layout switch says so (<see cref="TouchLayout.Watch"/>).</summary>
        private void RefreshTouchLayout()
        {
            if (menuTouch.Changed())
            {
                ApplyTouchLayout(menuTouch.Touch);
            }
        }

        /// <summary>Back to the remembered PC layout, then (touch) every page's touch layout for the current safe area.</summary>
        private void ApplyTouchLayout(bool touch)
        {
            menuTouchMemory.Restore();
            Vector4 safe = touch ? TouchLayout.SafeInsets() : Vector4.zero;
            float half = TouchLayout.CanvasHeight() * 0.5f;
            if (touch)
            {
                LayoutTitleForTouch(safe, half);
                LayoutPauseForTouch(safe, half);
                LayoutOptionsForTouch(safe, half);
                LayoutCreditsForTouch(safe, half);
            }
            TitleGridNavigation(touch);
            OptionsColumnNavigation(touch);
            if (ShopPage != null)
            {
                ShopPage.SetTouchLayout(touch, safe, half);
            }
        }

        /// <summary>The left edge of a touch column: the PC margin, or further right past a notch.</summary>
        private static float TouchColumnX(float margin, Vector4 safe) => Mathf.Max(margin, safe.x + TouchSideGap);

        private void LayoutTitleForTouch(Vector4 safe, float half)
        {
            if (titleCanvas == null || PlayButton == null)
            {
                return;
            }
            float x = TouchColumnX(TitleMargin, safe);
            float bottom = -half + safe.z + TouchBottomMargin;
            float height = TouchLayout.FitRows(TouchTitleTop, bottom, 3, TouchTitleRowGap, TouchTitleRowHeight, TouchMinRowHeight);
            float step = height + TouchTitleRowGap;
            float firstY = TouchTitleTop - height * 0.5f;
            float wide = 2f * TouchTitleColumnWidth + TouchTitleColumnGap;
            float second = x + TouchTitleColumnWidth + TouchTitleColumnGap;
            GridButton(PlayButton, x, firstY, wide, height, TouchTitlePlayFontSize);
            GridButton(LevelsButton, x, firstY - step, TouchTitleColumnWidth, height, TouchTitleFontSize);
            GridButton(TitleOptionsButton, second, firstY - step, TouchTitleColumnWidth, height, TouchTitleFontSize);
            GridButton(TitleCreditsButton, x, firstY - 2f * step, TouchTitleColumnWidth, height, TouchTitleFontSize);
            GridButton(QuitButton, second, firstY - 2f * step, TouchTitleColumnWidth, height, TouchTitleFontSize);
            // The title, its rule and the tagline share the PC margin: they move only past a notch. (The animated logo
            // above them moves its own rect every frame, so it stays where it is.)
            float dx = x - TitleMargin;
            if (dx > 0f)
            {
                foreach (string name in new[] { "Title", "Rule", "Tagline" })
                {
                    Nudge(titleCanvas.transform.Find(name), dx);
                }
            }

            Transform author = titleCanvas.transform.Find("Credits");
            Text authorText = author != null ? author.GetComponent<Text>() : null;
            if (authorText != null)
            {
                menuTouchMemory.Keep(authorText);
                authorText.alignment = TextAnchor.MiddleRight;
                Place(authorText.rectTransform, new Vector2(1f, 0f), new Vector2(-(TouchAuthorMargin + safe.y), TouchAuthorBottom + safe.z),
                    authorText.rectTransform.sizeDelta);
            }
            if (TitleShopButton != null)
            {
                Place(menuTouchMemory.Keep((RectTransform)TitleShopButton.transform), new Vector2(1f, 1f),
                    new Vector2(-(ShopButtonMarginX + safe.y), -(ShopButtonMarginY + safe.w)), TouchShopButtonSize);
                if (Labels.TryGetValue(TitleShopButton.name + "Label", out Text label))
                {
                    menuTouchMemory.Keep(label).fontSize = TouchShopFontSize;
                }
            }
        }

        /// <summary>A title grid tile: its plate at (<paramref name="x"/>, <paramref name="y"/>) on the left middle anchor, its label centred.</summary>
        private void GridButton(Button button, float x, float y, float width, float height, int fontSize)
        {
            if (button == null)
            {
                return;
            }
            Place(menuTouchMemory.Keep((RectTransform)button.transform), new Vector2(0f, 0.5f), new Vector2(x, y), new Vector2(width, height));
            if (Labels.TryGetValue(button.name + "Label", out Text label))
            {
                menuTouchMemory.Keep(label);
                label.fontSize = fontSize;
                label.alignment = TextAnchor.MiddleCenter;
                label.rectTransform.offsetMin = new Vector2(TouchLabelInset, 0f);
                label.rectTransform.offsetMax = new Vector2(-TouchLabelInset, 0f);
            }
        }

        /// <summary>A column button (pause menu): its plate at (<paramref name="x"/>, <paramref name="y"/>), its label left aligned as on PC, bigger.</summary>
        private void TouchColumnButton(Button button, float x, float y, float width, float height, int fontSize)
        {
            if (button == null)
            {
                return;
            }
            Place(menuTouchMemory.Keep((RectTransform)button.transform), new Vector2(0f, 0.5f), new Vector2(x, y), new Vector2(width, height));
            if (Labels.TryGetValue(button.name + "Label", out Text label))
            {
                menuTouchMemory.Keep(label);
                label.fontSize = fontSize;
                label.rectTransform.offsetMin = new Vector2(TouchColumnLabelLeft, 0f);
                label.rectTransform.offsetMax = new Vector2(-TouchColumnLabelRight, 0f);
            }
        }

        /// <summary>Moves a remembered element right by <paramref name="dx"/> (past a notch).</summary>
        private void Nudge(Transform element, float dx)
        {
            if (element is RectTransform rect)
            {
                menuTouchMemory.Keep(rect).anchoredPosition += new Vector2(dx, 0f);
            }
        }

        /// <summary>Moves a remembered element's anchored position to <paramref name="position"/>.</summary>
        private void MoveTo(Transform element, Vector2 position)
        {
            if (element is RectTransform rect)
            {
                menuTouchMemory.Keep(rect).anchoredPosition = position;
            }
        }

        private void LayoutPauseForTouch(Vector4 safe, float half)
        {
            if (pauseCanvas == null || ResumeButton == null)
            {
                return;
            }
            float x = TouchColumnX(TitleMargin, safe);
            MoveTo(pauseCanvas.transform.Find("PauseTitle"), new Vector2(x, TouchPauseTitleY));
            MoveTo(pauseCanvas.transform.Find("PauseRule"), new Vector2(x + 4f, TouchPauseRuleY));
            float bottom = -half + safe.z + TouchBottomMargin;
            Button[] column = { ResumeButton, RestartButton, MainMenuButton, PauseOptionsButton };
            float height = TouchLayout.FitRows(TouchPauseTop, bottom, column.Length, TouchPauseGap, TouchPauseButtonHeight, TouchMinRowHeight);
            for (int i = 0; i < column.Length; i++)
            {
                TouchColumnButton(column[i], x, TouchPauseTop - height * 0.5f - i * (height + TouchPauseGap), TouchPauseButtonWidth, height,
                    TouchPauseFontSize);
            }
        }

        /// <summary>The Options page's buttons in their up and down order (value rows, then Par défaut and Retour).</summary>
        private Button[] OptionsOrder()
        {
            return new[]
            {
                OptionsSensitivityButton, OptionsVolumeButton, OptionsMusicButton, OptionsConeButton, OptionsWallsButton,
                OptionsWallOpacityButton, OptionsQualityButton, OptionsDifficultyButton, OptionsLanguageButton, OptionsResetButton,
                OptionsBackButton,
            };
        }

        private void LayoutOptionsForTouch(Vector4 safe, float half)
        {
            if (optionsCanvas == null || OptionsSensitivityButton == null)
            {
                return;
            }
            float x = TouchColumnX(Tuning.OptionsMargin, safe);
            float dx = x - Tuning.OptionsMargin;
            if (dx > 0f)
            {
                Nudge(optionsCanvas.transform.Find("OptionsTitle"), dx);
                Nudge(optionsCanvas.transform.Find("OptionsRule"), dx);
            }
            if (optionsCanvas.transform.Find("Band") is RectTransform band)
            {
                menuTouchMemory.Keep(band).sizeDelta = new Vector2(TouchBandWidth, 0f);
            }
            float bottom = Mathf.Max(-half + safe.z + TouchBottomMargin, -half + TouchOptionsBottomClear);
            float height = TouchLayout.FitRows(TouchOptionsTop, bottom, TouchOptionsRows, TouchOptionsRowGap, TouchOptionsRowHeight, TouchMinRowHeight);
            Button[] rows = OptionsOrder();
            for (int i = 0; i < rows.Length; i++)
            {
                int column = i < TouchOptionsRows ? 0 : 1;
                int row = i - column * TouchOptionsRows;
                float rowX = x + column * (TouchOptionsColumnWidth + TouchOptionsColumnGap);
                float rowY = TouchOptionsTop - height * 0.5f - row * (height + TouchOptionsRowGap);
                // Rows 0 to 8 cycle a value (their arrows at the right); Par défaut and Retour are plain.
                OptionsRowForTouch(rows[i], rowX, rowY, height, i < rows.Length - 2);
            }
        }

        /// <summary>One Options row in the touch grid: the plate, its bigger icon and its bigger label between the icon and the arrows.</summary>
        private void OptionsRowForTouch(Button button, float x, float y, float height, bool valueRow)
        {
            if (button == null)
            {
                return;
            }
            Place(menuTouchMemory.Keep((RectTransform)button.transform), new Vector2(0f, 0.5f), new Vector2(x, y),
                new Vector2(TouchOptionsColumnWidth, height));
            Transform icon = button.transform.Find(button.name + "Icon");
            if (icon is RectTransform iconRect)
            {
                Place(menuTouchMemory.Keep(iconRect), new Vector2(0f, 0.5f), new Vector2(TouchOptionsIconInset, 0f),
                    new Vector2(TouchOptionsIconSize, TouchOptionsIconSize));
            }
            if (Labels.TryGetValue(button.name + "Label", out Text label))
            {
                menuTouchMemory.Keep(label);
                label.fontSize = valueRow ? TouchOptionsFontSize : TouchOptionsPlainFontSize;
                if (valueRow || icon != null)
                {
                    label.rectTransform.offsetMin = new Vector2(TouchOptionsLabelOffset, 0f);
                    label.rectTransform.offsetMax = new Vector2(valueRow ? -TouchOptionsArrowBand : -TouchOptionsIconInset, 0f);
                }
            }
        }

        private void LayoutCreditsForTouch(Vector4 safe, float half)
        {
            if (creditsCanvas == null || CreditsBackButton == null || CreditsScroll == null)
            {
                return;
            }
            float x = TouchColumnX(Tuning.OptionsMargin, safe);
            float dx = x - Tuning.OptionsMargin;
            if (dx > 0f)
            {
                Nudge(creditsCanvas.transform.Find("CreditsTitle"), dx);
                Nudge(creditsCanvas.transform.Find("CreditsRule"), dx);
            }
            float backY = Mathf.Max(TouchCreditsBackY, -half + safe.z + TouchBottomMargin + TouchCreditsBackSize.y * 0.5f);
            Place(menuTouchMemory.Keep((RectTransform)CreditsBackButton.transform), new Vector2(0f, 0.5f), new Vector2(x, backY), TouchCreditsBackSize);
            if (Labels.TryGetValue(CreditsBackButton.name + "Label", out Text label))
            {
                menuTouchMemory.Keep(label).fontSize = TouchCreditsBackFontSize;
            }
            var scroll = (RectTransform)CreditsScroll.transform;
            menuTouchMemory.Keep(scroll);
            float scrollBottom = backY + TouchCreditsBackSize.y * 0.5f + TouchCreditsGap;
            scroll.anchoredPosition = new Vector2(x, CreditsViewTop);
            scroll.sizeDelta = new Vector2(scroll.sizeDelta.x, Mathf.Max(100f, CreditsViewTop - scrollBottom));
        }

        /// <summary>
        /// The title column's left and right links. PC: none left, right to Shop (or none without a shop), as BuildTitle's
        /// chain and BuildShop left them. Touch: across each grid row too (Niveaux and Options, Crédits and Quitter), the
        /// right column's right still to Shop. Up and down stay the PC chain (Jouer, Niveaux, Options, Crédits, Quitter).
        /// </summary>
        private void TitleGridNavigation(bool touch)
        {
            if (PlayButton == null)
            {
                return;
            }
            SetSides(PlayButton, null, TitleShopButton);
            SetSides(LevelsButton, null, touch ? TitleOptionsButton : TitleShopButton);
            SetSides(TitleOptionsButton, touch ? LevelsButton : null, TitleShopButton);
            SetSides(TitleCreditsButton, null, touch ? QuitButton : TitleShopButton);
            SetSides(QuitButton, touch ? TitleCreditsButton : null, TitleShopButton);
        }

        /// <summary>
        /// The Options rows' left and right links: none on PC (one column); in the touch grid, across to the row beside
        /// (the left column's last row, which has none beside it, goes to Retour). Up and down stay the PC chain.
        /// </summary>
        private void OptionsColumnNavigation(bool touch)
        {
            Button[] rows = OptionsOrder();
            for (int i = 0; i < rows.Length; i++)
            {
                Selectable left = null;
                Selectable right = null;
                if (touch && i < TouchOptionsRows)
                {
                    right = rows[Mathf.Min(i + TouchOptionsRows, rows.Length - 1)];
                }
                else if (touch)
                {
                    left = rows[i - TouchOptionsRows];
                }
                SetSides(rows[i], left, right);
            }
        }

        private static void SetSides(Selectable selectable, Selectable left, Selectable right)
        {
            if (selectable == null)
            {
                return;
            }
            Navigation nav = selectable.navigation;
            nav.selectOnLeft = left;
            nav.selectOnRight = right;
            selectable.navigation = nav;
        }
    }
}
