// FieldStroke - actor field contributor for liquid threads (ThreadView, RetractionView), docs/CONTRACT.md 12.2.
// Initial version written by B0b; ownership passes to B1.
// Drawn only by ActorFieldCamera (layer LiquidLayers.Field = 31) into _PIO_ActorField. Additive on all four channels with
// alpha as data (not opacity): the fragment returns exactly _Channel * f * _PIO_ActorScale.
// Mesh: MeshTopology.Triangles (a triangle list, not a strip), vertices in world space under an identity transform,
// uv0.x = per-vertex amplitude multiplier (A = _Amplitude * uv0.x), uv0.y = cross coordinate in [-1, 1], vertex color
// unused. f = A * saturate(1 - y * y)^2. Strip half width at each sample = SupportForVisibleRadius(visibleRadius(s), A(s)).
// Per-renderer data through MaterialPropertyBlock: _Channel (LiquidLayers.ChannelMask), _Amplitude.
Shader "PainterIO/FieldStroke"
{
    Properties
    {
        [HideInInspector] _PIO_ShaderId ("id", Float) = 1
        _Channel ("Channel", Vector) = (1, 0, 0, 0)
        _Amplitude ("Amplitude", Float) = 1
    }

    SubShader
    {
        Tags { "RenderPipeline"="UniversalPipeline" "Queue"="Transparent" "RenderType"="Transparent" }

        Pass
        {
            Name "FieldStroke"
            Tags { "LightMode"="SRPDefaultUnlit" }
            Blend One One, One One
            BlendOp Add
            ZWrite Off
            ZTest Always
            Cull Off
            ColorMask RGBA

            HLSLPROGRAM
            #pragma vertex PIO_FieldStrokeVert
            #pragma fragment PIO_FieldStrokeFrag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Assets/Resources/Shaders/LiquidCommon.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _Channel;
                float _Amplitude;
                float _PIO_ShaderId;
            CBUFFER_END

            struct PIO_StrokeAttributes
            {
                float4 positionOS : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct PIO_StrokeVaryings
            {
                float4 positionCS : SV_POSITION;
                float amplitude : TEXCOORD0;
                float crossCoord : TEXCOORD1;
            };

            PIO_StrokeVaryings PIO_FieldStrokeVert(PIO_StrokeAttributes input)
            {
                PIO_StrokeVaryings output;
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                output.amplitude = _Amplitude * input.uv.x;
                output.crossCoord = input.uv.y;
                return output;
            }

            float4 PIO_FieldStrokeFrag(PIO_StrokeVaryings input) : SV_Target
            {
                float y = input.crossCoord;
                float s = saturate(1.0 - y * y);
                float f = input.amplitude * s * s;
                return _Channel * f * _PIO_ActorScale;
            }
            ENDHLSL
        }
    }
}
