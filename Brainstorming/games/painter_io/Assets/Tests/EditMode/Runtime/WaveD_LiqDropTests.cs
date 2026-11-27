// Owned by the wave D liq-drop package (contract 28 F2, docs/WAVE_D_FEEDBACK.md: "the liquid must look more like a
// drop"). EditMode checks of:
// - the dome field of TerritoryField (_PIO_TerritoryDome): published with its texel size, it rises inside a puddle, is
//   0 far from any territory, its gradient points inward, its shadow channel reads higher to the lower right of a puddle,
//   and the scissored path of a fill updates it while a far region stays exactly as it was (GPU read back; skipped
//   without a graphics device);
// - the sources: LiquidComposite reads the dome once (14 fetch sites, one extra: the F2 allowance), LiquidCommon only
//   gained declarations (its two functions and the older globals unchanged), TerritoryBlur passes 0 - 5 and their
//   helpers unchanged with the three dome passes after them and weights matching TerritoryField.DomeSigmaUnits, the fire,
//   electric and overlay shaders never read the dome (their look cannot change), the pearl teardrop only for pearl-sized
//   moving beads, the drop strength published by LiquidTheme;
// - the compile of the package's shaders for GLES3x and Direct3D 11 (every pass of TerritoryBlur, the forward pass of the
//   LiquidComposite and Bead graphs), and the no-em-dash rule on the package's files.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;

namespace PainterIO.Tests
{
    public class WaveD_LiqDropTests
    {
        private const float Frame = 1f / 60f;

        private static string ShaderPath(string file) => Path.Combine(Application.dataPath, "Resources", "Shaders", file);

        private static string ShaderSource(string file)
        {
            string path = ShaderPath(file);
            Assert.IsTrue(File.Exists(path), "missing " + path);
            return File.ReadAllText(path).Replace("\r\n", "\n");
        }

        private static string StripComments(string s)
        {
            s = Regex.Replace(s, @"/\*.*?\*/", " ", RegexOptions.Singleline);
            return Regex.Replace(s, @"//[^\n]*", "");
        }

        private static string Sha256(string s)
        {
            using (SHA256 sha = SHA256.Create())
            {
                byte[] hash = sha.ComputeHash(Encoding.UTF8.GetBytes(s));
                var sb = new StringBuilder();
                foreach (byte b in hash) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Dome field (GPU).

        private static bool HasGpu => SystemInfo.graphicsDeviceType != UnityEngine.Rendering.GraphicsDeviceType.Null;

        private static Texture2D ReadBack(RenderTexture rt)
        {
            RenderTexture previous = RenderTexture.active;
            var texture = new Texture2D(rt.width, rt.height, TextureFormat.RGBAFloat, false, true) { hideFlags = HideFlags.HideAndDontSave };
            try
            {
                RenderTexture.active = rt;
                texture.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
                texture.Apply();
            }
            finally
            {
                RenderTexture.active = previous;
            }
            return texture;
        }

        // (t, dt/dx, dt/dy, t toward the light) at a cell, decoded like LiquidComposite.PIO_FetchDome.
        private static Vector4 DomeAt(Texture2D tex, TerritoryField field, int i, int j)
        {
            Color c = tex.GetPixel(i, j);
            var v = new Vector4(c.r, c.g, c.b, c.a);
            if (field.FieldFormat == UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8B8A8_UNorm)
            {
                v.y = (v.y - 0.5f) * 2f;
                v.z = (v.z - 0.5f) * 2f;
            }
            return v;
        }

        private static void CellOf(OwnerGrid g, double x, double y, out int i, out int j)
        {
            i = Mathf.Clamp((int)Math.Floor((x - g.Origin) / g.CellSize), 0, g.Size - 1);
            j = Mathf.Clamp((int)Math.Floor((y - g.Origin) / g.CellSize), 0, g.Size - 1);
        }

        // Centroid and equivalent radius of the cells a player owns.
        private static void OwnedDisc(OwnerGrid g, byte owner, out double cx, out double cy, out double radius)
        {
            double sx = 0, sy = 0;
            int n = 0;
            for (int c = 0; c < g.Cells.Length; c++)
            {
                if (g.Cells[c] != owner) continue;
                sx += g.Origin + (c % g.Size + 0.5) * g.CellSize;
                sy += g.Origin + (c / g.Size + 0.5) * g.CellSize;
                n++;
            }
            Assert.Greater(n, 0, "player " + owner + " owns cells");
            cx = sx / n;
            cy = sy / n;
            radius = Math.Sqrt(n * g.CellSize * g.CellSize / Math.PI);
        }

        [Test]
        public void WaveD_DomeField_IsPublished_RisesInsidePuddles_AndCastsItsShadowLowerRight()
        {
            var field = new TerritoryField(Resources.Load<Shader>(LiquidRenderer.BlurShaderPath));
            GameSession session = CaptureSession();                    // four start discs far apart, at (+-16, +-16)
            Texture2D tex = null;
            try
            {
                field.Bind(session);
                field.Update(Frame);
                Assert.IsNotNull(field.Dome, "the dome render texture exists");
                Assert.AreEqual(field.Size, field.Dome.width, "the dome is published at the mask size");
                Assert.AreEqual(field.FieldFormat, field.Dome.graphicsFormat, "the dome uses the field format");
                Assert.AreEqual(256, TerritoryField.DomeGridSize(512), "the dome is blurred on a 256 x 256 grid");
                Assert.IsTrue(Shader.GetGlobalTexture("_PIO_TerritoryDome") == field.Dome, "_PIO_TerritoryDome published");
                Vector4 texel = Shader.GetGlobalVector("_PIO_TerritoryDomeTexel");
                Assert.AreEqual(field.Size, texel.z, 1e-3f);
                Assert.AreEqual(1f / field.Size, texel.x, 1e-7f);
                if (!HasGpu) Assert.Ignore("no graphics device: the dome passes cannot be read back");

                tex = ReadBack(field.Dome);
                OwnerGrid g = session.Sim.Grid;
                OwnedDisc(g, 1, out double cx, out double cy, out double radius);
                Assert.That(radius, Is.GreaterThan(1.0), "a start disc of a usable size");

                CellOf(g, cx, cy, out int ci, out int cj);
                Vector4 center = DomeAt(tex, field, ci, cj);
                Assert.That(center.x, Is.GreaterThan(0.6f), "the dome rises inside the start disc (t_dome at its center)");

                // The arena center, about 20 u from every start disc: no dome there.
                CellOf(g, 0.0, 0.0, out int fi, out int fj);
                Assert.That(NearestOwnedDistance(g, fi, fj, 4.5), Is.GreaterThan(4.0), "the arena center is bare");
                Vector4 far = DomeAt(tex, field, fi, fj);
                Assert.That(far.x, Is.LessThan(0.01f), "no dome far from the territories");

                // 0.6 R from the center toward +x: the gradient points back toward the center (inward).
                CellOf(g, cx + 0.6 * radius, cy, out int ri, out int rj);
                Vector4 right = DomeAt(tex, field, ri, rj);
                Assert.That(right.x, Is.LessThan(center.x), "the dome is highest in the middle");
                Assert.That(right.y, Is.LessThan(-0.05f), "dt/dx points inward on the right flank");
                Assert.That(Mathf.Abs(right.z), Is.LessThan(Mathf.Abs(right.y)), "mostly radial");

                // Just outside the lower-right rim, the shadow channel (sampled toward the light) reads more liquid than
                // the pixel itself; just outside the upper-left rim it reads less.
                var lowerRight = new Vector2(0.6f, -0.8f);
                CellOf(g, cx + lowerRight.x * (radius + 0.25), cy + lowerRight.y * (radius + 0.25), out int li, out int lj);
                Vector4 lr = DomeAt(tex, field, li, lj);
                Assert.That(lr.w, Is.GreaterThan(lr.x + 0.05f), "the soft shadow falls on the lower right");
                CellOf(g, cx - lowerRight.x * (radius + 0.25), cy - lowerRight.y * (radius + 0.25), out int ui, out int uj);
                Vector4 ul = DomeAt(tex, field, ui, uj);
                Assert.That(ul.w, Is.LessThan(ul.x), "and not on the upper left");
            }
            finally
            {
                if (tex != null) UnityEngine.Object.DestroyImmediate(tex);
                field.Dispose();
                session.Close();
            }
        }

        private static double NearestOwnedDistance(OwnerGrid g, int i, int j, double reach)
        {
            int r = (int)Math.Ceiling(reach / g.CellSize);
            double best = double.MaxValue;
            for (int y = Math.Max(0, j - r); y <= Math.Min(g.Size - 1, j + r); y++)
            {
                for (int x = Math.Max(0, i - r); x <= Math.Min(g.Size - 1, i + r); x++)
                {
                    byte o = g.Cells[y * g.Size + x];
                    if (o == 0 || o == OwnerGrid.Void) continue;
                    double d = Math.Sqrt((x - i) * (x - i) + (y - j) * (y - j)) * g.CellSize;
                    if (d < best) best = d;
                }
            }
            return best;
        }

        // Player 0 leaves its start disc to the north, draws a 5 x 5 u square and comes back unchased (contract 24); the
        // three others orbit inside their own discs (the LiquidRenderTests capture setup).
        private static GameSession CaptureSession()
        {
            var config = new SimConfig { TickRate = 60, LassoEnabled = false, Seed = 3 };
            var home = new Vec2d(-16, -16);
            var path = new List<Vec2d> { new Vec2d(-16, -11), new Vec2d(-11, -11), new Vec2d(-11, -16), new Vec2d(-16, -16) };
            var controllers = new IController[]
            {
                new DemoScenario.PathThenCircleController(path, home),
                new HomeCirclerController(new Vec2d(16, -16)),
                new HomeCirclerController(new Vec2d(16, 16)),
                new HomeCirclerController(new Vec2d(-16, 16)),
            };
            return new GameSession(config, new SimSetup { PlayerCount = 4, HumanIndex = 0 }, controllers, false);
        }

        [Test]
        public void WaveD_DomeField_FollowsAFill_AndLeavesFarRegionsAlone()
        {
            if (!HasGpu) Assert.Ignore("no graphics device: the dome passes cannot be read back");
            var field = new TerritoryField(Resources.Load<Shader>(LiquidRenderer.BlurShaderPath));
            GameSession session = CaptureSession();
            var events = new List<SimEvent>();
            Texture2D before = null, after = null;
            try
            {
                field.Bind(session);
                session.EventRaised += field.OnSimEvent;
                session.EventRaised += e => events.Add(e);
                session.Advance(Frame);
                field.Update(Frame);
                before = ReadBack(field.Dome);
                int passRunsBefore = field.PassRuns;

                bool captured = false;
                for (int k = 0; k < 60 * 30 && !captured; k++)
                {
                    session.Advance(Frame);
                    field.Update(Frame);
                    foreach (SimEvent e in events)
                    {
                        if (e.Type == SimEventType.Return && e.Player == 0 && e.Cells != null && e.Cells.Length > 0) captured = true;
                    }
                }
                Assert.IsTrue(captured, "the unchased return captures the square");
                for (int k = 0; k < 40; k++)
                {
                    session.Advance(Frame);
                    field.Update(Frame);
                }
                Assert.AreEqual(0, field.ActiveWaves, "the fill wave is over");
                Assert.Greater(field.PassRuns, passRunsBefore, "the passes ran for the fill (scissored path)");
                after = ReadBack(field.Dome);

                OwnerGrid g = session.Sim.Grid;
                CellOf(g, -13.0, -13.0, out int ci, out int cj);
                Vector4 b = DomeAt(before, field, ci, cj);
                Vector4 a = DomeAt(after, field, ci, cj);
                Assert.That(a.x, Is.GreaterThan(0.6f), "the captured square is domed after the fill");
                Assert.That(a.x - b.x, Is.GreaterThan(0.3f), "the dome rose with the fill");

                // A region far from the capture (player 2's disc at (16, 16) and its surroundings) is untouched.
                CellOf(g, 16.0, 16.0, out int fi, out int fj);
                float maxDiff = 0f;
                for (int dj = -24; dj <= 24; dj += 4)
                {
                    for (int di = -24; di <= 24; di += 4)
                    {
                        Vector4 d = DomeAt(after, field, fi + di, fj + dj) - DomeAt(before, field, fi + di, fj + dj);
                        maxDiff = Mathf.Max(maxDiff, Mathf.Max(Mathf.Abs(d.x), Mathf.Max(Mathf.Abs(d.y), Mathf.Max(Mathf.Abs(d.z), Mathf.Abs(d.w)))));
                    }
                }
                Assert.That(maxDiff, Is.LessThan(1e-3f), "the scissored dome passes leave far regions alone");
            }
            finally
            {
                if (before != null) UnityEngine.Object.DestroyImmediate(before);
                if (after != null) UnityEngine.Object.DestroyImmediate(after);
                field.Dispose();
                session.Close();
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Sources.

        [Test]
        public void WaveD_LiquidComposite_ReadsTheDomeOnce_OneExtraFetch()
        {
            string code = StripComments(ShaderSource("LiquidComposite.hlsl"));
            Assert.AreEqual(14, Regex.Matches(code, @"SAMPLE_TEXTURE2D_LOD\s*\(").Count, "13 wave C fetch sites + the dome");
            Assert.AreEqual(1, Regex.Matches(code, @"SAMPLE_TEXTURE2D_LOD\s*\(\s*_PIO_TerritoryDome").Count, "one bilinear dome site");
            Assert.AreEqual(1, Regex.Matches(code, @"PIO_FetchDome\s*\(\s*uvT").Count, "the dome is fetched once per pixel");
            int fetch = code.IndexOf("PIO_FetchDome(uvT", StringComparison.Ordinal);
            int actor = code.IndexOf("[branch] if (maxA >= PIO_ACTOR_MIN)", StringComparison.Ordinal);
            int ground = code.IndexOf("[branch] if (cT < 1.0)", StringComparison.Ordinal);
            Assert.Greater(actor, fetch, "the dome fetch is outside the actor branch");
            Assert.Greater(ground, fetch, "and outside the ground and puddle branches");
            StringAssert.Contains("saturate(_PIO_BiomeParams.x)", code, "LiquidTheme.DropStrength scales the drop");
            StringAssert.Contains("(1.0 - domeShadow)", code, "the dome's contact shadow darkens the ground");
            StringAssert.Contains("PIO_DropGloss(albedoT, nD) * bevel", code, "band and hot spot on the puddles");
            StringAssert.Contains("PIO_DropGloss(colK, nD) * (bevel * own)", code, "and on actors lying on their own puddle");
            Match thin = Regex.Match(code, @"#define\s+PIO_DROP_THIN\s+([0-9.]+)");
            Match thick = Regex.Match(code, @"#define\s+PIO_DROP_THICK\s+([0-9.]+)");
            Assert.IsTrue(thin.Success && thick.Success);
            float eThin = float.Parse(thin.Groups[1].Value, CultureInfo.InvariantCulture);
            float eThick = float.Parse(thick.Groups[1].Value, CultureInfo.InvariantCulture);
            Assert.Less(eThin, 1f, "thin liquid lighter");
            Assert.Greater(eThick, 1f, "thick center richer");
            // V5: the palette colors stay close to themselves at both ends (each sRGB channel within 24 levels).
            foreach (Color c in BiomeTheme.Get(BiomeId.Liquid).PlayerColors)
            {
                foreach (float e in new[] { eThin, eThick })
                {
                    Color lin = c.linear;
                    var shifted = new Color(Mathf.Pow(lin.r, e), Mathf.Pow(lin.g, e), Mathf.Pow(lin.b, e)).gamma;
                    Assert.Less(Mathf.Abs(shifted.r - c.r) * 255f, 24f, c + " red at exponent " + e);
                    Assert.Less(Mathf.Abs(shifted.g - c.g) * 255f, 24f, c + " green at exponent " + e);
                    Assert.Less(Mathf.Abs(shifted.b - c.b) * 255f, 24f, c + " blue at exponent " + e);
                }
            }
        }

        [Test]
        public void WaveD_LiquidCommon_AdditionsOnly()
        {
            string src = ShaderSource("LiquidCommon.hlsl");
            int a = src.IndexOf("float PIO_Height(float f)", StringComparison.Ordinal);
            int b = src.IndexOf("#endif // PIO_LIQUID_COMMON_INCLUDED", StringComparison.Ordinal);
            Assert.Greater(a, 0);
            Assert.Greater(b, a);
            Assert.AreEqual("e82a67831d85d84a69a7a1bfbb09013175d5e8a35aa5e5a18ef589bf61982f53", Sha256(src.Substring(a, b - a)),
                "PIO_Height and PIO_ShadeLiquid are byte for byte those of wave C");
            string code = StripComments(src);
            string[] older =
            {
                "TEXTURE2D(_PIO_TerritoryField);", "TEXTURE2D(_PIO_TerritoryHeight);", "float4 _PIO_TerritoryTexel;",
                "float4 _PIO_ArenaRect;", "float _PIO_TerritoryUnorm;", "TEXTURE2D(_PIO_BlurSource);", "float4 _PIO_BlurTexel;",
                "TEXTURE2D(_PIO_ActorField);", "float4 _PIO_ActorRect;", "float4 _PIO_ActorTexel;", "float _PIO_ActorScale;",
                "TEXTURE2D(_PIO_PocketMask);", "float4 _PIO_PocketTexel;", "float4 _PIO_Colors[4];", "float4 _PIO_PlayerFade;",
                "float4 _PIO_ShadowOffset;", "float4 _PIO_Quality;", "float4 _PIO_GroundColor;", "float4 _PIO_OutsideColor;",
                "float4 _PIO_ArenaShape;", "float4 _PIO_Time;", "TEXTURE2D(_PIO_RevealTime);", "float4 _PIO_RevealTexel;",
                "float _PIO_Now;", "float4 _PIO_SecondaryColors[4];", "float4 _PIO_BiomeParams;",
                "#define PIO_H0 0.17", "#define PIO_GRAD_RANGE 6.0",
            };
            foreach (string decl in older) StringAssert.Contains(decl, code, "kept: " + decl);
            StringAssert.Contains("TEXTURE2D(_PIO_TerritoryDome);", code);
            StringAssert.Contains("float4 _PIO_TerritoryDomeTexel;", code);
            // Still exactly two functions.
            int functions = Regex.Matches(code, @"^(?:float[234]?|half[234]?|void)\s+\w+\s*\([^;{]*\)\s*\{", RegexOptions.Multiline).Count;
            Assert.AreEqual(2, functions, "LiquidCommon exposes exactly PIO_Height and PIO_ShadeLiquid");
        }

        [Test]
        public void WaveD_TerritoryBlur_OldPassesUnchanged_DomePassesAppended()
        {
            string src = ShaderSource("TerritoryBlur.shader");
            int s1 = src.IndexOf("#define PIO_BLUR_W0", StringComparison.Ordinal);
            int e1 = src.IndexOf("return max(max(t.x, t.y), max(t.z, t.w));", StringComparison.Ordinal);
            e1 = src.IndexOf('}', e1) + 1;
            Assert.AreEqual("1f27edf757d427e02aec7057d25e15cef49b8c9e698b212c71a43e979defb38f", Sha256(src.Substring(s1, e1 - s1)),
                "the wave C blur helpers are unchanged");
            int s2 = src.IndexOf("Name \"BlurH\"", StringComparison.Ordinal);
            int e2 = src.IndexOf("return PIO_Wide1D(input.uv, float2(0.0, 1.0));", StringComparison.Ordinal);
            e2 = src.IndexOf("ENDHLSL", e2, StringComparison.Ordinal) + 7;
            Assert.AreEqual("edcdeb67c767a03b1899ada443eb1576919f434071e58c4b319186c04e61f317", Sha256(src.Substring(s2, e2 - s2)),
                "passes 0 - 5 (read by the fire and electric composites) are unchanged");
            var names = new List<string>();
            foreach (Match m in Regex.Matches(src, "Name \"(\\w+)\"")) names.Add(m.Groups[1].Value);
            CollectionAssert.AreEqual(new[] { "BlurH", "BlurV", "Upsample", "Height", "WideH", "WideV", "DomeH", "DomeV", "DomeField" }, names);
            var shader = Resources.Load<Shader>(LiquidRenderer.BlurShaderPath);
            Assert.IsNotNull(shader);
            Assert.AreEqual(9, shader.passCount);

            // The Gaussian weights are those of sigma = DomeSigmaUnits on the dome grid, normalized over 21 texels.
            double sigma = TerritoryField.DomeSigmaUnits / (Tuning.CellSize * TerritoryField.DomeDownscale);
            var w = new double[11];
            double sum = 0;
            for (int k = -10; k <= 10; k++) sum += Math.Exp(-0.5 * k * k / (sigma * sigma));
            for (int k = 0; k <= 10; k++)
            {
                w[k] = Math.Exp(-0.5 * k * k / (sigma * sigma)) / sum;
                Match m = Regex.Match(src, @"#define\s+PIO_DOME_W" + k + @"\s+([0-9.]+)");
                Assert.IsTrue(m.Success, "PIO_DOME_W" + k);
                Assert.AreEqual(w[k], double.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture), 2e-7, "PIO_DOME_W" + k);
            }
            for (int p = 1; p <= 5; p++)
            {
                int a = 2 * p - 1, b = 2 * p;
                double pw = w[a] + w[b], po = (a * w[a] + b * w[b]) / pw;
                Match mw = Regex.Match(src, @"#define\s+PIO_DOME_PW" + p + @"\s+([0-9.]+)");
                Match mo = Regex.Match(src, @"#define\s+PIO_DOME_PO" + p + @"\s+([0-9.]+)");
                Assert.IsTrue(mw.Success && mo.Success, "pair " + p);
                Assert.AreEqual(pw, double.Parse(mw.Groups[1].Value, CultureInfo.InvariantCulture), 2e-7, "PIO_DOME_PW" + p);
                Assert.AreEqual(po, double.Parse(mo.Groups[1].Value, CultureInfo.InvariantCulture), 2e-6, "PIO_DOME_PO" + p);
            }
            // The scissor growth covers the whole dome kernel: 20 cells of Gaussian, 1 of box, 4 of B-spline, 3 of shadow
            // reach (0.32 u) and the half-texel gradient.
            Assert.GreaterOrEqual(TerritoryField.DomeGrowCells, 20 + 1 + 4 + 3 + 1);
        }

        [Test]
        public void WaveD_OtherBiomeShaders_NeverReadTheDome()
        {
            foreach (string f in new[] { "FireComposite.hlsl", "FireBead.hlsl", "FireOverlay.hlsl", "ElectricComposite.hlsl",
                                         "ElectricBead.hlsl", "ElectricOverlay.hlsl", "Overlay.hlsl", "Bead.hlsl" })
            {
                Assert.IsFalse(StripComments(ShaderSource(f)).Contains("_PIO_TerritoryDome"), f + " reads the dome field");
            }
        }

        [Test]
        public void WaveD_PearlTeardrop_OnlyForMovingPearls()
        {
            string bead = StripComments(ShaderSource("Bead.hlsl"));
            StringAssert.Contains("float tear = smoothstep(0.28, 0.34, radius) * saturate((stretch - 1.0) * (1.0 / 0.04));", bead);
            StringAssert.Contains("float2 q = PIO_TearWarp(local / radii, tear);", bead, "the bead shape");
            StringAssert.Contains("PIO_TearWarp(localS / (radii * 1.08), tear)", bead, "its shadow follows");
            // Every other bead user passes a radius below 0.28 u or a stretch of 1 (no teardrop): droplets, splash drops,
            // evaporating beads and the retraction bulb bead (0.26 x 0.85 u).
            Assert.Less(RetractionView.BulbRadius * 0.85f, 0.28f, "the bulb bead");
            Assert.Less(RetractionView.DropletMaxRadius, 0.28f, "the droplets");
            Assert.AreEqual(1.04f, PearlView.MovingStretch, 1e-6f, "a pearl running straight is a full slight teardrop");
            Assert.Greater((float)Tuning.HeadRadius, 0.34f, "the pearl radius is above the teardrop threshold");
        }

        [Test]
        public void WaveD_LiquidTheme_PublishesTheDropStrength()
        {
            Assert.AreEqual(1f, LiquidTheme.DropStrength);
            Assert.AreEqual(LiquidTheme.DropStrength, BiomeTheme.Get(BiomeId.Liquid).ShaderParams.x, 1e-6f);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Compile and writing rules.

        [Test]
        public void WaveD_PackageShadersCompileForGles3AndDirect3D()
        {
            var targets = new[]
            {
                ("Assets/Resources/Shaders/TerritoryBlur.shader", false),
                ("Assets/Resources/Shaders/LiquidComposite.shadergraph", true),
                ("Assets/Resources/Shaders/Bead.shadergraph", true),
            };
            int compiled = 0, gles = 0;
            var failures = new List<string>();
            foreach ((string path, bool forwardOnly) in targets)
            {
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
                        if (forwardOnly && pass.Name.IndexOf("Forward", StringComparison.OrdinalIgnoreCase) < 0) continue;
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
                                failures.Add(path + " pass '" + pass.Name + "' " + stage + " " + platform + ": " + msg);
                            }
                        }
                    }
                }
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
            Assert.GreaterOrEqual(compiled, 9 * 4 + 2 * 4, "nine blur passes and two forward passes, vertex and fragment, two APIs");
            Assert.GreaterOrEqual(gles, 9 * 2 + 2 * 2);
        }

        [Test]
        public void WaveD_PackageFilesHaveNoEmDash()
        {
            var files = new List<string>
            {
                ShaderPath("LiquidComposite.hlsl"), ShaderPath("LiquidCommon.hlsl"), ShaderPath("Bead.hlsl"),
                ShaderPath("TerritoryBlur.shader"),
                Path.Combine(Application.dataPath, "Scripts", "Runtime", "Render", "TerritoryField.cs"),
                Path.Combine(Application.dataPath, "Scripts", "Runtime", "Biomes", "LiquidTheme.cs"),
                Path.Combine(Application.dataPath, "Tests", "EditMode", "Runtime", "WaveD_LiqDropTests.cs"),
            };
            foreach (string f in files)
            {
                Assert.IsTrue(File.Exists(f), f);
                Assert.AreEqual(-1, File.ReadAllText(f).IndexOf((char)0x2014), Path.GetFileName(f) + " contains an em dash");
            }
        }
    }
}
