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
    /// CEILING (2026-11-24, docs/next/progress/CEILING.md), on the real Boot scene and the real levels: the rooms' painted
    /// ceilings (RoomCeilings).
    /// <list type="bullet">
    /// <item>Ceiling_a: one per room at its wall top over its footprint, facing down; no collider, no shadow, not an
    /// occluder, never hit by a ray; from the default gameplay camera every ceiling is gone and its renderer off (the
    /// budgets unchanged); from an eye below them they show, fading in over about 0.3 s, and fade out again above; the
    /// night bounce follows a light switched off.</item>
    /// <item>Ceiling_b: shots to Build/shots/ceiling (or OOS_SHOT_DIR): the gameplay start view and the house view of level1
    /// (day) and level20 (night), before (RoomCeilings.Disabled) and after, compared pixel by pixel; a low orbit and an eye
    /// level view inside level1's living room; level20's best lit room from inside, by night (with bounce strength
    /// variants) and by day.</item>
    /// <item>Ceiling_c: the title tour at three points of its loop (the tour's own pose and lens shift).</item>
    /// </list>
    /// Run: --filter Ceiling_.
    /// </summary>
    public sealed class ProbeTestsCeiling
    {
        private const int Width = 1280;
        private const int Height = 720;

        /// <summary>Before and after differ by at most this mean (0 to 255 per channel) over the whole frame.</summary>
        private const float SameMean = 0.5f;

        private static string ShotsDir
        {
            get
            {
                string dir = Environment.GetEnvironmentVariable("OOS_SHOT_DIR");
                return Path.GetFullPath(string.IsNullOrEmpty(dir) ? Path.Combine(Application.dataPath, "..", "Build", "shots", "ceiling") : dir);
            }
        }

        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();
        private readonly StringBuilder log = new StringBuilder();
        private GameObject testCamera;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            RoomLights.Disabled = false;
            RoomCeilings.Disabled = false;
            RoomCeilings.BounceOverride = null;
            RoomCeilings.SunBounceOverride = null;
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
            yield return null;
            yield return null;
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            Application.logMessageReceived -= OnLog;
            RoomCeilings.Disabled = false;
            RoomCeilings.BounceOverride = null;
            RoomCeilings.SunBounceOverride = null;
            if (testCamera != null)
            {
                Object.Destroy(testCamera);
                testCamera = null;
            }
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

        // ----- Ceiling_a: the geometry, no gameplay effect, the rule and the fade -----

        [UnityTest, Timeout(300000)]
        public IEnumerator Ceiling_a_OnePerRoomNoGameplayFadesByCamera()
        {
            yield return Build("level20", null);
            RoomCeilings rc = RoomCeilings.Of(Game.Level);
            Assert.IsNotNull(rc, "level20 has no ceilings");
            List<RoomDef> rooms = Game.Def.AllRooms();
            Assert.AreEqual(rooms.Count, rc.Count, "one ceiling per room");
            Assert.IsEmpty(rc.GetComponentsInChildren<Collider>(true), "a ceiling carries a collider");
            for (int i = 0; i < rc.Count; i++)
            {
                RoomDef room = rooms[i];
                MeshRenderer r = rc.RendererOf(i);
                Assert.AreSame(room, rc.RoomOf(i), $"ceiling {i}: its room");
                Assert.AreEqual(ShadowCastingMode.Off, r.shadowCastingMode, $"{room.Id}: the ceiling casts shadows");
                Assert.AreNotEqual(Layers.Occluder, r.gameObject.layer, $"{room.Id}: the ceiling is an occluder");
                Assert.AreNotEqual(Layers.Floor, r.gameObject.layer, $"{room.Id}: the ceiling is on the floor layer");
                Mesh mesh = r.GetComponent<MeshFilter>().sharedMesh;
                Bounds b = mesh.bounds;
                Vector3 centre = r.transform.TransformPoint(b.center);
                Assert.AreEqual(room.WallHeight, centre.y, 1e-3f, $"{room.Id}: the ceiling's height");
                Assert.AreEqual(room.WallHeight, rc.HeightOf(i), 1e-3f, $"{room.Id}: the ceiling's height (reported)");
                Assert.AreEqual(0f, b.extents.y, 1e-3f, $"{room.Id}: the ceiling is not flat");
                Assert.AreEqual(room.X, centre.x, 1e-3f, $"{room.Id}: the ceiling's centre x");
                Assert.AreEqual(room.Z, centre.z, 1e-3f, $"{room.Id}: the ceiling's centre z");
                Assert.AreEqual(room.SizeX * 0.5f, b.extents.x, 1e-3f, $"{room.Id}: the ceiling's width");
                Assert.AreEqual(room.SizeZ * 0.5f, b.extents.z, 1e-3f, $"{room.Id}: the ceiling's depth");
                Assert.IsTrue(mesh.normals.All(n => n == Vector3.down), $"{room.Id}: the ceiling does not face down");
                // The first triangle runs clockwise seen from below: its geometric normal points down.
                int[] tri = mesh.triangles;
                Vector3[] v = mesh.vertices;
                Vector3 face = Vector3.Cross(v[tri[1]] - v[tri[0]], v[tri[2]] - v[tri[0]]);
                Assert.Less(face.y, 0f, $"{room.Id}: the ceiling's triangles face up");
                // Nothing a ray can meet: straight up from the room's middle, every layer.
                foreach (RaycastHit hit in Physics.RaycastAll(new Vector3(room.X, 1f, room.Z), Vector3.up, 5f, ~0, QueryTriggerInteraction.Collide))
                {
                    Assert.IsFalse(hit.transform.IsChildOf(rc.transform), $"{room.Id}: a ray hits the ceiling");
                }
                log.AppendLine($"[Ceiling_a] {room.Id}: {mesh.vertexCount} vertices, {rc.SourcesOf(i)} light pools, glow max {rc.GlowMaxOf(i):0.000}");
            }

            // The default gameplay camera: every ceiling gone, its renderer off, so the probe's budgets count none.
            Game.Camera.Snap();
            for (int f = 0; f < 3; f++)
            {
                yield return null;
            }
            float eyeY = main.Camera.transform.position.y;
            log.AppendLine($"[Ceiling_a] default gameplay camera at {main.Camera.transform.position}");
            for (int i = 0; i < rc.Count; i++)
            {
                Assert.Greater(eyeY, rc.HeightOf(i), "premise: the default gameplay camera is above the ceilings");
                Assert.AreEqual(0f, rc.LevelOf(i), 1e-4f, $"{rc.RoomOf(i).Id}: the ceiling shows from the default gameplay camera");
                Assert.IsFalse(rc.RendererOf(i).enabled, $"{rc.RoomOf(i).Id}: the hidden ceiling's renderer is on");
            }
            Probe.RenderCount counted = Probe.CountRenderers(Game.Level.Root.GetComponentsInChildren<Renderer>(false));
            Assert.IsFalse(rc.GetComponentsInChildren<Renderer>(true).Any(r => r.enabled), "a ceiling renderer is counted in the gameplay view");
            log.AppendLine($"[Ceiling_a] gameplay view: {counted.MaterialSlots} draw calls, {counted.Materials.Count} materials");

            // A camera of the test's own: above the ceilings (a snap on the switch), then 1.3 m lower, under them.
            int big = 0;
            for (int i = 1; i < rc.Count; i++)
            {
                if (rooms[i].SizeX * rooms[i].SizeZ > rooms[big].SizeX * rooms[big].SizeZ)
                {
                    big = i;
                }
            }
            RoomDef living = rooms[big];
            testCamera = new GameObject("CeilingTestCamera");
            Camera cam = testCamera.AddComponent<Camera>();
            cam.enabled = false;
            rc.View = cam;
            testCamera.transform.position = new Vector3(living.X, 2.9f, living.Z);
            yield return null;
            yield return null;
            Assert.AreEqual(0f, rc.LevelOf(big), 1e-4f, "from 2.9 m the ceiling shows");
            testCamera.transform.position = new Vector3(living.X, 1.6f, living.Z);
            yield return Fade(rc, big, 1f, "in");
            for (int i = 0; i < rc.Count; i++)
            {
                Assert.AreEqual(1f, rc.LevelOf(i), 1e-4f, $"{rc.RoomOf(i).Id}: from 1.6 m the ceiling does not show");
                Assert.IsTrue(rc.RendererOf(i).enabled, $"{rc.RoomOf(i).Id}: the shown ceiling's renderer is off");
                Assert.AreEqual(ShadowCastingMode.Off, rc.RendererOf(i).shadowCastingMode, $"{rc.RoomOf(i).Id}: the shown ceiling casts shadows");
            }
            testCamera.transform.position = new Vector3(living.X, 2.9f, living.Z);
            yield return Fade(rc, big, 0f, "out");
            Assert.IsFalse(rc.RendererOf(big).enabled, "the hidden ceiling's renderer is on");

            // The bounce follows the lights (night: every room light is on at Haut): one switched off, its room's glow drops.
            Assert.IsTrue(Main.Night, "premise: level20 is a night level");
            int lit = -1;
            for (int i = 0; i < rc.Count; i++)
            {
                if (rc.SourcesOf(i) > 0 && (lit < 0 || rc.GlowMaxOf(i) > rc.GlowMaxOf(lit)))
                {
                    lit = i;
                }
            }
            Assert.GreaterOrEqual(lit, 0, "no ceiling bounces a room light");
            float before = rc.GlowMaxOf(lit);
            Assert.Greater(before, 0f, "the lit room's ceiling has no glow");
            Assert.LessOrEqual(before * Luma(RoomCeilings.PaintColour.linear), RoomCeilings.BounceMax + 1e-3f, "the glow passes its cap");
            RoomLights lights = Game.Level.Root.GetComponentInChildren<RoomLights>(true);
            var off = lights.Fixtures.Where(fx => fx.Room == rc.RoomOf(lit) && fx.Light != null && fx.Light.enabled).Select(fx => fx.Light).ToList();
            foreach (Light l in off)
            {
                l.enabled = false;
            }
            yield return null;
            yield return null;
            float after = rc.GlowMaxOf(lit);
            log.AppendLine($"[Ceiling_a] {rc.RoomOf(lit).Id}: glow {before:0.000}, {after:0.000} with its {off.Count} light(s) off");
            foreach (Light l in off)
            {
                l.enabled = true;
            }
            Assert.Less(after, before * 0.5f, "the ceiling still glows with its room lights off");

            rc.View = null;
            Report("ceiling_a_log.txt");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>Waits until ceiling <paramref name="i"/> reaches <paramref name="target"/>, checking it fades (no snap) in about 0.3 s.</summary>
        private IEnumerator Fade(RoomCeilings rc, int i, float target, string way)
        {
            float start = Time.realtimeSinceStartup;
            float firstDt = -1f;
            bool between = false;
            bool ghostOnly = true;
            while (Mathf.Abs(rc.LevelOf(i) - target) > 1e-4f && Time.realtimeSinceStartup - start < 3f)
            {
                yield return null;
                if (firstDt < 0f)
                {
                    firstDt = Time.unscaledDeltaTime;
                }
                float level = rc.LevelOf(i);
                if (level > 1e-4f && level < 1f - 1e-4f)
                {
                    between = true;
                    ghostOnly &= !rc.RendererOf(i).enabled;
                }
            }
            float took = Time.realtimeSinceStartup - start;
            log.AppendLine($"[Ceiling_a] fade {way}: {took:0.000} s, first frame {firstDt:0.000} s, seen between {between}");
            Assert.AreEqual(target, rc.LevelOf(i), 1e-4f, $"the ceiling never faded {way}");
            Assert.GreaterOrEqual(took, RoomCeilings.FadeSeconds * 0.8f, $"the ceiling snapped {way} ({took:0.000} s)");
            Assert.LessOrEqual(took, 1.5f, $"the ceiling took too long to fade {way}");
            if (firstDt < RoomCeilings.FadeSeconds * 0.5f)
            {
                Assert.IsTrue(between, $"no frame between hidden and shown while fading {way}");
            }
            Assert.IsTrue(ghostOnly, $"the opaque renderer drew while fading {way}");
        }

        // ----- Ceiling_b: shots, before and after, inside -----

        [UnityTest, Timeout(600000)]
        public IEnumerator Ceiling_b_ShotsOverheadUnchangedInsideCeilinged()
        {
            Directory.CreateDirectory(ShotsDir);
            // The gameplay view: identical before and after, level1 by day and level20 by night.
            yield return BeforeAfter("level1", null, "level1");
            yield return BeforeAfter("level20", null, "level20_night");

            // level1's living room from inside: a low orbit of the game camera, and an eye level view across the room.
            yield return Build("level1", null);
            RoomCeilings rc = RoomCeilings.Of(Game.Level);
            Assert.IsNotNull(rc, "level1 has no ceilings");
            Game.Camera.SetDistance(4f);
            Game.Camera.SetView(-135f, 2f);
            yield return null;
            Game.Camera.SetView(-135f, 2f);
            Camera cam = main.Camera;
            Vector3 orbitEye = cam.transform.position;
            Color32[] orbit = Render(cam, orbitEye, cam.transform.rotation, rc);
            Save("level1_low_orbit", orbit);
            log.AppendLine($"[Ceiling_b] level1 low orbit at {orbitEye}, ceiling shown {rc.LevelOf(0):0.00}, top band luma {MeanLuma(orbit, 0f, 1f, 0.85f, 1f):0.000}");
            Assert.Less(orbitEye.y, rc.HeightOf(0) - RoomCeilings.HideMargin, "premise: the low orbit is under the ceiling");
            Assert.AreEqual(1f, rc.LevelOf(0), 1e-4f, "the low orbit does not show the ceiling");
            var eye = new Vector3(2.6f, 1.25f, 2.2f);
            Quaternion across = Quaternion.LookRotation(new Vector3(-2.5f, 0.9f, -1.5f) - eye, Vector3.up);
            Save("level1_inside_eye", Render(cam, eye, across, rc));
            foreach (float sunBounce in new[] { 0f, RoomCeilings.SunBounce * 0.6f, RoomCeilings.SunBounce * 1.5f })
            {
                RoomCeilings.SunBounceOverride = sunBounce;
                Color32[] px = Render(cam, eye, across, rc);
                Save($"level1_inside_eye_sun{sunBounce:0.00}", px);
                log.AppendLine($"[Ceiling_b] level1 eye view, sun bounce {sunBounce:0.00}: top band luma {MeanLuma(px, 0f, 1f, 0.85f, 1f):0.000}");
            }
            RoomCeilings.SunBounceOverride = null;
            RoomCeilings.Disabled = true;
            yield return Build("level1", null);
            Save("level1_inside_eye_before", Render(cam, eye, across, null));
            RoomCeilings.Disabled = false;
            Game.Camera.SetView(-135f, Tuning.PitchDefault);
            Game.Camera.SetDistance(Tuning.OrbitDistance);

            // level20, its room with the most light pools, from a corner at eye level: night (bounce variants), then day.
            yield return Build("level20", null);
            rc = RoomCeilings.Of(Game.Level);
            int best = 0;
            for (int i = 1; i < rc.Count; i++)
            {
                if (rc.GlowMaxOf(i) > rc.GlowMaxOf(best))
                {
                    best = i;
                }
            }
            RoomDef room = rc.RoomOf(best);
            var corner = new Vector3(room.MinX + 0.5f, 1.2f, room.MinZ + 0.5f);
            Quaternion look = Quaternion.LookRotation(new Vector3(room.MaxX - 0.3f, 1.1f, room.MaxZ - 0.3f) - corner, Vector3.up);
            log.AppendLine($"[Ceiling_b] level20 room {room.Id}: {rc.SourcesOf(best)} pools, glow max {rc.GlowMaxOf(best):0.000}");
            var variants = new List<(string name, float? strength)>
            {
                ("night", null), ("night_bounce0", 0f), ("night_bounce_half", RoomCeilings.BounceStrength * 0.5f),
                ("night_bounce_double", RoomCeilings.BounceStrength * 2f),
            };
            foreach ((string name, float? strength) in variants)
            {
                RoomCeilings.BounceOverride = strength;
                Color32[] px = Render(cam, corner, look, rc);
                Save($"level20_{room.Id}_inside_{name}", px);
                log.AppendLine($"  {name}: glow max {rc.GlowMaxOf(best):0.000}, top band luma {MeanLuma(px, 0f, 1f, 0.8f, 1f):0.000}, frame luma {MeanLuma(px, 0f, 1f, 0f, 1f):0.000}");
            }
            RoomCeilings.BounceOverride = null;
            RoomCeilings.Disabled = true;
            yield return Build("level20", null);
            Save($"level20_{room.Id}_inside_night_before", Render(cam, corner, look, null));
            RoomCeilings.Disabled = false;
            yield return Build("level20", LevelDef.LightingDay);
            rc = RoomCeilings.Of(Game.Level);
            Color32[] day = Render(cam, corner, look, rc);
            Save($"level20_{room.Id}_inside_day", day);
            log.AppendLine($"  day: glow max {rc.GlowMaxOf(best):0.000}, top band luma {MeanLuma(day, 0f, 1f, 0.8f, 1f):0.000}");

            Report("ceiling_b_log.txt");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>The start view and the house view of <paramref name="id"/>, without then with ceilings: saved, compared, asserted equal.</summary>
        private IEnumerator BeforeAfter(string id, string lighting, string tag)
        {
            RoomCeilings.Disabled = true;
            yield return Build(id, lighting);
            Assert.IsNull(RoomCeilings.Of(Game.Level), "premise: the before build has ceilings");
            Color32[] startBefore = StartView(null);
            Color32[] houseBefore = HouseView(null);
            RoomCeilings.Disabled = false;
            yield return Build(id, lighting);
            RoomCeilings rc = RoomCeilings.Of(Game.Level);
            Assert.IsNotNull(rc, $"{id}: no ceilings");
            Color32[] startAfter = StartView(rc);
            int shown = Enumerable.Range(0, rc.Count).Count(i => rc.LevelOf(i) > 0f);
            Color32[] houseAfter = HouseView(rc);
            shown += Enumerable.Range(0, rc.Count).Count(i => rc.LevelOf(i) > 0f);
            Save($"{tag}_start_before", startBefore);
            Save($"{tag}_start_after", startAfter);
            Save($"{tag}_house_before", houseBefore);
            Save($"{tag}_house_after", houseAfter);
            Compare(startBefore, startAfter, out float meanStart, out int changedStart);
            Compare(houseBefore, houseAfter, out float meanHouse, out int changedHouse);
            log.AppendLine($"[Ceiling_b] {tag}: start view mean diff {meanStart:0.000}, {changedStart} pixels over 8; house view mean diff {meanHouse:0.000}, {changedHouse} pixels over 8; ceilings shown {shown}");
            Assert.AreEqual(0, shown, $"{tag}: a ceiling shows in the overhead views");
            Assert.LessOrEqual(meanStart, SameMean, $"{tag}: the start view changed with the ceilings");
            Assert.LessOrEqual(meanHouse, SameMean, $"{tag}: the house view changed with the ceilings");
        }

        // ----- Ceiling_c: the title tour -----

        [UnityTest, Timeout(300000)]
        public IEnumerator Ceiling_c_TitleTourUnderTheCeilings()
        {
            Directory.CreateDirectory(ShotsDir);
            main.Menu.ShowTitle();
            TitleCameraTour tour = main.Camera.GetComponent<TitleCameraTour>();
            Assert.IsNotNull(tour, "premise: the camera has no title tour");
            for (int i = 0; i < 120 && !tour.Active; i++)
            {
                yield return null;
            }
            Assert.IsTrue(tour.Active, "premise: the title tour never started");
            RoomCeilings rc = RoomCeilings.Of(Game.Level);
            Assert.IsNotNull(rc, "the title house has no ceilings");
            Assert.IsNull(tour.Ceiling, "the tour still builds its own lid");
            for (int i = 0; i < 20; i++)
            {
                yield return null;
            }
            for (int i = 0; i < rc.Count; i++)
            {
                Assert.AreEqual(1f, rc.LevelOf(i), 1e-4f, $"{rc.RoomOf(i).Id}: the ceiling does not show on the tour");
            }
            tour.enabled = false;
            Camera cam = main.Camera;
            float[] stops = { 0.03f, 0.35f, 0.68f };
            for (int s = 0; s < stops.Length; s++)
            {
                tour.Pose(stops[s] * tour.Length, out Vector3 position, out Quaternion rotation);
                Color32[] px = Render(cam, position, rotation, rc, true);
                Save($"title_tour_{s + 1}", px);
                log.AppendLine($"[Ceiling_c] title_tour_{s + 1}: at {position}, yaw {rotation.eulerAngles.y:0}, top band luma {MeanLuma(px, 0f, 1f, 0.85f, 1f):0.000}");
            }
            // Before: the same house rebuilt without room ceilings, where the tour builds its old unlit lid.
            RoomCeilings.Disabled = true;
            tour.enabled = true;
            Game.Restart();
            for (int i = 0; i < 120 && !(tour.Active && tour.Ceiling != null); i++)
            {
                yield return null;
            }
            if (tour.Active && tour.Ceiling != null && RoomCeilings.Of(Game.Level) == null)
            {
                tour.enabled = false;
                for (int s = 0; s < stops.Length; s++)
                {
                    tour.Pose(stops[s] * tour.Length, out Vector3 position, out Quaternion rotation);
                    Save($"title_tour_{s + 1}_before", Render(cam, position, rotation, null, true));
                }
            }
            else
            {
                log.AppendLine($"[Ceiling_c] before shots skipped: tour active {tour.Active}, lid {tour.Ceiling != null}");
            }
            RoomCeilings.Disabled = false;
            tour.enabled = true;
            cam.ResetAspect();
            cam.ResetProjectionMatrix();
            Report("ceiling_c_log.txt");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- Helpers -----

        /// <summary>Loads <paramref name="id"/> if needed, then rebuilds it (under <paramref name="lighting"/> when given), paused.</summary>
        private IEnumerator Build(string id, string lighting)
        {
            Game.Paused = false;
            if (Game.LevelId != id || Game.Def == null)
            {
                Game.LoadLevel(id);
                Assert.AreEqual(id, Game.LevelId);
            }
            Game.Def.Lighting = lighting ?? LevelLoader.Load(id).Lighting;
            Game.Restart();
            Game.Paused = true;
            for (int i = 0; i < 2; i++)
            {
                yield return new WaitForFixedUpdate();
            }
            yield return null;
        }

        private Color32[] StartView(RoomCeilings rc)
        {
            Game.Camera.Snap();
            Camera cam = main.Camera;
            Color32[] px = Render(cam, cam.transform.position, cam.transform.rotation, rc);
            Game.Camera.Snap();
            return px;
        }

        private Color32[] HouseView(RoomCeilings rc)
        {
            Rect house = Game.Def.InteriorBounds();
            var mid = new Vector3(house.center.x, 0f, house.center.y);
            float far = Mathf.Max(house.width, house.height) * 1.05f;
            Quaternion top = Quaternion.Euler(60f, 0f, 0f);
            Vector3 high = mid + Vector3.up * 0.6f - top * Vector3.forward * far;
            Color32[] px = Render(main.Camera, high, top, rc);
            Game.Camera.Snap();
            return px;
        }

        /// <summary>Renders <paramref name="cam"/> from a pose (walls and ceilings set for it at once) into a fresh frame.</summary>
        private Color32[] Render(Camera cam, Vector3 position, Quaternion rotation, RoomCeilings rc, bool lensShift = false)
        {
            float aspect = cam.aspect;
            cam.aspect = Width / (float)Height;
            cam.transform.SetPositionAndRotation(position, rotation);
            cam.ResetProjectionMatrix();
            if (lensShift)
            {
                Matrix4x4 m = cam.projectionMatrix;
                m[0, 2] = -Tuning.TitleTourLensShift;
                cam.projectionMatrix = m;
            }
            WallFader fader = Game.Level.Root.GetComponent<WallFader>();
            if (fader != null)
            {
                fader.Apply(position);
                fader.DrawFaded(cam);
            }
            rc?.Apply(position);
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
            if (lensShift)
            {
                cam.ResetProjectionMatrix();
            }
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

        private static void Compare(Color32[] a, Color32[] b, out float mean, out int changed)
        {
            double sum = 0;
            changed = 0;
            for (int i = 0; i < a.Length; i++)
            {
                int d = Math.Abs(a[i].r - b[i].r) + Math.Abs(a[i].g - b[i].g) + Math.Abs(a[i].b - b[i].b);
                sum += d / 3.0;
                if (d > 24)
                {
                    changed++;
                }
            }
            mean = (float)(sum / a.Length);
        }

        private static float Luma(Color c) => 0.2126f * c.r + 0.7152f * c.g + 0.0722f * c.b;

        /// <summary>The mean luma (0 to 1) of a region (viewport fractions, y up).</summary>
        private static float MeanLuma(Color32[] pixels, float x0, float x1, float y0, float y1)
        {
            int ax = Mathf.Clamp(Mathf.RoundToInt(x0 * Width), 0, Width), bx = Mathf.Clamp(Mathf.RoundToInt(x1 * Width), 0, Width);
            int ay = Mathf.Clamp(Mathf.RoundToInt(y0 * Height), 0, Height), by = Mathf.Clamp(Mathf.RoundToInt(y1 * Height), 0, Height);
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

        private void Report(string file)
        {
            string report = log.ToString();
            Debug.Log(report);
            TestContext.WriteLine(report);
            Directory.CreateDirectory(ShotsDir);
            File.WriteAllText(Path.Combine(ShotsDir, file), report);
        }
    }
}
