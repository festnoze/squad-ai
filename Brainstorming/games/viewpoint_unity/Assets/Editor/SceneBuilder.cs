using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Viewpoint.Editor
{
    /// <summary>
    /// Builds Assets/Scenes/Main.unity from code instead of hand authoring it.
    ///
    /// PRD section 15.1 asks for a single scene holding only the skeleton, and
    /// in this port the skeleton is a single node: Main builds LevelRoot, the
    /// player, the two canvases and the photo studio at runtime. A scene that
    /// small is still worth generating rather than editing by hand, because a
    /// .unity file is YAML full of GUIDs: unreviewable in a diff, and easy to
    /// break by accident. Regenerating it is one menu click or one
    /// -executeMethod away.
    ///
    /// Deliberately absent from the scene: a camera and a light. Main creates
    /// both (plus the studio pair of PRD section 15.6), so a camera left in
    /// the scene would render the world a second time on top of the game.
    /// </summary>
    public static class SceneBuilder
    {
        /// <summary>Asset path of the one scene of the game (PRD section 15.2).</summary>
        private const string ScenePath = "Assets/Scenes/Main.unity";

        private const string SceneFolder = "Assets/Scenes";

        private const string RootName = "Main";

        /// <summary>
        /// Menu entry point. Throws on failure so the console carries a stack
        /// trace pointing at the step that gave up.
        /// </summary>
        [MenuItem("VIEWPOINT/Rebuild Main Scene")]
        public static void Rebuild()
        {
            // Interactive runs must not silently drop whatever the user has
            // open: NewScene in Single mode closes the current scenes without
            // asking. Batch mode has nobody to ask and nothing unsaved.
            if (!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
            {
                throw new OperationCanceledException(
                    "[SceneBuilder] Rebuild cancelled: the open scene was left unsaved.");
            }

            EnsureFolder();

            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            if (!scene.IsValid())
            {
                throw new InvalidOperationException("[SceneBuilder] NewScene returned an invalid scene.");
            }

            // The new scene is the active one, so this lands in it. One object,
            // one component: everything else is Main's job at runtime.
            var root = new GameObject(RootName);
            root.transform.position = Vector3.zero;
            root.transform.rotation = Quaternion.identity;
            root.AddComponent<global::Viewpoint.Main>();

            if (!EditorSceneManager.SaveScene(scene, ScenePath))
            {
                throw new IOException("[SceneBuilder] SaveScene refused to write " + ScenePath);
            }

            AssetDatabase.SaveAssets();

            // A save that reports fine can still leave nothing on disk, so the
            // file system is the only witness that counts. Application.dataPath
            // ends in /Assets; its parent is the project root, which is a safer
            // base than the process working directory.
            var absolute = Path.Combine(ProjectRoot(), ScenePath);
            if (!File.Exists(absolute))
            {
                throw new IOException("[SceneBuilder] Scene reported saved but is missing: " + absolute);
            }

            var bytes = new FileInfo(absolute).Length;
            if (bytes <= 0)
            {
                throw new IOException("[SceneBuilder] Scene saved empty: " + absolute);
            }

            RegisterInBuildSettings();

            Debug.Log(string.Format(
                "[SceneBuilder] Wrote {0} ({1} bytes), root '{2}' with Viewpoint.Main, build settings scene 0.",
                ScenePath, bytes, RootName));
        }

        /// <summary>
        /// Entry point for -executeMethod. In batch mode an exception is logged
        /// and the process still exits 0, which looks exactly like a pass, so
        /// every path ends in an explicit EditorApplication.Exit.
        /// </summary>
        public static void RebuildBatch()
        {
            try
            {
                Rebuild();
            }
            catch (Exception e)
            {
                Debug.LogError("[SceneBuilder] Rebuild failed: " + e);
                EditorApplication.Exit(1);
                return;
            }

            EditorApplication.Exit(0);
        }

        /// <summary>Creates Assets/Scenes when a fresh clone does not carry it.</summary>
        private static void EnsureFolder()
        {
            if (AssetDatabase.IsValidFolder(SceneFolder))
            {
                return;
            }

            // The folder can exist on disk without being imported yet (git does
            // not track empty directories, and a .meta alone is not enough).
            var absolute = Path.Combine(ProjectRoot(), SceneFolder);
            if (Directory.Exists(absolute))
            {
                AssetDatabase.Refresh();
            }

            if (AssetDatabase.IsValidFolder(SceneFolder))
            {
                return;
            }

            var guid = AssetDatabase.CreateFolder("Assets", "Scenes");
            if (string.IsNullOrEmpty(guid))
            {
                throw new IOException("[SceneBuilder] Could not create " + SceneFolder);
            }
        }

        /// <summary>
        /// Makes Main.unity the only enabled scene of the build, so a player
        /// build starts on it whatever the previous state of the list was.
        /// </summary>
        private static void RegisterInBuildSettings()
        {
            EditorBuildSettings.scenes = new[]
            {
                new EditorBuildSettingsScene(ScenePath, true),
            };
        }

        private static string ProjectRoot()
        {
            // Application.dataPath is "<project>/Assets".
            var root = Path.GetDirectoryName(Application.dataPath);
            if (string.IsNullOrEmpty(root))
            {
                throw new IOException("[SceneBuilder] Could not resolve the project root from " + Application.dataPath);
            }

            return root;
        }
    }
}
