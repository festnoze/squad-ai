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
    /// DOORFADE (docs/next/progress/DOORFADE.md): a look tool, not a check. Builds level8 (the red chair, the kitchen) and
    /// renders the gameplay orbit camera with the player just past a doorway, the wall fader applied for that camera:
    /// <list type="bullet">
    /// <item>&lt;name&gt;_before.png: the door parts drawn standing opaque over the faded wall (the old M9 doors rule,
    /// reproduced with plain copies of the frame and leaf renderers);</item>
    /// <item>&lt;name&gt;_after.png: the fader alone (DOORFADE: the door parts go with their wall).</item>
    /// </list>
    /// Scenes: an interior doorway without a leaf (salon to cuisine), an interior doorway with its leaf open (chambre to
    /// cuisine), the outer door of the salon seen from outside; both look, plus one lowered render.
    /// -executeMethod OutOfSight.Editor.DoorFadeShots.Shoot [-doorFadeShots &lt;dir&gt;]
    /// </summary>
    public static class DoorFadeShots
    {
        private static readonly string[] DoorParts = { "DoorFrame", "DoorPostA", "DoorPostB", "DoorHead", "DoorLeaf" };

        public static void Shoot()
        {
            int code = 0;
            try
            {
                string dir = Arg("-doorFadeShots") ?? Path.Combine("Build", "shots", "doorfade");
                Directory.CreateDirectory(dir);
                LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, "level8.json")));
                // In memory only: porte_cuisine stands open, as after the player went through it.
                foreach (OpeningDef d in def.Doors)
                {
                    if (d.Id == "porte_cuisine")
                    {
                        d.Leaf = OpeningDef.LeafOpen;
                    }
                }
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                LevelInstance level = LevelBuilder.Build(def);
                try
                {
                    // (name, player position, orbit yaw: the camera stands behind the player, on the side it came from)
                    var scenes = new List<(string name, Vector3 player, float yaw, WallLook look)>
                    {
                        ("salon_to_cuisine", new Vector3(3.85f, 0f, 1.75f), -90f, WallLook.Both),
                        ("salon_to_cuisine_lowered", new Vector3(3.85f, 0f, 1.75f), -90f, WallLook.Lowered),
                        ("chambre_to_cuisine_open_leaf", new Vector3(1.25f, 0f, 3.85f), 180f, WallLook.Both),
                        ("front_door_from_outside", new Vector3(9.3f, 0f, 1.25f), -90f, WallLook.Both),
                    };
                    ShootScenes(dir, level, scenes);
                }
                finally
                {
                    LevelBuilder.Teardown(level);
                    WallFader.LookOverride = null;
                    WallFader.OpacityOverride = null;
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[DoorFadeShots] threw: " + e);
                code = 1;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static void ShootScenes(string dir, LevelInstance level, List<(string name, Vector3 player, float yaw, WallLook look)> scenes)
        {
            Camera cam = Stage();
            cam.fieldOfView = 60f;
            var fader = level.Root.GetComponent<WallFader>();
            if (fader == null)
            {
                throw new InvalidOperationException("level8 has no wall fader");
            }
            var target = new GameObject("DoorFadeTarget").transform;
            var chair = GameObject.CreatePrimitive(PrimitiveType.Cube);
            Object.DestroyImmediate(chair.GetComponent<Collider>());
            chair.name = "PlayerMarker";
            chair.transform.localScale = new Vector3(0.45f, 0.9f, 0.45f);
            chair.GetComponent<MeshRenderer>().sharedMaterial = PrimitiveKit.Lit(new Color(0.84f, 0.15f, 0.24f), 0.3f);
            fader.Target = target;
            fader.Furniture = null;
            fader.View = cam;
            var parts = new List<Renderer>();
            foreach (MeshRenderer r in level.Root.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (Array.IndexOf(DoorParts, r.name) >= 0)
                {
                    parts.Add(r);
                }
            }
            foreach (DoorLeaf leaf in level.Leaves)
            {
                if (leaf != null && leaf.Renderer != null)
                {
                    parts.Add(leaf.Renderer);
                }
            }
            Debug.Log($"[DoorFadeShots] {parts.Count} door part renderers");
            try
            {
                foreach ((string name, Vector3 player, float yaw, WallLook look) in scenes)
                {
                    WallFader.LookOverride = look;
                    WallFader.OpacityOverride = Tuning.WallOpacityDefault / 100f;
                    target.position = player;
                    chair.transform.position = player + Vector3.up * 0.45f;
                    Vector3 focus = player + Vector3.up * Tuning.CameraTargetHeight;
                    Quaternion orbit = Quaternion.Euler(Tuning.PitchDefault, yaw, 0f);
                    Vector3 eye = focus - orbit * Vector3.forward * Tuning.OrbitDistance;
                    cam.transform.SetPositionAndRotation(eye, orbit);
                    fader.Apply(eye);
                    int moved = 0;
                    foreach (Renderer r in parts)
                    {
                        moved += fader.LevelOf(r) < 1f ? 1 : 0;
                    }
                    Debug.Log($"[DoorFadeShots] {name}: {fader.HiddenCount} parts out of the way, {moved} of them door parts");
                    // After: the fader alone.
                    fader.DrawFaded(cam);
                    Render(cam, Path.Combine(dir, name + "_after.png"), 1280, 800);
                    if (look != WallLook.Both)
                    {
                        continue;
                    }
                    // Before: the door parts out of the way drawn again standing opaque, as the M9 doors rule kept them.
                    var copies = new List<GameObject>();
                    foreach (Renderer r in parts)
                    {
                        if (fader.LevelOf(r) < 1f)
                        {
                            copies.Add(Copy(r));
                        }
                    }
                    fader.DrawFaded(cam);
                    Render(cam, Path.Combine(dir, name + "_before.png"), 1280, 800);
                    foreach (GameObject go in copies)
                    {
                        Object.DestroyImmediate(go);
                    }
                }
            }
            finally
            {
                Object.DestroyImmediate(target.gameObject);
                Object.DestroyImmediate(chair);
            }
        }

        /// <summary>A plain standing copy of a renderer (same mesh, materials, property block and pose), registered nowhere.</summary>
        private static GameObject Copy(Renderer source)
        {
            var go = new GameObject(source.name + " (before)");
            go.transform.SetPositionAndRotation(source.transform.position, source.transform.rotation);
            go.transform.localScale = source.transform.lossyScale;
            go.layer = source.gameObject.layer;
            go.AddComponent<MeshFilter>().sharedMesh = source.GetComponent<MeshFilter>().sharedMesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterials = source.sharedMaterials;
            r.shadowCastingMode = ShadowCastingMode.On;
            var block = new MaterialPropertyBlock();
            source.GetPropertyBlock(block, 0);
            if (!block.isEmpty)
            {
                r.SetPropertyBlock(block, 0);
            }
            return go;
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
            Debug.Log($"[DoorFadeShots] {file}");
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
