using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// The music (audio overhaul, docs/audio/AUDIO_REPORT.md 5): two seamless loops of <see cref="AudioLibrary"/>, the title
    /// page's ("Sneaky Snitch") and the levels' ("Investigations"), both by Kevin MacLeod (CC BY 4.0, credited at the
    /// bottom of the Options page). Built once by Main on its own child, with two 2D looping sources that never leave it (no GameObject is
    /// created afterwards, probe step 09).
    ///
    /// Every frame (unscaled time, so it runs under the paused title and the pause menu) it reads the menus and the game:
    /// <list type="bullet">
    /// <item>the title page (its level select and Options too) wants the title loop, anything else the level loop; the two
    /// crossfade over <see cref="Tuning.MusicCrossfadeSeconds"/>, and a loop faded out is paused where it was, so it
    /// resumes there instead of restarting;</item>
    /// <item>a catch or a win silences the level loop within <see cref="Tuning.MusicStingFadeSeconds"/>: the sting plays
    /// alone, readable; the music comes back over <see cref="Tuning.MusicReturnSeconds"/> on the retry or the next level;</item>
    /// <item>the pause menu ducks it to <see cref="Tuning.MusicPauseDuck"/> (the sources ignore AudioListener.pause, which
    /// pauses every game sound while the title or the pause menu is up).</item>
    /// </list>
    /// A loop's volume is its gain to the reference times its Tuning mix times the Music option times its crossfade times
    /// the duck. The Volume option is the listener's volume over everything, so it scales the music too, and
    /// <see cref="AudioMute"/> (tests, batch mode, -mute) silences it the same way. Tests read the volumes and the logical
    /// play state here, never isPlaying: batch mode may have no audio device.
    /// </summary>
    public sealed class MusicPlayer : MonoBehaviour
    {
        public enum Track
        {
            None,
            Title,
            Level,
        }

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
        public bool TitleRunning { get; private set; }
        public bool LevelRunning { get; private set; }

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

        private void Update()
        {
            Tick(Time.unscaledDeltaTime);
        }

        /// <summary>One update of <paramref name="dt"/> unscaled seconds: what the game wants, the fades, the volumes.</summary>
        public void Tick(float dt)
        {
            Main main = Main.Instance;
            Evaluate(main != null ? main.Game : null, main != null ? main.Menu : null);
            float cross = Tuning.MusicCrossfadeSeconds > 0f ? dt / Tuning.MusicCrossfadeSeconds : 1f;
            TitleFade = Mathf.MoveTowards(TitleFade, Wanted == Track.Title ? 1f : 0f, cross);
            LevelFade = Mathf.MoveTowards(LevelFade, Wanted == Track.Level ? 1f : 0f, cross);
            float duckTime = DuckTarget < Duck ? Tuning.MusicStingFadeSeconds : Tuning.MusicReturnSeconds;
            Duck = Mathf.MoveTowards(Duck, DuckTarget, duckTime > 0f ? dt / duckTime : 1f);

            float option = OptionFactor;
            float title = VolumeOf(Library != null ? Library.musicTitle : null, Tuning.MusicTitleMix, option, TitleFade, 1f);
            float level = VolumeOf(Library != null ? Library.musicLevel : null, Tuning.MusicLevelMix, option, LevelFade, Duck);
            TitleRunning = Apply(TitleSource, title, TitleFade, TitleRunning);
            LevelRunning = Apply(LevelSource, level, LevelFade * Duck, LevelRunning);
        }

        /// <summary>
        /// The game's wish: the title loop while the title page is up (its select and Options included), else the level
        /// loop, ducked to silence on a catch or a win and to <see cref="Tuning.MusicPauseDuck"/> under the pause menu.
        /// Nothing without a game (the loops fade out).
        /// </summary>
        private void Evaluate(GameState game, Menu menu)
        {
            if (game == null)
            {
                Wanted = Track.None;
                DuckTarget = 1f;
                return;
            }
            if (menu != null && menu.TitleOpen)
            {
                Wanted = Track.Title;
                DuckTarget = 1f;
                return;
            }
            Wanted = Track.Level;
            if (game.State != PlayState.Playing)
            {
                DuckTarget = 0f;
            }
            else
            {
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
        /// its place) once it reached 0. Returns the logical running state.
        /// </summary>
        private static bool Apply(AudioSource source, float volume, float audible, bool running)
        {
            if (source == null || source.clip == null)
            {
                return false;
            }
            source.volume = volume;
            if (audible > 0f && !running)
            {
                if (source.time > 0f)
                {
                    source.UnPause();
                }
                else
                {
                    source.Play();
                }
                return true;
            }
            if (audible <= 0f && running)
            {
                source.Pause();
                return false;
            }
            return running;
        }
    }
}
