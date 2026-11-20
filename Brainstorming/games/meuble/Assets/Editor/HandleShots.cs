using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using OutOfSight.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight.Editor
{
    /// <summary>
    /// Door and cabinet handles: a look tool, not a check. Builds every level in an editor scene and writes, per level, its
    /// renderers, material slots and distinct materials (handles.txt), then renders close views of door leaves and of the
    /// procedural storage furniture (cabinet, wardrobe, counter, sink unit, washbasin, TV unit, nightstand, stove, bookshelf) to PNGs,
    /// under the game's sun and ambient (no post processing).
    /// -executeMethod OutOfSight.Editor.HandleShots.Shoot -handleShots &lt;dir&gt; [-handleLevels level1,level21] [-handleNoShots]
    /// </summary>
    public static class HandleShots
    {
        private static readonly string[] StorageKinds =
        {
            "cabinet", WardrobeRule.Kind, "counter", PropKinds.KitchenSink, PropKinds.Washbasin, PropKinds.TvUnit, PropKinds.Nightstand,
            PropKinds.Stove, PropKinds.Bookshelf,
        };

        public static void Shoot()
        {
            int code = 0;
            try
            {
                string dir = Arg("-handleShots") ?? Path.Combine("TestResults", "handles");
                Directory.CreateDirectory(dir);
                string only = Arg("-handleLevels");
                bool shots = !Environment.GetCommandLineArgs().Contains("-handleNoShots");
                IEnumerable<string> ids = only != null
                    ? only.Split(',')
                    : Enumerable.Range(1, 24).Select(i => "level" + i).Concat(new[] { "title_house" });
                var report = new StringBuilder();
                foreach (string id in ids)
                {
                    ShootLevel(dir, id, shots, report);
                }
                File.WriteAllText(Path.Combine(dir, "handles.txt"), report.ToString());
            }
            catch (Exception e)
            {
                Debug.LogError("[HandleShots] threw: " + e);
                code = 1;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static void ShootLevel(string dir, string id, bool shots, StringBuilder report)
        {
            LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, id + ".json")));
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            LevelInstance level = LevelBuilder.Build(def);
            try
            {
                Probe.RenderCount count = Probe.CountRenderers(UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None));
                var fader = level.Root.GetComponent<WallFader>();
                if (fader != null && fader.Count > 0)
                {
                    count.Materials.Add(WallFader.GhostMaterial);
                }
                bool house = def.AllRooms().Count >= Tuning.HouseBudgetRooms;
                report.AppendLine($"{id}: {count.Renderers} renderers, {count.MaterialSlots} slots of {(house ? Tuning.BudgetHouseRenderers : Tuning.BudgetRenderers)}, "
                    + $"{count.Materials.Count} materials of {(house ? Tuning.BudgetHouseMaterials : Tuning.BudgetMaterials)}, {level.Leaves.Count} leaves");
                report.AppendLine("    " + string.Join(", ", count.Materials.Select(m => m.name).OrderBy(n => n)));
                var kinds = def.Props.Where(p => Array.IndexOf(StorageKinds, p.Kind) >= 0).Select(p => p.Kind + (string.IsNullOrEmpty(p.Model) ? "" : "(m)"));
                report.AppendLine("    storage: " + string.Join(", ", kinds));
                if (Environment.GetCommandLineArgs().Contains("-handleSlots"))
                {
                    // The slots under each child of the level root, the largest first.
                    var rows = new List<string>();
                    foreach (Transform child in level.Root.transform)
                    {
                        int slots = ModelKit.SlotsUnder(child);
                        if (slots > 0)
                        {
                            rows.Add($"{slots,3} {child.name} [{string.Join(",", child.GetComponentsInChildren<Renderer>(false).Select(r => r.name + ":" + string.Join("+", r.sharedMaterials.Select(m => m != null ? m.name : "null"))))}]");
                        }
                    }
                    rows.Sort(StringComparer.Ordinal);
                    rows.Reverse();
                    foreach (string row in rows)
                    {
                        report.AppendLine("      " + row);
                    }
                }
                if (!shots)
                {
                    return;
                }
                Camera cam = Setup();
                foreach (DoorLeaf leaf in level.Leaves.Take(3))
                {
                    // Both faces of the leaf from the game camera's height and distance (Tuning.OrbitDistance and up), then
                    // close. Before any fader pass: the walls stand and the leaf is drawn whole, never as its see-through copy.
                    Vector3 center = leaf.transform.position;
                    Vector3 across = leaf.transform.forward;
                    foreach (float side in new[] { -1f, 1f })
                    {
                        string face = side < 0 ? "a" : "b";
                        Vector3 eye = center + across * (side * 3.2f) + leaf.transform.right * 0.8f + Vector3.up * 2.6f;
                        Render(cam, null, eye, Quaternion.LookRotation(center - eye), Path.Combine(dir, $"{id}_leaf_{leaf.Id}_{face}_game.png"));
                        eye = center + across * (side * 1.3f) + leaf.transform.right * 0.6f + Vector3.up * 0.6f;
                        Render(cam, null, eye, Quaternion.LookRotation(center - eye), Path.Combine(dir, $"{id}_leaf_{leaf.Id}_{face}_close.png"));
                    }
                }
                foreach (PropDef prop in def.Props)
                {
                    if (Array.IndexOf(StorageKinds, prop.Kind) < 0)
                    {
                        continue;
                    }
                    Quaternion turn = Quaternion.Euler(0f, prop.Yaw, 0f);
                    // The front of a wardrobe is +z (WardrobeRule.Front), every other storage piece's -z.
                    float front = prop.Kind == WardrobeRule.Kind ? 1f : -1f;
                    float d = Mathf.Max(prop.SizeX, Mathf.Max(prop.SizeY, prop.SizeZ)) * 1.1f + 0.7f;
                    Vector3 center = prop.Position + Vector3.up * (prop.SizeY * 0.45f);
                    Vector3 eye = center + turn * new Vector3(d * 0.35f, d * 0.75f, front * d);
                    Render(cam, fader, eye, Quaternion.LookRotation(center - eye), Path.Combine(dir, $"{id}_{prop.Kind}_{prop.Name}_close.png"));
                    // The game camera's view: about Tuning.OrbitDistance plus a metre away, some 50 degrees down.
                    eye = center + turn * new Vector3(0.8f, 3.4f, front * 2.9f);
                    Render(cam, fader, eye, Quaternion.LookRotation(center - eye), Path.Combine(dir, $"{id}_{prop.Kind}_{prop.Name}_game.png"));
                    var doors = level.Root.transform.Find(prop.Name)?.GetComponent<WardrobeDoors>();
                    if (doors != null)
                    {
                        // Mid swing (the doors wide open, WardrobeDoors' hold), as GameState plays it, then back at rest.
                        BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic;
                        doors.Begin(true, null);
                        typeof(WardrobeDoors).GetMethod("Apply", flags).Invoke(doors, new object[] { 0.5f });
                        eye = center + turn * new Vector3(d * 0.35f, d * 0.75f, front * d);
                        Render(cam, fader, eye, Quaternion.LookRotation(center - eye), Path.Combine(dir, $"{id}_{prop.Kind}_{prop.Name}_open.png"));
                        typeof(WardrobeDoors).GetMethod("Apply", flags).Invoke(doors, new object[] { 1f });
                        typeof(WardrobeDoors).GetMethod("EndAnimation", flags).Invoke(doors, null);
                    }
                }
            }
            finally
            {
                LevelBuilder.Teardown(level);
            }
        }

        private static Camera Setup()
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
            cam.fieldOfView = 50f;
            cam.nearClipPlane = 0.05f;
            cam.farClipPlane = 120f;
            // The first render of a fresh editor comes out tinted while the shaders warm up: throw one away.
            var warm = new RenderTexture(64, 64, 24);
            cam.targetTexture = warm;
            cam.Render();
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(warm);
            return cam;
        }

        private static void Render(Camera cam, WallFader fader, Vector3 position, Quaternion rotation, string file)
        {
            cam.transform.SetPositionAndRotation(position, rotation);
            if (fader != null)
            {
                fader.Apply(position);
                fader.DrawFaded(cam);
            }
            var rt = new RenderTexture(960, 640, 24) { antiAliasing = 4 };
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
