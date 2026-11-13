using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.UI;

namespace Meuble
{
    /// <summary>
    /// The x-ray of docs/CONTRACT_M3.md 6 (pillar 2: the player always knows where every inhabitant looks).
    /// Four URP RenderObjects features on the renderer, set up by Meuble.Editor.ProjectSetup:
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
                        Debug.LogWarning($"[XRay] Layer '{ConeLayerName}' is not declared; run Meuble > Project Setup. Cones get no x-ray.");
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
    /// M3: the cone lives on the <see cref="XRay.ConeLayerName"/> layer, so where an Occluder hides it the
    /// x-ray draws it again (<see cref="XRay"/>).
    /// M3.1: a facing chevron stands in front of the inhabitant's face and points where it looks, in the cone's
    /// color. It is world space UI on the Inhabitant layer, so the marker pass draws it over walls: a hidden
    /// inhabitant's gaze always shows. A CanvasRenderer, it adds no renderer and no material to the budgets.
    /// M4 (docs/CONTRACT_M4.md 2.3): while the player lamp is off, the fan reaches only the scaled range the vision
    /// test uses for it (<see cref="RangeFactor"/>), in a dimmer color.
    /// </summary>
    [DefaultExecutionOrder(100)]
    public sealed class VisionConeView : MonoBehaviour
    {
        public Inhabitant Owner;
        public Vision Vision;

        /// <summary>Height the rays aim at: the top sample height of the player furniture.</summary>
        public float TargetHeight = 0.87f;

        private static readonly Color Calm = new Color(1f, 0.93f, 0.55f, 0.20f);
        private static readonly Color Alarm = new Color(1f, 0.35f, 0.25f, 0.30f);
        // M4 (docs/CONTRACT_M4.md 2.3): the shorter fan of a dark lamp, dimmer and greyer. Own materials (cached by
        // color), so the x-ray override of the cone pass is untouched; they exist only while a lamp is off.
        private static readonly Color CalmDark = new Color(0.72f, 0.70f, 0.58f, 0.13f);
        private static readonly Color AlarmDark = new Color(0.85f, 0.32f, 0.26f, 0.22f);

        // The chevron: its fill in the cone's hue, nearly opaque, over a dark outline.
        private static readonly Color FacingCalm = new Color(1f, 0.86f, 0.3f, 0.95f);
        private static readonly Color FacingAlarm = new Color(1f, 0.3f, 0.2f, 0.95f);
        private const float FacingSize = 0.42f;
        // Ahead of the eyes along the gaze and a little below them, so the arrow never covers the face.
        private const float FacingAhead = 0.6f;
        private const float FacingDrop = 0.18f;

        /// <summary>M3.1: the facing chevron's transform (tests).</summary>
        public RectTransform Facing { get; private set; }

        private Image facingImage;
        private Mesh mesh;
        private MeshRenderer meshRenderer;
        private Vector3[] vertices;
        private int[] triangles;

        public void Init()
        {
            if (mesh != null)
            {
                return;
            }
            mesh = new Mesh { name = "VisionCone" };
            mesh.MarkDynamic();
            int n = Tuning.ConeRayCount;
            vertices = new Vector3[n + 1];
            triangles = new int[(n - 1) * 3];
            for (int i = 0; i < n - 1; i++)
            {
                // Clockwise seen from above: the fan faces up.
                triangles[i * 3] = 0;
                triangles[i * 3 + 1] = i + 1;
                triangles[i * 3 + 2] = i + 2;
            }
            var normals = new Vector3[n + 1];
            for (int i = 0; i < normals.Length; i++)
            {
                normals[i] = Vector3.up;
            }
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.triangles = triangles;
            gameObject.AddComponent<MeshFilter>().sharedMesh = mesh;
            meshRenderer = gameObject.AddComponent<MeshRenderer>();
            meshRenderer.sharedMaterial = PrimitiveKit.UnlitTransparent(Calm);
            meshRenderer.shadowCastingMode = ShadowCastingMode.Off;
            meshRenderer.receiveShadows = false;
            gameObject.layer = XRay.ConeLayer;
            transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            BuildFacing();
            Rebuild();
        }

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
            Rebuild();
            bool alarm = Vision != null && Vision.SeesPlayer;
            bool dark = RangeFactor < 1f;
            meshRenderer.sharedMaterial = PrimitiveKit.UnlitTransparent(dark ? (alarm ? AlarmDark : CalmDark) : (alarm ? Alarm : Calm));
            if (facingImage != null)
            {
                facingImage.color = alarm ? FacingAlarm : FacingCalm;
            }
        }

        /// <summary>
        /// M4: the range factor the vision test uses for the player furniture (a dark lamp: LampOffLight), read from
        /// <see cref="Vision"/>. The fan shows that shorter range, dimmed.
        /// </summary>
        public float RangeFactor => Vision != null ? Vision.RangeFactor : 1f;

        /// <summary>M4: the fan's reach without occluders, in meters (tests).</summary>
        public float Range => Tuning.ViewRange * RangeFactor;

        public void Rebuild()
        {
            if (mesh == null || Owner == null || Owner.Routine == null)
            {
                return;
            }
            Vector3 eye = Owner.VisualEyePosition;
            float yaw = Owner.VisualEyeYaw;
            const float floorY = 0.015f;
            vertices[0] = new Vector3(eye.x, floorY, eye.z);
            int n = Tuning.ConeRayCount;
            float range = Range;
            for (int i = 0; i < n; i++)
            {
                float a = yaw - Tuning.ViewHalfAngle + 2f * Tuning.ViewHalfAngle * i / (n - 1);
                Vector3 h = YawMath.Forward(a);
                Vector3 target = new Vector3(eye.x, TargetHeight, eye.z) + h * range;
                Vector3 d = target - eye;
                float reach = range;
                if (Physics.Raycast(eye, d.normalized, out RaycastHit hit, d.magnitude, Layers.OccluderMask, QueryTriggerInteraction.Ignore))
                {
                    reach = YawMath.Planar(hit.point - eye).magnitude;
                }
                Vector3 p = new Vector3(eye.x, floorY, eye.z) + h * reach;
                vertices[i + 1] = p;
            }
            mesh.vertices = vertices;
            mesh.RecalculateBounds();
            if (Facing != null)
            {
                PlaceFacing(eye, YawMath.Forward(yaw));
            }
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
