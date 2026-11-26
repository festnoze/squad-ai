using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// PLANT (2026-11-24): a look test of the two potted plants, the ficus and the banana plant, over the same two collider
    /// boxes. Shots go to Build/shots/plant (or OOS_SHOT_DIR) from the real runtime path (Boot scene, GameState.LoadLevel),
    /// paused: level12's salon plant rebuilt as a ficus with a banana plant beside it, each close, then both in frame. It asserts the gameplay footprint (the Pot and Leaves boxes are collider-only, at their
    /// old sizes), the three visual parts and the triangle budget. Run it alone: --filter PlantLook_.
    /// </summary>
    public sealed class ProbeTestsPlantLook
    {
        private const int Width = 1280;
        private const int Height = 720;
        private const string LevelId = "level12";
        private const string PlantName = "PlanteSalon";

        private static string ShotsDir
        {
            get
            {
                string dir = Environment.GetEnvironmentVariable("OOS_SHOT_DIR");
                return Path.GetFullPath(string.IsNullOrEmpty(dir) ? Path.Combine(Application.dataPath, "..", "Build", "shots", "plant") : dir);
            }
        }

        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            errors.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            SaveStore.ResetForTests();
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            yield return new WaitForFixedUpdate();
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            yield return null;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                errors.Add(condition);
            }
        }

        [UnityTest, Timeout(600000)]
        public IEnumerator PlantLook_FicusAndBanana()
        {
            Directory.CreateDirectory(ShotsDir);
            Game.LoadLevel(LevelId);
            Assert.AreEqual(LevelId, Game.LevelId, "premise: the level was loaded");
            Game.Paused = true;
            for (int i = 0; i < 3; i++)
            {
                yield return new WaitForFixedUpdate();
            }
            yield return null;

            PropDef prop = Game.Def.Props.FirstOrDefault(p => p.Name == PlantName);
            Assert.IsNotNull(prop, "premise: level12 has its salon plant");
            Assert.AreEqual("plant", prop.Kind, "premise: the salon plant is a plant");
            Transform salon = Game.Level.Root.transform.Find(prop.Name);
            Assert.IsNotNull(salon, "the plant prop was not built");
            // The level's own plant, as built, whatever style its position picked: the same two collider boxes.
            float potH = prop.SizeY * 0.3f;
            AssertColliderBox(salon, "Pot", new Vector3(0f, potH * 0.5f, 0f), new Vector3(prop.SizeX * 0.6f, potH, prop.SizeZ * 0.6f));
            AssertColliderBox(salon, "Leaves", new Vector3(0f, potH + (prop.SizeY - potH) * 0.5f, 0f), new Vector3(prop.SizeX, prop.SizeY - potH, prop.SizeZ));
            Assert.Contains(FurnitureKit.PlantStyleOf(new PropDef { Kind = "plant", X = 1f, Z = 2f }), PropDef.PlantStyles, "an unstyled plant picks a known style");
            Assert.AreEqual(PropDef.PlantStyleBanana, FurnitureKit.PlantStyleOf(new PropDef { Kind = "plant", Style = PropDef.PlantStyleBanana, X = 1f, Z = 2f }),
                "a level's own style wins");

            // One plant of each style side by side in the salon: the ficus in place of the salon plant, the banana beside it
            // (toward the open floor, away from the sofa).
            RoomDef room = Game.Def.RoomAt(salon.position);
            Vector3 toRoom = room != null ? new Vector3(room.X - salon.position.x, 0f, room.Z - salon.position.z) : Vector3.back;
            Vector3 side = toRoom.sqrMagnitude > 1e-4f ? toRoom.normalized : Vector3.back;
            Vector3 right = Vector3.Cross(Vector3.up, -side);
            Transform ficus = Rebuild(salon, prop, PropDef.PlantStyleFicus, salon.position);
            Transform banana = Rebuild(null, prop, PropDef.PlantStyleBanana, salon.position + right * 0.8f);
            yield return null;

            Vector3 lift = Vector3.up * (prop.SizeY * 0.55f);
            Shoot("ficus_close", ficus.position + side * 1.5f + Vector3.up * 1.15f, ficus.position + lift);
            Shoot("banana_close", banana.position + side * 1.5f + Vector3.up * 1.15f, banana.position + lift);
            Vector3 middle = (ficus.position + banana.position) * 0.5f;
            Shoot("both", middle + side * 2.4f + Vector3.up * 1.5f, middle + lift);

            // Asserted after the shots, so a failure still leaves the pictures to look at.
            AssertPlant(ficus, prop, PropDef.PlantStyleFicus);
            AssertPlant(banana, prop, PropDef.PlantStyleBanana);

            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>Builds <paramref name="prop"/> in <paramref name="style"/> at <paramref name="at"/>, under <paramref name="root"/> (emptied first) or a new object.</summary>
        private Transform Rebuild(Transform root, PropDef prop, string style, Vector3 at)
        {
            if (root == null)
            {
                root = new GameObject(prop.Name + " " + style).transform;
                root.SetParent(Game.Level.Root.transform, true);
                root.SetPositionAndRotation(at, Quaternion.Euler(0f, prop.Yaw, 0f));
            }
            for (int i = root.childCount - 1; i >= 0; i--)
            {
                Object.DestroyImmediate(root.GetChild(i).gameObject);
            }
            var styled = new PropDef
            {
                Name = prop.Name, Kind = prop.Kind, X = at.x, Z = at.z, Yaw = prop.Yaw, SizeX = prop.SizeX, SizeY = prop.SizeY, SizeZ = prop.SizeZ,
                Occluder = prop.Occluder, Color = prop.Color, AccentColor = prop.AccentColor, Style = style,
            };
            FurnitureKit.Build(styled, root, Game.Level.Root.transform.Find(prop.Name).gameObject.layer, true);
            return root;
        }

        /// <summary>The same two collider boxes for every style, the three visual parts, the budget, and each style's leaves.</summary>
        private static void AssertPlant(Transform plant, PropDef prop, string style)
        {
            float potH = prop.SizeY * 0.3f;
            AssertColliderBox(plant, "Pot", new Vector3(0f, potH * 0.5f, 0f), new Vector3(prop.SizeX * 0.6f, potH, prop.SizeZ * 0.6f));
            AssertColliderBox(plant, "Leaves", new Vector3(0f, potH + (prop.SizeY - potH) * 0.5f, 0f), new Vector3(prop.SizeX, prop.SizeY - potH, prop.SizeZ));
            Assert.AreEqual(2, plant.GetComponentsInChildren<Collider>(true).Length, $"{style}: the plant keeps exactly its two colliders");
            foreach (string part in new[] { "PotShape", "Trunk", "Canopy" })
            {
                Transform t = plant.Find(part);
                Assert.IsNotNull(t, $"{style}: the plant has no {part}");
                Assert.IsNotNull(t.GetComponent<MeshRenderer>(), $"{style}: the plant's {part} is not drawn");
                Assert.IsNull(t.GetComponent<Collider>(), $"{style}: the plant's {part} carries a collider");
            }
            int triangles = plant.GetComponentsInChildren<MeshFilter>(true).Sum(f => f.sharedMesh.triangles.Length / 3);
            Debug.Log($"[PlantLook] {style}: {triangles} triangles");
            Assert.LessOrEqual(triangles, Tuning.BudgetFurnitureTriangles, $"{style}: the plant's triangles");

            var block = new MaterialPropertyBlock();
            plant.Find("Canopy").GetComponent<MeshRenderer>().GetPropertyBlock(block, 0);
            Texture leaves = block.GetTexture("_BaseMap");
            Assert.AreEqual(Surface.Foliage, TextureLibrary.SurfaceOf(leaves), $"{style}: the canopy shows no foliage");
            if (style == PropDef.PlantStyleBanana)
            {
                Assert.IsNotNull(TextureLibrary.BananaLeafColour, "the banana leaf chart is imported");
                Assert.AreSame(TextureLibrary.BananaLeafColour, leaves, "the banana canopy uses the leaf chart");
                Assert.AreEqual(new Vector4(1f, 1f, 0f, 0f), block.GetVector("_BaseMap_ST"), "each blade uses the full chart once");
            }
            plant.Find("Trunk").GetComponent<MeshRenderer>().GetPropertyBlock(block, 0);
            Assert.AreEqual(Surface.Soil, TextureLibrary.SurfaceOf(block.GetTexture("_BaseMap")), $"{style}: the trunk and soil show no soil");
            plant.Find("PotShape").GetComponent<MeshRenderer>().GetPropertyBlock(block, 0);
            Assert.AreEqual(Surface.Plain, TextureLibrary.SurfaceOf(block.GetTexture("_BaseMap")), $"{style}: the glazed pot shows a grain");
            Color32 shown = PrimitiveKit.PaletteOf(plant.Find("PotShape").GetComponent<MeshRenderer>().sharedMaterial) ?? Color.clear;
            Color32 want = LevelJson.ParseColor(prop.AccentColor, Color.gray);
            Assert.That(Mathf.Abs(shown.r - want.r) + Mathf.Abs(shown.g - want.g) + Mathf.Abs(shown.b - want.b), Is.LessThanOrEqualTo(9), $"{style}: the pot is not in the pot colour");
        }
        private static void AssertColliderBox(Transform plant, string name, Vector3 centre, Vector3 size)
        {
            Transform t = plant.Find(name);
            Assert.IsNotNull(t, $"the plant has no {name} box");
            Assert.IsNotNull(t.GetComponent<BoxCollider>(), $"the plant's {name} box has no collider");
            Assert.IsNull(t.GetComponent<MeshRenderer>(), $"the plant's {name} box is drawn (it is collider-only)");
            Assert.That((t.localPosition - centre).magnitude, Is.LessThan(1e-4f), $"the plant's {name} box moved");
            Assert.That((t.localScale - size).magnitude, Is.LessThan(1e-4f), $"the plant's {name} box changed size");
        }

        /// <summary>Renders the game camera from <paramref name="eye"/> looking at <paramref name="at"/>, walls faded for that pose.</summary>
        private void Shoot(string name, Vector3 eye, Vector3 at)
        {
            Camera cam = main.Camera;
            Quaternion rotation = Quaternion.LookRotation(at - eye, Vector3.up);
            float aspect = cam.aspect;
            cam.aspect = Width / (float)Height;
            cam.transform.SetPositionAndRotation(eye, rotation);
            WallFader fader = Game.Level.Root.GetComponent<WallFader>();
            if (fader != null)
            {
                fader.Apply(eye);
                fader.DrawFaded(cam);
            }
            RenderTexture rt = RenderTexture.GetTemporary(Width, Height, 24);
            RenderPipeline.SubmitRenderRequest(cam, new RenderPipeline.StandardRequest { destination = rt });
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = rt;
            var texture = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
            texture.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
            texture.Apply();
            RenderTexture.active = previous;
            RenderTexture.ReleaseTemporary(rt);
            cam.aspect = aspect;
            File.WriteAllBytes(Path.Combine(ShotsDir, name + ".png"), texture.EncodeToPNG());
            Object.Destroy(texture);
            Game.Camera.Snap();
        }
    }
}
