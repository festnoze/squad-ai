// LEVELNUM: draws the level number's glyph quads into CardNumber's mask texture (a command buffer, outside any camera).
// The positions go to clip space through _NumberToClip (set by CardNumber: the zoom's scale over the canvas size), not
// through the camera matrices. Rendering into a texture on a platform whose texture rows start at the top (D3D, Metal,
// Vulkan through Unity's conversion) flips y, as Unity's own projection does, so the mask is sampled upright with
// ordinary UVs. No keyword; created from code only, so ProjectSetup lists it in Always Included Shaders.
// LEVELNUM2: _MainTex is a signed distance field atlas (LevelDigitFont: 0.5 on the outline, rising inward). The distance
// to the outline in mask pixels is (field - 0.5) * _DistanceToPixels (exact, computed by CardNumber from the zoom's
// scale, so no screen derivatives and no dependency on the filtering precision). Output, kept at the maximum where
// glyph quads overlap:
//   r (and a): coverage, a one-pixel anti-aliased edge at any zoom;
//   g: a hairline band from the outline to _EdgeWidth pixels inside;
//   b: an inner shade, 1 at the outline fading to 0 at _ShadeWidth pixels inside (squared, so it is soft).
Shader "OutOfSight/UI Number Mask"
{
    Properties
    {
        _MainTex ("Digit distance field", 2D) = "black" {}
        _DistanceToPixels ("Field to mask pixels", Float) = 100
        _EdgeWidth ("Hairline width (mask pixels)", Float) = 1.5
        _ShadeWidth ("Inner shade width (mask pixels)", Float) = 24
    }
    SubShader
    {
        Tags { "Queue" = "Transparent" "IgnoreProjector" = "True" "RenderType" = "Transparent" }
        Cull Off
        Lighting Off
        ZWrite Off
        ZTest Always
        BlendOp Max
        Blend One One

        Pass
        {
            Name "NumberMask"
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 2.0
            #include "UnityCG.cginc"

            struct appdata
            {
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct v2f
            {
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
            };

            sampler2D _MainTex;
            float4x4 _NumberToClip;
            float _DistanceToPixels;
            float _EdgeWidth;
            float _ShadeWidth;

            v2f vert(appdata v)
            {
                v2f o;
                float4 p = mul(_NumberToClip, float4(v.vertex.xy, 0, 1));
                #if UNITY_UV_STARTS_AT_TOP
                p.y = -p.y;
                #endif
                o.pos = float4(p.xy, 0.5, 1);
                o.uv = v.uv;
                return o;
            }

            float4 frag(v2f i) : SV_Target
            {
                float field = tex2D(_MainTex, i.uv).r;
                // Signed distance to the outline in mask pixels, positive inside.
                float d = (field - 0.5) * _DistanceToPixels;
                float coverage = saturate(d + 0.5);
                float hairline = coverage * saturate(_EdgeWidth - d + 0.5);
                float fall = saturate(1.0 - d / max(_ShadeWidth, 1e-3));
                float shade = coverage * fall * fall;
                return float4(coverage, hairline, shade, coverage);
            }
            ENDCG
        }
    }
}
