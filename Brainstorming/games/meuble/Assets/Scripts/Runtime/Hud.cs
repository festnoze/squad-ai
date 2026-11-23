using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// HUD (PRD 4.3, 9): eye indicator top center, red edge pulse, title card, controls, fail and win
    /// panels. Text is uGUI Text on the built in LegacyRuntime.ttf (no TextMeshPro, PRD 8.4). Panels are
    /// shown and hidden by enabling their own Canvas, never their GameObject.
    /// M2 (docs/CONTRACT_M2.md 7, 11.6): the eye has three states (closed, open calm, open alarm); the
    /// labelled creak bar left of the eye (flashing during the warning) and the labelled suspicion bar right
    /// of it (highest across inhabitants); the suspicion strings on the fail panel and the win.next line on
    /// the win panel. Each M2 element has its own Canvas, hidden when its rule is off.
    /// M3 (docs/CONTRACT_M3.md 6): the whole HUD hides while a menu is open (<see cref="SetVisible"/>); after the
    /// last level of levels.json the win panel is the end screen (<see cref="ShowEnd"/>).
    /// M3.1: the eye and the two gauges sit in a band at the bottom of the screen, above the controls line. The
    /// orbit camera frames the chair at the center and looks down on the room, so heads and the "?" and "!"
    /// markers above them are in the upper half: nothing covers them and no marker is ever moved.
    /// M4 (docs/CONTRACT_M4.md 2 and 3): the hints of the current body only, in the bottom corners of the controls
    /// line (<see cref="SetBodyHints"/>), and the sat-on line above the band while the furniture is pinned
    /// (<see cref="SetSatOn"/>). M4.1: in the same place, the tipped line while the stool lies (<see cref="SetTipped"/>).
    /// M5 (docs/CONTRACT_M5_v3.md 4 and 15.5, CONTRACT_M5.md 3 and 16.10): a fourth eye state, <see cref="HudEye.Dog"/> (only
    /// the dog sees the furniture), drawn with dog ears so it differs by shape; the door hint (hud.door) in the sat-on row
    /// while a closed leaf is in reach (<see cref="ShowDoorHint"/>); and the people of the level under the intro card's
    /// hint (<see cref="ShowPeople"/>): "Ici : " and their names, then one line each with the name and the trait.
    /// M5 wave 5B (docs/CONTRACT_M5.md 6, 16.5): the balance gauge (hud.balance), shown only while the furniture carries a
    /// load (<see cref="SetBalance"/>): |dv| over the fall threshold, red above <see cref="Tuning.BalanceWarning"/>. It sits in
    /// the bottom band beside the creak gauge, on its left (the band has no room under the creak gauge: the controls line).
    /// </summary>
    public sealed class Hud : MonoBehaviour
    {
        /// <summary>Open in both seen states (calm and alarm), closed when unseen.</summary>
        public bool EyeOpen { get; private set; }

        /// <summary>M2.1: which of the three eye states shows.</summary>
        public HudEye Eye { get; private set; }
        public bool FailVisible => failCanvas != null && failCanvas.enabled;
        public bool WinVisible => winCanvas != null && winCanvas.enabled;

        /// <summary>
        /// M8 touch redesign: the win panel's own Next level/Replay/Menu buttons are up (a win with no end screen; the
        /// end screen has its own Menu and Replay instead). None of them is EventSystem-selected (Enter and gamepad A
        /// keep loading the next level the way GameState already reads them, so nothing here double-fires it); Menu
        /// reads this only to free the mouse cursor so the buttons can be clicked (<see cref="Menu.WantsCursor"/>).
        /// </summary>
        public bool WinButtonsVisible => WinVisible && !EndVisible;
        public Font Font { get; private set; }

        /// <summary>Resources path of the title's display face (Assets/ThirdParty/Fonts/Resources, SIL OFL 1.1, docs/LICENSES.md).</summary>
        public const string DisplayFontResource = "DMSerifDisplay-Regular";
        private static Font displayFont;

        /// <summary>
        /// M7 title redesign: the display face of the game title (title page, intro cards, title page buttons). Falls back to
        /// the built-in font when the file is missing, so text always renders.
        /// </summary>
        public static Font DisplayFont
        {
            get
            {
                if (displayFont == null)
                {
                    displayFont = Resources.Load<Font>(DisplayFontResource);
                    if (displayFont == null)
                    {
                        Debug.LogWarning("[Hud] " + DisplayFontResource + " not found: the title uses the built-in font");
                        displayFont = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
                    }
                }
                return displayFont;
            }
        }

        /// <summary>M6 (CONTRACT_M6 2.3): the dashed/striped pattern over the pulse is showing now (tests).</summary>
        public bool PulsePatternVisible => pulsePattern != null && pulsePattern.color.a > 0f;

        /// <summary>M6 (CONTRACT_M6 2.2): the controls line shows the gamepad names now (tests).</summary>
        public bool ControlsShowGamepad => controlsGamepad;

        /// <summary>Every label by name, for the built player check (labels must carry text).</summary>
        public readonly Dictionary<string, Text> Labels = new Dictionary<string, Text>();

        private Canvas rootCanvas;
        private Canvas failCanvas;
        private Canvas winCanvas;
        private Image eye;
        private Image eyeBackdrop;
        // Eye redesign (2026-11-20): the half open frame shown for an instant between the closed and the open eye, how
        // long ago the eye last changed, and whether that change opened or closed it (EyeBlink, AnimateEye).
        private Image eyeBlink;
        private float eyeChangeAge = 99f;
        private bool eyeChangeOpens;
        private bool eyeChangeBlinks;
        private float hudClock;

        /// <summary>Shots only: when above 0, every frame advances the HUD's animation clock by exactly this many seconds.</summary>
        public static float ShotStep;

        private Image pulse;
        // M6 (docs/CONTRACT_M6.md 2.3): the pattern over the pulse, and 2.2's controls line (gamepad names swap in).
        private Image pulsePattern;
        private Text controls;
        private bool controlsGamepad;
        private bool controlsTouch;
        private CanvasGroup titleCard;
        private Text winBody;
        private float seenMoving;
        private float titleTimer;

        // ----- LEVELNUM: the intro card's full-screen dim with the level number as holes in it (CardNumber). -----
        private CardNumber cardNumber;
        private int levelNumber;

        /// <summary>
        /// LEVELNUM: accessibility hook, false by default (the game has no reduced-motion option yet). True, the intro card's
        /// level number skips its zoom and shows in its final place at once.
        /// </summary>
        public static bool ReducedMotion;

        /// <summary>The intro card number's values in use (LEVELNUM round 3: StreamingAssets/card_number.json, read at each card).</summary>
        public CardNumberSettings CardSettings => cardNumber != null ? cardNumber.Settings : CardNumberSettings.Defaults;

        /// <summary>LEVELNUM: the dim's opacity behind the intro card (outside the number's holes; card_number.json dimOpacity).</summary>
        public float CardDimAlpha => CardSettings.DimOpacity;

        /// <summary>LEVELNUM: the number's zoom-out length in seconds (card_number.json zoomSeconds).</summary>
        public float NumberZoomSeconds => CardSettings.ZoomSeconds;

        /// <summary>LEVELNUM: the held card, its dim and the number fade out over this long from the first input (fadeSeconds).</summary>
        public float HeldCardFadeSeconds => CardSettings.FadeSeconds;

        // ----- M2 (docs/CONTRACT_M2.md 7): creak gauge, suspicion bar, suspicion fail panel, win.next. -----

        /// <summary>Creak gauge value shown (0 to 1) and whether the creak warning is on (the gauge shows its danger animation; the name predates it).</summary>
        public float CreakShown { get; private set; }
        public bool CreakFlashing { get; private set; }

        /// <summary>Highest suspicion across the inhabitants, as shown under the eye.</summary>
        public float SuspicionShown { get; private set; }

        public bool CreakGaugeVisible => creakCanvas != null && creakCanvas.enabled;
        public bool SuspicionGaugeVisible => suspicionCanvas != null && suspicionCanvas.enabled;
        public bool WinNextVisible => WinVisible && winNextCanvas != null && winNextCanvas.enabled;

        /// <summary>The reason the fail panel currently shows (None while it is hidden).</summary>
        public LoseReason FailReason { get; private set; }
        public bool SuspicionFailVisible => FailVisible && FailReason == LoseReason.Suspicion;
        public string FailTitleText => failTitle != null ? failTitle.text : null;
        public string FailBodyText => failBody != null ? failBody.text : null;

        // ----- M8 touch redesign (a phone has neither Enter nor R): the fail, win and end panels' own buttons. -----

        /// <summary>The fail panel's Retry (restarts the level); selected by default, so Enter and gamepad A submit it.</summary>
        public Button FailRetryButton { get; private set; }
        /// <summary>The fail panel's Menu (back to the title).</summary>
        public Button FailMenuButton { get; private set; }
        /// <summary>The win panel's Next level (only while a next level exists; shares win.next's own Canvas).</summary>
        public Button WinNextLevelButton { get; private set; }
        /// <summary>The win panel's Replay (restarts the level).</summary>
        public Button WinReplayButton { get; private set; }
        /// <summary>The win panel's Menu (back to the title).</summary>
        public Button WinMenuButton { get; private set; }
        /// <summary>The end screen's Replay (restarts the last level), beside <see cref="EndButton"/>.</summary>
        public Button EndReplayButton { get; private set; }

        private Canvas creakCanvas;
        private Canvas suspicionCanvas;
        private Canvas winNextCanvas;
        // The win panel's Replay and Menu (a plain win only; the end screen shows the EndGroup's row instead).
        private Canvas winButtonsCanvas;
        private Gauge creakGauge;
        private Gauge suspicionGauge;
        private Text failTitle;
        private Text failBody;
        // The fail panel's and win panel's own hint lines (the ones that used to say "Press R"/"Press Enter"): kept so
        // ShowFail/ShowWin/Relocalize can swap them for the touch wording while their Canvas stays the same.
        private Text failAction;
        private Text winNext;
        // Stars (idea 5, docs/next/progress/STARS.md): the row of three stars beside the time on the win panel (and beside the
        // end screen's own time), and the "New stars!" line under it. RecordLine shows them after it recorded the win.
        private StarRow winStars;
        private Text winStarsNew;

        // ----- M3 (docs/CONTRACT_M3.md 6): menus, end screen, markers below the HUD band. -----

        /// <summary>False while a menu is open: the HUD Canvas and every nested Canvas are disabled.</summary>
        public bool Visible { get; private set; } = true;

        /// <summary>The win panel shows end.title and end.body (the last level of levels.json was won).</summary>
        public bool EndVisible => WinVisible && endCanvas != null && endCanvas.enabled;

        /// <summary>The end screen's "Menu principal" button (Enter and gamepad A also go through GameState).</summary>
        public Button EndButton { get; private set; }

        public string WinTitleText => winTitle != null ? winTitle.text : null;
        public string WinBodyText => winBody != null ? winBody.text : null;

        /// <summary>The camera the world markers are seen through, and the game whose inhabitants carry them.</summary>
        public Camera View;
        public GameState Game;

        /// <summary>M3.1: the screen rect (pixels, y up) of the eye and the visible gauges, the bottom band.</summary>
        public Rect BandScreenRect
        {
            get
            {
                Rect band = WorldRect(eyeBackdrop != null ? eyeBackdrop.rectTransform : null);
                if (creakOn)
                {
                    band = Union(band, WorldRect(creakRect));
                }
                if (suspicionOn)
                {
                    band = Union(band, WorldRect(suspicionRect));
                }
                if (balanceOn)
                {
                    band = Union(band, WorldRect(balanceRect));
                }
                return band;
            }
        }

        // ----- M4 (docs/CONTRACT_M4.md 2 and 3): the hints of the current body and the sat-on line. -----

        /// <summary>"Maj : au ralenti" shows (every body while the Bodies rule is on).</summary>
        public bool CarefulHintVisible => carefulCanvas != null && carefulCanvas.enabled;

        /// <summary>
        /// "E : éteindre / allumer" shows (the floor lamp body while the Lamp rule is on). DOORAUTO: its text follows the
        /// device (hud.lamp, hud.lampPad, hud.lampTouch), label LampHintLabel.
        /// </summary>
        public bool LampHintVisible => lampCanvas != null && lampCanvas.enabled;

        /// <summary>"Quelqu'un est assis sur toi." shows (the player furniture is pinned by a sitter).</summary>
        public bool SatOnVisible => satOnCanvas != null && satOnCanvas.enabled;

        /// <summary>CONTRACT_M5 20: "Le chien te bloque : on vient te remettre en place." shows (the dog holds the furniture).</summary>
        public bool DogHoldVisible => dogHoldCanvas != null && dogHoldCanvas.enabled;

        /// <summary>M4.1: "Renversé : appuie sur une direction pour te relever." shows (the stool lies on its side).</summary>
        public bool TippedVisible => tippedCanvas != null && tippedCanvas.enabled;

        // ----- M5 (docs/CONTRACT_M5_v3.md 4, 15.2 and 15.5, CONTRACT_M5.md 3): the door hint and the people. -----

        /// <summary>"Pousse vers la porte pour l'ouvrir" shows (a closed leaf is in reach; DOORAUTO: a push, no key).</summary>
        public bool DoorHintVisible => doorCanvas != null && doorCanvas.enabled;

        /// <summary>The people block of the intro card shows (the level has people with a name).</summary>
        public bool PeopleVisible => peopleCanvas != null && peopleCanvas.enabled;

        // ----- M5 wave 5B (docs/CONTRACT_M5.md 6, 16.5): the balance gauge. -----

        /// <summary>The balance gauge shows (the furniture carries a load that has not fallen).</summary>
        public bool BalanceVisible => balanceCanvas != null && balanceCanvas.enabled;

        /// <summary>The balance shown, 0 to 1: |dv| over the fall threshold (1 is the fall).</summary>
        public float BalanceShown { get; private set; }

        /// <summary>The balance gauge is red: the ratio is above <see cref="Tuning.BalanceWarning"/> while it shows.</summary>
        public bool BalanceRed { get; private set; }

        /// <summary>The colour of the balance gauge's fill now (tests).</summary>
        public Color BalanceFillColor => balanceGauge != null ? balanceGauge.Fill.color : Color.clear;

        /// <summary>
        /// HUD gauge redesign (tests and shots): the fill each gauge draws now, 0 to 1. It eases toward the value set by
        /// GameState (<see cref="CreakShown"/>, <see cref="SuspicionShown"/>, <see cref="BalanceShown"/>), which stays exact.
        /// </summary>
        public float CreakFillDrawn => creakGauge != null ? creakGauge.Fill.fillAmount : 0f;
        public float SuspicionFillDrawn => suspicionGauge != null ? suspicionGauge.Fill.fillAmount : 0f;

        /// <summary>HUD gauge redesign: where each gauge's threshold marker stands (0 to 1 along its track; tests).</summary>
        public float CreakThreshold => creakGauge != null ? creakGauge.Threshold : 1f;
        public float SuspicionThreshold => suspicionGauge != null ? suspicionGauge.Threshold : 1f;

        /// <summary>Danger animation (tests): each gauge's fill colour, heat (0 to 1) and live sparks now.</summary>
        public Color CreakFillColour => creakGauge != null ? creakGauge.Fill.color : Color.clear;
        public float CreakHeat => creakGauge != null && creakGauge.Fx != null ? creakGauge.Fx.Heat : 0f;
        public float SuspicionHeat => suspicionGauge != null && suspicionGauge.Fx != null ? suspicionGauge.Fx.Heat : 0f;
        public int CreakSparks => creakGauge != null && creakGauge.Fx != null ? creakGauge.Fx.LiveSparks : 0;

        /// <summary>Eye redesign (tests): the blink's half open frame shows now (for an instant after the eye opens or closes).</summary>
        public bool EyeBlinkShowing => eyeBlink != null && eyeBlink.color.a > 0.5f;

        /// <summary>HUD gauge redesign: the suspicion gauge's screen rect in pixels, y up (empty when hidden; tests).</summary>
        public Rect SuspicionScreenRect => SuspicionGaugeVisible ? WorldRect(suspicionRect) : Rect.zero;

        /// <summary>The balance gauge's screen rect in pixels, y up (empty when hidden; tests).</summary>
        public Rect BalanceScreenRect => BalanceVisible ? WorldRect(balanceRect) : Rect.zero;

        /// <summary>The creak gauge's screen rect in pixels, y up (empty when hidden; tests).</summary>
        public Rect CreakScreenRect => CreakGaugeVisible ? WorldRect(creakRect) : Rect.zero;

        /// <summary>The lines the people block shows: "Ici : ..." first, then one line per person (tests).</summary>
        public IReadOnlyList<string> PeopleShown => peopleShown;

        /// <summary>Wave 5A.1 (critique m13): the people plate's screen rect in pixels, y up (empty when hidden; tests).</summary>
        public Rect PeopleScreenRect => PeopleVisible ? WorldRect(peoplePlate) : Rect.zero;

        /// <summary>The screen scale of the HUD canvas (screen pixels per reference pixel; tests).</summary>
        public float ScaleFactor => rootCanvas != null ? rootCanvas.scaleFactor : 1f;

        // ----- Onboarding tips (idea 3, docs/next/progress/TIPS.md): the first-time tips and the anchors they point at. -----

        /// <summary>The first-time tips of levels 1 to 3 (built by Init, a nested Canvas; null before Init).</summary>
        public Tips Tips { get; private set; }

        /// <summary>The eye's backdrop, what the eye and freeze tips point at.</summary>
        public RectTransform EyeAnchor => eyeBackdrop != null ? eyeBackdrop.rectTransform : null;

        /// <summary>The creak gauge's root, what the creak tip points at.</summary>
        public RectTransform CreakAnchor => creakRect;

        /// <summary>The suspicion gauge's root, what the suspicion tip points at.</summary>
        public RectTransform SuspicionAnchor => suspicionRect;

        private Canvas balanceCanvas;
        private RectTransform balanceRect;
        private Gauge balanceGauge;
        private bool balanceOn;
        private Canvas doorCanvas;
        private Canvas peopleCanvas;
        private RectTransform peoplePlate;
        private Text peopleHere;
        private Text peopleList;
        private Text peopleList2;
        private Vector2 peopleLaidFor;
        private bool doorOn;
        private bool peopleOn;
        private readonly List<string> peopleShown = new List<string>();

        private Canvas carefulCanvas;
        private Canvas lampCanvas;
        private Canvas satOnCanvas;
        private Canvas dogHoldCanvas;
        private Canvas tippedCanvas;
        private bool tippedOn;
        private bool carefulOn;
        private bool lampOn;
        private bool satOn;
        private bool dogHoldOn;

        // ----- Levels v2 (docs/levels_v2/LEVELS_V2.md 6, task C3b): held card, hint tokens, locked and lit hints, exit marker. -----
        private Text hintText;
        private Text startLine;
        private Image startPlate;
        // The intro card is held fully visible while the level waits for its first input (GameState.Started false).
        private bool cardHeld;
        private Canvas lockedCanvas;
        private Canvas litCanvas;
        private bool lockedOn;
        private bool litOn;
        private Canvas markerCanvas;
        private RectTransform markerRect;
        private Image markerPlate;
        private Image markerDoor;
        private Image markerArrow;
        private Image markerEye;
        private CanvasGroup markerGroup;
        private bool markerWanted;
        private bool markerClamped;
        private bool markerEyeOn;
        private Vector2 markerScreen;
        // The card was held at least once since ShowLevel: its fade then starts at the release instead of after 4 s.
        private bool cardWasHeld;

        private Canvas endCanvas;
        private Text winTitle;
        private Text winAction;
        private Text endTime;
        private RectTransform creakRect;
        private RectTransform suspicionRect;
        private bool creakOn = true;
        private bool suspicionOn = true;
        private bool failOn;
        private bool winOn;
        private bool winNextOn;
        private bool endOn;
        private readonly List<Canvas> markerCanvases = new List<Canvas>();
        private LevelInstance markerLevel;
        private static readonly Vector3[] Corners = new Vector3[4];

        // The bottom band, in reference pixels (1920 x 1080) from the bottom edge: the controls line, then the eye
        // and the gauges above it.
        private const float ControlsY = 22f;
        private const float EyeY = 80f;
        // HUD gauge redesign: 6 px lower and 8 px shorter than the M3.1 gauges, so their top (174) stays under the touch
        // careful toggle's bottom (179 units on a 4:3 tablet, the narrowest canvas).
        private const float GaugeY = 90f;
        private const float ActionY = -110f;
        private const float EndActionY = -150f;
        // M8 touch redesign: the fail, win and end panels' own button row, below every hint line and (on the win and
        // end panels) below win.next or the record line. At least 140 px tall at 1080p (a touch target) even when a
        // narrower than 16:9 window scales the canvas down (0.87 at 16:10, hence 170).
        private const float PanelButtonY = -300f;
        private const float PanelButtonWidth = 450f;
        private const float PanelButtonHeight = 170f;
        // End panel emphasis (2026-11-19): the panel's primary action (Retry on the fail panel, Next level on the win
        // panel, Menu principal on the end screen) is wider, taller and bold, in the selection red (PrimaryRed). The
        // secondary buttons got 30 px narrower for it, so the win row keeps its 1520 px (it fits a 4:3 tablet, whose
        // canvas is 1663 units wide at this scaler, with a margin). PanelButtonGap is the gap between two plates.
        private const float PanelPrimaryWidth = 540f;
        private const float PanelPrimaryHeight = 186f;
        private const int PanelPrimaryFontSize = 50;
        private const float PanelButtonGap = 40f;
        // Stars: the row's centre right of the time line (the body at y -10 on the win panel, EndTime at y -82 on the end
        // screen; the time's text spans about +-200 px at its widest), 56 px stars 8 px apart (184 px wide, so the row ends
        // at x 422, well inside a 4:3 tablet's 1663 unit canvas), and the "New stars!" line just under it. Above the button
        // row (its top is at -207) and clear of the record line (y -430).
        private const float WinStarsX = 330f;
        private const float WinStarsY = -10f;
        private const float EndStarsY = -82f;
        private const float WinStarSize = 56f;
        private const float WinStarGap = 8f;
        private const float WinStarsNewOffset = -40f;
        /// <summary>The menu button's selection red (<see cref="MenuButton"/>): the fail panel's selected Retry and the win panel's Next level at rest.</summary>
        public static readonly Color PrimaryRed = new Color(0.78f, 0.16f, 0.15f, 0.97f);
        private static readonly Color PrimaryRedHover = new Color(0.9f, 0.26f, 0.23f, 1f);
        // M4: the sat-on line, just above the eye backdrop (80 + 128 px).
        private const float SatOnY = 222f;
        private static readonly Color SatOnPlate = new Color(0.12f, 0.1f, 0.14f, 0.82f);
        private static readonly Color SatOnInk = new Color(1f, 0.9f, 0.62f, 1f);

        private static readonly Color BackdropClosed = new Color(0.1f, 0.1f, 0.12f, 0.55f);
        private static readonly Color BackdropCalm = new Color(0.16f, 0.3f, 0.42f, 0.85f);
        private static readonly Color BackdropAlarm = new Color(0.78f, 0.12f, 0.14f, 0.9f);
        // M5: the dog eye's backdrop, the dog's cone colour darker (wave 5A.1, CONTRACT_M5 17: a deep teal under the cyan
        // cone), never the alarm red nor the calm blue (its green is half again the calm one's).
        private static readonly Color BackdropDog = new Color(Tuning.DogConeColor.r * 0.55f, Tuning.DogConeColor.g * 0.55f,
            Tuning.DogConeColor.b * 0.55f, 0.88f);
        // The intro card's text, from the screen centre (reference pixels): the game title row, the level name, the hint.
        // The card spans the whole screen (its CanvasGroup fades everything on it) and its text keeps the M1 to M4 places.
        private const float CardTitleY = 280f;
        private const float CardNameY = 200f;
        private const float CardHintY = 100f;
        // Levels v2 (C3b): the hint's box, its top where the M1 one-line hint's top was (100 + 30), at most three lines tall.
        private const float CardHintTop = CardHintY + 30f;
        private const float CardHintWidth = 1600f;
        private const float CardHintHeight = 112f;
        private const int CardHintSize = 38;
        private const int CardHintMinSize = 26;
        // The start line (hud.start) on the sat-on row: nothing else uses that row while the level is held.
        // STARTFIX: wider for "Appuie sur Espace pour commencer (ou bouge)" (43 characters at size 40).
        private const float StartLineWidth = 1120f;
        private static readonly Color StartInk = new Color(1f, 0.93f, 0.66f, 1f);
        // The exit marker: its size, how far from the screen edge it clamps (reference pixels; the bottom margin clears the
        // eye band and the sat-on row), the fade (fully drawn from MarkerFadeFar metres, gone at MarkerFadeNear) and colours.
        private const float MarkerSize = 84f;
        private const float MarkerEdge = 64f;
        private const float MarkerBottomEdge = 320f;
        public const float MarkerFadeNear = 1f;
        public const float MarkerFadeFar = 3f;
        private const float MarkerHeight = 0.4f;
        /// <summary>Levels v2 (C3b): the exit marker's amber (never green beside the red player, AX3).</summary>
        public static readonly Color MarkerAmber = new Color(1f, 0.74f, 0.28f, 1f);
        private static readonly Color MarkerPlateColour = new Color(0.12f, 0.09f, 0.06f, 0.82f);
        // The top of the game title row (CardTitleY plus half its 60 px height): nothing of the people block goes below it.
        private const float CardTextTop = 310f;
        // M5: the people block of the intro card: the names line, then one line per person. Wave 5A.1 (critique m13): it
        // sits in the top band, above the card's text, so it never dims the player's furniture at the centre of the view;
        // from three people on, the person lines take two columns. At these sizes, shrunk to fit a narrow or short screen.
        private const float PeopleTop = 16f;
        private const float PeopleGap = 14f;
        private const float PeopleMargin = 24f;
        private const float PeopleHereHeight = 44f;
        private const float PeopleLineHeight = 36f;
        private const float PeoplePadding = 12f;
        private const float PeopleGutter = 56f;
        private const int PeopleHereSize = 32;
        private const int PeopleLineSize = 28;
        private const int PeopleMinSize = 16;
        // M6: opaque enough that an inhabitant's world marker ("?", "!", "z"), drawn behind every screen space overlay,
        // never bleeds through the plate during the intro card (CONTRACT_M6 polish); same dark tone as before.
        private static readonly Color PeoplePlate = new Color(0.08f, 0.07f, 0.1f, 0.95f);
        private const string PersonNameColor = "#FFD98C";
        // HUD gauge redesign (2026-11-19): each gauge's fill shifts from a calm colour (empty) to a warm one (at its threshold
        // marker) to the hot red (full). Creak: wood, amber, red; suspicion: gold, orange, red.
        private static readonly Color CreakWood = new Color(0.88f, 0.66f, 0.38f, 1f);
        private static readonly Color CreakAmber = new Color(1f, 0.56f, 0.2f, 1f);
        private static readonly Color CreakHot = new Color(1f, 0.28f, 0.18f, 1f);
        private static readonly Color SuspicionLow = new Color(1f, 0.83f, 0.32f, 1f);
        private static readonly Color SuspicionMid = new Color(1f, 0.55f, 0.2f, 1f);
        private static readonly Color SuspicionHigh = new Color(0.95f, 0.2f, 0.15f, 1f);
        // The gauge labels' cream (the menus' warm ink) and the threshold marker's.
        private static readonly Color GaugeInk = new Color(1f, 0.94f, 0.82f, 1f);
        private static readonly Color GaugeMarker = new Color(1f, 0.95f, 0.86f, 0.95f);
        private static readonly Color GaugeTick = new Color(1f, 0.95f, 0.86f, 0.3f);
        // The danger zone past the threshold: red stripes on the empty track.
        private static readonly Color GaugeDanger = new Color(0.8f, 0.18f, 0.14f, 0.3f);
        // M5 wave 5B: the balance gauge, a calm sea green that is neither the creak's wood nor the suspicion's yellow; red (the
        // creak's hot red, CreakHot) above the warning.
        private static readonly Color BalanceCalm = new Color(0.45f, 0.85f, 0.7f, 1f);
        // The capsule's geometry inside a gauge's 92 unit tall rect (reference pixels): the capsule at the bottom, the
        // icon's badge over its left end, the label above, right of the badge; the track inset in the capsule, after the
        // badge. GaugeLerpRate eases the drawn fill toward the value (per second), GaugeBumpRise is the rise in one
        // update that shakes the gauge (a discovery's 0.34 does; the creak's steady fill never does).
        private const float GaugeHeight = 84f;
        private const float CapsuleHeight = 40f;
        private const float CapsuleY = 10f;
        private const float CapsuleX = 26f;
        private const float BadgeSize = 60f;
        private const float TrackInset = 6f;
        private const float TrackLeft = BadgeSize + 2f;
        private const float GlowHalo = 14f;
        private const float GaugeLabelX = 70f;
        private const int GaugeLabelSize = 28;
        private const float GaugeLerpRate = 9f;
        private const float GaugeBumpRise = 0.08f;
        private const int GaugeTicks = 4;
        // The balance gauge's width and its gap to the creak gauge (reference pixels): narrower than the 330 of the creak and
        // suspicion gauges, so the band still fits a 5:4 screen.
        private const float BalanceWidth = 280f;
        private const float BalanceGap = 24f;
        // The creak and suspicion gauges: their inner edge this far from the screen centre, on either side of the eye, and
        // their width (reference pixels). The balance gauge is placed from these, so it moves with the creak gauge.
        private const float GaugeOffsetX = 128f;
        private const float GaugeWidth = 330f;
        private const float BalanceOffsetX = GaugeOffsetX + GaugeWidth + BalanceGap;

        public void Init()
        {
            Font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            if (Font == null)
            {
                Debug.LogError("[Hud] LegacyRuntime.ttf not found: no text will render");
            }
            rootCanvas = gameObject.AddComponent<Canvas>();
            rootCanvas.renderMode = RenderMode.ScreenSpaceOverlay;
            rootCanvas.sortingOrder = 10;
            var scaler = gameObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);
            scaler.matchWidthOrHeight = 0.5f;
            gameObject.AddComponent<GraphicRaycaster>();

            // Red edge pulse first, so everything else draws over it.
            pulse = NewImage(transform, "SeenPulse", ProceduralArt.Vignette, new Color(0.9f, 0.05f, 0.05f, 0f));
            Stretch(pulse.rectTransform);
            // M6 (docs/CONTRACT_M6.md 2.3): a dashed/striped pattern over the pulse, shown only while seen moving (never
            // in the calm or suspicious states, which show no pulse at all), so the warning is never colour alone.
            pulsePattern = NewImage(transform, "SeenPulsePattern", ProceduralArt.PulsePattern, new Color(1f, 1f, 1f, 0f));
            Stretch(pulsePattern.rectTransform);
            // LEVELNUM: the intro card's dim with the level number's holes, under the exit marker and every other HUD element.
            cardNumber = new CardNumber(transform);
            // Levels v2 (C3b): the exit marker over the world (walls included), under every other HUD element.
            BuildExitMarker();

            eyeBackdrop = NewImage(transform, "EyeBackdrop", ProceduralArt.Disc, BackdropClosed);
            Place(eyeBackdrop.rectTransform, new Vector2(0.5f, 0f), new Vector2(0f, EyeY), new Vector2(210f, 128f));
            eye = NewImage(eyeBackdrop.transform, "Eye", ProceduralArt.EyeClosed, Color.white);
            Place(eye.rectTransform, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(170f, 99f));
            eyeBlink = NewImage(eyeBackdrop.transform, "EyeBlink", ProceduralArt.EyeHalf, new Color(1f, 1f, 1f, 0f));
            Place(eyeBlink.rectTransform, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(170f, 99f));
            eyeBlink.canvasRenderer.cullTransparentMesh = true;

            controls = NewText(transform, "Controls", Strings.HudControls, 30, TextAnchor.LowerCenter, new Color(1f, 1f, 1f, 0.92f));
            Place(controls.rectTransform, new Vector2(0.5f, 0f), new Vector2(0f, ControlsY), new Vector2(1600f, 50f));

            var cardGo = new GameObject("TitleCard", typeof(RectTransform));
            cardGo.transform.SetParent(transform, false);
            titleCard = cardGo.AddComponent<CanvasGroup>();
            titleCard.interactable = false;
            titleCard.blocksRaycasts = false;
            Stretch((RectTransform)cardGo.transform);
            Text title = NewText(cardGo.transform, "Title", Strings.Title, 40, TextAnchor.MiddleCenter, new Color(1f, 0.92f, 0.75f, 1f));
            // M7 title redesign: the game title in its own display face, as on the title page.
            title.font = DisplayFont;
            title.fontSize = 46;
            Place(title.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, CardTitleY), new Vector2(1600f, 60f));
            Text levelName = NewText(cardGo.transform, "LevelName", Strings.Level1Name, 84, TextAnchor.MiddleCenter, Color.white);
            Place(levelName.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, CardNameY), new Vector2(1600f, 110f));
            Text hint = NewText(cardGo.transform, "Hint", Strings.Level1Hint, 38, TextAnchor.MiddleCenter, new Color(1f, 1f, 1f, 0.95f));
            Place(hint.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, CardHintY), new Vector2(1600f, 60f));
            // Levels v2 (C3b): the v2 hints run to two or three sentences. The hint keeps its top edge and wraps downward in
            // a box of at most CardHintHeight, its font shrunk until it fits (SetHintText).
            hint.rectTransform.pivot = new Vector2(0.5f, 1f);
            hint.rectTransform.anchoredPosition = new Vector2(0f, CardHintTop);
            hint.rectTransform.sizeDelta = new Vector2(CardHintWidth, CardHintHeight);
            hint.alignment = TextAnchor.UpperCenter;
            hint.horizontalOverflow = HorizontalWrapMode.Wrap;
            hintText = hint;
            BuildPeople(cardGo.transform);
            BuildStartLine(cardGo.transform);

            BuildCreakGauge();
            BuildSuspicionGauge();
            BuildBalanceGauge();
            BuildBodyHints();
            // Onboarding tips: over the band and the row hints, under the panels (built after them, so it draws over them).
            Tips = Tips.Build(this);

            failCanvas = NewPanel("FailPanel", Strings.FailTitle, Strings.FailBody, Strings.FailAction, new Color(0.25f, 0.02f, 0.03f, 0.62f),
                new Color(1f, 0.42f, 0.38f, 1f), out failBody);
            // M8 touch redesign: the panel's own Canvas overrides its sorting, so it needs its own raycaster for the
            // buttons below to be clickable and tappable (the same reason BuildEndGroup already adds one of its own).
            failCanvas.gameObject.AddComponent<GraphicRaycaster>();
            Labels.TryGetValue("FailPanelTitle", out failTitle);
            Labels.TryGetValue("FailPanelAction", out failAction);
            // End panel emphasis: Retry is the primary action, first and larger; it is red through the selection (it is
            // selected by default), so it stays dark at rest and Menu turns red alone when the D-pad moves onto it.
            FailRetryButton = MenuButton(failCanvas.transform, "FailRetry", Strings.FailRetry, DisplayFont, Labels);
            FailMenuButton = MenuButton(failCanvas.transform, "FailMenu", Strings.PauseMenu, DisplayFont, Labels);
            MakePrimary(FailRetryButton, false);
            PlaceRow(FailRetryButton, FailMenuButton);
            ChainLR(FailRetryButton, FailMenuButton);

            winCanvas = NewPanel("WinPanel", Strings.WinTitle, string.Format(Strings.WinBody, Strings.FormatSeconds(0f)), Strings.WinAction,
                new Color(0.02f, 0.16f, 0.08f, 0.58f), new Color(0.55f, 1f, 0.6f, 1f), out winBody);
            winCanvas.gameObject.AddComponent<GraphicRaycaster>();
            Labels.TryGetValue("WinPanelTitle", out winTitle);
            Labels.TryGetValue("WinPanelAction", out winAction);
            // Stars: beside the time, hidden until RecordLine shows them (ShowWinStars) for the win just recorded.
            winStars = new StarRow(winCanvas.transform, "WinStars", WinStarSize, WinStarGap);
            winStars.Place(new Vector2(0.5f, 0.5f), new Vector2(WinStarsX, WinStarsY));
            winStars.SetVisible(false);
            winStarsNew = NewText(winCanvas.transform, "WinStarsNew", Strings.StarsNewBest, 26, TextAnchor.MiddleCenter, Stars.Gold);
            Place(winStarsNew.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(WinStarsX, WinStarsY + WinStarsNewOffset), new Vector2(400f, 34f));
            winStarsNew.enabled = false;
            // win.next and the Next level button share a Canvas inside the win panel: shown only with a next level.
            var nextGo = new GameObject("WinNextGroup", typeof(RectTransform));
            nextGo.transform.SetParent(winCanvas.transform, false);
            Stretch((RectTransform)nextGo.transform);
            winNextCanvas = nextGo.AddComponent<Canvas>();
            nextGo.AddComponent<GraphicRaycaster>();
            winNext = NewText(nextGo.transform, "WinNext", Strings.WinNext, 38, TextAnchor.MiddleCenter, new Color(1f, 0.93f, 0.6f, 1f));
            Place(winNext.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, -170f), new Vector2(1600f, 60f));
            WinNextLevelButton = MenuButton(nextGo.transform, "WinNextLevel", Strings.WinNextButton, DisplayFont, Labels);
            // End screen fix (2026-11-20): Replay and Menu live in their own Canvas, shown only on a plain win. Children of
            // the win panel itself, they stayed up under the end screen (the win panel with its EndGroup) and drew a second
            // row over the end screen's own Replay and Menu principal.
            var rowGo = new GameObject("WinButtonsGroup", typeof(RectTransform));
            rowGo.transform.SetParent(winCanvas.transform, false);
            Stretch((RectTransform)rowGo.transform);
            winButtonsCanvas = rowGo.AddComponent<Canvas>();
            rowGo.AddComponent<GraphicRaycaster>();
            // Replay and Menu are not EventSystem-selected (WinButtonsVisible doc): Enter and gamepad A keep loading
            // the next level exactly as GameState already reads them, so no button here must also catch that press.
            WinReplayButton = MenuButton(rowGo.transform, "WinReplay", Strings.WinReplay, DisplayFont, Labels);
            WinMenuButton = MenuButton(rowGo.transform, "WinMenu", Strings.PauseMenu, DisplayFont, Labels);
            // End panel emphasis: Next level is the primary action, first and larger, and red at rest, since nothing
            // selects it (the same red as the fail panel's selected Retry).
            MakePrimary(WinNextLevelButton, true);
            PlaceRow(WinNextLevelButton, WinReplayButton, WinMenuButton);

            BuildEndGroup();
            HidePanels();
        }

        /// <summary>M8 touch redesign: explicit left/right Navigation between two buttons of the same row.</summary>
        private static void ChainLR(Button left, Button right)
        {
            Navigation ln = left.navigation;
            ln.mode = Navigation.Mode.Explicit;
            ln.selectOnRight = right;
            left.navigation = ln;
            Navigation rn = right.navigation;
            rn.mode = Navigation.Mode.Explicit;
            rn.selectOnLeft = left;
            right.navigation = rn;
        }

        /// <summary>
        /// End panel emphasis: <paramref name="button"/> becomes its panel's primary action, a bold and larger label
        /// (its plate is sized by <see cref="PlaceRow"/>). <paramref name="redAtRest"/> tints it the selection red with no
        /// selection at all (the win panel's Next level, which nothing selects); the fail panel's Retry is red through
        /// its default selection instead, so the D-pad never shows two red buttons at once.
        /// </summary>
        private static void MakePrimary(Button button, bool redAtRest)
        {
            Text label = button.GetComponentInChildren<Text>();
            if (label != null)
            {
                label.fontSize = PanelPrimaryFontSize;
                label.fontStyle = FontStyle.Bold;
            }
            if (redAtRest)
            {
                ColorBlock colors = button.colors;
                colors.normalColor = PrimaryRed;
                colors.highlightedColor = PrimaryRedHover;
                colors.selectedColor = PrimaryRed;
                button.colors = colors;
            }
        }

        /// <summary>
        /// End panel emphasis: one centred row of panel buttons at <see cref="PanelButtonY"/>, left to right,
        /// <see cref="PanelButtonGap"/> apart; the first is the primary action (<see cref="PanelPrimaryWidth"/> x
        /// <see cref="PanelPrimaryHeight"/>), the others secondary (<see cref="PanelButtonWidth"/> x <see cref="PanelButtonHeight"/>).
        /// </summary>
        private static void PlaceRow(Button primary, params Button[] secondary)
        {
            var row = new Button[secondary.Length + 1];
            row[0] = primary;
            secondary.CopyTo(row, 1);
            PlaceButtons(primary, row);
        }

        /// <summary>
        /// One centred row of panel buttons, <paramref name="row"/> left to right, <see cref="PanelButtonGap"/> apart:
        /// <paramref name="primary"/> (anywhere in the row, or null for none) at the primary size, the others at the
        /// secondary size. The same sizes, gap and height on every end panel.
        /// </summary>
        private static void PlaceButtons(Button primary, params Button[] row)
        {
            float total = -PanelButtonGap;
            foreach (Button button in row)
            {
                total += (button == primary ? PanelPrimaryWidth : PanelButtonWidth) + PanelButtonGap;
            }
            float x = -total * 0.5f;
            foreach (Button button in row)
            {
                bool isPrimary = button == primary;
                float width = isPrimary ? PanelPrimaryWidth : PanelButtonWidth;
                float height = isPrimary ? PanelPrimaryHeight : PanelButtonHeight;
                Place((RectTransform)button.transform, new Vector2(0.5f, 0.5f), new Vector2(x + width * 0.5f, PanelButtonY),
                    new Vector2(width, height));
                x += width + PanelButtonGap;
            }
        }

        /// <summary>
        /// Creak gauge (PRD 4.6), left of the eye: crack icon, "Grincement", a capsule filling to the right. Its marker is
        /// where the creak warning starts (the last <see cref="Tuning.CreakWarning"/> seconds before the creak).
        /// </summary>
        private void BuildCreakGauge()
        {
            creakGauge = BuildGauge("CreakGauge", new Vector2(1f, 0f), new Vector2(-GaugeOffsetX, GaugeY), UiIconLibrary.Creak, "CreakLabel",
                Strings.HudCreak, GaugeWidth, CreakWood, CreakAmber, CreakHot);
            creakGauge.TintIcon = UiIconLibrary.HasCreak;
            creakCanvas = creakGauge.Canvas;
            creakRect = creakGauge.Root;
            SetGaugeThreshold(creakGauge, 1f - Tuning.CreakWarning / Tuning.CreakFillTime, 0f);
            SetCreak(0f, false);
        }

        /// <summary>
        /// M5 wave 5B (CONTRACT_M5 6, 16.5): the balance gauge, left of the creak gauge in the bottom band: a vase on a plank,
        /// hud.balance, a bar of |dv| over the fall threshold. Hidden until <see cref="SetBalance"/> shows it (a load).
        /// </summary>
        private void BuildBalanceGauge()
        {
            balanceGauge = BuildGauge("BalanceGauge", new Vector2(1f, 0f), new Vector2(-BalanceOffsetX, GaugeY), ProceduralArt.Balance,
                "BalanceLabel", Strings.HudBalance, BalanceWidth, BalanceCalm, BalanceCalm, CreakHot);
            // Two colours only, calm or red (BalanceRed), as Step 44e reads them; the marker is the red threshold.
            balanceGauge.TwoTone = true;
            balanceCanvas = balanceGauge.Canvas;
            balanceRect = balanceGauge.Root;
            SetGaugeThreshold(balanceGauge, Tuning.BalanceWarning, 0f);
            balanceOn = false;
            SetBalance(0f, false);
            SetEnabled(balanceCanvas, false);
        }

        /// <summary>
        /// Suspicion bar (PRD 4.4), right of the eye: magnifier icon, "Soupçon", the highest suspicion. Its ticks count the
        /// discoveries left down from the loss at 1 (<see cref="SuspicionStep"/> apart), its marker is the last of them:
        /// past it, one more discovery loses the level.
        /// </summary>
        private void BuildSuspicionGauge()
        {
            suspicionGauge = BuildGauge("SuspicionGauge", new Vector2(0f, 0f), new Vector2(GaugeOffsetX, GaugeY), UiIconLibrary.Suspicion,
                "SuspicionLabel", Strings.HudSuspicion, GaugeWidth, SuspicionLow, SuspicionMid, SuspicionHigh);
            suspicionGauge.TintIcon = UiIconLibrary.HasSuspicion;
            suspicionCanvas = suspicionGauge.Canvas;
            suspicionRect = suspicionGauge.Root;
            SetGaugeThreshold(suspicionGauge, 1f - Tuning.SuspicionPerDiscovery, Tuning.SuspicionPerDiscovery);
            SetSuspicion(0f);
        }

        /// <summary>
        /// The suspicion one discovery adds at the current difficulty (a default tempered inhabitant): the gauge's ticks
        /// stand this far apart down from <see cref="Tuning.SuspicionLose"/>.
        /// </summary>
        private float SuspicionStep => Tuning.SuspicionPerDiscovery * (Game != null && Game.Difficulty != null ? Game.Difficulty.SuspicionFactor : 1f);

        /// <summary>
        /// M4: the contextual hints of the current body, each in its own Canvas, on the controls line: the careful hint
        /// in the bottom left corner, the lamp hint in the bottom right one (the controls text is centered, so the
        /// corners are free). The sat-on line sits just above the eye band, centered. Each label always carries its
        /// text (the built player check refuses an empty label); only its Canvas is switched.
        /// </summary>
        private void BuildBodyHints()
        {
            carefulCanvas = BuildHint("CarefulHint", ProceduralArt.Slow, Strings.HudCareful, new Vector2(0f, 0f), new Vector2(36f, ControlsY - 6f));
            lampCanvas = BuildHint("LampHint", ProceduralArt.Bulb, Strings.HudLamp, new Vector2(1f, 0f), new Vector2(-36f, ControlsY - 6f));

            satOnCanvas = BuildLine("SatOn", ProceduralArt.SatOn, Strings.HudSatOn, 760f);
            // CONTRACT_M5 20: the same row; the dog's hold with the dog eye as its icon.
            dogHoldCanvas = BuildLine("DogHold", ProceduralArt.EyeDog, Strings.HudDogHold, 1180f);
            // M4.1 (CONTRACT_M4 10.3): the same row; a stool lying on its side is never sat on.
            tippedCanvas = BuildLine("Tipped", ProceduralArt.Tipped, Strings.HudTipped, 1180f);
            // M5 (CONTRACT_M5_v3 15.2): the same row again; a pinned or lying furniture opens no door, so they never meet.
            doorCanvas = BuildLine("DoorHint", ProceduralArt.Door, Strings.HudDoor, 780f); // DOORAUTO: wide enough for the push sentence (no key any more)
            // Levels v2 (C3b): the same row; a leaf only the household opens ("Locked", in place of the door hint), and a
            // switched-off floor lamp standing in a lit zone (the dark gives it no cover there).
            lockedCanvas = BuildLine("DoorLockedHint", ProceduralArt.Door, Strings.HudDoorLocked, 520f);
            litCanvas = BuildLine("LitHint", ProceduralArt.Bulb, Strings.HudLit, 1120f);
        }

        /// <summary>
        /// Levels v2 (C3b): the start line of the held intro card (hud.start, label StartLine), on a plate in the sat-on row,
        /// inside the card so it fades with it. Shown only while the level waits for its first input.
        /// </summary>
        private void BuildStartLine(Transform card)
        {
            startPlate = NewImage(card, "StartPlate", ProceduralArt.Rounded, SatOnPlate);
            startPlate.type = Image.Type.Sliced;
            Place(startPlate.rectTransform, new Vector2(0.5f, 0f), new Vector2(0f, SatOnY), new Vector2(StartLineWidth, 76f));
            startLine = NewText(startPlate.transform, "StartLine", Strings.HudStart, 40, TextAnchor.MiddleCenter, StartInk);
            Stretch(startLine.rectTransform);
            startPlate.enabled = false;
            startLine.enabled = false;
        }

        /// <summary>
        /// Levels v2 (C3b, code_features "Exit and goal markers over walls"): a screen space marker for the exit zone, in its
        /// own Canvas: a dark disc with the amber door icon, an arrow at its rim (shown while the marker is clamped to the screen
        /// edge, pointing at the exit) and the open-eye glyph (shown while a human sees the furniture standing on the exit).
        /// </summary>
        private void BuildExitMarker()
        {
            var go = new GameObject("ExitMarker", typeof(RectTransform));
            go.transform.SetParent(transform, false);
            markerRect = (RectTransform)go.transform;
            markerRect.anchorMin = markerRect.anchorMax = Vector2.zero;
            markerRect.pivot = new Vector2(0.5f, 0.5f);
            markerRect.sizeDelta = new Vector2(MarkerSize, MarkerSize);
            markerCanvas = go.AddComponent<Canvas>();
            markerGroup = go.AddComponent<CanvasGroup>();
            markerGroup.interactable = false;
            markerGroup.blocksRaycasts = false;
            markerPlate = NewImage(go.transform, "ExitMarkerPlate", ProceduralArt.Disc, MarkerPlateColour);
            Stretch(markerPlate.rectTransform);
            markerDoor = NewImage(go.transform, "ExitMarkerDoor", ProceduralArt.Door, MarkerAmber);
            Place(markerDoor.rectTransform, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(MarkerSize * 0.72f, MarkerSize * 0.72f));
            markerEye = NewImage(go.transform, "ExitMarkerEye", ProceduralArt.EyeOpen, Color.white);
            Place(markerEye.rectTransform, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(MarkerSize * 0.86f, MarkerSize * 0.5f));
            // The arrow turns around the marker's centre: a pivot child carries the rotation, the chevron sits at its rim.
            var pivotGo = new GameObject("ExitMarkerArrowPivot", typeof(RectTransform));
            pivotGo.transform.SetParent(go.transform, false);
            var pivot = (RectTransform)pivotGo.transform;
            Place(pivot, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            markerArrow = NewImage(pivot, "ExitMarkerArrow", ProceduralArt.Chevron, MarkerAmber);
            Place(markerArrow.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, MarkerSize * 0.5f + 16f), new Vector2(38f, 38f));
            markerEye.enabled = false;
            markerArrow.enabled = false;
            markerCanvas.enabled = false;
        }

        /// <summary>
        /// M5 (CONTRACT_M5 3, 16.10): the people block of the intro card, in its own Canvas inside the card, so it fades with
        /// the card: a dark plate, the "Ici : ..." line, then the person lines in one or two columns (labels PeopleList and
        /// PeopleList2). Wave 5A.1 (critique m13): it hangs from the top edge, centred, above the card's text, never over
        /// the middle of the view where the player's furniture stands (<see cref="LayoutPeople"/>). Every label always carries
        /// text (the built player check); only the Canvas and the column labels are switched.
        /// </summary>
        private void BuildPeople(Transform card)
        {
            var go = new GameObject("People", typeof(RectTransform));
            go.transform.SetParent(card, false);
            var rect = (RectTransform)go.transform;
            rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 1f);
            rect.pivot = new Vector2(0.5f, 1f);
            rect.anchoredPosition = new Vector2(0f, -PeopleTop);
            rect.sizeDelta = new Vector2(1500f, PeopleHereHeight + PeoplePadding * 2f);
            peopleCanvas = go.AddComponent<Canvas>();
            Image plate = NewImage(go.transform, "PeoplePlate", ProceduralArt.Rounded, PeoplePlate);
            plate.type = Image.Type.Sliced;
            Stretch(plate.rectTransform);
            peoplePlate = rect;
            string none = string.Format(Strings.IntroHere, Strings.SelectNone);
            peopleHere = NewText(go.transform, "PeopleHere", none, PeopleHereSize, TextAnchor.MiddleCenter, new Color(1f, 0.92f, 0.75f, 1f));
            peopleList = NewPeopleColumn(go.transform, "PeopleList", none);
            peopleList2 = NewPeopleColumn(go.transform, "PeopleList2", none);
            peopleList2.enabled = false;
            peopleCanvas.enabled = false;
        }

        private Text NewPeopleColumn(Transform parent, string name, string value)
        {
            Text column = NewText(parent, name, value, PeopleLineSize, TextAnchor.UpperLeft, new Color(1f, 1f, 1f, 0.95f));
            column.supportRichText = true;
            return column;
        }

        /// <summary>
        /// Sizes and places the people block for its current text (wave 5A.1, critique m13): centred on the top edge, as wide
        /// as its widest line and as tall as its rows, shrunk step by step (down to <see cref="PeopleMinSize"/> pixels) until
        /// it fits the screen's width and the band above the card's game title row. Canvas units, so it holds at any aspect.
        /// </summary>
        private void LayoutPeople()
        {
            if (peoplePlate == null || peopleHere == null)
            {
                return;
            }
            Rect screen = ((RectTransform)transform).rect;
            float screenWidth = screen.width > 1f ? screen.width : 1920f;
            float screenHeight = screen.height > 1f ? screen.height : 1080f;
            peopleLaidFor = new Vector2(screen.width, screen.height);
            float maxWidth = screenWidth - 2f * PeopleMargin;
            float maxHeight = Mathf.Max(PeopleHereHeight, screenHeight * 0.5f - CardTextTop - PeopleTop - PeopleGap);
            int left = PeopleLeftCount;
            int right = Mathf.Max(0, peopleShown.Count - 1 - left);
            int rows = Mathf.Max(left, right);
            for (float scale = 1f; ; scale -= 0.05f)
            {
                peopleHere.fontSize = Mathf.Max(PeopleMinSize, Mathf.RoundToInt(PeopleHereSize * scale));
                int lineSize = Mathf.Max(PeopleMinSize, Mathf.RoundToInt(PeopleLineSize * scale));
                peopleList.fontSize = lineSize;
                peopleList2.fontSize = lineSize;
                float pad = PeoplePadding * scale;
                float hereHeight = PeopleHereHeight * scale;
                float lineHeight = PeopleLineHeight * scale;
                // Each person line advances by lineHeight (the font's own line is about 1.15 em).
                float spacing = lineHeight / (1.15f * lineSize);
                peopleList.lineSpacing = spacing;
                peopleList2.lineSpacing = spacing;
                float leftWidth = left > 0 ? peopleList.preferredWidth : 0f;
                float rightWidth = right > 0 ? peopleList2.preferredWidth : 0f;
                float gutter = right > 0 ? PeopleGutter * scale : 0f;
                float listWidth = leftWidth + gutter + rightWidth;
                float width = Mathf.Max(peopleHere.preferredWidth, listWidth) + 2f * pad;
                float height = 2f * pad + hereHeight + rows * lineHeight;
                bool smallest = peopleHere.fontSize == PeopleMinSize && lineSize == PeopleMinSize;
                if ((width <= maxWidth && height <= maxHeight) || smallest || scale < 0.1f)
                {
                    peoplePlate.sizeDelta = new Vector2(width, height);
                    Place(peopleHere.rectTransform, new Vector2(0.5f, 1f), new Vector2(0f, -pad), new Vector2(width - 2f * pad, hereHeight));
                    float x = pad + (width - 2f * pad - listWidth) * 0.5f;
                    float columnHeight = Mathf.Max(rows, 1) * lineHeight;
                    Place(peopleList.rectTransform, new Vector2(0f, 1f), new Vector2(x, -pad - hereHeight),
                        new Vector2(Mathf.Max(leftWidth, 1f), columnHeight));
                    Place(peopleList2.rectTransform, new Vector2(0f, 1f), new Vector2(x + leftWidth + gutter, -pad - hereHeight),
                        new Vector2(Mathf.Max(rightWidth, 1f), columnHeight));
                    return;
                }
            }
        }

        /// <summary>The person lines in the left column: all of them up to two people, else the first half (rounded up).</summary>
        private int PeopleLeftCount
        {
            get
            {
                int persons = Mathf.Max(0, peopleShown.Count - 1);
                return persons > 2 ? (persons + 1) / 2 : persons;
            }
        }

        /// <summary>A line on a dark plate above the eye band: an icon and a sentence, in its own Canvas.</summary>
        private Canvas BuildLine(string name, Sprite icon, string sentence, float width)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(transform, false);
            Place((RectTransform)go.transform, new Vector2(0.5f, 0f), new Vector2(0f, SatOnY), new Vector2(width, 76f));
            Canvas canvas = go.AddComponent<Canvas>();
            Image plate = NewImage(go.transform, name + "Plate", ProceduralArt.Rounded, SatOnPlate);
            plate.type = Image.Type.Sliced;
            Stretch(plate.rectTransform);
            Image image = NewImage(go.transform, name + "Icon", icon, Color.white);
            Place(image.rectTransform, new Vector2(0f, 0.5f), new Vector2(14f, 0f), new Vector2(62f, 62f));
            Text text = NewText(go.transform, name + "Line", sentence, 38, TextAnchor.MiddleCenter, SatOnInk);
            Place(text.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(30f, 0f), new Vector2(width - 80f, 70f));
            canvas.enabled = false;
            return canvas;
        }

        /// <summary>A hint on the controls line: an icon and a short label, anchored at a bottom corner.</summary>
        private Canvas BuildHint(string name, Sprite icon, string label, Vector2 corner, Vector2 offset)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(transform, false);
            Place((RectTransform)go.transform, corner, offset, new Vector2(440f, 56f));
            Canvas canvas = go.AddComponent<Canvas>();
            bool left = corner.x < 0.5f;
            Image image = NewImage(go.transform, name + "Icon", icon, Color.white);
            Place(image.rectTransform, new Vector2(left ? 0f : 1f, 0.5f), Vector2.zero, new Vector2(48f, 48f));
            Text text = NewText(go.transform, name + "Label", label, 30, left ? TextAnchor.MiddleLeft : TextAnchor.MiddleRight,
                new Color(1f, 1f, 1f, 0.92f));
            Place(text.rectTransform, new Vector2(left ? 0f : 1f, 0.5f), new Vector2(left ? 58f : -58f, 0f), new Vector2(380f, 50f));
            canvas.enabled = false;
            return canvas;
        }

        /// <summary>
        /// M4: which hints of the current body show, called by GameState on every fixed step. The careful hint shows
        /// for every body while the Bodies rule is on, the lamp hint for the floor lamp while the Lamp rule is on.
        /// </summary>
        public void SetBodyHints(bool careful, bool lamp)
        {
            if (carefulOn != careful || lampOn != lamp)
            {
                carefulOn = careful;
                lampOn = lamp;
                ApplyCanvases();
            }
        }

        /// <summary>M4: the sat-on line, shown while an inhabitant sits on the player furniture (it is pinned).</summary>
        public void SetSatOn(bool on)
        {
            if (satOn != on)
            {
                satOn = on;
                ApplyCanvases();
            }
        }

        /// <summary>CONTRACT_M5 20: the dog's hold line, shown while the dog pins the player furniture.</summary>
        public void SetDogHold(bool on)
        {
            if (dogHoldOn != on)
            {
                dogHoldOn = on;
                ApplyCanvases();
            }
        }

        /// <summary>M4.1: the tipped line, shown while the stool lies on its side (a move key rights it).</summary>
        public void SetTipped(bool on)
        {
            if (tippedOn != on)
            {
                tippedOn = on;
                ApplyCanvases();
            }
        }

        /// <summary>
        /// M3: the end screen part of the win panel, in its own Canvas: the time, and a "Menu principal" button
        /// (the mouse path back to the title; Enter and gamepad A are read by GameState).
        /// </summary>
        private void BuildEndGroup()
        {
            var go = new GameObject("EndGroup", typeof(RectTransform));
            go.transform.SetParent(winCanvas.transform, false);
            Stretch((RectTransform)go.transform);
            endCanvas = go.AddComponent<Canvas>();
            go.AddComponent<GraphicRaycaster>();
            endTime = NewText(go.transform, "EndTime", string.Format(Strings.WinBody, Strings.FormatSeconds(0f)), 40, TextAnchor.MiddleCenter,
                new Color(1f, 1f, 1f, 0.92f));
            Place(endTime.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, -82f), new Vector2(1600f, 60f));
            // M8 touch redesign: Rejouer beside Menu principal (a phone has no R key either). Menu principal stays the
            // end screen's default-selected button (Enter submits it, docs/CONTRACT_M3.md 6, S2); Rejouer is reachable
            // beside it with the keyboard or a gamepad's D-pad, and both are now at least 140 px tall at 1080p.
            EndReplayButton = MenuButton(go.transform, "EndReplay", Strings.WinReplay, DisplayFont, Labels);
            EndButton = MenuButton(go.transform, "EndMenuButton", Strings.PauseMenu, DisplayFont, Labels);
            // End screen fix (2026-11-20): the end screen has no next level, so Menu principal is its primary action, at the
            // primary size and bold like Next level and Retry; it is red through its default selection (as Retry is), so the
            // D-pad never shows two red buttons. The row keeps Menu on the right end, where it is on every other panel.
            MakePrimary(EndButton, false);
            PlaceButtons(EndButton, EndReplayButton, EndButton);
            ChainLR(EndReplayButton, EndButton);
            endCanvas.enabled = false;
        }

        /// <summary>
        /// A menu button (the end screen and <see cref="Menu"/>): a rounded plate tinted by the button states, dark
        /// at rest, the chair's red when selected or under the mouse, with a white label.
        /// </summary>
        public static Button MenuButton(Transform parent, string name, string label, Font font, Dictionary<string, Text> labels)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var plate = go.AddComponent<Image>();
            plate.sprite = ProceduralArt.Rounded;
            plate.type = Image.Type.Sliced;
            plate.color = Color.white;
            var button = go.AddComponent<Button>();
            button.targetGraphic = plate;
            ColorBlock colors = button.colors;
            colors.normalColor = new Color(0.1f, 0.1f, 0.13f, 0.86f);
            // Under the mouse: lighter, but never the red of the selection, so the two never look alike.
            colors.highlightedColor = new Color(0.3f, 0.29f, 0.33f, 0.94f);
            colors.selectedColor = PrimaryRed;
            colors.pressedColor = new Color(0.5f, 0.08f, 0.08f, 1f);
            colors.disabledColor = new Color(0.2f, 0.2f, 0.2f, 0.5f);
            colors.colorMultiplier = 1f;
            colors.fadeDuration = 0.08f;
            button.colors = colors;
            // Audio overhaul: the selection tick under the mouse and on keyboard or D-pad navigation.
            go.AddComponent<UiHoverSound>();
            var textGo = new GameObject(name + "Label", typeof(RectTransform));
            textGo.transform.SetParent(go.transform, false);
            var text = textGo.AddComponent<Text>();
            text.font = font;
            text.fontSize = 42;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = Color.white;
            text.text = label;
            text.raycastTarget = false;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            var shadow = textGo.AddComponent<Shadow>();
            shadow.effectColor = new Color(0f, 0f, 0f, 0.6f);
            shadow.effectDistance = new Vector2(2f, -2f);
            Stretch(text.rectTransform);
            if (labels != null)
            {
                labels[name + "Label"] = text;
            }
            return button;
        }

        /// <summary>
        /// HUD gauge redesign (2026-11-19): one gauge of the bottom band, built once, then driven by its value
        /// (<see cref="Target"/>, set by GameState) and animated in <see cref="Update"/> with no allocation.
        /// </summary>
        private sealed class Gauge
        {
            public Canvas Canvas;
            public RectTransform Root;
            // Everything drawn hangs under Body, so the pulse and the shake never move Root (BandScreenRect, tests).
            public RectTransform Body;
            public Image Glow;
            public Image Danger;
            public Image Fill;
            public Image Marker;
            public Image[] Ticks;
            public Image Badge;
            public Image Icon;
            public Text Label;
            public Color Calm;
            public Color Warm;
            public Color Hot;
            // Calm or hot only (the balance gauge, red above its warning), never the gradient.
            public bool TwoTone;
            // The icon is a drawn white one (UiIconLibrary): tinted cream, warming toward its level near the limit.
            public bool TintIcon;
            public float Target;
            public float Threshold = -1f;
            public float TickStep = -1f;
            // 1 on a sudden rise, then down to 0: the shake.
            public float Bump;
            // Danger animation (2026-11-20): the bloom, sheen, head flare and sparks past the threshold.
            public GaugeFx Fx;

            /// <summary>The fill's colour at <paramref name="t"/>: calm at 0, warm at the threshold, hot at 1.</summary>
            public Color LevelColour(float t)
            {
                if (t <= Threshold)
                {
                    return Color.Lerp(Calm, Warm, Threshold > 0f ? t / Threshold : 1f);
                }
                return Color.Lerp(Warm, Hot, (t - Threshold) / Mathf.Max(1e-3f, 1f - Threshold));
            }
        }

        /// <summary>
        /// HUD gauge redesign (2026-11-19): a gauge in its own Canvas, <paramref name="width"/> x <see cref="GaugeHeight"/>
        /// reference pixels, <paramref name="pivot"/> placing it beside the eye. A dark translucent capsule with a cream rim
        /// (readable over any floor) holds a recessed track; the icon sits on a round badge over the capsule's left end and
        /// the label (the menus' display face, in cream) above, right of the badge. In the track, bottom to top: the recess,
        /// the striped danger zone past the threshold, the fill (a pill Filled from the left, tinted by its level), the
        /// ticks, the inner shadow, the threshold marker. A soft glow behind the capsule fades in near the limit.
        /// </summary>
        private Gauge BuildGauge(string name, Vector2 pivot, Vector2 offset, Sprite icon, string labelName, string label, float width,
            Color calm, Color warm, Color hot)
        {
            var g = new Gauge { Calm = calm, Warm = warm, Hot = hot };
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(transform, false);
            g.Root = (RectTransform)go.transform;
            g.Root.anchorMin = g.Root.anchorMax = new Vector2(0.5f, 0f);
            g.Root.pivot = pivot;
            g.Root.anchoredPosition = offset;
            g.Root.sizeDelta = new Vector2(width, GaugeHeight);
            g.Canvas = go.AddComponent<Canvas>();

            var bodyGo = new GameObject(name + "Body", typeof(RectTransform));
            bodyGo.transform.SetParent(go.transform, false);
            g.Body = (RectTransform)bodyGo.transform;
            Stretch(g.Body);
            // The pulse scales about the capsule's centre (a stretched rect with no offsets stays put when its pivot moves).
            g.Body.pivot = new Vector2((CapsuleX + width) * 0.5f / width, (CapsuleY + CapsuleHeight * 0.5f) / GaugeHeight);

            float capsuleWidth = width - CapsuleX;
            g.Glow = NewImage(g.Body, name + "Glow", GaugeArt.Glow, Color.clear);
            g.Glow.type = Image.Type.Sliced;
            g.Glow.pixelsPerUnitMultiplier = GaugeArt.GlowMultiplier(CapsuleHeight, GlowHalo);
            Place(g.Glow.rectTransform, Vector2.zero, new Vector2(CapsuleX - GlowHalo, CapsuleY - GlowHalo),
                new Vector2(capsuleWidth + 2f * GlowHalo, CapsuleHeight + 2f * GlowHalo));

            Image plate = NewImage(g.Body, name + "Plate", GaugeArt.Plate, Color.white);
            plate.type = Image.Type.Sliced;
            plate.pixelsPerUnitMultiplier = GaugeArt.PillMultiplier(CapsuleHeight);
            Place(plate.rectTransform, Vector2.zero, new Vector2(CapsuleX, CapsuleY), new Vector2(capsuleWidth, CapsuleHeight));

            float trackWidth = width - TrackInset - TrackLeft;
            float trackHeight = CapsuleHeight - 2f * TrackInset;
            var trackGo = new GameObject(name + "Track", typeof(RectTransform));
            trackGo.transform.SetParent(g.Body, false);
            var track = (RectTransform)trackGo.transform;
            Place(track, Vector2.zero, new Vector2(TrackLeft, CapsuleY + TrackInset), new Vector2(trackWidth, trackHeight));

            Image recess = NewImage(track, name + "Recess", GaugeArt.Recess, Color.white);
            recess.type = Image.Type.Sliced;
            recess.pixelsPerUnitMultiplier = GaugeArt.PillMultiplier(trackHeight);
            Stretch(recess.rectTransform);

            g.Danger = NewImage(track, name + "Danger", GaugeArt.Hatch(trackWidth, trackHeight), GaugeDanger);
            g.Danger.type = Image.Type.Filled;
            g.Danger.fillMethod = Image.FillMethod.Horizontal;
            g.Danger.fillOrigin = (int)Image.OriginHorizontal.Right;
            g.Danger.fillAmount = 0f;
            Stretch(g.Danger.rectTransform);

            g.Fill = NewImage(track, name + "Fill", GaugeArt.Bar(trackWidth, trackHeight), calm);
            g.Fill.type = Image.Type.Filled;
            g.Fill.fillMethod = Image.FillMethod.Horizontal;
            g.Fill.fillOrigin = (int)Image.OriginHorizontal.Left;
            g.Fill.fillAmount = 0f;
            Stretch(g.Fill.rectTransform);

            g.Ticks = new Image[GaugeTicks];
            for (int i = 0; i < GaugeTicks; i++)
            {
                g.Ticks[i] = NewImage(track, name + "Tick" + i, null, GaugeTick);
                g.Ticks[i].rectTransform.sizeDelta = new Vector2(2f, trackHeight - 8f);
                g.Ticks[i].enabled = false;
            }

            Image shade = NewImage(track, name + "Shade", GaugeArt.Shade, Color.white);
            shade.type = Image.Type.Sliced;
            shade.pixelsPerUnitMultiplier = GaugeArt.PillMultiplier(trackHeight);
            Stretch(shade.rectTransform);

            g.Marker = NewImage(track, name + "Marker", null, GaugeMarker);
            g.Marker.rectTransform.sizeDelta = new Vector2(4f, trackHeight + 10f);
            var markerShadow = g.Marker.gameObject.AddComponent<Shadow>();
            markerShadow.effectColor = new Color(0f, 0f, 0f, 0.55f);
            markerShadow.effectDistance = new Vector2(1.5f, -1.5f);

            g.Badge = NewImage(g.Body, name + "Badge", GaugeArt.Badge, Color.white);
            Place(g.Badge.rectTransform, Vector2.zero, new Vector2(0f, CapsuleY + CapsuleHeight * 0.5f - BadgeSize * 0.5f),
                new Vector2(BadgeSize, BadgeSize));
            g.Icon = NewImage(g.Badge.transform, name + "Icon", icon, Color.white);
            g.Icon.preserveAspect = true;
            Place(g.Icon.rectTransform, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(BadgeSize * 0.62f, BadgeSize * 0.62f));

            float labelY = CapsuleY + CapsuleHeight + 2f;
            g.Label = NewText(g.Body, labelName, label, GaugeLabelSize, TextAnchor.LowerLeft, GaugeInk);
            g.Label.font = DisplayFont;
            Place(g.Label.rectTransform, Vector2.zero, new Vector2(GaugeLabelX, labelY), new Vector2(width - GaugeLabelX, GaugeHeight - labelY));

            // Danger animation (2026-11-20): built last, so its sparks draw over the whole gauge.
            g.Fx = new GaugeFx(g.Body, plate, track, g.Fill, new Vector2(CapsuleX, CapsuleY), new Vector2(capsuleWidth, CapsuleHeight),
                new Vector2(TrackLeft, CapsuleY + TrackInset), new Vector2(trackWidth, trackHeight), (uint)name.Length * 2654435761u);
            return g;
        }

        /// <summary>
        /// Moves a gauge's threshold marker (and its danger zone) to <paramref name="threshold"/> along the track, and its
        /// ticks to every <paramref name="tickStep"/> below the marker (none with 0). Nothing changes when both are already there.
        /// </summary>
        private static void SetGaugeThreshold(Gauge g, float threshold, float tickStep)
        {
            threshold = Mathf.Clamp(threshold, 0.05f, 1f);
            if (g == null || (Mathf.Abs(g.Threshold - threshold) < 1e-4f && Mathf.Abs(g.TickStep - tickStep) < 1e-4f))
            {
                return;
            }
            g.Threshold = threshold;
            g.TickStep = tickStep;
            g.Danger.fillAmount = 1f - threshold;
            AlongTrack(g.Marker.rectTransform, threshold);
            for (int i = 0; i < g.Ticks.Length; i++)
            {
                float at = threshold - (i + 1) * tickStep;
                bool on = tickStep > 0.02f && at > 0.06f;
                g.Ticks[i].enabled = on;
                if (on)
                {
                    AlongTrack(g.Ticks[i].rectTransform, at);
                }
            }
        }

        /// <summary>Centres <paramref name="rect"/> on the track at <paramref name="t"/> (0 to 1, left to right), vertically centred.</summary>
        private static void AlongTrack(RectTransform rect, float t)
        {
            rect.anchorMin = rect.anchorMax = new Vector2(t, 0.5f);
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = Vector2.zero;
        }

        /// <summary>A new value for a gauge: a rise over <see cref="GaugeBumpRise"/> in one update, or <paramref name="burst"/>, shakes it.</summary>
        private static void SetGaugeTarget(Gauge g, float value, bool burst)
        {
            if (g == null)
            {
                return;
            }
            if (!g.TwoTone && (burst || value - g.Target > GaugeBumpRise))
            {
                g.Bump = 1f;
            }
            if (burst && g.Fx != null)
            {
                // The creak itself: the full gauge bursts where its fill stood as it empties.
                g.Fx.Explode(g.Fill.fillAmount);
            }
            g.Target = value;
        }

        /// <summary>
        /// HUD gauge redesign: every gauge draws its value at once, with no easing and no shake (a new level, and the shots).
        /// </summary>
        public void SnapGauges()
        {
            SnapGauge(creakGauge);
            SnapGauge(suspicionGauge);
            SnapGauge(balanceGauge);
        }

        private static void SnapGauge(Gauge g)
        {
            if (g != null)
            {
                g.Fill.fillAmount = g.Target;
                g.Bump = 0f;
            }
        }

        /// <summary>
        /// One frame of a gauge (no allocation): the drawn fill eases toward the value and its colour follows its level
        /// (never flashing). Near the limit the glow fades in and the badge's ring warms; past the threshold (or with
        /// <paramref name="flash"/>, the creak warning, or <paramref name="red"/> on a two tone gauge) the danger animation
        /// (GaugeFx: bloom, laser sheen, hot spot, sparks on crossing) takes over and the glow breathes with it; a sudden
        /// rise shakes the gauge.
        /// </summary>
        private static void AnimateGauge(Gauge g, float dt, float time, bool flash, bool red)
        {
            if (g == null)
            {
                return;
            }
            float drawn = g.Fill.fillAmount;
            drawn = Mathf.Abs(g.Target - drawn) < 1e-3f ? g.Target : drawn + (g.Target - drawn) * (1f - Mathf.Exp(-GaugeLerpRate * dt));
            g.Fill.fillAmount = drawn;
            Color level = g.TwoTone ? (red ? g.Hot : g.Calm) : g.LevelColour(drawn);
            float near = g.TwoTone ? (red ? 1f : 0f) : Mathf.InverseLerp(g.Threshold - 0.1f, 1f, drawn);
            bool danger = g.TwoTone ? red : flash || drawn >= g.Threshold - 1e-4f;
            float heat = g.Fx.Animate(dt, time, drawn, danger, level);
            float breath = g.Fx.Breath;
            Color hotLevel = Color.Lerp(level, g.Hot, 0.5f * heat);
            g.Fill.color = level;
            Color glow = hotLevel;
            glow.a = 0.3f * near * (1f - heat) + heat * (0.35f + 0.35f * breath);
            g.Glow.color = glow;
            float warmth = Mathf.Max(near, heat);
            g.Badge.color = Color.Lerp(Color.white, hotLevel, warmth * 0.85f);
            if (g.TintIcon)
            {
                g.Icon.color = Color.Lerp(GaugeInk, hotLevel, 0.25f + 0.6f * warmth);
            }
            float grow = 1f + 0.012f * heat * breath;
            g.Body.localScale = new Vector3(grow, grow, 1f);
            g.Bump = Mathf.MoveTowards(g.Bump, 0f, dt * 2.2f);
            g.Body.anchoredPosition = new Vector2(g.Bump * g.Bump * 6f * Mathf.Sin(time * 63f), 0f);
        }

        /// <summary>Shows or hides each M2 gauge (hidden when its rule is off, as in the M1 probe).</summary>
        public void SetGauges(bool creak, bool suspicion)
        {
            if (creakOn != creak || suspicionOn != suspicion)
            {
                creakOn = creak;
                suspicionOn = suspicion;
                ApplyCanvases();
            }
        }

        /// <summary>
        /// M3: hides or shows the whole HUD. An open menu hides it by disabling its Canvas and every nested Canvas
        /// (PRD 8.4: never the GameObject); what each one should show is kept and comes back with the HUD.
        /// </summary>
        public void SetVisible(bool visible)
        {
            Visible = visible;
            ApplyCanvases();
        }

        /// <summary>Enables each Canvas from its own state and the HUD visibility.</summary>
        private void ApplyCanvases()
        {
            SetEnabled(rootCanvas, Visible);
            // End panel emphasis (2026-11-19): the play band (eye, gauges, controls line, body hints) hides under the fail
            // and win panels. Drawn under their translucent dim, on a 20:9 phone its labels showed between the panel
            // buttons and the controls line ran through the record line.
            bool band = !failOn && !winOn;
            if (eyeBackdrop != null)
            {
                eyeBackdrop.enabled = band;
            }
            if (eye != null)
            {
                eye.enabled = band;
            }
            if (eyeBlink != null)
            {
                eyeBlink.enabled = band;
            }
            if (controls != null)
            {
                controls.enabled = band;
            }
            SetEnabled(creakCanvas, Visible && creakOn && band);
            SetEnabled(suspicionCanvas, Visible && suspicionOn && band);
            SetEnabled(failCanvas, Visible && failOn);
            SetEnabled(winCanvas, Visible && winOn);
            // One row of buttons at a time on the win panel: Next level/Replay/Menu on a plain win, the EndGroup's own
            // Replay/Menu principal on the end screen (never both: they share the row's place).
            SetEnabled(winNextCanvas, Visible && winOn && winNextOn && !endOn);
            SetEnabled(winButtonsCanvas, Visible && winOn && !endOn);
            SetEnabled(endCanvas, Visible && winOn && endOn);
            SetEnabled(carefulCanvas, Visible && carefulOn && band);
            SetEnabled(lampCanvas, Visible && lampOn && band);
            SetEnabled(satOnCanvas, Visible && satOn && !failOn && !winOn);
            SetEnabled(dogHoldCanvas, Visible && dogHoldOn && !satOn && !failOn && !winOn);
            SetEnabled(tippedCanvas, Visible && tippedOn && !satOn && !dogHoldOn && !failOn && !winOn);
            SetEnabled(doorCanvas, Visible && doorOn && !satOn && !dogHoldOn && !tippedOn && !failOn && !winOn);
            // Levels v2 (C3b): the locked hint never with the door hint (GameState wants it only with no openable leaf in
            // reach); the lit hint last on the row, under every other line of it (the wardrobe prompt included).
            SetEnabled(lockedCanvas, Visible && lockedOn && !doorOn && !satOn && !dogHoldOn && !tippedOn && !failOn && !winOn);
            SetEnabled(litCanvas, Visible && litOn && !lockedOn && !doorOn && !satOn && !dogHoldOn && !tippedOn && !HideHintVisible
                && !failOn && !winOn);
            SetEnabled(markerCanvas, Visible && markerWanted && !failOn && !winOn);
            SetEnabled(peopleCanvas, Visible && peopleOn);
            SetEnabled(balanceCanvas, Visible && balanceOn && band);
        }

        private static void SetEnabled(Canvas canvas, bool enabled)
        {
            if (canvas != null && canvas.enabled != enabled)
            {
                canvas.enabled = enabled;
            }
        }

        /// <summary>Called by GameState on every fixed step with the creak gauge and its warning.</summary>
        public void SetCreak(float value, bool warning)
        {
            CreakShown = Mathf.Clamp01(value);
            CreakFlashing = warning;
            if (creakGauge != null)
            {
                // The marker is where the warning starts, at the difficulty's fill time; the creak itself (full, then
                // back to empty) shakes the gauge.
                SetGaugeThreshold(creakGauge, Game != null ? Game.Creak.WarningStart : 1f - Tuning.CreakWarning / Tuning.CreakFillTime, 0f);
                SetGaugeTarget(creakGauge, CreakShown, creakGauge.Target > 0.9f && CreakShown < 0.1f);
            }
        }

        /// <summary>Called by GameState on every fixed step with the highest suspicion.</summary>
        public void SetSuspicion(float value)
        {
            SuspicionShown = Mathf.Clamp01(value);
            if (suspicionGauge != null)
            {
                float step = SuspicionStep;
                SetGaugeThreshold(suspicionGauge, Tuning.SuspicionLose - step, step);
                SetGaugeTarget(suspicionGauge, SuspicionShown, false);
            }
        }

        /// <summary>M1 form: seen and still is calm, seen and moving is alarm.</summary>
        public void SetSeen(bool seen, float seenMovingTime)
        {
            SetEye(!seen ? HudEye.Closed : seenMovingTime > 0f ? HudEye.Alarm : HudEye.Calm, seenMovingTime);
        }

        /// <summary>
        /// Called by GameState at the end of every fixed step, so the eye flips on the step of the test.
        /// M2.1: closed when unseen; open and calm when seen and harmless; open with alert strokes on a red
        /// backdrop when seen and moving, or seen out of place (Suspect). The three differ by shape.
        /// M5: the dog eye (only the dog sees) is the open eye under two dog ears, on a deep orange backdrop.
        /// </summary>
        public void SetEye(HudEye state, float seenMovingTime)
        {
            bool wasOpen = EyeOpen;
            if (state != Eye)
            {
                // Eye redesign (2026-11-20): a change between closed and open blinks through the half open frame; a change
                // between two open eyes only pops. The sprite itself (EyeSprite) is the new state's at once.
                eyeChangeAge = 0f;
                eyeChangeBlinks = wasOpen != (state != HudEye.Closed);
                eyeChangeOpens = state != HudEye.Closed;
            }
            Eye = state;
            EyeOpen = state != HudEye.Closed;
            seenMoving = seenMovingTime;
            if (eye != null)
            {
                eye.sprite = SpriteOf(state);
                eyeBackdrop.color = state == HudEye.Closed ? BackdropClosed
                    : state == HudEye.Calm ? BackdropCalm
                    : state == HudEye.Dog ? BackdropDog
                    : BackdropAlarm;
            }
        }

        /// <summary>The sprite of an eye state: each state has its own shape (closed lid, open eye, alert strokes, dog ears).</summary>
        public static Sprite SpriteOf(HudEye state)
        {
            switch (state)
            {
                case HudEye.Closed:
                    return ProceduralArt.EyeClosed;
                case HudEye.Calm:
                    return ProceduralArt.EyeOpen;
                case HudEye.Dog:
                    return ProceduralArt.EyeDog;
                default:
                    return ProceduralArt.EyeAlarm;
            }
        }

        /// <summary>The sprite the eye shows now (tests).</summary>
        public Sprite EyeSprite => eye != null ? eye.sprite : null;

        // Eye redesign (2026-11-20): the blink's half open frame shows for EyeBlinkHold seconds, then the new eye pops in
        // from EyePop times its size over EyePopTime (an opening eye; a closing one only settles from a slight squash).
        private const float EyeBlinkHold = 0.06f;
        private const float EyePopTime = 0.16f;
        private const float EyePop = 1.14f;

        /// <summary>One frame of the eye's change (no allocation; nothing is written once it has settled).</summary>
        private void AnimateEye(float dt)
        {
            if (eye == null || eyeChangeAge > EyeBlinkHold + EyePopTime + 1f)
            {
                return;
            }
            eyeChangeAge += dt;
            float age = eyeChangeAge;
            bool hold = eyeChangeBlinks && age < EyeBlinkHold;
            float popAge = eyeChangeBlinks ? age - EyeBlinkHold : age;
            float t = Mathf.Clamp01(popAge / EyePopTime);
            // Ease out: fast at first, settling on 1.
            float e = 1f - (1f - t) * (1f - t) * (1f - t);
            float from = eyeChangeOpens ? EyePop : 0.9f;
            float scale = hold ? 1f : Mathf.Lerp(from, 1f, e);
            eye.rectTransform.localScale = new Vector3(scale, eyeChangeOpens ? scale : Mathf.Lerp(0.8f, 1f, e), 1f);
            Color c = eye.color;
            c.a = hold ? 0f : 1f;
            eye.color = c;
            Color b = eyeBlink.color;
            b.a = hold ? 1f : 0f;
            eyeBlink.color = b;
            if (age > EyeBlinkHold + EyePopTime)
            {
                // Settled: the next frames write nothing.
                eye.rectTransform.localScale = Vector3.one;
                eyeChangeAge = 99f;
            }
        }

        // ----- M5 (docs/CONTRACT_M5.md 16.12) -----
        /// <summary>The win panel's transform, where the record line attaches.</summary>
        public RectTransform WinPanel => winCanvas != null ? winCanvas.transform as RectTransform : null;

        // ----- Stars (idea 5, docs/next/progress/STARS.md) -----
        /// <summary>The win panel's star row (tests read its count, images and reveal state); null before Build.</summary>
        public StarRow WinStars => winStars;

        /// <summary>The star row shows on screen: a visible win panel with stars set for the win just recorded.</summary>
        public bool WinStarsVisible => WinVisible && winStars != null && winStars.Images.Count > 0 && winStars.Images[0].enabled;

        /// <summary>"New stars!" shows under the row (this win raised the saved count).</summary>
        public bool WinStarsNewVisible => WinStarsVisible && winStarsNew != null && winStarsNew.enabled;

        /// <summary>
        /// Shows <paramref name="count"/> stars beside the time of the win panel (or beside the end screen's time when
        /// <paramref name="endScreen"/>), popping in one after the other, and "New stars!" under them when
        /// <paramref name="newBest"/>. Called by RecordLine once the win is recorded; ShowWin and HidePanels hide the row.
        /// </summary>
        public void ShowWinStars(int count, bool newBest, bool endScreen)
        {
            if (winStars == null)
            {
                return;
            }
            float y = endScreen ? EndStarsY : WinStarsY;
            winStars.Place(new Vector2(0.5f, 0.5f), new Vector2(WinStarsX, y));
            winStars.Set(count, true);
            if (winStarsNew != null)
            {
                winStarsNew.text = Strings.StarsNewBest;
                winStarsNew.rectTransform.anchoredPosition = new Vector2(WinStarsX, y + WinStarsNewOffset);
                winStarsNew.enabled = newBest;
            }
        }

        private void HideWinStars()
        {
            if (winStars != null)
            {
                winStars.SetVisible(false);
            }
            if (winStarsNew != null)
            {
                winStarsNew.enabled = false;
            }
        }

        /// <summary>
        /// M5 (CONTRACT_M5_v3 15.2): the door hint (hud.door, DOORAUTO: push toward the door), called by GameState on every fixed step: shown while a
        /// closed leaf is in reach of a furniture that could open it. It shares the sat-on row (never both at once).
        /// </summary>
        public void ShowDoorHint(bool visible)
        {
            if (doorOn != visible)
            {
                doorOn = visible;
                ApplyCanvases();
            }
        }

        // ----- M6 gameplay (docs/CONTRACT_M6.md 2.5): the wardrobe prompt, on the sat-on row (built on first use). -----
        private Canvas hideCanvas;

        /// <summary>M6: the wardrobe prompt shows (hud.hide or hud.leave, DOORAUTO: a push; label HideHintLine).</summary>
        public bool HideHintVisible => hideCanvas != null && hideCanvas.enabled;

        /// <summary>
        /// M6, called by GameState on every fixed step: the wardrobe prompt with <paramref name="sentence"/>, while
        /// <paramref name="visible"/> and no panel, sat-on, tipped or door line shows.
        /// </summary>
        public void ShowHideHint(bool visible, string sentence)
        {
            if (visible && hideCanvas == null)
            {
                hideCanvas = BuildLine("HideHint", ProceduralArt.Door, sentence, 780f); // DOORAUTO: wide enough for the push sentence
            }
            if (hideCanvas == null)
            {
                return;
            }
            if (visible && Labels.TryGetValue("HideHintLine", out Text line) && line.text != sentence)
            {
                line.text = sentence;
            }
            SetEnabled(hideCanvas, Visible && visible && !satOn && !tippedOn && !doorOn && !lockedOn && !failOn && !winOn);
            // Levels v2 (C3b): the lit hint gives the row up to the wardrobe prompt.
            SetEnabled(litCanvas, Visible && litOn && !lockedOn && !doorOn && !satOn && !dogHoldOn && !tippedOn && !HideHintVisible
                && !failOn && !winOn);
        }

        /// <summary>
        /// M5 wave 5B (CONTRACT_M5 6, 16.5), called by GameState on every fixed step: the balance gauge shows
        /// <paramref name="ratio"/> (|dv| over the window, divided by the fall threshold; clamped to 0 to 1 on the bar), only
        /// while <paramref name="visible"/> (a load that has not fallen). Its fill turns red above
        /// <see cref="Tuning.BalanceWarning"/>.
        /// </summary>
        public void SetBalance(float ratio, bool visible)
        {
            BalanceShown = Mathf.Clamp01(ratio);
            BalanceRed = visible && ratio > Tuning.BalanceWarning; // MUTATION:BALANCE_RED
            if (balanceGauge != null)
            {
                SetGaugeTarget(balanceGauge, BalanceShown, false);
                balanceGauge.Fill.color = BalanceRed ? CreakHot : BalanceCalm;
            }
            if (balanceOn != visible)
            {
                balanceOn = visible;
                ApplyCanvases();
            }
        }

        /// <summary>
        /// The intro card's people (CONTRACT_M5 3, 16.10): <paramref name="lines"/>[0] is the "Ici : ..." line with the names,
        /// every other line one person (see <see cref="PeopleLines"/>). Null or empty hides the block (levels 1 to 7). It shows
        /// and fades with the level title; <see cref="ShowLevel"/> hides it, so call this after it.
        /// </summary>
        public void ShowPeople(IList<string> lines)
        {
            peopleShown.Clear();
            if (lines != null)
            {
                foreach (string line in lines)
                {
                    if (!string.IsNullOrEmpty(line))
                    {
                        peopleShown.Add(line);
                    }
                }
            }
            peopleOn = peopleShown.Count > 0;
            if (peopleOn && peopleHere != null)
            {
                peopleHere.text = peopleShown[0];
                int persons = peopleShown.Count - 1;
                // Three people or more: two columns, the first half (rounded up) on the left. Each column label always
                // carries text: an empty column keeps the names line, hidden.
                int left = PeopleLeftCount;
                int right = persons - left;
                peopleList.text = left > 0 ? string.Join("\n", peopleShown.GetRange(1, left)) : peopleShown[0];
                peopleList.enabled = left > 0;
                peopleList2.text = right > 0 ? string.Join("\n", peopleShown.GetRange(1 + left, right)) : peopleShown[0];
                peopleList2.enabled = right > 0;
                LayoutPeople();
            }
            ApplyCanvases();
        }

        /// <summary>
        /// M5 (CONTRACT_M5 3, 16.10): the people lines of the intro card for these personalities, in level order: first
        /// intro.here with the names joined by ", ", then one line each, the name (coloured) and its trait. Personalities with
        /// no name key (the default one) are not listed; with nobody listed the result is empty.
        /// </summary>
        public static List<string> PeopleLines(IEnumerable<PersonalityDef> people)
        {
            return PeopleLines(people, null);
        }

        /// <summary>
        /// Levels v2 (C3b, code_features "Intro card: inhabitant names"): the people lines with each inhabitant's data name
        /// (<paramref name="names"/>[i] for the i-th personality, InhabitantDef.Name). The names line lists the data names;
        /// each person line is hud.person ("{0}, {1}": the name, then the personality label, its article in lower case: "Lea,
        /// the Suspicious One", "Rex, the dog"), then the trait. A missing or empty name falls back to the M5 line (the label
        /// alone); a name equal to its label shows once ("Mamie" in French).
        /// </summary>
        public static List<string> PeopleLines(IEnumerable<PersonalityDef> people, IList<string> names)
        {
            var shown = new List<string>();
            var lines = new List<string>();
            if (people != null)
            {
                int index = -1;
                foreach (PersonalityDef p in people)
                {
                    index++;
                    if (p == null || string.IsNullOrEmpty(p.NameKey))
                    {
                        continue;
                    }
                    string label = Strings.Get(p.NameKey);
                    string name = names != null && index < names.Count ? names[index] : null;
                    shown.Add(string.IsNullOrEmpty(name) ? label : name);
                    string trait = string.IsNullOrEmpty(p.TraitKey) ? null : Strings.Get(p.TraitKey);
                    lines.Add(PersonLine(PersonTitle(name, label, p.Id == PersonalityDef.Dog), trait));
                }
            }
            if (shown.Count == 0)
            {
                return lines;
            }
            lines.Insert(0, string.Format(Strings.IntroHere, string.Join(", ", shown)));
            return lines;
        }

        /// <summary>
        /// Levels v2 (C3b): the coloured part of a person line, hud.person with the data name and the personality label. The
        /// label's leading article goes to lower case after the comma ("the Suspicious One", "la méfiante"); the dog's whole
        /// label does ("the dog", "le chien"). No name: the label alone; a name equal to the label: the name alone.
        /// </summary>
        public static string PersonTitle(string name, string label, bool dog)
        {
            if (string.IsNullOrEmpty(name))
            {
                return label;
            }
            if (string.IsNullOrEmpty(label) || string.Equals(name.Trim(), label.Trim(), System.StringComparison.OrdinalIgnoreCase))
            {
                return name;
            }
            return string.Format(Strings.HudPerson, name, LabelAfterName(label, dog));
        }

        private static readonly string[] Articles = { "The ", "Le ", "La ", "Les ", "L'", "L’" };

        private static string LabelAfterName(string label, bool dog)
        {
            if (dog)
            {
                return label.ToLowerInvariant();
            }
            foreach (string article in Articles)
            {
                if (label.StartsWith(article, System.StringComparison.Ordinal))
                {
                    return char.ToLowerInvariant(label[0]) + label.Substring(1);
                }
            }
            return label;
        }

        /// <summary>One person line: the name in a warm colour (rich text), then the trait, both from Strings.</summary>
        public static string PersonLine(string name, string trait)
        {
            string coloured = "<color=" + PersonNameColor + ">" + name + "</color>";
            return string.IsNullOrEmpty(trait) ? coloured : coloured + "    " + trait;
        }

        /// <summary>
        /// The people block for these personalities (<see cref="PeopleLines"/>), remembered so a language change can list them
        /// again in the new language. Levels v2 (C3b): with the data names of the current level's inhabitants, when
        /// <see cref="Game"/>'s level has one inhabitant per personality (GameState lists them in level order).
        /// </summary>
        public void ShowPeopleOf(IEnumerable<PersonalityDef> people)
        {
            peopleDefs = people != null ? new List<PersonalityDef>(people) : null;
            peopleNames = NamesOfLevel(peopleDefs != null ? peopleDefs.Count : 0);
            ShowPeople(PeopleLines(peopleDefs, peopleNames));
        }

        /// <summary>The data names of the current level's inhabitants, in level order; null when they are not <paramref name="count"/>.</summary>
        private List<string> NamesOfLevel(int count)
        {
            if (Game == null || Game.Level == null || Game.Level.Inhabitants == null || Game.Level.Inhabitants.Count != count || count == 0)
            {
                return null;
            }
            var names = new List<string>(count);
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                names.Add(h != null && h.Def != null ? h.Def.Name : null);
            }
            return names;
        }

        // What the intro card and the panels show, kept for Relocalize.
        private LevelDef shownLevel;
        private List<PersonalityDef> peopleDefs;
        private List<string> peopleNames;
        private float shownSeconds;

        /// <summary>
        /// The language changed: the lines built from formatted or composed strings are built again in the new language (the
        /// intro card's level name, hint and people, the controls line, the fail, win and end panels). The plain labels were
        /// already translated in place (Menu.OnLanguageChanged); nothing here changes what shows or the card's fade.
        /// </summary>
        public void Relocalize()
        {
            if (shownLevel != null)
            {
                if (Labels.TryGetValue("LevelName", out Text name))
                {
                    name.text = Strings.Get(shownLevel.NameKey);
                }
                SetHintText();
            }
            if (peopleOn && peopleDefs != null)
            {
                ShowPeople(PeopleLines(peopleDefs, peopleNames));
            }
            SetStartLineText();
            SetLampHintText();
            if (controls != null)
            {
                controls.text = controlsTouch ? Strings.HudControlsTouch : controlsGamepad ? Strings.HudControlsGamepad : Strings.HudControls;
            }
            if (failTitle != null)
            {
                failTitle.text = FailReason == LoseReason.Suspicion ? Strings.FailSuspicionTitle : Strings.FailTitle;
            }
            if (failBody != null)
            {
                failBody.text = FailReason == LoseReason.Suspicion ? Strings.FailSuspicionBody : Strings.FailBody;
            }
            if (failAction != null)
            {
                failAction.text = InputReader.TouchUIActive ? Strings.FailActionTouch : Strings.FailAction;
            }
            if (winTitle != null)
            {
                winTitle.text = endOn ? Strings.EndTitle : Strings.WinTitle;
            }
            if (winBody != null)
            {
                winBody.text = endOn ? Strings.EndBody : string.Format(Strings.WinBody, Strings.FormatSeconds(shownSeconds));
            }
            if (winAction != null)
            {
                winAction.text = InputReader.TouchUIActive ? Strings.WinActionTouch : Strings.WinAction;
            }
            if (winNext != null)
            {
                winNext.text = InputReader.TouchUIActive ? Strings.WinNextTouch : Strings.WinNext;
            }
            if (endTime != null)
            {
                endTime.text = string.Format(Strings.WinBody, Strings.FormatSeconds(shownSeconds));
            }
            if (winStarsNew != null)
            {
                winStarsNew.text = Strings.StarsNewBest;
            }
            Tips?.Relocalize();
        }

        public void ShowLevel(LevelDef level)
        {
            shownLevel = level;
            HidePanels();
            // Onboarding tips: a new level or a restart drops the shown tip.
            Tips?.OnLevelShown();
            if (Labels.TryGetValue("LevelName", out Text name))
            {
                name.text = Strings.Get(level.NameKey);
            }
            SetHintText();
            titleTimer = 0f;
            if (titleCard != null)
            {
                titleCard.alpha = 1f;
            }
            // Levels v2 (C3b): the held card follows GameState.Started from the next frame (Update); a level shown
            // started keeps the M1 timing (4 s, then the 1 s fade). No locked or lit line until GameState wants one.
            cardHeld = false;
            cardWasHeld = false;
            UpdateCardHold();
            // LEVELNUM: the level select's number of this level; a new level and every restart replay the zoom.
            string id = !string.IsNullOrEmpty(level.Id) ? level.Id : Game != null ? Game.LevelId : null;
            SetLevelNumber(Game != null ? LevelSelect.DisplayNumber(Game.LevelOrder, id) : 0);
            lockedOn = false;
            litOn = false;
            markerWanted = false;
            markerClamped = false;
            markerEyeOn = false;
            SetSeen(false, 0f);
            SetCreak(0f, false);
            SetSuspicion(0f);
            SetSatOn(false);
            SetDogHold(false);
            SetTipped(false);
            // M5: a new level lists its own people (ShowPeople, after this) and starts with no door in reach. Wave 5B: and
            // with no balance gauge until GameState shows it (a load).
            peopleShown.Clear();
            peopleOn = false;
            doorOn = false;
            SetBalance(0f, false);
            // A new level's gauges start empty at once, with no easing down from the last level and no shake.
            SnapGauges();
            ApplyCanvases();
        }

        public void ShowFail()
        {
            ShowFail(LoseReason.SeenMoving);
        }

        /// <summary>The fail panel with the strings of the reason: "VU !" when seen moving, "LOUCHE !" for suspicion.</summary>
        public void ShowFail(LoseReason reason)
        {
            bool suspicion = reason == LoseReason.Suspicion;
            if (failTitle != null)
            {
                failTitle.text = suspicion ? Strings.FailSuspicionTitle : Strings.FailTitle;
            }
            if (failBody != null)
            {
                failBody.text = suspicion ? Strings.FailSuspicionBody : Strings.FailBody;
            }
            if (failAction != null)
            {
                // M8 touch redesign: the hint line next to Retry/Menu never names a key a phone does not have.
                failAction.text = InputReader.TouchUIActive ? Strings.FailActionTouch : Strings.FailAction;
            }
            FailReason = reason == LoseReason.None ? LoseReason.SeenMoving : reason;
            failOn = true;
            winOn = false;
            ApplyCanvases();
            HideTitleCard();
        }

        public void ShowWin(float seconds)
        {
            ShowWin(seconds, false);
        }

        /// <summary>The win panel; <paramref name="hasNext"/> adds the win.next line (Enter loads the next level).</summary>
        public void ShowWin(float seconds, bool hasNext)
        {
            if (winTitle != null)
            {
                winTitle.text = Strings.WinTitle;
            }
            shownSeconds = seconds;
            winBody.text = string.Format(Strings.WinBody, Strings.FormatSeconds(seconds));
            if (winAction != null)
            {
                winAction.rectTransform.anchoredPosition = new Vector2(0f, ActionY);
                // M8 touch redesign: the hint line next to Replay/Next level/Menu never names a key a phone lacks.
                winAction.text = InputReader.TouchUIActive ? Strings.WinActionTouch : Strings.WinAction;
            }
            if (winNext != null)
            {
                winNext.text = InputReader.TouchUIActive ? Strings.WinNextTouch : Strings.WinNext;
            }
            winNextOn = hasNext;
            // Stars: the row of the previous win never shows on a new one; RecordLine shows this win's once recorded.
            HideWinStars();
            // With no next level (GameState shows the end screen instead, but ShowWin(seconds) has no next either),
            // Replay and Menu close up into a centred row rather than leave Next level's place empty.
            if (WinReplayButton != null && WinMenuButton != null && WinNextLevelButton != null)
            {
                if (hasNext)
                {
                    PlaceRow(WinNextLevelButton, WinReplayButton, WinMenuButton);
                }
                else
                {
                    PlaceButtons(null, WinReplayButton, WinMenuButton);
                }
            }
            endOn = false;
            winOn = true;
            failOn = false;
            ApplyCanvases();
            FailReason = LoseReason.None;
            HideTitleCard();
        }

        /// <summary>
        /// M3 end screen (docs/CONTRACT_M3.md 6): the win panel after the last level of levels.json shows end.title
        /// and end.body, then the time, "R" to replay and the button back to the title.
        /// </summary>
        public void ShowEnd(float seconds)
        {
            ShowWin(seconds, false);
            if (winTitle != null)
            {
                winTitle.text = Strings.EndTitle;
            }
            winBody.text = Strings.EndBody;
            if (endTime != null)
            {
                endTime.text = string.Format(Strings.WinBody, Strings.FormatSeconds(seconds));
            }
            if (winAction != null)
            {
                winAction.rectTransform.anchoredPosition = new Vector2(0f, EndActionY);
            }
            endOn = true;
            ApplyCanvases();
        }

        /// <summary>Selects the end screen button, so keyboard and gamepad users see where Enter goes.</summary>
        public void SelectEndButton()
        {
            if (EndButton != null && EventSystem.current != null)
            {
                EventSystem.current.SetSelectedGameObject(EndButton.gameObject);
            }
        }

        /// <summary>A panel always wins over the title card: the two texts must never overlap.</summary>
        private void HideTitleCard()
        {
            titleTimer = 100f;
            if (titleCard != null)
            {
                titleCard.alpha = 0f;
            }
            SyncBackdrop();
        }

        public float TitleCardAlpha => titleCard != null ? titleCard.alpha : 0f;

        public void HidePanels()
        {
            failOn = false;
            winOn = false;
            endOn = false;
            HideWinStars();
            ApplyCanvases();
            FailReason = LoseReason.None;
        }

        private void Update()
        {
            if (pulse == null)
            {
                return;
            }
            // HUD gauge redesign: the gauges ease, glow and shake; past its threshold (the creak warning) a gauge shows its
            // danger animation (GaugeFx). The eye plays its blink between closed and open. ShotStep (shots) makes every
            // frame one fixed step of the HUD's own clock.
            float gaugeDt = ShotStep > 0f ? ShotStep : Time.unscaledDeltaTime;
            hudClock += gaugeDt;
            // Stars: the win panel's reveal (nothing once the row settled).
            if (winStars != null)
            {
                winStars.Animate(gaugeDt);
            }
            float gaugeTime = hudClock;
            AnimateGauge(creakGauge, gaugeDt, gaugeTime, CreakFlashing, false);
            AnimateGauge(suspicionGauge, gaugeDt, gaugeTime, false, false);
            AnimateGauge(balanceGauge, gaugeDt, gaugeTime, false, BalanceRed);
            AnimateEye(gaugeDt);
            // PRD 4.3: the screen edge pulses red while seenMoving is above zero.
            float a = seenMoving > 0f ? 0.45f + 0.35f * Mathf.Sin(Time.unscaledTime * 18f) : 0f;
            Color c = pulse.color;
            c.a = Mathf.MoveTowards(c.a, a, Time.unscaledDeltaTime * 8f);
            if (seenMoving > 0f)
            {
                c.a = a;
            }
            pulse.color = c;
            if (pulsePattern != null)
            {
                // CONTRACT_M6 2.3: the pattern matches the pulse exactly, and only while seen moving.
                Color pc = pulsePattern.color;
                pc.a = seenMoving > 0f ? a : 0f; // MUTATION:PULSE_PATTERN_GATE
                pulsePattern.color = pc;
            }

            // M6 (CONTRACT_M6 2.2): the controls line's device names (InputReader has no other per frame poll point).
            InputReader.PollLastDevice();
            bool gamepad = InputReader.LastInputWasGamepad;
            // M7 (CONTRACT_M7 1.5): the touch names while the touch controls show.
            bool touch = InputReader.TouchUIActive;
            if (gamepad != controlsGamepad || touch != controlsTouch)
            {
                controlsGamepad = gamepad;
                controlsTouch = touch;
                if (controls != null)
                {
                    controls.text = gamepad ? Strings.HudControlsGamepad : Strings.HudControls; // MUTATION:CONTROLS_GAMEPAD_TEXT
                    controls.text = touch ? Strings.HudControlsTouch : controls.text;
                }
                // Levels v2 (C3b): the hint's {action} and {careful}, and the start line, name the new device's controls.
                SetHintText();
                SetStartLineText();
                SetLampHintText();
            }

            titleTimer += Time.unscaledDeltaTime;
            UpdateCardHold();
            if (titleCard != null)
            {
                // LEVELNUM: a held card goes with a short fade from the first input (HeldCardFadeSeconds); a card shown
                // started keeps the M1 timing (4 s, then 1 s).
                float fade = cardWasHeld ? HeldCardFadeSeconds : 1f;
                titleCard.alpha = titleTimer < CardHoldSeconds ? 1f : Mathf.Clamp01(1f - (titleTimer - CardHoldSeconds) / fade);
            }
            AnimateLevelNumber(gaugeDt);
            if (cardHeld && startLine != null)
            {
                // A slow breath on the start line, so the waiting card reads as waiting.
                Color s = startLine.color;
                s.a = 0.78f + 0.22f * Mathf.Cos(hudClock * 3.2f);
                startLine.color = s;
            }
            UpdateRowHints();
            // The people block fits the screen it was laid out for: it is laid out again when the screen changes size.
            if (peopleOn && titleCard != null && titleCard.alpha > 0f)
            {
                Rect screen = ((RectTransform)transform).rect;
                if (Mathf.Abs(screen.width - peopleLaidFor.x) > 0.5f || Mathf.Abs(screen.height - peopleLaidFor.y) > 0.5f)
                {
                    LayoutPeople();
                }
            }
        }

        // ----- Levels v2 (docs/levels_v2/LEVELS_V2.md 6, task C3b): held card, hint tokens, row hints, exit marker. -----

        /// <summary>The device whose control names the HUD writes into a hint ({action}, {careful}) and the start line.</summary>
        public enum HintDevice
        {
            Keyboard,
            Gamepad,
            Touch,
        }

        // M1 timing of a card shown started: fully visible for this long, then the 1 s fade.
        private const float CardShowSeconds = 4f;

        /// <summary>
        /// Seconds the intro card stays fully visible after <see cref="titleTimer"/> starts: 4 for a level shown started (M1),
        /// 0 once the card was held (the timer restarts at the release, so the fade, <see cref="HeldCardFadeSeconds"/> long
        /// since LEVELNUM, starts with the first input).
        /// </summary>
        private float CardHoldSeconds => cardWasHeld ? 0f : CardShowSeconds;

        /// <summary>Levels v2 (C3b): the intro card is held fully visible now (the level waits for its first input; tests).</summary>
        public bool CardHeld => cardHeld;

        /// <summary>Levels v2 (C3b): the held card's start line shows (hud.start, label StartLine; tests).</summary>
        public bool StartLineVisible => startLine != null && startLine.enabled && TitleCardAlpha > 0f;

        /// <summary>Levels v2 (C3b): the start line's text and the intro card's hint as shown (tokens resolved; tests).</summary>
        public string StartLineText => startLine != null ? startLine.text : null;
        public string HintShown => hintText != null ? hintText.text : null;

        /// <summary>Levels v2 (C3b): "Locked" (hud.door.locked) and the lit-zone line (hud.lit) show (tests).</summary>
        public bool LockedHintVisible => lockedCanvas != null && lockedCanvas.enabled;
        public bool LitHintVisible => litCanvas != null && litCanvas.enabled;

        /// <summary>Levels v2 (C3b): the exit marker is drawn now (its Canvas on and its alpha above 0; tests).</summary>
        public bool ExitMarkerVisible => markerCanvas != null && markerCanvas.enabled && markerGroup != null && markerGroup.alpha > 0.001f;

        /// <summary>The exit marker exists (built with the HUD; tests).</summary>
        public bool ExitMarkerExists => markerCanvas != null;

        /// <summary>The exit marker's alpha (1 from <see cref="MarkerFadeFar"/> metres, 0 at <see cref="MarkerFadeNear"/>; tests).</summary>
        public float ExitMarkerAlpha => markerGroup != null ? markerGroup.alpha : 0f;

        /// <summary>The exit marker sits clamped at the screen edge with its arrow (the exit is off screen or behind; tests).</summary>
        public bool ExitMarkerClamped => markerClamped;

        /// <summary>The exit marker shows the open-eye glyph (a human sees the furniture standing on the exit; tests).</summary>
        public bool ExitMarkerEyeShown => markerEyeOn;

        /// <summary>The exit marker's centre in screen pixels, y up (tests).</summary>
        public Vector2 ExitMarkerScreenPosition => markerScreen;

        /// <summary>The device the HUD names now: touch while the touch controls show, else the last device used.</summary>
        public HintDevice Device => controlsTouch ? HintDevice.Touch : controlsGamepad ? HintDevice.Gamepad : HintDevice.Keyboard;

        /// <summary>
        /// The name of the action control on <paramref name="device"/> in the current language. DOORAUTO: the action only
        /// switches the floor lamp (doors and wardrobes are a push, named in words): the key of the keyboard's lamp hint
        /// ("E"), the gamepad's ("X"), and on touch "tap the lamp" (touch.lamp; the action button is gone).
        /// </summary>
        public static string ActionLabel(HintDevice device)
        {
            switch (device)
            {
                case HintDevice.Touch:
                    return Strings.TouchLamp;
                case HintDevice.Gamepad:
                    return KeyOf(Strings.HudLampPad, "X");
                default:
                    return KeyOf(Strings.HudLamp, "E");
            }
        }

        /// <summary>DOORAUTO: the lamp hint's sentence on <paramref name="device"/> (hud.lamp, hud.lampPad, hud.lampTouch).</summary>
        public static string LampHintText(HintDevice device)
        {
            switch (device)
            {
                case HintDevice.Touch:
                    return Strings.HudLampTouch;
                case HintDevice.Gamepad:
                    return Strings.HudLampPad;
                default:
                    return Strings.HudLamp;
            }
        }

        /// <summary>DOORAUTO: the lamp hint (label LampHintLabel) in the current language for the current device.</summary>
        private void SetLampHintText()
        {
            if (Labels.TryGetValue("LampHintLabel", out Text lamp) && lamp != null)
            {
                lamp.text = LampHintText(Device);
            }
        }

        /// <summary>
        /// The name of the careful control on <paramref name="device"/> in the current language: the key of the careful hint
        /// ("Shift", "Maj"), the gamepad's left trigger ("LT"), the touch careful button's label.
        /// </summary>
        public static string CarefulLabel(HintDevice device)
        {
            switch (device)
            {
                case HintDevice.Touch:
                    return Strings.TouchCareful;
                case HintDevice.Gamepad:
                    return "LT";
                default:
                    return KeyOf(Strings.HudCareful, "Shift");
            }
        }

        /// <summary>The key before the colon of a "Key: does" hint line ("Maj : au ralenti" gives "Maj"), or the fallback.</summary>
        private static string KeyOf(string line, string fallback)
        {
            int colon = string.IsNullOrEmpty(line) ? -1 : line.IndexOf(':');
            string key = colon > 0 ? line.Substring(0, colon).Trim() : null;
            return string.IsNullOrEmpty(key) ? fallback : key;
        }

        /// <summary>
        /// Levels v2 (C3b, LEVELS_V2 D29): <paramref name="hint"/> with every {action} and {careful} replaced by the control
        /// names of <paramref name="device"/> (<see cref="ActionLabel"/>, <see cref="CarefulLabel"/>).
        /// </summary>
        public static string ResolveHintTokens(string hint, HintDevice device)
        {
            if (string.IsNullOrEmpty(hint) || hint.IndexOf('{') < 0)
            {
                return hint;
            }
            return hint.Replace("{action}", ActionLabel(device)).Replace("{careful}", CarefulLabel(device)); // MUTATION:HINT_TOKENS
        }

        /// <summary>
        /// The intro card's hint for the shown level and the current device, its font shrunk (38 down to 26) until its
        /// wrapped lines fit the hint box (the v2 hints run to two or three sentences).
        /// </summary>
        private void SetHintText()
        {
            if (hintText == null || shownLevel == null)
            {
                return;
            }
            hintText.text = ResolveHintTokens(Strings.Get(shownLevel.HintKey), Device);
            int size = CardHintSize;
            hintText.fontSize = size;
            while (size > CardHintMinSize && hintText.preferredHeight > CardHintHeight)
            {
                size -= 2;
                hintText.fontSize = size;
            }
        }

        /// <summary>The start line in the current language and for the current device (hud.start and its variants).</summary>
        private void SetStartLineText()
        {
            if (startLine == null)
            {
                return;
            }
            HintDevice device = Device;
            startLine.text = device == HintDevice.Touch ? Strings.HudStartTouch
                : device == HintDevice.Gamepad ? Strings.HudStartGamepad : Strings.HudStart;
        }

        /// <summary>
        /// Every frame and at ShowLevel: the card is held while the shown level waits for its first input (GameState.Started
        /// false, still playing, no panel). Held, the card stays fully visible (its timer stays at 0) with the start line;
        /// at the release the start line goes and the card fades over <see cref="HeldCardFadeSeconds"/> from that instant.
        /// </summary>
        private void UpdateCardHold()
        {
            bool held = shownLevel != null && Game != null && Game.Level != null && !Game.Started
                && Game.State == PlayState.Playing && !failOn && !winOn;
            if (held)
            {
                titleTimer = 0f; // MUTATION:CARD_HELD
                cardWasHeld = true;
            }
            if (held == cardHeld)
            {
                return;
            }
            cardHeld = held;
            if (held)
            {
                SetStartLineText();
            }
            if (startPlate != null)
            {
                startPlate.enabled = held;
            }
            if (startLine != null)
            {
                startLine.enabled = held;
            }
        }

        // ----- LEVELNUM (docs/next/progress/LEVELNUM.md): the intro card's dim with the level number's holes (CardNumber). -----

        /// <summary>LEVELNUM: the number the intro card shows (the level select's number), 0 when none (a level outside levels.json).</summary>
        public int LevelNumberShown => levelNumber;

        /// <summary>LEVELNUM: seconds of the number's zoom played (frozen while paused or under a menu); tests and shots set it.</summary>
        public float LevelNumberAge
        {
            get => cardNumber != null ? cardNumber.Age : 0f;
            set
            {
                if (cardNumber != null)
                {
                    cardNumber.Age = value;
                    PoseCardNumber();
                }
            }
        }

        /// <summary>LEVELNUM: the dim layer's alpha (it always follows <see cref="TitleCardAlpha"/>).</summary>
        public float CardBackdropAlpha => cardNumber != null ? cardNumber.Alpha : 0f;

        /// <summary>LEVELNUM: the dim's effective opacity outside the holes now.</summary>
        public float CardDimShown => CardDimAlpha * CardBackdropAlpha;

        /// <summary>LEVELNUM: the dim and the holes use their shaders (false: a plain dim, the shaders are missing).</summary>
        public bool LevelNumberHolesReady => cardNumber != null && cardNumber.Ready;

        /// <summary>LEVELNUM: the number's scale now, and the scale it settles at on the current canvas.</summary>
        public float LevelNumberScale => cardNumber != null ? cardNumber.Scale : 0f;
        public float LevelNumberFinalScale => cardNumber != null ? cardNumber.FinalScale : 0f;

        /// <summary>LEVELNUM: the number's ink (the digits' box) in the HUD root's local units, centred on the screen centre.</summary>
        public Rect LevelNumberInkRect => cardNumber != null ? cardNumber.InkRect : Rect.zero;

        /// <summary>LEVELNUM: the share of the holes' mask at least half covered, and the highest coverage (tests).</summary>
        public float LevelNumberCoveredShare(out float highest)
        {
            highest = 0f;
            return cardNumber != null ? cardNumber.CoveredShare(out highest) : 0f;
        }

        private void OnDestroy()
        {
            cardNumber?.Dispose();
            cardNumber = null;
        }

        /// <summary>The level select's <paramref name="number"/> on the card (0: none, a plain dim) and the zoom from its start.</summary>
        private void SetLevelNumber(int number)
        {
            levelNumber = Mathf.Max(0, number);
            if (cardNumber != null)
            {
                cardNumber.SetNumber(levelNumber);
            }
            PoseCardNumber();
        }

        /// <summary>The layer follows the card's alpha now (the number keeps its pose).</summary>
        private void SyncBackdrop()
        {
            PoseCardNumber();
        }

        /// <summary>Every frame: the zoom plays on the HUD clock, then the layer follows the card.</summary>
        private void AnimateLevelNumber(float dt)
        {
            // Frozen while paused or under a menu, so the zoom is seen when the card is; a step is capped at a 30 Hz frame,
            // so the frame after a level build (a long one) does not skip it.
            if (cardNumber != null && levelNumber > 0 && Visible && (Game == null || !Game.Paused))
            {
                cardNumber.Age += Mathf.Min(dt, 1f / 30f);
            }
            PoseCardNumber();
        }

        /// <summary>The number at its age (at the end under <see cref="ReducedMotion"/>) over the HUD's canvas, with the card's alpha.</summary>
        private void PoseCardNumber()
        {
            if (cardNumber == null)
            {
                return;
            }
            Rect canvas = ((RectTransform)transform).rect;
            float pixelsPerUnit = rootCanvas != null ? rootCanvas.scaleFactor : 1f;
            float age = ReducedMotion ? NumberZoomSeconds : cardNumber.Age;
            cardNumber.Pose(titleCard != null ? titleCard.alpha : 0f, age, canvas.size, canvas.size * pixelsPerUnit);
        }

        /// <summary>
        /// Every frame: the row hints GameState does not push (the locked door from <see cref="GameState.LockedDoorHintWanted"/>,
        /// the lit zone from the furniture), then the exit marker.
        /// </summary>
        private void UpdateRowHints()
        {
            bool locked = Game != null && Game.LockedDoorHintWanted; // MUTATION:LOCKED_HINT
            bool lit = LitHintWanted();
            if (locked != lockedOn || lit != litOn)
            {
                lockedOn = locked;
                litOn = lit;
                ApplyCanvases();
            }
            UpdateExitMarker();
        }

        /// <summary>
        /// The lit-zone line is wanted: the level runs, the furniture is a lamp body under the Lamp rule, its light is off
        /// and its centre stands in a lit zone (FurnitureController.InLitZone: the dark gives it no cover there).
        /// </summary>
        private bool LitHintWanted()
        {
            if (Game == null || Game.Level == null || Game.State != PlayState.Playing || !Game.Started)
            {
                return false;
            }
            FurnitureController f = Game.Furniture;
            if (f == null || f.Body == null || !f.Body.HasLight || f.Lamp == null || f.Rules == null || !f.Rules.Lamp)
            {
                return false;
            }
            return !f.Lamp.On && f.InLitZone && !f.Hidden && !f.Carried; // MUTATION:LIT_HINT
        }

        /// <summary>
        /// One frame of the exit marker: over the exit zone's centre (on its floor, MarkerHeight up); when that point is off
        /// screen or behind the camera, clamped to the screen edge along the line from the screen centre with its arrow
        /// pointing on; its alpha 1 from MarkerFadeFar metres of the furniture down to 0 at MarkerFadeNear; the open-eye
        /// glyph in place of the door (at full alpha) while a human sees the furniture standing on the exit. Hidden while
        /// paused, under the panels and the menus (ApplyCanvases), and when no level runs.
        /// </summary>
        private void UpdateExitMarker()
        {
            if (markerCanvas == null)
            {
                return;
            }
            LevelDef def = Game != null && Game.Level != null ? Game.Def : null;
            FurnitureController f = def != null ? Game.Furniture : null;
            bool want = def != null && def.Exit != null && f != null && View != null && Game.State == PlayState.Playing
                && !Game.Paused;
            if (want != markerWanted)
            {
                markerWanted = want;
                SetEnabled(markerCanvas, Visible && markerWanted && !failOn && !winOn);
            }
            if (!want)
            {
                markerClamped = false;
                markerEyeOn = false;
                return;
            }

            float floor = def.Floor != null ? def.FloorHeightAt(def.Exit.X, def.Exit.Z) : 0f;
            var world = new Vector3(def.Exit.X, floor + MarkerHeight, def.Exit.Z);
            Vector3 sp = View.WorldToScreenPoint(world);
            bool behind = sp.z <= 0f;
            float scale = rootCanvas != null && rootCanvas.scaleFactor > 0f ? rootCanvas.scaleFactor : 1f;
            Vector2 size = ((RectTransform)transform).rect.size;
            // Reference units, y up, origin at the bottom left (the marker's anchor).
            var p = new Vector2(sp.x, sp.y) / scale;
            if (behind)
            {
                // Behind the camera the projection is mirrored: mirror it back, so the arrow points the right way round.
                p = size - p;
            }
            float half = MarkerSize * 0.5f;
            bool onScreen = !behind && p.x >= 0f && p.x <= size.x && p.y >= 0f && p.y <= size.y;
            Vector2 pos;
            if (onScreen)
            {
                pos = new Vector2(Mathf.Clamp(p.x, half, size.x - half), Mathf.Clamp(p.y, half, size.y - half));
                markerClamped = false;
            }
            else
            {
                // Clamped inside the margins (the bottom one clears the eye band and the sat-on row), on the line from the
                // inner rect's centre toward the exit.
                var inner = Rect.MinMaxRect(MarkerEdge + half, MarkerBottomEdge + half, size.x - MarkerEdge - half, size.y - MarkerEdge - half);
                Vector2 c = inner.center;
                Vector2 d = p - c;
                if (d.sqrMagnitude < 1e-4f)
                {
                    d = Vector2.down;
                }
                float tx = Mathf.Abs(d.x) > 1e-4f ? inner.width * 0.5f / Mathf.Abs(d.x) : float.MaxValue;
                float ty = Mathf.Abs(d.y) > 1e-4f ? inner.height * 0.5f / Mathf.Abs(d.y) : float.MaxValue;
                pos = c + d * Mathf.Min(tx, ty); // MUTATION:MARKER_CLAMP
                markerClamped = true;
                markerArrow.rectTransform.parent.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg - 90f);
            }
            markerRect.anchoredPosition = pos;
            markerScreen = pos * scale;
            markerArrow.enabled = markerClamped;

            Vector3 at = f.transform.position;
            float distance = new Vector2(at.x - def.Exit.X, at.z - def.Exit.Z).magnitude;
            bool eyeOn = Game.Seen && def.Exit.Contains(at) && !f.Carried && !f.Hidden;
            markerEyeOn = eyeOn;
            markerEye.enabled = eyeOn;
            markerDoor.enabled = !eyeOn;
            markerGroup.alpha = eyeOn ? 1f : Mathf.InverseLerp(MarkerFadeNear, MarkerFadeFar, distance); // MUTATION:MARKER_FADE
        }

        // ----- M3: world markers (tests read them; M3.1 dropped the clamp, the HUD band is at the bottom) -----

        private static Rect WorldRect(RectTransform rect)
        {
            if (rect == null)
            {
                return Rect.zero;
            }
            // In a Screen Space Overlay canvas, world corners are screen pixels.
            rect.GetWorldCorners(Corners);
            return Rect.MinMaxRect(Corners[0].x, Corners[0].y, Corners[2].x, Corners[2].y);
        }

        private static Rect Union(Rect a, Rect b)
        {
            if (a.width <= 0f)
            {
                return b;
            }
            return b.width <= 0f ? a : Rect.MinMaxRect(Mathf.Min(a.xMin, b.xMin), Mathf.Min(a.yMin, b.yMin), Mathf.Max(a.xMax, b.xMax), Mathf.Max(a.yMax, b.yMax));
        }

        /// <summary>The world space Canvases under the inhabitants of the current level, found once per level.</summary>
        private void RefreshMarkers()
        {
            bool stale = markerLevel != Game.Level;
            foreach (Canvas c in markerCanvases)
            {
                stale |= c == null;
            }
            if (!stale)
            {
                return;
            }
            markerCanvases.Clear();
            markerLevel = Game.Level;
            foreach (Inhabitant inhabitant in Game.Level.Inhabitants)
            {
                if (inhabitant == null)
                {
                    continue;
                }
                foreach (Canvas c in inhabitant.GetComponentsInChildren<Canvas>(true))
                {
                    if (c.renderMode == RenderMode.WorldSpace)
                    {
                        markerCanvases.Add(c);
                    }
                }
            }
        }

        /// <summary>
        /// The screen rect (pixels, y up) of a world space rect seen through <see cref="View"/>; an empty rect when a
        /// corner is behind the camera.
        /// </summary>
        public Rect ScreenRectOf(RectTransform rect)
        {
            if (rect == null || View == null)
            {
                return Rect.zero;
            }
            rect.GetWorldCorners(Corners);
            float xMin = float.MaxValue, yMin = float.MaxValue, xMax = float.MinValue, yMax = float.MinValue;
            for (int i = 0; i < 4; i++)
            {
                Vector3 p = View.WorldToScreenPoint(Corners[i]);
                if (p.z <= 0f)
                {
                    return Rect.zero;
                }
                xMin = Mathf.Min(xMin, p.x);
                xMax = Mathf.Max(xMax, p.x);
                yMin = Mathf.Min(yMin, p.y);
                yMax = Mathf.Max(yMax, p.y);
            }
            return Rect.MinMaxRect(xMin, yMin, xMax, yMax);
        }

        /// <summary>The marker Canvases of the current level (tests).</summary>
        public IReadOnlyList<Canvas> MarkerCanvases
        {
            get
            {
                if (Game != null && Game.Level != null)
                {
                    RefreshMarkers();
                }
                return markerCanvases;
            }
        }

        // ----- Construction helpers -----

        private Canvas NewPanel(string name, string title, string body, string action, Color dim, Color titleColor, out Text bodyText)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(transform, false);
            Stretch((RectTransform)go.transform);
            var canvas = go.AddComponent<Canvas>();
            canvas.overrideSorting = true;
            canvas.sortingOrder = 20;
            Image background = NewImage(go.transform, "Dim", null, dim);
            Stretch(background.rectTransform);
            Text t = NewText(go.transform, name + "Title", title, 150, TextAnchor.MiddleCenter, titleColor);
            Place(t.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, 120f), new Vector2(1600f, 190f));
            bodyText = NewText(go.transform, name + "Body", body, 52, TextAnchor.MiddleCenter, Color.white);
            Place(bodyText.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, -10f), new Vector2(1600f, 80f));
            Text a = NewText(go.transform, name + "Action", action, 38, TextAnchor.MiddleCenter, new Color(1f, 1f, 1f, 0.85f));
            Place(a.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, ActionY), new Vector2(1600f, 60f));
            return canvas;
        }

        private static Image NewImage(Transform parent, string name, Sprite sprite, Color color)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var image = go.AddComponent<Image>();
            image.sprite = sprite;
            image.color = color;
            image.raycastTarget = false;
            return image;
        }

        private Text NewText(Transform parent, string name, string value, int size, TextAnchor anchor, Color color)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var text = go.AddComponent<Text>();
            text.font = Font;
            text.fontSize = size;
            text.alignment = anchor;
            text.color = color;
            text.text = value;
            text.raycastTarget = false;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            var shadow = go.AddComponent<Shadow>();
            shadow.effectColor = new Color(0f, 0f, 0f, 0.65f);
            shadow.effectDistance = new Vector2(2f, -3f);
            Labels[name] = text;
            return text;
        }

        private static void Place(RectTransform rect, Vector2 anchor, Vector2 offset, Vector2 size)
        {
            rect.anchorMin = rect.anchorMax = anchor;
            rect.pivot = anchor;
            rect.anchoredPosition = offset;
            rect.sizeDelta = size;
        }

        private static void Stretch(RectTransform rect)
        {
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }
    }

    /// <summary>
    /// The states of the HUD eye (docs/CONTRACT_M2.md 11.6), and since M5 the dog's (CONTRACT_M5_v3 15.5). Precedence:
    /// Alarm, then Calm (a human sees), then Dog (only the dog sees), then Closed.
    /// </summary>
    public enum HudEye
    {
        Closed,
        Calm,
        Alarm,
        /// <summary>M5: only the dog sees the furniture (v3 15.5: Alarm, then Calm, then Dog, then Closed).</summary>
        Dog,
    }
}
