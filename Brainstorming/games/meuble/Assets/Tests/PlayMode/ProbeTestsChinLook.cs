using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// CHIN (2026-11-22, docs/m9/heads/NOTES.md): the dark band under the women's chin. A look test on the REAL runtime
    /// path: the Boot scene, then levels with each woman model (the plain woman, the jacket, the dress) through
    /// GameState.LoadLevel; every human frozen where it stands, the first woman (and the first man, as the unchanged
    /// reference) shot from the front and from three quarters with the room's own lights, then from afar through a narrow
    /// field at the orbit camera's pitch, at the Haut, Moyen (the mobile default) and Bas tiers
    /// (Build/shots/chin/runtime_*.png, or OOS_SHOT_DIR). It asserts what the fix relies on: the shading normals of the
    /// woman's head grid under her chin, in the face frame of the posed mesh, face out of the neck rather than down.
    /// </summary>
    public sealed class ProbeTestsChinLook
    {
        private static string ShotDir
        {
            get
            {
                string dir = System.Environment.GetEnvironmentVariable("OOS_SHOT_DIR");
                return string.IsNullOrEmpty(dir) ? "Build/shots/chin" : dir;
            }
        }

        /// <summary>The woman's jaw line under her chin (image v, CharacterHead's Woman shape): the head grid rows below it
        /// tuck into the neck. Their UVs are (u, 1 - v); the collar and the rest of the skin sample v = 1 (uv.y 0).</summary>
        private const float WomanChinV = 0.868f;

        private static readonly (string tier, string quality)[] Tiers =
        {
            ("high", SaveOptions.QualityHigh), ("medium", SaveOptions.QualityMedium), ("low", SaveOptions.QualityLow),
        };

        private Main main;
        private int fixedSteps;
        private GameState Game => main.Game;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            fixedSteps = 0;
            GamePause.IsPaused = false;
            Time.timeScale = 1f;
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
            Game.FixedStepped += Count;
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            if (main != null && main.Game != null)
            {
                main.Game.FixedStepped -= Count;
            }
            RestoreSculpt();
            QualityTier.Apply(SaveOptions.Default());
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            yield return null;
        }

        private void Count() => fixedSteps++;

        private IEnumerator Until(System.Func<bool> until, float seconds)
        {
            int end = fixedSteps + Mathf.CeilToInt(seconds / Tuning.FixedStep);
            float realStart = Time.realtimeSinceStartup;
            while (fixedSteps < end && (until == null || !until()) && Time.realtimeSinceStartup - realStart < 60f)
            {
                yield return null;
            }
        }

        private static Vector3 Planar(Vector3 v)
        {
            v.y = 0f;
            return v.sqrMagnitude > 1e-6f ? v.normalized : Vector3.forward;
        }

        /// <summary>Renders the game's own camera (its post processing, its renderer) from <paramref name="from"/> toward
        /// <paramref name="at"/> into a PNG, then puts it back. <paramref name="mask"/> limits what it draws (walls in the
        /// way of a far shot).</summary>
        private IEnumerator Shoot(Vector3 from, Vector3 at, float fov, int mask, string file, int width = 1280, int height = 960)
        {
            // Not WaitForEndOfFrame: it never comes in a batch mode editor.
            yield return null;
            Camera cam = main.Camera;
            Transform t = cam.transform;
            Vector3 position = t.position;
            Quaternion rotation = t.rotation;
            float fieldOfView = cam.fieldOfView;
            float near = cam.nearClipPlane;
            int cullingMask = cam.cullingMask;
            CameraClearFlags clear = cam.clearFlags;
            Color background = cam.backgroundColor;
            RenderTexture target = cam.targetTexture;
            t.SetPositionAndRotation(from, Quaternion.LookRotation(at - from));
            cam.fieldOfView = fov;
            cam.nearClipPlane = 0.05f;
            cam.cullingMask = mask;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.80f, 0.77f, 0.72f);
            var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32) { antiAliasing = 4 };
            cam.targetTexture = rt;
            cam.aspect = width / (float)height;
            try
            {
                var request = new RenderPipeline.StandardRequest { destination = rt };
                if (RenderPipeline.SupportsRenderRequest(cam, request))
                {
                    RenderPipeline.SubmitRenderRequest(cam, request);
                }
                else
                {
                    cam.Render();
                }
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
                cam.targetTexture = target;
                cam.ResetAspect();
                t.SetPositionAndRotation(position, rotation);
                cam.fieldOfView = fieldOfView;
                cam.nearClipPlane = near;
                cam.cullingMask = cullingMask;
                cam.clearFlags = clear;
                cam.backgroundColor = background;
                rt.Release();
                Object.Destroy(rt);
            }
        }

        /// <summary>The face-frame normals (x right, y up, z forward, origin between the eyes) of the posed head grid's
        /// front vertices under the woman's chin: the rows tucked into her neck.</summary>
        private static List<Vector3> UnderChinNormals(InhabitantRig rig)
        {
            var normals = new List<Vector3>();
            Mesh shared = rig.Skin.sharedMesh;
            Vector2[] uv = shared.uv;
            var baked = new Mesh();
            rig.Skin.BakeMesh(baked, true);
            Vector3[] bakedNormals = baked.normals;
            for (int i = 0; i < uv.Length && i < bakedNormals.Length; i++)
            {
                if (uv[i].y > 0.001f && uv[i].y < 1f - WomanChinV - 0.005f && Mathf.Abs(uv[i].x - 0.5f) < 0.08f)
                {
                    Vector3 world = rig.Skin.transform.TransformDirection(bakedNormals[i]);
                    normals.Add(rig.BrowPivot.InverseTransformDirection(world).normalized);
                }
            }
            Object.Destroy(baked);
            return normals;
        }

        private static FieldInfo WomanSculptField =>
            typeof(CharacterLook).Assembly.GetType("OutOfSight.CharacterHead").GetField("WomanSculpt", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);

        /// <summary>The shipped woman sculpt while a "before" pass runs with another TuckNormal (null otherwise).</summary>
        private object shippedWoman;

        /// <summary>Sets the woman sculpt's TuckNormal (the runtime head is internal: by reflection) and drops the cached
        /// projections so the next level load sculpts the heads again.</summary>
        private void SetTuckNormal(float value)
        {
            FieldInfo field = WomanSculptField;
            // GetValue boxes a fresh copy of the struct each time: one kept as shipped, one changed.
            shippedWoman ??= field.GetValue(null);
            object sculpt = field.GetValue(null);
            sculpt.GetType().GetField("TuckNormal").SetValue(sculpt, value);
            field.SetValue(null, sculpt);
            ClearProjections();
        }

        private void RestoreSculpt()
        {
            if (shippedWoman != null)
            {
                WomanSculptField.SetValue(null, shippedWoman);
                shippedWoman = null;
                ClearProjections();
            }
        }

        private static void ClearProjections()
        {
            foreach (string name in new[] { "Projections", "PlainProjections" })
            {
                FieldInfo f = typeof(CharacterLook).GetField(name, BindingFlags.Static | BindingFlags.NonPublic);
                (f?.GetValue(null) as IDictionary)?.Clear();
            }
        }

        [UnityTest]
        [Timeout(600000)]
        public IEnumerator ChinLook_WomenUnderChinOnTheRuntimePath()
        {
            var report = new List<string>();
            var seen = new HashSet<string>();
            bool shotMan = false;

            // Before: the plain woman with the geometric normals under her jaw (TuckNormal 0), the dark band.
            SetTuckNormal(0f);
            try
            {
                Game.LoadLevel("level11");
                yield return Until(null, 0.3f);
                var before = Game.Level.Inhabitants.Where(h => h != null && !h.IsDog && h.Rig != null && !h.Rig.IsPet).ToList();
                foreach (Inhabitant h in before)
                {
                    h.Pin(h.Routine.Position, h.Routine.BodyYaw);
                }
                yield return Until(null, 0.5f);
                Inhabitant w = before.FirstOrDefault(h => CharacterLook.IsFemale(h.Rig.Entry));
                if (w != null)
                {
                    List<Vector3> under = UnderChinNormals(w.Rig);
                    report.Add($"BEFORE level11_{w.Rig.Entry.id}: {under.Count} under-chin normals, lowest y {(under.Count > 0 ? under.Min(n => n.y) : 0f):0.00}, "
                        + $"mean y {(under.Count > 0 ? under.Average(n => n.y) : 0f):0.00}, mean z {(under.Count > 0 ? under.Average(n => n.z) : 0f):0.00}");
                    Vector3 look = Planar(w.Rig.HeadForward);
                    Vector3 at = w.Rig.EyePosition - Vector3.up * 0.035f;
                    foreach (var (tier, quality) in Tiers.Take(2))
                    {
                        QualityTier.Apply(new SaveOptions { Quality = quality });
                        yield return null;
                        yield return null;
                        yield return Shoot(at + look * 0.62f + Vector3.up * 0.03f, at, 26f, ~0, $"before_level11_woman_{tier}_face.png");
                        Vector3 three = Quaternion.Euler(0f, 35f, 0f) * look;
                        yield return Shoot(at + three * 0.62f + Vector3.up * 0.05f, at, 26f, ~0, $"before_level11_woman_{tier}_three_quarter.png");
                    }
                }
            }
            finally
            {
                RestoreSculpt();
            }
            foreach (string id in new[] { "level11", "level9", "level10", "level14", "level13" })
            {
                Game.LoadLevel(id);
                yield return Until(null, 0.3f);
                if (Game.Level == null)
                {
                    continue;
                }
                var humans = Game.Level.Inhabitants.Where(h => h != null && !h.IsDog && h.Rig != null && !h.Rig.IsPet).ToList();
                foreach (Inhabitant h in humans)
                {
                    h.Pin(h.Routine.Position, h.Routine.BodyYaw);
                }
                yield return Until(null, 0.5f);
                var subjects = new List<Inhabitant>();
                Inhabitant woman = humans.FirstOrDefault(h => CharacterLook.IsFemale(h.Rig.Entry) && !seen.Contains(h.Rig.Entry.id));
                if (woman != null)
                {
                    seen.Add(woman.Rig.Entry.id);
                    subjects.Add(woman);
                }
                Inhabitant man = shotMan ? null : humans.FirstOrDefault(h => !CharacterLook.IsFemale(h.Rig.Entry));
                if (man != null)
                {
                    shotMan = true;
                    subjects.Add(man);
                }
                foreach (Inhabitant h in subjects)
                {
                    InhabitantRig rig = h.Rig;
                    bool female = CharacterLook.IsFemale(rig.Entry);
                    string name = $"{id}_{rig.Entry.id.Replace("quaternius.", "")}";
                    if (female)
                    {
                        Assert.IsTrue(rig.HasPaintedHead, $"{name}: premise, no painted head");
                        List<Vector3> under = UnderChinNormals(rig);
                        Assert.Greater(under.Count, 4, $"{name}: premise, no head grid vertex found under the chin");
                        float lowest = under.Min(n => n.y);
                        float forward = under.Average(n => n.z);
                        report.Add($"{name}: {under.Count} under-chin normals, lowest y {lowest:0.00}, mean z {forward:0.00}");
                        // MUTATION:CHIN_TUCK_NORMAL (CharacterHead.Append): without it these keep the tucked surface's own
                        // normals, facing down and back into the neck: the dark band.
                        Assert.Greater(lowest, -0.45f, $"{name}: a normal under the chin faces down into the neck: " + report.Last());
                        Assert.Greater(forward, 0.75f, $"{name}: the under chin does not face out like the neck: " + report.Last());
                    }
                    Vector3 look = Planar(rig.HeadForward);
                    Vector3 at = rig.EyePosition - Vector3.up * 0.035f;
                    foreach (var (tier, quality) in Tiers)
                    {
                        QualityTier.Apply(new SaveOptions { Quality = quality });
                        yield return null;
                        yield return null;
                        // The room's lights only, every layer: what a close look in the game would show.
                        yield return Shoot(at + look * 0.62f + Vector3.up * 0.03f, at, 26f, ~0, $"runtime_{name}_{tier}_face.png");
                        Vector3 three = Quaternion.Euler(0f, 35f, 0f) * look;
                        yield return Shoot(at + three * 0.62f + Vector3.up * 0.05f, at, 26f, ~0, $"runtime_{name}_{tier}_three_quarter.png");
                        // The orbit camera's pitch from 3 m, through a narrow field (the inhabitants only: no wall in the way).
                        float pitch = Tuning.PitchDefault * Mathf.Deg2Rad;
                        Vector3 toward = Quaternion.Euler(0f, 30f, 0f) * look * Mathf.Cos(pitch) + Vector3.up * Mathf.Sin(pitch);
                        yield return Shoot(at + toward * 3f, at, 8f, 1 << Layers.Inhabitant, $"runtime_{name}_{tier}_game.png", 900, 900);
                    }
                    report.Add($"{name}: shot ({(female ? "woman" : "man, reference")}), quality restored next");
                }
            }
            QualityTier.Apply(SaveOptions.Default());
            Directory.CreateDirectory(ShotDir);
            File.WriteAllLines(Path.Combine(ShotDir, "runtime_chin.txt"), report);
            Debug.Log("[ChinLook] " + string.Join(" | ", report));
            Assert.GreaterOrEqual(seen.Count, 2, "premise: fewer than two woman models found: " + string.Join(", ", seen));
        }
    }
}
