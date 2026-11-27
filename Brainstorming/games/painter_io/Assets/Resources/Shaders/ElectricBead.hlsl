// ElectricBead.hlsl - Custom Function file of ElectricBead.shadergraph (docs/CONTRACT.md 25.4), owned by ELEC.
// Its .meta carries the fixed GUID faa893c44e6045f1b40ed0abffb7459b: ElectricBead.shadergraph references this file by
// that GUID.
//
// Same vertex data as Bead.hlsl (Actors/QuadBatch.AddBead), so every bead view works unchanged:
//   UV0.xy = world offset of the pixel from the bead center; UV1 = (radius, stretch along dir, dir.x, dir.y);
//   UV2 = (shadow strength, specular lobes, highlight boost, unused); vertex color = (linear albedo rgb, opacity).
// The graph also feeds the world position of the pixel (Position node, World), so center = WorldPos.xy - UV0.xy gives a
// stable per-bead seed. Transparent, Blend SrcAlpha OneMinusSrcAlpha, ZTest Always, ZWrite Off.
// - Pearls (radius > 0.3 u): a plasma orb. White-hot core, neon body brighter toward the shell, five crackling filaments
//   from the core to the shell (slowly rotating, jagged offset re-rolled at 18 Hz) and a colored glow halo outside the
//   disc (no drop shadow: the glow separates the orb from what lies under it).
// - Droplets, evaporating beads and splash drops (smaller): spark dots. A saturated core (at most 1.1 x the player
//   color, never white: wave C) in a colored glow that reaches the quad margin, flickering per bead (hash of the bead
//   center and a 22 Hz step); a stretched bead (splash drop) is a streak along its direction.
// Values above 1 feed the High-tier bloom (threshold 1.1).
#ifndef PIO_ELECTRIC_BEAD_INCLUDED
#define PIO_ELECTRIC_BEAD_INCLUDED

#include "Assets/Resources/Shaders/LiquidCommon.hlsl"

#define PIOE_BEAD_ORB_RADIUS 0.3
#define PIOE_DOT_PEAK 1.1             // brightest spark dot = 1.1 x the player color (never white, wave C)

float PIOE_BeadHash(float2 cell)
{
    uint2 q = (uint2)((int2)floor(cell) + 65536);
    uint h = (q.x * 1597334677u) ^ (q.y * 3812015801u);
    h = h * 0x9E3779B1u;
    h ^= h >> 16;
    h *= 0x85EBCA6Bu;
    h ^= h >> 13;
    return (float)h * (1.0 / 4294967296.0);
}

float PIOE_BeadNoise(float2 p)
{
    float2 i = floor(p);
    float2 f = p - i;
    f = f * f * (3.0 - 2.0 * f);
    float a = PIOE_BeadHash(i);
    float b = PIOE_BeadHash(i + float2(1.0, 0.0));
    float c = PIOE_BeadHash(i + float2(0.0, 1.0));
    float d = PIOE_BeadHash(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

void PIO_ElectricBeadSG_float(float4 VertexColor, float4 UV0, float4 UV1, float4 UV2, float3 WorldPos,
                              out float3 BaseColor, out float Alpha)
{
    float2 p = UV0.xy;
    float radius = max(UV1.x, 1e-4);
    float stretch = clamp(UV1.y, 0.25, 4.0);
    float2 dir = UV1.zw;
    float dirLength = length(dir);
    dir = dirLength > 1e-5 ? dir / dirLength : float2(1.0, 0.0);
    float2 perp = float2(-dir.y, dir.x);
    float2 radii = radius * float2(stretch, 1.0 / stretch);
    float wpp = max(max(fwidth(p.x), fwidth(p.y)), 1e-6);
    float time = _PIO_Time.x;

    float2 local = float2(dot(p, dir), dot(p, perp));
    float2 q = local / radii;
    float d = length(q);
    float3 col = saturate(VertexColor.rgb);
    float3 hot = lerp(col, float3(1.0, 1.0, 1.0), 0.8);
    float opacity = saturate(VertexColor.a);

    // The quad half extent written by QuadBatch.AddBead: every glow reaches zero before the quad border.
    float ext = radius * max(stretch, 1.0 / stretch) * 1.08 + (UV2.x > 0.0 ? 0.12 + radius * 0.1 : 0.0) + 0.04;
    float border = max(abs(p.x), abs(p.y));
    float edgeFade = saturate((ext - border) / max(0.3 * ext, 2.0 * wpp));
    float2 center = WorldPos.xy - p;

    float3 color;
    float alpha;
    if (radius > PIOE_BEAD_ORB_RADIUS)
    {
        // Plasma orb.
        float radiusPixels = min(radii.x, radii.y) / wpp;
        float discA = saturate((1.0 - d) * radiusPixels + 0.5);
        float seed = dot(col, float3(12.9898, 78.233, 37.719));
        float tq = floor(time * 18.0);
        float theta = atan2(q.y, q.x);
        // Four filaments from the core to the shell, at least about 1.5 px wide at the usual 30 px/u.
        float fil = 0.0;
        float minWidth = 1.4 * wpp;
        [unroll] for (int i = 0; i < 4; i++)
        {
            float fi = (float)i;
            float h0 = frac(sin(seed + fi * 7.13) * 43758.5453);
            float h1 = frac(sin(seed + fi * 3.71 + 1.3) * 24634.6345);
            float spin = (h1 > 0.5 ? 1.0 : -1.0) * (0.5 + h1);
            float baseAngle = (fi + 0.6 * h0) * 1.5707963 + time * spin;
            float wig = (PIOE_BeadNoise(float2(d * 4.0, tq * 0.73 + fi * 13.0 + seed)) - 0.5) * 1.8 * d;
            float ang = theta - (baseAngle + wig);
            ang -= 6.2831853 * round(ang / 6.2831853);
            float dist = abs(ang) * max(d, 0.05) * radius;
            float width = max(0.022 + 0.02 * (1.0 - d), minWidth);
            fil += exp(-dist * dist / (width * width)) * smoothstep(0.08, 0.3, d) * (1.0 - smoothstep(0.75, 1.0, d));
        }
        float flick = 0.9 + 0.1 * PIOE_BeadHash(float2(tq, seed));
        // A solid glowing ball (never a ring: the charge ring is the only ring drawn around a pearl), brighter shell.
        float core = exp(-d * d * 14.0);
        float shell = smoothstep(0.62, 0.96, d);
        float3 orb = col * (0.78 + 0.22 * (1.0 - d)) + col * shell * 0.45 + hot * shell * shell * 0.15;
        orb += hot * (saturate(fil) * 0.95 + core * 1.3) * flick;
        float g = exp(-max(d - 1.0, 0.0) * 4.5);
        float glowA = (1.0 - discA) * g * 0.6 * edgeFade;
        float outA = discA + glowA;
        color = outA > 1e-5 ? (orb * discA + col * 1.25 * glowA) / outA : col;
        alpha = outA;
    }
    else
    {
        // Spark dot (a streak when stretched): a saturated core in a colored glow, flickering per bead. Wave C: no white
        // core (it made every dead-cable dot clip to white like the current packet, contract 25.5: the packet must stay
        // the brightest moving thing); the dot peaks at PIOE_DOT_PEAK x the player color, so it keeps its hue on every
        // tier, with or without bloom.
        float tq = floor(time * 22.0);
        float beadSeed = PIOE_BeadHash(floor(center * 12.0) + 101.0);
        float f = PIOE_BeadHash(float2(tq, beadSeed * 977.0));
        float on = f > 0.28 ? 1.0 : 0.35;
        float core = exp(-d * d * 5.0);
        // Larger beads (the evaporating front bead, big splash drops) keep a tighter glow: a spark, not a smear.
        float glow = exp(-d * (1.7 + 5.0 * saturate((radius - 0.11) / 0.1)));
        color = col * min(PIOE_DOT_PEAK, core * PIOE_DOT_PEAK + glow * 1.15);
        float coreA = saturate((1.0 - d) * (min(radii.x, radii.y) / wpp) + 0.5);
        alpha = saturate(max(coreA * 0.9, glow * 0.8)) * edgeFade;
        color *= on;
        alpha *= lerp(0.55, 1.0, on);
    }
    BaseColor = max(color, 0.0);
    Alpha = saturate(alpha * opacity);
}

void PIO_ElectricBeadSG_half(half4 VertexColor, half4 UV0, half4 UV1, half4 UV2, half3 WorldPos, out half3 BaseColor,
                             out half Alpha)
{
    float3 baseColor;
    float alpha;
    PIO_ElectricBeadSG_float((float4)VertexColor, (float4)UV0, (float4)UV1, (float4)UV2, (float3)WorldPos, baseColor, alpha);
    BaseColor = (half3)baseColor;
    Alpha = (half)alpha;
}

#endif // PIO_ELECTRIC_BEAD_INCLUDED
