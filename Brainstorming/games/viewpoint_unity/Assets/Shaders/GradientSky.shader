// Skybox of VIEWPOINT (PRD 14.3): a four color vertical gradient, the port of
// the Godot ProceduralSkyMaterial the original used. Sky_top at the zenith
// fading to sky_horizon at the horizon; below the horizon, sky_horizon fading
// to a 15 percent darkened horizon at the nadir.
//
// The blend curves reproduce Godot's own formula so the two builds can be
// compared side by side: the mix factor is 1 - pow(1 - c, 1 / curve), where c
// runs 0 at the horizon to 1 at the pole. The defaults 0.15 and 0.02 are
// Godot's own, which is why the ground reads as a nearly flat pale band that
// only darkens close to straight down.
Shader "Viewpoint/GradientSky"
{
    Properties
    {
        // Defaults are the palette values (sky_top, sky_horizon, sky_horizon,
        // sky_horizon darkened by 15 percent) so the shader previews correctly
        // before Main assigns them from Palette.
        _SkyTop ("Sky top", Color) = (0.53, 0.72, 0.87, 1)
        _SkyHorizon ("Sky horizon", Color) = (0.87, 0.91, 0.93, 1)
        _GroundHorizon ("Ground horizon", Color) = (0.87, 0.91, 0.93, 1)
        _GroundBottom ("Ground bottom", Color) = (0.7395, 0.7735, 0.7905, 1)
        _SkyCurve ("Sky curve", Range(0.01, 1)) = 0.15
        _GroundCurve ("Ground curve", Range(0.01, 1)) = 0.02
        _Exposure ("Exposure", Range(0, 8)) = 1
    }

    SubShader
    {
        Tags
        {
            "Queue" = "Background"
            "RenderType" = "Background"
            "PreviewType" = "Skybox"
            "RenderPipeline" = "UniversalPipeline"
        }

        Cull Off
        ZWrite Off

        Pass
        {
            Name "GradientSky"

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 3.0

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _SkyTop;
                float4 _SkyHorizon;
                float4 _GroundHorizon;
                float4 _GroundBottom;
                float _SkyCurve;
                float _GroundCurve;
                float _Exposure;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 directionOS : TEXCOORD0;
            };

            Varyings vert(Attributes input)
            {
                Varyings output;
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                // Unity draws the skybox mesh centered on the camera with an
                // unrotated model matrix, so a vertex's object space position IS
                // the world view direction. The built-in skyboxes use the same
                // trick to look up their cubemap.
                output.directionOS = input.positionOS.xyz;
                return output;
            }

            // Godot's blend: c is 0 at the horizon and 1 at the pole; a small
            // curve pushes the transition hard against the horizon.
            float GradientBlend(float c, float curve)
            {
                float safeCurve = max(curve, 0.0001);
                return saturate(1.0 - pow(saturate(1.0 - saturate(c)), 1.0 / safeCurve));
            }

            half4 frag(Varyings input) : SV_Target
            {
                float3 direction = normalize(input.directionOS);
                // acos of the clamped y is the angle down from the zenith: 0 at
                // the zenith, PI/2 at the horizon, PI at the nadir.
                float verticalAngle = acos(clamp(direction.y, -1.0, 1.0));

                float skyFactor = GradientBlend(1.0 - (verticalAngle / (PI * 0.5)), _SkyCurve);
                float3 sky = lerp(_SkyHorizon.rgb, _SkyTop.rgb, skyFactor);

                float groundFactor = GradientBlend((verticalAngle - (PI * 0.5)) / (PI * 0.5), _GroundCurve);
                float3 ground = lerp(_GroundHorizon.rgb, _GroundBottom.rgb, groundFactor);

                float3 color = lerp(ground, sky, step(0.0, direction.y));
                return half4(color * _Exposure, 1.0);
            }
            ENDHLSL
        }
    }

    Fallback Off
}
