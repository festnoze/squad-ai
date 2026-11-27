// Owned by the wave C biome-fire package. EditMode guards of the fire fixes of docs/waveC/fix_plan.json (perf-01, the
// fire part of visuals-chase-front-not-brightest, visuals-fire-reads-as-lava-tiles, visuals-fire-fill-not-spreading,
// visuals-fire-low-tier-lattice). The look itself is judged on player screenshots; these tests pin what text and
// numbers can prove:
// - shader rule 4 of the plan: in the three fire shaders no ddx / ddy / fwidth and no implicit-LOD sample sits inside a
//   [branch] block (the comments are stripped first);
// - the composite's Medium fetch budget (contract 12.2 item 4: at most 7 without actors) counted on its source;
// - the inverse normal CDF that turns the wide relief field into a world distance (the flame band's coordinate) is
//   accurate to a few thousandths of a unit over the whole band, with the constants the shader really uses;
// - the spark signature (white disc 0.12 u, orange halo 0.45 u) fits the 0.5 u glint quad of the actors package;
// - the FireFx spark budgets (live front shower at most 20, fill sparks bounded, cap 200);
// - both subshaders of the three fire graphs compile (target 2.0 for GLES3, the path without Gather, and target 4.5);
// - no em dash in the package's files.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using NUnit.Framework;
using PainterIO.Runtime;
using UnityEngine;

namespace PainterIO.Tests
{
    public class WaveC_BiomeFireTests
    {
        private static readonly string[] FireShaders = { "FireComposite.hlsl", "FireOverlay.hlsl", "FireBead.hlsl" };

        private static string ShaderPath(string name)
        {
            return Path.Combine(Application.dataPath, "Resources", "Shaders", name);
        }

        private static string StripComments(string src)
        {
            var sb = new StringBuilder(src.Length);
            int i = 0;
            while (i < src.Length)
            {
                if (i + 1 < src.Length && src[i] == '/' && src[i + 1] == '/')
                {
                    while (i < src.Length && src[i] != '\n') i++;
                    continue;
                }
                if (i + 1 < src.Length && src[i] == '/' && src[i + 1] == '*')
                {
                    int end = src.IndexOf("*/", i + 2, StringComparison.Ordinal);
                    i = end < 0 ? src.Length : end + 2;
                    continue;
                }
                sb.Append(src[i]);
                i++;
            }
            return sb.ToString();
        }

        private static int SkipSpace(string s, int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
            return i;
        }

        // Index just past the bracket matching the one at s[open].
        private static int Match(string s, int open, char o, char c)
        {
            int depth = 0;
            for (int i = open; i < s.Length; i++)
            {
                if (s[i] == o) depth++;
                else if (s[i] == c && --depth == 0) return i + 1;
            }
            throw new AssertionException("unbalanced " + o + c + " from index " + open);
        }

        // One statement starting at i: a braced block or a single statement up to its semicolon.
        private static int Statement(string s, int i, StringBuilder into)
        {
            i = SkipSpace(s, i);
            int end = s[i] == '{' ? Match(s, i, '{', '}') : s.IndexOf(';', i) + 1;
            into.Append(s, i, end - i).Append('\n');
            return end;
        }

        // The text of every [branch] if statement, with its else and else-if parts.
        private static List<string> BranchBodies(string src)
        {
            var bodies = new List<string>();
            int at = 0;
            while ((at = src.IndexOf("[branch]", at, StringComparison.Ordinal)) >= 0)
            {
                int i = SkipSpace(src, at + "[branch]".Length);
                Assert.That(src.Substring(i, 2), Is.EqualTo("if"), "[branch] must annotate an if at index " + at);
                var body = new StringBuilder();
                while (true)
                {
                    i = SkipSpace(src, i + 2);
                    i = Match(src, i, '(', ')');
                    i = Statement(src, i, body);
                    int j = SkipSpace(src, i);
                    if (!src.Substring(j).StartsWith("else", StringComparison.Ordinal)) break;
                    int k = SkipSpace(src, j + 4);
                    if (src.Substring(k).StartsWith("if", StringComparison.Ordinal) && !char.IsLetterOrDigit(src[k + 2]))
                    {
                        i = k;
                        continue;
                    }
                    i = Statement(src, k, body);
                    break;
                }
                bodies.Add(body.ToString());
                at += "[branch]".Length;                       // nested branches are listed on their own as well
            }
            return bodies;
        }

        [Test]
        public void WaveC_FireShadersKeepDerivativesAndImplicitLodOutOfDynamicBranches()
        {
            var forbidden = new Regex(@"\b(ddx|ddy|ddx_fine|ddy_fine|ddx_coarse|ddy_coarse|fwidth|tex2D|SAMPLE_TEXTURE2D)\s*\(");
            int checkedBranches = 0;
            foreach (string name in FireShaders)
            {
                string src = StripComments(File.ReadAllText(ShaderPath(name)));
                foreach (string body in BranchBodies(src))
                {
                    checkedBranches++;
                    Match m = forbidden.Match(body);
                    Assert.IsFalse(m.Success, name + ": '" + m.Value + "' inside a [branch] block:\n" + body);
                }
            }
            Assert.That(checkedBranches, Is.GreaterThanOrEqualTo(8), "the composite branches its expensive layers (perf-01)");
        }

        [Test]
        public void WaveC_FireCompositeMediumFetchBudgetIsAtMostSeven()
        {
            string src = StripComments(File.ReadAllText(ShaderPath("FireComposite.hlsl")));
            int start = src.IndexOf("void PIO_FireCompositeSG_float", StringComparison.Ordinal);
            Assert.That(start, Is.GreaterThan(0));
            int body = src.IndexOf('{', start);
            string main = src.Substring(body, Match(src, body, '{', '}') - body);
            int direct = Regex.Matches(main, @"\bSAMPLE_TEXTURE2D_LOD\s*\(").Count;
            int gathers = Regex.Matches(main, @"\b(PIO_FireWideDistance|PIO_FireRevealAges)\s*\(").Count;   // one fetch each
            int bspline = Regex.Matches(main, @"\bPIO_FireSampleBSpline\s*\(").Count;                    // High only
            Assert.AreEqual(1, bspline, "High's B-spline territory fetch replaces the bilinear one");
            Assert.AreEqual(0, Regex.Matches(main, @"\bGATHER_\w+\s*\(").Count, "gathers go through the two helpers");
            // Medium: every bilinear fetch of the main function (the bilinear territory fetch stands for High's B-spline).
            Assert.That(direct + gathers, Is.LessThanOrEqualTo(7), "contract 12.2 item 4, Medium without actors");
        }

        // The shader's inverse normal CDF (Abramowitz and Stegun 26.2.23), same constants as PIO_FireEdgeDistance.
        private static double EdgeDistance(double t, double sigma)
        {
            double p = Math.Min(Math.Max(Math.Min(t, 1.0 - t), 1e-7), 0.5);
            double s = Math.Sqrt(-2.0 * Math.Log(p));
            double z = s - (2.515517 + s * (0.802853 + s * 0.010328)) / (1.0 + s * (1.432788 + s * (0.189269 + s * 0.001308)));
            return (t < 0.5 ? z : -z) * sigma;
        }

        // Upper tail of the standard normal, Q(z) = erfc(z / sqrt 2) / 2, from a series and a continued fraction.
        private static double NormalTail(double z)
        {
            if (z < 0.0) return 1.0 - NormalTail(-z);
            double x = z / Math.Sqrt(2.0);
            if (x < 2.0)
            {
                // erf by its Taylor series.
                double sum = 0.0, term = x;
                for (int n = 0; n < 60; n++)
                {
                    sum += term / (2 * n + 1);
                    term *= -x * x / (n + 1);
                }
                return 0.5 * (1.0 - 2.0 / Math.Sqrt(Math.PI) * sum);
            }
            // erfc by Lentz's continued fraction.
            double f = x, c = x, d = 0.0;
            for (int n = 1; n < 200; n++)
            {
                double an = n * 0.5;
                d = 1.0 / (x + an * d);
                c = x + an / c;
                f *= c * d;
            }
            return 0.5 * Math.Exp(-x * x) / (f * Math.Sqrt(Math.PI));
        }

        [Test]
        public void WaveC_FireEdgeDistanceInvertsTheWideEdgeProfile()
        {
            string src = File.ReadAllText(ShaderPath("FireComposite.hlsl"));
            foreach (string k in new[] { "2.515517", "0.802853", "0.010328", "1.432788", "0.189269", "0.001308" })
            {
                StringAssert.Contains(k, src, "the shader keeps the coefficient " + k);
            }
            Match sigma = Regex.Match(src, @"#define\s+PIO_FIRE_WIDE_SIGMA\s+([0-9.]+)");
            Assert.IsTrue(sigma.Success);
            double s = double.Parse(sigma.Groups[1].Value, System.Globalization.CultureInfo.InvariantCulture);
            // TerritoryBlur: total sigma sqrt(1.28^2 + 1.6^2 + 1/3) mask texels of 0.125 u (narrow, wide, B-spline taps).
            double expected = Math.Sqrt(1.28 * 1.28 + 1.6 * 1.6 + 1.0 / 3.0) * 0.125;
            Assert.AreEqual(expected, s, 0.003, "PIO_FIRE_WIDE_SIGMA matches the blur chain");
            for (double x = -0.7; x <= 1.2 + 1e-9; x += 0.05)
            {
                double t = NormalTail(x / s);                      // the wide field of a straight edge at distance x
                Assert.AreEqual(x, EdgeDistance(t, s), 0.002, "distance at x = " + x);
            }
            Assert.AreEqual(0.0, EdgeDistance(0.5, s), 1e-3, "the contour");
        }

        [Test]
        public void WaveC_FireSparkSignatureFitsTheActorsGlintQuad()
        {
            string src = File.ReadAllText(ShaderPath("FireOverlay.hlsl"));
            double disc = double.Parse(Regex.Match(src, @"#define\s+PIO_FIRE_SPARK_DISC\s+([0-9.]+)").Groups[1].Value,
                                       System.Globalization.CultureInfo.InvariantCulture);
            double halo = double.Parse(Regex.Match(src, @"#define\s+PIO_FIRE_SPARK_HALO\s+([0-9.]+)").Groups[1].Value,
                                       System.Globalization.CultureInfo.InvariantCulture);
            Assert.AreEqual(0.12, disc, 0.02, "white disc of about 0.12 u");
            Assert.AreEqual(0.45, halo, 0.05, "orange halo of about 0.45 u");
            Assert.That(halo, Is.LessThanOrEqualTo(RetractionView.GlintHalfSize), "the halo fits the glint quad (cross-package value)");
            Assert.That(disc * 2.0, Is.LessThan(halo), "the disc sits well inside its halo");
            // The orange is #FF8A2A in linear space (the LDR signature).
            StringAssert.Contains("float3(1.0, 0.254, 0.0232)", src);
        }

        [Test]
        public void WaveC_FireFxSparkBudgets()
        {
            Assert.That(FireFx.MaxParticles, Is.LessThanOrEqualTo(200), "contract 25.5 particle cap");
            Assert.That(FireFx.MaxFrontSparks, Is.LessThanOrEqualTo(20), "fix plan: at most 20 live sparks at the live front");
            Assert.That(FireFx.SparkRate * FireFx.SparkLifeMax, Is.LessThanOrEqualTo(FireFx.MaxFrontSparks), "front shower bound");
            Assert.That(FireFx.SparkLifeMin, Is.GreaterThan(0f).And.LessThan(FireFx.SparkLifeMax));
            Assert.That(FireFx.FillSparkRate * FireFx.FillSparkLifeMax, Is.LessThanOrEqualTo(25f), "fill sparks stay a few");
            Assert.That(FireFx.FillSparkLifeMin, Is.GreaterThan(0f).And.LessThan(FireFx.FillSparkLifeMax));
            Assert.That(FireFx.MaxFills, Is.GreaterThan(0));
            Assert.That(BiomeTheme.Get(BiomeId.Fire).FillDuration, Is.EqualTo(0.6f).Within(1e-6f), "FillDuration unchanged (25.2)");
        }

        // Shader rule 4 of the plan: each fire graph must compile for GLES3 as well as for Direct3D 11. ShaderCheck
        // compiles only for the editor's API and a Windows build never compiles for GLES3. Gate C note: the URP Unlit
        // Shader Graph forward pass is "#pragma target 2.0" on every platform, so SHADER_TARGET is 20 and the Gather
        // path (PIO_FIRE_GATHER) is compiled out everywhere; the bilinear fallback is what ships. Every forward pass is
        // therefore compiled here for BOTH GLES3x (Android) and Direct3D 11 (Windows), base variant, no keywords.
        [Test]
        public void WaveC_FireGraphsCompileOnEverySubshader()
        {
            string[] graphs = { "FireComposite", "FireOverlay", "FireBead" };
            var targetRx = new Regex(@"#pragma\s+target\s+([0-9.]+)");
            int compiled = 0, gles = 0;
            var failures = new List<string>();
            foreach (string g in graphs)
            {
                string path = "Assets/Resources/Shaders/" + g + ".shadergraph";
                var shader = UnityEditor.AssetDatabase.LoadAssetAtPath<Shader>(path);
                Assert.IsNotNull(shader, path);
                UnityEditor.ShaderData data = UnityEditor.ShaderUtil.GetShaderData(shader);
                Assert.IsNotNull(data, path);
                for (int s = 0; s < data.SubshaderCount; s++)
                {
                    UnityEditor.ShaderData.Subshader sub = data.GetSubshader(s);
                    for (int p = 0; p < sub.PassCount; p++)
                    {
                        UnityEditor.ShaderData.Pass pass = sub.GetPass(p);
                        if (pass.Name.IndexOf("Forward", StringComparison.OrdinalIgnoreCase) < 0) continue;
                        Match t = targetRx.Match(pass.SourceCode ?? "");
                        string target = t.Success ? t.Groups[1].Value : "?";
                        foreach (bool low in new[] { true, false })
                        {
                            var platform = low ? UnityEditor.Rendering.ShaderCompilerPlatform.GLES3x : UnityEditor.Rendering.ShaderCompilerPlatform.D3D;
                            var buildTarget = low ? UnityEditor.BuildTarget.Android : UnityEditor.BuildTarget.StandaloneWindows64;
                            foreach (var stage in new[] { UnityEditor.Rendering.ShaderType.Vertex, UnityEditor.Rendering.ShaderType.Fragment })
                            {
                                if (!pass.HasShaderStage(stage)) continue;
                                UnityEditor.ShaderData.VariantCompileInfo info = pass.CompileVariant(stage, new string[0], platform, buildTarget);
                                compiled++;
                                if (low) gles++;
                                if (info.Success) continue;
                                var msg = new StringBuilder();
                                foreach (UnityEditor.ShaderMessage m in info.Messages) msg.Append(m.message).Append(" (line ").Append(m.line).Append(") ");
                                failures.Add(g + " subshader " + s + " pass '" + pass.Name + "' target " + target + " " + stage + " " + platform + ": " + msg);
                            }
                        }
                    }
                }
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
            Assert.That(compiled, Is.GreaterThanOrEqualTo(12), "the forward pass of each graph was compiled for GLES3 and Direct3D 11");
            Assert.That(gles, Is.GreaterThanOrEqualTo(6), "the forward pass of each graph was compiled for GLES3 (vertex and fragment)");
        }

        [Test]
        public void WaveC_FirePackageFilesHaveNoEmDash()
        {
            string[] files =
            {
                ShaderPath("FireComposite.hlsl"), ShaderPath("FireOverlay.hlsl"), ShaderPath("FireBead.hlsl"),
                Path.Combine(Application.dataPath, "Scripts", "Runtime", "Biomes", "FireFx.cs"),
                Path.Combine(Application.dataPath, "Tests", "EditMode", "Runtime", "WaveC_BiomeFireTests.cs"),
            };
            foreach (string f in files)
            {
                Assert.IsTrue(File.Exists(f), f);
                Assert.AreEqual(-1, File.ReadAllText(f).IndexOf((char)0x2014), Path.GetFileName(f) + " contains an em dash");
            }
        }
    }
}
