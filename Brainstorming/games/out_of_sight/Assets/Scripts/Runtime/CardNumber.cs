using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// LEVELNUM (docs/next/progress/LEVELNUM.md): the intro card's full-screen layer with the level number as holes in it.
    /// A greyish-black dim covers the scene behind the card; the digits of the level select's number are holes through
    /// which the scene shows, nearly clear glass (a faint wash, a hairline light edge and a soft inner shade along the
    /// outline). The number starts several times its final size (only part of a digit shows) and zooms out with a smooth
    /// ease-out to its settled size, a fraction of the screen height, centred on the screen. The HUD draws it first, so
    /// every HUD text stays on top. Round 3: every value comes from <see cref="CardNumberSettings"/>, read again from
    /// StreamingAssets/card_number.json each time the card is shown.
    /// How (round 2): nothing depends on stencil, depth or destination colour. The digits' glyph quads are drawn by a
    /// command buffer into a mask texture (<see cref="MaskShaderName"/>), and the layer is a RawImage whose shader
    /// (<see cref="DimShaderName"/>) mixes dim and glass by that mask, with plain alpha blending. Both shaders are created
    /// from code only: ProjectSetup lists them in Always Included Shaders.
    /// LEVELNUM2: the digits come from a baked signed distance field atlas (<see cref="LevelDigitFont"/>, Inter Display
    /// Bold by default), so the edge stays crisp and one pixel anti-aliased at every zoom step. The mask is drawn at the
    /// full screen resolution and carries three channels: coverage (r), the hairline inner edge (g) and the inner shade (b).
    /// </summary>
    public sealed class CardNumber
    {
        public const string DimShaderName = "OutOfSight/UI Card Dim";
        public const string MaskShaderName = "OutOfSight/UI Number Mask";

        /// <summary>The values in use, read again at every <see cref="SetNumber"/> (each card shown, so each restart).</summary>
        public CardNumberSettings Settings { get; private set; } = CardNumberSettings.Defaults;

        /// <summary>Edge and shade widths in the settings are pixels on a screen this tall (they scale with the screen).</summary>
        public const float ReferenceHeight = 1080f;

        // The mask texture is this fraction of the canvas's pixel size: 1, so the distance field's one-pixel edge is not
        // softened again by an upsampling.
        private const float MaskResolution = 1f;

        private readonly RawImage layer;
        private readonly CanvasGroup group;
        private readonly Material dimMaterial;
        private readonly Material maskMaterial;
        private readonly CommandBuffer commands = new CommandBuffer { name = "LevelNumberMask" };
        private readonly List<Vector3> positions = new List<Vector3>();
        private readonly List<Vector2> uvs = new List<Vector2>();
        private readonly List<int> indices = new List<int>();
        private Mesh mesh;
        private RenderTexture mask;
        private Vector2 inkSize;
        private LevelDigitFont font;
        private string digits = string.Empty;
        private bool disposed;

        /// <summary>The number shown (0: none, the layer is a plain dim).</summary>
        public int Number { get; private set; }

        /// <summary>Seconds of the zoom played.</summary>
        public float Age { get; set; } = 99f;

        /// <summary>The number's scale now (canvas units per glyph unit), and the scale it settles at for the current canvas height.</summary>
        public float Scale { get; private set; }
        public float FinalScale { get; private set; }

        /// <summary>Both shaders were found: the digits are holes (false: a plain dim, with a warning).</summary>
        public bool Ready => dimMaterial != null && maskMaterial != null;

        /// <summary>The layer group's alpha (the card's).</summary>
        public float Alpha => group != null ? group.alpha : 0f;

        /// <summary>The fade-in of the layer at the card's start, 0 to 1 (multiplies the card's alpha).</summary>
        public float FadeIn { get; private set; } = 1f;

        /// <summary>The digit face in use (null: none could be loaded, the layer is a plain dim).</summary>
        public string FontName => font != null ? font.Name : null;

        /// <summary>The digits' ink in canvas units, centred on the screen centre.</summary>
        public Rect InkRect
        {
            get
            {
                Vector2 size = inkSize * Scale;
                return Number > 0 ? new Rect(-size * 0.5f, size) : Rect.zero;
            }
        }

        /// <summary>The mask texture (tests read it back).</summary>
        public RenderTexture Mask => mask;

        public CardNumber(Transform hudRoot)
        {
            var go = new GameObject("CardBackdrop", typeof(RectTransform));
            go.transform.SetParent(hudRoot, false);
            var rect = (RectTransform)go.transform;
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
            group = go.AddComponent<CanvasGroup>();
            group.interactable = false;
            group.blocksRaycasts = false;
            group.alpha = 0f;

            var layerGo = new GameObject("CardDim", typeof(RectTransform));
            layerGo.transform.SetParent(go.transform, false);
            var layerRect = (RectTransform)layerGo.transform;
            layerRect.anchorMin = Vector2.zero;
            layerRect.anchorMax = Vector2.one;
            layerRect.offsetMin = Vector2.zero;
            layerRect.offsetMax = Vector2.zero;
            layer = layerGo.AddComponent<RawImage>();
            layer.raycastTarget = false;
            layer.maskable = false;
            layer.enabled = false;

            Shader dim = Shader.Find(DimShaderName);
            Shader draw = Shader.Find(MaskShaderName);
            if (dim != null && dim.isSupported && draw != null && draw.isSupported)
            {
                dimMaterial = new Material(dim) { name = "CardDim", hideFlags = HideFlags.HideAndDontSave };
                maskMaterial = new Material(draw) { name = "LevelNumberMask", hideFlags = HideFlags.HideAndDontSave };
                layer.material = dimMaterial;
                layer.color = Color.white;
            }
            else
            {
                Debug.LogWarning($"[CardNumber] {DimShaderName} or {MaskShaderName} missing or unsupported: the card shows a plain dim");
                layer.texture = null;
            }
            ApplyColours();
        }

        /// <summary>Releases the mask texture and the materials (the HUD is destroyed). The digit atlases stay cached.</summary>
        public void Dispose()
        {
            disposed = true;
            commands.Release();
            if (mask != null)
            {
                mask.Release();
                UnityEngine.Object.Destroy(mask);
                mask = null;
            }
            if (mesh != null)
            {
                UnityEngine.Object.Destroy(mesh);
            }
            if (dimMaterial != null)
            {
                UnityEngine.Object.Destroy(dimMaterial);
            }
            if (maskMaterial != null)
            {
                UnityEngine.Object.Destroy(maskMaterial);
            }
        }

        /// <summary>
        /// Shows <paramref name="number"/> (0: none) and starts the zoom from its beginning, with the settings read again
        /// (so an edited card_number.json shows at the next restart).
        /// </summary>
        public void SetNumber(int number)
        {
            if (disposed)
            {
                return;
            }
            Settings = CardNumberSettings.Load();
            ApplyColours();
            Number = Mathf.Max(0, number);
            digits = Number > 0 ? Number.ToString(CultureInfo.InvariantCulture) : string.Empty;
            font = LevelDigitFont.Get(Settings.Font) ?? LevelDigitFont.Get(CardNumberSettings.Defaults.Font);
            BuildMesh();
            Age = 0f;
        }

        /// <summary>
        /// Every frame (and after a jump of <see cref="Age"/>): the layer follows the card's <paramref name="alpha"/>; the
        /// number is posed at <paramref name="age"/> seconds of its zoom on a canvas of <paramref name="canvas"/> units
        /// and <paramref name="pixels"/> pixels, and the mask is drawn again while the layer shows.
        /// </summary>
        public void Pose(float alpha, float age, Vector2 canvas, Vector2 pixels)
        {
            group.alpha = alpha;
            bool shown = alpha > 0f;
            layer.enabled = shown;
            float height = canvas.y > 1f ? canvas.y : 1080f;
            FinalScale = inkSize.y > 1e-3f ? Settings.SettledHeight * height / inkSize.y : 1f;
            float t = Settings.ZoomSeconds > 0f ? Mathf.Clamp01(age / Settings.ZoomSeconds) : 1f;
            Scale = FinalScale * Mathf.Exp(Mathf.Log(Settings.StartZoom) * (1f - Ease(Settings.Easing, t)));
            // The fade-in runs on the real clock (reduced motion skips it with the zoom).
            FadeIn = Hud.ReducedMotion || Settings.FadeInSeconds <= 0f ? 1f : Mathf.SmoothStep(0f, 1f, Age / Settings.FadeInSeconds);
            Color c = layer.color;
            float a = Ready ? FadeIn : Settings.DimOpacity * FadeIn;
            if (!Mathf.Approximately(c.a, a))
            {
                // Only on a change: setting the colour dirties the layer's vertices (a canvas rebuild).
                c.a = a;
                layer.color = c;
            }
            if (shown && Ready)
            {
                DrawMask(canvas, pixels);
            }
        }

        /// <summary>The colours and opacities from <see cref="Settings"/> (a plain dim without the shaders).</summary>
        private void ApplyColours()
        {
            Color dim = Settings.DimColor;
            dim.a = Settings.DimOpacity;
            Color wash = Settings.WashColor;
            wash.a = Settings.WashOpacity;
            Color edge = Settings.EdgeColor;
            edge.a = Settings.EdgeOpacity;
            Color shade = Settings.DimColor;
            shade.a = Settings.InnerShadeOpacity;
            if (dimMaterial != null)
            {
                dimMaterial.SetColor("_DimColor", dim);
                dimMaterial.SetColor("_WashColor", wash);
                dimMaterial.SetColor("_EdgeColor", edge);
                dimMaterial.SetColor("_ShadeColor", shade);
            }
            else
            {
                layer.color = dim;
            }
        }

        /// <summary>The easing names accepted by card_number.json's "easing" key.</summary>
        public static readonly string[] Easings = { "expo", "quint", "quart", "cubic", "sine", "linear" };

        /// <summary>
        /// The zoom's curve, 0 at <paramref name="t"/> = 0 to exactly 1 at 1, ease-out with no overshoot, applied to the
        /// scale in log space (steady to the eye). "expo" is normalized so it lands on 1 with no jump.
        /// </summary>
        public static float Ease(string kind, float t)
        {
            t = Mathf.Clamp01(t);
            float u = 1f - t;
            switch (kind)
            {
                case "linear":
                    return t;
                case "sine":
                    return Mathf.Sin(t * Mathf.PI * 0.5f);
                case "cubic":
                    return 1f - u * u * u;
                case "quart":
                    return 1f - u * u * u * u;
                case "quint":
                    return 1f - u * u * u * u * u;
                default:
                    return (1f - Mathf.Pow(2f, -10f * t)) / (1f - Mathf.Pow(2f, -10f));
            }
        }

        /// <summary>
        /// The share of mask pixels at least half covered and the highest coverage (tests: the holes exist and have the
        /// expected size). Reads the texture back, so never call it per frame.
        /// </summary>
        public float CoveredShare(out float highest)
        {
            highest = 0f;
            if (mask == null)
            {
                return 0f;
            }
            var read = new Texture2D(mask.width, mask.height, TextureFormat.RGBA32, false, true);
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = mask;
            read.ReadPixels(new Rect(0, 0, mask.width, mask.height), 0, 0);
            read.Apply();
            RenderTexture.active = previous;
            Color32[] pixels = read.GetPixels32();
            UnityEngine.Object.Destroy(read);
            int covered = 0;
            foreach (Color32 p in pixels)
            {
                highest = Mathf.Max(highest, p.r / 255f);
                if (p.r >= 128)
                {
                    covered++;
                }
            }
            return pixels.Length > 0 ? covered / (float)pixels.Length : 0f;
        }

        /// <summary>The digits' quads from the baked atlas, laid out on their advances, their ink centred on the origin.</summary>
        private void BuildMesh()
        {
            positions.Clear();
            uvs.Clear();
            indices.Clear();
            inkSize = Vector2.zero;
            if (mesh == null)
            {
                mesh = new Mesh { name = "LevelNumber", hideFlags = HideFlags.HideAndDontSave };
            }
            mesh.Clear();
            if (string.IsNullOrEmpty(digits) || font == null)
            {
                return;
            }
            var min = new Vector2(float.MaxValue, float.MaxValue);
            var max = new Vector2(float.MinValue, float.MinValue);
            float pen = 0f;
            var placed = new List<(LevelDigitFont.Glyph glyph, float x)>();
            foreach (char ch in digits)
            {
                if (!font.TryGetGlyph(ch, out LevelDigitFont.Glyph g))
                {
                    continue;
                }
                placed.Add((g, pen));
                min = Vector2.Min(min, new Vector2(g.Ink.xMin + pen, g.Ink.yMin));
                max = Vector2.Max(max, new Vector2(g.Ink.xMax + pen, g.Ink.yMax));
                pen += g.Advance;
            }
            if (placed.Count == 0)
            {
                return;
            }
            Vector2 centre = (min + max) * 0.5f;
            inkSize = max - min;
            foreach ((LevelDigitFont.Glyph g, float x) in placed)
            {
                int b = positions.Count;
                Rect q = g.Quad;
                Rect uv = g.Uv;
                positions.Add(new Vector3(q.xMin + x - centre.x, q.yMin - centre.y, 0f));
                positions.Add(new Vector3(q.xMin + x - centre.x, q.yMax - centre.y, 0f));
                positions.Add(new Vector3(q.xMax + x - centre.x, q.yMax - centre.y, 0f));
                positions.Add(new Vector3(q.xMax + x - centre.x, q.yMin - centre.y, 0f));
                uvs.Add(new Vector2(uv.xMin, uv.yMin));
                uvs.Add(new Vector2(uv.xMin, uv.yMax));
                uvs.Add(new Vector2(uv.xMax, uv.yMax));
                uvs.Add(new Vector2(uv.xMax, uv.yMin));
                indices.Add(b);
                indices.Add(b + 1);
                indices.Add(b + 2);
                indices.Add(b + 2);
                indices.Add(b + 3);
                indices.Add(b);
            }
            mesh.SetVertices(positions);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(indices, 0);
            if (maskMaterial != null)
            {
                maskMaterial.mainTexture = font.Atlas;
            }
        }

        /// <summary>The mask: cleared, then the digits drawn at the current scale over the canvas.</summary>
        private void DrawMask(Vector2 canvas, Vector2 pixels)
        {
            int w = Mathf.Clamp(Mathf.RoundToInt(pixels.x * MaskResolution), 64, 4096);
            int h = Mathf.Clamp(Mathf.RoundToInt(pixels.y * MaskResolution), 64, 4096);
            if (mask == null || mask.width != w || mask.height != h)
            {
                if (mask != null)
                {
                    mask.Release();
                    UnityEngine.Object.Destroy(mask);
                }
                mask = new RenderTexture(w, h, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.Linear)
                {
                    name = "LevelNumberMask",
                    filterMode = FilterMode.Bilinear,
                    wrapMode = TextureWrapMode.Clamp,
                    hideFlags = HideFlags.HideAndDontSave,
                };
                mask.Create();
                layer.texture = mask;
            }
            float cw = canvas.x > 1f ? canvas.x : 1920f;
            float ch = canvas.y > 1f ? canvas.y : 1080f;
            maskMaterial.SetMatrix("_NumberToClip", Matrix4x4.Scale(new Vector3(2f * Scale / cw, 2f * Scale / ch, 1f)));
            if (font != null)
            {
                // Distance field value to mask pixels: one field unit is 2 * spread atlas texels; a texel is
                // (mask pixels per glyph unit) / (texels per glyph unit) mask pixels. Exact, so no screen derivatives.
                float pixelsPerUnit = Scale * h / ch;
                maskMaterial.SetFloat("_DistanceToPixels", 2f * font.SpreadTexels * pixelsPerUnit / font.TexelsPerUnit);
            }
            float referencePixels = h / ReferenceHeight;
            maskMaterial.SetFloat("_EdgeWidth", Settings.EdgeWidth * referencePixels);
            maskMaterial.SetFloat("_ShadeWidth", Settings.InnerShadeWidth * referencePixels);
            commands.Clear();
            commands.SetRenderTarget(mask);
            commands.ClearRenderTarget(false, true, Color.clear);
            if (Number > 0 && mesh != null && mesh.vertexCount > 0)
            {
                commands.DrawMesh(mesh, Matrix4x4.identity, maskMaterial, 0, 0);
            }
            Graphics.ExecuteCommandBuffer(commands);
        }
    }

    /// <summary>
    /// LEVELNUM2: the digits 0 to 9 of one face as a signed distance field atlas, baked offline by
    /// tools/bake_level_digits.py from an OFL font into Resources/LevelDigits/&lt;name&gt;.json (metrics) and
    /// &lt;name&gt;_sdf.bytes (one byte per texel, bottom row first; 0.5 is the outline, 1 is <see cref="SpreadTexels"/>
    /// texels inside). Raw bytes rather than an imported image: no import setting (compression, sRGB, mipmaps) can spoil
    /// the field on any platform. Units are em/1000, y up from the baseline. Loaded once per face and kept.
    /// </summary>
    public sealed class LevelDigitFont
    {
        public const string ResourceFolder = "LevelDigits/";

        /// <summary>The faces baked in the project (card_number.json's "font").</summary>
        public static readonly string[] Names = { "inter", "montserrat", "bebas", "dmserif" };

        public struct Glyph
        {
            public float Advance;
            public Rect Ink;
            public Rect Quad;
            public Rect Uv;
        }

        private static readonly Dictionary<string, LevelDigitFont> Cache = new Dictionary<string, LevelDigitFont>();

        private readonly Dictionary<char, Glyph> glyphs = new Dictionary<char, Glyph>();

        public string Name { get; private set; }
        public Texture2D Atlas { get; private set; }
        public float SpreadTexels { get; private set; }

        /// <summary>Atlas texels per glyph unit (the same for every glyph of the face).</summary>
        public float TexelsPerUnit { get; private set; }

        public bool TryGetGlyph(char c, out Glyph glyph) => glyphs.TryGetValue(c, out glyph);

        /// <summary>The face <paramref name="name"/>, loaded once; null (with a warning) when it is not in the build.</summary>
        public static LevelDigitFont Get(string name)
        {
            if (string.IsNullOrEmpty(name))
            {
                return null;
            }
            if (Cache.TryGetValue(name, out LevelDigitFont cached))
            {
                return cached != null && cached.Atlas != null ? cached : null;
            }
            LevelDigitFont loaded = null;
            try
            {
                loaded = Load(name);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[CardNumber] digit face {name} cannot be loaded: {e.Message}");
            }
            Cache[name] = loaded;
            return loaded;
        }

        private static LevelDigitFont Load(string name)
        {
            var meta = Resources.Load<TextAsset>(ResourceFolder + name);
            var data = Resources.Load<TextAsset>(ResourceFolder + name + "_sdf");
            if (meta == null || data == null)
            {
                Debug.LogWarning($"[CardNumber] digit face {name} not found in Resources/{ResourceFolder}");
                return null;
            }
            JObject o = JObject.Parse(meta.text);
            int width = o.Value<int>("atlasWidth");
            int height = o.Value<int>("atlasHeight");
            byte[] bytes = data.bytes;
            if (width <= 0 || height <= 0 || bytes.Length != width * height)
            {
                Debug.LogWarning($"[CardNumber] digit face {name}: atlas {width} x {height} does not match {bytes.Length} bytes");
                return null;
            }
            var font = new LevelDigitFont { Name = name, SpreadTexels = o.Value<float>("spreadTexels") };
            Texture2D atlas;
            if (SystemInfo.SupportsTextureFormat(TextureFormat.R8))
            {
                atlas = new Texture2D(width, height, TextureFormat.R8, false, true);
                atlas.LoadRawTextureData(bytes);
            }
            else
            {
                atlas = new Texture2D(width, height, TextureFormat.RGBA32, false, true);
                var pixels = new Color32[bytes.Length];
                for (int i = 0; i < bytes.Length; i++)
                {
                    pixels[i] = new Color32(bytes[i], bytes[i], bytes[i], 255);
                }
                atlas.SetPixels32(pixels);
            }
            atlas.name = "LevelDigits_" + name;
            atlas.filterMode = FilterMode.Bilinear;
            atlas.wrapMode = TextureWrapMode.Clamp;
            atlas.hideFlags = HideFlags.HideAndDontSave;
            atlas.Apply(false, true);
            font.Atlas = atlas;
            foreach (JToken g in (JArray)o["glyphs"])
            {
                string c = g.Value<string>("c");
                if (string.IsNullOrEmpty(c))
                {
                    continue;
                }
                var glyph = new Glyph
                {
                    Advance = g.Value<float>("advance"),
                    Ink = Box(g["ink"]),
                    Quad = Box(g["quad"]),
                    Uv = Box(g["uv"]),
                };
                font.glyphs[c[0]] = glyph;
                if (font.TexelsPerUnit <= 0f && glyph.Quad.width > 0f)
                {
                    font.TexelsPerUnit = glyph.Uv.width * width / glyph.Quad.width;
                }
            }
            return font.glyphs.Count > 0 && font.TexelsPerUnit > 0f ? font : null;
        }

        private static Rect Box(JToken t)
        {
            var a = (JArray)t;
            float x0 = a[0].Value<float>(), y0 = a[1].Value<float>(), x1 = a[2].Value<float>(), y1 = a[3].Value<float>();
            return Rect.MinMaxRect(x0, y0, x1, y1);
        }
    }

    /// <summary>
    /// LEVELNUM round 3: the intro card number's tunable values, read from an optional JSON file so they can be tuned on
    /// Windows without a rebuild: StreamingAssets/card_number.json (in a Windows build:
    /// OutOfSight_Data/StreamingAssets/card_number.json; in the editor: Assets/StreamingAssets/card_number.json, shipped
    /// with these defaults). Read at every card shown (each level start and restart, R). A missing file, a missing key, a
    /// wrong type or bad JSON falls back to the built-in default with a warning; every value is clamped to a sane range.
    /// On Android StreamingAssets is inside the APK: the file is not read there and the built-in defaults (the same
    /// values as the shipped file) apply. LEVELNUM2 added the face, the easing, the fade-in, the edge and the inner shade.
    /// </summary>
    public sealed class CardNumberSettings
    {
        public const string FileName = "card_number.json";

        /// <summary>Tests only: a file to read instead of StreamingAssets/card_number.json.</summary>
        public static string PathOverride;

        /// <summary>The built-in values (the shipped file carries the same).</summary>
        public static readonly CardNumberSettings Defaults = new CardNumberSettings();

        /// <summary>dimOpacity: the dim's opacity outside the digits, 0 to 1.</summary>
        public float DimOpacity { get; private set; } = 0.6f;

        /// <summary>dimColor: the dim's colour, [r, g, b] each 0 to 1 (also the inner shade's colour).</summary>
        public Color DimColor { get; private set; } = new Color(0.07f, 0.07f, 0.08f, 1f);

        /// <summary>washOpacity: the wash inside the digits, 0 (clear glass) to 1.</summary>
        public float WashOpacity { get; private set; } = 0.04f;

        /// <summary>washColor: the wash's colour, [r, g, b] each 0 to 1.</summary>
        public Color WashColor { get; private set; } = new Color(1f, 1f, 1f, 1f);

        /// <summary>startZoom: the number's size at the card's appearance in multiples of its settled size, 1 to 30.</summary>
        public float StartZoom { get; private set; } = 12.4f;

        /// <summary>zoomSeconds: the zoom-out's length, 0 (none) to 10 s.</summary>
        public float ZoomSeconds { get; private set; } = 2f;

        /// <summary>settledHeight: the settled digits' height as a fraction of the screen height, 0.1 to 1.2.</summary>
        public float SettledHeight { get; private set; } = 0.5f;

        /// <summary>fadeSeconds: the card's fade-out from the first input, 0.05 to 5 s.</summary>
        public float FadeSeconds { get; private set; } = 0.4f;

        /// <summary>font: the digits' face, one of <see cref="LevelDigitFont.Names"/>.</summary>
        public string Font { get; private set; } = "dmserif";

        /// <summary>easing: the zoom's ease-out curve, one of <see cref="CardNumber.Easings"/>.</summary>
        public string Easing { get; private set; } = "expo";

        /// <summary>fadeInSeconds: the dim's and the digits' fade-in when the card appears, 0 (none) to 2 s.</summary>
        public float FadeInSeconds { get; private set; } = 0.2f;

        /// <summary>edgeOpacity: the hairline light edge just inside the digits' outline, 0 (none) to 1.</summary>
        public float EdgeOpacity { get; private set; } = 0.25f;

        /// <summary>edgeWidth: that hairline's width in pixels of a 1080 pixel tall screen, 0.5 to 8.</summary>
        public float EdgeWidth { get; private set; } = 1.5f;

        /// <summary>edgeColor: the hairline's colour, [r, g, b] each 0 to 1.</summary>
        public Color EdgeColor { get; private set; } = new Color(1f, 1f, 1f, 1f);

        /// <summary>innerShadeOpacity: the soft shade (the dim's colour) inside the outline, fading inward, 0 (none) to 1.</summary>
        public float InnerShadeOpacity { get; private set; } = 0.2f;

        /// <summary>innerShadeWidth: how far inward that shade fades, in pixels of a 1080 pixel tall screen, 1 to 40.</summary>
        public float InnerShadeWidth { get; private set; } = 24f;

        /// <summary>The file read on this platform, or null where it is not read (Android: inside the APK).</summary>
        public static string FilePath
        {
            get
            {
                if (!string.IsNullOrEmpty(PathOverride))
                {
                    return PathOverride;
                }
                return Application.platform == RuntimePlatform.Android ? null : Path.Combine(Application.streamingAssetsPath, FileName);
            }
        }

        /// <summary>The settings from <see cref="FilePath"/>, or the defaults (with a warning when the file is missing or bad).</summary>
        public static CardNumberSettings Load()
        {
            string path = FilePath;
            if (path == null)
            {
                return Defaults;
            }
            string json;
            try
            {
                if (!File.Exists(path))
                {
                    Debug.LogWarning($"[CardNumber] {path} not found: the built-in values apply");
                    return Defaults;
                }
                json = File.ReadAllText(path);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[CardNumber] {path} cannot be read ({e.Message}): the built-in values apply");
                return Defaults;
            }
            var problems = new List<string>();
            CardNumberSettings settings = Parse(json, problems);
            if (problems.Count > 0)
            {
                Debug.LogWarning($"[CardNumber] {path}: " + string.Join("; ", problems));
            }
            return settings;
        }

        /// <summary>
        /// The settings in <paramref name="json"/>: each key read, checked and clamped, the default kept for a missing or
        /// wrong one; bad JSON gives the defaults. Every fallback and clamp adds a line to <paramref name="problems"/>.
        /// </summary>
        public static CardNumberSettings Parse(string json, List<string> problems)
        {
            var s = new CardNumberSettings();
            JObject o;
            try
            {
                o = JObject.Parse(json ?? string.Empty);
            }
            catch (Exception e)
            {
                problems?.Add("bad JSON, the built-in values apply (" + e.Message + ")");
                return s;
            }
            s.DimOpacity = Number(o, "dimOpacity", s.DimOpacity, 0f, 1f, problems);
            s.DimColor = Rgb(o, "dimColor", s.DimColor, problems);
            s.WashOpacity = Number(o, "washOpacity", s.WashOpacity, 0f, 1f, problems);
            s.WashColor = Rgb(o, "washColor", s.WashColor, problems);
            s.StartZoom = Number(o, "startZoom", s.StartZoom, 1f, 30f, problems);
            s.ZoomSeconds = Number(o, "zoomSeconds", s.ZoomSeconds, 0f, 10f, problems);
            s.SettledHeight = Number(o, "settledHeight", s.SettledHeight, 0.1f, 1.2f, problems);
            s.FadeSeconds = Number(o, "fadeSeconds", s.FadeSeconds, 0.05f, 5f, problems);
            s.Font = Choice(o, "font", s.Font, LevelDigitFont.Names, problems);
            s.Easing = Choice(o, "easing", s.Easing, CardNumber.Easings, problems);
            s.FadeInSeconds = Number(o, "fadeInSeconds", s.FadeInSeconds, 0f, 2f, problems);
            s.EdgeOpacity = Number(o, "edgeOpacity", s.EdgeOpacity, 0f, 1f, problems);
            s.EdgeWidth = Number(o, "edgeWidth", s.EdgeWidth, 0.5f, 8f, problems);
            s.EdgeColor = Rgb(o, "edgeColor", s.EdgeColor, problems);
            s.InnerShadeOpacity = Number(o, "innerShadeOpacity", s.InnerShadeOpacity, 0f, 1f, problems);
            s.InnerShadeWidth = Number(o, "innerShadeWidth", s.InnerShadeWidth, 1f, 40f, problems);
            return s;
        }

        private static string Text(float v) => v.ToString(CultureInfo.InvariantCulture);

        // Internal: MenuCameraSettings (FISHEYE) reads its numbers the same way.
        internal static float Number(JObject o, string key, float fallback, float min, float max, List<string> problems)
        {
            JToken t = o[key];
            if (t == null)
            {
                problems?.Add($"{key} missing, {Text(fallback)} used");
                return fallback;
            }
            if (t.Type != JTokenType.Float && t.Type != JTokenType.Integer)
            {
                problems?.Add($"{key} is not a number, {Text(fallback)} used");
                return fallback;
            }
            float v = t.Value<float>();
            if (float.IsNaN(v) || float.IsInfinity(v))
            {
                problems?.Add($"{key} is not a finite number, {Text(fallback)} used");
                return fallback;
            }
            float clamped = Mathf.Clamp(v, min, max);
            if (clamped != v)
            {
                problems?.Add($"{key} {Text(v)} clamped to {Text(clamped)}");
            }
            return clamped;
        }

        private static string Choice(JObject o, string key, string fallback, string[] allowed, List<string> problems)
        {
            JToken t = o[key];
            if (t == null)
            {
                problems?.Add($"{key} missing, \"{fallback}\" used");
                return fallback;
            }
            if (t.Type != JTokenType.String)
            {
                problems?.Add($"{key} is not a text, \"{fallback}\" used");
                return fallback;
            }
            string v = t.Value<string>().Trim().ToLowerInvariant();
            if (Array.IndexOf(allowed, v) < 0)
            {
                problems?.Add($"{key} \"{v}\" is not one of {string.Join(", ", allowed)}, \"{fallback}\" used");
                return fallback;
            }
            return v;
        }

        private static Color Rgb(JObject o, string key, Color fallback, List<string> problems)
        {
            JToken t = o[key];
            if (t == null)
            {
                problems?.Add($"{key} missing, the built-in colour used");
                return fallback;
            }
            if (!(t is JArray a) || a.Count != 3)
            {
                problems?.Add($"{key} is not [r, g, b], the built-in colour used");
                return fallback;
            }
            var c = new float[3];
            for (int i = 0; i < 3; i++)
            {
                if (a[i].Type != JTokenType.Float && a[i].Type != JTokenType.Integer)
                {
                    problems?.Add($"{key} is not [r, g, b] numbers, the built-in colour used");
                    return fallback;
                }
                float v = a[i].Value<float>();
                if (float.IsNaN(v) || float.IsInfinity(v))
                {
                    problems?.Add($"{key} is not [r, g, b] finite numbers, the built-in colour used");
                    return fallback;
                }
                c[i] = Mathf.Clamp01(v);
                if (c[i] != v)
                {
                    problems?.Add($"{key}[{i}] {Text(v)} clamped to {Text(c[i])}");
                }
            }
            return new Color(c[0], c[1], c[2], 1f);
        }
    }
}
