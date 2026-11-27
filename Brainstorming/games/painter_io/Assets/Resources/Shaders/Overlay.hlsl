// Overlay.hlsl - Custom Function file of Overlay.shadergraph (docs/CONTRACT.md 12.1, 12.3). Owned by B2 (actors).
// Its .meta carries the fixed GUID 3960910ef0d54c65b17d41ea37d5a883: Overlay.shadergraph references this file by that GUID.
//
// Analytic overlay shapes drawn by the main camera after the composite (queue Transparent, Blend SrcAlpha
// OneMinusSrcAlpha, ZTest Always, ZWrite Off): the lasso ring and its halo, the charge ring, chevrons (home arrow, edge
// indicators), the glint of the retraction front and the cut flash. Each shape is one quad of a world-space dynamic mesh
// (Actors/QuadBatch.cs). The four vertices of a quad carry the same per-shape data except UV0.xy:
//   UV0.xy = local shape coordinate (the quad spans [-1, 1]^2); UV0.z = world units per local unit; UV0.w unused
//   UV1    = (shape id, a, b, c)   parameters per shape, below
//   UV2    = (cos, sin of the local frame rotation in world, unused, specular lobes 1 or 2)
//   Vertex color = (linear rgb, opacity)
// Shapes (ids, see QuadBatch.OverlayShape):
//   0 Ring    a = centerline radius, b = tube half width, c = shadow strength. Torus-like fake normal shaded by
//             PIO_ShadeLiquid, soft shadow ring at _PIO_ShadowOffset.
//   1 Halo    a = radius of the glow peak, b = glow width. Soft additive-looking glow.
//   2 Chevron a = arm half thickness, b = outline width, c = outline opacity. Points toward local +x.
//   3 Glint   a = core size, b = ray length, c = ray half width. Four-point sparkle.
//   4 Flash   a = ring radius, b = band half width, c = glow strength. Thin bright ring pulse.
//   5 Disc    a = radius. Flat antialiased disc.
#ifndef PIO_OVERLAY_INCLUDED
#define PIO_OVERLAY_INCLUDED

#include "Assets/Resources/Shaders/LiquidCommon.hlsl"

float PIO_OverlaySegmentDistance(float2 p, float2 a, float2 b)
{
    float2 ab = b - a;
    float t = saturate(dot(p - a, ab) / max(dot(ab, ab), 1e-8));
    return length(p - (a + ab * t));
}

float2 PIO_OverlayRotate(float2 v, float2 cs)
{
    return float2(v.x * cs.x - v.y * cs.y, v.x * cs.y + v.y * cs.x);
}

void PIO_OverlaySG_float(float4 VertexColor, float4 UV0, float4 UV1, float4 UV2, out float3 BaseColor, out float Alpha)
{
    float2 q = UV0.xy;
    float unitsPerLocal = max(UV0.z, 1e-4);
    float shape = UV1.x;
    float2 cs = UV2.xy;
    float csLength = length(cs);
    cs = csLength > 1e-5 ? cs / csLength : float2(1.0, 0.0);
    float lobes = UV2.w > 1.5 ? 2.0 : 1.0;
    float opacity = saturate(VertexColor.a);
    float3 albedo = saturate(VertexColor.rgb);

    float rho = length(q);
    float aa = max(fwidth(rho), 1e-5);
    // Every shape fades out before the quad border so no square edge can show.
    float border = saturate((1.0 - rho) / aa + 0.5);

    float3 color = albedo;
    float alpha = 0.0;

    if (shape < 0.5)
    {
        // Ring: torus-like tube around the centerline radius a, half width b.
        float r0 = UV1.y;
        float w = max(UV1.z, 1e-4);
        float dr = (rho - r0) / w;
        float ringA = saturate((1.0 - abs(dr)) * w / aa + 0.5);
        float sd = clamp(dr, -1.0, 1.0);
        float2 radial = rho > 1e-5 ? q / rho : float2(1.0, 0.0);
        float nz = sqrt(saturate(1.0 - sd * sd));
        float2 nWorld = PIO_OverlayRotate(radial * sd, cs);
        float3 shaded = (float3)PIO_ShadeLiquid((half3)albedo, float3(nWorld, max(nz, 0.02)), nz, lobes);

        // Soft shadow ring centered at center - _PIO_ShadowOffset.
        float2 offset = _PIO_ShadowOffset.xy;
        if (dot(offset, offset) < 1e-8) offset = float2(-0.072, 0.096);
        float2 offsetLocal = float2(offset.x * cs.x + offset.y * cs.y, -offset.x * cs.y + offset.y * cs.x) / unitsPerLocal;
        float drs = (length(q + offsetLocal) - r0) / (w * 1.3);
        float shadowA = saturate(UV1.w) * (1.0 - smoothstep(0.45, 1.25, abs(drs)));

        float outA = ringA + shadowA * (1.0 - ringA);
        color = outA > 1e-5 ? shaded * (ringA / outA) : float3(0.0, 0.0, 0.0);
        alpha = outA;
    }
    else if (shape < 1.5)
    {
        // Halo: soft glow peaking at radius a.
        float r0 = UV1.y;
        float w = max(UV1.z, 1e-4);
        float x = (rho - r0) / w;
        alpha = exp(-x * x) * saturate((1.0 - rho) * 4.0);
    }
    else if (shape < 2.5)
    {
        // Chevron pointing toward local +x, with a dark outline for contrast over bright puddles.
        float t = max(UV1.y, 1e-4);
        float ow = max(UV1.z, 0.0);
        float d = min(PIO_OverlaySegmentDistance(q, float2(-0.26, 0.4), float2(0.45, 0.0)),
                      PIO_OverlaySegmentDistance(q, float2(0.45, 0.0), float2(-0.26, -0.4)));
        float aq = max(fwidth(d), 1e-5);
        float fillA = saturate((t - d) / aq + 0.5);
        float lineA = saturate((t + ow - d) / aq + 0.5) * saturate(UV1.w);
        float3 navy = float3(0.0075, 0.0123, 0.0399);
        float3 fill = albedo * lerp(0.82, 1.0, saturate(0.5 + 0.6 * q.y));
        float outA = fillA + lineA * (1.0 - fillA);
        color = outA > 1e-5 ? (fill * fillA + navy * lineA * (1.0 - fillA)) / outA : fill;
        alpha = outA;
    }
    else if (shape < 3.5)
    {
        // Glint: four-point sparkle.
        float c = max(UV1.y, 1e-4);
        float len = max(UV1.z, 1e-4);
        float rw = max(UV1.w, 1e-4);
        float core = exp(-rho * rho / (c * c));
        float rx = exp(-abs(q.x) / len) * exp(-(q.y * q.y) / (rw * rw));
        float ry = exp(-abs(q.y) / len) * exp(-(q.x * q.x) / (rw * rw));
        alpha = saturate(core + 0.85 * max(rx, ry)) * saturate((1.0 - rho) * 3.0);
    }
    else if (shape < 4.5)
    {
        // Flash: thin bright ring with a soft glow.
        float r0 = UV1.y;
        float w = max(UV1.z, 1e-4);
        float band = saturate((w - abs(rho - r0)) / aa + 0.5);
        float x = (rho - r0) / (w * 4.0);
        float glow = saturate(UV1.w) * exp(-x * x);
        alpha = saturate(band + glow);
    }
    else
    {
        // Disc.
        alpha = saturate((UV1.y - rho) / aa + 0.5);
    }

    BaseColor = color;
    Alpha = saturate(alpha * opacity * border);
}

void PIO_OverlaySG_half(half4 VertexColor, half4 UV0, half4 UV1, half4 UV2, out half3 BaseColor, out half Alpha)
{
    float3 baseColor;
    float alpha;
    PIO_OverlaySG_float((float4)VertexColor, (float4)UV0, (float4)UV1, (float4)UV2, baseColor, alpha);
    BaseColor = (half3)baseColor;
    Alpha = (half)alpha;
}

#endif // PIO_OVERLAY_INCLUDED
