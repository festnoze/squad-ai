using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// FISHEYE (docs/next/progress/FISHEYE.md): the barrel distortion of the title menu's 3D background (MenuFisheye on the
    /// tour camera, MenuFisheyePass, StreamingAssets/menu_camera.json read through MenuCameraSettings).
    /// - Fisheye01: the shipped file parses cleanly and equals the built-in defaults; bad JSON, a text value, out-of-range
    ///   values (clamped) and missing keys fall back with a problem line each; the lens formula fits (zoom 1: every border
    ///   pixel samples inside the picture and the farthest corner samples itself, so no black and no stretched edge).
    /// - Fisheye02, on the real Boot scene: the pass runs for the tour camera while the title is open and for no other
    ///   camera; it changes the picture without blackening its border; the peripheral blur softens the outer eighth of the
    ///   picture and leaves the lens centre untouched; an edited file is picked up while the title stays
    ///   open; in a level nothing is enqueued; reopening the title reads the file again. Writes PC 16:9 and phone 20:9 shots
    ///   (off, default, strong) to Build/shots/fisheye/editor_*.png (scene only: the menu canvas is an overlay).
    /// </summary>
    public sealed class ProbeTestsFisheye
    {
        private const string ShotDir = "Build/shots/fisheye";
        private static readonly (string name, int w, int h)[] Aspects = { ("pc", 1920, 1080), ("phone", 2400, 1080) };
        private static readonly float[] Stops = { 0.19f, 0.52f };

        private Main main;
        private string tempFile;
        private readonly List<string> logged = new List<string>();

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            logged.Clear();
            MenuCameraSettings.PathOverride = null;
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            Application.logMessageReceived -= OnLog;
            MenuCameraSettings.PathOverride = null;
            if (tempFile != null && File.Exists(tempFile))
            {
                File.Delete(tempFile);
            }
            tempFile = null;
            if (main != null && main.Camera != null)
            {
                TitleCameraTour tour = main.Camera.GetComponent<TitleCameraTour>();
                if (tour != null)
                {
                    tour.enabled = true;
                }
                main.Camera.targetTexture = null;
                main.Camera.ResetAspect();
                main.Camera.ResetProjectionMatrix();
            }
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            SaveStore.ResetForTests();
            yield return null;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                logged.Add(condition);
            }
        }

        [Test]
        public void Fisheye01_SettingsParseClampAndFallBack()
        {
            // The shipped file: no problem, the built-in values.
            string shipped = Path.Combine(Application.streamingAssetsPath, MenuCameraSettings.FileName);
            Assert.IsTrue(File.Exists(shipped), "the shipped file is missing: " + shipped);
            var problems = new List<string>();
            MenuCameraSettings s = MenuCameraSettings.Parse(File.ReadAllText(shipped), problems);
            CollectionAssert.IsEmpty(problems, "the shipped file has problems");
            MenuCameraSettings d = MenuCameraSettings.Defaults;
            Assert.AreEqual(d.FisheyeStrength, s.FisheyeStrength, 1e-6f, "shipped fisheyeStrength differs from the default");
            Assert.AreEqual(d.FisheyeZoom, s.FisheyeZoom, 1e-6f, "shipped fisheyeZoom differs from the default");
            Assert.AreEqual(d.FisheyeVignette, s.FisheyeVignette, 1e-6f, "shipped fisheyeVignette differs from the default");
            Assert.AreEqual(0.3f, d.FisheyeStrength, 1e-6f, "default strength");
            // User tuning (2026-11-24): a little below auto-fit (the lens shows a touch of its rim).
            Assert.AreEqual(0.834f, d.FisheyeZoom, 1e-6f, "default zoom (the user's tuning)");
            Assert.That(d.FisheyeVignette, Is.InRange(0f, 0.5f), "default vignette");
            Assert.AreEqual(d.PeripheralBlur, s.PeripheralBlur, 1e-6f, "shipped peripheralBlur differs from the default");
            Assert.AreEqual(d.PeripheralBlurRadius, s.PeripheralBlurRadius, 1e-6f, "shipped peripheralBlurRadius differs from the default");
            Assert.AreEqual(d.PeripheralBlurMotion, s.PeripheralBlurMotion, 1e-6f, "shipped peripheralBlurMotion differs from the default");
            // User tuning (2026-11-24): the full periphery blur.
            Assert.That(d.PeripheralBlur, Is.InRange(0.05f, 1f), "default blur: on");
            Assert.That(d.PeripheralBlurRadius, Is.InRange(0.2f, 0.7f), "default sharp centre");
            Assert.IsTrue(d.Visible, "the default is not visible");

            // Bad JSON: all defaults, one problem.
            problems.Clear();
            s = MenuCameraSettings.Parse("{ not json", problems);
            Assert.AreEqual(1, problems.Count, "bad JSON: " + string.Join(" | ", problems));
            Assert.AreEqual(d.FisheyeStrength, s.FisheyeStrength, 1e-6f);

            // A text value, out-of-range values and a missing key.
            problems.Clear();
            s = MenuCameraSettings.Parse("{ \"fisheyeStrength\": \"strong\", \"fisheyeZoom\": 0.1, \"fisheyeVignette\": 3,"
                + " \"peripheralBlur\": -2, \"peripheralBlurRadius\": [0.5], \"peripheralBlurMotion\": 9 }", problems);
            Assert.AreEqual(d.FisheyeStrength, s.FisheyeStrength, 1e-6f, "a text strength keeps the default");
            Assert.AreEqual(MenuCameraSettings.MinZoom, s.FisheyeZoom, 1e-6f, "zoom clamped up");
            Assert.AreEqual(1f, s.FisheyeVignette, 1e-6f, "vignette clamped down");
            Assert.AreEqual(0f, s.PeripheralBlur, 1e-6f, "blur clamped up to 0");
            Assert.AreEqual(d.PeripheralBlurRadius, s.PeripheralBlurRadius, 1e-6f, "an array radius keeps the default");
            Assert.AreEqual(1f, s.PeripheralBlurMotion, 1e-6f, "motion clamped down");
            Assert.AreEqual(6, problems.Count, "one problem per bad key: " + string.Join(" | ", problems));

            problems.Clear();
            s = MenuCameraSettings.Parse("{ \"fisheyeStrength\": 7 }", problems);
            Assert.AreEqual(MenuCameraSettings.MaxStrength, s.FisheyeStrength, 1e-6f, "strength clamped");
            Assert.AreEqual(d.FisheyeZoom, s.FisheyeZoom, 1e-6f, "missing zoom keeps the default");
            Assert.AreEqual(d.FisheyeVignette, s.FisheyeVignette, 1e-6f, "missing vignette keeps the default");
            Assert.AreEqual(d.PeripheralBlur, s.PeripheralBlur, 1e-6f, "missing blur keeps the default");
            Assert.AreEqual(d.PeripheralBlurRadius, s.PeripheralBlurRadius, 1e-6f, "missing radius keeps the default");
            Assert.AreEqual(d.PeripheralBlurMotion, s.PeripheralBlurMotion, 1e-6f, "missing motion keeps the default");
            Assert.AreEqual(6, problems.Count, "clamp plus five missing keys: " + string.Join(" | ", problems));

            problems.Clear();
            s = MenuCameraSettings.Parse("{ \"fisheyeStrength\": 0, \"fisheyeZoom\": 1, \"fisheyeVignette\": 0,"
                + " \"peripheralBlur\": 0, \"peripheralBlurRadius\": 0.4, \"peripheralBlurMotion\": 0.6 }", problems);
            CollectionAssert.IsEmpty(problems);
            Assert.IsFalse(s.Visible, "everything at 0 (zoom 1) must switch the pass off");
            s = MenuCameraSettings.Parse("{ \"fisheyeStrength\": 0, \"fisheyeZoom\": 1, \"fisheyeVignette\": 0,"
                + " \"peripheralBlur\": 0.2, \"peripheralBlurRadius\": 0.4, \"peripheralBlurMotion\": 0.6 }", null);
            Assert.IsTrue(s.Visible, "the blur alone keeps the pass on");

            // The lens: auto-fit at zoom 1 on PC and phone screens, centred or on the tour's shifted axis.
            Vector2 tourCentre = MenuFisheye.LensCentre(ShiftedProjection());
            Assert.AreEqual(0.5f + 0.5f * Tuning.TitleTourLensShift, tourCentre.x, 1e-5f, "the lens centre follows the tour's lens shift");
            Assert.AreEqual(0.5f, tourCentre.y, 1e-5f);
            foreach (float aspect in new[] { 16f / 9f, 20f / 9f })
            {
                foreach (Vector2 centre in new[] { new Vector2(0.5f, 0.5f), tourCentre })
                {
                    foreach (float k in new[] { 0.3f, 1f })
                    {
                        float farthest = 0f;
                        for (int i = 0; i <= 64; i++)
                        {
                            float t = i / 64f;
                            foreach (Vector2 uv in new[] { new Vector2(t, 0f), new Vector2(t, 1f), new Vector2(0f, t), new Vector2(1f, t) })
                            {
                                Vector2 src = MenuFisheye.SourceUv(uv, centre, aspect, k, 1f);
                                Assert.That(src.x, Is.InRange(-1e-4f, 1.0001f), $"aspect {aspect:0.00} centre {centre} k {k}: {uv} samples {src}");
                                Assert.That(src.y, Is.InRange(-1e-4f, 1.0001f), $"aspect {aspect:0.00} centre {centre} k {k}: {uv} samples {src}");
                                farthest = Mathf.Max(farthest, Mathf.Max(Mathf.Abs(src.x - centre.x) / Mathf.Max(centre.x, 1f - centre.x),
                                    Mathf.Abs(src.y - centre.y) / Mathf.Max(centre.y, 1f - centre.y)));
                            }
                        }
                        Assert.AreEqual(1f, farthest, 1e-3f, $"aspect {aspect:0.00} centre {centre} k {k}: the fit wastes the picture's edge");
                        // The centre is magnified 1 + k times.
                        Vector2 near = MenuFisheye.SourceUv(centre + new Vector2(0.001f, 0f), centre, aspect, k, 1f);
                        Assert.AreEqual(1f / (1f + k), (near.x - centre.x) / 0.001f, 1e-3f, "centre magnification");
                        // Zoom below 1 reaches outside (black borders), above 1 stays strictly inside.
                        Vector2 corner = new Vector2(centre.x < 0.5f ? 1f : 0f, 0f);
                        Vector2 outside = MenuFisheye.SourceUv(corner, centre, aspect, k, 0.8f);
                        Assert.IsTrue(outside.x < 0f || outside.x > 1f || outside.y < 0f, "zoom 0.8 should reach outside at the farthest corner");
                        Vector2 inside = MenuFisheye.SourceUv(corner, centre, aspect, k, 1.2f);
                        Assert.IsTrue(inside.x > 0f && inside.x < 1f && inside.y > 0f, "zoom 1.2 should crop");
                    }
                }
            }
        }

        [UnityTest]
        public IEnumerator Fisheye02_OnTheTitleCameraOnly()
        {
            main.Menu.ShowTitle();
            Camera cam = main.Camera;
            TitleCameraTour tour = cam.GetComponent<TitleCameraTour>();
            Assert.IsNotNull(tour, "premise: the camera has no title tour");
            MenuFisheye fisheye = cam.GetComponent<MenuFisheye>();
            Assert.IsNotNull(fisheye, "the tour camera has no MenuFisheye");
            for (int i = 0; i < 120 && !tour.Active; i++)
            {
                yield return null;
            }
            Assert.IsTrue(tour.Active, "premise: the title tour never started");
            yield return null;
            Assert.GreaterOrEqual(fisheye.Loads, 1, "the file was not read when the title opened");
            Assert.AreEqual(MenuCameraSettings.Defaults.FisheyeStrength, fisheye.Settings.FisheyeStrength, 1e-6f, "the shipped strength");
            Assert.IsTrue(fisheye.Active, "the fish-eye is not active on the title (shader missing?)");

            // The tour camera, at a fixed pose, PC and phone, off, default and strong.
            tour.enabled = false;
            Directory.CreateDirectory(ShotDir);
            tempFile = Path.Combine(Application.temporaryCachePath, "fisheye_test_menu_camera.json");
            var report = new List<string>();
            foreach (var a in Aspects)
            {
                for (int s = 0; s < Stops.Length; s++)
                {
                    tour.Pose(Stops[s] * tour.Length, out Vector3 position, out Quaternion rotation);
                    yield return null;
                    Color32[] plain = RenderWith(fisheye, cam, position, rotation, a.w, a.h, 0f, 0f);
                    Assert.IsFalse(fisheye.Active, "strength 0 and no vignette should switch the pass off");
                    int countBefore = MenuFisheye.EnqueuedCount;
                    Color32[] lens = RenderWith(fisheye, cam, position, rotation, a.w, a.h, -1f, -1f);
                    Assert.Greater(MenuFisheye.EnqueuedCount, countBefore, "the default did not enqueue the pass");
                    Assert.AreSame(cam, MenuFisheye.EnqueuedCamera, "the pass went to another camera");
                    Assert.AreEqual(Time.frameCount, MenuFisheye.RecordedFrame, "the pass was enqueued but never recorded");
                    Assert.AreEqual(a.w / (float)a.h, MenuFisheye.LastLens.z, 1e-3f, "the shader's aspect");
                    Assert.AreEqual(0.5f + 0.5f * Tuning.TitleTourLensShift, MenuFisheye.LastLens.x, 1e-3f, "the shader's lens centre");
                    MenuCameraSettings d = MenuCameraSettings.Defaults;
                    Assert.AreEqual(d.PeripheralBlur, MenuFisheye.LastBlur.x, 1e-6f, "the shader's blur");
                    Assert.AreEqual(d.PeripheralBlurRadius, MenuFisheye.LastBlur.y, 1e-6f, "the shader's blur radius");
                    Color32[] strong = RenderWith(fisheye, cam, position, rotation, a.w, a.h, 0.8f, 0.35f, 1f, 1f);
                    // The peripheral blur alone, on the default lens: off and strong.
                    Color32[] blurOff = RenderWith(fisheye, cam, position, rotation, a.w, a.h, d.FisheyeStrength, d.FisheyeVignette, 0f, d.PeripheralBlurMotion);
                    Color32[] blurStrong = RenderWith(fisheye, cam, position, rotation, a.w, a.h, d.FisheyeStrength, d.FisheyeVignette, 1f, d.PeripheralBlurMotion);
                    Color32[] blurSoft = RenderWith(fisheye, cam, position, rotation, a.w, a.h, d.FisheyeStrength, d.FisheyeVignette, 1f, 0f);
                    Save(Path.Combine(ShotDir, $"editor_{a.name}_{s + 1}_off.png"), plain, a.w, a.h);
                    Save(Path.Combine(ShotDir, $"editor_{a.name}_{s + 1}_default.png"), lens, a.w, a.h);
                    Save(Path.Combine(ShotDir, $"editor_{a.name}_{s + 1}_strong.png"), strong, a.w, a.h);
                    Save(Path.Combine(ShotDir, $"editor_{a.name}_{s + 1}_blur0.png"), blurOff, a.w, a.h);
                    Save(Path.Combine(ShotDir, $"editor_{a.name}_{s + 1}_blurstrong.png"), blurStrong, a.w, a.h);
                    Save(Path.Combine(ShotDir, $"editor_{a.name}_{s + 1}_blursoft.png"), blurSoft, a.w, a.h);

                    // The periphery loses detail, the centre (the lens centre, inside the sharp radius) does not change.
                    float sharpOff = EdgeDetail(blurOff, a.w, a.h);
                    float sharpDefault = EdgeDetail(lens, a.w, a.h);
                    float sharpStrong = EdgeDetail(blurStrong, a.w, a.h);
                    float centreDiff = CentreDiff(blurOff, blurStrong, a.w, a.h, MenuFisheye.LastLens.x);
                    report.Add($"{a.name}_{s + 1}: border detail blur 0 {sharpOff:0.00}, default {sharpDefault:0.00}, strong {sharpStrong:0.00};"
                        + $" centre diff blur 0 vs strong {centreDiff:0.000}");
                    Assert.Less(sharpStrong, sharpOff * 0.75f, $"{a.name}_{s + 1}: the strong blur does not soften the periphery");
                    Assert.Less(sharpDefault, sharpOff, $"{a.name}_{s + 1}: the default blur does not soften the periphery");
                    Assert.Less(centreDiff, 0.5f, $"{a.name}_{s + 1}: the blur reaches the sharp centre");

                    float diff = MeanDiff(plain, lens);
                    float edgePlain = EdgeLuma(plain, a.w, a.h);
                    float edgeLens = EdgeLuma(lens, a.w, a.h);
                    float edgeStrong = EdgeLuma(strong, a.w, a.h);
                    int blackPlain = BlackEdgePixels(plain, a.w, a.h);
                    int blackEdge = BlackEdgePixels(lens, a.w, a.h);
                    int blackStrong = BlackEdgePixels(strong, a.w, a.h);
                    report.Add($"{a.name}_{s + 1}: mean diff {diff:0.0}, edge luma off {edgePlain:0.0} default {edgeLens:0.0} strong {edgeStrong:0.0},"
                        + $" black border px off {blackPlain} default {blackEdge} strong {blackStrong}");
                    Assert.Greater(diff, 2f, $"{a.name}_{s + 1}: the default fish-eye does not change the picture");
                    Assert.Greater(edgeLens, edgePlain * 0.55f, $"{a.name}_{s + 1}: the border went dark (black or out-of-picture samples)");
                    Assert.LessOrEqual(blackEdge, blackPlain + (2 * (a.w + a.h)) / 50, $"{a.name}_{s + 1}: black pixels along the border");
                    Assert.LessOrEqual(blackStrong, blackPlain + (2 * (a.w + a.h)) / 50, $"{a.name}_{s + 1}: black pixels along the border (strong)");
                }
            }
            TestContext.WriteLine("[Fisheye] " + string.Join("\n", report));
            File.WriteAllLines(Path.Combine(ShotDir, "editor_fisheye.txt"), report);

            // Another camera rendering meanwhile never gets the pass.
            var other = new GameObject("FisheyeOtherCamera").AddComponent<Camera>();
            int count = MenuFisheye.EnqueuedCount;
            RenderTexture rt = RenderTexture.GetTemporary(320, 180, 24);
            RenderPipeline.SubmitRenderRequest(other, new RenderPipeline.StandardRequest { destination = rt });
            RenderTexture.ReleaseTemporary(rt);
            Object.Destroy(other.gameObject);
            Assert.AreEqual(count, MenuFisheye.EnqueuedCount, "another camera got the fish-eye");

            // Live edit while the title stays open: picked up within CheckSeconds.
            WriteSettings(0.5f, 0.2f);
            fisheye.Reload();
            Assert.AreEqual(0.5f, fisheye.Settings.FisheyeStrength, 1e-6f, "premise: the override file");
            int loads = fisheye.Loads;
            tour.enabled = true;
            cam.targetTexture = null;
            cam.ResetAspect();
            WriteSettings(0.75f, 0.2f);
            File.SetLastWriteTimeUtc(tempFile, System.DateTime.UtcNow.AddSeconds(5));
            float start = Time.realtimeSinceStartup;
            while (fisheye.Loads == loads && Time.realtimeSinceStartup - start < MenuFisheye.CheckSeconds + 2f)
            {
                yield return null;
            }
            Assert.Greater(fisheye.Loads, loads, "an edited file was not read again while the title stayed open");
            Assert.AreEqual(0.75f, fisheye.Settings.FisheyeStrength, 1e-6f, "the edited strength");

            // In a level: nothing enqueued, for the same camera.
            main.Menu.PlayLevel("level1");
            for (int i = 0; i < 200 && (tour.Active || main.Game.LevelId != "level1"); i++)
            {
                yield return null;
            }
            Assert.IsFalse(tour.Active, "premise: the tour still runs in a level");
            Assert.IsFalse(fisheye.Active, "the fish-eye is active in a level");
            count = MenuFisheye.EnqueuedCount;
            int recorded = MenuFisheye.RecordedFrame;
            rt = RenderTexture.GetTemporary(640, 360, 24);
            RenderPipeline.SubmitRenderRequest(cam, new RenderPipeline.StandardRequest { destination = rt });
            RenderTexture.ReleaseTemporary(rt);
            for (int i = 0; i < 5; i++)
            {
                yield return null;
            }
            Assert.AreEqual(count, MenuFisheye.EnqueuedCount, "the pass was enqueued in a level");
            Assert.AreEqual(recorded, MenuFisheye.RecordedFrame, "the pass ran in a level");

            // Back to the title: the file is read again.
            loads = fisheye.Loads;
            main.Menu.ShowTitle();
            for (int i = 0; i < 200 && !tour.Active; i++)
            {
                yield return null;
            }
            yield return null;
            Assert.IsTrue(tour.Active, "premise: the title tour did not restart");
            Assert.Greater(fisheye.Loads, loads, "reopening the title did not read the file again");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        // Writes the override file and points MenuCameraSettings at it.
        private void WriteSettings(float strength, float vignette, float blur = 0f, float motion = 0.6f)
        {
            File.WriteAllText(tempFile, string.Format(System.Globalization.CultureInfo.InvariantCulture,
                "{{ \"fisheyeStrength\": {0}, \"fisheyeZoom\": 1.0, \"fisheyeVignette\": {1}, \"peripheralBlur\": {2},"
                + " \"peripheralBlurRadius\": {3}, \"peripheralBlurMotion\": {4} }}",
                strength, vignette, blur, MenuCameraSettings.Defaults.PeripheralBlurRadius, motion));
            MenuCameraSettings.PathOverride = tempFile;
        }

        // A render of the tour camera with the given values (negative strength: the shipped file).
        private Color32[] RenderWith(MenuFisheye fisheye, Camera cam, Vector3 position, Quaternion rotation, int w, int h,
            float strength, float vignette, float blur = 0f, float motion = 0.6f)
        {
            if (strength < 0f)
            {
                MenuCameraSettings.PathOverride = null;
            }
            else
            {
                WriteSettings(strength, vignette, blur, motion);
            }
            fisheye.Reload();
            return Render(cam, position, rotation, w, h);
        }

        private static Matrix4x4 ShiftedProjection()
        {
            Matrix4x4 m = Matrix4x4.Perspective(55f, 16f / 9f, 0.05f, 80f);
            m[0, 2] = -Tuning.TitleTourLensShift;
            return m;
        }

        private static Color32[] Render(Camera cam, Vector3 position, Quaternion rotation, int width, int height)
        {
            cam.transform.SetPositionAndRotation(position, rotation);
            cam.aspect = width / (float)height;
            cam.ResetProjectionMatrix();
            Matrix4x4 m = cam.projectionMatrix;
            m[0, 2] = -Tuning.TitleTourLensShift;
            cam.projectionMatrix = m;
            RenderTexture rt = RenderTexture.GetTemporary(width, height, 24);
            RenderPipeline.SubmitRenderRequest(cam, new RenderPipeline.StandardRequest { destination = rt });
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

        private static float Luma(Color32 c) => 0.2126f * c.r + 0.7152f * c.g + 0.0722f * c.b;

        private static float MeanDiff(Color32[] a, Color32[] b)
        {
            double sum = 0;
            for (int i = 0; i < a.Length; i += 7)
            {
                sum += Mathf.Abs(Luma(a[i]) - Luma(b[i]));
            }
            return (float)(sum / (a.Length / 7));
        }

        // The mean luma of the outer 3 pixel band.
        private static float EdgeLuma(Color32[] p, int w, int h)
        {
            double sum = 0;
            int n = 0;
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    if (x < 3 || y < 3 || x >= w - 3 || y >= h - 3)
                    {
                        sum += Luma(p[y * w + x]);
                        n++;
                    }
                }
            }
            return (float)(sum / n);
        }

        // Mean absolute luma step between neighbours (right and up) in the outer eighth of the picture: its fine detail.
        private static float EdgeDetail(Color32[] p, int w, int h)
        {
            int bx = w / 8, by = h / 8;
            double sum = 0;
            int n = 0;
            for (int y = 0; y < h - 1; y += 2)
            {
                for (int x = 0; x < w - 1; x += 2)
                {
                    if (x >= bx && x < w - bx && y >= by && y < h - by)
                    {
                        continue;
                    }
                    float l = Luma(p[y * w + x]);
                    sum += Mathf.Abs(l - Luma(p[y * w + x + 1])) + Mathf.Abs(l - Luma(p[(y + 1) * w + x]));
                    n++;
                }
            }
            return (float)(sum / n);
        }

        // Mean absolute luma difference over a box of a tenth of the height around the lens centre.
        private static float CentreDiff(Color32[] a, Color32[] b, int w, int h, float centreX)
        {
            int cx = Mathf.RoundToInt(centreX * w), cy = h / 2, half = h / 20;
            double sum = 0;
            int n = 0;
            for (int y = cy - half; y < cy + half; y++)
            {
                for (int x = cx - half; x < cx + half; x++)
                {
                    sum += Mathf.Abs(Luma(a[y * w + x]) - Luma(b[y * w + x]));
                    n++;
                }
            }
            return (float)(sum / n);
        }

        private static int BlackEdgePixels(Color32[] p, int w, int h)
        {
            int black = 0;
            for (int x = 0; x < w; x++)
            {
                black += Luma(p[x]) < 2f ? 1 : 0;
                black += Luma(p[(h - 1) * w + x]) < 2f ? 1 : 0;
            }
            for (int y = 0; y < h; y++)
            {
                black += Luma(p[y * w]) < 2f ? 1 : 0;
                black += Luma(p[y * w + w - 1]) < 2f ? 1 : 0;
            }
            return black;
        }

        private static void Save(string file, Color32[] pixels, int w, int h)
        {
            var texture = new Texture2D(w, h, TextureFormat.RGBA32, false);
            texture.SetPixels32(pixels);
            texture.Apply();
            File.WriteAllBytes(file, texture.EncodeToPNG());
            Object.Destroy(texture);
        }
    }
}
