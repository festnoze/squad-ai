using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Viewpoint
{
    /// <summary>Which face of the single overlay is showing.</summary>
    public enum MenuMode
    {
        Hidden,
        Title,
        Paused,
        Victory
    }

    /// <summary>
    /// Title, pause and victory screens: ONE overlay whose three texts change,
    /// exactly as PRD section 12.4 describes it. The menu emits intents and
    /// decides nothing: Main owns the run, the fades and the mouse cursor.
    /// <para>
    /// Everything is built in code in <see cref="Awake"/> on a Screen Space
    /// Overlay canvas of its own, sorted above the HUD, with the same
    /// CanvasScaler settings as the HUD (1600 x 900, match height, PRD 12
    /// preamble) so the pixel figures of 12.4 mean the same thing on both.
    /// </para>
    /// <para>
    /// The buttons need an EventSystem to receive clicks. This class does NOT
    /// create one: Main does, because two EventSystems in a scene log an error
    /// every frame.
    /// </para>
    /// </summary>
    public sealed class Menu : MonoBehaviour
    {
        // ---- Player-facing strings, verbatim from PRD section 12.4 ----------
        // They deliberately carry no accents; do not "fix" them.

        const string TitleTitle = "VIEWPOINT";

        const string TitleSubtitle =
            "Posez des photos. Elles deviennent le monde.\n" +
            "\n" +
            "ZQSD/WASD bouger   Souris regarder   Espace sauter   E interagir\n" +
            "Clic gauche poser la photo   Clic droit la lever (molette : la tourner)\n" +
            "Mains vides avec l'appareil : clic droit viser, clic gauche declencher\n" +
            "R (maintenu) rembobiner   F11 plein ecran";

        const string TitleHint = "Entree : commencer au niveau 1   ou cliquez un niveau ci-dessous";

        const string PauseTitle = "PAUSE";
        const string PauseSubtitle = "Le monde attend votre prochaine photo.";
        const string PauseHint = "Echap : reprendre    Entree : recommencer la partie";

        const string VictoryTitle = "STUDIO FERME";

        // Twenty-five islands since v6: the campaign grew and this line grew
        // with it (PRD 12.4 and 13.2).
        const string VictorySubtitle =
            "Les vingt-cinq iles sont derriere vous.\n" +
            "Chaque photo posee est restee exactement la ou vous l'avez vue.";

        const string VictoryHint = "Entree : rejouer";

        const string LockedButtonSuffix = ". Verrouille";
        const string LockedTooltip = "Atteignez ce niveau pour le debloquer.";

        // ---- Look, from the PRD 12.4 table ----------------------------------

        /// <summary>Full screen dim behind the column (PRD 12.4).</summary>
        static readonly Color DimColor = new Color(0.08f, 0.10f, 0.14f, 0.82f);

        /// <summary>Subtitle: white alpha 0.85 (PRD 12.4).</summary>
        static readonly Color SubtitleColor = new Color(1f, 1f, 1f, 0.85f);

        /// <summary>Hint: warm amber (PRD 12.4).</summary>
        static readonly Color HintColor = new Color(1f, 0.82f, 0.5f);

        /// <summary>Levels label: white alpha 0.7 (PRD 12.4).</summary>
        static readonly Color LevelsLabelColor = new Color(1f, 1f, 1f, 0.7f);

        const float TitleSizePx = 72f;      // PRD 12.4
        const float SubtitleSizePx = 22f;   // PRD 12.4
        const float HintSizePx = 24f;       // PRD 12.4
        const float LevelsLabelSizePx = 18f; // PRD 12.4
        const float ButtonTextSizePx = 14f; // PRD 12.4

        const float HintSpacerPx = 30f;     // PRD 12.4: spacer above the hint
        const float GridSpacerPx = 26f;     // PRD 12.4: spacer above the levels label

        const float ButtonWidthPx = 180f;   // PRD 12.4
        const float ButtonHeightPx = 36f;   // PRD 12.4
        const float ButtonGapPx = 8f;       // PRD 12.4
        const int GridColumns = 5;          // PRD 12.4

        /// <summary>
        /// The original was a Godot VBoxContainer, whose default theme puts 4 px
        /// between children on top of the explicit spacers of 12.4. Keeping it
        /// reproduces the original spacing; the PRD spacers still supply the two
        /// gaps that matter.
        /// </summary>
        const float ColumnSpacingPx = 4f;

        /// <summary>
        /// The 12.4 grid rides on a Godot tooltip, which uGUI has no equivalent
        /// of. Rather than invent a tooltip system, the subtitle of the hovered
        /// level lands in one line under the grid, in the style of the levels
        /// label right above it (18 px, white alpha 0.7).
        /// </summary>
        const float TooltipHeightPx = 24f;

        /// <summary>
        /// Reference resolution of the whole UI (PRD section 12 preamble); the
        /// HUD uses the same one, so a 22 px string is 22 px on both.
        /// </summary>
        static readonly Vector2 ReferenceResolution = new Vector2(1600f, 900f);

        /// <summary>
        /// Above the HUD canvas: the menu covers the game AND its HUD. Main
        /// hides the HUD as well, this only makes the stacking unambiguous.
        /// </summary>
        const int SortingOrder = 100;

        // Button colours. PRD 12.4 fixes the geometry and the text of the grid
        // but not its palette (the original inherited the Godot theme), so they
        // stay in the blue-grey family of the dim above so the grid reads as
        // part of the overlay rather than as a stray widget.
        static readonly Color ButtonNormal = new Color(0.16f, 0.20f, 0.28f, 0.92f);
        static readonly Color ButtonHighlighted = new Color(0.24f, 0.31f, 0.42f, 0.95f);
        static readonly Color ButtonPressed = new Color(0.32f, 0.41f, 0.54f, 1f);
        static readonly Color ButtonDisabled = new Color(0.12f, 0.14f, 0.19f, 0.55f);
        static readonly Color ButtonLabelUnlocked = Color.white;
        static readonly Color ButtonLabelLocked = new Color(1f, 1f, 1f, 0.45f);

        /// <summary>Which screen is up; <see cref="MenuMode.Hidden"/> means the game is running.</summary>
        public MenuMode Mode { get; private set; }

        /// <summary>Enter on the title: begin a fresh run at level 1.</summary>
        public event Action StartRequested;

        /// <summary>Escape on the pause screen: back to the level, untouched.</summary>
        public event Action ResumeRequested;

        /// <summary>Enter on pause or victory: start the run over at level 1.</summary>
        public event Action RestartRequested;

        /// <summary>A level button was clicked, with its zero-based index.</summary>
        public event Action<int> LevelSelected;

        GameObject _root;
        Text _title;
        Text _subtitle;
        Text _hint;
        Text _levelsLabel;
        Text _tooltip;

        readonly List<Button> _levelButtons = new List<Button>();
        readonly List<Text> _levelLabels = new List<Text>();

        /// <summary>Text the hover line shows for each button, refreshed with the grid.</summary>
        readonly List<string> _levelTooltips = new List<string>();

        /// <summary>
        /// Frame on which the mode last changed. A single key press stays true
        /// for the whole frame, so without this guard the very Escape that makes
        /// Main open the pause screen would be read again here and close it -
        /// which of the two scripts runs first would decide whether pausing
        /// works at all.
        /// </summary>
        int _modeChangedFrame = -1;

        void Awake()
        {
            Build();
            HideMenu();
        }

        /// <summary>Title screen: the campaign has not started (or has been left).</summary>
        public void ShowTitle()
        {
            SetMode(MenuMode.Title);
            _title.text = TitleTitle;
            _subtitle.text = TitleSubtitle;
            _hint.text = TitleHint;
            RefreshLevels();
        }

        /// <summary>Pause screen: a level is loaded and frozen behind the dim.</summary>
        public void ShowPause()
        {
            SetMode(MenuMode.Paused);
            _title.text = PauseTitle;
            _subtitle.text = PauseSubtitle;
            _hint.text = PauseHint;
            RefreshLevels();
        }

        /// <summary>Victory screen: the last teleporter has been taken.</summary>
        public void ShowVictory()
        {
            SetMode(MenuMode.Victory);
            _title.text = VictoryTitle;
            _subtitle.text = VictorySubtitle;
            _hint.text = VictoryHint;
            RefreshLevels();
        }

        /// <summary>Back to the game: the overlay stops drawing and stops reading keys.</summary>
        public void HideMenu()
        {
            SetMode(MenuMode.Hidden);
        }

        void SetMode(MenuMode mode)
        {
            Mode = mode;
            _modeChangedFrame = Time.frameCount;
            if (_root != null)
            {
                _root.SetActive(mode != MenuMode.Hidden);
            }
        }

        void Update()
        {
            if (Mode == MenuMode.Hidden)
            {
                return;
            }

            // The press that opened this screen is not also a press on it.
            if (Time.frameCount == _modeChangedFrame)
            {
                return;
            }

            // Read the mode BEFORE raising anything: a listener hides or swaps
            // the screen inside the call, and one press must move one step.
            MenuMode mode = Mode;

            if (ViewpointInput.StartPressed)
            {
                if (mode == MenuMode.Title)
                {
                    StartRequested?.Invoke();
                }
                else
                {
                    // Pause and victory both restart the run at level 1.
                    RestartRequested?.Invoke();
                }
                return;
            }

            if (mode == MenuMode.Paused && ViewpointInput.PausePressed)
            {
                ResumeRequested?.Invoke();
            }
        }

        /// <summary>
        /// Reflects the persisted progression: reached levels are playable, the
        /// rest are visible but locked, so the player sees how far the road goes.
        /// </summary>
        void RefreshLevels()
        {
            GameState state = GameState.Instance;
            int count = LevelDefs.Count;

            for (int i = 0; i < _levelButtons.Count; i++)
            {
                bool unlocked = state.IsLevelUnlocked(i);
                _levelButtons[i].interactable = unlocked;

                LevelDef def = LevelDefs.GetDef(i);
                if (unlocked)
                {
                    // "?" is the original's fallback for a nameless level.
                    string name = def != null && !string.IsNullOrEmpty(def.Name) ? def.Name : "?";
                    _levelLabels[i].text = (i + 1) + ". " + name;
                    _levelLabels[i].color = ButtonLabelUnlocked;
                    _levelTooltips[i] = def != null && def.Subtitle != null ? def.Subtitle : string.Empty;
                }
                else
                {
                    _levelLabels[i].text = (i + 1) + LockedButtonSuffix;
                    _levelLabels[i].color = ButtonLabelLocked;
                    _levelTooltips[i] = LockedTooltip;
                }
            }

            int reached = Mathf.Clamp(state.FurthestLevel + 1, 1, Mathf.Max(count, 1));
            _levelsLabel.text = "Choisir un niveau (" + reached + " / " + count + " atteints)";
            _tooltip.text = string.Empty;
        }

        void SetTooltip(int index)
        {
            if (index >= 0 && index < _levelTooltips.Count)
            {
                _tooltip.text = _levelTooltips[index];
            }
        }

        void ClearTooltip()
        {
            _tooltip.text = string.Empty;
        }

        // ---- Construction ---------------------------------------------------

        void Build()
        {
            GameObject canvasObject = new GameObject("MenuCanvas", typeof(RectTransform));
            canvasObject.transform.SetParent(transform, false);

            Canvas canvas = canvasObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = SortingOrder;

            CanvasScaler scaler = canvasObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = ReferenceResolution;
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
            scaler.matchWidthOrHeight = 1f; // 1 = match height (PRD section 12 preamble)

            canvasObject.AddComponent<GraphicRaycaster>();

            _root = canvasObject;

            // The dim also swallows every click that misses a button.
            RectTransform dim = NewRect("Dim", canvasObject.transform);
            Stretch(dim);
            Image dimImage = dim.gameObject.AddComponent<Image>();
            dimImage.color = DimColor;
            dimImage.raycastTarget = true;

            RectTransform column = NewRect("Column", canvasObject.transform);
            column.anchorMin = new Vector2(0.5f, 0.5f);
            column.anchorMax = new Vector2(0.5f, 0.5f);
            column.pivot = new Vector2(0.5f, 0.5f);
            column.anchoredPosition = Vector2.zero;

            VerticalLayoutGroup layout = column.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.childAlignment = TextAnchor.MiddleCenter;
            layout.spacing = ColumnSpacingPx;
            layout.childControlWidth = true;
            layout.childControlHeight = true;
            layout.childForceExpandWidth = false;
            layout.childForceExpandHeight = false;

            // The column is as tall and as wide as what it holds, and it is
            // pinned by its centre, so it stays centred whatever the mode puts
            // in it.
            ContentSizeFitter fitter = column.gameObject.AddComponent<ContentSizeFitter>();
            fitter.horizontalFit = ContentSizeFitter.FitMode.PreferredSize;
            fitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            _title = NewLabel("Title", column, TitleSizePx, Color.white);
            _subtitle = NewLabel("Subtitle", column, SubtitleSizePx, SubtitleColor);
            NewSpacer("HintSpacer", column, HintSpacerPx);
            _hint = NewLabel("Hint", column, HintSizePx, HintColor);
            NewSpacer("GridSpacer", column, GridSpacerPx);
            _levelsLabel = NewLabel("LevelsLabel", column, LevelsLabelSizePx, LevelsLabelColor);

            BuildGrid(column);

            _tooltip = NewLabel("Tooltip", column, LevelsLabelSizePx, LevelsLabelColor);
            LayoutElement tooltipSize = _tooltip.gameObject.AddComponent<LayoutElement>();
            // Fixed height so the column does not jump as the hover line fills
            // and empties.
            tooltipSize.minHeight = TooltipHeightPx;
            tooltipSize.preferredHeight = TooltipHeightPx;
        }

        void BuildGrid(Transform parent)
        {
            RectTransform grid = NewRect("Levels", parent);
            GridLayoutGroup cells = grid.gameObject.AddComponent<GridLayoutGroup>();
            cells.cellSize = new Vector2(ButtonWidthPx, ButtonHeightPx);
            cells.spacing = new Vector2(ButtonGapPx, ButtonGapPx);
            cells.constraint = GridLayoutGroup.Constraint.FixedColumnCount;
            cells.constraintCount = GridColumns;
            cells.childAlignment = TextAnchor.MiddleCenter;

            int count = LevelDefs.Count;
            for (int i = 0; i < count; i++)
            {
                // Captured by the click and hover callbacks below: a loop
                // variable read later would be the last index for every button.
                int index = i;

                RectTransform cell = NewRect("Level" + (i + 1), grid);
                Image background = cell.gameObject.AddComponent<Image>();
                // White here: the ColorBlock below carries the actual colours,
                // and Selectable multiplies the two.
                background.color = Color.white;

                Button button = cell.gameObject.AddComponent<Button>();
                button.targetGraphic = background;
                button.transition = Selectable.Transition.ColorTint;
                // The original set focus_mode = FOCUS_NONE: the grid is clicked,
                // never tabbed through, and Enter belongs to the hint line.
                Navigation navigation = button.navigation;
                navigation.mode = Navigation.Mode.None;
                button.navigation = navigation;

                ColorBlock colors = ColorBlock.defaultColorBlock;
                colors.normalColor = ButtonNormal;
                colors.highlightedColor = ButtonHighlighted;
                colors.pressedColor = ButtonPressed;
                colors.selectedColor = ButtonNormal;
                colors.disabledColor = ButtonDisabled;
                button.colors = colors;

                button.onClick.AddListener(() =>
                {
                    Action<int> handler = LevelSelected;
                    if (handler != null)
                    {
                        handler(index);
                    }
                });

                // Stand-in for the Godot tooltip: EventTrigger is stock uGUI, so
                // no hover machinery of our own. A locked button still reports,
                // because a non-interactable Selectable still takes raycasts.
                EventTrigger hover = cell.gameObject.AddComponent<EventTrigger>();
                EventTrigger.Entry enter = new EventTrigger.Entry();
                enter.eventID = EventTriggerType.PointerEnter;
                enter.callback.AddListener(delegate { SetTooltip(index); });
                hover.triggers.Add(enter);

                EventTrigger.Entry exit = new EventTrigger.Entry();
                exit.eventID = EventTriggerType.PointerExit;
                exit.callback.AddListener(delegate { ClearTooltip(); });
                hover.triggers.Add(exit);

                Text label = NewLabel("Label", cell, ButtonTextSizePx, ButtonLabelUnlocked);
                Stretch(label.rectTransform);
                // A name longer than the 180 px cell has to wrap to a second
                // line, which 36 px holds at 14 px. uGUI has no margin, so the
                // padding is an inset on the rect, and wrapping has to be asked
                // for: Fonts.Apply leaves labels overflowing, which is right
                // for a one line prompt and wrong for a level name.
                label.rectTransform.offsetMin = new Vector2(6f, 2f);
                label.rectTransform.offsetMax = new Vector2(-6f, -2f);
                label.horizontalOverflow = HorizontalWrapMode.Wrap;
                label.verticalOverflow = VerticalWrapMode.Truncate;

                _levelButtons.Add(button);
                _levelLabels.Add(label);
                _levelTooltips.Add(string.Empty);
            }
        }

        static RectTransform NewRect(string name, Transform parent)
        {
            GameObject go = new GameObject(name, typeof(RectTransform));
            RectTransform rect = go.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            return rect;
        }

        static void Stretch(RectTransform rect)
        {
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }

        /// <summary>
        /// A centred label on the engine's builtin font. The menu sits on its
        /// own dim panel, so it needs no outline to stay readable. See Fonts
        /// for why this is uGUI Text and not TextMeshPro.
        /// </summary>
        static Text NewLabel(string name, Transform parent, float sizePx, Color color)
        {
            RectTransform rect = NewRect(name, parent);
            Text label = rect.gameObject.AddComponent<Text>();
            // Labels never eat a click: the button under them must get it, and
            // Fonts.Apply clears raycastTarget for exactly that reason.
            Fonts.Apply(label, Mathf.RoundToInt(sizePx), color, TextAnchor.MiddleCenter, false, Color.clear);
            return label;
        }

        static void NewSpacer(string name, Transform parent, float heightPx)
        {
            RectTransform rect = NewRect(name, parent);
            LayoutElement element = rect.gameObject.AddComponent<LayoutElement>();
            element.minHeight = heightPx;
            element.preferredHeight = heightPx;
        }
    }
}
