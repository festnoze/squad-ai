using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// MENUCAM (2026-11-23), on the real Boot scene: the title camera tour (TitleCameraTour) runs 30 percent nearer the
    /// floor (Tuning.TitleTourHeight 1.0 to 0.7) with a flatter tilt (Tuning.TitleTourPitch 7 to 5 degrees). Checks, along
    /// the whole loop: the new height and pitch; nothing within <see cref="Clearance"/> of the camera (no furniture, jamb or
    /// wall in its near plane); and the outside of the house shows no more than it did at the old height (a ray grid over
    /// the shifted lens, each ray's first wall, prop, floor or ceiling hit kept inside the house's outline). Writes before
    /// and after shots at six points of the loop, PC 16:9 (1920 x 1080) and phone 20:9 (2400 x 1080), to
    /// Build/shots/menucam, with a sheet per aspect (rows: the six points; left: before, right: after).
    /// </summary>
    public sealed class ProbeTestsMenuCam
    {
        private const string ShotDir = "Build/shots/menucam";
        private const float OldHeight = 1.0f;
        private const float OldPitch = 7f;
        private const float Clearance = 0.25f;
        // The title ceiling's underside (TitleCameraTour.BuildCeiling: wall height plus 0.03, half of its 0.06 box below).
        private const float CeilingY = 2.7f;
        // The house's outline: the rooms of title_house.json span x 0 to 13.4 and z 0 to 8.9, outer walls 0.1 thick.
        private static readonly Rect House = new Rect(-0.15f, -0.15f, 13.7f, 9.2f);
        private static readonly float[] Stops = { 0.03f, 0.19f, 0.35f, 0.52f, 0.68f, 0.85f };
        private static readonly (string name, int w, int h)[] Aspects = { ("pc", 1920, 1080), ("phone", 2400, 1080) };
        private const int SheetScale = 4;

        private Main main;
        private readonly List<string> logged = new List<string>();

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
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
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            Application.logMessageReceived -= OnLog;
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

        [UnityTest]
        public IEnumerator MenuCam_a_TheLowerTourClearsTheHouse()
        {
            Assert.AreEqual(OldHeight * 0.55f, Tuning.TitleTourHeight, 1e-4f, "the tour is not 45 percent nearer the floor");
            Assert.AreEqual(-4f, Tuning.TitleTourPitch, 1e-4f, "the tour's tilt (slightly up, to show the ceilings)");
            main.Menu.ShowTitle();
            TitleCameraTour tour = main.Camera.GetComponent<TitleCameraTour>();
            Assert.IsNotNull(tour, "premise: the camera has no title tour");
            for (int i = 0; i < 120 && !tour.Active; i++)
            {
                yield return null;
            }
            Assert.IsTrue(tour.Active, "premise: the title tour never started");
            Assert.AreEqual(TitleCameraTour.LevelId, main.Game.LevelId, "premise: the title is not over the title house");
            yield return null;
            tour.enabled = false;
            Camera cam = main.Camera;
            Physics.SyncTransforms();

            // The whole loop, every 5 cm: clearance and the outside, at the new pose and at the old one.
            var report = new StringBuilder();
            float worstNew = float.MaxValue, worstOld = float.MaxValue;
            string worstNewAt = "", worstOldAt = "";
            int raysNew = 0, outNew = 0, outOld = 0;
            var outsideNew = new List<string>();
            for (float d = 0f; d < tour.Length; d += 0.05f)
            {
                tour.Pose(d, out Vector3 position, out Quaternion rotation);
                Assert.AreEqual(Tuning.TitleTourHeight, position.y, 1e-4f, $"d={d:0.00}: the camera height");
                Assert.AreEqual(Tuning.TitleTourPitch, Mathf.DeltaAngle(0f, rotation.eulerAngles.x), 1e-3f, $"d={d:0.00}: the camera pitch");
                Old(position, rotation, out Vector3 oldPosition, out Quaternion oldRotation);
                float clearNew = ClearRadius(position);
                float clearOld = ClearRadius(oldPosition);
                if (clearNew < worstNew)
                {
                    worstNew = clearNew;
                    worstNewAt = $"d={d:0.00} at {position}";
                }
                if (clearOld < worstOld)
                {
                    worstOld = clearOld;
                    worstOldAt = $"d={d:0.00} at {oldPosition}";
                }
                if (Mathf.Repeat(d, 0.25f) < 0.05f)
                {
                    int n = OutsideRays(cam, position, rotation, 16f / 9f, out int total);
                    int o = OutsideRays(cam, oldPosition, oldRotation, 16f / 9f, out _);
                    raysNew += total;
                    outNew += n;
                    outOld += o;
                    if (n > o)
                    {
                        outsideNew.Add($"d={d:0.00} {n} vs {o}");
                    }
                }
            }
            report.AppendLine($"loop {tour.Length:0.00} m, {tour.LoopSeconds():0.0} s");
            report.AppendLine($"clearance new {worstNew:0.00} m ({worstNewAt}), old {worstOld:0.00} m ({worstOldAt})");
            report.AppendLine($"outside rays new {outNew} / {raysNew}, old {outOld} / {raysNew}; more than before at: "
                + (outsideNew.Count == 0 ? "none" : string.Join(", ", outsideNew)));

            // Shots: before and after at six points, PC and phone.
            Directory.CreateDirectory(ShotDir);
            foreach (var a in Aspects)
            {
                var tiles = new List<Color32[]>();
                for (int s = 0; s < Stops.Length; s++)
                {
                    float d = Stops[s] * tour.Length;
                    tour.Pose(d, out Vector3 position, out Quaternion rotation);
                    Old(position, rotation, out Vector3 oldPosition, out Quaternion oldRotation);
                    yield return null;
                    Color32[] before = Render(cam, oldPosition, oldRotation, a.w, a.h);
                    Color32[] after = Render(cam, position, rotation, a.w, a.h);
                    Save(Path.Combine(ShotDir, $"{a.name}_{s + 1}_before.png"), before, a.w, a.h);
                    Save(Path.Combine(ShotDir, $"{a.name}_{s + 1}_after.png"), after, a.w, a.h);
                    tiles.Add(before);
                    tiles.Add(after);
                    report.AppendLine($"{a.name}_{s + 1}: d={d:0.00} after at {position} yaw {rotation.eulerAngles.y:0}");
                }
                SaveSheet(Path.Combine(ShotDir, $"sheet_{a.name}.png"), tiles, a.w, a.h);
            }
            File.WriteAllText(Path.Combine(ShotDir, "menucam.txt"), report.ToString());
            TestContext.WriteLine("[MenuCam] " + report);
            tour.enabled = true;
            cam.ResetAspect();
            cam.ResetProjectionMatrix();

            Assert.GreaterOrEqual(worstNew, Clearance, $"something comes within {Clearance} m of the lowered camera: {worstNewAt}");
            Assert.LessOrEqual(outNew, outOld + raysNew / 100, "the lowered camera shows more of the outside than the old one");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        // The old pose (MENUCAM's "before"): same point and heading, the old height and tilt.
        private static void Old(Vector3 position, Quaternion rotation, out Vector3 oldPosition, out Quaternion oldRotation)
        {
            oldPosition = new Vector3(position.x, OldHeight, position.z);
            oldRotation = Quaternion.Euler(OldPitch, rotation.eulerAngles.y, 0f);
        }

        // The largest of a few radii free of any solid collider (the floor's own collider aside), 0 when even the smallest is not.
        private static float ClearRadius(Vector3 position)
        {
            float[] radii = { 0.6f, 0.5f, 0.4f, 0.3f, 0.25f, 0.2f, 0.15f, 0.1f };
            foreach (float r in radii)
            {
                bool hit = false;
                foreach (Collider c in Physics.OverlapSphere(position, r, ~0, QueryTriggerInteraction.Ignore))
                {
                    if (c.bounds.max.y > 0.1f)
                    {
                        hit = true;
                        break;
                    }
                }
                if (!hit)
                {
                    return r;
                }
            }
            return 0f;
        }

        // A 12 x 7 grid of rays over the shifted lens: how many first meet something outside the house's outline (or nothing).
        private static int OutsideRays(Camera cam, Vector3 position, Quaternion rotation, float aspect, out int total)
        {
            float tanY = Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad);
            float tanX = tanY * aspect;
            int outside = 0;
            total = 0;
            for (int j = 0; j < 7; j++)
            {
                float ny = -1f + 2f * (j + 0.5f) / 7f;
                for (int i = 0; i < 12; i++)
                {
                    float nx = -1f + 2f * (i + 0.5f) / 12f;
                    // The projection's m[0, 2] = -shift moves the picture so the NDC x of a view direction gains +shift.
                    Vector3 local = new Vector3((nx - Tuning.TitleTourLensShift) * tanX, ny * tanY, 1f);
                    Vector3 dir = (rotation * local).normalized;
                    float t = 60f;
                    if (Physics.Raycast(position, dir, out RaycastHit hit, t, ~0, QueryTriggerInteraction.Ignore))
                    {
                        t = hit.distance;
                    }
                    if (dir.y > 1e-4f)
                    {
                        t = Mathf.Min(t, (CeilingY - position.y) / dir.y);
                    }
                    else if (dir.y < -1e-4f)
                    {
                        t = Mathf.Min(t, -position.y / dir.y);
                    }
                    Vector3 p = position + dir * t;
                    total++;
                    if (!House.Contains(new Vector2(p.x, p.z)))
                    {
                        outside++;
                    }
                }
            }
            return outside;
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
            var request = new RenderPipeline.StandardRequest { destination = rt };
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

        private static void Save(string file, Color32[] pixels, int w, int h)
        {
            var texture = new Texture2D(w, h, TextureFormat.RGBA32, false);
            texture.SetPixels32(pixels);
            texture.Apply();
            File.WriteAllBytes(file, texture.EncodeToPNG());
            Object.Destroy(texture);
        }

        // Tiles two per row (before, after), at 1 / SheetScale, the first pair at the top, a 4 px gap between them.
        private static void SaveSheet(string file, List<Color32[]> tiles, int width, int height)
        {
            int tw = width / SheetScale;
            int th = height / SheetScale;
            const int gap = 4;
            int rows = tiles.Count / 2;
            int w = tw * 2 + gap;
            int h = th * rows + gap * (rows - 1);
            var sheet = new Color32[w * h];
            for (int k = 0; k < sheet.Length; k++)
            {
                sheet[k] = new Color32(255, 255, 255, 255);
            }
            for (int i = 0; i < tiles.Count; i++)
            {
                int ox = (i % 2) * (tw + gap);
                int oy = (rows - 1 - i / 2) * (th + gap);
                Color32[] src = tiles[i];
                for (int y = 0; y < th; y++)
                {
                    for (int x = 0; x < tw; x++)
                    {
                        sheet[(oy + y) * w + ox + x] = src[(y * SheetScale) * width + x * SheetScale];
                    }
                }
            }
            Save(file, sheet, w, h);
        }
    }
}
