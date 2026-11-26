using System;
using UnityEditor;
using UnityEngine;

namespace OutOfSight.Editor
{
    /// <summary>
    /// Command line entry point for the IDE cleanup (2026-11-19, product owner): forces Unity's own IDE
    /// integration (com.unity.ide.visualstudio or com.unity.ide.rider, whichever is the external script
    /// editor) to regenerate the solution and every .csproj from the assemblies that exist right now, so a
    /// stale Meuble.*.csproj (left over from the OutOfSight rename) never lingers next to the current
    /// OutOfSight.*.csproj files.
    ///
    /// The solution file is still named after the project FOLDER, not the assemblies: Unity's generator
    /// builds its name from <c>Path.GetFileName(ProjectDirectory)</c> (ProjectGeneration.SolutionFileImpl in
    /// the ide package), with no project setting, EditorPrefs key or callback to override it; the only
    /// generation hooks (AssetPostprocessor.OnGeneratedSlnSolution/OnGeneratedCSProject) can edit a file's
    /// CONTENT, not the path Unity writes it to. The project folder was renamed from "meuble" to "out_of_sight"
    /// (2026-11-27, user request), so the solution is "out_of_sight.sln" (delete a leftover "meuble.sln"), and every
    /// project inside it (OutOfSight.Core, OutOfSight.Runtime,
    /// OutOfSight.Editor, OutOfSight.Tests.EditMode, OutOfSight.Tests.PlayMode) is named after its assembly.
    /// </summary>
    public static class IdeSync
    {
        public static void Sync()
        {
            try
            {
                Unity.CodeEditor.CodeEditor.CurrentEditor?.SyncAll();
                Debug.Log("[IdeSync] Solution and project files regenerated.");
                EditorApplication.Exit(0);
            }
            catch (Exception e)
            {
                Debug.LogError("[IdeSync] Sync failed: " + e);
                EditorApplication.Exit(1);
            }
        }
    }
}
