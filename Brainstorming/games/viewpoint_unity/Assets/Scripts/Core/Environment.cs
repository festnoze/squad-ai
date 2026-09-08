using UnityEngine;
using UnityEngine.Rendering;

namespace Viewpoint
{
    /// <summary>
    /// Sky, sun, ambient, fog and tonemapping (PRD section 14.3, retuned by the
    /// visual upgrade: PRD_VISUAL items V-PIPE-02, V-SKY-01, V-SKY-04,
    /// V-LIGHT-01 and V-LIGHT-02). Called once by <see cref="Main"/> at boot; it
    /// owns no state beyond the objects it makes.
    /// </summary>
    public static class SceneEnvironment
    {
        const string SkyShader = "Viewpoint/GradientSky";

        /// <summary>
        /// V-LIGHT-01 warm key (PRD_VISUAL 4.4). Warmer and stronger than the
        /// original's (1, 0.96, 0.88) at 1.15, because the ambient below is now
        /// pulled cool on purpose: the sun carries all of the frame's warmth and
        /// the sky bounce carries all of its blue. The two are one decision and
        /// have to be retuned together, which is why they sit side by side here
        /// and in <see cref="ApplyAmbient"/> just below.
        /// </summary>
        static readonly Color SunColor = new Color(1f, 0.94f, 0.84f);
        const float SunIntensity = 1.3f;

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
        /// V-SKY-04 distance fog that shows (PRD_VISUAL 4.3). The original's
        /// 0.0012 SQUARED was a veil of a fraction of a percent at 40 m:
        /// invisible, and the reason the reference frames read as a tabletop
        /// rather than a world. The mode is now plain Exponential and the
        /// density is the PRD's 0.018.
        ///
        /// Unity's exponential fog keeps exp(-density * d) of a surface's
        /// contrast at distance d, so 0.018 keeps 53 percent at 35 m (the decor
        /// islands lose 47 percent, well past the 25 percent the item asks for)
        /// and 76 percent at 15 m (a near platform loses 24 percent, where the
        /// item asks for under 8). Both halves of that criterion cannot hold at
        /// once with distance-only fog: 8 percent at 15 m needs density 0.0056,
        /// which then costs the far islands only 18 percent. The PRD pins 0.018
        /// and names the way out in the same item: the height-aware fog of
        /// V-SKY-04's second stage, which thins the air at platform height and
        /// thickens it over the abyss. Until that exists, the far islands are
        /// the half of the criterion this number buys.
        /// </summary>
        /// <remarks>
        /// LOWERED from 0.018 once the height fog of V-SKY-04's second stage
        /// landed in Assets/Shaders/Surface.shader. The note above records why
        /// 0.018 could only ever buy half the item's acceptance criterion:
        /// distance-only fog that costs the far islands 47 percent also costs a
        /// 15 m platform 24 percent, where the item allows under 8.
        ///
        /// With depth-keyed fog now doing the work of making the drop read as
        /// depth, the distance term no longer has to carry it alone:
        ///     exp(-0.012 * 15) = 0.836, so a near platform loses 16 percent
        ///     exp(-0.012 * 35) = 0.656, so a far island loses 34 percent
        /// The far clause (at least 25) is met; the near clause (under 8) is
        /// still missed, at 16 rather than 24. Halving it again would satisfy
        /// the letter of the near clause and give up the far one, which is the
        /// clause that fixes the defect section 1.1 actually complains about
        /// ("no depth, the world is a tabletop"). So this is the honest middle,
        /// and V-SKY-04 is closer to but still not exactly on its stated
        /// numbers. Appendix C.7 has the full arithmetic.
        /// </remarks>
        const float FogDensity = 0.012f;

        /// <summary>
        /// V-LIGHT-01 cool fill (PRD_VISUAL 4.4). The three trilight terms used
        /// to be a palette colour each times one AmbientEnergy of 0.8, which is
        /// what Godot's sky contribution and energy dials gave. They now carry
        /// their own weights so the bounce falls off from zenith to nadir the
        /// way a sky does, and the single dial is gone rather than kept as a
        /// constant that no longer describes what happens.
        /// </summary>
        const float AmbientSkyScale = 0.9f;
        const float AmbientEquatorScale = 0.75f;
        const float AmbientGroundScale = 0.35f;

        /// <summary>
        /// The cool grey the ground term is pulled toward, so a shaded underside
        /// leans blue instead of leaning "the horizon, only darker".
        ///
        /// It enters the ambient at the ground weight, NOT at full strength: a
        /// straight lerp toward (0.55, 0.58, 0.66) would leave the ground term
        /// 40 percent BRIGHTER than the equator it has to sit under, and being
        /// the darkest of the three is the whole job of that term. What the pull
        /// changes is the hue, taking the ground's blue over red from 1.07 to
        /// 1.12, which is what V-LIGHT-01 accepts on (the shaded side's blue
        /// channel above its red). Raise <c>CoolFillPull</c> to cool the
        /// undersides further; the ground term stays the darkest at any value
        /// because both ends of the lerp are scaled by the same weight.
        /// </summary>
        static readonly Color CoolFill = new Color(0.55f, 0.58f, 0.66f);
        const float CoolFillPull = 0.5f;

        /// <summary>
        /// V-LIGHT-02 reflection probe from the sky (PRD_VISUAL 4.4). 128 is
        /// plenty: nothing in this game is a mirror, the sky is a smooth
        /// gradient, and the cubemap is baked once at boot rather than per
        /// frame.
        /// </summary>
        const int ReflectionResolution = 128;

        public static void Apply(Transform parent)
        {
            // The order matters twice over, and it was wrong both times.
            //
            // ApplySky hands its material to ApplySun because the sky shader
            // draws the sun disc and halo itself (V-SKY-01) and needs the
            // direction of the light that casts the shadows. The material is
            // passed along rather than read back out of RenderSettings.skybox,
            // so the values provably land on the material that is installed,
            // and rather than parked in a static field, so this class still
            // owns nothing between two boots.
            //
            // ApplyReflections runs LAST because DynamicGI.UpdateEnvironment
            // snapshots the settings as they stand at the call. Called from
            // inside ApplySky, where it used to live, it baked the ambient
            // probe and the sky reflection from a sky that had no sun in it.
            Material sky = ApplySky();
            ApplyAmbient();
            ApplyFog();
            ApplySun(parent, sky);
            ApplyReflections();
            ApplyPost();
        }

        /// <summary>
        /// Builds the gradient skybox and installs it. Returns the material so
        /// the sun can write its direction into it, or null when the shader is
        /// missing and there is no sky to feed.
        /// </summary>
        static Material ApplySky()
        {
            Shader shader = Shader.Find(SkyShader);
            if (shader == null)
            {
                // A missing skybox is not fatal, but silently rendering the
                // default grey would look like a lighting bug rather than a
                // missing asset, so say which shader is gone.
                Debug.LogError("[SceneEnvironment] Shader not found: " + SkyShader
                    + ". Is Assets/Shaders/GradientSky.shader present and compiling?");
                return null;
            }

            var sky = new Material(shader);
            sky.SetColor("_SkyTop", Palette.Get("sky_top"));
            sky.SetColor("_SkyHorizon", Palette.Get("sky_horizon"));
            sky.SetColor("_GroundHorizon", Palette.Get("sky_horizon"));
            // Below the horizon the ground fades to a 15 percent darkened
            // horizon, which is what the original's ground_bottom_color was.
            sky.SetColor("_GroundBottom", Darkened(Palette.Get("sky_horizon"), 0.15f));
            // Everything the shader gained for V-SKY-01 to V-SKY-03 beyond the
            // sun (its size, its halo, the horizon band, the clouds and their
            // scroll, the abyss darkening) is authored as a shader default and
            // deliberately NOT set here, so the sky can be retuned in the
            // shader without a compile of the game.
            //
            // The material keeps the name Unity gives a material built from a
            // shader, which is the shader's own name: the player diagnostics
            // print RenderSettings.skybox BY NAME and verify-player.ps1 greps
            // for "RenderSettings.skybox: Viewpoint/GradientSky". Naming this
            // material something friendlier would break the one check that
            // proves the sky survived shader stripping in a built player.
            RenderSettings.skybox = sky;
            return sky;
        }

        static void ApplyAmbient()
        {
            // Trilight, not Skybox: the DIFFUSE ambient is authored from the
            // palette by the three weighted terms below, while the SPECULAR
            // ambient comes from the sky cubemap baked in ApplyReflections.
            // Those are two independent settings and this pair is what the look
            // wants: a bounce the palette tests can still reason about, and a
            // real sky in the few surfaces smooth enough to show one.
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = Scaled(Palette.Get("sky_top"), AmbientSkyScale);
            RenderSettings.ambientEquatorColor = Scaled(Palette.Get("sky_horizon"), AmbientEquatorScale);
            RenderSettings.ambientGroundColor = PulledToward(
                Scaled(Palette.Get("sky_horizon"), AmbientGroundScale),
                Scaled(CoolFill, AmbientGroundScale),
                CoolFillPull);
            // Trilight reads its three colours as they are; the intensity
            // multiplier applies to the Skybox ambient mode only. Left at 1 so
            // that nothing scales the weights above a second time.
            RenderSettings.ambientIntensity = 1f;
        }

        static void ApplyFog()
        {
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Exponential;
            RenderSettings.fogColor = Palette.Get("sky_horizon");
            RenderSettings.fogDensity = FogDensity;
        }

        static void ApplySun(Transform parent, Material sky)
        {
            var go = new GameObject("Sun");
            go.transform.SetParent(parent, false);
            go.transform.rotation = Quaternion.Euler(SunEuler);

            Light sun = go.AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = SunColor;
            sun.intensity = SunIntensity;
            sun.shadows = LightShadows.Soft;
            // The picture studio has its own light and must not be lit twice.
            sun.cullingMask = ~Layers.PhotoStudioMask;

            // V-PIPE-02: shadow distance, cascade count and shadow bias are NOT
            // set here, and the lines that used to set them never did anything.
            // Under URP, QualitySettings.shadowDistance,
            // QualitySettings.shadowCascades and Light.shadowNormalBias are all
            // ignored: the pipeline reads its own asset and nothing else. So
            // this file claimed a 120 m distance and a 1.5 normal bias for the
            // whole life of the port while the renderer quietly used the
            // asset's 50 m and 0.5, and the diagonal shadow acne in the
            // reference frames WAS that gap. The real keys are in
            // Assets/Settings/PC_RPAsset.asset (and its mobile twin):
            // m_ShadowDistance, m_ShadowDepthBias, m_ShadowNormalBias,
            // m_ShadowCascadeCount. Tune them there. Do not put these lines
            // back: they will lie again, and next time they will be believed.

            if (sky == null)
            {
                return;
            }

            // V-SKY-01: the sky shader draws the sun disc and its halo, so it
            // needs the world direction TOWARD the sun, which is the light's
            // forward reversed. Both values are read back off the light that
            // was just built instead of being written a second time here: a
            // disc that disagrees with the shadows is worse than no disc, and
            // under this port's single z mirror a hand-copied direction is
            // exactly the kind of sign that flips. For the record, the euler
            // above yields a forward of (-0.354, -0.707, 0.612), so the
            // direction toward the sun is (0.354, 0.707, -0.612): the design
            // vector negated and then mirrored on z, and the reason the
            // shader's own default for this property (which previews the
            // unmirrored design space) must not be taken for the truth.
            Vector3 toSun = -go.transform.forward;
            sky.SetVector("_SunDirection", new Vector4(toSun.x, toSun.y, toSun.z, 0f));
            sky.SetColor("_SunColor", sun.color);
        }

        static void ApplyReflections()
        {
            // V-LIGHT-02: the default reflection probe is the sky itself, so the
            // steel cage rails, the polaroid gloss and the camera lens catch
            // something that belongs to this world instead of a flat grey.
            RenderSettings.defaultReflectionMode = DefaultReflectionMode.Skybox;
            RenderSettings.defaultReflectionResolution = ReflectionResolution;

            // The one UpdateEnvironment of the boot, and it is here rather than
            // beside the sky because it snapshots what the settings say NOW:
            // the skybox material with its sun values in it, the reflection
            // resolution above, and the three ambient colours. Anything that
            // changes one of those after this point needs another call.
            DynamicGI.UpdateEnvironment();
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
            // Why not from code, now that this assembly CAN reach the Volume
            // types (the asmdef gained the URP runtime references for the visual
            // upgrade): URP already applies DefaultVolumeProfile globally, so a
            // Volume built here would be a second opinion fighting the asset,
            // and a URP project expects to find its grading in the profile,
            // where the whole post-processing chain of PRD_VISUAL 4.2 lives.
            //
            // WHICH profile, though, and this one cost a whole inert tier.
            // There are TWO default profiles and the second one wins:
            //
            //   1. Assets/Settings/DefaultVolumeProfile.asset, the project-wide
            //      global default, applied FIRST. PRD_VISUAL 4.2 authors every
            //      post value here and this is where they belong.
            //   2. Assets/Settings/SampleSceneProfile.asset, which BOTH
            //      PC_RPAsset and Mobile_RPAsset name in their m_VolumeProfile
            //      field, applied SECOND (URP: VolumeManager.Initialize takes a
            //      global default and a quality default, in that order).
            //
            // SampleSceneProfile is a leftover of the URP template and it
            // happened to override Bloom threshold / intensity / scatter and
            // Vignette intensity. So the bloom and vignette of V-POST-01 and
            // V-POST-02 were authored correctly in profile 1 and then silently
            // overwritten by profile 2 on every frame: no error, no warning, the
            // asset inspector showing the right numbers, and nothing glowing.
            // Those four override flags are now cleared in SampleSceneProfile so
            // profile 1 is the only place these values live. Before adding a post
            // value, CHECK BOTH FILES: a YAML asset cannot carry a comment
            // saying so, which is why the warning is here instead.
        }

        /// <summary>Godot's Color.darkened: lerp toward black by the amount.</summary>
        static Color Darkened(Color c, float amount)
        {
            return new Color(c.r * (1f - amount), c.g * (1f - amount), c.b * (1f - amount), c.a);
        }

        /// <summary>
        /// The colour scaled on rgb, alpha untouched. Unity's Color times float
        /// scales ALPHA too, which the ambient probe ignores but which leaves a
        /// half transparent swatch in the lighting window and in anything that
        /// reads the value back, so the ambient weights come through here.
        /// </summary>
        static Color Scaled(Color c, float scale)
        {
            return new Color(c.r * scale, c.g * scale, c.b * scale, c.a);
        }

        /// <summary>
        /// Lerps rgb toward a tint, alpha untouched. For the one ambient term
        /// whose hue is authored rather than taken from the sky.
        /// </summary>
        static Color PulledToward(Color c, Color tint, float amount)
        {
            float t = Mathf.Clamp01(amount);
            return new Color(
                Mathf.Lerp(c.r, tint.r, t),
                Mathf.Lerp(c.g, tint.g, t),
                Mathf.Lerp(c.b, tint.b, t),
                c.a);
        }
    }
}
