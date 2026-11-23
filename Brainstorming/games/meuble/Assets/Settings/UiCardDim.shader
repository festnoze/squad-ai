// LEVELNUM: the intro card's full-screen layer (CardNumber, a RawImage under every other HUD element). _MainTex is the
// level number's coverage mask (CardNumber renders it, red channel): 0 gives the greyish-black dim, 1 the light white
// wash, so the digits are holes in the dim through which the scene shows slightly whitened. Plain alpha blending only:
// no stencil, depth or destination colour, so it draws the same in a Screen Space Overlay canvas on the back buffer, in
// a camera-space canvas and in an offscreen UI pass. The vertex alpha carries the card's fade (CanvasGroup). No keyword;
// created from code only, so ProjectSetup lists it in Always Included Shaders.
Shader "OutOfSight/UI Card Dim"
{
    Properties
    {
        [PerRendererData] _MainTex ("Number mask", 2D) = "black" {}
        _DimColor ("Dim (outside the digits)", Color) = (0.07, 0.07, 0.08, 0.5)
        _WashColor ("Wash (inside the digits)", Color) = (1, 1, 1, 0.2)
    }
    SubShader
    {
        Tags { "Queue" = "Transparent" "IgnoreProjector" = "True" "RenderType" = "Transparent" "PreviewType" = "Plane" }
        Cull Off
        Lighting Off
        ZWrite Off
        ZTest [unity_GUIZTestMode]
        Blend SrcAlpha OneMinusSrcAlpha

        Pass
        {
            Name "CardDim"
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 2.0
            #include "UnityCG.cginc"

            struct appdata
            {
                float4 vertex : POSITION;
                float4 color : COLOR;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct v2f
            {
                float4 pos : SV_POSITION;
                fixed4 color : COLOR;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _DimColor;
            fixed4 _WashColor;

            v2f vert(appdata v)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                o.color = v.color;
                return o;
            }

            float4 frag(v2f i) : SV_Target
            {
                float m = saturate(tex2D(_MainTex, i.uv).r);
                // Mixed premultiplied: at a glyph's antialiased edge, half dim and half wash is a darker, half-opaque
                // pixel. Mixing colour and alpha apart gave a mid-grey at mid alpha there: a pale rim around the digits.
                float a = lerp(_DimColor.a, _WashColor.a, m);
                float3 premultiplied = lerp(_DimColor.rgb * _DimColor.a, _WashColor.rgb * _WashColor.a, m);
                return float4(premultiplied / max(a, 1e-4), a * i.color.a);
            }
            ENDCG
        }
    }
}
