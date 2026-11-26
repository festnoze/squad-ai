// Walls 4 (docs/m9/FLOORS_WALLS.md section 7, WallArray): the wall fader's one see-through material (WallFader.GhostMaterial).
// Alpha blended, back faces culled, no depth write, drawn just before the regular transparents, lit as URP Lit
// (WallFinishesForward.hlsl with _SURFACE_TYPE_TRANSPARENT: no SSAO, no screen space shadow on it). A faded part of the
// wall material (_ArrayFinish 1 in its property block) shows the finish its vertices name from the two arrays; any other
// faded part (door frames, baseboards, windows, leaves; _ArrayFinish 0) shows its own 2D maps (_BaseMap and its tiling,
// _BumpMap, _BumpScale, _Smoothness, _Metallic), as the URP Lit see-through material it replaces did.
Shader "OutOfSight/Wall See-through"
{
    Properties
    {
        _BaseColor ("Base colour", Color) = (1, 1, 1, 1)
        _BaseMap ("Base map", 2D) = "white" {}
        [Normal] _BumpMap ("Normal map", 2D) = "bump" {}
        _BumpScale ("Normal strength", Float) = 1
        _Smoothness ("Smoothness", Range(0, 1)) = 0.1
        _Metallic ("Metallic", Range(0, 1)) = 0
        _ArrayFinish ("Wall finish arrays (1) or 2D maps (0)", Float) = 0
        [NoScaleOffset] _WallColours ("Wall colour maps", 2DArray) = "" {}
        [NoScaleOffset] _WallNormals ("Wall normal maps", 2DArray) = "" {}
    }
    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent-1" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        LOD 300

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }
            Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
            ZWrite Off
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma require 2darray
            #pragma vertex WallVertex
            #pragma fragment WallFragment

            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile_fragment _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BLENDING
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BOX_PROJECTION
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_ATLAS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ _LIGHT_COOKIES
            #pragma multi_compile _ _LIGHT_LAYERS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #pragma multi_compile_fragment _ REFLECTION_PROBE_ROTATION
            #include_with_pragmas "Packages/com.unity.render-pipelines.core/ShaderLibrary/FoveatedRenderingKeywords.hlsl"
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"
            #pragma multi_compile_instancing

            #define _SURFACE_TYPE_TRANSPARENT 1
            #define WALL_SEE_THROUGH 1
            #include "WallFinishesInput.hlsl"
            #include "WallFinishesForward.hlsl"
            ENDHLSL
        }
    }
    FallBack Off
}
