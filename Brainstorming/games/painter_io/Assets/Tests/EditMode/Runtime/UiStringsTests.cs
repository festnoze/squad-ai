// Owned by B4. EditMode checks of contract 15.6 (Strings: every key in both tables, the 15.6 keys, decimal comma in French and
// point in English, culture independence) and of the 15.1 uGUI rules on a code-built UiRoot (CanvasScaler 1080 x 1920 with
// screenMatchMode Expand since wave C, GraphicRaycaster, InputSystemUIInputModule, raycastTarget only on Selectables, the
// OFL font). No test writes
// PlayerPrefs: every formatting call passes its language explicitly.
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using System.Threading;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace PainterIO.Tests
{
    public class UiStringsTests
    {
        private const int Fr = Strings.French;
        private const int En = Strings.English;

        [Test]
        public void Strings_EveryKeyExistsInBothTables()
        {
            var missing = new List<string>();
            foreach (string k in Strings.Keys(Fr)) if (!Strings.Has(k, En)) missing.Add("EN lacks " + k);
            foreach (string k in Strings.Keys(En)) if (!Strings.Has(k, Fr)) missing.Add("FR lacks " + k);
            Assert.IsEmpty(missing, string.Join("\n", missing));
            Assert.That(new List<string>(Strings.Keys(Fr)).Count, Is.GreaterThanOrEqualTo(75), "full tables");
        }

        [Test]
        public void Strings_ContractKeysExist()
        {
            foreach (string k in Strings.RequiredKeys)
            {
                Assert.IsTrue(Strings.Has(k, Fr), "FR " + k);
                Assert.IsTrue(Strings.Has(k, En), "EN " + k);
            }
            Assert.AreEqual("Toi", Strings.Get(Palette.HumanNameKey, Fr));
            Assert.AreEqual("You", Strings.Get(Palette.HumanNameKey, En));
            string[] names = { "Corail", "Lagon", "Safran", "Lilas" };
            for (int i = 0; i < 4; i++) Assert.AreEqual(names[i], Strings.Get(Palette.ColorNameKey(i), Fr));
        }

        [Test]
        public void Strings_ValuesAreNonEmptyWithoutEmDashAndWithMatchingPlaceholders()
        {
            var placeholder = new Regex(@"\{(\d+)\}");
            foreach (string k in Strings.Keys(Fr))
            {
                string fr = Strings.Get(k, Fr), en = Strings.Get(k, En);
                Assert.IsFalse(string.IsNullOrWhiteSpace(fr), "FR " + k + " empty");
                Assert.IsFalse(string.IsNullOrWhiteSpace(en), "EN " + k + " empty");
                Assert.IsFalse(fr.IndexOf((char)0x2014) >= 0 || en.IndexOf((char)0x2014) >= 0, k + " contains an em dash");
                var a = new SortedSet<string>();
                var b = new SortedSet<string>();
                foreach (Match m in placeholder.Matches(fr)) a.Add(m.Groups[1].Value);
                foreach (Match m in placeholder.Matches(en)) b.Add(m.Groups[1].Value);
                Assert.IsTrue(a.SetEquals(b), k + ": FR and EN use different placeholders");
            }
        }

        [Test]
        public void Strings_ExactContractAndBriefTexts()
        {
            Assert.AreEqual("Sors de ta couleur et reviens pour agrandir ton terrain.", Strings.Get("tut.exit", Fr));
            Assert.AreEqual("On a coupé ton trait ! Rentre avant l’étincelle pour rester en vie.", Strings.Get("tut.cut", Fr), "contract 24 (v1.4)");
            Assert.AreEqual("Your thread was cut! Get home before the spark to stay alive.", Strings.Get("tut.cut", En));
            Assert.AreEqual("Lasso ! Recroise ton fil pour enfermer une poche, puis rentre.", Strings.Get("tut.lasso", Fr));
            Assert.AreEqual("Glisse ton doigt pour diriger", Strings.Get("hint.steer", Fr));
            Assert.AreEqual("Swipe to steer", Strings.Get("hint.steer", En));
            Assert.AreEqual("JOUER", Strings.Get("menu.play", Fr));
            Assert.AreEqual("Réglages de test", Strings.Get("options.test_settings", Fr));
            Assert.AreEqual("Quitter ?", Strings.Get("quit.title", Fr));
            Assert.AreEqual("Sauvé de justesse : boucle perdue.", Strings.Get("results.saved_close", Fr), "contract 24 (v1.4)");
            Assert.AreEqual("Saved by a hair: loop lost.", Strings.Get("results.saved_close", En));
            Assert.AreEqual("Lagon a été éliminé", Strings.FormatIn(Fr, "toast.eliminated", "Lagon"));
            Assert.AreEqual("Tu as coupé Safran !", Strings.FormatIn(Fr, "toast.cut", "Safran"));
            Assert.AreEqual("Ton étincelle a eu Safran !", Strings.FormatIn(Fr, "toast.spark_kill", "Safran"));
            Assert.AreEqual("Rentré 0,4 s avant l’étincelle : boucle perdue.", Strings.FormatIn(Fr, "results.saved", Strings.Decimal(0.43, 1, Fr)));
            Assert.AreEqual("Home 0.4 s ahead of the spark: loop lost.", Strings.FormatIn(En, "results.saved", Strings.Decimal(0.43, 1, En)));
            Assert.AreEqual("Lagon t’a coupé : rattrapé à 2,3 m de chez toi.",
                            Strings.FormatIn(Fr, "results.caught", "Lagon", Strings.Decimal(2.31, 1, Fr)));
            Assert.AreEqual("Meilleur : 34 % · 5 victoires",
                            Strings.FormatIn(Fr, "menu.best", Strings.Area(34.2, Fr), Strings.Count("menu.wins", 5, Fr)));
            Assert.AreEqual("7 captures · 2 coupes · 1 élimination · 1 poche · 1:12",
                            Strings.FormatIn(Fr, "results.stats", Strings.Count("results.stat.captures", 7, Fr),
                                             Strings.Count("results.stat.cuts", 2, Fr), Strings.Count("results.stat.kills", 1, Fr),
                                             Strings.Count("results.stat.pockets", 1, Fr), Strings.Duration(72.4)));
        }

        [Test]
        public void Format_FrenchCommaEnglishPoint()
        {
            Assert.AreEqual("0,4", Strings.Decimal(0.43, 1, Fr));
            Assert.AreEqual("0.4", Strings.Decimal(0.43, 1, En));
            Assert.AreEqual("2,3", Strings.Decimal(2.25, 1, Fr), "midpoint rounds away from zero");
            Assert.AreEqual("0,0", Strings.Decimal(-0.01, 1, Fr), "no negative zero");
            Assert.AreEqual("3,4 %", Strings.Area(3.44, Fr));
            Assert.AreEqual("3.4%", Strings.Area(3.44, En));
            Assert.AreEqual("28 %", Strings.Area(28.4, Fr), "whole numbers from 10 %");
            Assert.AreEqual("28%", Strings.Area(28.4, En));
            Assert.AreEqual("9,9 %", Strings.Area(9.94, Fr));
            Assert.AreEqual("10 %", Strings.Area(9.96, Fr), "9.96 rounds to 10.0, shown whole");
            Assert.AreEqual("0,0 %", Strings.Area(0.0, Fr));
            Assert.AreEqual("+2,1 %", Strings.Gain(2.12, Fr));
            Assert.AreEqual("+2.1%", Strings.Gain(2.12, En));
            Assert.AreEqual("+12 %", Strings.Gain(12.3, Fr));
        }

        [Test]
        public void Format_DoesNotDependOnTheThreadCulture()
        {
            CultureInfo saved = Thread.CurrentThread.CurrentCulture;
            try
            {
                foreach (string name in new[] { "fr-FR", "de-DE", "en-US" })
                {
                    Thread.CurrentThread.CurrentCulture = new CultureInfo(name);
                    Assert.AreEqual("3.4%", Strings.Area(3.44, En), name);
                    Assert.AreEqual("3,4 %", Strings.Area(3.44, Fr), name);
                    Assert.AreEqual("01:30", Strings.Clock(90.0), name);
                }
            }
            finally
            {
                Thread.CurrentThread.CurrentCulture = saved;
            }
        }

        [Test]
        public void Format_ClockDurationCountsAndRanks()
        {
            Assert.AreEqual("01:30", Strings.Clock(90.0));
            Assert.AreEqual("01:30", Strings.Clock(89.2), "seconds rounded up");
            Assert.AreEqual("00:37", Strings.Clock(36.01));
            Assert.AreEqual("00:00", Strings.Clock(0.0));
            Assert.AreEqual("00:00", Strings.Clock(-3.0));
            Assert.AreEqual("02:00", Strings.Clock(120.0));
            Assert.AreEqual("1:12", Strings.Duration(72.9));
            Assert.AreEqual("0:05", Strings.Duration(5.0));

            Assert.AreEqual("0 capture", Strings.Count("results.stat.captures", 0, Fr), "French singular for 0");
            Assert.AreEqual("0 captures", Strings.Count("results.stat.captures", 0, En));
            Assert.AreEqual("1 cut", Strings.Count("results.stat.cuts", 1, En));
            Assert.AreEqual("3 éliminations", Strings.Count("results.stat.kills", 3, Fr));

            Assert.AreEqual("1er", Strings.Rank(1, false, Fr));
            Assert.AreEqual("2e", Strings.Rank(2, false, Fr));
            Assert.AreEqual("4e", Strings.Rank(4, false, Fr));
            Assert.AreEqual("Ex æquo 1er", Strings.Rank(1, true, Fr));
            Assert.AreEqual("Ex æquo 2e", Strings.Rank(2, true, Fr));
            Assert.AreEqual("1st", Strings.Rank(1, false, En));
            Assert.AreEqual("2nd", Strings.Rank(2, false, En));
            Assert.AreEqual("3rd", Strings.Rank(3, false, En));
            Assert.AreEqual("4th", Strings.Rank(4, false, En));
            Assert.AreEqual("Tied 1st", Strings.Rank(1, true, En));
            Assert.AreEqual("5e", Strings.Rank(5, false, Fr), "generic fallback");
        }

        [Test]
        public void Results_CauseAndWhyLines()
        {
            int lang = Strings.Language;
            string attacker = Strings.PlayerName(2, -1);

            ResultsScreen.BuildLines(new HumanOutcome { Cause = EliminationCause.Spark, Attacker = 2, CaughtDistance = 2.31 },
                                     out string cause, out string why);
            Assert.AreEqual(Strings.FormatIn(lang, "results.caught", attacker, Strings.Decimal(2.31, 1, lang)), cause);
            StringAssert.Contains(attacker, cause);
            Assert.IsNull(why);

            ResultsScreen.BuildLines(new HumanOutcome { Cause = EliminationCause.TerritoryLost, Attacker = 1, Reason = RoundEndReason.AllEliminated },
                                     out cause, out why);
            Assert.AreEqual(Strings.Get("results.territory_lost", lang), cause);
            Assert.AreEqual(Strings.Get("results.all_eliminated", lang), why);

            ResultsScreen.BuildLines(new HumanOutcome { Reason = RoundEndReason.TimeUp, HadSavedReturn = true, LastSavedMargin = 0.43 },
                                     out cause, out why);
            Assert.AreEqual(Strings.Get("results.time_up", lang), cause);
            Assert.AreEqual(Strings.FormatIn(lang, "results.saved", Strings.Decimal(0.43, 1, lang)), why);

            ResultsScreen.BuildLines(new HumanOutcome { Reason = RoundEndReason.LastSurvivor, HadSavedReturn = true, LastSavedMargin = 0.02 },
                                     out cause, out why);
            Assert.AreEqual(Strings.Get("results.last_survivor", lang), cause);
            Assert.AreEqual(Strings.Get("results.saved_close", lang), why, "below 0.05 s: saved just in time");

            Assert.AreEqual(Strings.Get("results.saved_close", lang), Hud.SavedLine(0.049));
            Assert.AreEqual(Strings.FormatIn(lang, "results.saved", Strings.Decimal(0.05, 1, lang)), Hud.SavedLine(0.05));
        }

        [Test]
        public void UiRoot_FollowsTheUguiRules()
        {
            UiRoot ui = UiRoot.Create(null);
            try
            {
                Assert.IsNotNull(ui);
                Canvas[] canvases = ui.GetComponentsInChildren<Canvas>(true);
                Assert.That(canvases.Length, Is.GreaterThanOrEqualTo(7), "one canvas per screen");
                foreach (Canvas c in canvases)
                {
                    Assert.AreEqual(RenderMode.ScreenSpaceOverlay, c.renderMode, c.name);
                    var scaler = c.GetComponent<CanvasScaler>();
                    Assert.IsNotNull(scaler, c.name + " CanvasScaler");
                    Assert.AreEqual(CanvasScaler.ScaleMode.ScaleWithScreenSize, scaler.uiScaleMode, c.name);
                    Assert.AreEqual(new Vector2(1080f, 1920f), scaler.referenceResolution, c.name);
                    Assert.AreEqual(CanvasScaler.ScreenMatchMode.Expand, scaler.screenMatchMode, c.name + " (wave C: the whole design box stays visible)");
                    Assert.IsNotNull(c.GetComponent<GraphicRaycaster>(), c.name + " GraphicRaycaster");
                    Assert.IsNotNull(c.GetComponent<CanvasGroup>(), c.name + " CanvasGroup");
                    Assert.IsNotNull(c.GetComponentInChildren<SafeArea>(true), c.name + " SafeArea");
                }

                EventSystem es = ui.GetComponentInChildren<EventSystem>(true);
                if (es == null) es = Object.FindAnyObjectByType<EventSystem>();
                Assert.IsNotNull(es, "an EventSystem exists");
                Assert.IsTrue(HasComponentNamed(es.gameObject, "InputSystemUIInputModule"), "InputSystemUIInputModule (by name: the test asmdef does not reference the Input System)");
                Assert.IsNull(es.GetComponent<StandaloneInputModule>(), "never StandaloneInputModule");

                int texts = 0;
                foreach (Graphic g in ui.GetComponentsInChildren<Graphic>(true))
                {
                    if (g.raycastTarget)
                        Assert.IsNotNull(g.GetComponent<Selectable>(), g.name + " is a raycast target without being a Selectable (it would block steering)");
                    if (g is Text t)
                    {
                        texts++;
                        Assert.IsNotNull(t.font, t.name + " has a font");
                        Assert.IsFalse(t.supportRichText, t.name + " rich text off");
                    }
                }
                Assert.That(texts, Is.GreaterThan(40), "code-built texts");
                Assert.IsFalse(UiKit.UsingFallbackFont, "the OFL font loads from Resources/Fonts");
                Assert.AreEqual(UiKit.FontPath.Substring("Fonts/".Length), UiKit.Font.name);

                foreach (Selectable s in ui.GetComponentsInChildren<Selectable>(true))
                    Assert.AreEqual(Navigation.Mode.None, s.navigation.mode, s.name + " navigation off (arrows steer the pawn)");
            }
            finally
            {
                Object.DestroyImmediate(ui.gameObject);
            }
        }

        private static bool HasComponentNamed(GameObject go, string typeName)
        {
            foreach (Component c in go.GetComponents<Component>())
            {
                if (c != null && c.GetType().Name == typeName) return true;
            }
            return false;
        }
    }
}
