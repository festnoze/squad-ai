using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// The air of a level: a sparse field of drifting dust motes
    /// (PRD_VISUAL 4.8 V-VFX-08), requested by the owner on 2026-09-07 alongside
    /// the height fog.
    ///
    /// The problem it solves is stated in PRD_VISUAL 1.1: "Nothing moves except
    /// the hover bob of pickups and the ring spin." A world that holds perfectly
    /// still while the player does reads as paused, and the acceptance criterion
    /// for the item is exactly that: "the world does not look paused when the
    /// player stands still."
    ///
    /// Everything here is DECOR and is built to be invisible to the game:
    ///   - it joins no group, so nothing in Groups can find it;
    ///   - it carries no collider, so no raycast, no interaction ray and no
    ///     photo frustum can touch it;
    ///   - it hangs under the level root, so Main's teardown takes it with the
    ///     level;
    ///   - it is culled from the picture studio camera, because a polaroid is a
    ///     promise about geometry and must not contain weather.
    ///
    /// And it is DETERMINISTIC. Particle systems are seeded rather than left to
    /// UnityEngine.Random, because PlayMode Stage11Reload rebuilds a level and
    /// Stage12Rewind undoes one, and neither may come back looking different.
    /// </summary>
    public static class Atmosphere
    {
        /// <summary>
        /// PRD_VISUAL V-VFX-08: "30 to 50 particles over the playable area,
        /// 2 percent alpha, 12 s life".
        /// </summary>
        private const int MoteCount = 44;
        private const float MoteLife = 12f;
        private const float MoteAlpha = 0.02f;

        /// <summary>
        /// Motes are drawn as small billboards. 3 cm reads as a speck at arm's
        /// length and vanishes at ten metres, which is what dust does; anything
        /// larger reads as snow, and this game already learned that lesson once
        /// on the ground texture.
        /// </summary>
        private const float MoteSize = 0.03f;

        /// <summary>
        /// Barely a drift. Fast enough to notice over a few seconds of standing
        /// still, slow enough that nothing appears to be blowing.
        /// </summary>
        private const float MoteDrift = 0.055f;

        /// <summary>
        /// The volume is inflated past the playable bounds so motes are already
        /// present at the edges rather than appearing out of nothing when the
        /// player walks outward.
        /// </summary>
        private const float VolumePadding = 3f;

        /// <summary>
        /// Ceiling on the emission volume. A level whose bounds include a decor
        /// island forty metres out would otherwise spread forty-four motes over
        /// a volume where none of them is ever within sight.
        /// </summary>
        private const float MaxExtent = 26f;

        private static Material _moteMaterial;

        /// <summary>
        /// Hangs the level's air under <paramref name="levelRoot"/>. Called once
        /// per level by <see cref="LevelBuilder"/>, after everything else is
        /// built, with the bounds of what was built.
        ///
        /// Silent and harmless when there is no rasterizer: a headless run has
        /// no use for particles and the test suites must not pay for them.
        /// </summary>
        public static void Install(Transform levelRoot, Bounds playable)
        {
            if (levelRoot == null)
            {
                return;
            }
            if (SystemInfo.graphicsDeviceType == UnityEngine.Rendering.GraphicsDeviceType.Null)
            {
                return;
            }

            Vector3 extent = playable.size + Vector3.one * (VolumePadding * 2f);
            extent = new Vector3(
                Mathf.Clamp(extent.x, 6f, MaxExtent),
                Mathf.Clamp(extent.y, 4f, MaxExtent * 0.6f),
                Mathf.Clamp(extent.z, 6f, MaxExtent));

            GameObject go = new GameObject("Dust");
            // Set before the component exists, as everywhere else in this
            // project: a system that registered on the wrong layer would be
            // culled by the wrong cameras.
            go.layer = Layers.World;
            go.transform.SetParent(levelRoot, false);
            go.transform.localPosition = playable.center + Vector3.up * (extent.y * 0.15f);

            ParticleSystem ps = go.AddComponent<ParticleSystem>();
            // Stopped while it is configured. A ParticleSystem starts playing
            // the moment it is added, and a system that emits during setup
            // spits its first burst from an unconfigured shape at the origin.
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);

            // EVERY MODULE HERE IS A STRUCT AND MUST BE WRITTEN BACK.
            // ps.main.startLifetime = x does not compile, and the pattern that
            // does compile - taking a local copy and setting a field on it -
            // silently does nothing unless the property is assigned through.
            // Unity's module properties return a view whose SETTERS write to the
            // system, so assigning to a local variable's field works only
            // because that variable IS the view. Written out longhand here so
            // the next reader is not tempted to "simplify" it.
            ParticleSystem.MainModule main = ps.main;
            main.duration = MoteLife;
            main.loop = true;
            main.startLifetime = MoteLife;
            main.startSpeed = MoteDrift;
            main.startSize = MoteSize;
            main.maxParticles = MoteCount;
            main.simulationSpace = ParticleSystemSimulationSpace.Local;
            main.gravityModifier = 0f;
            main.playOnAwake = false;
            // The dust is atmosphere, not gameplay: it keeps drifting while the
            // game is paused in a menu, exactly as the HUD keeps animating.
            main.useUnscaledTime = true;
            // FULL alpha here, and the 2 percent lives on the MATERIAL instead
            // (see MoteMaterial). Start colour reaches the shader as the vertex
            // COLOR stream, and URP's plain Unlit - the fallback taken in a
            // built player, where the particle shader can be stripped - has no
            // COLOR input at all: Shaders/UnlitForwardPass.hlsl declares only
            // POSITION, TEXCOORD0 and (under DEBUG_DISPLAY) NORMAL/TANGENT. So
            // a start colour of 2 percent was silently DISCARDED in the player
            // and the motes added at near full white through SrcAlpha/One,
            // which is a field of bright specks instead of haze. Both shaders
            // multiply _BaseColor.a into the alpha, so putting the 2 percent
            // there makes the haze read identically on either path.
            main.startColor = new Color(1f, 1f, 1f, 1f);

            ParticleSystem.EmissionModule emission = ps.emission;
            emission.enabled = true;
            // Spread evenly over a lifetime so the field fills once and then
            // holds steady, rather than pulsing.
            emission.rateOverTime = MoteCount / MoteLife;

            ParticleSystem.ShapeModule shape = ps.shape;
            shape.enabled = true;
            shape.shapeType = ParticleSystemShapeType.Box;
            shape.scale = extent;

            // A slow wander, so motes do not all travel the same direction like
            // a snowfall. Cheap: one curve, no noise texture.
            ParticleSystem.NoiseModule noise = ps.noise;
            noise.enabled = true;
            noise.strength = 0.09f;
            noise.frequency = 0.16f;
            noise.scrollSpeed = 0.05f;
            noise.damping = true;

            // Fade in and out rather than popping. Motes at 2 percent alpha are
            // faint enough that a pop is subtle, but a field of forty of them
            // popping is a visible shimmer.
            //
            // Like the start colour, this gradient travels as vertex COLOR and
            // is therefore ignored by the plain-Unlit fallback path. Nothing to
            // do about that from here: on the fallback the motes hold a steady
            // 2 percent instead of breathing, which is a lesser fault than the
            // brightness bug above and only ever shows if the particle shader
            // really is missing from the build.
            ParticleSystem.ColorOverLifetimeModule fade = ps.colorOverLifetime;
            fade.enabled = true;
            var gradient = new Gradient();
            gradient.SetKeys(
                new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                new[]
                {
                    new GradientAlphaKey(0f, 0f),
                    new GradientAlphaKey(1f, 0.25f),
                    new GradientAlphaKey(1f, 0.75f),
                    new GradientAlphaKey(0f, 1f),
                });
            fade.color = new ParticleSystem.MinMaxGradient(gradient);

            ParticleSystemRenderer renderer = go.GetComponent<ParticleSystemRenderer>();
            renderer.renderMode = ParticleSystemRenderMode.Billboard;
            renderer.sharedMaterial = MoteMaterial();
            renderer.alignment = ParticleSystemRenderSpace.View;
            // Dust does not cast or receive shadows, and asking it to would put
            // forty translucent billboards through the shadow pass for nothing.
            renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            renderer.sortingFudge = 0f;

            // Deterministic, so a reload and a rewind reproduce the same air.
            ps.randomSeed = 20260907;
            ps.useAutoRandomSeed = false;

            // Prewarmed, or the player spends the first twelve seconds of every
            // level in a room whose dust is still arriving.
            ps.Simulate(MoteLife, true, true);
            ps.Play(true);
        }

        /// <summary>
        /// The mote material, generated and shared. Unlit and additive: a dust
        /// speck is a scattering of light, it does not want to be shaded, and an
        /// unlit particle cannot be dragged around by the level's own lighting.
        ///
        /// Generated rather than loaded, because PRD_VISUAL 3.2 as amended
        /// (Appendix C.11) allows the CC0 texture sets and the one font and
        /// nothing else: a dust sprite is drawn here, in code.
        /// </summary>
        /// <summary>
        /// A soft round speck, 32 px square, generated once and shared.
        ///
        /// Alpha only matters: the material scales it down to MoteAlpha and the
        /// particle system fades it, so all this has to supply is full-range
        /// falloff from opaque
        /// at the centre to nothing at the rim. Squared falloff rather than
        /// linear, because a linear ramp still shows a visible disc edge at the
        /// 2 percent alpha these motes are drawn at.
        ///
        /// 32 px is more than enough for something that covers three or four
        /// pixels on screen, and mipmaps are on so a mote seen at distance
        /// resolves to its average rather than shimmering.
        /// </summary>
        private static Texture2D MoteSprite()
        {
            const int size = 32;
            var texture = new Texture2D(size, size, TextureFormat.RGBA32, true, false);
            texture.name = "DustMoteSprite";
            texture.wrapMode = TextureWrapMode.Clamp;
            texture.filterMode = FilterMode.Bilinear;

            var pixels = new Color32[size * size];
            float centre = (size - 1) * 0.5f;
            float radius = centre;
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float dx = (x - centre) / radius;
                    float dy = (y - centre) / radius;
                    float d = Mathf.Sqrt((dx * dx) + (dy * dy));
                    float a = Mathf.Clamp01(1f - d);
                    a *= a;
                    pixels[(y * size) + x] = new Color32(255, 255, 255, (byte)Mathf.RoundToInt(a * 255f));
                }
            }
            texture.SetPixels32(pixels);
            texture.Apply(true, true);
            return texture;
        }

        private static Material MoteMaterial()
        {
            if (_moteMaterial != null)
            {
                return _moteMaterial;
            }

            Shader shader = Shader.Find("Universal Render Pipeline/Particles/Unlit");
            if (shader == null)
            {
                // The particle shader is not one of the three this project puts
                // in Always Included Shaders, so it can be stripped from a
                // player exactly as URP/Lit once was. Fall back to plain Unlit,
                // which IS always included, rather than handing the renderer a
                // null material and drawing forty magenta squares.
                //
                // This fallback IS taken in a player today: the particle
                // shader's only project reference is ParticlesUnlit.mat inside
                // UniversalRenderPipelineGlobalSettings' editor-only material
                // block, so nothing keeps it. The real repair is one line in
                // ProjectSettings/GraphicsSettings.asset m_AlwaysIncludedShaders
                // (guid 0406db5a14f94604a8c57ccfbc9f3b46), which this file does
                // not own; everything here is written to look the same either
                // way in the meantime.
                shader = Shader.Find("Universal Render Pipeline/Unlit");
            }
            if (shader == null)
            {
                Debug.LogWarning("[Atmosphere] No unlit shader for the dust; the level will have still air.");
                return null;
            }

            _moteMaterial = new Material(shader);
            _moteMaterial.name = "DustMote";
            // THE 2 PERCENT LIVES HERE, not in the start colour, because this
            // is the one place BOTH shader paths agree on. URP's particle unlit
            // takes params.baseColor = _BaseColor and multiplies it into the
            // sampled albedo (Shaders/Particles/ParticlesUnlitInput.hlsl
            // SampleAlbedo, then MixParticleColor's default multiply against
            // the vertex colour), and plain Unlit does the same one line at a
            // time (Shaders/UnlitForwardPass.hlsl: alpha = texColor.a *
            // _BaseColor.a). Whichever shader survives the build, the mote's
            // alpha ends up as sprite falloff times MoteAlpha.
            //
            // The alpha is NOT baked into the sprite instead: 0.02 * 255 is
            // 5.1, so an RGBA32 disc scaled by MoteAlpha would quantise to six
            // steps and show exactly the banded rim that MoteSprite's squared
            // falloff exists to avoid.
            _moteMaterial.SetColor("_BaseColor", new Color(1f, 1f, 1f, MoteAlpha));
            // A PARTICLE WITH NO TEXTURE IS A SQUARE, and it looked like one:
            // the first build put small hard white QUADS in the air instead of
            // specks of dust, which reads as a rendering fault rather than as
            // atmosphere. A billboard needs something to shape its alpha, so
            // the sprite is generated here (PRD_VISUAL 3.2 as amended allows the
            // CC0 sets and the font, and nothing else, so a dust sprite is drawn
            // in code like every other glyph in this project).
            Texture2D sprite = MoteSprite();
            _moteMaterial.SetTexture("_BaseMap", sprite);
            // URP's particle shaders read _BaseMap; the unlit fallback reads the
            // same name, so one assignment covers both paths.
            if (_moteMaterial.HasProperty("_MainTex"))
            {
                _moteMaterial.SetTexture("_MainTex", sprite);
            }
            // THE BLEND STATE HAS TO BE SET AS _SrcBlend AND _DstBlend, and
            // this is the second half of the white-square bug. Setting _Surface
            // and _Blend alone looks like it configures transparency and does
            // not: those two are what the material INSPECTOR reads, while the
            // shader's actual blend comes from the _SrcBlend / _DstBlend
            // properties and the surface-type keyword. With them left at their
            // opaque defaults the mote rendered OPAQUE, so the soft alpha of the
            // generated sprite was discarded and every speck was a hard white
            // quad, which is what the level 4 frame showed.
            //
            // SrcAlpha / One is additive-through-alpha: a mote brightens what it
            // drifts in front of, in proportion to the sprite's falloff, and can
            // never darken it. That is what dust catching the light does, and it
            // means the 2 percent alpha reads as a faint speck rather than as a
            // grey square.
            _moteMaterial.SetFloat("_Surface", 1f);           // transparent, for the inspector
            _moteMaterial.SetFloat("_Blend", 1f);             // premultiplied, for the inspector
            _moteMaterial.SetFloat("_SrcBlend", (float)UnityEngine.Rendering.BlendMode.SrcAlpha);
            _moteMaterial.SetFloat("_DstBlend", (float)UnityEngine.Rendering.BlendMode.One);
            _moteMaterial.SetFloat("_ZWrite", 0f);
            _moteMaterial.SetFloat("_AlphaClip", 0f);
            _moteMaterial.SetOverrideTag("RenderType", "Transparent");
            _moteMaterial.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent;
            _moteMaterial.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            _moteMaterial.DisableKeyword("_ALPHATEST_ON");
            return _moteMaterial;
        }
    }
}
