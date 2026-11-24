using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using OutOfSight.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using Object = UnityEngine.Object;

namespace OutOfSight.Editor
{
    /// <summary>
    /// CONECLIP (docs/next/progress/CONECLIP.md): a look tool, not a check. Builds level4 with the inhabitant seated on the
    /// salon sofa looking toward the buffet and the stool hidden behind it, then renders the gameplay orbit camera (and a view
    /// from above) with the old fan (&lt;name&gt;_before.png, VisionConeView.ClipShadows off) and the new one
    /// (&lt;name&gt;_after.png). It logs the vision test's verdict on the stool and, for every flat level, the stations where a
    /// low cover now cuts the fan.
    /// -executeMethod OutOfSight.Editor.ConeClipShots.Shoot [-coneClipShots &lt;dir&gt;]
    /// </summary>
    public static class ConeClipShots
    {
        private static readonly Vector3 StoolSpot = new Vector3(-0.4f, 0f, -1.05f);

        public static void Shoot()
        {
            int code = 0;
            try
            {
                string dir = Arg("-coneClipShots") ?? Path.Combine("Build", "shots", "coneclip");
                Directory.CreateDirectory(dir);
                ShootLevel4(dir);
                AuditLevels();
            }
            catch (Exception e)
            {
                Debug.LogError("[ConeClipShots] threw: " + e);
                code = 1;
            }
            finally
            {
                VisionConeView.ClipShadows = true;
                WallFader.LookOverride = null;
                WallFader.OpacityOverride = null;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static void ShootLevel4(string dir)
        {
            LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, "level4.json")));
            // In memory only: the inhabitant starts on the sofa, looking toward the buffet and the salon door, no glance.
            InhabitantDef man = def.Inhabitants[0];
            man.StartStation = 0;
            man.Stations[0].Facing = 120f;
            man.Stations[0].Dwell = 600f;
            man.Stations[0].Glances.Clear();
            man.Stations[0].GlanceEvery = null;
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            LevelInstance level = LevelBuilder.Build(def);
            try
            {
                Inhabitant inhabitant = level.Inhabitants[0];
                for (int i = 0; i < 150; i++)
                {
                    inhabitant.Step(0.02f);
                }
                typeof(Inhabitant).GetMethod("ApplyVisual", BindingFlags.NonPublic | BindingFlags.Instance)
                    ?.Invoke(inhabitant, new object[] { 1f });
                level.Furniture.transform.position = StoolSpot;
                Physics.SyncTransforms();
                Vision vision = level.Visions[0];
                bool seen = vision.Step(level.Furniture);
                var samples = new StringBuilder();
                for (int i = 0; i < vision.SampleVisible.Length; i++)
                {
                    samples.Append(vision.SampleVisible[i] ? '1' : '0');
                }
                Debug.Log($"[ConeClipShots] level4: eye {inhabitant.EyePosition} (visual {inhabitant.VisualEyePosition}, height {inhabitant.Routine.EyeHeight:0.00}), "
                    + $"eye yaw {inhabitant.VisualEyeYaw:0}, mode {inhabitant.Routine.Mode}; stool at {StoolSpot}: seen {seen}, samples {samples}");
                VisionConeView cone = level.Cones[0];
                Debug.Log($"[ConeClipShots] cone target {cone.TargetHeight:0.000}, radius {cone.TargetRadius:0.000}, range {cone.Range:0.0}, half {cone.HalfAngle:0}");

                Camera cam = Stage();
                cam.fieldOfView = 60f;
                var fader = level.Root.GetComponent<WallFader>();
                var target = new GameObject("ConeClipTarget").transform;
                target.position = StoolSpot;
                fader.Target = target;
                fader.Furniture = null;
                fader.View = cam;
                WallFader.LookOverride = WallLook.Both;
                WallFader.OpacityOverride = Tuning.WallOpacityDefault / 100f;
                var views = new List<(string name, float pitch, float yaw, float distance)>
                {
                    ("salon_orbit", Tuning.PitchDefault, -90f, Tuning.OrbitDistance),
                    ("salon_above", 80f, -90f, 7.5f),
                };
                foreach ((string name, float pitch, float yaw, float distance) in views)
                {
                    Vector3 focus = (name == "salon_above" ? new Vector3(-1.6f, 0f, -0.2f) : StoolSpot) + Vector3.up * Tuning.CameraTargetHeight;
                    Quaternion orbit = Quaternion.Euler(pitch, yaw, 0f);
                    Vector3 eye = focus - orbit * Vector3.forward * distance;
                    cam.transform.SetPositionAndRotation(eye, orbit);
                    fader.Apply(eye);
                    fader.DrawFaded(cam);
                    foreach (bool clip in new[] { false, true })
                    {
                        VisionConeView.ClipShadows = clip;
                        cone.Rebuild();
                        Render(cam, Path.Combine(dir, name + (clip ? "_after.png" : "_before.png")), 1280, 800);
                        if (name == "salon_orbit")
                        {
                            LogRays(cone, clip);
                        }
                    }
                }
                Object.DestroyImmediate(target.gameObject);
            }
            finally
            {
                LevelBuilder.Teardown(level);
            }
        }

        private static void LogRays(VisionConeView cone, bool clip)
        {
            var line = new StringBuilder($"[ConeClipShots] rays ({(clip ? "after" : "before")}): ");
            for (int i = 0; i < Tuning.ConeRayCount; i++)
            {
                line.Append($"{cone.ReachOf(i):0.00}{(cone.GapCount(i) > 0 ? "g" : "")} ");
            }
            Debug.Log(line.ToString());
        }

        /// <summary>
        /// Every flat level: from each station of each human, all around (5 degree steps), how many directions a low cover now
        /// cuts short (more than 0.3 m) or cuts a shadow out of, and which covers.
        /// </summary>
        private static void AuditLevels()
        {
            string[] files = Directory.GetFiles(LevelAudit.LevelsFolder, "level*.json");
            Array.Sort(files, StringComparer.Ordinal);
            foreach (string file in files)
            {
                if (!System.Text.RegularExpressions.Regex.IsMatch(Path.GetFileName(file), @"^level\d+\.json$"))
                {
                    continue;
                }
                LevelDef def = LevelJson.Parse(File.ReadAllText(file));
                if (def.Inhabitants == null || def.Inhabitants.Count == 0)
                {
                    continue;
                }
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                LevelInstance level = LevelBuilder.Build(def);
                try
                {
                    FloorMap floor = def.Floor ?? FloorMap.Flat;
                    if (!floor.IsFlat)
                    {
                        Debug.Log($"[ConeClipShots] audit {def.Id}: not flat, the fan is not clipped there");
                        continue;
                    }
                    for (int m = 0; m < level.Inhabitants.Count; m++)
                    {
                        Inhabitant inhabitant = level.Inhabitants[m];
                        VisionConeView cone = level.Cones[m];
                        float standing = inhabitant.Routine.EyeHeight;
                        InhabitantDef idef = def.Inhabitants[m];
                        for (int s = 0; s < idef.Stations.Count; s++)
                        {
                            StationDef st = idef.Stations[s];
                            float eyeHeight = string.IsNullOrEmpty(st.Sit) ? standing : Tuning.SitEyeHeight;
                            float floorY = floor.HeightAt(st.X, st.Z);
                            var eye = new Vector3(st.X, floorY + eyeHeight, st.Z);
                            int cut = 0;
                            int gaps = 0;
                            float worst = 0f;
                            var covers = new SortedSet<string>();
                            for (int a = 0; a < 360; a += 5)
                            {
                                Vector3 h = YawMath.Forward(a);
                                float before = cone.RayReach(eye, h, cone.Range, floor);
                                float after = cone.ShadowReach(eye, h, before, floorY, 0);
                                bool gap = cone.GapCount(0) > 0;
                                if (before - after > 0.3f || gap)
                                {
                                    cut += before - after > 0.3f ? 1 : 0;
                                    gaps += gap ? 1 : 0;
                                    worst = Mathf.Max(worst, before - after);
                                    string name = CoverName(level, eye, h, floorY + cone.TargetHeight, eye.y, before);
                                    if (name != null)
                                    {
                                        covers.Add(name);
                                    }
                                }
                            }
                            if (cut + gaps > 0)
                            {
                                Debug.Log($"[ConeClipShots] audit {def.Id} {idef.Name} station {s} (eye {eyeHeight:0.00}): {cut} directions cut (worst {worst:0.0} m), "
                                    + $"{gaps} with a shadow cut out; covers: {string.Join(", ", covers)}");
                            }
                        }
                    }
                }
                finally
                {
                    LevelBuilder.Teardown(level);
                }
            }
        }

        /// <summary>The first prop lower than the eye that a cast at the furniture top's height meets along the ray.</summary>
        private static string CoverName(LevelInstance level, Vector3 eye, Vector3 h, float height, float eyeY, float reach)
        {
            var origin = new Vector3(eye.x, height, eye.z);
            RaycastHit[] hits = Physics.RaycastAll(origin, h, reach, Layers.OccluderMask, QueryTriggerInteraction.Ignore);
            Array.Sort(hits, (x, y) => x.distance.CompareTo(y.distance));
            foreach (RaycastHit hit in hits)
            {
                if (hit.collider.bounds.max.y >= eyeY)
                {
                    continue;
                }
                Transform t = hit.collider.transform;
                while (t.parent != null && t.parent != level.Root.transform)
                {
                    t = t.parent;
                }
                return t.name;
            }
            return null;
        }

        private static Camera Stage()
        {
            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = new Color(1f, 0.87f, 0.67f);
            sun.intensity = 1.35f;
            sun.shadows = LightShadows.Soft;
            sun.shadowStrength = 0.78f;
            sun.transform.rotation = Quaternion.Euler(50f, 160f, 0f);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.58f, 0.63f, 0.73f);
            RenderSettings.ambientEquatorColor = new Color(0.52f, 0.47f, 0.42f);
            RenderSettings.ambientGroundColor = new Color(0.28f, 0.23f, 0.19f);
            var cam = new GameObject("ShotCamera").AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.45f, 0.62f, 0.38f);
            cam.nearClipPlane = 0.05f;
            cam.farClipPlane = 80f;
            // The first render of a fresh editor comes out tinted while the shaders warm up: throw one away.
            var warm = new RenderTexture(64, 64, 24);
            cam.targetTexture = warm;
            cam.Render();
            cam.targetTexture = null;
            Object.DestroyImmediate(warm);
            return cam;
        }

        private static void Render(Camera cam, string file, int width, int height)
        {
            var rt = new RenderTexture(width, height, 24) { antiAliasing = 4 };
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(width, height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
            tex.Apply();
            File.WriteAllBytes(file, tex.EncodeToPNG());
            RenderTexture.active = null;
            cam.targetTexture = null;
            Object.DestroyImmediate(rt);
            Object.DestroyImmediate(tex);
            Debug.Log($"[ConeClipShots] {file}");
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
