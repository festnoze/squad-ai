using UnityEngine;
using UnityEngine.Rendering;

namespace Viewpoint
{
    /// <summary>
    /// Sky, sun, ambient, fog and tonemapping (PRD section 14.3). Called once by
    /// <see cref="Main"/> at boot; it owns no state beyond the objects it makes.
    /// </summary>
    public static class SceneEnvironment
    {
        const string SkyShader = "Viewpoint/GradientSky";

        static readonly Color SunColor = new Color(1f, 0.96f, 0.88f);
        const float SunIntensity = 1.15f;
        const float ShadowDistance = 120f;
        const float ShadowNormalBias = 1.5f;

        /// <summary>
        /// Sun direction. The original's transform points the light along the
        /// design-space vector (-0.354, -0.707, -0.612): 45 degrees down, coming
        /// from the +x +z side. Mirrored on z and expressed as Unity euler
        /// angles, that is (45, -30, 0). Written as the euler rather than
        /// derived, with the design vector recorded here so the two can be
        /// checked against each other by hand.
        /// </summary>
        static readonly Vector3 SunEuler = new Vector3(45f, -30f, 0f);

        /// <summary>
        /// Godot's fog density, kept as the starting point. The two engines do
        /// not share a fog formula, so this is matched by eye on the decor
        /// islands 30 to 40 m out rather than converted.
        /// </summary>
        const float FogDensity = 0.0012f;

        /// <summary>
        /// Ambient, as the original: from the sky, at half strength (Godot sky
        /// contribution 0.5, energy 0.8). Unity has no sky-contribution dial, so
        /// the gradient is built from the palette and scaled by this instead.
        /// </summary>
        const float AmbientEnergy = 0.8f;

        public static void Apply(Transform parent)
        {
            ApplySky();
            ApplyFog();
            ApplySun(parent);
            ApplyPost();
        }

        static void ApplySky()
        {
            Shader shader = Shader.Find(SkyShader);
            if (shader == null)
            {
                // A missing skybox is not fatal, but silently rendering the
                // default grey would look like a lighting bug rather than a
                // missing asset, so say which shader is gone.
                Debug.LogError("[SceneEnvironment] Shader not found: " + SkyShader
                    + ". Is Assets/Shaders/GradientSky.shader present and compiling?");
                return;
            }

            var sky = new Material(shader);
            sky.SetColor("_SkyTop", Palette.Get("sky_top"));
            sky.SetColor("_SkyHorizon", Palette.Get("sky_horizon"));
            sky.SetColor("_GroundHorizon", Palette.Get("sky_horizon"));
            // Below the horizon the ground fades to a 15 percent darkened
            // horizon, which is what the original's ground_bottom_color was.
            sky.SetColor("_GroundBottom", Darkened(Palette.Get("sky_horizon"), 0.15f));
            RenderSettings.skybox = sky;

            RenderSettings.ambientMode = AmbientMode.Trilight;
            Color top = Palette.Get("sky_top") * AmbientEnergy;
            Color horizon = Palette.Get("sky_horizon") * AmbientEnergy;
            RenderSettings.ambientSkyColor = top;
            RenderSettings.ambientEquatorColor = horizon;
            RenderSettings.ambientGroundColor = Darkened(horizon, 0.15f);
            RenderSettings.ambientIntensity = 1f;
            DynamicGI.UpdateEnvironment();
        }

        static void ApplyFog()
        {
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.ExponentialSquared;
            RenderSettings.fogColor = Palette.Get("sky_horizon");
            RenderSettings.fogDensity = FogDensity;
        }

        static void ApplySun(Transform parent)
        {
            var go = new GameObject("Sun");
            go.transform.SetParent(parent, false);
            go.transform.rotation = Quaternion.Euler(SunEuler);

            Light sun = go.AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = SunColor;
            sun.intensity = SunIntensity;
            sun.shadows = LightShadows.Soft;
            sun.shadowNormalBias = ShadowNormalBias;
            // The picture studio has its own light and must not be lit twice.
            sun.cullingMask = ~Layers.PhotoStudioMask;

            QualitySettings.shadowDistance = ShadowDistance;
            QualitySettings.shadowCascades = 4;
        }

        static void ApplyPost()
        {
            // Tonemapping is NEUTRAL, not ACES, and it lives in the project's
            // DefaultVolumeProfile rather than here.
            //
            // Why not ACES: it crushes and desaturates bright albedos, which is
            // exactly what this palette is made of. Under ACES the cream
            // platforms go grey and the amber batteries go brown. The Godot
            // original used Filmic for the same reason.
            //
            // Why not from code: the Volume and Tonemapping types live in the
            // URP package assemblies, and reaching them would bind this
            // assembly to the render pipeline for one enum. URP already applies
            // DefaultVolumeProfile globally, so the setting belongs in the
            // asset, where a URP project expects to find it.
        }

        /// <summary>Godot's Color.darkened: lerp toward black by the amount.</summary>
        static Color Darkened(Color c, float amount)
        {
            return new Color(c.r * (1f - amount), c.g * (1f - amount), c.b * (1f - amount), c.a);
        }
    }
}
