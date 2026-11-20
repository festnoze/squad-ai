using System;
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
    /// The music must never stop for good (bug: "the music stops and does not loop, in some cases"). The player used to
    /// trust its own running flag, so a source stopped behind its back (an audio device change resets the audio system
    /// and stops every source, an OS suspend, a stream that ended) stayed silent until the next catch or title
    /// crossfade. These cases stop the real sources the way Unity does and assert the watchdog brings them back, and walk
    /// the music through restart, pause, win, next level, title and focus changes. The logical state and the restart
    /// counter are asserted everywhere; isPlaying is asserted only when the run has a live audio output (batch mode may
    /// have none), and every case logs which of the two it ran.
    /// </summary>
    public sealed class ProbeTestsMusicLoop
    {
        private int exceptions;
        private readonly List<string> logged = new List<string>();

        private Main main;
        private GameState Game => main.Game;
        private MusicPlayer Music => main.Music;
        private Menu Menu => main.Menu;
        private FurnitureController Chair => Game.Furniture;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            Assert.IsNotNull(Music, "premise: Main built no MusicPlayer");
            Assert.IsNotNull(Music.LevelSource, "premise: no level source");
            Assert.IsNotNull(Music.LevelSource.clip, "premise: the level loop has no clip");
            Assert.IsNotNull(Music.TitleSource.clip, "premise: the title loop has no clip");
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            AudioListener.pause = false;
            GamePause.IsPaused = false;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null && main.Game.Furniture != null)
            {
                main.Game.Furniture.ScriptedDirection = null;
            }
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

        private void AssertNoErrors()
        {
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static IEnumerator Until(Func<bool> condition, int maxSteps)
        {
            for (int i = 0; i < maxSteps && !condition(); i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        /// <summary>Brings the level loop to full and tells whether this run has a live audio output (isPlaying works).</summary>
        private bool StartLevelLoop()
        {
            MusicPlayer music = Music;
            music.Tick(Tuning.MusicCrossfadeSeconds + Tuning.MusicReturnSeconds + 0.1f);
            Assert.AreEqual(MusicPlayer.Track.Level, music.Wanted, "premise: a level wants the level loop");
            Assert.IsTrue(music.LevelRunning, "premise: the level loop does not run in a level");
            bool live = music.LevelSource.isPlaying;
            Debug.Log("[music test] live audio output: " + live);
            return live;
        }

        /// <summary>The level loop runs (logical), and really plays when the run has an audio output.</summary>
        private void AssertLevelPlays(bool live, string context)
        {
            Assert.IsTrue(Music.LevelRunning, context + ": the level loop is not running");
            Assert.Greater(Music.LevelSource.volume, 0f, context + ": the level loop is silent");
            if (live)
            {
                Assert.IsTrue(Music.LevelSource.isPlaying, context + ": the level source is not playing");
            }
        }

        private IEnumerator Win()
        {
            for (int i = 0; i < Game.Level.Inhabitants.Count; i++)
            {
                Game.Level.Inhabitants[i].Pin(new Vector3(90f + 5f * i, 0f, 90f), 0f);
            }
            yield return Steps(15);
            ZoneDef exit = Game.Def.Exit;
            Chair.Teleport(new Vector3(exit.X, 0f, exit.Z), Chair.Yaw);
            yield return Until(() => Game.State != PlayState.Playing, 20);
            Assert.AreEqual(PlayState.Won, Game.State, "premise: the level was not won");
        }

        // ----- 28ma: a source stopped behind the player's back comes back -----

        [UnityTest]
        public IEnumerator Step28ma_WatchdogRestartsALoopStoppedBehindThePlayersBack()
        {
            MusicPlayer music = Music;
            bool live = StartLevelLoop();
            int restarts = music.Restarts;

            // What an OS suspend or a device loss does: the source stops, the player is not told.
            music.LevelSource.Stop();
            Assert.IsFalse(music.LevelSource.isPlaying, "premise: the source did not stop");
            music.Tick(Tuning.MusicWatchdogSeconds * 0.5f);
            Assert.AreEqual(restarts, music.Restarts, "the watchdog restarted the loop before its grace");
            music.Tick(Tuning.MusicWatchdogSeconds * 0.5f + 0.01f);
            Assert.AreEqual(restarts + 1, music.Restarts, "the watchdog did not restart the stopped level loop");
            AssertLevelPlays(live, "after the watchdog");

            // The same under the pause menu (ducked, still running).
            Menu.SetPaused(true);
            music.Tick(Tuning.MusicStingFadeSeconds + 0.01f);
            Assert.IsTrue(music.LevelRunning, "the pause menu stopped the music");
            restarts = music.Restarts;
            music.LevelSource.Stop();
            music.Tick(Tuning.MusicWatchdogSeconds + 0.01f);
            Assert.AreEqual(restarts + 1, music.Restarts, "the watchdog does not run under the pause menu");
            if (live)
            {
                Assert.IsTrue(music.LevelSource.isPlaying, "the level loop stays stopped under the pause menu");
            }
            Menu.SetPaused(false);
            music.Tick(Tuning.MusicReturnSeconds + 0.01f);
            AssertLevelPlays(live, "after the pause");
            yield return null;
            AssertNoErrors();
        }

        // ----- 28mb: an audio configuration change (a headphones switch) restarts the music at once -----

        [UnityTest]
        public IEnumerator Step28mb_AudioDeviceChangeRestartsTheMusicAtOnce()
        {
            MusicPlayer music = Music;
            bool live = StartLevelLoop();
            int restarts = music.Restarts;
            int resets = music.AudioResets;

            // A device change stops every source, then raises OnAudioConfigurationChanged(true).
            music.LevelSource.Stop();
            music.TitleSource.Stop();
            music.HandleAudioConfigurationChanged(true);
            Assert.AreEqual(resets + 1, music.AudioResets);
            music.Tick(0.01f);
            Assert.AreEqual(restarts + 1, music.Restarts, "the audio reset did not restart the level loop at once");
            AssertLevelPlays(live, "after the device change");

            // The title loop was paused (faded out) when the reset stopped it: UnPause cannot resume a stopped source,
            // so the title page must still bring it back.
            Menu.ShowTitle();
            Assert.IsTrue(Menu.TitleOpen, "premise: the title opened");
            music.Tick(Tuning.MusicCrossfadeSeconds + 0.1f);
            Assert.IsTrue(music.TitleRunning, "the title loop does not start after an audio reset");
            if (live)
            {
                Assert.IsTrue(music.TitleSource.isPlaying, "the title source stays stopped after an audio reset");
            }
            Menu.Play();
            yield return Steps(3);
            music.Tick(Tuning.MusicCrossfadeSeconds + 0.1f);
            AssertLevelPlays(live, "back in the level");

            // The real thing when the run has an audio output: Unity's own reset stops the sources and calls the player.
            if (live)
            {
                restarts = music.Restarts;
                resets = music.AudioResets;
                bool reset = AudioSettings.Reset(AudioSettings.GetConfiguration());
                Debug.Log("[music test] AudioSettings.Reset: " + reset);
                if (reset)
                {
                    Assert.Greater(music.AudioResets, resets, "the player did not hear OnAudioConfigurationChanged");
                    music.Tick(0.01f);
                    music.Tick(Tuning.MusicWatchdogSeconds + 0.01f);
                    Assert.IsTrue(music.LevelSource.isPlaying, "the level loop stays stopped after AudioSettings.Reset");
                }
            }
            yield return null;
            AssertNoErrors();
        }

        // ----- 28mc: the loop wraps past its end -----

        [UnityTest]
        public IEnumerator Step28mc_LevelLoopWrapsPastItsEnd()
        {
            MusicPlayer music = Music;
            bool live = StartLevelLoop();
            AudioSource source = music.LevelSource;
            Assert.IsTrue(source.loop, "the level source does not loop");
            float length = source.clip.length;
            Assert.Greater(length, 30f, "premise: the level loop is too short");

            if (live)
            {
                // Seek just before the end and let the real audio run past it.
                source.time = length - 0.2f;
                float until = Time.realtimeSinceStartup + 1.5f;
                while (Time.realtimeSinceStartup < until)
                {
                    yield return null;
                }
                Assert.IsTrue(source.isPlaying, "the level loop stopped at its end instead of looping");
                Assert.Less(source.time, 2f, "the level loop did not wrap to its start");
            }

            // A loop whose source ended anyway (looping lost) restarts from its start, not from its last instant.
            source.loop = false;
            source.Stop();
            int restarts = music.Restarts;
            music.Tick(Tuning.MusicWatchdogSeconds + 0.01f);
            Assert.AreEqual(restarts + 1, music.Restarts, "the watchdog did not restart a loop that ended");
            Assert.IsTrue(source.loop, "the watchdog did not restore looping");
            Assert.Less(source.time, length - Tuning.MusicRestartTailSeconds, "the restart replays the end of the clip");
            AssertLevelPlays(live, "after the end");
            yield return null;
            AssertNoErrors();
        }

        // ----- 28md: restart, win, next level, focus: the music always comes back -----

        [UnityTest]
        public IEnumerator Step28md_MusicKeepsPlayingThroughRestartWinNextLevelAndFocus()
        {
            MusicPlayer music = Music;
            bool live = StartLevelLoop();

            // Restarts in a row.
            for (int i = 0; i < 3; i++)
            {
                Game.Restart();
                yield return Steps(2);
                music.Tick(Tuning.MusicReturnSeconds + 0.01f);
                Assert.AreEqual(PlayState.Playing, Game.State, "premise: the restart plays");
                AssertLevelPlays(live, "restart " + i);
            }

            // A win: silent for the jingle, then back under the end panel, then full on the next level.
            yield return Win();
            music.Tick(Tuning.MusicStingFadeSeconds + 0.01f);
            Assert.AreEqual(0f, music.Duck, 1e-4f, "the music plays over the win jingle");
            Assert.IsFalse(music.LevelRunning, "the silenced level loop was not paused");
            music.Tick(Tuning.MusicStingHoldSeconds);
            music.Tick(Tuning.MusicReturnSeconds + 0.01f);
            Assert.AreEqual(Tuning.MusicPauseDuck, music.Duck, 1e-4f, "the music never comes back under the end panel");
            AssertLevelPlays(live, "under the end panel");
            Game.NextLevel();
            yield return Steps(3);
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: the next level plays");
            music.Tick(Tuning.MusicReturnSeconds + 0.01f);
            Assert.AreEqual(1f, music.Duck, 1e-4f, "the music is not back to full on the next level");
            AssertLevelPlays(live, "next level");

            // A loop paused by the player and stopped behind its back meanwhile (UnPause is then a no-op): the watchdog
            // still brings it back after the title.
            Menu.ShowTitle();
            music.Tick(Tuning.MusicCrossfadeSeconds + 0.1f);
            Assert.IsFalse(music.LevelRunning, "premise: the level loop is paused under the title");
            music.LevelSource.Stop();
            Menu.Play();
            yield return Steps(3);
            int restarts = music.Restarts;
            music.Tick(Tuning.MusicCrossfadeSeconds + 0.1f);
            if (!music.LevelSource.isPlaying)
            {
                music.Tick(Tuning.MusicWatchdogSeconds + 0.01f);
                Assert.Greater(music.Restarts, restarts, "a stopped source resumed with UnPause stays silent");
            }
            AssertLevelPlays(live, "after the title");

            // Focus lost and regained (alt-tab, a phone call): checked at once, restarted when the OS stopped it.
            main.Music.SendMessage("OnApplicationFocus", false);
            music.LevelSource.Stop();
            restarts = music.Restarts;
            main.Music.SendMessage("OnApplicationFocus", true);
            music.Tick(0.01f);
            Assert.AreEqual(restarts + 1, music.Restarts, "the focus regain did not restart the stopped music");
            AssertLevelPlays(live, "after the focus regain");
            yield return null;
            AssertNoErrors();
        }
    }
}
