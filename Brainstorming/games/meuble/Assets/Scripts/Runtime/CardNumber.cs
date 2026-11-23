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
    /// which the scene shows, nearly clear (a faint white wash). The number starts several times its final size (only part
    /// of a digit shows) and zooms out with a smooth ease-out to its settled size, a fraction of the screen height, centred
    /// on the screen. The HUD draws it first, so every HUD text stays on top. Round 3: every value comes from
    /// <see cref="CardNumberSettings"/>, read again from StreamingAssets/card_number.json each time the card is shown.
    /// How (round 2): the first version cut the digits out with a uGUI stencil mask; in the built player the overlay
    /// canvas had no working stencil and the digits showed dimmed with their rim. Now nothing depends on stencil, depth or
    /// destination colour. The digits' glyph quads (the display face, from a TextGenerator) are drawn by a command buffer
    /// into a small mask texture (<see cref="MaskShaderName"/>), and the layer is a RawImage whose shader
    /// (<see cref="DimShaderName"/>) mixes dim and wash by that mask, with plain alpha blending. Both shaders are created
    /// from code only: ProjectSetup lists them in Always Included Shaders.
    /// </summary>
    public sealed class CardNumber
    {
        public const string DimShaderName = "OutOfSight/UI Card Dim";
        public const string MaskShaderName = "OutOfSight/UI Number Mask";

        /// <summary>The values in use, read again at every <see cref="SetNumber"/> (each card shown, so each restart).</summary>
        public CardNumberSettings Settings { get; private set; } = CardNumberSettings.Defaults;

        // The glyphs are generated at this size (canvas units at scale 1); the mask texture is this fraction of the
        // canvas's pixel size (bilinear upsampling softens the hole's edge by about a pixel).
        private const int FontSize = 480;
        private const float MaskResolution = 0.5f;

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
        private string digits = string.Empty;
        private bool disposed;
        private bool building;

        /// <summary>The number shown (0: none, the layer is a plain dim).</summary>
        public int Number { get; private set; }

        /// <summary>Seconds of the zoom played.</summary>
        public float Age { get; set; } = 99f;

        /// <summary>The number's scale now, and the scale it settles at for the current canvas height.</summary>
        public float Scale { get; private set; }
        public float FinalScale { get; private set; }

        /// <summary>Both shaders were found: the digits are holes (false: a plain dim, with a warning).</summary>
        public bool Ready => dimMaterial != null && maskMaterial != null;

        /// <summary>The layer group's alpha (the card's).</summary>
        public float Alpha => group != null ? group.alpha : 0f;

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
            Font.textureRebuilt += OnFontRebuilt;
        }

        /// <summary>Releases the mask texture and the font hook (the HUD is destroyed).</summary>
        public void Dispose()
        {
            disposed = true;
            Font.textureRebuilt -= OnFontRebuilt;
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
            Settings = CardNumberSettings.Load();
            ApplyColours();
            Number = Mathf.Max(0, number);
            digits = Number > 0 ? Number.ToString(System.Globalization.CultureInfo.InvariantCulture) : string.Empty;
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
            FinalScale = inkSize.y > 1f ? Settings.SettledHeight * height / inkSize.y : 1f;
            float t = Settings.ZoomSeconds > 0f ? Mathf.Clamp01(age / Settings.ZoomSeconds) : 1f;
            Scale = FinalScale * Mathf.Exp(Mathf.Log(Settings.StartZoom) * (1f - ZoomEase(t)));
            if (shown && Ready)
            {
                DrawMask(canvas, pixels);
            }
        }

        /// <summary>The dim's and the wash's colours and opacities from <see cref="Settings"/> (a plain dim without the shaders).</summary>
        private void ApplyColours()
        {
            Color dim = Settings.DimColor;
            dim.a = Settings.DimOpacity;
            Color wash = Settings.WashColor;
            wash.a = Settings.WashOpacity;
            if (dimMaterial != null)
            {
                dimMaterial.SetColor("_DimColor", dim);
                dimMaterial.SetColor("_WashColor", wash);
            }
            else
            {
                layer.color = dim;
            }
        }

        /// <summary>The zoom's curve: a smooth ease-out (cubic), no overshoot, applied to the scale in log space.</summary>
        public static float ZoomEase(float t)
        {
            float u = 1f - Mathf.Clamp01(t);
            return 1f - u * u * u;
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

        private void OnFontRebuilt(Font font)
        {
            if (!disposed && !building && font == Hud.DisplayFont && Number > 0)
            {
                // The atlas moved the glyphs: their UVs are stale.
                BuildMesh();
            }
        }

        /// <summary>The digits' glyph quads in the display face at <see cref="FontSize"/>, their ink centred on the origin.</summary>
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
            Font font = Hud.DisplayFont;
            if (string.IsNullOrEmpty(digits) || font == null)
            {
                return;
            }
            // A request that grows the atlas raises Font.textureRebuilt at once: no rebuild from inside this one.
            building = true;
            try
            {
                font.RequestCharactersInTexture(digits, FontSize, FontStyle.Normal);
            }
            finally
            {
                building = false;
            }
            var settings = new TextGenerationSettings
            {
                font = font,
                fontSize = FontSize,
                fontStyle = FontStyle.Normal,
                color = Color.white,
                lineSpacing = 1f,
                richText = false,
                scaleFactor = 1f,
                textAnchor = TextAnchor.MiddleCenter,
                alignByGeometry = false,
                resizeTextForBestFit = false,
                updateBounds = false,
                verticalOverflow = VerticalWrapMode.Overflow,
                horizontalOverflow = HorizontalWrapMode.Overflow,
                generationExtents = new Vector2(FontSize * 4f, FontSize * 2f),
                pivot = new Vector2(0.5f, 0.5f),
                generateOutOfBounds = true,
            };
            var generator = new TextGenerator();
            generator.Populate(digits, settings);
            IList<UIVertex> verts = generator.verts;
            int quads = verts.Count / 4;
            var min = new Vector2(float.MaxValue, float.MaxValue);
            var max = new Vector2(float.MinValue, float.MinValue);
            for (int i = 0; i < quads * 4; i++)
            {
                Vector3 p = verts[i].position;
                min = Vector2.Min(min, p);
                max = Vector2.Max(max, p);
            }
            if (quads == 0)
            {
                return;
            }
            Vector2 centre = (min + max) * 0.5f;
            inkSize = max - min;
            for (int q = 0; q < quads; q++)
            {
                for (int k = 0; k < 4; k++)
                {
                    UIVertex v = verts[q * 4 + k];
                    positions.Add(new Vector3(v.position.x - centre.x, v.position.y - centre.y, 0f));
                    uvs.Add(v.uv0);
                }
                int b = q * 4;
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
                maskMaterial.mainTexture = font.material.mainTexture;
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
    /// LEVELNUM round 3: the intro card number's tunable values, read from an optional JSON file so they can be tuned on
    /// Windows without a rebuild: StreamingAssets/card_number.json (in a Windows build:
    /// OutOfSight_Data/StreamingAssets/card_number.json; in the editor: Assets/StreamingAssets/card_number.json, shipped
    /// with these defaults). Read at every card shown (each level start and restart, R). A missing file, a missing key, a
    /// wrong type or bad JSON falls back to the built-in default with a warning; every value is clamped to a sane range.
    /// On Android StreamingAssets is inside the APK: the file is not read there and the built-in defaults (the same
    /// values as the shipped file) apply.
    /// </summary>
    public sealed class CardNumberSettings
    {
        public const string FileName = "card_number.json";

        /// <summary>Tests only: a file to read instead of StreamingAssets/card_number.json.</summary>
        public static string PathOverride;

        /// <summary>The built-in values (the shipped file carries the same).</summary>
        public static readonly CardNumberSettings Defaults = new CardNumberSettings();

        /// <summary>dimOpacity: the dim's opacity outside the digits, 0 to 1.</summary>
        public float DimOpacity { get; private set; } = 0.55f;

        /// <summary>dimColor: the dim's colour, [r, g, b] each 0 to 1.</summary>
        public Color DimColor { get; private set; } = new Color(0.07f, 0.07f, 0.08f, 1f);

        /// <summary>washOpacity: the white wash inside the digits, 0 (clear hole) to 1.</summary>
        public float WashOpacity { get; private set; } = 0.05f;

        /// <summary>washColor: the wash's colour, [r, g, b] each 0 to 1.</summary>
        public Color WashColor { get; private set; } = new Color(1f, 1f, 1f, 1f);

        /// <summary>startZoom: the number's size at the card's appearance in multiples of its settled size, 1 to 30.</summary>
        public float StartZoom { get; private set; } = 10f;

        /// <summary>zoomSeconds: the zoom-out's length, 0 (none) to 10 s.</summary>
        public float ZoomSeconds { get; private set; } = 1.75f;

        /// <summary>settledHeight: the settled digits' height as a fraction of the screen height, 0.1 to 1.2.</summary>
        public float SettledHeight { get; private set; } = 0.62f;

        /// <summary>fadeSeconds: the card's fade-out from the first input, 0.05 to 5 s.</summary>
        public float FadeSeconds { get; private set; } = 0.4f;

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
            return s;
        }

        private static string Text(float v) => v.ToString(CultureInfo.InvariantCulture);

        private static float Number(JObject o, string key, float fallback, float min, float max, List<string> problems)
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
