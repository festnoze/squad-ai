// Rule v1.7 (docs/CONTRACT.md section 31): countries first, the 15 min cap and the conquest goal, runtime side.
// - SaveData: the round time choices 5 / 10 / 15 min, 15 by default and not a tuning change, a pre-v1.7 value (60 / 90 /
//   120 s) migrated to the default; the settings show minutes;
// - GameSession.RoundConfig gives country rounds 900 s;
// - the HUD goal caption, the m:ss clock, the results lines of the conquest end;
// - the Europe win hook counts every winning end (conquest, last survivor, first at time up);
// - the menu has no "Pays" button any more.
// No test writes PlayerPrefs (SaveData.MemoryOnly) and every LaunchArgs.Reload is undone.
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;
using Object = UnityEngine.Object;

namespace PainterIO.Tests
{
    public class FlowV17Tests
    {
        private const int Fr = Strings.French, En = Strings.English;

        [SetUp]
        public void SetUp()
        {
            SaveData.MemoryOnly = true;
            SaveData.TraitMatrix = "";
            SaveData.ResetTestSettings();
            LaunchArgs.Reload(new[] { "PainterIO.exe" });
        }

        [TearDown]
        public void TearDown()
        {
            LaunchArgs.Reload();
            SaveData.MemoryOnly = false;
        }

        [Test]
        public void V17_RoundTimeIsFifteenMinutesByDefaultAndNotATuningChange()
        {
            Assert.AreEqual(new[] { 300f, 600f, 900f }, SaveData.RoundSecondsChoices);
            Assert.AreEqual(900f, SaveData.DefaultRoundSeconds);
            Assert.AreEqual(900f, SaveData.RoundSeconds);
            Assert.IsFalse(SaveData.TuningModified, "the 15 min default is the reference: wins and stats are recorded");
            Assert.AreEqual(900.0, GameSession.RoundConfig(1UL, false, RuleTraits.Classic).RoundDuration, "country rounds last 900 s");

            SaveData.RoundSeconds = 600f;
            Assert.AreEqual(600f, SaveData.RoundSeconds);
            Assert.IsTrue(SaveData.TuningModified, "10 min is a test setting");
            SaveData.RoundSeconds = 380f;
            Assert.AreEqual(300f, SaveData.RoundSeconds, "snapped to the nearest choice");
            SaveData.ResetTestSettings();
            Assert.AreEqual(900f, SaveData.RoundSeconds);
            Assert.IsFalse(SaveData.TuningModified);
        }

        [Test]
        public void V17_APreV17SavedRoundTimeReadsAsTheDefault()
        {
            foreach (float old in new[] { 60f, 90f, 120f, 0f, float.NaN })
            {
                Assert.AreEqual(SaveData.DefaultRoundSeconds, SaveData.MigrateRoundSeconds(old), "stored " + old);
            }
            Assert.AreEqual(300f, SaveData.MigrateRoundSeconds(300f));
            Assert.AreEqual(600f, SaveData.MigrateRoundSeconds(610f));
            Assert.AreEqual(900f, SaveData.MigrateRoundSeconds(900f));
            Assert.AreEqual(900f, SaveData.MigrateRoundSeconds(3600f));

            // Through PlayerPrefs, as an old install would have it (the key is restored afterwards).
            string key = SaveData.Prefix + "RoundSeconds";
            bool had = PlayerPrefs.HasKey(key);
            float saved = PlayerPrefs.GetFloat(key, 0f);
            try
            {
                SaveData.MemoryOnly = false;
                PlayerPrefs.SetFloat(key, 90f);
                SaveData.ReloadCache();
                Assert.AreEqual(900f, SaveData.RoundSeconds, "an old 90 s save plays 15 min rounds");
                Assert.IsFalse(SaveData.TuningModified);
            }
            finally
            {
                if (had) PlayerPrefs.SetFloat(key, saved);
                else PlayerPrefs.DeleteKey(key);
                SaveData.ReloadCache();
                SaveData.MemoryOnly = true;
            }
        }

        [Test]
        public void V17_SettingsShowMinutesAndTheHudShowsTheGoalAndAnMssClock()
        {
            Assert.AreEqual("15 min", SettingsPanel.RoundValueText(900f, Fr));
            Assert.AreEqual("5 min", SettingsPanel.RoundValueText(300f, En));
            Assert.AreEqual("Objectif 100 %", Hud.GoalText(1.0, Fr));
            Assert.AreEqual("Goal 100%", Hud.GoalText(1.0, En));
            Assert.AreEqual("Objectif 60 %", Hud.GoalText(0.6, Fr));
            Assert.AreEqual(0.0, Hud.GoalPercent(0.0), "goal off");
            Assert.AreEqual("15:00", Strings.Clock(900.0));
            Assert.AreEqual("9:59", Strings.Clock(598.2));
            Assert.AreEqual("0:07", Strings.Clock(6.5));
        }

        [Test]
        public void V17_ResultsLinesOfTheConquestEnd()
        {
            int lang = Strings.Language;
            ResultsScreen.BuildLines(new HumanOutcome { Rank = 1, Reason = RoundEndReason.Conquest, Winner = 0 }, out string cause, out string why);
            Assert.AreEqual(Strings.Get("results.conquest", lang), cause);
            Assert.IsNull(why);

            ResultsScreen.BuildLines(new HumanOutcome { Rank = 2, Reason = RoundEndReason.Conquest, Winner = 2 }, out cause, out why);
            Assert.AreEqual(Strings.FormatIn(lang, "results.conquest_rival", Strings.PlayerName(2, -1)), cause);

            ResultsScreen.BuildLines(new HumanOutcome { Rank = 1, Reason = RoundEndReason.TimeUp, Winner = 0 }, out cause, out why);
            Assert.AreEqual(Strings.Get("results.time_up", lang), cause);
            Assert.AreEqual(Strings.Get("results.time_up_winner", lang), why, "after the cap the largest land wins");

            foreach (string key in new[] { "results.conquest", "results.conquest_rival", "results.time_up_winner", "results.next_country", "hud.goal", "options.minutes_value" })
            {
                Assert.AreNotEqual(key, Strings.Get(key, Fr), key + " (FR)");
                Assert.AreNotEqual(key, Strings.Get(key, En), key + " (EN)");
            }
            Assert.AreEqual("PAYS SUIVANT", Strings.Get("results.next_country", Fr));
            Assert.AreEqual("REJOUER", Strings.Get("results.replay", Fr));
        }

        [Test]
        public void V17_EveryWinningEndCountsForTheEuropeCampaign()
        {
            foreach (RoundEndReason reason in new[] { RoundEndReason.Conquest, RoundEndReason.LastSurvivor, RoundEndReason.TimeUp })
            {
                Assert.IsTrue(EuropeProgress.IsCountedWin(true, false, new HumanOutcome { Rank = 1, Reason = reason }), reason + " won");
                Assert.IsTrue(EuropeProgress.IsCountedWin(true, false, new HumanOutcome { Rank = 1, SharedRank = true, Reason = reason }), reason + " shared");
                Assert.IsFalse(EuropeProgress.IsCountedWin(true, false, new HumanOutcome { Rank = 2, Reason = reason }), reason + " lost");
            }
        }

        [Test]
        public void V17_TheMenuHasNoCountriesButton()
        {
            UiRoot ui = UiRoot.Create(null);
            try
            {
                Assert.IsNotNull(ui.Menu);
                Assert.IsNull(ui.Menu.Canvas.transform.Find("SafeArea/Countries"), "the Pays button is gone");
                foreach (UnityEngine.UI.Button b in ui.Menu.Canvas.GetComponentsInChildren<UnityEngine.UI.Button>(true))
                {
                    Assert.AreNotEqual("Countries", b.name);
                }
                Assert.IsNotNull(System.Array.Find(ui.Menu.Canvas.GetComponentsInChildren<UnityEngine.UI.Button>(true), b => b.name == "Options"));
            }
            finally
            {
                Object.DestroyImmediate(ui.gameObject);
            }
        }
    }
}
