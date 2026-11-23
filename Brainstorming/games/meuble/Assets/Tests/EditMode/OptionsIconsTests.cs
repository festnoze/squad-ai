using System.IO;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Options icons (product owner, 2026-11-20; docs/m9/icons/NOTES.md): the Par défaut and Retour icons and the two Language
    /// flags ship as SVG sources and 256 x 256 RGBA renders in Assets/Art/UI/Icons, are referenced by the UI icon library
    /// (UiIconLibraryBuilder), are listed in docs/LICENSES.md, and are drawn the way the menu uses them: the two glyphs pure
    /// white (the menu tints them) on a transparent background, the flags in their own colours (French blue, white and red
    /// bands; US red and white stripes and a blue canton).
    /// </summary>
    public sealed class OptionsIconsTests
    {
        private const string Folder = "Assets/Art/UI/Icons/";
        private static readonly string[] Names = { "reset", "back", "flag_fr", "flag_us" };

        private static Color32[] Pixels(string name, out int width, out int height)
        {
            string path = Folder + name + ".png";
            Assert.IsTrue(File.Exists(path), path + " is missing");
            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                Assert.IsTrue(texture.LoadImage(File.ReadAllBytes(path)), path + " is not a PNG");
                width = texture.width;
                height = texture.height;
                return texture.GetPixels32();
            }
            finally
            {
                Object.DestroyImmediate(texture);
            }
        }

        [Test]
        public void Every_icon_has_its_svg_and_a_256_png()
        {
            foreach (string name in Names)
            {
                Assert.IsTrue(File.Exists(Folder + name + ".svg"), name + ".svg is missing");
                StringAssert.Contains("viewBox=\"0 0 64 64\"", File.ReadAllText(Folder + name + ".svg"), name + ".svg is not on the 64 grid");
                Color32[] pixels = Pixels(name, out int width, out int height);
                Assert.AreEqual(256, width, name + ".png width");
                Assert.AreEqual(256, height, name + ".png height");
                Assert.AreEqual(0, pixels[0].a, name + ".png has no transparent corner");
                Assert.AreEqual(0, pixels[pixels.Length - 1].a, name + ".png has no transparent corner");
            }
        }

        [Test]
        public void The_glyphs_are_white_to_tint()
        {
            foreach (string name in new[] { "reset", "back" })
            {
                Color32[] pixels = Pixels(name, out _, out _);
                int covered = 0;
                foreach (Color32 p in pixels)
                {
                    if (p.a > 0)
                    {
                        covered++;
                        Assert.IsTrue(p.r == 255 && p.g == 255 && p.b == 255, $"{name}.png has a pixel that is not white: {p}");
                    }
                }
                Assert.Greater(covered, pixels.Length / 12, name + ".png is nearly empty");
                Assert.Less(covered, pixels.Length / 2, name + ".png is nearly full");
            }
        }

        [Test]
        public void The_flags_show_their_colours()
        {
            // Middle row samples: France left to right blue, white, red.
            Color32[] fr = Pixels("flag_fr", out int w, out int h);
            Color32 blue = fr[h / 2 * w + w / 5];
            Color32 white = fr[h / 2 * w + w / 2];
            Color32 red = fr[h / 2 * w + w * 4 / 5];
            Assert.IsTrue(blue.b > 150 && blue.r < 90 && blue.a == 255, "the French flag's left band is not blue: " + blue);
            Assert.IsTrue(white.r > 240 && white.g > 240 && white.b > 240 && white.a == 255, "the French flag's middle band is not white: " + white);
            Assert.IsTrue(red.r > 180 && red.g < 90 && red.b < 90 && red.a == 255, "the French flag's right band is not red: " + red);

            // US: red and white stripes down its right side, a blue canton at its top left (texture rows run bottom up).
            Color32[] us = Pixels("flag_us", out w, out h);
            int reds = 0, whites = 0;
            for (int y = h / 5; y < h * 4 / 5; y++)
            {
                Color32 p = us[y * w + w * 4 / 5];
                reds += p.r > 160 && p.g < 90 && p.b < 100 ? 1 : 0;
                whites += p.r > 240 && p.g > 240 && p.b > 240 ? 1 : 0;
            }
            Assert.Greater(reds, 30, "the US flag has no red stripes");
            Assert.Greater(whites, 30, "the US flag has no white stripes");
            int bluePixels = 0;
            for (int y = h * 3 / 5; y < h * 7 / 10; y++)
            {
                for (int x = w / 10; x < w / 3; x++)
                {
                    Color32 p = us[y * w + x];
                    bluePixels += p.b > p.r + 30 && p.b > p.g + 30 ? 1 : 0;
                }
            }
            Assert.Greater(bluePixels, 200, "the US flag has no blue canton at its top left");
        }

        [Test]
        public void The_library_references_every_icon()
        {
            var library = AssetDatabase.LoadAssetAtPath<UiIconLibrary>("Assets/Resources/UiIconLibrary.asset");
            Assert.IsNotNull(library, "the UI icon library asset is missing (UiIconLibraryBuilder runs in Builder.SetupAndCompile)");
            Assert.AreEqual(Folder + "reset.png", AssetDatabase.GetAssetPath(library.reset), "the library's reset icon");
            Assert.AreEqual(Folder + "back.png", AssetDatabase.GetAssetPath(library.back), "the library's back icon");
            Assert.AreEqual(Folder + "flag_fr.png", AssetDatabase.GetAssetPath(library.flagFrench), "the library's French flag");
            Assert.AreEqual(Folder + "flag_us.png", AssetDatabase.GetAssetPath(library.flagEnglish), "the library's US flag");
        }

        [Test]
        public void Every_icon_is_in_the_licence_file()
        {
            string text = File.ReadAllText("docs/LICENSES.md");
            foreach (string name in Names)
            {
                StringAssert.Contains("`" + name + ".svg`", text, name + ".svg is not in docs/LICENSES.md");
                StringAssert.Contains("`" + name + ".png`", text, name + ".png is not in docs/LICENSES.md");
            }
        }
    }
}
