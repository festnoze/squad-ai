// Owned by the wave C biome-electric-liquid package. EditMode checks of:
// - the current packet (visuals-chase-front-not-brightest, electric part): halo opacity and head size of ElectricFx, the
//   LDR-safe spark star of ElectricOverlay (its white-blue core stays below white) and the spark dots of ElectricBead
//   (they peak at 1.1 x the player color and never clip to white for any electric player color);
// - the shader rules of the fix plan on the package's shaders: no derivative (ddx, ddy, fwidth, or a helper that uses
//   one) and no implicit-LOD sample inside a [branch] block, and no new texture fetch (perf-04, perf-06);
// - the electric fill (visuals-reveal-age-staircase): the reveal age is read once, clamped, and only gates the effects;
// - the liquid crease, the home chevron cap requested by the actors package (ElectricOverlay shape 2), the compile of
//   every owned graph's forward pass for GLES3x and Direct3D 11, and the no-em-dash rule on the package's files.
// The source checks read the .hlsl files (Assets/Resources/Shaders); the compile check uses ShaderData, no GPU.
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using NUnit.Framework;
using PainterIO.Runtime;
using UnityEngine;

namespace PainterIO.Tests
{
    public class WaveC_BiomeElectricLiquidTests
    {
        private static readonly string[] OwnedShaders =
        {
            "ElectricComposite.hlsl", "ElectricOverlay.hlsl", "ElectricBead.hlsl", "LiquidComposite.hlsl",
        };

        private static string ShaderSource(string file)
        {
            string path = Path.Combine(Application.dataPath, "Resources", "Shaders", file);
            Assert.IsTrue(File.Exists(path), "missing " + path);
            return File.ReadAllText(path);
        }

        // Strips // and /* */ comments so the checks only see code.
        private static string StripComments(string s)
        {
            s = Regex.Replace(s, @"/\*.*?\*/", " ", RegexOptions.Singleline);
            return Regex.Replace(s, @"//[^\n]*", "");
        }

        // Index just past the brace block that starts at the first '{' at or after `from` (-1 if none).
        private static int BlockEnd(string s, int from, out int open)
        {
            open = s.IndexOf('{', from);
            if (open < 0) return -1;
            int depth = 0;
            for (int i = open; i < s.Length; i++)
            {
                if (s[i] == '{') depth++;
                else if (s[i] == '}' && --depth == 0) return i + 1;
            }
            return -1;
        }

        // Body of every top-level function of the file, by name.
        private static Dictionary<string, string> Functions(string code)
        {
            var result = new Dictionary<string, string>();
            var head = new Regex(@"^(?:float[234]?|half[234]?|void|bool|int|uint)\s+(\w+)\s*\(", RegexOptions.Multiline);
            foreach (Match m in head.Matches(code))
            {
                int end = BlockEnd(code, m.Index, out int open);
                int semicolon = code.IndexOf(';', m.Index);
                if (end < 0 || (semicolon >= 0 && semicolon < open)) continue;   // a declaration, not a definition
                result[m.Groups[1].Value] = code.Substring(open, end - open);
            }
            return result;
        }

        private static readonly Regex Derivative = new Regex(@"\b(?:ddx|ddy|fwidth|ddx_fine|ddy_fine|ddx_coarse|ddy_coarse)\s*\(|\bSAMPLE_TEXTURE2D\s*\(|\btex2D\s*\(");

        // Names of the file's functions that use a derivative, directly or through another of its functions.
        private static HashSet<string> DerivativeFunctions(Dictionary<string, string> functions)
        {
            var found = new HashSet<string>();
            bool grew = true;
            while (grew)
            {
                grew = false;
                foreach (KeyValuePair<string, string> f in functions)
                {
                    if (found.Contains(f.Key)) continue;
                    bool uses = Derivative.IsMatch(f.Value);
                    foreach (string g in found)
                    {
                        if (uses) break;
                        uses = Regex.IsMatch(f.Value, @"\b" + g + @"\s*\(");
                    }
                    if (!uses) continue;
                    found.Add(f.Key);
                    grew = true;
                }
            }
            return found;
        }

        [Test]
        public void WaveC_PacketHalo_IsStronger_AndHeadIsOneAndAHalfTimesLarger()
        {
            Assert.AreEqual(0.8f, ElectricFx.PacketHaloOpacity, 1e-6f, "halo opacity 0.4 -> 0.8");
            Assert.AreEqual(0.8f * 1.5f, ElectricFx.PacketHalfSize.x, 1e-5f, "head half length 1.5 x 0.8 u");
            Assert.AreEqual(0.46f * 1.5f, ElectricFx.PacketHalfSize.y, 1e-5f, "head half width 1.5 x 0.46 u");
            // The shape keeps the forward reach of the B-2 head: its forward falloff factor is the size ratio squared.
            Match ahead = Regex.Match(ShaderSource("ElectricOverlay.hlsl"), @"#define\s+PIOE_PACKET_AHEAD\s+([0-9.]+)");
            Assert.IsTrue(ahead.Success, "PIOE_PACKET_AHEAD");
            float ratio = ElectricFx.PacketHalfSize.x / 0.8f;
            Assert.AreEqual(ratio * ratio, float.Parse(ahead.Groups[1].Value, CultureInfo.InvariantCulture), 1e-4f);
        }

        private static float Luma(Color linear)
        {
            Color s = new Color(Mathf.Clamp01(linear.r), Mathf.Clamp01(linear.g), Mathf.Clamp01(linear.b)).gamma;
            return 255f * (0.299f * s.r + 0.587f * s.g + 0.114f * s.b);
        }

        [Test]
        public void WaveC_SparkDots_NeverClipToWhite_ForAnyElectricColor()
        {
            string bead = StripComments(ShaderSource("ElectricBead.hlsl"));
            Match peak = Regex.Match(bead, @"#define\s+PIOE_DOT_PEAK\s+([0-9.]+)");
            Assert.IsTrue(peak.Success, "PIOE_DOT_PEAK");
            float k = float.Parse(peak.Groups[1].Value, CultureInfo.InvariantCulture);
            Assert.AreEqual(1.1f, k, 1e-4f);
            // The spark dot branch (after the orb branch) is a capped multiple of the player color: no white-hot core.
            int orb = bead.IndexOf("if (radius > PIOE_BEAD_ORB_RADIUS)", System.StringComparison.Ordinal);
            Assert.GreaterOrEqual(orb, 0, "orb branch");
            int orbEnd = BlockEnd(bead, orb, out _);
            int elseEnd = BlockEnd(bead, orbEnd, out int elseOpen);
            string dot = bead.Substring(elseOpen, elseEnd - elseOpen);
            StringAssert.Contains("min(PIOE_DOT_PEAK", dot);
            Assert.IsFalse(Regex.IsMatch(dot, @"\bhot\b"), "the spark dot no longer blends toward white");

            BiomeTheme theme = BiomeTheme.Get(BiomeId.Electric);
            Assert.AreEqual(4, theme.PlayerColors.Length);
            foreach (Color c in theme.PlayerColors)
            {
                Color lin = c.linear * k;
                Assert.Less(Luma(lin), 235f, "a spark dot of " + c + " would read as white");
                // It keeps its hue: the brightest channel clips, the others stay well below it.
                float min = Mathf.Min(Mathf.Clamp01(lin.r), Mathf.Min(Mathf.Clamp01(lin.g), Mathf.Clamp01(lin.b)));
                Assert.Less(min, 0.5f, "a spark dot of " + c + " lost its color");
            }
        }

        [Test]
        public void WaveC_SparkStar_IsLdrSafe_WhiteCenterOnly()
        {
            string overlay = StripComments(ShaderSource("ElectricOverlay.hlsl"));
            Match white = Regex.Match(overlay, @"#define\s+PIOE_GLINT_WHITE\s+([0-9.]+)");
            Match blue = Regex.Match(overlay, @"#define\s+PIOE_GLINT_BLUE\s+float3\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)");
            Match center = Regex.Match(overlay, @"#define\s+PIOE_GLINT_CENTER\s+([0-9.]+)");
            Assert.IsTrue(white.Success && blue.Success && center.Success, "spark star constants");
            Assert.AreEqual(0.1f, float.Parse(white.Groups[1].Value, CultureInfo.InvariantCulture), 1e-4f, "white center radius (u)");
            Assert.Greater(float.Parse(center.Groups[1].Value, CultureInfo.InvariantCulture), 1.1f, "the center feeds the High bloom");
            var b = new Color(float.Parse(blue.Groups[1].Value, CultureInfo.InvariantCulture),
                              float.Parse(blue.Groups[2].Value, CultureInfo.InvariantCulture),
                              float.Parse(blue.Groups[3].Value, CultureInfo.InvariantCulture));
            // The brightest white-blue core: a white vertex color (the glint's), lerped 0.75 toward the blue, times 1.1.
            Color core = Color.Lerp(Color.white, b, 0.75f) * 1.1f;
            Assert.Less(Luma(core), 235f, "the white-blue core must stay below white without bloom");
            StringAssert.Contains("PIOE_GLINT_WHITE / unitsPerLocal", overlay, "the white center is sized in world units");
        }

        [Test]
        public void WaveC_HomeChevron_IsCappedBelowWhite()
        {
            // Needs of the actors package: the electric chevron (shape 2) no longer boosts the off-white home chevron to
            // white beside the current packet (contract 25.5). Its fill is capped at PIOE_CHEVRON_MAX, below luma 235.
            string overlay = StripComments(ShaderSource("ElectricOverlay.hlsl"));
            Match cap = Regex.Match(overlay, @"#define\s+PIOE_CHEVRON_MAX\s+([0-9.]+)");
            Assert.IsTrue(cap.Success, "PIOE_CHEVRON_MAX");
            float k = float.Parse(cap.Groups[1].Value, CultureInfo.InvariantCulture);
            Assert.Less(Luma(new Color(k, k, k)), 235f, "a capped chevron fill reads below white");
            Assert.IsTrue(Regex.IsMatch(overlay, @"fill\s*=\s*min\([^;]*,\s*PIOE_CHEVRON_MAX\)"), "the chevron fill is capped");
            Assert.IsFalse(overlay.Contains("(1.15 + 0.25"), "the 1.15 to 1.4 boost is gone");
        }

        [Test]
        public void WaveC_OwnedShaders_NoDerivativeOrImplicitLodSampleInsideDynamicBranches()
        {
            foreach (string file in OwnedShaders)
            {
                string code = StripComments(ShaderSource(file));
                HashSet<string> derivative = DerivativeFunctions(Functions(code));
                int at = 0;
                int branches = 0;
                while ((at = code.IndexOf("[branch]", at, System.StringComparison.Ordinal)) >= 0)
                {
                    int end = BlockEnd(code, at, out int open);
                    Assert.Greater(end, 0, file + ": unbalanced [branch] block");
                    // An else block belongs to the same dynamic branch.
                    Match elseMatch = new Regex(@"\G\s*else\b").Match(code, end);
                    if (elseMatch.Success) end = BlockEnd(code, elseMatch.Index + elseMatch.Length, out _);
                    string block = code.Substring(at, end - at);
                    string line = code.Substring(at, Mathf.Min(60, code.Length - at)).Split('\n')[0];
                    Assert.IsFalse(Derivative.IsMatch(block), file + ": derivative or implicit-LOD sample in " + line);
                    foreach (string f in derivative)
                    {
                        Assert.IsFalse(Regex.IsMatch(block, @"\b" + f + @"\s*\("), file + ": " + f + " (uses a derivative) called in " + line);
                    }
                    branches++;
                    at = open + 1;                                     // nested branches are counted (and checked) too
                }
                if (file == "ElectricComposite.hlsl") Assert.GreaterOrEqual(branches, 7, "bicubic, ground, plasma, discharge, micro arcs, hop, actor");
                if (file == "LiquidComposite.hlsl") Assert.GreaterOrEqual(branches, 10, "3 fetch helpers, shadows (+ territory tap), ground, puddle (+ crease), actor, central");
            }
        }

        private static int Count(string code, string pattern)
        {
            return Regex.Matches(code, pattern).Count;
        }

        [Test]
        public void WaveC_Composites_KeepTheirFetchCount()
        {
            // Wave C adds no texture fetch (contract 12.2 item 4): the counts of the B-2 sources (each B-spline helper
            // holds 4 bilinear taps used only on High).
            string elec = StripComments(ShaderSource("ElectricComposite.hlsl"));
            Assert.AreEqual(10, Count(elec, @"SAMPLE_TEXTURE2D_LOD\s*\("), "ElectricComposite fetch sites");
            Assert.AreEqual(1, Count(elec, @"SAMPLE_TEXTURE2D_LOD\s*\(\s*_PIO_RevealTime"), "one reveal fetch");
            string liquid = StripComments(ShaderSource("LiquidComposite.hlsl"));
            Assert.AreEqual(13, Count(liquid, @"SAMPLE_TEXTURE2D_LOD\s*\("), "LiquidComposite fetch sites");
        }

        [Test]
        public void WaveC_ElectricFill_ClampsTheAge_AndDrawsNoEdgeFromIt()
        {
            string elec = StripComments(ShaderSource("ElectricComposite.hlsl"));
            Match max = Regex.Match(elec, @"#define\s+PIOE_FILL_AGE\s+([0-9.]+)");
            Assert.IsTrue(max.Success, "PIOE_FILL_AGE");
            Assert.AreEqual(0.4f, float.Parse(max.Groups[1].Value, CultureInfo.InvariantCulture), 1e-4f);
            // The only use of the clock is the clamped age; the effects follow the wide relief field (band, crest).
            Assert.AreEqual(1, Count(elec, @"_PIO_Now"), "one use of _PIO_Now");
            StringAssert.Contains("clamp(_PIO_Now - rev, 0.0, PIOE_FILL_AGE)", elec);
            Assert.IsFalse(Regex.IsMatch(elec, @"\bage\b"), "no unclamped age left");
            StringAssert.Contains("sweep = gate * band", elec);
            Assert.IsTrue(Regex.IsMatch(elec, @"band\s*=\s*smoothstep\([^;]*wide"), "the band comes from the wide relief field");
        }

        [Test]
        public void WaveC_LiquidCrease_FlattensAndCapsTheLitSlope()
        {
            string liquid = StripComments(ShaderSource("LiquidComposite.hlsl"));
            // The AA width must not come from fwidth(gap) (V-shaped at the contact, it collapses in straddling quads).
            StringAssert.Contains("fwCrease = max(dot(fwT, saturate(mj + m2)), 1e-4)", liquid);
            StringAssert.Contains("crease = 1.0 - smoothstep(creaseCore", liquid);
            StringAssert.Contains("puddle = lerp(puddle, flat * (1.0 - PIO_CREASE_DARK * crease), crease)", liquid);
            StringAssert.Contains("PIO_H0 / (2.0 * pix)", liquid);
            Match dark = Regex.Match(liquid, @"#define\s+PIO_CREASE_DARK\s+([0-9.]+)");
            Assert.IsTrue(dark.Success, "PIO_CREASE_DARK");
            Assert.AreEqual(0.25f, float.Parse(dark.Groups[1].Value, CultureInfo.InvariantCulture), 1e-4f);
            // The crease gradient is computed before the shading branch and used by the actor path (no seam).
            int gT = liquid.IndexOf("float2 gT =", System.StringComparison.Ordinal);
            int shade = liquid.IndexOf("PIO_ShadeLiquid((half3)albedoT", System.StringComparison.Ordinal);
            Assert.Greater(gT, 0);
            Assert.Greater(shade, gT);
            StringAssert.Contains("float2 gradH = gT + (gradHA - gradHT);", liquid);
        }

        // Shader rule 4 of the plan: the graphs must compile for GLES3 as well as for Direct3D. ShaderCheck compiles only
        // for the editor's API and a Windows build never compiles for GLES3. Note: the URP Unlit Shader Graph target has a
        // single subshader whose Universal Forward pass is "#pragma target 2.0" on every platform (only its GBuffer pass is
        // 4.5), so SHADER_TARGET is 20 in the forward pass everywhere and Gather-only code paths never run. Every forward
        // pass is compiled here for GLES3x (Android target) and for Direct3D 11 (Windows target), base variant.
        [Test]
        public void WaveC_OwnedGraphsCompileOnEverySubshader()
        {
            string[] graphs = { "ElectricComposite", "ElectricOverlay", "ElectricBead", "LiquidComposite" };
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
                        if (pass.Name.IndexOf("Forward", System.StringComparison.OrdinalIgnoreCase) < 0) continue;
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
                                var msg = new System.Text.StringBuilder();
                                foreach (UnityEditor.ShaderMessage m in info.Messages) msg.Append(m.message).Append(" (line ").Append(m.line).Append(") ");
                                failures.Add(g + " subshader " + s + " pass '" + pass.Name + "' " + stage + " " + platform + ": " + msg);
                            }
                        }
                    }
                }
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
            Assert.GreaterOrEqual(compiled, 16, "the forward pass of each graph was compiled for GLES3 and Direct3D");
            Assert.GreaterOrEqual(gles, 8, "the forward pass of each graph was compiled for GLES3 (vertex and fragment)");
        }

        [Test]
        public void WaveC_PackageFilesHaveNoEmDash()
        {
            var files = new List<string>();
            foreach (string s in OwnedShaders) files.Add(Path.Combine(Application.dataPath, "Resources", "Shaders", s));
            files.Add(Path.Combine(Application.dataPath, "Scripts", "Runtime", "Biomes", "ElectricFx.cs"));
            files.Add(Path.Combine(Application.dataPath, "Tests", "EditMode", "Runtime", "WaveC_BiomeElectricLiquidTests.cs"));
            foreach (string f in files)
            {
                Assert.IsTrue(File.Exists(f), f);
                Assert.AreEqual(-1, File.ReadAllText(f).IndexOf((char)0x2014), Path.GetFileName(f) + " contains an em dash");
            }
        }
    }
}
