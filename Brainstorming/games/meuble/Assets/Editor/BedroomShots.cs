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
    /// BEDROOM (docs/next/progress/BEDROOM.md): a look tool, not a check. Rebuilds the catalogs (wall arrays and dressing
    /// library, ModelCatalogBuilder.Build), then renders the bedroom pack's baked meshes with the game's wall material on a
    /// plain floor: one overview (a bedside vignette and the floor items, from a game-like high angle) and one close view per
    /// item, into Build/bedroom/preview/unity_*.png.
    /// -executeMethod OutOfSight.Editor.BedroomShots.Shoot
    /// </summary>
    public static class BedroomShots
    {
        private const string Folder = "Build/bedroom/preview";

        private static readonly string[] Ids =
        {
            DecorKinds.BedsideTable, DecorKinds.BedsideLamp, DecorKinds.AlarmClock, DecorKinds.ClothesHeap, DecorKinds.OddSocks,
            DecorKinds.Slippers, DecorKinds.LaundryBasket, DecorKinds.FloorBookStack, DecorKinds.TeddyBear,
        };

        public static void Shoot()
        {
            int code = 0;
            try
            {
                ModelCatalogBuilder.Build();
                AssetDatabase.SaveAssets();
                Directory.CreateDirectory(Folder);
                Render();
            }
            catch (Exception e)
            {
                Debug.LogError("[BedroomShots] threw: " + e);
                code = 1;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static void Render()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Material wall = WallArray.Material;
            if (wall == null || DressingLibrary.Load() == null)
            {
                throw new InvalidOperationException("no wall material or dressing library");
            }
            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = new Color(1f, 0.9f, 0.76f);
            sun.intensity = 1.25f;
            sun.shadows = LightShadows.Soft;
            sun.transform.rotation = Quaternion.Euler(55f, 160f, 0f);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.58f, 0.63f, 0.73f);
            RenderSettings.ambientEquatorColor = new Color(0.52f, 0.47f, 0.42f);
            RenderSettings.ambientGroundColor = new Color(0.28f, 0.23f, 0.19f);

            GameObject floor = GameObject.CreatePrimitive(PrimitiveType.Quad);
            floor.transform.SetPositionAndRotation(new Vector3(0.6f, 0f, 0.2f), Quaternion.Euler(90f, 0f, 0f));
            floor.transform.localScale = new Vector3(5f, 4f, 1f);
            var floorMaterial = new Material(Shader.Find("Universal Render Pipeline/Lit")) { color = new Color(0.62f, 0.5f, 0.38f) };
            floor.GetComponent<MeshRenderer>().sharedMaterial = floorMaterial;

            // The vignette: the bedside table (front +z here), the lamp toward the bed side and the clock on its top, the
            // teddy against it; the floor items in a row in front.
            Place(DecorKinds.BedsideTable, new Vector3(0f, 0f, -0.4f), 0f, wall);
            Place(DecorKinds.BedsideLamp, new Vector3(-0.09f, 0.55f, -0.43f), 0f, wall);
            Place(DecorKinds.AlarmClock, new Vector3(0.14f, 0.55f, -0.36f), -20f, wall);
            Place(DecorKinds.TeddyBear, new Vector3(0.42f, 0f, -0.45f), -15f, wall);
            Place(DecorKinds.LaundryBasket, new Vector3(1.0f, 0f, -0.45f), 0f, wall);
            Place(DecorKinds.ClothesHeap, new Vector3(-0.2f, 0f, 0.45f), 10f, wall);
            Place(DecorKinds.Slippers, new Vector3(0.55f, 0f, 0.35f), 0f, wall);
            Place(DecorKinds.OddSocks, new Vector3(0.95f, 0f, 0.4f), 30f, wall);
            Place(DecorKinds.FloorBookStack, new Vector3(1.35f, 0f, 0.05f), 15f, wall);

            var cam = new GameObject("ShotCamera").AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.15f, 0.16f, 0.19f);
            cam.fieldOfView = 40f;
            cam.nearClipPlane = 0.02f;
            cam.farClipPlane = 40f;
            var warm = new RenderTexture(64, 64, 24);
            cam.targetTexture = warm;
            cam.Render();
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(warm);

            var centre = new Vector3(0.55f, 0.1f, 0.0f);
            Shot(cam, centre + Quaternion.Euler(55f, 180f, 0f) * Vector3.back * 3.4f, centre, "unity_bedroom_set.png");
            Shot(cam, centre + new Vector3(0f, 2.7f, 0.5f), centre, "unity_bedroom_top.png");
            // One close view per item, alone at the origin (the vignette moved far away).
            foreach (Transform child in UnityEngine.Object.FindObjectsByType<Transform>(FindObjectsSortMode.None))
            {
                if (child.name.StartsWith("Bedroom ", StringComparison.Ordinal))
                {
                    child.position += new Vector3(50f, 0f, 0f);
                }
            }
            foreach (string id in Ids)
            {
                GameObject go = Place(id, Vector3.zero, 0f, wall);
                DressingLibrary.Entry entry = DressingLibrary.Lookup(id);
                Vector3 size = entry.boundsMax - entry.boundsMin;
                Vector3 look = (entry.boundsMin + entry.boundsMax) * 0.5f;
                float d = Mathf.Max(size.x, Mathf.Max(size.y, size.z)) * 1.9f + 0.15f;
                Shot(cam, look + Quaternion.Euler(32f, 210f, 0f) * Vector3.back * d, look, $"unity_{id}.png");
                Debug.Log($"[BedroomShots] {id}: {entry.triangles} triangles, bounds {entry.boundsMin.ToString("0.###")} to {entry.boundsMax.ToString("0.###")}");
                UnityEngine.Object.DestroyImmediate(go);
            }
        }

        private static GameObject Place(string id, Vector3 position, float yaw, Material material)
        {
            DressingLibrary.Entry entry = DressingLibrary.Lookup(id);
            if (entry == null || entry.mesh == null)
            {
                throw new InvalidOperationException("dressing library has no " + id);
            }
            var go = new GameObject("Bedroom " + id);
            go.transform.SetPositionAndRotation(position, Quaternion.Euler(0f, yaw, 0f));
            go.AddComponent<MeshFilter>().sharedMesh = entry.mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = ShadowCastingMode.On;
            return go;
        }

        private static void Shot(Camera cam, Vector3 eye, Vector3 target, string file)
        {
            cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(target - eye));
            var rt = new RenderTexture(1280, 800, 24) { antiAliasing = 4 };
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
            tex.Apply();
            File.WriteAllBytes(Path.Combine(Folder, file), tex.EncodeToPNG());
            RenderTexture.active = null;
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(rt);
            UnityEngine.Object.DestroyImmediate(tex);
        }
    }
}
