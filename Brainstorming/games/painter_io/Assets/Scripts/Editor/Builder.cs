using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
using PainterIO.Runtime;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace PainterIO.Editor
{
    /// <summary>
    /// Command line entry points and project settings (docs/CONTRACT.md 17 and 23.3).
    /// In batch mode every entry point ends in EditorApplication.Exit with an explicit code: a failed build otherwise exits
    /// 0, and BuildPlayer can report Succeeded without an artifact, so success is also confirmed against the file system.
    /// Output folder: "-buildOut &lt;dir&gt;" overrides it (BuildWindows writes &lt;dir&gt;/PainterIO.exe, BuildAndroid
    /// &lt;dir&gt;/PainterIO.apk, BuildAll &lt;dir&gt;/Windows and &lt;dir&gt;/Android); defaults Build/Windows and Build/Android.
    /// "-development" makes a Development Build.
    /// </summary>
    public static class Builder
    {
        public const string ScenePath = "Assets/Scenes/Main.unity";
        public const string GameObjectName = "Game";
        public const string DefaultWindowsDir = "Build/Windows";
        public const string DefaultAndroidDir = "Build/Android";
        public const string WindowsExeName = "PainterIO.exe";
        public const string ApkName = "PainterIO.apk";
        /// <summary>
        /// Wave D: the final name, shown as the Android launcher label and the Windows window title. The exe, the APK,
        /// the namespaces and the package id keep "PainterIO". Changing it moved the Windows PlayerPrefs key from
        /// HKCU\Software\PainterIO\Painter IO to HKCU\Software\PainterIO\Painter.io (saves restart once).
        /// </summary>
        public const string ProductName = "Painter.io";
        public const string CompanyName = "PainterIO";
        /// <summary>Wave D F1: app icons made by tools/logo/make_logo.py (icon_&lt;size&gt;.png, android_*.png).</summary>
        public const string IconFolder = "Assets/Art/Icon";
        /// <summary>Wave D F1: the logo sprites (logo_liquid, logo_fire, logo_electric, logo_mask) loaded by MenuScreen.</summary>
        public const string LogoFolder = "Assets/Resources/UI";
        public const string AndroidPackage = "com.painterio.game";
        public const int AndroidMinSdk = 25;
        public const string FieldLayerName = "LiquidField";
        public const string PcAssetPath = "Assets/Settings/PC_RPAsset.asset";
        public const string MobileAssetPath = "Assets/Settings/Mobile_RPAsset.asset";
        public const string VibratePermission = "android.permission.VIBRATE";

        private const string LogTag = "[Builder] ";
        private const string QualitySettingsPath = "ProjectSettings/QualitySettings.asset";
        private const string PcQualityLevel = "PC";
        private const string MobileQualityLevel = "Mobile";

        // Set by VibratePermissionCheck (compiled only while the editor's active target is Android).
        internal static string s_VibrateManifestChecked;

        // ---------------------------------------------------------------------------------------------------------------
        // Entry points
        // ---------------------------------------------------------------------------------------------------------------

        /// <summary>
        /// Reached only once every script compiled: applies the project settings, writes Scenes/Main.unity, runs ShaderCheck
        /// on Resources/Shaders and on the Shader Graph templates. Exit code 0 when all of it is green, 1 otherwise.
        /// </summary>
        [MenuItem("PainterIO/Setup And Compile")]
        public static void SetupAndCompile()
        {
            int code = 1;
            try
            {
                ApplyProjectSettings();
                EnsureScene();
                AssetDatabase.SaveAssets();
                bool shaders = ShaderCheck.Run();
                bool templates = ShaderCheck.RunTemplates();
                code = shaders && templates ? 0 : 1;
                Debug.Log(LogTag + (code == 0 ? "SetupAndCompile PASS" : "SetupAndCompile FAIL (ShaderCheck)"));
            }
            catch (Exception e)
            {
                Debug.LogError(LogTag + "SetupAndCompile threw: " + e);
                code = 1;
            }
            ExitIfBatch(code);
        }

        /// <summary>Windows 64 player (Mono) into &lt;buildOut or Build/Windows&gt;/PainterIO.exe.</summary>
        [MenuItem("PainterIO/Build Windows")]
        public static void BuildWindows()
        {
            ExitIfBatch(BuildWindowsInto(ArgOr("-buildOut", DefaultWindowsDir)));
        }

        /// <summary>
        /// Android APK (IL2CPP ARM64, minSdk 25, portrait, Vulkan then GLES3) into &lt;buildOut or Build/Android&gt;/PainterIO.apk.
        /// Records the active build target and switches back to it afterwards, on success and on failure. Fails when the APK
        /// manifest lacks android.permission.VIBRATE.
        /// </summary>
        [MenuItem("PainterIO/Build Android")]
        public static void BuildAndroid()
        {
            ExitIfBatch(BuildAndroidInto(ArgOr("-buildOut", DefaultAndroidDir)));
        }

        /// <summary>Windows then Android (Android last, it is slow and switches the target).</summary>
        [MenuItem("PainterIO/Build All")]
        public static void BuildAll()
        {
            string root = ArgOr("-buildOut", null);
            string windows = root == null ? DefaultWindowsDir : Path.Combine(root, "Windows");
            string android = root == null ? DefaultAndroidDir : Path.Combine(root, "Android");
            int code = BuildWindowsInto(windows);
            if (code == 0)
            {
                code = BuildAndroidInto(android);
            }
            ExitIfBatch(code);
        }

        // ---------------------------------------------------------------------------------------------------------------
        // Builds
        // ---------------------------------------------------------------------------------------------------------------

        private static int BuildWindowsInto(string dir)
        {
            string output = Path.Combine(dir, WindowsExeName).Replace('\\', '/');
            int code = Build(BuildTarget.StandaloneWindows64, BuildTargetGroup.Standalone, output);
            if (code == 0)
            {
                string data = Path.Combine(dir, Path.GetFileNameWithoutExtension(WindowsExeName) + "_Data");
                if (!Directory.Exists(data) || !File.Exists(Path.Combine(dir, "UnityPlayer.dll")))
                {
                    Debug.LogError(LogTag + "Windows build incomplete: " + data + " or UnityPlayer.dll missing");
                    code = 1;
                }
            }
            return code;
        }

        private static int BuildAndroidInto(string dir)
        {
            string output = Path.Combine(dir, ApkName).Replace('\\', '/');
            BuildTarget previous = EditorUserBuildSettings.activeBuildTarget;
            BuildTargetGroup previousGroup = BuildPipeline.GetBuildTargetGroup(previous);
            // An editor started with -buildTarget Android (so that the UNITY_ANDROID manifest callback is compiled) goes back
            // to Windows, the project's working target, so the next editor run of any agent does not open on Android.
            if (previous == BuildTarget.Android)
            {
                previous = BuildTarget.StandaloneWindows64;
                previousGroup = BuildTargetGroup.Standalone;
            }
            int code = 1;
            try
            {
                EditorUserBuildSettings.buildAppBundle = false;
                EditorUserBuildSettings.exportAsGoogleAndroidProject = false;
                s_VibrateManifestChecked = null;
                code = Build(BuildTarget.Android, BuildTargetGroup.Android, output);
                if (code == 0)
                {
                    Debug.Log(LogTag + (s_VibrateManifestChecked != null
                        ? "VIBRATE manifest callback ran on " + s_VibrateManifestChecked
                        : "VIBRATE manifest callback did not run (editor not started on Android); checking the APK only"));
                    if (!ApkHasPermission(output, VibratePermission, out string why))
                    {
                        Debug.LogError(LogTag + "APK manifest lacks " + VibratePermission + ": " + why);
                        code = 1;
                    }
                    else
                    {
                        long bytes = new FileInfo(output).Length;
                        Debug.Log($"{LogTag}APK has {VibratePermission}; size {bytes / (1024.0 * 1024.0):0.0} MB");
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogError(LogTag + "BuildAndroid threw: " + e);
                code = 1;
            }
            finally
            {
                try
                {
                    if (EditorUserBuildSettings.activeBuildTarget != previous)
                    {
                        bool switched = EditorUserBuildSettings.SwitchActiveBuildTarget(previousGroup, previous);
                        Debug.Log($"{LogTag}Build target restored to {previous}: {switched}");
                        if (!switched)
                        {
                            code = 1;
                        }
                    }
                }
                catch (Exception e)
                {
                    Debug.LogError(LogTag + "Build target restore threw: " + e);
                    code = 1;
                }
            }
            return code;
        }

        private static int Build(BuildTarget target, BuildTargetGroup group, string output)
        {
            var shaderErrors = new List<string>();
            Application.LogCallback capture = (message, stack, type) =>
            {
                if ((type == LogType.Error || type == LogType.Exception) && message != null
                    && message.IndexOf("Shader error", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    lock (shaderErrors)
                    {
                        shaderErrors.Add(message);
                    }
                }
            };
            try
            {
                string folder = Path.GetDirectoryName(output);
                if (!string.IsNullOrEmpty(folder))
                {
                    Directory.CreateDirectory(folder);
                }
                if (File.Exists(output))
                {
                    File.Delete(output);   // so the existence check below proves this build wrote it
                }
                ApplyProjectSettings();
                EnsureScene();
                AssetDatabase.SaveAssets();

                bool development = HasFlag("-development");
                var options = new BuildPlayerOptions
                {
                    scenes = new[] { ScenePath },
                    locationPathName = output,
                    target = target,
                    targetGroup = group,
                    options = development ? BuildOptions.Development : BuildOptions.None,
                };
                Application.logMessageReceivedThreaded += capture;
                BuildReport report;
                try
                {
                    report = BuildPipeline.BuildPlayer(options);
                }
                finally
                {
                    Application.logMessageReceivedThreaded -= capture;
                }
                BuildSummary summary = report.summary;
                bool produced = File.Exists(output) && new FileInfo(output).Length > 0;
                if (summary.result != BuildResult.Succeeded || !produced)
                {
                    Debug.LogError($"{LogTag}Build {target} failed: result {summary.result}, {summary.totalErrors} error(s), artifact present {produced} ({output})");
                    return 1;
                }
                if (shaderErrors.Count > 0)
                {
                    Debug.LogError($"{LogTag}Build {target} logged {shaderErrors.Count} shader error(s), first: {shaderErrors[0]}");
                    return 1;
                }
                Debug.Log($"{LogTag}Built {target} -> {output} ({summary.totalSize / (1024 * 1024)} MB reported, {summary.totalTime.TotalSeconds:0} s)");
                return 0;
            }
            catch (Exception e)
            {
                Debug.LogError(LogTag + "Build " + target + " threw: " + e);
                return 1;
            }
        }

        /// <summary>True when the binary AndroidManifest.xml of the APK contains the permission string (UTF-16 or UTF-8 pool).</summary>
        private static bool ApkHasPermission(string apk, string permission, out string why)
        {
            why = "";
            try
            {
                using (var file = File.OpenRead(apk))
                using (var zip = new ZipArchive(file, ZipArchiveMode.Read))
                {
                    ZipArchiveEntry entry = zip.GetEntry("AndroidManifest.xml");
                    if (entry == null)
                    {
                        why = "no AndroidManifest.xml in the APK";
                        return false;
                    }
                    byte[] bytes;
                    using (Stream s = entry.Open())
                    using (var memory = new MemoryStream())
                    {
                        s.CopyTo(memory);
                        bytes = memory.ToArray();
                    }
                    if (IndexOf(bytes, Encoding.Unicode.GetBytes(permission)) >= 0 || IndexOf(bytes, Encoding.UTF8.GetBytes(permission)) >= 0)
                    {
                        return true;
                    }
                    why = "permission string absent from the manifest";
                    return false;
                }
            }
            catch (Exception e)
            {
                why = "could not read the APK: " + e.Message;
                return false;
            }
        }

        private static int IndexOf(byte[] haystack, byte[] needle)
        {
            for (int i = 0; i + needle.Length <= haystack.Length; i++)
            {
                int k = 0;
                while (k < needle.Length && haystack[i + k] == needle[k])
                {
                    k++;
                }
                if (k == needle.Length)
                {
                    return i;
                }
            }
            return -1;
        }

        // ---------------------------------------------------------------------------------------------------------------
        // Project settings (idempotent)
        // ---------------------------------------------------------------------------------------------------------------

        /// <summary>Layer 31, player settings, quality levels and URP asset settings of contract 17.</summary>
        public static void ApplyProjectSettings()
        {
            EnsureFieldLayer();
            EnsureArtImports();
            EnsurePlayerSettings();
            EnsureIcons();
            EnsureRenderPipelineAssets();
            EnsureQualityLevels();
        }

        // ---------------------------------------------------------------------------------------------------------------
        // Logo and icons (wave D F1)
        // ---------------------------------------------------------------------------------------------------------------

        /// <summary>
        /// Re-imports a logo or icon texture whose importer does not match ArtTextureImport yet (an asset imported before
        /// the postprocessor existed, or by an editor of another agent), so every build ships the intended settings.
        /// </summary>
        private static void EnsureArtImports()
        {
            foreach (string folder in new[] { LogoFolder, IconFolder })
            {
                if (!AssetDatabase.IsValidFolder(folder))
                {
                    continue;
                }
                foreach (string guid in AssetDatabase.FindAssets("t:Texture2D", new[] { folder }))
                {
                    string path = AssetDatabase.GUIDToAssetPath(guid);
                    if (AssetImporter.GetAtPath(path) is TextureImporter importer && !ArtTextureImport.Matches(path, importer))
                    {
                        ArtTextureImport.Apply(path, importer);
                        importer.SaveAndReimport();
                        Debug.Log(LogTag + "Re-imported " + path + " with the logo / icon settings");
                    }
                }
            }
        }

        private static Texture2D LoadIcon(string file)
        {
            string path = IconFolder + "/" + file;
            var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
            if (tex == null)
            {
                Debug.LogWarning(LogTag + "Icon missing: " + path + " (run tools/logo/make_logo.py)");
            }
            return tex;
        }

        /// <summary>The generated Windows icon closest to a slot size (icon_16 ... icon_1024).</summary>
        internal static int IconSizeFor(int slot)
        {
            int[] made = { 16, 32, 48, 64, 128, 256, 512, 1024 };
            foreach (int size in made)
            {
                if (size >= slot)
                {
                    return size;
                }
            }
            return made[made.Length - 1];
        }

        /// <summary>
        /// Default icon, Windows player icon slots and the Android icon kinds (adaptive background + foreground layers,
        /// round and legacy), written only when they differ from what ProjectSettings already holds. The Android kinds
        /// come from PlayerSettings.GetSupportedIconKinds, so the editor assembly needs no Android module reference.
        /// </summary>
        private static void EnsureIcons()
        {
            Texture2D master = LoadIcon("icon_1024.png");
            if (master == null)
            {
                return;
            }
            Texture2D[] current = PlayerSettings.GetIcons(NamedBuildTarget.Unknown, IconKind.Any);
            if (current == null || current.Length != 1 || current[0] != master)
            {
                PlayerSettings.SetIcons(NamedBuildTarget.Unknown, new[] { master }, IconKind.Any);
                Debug.Log(LogTag + "Default icon set");
            }

            int[] sizes = PlayerSettings.GetIconSizes(NamedBuildTarget.Standalone, IconKind.Application);
            if (sizes != null && sizes.Length > 0)
            {
                var wanted = new Texture2D[sizes.Length];
                for (int i = 0; i < sizes.Length; i++)
                {
                    wanted[i] = LoadIcon("icon_" + IconSizeFor(sizes[i]) + ".png");
                }
                Texture2D[] have = PlayerSettings.GetIcons(NamedBuildTarget.Standalone, IconKind.Application);
                if (!SameTextures(have, wanted))
                {
                    PlayerSettings.SetIcons(NamedBuildTarget.Standalone, wanted, IconKind.Application);
                    Debug.Log(LogTag + "Windows icons set (" + sizes.Length + " slots)");
                }
            }

            Texture2D adaptiveBg = LoadIcon("android_adaptive_bg.png");
            Texture2D adaptiveFg = LoadIcon("android_adaptive_fg.png");
            Texture2D legacy = LoadIcon("android_legacy.png");
            Texture2D round = LoadIcon("android_round.png");
            PlatformIconKind[] kinds = PlayerSettings.GetSupportedIconKinds(NamedBuildTarget.Android);
            if (kinds == null || kinds.Length == 0)
            {
                Debug.LogWarning(LogTag + "No Android icon kinds (Android module missing?): Android icons not set");
                return;
            }
            foreach (PlatformIconKind kind in kinds)
            {
                PlatformIcon[] icons = PlayerSettings.GetPlatformIcons(NamedBuildTarget.Android, kind);
                if (icons == null || icons.Length == 0)
                {
                    continue;
                }
                string name = kind.ToString();
                bool changed = false;
                foreach (PlatformIcon icon in icons)
                {
                    Texture2D[] want;
                    if (icon.maxLayerCount >= 2)
                    {
                        want = new[] { adaptiveBg, adaptiveFg };   // layer 0 background, layer 1 foreground
                    }
                    else if (name.IndexOf("Round", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        want = new[] { round };
                    }
                    else
                    {
                        want = new[] { legacy };
                    }
                    if (Array.IndexOf(want, null) >= 0)
                    {
                        continue;
                    }
                    if (!SameTextures(icon.GetTextures(), want))
                    {
                        icon.SetTextures(want);
                        changed = true;
                    }
                }
                if (changed)
                {
                    PlayerSettings.SetPlatformIcons(NamedBuildTarget.Android, kind, icons);
                    Debug.Log(LogTag + "Android icons set: " + name + " (" + icons.Length + " sizes)");
                }
            }
        }

        private static bool SameTextures(Texture2D[] a, Texture2D[] b)
        {
            if (a == null || b == null || a.Length != b.Length)
            {
                return false;
            }
            for (int i = 0; i < a.Length; i++)
            {
                if (a[i] != b[i])
                {
                    return false;
                }
            }
            return true;
        }

        private static void EnsureFieldLayer()
        {
            UnityEngine.Object[] assets = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/TagManager.asset");
            if (assets.Length == 0)
            {
                throw new InvalidOperationException("ProjectSettings/TagManager.asset not found");
            }
            var tagManager = new SerializedObject(assets[0]);
            SerializedProperty layers = tagManager.FindProperty("layers");
            SerializedProperty slot = layers.GetArrayElementAtIndex(LiquidLayers.Field);
            if (slot.stringValue != FieldLayerName)
            {
                if (!string.IsNullOrEmpty(slot.stringValue))
                {
                    Debug.LogWarning($"{LogTag}Layer {LiquidLayers.Field} was '{slot.stringValue}', now '{FieldLayerName}'");
                }
                slot.stringValue = FieldLayerName;
                tagManager.ApplyModifiedPropertiesWithoutUndo();
            }
        }

        private static void EnsurePlayerSettings()
        {
            if (PlayerSettings.productName != ProductName)
            {
                PlayerSettings.productName = ProductName;
            }
            if (PlayerSettings.companyName != CompanyName)
            {
                PlayerSettings.companyName = CompanyName;
            }
            if (PlayerSettings.colorSpace != ColorSpace.Linear)
            {
                PlayerSettings.colorSpace = ColorSpace.Linear;
            }

            // Portrait everywhere.
            PlayerSettings.defaultInterfaceOrientation = UIOrientation.Portrait;
            PlayerSettings.allowedAutorotateToPortrait = true;
            PlayerSettings.allowedAutorotateToPortraitUpsideDown = false;
            PlayerSettings.allowedAutorotateToLandscapeLeft = false;
            PlayerSettings.allowedAutorotateToLandscapeRight = false;

            // No splash (allowed on every plan since Unity 6).
            PlayerSettings.SplashScreen.show = false;
            PlayerSettings.SplashScreen.showUnityLogo = false;

            // Windows: windowed portrait 540 x 960, resizable. Wave C (robust-09): the player no longer runs in the
            // background, so a minimized or unfocused window stops simulating and rendering the attract match (a round
            // auto-pauses on focus loss in GameDirector); PlayerProbe, DevShot and RenderLab turn
            // Application.runInBackground on at runtime, so the verify runs and the tools keep running unfocused.
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.defaultIsNativeResolution = false;
            PlayerSettings.defaultScreenWidth = 540;
            PlayerSettings.defaultScreenHeight = 960;
            PlayerSettings.resizableWindow = true;
            PlayerSettings.runInBackground = false;
            PlayerSettings.visibleInBackground = true;
            PlayerSettings.SetScriptingBackend(NamedBuildTarget.Standalone, ScriptingImplementation.Mono2x);

            // Android: package, IL2CPP ARM64, minSdk 25, Vulkan then GLES3.
            NamedBuildTarget android = NamedBuildTarget.Android;
            if (PlayerSettings.GetApplicationIdentifier(android) != AndroidPackage)
            {
                PlayerSettings.SetApplicationIdentifier(android, AndroidPackage);
            }
            PlayerSettings.SetScriptingBackend(android, ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
            PlayerSettings.Android.minSdkVersion = (AndroidSdkVersions)AndroidMinSdk;
            GraphicsDeviceType[] apis = { GraphicsDeviceType.Vulkan, GraphicsDeviceType.OpenGLES3 };
            GraphicsDeviceType[] current = PlayerSettings.GetGraphicsAPIs(BuildTarget.Android);
            if (PlayerSettings.GetUseDefaultGraphicsAPIs(BuildTarget.Android) || current == null || current.Length != apis.Length
                || current[0] != apis[0] || current[1] != apis[1])
            {
                PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.Android, false);
                PlayerSettings.SetGraphicsAPIs(BuildTarget.Android, apis);
            }
            // Wave C (perf-09): no forced offscreen buffer plus full-resolution blit every frame (Auto lets the player
            // render straight to the backbuffer when it can), and Swappy frame pacing for an even 60 fps cadence.
            if (PlayerSettings.Android.blitType != AndroidBlitType.Auto)
            {
                PlayerSettings.Android.blitType = AndroidBlitType.Auto;
            }
            if (!PlayerSettings.Android.optimizedFramePacing)
            {
                PlayerSettings.Android.optimizedFramePacing = true;
            }

            // The Input System package is the only input backend (InputSystemUIInputModule, SteeringInput).
            UnityEngine.Object[] player = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/ProjectSettings.asset");
            if (player.Length > 0)
            {
                var so = new SerializedObject(player[0]);
                SerializedProperty handler = so.FindProperty("activeInputHandler");
                if (handler != null && handler.intValue != 1)
                {
                    Debug.LogWarning(LogTag + "activeInputHandler was " + handler.intValue + ", now 1 (Input System package); restart the editor");
                    handler.intValue = 1;
                    so.ApplyModifiedPropertiesWithoutUndo();
                }
            }
        }

        /// <summary>
        /// URP assets: no depth or opaque texture on PC, no HDR on Mobile, URP shadows off and additional lights off on both
        /// (all lighting is custom, contract 12.1), Mobile render scale 1 on disk (in the player, GameDirector caps it on
        /// screens over 1920 px and LiquidRenderer applies the tier's render height cap, QualityTier.RenderScaleFor).
        /// </summary>
        private static void EnsureRenderPipelineAssets()
        {
            var pc = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(PcAssetPath);
            var mobile = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(MobileAssetPath);
            if (pc == null || mobile == null)
            {
                throw new InvalidOperationException("URP assets not found: " + PcAssetPath + " or " + MobileAssetPath);
            }
            EditRpAsset(pc, new Dictionary<string, object>
            {
                { "m_RequireDepthTexture", false },
                { "m_RequireOpaqueTexture", false },
                { "m_MainLightShadowsSupported", false },
                { "m_AdditionalLightShadowsSupported", false },
                { "m_AdditionalLightsRenderingMode", 0 },
            });
            EditRpAsset(mobile, new Dictionary<string, object>
            {
                { "m_RequireDepthTexture", false },
                { "m_RequireOpaqueTexture", false },
                { "m_SupportsHDR", false },
                { "m_MainLightShadowsSupported", false },
                { "m_AdditionalLightShadowsSupported", false },
                { "m_AdditionalLightsRenderingMode", 0 },
                { "m_RenderScale", 1f },
            });
        }

        private static void EditRpAsset(UniversalRenderPipelineAsset asset, Dictionary<string, object> values)
        {
            var so = new SerializedObject(asset);
            bool changed = false;
            foreach (KeyValuePair<string, object> pair in values)
            {
                SerializedProperty p = so.FindProperty(pair.Key);
                if (p == null)
                {
                    Debug.LogWarning($"{LogTag}{asset.name}: no serialized field {pair.Key}");
                    continue;
                }
                switch (pair.Value)
                {
                    case bool b when p.propertyType == SerializedPropertyType.Boolean:
                        if (p.boolValue != b) { p.boolValue = b; changed = true; }
                        break;
                    case int i when p.propertyType == SerializedPropertyType.Enum || p.propertyType == SerializedPropertyType.Integer:
                        if (p.intValue != i) { p.intValue = i; changed = true; }
                        break;
                    case float f when p.propertyType == SerializedPropertyType.Float:
                        if (Mathf.Abs(p.floatValue - f) > 1e-5f) { p.floatValue = f; changed = true; }
                        break;
                    default:
                        Debug.LogWarning($"{LogTag}{asset.name}: {pair.Key} has type {p.propertyType}, not set");
                        break;
                }
            }
            if (changed)
            {
                so.ApplyModifiedPropertiesWithoutUndo();
                EditorUtility.SetDirty(asset);
                AssetDatabase.SaveAssetIfDirty(asset);
                Debug.Log(LogTag + "URP asset settings applied to " + asset.name);
            }
        }

        /// <summary>
        /// Quality levels: "PC" uses PC_RPAsset and is the Standalone default, "Mobile" uses Mobile_RPAsset and is the Android
        /// default; each is excluded from the other platform. GraphicsSettings keeps PC_RPAsset as the default pipeline.
        /// </summary>
        private static void EnsureQualityLevels()
        {
            var pc = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(PcAssetPath);
            var mobile = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(MobileAssetPath);
            UnityEngine.Object[] assets = AssetDatabase.LoadAllAssetsAtPath(QualitySettingsPath);
            if (assets.Length == 0)
            {
                throw new InvalidOperationException(QualitySettingsPath + " not found");
            }
            var so = new SerializedObject(assets[0]);
            SerializedProperty levels = so.FindProperty("m_QualitySettings");
            int pcIndex = -1;
            int mobileIndex = -1;
            bool changed = false;
            for (int i = 0; i < levels.arraySize; i++)
            {
                SerializedProperty level = levels.GetArrayElementAtIndex(i);
                string name = level.FindPropertyRelative("name").stringValue;
                SerializedProperty pipeline = level.FindPropertyRelative("customRenderPipeline");
                if (name == PcQualityLevel)
                {
                    pcIndex = i;
                    if (pipeline.objectReferenceValue != pc) { pipeline.objectReferenceValue = pc; changed = true; }
                }
                else if (name == MobileQualityLevel)
                {
                    mobileIndex = i;
                    if (pipeline.objectReferenceValue != mobile) { pipeline.objectReferenceValue = mobile; changed = true; }
                }
            }
            if (pcIndex < 0 || mobileIndex < 0)
            {
                throw new InvalidOperationException("QualitySettings needs the levels 'PC' and 'Mobile' (URP template)");
            }
            SerializedProperty defaults = so.FindProperty("m_PerPlatformDefaultQuality");
            if (defaults != null)
            {
                for (int i = 0; i < defaults.arraySize; i++)
                {
                    SerializedProperty entry = defaults.GetArrayElementAtIndex(i);
                    string platform = entry.FindPropertyRelative("first").stringValue;
                    SerializedProperty value = entry.FindPropertyRelative("second");
                    int wanted = platform == "Android" ? mobileIndex : platform == "Standalone" ? pcIndex : value.intValue;
                    if (value.intValue != wanted) { value.intValue = wanted; changed = true; }
                }
            }
            if (changed)
            {
                so.ApplyModifiedPropertiesWithoutUndo();
                Debug.Log(LogTag + "Quality levels updated");
            }
            if (GraphicsSettings.defaultRenderPipeline != pc)
            {
                GraphicsSettings.defaultRenderPipeline = pc;
            }
        }

        // ---------------------------------------------------------------------------------------------------------------
        // Scene
        // ---------------------------------------------------------------------------------------------------------------

        /// <summary>
        /// Scenes/Main.unity holds exactly one root GameObject "Game" with GameDirector (cameras and everything else are
        /// created at runtime). Rewritten only when missing or different; always the only build scene.
        /// </summary>
        public static void EnsureScene()
        {
            if (!SceneIsValid())
            {
                Directory.CreateDirectory(Path.GetDirectoryName(ScenePath));
                Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                var game = new GameObject(GameObjectName);
                game.AddComponent<GameDirector>();
                if (!EditorSceneManager.SaveScene(scene, ScenePath))
                {
                    throw new InvalidOperationException("Could not save " + ScenePath);
                }
                Debug.Log(LogTag + "Wrote " + ScenePath);
            }
            EditorBuildSettingsScene[] current = EditorBuildSettings.scenes;
            if (current.Length != 1 || current[0].path != ScenePath || !current[0].enabled)
            {
                EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            }
        }

        private static bool SceneIsValid()
        {
            if (!File.Exists(ScenePath))
            {
                return false;
            }
            Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            GameObject[] roots = scene.GetRootGameObjects();
            if (roots.Length != 1 || roots[0].name != GameObjectName || roots[0].transform.childCount != 0)
            {
                return false;
            }
            Component[] components = roots[0].GetComponents<Component>();
            // Transform + GameDirector, and no missing script (a null component).
            return components.Length == 2 && components[0] is Transform && components[1] is GameDirector;
        }

        // ---------------------------------------------------------------------------------------------------------------
        // Helpers
        // ---------------------------------------------------------------------------------------------------------------

        internal static bool HasFlag(string flag)
        {
            return Array.IndexOf(Environment.GetCommandLineArgs(), flag) >= 0;
        }

        internal static string ArgOr(string flag, string fallback)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == flag)
                {
                    return args[i + 1];
                }
            }
            return fallback;
        }

        private static void ExitIfBatch(int code)
        {
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }
    }

    /// <summary>
    /// Wave D F1: import settings of the generated logo and icon textures. The logos (Resources/UI/logo_*.png) are
    /// sprites with mipmaps (they are drawn at a third of their size on a 540 px phone) and high quality compression;
    /// the icons (Art/Icon/*.png) stay uncompressed, without mipmaps or power-of-two scaling. Both: sRGB, alpha is
    /// transparency, clamp.
    /// </summary>
    internal sealed class ArtTextureImport : AssetPostprocessor
    {
        public override uint GetVersion()
        {
            return 1;
        }

        private void OnPreprocessTexture()
        {
            if (assetImporter is TextureImporter importer)
            {
                Apply(assetPath, importer);
            }
        }

        internal static bool IsLogo(string path)
        {
            return path.StartsWith(Builder.LogoFolder + "/logo_", StringComparison.Ordinal)
                && path.EndsWith(".png", StringComparison.OrdinalIgnoreCase);
        }

        internal static bool IsIcon(string path)
        {
            return path.StartsWith(Builder.IconFolder + "/", StringComparison.Ordinal)
                && path.EndsWith(".png", StringComparison.OrdinalIgnoreCase);
        }

        internal static void Apply(string path, TextureImporter ti)
        {
            if (IsLogo(path))
            {
                ti.textureType = TextureImporterType.Sprite;
                ti.spriteImportMode = SpriteImportMode.Single;
                ti.mipmapEnabled = true;
                ti.mipmapFilter = TextureImporterMipFilter.KaiserFilter;
                ti.textureCompression = TextureImporterCompression.CompressedHQ;
                ti.filterMode = FilterMode.Trilinear;
            }
            else if (IsIcon(path))
            {
                ti.textureType = TextureImporterType.Default;
                ti.mipmapEnabled = false;
                ti.npotScale = TextureImporterNPOTScale.None;
                ti.textureCompression = TextureImporterCompression.Uncompressed;
                ti.filterMode = FilterMode.Bilinear;
            }
            else
            {
                return;
            }
            ti.sRGBTexture = true;
            ti.alphaSource = TextureImporterAlphaSource.FromInput;
            ti.alphaIsTransparency = true;
            ti.wrapMode = TextureWrapMode.Clamp;
            ti.isReadable = false;
            ti.maxTextureSize = 2048;
        }

        internal static bool Matches(string path, TextureImporter ti)
        {
            bool logo = IsLogo(path);
            if (!logo && !IsIcon(path))
            {
                return true;
            }
            bool common = ti.sRGBTexture && ti.alphaIsTransparency && ti.wrapMode == TextureWrapMode.Clamp && !ti.isReadable
                && ti.alphaSource == TextureImporterAlphaSource.FromInput && ti.maxTextureSize == 2048;
            if (logo)
            {
                return common && ti.textureType == TextureImporterType.Sprite && ti.mipmapEnabled
                    && ti.textureCompression == TextureImporterCompression.CompressedHQ;
            }
            return common && ti.textureType == TextureImporterType.Default && !ti.mipmapEnabled
                && ti.npotScale == TextureImporterNPOTScale.None && ti.textureCompression == TextureImporterCompression.Uncompressed;
        }
    }

#if UNITY_ANDROID
    /// <summary>
    /// Contract 17 and 16: the generated unityLibrary manifest must declare android.permission.VIBRATE (Haptics). Inserts it
    /// when missing and logs it. Compiled only while the editor's active target is Android: start the editor with
    /// -buildTarget Android for BuildAndroid to run it. BuildAndroid also checks the final APK manifest either way.
    /// </summary>
    internal sealed class VibratePermissionCheck : UnityEditor.Android.IPostGenerateGradleAndroidProject
    {
        public int callbackOrder => 0;

        public void OnPostGenerateGradleAndroidProject(string path)
        {
            string manifest = Path.Combine(path, "src", "main", "AndroidManifest.xml");
            if (!File.Exists(manifest))
            {
                Debug.LogError("[Builder] VIBRATE check: no manifest at " + manifest);
                return;
            }
            string text = File.ReadAllText(manifest);
            if (text.Contains(Builder.VibratePermission))
            {
                Debug.Log("[Builder] VIBRATE permission present in " + manifest);
            }
            else
            {
                string line = "    <uses-permission android:name=\"" + Builder.VibratePermission + "\" />\n";
                int at = text.IndexOf("<application", StringComparison.Ordinal);
                if (at < 0)
                {
                    at = text.IndexOf("</manifest>", StringComparison.Ordinal);
                }
                if (at < 0)
                {
                    Debug.LogError("[Builder] VIBRATE check: no <application> or </manifest> in " + manifest);
                    return;
                }
                at = text.LastIndexOf('\n', at) + 1;   // insert as a whole line, before the tag's indentation
                File.WriteAllText(manifest, text.Insert(at, line));
                Debug.Log("[Builder] VIBRATE permission inserted into " + manifest);
            }
            Builder.s_VibrateManifestChecked = manifest;
        }
    }
#endif
}
