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
    /// Floor dust (product owner request, 2026-11-20, docs/m9/FLOORS_WALLS.md section 10), on the real Boot scene: the
    /// Haut tier alone draws the dusty floor variant and builds the level's floor map (Step97a); the map follows the
    /// walls, the corners, the doorways and the traffic paths (Step97b); only the floors change, subtly, never a wall or
    /// a rug (Step97c); shots of every floor family, Haut with and without the dust and Moyen (Step97z).
    /// </summary>
    public sealed class ProbeTestsM9FloorDust
    {
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
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            FloorDust.SetSuppressed(false);
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
            FloorDust.SetSuppressed(false);
            InputReader.ResetInjections();
            // Also puts the quality back to the platform default (Haut in the editor) for the next test.
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
                if (main.Game.Camera != null)
                {
                    main.Game.Camera.enabled = true;
                }
            }
            GamePause.IsPaused = false;
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

        private static void SetQuality(string quality)
        {
            SaveOptions o = SaveStore.Options;
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = quality, Difficulty = o.Difficulty,
                Language = o.Language, Walls = o.Walls, WallOpacity = o.WallOpacity,
            });
        }

        private static void SetWalls(string walls)
        {
            SaveOptions o = SaveStore.Options;
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty,
                Language = o.Language, Walls = walls, WallOpacity = o.WallOpacity,
            });
        }

        private WallFader Fader => Game.Level.Root.GetComponent<WallFader>();

        // ----- 97a: the Haut tier alone -----

        /// <summary>
        /// The PC default (Haut) draws the dusty variant with the current level's map; Moyen (the Android default) and Bas
        /// turn it off at once and build no map, not even over a restart; back on Haut the current level's map is built at
        /// once. The shader's floor test matches the arrays: slice 12 on are exactly the floor looks.
        /// </summary>
        [UnityTest]
        public IEnumerator Step97a_FloorDustOnlyOnTheHighTier()
        {
            // The shader's FLOOR_DUST_FIRST_FINISH: the floor looks are the slices from FirstFloorSlice on, and only them.
            var floors = new HashSet<Surface> { TextureLibrary.FloorSurface(null, false), TextureLibrary.FloorSurface(null, true) };
            foreach (string finish in RoomDef.FloorFinishes)
            {
                floors.Add(TextureLibrary.FloorSurface(finish, finish == RoomDef.CarpetFinish));
            }
            for (int i = 0; i < WallArray.Slices.Length; i++)
            {
                Assert.AreEqual(i >= FloorDust.FirstFloorSlice, floors.Contains(WallArray.Slices[i]),
                    $"slice {i} ({WallArray.Slices[i]}): the floor dust's first floor slice no longer splits walls from floors");
            }
            Assert.AreEqual(SaveOptions.QualityHigh, SaveOptions.DefaultQuality(true), "premise: Android starts on Haut (2026-11-25)");

            Assert.AreEqual(SaveOptions.QualityHigh, QualityTier.Applied, "premise: the editor plays on Haut");
            Assert.IsTrue(FloorDust.TierOn, "Haut: the floor dust tier is off");
            Assert.IsTrue(FloorDust.KeywordOn, "Haut: the dusty floor variant is not drawn");
            Assert.IsNotNull(FloorDust.Map, "Haut: the level has no floor map");
            AssertMapCovers(Game.Def, "Haut");

            foreach (string tier in new[] { SaveOptions.QualityMedium, SaveOptions.QualityLow })
            {
                SetQuality(tier);
                Assert.AreEqual(tier, QualityTier.Applied, $"premise: {tier} applied");
                Assert.IsFalse(FloorDust.KeywordOn, $"{tier}: the dusty floor variant is still drawn");
                int builds = FloorDust.Builds;
                Game.Restart();
                yield return Frames(3);
                Assert.IsFalse(FloorDust.KeywordOn, $"{tier}: a restart turned the dust on");
                Assert.AreEqual(builds, FloorDust.Builds, $"{tier}: a restart built a floor map (Bas and Moyen must pay nothing)");
                Assert.IsNull(FloorDust.Map, $"{tier}: the rebuilt level has a floor map");
            }

            int before = FloorDust.Builds;
            SetQuality(SaveOptions.QualityHigh);
            Assert.IsTrue(FloorDust.KeywordOn, "back on Haut: the dusty floor variant is not drawn at once");
            Assert.AreEqual(before + 1, FloorDust.Builds, "back on Haut: the current level's map was not built at once");
            AssertMapCovers(Game.Def, "back on Haut");
            yield return Load("level21");
            Assert.IsTrue(FloorDust.KeywordOn, "level21: no dust after a level change");
            AssertMapCovers(Game.Def, "level21");
            Assert.LessOrEqual(Mathf.Max(FloorDust.Map.width, FloorDust.Map.height), FloorDust.MaxSide, "level21: the map is over its cap");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        private static void AssertMapCovers(LevelDef def, string when)
        {
            Texture2D map = FloorDust.Map;
            Assert.IsNotNull(map, $"{when}: no map");
            Rect interior = def.InteriorBounds();
            Rect r = FloorDust.MapRect;
            Assert.IsTrue(r.xMin < interior.xMin && r.yMin < interior.yMin && r.xMax > interior.xMax && r.yMax > interior.yMax,
                $"{when}: the map {r} does not cover the house {interior}");
            Assert.AreEqual(TextureFormat.RGBA32, map.format, $"{when}: the map's format");
            Assert.AreEqual(FilterMode.Bilinear, map.filterMode, $"{when}: the map is not bilinear");
            Assert.AreEqual(TextureWrapMode.Clamp, map.wrapMode, $"{when}: the map does not clamp");
            Assert.AreSame(map, Shader.GetGlobalTexture(FloorDust.MapProperty), $"{when}: the shader does not get the map");
            Vector4 rect = Shader.GetGlobalVector(FloorDust.RectProperty);
            Assert.That(rect.x, Is.EqualTo(r.xMin).Within(1e-4f), $"{when}: the map's corner x");
            Assert.That(rect.y, Is.EqualTo(r.yMin).Within(1e-4f), $"{when}: the map's corner z");
            Assert.That(rect.z * r.width, Is.EqualTo(1f).Within(1e-4f), $"{when}: the map's width");
            Assert.That(rect.w * r.height, Is.EqualTo(1f).Within(1e-4f), $"{when}: the map's depth");
        }

        // ----- 97b: the map follows the rooms -----

        /// <summary>
        /// On a one room level and two houses: the grime is near nothing in the middle of a room, clear along a wall and
        /// stronger again in the corners, near nothing in a doorway; the wear lies on the doorways' paths, not in the
        /// corners; the patches vary around 0.5.
        /// </summary>
        [UnityTest]
        public IEnumerator Step97b_DustMapFollowsWallsCornersDoorwaysAndPaths()
        {
            foreach (string id in new[] { "level1", "level12", "level21" })
            {
                yield return Load(id);
                LevelDef def = Game.Def;
                Assert.IsNotNull(FloorDust.Map, $"{id}: premise: no map on Haut");
                var doors = new List<Vector2>();
                var entries = new List<Vector2>();
                foreach (OpeningDef door in def.Doors)
                {
                    foreach (RoomSide s in def.SidesOf(door, out float along))
                    {
                        doors.Add(s.AlongX ? new Vector2(along, s.Line) : new Vector2(s.Line, along));
                        float across = s.Line - s.Outward * (def.WallThickness() * 0.5f + FloorDust.DoorStep);
                        entries.Add(s.AlongX ? new Vector2(along, across) : new Vector2(across, along));
                    }
                }
                var centre = new List<float>();
                var wall = new List<float>();
                var corner = new List<float>();
                var cornerWear = new List<float>();
                foreach (RoomDef r in def.AllRooms())
                {
                    if (Mathf.Min(r.SizeX, r.SizeZ) < 2.4f)
                    {
                        continue;
                    }
                    centre.Add(Grime(new Vector2(r.X, r.Z)));
                    const float c = 0.12f;
                    foreach (Vector2 p in new[]
                    {
                        new Vector2(r.MinX + c, r.MinZ + c), new Vector2(r.MaxX - c, r.MinZ + c),
                        new Vector2(r.MinX + c, r.MaxZ - c), new Vector2(r.MaxX - c, r.MaxZ - c),
                    })
                    {
                        if (doors.All(d => Vector2.Distance(d, p) > 1.3f))
                        {
                            corner.Add(Grime(p));
                            cornerWear.Add(FloorDust.Sample(new Vector3(p.x, 0f, p.y)).y);
                        }
                    }
                    foreach (Vector2 p in new[]
                    {
                        new Vector2(r.X, r.MinZ + c), new Vector2(r.X, r.MaxZ - c), new Vector2(r.MinX + c, r.Z), new Vector2(r.MaxX - c, r.Z),
                    })
                    {
                        if (doors.All(d => Vector2.Distance(d, p) > 1.3f))
                        {
                            wall.Add(Grime(p));
                        }
                    }
                }
                // A doorway close to a room corner takes that corner's grime: only the others are measured.
                var cornerPoints = def.AllRooms().SelectMany(r => new[]
                {
                    new Vector2(r.MinX, r.MinZ), new Vector2(r.MaxX, r.MinZ), new Vector2(r.MinX, r.MaxZ), new Vector2(r.MaxX, r.MaxZ),
                }).ToList();
                List<Vector2> open = doors.Where(d => cornerPoints.All(p => Vector2.Distance(p, d) > FloorDust.CornerReach + 0.3f)).ToList();
                float doorway = open.Count > 0 ? open.Average(Grime) : 0f;
                float entryWear = entries.Count > 0 ? entries.Average(e => FloorDust.Sample(new Vector3(e.x, 0f, e.y)).y) : 0f;
                Debug.Log($"[Step97b] {id}: grime centre {centre.Average():0.000}, wall {wall.Average():0.000}, corner {corner.Average():0.000}, "
                    + $"doorway {doorway:0.000}; wear entries {entryWear:0.000}, corners {cornerWear.DefaultIfEmpty(0f).Average():0.000}");
                Assert.Greater(centre.Count, 0, $"{id}: premise: no room measured");
                Assert.Greater(wall.Count, 0, $"{id}: premise: no wall measured");
                Assert.Greater(corner.Count, 0, $"{id}: premise: no corner measured");
                Assert.Less(centre.Average(), 0.06f, $"{id}: the middle of the rooms is grimy");
                Assert.Greater(wall.Average(), 0.2f, $"{id}: no grime along the walls");
                Assert.Greater(corner.Average(), wall.Average() * 1.4f, $"{id}: the corners are not grimier than the walls");
                Assert.Less(doorway, wall.Average() * 0.4f, $"{id}: the doorways are as grimy as the walls");
                Assert.Greater(entryWear, 0.4f, $"{id}: no wear in front of the doorways");
                Assert.Less(cornerWear.DefaultIfEmpty(0f).Average(), entryWear * 0.3f, $"{id}: the corners are as worn as the paths");

                Color32[] pixels = FloorDust.Map.GetPixels32();
                float mean = (float)pixels.Average(p => p.b / 255.0);
                float sd = Mathf.Sqrt((float)pixels.Average(p => (p.b / 255.0 - mean) * (p.b / 255.0 - mean)));
                Debug.Log($"[Step97b] {id}: patches mean {mean:0.000}, sd {sd:0.000}, map {FloorDust.Map.width} x {FloorDust.Map.height}");
                Assert.That(mean, Is.InRange(0.4f, 0.6f), $"{id}: the patches do not vary around 0.5");
                Assert.That(sd, Is.InRange(0.08f, 0.3f), $"{id}: the patches are flat or noisy");
            }
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        private static float Grime(Vector2 p) => FloorDust.Sample(new Vector3(p.x, 0f, p.y)).x;

        // ----- 97c: only the floors, subtly -----

        /// <summary>
        /// The game view on Haut, rendered with and without the dust in the same frame (the look has no film grain, so the
        /// two are exact): the floor changes, a little; a view of a wall alone and a view of a rug alone do not change at all.
        /// </summary>
        [UnityTest]
        public IEnumerator Step97c_OnlyTheFloorsChangeAndSubtly()
        {
            Camera cam = main.Camera;
            float fov = cam.fieldOfView;
            try
            {
                foreach (string id in new[] { "level14", "level19" })
                {
                    // The game view in the lowered look (the walls in front cut, the floor seen); the views below in
                    // the none look (nothing cut, a wall stands whole).
                    SetWalls(SaveOptions.WallsLowered);
                    yield return Load(id);
                    Game.Camera.SetView(Game.Def.Player.Yaw, Tuning.PitchDefault);
                    yield return Frames(2);
                    Fader.Apply(cam.transform.position);
                    (float mean, float changed) = Diff(cam, 480, 300);
                    Debug.Log($"[Step97c] {id}: game view, mean luma change {mean:0.000} / 255, {changed:P1} of the pixels changed");
                    Assert.Greater(changed, 0.05f, $"{id}: the dust changed nothing in the game view");
                    Assert.Less(mean, 6f, $"{id}: the dust is not subtle ({mean:0.00} / 255 on average)");

                    SetWalls(SaveOptions.WallsNone);
                    Game.Camera.enabled = false;
                    // A wall alone: from inside the biggest room, 0.7 m from the middle of a wall with no doorway near it,
                    // looking at it a little up (the floor is out of view).
                    RoomDef room = Game.Def.AllRooms().OrderByDescending(r => r.SizeX * r.SizeZ).First();
                    var doors = new List<Vector2>();
                    foreach (OpeningDef door in Game.Def.Doors)
                    {
                        foreach (RoomSide s in Game.Def.SidesOf(door, out float along))
                        {
                            doors.Add(s.AlongX ? new Vector2(along, s.Line) : new Vector2(s.Line, along));
                        }
                    }
                    (Vector2 wallPoint, Vector3 eye, float yaw)[] walls =
                    {
                        (new Vector2(room.X, room.MinZ), new Vector3(room.X, 1.6f, room.MinZ + 0.7f), 180f),
                        (new Vector2(room.X, room.MaxZ), new Vector3(room.X, 1.6f, room.MaxZ - 0.7f), 0f),
                        (new Vector2(room.MinX, room.Z), new Vector3(room.MinX + 0.7f, 1.6f, room.Z), 270f),
                        (new Vector2(room.MaxX, room.Z), new Vector3(room.MaxX - 0.7f, 1.6f, room.Z), 90f),
                    };
                    var plain = walls.First(v => doors.All(d => Vector2.Distance(d, v.wallPoint) > 1.6f));
                    cam.transform.SetPositionAndRotation(plain.eye, Quaternion.Euler(-6f, plain.yaw, 0f));
                    Fader.Apply(cam.transform.position);
                    (float wallMean, _) = Diff(cam, 320, 200);
                    Assert.AreEqual(0f, wallMean, 0.02f, $"{id}: a view of a wall alone changed with the dust");

                    // A rug alone: straight down on its middle, the view inside it.
                    if (Game.Def.Rugs.Count > 0)
                    {
                        RugDef rug = Game.Def.Rugs.OrderByDescending(r => Mathf.Min(r.SizeX, r.SizeZ)).First();
                        float half = Mathf.Min(rug.SizeX, rug.SizeZ) * 0.3f;
                        cam.fieldOfView = 20f;
                        float height = half / Mathf.Tan(10f * Mathf.Deg2Rad) / 1.42f;
                        cam.transform.SetPositionAndRotation(new Vector3(rug.X, height, rug.Z), Quaternion.Euler(90f, rug.Yaw, 0f));
                        Fader.Apply(cam.transform.position);
                        (float rugMean, _) = Diff(cam, 200, 200);
                        cam.fieldOfView = fov;
                        Assert.AreEqual(0f, rugMean, 0.02f, $"{id}: a view of a rug alone changed with the dust");
                    }
                    Game.Camera.enabled = true;
                    Game.Camera.Snap();
                }
            }
            finally
            {
                cam.fieldOfView = fov;
                Game.Camera.enabled = true;
                FloorDust.SetSuppressed(false);
            }
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>The same frame with and without the dust: mean absolute luma change (0 to 255) and the share of pixels changed.</summary>
        private static (float mean, float changed) Diff(Camera cam, int w, int h)
        {
            FloorDust.SetSuppressed(false);
            Assert.IsTrue(FloorDust.KeywordOn, "premise: the dust is on");
            Color32[] dusty = RenderPixels(cam, w, h);
            FloorDust.SetSuppressed(true);
            Assert.IsFalse(FloorDust.KeywordOn, "premise: the dust is suppressed");
            Color32[] clean = RenderPixels(cam, w, h);
            FloorDust.SetSuppressed(false);
            double sum = 0;
            int changed = 0;
            for (int i = 0; i < dusty.Length; i++)
            {
                float d = Mathf.Abs(Luma(dusty[i]) - Luma(clean[i]));
                sum += d;
                if (d >= 1f)
                {
                    changed++;
                }
            }
            return ((float)(sum / dusty.Length), changed / (float)dusty.Length);
        }

        private static float Luma(Color32 c) => 0.2126f * c.r + 0.7152f * c.g + 0.0722f * c.b;

        // ----- 97z: shots -----

        /// <summary>
        /// Shots (not a check): for every room of levels 14, 19, 15 and 20 (every floor family: parquet, light oak,
        /// herringbone, kitchen and bathroom tiles, marble, verde, both carpets), one sheet per room, columns Haut with the
        /// dust, Haut without it, Moyen; rows the game camera on the room's centre and a closer view into its +x +z corner.
        /// Written to the folder in the OOS_SHOT_DIR environment variable, else TestResults/floordust (never docs/).
        /// OOS_DUST_LEVELS overrides the level list (comma separated).
        /// </summary>
        [UnityTest]
        public IEnumerator Step97z_FloorDustShots()
        {
            const int w = 640;
            const int h = 400;
            string dir = Environment.GetEnvironmentVariable("OOS_SHOT_DIR");
            if (string.IsNullOrEmpty(dir))
            {
                dir = Path.Combine("TestResults", "floordust");
            }
            Directory.CreateDirectory(dir);
            string list = Environment.GetEnvironmentVariable("OOS_DUST_LEVELS");
            string[] ids = string.IsNullOrEmpty(list) ? new[] { "level14", "level19", "level15", "level20" } : list.Split(',');
            SetWalls(SaveOptions.WallsLowered);
            Camera cam = main.Camera;
            try
            {
                foreach (string id in ids)
                {
                    SetQuality(SaveOptions.QualityHigh);
                    yield return Load(id);
                    List<RoomDef> rooms = Game.Def.AllRooms();
                    var shots = new Color32[rooms.Count][][];
                    for (int pass = 0; pass < 2; pass++)
                    {
                        if (pass == 1)
                        {
                            SetQuality(SaveOptions.QualityMedium);
                            yield return Frames(4);
                        }
                        for (int ri = 0; ri < rooms.Count; ri++)
                        {
                            RoomDef room = rooms[ri];
                            shots[ri] = shots[ri] ?? new Color32[6][];
                            Game.Camera.enabled = true;
                            Game.Furniture.Teleport(new Vector3(room.X, 0f, room.Z), Game.Def.Player.Yaw);
                            Game.Camera.SetView(Game.Def.Player.Yaw, Tuning.PitchDefault);
                            Game.Camera.SetDistance(Tuning.OrbitDistance * 1.3f);
                            yield return Frames(2);
                            Fader.Apply(cam.transform.position);
                            Fader.DrawFaded(cam);
                            Capture(cam, w, h, shots[ri], 0, pass);

                            Game.Camera.enabled = false;
                            var corner = new Vector3(room.MaxX, 0f, room.MaxZ);
                            Vector3 diagonal = new Vector3(1f, 0f, 1f).normalized;
                            float back = Mathf.Min(1.9f, 0.48f * Mathf.Min(room.SizeX, room.SizeZ) * 1.414f);
                            Vector3 eye = corner - diagonal * back + Vector3.up * 1.3f;
                            Vector3 look = corner - diagonal * 0.3f;
                            cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(look - eye, Vector3.up));
                            Fader.Apply(cam.transform.position);
                            Fader.DrawFaded(cam);
                            Capture(cam, w, h, shots[ri], 3, pass);
                            Game.Camera.enabled = true;
                        }
                    }
                    SetQuality(SaveOptions.QualityHigh);
                    for (int ri = 0; ri < rooms.Count; ri++)
                    {
                        var sheet = new Texture2D(w * 3, h * 2, TextureFormat.RGBA32, false);
                        for (int row = 0; row < 2; row++)
                        {
                            for (int col = 0; col < 3; col++)
                            {
                                sheet.SetPixels32(w * col, h * (1 - row), w, h, shots[ri][row * 3 + col]);
                            }
                        }
                        sheet.Apply();
                        string room = rooms[ri].Id ?? "room";
                        string floor = rooms[ri].FloorFinish ?? (rooms[ri].IsSoft ? "softcarpet" : "parquet");
                        File.WriteAllBytes(Path.Combine(dir, $"{id}_{room}_{floor}.png"), sheet.EncodeToPNG());
                        Object.Destroy(sheet);
                    }
                    Debug.Log($"[Step97z] {id}: {rooms.Count} sheets in {dir}");
                }
            }
            finally
            {
                Game.Camera.enabled = true;
                FloorDust.SetSuppressed(false);
                SetQuality(SaveOptions.QualityHigh);
            }
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// One view into <paramref name="into"/> at <paramref name="first"/>: on Haut (pass 0) with the dust then without it
        /// (the next slot), on Moyen (pass 1) the third slot.
        /// </summary>
        private static void Capture(Camera cam, int w, int h, Color32[][] into, int first, int pass)
        {
            if (pass == 0)
            {
                FloorDust.SetSuppressed(false);
                into[first] = RenderPixels(cam, w, h);
                FloorDust.SetSuppressed(true);
                into[first + 1] = RenderPixels(cam, w, h);
                FloorDust.SetSuppressed(false);
            }
            else
            {
                into[first + 2] = RenderPixels(cam, w, h);
            }
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
