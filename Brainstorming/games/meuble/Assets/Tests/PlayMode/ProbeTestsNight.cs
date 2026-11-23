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
    /// Levels v2 (D25, task C10): the night lighting preset ("lighting": "night", visual only) on the real Boot scene.
    /// Night_a renders level20's start view and its whole house by day and by night (the level's own Def forced either way,
    /// so the test holds before and after level20's data carries the key): the play area at night is clearly darker than
    /// by day and still above a readability floor, the vision cones change as many pixels as by day, the vision results are
    /// identical (no rule reads the preset) and the sun stays the one shadowed light. The shots go to Build/shots/night.
    /// Night_b checks the preset's parts on test_lights (one room of each type, windows): the moon, the ambient at about
    /// Main.NightAmbientFactor of the day's, every room light on at its full built intensity, Bas keeping one light per
    /// room, the dark blue windows, the tinted garden and sky, the clear colour; then a day level puts the day look back
    /// exactly.
    /// </summary>
    public sealed class ProbeTestsNight
    {
        private const string NightLevel = "level20";
        private const string TestLevel = "test_lights";
        private const string DayLevel = "level4";

        /// <summary>The play area's mean luma (0 to 1) at night stays at least this (the probe's near-black bound is 0.06).</summary>
        private const float ReadabilityFloor = 0.11f;

        /// <summary>The play area's mean luma at night is at most this fraction of the same view by day.</summary>
        private const float NightOverDayMax = 0.8f;

        /// <summary>The cones change at least this fraction of the pixels at night that they change by day.</summary>
        private const float ConeKeep = 0.6f;

        private const int Width = 1280;
        private const int Height = 720;

        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();

        private static string ShotsDir => Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Build", "shots", "night"));

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            RoomLights.Disabled = false;
            errors.Clear();
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
            Assert.IsNotNull(Game.Level, "the level was never built");
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            RoomLights.Disabled = false;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
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

        /// <summary>Loads <paramref name="id"/>, then rebuilds it with its Def's lighting set to <paramref name="lighting"/>.</summary>
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
            // Paused at once: nobody moves, so the day and night builds are compared in the same state.
            Game.Paused = true;
            yield return Steps(2);
            Assert.AreEqual(lighting == LevelDef.LightingNight, Main.Night, $"{id}: the preset applied for lighting '{lighting}'");
        }

        private RoomLights Lights => Game.Level.Root.GetComponentInChildren<RoomLights>(true);

        // ----- a: level20 by day and by night -----

        [UnityTest]
        public IEnumerator Night_a_Level20IsClearlyDarkerAtNightAndStillReadable()
        {
            Directory.CreateDirectory(ShotsDir);
            yield return Build(NightLevel, LevelDef.LightingDay);
            string authored = LevelLoader.Load(NightLevel).Lighting ?? "(none)";
            List<string> visionDay = Sweep();
            Measure day = null;
            yield return Shots("day", m => day = m);

            yield return Build(NightLevel, LevelDef.LightingNight);
            CollectionAssert.IsEmpty(main.LookProblems(), "night: the look's checks (one shadowed light, the moon is the sun)");
            List<string> visionNight = Sweep();
            Measure night = null;
            yield return Shots("night", m => night = m);

            string report = $"[Night_a] level20 (authored lighting {authored}): start play area luma day {day.Start:0.000}, night {night.Start:0.000} "
                + $"(ratio {night.Start / Mathf.Max(1e-4f, day.Start):0.000}, floor {ReadabilityFloor}, max ratio {NightOverDayMax}); whole frame day "
                + $"{day.StartFrame:0.000}, night {night.StartFrame:0.000}; house view day {day.House:0.000}, night {night.House:0.000}; cone pixels day "
                + $"{day.ConePixels}, night {night.ConePixels} (mean delta day {day.ConeDelta:0.0}, night {night.ConeDelta:0.0})";
            Debug.Log(report);
            TestContext.WriteLine(report);
            File.WriteAllText(Path.Combine(ShotsDir, "night_log.txt"), report);

            Assert.Less(night.Start, day.Start * NightOverDayMax, "night: the start view is not clearly darker than by day");
            Assert.GreaterOrEqual(night.Start, ReadabilityFloor, "night: the play area falls below the readability floor");
            Assert.Less(night.House, day.House, "night: the house view is not darker than by day");
            Assert.Greater(day.ConePixels, 0, "premise: the cones show in the house view by day");
            Assert.GreaterOrEqual(night.ConePixels, day.ConePixels * ConeKeep, "night: the vision cones lost their readability");
            Assert.AreEqual(visionDay.Count, visionNight.Count, "premise: same vision sweep");
            Assert.Greater(visionDay.Count(s => s.Contains(" True ")), 0, "premise: the sweep sees the player somewhere");
            for (int i = 0; i < visionDay.Count; i++)
            {
                Assert.AreEqual(visionDay[i], visionNight[i], "night: the vision changed with the lighting preset (visual only)");
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        private sealed class Measure
        {
            public float Start;
            public float StartFrame;
            public float House;
            public int ConePixels;
            public float ConeDelta;
        }

        /// <summary>The start view (the play area: the middle of the frame) and the whole house with and without the cones.</summary>
        private IEnumerator Shots(string tag, Action<Measure> done)
        {
            var m = new Measure();
            Game.Paused = true;
            Camera cam = main.Camera;
            var fader = Game.Level.Root.GetComponent<WallFader>();
            Game.Camera.Snap();
            yield return null;
            Game.Camera.Snap();
            Vector3 position = cam.transform.position;
            Quaternion rotation = cam.transform.rotation;
            Color32[] start = Render(cam, position, rotation, fader);
            Save($"level20_start_{tag}", start);
            m.Start = MeanLuma(start, 0.2f, 0.8f, 0.2f, 0.8f);
            m.StartFrame = MeanLuma(start, 0f, 1f, 0f, 1f);

            Rect house = Game.Def.InteriorBounds();
            var mid = new Vector3(house.center.x, 0f, house.center.y);
            float far = Mathf.Max(house.width, house.height) * 1.05f;
            Quaternion top = Quaternion.Euler(60f, 0f, 0f);
            Vector3 high = mid + Vector3.up * 0.6f - top * Vector3.forward * far;
            Color32[] withCones = Render(cam, high, top, fader);
            Save($"level20_house_{tag}", withCones);
            m.House = MeanLuma(withCones, 0f, 1f, 0f, 1f);
            List<GameObject> cones = Game.Level.Cones.Where(c => c != null && c.gameObject.activeSelf).Select(c => c.gameObject).ToList();
            foreach (GameObject c in cones)
            {
                c.SetActive(false);
            }
            Color32[] noCones = Render(cam, high, top, fader);
            foreach (GameObject c in cones)
            {
                c.SetActive(true);
            }
            double sum = 0;
            for (int i = 0; i < withCones.Length; i++)
            {
                int d = Math.Abs(Luma(withCones[i]) - Luma(noCones[i])) + Math.Abs(withCones[i].b - noCones[i].b);
                if (d > 8)
                {
                    m.ConePixels++;
                    sum += d;
                }
            }
            m.ConeDelta = m.ConePixels > 0 ? (float)(sum / m.ConePixels) : 0f;
            Game.Camera.Snap();
            yield return null;
            done(m);
        }

        /// <summary>The player furniture on a grid over the house, each watcher's vision of it (as ProbeTestsM8Lights' sweep).</summary>
        private List<string> Sweep()
        {
            var results = new List<string>();
            FurnitureController chair = Game.Furniture;
            Vector3 home = chair.transform.position;
            float yaw = chair.Yaw;
            Rect box = Game.Def.InteriorBounds();
            var sb = new StringBuilder();
            for (float x = box.xMin + 0.3f; x < box.xMax; x += 0.9f)
            {
                for (float z = box.yMin + 0.3f; z < box.yMax; z += 0.9f)
                {
                    if (Game.Def.RoomAt(new Vector3(x, 0f, z)) == null)
                    {
                        continue;
                    }
                    chair.Teleport(new Vector3(x, 0f, z), 45f);
                    Physics.SyncTransforms();
                    foreach (Vision v in Game.Level.Visions)
                    {
                        bool sees = v.Step(chair);
                        sb.Clear().Append(x.ToString("0.00")).Append(',').Append(z.ToString("0.00")).Append(' ').Append(v.name).Append(' ').Append(sees)
                            .Append(' ').Append(v.Range.ToString("0.0000"));
                        foreach (bool s in v.SampleVisible)
                        {
                            sb.Append(s ? '1' : '0');
                        }
                        results.Add(sb.ToString());
                    }
                }
            }
            chair.Teleport(home, yaw);
            Physics.SyncTransforms();
            return results;
        }

        // ----- b: the preset's parts, and the day look put back -----

        [UnityTest]
        public IEnumerator Night_b_ThePresetDimsTheMoonAndAmbientLightsTheRoomsAndTintsTheOutside()
        {
            yield return Build(TestLevel, LevelDef.LightingDay);
            Light sun = main.Sun;
            Color daySun = sun.color;
            float daySunIntensity = sun.intensity;
            Quaternion daySunRotation = sun.transform.rotation;
            Color daySky = RenderSettings.ambientSkyColor;
            Color dayEquator = RenderSettings.ambientEquatorColor;
            Color dayGround = RenderSettings.ambientGroundColor;
            Color dayClear = main.Camera.backgroundColor;
            Assert.AreEqual(Tuning.LookSunIntensity, daySunIntensity, 1e-6f, "premise: the day sun");
            AssertOutside(WindowImage.Colour, GardenBackdrop.Tint, "day");
            Assert.AreEqual(new Color(WindowImage.Intensity, WindowImage.Intensity, WindowImage.Intensity, 1f), WindowImage.Colour, "day: the window's neutral factor");

            yield return Build(TestLevel, LevelDef.LightingNight);
            // The moon: the same one shadowed directional light, dimmer, cooler, lower.
            CollectionAssert.IsEmpty(main.LookProblems(), "night: the look's checks");
            Assert.Less(sun.intensity, daySunIntensity * 0.5f, "night: the moon is not dim");
            Assert.Greater(sun.color.b, sun.color.r + 0.2f, "night: the moon is not cool");
            Assert.Less(Vector3.Angle(-sun.transform.forward, Vector3.up), Vector3.Angle(-(daySunRotation * Vector3.forward), Vector3.up) + 30f,
                "premise: the moon is above the horizon");
            Assert.Greater(Vector3.Angle(-sun.transform.forward, Vector3.up), Vector3.Angle(-(daySunRotation * Vector3.forward), Vector3.up),
                "night: the moon is not lower than the sun");
            // The ambient at about Main.NightAmbientFactor of the day's, and bluer.
            foreach ((Color night, Color dayColour, string name) in new[]
            {
                (RenderSettings.ambientSkyColor, daySky, "sky"), (RenderSettings.ambientEquatorColor, dayEquator, "equator"),
                (RenderSettings.ambientGroundColor, dayGround, "ground"),
            })
            {
                float ratio = night.grayscale / Mathf.Max(1e-4f, dayColour.grayscale);
                Assert.That(ratio, Is.InRange(Main.NightAmbientFactor - 0.08f, Main.NightAmbientFactor + 0.08f), $"night: the ambient {name} ratio");
                Assert.Greater(night.b / Mathf.Max(1e-4f, night.r), dayColour.b / Mathf.Max(1e-4f, dayColour.r), $"night: the ambient {name} is not bluer");
            }
            // Every room light on at its full built intensity on Haut (the editor default).
            RoomLights lights = Lights;
            Assert.IsNotNull(lights, "premise: test_lights has room lights");
            Assert.IsTrue(lights.Night, "night: the room lights were not built for the night");
            Assert.AreEqual(lights.Fixtures.Count, lights.EnabledLights, "night on Haut: a room light is off");
            Assert.IsTrue(lights.Fixtures.All(f => Mathf.Approximately(f.Light.intensity, f.Intensity)), "night: a room light is not at its full intensity");
            // The dark blue windows, the tinted garden and sky, the clear colour.
            Assert.AreEqual(WindowImage.NightColour, WindowImage.Colour, "night: the windows' factor");
            Assert.AreEqual(GardenBackdrop.NightTint, GardenBackdrop.Tint, "night: the garden's tint");
            AssertOutside(WindowImage.NightColour, GardenBackdrop.NightTint, "night");
            Assert.Greater(WindowImage.NightColour.b, WindowImage.NightColour.r + 0.2f, "night: the windows are not blue");
            Assert.Less(WindowImage.NightColour.maxColorComponent, 1f, "night: a window feeds the bloom");
            Assert.AreEqual(GardenBackdrop.ClearColour, main.Camera.backgroundColor, "night: the clear colour is not the night sky");
            Assert.Less(main.Camera.backgroundColor.grayscale, dayClear.grayscale * 0.5f, "night: the clear colour is not dark");

            // Bas keeps one light per room at night (none by day), Moyen one, Haut all.
            var tiers = new[] { (SaveOptions.QualityLow, 1), (SaveOptions.QualityMedium, 1), (SaveOptions.QualityHigh, RoomLights.MaxPerRoom) };
            foreach ((string tier, int perRoom) in tiers)
            {
                QualityTier.Apply(new SaveOptions { Quality = tier });
                yield return null;
                yield return null;
                Assert.AreEqual(perRoom, RoomLights.AllowedPerRoom(tier, true), $"{tier}: the night allowance");
                foreach (RoomDef room in Game.Def.AllRooms())
                {
                    List<RoomLights.Fixture> mine = Lights.Fixtures.Where(f => f.Room == room).ToList();
                    int on = mine.Count(f => f.Light.enabled);
                    Assert.AreEqual(Mathf.Min(perRoom, mine.Count), on, $"night {tier}: {room.Id} has {on} lights on of {mine.Count}");
                }
            }
            Assert.AreEqual(0, RoomLights.AllowedPerRoom(SaveOptions.QualityLow, false), "day: Bas keeps no light");
            QualityTier.Apply(new SaveOptions { Quality = SaveOptions.QualityHigh });
            yield return null;

            // A day level puts the day look back exactly.
            Game.LoadLevel(DayLevel);
            yield return Steps(2);
            Assert.IsFalse(Main.Night, "day level: the night preset stayed");
            Assert.AreEqual(daySun, sun.color, "day level: the sun colour");
            Assert.AreEqual(daySunIntensity, sun.intensity, 1e-6f, "day level: the sun intensity");
            Assert.Less(Quaternion.Angle(daySunRotation, sun.transform.rotation), 0.01f, "day level: the sun direction");
            Assert.AreEqual(daySky, RenderSettings.ambientSkyColor, "day level: the ambient sky");
            Assert.AreEqual(dayEquator, RenderSettings.ambientEquatorColor, "day level: the ambient equator");
            Assert.AreEqual(dayGround, RenderSettings.ambientGroundColor, "day level: the ambient ground");
            Assert.AreEqual(dayClear, main.Camera.backgroundColor, "day level: the clear colour");
            AssertOutside(WindowImage.Colour, GardenBackdrop.Tint, "day level");
            Assert.IsFalse(Lights.Night, "day level: the room lights think it is night");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>Every window picture and the garden ring of the level carry <paramref name="window"/> and <paramref name="garden"/>.</summary>
        private void AssertOutside(Color window, Color garden, string when)
        {
            int baseColor = Shader.PropertyToID("_BaseColor");
            int windows = 0;
            var block = new MaterialPropertyBlock();
            foreach (MeshRenderer r in Game.Level.Root.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (r.name == "WindowPane" && r.HasPropertyBlock())
                {
                    r.GetPropertyBlock(block, 0);
                    if (WindowImage.Shows(block))
                    {
                        windows++;
                        AssertClose(window, block.GetColor(baseColor), $"{when}: a window's factor");
                    }
                }
                else if (r.name == GardenBackdrop.RendererName && r.HasPropertyBlock())
                {
                    r.GetPropertyBlock(block);
                    AssertClose(garden, block.GetColor(baseColor), $"{when}: the garden ring's tint");
                }
            }
            if (Game.LevelId == TestLevel)
            {
                Assert.Greater(windows, 0, $"premise: {TestLevel} shows window pictures ({when})");
            }
        }

        private static void AssertClose(Color expected, Color actual, string message)
        {
            float d = Mathf.Max(Mathf.Max(Mathf.Abs(expected.r - actual.r), Mathf.Abs(expected.g - actual.g)), Mathf.Abs(expected.b - actual.b));
            Assert.Less(d, 2e-3f, $"{message}: expected {expected}, got {actual}");
        }

        // ----- Rendering -----

        private static Color32[] Render(Camera cam, Vector3 position, Quaternion rotation, WallFader fader)
        {
            float aspect = cam.aspect;
            cam.aspect = Width / (float)Height;
            cam.transform.SetPositionAndRotation(position, rotation);
            fader.Apply(position);
            fader.DrawFaded(cam);
            RenderTexture rt = RenderTexture.GetTemporary(Width, Height, 24);
            var request = new RenderPipeline.StandardRequest { destination = rt };
            RenderPipeline.SubmitRenderRequest(cam, request);
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = rt;
            var texture = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
            texture.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
            texture.Apply();
            RenderTexture.active = previous;
            RenderTexture.ReleaseTemporary(rt);
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

        /// <summary>The mean luma (0 to 1) of the frame's region from <paramref name="x0"/> to <paramref name="x1"/> and <paramref name="y0"/> to <paramref name="y1"/> (fractions).</summary>
        private static float MeanLuma(Color32[] pixels, float x0, float x1, float y0, float y1)
        {
            int ax = Mathf.RoundToInt(x0 * Width), bx = Mathf.RoundToInt(x1 * Width);
            int ay = Mathf.RoundToInt(y0 * Height), by = Mathf.RoundToInt(y1 * Height);
            double sum = 0;
            int n = 0;
            for (int y = ay; y < by; y++)
            {
                for (int x = ax; x < bx; x++)
                {
                    Color32 p = pixels[y * Width + x];
                    sum += (0.2126 * p.r + 0.7152 * p.g + 0.0722 * p.b) / 255.0;
                    n++;
                }
            }
            return n > 0 ? (float)(sum / n) : 0f;
        }

        private static int Luma(Color32 c)
        {
            return (c.r * 299 + c.g * 587 + c.b * 114) / 1000;
        }
    }
}
