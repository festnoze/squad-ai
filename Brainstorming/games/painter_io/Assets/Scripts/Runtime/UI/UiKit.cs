// Owned by B4. Contract 15.1: helpers for the code-built uGUI. Canvas Screen Space Overlay with a CanvasScaler (1080 x 1920,
// screenMatchMode Expand since wave C: the whole 1080 x 1920 design box is always visible, taller phones get a taller
// canvas and landscape windows a wider one) and a GraphicRaycaster on every Canvas; uGUI Text with the OFL font from
// Resources/Fonts (fallback LegacyRuntime.ttf); raycastTarget off on every non-interactive Graphic; navy text shadows
// (#151D38, alpha 0.7, 3 px at the reference resolution). Sprites (round, ring, triangle, vignette, gradient, soft band, and
// the logo's shine band since wave D) are generated in code once.
using System;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Events;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    public static class UiKit
    {
        public const float RefWidth = 1080f;
        public const float RefHeight = 1920f;
        /// <summary>
        /// Wave C (robust-01): Expand keeps the whole 1080 x 1920 design box on screen at every aspect (the old match 0.5
        /// cropped it vertically on landscape and square windows and horizontally on 20:9 and 21:9 phones).
        /// </summary>
        public const CanvasScaler.ScreenMatchMode ScreenMatch = CanvasScaler.ScreenMatchMode.Expand;
        public const string FontPath = "Fonts/Nunito-ExtraBold";
        public const string TitleFontPath = "Fonts/Nunito-Black";
        public const string FallbackFont = "LegacyRuntime.ttf";

        /// <summary>Navy of the shadows and dims (#151D38).</summary>
        public static readonly Color Navy = new Color32(0x15, 0x1D, 0x38, 0xFF);
        /// <summary>Panel navy (#1E2A4D, the table color).</summary>
        public static readonly Color PanelNavy = new Color32(0x1E, 0x2A, 0x4D, 0xFF);
        /// <summary>Lighter navy for secondary buttons and tracks.</summary>
        public static readonly Color NavyLight = new Color32(0x33, 0x42, 0x73, 0xFF);
        /// <summary>Light UI text #F3EEE8.</summary>
        public static readonly Color Light = new Color32(0xF3, 0xEE, 0xE8, 0xFF);
        public static readonly Color ShadowColor = new Color(0x15 / 255f, 0x1D / 255f, 0x38 / 255f, 0.7f);
        public static readonly Vector2 ShadowDistance = new Vector2(3f, -3f);

        private static Font font, titleFont;
        private static bool fallbackLogged;
        private static Sprite rounded, circle, ring, triangle, vignette, gradient, softBand, shine;

        /// <summary>True when the OFL font could not be loaded and LegacyRuntime.ttf is used.</summary>
        public static bool UsingFallbackFont { get; private set; }

        /// <summary>The UI font (Nunito ExtraBold), LegacyRuntime.ttf when missing.</summary>
        public static Font Font
        {
            get
            {
                if (font == null) font = LoadFont(FontPath);
                return font;
            }
        }

        /// <summary>The title font (Nunito Black), the UI font when missing.</summary>
        public static Font TitleFont
        {
            get
            {
                if (titleFont == null)
                {
                    titleFont = LoadFontOrNull(TitleFontPath);
                    if (titleFont == null) titleFont = Font;
                }
                return titleFont;
            }
        }

        private static Font LoadFont(string path)
        {
            Font f = LoadFontOrNull(path);
            if (f != null)
            {
                UsingFallbackFont = false;
                return f;
            }
            UsingFallbackFont = true;
            if (!fallbackLogged)
            {
                fallbackLogged = true;
                Debug.LogWarning("[PainterIO] UI font " + path + " missing: falling back to " + FallbackFont);
            }
            try
            {
                return Resources.GetBuiltinResource<Font>(FallbackFont);
            }
            catch (Exception e)
            {
                Debug.LogWarning("[PainterIO] fallback font failed: " + e.Message);
                return null;
            }
        }

        private static Font LoadFontOrNull(string path)
        {
            try
            {
                return Resources.Load<Font>(path);
            }
            catch (Exception)
            {
                return null;
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Canvases and rects.

        /// <summary>
        /// The canvas size (reference units) the CanvasScaler gives a screen of w x h pixels with ScreenMatch (Expand):
        /// 1080 wide and at least 1920 high on portrait screens taller than 9:16, 1920 high and at least 1080 wide otherwise.
        /// </summary>
        public static Vector2 CanvasSizeFor(float screenWidth, float screenHeight)
        {
            if (!(screenWidth > 0f) || !(screenHeight > 0f)) return new Vector2(RefWidth, RefHeight);
            float scale = Mathf.Min(screenWidth / RefWidth, screenHeight / RefHeight);
            return new Vector2(screenWidth / scale, screenHeight / scale);
        }

        /// <summary>
        /// A Screen Space Overlay canvas (CanvasScaler 1080 x 1920 Expand, GraphicRaycaster, CanvasGroup) with a SafeArea
        /// child that holds the content.
        /// </summary>
        public static Canvas CreateCanvas(Transform parent, string name, int sortingOrder, out CanvasGroup group, out RectTransform safe)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var canvas = go.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = sortingOrder;
            canvas.pixelPerfect = false;
            var scaler = go.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(RefWidth, RefHeight);
            scaler.screenMatchMode = ScreenMatch;
            scaler.referencePixelsPerUnit = 100f;
            go.AddComponent<GraphicRaycaster>();
            group = go.AddComponent<CanvasGroup>();
            safe = Rect("SafeArea", go.transform);
            Stretch(safe);
            safe.gameObject.AddComponent<SafeArea>();
            return canvas;
        }

        public static RectTransform Rect(string name, Transform parent)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.layer = 5;   // UI
            var rt = (RectTransform)go.transform;
            rt.SetParent(parent, false);
            return rt;
        }

        /// <summary>Full stretch with zero offsets.</summary>
        public static void Stretch(RectTransform rt)
        {
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.offsetMin = Vector2.zero;
            rt.offsetMax = Vector2.zero;
        }

        /// <summary>Anchored at anchor (both min and max), centered pivot, at pos with size.</summary>
        public static RectTransform Place(RectTransform rt, Vector2 anchor, Vector2 pos, Vector2 size)
        {
            rt.anchorMin = anchor;
            rt.anchorMax = anchor;
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.sizeDelta = size;
            rt.anchoredPosition = pos;
            return rt;
        }

        public static readonly Vector2 TopLeft = new Vector2(0f, 1f);
        public static readonly Vector2 TopCenter = new Vector2(0.5f, 1f);
        public static readonly Vector2 TopRight = new Vector2(1f, 1f);
        public static readonly Vector2 Center = new Vector2(0.5f, 0.5f);
        public static readonly Vector2 BottomCenter = new Vector2(0.5f, 0f);

        // ------------------------------------------------------------------------------------------------------------
        // Graphics.

        /// <summary>A non-interactive uGUI Text with the UI font and (optionally) the navy shadow.</summary>
        public static Text Label(Transform parent, string name, int size, Color color, TextAnchor align, bool shadow = true, bool title = false)
        {
            RectTransform rt = Rect(name, parent);
            var t = rt.gameObject.AddComponent<Text>();
            t.font = title ? TitleFont : Font;
            t.fontSize = size;
            t.fontStyle = FontStyle.Normal;
            t.color = color;
            t.alignment = align;
            t.horizontalOverflow = HorizontalWrapMode.Overflow;
            t.verticalOverflow = VerticalWrapMode.Overflow;
            t.supportRichText = false;
            t.resizeTextForBestFit = false;
            t.raycastTarget = false;
            t.lineSpacing = 1f;
            t.text = " ";
            if (shadow) AddShadow(t.gameObject);
            return t;
        }

        /// <summary>A wrapping paragraph Text of the given width.</summary>
        public static Text Paragraph(Transform parent, string name, int size, Color color, TextAnchor align, float width, bool shadow = true)
        {
            Text t = Label(parent, name, size, color, align, shadow);
            t.horizontalOverflow = HorizontalWrapMode.Wrap;
            t.rectTransform.sizeDelta = new Vector2(width, size * 3f);
            return t;
        }

        /// <summary>A navy outline (four offset copies), for texts drawn over a puddle of their own color.</summary>
        public static Outline AddOutline(GameObject go, float distance, float alpha)
        {
            var o = go.AddComponent<Outline>();
            o.effectColor = WithAlpha(Navy, alpha);
            o.effectDistance = new Vector2(distance, distance);
            o.useGraphicAlpha = true;
            return o;
        }

        /// <summary>
        /// A primary pill button that stays readable over a puddle of its own color: navy drop shadow, light rim, the
        /// colored face, a soft gloss band on its upper part and the label. Returns the container (scale it to pulse).
        /// </summary>
        public static RectTransform PrimaryButton(Transform parent, string name, Vector2 size, Color fill, int fontSize,
                                                  UnityAction onClick, out Image face, out Text label)
        {
            RectTransform group = Rect(name, parent);
            group.sizeDelta = size;
            float radius = size.y * 0.5f;
            Image shadow = Rounded(group, "Shadow", WithAlpha(Navy, 0.6f), radius + 4f);
            Stretch(shadow.rectTransform);
            shadow.rectTransform.offsetMin = new Vector2(-2f, -14f);
            shadow.rectTransform.offsetMax = new Vector2(2f, -6f);
            Image rim = Rounded(group, "Rim", WithAlpha(Light, 0.92f), radius + 6f);
            Stretch(rim.rectTransform);
            rim.rectTransform.offsetMin = new Vector2(-6f, -6f);
            rim.rectTransform.offsetMax = new Vector2(6f, 6f);
            Button b = Btn(group, "Face", size, fill, radius, fontSize, Light, onClick, out label);
            Stretch((RectTransform)b.transform);
            face = (Image)b.targetGraphic;
            Image gloss = Rounded(b.transform, "Gloss", new Color(1f, 1f, 1f, 0.13f), radius * 0.6f);
            gloss.rectTransform.anchorMin = new Vector2(0.1f, 0.62f);
            gloss.rectTransform.anchorMax = new Vector2(0.9f, 0.9f);
            gloss.rectTransform.offsetMin = gloss.rectTransform.offsetMax = Vector2.zero;
            gloss.transform.SetSiblingIndex(0);
            if (label != null) AddOutline(label.gameObject, 2f, 0.35f);
            return group;
        }

        public static Shadow AddShadow(GameObject go)
        {
            var s = go.AddComponent<Shadow>();
            s.effectColor = ShadowColor;
            s.effectDistance = ShadowDistance;
            s.useGraphicAlpha = true;
            return s;
        }

        public static Image Img(Transform parent, string name, Sprite sprite, Color color, bool raycast = false)
        {
            RectTransform rt = Rect(name, parent);
            var img = rt.gameObject.AddComponent<Image>();
            img.sprite = sprite;
            img.color = color;
            img.raycastTarget = raycast;
            img.type = Image.Type.Simple;
            img.preserveAspect = false;
            return img;
        }

        /// <summary>A rounded rectangle (sliced round sprite) with the given corner radius in reference pixels.</summary>
        public static Image Rounded(Transform parent, string name, Color color, float radius, bool raycast = false)
        {
            Image img = Img(parent, name, RoundedSprite, color, raycast);
            img.type = Image.Type.Sliced;
            img.fillCenter = true;
            img.pixelsPerUnitMultiplier = RoundedRadiusPixels / Mathf.Max(1f, radius);
            return img;
        }

        /// <summary>A full-screen image stretched over parent.</summary>
        public static Image FullScreen(Transform parent, string name, Color color, bool raycast)
        {
            Image img = Img(parent, name, null, color, raycast);
            Stretch(img.rectTransform);
            return img;
        }

        /// <summary>
        /// A button: rounded background (the target graphic), a centered label, navigation off, deselected after the click.
        /// The click raises UiRoot.ButtonClicked (UI click sound) and then runs onClick inside a try/catch.
        /// </summary>
        public static Button Btn(Transform parent, string name, Vector2 size, Color fill, float radius, int fontSize, Color textColor,
                                 UnityAction onClick, out Text label)
        {
            Image bg = Rounded(parent, name, fill, radius, true);
            bg.rectTransform.sizeDelta = size;
            // An invisible hit area must still be "rendered", or the GraphicRaycaster skips it (depth -1).
            if (fill.a <= 0.01f) bg.canvasRenderer.cullTransparentMesh = false;
            var b = bg.gameObject.AddComponent<Button>();
            b.targetGraphic = bg;
            b.navigation = new Navigation { mode = Navigation.Mode.None };
            ColorBlock cb = b.colors;
            cb.normalColor = Color.white;
            cb.highlightedColor = new Color(1.06f, 1.06f, 1.06f, 1f);
            cb.pressedColor = new Color(0.78f, 0.78f, 0.82f, 1f);
            cb.selectedColor = Color.white;
            cb.disabledColor = new Color(0.8f, 0.8f, 0.8f, 0.6f);
            cb.colorMultiplier = 1f;
            cb.fadeDuration = 0.08f;
            b.colors = cb;
            Wire(b, name, onClick);
            if (fontSize > 0)
            {
                label = Label(bg.transform, "Label", fontSize, textColor, TextAnchor.MiddleCenter, true);
                Stretch(label.rectTransform);
            }
            else label = null;
            return b;
        }

        /// <summary>Adds the click handler with the click event, the try/catch and the deselect.</summary>
        public static void Wire(Button b, string name, UnityAction onClick)
        {
            b.onClick.AddListener(() =>
            {
                UiRoot.RaiseButtonClicked();
                try
                {
                    onClick?.Invoke();
                }
                catch (Exception e)
                {
                    Debug.LogError("[PainterIO] UI button " + name + " failed: " + e);
                }
                Deselect();
            });
        }

        /// <summary>Clears the EventSystem selection (so Enter / Space never re-submit a button).</summary>
        public static void Deselect()
        {
            EventSystem es = EventSystem.current;
            if (es != null && es.currentSelectedGameObject != null) es.SetSelectedGameObject(null);
        }

        public static Color WithAlpha(Color c, float a)
        {
            c.a = a;
            return c;
        }

        /// <summary>Mixes c toward white by t.</summary>
        public static Color Lighten(Color c, float t)
        {
            return new Color(Mathf.Lerp(c.r, 1f, t), Mathf.Lerp(c.g, 1f, t), Mathf.Lerp(c.b, 1f, t), c.a);
        }

        /// <summary>Scales c toward black by t.</summary>
        public static Color Darken(Color c, float t)
        {
            return new Color(c.r * (1f - t), c.g * (1f - t), c.b * (1f - t), c.a);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Generated sprites (created once; recreated if Unity destroyed them).

        /// <summary>Corner radius in pixels of the rounded sprite (border of the 9-slice).</summary>
        public const float RoundedRadiusPixels = 64f;

        public static Sprite RoundedSprite
        {
            get
            {
                if (rounded == null)
                {
                    const int r = 64;
                    const int size = 2 * r + 2;
                    rounded = MakeSprite("PIO_UiRounded", size, size, (x, y) =>
                    {
                        float cx = size * 0.5f;
                        float dx = Mathf.Max(0f, Mathf.Abs(x - cx) - 1f);
                        float dy = Mathf.Max(0f, Mathf.Abs(y - cx) - 1f);
                        float d = Mathf.Sqrt(dx * dx + dy * dy);
                        return Mathf.Clamp01(r - d + 0.5f);
                    }, new Vector4(r, r, r, r), true);
                }
                return rounded;
            }
        }

        public static Sprite CircleSprite
        {
            get
            {
                if (circle == null)
                {
                    const int size = 128;
                    circle = MakeSprite("PIO_UiCircle", size, size, (x, y) =>
                    {
                        float d = Mathf.Sqrt((x - 64f) * (x - 64f) + (y - 64f) * (y - 64f));
                        return Mathf.Clamp01(63f - d + 0.5f);
                    }, Vector4.zero, true);
                }
                return circle;
            }
        }

        /// <summary>A ring of 10 px thickness on a 128 px sprite.</summary>
        public static Sprite RingSprite
        {
            get
            {
                if (ring == null)
                {
                    const int size = 128;
                    ring = MakeSprite("PIO_UiRing", size, size, (x, y) =>
                    {
                        float d = Mathf.Sqrt((x - 64f) * (x - 64f) + (y - 64f) * (y - 64f));
                        float outer = Mathf.Clamp01(63f - d + 0.5f);
                        float inner = Mathf.Clamp01(d - 53f + 0.5f);
                        return outer * inner;
                    }, Vector4.zero, true);
                }
                return ring;
            }
        }

        /// <summary>An isosceles triangle pointing up (+y).</summary>
        public static Sprite TriangleSprite
        {
            get
            {
                if (triangle == null)
                {
                    const int size = 64;
                    triangle = MakeSprite("PIO_UiTriangle", size, size, (x, y) =>
                    {
                        // Edges: base y = 4, apex (32, 60); signed distances to the three edges (positive inside).
                        float dBase = y - 4f;
                        Vector2 p = new Vector2(x, y);
                        float dl = EdgeDistance(p, new Vector2(4f, 4f), new Vector2(32f, 60f));
                        float dr = EdgeDistance(p, new Vector2(32f, 60f), new Vector2(60f, 4f));
                        float d = Mathf.Min(dBase, Mathf.Min(dl, dr));
                        return Mathf.Clamp01(d + 0.5f);
                    }, Vector4.zero, true);
                }
                return triangle;
            }
        }

        /// <summary>Width in pixels of the glowing border of the vignette sprite (its 9-slice border).</summary>
        public const float VignetteBorderPixels = 64f;

        /// <summary>
        /// Edge glow for a Sliced Image: transparent center, the 64 px border fades to opaque at the outer edge (rounded inner
        /// corners), so the band keeps a constant width in canvas units whatever the screen aspect.
        /// </summary>
        public static Sprite VignetteSprite
        {
            get
            {
                if (vignette == null)
                {
                    const int b = 64;
                    const int size = 2 * b + 2;
                    vignette = MakeSprite("PIO_UiVignette", size, size, (x, y) =>
                    {
                        float dx = Mathf.Max(0f, b - Mathf.Min(x, size - x));
                        float dy = Mathf.Max(0f, b - Mathf.Min(y, size - y));
                        float t = Mathf.Clamp01(Mathf.Sqrt(dx * dx + dy * dy) / b);
                        return Mathf.Pow(t, 2.2f);
                    }, new Vector4(b, b, b, b), false);
                }
                return vignette;
            }
        }

        /// <summary>Vertical alpha ramp: opaque at the top (y = 1), transparent at the bottom.</summary>
        public static Sprite GradientSprite
        {
            get
            {
                if (gradient == null)
                {
                    gradient = MakeSprite("PIO_UiGradient", 4, 128, (x, y) =>
                    {
                        float t = y / 128f;
                        return t * t * (3f - 2f * t);
                    }, Vector4.zero, false);
                }
                return gradient;
            }
        }

        /// <summary>Height in pixels of the feathered top and bottom edges of the soft band sprite (its 9-slice border).</summary>
        public const float SoftBandFeatherPixels = 60f;

        /// <summary>
        /// A horizontal band for a Sliced Image: opaque in the middle, its top and bottom 60 px fade to transparent
        /// (smoothstep), the sides stay opaque. With the reference pixels per unit the feathering is 60 canvas units.
        /// </summary>
        public static Sprite SoftBandSprite
        {
            get
            {
                if (softBand == null)
                {
                    const int f = 60;
                    const int h = 2 * f + 2;
                    softBand = MakeSprite("PIO_UiSoftBand", 4, h, (x, y) =>
                    {
                        float t = Mathf.Clamp01(Mathf.Min(y, h - y) / f);
                        return t * t * (3f - 2f * t);
                    }, new Vector4(0f, f, 0f, f), false);
                }
                return softBand;
            }
        }

        /// <summary>
        /// Wave D F1: a soft vertical light band (opaque along its middle column, Gaussian falloff to both sides, faded
        /// at both ends), swept across the logo through a Mask for its idle shine.
        /// </summary>
        public static Sprite ShineSprite
        {
            get
            {
                if (shine == null)
                {
                    const int w = 64, h = 128;
                    shine = MakeSprite("PIO_UiShine", w, h, (x, y) =>
                    {
                        float u = (x / w - 0.5f) / 0.2f;
                        float v = Mathf.Clamp01(Mathf.Min(y, h - y) / (h * 0.25f));
                        return Mathf.Exp(-u * u) * v * v * (3f - 2f * v);
                    }, Vector4.zero, false);
                }
                return shine;
            }
        }

        private static float EdgeDistance(Vector2 p, Vector2 a, Vector2 b)
        {
            // Signed distance to the line a->b, positive on the left side (the inside for a counter-clockwise walk).
            Vector2 d = (b - a).normalized;
            Vector2 n = new Vector2(d.y, -d.x);
            return Vector2.Dot(p - a, n);
        }

        private static Sprite MakeSprite(string name, int w, int h, Func<float, float, float> alpha, Vector4 border, bool mips)
        {
            var tex = new Texture2D(w, h, TextureFormat.RGBA32, mips, false)
            {
                name = name,
                wrapMode = TextureWrapMode.Clamp,
                filterMode = mips ? FilterMode.Trilinear : FilterMode.Bilinear,
                hideFlags = HideFlags.DontSave,
            };
            var px = new Color32[w * h];
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    float a = Mathf.Clamp01(alpha(x + 0.5f, y + 0.5f));
                    px[y * w + x] = new Color32(255, 255, 255, (byte)Mathf.RoundToInt(a * 255f));
                }
            }
            tex.SetPixels32(px);
            tex.Apply(mips, true);
            Sprite s = Sprite.Create(tex, new UnityEngine.Rect(0, 0, w, h), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect, border);
            s.name = name;
            s.hideFlags = HideFlags.DontSave;
            return s;
        }
    }
}
