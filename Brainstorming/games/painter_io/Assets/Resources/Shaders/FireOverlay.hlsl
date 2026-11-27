// FireOverlay.hlsl - the Custom Function of FireOverlay.shadergraph (docs/CONTRACT.md 25.2, 25.3, 25.5), owned by FIRE.
// Its .meta carries the fixed GUID 7df522bc4bde490797588a22616802a0: FireOverlay.shadergraph references this file by that GUID.
//
// The Feu biome's overlay shapes, with the SAME vertex data and shape ids as Overlay.hlsl (Actors/QuadBatch.cs
// AddOverlay): UV0.xy = local coordinate (the quad spans [-1, 1]^2), UV0.z = world units per local unit, UV1 = (shape id,
// a, b, c), UV2 = (cos, sin of the local frame, unused, lobes), vertex color = (linear rgb, opacity).
// Shared shapes, restyled as fire (same parameters):
//   0 Ring    a = centerline radius, b = tube half width, c = glow strength. A white-hot ring of fire: bright tube,
//             small flame tongues licking outward, a warm glow instead of a shadow.
//   1 Halo    a = radius of the glow peak, b = glow width. Warm soft glow.
//   2 Chevron a = arm half thickness, b = outline width, c = outline opacity. Flat fill, charcoal outline.
//   3 Glint   a = core size (unused since wave C), b = ray length, c = ray half width. THE SPARK: a solid white disc
//             over a saturated orange halo with eight flickering rays (HDR core on High), the brightest moving thing on
//             screen during a chase with or without bloom (contract 25.5); disc and halo are sized in world units.
//   4 Flash   a = ring radius, b = band half width, c = glow strength. A fiery ring pulse (cut flash).
//   5 Disc    a = radius. Flat antialiased disc.
// FireFx shapes (Biomes/FireFx.cs):
//  10 Ember   a = heat 0..1, b = unused, c = seed. A glowing ember or spark, elongated by the quad (stretched along its
//             velocity); white hot at heat 1, the flame color (vertex color) at 0.5, dark red and transparent at 0.
//  11 Smoke   a = seed, b = density, c = unused. A soft, noisy smoke puff in the vertex color.
//  12 Ash     a = heat 0..1, b = seed, c = unused. The burnt fuse droplet cooling to ash: transparent at heat 1 (the hot
//             ember bead under it shows), glowing cracks on grey ash in between, opaque grey ash at 0.
#ifndef PIO_FIRE_OVERLAY_INCLUDED
#define PIO_FIRE_OVERLAY_INCLUDED

#include "Assets/Resources/Shaders/LiquidCommon.hlsl"

#define PIO_FIRE_SPARK_DISC 0.12       // u: radius of the solid white disc of the spark (shape 3)
#define PIO_FIRE_SPARK_CORONA 0.17     // u: outer radius of the pale white-hot corona around the disc
#define PIO_FIRE_SPARK_HALO 0.45       // u: radius of its orange halo

float PIO_FireOverlayHash(float2 cell)
{
    uint2 q = (uint2)((int2)cell + 65536);
    uint h = (q.x * 1597334677u) ^ (q.y * 3812015801u);
    h = h * 0x9E3779B1u;
    h ^= h >> 16;
    h *= 0x85EBCA6Bu;
    h ^= h >> 13;
    return (float)h * (1.0 / 4294967296.0);
}

float PIO_FireOverlayNoise(float2 p)
{
    float2 i = floor(p);
    float2 f = p - i;
    f = f * f * (3.0 - 2.0 * f);
    float a = PIO_FireOverlayHash(i);
    float b = PIO_FireOverlayHash(i + float2(1.0, 0.0));
    float c = PIO_FireOverlayHash(i + float2(0.0, 1.0));
    float d = PIO_FireOverlayHash(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

float PIO_FireOverlaySegmentDistance(float2 p, float2 a, float2 b)
{
    float2 ab = b - a;
    float t = saturate(dot(p - a, ab) / max(dot(ab, ab), 1e-8));
    return length(p - (a + ab * t));
}

float2 PIO_FireOverlayRotate(float2 v, float2 cs)
{
    return float2(v.x * cs.x - v.y * cs.y, v.x * cs.y + v.y * cs.x);
}

// Hot ramp of a flame color: 0 = dark red ember, 0.5 = the flame color, 1 = white hot (HDR).
float3 PIO_FireOverlayRamp(float heat, float3 flame)
{
    float3 c = lerp(flame * float3(0.35, 0.12, 0.08), flame * 1.25, smoothstep(0.0, 0.5, heat));
    return lerp(c, float3(2.4, 2.0, 1.4), smoothstep(0.55, 1.0, heat));
}

void PIO_FireOverlaySG_float(float4 VertexColor, float4 UV0, float4 UV1, float4 UV2, out float3 BaseColor, out float Alpha)
{
    float2 q = UV0.xy;
    float unitsPerLocal = max(UV0.z, 1e-4);
    float shape = UV1.x;
    float2 cs = UV2.xy;
    float csLength = length(cs);
    cs = csLength > 1e-5 ? cs / csLength : float2(1.0, 0.0);
    float opacity = saturate(VertexColor.a);
    float3 albedo = max(VertexColor.rgb, 0.0);
    float time = _PIO_Time.x;

    float rho = length(q);
    float aa = max(fwidth(rho), 1e-5);
    // Every shape fades out before the quad border so no square edge can show.
    float border = saturate((1.0 - rho) / aa + 0.5);

    float3 color = albedo;
    float alpha = 0.0;

    if (shape < 0.5)
    {
        // Ring of fire: a white-hot tube with small tongues licking outward and a warm glow.
        float r0 = UV1.y;
        float w = max(UV1.z, 1e-4);
        float2 world = PIO_FireOverlayRotate(q, cs);       // local frame turned to world axes (tongues rise up)
        float n = PIO_FireOverlayNoise(world * (3.2 / max(r0, 0.05)) + float2(0.0, -time * 3.0));
        float dr = (rho - r0) / w;
        float tube = saturate((1.0 - abs(dr)) * w / aa + 0.5);
        float lickOut = saturate((1.0 + 1.6 * n - dr) / 0.6) * step(0.0, dr) * saturate(dr + 1.0);
        float glowX = (rho - r0) / (w * 3.5);
        float glow = saturate(UV1.w + 0.2) * 0.45 * exp(-glowX * glowX);
        float core = 1.0 - saturate(abs(dr));
        float3 tubeCol = lerp(albedo * float3(1.0, 0.78, 0.45), float3(1.9, 1.75, 1.45), core * core);
        float3 lickCol = lerp(float3(1.0, 0.55, 0.18), float3(1.6, 1.3, 0.8), n);
        float a1 = max(lickOut * 0.75 * (0.6 + 0.4 * n), glow);
        float3 c1 = lickOut * 0.75 > glow ? lickCol : albedo * float3(1.0, 0.72, 0.4);
        float outA = tube + a1 * (1.0 - tube);
        color = outA > 1e-5 ? (tubeCol * tube + c1 * a1 * (1.0 - tube)) / outA : tubeCol;
        alpha = outA;
    }
    else if (shape < 1.5)
    {
        // Warm halo.
        float r0 = UV1.y;
        float w = max(UV1.z, 1e-4);
        float x = (rho - r0) / w;
        alpha = exp(-x * x) * saturate((1.0 - rho) * 4.0);
        color = lerp(albedo, float3(1.0, 0.62, 0.25), 0.35);
    }
    else if (shape < 2.5)
    {
        // Chevron pointing toward local +x, with a charcoal outline for contrast over bright embers.
        float t = max(UV1.y, 1e-4);
        float ow = max(UV1.z, 0.0);
        float d = min(PIO_FireOverlaySegmentDistance(q, float2(-0.26, 0.4), float2(0.45, 0.0)),
                      PIO_FireOverlaySegmentDistance(q, float2(0.45, 0.0), float2(-0.26, -0.4)));
        float aq = aa;                                     // d and rho are both unit-gradient distances: no fwidth here
        float fillA = saturate((t - d) / aq + 0.5);
        float lineA = saturate((t + ow - d) / aq + 0.5) * saturate(UV1.w);
        float3 charcoal = float3(0.012, 0.009, 0.008);
        float3 fill = albedo * lerp(0.84, 1.0, saturate(0.5 + 0.6 * q.y));
        float outA = fillA + lineA * (1.0 - fillA);
        color = outA > 1e-5 ? (fill * fillA + charcoal * lineA * (1.0 - fillA)) / outA : fill;
        alpha = outA;
    }
    else if (shape < 3.5)
    {
        // THE SPARK (contract 25.5): the brightest moving thing on screen, with or without bloom. Sized in world units
        // through UV0.z (world units per local unit; the actors package draws the front glint at a 0.5 u half size): a
        // solid white disc of radius PIO_FIRE_SPARK_DISC over a saturated orange halo (#FF8A2A, radius
        // PIO_FIRE_SPARK_HALO, alpha 0.8 with a smooth falloff) and eight flickering rays (1.5 x longer than wave B).
        // Without bloom (Medium and Low, the Android tiers) this LDR signature reads by itself; High (bicubic tier, the
        // only one with bloom) keeps the HDR boost of the core and the rays. The disc holds its full alpha down to an
        // opacity of 0.62 (the glint flicker and a fading cut burst dim the rays and the halo first).
        float len = max(UV1.z, 1e-4) * 2.25;
        float rw = max(UV1.w, 1e-4) * 1.2;
        float flick = 0.8 + 0.2 * sin(time * 61.0) * sin(time * 37.0 + 1.3);
        float rWorld = rho * unitsPerLocal;
        float aaWorld = max(aa * unitsPerLocal, 1e-4);
        float disc = saturate((PIO_FIRE_SPARK_DISC - rWorld) / aaWorld + 0.5);
        // White-hot corona hugging the disc (pale yellow, still above 235 luma without bloom), then the orange halo,
        // saturated (alpha 0.8) out to about half its radius before it falls off smoothly.
        float corona = saturate((PIO_FIRE_SPARK_CORONA - rWorld) / aaWorld + 0.5);
        float haloA = 0.8 * (1.0 - smoothstep(0.2, PIO_FIRE_SPARK_HALO, rWorld));
        float rx = exp(-abs(q.x) / len) * exp(-(q.y * q.y) / (rw * rw));
        float ry = exp(-abs(q.y) / len) * exp(-(q.x * q.x) / (rw * rw));
        float2 qd = float2(q.x + q.y, q.x - q.y) * 0.70710678;
        float dx = exp(-abs(qd.x) / (len * 0.6)) * exp(-(qd.y * qd.y) / (rw * rw * 0.6));
        float dy = exp(-abs(qd.y) / (len * 0.6)) * exp(-(qd.x * qd.x) / (rw * rw * 0.6));
        float rays = max(max(rx, ry), 0.7 * max(dx, dy)) * flick;
        float raysA = saturate(1.1 * rays) * saturate((1.0 - rho) * 3.0);
        bool hdr = _PIO_Quality.z > 0.5;
        float3 white = hdr ? float3(5.2, 4.6, 3.6) : float3(1.0, 1.0, 1.0);
        float3 rayCol = hdr ? lerp(float3(2.6, 1.6, 0.6), white, saturate(rays * 0.6))
                            : lerp(float3(1.0, 0.8, 0.5), white, saturate(rays * 1.3));
        float3 haloCol = hdr ? float3(2.2, 0.6, 0.06) : float3(1.0, 0.254, 0.0232);
        float3 coronaCol = hdr ? float3(3.2, 2.4, 1.2) : float3(1.0, 0.9, 0.62);
        // Halo, rays over it (both dimmed by the opacity), then the corona and the disc on top.
        float layerA = haloA;
        float3 layerC = haloCol;
        float outA = raysA + layerA * (1.0 - raysA);
        layerC = outA > 1e-5 ? (rayCol * raysA + layerC * layerA * (1.0 - raysA)) / outA : rayCol;
        layerA = outA * opacity;
        float discA = max(disc, corona) * saturate(opacity * 1.6);
        float3 discC = lerp(coronaCol, white, disc);
        outA = discA + layerA * (1.0 - discA);
        color = outA > 1e-5 ? (discC * discA + layerC * layerA * (1.0 - discA)) / outA : discC;
        alpha = outA;
        opacity = 1.0;                                     // already applied per layer
    }
    else if (shape < 4.5)
    {
        // Fiery ring pulse.
        float r0 = UV1.y;
        float w = max(UV1.z, 1e-4);
        float band = saturate((w - abs(rho - r0)) / aa + 0.5);
        float x = (rho - r0) / (w * 4.0);
        float glow = saturate(UV1.w) * exp(-x * x);
        alpha = saturate(band + glow);
        color = lerp(float3(1.6, 0.75, 0.25), float3(2.2, 1.9, 1.5), band);
    }
    else if (shape < 7.5)
    {
        // Disc (and any unknown shared id).
        alpha = saturate((UV1.y - rho) / aa + 0.5);
    }
    else if (shape < 10.5)
    {
        // Ember / spark particle (the quad is stretched along its velocity).
        float heat = saturate(UV1.y);
        float core = exp(-dot(q, q) * 4.0);
        float hotCore = exp(-dot(q, q) * 14.0);
        alpha = saturate(core * (0.35 + 0.65 * heat) + hotCore * heat) * saturate((1.0 - rho) * 3.0);
        color = PIO_FireOverlayRamp(heat * (0.75 + 0.25 * hotCore), albedo);
    }
    else if (shape < 11.5)
    {
        // Smoke puff.
        float seed = UV1.y;
        float density = saturate(UV1.z);
        float n = PIO_FireOverlayNoise(q * 2.1 + float2(seed * 17.0, seed * 5.0 - time * 0.4)) * 0.6
                + PIO_FireOverlayNoise(q * 4.3 + float2(-seed * 9.0, time * 0.3)) * 0.4;
        float body = 1.0 - smoothstep(0.15 + 0.3 * n, 1.0, rho);
        alpha = density * body * (0.55 + 0.45 * n);
        color = albedo * (0.85 + 0.3 * n);
    }
    else
    {
        // Ash of a burnt fuse droplet.
        float heat = saturate(UV1.y);
        float seed = UV1.z;
        float n = PIO_FireOverlayNoise(q * 2.6 + seed * 23.0);
        float disc = 1.0 - smoothstep(0.62, 1.0, rho + 0.18 * (n - 0.5));
        float cool = 1.0 - heat;
        // Covers the hot bead quickly (opaque from heat 0.45 down); in between, a dull red crust with glowing cracks.
        alpha = disc * saturate(cool * 1.8);
        float cracks = smoothstep(0.5, 0.78, n);
        float3 ashCol = float3(0.075, 0.068, 0.063) * (0.8 + 0.4 * n);
        ashCol = lerp(ashCol, albedo * 0.32, saturate(heat * 1.6));
        float glowAmt = saturate((heat - 0.08) * 2.2) * cracks;
        color = lerp(ashCol, albedo * 1.2 + float3(0.12, 0.04, 0.0), glowAmt);
    }

    BaseColor = color;
    Alpha = saturate(alpha * opacity * border);
}

void PIO_FireOverlaySG_half(half4 VertexColor, half4 UV0, half4 UV1, half4 UV2, out half3 BaseColor, out half Alpha)
{
    float3 baseColor;
    float alpha;
    PIO_FireOverlaySG_float((float4)VertexColor, (float4)UV0, (float4)UV1, (float4)UV2, baseColor, alpha);
    BaseColor = (half3)baseColor;
    Alpha = (half)alpha;
}

#endif // PIO_FIRE_OVERLAY_INCLUDED
