// Bead.hlsl - Custom Function file of Bead.shadergraph (docs/CONTRACT.md 12.1, 12.3). Written by B2 (actors); owned by
// LIQ since wave B-2 (liquid polish: shadow reach and softness matched to the composite, rim bounce light on pearls).
// Its .meta carries the fixed GUID c0ad563d8fb44f6ab2e595470040888f: Bead.shadergraph references this file by that GUID.
//
// Analytic bead impostors: pearls, droplets and splash drops, drawn at full resolution by the main camera after the
// composite (queue Transparent, Blend SrcAlpha OneMinusSrcAlpha, ZTest Always, ZWrite Off). Each bead is one quad of a
// world-space dynamic mesh (Actors/QuadBatch.cs). The four vertices of a quad carry the same per-bead data:
//   UV0.xy = world offset of the vertex from the bead center (interpolated: the pixel's offset); UV0.zw unused
//   UV1    = (radius in u, stretch along dir, dir.x, dir.y); stretch 1 is round, > 1 elongates along dir (1 / stretch across)
//   UV2    = (shadow strength 0..1, specular lobes 1 or 2, highlight boost 0..1, unused)
//   Vertex color = (linear albedo rgb, opacity)
// A soft shadow ellipse is drawn first (same quad) at _PIO_ShadowOffset (sampling toward the light puts it lower right),
// then the bead: q = local offset / radii, 1 px antialiased disc, nTable = (q, sqrt(1 - |q|^2)), color = PIO_ShadeLiquid.
// Wave D (liq-drop, contract 28 F2, "the pearl reads as a drop too"): a pearl-sized bead (radius >= about 0.3 u) that
// moves (PearlView's stretch above 1: 1.04 while it runs straight, less in a tight turn) becomes a slight teardrop along
// its motion: the rear half (toward its thread) is drawn longer and narrower, its shadow follows. Droplets, splash drops
// and the retraction bulb bead (all smaller than 0.3 u) keep their shapes.
#ifndef PIO_BEAD_INCLUDED
#define PIO_BEAD_INCLUDED

#include "Assets/Resources/Shaders/LiquidCommon.hlsl"

#define PIO_BEAD_SHADOW_SCALE 1.5      // same reach as LiquidComposite.hlsl PIO_SHADOW_SCALE (0.18 u)
#define PIO_TEAR_LENGTH 0.28           // the rear half of a moving pearl is up to 28 % longer ...
#define PIO_TEAR_TAPER 0.32            // ... and narrows toward its tail (width x (1 - 0.32 u^2))

// Teardrop warp of the bead's unit coordinates (x along the motion): the rear (x < 0) is stretched and tapered, the front
// half stays round. Smooth across the middle (no crease in the dome normal), the identity when tear = 0.
float2 PIO_TearWarp(float2 q, float tear)
{
    float back = smoothstep(0.2, -0.6, q.x) * tear;
    float u = q.x / (1.0 + PIO_TEAR_LENGTH * back);
    float taper = 1.0 - PIO_TEAR_TAPER * back * saturate(u * u);
    return float2(u, q.y / taper);
}

// One soft rounded window pane of the key light's reflection: center c and tangent axis (unit) in world axes, in the
// dome-normal plane (|n.xy| = 1 on the rim); 0.11 x 0.08 half extents, soft edge.
float PIO_BeadPane(float2 nxy, float2 c, float2 tangent)
{
    float2 d = nxy - c;
    float u = dot(d, tangent) * (1.0 / 0.11);
    float v = dot(d, float2(-tangent.y, tangent.x)) * (1.0 / 0.08);
    float r = pow(pow(abs(u), 4.0) + pow(abs(v), 4.0), 0.25);           // rounded square
    return 1.0 - smoothstep(0.55, 1.0, r);
}

void PIO_BeadSG_float(float4 VertexColor, float4 UV0, float4 UV1, float4 UV2, out float3 BaseColor, out float Alpha)
{
    float2 p = UV0.xy;
    float radius = max(UV1.x, 1e-4);
    float stretch = clamp(UV1.y, 0.25, 4.0);
    float2 dir = UV1.zw;
    float dirLength = length(dir);
    dir = dirLength > 1e-5 ? dir / dirLength : float2(1.0, 0.0);
    float2 perp = float2(-dir.y, dir.x);
    float2 radii = radius * float2(stretch, 1.0 / stretch);

    // World units per pixel (orthographic camera without rotation).
    float wpp = max(max(fwidth(p.x), fwidth(p.y)), 1e-6);

    // Wave D: teardrop amount, full for a pearl running straight (stretch 1.04), none for a round or small bead.
    float tear = smoothstep(0.28, 0.34, radius) * saturate((stretch - 1.0) * (1.0 / 0.04));

    // Bead disc, 1 px antialiasing centered on the true radius.
    float2 local = float2(dot(p, dir), dot(p, perp));
    float2 q = PIO_TearWarp(local / radii, tear);
    float d2 = dot(q, q);
    float d = sqrt(d2);
    float radiusPixels = min(radii.x, radii.y) / wpp;
    float beadA = saturate((1.0 - d) * radiusPixels + 0.5);

    // Dome normal in table space (x, y = world x, y; z toward the viewer).
    float2 qn = d > 1.0 ? q / d : q;
    float nz = sqrt(saturate(1.0 - dot(qn, qn)));
    float2 nxy = qn.x * dir + qn.y * perp;
    float3 nTable = float3(nxy, max(nz, 0.02));
    float lobes = UV2.y > 1.5 ? 2.0 : 1.0;
    float3 color = (float3)PIO_ShadeLiquid((half3)saturate(VertexColor.rgb), nTable, nz, lobes);

    // Optional extra sparkle for clear beads (pearls, droplets): the reflection of the key light's window, two small soft
    // panes side by side near the top of the dome as on the reference pearls (on a small droplet they merge into one
    // dot). nxy is the dome normal in world axes.
    float boost = saturate(UV2.z);
    float panes = PIO_BeadPane(nxy, float2(-0.25, 0.33), float2(0.8, 0.6)) + PIO_BeadPane(nxy, float2(0.02, 0.43), float2(1.0, -0.05));
    color += boost * 0.75 * saturate(panes) * beadA;

    // LIQ: the table's light bounced back into the lower-right rim of a bead (the reference pearl shows it as a thin
    // light crescent opposite the key highlight). Only on beads large enough to resolve it (about 5 px of radius).
    float rimR = length(qn);
    float rimAz = dot(nxy, float2(0.6, -0.8)) / max(rimR, 1e-4);
    float rimBand = (rimR - 0.86) * (1.0 / 0.06);
    float bounce = boost * 0.22 * exp(-rimBand * rimBand) * smoothstep(0.65, 0.97, rimAz) * smoothstep(5.0, 8.0, radiusPixels);
    color += bounce * lerp((float3)saturate(VertexColor.rgb), float3(1.0, 1.0, 1.0), 0.4) * beadA;

    // Soft shadow ellipse, centered at center - PIO_BEAD_SHADOW_SCALE x _PIO_ShadowOffset (lower right of the bead),
    // the reach and softness of the composite's drop shadows (LiquidComposite.hlsl PIO_SHADOW_SCALE).
    float2 offset = _PIO_ShadowOffset.xy;
    if (dot(offset, offset) < 1e-8) offset = float2(-0.072, 0.096);
    float2 ps = p + offset * PIO_BEAD_SHADOW_SCALE;
    float2 localS = float2(dot(ps, dir), dot(ps, perp));
    float ds = length(PIO_TearWarp(localS / (radii * 1.08), tear));
    float shadowA = saturate(UV2.x * 1.2) * (1.0 - smoothstep(0.35, 1.2, ds));

    // Safety fade at the quad border (QuadBatch.AddBead's extent), so no square edge can ever show.
    float ext = radius * max(stretch, 1.0 / stretch) * 1.08 + (UV2.x > 0.0 ? 0.12 + radius * 0.1 : 0.0) + 0.04;
    float border = saturate((ext - max(abs(p.x), abs(p.y))) / wpp - 0.5);

    // Shadow first, bead over it (the shadow is black: it multiplies what lies under it by 1 - alpha).
    float opacity = saturate(VertexColor.a);
    float bA = beadA * opacity;
    float sA = shadowA * opacity * border;
    float outA = bA + sA * (1.0 - bA);
    BaseColor = outA > 1e-5 ? color * (bA / outA) : float3(0.0, 0.0, 0.0);
    Alpha = outA;
}

void PIO_BeadSG_half(half4 VertexColor, half4 UV0, half4 UV1, half4 UV2, out half3 BaseColor, out half Alpha)
{
    float3 baseColor;
    float alpha;
    PIO_BeadSG_float((float4)VertexColor, (float4)UV0, (float4)UV1, (float4)UV2, baseColor, alpha);
    BaseColor = (half3)baseColor;
    Alpha = (half)alpha;
}

#endif // PIO_BEAD_INCLUDED
