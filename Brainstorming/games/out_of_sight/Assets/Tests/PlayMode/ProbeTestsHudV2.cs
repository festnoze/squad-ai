using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Levels v2 task C3b (docs/levels_v2/LEVELS_V2.md 6 and 8, wave1/code_features.json "Start on first input", "Intro
    /// card: inhabitant names and the goal line", "Exit and goal markers over walls") on the real Boot scene:
    /// <list type="bullet">
    /// <item>HudV2_01: a held level keeps the intro card fully visible past the M1 4 s with the start line (its gamepad
    /// variant once the pad is the last device) while the world runs under it (AUTOSTART); the first move input releases
    /// it, the start line goes and the card fades (Hud.HeldCardFadeSeconds, LEVELNUM).</item>
    /// <item>HudV2_02: level22's card lists the data names (Alfred, Mamie, the Comtesse's) as hud.person lines.</item>
    /// <item>HudV2_03: level4's hint resolves {careful} to the device's control (keyboard, then gamepad); no hint of the
    /// manifest keeps a token, in either language, on any device.</item>
    /// <item>HudV2_04: the exit marker exists, sits on the exit when it is on screen, clamps to the screen edge with its
    /// arrow when it is behind or beside the camera, fades from 3 m to 1 m of the furniture, and hides while paused and
    /// under a panel.</item>
    /// <item>HudV2_05: "Locked" shows in reach of a playerLocked leaf (test_v2_locked_door), never with "E: open".</item>
    /// <item>HudV2_06: the lit-zone line shows while the switched-off lamp stands in a lit zone (test_v2_litzone) only.</item>
    /// </list>
    /// The HUD runs on real frames (Update, unscaled time): the waits count frames or real seconds under a guard.
    /// </summary>
    public sealed class ProbeTestsHudV2
    {
        private const string LockedLevel = "test_v2_locked_door";
        private const string LitLevel = "test_v2_litzone";

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private GameState Game => main.Game;
        private Hud Hud => main.Hud;
        private FurnitureController Chair => Game.Furniture;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            GameState.HoldStart = false;
            GamePause.IsPaused = false;
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

        private IEnumerator Load(string id)
        {
            Game.LoadLevel(id);
            Assert.AreEqual(id, Game.Def.Id, "premise: the level loaded");
            yield return FixedSteps(2);
            yield return Frames(2);
        }

        /// <summary>HudV2_01: the card is held until the first move input, with the start line, then fades (Hud.HeldCardFadeSeconds).</summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator HudV2_01_CardHeldUntilTheFirstInputThenFades()
        {
            GameState.HoldStart = true;
            Game.LoadLevel("level1");
            Assert.IsFalse(Game.Started, "premise: the build with the hold on did not hold");
            yield return Frames(2);
            Assert.IsTrue(Hud.CardHeld, "the card is not held while the level waits");
            Assert.IsTrue(Hud.StartLineVisible, "no start line on the held card");
            Assert.AreEqual(Strings.HudStart, Hud.StartLineText, "the keyboard start line");

            // Well past the M1 timing (4 s shown, then 1 s of fade): still fully shown.
            float t0 = Time.realtimeSinceStartup;
            float lowest = 1f;
            while (Time.realtimeSinceStartup - t0 < 5.6f)
            {
                lowest = Mathf.Min(lowest, Hud.TitleCardAlpha);
                yield return null;
            }
            Assert.AreEqual(1f, lowest, 1e-4f, "the held card faded with no input");
            Assert.IsTrue(Hud.CardHeld && Hud.StartLineVisible, "the held card lost its start line");
            Assert.AreEqual(0, Game.Steps, "premise: the held level's clock ran");
            // AUTOSTART: the card only waits for the player; the world runs under it.
            Assert.Greater(Game.WorldSteps, 0, "the world waited under the held card");
            Assert.AreEqual(PlayState.Playing, Game.State, "the level ended under the held card");

            // The pad as the last device: the start line names the stick.
            InputReader.InjectLastDevice(true);
            yield return Frames(2);
            Assert.AreEqual(Strings.HudStartGamepad, Hud.StartLineText, "the gamepad start line");
            InputReader.InjectLastDevice(false);
            yield return Frames(2);
            Assert.AreEqual(Strings.HudStart, Hud.StartLineText, "the keyboard start line again");

            // The first move input releases the level; the card fades from that instant over Hud.HeldCardFadeSeconds (0.4 s since LEVELNUM).
            InputReader.InjectMoveVector(Vector2.up);
            int guard = 0;
            while (!Game.Started && guard++ < 20)
            {
                yield return new WaitForFixedUpdate();
            }
            InputReader.ClearMoveVector();
            Assert.IsTrue(Game.Started, "the move input did not start the level");
            yield return null;
            float released = Time.realtimeSinceStartup;
            Assert.IsFalse(Hud.CardHeld, "the card is still held after the start");
            Assert.IsFalse(Hud.StartLineVisible, "the start line outlived the start");
            bool partial = false;
            while (Time.realtimeSinceStartup - released < 1.4f)
            {
                float a = Hud.TitleCardAlpha;
                partial |= a > 0.01f && a < 0.99f;
                yield return null;
            }
            Assert.IsTrue(partial, "the card did not fade (no frame between shown and gone)");
            Assert.AreEqual(0f, Hud.TitleCardAlpha, 1e-4f, "the card is not gone 1.4 s after the start");
            AssertClean();
        }

        /// <summary>HudV2_02: level22's card names Alfred, Mamie and the Comtesse as in the data, hud.person lines.</summary>
        [UnityTest]
        [Timeout(120000)]
        public IEnumerator HudV2_02_Level22CardListsTheDataNames()
        {
            yield return Load("level22");
            Assert.IsTrue(Hud.PeopleVisible, "level22's card lists nobody");
            string countess = null;
            foreach (InhabitantDef h in Game.Def.Inhabitants)
            {
                if (h.Personality == PersonalityDef.Watchful)
                {
                    countess = h.Name;
                }
            }
            Assert.IsFalse(string.IsNullOrEmpty(countess), "premise: level22 has a watchful inhabitant (the Comtesse)");
            string all = string.Join("\n", Hud.PeopleShown);
            foreach (string name in new[] { "Alfred", "Mamie", countess })
            {
                StringAssert.Contains(name, Hud.PeopleShown[0], $"the names line does not list {name}");
            }
            // Each human: hud.person with the data name and the personality label (a label equal to the name shows once).
            StringAssert.Contains(Hud.PersonTitle("Alfred", Strings.PersonHurried, false), all, "Alfred's person line");
            StringAssert.Contains(Hud.PersonTitle(countess, Strings.PersonWatchful, false), all, "the Comtesse's person line");
            StringAssert.Contains(Hud.PersonTitle("Mamie", Strings.PersonGranny, false), all, "Mamie's person line");
            StringAssert.Contains(string.Format(Strings.HudPerson, "Alfred", ""), all, "Alfred is not shown as 'Alfred, ...'");

            // The format itself: the label's article after the comma in lower case, the dog's whole label too.
            Assert.AreEqual("Lea, the Suspicious One", Hud.PersonTitle("Lea", "The Suspicious One", false));
            Assert.AreEqual("Rex, the dog", Hud.PersonTitle("Rex", "The Dog", true));
            Assert.AreEqual("Mamie", Hud.PersonTitle("Mamie", "Mamie", false));
            Assert.AreEqual("The Daydreamer", Hud.PersonTitle(null, "The Daydreamer", false));
            Assert.IsFalse(all.Contains("\u2014"), "an em-dash on the card");
            AssertClean();
        }

        /// <summary>HudV2_03: the hint's tokens become the device's control names.</summary>
        [UnityTest]
        [Timeout(120000)]
        public IEnumerator HudV2_03_HintTokensNameTheDeviceControls()
        {
            yield return Load("level4");
            Assert.IsTrue(Strings.Get(Game.Def.HintKey).Contains("{careful}"), "premise: level4's hint has the {careful} token");
            string keyboard = Hud.CarefulLabel(Hud.HintDevice.Keyboard);
            Assert.IsFalse(string.IsNullOrEmpty(keyboard), "no keyboard careful label");
            Assert.AreEqual(Hud.HintDevice.Keyboard, Hud.Device, "premise: the keyboard is the device");
            StringAssert.DoesNotContain("{careful}", Hud.HintShown, "level4's hint keeps {careful}");
            StringAssert.Contains(keyboard, Hud.HintShown, "level4's hint does not name the keyboard's careful key");
            Assert.AreEqual(Hud.ResolveHintTokens(Strings.Get(Game.Def.HintKey), Hud.HintDevice.Keyboard), Hud.HintShown);

            InputReader.InjectLastDevice(true);
            yield return Frames(2);
            Assert.AreEqual(Hud.HintDevice.Gamepad, Hud.Device, "premise: the gamepad is the device");
            StringAssert.Contains(Hud.CarefulLabel(Hud.HintDevice.Gamepad), Hud.HintShown, "the gamepad's careful control");
            StringAssert.DoesNotContain(keyboard, Hud.HintShown, "the keyboard key stayed with the gamepad");
            InputReader.InjectLastDevice(false);
            yield return Frames(2);
            StringAssert.Contains(keyboard, Hud.HintShown, "back to the keyboard key");

            // No hint of the manifest keeps a token, in either language, on any device.
            var left = new List<string>();
            foreach (string id in Game.LevelOrder)
            {
                LevelDef def = LevelLoader.Load(id);
                if (def == null || string.IsNullOrEmpty(def.HintKey))
                {
                    continue;
                }
                foreach (string language in new[] { Strings.English, Strings.French })
                {
                    foreach (Hud.HintDevice device in new[] { Hud.HintDevice.Keyboard, Hud.HintDevice.Gamepad, Hud.HintDevice.Touch })
                    {
                        string shown = Hud.ResolveHintTokens(Strings.Get(def.HintKey, language), device);
                        if (shown.Contains("{action}") || shown.Contains("{careful}"))
                        {
                            left.Add($"{id} {language} {device}: {shown}");
                        }
                    }
                }
            }
            CollectionAssert.IsEmpty(left, string.Join("\n", left));
            // DOORAUTO: {action} names the lamp switch only; on touch it is "tap the lamp" (the action button is gone).
            string lamp = Hud.ResolveHintTokens("{action} / {action}", Hud.HintDevice.Touch);
            Assert.AreEqual(Strings.TouchLamp + " / " + Strings.TouchLamp, lamp, "every {action} on touch");
            AssertClean();
        }

        /// <summary>HudV2_04: the exit marker sits on the exit, clamps off screen with its arrow, fades near and hides.</summary>
        [UnityTest]
        [Timeout(180000)]
        public IEnumerator HudV2_04_ExitMarkerClampsAndFades()
        {
            yield return Load("level1");
            Game.Rules = GameRules.M4;
            Assert.IsTrue(Hud.ExitMarkerExists, "no exit marker");
            ZoneDef exit = Game.Def.Exit;
            Vector3 exitPoint = new Vector3(exit.X, Game.Def.FloorHeightAt(exit.X, exit.Z) + 0.4f, exit.Z);
            Vector3 spawn = Chair.transform.position;
            float spawnDistance = new Vector2(spawn.x - exit.X, spawn.z - exit.Z).magnitude;
            Assert.Greater(spawnDistance, Hud.MarkerFadeFar, "premise: level1 spawns more than 3 m from the exit");
            Assert.IsTrue(Hud.ExitMarkerVisible, "the exit marker is not drawn at the spawn");
            Assert.AreEqual(1f, Hud.ExitMarkerAlpha, 1e-4f, "the marker is not fully drawn far from the exit");

            Camera saved = Hud.View;
            var camGo = new GameObject("HudV2TestCamera");
            Camera cam = camGo.AddComponent<Camera>();
            cam.enabled = false;
            cam.fieldOfView = 60f;
            try
            {
                Hud.View = cam;
                var screen = new Rect(0f, 0f, Screen.width, Screen.height);

                // Facing the exit: on screen, on the exit's projection, no arrow.
                cam.transform.position = exitPoint + new Vector3(0f, 3f, -6f);
                cam.transform.LookAt(exitPoint);
                yield return Frames(2);
                Vector3 projected = cam.WorldToScreenPoint(exitPoint);
                Assert.IsFalse(Hud.ExitMarkerClamped, "the marker clamps while the exit is on screen");
                Assert.Less(Vector2.Distance(Hud.ExitMarkerScreenPosition, new Vector2(projected.x, projected.y)), 2f,
                    $"the marker {Hud.ExitMarkerScreenPosition} is not on the exit {projected}");

                // Beside the camera (70 degrees to the right of the exit): in front, off screen; clamped on the left.
                Vector3 toExit = YawMath.Planar(exitPoint - cam.transform.position).normalized;
                cam.transform.rotation = Quaternion.LookRotation(Quaternion.Euler(0f, 70f, 0f) * toExit, Vector3.up);
                yield return Frames(2);
                Vector3 beside = cam.WorldToScreenPoint(exitPoint);
                Assert.IsTrue(beside.z > 0f && !screen.Contains(new Vector2(beside.x, beside.y)), $"premise: the exit {beside} is in front and off screen");
                Assert.IsTrue(Hud.ExitMarkerClamped, "the marker does not clamp off screen");
                Vector2 at = Hud.ExitMarkerScreenPosition;
                Assert.IsTrue(screen.Contains(at), $"the clamped marker {at} leaves the screen {screen}");
                Assert.Less(at.x, screen.width * 0.25f, $"the clamped marker {at} is not on the left edge (the exit is to the left)");

                // Behind the camera: clamped on the screen.
                cam.transform.rotation = Quaternion.LookRotation(-toExit, Vector3.up);
                yield return Frames(2);
                Assert.IsTrue(Hud.ExitMarkerClamped, "the marker does not clamp with the exit behind");
                Assert.IsTrue(screen.Contains(Hud.ExitMarkerScreenPosition), $"the marker {Hud.ExitMarkerScreenPosition} leaves the screen with the exit behind");
                Assert.IsTrue(Hud.ExitMarkerVisible, "the clamped marker is not drawn");
            }
            finally
            {
                Hud.View = saved;
                Object.Destroy(camGo);
            }

            // The fade: 2 m from the exit half drawn, 0.8 m gone (the furniture is not on the exit zone there).
            RoomDef room = Game.Def.RoomAt(new Vector3(exit.X, 0f, exit.Z));
            Vector3 inward = room != null ? YawMath.Planar(new Vector3(room.X, 0f, room.Z) - new Vector3(exit.X, 0f, exit.Z)) : Vector3.zero;
            if (inward.sqrMagnitude < 1e-4f)
            {
                inward = YawMath.Planar(spawn - new Vector3(exit.X, 0f, exit.Z));
            }
            inward.Normalize();
            var exitFloor = new Vector3(exit.X, Chair.transform.position.y, exit.Z);
            Chair.Teleport(exitFloor + inward * 2f, Chair.Yaw);
            yield return Frames(2);
            Assert.AreEqual(0.5f, Hud.ExitMarkerAlpha, 0.06f, "the marker is not half drawn 2 m from the exit");
            Chair.Teleport(exitFloor + inward * 0.8f, Chair.Yaw);
            yield return Frames(2);
            Assert.IsFalse(exit.Contains(Chair.transform.position), "premise: 0.8 m from the centre is off the exit zone");
            Assert.AreEqual(0f, Hud.ExitMarkerAlpha, 1e-4f, "the marker is still drawn 0.8 m from the exit");
            Assert.IsFalse(Hud.ExitMarkerVisible, "the faded marker counts as drawn");
            Assert.IsFalse(Hud.ExitMarkerEyeShown, "the eye glyph off the exit zone");
            Chair.Teleport(spawn, Chair.Yaw);
            yield return Frames(2);
            Assert.IsTrue(Hud.ExitMarkerVisible, "the marker did not come back far from the exit");

            // Hidden while paused and under a panel.
            Game.Paused = true;
            yield return Frames(2);
            Assert.IsFalse(Hud.ExitMarkerVisible, "the marker shows while paused");
            Game.Paused = false;
            yield return Frames(2);
            Assert.IsTrue(Hud.ExitMarkerVisible, "the marker did not come back after the pause");
            Hud.ShowFail();
            yield return Frames(2);
            Assert.IsFalse(Hud.ExitMarkerVisible, "the marker shows over the fail panel");
            Hud.HidePanels();
            yield return Frames(2);
            Assert.IsTrue(Hud.ExitMarkerVisible, "the marker did not come back after the panel");
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: level1 still plays");
            AssertClean();
        }

        /// <summary>HudV2_05: "Locked" in reach of a playerLocked leaf, never together with "E: open".</summary>
        [UnityTest]
        [Timeout(120000)]
        public IEnumerator HudV2_05_LockedHintAtAPlayerLockedLeaf()
        {
            Game.LoadLevel(LockedLevel);
            Game.Rules = GameRules.M4;
            yield return FixedSteps(2);
            yield return Frames(2);
            Assert.IsTrue(Game.LockedDoorHintWanted, "premise: the locked hint is wanted at the fixture's spawn");
            Assert.IsTrue(Hud.LockedHintVisible, "no 'Locked' hint in reach of a playerLocked leaf");
            Assert.IsFalse(Hud.DoorHintVisible, "'E: open' shows for a playerLocked leaf");
            Assert.IsTrue(Hud.Labels.TryGetValue("DoorLockedHintLine", out Text line), "premise: the locked line label");
            Assert.AreEqual(Strings.HudDoorLocked, line.text, "the locked line's text");
            Hud.ShowFail();
            yield return Frames(1);
            Assert.IsFalse(Hud.LockedHintVisible, "'Locked' shows over the fail panel");
            Hud.HidePanels();
            AssertClean();
        }

        /// <summary>HudV2_06: the lit-zone line shows only while the switched-off lamp stands in a lit zone.</summary>
        [UnityTest]
        [Timeout(120000)]
        public IEnumerator HudV2_06_LitHintWhileTheDarkLampStandsInALitZone()
        {
            Game.LoadLevel(LitLevel);
            yield return FixedSteps(2);
            // Nobody catches the lamp while it is moved around (the HUD reads the furniture, not the clock).
            Game.Paused = true;
            yield return Frames(2);
            FurnitureController lamp = Game.Furniture;
            Assert.IsNotNull(lamp.Lamp, "premise: the player is the floor lamp");
            Assert.IsTrue(lamp.Rules != null && lamp.Rules.Lamp, "premise: the lamp rule is on");
            Assert.GreaterOrEqual(Game.Def.LitZones.Count, 1, "premise: a lit zone");
            LitZoneDef zone = Game.Def.LitZones[0];
            Vector3 spawn = lamp.transform.position;
            Vector3 inZone = new Vector3(zone.X, spawn.y, zone.Z);

            lamp.Lamp.SetOn(false);
            lamp.Teleport(inZone, lamp.Yaw);
            yield return Frames(2);
            Assert.IsTrue(lamp.InLitZone, "premise: the lamp stands in the zone");
            Assert.IsTrue(Hud.LitHintVisible, "no lit-zone line for the dark lamp in the zone");
            Assert.IsTrue(Hud.Labels.TryGetValue("LitHintLine", out Text line) && line.text == Strings.HudLit, "the lit line's text");

            lamp.Lamp.SetOn(true);
            yield return Frames(2);
            Assert.IsFalse(Hud.LitHintVisible, "the lit-zone line for a lit lamp");

            lamp.Lamp.SetOn(false);
            lamp.Teleport(spawn, lamp.Yaw);
            yield return Frames(2);
            Assert.IsFalse(lamp.InLitZone, "premise: the spawn is outside the zone");
            Assert.IsFalse(Hud.LitHintVisible, "the lit-zone line outside the zone");
            lamp.Lamp.SetOn(true);
            Game.Paused = false;
            AssertClean();
        }
    }
}
