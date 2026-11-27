// ElectricOverlay.hlsl - Custom Function file of ElectricOverlay.shadergraph (docs/CONTRACT.md 25.4), owned by ELEC.
// Its .meta carries the fixed GUID 05cd1997f93447179224c05ccb3853da: ElectricOverlay.shadergraph references this file by
// that GUID.
//
// Same vertex data and shape ids as Overlay.hlsl (Actors/QuadBatch.AddOverlay), so every overlay view works unchanged:
//   UV0.xy = local shape coordinate (the quad spans [-1, 1]^2); UV0.z = world units per local unit (half size x);
//   UV0.w = 0 for quads (per-vertex level for the ElectricFx strips); UV1 = (shape id, a, b, c);
//   UV2 = (cos, sin of the local frame rotation, unused, specular lobes); vertex color = (linear rgb, opacity).
// Transparent, Blend SrcAlpha OneMinusSrcAlpha, ZTest Always, ZWrite Off. Values above 1 feed the High-tier bloom.
// Contract shapes, restyled as neon:
//   0 Ring    a = centerline radius, b = tube half width, c = shadow strength. Neon tube: white-hot core line, cool
//             glow, small arcs crawling along it (15 Hz), soft dark contact ring under it at _PIO_ShadowOffset.
//   1 Halo    a = radius of the glow peak, b = glow width, c = extra emission 0..1 (0 in the shared views). Soft glow.
//   2 Chevron a = arm half thickness, b = outline width, c = outline opacity. Neon chevron with a dark outline and glow;
//             its fill gets no boost above the cool-tinted albedo and is capped at PIOE_CHEVRON_MAX (wave C: it read as
//             white beside the packet).
//   3 Glint   a = core size, b = ray length, c = ray half width. Electric spark star with jagged flickering rays and a
//             solid white center of 0.1 u (world) in a white-blue core that stays below white (LDR-safe, wave C).
//   4 Flash   a = ring radius, b = band half width, c = glow strength. Crackling lightning ring (cut flash).
//   5 Disc    a = radius. Flat antialiased disc.
// ElectricFx shapes (ELEC's own effects, never sent by the shared views):
//   6 Bolt    a = seed, b = aspect (half size y / half size x), c = core half width (world). A lightning bolt from local
//             x = -1 to x = +1 (jagged path re-rolled at 20 Hz, pinned at both ends) with one fading branch.
//   7 Cable   strip mesh: UV0.y = cross coordinate [-1, 1], UV0.z = half width (world), UV0.w = level 0..1. Dim cable.
//   8 Glow    strip mesh, same layout as Cable: a glow ribbon with a white core (the current packet's tail).
//   9 Spark   a = intensity. A spark streaking toward local +x (head at x = 0.55).
//  10 Packet  a = intensity. The current packet: a white-blue hot head at local x = 0.3 in an elongated glow that
//             falls off faster ahead of the head (local x > 0.3) than behind it.
// Trait shapes (wave D-2 traits-fx, same ids and parameters as Overlay.hlsl, drawn by Actors/TraitFxView.cs), as neon:
//  16 Streak  a plasma streak with a jagged filament behind an orb running on its own territory (Conduction).
//  17 Arc     a small lightning arc between a head and the exposed wire it could cut (ArcReach).
//  18 Aura    a crackling neon ring around the orb, wider and brighter per speed level (KillSpeedBoost).
//  19 Film    a force field: a neon rim with faint hexagons inside (KillShield).
//  20 Timer   a small neon ring draining clockwise.
//  21 Shimmer current pulses running along a shielded wire (strip mesh).
// Every trait shape stays below sRGB luma 235 without bloom (the current packet stays the brightest moving thing).
#ifndef PIO_ELECTRIC_OVERLAY_INCLUDED
#define PIO_ELECTRIC_OVERLAY_INCLUDED

#include "Assets/Resources/Shaders/LiquidCommon.hlsl"

#define PIOE_GLINT_WHITE 0.1                     // world radius of the solid white center of the spark star (shape 3)
#define PIOE_GLINT_CENTER 1.6                    // its value: white without bloom, above the 1.1 bloom threshold on High
#define PIOE_GLINT_BLUE float3(0.30, 0.62, 1.0)  // saturated white-blue around it (stays below white, luma < 235)
#define PIOE_PACKET_AHEAD 2.25                   // packet head: forward falloff factor, (1.5 x quad size)^2
#define PIOE_CHEVRON_MAX 0.8                     // chevron fill cap, linear (sRGB luma about 231: never reads as white)

float PIOE_OvHash(float2 cell)
{
    uint2 q = (uint2)((int2)floor(cell) + 65536);
    uint h = (q.x * 1597334677u) ^ (q.y * 3812015801u);
    h = h * 0x9E3779B1u;
    h ^= h >> 16;
    h *= 0x85EBCA6Bu;
    h ^= h >> 13;
    return (float)h * (1.0 / 4294967296.0);
}

float PIOE_OvNoise(float2 p)
{
    float2 i = floor(p);
    float2 f = p - i;
    f = f * f * (3.0 - 2.0 * f);
    float a = PIOE_OvHash(i);
    float b = PIOE_OvHash(i + float2(1.0, 0.0));
    float c = PIOE_OvHash(i + float2(0.0, 1.0));
    float d = PIOE_OvHash(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

float PIOE_OvSegmentDistance(float2 p, float2 a, float2 b)
{
    float2 ab = b - a;
    float t = saturate(dot(p - a, ab) / max(dot(ab, ab), 1e-8));
    return length(p - (a + ab * t));
}

// Jagged bolt offset along x (world units), pinned at both ends of [-1, 1] (local x).
float PIOE_BoltPath(float xw, float lx, float seed, float tq, float amplitude)
{
    float n = (PIOE_OvNoise(float2(xw * 2.2 + seed * 17.0, tq * 1.37 + seed)) - 0.5)
            + 0.5 * (PIOE_OvNoise(float2(xw * 6.5 - seed * 5.0, tq * 2.11 - seed)) - 0.5)
            + 0.25 * (PIOE_OvNoise(float2(xw * 15.0 + seed * 3.0, tq * 3.3)) - 0.5);
    float pin = sqrt(saturate(1.0 - lx * lx));
    return n * amplitude * pin;
}

float PIOE_OvSq(float x)
{
    return x * x;
}

// Wave D-2 trait shapes as neon: the cool white-blue of their cores, capped below sRGB luma 235.
#define PIOE_TRAIT_CORE float3(0.56, 0.72, 0.80)

// Wave D-2 trait shapes (16 - 21) of the electric biome (header). Returns (rgb, alpha before opacity). wppX = world
// units per pixel along local x (taken by the caller outside any branch).
float4 PIOE_OverlayTrait(float shape, float2 q, float4 uv0, float4 p, float2 cs, float3 albedo, float aa, float wppX)
{
    float time = _PIO_Time.x;
    float unitsPerLocal = max(uv0.z, 1e-4);
    float rho = length(q);
    float3 neon = min(albedo * 1.1, float3(1.0, 1.0, 1.0));
    float3 color = neon;
    float alpha = 0.0;
    if (shape < 16.5)
    {
        // Streak: a neon plasma streak with a jagged white-blue filament down its middle (17 Hz).
        float k = saturate(p.y);
        float u = q.x * 0.5 + 0.5;
        float wv = 0.16 + 0.84 * pow(saturate(u), 0.7);
        float body = exp(-(q.y * q.y) / (wv * wv * 0.28)) * smoothstep(0.0, 0.4, u) * (1.0 - smoothstep(0.88, 1.0, u));
        float tq = floor(time * 17.0 + p.w * 5.0);
        float jag = (PIOE_OvNoise(float2(q.x * 6.0 + tq * 3.1, tq)) - 0.5) * 0.5 * wv;
        float fil = exp(-PIOE_OvSq((q.y - jag) / max(0.08 * wv, 0.025))) * smoothstep(0.1, 0.65, u) * (1.0 - smoothstep(0.88, 1.0, u));
        color = lerp(lerp(neon, PIOE_TRAIT_CORE, 0.2), PIOE_TRAIT_CORE, saturate(fil));
        alpha = k * saturate(0.5 * body + 0.85 * fil);
    }
    else if (shape < 17.5)
    {
        // Arc: a small lightning arc, pinned at both ends, re-rolled at 20 Hz, with a short fading branch.
        float seed = p.y;
        float lx = q.x * (1.0 / 0.88);
        float halfX = unitsPerLocal * 0.88;
        float halfY = unitsPerLocal * max(p.z, 1e-3);
        float yw = q.y * halfY;
        float tq = floor(time * 20.0 + seed * 10.0);
        float lc = clamp(lx, -1.0, 1.0);
        float path = ((PIOE_OvNoise(float2(lc * 2.6 + seed * 17.0, tq * 1.37 + seed)) - 0.5)
                    + 0.6 * (PIOE_OvNoise(float2(lc * 6.5 - seed * 5.0, tq * 2.11 - seed)) - 0.5)
                    + 0.3 * (PIOE_OvNoise(float2(lc * 15.0 + seed * 3.0, tq * 3.3)) - 0.5)) * halfY * sqrt(saturate(1.0 - lc * lc));
        float cw = max(p.w, wppX * 0.7);
        float dist = abs(yw - path);
        float core = exp(-dist * dist / (cw * cw));
        float glow = exp(-dist / (cw * 4.5));
        float ends = 1.0 - smoothstep(0.96, 1.04, abs(lx));
        float2 wq = float2(q.x * unitsPerLocal, yw);
        float contact = exp(-dot(wq - float2(halfX, 0.0), wq - float2(halfX, 0.0)) / 0.0036)
                      + exp(-dot(wq + float2(halfX, 0.0), wq + float2(halfX, 0.0)) / 0.0036);
        color = lerp(neon, PIOE_TRAIT_CORE, saturate(core * 1.3 + contact));
        alpha = saturate(saturate(core + 0.55 * glow) * ends + 0.8 * contact) * (1.0 - smoothstep(0.8, 1.0, abs(q.y)));
    }
    else if (shape < 18.5)
    {
        // Aura: a crackling neon ring around the orb, jag re-rolled at 15 Hz, wider and brighter per level.
        float level = max(p.y, 0.0);
        float rim = max(p.z, 0.05);
        float ang = atan2(q.y, q.x);
        float tq = floor(time * 15.0);
        float r1 = rim + 0.08 + 0.04 * min(level, 3.0);
        float jag = (PIOE_OvNoise(float2(ang * 6.0 + tq * 2.3, tq * 0.7)) - 0.5) * 0.09;
        float crackle = exp(-PIOE_OvSq((rho - r1 + jag) / 0.022));
        float seg = smoothstep(0.35 - 0.08 * min(level, 3.0), 0.6, PIOE_OvNoise(float2(ang * 2.0 - time * 2.0, level)));
        float glowR = exp(-PIOE_OvSq((rho - r1) / (0.07 + 0.03 * min(level, 3.0)))) * step(rim * 0.85, rho);
        float burst = saturate(p.w) * exp(-PIOE_OvSq((rho - rim - 0.35 * (1.0 - p.w)) / 0.08));
        color = lerp(neon, PIOE_TRAIT_CORE, saturate(crackle * seg + burst));
        alpha = saturate((0.14 + 0.08 * min(level, 3.0)) * glowR + 0.85 * crackle * seg + 0.7 * burst);
    }
    else if (shape < 19.5)
    {
        // Film: a force field, a neon rim with faint hexagons inside that flicker.
        float r0 = max(p.y, 0.1);
        float rr = rho / r0;
        float inside = saturate((1.0 - rr) * r0 / aa + 0.5);
        float rimG = pow(saturate(rr), 6.0);
        float2 hq = q * (4.5 / r0);
        float2 hp = abs(frac(float2(hq.x, hq.y * 0.57735 + hq.x * 0.5)) - 0.5);
        float hexL = 1.0 - smoothstep(0.0, 0.08, min(hp.x, hp.y));
        float flick = 0.7 + 0.3 * step(0.4, PIOE_OvNoise(float2(floor(time * 12.0), 3.0)));
        float pop = saturate(p.w);
        color = lerp(neon, PIOE_TRAIT_CORE, saturate(0.3 * rimG + 0.4 * pop));
        alpha = inside * saturate(0.05 + 0.6 * rimG * flick + 0.18 * hexL * smoothstep(0.3, 0.9, rr) * saturate(p.z + 0.5) + 0.5 * pop * rimG);
    }
    else if (shape < 20.5)
    {
        // Timer: a small neon ring draining clockwise from 12 o'clock over a dim track.
        float r0 = p.y;
        float hw = max(p.z, 1e-3);
        float frac01 = saturate(p.w);
        float band = saturate((hw - abs(rho - r0)) / aa + 0.5);
        float a01 = frac(0.25 - atan2(q.y, q.x) / 6.2831853 + 1.0);
        float onArc = saturate((frac01 - a01) * 6.2831853 * r0 / aa + 0.5);
        float core = exp(-PIOE_OvSq((rho - r0) / (hw * 0.5)));
        color = lerp(neon * 0.25, lerp(neon, PIOE_TRAIT_CORE, core * 0.6), onArc);
        alpha = band * lerp(0.4, 1.0, onArc);
    }
    else
    {
        // Shimmer (strip): pulses of current running along the shielded wire over a faint cool sheen.
        float k = saturate(p.y);
        float y = uv0.y;
        float s = uv0.w;
        float body = exp(-y * y * 2.5);
        float g = frac(s * (1.0 / 0.8) - time * 3.0);
        float pulse = exp(-PIOE_OvSq((g - 0.5) / 0.14)) * exp(-y * y * 9.0);
        float tq = floor(time * 15.0);
        float jag = (PIOE_OvNoise(float2(s * 6.0 + tq * 3.1, tq)) - 0.5) * 0.9;
        float filament = exp(-PIOE_OvSq((y - jag) / 0.12)) * (0.6 + 0.4 * PIOE_OvNoise(float2(s * 5.0, tq + 7.0)));
        color = lerp(neon, PIOE_TRAIT_CORE, saturate(0.3 + pulse + 0.5 * filament));
        alpha = k * saturate(0.15 * body + 0.45 * filament + 0.9 * pulse) * (1.0 - smoothstep(0.75, 1.0, abs(y)));
    }
    return float4(color, alpha);
}

void PIO_ElectricOverlaySG_float(float4 VertexColor, float4 UV0, float4 UV1, float4 UV2, out float3 BaseColor, out float Alpha)
{
    float2 q = UV0.xy;
    float unitsPerLocal = max(UV0.z, 1e-4);
    float shape = UV1.x;
    float2 cs = UV2.xy;
    float csLength = length(cs);
    cs = csLength > 1e-5 ? cs / csLength : float2(1.0, 0.0);
    float opacity = saturate(VertexColor.a);
    float3 albedo = saturate(VertexColor.rgb);
    float time = _PIO_Time.x;
    float3 cool = float3(0.72, 0.90, 1.0);

    float rho = length(q);
    float aa = max(fwidth(rho), 1e-5);
    float border = saturate((1.0 - rho) / aa + 0.5);
    // World units per pixel along local x (orthographic camera: the gradient length is rotation-invariant).
    float wppX = length(float2(ddx(q.x), ddy(q.x))) * unitsPerLocal;
    float aaY = max(fwidth(q.y), 1e-5);

    float3 color = albedo;
    float alpha = 0.0;

    if (shape > 15.5)
    {
        // Wave D-2 trait shapes (header).
        float4 trait = PIOE_OverlayTrait(shape, q, UV0, UV1, cs, albedo, aa, wppX);
        color = trait.rgb;
        alpha = trait.a * border;
    }
    else if (shape < 0.5)
    {
        // Ring: neon tube with crawling arcs and a soft dark contact ring.
        float r0 = UV1.y;
        float w = max(UV1.z, 1e-4);
        float dr = (rho - r0) / w;
        float tube = saturate((1.0 - abs(dr)) * w / aa + 0.5);
        float core = exp(-dr * dr * 9.0);
        float glow = exp(-dr * dr * 0.8) * saturate((1.0 - rho) * 6.0);
        float ang = atan2(q.y, q.x);
        float tq = floor(time * 15.0);
        float n = PIOE_OvNoise(float2(ang * 4.0 + tq * 3.1, tq * 0.7)) - 0.5;
        float arcSeg = step(0.55, PIOE_OvNoise(float2(ang * 1.6 - time * 1.3, 4.0)));
        float arc = exp(-(dr + n * 2.4) * (dr + n * 2.4) * 25.0) * arcSeg;
        float3 tint = lerp(albedo, cool, 0.35);
        float3 neon = tint * (0.85 + 1.5 * core) + cool * arc * 1.6;

        float2 offset = _PIO_ShadowOffset.xy;
        if (dot(offset, offset) < 1e-8) offset = float2(-0.072, 0.096);
        float2 offsetLocal = float2(offset.x * cs.x + offset.y * cs.y, -offset.x * cs.y + offset.y * cs.x) / unitsPerLocal;
        float drs = (length(q + offsetLocal) - r0) / (w * 1.5);
        float shadowA = saturate(UV1.w) * 0.6 * (1.0 - smoothstep(0.4, 1.3, abs(drs)));

        float bodyA = saturate(max(tube, arc * 0.9));
        float glowA = glow * 0.45 * (1.0 - bodyA);
        float lightA = bodyA + glowA;
        float3 light = lightA > 1e-5 ? (neon * bodyA + tint * 1.2 * glowA) / lightA : tint;
        float outA = lightA + shadowA * (1.0 - lightA);
        color = outA > 1e-5 ? light * (lightA / outA) : float3(0.0, 0.0, 0.0);
        alpha = outA * border;
    }
    else if (shape < 1.5)
    {
        // Halo: soft glow peaking at radius a; c (0 in the shared views) raises its emission for ElectricFx glows.
        float r0 = UV1.y;
        float w = max(UV1.z, 1e-4);
        float x = (rho - r0) / w;
        color = albedo * (1.2 + 2.0 * saturate(UV1.w));
        alpha = exp(-x * x) * saturate((1.0 - rho) * 4.0);
    }
    else if (shape < 2.5)
    {
        // Neon chevron pointing toward local +x: bright fill, dark outline for contrast, soft glow.
        float t = max(UV1.y, 1e-4);
        float ow = max(UV1.z, 0.0);
        float d = min(PIOE_OvSegmentDistance(q, float2(-0.26, 0.4), float2(0.45, 0.0)),
                      PIOE_OvSegmentDistance(q, float2(0.45, 0.0), float2(-0.26, -0.4)));
        float aq = max(fwidth(d), 1e-5);
        float fillA = saturate((t - d) / aq + 0.5);
        float lineA = saturate((t + ow - d) / aq + 0.5) * saturate(UV1.w);
        float glowA = exp(-max(d - t - ow, 0.0) * 9.0) * 0.35 * (1.0 - smoothstep(0.75, 1.0, rho));
        float3 navy = float3(0.004, 0.006, 0.018);
        // Wave C (actors request, contract 25.5): no boost above the cool-tinted albedo (it used to be 1.15 to 1.4 x) and a
        // cap at PIOE_CHEVRON_MAX, so the off-white home chevron (linear 0.78) no longer turns white beside the packet.
        float3 fill = min(lerp(albedo, cool, 0.25) * (0.88 + 0.12 * saturate(0.5 + 0.6 * q.y)), PIOE_CHEVRON_MAX);
        float solidA = fillA + lineA * (1.0 - fillA);
        float3 solid = solidA > 1e-5 ? (fill * fillA + navy * lineA * (1.0 - fillA)) / solidA : fill;
        float outA = solidA + glowA * (1.0 - solidA);
        color = outA > 1e-5 ? (solid * solidA + cool * glowA * (1.0 - solidA)) / outA : fill;
        alpha = outA * border;
    }
    else if (shape < 3.5)
    {
        // Electric spark star: the glint on the current packet's head (RetractionView; quad half size 0.5 u from wave C)
        // and the short-circuit burst. LDR-safe (Medium, Low and every Android tier have no bloom, so anything above 1
        // just clips to white): a solid white center of radius PIOE_GLINT_WHITE world units, then a saturated white-blue
        // core and jagged flickering rays that both stay below white, so the center reads as the hottest point on every
        // tier. Only the center goes above 1, for the High-tier bloom (threshold 1.1).
        float c = max(UV1.y, 1e-4);
        float len = max(UV1.z, 1e-4);
        float rw = max(UV1.w, 1e-4);
        float tq = floor(time * 24.0);
        float jagX = 0.55 + 0.9 * PIOE_OvNoise(float2(q.x * 9.0 + tq * 5.3, tq));
        float jagY = 0.55 + 0.9 * PIOE_OvNoise(float2(q.y * 9.0 - tq * 4.1, tq + 7.0));
        float core = exp(-rho * rho / (c * c));
        float rx = exp(-abs(q.x) / len) * exp(-(q.y * q.y) / (rw * rw * jagX * jagX));
        float ry = exp(-abs(q.y) / len) * exp(-(q.x * q.x) / (rw * rw * jagY * jagY));
        float2 qd = float2(q.x + q.y, q.x - q.y) * 0.70710678;
        float rd = 0.45 * max(exp(-abs(qd.x) / (len * 0.6)) * exp(-(qd.y * qd.y) / (rw * rw * 0.5)),
                              exp(-abs(qd.y) / (len * 0.6)) * exp(-(qd.x * qd.x) / (rw * rw * 0.5)));
        float white = saturate((PIOE_GLINT_WHITE / unitsPerLocal - rho) / aa + 0.5);
        float3 blue = lerp(albedo, PIOE_GLINT_BLUE, 0.75) * (0.85 + 0.25 * core);
        color = lerp(blue, float3(PIOE_GLINT_CENTER, PIOE_GLINT_CENTER, PIOE_GLINT_CENTER), white);
        alpha = saturate(max(white, core + 0.85 * max(max(rx, ry), rd))) * saturate((1.0 - rho) * 3.0);
    }
    else if (shape < 4.5)
    {
        // Crackling lightning ring with a soft glow.
        float r0 = UV1.y;
        float w = max(UV1.z, 1e-4);
        float ang = atan2(q.y, q.x);
        float tq = floor(time * 20.0);
        float jag = (PIOE_OvNoise(float2(ang * 11.0 + tq * 2.7, tq * 0.9)) - 0.5) * w * 2.6
                  + (PIOE_OvNoise(float2(ang * 29.0 - tq * 1.9, tq * 1.3 + 5.0)) - 0.5) * w * 1.4;
        float dj = rho + jag - r0;
        float band = saturate((w * 0.8 - abs(dj)) / aa + 0.5);
        float x = (rho - r0) / (w * 4.0);
        float glow = saturate(UV1.w) * exp(-x * x);
        color = lerp(albedo, cool, 0.5) * (1.0 + 1.2 * band);
        alpha = saturate(band + glow) * border;
    }
    else if (shape < 5.5)
    {
        // Disc.
        alpha = saturate((UV1.y - rho) / aa + 0.5) * border;
    }
    else if (shape < 6.5)
    {
        // Bolt from local x = -1 to +1.
        float seed = UV1.y;
        float aspect = max(UV1.z, 1e-3);
        float coreW = max(UV1.w, 1e-4);
        float halfY = unitsPerLocal * aspect;
        float xw = q.x * unitsPerLocal;
        float yw = q.y * halfY;
        float tq = floor(time * 20.0 + seed * 10.0);
        float amp = 0.7 * halfY;
        float path = PIOE_BoltPath(xw, q.x, seed, tq, amp);
        float cw = max(coreW, wppX * 0.7);
        float dist = abs(yw - path);
        float core = exp(-dist * dist / (cw * cw));
        float glow = exp(-dist / (cw * 5.0));
        // One branch leaves the bolt at x0 and drifts away while it fades.
        float x0 = -0.2 + 0.4 * frac(seed * 7.31);
        float side = frac(seed * 3.17) > 0.5 ? 1.0 : -1.0;
        float u = saturate((q.x - x0) / max(1.0 - x0, 1e-3));
        float branchPath = path + side * u * 0.55 * halfY
                         + (PIOE_OvNoise(float2(xw * 7.0 + seed * 11.0, tq * 1.7)) - 0.5) * 0.3 * halfY * u;
        float bd = abs(yw - branchPath);
        float branch = q.x > x0 ? exp(-bd * bd / (cw * cw * 0.5)) * (1.0 - u) * 0.8 : 0.0;
        float ends = 1.0 - smoothstep(0.93, 1.0, abs(q.x));
        float sideFade = 1.0 - smoothstep(0.8, 1.0, abs(q.y));
        float3 hot = lerp(albedo, float3(1.0, 1.0, 1.0), 0.75);
        float c = saturate(core + branch);
        color = hot * 2.2 * c + albedo * 1.3 * (1.0 - c);
        alpha = saturate(c + glow * 0.55) * ends * sideFade;
    }
    else if (shape < 7.5)
    {
        // Cable strip: dim grey with a faint center sheen.
        float level = saturate(UV0.w);
        float body = saturate((1.0 - abs(q.y)) / aaY + 0.5);
        color = albedo * (0.75 + 0.45 * exp(-q.y * q.y * 6.0));
        alpha = body * level;
    }
    else if (shape < 8.5)
    {
        // Glow ribbon with a white core (the packet's tail).
        float level = saturate(UV0.w);
        float core = exp(-q.y * q.y * 22.0);
        float glow = exp(-q.y * q.y * 3.0) * (1.0 - q.y * q.y);
        color = albedo * 1.3 + cool * core * 1.8 * level;
        alpha = saturate(glow * 0.85 + core * 0.5) * level;
    }
    else if (shape < 9.5)
    {
        // Spark streaking toward local +x.
        float intensity = max(UV1.y, 0.0);
        float hx = q.x - 0.55;
        float head = exp(-(hx * hx * 30.0 + q.y * q.y * 70.0));
        float trail = exp(-q.y * q.y * 45.0) * smoothstep(-1.0, 0.55, q.x) * (q.x < 0.55 ? 1.0 : exp(-hx * hx * 60.0));
        float3 hot = lerp(albedo, float3(1.0, 1.0, 1.0), 0.7);
        color = hot * (1.2 + 1.4 * head) * intensity;
        alpha = saturate(head + trail * 0.75) * border;
    }
    else
    {
        // Current packet: white-blue hot head in an elongated glow (the tail behind it is a Glow strip). Wave C: ElectricFx
        // draws the quad 1.5 x larger; ahead of the head (hx > 0) the core and the glow fall off 1.5 x faster in local
        // units, so they reach exactly as far past the front in world units as before (the head never runs past the
        // front, V7) while the head grows backward along the wire.
        float intensity = max(UV1.y, 0.0);
        float hx = q.x - 0.3;
        float ahead = hx > 0.0 ? PIOE_PACKET_AHEAD : 1.0;
        float core = exp(-(hx * hx * 16.0 * ahead + q.y * q.y * 16.0));
        float glow = exp(-(hx * hx * 2.4 * ahead + q.y * q.y * 4.5));
        color = cool * 3.0 * core * intensity + albedo * 1.3 * (1.0 - core);
        alpha = saturate(core + glow * 0.75) * border;
    }

    BaseColor = max(color, 0.0);
    Alpha = saturate(alpha * opacity);
}

void PIO_ElectricOverlaySG_half(half4 VertexColor, half4 UV0, half4 UV1, half4 UV2, out half3 BaseColor, out half Alpha)
{
    float3 baseColor;
    float alpha;
    PIO_ElectricOverlaySG_float((float4)VertexColor, (float4)UV0, (float4)UV1, (float4)UV2, baseColor, alpha);
    BaseColor = (half3)baseColor;
    Alpha = (half)alpha;
}

#endif // PIO_ELECTRIC_OVERLAY_INCLUDED
