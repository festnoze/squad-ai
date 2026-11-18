using System;
using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Audio overhaul (docs/audio/AUDIO_REPORT.md), on the real Boot scene: the new recorded cues (win, wardrobe, menu
    /// selection, door, crash, topple, lamp, muffled hops), the music player (title and level loops, crossfade, the duck on a
    /// catch, a win and the pause menu, the Music option) and the Options page's Music row. Every assertion reads
    /// configuration, volumes and counters, never isPlaying: batch mode may have no audio device. Every test first asserts
    /// its premise (the library and its clips), so a stub returning null cannot pass. The music's fades are driven by
    /// MusicPlayer.Tick with explicit durations, never by waiting on rendered frames.
    /// </summary>
    public sealed class ProbeTestsAudioOverhaul
    {
        private int exceptions;
        private readonly List<string> logged = new List<string>();

        private Main main;
        private GameState Game => main.Game;
        private Sfx Sfx => main.Sfx;
        private MusicPlayer Music => main.Music;
        private Menu Menu => main.Menu;
        private FurnitureController Chair => Game.Furniture;
        private Inhabitant Habitant => Game.MainInhabitant;

        private static readonly Vector3 WindowSpot = new Vector3(0f, 0f, -2.3f);

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
            Assert.IsNotNull(Sfx, "Main built no Sfx");
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

        private AudioLibrary RequireLibrary()
        {
            AudioLibrary library = AudioLibrary.Load();
            Assert.IsNotNull(library, "premise: Resources/AudioLibrary.asset is missing (AudioLibraryBuilder.Build)");
            Assert.AreSame(library, Sfx.Library, "Sfx does not use the library");
            return library;
        }

        /// <summary>A role's volume is exactly gain * mix * scale and below 1 (never clamped).</summary>
        private static void AssertEffective(string role, AudioLibrary.Entry entry, float mix, float scale, float effective)
        {
            Assert.IsTrue(AudioLibrary.Has(entry), role + ": no clip");
            float expected = entry.gain * mix * scale;
            Assert.Less(expected, 1f, $"{role}: gain {entry.gain:0.000} * mix {mix:0.000} reaches 1, the volume would clamp");
            Assert.AreEqual(expected, effective, 1e-3f, role + ": the effective volume is not gain * mix");
        }

        // ----- 27i: the new recorded cues -----

        [UnityTest]
        public IEnumerator Step27i_NewCuesPlayTheirRecordings()
        {
            AudioLibrary library = RequireLibrary();
            Sfx sfx = Sfx;
            // One synchronous block: no fixed step runs between a call and its check.
            int wins = sfx.WinsPlayed;
            sfx.PlayWin();
            Assert.AreEqual(wins + 1, sfx.WinsPlayed, "win counter");
            Assert.AreSame(library.stingWin.clip, sfx.LastClip, "the win plays the pizzicato jingle");
            AssertEffective("stingWin", library.stingWin, Tuning.SfxWinMix, 1f, sfx.LastVolume);

            int opens = sfx.WardrobeOpensPlayed;
            int closes = sfx.WardrobeClosesPlayed;
            sfx.PlayWardrobe(0.2f, true);
            Assert.AreSame(library.wardrobeOpen.clip, sfx.LastClip, "wardrobe open");
            AssertEffective("wardrobeOpen", library.wardrobeOpen, Tuning.SfxWardrobeMix, 1f, sfx.LastVolume);
            sfx.PlayWardrobe(0.2f, false);
            Assert.AreSame(library.wardrobeClose.clip, sfx.LastClip, "wardrobe close");
            AssertEffective("wardrobeClose", library.wardrobeClose, Tuning.SfxWardrobeMix, 1f, sfx.LastVolume);
            Assert.AreEqual(opens + 1, sfx.WardrobeOpensPlayed);
            Assert.AreEqual(closes + 1, sfx.WardrobeClosesPlayed);

            sfx.PlayDoor(0f);
            Assert.AreSame(library.doorOpen.clip, sfx.LastClip, "the door plays its recording, not the synthesis");
            AssertEffective("doorOpen", library.doorOpen, Tuning.SfxDoorMix, 1f, sfx.LastVolume);
            sfx.PlayCrash(0f);
            Assert.AreSame(library.crash.clip, sfx.LastClip, "the crash plays its recording");
            AssertEffective("crash", library.crash, Tuning.SfxCrashMix, 1f, sfx.LastVolume);
            sfx.PlayTopple(0f, false);
            Assert.AreSame(library.topple.clip, sfx.LastClip, "the topple plays its recording");
            AssertEffective("topple", library.topple, Tuning.SfxToppleMix, 1f, sfx.LastVolume);
            sfx.PlayTopple(0f, true);
            AssertEffective("topple (soft)", library.topple, Tuning.SfxToppleMix, 0.35f, sfx.LastVolume);
            sfx.PlayClick(0f);
            Assert.AreSame(library.lampClick.clip, sfx.LastClip, "the lamp plays its recorded switch");
            AssertEffective("lampClick", library.lampClick, Tuning.SfxLampClickMix, 1f, sfx.LastVolume);

            // The selection tick never touches LastClip, and ignores the listener pause like the click.
            AudioClip last = sfx.LastClip;
            int hovers = sfx.UiHoversPlayed;
            AudioListener.pause = true;
            try
            {
                sfx.PlayUiHover();
            }
            finally
            {
                AudioListener.pause = false;
            }
            Assert.AreEqual(hovers + 1, sfx.UiHoversPlayed, "selection tick counter");
            Assert.AreSame(last, sfx.LastClip, "the selection tick changed LastClip");

            // Every menu button carries the selection tick.
            Assert.IsNotNull(Menu, "premise: Main built no Menu");
            Assert.IsNotNull(Menu.OptionsMusicButton, "premise: no Music row");
            Assert.IsTrue(Menu.OptionsMusicButton.TryGetComponent<UiHoverSound>(out _), "a menu button has no selection tick");

            // Without a library: the synthesis comes back, and the new events stay silent.
            var go = new GameObject("SfxWithoutLibrary");
            try
            {
                Sfx bare = go.AddComponent<Sfx>();
                bare.Init(null);
                bare.PlayDoor(0f);
                Assert.AreSame(bare.Door, bare.LastClip, "fallback door");
                bare.PlayCrash(0f);
                Assert.AreSame(bare.Crash, bare.LastClip, "fallback crash");
                bare.PlayTopple(0f, false);
                Assert.AreSame(bare.Topple, bare.LastClip, "fallback topple");
                bare.PlayClick(0f);
                Assert.AreSame(bare.Click, bare.LastClip, "fallback lamp click");
                bare.PlaySoftHop();
                Assert.AreSame(bare.Hop, bare.LastClip, "fallback soft hop");
                bare.PlayWin();
                bare.PlayWardrobe(0f, true);
                bare.PlayUiHover();
                Assert.AreEqual(0, bare.WinsPlayed + bare.WardrobeOpensPlayed + bare.UiHoversPlayed, "a new cue played without its recording");
            }
            finally
            {
                Object.Destroy(go);
            }
            yield return Steps(2);
            AssertNoErrors();
        }

        [UnityTest]
        public IEnumerator Step27j_AWinPlaysTheJingleAndSilencesTheMusic()
        {
            AudioLibrary library = RequireLibrary();
            Assert.IsNotNull(Music, "premise: Main built no MusicPlayer");
            Music.Tick(3f);
            Assert.AreEqual(MusicPlayer.Track.Level, Music.Wanted, "premise: a level wants the level loop");
            Assert.AreEqual(1f, Music.Duck, 1e-4f, "premise: the level loop is not ducked in play");
            int wins = Sfx.WinsPlayed;
            for (int i = 0; i < Game.Level.Inhabitants.Count; i++)
            {
                Game.Level.Inhabitants[i].Pin(new Vector3(90f + 5f * i, 0f, 90f), 0f);
            }
            yield return Steps(15);
            ZoneDef exit = Game.Def.Exit;
            Chair.Teleport(new Vector3(exit.X, 0f, exit.Z), Chair.Yaw);
            yield return Until(() => Game.State != PlayState.Playing, 20);
            Assert.AreEqual(PlayState.Won, Game.State, "premise: the level was not won");
            Assert.AreEqual(wins + 1, Sfx.WinsPlayed, "one win jingle per win");
            Assert.AreSame(library.stingWin.clip, Sfx.LastWinClip, "the win did not play the jingle");
            Music.Tick(Tuning.MusicStingFadeSeconds + 0.01f);
            Assert.AreEqual(0f, Music.Duck, 1e-4f, "the music still plays under the win jingle");
            Assert.AreEqual(0f, Music.LevelSource.volume, 1e-4f);
            Assert.IsFalse(Music.LevelRunning, "the silenced level loop was not paused");
            AssertNoErrors();
        }

        // ----- 28: the music -----

        [UnityTest]
        public IEnumerator Step28a_MusicLoopsAreStreamedStereoAndIgnoreThePause()
        {
            AudioLibrary library = RequireLibrary();
            Assert.IsNotNull(Music, "premise: Main built no MusicPlayer");
            Assert.AreSame(library, Music.Library);
            foreach (KeyValuePair<string, AudioLibrary.Entry> pair in library.MusicRoles())
            {
                Assert.IsTrue(AudioLibrary.Has(pair.Value), pair.Key + " has no clip");
                AudioClip clip = pair.Value.clip;
                Assert.AreEqual(2, clip.channels, pair.Key + " is not stereo");
                Assert.AreEqual(AudioClipLoadType.Streaming, clip.loadType, pair.Key + " is not streamed");
                Assert.Greater(clip.length, 30f, pair.Key + " is too short for a loop");
                Assert.That(pair.Value.loudness, Is.InRange(-24f, -14f), pair.Key + " has no measured loudness");
                Assert.AreEqual(AudioLibrary.GainFor(pair.Value.loudness), pair.Value.gain, 1e-4f, pair.Key + " gain");
            }
            Assert.AreSame(library.musicTitle.clip, Music.TitleSource.clip);
            Assert.AreSame(library.musicLevel.clip, Music.LevelSource.clip);
            foreach (AudioSource s in new[] { Music.TitleSource, Music.LevelSource })
            {
                Assert.IsTrue(s.loop, "a music source does not loop");
                Assert.AreEqual(0f, s.spatialBlend, "a music source is not 2D");
                Assert.IsFalse(s.playOnAwake);
                Assert.IsTrue(s.ignoreListenerPause, "the music must play under the paused title and pause menu");
                Assert.AreNotSame(Sfx.gameObject, s.gameObject, "the music sits on the Sfx object (step 27g forbids it)");
            }
            // The test run is muted (AudioMute): the listener volume is 0, so the music is silent too.
            Assert.IsTrue(AudioMute.Muted, "premise: tests run muted");
            Assert.AreEqual(0f, AudioListener.volume, 1e-6f, "the listener is not muted in a test run");
            int count = Music.GetComponents<AudioSource>().Length;
            Game.Restart();
            yield return Steps(3);
            Assert.AreEqual(count, Music.GetComponents<AudioSource>().Length, "a restart added music sources");
            AssertNoErrors();
        }

        [UnityTest]
        public IEnumerator Step28b_MusicFollowsTitleLevelCatchAndPause()
        {
            AudioLibrary library = RequireLibrary();
            MusicPlayer music = Music;
            Assert.IsNotNull(music, "premise: Main built no MusicPlayer");
            float option = SaveStore.Options.Music / 100f;
            Assert.AreEqual(Tuning.MusicDefault / 100f, option, 1e-4f, "premise: the default Music option");

            // In a level: the level loop at gain * mix * option.
            music.Tick(Tuning.MusicCrossfadeSeconds + 0.1f);
            Assert.AreEqual(MusicPlayer.Track.Level, music.Wanted);
            Assert.AreEqual(1f, music.LevelFade, 1e-4f);
            Assert.AreEqual(0f, music.TitleFade, 1e-4f);
            Assert.IsTrue(music.LevelRunning, "the level loop does not run in a level");
            Assert.IsFalse(music.TitleRunning, "the title loop runs in a level");
            float full = library.musicLevel.gain * Tuning.MusicLevelMix * option;
            Assert.AreEqual(full, music.LevelSource.volume, 1e-4f, "level loop volume");
            Assert.Less(full, 1f);

            // The pause menu ducks it.
            Menu.SetPaused(true);
            Assert.IsTrue(Menu.PauseOpen, "premise: the pause menu opened");
            music.Tick(Tuning.MusicStingFadeSeconds + 0.01f);
            Assert.AreEqual(Tuning.MusicPauseDuck, music.Duck, 1e-4f, "the pause menu does not duck the music");
            Assert.AreEqual(full * Tuning.MusicPauseDuck, music.LevelSource.volume, 1e-4f);
            Assert.IsTrue(music.LevelRunning, "the pause menu stopped the music");
            Menu.SetPaused(false);
            music.Tick(Tuning.MusicReturnSeconds + 0.01f);
            Assert.AreEqual(1f, music.Duck, 1e-4f, "the music did not come back after the pause");

            // The Music option scales it at once.
            SaveOptions o = SaveStore.Options;
            SaveStore.SetOptions(new SaveOptions { Sensitivity = o.Sensitivity, Volume = o.Volume, Music = 30, Cone = o.Cone });
            music.Tick(0.01f);
            Assert.AreEqual(library.musicLevel.gain * Tuning.MusicLevelMix * 0.3f, music.LevelSource.volume, 1e-4f, "Music 30 %");
            SaveStore.SetOptions(new SaveOptions { Sensitivity = o.Sensitivity, Volume = o.Volume, Music = 0, Cone = o.Cone });
            music.Tick(0.01f);
            Assert.AreEqual(0f, music.LevelSource.volume, 1e-6f, "Music 0 % is not silent");
            SaveStore.SetOptions(new SaveOptions { Sensitivity = o.Sensitivity, Volume = o.Volume, Music = Tuning.MusicDefault, Cone = o.Cone });
            music.Tick(0.01f);

            // The title page crossfades to the title loop, Jouer back to the level loop.
            Menu.ShowTitle();
            Assert.IsTrue(Menu.TitleOpen, "premise: the title opened");
            music.Tick(Tuning.MusicCrossfadeSeconds * 0.5f);
            Assert.Greater(music.TitleFade, 0f, "the crossfade did not start");
            Assert.Less(music.TitleFade, 1f, "the crossfade is a cut");
            Assert.IsTrue(music.TitleRunning && music.LevelRunning, "both loops run during the crossfade");
            music.Tick(Tuning.MusicCrossfadeSeconds);
            Assert.AreEqual(MusicPlayer.Track.Title, music.Wanted);
            Assert.AreEqual(1f, music.TitleFade, 1e-4f);
            Assert.AreEqual(0f, music.LevelFade, 1e-4f);
            Assert.IsFalse(music.LevelRunning, "the faded level loop was not paused");
            Assert.AreEqual(library.musicTitle.gain * Tuning.MusicTitleMix * option, music.TitleSource.volume, 1e-4f, "title loop volume");
            Menu.Play();
            yield return Steps(3);
            Assert.IsFalse(Menu.TitleOpen, "premise: Jouer closed the title");
            music.Tick(Tuning.MusicCrossfadeSeconds + 0.1f);
            Assert.AreEqual(MusicPlayer.Track.Level, music.Wanted);
            Assert.IsTrue(music.LevelRunning && !music.TitleRunning, "Jouer did not bring the level loop back");

            // A catch silences the level loop; the retry brings it back.
            Game.Rules = GameRules.M2;
            Habitant.Pin(WindowSpot, YawMath.YawOf(Chair.transform.position - WindowSpot));
            Chair.ScriptedDirection = Vector3.forward;
            yield return Until(() => Game.State != PlayState.Playing, 150);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Caught, Game.State, "premise: caught while seen moving");
            music.Tick(Tuning.MusicStingFadeSeconds + 0.01f);
            Assert.AreEqual(0f, music.Duck, 1e-4f, "the music plays over the caught sting");
            Assert.IsFalse(music.LevelRunning, "the silenced level loop was not paused");
            Game.Restart();
            yield return Steps(2);
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: the retry plays");
            music.Tick(Tuning.MusicReturnSeconds + 0.01f);
            Assert.AreEqual(1f, music.Duck, 1e-4f, "the music did not come back on the retry");
            Assert.IsTrue(music.LevelRunning);
            AssertNoErrors();
        }

        // ----- 28c: the Options page's Music row -----

        [UnityTest]
        public IEnumerator Step28c_OptionsMusicRowCyclesSavesAndFits()
        {
            Assert.IsNotNull(Menu, "premise: Main built no Menu");
            Button row = Menu.OptionsMusicButton;
            Assert.IsNotNull(row, "the Options page has no Music row");
            Assert.AreSame(row, Menu.OptionsVolumeButton.navigation.selectOnDown, "down from Volume is not Music");
            Assert.AreSame(Menu.OptionsConeButton, row.navigation.selectOnDown, "down from Music is not the cone row");
            Assert.IsNotNull(row.transform.Find("OptionsMusicIcon"), "the Music row has no icon");
            Assert.IsTrue(Menu.Labels.TryGetValue("OptionsMusicLabel", out Text label), "the Music row has no label");

            Menu.SetPaused(true);
            Menu.OpenOptions();
            Assert.IsTrue(Menu.OptionsOpen, "premise: Options opened from the pause menu");
            Assert.AreEqual(string.Format(Strings.OptionsMusic, Tuning.MusicDefault), label.text, "the row does not show the default");
            row.onClick.Invoke();
            Assert.AreEqual(Tuning.MusicDefault + Tuning.MusicStep, SaveStore.Options.Music, "a click did not step the Music option");
            Assert.AreEqual(string.Format(Strings.OptionsMusic, Tuning.MusicDefault + Tuning.MusicStep), label.text, "the row did not refresh");
            // The other rows keep the Music option (they rebuild SaveOptions).
            Menu.OptionsVolumeButton.onClick.Invoke();
            Assert.AreEqual(Tuning.MusicDefault + Tuning.MusicStep, SaveStore.Options.Music, "the Volume row reset the Music option");
            for (int i = 0; i < 20 && SaveStore.Options.Music != Tuning.MusicMax; i++)
            {
                row.onClick.Invoke();
            }
            row.onClick.Invoke();
            Assert.AreEqual(Tuning.MusicMin, SaveStore.Options.Music, "after 100 % the Music row does not wrap to 0 %");
            Assert.AreEqual("Musique : {0} %", Strings.Get("options.music", Strings.French), "French label");
            Assert.AreEqual("Music: {0}%", Strings.Get("options.music", Strings.English), "English label");

            // Nine rows: the last one (Retour) still clears the bottom of a 20:9 phone (966 reference units at match 0.5).
            var back = (RectTransform)Menu.OptionsBackButton.transform;
            float bottom = back.anchoredPosition.y - back.sizeDelta.y * back.pivot.y;
            Assert.Greater(bottom, -966f / 2f + 20f, "the Options page runs off the bottom of a 20:9 screen");
            var volume = (RectTransform)Menu.OptionsVolumeButton.transform;
            var music = (RectTransform)row.transform;
            Assert.GreaterOrEqual(volume.anchoredPosition.y - volume.sizeDelta.y * volume.pivot.y,
                music.anchoredPosition.y + music.sizeDelta.y * (1f - music.pivot.y), "the Volume and Music rows overlap");
            Menu.CloseOptions();
            Menu.SetPaused(false);
            yield return null;
            AssertNoErrors();
        }
    }
}
