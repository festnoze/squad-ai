#ifndef PIO_COUNTRY_DISTANCE_INCLUDED
#define PIO_COUNTRY_DISTANCE_INCLUDED

TEXTURE2D(_PIO_CountryDistance);
SAMPLER(sampler_PIO_CountryDistance);

float PIO_OptionalCountryDistance(float2 world, float classicDistance)
{
    UNITY_BRANCH
    if (_PIO_ArenaShape.z < 0.5) return classicDistance;
    float2 uv = world / (2.0 * _PIO_ArenaShape.x) + 0.5;
    float sd = SAMPLE_TEXTURE2D_LOD(_PIO_CountryDistance, sampler_PIO_CountryDistance, saturate(uv), 0).r * 4.0 - 2.0;
    return sd + length(abs(world) - min(abs(world), _PIO_ArenaShape.xx));
}

// The arena frame, shared by the three biome composites (docs/border_neon.json): a flat light grey outside the arena
// (_PIO_OutsideColor = Palette.OutsideArena, the same in every biome) and a thin yellow neon line on the edge with a soft
// glow on both sides. sd = arena signed distance in world units (> 0 outside, square or country polygon alike), pix =
// world units per pixel (taken by the caller outside any dynamic branch), inside = the biome ground already shaded.
// Pure arithmetic: no fetch, no derivative (usable in a dynamic branch).
#define PIO_NEON_CORE float3(1.0, 0.94, 0.50)   // linear: pale yellow-white core
#define PIO_NEON_GLOW float3(1.0, 0.80, 0.03)   // linear: saturated neon yellow of the halo
#define PIO_NEON_OFFSET 0.04                    // u: the line sits just outside the edge, so a territory that hugs the rim
                                                // never covers its core
#define PIO_NEON_HALF 0.045                     // u: half width of the core (at least 0.75 px)
#define PIO_NEON_NEAR 0.09                      // u: falloff of the strong inner halo
#define PIO_NEON_FAR 0.30                       // u: falloff of the soft wide halo
#define PIO_NEON_PULSE 0.07                     // relative amplitude of the slow pulse of the halo (period about 4.5 s)

float3 PIO_ArenaFrame(float3 inside, float sd, float pix, float time)
{
    float inArena = saturate(0.5 - sd / pix);
    float3 g = lerp(_PIO_OutsideColor.rgb, inside, inArena);
    float x = abs(sd - PIO_NEON_OFFSET);
    float pulse = 1.0 + PIO_NEON_PULSE * sin(time * 1.4);
    float glow = saturate((0.60 * exp(-x / PIO_NEON_NEAR) + 0.32 * exp(-x / PIO_NEON_FAR)) * pulse);
    g = lerp(g, PIO_NEON_GLOW, glow);
    float hw = max(PIO_NEON_HALF, 0.75 * pix);
    float core = saturate((hw - x) / pix + 0.5);
    return lerp(g, PIO_NEON_CORE, core);
}

#endif
