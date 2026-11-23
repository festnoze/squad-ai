using System;
using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using UnityEditor;
using UnityEditor.Android;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace OutOfSight.Editor
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
        public const string ProductName = "Out of Sight";

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
        // 0.85 opaque: at 0.7 the warm cream crepi walls (2026-11-18) washed the blue out to a faint tint.
        private static readonly Color SilhouetteColor = new Color(0.22f, 0.52f, 1f, 0.85f);
        private static readonly Color ConeXRayColor = new Color(0.12f, 0.3f, 0.95f, 0.38f);

        // SSAO: contact shadows under the furniture and in the corners (Haut only: Mobile_Renderer has none).
        // Room lighting on Haut (2026-11-20, A/B shots of four candidates rounds): a room-scale radius so a wall and floor
        // junction and a wall corner darken over a hand's breadth (the M3 0.6 / 0.3 / 0.25 only lined the furniture), part of
        // it on the sunlit surfaces too, interleaved gradient noise with 12 samples (blue noise left a grain in the corners at
        // the title's close eye level camera; a radius of 0.9 m and more left black blotches there).
        private const float SsaoIntensity = 1.6f;
        private const float SsaoRadius = 0.7f;
        private const float SsaoDirectLighting = 0.6f;

        [MenuItem("OutOfSight/Project Setup")]
        public static void Apply()
        {
            EnsureLayers();
            EnsureNavMeshAreas();
            EnsureAlwaysIncludedShaders();
            EnsureBootScene();
            EnsurePlayerSettings();
            EnsureSplashScreenDisabled();
            EnsureAndroidSettings();
            EnsureQualityLevels();
            EnsureRendererFeatures();
            EnsureAppIcon();
            AssetDatabase.SaveAssets();
            Debug.Log("[ProjectSetup] Layers, shaders, Boot scene, player settings and renderer features are in place.");
        }

        // ----- M3: renderer features -----

        private static void EnsureRendererFeatures()
        {
            // M7 walls pass (product owner, 2026-11-19): a flat colour no renderer's property block can override (URP applies a
            // renderer's block to an override material: the characters' prints showed their bodies through standing walls).
            Material silhouette = EnsureFlatMaterial(SilhouetteMaterialPath, SilhouetteColor, CullMode.Back);
            // Cones look (2026-11-20): the hidden part of a cone is the vision cone shader's blue hatching (its _XRay mode).
            Material cone = EnsureConeXRayMaterial(ConeMaterialPath, ConeXRayColor);
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
            Set(settings, "AOMethod", 1);          // interleaved gradient (smooth at close range)
            Set(settings, "Downsample", false);
            Set(settings, "AfterOpaque", false);   // applied in the lighting, not multiplied over the image
            Set(settings, "Source", 1);            // depth normals
            Set(settings, "NormalSamples", 1);     // medium
            Set(settings, "Intensity", SsaoIntensity);
            Set(settings, "DirectLightingStrength", SsaoDirectLighting);
            Set(settings, "Radius", SsaoRadius);
            Set(settings, "Samples", 0);           // high (12)
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

        /// <summary>The shader of <see cref="EnsureFlatMaterial"/> (Assets/Settings/XRayFlat.shader).</summary>
        public const string XRayFlatShaderName = "OutOfSight/XRay Flat";

        /// <summary>
        /// The x-ray silhouette's material asset: <see cref="XRayFlatShaderName"/>, one flat colour (_XRayColor) that no
        /// renderer's MaterialPropertyBlock sets, alpha blended (it ships because the renderer references it).
        /// </summary>
        private static Material EnsureFlatMaterial(string path, Color color, CullMode cull)
        {
            Shader shader = Shader.Find(XRayFlatShaderName);
            if (shader == null)
            {
                throw new InvalidOperationException("Shader not found in the editor: " + XRayFlatShaderName);
            }
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m == null)
            {
                m = new Material(shader) { name = Path.GetFileNameWithoutExtension(path) };
                AssetDatabase.CreateAsset(m, path);
            }
            m.shader = shader;
            m.shaderKeywords = new string[0];
            m.SetColor("_XRayColor", color);
            m.SetFloat("_Cull", (float)cull);
            m.renderQueue = (int)RenderQueue.Transparent;
            EditorUtility.SetDirty(m);
            return m;
        }

        /// <summary>
        /// Cones look (2026-11-20): the x-ray cone material asset, <see cref="VisionConeView.ConeShaderName"/> in its x-ray
        /// mode (a blue diagonal hatching that fades with distance, read from the fan mesh's own UVs; no property block on
        /// a cone, so nothing overrides its colour). The renderer references it, so the shader ships in the player with it.
        /// </summary>
        private static Material EnsureConeXRayMaterial(string path, Color color)
        {
            Shader shader = Shader.Find(VisionConeView.ConeShaderName);
            if (shader == null)
            {
                throw new InvalidOperationException("Shader not found in the editor: " + VisionConeView.ConeShaderName);
            }
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m == null)
            {
                m = new Material(shader) { name = Path.GetFileNameWithoutExtension(path) };
                AssetDatabase.CreateAsset(m, path);
            }
            m.shader = shader;
            m.shaderKeywords = new string[0];
            m.SetColor("_BaseColor", color);
            m.SetFloat("_XRay", 1f);
            m.renderQueue = (int)RenderQueue.Transparent;
            EditorUtility.SetDirty(m);
            return m;
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

        /// <summary>
        /// M5 (docs/CONTRACT_M5_v3.md 15.1): the NavMesh areas of the door leaves, Tuning.DoorAreaBase + leaf index, are named
        /// "Door0" and "Door1" in ProjectSettings/NavMeshAreas.asset (cost 1, as Walkable). Only the names change: a plan's
        /// area mask works by index.
        /// </summary>
        private static void EnsureNavMeshAreas()
        {
            UnityEngine.Object[] assets = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/NavMeshAreas.asset");
            if (assets.Length == 0)
            {
                throw new InvalidOperationException("NavMeshAreas.asset not found");
            }
            var settings = new SerializedObject(assets[0]);
            SerializedProperty areas = settings.FindProperty("areas");
            if (areas == null || !areas.isArray)
            {
                throw new InvalidOperationException("NavMeshAreas.asset has no areas array");
            }
            bool changed = false;
            for (int k = 0; k < Tuning.MaxLeavesPerLevel; k++)
            {
                int index = Tuning.DoorAreaBase + k;
                SerializedProperty area = areas.GetArrayElementAtIndex(index);
                SerializedProperty name = area.FindPropertyRelative("name");
                SerializedProperty cost = area.FindPropertyRelative("cost");
                string wanted = "Door" + k;
                if (name.stringValue != wanted)
                {
                    if (!string.IsNullOrEmpty(name.stringValue))
                    {
                        Debug.LogWarning($"[ProjectSetup] NavMesh area {index} was '{name.stringValue}', now '{wanted}'.");
                    }
                    name.stringValue = wanted;
                    changed = true;
                }
                if (cost != null && Mathf.Abs(cost.floatValue - 1f) > 1e-6f)
                {
                    cost.floatValue = 1f;
                    changed = true;
                }
            }
            if (changed)
            {
                settings.ApplyModifiedPropertiesWithoutUndo();
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
            // Cones look (2026-11-20): the vision cone shader is created from code (VisionConeView.ConeMaterial), so it is
            // kept here as well as by XRay_Cone.mat (a shader only named in code is stripped from the player).
            // LEVELNUM: the intro card's dim with the level number's holes (CardNumber) creates both its materials from code
            // (Assets/Settings/UiCardDim.shader, UiNumberMask.shader); UI/Default is a default Always Included shader, pinned.
            foreach (string name in new[] { PrimitiveKit.LitShaderName, PrimitiveKit.UnlitShaderName, VisionConeView.ConeShaderName,
                CardNumber.DimShaderName, CardNumber.MaskShaderName, "UI/Default" })
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
            if (PlayerSettings.companyName != "OutOfSight")
            {
                PlayerSettings.companyName = "OutOfSight";
            }
            // The product owner's request (2026-11-18): full screen by default (-screen-fullscreen 0 still opens a window).
            PlayerSettings.fullScreenMode = FullScreenMode.FullScreenWindow;
            PlayerSettings.defaultIsNativeResolution = true;
            PlayerSettings.defaultScreenWidth = 1600;
            PlayerSettings.defaultScreenHeight = 900;
            PlayerSettings.resizableWindow = true;
            PlayerSettings.runInBackground = true;
            PlayerSettings.visibleInBackground = true;
            PlayerSettings.SetManagedStrippingLevel(UnityEditor.Build.NamedBuildTarget.Standalone, ManagedStrippingLevel.Low);
        }

        /// <summary>No Unity splash screen or logo on startup, on Windows and Android (Unity 6 allows this on every plan).</summary>
        private static void EnsureSplashScreenDisabled()
        {
            PlayerSettings.SplashScreen.show = false;
            PlayerSettings.SplashScreen.showUnityLogo = false;
        }

        // ----- M7 android (docs/CONTRACT_M7.md 1.3 and 1.4) -----

        public const string AndroidPackage = "com.outofsight.game";
        public const string PcAssetPath = "Assets/Settings/PC_RPAsset.asset";
        public const string MobileAssetPath = "Assets/Settings/Mobile_RPAsset.asset";
        private const string QualitySettingsPath = "ProjectSettings/QualitySettings.asset";

        /// <summary>
        /// CONTRACT_M7 1.3: IL2CPP, ARM64, minimum API 26, the highest installed target API, landscape only (both
        /// sides), the package id, Vulkan then OpenGL ES 3, ASTC textures and the debug keystore. Sized for a compact
        /// APK: High managed stripping (Assets/link.xml leaves the game's own assemblies, and so the Newtonsoft
        /// reflection over the save and level types, whole), IL2CPP code for size, R8 for the Java side.
        /// </summary>
        private static void EnsureAndroidSettings()
        {
            var android = UnityEditor.Build.NamedBuildTarget.Android;
            if (PlayerSettings.GetApplicationIdentifier(android) != AndroidPackage)
            {
                PlayerSettings.SetApplicationIdentifier(android, AndroidPackage);
            }
            PlayerSettings.SetScriptingBackend(android, ScriptingImplementation.IL2CPP);
            // Compact APK: High stripping (Assets/link.xml keeps the game's assemblies and Newtonsoft whole, for
            // the reflection over the save and level types), IL2CPP code generated for size,
            // Master configuration (link time optimization) and R8 minification of the Java code.
            PlayerSettings.SetManagedStrippingLevel(android, ManagedStrippingLevel.High);
            PlayerSettings.SetIl2CppCodeGeneration(android, UnityEditor.Build.Il2CppCodeGeneration.OptimizeSize);
            PlayerSettings.SetIl2CppCompilerConfiguration(android, Il2CppCompilerConfiguration.Master);
            PlayerSettings.Android.minifyRelease = true;
            PlayerSettings.stripEngineCode = true;
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
            PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel26;
            PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevelAuto;
            PlayerSettings.Android.useCustomKeystore = false;
            TextureCompressionFormat[] formats = PlayerSettings.Android.textureCompressionFormats;
            if (formats == null || formats.Length != 1 || formats[0] != TextureCompressionFormat.ASTC)
            {
                PlayerSettings.Android.textureCompressionFormats = new[] { TextureCompressionFormat.ASTC };
            }
            if (EditorUserBuildSettings.androidBuildSubtarget != MobileTextureSubtarget.ASTC)
            {
                EditorUserBuildSettings.androidBuildSubtarget = MobileTextureSubtarget.ASTC;
            }
            GraphicsDeviceType[] apis = { GraphicsDeviceType.Vulkan, GraphicsDeviceType.OpenGLES3 };
            GraphicsDeviceType[] current = PlayerSettings.GetGraphicsAPIs(BuildTarget.Android);
            if (PlayerSettings.GetUseDefaultGraphicsAPIs(BuildTarget.Android) || current == null || current.Length != apis.Length
                || current[0] != apis[0] || current[1] != apis[1])
            {
                PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.Android, false);
                PlayerSettings.SetGraphicsAPIs(BuildTarget.Android, apis);
            }
            PlayerSettings.defaultInterfaceOrientation = UIOrientation.AutoRotation;
            PlayerSettings.allowedAutorotateToPortrait = false;
            PlayerSettings.allowedAutorotateToPortraitUpsideDown = false;
            PlayerSettings.allowedAutorotateToLandscapeLeft = true;
            PlayerSettings.allowedAutorotateToLandscapeRight = true;
        }

        /// <summary>
        /// CONTRACT_M7 1.4: QualitySettings holds exactly Bas, Moyen and Haut, in that order, on every platform (none
        /// excluded, so a PC player can choose Bas and an Android one Haut). Bas and Moyen use Mobile_RPAsset (render
        /// scale 1 and no soft shadows here; QualityTier lowers the scale to 0.75 at run time on Bas), Haut uses
        /// PC_RPAsset. Defaults: Moyen on Android and iOS, Haut everywhere else (the editor included), so the PC look
        /// and its frame times are those of M6. The M6 pair "Mobile" and "PC" becomes Moyen and Haut, and Bas is
        /// inserted as a copy of Moyen.
        /// </summary>
        private static void EnsureQualityLevels()
        {
            var pc = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(PcAssetPath);
            var mobile = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(MobileAssetPath);
            if (pc == null || mobile == null)
            {
                throw new InvalidOperationException("URP assets not found: " + PcAssetPath + " or " + MobileAssetPath);
            }
            var mobileSo = new SerializedObject(mobile);
            bool mobileChanged = false;
            SerializedProperty scale = mobileSo.FindProperty("m_RenderScale");
            if (scale != null && Mathf.Abs(scale.floatValue - Tuning.QualityMediumRenderScale) > 1e-4f)
            {
                scale.floatValue = Tuning.QualityMediumRenderScale;
                mobileChanged = true;
            }
            SerializedProperty soft = mobileSo.FindProperty("m_SoftShadowsSupported");
            if (soft != null && soft.boolValue)
            {
                soft.boolValue = false;
                mobileChanged = true;
            }
            if (mobileChanged)
            {
                mobileSo.ApplyModifiedPropertiesWithoutUndo();
                EditorUtility.SetDirty(mobile);
                AssetDatabase.SaveAssetIfDirty(mobile);
            }

            UnityEngine.Object[] assets = AssetDatabase.LoadAllAssetsAtPath(QualitySettingsPath);
            if (assets.Length == 0)
            {
                throw new InvalidOperationException("QualitySettings.asset not found");
            }
            var so = new SerializedObject(assets[0]);
            SerializedProperty levels = so.FindProperty("m_QualitySettings");
            Rename(levels, "Mobile", QualityTier.LevelMedium);
            Rename(levels, "PC", QualityTier.LevelHigh);
            if (LevelIndex(levels, QualityTier.LevelLow) < 0)
            {
                int medium = LevelIndex(levels, QualityTier.LevelMedium);
                if (medium < 0)
                {
                    throw new InvalidOperationException("QualitySettings has neither Bas nor Moyen (nor the M6 Mobile level) to copy");
                }
                levels.InsertArrayElementAtIndex(medium);
                levels.GetArrayElementAtIndex(medium).FindPropertyRelative("name").stringValue = QualityTier.LevelLow;
            }
            string[] wanted = { QualityTier.LevelLow, QualityTier.LevelMedium, QualityTier.LevelHigh };
            for (int i = 0; i < wanted.Length; i++)
            {
                int at = LevelIndex(levels, wanted[i]);
                if (at < 0)
                {
                    throw new InvalidOperationException("QualitySettings has no level " + wanted[i]);
                }
                if (at != i)
                {
                    levels.MoveArrayElement(at, i);
                }
            }
            while (levels.arraySize > wanted.Length)
            {
                Debug.LogWarning("[ProjectSetup] Extra quality level removed: "
                    + levels.GetArrayElementAtIndex(wanted.Length).FindPropertyRelative("name").stringValue);
                levels.DeleteArrayElementAtIndex(wanted.Length);
            }
            for (int i = 0; i < wanted.Length; i++)
            {
                SerializedProperty level = levels.GetArrayElementAtIndex(i);
                bool high = i == wanted.Length - 1;
                level.FindPropertyRelative("customRenderPipeline").objectReferenceValue = high ? (UnityEngine.Object)pc : mobile;
                level.FindPropertyRelative("excludedTargetPlatforms").arraySize = 0;
                if (!high)
                {
                    level.FindPropertyRelative("shadows").intValue = (int)UnityEngine.ShadowQuality.HardOnly;
                }
            }
            SerializedProperty defaults = so.FindProperty("m_PerPlatformDefaultQuality");
            for (int i = 0; defaults != null && i < defaults.arraySize; i++)
            {
                SerializedProperty entry = defaults.GetArrayElementAtIndex(i);
                string platform = entry.FindPropertyRelative("first").stringValue;
                entry.FindPropertyRelative("second").intValue = platform == "Android" || platform == "iPhone" ? 1 : 2;
            }
            so.FindProperty("m_CurrentQuality").intValue = 2;
            if (so.ApplyModifiedPropertiesWithoutUndo())
            {
                Debug.Log("[ProjectSetup] Quality levels set: Bas, Moyen, Haut.");
            }
        }

        // ----- M7 app icon: a red chair with a long shadow (docs/m7/app_icon.png) -----

        public const string AppIconPath = "Assets/Art/Icon/AppIcon_1024.png";
        public const string AppIconAdaptiveBackgroundPath = "Assets/Art/Icon/AppIcon_Adaptive_Background_1024.png";
        public const string AppIconAdaptiveForegroundPath = "Assets/Art/Icon/AppIcon_Adaptive_Foreground_1024.png";

        /// <summary>
        /// The app icon: the red chair, uncompressed and without mipmaps (PlayerSettings never samples
        /// icon mips), set as the default/Standalone (Windows) icon and as the Android legacy icon, plus
        /// the Android adaptive icon's background and foreground layers.
        /// </summary>
        private static void EnsureAppIcon()
        {
            Texture2D master = EnsureIconImporter(AppIconPath);
            Texture2D background = EnsureIconImporter(AppIconAdaptiveBackgroundPath);
            Texture2D foreground = EnsureIconImporter(AppIconAdaptiveForegroundPath);
            if (master == null || background == null || foreground == null)
            {
                throw new InvalidOperationException("App icon textures not found under Assets/Art/Icon");
            }

            SetIcons(BuildTargetGroup.Unknown, master);     // PlayerSettings default icon
            SetIcons(BuildTargetGroup.Standalone, master);  // Windows/Mac/Linux standalone icon
            SetIcons(BuildTargetGroup.Android, master);     // Android legacy icon (shown if adaptive is off)

            PlatformIconKind adaptive = AndroidPlatformIconKind.Adaptive;
            PlatformIcon[] adaptiveIcons = PlayerSettings.GetPlatformIcons(BuildTargetGroup.Android, adaptive);
            foreach (PlatformIcon icon in adaptiveIcons)
            {
                icon.SetTextures(new[] { background, foreground });
            }
            PlayerSettings.SetPlatformIcons(BuildTargetGroup.Android, adaptive, adaptiveIcons);
        }

        private static void SetIcons(BuildTargetGroup group, Texture2D icon)
        {
            int[] sizes = PlayerSettings.GetIconSizesForTargetGroup(group);
            if (sizes.Length == 0)
            {
                return;
            }
            var icons = new Texture2D[sizes.Length];
            for (int i = 0; i < icons.Length; i++)
            {
                icons[i] = icon;
            }
            PlayerSettings.SetIconsForTargetGroup(group, icons);
        }

        /// <summary>Uncompressed, no mipmaps, sRGB: a crisp source icon with no compression artefacts.</summary>
        private static Texture2D EnsureIconImporter(string path)
        {
            if (AssetImporter.GetAtPath(path) is TextureImporter importer)
            {
                bool changed = false;
                if (importer.textureType != TextureImporterType.Default)
                {
                    importer.textureType = TextureImporterType.Default;
                    changed = true;
                }
                if (importer.mipmapEnabled)
                {
                    importer.mipmapEnabled = false;
                    changed = true;
                }
                if (importer.textureCompression != TextureImporterCompression.Uncompressed)
                {
                    importer.textureCompression = TextureImporterCompression.Uncompressed;
                    changed = true;
                }
                if (!importer.alphaIsTransparency)
                {
                    importer.alphaIsTransparency = true;
                    changed = true;
                }
                if (!importer.sRGBTexture)
                {
                    importer.sRGBTexture = true;
                    changed = true;
                }
                if (changed)
                {
                    importer.SaveAndReimport();
                }
            }
            return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        }

        private static int LevelIndex(SerializedProperty levels, string name)
        {
            for (int i = 0; i < levels.arraySize; i++)
            {
                if (levels.GetArrayElementAtIndex(i).FindPropertyRelative("name").stringValue == name)
                {
                    return i;
                }
            }
            return -1;
        }

        private static void Rename(SerializedProperty levels, string from, string to)
        {
            int at = LevelIndex(levels, from);
            if (at >= 0 && LevelIndex(levels, to) < 0)
            {
                levels.GetArrayElementAtIndex(at).FindPropertyRelative("name").stringValue = to;
            }
        }
    }
}
