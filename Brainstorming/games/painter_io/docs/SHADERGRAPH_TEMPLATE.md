# Thin Shader Graph templates (how to clone them)

Written by B0b (editor and shader tooling) for B1 (LiquidComposite) and B2 (Bead, Overlay). Normative background:
docs/CONTRACT.md 12.1 (shader policy) and 12.2 (architecture). Everything below was verified on Unity 6000.3.23f1, URP 17.3,
Shader Graph 17.3: both templates import with no error, compile all 6 passes of their URP subshader, and render the expected
pixels (section 8).

## 1. What a thin graph is

A thin graph has no logic. Input nodes (Vertex Color, UV, Position) feed ONE Custom Function node in File mode; its outputs go
to the Base Color and Alpha blocks. All the math lives in an `.hlsl` file that includes `LiquidCommon.hlsl`. The graph exposes
exactly one property, the hidden marker `_PIO_ShaderId`. Every `_PIO_*` global is declared in `LiquidCommon.hlsl`, never as a
graph property. Per-object data arrives through vertex attributes (vertex color, uv1, uv2), never through a
MaterialPropertyBlock.

## 2. Files and fixed GUIDs

| File | GUID | Notes |
|---|---|---|
| `Assets/Shaders/Templates/ThinUnlitOpaque.shadergraph` | `6d821ab77a86456e855b68afe84307d3` | object ids `a1000000000000000000000000000NNN` |
| `Assets/Shaders/Templates/ThinUnlitTransparent.shadergraph` | `814534424b124a5e8eed25671d8f10e6` | object ids `b1000000000000000000000000000NNN` |
| `Assets/Shaders/Templates/TemplateFunctions.hlsl` | `8b2e4ad43a844401a144addd3ca5eaab` | function `PIO_TemplateSG_float` |
| `Assets/Resources/Shaders/LiquidCommon.hlsl` | `d210809a08e442a9a9875e8fb65efb22` | the `_PIO_*` globals, `PIO_Height`, `PIO_ShadeLiquid` |
| `Assets/Resources/Shaders/FieldBlob.shader` | `4c1a4d029c63424b81d653947dfa3ab8` | hand-written HLSL (not a graph) |
| `Assets/Resources/Shaders/FieldStroke.shader` | `94686ce4ecf246d8a8bf30b27985c944` | hand-written HLSL (not a graph) |

The templates live outside `Resources`, so they never ship in a player. Shader names:
`Shader Graphs/PainterIO/ThinUnlitOpaque` and `Shader Graphs/PainterIO/ThinUnlitTransparent`.

Template settings (UniversalTarget, Unlit sub target):

| Template | m_SurfaceType | m_AlphaMode | m_ZTestMode | m_ZWriteControl | m_RenderFace | Queue |
|---|---|---|---|---|---|---|
| ThinUnlitOpaque | 0 Opaque | 0 Alpha (unused) | 8 Always | 2 ForceDisabled | 0 Both (Cull Off) | 2000 Geometry |
| ThinUnlitTransparent | 1 Transparent | 0 Alpha (Blend SrcAlpha OneMinusSrcAlpha) | 8 Always | 2 ForceDisabled | 0 Both | 3000 Transparent |

Clone ThinUnlitOpaque for LiquidComposite; clone ThinUnlitTransparent for Bead and Overlay.

## 3. Object id map of a template

Shader Graph files are "multi-JSON": one JSON object per block, blocks separated by ONE blank line. Objects reference each
other by `m_ObjectId` (32 hex characters, unique inside the file). In ThinUnlitOpaque the ids are `a1` + 27 zeros + a 3 digit
suffix (ThinUnlitTransparent uses `b1`):

| Suffix | Object | Role |
|---|---|---|
| 001 | GraphData | `m_Path`, `m_Nodes`, `m_Edges`, contexts, `m_ActiveTargets` |
| 002 | CategoryData | lists the property |
| 003 | Vector1ShaderProperty | `_PIO_ShaderId` (hidden, default 1) |
| 004 | UniversalTarget | surface type, blend, depth, cull |
| 005 | UniversalUnlitSubTarget | Unlit |
| 010 / 011 | BlockNode VertexDescription.Position + slot | vertex context |
| 012 / 013 | BlockNode VertexDescription.Normal + slot | vertex context |
| 014 / 015 | BlockNode VertexDescription.Tangent + slot | vertex context |
| 016 / 017 | BlockNode SurfaceDescription.BaseColor + slot | fragment context |
| 018 / 019 | BlockNode SurfaceDescription.Alpha + slot | fragment context |
| 020 / 021 | VertexColorNode + its Out slot (Vector4) | input |
| 022 / 023 | UVNode (`m_OutputChannel` 1 = uv1) + its Out slot (Vector4) | input |
| 024 | CustomFunctionNode | `m_SourceType` 0 (File), `m_FunctionName`, `m_FunctionSource` = .hlsl GUID |
| 025 | Vector4MaterialSlot `VertexColor`, slot id 0, input | function parameter 1 |
| 026 | Vector2MaterialSlot `UV1`, slot id 1, input | function parameter 2 |
| 027 | Vector3MaterialSlot `BaseColor`, slot id 2, output | function parameter 3 (out) |
| 028 | Vector1MaterialSlot `Alpha`, slot id 3, output | function parameter 4 (out) |

Edges (in GraphData `m_Edges`): 020 slot 0 -> 024 slot 0, 022 slot 0 -> 024 slot 1, 024 slot 2 -> 016 slot 0 (Base Color),
024 slot 3 -> 018 slot 0 (Alpha). A slot is addressed by its node object id plus its integer `m_Id`, never by the slot's
object id.

## 4. Clone recipe (example: B2 makes Bead from ThinUnlitTransparent)

Do steps 1 and 2 BEFORE any Unity run sees the files: a `.hlsl` imported without a `.meta` gets a random GUID, and every graph
that references the fixed GUID then silently fails (section 9).

1. **Function file and its .meta.** Write `Assets/Resources/Shaders/Bead.hlsl` and `Assets/Resources/Shaders/Bead.hlsl.meta`.
   Make a GUID with `[guid]::NewGuid().ToString('N')` (PowerShell), check it is unused
   (`Select-String -Path Assets -Recurse ...` or Grep for it), and record it in your report. The .meta text, exactly:
   ```
   fileFormatVersion: 2
   guid: <your 32 hex GUID>
   ShaderIncludeImporter:
     externalObjects: {}
     userData:
     assetBundleName:
     assetBundleVariant:
   ```
   The function file (graph precision is Single, so Shader Graph calls `<FunctionName>_float`):
   ```hlsl
   #ifndef PIO_BEAD_INCLUDED
   #define PIO_BEAD_INCLUDED
   #include "Assets/Resources/Shaders/LiquidCommon.hlsl"
   // Inputs first, in slot order, then outputs, in slot order (that is the call Shader Graph generates).
   void PIO_BeadSG_float(float4 VertexColor, float4 UV1, float2 UV0, out float3 BaseColor, out float Alpha)
   {
       // ... math, may read any _PIO_* global and call PIO_Height / PIO_ShadeLiquid ...
   }
   #endif
   ```
   An optional `PIO_BeadSG_half` overload keeps the file valid if someone switches the graph to Half precision.
2. **Graph and its .meta.** Copy `ThinUnlitTransparent.shadergraph` to `Assets/Resources/Shaders/Bead.shadergraph` and write
   `Bead.shadergraph.meta` with a NEW GUID:
   ```
   fileFormatVersion: 2
   guid: <new 32 hex GUID>
   ScriptedImporter:
     internalIDToNameTable: []
     externalObjects: {}
     serializedVersion: 2
     userData: 
     assetBundleName: 
     assetBundleVariant: 
     script: {fileID: 11500000, guid: 625f186215c104763be7675aa2d941aa, type: 3}
   ```
   (`625f186215c104763be7675aa2d941aa` is the ShaderGraphImporter script; do not change it.)
3. **Object ids.** Every id of the template is `b1` + 27 zeros + a 3 digit suffix (32 characters). Replace the 29 character
   prefix everywhere in the file, for example in PowerShell:
   `$t = Get-Content Bead.shadergraph -Raw; $t.Replace("b1" + "0" * 27, "e2" + "0" * 27) | Set-Content Bead.shadergraph -NoNewline`.
   A global replace keeps every reference consistent. Ids only need to be unique inside one file, but a distinct prefix per
   graph makes copy-paste mistakes visible. Also give the property a fresh `m_Guid.m_GuidSerialized` (dashed form,
   `[guid]::NewGuid().ToString()`).
4. **Custom Function node (suffix 024).** Set:
   - `"m_FunctionName": "PIO_BeadSG"` (no `_float` suffix: Shader Graph appends the precision),
   - `"m_FunctionSource": "<GUID of Bead.hlsl>"` (the GUID from step 1, without dashes),
   - `"m_Name": "PIO_BeadSG (Custom Function)"` (display only),
   - keep `"m_SourceType": 0` (File; 1 would be String mode) and `"m_FunctionSourceUsePragmas": true`.
5. **Function parameters = node slots.** One slot object per parameter, listed in the node's `m_Slots` in the HLSL parameter
   order (all inputs, then all outputs). Per slot object:
   - `m_Type`: `UnityEditor.ShaderGraph.Vector1MaterialSlot` (float), `Vector2MaterialSlot` (float2), `Vector3MaterialSlot`
     (float3) or `Vector4MaterialSlot` (float4),
   - `m_Id`: small integer unique inside the node (edges use it),
   - `m_DisplayName` and `m_ShaderOutputName`: the HLSL parameter name,
   - `m_SlotType`: 0 input, 1 output; `m_StageCapability`: 3 (vertex and fragment) is fine,
   - `m_Value` / `m_DefaultValue`: the value used when an input is left unconnected (same shape as the type).
   To add an input, copy slot 026 (a Vector2) or 025 (a Vector4), give it a new object id and `m_Id`, insert its object id in
   `m_Slots` at the right position, and renumber nothing else (edges refer to `m_Id`, not to positions).
6. **Input nodes.** Copy the UV node (022/023) for another channel and set `"m_OutputChannel"`: 0 = uv0, 1 = uv1, 2 = uv2, ...
   The UV node outputs the full float4 of that channel, so a mesh can pass four floats per channel. World or object position:
   ```json
   {
       "m_SGVersion": 1,
       "m_Type": "UnityEditor.ShaderGraph.PositionNode",
       "m_ObjectId": "e2000000000000000000000000000030",
       "m_Group": { "m_Id": "" },
       "m_Name": "Position",
       "m_DrawState": { "m_Expanded": true, "m_Position": { "serializedVersion": "2", "x": -760.0, "y": 420.0, "width": 208.0, "height": 315.0 } },
       "m_Slots": [ { "m_Id": "e2000000000000000000000000000031" } ],
       "synonyms": [],
       "m_Precision": 0,
       "m_PreviewExpanded": false,
       "m_PreviewMode": 2,
       "m_CustomColors": { "m_SerializableColors": [] },
       "m_Space": 2
   }
   ```
   with its output slot (a `Vector3MaterialSlot`, `"m_Id": 0`, `"m_DisplayName": "Out"`, `"m_ShaderOutputName": "Out"`,
   `"m_SlotType": 1`, zero `m_Value` / `m_DefaultValue`, `"m_Labels": []`). `m_Space`: 0 Object, 2 World, 4 Absolute World
   (URP has no camera-relative rendering, so World and Absolute World are the same). Add every new node object id to
   GraphData `m_Nodes` and wire it with an edge:
   ```json
   { "m_OutputSlot": { "m_Node": { "m_Id": "<source node id>" }, "m_SlotId": 0 },
     "m_InputSlot":  { "m_Node": { "m_Id": "<custom function node id>" }, "m_SlotId": <input slot m_Id> } }
   ```
   Pretty-printing does not matter, but keep exactly one blank line between top-level objects and no blank line inside one.
7. **Target settings (suffix 004).** Keep the template's values unless the contract says otherwise (table in section 2). Keep
   `m_AllowMaterialOverride` false (true turns the surface settings into material properties and adds a ShadowCaster pass),
   `m_CastShadows` and `m_ReceiveShadows` false.
8. **Shader path.** Keep GraphData `"m_Path": "Shader Graphs/PainterIO"`. The file name gives the last part, so
   `Bead.shadergraph` is `Shader Graphs/PainterIO/Bead`. ShaderCheck fails any graph in Resources/Shaders whose name differs.
9. **Marker property (suffix 003).** Keep it as is: `m_OverrideReferenceName` `_PIO_ShaderId`, `m_Hidden` true, `m_Value` 1,
   `m_GeneratePropertyBlock` true. Add no other property. ShaderCheck fails a graph with any other `_PIO_*` property.
10. **Never** leave a `.shader` and a `.shadergraph` of the same name in Resources/Shaders (ShaderCheck fails it:
    `Resources.Load` would be ambiguous).

## 5. Runtime use

- Load: `Resources.Load<Shader>("Shaders/Bead")` (works for a `.shadergraph` main asset); never `Shader.Find`.
- Material: `new Material(shader)`; set `material.renderQueue` in code when the contract asks for a specific queue
  (LiquidComposite: Geometry-100 = 1900). Do not rely on the graph default for that.
- Per-object data through the mesh, so the SRP Batcher stays valid:
  - vertex color: `mesh.SetColors(List<Color>)` arrives raw (float, no sRGB to linear conversion), `List<Color32>` arrives
    as bytes / 255. Convert palette colors with `Color.linear` yourself if the math wants linear values, or read the
    `_PIO_Colors` global instead.
  - uv1, uv2: `mesh.SetUVs(1, List<Vector4>)`, `mesh.SetUVs(2, List<Vector4>)` (four floats each, read through UV nodes with
    `m_OutputChannel` 1 and 2).
  - Never a MaterialPropertyBlock on a graph renderer (the FieldBlob / FieldStroke `.shader` contributors are the only users
    of MaterialPropertyBlock, contract 12.2).
- Globals: `Shader.SetGlobalTexture / SetGlobalVector / SetGlobalFloat / SetGlobalVectorArray` with the `_PIO_*` names of
  `LiquidCommon.hlsl`. An unset global reads as 0.

## 6. Rules for the .hlsl function file

- Include guard, then `#include "Assets/Resources/Shaders/LiquidCommon.hlsl"` (it includes URP `Core.hlsl`; both are
  guarded, so including them again is free). Never redeclare a `_PIO_*` global.
- Define `<FunctionName>_float`. Parameter names must match the slots' `m_ShaderOutputName`, types must match the slot types.
- The same surface code is compiled into every pass of the Unlit sub target (Universal Forward, MotionVectors,
  DepthNormalsOnly, GBuffer, SceneSelectionPass, ScenePickingPass): no pass-specific macros, keep it valid everywhere.
- The function runs in the fragment stage when it feeds Base Color / Alpha, so `fwidth`, `ddx`, `ddy` and
  `SAMPLE_TEXTURE2D(_PIO_ActorField, sampler_PIO_ActorField, uv)` are allowed. In the vertex stage use `SAMPLE_TEXTURE2D_LOD`.
- Output linear RGB (the project is in Linear color space; URP converts to sRGB on output).

## 7. Verifying a new graph

1. `pwsh -NoProfile -File tools/unity.ps1 -Agent <you> -UnityArgs "run . --timeout 1800 -- -executeMethod PainterIO.Editor.Builder.SetupAndCompile -logFile Logs/<you>_setup.log"`
2. In the log, each shader prints one line; a healthy Unlit graph reads
   `[ShaderCheck] Assets/Resources/Shaders/Bead.shadergraph: 'Shader Graphs/PainterIO/Bead', queue 3000, 6 pass(es) compiled: Universal Forward, MotionVectors, DepthNormalsOnly, GBuffer, SceneSelectionPass, ScenePickingPass`
   then `[ShaderCheck] PASS Assets/Resources/Shaders`. "1 pass(es)" on a graph means a fallback or error shader is running.
3. Build the player and look at the DevShot PNGs (contract 23.3). Editor checks cannot see player-only problems.

ShaderCheck fails on: no Shader main asset, ShaderUtil.ShaderHasError, any Error message, errors logged during import or
compilation, the internal error shader, a missing `_PIO_ShaderId`, any other `_PIO_*` property, an active subshader that is not
tagged `"RenderPipeline"="UniversalPipeline"` or whose pass count differs from the material's, a wrong graph shader name, two
assets with the same name, an `.hlsl` without `.meta`, a Custom Function GUID that resolves to no `.hlsl`, and an `.hlsl` that
defines neither `<FunctionName>_float` nor `<FunctionName>_half`.

## 8. How the templates were proven

`PainterIO.Editor.ShaderCheck.RenderTemplatesBatch` (re-runnable:
`-UnityArgs "run . --timeout 1800 -- -executeMethod PainterIO.Editor.ShaderCheck.RenderTemplatesBatch -shotDir TestResults -logFile Logs/<you>_render.log"`)
runs RunTemplates, then renders each template on a quad into a linear 64 x 64 RenderTexture through a temporary orthographic
camera, in batch mode (the editor has a real D3D12 device even with -batchmode). The template function outputs
BaseColor = (vertex color r, uv1.x, `_PIO_PlayerFade.x`) and Alpha = vertex color a * uv1.y, with vertex color
(0.8, 0.1, 0.1, 1), uv1 (0.3, 0.5) and `Shader.SetGlobalVector("_PIO_PlayerFade", (0.6, 0, 0, 0))`. A white URP Unlit quad
sits in FRONT of the template on the left half (drawn first), a green one BEHIND it on the bottom-right quadrant (drawn after).
Measured (2026-11-26):

| Template | left (over the nearer white) | top-right (over the blue clear) | bottom-right |
|---|---|---|---|
| ThinUnlitOpaque | (0.800, 0.298, 0.600) = T | (0.800, 0.298, 0.600) = T | green (ZWrite off) |
| ThinUnlitTransparent | (0.898, 0.647, 0.800) = T/2 + white/2 | (0.400, 0.149, 0.800) = T/2 + blue/2 | green (ZWrite off) |

This proves, in one go: the File-mode Custom Function resolves its `.hlsl` by GUID, vertex color and uv1 reach the function,
a `_PIO_*` global declared only in `LiquidCommon.hlsl` follows `Shader.SetGlobalVector`, ZTest Always draws over nearer
geometry, ZWrite ForceDisabled leaves the depth buffer alone, and the Transparent template blends SrcAlpha OneMinusSrcAlpha.
The images are written to `TestResults/B0b_render_<template>.png`.

The same batch method also proves the two hand-written actor field contributors (`RenderFieldContributors`): a 64 x 64
R16G16B16A16_SFloat RT cleared to (0, 0, 0, 0), camera settings of ActorFieldCamera (allowHDR off, MSAA off),
`_PIO_ActorScale` = 0.5, MaterialPropertyBlock `_Channel` / `_Amplitude`. Three FieldBlob quads (one red channel amplitude 1,
two alpha channel amplitude 0.8) give R = 0.4995 and A = 0.7988 at the center (= 1 x 0.5 and 2 x 0.8 x 0.5: additive, alpha is
data), and every sample matches `A saturate(1 - |q|^2)^2 x 0.5`. A FieldStroke strip (uv0.x amplitude multiplier 1 to 0.5,
uv0.y cross coordinate -1 to 1) matches `0.6 m(x) saturate(1 - y^2)^2 x 0.5` within 1e-3. Images:
`TestResults/B0b_render_FieldBlob.png`, `TestResults/B0b_render_FieldStroke.png` (R, G, A shown as R, G, B). Any error logged
during either render check fails it.

## 9. Pitfalls (hit or checked while building the templates)

- **Batch-mode false green.** Until a camera renders, the URP pipeline instance does not exist and `Shader.globalRenderPipeline`
  is empty. Every `"RenderPipeline"="UniversalPipeline"` subshader is then unsupported, and a Shader Graph runs its
  `FallBack "Hidden/Shader Graph/FallbackError"`: 1 pass, queue 2000, but the properties (and `_PIO_ShaderId`) are still
  there. Compiling "every pass of the material" then compiles the fallback and the check passes while the graph code was never
  compiled; a Transparent graph even reports queue 2000. ShaderCheck now renders one warm-up frame first
  (`EnsureUniversalPipelineActive`) and asserts the active subshader is the URP one. If you write your own editor check,
  do the same.
- **A camera target RenderTexture needs a depth buffer (URP 17 Render Graph).** A camera whose `targetTexture` has no
  depth-stencil format draws NOTHING and only logs "In the render graph API, the output Render Texture must have a depth
  buffer" and "Fake or uninitialized surface is not supported for attachment 0". This applies to ActorFieldCamera's
  `_PIO_ActorField` (contract 19 says "no depth" for RTs: for that camera target use at least a 16 bit depth buffer, for
  example `new RenderTextureDescriptor(w, h, GraphicsFormat.R16G16B16A16_SFloat, 16)`). The territory blur passes drawn with
  a CommandBuffer and `Graphics.ExecuteCommandBuffer` are not concerned. The field render check hit exactly this (all zeros)
  before its RT got a depth buffer.
- **A regenerated .meta breaks the graph silently.** A Custom Function in File mode stores only the `.hlsl` GUID. If Unity
  imports the `.hlsl` before its hand-written `.meta` exists, it invents a GUID; the graph then generates no code for the node
  and imports as an error shader (magenta, no properties). Write the `.meta` first; ShaderCheck names this case.
- **The Shader Graph error shader has no properties.** That is why every shader carries `_PIO_ShaderId`: a missing marker means
  the graph failed to generate (see the import log for the node error).
- **Precision suffix.** `m_FunctionName` has no suffix; the graph (Single precision, `m_GraphPrecision` 0) calls `_float`.
- **Serialization versions.** Keep the template's `m_SGVersion` values (GraphData 3, UniversalTarget 1, UniversalUnlitSubTarget
  2, CustomFunctionNode 1, Vector1ShaderProperty 1, PositionNode 1, slots and block nodes 0). A lower version runs an upgrade
  path on import that can rewrite fields.
- **Pass list.** Opaque + ZWrite ForceDisabled has no DepthOnly pass (6 passes). If a DepthOnly pass appears, ZWrite is not
  disabled. There is no ShadowCaster pass as long as `m_CastShadows` and `m_AllowMaterialOverride` stay false.
- **Graph properties are per-material.** A property lands in UnityPerMaterial, and `Shader.SetGlobal*` on the same name is then
  ignored for that material. Hence the rule: globals only in `LiquidCommon.hlsl`.
- **Opening a graph in the Shader Graph window and saving it** is allowed: it rewrites the file with new random object ids but
  keeps the `.hlsl` GUID reference. Re-run SetupAndCompile afterwards.
