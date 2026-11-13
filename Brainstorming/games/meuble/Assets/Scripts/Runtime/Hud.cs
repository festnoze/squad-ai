using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Meuble
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
    /// </summary>
    public sealed class Hud : MonoBehaviour
    {
        /// <summary>Open in both seen states (calm and alarm), closed when unseen.</summary>
        public bool EyeOpen { get; private set; }

        /// <summary>M2.1: which of the three eye states shows.</summary>
        public HudEye Eye { get; private set; }
        public bool FailVisible => failCanvas != null && failCanvas.enabled;
        public bool WinVisible => winCanvas != null && winCanvas.enabled;
        public Font Font { get; private set; }

        /// <summary>Every label by name, for the built player check (labels must carry text).</summary>
        public readonly Dictionary<string, Text> Labels = new Dictionary<string, Text>();

        private Canvas rootCanvas;
        private Canvas failCanvas;
        private Canvas winCanvas;
        private Image eye;
        private Image eyeBackdrop;
        private Image pulse;
        private CanvasGroup titleCard;
        private Text winBody;
        private float seenMoving;
        private float titleTimer;

        // ----- M2 (docs/CONTRACT_M2.md 7): creak gauge, suspicion bar, suspicion fail panel, win.next. -----

        /// <summary>Creak gauge value shown (0 to 1) and whether it flashes (the creak warning).</summary>
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

        private Canvas creakCanvas;
        private Canvas suspicionCanvas;
        private Canvas winNextCanvas;
        private RectTransform creakFill;
        private Image creakFillImage;
        private Image creakFrame;
        private RectTransform suspicionFill;
        private Image suspicionFillImage;
        private Text failTitle;
        private Text failBody;

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
                return band;
            }
        }

        // ----- M4 (docs/CONTRACT_M4.md 2 and 3): the hints of the current body and the sat-on line. -----

        /// <summary>"Maj : au ralenti" shows (every body while the Bodies rule is on).</summary>
        public bool CarefulHintVisible => carefulCanvas != null && carefulCanvas.enabled;

        /// <summary>"E : éteindre / allumer" shows (the floor lamp body while the Lamp rule is on).</summary>
        public bool LampHintVisible => lampCanvas != null && lampCanvas.enabled;

        /// <summary>"Quelqu'un est assis sur toi." shows (the player furniture is pinned by a sitter).</summary>
        public bool SatOnVisible => satOnCanvas != null && satOnCanvas.enabled;

        /// <summary>M4.1: "Renversé : appuie sur une direction pour te relever." shows (the stool lies on its side).</summary>
        public bool TippedVisible => tippedCanvas != null && tippedCanvas.enabled;

        private Canvas carefulCanvas;
        private Canvas lampCanvas;
        private Canvas satOnCanvas;
        private Canvas tippedCanvas;
        private bool tippedOn;
        private bool carefulOn;
        private bool lampOn;
        private bool satOn;

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
        private const float GaugeY = 96f;
        private const float ActionY = -110f;
        private const float EndActionY = -150f;
        // M4: the sat-on line, just above the eye backdrop (80 + 128 px).
        private const float SatOnY = 222f;
        private static readonly Color SatOnPlate = new Color(0.12f, 0.1f, 0.14f, 0.82f);
        private static readonly Color SatOnInk = new Color(1f, 0.9f, 0.62f, 1f);

        private static readonly Color BackdropClosed = new Color(0.1f, 0.1f, 0.12f, 0.55f);
        private static readonly Color BackdropCalm = new Color(0.16f, 0.3f, 0.42f, 0.85f);
        private static readonly Color BackdropAlarm = new Color(0.78f, 0.12f, 0.14f, 0.9f);
        private static readonly Color GaugeBack = new Color(0.1f, 0.1f, 0.12f, 0.78f);
        private static readonly Color GaugeRim = new Color(1f, 0.97f, 0.9f, 0.55f);
        private static readonly Color CreakWood = new Color(0.86f, 0.62f, 0.34f, 1f);
        private static readonly Color CreakHot = new Color(1f, 0.28f, 0.18f, 1f);
        private static readonly Color SuspicionLow = new Color(1f, 0.8f, 0.25f, 1f);
        private static readonly Color SuspicionHigh = new Color(0.95f, 0.2f, 0.15f, 1f);

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

            eyeBackdrop = NewImage(transform, "EyeBackdrop", ProceduralArt.Disc, BackdropClosed);
            Place(eyeBackdrop.rectTransform, new Vector2(0.5f, 0f), new Vector2(0f, EyeY), new Vector2(210f, 128f));
            eye = NewImage(eyeBackdrop.transform, "Eye", ProceduralArt.EyeClosed, Color.white);
            Place(eye.rectTransform, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(170f, 99f));

            Text controls = NewText(transform, "Controls", Strings.HudControls, 30, TextAnchor.LowerCenter, new Color(1f, 1f, 1f, 0.92f));
            Place(controls.rectTransform, new Vector2(0.5f, 0f), new Vector2(0f, ControlsY), new Vector2(1600f, 50f));

            var cardGo = new GameObject("TitleCard", typeof(RectTransform));
            cardGo.transform.SetParent(transform, false);
            titleCard = cardGo.AddComponent<CanvasGroup>();
            titleCard.interactable = false;
            titleCard.blocksRaycasts = false;
            Place((RectTransform)cardGo.transform, new Vector2(0.5f, 0.5f), new Vector2(0f, 190f), new Vector2(1600f, 300f));
            Text title = NewText(cardGo.transform, "Title", Strings.Title, 40, TextAnchor.MiddleCenter, new Color(1f, 0.92f, 0.75f, 1f));
            Place(title.rectTransform, new Vector2(0.5f, 1f), new Vector2(0f, -30f), new Vector2(1600f, 60f));
            Text levelName = NewText(cardGo.transform, "LevelName", Strings.Level1Name, 84, TextAnchor.MiddleCenter, Color.white);
            Place(levelName.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, 10f), new Vector2(1600f, 110f));
            Text hint = NewText(cardGo.transform, "Hint", Strings.Level1Hint, 38, TextAnchor.MiddleCenter, new Color(1f, 1f, 1f, 0.95f));
            Place(hint.rectTransform, new Vector2(0.5f, 0f), new Vector2(0f, 30f), new Vector2(1600f, 60f));

            BuildCreakGauge();
            BuildSuspicionGauge();
            BuildBodyHints();

            failCanvas = NewPanel("FailPanel", Strings.FailTitle, Strings.FailBody, Strings.FailAction, new Color(0.25f, 0.02f, 0.03f, 0.62f),
                new Color(1f, 0.42f, 0.38f, 1f), out failBody);
            Labels.TryGetValue("FailPanelTitle", out failTitle);
            winCanvas = NewPanel("WinPanel", Strings.WinTitle, string.Format(Strings.WinBody, "0,0"), Strings.WinAction,
                new Color(0.02f, 0.16f, 0.08f, 0.58f), new Color(0.55f, 1f, 0.6f, 1f), out winBody);
            Labels.TryGetValue("WinPanelTitle", out winTitle);
            Labels.TryGetValue("WinPanelAction", out winAction);
            // win.next has its own Canvas inside the win panel: shown only when there is a next level.
            var nextGo = new GameObject("WinNextGroup", typeof(RectTransform));
            nextGo.transform.SetParent(winCanvas.transform, false);
            Stretch((RectTransform)nextGo.transform);
            winNextCanvas = nextGo.AddComponent<Canvas>();
            Text next = NewText(nextGo.transform, "WinNext", Strings.WinNext, 38, TextAnchor.MiddleCenter, new Color(1f, 0.93f, 0.6f, 1f));
            Place(next.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, -170f), new Vector2(1600f, 60f));
            BuildEndGroup();
            HidePanels();
        }

        /// <summary>Creak gauge (PRD 4.6), left of the eye: crack icon, "Grincement", a bar filling to the right.</summary>
        private void BuildCreakGauge()
        {
            creakCanvas = BuildBar("CreakGauge", new Vector2(1f, 0f), new Vector2(-128f, GaugeY), ProceduralArt.Creak, "CreakLabel",
                Strings.HudCreak, CreakWood, out creakFrame, out creakFill, out creakFillImage);
            creakRect = (RectTransform)creakCanvas.transform;
            SetCreak(0f, false);
        }

        /// <summary>Suspicion bar (PRD 4.4), right of the eye: magnifier icon, "Soupçon", the highest suspicion.</summary>
        private void BuildSuspicionGauge()
        {
            suspicionCanvas = BuildBar("SuspicionGauge", new Vector2(0f, 0f), new Vector2(128f, GaugeY), ProceduralArt.Magnifier,
                "SuspicionLabel", Strings.HudSuspicion, SuspicionLow, out _, out suspicionFill, out suspicionFillImage);
            suspicionRect = (RectTransform)suspicionCanvas.transform;
            SetSuspicion(0f);
        }

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
            // M4.1 (CONTRACT_M4 10.3): the same row; a stool lying on its side is never sat on.
            tippedCanvas = BuildLine("Tipped", ProceduralArt.Tipped, Strings.HudTipped, 1180f);
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
            endTime = NewText(go.transform, "EndTime", string.Format(Strings.WinBody, "0,0"), 40, TextAnchor.MiddleCenter,
                new Color(1f, 1f, 1f, 0.92f));
            Place(endTime.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, -82f), new Vector2(1600f, 60f));
            EndButton = MenuButton(go.transform, "EndMenuButton", Strings.PauseMenu, Font, Labels);
            Place((RectTransform)EndButton.transform, new Vector2(0.5f, 0.5f), new Vector2(0f, -250f), new Vector2(480f, 88f));
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
            colors.selectedColor = new Color(0.78f, 0.16f, 0.15f, 0.97f);
            colors.pressedColor = new Color(0.5f, 0.08f, 0.08f, 1f);
            colors.disabledColor = new Color(0.2f, 0.2f, 0.2f, 0.5f);
            colors.colorMultiplier = 1f;
            colors.fadeDuration = 0.08f;
            button.colors = colors;
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
        /// A labelled bar in its own Canvas: icon and label on the first row, the bar (rim, background, fill
        /// sized by its anchors) on the second. <paramref name="pivot"/> places the group beside the eye.
        /// </summary>
        private Canvas BuildBar(string name, Vector2 pivot, Vector2 offset, Sprite icon, string labelName, string label, Color fillColor,
            out Image back, out RectTransform fill, out Image fillImage)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(transform, false);
            var rect = (RectTransform)go.transform;
            rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0f);
            rect.pivot = pivot;
            rect.anchoredPosition = offset;
            rect.sizeDelta = new Vector2(330f, 92f);
            Canvas canvas = go.AddComponent<Canvas>();
            Image iconImage = NewImage(go.transform, name + "Icon", icon, Color.white);
            Place(iconImage.rectTransform, new Vector2(0f, 1f), Vector2.zero, new Vector2(46f, 46f));
            Text text = NewText(go.transform, labelName, label, 32, TextAnchor.MiddleLeft, Color.white);
            Place(text.rectTransform, new Vector2(0f, 1f), new Vector2(54f, 0f), new Vector2(276f, 46f));
            Image rim = NewImage(go.transform, name + "Rim", null, GaugeRim);
            Place(rim.rectTransform, new Vector2(0f, 0f), Vector2.zero, new Vector2(330f, 36f));
            back = NewImage(rim.transform, name + "Back", null, GaugeBack);
            var backRect = back.rectTransform;
            backRect.anchorMin = Vector2.zero;
            backRect.anchorMax = Vector2.one;
            backRect.offsetMin = new Vector2(2f, 2f);
            backRect.offsetMax = new Vector2(-2f, -2f);
            fillImage = NewImage(Track(back.transform), name + "Fill", null, fillColor);
            fill = fillImage.rectTransform;
            fill.pivot = new Vector2(0f, 0.5f);
            fill.anchorMin = Vector2.zero;
            fill.anchorMax = new Vector2(0f, 1f);
            fill.offsetMin = Vector2.zero;
            fill.offsetMax = Vector2.zero;
            return canvas;
        }

        /// <summary>An empty rect 3 px inside a gauge background: the fill is sized by its anchors only.</summary>
        private static Transform Track(Transform background)
        {
            var go = new GameObject("Track", typeof(RectTransform));
            go.transform.SetParent(background, false);
            var rect = (RectTransform)go.transform;
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = new Vector2(3f, 3f);
            rect.offsetMax = new Vector2(-3f, -3f);
            return go.transform;
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
            SetEnabled(creakCanvas, Visible && creakOn);
            SetEnabled(suspicionCanvas, Visible && suspicionOn);
            SetEnabled(failCanvas, Visible && failOn);
            SetEnabled(winCanvas, Visible && winOn);
            SetEnabled(winNextCanvas, Visible && winOn && winNextOn);
            SetEnabled(endCanvas, Visible && winOn && endOn);
            SetEnabled(carefulCanvas, Visible && carefulOn);
            SetEnabled(lampCanvas, Visible && lampOn);
            SetEnabled(satOnCanvas, Visible && satOn && !failOn && !winOn);
            SetEnabled(tippedCanvas, Visible && tippedOn && !satOn && !failOn && !winOn);
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
            if (creakFill != null)
            {
                creakFill.anchorMax = new Vector2(CreakShown, 1f);
            }
        }

        /// <summary>Called by GameState on every fixed step with the highest suspicion.</summary>
        public void SetSuspicion(float value)
        {
            SuspicionShown = Mathf.Clamp01(value);
            if (suspicionFill != null)
            {
                suspicionFill.anchorMax = new Vector2(SuspicionShown, 1f);
                suspicionFillImage.color = Color.Lerp(SuspicionLow, SuspicionHigh, SuspicionShown);
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
        /// </summary>
        public void SetEye(HudEye state, float seenMovingTime)
        {
            Eye = state;
            EyeOpen = state != HudEye.Closed;
            seenMoving = seenMovingTime;
            if (eye != null)
            {
                eye.sprite = state == HudEye.Closed ? ProceduralArt.EyeClosed : state == HudEye.Calm ? ProceduralArt.EyeOpen : ProceduralArt.EyeAlarm;
                eyeBackdrop.color = state == HudEye.Closed ? BackdropClosed : state == HudEye.Calm ? BackdropCalm : BackdropAlarm;
            }
        }

        public void ShowLevel(LevelDef level)
        {
            HidePanels();
            if (Labels.TryGetValue("LevelName", out Text name))
            {
                name.text = Strings.Get(level.NameKey);
            }
            if (Labels.TryGetValue("Hint", out Text hint))
            {
                hint.text = Strings.Get(level.HintKey);
            }
            titleTimer = 0f;
            if (titleCard != null)
            {
                titleCard.alpha = 1f;
            }
            SetSeen(false, 0f);
            SetCreak(0f, false);
            SetSuspicion(0f);
            SetSatOn(false);
            SetTipped(false);
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
            winBody.text = string.Format(Strings.WinBody, Strings.FormatSeconds(seconds));
            if (winAction != null)
            {
                winAction.rectTransform.anchoredPosition = new Vector2(0f, ActionY);
            }
            winNextOn = hasNext;
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
        }

        public float TitleCardAlpha => titleCard != null ? titleCard.alpha : 0f;

        public void HidePanels()
        {
            failOn = false;
            winOn = false;
            endOn = false;
            ApplyCanvases();
            FailReason = LoseReason.None;
        }

        private void Update()
        {
            if (pulse == null)
            {
                return;
            }
            // Creak warning: the gauge flashes between wood and hot red, fast enough to catch the eye.
            if (creakFillImage != null)
            {
                bool on = CreakFlashing && Mathf.Repeat(Time.unscaledTime * 6f, 1f) < 0.5f;
                creakFillImage.color = CreakFlashing ? (on ? CreakHot : Color.white) : CreakWood;
                creakFrame.color = CreakFlashing && on ? new Color(0.55f, 0.08f, 0.06f, 0.85f) : GaugeBack;
            }
            // PRD 4.3: the screen edge pulses red while seenMoving is above zero.
            float a = seenMoving > 0f ? 0.45f + 0.35f * Mathf.Sin(Time.unscaledTime * 18f) : 0f;
            Color c = pulse.color;
            c.a = Mathf.MoveTowards(c.a, a, Time.unscaledDeltaTime * 8f);
            if (seenMoving > 0f)
            {
                c.a = a;
            }
            pulse.color = c;

            titleTimer += Time.unscaledDeltaTime;
            if (titleCard != null)
            {
                titleCard.alpha = titleTimer < 4f ? 1f : Mathf.Clamp01(1f - (titleTimer - 4f));
            }
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

    /// <summary>The three states of the HUD eye (docs/CONTRACT_M2.md 11.6).</summary>
    public enum HudEye
    {
        Closed,
        Calm,
        Alarm,
    }
}
