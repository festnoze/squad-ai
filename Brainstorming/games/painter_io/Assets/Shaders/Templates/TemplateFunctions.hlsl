// TemplateFunctions.hlsl - Custom Function file of the thin Shader Graph templates ThinUnlitOpaque and
// ThinUnlitTransparent (docs/SHADERGRAPH_TEMPLATE.md). Written by B0b.
// Its .meta carries the fixed GUID 8b2e4ad43a844401a144addd3ca5eaab: the graphs reference this file by that GUID.
//
// The function is a test pattern that proves, each on its own output channel, the three data paths a thin graph
// relies on (ShaderCheck.RenderTemplates reads them back from a RenderTexture):
//   BaseColor.r = vertex color red           (per-object data through vertex color)
//   BaseColor.g = uv1.x                       (per-object data through uv1)
//   BaseColor.b = _PIO_PlayerFade.x           (a _PIO_* global declared in LiquidCommon.hlsl, set by Shader.SetGlobal*)
//   Alpha       = vertex color alpha * uv1.y  (ignored by the Opaque template)
//
// Shader Graph calls <FunctionName>_<precision>: the graphs use Single precision, so PIO_TemplateSG_float is the one
// called; the _half overload keeps the file valid if someone switches a graph to Half.
#ifndef PIO_TEMPLATE_FUNCTIONS_INCLUDED
#define PIO_TEMPLATE_FUNCTIONS_INCLUDED

#include "Assets/Resources/Shaders/LiquidCommon.hlsl"

void PIO_TemplateSG_float(float4 VertexColor, float2 UV1, out float3 BaseColor, out float Alpha)
{
    BaseColor = float3(VertexColor.r, UV1.x, _PIO_PlayerFade.x);
    Alpha = VertexColor.a * UV1.y;
}

void PIO_TemplateSG_half(half4 VertexColor, half2 UV1, out half3 BaseColor, out half Alpha)
{
    float3 baseColor;
    float alpha;
    PIO_TemplateSG_float((float4)VertexColor, (float2)UV1, baseColor, alpha);
    BaseColor = (half3)baseColor;
    Alpha = (half)alpha;
}

#endif // PIO_TEMPLATE_FUNCTIONS_INCLUDED
