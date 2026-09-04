using System.Collections;
using TMPro;
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

        // ---- Widgets --------------------------------------------------------

        Canvas _canvas;
        RectTransform _canvasRect;
        TextMeshProUGUI _batteryLabel;
        TextMeshProUGUI _filmLabel;
        TextMeshProUGUI _promptLabel;
        TextMeshProUGUI _toastLabel;
        TextMeshProUGUI _rewindLabel;
        TextMeshProUGUI _bannerTitle;
        TextMeshProUGUI _bannerSubtitle;
        TextMeshProUGUI _heldTitle;
        TextMeshProUGUI _heldHint;

        RawImage _photoView;
        RectTransform _photoViewRect;
        RectTransform _viewfinder;
        RectTransform[] _viewfinderDims;
        RectTransform[] _viewfinderEdges;
        RectTransform[] _viewfinderBrackets;
        RectTransform _heldPanel;
        PhotoCard _heldCard;
        PhotoCardShadow _heldCardShadow;
        CanvasGroup _bannerGroup;
        Image _fade;
        Image _rewindTint;

        float _bannerTimer;
        float _toastTimer;
        float _lastSquareSide = -1f;

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
            OnBatteriesChanged(State.CarriedBatteries, State.InsertedBatteries, State.RequiredBatteries);
            OnFilmsChanged(State.CameraFilms);
        }

        void OnDisable()
        {
            State.BatteriesChanged -= OnBatteriesChanged;
            State.FilmsChanged -= OnFilmsChanged;
        }

        void Update()
        {
            float dt = Time.unscaledDeltaTime;

            if (_bannerTimer > 0f)
            {
                _bannerTimer -= dt;
                // Fades in over the first two thirds of a second and out over the
                // last, exactly the curve of the original.
                float alpha = Mathf.Clamp01(Mathf.Min(_bannerTimer, BannerSeconds - _bannerTimer) * 1.5f);
                _bannerGroup.alpha = alpha;
            }
            else if (_bannerGroup.alpha != 0f)
            {
                _bannerGroup.alpha = 0f;
            }

            if (_toastTimer > 0f)
            {
                _toastTimer -= dt;
                if (_toastTimer <= 0f)
                {
                    _toastLabel.gameObject.SetActive(false);
                }
            }

            // The square depends on the viewport height, so it is re-derived
            // whenever the window changes rather than cached at build time.
            float side = SquareSide();
            if (!Mathf.Approximately(side, _lastSquareSide))
            {
                _lastSquareSide = side;
                LayoutSquare(side);
            }
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

        void LayoutSquare(float side)
        {
            _photoViewRect.sizeDelta = new Vector2(side, side);

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
        /// re-subscribe the counters) on every menu toggle.
        /// </summary>
        public void SetVisible(bool visible)
        {
            if (_canvas != null && _canvas.enabled != visible)
            {
                _canvas.enabled = visible;
            }
        }

        public void SetPrompt(string text)
        {
            _promptLabel.text = text ?? string.Empty;
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
        /// </summary>
        public void SetPhotoView(Texture2D texture, int rollSteps = 0)
        {
            bool visible = texture != null;
            if (_photoView.gameObject.activeSelf != visible)
            {
                _photoView.gameObject.SetActive(visible);
            }
            if (!visible)
            {
                return;
            }
            _photoView.texture = texture;
            _photoViewRect.localRotation = Quaternion.Euler(0f, 0f, -90f * rollSteps);
        }

        public void SetViewfinder(bool active)
        {
            if (_viewfinder.gameObject.activeSelf != active)
            {
                _viewfinder.gameObject.SetActive(active);
            }
        }

        /// <summary>
        /// The held-photo panel. The card steps aside while the photo is raised:
        /// the full picture in front of the player replaces it.
        /// </summary>
        public void SetHeld(string title, Texture2D texture, bool raised)
        {
            bool holding = !string.IsNullOrEmpty(title);
            if (_heldPanel.gameObject.activeSelf != holding)
            {
                _heldPanel.gameObject.SetActive(holding);
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

        public void SetRewinding(bool active, float secondsLeft)
        {
            if (_rewindTint.gameObject.activeSelf != active)
            {
                _rewindTint.gameObject.SetActive(active);
                _rewindLabel.gameObject.SetActive(active);
            }
            if (active)
            {
                _rewindLabel.text = string.Format(
                    System.Globalization.CultureInfo.InvariantCulture,
                    "REMBOBINAGE   {0:0.0} s d'historique", secondsLeft);
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
            _toastTimer = ToastSeconds;
        }

        /// <summary>Fades to black over 0.6 s. Yield on it to wait for the black.</summary>
        public IEnumerator FadeOut()
        {
            yield return Fade(1f);
        }

        public void FadeIn()
        {
            StartCoroutine(Fade(0f));
        }

        IEnumerator Fade(float target)
        {
            Color from = _fade.color;
            float start = from.a;
            float elapsed = 0f;
            while (elapsed < FadeSeconds)
            {
                // Unscaled: a fade must finish even if something has stopped time.
                elapsed += Time.unscaledDeltaTime;
                float a = Mathf.Lerp(start, target, Mathf.Clamp01(elapsed / FadeSeconds));
                _fade.color = new Color(FadeColor.r, FadeColor.g, FadeColor.b, a);
                yield return null;
            }
            _fade.color = new Color(FadeColor.r, FadeColor.g, FadeColor.b, target);
        }

        void OnBatteriesChanged(int carried, int inserted, int required)
        {
            _batteryLabel.text = string.Format(
                "Piles : {0} portee{1}   |   Teleporteur : {2} / {3}",
                carried, carried > 1 ? "s" : "", inserted, required);
        }

        void OnFilmsChanged(int films)
        {
            bool visible = films > 0;
            if (_filmLabel.gameObject.activeSelf != visible)
            {
                _filmLabel.gameObject.SetActive(visible);
            }
            if (visible)
            {
                _filmLabel.text = "Pellicule : " + films
                    + "   (clic droit : viser   clic gauche : declencher)";
            }
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
                TextAlignmentOptions.TopLeft, OutlineStrong);
            AnchorTopLeft(_batteryLabel.rectTransform, BatteryOffset, new Vector2(900f, 34f));

            _filmLabel = NewLabel("Films", root, FilmSizePx, FilmColor,
                TextAlignmentOptions.TopLeft, OutlineStrong);
            AnchorTopLeft(_filmLabel.rectTransform, FilmOffset, new Vector2(900f, 30f));
            _filmLabel.gameObject.SetActive(false);
        }

        void BuildPhotoView(Transform root)
        {
            RectTransform rect = NewRect("PhotoView", root);
            SetCentered(rect, Vector2.zero, new Vector2(ReferenceResolution.y, ReferenceResolution.y));
            _photoView = rect.gameObject.AddComponent<RawImage>();
            _photoView.raycastTarget = false;
            _photoViewRect = rect;
            rect.gameObject.SetActive(false);
        }

        void BuildViewfinder(Transform root)
        {
            RectTransform rect = NewRect("Viewfinder", root);
            Stretch(rect);
            _viewfinder = rect;

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

            // Four corners, two arms each, two passes (dark under light).
            _viewfinderBrackets = new RectTransform[16];
            var index = 0;
            for (var corner = 0; corner < 4; corner++)
            {
                for (var pass = 0; pass < 2; pass++)
                {
                    for (var arm = 0; arm < 2; arm++)
                    {
                        _viewfinderBrackets[index] = NewRect("Bracket" + index, rect);
                        NewImage(_viewfinderBrackets[index], pass == 0 ? BracketDark : BracketLight);
                        index++;
                    }
                }
            }

            rect.gameObject.SetActive(false);
        }

        void BuildPrompt(Transform root)
        {
            _promptLabel = NewLabel("Prompt", root, PromptSizePx, Color.white,
                TextAlignmentOptions.Center, OutlineStrong);
            RectTransform rect = _promptLabel.rectTransform;
            rect.anchorMin = new Vector2(0.5f, 0f);
            rect.anchorMax = new Vector2(0.5f, 0f);
            rect.pivot = new Vector2(0.5f, 0f);
            rect.anchoredPosition = new Vector2(0f, PromptBottomPx);
            rect.sizeDelta = new Vector2(1200f, 34f);
        }

        void BuildHeldPanel(Transform root)
        {
            RectTransform panel = NewRect("HeldPanel", root);
            panel.anchorMin = new Vector2(1f, 0f);
            panel.anchorMax = new Vector2(1f, 0f);
            panel.pivot = new Vector2(1f, 0f);
            panel.anchoredPosition = new Vector2(-HeldMarginPx, HeldMarginPx);
            panel.sizeDelta = new Vector2(520f, 150f);
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
                TextAlignmentOptions.Right, OutlineSoft);
            _heldHint = NewLabel("HeldHint", panel, HeldHintSizePx, HeldHintColor,
                TextAlignmentOptions.Right, OutlineSoft);
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
                TextAlignmentOptions.Center, OutlineSoft);
            _bannerSubtitle = NewLabel("BannerSubtitle", banner, BannerSubtitleSizePx,
                BannerSubtitleColor, TextAlignmentOptions.Center, OutlineSoft);
        }

        void BuildToast(Transform root)
        {
            _toastLabel = NewLabel("Toast", root, ToastSizePx, ToastColor,
                TextAlignmentOptions.Center, OutlineStrong);
            RectTransform rect = _toastLabel.rectTransform;
            rect.anchorMin = new Vector2(0.5f, 0f);
            rect.anchorMax = new Vector2(0.5f, 0f);
            rect.pivot = new Vector2(0.5f, 0f);
            rect.anchoredPosition = new Vector2(0f, ToastBottomPx);
            rect.sizeDelta = new Vector2(1200f, 30f);
            _toastLabel.gameObject.SetActive(false);
        }

        void BuildRewind(Transform root)
        {
            RectTransform tint = NewRect("RewindTint", root);
            Stretch(tint);
            _rewindTint = NewImage(tint, RewindTint);
            tint.gameObject.SetActive(false);

            _rewindLabel = NewLabel("RewindLabel", root, RewindSizePx, RewindColor,
                TextAlignmentOptions.Center, OutlineStrong);
            RectTransform rect = _rewindLabel.rectTransform;
            rect.anchorMin = new Vector2(0.5f, 1f);
            rect.anchorMax = new Vector2(0.5f, 1f);
            rect.pivot = new Vector2(0.5f, 1f);
            rect.anchoredPosition = new Vector2(0f, -RewindTopPx);
            rect.sizeDelta = new Vector2(1200f, 42f);
            _rewindLabel.gameObject.SetActive(false);
        }

        void BuildFade(Transform root)
        {
            // Last child, so it covers everything the HUD drew above.
            RectTransform rect = NewRect("Fade", root);
            Stretch(rect);
            _fade = NewImage(rect, new Color(FadeColor.r, FadeColor.g, FadeColor.b, 0f));
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

        /// <summary>
        /// A TextMeshPro line on the default font asset: no font file ships with
        /// the project, and TMP_Text resolves TMP_Settings' default when it
        /// awakes with none.
        /// </summary>
        static TextMeshProUGUI NewLabel(string name, Transform parent, float sizePx,
            Color color, TextAlignmentOptions alignment, Color outlineColor)
        {
            RectTransform rect = NewRect(name, parent);
            var label = rect.gameObject.AddComponent<TextMeshProUGUI>();
            label.fontSize = sizePx;
            label.color = color;
            label.alignment = alignment;
            label.raycastTarget = false;
            label.richText = false;
            label.text = string.Empty;
            // Font first, outline second, and both through Fonts: the outline
            // makes TMP instance the font's material, so on a label with no font
            // asset it throws. No font at all is a legitimate headless case.
            Fonts.Apply(label, outlineColor, OutlineWidth);
            return label;
        }
    }
}
