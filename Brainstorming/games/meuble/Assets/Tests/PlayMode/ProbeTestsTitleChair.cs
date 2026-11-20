using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Step 74 (title chair, 2026-11-19), on the real Boot scene: the baked title logo (TitleLogo), the red chair standing
    /// in a soft warm pool of light on the floor that holds its short shadow, framed a little right of the column's margin.
    /// Checks the bake, the pool (lit, soft edged, fading to nothing before the texture's edges) and the shadow inside it,
    /// the logo's fit on a 20:9 phone, then writes the title page's shots to docs/m9/titlechair.
    /// </summary>
    public sealed class ProbeTestsTitleChair
    {
        private const string ShotDir = "docs/m9/titlechair";
        // A 20:9 phone at the menu's CanvasScaler (1920 x 1080 reference, match 0.5): 966 reference units high.
        private const float PhoneHalfHeight = 966f / 2f;

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private Menu Menu => main.Menu;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
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
            Assert.IsNotNull(Menu, "premise: Main built no Menu");
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            Cursor.lockState = CursorLockMode.None;
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

        [UnityTest]
        public IEnumerator Step74a_TitleChairStandsInAPoolOfLight()
        {
            Strings.SetLanguage(Strings.French);
            Menu.ShowTitle();
            TitleLogo logo = Menu.GetComponentInChildren<TitleLogo>(true);
            Assert.IsNotNull(logo, "the title has no TitleLogo");
            for (int i = 0; i < 300 && !logo.Ready; i++)
            {
                yield return null;
            }
            Assert.IsTrue(logo.Ready, "the title logo was never baked");
            // The fade in.
            for (float t = 0f; t < 0.8f; t += Time.unscaledDeltaTime)
            {
                yield return null;
            }

            var texture = (Texture2D)logo.Image.texture;
            Assert.IsNotNull(texture, "premise: the logo has no texture");
            // The shots first, so a failing look check still leaves the pictures to look at.
            Directory.CreateDirectory(ShotDir);
            File.WriteAllBytes(Path.Combine(ShotDir, "title_chair_logo.png"), texture.EncodeToPNG());
            yield return Shoot("title_chair_1920x1080.png", 1920, 1080);
            yield return Shoot("title_chair_2400x1080.png", 2400, 1080);
            Color32[] pixels = texture.GetPixels32();
            int w = texture.width;
            int h = texture.height;

            // Nothing at the texture's edges: the pool fades out inside it, never cut by the image's frame.
            float edge = 0f;
            for (int x = 0; x < w; x++)
            {
                edge = Mathf.Max(edge, Mathf.Max(pixels[x].a, pixels[(h - 1) * w + x].a));
            }
            for (int y = 0; y < h; y++)
            {
                edge = Mathf.Max(edge, Mathf.Max(pixels[y * w].a, pixels[y * w + w - 1].a));
            }
            Assert.Less(edge, 8f, "the logo is cut by its frame (alpha on its border)");

            // The pool: a lit warm centre, the shadow darker inside it, a soft edge (many partly covering pixels).
            Vector2Int centre = logo.PoolPixel;
            Vector2Int shadow = logo.ShadowPixel;
            Color pool = pixels[centre.y * w + centre.x];
            Color dark = pixels[shadow.y * w + shadow.x];
            TestContext.WriteLine($"[Step74a] pool {centre} {pool}, shadow {shadow} {dark}, least pool light under the shadow {logo.ShadowInPool:0.00}");
            Assert.Greater(logo.ShadowInPool, 0.2f, "part of the chair's shadow falls outside the pool of light");
            Assert.Greater(pool.a, 0.5f, "the pool of light is not there under the chair");
            Assert.Greater(pool.r, pool.b + 0.15f, "the pool of light is not warm");
            Assert.Greater(pool.r * 0.3f + pool.g * 0.59f + pool.b * 0.11f, 0.55f, "the pool does not read as light");
            Assert.Greater(dark.a, 0.5f, "the shadow falls outside the pool of light");
            float poolLuma = pool.r * 0.3f + pool.g * 0.59f + pool.b * 0.11f;
            float darkLuma = dark.r * 0.3f + dark.g * 0.59f + dark.b * 0.11f;
            Assert.Less(darkLuma, poolLuma * 0.75f, "the chair's shadow does not show in the pool");
            int soft = 0;
            foreach (Color32 p in pixels)
            {
                if (p.a > 20 && p.a < 200)
                {
                    soft++;
                }
            }
            Assert.Greater(soft, w * h / 20, "the pool's edge is not soft");

            // On screen on a 20:9 phone: the logo's chair and pool stay below the top edge.
            var rect = logo.Image.rectTransform;
            float top = rect.anchoredPosition.y + rect.sizeDelta.y * (1f - rect.pivot.y);
            int firstRow = h;
            for (int y = h - 1; y >= 0 && firstRow == h; y--)
            {
                for (int x = 0; x < w; x++)
                {
                    if (pixels[y * w + x].a > 8)
                    {
                        firstRow = y;
                        break;
                    }
                }
            }
            float drawnTop = top - rect.sizeDelta.y * (h - 1 - firstRow) / h;
            TestContext.WriteLine($"[Step74a] logo top {top:0}, drawn top {drawnTop:0} reference units");
            Assert.Less(drawnTop, PhoneHalfHeight - 4f, "the chair leaves the top of a 20:9 phone");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Renders the menu canvas over the scene into a <paramref name="width"/> x <paramref name="height"/> PNG under
        /// <see cref="ShotDir"/> (ProbeTestsCredits' helper): the menu's root canvas switches to Screen Space Camera on the
        /// game camera, which renders into a texture of that size, then everything is put back.
        /// </summary>
        private IEnumerator Shoot(string file, int width, int height)
        {
            Camera cam = main.Camera;
            Canvas root = Menu.GetComponent<Canvas>();
            Assert.IsNotNull(cam, "premise: Main has no camera");
            Assert.IsNotNull(root, "premise: the menu has no root canvas");
            var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32);
            RenderTexture previousTarget = cam.targetTexture;
            float previousPlane = root.planeDistance;
            cam.targetTexture = rt;
            cam.aspect = width / (float)height;
            root.renderMode = RenderMode.ScreenSpaceCamera;
            root.worldCamera = cam;
            root.planeDistance = cam.nearClipPlane + 0.01f;
            try
            {
                yield return null;
                yield return null;
                Canvas.ForceUpdateCanvases();
                cam.ResetProjectionMatrix();
                var request = new RenderPipeline.StandardRequest { destination = rt };
                Assert.IsTrue(RenderPipeline.SupportsRenderRequest(cam, request), "premise: the pipeline cannot render the camera to a texture");
                RenderPipeline.SubmitRenderRequest(cam, request);
                RenderTexture previous = RenderTexture.active;
                RenderTexture.active = rt;
                var shot = new Texture2D(width, height, TextureFormat.RGB24, false);
                shot.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                shot.Apply();
                RenderTexture.active = previous;
                Directory.CreateDirectory(ShotDir);
                File.WriteAllBytes(Path.Combine(ShotDir, file), shot.EncodeToPNG());
                Object.Destroy(shot);
            }
            finally
            {
                root.renderMode = RenderMode.ScreenSpaceOverlay;
                root.worldCamera = null;
                root.planeDistance = previousPlane;
                cam.targetTexture = previousTarget;
                cam.ResetAspect();
                rt.Release();
                Object.Destroy(rt);
            }
            yield return null;
            Canvas.ForceUpdateCanvases();
        }
    }
}
