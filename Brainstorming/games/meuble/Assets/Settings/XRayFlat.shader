// The x-ray silhouette's override shader (XRay_Silhouette.mat, ProjectSetup): one flat colour, alpha blended, no depth
// write. URP applies a renderer's MaterialPropertyBlock to a RenderObjects override material too, and the characters'
// blocks carry their own prints and base colour (_BaseMap, _BaseColor, CharacterLook): with URP Unlit the hidden body
// showed in its own colours through a standing wall. Its colour is _XRayColor, a property no renderer block ever sets.
Shader "OutOfSight/XRay Flat"
{
    Properties
    {
        _XRayColor ("X-ray colour", Color) = (0.22, 0.52, 1, 0.85)
        [Enum(UnityEngine.Rendering.CullMode)] _Cull ("Cull", Float) = 2
    }
    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        Pass
        {
            Name "XRayFlat"
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull [_Cull]

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _XRayColor;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                return _XRayColor;
            }
            ENDHLSL
        }
    }
}
