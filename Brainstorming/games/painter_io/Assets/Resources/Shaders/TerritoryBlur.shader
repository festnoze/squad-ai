// TerritoryBlur - GPU passes of the territory field (docs/CONTRACT.md 12.2 item 1), owned by B1.
// Driven by TerritoryField through a CommandBuffer (Graphics.ExecuteCommandBuffer in LateUpdate). Every pass draws a
// procedural full-screen triangle (cmd.DrawProcedural, 3 vertices, position from SV_VertexID) limited by the command
// buffer's scissor rectangle, and reads its input through the explicit globals _PIO_BlurSource and _PIO_BlurTexel.
// The Core RP full-screen triangle helpers keep every pass memory-consistent on every graphics API (a destination
// texel reads the source at the same uv), so all territory textures share the Texture2D convention: v = 0 is grid row 0.
//   Pass 0 BlurH:    separable Gaussian, sigma 1.28 texels, 5 linearly interpolated taps along x (mask -> ping A).
//   Pass 1 BlurV:    the same along y (ping A -> ping B).
//   Pass 2 Upsample: bicubic B-spline (4 bilinear taps) of ping B into the 1024^2 _PIO_TerritoryField.
//   Pass 3 Height:   reads the WIDE field (ping C, below) through B-spline taps: H_T = PIO_Height(max t_wide), its
//                    world-space gradient by central differences of H at one field texel, and max t_wide, into the
//                    1024^2 _PIO_TerritoryHeight (8-bit encoding when _PIO_TerritoryUnorm = 1).
//   Pass 4 WideH / Pass 5 WideV: a second Gaussian (sigma 1.6 texels, 7 taps) applied to ping B, so t_wide has a total
//                    sigma of 2.05 cells (0.26 u). The contour stays the narrow field's 0.5 iso (same place on straight
//                    edges); only the relief uses t_wide, which gives the puddles a broader rounded edge (thick liquid,
//                    docs/reference_gouttes.png) and a broader soft shadow source (height .w).
// Wave D (liq-drop, contract 28 F2): the dome field, a much wider Gaussian (sigma 0.8 u) that keeps rising over 1.5 - 2 u
// inside a puddle, so the liquid composite can shade every puddle as one domed drop. Passes 0 - 5 are unchanged (the fire
// and electric composites read their outputs); the dome passes have their own render textures:
//   Pass 6 DomeH:     visual mask (512) -> 256 x 256 dome grid. Every tap is one bilinear fetch at a corner shared by
//                    four mask texels (their exact 2 x 2 average, the downsample), 21 taps of a Gaussian of sigma
//                    3.2 dome texels (0.8 u) along x.
//   Pass 7 DomeV:     the same Gaussian along y on the dome grid (center plus five linearly interpolated taps per side).
//   Pass 8 DomeField: B-spline reconstruction of the dome grid into the mask-sized _PIO_TerritoryDome: (t_dome = max over
//                    the channels, its world gradient by central differences at one output texel, t_dome at
//                    PIO_DOME_SHADOW_REACH toward the key light), 8-bit encoding when _PIO_TerritoryUnorm = 1.
Shader "PainterIO/TerritoryBlur"
{
    Properties
    {
        [HideInInspector] _PIO_ShaderId ("id", Float) = 1
    }

    SubShader
    {
        Tags { "RenderPipeline"="UniversalPipeline" "RenderType"="Opaque" "Queue"="Geometry" }

        ZWrite Off
        ZTest Always
        Cull Off
        Blend Off

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
        #include "Assets/Resources/Shaders/LiquidCommon.hlsl"

        CBUFFER_START(UnityPerMaterial)
            float _PIO_ShaderId;
        CBUFFER_END

        // Normalized Gaussian of sigma 1.28 texels over 9 texels, folded into a center tap and two linear taps per side.
        #define PIO_BLUR_W0 0.3117715
        #define PIO_BLUR_W1 0.3217533
        #define PIO_BLUR_O1 1.2858701
        #define PIO_BLUR_W2 0.0223610
        #define PIO_BLUR_O2 3.1056250
        // Normalized Gaussian of sigma 1.6 texels over 13 texels: a center tap and three linear taps per side.
        #define PIO_WIDE_W0 0.2493481
        #define PIO_WIDE_W1 0.3192680
        #define PIO_WIDE_O1 1.3575675
        #define PIO_WIDE_W2 0.0539486
        #define PIO_WIDE_O2 3.2030746
        #define PIO_WIDE_W3 0.0021094
        #define PIO_WIDE_O3 5.1044773

        struct PIO_BlurVaryings
        {
            float4 positionCS : SV_POSITION;
            float2 uv : TEXCOORD0;
        };

        PIO_BlurVaryings PIO_BlurVert(uint vertexID : SV_VertexID)
        {
            PIO_BlurVaryings output;
            output.positionCS = GetFullScreenTriangleVertexPosition(vertexID);
            output.uv = GetFullScreenTriangleTexCoord(vertexID);
            return output;
        }

        float4 PIO_BlurTap(float2 uv)
        {
            return SAMPLE_TEXTURE2D_LOD(_PIO_BlurSource, sampler_PIO_BlurSource, uv, 0);
        }

        float4 PIO_Blur1D(float2 uv, float2 axis)
        {
            float2 d1 = axis * (PIO_BLUR_O1 * _PIO_BlurTexel.xy);
            float2 d2 = axis * (PIO_BLUR_O2 * _PIO_BlurTexel.xy);
            float4 sum = PIO_BlurTap(uv) * PIO_BLUR_W0;
            sum += (PIO_BlurTap(uv + d1) + PIO_BlurTap(uv - d1)) * PIO_BLUR_W1;
            sum += (PIO_BlurTap(uv + d2) + PIO_BlurTap(uv - d2)) * PIO_BLUR_W2;
            return sum;
        }

        float4 PIO_Wide1D(float2 uv, float2 axis)
        {
            float2 d1 = axis * (PIO_WIDE_O1 * _PIO_BlurTexel.xy);
            float2 d2 = axis * (PIO_WIDE_O2 * _PIO_BlurTexel.xy);
            float2 d3 = axis * (PIO_WIDE_O3 * _PIO_BlurTexel.xy);
            float4 sum = PIO_BlurTap(uv) * PIO_WIDE_W0;
            sum += (PIO_BlurTap(uv + d1) + PIO_BlurTap(uv - d1)) * PIO_WIDE_W1;
            sum += (PIO_BlurTap(uv + d2) + PIO_BlurTap(uv - d2)) * PIO_WIDE_W2;
            sum += (PIO_BlurTap(uv + d3) + PIO_BlurTap(uv - d3)) * PIO_WIDE_W3;
            return sum;
        }

        // Cubic B-spline reconstruction from 4 bilinear taps (Sigg and Hadwiger).
        float4 PIO_BSpline(float2 uv)
        {
            float2 st = uv * _PIO_BlurTexel.zw - 0.5;
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
            float2 p0 = (i + 0.5 - 1.0 + w1 / g0) * _PIO_BlurTexel.xy;
            float2 p1 = (i + 0.5 + 1.0 + w3 / g1) * _PIO_BlurTexel.xy;
            float4 s00 = PIO_BlurTap(float2(p0.x, p0.y));
            float4 s10 = PIO_BlurTap(float2(p1.x, p0.y));
            float4 s01 = PIO_BlurTap(float2(p0.x, p1.y));
            float4 s11 = PIO_BlurTap(float2(p1.x, p1.y));
            return g0.y * (g0.x * s00 + g1.x * s10) + g1.y * (g0.x * s01 + g1.x * s11);
        }

        float PIO_MaxT(float2 uv)
        {
            float4 t = saturate(PIO_BSpline(uv));
            return max(max(t.x, t.y), max(t.z, t.w));
        }

        // Dome Gaussian (wave D): sigma 3.2 dome texels (0.8 u at 0.25 u per texel), normalized over 21 texels. Unfolded
        // weights for DomeH (each of its taps is already a 2 x 2 box of the mask, so pairs cannot be merged) and the
        // center plus five linear pairs for DomeV.
        #define PIO_DOME_W0 0.1247925
        #define PIO_DOME_W1 0.1188455
        #define PIO_DOME_W2 0.1026515
        #define PIO_DOME_W3 0.0804149
        #define PIO_DOME_W4 0.0571342
        #define PIO_DOME_W5 0.0368166
        #define PIO_DOME_W6 0.0215169
        #define PIO_DOME_W7 0.0114053
        #define PIO_DOME_W8 0.0054830
        #define PIO_DOME_W9 0.0023907
        #define PIO_DOME_W10 0.0009454
        #define PIO_DOME_PW1 0.2214969
        #define PIO_DOME_PO1 1.4634442
        #define PIO_DOME_PW2 0.1375490
        #define PIO_DOME_PO2 3.4153731
        #define PIO_DOME_PW3 0.0583335
        #define PIO_DOME_PO3 5.3688603
        #define PIO_DOME_PW4 0.0168882
        #define PIO_DOME_PO4 7.3246635
        #define PIO_DOME_PW5 0.0033361
        #define PIO_DOME_PO5 9.2833846

        // A symmetric pair of taps at +/- d.
        float4 PIO_BlurPair(float2 uv, float2 d)
        {
            return PIO_BlurTap(uv + d) + PIO_BlurTap(uv - d);
        }
        ENDHLSL

        Pass
        {
            Name "BlurH"
            Tags { "LightMode"="SRPDefaultUnlit" }
            HLSLPROGRAM
            #pragma vertex PIO_BlurVert
            #pragma fragment PIO_BlurHFrag
            float4 PIO_BlurHFrag(PIO_BlurVaryings input) : SV_Target
            {
                return PIO_Blur1D(input.uv, float2(1.0, 0.0));
            }
            ENDHLSL
        }

        Pass
        {
            Name "BlurV"
            Tags { "LightMode"="SRPDefaultUnlit" }
            HLSLPROGRAM
            #pragma vertex PIO_BlurVert
            #pragma fragment PIO_BlurVFrag
            float4 PIO_BlurVFrag(PIO_BlurVaryings input) : SV_Target
            {
                return PIO_Blur1D(input.uv, float2(0.0, 1.0));
            }
            ENDHLSL
        }

        Pass
        {
            Name "Upsample"
            Tags { "LightMode"="SRPDefaultUnlit" }
            HLSLPROGRAM
            #pragma vertex PIO_BlurVert
            #pragma fragment PIO_UpsampleFrag
            float4 PIO_UpsampleFrag(PIO_BlurVaryings input) : SV_Target
            {
                return saturate(PIO_BSpline(input.uv));
            }
            ENDHLSL
        }

        Pass
        {
            Name "Height"
            Tags { "LightMode"="SRPDefaultUnlit" }
            HLSLPROGRAM
            #pragma vertex PIO_BlurVert
            #pragma fragment PIO_HeightFrag
            float4 PIO_HeightFrag(PIO_BlurVaryings input) : SV_Target
            {
                // _PIO_BlurTexel describes the 512 wide source; the output is the 1024 height texture, whose texel is
                // half a source texel: the differences are taken at one output texel.
                float2 dx = float2(0.5 * _PIO_BlurTexel.x, 0.0);
                float2 dy = float2(0.0, 0.5 * _PIO_BlurTexel.y);
                float tC = PIO_MaxT(input.uv);
                float h = PIO_Height(tC);
                float hxp = PIO_Height(PIO_MaxT(input.uv + dx));
                float hxm = PIO_Height(PIO_MaxT(input.uv - dx));
                float hyp = PIO_Height(PIO_MaxT(input.uv + dy));
                float hym = PIO_Height(PIO_MaxT(input.uv - dy));
                // World size of one field texel along each axis.
                float2 texelWorld = _PIO_ArenaRect.zw * float2(dx.x, dy.y);
                float2 grad = float2(hxp - hxm, hyp - hym) / (2.0 * texelWorld);
                if (_PIO_TerritoryUnorm > 0.5)
                {
                    return saturate(float4(h / PIO_H0, grad / (2.0 * PIO_GRAD_RANGE) + 0.5, tC));
                }
                return float4(h, grad, tC);
            }
            ENDHLSL
        }

        Pass
        {
            Name "WideH"
            Tags { "LightMode"="SRPDefaultUnlit" }
            HLSLPROGRAM
            #pragma vertex PIO_BlurVert
            #pragma fragment PIO_WideHFrag
            float4 PIO_WideHFrag(PIO_BlurVaryings input) : SV_Target
            {
                return PIO_Wide1D(input.uv, float2(1.0, 0.0));
            }
            ENDHLSL
        }

        Pass
        {
            Name "WideV"
            Tags { "LightMode"="SRPDefaultUnlit" }
            HLSLPROGRAM
            #pragma vertex PIO_BlurVert
            #pragma fragment PIO_WideVFrag
            float4 PIO_WideVFrag(PIO_BlurVaryings input) : SV_Target
            {
                return PIO_Wide1D(input.uv, float2(0.0, 1.0));
            }
            ENDHLSL
        }

        Pass
        {
            Name "DomeH"
            Tags { "LightMode"="SRPDefaultUnlit" }
            HLSLPROGRAM
            #pragma vertex PIO_BlurVert
            #pragma fragment PIO_DomeHFrag
            float4 PIO_DomeHFrag(PIO_BlurVaryings input) : SV_Target
            {
                // _PIO_BlurTexel describes the visual mask; the target is the half-size dome grid, so the center of a
                // dome texel is a corner shared by four mask texels and one dome texel spans two mask texels.
                float2 d = float2(2.0 * _PIO_BlurTexel.x, 0.0);
                float2 uv = input.uv;
                float4 sum = PIO_BlurTap(uv) * PIO_DOME_W0;
                sum += PIO_BlurPair(uv, d) * PIO_DOME_W1;
                sum += PIO_BlurPair(uv, 2.0 * d) * PIO_DOME_W2;
                sum += PIO_BlurPair(uv, 3.0 * d) * PIO_DOME_W3;
                sum += PIO_BlurPair(uv, 4.0 * d) * PIO_DOME_W4;
                sum += PIO_BlurPair(uv, 5.0 * d) * PIO_DOME_W5;
                sum += PIO_BlurPair(uv, 6.0 * d) * PIO_DOME_W6;
                sum += PIO_BlurPair(uv, 7.0 * d) * PIO_DOME_W7;
                sum += PIO_BlurPair(uv, 8.0 * d) * PIO_DOME_W8;
                sum += PIO_BlurPair(uv, 9.0 * d) * PIO_DOME_W9;
                sum += PIO_BlurPair(uv, 10.0 * d) * PIO_DOME_W10;
                return sum;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DomeV"
            Tags { "LightMode"="SRPDefaultUnlit" }
            HLSLPROGRAM
            #pragma vertex PIO_BlurVert
            #pragma fragment PIO_DomeVFrag
            float4 PIO_DomeVFrag(PIO_BlurVaryings input) : SV_Target
            {
                float2 t = float2(0.0, _PIO_BlurTexel.y);
                float2 uv = input.uv;
                float4 sum = PIO_BlurTap(uv) * PIO_DOME_W0;
                sum += PIO_BlurPair(uv, PIO_DOME_PO1 * t) * PIO_DOME_PW1;
                sum += PIO_BlurPair(uv, PIO_DOME_PO2 * t) * PIO_DOME_PW2;
                sum += PIO_BlurPair(uv, PIO_DOME_PO3 * t) * PIO_DOME_PW3;
                sum += PIO_BlurPair(uv, PIO_DOME_PO4 * t) * PIO_DOME_PW4;
                sum += PIO_BlurPair(uv, PIO_DOME_PO5 * t) * PIO_DOME_PW5;
                return sum;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DomeField"
            Tags { "LightMode"="SRPDefaultUnlit" }
            HLSLPROGRAM
            #pragma vertex PIO_BlurVert
            #pragma fragment PIO_DomeFieldFrag
            float4 PIO_DomeFieldFrag(PIO_BlurVaryings input) : SV_Target
            {
                // _PIO_BlurTexel describes the dome grid; the output has twice its resolution: the differences are taken
                // at one output texel, half a grid texel.
                float2 dx = float2(0.5 * _PIO_BlurTexel.x, 0.0);
                float2 dy = float2(0.0, 0.5 * _PIO_BlurTexel.y);
                float tC = PIO_MaxT(input.uv);
                float txp = PIO_MaxT(input.uv + dx);
                float txm = PIO_MaxT(input.uv - dx);
                float typ = PIO_MaxT(input.uv + dy);
                float tym = PIO_MaxT(input.uv - dy);
                float2 texelWorld = _PIO_ArenaRect.zw * float2(dx.x, dy.y);
                float2 grad = float2(txp - txm, typ - tym) / (2.0 * texelWorld);
                // The shadow source: t_dome toward the key light (normalize(L.xy) = (-0.6, 0.8)), so ground to the lower
                // right of a puddle reads a high value.
                float2 toLight = float2(-0.6, 0.8) * PIO_DOME_SHADOW_REACH / _PIO_ArenaRect.zw;
                float tS = PIO_MaxT(input.uv + toLight);
                if (_PIO_TerritoryUnorm > 0.5)
                {
                    return saturate(float4(tC, grad / (2.0 * PIO_DOME_GRAD_RANGE) + 0.5, tS));
                }
                return float4(tC, grad, tS);
            }
            ENDHLSL
        }
    }
}