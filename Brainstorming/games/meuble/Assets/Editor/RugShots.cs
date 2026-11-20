using System;
using System.IO;
using OutOfSight.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight.Editor
{
    /// <summary>
    /// M7 rug nine-slice (2026-11-19) verification: a look tool, not a check, throwaway (not part of any build).
    /// Builds a level once (today's nine-slice <see cref="LevelBuilder.BuildRugImage"/> already in place), shoots
    /// every rug/doormat "Image" renderer named <paramref name="rugId"/> as it stands ("after"), then swaps that
    /// renderer's mesh back to the old single stretched <see cref="PrimitiveKit.QuadMesh"/> (same transform, so the
    /// same place and size) and shoots again ("before"), so both come from the same level instance, one Unity run.
    /// -executeMethod OutOfSight.Editor.RugShots.Shoot -rugShots &lt;dir&gt;
    /// </summary>
    public static class RugShots
    {
        private struct Target
        {
            public string Level;
            public string Name;
            public float X;
            public float Z;
            public float SizeX;
            public float SizeZ;
        }

        private static readonly Target[] Targets =
        {
            new Target { Level = "level2", Name = "corridor", X = 0f, Z = 1.55f, SizeX = 5.2f, SizeZ = 0.8f },
            new Target { Level = "level22", Name = "galerie", X = 12f, Z = 10.95f, SizeX = 15.0f, SizeZ = 1.2f },
            new Target { Level = "level22", Name = "galerie_est", X = 20.95f, Z = 6.5f, SizeX = 1.2f, SizeZ = 9.0f },
        };

        public static void Shoot()
        {
            int code = 0;
            try
            {
                string dir = Arg("-rugShots") ?? Path.Combine("TestResults", "rugshots");
                Directory.CreateDirectory(dir);
                string currentLevel = null;
                LevelDef def = null;
                LevelInstance level = null;
                try
                {
                    foreach (Target t in Targets)
                    {
                        if (t.Level != currentLevel)
                        {
                            if (level != null)
                            {
                                LevelBuilder.Teardown(level);
                            }
                            currentLevel = t.Level;
                            def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, t.Level + ".json")));
                            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                            level = LevelBuilder.Build(def);
                            SetUpLightingAndCamera(out _);
                        }
                        ShootTarget(level, def, t, dir);
                    }
                }
                finally
                {
                    if (level != null)
                    {
                        LevelBuilder.Teardown(level);
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[RugShots] threw: " + e);
                code = 1;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static Camera cam;

        private static void SetUpLightingAndCamera(out Camera camera)
        {
            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = new Color(1f, 0.87f, 0.67f);
            sun.intensity = 1.35f;
            sun.shadows = LightShadows.Soft;
            sun.shadowStrength = 0.78f;
            sun.transform.rotation = Quaternion.Euler(44f, 32f, 0f);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.58f, 0.63f, 0.73f);
            RenderSettings.ambientEquatorColor = new Color(0.52f, 0.47f, 0.42f);
            RenderSettings.ambientGroundColor = new Color(0.28f, 0.23f, 0.19f);
            cam = new GameObject("ShotCamera").AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.15f, 0.16f, 0.19f);
            cam.fieldOfView = 50f;
            cam.nearClipPlane = 0.05f;
            cam.farClipPlane = 80f;
            var warm = new RenderTexture(64, 64, 24);
            cam.targetTexture = warm;
            cam.Render();
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(warm);
            camera = cam;
        }

        private static void ShootTarget(LevelInstance level, LevelDef def, Target t, string dir)
        {
            // Straight top-down, orthographic (no perspective distance to get wrong): yaw turns the rug's long
            // axis to the image's horizontal, orthographicSize sizes the frame in world metres directly.
            float longSize = Mathf.Max(t.SizeX, t.SizeZ);
            float shortSize = Mathf.Min(t.SizeX, t.SizeZ);
            float yaw = t.SizeX >= t.SizeZ ? 0f : 90f;
            const float aspect = 1600f / 1000f;
            float size = Mathf.Max(longSize * 1.2f / (2f * aspect), shortSize * 1.2f / 2f);
            Vector3 focus = new Vector3(t.X, def.FloorHeightAt(t.X, t.Z), t.Z);
            Quaternion rotation = Quaternion.Euler(90f, yaw, 0f);
            cam.orthographic = true;
            cam.orthographicSize = size;
            cam.transform.SetPositionAndRotation(focus + Vector3.up * 8f, rotation);

            MeshFilter image = FindImageNear(level, t.X, t.Z);
            Debug.Log($"[RugShots] {t.Level}_{t.Name}: image={(image != null ? image.transform.position.ToString() : "NOT FOUND")} focus={focus} size={size}");

            // "after": today's nine-slice, unchanged.
            Render(Path.Combine(dir, $"{t.Level}_{t.Name}_after.png"));

            // "before": the same renderer, its mesh swapped back to the old single stretched quad.
            Mesh original = image != null ? image.sharedMesh : null;
            if (image != null)
            {
                image.sharedMesh = PrimitiveKit.QuadMesh;
            }
            Render(Path.Combine(dir, $"{t.Level}_{t.Name}_before.png"));
            if (image != null)
            {
                image.sharedMesh = original;
            }
        }

        /// <summary>The rug/doormat "Image" MeshFilter whose world position is closest to (x, z): there is exactly
        /// one per rug, so the closest one is the one built for this target.</summary>
        private static MeshFilter FindImageNear(LevelInstance level, float x, float z)
        {
            MeshFilter best = null;
            float bestDist = float.MaxValue;
            foreach (MeshFilter mf in level.Root.GetComponentsInChildren<MeshFilter>(true))
            {
                if (mf.gameObject.name != "Image")
                {
                    continue;
                }
                Vector3 p = mf.transform.position;
                float d = (p.x - x) * (p.x - x) + (p.z - z) * (p.z - z);
                if (d < bestDist)
                {
                    bestDist = d;
                    best = mf;
                }
            }
            return best;
        }

        private static void Render(string file)
        {
            var rt = new RenderTexture(1600, 1000, 24) { antiAliasing = 4 };
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
            tex.Apply();
            File.WriteAllBytes(file, tex.EncodeToPNG());
            RenderTexture.active = null;
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(rt);
            UnityEngine.Object.DestroyImmediate(tex);
            Debug.Log("[RugShots] " + file);
        }

        private static string Arg(string flag)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == flag)
                {
                    return args[i + 1];
                }
            }
            return null;
        }
    }
}
