using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
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
    /// NIGHT pass (2026-11-22): a look test of the night preset on the REAL runtime path (the Boot scene, the real level
    /// through GameState.LoadLevel), for level20 (Midnight Munchies) and level25 (The Showroom), on Haut (PC) and on Moyen
    /// (the mobile default, Mobile_RPAsset, one room light per room). Shots go to Build/shots/night (or OOS_SHOT_DIR):
    /// the start view from the game camera with the HUD drawn over it (the HUD canvas moved to camera space for the shot),
    /// the whole house from above, a close view of the red target (the player furniture) and, for level20, the start view
    /// with the player's floor lamp switched off. On Haut the same start and house views are also shot by day, for
    /// comparison. Numbers (mean luma, the target's redness and contrast) go to a log next to the shots.
    /// It asserts only what the shots rely on and what night must keep: the preset applied, the look's checks (one shadowed
    /// light), no error, the target still reading red, the play area above a readability floor, and on level20 the lamp
    /// mattering (the view clearly darker with it off). Run it alone: --filter NightLook_.
    /// </summary>
    public sealed class ProbeTestsNightLook
    {
        private const int Width = 1280;
        private const int Height = 720;

        /// <summary>The start view's middle at night keeps at least this mean luma (0 to 1; the probe's near-black bound is 0.06).</summary>
        private const float ReadabilityFloor = 0.08f;

        /// <summary>The target's rectangle keeps at least this many clearly red pixels (r over both g and b by <see cref="RedMargin"/>).</summary>
        private const int RedPixelsFloor = 200;

        /// <summary>A pixel reads red when r exceeds both g and b by this much (0 to 255).</summary>
        private const int RedMargin = 30;

        /// <summary>level20: the start view with the lamp off is at most this fraction of the same view with it on.</summary>
        private const float LampOffMax = 0.95f;

        private static string ShotsDir
        {
            get
            {
                string dir = Environment.GetEnvironmentVariable("OOS_SHOT_DIR");
                return Path.GetFullPath(string.IsNullOrEmpty(dir) ? Path.Combine(Application.dataPath, "..", "Build", "shots", "night") : dir);
            }
        }

        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();
        private readonly StringBuilder log = new StringBuilder();

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            RoomLights.Disabled = false;
            errors.Clear();
            log.Clear();
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
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            QualityTier.Apply(new SaveOptions { Quality = SaveOptions.QualityHigh });
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

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        [UnityTest, Timeout(600000)] public IEnumerator NightLook_a_Level20High() { yield return Look("level20", SaveOptions.QualityHigh); }
        [UnityTest, Timeout(600000)] public IEnumerator NightLook_b_Level20Mobile() { yield return Look("level20", SaveOptions.QualityMedium); }
        [UnityTest, Timeout(600000)] public IEnumerator NightLook_c_Level25High() { yield return Look("level25", SaveOptions.QualityHigh); }
        [UnityTest, Timeout(600000)] public IEnumerator NightLook_d_Level25Mobile() { yield return Look("level25", SaveOptions.QualityMedium); }

        /// <summary>Applies the tier, loads <paramref name="id"/> under its lighting, shoots it, then checks what night must keep.</summary>
        private IEnumerator Look(string id, string tier)
        {
            Directory.CreateDirectory(ShotsDir);
            QualityTier.Apply(new SaveOptions { Quality = tier });
            yield return null;
            yield return null;
            string tag = $"{id}_{(tier == SaveOptions.QualityHigh ? "high" : "mobile")}";
            string authored = LevelLoader.Load(id).Lighting ?? "(none)";
            log.AppendLine($"[NightLook] {tag}: authored lighting {authored}, tier {tier} ({QualitySettings.names[QualitySettings.GetQualityLevel()]}), render scale {QualityTier.ActiveRenderScale:0.00}");

            if (tier == SaveOptions.QualityHigh)
            {
                yield return Build(id, LevelDef.LightingDay);
                float dayStart = 0f;
                yield return StartView($"{tag}_start_day", true, l => dayStart = l);
                float dayHouse = HouseView($"{tag}_house_day");
                log.AppendLine($"  day: start luma {dayStart:0.000}, house luma {dayHouse:0.000}");
            }

            // The level's own lighting (night for both levels); forced, so the shots hold whatever a parallel layout pass ships.
            yield return Build(id, LevelDef.LightingNight);
            // The look's checks: one shadowed light and it is the moon. Moyen's Mobile_Renderer has no SSAO by design
            // (QualityTier), so that one check is the PC look's only (first run of this test: it stopped both mobile cases).
            List<string> problems = main.LookProblems();
            if (tier != SaveOptions.QualityHigh)
            {
                problems.RemoveAll(p => p.Contains("SSAO"));
            }
            CollectionAssert.IsEmpty(problems, $"{tag}: the look's checks at night (one shadowed light, the moon is the sun)");
            RoomLights lights = Game.Level.Root.GetComponentInChildren<RoomLights>(true);
            if (lights != null)
            {
                log.AppendLine($"  room lights: {lights.Fixtures.Count} fixtures, {lights.EnabledLights} enabled, night {lights.Night}: "
                    + string.Join(", ", lights.Fixtures.Select(f => $"{f.Room.Id}/{f.Style}#{f.Rank} {f.Light.intensity:0.00} at {f.Light.transform.position}{(f.Light.enabled ? "" : " off")}")));
            }
            float start = 0f;
            yield return StartView($"{tag}_start", true, l => start = l);
            float house = HouseView($"{tag}_house");
            TargetView($"{tag}_target", out int redPixels, out float targetLuma, out float surroundLuma);
            log.AppendLine($"  night: start luma {start:0.000}, house luma {house:0.000}; target red pixels {redPixels}, target luma {targetLuma:0.000} "
                + $"over surround {surroundLuma:0.000}");

            // Tuning variants of the preset, rendered from the same build (moon and ambient scaled, room lights scaled), then
            // put back exactly: they let the preset's numbers be chosen from real captures.
            yield return Variant(tag, "v_darker", 0.75f, 0.75f, 1f);
            yield return Variant(tag, "v_brighter", 1.35f, 1.3f, 1f);
            yield return Variant(tag, "v_pools", 1f, 1f, 1.35f);
            yield return Variant(tag, "v_darker_pools", 0.75f, 0.75f, 1.35f);

            float lampOff = -1f;
            float lampOn = -1f;
            LampLight lamp = Game.Furniture != null ? Game.Furniture.Lamp : null;
            if (lamp != null)
            {
                lamp.SetOn(false);
                yield return null;
                yield return StartView($"{tag}_start_lampoff", false, l => lampOff = l);
                lamp.SetOn(true);
                yield return null;
                yield return StartView($"{tag}_start_lampon_nohud", false, l => lampOn = l);
                log.AppendLine($"  lamp: start luma on {lampOn:0.000}, off {lampOff:0.000} (ratio {lampOff / Mathf.Max(1e-4f, lampOn):0.000}); night light {lamp.Light.intensity:0.00} range {lamp.Light.range:0.0}");
            }

            // The Showroom's hall: its sconce pair on the other choice of the level's "lightWall" field (the authored "-z"
            // against the automatic placement, which picks the north wall), for comparison.
            RoomDef hall = Game.Def.AllRooms().FirstOrDefault(r => r.Id == "magasin");
            if (hall != null)
            {
                string pinned = hall.LightWall;
                hall.LightWall = string.IsNullOrEmpty(pinned) ? "-z" : null;
                Game.Paused = false;
                Game.Restart();
                Game.Paused = true;
                yield return Steps(2);
                yield return null;
                RoomLights south = Game.Level.Root.GetComponentInChildren<RoomLights>(true);
                float southStart = 0f;
                yield return StartView($"{tag}_v_otherwall_start", false, l => southStart = l);
                float southHouse = HouseView($"{tag}_v_otherwall_house");
                log.AppendLine($"  variant v_otherwall (magasin lightWall {hall.LightWall ?? "auto"}): start luma {southStart:0.000}, house luma {southHouse:0.000}; "
                    + (south != null ? string.Join(", ", south.Fixtures.Select(f => $"{f.Room.Id}/{f.Style}#{f.Rank} at {f.Light.transform.position}")) : "no lights"));
                hall.LightWall = pinned;
            }

            string report = log.ToString();
            Debug.Log(report);
            TestContext.WriteLine(report);
            File.WriteAllText(Path.Combine(ShotsDir, tag + "_log.txt"), report);

            Assert.IsTrue(Main.Night, $"{tag}: the night preset is not applied");
            Assert.GreaterOrEqual(start, ReadabilityFloor, $"{tag}: the start view falls below the readability floor");
            Assert.GreaterOrEqual(redPixels, RedPixelsFloor, $"{tag}: the target does not read red at night");
            if (lamp != null)
            {
                Assert.Less(lampOff, lampOn * LampOffMax, $"{tag}: switching the lamp off does not darken its view enough");
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>Loads <paramref name="id"/> if needed, then rebuilds it under <paramref name="lighting"/>, paused (nobody moves).</summary>
        private IEnumerator Build(string id, string lighting)
        {
            Game.Paused = false;
            if (Game.LevelId != id || Game.Def == null)
            {
                Game.LoadLevel(id);
                Assert.AreEqual(id, Game.LevelId);
            }
            Game.Def.Lighting = lighting;
            Game.Restart();
            Game.Paused = true;
            yield return Steps(2);
            yield return null;
            Assert.AreEqual(lighting == LevelDef.LightingNight, Main.Night, $"{id}: the preset applied for lighting '{lighting}'");
        }

        private WallFader Fader => Game.Level.Root.GetComponent<WallFader>();

        /// <summary>
        /// One tuning variant: the moon's intensity, the ambient trilight and every enabled room light scaled, the start view
        /// (no HUD) and the house shot and logged, then everything put back exactly.
        /// </summary>
        private IEnumerator Variant(string tag, string name, float moon, float ambient, float pools)
        {
            Light sun = main.Sun;
            float sunIntensity = sun.intensity;
            Color sky = RenderSettings.ambientSkyColor, equator = RenderSettings.ambientEquatorColor, ground = RenderSettings.ambientGroundColor;
            RoomLights lights = Game.Level.Root.GetComponentInChildren<RoomLights>(true);
            var saved = new List<(Light light, float intensity)>();
            if (lights != null)
            {
                foreach (RoomLights.Fixture f in lights.Fixtures)
                {
                    if (f.Light != null)
                    {
                        saved.Add((f.Light, f.Light.intensity));
                        f.Light.intensity *= pools;
                    }
                }
            }
            sun.intensity = sunIntensity * moon;
            RenderSettings.ambientSkyColor = sky * ambient;
            RenderSettings.ambientEquatorColor = equator * ambient;
            RenderSettings.ambientGroundColor = ground * ambient;
            DynamicGI.UpdateEnvironment();
            float start = 0f;
            yield return StartView($"{tag}_{name}_start", false, l => start = l);
            float house = HouseView($"{tag}_{name}_house");
            log.AppendLine($"  variant {name} (moon x{moon}, ambient x{ambient}, pools x{pools}): start luma {start:0.000}, house luma {house:0.000}");
            sun.intensity = sunIntensity;
            RenderSettings.ambientSkyColor = sky;
            RenderSettings.ambientEquatorColor = equator;
            RenderSettings.ambientGroundColor = ground;
            DynamicGI.UpdateEnvironment();
            foreach ((Light l, float intensity) in saved)
            {
                l.intensity = intensity;
            }
            yield return null;
        }

        /// <summary>The game camera's own start view; with <paramref name="hud"/>, the HUD drawn over it. Reports the middle's mean luma.</summary>
        private IEnumerator StartView(string name, bool hud, Action<float> done)
        {
            Camera cam = main.Camera;
            Game.Camera.Snap();
            yield return null;
            Game.Camera.Snap();
            Canvas root = hud && main.Hud != null ? main.Hud.GetComponent<Canvas>() : null;
            var rt = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32);
            RenderTexture previousTarget = cam.targetTexture;
            float previousPlane = root != null ? root.planeDistance : 0f;
            Color32[] pixels;
            try
            {
                if (root != null)
                {
                    cam.targetTexture = rt;
                    cam.aspect = Width / (float)Height;
                    root.renderMode = RenderMode.ScreenSpaceCamera;
                    root.worldCamera = cam;
                    root.planeDistance = cam.nearClipPlane + 0.02f;
                    yield return null;
                    yield return null;
                    Canvas.ForceUpdateCanvases();
                    Game.Camera.Snap();
                }
                pixels = Render(cam, cam.transform.position, cam.transform.rotation, rt);
            }
            finally
            {
                if (root != null)
                {
                    root.renderMode = RenderMode.ScreenSpaceOverlay;
                    root.worldCamera = null;
                    root.planeDistance = previousPlane;
                }
                cam.targetTexture = previousTarget;
                cam.ResetAspect();
                rt.Release();
                Object.Destroy(rt);
            }
            Save(name, pixels);
            done(MeanLuma(pixels, 0.2f, 0.8f, 0.2f, 0.8f));
            Game.Camera.Snap();
        }

        /// <summary>The whole house from above (60 degrees down), as ProbeTestsNight's house view.</summary>
        private float HouseView(string name)
        {
            Camera cam = main.Camera;
            Rect house = Game.Def.InteriorBounds();
            var mid = new Vector3(house.center.x, 0f, house.center.y);
            float far = Mathf.Max(house.width, house.height) * 1.05f;
            Quaternion top = Quaternion.Euler(60f, 0f, 0f);
            Vector3 high = mid + Vector3.up * 0.6f - top * Vector3.forward * far;
            Color32[] pixels = Render(cam, high, top, null);
            Save(name, pixels);
            Game.Camera.Snap();
            return MeanLuma(pixels, 0f, 1f, 0f, 1f);
        }

        /// <summary>
        /// A close view of the player furniture (the red target) from 1.8 m out toward the middle of its own room and 3 m up
        /// (over the walls: the first run's view from the house's middle crossed the spawn room's wall).
        /// Reports the target rectangle's clearly red pixels, the luma of its middle and the luma of the ring around it.
        /// </summary>
        private void TargetView(string name, out int redPixels, out float targetLuma, out float surroundLuma)
        {
            Camera cam = main.Camera;
            FurnitureController target = Game.Furniture;
            Vector3 p = target.transform.position;
            RoomDef own = Game.Def.RoomAt(p);
            Rect house = Game.Def.InteriorBounds();
            Vector3 toMid = own != null ? new Vector3(own.X - p.x, 0f, own.Z - p.z) : new Vector3(house.center.x - p.x, 0f, house.center.y - p.z);
            Vector3 dir = toMid.sqrMagnitude > 0.01f ? toMid.normalized : Vector3.back;
            Vector3 eye = p + dir * 1.8f + Vector3.up * 3f;
            Quaternion rotation = Quaternion.LookRotation(p + Vector3.up * 0.45f - eye, Vector3.up);

            // The target's screen rectangle (its renderers' bounds) at the shot's aspect.
            float aspect = cam.aspect;
            cam.aspect = Width / (float)Height;
            cam.transform.SetPositionAndRotation(eye, rotation);
            Renderer[] renderers = target.GetComponentsInChildren<Renderer>().Where(r => r.enabled && r is MeshRenderer).ToArray();
            Bounds b = renderers.Length > 0 ? renderers[0].bounds : new Bounds(p, Vector3.one * 0.5f);
            foreach (Renderer r in renderers)
            {
                b.Encapsulate(r.bounds);
            }
            float x0 = 1f, x1 = 0f, y0 = 1f, y1 = 0f;
            for (int k = 0; k < 8; k++)
            {
                Vector3 corner = b.center + Vector3.Scale(b.extents, new Vector3((k & 1) == 0 ? -1f : 1f, (k & 2) == 0 ? -1f : 1f, (k & 4) == 0 ? -1f : 1f));
                Vector3 v = cam.WorldToViewportPoint(corner);
                x0 = Mathf.Min(x0, v.x); x1 = Mathf.Max(x1, v.x);
                y0 = Mathf.Min(y0, v.y); y1 = Mathf.Max(y1, v.y);
            }
            cam.aspect = aspect;
            Color32[] pixels = Render(cam, eye, rotation, null);
            Save(name, pixels);
            Game.Camera.Snap();

            // The middle half of the rectangle (mostly the furniture, little floor) and a ring 0.6 of its size around it.
            float cx = (x0 + x1) * 0.5f, cy = (y0 + y1) * 0.5f, hw = (x1 - x0) * 0.5f, hh = (y1 - y0) * 0.5f;
            redPixels = RedPixels(pixels, cx - hw, cx + hw, cy - hh, cy + hh);
            targetLuma = MeanLuma(pixels, Mathf.Clamp01(cx - hw * 0.5f), Mathf.Clamp01(cx + hw * 0.5f), Mathf.Clamp01(cy - hh * 0.5f), Mathf.Clamp01(cy + hh * 0.5f));
            float outer = MeanLuma(pixels, Mathf.Clamp01(cx - hw * 1.6f), Mathf.Clamp01(cx + hw * 1.6f), Mathf.Clamp01(cy - hh * 1.6f), Mathf.Clamp01(cy + hh * 1.6f));
            float inner = MeanLuma(pixels, Mathf.Clamp01(cx - hw), Mathf.Clamp01(cx + hw), Mathf.Clamp01(cy - hh), Mathf.Clamp01(cy + hh));
            float outerArea = Mathf.Clamp01(cx + hw * 1.6f) - Mathf.Clamp01(cx - hw * 1.6f);
            outerArea *= Mathf.Clamp01(cy + hh * 1.6f) - Mathf.Clamp01(cy - hh * 1.6f);
            float innerArea = (Mathf.Clamp01(cx + hw) - Mathf.Clamp01(cx - hw)) * (Mathf.Clamp01(cy + hh) - Mathf.Clamp01(cy - hh));
            surroundLuma = outerArea > innerArea + 1e-5f ? (outer * outerArea - inner * innerArea) / (outerArea - innerArea) : outer;
        }

        // ----- Rendering -----

        /// <summary>Renders <paramref name="cam"/> from a pose into a fresh frame (walls faded for that pose), or into <paramref name="into"/>.</summary>
        private Color32[] Render(Camera cam, Vector3 position, Quaternion rotation, RenderTexture into)
        {
            float aspect = cam.aspect;
            cam.aspect = Width / (float)Height;
            cam.transform.SetPositionAndRotation(position, rotation);
            WallFader fader = Fader;
            if (fader != null)
            {
                fader.Apply(position);
                fader.DrawFaded(cam);
            }
            RenderTexture rt = into != null ? into : RenderTexture.GetTemporary(Width, Height, 24);
            var request = new RenderPipeline.StandardRequest { destination = rt };
            RenderPipeline.SubmitRenderRequest(cam, request);
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = rt;
            var texture = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
            texture.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
            texture.Apply();
            RenderTexture.active = previous;
            if (into == null)
            {
                RenderTexture.ReleaseTemporary(rt);
            }
            cam.aspect = aspect;
            Color32[] pixels = texture.GetPixels32();
            Object.Destroy(texture);
            return pixels;
        }

        private static void Save(string name, Color32[] pixels)
        {
            var texture = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
            texture.SetPixels32(pixels);
            texture.Apply();
            File.WriteAllBytes(Path.Combine(ShotsDir, name + ".png"), texture.EncodeToPNG());
            Object.Destroy(texture);
        }

        /// <summary>The mean luma (0 to 1) of the region from <paramref name="x0"/> to <paramref name="x1"/> and <paramref name="y0"/> to <paramref name="y1"/> (viewport fractions, y up).</summary>
        private static float MeanLuma(Color32[] pixels, float x0, float x1, float y0, float y1)
        {
            double sum = 0;
            int n = 0;
            Each(pixels, x0, x1, y0, y1, p =>
            {
                sum += (0.2126 * p.r + 0.7152 * p.g + 0.0722 * p.b) / 255.0;
                n++;
            });
            return n > 0 ? (float)(sum / n) : 0f;
        }

        /// <summary>The pixels of a region (viewport fractions) whose r exceeds both g and b by <see cref="RedMargin"/>.</summary>
        private static int RedPixels(Color32[] pixels, float x0, float x1, float y0, float y1)
        {
            int n = 0;
            Each(pixels, Mathf.Clamp01(x0), Mathf.Clamp01(x1), Mathf.Clamp01(y0), Mathf.Clamp01(y1), p =>
            {
                if (p.r - p.g > RedMargin && p.r - p.b > RedMargin)
                {
                    n++;
                }
            });
            return n;
        }

        private static void Each(Color32[] pixels, float x0, float x1, float y0, float y1, Action<Color32> visit)
        {
            int ax = Mathf.Clamp(Mathf.RoundToInt(x0 * Width), 0, Width), bx = Mathf.Clamp(Mathf.RoundToInt(x1 * Width), 0, Width);
            int ay = Mathf.Clamp(Mathf.RoundToInt(y0 * Height), 0, Height), by = Mathf.Clamp(Mathf.RoundToInt(y1 * Height), 0, Height);
            for (int y = ay; y < by; y++)
            {
                for (int x = ax; x < bx; x++)
                {
                    visit(pixels[y * Width + x]);
                }
            }
        }
    }
}
