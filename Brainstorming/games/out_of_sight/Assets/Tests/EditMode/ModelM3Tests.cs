using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// docs/CONTRACT_M3.md 9, EditMode (Core-only): the pure math of the model pipeline (ModelMath: Box and
    /// Uniform fit on synthetic bounds, recentring, sRGB quantisation, the red test, colour mapping) and the M3
    /// model ids of the level data.
    /// </summary>
    public sealed class ModelM3Tests
    {
        // Kenney colours as glTFast stores them: the glTF linear baseColorFactor converted to gamma.
        private static Color Gamma(float r, float g, float b) => new Color(Mathf.LinearToGammaSpace(r), Mathf.LinearToGammaSpace(g), Mathf.LinearToGammaSpace(b), 1f);

        private static readonly Color KenneyCarpet = Gamma(0.88f, 0.11f, 0.09f);
        private static readonly Color KenneyCarpetDarker = Gamma(0.33f, 0.07f, 0.06f);
        private static readonly Color KenneyWood = Gamma(0.79f, 0.33f, 0.13f);
        private static readonly Color KenneyMetal = Gamma(0.52f, 0.65f, 0.68f);
        private static readonly Color PlayerRed = new Color32(0xD7, 0x26, 0x3D, 0xFF);
        private static readonly Color RugBlue = new Color32(0x2E, 0x6D, 0xB4, 0xFF);

        private const float Eps = 1e-4f;

        // ----- Fit -----

        /// <summary>The 8 corners of native bounds, through the fit, give the bounds the fit produced.</summary>
        private static Bounds Fitted(Vector3 center, Vector3 size, Vector3 position, Vector3 scale, float yaw)
        {
            var b = new Bounds(ModelMath.ApplyFit(center - size * 0.5f, position, scale, yaw), Vector3.zero);
            for (int i = 0; i < 8; i++)
            {
                var corner = new Vector3((i & 1) == 0 ? -0.5f : 0.5f, (i & 2) == 0 ? -0.5f : 0.5f, (i & 4) == 0 ? -0.5f : 0.5f);
                b.Encapsulate(ModelMath.ApplyFit(center + Vector3.Scale(corner, size), position, scale, yaw));
            }
            return b;
        }

        private static void AssertNear(Vector3 expected, Vector3 actual, string label)
        {
            Assert.That((expected - actual).magnitude, Is.LessThan(Eps), $"{label}: expected {expected:F4}, got {actual:F4}");
        }

        [Test]
        public void Box_fit_fills_the_box_on_the_floor_for_every_quarter_turn()
        {
            // Kenney sofa, corner pivot (x in [0, 0.98] after glTFast's x mirror, z in [0, 0.41]), level 1 sofa box.
            var size = new Vector3(0.98f, 0.46f, 0.41f);
            var center = new Vector3(0.49f, 0.23f, 0.205f);
            var box = new Vector3(2.0f, 0.85f, 0.9f);
            foreach (float yaw in new[] { 0f, 90f, 180f, 270f, -90f })
            {
                Vector3 scale = ModelMath.BoxScale(size, box, yaw);
                Vector3 position = ModelMath.FitPosition(center, size, scale, yaw);
                Bounds b = Fitted(center, size, position, scale, yaw);
                AssertNear(new Vector3(-1.0f, 0f, -0.45f), b.min, "min at yaw " + yaw);
                AssertNear(new Vector3(1.0f, 0.85f, 0.45f), b.max, "max at yaw " + yaw);
            }
        }

        [Test]
        public void Box_scale_is_per_axis_and_swaps_x_and_z_on_a_quarter_turn()
        {
            var size = new Vector3(0.20f, 0.47f, 0.25f);
            var box = new Vector3(0.45f, 0.90f, 0.50f);
            AssertNear(new Vector3(2.25f, 0.90f / 0.47f, 2.0f), ModelMath.BoxScale(size, box, 0f), "yaw 0");
            AssertNear(new Vector3(2.25f, 0.90f / 0.47f, 2.0f), ModelMath.BoxScale(size, box, 180f), "yaw 180");
            AssertNear(new Vector3(2.5f, 0.90f / 0.47f, 1.8f), ModelMath.BoxScale(size, box, 90f), "yaw 90");
            AssertNear(new Vector3(2.5f, 0.90f / 0.47f, 1.8f), ModelMath.BoxScale(size, box, 270f), "yaw 270");
            Assert.AreEqual(Vector3.zero.x, ModelMath.BoxScale(new Vector3(0f, 1f, 1f), box, 0f).x, "a flat axis never divides by zero");
        }

        [Test]
        public void Recentring_moves_a_corner_pivot_to_the_footprint_centre()
        {
            // Kenney chair: pivot on a corner, bounds [0, 0.2] x [0, 0.47] x [0, 0.2].
            var size = new Vector3(0.2f, 0.47f, 0.2f);
            var center = new Vector3(0.1f, 0.235f, 0.1f);
            AssertNear(new Vector3(-0.1f, 0f, -0.1f), ModelMath.FitPosition(center, size, Vector3.one, 0f), "yaw 0");
            // Turned half way: the corner pivot lands on the other side.
            AssertNear(new Vector3(0.1f, 0f, 0.1f), ModelMath.FitPosition(center, size, Vector3.one, 180f), "yaw 180");
            // A bounds bottom below the root (a negative min y) is lifted onto the floor.
            AssertNear(new Vector3(0f, 0.5f, 0f), ModelMath.FitPosition(new Vector3(0f, 0f, 0f), new Vector3(1f, 1f, 1f), Vector3.one, 0f), "centred root");
        }

        [Test]
        public void Uniform_fit_scales_from_the_height_only()
        {
            // A rigged human: the eyes at 4.4 native units go to the routine's eye height.
            float s = ModelMath.UniformScale(4.4f, Tuning.EyeHeight);
            Assert.That(4.4f * s, Is.EqualTo(Tuning.EyeHeight).Within(Eps));
            // A static model: one scale from the box height, then centred with its bottom on the floor.
            var size = new Vector3(0.15f, 0.86f, 0.18f);
            var center = new Vector3(0.06f, 0.43f, 0.06f);
            float u = ModelMath.UniformScale(size.y, 1.8f);
            Vector3 scale = Vector3.one * u;
            Bounds b = Fitted(center, size, ModelMath.FitPosition(center, size, scale, 0f), scale, 0f);
            Assert.That(b.min.y, Is.EqualTo(0f).Within(Eps), "bottom on the floor");
            Assert.That(b.max.y, Is.EqualTo(1.8f).Within(Eps), "height from the box");
            AssertNear(new Vector3(0f, 0.9f, 0f), b.center, "centred");
            Assert.That(b.size.x / b.size.z, Is.EqualTo(size.x / size.z).Within(Eps), "proportions kept");
            Assert.AreEqual(0f, ModelMath.UniformScale(0f, 1f), "a zero height never divides by zero");
        }

        [Test]
        public void Yaw_offsets_snap_to_right_angles_and_follow_the_facing()
        {
            Assert.AreEqual(180f, ModelMath.SnapYaw(179.2f));
            Assert.AreEqual(270f, ModelMath.SnapYaw(-90f));
            Assert.AreEqual(0f, ModelMath.SnapYaw(360f));
            Assert.IsTrue(ModelMath.IsRightAngle(-180f));
            Assert.IsTrue(ModelMath.IsRightAngle(450f));
            Assert.IsFalse(ModelMath.IsRightAngle(45f));
            Assert.IsFalse(ModelMath.IsRightAngle(91f));
            Assert.IsTrue(ModelMath.IsQuarterTurn(90f));
            Assert.IsTrue(ModelMath.IsQuarterTurn(-90f));
            Assert.IsFalse(ModelMath.IsQuarterTurn(180f));
            // A model facing +z needs no turn, one facing -z a half turn; the result turns its forward onto +z.
            Assert.AreEqual(0f, ModelMath.YawOffsetFacing(Vector3.forward));
            Assert.AreEqual(180f, ModelMath.YawOffsetFacing(Vector3.back));
            foreach (Vector3 f in new[] { Vector3.forward, Vector3.back, Vector3.right, Vector3.left, new Vector3(0.3f, 0f, -1f) })
            {
                Vector3 turned = Quaternion.Euler(0f, ModelMath.YawOffsetFacing(f), 0f) * f.normalized;
                Assert.That(turned.z, Is.GreaterThan(0.9f), $"forward {f} turned to {turned}");
            }
        }

        // ----- Colours -----

        [Test]
        public void Quantisation_is_srgb_on_a_1_64_grid_and_merges_near_identical_colours()
        {
            Color a = ModelMath.Quantize(new Color(0.701f, 0.300f, 0.200f, 0.5f));
            Color b = ModelMath.Quantize(new Color(0.703f, 0.302f, 0.199f, 1f));
            Assert.AreEqual(a, b, "near-identical colours share one value");
            Assert.AreEqual(1f, a.a, "opaque");
            foreach (float c in new[] { a.r, a.g, a.b })
            {
                Assert.That(Mathf.Abs(c * 64f - Mathf.Round(c * 64f)), Is.LessThan(1e-4f), $"{c} is on the grid");
            }
            Assert.AreEqual(a, ModelMath.Quantize(a), "idempotent");
            Assert.AreEqual(new Color(0f, 1f, 0.5f, 1f), ModelMath.Quantize(new Color(-0.2f, 1.7f, 0.5f)), "clamped");
            Assert.AreNotEqual(ModelMath.Quantize(new Color(0.5f, 0.5f, 0.5f)), ModelMath.Quantize(new Color(0.5f + 1.5f / 64f, 0.5f, 0.5f)),
                "colours more than a step apart stay apart");
            // Quantisation happens in sRGB: the step between two quantised values is 1/64 of sRGB, not of linear.
            Assert.That(ModelMath.Quantize(new Color(0.5f + 0.4f / 64f, 0f, 0f)).r, Is.EqualTo(0.5f).Within(1e-6f));
        }

        [Test]
        public void Near_blacks_merge_into_one_colour()
        {
            // M3.1: the threshold applies in linear space. Linear 0.08 is sRGB 0.313.
            Assert.That(ModelMath.ToLinear(0.3133f), Is.EqualTo(0.08f).Within(3e-4f));
            Assert.That(ModelMath.ToLinear(Mathf.LinearToGammaSpace(0.42f)), Is.EqualTo(0.42f).Within(1e-3f), "matches Unity's conversion");
            Assert.IsTrue(ModelMath.IsNearBlack(new Color(0.30f, 0.20f, 0.10f)));
            Assert.IsFalse(ModelMath.IsNearBlack(new Color(0.30f, 0.32f, 0.10f)), "one channel above sRGB 0.313 is not near-black");
            Assert.IsFalse(ModelMath.IsNearBlack(new Color(0.6f, 0.01f, 0.01f)));
            // The Quaternius darks as glTFast stores them (gamma of the glTF linear factor).
            Color manEyes = Gamma(0.02f, 0.02f, 0.02f);
            Color manHair = Gamma(0.042f, 0.028f, 0.029f);
            Color manSkin = Gamma(0.11f, 0.075f, 0.057f);
            Color womanPants = Gamma(0.049f, 0.042f, 0.042f);
            Color womanHairBase = Gamma(0.07f, 0.07f, 0.07f);
            Assert.IsFalse(manEyes.r < 0.08f, "control: in sRGB the man's eyes (0.15) are not below 0.08, so nothing of him merged in M3");
            var paint = new ModelPaint();
            foreach (Color dark in new[] { manEyes, manHair, womanPants, womanHairBase })
            {
                Assert.AreEqual(ModelMath.NearBlack, ModelMath.MapColor(dark, false, 0f, paint), $"{dark} merges");
            }
            Assert.AreNotEqual(ModelMath.NearBlack, ModelMath.MapColor(manSkin, false, 0f, paint), "the skin (linear 0.11) stays its own colour");
            Assert.AreEqual(ModelMath.NearBlack, ModelMath.Quantize(ModelMath.NearBlack), "the merged near-black is on the grid");
            Assert.IsTrue(ModelMath.IsNearBlack(ModelMath.NearBlack), "and is itself a near-black (mapping is idempotent)");
        }

        [Test]
        public void Red_test_matches_hue_saturation_and_value_in_srgb()
        {
            Assert.IsTrue(ModelMath.IsRed(KenneyCarpet), "Kenney carpet");
            Assert.IsTrue(ModelMath.IsRed(KenneyCarpetDarker), "Kenney carpetDarker (sRGB value 0.61)");
            Assert.IsTrue(ModelMath.IsRed(PlayerRed), "the player colour");
            Assert.IsFalse(ModelMath.IsRed(KenneyWood), "Kenney wood is hue 25 in sRGB: not red");
            Assert.IsFalse(ModelMath.IsRed(KenneyMetal));
            Assert.IsFalse(ModelMath.IsRed(RugBlue));
            Assert.IsTrue(ModelMath.IsRed(Color.HSVToRGB(19f / 360f, 0.8f, 0.8f)), "hue 19");
            Assert.IsTrue(ModelMath.IsRed(Color.HSVToRGB(341f / 360f, 0.8f, 0.8f)), "hue -19");
            Assert.IsFalse(ModelMath.IsRed(Color.HSVToRGB(21f / 360f, 0.8f, 0.8f)), "hue 21");
            Assert.IsFalse(ModelMath.IsRed(Color.HSVToRGB(339f / 360f, 0.8f, 0.8f)), "hue -21");
            Assert.IsFalse(ModelMath.IsRed(Color.HSVToRGB(0f, 0.48f, 0.8f)), "saturation 0.48");
            Assert.IsTrue(ModelMath.IsRed(Color.HSVToRGB(0f, 0.52f, 0.8f)), "saturation 0.52");
            Assert.IsFalse(ModelMath.IsRed(Color.HSVToRGB(0f, 0.9f, 0.33f)), "value 0.33");
            Assert.IsTrue(ModelMath.IsRed(Color.HSVToRGB(0f, 0.9f, 0.37f)), "value 0.37");
            // In linear, Kenney wood would be hue 18 and count as red: the test must run on sRGB.
            Assert.IsTrue(ModelMath.IsRed(new Color(0.79f, 0.33f, 0.13f)), "control: the linear wood factor reads as red");
        }

        [Test]
        public void Reds_are_remapped_to_the_target_and_keep_their_shading()
        {
            var colors = new List<Color> { KenneyCarpet, KenneyCarpetDarker, KenneyWood };
            float reference = ModelMath.RedReference(colors);
            Assert.That(reference, Is.EqualTo(ModelMath.Value(KenneyCarpet)).Within(1e-6f), "the brightest red is the reference");
            var rug = new ModelPaint { Red = RugBlue };
            Assert.AreEqual(RugBlue, ModelMath.MapColor(KenneyCarpet, false, reference, rug), "carpet takes the rug colour exactly");
            Color border = ModelMath.MapColor(KenneyCarpetDarker, false, reference, rug);
            Assert.IsFalse(ModelMath.IsRed(border), "the darker carpet is no longer red");
            Assert.Less(ModelMath.Value(border), ModelMath.Value(RugBlue), "and stays darker than the field");
            Color.RGBToHSV(border, out float h1, out _, out _);
            Color.RGBToHSV(RugBlue, out float h2, out _, out _);
            Assert.That(Mathf.Abs(h1 - h2) * 360f, Is.LessThan(6f), "with the hue of the rug");
            Assert.AreEqual(border, ModelMath.Quantize(border), "a derived colour is quantised");
            Assert.AreEqual(ModelMath.Quantize(KenneyWood), ModelMath.MapColor(KenneyWood, false, reference, rug), "wood is only quantised");
            // No target: never red (PRD 7.2 keeps red for the player furniture).
            Color fallback = ModelMath.MapColor(KenneyCarpet, false, reference, new ModelPaint());
            Assert.IsFalse(ModelMath.IsRed(fallback));
            Assert.AreEqual(ModelMath.Opaque(ModelMath.DefaultRedTarget), fallback);
        }

        [Test]
        public void The_main_material_takes_the_furniture_colour()
        {
            Color decoyWood = new Color32(0x8C, 0x5A, 0x36, 0xFF);
            var player = new ModelPaint { Main = PlayerRed, Red = PlayerRed };
            Assert.AreEqual(PlayerRed, ModelMath.MapColor(KenneyWood, true, 0f, player), "the player model is red on its main material");
            Assert.AreEqual(PlayerRed, ModelMath.MapColor(KenneyCarpet, false, ModelMath.Value(KenneyCarpet), player), "and on its reds");
            Assert.AreEqual(ModelMath.Quantize(KenneyMetal), ModelMath.MapColor(KenneyMetal, false, 0f, player), "other materials keep their colour");
            var decoy = new ModelPaint { Main = decoyWood, Red = decoyWood };
            Color main = ModelMath.MapColor(KenneyWood, true, 0f, decoy);
            Assert.AreEqual(decoyWood, main, "a decoy keeps its colour exactly (it shares the material of its level colour)");
            Assert.AreNotEqual(PlayerRed, ModelMath.MapColor(KenneyCarpet, false, ModelMath.Value(KenneyCarpet), decoy), "a decoy is never red");
            Assert.AreEqual(1, ModelMath.IndexOfMax(new List<long> { 10, 340, 12 }));
            Assert.AreEqual(0, ModelMath.IndexOfMax(new List<long> { 7, 7 }), "first on a tie");
            Assert.AreEqual(-1, ModelMath.IndexOfMax(new List<long>()));
        }

        // ----- Level data (CONTRACT_M3 4) -----

        private static LevelDef Level(string id) => LevelJson.Parse(File.ReadAllText($"Assets/Resources/Levels/{id}.json"));

        [Test]
        public void Levels_1_to_3_name_models_for_the_chair_rugs_doormat_and_decoys()
        {
            foreach (string id in new[] { "level1", "level2", "level3" })
            {
                LevelDef l = Level(id);
                Assert.AreEqual("kenney.chair", l.Player.Model, id + " player");
                Assert.AreEqual("kenney.doormat", l.Exit.Model, id + " exit doormat");
                foreach (RugDef r in l.Rugs)
                {
                    Assert.AreEqual("kenney.rug", r.Model, id + " rug");
                }
                foreach (DecoyDef d in l.Decoys)
                {
                    Assert.AreEqual("kenney.chair", d.Model, id + " decoy");
                }
                foreach (InhabitantDef h in l.Inhabitants)
                {
                    Assert.AreEqual("quaternius.man", h.Model, $"{id} inhabitant {h.Name}: every inhabitant of levels 1 to 3 is the man (material budget)");
                }
                Assert.IsEmpty(LevelValidator.Validate(l), id + " still validates");
            }
            Assert.AreEqual("kenney.sofa", Level("level1").Props.Find(p => p.Name == "Sofa").Model);
            Assert.Greater(Level("level2").Rugs.Count + Level("level3").Decoys.Count, 0, "premise: rugs and decoys exist");
            // CONTRACT_M3 2: tables, the tall bookshelf and the other kinds (the bed) stay procedural.
            foreach (string id in new[] { "level1", "level2", "level3" })
            {
                foreach (PropDef p in Level(id).Props)
                {
                    if (p.Kind == "table" || p.Kind == "bookshelf" || p.Name == "Bed")
                    {
                        Assert.IsNull(p.Model, $"{id} {p.Name} stays procedural");
                    }
                }
            }
        }
    }
}
