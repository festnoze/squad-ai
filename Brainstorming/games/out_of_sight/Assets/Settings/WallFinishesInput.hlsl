// Walls 4 (docs/m9/FLOORS_WALLS.md section 7): the inputs shared by every pass of OutOfSight/Wall Finishes and
// OutOfSight/Wall See-through. One material per shader for every wall finish: the finishes are slices of two
// Texture2DArrays (colour, sRGB; normal, linear RGB), and each vertex names its own (WallArray.Tag): UV1 = (slice + 1,
// repeats per metre, smoothness, normal strength), UV2.x = 1 for a tiled wall (clamped up the wall).
// The see-through shader also draws any other faded part (frames, baseboards, windows, leaves) from the 2D maps of its
// property block (_BaseMap, _BumpMap, _Smoothness, _Metallic), exactly what the URP Lit see-through material read.
#ifndef OUTOFSIGHT_WALL_FINISHES_INPUT_INCLUDED
#define OUTOFSIGHT_WALL_FINISHES_INPUT_INCLUDED

#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

CBUFFER_START(UnityPerMaterial)
    float4 _BaseMap_ST;
    half4 _BaseColor;
    half _BumpScale;
    half _Smoothness;
    half _Metallic;
    half _ArrayFinish;
CBUFFER_END

TEXTURE2D_ARRAY(_WallColours);
SAMPLER(sampler_WallColours);
TEXTURE2D_ARRAY(_WallNormals);
SAMPLER(sampler_WallNormals);
TEXTURE2D(_BaseMap);
SAMPLER(sampler_BaseMap);
TEXTURE2D(_BumpMap);
SAMPLER(sampler_BumpMap);

#endif
