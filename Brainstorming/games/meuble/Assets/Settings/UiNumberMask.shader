// LEVELNUM: draws the level number's glyph quads into CardNumber's mask texture (a command buffer, outside any camera).
// The positions go to clip space through _NumberToClip (set by CardNumber: the zoom's scale over the canvas size), not
// through the camera matrices. Rendering into a texture on a platform whose texture rows start at the top (D3D, Metal,
// Vulkan through Unity's conversion) flips y, as Unity's own projection does, so the mask is sampled upright with
// ordinary UVs. Output: the font atlas coverage in every channel, kept at the maximum where glyphs overlap. No keyword;
// created from code only, so ProjectSetup lists it in Always Included Shaders.
Shader "OutOfSight/UI Number Mask"
{
    Properties
    {
        _MainTex ("Font atlas", 2D) = "white" {}
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

            fixed4 frag(v2f i) : SV_Target
            {
                fixed a = tex2D(_MainTex, i.uv).a;
                return fixed4(a, a, a, a);
            }
            ENDCG
        }
    }
}
