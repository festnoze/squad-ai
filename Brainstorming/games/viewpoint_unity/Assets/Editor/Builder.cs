using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace Viewpoint.Editor
{
    /// <summary>
    /// Command line entry points. Two lessons are baked in here, both learned
    /// the hard way on this toolchain:
    ///
    /// 1. In batch mode a failed build still exits 0 unless the method exits
    ///    explicitly, so every path ends in EditorApplication.Exit.
    /// 2. BuildPipeline.BuildPlayer can report Succeeded without leaving an
    ///    artifact on disk, so success is confirmed against the file system,
    ///    never against the report alone.
    /// </summary>
    public static class Builder
    {
        private const string ScenePath = "Assets/Scenes/Main.unity";

        /// <summary>
        /// Compiles nothing by itself: it only runs once the editor has
        /// finished compiling, so reaching it at all proves the scripts build.
        /// Used as the fast compile gate before the test suites are worth
        /// running.
        /// </summary>
        public static void CompileCheck()
        {
            Debug.Log("[Builder] Scripts compiled.");
            EditorApplication.Exit(0);
        }

        public static void BuildWindows()
        {
            Build(BuildTarget.StandaloneWindows64, ArgOr("-output", "Build/Windows/VIEWPOINT.exe"));
        }

        public static void BuildWebGL()
        {
            Build(BuildTarget.WebGL, ArgOr("-output", "Build/WebGL"));
        }

        private static void Build(BuildTarget target, string output)
        {
            if (!File.Exists(ScenePath))
            {
                Debug.LogError("[Builder] Missing scene: " + ScenePath);
                EditorApplication.Exit(1);
                return;
            }

            var options = new BuildPlayerOptions
            {
                scenes = new[] { ScenePath },
                locationPathName = output,
                target = target,
                options = BuildOptions.None,
            };

            BuildReport report;
            try
            {
                report = BuildPipeline.BuildPlayer(options);
            }
            catch (Exception e)
            {
                Debug.LogError("[Builder] Build threw: " + e);
                EditorApplication.Exit(1);
                return;
            }

            var summary = report.summary;
            // A WebGL build lands in a directory, a Windows build in a file.
            var produced = Directory.Exists(output) || File.Exists(output);
            if (summary.result != BuildResult.Succeeded || !produced)
            {
                Debug.LogError(string.Format(
                    "[Builder] Build failed: result {0}, {1} errors, artifact present {2}",
                    summary.result, summary.totalErrors, produced));
                EditorApplication.Exit(1);
                return;
            }

            Debug.Log(string.Format("[Builder] Built {0} -> {1} ({2} bytes)",
                target, output, summary.totalSize));
            EditorApplication.Exit(0);
        }

        private static string ArgOr(string flag, string fallback)
        {
            var args = Environment.GetCommandLineArgs();
            for (var i = 0; i < args.Length - 1; i++)
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
