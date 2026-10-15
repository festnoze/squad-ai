using System;
using System.Collections.Generic;
using System.Reflection;
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
    /// <para>
    /// PRD_VISUAL 4.12 (Tier 5) rebuilt the LOOK of this screen and nothing
    /// else. Every string is still the one gameplay PRD 12.4 pins, character
    /// for character, and Enter, Escape and a click still do exactly what they
    /// did: the whole of this tier is panels, pictures, colour and timing.
    /// The four items and where they live:
    /// </para>
    /// <list type="bullet">
    ///   <item>V-MENU-01, the menu side ONLY: the dim LIGHTENS over the diorama
    ///   Main builds behind the title and victory screens, and stays at PRD
    ///   12.4's full strength on pause, where the live level is what the player
    ///   wants to see. See <see cref="DimTargetAlpha"/>. The item is NOT
    ///   delivered yet: Main declares MenuDioramaShowing but nothing writes it
    ///   and no diorama is built, so the lighter dim is reached on no frame of
    ///   any run today. This side needs no change when that half lands.</item>
    ///   <item>V-MENU-02, the menu side ONLY: each unlocked cell carries a
    ///   rendered thumbnail of its level, asked of the picture studio. See
    ///   <see cref="PumpThumbnails"/>, and read the comment there before
    ///   assuming the studio answers - today it does not. PhotoSnaps has no
    ///   RequestLevelThumbnail(int), so the binder finds nothing, every cell
    ///   stays text-only and the item is NOT delivered yet.</item>
    ///   <item>V-MENU-03: rounded cells, a hover lift, a teal focus ring, a
    ///   coral tint on the level the player is at and locked cells at 45
    ///   percent behind a drawn padlock. Every shape is generated in
    ///   <see cref="MenuArt"/>: PRD_VISUAL 3.2 as amended (appendix C.11)
    ///   allows the font and the CC0 texture sets, and no icon file.</item>
    ///   <item>V-MENU-04: the overlay fades and slides 16 px over 0.2 s and the
    ///   title's letters settle in once. See <see cref="MenuTitleSettle"/>. The
    ///   animation is driven from Update and reaches NOTHING that decides
    ///   anything: the input block below is the one it was before this tier,
    ///   guards included, so Enter is still read on the first frame the player
    ///   could press it.</item>
    /// </list>
    /// <para>
    /// The layout changed shape for one reason worth recording. PRD 12.4 puts
    /// everything in one centred column, and that column held while the grid
    /// was five rows of 36 px buttons (212 px of the 900 the canvas has). The
    /// thumbnails of V-MENU-02 make the grid five rows of 130 px, which is 682
    /// px, and the title, the four lines of controls and the hint do not fit in
    /// what is left. So the column became TWO panels side by side: the text on
    /// the left, the level grid on the right, each on its own rounded plate.
    /// The strings, their sizes and their colours are untouched; only where
    /// they sit changed, which is the one freedom PRD_VISUAL 4.12 asks for. The
    /// hint travelled with the grid rather than with the title, because its
    /// pinned wording ends with "ci-dessous" and has to keep pointing at the
    /// thing underneath it.
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

        /// <summary>
        /// The dim over the diorama (V-MENU-01). PRD 12.4's 0.82 exists to make
        /// text readable over a LIVE LEVEL, which is a picture the menu has no
        /// control over; at that strength the little world Main turns behind the
        /// title screen is a grey smear and the item is bought for nothing.
        /// Half of it is enough here because the text no longer relies on the
        /// dim at all: every label now sits on a plate of its own (PanelColor
        /// below), which is what V-HUD-01 calls the condition for a drop shadow
        /// rather than a contour.
        ///
        /// Pause keeps 0.82. PRD_VISUAL 4.12 says so in as many words, and the
        /// reason is not decoration: on pause the player is IN the level behind
        /// the glass, and a legible pause screen matters more than a pretty
        /// view of a frozen frame.
        /// </summary>
        const float DimOverDioramaAlpha = 0.42f;

        /// <summary>
        /// How fast the dim crosses between its two strengths. The diorama can
        /// appear a frame or two after the menu (Main builds it, Main raises
        /// MenuDioramaShowing), so the two are blended rather than switched:
        /// a one frame disagreement between this class and Main is then
        /// invisible instead of a flash of the wrong dim.
        /// </summary>
        const float DimBlendSeconds = 0.25f;

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

        // PRD 12.4 has two spacers in its one column: 30 px above the hint and
        // 26 px above the levels label. In the two panel layout the hint is the
        // first thing on the grid panel, so the 30 px above it became the
        // panel's own padding and only the 26 px is still a spacer.
        const float GridSpacerPx = 26f;

        const float ButtonWidthPx = 180f;   // PRD 12.4, kept by V-MENU-02
        const float ButtonGapPx = 8f;       // PRD 12.4
        const int GridColumns = 5;          // PRD 12.4

        /// <summary>
        /// V-MENU-02's cell: 180 x 130 instead of PRD 12.4's 180 x 36, because
        /// a thumbnail, a number and a name do not fit in 36 px. The three
        /// bands inside it are below, and they add up to exactly 130.
        /// </summary>
        const float ButtonHeightPx = 130f;

        /// <summary>
        /// The picture box inside a cell. The studio renders 160 x 90; this is
        /// the same 16:9 shrunk by the cell's padding, and a texture that
        /// arrives at another shape is centre-cropped into it by
        /// <see cref="CenterCrop"/> rather than squashed.
        /// </summary>
        const float ThumbWidthPx = 156f;
        const float ThumbHeightPx = 86f;

        /// <summary>Padding above the picture, and the gap down to the name.</summary>
        const float ThumbTopPx = 4f;
        const float ThumbGapPx = 4f;

        /// <summary>
        /// The name band at the bottom of a cell: two lines of 14 px, because
        /// "13. L'escalier sur l'escalier" does not fit on one at 156 px wide.
        /// 4 + 86 + 4 + 35 + 1 = 130.
        ///
        /// 35 and not 32 because a dynamic font decides its own line height
        /// (Manrope's is about 1.35 em, so two lines can want 38 px), and the
        /// label is left OVERFLOWING rather than truncated for the same reason:
        /// a name is a string gameplay PRD 12.4 pins, and half of one is worse
        /// than one that leans a pixel or two into the picture above it.
        /// </summary>
        const float LabelBandPx = 35f;
        const float LabelBottomPx = 1f;

        /// <summary>Horizontal inset of a label inside its cell.</summary>
        const float LabelInsetPx = 6f;

        /// <summary>
        /// The original was a Godot VBoxContainer, whose default theme puts 4 px
        /// between children on top of the explicit spacers of 12.4. Keeping it
        /// reproduces the original spacing; the PRD spacer still supplies the one
        /// gap that matters.
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

        // ---- The two panels -------------------------------------------------

        /// <summary>
        /// The plate under each panel. Dark and nearly opaque, so the labels on
        /// it keep the 4.5:1 they need whatever the diorama turns behind them:
        /// that is the condition Fonts.cs names for TextEdge.Shadow, and it is
        /// why every label in this file asks for a shadow and not a contour.
        /// </summary>
        static readonly Color PanelColor = new Color(0.07f, 0.09f, 0.13f, 0.78f);

        const float PanelPaddingPx = 20f;
        const float PanelRadiusPx = 18f;
        const float ScreenMarginPx = 28f;
        const float PanelGapPx = 20f;

        /// <summary>
        /// The text panel's inner width. It is what is left of 1600 once the
        /// grid panel (932 of cells plus its padding), the two screen margins
        /// and the gap between the panels are taken out. The control list WRAPS
        /// inside it: it is not rewritten, resized or abbreviated, its longest
        /// line simply runs onto a second one, which is the price of showing a
        /// four line control list and twenty-five pictures in one 1600 x 900
        /// frame. The title screen's hint does NOT pay that price: it moved to
        /// the grid panel, where it fits on one line (see BuildGridPanel, and
        /// the reason it had to move at all).
        /// </summary>
        const float TextColumnPx = 500f;

        /// <summary>
        /// The grid itself: five cells and four gaps, 932 px. It is what makes
        /// the right panel as wide as it is, and the two labels above and below
        /// the grid are capped to it so that neither can widen the plate.
        /// </summary>
        const float GridInnerWidthPx =
            (GridColumns * ButtonWidthPx) + ((GridColumns - 1) * ButtonGapPx);

        /// <summary>
        /// The width the two panels and their margins need. The canvas scaler
        /// matches HEIGHT, so a window narrower than 16:9 gives the UI fewer
        /// than 1600 px of width and this layout would run off both sides.
        /// <see cref="FitContent"/> scales the whole thing down by the shortfall
        /// instead, which is smaller but whole; a clipped level grid would hide
        /// the very buttons this screen exists for.
        /// </summary>
        const float LayoutWidthPx =
            (2f * ScreenMarginPx) + PanelGapPx
            + TextColumnPx + (2f * PanelPaddingPx)
            + GridInnerWidthPx + (2f * PanelPaddingPx);

        // ---- Cell states (V-MENU-03) ----------------------------------------

        // Button colours. PRD 12.4 fixes the geometry and the text of the grid
        // but not its palette (the original inherited the Godot theme), so they
        // stay in the blue-grey family of the dim above so the grid reads as
        // part of the overlay rather than as a stray widget.
        static readonly Color ButtonNormal = new Color(0.16f, 0.20f, 0.28f, 0.92f);
        static readonly Color ButtonHighlighted = new Color(0.24f, 0.31f, 0.42f, 0.95f);
        static readonly Color ButtonPressed = new Color(0.32f, 0.41f, 0.54f, 1f);
        static readonly Color ButtonLabelUnlocked = Color.white;

        /// <summary>
        /// The name and the padlock of a LOCKED cell. Opaque, and that is the
        /// whole point of it: V-MENU-03's 45 percent is carried ONCE, by the
        /// cell's CanvasGroup (see ApplyCellState and MakeColors), and a
        /// CanvasGroup multiplies every graphic under it by its own alpha. A
        /// colour that carried the 45 percent a second time would composite the
        /// locked name and glyph at 0.45 x 0.45 = 0.20 over a plate already at
        /// 0.41, which is not the dimmed-but-readable cell the item asks for,
        /// it is an unreadable one.
        /// </summary>
        static readonly Color ButtonLabelLocked = Color.white;

        /// <summary>
        /// The coral of V-MENU-03, and the teal of its focus ring, taken from
        /// the palette rather than typed again: PRD_VISUAL 3.1 makes coral "the
        /// critical shot" and teal "the standard route" everywhere else in the
        /// game, and the grid means the same two things by them (where you are,
        /// and what has the keyboard). A second copy of those numbers here
        /// would be free to drift away from the ground the player walks on.
        /// </summary>
        static readonly Color CurrentTint = Palette.Get("accent");
        static readonly Color FocusTint = Palette.Get("teal");

        /// <summary>
        /// How far the current cell is pulled towards coral. Enough to find at
        /// a glance across 25 cells, short of a filled coral button, which
        /// would read as "selected" and invite a second click.
        /// </summary>
        const float CurrentTintAmount = 0.45f;

        /// <summary>Locked buttons at 45 percent (V-MENU-03), glyph included.</summary>
        const float LockedAlpha = 0.45f;

        /// <summary>The hover lift of V-MENU-03: scale 1.03 reached in 0.1 s.</summary>
        const float HoverScale = 1.03f;
        const float HoverSeconds = 0.1f;

        /// <summary>Corner radius of a cell, and the thickness of its focus ring.</summary>
        const int CellRadiusPx = 12;
        const float FocusRingPx = 2f;

        // ---- Transitions (V-MENU-04) ----------------------------------------

        /// <summary>Fade and slide, 0.2 s, from PRD_VISUAL 4.12.</summary>
        const float TransitionSeconds = 0.2f;
        const float SlidePx = 16f;

        // ---- Thumbnails (V-MENU-02) -----------------------------------------

        /// <summary>
        /// How many levels this asks the studio for in one frame. A studio that
        /// builds a level, shoots it and tears it down inside the call would
        /// otherwise do twenty-five of those on the frame the title screen
        /// opens, which is the one frame of the whole game the player is
        /// watching an animation on. Spread over a handful of frames the same
        /// work is invisible, and a studio that merely QUEUES the request does
        /// not care either way: five a frame fills a twenty-five deep queue in
        /// five frames, far inside V-MENU-02's two second budget.
        /// </summary>
        const int ThumbnailCallsPerFrame = 5;

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
        RectTransform _canvasRect;
        RectTransform _content;
        CanvasGroup _group;
        Image _dim;
        Text _title;
        Text _subtitle;
        Text _hint;
        Text _levelsLabel;
        Text _tooltip;
        MenuTitleSettle _titleSettle;

        /// <summary>
        /// Main, for the one question this class asks it: is the diorama of
        /// V-MENU-01 on screen right now. Main exposes that as a read-only
        /// property and drives the diorama from its own read of Menu.Mode, so
        /// there is no second opinion to disagree with and no half of the item
        /// to go missing (appendix C.23). Null is a supported state: an
        /// EditMode fixture can build a Menu on its own, and Main builds every
        /// subsystem inside its own try.
        /// </summary>
        Main _main;

        readonly List<Cell> _cells = new List<Cell>();

        /// <summary>The cell the pointer is over, or -1. Drives the hover lift.</summary>
        int _hovered = -1;

        /// <summary>
        /// The cell the focus ring is currently on, or -1, cached so the ring is
        /// only rewritten when it actually moves. See <see cref="StepFocus"/>
        /// for what "focus" can mean on a grid with no keyboard travel.
        /// </summary>
        int _focused = -1;

        /// <summary>Current dim alpha, blended towards <see cref="DimTargetAlpha"/>.</summary>
        float _dimAlpha = DimColor.a;

        /// <summary>Current scale of the whole layout, 1 at 16:9 or wider.</summary>
        float _contentScale = 1f;

        // Transition state. _transitionElapsed starts finished so nothing
        // animates before the first show.
        float _transitionElapsed = TransitionSeconds;
        float _transitionFromAlpha;
        float _transitionFromY;
        bool _transitionShowing;

        /// <summary>True once the title screen has played its letter settle.</summary>
        bool _titleSettlePlayed;

        // The picture studio's thumbnail API, bound by reflection ONCE. See
        // ResolveThumbnailApi for why this is reflection and not a call.
        MethodInfo _thumbnailFetch;
        MethodInfo _thumbnailRequest;
        PhotoSnaps _thumbnailStudio;
        bool _thumbnailResolved;
        int _thumbnailCursor;
        readonly object[] _oneArg = new object[1];

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
            _main = GetComponentInParent<Main>();
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
            PlayTitleSettle();
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

        /// <summary>
        /// Puts the overlay in a mode and starts the 0.2 s transition of
        /// V-MENU-04 towards it.
        ///
        /// Mode is written FIRST and unconditionally, before a single pixel
        /// moves. That is the whole of the item's acceptance criterion ("Enter
        /// on the title still starts the game within the same frame's input
        /// handling"): every caller of this class reads Mode, the input block in
        /// Update reads Mode, and none of them can see the animation at all.
        /// The transition only ever decides when the CanvasGroup reaches zero.
        /// </summary>
        void SetMode(MenuMode mode)
        {
            MenuMode previous = Mode;
            Mode = mode;
            _modeChangedFrame = Time.frameCount;

            if (_root == null)
            {
                return;
            }

            if (mode == MenuMode.Hidden)
            {
                // Hidden to hidden is the boot path (Awake calls HideMenu on a
                // menu that has never been shown) and a redundant hide from
                // Main. Neither deserves a fade out of something not on screen.
                if (previous == MenuMode.Hidden || !_root.activeSelf)
                {
                    SnapHidden();
                    return;
                }
                StartTransition(false);
                return;
            }

            if (!_root.activeSelf)
            {
                _root.SetActive(true);
            }

            // The keyboard focus of the LAST menu never carries into this one.
            // The grid is clicked and never tabbed (the original set
            // focus_mode = FOCUS_NONE and the Navigation below keeps that), and
            // with Navigation.Mode.None a click does NOT leave the clicked cell
            // selected either: Selectable.OnPointerDown skips the selection
            // entirely in that mode, which is the whole subject of StepFocus.
            // So no cell of THIS grid can be selected here. This line clears
            // whatever else in the game may have been - the UI input module
            // turns Enter into Submit on whatever is selected, and a stale
            // selection would make one Enter both restart the run and press
            // something - and it costs one call on a screen change.
            if (EventSystem.current != null)
            {
                EventSystem.current.SetSelectedGameObject(null);
            }

            StartTransition(true);
        }

        void StartTransition(bool showing)
        {
            _transitionFromAlpha = _group.alpha;
            _transitionFromY = _content.anchoredPosition.y;
            _transitionShowing = showing;
            _transitionElapsed = 0f;

            // Raycasts follow the INTENT, not the animation: a menu on its way
            // out must stop eating clicks on the frame it is dismissed, or the
            // left click that places a photo would be swallowed by a dim that
            // is already invisible.
            _group.blocksRaycasts = showing;
            _group.interactable = showing;
        }

        void SnapHidden()
        {
            _transitionElapsed = TransitionSeconds;
            _transitionShowing = false;
            _group.alpha = 0f;
            _group.blocksRaycasts = false;
            _group.interactable = false;
            _content.anchoredPosition = new Vector2(0f, -SlidePx);
            _root.SetActive(false);
        }

        void Update()
        {
            // The look is stepped FIRST and outside every guard below, because
            // the fade out has to keep running on the frames after the menu was
            // dismissed. None of it can reach the input block: these methods
            // write alphas, colours, scales and one anchored position.
            float dt = Time.unscaledDeltaTime;
            StepTransition(dt);

            if (_root != null && _root.activeSelf)
            {
                StepDim(dt);
                StepHover(dt);
                StepFocus();
                FitContent();
                PumpThumbnails();
            }

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

        // ---- The look, stepped every frame ----------------------------------

        /// <summary>V-MENU-04's fade and 16 px slide, on the unscaled clock.</summary>
        void StepTransition(float dt)
        {
            if (_transitionElapsed >= TransitionSeconds || _group == null)
            {
                return;
            }

            _transitionElapsed = Mathf.Min(_transitionElapsed + dt, TransitionSeconds);
            float k = EaseOut(_transitionElapsed / TransitionSeconds);

            _group.alpha = Mathf.Lerp(_transitionFromAlpha, _transitionShowing ? 1f : 0f, k);
            float y = Mathf.Lerp(_transitionFromY, _transitionShowing ? 0f : -SlidePx, k);
            _content.anchoredPosition = new Vector2(0f, y);

            if (_transitionElapsed >= TransitionSeconds && !_transitionShowing && _root.activeSelf)
            {
                // Deactivated only once the fade has actually landed on zero,
                // for the reason Hud's Fader gives: hiding an object mid fade
                // is a vanish, not a fade.
                _root.SetActive(false);
            }
        }

        /// <summary>
        /// V-MENU-01's two dims, crossed rather than switched. Reads Main and
        /// never writes it: whether the diorama is up is Main's answer to give.
        /// </summary>
        void StepDim(float dt)
        {
            float target = DimTargetAlpha();
            if (!Mathf.Approximately(_dimAlpha, target))
            {
                _dimAlpha = Mathf.MoveTowards(_dimAlpha, target, dt / DimBlendSeconds);
                _dim.color = new Color(DimColor.r, DimColor.g, DimColor.b, _dimAlpha);
            }
        }

        float DimTargetAlpha()
        {
            // Leaving: hold whatever we had. The overlay is fading out as a
            // whole, and a dim that lightens on the way out reads as a flash.
            if (Mode == MenuMode.Hidden)
            {
                return _dimAlpha;
            }

            // Pause keeps PRD 12.4's full strength, diorama or not: it is where
            // the player is, and PRD_VISUAL 4.12 says so explicitly.
            if (Mode == MenuMode.Paused)
            {
                return DimColor.a;
            }

            bool diorama = _main != null && _main.MenuDioramaShowing;
            return diorama ? DimOverDioramaAlpha : DimColor.a;
        }

        /// <summary>The hover lift of V-MENU-03, one cell at a time.</summary>
        void StepHover(float dt)
        {
            float rate = (HoverScale - 1f) / HoverSeconds;
            for (var i = 0; i < _cells.Count; i++)
            {
                Cell cell = _cells[i];
                // A locked cell does not lift: it cannot be pressed, and a
                // button that answers the pointer and then refuses the click is
                // a worse lie than one that stays still.
                float target = i == _hovered && cell.Button.interactable ? HoverScale : 1f;
                if (Mathf.Approximately(cell.Scale, target))
                {
                    continue;
                }
                cell.Scale = Mathf.MoveTowards(cell.Scale, target, rate * dt);
                cell.Rect.localScale = new Vector3(cell.Scale, cell.Scale, 1f);
            }
        }

        /// <summary>
        /// The teal focus ring of V-MENU-03. It follows the cell this class
        /// knows is focused - the one under the pointer - and NOT the
        /// EventSystem's selection, which is a distinction worth the paragraphs
        /// it takes, because the obvious version of this method draws nothing
        /// on any frame of any run.
        /// <para>
        /// Every cell is built with Navigation.Mode.None (BuildGrid says why),
        /// and uGUI's Selectable.OnPointerDown only selects the object it is on
        /// when the mode is NOT None:
        /// "if (IsInteractable() and navigation.mode != Navigation.Mode.None
        /// and EventSystem.current != null) EventSystem.current
        /// .SetSelectedGameObject(...)". So a click does not leave the cell
        /// selected, nothing else here calls Select, and a ring driven off
        /// currentSelectedGameObject would be off forever.
        /// </para>
        /// <para>
        /// Selecting the cell by hand instead would not be a fix, it would
        /// break something pinned. Button.OnSubmit calls Press() whatever the
        /// navigation mode is - the mode gates travel and selection, never
        /// Submit - so a selected cell turns the Enter that starts or restarts
        /// the run into a level click as well: one key, two things, which is
        /// exactly what the Navigation comment in BuildGrid refuses and what
        /// V-MENU-04's acceptance criterion forbids in as many words.
        /// </para>
        /// <para>
        /// PRD_VISUAL 4.12 calls the ring a KEYBOARD focus outline. This grid
        /// has no keyboard travel, and adding some is a change to input
        /// handling rather than to the look, so it is not this tier's to make
        /// (it is filed as a follow-up). Until it exists, the ring marks the
        /// focus this screen really has, the cell the pointer is on, and only
        /// on cells that can be pressed - a ring around a locked cell would
        /// promise a click it would then refuse, which is the same lie the
        /// hover lift declines to tell in StepHover.
        /// </para>
        /// </summary>
        void StepFocus()
        {
            int focused = _hovered >= 0 && _hovered < _cells.Count
                && _cells[_hovered].Button.interactable
                ? _hovered
                : -1;
            if (focused == _focused)
            {
                return;
            }
            _focused = focused;

            for (var i = 0; i < _cells.Count; i++)
            {
                Cell cell = _cells[i];
                // The sprite check is the same guard the padlock takes: a ring
                // whose rounded outline could not be drawn would be a filled
                // teal rectangle over the cell, which is worse than no ring.
                cell.Focus.enabled = cell.Focus.sprite != null && i == focused;
            }
        }

        /// <summary>
        /// Keeps the two panels inside a canvas narrower than 16:9. The scaler
        /// matches height, so the canvas is always 900 tall and only the width
        /// moves; below the width this layout needs, everything shrinks by the
        /// shortfall rather than running off the sides.
        /// </summary>
        void FitContent()
        {
            if (_canvasRect == null)
            {
                return;
            }
            float width = _canvasRect.rect.width;
            float k = width > 1f ? Mathf.Min(1f, width / LayoutWidthPx) : 1f;
            if (Mathf.Approximately(k, _contentScale))
            {
                return;
            }
            _contentScale = k;
            _content.localScale = new Vector3(k, k, 1f);
        }

        /// <summary>Cubic ease out, the same curve the HUD settles on.</summary>
        static float EaseOut(float t)
        {
            float k = 1f - Mathf.Clamp01(t);
            return 1f - (k * k * k);
        }

        // ---- Level thumbnails (V-MENU-02) -----------------------------------

        /// <summary>
        /// Asks the picture studio for the thumbnails of the unlocked levels,
        /// a few a frame, and hands each one to its cell as it arrives.
        ///
        /// Only on the title and victory screens. V-MENU-02 caches "at the first
        /// title screen" and the studio builds a whole level to shoot it: doing
        /// that from the PAUSE screen would spend that work while a live level
        /// is loaded, for a grid the player opened to leave. Pause still SHOWS
        /// every thumbnail already in hand, because they are kept here for the
        /// session.
        ///
        /// Only for UNLOCKED levels, which is the item's own wording ("every
        /// unlocked level's thumbnail"). A locked cell shows the padlock, so a
        /// picture of a level the player has never reached would be spoiling
        /// work nobody asked for.
        /// </summary>
        void PumpThumbnails()
        {
            if (Mode != MenuMode.Title && Mode != MenuMode.Victory)
            {
                return;
            }
            if (_cells.Count == 0)
            {
                return;
            }
            if (!_thumbnailResolved)
            {
                ResolveThumbnailApi();
            }
            if (_thumbnailFetch == null && _thumbnailRequest == null)
            {
                return;
            }

            GameState state = GameState.Instance;
            var calls = 0;
            for (var n = 0; n < _cells.Count && calls < ThumbnailCallsPerFrame; n++)
            {
                int index = _thumbnailCursor % _cells.Count;
                _thumbnailCursor = (_thumbnailCursor + 1) % _cells.Count;

                Cell cell = _cells[index];
                if (cell.Picture != null || !state.IsLevelUnlocked(index))
                {
                    continue;
                }

                calls++;
                Texture picture = AskThumbnail(index, cell);
                if (picture == null)
                {
                    continue;
                }

                cell.Picture = picture;
                ApplyCellState(index);
            }
        }

        /// <summary>
        /// One poll of the studio for one level: the picture if it is ready,
        /// null while it is not, and a request queued the first time.
        /// </summary>
        Texture AskThumbnail(int index, Cell cell)
        {
            var picture = Invoke(_thumbnailFetch, index) as Texture;
            if (picture != null)
            {
                return picture;
            }

            // A studio that answers with a texture from the same call it queues
            // on needs no second call: polling it IS requesting.
            if (_thumbnailRequest == null || _thumbnailRequest == _thumbnailFetch || cell.Requested)
            {
                return null;
            }

            cell.Requested = true;
            Invoke(_thumbnailRequest, index);
            return null;
        }

        object Invoke(MethodInfo method, int index)
        {
            if (method == null)
            {
                return null;
            }
            try
            {
                _oneArg[0] = index;
                return method.Invoke(method.IsStatic ? null : _thumbnailStudio, _oneArg);
            }
            catch (Exception e)
            {
                // One bad call is the end of the thumbnails and of nothing
                // else: the grid keeps its numbers, its names and its 25
                // buttons, which is exactly what it was before this tier.
                Debug.LogError("[Menu] Level thumbnails off, " + method.Name + " threw: " + e);
                _thumbnailFetch = null;
                _thumbnailRequest = null;
                return null;
            }
        }

        /// <summary>
        /// Binds PhotoSnaps's level thumbnail API, by reflection, once.
        ///
        /// Reflection and not a call, for the reason appendix C.23 records: the
        /// two halves of V-MENU-02 are in two files owned by two agents in the
        /// same round, and a compile-time call to a method whose exact shape is
        /// still being written would either land on the wrong signature or take
        /// the WHOLE GAME down with it if the other half slipped a round. Main
        /// binds Hud's colour fade the same way and for the same reason, and the
        /// price is the same: this must tolerate finding nothing.
        ///
        /// What is accepted, in the studio's own vocabulary (GetTexture / Request
        /// is the pair it already exposes for the polaroids):
        ///  - any public method, static or instance, whose name contains
        ///    "LevelThumbnail", taking one int;
        ///  - returning a Texture, which is the picture (a name starting with
        ///    "Get" wins over any other, so a Get/Request pair binds correctly);
        ///  - returning void, which is a request to build one.
        /// A single "RequestLevelThumbnail(int) -> Texture2D", which is what
        /// PRD_VISUAL 4.12 names, satisfies both roles at once.
        ///
        /// The one line it logs is the evidence: in a player log it says whether
        /// this menu found a studio API at all, which is the difference between
        /// "the thumbnails did not render" and "nobody ever asked for one".
        /// </summary>
        void ResolveThumbnailApi()
        {
            _thumbnailResolved = true;

            MethodInfo[] methods = typeof(PhotoSnaps).GetMethods(
                BindingFlags.Public | BindingFlags.Static | BindingFlags.Instance);

            for (var i = 0; i < methods.Length; i++)
            {
                MethodInfo method = methods[i];
                if (method.Name.IndexOf("LevelThumbnail", StringComparison.Ordinal) < 0)
                {
                    continue;
                }
                ParameterInfo[] parameters = method.GetParameters();
                if (parameters.Length != 1 || parameters[0].ParameterType != typeof(int))
                {
                    continue;
                }

                if (typeof(Texture).IsAssignableFrom(method.ReturnType))
                {
                    if (_thumbnailFetch == null
                        || method.Name.StartsWith("Get", StringComparison.Ordinal))
                    {
                        _thumbnailFetch = method;
                    }
                }
                else if (method.ReturnType == typeof(void) && _thumbnailRequest == null)
                {
                    _thumbnailRequest = method;
                }
            }

            if (_thumbnailRequest == null)
            {
                _thumbnailRequest = _thumbnailFetch;
            }

            bool needsInstance = (_thumbnailFetch != null && !_thumbnailFetch.IsStatic)
                || (_thumbnailRequest != null && !_thumbnailRequest.IsStatic);
            if (needsInstance)
            {
                _thumbnailStudio = FindAnyObjectByType<PhotoSnaps>();
                if (_thumbnailStudio == null)
                {
                    // An instance method with no instance is not a binding.
                    if (_thumbnailFetch != null && !_thumbnailFetch.IsStatic)
                    {
                        _thumbnailFetch = null;
                    }
                    if (_thumbnailRequest != null && !_thumbnailRequest.IsStatic)
                    {
                        _thumbnailRequest = null;
                    }
                }
            }

            Debug.Log("[Menu] Level thumbnails: "
                + (_thumbnailFetch != null ? "PhotoSnaps." + _thumbnailFetch.Name + "(int)" : "no getter")
                + ", request "
                + (_thumbnailRequest != null ? "PhotoSnaps." + _thumbnailRequest.Name + "(int)" : "none"));
        }

        /// <summary>
        /// The part of a texture a 16:9 box should sample, centred. The studio
        /// is asked for 160 x 90 and a square readback is exactly what its
        /// polaroid path produces, so a picture of another shape is likely
        /// rather than hypothetical: cropped it stays true, stretched it would
        /// make a level look like a level it is not.
        /// </summary>
        static Rect CenterCrop(Texture texture, float boxAspect)
        {
            if (texture == null || texture.width <= 0 || texture.height <= 0 || boxAspect <= 0f)
            {
                return new Rect(0f, 0f, 1f, 1f);
            }
            float source = (float)texture.width / texture.height;
            if (source > boxAspect)
            {
                float w = boxAspect / source;
                return new Rect((1f - w) * 0.5f, 0f, w, 1f);
            }
            float h = source / boxAspect;
            return new Rect(0f, (1f - h) * 0.5f, 1f, h);
        }

        // ---- The level grid --------------------------------------------------

        /// <summary>
        /// Reflects the persisted progression: reached levels are playable, the
        /// rest are visible but locked, so the player sees how far the road goes.
        /// </summary>
        void RefreshLevels()
        {
            GameState state = GameState.Instance;
            int count = LevelDefs.Count;

            for (var i = 0; i < _cells.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                if (state.IsLevelUnlocked(i))
                {
                    // "?" is the original's fallback for a nameless level.
                    string name = def != null && !string.IsNullOrEmpty(def.Name) ? def.Name : "?";
                    _cells[i].Label.text = (i + 1) + ". " + name;
                    _cells[i].Label.color = ButtonLabelUnlocked;
                    _cells[i].Tooltip = def != null && def.Subtitle != null ? def.Subtitle : string.Empty;
                }
                else
                {
                    _cells[i].Label.text = (i + 1) + LockedButtonSuffix;
                    _cells[i].Label.color = ButtonLabelLocked;
                    _cells[i].Tooltip = LockedTooltip;
                }

                ApplyCellState(i);
            }

            int reached = Mathf.Clamp(state.FurthestLevel + 1, 1, Mathf.Max(count, 1));
            _levelsLabel.text = "Choisir un niveau (" + reached + " / " + count + " atteints)";
            _tooltip.text = string.Empty;
        }

        /// <summary>
        /// Everything about one cell that depends on the run rather than on the
        /// build: locked or not, current or not, picture or no picture.
        ///
        /// The no-picture path is the one that matters most and it is the one
        /// nothing on screen advertises. A headless run, a player whose studio
        /// was stripped, a cache that has not drained yet and a level nobody has
        /// unlocked all land here, and in every one of them the cell has to stay
        /// a perfectly usable button: the name fills the whole cell, centred,
        /// and the grid reads exactly as it did before this tier.
        /// </summary>
        void ApplyCellState(int index)
        {
            Cell cell = _cells[index];
            bool unlocked = GameState.Instance.IsLevelUnlocked(index);
            bool current = unlocked && index == CurrentLevelIndex();

            cell.Button.interactable = unlocked;
            cell.Button.colors = current ? CurrentColors : NormalColors;
            cell.Group.alpha = unlocked ? 1f : LockedAlpha;

            // No padlock rather than a white block: an Image with no sprite
            // draws a filled rectangle, and the cell already says "Verrouille"
            // in the string PRD 12.4 pins.
            bool padlock = !unlocked && cell.Lock.sprite != null;
            cell.Lock.enabled = padlock;

            bool picture = unlocked && cell.Picture != null;
            cell.Thumb.enabled = picture;
            if (picture)
            {
                cell.Thumb.texture = cell.Picture;
                cell.Thumb.uvRect = CenterCrop(cell.Picture, ThumbWidthPx / ThumbHeightPx);
            }

            // The name sits in the bottom band when something occupies the top
            // of the cell, and takes the whole cell when nothing does.
            bool band = picture || padlock;
            RectTransform rect = cell.Label.rectTransform;
            rect.offsetMin = new Vector2(LabelInsetPx, band ? LabelBottomPx : 2f);
            rect.offsetMax = new Vector2(-LabelInsetPx,
                band ? LabelBottomPx + LabelBandPx - ButtonHeightPx : -2f);
        }

        /// <summary>
        /// The level the coral tint marks. On pause it is the level the player
        /// is standing in; anywhere else there is no level in play, so it is the
        /// furthest one reached, which is where the campaign currently stands
        /// and the cell the player most likely wants.
        /// </summary>
        int CurrentLevelIndex()
        {
            int count = LevelDefs.Count;
            if (count <= 0)
            {
                return -1;
            }
            GameState state = GameState.Instance;
            int index = Mode == MenuMode.Paused ? state.LevelIndex : state.FurthestLevel;
            return Mathf.Clamp(index, 0, count - 1);
        }

        void SetTooltip(int index)
        {
            if (index >= 0 && index < _cells.Count)
            {
                _tooltip.text = _cells[index].Tooltip;
                _hovered = index;
            }
        }

        void ClearTooltip(int index)
        {
            _tooltip.text = string.Empty;
            if (_hovered == index)
            {
                _hovered = -1;
            }
        }

        /// <summary>
        /// The title's letters settle in on the FIRST title screen only
        /// (V-MENU-04). Not on pause, not on victory, and not on the title
        /// screen the player comes back to: an animation that plays every time
        /// is a delay, and the one this replaces played never.
        /// </summary>
        void PlayTitleSettle()
        {
            if (_titleSettlePlayed || _titleSettle == null)
            {
                return;
            }
            _titleSettlePlayed = true;
            _titleSettle.Play();
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

            // One group for the whole overlay: V-MENU-04's fade is a fade of
            // the SCREEN, and a CanvasGroup is also the only way to fade a
            // label whose edge effect keeps its own alpha (Fonts.ApplyEdge
            // leaves useGraphicAlpha off, for reasons its comment gives).
            _group = canvasObject.AddComponent<CanvasGroup>();
            _group.alpha = 0f;

            _root = canvasObject;
            _canvasRect = canvasObject.GetComponent<RectTransform>();

            // The dim also swallows every click that misses a button.
            RectTransform dim = NewRect("Dim", canvasObject.transform);
            Stretch(dim);
            _dim = dim.gameObject.AddComponent<Image>();
            _dim.color = DimColor;
            _dim.raycastTarget = true;

            // Everything above the dim slides together, so the slide is one
            // anchored position and not one per panel.
            _content = NewRect("Content", canvasObject.transform);
            Stretch(_content);
            _content.anchoredPosition = new Vector2(0f, -SlidePx);

            BuildTextPanel(_content);
            BuildGridPanel(_content);
        }

        /// <summary>
        /// The left plate: the title and the subtitle, in the sizes and colours
        /// of PRD 12.4, wrapped inside <see cref="TextColumnPx"/>. The hint is
        /// on the other plate, and BuildGridPanel says why.
        /// </summary>
        void BuildTextPanel(Transform parent)
        {
            RectTransform panel = NewPanel("TextPanel", parent, new Vector2(0f, 0.5f));
            panel.anchorMin = new Vector2(0f, 0.5f);
            panel.anchorMax = new Vector2(0f, 0.5f);
            panel.anchoredPosition = new Vector2(ScreenMarginPx, 0f);

            // The title is built by hand rather than through NewLabel for one
            // reason, and it is not a style choice: the settle effect has to be
            // attached BEFORE Fonts.Apply puts a Shadow on the label. uGUI runs
            // its mesh modifiers in COMPONENT ORDER, so first in the list this
            // effect sees the raw text mesh, one quad per character, and moves
            // whole letters; after the Shadow it would see that mesh ALREADY
            // DOUBLED, count twice as many letters as there are and drag the
            // shadow of one letter around with the body of another.
            RectTransform titleRect = NewRect("Title", panel);
            _title = titleRect.gameObject.AddComponent<Text>();
            _titleSettle = titleRect.gameObject.AddComponent<MenuTitleSettle>();
            Fonts.Apply(_title, Mathf.RoundToInt(TitleSizePx), Color.white,
                TextAnchor.MiddleLeft, TextEdge.Shadow, Fonts.EdgeColor, TextWeight.Title);
            // "STUDIO FERME" is wider than this column at 72 px and takes two
            // lines on the victory screen. That is the trade the column width
            // buys, and it is the right way round: a title that wraps still
            // reads, a title that runs off its plate does not.
            CapWidth(_title, TextColumnPx, true);

            _subtitle = NewLabel("Subtitle", panel, SubtitleSizePx, SubtitleColor,
                TextAnchor.UpperLeft, TextWeight.Regular);
            CapWidth(_subtitle, TextColumnPx, true);
        }

        /// <summary>The right plate: the levels label, the grid and the hover line.</summary>
        void BuildGridPanel(Transform parent)
        {
            RectTransform panel = NewPanel("GridPanel", parent, new Vector2(1f, 0.5f));
            panel.anchorMin = new Vector2(1f, 0.5f);
            panel.anchorMax = new Vector2(1f, 0.5f);
            panel.anchoredPosition = new Vector2(-ScreenMarginPx, 0f);

            // The hint lives here, on top of the grid, and not under the
            // subtitle where PRD 12.4 puts it. That is not a rearrangement for
            // its own sake: the title screen's hint ENDS with "ou cliquez un
            // niveau ci-dessous", the string is pinned to the character, and in
            // a two panel layout the only place the grid is genuinely BELOW it
            // is this one. It also stops the longest hint wrapping, because
            // 932 px of grid is wider than the text column. The reading order
            // of 12.4 is kept: title and subtitle, then hint, then the levels
            // label, then the grid.
            _hint = NewLabel("Hint", panel, HintSizePx, HintColor,
                TextAnchor.MiddleCenter, TextWeight.Regular);
            CapWidth(_hint, GridInnerWidthPx, false);

            // PRD 12.4's 26 px between the hint and the levels label, less the
            // two 4 px gaps the layout group puts either side of a spacer.
            NewSpacer("HintSpacer", panel, GridSpacerPx - (2f * ColumnSpacingPx));

            _levelsLabel = NewLabel("LevelsLabel", panel, LevelsLabelSizePx, LevelsLabelColor,
                TextAnchor.MiddleCenter, TextWeight.Regular);
            CapWidth(_levelsLabel, GridInnerWidthPx, false);

            BuildGrid(panel);

            _tooltip = NewLabel("Tooltip", panel, LevelsLabelSizePx, LevelsLabelColor,
                TextAnchor.MiddleCenter, TextWeight.Regular);
            // The grid decides this panel's width, never the hover line: the
            // longest level subtitle is under the grid's own 932 px, and the cap
            // means a longer one added later cannot widen the plate.
            CapWidth(_tooltip, GridInnerWidthPx, false);
            LayoutElement tooltipSize = _tooltip.gameObject.GetComponent<LayoutElement>();
            // Fixed height so the panel does not jump as the hover line fills
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
            for (var i = 0; i < count; i++)
            {
                // Captured by the click and hover callbacks below: a loop
                // variable read later would be the last index for every button.
                int index = i;

                var cell = new Cell();
                cell.Rect = NewRect("Level" + (i + 1), grid);

                // The cell fades as a whole, glyph and name included, which is
                // what "locked buttons at 45 percent" means: a ColorBlock only
                // ever tints the background graphic.
                cell.Group = cell.Rect.gameObject.AddComponent<CanvasGroup>();

                cell.Background = cell.Rect.gameObject.AddComponent<Image>();
                cell.Background.sprite = MenuArt.RoundedFill(CellRadiusPx);
                cell.Background.type = Image.Type.Sliced;
                // White here: the ColorBlock below carries the actual colours,
                // and Selectable multiplies the two.
                cell.Background.color = Color.white;

                cell.Button = cell.Rect.gameObject.AddComponent<Button>();
                cell.Button.targetGraphic = cell.Background;
                cell.Button.transition = Selectable.Transition.ColorTint;
                // The original set focus_mode = FOCUS_NONE: the grid is clicked,
                // never tabbed through, and Enter belongs to the hint line.
                // V-MENU-03's focus ring does NOT change that: turning
                // navigation on would let the UI module's Submit fire a level
                // button on the same Enter that starts or restarts the run, so
                // one key would do two things. The ring draws the state; the
                // travel that would reach it is a change to input handling and
                // is out of this tier's scope.
                Navigation navigation = cell.Button.navigation;
                navigation.mode = Navigation.Mode.None;
                cell.Button.navigation = navigation;
                cell.Button.colors = NormalColors;

                cell.Button.onClick.AddListener(() =>
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
                // The same two events drive the lift of V-MENU-03.
                EventTrigger hover = cell.Rect.gameObject.AddComponent<EventTrigger>();
                EventTrigger.Entry enter = new EventTrigger.Entry();
                enter.eventID = EventTriggerType.PointerEnter;
                enter.callback.AddListener(delegate { SetTooltip(index); });
                hover.triggers.Add(enter);

                EventTrigger.Entry exit = new EventTrigger.Entry();
                exit.eventID = EventTriggerType.PointerExit;
                exit.callback.AddListener(delegate { ClearTooltip(index); });
                hover.triggers.Add(exit);

                BuildCellContents(cell);
                _cells.Add(cell);
            }
        }

        /// <summary>
        /// What a cell draws on top of its background: the picture, the padlock,
        /// the name and the focus ring. None of them takes a raycast, so the
        /// button under them gets every click and every hover.
        /// </summary>
        void BuildCellContents(Cell cell)
        {
            RectTransform thumb = NewRect("Thumb", cell.Rect);
            thumb.anchorMin = Vector2.zero;
            thumb.anchorMax = Vector2.one;
            thumb.offsetMin = new Vector2((ButtonWidthPx - ThumbWidthPx) * 0.5f,
                LabelBottomPx + LabelBandPx + ThumbGapPx);
            thumb.offsetMax = new Vector2(-(ButtonWidthPx - ThumbWidthPx) * 0.5f, -ThumbTopPx);
            cell.Thumb = thumb.gameObject.AddComponent<RawImage>();
            cell.Thumb.raycastTarget = false;
            // Off until a picture arrives: a RawImage with no texture draws a
            // white rectangle, which would look like a thumbnail that failed
            // rather than like a button that never had one.
            cell.Thumb.enabled = false;

            RectTransform padlock = NewRect("Lock", cell.Rect);
            padlock.anchorMin = new Vector2(0.5f, 1f);
            padlock.anchorMax = new Vector2(0.5f, 1f);
            padlock.pivot = new Vector2(0.5f, 1f);
            padlock.sizeDelta = new Vector2(MenuArt.LockWidthPx, MenuArt.LockHeightPx);
            padlock.anchoredPosition = new Vector2(0f,
                -(ThumbTopPx + ((ThumbHeightPx - MenuArt.LockHeightPx) * 0.5f)));
            cell.Lock = padlock.gameObject.AddComponent<Image>();
            cell.Lock.sprite = MenuArt.LockGlyph();
            cell.Lock.color = ButtonLabelLocked;
            cell.Lock.raycastTarget = false;
            cell.Lock.enabled = false;

            Text label = NewLabel("Label", cell.Rect, ButtonTextSizePx, ButtonLabelUnlocked,
                TextAnchor.MiddleCenter, TextWeight.Regular);
            Stretch(label.rectTransform);
            // A name longer than the 180 px cell has to wrap to a second
            // line, which the name band holds at 14 px. uGUI has no margin, so
            // the padding is an inset on the rect (ApplyCellState moves it
            // between the band and the whole cell), and wrapping has to be
            // asked for: Fonts.Apply leaves labels overflowing, which is right
            // for a one line prompt and wrong for a level name.
            label.rectTransform.offsetMin = new Vector2(LabelInsetPx, 2f);
            label.rectTransform.offsetMax = new Vector2(-LabelInsetPx, -2f);
            label.horizontalOverflow = HorizontalWrapMode.Wrap;
            label.verticalOverflow = VerticalWrapMode.Overflow;
            cell.Label = label;

            // Last child, so the ring draws over the picture and the name.
            RectTransform focus = NewRect("Focus", cell.Rect);
            Stretch(focus);
            cell.Focus = focus.gameObject.AddComponent<Image>();
            cell.Focus.sprite = MenuArt.FocusRing(CellRadiusPx, FocusRingPx);
            cell.Focus.type = Image.Type.Sliced;
            cell.Focus.fillCenter = false;
            cell.Focus.color = FocusTint;
            cell.Focus.raycastTarget = false;
            cell.Focus.enabled = false;
        }

        /// <summary>
        /// A rounded plate that sizes itself to what it holds. The panel IS the
        /// layout group: one object fewer, and the plate can never be a pixel
        /// out of step with the column it is behind.
        /// </summary>
        static RectTransform NewPanel(string name, Transform parent, Vector2 pivot)
        {
            RectTransform panel = NewRect(name, parent);
            panel.pivot = pivot;

            Image plate = panel.gameObject.AddComponent<Image>();
            plate.sprite = MenuArt.RoundedFill(Mathf.RoundToInt(PanelRadiusPx));
            plate.type = Image.Type.Sliced;
            plate.color = PanelColor;
            // The plate takes the clicks that land on it so a stray click beside
            // a button does nothing, exactly as the dim behind it does.
            plate.raycastTarget = true;

            VerticalLayoutGroup layout = panel.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.childAlignment = TextAnchor.UpperCenter;
            layout.spacing = ColumnSpacingPx;
            layout.padding = new RectOffset(
                Mathf.RoundToInt(PanelPaddingPx), Mathf.RoundToInt(PanelPaddingPx),
                Mathf.RoundToInt(PanelPaddingPx), Mathf.RoundToInt(PanelPaddingPx));
            layout.childControlWidth = true;
            layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;

            // As tall and as wide as what it holds, and pinned by a pivot on the
            // screen edge it belongs to, so it stays put whatever the mode puts
            // in it.
            ContentSizeFitter fitter = panel.gameObject.AddComponent<ContentSizeFitter>();
            fitter.horizontalFit = ContentSizeFitter.FitMode.PreferredSize;
            fitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            return panel;
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
        /// A label on the project typeface. Every menu label sits on one of the
        /// two plates, which is the case Fonts.cs reserves TextEdge.Shadow for:
        /// the contrast is the panel's job and the edge only adds depth. The
        /// title takes the title weight (which under Manrope draws like the
        /// regular one, see Fonts.StyleFor: the hierarchy here is carried by 72
        /// px against 22).
        /// </summary>
        static Text NewLabel(string name, Transform parent, float sizePx, Color color,
            TextAnchor alignment, TextWeight weight)
        {
            RectTransform rect = NewRect(name, parent);
            Text label = rect.gameObject.AddComponent<Text>();
            // Labels never eat a click: the button under them must get it, and
            // Fonts.Apply clears raycastTarget for exactly that reason.
            Fonts.Apply(label, Mathf.RoundToInt(sizePx), color, alignment,
                TextEdge.Shadow, Fonts.EdgeColor, weight);
            return label;
        }

        /// <summary>
        /// Caps how wide a label may ask its panel to be.
        ///
        /// This is what makes the two panel layout hold. A uGUI Text reports the
        /// width of its UNWRAPPED string as its preferred width, so the control
        /// list of the title screen would ask its plate for some 780 px and push
        /// it straight through the level grid. A LayoutElement outranks the Text
        /// (higher layout priority), so the plate stops at the column width and
        /// the string runs onto a second line instead. The string itself is
        /// untouched: wrapping is where the glyphs land, not what they say.
        ///
        /// Wrap is asked for explicitly because Fonts.Apply leaves labels
        /// overflowing, which is right for a one line prompt over the world and
        /// wrong for a paragraph in a panel.
        /// </summary>
        static void CapWidth(Text label, float widthPx, bool wrap)
        {
            if (wrap)
            {
                label.horizontalOverflow = HorizontalWrapMode.Wrap;
            }
            LayoutElement element = label.gameObject.GetComponent<LayoutElement>();
            if (element == null)
            {
                element = label.gameObject.AddComponent<LayoutElement>();
            }
            element.preferredWidth = widthPx;
            element.flexibleWidth = 0f;
        }

        static void NewSpacer(string name, Transform parent, float heightPx)
        {
            RectTransform rect = NewRect(name, parent);
            LayoutElement element = rect.gameObject.AddComponent<LayoutElement>();
            element.minHeight = heightPx;
            element.preferredHeight = heightPx;
        }

        // ---- Per-cell widgets and colours -----------------------------------

        /// <summary>
        /// Everything one level cell owns. A class rather than the parallel
        /// lists this file used to keep, because a cell went from two widgets to
        /// seven with this tier and seven lists that must stay the same length
        /// is a bug waiting for the first early return.
        /// </summary>
        sealed class Cell
        {
            public RectTransform Rect;
            public CanvasGroup Group;
            public Button Button;
            public Image Background;
            public Image Lock;
            public Image Focus;
            public RawImage Thumb;
            public Text Label;

            /// <summary>Text the hover line shows, refreshed with the grid.</summary>
            public string Tooltip = string.Empty;

            /// <summary>The level's thumbnail once the studio has produced one.</summary>
            public Texture Picture;

            /// <summary>True once a build has been asked for, so it is asked once.</summary>
            public bool Requested;

            /// <summary>Current hover lift, 1 at rest.</summary>
            public float Scale = 1f;
        }

        static readonly ColorBlock NormalColors = MakeColors(ButtonNormal);
        static readonly ColorBlock CurrentColors =
            MakeColors(Color.Lerp(ButtonNormal, CurrentTint, CurrentTintAmount));

        /// <summary>
        /// A ColorBlock around one resting colour. The disabled colour is the
        /// resting one on purpose: the 45 percent of a locked cell is carried by
        /// its CanvasGroup, which dims the name and the padlock with the plate
        /// instead of dimming the plate alone.
        /// </summary>
        static ColorBlock MakeColors(Color normal)
        {
            ColorBlock colors = ColorBlock.defaultColorBlock;
            colors.normalColor = normal;
            colors.highlightedColor = Color.Lerp(normal, ButtonHighlighted, 0.75f);
            colors.pressedColor = Color.Lerp(normal, ButtonPressed, 0.75f);
            colors.selectedColor = normal;
            colors.disabledColor = normal;
            return colors;
        }

        // ---- Drawn art (PRD_VISUAL 3.2: no icon files) -----------------------

        /// <summary>
        /// The shapes this screen is made of, drawn into small textures once and
        /// shared by every widget that wants them. PRD_VISUAL 3.2 as amended
        /// (appendix C.11) allows the font and the CC0 material sets and nothing
        /// else: no sprite, no icon file, no nine-slice exported from anywhere.
        ///
        /// Each shape is a 9-sliced ALPHA MASK in white, tinted by the Image
        /// that draws it, so one 28 x 28 texture serves the cells, the plates,
        /// the focus rings and any colour they are ever asked to take.
        /// </summary>
        static class MenuArt
        {
            /// <summary>The padlock's texture, and the size a cell draws it at.</summary>
            public const int LockWidthPx = 26;
            public const int LockHeightPx = 32;

            const int LockTextureWidth = 32;
            const int LockTextureHeight = 40;

            static readonly Dictionary<int, Sprite> Fills = new Dictionary<int, Sprite>();
            static readonly Dictionary<int, Sprite> Rings = new Dictionary<int, Sprite>();
            static Sprite _lock;

            /// <summary>
            /// True once a texture could not be made. It stops the next
            /// twenty-six attempts, so a machine that cannot allocate a 28 px
            /// texture says so ONCE instead of once per cell.
            /// </summary>
            static bool _broken;

            /// <summary>A filled rounded rectangle, 9-sliced on its radius.</summary>
            public static Sprite RoundedFill(int radius)
            {
                if (_broken)
                {
                    return null;
                }
                Sprite sprite;
                if (Fills.TryGetValue(radius, out sprite) && sprite != null)
                {
                    return sprite;
                }
                sprite = BuildRounded(radius, 0f, "MenuRoundedFill" + radius);
                Fills[radius] = sprite;
                return sprite;
            }

            /// <summary>The same outline, hollow: V-MENU-03's focus ring.</summary>
            public static Sprite FocusRing(int radius, float thickness)
            {
                if (_broken)
                {
                    return null;
                }
                Sprite sprite;
                if (Rings.TryGetValue(radius, out sprite) && sprite != null)
                {
                    return sprite;
                }
                sprite = BuildRounded(radius, thickness, "MenuFocusRing" + radius);
                Rings[radius] = sprite;
                return sprite;
            }

            /// <summary>
            /// The padlock of V-MENU-02 and V-MENU-03: a shackle over a body
            /// with a keyhole, drawn from three distance fields so it is smooth
            /// at any size the cell asks for.
            /// </summary>
            public static Sprite LockGlyph()
            {
                if (_broken)
                {
                    return null;
                }
                if (_lock != null)
                {
                    return _lock;
                }

                var pixels = new Color32[LockTextureWidth * LockTextureHeight];
                const float bodyTop = 23f;
                const float shackleY = 23f;
                const float shackleOuter = 9.5f;
                const float shackleInner = 6f;

                for (var y = 0; y < LockTextureHeight; y++)
                {
                    int row = y * LockTextureWidth;
                    for (var x = 0; x < LockTextureWidth; x++)
                    {
                        float px = x + 0.5f;
                        float py = y + 0.5f;

                        // The body: a rounded box from the bottom up to bodyTop.
                        float body = -RoundedBoxDistance(px - (LockTextureWidth * 0.5f),
                            py - (bodyTop * 0.5f), 13f, bodyTop * 0.5f, 4f);

                        // The shackle: the upper half of an annulus.
                        float ring = 0f;
                        if (py >= shackleY)
                        {
                            float dx = px - (LockTextureWidth * 0.5f);
                            float dy = py - shackleY;
                            float d = Mathf.Sqrt((dx * dx) + (dy * dy));
                            ring = Mathf.Min(shackleOuter - d, d - shackleInner);
                        }

                        // The keyhole, cut out of the body.
                        float kx = px - (LockTextureWidth * 0.5f);
                        float ky = py - 11f;
                        float hole = 2.7f - Mathf.Sqrt((kx * kx) + (ky * ky));

                        float ink = Mathf.Max(body, ring);
                        float a = Mathf.Clamp01(ink + 0.5f) * (1f - Mathf.Clamp01(hole + 0.5f));
                        pixels[row + x] = new Color32(255, 255, 255,
                            (byte)Mathf.RoundToInt(Mathf.Clamp01(a) * 255f));
                    }
                }

                Texture2D texture = NewTexture(LockTextureWidth, LockTextureHeight, "MenuLockGlyph");
                if (texture == null)
                {
                    return null;
                }
                texture.SetPixels32(pixels);
                texture.Apply(false, true);
                _lock = Sprite.Create(texture,
                    new Rect(0f, 0f, LockTextureWidth, LockTextureHeight),
                    new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect);
                _lock.name = "MenuLockGlyph";
                return _lock;
            }

            /// <summary>
            /// One rounded rectangle, filled when thickness is 0 and hollow
            /// otherwise. The texture is 2 r + 4 square and the 9-slice border
            /// is exactly r, so the four corners are never stretched and the 4
            /// px core is what an Image of any size repeats.
            /// </summary>
            static Sprite BuildRounded(int radius, float thickness, string name)
            {
                int size = (radius * 2) + 4;
                float half = size * 0.5f;
                float inner = half - radius;

                var pixels = new Color32[size * size];
                for (var y = 0; y < size; y++)
                {
                    int row = y * size;
                    for (var x = 0; x < size; x++)
                    {
                        float d = RoundedBoxDistance(x + 0.5f - half, y + 0.5f - half,
                            inner + radius, inner + radius, radius);
                        // One pixel of antialiasing on the outside edge, and on
                        // the inside edge of a ring.
                        float a = Mathf.Clamp01(0.5f - d);
                        if (thickness > 0f)
                        {
                            a *= Mathf.Clamp01(d + thickness + 0.5f);
                        }
                        pixels[row + x] = new Color32(255, 255, 255,
                            (byte)Mathf.RoundToInt(a * 255f));
                    }
                }

                Texture2D texture = NewTexture(size, size, name);
                if (texture == null)
                {
                    return null;
                }
                texture.SetPixels32(pixels);
                texture.Apply(false, true);

                Sprite sprite = Sprite.Create(texture, new Rect(0f, 0f, size, size),
                    new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect,
                    new Vector4(radius, radius, radius, radius));
                sprite.name = name;
                return sprite;
            }

            /// <summary>
            /// Signed distance from a point to a rounded box centred on the
            /// origin: negative inside, positive outside. The same formula the
            /// polaroid's shadow uses, and it is measured as a distance rather
            /// than per axis so a corner is as crisp as an edge.
            /// </summary>
            static float RoundedBoxDistance(float px, float py, float halfWidth, float halfHeight,
                float radius)
            {
                float ex = Mathf.Abs(px) - halfWidth + radius;
                float ey = Mathf.Abs(py) - halfHeight + radius;
                float outX = Mathf.Max(ex, 0f);
                float outY = Mathf.Max(ey, 0f);
                return Mathf.Sqrt((outX * outX) + (outY * outY))
                    + Mathf.Min(Mathf.Max(ex, ey), 0f) - radius;
            }

            /// <summary>
            /// The one texture allocation of this whole screen, and the one
            /// place it can fail.
            ///
            /// It is wrapped because of what a throw here would cost: this
            /// class is reached from Menu.Awake, Menu is built inside Main.Awake,
            /// and an exception inside Awake abandons THE REST OF AWAKE. That is
            /// the exact mechanism the README records under TextMeshPro, where a
            /// broken label left the game with no player, no level root and no
            /// rewind and the symptom read as "the levels are empty". A menu
            /// that cannot draw its rounded corners must cost rounded corners
            /// and nothing else, so a failure returns null, every caller of this
            /// class treats a null sprite as "draw the plain shape", and the
            /// grid keeps its twenty-five buttons.
            /// </summary>
            static Texture2D NewTexture(int width, int height, string name)
            {
                try
                {
                    var texture = new Texture2D(width, height, TextureFormat.RGBA32, false, false);
                    texture.name = name;
                    texture.wrapMode = TextureWrapMode.Clamp;
                    texture.filterMode = FilterMode.Bilinear;
                    return texture;
                }
                catch (Exception e)
                {
                    _broken = true;
                    Debug.LogWarning("[Menu] " + name + " could not be drawn, the menu keeps"
                        + " its square corners: " + e.Message);
                    return null;
                }
            }
        }
    }

    /// <summary>
    /// V-MENU-04's letter settle: the title's characters drop into place with a
    /// 0.4 s stagger, once.
    ///
    /// A mesh effect on the ONE label and not nine labels of one letter each,
    /// and that is a correctness decision rather than a tidiness one. The title
    /// carries a string gameplay PRD 12.4 pins, the shot probe prints every menu
    /// label with its text, and verify-player.ps1 greps that dump for
    /// text="VIEWPOINT". Split into letters, the pinned string would not exist
    /// anywhere on screen and the check that proves the menu is not empty would
    /// go red for a purely decorative reason.
    ///
    /// It moves letters and never fades them. Fonts.Apply puts a Shadow under
    /// this label with useGraphicAlpha off (its comment says why), so the shadow
    /// copies keep their own alpha whatever the glyph does: a per letter fade
    /// would leave the dark copy of a letter hanging in the air before the
    /// letter arrived. The overlay's own 0.2 s fade takes care of the alpha for
    /// all of them at once.
    ///
    /// Nothing here gates anything. It writes vertex positions, it stops on its
    /// own when the last letter lands, and Menu.Update reads the keyboard
    /// whether it is running or not.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class MenuTitleSettle : BaseMeshEffect
    {
        /// <summary>Total spread between the first letter and the last (PRD_VISUAL 4.12).</summary>
        const float StaggerSeconds = 0.4f;

        /// <summary>How long one letter takes to land.</summary>
        const float LetterSeconds = 0.32f;

        /// <summary>How far above its place a letter starts, in reference pixels.</summary>
        const float DropPx = 18f;

        float _startedAt = -1f;
        bool _playing;

        /// <summary>Starts the settle from the top. Called once, by the menu.</summary>
        public void Play()
        {
            _startedAt = Time.unscaledTime;
            _playing = true;
            if (graphic != null)
            {
                graphic.SetVerticesDirty();
            }
        }

        void Update()
        {
            // A Text only rebuilds its mesh when something dirties it, so the
            // animation is this line. It stops as soon as ModifyMesh reports the
            // last letter home, which is why this costs nothing for the rest of
            // the run.
            if (_playing && graphic != null)
            {
                graphic.SetVerticesDirty();
            }
        }

        public override void ModifyMesh(VertexHelper vh)
        {
            if (!IsActive() || !_playing)
            {
                return;
            }

            int quads = vh.currentVertCount / 4;
            if (quads <= 0)
            {
                _playing = false;
                return;
            }

            float elapsed = Time.unscaledTime - _startedAt;
            var pending = false;
            var vertex = new UIVertex();

            for (var q = 0; q < quads; q++)
            {
                // One quad per visible character, because this effect is FIRST
                // in the modifier list and therefore sees the raw text mesh.
                float delay = quads > 1 ? StaggerSeconds * q / (quads - 1) : 0f;
                float t = Mathf.Clamp01((elapsed - delay) / LetterSeconds);
                if (t < 1f)
                {
                    pending = true;
                }

                float drop = (1f - EaseOut(t)) * DropPx;
                if (drop <= 0f)
                {
                    continue;
                }

                for (var c = 0; c < 4; c++)
                {
                    int i = (q * 4) + c;
                    vh.PopulateUIVertex(ref vertex, i);
                    vertex.position = new Vector3(vertex.position.x, vertex.position.y + drop,
                        vertex.position.z);
                    vh.SetUIVertex(vertex, i);
                }
            }

            if (!pending)
            {
                _playing = false;
            }
        }

        static float EaseOut(float t)
        {
            float k = 1f - Mathf.Clamp01(t);
            return 1f - (k * k * k);
        }
    }
}
