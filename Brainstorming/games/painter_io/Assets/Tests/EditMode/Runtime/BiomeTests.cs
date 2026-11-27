// Owned by BI (wave B-2). EditMode checks of the biome infrastructure (contract 25.1, 25.2): the three themes carry the
// contract values, BiomeTheme.Current / Get / Changed / Parse, the liquid shader fallback, Palette following the biome,
// the Strings names, the -biome command line, the per-biome FillDuration of the fill wave and the _PIO_RevealTime data,
// the live shader re-binding of the bead and overlay batches and the BiomeFx host. Every test leaves the Liquid biome
// current. No test writes PlayerPrefs.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;
using Object = UnityEngine.Object;

namespace PainterIO.Tests
{
    public class BiomeTests
    {
        private const float Frame = 1f / 60f;

        [TearDown]
        public void TearDown()
        {
            BiomeTheme.SetCurrent(BiomeId.Liquid);
        }

        private static Color Hex(string hex)
        {
            Assert.IsTrue(ColorUtility.TryParseHtmlString(hex, out Color c), hex);
            return c;
        }

        private static void AssertColor(string hex, Color actual, string what)
        {
            Color32 e = Hex(hex), a = actual;
            Assert.AreEqual(e.r, a.r, what + " r");
            Assert.AreEqual(e.g, a.g, what + " g");
            Assert.AreEqual(e.b, a.b, what + " b");
        }

        [Test]
        public void Biome_ThemesCarryTheContractValues()
        {
            BiomeTheme liquid = BiomeTheme.Get(BiomeId.Liquid);
            BiomeTheme fire = BiomeTheme.Get(BiomeId.Fire);
            BiomeTheme elec = BiomeTheme.Get(BiomeId.Electric);
            Assert.AreEqual(BiomeId.Liquid, liquid.Id);
            Assert.AreEqual(BiomeId.Fire, fire.Id);
            Assert.AreEqual(BiomeId.Electric, elec.Id);
            Assert.AreEqual("biome.liquid", liquid.NameKey);
            Assert.AreEqual("biome.fire", fire.NameKey);
            Assert.AreEqual("biome.electric", elec.NameKey);
            Assert.AreEqual("LiquidComposite", liquid.CompositeShader);
            Assert.AreEqual("Bead", liquid.BeadShader);
            Assert.AreEqual("Overlay", liquid.OverlayShader);
            Assert.AreEqual("FireComposite", fire.CompositeShader);
            Assert.AreEqual("FireBead", fire.BeadShader);
            Assert.AreEqual("FireOverlay", fire.OverlayShader);
            Assert.AreEqual("ElectricComposite", elec.CompositeShader);
            Assert.AreEqual("ElectricBead", elec.BeadShader);
            Assert.AreEqual("ElectricOverlay", elec.OverlayShader);
            Assert.AreEqual(0.35f, liquid.FillDuration, 1e-6f);
            Assert.AreEqual(0.60f, fire.FillDuration, 1e-6f);
            Assert.AreEqual(0.25f, elec.FillDuration, 1e-6f);
            Assert.IsFalse(liquid.BloomOnHigh);
            Assert.IsTrue(fire.BloomOnHigh);
            Assert.IsTrue(elec.BloomOnHigh);
            foreach (BiomeTheme t in new[] { liquid, fire, elec }) Assert.That(t.BloomThreshold, Is.GreaterThanOrEqualTo(1.1f), "12.1 threshold");

            // Liquid = the palette of 11.3.
            string[] liquidColors = { "#F2674F", "#22C4B6", "#F5B731", "#8E6CEF" };
            string[] fireColors = { "#FF5A2A", "#22E0B8", "#FFC21F", "#B472FF" };
            string[] elecColors = { "#FF4D6D", "#2EF2FF", "#FFE84D", "#A974FF" };
            for (int i = 0; i < 4; i++)
            {
                AssertColor(liquidColors[i], liquid.PlayerColors[i], "liquid " + i);
                AssertColor(fireColors[i], fire.PlayerColors[i], "fire " + i);
                AssertColor(elecColors[i], elec.PlayerColors[i], "electric " + i);
            }
            AssertColor("#FFD08A", fire.SecondaryColors[0], "fire hot core");
            AssertColor("#1E2A4D", liquid.Ground, "liquid ground");
            // Border neon (docs/border_neon.json): one flat light grey outside the arena in every biome.
            AssertColor("#B4B9C1", liquid.OutsideArena, "liquid outside");
            AssertColor("#1A1412", fire.Ground, "fire ground");
            AssertColor("#B4B9C1", fire.OutsideArena, "fire outside");
            AssertColor("#0B0F1E", elec.Ground, "electric ground");
            AssertColor("#B4B9C1", elec.OutsideArena, "electric outside");
            AssertColor("#F3EEE8", liquid.UiAccent, "liquid HUD accent = the UI light (HUD unchanged)");

            // Readability (25.5): the four player colors of every biome stay clearly distinct.
            foreach (BiomeTheme t in new[] { liquid, fire, elec })
            {
                Assert.AreEqual(4, t.PlayerColors.Length);
                Assert.AreEqual(4, t.SecondaryColors.Length);
                for (int i = 0; i < 4; i++)
                {
                    for (int j = i + 1; j < 4; j++)
                    {
                        Color a = t.PlayerColors[i], b = t.PlayerColors[j];
                        float d = Mathf.Abs(a.r - b.r) + Mathf.Abs(a.g - b.g) + Mathf.Abs(a.b - b.b);
                        Assert.That(d, Is.GreaterThan(0.3f), t.Id + " colors " + i + " and " + j);
                    }
                }
            }
            Assert.AreSame(fire, BiomeTheme.Get(BiomeId.Fire), "themes are cached");
            Assert.AreSame(liquid, BiomeTheme.Get((BiomeId)42), "an unknown id gives Liquid");
        }

        [Test]
        public void Biome_ParseClampAndCommandNames()
        {
            Assert.AreEqual(BiomeId.Liquid, BiomeTheme.Parse("liquid"));
            Assert.AreEqual(BiomeId.Fire, BiomeTheme.Parse("FIRE"));
            Assert.AreEqual(BiomeId.Electric, BiomeTheme.Parse(" electric "));
            Assert.AreEqual(BiomeId.Fire, BiomeTheme.Parse("1"));
            Assert.AreEqual(BiomeId.Electric, BiomeTheme.Parse("2"));
            Assert.AreEqual(BiomeId.Fire, BiomeTheme.Parse("feu"), "French alias");
            Assert.IsNull(BiomeTheme.Parse("lava"));
            Assert.IsNull(BiomeTheme.Parse(null));
            Assert.IsNull(BiomeTheme.Parse(""));
            Assert.AreEqual(BiomeId.Liquid, BiomeTheme.Clamp(-1));
            Assert.AreEqual(BiomeId.Liquid, BiomeTheme.Clamp(3));
            Assert.AreEqual(BiomeId.Electric, BiomeTheme.Clamp(2));
            Assert.AreEqual("liquid", BiomeTheme.CommandNameOf(BiomeId.Liquid));
            Assert.AreEqual("fire", BiomeTheme.Get(BiomeId.Fire).CommandName);
            Assert.AreEqual("electric", BiomeTheme.CommandNameOf(BiomeId.Electric));
            Assert.AreEqual(3, BiomeTheme.Count);
            Assert.That(SaveData.Biome, Is.InRange(0, BiomeTheme.Count - 1), "SaveData.Biome is a valid biome");
        }

        [Test]
        public void Biome_LaunchArgsReadTheBiomeFlag()
        {
            try
            {
                LaunchArgs.Reload(new[] { "PainterIO.exe", "-devshot", "x", "-biome", "electric" });
                Assert.AreEqual(BiomeId.Electric, LaunchArgs.Biome);
                LaunchArgs.Reload(new[] { "PainterIO.exe", "-biome", "nope" });
                Assert.IsNull(LaunchArgs.Biome, "an unknown biome is ignored");
                LaunchArgs.Reload(new[] { "PainterIO.exe" });
                Assert.IsNull(LaunchArgs.Biome);
            }
            finally
            {
                LaunchArgs.Reload();
            }
        }

        [Test]
        public void Biome_SetCurrentRaisesChangedOnceAndPaletteFollows()
        {
            var seen = new List<BiomeId>();
            Action<BiomeTheme> handler = t => seen.Add(t.Id);
            BiomeTheme.Changed += handler;
            try
            {
                BiomeTheme.SetCurrent(BiomeId.Liquid);
                seen.Clear();
                BiomeTheme.SetCurrent(BiomeId.Fire);
                BiomeTheme.SetCurrent(BiomeId.Fire);
                CollectionAssert.AreEqual(new[] { BiomeId.Fire }, seen, "raised once per actual change");
                Assert.AreEqual(BiomeId.Fire, BiomeTheme.Current.Id);
                BiomeTheme fire = BiomeTheme.Get(BiomeId.Fire);
                for (int p = 0; p < 4; p++)
                {
                    Assert.AreEqual(fire.PlayerColors[Palette.ColorIndexOf(p)], Palette.ColorOf(p), "Palette.ColorOf follows the biome");
                    Assert.AreEqual(fire.SecondaryColors[Palette.ColorIndexOf(p)], Palette.SecondaryColorOf(p));
                }
                Assert.AreEqual(fire.PlayerColors[2], Palette.ColorAt(2));
                Assert.AreEqual(fire.Ground, Palette.GroundColor);
                Assert.AreEqual(fire.OutsideArena, Palette.OutsideColor);
                BiomeTheme.SetCurrent(BiomeId.Fire, true);
                Assert.AreEqual(2, seen.Count, "force raises again");
                BiomeTheme.SetCurrent(BiomeId.Liquid);
                Assert.AreEqual(Palette.Colors[Palette.ColorIndexOf(0)], Palette.ColorOf(0), "Liquid gives the 11.3 palette back");
            }
            finally
            {
                BiomeTheme.Changed -= handler;
            }
        }

        [Test]
        public void Biome_MissingShadersFallBackToTheLiquidOnes()
        {
            foreach (BiomeId id in new[] { BiomeId.Liquid, BiomeId.Fire, BiomeId.Electric })
            {
                BiomeTheme t = BiomeTheme.Get(id);
                AssertResolved(t.ResolveComposite(), t.CompositeShader, BiomeTheme.LiquidCompositeShader);
                AssertResolved(t.ResolveBead(), t.BeadShader, BiomeTheme.LiquidBeadShader);
                AssertResolved(t.ResolveOverlay(), t.OverlayShader, BiomeTheme.LiquidOverlayShader);
            }
            Shader fallback = BiomeTheme.LoadShader("NoSuchShader_PIO", BiomeTheme.LiquidBeadShader);
            Assert.IsNotNull(fallback);
            StringAssert.EndsWith("/Bead", fallback.name);
            Assert.IsFalse(BiomeTheme.HasShader("NoSuchShader_PIO"));
            Assert.IsTrue(BiomeTheme.HasShader(BiomeTheme.LiquidCompositeShader));
        }

        private static void AssertResolved(Shader s, string wanted, string liquid)
        {
            Assert.IsNotNull(s, wanted);
            Assert.IsTrue(s.isSupported, wanted);
            string expected = BiomeTheme.HasShader(wanted) ? wanted : liquid;
            StringAssert.EndsWith("/" + expected, s.name, wanted + " resolves to " + expected);
        }

        [Test]
        public void Biome_StringsNameEveryBiome()
        {
            Assert.AreEqual("Liquide", Strings.Get("biome.liquid", Strings.French));
            Assert.AreEqual("Feu", Strings.Get("biome.fire", Strings.French));
            Assert.AreEqual("Électricité", Strings.Get("biome.electric", Strings.French));
            Assert.AreEqual("Liquid", Strings.Get("biome.liquid", Strings.English));
            Assert.AreEqual("Fire", Strings.Get("biome.fire", Strings.English));
            Assert.AreEqual("Electricity", Strings.Get("biome.electric", Strings.English));
            foreach (BiomeId id in new[] { BiomeId.Liquid, BiomeId.Fire, BiomeId.Electric })
            {
                string key = BiomeTheme.Get(id).NameKey;
                Assert.IsTrue(Strings.Has(key, Strings.French) && Strings.Has(key, Strings.English), key);
            }
            Assert.IsTrue(Strings.Has("menu.biome", Strings.French) && Strings.Has("menu.biome", Strings.English));
            // Contract 24 presentation lines (v1.4).
            Assert.AreEqual("On a coupé ton trait ! Rentre avant l’étincelle pour rester en vie.", Strings.Get("tut.cut", Strings.French));
            Assert.AreEqual("Your thread was cut! Get home before the spark to stay alive.", Strings.Get("tut.cut", Strings.English));
            Assert.AreEqual("Rentré 0,4 s avant l’étincelle : boucle perdue.", Strings.FormatIn(Strings.French, "results.saved", Strings.Decimal(0.4, 1, Strings.French)));
            Assert.AreEqual("Home 0.4 s ahead of the spark: loop lost.", Strings.FormatIn(Strings.English, "results.saved", Strings.Decimal(0.4, 1, Strings.English)));
            Assert.AreEqual("Sauvé de justesse : boucle perdue.", Strings.Get("results.saved_close", Strings.French));
            Assert.AreEqual("Saved by a hair: loop lost.", Strings.Get("results.saved_close", Strings.English));
        }

        // ------------------------------------------------------------------------------------------------------------
        // TerritoryField: per-biome fill duration and reveal times.

        // Player 0 leaves its start disc to the north, draws a 5 x 5 u square and comes back unchased; the others orbit home.
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

        [TestCase(BiomeId.Liquid)]
        [TestCase(BiomeId.Fire)]
        [TestCase(BiomeId.Electric)]
        public void Biome_FillLastsTheBiomeFillDurationAndStampsRevealTimes(BiomeId biome)
        {
            BiomeTheme.SetCurrent(biome);
            float fillDuration = BiomeTheme.Get(biome).FillDuration;
            Assert.AreEqual(fillDuration, TerritoryField.CurrentFillDuration, 1e-6f);
            var field = new TerritoryField(Resources.Load<Shader>(LiquidRenderer.BlurShaderPath));
            GameSession session = CaptureSession();
            var events = new List<SimEvent>();
            try
            {
                field.Bind(session);
                session.EventRaised += field.OnSimEvent;
                session.EventRaised += e => events.Add(e);
                Assert.IsNotNull(field.RevealTexture, "_PIO_RevealTime exists");
                Assert.AreEqual(field.Size, field.RevealTexture.width);
                int homeCell = CellAt(session.Sim.Grid, new Vec2d(-16, -16));
                Assert.AreEqual(TerritoryField.RevealNever, field.RevealTimeOf(homeCell), "cells present at bind time");

                SimEvent ret = null;
                for (int guard = 0; ret == null && guard < 600; guard++)
                {
                    session.Advance(Frame);
                    field.Update(Frame);
                    foreach (SimEvent e in events)
                    {
                        if (e.Type == SimEventType.Return && e.Player == 0 && e.Cells != null && e.Cells.Length > 0) ret = e;
                    }
                }
                Assert.IsNotNull(ret, "the unchased return captures cells");
                int frames = 0;
                while (frames++ < 120)
                {
                    bool all = true;
                    foreach (int c in ret.Cells)
                    {
                        if (field.VisualOwner(c) != 1)
                        {
                            all = false;
                            break;
                        }
                    }
                    if (all) break;
                    session.Advance(Frame);
                    field.Update(Frame);
                }
                double seconds = frames * (double)Frame;
                Assert.That(seconds, Is.InRange(fillDuration - 0.05, fillDuration + 0.1), biome + ": the fill lasts the biome's FillDuration");

                // Reveal times: every captured cell was stamped inside [return, return + FillDuration], in distance order.
                OwnerGrid g = session.Sim.Grid;
                float first = float.MaxValue, last = float.MinValue;
                int nearest = -1, farthest = -1;
                double dMin = double.MaxValue, dMax = 0.0;
                foreach (int c in ret.Cells)
                {
                    float r = field.RevealTimeOf(c);
                    Assert.That(r, Is.GreaterThan(TerritoryField.RevealNever + 1f), "captured cell stamped");
                    first = Mathf.Min(first, r);
                    last = Mathf.Max(last, r);
                    double d = Distance(g, c, ret.Point);
                    if (d < dMin) { dMin = d; nearest = c; }
                    if (d > dMax) { dMax = d; farthest = c; }
                }
                Assert.That(last - first, Is.InRange(fillDuration * 0.8f, fillDuration + 0.02f), "the stamps span the fill");
                Assert.That(field.RevealTimeOf(farthest), Is.GreaterThan(field.RevealTimeOf(nearest)), "the far side is revealed last");
                Assert.That(field.RevealNow, Is.GreaterThanOrEqualTo(last - 1e-3f), "_PIO_Now is at or after the last reveal");
                Assert.AreEqual(TerritoryField.RevealNever, field.RevealTimeOf(homeCell), "untouched cells keep -1000");
                Assert.IsTrue(Shader.GetGlobalTexture("_PIO_RevealTime") == field.RevealTexture, "_PIO_RevealTime published");
                Assert.AreEqual(field.RevealNow, Shader.GetGlobalFloat("_PIO_Now"), 1e-3f, "_PIO_Now published");
            }
            finally
            {
                session.Close();
                field.Dispose();
            }
        }

        private static int CellAt(OwnerGrid g, Vec2d p)
        {
            int i = (int)Math.Floor((p.X - g.Origin) / g.CellSize), j = (int)Math.Floor((p.Y - g.Origin) / g.CellSize);
            return j * g.Size + i;
        }

        private static double Distance(OwnerGrid g, int c, Vec2d p)
        {
            double x = g.Origin + (c % g.Size + 0.5) * g.CellSize - p.X, y = g.Origin + (c / g.Size + 0.5) * g.CellSize - p.Y;
            return Math.Sqrt(x * x + y * y);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Views.

        [Test]
        public void Biome_QuadBatchesRebindTheirShaderOfTheirKind()
        {
            var parent = new GameObject("BiomeTestParent");
            Shader bead = Resources.Load<Shader>("Shaders/Bead");
            Shader overlay = Resources.Load<Shader>("Shaders/Overlay");
            Shader other = Resources.Load<Shader>("Shaders/FieldBlob");
            var beads = new QuadBatch("TestBeads", parent.transform, bead, QuadBatch.QueuePearls, 0);
            var overlays = new QuadBatch("TestOverlays", parent.transform, overlay, QuadBatch.QueueOverlays, 0);
            try
            {
                Assert.AreEqual(QuadBatchKind.Bead, beads.Kind);
                Assert.AreEqual(QuadBatchKind.Overlay, overlays.Kind);
                QuadBatch.RebindAll(other, bead);
                Assert.AreSame(other, beads.Material.shader, "bead batches take the bead shader");
                Assert.AreSame(bead, overlays.Material.shader, "overlay batches take the overlay shader");
                Assert.AreEqual(QuadBatch.QueuePearls, beads.Material.renderQueue, "the render queue survives the swap");
                Assert.AreEqual(QuadBatch.QueueOverlays, overlays.Material.renderQueue);
                QuadBatch.RebindAll(bead, overlay);
                Assert.AreSame(bead, beads.Material.shader);
                Assert.AreSame(overlay, overlays.Material.shader);
            }
            finally
            {
                beads.Destroy();
                overlays.Destroy();
                Object.DestroyImmediate(parent);
            }
        }

        [Test]
        public void Biome_FxHostSwapsTheEffectsComponent()
        {
            BiomeTheme.SetCurrent(BiomeId.Liquid);
            var host = (BiomeFxHost)BiomeFx.Create(null);
            try
            {
                Assert.IsInstanceOf<LiquidFx>(host.Active);
                BiomeTheme.SetCurrent(BiomeId.Fire);
                Assert.IsInstanceOf<FireFx>(host.Active);
                Assert.AreEqual(1, host.GetComponents<BiomeFxBehaviour>().Length, "the old component is gone");
                BiomeTheme.SetCurrent(BiomeId.Electric);
                Assert.IsInstanceOf<ElectricFx>(host.Active);
                Assert.AreEqual(BiomeId.Electric, host.Active.Biome);
                Assert.AreEqual(typeof(FireFx), BiomeFx.ComponentTypeOf(BiomeId.Fire));
            }
            finally
            {
                host.Teardown();
                Object.DestroyImmediate(host.gameObject);
            }
        }
    }
}
