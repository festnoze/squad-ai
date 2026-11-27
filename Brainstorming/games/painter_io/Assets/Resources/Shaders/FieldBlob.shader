// FieldBlob - actor field contributor for round blobs (pearl neck blob, retraction bulb, pulses), docs/CONTRACT.md 12.2.
// Initial version written by B0b; ownership passes to B1.
// Drawn only by ActorFieldCamera (layer LiquidLayers.Field = 31) into _PIO_ActorField. Additive on all four channels with
// alpha as data (not opacity): the fragment returns exactly _Channel * f * _PIO_ActorScale.
// Mesh: LiquidLayers.QuadMesh, uv0 in [0,1]^2. Transform scale = (2 S stretch, 2 S / stretch, 1) with
// S = LiquidLayers.SupportForVisibleRadius(visibleRadius, A); Z rotation = velocity angle.
// Per-renderer data through MaterialPropertyBlock: _Channel (LiquidLayers.ChannelMask), _Amplitude.
Shader "PainterIO/FieldBlob"
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
            Name "FieldBlob"
            Tags { "LightMode"="SRPDefaultUnlit" }
            Blend One One, One One
            BlendOp Add
            ZWrite Off
            ZTest Always
            Cull Off
            ColorMask RGBA

            HLSLPROGRAM
            #pragma vertex PIO_FieldBlobVert
            #pragma fragment PIO_FieldBlobFrag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Assets/Resources/Shaders/LiquidCommon.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _Channel;
                float _Amplitude;
                float _PIO_ShaderId;
            CBUFFER_END

            struct PIO_BlobAttributes
            {
                float4 positionOS : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct PIO_BlobVaryings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
            };

            PIO_BlobVaryings PIO_FieldBlobVert(PIO_BlobAttributes input)
            {
                PIO_BlobVaryings output;
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                output.uv = input.uv;
                return output;
            }

            float4 PIO_FieldBlobFrag(PIO_BlobVaryings input) : SV_Target
            {
                // q in [-1, 1]^2 over the quad; f = A * saturate(1 - |q|^2)^2 (support radius = quad half size).
                float2 q = input.uv * 2.0 - 1.0;
                float s = saturate(1.0 - dot(q, q));
                float f = _Amplitude * s * s;
                return _Channel * f * _PIO_ActorScale;
            }
            ENDHLSL
        }
    }
}
