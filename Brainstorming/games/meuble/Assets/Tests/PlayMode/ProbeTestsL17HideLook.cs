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
    /// L17HIDE (2026-11-23): a look test of the long gallery of level19, the 17th card of the level select (levels.json
    /// order), where the stool hides only in the three tall wardrobes. Its low cabinets read as small wardrobes a stool
    /// could fit in, so they became low open bookcases (same boxes, same colliders, so the same sight blocking). Shots go to
    /// Build/shots/l17 (or OOS_SHOT_DIR) from the real runtime path (Boot scene, GameState.LoadLevel), paused: the gallery
    /// from above the salon wall, and a low view along it at the stool's eye. It asserts only what the shots rely on: no
    /// cabinet left in the gallery, three bookcases and three wardrobes there, no error. Run it alone: --filter L17HideLook_.
    /// </summary>
    public sealed class ProbeTestsL17HideLook
    {
        private const int Width = 1280;
        private const int Height = 720;
        private const string LevelId = "level19";
        private const string GalleryId = "galerie";

        private static string ShotsDir
        {
            get
            {
                string dir = Environment.GetEnvironmentVariable("OOS_SHOT_DIR");
                return Path.GetFullPath(string.IsNullOrEmpty(dir) ? Path.Combine(Application.dataPath, "..", "Build", "shots", "l17") : dir);
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
        public IEnumerator L17HideLook_Corridor()
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

            RoomDef gallery = Game.Def.AllRooms().FirstOrDefault(r => r.Id == GalleryId);
            Assert.IsNotNull(gallery, "premise: level19 has its gallery");
            var inGallery = Game.Def.Props.Where(p => Game.Def.RoomAt(new Vector3(p.X, 0f, p.Z)) == gallery).ToList();
            string listing = string.Join(", ", inGallery.Select(p => $"{p.Name} {p.Kind} ({p.X:0.00}, {p.Z:0.00}) {p.SizeX:0.00}x{p.SizeY:0.00}x{p.SizeZ:0.00}"));
            Debug.Log("[L17HideLook] gallery props: " + listing);

            float midZ = gallery.Z;
            Shoot("l17_corridor_high", new Vector3(8.0f, 3.4f, midZ + 3.6f), new Vector3(7.0f, 0.45f, midZ - 0.9f));
            Shoot("l17_corridor_low", new Vector3(14.5f, 0.75f, midZ + 0.7f), new Vector3(4.0f, 0.5f, midZ - 0.8f));

            Assert.IsFalse(inGallery.Exists(p => p.Kind == PropKinds.Cabinet), "a cabinet (a small wardrobe look) is left in the gallery: " + listing);
            Assert.AreEqual(3, inGallery.Count(p => p.Kind == PropKinds.Bookshelf), "the gallery's three bookcases: " + listing);
            Assert.AreEqual(3, inGallery.Count(p => p.Kind == WardrobeRule.Kind), "the gallery's three wardrobes: " + listing);
            CollectionAssert.IsEmpty(errors, "no error logged");
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
