using System;
using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight.Editor
{
    /// <summary>
    /// Soft movers (2026-11-20): a look tool, not a check. Renders the furniture bodies and the other moving objects to PNGs,
    /// under the game's sun and ambient (no post processing), so the rounded shapes can be compared with the old ones:
    /// <list type="bullet">
    /// <item>a lineup of the six bodies in the player's red (each body's catalog model, else its procedural visual), then the
    /// same lineup with ModelKit disabled (the procedural fallbacks), front and back three quarters, and a close-up of each;</item>
    /// <item>levels with each body as the player: the game camera's default view (Tuning.OrbitDistance at
    /// Tuning.PitchDefault) from its front and from its back, a close-up, and a close-up of the first decoy and robot.</item>
    /// </list>
    /// Every picture twice: "before" (the Kenney models' own hard meshes, SoftBodies.RoundModels off, and the old boxes of
    /// the procedural bodies, BodyShotsLegacy) and "after" (the game as it builds now).
    /// -executeMethod OutOfSight.Editor.BodyShots.Shoot -bodyShots &lt;dir&gt; [-bodyLevels level1,level4] [-bodySets after]
    /// </summary>
    public static class BodyShots
    {
        private static readonly string[] DefaultLevels = { "level1", "level4", "level5", "level6", "level7", "level10", "level11", "level3", "level9" };

        private static readonly Color Red = new Color32(0xD7, 0x26, 0x3D, 0xFF);

        public static void Shoot()
        {
            int code = 0;
            try
            {
                string dir = Arg("-bodyShots") ?? Path.Combine("TestResults", "bodies");
                Directory.CreateDirectory(dir);
                string levels = Arg("-bodyLevels");
                foreach (string tag in (Arg("-bodySets") ?? "before,after").Split(','))
                {
                    bool before = tag == "before";
                    SoftBodies.RoundModels = !before;
                    Lineup(dir, tag, false, before);
                    Lineup(dir, tag, true, before);
                    foreach (string id in levels != null ? levels.Split(',') : DefaultLevels)
                    {
                        ShootLevel(dir, tag, id, before);
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[BodyShots] threw: " + e);
                code = 1;
            }
            finally
            {
                ModelKit.Disabled = false;
                SoftBodies.RoundModels = true;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static Camera Stage()
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
            cam.fieldOfView = 40f;
            cam.nearClipPlane = 0.03f;
            cam.farClipPlane = 80f;
            // The first render of a fresh editor comes out tinted while the shaders warm up: throw one away.
            var warm = new RenderTexture(64, 64, 24);
            cam.targetTexture = warm;
            cam.Render();
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(warm);
            return cam;
        }

        /// <summary>The six bodies in a row along x, facing +z, on a plain floor.</summary>
        private static void Lineup(string dir, string tag, bool procedural, bool legacy)
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            ModelKit.Disabled = procedural;
            var floor = new GameObject("Floor");
            floor.AddComponent<MeshFilter>().sharedMesh = PrimitiveKit.BoxMesh;
            floor.AddComponent<MeshRenderer>().sharedMaterial = PrimitiveKit.Lit(new Color(0.62f, 0.58f, 0.52f), 0.2f);
            floor.transform.localScale = new Vector3(14f, 0.02f, 8f);
            floor.transform.position = new Vector3(0f, -0.01f, 0f);
            var placed = new List<(string kind, Transform root, Vector3 size)>();
            float x = -(BodyKinds.All.Length - 1) * 0.55f;
            foreach (string kind in BodyKinds.All)
            {
                BodyDef body = BodyDef.For(kind);
                var root = new GameObject(kind) { layer = Layers.Player };
                root.transform.position = new Vector3(x, 0f, 0f);
                string model = kind == BodyKinds.Chair ? ModelCatalog.KenneyChair : BodyKinds.DefaultModel(kind);
                if (model == null || ModelKit.Instantiate(model, root.transform, body.Size, ModelFit.Box, new ModelPaint { Main = Red, Red = Red }) == null)
                {
                    if (legacy)
                    {
                        BodyShotsLegacy.Body(kind, root.transform, body.Size, Red, Layers.Player);
                    }
                    else
                    {
                        FurnitureKit.Body(kind, root.transform, body.Size, Red, Layers.Player);
                    }
                }
                placed.Add((kind, root.transform, body.Size));
                x += 1.1f;
            }
            ModelKit.Disabled = false;
            Camera cam = Stage();
            string set = procedural ? "proc" : "model";
            cam.fieldOfView = 50f;
            Render(cam, null, new Vector3(0.8f, 2.6f, 6.2f), new Vector3(0f, 0.55f, 0f), Path.Combine(dir, $"{tag}_lineup_{set}_front.png"));
            Render(cam, null, new Vector3(-0.8f, 2.6f, -6.2f), new Vector3(0f, 0.55f, 0f), Path.Combine(dir, $"{tag}_lineup_{set}_back.png"));
            cam.fieldOfView = 40f;
            foreach ((string kind, Transform root, Vector3 size) in placed)
            {
                Vector3 centre = root.position + Vector3.up * (size.y * 0.5f);
                float d = Mathf.Max(size.y, size.x) * 1.7f + 0.3f;
                Render(cam, null, centre + new Vector3(0.55f * d, 0.45f * d, 0.85f * d), centre, Path.Combine(dir, $"{tag}_{set}_{kind}_front.png"));
                Render(cam, null, centre + new Vector3(-0.6f * d, 0.5f * d, -0.8f * d), centre, Path.Combine(dir, $"{tag}_{set}_{kind}_back.png"));
            }
        }

        /// <summary>A procedural body visual (no model root under it) rebuilt as the old boxes, in <paramref name="color"/>.</summary>
        private static void Legacy(Transform visual, string kind, Vector3 size, Color color)
        {
            if (visual == null || ModelKit.ModelRootsUnder(visual).Count > 0)
            {
                return;
            }
            var doomed = new List<GameObject>();
            foreach (Transform child in visual)
            {
                if (child.GetComponent<LoadView>() == null)
                {
                    doomed.Add(child.gameObject);
                }
            }
            foreach (GameObject g in doomed)
            {
                UnityEngine.Object.DestroyImmediate(g);
            }
            BodyShotsLegacy.Body(kind, visual, size, color, visual.gameObject.layer);
        }

        private static void ShootLevel(string dir, string tag, string id, bool legacy)
        {
            LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, id + ".json")));
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            LevelInstance level = LevelBuilder.Build(def);
            try
            {
                if (legacy)
                {
                    if (level.Furniture != null)
                    {
                        Legacy(level.Furniture.Visual, level.Furniture.Kind, level.Furniture.Size, LevelJson.ParseColor(def.Player.Color, Red));
                    }
                    foreach (Decoy decoy in level.Decoys)
                    {
                        Legacy(decoy.transform.Find("Visual"), decoy.Kind, decoy.Size, new Color32(0x8C, 0x5A, 0x36, 0xFF));
                    }
                    foreach (Robot robot in level.Robots)
                    {
                        Transform shell = robot.Body != null ? robot.Body.Find("Shell") : null;
                        if (shell != null)
                        {
                            shell.GetComponent<MeshFilter>().sharedMesh = BodyShotsLegacy.RobotShell();
                        }
                    }
                }
                Camera cam = Stage();
                cam.fieldOfView = 55f;
                var fader = level.Root.GetComponent<WallFader>();
                FurnitureController player = level.Furniture;
                if (player != null)
                {
                    Vector3 target = player.transform.position + Vector3.up * Tuning.CameraTargetHeight;
                    float yaw = player.transform.eulerAngles.y;
                    foreach ((string side, float offset) in new[] { ("front", 180f + 30f), ("back", 30f) })
                    {
                        Quaternion orbit = Quaternion.Euler(Tuning.PitchDefault, yaw + offset, 0f);
                        Vector3 eye = target - orbit * Vector3.forward * Tuning.OrbitDistance;
                        Render(cam, fader, eye, target, Path.Combine(dir, $"{tag}_{id}_game_{side}.png"));
                    }
                    cam.fieldOfView = 40f;
                    Vector3 size = player.Size;
                    Vector3 centre = player.transform.position + Vector3.up * (size.y * 0.5f);
                    float d = Mathf.Max(size.y, size.x) * 1.6f + 0.3f;
                    Quaternion turn = Quaternion.Euler(0f, yaw, 0f);
                    Render(cam, fader, centre + turn * new Vector3(0.55f * d, 0.5f * d, 0.85f * d), centre, Path.Combine(dir, $"{tag}_{id}_player_close.png"));
                    Render(cam, fader, centre + turn * new Vector3(-0.55f * d, 0.55f * d, -0.85f * d), centre, Path.Combine(dir, $"{tag}_{id}_player_back.png"));
                    // The top of the body from above and near (a tall lamp's shade, a seat), clear of the room's railings.
                    Vector3 top = player.transform.position + Vector3.up * (size.y * 0.8f);
                    float near = Mathf.Max(size.x, size.z) * 2.6f + 0.35f;
                    Render(cam, fader, top + turn * new Vector3(0.45f * near, 0.75f * near, 0.6f * near), top, Path.Combine(dir, $"{tag}_{id}_player_top.png"));
                }
                cam.fieldOfView = 40f;
                if (level.Decoys.Count > 0)
                {
                    Decoy decoy = level.Decoys[0];
                    Vector3 centre = decoy.transform.position + Vector3.up * (decoy.Size.y * 0.5f);
                    float d = Mathf.Max(decoy.Size.y, decoy.Size.x) * 1.6f + 0.3f;
                    Quaternion turn = decoy.transform.rotation;
                    Render(cam, fader, centre + turn * new Vector3(0.55f * d, 0.5f * d, 0.85f * d), centre, Path.Combine(dir, $"{tag}_{id}_decoy_close.png"));
                }
                if (level.Robots.Count > 0)
                {
                    Transform robot = level.Robots[0].Body != null ? level.Robots[0].Body : level.Robots[0].transform;
                    Vector3 centre = robot.position + Vector3.up * 0.05f;
                    Render(cam, fader, centre + robot.rotation * new Vector3(0.35f, 0.4f, 0.55f), centre, Path.Combine(dir, $"{tag}_{id}_robot_close.png"));
                }
            }
            finally
            {
                LevelBuilder.Teardown(level);
            }
        }

        private static void Render(Camera cam, WallFader fader, Vector3 position, Vector3 look, string file)
        {
            cam.transform.SetPositionAndRotation(position, Quaternion.LookRotation(look - position));
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
            Debug.Log($"[BodyShots] {file}");
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
