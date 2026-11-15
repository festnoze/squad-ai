using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace Meuble.Editor
{
    /// <summary>
    /// Command line entry points. In batch mode a failed build still exits 0 unless the method exits
    /// explicitly, and BuildPlayer can report Succeeded without an artifact, so every path ends in
    /// EditorApplication.Exit and success is confirmed against the file system.
    /// </summary>
    public static class Builder
    {
        public const string WindowsOutput = "Build/Windows/Meuble.exe";

        /// <summary>Reached only once the editor compiled every script: runs the setup and exits 0.</summary>
        public static void SetupAndCompile()
        {
            try
            {
                ProjectSetup.Apply();
                // M3: the catalogs that ship the models and the clips (docs/CONTRACT_M3.md 3 and 7).
                ModelCatalogBuilder.Build();
                AudioLibraryBuilder.Build();
                UnityEditor.AssetDatabase.SaveAssets();
                Debug.Log("[Builder] Scripts compiled and project set up.");
                EditorApplication.Exit(0);
            }
            catch (Exception e)
            {
                Debug.LogError("[Builder] Setup failed: " + e);
                EditorApplication.Exit(1);
            }
        }

        [MenuItem("Meuble/Build Windows Player")]
        public static void BuildWindows()
        {
            string output = ArgOr("-output", WindowsOutput);
            int code = Build(BuildTarget.StandaloneWindows64, output);
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static int Build(BuildTarget target, string output)
        {
            try
            {
                ProjectSetup.Apply();
                ModelCatalogBuilder.Build();
                AudioLibraryBuilder.Build();
                AssetDatabase.SaveAssets();
                // -development: a Development Build with script debugging, so Visual Studio can attach to the player
                // (Debug > Attach Unity Debugger). -waitForDebugger also makes the player wait for it at startup.
                bool development = HasFlag("-development");
                EditorUserBuildSettings.waitForManagedDebugger = development && HasFlag("-waitForDebugger");
                var options = new BuildPlayerOptions
                {
                    scenes = new[] { ProjectSetup.ScenePath },
                    locationPathName = output,
                    target = target,
                    options = development ? BuildOptions.Development | BuildOptions.AllowDebugging : BuildOptions.None,
                };
                BuildReport report = BuildPipeline.BuildPlayer(options);
                BuildSummary summary = report.summary;
                bool produced = File.Exists(output);
                if (summary.result != BuildResult.Succeeded || !produced)
                {
                    Debug.LogError($"[Builder] Build failed: result {summary.result}, {summary.totalErrors} errors, artifact present {produced}");
                    return 1;
                }
                Debug.Log($"[Builder] Built {target} -> {output} ({summary.totalSize / (1024 * 1024)} MB reported)");
                return 0;
            }
            catch (Exception e)
            {
                Debug.LogError("[Builder] Build threw: " + e);
                return 1;
            }
        }

        private static bool HasFlag(string flag)
        {
            return Array.IndexOf(Environment.GetCommandLineArgs(), flag) >= 0;
        }

        private static string ArgOr(string flag, string fallback)
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
    }
}
