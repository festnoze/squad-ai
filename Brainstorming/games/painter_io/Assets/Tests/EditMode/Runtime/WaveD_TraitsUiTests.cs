// Owned by traits-ui (wave D-2). EditMode checks of the trait UI (docs/BIOME_TRAITS.md sections 5 and 7.2): names and
// one-line descriptions of all 11 traits in FR and EN (with their parameters), the exact reward toasts, the procedural
// icons, the biome cards and the rules list following BiomeTraitTable.Resolve and the "Règles des biomes" switch, the
// hidden trait matrix writing SaveData.TraitMatrix, the reward chips, the kill toast merge and the results stats items.
// Every test runs with SaveData.MemoryOnly (no PlayerPrefs written).
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Tests
{
    public class WaveD_TraitsUiTests
    {
        private const int Fr = Strings.French;
        private const int En = Strings.English;

        private bool savedMemoryOnly;

        [SetUp]
        public void SetUp()
        {
            savedMemoryOnly = SaveData.MemoryOnly;
            SaveData.MemoryOnly = true;
            SaveData.BiomeRulesOn = true;
            SaveData.ResetTraitMatrix();
        }

        [TearDown]
        public void TearDown()
        {
            SaveData.MemoryOnly = savedMemoryOnly;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Strings.

        [Test]
        public void TraitsUi_EveryTraitHasANameAndADescriptionInBothLanguages()
        {
            Assert.AreEqual(11, TraitDefaults.All.Count, "BIOME_TRAITS 2 + 7: eleven traits");
            foreach (TraitId id in TraitDefaults.All)
            {
                foreach (int lang in new[] { Fr, En })
                {
                    Assert.IsTrue(Strings.Has(TraitText.NameKey(id), lang), id + " name, language " + lang);
                    Assert.IsTrue(Strings.Has(TraitText.DescKey(id), lang), id + " desc, language " + lang);
                    string d = TraitText.Describe(TraitDefaults.Spec(id), lang);
                    Assert.IsFalse(string.IsNullOrWhiteSpace(d), id + " description");
                    Assert.IsFalse(d.Contains("{") || d.Contains("}"), id + " description keeps a placeholder: " + d);
                    Assert.IsFalse(d.IndexOf((char)0x2014) >= 0, id + " em dash");
                    Assert.That(d.Length, Is.LessThanOrEqualTo(52), id + " one short line: " + d);
                }
            }
            foreach (string k in TraitText.VariantKeys)
            {
                Assert.IsTrue(Strings.Has(k, Fr), k);
                Assert.IsTrue(Strings.Has(k, En), k);
            }
            Assert.AreEqual("Règles des biomes", Strings.Get("options.biome_rules", Fr));
            Assert.AreEqual("Règles classiques", Strings.Get("options.classic_rules", Fr));
            Assert.AreEqual("Réinitialiser", Strings.Get("options.reset", Fr));
        }

        [Test]
        public void TraitsUi_DescriptionsTakeTheTraitParameters()
        {
            Assert.AreEqual("Étincelle plus rapide : × 2,1", TraitText.Describe(new TraitSpec(TraitId.SparkSpeed, 2.1), Fr), "Feu");
            Assert.AreEqual("Étincelle plus lente : × 1,5", TraitText.Describe(new TraitSpec(TraitId.SparkSpeed, 1.5), Fr), "Électricité");
            Assert.AreEqual("Faster spark: × 2.1", TraitText.Describe(new TraitSpec(TraitId.SparkSpeed, 2.1), En));
            Assert.AreEqual("+30 % de vitesse sur ton terrain", TraitText.Describe(new TraitSpec(TraitId.Conduction, 1.3), Fr));
            Assert.AreEqual("Tu coupes de plus loin : +40 %", TraitText.Describe(new TraitSpec(TraitId.ArcReach, 1.4), Fr));
            Assert.AreEqual("Ton terrain s’étend toutes les 4 s", TraitText.Describe(new TraitSpec(TraitId.Propagation, 4.0, 1.0), Fr));
            Assert.AreEqual("Un anneau lasso toutes les 10 s", TraitText.Describe(new TraitSpec(TraitId.RingInterval, 10.0), Fr));
            Assert.AreEqual("+10 % de vitesse par élimination (max +30 %)", TraitText.Describe(new TraitSpec(TraitId.KillSpeedBoost, 0.1, 0.3), Fr));
            Assert.AreEqual("+10% speed per elimination (max +30%)", TraitText.Describe(new TraitSpec(TraitId.KillSpeedBoost, 0.1, 0.3), En));
            Assert.AreEqual("Invincible 3 s après une élimination", TraitText.Describe(new TraitSpec(TraitId.KillShield, 3.0), Fr));
            Assert.AreEqual("Invincible 2,5 s après une élimination", TraitText.Describe(new TraitSpec(TraitId.KillShield, 2.5), Fr));
            Assert.AreEqual("Élimine un rival : son terrain est à toi", TraitText.Describe(new TraitSpec(TraitId.KillInheritance, 1.0), Fr));
            Assert.AreEqual("Élimine un rival : 50 % de son terrain", TraitText.Describe(new TraitSpec(TraitId.KillInheritance, 0.5), Fr));
            Assert.AreEqual("Inertie", TraitText.Name(TraitId.Inertia, Fr));
            Assert.AreEqual("Bouclier", TraitText.Name(TraitId.KillShield, Fr));
            Assert.AreEqual("Shield", TraitText.Name(TraitId.KillShield, En));
        }

        [Test]
        public void TraitsUi_RewardToastsAreTheSpecTexts()
        {
            // BIOME_TRAITS 7.2: "Tu as pris le terrain de Safran !", "Vitesse +10 %", "Invincible 3 s".
            Assert.AreEqual("Tu as pris le terrain de Safran !", Strings.FormatIn(Fr, "toast.inherit", "Safran"));
            Assert.AreEqual("Vitesse +10 %", Strings.FormatIn(Fr, "toast.speed", TraitText.Percent(0.1, Fr)));
            Assert.AreEqual("Invincible 3 s", Strings.FormatIn(Fr, "toast.shield", TraitText.Seconds(3.0, Fr)));
            Assert.AreEqual("You took Saffron's land!", Strings.FormatIn(En, "toast.inherit", "Saffron"));
            Assert.AreEqual("Speed +10%", Strings.FormatIn(En, "toast.speed", TraitText.Percent(0.1, En)));
            Assert.AreEqual("Vitesse max : +30 %", Strings.FormatIn(Fr, "toast.speed_max", TraitText.Percent(0.3, Fr)));
            int lang = Strings.Language;
            Assert.AreEqual(Strings.FormatIn(lang, "toast.speed", TraitText.Percent(0.1, lang)), Hud.SpeedToast(0.1, 1.2, 0.3), "the gain of this kill");
            Assert.AreEqual(Strings.FormatIn(lang, "toast.speed_max", TraitText.Percent(0.3, lang)), Hud.SpeedToast(0.1, 1.3, 0.3), "at the cap: the total");
            Assert.AreEqual(Strings.FormatIn(lang, "toast.speed", TraitText.Percent(0.1, lang)), Hud.SpeedToast(0.1, 1.3, double.NaN), "unknown cap");
        }

        // ------------------------------------------------------------------------------------------------------------
        // Icons.

        [Test]
        public void TraitsUi_EveryTraitHasItsOwnVisibleIcon()
        {
            var seen = new HashSet<Sprite>();
            foreach (TraitId id in TraitDefaults.All)
            {
                Assert.IsTrue(TraitIcons.HasOwnShape(id), id + " has its own drawing");
                float c = TraitIcons.Coverage(id);
                Assert.That(c, Is.InRange(0.06f, 0.6f), id + " covers a readable share of the icon");
                Sprite s = TraitIcons.Get(id);
                Assert.IsNotNull(s, id.ToString());
                Assert.AreEqual(TraitIcons.Size, (int)s.rect.width);
                Assert.AreSame(s, TraitIcons.Get(id), "cached");
                Assert.IsTrue(seen.Add(s), id + " distinct sprite");
            }
            Assert.IsNotNull(TraitIcons.Check);
            // A sheet for the visual check (TestResults is outside Assets).
            string dir = Path.Combine(Path.GetDirectoryName(Application.dataPath) ?? ".", "TestResults");
            Directory.CreateDirectory(dir);
            File.WriteAllBytes(Path.Combine(dir, "traits-ui_icons.png"), TraitIcons.RenderSheetPng(96));
        }

        // ------------------------------------------------------------------------------------------------------------
        // Menu.

        [Test]
        public void TraitsUi_MenuCardsAndRulesFollowTheResolvedSetsAndTheMasterSwitch()
        {
            BiomeId saved = BiomeTheme.Current.Id;
            BiomeTheme.SetCurrent(BiomeId.Electric);
            UiRoot ui = UiRoot.Create(null);
            try
            {
                MenuScreen menu = ui.Menu;
                menu.RefreshTraits();
                menu.Tick(1f / 60f);
                for (int b = 0; b < BiomeTheme.Count; b++)
                {
                    var biome = (BiomeId)b;
                    List<TraitSpec> expected = TraitText.Enabled(BiomeTraitTable.Resolve(biome));
                    List<TraitSpec> shown = menu.TraitsShown(biome);
                    Assert.AreEqual(Ids(expected), Ids(shown), biome + ": the card shows BiomeTraitTable.Resolve");
                    Assert.That(shown.Count, Is.GreaterThan(0), biome + " has default traits (v1.1 table)");
                    Assert.AreEqual(Mathf.Min(shown.Count, TraitChipRow.MaxChips), menu.ChipsOf(biome).ChipCount, biome + " chips");
                    Assert.AreSame(TraitIcons.Get(shown[0].Id), menu.ChipsOf(biome).IconAt(0));
                }
                List<TraitSpec> elec = menu.TraitsShown(BiomeId.Electric);
                Assert.AreEqual(elec.Count, menu.Rules.VisibleRows, "one row per trait of the selected biome");
                Assert.IsNull(menu.Rules.LineText);
                Assert.AreEqual(TraitText.Name(elec[0].Id) + "|" + TraitText.Describe(elec[0]), menu.Rules.RowText(0), "icon, name and description");

                // A new selection redraws the list.
                BiomeTheme.SetCurrent(BiomeId.Liquid);
                menu.Tick(1f / 60f);
                Assert.AreEqual(menu.TraitsShown(BiomeId.Liquid).Count, menu.Rules.VisibleRows);

                // "Règles classiques": no chip, one line.
                SaveData.BiomeRulesOn = false;
                menu.RefreshTraits();
                Assert.IsTrue(menu.ClassicRulesShown);
                for (int b = 0; b < BiomeTheme.Count; b++) Assert.AreEqual(0, menu.ChipsOf((BiomeId)b).ChipCount);
                Assert.AreEqual(0, menu.Rules.VisibleRows);
                Assert.AreEqual(Strings.Get("menu.rules_classic"), menu.Rules.LineText);
                SaveData.BiomeRulesOn = true;
                menu.RefreshTraits();
                Assert.IsFalse(menu.ClassicRulesShown);
                Assert.AreEqual(menu.TraitsShown(BiomeId.Liquid).Count, menu.Rules.VisibleRows);

                // Every trait on one biome (custom matrix): compact list and a "+N" chip, nothing lost.
                foreach (TraitId id in TraitDefaults.All) BiomeTraitTable.SetAssigned(id, BiomeId.Liquid, true);
                menu.RefreshTraits();
                Assert.AreEqual(11, menu.TraitsShown(BiomeId.Liquid).Count);
                Assert.AreEqual(11, menu.Rules.VisibleRows);
                StringAssert.EndsWith("|", menu.Rules.RowText(0), "compact: names only");
                Assert.AreEqual(TraitChipRow.MaxChips, menu.ChipsOf(BiomeId.Liquid).ChipCount);
                Assert.AreEqual(Strings.Format("menu.rules_more", "7"), menu.ChipsOf(BiomeId.Liquid).MoreText);
            }
            finally
            {
                Object.DestroyImmediate(ui.gameObject);
                BiomeTheme.SetCurrent(saved);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Options: the trait matrix.

        [Test]
        public void TraitsUi_MatrixHasOneRowPerTraitAndWritesTheSavedMatrix()
        {
            UiRoot ui = UiRoot.Create(null);
            try
            {
                TraitMatrixPanel m = ui.Settings.Matrix;
                Assert.IsNotNull(m);
                Assert.AreEqual(TraitDefaults.All.Count, m.RowCount, "one row per trait");
                ui.Settings.SetMatrixOpen(true);
                Assert.IsTrue(m.IsOpen);
                foreach (TraitId id in TraitDefaults.All)
                {
                    for (int b = 0; b < BiomeTheme.Count; b++)
                    {
                        Assert.AreEqual(BiomeTraitTable.IsDefault(id, (BiomeId)b), m.IsChecked(id, (BiomeId)b), id + " / " + (BiomeId)b + " default");
                        Assert.IsFalse(m.IsMarkedModified(id, (BiomeId)b));
                    }
                }
                Assert.IsFalse(SaveData.TuningModified);

                // Move KillShield from Liquide to Feu.
                m.Toggle(TraitId.KillShield, BiomeId.Fire);
                m.Toggle(TraitId.KillShield, BiomeId.Liquid);
                Assert.IsTrue(m.IsChecked(TraitId.KillShield, BiomeId.Fire));
                Assert.IsFalse(m.IsChecked(TraitId.KillShield, BiomeId.Liquid));
                Assert.IsTrue(m.IsMarkedModified(TraitId.KillShield, BiomeId.Fire));
                Assert.IsTrue(m.IsMarkedModified(TraitId.KillShield, BiomeId.Liquid));
                Assert.AreEqual("KillShield=F", SaveData.TraitMatrix);
                Assert.IsTrue(SaveData.TuningModified, "a modified matrix is a test setting");
                Assert.IsTrue(BiomeTraitTable.Resolve(BiomeId.Fire).Has(TraitId.KillShield), "the next round uses it");
                Assert.IsFalse(BiomeTraitTable.Resolve(BiomeId.Liquid).Has(TraitId.KillShield));
                ui.Menu.RefreshTraits();
                Assert.IsTrue(Ids(ui.Menu.TraitsShown(BiomeId.Fire)).Contains(TraitId.KillShield), "the Feu card shows it");

                // The master switch off: the matrix waits (note), stays editable.
                SaveData.BiomeRulesOn = false;
                m.Refresh();
                Assert.AreEqual(Strings.Get("options.matrix_classic"), m.NoteText);
                SaveData.BiomeRulesOn = true;
                m.Refresh();
                Assert.AreEqual(Strings.Get("options.matrix_note"), m.NoteText);

                // Réinitialiser.
                SaveData.ResetTraitMatrix();
                m.Refresh();
                Assert.AreEqual("", SaveData.TraitMatrix);
                Assert.IsTrue(m.IsChecked(TraitId.KillShield, BiomeId.Liquid));
                Assert.IsFalse(m.IsMarkedModified(TraitId.KillShield, BiomeId.Fire));
                ui.Settings.SetMatrixOpen(false);
                Assert.IsFalse(m.IsOpen);
            }
            finally
            {
                Object.DestroyImmediate(ui.gameObject);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // HUD and results.

        [Test]
        public void TraitsUi_KillRewardsMergeIntoTheKillToastAndFeedTheTally()
        {
            UiRoot ui = UiRoot.Create(null);
            GameSession s = GameSession.CreateRound(12345UL, false);
            try
            {
                Hud hud = ui.Hud;
                hud.Bind(s);
                int h = s.HumanIndex;
                Assert.AreEqual(0, h);
                int victim = 2;
                string name = Strings.PlayerName(victim, h);
                hud.OnSimEvent(s, new SimEvent { Type = SimEventType.Eliminated, Player = victim, Other = h, Cause = EliminationCause.Spark, Time = 10.0 }, false);
                Assert.AreEqual(Strings.Format("toast.spark_kill", name), hud.CurrentToast);
                hud.OnSimEvent(s, new SimEvent { Type = SimEventType.TerritoryInherited, Player = h, Other = victim, Time = 10.0, Cells = new[] { 1, 2, 3 } }, false);
                Assert.AreEqual(Strings.Format("toast.inherit", name), hud.CurrentToast, "the land reward replaces the kill toast");
                Assert.IsNull(hud.CurrentToastSub);
                hud.OnSimEvent(s, new SimEvent { Type = SimEventType.SpeedBoosted, Player = h, Other = victim, Time = 10.0, Value = 1.1 }, false);
                hud.OnSimEvent(s, new SimEvent { Type = SimEventType.ShieldStarted, Player = h, Other = victim, Time = 10.0, Value = 13.0 }, false);
                string speed = Strings.Format("toast.speed", TraitText.Percent(0.1, Strings.Language));
                string shield = Strings.Format("toast.shield", TraitText.Seconds(3.0, Strings.Language));
                Assert.AreEqual(speed + " · " + shield, hud.CurrentToastSub, "speed and shield join the second line");
                Assert.AreEqual(0, hud.QueuedToasts, "one kill, one pill");

                RewardTally t = hud.Rewards;
                Assert.AreEqual(1, t.Inherited);
                Assert.AreEqual(3, t.InheritedCells);
                Assert.AreEqual(1.1, t.SpeedMultiplier, 1e-9);
                Assert.AreEqual(1, t.Shields);

                // A shield that puts out the human's spark: the next chased return is not "saved by a hair".
                hud.OnSimEvent(s, new SimEvent { Type = SimEventType.ShieldStarted, Player = h, Other = 3, Time = 20.0, Value = 23.0, Chased = true }, false);
                hud.OnSimEvent(s, new SimEvent { Type = SimEventType.Return, Player = h, Time = 21.0, Chased = true, Margin = 0.0, Cells = new int[0] }, false);
                Assert.IsTrue(t.LastChasedReturnQuenched);
                Assert.AreEqual(2, t.Shields);

                // Rewards of bots are not the human's.
                hud.OnSimEvent(s, new SimEvent { Type = SimEventType.SpeedBoosted, Player = 1, Other = 3, Time = 30.0, Value = 1.3 }, false);
                Assert.AreEqual(1.1, t.SpeedMultiplier, 1e-9);

                hud.Bind(s);
                Assert.IsFalse(hud.Rewards.Any, "a new session starts from zero");
            }
            finally
            {
                s.Close();
                Object.DestroyImmediate(ui.gameObject);
            }
        }

        [Test]
        public void TraitsUi_ResultsStatsLineGainsTheRewardsOnlyWhenEarned()
        {
            var o = new HumanOutcome { Captures = 7, CutsMade = 2, Kills = 1, PocketsMade = 1, SurvivedSeconds = 72.4 };
            const string basic = "7 captures · 2 coupes · 1 élimination · 1 poche · 1:12";
            Assert.AreEqual(basic, ResultsScreen.StatsLine(o, null, Fr), "15.5 unchanged");
            Assert.AreEqual(basic, ResultsScreen.StatsLine(o, new RewardTally(), Fr), "no reward, no change");
            var t = new RewardTally { Inherited = 1, SpeedMultiplier = 1.2, Shields = 2 };
            Assert.AreEqual(basic + "\n1 terrain pris · vitesse +20 % · 2 boucliers", ResultsScreen.StatsLine(o, t, Fr), "rewards on their own line");
            Assert.AreEqual("1 land taken · speed +20% · 2 shields", t.StatsItems(En));
        }

        [Test]
        public void TraitsUi_RewardChipsShowTheSpeedLevelAndTheShieldTime()
        {
            var go = new GameObject("ChipsCanvas", typeof(RectTransform));
            try
            {
                go.AddComponent<Canvas>();
                var chips = new RewardChips((RectTransform)go.transform, new Vector2(170f, -213f));
                Color human = Palette.ColorOf(0);
                Assert.IsFalse(chips.SpeedVisible);
                Assert.IsFalse(chips.ShieldVisible);
                for (int k = 0; k < 20; k++) chips.Tick(1f / 60f, 1.2, 0.1, 0.3, 2.1, 3.0, human);
                Assert.IsTrue(chips.SpeedVisible);
                Assert.IsTrue(chips.ShieldVisible);
                Assert.AreEqual(2, chips.PipsLit);
                Assert.AreEqual(3, chips.PipsDrawn, "one pip per level up to the cap");
                Assert.AreEqual(Strings.Format("hud.speed", TraitText.Percent(0.2, Strings.Language)), chips.SpeedText);
                Assert.AreEqual(0.7f, chips.ShieldFill, 1e-4f);
                Assert.AreEqual(Strings.Format("hud.seconds", Strings.Decimal(2.1, 1)), chips.ShieldText);
                for (int k = 0; k < 20; k++) chips.Tick(1f / 60f, 1.0, 0.1, 0.3, 0.0, 3.0, human);
                Assert.IsFalse(chips.SpeedVisible, "no bonus: hidden");
                Assert.IsFalse(chips.ShieldVisible, "no shield: hidden");
                // Raycasts: none of the chips' graphics blocks steering.
                foreach (Graphic g in go.GetComponentsInChildren<Graphic>(true)) Assert.IsFalse(g.raycastTarget, g.name);
            }
            finally
            {
                Object.DestroyImmediate(go);
            }
        }

        [Test]
        public void TraitsUi_TallToastWithARewardLineStillAvoidsTheBoard()
        {
            foreach (float sw in new[] { 600f, 966f, 1080f, 1440f, 3413f })
            {
                Rect board = Hud.BoardRect(sw);
                for (float tw = 300f; tw <= 2400f; tw += 100f)
                {
                    Hud.ToastPlacement p = Hud.ToastLayout(sw, tw, true, float.NaN, float.NaN, Hud.ToastSubHeight);
                    Assert.IsFalse(p.Bounds.Overlaps(board), "safe " + sw + " toast " + tw);
                    float baseHeight = p.Wrap ? Hud.ToastWrapHeight : Hud.ToastHeight;
                    Assert.AreEqual(baseHeight + Hud.ToastSubHeight, p.Size.y, 1e-3f);
                    Hud.ToastPlacement q = Hud.ToastLayout(sw, tw, true, float.NaN, float.NaN);
                    Assert.AreEqual(baseHeight, q.Size.y, 1e-3f, "without a reward line: unchanged");
                }
            }
        }

        // ------------------------------------------------------------------------------------------------------------

        private static List<TraitId> Ids(List<TraitSpec> specs)
        {
            var ids = new List<TraitId>();
            foreach (TraitSpec s in specs) ids.Add(s.Id);
            return ids;
        }
    }
}
