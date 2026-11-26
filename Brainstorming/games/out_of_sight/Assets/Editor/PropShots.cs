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
    /// M8 room objects (docs/m8/ROOMS_PLAN.md 3): a look tool, not a check. Builds a level in an editor scene twice, with its
    /// catalog models ("model") and with ModelKit disabled ("proc", every prop procedural), and renders to PNGs: a view of
    /// every room from inside its -z wall toward +z (where the room objects stand at yaw 0), and a close view of the front of
    /// every M8 room object (PropKinds.RoomObjects), under the game's sun and ambient (no post processing).
    /// -executeMethod OutOfSight.Editor.PropShots.Shoot -propShots &lt;dir&gt; -propLevel test_rooms [-propKinds bookshelf]
    /// </summary>
    public static class PropShots
    {
        public static void Shoot()
        {
            int code = 0;
            try
            {
                string dir = Arg("-propShots") ?? Path.Combine("TestResults", "props");
                Directory.CreateDirectory(dir);
                // -propLevel a,b: several levels in one editor run.
                foreach (string id in (Arg("-propLevel") ?? "test_rooms").Split(','))
                {
                    ShootLevel(dir, id, false);
                    ShootLevel(dir, id, true);
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[PropShots] threw: " + e);
                code = 1;
            }
            finally
            {
                ModelKit.Disabled = false;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static void ShootLevel(string dir, string id, bool procedural)
        {
            LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, id + ".json")));
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            ModelKit.Disabled = procedural;
            LevelInstance level = LevelBuilder.Build(def);
            ModelKit.Disabled = false;
            string tag = procedural ? "proc" : "model";
            try
            {
                var sun = new GameObject("Sun").AddComponent<Light>();
                sun.type = LightType.Directional;
                sun.color = new Color(1f, 0.87f, 0.67f);
                sun.intensity = 1.35f;
                sun.shadows = LightShadows.Soft;
                sun.shadowStrength = 0.78f;
                sun.transform.rotation = Quaternion.Euler(50f, 20f, 0f);
                RenderSettings.ambientMode = AmbientMode.Trilight;
                RenderSettings.ambientSkyColor = new Color(0.58f, 0.63f, 0.73f);
                RenderSettings.ambientEquatorColor = new Color(0.52f, 0.47f, 0.42f);
                RenderSettings.ambientGroundColor = new Color(0.28f, 0.23f, 0.19f);
                var cam = new GameObject("ShotCamera").AddComponent<Camera>();
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.15f, 0.16f, 0.19f);
                cam.fieldOfView = 60f;
                cam.nearClipPlane = 0.05f;
                cam.farClipPlane = 80f;
                var fader = level.Root.GetComponent<WallFader>();
                // The first render of a fresh editor comes out tinted while the shaders warm up: throw one away.
                var warm = new RenderTexture(64, 64, 24);
                cam.targetTexture = warm;
                cam.Render();
                cam.targetTexture = null;
                UnityEngine.Object.DestroyImmediate(warm);

                foreach (RoomDef room in def.AllRooms())
                {
                    var eye = new Vector3(room.X, 2.3f, room.Z - room.SizeZ * 0.5f + 0.15f);
                    var look = new Vector3(room.X, 0.55f, room.Z + room.SizeZ * 0.3f);
                    Render(cam, fader, eye, Quaternion.LookRotation(look - eye), Path.Combine(dir, $"{id}_room_{room.Id}_{tag}.png"));
                }
                // -propKinds a,b: the close views of those kinds instead of the M8 room objects (the bookshelf pass: bookshelf).
                string kindsArg = Arg("-propKinds");
                string[] kinds = string.IsNullOrEmpty(kindsArg) ? PropKinds.RoomObjects : kindsArg.Split(',');
                foreach (PropDef prop in def.Props)
                {
                    if (Array.IndexOf(kinds, prop.Kind) < 0)
                    {
                        continue;
                    }
                    // In front of the prop (its -z face), a little to its +x side and above.
                    Quaternion turn = Quaternion.Euler(0f, prop.Yaw, 0f);
                    float d = Mathf.Max(prop.SizeX, Mathf.Max(prop.SizeY, prop.SizeZ)) * 1.1f + 0.7f;
                    Vector3 center = prop.Position + Vector3.up * (prop.SizeY * 0.45f);
                    Vector3 eye = center + turn * new Vector3(d * 0.35f, d * 0.55f, -d);
                    Render(cam, fader, eye, Quaternion.LookRotation(center - eye), Path.Combine(dir, $"{id}_{prop.Kind}_{prop.Name}_{tag}.png"));
                    // The game camera's default view (Tuning.OrbitDistance at Tuning.PitchDefault, aimed at
                    // Tuning.CameraTargetHeight), from the prop's front a little to its side.
                    Vector3 target = prop.Position + Vector3.up * Tuning.CameraTargetHeight;
                    Quaternion orbit = turn * Quaternion.Euler(Tuning.PitchDefault, 25f, 0f);
                    Vector3 gameEye = target - orbit * Vector3.forward * Tuning.OrbitDistance;
                    Render(cam, fader, gameEye, orbit, Path.Combine(dir, $"{id}_{prop.Kind}_{prop.Name}_{tag}_game.png"));
                }
            }
            finally
            {
                LevelBuilder.Teardown(level);
            }
        }

        private static void Render(Camera cam, WallFader fader, Vector3 position, Quaternion rotation, string file)
        {
            cam.transform.SetPositionAndRotation(position, rotation);
            if (fader != null)
            {
                fader.Apply(position);
                fader.DrawFaded(cam);
            }
            var rt = new RenderTexture(1280, 800, 24) { antiAliasing = 4 };
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
            Debug.Log($"[PropShots] {file}");
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
