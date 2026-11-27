// Europe map (EuropeMapView): extruded land (vertex colors x _Tint), flagpoles, and the flag cloths animated on the GPU
// (_Wave = 1: the vertices wave in the vertex shader, phase-shifted per flag by _Phase, so every flag shares one mesh and
// one material, its texture coming from a MaterialPropertyBlock). _Cutout = 1 discards texels with alpha < 0.5 (the
// conquered medal).
Shader "PainterIO/EuropeMap"
{
    Properties
    {
        _MainTex ("Flag", 2D) = "white" {}
        _Tint ("Tint", Color) = (1, 1, 1, 1)
        _Wave ("Cloth wave", Float) = 0
        _Phase ("Cloth phase", Float) = 0
        _Cutout ("Alpha cutout", Float) = 0
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "RenderType" = "Opaque" }
        Pass
        {
            Cull Off
            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);
            CBUFFER_START(UnityPerMaterial)
            float4 _Tint;
            float _Wave;
            float _Phase;
            float _Cutout;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float2 uv : TEXCOORD0;
                float4 color : COLOR;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 color : COLOR;
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                float3 position = input.positionOS.xyz;
                float phase = input.uv.x * 10.0 - _Time.y * 4.0 + input.uv.y + _Phase;
                position.z += _Wave * 0.23 * input.uv.x * sin(phase);
                position.y += _Wave * 0.09 * input.uv.x * cos(phase);
                output.positionCS = TransformObjectToHClip(position);
                output.uv = input.uv;
                output.color = lerp(input.color.rgb, (0.88 + 0.12 * cos(phase)).xxx, _Wave) * _Tint.rgb;
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                half4 texel = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, input.uv);
                UNITY_BRANCH
                if (_Cutout > 0.5) clip(texel.a - 0.5);
                return half4(texel.rgb * input.color, 1);
            }
            ENDHLSL
        }
    }
}
