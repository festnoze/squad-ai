using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// TOUCHTUTO (2026-11-25, docs/next/progress/TOUCHTUTO.md): the level 1 touch tutorial, the validated mockup
    /// (Build/shots/tuto/tuto_mockup.png) drawn in code. A dark veil over the whole screen; two rounded zone panels on the
    /// touch split (<see cref="Tuning.TouchStickZoneShare"/>): the left third with the stick icon, "Move" and its caption,
    /// the right two thirds with the drag icon ("Turn") and the pinch icon ("Zoom") side by side; at the bottom centre, the
    /// gold "Tap the screen to play" on a dark pill. Titles bold and in capitals, captions lighter, in the HUD's font; the
    /// icons are <see cref="ProceduralArt"/> sprites, tinted the mockup's cream.
    ///
    /// When (<see cref="Wanted"/>): every time level 1 ("level1") is built and waits for its first input (a restart and a
    /// retry included: every build holds again), while the touch controls show (<see cref="InputReader.TouchUIActive"/>:
    /// never on a PC without touch), never in spectator mode, under a menu, the pause or the fail and win panels. It goes
    /// when the level starts. TouchControls owns it, decides it every frame (before Hud reads
    /// <see cref="TouchControls.TutorialShowing"/>) and routes the fingers: while it shows, a finger steers nothing and its
    /// lift is the start press (one tap anywhere dismisses it and starts the level, with no move and no camera turn). Hud
    /// hides what it replaces: the start line, the controls line and the intro card (whose text it would overlap).
    ///
    /// Its own root canvas, over the HUD (10, panels 20) and the touch overlay (30), under the menus (50); a CanvasScaler
    /// matched on the height, so a size here is that many pixels of a 1080 pixel high screen (the mockup's 2400 x 1080
    /// reference). Nothing is a raycast target. Built the first time it shows (a PC never draws its art), shown and
    /// hidden by enabling its Canvas, never its GameObject.
    /// </summary>
    public sealed class TouchTutorial
    {
        /// <summary>The level whose every build shows the tutorial on touch.</summary>
        public const string LevelId = "level1";

        /// <summary>The canvas sorting order: over the HUD (10, its panels 20) and the touch overlay (30), under the menus (50).</summary>
        public const int SortingOrder = 40;

        /// <summary>The canvas is on (tests).</summary>
        public bool Visible => canvas != null && canvas.enabled;

        /// <summary>The canvas (tests).</summary>
        public Canvas Canvas => canvas;

        /// <summary>The two zone panels (tests: they follow the touch split).</summary>
        public RectTransform MoveZone { get; private set; }
        public RectTransform CameraZone { get; private set; }

        /// <summary>Every text by name (MoveTitle, MoveCaption, TurnTitle, TurnCaption, ZoomTitle, ZoomCaption, TapLine; tests).</summary>
        public readonly Dictionary<string, Text> Labels = new Dictionary<string, Text>();

        // Layout in pixels of a 1080 pixel high screen, from the mockup (tuto.html at 2400 x 1080): the zone panels' margins
        // (screen edges, and each side of the split), the columns' items as offsets from the screen's vertical centre (the
        // mockup's flex columns, normal line heights), the gap between the two camera items, and the tap pill.
        private const float ReferenceHeight = 1080f;
        private const float ZoneEdge = 40f;
        private const float ZoneBottom = 120f;
        private const float ZoneSplitGap = 30f;
        private const float ZonePadding = 24f;
        private const float MoveIconSize = 300f;
        private const float MoveIconY = 102f;
        private const float MoveTitleY = -125f;
        private const float MoveCaptionY = -226f;
        private const float CameraIconSize = 260f;
        private const float CameraIconY = 90f;
        private const float CameraTitleY = -105f;
        private const float CameraCaptionY = -194f;
        private const float CameraItemGap = 200f;
        private const int TitleSize = 64;
        private const int CaptionSize = 38;
        private const float TitleHeight = 90f;
        private const float CaptionHeight = 56f;
        private const float TextBoxWidth = 1000f;
        private const int TapSize = 40;
        private const float TapBottom = 34f;
        private const float TapHeight = 81f;
        private const float TapPadding = 44f;
        // The Rounded sprite's 24 px border shown 40 units wide: the pill's ends are round.
        private const float TapCornerMultiplier = 0.6f;

        // The mockup's colours: the veil rgba(12, 8, 6, 0.58), the cream #F7F1E6 (captions at 0.85), the zone panels'
        // outline at 0.18 (TutorialZone holds the fill's 0.05 as a share of it), the gold #F2C14E on rgba(12, 8, 6, 0.55).
        private static readonly Color VeilColour = new Color(12f / 255f, 8f / 255f, 6f / 255f, 0.58f);
        private static readonly Color Ink = new Color(247f / 255f, 241f / 255f, 230f / 255f, 1f);
        private static readonly Color CaptionInk = new Color(247f / 255f, 241f / 255f, 230f / 255f, 0.85f);
        private static readonly Color ZoneTint = new Color(247f / 255f, 241f / 255f, 230f / 255f, 0.18f);
        private static readonly Color Gold = new Color(242f / 255f, 193f / 255f, 78f / 255f, 1f);
        private static readonly Color PillColour = new Color(12f / 255f, 8f / 255f, 6f / 255f, 0.55f);

        private readonly Canvas canvas;
        private readonly Font font;
        private readonly RectTransform moveContent;
        private readonly RectTransform cameraContent;
        private readonly RectTransform turnItem;
        private readonly RectTransform zoomItem;
        private readonly RectTransform tapPlate;
        private readonly Text moveTitle;
        private readonly Text moveCaption;
        private readonly Text turnTitle;
        private readonly Text turnCaption;
        private readonly Text zoomTitle;
        private readonly Text zoomCaption;
        private readonly Text tapLine;
        // What the texts and the layout were made for: rebuilt when the language or the screen changes.
        private string laidLanguage;
        private Vector2Int laidScreen;

        /// <summary>
        /// The tutorial is wanted now: level 1 built and waiting for its first input (not a spectator session), still playing,
        /// the touch controls up, no pause, no menu (the HUD shows) and no fail or win panel. TouchControls also requires its
        /// own overlay to show (the same touch, pause and panel conditions).
        /// </summary>
        public static bool Wanted(Main main)
        {
            GameState game = main != null ? main.Game : null;
            Hud hud = main != null ? main.Hud : null;
            if (game == null || hud == null || game.Level == null || game.Spectator || !game.AwaitingStart || game.State != PlayState.Playing)
            {
                return false;
            }
            if (!InputReader.TouchUIActive || GamePause.IsPaused || !hud.Visible || hud.FailVisible || hud.WinVisible)
            {
                return false;
            }
            return IsTutorialLevel(game);
        }

        /// <summary>The level in play is level 1 (its definition's id, else the id it was loaded by).</summary>
        public static bool IsTutorialLevel(GameState game)
        {
            if (game == null)
            {
                return false;
            }
            string id = game.Def != null && !string.IsNullOrEmpty(game.Def.Id) ? game.Def.Id : game.LevelId;
            return id == LevelId;
        }

        /// <summary>Builds the overlay, hidden, under <paramref name="parent"/> (TouchControls' object: it survives scene loads).</summary>
        public TouchTutorial(Transform parent)
        {
            Main main = Main.Instance;
            font = main != null && main.Hud != null && main.Hud.Font != null ? main.Hud.Font : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            var root = new GameObject("TouchTutorial", typeof(RectTransform));
            root.transform.SetParent(parent, false);
            canvas = root.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = SortingOrder;
            var scaler = root.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, ReferenceHeight);
            scaler.matchWidthOrHeight = 1f;
            canvas.enabled = false;

            Image veil = NewImage(root.transform, "Veil", null, VeilColour);
            Stretch(veil.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);

            float share = Tuning.TouchStickZoneShare;
            Image moveZone = NewImage(root.transform, "MoveZone", ProceduralArt.TutorialZone, ZoneTint);
            moveZone.type = Image.Type.Sliced;
            MoveZone = moveZone.rectTransform;
            Stretch(MoveZone, Vector2.zero, new Vector2(share, 1f), new Vector2(ZoneEdge, ZoneBottom), new Vector2(-ZoneSplitGap, -ZoneEdge));
            Image cameraZone = NewImage(root.transform, "CameraZone", ProceduralArt.TutorialZone, ZoneTint);
            cameraZone.type = Image.Type.Sliced;
            CameraZone = cameraZone.rectTransform;
            Stretch(CameraZone, new Vector2(share, 0f), Vector2.one, new Vector2(ZoneSplitGap, ZoneBottom), new Vector2(-ZoneEdge, -ZoneEdge));

            // The left third: the stick, "Move", its caption, centred in the third (the mockup's column).
            RectTransform moveColumn = NewRect(root.transform, "MoveColumn");
            Stretch(moveColumn, Vector2.zero, new Vector2(share, 1f), Vector2.zero, Vector2.zero);
            moveContent = NewRect(moveColumn, "MoveContent");
            Place(moveContent, Vector2.zero, Vector2.zero);
            Place(NewImage(moveContent, "MoveIcon", ProceduralArt.TutorialStick, Ink).rectTransform, new Vector2(0f, MoveIconY), new Vector2(MoveIconSize, MoveIconSize));
            moveTitle = NewText(moveContent, "MoveTitle", TitleSize, FontStyle.Bold, Ink, MoveTitleY, TitleHeight);
            moveCaption = NewText(moveContent, "MoveCaption", CaptionSize, FontStyle.Normal, CaptionInk, MoveCaptionY, CaptionHeight);

            // The right two thirds: "Turn" and "Zoom" side by side, the row centred in them.
            RectTransform cameraColumn = NewRect(root.transform, "CameraColumn");
            Stretch(cameraColumn, new Vector2(share, 0f), Vector2.one, Vector2.zero, Vector2.zero);
            cameraContent = NewRect(cameraColumn, "CameraContent");
            Place(cameraContent, Vector2.zero, Vector2.zero);
            turnItem = NewRect(cameraContent, "TurnItem");
            Place(turnItem, Vector2.zero, Vector2.zero);
            Place(NewImage(turnItem, "TurnIcon", ProceduralArt.TutorialDrag, Ink).rectTransform, new Vector2(0f, CameraIconY), new Vector2(CameraIconSize, CameraIconSize));
            turnTitle = NewText(turnItem, "TurnTitle", TitleSize, FontStyle.Bold, Ink, CameraTitleY, TitleHeight);
            turnCaption = NewText(turnItem, "TurnCaption", CaptionSize, FontStyle.Normal, CaptionInk, CameraCaptionY, CaptionHeight);
            zoomItem = NewRect(cameraContent, "ZoomItem");
            Place(zoomItem, Vector2.zero, Vector2.zero);
            Place(NewImage(zoomItem, "ZoomIcon", ProceduralArt.TutorialPinch, Ink).rectTransform, new Vector2(0f, CameraIconY), new Vector2(CameraIconSize, CameraIconSize));
            zoomTitle = NewText(zoomItem, "ZoomTitle", TitleSize, FontStyle.Bold, Ink, CameraTitleY, TitleHeight);
            zoomCaption = NewText(zoomItem, "ZoomCaption", CaptionSize, FontStyle.Normal, CaptionInk, CameraCaptionY, CaptionHeight);

            // The bottom centre: the gold line on its dark pill (it replaces the HUD's start line).
            Image pill = NewImage(root.transform, "TapPlate", ProceduralArt.Rounded, PillColour);
            pill.type = Image.Type.Sliced;
            pill.pixelsPerUnitMultiplier = TapCornerMultiplier;
            tapPlate = pill.rectTransform;
            tapPlate.anchorMin = tapPlate.anchorMax = new Vector2(0.5f, 0f);
            tapPlate.pivot = new Vector2(0.5f, 0f);
            tapPlate.anchoredPosition = new Vector2(0f, TapBottom);
            tapPlate.sizeDelta = new Vector2(600f, TapHeight);
            tapLine = NewText(tapPlate, "TapLine", TapSize, FontStyle.Normal, Gold, 0f, TapHeight);
            Stretch(tapLine.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);

            Refresh();
        }

        /// <summary>
        /// Every frame from TouchControls: shows or hides the canvas; while shown, the texts and the layout follow the language
        /// and the screen, and the tap line breathes slowly like the start line it replaces.
        /// </summary>
        public void SetVisible(bool visible)
        {
            if (canvas.enabled != visible)
            {
                canvas.enabled = visible;
            }
            if (!visible)
            {
                return;
            }
            if (laidLanguage != Strings.Language || laidScreen.x != Screen.width || laidScreen.y != Screen.height)
            {
                Refresh();
            }
            Color c = Gold;
            c.a = 0.8f + 0.2f * Mathf.Cos(Time.unscaledTime * 3.2f);
            tapLine.color = c;
        }

        /// <summary>The texts in the current language, then the layout for the current screen.</summary>
        private void Refresh()
        {
            laidLanguage = Strings.Language;
            laidScreen = new Vector2Int(Screen.width, Screen.height);
            moveTitle.text = Strings.TutoMoveTitle.ToUpperInvariant();
            moveCaption.text = Strings.TutoMoveCaption;
            turnTitle.text = Strings.TutoTurnTitle.ToUpperInvariant();
            turnCaption.text = Strings.TutoTurnCaption;
            zoomTitle.text = Strings.TutoZoomTitle.ToUpperInvariant();
            zoomCaption.text = Strings.TutoZoomCaption;
            tapLine.text = Strings.TutoTap;
            Layout();
        }

        /// <summary>
        /// The camera items placed like the mockup's row (each as wide as its widest part, <see cref="CameraItemGap"/> apart,
        /// the row centred), each column shrunk to fit inside its zone panel on a narrow screen (a 4:3 tablet), and the
        /// pill as wide as its line.
        /// </summary>
        private void Layout()
        {
            // The canvas width in units: the scaler matches the height, so the screen is 1080 units high.
            float width = Mathf.Max(1f, Screen.width) * ReferenceHeight / Mathf.Max(1f, Screen.height);
            float share = Tuning.TouchStickZoneShare;

            float moveWidth = Mathf.Max(MoveIconSize, Mathf.Max(moveTitle.preferredWidth, moveCaption.preferredWidth));
            float moveRoom = width * share - ZoneEdge - ZoneSplitGap - 2f * ZonePadding;
            moveContent.localScale = Vector3.one * Fit(moveRoom, moveWidth);

            float turnWidth = Mathf.Max(CameraIconSize, Mathf.Max(turnTitle.preferredWidth, turnCaption.preferredWidth));
            float zoomWidth = Mathf.Max(CameraIconSize, Mathf.Max(zoomTitle.preferredWidth, zoomCaption.preferredWidth));
            float row = turnWidth + CameraItemGap + zoomWidth;
            turnItem.anchoredPosition = new Vector2(-row * 0.5f + turnWidth * 0.5f, 0f);
            zoomItem.anchoredPosition = new Vector2(row * 0.5f - zoomWidth * 0.5f, 0f);
            float cameraRoom = width * (1f - share) - ZoneSplitGap - ZoneEdge - 2f * ZonePadding;
            cameraContent.localScale = Vector3.one * Fit(cameraRoom, row);

            tapPlate.sizeDelta = new Vector2(tapLine.preferredWidth + 2f * TapPadding, TapHeight);
        }

        /// <summary>1, or the scale that brings <paramref name="content"/> units into <paramref name="room"/> units.</summary>
        private static float Fit(float room, float content)
        {
            return content > room && content > 0f ? Mathf.Max(0.1f, room / content) : 1f;
        }

        // ----- Construction helpers -----

        private static RectTransform NewRect(Transform parent, string name)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            return (RectTransform)go.transform;
        }

        private static Image NewImage(Transform parent, string name, Sprite sprite, Color colour)
        {
            RectTransform rect = NewRect(parent, name);
            var image = rect.gameObject.AddComponent<Image>();
            image.sprite = sprite;
            image.color = colour;
            image.raycastTarget = false;
            image.preserveAspect = sprite != null && image.type == Image.Type.Simple;
            return image;
        }

        private Text NewText(Transform parent, string name, int size, FontStyle style, Color colour, float y, float height)
        {
            RectTransform rect = NewRect(parent, name);
            var text = rect.gameObject.AddComponent<Text>();
            text.font = font;
            text.fontSize = size;
            text.fontStyle = style;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = colour;
            text.raycastTarget = false;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            // Never empty (Refresh writes the real text at once).
            text.text = name;
            Place(rect, new Vector2(0f, y), new Vector2(TextBoxWidth, height));
            Labels[name] = text;
            return text;
        }

        /// <summary>Centred on its parent's centre, at <paramref name="offset"/>, <paramref name="size"/> units.</summary>
        private static void Place(RectTransform rect, Vector2 offset, Vector2 size)
        {
            rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0.5f);
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = offset;
            rect.sizeDelta = size;
        }

        private static void Stretch(RectTransform rect, Vector2 anchorMin, Vector2 anchorMax, Vector2 offsetMin, Vector2 offsetMax)
        {
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.offsetMin = offsetMin;
            rect.offsetMax = offsetMax;
        }
    }
}
