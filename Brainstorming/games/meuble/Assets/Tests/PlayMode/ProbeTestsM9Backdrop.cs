using System.Collections;
using System.Collections.Generic;
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
    /// Garden backdrop (product owner image of 2026-11-19, GardenBackdrop, docs/m9/backdrop/NOTES.md): every level and the
    /// title house stand in a ring showing the owner's garden on its inside. The camera stays inside the ring and below its
    /// top at every zoom, orbit and focus the level allows, the far clip holds it, the picture keeps its aspect, and the
    /// ring blocks nothing (no collider, a layer no gameplay mask holds, no shadow, no new material). Shots under
    /// docs/m9/backdrop/.
    /// </summary>
    public sealed class ProbeTestsM9Backdrop
    {
        /// <summary>The prefix of the shots (one per look iteration, see NOTES.md).</summary>
        private const string ShotPrefix = "v4";

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private GameState Game => main.Game;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            LevelBuilder.CombineRenderers = true;
            TextureLibrary.Disabled = false;
            InputReader.ResetInjections();
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
            yield return Frames(3);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            Application.logMessageReceived -= OnLog;
            yield return null;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        private static IEnumerator Frames(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return null;
            }
        }

        private IEnumerator Load(string id)
        {
            Game.LoadLevel(id);
            Assert.AreEqual(id, Game.Def.Id, "premise: the level loaded");
            for (int i = 0; i < Game.Level.Inhabitants.Count; i++)
            {
                Game.Level.Inhabitants[i].Pin(new Vector3(90f + 5f * i, 0f, 90f), 0f);
            }
            yield return Frames(3);
        }

        private List<string> AllLevels()
        {
            var ids = Game.LevelOrder.ToList();
            if (LevelLoader.Load(TitleCameraTour.LevelId) != null)
            {
                ids.Add(TitleCameraTour.LevelId);
            }
            return ids;
        }

        private MeshRenderer Backdrop()
        {
            return Game.Level.Root.GetComponentsInChildren<MeshRenderer>(true).FirstOrDefault(r => r.name == GardenBackdrop.RendererName);
        }

        /// <summary>
        /// Step 95a: on every level (and the title house), for a focus at every corner of the interior, on the exit and at
        /// the highest floor, at every yaw (15 degree steps), the lowest, default and highest pitch and the longest zoom,
        /// the unclamped camera stands inside the ring's camera space (so the fence never moves the camera in play), at
        /// least the clearance inside the ring and below its top; the picture keeps its aspect; a zoom far beyond the
        /// level's bound is fenced back inside.
        /// </summary>
        [UnityTest]
        public IEnumerator Step95a_EveryCameraPoseStaysInsideTheRing()
        {
            var table = new List<string>();
            int poses = 0;
            foreach (string id in AllLevels())
            {
                LevelDef def = LevelLoader.Load(id);
                Assert.IsNotNull(def, $"{id}: premise: the level parses");
                GardenBackdrop.Ring ring = GardenBackdrop.RingFor(def);
                float circumference = 2f * Mathf.PI * ring.Radius;
                Assert.That(ring.Height * GardenBackdrop.ImageAspect * ring.Repeats, Is.EqualTo(circumference).Within(1e-3f),
                    $"{id}: the picture is stretched ({ring.Repeats} repeats of {ring.Height:0.00} m on {circumference:0.0} m)");
                Assert.Greater(ring.Top, ring.CameraTop, $"{id}: the camera may look over the ring");
                Assert.Less(ring.CameraRadius, ring.Radius - 1f, $"{id}: the camera fence lies on the ring");
                float arm = OrbitCamera.MaxDistanceFor(def);
                float top = GardenBackdrop.FocusTop(def);
                Rect interior = def.InteriorBounds();
                var foci = new List<Vector3>
                {
                    new Vector3(interior.xMin, top, interior.yMin), new Vector3(interior.xMax, top, interior.yMin),
                    new Vector3(interior.xMin, top, interior.yMax), new Vector3(interior.xMax, top, interior.yMax),
                };
                if (def.Exit != null)
                {
                    foci.Add(new Vector3(def.Exit.X, top, def.Exit.Z));
                }
                float worst = float.MaxValue;
                foreach (Vector3 focus in foci)
                {
                    for (int yaw = 0; yaw < 360; yaw += 15)
                    {
                        foreach (float pitch in new[] { Tuning.PitchMin, Tuning.PitchDefault, Tuning.PitchMax })
                        {
                            Vector3 back = Quaternion.Euler(pitch, yaw, 0f) * Vector3.back;
                            Vector3 eye = focus + back * arm;
                            Assert.IsTrue(ring.HoldsCamera(eye), $"{id}: focus {focus}, yaw {yaw}, pitch {pitch}: the camera at {eye} leaves the ring");
                            Assert.AreEqual(arm, GardenBackdrop.ClampArm(ring, focus, back, arm), 1e-4f, $"{id}: the fence moves the camera in play");
                            float gap = ring.Radius - new Vector2(eye.x - ring.Center.x, eye.z - ring.Center.z).magnitude;
                            worst = Mathf.Min(worst, gap);
                            // A zoom far beyond the level's bound is fenced back inside.
                            float fenced = GardenBackdrop.ClampArm(ring, focus, back, 200f);
                            Assert.IsTrue(ring.HoldsCamera(focus + back * fenced), $"{id}: the fence lets a long zoom out");
                            poses++;
                        }
                    }
                }
                Assert.GreaterOrEqual(worst, GardenBackdrop.CameraClearance, $"{id}: the camera comes within {worst:0.00} m of the ring");
                table.Add($"{id}: R {ring.Radius:0.0} H {ring.Height:0.0} x{ring.Repeats} gap {worst:0.0} far {ring.FarClip:0}");
            }
            Debug.Log($"[Step95a] {poses} poses | " + string.Join(" | ", table));
            TestContext.WriteLine("[Step95a] " + string.Join(" | ", table));
            yield return null;
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Step 95b: on a small level, a house, the largest one and the title house, the built ring: one renderer of one
        /// slot, drawn with the windows' material (no new material), the picture through its block, no collider, the
        /// Default layer (no gameplay mask), no shadow; the real game camera at its longest zoom, at every yaw and the
        /// lowest and highest pitch, stands inside the ring, unclamped, with the ring inside its far clip.
        /// </summary>
        [UnityTest]
        public IEnumerator Step95b_BuiltRingBlocksNothingAndHoldsTheGameCamera()
        {
            var ids = new List<string> { "level1", "level12", "level22" };
            if (LevelLoader.Load(TitleCameraTour.LevelId) != null)
            {
                ids.Add(TitleCameraTour.LevelId);
            }
            foreach (string id in ids)
            {
                yield return Load(id);
                MeshRenderer ring = Backdrop();
                Assert.IsNotNull(ring, $"{id}: no garden backdrop");
                Assert.AreEqual(1, ring.sharedMaterials.Length, $"{id}: the backdrop has several slots");
                Assert.IsEmpty(ring.GetComponentsInChildren<Collider>(true), $"{id}: the backdrop has a collider");
                int layerBit = 1 << ring.gameObject.layer;
                Assert.AreEqual(0, layerBit & (Layers.OccluderMask | Layers.ChairBlockerMask | Layers.NavMeshSourceMask | (1 << Layers.Floor)),
                    $"{id}: the backdrop is on a gameplay layer");
                Assert.AreEqual(ShadowCastingMode.Off, ring.shadowCastingMode, $"{id}: the backdrop casts shadows");
                Assert.IsFalse(ring.receiveShadows, $"{id}: the backdrop receives shadows");
                Assert.AreEqual(PrimitiveKit.UnlitShaderName, ring.sharedMaterial.shader.name, $"{id}: the backdrop is lit");
                int users = Game.Level.Root.GetComponentsInChildren<Renderer>(true).Count(r => r != ring && r.sharedMaterials.Contains(ring.sharedMaterial));
                Assert.Greater(users, 0, $"{id}: the backdrop's material is its own (a new material)");
                var block = new MaterialPropertyBlock();
                ring.GetPropertyBlock(block);
                Assert.AreSame(GardenBackdrop.Texture, block.GetTexture("_BaseMap"), $"{id}: the backdrop does not show the garden");
                Assert.AreEqual(TextureWrapMode.Repeat, GardenBackdrop.Texture.wrapModeU, "the garden does not repeat round the ring");

                OrbitCamera orbit = Game.Camera;
                Camera cam = main.Camera;
                Assert.IsTrue(orbit.Fence.HasValue, $"{id}: the camera has no fence");
                GardenBackdrop.Ring fence = orbit.Fence.Value;
                Assert.AreEqual(GardenBackdrop.RingFor(Game.Def).Radius, fence.Radius, 1e-4f, $"{id}: the fence is not this level's ring");
                Assert.AreEqual(fence.Radius, ring.bounds.extents.x, 0.05f, $"{id}: the built ring is not the fence's");
                Assert.GreaterOrEqual(cam.farClipPlane, fence.FarClip, $"{id}: the far clip cuts the ring");
                orbit.SetDistance(orbit.MaxDistance);
                for (int yaw = 0; yaw < 360; yaw += 30)
                {
                    foreach (float pitch in new[] { Tuning.PitchMin, Tuning.PitchMax })
                    {
                        orbit.SetView(yaw, pitch);
                        Vector3 eye = cam.transform.position;
                        Assert.IsTrue(fence.HoldsCamera(eye), $"{id}: yaw {yaw}, pitch {pitch}: the camera at {eye} leaves the ring");
                        float arm = Vector3.Distance(eye, orbit.Target.VisualCenter + Vector3.up * Tuning.CameraTargetHeight);
                        Assert.AreEqual(orbit.MaxDistance, arm, 0.02f, $"{id}: yaw {yaw}, pitch {pitch}: the fence shortened the zoom in play");
                    }
                }
            }
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Step 95z: shots from the real game camera, docs/m9/backdrop/PREFIX_LEVEL.png, one 4 by 3 sheet per level: four
        /// yaws, at the longest zoom and the lowest pitch, at the longest zoom and a mid pitch, at the default zoom and pitch.
        /// </summary>
        [UnityTest]
        public IEnumerator Step95z_BackdropShots()
        {
            const int w = 480;
            const int h = 300;
            foreach (string id in new[] { "level1", "level9", "level12", "level21", "level22", TitleCameraTour.LevelId })
            {
                yield return Load(id);
                OrbitCamera orbit = Game.Camera;
                Camera cam = main.Camera;
                var sheet = new Texture2D(w * 4, h * 3, TextureFormat.RGBA32, false);
                float yaw = Game.Def.Player.Yaw;
                (float distance, float pitch)[] rows = { (orbit.MaxDistance, Tuning.PitchMin), (orbit.MaxDistance, 32f), (Tuning.OrbitDistance, Tuning.PitchDefault) };
                for (int row = 0; row < rows.Length; row++)
                {
                    orbit.SetDistance(rows[row].distance);
                    for (int i = 0; i < 4; i++)
                    {
                        orbit.SetView(yaw + 30f + 90f * i, rows[row].pitch);
                        yield return Frames(2);
                        Color32[] pixels = RenderPixels(cam, w, h);
                        sheet.SetPixels32(w * i, h * (rows.Length - 1 - row), w, h, pixels);
                    }
                }
                sheet.Apply();
                string dir = System.IO.Path.Combine("docs", "m9", "backdrop");
                System.IO.Directory.CreateDirectory(dir);
                System.IO.File.WriteAllBytes(System.IO.Path.Combine(dir, ShotPrefix + "_" + id + ".png"), sheet.EncodeToPNG());
                Object.Destroy(sheet);
            }
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        private static Color32[] RenderPixels(Camera cam, int width, int height)
        {
            RenderTexture rt = RenderTexture.GetTemporary(width, height, 24);
            var request = new RenderPipeline.StandardRequest { destination = rt };
            Assert.IsTrue(RenderPipeline.SupportsRenderRequest(cam, request), "premise: the pipeline cannot render the camera to a texture");
            RenderPipeline.SubmitRenderRequest(cam, request);
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = rt;
            var texture = new Texture2D(width, height, TextureFormat.RGBA32, false);
            texture.ReadPixels(new Rect(0, 0, width, height), 0, 0);
            texture.Apply();
            RenderTexture.active = previous;
            RenderTexture.ReleaseTemporary(rt);
            Color32[] pixels = texture.GetPixels32();
            Object.Destroy(texture);
            return pixels;
        }
    }
}
