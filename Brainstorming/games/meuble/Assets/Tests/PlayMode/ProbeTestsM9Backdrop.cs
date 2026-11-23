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
    /// Garden backdrop (product owner images of 2026-11-19 and 2026-11-20, GardenBackdrop, docs/m9/backdrop/NOTES.md): every
    /// level and the title house stand in a ring showing the owner's garden on its inside, closed at its top by a round sky
    /// ceiling. The camera stays inside the ring and below its top at every zoom, orbit, view pitch (down to the sky look,
    /// Tuning.PitchMin) and focus the level allows, the far clip holds it, the picture keeps its aspect, the ceiling closes
    /// the ring with no gap and no colour step, nothing of the void shows at the highest look, and neither part blocks
    /// anything (no collider, a layer no gameplay mask holds, no shadow, no new material). Shots under Build/shots/backdrop/
    /// (never under docs/).
    /// </summary>
    public sealed class ProbeTestsM9Backdrop
    {
        /// <summary>The prefix of the shots (one per look iteration, see NOTES.md).</summary>
        private const string ShotPrefix = "v5";

        /// <summary>Where the shots go (Build/ is ignored by git; docs/ holds no image).</summary>
        private static readonly string ShotDir = System.IO.Path.Combine("Build", "shots", "backdrop");

        /// <summary>The pitches a camera pose may take: the sky look, the arm's floor, the old lowest, the default, the highest.</summary>
        private static readonly float[] Pitches = { Tuning.PitchMin, Tuning.OrbitArmPitchMin, 15f, Tuning.PitchDefault, Tuning.PitchMax };

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
        /// the highest floor, at every yaw (15 degree steps), every pitch of <see cref="Pitches"/> (the arm from
        /// OrbitCamera.ArmDirection) and the longest zoom, the unclamped camera stands inside the ring's camera space (so the
        /// fence never moves the camera in play), at least the clearance inside the ring and below its top; the picture
        /// keeps its aspect and fits under the ceiling; a zoom far beyond the level's bound is fenced back inside. The arm
        /// never dips below Tuning.OrbitArmPitchMin, and above its easing it is the view.
        /// </summary>
        [UnityTest]
        public IEnumerator Step95a_EveryCameraPoseStaysInsideTheRing()
        {
            Assert.Less(Tuning.PitchMin, 15f, "premise: the view looks higher than the 2026-11-19 lowest pitch");
            for (float p = Tuning.PitchMin; p <= Tuning.PitchMax; p += 0.5f)
            {
                float armPitch = OrbitCamera.ArmPitchFor(p);
                Assert.GreaterOrEqual(armPitch, Tuning.OrbitArmPitchMin - 1e-4f, $"pitch {p}: the arm dips to {armPitch}");
                Assert.GreaterOrEqual(armPitch, p - 1e-4f, $"pitch {p}: the arm stands below the view");
                if (p >= Tuning.OrbitArmPitchMin + Tuning.OrbitArmPitchEase)
                {
                    Assert.AreEqual(p, armPitch, 1e-4f, $"pitch {p}: the arm leaves the view above its easing");
                }
            }
            var table = new List<string>();
            int poses = 0;
            foreach (string id in AllLevels())
            {
                LevelDef def = LevelLoader.Load(id);
                Assert.IsNotNull(def, $"{id}: premise: the level parses");
                GardenBackdrop.Ring ring = GardenBackdrop.RingFor(def);
                float circumference = 2f * Mathf.PI * ring.Radius;
                Assert.That(ring.PictureHeight * GardenBackdrop.ImageAspect * ring.Repeats, Is.EqualTo(circumference).Within(1e-3f),
                    $"{id}: the picture is stretched ({ring.Repeats} repeats of {ring.PictureHeight:0.00} m on {circumference:0.0} m)");
                Assert.LessOrEqual(ring.PictureHeight, ring.Height + 1e-4f, $"{id}: the picture rises above the ceiling");
                Assert.AreEqual(GardenBackdrop.PictureRatio, ring.PictureHeight / ring.Radius, 0.2f, $"{id}: the garden is out of scale");
                Assert.Greater(ring.Top, ring.CameraTop, $"{id}: the camera may rise above the ceiling");
                // The ceiling's rounded rim never cuts into the camera space (its highest point at its farthest reach).
                Assert.Greater(ring.InnerRadiusAt(ring.CameraTop) - ring.CameraRadius, 0.5f, $"{id}: the ceiling's rounded rim reaches the camera");
                Assert.GreaterOrEqual(ring.WallTop + GardenBackdrop.Sink, ring.PictureHeight - 1e-4f, $"{id}: the rounded rim cuts the picture");
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
                        foreach (float pitch in Pitches)
                        {
                            Vector3 back = OrbitCamera.ArmDirection(yaw, pitch);
                            Vector3 eye = focus + back * arm;
                            Assert.IsTrue(ring.HoldsCamera(eye), $"{id}: focus {focus}, yaw {yaw}, pitch {pitch}: the camera at {eye} leaves the ring");
                            Assert.AreEqual(arm, GardenBackdrop.ClampArm(ring, focus, back, arm), 1e-4f, $"{id}: the fence moves the camera in play");
                            float gap = ring.InnerRadiusAt(eye.y) - new Vector2(eye.x - ring.Center.x, eye.z - ring.Center.z).magnitude;
                            worst = Mathf.Min(worst, gap);
                            // A zoom far beyond the level's bound is fenced back inside.
                            float fenced = GardenBackdrop.ClampArm(ring, focus, back, 200f);
                            Assert.IsTrue(ring.HoldsCamera(focus + back * fenced), $"{id}: the fence lets a long zoom out");
                            poses++;
                        }
                    }
                }
                Assert.GreaterOrEqual(worst, GardenBackdrop.CameraClearance, $"{id}: the camera comes within {worst:0.00} m of the ring");
                table.Add($"{id}: R {ring.Radius:0.0} H {ring.Height:0.0} picture {ring.PictureHeight:0.0} x{ring.Repeats} gap {worst:0.0} far {ring.FarClip:0}");
            }
            Debug.Log($"[Step95a] {poses} poses | " + string.Join(" | ", table));
            TestContext.WriteLine("[Step95a] " + string.Join(" | ", table));
            yield return null;
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Step 95b: on a small level, a house, the largest one and the title house, the built ring and its ceiling: one
        /// renderer of one slot each, both drawn with the windows' material (no new material), each picture through its
        /// block, no collider, the Default layer (no gameplay mask), no shadow; the ceiling's flat part lies at the ring's top,
        /// its rounded rim comes down onto the ring's own top vertices with the wall's normals (no gap, no crease), every face
        /// toward the inside. The real game camera at its longest zoom, at
        /// every yaw and every pitch of <see cref="Pitches"/>, stands inside the ring, unclamped, with the ring inside its
        /// far clip, and at the sky look its view points above the horizon. Rendered against a magenta clear colour at the
        /// sky look and the highest pitch, no pixel of the void shows (the ring, its ceiling and the grass close the view).
        /// </summary>
        [UnityTest]
        public IEnumerator Step95b_BuiltRingBlocksNothingAndHoldsTheGameCamera()
        {
            var ids = new List<string> { "level1", "level12", "level22" };
            if (LevelLoader.Load(TitleCameraTour.LevelId) != null)
            {
                ids.Add(TitleCameraTour.LevelId);
            }
            var table = new List<string>();
            foreach (string id in ids)
            {
                yield return Load(id);
                MeshRenderer ring = Backdrop();
                Assert.IsNotNull(ring, $"{id}: no garden backdrop");
                MeshRenderer sky = ring.GetComponentsInChildren<MeshRenderer>(true).FirstOrDefault(r => r.name == GardenBackdrop.SkyRendererName);
                Assert.IsNotNull(sky, $"{id}: the ring has no sky ceiling");
                foreach (MeshRenderer part in new[] { ring, sky })
                {
                    Assert.AreEqual(1, part.sharedMaterials.Length, $"{id}: {part.name} has several slots");
                    Assert.IsEmpty(part.GetComponentsInChildren<Collider>(true), $"{id}: {part.name} has a collider");
                    int layerBit = 1 << part.gameObject.layer;
                    Assert.AreEqual(0, layerBit & (Layers.OccluderMask | Layers.ChairBlockerMask | Layers.NavMeshSourceMask | (1 << Layers.Floor)),
                        $"{id}: {part.name} is on a gameplay layer");
                    Assert.AreEqual(ShadowCastingMode.Off, part.shadowCastingMode, $"{id}: {part.name} casts shadows");
                    Assert.IsFalse(part.receiveShadows, $"{id}: {part.name} receives shadows");
                    Assert.AreEqual(PrimitiveKit.UnlitShaderName, part.sharedMaterial.shader.name, $"{id}: {part.name} is lit");
                }
                Assert.AreSame(ring.sharedMaterial, sky.sharedMaterial, $"{id}: the ceiling has a material of its own");
                int users = Game.Level.Root.GetComponentsInChildren<Renderer>(true).Count(r => r != ring && r != sky && r.sharedMaterials.Contains(ring.sharedMaterial));
                Assert.Greater(users, 0, $"{id}: the backdrop's material is its own (a new material)");
                var block = new MaterialPropertyBlock();
                ring.GetPropertyBlock(block);
                Assert.AreSame(GardenBackdrop.Texture, block.GetTexture("_BaseMap"), $"{id}: the backdrop does not show the garden");
                Assert.AreEqual(TextureWrapMode.Repeat, GardenBackdrop.Texture.wrapModeU, "the garden does not repeat round the ring");
                Assert.AreEqual(TextureWrapMode.Clamp, GardenBackdrop.Texture.wrapModeV, "the garden wraps from its sky to its lawn");
                sky.GetPropertyBlock(block);
                Assert.AreSame(GardenBackdrop.SkyTexture, block.GetTexture("_BaseMap"), $"{id}: the ceiling does not show the sky");

                OrbitCamera orbit = Game.Camera;
                Camera cam = main.Camera;
                Assert.IsTrue(orbit.Fence.HasValue, $"{id}: the camera has no fence");
                GardenBackdrop.Ring fence = orbit.Fence.Value;
                Assert.AreEqual(GardenBackdrop.RingFor(Game.Def).Radius, fence.Radius, 1e-4f, $"{id}: the fence is not this level's ring");
                Assert.AreEqual(fence.Radius, ring.bounds.extents.x, 0.05f, $"{id}: the built ring is not the fence's");
                Assert.GreaterOrEqual(cam.farClipPlane, fence.FarClip, $"{id}: the far clip cuts the ring");

                // The ceiling closes the ring: its flat part at the ring's top, its lowest vertices the ring's own top
                // vertices (the wall's top) with the wall's own normals (a smooth round, no crease for the ambient occlusion to
                // darken), every face toward the inside.
                Assert.AreEqual(fence.Top, sky.bounds.max.y, 1e-3f, $"{id}: the ceiling's flat part is not at the ring's top");
                Assert.AreEqual(fence.WallTop, sky.bounds.min.y, 1e-3f, $"{id}: the ceiling does not come down to the wall's top");
                Assert.AreEqual(fence.WallTop, ring.bounds.max.y, 1e-3f, $"{id}: the wall does not end where the rounded rim starts");
                Assert.AreEqual(fence.Radius, sky.bounds.extents.x, 0.05f, $"{id}: the ceiling is not the ring's size");
                Mesh ringMesh = ring.GetComponent<MeshFilter>().sharedMesh;
                Mesh skyMesh = sky.GetComponent<MeshFilter>().sharedMesh;
                Vector3[] skyVertices = skyMesh.vertices;
                Vector3[] skyNormals = skyMesh.normals;
                Vector3[] ringVertices = ringMesh.vertices;
                Vector3[] ringNormals = ringMesh.normals;
                for (int i = 1; i < ringVertices.Length; i += 2)
                {
                    Vector3 top = ring.transform.TransformPoint(ringVertices[i]);
                    int nearest = Enumerable.Range(0, skyVertices.Length).OrderBy(k => Vector3.Distance(sky.transform.TransformPoint(skyVertices[k]), top)).First();
                    float gap = Vector3.Distance(sky.transform.TransformPoint(skyVertices[nearest]), top);
                    Assert.Less(gap, 1e-3f, $"{id}: the ring's top vertex {i} has no ceiling vertex (a gap of {gap:0.000} m)");
                    Assert.Greater(Vector3.Dot(skyNormals[nearest], ringNormals[i]), 0.999f, $"{id}: the ceiling meets the wall at an angle (a crease) at vertex {i}");
                }
                int[] triangles = skyMesh.triangles;
                for (int t = 0; t < triangles.Length; t += 3)
                {
                    Vector3 a = skyVertices[triangles[t]], b = skyVertices[triangles[t + 1]], c = skyVertices[triangles[t + 2]];
                    Vector3 inward = skyNormals[triangles[t]] + skyNormals[triangles[t + 1]] + skyNormals[triangles[t + 2]];
                    Assert.Greater(Vector3.Dot(Vector3.Cross(b - a, c - a), inward), 0f, $"{id}: the ceiling's triangle {t / 3} faces outward (Unity's front face is clockwise)");
                }
                Vector2[] skyUvs = skyMesh.uv;
                Assert.IsTrue(skyUvs.All(uv => uv.x >= -1e-4f && uv.x <= 1f + 1e-4f && uv.y >= -1e-4f && uv.y <= 1f + 1e-4f),
                    $"{id}: the ceiling samples outside its picture");

                orbit.SetDistance(orbit.MaxDistance);
                for (int yaw = 0; yaw < 360; yaw += 30)
                {
                    foreach (float pitch in Pitches)
                    {
                        orbit.SetView(yaw, pitch);
                        Vector3 eye = cam.transform.position;
                        Assert.IsTrue(fence.HoldsCamera(eye), $"{id}: yaw {yaw}, pitch {pitch}: the camera at {eye} leaves the ring");
                        float arm = Vector3.Distance(eye, orbit.Target.VisualCenter + Vector3.up * Tuning.CameraTargetHeight);
                        Assert.AreEqual(orbit.MaxDistance, arm, 0.02f, $"{id}: yaw {yaw}, pitch {pitch}: the fence shortened the zoom in play");
                        Assert.AreEqual(-Mathf.Sin(pitch * Mathf.Deg2Rad), cam.transform.forward.y, 1e-3f,
                            $"{id}: yaw {yaw}, pitch {pitch}: the view does not look at the pitch asked");
                    }
                }
                orbit.SetView(0f, Tuning.PitchMin - 30f);
                Assert.AreEqual(Tuning.PitchMin, orbit.Pitch, 1e-4f, $"{id}: the view pitch is not clamped to Tuning.PitchMin");
                Assert.Greater(cam.transform.forward.y, 0f, $"{id}: at the sky look the view does not point above the horizon");

                // No pixel of the void at the sky look or the highest pitch, at the longest and the shortest zoom.
                Color clear = cam.backgroundColor;
                int voids = 0;
                int frames = 0;
                try
                {
                    cam.backgroundColor = Color.magenta;
                    foreach (float distance in new[] { orbit.MaxDistance, Tuning.OrbitDistanceMin })
                    {
                        orbit.SetDistance(distance);
                        for (int yaw = 0; yaw < 360; yaw += 60)
                        {
                            foreach (float pitch in new[] { Tuning.PitchMin, Tuning.PitchMax })
                            {
                                orbit.SetView(yaw, pitch);
                                yield return null;
                                Color32[] pixels = RenderPixels(cam, 192, 108);
                                int count = pixels.Count(p => p.r > 200 && p.g < 60 && p.b > 200);
                                Assert.AreEqual(0, count, $"{id}: zoom {distance:0.0}, yaw {yaw}, pitch {pitch}: {count} pixels of the void show");
                                voids += count;
                                frames++;
                            }
                        }
                    }
                }
                finally
                {
                    cam.backgroundColor = clear;
                }
                table.Add($"{id}: R {fence.Radius:0.0} top {fence.Top:0.0} picture {fence.PictureHeight:0.0} x{fence.Repeats}, {frames} frames, {voids} void pixels");
            }
            Debug.Log("[Step95b] " + string.Join(" | ", table));
            TestContext.WriteLine("[Step95b] " + string.Join(" | ", table));
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Step 95c: the shipped pictures meet without a seam: the garden's top rows and the sky's rim band are exactly
        /// GardenBackdrop.SkyTop (the ring's top edge, the band above the picture and the ceiling's rim are one colour);
        /// the garden wraps (its left and right columns meet no harder than two neighbouring columns), keeps the 4 to 1
        /// aspect the ring is sized for; the sky's sun stands on its right half (the ceiling turns image right toward the
        /// scene's light).
        /// </summary>
        [UnityTest]
        public IEnumerator Step95c_PicturesMeetWithoutASeam()
        {
            var garden = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            var skyImage = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                Assert.IsTrue(garden.LoadImage(System.IO.File.ReadAllBytes("Assets/Resources/" + GardenBackdrop.ResourcePath + ".png")), "the garden picture does not load");
                Assert.IsTrue(skyImage.LoadImage(System.IO.File.ReadAllBytes("Assets/Resources/" + GardenBackdrop.SkyResourcePath + ".png")), "the sky picture does not load");
                Assert.AreEqual(GardenBackdrop.ImageAspect, (float)garden.width / garden.height, 1e-3f, "the garden picture is not the aspect the ring is sized for");
                Assert.AreEqual(skyImage.width, skyImage.height, "the sky picture is not square");
                Color32 want = GardenBackdrop.SkyTop;
                Color32[] g = garden.GetPixels32();
                int w = garden.width;
                int h = garden.height;
                // Texture rows run bottom to top: the top rows are the last ones.
                for (int y = h - 8; y < h; y++)
                {
                    for (int x = 0; x < w; x += 7)
                    {
                        Color32 p = g[y * w + x];
                        Assert.IsTrue(p.r == want.r && p.g == want.g && p.b == want.b, $"the garden's top row {h - 1 - y} at x {x} is {p}, not the sky top {want}");
                    }
                }
                double edge = 0;
                double inner = 0;
                for (int y = 0; y < h; y++)
                {
                    edge += Diff(g[y * w + w - 1], g[y * w]);
                    inner += Diff(g[y * w + w / 2], g[y * w + w / 2 + 1]);
                }
                Assert.LessOrEqual(edge, inner * 1.5, $"the garden does not wrap (edge step {edge / h:0.00} against {inner / h:0.00} inside)");

                Color32[] s = skyImage.GetPixels32();
                int n = skyImage.width;
                float half = n * 0.5f;
                int rim = 0;
                double right = 0;
                double left = 0;
                for (int y = 0; y < n; y++)
                {
                    for (int x = 0; x < n; x++)
                    {
                        float r = new Vector2(x + 0.5f - half, y + 0.5f - half).magnitude / half;
                        Color32 p = s[y * n + x];
                        if (r > 0.985f)
                        {
                            Assert.IsTrue(p.r == want.r && p.g == want.g && p.b == want.b, $"the sky's rim at ({x}, {y}) is {p}, not the sky top {want}");
                            rim++;
                        }
                        else if (p.r + p.g + p.b > 3 * 245)
                        {
                            if (x >= half)
                            {
                                right++;
                            }
                            else
                            {
                                left++;
                            }
                        }
                    }
                }
                Assert.Greater(rim, 0, "premise: rim pixels measured");
                Assert.Greater(right, 3 * left, $"the sky's sun is not on its right half ({right} bright pixels right, {left} left)");
            }
            finally
            {
                Object.Destroy(garden);
                Object.Destroy(skyImage);
            }
            yield return null;
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        private static int Diff(Color32 a, Color32 b)
        {
            return Mathf.Abs(a.r - b.r) + Mathf.Abs(a.g - b.g) + Mathf.Abs(a.b - b.b);
        }

        /// <summary>
        /// Step 95z: shots from the real game camera under Build/shots/backdrop/: one 4 by 4 sheet per level,
        /// PREFIX_LEVEL.png, four yaws (toward the scene's light first, then a quarter turn each), at the longest zoom and
        /// the sky look (Tuning.PitchMin), at the default zoom and the sky look, at the longest zoom and the 2026-11-19
        /// lowest pitch (15), at the default zoom and pitch; and two 1280 by 720 views, PREFIX_LEVEL_sun.png (the longest
        /// zoom, the sky look, toward the light) and PREFIX_LEVEL_away.png (the same, away from it).
        /// </summary>
        [UnityTest]
        public IEnumerator Step95z_BackdropShots()
        {
            const int w = 480;
            const int h = 270;
            System.IO.Directory.CreateDirectory(ShotDir);
            float azimuth = GardenBackdrop.SunAzimuth();
            float sunYaw = Mathf.Atan2(Mathf.Cos(azimuth), Mathf.Sin(azimuth)) * Mathf.Rad2Deg;
            foreach (string id in new[] { "level1", "level9", "level12", "level21", "level22", TitleCameraTour.LevelId })
            {
                yield return Load(id);
                OrbitCamera orbit = Game.Camera;
                Camera cam = main.Camera;
                (float distance, float pitch)[] rows =
                {
                    (orbit.MaxDistance, Tuning.PitchMin), (Tuning.OrbitDistance, Tuning.PitchMin), (orbit.MaxDistance, 15f),
                    (Tuning.OrbitDistance, Tuning.PitchDefault),
                };
                var sheet = new Texture2D(w * 4, h * rows.Length, TextureFormat.RGBA32, false);
                for (int row = 0; row < rows.Length; row++)
                {
                    orbit.SetDistance(rows[row].distance);
                    for (int i = 0; i < 4; i++)
                    {
                        orbit.SetView(sunYaw + 90f * i, rows[row].pitch);
                        yield return Frames(2);
                        Color32[] pixels = RenderPixels(cam, w, h);
                        sheet.SetPixels32(w * i, h * (rows.Length - 1 - row), w, h, pixels);
                    }
                }
                sheet.Apply();
                System.IO.File.WriteAllBytes(System.IO.Path.Combine(ShotDir, ShotPrefix + "_" + id + ".png"), sheet.EncodeToPNG());
                Object.Destroy(sheet);
                orbit.SetDistance(orbit.MaxDistance);
                foreach ((string suffix, float turn) in new[] { ("sun", 0f), ("away", 180f) })
                {
                    orbit.SetView(sunYaw + turn, Tuning.PitchMin);
                    yield return Frames(2);
                    var view = new Texture2D(1280, 720, TextureFormat.RGBA32, false);
                    view.SetPixels32(RenderPixels(cam, 1280, 720));
                    view.Apply();
                    System.IO.File.WriteAllBytes(System.IO.Path.Combine(ShotDir, ShotPrefix + "_" + id + "_" + suffix + ".png"), view.EncodeToPNG());
                    Object.Destroy(view);
                }
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
