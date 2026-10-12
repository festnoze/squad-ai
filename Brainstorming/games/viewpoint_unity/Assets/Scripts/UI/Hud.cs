using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Viewpoint
{
    /// <summary>
    /// The in-game overlay (PRD section 12.1): crosshair, battery and film
    /// counters, interaction prompt, the raised picture, the viewfinder, the
    /// held-photo panel, the level banner, the rewind wash, the toast and the
    /// black fade. Built entirely in code, like the original, and driven every
    /// frame by <see cref="Main"/>.
    ///
    /// Every pixel figure below is read straight off the PRD 12.1 table and
    /// means what it says because the canvas scales against a 1600 x 900
    /// reference matched on HEIGHT. Match on height and not on width because
    /// the raised picture is sized from the viewport HEIGHT (12.2): matching
    /// width would let an ultrawide window scale the UI away from the square
    /// the 3D frustum actually covers.
    ///
    /// PRD_VISUAL tier 4 added the motion (V-ANIM-03, V-ANIM-04, V-VFX-06,
    /// V-HUD-06, V-POST-06). One rule governs all of it and is worth stating
    /// once: A TWEEN OWNS PIXELS, NEVER STATE. Every widget's meaning is
    /// applied the instant Main hands it over, and the animation is a departure
    /// from that resting value which decays back to it. Nothing here can defer
    /// a collider, a counter, a held id or an event, and the raised picture in
    /// particular puts the roll on the anchor rect AT ONCE and lets only the
    /// picture under it lag (see <see cref="SetPhotoView"/>).
    ///
    /// PRD_VISUAL tier 5 gave the overlay its surfaces (V-HUD-02 to 05 and
    /// V-HUD-07): the counters, the prompt and the held hints now sit on drawn
    /// panels instead of floating on the world. Two rules govern that work and
    /// are worth stating once too:
    ///
    /// EVERY PANEL, CAP AND GLYPH IS PAINTED IN THIS FILE. Section 3.2 as
    /// amended (Appendix C.11) allows the font and the CC0 texture sets and
    /// nothing else, so there is no sprite atlas to import and nothing to
    /// strip out of the player. The painters live at the bottom of the file
    /// and everything they produce is cached on the instance, so a frame of
    /// HUD costs no texture work at all.
    ///
    /// A PANEL CHANGES WHAT A LABEL NEEDS. A label on bare sky is carried
    /// entirely by its dark contour (white on this sky is about 1.24:1, see
    /// Fonts.Apply); a label on one of these panels has its contrast from the
    /// panel and takes the lighter TextEdge.Shadow. Which label gets which is
    /// therefore a consequence of where it sits, not a taste, and it is noted
    /// at each Build below.
    /// </summary>
    public sealed class Hud : MonoBehaviour
    {
        static readonly Vector2 ReferenceResolution = new Vector2(1600f, 900f);

        /// <summary>Under the menu, which sits at 100.</summary>
        const int SortingOrder = 50;

        // ---- PRD 12.1 -------------------------------------------------------

        /// <summary>
        /// PRD 12.1's white at 85 percent. The 5 x 5 px square it used to fill
        /// is gone: V-HUD-05 replaces it with a ring, a dot and a reticle, all
        /// sized in the tier 5 block below. The ALPHA is the part of the pinned
        /// look that survives, and it is shared by all three.
        /// </summary>
        static readonly Color CrosshairColor = new Color(1f, 1f, 1f, 0.85f);

        const float BatterySizePx = 22f;
        static readonly Vector2 BatteryOffset = new Vector2(24f, 20f);

        const float FilmSizePx = 20f;

        /// <summary>
        /// PRD 12.1 also gives the film line its own offset, (24, 52). It has
        /// no constant any more because nothing positions that line: V-HUD-02
        /// makes it the second row of a panel, and the row lands where the
        /// first row's height and the panel's spacing put it, which is 54.
        /// See BuildCounters.
        /// </summary>
        static readonly Color FilmColor = new Color(0.75f, 0.95f, 0.93f);

        const float PromptSizePx = 22f;
        const float PromptBottomPx = 120f;

        const float HeldMarginPx = 24f;

        /// <summary>
        /// Not a PRD number: 12.1 pins the 24 px margins and 12.3 pins the
        /// 86 x 78 minimum, and the width was free. It was 520 while the hints
        /// were one line of text. V-HUD-04 turns that line into four key-cap
        /// pairs, and measured on Manrope's own advance widths those cost about
        /// 341 px of type (the four keys at 13 px and the four actions at 15)
        /// plus 101 px of chip padding and gaps. 580 leaves the row 556 px
        /// inside the panel's padding, which clears 442 with enough room for
        /// the synthesised weight (see Fonts.StyleFor) to run wider than the
        /// metrics say, since a row that overflows this panel overflows it to
        /// the LEFT, off the edge of the panel entirely.
        /// </summary>
        const float HeldPanelWidthPx = 580f;

        const float HeldPanelHeightPx = 158f;
        const float HeldTitleSizePx = 22f;
        const float HeldHintSizePx = 15f;

        static readonly Vector2 HeldPanelMinSize = new Vector2(86f, 78f);
        static readonly Color HeldHintColor = new Color(1f, 1f, 1f, 0.75f);

        /// <summary>
        /// The hint line of PRD 12.1, VERBATIM, and the only copy of it.
        ///
        /// V-HUD-04 asks for "the four control hints as key-cap glyph pairs in
        /// a row" while its acceptance asks that "the hint string's four
        /// commands stay in the same order and words". Both hold here because
        /// the row is BUILT BY SPLITTING THIS CONSTANT and never by retyping
        /// its pieces: the four commands are what Split hands back, in the
        /// order it hands them back, and each command's key and action are the
        /// two halves of its first " : ". BuildHintRow rejoins them and logs an
        /// error if the result is not this string byte for byte, so an edit
        /// that breaks the identity says so instead of shipping.
        /// </summary>
        const string HeldHintText =
            "Clic gauche : poser   Clic droit : lever   Molette : pivoter   F : reposer";

        /// <summary>The three spaces PRD 12.1 puts between two commands.</summary>
        const string HintSeparator = "   ";

        /// <summary>
        /// What sits between a key and what it does, in every prompt and in
        /// every hint the game writes. Used to lift the key out of a string
        /// without editing the string (see <see cref="SplitPromptKey"/>).
        /// </summary>
        const string KeySeparator = " : ";

        const float BannerTopPx = 70f;
        const float BannerTitleSizePx = 44f;
        const float BannerSubtitleSizePx = 20f;
        static readonly Color BannerSubtitleColor = new Color(1f, 1f, 1f, 0.85f);
        const float BannerSeconds = 4.5f;

        static readonly Color FadeColor = new Color(0.05f, 0.05f, 0.08f);
        const float FadeSeconds = 0.6f;

        static readonly Color RewindTint = new Color(0.35f, 0.55f, 0.85f, 0.18f);
        const float RewindSizePx = 30f;
        const float RewindTopPx = 170f;
        static readonly Color RewindColor = new Color(0.85f, 0.94f, 1.0f);

        const float ToastSizePx = 20f;
        const float ToastBottomPx = 160f;
        static readonly Color ToastColor = new Color(1f, 0.85f, 0.6f);
        const float ToastSeconds = 2.2f;

        /// <summary>
        /// Outline strength for the readable labels. The original gave Godot an
        /// outline in PIXELS (6 to 8); TextMeshPro's outlineWidth is normalized
        /// against the font's SDF spread instead, so this is matched by eye
        /// rather than converted, and it is the one number in this file that is
        /// not a port.
        /// </summary>
        const float OutlineWidth = 0.2f;

        static readonly Color OutlineSoft = new Color(0f, 0f, 0f, 0.5f);
        static readonly Color OutlineStrong = new Color(0f, 0f, 0f, 0.7f);

        // ---- PRD 12.2, the shared square ------------------------------------

        static readonly Color ViewfinderDim = new Color(0.05f, 0.06f, 0.10f, 0.35f);
        static readonly Color ViewfinderEdge = new Color(1f, 1f, 1f, 0.5f);
        static readonly Color BracketDark = new Color(0.05f, 0.06f, 0.10f, 0.7f);
        static readonly Color BracketLight = new Color(1f, 1f, 1f, 0.95f);
        const float ViewfinderEdgePx = 2f;
        const float BracketArmFraction = 0.16f;
        const float BracketDarkPx = 7f;
        const float BracketLightPx = 3f;

        // ---- PRD_VISUAL 4.8, 4.9 and 4.11: the motion -----------------------
        //
        // These are the only numbers in this file that do not come from the
        // gameplay PRD. They come from PRD_VISUAL, which writes each duration
        // out in its item, and they are all SHORT on purpose: the probe reads
        // the world on the frame an action happens, and an effect the eye can
        // wait for is an effect that has started to lie about the state.

        /// <summary>V-VFX-04 and V-ANIM-03: scale 1.0 to 1.25 to 1.0.</summary>
        const float CounterPopSeconds = 0.2f;
        const float CounterPopScale = 0.25f;

        const float PromptInSeconds = 0.12f;
        const float PromptOutSeconds = 0.2f;

        const float HeldSlideSeconds = 0.2f;

        // Matches the raise tween in V-ANIM-04, so the card leaves the panel over

        // exactly the time the picture takes to arrive in front of the eye.

        const float CardRaiseFadeSeconds = 0.18f;

        /// <summary>
        /// Where the held panel parks while it is off screen. Its right edge is
        /// its pivot, so anything past its own width clears the frame whatever
        /// the window's aspect is.
        /// </summary>
        const float HeldHiddenX = HeldPanelWidthPx + HeldMarginPx;

        const float ToastInSeconds = 0.18f;
        const float ToastOutSeconds = 0.25f;
        const float ToastRisePx = 12f;

        /// <summary>V-ANIM-04: raising, turning and lowering the picture.</summary>
        const float PhotoRaiseSeconds = 0.18f;
        const float PhotoTurnSeconds = 0.12f;
        const float PhotoLowerSeconds = 0.18f;

        /// <summary>V-VFX-06: the fresh polaroid pulled out of the camera.</summary>
        const float PhotoPullSeconds = 0.35f;
        const float PhotoPullBelowPx = 90f;
        const float PhotoPullScale = 0.55f;

        /// <summary>
        /// Overshoot of the raise, as the c1 term of the standard back-out
        /// easing. 1.2 peaks about 6 percent past the square, which reads as a
        /// picture settling rather than as a bounce.
        /// </summary>
        const float PhotoOvershoot = 1.2f;

        const float ViewfinderInSeconds = 0.15f;
        const float ViewfinderOutSeconds = 0.1f;

        /// <summary>
        /// The brackets fly in from outside the corners, which is one scale on
        /// their common parent rather than sixteen animated positions: the
        /// parent's pivot is the canvas centre, so scaling it walks every arm
        /// along the diagonal it already sits on.
        /// </summary>
        const float BracketFromScale = 1.12f;

        const int FrostBands = 3;
        const float FrostBandPx = 4f;
        static readonly Color FrostColor = new Color(0.88f, 0.94f, 1f, 0.13f);

        /// <summary>
        /// V-VFX-06 gives the shutter 0.12 s, and that is the WHOLE closure:
        /// shut and open again, like every other duration in section 4.8. Split
        /// evenly, the frame is fully black for a single frame rather than for
        /// an eighth of a second, which is both what a shutter looks like and
        /// what keeps a screenshot out of the dark (the shot probe's frames must
        /// not read near-black, and verify-player fails them if they do).
        /// </summary>
        const float ShutterCloseSeconds = 0.06f;
        const float ShutterOpenSeconds = 0.06f;
        const float ShutterFlashSeconds = 0.08f;
        static readonly Color ShutterLeafColor = new Color(0.02f, 0.02f, 0.03f, 1f);

        /// <summary>
        /// How long after <see cref="PlayShutter"/> a picture arriving in hand
        /// still counts as freshly taken. The capture sets the placer raised in
        /// the same frame, so this only has to survive one Update; it is a
        /// fifth of a second so that a hitch cannot turn the pull-from-camera
        /// slide into a card-to-square raise.
        /// </summary>
        const float ShutterArmSeconds = 0.2f;

        const float RewindInSeconds = 0.15f;
        const float RewindOutSeconds = 0.2f;

        /// <summary>
        /// V-HUD-06's "slow reverse pulse". A snap to full brightness followed
        /// by a slow decay, and the direction is the whole point: a pulse that
        /// ramps UP reads as something charging, so the reverse of that reads as
        /// something running backwards. A symmetric breath would read as
        /// waiting.
        /// </summary>
        const float RewindPulseSeconds = 0.85f;
        const float RewindPulseFloor = 0.55f;

        const float RewindBarWidthPx = 320f;
        const float RewindBarHeightPx = 3f;

        /// <summary>Just under the label's own 42 px box.</summary>
        const float RewindBarTopPx = RewindTopPx + 44f;

        /// <summary>
        /// The amber of the rewind bar is READ from the palette, not copied.
        /// In this game amber means stored energy (PRD 5.1), and a bar that
        /// spends the player's history is spending exactly that; a copied
        /// triple would drift the day the palette moves.
        /// </summary>
        static readonly Color RewindAmber = Palette.Get("battery");

        // ---- PRD_VISUAL 4.11: the panels, the caps and the drawn glyphs -----
        //
        // Tier 5's whole design, in one block: one ink, three alphas, one
        // corner radius family and the sizes the glyphs are painted at.

        /// <summary>
        /// The one dark this interface is made of. It is the menu's dim of PRD
        /// 12.4 (0.08, 0.10, 0.14) rather than a new colour, so a HUD panel and
        /// the menu that can open over it read as the same material. Only the
        /// alpha changes from panel to panel, and every alpha below is the one
        /// its own item names.
        /// </summary>
        static readonly Color PanelInk = new Color(0.08f, 0.10f, 0.14f);

        /// <summary>V-HUD-02: "a single rounded panel at 60 percent dark".</summary>
        const float CounterPanelAlpha = 0.60f;

        /// <summary>V-HUD-03: "a pill (generated rounded rect, 55 percent dark)".</summary>
        const float PromptPillAlpha = 0.55f;

        /// <summary>V-HUD-04: "a simple 65 percent dark", see BuildHeldPanel.</summary>
        const float HeldPanelAlpha = 0.65f;

        /// <summary>
        /// Corner radius of the counter and held panels, in reference pixels.
        /// Ten is a fifth of the counter panel's height: enough to read as
        /// drawn rather than as a default rectangle, and short of the "pill"
        /// V-HUD-03 reserves for the prompt.
        /// </summary>
        const int PanelRadiusPx = 10;

        /// <summary>Corner radius of a key cap. A chip, not a pill.</summary>
        const int KeyCapRadiusPx = 4;

        const float CounterPadXPx = 10f;
        const float CounterPadYPx = 8f;
        const float CounterRowGapPx = 8f;
        const float CounterRowSpacingPx = 4f;

        /// <summary>PRD_VISUAL names the size: "a generated 16 x 24 icon".</summary>
        static readonly Vector2 BatteryGlyphPx = new Vector2(16f, 24f);

        static readonly Vector2 FilmGlyphPx = new Vector2(20f, 20f);

        /// <summary>
        /// The battery glyph is amber and the film glyph is the film counter's
        /// own teal, both READ rather than copied: amber means stored energy in
        /// this game and the numbers beside the glyph are exactly that count
        /// (PRD 5.1), so a glyph that spelt out a triple would drift the day
        /// the palette moves.
        /// </summary>
        static readonly Color BatteryGlyphColor = Palette.Get("battery");

        /// <summary>
        /// Forty and not more: PRD 12.1 puts the prompt's bottom edge at 120 px
        /// and the toast's at 160, and those two used to be a bare line of text
        /// each. Now that the prompt has a box around it, anything taller than
        /// the 40 px between them would slide under the toast, which is the one
        /// other thing that speaks from the bottom of this screen.
        /// </summary>
        const float PromptPillHeightPx = 40f;
        const float PromptPillPadXPx = 18f;
        const float PromptCapGapPx = 10f;

        /// <summary>
        /// A key cap's letter. Smaller than the line it prefixes, because a cap
        /// is a label on a key and not a word in the sentence.
        /// </summary>
        const float PromptCapSizePx = 16f;

        const float HintCapSizePx = 13f;
        const float KeyCapPadXPx = 6f;
        const float KeyCapPadYPx = 3f;
        const float HintPairGapPx = 5f;
        const float HintCommandGapPx = 11f;
        const float HintRowHeightPx = 26f;

        /// <summary>
        /// A cap is a light chip with dark type on it, the one place in this
        /// interface where that polarity is inverted. That is the point: a key
        /// cap has to read as a physical thing the player presses, and on a
        /// dark panel the only way to say "object" rather than "word" is to
        /// make it the brightest thing in the line.
        /// </summary>
        static readonly Color KeyCapFace = new Color(0.93f, 0.95f, 0.97f, 0.92f);
        static readonly Color KeyCapInk = new Color(0.07f, 0.09f, 0.13f);

        /// <summary>
        /// The longest key a cap will hold. Long enough for "F11", short enough
        /// that a sentence opening on a colon ("Mains pleines : ...") can never
        /// be mistaken for a key. See <see cref="SplitPromptKey"/>.
        /// </summary>
        const int KeyCapMaxChars = 3;

        // ---- V-HUD-05: the crosshair ----------------------------------------

        /// <summary>Outer diameter of the ring. The item's "6 px ring".</summary>
        const float CrosshairRingPx = 6f;

        const float CrosshairRingStrokePx = 1.3f;

        /// <summary>The item's "2 px dot", which is all that is left while a
        /// picture is raised.</summary>
        const float CrosshairDotPx = 2f;

        /// <summary>The viewfinder's reticle: a circle with four tick marks.</summary>
        const float CrosshairReticlePx = 24f;

        /// <summary>
        /// What the ring shrinks TO when a picture is raised: the dot's own
        /// size, so the ring does not fade out beside the dot, it collapses
        /// into it.
        /// </summary>
        const float CrosshairShrink = CrosshairDotPx / CrosshairRingPx;

        const float CrosshairFadeSeconds = 0.12f;

        // ---- V-HUD-07: the banner's rule and its delayed subtitle -----------

        /// <summary>
        /// How long the rule takes to grow out from under the title. Inside the
        /// 0.667 s the pinned alpha curve takes to reach full, so the line is
        /// done arriving by the time the words are fully there.
        /// </summary>
        const float BannerRuleSeconds = 0.35f;

        const float BannerRuleHeightPx = 2f;

        /// <summary>
        /// Slack either side of the title, so the rule reads as belonging to
        /// the words rather than as underlining them.
        /// </summary>
        const float BannerRuleMarginPx = 48f;

        const float BannerRuleMinPx = 160f;
        const float BannerRuleMaxPx = 900f;
        static readonly Color BannerRuleColor = new Color(1f, 1f, 1f, 0.55f);

        /// <summary>V-HUD-07: "the subtitle fades in 0.15 s after the title".</summary>
        const float BannerSubtitleDelay = 0.15f;
        const float BannerSubtitleFade = 0.15f;

        // ---- V-POST-06: the two transition colours --------------------------

        /// <summary>
        /// Falling fades to this, and it is the colour every fade used before
        /// V-POST-06 split the two transitions apart.
        /// </summary>
        public static Color FadeBlack
        {
            get { return FadeColor; }
        }

        /// <summary>
        /// Departing a level fades to this instead: the teleporter's light
        /// swallowing the frame. Not pure white but white carrying a trace of
        /// the teleporter's indigo, so the wash belongs to this palette.
        /// </summary>
        public static readonly Color FadeWhite = new Color(0.97f, 0.97f, 1f);

        // ---- Widgets --------------------------------------------------------

        Canvas _canvas;
        RectTransform _canvasRect;
        Text _batteryLabel;
        Text _filmLabel;
        RectTransform _batteryGlyph;
        RectTransform _filmGlyph;
        Text _promptLabel;
        Text _promptCapLabel;
        RectTransform _promptCap;
        string _promptText = string.Empty;
        Text _toastLabel;
        Text _rewindLabel;
        Text _bannerTitle;
        Text _bannerSubtitle;
        Text _heldTitle;

        RawImage _photoView;
        RectTransform _photoViewRect;
        RectTransform _pictureRect;
        RawImage _ghostView;
        RectTransform _ghostRect;
        CanvasGroup _ghostGroup;
        RectTransform _bracketRoot;
        RectTransform[] _viewfinderDims;
        RectTransform[] _viewfinderEdges;
        RectTransform[] _viewfinderBrackets;
        RectTransform[] _viewfinderFrost;
        RectTransform _heldPanel;
        PhotoCard _heldCard;
        PhotoCardShadow _heldCardShadow;
        readonly Tween _heldCardFade = new Tween();
        float _heldCardFromA;
        float _heldCardToA = 1f;
        Texture2D _heldCardTexture;
        CanvasGroup _bannerGroup;
        CanvasGroup _bannerSubtitleGroup;
        RectTransform _bannerRule;
        float _bannerRuleWidth;
        RectTransform _crosshairRing;
        CanvasGroup _crosshairRingGroup;
        Fader _crosshairRingFader;
        Fader _crosshairReticleFader;
        Image _fade;
        CanvasGroup _rewindPulse;
        RectTransform _rewindBarFill;
        RectTransform _shutterRoot;
        RectTransform _shutterTop;
        RectTransform _shutterBottom;
        Image _shutterFlash;
        CanvasGroup _toastGroup;

        Fader _promptFader;
        Fader _filmFader;
        Fader _viewfinderFader;
        Fader _rewindFader;

        // ---- The drawn art --------------------------------------------------
        //
        // Cached on the INSTANCE and not statically. A static cache would
        // survive a domain reload in the editor holding references to textures
        // play mode has already destroyed, which read as null and rebuild
        // anyway; on the instance there is exactly one cache per HUD, it is
        // filled once during Build, and OnDestroy can give it all back.

        readonly Dictionary<int, Sprite> _roundedSprites = new Dictionary<int, Sprite>();
        readonly List<UnityEngine.Object> _drawn = new List<UnityEngine.Object>();
        Sprite _batteryGlyphSprite;
        Sprite _filmGlyphSprite;
        Sprite _ringSprite;
        Sprite _dotSprite;
        Sprite _reticleSprite;

        float _bannerTimer;
        float _toastTimer;
        float _lastSquareSide = -1f;

        // ---- Tween state ----------------------------------------------------

        readonly Tween _batteryPop = new Tween();
        readonly Tween _filmPop = new Tween();
        string _batteryText = string.Empty;
        int _filmCount = -1;
        bool _quiet;

        readonly Tween _heldSlide = new Tween();
        bool _heldShown;
        float _heldFromX;
        float _heldToX;

        readonly Tween _photoRise = new Tween();
        readonly Tween _photoTurn = new Tween();
        Vector2 _photoFrom;
        float _photoFromScale;
        float _photoTurnFrom;
        int _photoRoll;
        bool _photoShown;
        bool _photoRested;

        readonly Tween _ghost = new Tween();
        Vector2 _ghostFrom;
        Vector2 _ghostTo;
        float _ghostFromScale;
        float _ghostToScale;

        readonly Tween _brackets = new Tween();
        bool _viewfinderOn;

        readonly Tween _shutter = new Tween();
        readonly Tween _flash = new Tween();
        bool _flashed;
        float _shutterArmedUntil = -1f;

        bool _rewinding;
        float _rewindSpan;
        float _rewindFill;
        float _rewindPulseTime;

        GameState State
        {
            get { return GameState.Instance; }
        }

        void Awake()
        {
            Build();
        }

        void OnEnable()
        {
            State.BatteriesChanged += OnBatteriesChanged;
            State.FilmsChanged += OnFilmsChanged;
            State.LevelStarted += OnLevelStarted;
            // The counters must be right before the first event arrives, or the
            // HUD spends the opening moments of a level lying about the tally.
            // Primed QUIETLY: the pop of V-VFX-04 announces a change the player
            // caused, and there is nothing to announce about a starting value.
            _quiet = true;
            OnBatteriesChanged(State.CarriedBatteries, State.InsertedBatteries, State.RequiredBatteries);
            OnFilmsChanged(State.CameraFilms);
            _quiet = false;
        }

        void OnDisable()
        {
            State.BatteriesChanged -= OnBatteriesChanged;
            State.FilmsChanged -= OnFilmsChanged;
            State.LevelStarted -= OnLevelStarted;
        }

        void Update()
        {
            // Unscaled throughout, exactly like Fade below and for the same
            // reason: the HUD has to keep moving while the game is paused, while
            // a rewind is running the world backwards, and while anything else
            // has taken the timescale away.
            float dt = Time.unscaledDeltaTime;

            // The square depends on the viewport height, so it is re-derived
            // whenever the window changes rather than cached at build time. It
            // comes first because the picture tweens measure their travel in
            // squares.
            float side = SquareSide();
            if (!Mathf.Approximately(side, _lastSquareSide))
            {
                _lastSquareSide = side;
                LayoutSquare(side);
            }

            if (_bannerTimer > 0f)
            {
                _bannerTimer -= dt;
                // Fades in over the first two thirds of a second and out over the
                // last, exactly the curve of the original. V-ANIM-03 says the
                // banner keeps this curve, and V-HUD-07 says the same of the
                // 4.5 s, so this line is untouched by tier 5: everything the
                // item adds is written on CHILDREN of the group this alpha
                // drives, and a nested CanvasGroup multiplies. The rule and the
                // subtitle therefore arrive inside the pinned fade rather than
                // beside it, and when the banner leaves, it leaves as one.
                float alpha = Mathf.Clamp01(Mathf.Min(_bannerTimer, BannerSeconds - _bannerTimer) * 1.5f);
                _bannerGroup.alpha = alpha;
                StepBanner(BannerSeconds - _bannerTimer);
            }
            else if (_bannerGroup.alpha != 0f)
            {
                _bannerGroup.alpha = 0f;
            }

            StepToast(dt);
            // V-VFX-04's pop is written on the GLYPH of each counter and no
            // longer on its line of text, and the reason is the panel V-HUD-02
            // puts under both. A line that swells by a quarter inside a panel
            // sized to hold it is a line that leaves the panel for a fifth of a
            // second, which reads as the frame breaking rather than as the
            // number changing; the tween, its 0.2 s and its amplitude are
            // untouched, only what they are applied to moved. A 16 x 24 glyph
            // at 1.25 still sits inside the panel's own padding, and a number
            // that stays still at the instant it changes is a number that can
            // be read at the instant it changes.
            StepPop(_batteryPop, _batteryGlyph, dt);
            StepPop(_filmPop, _filmGlyph, dt);
            _promptFader.Step(dt);
            _filmFader.Step(dt);
            StepPrompt();
            StepCrosshair(dt);
            StepHeld(dt);
            StepHeldCard(dt);
            StepPicture(dt);
            StepGhost(dt);
            StepViewfinder(dt);
            StepShutter(dt);
            StepRewind(dt);
        }

        // ---- The one square both the picture and the viewfinder use ---------

        /// <summary>
        /// Side, in canvas units, of the screen region the placement frustum
        /// covers: the photo fov (50 degrees) inside the camera fov (75), both
        /// vertical.
        ///
        /// side = height * tan(photoFov / 2) / tan(cameraFov / 2)
        ///
        /// Derived from the two constants and never written as the resulting
        /// 0.6077, so the raised picture and the viewfinder cannot drift apart
        /// from each other or from the 3D frustum they are promising to show.
        /// </summary>
        float SquareSide()
        {
            float height = _canvasRect != null ? _canvasRect.rect.height : ReferenceResolution.y;
            float photoHalf = Mathf.Tan(PhotoMath.PhotoFovDeg * 0.5f * Mathf.Deg2Rad);
            float cameraHalf = Mathf.Tan(PlayerController.CameraFov * 0.5f * Mathf.Deg2Rad);
            return height * photoHalf / cameraHalf;
        }

        /// <summary>The last laid-out square, for the tweens that measure travel in it.</summary>
        float Side()
        {
            return _lastSquareSide > 0f ? _lastSquareSide : SquareSide();
        }

        void LayoutSquare(float side)
        {
            _photoViewRect.sizeDelta = new Vector2(side, side);
            // The picture and its departing ghost ARE the square. The tweens
            // move and scale them; they never resize them, so the resting
            // picture is always exactly the frustum's section.
            _pictureRect.sizeDelta = new Vector2(side, side);
            _ghostRect.sizeDelta = new Vector2(side, side);

            float half = side * 0.5f;
            // Four dim panels around the square. Anchored to the canvas centre so
            // the arithmetic is symmetric.
            SetCentered(_viewfinderDims[0], new Vector2(0f, half + ReferenceResolution.y), new Vector2(ReferenceResolution.x * 4f, ReferenceResolution.y * 2f));
            SetCentered(_viewfinderDims[1], new Vector2(0f, -half - ReferenceResolution.y), new Vector2(ReferenceResolution.x * 4f, ReferenceResolution.y * 2f));
            SetCentered(_viewfinderDims[2], new Vector2(-half - ReferenceResolution.x, 0f), new Vector2(ReferenceResolution.x * 2f, side));
            SetCentered(_viewfinderDims[3], new Vector2(half + ReferenceResolution.x, 0f), new Vector2(ReferenceResolution.x * 2f, side));

            // The 2 px outline, as four thin bars on the square's edges.
            SetCentered(_viewfinderEdges[0], new Vector2(0f, half), new Vector2(side, ViewfinderEdgePx));
            SetCentered(_viewfinderEdges[1], new Vector2(0f, -half), new Vector2(side, ViewfinderEdgePx));
            SetCentered(_viewfinderEdges[2], new Vector2(-half, 0f), new Vector2(ViewfinderEdgePx, side));
            SetCentered(_viewfinderEdges[3], new Vector2(half, 0f), new Vector2(ViewfinderEdgePx, side));

            // V-VFX-06's frosted rim: bands hugging the outside of the edge,
            // fading outward. OUTSIDE and not inside on purpose. The player is
            // lining up a shot through this square, and hazing the subject to
            // decorate the frame would be paying for the look with the thing the
            // look exists to serve.
            for (var band = 0; band < FrostBands; band++)
            {
                float inner = ViewfinderEdgePx * 0.5f + FrostBandPx * band;
                float centre = half + inner + FrostBandPx * 0.5f;
                float reach = inner + FrostBandPx;
                int at = band * 4;
                // The horizontal bands run the full outer width and the vertical
                // ones stop at the square, so no two bands overlap: overlapping
                // alpha would light the corners brighter than the sides.
                SetCentered(_viewfinderFrost[at + 0], new Vector2(0f, centre), new Vector2(side + reach * 2f, FrostBandPx));
                SetCentered(_viewfinderFrost[at + 1], new Vector2(0f, -centre), new Vector2(side + reach * 2f, FrostBandPx));
                SetCentered(_viewfinderFrost[at + 2], new Vector2(-centre, 0f), new Vector2(FrostBandPx, side));
                SetCentered(_viewfinderFrost[at + 3], new Vector2(centre, 0f), new Vector2(FrostBandPx, side));
            }

            // Corner brackets: a dark stroke UNDER a white one, because they have
            // to read against a bright sky as well as against the ground.
            float arm = side * BracketArmFraction;
            var index = 0;
            for (var cx = 0; cx < 2; cx++)
            {
                for (var cy = 0; cy < 2; cy++)
                {
                    float sx = cx == 0 ? -1f : 1f;
                    float sy = cy == 0 ? -1f : 1f;
                    var corner = new Vector2(half * sx, half * sy);
                    for (var pass = 0; pass < 2; pass++)
                    {
                        float thickness = pass == 0 ? BracketDarkPx : BracketLightPx;
                        SetCentered(_viewfinderBrackets[index++],
                            corner + new Vector2(-sx * arm * 0.5f, 0f),
                            new Vector2(arm, thickness));
                        SetCentered(_viewfinderBrackets[index++],
                            corner + new Vector2(0f, -sy * arm * 0.5f),
                            new Vector2(thickness, arm));
                    }
                }
            }
        }

        // ---- The API Main drives --------------------------------------------

        /// <summary>
        /// Shows or hides the overlay. Disables the CANVAS and never the
        /// GameObject: deactivating the object would kill the fade coroutine a
        /// level load has just started, and would re-run OnEnable (and so
        /// re-subscribe the counters) on every menu toggle. The tweens keep
        /// running while it is off, for the same reason: a HUD that comes back
        /// mid animation is right, a HUD stuck half way is not.
        /// </summary>
        public void SetVisible(bool visible)
        {
            if (_canvas != null && _canvas.enabled != visible)
            {
                _canvas.enabled = visible;
            }
        }

        /// <summary>
        /// The interaction prompt. V-ANIM-03 fades it in over 0.12 s and out
        /// over 0.2 s, so an empty string starts the fade instead of blanking
        /// the label: the words have to stay readable while they leave.
        ///
        /// V-HUD-03 asks that the key be "prefixed with a key-cap glyph" while
        /// "the French string after the key-cap is unchanged", and the callers
        /// hand this method ONE string that already contains the key
        /// ("E : ramasser la pile"). The split is therefore made HERE, on the
        /// string, and never in the callers: PlayerController and every
        /// IInteractable keep writing exactly the prompt they always wrote, the
        /// smoke probe keeps reading that same string off PlayerController, and
        /// only the DRAWING of it is in two pieces. <see cref="SplitPromptKey"/>
        /// takes the key, the cap draws it, and the label draws the remainder
        /// character for character.
        ///
        /// What the screen loses is the " : " between the two, which is what a
        /// cap is FOR: the item pins "the French string after the key-cap" and
        /// that is what survives. A prompt with no key ("Il manque 2 piles") or
        /// whose head is a sentence and not a key ("Mains pleines : posez...")
        /// keeps every character and shows no cap.
        /// </summary>
        public void SetPrompt(string text)
        {
            string wanted = text ?? string.Empty;
            if (wanted.Length == 0)
            {
                _promptFader.Hide(PromptOutSeconds);
                return;
            }
            if (_promptText != wanted)
            {
                _promptText = wanted;
                string key;
                string rest;
                bool capped = SplitPromptKey(wanted, out key, out rest);
                _promptLabel.text = rest;
                _promptCapLabel.text = capped ? key : string.Empty;
                if (_promptCap.gameObject.activeSelf != capped)
                {
                    _promptCap.gameObject.SetActive(capped);
                }
            }
            _promptFader.Show(PromptInSeconds);
        }

        /// <summary>
        /// Lifts the key off the front of a prompt WITHOUT editing the prompt.
        /// True when the text opens on a key and a colon, in which case the key
        /// and the rest of the sentence come back separately and
        /// <c>key + " : " + rest</c> is the argument byte for byte.
        ///
        /// The two guards are what keep a sentence from being mistaken for a
        /// key. A head longer than three characters is not a key ("F11" is the
        /// longest this game has), and a head containing a space is a phrase:
        /// "Mains pleines : posez (clic gauche) ou reposez (F) votre photo"
        /// fails both and is drawn whole, which is right, because there is no
        /// key to press in it.
        /// </summary>
        static bool SplitPromptKey(string text, out string key, out string rest)
        {
            key = string.Empty;
            rest = text;
            int at = text.IndexOf(KeySeparator, System.StringComparison.Ordinal);
            if (at <= 0 || at > KeyCapMaxChars)
            {
                return false;
            }
            string head = text.Substring(0, at);
            if (head.IndexOf(' ') >= 0)
            {
                return false;
            }
            key = head;
            rest = text.Substring(at + KeySeparator.Length);
            return true;
        }

        /// <summary>
        /// Shows the raised picture over the exact screen region the placement
        /// frustum covers, turned by the held roll. Null hides it.
        ///
        /// ONE STEP READS CLOCKWISE, on the HUD and in the world. In Unity a
        /// positive z euler turns counter-clockwise on screen, so the sign is
        /// negative here. The original had the HUD clockwise and the world
        /// counter-clockwise for twenty-five levels; they agreed at 0 and 180
        /// and nowhere else, which is why nobody noticed.
        ///
        /// V-ANIM-04 animates this and changes NOTHING about the two lines that
        /// matter. The PhotoView rect is the anchor: it appears, disappears and
        /// takes the roll on the frame Main hands it over, because that is what
        /// the smoke probe reads (it walks "HudCanvas/PhotoView" by path and
        /// asserts activeInHierarchy, a pivot of 0.5 and a local z of exactly
        /// -90 three frames after one wheel step). The animation lives on the
        /// Picture child under it, which carries the residual offset, scale and
        /// roll and decays them to nothing. Composed, the two always agree with
        /// the placer at rest.
        /// </summary>
        public void SetPhotoView(Texture2D texture, int rollSteps = 0)
        {
            bool visible = texture != null;
            if (!visible)
            {
                if (_photoShown)
                {
                    _photoShown = false;
                    // V-HUD-05: the ring comes back with the frame it left.
                    ApplyCrosshair();
                    // The reverse of the raise (V-ANIM-04) is played by a GHOST
                    // copy, never by this rect: the probe requires the picture
                    // to be gone from the HUD three frames after a placement,
                    // and an animation that kept the real widget alive for
                    // 0.18 s would be an animation gating a fact.
                    StartLower();
                }
                if (_photoViewRect.gameObject.activeSelf)
                {
                    _photoViewRect.gameObject.SetActive(false);
                }
                return;
            }

            if (!_photoViewRect.gameObject.activeSelf)
            {
                _photoViewRect.gameObject.SetActive(true);
            }
            _photoView.texture = texture;

            int previous = _photoRoll;
            _photoRoll = rollSteps;
            _photoViewRect.localRotation = Quaternion.Euler(0f, 0f, -90f * rollSteps);

            if (!_photoShown)
            {
                _photoShown = true;
                // V-HUD-05: the square in front of the eye is the frame now, so
                // the ring collapses into the dot.
                ApplyCrosshair();
                StartRise();
            }
            else if (rollSteps != previous)
            {
                StartTurn(previous, rollSteps);
            }
        }

        public void SetViewfinder(bool active)
        {
            if (active == _viewfinderOn)
            {
                return;
            }
            _viewfinderOn = active;
            // V-HUD-05: the reticle is the viewfinder's crosshair.
            ApplyCrosshair();
            if (active)
            {
                // Frame one already has the brackets out at the corners, so the
                // first thing the eye sees is the travel and not a flash at
                // rest (V-VFX-06).
                _brackets.Start(ViewfinderInSeconds);
                _bracketRoot.localScale = new Vector3(BracketFromScale, BracketFromScale, 1f);
                _viewfinderFader.Show(ViewfinderInSeconds);
            }
            else
            {
                _viewfinderFader.Hide(ViewfinderOutSeconds);
            }
        }

        /// <summary>
        /// The shutter of V-VFX-06, called by the capture the moment it
        /// succeeds. PRESENTATION ONLY: it gates nothing, returns nothing and
        /// is safe from anywhere, at any timescale, including while paused. It
        /// does two things: it shuts two black leaves over the frame and opens
        /// them again in 0.12 s with a white flash frame between, and it arms
        /// the next picture that arrives in hand to slide up out of the camera
        /// (0.35 s) instead of rising from the held card (0.18 s). Calling it
        /// twice restarts it.
        /// </summary>
        public void PlayShutter()
        {
            _shutterArmedUntil = Time.unscaledTime + ShutterArmSeconds;
            _shutter.Start(ShutterCloseSeconds + ShutterOpenSeconds);
            _flash.Snap();
            _flashed = false;
            _shutterFlash.color = new Color(1f, 1f, 1f, 0f);
            _shutterTop.sizeDelta = new Vector2(0f, 0f);
            _shutterBottom.sizeDelta = new Vector2(0f, 0f);
            if (!_shutterRoot.gameObject.activeSelf)
            {
                _shutterRoot.gameObject.SetActive(true);
            }
        }

        /// <summary>
        /// The held-photo panel. The card steps aside while the photo is raised:
        /// the full picture in front of the player replaces it.
        ///
        /// V-ANIM-03 slides the panel in from the right over 0.2 s and out the
        /// same way, so the panel object outlives the empty title by the length
        /// of one slide. It carries no state anyone reads, which is why it may.
        /// </summary>
        public void SetHeld(string title, Texture2D texture, bool raised)
        {
            bool holding = !string.IsNullOrEmpty(title);
            if (holding != _heldShown)
            {
                _heldShown = holding;
                if (holding && !_heldPanel.gameObject.activeSelf)
                {
                    _heldPanel.gameObject.SetActive(true);
                }
                _heldFromX = _heldPanel.anchoredPosition.x;
                _heldToX = holding ? -HeldMarginPx : HeldHiddenX;
                _heldSlide.Start(HeldSlideSeconds);
                // Stepped by zero right away so the panel is already at the
                // start of its slide. Nothing orders Main's Update against this
                // one, and without it a show could draw one frame at rest
                // before the slide takes over.
                StepHeld(0f);
            }
            if (!holding)
            {
                return;
            }
            _heldTitle.text = "Photo : « " + title + " »";

            // V-ANIM-03: "no HUD element appears or vanishes in one frame", and
            // this card was the exception. Main pushes `raised` EVERY frame, so
            // blanking the texture on the frame the player right-clicks made the
            // card and its shadow disappear instantly while the ghost copy was
            // still 0.18 s from landing on the raised picture - a pop at both
            // ends of a handoff that the ghost exists to make continuous.
            //
            // The texture is HELD rather than cleared, so the card still has
            // something to draw while it fades, and it is only released once the
            // fade has fully landed (StepHeldCard). CardRaiseFadeSeconds matches
            // the raise's own duration so the card leaves exactly as the picture
            // arrives.
            bool wantCard = texture != null && !raised;
            if (texture != null)
            {
                _heldCardTexture = texture;
            }
            float wantAlpha = wantCard ? 1f : 0f;
            if (!Mathf.Approximately(wantAlpha, _heldCardToA))
            {
                _heldCardFromA = _heldCard.color.a;
                _heldCardToA = wantAlpha;
                _heldCardFade.Start(CardRaiseFadeSeconds);
            }
            StepHeldCard(0f);
        }

        /// <summary>
        /// The rewind wash, its label and, since V-HUD-06, a thin amber bar
        /// under the label that shrinks as the history is spent.
        ///
        /// THE LABEL STRING IS UNTOUCHED: PRD 12 pins it, invariant culture and
        /// all. The bar is normalized against the history the player HAD when
        /// they started holding R, not against the five-minute ceiling of
        /// Rewind.MaxSamples, because a bar that reads full for four minutes of
        /// a five minute buffer tells nobody anything. Normalized that way it
        /// always starts full and always empties exactly when the history runs
        /// out, which is the one fact the player needs.
        /// </summary>
        public void SetRewinding(bool active, float secondsLeft)
        {
            if (active && !_rewinding)
            {
                _rewindSpan = Mathf.Max(secondsLeft, 0f);
                _rewindPulseTime = 0f;
            }
            _rewinding = active;
            if (active)
            {
                _rewindFader.Show(RewindInSeconds);
                _rewindLabel.text = string.Format(
                    System.Globalization.CultureInfo.InvariantCulture,
                    "REMBOBINAGE   {0:0.0} s d'historique", secondsLeft);
                _rewindFill = _rewindSpan > 0.001f
                    ? Mathf.Clamp01(secondsLeft / _rewindSpan)
                    : 0f;
            }
            else
            {
                _rewindFader.Hide(RewindOutSeconds);
            }
        }

        /// <summary>
        /// The level banner. The 4.5 s and the alpha curve are pinned by PRD
        /// 12.1 and V-HUD-07 repeats it, so neither is touched here.
        ///
        /// The rule line is measured against the TITLE that was just set rather
        /// than given a width of its own, because a rule that is wider than the
        /// words it belongs to reads as a divider between two things. Asking
        /// the Text for its preferred width is what makes "Niveau 3 : L'arche"
        /// and "Niveau 19 : Le grand escalier suspendu" both come out looking
        /// deliberate; the clamp covers the headless case, where there is no
        /// font and the answer is zero.
        /// </summary>
        public void ShowBanner(string title, string subtitle)
        {
            _bannerTitle.text = title ?? string.Empty;
            _bannerSubtitle.text = subtitle ?? string.Empty;
            _bannerRuleWidth = Mathf.Clamp(
                _bannerTitle.preferredWidth + BannerRuleMarginPx * 2f,
                BannerRuleMinPx, BannerRuleMaxPx);
            _bannerTimer = BannerSeconds;
            // Nothing on this HUD appears in one frame (V-ANIM-03), so the rule
            // and the subtitle start at nothing and are stepped from here on.
            StepBanner(0f);
        }

        public void ShowToast(string text)
        {
            _toastLabel.text = text ?? string.Empty;
            _toastLabel.gameObject.SetActive(true);
            _toastGroup.alpha = 0f;
            _toastTimer = ToastSeconds;
        }

        /// <summary>
        /// Fades to the fall colour over 0.6 s. Yield on it to wait for the
        /// black. The duration is pinned by the gameplay PRD.
        /// </summary>
        public IEnumerator FadeOut()
        {
            yield return Fade(1f, FadeColor);
        }

        /// <summary>
        /// Fades out to a chosen colour, for V-POST-06: departing a level fades
        /// to <see cref="FadeWhite"/> and falling to <see cref="FadeBlack"/>.
        /// The 0.6 s is the same 0.6 s; only the colour is the caller's.
        /// </summary>
        public IEnumerator FadeOut(Color color)
        {
            yield return Fade(1f, color);
        }

        /// <summary>
        /// Fades the screen back in, keeping whatever colour is currently on it.
        /// That is what this always did (the colour could only ever be one), and
        /// it is what a caller wants now that there are two: a level that
        /// departed into white must come back OUT of white, not cut to it.
        /// </summary>
        public void FadeIn()
        {
            StartCoroutine(Fade(0f, _fade.color));
        }

        /// <summary>Fades in from a chosen colour.</summary>
        public void FadeIn(Color color)
        {
            StartCoroutine(Fade(0f, color));
        }

        IEnumerator Fade(float target, Color color)
        {
            Color from = _fade.color;
            float start = from.a;
            // The colour is crossfaded only when there is something on screen to
            // crossfade. Starting from a clear screen, the new colour is adopted
            // at once: lerping the rgb from an invisible black to white would
            // wash the frame through grey for no reason.
            Color rgbFrom = start <= 0.001f ? color : from;
            float elapsed = 0f;
            while (elapsed < FadeSeconds)
            {
                // Unscaled: a fade must finish even if something has stopped time.
                elapsed += Time.unscaledDeltaTime;
                float k = Mathf.Clamp01(elapsed / FadeSeconds);
                Color rgb = Color.Lerp(rgbFrom, color, k);
                _fade.color = new Color(rgb.r, rgb.g, rgb.b, Mathf.Lerp(start, target, k));
                yield return null;
            }
            _fade.color = new Color(color.r, color.g, color.b, target);
        }

        /// <summary>
        /// Reopens the quiet window for a level start, so the counters change
        /// without popping.
        ///
        /// OnEnable's priming is not enough on its own, and the gap is easy to
        /// miss: GameState.BeginLevel re-raises BOTH counter events on every
        /// LoadLevel, long after OnEnable ran, and the battery line always
        /// differs across a level boundary (level k ends "Teleporteur : N / N"
        /// and level k+1 opens "0 / M"), so the early-out on an unchanged
        /// string never catches it. The pop of V-VFX-04 exists to announce a
        /// change THE PLAYER CAUSED; firing it on every level start, and after
        /// every fall, announces a pickup that never happened.
        ///
        /// One frame is the right length. BeginLevel raises films, then this,
        /// then batteries, all in the same call stack, so clearing the flag at
        /// the end of the frame covers the counter events of the level start
        /// and nothing the player could have caused since.
        /// </summary>
        void OnLevelStarted(int index)
        {
            _quiet = true;
            StartCoroutine(EndQuietWindow());
        }

        IEnumerator EndQuietWindow()
        {
            yield return null;
            _quiet = false;
        }

        void OnBatteriesChanged(int carried, int inserted, int required)
        {
            string text = string.Format(
                "Piles : {0} portee{1}   |   Teleporteur : {2} / {3}",
                carried, carried > 1 ? "s" : "", inserted, required);
            if (_batteryText == text)
            {
                return;
            }
            _batteryText = text;
            _batteryLabel.text = text;
            if (!_quiet)
            {
                // V-VFX-04: the counter pops when it changes, so a pickup is felt
                // without reading the line.
                _batteryPop.Start(CounterPopSeconds);
            }
        }

        void OnFilmsChanged(int films)
        {
            bool visible = films > 0;
            if (visible)
            {
                _filmLabel.text = "Pellicule : " + films
                    + "   (clic droit : viser   clic gauche : declencher)";
                _filmFader.Show(PromptInSeconds);
            }
            else
            {
                _filmFader.Hide(PromptOutSeconds);
            }
            if (films != _filmCount)
            {
                _filmCount = films;
                if (visible && !_quiet)
                {
                    _filmPop.Start(CounterPopSeconds);
                }
            }
        }

        // ---- Stepping the tweens --------------------------------------------

        /// <summary>
        /// The toast's 2.2 s are pinned by PRD 12.1, so V-ANIM-03's rise and
        /// fade are cut OUT of that window rather than added to it: it climbs
        /// 12 px over the first 0.18 s and fades over the last 0.25 s, and it
        /// still leaves at 2.2 s exactly.
        /// </summary>
        void StepToast(float dt)
        {
            if (_toastTimer <= 0f)
            {
                return;
            }
            _toastTimer -= dt;
            if (_toastTimer <= 0f)
            {
                _toastLabel.gameObject.SetActive(false);
                return;
            }
            float age = ToastSeconds - _toastTimer;
            float rise = EaseOut(Mathf.Clamp01(age / ToastInSeconds));
            float leave = Mathf.Clamp01(_toastTimer / ToastOutSeconds);
            _toastGroup.alpha = Mathf.Min(rise, leave);
            _toastLabel.rectTransform.anchoredPosition =
                new Vector2(0f, ToastBottomPx - ToastRisePx * (1f - rise));
        }

        /// <summary>
        /// The counter pop (V-VFX-04). Applied to the counter's GLYPH since
        /// V-HUD-02 put a panel under both lines: a rect inside a layout group
        /// has a centred pivot, so the glyph swells about its own middle, the
        /// layout ignores scale and nothing around it moves. See the call in
        /// Update for why the line of text is no longer what pops.
        /// </summary>
        static void StepPop(Tween pop, RectTransform rect, float dt)
        {
            if (!pop.Step(dt))
            {
                return;
            }
            float scale = 1f + CounterPopScale * Pop(pop.Cursor);
            rect.localScale = new Vector3(scale, scale, 1f);
        }

        void StepPrompt()
        {
            // Cleared only once the words have actually finished leaving. The
            // cached string goes with them, so the next prompt is split again
            // rather than compared against a line that is no longer drawn.
            if (_promptFader.Hidden && _promptText.Length > 0)
            {
                _promptText = string.Empty;
                _promptLabel.text = string.Empty;
                _promptCapLabel.text = string.Empty;
                if (_promptCap.gameObject.activeSelf)
                {
                    _promptCap.gameObject.SetActive(false);
                }
            }
        }

        /// <summary>
        /// V-HUD-05's three states, which are not three widgets but one dot and
        /// two things that come and go around it.
        ///
        /// The dot is the aim point and never moves: it is what the placement
        /// ray actually reads, so it is the one part of the crosshair that may
        /// not be animated away. The ring collapses INTO it while a picture is
        /// raised (the raised square is the frame then, and a ring inside a
        /// frame is two frames), and the reticle takes its place while the
        /// viewfinder is up. The ring's scale is driven off its own group alpha
        /// rather than off a second tween, so the shrink and the fade cannot
        /// come apart.
        /// </summary>
        void StepCrosshair(float dt)
        {
            _crosshairRingFader.Step(dt);
            _crosshairReticleFader.Step(dt);
            float k = Mathf.Lerp(CrosshairShrink, 1f, _crosshairRingGroup.alpha);
            _crosshairRing.localScale = new Vector3(k, k, 1f);
        }

        /// <summary>
        /// Picks the crosshair's state from the two facts that decide it. Called
        /// from both of the places that can change one of them, never from
        /// Update: the state is instant truth, and only the travel between
        /// states is animated.
        /// </summary>
        void ApplyCrosshair()
        {
            if (_crosshairRingFader == null)
            {
                return;
            }
            if (_viewfinderOn)
            {
                _crosshairReticleFader.Show(CrosshairFadeSeconds);
                _crosshairRingFader.Hide(CrosshairFadeSeconds);
                return;
            }
            _crosshairReticleFader.Hide(CrosshairFadeSeconds);
            if (_photoShown)
            {
                _crosshairRingFader.Hide(CrosshairFadeSeconds);
            }
            else
            {
                _crosshairRingFader.Show(CrosshairFadeSeconds);
            }
        }

        /// <summary>
        /// V-HUD-07's rule and delayed subtitle, both written as functions of
        /// the banner's OWN age so that neither can drift from the 4.5 s the
        /// PRD pins. The rule grows outward from the centre because its rect is
        /// centred and only its width changes; the subtitle's ramp multiplies
        /// with the banner's pinned curve rather than replacing it.
        /// </summary>
        void StepBanner(float age)
        {
            float grow = EaseOut(Mathf.Clamp01(age / BannerRuleSeconds));
            _bannerRule.sizeDelta = new Vector2(_bannerRuleWidth * grow, BannerRuleHeightPx);
            _bannerSubtitleGroup.alpha =
                Mathf.Clamp01((age - BannerSubtitleDelay) / BannerSubtitleFade);
        }

        /// <summary>
        /// Fades the held card and its shadow between the panel and the raised
        /// picture. The texture is released only when the card has finished
        /// fading OUT, because a card with no texture draws nothing and would
        /// bring back the very pop this fade removes.
        /// </summary>
        void StepHeldCard(float dt)
        {
            _heldCardFade.Step(dt);
            float a = Mathf.Lerp(_heldCardFromA, _heldCardToA, _heldCardFade.Cursor);

            bool visible = a > 0.001f && _heldCardTexture != null;
            _heldCard.Texture = visible ? _heldCardTexture : null;
            _heldCardShadow.Visible = visible;

            Color c = _heldCard.color;
            _heldCard.color = new Color(c.r, c.g, c.b, a);
            Color sc = _heldCardShadow.color;
            _heldCardShadow.color = new Color(sc.r, sc.g, sc.b, a);

            if (_heldCardFade.Done && _heldCardToA <= 0f)
            {
                _heldCardTexture = null;
            }
        }

        void StepHeld(float dt)
        {
            if (_heldSlide.Step(dt))
            {
                float x = Mathf.LerpUnclamped(_heldFromX, _heldToX, EaseOut(_heldSlide.Cursor));
                _heldPanel.anchoredPosition = new Vector2(x, HeldMarginPx);
                return;
            }
            if (!_heldShown && _heldPanel.gameObject.activeSelf)
            {
                _heldPanel.gameObject.SetActive(false);
            }
        }

        /// <summary>
        /// V-ANIM-04, the raise and the turn. Both are departures from rest
        /// written on the Picture child, so when both are done the child is at
        /// identity and the picture on screen is exactly the anchor's instant
        /// roll: "the on-screen picture and the placer's roll agree at the end
        /// of every tween".
        /// </summary>
        void StepPicture(float dt)
        {
            bool rising = _photoRise.Step(dt);
            bool turning = _photoTurn.Step(dt);
            if (!rising && !turning && _photoRested)
            {
                return;
            }

            // Unclamped, because the back-out easing goes past 1 on purpose and
            // Mathf.Lerp would eat the overshoot.
            float k = _photoRise.Done ? 1f : EaseOutBack(_photoRise.Cursor);
            Vector2 offset = Vector2.LerpUnclamped(_photoFrom, Vector2.zero, k);
            float scale = Mathf.LerpUnclamped(_photoFromScale, 1f, k);
            float turn = _photoTurn.Done
                ? 0f
                : Mathf.LerpUnclamped(_photoTurnFrom, 0f, EaseOut(_photoTurn.Cursor));

            // The offset is chosen in canvas axes (the card is bottom right of
            // the SCREEN), but this rect hangs under the anchor, which already
            // carries the roll. Without turning the offset back into the rolled
            // frame, a picture held sideways would slide in from the side the
            // roll points at instead of from the card.
            _pictureRect.anchoredPosition = QuarterTurns(_photoRoll, offset);
            _pictureRect.localScale = new Vector3(scale, scale, 1f);
            _pictureRect.localRotation = Quaternion.Euler(0f, 0f, turn);
            _photoRested = _photoRise.Done && _photoTurn.Done;
        }

        void StepGhost(float dt)
        {
            if (_ghost.Step(dt))
            {
                float k = EaseOut(_ghost.Cursor);
                _ghostRect.anchoredPosition = Vector2.LerpUnclamped(_ghostFrom, _ghostTo, k);
                float scale = Mathf.LerpUnclamped(_ghostFromScale, _ghostToScale, k);
                _ghostRect.localScale = new Vector3(scale, scale, 1f);
                _ghostGroup.alpha = 1f - k;
                return;
            }
            if (_ghostRect.gameObject.activeSelf)
            {
                _ghostRect.gameObject.SetActive(false);
            }
        }

        void StepViewfinder(float dt)
        {
            _viewfinderFader.Step(dt);
            if (_brackets.Step(dt))
            {
                float scale = Mathf.LerpUnclamped(BracketFromScale, 1f, EaseOut(_brackets.Cursor));
                _bracketRoot.localScale = new Vector3(scale, scale, 1f);
            }
        }

        void StepShutter(float dt)
        {
            bool leaves = _shutter.Step(dt);
            bool flashing = _flash.Step(dt);
            if (leaves)
            {
                float total = ShutterCloseSeconds + ShutterOpenSeconds;
                float t = _shutter.Cursor * total;
                float closed;
                if (t <= ShutterCloseSeconds)
                {
                    closed = t / ShutterCloseSeconds;
                }
                else
                {
                    closed = 1f - (t - ShutterCloseSeconds) / ShutterOpenSeconds;
                    if (!_flashed)
                    {
                        // The white frame fires at the closed instant, over the
                        // leaves rather than under them, which is what makes it
                        // read as light and not as a hole in the shutter.
                        _flashed = true;
                        _flash.Start(ShutterFlashSeconds);
                        _shutterFlash.color = Color.white;
                        flashing = true;
                    }
                }
                float reach = (_canvasRect.rect.height * 0.5f + 2f) * Mathf.Clamp01(closed);
                _shutterTop.sizeDelta = new Vector2(0f, reach);
                _shutterBottom.sizeDelta = new Vector2(0f, reach);
            }
            if (flashing)
            {
                _shutterFlash.color = new Color(1f, 1f, 1f, 1f - EaseOut(_flash.Cursor));
            }
            if (!leaves && !flashing && _shutterRoot.gameObject.activeSelf)
            {
                _shutterRoot.gameObject.SetActive(false);
            }
        }

        void StepRewind(float dt)
        {
            _rewindFader.Step(dt);
            if (_rewindFader.Hidden)
            {
                return;
            }
            _rewindPulseTime += dt;
            // A bright snap and a slow decay, over and over. See the constant.
            float phase = Mathf.Repeat(_rewindPulseTime, RewindPulseSeconds) / RewindPulseSeconds;
            _rewindPulse.alpha = Mathf.Lerp(1f, RewindPulseFloor, phase);
            _rewindBarFill.sizeDelta = new Vector2(RewindBarWidthPx * _rewindFill, RewindBarHeightPx);
        }

        // ---- Starting the picture tweens ------------------------------------

        void StartRise()
        {
            float side = Side();
            if (Time.unscaledTime <= _shutterArmedUntil)
            {
                // V-VFX-06: a picture that has just been taken is pulled out of
                // the camera, so it comes up through the bottom of the frame.
                _shutterArmedUntil = -1f;
                _photoFrom = new Vector2(0f, -(side * 0.5f + PhotoPullBelowPx));
                _photoFromScale = PhotoPullScale;
                _photoRise.Start(PhotoPullSeconds);
            }
            else
            {
                _photoFrom = CardOffset(side);
                _photoFromScale = CardScale(side);
                _photoRise.Start(PhotoRaiseSeconds);
            }
            _photoTurn.Snap();
            _photoRested = false;
            // Placed at the start of its travel at once, for the same reason the
            // panel is: this can run either side of Update.
            StepPicture(0f);
        }

        void StartTurn(int previous, int now)
        {
            // Whatever of the previous turn has not been walked yet is carried
            // over, so spinning the wheel twice quickly is one continuous
            // movement instead of a restart.
            float already = _photoTurn.Done
                ? 0f
                : Mathf.LerpUnclamped(_photoTurnFrom, 0f, EaseOut(_photoTurn.Cursor));
            // The SHORT way round. RollSteps wraps 3 to 0, and the long way
            // would spin the picture three quarters backwards for one wheel
            // step. DeltaAngle from the new angle to the old one is exactly the
            // residual the picture still has to travel.
            _photoTurnFrom = Mathf.DeltaAngle(-90f * now, -90f * previous) + already;
            _photoTurn.Start(PhotoTurnSeconds);
            _photoRested = false;
            // The anchor took the new roll one line ago, so without this the
            // picture could show a single frame already turned before the tween
            // walks it back to where it was.
            StepPicture(0f);
        }

        /// <summary>
        /// Plays the raise backwards on a copy, because the real widget has
        /// already gone (see <see cref="SetPhotoView"/>). It fades as it goes:
        /// the picture leaves for two different reasons (lowered back to the
        /// hand, or spent by a placement) and only one of them has a card left
        /// to land on, so the copy heads for the card when the hand is still
        /// full and drops out of frame when it is not.
        /// </summary>
        void StartLower()
        {
            float side = Side();
            float turn = _photoTurn.Done
                ? 0f
                : Mathf.LerpUnclamped(_photoTurnFrom, 0f, EaseOut(_photoTurn.Cursor));

            _ghostView.texture = _photoView.texture;
            _ghostRect.localRotation = Quaternion.Euler(0f, 0f, -90f * _photoRoll + turn);
            // Back out of the rolled frame: the ghost hangs under the canvas and
            // travels in canvas axes.
            _ghostFrom = QuarterTurns(-_photoRoll, _pictureRect.anchoredPosition);
            _ghostFromScale = _pictureRect.localScale.x;
            if (_heldShown)
            {
                _ghostTo = CardOffset(side);
                _ghostToScale = CardScale(side);
            }
            else
            {
                _ghostTo = new Vector2(0f, -(side * 0.5f + PhotoPullBelowPx));
                _ghostToScale = PhotoPullScale;
            }
            _ghost.Start(PhotoLowerSeconds);
            _ghostGroup.alpha = 1f;
            if (!_ghostRect.gameObject.activeSelf)
            {
                _ghostRect.gameObject.SetActive(true);
            }
            // Placed where the real picture just was, before anything can draw
            // it: the copy has to take over invisibly or the handover reads as a
            // jump.
            StepGhost(0f);
        }

        /// <summary>
        /// Where the held card sits, in canvas units from the centre. ASKED of
        /// the card rather than rebuilt from PRD 12.1's margins: the panel's own
        /// slide and its layout group both move it, and a copied offset would be
        /// wrong the moment either changes.
        /// </summary>
        Vector2 CardOffset(float side)
        {
            if (_heldShown && _heldCard != null && _canvasRect != null)
            {
                return _canvasRect.InverseTransformPoint(_heldCard.rectTransform.position);
            }
            return new Vector2(0f, -(side * 0.5f + PhotoPullBelowPx));
        }

        static float CardScale(float side)
        {
            return Mathf.Clamp(PhotoCardGeometry.CardSize / Mathf.Max(side, 1f), 0.02f, 1f);
        }

        // ---- Construction ---------------------------------------------------

        void Build()
        {
            var canvasObject = new GameObject("HudCanvas", typeof(RectTransform));
            canvasObject.transform.SetParent(transform, false);

            Canvas canvas = canvasObject.AddComponent<Canvas>();
            _canvas = canvas;
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = SortingOrder;

            CanvasScaler scaler = canvasObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = ReferenceResolution;
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
            scaler.matchWidthOrHeight = 1f; // 1 = height, see the class comment.

            // No GraphicRaycaster: nothing on the HUD is clickable, and one here
            // would quietly compete with the menu for the pointer.
            _canvasRect = canvasObject.GetComponent<RectTransform>();
            Transform root = canvasObject.transform;

            // Every glyph the widgets below hang on an Image is painted first
            // and then never again (PRD_VISUAL 3.2 as amended allows the font
            // and the CC0 texture sets and nothing else, so all of this is
            // code). Five small textures here and three rounded corners on
            // demand, under 150 KB together, and nothing in Update ever touches
            // a pixel of any of them.
            PaintArt();

            BuildCrosshair(root);
            BuildCounters(root);
            BuildPhotoView(root);
            BuildViewfinder(root);
            BuildPrompt(root);
            BuildHeldPanel(root);
            BuildBanner(root);
            BuildToast(root);
            BuildRewind(root);
            BuildShutter(root);
            BuildFade(root);

            LayoutSquare(SquareSide());
        }

        /// <summary>
        /// V-HUD-05's crosshair: a ring, a dot and a reticle, all three painted
        /// here (rule 4) and none of them ever rebuilt.
        ///
        /// The three rects are siblings and the dot is drawn LAST, so it stays
        /// on top of whichever of the other two is up. PRD 12.1's 5 x 5 square
        /// is gone, which is the item; its white at 85 percent is not, and all
        /// three share it.
        /// </summary>
        void BuildCrosshair(Transform root)
        {
            RectTransform group = NewRect("Crosshair", root);
            SetCentered(group, Vector2.zero, new Vector2(CrosshairReticlePx, CrosshairReticlePx));

            _crosshairRing = NewRect("Ring", group);
            SetCentered(_crosshairRing, Vector2.zero, RingSpriteSizePx());
            NewGlyph(_crosshairRing, _ringSprite, CrosshairColor);
            _crosshairRingGroup = NewGroup(_crosshairRing.gameObject);
            // The ring is the resting state, so it is the one thing on this HUD
            // that starts shown. Everything else a Fader owns starts parked.
            _crosshairRingGroup.alpha = 1f;
            _crosshairRingFader = new Fader(_crosshairRingGroup);

            RectTransform reticle = NewRect("Reticle", group);
            SetCentered(reticle, Vector2.zero,
                new Vector2(CrosshairReticlePx, CrosshairReticlePx));
            NewGlyph(reticle, _reticleSprite, CrosshairColor);
            // No field for this group: only the ring's alpha is read back
            // (StepCrosshair drives the shrink off it), and the reticle's is
            // the Fader's business alone.
            _crosshairReticleFader = new Fader(NewGroup(reticle.gameObject));
            reticle.gameObject.SetActive(false);

            RectTransform dot = NewRect("Dot", group);
            SetCentered(dot, Vector2.zero,
                new Vector2(CrosshairDotPx * 2f, CrosshairDotPx * 2f));
            NewGlyph(dot, _dotSprite, CrosshairColor);
        }

        /// <summary>
        /// V-HUD-02: the two counters, their glyphs and the panel they now lie
        /// on. Three decisions are worth writing down.
        ///
        /// WHERE THE PANEL SITS. PRD 12.1 puts the battery line's top left at
        /// (24, 20) and the film line's at (24, 52). Those offsets belong to
        /// LABELS, and this item replaces the labels with a panel, so the panel
        /// is placed by its padding instead: its corner goes at (24 - padX,
        /// 20 - padY), which lands the first row's glyph exactly on the pinned
        /// (24, 20) and the second row's within 2 px of the pinned (24, 52).
        /// The numbers of 12.1 are therefore still describing what is on
        /// screen, with the glyph occupying the position the line used to and
        /// the words following it.
        ///
        /// WHY IT IS FITTED AND NOT SIZED. The film row only exists while the
        /// player carries film, and a panel left at its two-row height would
        /// have an empty half on most levels. A ContentSizeFitter over a
        /// vertical layout costs one rebuild on the frame the row appears or
        /// leaves, and the Fader already deactivates that row, which is exactly
        /// what a layout group ignores.
        ///
        /// WHAT THE PANEL BUYS THE LABELS. Both lines lose the four-sided
        /// contour they needed over bare sky and take the lighter
        /// TextEdge.Shadow, which is the "cleaner look" V-HUD-01 asked for and
        /// could not have while these two floated on the world.
        ///
        /// TWO CLAUSES OF V-HUD-02 ARE NOT HONOURED, AND BOTH CONTRADICT
        /// SOMETHING THE ITEM ITSELF SAYS. They are recorded here rather than
        /// silently diverged from, which is what Appendix C asks of an item
        /// that turns out to be impossible as written.
        ///
        /// 1. "The pipe separator replaced by spacing. Text unchanged." The
        ///    pipe is INSIDE the pinned string
        ///    ("Piles : {0} portee{1}   |   Teleporteur : {2} / {3}", PRD 12.1),
        ///    so the two sentences ask for opposite things and the acceptance
        ///    below them ("the strings of gameplay PRD 12.1 are present
        ///    verbatim") settles which one wins. The line is therefore ONE
        ///    label holding the whole format string, pipe and all. Splitting
        ///    the draw across two labels was considered and rejected: whichever
        ///    of the two halves the pipe is given it is still drawn, so the
        ///    split buys nothing on screen and costs an invariant (two halves
        ///    that must concatenate byte for byte) with no test to hold it.
        ///    What the item actually wanted - a line that reads as a counter
        ///    rather than as a debug print - is bought by the panel, the glyph
        ///    and the three spaces the pinned string already puts either side
        ///    of that pipe.
        ///
        /// 2. "The panel occupies no more than 420 x 64 px at reference." The
        ///    strings do not fit in it. Measured against Manrope's own advance
        ///    widths, the battery line is 357 px at its pinned 22 px (382 at
        ///    "12 portees ... 10 / 12"), and the film line is 483 px at its
        ///    pinned 20 px, before the synthesised weight and before the glyph,
        ///    the gap and the padding. One row lands near 400 to 430 px wide
        ///    and 46 px high, which meets the cap in the common case; the
        ///    second row cannot be brought under it at all without shrinking a
        ///    pinned size or cutting a pinned string. The panel is fitted to
        ///    its content instead of clamped, because a clamp would only move
        ///    the failure from a wide panel to text hanging out of a narrow one.
        /// </summary>
        void BuildCounters(Transform root)
        {
            RectTransform panel = NewRect("Counters", root);
            // ZERO, AND NOT THE ITEM'S 420 x 64. The ContentSizeFitter below
            // overwrites both axes on the first layout pass, so ANY size
            // written here is discarded; writing the cap would only read as a
            // cap that is being honoured, and it is not (see point 2 of the
            // summary above for what the pinned strings actually measure). The
            // anchor, the pivot and the corner offset are what this call is
            // really for.
            AnchorTopLeft(panel,
                new Vector2(BatteryOffset.x - CounterPadXPx, BatteryOffset.y - CounterPadYPx),
                Vector2.zero);
            NewPanel(panel, Alpha(PanelInk, CounterPanelAlpha), PanelRadiusPx);

            var layout = panel.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.childAlignment = TextAnchor.UpperLeft;
            layout.childForceExpandWidth = false;
            layout.childForceExpandHeight = false;
            layout.padding = new RectOffset(
                Mathf.RoundToInt(CounterPadXPx), Mathf.RoundToInt(CounterPadXPx),
                Mathf.RoundToInt(CounterPadYPx), Mathf.RoundToInt(CounterPadYPx));
            layout.spacing = CounterRowSpacingPx;

            var fitter = panel.gameObject.AddComponent<ContentSizeFitter>();
            fitter.horizontalFit = ContentSizeFitter.FitMode.PreferredSize;
            fitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            RectTransform batteryRow = NewRow("BatteryRow", panel, CounterRowGapPx);
            _batteryGlyph = NewRect("BatteryGlyph", batteryRow);
            NewGlyph(_batteryGlyph, _batteryGlyphSprite, BatteryGlyphColor);
            SetLayoutSize(_batteryGlyph, BatteryGlyphPx);
            _batteryLabel = NewLabel("Batteries", batteryRow, BatterySizePx, Color.white,
                TextAnchor.MiddleLeft, TextEdge.Shadow, OutlineSoft, TextWeight.Regular);

            RectTransform filmRow = NewRow("FilmRow", panel, CounterRowGapPx);
            _filmGlyph = NewRect("FilmGlyph", filmRow);
            NewGlyph(_filmGlyph, _filmGlyphSprite, FilmColor);
            SetLayoutSize(_filmGlyph, FilmGlyphPx);
            _filmLabel = NewLabel("Films", filmRow, FilmSizePx, FilmColor,
                TextAnchor.MiddleLeft, TextEdge.Shadow, OutlineSoft, TextWeight.Regular);
            // The FADER MOVED FROM THE LABEL TO THE ROW, so the film glyph
            // leaves with the number it counts. It is also what lets the panel
            // shrink back to one row: a layout group skips inactive children,
            // and a Fader deactivates what it has finished hiding.
            _filmFader = NewFader(filmRow.gameObject);
        }

        /// <summary>
        /// The raised picture, in two rects that do two different jobs.
        ///
        /// "PhotoView" is the ANCHOR: it is what the smoke probe finds by path,
        /// and it carries only instant truth (shown or not, and the roll).
        /// "Picture" under it holds the RawImage and every tween of V-ANIM-04.
        /// The RawImage lives on the child and not on the anchor precisely
        /// because the anchor may not move: an animation on the same rect the
        /// probe reads would be an animation deciding what the probe sees.
        ///
        /// "PhotoGhost" beside them is the copy the lowering plays on, so the
        /// anchor can disappear on the frame it is told to.
        /// </summary>
        void BuildPhotoView(Transform root)
        {
            RectTransform rect = NewRect("PhotoView", root);
            SetCentered(rect, Vector2.zero, new Vector2(ReferenceResolution.y, ReferenceResolution.y));
            _photoViewRect = rect;

            _pictureRect = NewRect("Picture", rect);
            SetCentered(_pictureRect, Vector2.zero, new Vector2(ReferenceResolution.y, ReferenceResolution.y));
            _photoView = _pictureRect.gameObject.AddComponent<RawImage>();
            _photoView.raycastTarget = false;
            rect.gameObject.SetActive(false);

            _ghostRect = NewRect("PhotoGhost", root);
            SetCentered(_ghostRect, Vector2.zero, new Vector2(ReferenceResolution.y, ReferenceResolution.y));
            _ghostView = _ghostRect.gameObject.AddComponent<RawImage>();
            _ghostView.raycastTarget = false;
            _ghostGroup = NewGroup(_ghostRect.gameObject);
            _ghostRect.gameObject.SetActive(false);
        }

        void BuildViewfinder(Transform root)
        {
            RectTransform rect = NewRect("Viewfinder", root);
            Stretch(rect);

            _viewfinderDims = new RectTransform[4];
            for (var i = 0; i < 4; i++)
            {
                _viewfinderDims[i] = NewRect("Dim" + i, rect);
                NewImage(_viewfinderDims[i], ViewfinderDim);
            }

            _viewfinderEdges = new RectTransform[4];
            for (var i = 0; i < 4; i++)
            {
                _viewfinderEdges[i] = NewRect("Edge" + i, rect);
                NewImage(_viewfinderEdges[i], ViewfinderEdge);
            }

            // The frosted rim. Each band dimmer than the last, quadratically, so
            // the rim reads as a falloff and not as three stripes.
            _viewfinderFrost = new RectTransform[FrostBands * 4];
            for (var band = 0; band < FrostBands; band++)
            {
                float drop = 1f - (float)band / FrostBands;
                var shade = new Color(FrostColor.r, FrostColor.g, FrostColor.b,
                    FrostColor.a * drop * drop);
                for (var side = 0; side < 4; side++)
                {
                    int at = band * 4 + side;
                    _viewfinderFrost[at] = NewRect("Frost" + at, rect);
                    NewImage(_viewfinderFrost[at], shade);
                }
            }

            // One parent for all sixteen arms, so V-VFX-06's fly-in is a single
            // scale (see BracketFromScale). Stretched to the canvas with a
            // centred pivot, which is what makes that scale walk the corners.
            _bracketRoot = NewRect("Brackets", rect);
            Stretch(_bracketRoot);

            // Four corners, two arms each, two passes (dark under light).
            _viewfinderBrackets = new RectTransform[16];
            var index = 0;
            for (var corner = 0; corner < 4; corner++)
            {
                for (var pass = 0; pass < 2; pass++)
                {
                    for (var arm = 0; arm < 2; arm++)
                    {
                        _viewfinderBrackets[index] = NewRect("Bracket" + index, _bracketRoot);
                        NewImage(_viewfinderBrackets[index], pass == 0 ? BracketDark : BracketLight);
                        index++;
                    }
                }
            }

            _viewfinderFader = NewFader(rect.gameObject);
        }

        /// <summary>
        /// V-HUD-03's pill. A rounded rect at 55 percent dark, holding a key
        /// cap and the rest of the sentence, fitted to whatever it is given.
        ///
        /// The pill is a CAPSULE and not a rounded box: its corner radius is
        /// half its height, which is what the item's word "pill" means and what
        /// tells it apart at a glance from the counter panel above it. One
        /// sprite serves both, because a 9-slice of radius r draws any box at
        /// least 2r across.
        ///
        /// It is fitted on BOTH axes and centred on the pinned 120 px, so the
        /// pinned position is the pill's and the words inside it are what
        /// decide its width. The acceptance ("the prompt reads against both a
        /// bright sky and the dark cage bars") is carried by the pill itself:
        /// over the bars it is a slightly darker dark, over the sky it is the
        /// only dark there is, and in both cases the white sits on the SAME
        /// background instead of on whatever the player happens to face.
        ///
        /// THE FADER MOVED FROM THE LABEL TO THE PILL. V-ANIM-03's 0.12 s in
        /// and 0.2 s out are unchanged, but they now carry the pill, the cap
        /// and the words together; a pill that stayed while its text faded
        /// would be an empty capsule sitting on screen.
        /// </summary>
        void BuildPrompt(Transform root)
        {
            RectTransform pill = NewRect("Prompt", root);
            pill.anchorMin = new Vector2(0.5f, 0f);
            pill.anchorMax = new Vector2(0.5f, 0f);
            pill.pivot = new Vector2(0.5f, 0f);
            pill.anchoredPosition = new Vector2(0f, PromptBottomPx);
            pill.sizeDelta = new Vector2(400f, PromptPillHeightPx);
            NewPanel(pill, Alpha(PanelInk, PromptPillAlpha),
                Mathf.RoundToInt(PromptPillHeightPx * 0.5f));

            var layout = pill.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.childAlignment = TextAnchor.MiddleCenter;
            layout.childForceExpandWidth = false;
            layout.childForceExpandHeight = false;
            layout.padding = new RectOffset(
                Mathf.RoundToInt(PromptPillPadXPx), Mathf.RoundToInt(PromptPillPadXPx), 0, 0);
            layout.spacing = PromptCapGapPx;

            var fitter = pill.gameObject.AddComponent<ContentSizeFitter>();
            fitter.horizontalFit = ContentSizeFitter.FitMode.PreferredSize;
            fitter.verticalFit = ContentSizeFitter.FitMode.Unconstrained;

            _promptCap = NewKeyCap("PromptKey", pill, PromptCapSizePx, out _promptCapLabel);
            _promptCap.gameObject.SetActive(false);

            _promptLabel = NewLabel("PromptText", pill, PromptSizePx, Color.white,
                TextAnchor.MiddleLeft, TextEdge.Shadow, OutlineSoft, TextWeight.Regular);

            _promptFader = NewFader(pill.gameObject);
        }

        /// <summary>
        /// V-HUD-04's held panel: the polaroid card, the title and the four
        /// control hints as key-cap pairs, on a rounded panel at 65 percent.
        ///
        /// THE ITEM OFFERS A BLUR AND IT IS DECLINED, for a reason that is not
        /// about cost. "A blurred copy of the frame behind it via the opaque
        /// texture, or a simple 65 percent dark if the blur costs too much."
        /// The RP asset does set m_RequireOpaqueTexture, so _CameraOpaqueTexture
        /// exists; a UI Image cannot sample it without a shader, and a new
        /// .shader is allowed where a new binary asset is not. What settles it
        /// is the README's oldest trap: A SHADER REACHED ONLY BY Shader.Find IS
        /// STRIPPED FROM THE PLAYER. Every shader this game creates in code had
        /// to be added to Always Included Shaders in
        /// ProjectSettings/GraphicsSettings.asset to survive a build, and that
        /// file is not this agent's to edit. A blur shader added here would
        /// look perfect in the editor and come back null in the player, which
        /// is a panel drawing with a null material: invisible, silent, and
        /// exactly the failure mode that once read as "the levels are empty".
        ///
        /// Two smaller reasons point the same way. A ScreenSpaceOverlay canvas
        /// draws after everything, so the opaque texture it would sample is the
        /// frame BEFORE transparents, and the blur would miss the very things
        /// (the teleporter's light, the motes) that make the frame worth
        /// blurring. And the panel sits over the abyss more often than not,
        /// where there is nothing behind it to blur.
        ///
        /// So: 65 percent dark, the branch the item itself sanctions. It is
        /// darker than the 55 it replaces, which is what the hints need now
        /// that they are dark type on light caps.
        /// </summary>
        void BuildHeldPanel(Transform root)
        {
            RectTransform panel = NewRect("HeldPanel", root);
            panel.anchorMin = new Vector2(1f, 0f);
            panel.anchorMax = new Vector2(1f, 0f);
            panel.pivot = new Vector2(1f, 0f);
            // PRD 12.1 puts the panel 24 px in from the bottom right corner.
            // It is BUILT parked off the right edge instead, because V-ANIM-03
            // slides it in: the pinned -24 is the value every show tween lands
            // on, and the panel is never on screen anywhere else.
            panel.anchoredPosition = new Vector2(HeldHiddenX, HeldMarginPx);
            panel.sizeDelta = new Vector2(HeldPanelWidthPx, HeldPanelHeightPx);
            NewPanel(panel, Alpha(PanelInk, HeldPanelAlpha), PanelRadiusPx);
            _heldPanel = panel;

            var layout = panel.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.childAlignment = TextAnchor.LowerRight;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            layout.padding = new RectOffset(12, 12, 8, 8);
            layout.spacing = 2f;

            // The card slot keeps its size whether or not a card is drawn, so the
            // panel does not jump when the photo is raised.
            RectTransform cardSlot = NewRect("CardSlot", panel);
            var slotElement = cardSlot.gameObject.AddComponent<LayoutElement>();
            slotElement.minWidth = HeldPanelMinSize.x;
            slotElement.minHeight = HeldPanelMinSize.y;
            slotElement.preferredWidth = HeldPanelMinSize.x;
            slotElement.preferredHeight = HeldPanelMinSize.y;

            RectTransform shadowRect = NewRect("CardShadow", cardSlot);
            SetCentered(shadowRect, Vector2.zero, HeldPanelMinSize);
            _heldCardShadow = shadowRect.gameObject.AddComponent<PhotoCardShadow>();
            _heldCardShadow.raycastTarget = false;

            RectTransform cardRect = NewRect("Card", cardSlot);
            SetCentered(cardRect, Vector2.zero, HeldPanelMinSize);
            _heldCard = cardRect.gameObject.AddComponent<PhotoCard>();
            _heldCard.raycastTarget = false;

            _heldTitle = NewLabel("HeldTitle", panel, HeldTitleSizePx, Color.white,
                TextAnchor.MiddleRight, TextEdge.Shadow, OutlineSoft, TextWeight.Regular);

            BuildHintRow(panel);

            panel.gameObject.SetActive(false);
        }

        /// <summary>
        /// V-HUD-04's four control hints, as key-cap pairs in a row.
        ///
        /// The row is built by SPLITTING <see cref="HeldHintText"/> and never by
        /// retyping its pieces, which is what makes the acceptance ("the hint
        /// string's four commands stay in the same order and words") true by
        /// construction rather than by review: Split hands back the four
        /// commands in order, each command's first " : " separates its key from
        /// what the key does, and rejoining all of it reproduces the constant.
        /// The guard at the end says so out loud if a later edit breaks it,
        /// because a hint row that quietly drops a word looks exactly like a
        /// hint row that does not.
        ///
        /// The row carries no state and is written exactly once, which is why
        /// nothing here is kept in a field: there is no later frame in which
        /// any of it changes.
        /// </summary>
        void BuildHintRow(RectTransform panel)
        {
            RectTransform row = NewRect("HeldHints", panel);
            var layout = row.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.childAlignment = TextAnchor.MiddleRight;
            layout.childForceExpandWidth = false;
            layout.childForceExpandHeight = false;
            layout.spacing = HintCommandGapPx;
            SetLayoutHeight(row, HintRowHeightPx);

            string[] commands = HeldHintText.Split(
                new string[] { HintSeparator }, System.StringSplitOptions.None);
            var rebuilt = new System.Text.StringBuilder();
            for (var i = 0; i < commands.Length; i++)
            {
                if (i > 0)
                {
                    rebuilt.Append(HintSeparator);
                }
                string command = commands[i];
                int at = command.IndexOf(KeySeparator, System.StringComparison.Ordinal);
                RectTransform pair = NewRow("Hint" + i, row, HintPairGapPx);
                if (at > 0)
                {
                    Text cap;
                    NewKeyCap("Key" + i, pair, HintCapSizePx, out cap);
                    cap.text = command.Substring(0, at);
                    Text action = NewLabel("Action" + i, pair, HeldHintSizePx, HeldHintColor,
                        TextAnchor.MiddleLeft, TextEdge.Shadow, OutlineSoft, TextWeight.Regular);
                    action.text = command.Substring(at + KeySeparator.Length);
                    rebuilt.Append(cap.text).Append(KeySeparator).Append(action.text);
                    continue;
                }
                // No key in this command: it is drawn whole, for the same
                // reason a keyless prompt is (see SplitPromptKey).
                Text whole = NewLabel("Action" + i, pair, HeldHintSizePx, HeldHintColor,
                    TextAnchor.MiddleLeft, TextEdge.Shadow, OutlineSoft, TextWeight.Regular);
                whole.text = command;
                rebuilt.Append(command);
            }

            if (rebuilt.ToString() != HeldHintText)
            {
                Debug.LogError("[Hud] The hint row no longer spells PRD 12.1's hint: \""
                    + rebuilt + "\"");
            }
        }

        void BuildBanner(Transform root)
        {
            RectTransform banner = NewRect("Banner", root);
            banner.anchorMin = new Vector2(0.5f, 1f);
            banner.anchorMax = new Vector2(0.5f, 1f);
            banner.pivot = new Vector2(0.5f, 1f);
            banner.anchoredPosition = new Vector2(0f, -BannerTopPx);
            banner.sizeDelta = new Vector2(1300f, 120f);
            _bannerGroup = banner.gameObject.AddComponent<CanvasGroup>();
            _bannerGroup.alpha = 0f;
            _bannerGroup.interactable = false;
            _bannerGroup.blocksRaycasts = false;

            var layout = banner.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.childAlignment = TextAnchor.UpperCenter;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;

            // The banner is the one thing on this HUD that lands on BARE SKY
            // every time (it arrives on the frame a level opens, over whatever
            // the spawn happens to face), so both its labels keep the
            // four-sided contour and only the title takes the heavier weight.
            // Under Manrope, Title and Regular render the same and the
            // hierarchy is the 44 against 20 px; under the fallback font the
            // distinction is real. See Fonts.StyleFor.
            _bannerTitle = NewLabel("BannerTitle", banner, BannerTitleSizePx, Color.white,
                TextAnchor.MiddleCenter, TextEdge.Contour, OutlineSoft, TextWeight.Title);

            // V-HUD-07's rule, in two rects: a full-width holder the layout can
            // measure, and the line itself centred inside it. Centred is what
            // makes the growth read as "outward" without animating a position,
            // and it is why the line may not be a layout child of its own.
            RectTransform ruleHolder = NewRect("BannerRuleRow", banner);
            SetLayoutHeight(ruleHolder, BannerRuleHeightPx + 10f);
            _bannerRule = NewRect("BannerRule", ruleHolder);
            SetCentered(_bannerRule, Vector2.zero, new Vector2(0f, BannerRuleHeightPx));
            NewImage(_bannerRule, BannerRuleColor);

            _bannerSubtitle = NewLabel("BannerSubtitle", banner, BannerSubtitleSizePx,
                BannerSubtitleColor, TextAnchor.MiddleCenter, TextEdge.Contour, OutlineSoft,
                TextWeight.Regular);
            // A group of its own for the 0.15 s delay. Nested groups multiply,
            // so this one only ever subtracts from the pinned banner curve and
            // can never make the subtitle outlive it.
            _bannerSubtitleGroup = NewGroup(_bannerSubtitle.gameObject);
        }

        void BuildToast(Transform root)
        {
            _toastLabel = NewLabel("Toast", root, ToastSizePx, ToastColor,
                TextAnchor.MiddleCenter, OutlineStrong);
            RectTransform rect = _toastLabel.rectTransform;
            rect.anchorMin = new Vector2(0.5f, 0f);
            rect.anchorMax = new Vector2(0.5f, 0f);
            rect.pivot = new Vector2(0.5f, 0f);
            rect.anchoredPosition = new Vector2(0f, ToastBottomPx);
            rect.sizeDelta = new Vector2(1200f, 30f);
            _toastGroup = NewGroup(_toastLabel.gameObject);
            _toastLabel.gameObject.SetActive(false);
        }

        /// <summary>
        /// The rewind treatment: the wash, the label and V-HUD-06's bar, under
        /// one container so the whole thing fades in and out together (nothing
        /// on this HUD may appear in a single frame, V-ANIM-03). The container
        /// is stretched to the canvas, so every child keeps the geometry PRD
        /// 12.1 gives it.
        /// </summary>
        void BuildRewind(Transform root)
        {
            RectTransform group = NewRect("Rewind", root);
            Stretch(group);
            _rewindFader = NewFader(group.gameObject);

            RectTransform tint = NewRect("RewindTint", group);
            Stretch(tint);
            NewImage(tint, RewindTint);

            _rewindLabel = NewLabel("RewindLabel", group, RewindSizePx, RewindColor,
                TextAnchor.MiddleCenter, OutlineStrong);
            RectTransform rect = _rewindLabel.rectTransform;
            rect.anchorMin = new Vector2(0.5f, 1f);
            rect.anchorMax = new Vector2(0.5f, 1f);
            rect.pivot = new Vector2(0.5f, 1f);
            rect.anchoredPosition = new Vector2(0f, -RewindTopPx);
            rect.sizeDelta = new Vector2(1200f, 42f);
            // A SECOND CanvasGroup, on the label alone, for the pulse. Nested
            // groups multiply, so the pulse rides on top of the fade instead of
            // fighting it, and dimming the label this way keeps its outline
            // dimming with it (Fonts.Apply turns useGraphicAlpha off).
            _rewindPulse = NewGroup(_rewindLabel.gameObject);
            _rewindPulse.alpha = 1f;

            // The bar: a dim track with an amber fill that shrinks from both
            // ends, under a centred label. Symmetric because the label above it
            // is centred; a bar draining sideways under centred text reads as
            // belonging to something else.
            RectTransform track = NewRect("RewindBarTrack", group);
            AnchorTopCenter(track, RewindBarTopPx, new Vector2(RewindBarWidthPx, RewindBarHeightPx));
            NewImage(track, new Color(RewindAmber.r, RewindAmber.g, RewindAmber.b, 0.16f));

            RectTransform fill = NewRect("RewindBarFill", group);
            AnchorTopCenter(fill, RewindBarTopPx, new Vector2(RewindBarWidthPx, RewindBarHeightPx));
            NewImage(fill, new Color(RewindAmber.r, RewindAmber.g, RewindAmber.b, 0.9f));
            _rewindBarFill = fill;
            // Not deactivated here: NewFader already parked the whole group off,
            // and SetRewinding is what brings it back.
        }

        /// <summary>
        /// V-VFX-06's shutter: two leaves that close over the frame and a white
        /// flash above them. Built after everything else and before the fade, so
        /// it hides the HUD it is commenting on and the fade still covers it.
        /// </summary>
        void BuildShutter(Transform root)
        {
            RectTransform group = NewRect("Shutter", root);
            Stretch(group);
            _shutterRoot = group;

            _shutterTop = NewRect("LeafTop", group);
            _shutterTop.anchorMin = new Vector2(0f, 1f);
            _shutterTop.anchorMax = new Vector2(1f, 1f);
            _shutterTop.pivot = new Vector2(0.5f, 1f);
            _shutterTop.anchoredPosition = Vector2.zero;
            _shutterTop.sizeDelta = Vector2.zero;
            NewImage(_shutterTop, ShutterLeafColor);

            _shutterBottom = NewRect("LeafBottom", group);
            _shutterBottom.anchorMin = new Vector2(0f, 0f);
            _shutterBottom.anchorMax = new Vector2(1f, 0f);
            _shutterBottom.pivot = new Vector2(0.5f, 0f);
            _shutterBottom.anchoredPosition = Vector2.zero;
            _shutterBottom.sizeDelta = Vector2.zero;
            NewImage(_shutterBottom, ShutterLeafColor);

            RectTransform flash = NewRect("Flash", group);
            Stretch(flash);
            _shutterFlash = NewImage(flash, new Color(1f, 1f, 1f, 0f));

            group.gameObject.SetActive(false);
        }

        void BuildFade(Transform root)
        {
            // Last child, so it covers everything the HUD drew above.
            RectTransform rect = NewRect("Fade", root);
            Stretch(rect);
            _fade = NewImage(rect, new Color(FadeColor.r, FadeColor.g, FadeColor.b, 0f));
        }

        // ---- The tween helper -----------------------------------------------

        /// <summary>
        /// A one-shot cursor from 0 to 1, and the whole tween machinery of this
        /// HUD (V-ANIM-03 asks for "a small tween helper in Hud (no package)",
        /// and there is no tweening package in this project).
        ///
        /// It deliberately knows nothing about what it drives: a caller starts
        /// it, steps it on the clock it chose, shapes the cursor with one of the
        /// easings below and writes the result to a widget. That is what keeps
        /// this tier's one rule inspectable in a single place. A Tween holds a
        /// number between 0 and 1 and can therefore only ever move pixels: it
        /// has no way to hold a collider, a counter or an event back.
        /// </summary>
        sealed class Tween
        {
            float _elapsed;
            float _duration;

            /// <summary>True when there is nothing left to animate.</summary>
            public bool Done
            {
                get { return _elapsed >= _duration; }
            }

            /// <summary>The raw cursor, 0 to 1. A tween that is done reads 1.</summary>
            public float Cursor
            {
                get { return _duration <= 0f ? 1f : Mathf.Clamp01(_elapsed / _duration); }
            }

            public void Start(float seconds)
            {
                _duration = Mathf.Max(seconds, 0.0001f);
                _elapsed = 0f;
            }

            /// <summary>Ends it now, on its target, with no frame of animation.</summary>
            public void Snap()
            {
                _duration = 0f;
                _elapsed = 0f;
            }

            /// <summary>
            /// Advances the cursor. Returns true on every frame that still had
            /// work, INCLUDING the frame that lands exactly on the end, so a
            /// caller can write the final value once and then leave its widget
            /// alone.
            /// </summary>
            public bool Step(float dt)
            {
                if (Done)
                {
                    return false;
                }
                _elapsed = Mathf.Min(_elapsed + dt, _duration);
                return true;
            }
        }

        /// <summary>
        /// A CanvasGroup with a tween on its alpha, plus the one rule that is
        /// the whole difference between fading out and vanishing: the object is
        /// deactivated only once the fade has actually landed on zero.
        ///
        /// A CanvasGroup and not the graphic's own colour, because Fonts.Apply
        /// gives every label an Outline with useGraphicAlpha off: dimming the
        /// text colour would leave a solid black outline behind and the label
        /// would read as hollow rather than as absent.
        /// </summary>
        sealed class Fader
        {
            readonly CanvasGroup _group;
            readonly Tween _tween = new Tween();
            float _from;
            float _target;

            public Fader(CanvasGroup group)
            {
                _group = group;
                _target = group.alpha;
            }

            /// <summary>Fully faded out, and staying that way.</summary>
            public bool Hidden
            {
                get { return _target <= 0f && _tween.Done; }
            }

            public void Show(float seconds)
            {
                if (!_group.gameObject.activeSelf)
                {
                    _group.gameObject.SetActive(true);
                }
                To(1f, seconds);
            }

            public void Hide(float seconds)
            {
                To(0f, seconds);
            }

            public void To(float alpha, float seconds)
            {
                if (Mathf.Approximately(_target, alpha))
                {
                    // Already there or already heading there. Callers drive this
                    // every frame from Main, so restarting would freeze the fade
                    // at its first step forever.
                    return;
                }
                _from = _group.alpha;
                _target = alpha;
                _tween.Start(seconds);
            }

            public void Step(float dt)
            {
                if (_tween.Step(dt))
                {
                    _group.alpha = Mathf.Lerp(_from, _target, EaseOut(_tween.Cursor));
                    return;
                }
                if (_target <= 0f && _group.gameObject.activeSelf)
                {
                    _group.gameObject.SetActive(false);
                }
            }
        }

        /// <summary>Cubic ease out: fast, then settling. The HUD's default.</summary>
        static float EaseOut(float t)
        {
            float k = 1f - Mathf.Clamp01(t);
            return 1f - k * k * k;
        }

        /// <summary>
        /// Cubic ease out that overshoots and settles back (V-ANIM-04's "slight
        /// overshoot"). It returns values ABOVE 1, so every caller must use the
        /// unclamped Lerp family: Mathf.Lerp would silently eat the overshoot
        /// and the raise would just be a slower slide.
        /// </summary>
        static float EaseOutBack(float t)
        {
            float k = Mathf.Clamp01(t) - 1f;
            return 1f + k * k * ((PhotoOvershoot + 1f) * k + PhotoOvershoot);
        }

        /// <summary>0 to 1 to 0, a half sine: the counter pop of V-VFX-04.</summary>
        static float Pop(float t)
        {
            return Mathf.Sin(Mathf.Clamp01(t) * Mathf.PI);
        }

        /// <summary>
        /// Rotates a canvas offset by whole quarter turns, counter-clockwise for
        /// a positive count. Written as an axis swap rather than run through a
        /// quaternion because at multiples of 90 degrees the swap is EXACT: the
        /// resting picture has to land on zero offset, and a picture that came to
        /// rest 0.0001 px off centre would be a blurred picture.
        /// </summary>
        static Vector2 QuarterTurns(int turns, Vector2 v)
        {
            switch (((turns % 4) + 4) % 4)
            {
                case 1:
                    return new Vector2(-v.y, v.x);
                case 2:
                    return new Vector2(-v.x, -v.y);
                case 3:
                    return new Vector2(v.y, -v.x);
                default:
                    return v;
            }
        }

        // ---- Small helpers --------------------------------------------------

        static RectTransform NewRect(string name, Transform parent)
        {
            var go = new GameObject(name, typeof(RectTransform));
            RectTransform rect = go.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            return rect;
        }

        static Image NewImage(RectTransform rect, Color color)
        {
            Image image = rect.gameObject.AddComponent<Image>();
            image.color = color;
            image.raycastTarget = false;
            return image;
        }

        /// <summary>
        /// A CanvasGroup that cannot take the pointer, whatever it ends up
        /// holding. The HUD has no raycaster at all (see Build), and this keeps
        /// it that way if one ever arrives.
        /// </summary>
        static CanvasGroup NewGroup(GameObject target)
        {
            var group = target.AddComponent<CanvasGroup>();
            group.alpha = 0f;
            group.interactable = false;
            group.blocksRaycasts = false;
            return group;
        }

        static Fader NewFader(GameObject target)
        {
            CanvasGroup group = NewGroup(target);
            var fader = new Fader(group);
            // Faded out AND inactive to begin with: a Fader turns the object
            // back on itself when it is shown.
            target.SetActive(false);
            return fader;
        }

        static void Stretch(RectTransform rect)
        {
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }

        static void SetCentered(RectTransform rect, Vector2 position, Vector2 size)
        {
            rect.anchorMin = new Vector2(0.5f, 0.5f);
            rect.anchorMax = new Vector2(0.5f, 0.5f);
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = position;
            rect.sizeDelta = size;
        }

        static void AnchorTopLeft(RectTransform rect, Vector2 offset, Vector2 size)
        {
            rect.anchorMin = new Vector2(0f, 1f);
            rect.anchorMax = new Vector2(0f, 1f);
            rect.pivot = new Vector2(0f, 1f);
            // The offset is given as a distance DOWN from the top edge.
            rect.anchoredPosition = new Vector2(offset.x, -offset.y);
            rect.sizeDelta = size;
        }

        static void AnchorTopCenter(RectTransform rect, float topPx, Vector2 size)
        {
            rect.anchorMin = new Vector2(0.5f, 1f);
            rect.anchorMax = new Vector2(0.5f, 1f);
            rect.pivot = new Vector2(0.5f, 1f);
            rect.anchoredPosition = new Vector2(0f, -topPx);
            rect.sizeDelta = size;
        }

        /// <summary>
        /// A label over the WORLD. Everything about the font and the edge lives
        /// in Fonts, which also records why this is uGUI Text and not
        /// TextMeshPro: TMP cannot start in a player without an asset this
        /// project deliberately does not ship. This short form means "there is
        /// nothing behind this label", so it takes the four-sided contour that
        /// is the only thing keeping white readable over a pale sky.
        /// </summary>
        static Text NewLabel(string name, Transform parent, float sizePx,
            Color color, TextAnchor alignment, Color outlineColor)
        {
            RectTransform rect = NewRect(name, parent);
            var label = rect.gameObject.AddComponent<Text>();
            Fonts.Apply(label, Mathf.RoundToInt(sizePx), color, alignment, true, outlineColor);
            return label;
        }

        /// <summary>
        /// A label whose edge and weight are chosen, for the labels tier 5 puts
        /// ON something: a panel already carries their contrast, so they take
        /// the one-sided TextEdge.Shadow and lose the letterpress ring.
        /// </summary>
        static Text NewLabel(string name, Transform parent, float sizePx,
            Color color, TextAnchor alignment, TextEdge edge, Color edgeColor, TextWeight weight)
        {
            RectTransform rect = NewRect(name, parent);
            var label = rect.gameObject.AddComponent<Text>();
            Fonts.Apply(label, Mathf.RoundToInt(sizePx), color, alignment, edge, edgeColor, weight);
            return label;
        }

        /// <summary>The same colour at a chosen alpha. Reads as the design does.</summary>
        static Color Alpha(Color color, float alpha)
        {
            return new Color(color.r, color.g, color.b, alpha);
        }

        /// <summary>
        /// A rounded panel: one 9-sliced sprite of the given corner radius,
        /// tinted by the Image. Sliced rather than stretched, so one painted
        /// corner serves the counter panel, the prompt pill, the held card and
        /// every key cap at any size at least twice its radius.
        /// </summary>
        Image NewPanel(RectTransform rect, Color color, int radiusPx)
        {
            Image image = NewImage(rect, color);
            image.sprite = RoundedSprite(radiusPx);
            image.type = Image.Type.Sliced;
            image.pixelsPerUnitMultiplier = 1f;
            return image;
        }

        /// <summary>A painted glyph, drawn at whatever size its rect is given.</summary>
        static Image NewGlyph(RectTransform rect, Sprite sprite, Color color)
        {
            Image image = NewImage(rect, color);
            image.sprite = sprite;
            image.type = Image.Type.Simple;
            return image;
        }

        /// <summary>
        /// A horizontal strip whose children keep their own sizes and sit on
        /// one middle line. Used for a counter's glyph and numbers, and for a
        /// hint's cap and words.
        /// </summary>
        static RectTransform NewRow(string name, RectTransform parent, float spacing)
        {
            RectTransform rect = NewRect(name, parent);
            var layout = rect.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.childAlignment = TextAnchor.MiddleLeft;
            layout.childForceExpandWidth = false;
            layout.childForceExpandHeight = false;
            layout.spacing = spacing;
            return rect;
        }

        /// <summary>
        /// Fixes what a layout group should give a child that has no opinion of
        /// its own. An Image has no preferred size, so without this a glyph
        /// inside a row would be measured as nothing.
        /// </summary>
        static void SetLayoutSize(RectTransform rect, Vector2 size)
        {
            var element = rect.gameObject.AddComponent<LayoutElement>();
            element.minWidth = size.x;
            element.minHeight = size.y;
            element.preferredWidth = size.x;
            element.preferredHeight = size.y;
        }

        /// <summary>The same for a row whose width its parent decides.</summary>
        static void SetLayoutHeight(RectTransform rect, float height)
        {
            var element = rect.gameObject.AddComponent<LayoutElement>();
            element.minHeight = height;
            element.preferredHeight = height;
        }

        /// <summary>
        /// A key cap: V-HUD-03's "small square with E in it, drawn as a nested
        /// Text on a rounded rect".
        ///
        /// It is a layout group and not a fixed square, which is what lets the
        /// same cap hold "E", "F", "Molette" and "Clic gauche": the chip grows
        /// with its letter and a one-character cap still comes out square,
        /// because the padding is symmetric and the cap's height is the
        /// letter's line box. Its width reaches its parent as the layout
        /// group's own preferred width, so no ContentSizeFitter is needed and
        /// nothing here fights the row it sits in.
        ///
        /// The letter takes NO edge: it is dark type on a light chip, which is
        /// contrast the other way round, and a shadow under it would only
        /// muddy a 13 px glyph.
        /// </summary>
        RectTransform NewKeyCap(string name, RectTransform parent, float sizePx, out Text label)
        {
            RectTransform cap = NewRect(name, parent);
            NewPanel(cap, KeyCapFace, KeyCapRadiusPx);
            var layout = cap.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.childAlignment = TextAnchor.MiddleCenter;
            layout.childForceExpandWidth = false;
            layout.childForceExpandHeight = false;
            layout.padding = new RectOffset(
                Mathf.RoundToInt(KeyCapPadXPx), Mathf.RoundToInt(KeyCapPadXPx),
                Mathf.RoundToInt(KeyCapPadYPx), Mathf.RoundToInt(KeyCapPadYPx));
            label = NewLabel("Cap", cap, sizePx, KeyCapInk,
                TextAnchor.MiddleCenter, TextEdge.None, KeyCapInk, TextWeight.Title);
            return cap;
        }

        // ---- Painting the art (PRD_VISUAL 3.2 as amended: no new asset) -----

        /// <summary>
        /// How many texels each reference pixel of a painted glyph is drawn
        /// with. The HUD is authored at 1600 x 900 and scales up with the
        /// window, so a glyph painted 1:1 would soften on any larger screen;
        /// four covers 4K on the crosshair, which is the smallest and therefore
        /// the most exposed of them. It costs nothing: the largest texture in
        /// this file is 96 x 96.
        /// </summary>
        const int ArtScale = 4;

        /// <summary>
        /// The same for a rounded panel's corner, at half the resolution. A
        /// panel corner is ten to twenty pixels of arc rather than one or two,
        /// so it is already smooth at two texels per pixel, and the prompt
        /// pill's radius of 22 would otherwise cost a 180 px square texture to
        /// draw a shape the eye reads as "not sharp".
        /// </summary>
        const int PanelArtScale = 2;

        /// <summary>
        /// Paints everything the widgets hang on an Image, once, at build.
        ///
        /// Order matters only in that BuildCrosshair and the rest run after it.
        /// The rounded panels are painted lazily instead (see RoundedSprite),
        /// because their radius is what identifies them and the callers are the
        /// ones that know it.
        /// </summary>
        void PaintArt()
        {
            _batteryGlyphSprite = PaintBattery();
            _filmGlyphSprite = PaintFilmCan();
            _ringSprite = PaintRing();
            _dotSprite = PaintDot();
            _reticleSprite = PaintReticle();
        }

        /// <summary>
        /// The 9-slice for a rounded box of the given corner radius, painted on
        /// first use and kept.
        ///
        /// The texture is only 2r + 1 reference pixels square: four corners and
        /// a single pixel of middle, which is all a 9-slice ever samples. The
        /// sprite is created at PanelArtScale times the canvas's own 100 pixels
        /// per unit, so its border of r * PanelArtScale texels comes back out as
        /// exactly r canvas units however finely it was painted. Get that pair
        /// out of step and the corners arrive at the wrong size with nothing to
        /// say so.
        /// </summary>
        Sprite RoundedSprite(int radiusPx)
        {
            Sprite cached;
            if (_roundedSprites.TryGetValue(radiusPx, out cached) && cached != null)
            {
                return cached;
            }

            int side = radiusPx * 2 + 1;
            var painter = new Painter(side, side, PanelArtScale);
            painter.RoundedRect(side * 0.5f, side * 0.5f,
                side * 0.5f - radiusPx, side * 0.5f - radiusPx, radiusPx, 0f);
            Texture2D texture = Bake(painter);
            texture.name = "Rounded" + radiusPx;
            float border = radiusPx * PanelArtScale;
            Sprite sprite = Sprite.Create(
                texture, new Rect(0f, 0f, texture.width, texture.height),
                new Vector2(0.5f, 0.5f), 100f * PanelArtScale, 0, SpriteMeshType.FullRect,
                new Vector4(border, border, border, border));
            sprite.name = "Rounded" + radiusPx;
            _drawn.Add(sprite);
            _roundedSprites[radiusPx] = sprite;
            return sprite;
        }

        /// <summary>
        /// V-HUD-02's battery: "a generated 16 x 24 icon: a rounded rect with a
        /// nub". Drawn upright, with the nub on top and a charge bar inside,
        /// because the thing it labels is a count of batteries carried and a
        /// battery standing up is the shape a player reads without looking.
        /// </summary>
        Sprite PaintBattery()
        {
            float w = BatteryGlyphPx.x;
            float h = BatteryGlyphPx.y;
            float cx = w * 0.5f;
            var painter = new Painter(w, h, ArtScale);

            // Every extent below is inset from the edge of the box by at least
            // the stroke's own half width. A shape painted flush with the edge
            // loses its antialiasing to the clamp, and on a 16 px glyph that
            // reads as a chipped corner.
            const float nubHalfW = 3f;
            const float nubHalfH = 1.5f;
            const float nubRadius = 1f;
            const float shellInset = 1f;
            const float shellRadius = 3f;
            const float shellStroke = 1.6f;

            // The nub, first and on its own, so the shell's stroke can overlap
            // its base and the two read as one piece of metal.
            painter.RoundedRect(cx, h - nubHalfH - 0.5f,
                nubHalfW - nubRadius, nubHalfH - nubRadius, nubRadius, 0f);

            // The shell: an outline, so the glyph reads as a container.
            float shellTop = h - nubHalfH * 2f - 0.5f;
            float shellCy = (shellTop + shellInset) * 0.5f;
            float shellHalfH = (shellTop - shellInset) * 0.5f;
            float shellHalfW = cx - shellInset;
            painter.RoundedRect(cx, shellCy, shellHalfW - shellRadius,
                shellHalfH - shellRadius, shellRadius, shellStroke);

            // The charge, filling the bottom half of the cell. Not the whole
            // of it: a battery drawn full is a battery that looks like a
            // percentage, and this glyph labels a count.
            painter.RoundedRect(cx, 7.5f, 4f, 3.5f, 1f, 0f);
            return Bake(painter, "BatteryGlyph");
        }

        /// <summary>
        /// The film can of V-HUD-02: a reel seen face on, which is a ring, a
        /// hub and the three windows between the spokes. Three and not four,
        /// so the glyph cannot be mistaken for a wheel.
        /// </summary>
        Sprite PaintFilmCan()
        {
            float w = FilmGlyphPx.x;
            float h = FilmGlyphPx.y;
            float cx = w * 0.5f;
            float cy = h * 0.5f;
            var painter = new Painter(w, h, ArtScale);
            painter.Circle(cx, cy, w * 0.5f - 1.4f, 1.6f);
            painter.Disc(cx, cy, 2.2f);
            for (var i = 0; i < 3; i++)
            {
                float angle = (90f + i * 120f) * Mathf.Deg2Rad;
                painter.Disc(cx + Mathf.Cos(angle) * 5.2f, cy + Mathf.Sin(angle) * 5.2f, 1.7f);
            }
            return Bake(painter, "FilmGlyph");
        }

        /// <summary>
        /// The box the ring is painted in. Two pixels wider than the ring on
        /// each side, so the stroke's own antialiasing is never clipped by the
        /// edge of the texture.
        /// </summary>
        static Vector2 RingSpriteSizePx()
        {
            return new Vector2(CrosshairRingPx + 4f, CrosshairRingPx + 4f);
        }

        /// <summary>V-HUD-05's "6 px ring".</summary>
        Sprite PaintRing()
        {
            Vector2 box = RingSpriteSizePx();
            var painter = new Painter(box.x, box.y, ArtScale);
            painter.Circle(box.x * 0.5f, box.y * 0.5f,
                CrosshairRingPx * 0.5f - CrosshairRingStrokePx * 0.5f, CrosshairRingStrokePx);
            return Bake(painter, "CrosshairRing");
        }

        /// <summary>V-HUD-05's "2 px dot", the one part that never leaves.</summary>
        Sprite PaintDot()
        {
            float box = CrosshairDotPx * 2f;
            // Painted at twice the scale of everything else: it is two pixels
            // across, so a texel is a quarter of the whole shape at ArtScale
            // and the disc would come out as a cross.
            var painter = new Painter(box, box, ArtScale * 2);
            painter.Disc(box * 0.5f, box * 0.5f, CrosshairDotPx * 0.5f);
            return Bake(painter, "CrosshairDot");
        }

        /// <summary>
        /// V-HUD-05's viewfinder reticle: "a circle with tick marks". The ticks
        /// sit OUTSIDE the circle and point inward at it, which is what a
        /// camera reticle does and what tells this state apart from the ring at
        /// a glance even though both are circles.
        /// </summary>
        Sprite PaintReticle()
        {
            float box = CrosshairReticlePx;
            float c = box * 0.5f;
            const float circleRadius = 7f;
            const float tickInner = 8.6f;
            const float tickOuter = 11f;
            const float tickHalfWide = 0.6f;
            float tickHalfLong = (tickOuter - tickInner) * 0.5f;
            float tickMid = tickInner + tickHalfLong;

            var painter = new Painter(box, box, ArtScale);
            painter.Circle(c, c, circleRadius, 1.2f);
            // Square ticks and not rounded ones: at 1.2 x 3 px a corner radius
            // would round the whole mark into a blob.
            painter.RoundedRect(c, c + tickMid, tickHalfWide, tickHalfLong, 0f, 0f);
            painter.RoundedRect(c, c - tickMid, tickHalfWide, tickHalfLong, 0f, 0f);
            painter.RoundedRect(c + tickMid, c, tickHalfLong, tickHalfWide, 0f, 0f);
            painter.RoundedRect(c - tickMid, c, tickHalfLong, tickHalfWide, 0f, 0f);
            return Bake(painter, "CrosshairReticle");
        }

        Sprite Bake(Painter painter, string name)
        {
            Texture2D texture = Bake(painter);
            texture.name = name;
            // FullRect and not the default Tight: a tight mesh is traced from
            // the texture's own alpha, which means READING the pixels back,
            // and Bake has already released the CPU copy. A tight mesh would
            // also save nothing here - every one of these glyphs fills most of
            // its box.
            Sprite sprite = Sprite.Create(
                texture, new Rect(0f, 0f, texture.width, texture.height),
                new Vector2(0.5f, 0.5f), 100f * painter.Scale, 0,
                SpriteMeshType.FullRect, Vector4.zero);
            sprite.name = name;
            _drawn.Add(sprite);
            return sprite;
        }

        Texture2D Bake(Painter painter)
        {
            Texture2D texture = painter.Bake();
            _drawn.Add(texture);
            return texture;
        }

        /// <summary>
        /// Gives back every texture and sprite this HUD painted.
        ///
        /// They are runtime objects with no owner in the scene, so nothing else
        /// would: a play mode run that builds and tears down a HUD per test
        /// would leave one set behind each time. Destroy and not
        /// DestroyImmediate, and only while playing, because this class is
        /// reachable from edit-mode tooling and DestroyImmediate on an asset is
        /// how a checkout loses a file.
        /// </summary>
        void OnDestroy()
        {
            if (!Application.isPlaying)
            {
                return;
            }
            for (var i = 0; i < _drawn.Count; i++)
            {
                if (_drawn[i] != null)
                {
                    Destroy(_drawn[i]);
                }
            }
            _drawn.Clear();
            _roundedSprites.Clear();
        }

        /// <summary>
        /// A tiny software rasteriser: the whole of this tier's art, in one
        /// primitive.
        ///
        /// Every glyph here is a rounded rectangle, filled or stroked, and a
        /// circle is the case where both half-extents are zero. Written as a
        /// signed distance rather than as pixels because the distance is what
        /// gives antialiasing for free: coverage is how far inside the shape a
        /// texel's centre falls, measured in texels, which is exactly the
        /// fraction of that texel the shape covers along a straight edge and a
        /// close enough approximation on a curve.
        ///
        /// Shapes ACCUMULATE by taking the larger coverage, so drawing a nub
        /// under a shell leaves no seam between them: a pixel that belongs to
        /// both is fully covered once, not twice. That is also why nothing here
        /// writes colour. A glyph is a single-colour mask and the Image tints
        /// it, which keeps the palette in one place (the constants at the top)
        /// instead of baked into a texture nobody can read.
        /// </summary>
        sealed class Painter
        {
            readonly float[] _cover;
            readonly int _width;
            readonly int _height;
            readonly int _scale;

            public Painter(float widthPx, float heightPx, int scale)
            {
                _scale = scale;
                _width = Mathf.Max(1, Mathf.RoundToInt(widthPx * scale));
                _height = Mathf.Max(1, Mathf.RoundToInt(heightPx * scale));
                _cover = new float[_width * _height];
            }

            public int Scale
            {
                get { return _scale; }
            }

            /// <summary>
            /// A rounded rectangle centred on (cx, cy) with the given
            /// half-extents OUTSIDE the corner radius, so the shape's real
            /// half-size is half + radius. A stroke of zero fills it; anything
            /// else draws a band of that width centred on the outline.
            /// </summary>
            public void RoundedRect(float cx, float cy, float halfW, float halfH,
                float radius, float stroke)
            {
                // Everything is measured in reference pixels and only turned
                // into texels at the end, so the ramp is one texel wide
                // whatever the supersampling is.
                float ramp = _scale;
                float half = stroke * 0.5f;
                for (var y = 0; y < _height; y++)
                {
                    float py = (y + 0.5f) / _scale;
                    for (var x = 0; x < _width; x++)
                    {
                        float px = (x + 0.5f) / _scale;
                        float dx = Mathf.Abs(px - cx) - halfW;
                        float dy = Mathf.Abs(py - cy) - halfH;
                        float ax = Mathf.Max(dx, 0f);
                        float ay = Mathf.Max(dy, 0f);
                        float d = Mathf.Sqrt(ax * ax + ay * ay)
                            + Mathf.Min(Mathf.Max(dx, dy), 0f) - radius;
                        if (stroke > 0f)
                        {
                            d = Mathf.Abs(d) - half;
                        }
                        float cover = Mathf.Clamp01(0.5f - d * ramp);
                        int at = y * _width + x;
                        if (cover > _cover[at])
                        {
                            _cover[at] = cover;
                        }
                    }
                }
            }

            public void Disc(float cx, float cy, float radius)
            {
                RoundedRect(cx, cy, 0f, 0f, radius, 0f);
            }

            public void Circle(float cx, float cy, float radius, float stroke)
            {
                RoundedRect(cx, cy, 0f, 0f, radius, stroke);
            }

            /// <summary>
            /// White everywhere, with the coverage in the alpha. Bilinear so a
            /// glyph drawn between two sizes stays smooth, clamped so the edge
            /// texel cannot wrap to the far side, and handed back with its CPU
            /// copy released: nothing reads these pixels again.
            /// </summary>
            public Texture2D Bake()
            {
                var texture = new Texture2D(_width, _height, TextureFormat.RGBA32, false, true);
                texture.filterMode = FilterMode.Bilinear;
                texture.wrapMode = TextureWrapMode.Clamp;
                texture.anisoLevel = 0;
                var pixels = new Color32[_cover.Length];
                for (var i = 0; i < _cover.Length; i++)
                {
                    pixels[i] = new Color32(255, 255, 255,
                        (byte)Mathf.RoundToInt(Mathf.Clamp01(_cover[i]) * 255f));
                }
                texture.SetPixels32(pixels);
                texture.Apply(false, true);
                return texture;
            }
        }
    }
}
