// ElectricComposite.hlsl - the Custom Function of ElectricComposite.shadergraph (docs/CONTRACT.md 25.4), owned by ELEC.
// Its .meta carries the fixed GUID 67a2502f5eeb4a68861aa3d7ba7b5509: the graph references this file by that GUID.
//
// The Electricite biome composite: one full-resolution pass over the static LiquidSurface quad (uv1 = world position),
// reading the same globals as LiquidComposite (territory field, wide relief field, actor field, pocket mask, palette,
// fade) plus the biome globals (_PIO_RevealTime, _PIO_Now, _PIO_SecondaryColors). Emissive look, no relief shading:
// - Ground: very dark blue-black with a faint hexagonal circuit grid (traces and vias) that lights up softly, tinted by
//   the nearby player, close to territories; a cool neon line marks the arena edge, the outside is darker.
// - Territory: an electrified plasma field. Interior = dimmed neon surface with a slowly flowing hex pattern; edge = a
//   bright neon rim with crawling micro arcs (jagged noise re-rolled at 12 Hz) and occasional small lightning arcs that
//   hop along the border (a random spot per 3.2 u cell, re-drawn every 0.38 s). A colored glow halo outside the edge
//   separates the layers.
// - Interior arcs (wave D, docs/WAVE_D_FEEDBACK.md F3): the whole surface is crossed by short jagged streaks in the
//   live wire's language (0.3 to 0.8 u, a thin white-hot core in a neon glow of the player color, jag re-rolled at 12
//   to 20 Hz per arc), each drifting slowly, popping in, flickering, fading out and re-spawning elsewhere, a few more
//   near the rim. One arc slot per cell of a turned 1.46 u grid, each cell on its own phase, so no frame flashes the
//   whole territory. Density from ElectricTheme.ShaderParams (_PIO_BiomeParams): High as set, Medium half, Low a
//   quarter with slow, static-ish arcs. The core stays below sRGB luma 235 (the chase packet stays the brightest
//   moving thing); no arc under a pending pocket (stripes only) nor across the rim band. No texture fetch.
// - Fill (FillDuration 0.25 s, driven by _PIO_RevealTime): a crackling discharge of branching lightning rides the
//   advancing contour of the fill (a band about 0.15 to 0.8 u behind it, from the wide relief field; the clamped reveal
//   age only gates it, so no edge follows the reveal cells: wave C), then the hex pattern pulses once. ElectricFx adds
//   the big bolts growing from the return point.
// - Live wire (actor layer, k = argmax a): neon body at the contract visible width (same-color fusion fA = a_k + t_k
//   makes the necks), a thin white-hot core displaced by a jagged offset re-rolled at 17 Hz, a colored glow halo.
// - Pending pockets: dashed neon diagonal lines (marching), no rim, no flow, so home stays identifiable.
// - Elimination (_PIO_PlayerFade): short circuit. The territory keeps its shape, surges, flickers (9 Hz, half contrast,
//   local only: no strobing) while its micro arcs intensify, blacks out, then disappears when the fade ends.
// Fetch budget (Medium): territory field 1, wide relief 1, pocket 1, reveal 1, actor 1 (5 without actors); the actor
// path adds the jittered core fetch (6). High uses B-spline fetches of the territory field and the pocket mask. The
// interior arcs (wave D) are pure arithmetic: no fetch added.
// Cost (wave C): the ground runs only where cT < 1, the plasma surface only where cT > 0 and the micro arcs only near
// the borders (dynamic branches, derivatives all taken before them); the fill discharge and the hopping arcs were
// already branched. Wave D: the interior arcs run inside the plasma branch, in their own branch, and visit the 2 x 2
// nearest grid cells with an early out per cell (inactive slot, then outside the arc's box or life).
// Values above 1 feed the High-tier bloom (threshold 1.1); without HDR they clip to a hotter tint.
#ifndef PIO_ELECTRIC_COMPOSITE_INCLUDED
#define PIO_ELECTRIC_COMPOSITE_INCLUDED

#include "Assets/Resources/Shaders/LiquidCommon.hlsl"
#include "Assets/Resources/Shaders/CountryDistance.hlsl"

#define PIOE_ACTOR_MIN 0.003
#define PIOE_HEX_GROUND 0.70          // hex cell size of the circuit grid on the ground (world units)
#define PIOE_HEX_PLASMA 0.46          // hex cell size of the flowing pattern inside territories
#define PIOE_POCKET_PERIOD 0.35       // dashed pocket lines period, world units (contract 12.2 stripe period)
#define PIOE_INTERIOR 0.50            // interior brightness of the neon surface (x player color)
#define PIOE_FILL_AGE 0.4             // s: reveal ages are clamped to [0, this]; everything of the fill is off at this age

// Interior arcs (wave D, F3). An arc reaches at most 0.4 (half length) + 0.108 + 0.043 (jag) + 0.17 (glow) = 0.721 u
// from its center, and its center stays inside its own cell (drift included), so it never reaches past the 2 x 2
// cells a pixel visits: the reach must stay below half a cell (0.73 u).
#define PIOE_ARC_CELL 1.46            // world units: one arc slot per cell of the turned grid
#define PIOE_ARC_LEN_MIN 0.30         // arc length range, world units (F3: about 0.3 to 0.8 u)
#define PIOE_ARC_LEN_MAX 0.80
#define PIOE_ARC_CORE 0.042           // half width of the white-hot core at the middle of an arc, world units
#define PIOE_ARC_GLOW 0.17            // reach of the neon glow around the core, world units
#define PIOE_ARC_CALM 0.5             // under the glow the hex pattern fades this much toward the plain surface
#define PIOE_ARC_NEON 1.3             // halo color: the player color times this (a neon boost) ...
#define PIOE_ARC_HALO 0.45            // ... moved this far toward the core color, luminance capped at 0.92 x the core's
#define PIOE_ARC_WHITE 0.5            // the core color is the secondary color pushed this far toward white, times the
                                      // core level (ElectricTheme.ArcCoreLevel keeps it below sRGB luma 235)
#define PIOE_ARC_PERIOD 0.8           // s: one spawn slot per cell, each cell on its own phase (never a global flash)
#define PIOE_ARC_PERIOD_LOW 2.0       // s: Low keeps a few long-lived arcs
#define PIOE_ARC_DRIFT 0.25           // u/s: largest drift speed per axis during an arc's life (none on Low)
#define PIOE_ARC_HZ_MIN 12.0          // jag re-roll rate of an arc, drawn per arc in [min, max] Hz (F3: 12 to 20 Hz)
#define PIOE_ARC_HZ_MAX 20.0
#define PIOE_ARC_HZ_LOW 3.0           // Low: slow re-roll (static-ish arcs)
#define PIOE_ARC_MEDIUM 0.5           // density scale on Medium (F3: Medium halves the density)
#define PIOE_ARC_LOW 0.25             // density scale on Low (a few arcs)

float PIOE_Max4(float4 v)
{
    return max(max(v.x, v.y), max(v.z, v.w));
}

// One-hot mask of the largest channel (the first one on ties).
float4 PIOE_ArgmaxMask(float4 v)
{
    float m = PIOE_Max4(v);
    float4 e = step(m, v);
    e.y *= 1.0 - e.x;
    e.z *= saturate(1.0 - e.x - e.y);
    e.w *= saturate(1.0 - e.x - e.y - e.z);
    return e;
}

float3 PIOE_Color(float4 m)
{
    return m.x * _PIO_Colors[0].rgb + m.y * _PIO_Colors[1].rgb + m.z * _PIO_Colors[2].rgb + m.w * _PIO_Colors[3].rgb;
}

float3 PIOE_Secondary(float4 m)
{
    return m.x * _PIO_SecondaryColors[0].rgb + m.y * _PIO_SecondaryColors[1].rgb + m.z * _PIO_SecondaryColors[2].rgb
         + m.w * _PIO_SecondaryColors[3].rgb;
}

// Integer hash of a lattice point, in [0, 1).
float PIOE_Hash(float2 cell)
{
    uint2 q = (uint2)((int2)floor(cell) + 65536);
    uint h = (q.x * 1597334677u) ^ (q.y * 3812015801u);
    h = h * 0x9E3779B1u;
    h ^= h >> 16;
    h *= 0x85EBCA6Bu;
    h ^= h >> 13;
    return (float)h * (1.0 / 4294967296.0);
}

float PIOE_Noise(float2 p)
{
    float2 i = floor(p);
    float2 f = p - i;
    f = f * f * (3.0 - 2.0 * f);
    float a = PIOE_Hash(i);
    float b = PIOE_Hash(i + float2(1.0, 0.0));
    float c = PIOE_Hash(i + float2(0.0, 1.0));
    float d = PIOE_Hash(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

// Hexagonal tiling (flat-topped rows along x). xy = offset from the cell center (hex units), zw = cell id.
float4 PIOE_HexCoords(float2 uv)
{
    const float2 s = float2(1.0, 1.7320508);
    float4 hc = floor(float4(uv, uv - float2(0.5, 1.0)) / s.xyxy) + 0.5;
    float4 h = float4(uv - hc.xy * s, uv - (hc.zw + 0.5) * s);
    return dot(h.xy, h.xy) < dot(h.zw, h.zw) ? float4(h.xy, hc.xy) : float4(h.zw, hc.zw + 0.5);
}

// Distance from the cell center: 0 at the center, 0.5 on the edges.
float PIOE_HexDist(float2 p)
{
    p = abs(p);
    return max(dot(p, float2(0.5, 0.8660254)), p.x);
}

// Hex edge distance with its antialiasing width: x = 0.5 - PIOE_HexDist(p) (0 on the cell edges), y = |d/dx| + |d/dy|
// of x per hex unit, which is what fwidth returns for this piecewise linear function when the screen axes are the world
// axes (orthographic top-down camera). Multiply y by the pixel size in hex units. No derivative: usable in a branch.
float2 PIOE_HexEdge(float2 p)
{
    p = abs(p);
    float slant = dot(p, float2(0.5, 0.8660254));
    return slant > p.x ? float2(0.5 - slant, 1.3660254) : float2(0.5 - p.x, 1.0);
}

// Antialiased thin line where x crosses 0 (x in any unit), half width hw in the same unit.
float PIOE_Line(float x, float hw)
{
    float aa = max(fwidth(x), 1e-5);
    return saturate((hw - abs(x)) / aa + 0.5);
}

// The same with an explicit antialiasing width aa (x units per pixel): no derivative, so usable in a dynamic branch.
float PIOE_LineAA(float x, float hw, float aa)
{
    return saturate((hw - abs(x)) / max(aa, 1e-5) + 0.5);
}

// Exact signed distance of the rounded-square arena (< 0 inside).
float PIOE_ArenaSdf(float2 p)
{
    float r = _PIO_ArenaShape.y;
    float2 q = abs(p) - (_PIO_ArenaShape.x - r);
    return PIO_OptionalCountryDistance(p, length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r);
}

// Cubic B-spline reconstruction from 4 bilinear taps (Sigg and Hadwiger). texel = (1/w, 1/h, w, h).
float4 PIOE_SampleBSpline(TEXTURE2D_PARAM(tex, smp), float2 uv, float4 texel)
{
    float2 st = uv * texel.zw - 0.5;
    float2 i = floor(st);
    float2 f = st - i;
    float2 f2 = f * f;
    float2 f3 = f2 * f;
    float2 w0 = (1.0 / 6.0) * (-f3 + 3.0 * f2 - 3.0 * f + 1.0);
    float2 w1 = (1.0 / 6.0) * (3.0 * f3 - 6.0 * f2 + 4.0);
    float2 w2 = (1.0 / 6.0) * (-3.0 * f3 + 3.0 * f2 + 3.0 * f + 1.0);
    float2 w3 = (1.0 / 6.0) * f3;
    float2 g0 = w0 + w1;
    float2 g1 = w2 + w3;
    float2 p0 = (i + 0.5 - 1.0 + w1 / g0) * texel.xy;
    float2 p1 = (i + 0.5 + 1.0 + w3 / g1) * texel.xy;
    float4 s00 = SAMPLE_TEXTURE2D_LOD(tex, smp, float2(p0.x, p0.y), 0);
    float4 s10 = SAMPLE_TEXTURE2D_LOD(tex, smp, float2(p1.x, p0.y), 0);
    float4 s01 = SAMPLE_TEXTURE2D_LOD(tex, smp, float2(p0.x, p1.y), 0);
    float4 s11 = SAMPLE_TEXTURE2D_LOD(tex, smp, float2(p1.x, p1.y), 0);
    return g0.y * (g0.x * s00 + g1.x * s10) + g1.y * (g0.x * s01 + g1.x * s11);
}

// The circuit board: dark blue-black, a faint hex grid of traces with vias, lit and tinted near territories. pix = world
// units per pixel, taken by the caller outside the dynamic branch this runs in (no derivative in here, wave C).
float3 PIOE_Ground(float2 w, float time, float near, float3 tint, float pix)
{
    float sd = PIOE_ArenaSdf(w);
    float inArena = saturate(0.5 - sd / pix);

    float mottle = PIOE_Noise(w * 0.9 + 31.0) - 0.5;
    float3 base = _PIO_GroundColor.rgb * (1.0 + 0.35 * mottle);

    float2 hu = w / PIOE_HEX_GROUND;
    float pixHex = pix / PIOE_HEX_GROUND;
    float4 h = PIOE_HexCoords(hu);
    float2 edge = PIOE_HexEdge(h.xy);
    float cellHash = PIOE_Hash(h.zw * 1.37 + 5.0);
    float trace = PIOE_LineAA(edge.x, 0.022, edge.y * pixHex);
    // Some edges carry a brighter trace, some cells a via (circuit look rather than a plain honeycomb). The radius has
    // a unit gradient, so its fwidth is (|x| + |y|) / r per hex unit.
    float r = length(h.xy);
    float rAA = pixHex * (abs(h.x) + abs(h.y)) / max(r, 1e-4);
    float via = PIOE_LineAA(r - 0.11, 0.035, rAA) * step(0.72, cellHash);
    float pad = saturate((0.07 - r) / max(rAA, 1e-5) + 0.5) * step(0.72, cellHash);
    float shimmer = 0.75 + 0.25 * sin(time * 0.8 + cellHash * 6.2832);
    float lit = 0.18 + 3.5 * near;
    float3 circuit = float3(0.010, 0.022, 0.055) * lit * shimmer;
    float3 inside = base + (trace * 0.85 + via + pad * 0.7) * circuit + (trace + via) * tint * near * 0.16;

    // Arena edge: a soft cool neon line, the darker outside beyond it.
    float rimLine = exp(-abs(sd) / 0.045) * 0.10 + exp(-max(sd, 0.0) / 0.5) * 0.015 * inArena;
    float innerShade = 1.0 - 0.35 * (1.0 - smoothstep(0.0, 1.2, -sd));
    float3 outside = _PIO_OutsideColor.rgb * (1.0 + 0.2 * mottle);
    float3 g = lerp(outside, inside * innerShade, inArena);
    return g + float3(0.05, 0.16, 0.42) * rimLine;
}

// 32-bit integer mixer (lowbias32).
uint PIOE_Mix(uint h)
{
    h ^= h >> 16;
    h *= 0x7FEB352Du;
    h ^= h >> 15;
    h *= 0x846CA68Bu;
    h ^= h >> 16;
    return h;
}

// Hash of a lattice cell and a non-negative integer key (spawn slot, jag step).
uint PIOE_HashKey(float2 cell, float key)
{
    uint2 q = (uint2)((int2)floor(cell) + 65536);
    return PIOE_Mix((q.x * 1597334677u) ^ (q.y * 3812015801u) ^ ((uint)key * 2246822519u));
}

// Byte i (0..3) of a hash, in [0, 1].
float PIOE_Byte(uint h, uint i)
{
    return (float)((h >> (8u * i)) & 255u) * (1.0 / 255.0);
}

// Knot j of a jag level packed in a hash: 4 bits (coarse) or 3 bits (fine) per knot, in [-1, 1].
float PIOE_Knot4(uint bits, uint j)
{
    return (float)((bits >> (4u * j)) & 15u) * (2.0 / 15.0) - 1.0;
}

float PIOE_Knot3(uint bits, uint j)
{
    return (float)((bits >> (3u * j)) & 7u) * (2.0 / 7.0) - 1.0;
}

// Interior arcs (wave D, docs/WAVE_D_FEEDBACK.md F3): short jagged streaks with a white-hot core and a neon glow, the
// visual language of the live wire. One arc slot per cell of a grid turned by about 24 degrees (no axis-aligned rows).
// In each slot (PIOE_ARC_PERIOD, a phase per cell from a Weyl sequence) a cell holds an arc with probability `density`
// (soft threshold, so a density that changes across the rim fades arcs instead of clipping them): a random spot,
// angle and length, drifting slowly through the slot, popping in, flickering while its jagged offset is re-rolled at
// its own 12 - 20 Hz rate, then fading out; the next slot re-spawns it elsewhere in the cell. The jag is two piecewise
// linear levels (5 and 10 segments) anchored at both ends; the distance to the local segment is corrected by its slope.
// An arc stays within half a cell of its own cell, so a pixel visits only the 2 x 2 nearest cells, each with early outs.
// pix = world units per pixel, taken by the caller: no derivative in here, usable inside dynamic branches.
// Returns x = core coverage, y = glow (both 0..1, the strongest arc wins).
float2 PIOE_Arcs(float2 w, float time, float density, bool low, float pix)
{
    const float2 rot = float2(0.9135455, 0.4067366);                 // cos and sin of 24 degrees
    float2 pr = float2(dot(w, rot), dot(w, float2(-rot.y, rot.x)));   // world units in the turned grid frame
    float2 base = floor(pr * (1.0 / PIOE_ARC_CELL) - 0.5);
    float period = low ? PIOE_ARC_PERIOD_LOW : PIOE_ARC_PERIOD;
    float drift = low ? 0.0 : PIOE_ARC_DRIFT * period;                // drift over a whole slot, per axis
    float fine = low ? 0.0 : 0.4;                                     // Low: coarse jag only
    float coreOut = 0.0;
    float glowOut = 0.0;
    [unroll] for (int i = 0; i < 4; i++)
    {
        float2 cid = base + float2((float)(i & 1), (float)(i >> 1));
        float u = time / period + frac(dot(cid, float2(0.6180340, 0.7548777)));
        float slot = floor(u);
        float f = u - slot;
        uint h = PIOE_HashKey(cid, slot);
        float act = saturate((density - PIOE_Byte(h, 0u)) * 12.0);
        [branch] if (act > 0.0)
        {
            uint h2 = PIOE_Mix(h ^ 0x9E3779B9u);
            // Center: inside the cell with a margin for the drift (0.5 x 0.25 u/s x 0.8 s x 1 = 0.1 u = 0.068 cell).
            float2 jit = float2(PIOE_Byte(h, 1u), PIOE_Byte(h, 2u));
            float2 dir = float2(PIOE_Byte(h2, 0u), PIOE_Byte(h2, 1u)) * 2.0 - 1.0;
            float2 center = (cid + lerp(0.08, 0.92, jit)) * PIOE_ARC_CELL + dir * (drift * (f - 0.5));
            float2 rel = pr - center;
            float ang = PIOE_Byte(h, 3u) * 3.14159265;
            float2 ax = float2(cos(ang), sin(ang));
            float len = lerp(PIOE_ARC_LEN_MIN, PIOE_ARC_LEN_MAX, PIOE_Byte(h2, 2u));
            float amp = 0.11 * len + 0.02;                            // coarse jag amplitude (fine level: 0.4 x)
            float s = dot(rel, ax);
            float d = dot(rel, float2(-ax.y, ax.x));
            // Life in the slot: starts in its first quarter, lasts 55 to 90 % of it; pops in, fades out.
            uint lifeBits = h2 >> 24;
            float lg = (f - (float)(lifeBits & 15u) * (0.25 / 15.0)) / (0.55 + (float)(lifeBits >> 4) * (0.35 / 15.0));
            float env = smoothstep(0.0, 0.05, lg) * (1.0 - smoothstep(0.7, 1.0, lg));
            [branch] if (env > 0.0 && abs(s) < 0.5 * len + PIOE_ARC_GLOW && abs(d) < 1.4 * amp + PIOE_ARC_GLOW)
            {
                uint h3 = PIOE_Mix(h2 ^ 0x85EBCA6Bu);
                float hz = low ? PIOE_ARC_HZ_LOW : lerp(PIOE_ARC_HZ_MIN, PIOE_ARC_HZ_MAX, PIOE_Byte(h3, 0u));
                float tq = floor(time * hz + PIOE_Byte(h3, 1u));
                uint hj = PIOE_HashKey(cid + 8191.0, tq);                // coarse knots (4 x 4 bits) and flicker (4 bits)
                uint hf = PIOE_Mix(hj ^ 0x27D4EB2Fu);                    // fine knots (9 x 3 bits)
                float sc = saturate(s / len + 0.5);
                float x1 = sc * 5.0;
                float k1 = min(floor(x1), 4.0);
                uint i1 = (uint)k1;
                float a0 = i1 == 0u ? 0.0 : PIOE_Knot4(hj, max(i1, 1u) - 1u);
                float a1 = i1 >= 4u ? 0.0 : PIOE_Knot4(hj, min(i1, 3u));
                float x2 = sc * 10.0;
                float k2 = min(floor(x2), 9.0);
                uint i2 = (uint)k2;
                float b0 = i2 == 0u ? 0.0 : PIOE_Knot3(hf, max(i2, 1u) - 1u);
                float b1 = i2 >= 9u ? 0.0 : PIOE_Knot3(hf, min(i2, 8u));
                float o = (lerp(a0, a1, x1 - k1) + fine * lerp(b0, b1, x2 - k2)) * amp;
                float inside = step(abs(s), 0.5 * len);
                float slope = ((a1 - a0) * 5.0 + fine * (b1 - b0) * 10.0) * (amp / len) * inside;
                float perp = abs(d - o) * rsqrt(1.0 + slope * slope);
                float along = max(abs(s) - 0.5 * len, 0.0);
                float dist = sqrt(perp * perp + along * along);
                // Full width over the middle 60 %, thinner toward the ends; a core thinner than a pixel keeps its energy.
                float tap = saturate(min(sc, 1.0 - sc) * 5.0);
                float coreHW = PIOE_ARC_CORE * (0.35 + 0.65 * tap);
                float drawn = max(coreHW, 0.5 * pix);
                float core = saturate((drawn - dist) / pix + 0.5) * (coreHW / drawn);
                float glow = 1.0 - saturate(dist * (1.0 / PIOE_ARC_GLOW));
                glow *= glow * (0.45 + 0.55 * tap);
                float e = env * act * (0.7 + 0.3 * (float)(hj >> 28) * (1.0 / 15.0));   // local flicker per jag step
                coreOut = max(coreOut, core * e);
                glowOut = max(glowOut, glow * e);
            }
        }
    }
    return float2(coreOut, glowOut);
}

void PIO_ElectricCompositeSG_float(float4 VertexColor, float2 UV1, out float3 BaseColor, out float Alpha)
{
    float2 w = UV1;
    float time = _PIO_Time.x;
    bool bicubic = _PIO_Quality.z > 0.5;
    bool low = _PIO_Quality.y < 0.5;                 // Low tier (no shadow taps): fewer noise octaves
    float actorScale = max(_PIO_ActorScale, 1e-4);
    // World units per pixel, taken here, outside every dynamic branch: the branches below get analytic AA widths.
    float pix = max(max(fwidth(w.x), fwidth(w.y)), 1e-5);

    // ---- Territory layer ------------------------------------------------------------------------------------------
    float2 uvT = (w - _PIO_ArenaRect.xy) / _PIO_ArenaRect.zw;
    float4 tRaw;
    float4 pocket;
    [branch] if (bicubic)
    {
        tRaw = PIOE_SampleBSpline(TEXTURE2D_ARGS(_PIO_TerritoryField, sampler_PIO_TerritoryField), uvT, _PIO_TerritoryTexel);
        pocket = PIOE_SampleBSpline(TEXTURE2D_ARGS(_PIO_PocketMask, sampler_PIO_PocketMask), uvT, _PIO_PocketTexel);
    }
    else
    {
        tRaw = SAMPLE_TEXTURE2D_LOD(_PIO_TerritoryField, sampler_PIO_TerritoryField, uvT, 0);
        pocket = SAMPLE_TEXTURE2D_LOD(_PIO_PocketMask, sampler_PIO_PocketMask, uvT, 0);
    }
    // Short circuit: a fading player keeps its full shape until the very end of the fade (the color blacks out instead).
    float4 fade = _PIO_PlayerFade;
    float4 shapeFade = saturate(fade * 25.0);
    float4 t = tRaw * shapeFade;
    float wide = SAMPLE_TEXTURE2D_LOD(_PIO_TerritoryHeight, sampler_PIO_TerritoryHeight, uvT, 0).w;
    float rev = SAMPLE_TEXTURE2D_LOD(_PIO_RevealTime, sampler_PIO_RevealTime, uvT, 0).r;

    float4 mj = PIOE_ArgmaxMask(t);
    float tj = dot(t, mj);
    float fwTj = max(fwidth(tj), 1e-4);
    float cT = saturate((tj - 0.5) / fwTj + 0.5);
    // Where two colors touch, blend the two strongest over about one pixel (antialiased contact line).
    float4 others = t * (1.0 - mj);
    float4 m2 = PIOE_ArgmaxMask(others);
    float gap = tj - PIOE_Max4(others);
    float wj = 0.5 + 0.5 * saturate(gap / max(fwidth(gap), 1e-4));
    float3 colJ = lerp(PIOE_Color(m2), PIOE_Color(mj), wj);
    float3 secJ = lerp(PIOE_Secondary(m2), PIOE_Secondary(mj), wj);
    float jIndex = dot(mj, float4(0.0, 1.0, 2.0, 3.0));

    // Blackout level of the strongest channel (1 = alive). e runs 0 -> 1 over the 0.6 s evaporation.
    float fadeJ = dot(fade, mj);
    float e = 1.0 - saturate(fadeJ);
    float dying = step(1e-3, e);
    // Comfortable flicker (a territory can cover much of the screen): 9 Hz, at most half contrast, for 0.6 s.
    float flickStep = floor(time * 9.0);
    float on = PIOE_Hash(float2(flickStep, jIndex * 13.0 + 3.0)) > e * 0.95 ? 1.0 : 0.5;
    float surge = 1.0 + 0.6 * exp(-e * 14.0) * dying;
    float level = lerp(1.0, on * (1.0 - smoothstep(0.30, 0.92, e)), smoothstep(0.0, 0.06, e)) * surge;

    // Near-territory light for the ground: the wide relief field (max t, sigma 0.26 u) and a t-weighted tint.
    float tsum = dot(t, float4(1.0, 1.0, 1.0, 1.0));
    float3 tint = (t.x * _PIO_Colors[0].rgb + t.y * _PIO_Colors[1].rgb + t.z * _PIO_Colors[2].rgb + t.w * _PIO_Colors[3].rgb)
                  / max(tsum, 1e-4);
    tint = lerp(float3(0.10, 0.35, 0.85), tint, saturate(tsum * 6.0));
    float near = smoothstep(0.0, 0.7, wide) * lerp(1.0, level, dying);

    // Fill discharge timing (contract 25.4: FillDuration 0.25 s, then one hex pulse). Wave C: the age is clamped to
    // [0, PIOE_FILL_AGE] and only gates the effects on and off with a smooth fade in time; WHERE the discharge shows comes
    // from the smooth wide relief field (a band at fixed depths behind the contour, as the liquid ripple does), never from
    // the reveal ages: each cell holds one reveal time (-1000 when never revealed) and bilinear filtering cannot smooth
    // those jumps, so every edge drawn from the ages traced the 0.125 u cell staircase. Cells appear in order of distance
    // from the return point, so the territory contour itself is the advancing front of the fill and the band rides it,
    // then fades on the final contour. The band starts deeper than one cell behind the contour, where the contour's own
    // freshly revealed cells always gate it on (the gate's staircase sits at the last cell centers, outside the band).
    // Known limit: where the band crosses into older territory (near the two junctions of the new area) the bilinear age
    // still snaps from fresh to old within one pixel, a short cell-aligned cut. Clamping the four ages before filtering
    // needs a Gather, and the Shader Graph Unlit Forward pass compiles at target 2.0 (no Gather) on every platform.
    float ageC = clamp(_PIO_Now - rev, 0.0, PIOE_FILL_AGE);
    float gate = 1.0 - smoothstep(0.05, 0.32, ageC);
    float pulseU = saturate((ageC - 0.12) * (1.0 / 0.28));          // one pulse between 0.12 and 0.40 s, peak at 0.26 s
    float pulse = sin(pulseU * 3.14159265);
    pulse *= pulse;
    float band = smoothstep(0.70, 0.80, wide) * (1.0 - smoothstep(0.95, 0.9992, wide));  // about 0.14 to 0.8 u deep
    float sweep = gate * band;
    float crestX = (wide - 0.80) * (1.0 / 0.07);                    // the bright leading crest, about 0.2 u deep
    float crest = gate * exp(-crestX * crestX) * smoothstep(0.66, 0.76, wide);   // no tail over the last cell centers

    // Pending pocket coverage (its derivative is taken here, outside every dynamic branch; the stripes are drawn below).
    float4 mp = PIOE_ArgmaxMask(pocket);
    float pm = dot(pocket, mp);
    float pocketCover = saturate((pm - 0.5) / max(fwidth(pm), 1e-4) + 0.5);

    // Interior arcs (wave D, F3). Density per tier from ElectricTheme.ShaderParams (x = High density, y = extra density
    // near the rim, z = core level, w = glow level; all 0 turns the arcs off), more within about 0.6 u of the edge (wide
    // relief field); the arcs fade out before the rim band (narrow field) and never show under a pending pocket.
    float4 arcParams = _PIO_BiomeParams;
    float arcTier = bicubic ? 1.0 : (low ? PIOE_ARC_LOW : PIOE_ARC_MEDIUM);
    float rimNear = 1.0 - smoothstep(0.90, 0.995, wide);
    float arcDensity = (arcParams.x + arcParams.y * rimNear) * arcTier;
    float arcMask = smoothstep(0.80, 0.93, tj) * (1.0 - pocketCover);

    // ---- Ground, only where the territory does not fully cover the pixel (cT is exactly 1 inside it) -------------------
    float3 ground = float3(0.0, 0.0, 0.0);
    [branch] if (cT < 1.0)
    {
        ground = PIOE_Ground(w, time, near, tint, pix);
        // Colored glow halo just outside the edges (separates the layers).
        float halo = pow(saturate(wide * 1.6), 1.6) * (1.0 - cT);
        ground += tint * halo * 0.30 * lerp(1.0, level, dying);
    }

    // ---- Plasma surface, only where the territory shows (cT is exactly 0 off it): the lerp result is unchanged ---------
    // Wave C (perf): the hex tiling, the flow noise, the surface and the rim used to run on every pixel. No derivative
    // inside the branch: the hex line gets its analytic AA width from pix.
    float3 color = ground;
    [branch] if (cT > 0.0)
    {
        // Dimmed neon with a slowly flowing hex pattern.
        float2 hu = w / PIOE_HEX_PLASMA;
        float4 h = PIOE_HexCoords(hu);
        float2 hexEdge = PIOE_HexEdge(h.xy);
        float hexLine = PIOE_LineAA(hexEdge.x, 0.035, hexEdge.y * (pix / PIOE_HEX_PLASMA));
        float flowNoise = PIOE_Noise(w * 0.33 + float2(time * 0.07, -time * 0.05));
        float flow = 0.5 + 0.5 * sin(dot(h.zw, float2(0.61, 0.37)) * 1.15 - time * 1.35 + flowNoise * 5.0);
        float flowPeak = smoothstep(0.75, 1.0, flow);
        float cellGlow = 1.0 - smoothstep(0.0, 0.5, 0.5 - hexEdge.x);

        // Fill discharge: crackling branches in the band behind the advancing contour.
        float discharge = 0.0;
        [branch] if (sweep > 0.01)
        {
            // Warped ridged noise with a high-frequency jag (no smooth loops), cut into fragments: crackling branches.
            float tqF = floor(time * 30.0);
            float2 q = w * 2.1;
            q += 0.9 * (float2(PIOE_Noise(w * 1.1 + tqF * 0.37), PIOE_Noise(w * 1.1 - tqF * 0.29 + 9.0)) - 0.5);
            q += 0.28 * (float2(PIOE_Noise(w * 9.0 + 3.0 + tqF), PIOE_Noise(w * 9.0 + 7.0 - tqF)) - 0.5);
            float r1 = 1.0 - abs(2.0 * PIOE_Noise(q) - 1.0);
            float bolt = pow(saturate(r1), 30.0);
            if (!low)
            {
                float r2 = 1.0 - abs(2.0 * PIOE_Noise(q * 2.3 + 17.0) - 1.0);
                bolt += 0.6 * pow(saturate(r2), 36.0);
            }
            float frag = smoothstep(0.30, 0.55, PIOE_Noise(w * 0.85 + 41.0 + tqF * 0.11));
            discharge = saturate(bolt * 2.6 * frag) * sweep;
        }

        float3 surface = colJ * (PIOE_INTERIOR + 0.10 * flow + 0.06 * cellGlow);
        surface += colJ * hexLine * (0.30 + 0.70 * flow) * (1.0 + 1.6 * pulse);
        surface += secJ * hexLine * flowPeak * 0.35;
        surface += secJ * pulse * hexLine * 0.6;
        // Inner glow toward the rim, then the bright neon rim band.
        float rimIn = 1.0 - smoothstep(0.5, 0.95, tj);
        surface += colJ * rimIn * 0.35;
        float rim = 1.0 - smoothstep(0.52, 0.74, tj);
        float3 rimColor = colJ * 1.25 + secJ * 0.45;
        surface = lerp(surface, rimColor, rim);
        // The discharge sweep: a soft flash over the band (the white-hot secondary color: the player color alone barely
        // shows on a saturated neon surface), its bright leading crest and the white-hot branches.
        surface += colJ * sweep * 0.30 + secJ * (discharge * 2.4 + sweep * 0.40 + crest * 0.75);

        // Interior arcs: the hex lines calm down under the glow, a neon halo (a blend toward the boosted player color moved
        // partly toward the core color, its luminance capped below the core's: it shows on a surface of the same color and
        // never outshines the core, where an additive halo on a bright neon like cyan saturated above it), then the
        // white-hot core (the secondary pushed toward white, times the core level: below sRGB luma 235 for every electric
        // color, never feeding the High bloom). Blacked out with the rest by the short circuit below.
        [branch] if (arcMask > 0.0 && arcDensity > 0.0)
        {
            float2 arc = PIOE_Arcs(w, time, arcDensity, low, pix) * arcMask;
            const float3 lumW = float3(0.2126, 0.7152, 0.0722);
            float3 arcCore = lerp(secJ, float3(1.0, 1.0, 1.0), PIOE_ARC_WHITE) * arcParams.z;
            float3 halo = lerp(colJ * PIOE_ARC_NEON, arcCore, PIOE_ARC_HALO);
            halo *= min(1.0, 0.92 * dot(arcCore, lumW) / max(dot(halo, lumW), 1e-4));
            surface = lerp(surface, colJ * (PIOE_INTERIOR + 0.1), PIOE_ARC_CALM * arc.y);
            surface = lerp(surface, halo, saturate(arc.y * arcParams.w));
            surface = lerp(surface, arcCore, arc.x);
        }

        // Short circuit: surge, flicker and black out toward a dead blue-grey.
        float3 dead = colJ * 0.05 + float3(0.006, 0.008, 0.016);
        surface = lerp(surface, lerp(dead, surface, level), dying);

        color = lerp(ground, surface, cT);
    }

    // Micro arcs crawling along every border (jagged contour re-rolled at 12 Hz, moving segments). Wave C (perf): only
    // where tj is in [0.12, 0.75] (arcT = tj +/- 0.15 must reach 0.43 +/- 0.022, and the segment mask is 0 below 0.2);
    // the AA width is taken outside the branch: fwidth(tj) plus the typical slope of the two noise terms.
    float arcAA = 1.4 * fwTj + 2.0 * pix;
    [branch] if (tj > 0.12 && tj < 0.75)
    {
        float tq = floor(time * 12.0);
        float n1 = PIOE_Noise(w * 6.5 + tq * 17.31) - 0.5;
        float n2 = low ? 0.0 : PIOE_Noise(w * 15.0 - tq * 9.7) - 0.5;
        float arcT = tj + n1 * 0.22 + n2 * 0.08;
        float arcLine = saturate((0.022 - abs(arcT - 0.43)) / arcAA + 0.5);
        float seg = smoothstep(0.52, 0.74, PIOE_Noise(w * 1.1 + float2(time * 0.9, -time * 0.55)));
        float micro = arcLine * seg * smoothstep(0.2, 0.32, tj) * (1.0 + 2.5 * dying * level);
        color += (secJ * 1.5 + colJ * 0.5) * micro * lerp(1.0, level, dying);
    }

    // Occasional small lightning arcs hopping along the border: a random spot per 3.2 u cell, re-drawn every 0.38 s.
    {
        float slotRate = 2.6;
        float slot = floor(time * slotRate);
        float phase = frac(time * slotRate);
        float2 cell = floor(w / 3.2);
        float hh = PIOE_Hash(cell * 1.31 + slot * 7.13);
        float active = hh > 0.70 ? 1.0 - smoothstep(0.05, 0.42, phase) : 0.0;
        float hopAA = fwTj * 2.0 + 0.01;                              // no derivative inside the dynamic branch
        [branch] if (active > 0.0)
        {
            float2 center = (cell + float2(PIOE_Hash(cell + slot * 3.1 + 1.0), PIOE_Hash(cell + slot * 5.7 + 2.0))) * 3.2;
            float m = 1.0 - smoothstep(0.35, 1.25, length(w - center));
            float tq2 = floor(time * 20.0);
            float arcT2 = tj + (PIOE_Noise(w * 4.2 + tq2 * 3.3) - 0.5) * 0.45 + (PIOE_Noise(w * 11.0 + tq2 * 1.7) - 0.5) * 0.14;
            float hopLine = saturate((0.03 - abs(arcT2 - 0.30)) / hopAA + 0.5);
            float hop = hopLine * m * active * smoothstep(0.06, 0.2, tj) * lerp(1.0, level, dying);
            color += (secJ * 2.2 + colJ * 0.8) * hop;
        }
    }

    // ---- Pending pockets: dashed neon lines, flat (no rim, no flow); mp and pocketCover come from above -----------------
    {
        float across = (w.x + w.y) * (0.70710678 / PIOE_POCKET_PERIOD) - time * 0.22;
        float along = (w.x - w.y) * (0.70710678 / 0.30) + time * 0.9;
        float stripe = PIOE_Line(frac(across) - 0.5, 0.17);
        float dash = PIOE_Line(frac(along) - 0.5, 0.31);
        float3 pc = PIOE_Color(mp);
        float3 ps = PIOE_Secondary(mp);
        color = lerp(color, color * 0.6 + pc * 0.08, 0.6 * pocketCover);
        color = lerp(color, pc * 1.15 + ps * 0.25, 0.95 * stripe * dash * pocketCover);
    }

    // ---- Actor layer: the live wire ---------------------------------------------------------------------------------
    float2 uvA = (w - _PIO_ActorRect.xy) / _PIO_ActorRect.zw;
    float4 a = SAMPLE_TEXTURE2D_LOD(_PIO_ActorField, sampler_PIO_ActorField, uvA, 0) / actorScale;
    float maxA = PIOE_Max4(a);
    float4 mk = PIOE_ArgmaxMask(a);
    float ak = dot(a, mk);
    float tk = dot(t, mk);
    float fA = ak + tk;
    float cA = saturate((fA - 0.5) / max(fwidth(fA), 1e-4) + 0.5);   // derivatives outside the dynamic branch
    [branch] if (maxA >= PIOE_ACTOR_MIN)
    {
        float own = smoothstep(0.35, 0.85, tk);                       // lying on its own territory: it merges
        float kIndex = dot(mk, float4(0.0, 1.0, 2.0, 3.0));
        float tq = floor(time * 17.0);                                // jagged lightning offset, 17 Hz
        float2 jit = (float2(PIOE_Noise(w * 5.5 + tq * 7.17), PIOE_Noise(w * 5.5 - tq * 3.71 + 19.3)) - 0.5) * 0.11;
        jit += (float2(PIOE_Noise(w * 13.0 + tq * 1.9 + 3.0), PIOE_Noise(w * 13.0 - tq * 2.3 + 7.1)) - 0.5) * 0.04;
        float aj = dot(SAMPLE_TEXTURE2D_LOD(_PIO_ActorField, sampler_PIO_ActorField, uvA + jit / _PIO_ActorRect.zw, 0), mk) / actorScale;
        float flick = 0.82 + 0.18 * PIOE_Hash(float2(tq, kIndex + 11.0));
        float core = smoothstep(0.86, 0.985, aj) * (1.0 - own);         // thin: about 40 % of the visible width
        float3 colK = PIOE_Color(mk);
        float3 secK = PIOE_Secondary(mk);
        float3 body = colK * 1.08 + secK * 0.12;
        float3 wire = lerp(body, secK * 2.4 * flick, core);
        color = lerp(color, wire, cA * (1.0 - own));
        // Colored glow halo outside the visible body (and a faint one over its own territory).
        float glow = smoothstep(0.06, 0.5, ak) * (1.0 - cA * (1.0 - own)) * (1.0 - 0.6 * own);
        color += colK * glow * 0.55 + secK * glow * glow * glow * 0.25;
    }

    BaseColor = max(color, 0.0);
    Alpha = 1.0;
}

void PIO_ElectricCompositeSG_half(half4 VertexColor, half2 UV1, out half3 BaseColor, out half Alpha)
{
    float3 baseColor;
    float alpha;
    PIO_ElectricCompositeSG_float((float4)VertexColor, (float2)UV1, baseColor, alpha);
    BaseColor = (half3)baseColor;
    Alpha = (half)alpha;
}

#endif // PIO_ELECTRIC_COMPOSITE_INCLUDED
