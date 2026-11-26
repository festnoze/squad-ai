Shader "Out of Sight/Window Glass"
{
    Properties
    {
        _Tint ("Glass tint", Color) = (0.93, 0.98, 1, 1)
        _Veil ("Tint opacity", Range(0, 0.1)) = 0.006
        _ReflectionStrength ("Reflection strength", Range(0, 1)) = 0.88
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent" "RenderType" = "Transparent" }
        Pass
        {
            Tags { "LightMode" = "UniversalForwardOnly" }
            Blend One OneMinusSrcAlpha
            Cull Off
            ZWrite Off

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex Vert
            #pragma fragment Frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _Tint;
                half _Veil;
                half _ReflectionStrength;
            CBUFFER_END

            struct Attributes
            {
                float3 positionOS : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 view : TEXCOORD1;
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                output.positionCS = TransformObjectToHClip(input.positionOS);
                output.uv = input.uv;
                // A shared view direction keeps the pattern identical on all six panes.
                float3 center = TransformObjectToWorld(float3(0.0, 0.68, 0.046));
                output.view = TransformWorldToObjectDir(GetWorldSpaceNormalizeViewDir(center));
                return output;
            }

            half Streak(float2 uv, float2 from, float2 to, float width)
            {
                float2 axis = to - from;
                float along = dot(uv - from, axis) / dot(axis, axis);
                float distanceFromLine = length(uv - from - axis * saturate(along));
                float antialias = max(0.0005, 0.75 * fwidth(distanceFromLine));
                float edge = 1.0 - smoothstep(max(0.0, width - antialias), width + antialias, distanceFromLine);
                float tips = smoothstep(0.0, 0.15, along) * (1.0 - smoothstep(0.75, 1.0, along));
                return edge * tips;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                float2 shift = clamp(input.view.xy * float2(0.065, 0.045), -0.033, 0.033);
                float2 uv = float2(1.0 - input.uv.x, input.uv.y) + shift;
                half mainGlint = Streak(uv, float2(0.579, 0.262), float2(0.929, 0.884), 0.0095);
                half echo = Streak(uv, float2(0.842, 0.551), float2(0.951, 0.745), 0.0048);
                half oppositeEdge = Streak(uv, float2(0.079, 0.172), float2(0.190, 0.370), 0.0053);
                half glint = max(0.30h * mainGlint, max(0.67h * echo, 0.52h * oppositeEdge));
                half angle = lerp(0.73h, 1.0h, smoothstep(0.08h, 0.68h, length(input.view.xy)));
                half reflectance = min(1.0h - _Veil, glint * angle * _ReflectionStrength);
                half opacity = saturate(reflectance + _Veil);
                return half4(half3(0.985h, 0.993h, 1.0h) * reflectance + _Tint.rgb * _Veil, opacity);
            }
            ENDHLSL
        }
    }
}
