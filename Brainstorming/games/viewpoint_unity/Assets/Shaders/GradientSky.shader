// Skybox of VIEWPOINT (PRD 14.3), upgraded by PRD_VISUAL 4.3 into a sky with
// a sun, two cloud decks and an abyss below: items V-SKY-01, V-SKY-02 and
// V-SKY-03.
//
// The base is still the four color vertical gradient, the port of the Godot
// ProceduralSkyMaterial the original used, and every layer added here sits ON
// TOP of it: sky_top at the zenith fading to sky_horizon at the horizon;
// below the horizon, sky_horizon fading to a 15 percent darkened horizon at
// the nadir.
//
// The blend curves reproduce Godot's own formula so the two builds can be
// compared side by side: the mix factor is 1 - pow(1 - c, 1 / curve), where c
// runs 0 at the horizon to 1 at the pole. _SkyCurve keeps Godot's 0.15.
// _GroundCurve no longer keeps Godot's 0.02, on purpose: see the note on the
// property itself.
//
// What is layered over the gradient, in this order:
//   1. the cloud decks (V-SKY-02, V-SKY-03), one above the horizon and a
//      sparser darker one below, so that the haze band of step 2 washes a
//      cloud out exactly as much as it washes out the sky behind it;
//   2. the horizon haze band (V-SKY-01, V-SKY-03), computed from abs(y) so
//      BOTH halves converge to the same color at y = 0. That symmetry is what
//      removes the horizon line V-SKY-03 is about;
//   3. the sun halo, then the sun disc (V-SKY-01), which are in front of the
//      haze rather than mixed into it.
//
// Two brightness rules run through the whole file, and every term added here
// is bounded so it respects them (PRD_VISUAL 7 and V-POST-01):
//   - the sun disc is ABOVE the 1.05 bloom threshold, because it is the one
//     thing in this shader that must bloom;
//   - everything else stays BELOW it, halo and haze band included, and below
//     the 0.98 the emissive isolation check of PRD_VISUAL 6.3 thresholds at.
//     A sky that blooms is a sky that stops the glow from meaning "this
//     glows", which is the whole job of the emissives in this game.
// Both rules are about what this shader returns at _Exposure = 1, which is
// the value the game ships: _Exposure is a preview knob and raising it drags
// the sky up through the bloom threshold with it.
Shader "Viewpoint/GradientSky"
{
    Properties
    {
        // Defaults are the palette values (sky_top, sky_horizon, sky_horizon,
        // sky_horizon darkened by 15 percent) so the shader previews correctly
        // before Main assigns them from Palette.
        _SkyTop ("Sky top", Color) = (0.53, 0.72, 0.87, 1)
        _SkyHorizon ("Sky horizon", Color) = (0.87, 0.91, 0.93, 1)
        _GroundHorizon ("Ground horizon", Color) = (0.87, 0.91, 0.93, 1)
        _GroundBottom ("Ground bottom", Color) = (0.7395, 0.7735, 0.7905, 1)
        _SkyCurve ("Sky curve", Range(0.01, 1)) = 0.15

        // Godot's own value here was 0.02, which means an exponent of 50: the
        // ground half reached _GroundBottom within a couple of degrees of the
        // horizon and then never changed again, so it read as one flat pale
        // band with a hard line where it met the sky. V-SKY-03 wants the
        // opposite, a gradient the eye can read depth in, so the curve is
        // raised to 0.35 (an exponent of about 2.9, a gentle ramp across the
        // whole lower hemisphere) and the real darkening is done by
        // _AbyssDarken further down. The endpoint colors are untouched, so
        // PRD 14.3's description of the gradient still holds.
        _GroundCurve ("Ground curve", Range(0.01, 1)) = 0.35
        _Exposure ("Exposure", Range(0, 8)) = 1

        // V-SKY-01. _SunDirection is the world space UNIT direction pointing
        // TOWARD the sun, which is -light.forward: Environment.cs sets it and
        // _SunColor from the Sun light it creates, and sets nothing else in
        // this shader. The defaults are the shipped sun, so the material
        // previews with a sun in the right place. xyz is used, w is ignored.
        _SunDirection ("Sun direction", Vector) = (0.354, 0.707, 0.612, 0)
        _SunColor ("Sun color", Color) = (1, 0.94, 0.84, 1)

        // Everything from here down is authored as a default and left alone by
        // C#, so the sky can be retuned without touching a script.
        _SunSize ("Sun angular radius deg", Range(0.1, 10)) = 1.5
        _SunHalo ("Sun halo strength", Range(0, 4)) = 1.0
        _HorizonBand ("Horizon band strength", Range(0, 2)) = 0.35

        // V-SKY-02 for the two cloud knobs, V-SKY-03 for the abyss.
        _CloudDensity ("Cloud density", Range(0, 1)) = 0.35
        _CloudScroll ("Cloud scroll speed", Range(0, 0.05)) = 0.004
        _AbyssDarken ("Abyss darkening", Range(0, 1)) = 0.55
    }

    SubShader
    {
        Tags
        {
            "Queue" = "Background"
            "RenderType" = "Background"
            "PreviewType" = "Skybox"
            "RenderPipeline" = "UniversalPipeline"
        }

        Cull Off
        ZWrite Off

        Pass
        {
            Name "GradientSky"

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 3.0

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _SkyTop;
                float4 _SkyHorizon;
                float4 _GroundHorizon;
                float4 _GroundBottom;
                float _SkyCurve;
                float _GroundCurve;
                float _Exposure;
                // Same order as the Properties block above. A property that is
                // declared there and missing here is not a warning, it is a
                // broken shader under SRP batching, so the two lists are kept
                // in step by eye every time one of them grows.
                float4 _SunDirection;
                float4 _SunColor;
                float _SunSize;
                float _SunHalo;
                float _HorizonBand;
                float _CloudDensity;
                float _CloudScroll;
                float _AbyssDarken;
            CBUFFER_END

            // --- V-SKY-01, the sun ---------------------------------------

            // 3.0 times the sun color puts the disc at 3.0 in linear, well over
            // the 1.05 bloom threshold V-POST-01 sets, and above the 2.0 energy
            // of the strongest emissive in the game, so the sun is also the
            // brightest thing in any frame that contains it.
            static const float SunDiscBrightness = 3.0;

            // The disc edge is faded over a tenth of a degree. Without it the
            // disc is a hard threshold on an angle and stair-steps along its
            // rim; with it the rim costs one smoothstep and reads round.
            static const float SunEdgeDeg = 0.1;

            // PRD_VISUAL 4.3 pins the halo as a broad pow(dot, 24) glow.
            static const float SunHaloExponent = 24.0;

            // The halo is a lerp toward a color capped at this value rather
            // than an additive glow. Additive is the obvious way to write a
            // glow and it is wrong here twice over: at the strength that makes
            // the halo read it lands the sky above the bloom threshold and the
            // halo becomes a giant blob, and clamping the sum per channel
            // distorts the hue, because the sky's green is much closer to the
            // ceiling than its red and so saturates first. Lerping toward a
            // capped color keeps the halo's hue exactly the sun's and its
            // value provably under the threshold.
            static const float SunHaloCeiling = 0.93;

            // --- V-SKY-01 and V-SKY-03, the horizon haze band -------------

            // PRD_VISUAL 4.3 pins the band's mix as exp(-abs(y) * 8).
            static const float BandFalloff = 8.0;

            // PRD_VISUAL 7: "the horizon band is authored below 0.95", so that
            // bloom never leaks onto it. The palette's sky_horizon is already
            // (0.87, 0.91, 0.93), which leaves almost no headroom under that
            // ceiling in blue: the band therefore WHITENS the horizon (it
            // lifts red and green toward the ceiling) instead of brightening
            // every channel. That is what atmospheric haze does anyway, it
            // desaturates toward white, so the constraint and the look agree.
            static const float BandCeiling = 0.94;
            static const float BandLift = 1.18;

            // --- V-SKY-03, the abyss --------------------------------------

            // The abyss darkening reaches full strength this far down (y of
            // -0.9, about 64 degrees below the horizon), and starts right at
            // the horizon where it is worth nothing, so the two halves still
            // meet at exactly the same color at y = 0.
            static const float AbyssFullDepth = 0.9;

            // --- V-SKY-02, the cloud decks --------------------------------

            // Frequency of the first octave on the projected deck. At 30
            // degrees of elevation it puts about fourteen cells around the
            // sky, so one cell is roughly 26 degrees of azimuth: cumulus
            // sized rather than texture sized.
            static const float CloudScale = 1.45;

            // Second octave: 2.7 rather than 2.0 so the two octaves never line
            // their cells up, plus an offset so it is a different patch of the
            // same noise field and not a scaled copy of the first.
            static const float CloudDetailScale = 2.7;
            static const float CloudDetailOffset = 11.3;
            static const float CloudBaseWeight = 0.66;
            static const float CloudDetailWeight = 0.34;

            // The soft threshold. CloudSoftness is the width of the ramp from
            // clear sky to full cloud in noise units, and it is wide on
            // purpose: V-SKY-02's acceptance criterion is that no cloud ever
            // has a hard edge, and a narrow ramp on a two octave noise field
            // gives exactly the hard edge it forbids.
            static const float CloudSoftness = 0.30;
            static const float CloudEdgeSparse = 0.85;
            static const float CloudEdgeDense = 0.35;

            // Clouds fade out into the haze near the horizon, between these
            // two elevations. Two reasons: a real deck of cloud does exactly
            // that, and the 1 / (y + 0.05) projection compresses cells so hard
            // down there that a cloud at full strength would alias into a
            // shimmering fringe along the horizon.
            static const float CloudFadeStart = 0.04;
            static const float CloudFadeEnd = 0.26;

            // PRD_VISUAL 4.3: sky_horizon on the lit side, sky_horizon
            // darkened 10 percent on the shadow side.
            static const float CloudShadowDarken = 0.9;

            // The lower deck of V-SKY-03: 60 percent of the density, a
            // slightly darker tint, and a large offset in the noise field so
            // it is a different sky and not a mirror image of the upper deck.
            static const float LowerCloudDensity = 0.6;
            static const float LowerCloudTint = 0.82;
            static const float2 UpperCloudOffset = float2(0.0, 0.0);
            static const float2 LowerCloudOffset = float2(37.4, 11.9);

            // Scroll direction, so the deck drifts rather than sliding along
            // one axis.
            static const float2 CloudScrollAxis = float2(1.0, 0.37);

            struct Attributes
            {
                float4 positionOS : POSITION;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 directionOS : TEXCOORD0;
            };

            Varyings vert(Attributes input)
            {
                Varyings output;
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                // Unity draws the skybox mesh centered on the camera with an
                // unrotated model matrix, so a vertex's object space position IS
                // the world view direction. The built-in skyboxes use the same
                // trick to look up their cubemap.
                output.directionOS = input.positionOS.xyz;
                return output;
            }

            // Godot's blend: c is 0 at the horizon and 1 at the pole; a small
            // curve pushes the transition hard against the horizon.
            float GradientBlend(float c, float curve)
            {
                float safeCurve = max(curve, 0.0001);
                return saturate(1.0 - pow(saturate(1.0 - saturate(c)), 1.0 / safeCurve));
            }

            // Scales a color so its largest channel lands on the ceiling,
            // which caps its value without touching its hue. Used for every
            // bright term added to the sky, because a per channel clamp caps
            // the value and shifts the hue while doing it.
            float3 CapToCeiling(float3 color, float ceiling)
            {
                float peak = max(max(color.r, color.g), max(color.b, 0.0001));
                return color * min(1.0, ceiling / peak);
            }

            // Value noise hash: one pseudo random value per integer lattice
            // point. Written by hand rather than sampled from a texture,
            // because PRD_VISUAL 3.2 allows no binary asset at all. No sin()
            // in it: sin based hashes differ between GPU vendors, and a cloud
            // deck that changes shape per driver is not a cloud deck.
            float NoiseHash(float3 cell)
            {
                float3 p = frac(cell * 0.3183099 + 0.1);
                p *= 17.0;
                return frac(p.x * p.y * p.z * (p.x + p.y + p.z));
            }

            // One octave of 3D value noise in 0..1: the eight lattice corners
            // around p, interpolated with the smoothstep polynomial so the
            // field is continuous in value AND in slope. Linear interpolation
            // here would show the lattice as a grid of creases, which on a
            // cloud is exactly the hard edge V-SKY-02 forbids.
            float ValueNoise3D(float3 p)
            {
                float3 cell = floor(p);
                float3 f = frac(p);
                float3 u = f * f * (3.0 - 2.0 * f);

                float c000 = NoiseHash(cell + float3(0.0, 0.0, 0.0));
                float c100 = NoiseHash(cell + float3(1.0, 0.0, 0.0));
                float c010 = NoiseHash(cell + float3(0.0, 1.0, 0.0));
                float c110 = NoiseHash(cell + float3(1.0, 1.0, 0.0));
                float c001 = NoiseHash(cell + float3(0.0, 0.0, 1.0));
                float c101 = NoiseHash(cell + float3(1.0, 0.0, 1.0));
                float c011 = NoiseHash(cell + float3(0.0, 1.0, 1.0));
                float c111 = NoiseHash(cell + float3(1.0, 1.0, 1.0));

                float x00 = lerp(c000, c100, u.x);
                float x10 = lerp(c010, c110, u.x);
                float x01 = lerp(c001, c101, u.x);
                float x11 = lerp(c011, c111, u.x);
                return lerp(lerp(x00, x10, u.y), lerp(x01, x11, u.y), u.z);
            }

            // Coverage of one cloud deck in 0..1 for a view direction whose y
            // is the elevation ABOVE the deck's own horizon. The lower deck of
            // V-SKY-03 passes a direction mirrored on y, so it reuses this
            // projection unchanged and reads as a deck seen from above.
            //
            // Cost: two octaves, so sixteen hashes, and the shader evaluates
            // this twice per background pixel. That is the whole cloud budget
            // PRD_VISUAL allows for this file.
            float CloudCoverage(float3 direction, float density, float2 offset)
            {
                float elevation = max(direction.y, 0.0);

                // 1 / (y + 0.05) is the deck projection PRD_VISUAL 4.3 asks
                // for: dividing xz by the elevation puts the noise on a
                // horizontal slab at unit height, so cells compress toward the
                // horizon the way a real cloud deck does under perspective.
                // The 0.05 is what keeps it finite at y = 0.
                float3 p = direction * (CloudScale / (elevation + 0.05));

                // The scroll is added AFTER the projection, so a cell moves at
                // _CloudScroll noise units per second whatever elevation it is
                // seen at. _Time.y is seconds since load and is used raw: no
                // frac() on it, because wrapping the offset would make the
                // whole deck jump at the wrap. At 0.004 units per second a cell
                // crosses about a quarter of its own width in a minute, which
                // is the "perceptible over a minute, imperceptible over a
                // second" V-SKY-02 asks for.
                p.xz += offset + _Time.y * _CloudScroll * CloudScrollAxis;

                float n = CloudBaseWeight * ValueNoise3D(p)
                    + CloudDetailWeight * ValueNoise3D(p * CloudDetailScale + CloudDetailOffset);

                // Density slides the threshold instead of scaling the result:
                // scaling would fade a whole deck uniformly, sliding the
                // threshold makes the clouds themselves sparser, which is what
                // "sparse cumulus" means.
                float edge = lerp(CloudEdgeSparse, CloudEdgeDense, saturate(density));
                float coverage = smoothstep(edge, edge + CloudSoftness, n);

                return coverage * smoothstep(CloudFadeStart, CloudFadeEnd, elevation);
            }

            half4 frag(Varyings input) : SV_Target
            {
                float3 direction = normalize(input.directionOS);
                // acos of the clamped y is the angle down from the zenith: 0 at
                // the zenith, PI/2 at the horizon, PI at the nadir.
                float verticalAngle = acos(clamp(direction.y, -1.0, 1.0));

                // Environment.cs feeds -light.forward, which is already unit
                // length, but a hand typed default is not necessarily. One
                // normalize keeps the dot products honest; the max() means a
                // zero vector yields no sun rather than a NaN sky.
                float3 sunDirection = _SunDirection.xyz / max(length(_SunDirection.xyz), 0.0001);
                float sunCos = dot(direction, sunDirection);

                // --- the Godot gradient, the base of everything -----------
                float skyFactor = GradientBlend(1.0 - (verticalAngle / (PI * 0.5)), _SkyCurve);
                float3 sky = lerp(_SkyHorizon.rgb, _SkyTop.rgb, skyFactor);

                float groundFactor = GradientBlend((verticalAngle - (PI * 0.5)) / (PI * 0.5), _GroundCurve);
                float3 ground = lerp(_GroundHorizon.rgb, _GroundBottom.rgb, groundFactor);

                // --- V-SKY-02 and V-SKY-03, the two cloud decks -----------
                // The lit side is decided by the sun direction, and the ramp is
                // wide (a cloud is not a hard shaded sphere) and centered
                // slightly toward the sun so most of the sky reads as the
                // shadow side, which is what makes the few lit ones read as
                // lit at all.
                float3 cloudColor = lerp(_SkyHorizon.rgb * CloudShadowDarken, _SkyHorizon.rgb,
                    smoothstep(-0.15, 0.45, sunCos));

                sky = lerp(sky, cloudColor, CloudCoverage(direction, _CloudDensity, UpperCloudOffset));

                float3 lowerDirection = float3(direction.x, -direction.y, direction.z);
                float lowerCoverage = CloudCoverage(lowerDirection,
                    _CloudDensity * LowerCloudDensity, LowerCloudOffset);
                ground = lerp(ground, cloudColor * LowerCloudTint, lowerCoverage);

                // --- V-SKY-03, the abyss ---------------------------------
                // Applied AFTER the lower deck so the wisps sink into the dark
                // with the sky they float in. Darkening the ground first and
                // then mixing bright clouds into it would give the deepest
                // wisps the highest contrast in the frame, which is the
                // opposite of reading as far below.
                ground *= 1.0 - _AbyssDarken * smoothstep(0.0, AbyssFullDepth, -direction.y);

                float3 color = lerp(ground, sky, step(0.0, direction.y));

                // --- V-SKY-01 and V-SKY-03, the horizon haze band ---------
                // One band for both halves, from abs(y), so the sky side and
                // the ground side are pulled toward the SAME color as y goes to
                // zero. That is what makes the horizon a soft crease instead of
                // a line, and it is the half of V-SKY-03's acceptance criterion
                // the gradient alone does not buy.
                float3 hazeColor = min(_SkyHorizon.rgb * BandLift, BandCeiling);
                float band = saturate(exp(-abs(direction.y) * BandFalloff) * _HorizonBand);
                color = lerp(color, hazeColor, band);

                // --- V-SKY-01, the halo then the disc ---------------------
                float halo = saturate(pow(saturate(sunCos), SunHaloExponent) * _SunHalo);
                color = lerp(color, CapToCeiling(_SunColor.rgb, SunHaloCeiling), halo);

                // The disc is the last word and is never occluded by a cloud,
                // deliberately: V-SKY-01's acceptance criterion is that the
                // disc is visible when looking toward the sun, and letting a
                // noise field decide that would make the check depend on the
                // second the frame was taken.
                // Worked in degrees so that _SunSize and the antialiasing width
                // are the numbers an author reads on the property.
                float sunAngleDeg = acos(clamp(sunCos, -1.0, 1.0)) * (180.0 / PI);
                float disc = 1.0 - smoothstep(_SunSize - SunEdgeDeg * 0.5,
                    _SunSize + SunEdgeDeg * 0.5, sunAngleDeg);
                color = lerp(color, _SunColor.rgb * SunDiscBrightness, disc);

                return half4(color * _Exposure, 1.0);
            }
            ENDHLSL
        }
    }

    Fallback Off
}
