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
    /// M7 walls pass: a look tool, not a check. Builds a few levels in an editor scene and renders the see-through walls to PNGs
    /// from a high camera behind the player (the view of the product owner's report, 2026-11-18) and from the three other
    /// sides, the wall fader applied for each camera, under the game's sun and ambient (no post processing).
    /// -executeMethod OutOfSight.Editor.WallShots.Shoot -wallShots &lt;dir&gt; -wallLevels level4,level12 [-wallLegacy]
    /// With -wallLegacy every view is also rendered "before": the level built part by part, its floor under the walls, its
    /// fills and closures hidden, a faded wall not drawn at all, and the pre M7 rules put back (an outer wall's cap cut only
    /// when its plane separates the camera from the player, outer door frames never cut), an emulation of the old walls.
    /// </summary>
    public static class WallShots
    {
        public static void Shoot()
        {
            int code = 0;
            try
            {
                string dir = Arg("-wallShots") ?? Path.Combine("TestResults", "walls");
                string[] ids = (Arg("-wallLevels") ?? "level4,level12,level19").Split(',');
                bool legacy = Array.IndexOf(Environment.GetCommandLineArgs(), "-wallLegacy") >= 0;
                Directory.CreateDirectory(dir);
                foreach (string id in ids)
                {
                    if (legacy)
                    {
                        ShootLevel(dir, id, true);
                    }
                    ShootLevel(dir, id, false);
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[WallShots] threw: " + e);
                code = 1;
            }
            finally
            {
                LevelBuilder.CombineRenderers = true;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static void ShootLevel(string dir, string id, bool legacy)
        {
            LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, id + ".json")));
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            LevelBuilder.CombineRenderers = !legacy;
            LevelInstance level = LevelBuilder.Build(def);
            LevelBuilder.CombineRenderers = true;
            string tag = legacy ? "before" : "translucent";
            try
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
                var cam = new GameObject("ShotCamera").AddComponent<Camera>();
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.15f, 0.16f, 0.19f);
                cam.fieldOfView = 55f;
                cam.nearClipPlane = 0.05f;
                cam.farClipPlane = 80f;
                var fader = level.Root.GetComponent<WallFader>();
                // The first render of a fresh editor comes out tinted while the shaders warm up: throw one away.
                var warm = new RenderTexture(64, 64, 24);
                cam.targetTexture = warm;
                cam.Render();
                cam.targetTexture = null;
                UnityEngine.Object.DestroyImmediate(warm);

                Vector3 player = def.Player.Position;
                Vector3 focus = player + Vector3.up * 0.5f;
                string[] sides = { "back", "right", "front", "left" };
                for (int i = 0; i < sides.Length; i++)
                {
                    Quaternion orbit = Quaternion.Euler(48f, def.Player.Yaw + 90f * i, 0f);
                    Render(cam, level, fader, legacy, player, focus - orbit * Vector3.forward * 9f, orbit, Path.Combine(dir, $"{id}_high_{sides[i]}_{tag}.png"));
                }
                Quaternion near = Quaternion.Euler(Tuning.PitchDefault, def.Player.Yaw, 0f);
                Render(cam, level, fader, legacy, player, focus - near * Vector3.forward * Tuning.OrbitDistance * 1.3f, near,
                    Path.Combine(dir, $"{id}_start_{tag}.png"));
            }
            finally
            {
                LevelBuilder.Teardown(level);
            }
        }

        private static void Render(Camera cam, LevelInstance level, WallFader fader, bool legacy, Vector3 player, Vector3 position, Quaternion rotation,
            string file)
        {
            cam.transform.SetPositionAndRotation(position, rotation);
            fader.Apply(position);
            if (legacy)
            {
                Legacy(level, fader, position, player);
            }
            else
            {
                fader.DrawFaded(cam);
            }
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
            Debug.Log($"[WallShots] {file} (parts cut: {fader.HiddenCount})");
        }

        /// <summary>
        /// The old walls on a level built part by part: no floor under the walls, no fill, no closure, a faded wall not drawn;
        /// an outer wall's cap cut only when its plane separates the camera from the player; outer door frames and a shared
        /// line's windows never cut; a shared wall's baseboards cut with it.
        /// </summary>
        private static void Legacy(LevelInstance level, WallFader fader, Vector3 camera, Vector3 player)
        {
            foreach (MeshRenderer r in level.Root.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (r.name == "WallFloor" || r.name == "Fill")
                {
                    r.enabled = false;
                    continue;
                }
                Transform wall = r.transform.parent;
                if (wall == null || !wall.name.StartsWith("Wall ", StringComparison.Ordinal))
                {
                    continue;
                }
                bool separates = Vector3.Dot(camera - wall.position, wall.forward) * Vector3.Dot(player - wall.position, wall.forward) < 0f;
                MeshRenderer cap = null;
                float capHeight = float.MinValue;
                foreach (Transform child in wall)
                {
                    if (child.name == "Cap" && Mathf.Abs(child.localRotation.eulerAngles.x - 90f) < 1f)
                    {
                        cap = cap != null ? cap : child.GetComponent<MeshRenderer>();
                        capHeight = Mathf.Max(capHeight, child.localPosition.y);
                    }
                }
                bool outer = cap != null && fader.IsOuter(cap);
                if (r.name == "Cap")
                {
                    // The closures: an end quad (turned about y) or a cap over a crossing band (just under the line's cap).
                    bool end = Mathf.Abs(r.transform.localRotation.eulerAngles.x - 90f) >= 1f;
                    if (end || r.transform.localPosition.y < capHeight - 1e-3f)
                    {
                        r.enabled = false;
                        continue;
                    }
                    if (outer)
                    {
                        r.shadowCastingMode = separates ? ShadowCastingMode.ShadowsOnly : ShadowCastingMode.Off;
                    }
                }
                else if (outer && r.name.StartsWith("Door", StringComparison.Ordinal))
                {
                    r.shadowCastingMode = ShadowCastingMode.On;
                }
                else if (!outer && r.name == "Baseboards")
                {
                    r.shadowCastingMode = separates ? ShadowCastingMode.ShadowsOnly : ShadowCastingMode.Off;
                }
                else if (!outer && (r.name.StartsWith("Frame", StringComparison.Ordinal) || r.name == "Mullion" || r.name == "Transom"
                    || r.name == "WindowPane"))
                {
                    r.shadowCastingMode = ShadowCastingMode.Off;
                }
            }
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
