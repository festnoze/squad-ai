using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Debug = UnityEngine.Debug;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Room lighting on Haut (2026-11-20): a look tool, explicit, never a check. Renders the same game camera views of a few
    /// levels and of the title house under several lighting candidates (the High renderer's SSAO settings, the ambient, the
    /// sun, the secondary room lights), so they can be compared A/B. Driven by a text file, so a new set of candidates needs no
    /// recompilation: TestResults/lighting/config.txt (one "key=value" per line, '#' comments):
    ///   out=&lt;folder&gt;                 where the PNGs go (default TestResults/lighting/shots)
    ///   levels=level4,level12,title_house
    ///   candidate=name|ssao=1;i=1.0;r=0.5;d=0.5;samples=1;blur=0;after=0;down=0;fall=100;amb=1;sun=1;rl=1;rr=1
    /// Keys of a candidate (anything left out keeps the project's own value): ssao 0/1 (the feature on), i intensity, r radius,
    /// d direct lighting strength, samples 0 high 1 medium 2 low, blur 0 bilateral 1 gaussian 2 kawase, after 1 applied after
    /// the opaques, down 1 half resolution, method 0 blue noise 1 interleaved gradient, fall the falloff distance, amb a factor on the ambient trilight, sun a factor on
    /// the sun's intensity, rl / rr factors on the secondary room lights' intensity / range, ceil / ceilr the title ceiling's
    /// Haut contact shade at a wall and its reach (TitleCameraTour; ceil=0 shows the plain ceiling of Bas and Moyen).
    /// Writes &lt;level&gt;_&lt;view&gt;_&lt;candidate&gt;.png per view and candidate, a sheet per view (the candidates in config order,
    /// each tile numbered from 0), and timing.txt (render plus readback per candidate, a rough relative cost).
    /// Everything changed is put back afterwards (the renderer asset's SSAO settings included).
    /// Lighting_a_ is a check (not explicit): the title ceiling's Haut contact shade, on Haut only and following the tier.
    /// </summary>
    public sealed class ProbeTestsLightingShots
    {
        private const string ConfigPath = "TestResults/lighting/config.txt";
        private const int Width = 1280;
        private const int Height = 720;
        private const int Tile = 2;

        private Main main;
        private GameState Game => main.Game;

        private sealed class Candidate
        {
            public string Name;
            public readonly Dictionary<string, float> Values = new Dictionary<string, float>();

            public float Get(string key, float fallback) => Values.TryGetValue(key, out float v) ? v : fallback;

            public bool Has(string key) => Values.ContainsKey(key);
        }

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
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
            RestoreSsao();
            TitleCameraTour.CeilingShadeOverride = null;
            TitleCameraTour.CeilingShadeReachOverride = null;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            SaveStore.ResetForTests();
            yield return null;
        }

        [UnityTest, Explicit("look tool: renders lighting candidates to the folder of TestResults/lighting/config.txt")]
        public IEnumerator Lighting_z_Shots()
        {
            string outDir = Path.Combine("TestResults", "lighting", "shots");
            var levels = new List<string> { "level4", "level12", "level16", TitleCameraTour.LevelId };
            var candidates = new List<Candidate>();
            if (File.Exists(ConfigPath))
            {
                foreach (string raw in File.ReadAllLines(ConfigPath))
                {
                    string line = raw.Trim();
                    if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal))
                    {
                        continue;
                    }
                    int eq = line.IndexOf('=');
                    string key = line.Substring(0, eq).Trim();
                    string value = line.Substring(eq + 1).Trim();
                    if (key == "out")
                    {
                        outDir = value;
                    }
                    else if (key == "levels")
                    {
                        levels = new List<string>(value.Split(','));
                    }
                    else if (key == "candidate")
                    {
                        candidates.Add(Parse(value));
                    }
                }
            }
            if (candidates.Count == 0)
            {
                candidates.Add(new Candidate { Name = "base" });
            }
            Directory.CreateDirectory(outDir);
            CaptureSsao();
            var timing = new List<string>();
            try
            {
                foreach (string id in levels)
                {
                    if (id == TitleCameraTour.LevelId)
                    {
                        yield return Title(outDir, candidates, timing);
                    }
                    else
                    {
                        yield return Level(id, outDir, candidates, timing);
                    }
                }
            }
            finally
            {
                RestoreSsao();
            }
            File.WriteAllLines(Path.Combine(outDir, "timing.txt"), timing);
            Debug.Log("[LightingShots] " + string.Join(" | ", timing));
        }

        /// <summary>
        /// The title ceiling's corners (TitleCameraTour): on Haut the ceiling over the title house is its shaded underside
        /// (darker along the walls), on Bas and Moyen the plain box exactly as before, following the Qualité option at once.
        /// </summary>
        [UnityTest]
        public IEnumerator Lighting_a_TheTitleCeilingIsShadedOnHautOnly()
        {
            var errors = new List<string>();
            void OnLog(string condition, string stack, LogType type)
            {
                if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
                {
                    errors.Add(condition);
                }
            }
            Application.logMessageReceived += OnLog;
            try
            {
                main.Menu.ShowTitle();
                TitleCameraTour tour = main.Camera.GetComponent<TitleCameraTour>();
                Assert.IsNotNull(tour, "premise: the camera has no title tour");
                for (int i = 0; i < 120 && !tour.Active; i++)
                {
                    yield return null;
                }
                Assert.IsTrue(tour.Active, "premise: the title tour never started");
                // CEILING (2026-11-24): the title house now shows its rooms' own lit ceilings (RoomCeilings, SSAO in their
                // corners on Haut) and the tour builds no lid of its own; the shaded lid below is the fallback without them.
                RoomCeilings rooms = RoomCeilings.Of(main.Game.Level);
                if (rooms != null)
                {
                    Assert.IsNull(tour.Ceiling, "the tour built its own lid over the rooms' ceilings");
                    Assert.AreEqual(main.Game.Def.AllRooms().Count, rooms.Count, "one ceiling per room of the title house");
                    for (int i = 0; i < 30; i++)
                    {
                        yield return null;
                    }
                    for (int i = 0; i < rooms.Count; i++)
                    {
                        Assert.AreEqual(1f, rooms.LevelOf(i), 1e-4f, $"{rooms.RoomOf(i).Id}: the ceiling does not show from the tour's eye level");
                        Assert.IsTrue(rooms.RendererOf(i).enabled, $"{rooms.RoomOf(i).Id}: the shown ceiling's renderer is off");
                    }
                    CollectionAssert.IsEmpty(errors, "no error logged");
                    yield break;
                }
                Assert.IsNotNull(tour.Ceiling, "the title house has no ceiling");
                Assert.IsTrue(tour.CeilingShaded, "Haut (the editor default): the ceiling is not shaded");
                MeshFilter filter = tour.Ceiling.GetComponent<MeshFilter>();
                Assert.AreNotSame(PrimitiveKit.BoxMesh, filter.sharedMesh, "Haut: the ceiling is still the plain box");
                Assert.IsNotNull(tour.Ceiling.sharedMaterial.GetTexture("_BaseMap"), "Haut: the shaded ceiling has no shade texture");
                foreach (string tier in new[] { SaveOptions.QualityLow, SaveOptions.QualityMedium, SaveOptions.QualityHigh })
                {
                    QualityTier.Apply(new SaveOptions { Quality = tier });
                    yield return null;
                    yield return null;
                    bool high = tier == SaveOptions.QualityHigh;
                    Assert.AreEqual(high, tour.CeilingShaded, $"{tier}: the ceiling shade");
                    Assert.AreEqual(high, filter.sharedMesh != PrimitiveKit.BoxMesh, $"{tier}: the ceiling mesh");
                    if (!high)
                    {
                        Assert.IsNull(tour.Ceiling.sharedMaterial.GetTexture("_BaseMap"), $"{tier}: the plain ceiling shows a texture");
                    }
                }
                CollectionAssert.IsEmpty(errors, "no error logged");
            }
            finally
            {
                Application.logMessageReceived -= OnLog;
            }
        }

        private static Candidate Parse(string value)
        {
            string[] parts = value.Split('|');
            var c = new Candidate { Name = parts[0].Trim() };
            if (parts.Length > 1)
            {
                foreach (string kv in parts[1].Split(';'))
                {
                    string[] p = kv.Split('=');
                    if (p.Length == 2)
                    {
                        c.Values[p[0].Trim()] = float.Parse(p[1].Trim(), CultureInfo.InvariantCulture);
                    }
                }
            }
            return c;
        }

        // ----- Levels: the game camera on the player's start and on two other rooms -----

        private IEnumerator Level(string id, string outDir, List<Candidate> candidates, List<string> timing)
        {
            Game.Paused = false;
            Game.LoadLevel(id);
            yield return new WaitForFixedUpdate();
            yield return new WaitForFixedUpdate();
            Game.Paused = true;
            FurnitureController chair = Game.Furniture;
            Vector3 start = chair.transform.position;
            float yaw = chair.Yaw;
            var views = new List<(string name, Vector3 at, float yaw, float pitch, float distance)>
            {
                ("start", start, yaw, Tuning.PitchDefault, Tuning.OrbitDistance),
            };
            // The two largest rooms the start is not in, looked at across a corner.
            List<RoomDef> rooms = Game.Def.AllRooms();
            rooms.Sort((a, b) => (b.SizeX * b.SizeZ).CompareTo(a.SizeX * a.SizeZ));
            RoomDef home = Game.Def.RoomAt(start);
            int added = 0;
            foreach (RoomDef r in rooms)
            {
                if (r == home || added >= 2)
                {
                    continue;
                }
                views.Add(($"room_{r.Id}", FreeSpot(new Vector3(r.X, start.y, r.Z)), yaw + 135f + 90f * added, 48f, Tuning.OrbitDistanceMax));
                added++;
            }
            if (added == 0 && home != null)
            {
                views.Add(("start_high", start, yaw + 180f, 58f, Tuning.OrbitDistanceMax));
            }
            foreach (var v in views)
            {
                chair.Teleport(v.at, v.yaw);
                Physics.SyncTransforms();
                Game.Camera.SetDistance(v.distance);
                Game.Camera.SetView(v.yaw, v.pitch);
                yield return null;
                Game.Camera.Snap();
                Camera cam = main.Camera;
                Vector3 position = cam.transform.position;
                Quaternion rotation = cam.transform.rotation;
                var fader = Game.Level.Root.GetComponent<WallFader>();
                yield return Shoot($"{id}_{v.name}", outDir, candidates, timing, v.name == "start", () =>
                {
                    cam.transform.SetPositionAndRotation(position, rotation);
                    cam.ResetProjectionMatrix();
                    fader.Apply(position);
                    fader.DrawFaded(cam);
                });
            }
            chair.Teleport(start, yaw);
            Physics.SyncTransforms();
        }

        private Vector3 FreeSpot(Vector3 focus)
        {
            for (float r = 0f; r < 3f; r += 0.25f)
            {
                for (int a = 0; a < 8; a++)
                {
                    Vector3 p = focus + Quaternion.Euler(0f, a * 45f, 0f) * Vector3.forward * r;
                    if (Game.Def.RoomAt(p) != null && !Physics.CheckSphere(p + Vector3.up * 0.5f, 0.35f, Layers.OccluderMask, QueryTriggerInteraction.Ignore))
                    {
                        return p;
                    }
                }
            }
            return focus;
        }

        // ----- The title house: the tour's eye level camera at a few points of its loop -----

        private IEnumerator Title(string outDir, List<Candidate> candidates, List<string> timing)
        {
            Game.Paused = false;
            main.Menu.ShowTitle();
            TitleCameraTour tour = main.Camera.GetComponent<TitleCameraTour>();
            Assert.IsNotNull(tour, "premise: the camera has no title tour");
            for (int i = 0; i < 120 && !tour.Active; i++)
            {
                yield return null;
            }
            Assert.IsTrue(tour.Active, "premise: the title tour never started");
            tour.enabled = false;
            Camera cam = main.Camera;
            float[] stops = { 2.5f, 8.5f, 17f, 26f };
            for (int s = 0; s < stops.Length; s++)
            {
                tour.Pose(stops[s] % Mathf.Max(1f, tour.Length), out Vector3 position, out Quaternion rotation);
                yield return Shoot($"title_{s}", outDir, candidates, timing, s == 0, () =>
                {
                    cam.transform.SetPositionAndRotation(position, rotation);
                    cam.ResetProjectionMatrix();
                    Matrix4x4 m = cam.projectionMatrix;
                    m[0, 2] = -Tuning.TitleTourLensShift;
                    cam.projectionMatrix = m;
                });
            }
            // The title stays open: keep the title house last in the levels list.
            tour.enabled = true;
            cam.ResetProjectionMatrix();
        }

        // ----- Rendering one view under every candidate -----

        private IEnumerator Shoot(string name, string outDir, List<Candidate> candidates, List<string> timing, bool time, Action pose)
        {
            Camera cam = main.Camera;
            var tiles = new List<Color32[]>();
            var line = new StringBuilder(name).Append(':');
            foreach (Candidate c in candidates)
            {
                Apply(c);
                // Two frames: the ambient probe and the lights settle.
                yield return null;
                yield return null;
                pose();
                Color32[] pixels = Render(cam);
                Save(Path.Combine(outDir, $"{name}_{c.Name}.png"), pixels, Width, Height);
                tiles.Add(pixels);
                if (time)
                {
                    // Rough relative cost: renders each forced to finish by a one pixel readback.
                    const int runs = 6;
                    Render(cam);
                    var watch = Stopwatch.StartNew();
                    for (int k = 0; k < runs; k++)
                    {
                        pose();
                        Render(cam);
                    }
                    watch.Stop();
                    line.Append(' ').Append(c.Name).Append(' ').Append((watch.Elapsed.TotalMilliseconds / runs).ToString("0.0", CultureInfo.InvariantCulture)).Append(" ms");
                }
                Unapply();
            }
            if (time)
            {
                timing.Add(line.ToString());
            }
            SaveSheet(Path.Combine(outDir, $"sheet_{name}.png"), tiles);
        }

        private static Color32[] Render(Camera cam)
        {
            float aspect = cam.aspect;
            cam.aspect = Width / (float)Height;
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

        private static void Save(string file, Color32[] pixels, int w, int h)
        {
            var texture = new Texture2D(w, h, TextureFormat.RGBA32, false);
            texture.SetPixels32(pixels);
            texture.Apply();
            File.WriteAllBytes(file, texture.EncodeToPNG());
            Object.Destroy(texture);
        }

        /// <summary>The candidates of one view at half size, two per row, each numbered in its top left corner.</summary>
        private static void SaveSheet(string file, List<Color32[]> tiles)
        {
            int tw = Width / Tile;
            int th = Height / Tile;
            int cols = tiles.Count > 1 ? 2 : 1;
            int rows = (tiles.Count + cols - 1) / cols;
            int w = tw * cols;
            int h = th * rows;
            var sheet = new Color32[w * h];
            for (int i = 0; i < tiles.Count; i++)
            {
                int ox = (i % cols) * tw;
                // Row 0 at the top of the picture (texture rows go up).
                int oy = (rows - 1 - i / cols) * th;
                Color32[] src = tiles[i];
                for (int y = 0; y < th; y++)
                {
                    for (int x = 0; x < tw; x++)
                    {
                        sheet[(oy + y) * w + ox + x] = src[(y * Tile) * Width + x * Tile];
                    }
                }
                Number(sheet, w, ox + 6, oy + th - 6, i);
            }
            Save(file, sheet, w, h);
        }

        // A 3 x 5 digit font, one row per string, top row first.
        private static readonly string[] Digits =
        {
            "111101101101111", "010110010010111", "111001111100111", "111001111001111", "101101111001001",
            "111100111001111", "111100111101111", "111001001001001", "111101111101111", "111101111001111",
        };

        private static void Number(Color32[] sheet, int w, int left, int top, int n)
        {
            string text = n.ToString(CultureInfo.InvariantCulture);
            const int scale = 4;
            int boxW = text.Length * 4 * scale + scale;
            int boxH = 7 * scale;
            for (int y = 0; y < boxH; y++)
            {
                for (int x = 0; x < boxW; x++)
                {
                    int px = left + x;
                    int py = top - y;
                    if (px >= 0 && px < w && py >= 0 && py * w + px < sheet.Length)
                    {
                        sheet[py * w + px] = new Color32(0, 0, 0, 255);
                    }
                }
            }
            for (int k = 0; k < text.Length; k++)
            {
                string glyph = Digits[text[k] - '0'];
                for (int gy = 0; gy < 5; gy++)
                {
                    for (int gx = 0; gx < 3; gx++)
                    {
                        if (glyph[gy * 3 + gx] != '1')
                        {
                            continue;
                        }
                        for (int sy = 0; sy < scale; sy++)
                        {
                            for (int sx = 0; sx < scale; sx++)
                            {
                                int px = left + scale + k * 4 * scale + gx * scale + sx;
                                int py = top - scale - gy * scale - sy;
                                if (px >= 0 && px < w && py >= 0 && py * w + px < sheet.Length)
                                {
                                    sheet[py * w + px] = new Color32(255, 255, 255, 255);
                                }
                            }
                        }
                    }
                }
            }
        }

        // ----- Applying a candidate -----

        private Color savedSky, savedEquator, savedGround;
        private float savedSun;
        private readonly List<(Light light, float intensity, float range)> savedRoom = new List<(Light, float, float)>();

        private void Apply(Candidate c)
        {
            ApplySsao(c);
            savedSky = RenderSettings.ambientSkyColor;
            savedEquator = RenderSettings.ambientEquatorColor;
            savedGround = RenderSettings.ambientGroundColor;
            float amb = c.Get("amb", 1f);
            RenderSettings.ambientSkyColor = savedSky * amb;
            RenderSettings.ambientEquatorColor = savedEquator * amb;
            RenderSettings.ambientGroundColor = savedGround * amb;
            DynamicGI.UpdateEnvironment();
            savedSun = main.Sun.intensity;
            main.Sun.intensity = savedSun * c.Get("sun", 1f);
            TitleCameraTour.CeilingShadeOverride = c.Has("ceil") ? c.Get("ceil", 0f) : (float?)null;
            TitleCameraTour.CeilingShadeReachOverride = c.Has("ceilr") ? c.Get("ceilr", 0f) : (float?)null;
            TitleCameraTour tour = main.Camera.GetComponent<TitleCameraTour>();
            if (tour != null)
            {
                tour.RefreshCeiling();
            }
            savedRoom.Clear();
            RoomLights lights = Game.Level != null ? Game.Level.Root.GetComponentInChildren<RoomLights>(true) : null;
            if (lights != null)
            {
                foreach (RoomLights.Fixture f in lights.Fixtures)
                {
                    if (f.Light == null)
                    {
                        continue;
                    }
                    savedRoom.Add((f.Light, f.Light.intensity, f.Light.range));
                    f.Light.intensity *= c.Get("rl", 1f);
                    f.Light.range *= c.Get("rr", 1f);
                }
            }
        }

        private void Unapply()
        {
            RenderSettings.ambientSkyColor = savedSky;
            RenderSettings.ambientEquatorColor = savedEquator;
            RenderSettings.ambientGroundColor = savedGround;
            DynamicGI.UpdateEnvironment();
            main.Sun.intensity = savedSun;
            foreach ((Light light, float intensity, float range) in savedRoom)
            {
                if (light != null)
                {
                    light.intensity = intensity;
                    light.range = range;
                }
            }
            savedRoom.Clear();
            TitleCameraTour.CeilingShadeOverride = null;
            TitleCameraTour.CeilingShadeReachOverride = null;
            TitleCameraTour tour = main.Camera.GetComponent<TitleCameraTour>();
            if (tour != null)
            {
                tour.RefreshCeiling();
            }
            RestoreSsao();
        }

        // The High renderer's SSAO feature, through reflection (its settings are internal to URP, and this assembly does not
        // reference the URP runtime).
        private static readonly string[] SsaoFields =
        {
            "Intensity", "Radius", "DirectLightingStrength", "Falloff", "Samples", "BlurQuality", "AfterOpaque", "Downsample", "AOMethod",
        };

        private object ssaoFeature;
        private object ssaoSettings;
        private bool ssaoActive;
        private readonly Dictionary<string, object> ssaoSaved = new Dictionary<string, object>();

        private void CaptureSsao()
        {
            ssaoFeature = null;
            ssaoSettings = null;
            ssaoSaved.Clear();
            RenderPipelineAsset asset = GraphicsSettings.currentRenderPipeline;
            if (asset == null)
            {
                return;
            }
            FieldInfo list = asset.GetType().GetField("m_RendererDataList", BindingFlags.NonPublic | BindingFlags.Instance);
            var datas = list != null ? list.GetValue(asset) as Array : null;
            object data = datas != null && datas.Length > 0 ? datas.GetValue(0) : null;
            var features = data?.GetType().GetProperty("rendererFeatures")?.GetValue(data) as IList;
            if (features == null)
            {
                return;
            }
            foreach (object f in features)
            {
                if (f != null && f.GetType().Name == "ScreenSpaceAmbientOcclusion")
                {
                    ssaoFeature = f;
                    ssaoSettings = f.GetType().GetField("m_Settings", BindingFlags.NonPublic | BindingFlags.Instance)?.GetValue(f);
                }
            }
            if (ssaoSettings == null)
            {
                Debug.LogWarning("[LightingShots] no SSAO feature found on the active renderer");
                return;
            }
            ssaoActive = (bool)ssaoFeature.GetType().GetProperty("isActive").GetValue(ssaoFeature);
            foreach (string field in SsaoFields)
            {
                ssaoSaved[field] = SsaoField(field).GetValue(ssaoSettings);
            }
            Debug.Log("[LightingShots] SSAO as found: active " + ssaoActive + ", " + string.Join(", ", SsaoFields.Select(f => f + " " + ssaoSaved[f])));
        }

        private FieldInfo SsaoField(string name)
        {
            return ssaoSettings.GetType().GetField(name, BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Public);
        }

        private void ApplySsao(Candidate c)
        {
            if (ssaoSettings == null)
            {
                return;
            }
            if (c.Has("ssao"))
            {
                ssaoFeature.GetType().GetMethod("SetActive").Invoke(ssaoFeature, new object[] { c.Get("ssao", 1f) > 0.5f });
            }
            SetFloat("Intensity", c, "i");
            SetFloat("Radius", c, "r");
            SetFloat("DirectLightingStrength", c, "d");
            SetFloat("Falloff", c, "fall");
            SetEnum("Samples", c, "samples");
            SetEnum("BlurQuality", c, "blur");
            SetBool("AfterOpaque", c, "after");
            SetBool("Downsample", c, "down");
            SetEnum("AOMethod", c, "method");
        }

        private void SetFloat(string field, Candidate c, string key)
        {
            if (c.Has(key))
            {
                SsaoField(field).SetValue(ssaoSettings, c.Get(key, 0f));
            }
        }

        private void SetEnum(string field, Candidate c, string key)
        {
            if (c.Has(key))
            {
                FieldInfo f = SsaoField(field);
                f.SetValue(ssaoSettings, Enum.ToObject(f.FieldType, Mathf.RoundToInt(c.Get(key, 0f))));
            }
        }

        private void SetBool(string field, Candidate c, string key)
        {
            if (c.Has(key))
            {
                SsaoField(field).SetValue(ssaoSettings, c.Get(key, 0f) > 0.5f);
            }
        }

        private void RestoreSsao()
        {
            if (ssaoSettings == null)
            {
                return;
            }
            foreach (KeyValuePair<string, object> kv in ssaoSaved)
            {
                SsaoField(kv.Key).SetValue(ssaoSettings, kv.Value);
            }
            ssaoFeature.GetType().GetMethod("SetActive").Invoke(ssaoFeature, new object[] { ssaoActive });
        }
    }
}
