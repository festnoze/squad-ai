using Meuble.Core;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// The sounds of the game (PRD 7.3).
    /// M1: hop tick, the "hm ?" telegraph and the caught sting. M2 (docs/CONTRACT_M2.md 7): the wood
    /// creak, the rising tension loop of the creak warning, the "hein ?" discovery sting and the
    /// put down thump, all synthesized at startup.
    ///
    /// M3 (docs/CONTRACT_M3.md 7): a recorded clip of <see cref="AudioLibrary"/> plays whenever the library has
    /// one for the role, and the synthesis otherwise. "hm ?", the tension loop and "hein ?" stay synthesized
    /// (see <see cref="UseRecordedHein"/>). New sounds: hop variants never repeated twice in a row, a chair leg
    /// scrape when the chair pivots on the spot or is picked up, a short creak when the creak warning starts,
    /// the footsteps of every inhabitant (<see cref="FootstepAudio"/>), a room tone loop, and the UI click.
    /// A recorded clip plays at its library gain (to the common loudness) times the role's mix level.
    ///
    /// Dedicated sources only: PlayClipAtPoint would spawn GameObjects and break the object count check of
    /// probe step 09. Tests read the counters and <see cref="LastClip"/>, never isPlaying: batch mode may
    /// have no audio device.
    ///
    /// M4 (docs/CONTRACT_M4.md 2, 3 and amendment 9.12): the stool's topple and its rattle loop (the tell), the lamp
    /// click, the office chair's roll and the pratfall, all synthesized (no AudioLibrary role).
    /// </summary>
    public sealed class Sfx : MonoBehaviour
    {
        private const int Rate = 44100;

        // The synthesized clips: what plays when the library has no recording for the role.
        public AudioClip Hop { get; private set; }
        public AudioClip Hm { get; private set; }
        public AudioClip Caught { get; private set; }
        public AudioClip Creak { get; private set; }
        public AudioClip Tension { get; private set; }
        public AudioClip Hein { get; private set; }
        public AudioClip Thump { get; private set; }
        public AudioClip UiClick { get; private set; }

        /// <summary>True while the creak warning tension loop plays (probe and tests).</summary>
        public bool TensionPlaying => tensionSource != null && tensionSource.isPlaying;

        /// <summary>Number of creaks played since startup (tests).</summary>
        public int CreaksPlayed { get; private set; }

        // ----- M3: recorded audio (tests read these) -----

        /// <summary>The recorded clips in use, or null when every sound is synthesized.</summary>
        public AudioLibrary Library { get; private set; }

        /// <summary>The clip of the last one-shot played by this component, and its volume.</summary>
        public AudioClip LastClip { get; private set; }
        public float LastVolume { get; private set; }

        public int HopsPlayed { get; private set; }

        /// <summary>Index in the library's hops of the last recorded hop, -1 before the first one.</summary>
        public int LastHopVariant { get; private set; } = -1;

        public int ScrapesPlayed { get; private set; }
        public int LastScrapeVariant { get; private set; } = -1;
        public float LastScrapeVolume { get; private set; }

        /// <summary>Short creaks played when a creak warning started.</summary>
        public int WarningCreaksPlayed { get; private set; }

        public int StingsPlayed { get; private set; }

        /// <summary>The clip of the last caught sting (tests: seen moving and suspicion get different stings).</summary>
        public AudioClip LastStingClip { get; private set; }
        public float LastStingVolume { get; private set; }
        public int UiClicksPlayed { get; private set; }

        /// <summary>FootstepAudio components added to inhabitant roots since startup.</summary>
        public int FootstepComponentsAdded { get; private set; }

        // ----- M4 (docs/CONTRACT_M4.md 2 and 3, amendment 9.12): synthesized only, AudioLibrary unchanged. -----

        /// <summary>The stool hits the floor: a wooden clatter with two bounces.</summary>
        public AudioClip Topple { get; private set; }

        /// <summary>The floor lamp's switch: a press and a release.</summary>
        public AudioClip Click { get; private set; }

        /// <summary>The office chair's casters: one short rumble per roll noise event.</summary>
        public AudioClip Roll { get; private set; }

        /// <summary>The stool's legs chattering while it is too fast (the tell), a seamless one second loop.</summary>
        public AudioClip Rattle { get; private set; }

        /// <summary>Sitting on nothing: a falling slide whistle, then the bump on the floor.</summary>
        public AudioClip Pratfall { get; private set; }

        public int TopplesPlayed { get; private set; }
        public int ClicksPlayed { get; private set; }
        public int RollsPlayed { get; private set; }
        public int PratfallsPlayed { get; private set; }

        /// <summary>True while the rattle loop is wanted (the stool's tell); tests read this, never isPlaying.</summary>
        public bool RattleActive { get; private set; }

        /// <summary>The 2D rattle loop source (paused with the AudioListener like every game sound).</summary>
        public AudioSource RattleSource { get; private set; }

        /// <summary>The 2D room tone loop, or null without a recording.</summary>
        public AudioSource RoomToneSource { get; private set; }

        /// <summary>The optional ticking clock layer, or null while it is off (<see cref="SetClockLayer"/>).</summary>
        public AudioSource ClockSource { get; private set; }

        /// <summary>The menu click source: it ignores AudioListener.pause, so menus click while the game is paused.</summary>
        public AudioSource UiSource { get; private set; }

        /// <summary>
        /// "hein ?" stays synthesized by default: it is the same voice as the synthesized "hm ?" telegraph, and
        /// vocal_huh is a high cartoon voice of unknown origin, gained +11.7 dB (docs/M3_AUDIO.md 2.8). Set true for
        /// the product owner's listening pass (and the volume test).
        /// </summary>
        public bool UseRecordedHein { get; set; }

        /// <summary>True when "hein ?" plays the recorded vocal_huh instead of the synthesized voice.</summary>
        public bool RecordedHein => UseRecordedHein && AudioLibrary.Has(Library != null ? Library.vocalHuh : null);

        // Hop on a silent floor (rug or soft room): a faint felt tap for the player, and no noise event.
        private const float SoftHopVolume = 0.25f;

        // Every partial of the tension loop is a whole number of cycles in this length: a seamless loop.
        private const float TensionLoopSeconds = 1f;

        // M4: the rattle loop; every tick decays well before the loop point, so the loop has no click.
        private const float RattleLoopSeconds = Tuning.SfxRattleLoopSeconds;

        // M4: a roll on a silent floor (rug or soft room) is a faint felt rumble for the player, like the soft hop.
        private const float SoftRollVolume = Tuning.SfxSoftRollVolume;

        // M4.1: a topple on a silent floor, muffled: quieter and lower (wanted in Tuning: SfxSoftToppleVolume 0.35,
        // SfxSoftTopplePitch 0.8).
        private const float SoftToppleVolume = 0.35f;
        private const float SoftTopplePitch = 0.8f;

        // M3.1: the whole mix sits 2.3 dB (1 / 1.3) under the M3 levels, so the loudest recorded role ("hein ?",
        // mix 1) never needs a volume above 1 and no volume is ever clamped. The synthesized cues take the same
        // scale, so their balance with the recordings holds.
        private const float MixScale = 1f / 1.3f;

        // Volumes of the synthesized clips: the M2 values times the mix scale.
        private const float HopSynthVolume = 0.32f * MixScale;
        private const float HmVolume = 0.55f * MixScale;
        private const float CaughtSynthVolume = 0.6f * MixScale;
        private const float CreakSynthVolume = 0.75f * MixScale;
        private const float HeinSynthVolume = 0.6f * MixScale;
        private const float ThumpSynthVolume = 0.6f * MixScale;
        private const float UiClickSynthVolume = 0.35f * MixScale;
        private const float TensionStartVolume = 0.12f * MixScale;
        private const float TensionEndVolume = 0.55f * MixScale;
        // M4 synthesized cues (wanted in Tuning, integrator): the topple as loud as the caught sting, the click and
        // the roll near the hop tick, the rattle a bed under the hops, the pratfall like the thump.
        private const float ToppleSynthVolume = Tuning.SfxToppleSynthVolume * MixScale;
        private const float ClickSynthVolume = Tuning.SfxClickSynthVolume * MixScale;
        private const float RollSynthVolume = Tuning.SfxRollSynthVolume * MixScale;
        private const float RattleSynthVolume = Tuning.SfxRattleSynthVolume * MixScale;
        private const float PratfallSynthVolume = Tuning.SfxPratfallSynthVolume * MixScale;

        // Mix levels of the recordings (at most 1, in Tuning), multiplied by each clip's gain to the common -20 dBFS
        // active RMS: the playback volume is exactly gain * mix, below 1 for every clip. Levels, like the
        // synthesis they replace: caught and creak about -20.3 dBFS, thump -20.8, the hop near -31.5 (a little
        // under the 45 ms tick it replaces, because a 0.25 s knock sounds louder at equal RMS).
        private const float HopMix = Tuning.SfxHopMix;
        private const float PivotScrapeMix = Tuning.SfxPivotScrapeMix;
        private const float PickUpScrapeMix = Tuning.SfxPickUpScrapeMix;
        private const float CreakMix = Tuning.SfxCreakMix;
        private const float WarningCreakMix = Tuning.SfxWarningCreakMix;
        private const float ThumpMix = Tuning.SfxThumpMix;
        private const float CaughtMix = Tuning.SfxCaughtMix;
        private const float HeinMix = Tuning.SfxHeinMix;
        private const float FootstepMix = Tuning.SfxFootstepMix;
        // The air vent bed at about -44 dBFS: heard in a quiet moment, never over a cue.
        private const float RoomToneMix = Tuning.SfxRoomToneMix;
        private const float ClockMix = Tuning.SfxClockMix;
        private const float UiClickMix = Tuning.SfxUiClickMix;

        // A hop taken while the chair turns hard on the spot (a reversal) is a leg scrape instead.
        private const float PivotYawRate = Tuning.SfxPivotYawRate;
        private const float PivotMaxSpeed = Tuning.SfxPivotMaxSpeed;

        // vocal_huh is a high cartoon voice (230 to 480 Hz): pitched down for an adult inhabitant.
        private const float RecordedHeinPitch = 0.75f;

        // The ticking clock competes with the hop and footstep cues (docs/M3_AUDIO.md 2.5): off until a level
        // names a room for it. static readonly, not const: no unreachable code warning.
        private static readonly bool ClockLayerAtStart = false;

        private AudioSource[] hopSources;
        private int nextHopSource;
        private AudioSource hmSource;
        private AudioSource stingSource;
        private AudioSource creakSource;
        private AudioSource warningSource;
        private AudioSource tensionSource;
        private AudioSource heinSource;
        private AudioSource thumpSource;
        private AudioSource scrapeSource;
        private AudioSource toppleSource;
        private AudioSource clickSource;
        private AudioSource rollSource;
        private AudioSource pratfallSource;
        private System.Random noise;
        private System.Random choice;
        private bool tensionWasActive;
        private bool wasCarried;
        private FurnitureController watchedFurniture;
        private int footstepSeed = 100;

        public void Init()
        {
            Init(AudioLibrary.Load());
        }

        /// <summary>Builds every source, with the recordings of <paramref name="library"/> where it has them (null: all synthesized).</summary>
        public void Init(AudioLibrary library)
        {
            Library = library;
            noise = new System.Random(1234);
            choice = new System.Random(4321);
            Hop = Synthesize("hop", 0.045f, HopSample);
            Hm = Synthesize("hm", 0.48f, HmSample);
            Caught = Synthesize("caught", 1.1f, CaughtSample);
            Creak = SynthesizeCreak("creak", 0.95f);
            Tension = Synthesize("tension", TensionLoopSeconds, TensionSample);
            Hein = Synthesize("hein", 0.42f, HeinSample);
            Thump = Synthesize("thump", 0.32f, ThumpSample);
            UiClick = Synthesize("ui click", 0.03f, UiClickSample);
            Topple = SynthesizeTopple("topple", 0.62f);
            Click = Synthesize("click", 0.09f, ClickSample);
            Roll = Synthesize("roll", 0.3f, RollSample);
            Rattle = SynthesizeRattle("rattle", RattleLoopSeconds);
            Pratfall = Synthesize("pratfall", 0.95f, PratfallSample);
            // Two hop sources in turn: a hop's pitch is set on a source whose previous hop has ended, so a
            // recorded tail (up to 0.3 s, hops every 0.22 s) is never re-pitched mid sound.
            hopSources = new[] { NewSource(1f), NewSource(1f) };
            hmSource = NewSource(1f);
            stingSource = NewSource(1f);
            creakSource = NewSource(1f);
            warningSource = NewSource(1f);
            tensionSource = NewSource(0f);
            tensionSource.clip = Tension;
            tensionSource.loop = true;
            heinSource = NewSource(1f);
            thumpSource = NewSource(1f);
            scrapeSource = NewSource(1f);
            toppleSource = NewSource(1f);
            clickSource = NewSource(1f);
            rollSource = NewSource(1f);
            pratfallSource = NewSource(1f);
            RattleSource = NewSource(0f);
            RattleSource.clip = Rattle;
            RattleSource.loop = true;
            UiSource = NewSource(1f);
            UiSource.ignoreListenerPause = true;
            RoomToneSource = NewLoop(Library != null ? Library.roomTone : null, RoomToneMix);
            SetClockLayer(ClockLayerAtStart);
        }

        /// <summary>Starts or stops the optional ticking clock layer (listening pass, tests). Adds no GameObject.</summary>
        public void SetClockLayer(bool on)
        {
            if (on && ClockSource == null)
            {
                ClockSource = NewLoop(Library != null ? Library.clockLoop : null, ClockMix);
            }
            else if (!on && ClockSource != null)
            {
                ClockSource.Stop();
                Destroy(ClockSource);
                ClockSource = null;
            }
        }

        private AudioSource NewSource(float volume)
        {
            AudioSource s = gameObject.AddComponent<AudioSource>();
            s.playOnAwake = false;
            s.spatialBlend = 0f;
            s.volume = volume;
            return s;
        }

        /// <summary>A 2D loop that starts at once (paused with the AudioListener like every game sound).</summary>
        private AudioSource NewLoop(AudioLibrary.Entry entry, float mix)
        {
            if (!AudioLibrary.Has(entry))
            {
                return null;
            }
            AudioSource s = NewSource(Mix(entry, mix));
            s.clip = entry.clip;
            s.loop = true;
            s.Play();
            return s;
        }

        /// <summary>
        /// A clip's playback volume: its gain to the common loudness times the role's mix level. Never clamped:
        /// every gain * mix stays below 1 (probe step 27h).
        /// </summary>
        internal static float Mix(AudioLibrary.Entry entry, float mix)
        {
            return entry.gain * mix;
        }

        /// <summary>A random variant index in [0, count), never <paramref name="last"/> when there is a choice.</summary>
        internal static int PickVariant(System.Random random, int count, int last)
        {
            if (count <= 1)
            {
                return 0;
            }
            if (last < 0 || last >= count)
            {
                return random.Next(count);
            }
            int v = random.Next(count - 1);
            return v >= last ? v + 1 : v; // MUTATION:VARIANT
        }

        /// <summary>True when a hop is taken pivoting on the spot (a hard turn at low speed): it then scrapes.</summary>
        public static bool IsPivot(float planarSpeed, float yawRate)
        {
            return Mathf.Abs(yawRate) >= PivotYawRate && planarSpeed <= PivotMaxSpeed;
        }

        private void Play(AudioSource source, AudioClip clip, float volume)
        {
            volume = Mathf.Clamp01(volume);
            source.PlayOneShot(clip, volume);
            LastClip = clip;
            LastVolume = volume;
        }

        private static GameState CurrentGame()
        {
            Main main = Main.Instance;
            return main != null ? main.Game : null;
        }

        private bool HasHops => Library != null && AudioLibrary.HasAll(Library.hops);
        private bool HasScrapes => Library != null && AudioLibrary.HasAll(Library.scrapes);
        private bool HasFootsteps => Library != null && AudioLibrary.HasAll(Library.footsteps);

        private AudioLibrary.Entry Recorded(System.Func<AudioLibrary, AudioLibrary.Entry> role)
        {
            if (Library == null)
            {
                return null;
            }
            AudioLibrary.Entry entry = role(Library);
            return AudioLibrary.Has(entry) ? entry : null;
        }

        // ----- Fixed step: footsteps and the pick up -----

        private void FixedUpdate()
        {
            if (GamePause.IsPaused)
            {
                return;
            }
            GameState game = CurrentGame();
            if (game == null || game.Level == null)
            {
                return;
            }
            EnsureFootsteps(game.Level);
            WatchCarry(game.Furniture);
        }

        /// <summary>
        /// Adds a <see cref="FootstepAudio"/> (and its 3D AudioSource) with AddComponent on every inhabitant root
        /// that lacks one. Runs on every fixed step, so a rebuilt level is covered on its first step.
        /// </summary>
        public void EnsureFootsteps(LevelInstance level)
        {
            if (level == null || !HasFootsteps)
            {
                return;
            }
            foreach (Inhabitant inhabitant in level.Inhabitants)
            {
                if (inhabitant != null && !inhabitant.TryGetComponent<FootstepAudio>(out _))
                {
                    inhabitant.gameObject.AddComponent<FootstepAudio>().Init(inhabitant, Library.footsteps, FootstepMix, footstepSeed++);
                    FootstepComponentsAdded++;
                }
            }
        }

        /// <summary>The inhabitant grabs the chair: its legs scrape as it leaves the floor (the put down thumps).</summary>
        private void WatchCarry(FurnitureController furniture)
        {
            bool carried = furniture != null && furniture.Carried;
            if (carried && !wasCarried && furniture == watchedFurniture)
            {
                PlayPickUpScrape();
            }
            wasCarried = carried;
            watchedFurniture = furniture;
        }

        // ----- Cues -----

        /// <summary>M3 (docs/CONTRACT_M3.md 6 and 7): the menu click, heard while the game is paused.</summary>
        public void PlayUiClick()
        {
            if (UiSource == null)
            {
                return;
            }
            AudioLibrary.Entry entry = Recorded(l => l.uiClick);
            if (entry != null)
            {
                Play(UiSource, entry.clip, Mix(entry, UiClickMix));
            }
            else
            {
                Play(UiSource, UiClick, UiClickSynthVolume);
            }
            UiClicksPlayed++;
        }

        public void PlayHop()
        {
            PlayHop(1f);
        }

        /// <summary>
        /// A hop at a volume scale (M2: muffled on a silent floor). M3: a recorded variant, never the one before,
        /// or a leg scrape when the chair pivots on the spot.
        /// </summary>
        public void PlayHop(float volumeScale)
        {
            if (hopSources == null)
            {
                return;
            }
            volumeScale = Mathf.Clamp01(volumeScale);
            GameState game = CurrentGame();
            FurnitureController furniture = game != null ? game.Furniture : null;
            if (HasScrapes && furniture != null && IsPivot(furniture.PlanarSpeed, furniture.YawRate))
            {
                PlayScrape(PivotScrapeMix, volumeScale);
                return;
            }
            AudioSource source = hopSources[nextHopSource];
            nextHopSource = (nextHopSource + 1) % hopSources.Length;
            source.pitch = 0.92f + (float)noise.NextDouble() * 0.16f;
            if (HasHops)
            {
                int v = PickVariant(choice, Library.hops.Length, LastHopVariant);
                LastHopVariant = v;
                AudioLibrary.Entry entry = Library.hops[v];
                // The gain already evens out the 4 dB spread of the files: the pitch varies, the level does not.
                Play(source, entry.clip, Mix(entry, HopMix) * volumeScale);
            }
            else
            {
                Play(source, Hop, HopSynthVolume * volumeScale);
            }
            HopsPlayed++;
        }

        public void PlaySoftHop()
        {
            PlayHop(SoftHopVolume);
        }

        /// <summary>The inhabitant grabs the chair: a leg scrape (called by the carry watch, and tests).</summary>
        public void PlayPickUpScrape()
        {
            if (HasScrapes && scrapeSource != null)
            {
                PlayScrape(PickUpScrapeMix, 1f);
            }
        }

        private void PlayScrape(float mix, float volumeScale)
        {
            int v = PickVariant(choice, Library.scrapes.Length, LastScrapeVariant);
            LastScrapeVariant = v;
            AudioLibrary.Entry entry = Library.scrapes[v];
            scrapeSource.pitch = 0.95f + (float)noise.NextDouble() * 0.1f;
            Play(scrapeSource, entry.clip, Mix(entry, mix) * volumeScale);
            LastScrapeVolume = LastVolume;
            ScrapesPlayed++;
        }

        /// <summary>The creak itself (PRD 4.6): loud, every inhabitant in range plausibly hears it.</summary>
        public void PlayCreak()
        {
            if (creakSource == null)
            {
                return;
            }
            creakSource.pitch = 0.95f + (float)noise.NextDouble() * 0.1f;
            AudioLibrary.Entry entry = Recorded(l => l.creakLong);
            if (entry != null)
            {
                Play(creakSource, entry.clip, Mix(entry, CreakMix));
            }
            else
            {
                Play(creakSource, Creak, CreakSynthVolume);
            }
            CreaksPlayed++;
        }

        /// <summary>
        /// Called on every fixed step: the tension loop plays while <paramref name="active"/>, its pitch and
        /// volume rising with <paramref name="progress"/> (0 at the start of the warning, 1 at the creak).
        /// M3: the warning starts with a short recorded creak, the chair beginning to strain.
        /// </summary>
        public void SetTension(bool active, float progress)
        {
            if (tensionSource == null)
            {
                return;
            }
            bool started = active && !tensionWasActive;
            tensionWasActive = active;
            if (!active)
            {
                if (tensionSource.isPlaying)
                {
                    tensionSource.Stop();
                }
                return;
            }
            if (started)
            {
                AudioLibrary.Entry entry = Recorded(l => l.creakShort);
                if (entry != null)
                {
                    warningSource.pitch = 0.95f + (float)noise.NextDouble() * 0.1f;
                    Play(warningSource, entry.clip, Mix(entry, WarningCreakMix));
                    WarningCreaksPlayed++;
                }
            }
            progress = Mathf.Clamp01(progress);
            tensionSource.pitch = Mathf.Lerp(0.8f, 1.75f, progress);
            tensionSource.volume = Mathf.Lerp(TensionStartVolume, TensionEndVolume, progress * progress);
            if (!tensionSource.isPlaying)
            {
                tensionSource.Play();
            }
        }

        /// <summary>The "hein ?" of a discovery, panned toward the inhabitant.</summary>
        public void PlayHein(float pan)
        {
            if (heinSource == null)
            {
                return;
            }
            heinSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
            if (RecordedHein)
            {
                heinSource.pitch = RecordedHeinPitch;
                Play(heinSource, Library.vocalHuh.clip, Mix(Library.vocalHuh, HeinMix));
            }
            else
            {
                heinSource.pitch = 1f;
                Play(heinSource, Hein, HeinSynthVolume);
            }
        }

        /// <summary>The furniture is put back on the floor.</summary>
        public void PlayThump(float pan)
        {
            if (thumpSource == null)
            {
                return;
            }
            thumpSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
            AudioLibrary.Entry entry = Recorded(l => l.thump);
            if (entry != null)
            {
                Play(thumpSource, entry.clip, Mix(entry, ThumpMix));
            }
            else
            {
                Play(thumpSource, Thump, ThumpSynthVolume);
            }
        }

        /// <summary>Plays the telegraph, panned toward the inhabitant as seen from the camera (always synthesized).</summary>
        public void PlayHm(float pan)
        {
            if (hmSource != null)
            {
                hmSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
                Play(hmSource, Hm, HmVolume);
            }
        }

        /// <summary>
        /// The caught sting. M3: the two note sax "wah... wah" when seen moving, and the full "wah wah wah waaah"
        /// when the household's suspicion ran out (the slow defeat gets the long one).
        /// </summary>
        public void PlayCaught()
        {
            if (stingSource == null)
            {
                return;
            }
            GameState game = CurrentGame();
            bool suspicion = game != null && game.LoseReason == LoseReason.Suspicion;
            AudioLibrary.Entry entry = (suspicion ? Recorded(l => l.stingCaughtLong) : null) ?? Recorded(l => l.stingCaught);
            if (entry != null)
            {
                Play(stingSource, entry.clip, Mix(entry, CaughtMix));
            }
            else
            {
                Play(stingSource, Caught, CaughtSynthVolume);
            }
            LastStingClip = LastClip;
            LastStingVolume = LastVolume;
            StingsPlayed++;
        }

        // ----- M4 cues (docs/CONTRACT_M4.md 2 and 3) -----

        /// <summary>The stool tips over and hits the floor, panned toward it.</summary>
        public void PlayTopple(float pan)
        {
            PlayTopple(pan, false);
        }

        /// <summary>
        /// M4.1 (CONTRACT_M4 10.6): on a rug or in a soft room the topple makes no noise event, so the player hears it
        /// muffled (lower and quieter), like the soft hop.
        /// </summary>
        public void PlayTopple(float pan, bool soft)
        {
            if (toppleSource == null)
            {
                return;
            }
            toppleSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
            toppleSource.pitch = (soft ? SoftTopplePitch : 0.95f) + (float)noise.NextDouble() * 0.1f;
            Play(toppleSource, Topple, ToppleSynthVolume * (soft ? SoftToppleVolume : 1f));
            TopplesPlayed++;
        }

        /// <summary>The floor lamp's switch, by the player or by an inhabitant switching it back on.</summary>
        public void PlayClick(float pan)
        {
            if (clickSource == null)
            {
                return;
            }
            clickSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
            Play(clickSource, Click, ClickSynthVolume);
            ClicksPlayed++;
        }

        /// <summary>One roll of the office chair's casters; muffled on a silent floor, where it makes no noise event.</summary>
        public void PlayRoll(bool silent)
        {
            if (rollSource == null)
            {
                return;
            }
            rollSource.pitch = 0.94f + (float)noise.NextDouble() * 0.12f;
            Play(rollSource, Roll, RollSynthVolume * (silent ? SoftRollVolume : 1f));
            RollsPlayed++;
        }

        /// <summary>An inhabitant sat on nothing: the comic fall (pillar 4), panned toward the inhabitant.</summary>
        public void PlayPratfall(float pan)
        {
            if (pratfallSource == null)
            {
                return;
            }
            pratfallSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
            Play(pratfallSource, Pratfall, PratfallSynthVolume);
            PratfallsPlayed++;
        }

        /// <summary>
        /// Called on every fixed step: the stool's rattle loop plays while <paramref name="active"/> (the tell, above
        /// the tip speed), louder with <paramref name="intensity"/> (0 to 1).
        /// </summary>
        public void SetRattle(bool active, float intensity)
        {
            RattleActive = active;
            if (RattleSource == null)
            {
                return;
            }
            if (!active)
            {
                if (RattleSource.isPlaying)
                {
                    RattleSource.Stop();
                }
                return;
            }
            float k = Mathf.Clamp01(intensity);
            RattleSource.volume = RattleSynthVolume * (0.6f + 0.4f * k);
            RattleSource.pitch = 0.9f + 0.25f * k;
            if (!RattleSource.isPlaying)
            {
                RattleSource.Play();
            }
        }

        private delegate float Generator(float t, float duration);

        private AudioClip Synthesize(string name, float duration, Generator generator)
        {
            int count = Mathf.CeilToInt(duration * Rate);
            var data = new float[count];
            for (int i = 0; i < count; i++)
            {
                data[i] = Mathf.Clamp(generator(i / (float)Rate, duration), -1f, 1f);
            }
            AudioClip clip = AudioClip.Create(name, count, 1, Rate, false);
            clip.SetData(data, 0);
            return clip;
        }

        // ----- M2 sounds -----

        /// <summary>
        /// Wood creak: a stick and slip pulse train (a slow, uneven rate, like a joint under load) exciting
        /// three damped wood resonances. It needs filter state, so it does not use <see cref="Generator"/>.
        /// </summary>
        private AudioClip SynthesizeCreak(string name, float duration)
        {
            int count = Mathf.CeilToInt(duration * Rate);
            var data = new float[count];
            float[] freqs = { 310f, 690f, 1450f };
            float[] damping = { 0.9965f, 0.9952f, 0.993f };
            float[] gains = { 1f, 0.6f, 0.3f };
            var y1 = new float[3];
            var y2 = new float[3];
            float phase = 0f;
            float peak = 1e-6f;
            for (int i = 0; i < count; i++)
            {
                float t = i / (float)Rate;
                float x = t / duration;
                // The slip rate swells from 25 to about 95 slips per second, then sags: a "crrreeak".
                float rate = 25f + 70f * Mathf.Sin(Mathf.PI * Mathf.Pow(x, 0.7f)) + 6f * Mathf.Sin(2f * Mathf.PI * 3.1f * t);
                phase += rate / Rate;
                float excitation = 0f;
                if (phase >= 1f)
                {
                    phase -= 1f;
                    excitation = 0.6f + 0.4f * (float)noise.NextDouble();
                }
                excitation += ((float)noise.NextDouble() * 2f - 1f) * 0.02f;
                float s = 0f;
                for (int k = 0; k < 3; k++)
                {
                    float w = 2f * Mathf.PI * freqs[k] * (1f + 0.05f * x) / Rate;
                    float r = damping[k];
                    float y = 2f * r * Mathf.Cos(w) * y1[k] - r * r * y2[k] + excitation;
                    y2[k] = y1[k];
                    y1[k] = y;
                    s += y * gains[k];
                }
                float env = Mathf.Clamp01(t / 0.03f) * Mathf.Clamp01((duration - t) / 0.15f);
                data[i] = s * env;
                peak = Mathf.Max(peak, Mathf.Abs(data[i]));
            }
            for (int i = 0; i < count; i++)
            {
                data[i] = Mathf.Clamp(data[i] / peak * 0.85f, -1f, 1f);
            }
            AudioClip clip = AudioClip.Create(name, count, 1, Rate, false);
            clip.SetData(data, 0);
            return clip;
        }

        /// <summary>Strained wood: a low bowed tone with a fast uneven tremolo and a rough noise edge.</summary>
        private float TensionSample(float t, float d)
        {
            // Whole numbers of cycles per second only: the 1 s loop has no click.
            float tone = Mathf.Sin(2f * Mathf.PI * 98f * t) * 0.5f + Mathf.Sin(2f * Mathf.PI * 196f * t) * 0.3f
                + Mathf.Sin(2f * Mathf.PI * 297f * t) * 0.18f + Mathf.Sin(2f * Mathf.PI * 411f * t) * 0.1f;
            float tremolo = 0.65f + 0.35f * Mathf.Sin(2f * Mathf.PI * 11f * t) * Mathf.Sin(2f * Mathf.PI * 3f * t);
            float grain = ((float)noise.NextDouble() * 2f - 1f) * 0.12f;
            return (tone * tremolo + grain) * 0.5f;
        }

        /// <summary>"hein ?": the hm voice, higher, more open and rising hard at the end, a surprised question.</summary>
        private float HeinSample(float t, float d)
        {
            float x = t / d;
            float pitch = 210f + 150f * Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((x - 0.25f) / 0.75f));
            float phase = 2f * Mathf.PI * pitch * t;
            float s = 0f;
            for (int k = 1; k <= 8; k++)
            {
                // An open nasal vowel: a formant around 550 Hz over a weaker one near 1 800 Hz.
                float f = pitch * k;
                float formant = Mathf.Exp(-Mathf.Pow((f - 550f) / 300f, 2f)) + 0.35f * Mathf.Exp(-Mathf.Pow((f - 1800f) / 500f, 2f)) + 0.08f;
                s += Mathf.Sin(phase * k) * formant / Mathf.Sqrt(k);
            }
            float attack = Mathf.Clamp01(t / 0.03f);
            float release = Mathf.Clamp01((d - t) / 0.08f);
            return s * 0.38f * attack * release;
        }

        /// <summary>Put down thump: a low falling thud with a short wood knock on top.</summary>
        private float ThumpSample(float t, float d)
        {
            float f = 95f * (1f - 0.35f * Mathf.Clamp01(t / 0.12f));
            float body = Mathf.Sin(2f * Mathf.PI * f * t) * Mathf.Exp(-t * 18f);
            float knock = Mathf.Sin(2f * Mathf.PI * 240f * t) * Mathf.Exp(-t * 45f) * 0.5f;
            float n = ((float)noise.NextDouble() * 2f - 1f) * Mathf.Exp(-t * 120f) * 0.35f;
            float attack = Mathf.Clamp01(t / 0.003f);
            return (body + knock + n) * 0.75f * attack;
        }

        /// <summary>The fallback menu click: a 30 ms bright blip.</summary>
        private float UiClickSample(float t, float d)
        {
            float env = Mathf.Exp(-t * 220f) * Mathf.Clamp01(t / 0.001f);
            float tone = Mathf.Sin(2f * Mathf.PI * 1750f * t) * 0.6f + Mathf.Sin(2f * Mathf.PI * 3100f * t) * 0.2f;
            return tone * env * 0.8f;
        }

        /// <summary>Wood tick: a short decaying click plus a pinch of noise.</summary>
        private float HopSample(float t, float d)
        {
            float env = Mathf.Exp(-t * 110f);
            float tone = Mathf.Sin(2f * Mathf.PI * 820f * t) * 0.6f + Mathf.Sin(2f * Mathf.PI * 1630f * t) * 0.25f;
            float n = ((float)noise.NextDouble() * 2f - 1f) * Mathf.Exp(-t * 400f);
            return (tone * env + n * 0.5f) * 0.8f;
        }

        /// <summary>A hummed "hm ?": a nasal tone whose pitch rises at the end, like a question.</summary>
        private float HmSample(float t, float d)
        {
            float x = t / d;
            float pitch = 150f + (x > 0.45f ? 70f * Mathf.SmoothStep(0f, 1f, (x - 0.45f) / 0.55f) : 0f);
            float vibrato = 1f + 0.012f * Mathf.Sin(2f * Mathf.PI * 5.5f * t);
            float phase = 2f * Mathf.PI * pitch * vibrato * t;
            float s = 0f;
            for (int k = 1; k <= 7; k++)
            {
                // A soft formant around 250 to 300 Hz gives the closed mouth "m" color.
                float f = pitch * k;
                float formant = Mathf.Exp(-Mathf.Pow((f - 280f) / 260f, 2f)) + 0.15f;
                s += Mathf.Sin(phase * k) * formant / k;
            }
            float attack = Mathf.Clamp01(t / 0.04f);
            float release = Mathf.Clamp01((d - t) / 0.1f);
            return s * 0.45f * attack * release;
        }

        /// <summary>A comic "wah wah": two descending muted brass notes, the second one sagging.</summary>
        private float CaughtSample(float t, float d)
        {
            float f;
            float local;
            float length;
            if (t < 0.34f)
            {
                f = 311f;
                local = t;
                length = 0.34f;
            }
            else
            {
                local = t - 0.34f;
                length = d - 0.34f;
                f = 262f * (1f - 0.12f * Mathf.Clamp01(local / length)) * (1f + 0.02f * Mathf.Sin(2f * Mathf.PI * 6f * local));
            }
            float phase = 2f * Mathf.PI * f * local;
            float s = 0f;
            for (int k = 1; k <= 9; k++)
            {
                s += Mathf.Sin(phase * k) / k * (k % 2 == 1 ? 1f : 0.6f);
            }
            float wah = 0.55f + 0.45f * Mathf.Sin(Mathf.PI * Mathf.Clamp01(local / length));
            float env = Mathf.Clamp01(local / 0.02f) * Mathf.Clamp01((length - local) / 0.08f);
            return s * 0.32f * wah * env;
        }

        // ----- M4 sounds -----

        // Filter state of the roll rumble, used only while it is synthesized.
        private float rollLowpass;

        /// <summary>
        /// The stool on the floor: the seat edge hits, then two smaller bounces and a leg clatter. Each impact is a
        /// low falling body, a bright wood knock and a noise click.
        /// </summary>
        private AudioClip SynthesizeTopple(string name, float duration)
        {
            int count = Mathf.CeilToInt(duration * Rate);
            var data = new float[count];
            float[] at = { 0f, 0.15f, 0.25f, 0.31f };
            float[] amp = { 1f, 0.5f, 0.28f, 0.16f };
            float peak = 1e-6f;
            for (int i = 0; i < count; i++)
            {
                float t = i / (float)Rate;
                float s = 0f;
                for (int k = 0; k < at.Length; k++)
                {
                    float local = t - at[k];
                    if (local < 0f)
                    {
                        continue;
                    }
                    float f = 150f * (1f - 0.2f * Mathf.Clamp01(local / 0.1f));
                    float body = Mathf.Sin(2f * Mathf.PI * f * local) * Mathf.Exp(-local * 22f);
                    float knock = Mathf.Sin(2f * Mathf.PI * (780f + 120f * k) * local) * Mathf.Exp(-local * 60f) * 0.6f;
                    float ring = Mathf.Sin(2f * Mathf.PI * 1650f * local) * Mathf.Exp(-local * 90f) * 0.25f;
                    float click = ((float)noise.NextDouble() * 2f - 1f) * Mathf.Exp(-local * 300f) * 0.5f;
                    s += amp[k] * (body + knock + ring + click) * Mathf.Clamp01(local / 0.002f);
                }
                data[i] = s * Mathf.Clamp01((duration - t) / 0.03f);
                peak = Mathf.Max(peak, Mathf.Abs(data[i]));
            }
            for (int i = 0; i < count; i++)
            {
                data[i] = Mathf.Clamp(data[i] / peak * 0.9f, -1f, 1f);
            }
            AudioClip clip = AudioClip.Create(name, count, 1, Rate, false);
            clip.SetData(data, 0);
            return clip;
        }

        /// <summary>
        /// The legs of a stool going too fast: wood taps every 40 to 70 ms, two legs at two pitches. The last tap ends
        /// well before the loop point, so the loop is seamless.
        /// </summary>
        private AudioClip SynthesizeRattle(string name, float duration)
        {
            int count = Mathf.CeilToInt(duration * Rate);
            var data = new float[count];
            var rng = new System.Random(77);
            int tapLength = Mathf.CeilToInt(0.025f * Rate);
            float tick = 0.01f;
            while (tick < duration - 0.03f)
            {
                float amp = 0.5f + 0.5f * (float)rng.NextDouble();
                float f = rng.Next(2) == 0 ? 1250f : 1580f;
                int start = Mathf.FloorToInt(tick * Rate);
                for (int i = start; i < count && i < start + tapLength; i++)
                {
                    float local = (i - start) / (float)Rate;
                    float tap = Mathf.Sin(2f * Mathf.PI * f * local) * Mathf.Exp(-local * 260f);
                    float knock = Mathf.Sin(2f * Mathf.PI * 420f * local) * Mathf.Exp(-local * 140f) * 0.5f;
                    float n = ((float)rng.NextDouble() * 2f - 1f) * Mathf.Exp(-local * 900f) * 0.4f;
                    data[i] += amp * (tap + knock + n);
                }
                tick += 0.04f + 0.03f * (float)rng.NextDouble();
            }
            float peak = 1e-6f;
            for (int i = 0; i < count; i++)
            {
                peak = Mathf.Max(peak, Mathf.Abs(data[i]));
            }
            for (int i = 0; i < count; i++)
            {
                data[i] = Mathf.Clamp(data[i] / peak * 0.8f, -1f, 1f);
            }
            AudioClip clip = AudioClip.Create(name, count, 1, Rate, false);
            clip.SetData(data, 0);
            return clip;
        }

        /// <summary>The lamp switch: a bright press, then a softer release 45 ms later.</summary>
        private float ClickSample(float t, float d)
        {
            float s = SwitchSnap(t) + 0.6f * SwitchSnap(t - 0.045f);
            return s * 0.7f * Mathf.Clamp01((d - t) / 0.01f);
        }

        private float SwitchSnap(float local)
        {
            if (local < 0f)
            {
                return 0f;
            }
            float tone = Mathf.Sin(2f * Mathf.PI * 2300f * local) * Mathf.Exp(-local * 400f) * 0.7f
                + Mathf.Sin(2f * Mathf.PI * 5200f * local) * Mathf.Exp(-local * 900f) * 0.4f;
            float n = ((float)noise.NextDouble() * 2f - 1f) * Mathf.Exp(-local * 1500f) * 0.6f;
            return tone + n;
        }

        /// <summary>Casters on a hard floor: low passed noise bumped by the wheel turns, over a soft low hum.</summary>
        private float RollSample(float t, float d)
        {
            if (t <= 0f)
            {
                rollLowpass = 0f;
            }
            float n = (float)noise.NextDouble() * 2f - 1f;
            rollLowpass += (n - rollLowpass) * 0.08f;
            float wheel = 0.6f + 0.4f * Mathf.Sin(2f * Mathf.PI * 23f * t);
            float hum = Mathf.Sin(2f * Mathf.PI * 70f * t) * 0.25f;
            float env = Mathf.Clamp01(t / 0.04f) * Mathf.Clamp01((d - t) / 0.08f);
            return (rollLowpass * 2.2f + hum) * wheel * env * 0.8f;
        }

        /// <summary>The pratfall: a slide whistle falling from about 1 150 to 360 Hz, then a heavy bump on the floor.</summary>
        private float PratfallSample(float t, float d)
        {
            float s = 0f;
            const float slide = 0.48f;
            if (t < slide)
            {
                // An exponential sweep, integrated analytically: f(t) = f0 exp(-k t).
                const float f0 = 1150f;
                const float k = 2.4f;
                float phase = 2f * Mathf.PI * f0 * (1f - Mathf.Exp(-k * t)) / k + 0.25f * Mathf.Sin(2f * Mathf.PI * 6f * t);
                float env = Mathf.Clamp01(t / 0.03f) * Mathf.Clamp01((slide - t) / 0.05f);
                s += (Mathf.Sin(phase) + 0.15f * Mathf.Sin(2f * phase)) * env * 0.45f;
            }
            float local = t - 0.5f;
            if (local >= 0f)
            {
                float f = 80f * (1f - 0.3f * Mathf.Clamp01(local / 0.15f));
                float body = Mathf.Sin(2f * Mathf.PI * f * local) * Mathf.Exp(-local * 12f);
                float knock = Mathf.Sin(2f * Mathf.PI * 190f * local) * Mathf.Exp(-local * 35f) * 0.5f;
                float n = ((float)noise.NextDouble() * 2f - 1f) * Mathf.Exp(-local * 90f) * 0.3f;
                s += (body + knock + n) * 0.8f * Mathf.Clamp01(local / 0.003f) * Mathf.Clamp01((d - t) / 0.05f);
            }
            return s;
        }
    }
}
