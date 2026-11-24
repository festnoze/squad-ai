using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// The x-ray of docs/CONTRACT_M3.md 6 (pillar 2: the player always knows where every inhabitant looks).
    /// Four URP RenderObjects features on the renderer, set up by OutOfSight.Editor.ProjectSetup:
    /// 1. <see cref="MaskFeature"/>: the visible pixels of the Occluder layer (the walls and every prop flagged
    ///    as an occluder, such as the tall bookshelf) mark the stencil, drawn with an invisible material;
    /// 2. <see cref="ConeFeature"/>: the vision cones (their own layer) where a marked occluder hides them, at
    ///    reduced alpha (depth test Greater, stencil Equal);
    /// 3. <see cref="SilhouetteFeature"/>: the inhabitants where a marked occluder hides them, as one flat
    ///    silhouette (depth Greater, stencil Equal, and the pass bumps the stencil so each pixel draws once);
    /// 4. <see cref="MarkerFeature"/>: the world space UI on the Inhabitant layer over everything, depth test
    ///    Always: the "?" and "!" markers and each inhabitant's facing chevron (<see cref="VisionConeView"/>).
    /// The x-ray never draws over the player's chair, a prop off the Occluder layer or a visible inhabitant: only
    /// Occluder pixels carry the mark, which keeps the red chair as easy to find as without it.
    /// </summary>
    public static class XRay
    {
        /// <summary>The vision cones' own layer, so the x-ray pass can pick them (ProjectSetup declares it).</summary>
        public const string ConeLayerName = "VisionCone";
        public const int ConeLayerIndex = 11;

        public const string MaskFeature = "XRay Mask";
        public const string ConeFeature = "XRay Cones";
        public const string SilhouetteFeature = "XRay Silhouette";
        public const string MarkerFeature = "XRay Markers";

        /// <summary>The stencil value of a visible occluder pixel, the only pixels the x-ray draws on.</summary>
        public const int StencilMark = 1;

        private static int coneLayer = -2;

        /// <summary>The VisionCone layer, or Default (no x-ray for the cones) with one warning when it is missing.</summary>
        public static int ConeLayer
        {
            get
            {
                if (coneLayer == -2)
                {
                    coneLayer = LayerMask.NameToLayer(ConeLayerName);
                    if (coneLayer < 0)
                    {
                        Debug.LogWarning($"[XRay] Layer '{ConeLayerName}' is not declared; run OutOfSight > Project Setup. Cones get no x-ray.");
                        coneLayer = 0;
                    }
                }
                return coneLayer;
            }
        }

        /// <summary>
        /// What is wrong with the x-ray and the ambient occlusion on the renderer in use: an empty list when the
        /// four features and the SSAO are there, active and configured (tests and the built player check).
        /// </summary>
        public static List<string> Problems()
        {
            var problems = new List<string>();
            var asset = GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
            if (asset == null)
            {
                problems.Add("the render pipeline is not URP");
                return problems;
            }
            ScriptableRendererData data = asset.rendererDataList.Length > 0 ? asset.rendererDataList[0] : null;
            if (data == null)
            {
                problems.Add("the URP asset has no renderer data");
                return problems;
            }
            int inhabitant = 1 << Layers.Inhabitant;
            int cones = 1 << ConeLayer;
            Check(data, MaskFeature, 1 << Layers.Occluder, CompareFunction.LessEqual, true, CompareFunction.Always, problems);
            Check(data, ConeFeature, cones, CompareFunction.Greater, true, CompareFunction.Equal, problems);
            Check(data, SilhouetteFeature, inhabitant, CompareFunction.Greater, true, CompareFunction.Equal, problems);
            Check(data, MarkerFeature, inhabitant, CompareFunction.Always, false, null, problems);
            bool ssao = false;
            foreach (ScriptableRendererFeature f in data.rendererFeatures)
            {
                ssao |= f is ScreenSpaceAmbientOcclusion && f.isActive;
            }
            if (!ssao)
            {
                problems.Add("no active SSAO feature on " + data.name);
            }
            return problems;
        }

        /// <summary>
        /// Cones look (2026-11-20): the override material of the <see cref="ConeFeature"/> pass on the renderer in use (the
        /// vision cone shader in its hatched x-ray mode, XRay_Cone.mat), or null when the pass is missing (tests).
        /// </summary>
        public static Material ConeOverrideMaterial()
        {
            var asset = GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
            ScriptableRendererData data = asset != null && asset.rendererDataList.Length > 0 ? asset.rendererDataList[0] : null;
            if (data == null)
            {
                return null;
            }
            foreach (ScriptableRendererFeature f in data.rendererFeatures)
            {
                if (f is RenderObjects r && f.name == ConeFeature)
                {
                    return r.settings.overrideMaterial;
                }
            }
            return null;
        }

        private static void Check(ScriptableRendererData data, string name, int layerMask, CompareFunction depth, bool material,
            CompareFunction? stencil, List<string> problems)
        {
            RenderObjects found = null;
            foreach (ScriptableRendererFeature f in data.rendererFeatures)
            {
                if (f is RenderObjects r && f.name == name)
                {
                    found = r;
                }
            }
            if (found == null)
            {
                problems.Add($"{data.name} has no RenderObjects feature '{name}'");
                return;
            }
            RenderObjects.RenderObjectsSettings s = found.settings;
            if (!found.isActive)
            {
                problems.Add($"'{name}' is inactive");
            }
            if (s.filterSettings.LayerMask.value != layerMask)
            {
                problems.Add($"'{name}' renders layer mask {s.filterSettings.LayerMask.value}, expected {layerMask}");
            }
            if (!s.overrideDepthState || s.depthCompareFunction != depth || s.enableWrite)
            {
                problems.Add($"'{name}' depth state is {s.depthCompareFunction} (override {s.overrideDepthState}, write {s.enableWrite}), expected {depth} without write");
            }
            if (material && s.overrideMaterial == null)
            {
                problems.Add($"'{name}' has no override material");
            }
            StencilStateData st = s.stencilSettings;
            bool stencilOk = stencil == null
                ? !st.overrideStencilState
                : st.overrideStencilState && st.stencilCompareFunction == stencil.Value && st.stencilReference == StencilMark;
            if (!stencilOk)
            {
                problems.Add($"'{name}' stencil is {(st.overrideStencilState ? st.stencilCompareFunction + " " + st.stencilReference : "off")}, expected {(stencil == null ? "off" : stencil + " " + StencilMark)}");
            }
        }
    }

    /// <summary>
    /// The translucent fan on the floor (PRD 4.3): range and angle of the cone, clipped by occluders with a
    /// fan of 40 raycasts. Each ray aims from the eye at the height of the furniture top, so a prop lower
    /// than the furniture never shortens the fan: the top corners of the chair are seen over it, which is
    /// exactly what the vision test does. The wedge is a superset of where the chair can be seen, never a
    /// subset: the fan may warn about a spot that is safe, it never hides a spot that is not.
    /// M5B (CONTRACT_M5 17, critique m20): an eye BELOW the furniture top (the dog's 0.35 m, a human's 1.6 m under the floor
    /// lamp's top) looks up at it, so the far top is the hardest to see and a nearer one may show over a cover the far ray
    /// hits. Such a ray goes on past the hit (<see cref="RayReach"/>): a cover lower than the top lets the top be seen up to
    /// hit x (top - eye) / (cover - eye) away (the sight line clears the cover's near edge), and the ray is cast again toward
    /// that nearer top, up to <see cref="Tuning.ConeSupersetPasses"/> times. A cover at least as high as the top ends the ray
    /// at the hit, as before. An eye at or above the top keeps the M1 ray exactly.
    /// M5B (critique m14): on a level with a platform or a ramp each ray is cut in <see cref="Radial"/> samples, every
    /// <see cref="Tuning.ConeRadialStep"/> (about) from the eye and the last on the rim (a ray cut short repeats its rim), each
    /// on the floor under it, and a sample near a higher one (<see cref="DrapedHeight"/>) is raised to it: the fan drapes
    /// over a platform edge and lies on the platform top, never inside it (where the x-ray pass would draw it as hidden). The
    /// outline is the M1 fan's. On a flat floor a ray is one sample: the M1 fan.
    /// M3: the cone lives on the <see cref="XRay.ConeLayerName"/> layer, so where an Occluder hides it the
    /// x-ray draws it again (<see cref="XRay"/>).
    /// M3.1: a facing chevron stands in front of the inhabitant's face and points where it looks, in the cone's
    /// color. It is world space UI on the Inhabitant layer, so the marker pass draws it over walls: a hidden
    /// inhabitant's gaze always shows. A CanvasRenderer, it adds no renderer and no material to the budgets.
    /// M4 (docs/CONTRACT_M4.md 2.3): while the player lamp is off, the fan reaches only the scaled range the vision
    /// test uses for it (<see cref="RangeFactor"/>), in a dimmer color.
    /// M5 (docs/CONTRACT_M5.md 3, CONTRACT_M5_v3.md 15.4 and 15.5): each fan uses its watcher's own range and half angle
    /// (the personality's, times the lamp factor) from its own eye (the dog's 0.35 m); every vertex lies on the floor
    /// under it (<see cref="FloorMap"/>), and each ray aims at the furniture top above the floor where it lands. The dog's
    /// fan and chevron are cyan (CONTRACT_M5 17): <see cref="Tuning.DogConeColor"/> while calm,
    /// <see cref="Tuning.DogConeAlarmColor"/> while it sees the furniture. A sleeping watcher's fan and chevron are hidden
    /// (its eye is closed; the inhabitant shows a "z" instead).
    /// Cones look (product owner request, 2026-11-20): the fan is drawn by <see cref="ConeShaderName"/>
    /// (Assets/Settings/VisionCone.shader), a fan of light whose opacity fades with distance and toward its sides, with faint
    /// streaks and a thin crisp line on its true edge; still one material per colour (<see cref="ConeMaterial"/>). What the
    /// shader needs per watcher rides the mesh (UV0 the watcher's frame in ranges, UV1 the rim fraction, the half angle, a
    /// phase seed and the <see cref="Look"/>), never a property block. The look tells the states apart by pattern as well as
    /// by colour: calm (a still gradient), searching (a sweeping band) and seeing (waves running outward, a quick pulse); the
    /// part a wall hides is the x-ray pass's blue hatching (XRay_Cone.mat, the same shader). The outline of the fan, its
    /// rays and every rule above are unchanged: only the fill's look is new.
    /// </summary>
    [DefaultExecutionOrder(100)]
    public sealed class VisionConeView : MonoBehaviour
    {
        public Inhabitant Owner;
        public Vision Vision;

        /// <summary>Height the rays aim at: the top sample height of the player furniture.</summary>
        public float TargetHeight = 0.87f;

        /// <summary>
        /// CONECLIP (docs/next/progress/CONECLIP.md): the planar half diagonal of the furniture's top samples around its
        /// centre (LevelBuilder.ConeTargetRadius). A low cover's shadow ends this much nearer, so a furniture centred just
        /// inside the shadow whose far top corner pokes out of it is still under the fan.
        /// </summary>
        public float TargetRadius;

        /// <summary>
        /// CONECLIP: the shadows of the low covers are taken out of the fan (<see cref="ShadowReach"/>). False only in the
        /// ConeClipShots look tool, to render the old fan beside the new one.
        /// </summary>
        public static bool ClipShadows = true;

        /// <summary>Cones look: the fan's shader (Assets/Settings/VisionCone.shader; it ships with XRay_Cone.mat and in Always Included Shaders).</summary>
        public const string ConeShaderName = "OutOfSight/Vision Cone";

        /// <summary>Cones look: the watcher's state as the fan's pattern shows it (UV1.w of the fan mesh).</summary>
        public enum ConeLook
        {
            /// <summary>Watching calmly: a still soft gradient with a slow shimmer.</summary>
            Calm = 0,
            /// <summary>Alerted or investigating, without seeing the furniture: a bright band sweeps across the fan.</summary>
            Searching = 1,
            /// <summary>Seeing the furniture (the red fan): waves run outward from the eye, a quick pulse.</summary>
            Seeing = 2,
        }

        /// <summary>Cones look: the pattern the fan showed on the last frame (tests).</summary>
        public ConeLook Look { get; private set; } = ConeLook.Calm;

        private static readonly Dictionary<Color32, Material> ConeMaterials = new Dictionary<Color32, Material>();
        private static Shader coneShader;
        private static bool coneShaderMissing;

        /// <summary>
        /// Cones look: the one fan material of <paramref name="color"/> (cached by colour, so every cone of a colour shares
        /// it: the "one material per cone colour" rule of the budgets), drawn by <see cref="ConeShaderName"/>. Without that
        /// shader (never expected: it ships with XRay_Cone.mat) it logs one error and falls back to the flat URP Unlit fan.
        /// </summary>
        public static Material ConeMaterial(Color color)
        {
            Color32 key = color;
            if (ConeMaterials.TryGetValue(key, out Material cached) && cached != null)
            {
                return cached;
            }
            if (coneShader == null && !coneShaderMissing)
            {
                coneShader = Shader.Find(ConeShaderName);
                if (coneShader == null || !coneShader.isSupported)
                {
                    coneShader = null;
                    coneShaderMissing = true;
                    Debug.LogError($"[VisionConeView] Shader '{ConeShaderName}' not found or unsupported: the cones fall back to the flat fan.");
                }
            }
            Material m;
            if (coneShader == null)
            {
                m = PrimitiveKit.UnlitTransparent(color);
            }
            else
            {
                m = new Material(coneShader)
                {
                    name = "VisionCone " + ColorUtility.ToHtmlStringRGBA(color),
                    renderQueue = (int)RenderQueue.Transparent,
                    hideFlags = HideFlags.DontUnloadUnusedAsset,
                };
                m.SetColor(BaseColorId, color);
            }
            ConeMaterials[key] = m;
            return m;
        }

        private static readonly Color Calm = new Color(1f, 0.93f, 0.55f, 0.20f);
        private static readonly Color Alarm = new Color(1f, 0.35f, 0.25f, 0.30f);
        // M4 (docs/CONTRACT_M4.md 2.3): the shorter fan of a dark lamp, dimmer and greyer. Own materials (cached by
        // color), so the x-ray override of the cone pass is untouched; they exist only while a lamp is off.
        private static readonly Color CalmDark = new Color(0.72f, 0.70f, 0.58f, 0.13f);
        private static readonly Color AlarmDark = new Color(0.85f, 0.32f, 0.26f, 0.22f);

        // The chevron: its fill in the cone's hue, nearly opaque, over a dark outline.
        private const float FacingAlpha = 0.95f;
        private static readonly Color FacingCalm = new Color(1f, 0.86f, 0.3f, FacingAlpha);
        private static readonly Color FacingAlarm = new Color(1f, 0.3f, 0.2f, FacingAlpha);
        // M5 (CONTRACT_M5 17): the dog's chevron, a deep teal while calm (its cone's cyan, shaded), the vivid alarm cyan while
        // it sees the furniture.
        private static readonly Color FacingDog = Shade(Tuning.DogConeColor, Tuning.DogChevronCalmShade, FacingAlpha);
        private static readonly Color FacingDogAlarm = Shade(Tuning.DogConeAlarmColor, 1f, FacingAlpha);
        // M5: the fan floats this far above the floor under each vertex (as M1's 0.015 above y = 0).
        private const float FloorLift = 0.015f;
        // M5B m20: a recast past a cover aims this much nearer than the exact clearance over its edge (Tuning).
        private const float ClearMargin = Tuning.ConeClearMargin;
        private const float FacingSize = 0.42f;
        // Ahead of the eyes along the gaze and a little below them, so the arrow never covers the face.
        private const float FacingAhead = 0.6f;
        private const float FacingDrop = 0.18f;

        /// <summary>M3.1: the facing chevron's transform (tests).</summary>
        public RectTransform Facing { get; private set; }

        private Image facingImage;
        private Canvas facingCanvas;
        private Mesh mesh;
        private MeshRenderer meshRenderer;
        // The apex and the rim (one vertex per ray), as last rebuilt: the public outline of the fan.
        private Vector3[] vertices;
        // M5B: the mesh itself, the apex then Radial samples per ray (the rim last), the floor height under each sample and
        // its planar distance from the eye; the spacing of the samples along a ray and the angle between two rays (radians).
        private Vector3[] meshVertices;
        private float[] rawHeights;
        private float[] sampleDistances;
        private int radial;
        private float spacing;
        private float rayStep;
        // Cones look: per mesh vertex, the shader's two UV channels (see the class summary), and this watcher's phase seed.
        private Vector2[] meshLocal;
        private Vector4[] meshData;
        // CONECLIP: per mesh vertex (UV2.x), 1 where the furniture top is hidden by a low cover in the middle of a ray (the
        // shader cuts the fan there), 0 elsewhere. Per ray: its reach once the end shadow is cut, and its middle shadows.
        private Vector2[] meshHidden;
        private float[] rayReach;
        private int[] gapCount;
        private float[] gapStart;
        private float[] gapEnd;
        private const int MaxGaps = 4;
        // CONECLIP: a collider whose bottom is higher than this above the eye's floor is not a cover standing on the floor
        // (a lintel, a shelf): what lies under it may be seen, so it casts no shadow on the fan.
        private const float CoverFloorGap = 0.05f;
        private static readonly RaycastHit[] ShadowHits = new RaycastHit[16];
        private static readonly RaycastHit[] BackHits = new RaycastHit[16];
        private static readonly float[] SpanStart = new float[16];
        private static readonly float[] SpanEnd = new float[16];
        private float seed;
        // M5B m14: a sample is raised to the floor of any other sample this many spacings away (diagonal neighbours included).
        private const float DrapeReach = Tuning.ConeDrapeReach;

        public void Init()
        {
            if (mesh != null)
            {
                return;
            }
            mesh = new Mesh { name = "VisionCone" };
            mesh.MarkDynamic();
            vertices = new Vector3[Tuning.ConeRayCount + 1];
            rayReach = new float[Tuning.ConeRayCount];
            gapCount = new int[Tuning.ConeRayCount];
            gapStart = new float[Tuning.ConeRayCount * MaxGaps];
            gapEnd = new float[Tuning.ConeRayCount * MaxGaps];
            // Cones look: each watcher's own phase, so two fans never pulse or sweep in step.
            seed = Mathf.Repeat(GetInstanceID() * 0.618034f, 1f);
            EnsureTopology(1);
            gameObject.AddComponent<MeshFilter>().sharedMesh = mesh;
            meshRenderer = gameObject.AddComponent<MeshRenderer>();
            meshRenderer.sharedMaterial = ConeMaterial(Calm);
            meshRenderer.shadowCastingMode = ShadowCastingMode.Off;
            meshRenderer.receiveShadows = false;
            gameObject.layer = XRay.ConeLayer;
            transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            BuildFacing();
            BuildOutline();
            Rebuild();
        }

        // ----- M6 (docs/CONTRACT_M6.md 2.1 and 2.3): the "Jamais" hide switch and the alerted dashed outline. -----

        private LineRenderer outline;
        private MaterialPropertyBlock outlineBlock;
        private static Material outlineMaterial;
        private static Texture2D dashTexture;
        private static readonly int BaseMapId = Shader.PropertyToID("_BaseMap");
        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");

        /// <summary>A dashed line around the fan's whole silhouette (apex and rim), shown only for an alerted watcher
        /// (CONTRACT_M6 2.3): a pattern, not only the fill's colour change, and it hides with the cone under "Jamais".
        /// It traces the same clipped ray hit distances as the mesh, so it never reaches past a wall.</summary>
        private void BuildOutline()
        {
            outline = gameObject.AddComponent<LineRenderer>();
            outline.useWorldSpace = true;
            outline.loop = true;
            outline.widthMultiplier = Tuning.ConeOutlineWidth;
            outline.numCapVertices = 0;
            outline.numCornerVertices = 0;
            outline.shadowCastingMode = ShadowCastingMode.Off;
            outline.receiveShadows = false;
            outline.textureMode = LineTextureMode.Tile;
            outline.sharedMaterial = OutlineMaterial();
            outline.enabled = false;
            // An instance block, created here (never as a static or instance field initializer: MaterialPropertyBlock's
            // native side refuses that, "not allowed to be called from a MonoBehaviour constructor").
            outlineBlock = new MaterialPropertyBlock();
        }

        private static Material OutlineMaterial()
        {
            if (outlineMaterial != null)
            {
                return outlineMaterial;
            }
            // A private instance (never PrimitiveKit's own shared white cache entry) so its texture is its own.
            outlineMaterial = new Material(PrimitiveKit.UnlitTransparent(Color.white))
            {
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
            outlineMaterial.SetTexture(BaseMapId, DashTexture());
            outlineMaterial.SetTextureScale(BaseMapId, new Vector2(1f / Tuning.ConeOutlineDash, 1f));
            return outlineMaterial;
        }

        /// <summary>A 50 percent duty cycle dash along U (Repeat), so a tiled LineRenderer reads as dashed, not solid.</summary>
        private static Texture2D DashTexture()
        {
            if (dashTexture != null)
            {
                return dashTexture;
            }
            const int n = 16;
            dashTexture = new Texture2D(n, 1, TextureFormat.RGBA32, false)
            {
                name = "ConeOutlineDash",
                wrapMode = TextureWrapMode.Repeat,
                filterMode = FilterMode.Point,
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
            var pixels = new Color[n];
            for (int i = 0; i < n; i++)
            {
                pixels[i] = i < n / 2 ? Color.white : new Color(1f, 1f, 1f, 0f);
            }
            dashTexture.SetPixels(pixels);
            dashTexture.Apply(false, true);
            return dashTexture;
        }

        /// <summary>M6 (CONTRACT_M6 2.3): the dashed outline is on now (tests; it also hides under "Jamais", as the fan).</summary>
        public bool OutlineVisible => outline != null && outline.enabled;

        /// <summary>M6 (CONTRACT_M6 2.1): the floor cone fan is currently rendered (tests; "Jamais" hides it, as <see cref="Hidden"/> does for a sleeping watcher).</summary>
        public bool MeshVisible => meshRenderer != null && meshRenderer.enabled;

        /// <summary>A world space Canvas of 100 x 100 units scaled to <see cref="FacingSize"/> meters, holding the chevron.</summary>
        private void BuildFacing()
        {
            int layer = Layers.Inhabitant;
            var go = new GameObject("Facing", typeof(RectTransform)) { layer = layer };
            go.transform.SetParent(transform, false);
            Facing = (RectTransform)go.transform;
            Facing.sizeDelta = new Vector2(100f, 100f);
            Facing.localScale = Vector3.one * (FacingSize / 100f);
            Canvas canvas = go.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;
            canvas.sortingOrder = 4;
            facingCanvas = canvas;
            var imageGo = new GameObject("Chevron", typeof(RectTransform)) { layer = layer };
            imageGo.transform.SetParent(go.transform, false);
            var rect = (RectTransform)imageGo.transform;
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
            facingImage = imageGo.AddComponent<Image>();
            facingImage.sprite = ProceduralArt.Chevron;
            facingImage.raycastTarget = false;
            facingImage.color = FacingCalm;
        }

        private void LateUpdate()
        {
            if (mesh == null || Owner == null || Owner.Routine == null)
            {
                return;
            }
            // M5: a sleeping watcher sees nothing: no fan, no chevron (its "z" shows instead).
            Hidden = Owner.Routine.Asleep;
            // M6 (CONTRACT_M6 2.1): "Jamais" hides the floor cone renderers (this fan and its alert outline), never the
            // eye indicator or the screen edge pulse (Hud's own concern, untouched here).
            bool coneHidden = SaveStore.Options.HidesCone; // MUTATION:CONE_HIDE
            meshRenderer.enabled = !Hidden && !coneHidden;
            if (facingCanvas != null)
            {
                facingCanvas.enabled = !Hidden;
            }
            if (Hidden)
            {
                if (outline != null)
                {
                    outline.enabled = false;
                }
                return;
            }
            bool alarm = Vision != null && Vision.SeesPlayer;
            // Cones look: the pattern rides the mesh (UV1.w), so it is set before the rebuild writes it.
            InhabitantMode mode = Owner.Routine.Mode;
            bool searching = mode == InhabitantMode.Alerted || mode == InhabitantMode.Investigating;
            Look = alarm ? ConeLook.Seeing : searching ? ConeLook.Searching : ConeLook.Calm; // MUTATION:CONE_LOOK
            Rebuild();
            bool dark = RangeFactor < 1f;
            bool dog = Owner.IsDog;
            Color = ConeColor(dog, alarm, dark);
            meshRenderer.sharedMaterial = ConeMaterial(Color);
            if (facingImage != null)
            {
                facingImage.color = FacingColor(dog, alarm);
            }
            if (outline != null)
            {
                // CONTRACT_M6 2.3: a dashed outline on an alerted watcher's cone, not only the fill's colour change.
                outline.enabled = !coneHidden && alarm; // MUTATION:CONE_OUTLINE_ALARM
                if (outline.enabled)
                {
                    outlineBlock.SetColor(BaseColorId, new Color(Color.r, Color.g, Color.b, 0.95f));
                    outline.SetPropertyBlock(outlineBlock);
                }
            }
        }

        /// <summary>
        /// The chevron's fill: a human's yellow, red while it sees the furniture; M5: the dog's deep teal, the vivid
        /// <see cref="Tuning.DogConeAlarmColor"/> while it sees the furniture.
        /// </summary>
        public static Color FacingColor(bool dog, bool alarm) => dog ? (alarm ? FacingDogAlarm : FacingDog) : (alarm ? FacingAlarm : FacingCalm);

        /// <summary>M5: the chevron's fill on the last frame (tests).</summary>
        public Color FacingFill => facingImage != null ? facingImage.color : Color.clear;

        /// <summary>A colour times <paramref name="k"/> (its RGB), at <paramref name="alpha"/>.</summary>
        private static Color Shade(Color c, float k, float alpha) => new Color(c.r * k, c.g * k, c.b * k, alpha);

        /// <summary>M5: the fan's vertices (the apex, then one per ray), world space, as last rebuilt (tests).</summary>
        public Vector3[] Vertices => vertices;

        /// <summary>
        /// M5B: the samples per ray of the mesh (1 on a flat floor; the watcher's range over Tuning.ConeRadialStep on a level
        /// with a platform or a ramp).
        /// </summary>
        public int Radial => radial;

        /// <summary>M5B: the fan's mesh (world space: the cone's transform is the identity), for tests.</summary>
        public Mesh FanMesh => mesh;

        /// <summary>M5B: the mesh index of sample <paramref name="sample"/> (1 to <see cref="Radial"/>) of ray <paramref name="ray"/>.</summary>
        public int MeshIndex(int ray, int sample) => 1 + ray * radial + (sample - 1);

        /// <summary>
        /// M5B: the mesh of <paramref name="samples"/> samples per ray: the apex fan between the first samples, then two
        /// triangles per pair of neighbour samples, each wound clockwise seen from above (it faces up). The topology changes
        /// only when the samples per ray do.
        /// </summary>
        private void EnsureTopology(int samples)
        {
            samples = Mathf.Max(1, samples);
            if (samples == radial && meshVertices != null)
            {
                return;
            }
            radial = samples;
            int n = Tuning.ConeRayCount;
            int count = 1 + n * radial;
            meshVertices = new Vector3[count];
            rawHeights = new float[count];
            sampleDistances = new float[count];
            meshLocal = new Vector2[count];
            meshData = new Vector4[count];
            meshHidden = new Vector2[count];
            var triangles = new List<int>((n - 1) * (2 * radial - 1) * 3);
            for (int i = 0; i < n - 1; i++)
            {
                triangles.Add(0);
                triangles.Add(MeshIndex(i, 1));
                triangles.Add(MeshIndex(i + 1, 1));
                for (int s = 1; s < radial; s++)
                {
                    int a = MeshIndex(i, s);
                    int b = MeshIndex(i, s + 1);
                    int c = MeshIndex(i + 1, s + 1);
                    int d = MeshIndex(i + 1, s);
                    triangles.Add(a);
                    triangles.Add(b);
                    triangles.Add(c);
                    triangles.Add(a);
                    triangles.Add(c);
                    triangles.Add(d);
                }
            }
            var normals = new Vector3[count];
            for (int i = 0; i < count; i++)
            {
                normals[i] = Vector3.up;
            }
            mesh.Clear();
            mesh.indexFormat = count > 65000 ? IndexFormat.UInt32 : IndexFormat.UInt16;
            mesh.vertices = meshVertices;
            mesh.normals = normals;
            mesh.SetUVs(0, meshLocal);
            mesh.SetUVs(1, meshData);
            mesh.SetUVs(2, meshHidden);
            mesh.SetTriangles(triangles, 0);
        }

        /// <summary>M5: true while the watcher sleeps: the fan and the chevron are hidden.</summary>
        public bool Hidden { get; private set; }

        /// <summary>M5: the colour of the fan on the last frame (<see cref="ConeColor"/>).</summary>
        public Color Color { get; private set; } = Calm;

        /// <summary>
        /// The fan's colour: a human's warm yellow, red while it sees the furniture, both dimmer while a lamp is dark (M4);
        /// M5 (CONTRACT_M5 17): the dog's cyan <see cref="Tuning.DogConeColor"/>, the vivid, more opaque
        /// <see cref="Tuning.DogConeAlarmColor"/> while it sees the furniture, both shaded while a lamp is dark.
        /// </summary>
        public static Color ConeColor(bool dog, bool alarm, bool dark)
        {
            if (!dog)
            {
                return dark ? (alarm ? AlarmDark : CalmDark) : (alarm ? Alarm : Calm);
            }
            Color c = alarm ? Tuning.DogConeAlarmColor : Tuning.DogConeColor; // MUTATION:DOG_ALARM_HUE
            if (dark)
            {
                return Shade(c, Tuning.DogConeDarkShade, alarm ? Tuning.DogConeDarkAlarmAlpha : Tuning.DogConeDarkAlpha);
            }
            return Shade(c, 1f, alarm ? Tuning.DogConeAlarmAlpha : Tuning.DogConeCalmAlpha);
        }

        /// <summary>
        /// M4: the range factor the vision test uses for the player furniture (a dark lamp: LampOffLight), read from
        /// <see cref="Vision"/>. The fan shows that shorter range, dimmed.
        /// </summary>
        public float RangeFactor => Vision != null ? Vision.RangeFactor : 1f;

        /// <summary>
        /// M4: the fan's reach without occluders, in meters (tests). M5: the watcher's own range (the personality's, the
        /// teen's 6 m, the dog's 6 m) times the lamp factor.
        /// </summary>
        public float Range => (Owner != null && Owner.Routine != null ? Owner.Routine.ViewRange : Tuning.ViewRange) * RangeFactor; // MUTATION:CONE_RANGE

        /// <summary>M5: the fan's half angle, the watcher's own (the personality's).</summary>
        public float HalfAngle => Owner != null && Owner.Routine != null ? Owner.Routine.HalfAngle : Tuning.ViewHalfAngle;

        public void Rebuild()
        {
            if (mesh == null || Owner == null || Owner.Routine == null)
            {
                return;
            }
            Vector3 eye = Owner.VisualEyePosition;
            float yaw = Owner.VisualEyeYaw;
            FloorMap floor = Owner.Routine.Floor ?? FloorMap.Flat;
            int n = Tuning.ConeRayCount;
            float range = Range;
            float half = HalfAngle;
            // CONECLIP: every ray's reach first, then (on a flat floor) the shadows of the low covers it crosses: a shadow
            // that runs to the end of the ray cuts it, one in the middle is cut out of the fill (UV2) on radial samples.
            bool anyGap = false;
            float eyeFloor = floor.HeightAt(eye.x, eye.z);
            for (int i = 0; i < n; i++)
            {
                Vector3 dir = YawMath.Forward(yaw - half + 2f * half * i / (n - 1));
                float r = RayReach(eye, dir, range, floor);
                gapCount[i] = 0;
                if (ClipShadows && floor.IsFlat)
                {
                    r = ShadowReach(eye, dir, r, eyeFloor, i);
                    anyGap |= gapCount[i] > 0;
                }
                rayReach[i] = r;
            }
            // M5B m14: a level with a platform or a ramp cuts each ray every ConeRadialStep of the watcher's own range.
            int samples = floor.IsFlat ? 1 : Mathf.CeilToInt(Owner.Routine.ViewRange / Tuning.ConeRadialStep); // MUTATION:CONE_RADIAL
            if (anyGap)
            {
                // CONECLIP: a shadow in the middle of a ray needs samples along it to be cut out of the fill.
                samples = Mathf.CeilToInt(Owner.Routine.ViewRange / Tuning.ConeRadialStep);
            }
            EnsureTopology(samples);
            var origin = new Vector3(eye.x, 0f, eye.z);
            rawHeights[0] = eyeFloor;
            meshVertices[0] = new Vector3(eye.x, rawHeights[0] + FloorLift, eye.z);
            // The samples sit at the same distances on every ray (a ray cut short repeats its rim), so the samples of two
            // neighbour rays with the same index are neighbours on the floor too.
            spacing = Owner.Routine.ViewRange / radial;
            rayStep = 2f * half / (n - 1) * Mathf.Deg2Rad;
            // Cones look: the shader's per vertex data. UV0 is the sample in the watcher's frame (across, along the gaze) in
            // units of the fan's range; UV1 its fraction of its own ray's reach (1 on the rim), the half angle in radians,
            // the phase seed and the look.
            float unit = 1f / Mathf.Max(range, 1e-3f);
            float halfRadians = half * Mathf.Deg2Rad;
            float look = (float)Look;
            meshLocal[0] = Vector2.zero;
            meshData[0] = new Vector4(0f, halfRadians, seed, look);
            for (int i = 0; i < n; i++)
            {
                float a = yaw - half + 2f * half * i / (n - 1);
                Vector3 h = YawMath.Forward(a);
                float reach = rayReach[i];
                float relative = (a - yaw) * Mathf.Deg2Rad;
                float across = Mathf.Sin(relative) * unit;
                float along = Mathf.Cos(relative) * unit;
                for (int s = 1; s <= radial; s++)
                {
                    float d = s == radial ? reach : Mathf.Min(s * spacing, reach);
                    Vector3 p = origin + h * d;
                    int k = MeshIndex(i, s);
                    rawHeights[k] = floor.HeightAt(p.x, p.z);
                    sampleDistances[k] = d;
                    meshVertices[k] = p;
                    meshLocal[k] = new Vector2(across * d, along * d);
                    meshData[k] = new Vector4(reach > 1e-4f ? d / reach : 1f, halfRadians, seed, look);
                }
            }
            bool flat = floor.IsFlat;
            for (int i = 0; i < n; i++)
            {
                for (int s = 1; s <= radial; s++)
                {
                    int k = MeshIndex(i, s);
                    meshVertices[k].y = (flat ? rawHeights[k] : DrapedHeight(i, s)) + FloorLift;
                }
                vertices[i + 1] = meshVertices[MeshIndex(i, radial)];
            }
            vertices[0] = meshVertices[0];
            for (int i = 0; i < n; i++)
            {
                for (int s = 1; s <= radial; s++)
                {
                    int k = MeshIndex(i, s);
                    meshHidden[k] = new Vector2(anyGap && HiddenAround(i, sampleDistances[k]) ? 1f : 0f, 0f);
                }
            }
            mesh.vertices = meshVertices;
            mesh.SetUVs(0, meshLocal);
            mesh.SetUVs(1, meshData);
            mesh.SetUVs(2, meshHidden);
            mesh.RecalculateBounds();
            if (Facing != null)
            {
                PlaceFacing(eye, YawMath.Forward(yaw));
            }
            if (outline != null)
            {
                // M6 (CONTRACT_M6 2.3): the fan's own silhouette, a little above it so it never z-fights it: the apex,
                // then the rim ray by ray, looped (closing from the last ray's rim back to the apex). The apex must be
                // in the loop: without it, the closing segment ran straight from the last ray's rim back to the first
                // one, a chord across the whole wedge that ignored every wall a ray was clipped against in between.
                outline.positionCount = n + 1;
                Vector3 apex = vertices[0];
                outline.SetPosition(0, new Vector3(apex.x, apex.y + FloorLift, apex.z));
                for (int i = 0; i < n; i++)
                {
                    Vector3 p = vertices[i + 1];
                    outline.SetPosition(i + 1, new Vector3(p.x, p.y + FloorLift, p.z));
                }
            }
        }

        /// <summary>
        /// M5B m14: the height a sample is drawn at: the highest floor under any sample of its ray or of the two rays beside
        /// it (the apex included) within <see cref="DrapeReach"/> times the local spacing (the larger of the spacing along a
        /// ray and the gap between two rays there). The corners of a triangle of the fan between two whole rays lie within
        /// that reach of each other, so a triangle touching a platform sample lies at the platform's height or above, never
        /// inside it, and only the samples near a height change are raised. Samples on the same spot (a repeated rim) get the
        /// same height. The one exception is a triangle that joins the end of a ray cut short (by a wall or a cover) to the
        /// longer ray beside it: where that end meets a height change it may dip a few centimetres (probe step 37w bounds it).
        /// </summary>
        private float DrapedHeight(int ray, int sample)
        {
            int n = Tuning.ConeRayCount;
            int k = MeshIndex(ray, sample);
            float d = sampleDistances[k];
            Vector3 p = meshVertices[k];
            float reach = DrapeReach * Mathf.Max(spacing, d * rayStep);
            float reachSqr = reach * reach;
            float height = rawHeights[k];
            if (d <= reach)
            {
                height = Mathf.Max(height, rawHeights[0]);
            }
            int low = Mathf.Max(1, Mathf.FloorToInt((d - reach) / spacing));
            int high = Mathf.Min(radial, Mathf.CeilToInt((d + reach) / spacing));
            for (int i = Mathf.Max(0, ray - 1); i <= Mathf.Min(n - 1, ray + 1); i++)
            {
                for (int s = low; s <= high; s++)
                {
                    int j = MeshIndex(i, s);
                    Vector3 q = meshVertices[j];
                    float dx = q.x - p.x;
                    float dz = q.z - p.z;
                    if (dx * dx + dz * dz <= reachSqr)
                    {
                        height = Mathf.Max(height, rawHeights[j]);
                    }
                }
            }
            return height;
        }

        /// <summary>M5B m14: the planar distance from the eye of each mesh vertex (tests).</summary>
        public float SampleDistance(int index) => sampleDistances != null && index >= 0 && index < sampleDistances.Length ? sampleDistances[index] : 0f;

        /// <summary>M5B m14: the spacing of the samples along a ray, metres (the watcher's range over <see cref="Radial"/>).</summary>
        public float Spacing => spacing;

        /// <summary>M5B m14: the angle between two neighbour rays, radians.</summary>
        public float RayStep => rayStep;

        /// <summary>
        /// The planar reach of the ray along <paramref name="h"/> (a unit planar direction) from <paramref name="eye"/>: the
        /// farthest distance, up to <paramref name="range"/>, at which the furniture top could be seen along it. The ray aims
        /// at the furniture top above the floor at the far end; with the eye at or above that top, the first occluder it hits
        /// ends it (M1: every nearer top lies on a lower sight line). M5B m20: with the eye below the top, a cover lower than
        /// the top hides the far top but not a nearer one: the top is seen over the cover's near edge up to
        /// hit x (top - eye) / (cover top - eye), so the ray is cast again toward that top (a superset: the fan never ends
        /// short of a top the eye sees).
        /// </summary>
        public float RayReach(Vector3 eye, Vector3 h, float range, FloorMap floor)
        {
            floor = floor ?? FloorMap.Flat;
            var origin = new Vector3(eye.x, 0f, eye.z);
            float d = range;
            int passes = Mathf.Max(1, Tuning.ConeSupersetPasses);
            for (int pass = 0; pass < passes; pass++)
            {
                // The furniture top above the floor at the far end of the ray (M5: a platform there raises it).
                Vector3 far = origin + h * d;
                float top = floor.HeightAt(far.x, far.z) + TargetHeight;
                Vector3 to = new Vector3(far.x, top, far.z) - eye;
                float length = to.magnitude;
                if (length < 1e-4f
                    || !Physics.Raycast(eye, to / length, out RaycastHit hit, length, Layers.OccluderMask, QueryTriggerInteraction.Ignore))
                {
                    return d;
                }
                float atHit = YawMath.Planar(hit.point - eye).magnitude;
                bool lookingUp = eye.y < top; // MUTATION:FAN_SUPERSET
                float cover = hit.collider != null ? hit.collider.bounds.max.y : float.MaxValue;
                if (!lookingUp || cover >= top - 1e-4f || cover <= eye.y + 1e-4f)
                {
                    return atHit;
                }
                float clear = atHit * (top - eye.y) / (cover - eye.y);
                if (clear >= d - 1e-3f)
                {
                    // A hit the sight line should clear (not met at a cover's near edge): keep the longer reach.
                    return d;
                }
                // Aimed a hair nearer than the exact clearance, so the next cast passes over the cover's edge and finds
                // what lies beyond it.
                d = clear - ClearMargin;
            }
            return d;
        }

        /// <summary>
        /// CONECLIP (docs/next/progress/CONECLIP.md): <see cref="RayReach"/> casts one sight line, toward the furniture top
        /// at the far end of the ray. With the eye above the top (a human, standing or seated) a cover lower than the eye but
        /// higher than the top can let that far line pass over it (it then ends on a wall), while every nearer top lies on a
        /// steeper line that the cover stops: the fan was drawn over a spot the vision test never sees (the salon buffet of
        /// level4, seen from the sofa). This finds those shadows along the ray, on a flat floor, for covers standing on it:
        /// one cast at the top's height finds every cover higher than the top (its near face), one cast back finds its far
        /// face, and a top at planar distance x behind a cover of height c is hidden while
        /// x &lt; far x (eye - top) / (eye - c) (always when c reaches the eye), less <see cref="TargetRadius"/>. A shadow that
        /// runs to the end of the ray cuts the ray at the cover's near face (the returned reach); up to
        /// <see cref="MaxGaps"/> shadows in the middle are kept for the fill (<see cref="GapCount"/>). An eye at or below the
        /// top keeps <paramref name="reach"/> (M5B m20 already handles it). The fan stays a superset of what is seen.
        /// </summary>
        public float ShadowReach(Vector3 eye, Vector3 h, float reach, float floorY, int ray)
        {
            gapCount[ray] = 0;
            float e = eye.y - floorY;
            float t = TargetHeight;
            if (e <= t + 1e-3f || reach <= 1e-3f)
            {
                return reach;
            }
            var origin = new Vector3(eye.x, floorY + t, eye.z);
            int hits = Physics.RaycastNonAlloc(origin, h, ShadowHits, reach, Layers.OccluderMask, QueryTriggerInteraction.Ignore);
            if (hits == 0)
            {
                return reach;
            }
            Vector3 back = origin + h * reach;
            int backs = Physics.RaycastNonAlloc(back, -h, BackHits, reach, Layers.OccluderMask, QueryTriggerInteraction.Ignore);
            int spans = 0;
            for (int j = 0; j < hits && spans < SpanStart.Length; j++)
            {
                Collider c = ShadowHits[j].collider;
                if (c == null)
                {
                    continue;
                }
                Bounds b = c.bounds;
                float cover = b.max.y - floorY;
                if (b.min.y > floorY + CoverFloorGap || cover <= t)
                {
                    continue;
                }
                float near = ShadowHits[j].distance;
                // The far face: where the cast back meets the same collider (none: it runs past the end of the ray).
                float far = reach;
                for (int k = 0; k < backs; k++)
                {
                    if (BackHits[k].collider == c)
                    {
                        far = Mathf.Min(far, reach - BackHits[k].distance);
                    }
                }
                float end = cover >= e - 1e-4f ? float.MaxValue : far * (e - t) / (e - cover) - TargetRadius;
                if (end <= near)
                {
                    continue;
                }
                // The claim checked on two true sight lines (the vision test's own raycast), halfway into the shadow behind
                // the cover and at its end: a collider that is no upright box (its bounds overstate its height) or a grazing
                // hit casts no shadow on the fan.
                float from = Mathf.Max(near, far);
                float to = Mathf.Min(end, reach) - 0.02f;
                if (to > from && (!TopHidden(eye, h, (from + to) * 0.5f, floorY + t) || !TopHidden(eye, h, to, floorY + t)))
                {
                    continue;
                }
                // Insert sorted by start.
                int at = spans;
                while (at > 0 && SpanStart[at - 1] > near)
                {
                    SpanStart[at] = SpanStart[at - 1];
                    SpanEnd[at] = SpanEnd[at - 1];
                    at--;
                }
                SpanStart[at] = near;
                SpanEnd[at] = Mathf.Min(end, reach);
                spans++;
            }
            // Merge the overlapping shadows.
            int merged = 0;
            for (int j = 0; j < spans; j++)
            {
                if (merged > 0 && SpanStart[j] <= SpanEnd[merged - 1])
                {
                    SpanEnd[merged - 1] = Mathf.Max(SpanEnd[merged - 1], SpanEnd[j]);
                    continue;
                }
                SpanStart[merged] = SpanStart[j];
                SpanEnd[merged] = SpanEnd[j];
                merged++;
            }
            // A shadow that runs to the end of the ray cuts it at its start.
            while (merged > 0 && SpanEnd[merged - 1] >= reach - 1e-3f)
            {
                reach = Mathf.Min(reach, SpanStart[merged - 1]);
                merged--;
            }
            // The others are cut out of the fill; extra ones are dropped (the fan then still covers them: a superset).
            int keep = Mathf.Min(merged, MaxGaps);
            for (int j = 0; j < keep; j++)
            {
                gapStart[ray * MaxGaps + j] = SpanStart[j];
                gapEnd[ray * MaxGaps + j] = SpanEnd[j];
            }
            gapCount[ray] = keep;
            return Mathf.Max(0f, reach);
        }

        /// <summary>CONECLIP: the furniture top at planar distance <paramref name="d"/> along <paramref name="h"/> is hidden from the eye (Vision.Occluded).</summary>
        private static bool TopHidden(Vector3 eye, Vector3 h, float d, float topY)
        {
            Vector3 p = new Vector3(eye.x, 0f, eye.z) + h * d;
            return Vision.Occluded(eye, new Vector3(p.x, topY, p.z));
        }

        /// <summary>CONECLIP: the shadows in the middle of ray <paramref name="ray"/> on the last rebuild (tests, the look tool).</summary>
        public int GapCount(int ray) => gapCount != null && ray >= 0 && ray < gapCount.Length ? gapCount[ray] : 0;

        /// <summary>CONECLIP: the reach of ray <paramref name="ray"/> on the last rebuild, shadows cut (tests, the look tool).</summary>
        public float ReachOf(int ray) => rayReach != null && ray >= 0 && ray < rayReach.Length ? rayReach[ray] : 0f;

        /// <summary>CONECLIP: planar distance <paramref name="d"/> of ray <paramref name="ray"/> lies in one of its middle shadows.</summary>
        private bool InGap(int ray, float d)
        {
            if (d < 0f || d > rayReach[ray])
            {
                return false;
            }
            for (int j = 0; j < gapCount[ray]; j++)
            {
                if (d >= gapStart[ray * MaxGaps + j] && d <= gapEnd[ray * MaxGaps + j])
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// CONECLIP: a sample is cut out of the fill only when its whole neighbourhood is in shadow (one spacing on either
        /// side along its ray, and the same distance on the rays beside it), so the fade the mesh interpolates toward a cut
        /// sample stays inside the shadow and never dims a spot that is seen.
        /// </summary>
        private bool HiddenAround(int ray, float d)
        {
            int n = Tuning.ConeRayCount;
            for (int i = Mathf.Max(0, ray - 1); i <= Mathf.Min(n - 1, ray + 1); i++)
            {
                if (!InGap(i, d) || (i == ray && (!InGap(i, d - spacing) || !InGap(i, d + spacing))))
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>
        /// The chevron stands in front of the face and faces the camera, its tip along the gaze as the camera sees
        /// it: right or left when the inhabitant looks sideways, up when it looks away, down when it looks at the
        /// camera. Laid flat it would shrink to a line under the low orbit pitches.
        /// </summary>
        private void PlaceFacing(Vector3 eye, Vector3 gaze)
        {
            Vector3 at = eye + gaze * FacingAhead - Vector3.up * FacingDrop;
            Camera view = Camera.main;
            if (view == null)
            {
                Facing.SetPositionAndRotation(at, Quaternion.Euler(90f, YawMath.YawOf(gaze), 0f));
                return;
            }
            Vector3 away = at - view.transform.position;
            Vector3 tip = Vector3.ProjectOnPlane(gaze, away.normalized);
            if (away.sqrMagnitude < 1e-6f || tip.sqrMagnitude < 1e-6f)
            {
                tip = view.transform.up;
            }
            // A UI canvas shows its -z side: +z points away from the camera, +y (the chevron's tip) along the gaze.
            Facing.SetPositionAndRotation(at, Quaternion.LookRotation(away, tip));
        }

        private void OnDestroy()
        {
            if (mesh != null)
            {
                if (Application.isPlaying)
                {
                    Destroy(mesh);
                }
                else
                {
                    DestroyImmediate(mesh);
                }
            }
        }
    }
}
