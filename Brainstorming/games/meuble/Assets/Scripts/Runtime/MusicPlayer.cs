using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// The music (audio overhaul, docs/audio/AUDIO_REPORT.md 5): two seamless loops of <see cref="AudioLibrary"/>, the title
    /// page's ("Sneaky Snitch") and the levels' ("Investigations"), both by Kevin MacLeod (CC BY 4.0, credited on the
    /// Credits page and at the bottom of the Options page). Built once by Main on its own child, with two 2D looping sources that never leave it (no GameObject is
    /// created afterwards, probe step 09).
    ///
    /// Every frame (unscaled time, so it runs under the paused title and the pause menu) it reads the menus and the game:
    /// <list type="bullet">
    /// <item>the title page (its level select and Options too) wants the title loop, anything else the level loop; the two
    /// crossfade over <see cref="Tuning.MusicCrossfadeSeconds"/>, and a loop faded out is paused where it was, so it
    /// resumes there instead of restarting;</item>
    /// <item>a catch or a win silences the level loop within <see cref="Tuning.MusicStingFadeSeconds"/>: the sting plays
    /// alone, readable; after <see cref="Tuning.MusicStingHoldSeconds"/> the loop comes back under the end panel at
    /// <see cref="Tuning.MusicPauseDuck"/>, and at full level over <see cref="Tuning.MusicReturnSeconds"/> on the retry or
    /// the next level;</item>
    /// <item>the pause menu ducks it to <see cref="Tuning.MusicPauseDuck"/> (the sources ignore AudioListener.pause, which
    /// pauses every game sound while the title or the pause menu is up).</item>
    /// </list>
    /// A loop's volume is its gain to the reference times its Tuning mix times the Music option times its crossfade times
    /// the duck. The Volume option is the listener's volume over everything, so it scales the music too, and
    /// <see cref="AudioMute"/> (tests, batch mode, -mute) silences it the same way. Tests read the volumes and the logical
    /// play state here, never isPlaying alone: batch mode may have no audio device.
    ///
    /// Watchdog (the "music stops and never comes back" bug): Unity stops every source behind the player's back when the
    /// audio system resets (an output device change such as plugging headphones, AudioSettings.Reset), and a mobile OS can
    /// do the same on a suspend or an audio focus loss. The player used to trust its own "running" flag and only called
    /// Play on a fade-in, so such a loop stayed silent until the next catch or title crossfade. Now a running loop that is
    /// not playing for <see cref="Tuning.MusicWatchdogSeconds"/> (at once after an audio reset or a focus regain) is
    /// restarted where it was last heard, from the start when it stopped at its end.
    /// </summary>
    public sealed class MusicPlayer : MonoBehaviour
    {
        public enum Track
        {
            None,
            Title,
            Level,
        }

        /// <summary>One loop's bookkeeping: its logical state and what the watchdog last heard of the real source.</summary>
        private sealed class Loop
        {
            /// <summary>Started and not paused by this player.</summary>
            public bool Running;

            /// <summary>Paused by this player (a fade-out): the next start resumes it with UnPause.</summary>
            public bool Held;

            /// <summary>The last position heard playing, in seconds.</summary>
            public float Position;

            /// <summary>Unscaled seconds the loop has been running without its source playing.</summary>
            public float Silent;

            /// <summary>An audio reset or a focus regain: verify the source on the next tick, no grace.</summary>
            public bool CheckNow;
        }

        private readonly Loop title = new Loop();
        private readonly Loop level = new Loop();

        /// <summary>Unscaled seconds since the game left Playing (a catch or a win), 0 in play.</summary>
        private float endSeconds;

        public AudioLibrary Library { get; private set; }
        public AudioSource TitleSource { get; private set; }
        public AudioSource LevelSource { get; private set; }

        /// <summary>The loop the game asks for now.</summary>
        public Track Wanted { get; private set; }

        /// <summary>Crossfade positions, 0 (silent, paused) to 1 (full).</summary>
        public float TitleFade { get; private set; }
        public float LevelFade { get; private set; }

        /// <summary>The duck applied to the level loop: 1 in play, <see cref="Tuning.MusicPauseDuck"/> paused, 0 caught or won.</summary>
        public float Duck { get; private set; } = 1f;

        /// <summary>The duck the game asks for now (<see cref="Duck"/> moves toward it).</summary>
        public float DuckTarget { get; private set; } = 1f;

        /// <summary>True while the loop is started and not paused by this player (tests: logical state, never isPlaying).</summary>
        public bool TitleRunning => title.Running;
        public bool LevelRunning => level.Running;

        /// <summary>How many times the watchdog restarted a loop that should have been playing (tests).</summary>
        public int Restarts { get; private set; }

        /// <summary>How many audio configuration changes (device switches, resets) this player handled (tests).</summary>
        public int AudioResets { get; private set; }

        /// <summary>The Music option as a factor (0 to 1).</summary>
        public static float OptionFactor => Mathf.Clamp01(SaveStore.Options.Music / 100f);

        public void Init(AudioLibrary library)
        {
            Library = library;
            TitleSource = NewSource(library != null && AudioLibrary.Has(library.musicTitle) ? library.musicTitle.clip : null);
            LevelSource = NewSource(library != null && AudioLibrary.Has(library.musicLevel) ? library.musicLevel.clip : null);
            Wanted = Track.None;
            TitleFade = 0f;
            LevelFade = 0f;
            Duck = 1f;
            DuckTarget = 1f;
        }

        private AudioSource NewSource(AudioClip clip)
        {
            AudioSource s = gameObject.AddComponent<AudioSource>();
            s.playOnAwake = false;
            s.loop = true;
            s.spatialBlend = 0f;
            s.volume = 0f;
            s.clip = clip;
            // Above every effect: the voice limit never culls the music.
            s.priority = 0;
            // The title page and the pause menu pause the listener; the music plays (ducked) under them.
            s.ignoreListenerPause = true;
            return s;
        }

        private void OnEnable()
        {
            AudioSettings.OnAudioConfigurationChanged += HandleAudioConfigurationChanged;
        }

        private void OnDisable()
        {
            AudioSettings.OnAudioConfigurationChanged -= HandleAudioConfigurationChanged;
        }

        private void OnApplicationFocus(bool focused)
        {
            if (focused)
            {
                CheckLoops();
            }
        }

        private void OnApplicationPause(bool paused)
        {
            if (!paused)
            {
                CheckLoops();
            }
        }

        /// <summary>
        /// AudioSettings.OnAudioConfigurationChanged: the audio system was reset (an output device change or a reset) and
        /// every source is stopped. The running loops are restarted on the next tick, the paused ones are restarted from
        /// their place when they fade back in (UnPause cannot resume a stopped source).
        /// </summary>
        public void HandleAudioConfigurationChanged(bool deviceWasChanged)
        {
            AudioResets++;
            title.Held = false;
            level.Held = false;
            CheckLoops();
        }

        /// <summary>Asks the watchdog to verify both loops on the next tick, without its grace delay.</summary>
        public void CheckLoops()
        {
            title.CheckNow = true;
            level.CheckNow = true;
        }

        private void Update()
        {
            Tick(Time.unscaledDeltaTime);
        }

        /// <summary>One update of <paramref name="dt"/> unscaled seconds: what the game wants, the fades, the volumes.</summary>
        public void Tick(float dt)
        {
            Main main = Main.Instance;
            Evaluate(main != null ? main.Game : null, main != null ? main.Menu : null, dt);
            float cross = Tuning.MusicCrossfadeSeconds > 0f ? dt / Tuning.MusicCrossfadeSeconds : 1f;
            TitleFade = Mathf.MoveTowards(TitleFade, Wanted == Track.Title ? 1f : 0f, cross);
            LevelFade = Mathf.MoveTowards(LevelFade, Wanted == Track.Level ? 1f : 0f, cross);
            float duckTime = DuckTarget < Duck ? Tuning.MusicStingFadeSeconds : Tuning.MusicReturnSeconds;
            Duck = Mathf.MoveTowards(Duck, DuckTarget, duckTime > 0f ? dt / duckTime : 1f);

            float option = OptionFactor;
            float titleVolume = VolumeOf(Library != null ? Library.musicTitle : null, Tuning.MusicTitleMix, option, TitleFade, 1f);
            float levelVolume = VolumeOf(Library != null ? Library.musicLevel : null, Tuning.MusicLevelMix, option, LevelFade, Duck);
            Apply(TitleSource, title, titleVolume, TitleFade, dt);
            Apply(LevelSource, level, levelVolume, LevelFade * Duck, dt);
        }

        /// <summary>
        /// The game's wish: the title loop while the title page is up (its select and Options included), else the level
        /// loop, ducked to silence on a catch or a win (back to <see cref="Tuning.MusicPauseDuck"/> under the end panel
        /// after <see cref="Tuning.MusicStingHoldSeconds"/>) and to <see cref="Tuning.MusicPauseDuck"/> under the pause
        /// menu. Nothing without a game (the loops fade out).
        /// </summary>
        private void Evaluate(GameState game, Menu menu, float dt)
        {
            if (game == null)
            {
                Wanted = Track.None;
                DuckTarget = 1f;
                endSeconds = 0f;
                return;
            }
            if (menu != null && menu.TitleOpen)
            {
                Wanted = Track.Title;
                DuckTarget = 1f;
                endSeconds = 0f;
                return;
            }
            Wanted = Track.Level;
            if (game.State != PlayState.Playing)
            {
                // The sting plays alone, then the loop comes back softly under the end panel: it never stays silent.
                endSeconds += dt;
                DuckTarget = endSeconds < Tuning.MusicStingHoldSeconds ? 0f : Tuning.MusicPauseDuck;
            }
            else
            {
                endSeconds = 0f;
                DuckTarget = menu != null && menu.PauseOpen ? Tuning.MusicPauseDuck : 1f;
            }
        }

        /// <summary>A loop's volume: its gain to the reference, its mix, the Music option, its crossfade and the duck.</summary>
        public static float VolumeOf(AudioLibrary.Entry entry, float mix, float option, float fade, float duck)
        {
            if (!AudioLibrary.Has(entry))
            {
                return 0f;
            }
            return Mathf.Clamp01(entry.gain * mix * option * fade * duck);
        }

        /// <summary>
        /// Sets the source's volume, starts or resumes it while <paramref name="audible"/> is above 0 and pauses it (keeping
        /// its place) once it reached 0. While it runs, the watchdog makes sure the real source plays.
        /// </summary>
        private void Apply(AudioSource source, Loop loop, float volume, float audible, float dt)
        {
            if (source == null || source.clip == null)
            {
                loop.Running = false;
                return;
            }
            source.volume = volume;
            if (audible > 0f && !loop.Running)
            {
                if (loop.Held)
                {
                    source.UnPause();
                }
                else
                {
                    PlayAt(source, loop.Position);
                }
                loop.Held = false;
                loop.Running = true;
                loop.Silent = 0f;
                return;
            }
            if (audible <= 0f && loop.Running)
            {
                if (source.isPlaying)
                {
                    loop.Position = source.time;
                }
                source.Pause();
                loop.Held = true;
                loop.Running = false;
                return;
            }
            if (loop.Running)
            {
                Watch(source, loop, dt);
            }
        }

        /// <summary>
        /// The watchdog of a running loop: it remembers where the source plays, and restarts it there when it stopped
        /// behind the player's back (an audio reset, a suspend, a stream that ended).
        /// </summary>
        private void Watch(AudioSource source, Loop loop, float dt)
        {
            if (!source.loop)
            {
                source.loop = true;
            }
            if (source.isPlaying)
            {
                loop.Position = source.time;
                loop.Silent = 0f;
                loop.CheckNow = false;
                return;
            }
            loop.Silent += dt;
            bool due = loop.CheckNow || loop.Silent >= Tuning.MusicWatchdogSeconds;
            if (due) // MUTATION:MUSIC_LOOP
            {
                PlayAt(source, loop.Position);
                loop.Silent = 0f;
                loop.CheckNow = false;
                Restarts++;
            }
        }

        /// <summary>
        /// Plays the source from <paramref name="position"/> seconds, from the start when that is at (or near) the clip's
        /// end, so a loop that stopped at its end starts over instead of replaying its last instant.
        /// </summary>
        private static void PlayAt(AudioSource source, float position)
        {
            source.Stop();
            source.Play();
            float length = source.clip.length;
            if (position > 0f && position < length - Tuning.MusicRestartTailSeconds)
            {
                source.time = position;
            }
        }
    }
}
