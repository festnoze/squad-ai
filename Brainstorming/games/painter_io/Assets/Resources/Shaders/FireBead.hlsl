// FireBead.hlsl - the Custom Function of FireBead.shadergraph (docs/CONTRACT.md 25.2, 25.3), owned by FIRE.
// Its .meta carries the fixed GUID f5a58eaf99134b9787685a65ada22d8e: FireBead.shadergraph references this file by that GUID.
//
// The Feu biome's bead impostors, with the SAME vertex data as Bead.hlsl (Actors/QuadBatch.cs AddBead):
//   UV0.xy = world offset of the pixel from the bead center; UV1 = (radius in u, stretch, dir.x, dir.y);
//   UV2 = (shadow strength, specular lobes, highlight boost, unused); vertex color = (linear player color, opacity).
// Fire emits light, so the shadow and gloss inputs are ignored. What a bead is follows from its radius and stretch:
// - radius >= 0.28 u: a pearl (or the pop of an eliminated pearl): a FIREBALL. A white-hot center in the player's hot
//   core color (_PIO_SecondaryColors of the player whose _PIO_Colors entry matches the vertex color), a body in the flame
//   color with a swirling texture, a flickering corona of flame tongues that rise toward screen up, and a soft glow.
// - smaller and stretched (> 1.04): a spark flying out of a burst (the splash drops of an elimination): a white-hot
//   streak along dir.
// - smaller and round: a glowing ember (the retraction droplet chain, the evaporating beads of a saved return). The
//   cooling of the burnt fuse to grey ash is drawn over the droplets by FireFx (FireOverlay shape 12), which knows the
//   age of each droplet.
// Every color is linear and may exceed 1 (bloom on High).
#ifndef PIO_FIRE_BEAD_INCLUDED
#define PIO_FIRE_BEAD_INCLUDED

#include "Assets/Resources/Shaders/LiquidCommon.hlsl"

float PIO_FireBeadHash(float2 cell)
{
    uint2 q = (uint2)((int2)cell + 65536);
    uint h = (q.x * 1597334677u) ^ (q.y * 3812015801u);
    h = h * 0x9E3779B1u;
    h ^= h >> 16;
    h *= 0x85EBCA6Bu;
    h ^= h >> 13;
    return (float)h * (1.0 / 4294967296.0);
}

float PIO_FireBeadNoise(float2 p)
{
    float2 i = floor(p);
    float2 f = p - i;
    f = f * f * (3.0 - 2.0 * f);
    float a = PIO_FireBeadHash(i);
    float b = PIO_FireBeadHash(i + float2(1.0, 0.0));
    float c = PIO_FireBeadHash(i + float2(0.0, 1.0));
    float d = PIO_FireBeadHash(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

// The hot core color of a flame color: the matching player's secondary color, else a white-hot tint of the flame.
float3 PIO_FireBeadHot(float3 flame)
{
    float3 hot = lerp(flame, float3(1.0, 0.92, 0.75), 0.6);
    float best = 0.004;
    [unroll] for (int i = 0; i < 4; i++)
    {
        float3 d = flame - _PIO_Colors[i].rgb;
        float e = dot(d, d);
        if (e < best)
        {
            best = e;
            hot = _PIO_SecondaryColors[i].rgb;
        }
    }
    return hot;
}

// Premultiplied "over": layer (c, a) over (cb, ab).
void PIO_FireBeadOver(float3 c, float a, inout float3 cb, inout float ab)
{
    float outA = a + ab * (1.0 - a);
    cb = outA > 1e-5 ? (c * a + cb * ab * (1.0 - a)) / outA : float3(0.0, 0.0, 0.0);
    ab = outA;
}

void PIO_FireBeadSG_float(float4 VertexColor, float4 UV0, float4 UV1, float4 UV2, out float3 BaseColor, out float Alpha)
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
    float2 local = float2(dot(p, dir), dot(p, perp));
    float2 q = local / radii;
    float d = length(q);
    float minPixels = min(radii.x, radii.y) / wpp;
    float opacity = saturate(VertexColor.a);
    float3 flame = saturate(VertexColor.rgb);
    float3 hot = PIO_FireBeadHot(flame);
    float time = _PIO_Time.x;
    float seed = frac(radius * 37.17 + flame.r * 3.1 + flame.g * 5.3 + flame.b * 1.7);

    float3 color = float3(0.0, 0.0, 0.0);
    float alpha = 0.0;
    float coreA = saturate((1.0 - d) * minPixels + 0.5);

    if (radius >= 0.28)
    {
        // ---- Fireball --------------------------------------------------------------------------------------------------
        float2 pw = p / radius;                     // world-oriented, unstretched (the corona rises toward screen up)
        float rho = length(pw);
        float upw = rho > 1e-4 ? saturate(0.5 + 0.5 * pw.y / rho) : 0.5;
        float n = PIO_FireBeadNoise(pw * 2.6 + float2(seed * 7.0, -time * 3.3)) * 0.65
                + PIO_FireBeadNoise(pw * 5.3 + float2(-seed * 3.0, -time * 5.2)) * 0.35;
        float reach = 1.06 + 0.4 * n * n * 1.3 * (0.45 + 0.95 * upw);
        // The quad reaches about 1.53 radii (QuadBatch margin): every layer fades out before its border.
        float coronaA = saturate((reach - rho) / 0.12) * 0.92 * saturate((1.52 - rho) * 8.0);
        float3 coronaCol = lerp(flame * 1.15, hot * 1.3, saturate((reach - rho) * 2.2));
        float glowA = 0.32 * exp(-max(rho - 0.95, 0.0) * 4.0) * saturate((1.52 - rho) * 5.0);

        float heat = saturate(1.0 - d * d);
        float flick = 0.9 + 0.1 * sin(time * 23.0 + seed * 40.0) * sin(time * 8.7 + seed * 17.0);
        float swirl = PIO_FireBeadNoise(q * 2.3 + float2(time * 0.9, -time * 2.2));
        // The body stays in the flame color (the player reads by it); only a small centre burns white hot. Wave C: the
        // hot core is a little less hot (hot x 1.3 stays below 235 luma without bloom) and the white centre smaller, so
        // the fuse spark (FireOverlay shape 3) stays the brightest moving thing on Medium and Low (contract 25.5).
        float3 body = lerp(flame * 1.2, hot * 1.3, smoothstep(0.45, 1.0, heat + 0.2 * (swirl - 0.5)));
        body = lerp(body, float3(1.6, 1.5, 1.3), smoothstep(0.93, 1.0, heat) * 0.4);
        body *= (0.84 + 0.32 * swirl) * flick;
        // A darker rim keeps the silhouette of the ball readable over a bright bed of its own color.
        body *= lerp(1.0, 0.72, smoothstep(0.78, 1.0, d));
        // Without bloom (Medium and Low: no bicubic tier) a light player color (yellow) would clip the hot core to near
        // white and outshine the spark: the luminance of the body and the corona is capped below the spark's white
        // (linear 0.7, about 215 luma), keeping their hue. High keeps its HDR core for the bloom.
        float lumCap = _PIO_Quality.z > 0.5 ? 1e4 : 0.7;
        float3 lumW = float3(0.2126, 0.7152, 0.0722);
        body *= min(1.0, lumCap / max(dot(body, lumW), 1e-4));
        coronaCol *= min(1.0, lumCap / max(dot(coronaCol, lumW), 1e-4));

        color = flame * 0.9;
        alpha = glowA;
        PIO_FireBeadOver(coronaCol, coronaA, color, alpha);
        PIO_FireBeadOver(body, coreA, color, alpha);
    }
    else if (stretch > 1.04)
    {
        // ---- Spark of a burst: a white-hot streak along dir -------------------------------------------------------------
        float streak = saturate(1.0 - d);
        float3 c = lerp(flame * 1.3, hot * 2.4, smoothstep(0.25, 0.85, streak));
        float glowA = 0.35 * exp(-max(d - 0.9, 0.0) * 3.5) * saturate((1.9 - d) * 3.0);
        color = flame;
        alpha = glowA;
        PIO_FireBeadOver(c, coreA, color, alpha);
    }
    else
    {
        // ---- Ember: a glowing coal ----------------------------------------------------------------------------------
        float heat = saturate(1.0 - d * d);
        float flick = 0.85 + 0.15 * sin(time * (17.0 + 9.0 * seed) + seed * 31.0);
        float spots = PIO_FireBeadNoise(q * 2.5 + seed * 13.0);
        float3 c = lerp(flame * 0.95, hot * 1.3, smoothstep(0.35, 1.0, heat)) * flick;
        c *= lerp(0.6, 1.0, smoothstep(0.3, 0.62, spots + heat * 0.4));
        float glowA = 0.26 * exp(-max(d - 0.9, 0.0) * 7.0) * saturate((1.3 - d) * 5.0);
        color = flame * 0.9;
        alpha = glowA;
        PIO_FireBeadOver(c, coreA, color, alpha);
    }

    BaseColor = color;
    Alpha = saturate(alpha * opacity);
}

void PIO_FireBeadSG_half(half4 VertexColor, half4 UV0, half4 UV1, half4 UV2, out half3 BaseColor, out half Alpha)
{
    float3 baseColor;
    float alpha;
    PIO_FireBeadSG_float((float4)VertexColor, (float4)UV0, (float4)UV1, (float4)UV2, baseColor, alpha);
    BaseColor = (half3)baseColor;
    Alpha = (half)alpha;
}

#endif // PIO_FIRE_BEAD_INCLUDED
