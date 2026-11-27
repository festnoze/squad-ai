// FireComposite.hlsl - the Custom Function of FireComposite.shadergraph (docs/CONTRACT.md 25.2, 25.3, 25.5), owned by FIRE.
// Its .meta carries the fixed GUID 72ceb8c7036a46a6bd9e75d1d4c72781: the graph references this file by that GUID.
//
// The Feu biome composite. Same inputs, globals and layering as LiquidComposite (one full-resolution pass over the
// static LiquidSurface quad, UV1 = world position w of the pixel), with an emissive fire look instead of glossy paint:
// - Ground: charred stone and ash (#1A1412 to #241A16, faint cooled cracks), light grey outside the arena past a yellow neon line (shared PIO_ArenaFrame), lit by a warm
//   glow around every fire (soft, a little stronger above each fire: light rises).
// - Territory: j = argmax t_i (the contour uses the unfaded field, so a burning-out bed keeps its shape). The interior is
//   a bed of glowing coals in the player's flame color (animated cellular noise, slow breathing pulse per coal, dark
//   crust between coals, now and then a coal flaring at its centre).
// - The flame band (25.3, "the spreading the user likes"): live tongues lick outward from every edge over the bare
//   ground and upward-scrolling tongues burn over the outer rim inside the bed, so the edge is a band of flames, not a
//   line. The band is laid out in WORLD units: d, the signed distance to the contour, comes from the wide relief field
//   (height .w, a Gaussian of sigma PIO_FIRE_WIDE_SIGMA across a straight edge) through the inverse normal CDF, and the
//   outward normal from its gradient (Gather on shader model 4.5 and up: exact per pixel, no 2 x 2 quad steps). Tongues
//   reach up to about 0.85 u above edges facing screen up and 0.3 u below edges facing down, and the owner of a far
//   tongue is read 0.35 u inward along the normal (the owner tap), so every tongue keeps its player's color.
// - Fill (the spreading fire): _PIO_Now - _PIO_RevealTime is the age of each cell since it was revealed. The front is a
//   moving BAND: a white-hot band just inside the contour with taller tongues licking ahead of it. Its place comes from
//   the contour (the territory grows cell by cell during the fill, so the band rides the advancing edge across the
//   captured area); the age only gates it on (a Gaussian of the age, centred at 0.08 s, zero after 0.3 s), read
//   PIO_FIRE_GATE_DEPTH inside the contour so it never mixes unrevealed cells, with every texel's age clamped before
//   interpolation (Gather) so old and never-revealed (-1000) cells draw no texel steps. Fresh embers glow warmer and
//   settle within 0.8 s; deeper than 0.2 u inside, the age is read at the centre of each coal, so the boundary between
//   fresh and old embers runs along the dark crust between coals instead of the 0.125 u texel staircase. Without Gather
//   the same band shows (only the ends of the gate snap to cells).
// - Elimination: while _PIO_PlayerFade drops, the bed cools to grey ash, its flames die and the ash crumbles away
//   through a noise dissolve (FireFx adds the smoke).
// - Pending pockets: glowing ember stripes in the owner's color, flat, no coal texture and no flames (home stays the
//   only bed with coals and flames).
// - Actors (only where max a_i >= 0.003): k = argmax a_i, fA = a_k + t_k (same-color fusion: the fuse emerges from its
//   own bed and merges into it). A thread is a burning fuse: a thin dark cord (fA > 0.8) inside a sheath of small flames
//   in the flame color whose tongues reach a little past the visible edge (fA = 0.5), embers crawling along the cord.
// Cost (wave C, perf-01): every expensive layer runs in a coherent dynamic branch: the coals only where cT > 0, the
// ground (grain, cracks, glow) only where the bed does not cover, the flame noise only inside the flame band, the
// reveal age and the owner tap only within PIO_FIRE_NEAR of a bed. No derivative and no implicit-LOD sample runs inside
// a dynamic branch (fwidth and ddx/ddy are taken at the top, every fetch in a branch is LOD 0 or a Gather).
// Tiers (QualityTier is not touched: _PIO_Quality.z bicubic is 1 on High only, .y shadows is 1 on High and Medium):
// High = B-spline territory, 3 x 3 animated coals, 3 flame octaves; Medium = bilinear, 2 x 2 animated coals, 2 octaves;
// Low = 2 x 2 static coals, 2 octaves on a single warp, no owner and glow taps (tongues capped where the pixel's own
// field still names the owner), no cracks.
// - Biome traits (wave D-2 traits-fx, docs/BIOME_TRAITS.md 5 and 7, generic: any trait may run in this biome):
//   - Rim: with Propagation a bed may reach the border of the grid (the arena's straight sides): the narrow field and
//     the contour distance are limited by a straight edge lying on the border, so the bed ends there with its flames.
//   - Scorched ground (ScorchedEarth): ash with dying embers. The scorch level is the G channel of _PIO_RevealTime,
//     fetched only while a scorch exists (_PIO_ScorchOn) and only on the ground; the actor glow on the ground now comes
//     from the actor fetch at the pixel, so that fetch slot is the one the scorch uses.
//   - Growth (Propagation, _PIO_GrowPulse): the flames of a growing bed lick a little higher and its rim glows a little
//     hotter while its ring creeps out; no white-hot band (that stays the capture's).
//   - Inherited land (KillInheritance): TerritoryField sweeps a fill wave in the killer's color over it, so the
//     spreading-fire front above crosses the land the killer takes.
// Fetch budget (Medium): territory field 1, wide relief 1 (Gather), reveal 1 (Gather), pocket 1, actor 1, owner tap 1,
// scorch 1 (wave D-2: only while a scorch exists; it replaced the actor glow tap) = 7, with or without actors (the actor
// path needs no forward differences: no relief to shade, and fwidth(fA) is taken outside the dynamic branch). High uses
// B-spline territory fetches (4). Low: 5 (6 while a scorch exists).
#ifndef PIO_FIRE_COMPOSITE_INCLUDED
#define PIO_FIRE_COMPOSITE_INCLUDED

#include "Assets/Resources/Shaders/LiquidCommon.hlsl"
#include "Assets/Resources/Shaders/CountryDistance.hlsl"

// Gate C note: the URP Unlit Shader Graph forward pass is "#pragma target 2.0" on every platform, so SHADER_TARGET is
// 20 here and PIO_FIRE_GATHER is never defined in the shipped shader: the bilinear fallback paths below are what runs on
// Windows and on Android. The Gather paths are kept for a future target 4.5 forward pass.
#if defined(PLATFORM_SUPPORT_GATHER) && (SHADER_TARGET >= 45)
#define PIO_FIRE_GATHER 1
#endif

#define PIO_FIRE_ACTOR_MIN 0.003
#define PIO_FIRE_STRIPE_PERIOD 0.35
#define PIO_FIRE_STRIPE_OPACITY 0.66
#define PIO_FIRE_WIDE_SIGMA 0.267      // u: width of the wide relief field across a straight edge (2.13 mask texels)
#define PIO_FIRE_NEAR 1.2              // u: no flame, glow or fill front shows farther than this outside a bed
#define PIO_FIRE_OWNER_OFFSET 0.35     // u: the owner tap looks this far inward along the normal
#define PIO_FIRE_OWNER_REACH 0.55      // u: the pixel's own narrow field names its owner at least this far out
#define PIO_FIRE_GATE_DEPTH 0.16       // u: the fill gate is read this far inside the contour
#define PIO_FIRE_AGE_BAND 0.4          // s: per-texel clamp of the age for the front gate
#define PIO_FIRE_AGE_WARM 0.8          // s: fresh embers settle within this time (per-texel clamp of the warm age)
#define PIO_FIRE_JITTER 0.05           // u: ragged reveal sampling
#define PIO_FIRE_COAL_FREQ 1.75        // coals per unit (cellular noise frequency)
#define PIO_FIRE_WHITE float3(1.75, 1.6, 1.35)
#define PIO_FIRE_GROW_REACH 0.4        // wave D-2: a growing bed's flames reach this much farther (fraction)
#define PIO_FIRE_GROW_HEAT 0.24        // ... and its rim burns this much hotter
#define PIO_FIRE_ASH float3(0.085, 0.078, 0.072)   // wave D-2: linear grey of scorched ash
#define PIO_FIRE_EMBER float3(1.0, 0.30, 0.06)     // ... and of its dying embers

// Wave D-2 rim (header): signed distance (world units, > 0 outside) to the border of the grid rectangle and its outward
// normal. No derivative.
float PIO_FireGridBorder(float2 w, out float2 nOut)
{
    float2 halfR = _PIO_ArenaRect.zw * 0.5;
    float2 rel = w - (_PIO_ArenaRect.xy + halfR);
    float2 q = abs(rel) - halfR;
    bool alongX = q.x > q.y;
    nOut = alongX ? float2(rel.x >= 0.0 ? 1.0 : -1.0, 0.0) : float2(0.0, rel.y >= 0.0 ? 1.0 : -1.0);
    return alongX ? q.x : q.y;
}

// Logistic approximation of the standard normal CDF: the profile of a blurred straight edge.
float PIO_FireEdgeProfile(float x)
{
    return 1.0 / (1.0 + exp(-1.702 * x));
}

float PIO_FireMax4(float4 v)
{
    return max(max(v.x, v.y), max(v.z, v.w));
}

// One-hot mask of the largest channel (the first one on ties).
float4 PIO_FireArgmax(float4 v)
{
    float m = PIO_FireMax4(v);
    float4 e = step(m, v);
    e.y *= 1.0 - e.x;
    e.z *= saturate(1.0 - e.x - e.y);
    e.w *= saturate(1.0 - e.x - e.y - e.z);
    return e;
}

float3 PIO_FireColorOf(float4 m)
{
    return m.x * _PIO_Colors[0].rgb + m.y * _PIO_Colors[1].rgb + m.z * _PIO_Colors[2].rgb + m.w * _PIO_Colors[3].rgb;
}

// The hot core color of the player (FireTheme.SecondaryColors, published per sim player).
float3 PIO_FireHotOf(float4 m)
{
    return m.x * _PIO_SecondaryColors[0].rgb + m.y * _PIO_SecondaryColors[1].rgb
         + m.z * _PIO_SecondaryColors[2].rgb + m.w * _PIO_SecondaryColors[3].rgb;
}

// Integer hash of a lattice point, in [0, 1).
float PIO_FireHash(float2 cell)
{
    uint2 q = (uint2)((int2)cell + 65536);
    uint h = (q.x * 1597334677u) ^ (q.y * 3812015801u);
    h = h * 0x9E3779B1u;
    h ^= h >> 16;
    h *= 0x85EBCA6Bu;
    h ^= h >> 13;
    return (float)h * (1.0 / 4294967296.0);
}

float2 PIO_FireHash2(float2 cell)
{
    return float2(PIO_FireHash(cell), PIO_FireHash(cell + float2(113.0, 57.0)));
}

float PIO_FireNoise(float2 p)
{
    float2 i = floor(p);
    float2 f = p - i;
    f = f * f * (3.0 - 2.0 * f);
    float a = PIO_FireHash(i);
    float b = PIO_FireHash(i + float2(1.0, 0.0));
    float c = PIO_FireHash(i + float2(0.0, 1.0));
    float d = PIO_FireHash(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

// 2 or 3 octaves of value noise, normalized to [0, 1].
float PIO_FireFbm(float2 p, bool third)
{
    float n = PIO_FireNoise(p) * 0.5714;
    n += PIO_FireNoise(p * 2.03 + float2(17.1, 3.7)) * 0.2857;
    [branch] if (third)
    {
        n += PIO_FireNoise(p * 4.11 + float2(-5.3, 11.9)) * 0.1429;
    }
    else
    {
        n += 0.0714;
    }
    return n;
}

// Animated cellular noise over the 3 x 3 neighbourhood (High): (F1, F2, hash of the nearest cell), and the position of
// the nearest feature point (the coal's centre, in noise space). The feature points drift slowly inside their cells.
float3 PIO_FireCells9(float2 p, float time, out float2 centre)
{
    float2 i = floor(p);
    float2 f = p - i;
    float f1 = 8.0;
    float f2 = 8.0;
    float id = 0.0;
    float2 best = float2(0.0, 0.0);
    [unroll] for (int y = -1; y <= 1; y++)
    {
        [unroll] for (int x = -1; x <= 1; x++)
        {
            float2 c = float2((float)x, (float)y);
            float2 h = PIO_FireHash2(i + c);
            float2 o = c + 0.5 + 0.36 * sin(time * 0.33 + 6.2831853 * h) - f;
            float d = dot(o, o);
            if (d < f1)
            {
                f2 = f1;
                f1 = d;
                id = h.x;
                best = o;
            }
            else if (d < f2)
            {
                f2 = d;
            }
        }
    }
    centre = p + best;
    return float3(sqrt(f1), sqrt(f2), id);
}

// The same coals over the 2 x 2 cells whose centres surround p (Medium: 4 cells instead of 9). With feature points
// kept within 0.33 of their cell centre, F1 is always exact and every border between two coals lies inside the block,
// so the crust lines match the 3 x 3 search (same hash, same coal identities as High).
float3 PIO_FireCells4(float2 p, float time, out float2 centre)
{
    float2 i = floor(p - 0.5);
    float2 f = p - i;
    float f1 = 8.0;
    float f2 = 8.0;
    float id = 0.0;
    float2 best = float2(0.0, 0.0);
    [unroll] for (int y = 0; y <= 1; y++)
    {
        [unroll] for (int x = 0; x <= 1; x++)
        {
            float2 c = float2((float)x, (float)y);
            float2 h = PIO_FireHash2(i + c);
            float2 o = c + 0.5 + 0.33 * sin(time * 0.33 + 6.2831853 * h) - f;
            float d = dot(o, o);
            if (d < f1)
            {
                f2 = f1;
                f1 = d;
                id = h.x;
                best = o;
            }
            else if (d < f2)
            {
                f2 = d;
            }
        }
    }
    centre = p + best;
    return float3(sqrt(f1), sqrt(f2), id);
}

// Low: the same 2 x 2 cellular look with static feature points, one hash per cell (never thresholded value noise,
// which drew rounded squares and contour rings on the lattice).
float3 PIO_FireCellsStatic(float2 p, out float2 centre)
{
    float2 i = floor(p - 0.5);
    float2 f = p - i;
    float f1 = 8.0;
    float f2 = 8.0;
    float id = 0.0;
    float2 best = float2(0.0, 0.0);
    [unroll] for (int y = 0; y <= 1; y++)
    {
        [unroll] for (int x = 0; x <= 1; x++)
        {
            float2 c = float2((float)x, (float)y);
            float hx = PIO_FireHash(i + c);
            float2 h = float2(hx, frac(hx * 61.73));
            float2 o = c + 0.5 + 0.33 * (2.0 * h - 1.0) - f;
            float d = dot(o, o);
            if (d < f1)
            {
                f2 = f1;
                f1 = d;
                id = hx;
                best = o;
            }
            else if (d < f2)
            {
                f2 = d;
            }
        }
    }
    centre = p + best;
    return float3(sqrt(f1), sqrt(f2), id);
}

// Ember color ramp: heat 0 = dark crust, about 0.6 = the flame color, 1 = the hot core (HDR), above 1 = white hot.
float3 PIO_FireRamp(float heat, float3 flame, float3 hot)
{
    float3 crust = flame * 0.05 + float3(0.006, 0.004, 0.003);
    float3 c = lerp(crust, flame * 0.55, smoothstep(0.0, 0.42, heat));
    c = lerp(c, flame, smoothstep(0.38, 0.72, heat));
    c = lerp(c, hot * 1.25, smoothstep(0.7, 1.05, heat));
    c += hot * max(heat - 1.05, 0.0) * 1.8;
    return c;
}

// Cubic B-spline reconstruction from 4 bilinear taps (Sigg and Hadwiger). texel = (1/w, 1/h, w, h).
float4 PIO_FireSampleBSpline(TEXTURE2D_PARAM(tex, smp), float2 uv, float4 texel)
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

// Signed outward distance (world units, > 0 outside) of a point whose Gaussian-blurred edge field reads t, for a
// straight edge: t = Phi(-d / sigma). Inverse normal CDF by Abramowitz and Stegun 26.2.23 (|error| < 4.5e-4 in z).
float PIO_FireEdgeDistance(float t, float sigma)
{
    float p = clamp(min(t, 1.0 - t), 1e-7, 0.5);
    float s = sqrt(-2.0 * log(p));
    float z = s - (2.515517 + s * (0.802853 + s * 0.010328)) / (1.0 + s * (1.432788 + s * (0.189269 + s * 0.001308)));
    return (t < 0.5 ? z : -z) * sigma;
}

// The signed world distance d to the contour (> 0 outside) from the wide relief field (max t_wide, height .w) at uv,
// and its world gradient. With Gather (shader model 4.5 and up) each of the four texels of the bilinear footprint is
// turned into a distance first and the DISTANCES are interpolated: a distance field is nearly linear across an edge, so
// its bilinear gradient is smooth from texel to texel (the gradient of the interpolated field itself jumps by tens of
// percent at every texel boundary in the tail of the Gaussian, which made the normal, the reach of the tongues and the
// gate's sample point jump). The gather is taken at the centre of the footprint, so the hardware's choice of texels
// always matches the weights computed here. Without Gather (the GLES3 target 2.0 subshader): one bilinear fetch, and
// grad is the outward direction of the relief gradient of the same texel (-dH/dx, -dH/dy, exact per pixel but zero
// where the relief is flat, outside the beds and deep inside); the caller blends it with screen derivatives of d,
// taken outside any dynamic branch. |grad| is about 1 along an edge and drops where edges meet (saddles between
// lobes): a measure of how well the normal is defined.
float PIO_FireWideDistance(float2 uv, out float2 grad)
{
#ifdef PIO_FIRE_GATHER
    float2 st = uv * _PIO_TerritoryTexel.zw - 0.5;
    float2 i = floor(st);
    float2 f = st - i;
    float4 g = GATHER_ALPHA_TEXTURE2D(_PIO_TerritoryHeight, sampler_PIO_TerritoryHeight, (i + 1.0) * _PIO_TerritoryTexel.xy);
    float4 dz = float4(PIO_FireEdgeDistance(g.x, PIO_FIRE_WIDE_SIGMA), PIO_FireEdgeDistance(g.y, PIO_FIRE_WIDE_SIGMA),
                       PIO_FireEdgeDistance(g.z, PIO_FIRE_WIDE_SIGMA), PIO_FireEdgeDistance(g.w, PIO_FIRE_WIDE_SIGMA));
    float2 texelW = _PIO_ArenaRect.zw * _PIO_TerritoryTexel.xy;
    grad = float2(lerp(dz.z - dz.w, dz.y - dz.x, f.y), lerp(dz.x - dz.w, dz.y - dz.z, f.x)) / texelW;
    return lerp(lerp(dz.w, dz.z, f.x), lerp(dz.x, dz.y, f.x), f.y);
#else
    float4 h = SAMPLE_TEXTURE2D_LOD(_PIO_TerritoryHeight, sampler_PIO_TerritoryHeight, uv, 0);
    grad = _PIO_TerritoryUnorm > 0.5 ? (0.5 - h.yz) * (2.0 * PIO_GRAD_RANGE) : -h.yz;
    return PIO_FireEdgeDistance(h.w, PIO_FIRE_WIDE_SIGMA);
#endif
}

// Ages of the reveal at uv (seconds since the cell was revealed), for the front gate (clamped at PIO_FIRE_AGE_BAND)
// and the fresh embers (clamped at PIO_FIRE_AGE_WARM). The reveal texture holds -1000 for cells present at session
// start, and a bilinear fetch that mixes a fresh time with that sentinel (or with any old time) snaps from fresh to
// ancient inside one cell. So the four texels are gathered and each age is clamped BEFORE the interpolation: old and
// never-revealed cells all read the clamp, and a fresh area fades into them over one texel with no step. One fetch
// (Gather, shader model 4.5 and up, taken at the footprint centre); without Gather, one bilinear fetch.
void PIO_FireRevealAges(float2 uv, out float ageBand, out float ageWarm)
{
#ifdef PIO_FIRE_GATHER
    float2 st = uv * _PIO_RevealTexel.zw - 0.5;
    float2 i = floor(st);
    float2 f = st - i;
    float4 r = GATHER_RED_TEXTURE2D(_PIO_RevealTime, sampler_PIO_RevealTime, (i + 1.0) * _PIO_RevealTexel.xy);
    float4 age = max(_PIO_Now - r, 0.0);
    float4 aB = min(age, PIO_FIRE_AGE_BAND);
    float4 aW = min(age, PIO_FIRE_AGE_WARM);
    ageBand = lerp(lerp(aB.w, aB.z, f.x), lerp(aB.x, aB.y, f.x), f.y);
    ageWarm = lerp(lerp(aW.w, aW.z, f.x), lerp(aW.x, aW.y, f.x), f.y);
#else
    float r = SAMPLE_TEXTURE2D_LOD(_PIO_RevealTime, sampler_PIO_RevealTime, uv, 0).r;
    float age = max(_PIO_Now - r, 0.0);
    ageBand = min(age, PIO_FIRE_AGE_BAND);
    ageWarm = min(age, PIO_FIRE_AGE_WARM);
#endif
}

// Exact signed distance of the rounded-square arena (< 0 inside).
float PIO_FireArenaSdf(float2 p)
{
    float r = _PIO_ArenaShape.y;
    float2 q = abs(p) - (_PIO_ArenaShape.x - r);
    return PIO_OptionalCountryDistance(p, length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r);
}

// One side of the flame band: color (rgb) and coverage (a) of the tongues at band coordinate h (0 on the contour, 1 at
// the reach), for the stretched flame noise nS in [0, 1], a reach in world units and the fill gate. The coverage is 0
// from h = 1 on, so the band ends continuously where its dynamic branch stops.
float4 PIO_FireTongue(float nS, float h, float reach, float3 flame, float3 hot, float gate)
{
    float f = nS - h;                                          // > 0 inside a tongue, larger toward its root
    float body = saturate(f * reach * 18.0);                   // soft edge of about 0.055 u
    body *= 0.7 + 0.3 * (1.0 - smoothstep(0.6, 1.0, h));      // the tips thin out
    float core = saturate((f - 0.42) * 3.5) * saturate(1.0 - 1.2 * h);   // patchy: only the strong tongues' bases
    float3 col = lerp(flame * 1.2, hot * 1.55, core);
    col = lerp(col, PIO_FIRE_WHITE, gate * core);            // white hot at the base of the fill front
    return float4(col, body);
}

// Wave D-2 scorched ground (header): grey ash with dying embers over the charred ground g. level = the scorch level
// (TerritoryField fades it: in with the burn out of the bed, out over the last 2 s), pix = world units per pixel. The
// embers die before the ash: they need a level near 1. No derivative: called inside the ground branch.
float3 PIO_FireAsh(float3 g, float level, float2 w, float time, float pix)
{
    float rag = PIO_FireNoise(w * 2.1 + float2(5.0, 1.0)) * 0.6 + PIO_FireNoise(w * 5.7 + float2(-2.0, 9.0)) * 0.4;
    float edge = level - 0.5 + 0.45 * (rag - 0.5);
    float cover = saturate(edge / max(0.08, 2.0 * pix) + 0.5);
    float mottle = PIO_FireNoise(w * 1.3 + float2(41.0, 3.0));
    float fine = PIO_FireNoise(w * 17.0 + float2(3.0, 7.0));
    float3 ash = PIO_FIRE_ASH * (0.72 + 0.45 * mottle) * (0.9 + 0.2 * fine);
    // Embers: one candidate per cell of a 0.4 u lattice, a small soft speck that breathes and sometimes flares.
    float2 cellP = w * 2.5;
    float2 cid = floor(cellP);
    float hsh = PIO_FireHash(cid + float2(17.0, 3.0));
    float2 ctr = cid + 0.25 + 0.5 * float2(hsh, frac(hsh * 47.13));
    float dist = length(cellP - ctr);
    float live = step(0.72, hsh) * smoothstep(0.55, 0.95, level) * cover;
    float breath = 0.55 + 0.45 * sin(time * (1.3 + 2.1 * hsh) + hsh * 40.0);
    float speck = saturate(1.0 - dist / (0.16 + 0.1 * hsh)) * live * breath;
    float3 c = lerp(g, ash, cover);
    return c + PIO_FIRE_EMBER * (speck * speck * 0.9) + PIO_FIRE_EMBER * (0.04 * live * breath * saturate(1.0 - dist));
}

void PIO_FireCompositeSG_float(float4 VertexColor, float2 UV1, out float3 BaseColor, out float Alpha)
{
    float2 w = UV1;
    float dxw = ddx(w.x);
    float dyw = ddy(w.y);
    float px = max(fwidth(w.x), 1e-5);
    float py = max(fwidth(w.y), 1e-5);
    float pix = max(px, py);
    float time = _PIO_Time.x;
    bool bicubic = _PIO_Quality.z > 0.5;       // High: B-spline territory, 3 x 3 coals, 3 flame octaves
    bool rich = _PIO_Quality.y > 0.5;          // Medium and High: owner and glow taps, cracks, animated coals
    float actorScale = max(_PIO_ActorScale, 1e-4);

    // ---- Territory field (narrow): owner, contour, crease ---------------------------------------------------------
    float2 uvT = (w - _PIO_ArenaRect.xy) / _PIO_ArenaRect.zw;
    float4 tRaw;
    [branch] if (bicubic)
    {
        tRaw = PIO_FireSampleBSpline(TEXTURE2D_ARGS(_PIO_TerritoryField, sampler_PIO_TerritoryField), uvT, _PIO_TerritoryTexel);
    }
    else
    {
        tRaw = SAMPLE_TEXTURE2D_LOD(_PIO_TerritoryField, sampler_PIO_TerritoryField, uvT, 0);
    }
    // Wave D-2 rim (header): a bed that reaches the grid border ends there.
    float2 nB;
    float dB = PIO_FireGridBorder(w, nB);
    tRaw = min(tRaw, PIO_FireEdgeProfile(-dB / PIO_WALL_SIGMA_NARROW));
    float4 mj = PIO_FireArgmax(tRaw);
    float tj = dot(tRaw, mj);
    float fadeJ = saturate(dot(_PIO_PlayerFade, mj));
    float burn = 1.0 - fadeJ;
    float cT = saturate((tj - 0.5) / max(fwidth(tj), 1e-4) + 0.5);
    // Crease: where two beds touch, blend the two strongest channels over about a pixel and draw a dark seam.
    float4 others = tRaw * (1.0 - mj);
    float4 m2 = PIO_FireArgmax(others);
    float t2 = dot(others, m2);
    float gap = tj - t2;
    float wj = 0.5 + 0.5 * saturate(gap / max(fwidth(gap), 1e-4));
    float3 flameJ = PIO_FireColorOf(mj);
    float3 hotJ = PIO_FireHotOf(mj);

    // ---- Wide relief field: world distance to the contour and the outward normal -----------------------------------
    float2 gD;
    float d = PIO_FireWideDistance(uvT, gD);                      // > 0 outside the beds, < 0 inside (u)
#ifndef PIO_FIRE_GATHER
    // Without Gather: the screen derivatives of d (constant over each 2 x 2 quad on many GPUs) give the normal and its
    // quality; where the relief slopes (just inside the contour, where the gate and the owner tap are read) its
    // per-pixel direction replaces theirs, so the normal does not step from quad to quad there.
    float2 gS = float2(ddx(d) / (abs(dxw) > 1e-7 ? dxw : 1e-7), ddy(d) / (abs(dyw) > 1e-7 ? dyw : 1e-7));
    float hLen = length(gD);
    gD = lerp(gS, gD * (length(gS) / max(hLen, 1e-5)), smoothstep(0.03, 0.2, hLen));
#endif
    // Wave D-2 rim: the contour distance of an intersection is the larger one (the border is the edge there).
    [flatten] if (dB > d)
    {
        d = dB;
        gD = nB;
    }
    float gLen = length(gD);
    float2 nOut = gLen > 1e-4 ? gD / gLen : float2(0.0, 1.0);
    float normalOk = smoothstep(0.45, 0.8, gLen);                // about 1 along edges, 0 where edges meet
    float up01 = 0.5 + 0.5 * nOut.y;                              // 1 on edges facing screen up, 0 facing down

    // ---- The coals (only where the bed shows), early: their centres carry the age of the fresh embers ---------------
    float3 cells = float3(1.0, 1.0, 0.0);
    float2 coalAt = w;
    [branch] if (cT > 0.0)
    {
        [branch] if (bicubic)
        {
            cells = PIO_FireCells9(w * PIO_FIRE_COAL_FREQ, time, coalAt);
        }
        else if (rich)
        {
            cells = PIO_FireCells4(w * PIO_FIRE_COAL_FREQ, time, coalAt);
        }
        else
        {
            cells = PIO_FireCellsStatic(w * PIO_FIRE_COAL_FREQ, coalAt);
        }
        coalAt *= 1.0 / PIO_FIRE_COAL_FREQ;
    }

    // ---- Reveal age: the gate of the spreading fire (only near a bed) -----------------------------------------------
    float gate = 0.0;
    float warm = 0.0;
    [branch] if (d < PIO_FIRE_NEAR)
    {
        // Near the contour and outside: read inside the contour along the normal (the cells the flames burn from), with
        // a small ragged jitter. Deeper inside: read at the centre of the pixel's coal, so a coal is fresh or old as a
        // whole and the boundary between fresh and old embers runs along the dark crust, never along the texel steps.
        float2 jit = PIO_FIRE_JITTER * float2(sin(w.y * 23.0 + time * 4.1), sin(w.x * 21.0 - time * 3.7));
        float2 wEdge = w - nOut * clamp(d + PIO_FIRE_GATE_DEPTH, 0.0, PIO_FIRE_NEAR + PIO_FIRE_GATE_DEPTH) + jit;
        float2 wR = lerp(coalAt, wEdge, smoothstep(-0.42, -0.2, d));
        float ageBand;
        float ageWarm;
        PIO_FireRevealAges((wR - _PIO_ArenaRect.xy) / _PIO_ArenaRect.zw, ageBand, ageWarm);
        // A Gaussian of the age centred at 0.08 s (width 0.08 s, a softer rise before the peak), zero after 0.3 s.
        // Outside, where edges meet and the normal is not defined, the boost fades instead of jumping.
        float e = max(ageBand - 0.08, (0.08 - ageBand) * 0.45) * (1.0 / 0.08);
        gate = exp(-e * e) * (1.0 - smoothstep(0.24, 0.3, ageBand)) * lerp(1.0, normalOk, saturate(d / 0.1 + 1.0));
        warm = 1.0 - smoothstep(0.05, PIO_FIRE_AGE_WARM, ageWarm);
    }

    // ---- Actor field (sampled here so fwidth(fA) stays outside the dynamic branch) --------------------------------
    float2 uvA = (w - _PIO_ActorRect.xy) / _PIO_ActorRect.zw;
    float4 a = SAMPLE_TEXTURE2D_LOD(_PIO_ActorField, sampler_PIO_ActorField, uvA, 0) / actorScale;
    float maxA = PIO_FireMax4(a);
    float4 mk = PIO_FireArgmax(a);
    float tk = dot(tRaw * _PIO_PlayerFade, mk);
    float fA = dot(a, mk) + tk;
    float fwA = max(fwidth(fA), 1e-4);

    // ---- Owner of the outer flames (Medium, High): the narrow field 0.35 u inward along the normal ------------------
    float4 tIn = float4(0.0, 0.0, 0.0, 0.0);
    [branch] if (rich && d > -0.1 && d < PIO_FIRE_NEAR)
    {
        float2 wO = w - nOut * PIO_FIRE_OWNER_OFFSET;
        tIn = SAMPLE_TEXTURE2D_LOD(_PIO_TerritoryField, sampler_PIO_TerritoryField, (wO - _PIO_ArenaRect.xy) / _PIO_ArenaRect.zw, 0);
    }
    float4 mo = PIO_FireArgmax(tRaw + 1e-4 * tIn);
    float ownerKnown = smoothstep(2e-7, 4e-6, PIO_FireMax4(tRaw + tIn));
    float3 flameO = PIO_FireColorOf(mo);
    float3 hotO = PIO_FireHotOf(mo);
    float fadeO = saturate(dot(_PIO_PlayerFade, mo));
    float aliveO = fadeO * fadeO;
    float aliveJ = fadeJ * fadeJ;
    // Wave D-2 growth (Propagation): the envelope of the flames' owner and of the bed's.
    float growO = dot(_PIO_GrowPulse, mo);
    float growJ = dot(_PIO_GrowPulse, mj);

    // ---- The flame band: tongues outward over the ground and inward over the rim -----------------------------------
    // Outward reach: about 0.85 u on edges facing up, 0.3 u facing down; the fill front adds up to 75 %, a growing bed
    // up to PIO_FIRE_GROW_REACH. Capped where the owner is still known (the owner tap adds its offset on Medium and High).
    float reachCap = PIO_FIRE_OWNER_REACH + (rich ? PIO_FIRE_OWNER_OFFSET : 0.0);
    float reachOut = min(lerp(0.3, 0.85, up01) * (1.0 + 0.75 * gate + PIO_FIRE_GROW_REACH * growO), reachCap);
    float reachIn = min((0.42 + 0.08 * up01) * (1.0 + 0.6 * gate), 0.7);
    float3 flameAdd = float3(0.0, 0.0, 0.0);
    float4 flameIn = float4(0.0, 0.0, 0.0, 0.0);
    [branch] if (d < reachOut && d > -reachIn && max(aliveO, aliveJ) > 0.0)
    {
        // One domain-warped noise, stretched along y and rising toward screen up (2 warps and 3 octaves on High, 2 and
        // 2 on Medium, 1 and 2 on Low).
        float2 fq = w * float2(3.4, 1.5);
        float2 warp;
        warp.x = PIO_FireNoise(fq * 0.8 + float2(0.0, -time * 1.3));
        [branch] if (rich)
        {
            warp.y = PIO_FireNoise(fq * 0.8 + float2(5.2, -time * 1.65));
        }
        else
        {
            warp.y = 1.0 - warp.x;
        }
        float flameN = PIO_FireFbm(fq + 1.7 * warp + float2(0.0, -time * 2.7), bicubic);
        float nS = saturate((flameN - 0.5) * 2.4 + 0.55);       // stretched: a few tongues reach the full reach
        float4 tO = PIO_FireTongue(nS, max(d, 0.0) / max(reachOut, 1e-3), reachOut, flameO, hotO, gate);
        flameAdd = tO.rgb * (tO.a * (1.0 + 0.45 * gate) * aliveO * ownerKnown * (1.0 - cT));
        float4 tI = PIO_FireTongue(nS, max(-d, 0.0) / reachIn, reachIn, flameJ, hotJ, gate);
        flameIn = float4(tI.rgb, tI.a * 0.7 * aliveJ);
    }

    // ---- Ember bed (only where the bed shows) -----------------------------------------------------------------------
    float3 bed = float3(0.0, 0.0, 0.0);
    float dissolve = 1.0;
    [branch] if (cT > 0.0)
    {
        float crust = smoothstep(0.03, 0.17, cells.y - cells.x);
        float breath = 0.5 + 0.5 * sin(time * (0.7 + 0.8 * cells.z) + cells.z * 6.2831853);
        float slow = PIO_FireNoise(w * 0.6 + float2(time * 0.06, -time * 0.04));
        float zone = PIO_FireNoise(w * 0.3 + float2(-time * 0.025, time * 0.02));
        // Each coal has its own heat, breathes slowly, glows hotter at its centre; broad zones burn hotter or dimmer.
        float coal = 0.24 + 0.32 * cells.z + 0.18 * breath + 0.26 * zone + 0.08 * slow - 0.4 * cells.x;
        // Twinkle: now and then one coal flares at its centre, picked per coal and per third of a second.
        float slot = floor(time * 3.0);
        float pick = PIO_FireHash(float2(floor(cells.z * 8192.0), slot));
        float twinkle = smoothstep(0.86, 0.95, pick) * sin(frac(time * 3.0) * 3.14159265) * (1.0 - smoothstep(0.04, 0.3, cells.x));
        float heat = lerp(0.04 + 0.05 * slow, coal + 0.45 * twinkle, crust);
        float rim = saturate(1.0 + d / 0.3);                            // 1 on the contour, 0 at 0.3 u inside
        heat += (0.14 + PIO_FIRE_GROW_HEAT * growJ) * rim * rim;         // a little hotter by the edge (more while growing)
        float band = (d + 0.14) * (1.0 / 0.2);
        heat += 1.05 * gate * exp(-band * band) + 0.14 * warm * crust;   // the white-hot front band, fresh embers
        heat *= 1.0 - burn;
        bed = PIO_FireRamp(heat, flameJ, hotJ);
        float3 bed2 = PIO_FireRamp(heat, PIO_FireColorOf(m2), PIO_FireHotOf(m2));
        bed = lerp(bed2, bed, wj);
        float seam = (1.0 - smoothstep(0.0, 0.13, gap)) * smoothstep(0.22, 0.42, t2);
        bed *= 1.0 - 0.8 * seam;
        // The inner tongues burn over the rim.
        bed = lerp(bed, flameIn.rgb, flameIn.a);
        // Burn out: the bed cools to grey ash, then crumbles away.
        [branch] if (burn > 0.0)
        {
            float3 ash = float3(0.05, 0.044, 0.04) * (0.7 + 0.6 * slow) * lerp(0.55, 1.0, crust);
            ash += flameJ * 0.25 * smoothstep(0.75, 0.95, crust * cells.z) * saturate(1.0 - burn * 1.4);   // last glowing flecks
            bed = lerp(bed, ash, smoothstep(0.05, 0.55, burn));
            dissolve = saturate((fadeJ * 1.3 - PIO_FireNoise(w * 3.3 + float2(11.0, 0.0))) / 0.1);
        }
    }
    float bedCover = cT * dissolve;

    // ---- Ground: charred stone, cooled cracks, warm glow around the fires (only where the bed does not cover) -------
    float3 ground = float3(0.0, 0.0, 0.0);
    [branch] if (bedCover < 1.0)
    {
        float sd = PIO_FireArenaSdf(w);
        float mottle = PIO_FireNoise(w * 0.9 + float2(31.0, 4.0));
        float fine = PIO_FireNoise(w * 21.0) - 0.5;
        float3 g0 = _PIO_GroundColor.rgb;                    // #1A1412
        float3 g1 = g0 * float3(1.55, 1.42, 1.40);           // about #241A16
        float3 inside = lerp(g0, g1, smoothstep(0.25, 0.85, mottle)) * (1.0 + fine * 0.2);
        [branch] if (rich)
        {
            // Sparse: the cracks only show where a broad mask allows them. AA width from the pixel size (no fwidth).
            float mask = smoothstep(0.5, 0.78, PIO_FireNoise(w * 0.21 + float2(3.0, 9.0)));
            [branch] if (mask > 0.0)
            {
                float crackN = PIO_FireNoise(w * 0.85 + float2(7.3, -2.1)) * 0.65 + PIO_FireNoise(w * 1.9 + float2(-3.1, 5.5)) * 0.35;
                float crackW = 0.012 + 1.0 * pix;
                inside *= 1.0 - 0.32 * (1.0 - smoothstep(0.0, crackW, abs(crackN - 0.5))) * mask;
            }
        }
        inside *= 1.0 - 0.35 * (1.0 - smoothstep(0.0, 1.4, -sd));
        // Wave D-2 scorched ground (header): one LOD 0 fetch, only while a scorch exists (uniform gate), none past the
        // grid border; then the ash in its own branch.
        float scorch = 0.0;
        [branch] if (_PIO_ScorchOn > 0.5)
        {
            scorch = SAMPLE_TEXTURE2D_LOD(_PIO_RevealTime, sampler_PIO_RevealTime, uvT, 0).g * saturate(0.5 - dB / pix);
        }
        [branch] if (scorch > 0.002)
        {
            inside = PIO_FireAsh(inside, scorch, w, time, pix);
        }
        ground = PIO_ArenaFrame(inside, sd, pix, time);         // flat light grey outside, yellow neon edge (shared)
        // The glow: soft, stronger above each fire (light rises), brighter while the fire spreads (or grows).
        float glowT = 0.5 * exp(-6.0 * max(d, 0.0)) * fadeO * lerp(0.75, 1.3, up01) * ownerKnown;
        float3 glowCol = flameO * glowT * (1.0 + 0.8 * gate + 0.5 * growO);
        // Actors light the ground around them (Medium, High). Wave D-2: from the actor fetch at the pixel (the offset
        // tap's slot now serves the scorch).
        glowCol += rich ? PIO_FireColorOf(mk) * smoothstep(0.0, 0.7, saturate(maxA)) : float3(0.0, 0.0, 0.0);
        ground += glowCol * 0.2;
    }
    float3 color = lerp(ground, bed, bedCover) + flameAdd;

    // ---- Pending pockets: glowing ember stripes, no coals, no flames --------------------------------------------------
    float4 pocket = SAMPLE_TEXTURE2D_LOD(_PIO_PocketMask, sampler_PIO_PocketMask, uvT, 0);
    float4 mp = PIO_FireArgmax(pocket);
    float pm = dot(pocket, mp);
    float pocketCover = saturate((pm - 0.5) / max(fwidth(pm), 1e-4) + 0.5);
    float sd2 = (w.x + w.y) * (0.70710678 / PIO_FIRE_STRIPE_PERIOD) - time * 0.22;
    float stripe = saturate((0.25 - abs(frac(sd2) - 0.5)) / max(fwidth(sd2), 1e-4) + 0.5);
    float glimmer = 0.86 + 0.14 * sin(time * 3.1 + (w.x - w.y) * 1.9);
    float3 stripeCol = lerp(PIO_FireColorOf(mp), PIO_FireHotOf(mp), 0.22) * 1.08 * glimmer;
    color = lerp(color, stripeCol, PIO_FIRE_STRIPE_OPACITY * stripe * pocketCover);

    // ---- Actors: burning fuses ----------------------------------------------------------------------------------------
    [branch] if (maxA >= PIO_FIRE_ACTOR_MIN)
    {
        float3 fc = PIO_FireColorOf(mk);
        float3 fh = PIO_FireHotOf(mk);
        float cA = saturate((fA - 0.5) / fwA + 0.5);
        float core = saturate((fA - 0.9) / fwA + 0.5);
        float onOwn = smoothstep(0.42, 0.85, tk);
        float2 sq = w * float2(6.5, 3.0);
        float fn = PIO_FireNoise(sq + float2(0.0, -time * 4.6)) * 0.6 + PIO_FireNoise(sq * 2.1 + float2(3.7, -time * 6.8)) * 0.4;
        float lick = saturate((fA - (0.48 - 0.36 * fn * fn * 1.3)) / 0.08);
        float3 sheath = lerp(fc * 1.3, fh * 1.65, saturate(fn * 1.8 - 0.6));
        // The cord: dark, smouldering, with embers crawling along it.
        float crawl = smoothstep(0.7, 0.95, PIO_FireNoise(w * 7.0 + float2(time * 1.7, -time * 2.3)));
        float3 cord = lerp(fc * 0.22 + float3(0.012, 0.008, 0.006), fh * 1.3, crawl * 0.9);
        float3 fuse = lerp(sheath, cord, core * 0.85);
        float3 tip = lerp(fc * 1.1, fh * 1.4, fn);
        fuse = lerp(tip, fuse, cA);
        // A faint leftover of the actor field (a thread just absorbed by a spreading fill) fades out instead of drawing
        // specks of cord over the flames.
        float actorA = max(cA, lick * 0.9) * (1.0 - onOwn) * smoothstep(PIO_FIRE_ACTOR_MIN, 0.04, maxA);
        color = lerp(color, fuse, actorA);
    }

    BaseColor = max(color, 0.0);
    Alpha = 1.0;
}

void PIO_FireCompositeSG_half(half4 VertexColor, half2 UV1, out half3 BaseColor, out half Alpha)
{
    float3 baseColor;
    float alpha;
    PIO_FireCompositeSG_float((float4)VertexColor, (float2)UV1, baseColor, alpha);
    BaseColor = (half3)baseColor;
    Alpha = (half)alpha;
}

#endif // PIO_FIRE_COMPOSITE_INCLUDED
