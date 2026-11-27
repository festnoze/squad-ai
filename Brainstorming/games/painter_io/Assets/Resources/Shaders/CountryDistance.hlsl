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

#endif
