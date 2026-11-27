// LiquidCommon.hlsl - shared declarations of the Painter IO liquid look (docs/CONTRACT.md 12.1 and 12.2).
// First version by B0b (editor and shader tooling); owned by B1 (liquid render) since wave B. BI (wave B-2) added the
// biome globals (_PIO_RevealTime, _PIO_RevealTexel, _PIO_Now, _PIO_SecondaryColors, _PIO_BiomeParams). LIQ (wave B-2)
// owns it now and retuned PIO_ShadeLiquid; the fire and electric graphs include this file, so every global and both
// function signatures stay as they are (additions only). Wave D liq-drop added the dome field (_PIO_TerritoryDome,
// _PIO_TerritoryDomeTexel, PIO_DOME_*), read only by TerritoryBlur and LiquidComposite.
//
// Rules:
// - This file is the ONLY place that declares the _PIO_* globals. A _PIO_* global is never a Shader Graph property and
//   never lives in UnityPerMaterial: Shader.SetGlobal* would then be silently ignored.
// - _PIO_ShaderId is the one exception: it is a per-shader marker property declared by each shader itself (graph
//   property or Properties block), so it is NOT declared here.
// - Exposes exactly two functions: PIO_Height and PIO_ShadeLiquid. Helpers of one shader live in that shader's file.
// - Table space: x and y are Unity world x and y, z points out of the table toward the viewer (Unity -Z).
// - Its .meta carries the fixed GUID d210809a08e442a9a9875e8fb65efb22 (never let Unity regenerate it).
#ifndef PIO_LIQUID_COMMON_INCLUDED
#define PIO_LIQUID_COMMON_INCLUDED

// TEXTURE2D, SAMPLER and the real/half types come from the URP core library. Core.hlsl has its own include guard, so
// this include is free in a hand-written .shader that already included it and in a Shader Graph pass (pregraph).
#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

// ---------------------------------------------------------------------------------------------------------------------
// Globals (set from C# with Shader.SetGlobal* or CommandBuffer.SetGlobal*; an unset global reads as 0).
// ---------------------------------------------------------------------------------------------------------------------

// Territory field, world space over _PIO_ArenaRect (TerritoryField, B1).
TEXTURE2D(_PIO_TerritoryField);    SAMPLER(sampler_PIO_TerritoryField);    // RGBA: t_i per player channel
TEXTURE2D(_PIO_TerritoryHeight);   SAMPLER(sampler_PIO_TerritoryHeight);   // (H_T, dH_T/dx, dH_T/dy, max t), world units
float4 _PIO_TerritoryTexel;        // (1/w, 1/h, w, h) of the territory field and height textures
float4 _PIO_ArenaRect;             // (minX, minY, sizeX, sizeY) = (-32, -32, 64, 64)
float _PIO_TerritoryUnorm;         // B1: 1 when the field and height RTs fell back to R8G8B8A8_UNorm (contract 19):
                                   // the height texture then stores (H / h0, dH/dx and dH/dy remapped by
                                   // PIO_GRAD_RANGE, max t); 0 with half-float RTs (raw world units)

// Territory blur passes (TerritoryBlur.shader, procedural full-screen triangle).
TEXTURE2D(_PIO_BlurSource);        SAMPLER(sampler_PIO_BlurSource);
float4 _PIO_BlurTexel;             // (1/w, 1/h, w, h) of _PIO_BlurSource

// Actor field, world-rectangle space (ActorFieldCamera, B1). Sample at uv = (worldXY - _PIO_ActorRect.xy) / _PIO_ActorRect.zw.
TEXTURE2D(_PIO_ActorField);        SAMPLER(sampler_PIO_ActorField);
float4 _PIO_ActorRect;             // (xMin, yMin, width, height) in world units
float4 _PIO_ActorTexel;            // (1/w, 1/h, w, h) of _PIO_ActorField
float _PIO_ActorScale;             // 1 with a half-float actor RT, 0.25 with an 8-bit RT: contributors multiply, the composite divides

// Pending pockets (512 x 512 RGBA32 linear, channel per player, over _PIO_ArenaRect).
TEXTURE2D(_PIO_PocketMask);        SAMPLER(sampler_PIO_PocketMask);
float4 _PIO_PocketTexel;           // B1: (1/w, 1/h, w, h) of _PIO_PocketMask

// Palette, per-player fade, shadows, quality.
float4 _PIO_Colors[4];             // linear RGB of each sim player's displayed color (a unused)
float4 _PIO_PlayerFade;            // per player channel: 1 visible, fades to 0 on evaporation
float4 _PIO_ShadowOffset;          // xy = 0.12 * normalize(L.xy) = (-0.072, 0.096) u (toward the light); zw unused
float4 _PIO_Quality;               // x = specular lobes (1 or 2), y = shadow taps on (0 or 1),
                                   // z = bicubic territory (0 or 1), w = central differences (0 or 1)

// Table (B1 additions).
float4 _PIO_GroundColor;           // linear RGB of the arena ground (Palette.Background)
float4 _PIO_OutsideColor;          // linear RGB outside the arena (Palette.OutsideArena)
float4 _PIO_ArenaShape;            // (half size, corner radius, country mask enabled, 0)
float4 _PIO_Time;                  // x = seconds since the current session started (unscaled), wraps at 4096 s; yzw unused

// Biomes (contract 25.2; set by BI's TerritoryField and LiquidRenderer, shared by every biome's composite).
TEXTURE2D(_PIO_RevealTime);        SAMPLER(sampler_PIO_RevealTime);        // R: visual clock time each cell was last revealed
                                   // or changed owner (512 x 512 RHalf over _PIO_ArenaRect, bilinear); -1000 for cells
                                   // present at session start. Front age = _PIO_Now - reveal (rolling epoch: only the
                                   // difference is meaningful; the clock is the sim render clock of the fill waves)
float4 _PIO_RevealTexel;           // (1/w, 1/h, w, h) of _PIO_RevealTime
float _PIO_Now;                    // the same clock now (stops in pause, slows in slow motion, like the fill waves)
float4 _PIO_SecondaryColors[4];    // linear RGB per sim player: the biome's secondary color (fire hot core, neon core, liquid tint)
float4 _PIO_BiomeParams;           // free per-biome parameters (BiomeTheme.ShaderParams)

// Dome field (wave D liq-drop, contract 28 F2; built by TerritoryField in the same scissored command buffer as the
// territory blur). A much wider Gaussian of the visual mask (sigma 0.8 u, blurred on a 256 x 256 grid, published at the
// mask size over _PIO_ArenaRect, bilinear): it keeps rising over 1.5 - 2 u inside a large puddle, so LiquidComposite
// shades each puddle as one domed drop while the narrow fields keep its edge sharp.
TEXTURE2D(_PIO_TerritoryDome);     SAMPLER(sampler_PIO_TerritoryDome);     // x = t_dome (max over the channels),
                                   // yz = dt_dome/dx, dt_dome/dy per world unit, w = t_dome sampled
                                   // PIO_DOME_SHADOW_REACH toward the key light (the soft contact shadow source)
float4 _PIO_TerritoryDomeTexel;    // (1/w, 1/h, w, h) of _PIO_TerritoryDome

// Biome traits (wave D-2 traits-fx, docs/BIOME_TRAITS.md sections 5 and 7; set by TerritoryField, read by the three
// composites). An unset global reads as 0, which turns every trait effect off.
// - Scorched ground (ScorchedEarth): the scorch level of each cell (1 = scorched, fading to 0 over the last
//   PIO_SCORCH_FADE seconds) is the G channel of _PIO_RevealTime (an RG texture since wave D-2), so LiquidComposite and
//   ElectricComposite read it from the reveal fetch they already make and the 12.2 item 4 fetch budgets are unchanged.
//   This stands for the "_PIO_ScorchMask" of BIOME_TRAITS 5 (same grid, same meaning, same fade).
float _PIO_ScorchOn;               // 1 while at least one cell is scorched (gates FireComposite's scorch fetch), else 0
// - Propagation (TerritoryGrew): a slow, subtle edge front. Per sim player channel, an envelope in [0, 1] that rises in
//   about 0.15 s when that player's territory grows and decays over about 1.2 s; each composite draws its own soft edge
//   accent with it (liquid creep, flames licking a little higher, rim crackle). Never as bright as a capture front.
float4 _PIO_GrowPulse;

// ---------------------------------------------------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------------------------------------------------

#define PIO_H0 0.17                // liquid height of a flat puddle interior, world units
// Key light from the upper left, normalize(-0.45, 0.6, 0.66), and the view direction, in table space.
#define PIO_LIGHT_DIR float3(-0.4504282, 0.6005710, 0.6606281)
#define PIO_VIEW_DIR float3(0.0, 0.0, 1.0)
// Gradient range of the 8-bit height fallback: stored = dH / (2 * PIO_GRAD_RANGE) + 0.5.
#define PIO_GRAD_RANGE 6.0
// Dome field (wave D): gradient range of its 8-bit fallback (stored = dt / (2 * PIO_DOME_GRAD_RANGE) + 0.5; |dt/dx| of a
// Gaussian edge of sigma 0.8 u peaks at 0.5 per u) and the distance toward the light (-0.6, 0.8) of its shadow sample.
#define PIO_DOME_GRAD_RANGE 1.0
#define PIO_DOME_SHADOW_REACH 0.32
// Biome traits (wave D-2): seconds over which a scorched cell fades out before its scorch ends (TerritoryField writes
// the faded level, this is for reference), and the Gaussian sigmas, in world units, of the edge profiles the composites
// rebuild where a territory reaches the border of the grid (_PIO_ArenaRect): with Propagation a puddle may reach the
// arena rim, and the clamped fields would otherwise smear it past the rim. Narrow field, relief field, dome field.
#define PIO_SCORCH_FADE 2.0
#define PIO_WALL_SIGMA_NARROW 0.16
#define PIO_WALL_SIGMA_WIDE 0.26
#define PIO_WALL_SIGMA_DOME 0.8

// ---------------------------------------------------------------------------------------------------------------------
// Functions
// ---------------------------------------------------------------------------------------------------------------------

// Height of the liquid for a field value f (contract 12.2): h0 * sqrt(max(0, (sqrt(f) - 0.70711) / 0.29289)).
// H(0.5) = 0, so the iso contour is the visible edge; for f = A (1 - r^2)^2 with A = 1 it is a half-ellipsoid whose
// radius is the visible radius. No clamp at f = 1: overlaps keep rising smoothly.
float PIO_Height(float f)
{
    return PIO_H0 * sqrt(max(0.0, (sqrt(max(f, 0.0)) - 0.70711) / 0.29289));
}

// Glossy paint shading. albedoLinear: linear RGB; nTable: normal in table space (need not be normalized);
// thickness01 = H / h0; lobes: 1 or 2 (QualityTier). Returns linear RGB.
// Model (B1, retuned by LIQ in wave B-2 against docs/reference_gouttes.png):
// - wrapped Lambert normalized so a flat surface returns its albedo exactly (saturated paint, V5);
// - a tight Blinn-Phong highlight (gloss 130) where the surface faces the key light;
// - an area-light streak: the reference is lit by a broad softbox, so its highlights are long thin white lines that
//   run along every edge whose slope faces the upper left, not a single spot. It comes from a window on the tilt of the
//   normal (asin |n.xy|, a line at 19 degrees) times a window on its azimuth around the light's (full within about 30
//   degrees, gone past about 70). On a puddle bevel it draws the crisp streak (LiquidComposite adds the faint inner
//   second line of the puddles itself), on a thread the tube highlight, on a bead a curved window reflection. Flat
//   interiors (tilt 0) get nothing;
// - a broad soft lobe on High only (counted above its flat value, so flat interiors stay untouched);
// - a Fresnel rim on steep sides, a slight darkening at the meniscus foot, a slight brightening where the liquid is thin.
half3 PIO_ShadeLiquid(half3 albedoLinear, float3 nTable, float thickness01, float lobes)
{
    float3 n = normalize(nTable);
    const float3 l = PIO_LIGHT_DIR;
    const float3 h = float3(-0.2471578, 0.3295437, 0.9112156);   // normalize(l + v), v = (0, 0, 1)

    // Wrapped Lambert with ambient, divided by its value for the flat normal (0, 0, 1).
    const float wrap = 0.25;
    const float ambient = 0.32;
    float lambert = saturate((dot(n, l) + wrap) / (1.0 + wrap));
    const float lambertFlat = (0.6606281 + wrap) / (1.0 + wrap);
    float diffuse = (ambient + (1.0 - ambient) * lambert) / (ambient + (1.0 - ambient) * lambertFlat);

    float t = saturate(thickness01);
    float foot = lerp(0.80, 1.0, smoothstep(0.0, 0.3, t));             // meniscus foot slightly darker
    float thin = 1.0 + 0.06 * (1.0 - smoothstep(0.3, 0.95, t));        // thin liquid slightly brighter

    float ndh = saturate(dot(n, h));
    float spec = pow(ndh, 130.0) * 1.2;                                 // tight highlight

    // Area-light streaks (see above). The light's azimuth is normalize(L.xy) = (-0.6, 0.8).
    float tilt = saturate(length(n.xy));
    float tiltDeg = asin(tilt) * 57.2957795;
    float azimuth = dot(n.xy, float2(-0.6, 0.8)) / max(tilt, 1e-4);
    float window = smoothstep(0.35, 0.88, azimuth);
    float s1 = (tiltDeg - 19.0) * (1.0 / 5.0);
    spec += window * 0.85 * exp(-s1 * s1);

    const float broadFlat = 0.32768;                                    // pow(h.z, 12)
    float broad = (lobes > 1.5) ? max(0.0, pow(ndh, 12.0) - broadFlat) * 0.25 : 0.0;
    float rim = pow(1.0 - saturate(n.z), 3.0) * 0.10;                   // Fresnel rim on steep sides

    float3 albedo = (float3)albedoLinear;
    float3 color = albedo * diffuse * foot * thin;
    color += (spec + broad).xxx;
    color += rim * lerp(albedo, float3(1.0, 1.0, 1.0), 0.35);
    return (half3)color;
}

#endif // PIO_LIQUID_COMMON_INCLUDED
