using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Onboarding tips (idea 3, docs/next/progress/TIPS.md) on the real Boot scene. Written statically (not run yet: the
    /// product owner asked for no Unity test runs); see the A VERIFIER list of the progress file.
    /// <list type="bullet">
    /// <item>Tips_01: on level1, driving the chair forward brings the freeze tip (or the eye tip) within 25 s of game time;
    /// its text carries no token, the plate is visible with the pointer over the eye, it goes by itself after ShowSeconds
    /// and the save then holds the key; the same trigger is refused afterwards (once per save).</item>
    /// <item>Tips_02: a triggered creak tip points at the creak gauge; the suspicion tip at the suspicion gauge; a tip refused
    /// while another shows; the freeze tip replaces the eye tip.</item>
    /// <item>Tips_03: the decoy tip does not apply to level1 and does on level3 (pointer over the decoy, then the plate on its
    /// row when the spot is off screen); the rug tip applies to level2 only from the lineup's start.</item>
    /// <item>Tips_04: paused, the plate hides and its clock stops; resumed, it comes back; a tip cut short before MinSeconds is
    /// not committed and shows again; a restart clears the plate.</item>
    /// <item>Tips_05: the fail panel drops the tip; a win panel too.</item>
    /// <item>Tips_06 (plain test): SaveData round-trips "tips", ignores a malformed one, and TipDef.ConeTurnsToward holds its
    /// contract; every tips.* string exists in both languages with no em-dash and the {move} token resolves per device.</item>
    /// <item>Tips_07 (AUTOSTART): no tip under the held card although the world runs there; one may show after the start.</item>
    /// </list>
    /// </summary>
    public sealed class ProbeTestsTips
    {
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private GameState Game => main.Game;
        private Hud Hud => main.Hud;
        private Tips Tips => Hud.Tips;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            GameState.HoldStart = false;
            GamePause.IsPaused = false;
            Tips.EnabledOverride = true;
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            InputReader.ResetInjections();
            InputReader.InjectLastDevice(false);
            SaveStore.ResetForTests();
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            Assert.IsNotNull(Hud, "premise: Main has no HUD");
            Assert.IsNotNull(Tips, "premise: the HUD built no Tips");
            GamePause.IsPaused = false;
            yield return FixedSteps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            InputReader.InjectLastDevice(false);
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            GamePause.IsPaused = false;
            GameState.HoldStart = false;
            Tips.EnabledOverride = null;
            Application.logMessageReceived -= OnLog;
            yield return null;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        private void AssertClean()
        {
            Assert.AreEqual(0, exceptions, "errors were logged: " + string.Join(" | ", logged));
        }

        private static IEnumerator FixedSteps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static IEnumerator Frames(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return null;
            }
        }

        private static IEnumerator RealSeconds(float seconds)
        {
            float t0 = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - t0 < seconds)
            {
                yield return null;
            }
        }

        private IEnumerator Load(string id)
        {
            Game.LoadLevel(id);
            Assert.AreEqual(id, Game.Def.Id, "premise: the level loaded");
            yield return FixedSteps(2);
            yield return Frames(2);
        }

        private static bool Near(Rect rect, Vector2 point, float margin)
        {
            return point.x >= rect.xMin - margin && point.x <= rect.xMax + margin && point.y >= rect.yMin - margin && point.y <= rect.yMax + margin;
        }

        /// <summary>Tips_01: the freeze or eye tip comes by itself on level1, resolves its token, goes after ShowSeconds and is saved.</summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Tips_01_FirstTipOnLevel1ShowsOnceAndIsSaved()
        {
            yield return Load("level1");
            Assert.IsNull(Tips.ShownKey, "premise: no tip at the start");
            InputReader.InjectMoveVector(Vector2.up);
            float t0 = Time.realtimeSinceStartup;
            while (Tips.ShownKey == null && Game.State == PlayState.Playing && Time.realtimeSinceStartup - t0 < 25f)
            {
                yield return null;
            }
            InputReader.ClearMoveVector();
            Assert.IsNotNull(Tips.ShownKey, "no tip fired on level1 while driving toward the watcher");
            string key = Tips.ShownKey;
            Assert.IsTrue(key == TipDef.Freeze || key == TipDef.Eye || key == TipDef.Creak || key == TipDef.Suspicion, "unexpected tip " + key);
            yield return Frames(3);
            Assert.IsTrue(Tips.Visible, "the plate is not drawn");
            StringAssert.DoesNotContain("{", Tips.ShownText, "a token stayed in the tip");
            Assert.IsTrue(Tips.PointerVisible, "no pointer");
            if (key == TipDef.Freeze || key == TipDef.Eye)
            {
                Rect eye = Hud.ScreenRectOf(Hud.EyeAnchor);
                Assert.IsTrue(Near(eye, Tips.PointerScreen, 60f * Hud.ScaleFactor), "the pointer is not over the eye: " + Tips.PointerScreen + " vs " + eye);
            }
            if (Game.State != PlayState.Playing)
            {
                Assert.Inconclusive("caught before the tip could run its course");
            }
            yield return RealSeconds(TipDef.MinSeconds + 0.3f);
            Assert.IsTrue(Tips.Committed, "the tip was not committed after MinSeconds");
            CollectionAssert.Contains(SaveStore.Current.Tips, key, "the save does not hold the shown tip");
            yield return RealSeconds(TipDef.ShowSeconds);
            Assert.IsNull(Tips.ShownKey, "the tip stayed past ShowSeconds");
            Assert.IsFalse(Tips.Trigger(key), "the same tip showed again in the same save");
            StringAssert.Contains("already shown", Tips.LastRefusal);
            AssertClean();
        }

        /// <summary>Tips_02: the gauge tips point at their gauge; one tip at a time; the freeze tip preempts the eye tip.</summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Tips_02_GaugeTipsPointAtTheirGaugeAndOneShowsAtATime()
        {
            yield return Load("level1");
            Assert.IsTrue(Tips.Trigger(TipDef.Creak), "the creak tip was refused: " + Tips.LastRefusal);
            yield return Frames(3);
            Assert.IsTrue(Tips.Visible, "the creak plate is not drawn");
            Assert.IsTrue(Near(Hud.CreakScreenRect, Tips.PointerScreen, 60f * Hud.ScaleFactor), "the pointer is not over the creak gauge");
            Assert.IsFalse(Tips.Trigger(TipDef.Suspicion), "a second tip showed over the first");
            StringAssert.Contains("on screen", Tips.LastRefusal);
            Tips.Clear();
            yield return Frames(2);

            Assert.IsTrue(Tips.Trigger(TipDef.Suspicion), "the suspicion tip was refused: " + Tips.LastRefusal);
            yield return Frames(3);
            Assert.IsTrue(Near(Hud.SuspicionScreenRect, Tips.PointerScreen, 60f * Hud.ScaleFactor), "the pointer is not over the suspicion gauge");
            Tips.Clear();
            yield return Frames(2);

            Assert.IsTrue(Tips.Trigger(TipDef.Eye), "the eye tip was refused: " + Tips.LastRefusal);
            Assert.IsTrue(Tips.Trigger(TipDef.Freeze), "the freeze tip did not replace the eye tip: " + Tips.LastRefusal);
            Assert.AreEqual(TipDef.Freeze, Tips.ShownKey);
            AssertClean();
        }

        /// <summary>Tips_03: the decoy and rug tips apply to their levels only; the decoy pointer sits over the decoy.</summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Tips_03_WorldTipsApplyToTheirLevels()
        {
            yield return Load("level1");
            Assert.IsFalse(Tips.Trigger(TipDef.Decoy, Vector3.zero), "the decoy tip showed on level1");
            StringAssert.Contains("does not apply", Tips.LastRefusal);
            Assert.IsFalse(Tips.Trigger(TipDef.Rug, Vector3.zero), "the rug tip showed on level1");

            yield return Load("level3");
            Assert.IsTrue(Game.Level.Decoys.Count > 0, "premise: level3 has decoys");
            Decoy decoy = Game.Level.Decoys[0];
            Vector3 spot = decoy.Pose.Position + Vector3.up * decoy.Size.y;
            Assert.IsTrue(Tips.Trigger(TipDef.Decoy, spot), "the decoy tip was refused on level3: " + Tips.LastRefusal);
            yield return Frames(3);
            Assert.IsTrue(Tips.Visible, "the decoy plate is not drawn");
            Vector3 projected = Hud.View.WorldToScreenPoint(spot);
            if (projected.z > 0f && projected.x >= 0f && projected.x <= Screen.width && projected.y >= 0f && projected.y <= Screen.height)
            {
                Assert.IsTrue(Tips.PointerVisible, "the decoy is on screen but no pointer shows");
                Assert.AreEqual(projected.x, Tips.PointerScreen.x, 4f, "the pointer is not over the decoy (x)");
                Assert.Greater(Tips.PointerScreen.y, projected.y, "the pointer is not above the decoy");
            }
            else
            {
                Assert.IsFalse(Tips.PointerVisible, "a pointer shows for a spot off screen");
            }
            Tips.Clear();

            yield return Load("level2");
            Assert.IsTrue(Tips.Trigger(TipDef.Rug, Vector3.zero), "the rug tip was refused on level2: " + Tips.LastRefusal);
            AssertClean();
        }

        /// <summary>Tips_04: pause hides the plate and stops its clock; a tip cut short is not committed; a restart clears it.</summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Tips_04_PauseSafeAndCutShortComesBack()
        {
            yield return Load("level1");
            Assert.IsTrue(Tips.Trigger(TipDef.Creak), Tips.LastRefusal);
            yield return Frames(3);
            float shown = Tips.ShownSeconds;
            Game.Paused = true;
            yield return RealSeconds(0.6f);
            Assert.IsFalse(Tips.Visible, "the plate stayed drawn while paused");
            Assert.AreEqual(shown, Tips.ShownSeconds, 0.05f, "the tip's clock ran while paused");
            Game.Paused = false;
            yield return Frames(3);
            Assert.IsTrue(Tips.Visible, "the plate did not come back after the pause");

            // Cut short before MinSeconds: not committed, so it shows again.
            Assert.Less(Tips.ShownSeconds, TipDef.MinSeconds, "premise: still under MinSeconds");
            Game.Restart();
            yield return FixedSteps(2);
            yield return Frames(2);
            Assert.IsNull(Tips.ShownKey, "the restart kept the plate");
            Assert.IsFalse(SaveStore.Current.Tips.Contains(TipDef.Creak), "a tip cut short was written to the save");
            Assert.IsTrue(Tips.Trigger(TipDef.Creak), "a tip cut short did not come back: " + Tips.LastRefusal);
            AssertClean();
        }

        /// <summary>Tips_05: the end panels drop the tip.</summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Tips_05_EndPanelsDropTheTip()
        {
            yield return Load("level1");
            Assert.IsTrue(Tips.Trigger(TipDef.Suspicion), Tips.LastRefusal);
            yield return Frames(3);
            Assert.IsTrue(Tips.Visible);
            // Drive into the watcher's sight until caught (level1 teaches exactly that).
            InputReader.InjectMoveVector(Vector2.up);
            float t0 = Time.realtimeSinceStartup;
            while (Game.State == PlayState.Playing && Time.realtimeSinceStartup - t0 < 40f)
            {
                yield return null;
            }
            InputReader.ClearMoveVector();
            if (Game.State == PlayState.Playing)
            {
                Assert.Inconclusive("never caught within 40 s: the level1 route must be redrawn for this test");
            }
            yield return Frames(3);
            Assert.IsFalse(Tips.Visible, "the plate is drawn under the end panel");
            Assert.IsNull(Tips.ShownKey, "the end panel kept the tip");
            Assert.IsFalse(Tips.Trigger(TipDef.Eye), "a tip showed on a finished level");
            AssertClean();
        }

        /// <summary>
        /// Tips_07 (AUTOSTART): under the held card the world runs but no tip shows, on its own or asked for (the furniture
        /// is out of play: nothing a tip talks about can happen there); the first move input starts the level and a tip may
        /// show again.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Tips_07_NoTipUnderTheHeldCard()
        {
            GameState.HoldStart = true;
            Game.LoadLevel("level1");
            Assert.IsFalse(Game.Started, "premise: the build with the hold on did not hold");
            yield return FixedSteps(Mathf.RoundToInt(3f / Tuning.FixedStep));
            Assert.IsFalse(Game.Started, "the level started with no input");
            Assert.Greater(Game.WorldSteps, 0, "premise: the world does not run under the held card");
            Assert.IsNull(Tips.ShownKey, "a tip showed under the held card");
            Assert.IsFalse(Tips.Trigger(TipDef.Creak), "a tip was accepted under the held card");
            StringAssert.Contains("no running level", Tips.LastRefusal);

            InputReader.InjectMoveVector(Vector2.up);
            int guard = 0;
            while (!Game.Started && guard++ < 20)
            {
                yield return new WaitForFixedUpdate();
            }
            InputReader.ClearMoveVector();
            Assert.IsTrue(Game.Started, "the move input did not start the level");
            Tips.Clear(); // a tip the first step brought by itself would refuse the next one ("on screen")
            Assert.IsTrue(Tips.Trigger(TipDef.Creak), "a tip was refused after the start: " + Tips.LastRefusal);
            GameState.HoldStart = false;
            AssertClean();
        }

        /// <summary>Tips_06: SaveData round trip, TipDef contract and the strings.</summary>
        [Test]
        public void Tips_06_SaveRoundTripAndStrings()
        {
            var data = new SaveData();
            data.Tips.Add(TipDef.Freeze);
            data.Tips.Add(TipDef.Rug);
            SaveData back = SaveData.Parse(data.ToJson(), out string problem);
            Assert.IsNull(problem, "the save with tips does not parse: " + problem);
            CollectionAssert.AreEqual(new[] { TipDef.Freeze, TipDef.Rug }, back.Tips);

            SaveData malformed = SaveData.Parse("{ \"version\": 1, \"tips\": 42 }", out problem);
            Assert.IsNull(problem, "a malformed tips entry failed the save");
            Assert.IsEmpty(malformed.Tips);
            SaveData mixed = SaveData.Parse("{ \"version\": 1, \"tips\": [\"tips.eye\", 3, null, \"tips.eye\"] }", out problem);
            Assert.IsNull(problem);
            CollectionAssert.AreEqual(new[] { TipDef.Eye }, mixed.Tips, "non strings are skipped, duplicates kept once");

            Assert.IsTrue(TipDef.ConeTurnsToward(50f, 60f, 35f), "within the margin and shrinking");
            Assert.IsFalse(TipDef.ConeTurnsToward(70f, 80f, 35f), "outside the margin");
            Assert.IsFalse(TipDef.ConeTurnsToward(20f, 20f, 35f), "not turning");
            Assert.IsFalse(TipDef.ConeTurnsToward(20f, 10f, 35f), "turning away");
            Assert.IsTrue(TipDef.Find(TipDef.Decoy).AppliesTo("level3"));
            Assert.IsFalse(TipDef.Find(TipDef.Decoy).AppliesTo("level1"));
            Assert.IsFalse(TipDef.Find(TipDef.Rug).AppliesTo("level1"));
            Assert.IsNull(TipDef.Find("tips.nothing"));

            foreach (TipDef tip in TipDef.All)
            {
                foreach (string language in new[] { Strings.English, Strings.French })
                {
                    string text = Strings.Get(tip.Key, language);
                    Assert.AreNotEqual(tip.Key, text, tip.Key + " missing in " + language);
                    StringAssert.DoesNotContain("—", text, "no em-dash");
                    StringAssert.DoesNotContain("{action}", text, "tips name no key: {action} is a hint token, keep it out of tips");
                }
            }
            foreach (string device in new[] { "keyboard", "gamepad", "touch" })
            {
                Assert.AreNotEqual(TipDef.MoveKey(device), Strings.Get(TipDef.MoveKey(device)), "tips.move." + device + " missing");
                string resolved = Strings.Get(TipDef.Freeze).Replace(TipDef.MoveToken, Strings.Get(TipDef.MoveKey(device)));
                StringAssert.DoesNotContain("{move}", resolved);
            }
            Assert.AreEqual("tips.move.keyboard", TipDef.MoveKey("mouse"), "an unknown device reads as the keyboard");
        }
    }
}
