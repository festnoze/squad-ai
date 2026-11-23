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
    /// Idea 7 (BUBBLES, docs/next/progress/BUBBLES.md), on the real Boot scene under GameRules.M2: the reaction tables (every
    /// kind has lines, 3 to 6 per group, at most 5 words, both languages, no em-dash), the seeded choice is deterministic, a
    /// discovery puts a "noticed" bubble over the inhabitant that fades after Hold + Fade, the catch keeps its own line under
    /// the fail panel, the pool never grows, and the title house shows nothing. Written for the compile-only wave: not run
    /// yet (A VERIFIER in the progress file).
    /// </summary>
    public sealed class ProbeTestsBubbles
    {
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private GameState Game => main.Game;
        private Menu Menu => main.Menu;
        private FurnitureController Chair => Game.Furniture;
        private Inhabitant Habitant => Game.MainInhabitant;
        private SpeechBubbles Bubbles => Game.GetComponentInChildren<SpeechBubbles>(true);

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            SpeechBubbles.Seed = 7;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            Game.Rules = GameRules.M2;
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                }
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            Cursor.lockState = CursorLockMode.None;
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

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static int Words(string line)
        {
            int n = 0;
            foreach (string token in line.Split(' '))
            {
                foreach (char c in token)
                {
                    if (char.IsLetterOrDigit(c))
                    {
                        n++;
                        break;
                    }
                }
            }
            return n;
        }

        // ----- The tables (pure Core, no scene needed, but the Boot scene is cheap and loaded anyway) -----

        [Test]
        public void Step80a_ReactionTables_EveryKindHasLines_ShortBothLanguages_NoEmDash()
        {
            foreach (ReactionKind kind in Reactions.AllKinds)
            {
                // DOGCARRY: the dog's drag lines are the dog's own, like its barks.
                string speaker = kind == ReactionKind.DogBark || kind == ReactionKind.DogDrag ? PersonalityDef.Dog
                    : kind == ReactionKind.RobotBump ? Reactions.Robot : null;
                Assert.GreaterOrEqual(Reactions.Count(kind, speaker), Reactions.MinVariants, kind + " has too few lines");
            }
            foreach (string group in Reactions.Groups)
            {
                string[] parts = group.Split('.');
                ReactionKind kind = ReactionKind.NearMiss;
                foreach (ReactionKind k in Reactions.AllKinds)
                {
                    if (Reactions.KindId(k) == parts[0])
                    {
                        kind = k;
                    }
                }
                string[] keys = Reactions.Keys(kind, parts[1]);
                Assert.That(keys.Length, Is.InRange(Reactions.MinVariants, Reactions.MaxVariants), group + " variant count");
                foreach (string key in keys)
                {
                    foreach (string language in new[] { Strings.English, Strings.French })
                    {
                        string line = Strings.Get(key, language);
                        Assert.AreNotEqual(key, line, key + " missing in " + language);
                        Assert.LessOrEqual(Words(line), Reactions.MaxWords, key + " too long in " + language + ": " + line);
                        Assert.IsFalse(line.IndexOf((char)0x2014) >= 0, key + " has an em-dash in " + language);
                    }
                }
            }
            // The personalities each speak with their own voice on the four flavoured kinds; Granny sits in her own words.
            foreach (string p in new[] { PersonalityDef.Dreamer, PersonalityDef.Watchful, PersonalityDef.Hurried, PersonalityDef.Granny, PersonalityDef.Teen, PersonalityDef.Tidy })
            {
                foreach (ReactionKind kind in new[] { ReactionKind.NearMiss, ReactionKind.Noticed, ReactionKind.PutBack, ReactionKind.Caught })
                {
                    Assert.IsTrue(Reactions.HasOwn(kind, p), p + " has no own " + kind + " lines");
                }
            }
            Assert.IsTrue(Reactions.HasOwn(ReactionKind.SatOn, PersonalityDef.Granny), "Granny has no own sat-on lines");
            Assert.IsFalse(Reactions.HasOwn(ReactionKind.SatOn, PersonalityDef.Teen), "the teen falls back on the default sat-on lines");
            Assert.AreEqual(Reactions.Count(ReactionKind.SatOn, PersonalityDef.Default), Reactions.Count(ReactionKind.SatOn, PersonalityDef.Teen));
        }

        [Test]
        public void Step80b_ReactionPick_IsSeededAndNeverRepeatsTheAvoidedVariant()
        {
            var a = new System.Random(42);
            var b = new System.Random(42);
            for (int i = 0; i < 20; i++)
            {
                Assert.AreEqual(Reactions.Pick(ReactionKind.Noticed, PersonalityDef.Tidy, a), Reactions.Pick(ReactionKind.Noticed, PersonalityDef.Tidy, b));
            }
            var c = new System.Random(3);
            for (int i = 0; i < 30; i++)
            {
                Reactions.Pick(ReactionKind.Caught, PersonalityDef.Granny, c, 1, out int variant);
                Assert.AreNotEqual(1, variant, "the avoided variant came back");
            }
            Assert.IsNull(Reactions.Pick(ReactionKind.DogBark, PersonalityDef.Default, c), "a human has no bark");
            Assert.IsNull(Reactions.Pick(ReactionKind.DogDrag, PersonalityDef.Default, c), "a human has no drag line");
        }

        // ----- In the scene -----

        [UnityTest]
        public IEnumerator Step80c_Discovery_ShowsANoticedBubbleOverTheInhabitant_ThatFades()
        {
            SpeechBubbles bubbles = Bubbles;
            Assert.IsNotNull(bubbles, "GameState built no SpeechBubbles");
            Assert.AreEqual(SpeechBubbles.PoolSize, bubbles.transform.childCount, "the pool is built once, PoolSize bubbles");
            Assert.AreEqual(0, bubbles.ActiveCount, "nothing is said before anything happens");
            // The chair far out of place, right in front of the pinned inhabitant: a discovery after the grace.
            Vector3 eye = Habitant.Routine.Position;
            Vector3 forward = Quaternion.Euler(0f, Habitant.Routine.BodyYaw, 0f) * Vector3.forward;
            Habitant.Pin(eye, Habitant.Routine.BodyYaw, 0f, true);
            Chair.Teleport(eye + forward * 2.5f, 0f);
            int guard = 0;
            while (Game.DiscoveryCount == 0 && Game.State == PlayState.Playing && guard++ < 400)
            {
                yield return new WaitForFixedUpdate();
            }
            Assert.Greater(Game.DiscoveryCount, 0, "premise: no discovery");
            yield return null;
            string text = bubbles.TextOver(Habitant);
            Assert.IsNotNull(text, "no bubble over the inhabitant after its discovery");
            Assert.AreEqual(ReactionKind.Noticed, bubbles.LastKind);
            bool known = false;
            foreach (string key in Reactions.Keys(ReactionKind.Noticed, Habitant.Personality.Id))
            {
                known |= Strings.Get(key) == text;
            }
            Assert.IsTrue(known, "the bubble says a line of another kind: " + text);
            Vector2 at = bubbles.PositionOver(Habitant);
            Assert.Greater(at.x, 0f, "the bubble is off screen");
            Assert.Greater(at.y, 0f, "the bubble is off screen");
            Assert.AreEqual(1, bubbles.ActiveCount, "one bubble per inhabitant");
            yield return new WaitForSeconds(SpeechBubbles.Hold + SpeechBubbles.Fade + 0.2f);
            Assert.IsNull(bubbles.TextOver(Habitant), "the bubble never faded");
            Assert.AreEqual(SpeechBubbles.PoolSize, bubbles.transform.childCount, "the pool grew");
            Assert.AreEqual(0, exceptions, string.Join("\n", logged));
        }

        [UnityTest]
        public IEnumerator Step80d_Caught_KeepsTheCatchLineUnderTheFailPanel()
        {
            SpeechBubbles bubbles = Bubbles;
            Vector3 eye = Habitant.Routine.Position;
            Vector3 forward = Quaternion.Euler(0f, Habitant.Routine.BodyYaw, 0f) * Vector3.forward;
            Habitant.Pin(eye, Habitant.Routine.BodyYaw, 0f, true);
            Chair.Teleport(eye + forward * 2.5f, 0f);
            Chair.ScriptedDirection = Vector3.right;
            int guard = 0;
            while (Game.State == PlayState.Playing && guard++ < 600)
            {
                yield return new WaitForFixedUpdate();
            }
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Caught, Game.State, "premise: never caught");
            yield return null;
            Assert.AreEqual(ReactionKind.Caught, bubbles.LastKind, "the catch raised no line");
            Assert.AreEqual(1, bubbles.ActiveCount, "the end panel keeps only the catch's own line");
            Assert.Greater(bubbles.AlphaOver(Habitant), 0f, "the catch line is hidden");
            yield return new WaitForSeconds(SpeechBubbles.Hold + SpeechBubbles.Fade + 0.2f);
            Assert.AreEqual(0, bubbles.ActiveCount, "the catch line never faded");
        }

        [UnityTest]
        public IEnumerator Step80e_TitleHouse_SaysNothing()
        {
            SpeechBubbles bubbles = Bubbles;
            Menu.ShowTitle();
            yield return Steps(150);
            Assert.AreEqual(0, bubbles.ActiveCount, "a bubble showed on the title house");
            Assert.AreEqual(0, bubbles.ShownCount, "a bubble was counted on the title house");
            Assert.AreEqual(0, exceptions, string.Join("\n", logged));
        }
    }
}
