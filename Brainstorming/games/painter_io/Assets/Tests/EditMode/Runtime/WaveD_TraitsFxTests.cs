// Owned by the wave D-2 traits-fx package (docs/BIOME_TRAITS.md sections 5 and 7.2: the generic trait visuals). EditMode
// checks of:
// - TerritoryField (CPU side, on the scripted demo round under a trait set): a Propagation ring is revealed as a slow
//   creep (several angular steps over GrowSeconds, never all at once) with a _PIO_GrowPulse envelope; an inherited land
//   (KillInheritance) is swept in the killer's color from the kill point after InheritDelaySeconds; scorched cells
//   (ScorchedEarth) fade in, hold, fade out over the last 2 s and leave; a classic round touches none of it;
// - the shader sources: no fetch added to any composite (the scorch rides the reveal fetch, FireComposite reuses the
//   actor glow tap's slot under a uniform gate), the rim wall and the growth pulse in every composite, the trait shapes
//   16 - 21 in the three overlay shaders and below sRGB luma 235, LiquidCommon additions only;
// - TraitFxView helpers and the no-em-dash rule on the package's files.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;

namespace PainterIO.Tests
{
    public class WaveD_TraitsFxTests
    {
        private const float Frame = 1f / 60f;

        private static string ShaderSource(string file)
        {
            string path = Path.Combine(Application.dataPath, "Resources", "Shaders", file);
            Assert.IsTrue(File.Exists(path), "missing " + path);
            return File.ReadAllText(path).Replace("\r\n", "\n");
        }

        private static string StripComments(string s)
        {
            s = Regex.Replace(s, @"/\*.*?\*/", " ", RegexOptions.Singleline);
            return Regex.Replace(s, @"//[^\n]*", "");
        }

        private static int Count(string code, string pattern) => Regex.Matches(code, pattern).Count;

        // Body of the first brace block at or after `from`.
        private static string Block(string s, int from)
        {
            int open = s.IndexOf('{', from);
            Assert.GreaterOrEqual(open, 0);
            int depth = 0;
            for (int i = open; i < s.Length; i++)
            {
                if (s[i] == '{') depth++;
                else if (s[i] == '}' && --depth == 0) return s.Substring(open, i + 1 - open);
            }
            Assert.Fail("unbalanced block");
            return null;
        }

        // ------------------------------------------------------------------------------------------------------------
        // TerritoryField on the demo round.

        private sealed class Run : IDisposable
        {
            public readonly GameSession Session;
            public readonly TerritoryField Field;
            public readonly List<SimEvent> Events = new List<SimEvent>();

            public Run(string traits)
            {
                Session = DemoScenario.CreateSession(out _, null, RuleTraits.Parse(traits));
                Field = new TerritoryField(Resources.Load<Shader>(LiquidRenderer.BlurShaderPath));
                Field.Bind(Session);
                Session.EventRaised += Field.OnSimEvent;
                Session.EventRaised += e => Events.Add(e);
            }

            public void Step(int frames = 1)
            {
                for (int k = 0; k < frames; k++)
                {
                    Session.Advance(Frame);
                    Field.Update(Frame);
                }
            }

            /// <summary>Steps until an event matches (true) or the frame budget runs out.</summary>
            public bool StepUntil(Func<SimEvent, bool> match, int maxFrames, out SimEvent found)
            {
                found = null;
                for (int k = 0; k < maxFrames; k++)
                {
                    int before = Events.Count;
                    Step();
                    for (int i = before; i < Events.Count; i++)
                    {
                        if (!match(Events[i])) continue;
                        found = Events[i];
                        return true;
                    }
                }
                return false;
            }

            public void Dispose()
            {
                Field.Dispose();
                Session.Close();
            }
        }

        [Test]
        public void WaveD2_TerritoryGrew_CreepsInSteps_WithAGrowPulse()
        {
            using (var run = new Run("Propagation(4,1)"))
            {
                Assert.IsTrue(run.StepUntil(e => e.Type == SimEventType.TerritoryGrew && e.Cells != null && e.Cells.Length > 100,
                                            60 * 9, out SimEvent grew), "a Propagation ring of more than 100 cells");
                int owner = grew.Player + 1;
                int[] cells = grew.Cells;
                Assert.Greater(run.Field.ActiveWaves, 0, "the ring is a wave, not an instant change");
                int shownAtOnce = 0;
                foreach (int c in cells) if (run.Field.VisualOwner(c) == owner) shownAtOnce++;
                Assert.Less(shownAtOnce, cells.Length * 0.6, "the ring is not revealed all at once");

                run.Step(12);
                float pulse = run.Field.GrowPulse[grew.Player];
                Assert.That(pulse, Is.GreaterThan(0.3f), "the grow pulse is up 0.2 s after the growth");

                run.Step(Mathf.CeilToInt(TerritoryField.GrowSeconds * 60f) + 6);
                OwnerGrid g = run.Session.Sim.Grid;
                var ages = new HashSet<int>();
                int owned = 0, shown = 0;
                float now = run.Field.RevealNow;
                foreach (int c in cells)
                {
                    if (g.Cells[c] != owner) continue;
                    owned++;
                    if (run.Field.VisualOwner(c) == owner) shown++;
                    ages.Add(Mathf.RoundToInt((now - run.Field.RevealTimeOf(c)) * 100f));
                }
                Assert.Greater(owned, 0);
                Assert.AreEqual(owned, shown, "every grown cell still owned shows after GrowSeconds");
                Assert.GreaterOrEqual(ages.Count, 3, "the creep reveals the ring in several steps");
                run.Step(Mathf.CeilToInt(TerritoryField.GrowPulseSeconds * 60f));
                Assert.AreEqual(0f, run.Field.GrowPulse[grew.Player], 1e-6f, "the pulse is over");
            }
        }

        [Test]
        public void WaveD2_TerritoryInherited_SweepsTheKillersColorFromTheKillPoint()
        {
            using (var run = new Run("KillInheritance(1,0)"))
            {
                Assert.IsTrue(run.StepUntil(e => e.Type == SimEventType.TerritoryInherited, 60 * 16, out SimEvent inherited),
                              "the demo's fatal cut pays the killer");
                int killer = inherited.Player + 1;
                int[] cells = inherited.Cells;
                Assert.Greater(cells.Length, 100);
                int early = 0;
                foreach (int c in cells) if (run.Field.VisualOwner(c) == killer) early++;
                Assert.AreEqual(0, early, "nothing is taken before the sweep starts");

                run.Step(Mathf.CeilToInt((TerritoryField.InheritDelaySeconds + TerritoryField.InheritMaxSeconds) * 60f) + 6);
                OwnerGrid g = run.Session.Sim.Grid;
                float now = run.Field.RevealNow;
                double cs = g.CellSize, org = g.Origin;
                var pairs = new List<KeyValuePair<double, float>>();
                foreach (int c in cells)
                {
                    if (g.Cells[c] != killer) continue;
                    Assert.AreEqual(killer, run.Field.VisualOwner(c), "the inherited land shows the killer's color");
                    double dx = org + (c % g.Size + 0.5) * cs - inherited.Point.X;
                    double dy = org + (c / g.Size + 0.5) * cs - inherited.Point.Y;
                    pairs.Add(new KeyValuePair<double, float>(Math.Sqrt(dx * dx + dy * dy), now - run.Field.RevealTimeOf(c)));
                }
                Assert.Greater(pairs.Count, 100);
                pairs.Sort((a, b) => a.Key.CompareTo(b.Key));
                float nearAge = pairs[0].Value, farAge = pairs[pairs.Count - 1].Value;
                Assert.Greater(nearAge, farAge, "the sweep reaches the near cells first");
                Assert.LessOrEqual(nearAge - farAge, TerritoryField.InheritMaxSeconds + 0.02f, "the sweep lasts at most InheritMaxSeconds");
                Assert.GreaterOrEqual(nearAge - farAge, TerritoryField.InheritMinSeconds - 0.05f, "and at least InheritMinSeconds");
            }
        }

        [Test]
        public void WaveD2_ScorchedCells_FadeIn_Hold_FadeOut_AndLeave()
        {
            using (var run = new Run("ScorchedEarth(15,0)"))
            {
                Assert.IsTrue(run.StepUntil(e => e.Type == SimEventType.Eliminated && e.Cells != null && e.Cells.Length > 0, 60 * 16,
                                            out SimEvent eliminated), "the demo's fatal cut frees the victim's land");
                SimView view = run.Session.Sim.View;
                int probe = -1;
                foreach (int c in eliminated.Cells)
                {
                    if (!view.IsScorched(c)) continue;
                    probe = c;
                    break;
                }
                Assert.GreaterOrEqual(probe, 0, "the freed land is scorched");
                double end = view.ScorchEndTime(probe);
                run.Step(Mathf.CeilToInt(TerritoryField.ScorchFadeInSeconds * 60f) + 4);
                Assert.IsTrue(run.Field.ScorchActive, "_PIO_ScorchOn is set");
                Assert.AreEqual(1f, Shader.GetGlobalFloat("_PIO_ScorchOn"), 1e-6f);
                Assert.That(run.Field.ScorchOf(probe), Is.GreaterThan(0.9f), "fully scorched after the fade in");
                Assert.That(run.Field.RevealTexture.graphicsFormat.ToString(), Does.Contain("G"), "the reveal texture carries G");

                // Run the visual clock to one second before the end (the cells of one elimination share their end time;
                // the ones still neutral show the faded level), then past it.
                for (int k = 0; k < 60 * 20 && run.Field.VisualTime() < end - 1.0; k++) run.Step();
                OwnerGrid g = run.Session.Sim.Grid;
                int neutral = 0;
                foreach (int c in eliminated.Cells)
                {
                    if (g.Cells[c] != 0 || view.ScorchEndTime(c) != end) continue;
                    neutral++;
                    Assert.That(run.Field.ScorchOf(c), Is.InRange(0.3f, 0.7f), "half faded one second before the end");
                }
                Assert.Greater(neutral, 0, "some scorched cells are still neutral");
                for (int k = 0; k < 60 * 3 && run.Field.VisualTime() < end + 0.2; k++) run.Step();
                run.Step(3);
                Assert.AreEqual(0f, run.Field.ScorchOf(probe), "gone after the end");
                Assert.IsFalse(run.Field.ScorchActive);
                Assert.AreEqual(0, run.Field.ScorchTracked, "no cell tracked any more");
                Assert.AreEqual(0f, Shader.GetGlobalFloat("_PIO_ScorchOn"), 1e-6f);
            }
        }

        [Test]
        public void WaveD2_ClassicRound_TouchesNoTraitState()
        {
            using (var run = new Run("classic"))
            {
                run.Step((int)DemoScenario.Caught + 40);
                Assert.AreEqual(0, run.Field.ScorchTracked);
                Assert.IsFalse(run.Field.ScorchActive);
                Assert.AreEqual(Vector4.zero, run.Field.GrowPulse);
                Assert.AreEqual(0f, Shader.GetGlobalFloat("_PIO_ScorchOn"), 1e-6f);
                Assert.AreEqual(Vector4.zero, Shader.GetGlobalVector("_PIO_GrowPulse"));
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Shader sources.

        [Test]
        public void WaveD2_Composites_AddNoFetch_TheScorchRidesTheRevealFetch()
        {
            string liquid = StripComments(ShaderSource("LiquidComposite.hlsl"));
            Assert.AreEqual(14, Count(liquid, @"SAMPLE_TEXTURE2D_LOD\s*\("), "LiquidComposite: wave D sites unchanged");
            Assert.AreEqual(1, Count(liquid, @"SAMPLE_TEXTURE2D_LOD\s*\(\s*_PIO_RevealTime[^;]*\)\.rg"), "one reveal fetch, reading R and G");
            string elec = StripComments(ShaderSource("ElectricComposite.hlsl"));
            Assert.AreEqual(10, Count(elec, @"SAMPLE_TEXTURE2D_LOD\s*\("), "ElectricComposite: sites unchanged");
            Assert.AreEqual(1, Count(elec, @"SAMPLE_TEXTURE2D_LOD\s*\(\s*_PIO_RevealTime[^;]*\)\.rg"), "one reveal fetch, reading R and G");

            string fire = StripComments(ShaderSource("FireComposite.hlsl"));
            int start = fire.IndexOf("void PIO_FireCompositeSG_float", StringComparison.Ordinal);
            string main = Block(fire, start);
            int direct = Count(main, @"\bSAMPLE_TEXTURE2D_LOD\s*\(");
            int helpers = Count(main, @"\b(PIO_FireWideDistance|PIO_FireRevealAges)\s*\(");
            Assert.LessOrEqual(direct + helpers, 7, "FireComposite: Medium budget 7 kept");
            int gate = main.IndexOf("[branch] if (_PIO_ScorchOn > 0.5)", StringComparison.Ordinal);
            Assert.Greater(gate, 0, "the fire scorch fetch is gated by _PIO_ScorchOn");
            StringAssert.Contains("SAMPLE_TEXTURE2D_LOD(_PIO_RevealTime", Block(main, gate), "inside the gate");
            Assert.IsFalse(Regex.IsMatch(main, @"uvA\s*\+\s*off"), "the offset actor glow tap is gone (its slot serves the scorch)");
        }

        [Test]
        public void WaveD2_Composites_HaveTheRimWall_TheGrowPulse_AndTheScorchLook()
        {
            foreach (string file in new[] { "LiquidComposite.hlsl", "FireComposite.hlsl", "ElectricComposite.hlsl" })
            {
                string code = StripComments(ShaderSource(file));
                StringAssert.Contains("PIO_WALL_SIGMA_NARROW", code, file + ": the narrow field ends on the grid border");
                StringAssert.Contains("_PIO_GrowPulse", code, file + ": the growth front");
                Assert.IsTrue(Regex.IsMatch(code, @"\[branch\]\s*if\s*\(\s*scorch\s*>\s*0\.002\s*\)"), file + ": the scorch look in its own branch");
            }
            StringAssert.Contains("PIO_LiquidWallRelief(ht, dB, nB)", StripComments(ShaderSource("LiquidComposite.hlsl")), "the relief ends on the border");
            StringAssert.Contains("PIO_LiquidWallDome(dm, dB, nB, wt)", StripComments(ShaderSource("LiquidComposite.hlsl")), "so does the dome");
            StringAssert.Contains("PIO_WALL_SIGMA_WIDE", StripComments(ShaderSource("ElectricComposite.hlsl")), "and the electric wide field");
        }

        [Test]
        public void WaveD2_LiquidCommon_DeclaresTheTraitGlobals()
        {
            string code = StripComments(ShaderSource("LiquidCommon.hlsl"));
            StringAssert.Contains("float _PIO_ScorchOn;", code);
            StringAssert.Contains("float4 _PIO_GrowPulse;", code);
            foreach (string d in new[] { "PIO_SCORCH_FADE", "PIO_WALL_SIGMA_NARROW", "PIO_WALL_SIGMA_WIDE", "PIO_WALL_SIGMA_DOME" })
            {
                Assert.IsTrue(Regex.IsMatch(code, @"#define\s+" + d + @"\s"), d);
            }
            Assert.AreEqual(TerritoryField.ScorchFadeSeconds, ParseDefine(code, "PIO_SCORCH_FADE"), 1e-6f, "same fade as TerritoryField");
        }

        private static float ParseDefine(string code, string name)
        {
            Match m = Regex.Match(code, @"#define\s+" + name + @"\s+([0-9.]+)");
            Assert.IsTrue(m.Success, name);
            return float.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture);
        }

        private static Vector3 ParseFloat3(string code, string name)
        {
            Match m = Regex.Match(code, @"#define\s+" + name + @"\s+float3\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)");
            Assert.IsTrue(m.Success, name);
            return new Vector3(float.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture),
                               float.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture),
                               float.Parse(m.Groups[3].Value, CultureInfo.InvariantCulture));
        }

        private static float Luma(Vector3 linear)
        {
            Color s = new Color(Mathf.Clamp01(linear.x), Mathf.Clamp01(linear.y), Mathf.Clamp01(linear.z)).gamma;
            return 255f * (0.299f * s.r + 0.587f * s.g + 0.114f * s.b);
        }

        [Test]
        public void WaveD2_OverlayShaders_DrawTheTraitShapes_BelowWhite()
        {
            var files = new Dictionary<string, string>
            {
                { "Overlay.hlsl", "PIO_OverlayTrait" }, { "FireOverlay.hlsl", "PIO_FireOverlayTrait" }, { "ElectricOverlay.hlsl", "PIOE_OverlayTrait" },
            };
            foreach (KeyValuePair<string, string> f in files)
            {
                string code = StripComments(ShaderSource(f.Key));
                StringAssert.Contains("if (shape > 15.5)", code, f.Key + ": dispatches the trait shapes first");
                Assert.AreEqual(2, Count(code, @"\b" + f.Value + @"\s*\("), f.Key + ": defines and calls " + f.Value);
                string body = Block(code, code.IndexOf("float4 " + f.Value, StringComparison.Ordinal));
                foreach (string s in new[] { "16.5", "17.5", "18.5", "19.5", "20.5" }) StringAssert.Contains("shape < " + s, body, f.Key + " shape bound " + s);
                Assert.IsFalse(Regex.IsMatch(body, @"\bpow\s*\([^,]*,\s*2\.0\s*\)"), f.Key + ": no pow(x, 2) (negative bases)");
                Assert.IsFalse(Regex.IsMatch(body, @"\b(ddx|ddy|fwidth)\s*\("), f.Key + ": no derivative inside the shape branches");
            }
            float white = ParseDefine(StripComments(ShaderSource("Overlay.hlsl")), "PIO_OV_WHITE");
            Assert.Less(Luma(new Vector3(white, white, white)), 235f, "liquid trait white");
            Assert.Less(Luma(ParseFloat3(StripComments(ShaderSource("FireOverlay.hlsl")), "PIO_FIRE_TRAIT_GOLD")), 235f, "fire trait gold");
            Assert.Less(Luma(ParseFloat3(StripComments(ShaderSource("ElectricOverlay.hlsl")), "PIOE_TRAIT_CORE")), 235f, "electric trait core");
            Assert.AreEqual(16, (int)OverlayShape.Streak);
            Assert.AreEqual(21, (int)OverlayShape.Shimmer);
            Assert.AreEqual(TraitFxView.ShapeTimer, (int)OverlayShape.Timer);
        }

        // ------------------------------------------------------------------------------------------------------------
        // TraitFxView helpers.

        [Test]
        public void WaveD2_TraitFxView_Helpers()
        {
            Assert.AreEqual(0.6f, TraitFxView.PopScale(0f), 1e-5f);
            Assert.AreEqual(1.08f, TraitFxView.PopScale(0.6f), 1e-5f);
            Assert.AreEqual(1f, TraitFxView.PopScale(1f), 1e-5f);
            Assert.AreEqual(TraitDefaults.KillSpeedBoostPerKill, TraitFxView.PerKill(RuleTraits.Classic), 1e-9);
            Assert.AreEqual(0.2, TraitFxView.PerKill(RuleTraits.Parse("KillSpeedBoost(0.2,0.3)")), 1e-9);
            Assert.AreEqual((float)TraitDefaults.KillShieldDuration, TraitFxView.ShieldDuration(RuleTraits.Classic), 1e-6f);
            Assert.AreEqual(5f, TraitFxView.ShieldDuration(RuleTraits.Parse("KillShield(5,0)")), 1e-6f);
            Assert.AreEqual(1.25, TraitFxView.ReachScale, 1e-9, "BIOME_TRAITS 5: ContactRadius x 1.25");
        }

        [Test]
        public void WaveD2_PackageFilesHaveNoEmDash()
        {
            string root = Application.dataPath;
            var files = new List<string>
            {
                Path.Combine(root, "Scripts", "Runtime", "Render", "TerritoryField.cs"),
                Path.Combine(root, "Scripts", "Runtime", "Actors", "TraitFxView.cs"),
                Path.Combine(root, "Scripts", "Runtime", "Actors", "ActorViews.cs"),
                Path.Combine(root, "Scripts", "Runtime", "Actors", "QuadBatch.cs"),
                Path.Combine(root, "Tests", "EditMode", "Runtime", "WaveD_TraitsFxTests.cs"),
            };
            foreach (string s in new[] { "LiquidCommon.hlsl", "LiquidComposite.hlsl", "FireComposite.hlsl", "ElectricComposite.hlsl",
                                         "Overlay.hlsl", "FireOverlay.hlsl", "ElectricOverlay.hlsl" })
            {
                files.Add(Path.Combine(root, "Resources", "Shaders", s));
            }
            foreach (string f in files)
            {
                Assert.IsTrue(File.Exists(f), f);
                Assert.AreEqual(-1, File.ReadAllText(f).IndexOf((char)0x2014), Path.GetFileName(f) + " contains an em dash");
            }
        }
    }
}
