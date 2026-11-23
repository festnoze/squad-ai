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
    /// Cones look (product owner request, 2026-11-20), on the real Boot scene: the floor fan is drawn by the vision cone
    /// shader (VisionConeView.ConeShaderName), one material per cone colour and no property block on any cone, and its mesh
    /// carries what the shader reads: the watcher's frame in ranges (UV0, exact against the fan's own vertices), the rim
    /// fraction (1 on every ray's end), the half angle, and the look (calm, searching while alerted, seeing). The x-ray
    /// pass's override material is the same shader in its hatched mode. Cones_z_Shots is a look tool (explicit): it renders
    /// each state from a game-like camera on a few levels (OOS_CONE_SHOTS, default TestResults/cone_shots; never docs/).
    /// </summary>
    public sealed class ProbeTestsVisionCones
    {
        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
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
            Application.logMessageReceived -= OnLog;
            WallFader.LookOverride = null;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
                if (main.Game.Camera != null)
                {
                    main.Game.Camera.enabled = true;
                }
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

        /// <summary>Fixed steps for the rules, then two frames so every LateUpdate (the cone above all) has run.</summary>
        private static IEnumerator Settle()
        {
            yield return Steps(2);
            yield return null;
            yield return null;
        }

        // ----- a: the fan's material and mesh data -----

        [UnityTest]
        public IEnumerator Cones_a_FanCarriesItsLookOnOneMaterialPerColour()
        {
            Shader shader = Shader.Find(VisionConeView.ConeShaderName);
            Assert.IsNotNull(shader, "the vision cone shader does not resolve");
            Assert.IsTrue(shader.isSupported, "the vision cone shader is not supported here");
            Material xray = XRay.ConeOverrideMaterial();
            Assert.IsNotNull(xray, "premise: the x-ray cone pass has no override material");
            Assert.AreEqual(VisionConeView.ConeShaderName, xray.shader.name, "the hidden part of a cone is not drawn by the cone shader");
            Assert.AreEqual(1f, xray.GetFloat("_XRay"), 1e-6f, "the x-ray cone material is not in its hatched mode");

            Inhabitant h = Game.MainInhabitant;
            Assert.IsNotNull(h, "premise: the level has an inhabitant");
            VisionConeView cone = Game.Level.Cones.Find(c => c != null && c.Owner == h);
            Vision vision = Game.Level.Visions.Find(v => v != null && v.Owner == h);
            Assert.IsNotNull(cone, "premise: the inhabitant has a cone");
            Assert.IsNotNull(vision, "premise: the inhabitant has a vision");
            FurnitureController chair = Game.Furniture;
            Vector3 chairAt = YawMath.Planar(chair.transform.position);
            Vector3 home = h.Routine.Position;
            float away = YawMath.YawOf(home - chairAt);

            // Calm: looking away from the chair, at rest.
            h.Pin(home, away, 0f, true);
            yield return Settle();
            Assert.IsFalse(vision.SeesPlayer, "premise: the watcher looking away sees the chair");
            AssertFan(cone, VisionConeView.ConeLook.Calm, "calm");

            // Searching: alerted by a noise ahead of it (still away from the chair), it does not see the chair.
            h.Routine.Alert(home + YawMath.Forward(away) * 3f, NoiseKind.Creak);
            yield return Settle();
            Assert.AreEqual(InhabitantMode.Alerted, h.Routine.Mode, "premise: the noise did not alert the watcher");
            Assert.IsFalse(vision.SeesPlayer, "premise: the alerted watcher sees the chair");
            AssertFan(cone, VisionConeView.ConeLook.Searching, "searching");

            // Seeing: facing the chair.
            h.Pin(home, YawMath.YawOf(chairAt - home), 0f, true);
            yield return Settle();
            Assert.IsTrue(vision.SeesPlayer, "premise: the watcher facing the chair does not see it");
            AssertFan(cone, VisionConeView.ConeLook.Seeing, "seeing");
            Assert.AreSame(VisionConeView.ConeMaterial(VisionConeView.ConeColor(h.IsDog, true, cone.RangeFactor < 1f)),
                cone.GetComponent<MeshRenderer>().sharedMaterial, "the seeing fan does not take its alarm colour's material");

            // Every cone of the level: its colour's one material, no property block.
            foreach (VisionConeView c in Game.Level.Cones)
            {
                MeshRenderer r = c != null ? c.GetComponent<MeshRenderer>() : null;
                if (r == null || !r.enabled)
                {
                    continue;
                }
                Assert.AreSame(VisionConeView.ConeMaterial(c.Color), r.sharedMaterial, $"{c.name}: not its colour's one material");
                Assert.IsFalse(r.HasPropertyBlock(), $"{c.name}: a cone carries a property block (it would reach the x-ray material too)");
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>The fan's material and the shader's data on every vertex of its mesh, against its own geometry.</summary>
        private static void AssertFan(VisionConeView cone, VisionConeView.ConeLook look, string label)
        {
            MeshRenderer r = cone.GetComponent<MeshRenderer>();
            Assert.IsTrue(r.enabled, $"{label}: premise: the fan is hidden");
            Assert.AreEqual(VisionConeView.ConeShaderName, r.sharedMaterial.shader.name, $"{label}: the fan is not drawn by the cone shader");
            Assert.AreSame(VisionConeView.ConeMaterial(cone.Color), r.sharedMaterial, $"{label}: the fan is not its colour's one material");
            Assert.IsFalse(r.HasPropertyBlock(), $"{label}: the fan carries a property block");
            Assert.AreEqual(look, cone.Look, $"{label}: the fan's look");

            Mesh mesh = cone.FanMesh;
            Assert.IsTrue(mesh.HasVertexAttribute(VertexAttribute.TexCoord0) && mesh.HasVertexAttribute(VertexAttribute.TexCoord1),
                $"{label}: the fan mesh has no shader data");
            var local = new List<Vector2>();
            var data = new List<Vector4>();
            mesh.GetUVs(0, local);
            mesh.GetUVs(1, data);
            Vector3[] vertices = mesh.vertices;
            Assert.AreEqual(vertices.Length, local.Count, $"{label}: UV0 count");
            Assert.AreEqual(vertices.Length, data.Count, $"{label}: UV1 count");
            float half = cone.HalfAngle * Mathf.Deg2Rad;
            Assert.AreEqual(Vector2.zero, local[0], $"{label}: the apex is not the frame's origin");
            Assert.AreEqual(0f, data[0].x, 1e-6f, $"{label}: the apex's rim fraction");
            Vector3 apex = vertices[0];
            int rays = Tuning.ConeRayCount;
            for (int i = 0; i < rays; i++)
            {
                float relative = (-cone.HalfAngle + 2f * cone.HalfAngle * i / (rays - 1)) * Mathf.Deg2Rad;
                for (int s = 1; s <= cone.Radial; s++)
                {
                    int k = cone.MeshIndex(i, s);
                    Vector4 d = data[k];
                    float metres = new Vector2(vertices[k].x - apex.x, vertices[k].z - apex.z).magnitude;
                    Assert.AreEqual(metres, local[k].magnitude * cone.Range, 2e-3f, $"{label}: ray {i} sample {s}: UV0 is not the distance from the eye");
                    if (metres > 0.05f)
                    {
                        Assert.AreEqual(relative, Mathf.Atan2(local[k].x, local[k].y), 2e-3f, $"{label}: ray {i} sample {s}: UV0 is not the ray's angle");
                    }
                    Assert.AreEqual(half, d.y, 1e-5f, $"{label}: ray {i} sample {s}: the half angle");
                    Assert.AreEqual((float)look, d.w, 1e-6f, $"{label}: ray {i} sample {s}: the look");
                    Assert.That(d.x, Is.InRange(0f, 1f + 1e-5f), $"{label}: ray {i} sample {s}: the rim fraction");
                }
                Assert.AreEqual(1f, data[cone.MeshIndex(i, cone.Radial)].x, 1e-5f, $"{label}: ray {i}: its end is not on the rim");
            }
        }

        // ----- z: the look shots (a tool, explicit) -----

        private static string ShotsDir
        {
            get
            {
                string env = Environment.GetEnvironmentVariable("OOS_CONE_SHOTS");
                return Path.GetFullPath(string.IsNullOrEmpty(env) ? Path.Combine(Application.dataPath, "..", "TestResults", "cone_shots") : env);
            }
        }

        private const int Width = 1280;
        private const int Height = 720;

        [UnityTest, Explicit("look tool: renders the cone states to OOS_CONE_SHOTS (default TestResults/cone_shots)")]
        public IEnumerator Cones_z_Shots()
        {
            Directory.CreateDirectory(ShotsDir);
            var log = new List<string>();
            string[] ids = (Environment.GetEnvironmentVariable("OOS_CONE_LEVELS") ?? "level9,level16,level22").Split(',');
            try
            {
                foreach (string id in ids)
                {
                    Game.Paused = false;
                    Game.LoadLevel(id);
                    yield return Steps(2);
                    yield return ShootLevel(id, log);
                    if (id == ids[0])
                    {
                        QualityTier.Apply(new SaveOptions { Quality = SaveOptions.QualityMedium });
                        yield return null;
                        Game.Paused = false;
                        Game.Restart();
                        yield return Steps(2);
                        yield return ShootLevel(id + "_moyen", log);
                        QualityTier.Apply(new SaveOptions { Quality = SaveOptions.QualityHigh });
                        yield return null;
                    }
                }
            }
            finally
            {
                Game.Camera.enabled = true;
                WallFader.LookOverride = null;
            }
            File.WriteAllLines(Path.Combine(ShotsDir, "shots_log.txt"), log);
            Debug.Log("[ConeShots] " + string.Join(" | ", log));
        }

        /// <summary>
        /// One level: its first human (and its first awake dog) pinned facing its longest free view, the rules paused (vision
        /// is stepped by hand), a fixed camera from behind and to the side of the fan; calm, searching (alerted by a noise
        /// ahead) and seeing (the chair inside the fan), each also in the flat pre 2026-11-20 look for comparison; then the
        /// x-ray: the watcher in the next room, seen over the shared wall by the game's own orbit camera.
        /// </summary>
        private IEnumerator ShootLevel(string tag, List<string> log)
        {
            Game.Paused = true;
            FurnitureController chair = Game.Furniture;
            var subjects = new List<Inhabitant>();
            Inhabitant human = Game.Level.Inhabitants.FirstOrDefault(x => x != null && !x.IsDog);
            Inhabitant dog = Game.Level.Inhabitants.FirstOrDefault(x => x != null && x.IsDog && !x.Routine.Asleep);
            if (human != null)
            {
                subjects.Add(human);
            }
            if (dog != null)
            {
                subjects.Add(dog);
            }
            Camera cam = main.Camera;
            OrbitCamera orbit = Game.Camera;
            var fader = Game.Level.Root.GetComponent<WallFader>();
            foreach (Inhabitant h in subjects)
            {
                VisionConeView cone = Game.Level.Cones.Find(c => c != null && c.Owner == h);
                Vision vision = Game.Level.Visions.Find(v => v != null && v.Owner == h);
                if (cone == null || vision == null)
                {
                    continue;
                }
                string name = tag + "_" + (h.IsDog ? "dog" : "human");
                Vector3 at = h.Routine.Position;
                float yaw = LongestView(h, out float free);
                Vector3 gaze = YawMath.Forward(yaw);
                h.Pin(at, yaw, 0f, true);
                float reach = Mathf.Min(free, cone.Range);
                Vector3 centre = at + gaze * reach * 0.45f;
                Quaternion view = Quaternion.Euler(50f, yaw + 35f, 0f);
                Vector3 position = centre + Vector3.up * 0.3f - view * Vector3.forward * Mathf.Clamp(reach * 1.25f + 2.5f, 6f, 11f);
                orbit.enabled = false;

                // Calm: the chair behind the watcher.
                chair.Teleport(FreeSpot(at - gaze * 1.4f), yaw);
                Physics.SyncTransforms();
                vision.Step(chair);
                yield return Frames(2);
                yield return Shoot(cam, fader, position, view, name + "_calm", log, cone, vision);
                yield return Before(cam, fader, position, view, name + "_calm_before", cone);

                if (h.Routine.Personality == null || h.Routine.Personality.Hears)
                {
                    h.Routine.Alert(at + gaze * 3f, NoiseKind.Creak);
                    yield return Frames(2);
                    for (int t = 0; t < 3; t++)
                    {
                        yield return Shoot(cam, fader, position, view, $"{name}_searching_t{t}", log, cone, vision);
                        yield return new WaitForSecondsRealtime(0.45f);
                    }
                    h.Pin(at, yaw, 0f, true);
                }

                // Seeing: the chair inside the fan.
                chair.Teleport(FreeSpot(at + gaze * Mathf.Min(2.6f, reach * 0.6f)), yaw + 180f);
                Physics.SyncTransforms();
                bool seen = vision.Step(chair);
                yield return Frames(2);
                for (int t = 0; t < 3; t++)
                {
                    yield return Shoot(cam, fader, position, view, $"{name}_seeing_t{t}", log, cone, vision);
                    yield return new WaitForSecondsRealtime(0.3f);
                }
                yield return Before(cam, fader, position, view, name + "_seeing_before", cone);
                log.Add($"{name}: yaw {yaw:0}, free view {free:0.0} m, chair seen {seen}");
                chair.Teleport(FreeSpot(at - gaze * 1.4f), yaw);
                Physics.SyncTransforms();
                vision.Step(chair);
            }
            orbit.enabled = true;

            // The x-ray: the human pinned in the room next to the chair's, seen over their shared wall by the orbit camera.
            if (human != null)
            {
                VisionConeView cone = Game.Level.Cones.Find(c => c != null && c.Owner == human);
                RoomDef home = Game.Def.RoomAt(chair.transform.position);
                Vector3 chairAt = YawMath.Planar(chair.transform.position);
                RoomDef other = Game.Def.AllRooms().Where(r => r != home)
                    .OrderBy(r => (new Vector3(r.X, 0f, r.Z) - chairAt).sqrMagnitude).FirstOrDefault();
                if (other != null && cone != null)
                {
                    var there = new Vector3(other.X, 0f, other.Z);
                    float viewYaw = YawMath.YawOf(there - chairAt);
                    human.Pin(there, viewYaw + 90f, 0f, true);
                    orbit.SetView(viewYaw, 30f);
                    orbit.SetDistance(5f);
                    yield return Frames(3);
                    Color32[] pixels = Render(cam, cam.transform.position, cam.transform.rotation, fader);
                    Save(tag + "_xray", pixels);
                    log.Add($"{tag}_xray: chair in {home?.Id}, watcher in {other.Id}");
                }
            }
            Game.Paused = false;
        }

        /// <summary>The yaw (of 24) along which the watcher's eye sees farthest before an occluder, and that distance.</summary>
        private static float LongestView(Inhabitant h, out float free)
        {
            Vector3 eye = h.Routine.EyePosition;
            float best = -1f;
            float bestYaw = 0f;
            free = 0.5f;
            for (int k = 0; k < 24; k++)
            {
                float yaw = k * 15f;
                float d = Clear(eye, yaw);
                // Prefer a wide clear sector: the two directions 25 degrees aside count half.
                float score = d + 0.5f * (Clear(eye, yaw - 25f) + Clear(eye, yaw + 25f));
                if (score > best)
                {
                    best = score;
                    bestYaw = yaw;
                    free = Mathf.Max(d, 0.5f);
                }
            }
            return bestYaw;
        }

        private static float Clear(Vector3 eye, float yaw)
        {
            return Physics.Raycast(eye, YawMath.Forward(yaw), out RaycastHit hit, 12f, Layers.OccluderMask, QueryTriggerInteraction.Ignore) ? hit.distance : 12f;
        }

        private static IEnumerator Frames(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return null;
            }
        }

        private IEnumerator Shoot(Camera cam, WallFader fader, Vector3 position, Quaternion rotation, string name, List<string> log,
            VisionConeView cone, Vision vision)
        {
            cam.transform.SetPositionAndRotation(position, rotation);
            yield return null;
            Save(name, Render(cam, position, rotation, fader));
            log.Add($"{name}: look {cone.Look}, sees {vision.SeesPlayer}, colour {ColorUtility.ToHtmlStringRGBA(cone.Color)}");
        }

        /// <summary>The same view with the fan in the flat URP Unlit look it had before 2026-11-20 (the cone held still).</summary>
        private IEnumerator Before(Camera cam, WallFader fader, Vector3 position, Quaternion rotation, string name, VisionConeView cone)
        {
            MeshRenderer r = cone.GetComponent<MeshRenderer>();
            Material now = r.sharedMaterial;
            cone.enabled = false;
            r.sharedMaterial = PrimitiveKit.UnlitTransparent(cone.Color);
            cam.transform.SetPositionAndRotation(position, rotation);
            yield return null;
            Save(name, Render(cam, position, rotation, fader));
            r.sharedMaterial = now;
            cone.enabled = true;
        }

        private Vector3 FreeSpot(Vector3 focus)
        {
            for (float radius = 0f; radius < 3f; radius += 0.25f)
            {
                for (int a = 0; a < 8; a++)
                {
                    Vector3 p = focus + Quaternion.Euler(0f, a * 45f, 0f) * Vector3.forward * radius;
                    if (Game.Def.RoomAt(p) != null && !Physics.CheckSphere(p + Vector3.up * 0.5f, 0.35f, Layers.OccluderMask, QueryTriggerInteraction.Ignore))
                    {
                        return p;
                    }
                }
            }
            return focus;
        }

        private static Color32[] Render(Camera cam, Vector3 position, Quaternion rotation, WallFader fader)
        {
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
    }
}
