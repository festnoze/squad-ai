using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

/// <summary>
/// Command-line build entry point.
///
/// Only desktop targets have a built-in command-line build in the Unity CLI;
/// Android, iOS and WebGL require either a build profile or an --execute-method
/// like this one. One method covers every target: `unity build --target X`
/// forwards -buildTarget to Unity, which switches the active target before this
/// runs, so the target is read rather than hardcoded.
///
///   unity build &lt;project&gt; --target Android \
///     --execute-method Builder.PerformBuild \
///     --output-path C:/out/game.apk
/// </summary>
public static class Builder
{
    public static void PerformBuild()
    {
        try
        {
            var target = EditorUserBuildSettings.activeBuildTarget;
            var scenes = EditorBuildSettings.scenes
                .Where(s => s.enabled)
                .Select(s => s.path)
                .ToArray();

            // An empty scene list produces a player that boots to nothing while
            // the build still reports success, so refuse it outright.
            if (scenes.Length == 0)
                Fail("No enabled scenes in Build Settings; refusing to build an empty player.");

            var output = ArgValue("-buildOutput") ?? DefaultOutput(target);
            var dir = Path.GetDirectoryName(output);
            if (!string.IsNullOrEmpty(dir))
                Directory.CreateDirectory(dir);

            Debug.Log($"[Builder] target={target} scenes={scenes.Length} output={output}");

            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = output,
                target = target,
                options = BuildOptions.None,
            });

            var summary = report.summary;
            Debug.Log($"[Builder] result={summary.result} size={summary.totalSize} " +
                      $"errors={summary.totalErrors} time={summary.totalTime}");

            if (summary.result != BuildResult.Succeeded)
                Fail($"Build finished with result={summary.result}, errors={summary.totalErrors}.");

            // BuildPlayer can report Succeeded without leaving an artifact on
            // disk in some misconfigurations, so check the file itself.
            if (!File.Exists(output) && !Directory.Exists(output))
                Fail($"Build reported success but nothing exists at {output}.");

            Debug.Log("[Builder] OK");
            EditorApplication.Exit(0);
        }
        catch (Exception e)
        {
            Fail($"Unhandled exception: {e}");
        }
    }

    private static void Fail(string message)
    {
        Debug.LogError($"[Builder] FAILED: {message}");
        // Without an explicit non-zero exit, batch mode returns 0 and CI reads
        // a broken build as a passing one.
        EditorApplication.Exit(1);
    }

    private static string ArgValue(string name)
    {
        var args = Environment.GetCommandLineArgs();
        for (var i = 0; i < args.Length - 1; i++)
            if (string.Equals(args[i], name, StringComparison.Ordinal))
                return args[i + 1];
        return null;
    }

    private static string DefaultOutput(BuildTarget target) => target switch
    {
        BuildTarget.Android => "Builds/Android/game.apk",
        BuildTarget.StandaloneWindows64 => "Builds/Windows/game.exe",
        BuildTarget.WebGL => "Builds/WebGL",
        _ => $"Builds/{target}/game",
    };
}
