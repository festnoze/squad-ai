// FISHEYE (docs/next/progress/FISHEYE.md): the barrel distortion and the peripheral blur of the title menu's 3D
// background, drawn by MenuFisheyePass (Assets/Scripts/Runtime/MenuFisheye.cs) as one full-screen blit of the title
// camera's colour, after its post-processing, before the final blit (the overlay canvases of the menu, the title logo
// and the HUD come after it). No keyword, one pass: the material is created from code, so the shader is in Always
// Included Shaders (ProjectSetup).
//
// Lens: for an output pixel at uv, with d its offset from the lens centre and r2 its squared radius (in screen heights,
// normalised so the farthest screen corner is 1), the source is sampled at centre + d * (1 + k * r2) * fit, where
// fit = 1 / ((1 + k) * zoom). With zoom 1 the farthest corner samples exactly its own corner and every other pixel
// samples nearer the centre than itself: no black and no clamped (stretched) border. The centre is magnified 1 + k times.
//
// Peripheral blur: weight w = smoothstep(radius, radius + BLUR_FALLOFF, rb), rb the way from the lens centre to the
// screen edge on each side (corners 1), so the centre stays sharp. Where blur * w > 0, BLUR_TAPS - 1 more taps around
// the lens sample, each offset by a mix (motion) of a soft disc (golden angle spiral) and a radial streak through the
// sample (zoom blur), in a fixed pattern. Blur 0 or the sharp centre: no extra tap (a branch on the weight).
Shader "OutOfSight/Menu Fisheye"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" "RenderPipeline" = "UniversalPipeline" }
        ZWrite Off
        ZTest Always
        Cull Off
        Blend Off

        Pass
        {
            Name "MenuFisheye"

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.core/Runtime/Utilities/Blit.hlsl"

            // Taps per blurred pixel, the lens sample included.
            #define BLUR_TAPS 8
            // Width of the blur's ramp, in normalised radius (the farthest corner is 1).
            #define BLUR_FALLOFF 0.45
            // Full-strength sizes, in screen heights: the streak's length and the soft disc's radius.
            #define BLUR_STREAK 0.05
            #define BLUR_DISC 0.012

            // x: strength k, y: fit = 1 / ((1 + k) * zoom), z: vignette, w: unused.
            float4 _FisheyeParams;
            // xy: lens centre (uv), z: aspect (width / height), w: 1 / (squared radius of the farthest corner).
            float4 _FisheyeLens;
            // x: peripheral blur strength, y: clear radius (normalised), z: motion (0 soft, 1 radial streak), w: unused.
            float4 _FisheyeBlur;

            half4 Frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);
                float2 uv = input.texcoord;
                float aspect = _FisheyeLens.z;
                float2 d = uv - _FisheyeLens.xy;
                float2 dn = float2(d.x * aspect, d.y);
                float r2 = dot(dn, dn) * _FisheyeLens.w;
                float2 suv = _FisheyeLens.xy + d * ((1.0 + _FisheyeParams.x * r2) * _FisheyeParams.y);
                half4 c = SAMPLE_TEXTURE2D_X_LOD(_BlitTexture, sampler_LinearClamp, suv, 0);

                // The blur's radius: the way from the lens centre to the screen's edge on each side (each corner is 1,
                // each edge's middle 0.71), so the periphery blurs alike on every side even with the lens off centre.
                float2 side = float2(d.x < 0.0 ? _FisheyeLens.x : 1.0 - _FisheyeLens.x, d.y < 0.0 ? _FisheyeLens.y : 1.0 - _FisheyeLens.y);
                float rb = length(d / max(side, 1e-4)) * 0.70710678;
                float amount = _FisheyeBlur.x * smoothstep(_FisheyeBlur.y, _FisheyeBlur.y + BLUR_FALLOFF, rb);
                UNITY_BRANCH
                if (amount > 0.0005)
                {
                    // Directions in screen heights, turned back into uv by dividing x by the aspect.
                    float2 sd = float2((suv.x - _FisheyeLens.x) * aspect, suv.y - _FisheyeLens.y);
                    float len = length(sd);
                    float2 radial = len > 1e-5 ? sd / len : float2(1.0, 0.0);
                    float2 toUv = float2(1.0 / aspect, 1.0);
                    float streak = amount * BLUR_STREAK;
                    float disc = amount * BLUR_DISC;
                    float motion = _FisheyeBlur.z;
                    half4 sum = c;
                    // A fixed pattern (no per-pixel noise: with so few taps it reads as grain).
                    UNITY_UNROLL
                    for (int i = 1; i < BLUR_TAPS; i++)
                    {
                        float t = i / (float)(BLUR_TAPS - 1);
                        // Radial streak through the sample, alternately inward and outward, so the picture does not shift.
                        float2 streakOffset = radial * ((i & 1) ? -0.5 : 0.5) * (floor((i + 1) * 0.5) / (BLUR_TAPS * 0.5)) * streak;
                        // Soft disc: a golden angle spiral.
                        float angle = i * 2.39996;
                        float2 discOffset = float2(cos(angle), sin(angle)) * sqrt(t) * disc;
                        float2 offset = lerp(discOffset, streakOffset, motion) * toUv;
                        sum += SAMPLE_TEXTURE2D_X_LOD(_BlitTexture, sampler_LinearClamp, suv + offset, 0);
                    }
                    c = sum / BLUR_TAPS;
                }

                // Zoomed out (zoom below 1): what falls outside the picture is black, never a stretched edge.
                float2 inside = step(-0.001, suv) * step(suv, 1.001);
                half keep = (half)(inside.x * inside.y);
                half shade = (half)(1.0 - _FisheyeParams.z * smoothstep(0.3, 1.0, r2));
                c.rgb *= keep * shade;
                return c;
            }
            ENDHLSL
        }
    }
    Fallback Off
}
