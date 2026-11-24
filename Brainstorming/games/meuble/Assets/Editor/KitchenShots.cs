using System;
using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using Object = UnityEngine.Object;

namespace OutOfSight.Editor
{
    /// <summary>
    /// KITCHEN (docs/next/progress/KITCHEN.md): a look tool, not a check. Rebuilds the texture arrays and the dressing library
    /// (ModelCatalogBuilder.Build), then renders, with the wall material exactly as the game draws them:
    /// <list type="bullet">
    /// <item>each of the ten kitchen meshes alone (Build/kitchen/preview/&lt;id&gt;.png);</item>
    /// <item>the set: the five modules in one run with the five utensils on them (kitchen_set.png);</item>
    /// <item>the test_rooms kitchen dressed in memory (its sink, stove and counter wear the looks, utensils as decor), from the
    /// game camera and from above (kitchen_ingame*.png). No level file is written.</item>
    /// </list>
    /// -executeMethod OutOfSight.Editor.KitchenShots.Shoot [-kitchenShots &lt;dir&gt;]
    /// </summary>
    public static class KitchenShots
    {
        private static readonly string[] Ids =
        {
            DecorKinds.KitchenBaseCabinet, DecorKinds.KitchenDrawerCabinet, DecorKinds.KitchenSinkCabinet, DecorKinds.KitchenRange,
            DecorKinds.KitchenTallCabinet, DecorKinds.Saucepan, DecorKinds.FryingPan, DecorKinds.StockPot, DecorKinds.Kettle,
            DecorKinds.CuttingBoard,
        };

        public static void Shoot()
        {
            int code = 0;
            try
            {
                string dir = Arg("-kitchenShots") ?? Path.Combine("Build", "kitchen", "preview");
                Directory.CreateDirectory(dir);
                ModelCatalogBuilder.Build();
                DressingLibrary library = DressingLibrary.Load();
                Material material = WallArray.Material;
                if (library == null || material == null)
                {
                    throw new InvalidOperationException("no dressing library or no wall material after ModelCatalogBuilder.Build");
                }
                var report = new System.Text.StringBuilder("[KitchenShots]\n");
                foreach (string id in Ids)
                {
                    DressingLibrary.Entry e = library.Find(id);
                    report.Append(e == null ? $"  {id}: NOT BAKED\n" : $"  {id}: {e.triangles} triangles, size {e.Size.ToString("0.###")}\n");
                }
                Debug.Log(report.ToString());
                ShootItems(dir, library, material);
                ShootSet(dir, library, material);
                ShootLevel(dir);
            }
            catch (Exception e)
            {
                Debug.LogError("[KitchenShots] threw: " + e);
                code = 1;
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
            sun.transform.rotation = Quaternion.Euler(50f, 160f, 0f);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.58f, 0.63f, 0.73f);
            RenderSettings.ambientEquatorColor = new Color(0.52f, 0.47f, 0.42f);
            RenderSettings.ambientGroundColor = new Color(0.28f, 0.23f, 0.19f);
            var cam = new GameObject("ShotCamera").AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.20f, 0.21f, 0.24f);
            cam.fieldOfView = 35f;
            cam.nearClipPlane = 0.02f;
            cam.farClipPlane = 60f;
            // The first render of a fresh editor comes out tinted while the shaders warm up: throw one away.
            var warm = new RenderTexture(64, 64, 24);
            cam.targetTexture = warm;
            cam.Render();
            cam.targetTexture = null;
            Object.DestroyImmediate(warm);
            return cam;
        }

        private static GameObject Place(DressingLibrary.Entry e, Material material, Vector3 position, float yaw)
        {
            var go = new GameObject(e.id);
            go.transform.SetPositionAndRotation(position, Quaternion.Euler(0f, yaw, 0f));
            go.AddComponent<MeshFilter>().sharedMesh = e.mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = material;
            r.shadowCastingMode = ShadowCastingMode.On;
            return go;
        }

        /// <summary>A camera in front (+z, the meshes' fronts), to the right and above, framing <paramref name="bounds"/>.</summary>
        private static void Frame(Camera cam, Bounds bounds, Vector3 direction, float margin)
        {
            float radius = bounds.extents.magnitude;
            float distance = radius * margin / Mathf.Sin(cam.fieldOfView * 0.5f * Mathf.Deg2Rad);
            Vector3 eye = bounds.center + direction.normalized * distance;
            cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(bounds.center - eye));
        }

        private static void ShootItems(string dir, DressingLibrary library, Material material)
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Camera cam = Stage();
            foreach (string id in Ids)
            {
                DressingLibrary.Entry e = library.Find(id);
                if (e == null)
                {
                    continue;
                }
                GameObject go = Place(e, material, Vector3.zero, 0f);
                var bounds = new Bounds((e.boundsMin + e.boundsMax) * 0.5f, e.Size);
                Frame(cam, bounds, new Vector3(0.55f, 0.75f, 1f), 1.05f);
                Render(cam, Path.Combine(dir, id + ".png"), 900, 900);
                Object.DestroyImmediate(go);
            }
        }

        private static void ShootSet(string dir, DressingLibrary library, Material material)
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Camera cam = Stage();
            string[] run = { DecorKinds.KitchenTallCabinet, DecorKinds.KitchenDrawerCabinet, DecorKinds.KitchenSinkCabinet, DecorKinds.KitchenRange, DecorKinds.KitchenBaseCabinet };
            var centres = new Dictionary<string, float>();
            float total = 0f;
            foreach (string id in run)
            {
                total += library.Find(id).Size.x;
            }
            float at = -total * 0.5f;
            var all = new Bounds(Vector3.zero, Vector3.zero);
            foreach (string id in run)
            {
                DressingLibrary.Entry e = library.Find(id);
                float centre = at + e.Size.x * 0.5f;
                at += e.Size.x;
                centres[id] = centre;
                Place(e, material, new Vector3(centre - (e.boundsMin.x + e.boundsMax.x) * 0.5f, 0f, 0f), 0f);
                all.Encapsulate(new Bounds(new Vector3(centre, e.Size.y * 0.5f, 0f), e.Size));
            }
            // The utensils on the worktops and the hob (the mesh fronts face +z; the pan handles point to -x).
            float top = 0.9f;
            float range = centres[DecorKinds.KitchenRange];
            Place(library.Find(DecorKinds.FryingPan), material, new Vector3(range + 0.03f, top, 0.13f), 0f);
            Place(library.Find(DecorKinds.StockPot), material, new Vector3(range - 0.145f, top, -0.14f), 0f);
            Place(library.Find(DecorKinds.Saucepan), material, new Vector3(range + 0.15f, top, -0.14f), 180f);
            Place(library.Find(DecorKinds.CuttingBoard), material, new Vector3(centres[DecorKinds.KitchenDrawerCabinet], top, 0.05f), -8f);
            Place(library.Find(DecorKinds.Kettle), material, new Vector3(centres[DecorKinds.KitchenBaseCabinet] + 0.05f, top, -0.05f), 0f);
            Frame(cam, all, new Vector3(0.35f, 0.9f, 1f), 0.9f);
            Render(cam, Path.Combine(dir, "kitchen_set.png"), 1600, 1000);
            // The game's view: from above, as the cutaway camera sees a kitchen.
            Frame(cam, all, new Vector3(0f, 1.6f, 1f), 0.85f);
            Render(cam, Path.Combine(dir, "kitchen_set_top.png"), 1600, 1000);
        }

        private static void ShootLevel(string dir)
        {
            LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, "test_rooms.json")));
            // In memory only: the coordinator writes the real placements into the level files.
            PropDef sink = def.Props.Find(p => p.Kind == PropKinds.KitchenSink);
            PropDef stove = def.Props.Find(p => p.Kind == PropKinds.Stove);
            PropDef counter = def.Props.Find(p => p.Kind == PropKinds.Counter);
            if (sink == null || stove == null || counter == null)
            {
                throw new InvalidOperationException("test_rooms has no sink, stove or counter");
            }
            sink.Dress = DecorKinds.KitchenSinkCabinet;
            stove.Dress = DecorKinds.KitchenRange;
            counter.Dress = DecorKinds.KitchenBaseCabinet;
            def.Decor = new List<DecorDef>
            {
                new DecorDef { Kind = DecorKinds.FryingPan, Host = stove.Name, X = 0.14f, Z = -0.13f, Yaw = 0f },
                new DecorDef { Kind = DecorKinds.Kettle, Host = stove.Name, X = -0.14f, Z = 0.14f, Yaw = 180f },
                new DecorDef { Kind = DecorKinds.CuttingBoard, Host = counter.Name, X = -0.2f, Z = -0.07f, Yaw = 0f },
                new DecorDef { Kind = DecorKinds.StockPot, Host = counter.Name, X = 0.25f, Z = 0.04f, Yaw = 0f },
            };
            var issues = new List<string>();
            foreach (string issue in LevelValidator.Validate(def))
            {
                if (issue.Contains("decor") || issue.Contains("dress") || issue.Contains("look"))
                {
                    issues.Add(issue);
                }
            }
            Debug.Log("[KitchenShots] validator on the dressed test_rooms: " + (issues.Count == 0 ? "no dressing issue" : string.Join("; ", issues)));

            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            LevelInstance level = LevelBuilder.Build(def);
            try
            {
                Debug.Log($"[KitchenShots] test_rooms dressing: {level.Dressing.Count} placements, problems: {string.Join("; ", level.DressingProblems)}");
                Camera cam = Stage();
                cam.fieldOfView = 60f;
                var fader = level.Root.GetComponent<WallFader>();
                Vector3 target = stove.Position + Vector3.up * Tuning.CameraTargetHeight + new Vector3(-0.4f, 0f, 0f);
                foreach ((float pitch, float yaw, string name) in new[] { (Tuning.PitchDefault, 15f, "kitchen_ingame.png"), (70f, 0f, "kitchen_ingame_top.png") })
                {
                    // The prop fronts face -z: the camera looks toward +z from the room side.
                    Quaternion orbit = Quaternion.Euler(pitch, yaw, 0f);
                    Vector3 eye = target - orbit * Vector3.forward * Tuning.OrbitDistance;
                    cam.transform.SetPositionAndRotation(eye, orbit);
                    if (fader != null)
                    {
                        fader.Apply(eye);
                        fader.DrawFaded(cam);
                    }
                    Render(cam, Path.Combine(dir, name), 1280, 800);
                }
            }
            finally
            {
                LevelBuilder.Teardown(level);
            }
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
            Debug.Log($"[KitchenShots] {file}");
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
