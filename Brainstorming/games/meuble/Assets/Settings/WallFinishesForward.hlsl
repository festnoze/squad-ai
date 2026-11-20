// Walls 4 (docs/m9/FLOORS_WALLS.md section 7): the forward pass of OutOfSight/Wall Finishes (opaque) and of
// OutOfSight/Wall See-through (_SURFACE_TYPE_TRANSPARENT and WALL_SEE_THROUGH defined). URP's own lighting
// (UniversalFragmentPBR: main light and its cascaded shadows, additional lights in Forward and Forward+, SSAO, reflection
// probes, fog), so a wall lights exactly as the URP Lit material it replaces. What differs:
// - the albedo and the normal come from the finish arrays, the slice and the tile named by the vertex;
// - the tiling is UV0 (metres) times the vertex's repeats per metre, wrapped by the sampler (Repeat both ways); every
//   sample takes the gradients of that continuous UV, so a band's own wraps below leave no mip seam;
// - a tiled wall (UV2.x > 0, its trim height) is laid as bands (WallBandUv): the paint from the floor up to the trim,
//   mirrored back and forth inside the paint stretch of the image (never stretched), the trim once, then the tile field
//   repeated in whole rows to the wall top, every other repeat shifted by UV2.w (the subway tiles' running bond);
// - the tangent frame is rebuilt per pixel from the screen derivatives of the position and the UV (no mesh tangent: the
//   combined wall meshes carry none), its handedness kept whatever the platform's screen orientation;
// - the ambient light is the probe's spherical harmonics per pixel (no lightmap: the levels are built at run time);
// - a vertex may name a flat colour instead of a finish (WallArray.Flat: the fixture housings in a wall cap).
#ifndef OUTOFSIGHT_WALL_FINISHES_FORWARD_INCLUDED
#define OUTOFSIGHT_WALL_FINISHES_FORWARD_INCLUDED

#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

// A band is read this far inside its stretch of the image (one texel of the 512 map), so a wrap never filters in the
// next stretch.
#define WALL_BAND_EDGE (1.0 / 512.0)

struct WallAttributes
{
    float4 positionOS : POSITION;
    float3 normalOS : NORMAL;
    float2 uv : TEXCOORD0;
    float4 finish : TEXCOORD1;
    float4 band : TEXCOORD2;
    UNITY_VERTEX_INPUT_INSTANCE_ID
};

struct WallVaryings
{
    float2 uv : TEXCOORD0;
    float4 finish : TEXCOORD1;
    float3 positionWS : TEXCOORD2;
    float3 normalWS : TEXCOORD3;
#ifdef _ADDITIONAL_LIGHTS_VERTEX
    half4 fogFactorAndVertexLight : TEXCOORD4;
#else
    half fogFactor : TEXCOORD4;
#endif
#if defined(REQUIRES_VERTEX_SHADOW_COORD_INTERPOLATOR)
    float4 shadowCoord : TEXCOORD5;
#endif
    float4 band : TEXCOORD6;
    float4 positionCS : SV_POSITION;
    UNITY_VERTEX_INPUT_INSTANCE_ID
    UNITY_VERTEX_OUTPUT_STEREO
};

WallVaryings WallVertex(WallAttributes input)
{
    WallVaryings output = (WallVaryings)0;
    UNITY_SETUP_INSTANCE_ID(input);
    UNITY_TRANSFER_INSTANCE_ID(input, output);
    UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

    VertexPositionInputs vertexInput = GetVertexPositionInputs(input.positionOS.xyz);
    VertexNormalInputs normalInput = GetVertexNormalInputs(input.normalOS);
    half3 vertexLight = VertexLighting(vertexInput.positionWS, normalInput.normalWS);
    half fogFactor = 0;
#if !defined(_FOG_FRAGMENT)
    fogFactor = ComputeFogFactor(vertexInput.positionCS.z);
#endif

    output.uv = input.uv;
    output.finish = input.finish;
    output.band = input.band;
    output.positionWS = vertexInput.positionWS;
    output.normalWS = normalInput.normalWS;
#ifdef _ADDITIONAL_LIGHTS_VERTEX
    output.fogFactorAndVertexLight = half4(fogFactor, vertexLight);
#else
    output.fogFactor = fogFactor;
#endif
#if defined(REQUIRES_VERTEX_SHADOW_COORD_INTERPOLATOR)
    output.shadowCoord = GetShadowCoord(vertexInput);
#endif
    output.positionCS = vertexInput.positionCS;
    return output;
}

// The tangent frame (rows: tangent, bitangent, normal) of a surface whose UV is uv at positionWS, from the screen
// derivatives (a cotangent frame): T follows the growth of U, B the growth of V. Scaled so the longer is unit, both
// flipped with the sign of the derivatives' determinant, so a flipped screen (render to texture) keeps the handedness.
float3x3 WallTangentFrame(float3 normalWS, float3 positionWS, float2 uv)
{
    float3 dp1 = ddx(positionWS);
    float3 dp2 = ddy(positionWS);
    float2 duv1 = ddx(uv);
    float2 duv2 = ddy(uv);
    float3 dp2perp = cross(dp2, normalWS);
    float3 dp1perp = cross(normalWS, dp1);
    float3 t = dp2perp * duv1.x + dp1perp * duv2.x;
    float3 b = dp2perp * duv1.y + dp1perp * duv2.y;
    float scale = rsqrt(max(max(dot(t, t), dot(b, b)), 1e-20));
    scale *= dot(dp1, dp2perp) < 0.0 ? -1.0 : 1.0;
    return float3x3(t * scale, b * scale, normalWS);
}

// A tiled wall's image UV at metres (x along the wall, y above the floor), repeatsPerMetre the image's own scale, band =
// (trim height, paint top V, tile field bottom V, row shift U). vSign is -1 where the paint is read mirrored (its normal's
// V turns over with it).
float2 WallBandUv(float2 metres, float repeatsPerMetre, float4 band, out float vSign)
{
    float u = metres.x * repeatsPerMetre;
    float y = metres.y;
    float paintTop = band.y;
    float tilesBottom = band.z;
    float trimTop = band.x + (tilesBottom - paintTop) / repeatsPerMetre;
    float v;
    vSign = 1.0;
    if (y < band.x)
    {
        // The paint, from the trim down: back and forth inside [edge, paintTop - edge].
        float range = paintTop - 2.0 * WALL_BAND_EDGE;
        float t = (band.x - y) * repeatsPerMetre;
        float m = fmod(t, 2.0 * range);
        bool back = m > range;
        v = paintTop - WALL_BAND_EDGE - (back ? 2.0 * range - m : m);
        vSign = back ? -1.0 : 1.0;
    }
    else if (y < trimTop)
    {
        v = paintTop + (y - band.x) * repeatsPerMetre;
    }
    else
    {
        // The tile field, in whole rows from the trim up; every other repeat shifted along the wall.
        float field = 1.0 - tilesBottom;
        float t = (y - trimTop) * repeatsPerMetre;
        float k = floor(t / field);
        v = clamp(tilesBottom + (t - k * field), tilesBottom + WALL_BAND_EDGE, 1.0 - WALL_BAND_EDGE);
        u += fmod(k, 2.0) * band.w;
    }
    return float2(u, v);
}

// What the pixel shows: albedo, tangent space normal, smoothness, metallic, and the continuous UV the tangent frame
// follows.
void WallSurface(WallVaryings input, out half3 albedo, out half3 normalTS, out half smoothness, out half metallic, out float2 uv)
{
#if defined(WALL_SEE_THROUGH)
    // A faded part that is no wall of the wall material (_ArrayFinish 0, its property block): its own 2D maps, as the URP
    // Lit see-through material showed them. A uniform branch: one value per draw.
    if (_ArrayFinish < 0.5)
    {
        uv = TRANSFORM_TEX(input.uv, _BaseMap);
        albedo = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, uv).rgb * _BaseColor.rgb;
        normalTS = UnpackNormalScale(SAMPLE_TEXTURE2D(_BumpMap, sampler_BumpMap, uv), _BumpScale);
        smoothness = _Smoothness;
        metallic = _Metallic;
        return;
    }
#endif
    // Fixture housings (2026-11-19, RoomLights): a vertex whose finish is below 0 (WallArray.Flat, UV1.x = -1) is a flat
    // painted part merged into its wall line's cap: the black metal frame of a sconce or a neon tube. Albedo UV2.rgb
    // (linear), metallic UV1.y, smoothness UV1.z, no normal map. A vertex attribute branch: a frame's triangles are all
    // flat, a wall's never, so a warp never mixes them except along a frame's silhouette.
    if (input.finish.x < -0.5)
    {
        uv = input.uv;
        albedo = input.band.rgb * _BaseColor.rgb;
        normalTS = half3(0.0, 0.0, 1.0);
        smoothness = input.finish.z;
        metallic = input.finish.y;
        return;
    }
    float slice = round(input.finish.x) - 1.0;
    uv = input.uv * input.finish.y;
    float2 dx = ddx(uv);
    float2 dy = ddy(uv);
    float vSign = 1.0;
    float2 at = input.band.x > 0.0 ? WallBandUv(input.uv, input.finish.y, input.band, vSign) : uv;
    albedo = SAMPLE_TEXTURE2D_ARRAY_GRAD(_WallColours, sampler_WallColours, at, slice, dx, dy).rgb * _BaseColor.rgb;
    normalTS = UnpackNormalRGB(SAMPLE_TEXTURE2D_ARRAY_GRAD(_WallNormals, sampler_WallNormals, at, slice, dx, dy), input.finish.w);
    normalTS.y *= vSign;
    smoothness = input.finish.z;
    metallic = 0;
}

void WallFragment(
    WallVaryings input
    , out half4 outColor : SV_Target0
#ifdef _WRITE_RENDERING_LAYERS
    , out uint outRenderingLayers : SV_Target1
#endif
)
{
    UNITY_SETUP_INSTANCE_ID(input);
    UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

    half3 albedo;
    half3 normalTS;
    half smoothness;
    half metallic;
    float2 uv;
    WallSurface(input, albedo, normalTS, smoothness, metallic, uv);

    float3 normalWS = normalize(input.normalWS);
    half3x3 tangentToWorld = (half3x3)WallTangentFrame(normalWS, input.positionWS, uv);

    InputData inputData = (InputData)0;
    inputData.positionWS = input.positionWS;
    inputData.positionCS = input.positionCS;
    inputData.tangentToWorld = tangentToWorld;
    inputData.normalWS = NormalizeNormalPerPixel(TransformTangentToWorld(normalTS, tangentToWorld));
    inputData.viewDirectionWS = GetWorldSpaceNormalizeViewDir(input.positionWS);
#if defined(REQUIRES_VERTEX_SHADOW_COORD_INTERPOLATOR)
    inputData.shadowCoord = input.shadowCoord;
#elif defined(MAIN_LIGHT_CALCULATE_SHADOWS)
    inputData.shadowCoord = TransformWorldToShadowCoord(input.positionWS);
#else
    inputData.shadowCoord = float4(0, 0, 0, 0);
#endif
#ifdef _ADDITIONAL_LIGHTS_VERTEX
    inputData.fogCoord = InitializeInputDataFog(float4(input.positionWS, 1.0), input.fogFactorAndVertexLight.x);
    inputData.vertexLighting = input.fogFactorAndVertexLight.yzw;
#else
    inputData.fogCoord = InitializeInputDataFog(float4(input.positionWS, 1.0), input.fogFactor);
#endif
    inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(input.positionCS);
    inputData.bakedGI = SampleSH(inputData.normalWS);
    inputData.shadowMask = unity_ProbesOcclusion;

    SurfaceData surfaceData = (SurfaceData)0;
    surfaceData.albedo = albedo;
    surfaceData.metallic = metallic;
    surfaceData.specular = half3(0, 0, 0);
    surfaceData.smoothness = smoothness;
    surfaceData.normalTS = normalTS;
    surfaceData.occlusion = 1;
    surfaceData.alpha = _BaseColor.a;

    half4 color = UniversalFragmentPBR(inputData, surfaceData);
    color.rgb = MixFog(color.rgb, inputData.fogCoord);
#if defined(_SURFACE_TYPE_TRANSPARENT)
    color.a = surfaceData.alpha;
#else
    color.a = 1.0;
#endif
    outColor = color;
#ifdef _WRITE_RENDERING_LAYERS
    outRenderingLayers = EncodeMeshRenderingLayer();
#endif
}

#endif
