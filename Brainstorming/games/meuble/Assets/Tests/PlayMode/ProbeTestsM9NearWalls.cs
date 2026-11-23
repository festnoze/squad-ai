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
    /// M9 near walls (product owner, 2026-11-19: "even translucent, the outer wall in front of the camera veils the whole
    /// view"): in the see-through and both looks, an outer wall between the camera and the house that covers more than
    /// Tuning.NearWallEnterCoverage of the screen fades to nothing while its door frames stay opaque (M9 doors rule); an interior wall or a
    /// small outer wall keeps the wall opacity option. Shots under Build/shots/nearwalls/.
    /// </summary>
    public sealed class ProbeTestsM9NearWalls
    {
        /// <summary>The prefix of the shots (before the change, then after it).</summary>
        private const string ShotPrefix = "after";

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

        private WallFader Fader => Game.Level.Root.GetComponent<WallFader>();

        private static void SetWalls(string walls, int opacity)
        {
            SaveOptions o = SaveStore.Options;
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty,
                Language = o.Language, Walls = walls, WallOpacity = opacity,
            });
        }

        /// <summary>The caps of the level (one per wall line, under its wall root).</summary>
        private List<MeshRenderer> Caps()
        {
            var caps = new List<MeshRenderer>();
            foreach (MeshRenderer r in Game.Level.Root.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (r.name == "Cap")
                {
                    caps.Add(r);
                }
            }
            return caps;
        }

        private static bool Cut(Renderer r) => r.shadowCastingMode == ShadowCastingMode.ShadowsOnly;

        /// <summary>
        /// A camera outside the outer wall line of <paramref name="cap"/>, <paramref name="distance"/> off its plane and
        /// <paramref name="height"/> up, in front of its middle, looking into the house; placed on the game camera and applied.
        /// </summary>
        private Vector3 LookAtOuter(MeshRenderer cap, float distance, float height)
        {
            WallFader fader = Fader;
            Assert.IsTrue(fader.PlaneOf(cap, out Vector3 point, out Vector3 inward), "premise: the cap fades");
            Vector3 middle = cap.bounds.center;
            middle += inward * Vector3.Dot(point - middle, inward);
            Vector3 eye = new Vector3(middle.x, 0f, middle.z) - inward * distance + Vector3.up * height;
            Vector3 look = new Vector3(middle.x, 0.6f, middle.z) + inward * 1.5f;
            Camera cam = main.Camera;
            cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(look - eye));
            fader.Apply(eye);
            return eye;
        }

        /// <summary>
        /// Step 90a: in the see-through and both looks, a long outer wall seen from close outside it (more than the enter
        /// coverage of the screen) vanishes, its door frames standing opaque; the same wall from far (a small part of the screen) keeps
        /// the opacity option; both keeps the stubs; lowered and off ignore the coverage.
        /// </summary>
        [UnityTest]
        public IEnumerator Step90a_LargeNearOuterWallVanishesSmallKeepsOpacity()
        {
            int checkedWalls = 0;
            int checkedFrames = 0;
            foreach (string id in new[] { "level1", "level12" })
            {
                yield return Load(id);
                WallFader fader = Fader;
                MeshRenderer[] renderers = Game.Level.Root.GetComponentsInChildren<MeshRenderer>(true);
                foreach (MeshRenderer cap in Caps())
                {
                    if (!fader.IsOuter(cap) || !fader.PlaneOf(cap, out Vector3 point, out Vector3 inward))
                    {
                        continue;
                    }
                    Bounds b = cap.bounds;
                    if (Mathf.Max(b.size.x, b.size.z) < 3f)
                    {
                        continue;
                    }
                    SetWalls(SaveOptions.WallsSeeThrough, 35);
                    LookAtOuter(cap, 1.6f, 2.4f);
                    float near = fader.CoverageOf(cap);
                    Assert.Greater(near, Tuning.NearWallEnterCoverage, $"{id}: premise: {cap.transform.parent.name} covers the screen from close");
                    Assert.IsTrue(Cut(cap), $"{id}: {cap.transform.parent.name} stands while the camera is outside it");
                    Assert.IsTrue(fader.VanishingOf(cap), $"{id}: {cap.transform.parent.name} covers {near:0.00} of the screen and does not vanish");
                    Assert.AreEqual(0f, fader.AlphaOf(cap), 1e-4f, $"{id}: a near outer wall still shows at the opacity option");
                    Assert.AreEqual(0f, fader.LevelOf(cap), 1e-4f, $"{id}: a vanished wall reads as standing (its fixtures would show)");
                    // Its door frames (registered on its plane) stand opaque in the vanished wall (M9 doors rule: doors never move).
                    foreach (MeshRenderer r in renderers)
                    {
                        if (r.name != "DoorFrame" || !fader.IsOuter(r) || !fader.PlaneOf(r, out Vector3 fp, out Vector3 fn)
                            || Vector3.Dot(fn, inward) < 0.999f || Mathf.Abs(Vector3.Dot(fp - point, inward)) > 0.01f)
                        {
                            continue;
                        }
                        checkedFrames++;
                        Assert.IsFalse(Cut(r), $"{id}: the door frame of a vanished wall is out of the way (doors never move)");
                        Assert.AreEqual(1f, fader.AlphaOf(r), 1e-4f, $"{id}: the door frame of a vanished wall is not opaque");
                    }

                    SetWalls(SaveOptions.WallsBoth, 35);
                    LookAtOuter(cap, 1.6f, 2.4f);
                    Assert.AreEqual(0f, fader.AlphaOf(cap), 1e-4f, $"{id}: both: a near outer wall still shows above its stub");
                    Assert.IsTrue(fader.Stubs.All(s => s.enabled), $"{id}: both: the stubs no longer show under a vanished wall");

                    SetWalls(SaveOptions.WallsSeeThrough, 35);
                    LookAtOuter(cap, 30f, 22f);
                    float far = fader.CoverageOf(cap);
                    Assert.Less(far, Tuning.NearWallExitCoverage, $"{id}: premise: {cap.transform.parent.name} is small from far");
                    Assert.Greater(far, 0f, $"{id}: premise: the wall is on screen from far");
                    Assert.IsTrue(Cut(cap), $"{id}: premise: the far camera is still outside the wall");
                    Assert.IsFalse(fader.VanishingOf(cap), $"{id}: a small outer wall ({far:0.00} of the screen) vanishes");
                    Assert.AreEqual(0.35f, fader.AlphaOf(cap), 1e-4f, $"{id}: a small outer wall leaves the opacity option");

                    SetWalls(SaveOptions.WallsLowered, 35);
                    LookAtOuter(cap, 1.6f, 2.4f);
                    Assert.AreEqual(0f, fader.AlphaOf(cap), "lowered: the wall shows nothing above its stub");
                    Assert.IsFalse(fader.VanishingOf(cap), "lowered: the coverage plays no part");
                    SetWalls(SaveOptions.WallsNone, 35);
                    LookAtOuter(cap, 1.6f, 2.4f);
                    Assert.IsFalse(Cut(cap), "off: the wall stays as it is");
                    Assert.AreEqual(1f, fader.LevelOf(cap), 1e-4f, "off: the wall stands");
                    checkedWalls++;
                    TestContext.WriteLine($"[Step90a] {id} {cap.transform.parent.name}: {near:0.000} of the screen from close, {far:0.000} from far");
                }
            }
            SetWalls(SaveOptions.WallsLowered, Tuning.WallOpacityDefault);
            yield return Frames(2);
            TestContext.WriteLine($"[Step90a] {checkedWalls} outer walls, {checkedFrames} door frames checked");
            Assert.Greater(checkedWalls, 3, "premise: outer walls checked");
            Assert.Greater(checkedFrames, 0, "premise: an outer doorway checked");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Step 90b: an interior (shared) wall seen from just as close keeps the opacity option in the see-through and both
        /// looks: the coverage rule is for outer walls only.
        /// </summary>
        [UnityTest]
        public IEnumerator Step90b_InteriorWallKeepsOpacityFromClose()
        {
            yield return Load("level12");
            WallFader fader = Fader;
            Camera cam = main.Camera;
            Vector3 player = Game.Furniture.transform.position;
            int checkedWalls = 0;
            foreach (MeshRenderer cap in Caps())
            {
                if (fader.IsOuter(cap) || !fader.PlaneOf(cap, out Vector3 point, out Vector3 normal))
                {
                    continue;
                }
                float side = Vector3.Dot(player - point, normal);
                if (Mathf.Abs(side) < 0.5f)
                {
                    continue;
                }
                Vector3 middle = cap.bounds.center;
                Vector3 eye = new Vector3(middle.x, 0f, middle.z) - normal * (Mathf.Sign(side) * 1.6f) + Vector3.up * 2.4f;
                Vector3 look = new Vector3(middle.x, 0.6f, middle.z) + normal * (Mathf.Sign(side) * 1.5f);
                cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(look - eye));
                foreach (string walls in new[] { SaveOptions.WallsSeeThrough, SaveOptions.WallsBoth })
                {
                    SetWalls(walls, 20);
                    fader.Apply(eye);
                    Assert.IsTrue(Cut(cap), $"{walls}: premise: {cap.transform.parent.name} is faded from {eye}");
                    Assert.AreEqual(-1f, fader.CoverageOf(cap), $"{walls}: an interior wall goes with an outer line");
                    Assert.IsFalse(fader.VanishingOf(cap), $"{walls}: an interior wall vanishes");
                    Assert.AreEqual(0.2f, fader.AlphaOf(cap), 1e-4f, $"{walls}: an interior wall seen from close leaves the opacity option");
                }
                checkedWalls++;
            }
            SetWalls(SaveOptions.WallsLowered, Tuning.WallOpacityDefault);
            yield return Frames(2);
            Assert.Greater(checkedWalls, 1, "premise: level12 has interior walls off the player");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Step 90c: in real frames (a camera of its own on the wall fader), a camera backing away from a near outer wall then
        /// coming back: the wall vanishes and comes back smoothly (never more than a frame's step of opacity at once), only
        /// across the hysteresis band (back to the opacity option under the exit coverage, gone again over the enter one),
        /// and every transition ends.
        /// </summary>
        [UnityTest]
        public IEnumerator Step90c_NearWallVanishesSmoothlyWithHysteresis()
        {
            yield return Load("level1");
            WallFader fader = Fader;
            MeshRenderer cap = null;
            foreach (MeshRenderer c in Caps())
            {
                if (fader.IsOuter(c) && Mathf.Max(c.bounds.size.x, c.bounds.size.z) >= 3f)
                {
                    cap = c;
                    break;
                }
            }
            Assert.IsNotNull(cap, "premise: level1 has a long outer wall");
            Assert.IsTrue(fader.PlaneOf(cap, out Vector3 point, out Vector3 inward));
            SetWalls(SaveOptions.WallsSeeThrough, 35);
            var go = new GameObject("NearWallTestCamera");
            Camera test = go.AddComponent<Camera>();
            test.CopyFrom(main.Camera);
            test.enabled = false;
            Camera saved = fader.View;
            fader.View = test;
            try
            {
                Vector3 middle = cap.bounds.center;
                middle += inward * Vector3.Dot(point - middle, inward);
                Vector3 look = new Vector3(middle.x, 0.6f, middle.z) + inward * 1.5f;
                void Place(float distance)
                {
                    Vector3 eye = new Vector3(middle.x, 0f, middle.z) - inward * distance + Vector3.up * (1f + distance * 0.8f);
                    go.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(look - eye));
                }
                Place(1.6f);
                yield return Frames(3);
                float settle = Time.realtimeSinceStartup;
                while (fader.Moving > 0 && Time.realtimeSinceStartup - settle < 3f)
                {
                    yield return null;
                }
                Assert.IsTrue(fader.VanishingOf(cap), "premise: the near wall vanished");
                Assert.AreEqual(0f, fader.AlphaOf(cap), 1e-4f, "premise: the near wall shows nothing");

                float maxStep = 0f;
                float previous = fader.AlphaOf(cap);
                bool cameBack = false;
                bool wentAgain = false;
                float exitAt = -1f;
                float enterAt = -1f;
                // Back away 2 cm a frame (never a jump), then come back: the band between the two thresholds keeps the state.
                for (int pass = 0; pass < 2; pass++)
                {
                    for (int step = 0; step <= 600; step++)
                    {
                        float d = pass == 0 ? 1.6f + 0.02f * step : 13.6f - 0.02f * step;
                        if (d < 1.6f || d > 13.6f)
                        {
                            break;
                        }
                        Place(d);
                        bool before = fader.VanishingOf(cap);
                        yield return null;
                        float coverage = fader.CoverageOf(cap);
                        bool now = fader.VanishingOf(cap);
                        float alpha = fader.AlphaOf(cap);
                        maxStep = Mathf.Max(maxStep, Mathf.Abs(alpha - previous));
                        previous = alpha;
                        if (before && !now)
                        {
                            cameBack = true;
                            exitAt = coverage;
                            Assert.LessOrEqual(coverage, Tuning.NearWallExitCoverage + 1e-4f, "the wall came back above the exit coverage");
                        }
                        if (!before && now)
                        {
                            wentAgain = true;
                            enterAt = coverage;
                            Assert.Greater(coverage, Tuning.NearWallEnterCoverage, "the wall vanished again under the enter coverage");
                        }
                        if (coverage > Tuning.NearWallExitCoverage && coverage <= Tuning.NearWallEnterCoverage)
                        {
                            Assert.AreEqual(before, now, $"the state flipped inside the hysteresis band at {coverage:0.000}");
                        }
                    }
                }
                Assert.IsTrue(cameBack, "the wall never came back while the camera backed away");
                Assert.IsTrue(wentAgain, "the wall never vanished again while the camera came back");
                float start = Time.realtimeSinceStartup;
                while (fader.Moving > 0 && Time.realtimeSinceStartup - start < 3f)
                {
                    yield return null;
                }
                Assert.AreEqual(0, fader.Moving, "a near wall transition never ends");
                // At most a tenth of a second per frame (WallFader clamps the step): 0.35 * 0.1 / NearWallVanishSeconds.
                Assert.LessOrEqual(maxStep, 0.35f * 0.1f / Tuning.NearWallVanishSeconds + 0.02f, "the near wall popped in or out");
                TestContext.WriteLine($"[Step90c] back at {exitAt:0.000}, gone again at {enterAt:0.000}, largest opacity step {maxStep:0.000}");
            }
            finally
            {
                fader.View = saved;
                Object.Destroy(go);
            }
            SetWalls(SaveOptions.WallsLowered, Tuning.WallOpacityDefault);
            yield return Frames(2);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// The shots: on level1 and level12, the see-through look at 35 %, the game camera around the player at its default
        /// distance and two pitches, four yaws each: one 4 by 2 contact sheet per level, Build/shots/nearwalls/PREFIX_LEVEL.png;
        /// level1 in the both look too (PREFIX_level1_both.png).
        /// </summary>
        [UnityTest]
        public IEnumerator Step90z_NearWallShots()
        {
            const int w = 480;
            const int h = 300;
            foreach (string shot in new[] { "level1", "level12", "level1_both" })
            {
                string id = shot.Split('_')[0];
                yield return Load(id);
                SetWalls(shot.EndsWith("_both") ? SaveOptions.WallsBoth : SaveOptions.WallsSeeThrough, 35);
                WallFader fader = Fader;
                OrbitCamera orbit = Game.Camera;
                Camera cam = main.Camera;
                var sheet = new Texture2D(w * 4, h * 2, TextureFormat.RGBA32, false);
                float yaw = Game.Def.Player.Yaw;
                float[] pitches = { Tuning.PitchDefault, 28f };
                for (int row = 0; row < 2; row++)
                {
                    for (int i = 0; i < 4; i++)
                    {
                        orbit.SetView(yaw + 45f + 90f * i, pitches[row]);
                        yield return Frames(2);
                        fader.Apply(cam.transform.position);
                        fader.DrawFaded(cam);
                        Color32[] pixels = RenderPixels(cam, w, h);
                        sheet.SetPixels32(w * i, h * (1 - row), w, h, pixels);
                    }
                }
                sheet.Apply();
                string dir = System.IO.Path.Combine("Build", "shots", "nearwalls");
                System.IO.Directory.CreateDirectory(dir);
                System.IO.File.WriteAllBytes(System.IO.Path.Combine(dir, ShotPrefix + "_" + shot + ".png"), sheet.EncodeToPNG());
                Object.Destroy(sheet);
            }
            SetWalls(SaveOptions.WallsLowered, Tuning.WallOpacityDefault);
            yield return Frames(2);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// The door shots (product owner rule, 2026-11-19: doors and their frames never move, only the wall does): a
        /// doorway seen from the far side of its wall in the four looks (lowered, see-through 35 %, both, off), one row each:
        /// level12's first shared doorway and first outer doorway (from outside), level8's leaf door porte_cuisine;
        /// Build/shots/doors/DOORPREFIX_doors.png.
        /// </summary>
        [UnityTest]
        public IEnumerator Step91z_DoorShots()
        {
            const int w = 480;
            const int h = 300;
            string[] looks = { SaveOptions.WallsLowered, SaveOptions.WallsSeeThrough, SaveOptions.WallsBoth, SaveOptions.WallsNone };
            var sheet = new Texture2D(w * 4, h * 3, TextureFormat.RGBA32, false);
            int row = 0;
            foreach ((string id, string door, bool outer) in new[] { ("level12", "", false), ("level12", "", true), ("level8", "porte_cuisine", false) })
            {
                yield return Load(id);
                WallFader fader = Fader;
                Camera cam = main.Camera;
                Vector3 player = Game.Furniture.transform.position;
                Vector3 at = default;
                Vector3 away = default;
                bool found = false;
                foreach (OpeningDef d in Game.Def.Doors)
                {
                    if (found || !d.IsPointForm || (door != "" && d.Id != door))
                    {
                        continue;
                    }
                    var p = new Vector3(d.X, 0f, d.Z);
                    foreach (MeshRenderer cap in Caps())
                    {
                        if (fader.IsOuter(cap) != outer || !fader.PlaneOf(cap, out Vector3 point, out Vector3 normal)
                            || Mathf.Abs(Vector3.Dot(p - point, normal)) > 0.1f || !cap.bounds.Contains(new Vector3(p.x, cap.bounds.center.y, p.z)))
                        {
                            continue;
                        }
                        float side = Vector3.Dot(player - point, normal);
                        if (!outer && Mathf.Abs(side) < 0.5f)
                        {
                            continue;
                        }
                        at = p;
                        away = outer ? -normal : -normal * Mathf.Sign(side);
                        found = true;
                        break;
                    }
                }
                Assert.IsTrue(found, $"premise: {id} has the doorway for the shot ({(outer ? "outer" : "shared")} {door})");
                Vector3 eye = at + away * 3.2f + Vector3.up * 2.8f;
                cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(at + Vector3.up * 1f - eye));
                for (int i = 0; i < looks.Length; i++)
                {
                    SetWalls(looks[i], 35);
                    fader.Apply(eye);
                    fader.DrawFaded(cam);
                    Color32[] pixels = RenderPixels(cam, w, h);
                    sheet.SetPixels32(w * i, h * (2 - row), w, h, pixels);
                }
                row++;
            }
            sheet.Apply();
            string dir = System.IO.Path.Combine("Build", "shots", "doors");
            System.IO.Directory.CreateDirectory(dir);
            System.IO.File.WriteAllBytes(System.IO.Path.Combine(dir, DoorShotPrefix + "_doors.png"), sheet.EncodeToPNG());
            Object.Destroy(sheet);
            SetWalls(SaveOptions.WallsLowered, Tuning.WallOpacityDefault);
            yield return Frames(2);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>The prefix of the door shots (before the door rule, then after it).</summary>
        private const string DoorShotPrefix = "after";

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
