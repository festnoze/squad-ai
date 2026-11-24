// The floor vision cone (VisionConeView, product owner request of 2026-11-20): a fan of light rather than a flat sheet. Its
// opacity is highest at the watcher's eye and fades with distance and toward the two side edges, faint light streaks
// radiate from the eye, and a thin crisp line (a constant few pixels, fwidth) marks the true gameplay edge: the rim where
// the range or an occluder ends each ray, and the two side edges of the half angle. The shape is the mesh's, untouched.
//
// One material per cone colour (_BaseColor, its alpha the nominal opacity); everything per watcher rides the mesh, so no
// renderer carries a property block (URP would also apply a block to the x-ray override material):
//   UV0 = the fragment in the watcher's frame (x across the gaze, y along it), in units of the fan's range: exact under
//         interpolation (linear in the floor position), so the distance and the angle are computed per pixel;
//   UV1 = x the fraction of its own ray's reach (1 on the rim), y the half angle (radians), z a phase seed per watcher,
//         w the watcher's state: 0 calm, 1 searching (alerted or investigating), 2 seeing the furniture;
//   UV2 = x 1 where a low cover hides the furniture top in the middle of a ray (CONECLIP): the fan is cut out there.
// The states differ by pattern as well as by colour (colour-blind players): calm is a still soft gradient with a slow
// shimmer, searching adds a bright band that sweeps from side to side, seeing sends sharp-fronted waves outward from the
// eye with a quick pulse and stronger streaks. With _XRay = 1 (XRay_Cone.mat, the "XRay Cones" pass that redraws the part
// a wall hides) the fan is a blue diagonal hatching in floor space instead, scrolling faster while the watcher sees.
// Cheap on mobile: no texture, no screen-space effect, one atan2 and a few value noises per pixel, no keyword.
Shader "OutOfSight/Vision Cone"
{
    Properties
    {
        _BaseColor ("Colour (alpha: nominal opacity)", Color) = (1, 0.93, 0.55, 0.2)
        _XRay ("X-ray hatching (the part a wall hides)", Float) = 0
    }
    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        Pass
        {
            Name "VisionCone"
            Tags { "LightMode" = "UniversalForwardOnly" }
            Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
            ZWrite Off
            Cull Off

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex Vert
            #pragma fragment Frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _BaseColor;
                half _XRay;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float2 local : TEXCOORD0;
                float4 data : TEXCOORD1;
                float2 shade : TEXCOORD2;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 local : TEXCOORD0;
                float4 data : TEXCOORD1;
                float2 floorXZ : TEXCOORD2;
                float shade : TEXCOORD3;
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                float3 world = TransformObjectToWorld(input.positionOS.xyz);
                output.positionCS = TransformWorldToHClip(world);
                output.local = input.local;
                output.data = input.data;
                output.floorXZ = world.xz;
                output.shade = input.shade.x;
                return output;
            }

            // A sin-free hash (stable on mobile GPUs at large inputs) and its smooth 1D value noise, 0 to 1.
            float Hash11(float n)
            {
                n = frac(n * 0.1031);
                n *= n + 33.33;
                n *= n + n;
                return frac(n);
            }

            float Noise1(float x)
            {
                float i = floor(x);
                float f = frac(x);
                float u = f * f * (3.0 - 2.0 * f);
                return lerp(Hash11(i), Hash11(i + 1.0), u);
            }

            // 1 within about [inner, outer] pixels of the edge where value reaches 1 (value grows toward the edge).
            float EdgeLine(float value, float inner, float outer)
            {
                float w = clamp(fwidth(value), 1e-5, 0.08);
                return smoothstep(1.0 - inner * w, 1.0 - outer * w, value);
            }

            half4 Frag(Varyings input) : SV_Target
            {
                float2 p = input.local;
                float d = length(p);                          // 0 at the eye, 1 at the fan's full range
                float halfAngle = max(input.data.y, 0.01);
                // -1 to 1 from one side edge to the other (nudged off the apex, where atan2(0, 0) is undefined in GLSL).
                float across = atan2(p.x, p.y + 1e-5) / halfAngle;
                float side = saturate(abs(across));
                float rim = input.data.x;                     // 1 on the true outer edge (range or occluder)
                float state = input.data.w;
                float t = _Time.y + input.data.z * 37.0;
                // CONECLIP: 0 where a low cover hides the furniture top in the middle of a ray, 1 elsewhere.
                float keep = 1.0 - saturate(input.shade);

                // The thin crisp edge line, on the rim and on both side edges, a constant width on screen.
                float edge = max(EdgeLine(rim, 2.6, 0.6), EdgeLine(side, 2.6, 0.6) * step(0.02, d));
                // The hatching's coordinate and its screen derivative, taken outside any branch.
                float hatch = (input.floorXZ.x + input.floorXZ.y) * 2.4;
                float hatchAA = max(fwidth(hatch) * 2.0, 1e-4);

                if (_XRay > 0.5)
                {
                    // The hidden part: a diagonal hatching laid on the floor (it stays put when the watcher turns),
                    // anti-aliased by its own screen derivative, scrolling faster while the watcher sees the furniture.
                    float speed = state > 1.5 ? 1.1 : (state > 0.5 ? 0.5 : 0.18);
                    float s = hatch - t * speed;
                    float tri = abs(frac(s) - 0.5) * 2.0;
                    float stripe = smoothstep(0.5 - hatchAA, 0.5 + hatchAA, tri);
                    float fade = lerp(1.15, 0.7, saturate(d));
                    float xa = _BaseColor.a * (0.4 + 0.9 * stripe) * fade;
                    xa = max(xa, edge * 0.6);
                    return half4(_BaseColor.rgb, saturate(xa) * keep);
                }

                // The light: strongest at the eye, fading with distance and toward the side edges, softly started
                // under the watcher's feet.
                float body = lerp(1.5, 0.78, saturate(d));
                body *= lerp(1.0, 0.5, smoothstep(0.45, 1.0, side));
                body *= smoothstep(0.0, 0.07, d);

                // Faint light streaks radiating from the eye, slowly drifting, and a slow shimmer moving outward.
                float streaks = Noise1(across * 7.0 + t * 0.05) * 0.6 + Noise1(across * 17.0 - t * 0.09) * 0.4;
                float shimmer = Noise1(d * 8.0 - t * 0.55);
                float streakAmount = 0.34;
                float lineAlpha = 0.7;

                [branch]
                if (state > 1.5)
                {
                    // Seeing: waves with a sharp outer front run out from the eye, a quick pulse, stronger streaks.
                    float ph = frac(t * 1.5 - d * 3.2);
                    float wave = smoothstep(0.0, 0.05, ph) * (1.0 - smoothstep(0.05, 0.55, ph));
                    body *= (0.88 + 0.9 * wave) * (0.9 + 0.1 * sin(t * 9.0));
                    streakAmount = 0.6;
                    lineAlpha = 0.85;
                }
                else if (state > 0.5)
                {
                    // Searching: a bright band sweeps across the fan from side to side, like a torch beam.
                    float sweep = sin(t * 1.7);
                    float band = (across - sweep) * 3.2;
                    body *= 1.0 + 0.95 * exp(-band * band);
                    lineAlpha = 0.75;
                }
                body *= (1.0 - streakAmount * 0.5) + streakAmount * streaks;
                body *= 0.93 + 0.14 * shimmer;

                // A slightly whiter hot core near the eye.
                half3 colour = lerp(_BaseColor.rgb, half3(1.0, 1.0, 1.0), (half)(0.2 * saturate(1.0 - d * 1.7)));
                float a = _BaseColor.a * body;
                // A soft brighter rim just inside the true edge, then the crisp line itself.
                a *= 1.0 + 0.35 * smoothstep(0.8, 1.0, rim);
                float lineA = edge * lineAlpha;
                // The line in a deeper, more saturated tint (the colour squared): it reads on light floors as on dark ones.
                half3 lineColour = _BaseColor.rgb * _BaseColor.rgb;
                colour = lerp(colour, lineColour, (half)saturate(lineA / max(a + lineA, 1e-3)));
                a = a + lineA * (1.0 - a);
                return half4(colour, min(a, 0.92) * keep);
            }
            ENDHLSL
        }
    }
    FallBack Off
}
