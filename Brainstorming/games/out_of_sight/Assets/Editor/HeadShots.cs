using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using OutOfSight.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight.Editor
{
    /// <summary>
    /// M9 heads (docs/m9/heads/NOTES.md): a look tool, not a check. Builds a level in an editor scene and photographs the
    /// first man and the first woman: close-ups of the face (front, three quarters, profile, back three quarters) over a
    /// plain backdrop, and the default game camera (Tuning.OrbitDistance at Tuning.PitchDefault, the game's 55 degree
    /// field) over the whole room, with narrow-field copies of that same view on the head and on the whole body (the
    /// head's size against the body). Each sculpt trial of
    /// <see cref="Trials"/> named in -headVariants is set on CharacterHead's man and woman sculpts (by reflection: the
    /// head is internal to the runtime) before the level is rebuilt, and the shots go under &lt;dir&gt;/&lt;variant&gt;/.
    /// "final" shoots the sculpt the runtime ships. heads.txt lists every human's triangles per variant.
    /// -executeMethod OutOfSight.Editor.HeadShots.Shoot -headShots docs/m9/heads -headVariants final,b [-headLevel title_house]
    /// [-headBudgetLevels level11,level1]
    /// </summary>
    public static class HeadShots
    {
        private const int Width = 1280;
        private const int Height = 960;
        private static readonly Color Backdrop = new Color(0.80f, 0.77f, 0.72f);

        /// <summary>The sculpt trials: per variant, the fields set on the man's and on the woman's sculpt (the others
        /// keep the shipped values).</summary>
        private static readonly Dictionary<string, (Dictionary<string, float> man, Dictionary<string, float> woman)> Trials =
            new Dictionary<string, (Dictionary<string, float>, Dictionary<string, float>)>
            {
                // Light touch: a slightly larger head, every feature a little stronger than M7.
                ["v1_subtle"] = (Features(1.06f, 1.2f, 1f, 0.002f, 0.006f, 0.002f, 0.002f, 0f, 0.0015f, 0.004f, 0.001f, 0.003f, 0.3f, 0.014f, 0.2f),
                    Features(1.06f, 1.2f, 1f, 0.0015f, 0.0025f, 0.002f, 0.002f, 0f, 0.0015f, 0.003f, 0.001f, 0.0015f, 0.3f, 0.012f, 0.2f)),
                // Defined: a head 10 % larger, a real nose with its wings, brow over sockets, chin and jaw, ears off the head.
                ["v2_defined"] = (Features(1.10f, 1.45f, 1.05f, 0.003f, 0.008f, 0.003f, 0.004f, 0.002f, 0.0025f, 0.007f, 0.002f, 0.006f, 0.6f, 0.018f, 0.3f),
                    Features(1.10f, 1.45f, 1.05f, 0.0025f, 0.0035f, 0.003f, 0.003f, 0f, 0.0025f, 0.005f, 0.002f, 0.003f, 0.6f, 0.015f, 0.3f)),
                // Strong: everything pushed further, to see where it turns into a caricature.
                ["v3_strong"] = (Features(1.15f, 1.8f, 1.1f, 0.004f, 0.011f, 0.004f, 0.006f, 0.003f, 0.0035f, 0.010f, 0.003f, 0.009f, 0.9f, 0.024f, 0.4f),
                    Features(1.15f, 1.8f, 1.1f, 0.0035f, 0.005f, 0.004f, 0.004f, 0f, 0.0035f, 0.007f, 0.003f, 0.004f, 0.9f, 0.020f, 0.4f)),
                // Big and subtle: the strong variant's head size with the light touch's features.
                ["v4_big_subtle"] = (Features(1.15f, 1.2f, 1f, 0.002f, 0.006f, 0.002f, 0.002f, 0f, 0.0015f, 0.004f, 0.001f, 0.003f, 0.3f, 0.014f, 0.2f),
                    Features(1.15f, 1.2f, 1f, 0.0015f, 0.0025f, 0.002f, 0.002f, 0f, 0.0015f, 0.003f, 0.001f, 0.0015f, 0.3f, 0.012f, 0.2f)),
                // Round 2 (a straight bridge and a round nose tip on two rows, an ear with softer edges): v2 with a shorter
                // nose, a softer jaw edge and a face front that rounds off toward the eye corners.
                ["v5_round"] = (Features(1.10f, 1.25f, 1.05f, 0.003f, 0.007f, 0.003f, 0.004f, 0.0015f, 0.0025f, 0.007f, 0.002f, 0.006f, 0.5f, 0.016f, 0.3f, 0.4f),
                    Features(1.10f, 1.25f, 1.05f, 0.0025f, 0.003f, 0.003f, 0.003f, 0f, 0.0025f, 0.005f, 0.002f, 0.003f, 0.3f, 0.014f, 0.3f, 0.3f)),
                // v5 a little larger, with a longer nose and a rounder face front.
                ["v6_round_big"] = (Features(1.14f, 1.35f, 1.05f, 0.003f, 0.007f, 0.003f, 0.004f, 0.0015f, 0.0025f, 0.007f, 0.002f, 0.006f, 0.5f, 0.016f, 0.3f, 0.6f),
                    Features(1.14f, 1.35f, 1.05f, 0.0025f, 0.003f, 0.003f, 0.003f, 0f, 0.0025f, 0.005f, 0.002f, 0.003f, 0.3f, 0.014f, 0.3f, 0.5f)),
                // Round 3, kept: v6 on a raised nose bridge, slightly deeper eye sockets, fuller lips, and the side columns
                // moved toward the back of the head (less faceted from behind).
                ["v7_refined"] = (Features(1.14f, 1.35f, 1.05f, 0.003f, 0.007f, 0.004f, 0.004f, 0.0015f, 0.003f, 0.007f, 0.002f, 0.006f, 0.5f, 0.016f, 0.3f, 0.6f),
                    Features(1.14f, 1.35f, 1.05f, 0.0025f, 0.003f, 0.0035f, 0.003f, 0f, 0.003f, 0.005f, 0.002f, 0.003f, 0.3f, 0.014f, 0.3f, 0.5f)),
                // Woman fix (2026-11-21): the man unchanged; the woman's flatter face front, softer chin and cheeks, firmer
                // jaw edge (her landmarks and sections are in WomanShapeTrials).
                ["w1_flat"] = (new Dictionary<string, float>(),
                    Features(1.14f, 1.35f, 1.05f, 0.0025f, 0.003f, 0.0035f, 0.003f, 0f, 0.003f, 0.0035f, 0.002f, 0.003f, 0.5f, 0.014f, 0.3f, 0.3f)),
                ["w3_wide"] = (new Dictionary<string, float>(),
                    Features(1.14f, 1.35f, 1.05f, 0.0025f, 0.003f, 0.0035f, 0.003f, 0f, 0.003f, 0.0035f, 0.002f, 0.003f, 0.5f, 0.014f, 0.3f, 0.25f)),
                // Round 2 of the woman fix: the shipped woman (w1 with a tapered jaw, a lighter under-chin band and a
                // firmer jaw edge 0.7), here with the softer jaw edge 0.5 to compare.
                ["w5_edge05"] = (new Dictionary<string, float>(),
                    Features(1.14f, 1.35f, 1.05f, 0.0025f, 0.003f, 0.0035f, 0.003f, 0f, 0.003f, 0.0035f, 0.002f, 0.0015f, 0.5f, 0.014f, 0.3f, 0.3f)),
                // CHIN (2026-11-22): the shipped woman with the geometric normals under her jaw (the dark band, before the
                // fix) and with them turned only part way toward the neck. "final" ships TuckNormal 1.
                ["c0_before"] = (new Dictionary<string, float>(), new Dictionary<string, float> { ["TuckNormal"] = 0f }),
                ["c1_soft"] = (new Dictionary<string, float>(), new Dictionary<string, float> { ["TuckNormal"] = 0.6f }),
            };

        /// <summary>The woman's shape trials: fields of CharacterHead's private Woman shape (landmarks, rows, sections),
        /// set by reflection on top of the sculpt trial of the same name. "Sections" is the whole table, one float[8] per
        /// section (v, y, half width, zc, zf, zb, front and back exponents).</summary>
        private static readonly Dictionary<string, Dictionary<string, object>> WomanShapeTrials =
            new Dictionary<string, Dictionary<string, object>>
            {
                ["w1_flat"] = WomanShape(0.031f, 0.003f),
                ["w3_wide"] = WomanShape(0.032f, 0.005f),
            };

        /// <summary>The fixed woman: the eye span given, the face front out to the eyeliner wings (|du| 0.135), the lips
        /// on the painted mouth, a smaller cheek, a wider chin; sections widened by <paramref name="widen"/> over the
        /// face, a flatter front across the eyes, a shorter skull back and a lower face set back behind the lips.</summary>
        private static Dictionary<string, object> WomanShape(float eyeHalfSpan, float widen)
        {
            float w = widen;
            return new Dictionary<string, object>
            {
                ["EyeHalfSpan"] = eyeHalfSpan, ["FrontDu"] = 0.135f, ["MouthV"] = 0.69f, ["CheekHeight"] = 0.003f, ["ChinSigmaX"] = 0.02f,
                ["Rows"] = new[] { 0f, 0.05f, 0.11f, 0.17f, 0.235f, 0.30f, 0.36f, 0.41f, 0.457f, 0.51f, 0.555f, 0.585f, 0.603f, 0.621f, 0.64f, 0.69f, 0.745f, 0.81f, 0.868f, 0.9f, 0.94f },
                ["Sections"] = new[]
                {
                    new[] { 0f, 0.115f, 0f, -0.086f, -0.086f, -0.086f, 2f, 2f },
                    new[] { 0.06f, 0.111f, 0.040f, -0.086f, -0.044f, -0.128f, 2.2f, 2f },
                    new[] { 0.12f, 0.101f, 0.060f, -0.084f, -0.016f, -0.155f, 2.5f, 2.1f },
                    new[] { 0.18f, 0.085f, 0.074f, -0.082f, 0f, -0.171f, 2.9f, 2.2f },
                    new[] { 0.24f, 0.066f, 0.081f, -0.080f, 0.008f, -0.176f, 3.1f, 2.2f },
                    new[] { 0.33f, 0.036f, 0.084f + w, -0.079f, 0.012f, -0.182f, 3.6f, 2.3f },
                    new[] { 0.39f, 0.016f, 0.084f + w, -0.079f, 0.013f, -0.183f, 3.6f, 2.3f },
                    new[] { 0.457f, 0f, 0.084f + w, -0.079f, 0.010f, -0.183f, 3.6f, 2.3f },
                    new[] { 0.53f, -0.017f, 0.085f + w, -0.079f, 0.013f, -0.180f, 3.6f, 2.3f },
                    new[] { 0.60f, -0.033f, 0.083f + w, -0.079f, 0.015f, -0.174f, 3.3f, 2.3f },
                    new[] { 0.682f, -0.052f, 0.077f + w, -0.080f, 0.017f, -0.168f, 2.8f, 2.3f },
                    new[] { 0.745f, -0.067f, 0.070f + w, -0.082f, 0.014f, -0.165f, 2.3f, 2.3f },
                    new[] { 0.81f, -0.083f, 0.059f + w, -0.086f, 0.010f, -0.163f, 2.2f, 2.3f },
                    new[] { 0.868f, -0.097f, 0.045f, -0.091f, 0.003f, -0.161f, 2.1f, 2.3f },
                    new[] { 1f, -0.108f, 0.042f, -0.100f, -0.045f, -0.165f, 2.2f, 2.3f },
                },
            };
        }

        /// <summary>The woman shape fields a trial changed, with their shipped values.</summary>
        private static readonly List<(FieldInfo field, object value)> ShapeRestore = new List<(FieldInfo, object)>();

        private static Dictionary<string, float> Features(float scale, float nose, float noseWidth, float alar, float brow, float socket,
            float cheekbone, float cheekHollow, float lips, float chin, float chinGroove, float jaw, float jawEdge, float ear, float earCup, float frontRound = 0f)
        {
            return new Dictionary<string, float>
            {
                ["Scale"] = scale, ["Nose"] = nose, ["NoseWidth"] = noseWidth, ["Alar"] = alar, ["Brow"] = brow, ["Socket"] = socket,
                ["Cheekbone"] = cheekbone, ["CheekHollow"] = cheekHollow, ["Lips"] = lips, ["Chin"] = chin, ["ChinGroove"] = chinGroove,
                ["Jaw"] = jaw, ["JawEdge"] = jawEdge, ["Ear"] = ear, ["EarCup"] = earCup, ["FrontRound"] = frontRound, ["FrontRound"] = frontRound,
            };
        }

        public static void Shoot()
        {
            int code = 0;
            var report = new StringBuilder();
            try
            {
                string dir = Arg("-headShots") ?? Path.Combine("docs", "m9", "heads");
                string id = Arg("-headLevel") ?? "title_house";
                string[] variants = (Arg("-headVariants") ?? "final").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
                string[] budgetLevels = (Arg("-headBudgetLevels") ?? "").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
                foreach (string variant in variants)
                {
                    object man = null, woman = null;
                    try
                    {
                        Apply(variant, out man, out woman);
                        string folder = Path.Combine(dir, variant);
                        Directory.CreateDirectory(folder);
                        ShootLevel(folder, id, variant, report, true);
                        foreach (string other in budgetLevels)
                        {
                            ShootLevel(folder, other, variant, report, false);
                        }
                    }
                    finally
                    {
                        Restore(man, woman);
                    }
                }
                Directory.CreateDirectory(dir);
                File.AppendAllText(Path.Combine(dir, "heads.txt"), report.ToString());
            }
            catch (Exception e)
            {
                Debug.LogError("[HeadShots] threw: " + e);
                code = 1;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static Type HeadType => typeof(CharacterLook).Assembly.GetType("OutOfSight.CharacterHead");

        /// <summary>Sets the trial's sculpt fields; returns the shipped sculpts to restore. Clears the projected meshes so
        /// the next build sculpts the heads again.</summary>
        private static void Apply(string variant, out object man, out object woman)
        {
            man = woman = null;
            ClearProjections();
            if (!Trials.TryGetValue(variant, out var trial))
            {
                if (variant != "final")
                {
                    throw new ArgumentException("unknown head variant " + variant);
                }
                return;
            }
            FieldInfo manField = HeadType.GetField("ManSculpt", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
            FieldInfo womanField = HeadType.GetField("WomanSculpt", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
            man = manField.GetValue(null);
            woman = womanField.GetValue(null);
            manField.SetValue(null, With(man, trial.man));
            womanField.SetValue(null, With(woman, trial.woman));
            if (WomanShapeTrials.TryGetValue(variant, out var shapeFields))
            {
                SetWomanShape(shapeFields);
            }
        }

        private static void SetWomanShape(Dictionary<string, object> fields)
        {
            object shape = HeadType.GetField("Woman", BindingFlags.Static | BindingFlags.NonPublic).GetValue(null);
            Type type = shape.GetType();
            Type sectionType = HeadType.GetNestedType("Section", BindingFlags.NonPublic);
            foreach (var pair in fields)
            {
                FieldInfo f = type.GetField(pair.Key, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (f == null)
                {
                    throw new ArgumentException("no shape field " + pair.Key);
                }
                object value = pair.Value;
                if (pair.Value is float[][] table)
                {
                    Array sections = Array.CreateInstance(sectionType, table.Length);
                    for (int i = 0; i < table.Length; i++)
                    {
                        sections.SetValue(Activator.CreateInstance(sectionType, table[i].Cast<object>().ToArray()), i);
                    }
                    value = sections;
                }
                ShapeRestore.Add((f, f.GetValue(shape)));
                f.SetValue(shape, value);
            }
        }

        private static object With(object shipped, Dictionary<string, float> fields)
        {
            Type type = shipped.GetType();
            object copy = Activator.CreateInstance(type, true);
            foreach (FieldInfo f in type.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
            {
                f.SetValue(copy, f.GetValue(shipped));
            }
            foreach (var pair in fields)
            {
                FieldInfo f = type.GetField(pair.Key, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (f == null)
                {
                    throw new ArgumentException("no sculpt field " + pair.Key);
                }
                f.SetValue(copy, pair.Value);
            }
            return copy;
        }

        private static void Restore(object man, object woman)
        {
            if (man != null)
            {
                HeadType.GetField("ManSculpt", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public).SetValue(null, man);
                HeadType.GetField("WomanSculpt", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public).SetValue(null, woman);
            }
            if (ShapeRestore.Count > 0)
            {
                object shape = HeadType.GetField("Woman", BindingFlags.Static | BindingFlags.NonPublic).GetValue(null);
                for (int i = ShapeRestore.Count - 1; i >= 0; i--)
                {
                    ShapeRestore[i].field.SetValue(shape, ShapeRestore[i].value);
                }
                ShapeRestore.Clear();
            }
            ClearProjections();
        }

        private static void ClearProjections()
        {
            foreach (string name in new[] { "Projections", "PlainProjections" })
            {
                FieldInfo f = typeof(CharacterLook).GetField(name, BindingFlags.Static | BindingFlags.NonPublic);
                (f?.GetValue(null) as System.Collections.IDictionary)?.Clear();
            }
        }

        private static void ShootLevel(string dir, string id, string variant, StringBuilder report, bool shots)
        {
            LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, id + ".json")));
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            LevelInstance level = LevelBuilder.Build(def);
            try
            {
                List<Inhabitant> humans = level.Inhabitants.Where(h => h != null && h.Rig != null && !h.Rig.IsPet).ToList();
                foreach (Inhabitant h in humans)
                {
                    report.AppendLine($"{variant} {id} {h.name}: {h.Rig.Entry?.id}, painted {h.Rig.HasPaintedHead}, "
                        + $"triangles {Probe.TrianglesUnder(h.transform)} of {Tuning.BudgetInhabitantTriangles}, vertices {h.Rig.Skin.sharedMesh.vertexCount}");
                }
                if (!shots)
                {
                    return;
                }
                Camera cam = Setup();
                var fader = level.Root.GetComponent<WallFader>();
                Inhabitant man = humans.FirstOrDefault(h => !CharacterLook.IsFemale(h.Rig.Entry));
                Inhabitant woman = humans.FirstOrDefault(h => CharacterLook.IsFemale(h.Rig.Entry));
                foreach (Inhabitant h in new[] { man, woman })
                {
                    if (h == null)
                    {
                        continue;
                    }
                    string who = CharacterLook.IsFemale(h.Rig.Entry) ? "woman" : "man";
                    ShootHuman(cam, fader, level, h, humans, Path.Combine(dir, who));
                }
            }
            finally
            {
                LevelBuilder.Teardown(level);
            }
        }

        private static void ShootHuman(Camera cam, WallFader fader, LevelInstance level, Inhabitant h, List<Inhabitant> humans, string prefix)
        {
            InhabitantRig rig = h.Rig;
            Vector3 look = Planar(rig.HeadForward);
            Vector3 eye = rig.EyePosition;
            Vector3 at = eye - Vector3.up * 0.035f;

            // The close-ups: only this human's skin on the inhabitants' layer, over the backdrop, with a soft fill.
            var moved = new List<GameObject>();
            foreach (Renderer r in UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None))
            {
                bool mine = r is SkinnedMeshRenderer && r.transform.IsChildOf(h.transform);
                if (r.gameObject.layer == Layers.Inhabitant && !mine)
                {
                    r.gameObject.layer = 2;
                    moved.Add(r.gameObject);
                }
            }
            var canvases = new List<GameObject>();
            foreach (Canvas c in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsSortMode.None))
            {
                if (c.enabled && c.renderMode == RenderMode.WorldSpace && c.gameObject.activeSelf)
                {
                    c.gameObject.SetActive(false);
                    canvases.Add(c.gameObject);
                }
            }
            var fill = new GameObject("Portrait fill").AddComponent<Light>();
            fill.type = LightType.Point;
            fill.intensity = 0.65f;
            fill.range = 5f;
            try
            {
                cam.cullingMask = 1 << Layers.Inhabitant;
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = Backdrop;
                fill.cullingMask = cam.cullingMask;
                foreach (var (turn, lift, distance, fov, name) in new[]
                {
                    (0f, 0.03f, 0.62f, 26f, "face"),
                    (35f, 0.05f, 0.62f, 26f, "three_quarter"),
                    (90f, 0.03f, 0.68f, 28f, "profile"),
                    (150f, 0.12f, 0.65f, 30f, "back"),
                })
                {
                    Vector3 from = at + Quaternion.Euler(0f, turn, 0f) * look * distance + Vector3.up * lift;
                    fill.transform.position = at + (from - at).normalized * 1.8f;
                    cam.fieldOfView = fov;
                    Render(cam, null, from, Quaternion.LookRotation(at - from), Width, Height, $"{prefix}_{name}.jpg");
                }
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(fill.gameObject);
                foreach (GameObject g in moved)
                {
                    if (g != null)
                    {
                        g.layer = Layers.Inhabitant;
                    }
                }
                foreach (GameObject g in canvases)
                {
                    if (g != null)
                    {
                        g.SetActive(true);
                    }
                }
            }

            // The default game camera: aimed at a player chair 1.2 m in front of the human (Tuning.CameraTargetHeight),
            // Tuning.OrbitDistance away at Tuning.PitchDefault, from behind the chair a little to its side, so the human
            // faces the camera. The whole room, the game's 55 degree field; then the same eye through a narrow field on
            // the head (what a zoomed crop of that frame shows).
            cam.cullingMask = ~0;
            cam.backgroundColor = new Color(0.15f, 0.16f, 0.19f);
            Vector3 feet = h.transform.position;
            Vector3 body = Planar(h.Visual != null ? h.Visual.forward : h.transform.forward);
            Vector3 target = feet + body * 1.2f + Vector3.up * Tuning.CameraTargetHeight;
            float yaw = Quaternion.LookRotation(-body).eulerAngles.y + 25f;
            Quaternion orbit = Quaternion.Euler(Tuning.PitchDefault, yaw, 0f);
            Vector3 gameEye = target - orbit * Vector3.forward * Tuning.OrbitDistance;
            cam.fieldOfView = 55f;
            Render(cam, fader, gameEye, orbit, 1600, 900, $"{prefix}_game.jpg");
            cam.fieldOfView = 9f;
            Render(cam, fader, gameEye, Quaternion.LookRotation(at - gameEye), 900, 900, $"{prefix}_game_zoom.jpg");
            // The same eye on the whole body: the head's size against the body at play distance.
            cam.fieldOfView = 24f;
            Render(cam, fader, gameEye, Quaternion.LookRotation(feet + Vector3.up * 0.9f - gameEye), 900, 900, $"{prefix}_game_body.jpg");
        }

        private static Vector3 Planar(Vector3 v)
        {
            v.y = 0f;
            return v.sqrMagnitude > 1e-6f ? v.normalized : Vector3.forward;
        }

        private static Camera Setup()
        {
            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = new Color(1f, 0.87f, 0.67f);
            sun.intensity = 1.35f;
            sun.shadows = LightShadows.Soft;
            sun.shadowStrength = 0.78f;
            sun.transform.rotation = Quaternion.Euler(50f, 20f, 0f);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.58f, 0.63f, 0.73f);
            RenderSettings.ambientEquatorColor = new Color(0.52f, 0.47f, 0.42f);
            RenderSettings.ambientGroundColor = new Color(0.28f, 0.23f, 0.19f);
            var cam = new GameObject("ShotCamera").AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.nearClipPlane = 0.05f;
            cam.farClipPlane = 120f;
            // The first render of a fresh editor comes out tinted while the shaders warm up: throw one away.
            var warm = new RenderTexture(64, 64, 24);
            cam.targetTexture = warm;
            cam.Render();
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(warm);
            return cam;
        }

        private static void Render(Camera cam, WallFader fader, Vector3 position, Quaternion rotation, int width, int height, string file)
        {
            cam.transform.SetPositionAndRotation(position, rotation);
            if (fader != null)
            {
                fader.Apply(position);
                fader.DrawFaded(cam);
            }
            var rt = new RenderTexture(width, height, 24) { antiAliasing = 4 };
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(width, height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
            tex.Apply();
            File.WriteAllBytes(file, tex.EncodeToJPG(90));
            RenderTexture.active = null;
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(rt);
            UnityEngine.Object.DestroyImmediate(tex);
            Debug.Log($"[HeadShots] {file}");
        }

        private static string Arg(string flag)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == flag)
                {
                    return args[i + 1];
                }
            }
            return null;
        }
    }
}
