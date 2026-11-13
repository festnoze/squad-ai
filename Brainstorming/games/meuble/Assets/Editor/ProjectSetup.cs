using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace Meuble.Editor
{
    /// <summary>
    /// Idempotent project setup, run before every build and by verify.sh: the layers of PRD 8.3 (plus
    /// Furniture, layer 10, docs/CONTRACT_M2.md 6, and VisionCone, layer 11, docs/CONTRACT_M3.md 6), the
    /// URP Lit and Unlit shaders in Always Included Shaders (PRD 8.4), the Boot scene generated from code,
    /// the build scene list and the player settings. Project files are edited through the editor's own
    /// serialization, never by hand.
    /// M3 (docs/CONTRACT_M3.md 6): the renderer features. SSAO on PC_Renderer, and the four RenderObjects
    /// features of the x-ray (<see cref="XRay"/>) on PC_Renderer and Mobile_Renderer, with their two override
    /// materials in Assets/Settings. A feature is a sub-asset of the renderer: it is added through
    /// SerializedObject (m_RendererFeatures and m_Settings are not public), m_RendererFeatureMap is kept in sync
    /// with it, and an existing feature is found by type and name and reconfigured, never duplicated.
    /// </summary>
    public static class ProjectSetup
    {
        public const string ScenePath = "Assets/Scenes/Boot.unity";
        public const string ProductName = "UN, DEUX, TROIS, MEUBLE";

        private const int InhabitantLayerIndex = 8;

        private static readonly (int index, string name)[] RequiredLayers =
        {
            (OccluderLayerIndex, Layers.OccluderName), (7, Layers.PlayerName), (InhabitantLayerIndex, Layers.InhabitantName), (9, Layers.FloorName),
            (10, Layers.FurnitureName), (XRay.ConeLayerIndex, XRay.ConeLayerName),
        };

        public const string PcRendererPath = "Assets/Settings/PC_Renderer.asset";
        public const string MobileRendererPath = "Assets/Settings/Mobile_Renderer.asset";
        public const string SilhouetteMaterialPath = "Assets/Settings/XRay_Silhouette.mat";
        public const string ConeMaterialPath = "Assets/Settings/XRay_Cone.mat";
        public const string StencilMaterialPath = "Assets/Settings/XRay_StencilOnly.mat";
        private const int OccluderLayerIndex = 6;

        // The x-ray look: whatever a wall hides is blue, a hue no wall, floor or furniture uses. The silhouette is a
        // light, dense blue; the hidden part of a cone a deeper blue at about a third (M3.1: the M3 pale yellow at
        // 0.12 vanished on the cream walls). The gaze itself is the facing chevron of VisionConeView.
        private static readonly Color SilhouetteColor = new Color(0.22f, 0.52f, 1f, 0.7f);
        private static readonly Color ConeXRayColor = new Color(0.12f, 0.3f, 0.95f, 0.38f);

        // SSAO: contact shadows under the furniture and in the corners, kept light on a flat palette.
        private const float SsaoIntensity = 0.6f;
        private const float SsaoRadius = 0.3f;
        private const float SsaoDirectLighting = 0.25f;

        [MenuItem("Meuble/Project Setup")]
        public static void Apply()
        {
            EnsureLayers();
            EnsureAlwaysIncludedShaders();
            EnsureBootScene();
            EnsurePlayerSettings();
            EnsureRendererFeatures();
            AssetDatabase.SaveAssets();
            Debug.Log("[ProjectSetup] Layers, shaders, Boot scene, player settings and renderer features are in place.");
        }

        // ----- M3: renderer features -----

        private static void EnsureRendererFeatures()
        {
            Material silhouette = EnsureTransparentMaterial(SilhouetteMaterialPath, SilhouetteColor, CullMode.Back);
            Material cone = EnsureTransparentMaterial(ConeMaterialPath, ConeXRayColor, CullMode.Off);
            // Fully transparent: drawn only for its stencil write (URP Unlit has no ColorMask property).
            Material stencilOnly = EnsureTransparentMaterial(StencilMaterialPath, new Color(0f, 0f, 0f, 0f), CullMode.Back);
            foreach (string path in new[] { PcRendererPath, MobileRendererPath })
            {
                var data = AssetDatabase.LoadAssetAtPath<UniversalRendererData>(path);
                if (data == null)
                {
                    if (path == PcRendererPath)
                    {
                        throw new InvalidOperationException("Renderer data not found: " + path);
                    }
                    continue;
                }
                if (path == PcRendererPath)
                {
                    ConfigureSsao(EnsureFeature<ScreenSpaceAmbientOcclusion>(data, null));
                }
                int inhabitant = 1 << InhabitantLayerIndex;
                int cones = 1 << XRay.ConeLayerIndex;
                int occluders = 1 << OccluderLayerIndex;
                // 1. The visible pixels of the Occluder layer (the walls and every prop flagged as an occluder) mark
                //    the stencil (an invisible material, drawn where the occluder already won the depth test). Only
                //    there may the x-ray draw: never over the red chair, another prop or an inhabitant in plain sight.
                Configure(EnsureFeature<RenderObjects>(data, XRay.MaskFeature), RenderPassEvent.AfterRenderingOpaques,
                    RenderQueueType.Opaque, occluders, stencilOnly, CompareFunction.LessEqual,
                    Stencil(CompareFunction.Always, StencilOp.Replace));
                // 2. The part of every vision cone that a wall hides, faint, after the regular transparents.
                Configure(EnsureFeature<RenderObjects>(data, XRay.ConeFeature), RenderPassEvent.AfterRenderingTransparents + 1,
                    RenderQueueType.Transparent, cones, cone, CompareFunction.Greater,
                    Stencil(CompareFunction.Equal, StencilOp.Keep));
                // 3. The part of every inhabitant that a wall hides, as one flat silhouette. Each pixel is drawn once
                //    (the pass bumps the stencil off the mark), so overlapping limbs never stack.
                Configure(EnsureFeature<RenderObjects>(data, XRay.SilhouetteFeature), RenderPassEvent.AfterRenderingTransparents + 2,
                    RenderQueueType.Opaque, inhabitant, silhouette, CompareFunction.Greater,
                    Stencil(CompareFunction.Equal, StencilOp.IncrementSaturate));
                // 4. The "?" and "!" markers (world space UI, transparent queue, Inhabitant layer) over everything.
                Configure(EnsureFeature<RenderObjects>(data, XRay.MarkerFeature), RenderPassEvent.AfterRenderingTransparents + 3,
                    RenderQueueType.Transparent, inhabitant, null, CompareFunction.Always, null);
                SyncFeatureMap(data);
                data.SetDirty();
                EditorUtility.SetDirty(data);
                AssetDatabase.SaveAssetIfDirty(data);
            }
        }

        /// <summary>A stencil test against the occluder mark (<see cref="XRay.StencilMark"/>).</summary>
        private static StencilStateData Stencil(CompareFunction compare, StencilOp pass)
        {
            return new StencilStateData
            {
                overrideStencilState = true,
                stencilReference = XRay.StencilMark,
                stencilCompareFunction = compare,
                passOperation = pass,
                failOperation = StencilOp.Keep,
                zFailOperation = StencilOp.Keep,
            };
        }

        /// <summary>
        /// The feature of type <typeparamref name="T"/> named <paramref name="name"/> (any name when null), or a new
        /// one added as a sub-asset of the renderer, at the end of m_RendererFeatures and of m_RendererFeatureMap.
        /// </summary>
        private static T EnsureFeature<T>(ScriptableRendererData data, string name) where T : ScriptableRendererFeature
        {
            foreach (ScriptableRendererFeature f in data.rendererFeatures)
            {
                if (f is T typed && (name == null || f.name == name))
                {
                    return typed;
                }
            }
            T feature = ScriptableObject.CreateInstance<T>();
            feature.name = name ?? typeof(T).Name;
            AssetDatabase.AddObjectToAsset(feature, data);
            AssetDatabase.TryGetGUIDAndLocalFileIdentifier(feature, out string _, out long localId);
            var so = new SerializedObject(data);
            SerializedProperty list = so.FindProperty("m_RendererFeatures");
            SerializedProperty map = so.FindProperty("m_RendererFeatureMap");
            list.arraySize++;
            list.GetArrayElementAtIndex(list.arraySize - 1).objectReferenceValue = feature;
            map.arraySize++;
            map.GetArrayElementAtIndex(map.arraySize - 1).longValue = localId;
            so.ApplyModifiedPropertiesWithoutUndo();
            Debug.Log($"[ProjectSetup] Added renderer feature '{feature.name}' to {data.name}.");
            return feature;
        }

        /// <summary>m_RendererFeatureMap holds, for each entry of m_RendererFeatures, the local file id of that sub-asset.</summary>
        private static void SyncFeatureMap(ScriptableRendererData data)
        {
            var so = new SerializedObject(data);
            SerializedProperty list = so.FindProperty("m_RendererFeatures");
            SerializedProperty map = so.FindProperty("m_RendererFeatureMap");
            bool changed = map.arraySize != list.arraySize;
            map.arraySize = list.arraySize;
            for (int i = 0; i < list.arraySize; i++)
            {
                UnityEngine.Object feature = list.GetArrayElementAtIndex(i).objectReferenceValue;
                long localId = 0;
                if (feature != null)
                {
                    AssetDatabase.TryGetGUIDAndLocalFileIdentifier(feature, out string _, out localId);
                }
                SerializedProperty entry = map.GetArrayElementAtIndex(i);
                if (entry.longValue != localId)
                {
                    entry.longValue = localId;
                    changed = true;
                }
            }
            if (changed)
            {
                so.ApplyModifiedPropertiesWithoutUndo();
                Debug.Log($"[ProjectSetup] m_RendererFeatureMap of {data.name} resynchronized.");
            }
        }

        private static void Configure(RenderObjects feature, RenderPassEvent evt, RenderQueueType queue, int layerMask, Material material,
            CompareFunction depth, StencilStateData stencil)
        {
            RenderObjects.RenderObjectsSettings s = feature.settings;
            s.passTag = feature.name;
            s.Event = evt;
            s.filterSettings.RenderQueueType = queue;
            s.filterSettings.LayerMask = layerMask;
            s.filterSettings.PassNames = new string[0];
            s.overrideMode = material != null
                ? RenderObjects.RenderObjectsSettings.OverrideMaterialMode.Material
                : RenderObjects.RenderObjectsSettings.OverrideMaterialMode.None;
            s.overrideMaterial = material;
            s.overrideMaterialPassIndex = 0;
            s.overrideShader = null;
            s.overrideDepthState = true;
            s.depthCompareFunction = depth;
            s.enableWrite = false;
            s.stencilSettings = stencil ?? new StencilStateData();
            s.cameraSettings = new RenderObjects.CustomCameraSettings();
            feature.SetActive(true);
            EditorUtility.SetDirty(feature);
        }

        /// <summary>SSAO settings are private (m_Settings of an internal type): set through SerializedObject.</summary>
        private static void ConfigureSsao(ScreenSpaceAmbientOcclusion ssao)
        {
            var so = new SerializedObject(ssao);
            SerializedProperty settings = so.FindProperty("m_Settings");
            if (settings == null)
            {
                throw new InvalidOperationException("SSAO m_Settings not found: the URP version changed its layout");
            }
            Set(settings, "AOMethod", 0);          // blue noise
            Set(settings, "Downsample", false);
            Set(settings, "AfterOpaque", false);   // applied in the lighting, not multiplied over the image
            Set(settings, "Source", 1);            // depth normals
            Set(settings, "NormalSamples", 1);     // medium
            Set(settings, "Intensity", SsaoIntensity);
            Set(settings, "DirectLightingStrength", SsaoDirectLighting);
            Set(settings, "Radius", SsaoRadius);
            Set(settings, "Samples", 1);           // medium
            Set(settings, "BlurQuality", 0);       // high
            Set(settings, "Falloff", 100f);
            so.ApplyModifiedPropertiesWithoutUndo();
            ssao.SetActive(true);
            EditorUtility.SetDirty(ssao);
        }

        private static void Set(SerializedProperty parent, string name, float value)
        {
            Find(parent, name).floatValue = value;
        }

        private static void Set(SerializedProperty parent, string name, int value)
        {
            Find(parent, name).intValue = value;
        }

        private static void Set(SerializedProperty parent, string name, bool value)
        {
            Find(parent, name).boolValue = value;
        }

        private static SerializedProperty Find(SerializedProperty parent, string name)
        {
            SerializedProperty p = parent.FindPropertyRelative(name);
            if (p == null)
            {
                throw new InvalidOperationException("SSAO setting not found: " + name);
            }
            return p;
        }

        /// <summary>An alpha blended URP Unlit material asset (the x-ray overrides ship because the renderer references them).</summary>
        private static Material EnsureTransparentMaterial(string path, Color color, CullMode cull)
        {
            Shader shader = Shader.Find(PrimitiveKit.UnlitShaderName);
            if (shader == null)
            {
                throw new InvalidOperationException("Shader not found in the editor: " + PrimitiveKit.UnlitShaderName);
            }
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m == null)
            {
                m = new Material(shader) { name = Path.GetFileNameWithoutExtension(path) };
                AssetDatabase.CreateAsset(m, path);
            }
            m.shader = shader;
            m.SetFloat("_Surface", 1f);
            m.SetFloat("_Blend", 0f);
            m.SetFloat("_Cull", (float)cull);
            m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
            m.SetFloat("_DstBlendAlpha", (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_ZWrite", 0f);
            m.SetOverrideTag("RenderType", "Transparent");
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            m.SetColor("_BaseColor", color);
            EditorUtility.SetDirty(m);
            return m;
        }

        private static void EnsureLayers()
        {
            UnityEngine.Object[] assets = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/TagManager.asset");
            if (assets.Length == 0)
            {
                throw new InvalidOperationException("TagManager.asset not found");
            }
            var tagManager = new SerializedObject(assets[0]);
            SerializedProperty layers = tagManager.FindProperty("layers");
            bool changed = false;
            foreach ((int index, string name) in RequiredLayers)
            {
                SerializedProperty slot = layers.GetArrayElementAtIndex(index);
                if (slot.stringValue != name)
                {
                    if (!string.IsNullOrEmpty(slot.stringValue))
                    {
                        Debug.LogWarning($"[ProjectSetup] Layer {index} was '{slot.stringValue}', now '{name}'.");
                    }
                    slot.stringValue = name;
                    changed = true;
                }
            }
            if (changed)
            {
                tagManager.ApplyModifiedPropertiesWithoutUndo();
            }
        }

        private static void EnsureAlwaysIncludedShaders()
        {
            var graphics = AssetDatabase.LoadAssetAtPath<GraphicsSettings>("ProjectSettings/GraphicsSettings.asset");
            if (graphics == null)
            {
                throw new InvalidOperationException("GraphicsSettings.asset not found");
            }
            var so = new SerializedObject(graphics);
            SerializedProperty list = so.FindProperty("m_AlwaysIncludedShaders");
            var present = new HashSet<Shader>();
            for (int i = 0; i < list.arraySize; i++)
            {
                if (list.GetArrayElementAtIndex(i).objectReferenceValue is Shader s)
                {
                    present.Add(s);
                }
            }
            bool changed = false;
            foreach (string name in new[] { PrimitiveKit.LitShaderName, PrimitiveKit.UnlitShaderName })
            {
                Shader shader = Shader.Find(name);
                if (shader == null)
                {
                    throw new InvalidOperationException("Shader not found in the editor: " + name);
                }
                if (!present.Contains(shader))
                {
                    list.InsertArrayElementAtIndex(list.arraySize);
                    list.GetArrayElementAtIndex(list.arraySize - 1).objectReferenceValue = shader;
                    changed = true;
                }
            }
            if (changed)
            {
                so.ApplyModifiedPropertiesWithoutUndo();
            }
        }

        /// <summary>Boot.unity holds a single GameObject with Main; everything else is built at runtime.</summary>
        private static void EnsureBootScene()
        {
            if (!File.Exists(ScenePath))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(ScenePath));
                Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                var main = new GameObject("Main");
                main.AddComponent<Main>();
                if (!EditorSceneManager.SaveScene(scene, ScenePath))
                {
                    throw new InvalidOperationException("Could not save " + ScenePath);
                }
            }
            EditorBuildSettingsScene[] current = EditorBuildSettings.scenes;
            if (current.Length != 1 || current[0].path != ScenePath || !current[0].enabled)
            {
                EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            }
        }

        private static void EnsurePlayerSettings()
        {
            if (PlayerSettings.productName != ProductName)
            {
                PlayerSettings.productName = ProductName;
            }
            if (PlayerSettings.companyName != "Meuble")
            {
                PlayerSettings.companyName = "Meuble";
            }
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.defaultScreenWidth = 1600;
            PlayerSettings.defaultScreenHeight = 900;
            PlayerSettings.resizableWindow = true;
            PlayerSettings.runInBackground = true;
            PlayerSettings.visibleInBackground = true;
            PlayerSettings.SetManagedStrippingLevel(UnityEditor.Build.NamedBuildTarget.Standalone, ManagedStrippingLevel.Low);
        }
    }
}
