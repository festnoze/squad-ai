using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace Smoke.Editor
{
    /// <summary>
    /// Generates the game scene from code and builds the Windows player.
    /// Batch entry points: Smoke.Editor.SmokeBuilder.BuildScene / BuildPlayer / BuildAll.
    /// Materials are saved as assets so the build keeps their shaders (Shader.Find alone gets stripped).
    /// </summary>
    public static class SmokeBuilder
    {
        public const string ScenePath = "Assets/Scenes/Main.unity";
        public const string MaterialDir = "Assets/Materials";
        public const string PlayerPath = "Build/Windows/unity_smoke.exe";
        private const string LitShader = "Universal Render Pipeline/Lit";
        private const int CoinCount = 8;
        private const float HalfSize = 10f;

        [MenuItem("Smoke/Build Scene")]
        public static void BuildScene()
        {
            Material ground = SaveMaterial("Ground", new Color(0.22f, 0.45f, 0.30f), 0.2f);
            Material wall = SaveMaterial("Wall", new Color(0.55f, 0.55f, 0.60f), 0.1f);
            Material playerMat = SaveMaterial("Player", new Color(0.15f, 0.45f, 0.95f), 0.6f);
            Material coinMat = SaveMaterial("Coin", new Color(1.0f, 0.80f, 0.10f), 0.8f, 0.9f);

            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);

            Camera cam = Camera.main;
            cam.transform.position = new Vector3(0f, 17f, -14f);
            cam.transform.LookAt(new Vector3(0f, 0f, -1f));
            cam.fieldOfView = 50f;

            Light sun = UnityEngine.Object.FindFirstObjectByType<Light>();
            sun.transform.rotation = Quaternion.Euler(55f, -35f, 0f);
            sun.shadows = LightShadows.Soft;

            GameObject floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
            floor.name = "Ground";
            floor.transform.localScale = new Vector3(HalfSize / 5f, 1f, HalfSize / 5f);
            floor.GetComponent<Renderer>().sharedMaterial = ground;

            CreateWall("Wall_N", new Vector3(0f, 0.5f, HalfSize), new Vector3(HalfSize * 2f + 1f, 1f, 1f), wall);
            CreateWall("Wall_S", new Vector3(0f, 0.5f, -HalfSize), new Vector3(HalfSize * 2f + 1f, 1f, 1f), wall);
            CreateWall("Wall_E", new Vector3(HalfSize, 0.5f, 0f), new Vector3(1f, 1f, HalfSize * 2f + 1f), wall);
            CreateWall("Wall_W", new Vector3(-HalfSize, 0.5f, 0f), new Vector3(1f, 1f, HalfSize * 2f + 1f), wall);

            GameObject player = GameObject.CreatePrimitive(PrimitiveType.Cube);
            player.name = "Player";
            player.transform.position = new Vector3(0f, 0.5f, 0f);
            player.GetComponent<Renderer>().sharedMaterial = playerMat;
            Rigidbody body = player.AddComponent<Rigidbody>();
            body.constraints = RigidbodyConstraints.FreezeRotation;
            body.interpolation = RigidbodyInterpolation.Interpolate;
            body.collisionDetectionMode = CollisionDetectionMode.Continuous;
            player.AddComponent<PlayerController>();

            // Deterministic ring of coins so tests and screenshots are reproducible.
            for (int i = 0; i < CoinCount; i++)
            {
                float angle = i * Mathf.PI * 2f / CoinCount;
                float radius = i % 2 == 0 ? 7f : 4.5f;
                CreateCoin(i, new Vector3(Mathf.Cos(angle) * radius, 0.75f, Mathf.Sin(angle) * radius), coinMat);
            }

            GameObject managerGo = new GameObject("GameManager");
            GameManager manager = managerGo.AddComponent<GameManager>();
            managerGo.AddComponent<SmokeProbe>();
            BuildHud(manager);

            Directory.CreateDirectory(Path.GetDirectoryName(ScenePath));
            if (!EditorSceneManager.SaveScene(scene, ScenePath))
            {
                throw new InvalidOperationException("Could not save " + ScenePath);
            }
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            AssetDatabase.SaveAssets();
            Debug.Log("[SmokeBuilder] Scene written to " + ScenePath);
        }

        [MenuItem("Smoke/Build Windows Player")]
        public static void BuildPlayer()
        {
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.defaultScreenWidth = 1280;
            PlayerSettings.defaultScreenHeight = 720;
            PlayerSettings.resizableWindow = true;
            PlayerSettings.runInBackground = true;

            var options = new BuildPlayerOptions
            {
                scenes = new[] { ScenePath },
                locationPathName = PlayerPath,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None,
            };
            BuildReport report = BuildPipeline.BuildPlayer(options);
            // A "Succeeded" summary can come without an artefact on disk: check both.
            if (report.summary.result != BuildResult.Succeeded || !File.Exists(PlayerPath))
            {
                throw new InvalidOperationException(
                    $"Player build failed: result={report.summary.result}, errors={report.summary.totalErrors}, exists={File.Exists(PlayerPath)}");
            }
            Debug.Log($"[SmokeBuilder] Player built: {PlayerPath} ({report.summary.totalSize / (1024 * 1024)} MB)");
        }

        /// <summary>Batch entry point: scene then player, exits 0 on success and 1 on any failure.</summary>
        public static void BuildAll()
        {
            int code = 0;
            try
            {
                BuildScene();
                BuildPlayer();
            }
            catch (Exception e)
            {
                Debug.LogError("[SmokeBuilder] " + e);
                code = 1;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static Material SaveMaterial(string name, Color color, float smoothness, float metallic = 0f)
        {
            Directory.CreateDirectory(MaterialDir);
            string path = $"{MaterialDir}/{name}.mat";
            Shader shader = Shader.Find(LitShader);
            if (shader == null)
            {
                throw new InvalidOperationException("Shader not found: " + LitShader);
            }
            Material mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null)
            {
                mat = new Material(shader);
                AssetDatabase.CreateAsset(mat, path);
            }
            mat.shader = shader;
            mat.SetColor("_BaseColor", color);
            mat.SetFloat("_Smoothness", smoothness);
            mat.SetFloat("_Metallic", metallic);
            EditorUtility.SetDirty(mat);
            return mat;
        }

        private static void CreateWall(string name, Vector3 position, Vector3 scale, Material mat)
        {
            GameObject wall = GameObject.CreatePrimitive(PrimitiveType.Cube);
            wall.name = name;
            wall.transform.position = position;
            wall.transform.localScale = scale;
            wall.GetComponent<Renderer>().sharedMaterial = mat;
        }

        private static void CreateCoin(int index, Vector3 position, Material mat)
        {
            var root = new GameObject($"Coin_{index}");
            root.transform.position = position;
            SphereCollider trigger = root.AddComponent<SphereCollider>();
            trigger.isTrigger = true;
            trigger.radius = 0.7f;
            root.AddComponent<Coin>();

            GameObject visual = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            visual.name = "Visual";
            UnityEngine.Object.DestroyImmediate(visual.GetComponent<Collider>());
            visual.transform.SetParent(root.transform, false);
            visual.transform.localRotation = Quaternion.Euler(90f, 0f, 0f);
            visual.transform.localScale = new Vector3(0.8f, 0.06f, 0.8f);
            visual.GetComponent<Renderer>().sharedMaterial = mat;
        }

        private static void BuildHud(GameManager manager)
        {
            var canvasGo = new GameObject("HUD");
            Canvas canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            CanvasScaler scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);

            // Engine built-in font: present in every player, unlike TMP or OS fonts.
            Font font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            Text score = CreateText(canvasGo.transform, "Score", font, 56, TextAnchor.UpperLeft,
                new Vector2(0f, 1f), new Vector2(40f, -30f), "Pieces : 0/0");
            Text message = CreateText(canvasGo.transform, "Message", font, 48, TextAnchor.UpperCenter,
                new Vector2(0.5f, 1f), new Vector2(0f, -110f), "ZQSD / fleches pour ramasser les pieces");

            var so = new SerializedObject(manager);
            so.FindProperty("scoreText").objectReferenceValue = score;
            so.FindProperty("messageText").objectReferenceValue = message;
            so.ApplyModifiedPropertiesWithoutUndo();
        }

        private static Text CreateText(Transform parent, string name, Font font, int size, TextAnchor anchor,
            Vector2 pivotAnchor, Vector2 offset, string initial)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            RectTransform rect = go.AddComponent<RectTransform>();
            rect.anchorMin = rect.anchorMax = rect.pivot = pivotAnchor;
            rect.anchoredPosition = offset;
            rect.sizeDelta = new Vector2(1400f, 90f);
            Text text = go.AddComponent<Text>();
            text.font = font;
            text.fontSize = size;
            text.alignment = anchor;
            text.color = Color.white;
            text.text = initial;
            Outline outline = go.AddComponent<Outline>();
            outline.effectColor = new Color(0f, 0f, 0f, 0.8f);
            outline.effectDistance = new Vector2(2f, -2f);
            return text;
        }
    }
}
