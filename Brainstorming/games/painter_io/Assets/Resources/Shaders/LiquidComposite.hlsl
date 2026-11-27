// LiquidComposite.hlsl - the Custom Function of LiquidComposite.shadergraph (docs/CONTRACT.md 12.2 item 3). Written by
// B1; owned by LIQ since wave B-2 (liquid polish against docs/reference_gouttes.png, contract 25.6).
// Its .meta carries the fixed GUID 10ca3f7c333c41cbbebe89520819584d: the graph references this file by that GUID.
//
// One full-resolution pass over the static LiquidSurface quad ([-40, 40]^2, z = 0). LiquidSurface writes the world
// position of each vertex into uv1, so UV1 is the world position w of the pixel. Per pixel:
// - Territory layer: t_i from _PIO_TerritoryField times _PIO_PlayerFade (sampled at w plus a slow wobble of at most
//   0.04 u), j = argmax t_i, cT = saturate((t_j - 0.5) / fwidth(t_j) + 0.5) (the contour). The relief HT and its
//   gradient come from _PIO_TerritoryHeight (H of the wider relief field, scaled by the fade of j). Ground (navy, faint
//   woven grain, a soft vignette, a soft rim shadow, light grey outside the arena past a yellow neon line) under it, with a contact darkening
//   right around the liquid (every tier, no extra fetch) and a soft lower-right drop shadow of everything (Medium and
//   High); rival actors shadow the puddles. Two colors that touch both fall to H = 0, which draws the crease: within
//   one relief texel of the contact the lit surface goes flat and darkens into an antialiased groove (wave C), and no
//   slope steeper than h0 / 2 per pixel is ever lit. The ground is shaded only where cT < 1 and the puddle only
//   where cT > 0 (wave C). Pending pockets: 45 degree stripes in the owner's color at 55 %, no relief, no gloss.
// - Fill ripple (contract 25.2): _PIO_RevealTime holds the time each cell's color arrived, so _PIO_Now - reveal is the
//   age of the liquid there. Fresh liquid carries a wave front crest and one smaller trailing ripple just behind its
//   edge: soft bands at fixed depths behind the contour (read from the wide relief field) that lift the light a little
//   and carry a wet sheen, gated by the age: they ride the advancing edge of a fill and fade within PIO_RIPPLE_LIFE
//   seconds once it stops.
// - Actor layer, only where max a_i >= 0.003: k = argmax a_i, coverage cA from fA = a_k + t_k + PIO_FLARE a_k t_k
//   (same-color fusion makes the necks; the product term widens the neck flare where a thread leaves its puddle, and
//   vanishes with either term, so the contour off the junction is unchanged). The actor height HA blends two cases by
//   "own" (how much the territory under the actor is its own color): on a rival puddle or bare ground HA = HT + H(a_k)
//   (threads keep their full height on top of rival puddles); on its own puddle HA = H(C(max(a_k, tw_k) +
//   PIO_UNION_FILLET min(a_k, tw_k))), a union with the wider relief field tw, where C leaves values <= 1 alone and
//   saturates above 1 toward 1 + PIO_MERGE_CAP (tiny): the union of thread, neck, pearl blob and puddle is one surface
//   level with the puddle at h0, with no blister, no terrace and no groove at the junction, and an actor lying on the
//   flat of its own puddle is flush with it (self crossings of a thread level off the same way). HA equals HT where a_k
//   goes to 0, and its normal is the territory normal plus the finite-difference gradient of the extra height HA - HT,
//   so the switch between the layers is seamless. The coverage AA width uses fwidth(t) taken before the dynamic branch:
//   no derivative instruction runs inside it.
// - Lighting: PIO_ShadeLiquid of each layer with nTable = normalize(-dH/dx, -dH/dy, 1).
// - Drop (wave D liq-drop, contract 28 F2: "every puddle reads as one big drop"). _PIO_TerritoryDome is a much wider
//   field (sigma 0.8 u, TerritoryField) whose value t_dome is 0.5 on a straight edge and keeps rising for 1.5 - 2 u
//   inside a large puddle. The dome profile s = C(2 t_dome - 1) (C: a soft start, C1 at the dome's foot) times the bevel
//   b = HT / h0 (0 on the contour, 1 past the narrow meniscus) gives the depth of the liquid, 0 on the edge and on thin
//   strips, 1 in the thick center of a large puddle, and the dome's lighting normal nD from the stored dome gradient.
//   The meniscus keeps its crisp narrow bevel shaded by PIO_ShadeLiquid exactly as before (its edge streaks), and the
//   dome adds its own layer: depth absorption (albedo^e, e from PIO_DROP_THIN at the thin rim to PIO_DROP_THICK in the
//   center: lighter, more translucent edge and richer thick body), a wrapped Lambert of nD (the body is lit from the
//   upper left and turns deeper on the lower right), a broad soft highlight band (a wide lobe of nD toward the key
//   light) and a sharp hot spot (a very tight lobe around a half vector tilted 12 degrees, a slope the dome reaches on
//   its upper-left flank). The ground gets a softer, stronger contact shadow on the lower right from t_dome sampled
//   toward the light (stored in the same texel). An actor on its own puddle takes the same terms (weighted by own), so
//   necks and a pearl at home stay seamless; threads on bare ground or on a rival puddle are unchanged (b = 0 or
//   own = 0). _PIO_BiomeParams.x (LiquidTheme.DropStrength) scales it all: 0 gives back the wave C puddles.
// - Biome traits (wave D-2 traits-fx, docs/BIOME_TRAITS.md 5 and 7, generic: any trait may run in this biome):
//   - Rim: with Propagation a puddle may reach the border of the grid (the arena's straight sides), where the clamped
//     fields would smear it outside the arena. The narrow field, the relief (height and gradient), the wide field and the
//     dome are limited by the analytic profiles of a straight edge lying on the border (PIO_LiquidWall), so the puddle
//     ends on the rim with its usual meniscus, bevel, drop and shadow.
//   - Scorched ground (ScorchedEarth): the G channel of the reveal fetch (no extra fetch) turns the table into a dried
//     paint stain: lighter, desaturated and matte, a faint crackle, and a darker coffee ring along its ragged edge.
//   - Growth (Propagation, _PIO_GrowPulse): a liquid creep, a soft wet crest riding just behind the advancing edge and a
//     faint film of the color spreading past it; much weaker than the fill ripple, never a capture.
// Fetch budget (Medium): territory field 1, height 1, dome 1 (wave D), pocket 1, actor 1, reveal 1, shadow taps 2 (8
// without actors; the territory shadow tap is skipped inside puddles, cT = 1); the actor path adds 2 x 2
// forward-difference fetches (actor field and relief at +x and +y: 12). Low has no shadow taps (6 and 10). High uses
// B-spline fetches and central differences (contract 12.2 item 4 allows it). Wave D-2 adds no fetch.
#ifndef PIO_LIQUID_COMPOSITE_INCLUDED
#define PIO_LIQUID_COMPOSITE_INCLUDED

#include "Assets/Resources/Shaders/LiquidCommon.hlsl"
#include "Assets/Resources/Shaders/CountryDistance.hlsl"

#define PIO_ACTOR_MIN 0.003
#define PIO_WOBBLE_AMPLITUDE 0.028     // per axis, so |d| <= 0.0396 u
#define PIO_STRIPE_PERIOD 0.35
#define PIO_STRIPE_OPACITY 0.55
#define PIO_SHADOW_SCALE 1.5           // drop shadows reach 1.5 x _PIO_ShadowOffset = 0.18 u (Bead.hlsl uses the same)
#define PIO_GROUND_SHADOW 0.70         // ground right under the soft drop shadow keeps 30 % of its light
#define PIO_SURFACE_SHADOW 0.42        // a rival actor's shadow on a puddle
#define PIO_CONTACT_SHADOWED 0.14      // contact darkening of the table around the liquid with the drop shadow on
#define PIO_CONTACT_LOW 0.32           // the same on Low, which has no shadow taps (it is then the only shadow)
#define PIO_VIGNETTE 0.16              // the table darkens by up to this much (linear) in the corners of the view
#define PIO_RELIEF_GAIN 1.7            // territory normals: slope multiplier so the rounded edges read at 30 px/u
#define PIO_INNER_STREAK 0.25          // peak of the faint inner second streak on puddle bevels
#define PIO_FLARE 1.0                  // neck flare of the same-color fusion (see the header)
#define PIO_MERGE_CAP 0.002            // a fused field above 1 saturates toward 1 + PIO_MERGE_CAP: liquid unions level at h0
#define PIO_UNION_FILLET 0.5           // own-color height union: max(a, tw) + PIO_UNION_FILLET min(a, tw)
#define PIO_RIPPLE_LIFE 0.32           // s: liquid older than this carries no ripple
#define PIO_RIPPLE_CREST1 0.80         // wide-field value of the wave front crest (about 0.2 u behind the edge)
#define PIO_RIPPLE_CREST2 0.975        // wide-field value of the trailing ripple (about 0.5 u behind the edge)
#define PIO_RIPPLE_LIFT 0.07           // a crest lifts the liquid's light by up to 7 %
#define PIO_RIPPLE_SHEEN 0.16          // and carries a wet sheen up to this much white
#define PIO_CREASE_DARK 0.25           // the contact groove between two colors darkens the albedo by up to 25 % (wave C)
// Drop (wave D, header). The dome's lighting gradient is PIO_DROP_SLOPE x b x C'(q) x 2 grad t_dome: about 0.4 at its
// steepest (0.3 - 0.5 u inside a straight edge), 0.23 at 1 u, 0.08 at 1.5 u, 0 in the flat center of a large puddle.
#define PIO_DROP_EPS 0.15              // soft start of the dome profile C(q) = (1 + eps) q^2 / (q + eps)
#define PIO_DROP_SLOPE 0.45            // lighting slope of the dome per unit of d(2 t_dome)/du
#define PIO_DROP_THIN 0.88             // albedo exponent of thin liquid (rim, thin strips): lighter, more translucent
#define PIO_DROP_THICK 1.14            // albedo exponent of the thick center: richer (depth absorption)
#define PIO_DROP_BAND_POWER 10.0       // broad soft highlight band: a wide lobe toward the key light's half vector
#define PIO_DROP_BAND 0.7
#define PIO_DROP_BAND_WHITE 0.6        // the band's sheen: the paint color lifted 60 % toward white
#define PIO_DROP_HOT_POWER 900.0       // sharp specular hot spot
#define PIO_DROP_HOT 1.0
#define PIO_DROP_HOT_DIR float3(-0.1247470, 0.1663293, 0.9781476)   // 12 degrees of tilt toward the light's azimuth
#define PIO_DROP_SHADOW 0.35           // soft contact shadow of the dome on the ground (lower right)
#define PIO_DROP_SHADOW_LO 0.2         // ... from t_dome sampled toward the light
#define PIO_DROP_SHADOW_HI 0.8
// Biome traits (wave D-2, header).
#define PIO_GROW_CREST 0.66            // wide-field value of the growth crest (just behind the advancing edge)
#define PIO_GROW_LIFT 0.6              // its strength relative to the fill ripple's crest
#define PIO_GROW_FILM 0.16             // the film of color spreading just past the edge (fraction of the color)
#define PIO_STAIN_LIFT 1.55            // a dried stain is lighter than the table ...
#define PIO_STAIN_GREY 0.75            // ... desaturated toward its grey by this much
#define PIO_STAIN_RING 0.42            // the coffee ring darkens the stain's edge by up to this much

// Logistic approximation of the standard normal CDF (|error| < 0.01): the profile of a blurred straight edge.
float PIO_EdgeProfile(float x)
{
    return 1.0 / (1.0 + exp(-1.702 * x));
}

// Wave D-2 rim (header): signed distance (world units, > 0 outside) of w to the border of the grid rectangle
// _PIO_ArenaRect and its outward normal. No derivative: usable in a branch.
float PIO_GridBorder(float2 w, out float2 nOut)
{
    float2 halfR = _PIO_ArenaRect.zw * 0.5;
    float2 rel = w - (_PIO_ArenaRect.xy + halfR);
    float2 q = abs(rel) - halfR;
    bool alongX = q.x > q.y;
    nOut = alongX ? float2(rel.x >= 0.0 ? 1.0 : -1.0, 0.0) : float2(0.0, rel.y >= 0.0 ? 1.0 : -1.0);
    return alongX ? q.x : q.y;
}

// Wave D-2 rim: limits a relief sample (H_T, dH/dx, dH/dy, max t_wide; world units) by a straight puddle edge lying on
// the grid border (signed distance dB, outward normal n): the height of that edge, PIO_Height of its wide profile, wins
// where it is lower, with its own gradient. Off the border (the usual case) the sample is returned unchanged.
float4 PIO_LiquidWallRelief(float4 h, float dB, float2 n)
{
    float tw = PIO_EdgeProfile(-dB / PIO_WALL_SIGMA_WIDE);
    float hw = PIO_Height(tw);
    float4 r = h;
    r.w = min(h.w, tw);
    [flatten] if (hw < h.x)
    {
        // dH/dt of PIO_Height times dt/d(dB) of the profile; the slope at the contour is unbounded (the caller caps it).
        float st = sqrt(max(tw, 1e-6));
        float u = max((st - 0.70711) / 0.29289, 1e-4);
        float dHdt = PIO_H0 * 0.5 / sqrt(u) * (1.0 / 0.29289) * 0.5 / st;
        float dtdB = -(1.702 / PIO_WALL_SIGMA_WIDE) * tw * (1.0 - tw);
        r.xyz = float3(hw, n * (dHdt * dtdB));
    }
    return r;
}

// Wave D-2 rim: the same for a dome sample (t_dome, dt/dx, dt/dy, t_dome toward the light) at the wobbled point w.
float4 PIO_LiquidWallDome(float4 dm, float dB, float2 n, float2 w)
{
    float td = PIO_EdgeProfile(-dB / PIO_WALL_SIGMA_DOME);
    float4 r = dm;
    [flatten] if (td < dm.x)
    {
        r.xyz = float3(td, n * (-(1.702 / PIO_WALL_SIGMA_DOME) * td * (1.0 - td)));
    }
    float2 nS;
    float dBs = PIO_GridBorder(w + float2(-0.6, 0.8) * PIO_DOME_SHADOW_REACH, nS);
    r.w = min(dm.w, PIO_EdgeProfile(-dBs / PIO_WALL_SIGMA_DOME));
    return r;
}


float PIO_Max4(float4 v)
{
    return max(max(v.x, v.y), max(v.z, v.w));
}

// One-hot mask of the largest channel (the first one on ties).
float4 PIO_ArgmaxMask(float4 v)
{
    float m = PIO_Max4(v);
    float4 e = step(m, v);
    e.y *= 1.0 - e.x;
    e.z *= saturate(1.0 - e.x - e.y);
    e.w *= saturate(1.0 - e.x - e.y - e.z);
    return e;
}

float3 PIO_ChannelColor(float4 mask)
{
    return mask.x * _PIO_Colors[0].rgb + mask.y * _PIO_Colors[1].rgb + mask.z * _PIO_Colors[2].rgb + mask.w * _PIO_Colors[3].rgb;
}

// Cubic B-spline reconstruction from 4 bilinear taps (Sigg and Hadwiger). texel = (1/w, 1/h, w, h).
float4 PIO_SampleBSpline(TEXTURE2D_PARAM(tex, smp), float2 uv, float4 texel)
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

// t_i at uv (unfaded).
float4 PIO_FetchTerritory(float2 uv, bool bicubic)
{
    float4 t;
    [branch] if (bicubic)
    {
        t = PIO_SampleBSpline(TEXTURE2D_ARGS(_PIO_TerritoryField, sampler_PIO_TerritoryField), uv, _PIO_TerritoryTexel);
    }
    else
    {
        t = SAMPLE_TEXTURE2D_LOD(_PIO_TerritoryField, sampler_PIO_TerritoryField, uv, 0);
    }
    return t;
}

// A raw relief sample converted to world units whatever the storage format: (H_T, dH/dx, dH/dy, max t of the wide field).
float4 PIO_DecodeHeight(float4 s)
{
    if (_PIO_TerritoryUnorm > 0.5)
    {
        s = float4(s.x * PIO_H0, (s.yz - 0.5) * (2.0 * PIO_GRAD_RANGE), s.w);
    }
    return s;
}

float4 PIO_FetchHeight(float2 uv, bool bicubic)
{
    float4 s;
    [branch] if (bicubic)
    {
        s = PIO_SampleBSpline(TEXTURE2D_ARGS(_PIO_TerritoryHeight, sampler_PIO_TerritoryHeight), uv, _PIO_TerritoryTexel);
    }
    else
    {
        s = SAMPLE_TEXTURE2D_LOD(_PIO_TerritoryHeight, sampler_PIO_TerritoryHeight, uv, 0);
    }
    return PIO_DecodeHeight(s);
}

// The dome field (wave D): (t_dome, dt/dx, dt/dy per world unit, t_dome toward the light) whatever the storage format.
float4 PIO_FetchDome(float2 uv, bool bicubic)
{
    float4 s;
    [branch] if (bicubic)
    {
        s = PIO_SampleBSpline(TEXTURE2D_ARGS(_PIO_TerritoryDome, sampler_PIO_TerritoryDome), uv, _PIO_TerritoryDomeTexel);
    }
    else
    {
        s = SAMPLE_TEXTURE2D_LOD(_PIO_TerritoryDome, sampler_PIO_TerritoryDome, uv, 0);
    }
    if (_PIO_TerritoryUnorm > 0.5)
    {
        s.yz = (s.yz - 0.5) * (2.0 * PIO_DOME_GRAD_RANGE);
    }
    return s;
}

float4 PIO_FetchPocket(float2 uv, bool bicubic)
{
    float4 p;
    [branch] if (bicubic)
    {
        p = PIO_SampleBSpline(TEXTURE2D_ARGS(_PIO_PocketMask, sampler_PIO_PocketMask), uv, _PIO_PocketTexel);
    }
    else
    {
        p = SAMPLE_TEXTURE2D_LOD(_PIO_PocketMask, sampler_PIO_PocketMask, uv, 0);
    }
    return p;
}

// Slow, low-frequency displacement of the puddle edges (contract 12.3: at most 0.04 u).
float2 PIO_Wobble(float2 w, float time)
{
    float2 p = w * 0.55;
    float a = sin(p.x * 1.7 + time * 0.61 + 1.4 * sin(p.y * 1.3 + time * 0.37));
    float b = sin(p.y * 1.9 - time * 0.53 + 1.4 * sin(p.x * 1.1 - time * 0.29));
    return float2(a, b) * PIO_WOBBLE_AMPLITUDE;
}

// Integer hash of a lattice point, in [0, 1).
float PIO_Hash(float2 cell)
{
    uint2 q = (uint2)((int2)cell + 65536);
    uint h = (q.x * 1597334677u) ^ (q.y * 3812015801u);
    h = h * 0x9E3779B1u;
    h ^= h >> 16;
    h *= 0x85EBCA6Bu;
    h ^= h >> 13;
    return (float)h * (1.0 / 4294967296.0);
}

float PIO_ValueNoise(float2 p)
{
    float2 i = floor(p);
    float2 f = p - i;
    f = f * f * (3.0 - 2.0 * f);
    float a = PIO_Hash(i);
    float b = PIO_Hash(i + float2(1.0, 0.0));
    float c = PIO_Hash(i + float2(0.0, 1.0));
    float d = PIO_Hash(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

// Wave D-2 scorched ground (header): a dried paint stain on the table color g. level = scorch level (0..1, already
// faded by TerritoryField), w = world position, pix = world units per pixel. No derivative: called inside the ground
// branch. The stain's ragged edge comes from a noise threshold on the level, so the 0.125 u cells never show.
float3 PIO_DriedStain(float3 g, float level, float2 w, float pix)
{
    float rag = PIO_ValueNoise(w * 2.3 + 7.0) * 0.6 + PIO_ValueNoise(w * 6.1 - 3.0) * 0.4;
    float edge = level - 0.5 + 0.42 * (rag - 0.5);
    float cover = saturate(edge / max(0.08, 2.0 * pix) + 0.5);
    float ring = exp(-edge * edge * 110.0) * saturate(level * 3.0);
    // Faint crackle of dried paint: thin dark lines where a stretched noise crosses its middle.
    float crack = PIO_ValueNoise(w * float2(4.2, 3.6) + 21.0);
    float lines = 1.0 - smoothstep(0.0, 0.035 + pix, abs(crack - 0.5));
    float grey = dot(g, float3(0.2126, 0.7152, 0.0722));
    float3 stain = lerp(g, float3(grey, grey, grey) * float3(1.08, 1.0, 0.92), PIO_STAIN_GREY) * PIO_STAIN_LIFT;
    stain *= 1.0 - 0.18 * lines * cover;
    float3 c = lerp(g, stain, cover);
    return c * (1.0 - PIO_STAIN_RING * ring);
}

// Exact signed distance of the rounded-square arena (< 0 inside).
float PIO_ArenaSdf(float2 p)
{
    float r = _PIO_ArenaShape.y;
    float2 q = abs(p) - (_PIO_ArenaShape.x - r);
    return PIO_OptionalCountryDistance(p, length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r);
}

// The table: navy with a faint woven grain (two value noises stretched across each other, about 2 px per lattice cell
// at 30 px/u so the grain does not crawl when the camera pans; multiplicative in linear space, about +/- 1 sRGB level
// like the reference) and a slow mottle, a soft inner shadow along the arena rim, then the shared arena frame (flat
// light grey outside, yellow neon line on the edge: CountryDistance.hlsl).
float3 PIO_Ground(float2 w, float pix, float time)
{
    float sd = PIO_ArenaSdf(w);
    float fibers = PIO_ValueNoise(w * float2(15.0, 5.5)) + PIO_ValueNoise(w * float2(5.5, 15.0) + 31.0) - 1.0;
    float mottle = PIO_ValueNoise(w * 1.7 + 17.0) - 0.5;
    float grain = 1.0 + fibers * 0.13 + mottle * 0.09;
    float rim = 1.0 - 0.32 * (1.0 - smoothstep(0.0, 1.4, -sd));
    float3 inside = _PIO_GroundColor.rgb * grain * rim;
    return PIO_ArenaFrame(inside, sd, pix, time);
}

// Soft darkening of the table toward the corners of the view (the actor field rectangle is the view grown by 0.6 u).
float PIO_Vignette(float2 w)
{
    float2 halfSize = max(_PIO_ActorRect.zw * 0.5, 1e-3);
    float2 r = (w - (_PIO_ActorRect.xy + halfSize)) / halfSize;
    return 1.0 - PIO_VIGNETTE * smoothstep(0.2, 1.0, dot(r, r) * 0.5);
}

// The faint inner second streak of a puddle's bevel (the reference shows a double line): the same tilt and azimuth
// windows as the streak of PIO_ShadeLiquid, at 9 degrees of tilt. Territory layer only: on the small domes of beads
// and threads it would merge with the main streak into a wedge. n need not be normalized.
float PIO_InnerStreak(float3 n)
{
    n = normalize(n);
    float tilt = saturate(length(n.xy));
    float tiltDeg = asin(tilt) * 57.2957795;
    float azimuth = dot(n.xy, float2(-0.6, 0.8)) / max(tilt, 1e-4);
    float s2 = (tiltDeg - 9.0) * (1.0 / 3.0);
    return smoothstep(0.35, 0.88, azimuth) * PIO_INNER_STREAK * exp(-s2 * s2);
}

// Drop (wave D, header): the wrapped Lambert of the dome normal nD (normalized), divided by its flat value as in
// PIO_ShadeLiquid, so a flat dome (the edge, thin strips, the flat center of a large puddle) returns exactly 1.
float PIO_DropDiffuse(float3 nD)
{
    const float wrap = 0.25;
    const float ambient = 0.32;
    float lambert = saturate((dot(nD, PIO_LIGHT_DIR) + wrap) / (1.0 + wrap));
    const float lambertFlat = (0.6606281 + wrap) / (1.0 + wrap);
    return (ambient + (1.0 - ambient) * lambert) / (ambient + (1.0 - ambient) * lambertFlat);
}

// Drop terms at a pixel (header): bevel b = HT / h0 times the drop strength (HT carries the fade of j), the dome profile
// C(2 t_dome - 1) (0 at t_dome <= 0.5, 1 in a thick center), the dome's lighting normal nD from the stored dome gradient,
// its wrapped Lambert and the absorption exponent of the albedo. No derivative: called inside the dynamic branches.
void PIO_DropTerms(float4 dm, float HT, float dropOn, out float bevel, out float3 nD, out float dropDiffuse, out float dropExp)
{
    bevel = saturate(HT / PIO_H0) * dropOn;
    float dq = saturate(2.0 * dm.x - 1.0);
    float dqe = dq + PIO_DROP_EPS;
    float dome = (1.0 + PIO_DROP_EPS) * dq * dq / dqe;
    float domeSlope = (1.0 + PIO_DROP_EPS) * dq * (dq + 2.0 * PIO_DROP_EPS) / (dqe * dqe);
    float2 gD = (PIO_DROP_SLOPE * 2.0 * bevel * domeSlope) * dm.yz;
    nD = normalize(float3(-gD, 1.0));
    dropDiffuse = PIO_DropDiffuse(nD);
    dropExp = 1.0 + bevel * (PIO_DROP_THIN - 1.0 + (PIO_DROP_THICK - PIO_DROP_THIN) * dome);
}

// Drop gloss: the broad soft highlight band (counted above its flat value, so a flat dome gets none) tinted by the paint,
// plus the sharp white hot spot. The caller weights it by the bevel (0 on the contour).
float3 PIO_DropGloss(float3 albedo, float3 nD)
{
    const float3 h = float3(-0.2471578, 0.3295437, 0.9112156);       // normalize(L + V), as in PIO_ShadeLiquid
    float ndh = saturate(dot(nD, h));
    float band = max(0.0, pow(max(ndh, 1e-6), PIO_DROP_BAND_POWER) - pow(0.9112156, PIO_DROP_BAND_POWER)) * PIO_DROP_BAND;
    float hot = pow(max(saturate(dot(nD, PIO_DROP_HOT_DIR)), 1e-6), PIO_DROP_HOT_POWER) * PIO_DROP_HOT;
    return band * lerp(albedo, float3(1.0, 1.0, 1.0), PIO_DROP_BAND_WHITE) + hot;
}

// Own-color fusion above 1 saturates toward 1 + PIO_MERGE_CAP (C1 at 1, identity below).
float PIO_Compress(float f)
{
    return f <= 1.0 ? f : 1.0 + PIO_MERGE_CAP * (1.0 - exp(-(f - 1.0) * (1.0 / PIO_MERGE_CAP)));
}

// Actor-path sample at one offset (bilinear only): ak = a_k, HTp = the territory relief there (faded like the center),
// HA = the actor surface height (header): lerp(rival case HT + H(C(a_k)), own case H(C(union)), own) with the union
// field max(a_k, tw) + PIO_UNION_FILLET min(a_k, tw). A plain sum a_k + tw (the coverage fusion) would lift the bevel
// to the plateau as soon as a sliver of actor field appears on it, which drew the edge of a neck's field support as a
// disc; the union rises only where the actor itself is taller than the bevel, and the min term still fills the neck
// fillet outside the contour. The own case is written as HT + extra with extra = H(C(union)) - H(tw), so it equals the
// stored relief exactly where a_k is 0. With the tiny cap, an actor on the flat of its own puddle (a pearl at home, the
// start of a neck) is flush with it, and at the junction the thread top stays level with the puddle top.
void PIO_ActorAt(float2 uvA, float2 uvT, float4 mk, float actorScale, float own, float fadeJ, float fadeK,
                 out float ak, out float HTp, out float HA)
{
    ak = dot(SAMPLE_TEXTURE2D_LOD(_PIO_ActorField, sampler_PIO_ActorField, uvA, 0), mk) / actorScale;
    float4 hs = PIO_DecodeHeight(SAMPLE_TEXTURE2D_LOD(_PIO_TerritoryHeight, sampler_PIO_TerritoryHeight, uvT, 0));
    HTp = hs.x * fadeJ;
    float tw = hs.w * fadeK;
    float rival = PIO_Height(PIO_Compress(ak));
    float mine = PIO_Height(PIO_Compress(max(ak, tw) + PIO_UNION_FILLET * min(ak, tw))) - PIO_Height(tw);
    HA = HTp + lerp(rival, mine, own);
}

void PIO_CompositeSG_float(float4 VertexColor, float2 UV1, out float3 BaseColor, out float Alpha)
{
    float2 w = UV1;
    float px = max(fwidth(w.x), 1e-5);
    float py = max(fwidth(w.y), 1e-5);
    float pix = max(px, py);
    float time = _PIO_Time.x;
    bool bicubic = _PIO_Quality.z > 0.5;
    bool shadows = _PIO_Quality.y > 0.5;
    bool central = _PIO_Quality.w > 0.5;
    float lobes = _PIO_Quality.x;
    float actorScale = max(_PIO_ActorScale, 1e-4);

    // ---- Territory layer ------------------------------------------------------------------------------------------
    float2 wt = w + PIO_Wobble(w, time);
    float2 uvT = (wt - _PIO_ArenaRect.xy) / _PIO_ArenaRect.zw;
    // Wave D-2 rim (header): a puddle that reaches the grid border ends there with a normal edge profile.
    float2 nB;
    float dB = PIO_GridBorder(wt, nB);
    float wallN = PIO_EdgeProfile(-dB / PIO_WALL_SIGMA_NARROW);
    float4 t = min(PIO_FetchTerritory(uvT, bicubic), wallN) * _PIO_PlayerFade;
    float4 ht = PIO_FetchHeight(uvT, bicubic);
    float4 dm = PIO_FetchDome(uvT, bicubic);                             // wave D: the wide dome field
    [branch] if (dB > -2.5)
    {
        ht = PIO_LiquidWallRelief(ht, dB, nB);
        dm = PIO_LiquidWallDome(dm, dB, nB, wt);
    }
    float4 mj = PIO_ArgmaxMask(t);
    float tj = dot(t, mj);
    float fadeJ = dot(_PIO_PlayerFade, mj);
    float HT = ht.x * fadeJ;
    float cT = saturate((tj - 0.5) / max(fwidth(tj), 1e-4) + 0.5);
    float4 fwT = fwidth(t);                                               // for the actor coverage (outside the branch)
    // Where two colors touch, the argmax switches: blend the two strongest channels over about one pixel so the
    // contact line (the crease) is antialiased like the edges.
    float4 others = t * (1.0 - mj);
    float4 m2 = PIO_ArgmaxMask(others);
    float gap = tj - PIO_Max4(others);                                   // continuous, also where the others are 0
    float fwGap = max(fwidth(gap), 1e-4);
    float wj = 0.5 + 0.5 * saturate(gap / fwGap);
    float3 albedoT = lerp(PIO_ChannelColor(m2), PIO_ChannelColor(mj), wj);
    // The crease (wave C): both menisci fall to H = 0 at the contact, where the sqrt height profile has an unbounded
    // slope (times PIO_RELIEF_GAIN) and the stored relief gradient flips sign; its bilinear (or B-spline) interpolation
    // crosses zero within one relief texel of the contact, so some pixels there hit the streak tilt and others the steep
    // dark side: a dotted white and dark 1 px line. Over that texel the lit surface goes flat (streak, specular and
    // Fresnel rim gone) and darkens into an antialiased groove, fading out over the next half texel (at least 2 px);
    // the shaded color is blended toward the flat groove rather than the normal tilted down, which would sweep it
    // through the streak tilt and draw a thin bright line. No slope steeper than h0 / 2 per pixel is ever lit.
    // The AA width of the crease is the sum of the two channels' own fwidths: fwidth(gap) collapses in the 2 x 2 quads
    // that straddle the contact (gap is V-shaped there), which left every other quad uncreased. Every tier, no fetch.
    float fwCrease = max(dot(fwT, saturate(mj + m2)), 1e-4);
    float creaseCore = (fwCrease / pix) * (_PIO_TerritoryTexel.x * _PIO_ArenaRect.z);   // gap across one relief texel
    float crease = 1.0 - smoothstep(creaseCore, creaseCore + max(0.5 * creaseCore, 2.0 * fwCrease), gap);
    float2 gT = ht.yz * (fadeJ * PIO_RELIEF_GAIN);
    float gLen = length(gT);
    float gMax = PIO_H0 / (2.0 * pix);
    gT *= gLen > gMax ? gMax / gLen : 1.0;

    // Drop (wave D, header): every tier, one fetch (above). Only the ground's dome shadow is needed everywhere; the depth
    // and the dome's lighting normal (PIO_DropTerms) are evaluated inside the puddle and actor branches, so the ground
    // pixels that dominate the view pay one fetch and one smoothstep.
    float dropOn = saturate(_PIO_BiomeParams.x);
    float domeShadow = (PIO_DROP_SHADOW * dropOn) * smoothstep(PIO_DROP_SHADOW_LO, PIO_DROP_SHADOW_HI, dm.w * fadeJ);

    // Fill ripple (header). It only modulates the light (a normal from screen derivatives of the bilinear reveal texture
    // showed its texels and 2 x 2 pixel quads). The crests follow the territory contour, not the reveal times: any
    // function of the reveal age traces the cell staircase where fresh liquid meets old liquid (cells never revealed hold
    // -1000, older captures their own time, and bilinear filtering cannot smooth such jumps). So the crests sit at fixed
    // depths behind the contour, read from the smooth wide relief field (tw = 0.5 on the contour), and the reveal age only
    // gates them on while the liquid there is fresh: they ride the advancing edge during the fill and fade when it stops.
    // One tap, every tier.
    // Wave D-2: the same fetch carries the scorch level in G (ScorchedEarth, header); none outside the grid.
    float2 revealRG = SAMPLE_TEXTURE2D_LOD(_PIO_RevealTime, sampler_PIO_RevealTime, uvT, 0).rg;
    float reveal = revealRG.x;
    float scorch = revealRG.y * saturate(0.5 - dB / pix);
    float age = clamp(_PIO_Now - reveal, 0.0, PIO_RIPPLE_LIFE);
    float fresh = 1.0 - smoothstep(0.06, PIO_RIPPLE_LIFE, age);
    float twj = ht.w * fadeJ;
    float c1 = (twj - PIO_RIPPLE_CREST1) * (1.0 / 0.085);
    float c2 = (twj - PIO_RIPPLE_CREST2) * (1.0 / 0.02);
    float wave = (exp(-c1 * c1) + 0.45 * exp(-c2 * c2)) * fresh;
    // Wave D-2 growth (Propagation, header): a weaker crest just behind the creeping edge, kept off the creases.
    float grow = dot(_PIO_GrowPulse, mj) * (1.0 - crease);
    float cg = (twj - PIO_GROW_CREST) * (1.0 / 0.1);
    wave += PIO_GROW_LIFT * grow * exp(-cg * cg);
    float rippleLift = 1.0 + PIO_RIPPLE_LIFT * wave;
    float rippleSheen = PIO_RIPPLE_SHEEN * wave * wave;

    float2 uvA = (w - _PIO_ActorRect.xy) / _PIO_ActorRect.zw;
    float4 a = SAMPLE_TEXTURE2D_LOD(_PIO_ActorField, sampler_PIO_ActorField, uvA, 0) / actorScale;
    float maxA = PIO_Max4(a);

    // Contact darkening (no extra fetch): the wide relief field and the actor field at the pixel itself spill a little
    // past the visible edges, so the table darkens right around the liquid on every side. Stronger on Low, where it is
    // the only shadow.
    float contact = (shadows ? PIO_CONTACT_SHADOWED : PIO_CONTACT_LOW) * smoothstep(0.04, 0.5, saturate(ht.w * fadeJ + maxA));

    // Soft drop shadows toward the lower right (the taps look toward the light). The territory source is max t_wide from
    // the relief texture (height .w), broader than the contour field, so the shadow reads as a soft drop shadow at
    // 30 px/u; own-color actors never shadow their own puddle (they merge into it). The territory tap only feeds the
    // ground shadow, so it is skipped where the puddle covers the pixel (cT = 1, wave C).
    float groundShadow = 0.0;
    float surfaceShadow = 0.0;
    [branch] if (shadows)
    {
        float2 off = _PIO_ShadowOffset.xy * PIO_SHADOW_SCALE;
        float4 aS = SAMPLE_TEXTURE2D_LOD(_PIO_ActorField, sampler_PIO_ActorField, uvA + off / _PIO_ActorRect.zw, 0) / actorScale;
        surfaceShadow = PIO_SURFACE_SHADOW * smoothstep(0.03, 0.85, PIO_Max4(aS * (1.0 - mj)));
        [branch] if (cT < 1.0)
        {
            float tw = SAMPLE_TEXTURE2D_LOD(_PIO_TerritoryHeight, sampler_PIO_TerritoryHeight, uvT + off / _PIO_ArenaRect.zw, 0).w * fadeJ;
            float2 nOff;
            float dBoff = PIO_GridBorder(wt + off, nOff);                // wave D-2 rim: no shadow smeared past it
            tw = min(tw, PIO_EdgeProfile(-dBoff / PIO_WALL_SIGMA_WIDE));
            groundShadow = PIO_GROUND_SHADOW * smoothstep(0.0, 0.72, saturate(tw + PIO_Max4(aS)));
        }
    }

    // Wave C (perf): the ground is only shaded where the puddle does not fully cover it (cT < 1) and the puddle only
    // where it shows (cT > 0); cT is exactly 0 off the territory and exactly 1 inside it, so the lerp below gives the
    // same color as shading both everywhere. No derivative inside either branch (pix and every fwidth are taken above).
    float3 ground = float3(0.0, 0.0, 0.0);
    [branch] if (cT < 1.0)
    {
        float3 table = PIO_Ground(w, pix, time);
        // Wave D-2: scorched ground is a dried paint stain (its own branch: no cost without ScorchedEarth).
        [branch] if (scorch > 0.002)
        {
            table = PIO_DriedStain(table, scorch, w, pix);
        }
        ground = table * ((1.0 - groundShadow) * (1.0 - domeShadow) * (1.0 - contact) * PIO_Vignette(w));
        // Wave D-2 growth: a faint film of the color creeping out past the edge: at the pulse's peak it hugs the edge,
        // then it slides outward (lower narrow-field values, up to about 0.2 u out) while it fades.
        float filmAt = lerp(0.14, 0.42, grow);
        float filmX = (tj - filmAt) * (1.0 / 0.13);
        ground += PIO_ChannelColor(mj) * (PIO_GROW_FILM * grow * exp(-filmX * filmX) * step(0.03, tj));
    }
    float3 puddle = float3(0.0, 0.0, 0.0);
    [branch] if (cT > 0.0)
    {
        // Wave D: the drop's albedo (depth absorption and the dome's diffuse) goes through the unchanged meniscus shading,
        // then the dome's gloss (band and hot spot) is added.
        float bevel, dropDiffuse, dropExp;
        float3 nD;
        PIO_DropTerms(dm, HT, dropOn, bevel, nD, dropDiffuse, dropExp);
        float3 albedoTD = pow(max(albedoT, 1e-4), dropExp) * dropDiffuse;
        puddle = (float3)PIO_ShadeLiquid((half3)albedoTD, float3(-gT, 1.0), HT / PIO_H0, lobes);
        puddle += PIO_InnerStreak(float3(-gT, 1.0));
        puddle += PIO_DropGloss(albedoT, nD) * bevel;
        // The crease: PIO_ShadeLiquid of a flat normal (diffuse 1, no specular, streak or rim: only the meniscus foot
        // and thin-liquid terms of the thickness remain), darkened into the groove.
        [branch] if (crease > 0.0)
        {
            float th = saturate(HT / PIO_H0);
            float3 flat = albedoTD * (lerp(0.80, 1.0, smoothstep(0.0, 0.3, th)) * (1.0 + 0.06 * (1.0 - smoothstep(0.3, 0.95, th))));
            puddle = lerp(puddle, flat * (1.0 - PIO_CREASE_DARK * crease), crease);
        }
        puddle = puddle * rippleLift + rippleSheen;
        puddle *= 1.0 - surfaceShadow;
    }
    float3 color = lerp(ground, puddle, cT);

    // Pending pockets: flat diagonal stripes on the territory layer, under the actors.
    float2 uvP = (w - _PIO_ArenaRect.xy) / _PIO_ArenaRect.zw;
    float4 pocket = PIO_FetchPocket(uvP, bicubic);
    float4 mp = PIO_ArgmaxMask(pocket);
    float pm = dot(pocket, mp);
    float pocketCover = saturate((pm - 0.5) / max(fwidth(pm), 1e-4) + 0.5);
    float d = (w.x + w.y) * (0.70710678 / PIO_STRIPE_PERIOD) - time * 0.22;
    float stripeWidth = max(fwidth(d), 1e-4);
    float stripe = saturate((0.25 - abs(frac(d) - 0.5)) / stripeWidth + 0.5);
    color = lerp(color, PIO_ChannelColor(mp), PIO_STRIPE_OPACITY * stripe * pocketCover);

    // ---- Actor layer ----------------------------------------------------------------------------------------------
    [branch] if (maxA >= PIO_ACTOR_MIN)
    {
        float4 mk = PIO_ArgmaxMask(a);
        float tk = dot(t, mk);
        float own = saturate((tk - PIO_Max4(t * (1.0 - mk))) * 5.0 + 0.5);   // 1 on its own puddle, 0 on a rival's
        float fadeK = dot(_PIO_PlayerFade, mk);
        float2 stepW = _PIO_ActorTexel.xy * _PIO_ActorRect.zw;            // world size of one actor texel
        float2 duA = float2(_PIO_ActorTexel.x, 0.0);
        float2 dvA = float2(0.0, _PIO_ActorTexel.y);
        float2 duT = float2(stepW.x / _PIO_ArenaRect.z, 0.0);
        float2 dvT = float2(0.0, stepW.y / _PIO_ArenaRect.w);

        float ak, hT0, hA0, akX, hTX, hAX, akY, hTY, hAY;
        PIO_ActorAt(uvA, uvT, mk, actorScale, own, fadeJ, fadeK, ak, hT0, hA0);
        PIO_ActorAt(uvA + duA, uvT + duT, mk, actorScale, own, fadeJ, fadeK, akX, hTX, hAX);
        PIO_ActorAt(uvA + dvA, uvT + dvT, mk, actorScale, own, fadeJ, fadeK, akY, hTY, hAY);
        float2 gradA;
        float2 gradHA;
        float2 gradHT;
        [branch] if (central)
        {
            float akXm, hTXm, hAXm, akYm, hTYm, hAYm;
            PIO_ActorAt(uvA - duA, uvT - duT, mk, actorScale, own, fadeJ, fadeK, akXm, hTXm, hAXm);
            PIO_ActorAt(uvA - dvA, uvT - dvT, mk, actorScale, own, fadeJ, fadeK, akYm, hTYm, hAYm);
            float2 inv = 1.0 / (2.0 * stepW);
            gradA = float2(akX - akXm, akY - akYm) * inv;
            gradHA = float2(hAX - hAXm, hAY - hAYm) * inv;
            gradHT = float2(hTX - hTXm, hTY - hTYm) * inv;
        }
        else
        {
            float2 inv = 1.0 / stepW;
            gradA = float2(akX - ak, akY - ak) * inv;
            gradHA = float2(hAX - hA0, hAY - hA0) * inv;
            gradHT = float2(hTX - hT0, hTY - hT0) * inv;
        }
        // Coverage: the fused field and an AA width from its gradient (fwidth of t was taken before the branch).
        float fA = ak + tk + PIO_FLARE * ak * tk;
        float fwA = (abs(gradA.x) * px + abs(gradA.y) * py) * (1.0 + PIO_FLARE * tk) + dot(fwT, mk) * (1.0 + PIO_FLARE * ak);
        float cA = saturate((fA - 0.5) / max(fwA, 1e-4) + 0.5);
        // Normal: HA = HT + extra. The relief part is the territory layer's own gradient gT (B-spline on High, with the
        // same PIO_RELIEF_GAIN), the extra part comes from finite differences (both HA and HT are differenced from the same
        // bilinear relief, so their difference is consistent). Where a_k goes to 0 the extra vanishes and the normal is
        // exactly the territory normal: the end of the actor's field support draws no seam.
        float2 gradH = gT + (gradHA - gradHT);
        float thickness = (hA0 - HT * (1.0 - own)) / PIO_H0;              // over a rival puddle: the thread's own height
        // Wave D: on its own puddle an actor takes the drop terms of the territory under it (no seam at a neck or around
        // a pearl at home); on bare ground (bevel 0) or on a rival puddle (own 0) it keeps its plain color and gloss.
        float bevel, dropDiffuse, dropExp;
        float3 nD;
        PIO_DropTerms(dm, HT, dropOn, bevel, nD, dropDiffuse, dropExp);
        float3 colK = PIO_ChannelColor(mk);
        float3 albK = pow(max(colK, 1e-4), lerp(1.0, dropExp, own)) * lerp(1.0, dropDiffuse, own);
        float3 actor = (float3)PIO_ShadeLiquid((half3)albK, float3(-gradH, 1.0), thickness, lobes);
        actor += PIO_InnerStreak(float3(-gradH, 1.0));                    // as on the territory layer: no seam between them
        actor += PIO_DropGloss(colK, nD) * (bevel * own);
        color = lerp(color, actor, cA);
    }
    BaseColor = max(color, 0.0);
    Alpha = 1.0;
}

void PIO_CompositeSG_half(half4 VertexColor, half2 UV1, out half3 BaseColor, out half Alpha)
{
    float3 baseColor;
    float alpha;
    PIO_CompositeSG_float((float4)VertexColor, (float2)UV1, baseColor, alpha);
    BaseColor = (half3)baseColor;
    Alpha = (half)alpha;
}

#endif // PIO_LIQUID_COMPOSITE_INCLUDED
