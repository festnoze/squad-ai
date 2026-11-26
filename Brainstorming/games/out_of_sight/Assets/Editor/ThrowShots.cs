using System;
using System.Collections.Generic;
using System.IO;
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
    /// THROWFIX (docs/next/progress/COHERENCE.md): a look tool, not a check. Builds levels whose sofas carry the throw and
    /// renders close shots of each throw on its sofa (Build/shots/throw/&lt;level&gt;_&lt;host&gt;_&lt;view&gt;.png): from the
    /// seat side, in profile, from behind (the sofa and its throw alone) and from the game camera (the whole level). It also
    /// logs the built backrest's measured top profile under the throw (a downward ray on the sofa's drawn meshes) and the
    /// throw's bounds in the sofa's frame. One extra shot set is a procedural sofa (level5's sofa without its model).
    /// -executeMethod OutOfSight.Editor.ThrowShots.Shoot [-throwShots &lt;dir&gt;]
    /// </summary>
    public static class ThrowShots
    {
        private static readonly string[] Levels = { "level5", "level8", "level11", "title_house", "level4", "level6" };

        public static void Shoot()
        {
            int code = 0;
            bool combine = LevelBuilder.CombineRenderers;
            try
            {
                string dir = Arg("-throwShots") ?? Path.Combine("Build", "shots", "throw");
                Directory.CreateDirectory(dir);
                ModelCatalogBuilder.Build();
                // Each decor item on its own renderer under its host: the close shots show the sofa and its throw alone.
                LevelBuilder.CombineRenderers = false;
                var report = new StringBuilder("[ThrowShots]\n");
                foreach (string id in Levels)
                {
                    ShootLevel(dir, id, false, report);
                }
                ShootLevel(dir, "level5", true, report);
                Debug.Log(report.ToString());
            }
            catch (Exception e)
            {
                Debug.LogError("[ThrowShots] threw: " + e);
                code = 1;
            }
            finally
            {
                LevelBuilder.CombineRenderers = combine;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static void ShootLevel(string dir, string id, bool procedural, StringBuilder report)
        {
            LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, id + ".json")));
            List<DecorDef> throws = def.Decor.FindAll(d => d != null && d.Kind == DecorKinds.SofaThrow);
            if (procedural)
            {
                // In memory only: the sofas draw their procedural visual.
                foreach (DecorDef d in throws)
                {
                    PropDef sofa = def.Props.Find(p => p != null && p.Name == d.Host);
                    if (sofa != null)
                    {
                        sofa.Model = null;
                    }
                }
            }
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            LevelInstance level = LevelBuilder.Build(def);
            try
            {
                Camera cam = Stage();
                string tag = id + (procedural ? "_procedural" : string.Empty);
                if (level.DressingProblems.Count > 0)
                {
                    report.Append($"  {tag}: dressing problems: {string.Join("; ", level.DressingProblems)}\n");
                }
                Transform root = level.Root.transform;
                foreach (DecorDef d in throws)
                {
                    PropDef sofa = def.Props.Find(p => p != null && p.Name == d.Host);
                    Transform host = root.Find(d.Host);
                    if (sofa == null || host == null)
                    {
                        report.Append($"  {tag}: no host {d.Host}\n");
                        continue;
                    }
                    Measure(tag, level, sofa, host, d, report);
                    LevelBuilder.SofaBackrest(sofa, host, out float centre, out float depth, out float top);
                    report.Append($"    backrest used: centre z {centre:0.000}, thickness {depth:0.000}, top {top:0.000}\n");
                    var target = new Vector3(d.X, top, centre);
                    string stem = Path.Combine(dir, tag + "_" + d.Host);
                    var hidden = new List<Renderer>();
                    foreach (Renderer r in root.GetComponentsInChildren<Renderer>())
                    {
                        if (r.enabled && !r.transform.IsChildOf(host))
                        {
                            r.enabled = false;
                            hidden.Add(r);
                        }
                    }
                    Close(cam, host, target, new Vector3(0.25f, 0.55f, -1.4f), stem + "_seat.png");
                    Close(cam, host, target, new Vector3(1.5f, 0.3f, 0f), stem + "_profile.png");
                    Close(cam, host, target, new Vector3(0.4f, 0.45f, 1.4f), stem + "_back.png");
                    foreach (Renderer r in hidden)
                    {
                        r.enabled = true;
                    }
                    // The game's view: the orbit camera looking at the sofa from its seat side, over the throw.
                    var fader = level.Root.GetComponent<WallFader>();
                    cam.fieldOfView = 60f;
                    Quaternion orbit = Quaternion.Euler(Tuning.PitchDefault, host.eulerAngles.y + 20f, 0f);
                    Vector3 focus = host.TransformPoint(target);
                    Vector3 eye = focus - orbit * Vector3.forward * Tuning.OrbitDistance * 0.6f;
                    cam.transform.SetPositionAndRotation(eye, orbit);
                    if (fader != null)
                    {
                        fader.Apply(eye);
                        fader.DrawFaded(cam);
                    }
                    Render(cam, stem + "_game.png", 1100, 760);
                    cam.fieldOfView = 35f;
                }
            }
            finally
            {
                LevelBuilder.Teardown(level);
            }
        }

        /// <summary>
        /// Logs, in the sofa's frame, the top of its drawn meshes under the throw (rays straight down every 2.5 cm across its
        /// depth, at the throw's x) and the throw's own bounds.
        /// </summary>
        private static void Measure(string tag, LevelInstance level, PropDef sofa, Transform host, DecorDef d, StringBuilder report)
        {
            var temp = new List<MeshCollider>();
            foreach (MeshFilter f in host.GetComponentsInChildren<MeshFilter>())
            {
                if (f.sharedMesh == null || f.name.StartsWith(LevelBuilder.DecorPrefix, StringComparison.Ordinal))
                {
                    continue;
                }
                var c = f.gameObject.AddComponent<MeshCollider>();
                c.sharedMesh = f.sharedMesh;
                temp.Add(c);
            }
            Physics.SyncTransforms();
            var profile = new StringBuilder();
            float half = sofa.SizeZ * 0.5f;
            for (float z = -half; z <= half + 1e-4f; z += 0.025f)
            {
                Vector3 from = host.TransformPoint(new Vector3(d.X, sofa.SizeY + 1f, z));
                float top = float.NaN;
                foreach (RaycastHit hit in Physics.RaycastAll(from, Vector3.down, 3f))
                {
                    if (hit.collider is MeshCollider mc && temp.Contains(mc))
                    {
                        float y = host.InverseTransformPoint(hit.point).y;
                        top = float.IsNaN(top) ? y : Mathf.Max(top, y);
                    }
                }
                profile.Append($" {z:0.000}:{top:0.000}");
            }
            foreach (MeshCollider c in temp)
            {
                Object.DestroyImmediate(c);
            }
            report.Append($"  {tag} {d.Host} (model {sofa.Model ?? "none"}, size {sofa.Size.ToString("0.00")}, yaw {sofa.Yaw}, throw yaw {d.Yaw}):\n");
            report.Append($"    top profile z:y{profile}\n");
            foreach (DressingPlacement p in level.Dressing)
            {
                if (p.Id != DecorKinds.SofaThrow || p.Host != d.Host)
                {
                    continue;
                }
                Transform root = level.Root.transform;
                Vector3 a = host.InverseTransformPoint(root.TransformPoint(p.Bounds.min));
                Vector3 b = host.InverseTransformPoint(root.TransformPoint(p.Bounds.max));
                report.Append($"    throw bounds in the sofa frame: {Vector3.Min(a, b).ToString("0.000")} .. {Vector3.Max(a, b).ToString("0.000")}, host top {p.HostTop:0.000}\n");
            }
        }

        private static void Close(Camera cam, Transform host, Vector3 localTarget, Vector3 localOffset, string file)
        {
            Vector3 target = host.TransformPoint(localTarget);
            Vector3 eye = host.TransformPoint(localTarget + localOffset);
            cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(target - eye));
            Render(cam, file, 900, 700);
        }

        private static Camera Stage()
        {
            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = new Color(1f, 0.92f, 0.8f);
            sun.intensity = 1.2f;
            sun.shadows = LightShadows.Soft;
            sun.transform.rotation = Quaternion.Euler(55f, 140f, 0f);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.58f, 0.63f, 0.73f);
            RenderSettings.ambientEquatorColor = new Color(0.52f, 0.47f, 0.42f);
            RenderSettings.ambientGroundColor = new Color(0.28f, 0.23f, 0.19f);
            var cam = new GameObject("ShotCamera").AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.20f, 0.21f, 0.24f);
            cam.fieldOfView = 35f;
            cam.nearClipPlane = 0.02f;
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
