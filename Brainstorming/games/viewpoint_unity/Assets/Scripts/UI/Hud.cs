using System.Collections;
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
    /// </summary>
    public sealed class Hud : MonoBehaviour
    {
        static readonly Vector2 ReferenceResolution = new Vector2(1600f, 900f);

        /// <summary>Under the menu, which sits at 100.</summary>
        const int SortingOrder = 50;

        // ---- PRD 12.1 -------------------------------------------------------

        const float CrosshairPx = 5f;
        static readonly Color CrosshairColor = new Color(1f, 1f, 1f, 0.85f);

        const float BatterySizePx = 22f;
        static readonly Vector2 BatteryOffset = new Vector2(24f, 20f);

        const float FilmSizePx = 20f;
        static readonly Vector2 FilmOffset = new Vector2(24f, 52f);
        static readonly Color FilmColor = new Color(0.75f, 0.95f, 0.93f);

        const float PromptSizePx = 22f;
        const float PromptBottomPx = 120f;

        const float HeldMarginPx = 24f;
        const float HeldPanelWidthPx = 520f;
        const float HeldTitleSizePx = 22f;
        const float HeldHintSizePx = 15f;
        static readonly Vector2 HeldPanelMinSize = new Vector2(86f, 78f);
        static readonly Color HeldHintColor = new Color(1f, 1f, 1f, 0.75f);

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
        Text _promptLabel;
        Text _toastLabel;
        Text _rewindLabel;
        Text _bannerTitle;
        Text _bannerSubtitle;
        Text _heldTitle;
        Text _heldHint;

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
        CanvasGroup _bannerGroup;
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
                // banner keeps this curve, so nothing here changed.
                float alpha = Mathf.Clamp01(Mathf.Min(_bannerTimer, BannerSeconds - _bannerTimer) * 1.5f);
                _bannerGroup.alpha = alpha;
            }
            else if (_bannerGroup.alpha != 0f)
            {
                _bannerGroup.alpha = 0f;
            }

            StepToast(dt);
            StepPop(_batteryPop, _batteryLabel.rectTransform, dt);
            StepPop(_filmPop, _filmLabel.rectTransform, dt);
            _promptFader.Step(dt);
            _filmFader.Step(dt);
            StepPrompt();
            StepHeld(dt);
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
        /// </summary>
        public void SetPrompt(string text)
        {
            string wanted = text ?? string.Empty;
            if (wanted.Length == 0)
            {
                _promptFader.Hide(PromptOutSeconds);
                return;
            }
            if (_promptLabel.text != wanted)
            {
                _promptLabel.text = wanted;
            }
            _promptFader.Show(PromptInSeconds);
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
            bool showCard = texture != null && !raised;
            _heldCard.Texture = showCard ? texture : null;
            _heldCardShadow.Visible = showCard;
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

        public void ShowBanner(string title, string subtitle)
        {
            _bannerTitle.text = title ?? string.Empty;
            _bannerSubtitle.text = subtitle ?? string.Empty;
            _bannerTimer = BannerSeconds;
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
        /// The counter pop. Applied to the label's own rect, whose pivot is its
        /// top left ANCHOR, so the line swells towards the middle of the screen
        /// and its PRD 12.1 offset from the corner never moves.
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
            // Cleared only once the words have actually finished leaving.
            if (_promptFader.Hidden && _promptLabel.text.Length > 0)
            {
                _promptLabel.text = string.Empty;
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

        void BuildCrosshair(Transform root)
        {
            RectTransform rect = NewRect("Crosshair", root);
            SetCentered(rect, Vector2.zero, new Vector2(CrosshairPx, CrosshairPx));
            NewImage(rect, CrosshairColor);
        }

        void BuildCounters(Transform root)
        {
            _batteryLabel = NewLabel("Batteries", root, BatterySizePx, Color.white,
                TextAnchor.UpperLeft, OutlineStrong);
            AnchorTopLeft(_batteryLabel.rectTransform, BatteryOffset, new Vector2(900f, 34f));

            _filmLabel = NewLabel("Films", root, FilmSizePx, FilmColor,
                TextAnchor.UpperLeft, OutlineStrong);
            AnchorTopLeft(_filmLabel.rectTransform, FilmOffset, new Vector2(900f, 30f));
            _filmFader = NewFader(_filmLabel.gameObject);
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

        void BuildPrompt(Transform root)
        {
            _promptLabel = NewLabel("Prompt", root, PromptSizePx, Color.white,
                TextAnchor.MiddleCenter, OutlineStrong);
            RectTransform rect = _promptLabel.rectTransform;
            rect.anchorMin = new Vector2(0.5f, 0f);
            rect.anchorMax = new Vector2(0.5f, 0f);
            rect.pivot = new Vector2(0.5f, 0f);
            rect.anchoredPosition = new Vector2(0f, PromptBottomPx);
            rect.sizeDelta = new Vector2(1200f, 34f);
            _promptFader = NewFader(_promptLabel.gameObject);
        }

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
            panel.sizeDelta = new Vector2(HeldPanelWidthPx, 150f);
            NewImage(panel, new Color(0.08f, 0.10f, 0.14f, 0.55f));
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
                TextAnchor.MiddleRight, OutlineSoft);
            _heldHint = NewLabel("HeldHint", panel, HeldHintSizePx, HeldHintColor,
                TextAnchor.MiddleRight, OutlineSoft);
            _heldHint.text = "Clic gauche : poser   Clic droit : lever   Molette : pivoter   F : reposer";

            panel.gameObject.SetActive(false);
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

            _bannerTitle = NewLabel("BannerTitle", banner, BannerTitleSizePx, Color.white,
                TextAnchor.MiddleCenter, OutlineSoft);
            _bannerSubtitle = NewLabel("BannerSubtitle", banner, BannerSubtitleSizePx,
                BannerSubtitleColor, TextAnchor.MiddleCenter, OutlineSoft);
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
        /// A label on the engine's builtin font. Everything about the font and
        /// the outline lives in Fonts, which also records why this is uGUI Text
        /// and not TextMeshPro: TMP cannot start in a player without an asset
        /// this project deliberately does not ship.
        /// </summary>
        static Text NewLabel(string name, Transform parent, float sizePx,
            Color color, TextAnchor alignment, Color outlineColor)
        {
            RectTransform rect = NewRect(name, parent);
            var label = rect.gameObject.AddComponent<Text>();
            Fonts.Apply(label, Mathf.RoundToInt(sizePx), color, alignment, true, outlineColor);
            return label;
        }
    }
}
