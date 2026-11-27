// Owned by B1. Contract 12.2 item 2 and 19: the actor field camera. An orthographic camera created at runtime that renders
// ONLY layer LiquidLayers.Field (the FieldBlob / FieldStroke contributors of the actor views) into _PIO_ActorField, over
// the world rectangle R = main camera view grown by 0.6 u per side. It runs in LateUpdate after CameraRig (order 100) and
// after the field-feeding views (default order), and publishes _PIO_ActorRect = (R.xMin, R.yMin, R.width, R.height),
// _PIO_ActorTexel and _PIO_ActorScale. Every consumer samples it at uv = (worldXY - _PIO_ActorRect.xy) / _PIO_ActorRect.zw.
//
// Render target (contract 19): R16G16B16A16_SFloat when it supports blending, else R8G8B8A8_UNorm with
// _PIO_ActorScale = 0.25; linear, bilinear, clamp, no mips. It carries a 16-bit depth buffer: URP 17's Render Graph
// draws nothing into a camera target without one (B0b finding, contract_issues of docs/waveB/B0b.json). The RT is
// reallocated when its computed size changes (window resize, quality tier, render scale), reassigned to the camera and to
// the global, and the old one released.
// Wave C (infra-perf): the pixels per unit come from the RENDERED height (main camera pixel height x the active URP
// renderScale clamped to 0.1-1), so the actor RT shrinks with the tier's render height cap like the composite does.
using System;
using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace PainterIO.Runtime
{
    [DefaultExecutionOrder(200)]
    public sealed class ActorFieldCamera : MonoBehaviour
    {
        /// <summary>World margin added to each side of the main camera view (contract 12.2).</summary>
        public const float Margin = 0.6f;
        /// <summary>Depth buffer bits of the actor RT (required by URP 17 Render Graph for a camera target).</summary>
        public const int DepthBits = 16;
        /// <summary>Camera depth: renders before the main camera (depth 0).</summary>
        public const float CameraDepth = -10f;
        /// <summary>Camera z (same as the main camera; contributors lie at z = 0).</summary>
        public const float CameraZ = -50f;
        /// <summary>_PIO_ActorScale with the 8-bit fallback RT.</summary>
        public const float UnormScale = 0.25f;

        private static readonly int IdField = Shader.PropertyToID("_PIO_ActorField");
        private static readonly int IdRect = Shader.PropertyToID("_PIO_ActorRect");
        private static readonly int IdTexel = Shader.PropertyToID("_PIO_ActorTexel");
        private static readonly int IdScale = Shader.PropertyToID("_PIO_ActorScale");

        private Camera cam;
        private Camera mainCamera;
        private RenderTexture target;
        private GraphicsFormat format;
        private float actorScale = 1f;
        private Rect worldRect;
        private bool errorLogged;

        /// <summary>The actor field camera.</summary>
        public Camera Camera => cam;

        /// <summary>_PIO_ActorField (null only before Create finished).</summary>
        public RenderTexture Texture => target;

        /// <summary>The world rectangle R covered by the field (published as _PIO_ActorRect).</summary>
        public Rect WorldRect => worldRect;

        /// <summary>_PIO_ActorScale: 1 with the half-float RT, 0.25 with the 8-bit fallback.</summary>
        public float ActorScale => actorScale;

        /// <summary>Format of the actor RT.</summary>
        public GraphicsFormat Format => format;

        /// <summary>Times the RT was (re)allocated.</summary>
        public int Allocations { get; private set; }

        public static ActorFieldCamera Create(Transform parent)
        {
            var go = new GameObject("ActorFieldCamera");
            if (parent != null) go.transform.SetParent(parent, false);
            var c = go.AddComponent<Camera>();
            c.orthographic = true;
            c.depth = CameraDepth;
            c.cullingMask = 1 << LiquidLayers.Field;
            c.clearFlags = CameraClearFlags.SolidColor;
            c.backgroundColor = new Color(0f, 0f, 0f, 0f);
            c.allowHDR = false;
            c.allowMSAA = false;
            c.useOcclusionCulling = false;
            c.nearClipPlane = 0.1f;
            c.farClipPlane = 200f;
            c.orthographicSize = 10f;
            UniversalAdditionalCameraData data = c.GetUniversalAdditionalCameraData();
            if (data != null)
            {
                data.renderType = CameraRenderType.Base;
                data.renderPostProcessing = false;
                data.renderShadows = false;
                data.requiresDepthOption = CameraOverrideOption.Off;
                data.requiresColorOption = CameraOverrideOption.Off;
                data.antialiasing = AntialiasingMode.None;
                data.stopNaN = false;
                data.dithering = false;
            }
            var afc = go.AddComponent<ActorFieldCamera>();
            afc.cam = c;
            bool half = SystemInfo.IsFormatSupported(GraphicsFormat.R16G16B16A16_SFloat, GraphicsFormatUsage.Blend)
                        && SystemInfo.IsFormatSupported(GraphicsFormat.R16G16B16A16_SFloat, GraphicsFormatUsage.Render);
            afc.format = half ? GraphicsFormat.R16G16B16A16_SFloat : GraphicsFormat.R8G8B8A8_UNorm;
            afc.actorScale = half ? 1f : UnormScale;
            afc.UpdateField();
            return afc;
        }

        private void LateUpdate()
        {
            try
            {
                UpdateField();
            }
            catch (Exception e)
            {
                if (errorLogged) return;
                errorLogged = true;
                Debug.LogError("[PainterIO] ActorFieldCamera update failed: " + e);
            }
        }

        private void OnDestroy()
        {
            if (cam != null) cam.targetTexture = null;
            if (target != null)
            {
                target.Release();
                LiquidRenderer.SafeDestroy(target);
                target = null;
            }
        }

        /// <summary>Follows the main camera view, reallocates the RT when its size changes and publishes the globals.</summary>
        public void UpdateField()
        {
            if (cam == null) return;
            Camera main = MainCamera();
            Vector2 center;
            float halfH, aspect, pixelHeight;
            if (main != null)
            {
                Vector3 p = main.transform.position;
                center = new Vector2(p.x, p.y);
                halfH = Mathf.Max(0.01f, main.orthographicSize);
                aspect = main.aspect > 0f ? main.aspect : 9f / 16f;
                pixelHeight = Mathf.Max(1f, main.pixelHeight);
            }
            else
            {
                // No main camera yet: a portrait view of 18 u at the origin, so the RT exists from the first frame.
                center = Vector2.zero;
                aspect = Screen.height > 0 ? Mathf.Max(0.1f, Screen.width / (float)Screen.height) : 9f / 16f;
                halfH = aspect <= 1f ? 9f / aspect : 10f;
                pixelHeight = Mathf.Max(1f, Screen.height);
            }
            pixelHeight = RenderedHeight(pixelHeight, CurrentRenderScale());
            float halfW = halfH * aspect;
            worldRect = new Rect(center.x - halfW - Margin, center.y - halfH - Margin, 2f * (halfW + Margin), 2f * (halfH + Margin));
            float ppu = pixelHeight / (2f * halfH);
            float scale = QualityTier.ActorFieldScale;
            int maxSide = Mathf.Max(16, Mathf.Min(SystemInfo.maxTextureSize, 4096));
            // Gate B: the size is rounded UP to a multiple of RtQuantum px. The 0.6 u margin is in world units while ppu
            // changes during the chase zoom, so the exact size drifted by a few px on most zoom frames and the RT was
            // reallocated every frame of each zoom ease. Consumers map with _PIO_ActorRect and _PIO_ActorTexel, so a
            // slightly denser RT changes nothing visible.
            int w = QuantizeSide(worldRect.width * ppu * scale, maxSide);
            int h = QuantizeSide(worldRect.height * ppu * scale, maxSide);
            if (target == null || target.width != w || target.height != h || !target.IsCreated()) Reallocate(w, h);

            transform.SetPositionAndRotation(new Vector3(worldRect.center.x, worldRect.center.y, CameraZ), Quaternion.identity);
            cam.orthographicSize = worldRect.height * 0.5f;
            cam.aspect = worldRect.width / worldRect.height;
            Publish();
        }

        /// <summary>RT side quantum in pixels (see UpdateField).</summary>
        public const int RtQuantum = 32;

        /// <summary>Rendered height in pixels: the camera's pixel height x the render scale clamped to [0.1, 1], at least 1.</summary>
        public static float RenderedHeight(float pixelHeight, float renderScale)
        {
            float s = float.IsNaN(renderScale) ? 1f : Mathf.Clamp(renderScale, 0.1f, 1f);
            return Mathf.Max(1f, pixelHeight * s);
        }

        /// <summary>The active URP asset's renderScale (1 when no URP asset is active).</summary>
        public static float CurrentRenderScale()
        {
            var urp = GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
            return urp != null ? urp.renderScale : 1f;
        }

        /// <summary>Exact side in pixels rounded up to a multiple of RtQuantum, clamped to [16, maxSide].</summary>
        public static int QuantizeSide(float pixels, int maxSide)
        {
            int n = Mathf.CeilToInt(Mathf.Max(1f, pixels) / RtQuantum - 1e-4f) * RtQuantum;
            return Mathf.Clamp(n, 16, maxSide);
        }

        private Camera MainCamera()
        {
            if (mainCamera != null && mainCamera.isActiveAndEnabled) return mainCamera;
            mainCamera = Camera.main;
            if (mainCamera == cam) mainCamera = null;
            return mainCamera;
        }

        private void Reallocate(int w, int h)
        {
            RenderTexture old = target;
            var desc = new RenderTextureDescriptor(w, h, format, DepthBits)
            {
                useMipMap = false,
                autoGenerateMips = false,
                msaaSamples = 1,
                sRGB = false,
            };
            target = new RenderTexture(desc)
            {
                name = "PIO ActorField",
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                anisoLevel = 0,
                hideFlags = HideFlags.HideAndDontSave,
            };
            target.Create();
            cam.targetTexture = target;
            Allocations++;
            if (old != null)
            {
                old.Release();
                LiquidRenderer.SafeDestroy(old);
            }
        }

        private void Publish()
        {
            if (target == null) return;
            Shader.SetGlobalTexture(IdField, target);
            Shader.SetGlobalVector(IdRect, new Vector4(worldRect.xMin, worldRect.yMin, worldRect.width, worldRect.height));
            Shader.SetGlobalVector(IdTexel, new Vector4(1f / target.width, 1f / target.height, target.width, target.height));
            Shader.SetGlobalFloat(IdScale, actorScale);
        }
    }
}
