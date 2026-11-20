using System;
using System.Collections;
using System.Threading.Tasks;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.UI;
using Object = UnityEngine.Object;

namespace OutOfSight
{
    /// <summary>
    /// M7 title logo: the player's red chair seen at a three-quarter angle, with a short shadow cast by a high
    /// (about 11 am) sun, baked ONCE into a small texture the first time the title page shows, then drawn by a
    /// RawImage above the title (it replaces the flat chair icon, kept as the fallback if the bake fails).
    ///
    /// - Isolation: a rig (the real level 1 chair model through ModelKit, or FurnitureKit's procedural chair) on an
    ///   unnamed layer (Tuning.TitleLogoLayer) that only the two logo cameras render, placed far sideways to the sun
    ///   (Tuning.TitleLogoRigDistance): beyond the main camera's far plane and outside its shadow cascades, and with
    ///   nothing between it and the sun. It lives for two frames, then the rig, cameras and render textures are destroyed:
    ///   no per frame cost afterwards, nothing left in the scene for gameplay.
    /// - Lighting: the scene's own sun is the key light (no second directional light, which could take over as the main
    ///   light). The rig is rotated so that the sun arrives high and a little to one side (Tuning.TitleLogoSunElevation,
    ///   Tuning.TitleLogoSunHeading) in the rig's frame, so the chair's shading always matches its shadow; a small
    ///   range limited rim light sits behind it, and a warm spot from straight above lights the seat (rendered once, so
    ///   it costs nothing per frame on any tier).
    /// - The pool of light (2026-11-19, replaces the translucent floor patch that read as a halo): a soft warm disc on the
    ///   ground, lit like a spot from above, centred between the chair's foot and its shadow's tip and wide enough to hold
    ///   the whole shadow (Tuning.TitleLogoPool*). An orthographic camera maps pixels to the ground affinely, so the disc
    ///   is an exact ellipse in perspective; it is brightest under the chair, warms to amber and fades to nothing before
    ///   the texture's edges, and a faint dither keeps its gradient free of banding.
    /// - The shadow: a second camera renders the same chair through its view matrix times the projection onto the ground
    ///   along the sun, which is exactly the chair's shadow (its alpha is the mask). It darkens the pool's light, darkest
    ///   at the foot, fading and softening toward the tip. Composited on the CPU at twice the size and averaged down; this
    ///   never depends on the quality tier's shadow settings, so PC and Android get the same logo.
    /// </summary>
    public sealed class TitleLogo : MonoBehaviour
    {
        /// <summary>The image that shows the baked logo (hidden until the bake succeeds).</summary>
        public RawImage Image { get; private set; }

        /// <summary>True once the logo texture is baked and shown.</summary>
        public bool Ready { get; private set; }

        /// <summary>The brightest lit floor pixel of the pool (no chair, no shadow), in texture pixels.</summary>
        public Vector2Int PoolPixel { get; private set; }

        /// <summary>The darkest shadow pixel on the floor (outside the chair), in texture pixels.</summary>
        public Vector2Int ShadowPixel { get; private set; }

        /// <summary>The pool's least light under any part of the shadow (0 when the shadow leaves the pool, 1 at its core).</summary>
        public float ShadowInPool { get; private set; }

        private const string ChairModel = "kenney.chair";
        private static readonly Color ChairRed = new Color32(0xD7, 0x26, 0x3D, 0xFF);
        private static readonly Color PoolCore = new Color(1f, 0.9f, 0.7f);
        private static readonly Color PoolRim = new Color(0.93f, 0.55f, 0.27f);
        private static readonly Color ShadowInk = new Color(0.24f, 0.11f, 0.06f);
        private static readonly Color RimColor = new Color(1f, 0.86f, 0.66f);
        private static readonly Color SpotColor = new Color(1f, 0.88f, 0.7f);
        private const float FadeSeconds = 0.45f;
        private const float ChairCurve = 1.45f;

        private Menu menu;
        private Graphic fallback;
        private Texture2D baked;

        /// <summary>The logo under <paramref name="parent"/>; <paramref name="fallback"/> (the flat icon) shows only if the bake fails.</summary>
        public static TitleLogo Create(Transform parent, Menu menu, Graphic fallback)
        {
            var go = new GameObject("Logo", typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var image = go.AddComponent<RawImage>();
            image.raycastTarget = false;
            image.enabled = false;
            var logo = go.AddComponent<TitleLogo>();
            logo.Image = image;
            logo.menu = menu;
            logo.fallback = fallback;
            if (fallback != null)
            {
                fallback.enabled = false;
            }
            return logo;
        }

        private IEnumerator Start()
        {
            if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
            {
                Fail("no graphics device");
                yield break;
            }
            // Baked the first time the title page actually shows (never under the probe, which keeps it closed).
            while (menu != null && !menu.TitlePageShown)
            {
                yield return null;
            }
            yield return null;

            Rig rig = null;
            try
            {
                rig = Rig.Build();
            }
            catch (Exception e)
            {
                rig?.Dispose();
                Fail(e.Message);
                yield break;
            }
            // The two cameras render on request, right away (2026-11-19): an editor in batch mode never reaches the end of
            // a frame, so the old wait for it left the probes without a logo. Where the pipeline cannot take a request,
            // they render with the next frame as before.
            yield return null;
            bool rendered;
            try
            {
                rendered = rig.Render();
            }
            catch (Exception e)
            {
                rig.Dispose();
                Fail(e.Message);
                yield break;
            }
            if (!rendered)
            {
                yield return null;
                yield return new WaitForEndOfFrame();
            }
            // Read back over the next frames, then compose on a worker thread: a synchronous read and the composition
            // took a single frame of about 150 ms, a visible hitch on the title page (and on the probes' clocks).
            IEnumerator readBack = rig.ReadBack();
            while (true)
            {
                bool more;
                try
                {
                    more = readBack.MoveNext();
                }
                catch (Exception e)
                {
                    rig.Dispose();
                    Fail(e.Message);
                    yield break;
                }
                if (!more)
                {
                    break;
                }
                yield return readBack.Current;
            }
            rig.Dispose();
            Task<Color32[]> compose = Task.Run(() => rig.Compose());
            while (!compose.IsCompleted)
            {
                yield return null;
            }
            if (compose.IsFaulted || compose.IsCanceled)
            {
                Fail(compose.Exception != null ? compose.Exception.GetBaseException().Message : "composition cancelled");
                yield break;
            }
            try
            {
                baked = Rig.MakeTexture(compose.Result);
                PoolPixel = rig.PoolPixel;
                ShadowPixel = rig.ShadowPixel;
                ShadowInPool = rig.ShadowInPool;
            }
            catch (Exception e)
            {
                Fail(e.Message);
            }
            if (baked == null)
            {
                yield break;
            }
            Image.texture = baked;
            Image.color = new Color(1f, 1f, 1f, 0f);
            Image.enabled = true;
            Ready = true;
            for (float t = 0f; t < FadeSeconds; t += Time.unscaledDeltaTime)
            {
                Image.color = new Color(1f, 1f, 1f, Mathf.SmoothStep(0f, 1f, t / FadeSeconds));
                yield return null;
            }
            Image.color = Color.white;
        }

        private void Fail(string why)
        {
            Debug.LogWarning("[TitleLogo] Logo not baked, the flat icon stays: " + why);
            if (fallback != null)
            {
                fallback.enabled = true;
            }
        }

        private void OnDestroy()
        {
            if (baked != null)
            {
                Destroy(baked);
            }
        }

        /// <summary>The temporary scene: the chair, its rim light and the two cameras, with their render targets.</summary>
        private sealed class Rig : IDisposable
        {
            private GameObject root;
            private Camera chairCamera;
            private Camera shadowCamera;
            private RenderTexture chairTarget;
            private RenderTexture shadowTarget;
            private Vector3 horizontal;
            private float shadowLength;

            public Vector2Int PoolPixel { get; private set; }
            public Vector2Int ShadowPixel { get; private set; }
            public float ShadowInPool { get; private set; }

            private static int Width => Tuning.TitleLogoWidth * 2;
            private static int Height => Tuning.TitleLogoHeight * 2;

            public static Rig Build()
            {
                var rig = new Rig();
                try
                {
                    rig.Create();
                }
                catch
                {
                    rig.Dispose();
                    throw;
                }
                return rig;
            }

            private void Create()
            {
                int layer = Tuning.TitleLogoLayer;
                Light sun = Main.Instance != null ? Main.Instance.Sun : null;
                Vector3 sunForward = sun != null ? sun.transform.forward : Quaternion.Euler(44f, 32f, 0f) * Vector3.forward;

                // The sun's travel in the rig's frame: low over the ground, heading right and into the depth of the view.
                float elevation = Tuning.TitleLogoSunElevation * Mathf.Deg2Rad;
                float heading = Tuning.TitleLogoSunHeading * Mathf.Deg2Rad;
                horizontal = new Vector3(Mathf.Cos(heading), 0f, Mathf.Sin(heading));
                Vector3 local = (horizontal * Mathf.Cos(elevation) + Vector3.down * Mathf.Sin(elevation)).normalized;
                // The rotation that carries it onto the real sun, keeping the rig's up as close to the world's as it can.
                Quaternion rotation = Frame(sunForward) * Quaternion.Inverse(Frame(local));
                Vector3 side = Vector3.Cross(sunForward, Vector3.up);
                if (side.sqrMagnitude < 1e-4f)
                {
                    side = Vector3.right;
                }
                Vector3 origin = side.normalized * Tuning.TitleLogoRigDistance;

                root = new GameObject("TitleLogoRig") { layer = layer };
                root.transform.SetPositionAndRotation(origin, rotation);

                Vector3 size = BodyDef.For("chair").Size;
                shadowLength = size.y / Mathf.Tan(elevation);
                var holder = new GameObject("Chair") { layer = layer };
                holder.transform.SetParent(root.transform, false);
                holder.transform.localRotation = Quaternion.Euler(0f, Tuning.TitleLogoChairYaw, 0f);
                if (ModelKit.Instantiate(ChairModel, holder.transform, size, ModelFit.Box, new ModelPaint { Main = ChairRed, Red = ChairRed }) == null)
                {
                    FurnitureKit.Chair(holder.transform, size, ChairRed, layer);
                }
                foreach (Transform t in holder.GetComponentsInChildren<Transform>(true))
                {
                    t.gameObject.layer = layer;
                }
                foreach (Renderer r in holder.GetComponentsInChildren<Renderer>(true))
                {
                    r.shadowCastingMode = ShadowCastingMode.On;
                    r.receiveShadows = true;
                }

                // A warm rim behind the chair, its range far short of anything else.
                var rim = new GameObject("Rim") { layer = layer };
                rim.transform.SetParent(root.transform, false);
                rim.transform.localPosition = new Vector3(0.75f, 1.35f, 0.9f);
                Light light = rim.AddComponent<Light>();
                light.type = LightType.Point;
                light.color = RimColor;
                light.intensity = 1.4f;
                light.range = 2.6f;
                light.shadows = LightShadows.None;
                light.cullingMask = 1 << layer;

                // The spot the pool of light comes from: straight above the pool's centre, warm, lighting the seat and the
                // tops of the rails (no shadow of its own: the short sun shadow is the one the logo shows).
                var spot = new GameObject("Spot") { layer = layer };
                spot.transform.SetParent(root.transform, false);
                spot.transform.localPosition = horizontal * Tuning.TitleLogoPoolCentre + Vector3.up * 2.2f;
                spot.transform.localRotation = Quaternion.Euler(90f, 0f, 0f);
                Light spotLight = spot.AddComponent<Light>();
                spotLight.type = LightType.Spot;
                spotLight.color = SpotColor;
                spotLight.intensity = Tuning.TitleLogoSpotIntensity;
                spotLight.range = 4f;
                spotLight.spotAngle = 70f;
                spotLight.innerSpotAngle = 30f;
                spotLight.shadows = LightShadows.None;
                spotLight.cullingMask = 1 << layer;

                chairTarget = NewTarget("TitleLogoChair");
                shadowTarget = NewTarget("TitleLogoShadow");
                chairCamera = NewCamera("ChairCamera", chairTarget, true);
                shadowCamera = NewCamera("ShadowCamera", shadowTarget, false);
                // The shadow camera sees every point of the chair moved onto the ground along the sun.
                Vector3 up = root.transform.up;
                shadowCamera.worldToCameraMatrix = chairCamera.worldToCameraMatrix * Projection(up, origin, sunForward);
                shadowCamera.cullingMatrix = chairCamera.projectionMatrix * chairCamera.worldToCameraMatrix;
            }

            /// <summary>Renders both cameras into their targets now; false (nothing rendered, cameras left to the next
            /// frame) where the pipeline cannot take a render request.</summary>
            public bool Render()
            {
                var chairRequest = new RenderPipeline.StandardRequest { destination = chairTarget };
                var shadowRequest = new RenderPipeline.StandardRequest { destination = shadowTarget };
                if (!RenderPipeline.SupportsRenderRequest(chairCamera, chairRequest)
                    || !RenderPipeline.SupportsRenderRequest(shadowCamera, shadowRequest))
                {
                    return false;
                }
                // Rendered once here, never again with the frame.
                chairCamera.enabled = false;
                shadowCamera.enabled = false;
                RenderPipeline.SubmitRenderRequest(chairCamera, chairRequest);
                RenderPipeline.SubmitRenderRequest(shadowCamera, shadowRequest);
                return true;
            }

            private static Quaternion Frame(Vector3 forward)
            {
                Vector3 up = Vector3.up - Vector3.Dot(Vector3.up, forward) * forward;
                if (up.sqrMagnitude < 1e-4f)
                {
                    up = Vector3.forward;
                }
                return Quaternion.LookRotation(forward, up.normalized);
            }

            /// <summary>The projection onto the plane through <paramref name="point"/> of normal <paramref name="normal"/>, along <paramref name="direction"/>.</summary>
            private static Matrix4x4 Projection(Vector3 normal, Vector3 point, Vector3 direction)
            {
                float nd = Vector3.Dot(normal, direction);
                float np = Vector3.Dot(normal, point);
                Matrix4x4 m = Matrix4x4.identity;
                for (int r = 0; r < 3; r++)
                {
                    for (int c = 0; c < 3; c++)
                    {
                        m[r, c] = (r == c ? 1f : 0f) - direction[r] * normal[c] / nd;
                    }
                    m[r, 3] = direction[r] * np / nd;
                }
                return m;
            }

            private static RenderTexture NewTarget(string name)
            {
                var rt = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB)
                {
                    name = name,
                    antiAliasing = 1,
                };
                rt.Create();
                return rt;
            }

            private Camera NewCamera(string name, RenderTexture target, bool shadows)
            {
                float pitch = Tuning.TitleLogoPitch;
                float frameWidth = Tuning.TitleLogoFrameWidth;
                float frameHeight = frameWidth * Height / Width;
                Quaternion look = Quaternion.Euler(pitch, 0f, 0f);
                Vector3 right = Vector3.right;
                Vector3 up = look * Vector3.up;
                Vector3 forward = look * Vector3.forward;
                // The chair's foot (the rig origin) sits TitleLogoChairInset from the left edge, TitleLogoFootHeight up.
                Vector3 aim = right * (frameWidth * 0.5f - Tuning.TitleLogoChairInset) + up * (frameHeight * (0.5f - Tuning.TitleLogoFootHeight));

                var go = new GameObject(name) { layer = Tuning.TitleLogoLayer };
                go.transform.SetParent(root.transform, false);
                go.transform.localRotation = look;
                go.transform.localPosition = aim - forward * 8f;
                Camera cam = go.AddComponent<Camera>();
                cam.orthographic = true;
                cam.orthographicSize = frameHeight * 0.5f;
                cam.aspect = Width / (float)Height;
                cam.nearClipPlane = 0.1f;
                cam.farClipPlane = 30f;
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0f, 0f, 0f, 0f);
                cam.cullingMask = 1 << Tuning.TitleLogoLayer;
                cam.allowHDR = false;
                cam.allowMSAA = false;
                cam.useOcclusionCulling = false;
                cam.depth = -50f;
                cam.targetTexture = target;
                UniversalAdditionalCameraData data = cam.GetUniversalAdditionalCameraData();
                data.renderPostProcessing = false;
                data.antialiasing = AntialiasingMode.None;
                data.renderShadows = shadows;
                data.requiresColorOption = CameraOverrideOption.Off;
                data.requiresDepthOption = CameraOverrideOption.Off;
                return cam;
            }

            private Color32[] chairPixels;
            private Color32[] shadowPixels;
            private Vector2 g00;
            private Vector2 gx;
            private Vector2 gy;

            /// <summary>
            /// Reads both targets back without stalling the frame where the platform can (AsyncGPUReadback), over a few
            /// frames; a synchronous read otherwise, or if the request fails. Then takes the ground mapping from the camera,
            /// so the composition needs nothing from the rig afterwards (it can be disposed).
            /// </summary>
            public IEnumerator ReadBack()
            {
                if (SystemInfo.supportsAsyncGPUReadback)
                {
                    AsyncGPUReadbackRequest chairRequest = AsyncGPUReadback.Request(chairTarget, 0, TextureFormat.RGBA32);
                    AsyncGPUReadbackRequest shadowRequest = AsyncGPUReadback.Request(shadowTarget, 0, TextureFormat.RGBA32);
                    for (int i = 0; i < 30 && !(chairRequest.done && shadowRequest.done); i++)
                    {
                        yield return null;
                    }
                    chairRequest.WaitForCompletion();
                    shadowRequest.WaitForCompletion();
                    if (!chairRequest.hasError && !shadowRequest.hasError)
                    {
                        chairPixels = chairRequest.GetData<Color32>().ToArray();
                        shadowPixels = shadowRequest.GetData<Color32>().ToArray();
                    }
                }
                if (chairPixels == null || shadowPixels == null)
                {
                    chairPixels = Read(chairTarget);
                    shadowPixels = Read(shadowTarget);
                }
                // Ground coordinates of the pixel centres, affine in an orthographic view: three corners give the map.
                g00 = Ground(0f, 0f);
                gx = (Ground(1f, 0f) - g00) / Tuning.TitleLogoWidth;
                gy = (Ground(0f, 1f) - g00) / Tuning.TitleLogoHeight;
            }

            /// <summary>The logo's texture from <see cref="Compose"/>'s pixels (main thread).</summary>
            public static Texture2D MakeTexture(Color32[] pixels)
            {
                var texture = new Texture2D(Tuning.TitleLogoWidth, Tuning.TitleLogoHeight, TextureFormat.RGBA32, false, false)
                {
                    name = "TitleLogo",
                    wrapMode = TextureWrapMode.Clamp,
                    filterMode = FilterMode.Bilinear,
                };
                texture.SetPixels32(pixels);
                // Kept readable (450 KB): the title probe checks the pool and the shadow in it.
                texture.Apply(false, false);
                return texture;
            }

            /// <summary>Composes the logo (straight alpha, sRGB) at Tuning.TitleLogoWidth x Height from the read back
            /// targets. Pure arithmetic on arrays, safe off the main thread (the bake runs it on a worker so the title's
            /// frames never stall).</summary>
            public Color32[] Compose()
            {
                int w = Tuning.TitleLogoWidth;
                int h = Tuning.TitleLogoHeight;
                // Should the target drop the alpha (all opaque), tell the chair from the cleared black by its colour.
                bool alpha = chairPixels[0].a < 128;

                var chair = new Color[w * h];
                var mask = new float[w * h];
                for (int y = 0; y < h; y++)
                {
                    for (int x = 0; x < w; x++)
                    {
                        Color sum = Color.clear;
                        float shadow = 0f;
                        for (int k = 0; k < 4; k++)
                        {
                            int i = (2 * y + (k >> 1)) * Width + 2 * x + (k & 1);
                            Color32 c = chairPixels[i];
                            float a = alpha ? c.a / 255f : Mathf.Max(c.r, Mathf.Max(c.g, c.b)) > 3 ? 1f : 0f;
                            sum += new Color(c.r / 255f, c.g / 255f, c.b / 255f, a);
                            Color32 s = shadowPixels[i];
                            shadow += alpha ? s.a / 255f : Mathf.Max(s.r, Mathf.Max(s.g, s.b)) > 3 ? 1f : 0f;
                        }
                        chair[y * w + x] = sum * 0.25f;
                        mask[y * w + x] = shadow * 0.25f;
                    }
                }
                float[] soft = Blur(Blur(mask, w, h, Tuning.TitleLogoShadowBlur), w, h, Tuning.TitleLogoShadowBlur);

                var output = new Color32[w * h];
                var poolCentre = new Vector2(Tuning.TitleLogoPoolCentre, 0f);
                float radius = Tuning.TitleLogoPoolRadius;
                float brightest = -1f;
                float darkest = -1f;
                float leastLight = 1f;
                for (int y = 0; y < h; y++)
                {
                    for (int x = 0; x < w; x++)
                    {
                        int i = y * w + x;
                        Vector2 g = g00 + gx * (x + 0.5f) + gy * (y + 0.5f);
                        float along = g.x;
                        float t = Mathf.Clamp01(along / shadowLength);

                        // The pool of light: a lit plateau a little hotter at its heart, then a soft falloff to nothing at
                        // the radius, like a spot's penumbra, warming from cream to amber outward.
                        float r = (g - poolCentre).magnitude / radius;
                        // (Mathf.SmoothStep interpolates between its first two arguments, it is not GLSL's smoothstep:
                        // the edge is mapped to 0..1 first.)
                        float edge = Mathf.InverseLerp(Tuning.TitleLogoPoolCore, 1f, r);
                        float light = (1f - Mathf.SmoothStep(0f, 1f, edge)) * Mathf.Lerp(1f, 0.82f, Mathf.Min(r, 1f));
                        Color ground = Color.Lerp(PoolRim, PoolCore, Mathf.Sqrt(light));
                        // The chair's shadow darkens that light: sharp and deep at the foot, softer toward the tip.
                        float shade = Mathf.Lerp(mask[i], soft[i], Mathf.SmoothStep(0f, 1f, t))
                            * Mathf.Lerp(Tuning.TitleLogoShadowNear, Tuning.TitleLogoShadowFar, t);
                        ground = Color.Lerp(ground, ShadowInk, shade);
                        // Light over the dark title band: the pool's opacity is its light (with a faint dither so the
                        // 8 bit gradient does not band); in the shadow the floor stays, only darker.
                        float dither = light > 0f ? (Hash(x, y) - 0.5f) / 255f : 0f;
                        float groundAlpha = Mathf.Clamp01(light * Tuning.TitleLogoPoolAlpha + dither);

                        Color c = chair[i];
                        if (c.a < 0.01f)
                        {
                            if (shade < 0.02f && light > brightest)
                            {
                                brightest = light;
                                PoolPixel = new Vector2Int(x, y);
                            }
                            if (shade > darkest)
                            {
                                darkest = shade;
                                ShadowPixel = new Vector2Int(x, y);
                            }
                            if (mask[i] > 0.05f)
                            {
                                leastLight = Mathf.Min(leastLight, light);
                            }
                        }
                        if (c.a > 1e-4f)
                        {
                            // The graphic treatment: a gamma curve on the chair deepens the lacquer red and its shaded side.
                            float a = c.a;
                            c = new Color(Mathf.Pow(c.r / a, ChairCurve) * a, Mathf.Pow(c.g / a, ChairCurve) * a, Mathf.Pow(c.b / a, ChairCurve) * a, a);
                        }
                        float outAlpha = c.a + groundAlpha * (1f - c.a);
                        Color rgb = outAlpha > 1e-4f ? (new Color(c.r, c.g, c.b) + ground * (groundAlpha * (1f - c.a))) / outAlpha : Color.clear;
                        output[i] = new Color(rgb.r, rgb.g, rgb.b, outAlpha);
                    }
                }
                ShadowInPool = leastLight;
                return output;
            }

            /// <summary>A cheap per pixel hash in [0, 1), for the dither.</summary>
            private static float Hash(int x, int y)
            {
                uint n = (uint)(x * 73856093) ^ (uint)(y * 19349663);
                n = (n ^ (n >> 13)) * 1274126177u;
                return (n & 0xFFFF) / 65536f;
            }

            /// <summary>The rig ground point under a viewport point, as (along the shadow, across it) in metres.</summary>
            private Vector2 Ground(float u, float v)
            {
                Ray ray = chairCamera.ViewportPointToRay(new Vector3(u, v, 0f));
                Transform frame = root.transform;
                var plane = new Plane(frame.up, frame.position);
                plane.Raycast(ray, out float distance);
                Vector3 p = frame.InverseTransformPoint(ray.GetPoint(distance));
                return new Vector2(p.x * horizontal.x + p.z * horizontal.z, -p.x * horizontal.z + p.z * horizontal.x);
            }

            private static Color32[] Read(RenderTexture target)
            {
                RenderTexture previous = RenderTexture.active;
                var texture = new Texture2D(target.width, target.height, TextureFormat.RGBA32, false, false);
                try
                {
                    RenderTexture.active = target;
                    texture.ReadPixels(new Rect(0, 0, target.width, target.height), 0, 0, false);
                    texture.Apply(false);
                    return texture.GetPixels32();
                }
                finally
                {
                    RenderTexture.active = previous;
                    Object.Destroy(texture);
                }
            }

            /// <summary>A separable box blur of <paramref name="radius"/> pixels (two passes approach a gaussian).</summary>
            private static float[] Blur(float[] src, int w, int h, int radius)
            {
                var tmp = new float[src.Length];
                var dst = new float[src.Length];
                float norm = 1f / (2 * radius + 1);
                for (int y = 0; y < h; y++)
                {
                    float sum = 0f;
                    for (int k = -radius; k <= radius; k++)
                    {
                        sum += src[y * w + Mathf.Clamp(k, 0, w - 1)];
                    }
                    for (int x = 0; x < w; x++)
                    {
                        tmp[y * w + x] = sum * norm;
                        sum += src[y * w + Mathf.Min(x + radius + 1, w - 1)] - src[y * w + Mathf.Max(x - radius, 0)];
                    }
                }
                for (int x = 0; x < w; x++)
                {
                    float sum = 0f;
                    for (int k = -radius; k <= radius; k++)
                    {
                        sum += tmp[Mathf.Clamp(k, 0, h - 1) * w + x];
                    }
                    for (int y = 0; y < h; y++)
                    {
                        dst[y * w + x] = sum * norm;
                        sum += tmp[Mathf.Min(y + radius + 1, h - 1) * w + x] - tmp[Mathf.Max(y - radius, 0) * w + x];
                    }
                }
                return dst;
            }

            public void Dispose()
            {
                if (root != null)
                {
                    Object.Destroy(root);
                    root = null;
                }
                foreach (RenderTexture rt in new[] { chairTarget, shadowTarget })
                {
                    if (rt != null)
                    {
                        rt.Release();
                        Object.Destroy(rt);
                    }
                }
                chairTarget = null;
                shadowTarget = null;
            }
        }
    }
}
