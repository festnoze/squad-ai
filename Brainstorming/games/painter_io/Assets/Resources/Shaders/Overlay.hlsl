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
// Trait shapes (wave D-2 traits-fx, docs/BIOME_TRAITS.md 5 and 7.2; shared by every biome overlay shader with the same
// parameters, drawn by Actors/TraitFxView.cs; each biome styles them):
//  16 Streak  a = intensity 0..1, b = aspect (half size y / half size x), c = seed. Conduction speed streak behind a
//             pearl: the quad's local +x points along the motion, the pearl rim at x = +1, the tail at x = -1.
//  17 Arc     a = seed, b = aspect, c = core half width (world). ArcReach spark line from local x = -1 (the head) to
//             x = +1 (the exposed trail point): a jagged flickering filament pinned at both ends.
//  18 Aura    a = speed level (1 per KillSpeedBoost kill, continuous), b = pearl rim radius (local), c = burst 0..1.
//             A glow ring around the pearl that grows with the level, with level orbiting glints.
//  19 Film    a = film radius (local), b = shimmer 0..1, c = pop 0..1. KillShield: a glossy film around the pearl.
//  20 Timer   a = radius (local), b = tube half width (local), c = remaining fraction 0..1. Small ring draining
//             clockwise from 12 o'clock (draw it unrotated).
//  21 Shimmer strip mesh along a shielded trail: UV0.x = 0, UV0.y = cross coordinate [-1, 1], UV0.z = half width
//             (world), UV0.w = arc length (world); a = intensity. Glints running along an uncuttable trail.
// Readability (contract 25.5): every trait shape stays below sRGB luma 235, so the chase front stays the brightest.
#ifndef PIO_OVERLAY_INCLUDED
#define PIO_OVERLAY_INCLUDED

#include "Assets/Resources/Shaders/LiquidCommon.hlsl"

#define PIO_OV_WHITE 0.78              // wave D-2: the whitest a trait shape gets (linear, about sRGB 229)

float PIO_OvSq(float x)
{
    return x * x;
}

// Integer hash of a lattice point and value noise (wave D-2 trait shapes).
float PIO_OverlayHash(float2 cell)
{
    uint2 q = (uint2)((int2)floor(cell) + 65536);
    uint h = (q.x * 1597334677u) ^ (q.y * 3812015801u);
    h = h * 0x9E3779B1u;
    h ^= h >> 16;
    h *= 0x85EBCA6Bu;
    h ^= h >> 13;
    return (float)h * (1.0 / 4294967296.0);
}

float PIO_OverlayNoise(float2 p)
{
    float2 i = floor(p);
    float2 f = p - i;
    f = f * f * (3.0 - 2.0 * f);
    float a = PIO_OverlayHash(i);
    float b = PIO_OverlayHash(i + float2(1.0, 0.0));
    float c = PIO_OverlayHash(i + float2(0.0, 1.0));
    float d = PIO_OverlayHash(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

// Wave D-2 trait shapes (16 - 21) of the liquid biome: glossy paint and glass. Returns (rgb, alpha before opacity).
float4 PIO_OverlayTrait(float shape, float2 q, float4 uv0, float4 p, float2 cs, float3 albedo, float aa, float lobes)
{
    float time = _PIO_Time.x;
    float unitsPerLocal = max(uv0.z, 1e-4);
    float rho = length(q);
    float3 white = float3(PIO_OV_WHITE, PIO_OV_WHITE, PIO_OV_WHITE);
    float3 color = albedo;
    float alpha = 0.0;
    if (shape < 16.5)
    {
        // Streak: a wet comet tail in the pearl's color with a white sheen line and two thin speed lines.
        float k = saturate(p.y);
        float u = q.x * 0.5 + 0.5;                                 // 0 at the tail, 1 at the pearl rim
        float wv = 0.18 + 0.82 * pow(saturate(u), 0.7);
        float head = 1.0 - smoothstep(0.88, 1.0, u);
        float body = exp(-(q.y * q.y) / (wv * wv * 0.3)) * smoothstep(0.0, 0.4, u) * head;
        float sheen = exp(-(q.y + 0.15 * wv) * (q.y + 0.15 * wv) / (wv * wv * 0.025)) * smoothstep(0.2, 0.75, u);
        float dash = smoothstep(0.35, 0.65, frac(u * 2.0 + time * 3.0 + p.w));
        float lines = (exp(-PIO_OvSq((q.y - 0.6 * wv) / 0.08)) + exp(-PIO_OvSq((q.y + 0.6 * wv) / 0.08))) * dash * smoothstep(0.05, 0.6, u);
        color = lerp(albedo, white, saturate(0.45 + 0.5 * sheen + 0.4 * lines));
        alpha = k * saturate(0.6 * body + 0.35 * sheen * body + 0.45 * lines * head);
    }
    else if (shape < 17.5)
    {
        // Arc: a thin bright tension filament with a soft colored glow, jag re-rolled at 18 Hz, a bright contact point
        // at each end. The arc spans local x in [-0.88, 0.88] (TraitFxView sizes the quad so), inside the quad's round
        // border fade. Its kinks are laid out along the arc (a short arc still has a few).
        float seed = p.y;
        float lx = q.x * (1.0 / 0.88);
        float halfX = unitsPerLocal * 0.88;
        float halfY = unitsPerLocal * max(p.z, 1e-3);
        float yw = q.y * halfY;
        float tq = floor(time * 18.0 + seed * 7.0);
        float lc = clamp(lx, -1.0, 1.0);
        float path = ((PIO_OverlayNoise(float2(lc * 2.6 + seed * 17.0, tq * 1.37)) - 0.5)
                    + 0.6 * (PIO_OverlayNoise(float2(lc * 6.5 - seed * 5.0, tq * 2.11)) - 0.5)) * halfY * sqrt(saturate(1.0 - lc * lc));
        float cw = max(p.w, 0.012);
        float dist = abs(yw - path);
        float core = exp(-dist * dist / (cw * cw));
        float glow = exp(-dist / (cw * 4.0));
        float ends = 1.0 - smoothstep(0.96, 1.04, abs(lx));
        float2 wq = float2(q.x * unitsPerLocal, yw);
        float contact = exp(-dot(wq - float2(halfX, 0.0), wq - float2(halfX, 0.0)) / 0.0036)
                      + exp(-dot(wq + float2(halfX, 0.0), wq + float2(halfX, 0.0)) / 0.0036);
        color = lerp(albedo, white, saturate(core * 1.2 + contact));
        alpha = saturate(saturate(core + 0.45 * glow) * ends + 0.8 * contact) * (1.0 - smoothstep(0.8, 1.0, abs(q.y)));
    }
    else if (shape < 18.5)
    {
        // Aura: a glossy halo of the color around the pearl, wider and stronger per level, with level orbiting glints.
        float level = max(p.y, 0.0);
        float rim = max(p.z, 0.05);
        float wl = 0.1 + 0.06 * min(level, 3.0);
        float x = (rho - rim) / wl;
        float glow = exp(-x * x) * step(rim * 0.8, rho);
        float ang = atan2(q.y, q.x);
        float n = max(1.0, floor(level + 0.5));
        float orbit = frac((ang / 6.2831853 + 0.5) * n - time * 0.7);
        float glint = exp(-PIO_OvSq((orbit - 0.5) / 0.06)) * exp(-PIO_OvSq((rho - rim - wl * 0.7) / (wl * 0.35)));
        float burst = saturate(p.w) * exp(-PIO_OvSq((rho - rim - 0.35 * (1.0 - p.w)) / 0.08));
        color = lerp(albedo, white, saturate(0.2 + 0.7 * glint + 0.5 * burst));
        alpha = saturate((0.16 + 0.1 * min(level, 3.0)) * glow + 0.75 * glint + 0.7 * burst);
    }
    else if (shape < 19.5)
    {
        // Film: a glossy soap film around the pearl (Fresnel rim, a window highlight on the upper left, a faint
        // iridescent tint that drifts), slightly wobbling.
        float r0 = max(p.y, 0.1);
        float ang = atan2(q.y, q.x);
        float wob = 1.0 + 0.025 * sin(ang * 3.0 + time * 5.0) + 0.02 * sin(ang * 5.0 - time * 3.7);
        float rr = rho / (r0 * wob);
        float inside = saturate((1.0 - rr) * r0 / aa + 0.5);
        float fres = pow(saturate(rr), 4.0);
        float edgeLine = exp(-PIO_OvSq((rr - 0.965) / 0.035));
        float2 world = float2(q.x * cs.x - q.y * cs.y, q.x * cs.y + q.y * cs.x) / max(rho, 1e-4);
        float lightAz = saturate(dot(world, float2(-0.6, 0.8)));
        float window = exp(-PIO_OvSq((rr - 0.74) / 0.08)) * smoothstep(0.72, 0.98, lightAz);
        float lowAz = saturate(dot(world, float2(0.6, -0.8)));
        float bounce = exp(-PIO_OvSq((rr - 0.86) / 0.07)) * smoothstep(0.6, 0.95, lowAz);
        float3 iri = 0.5 + 0.5 * cos(6.2831853 * (rr * 0.8 + float3(0.0, 0.33, 0.67) + time * 0.15 + ang * 0.16));
        float shimmer = 0.85 + 0.15 * saturate(p.z) * sin(time * 9.0 + ang * 2.0);
        float pop = saturate(p.w);
        color = lerp(lerp(albedo, iri, 0.45), white, saturate(0.3 * fres + 0.6 * edgeLine + window + 0.5 * pop));
        alpha = inside * saturate(0.08 + 0.45 * fres * shimmer + 0.45 * edgeLine + 0.85 * window + 0.35 * bounce + 0.5 * pop * fres);
    }
    else if (shape < 20.5)
    {
        // Timer: a small glossy ring draining clockwise from 12 o'clock over a faint track.
        float r0 = p.y;
        float hw = max(p.z, 1e-3);
        float frac01 = saturate(p.w);
        float band = saturate((hw - abs(rho - r0)) / aa + 0.5);
        float a01 = frac(0.25 - atan2(q.y, q.x) / 6.2831853 + 1.0);   // 0 at 12 o'clock, growing clockwise
        float onArc = saturate((frac01 - a01) * 6.2831853 * r0 / aa + 0.5);
        float nz = sqrt(saturate(1.0 - PIO_OvSq((rho - r0) / hw)));
        float3 tube = (float3)PIO_ShadeLiquid((half3)lerp(albedo, white, 0.25), float3(q / max(rho, 1e-4) * (rho - r0) / hw, max(nz, 0.05)), nz, lobes);
        color = lerp(float3(0.02, 0.03, 0.07), min(tube, white), onArc);
        alpha = band * lerp(0.55, 1.0, onArc);
    }
    else
    {
        // Shimmer (strip): a glassy, faintly iridescent film over the trail (the shield's film, stretched along it): a
        // highlight line on its upper side that ripples, and long glints running along its middle toward the head.
        float k = saturate(p.y);
        float y = uv0.y;
        float s = uv0.w;
        float body = exp(-y * y * 2.2);
        float hl = exp(-PIO_OvSq((y - 0.35) / 0.18)) * (0.55 + 0.45 * sin(s * 7.0 - time * 9.0));
        float g = frac(s * (1.0 / 0.9) - time * 2.2);
        float glint = exp(-PIO_OvSq((g - 0.5) / 0.16)) * exp(-y * y * 9.0);
        float3 iri = 0.5 + 0.5 * cos(6.2831853 * (s * 0.35 - time * 0.3 + float3(0.0, 0.33, 0.67)));
        color = lerp(lerp(albedo, iri, 0.4), white, saturate(0.35 + 0.6 * glint + 0.5 * hl));
        alpha = k * saturate(0.16 * body + 0.5 * hl + 0.85 * glint) * (1.0 - smoothstep(0.75, 1.0, abs(y)));
    }
    return float4(color, alpha);
}

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

    if (shape > 15.5)
    {
        // Wave D-2 trait shapes (header).
        float4 trait = PIO_OverlayTrait(shape, q, UV0, UV1, cs, albedo, aa, lobes);
        color = trait.rgb;
        alpha = trait.a;
    }
    else if (shape < 0.5)
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
