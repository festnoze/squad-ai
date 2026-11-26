using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
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
    ///
    /// M5 (docs/CONTRACT_M5_v3.md 3 and 4): the door's swing (the latch, then the hinge), the dog's bark and the dog's
    /// sniff (its telegraph, in place of the human "hm ?"), all synthesized. The swing is a sound, not a noise event.
    ///
    /// M5 wave 5B (docs/CONTRACT_M5.md 4, 5 and 6): the robot vacuum's hum, a quiet 3D loop on every robot (an AudioSource
    /// added to the robot's own GameObject, like the footsteps: no GameObject is created), the fallen load's crash, the
    /// rocking chair's creak while it rocks and the robot's bump into the furniture, all synthesized.
    ///
    /// Audio overhaul (docs/audio/AUDIO_REPORT.md): every recording is loudness matched by tools/audio/audio_pipeline.py and
    /// played at its role's playback target (Tuning mixes). Recordings now replace the synthesized door swing, crash,
    /// topple and lamp click when the library has them (the synthesis stays the fallback), a hop on a rug plays its own
    /// muffled variants, and three silent events get a sound: the win (<see cref="PlayWin"/>), the wardrobe's doors
    /// (<see cref="PlayWardrobe"/>) and the menu selection (<see cref="PlayUiHover"/>). The music is <see cref="MusicPlayer"/>.
    ///
    /// STARSANIM (docs/next/progress/STARSANIM.md): the end screen's star chimes (<see cref="PlayStarChime"/>, rising, the
    /// third a chord) and the empty star's tick (<see cref="PlayStarDull"/>), synthesized at startup like the M2 to M5 cues.
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

        // ----- Audio overhaul (docs/audio/AUDIO_REPORT.md): new events (tests read these, never isPlaying) -----

        /// <summary>Menu selection ticks played (a new button selected).</summary>
        public int UiHoversPlayed { get; private set; }

        /// <summary>Win jingles played (one per win), and the clip of the last one.</summary>
        public int WinsPlayed { get; private set; }
        public AudioClip LastWinClip { get; private set; }

        /// <summary>Wardrobe door sounds played: the doors opening, and shutting.</summary>
        public int WardrobeOpensPlayed { get; private set; }
        public int WardrobeClosesPlayed { get; private set; }

        // ----- STARSANIM (docs/next/progress/STARSANIM.md): the end screen's star chimes, synthesized (no recording). -----

        /// <summary>The star chimes, one per star of the row, rising (G5, C6, E6); the third rings a full C major chord.</summary>
        public AudioClip[] StarChimes { get; private set; }

        /// <summary>The soft dull tick of a star left empty.</summary>
        public AudioClip StarDull { get; private set; }

        /// <summary>Star chimes and dull ticks played, the index of the last chime (-1 before any) and its volume (tests).</summary>
        public int StarChimesPlayed { get; private set; }
        public int StarDullsPlayed { get; private set; }
        public int LastStarChime { get; private set; } = -1;
        public float LastStarChimeVolume { get; private set; }

        /// <summary>Index in the library's softHops of the last muffled hop, -1 before the first one.</summary>
        public int LastSoftHopVariant { get; private set; } = -1;

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

        // ----- M5 (docs/CONTRACT_M5_v3.md 3 and 4): synthesized only, AudioLibrary unchanged. -----

        /// <summary>A door swings open: the latch clicks, then the hinge squeaks over the 0.6 s swing.</summary>
        public AudioClip Door { get; private set; }

        /// <summary>The dog barks: two short "wouf", the second lower.</summary>
        public AudioClip Bark { get; private set; }

        /// <summary>The dog's telegraph: two quick sniffs.</summary>
        public AudioClip Sniff { get; private set; }

        public int DoorsPlayed { get; private set; }
        public int BarksPlayed { get; private set; }
        public int SniffsPlayed { get; private set; }

        /// <summary>The pan of the last bark (tests: it comes from the dog's side).</summary>
        public float LastBarkPan { get; private set; }

        // ----- M5 wave 5B (docs/CONTRACT_M5.md 4, 5 and 6): synthesized only, AudioLibrary unchanged. -----

        /// <summary>The robot vacuum's hum: a motor drone with its brushes, a seamless one second loop (on the robot).</summary>
        public AudioClip Hum { get; private set; }

        /// <summary>
        /// The hum loop's length, seconds (the synthesized clip is exactly this long). Levels v2 C8: the robot's hum disc
        /// (Robot.HumDisc) pulses once per loop.
        /// </summary>
        public const float HumLoopSeconds = 1f;

        /// <summary>The fallen load: a dull knock on the floor, then breaking china and scattering shards.</summary>
        public AudioClip Crash { get; private set; }

        /// <summary>The rocking chair rocks: two soft creaks of its runners, forward and back, over the 0.8 s rock.</summary>
        public AudioClip RockCreak { get; private set; }

        /// <summary>The careful rock (RockCarefulTime, 0.4 s): the same two creaks, over the shorter rock.</summary>
        public AudioClip RockCreakCareful { get; private set; }

        /// <summary>The clip of the last rock creak played (tests: the careful rock plays the careful clip).</summary>
        public AudioClip LastRockCreak { get; private set; }

        public int CrashesPlayed { get; private set; }
        public int RockCreaksPlayed { get; private set; }
        public int BumpsPlayed { get; private set; }

        /// <summary>The pan of the last crash (tests: it comes from the clue's side).</summary>
        public float LastCrashPan { get; private set; }

        /// <summary>Hum sources added to robots since startup (one per robot of each built level).</summary>
        public int HumSourcesAdded { get; private set; }

        /// <summary>
        /// The hum's volume for a furniture <paramref name="distance"/> metres from the robot (planar): full within
        /// SfxHumMinDistance, falling linearly to silence at SfxHumMaxDistance. The hum is what the furniture hears, so it
        /// follows the furniture, never the camera. Levels v2 C8: SfxHumMaxDistance is 3.5 m (it was 7 m), so the hum fades
        /// out just past the 2.5 m within which it masks noises (Tuning.RobotHumRadius, the hum disc): the ear and the rule agree.
        /// </summary>
        public static float HumVolumeAt(float distance)
        {
            float fade = Mathf.InverseLerp(Tuning.SfxHumMinDistance, Tuning.SfxHumMaxDistance, distance); // MUTATION:HUM_AUDIO_RANGE
            return HumVolume * (1f - fade);
        }

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
        // Audio overhaul, Request 2 (docs/audio/AUDIO_REPORT.md 4): an additional -4 dB (/ 1.585, 10^0.2), matching the
        // same cut applied to every Tuning.SfxXxxMix: every synthesized-only cue (the roll, the rattle, the pratfall, the
        // bark, the sniff, the hum, the rock creak, the bump) and every library-less fallback moves down with the rest of
        // the effects, music untouched.
        private const float MixScale = 1f / 1.3f / 1.585f;

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
        // M5 synthesized cues: the door near the thump, the bark as loud as the caught sting (it is the dog's alarm), the
        // sniff a little under the "hm ?" it replaces.
        private const float DoorSynthVolume = Tuning.SfxDoorSynthVolume * MixScale;
        private const float BarkSynthVolume = Tuning.SfxBarkSynthVolume * MixScale;
        private const float SniffSynthVolume = Tuning.SfxSniffSynthVolume * MixScale;
        // M5 wave 5B: the hum a quiet bed near the robot, the crash as loud as the caught sting (heard 6 m away), the rock
        // creak under the creak, the bump under the put-down thump (it reuses the thump, higher).
        private const float HumVolume = Tuning.SfxHumVolume * MixScale;
        private const float CrashSynthVolume = Tuning.SfxCrashSynthVolume * MixScale;
        private const float RockCreakSynthVolume = Tuning.SfxRockCreakSynthVolume * MixScale;
        private const float BumpSynthVolume = Tuning.SfxBumpSynthVolume * MixScale;
        private const float BumpPitch = 1.45f;
        // STARSANIM: the star chimes a little under the win jingle they follow, the third louder, the empty star's tick soft.
        private const float StarChimeVolume = Tuning.SfxStarChimeVolume * MixScale;
        private const float StarChimeFinalVolume = Tuning.SfxStarChimeFinalVolume * MixScale;
        private const float StarDullVolume = Tuning.SfxStarDullVolume * MixScale;
        private const float StarChimeSeconds = 0.9f;
        private const float StarFinalSeconds = 1.4f;
        // Each chime's notes as (frequency Hz, delay s, gain) triples: G5, then C6, then a rolled C major chord led by E6
        // (E6, C6, G6, C7), so the three stars climb G, C, E and the last one lands on the full chord.
        private static readonly float[] StarNote1 = { 783.99f, 0f, 1f };
        private static readonly float[] StarNote2 = { 1046.5f, 0f, 1f };
        private static readonly float[] StarChord = { 1318.51f, 0f, 1f, 1046.5f, 0.02f, 0.55f, 1567.98f, 0.045f, 0.6f, 2093f, 0.08f, 0.45f };

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
        // Audio overhaul: the new recorded roles (playback targets in Tuning).
        private const float SoftHopMix = Tuning.SfxSoftHopMix;
        private const float UiHoverMix = Tuning.SfxUiHoverMix;
        private const float WinMix = Tuning.SfxWinMix;
        private const float DoorMix = Tuning.SfxDoorMix;
        private const float WardrobeMix = Tuning.SfxWardrobeMix;
        private const float CrashMix = Tuning.SfxCrashMix;
        private const float ToppleMix = Tuning.SfxToppleMix;
        private const float LampClickMix = Tuning.SfxLampClickMix;
        private const float PitchJitter = Tuning.SfxPitchJitter;

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
        private AudioSource doorSource;
        private AudioSource barkSource;
        private AudioSource sniffSource;
        private AudioSource crashSource;
        private AudioSource rockSource;
        private AudioSource bumpSource;
        private AudioSource wardrobeSource;
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
            Door = SynthesizeDoor("door", Tuning.DoorOpenTime + 0.15f);
            Bark = Synthesize("bark", 0.52f, BarkSample);
            Sniff = Synthesize("sniff", 0.3f, SniffSample);
            Hum = SynthesizeHum("hum", HumLoopSeconds);
            Crash = SynthesizeCrash("crash", 0.9f);
            RockCreak = SynthesizeRockCreak("rock creak", Tuning.RockTime);
            RockCreakCareful = SynthesizeRockCreak("rock creak careful", Tuning.RockCarefulTime);
            // STARSANIM: the star chimes (a glockenspiel bar each, rising) and the empty star's tick.
            StarChimes = new[]
            {
                SynthesizeChime("star chime 1", StarChimeSeconds, StarNote1),
                SynthesizeChime("star chime 2", StarChimeSeconds, StarNote2),
                SynthesizeChime("star chime 3", StarFinalSeconds, StarChord),
            };
            StarDull = Synthesize("star dull", 0.14f, StarDullSample);
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
            doorSource = NewSource(1f);
            barkSource = NewSource(1f);
            sniffSource = NewSource(1f);
            crashSource = NewSource(1f);
            rockSource = NewSource(1f);
            bumpSource = NewSource(1f);
            bumpSource.pitch = BumpPitch;
            wardrobeSource = NewSource(1f);
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
        private bool HasSoftHops => Library != null && AudioLibrary.HasAll(Library.softHops);
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
            EnsureRobotHums(game.Level);
            UpdateRobotHums(game);
            WatchCarry(game.Furniture);
        }

        /// <summary>
        /// M5 wave 5B (CONTRACT_M5 4): adds the hum, an AudioSource looping <see cref="Hum"/>, to every robot of the level
        /// that lacks one (AddComponent on the robot's own GameObject: no GameObject is created). It runs on every fixed step,
        /// so the robots of a rebuilt level hum from its first step; it pauses with the AudioListener like every game sound.
        /// M5 5B.1: the source is 2D; <see cref="UpdateRobotHums"/> sets its volume from the furniture's distance to the robot
        /// (<see cref="HumVolumeAt"/>) and pans it toward the robot.
        /// </summary>
        public void EnsureRobotHums(LevelInstance level)
        {
            if (level == null || Hum == null)
            {
                return;
            }
            foreach (Component robot in level.Robots)
            {
                if (robot == null || robot.TryGetComponent<AudioSource>(out _))
                {
                    continue;
                }
                AudioSource s = robot.gameObject.AddComponent<AudioSource>();
                s.playOnAwake = false;
                s.clip = Hum;
                s.loop = true;
                s.volume = 0f;
                s.spatialBlend = 0f;
                s.dopplerLevel = 0f;
                // C8: the source's own rolloff states the same range as HumVolumeAt (the volume is set by hand: 2D source).
                s.rolloffMode = AudioRolloffMode.Linear;
                s.minDistance = Tuning.SfxHumMinDistance;
                s.maxDistance = Tuning.SfxHumMaxDistance;
                s.Play();
                HumSourcesAdded++;
            }
        }

        /// <summary>
        /// Every fixed step: each robot's hum at <see cref="HumVolumeAt"/> of the player furniture's planar distance to it,
        /// panned toward the robot from the camera. Silent without a player furniture.
        /// </summary>
        public void UpdateRobotHums(GameState game)
        {
            if (game == null || game.Level == null)
            {
                return;
            }
            FurnitureController furniture = game.Furniture;
            Transform view = game.Camera != null ? game.Camera.transform : null;
            foreach (Component robot in game.Level.Robots)
            {
                AudioSource s = HumOf(robot);
                if (s == null)
                {
                    continue;
                }
                Vector3 at = robot.transform.position;
                s.volume = furniture != null ? HumVolumeAt(YawMath.Planar(at - furniture.transform.position).magnitude) : 0f;
                if (view != null)
                {
                    Vector3 local = view.InverseTransformPoint(at);
                    s.panStereo = Mathf.Clamp(local.x / Mathf.Max(1f, local.magnitude), -0.8f, 0.8f);
                }
            }
        }

        /// <summary>The hum source of a robot (its 3D AudioSource), or null before the first fixed step of its level.</summary>
        public static AudioSource HumOf(Component robot)
        {
            return robot != null && robot.TryGetComponent(out AudioSource s) ? s : null;
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

        /// <summary>
        /// Audio overhaul: the menu's selection tick (a new button selected by the mouse, the arrows or the D-pad), heard
        /// while the game is paused like the click. Silent without its recording (no synthesized fallback). It never
        /// sets <see cref="LastClip"/>, so a selection change between a test's call and its check cannot change it.
        /// </summary>
        public void PlayUiHover()
        {
            AudioLibrary.Entry entry = Recorded(l => l.uiHover);
            if (UiSource == null || entry == null)
            {
                return;
            }
            UiSource.PlayOneShot(entry.clip, Mathf.Clamp01(Mix(entry, UiHoverMix)));
            UiHoversPlayed++;
        }

        /// <summary>
        /// Audio overhaul: the win, a rising pizzicato jingle on the sting source (the music fades out under it,
        /// <see cref="MusicPlayer"/>). Silent without its recording.
        /// </summary>
        public void PlayWin()
        {
            AudioLibrary.Entry entry = Recorded(l => l.stingWin);
            if (stingSource == null || entry == null)
            {
                return;
            }
            Play(stingSource, entry.clip, Mix(entry, WinMix));
            LastWinClip = entry.clip;
            WinsPlayed++;
        }

        /// <summary>
        /// STARSANIM (docs/next/progress/STARSANIM.md): the chime of star <paramref name="index"/> (0, 1, 2) filling on the end
        /// screen, each higher than the one before, the third a fuller chord. On the menu click's source (<see cref="UiSource"/>,
        /// one shots overlap, so a chime rings on under the next), heard at the options' volume and silent while
        /// <see cref="AudioMute"/> mutes the listener. Never sets <see cref="LastClip"/>, like <see cref="PlayUiHover"/>.
        /// </summary>
        public void PlayStarChime(int index)
        {
            if (UiSource == null || StarChimes == null || StarChimes.Length == 0)
            {
                return;
            }
            int i = Mathf.Clamp(index, 0, StarChimes.Length - 1);
            float volume = (i == StarChimes.Length - 1 ? StarChimeFinalVolume : StarChimeVolume);
            UiSource.PlayOneShot(StarChimes[i], Mathf.Clamp01(volume));
            LastStarChime = i;
            LastStarChimeVolume = volume;
            StarChimesPlayed++;
        }

        /// <summary>STARSANIM: the soft dull tick of a star left empty (same source and rules as <see cref="PlayStarChime"/>).</summary>
        public void PlayStarDull()
        {
            if (UiSource == null || StarDull == null)
            {
                return;
            }
            UiSource.PlayOneShot(StarDull, Mathf.Clamp01(StarDullVolume));
            StarDullsPlayed++;
        }

        /// <summary>
        /// Audio overhaul: the wardrobe's doors, panned toward the furniture: <paramref name="open"/> as they swing open at the
        /// start of the entry or exit action, then shut at its end. Silent without the recordings.
        /// </summary>
        public void PlayWardrobe(float pan, bool open)
        {
            AudioLibrary.Entry entry = Recorded(open ? (System.Func<AudioLibrary, AudioLibrary.Entry>)(l => l.wardrobeOpen) : l => l.wardrobeClose);
            if (wardrobeSource == null || entry == null)
            {
                return;
            }
            wardrobeSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
            wardrobeSource.pitch = Jitter();
            Play(wardrobeSource, entry.clip, Mix(entry, WardrobeMix));
            if (open)
            {
                WardrobeOpensPlayed++;
            }
            else
            {
                WardrobeClosesPlayed++;
            }
        }

        /// <summary>A pitch around 1 (+- <see cref="PitchJitter"/>) for a recording without variants.</summary>
        private float Jitter()
        {
            return 1f + PitchJitter * (2f * (float)noise.NextDouble() - 1f);
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

        /// <summary>
        /// A hop on a silent floor (a rug, a soft room) or masked by a robot: the muffled recorded variants at their own
        /// mix (audio overhaul), never the one before; a pivot there scrapes at a quarter. Without the muffled recordings,
        /// the hard hop at a quarter of its volume (M2).
        /// </summary>
        public void PlaySoftHop()
        {
            if (!HasSoftHops || hopSources == null)
            {
                PlayHop(SoftHopVolume);
                return;
            }
            GameState game = CurrentGame();
            FurnitureController furniture = game != null ? game.Furniture : null;
            if (HasScrapes && furniture != null && IsPivot(furniture.PlanarSpeed, furniture.YawRate))
            {
                PlayScrape(PivotScrapeMix, SoftHopVolume);
                return;
            }
            AudioSource source = hopSources[nextHopSource];
            nextHopSource = (nextHopSource + 1) % hopSources.Length;
            source.pitch = 0.92f + (float)noise.NextDouble() * 0.16f;
            int v = PickVariant(choice, Library.softHops.Length, LastSoftHopVariant);
            LastSoftHopVariant = v;
            AudioLibrary.Entry entry = Library.softHops[v];
            Play(source, entry.clip, Mix(entry, SoftHopMix));
            HopsPlayed++;
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
            if (heinSource == null || !Tuning.SfxHeinEnabled)
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
            if (hmSource != null && Tuning.SfxHmEnabled)
            {
                hmSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
                Play(hmSource, Hm, HmVolume);
            }
        }

        /// <summary>
        /// The caught sting. M3: a short sting when seen moving, and the long "wah wah wah waaah" when the household's
        /// suspicion ran out (the slow defeat gets the long one). SOUNDS (2026-11-24): both made for the game by
        /// tools/audio/make_sounds.py, a brass stab and a marimba run for the short one, a muted brass for the long one.
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
            // Audio overhaul: the recorded wooden fall when there is one, muffled the same way on a silent floor.
            AudioLibrary.Entry entry = Recorded(l => l.topple);
            float scale = soft ? SoftToppleVolume : 1f;
            Play(toppleSource, entry != null ? entry.clip : Topple, (entry != null ? Mix(entry, ToppleMix) : ToppleSynthVolume) * scale);
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
            // Audio overhaul: the recorded switch when there is one.
            AudioLibrary.Entry entry = Recorded(l => l.lampClick);
            if (entry != null)
            {
                clickSource.pitch = Jitter();
                Play(clickSource, entry.clip, Mix(entry, LampClickMix));
            }
            else
            {
                clickSource.pitch = 1f;
                Play(clickSource, Click, ClickSynthVolume);
            }
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

        // ----- M5 cues (docs/CONTRACT_M5_v3.md 3 and 4) -----

        /// <summary>A door leaf starts its swing (the player pressed E in reach), panned toward the door.</summary>
        public void PlayDoor(float pan)
        {
            if (doorSource == null)
            {
                return;
            }
            doorSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
            doorSource.pitch = 0.96f + (float)noise.NextDouble() * 0.08f;
            // Audio overhaul: the recorded wooden door when there is one.
            AudioLibrary.Entry entry = Recorded(l => l.doorOpen);
            Play(doorSource, entry != null ? entry.clip : Door, entry != null ? Mix(entry, DoorMix) : DoorSynthVolume);
            DoorsPlayed++;
        }

        /// <summary>The dog barks (it saw the furniture move), panned toward the dog.</summary>
        public void PlayBark(float pan)
        {
            if (barkSource == null)
            {
                return;
            }
            LastBarkPan = Mathf.Clamp(pan, -0.8f, 0.8f);
            barkSource.panStereo = LastBarkPan;
            barkSource.pitch = 0.95f + (float)noise.NextDouble() * 0.1f;
            Play(barkSource, Bark, BarkSynthVolume);
            BarksPlayed++;
        }

        /// <summary>The dog's telegraph (a wake or a turn over 30 deg): two quick sniffs, panned toward the dog.</summary>
        public void PlaySniff(float pan)
        {
            if (sniffSource == null)
            {
                return;
            }
            sniffSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
            Play(sniffSource, Sniff, SniffSynthVolume);
            SniffsPlayed++;
        }

        // ----- M5 wave 5B cues (docs/CONTRACT_M5.md 4, 5 and 6) -----

        /// <summary>The load fell off the furniture: the crash, panned toward where it lies.</summary>
        public void PlayCrash(float pan)
        {
            if (crashSource == null)
            {
                return;
            }
            LastCrashPan = Mathf.Clamp(pan, -0.8f, 0.8f);
            crashSource.panStereo = LastCrashPan;
            crashSource.pitch = 0.96f + (float)noise.NextDouble() * 0.08f;
            // Audio overhaul: the recorded breaking dishes when there is one.
            AudioLibrary.Entry entry = Recorded(l => l.crash);
            Play(crashSource, entry != null ? entry.clip : Crash, entry != null ? Mix(entry, CrashMix) : CrashSynthVolume);
            CrashesPlayed++;
        }

        /// <summary>
        /// The rocking chair starts its rock of <paramref name="rockTime"/> seconds: the runners creak forward and back, panned
        /// toward it, over the full rock (<see cref="RockCreak"/>) or the careful one (<see cref="RockCreakCareful"/>, for a
        /// rock no longer than RockCarefulTime).
        /// </summary>
        public void PlayRockCreak(float pan, float rockTime)
        {
            if (rockSource == null || !Tuning.SfxRockCreakEnabled)
            {
                return;
            }
            AudioClip clip = rockTime <= Tuning.RockCarefulTime + 1e-4f ? RockCreakCareful : RockCreak;
            rockSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
            rockSource.pitch = 0.95f + (float)noise.NextDouble() * 0.1f;
            Play(rockSource, clip, RockCreakSynthVolume);
            LastRockCreak = clip;
            RockCreaksPlayed++;
        }

        /// <summary>The robot bumps into the furniture: a soft knock (the put-down thump, higher), panned toward it.</summary>
        public void PlayBump(float pan)
        {
            if (bumpSource == null)
            {
                return;
            }
            bumpSource.panStereo = Mathf.Clamp(pan, -0.8f, 0.8f);
            Play(bumpSource, Thump, BumpSynthVolume);
            BumpsPlayed++;
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

        // ----- STARSANIM sounds -----

        /// <summary>
        /// A star chime: each (frequency, delay, gain) triple of <paramref name="notes"/> strikes a glockenspiel bar at its
        /// delay (<see cref="BarSample"/>), the sum normalised to a 0.85 peak with a short fade at the clip's end.
        /// </summary>
        private AudioClip SynthesizeChime(string name, float duration, float[] notes)
        {
            int count = Mathf.CeilToInt(duration * Rate);
            var data = new float[count];
            float peak = 1e-6f;
            for (int i = 0; i < count; i++)
            {
                float t = i / (float)Rate;
                float s = 0f;
                for (int n = 0; n + 2 < notes.Length; n += 3)
                {
                    float local = t - notes[n + 1];
                    if (local >= 0f)
                    {
                        s += BarSample(notes[n], local) * notes[n + 2];
                    }
                }
                data[i] = s * Mathf.Clamp01((duration - t) / 0.06f);
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

        /// <summary>
        /// One struck glockenspiel bar of fundamental <paramref name="f"/>, <paramref name="t"/> seconds after the strike: a
        /// round fundamental with a soft octave, the bar's inharmonic partials (2.76, 5.40, 8.93 f) as a bright "ting" that dies
        /// first, a 2.5 ms attack.
        /// </summary>
        private static float BarSample(float f, float t)
        {
            float w = 2f * Mathf.PI * f * t;
            float s = Mathf.Sin(w) * Mathf.Exp(-t * 4.2f)
                + 0.36f * Mathf.Sin(2f * w) * Mathf.Exp(-t * 6.5f)
                + 0.22f * Mathf.Sin(2.76f * w) * Mathf.Exp(-t * 11f)
                + 0.12f * Mathf.Sin(5.4f * w) * Mathf.Exp(-t * 22f)
                + 0.06f * Mathf.Sin(8.93f * w) * Mathf.Exp(-t * 40f);
            return s * Mathf.Clamp01(t / 0.0025f);
        }

        /// <summary>An empty star: a soft, low wooden "tok" (a short falling knock with a pinch of noise), never bright.</summary>
        private float StarDullSample(float t, float d)
        {
            float f = 300f * (1f - 0.15f * Mathf.Clamp01(t / 0.06f));
            float body = Mathf.Sin(2f * Mathf.PI * f * t) * Mathf.Exp(-t * 38f);
            float knock = Mathf.Sin(2f * Mathf.PI * 620f * t) * Mathf.Exp(-t * 85f) * 0.35f;
            // Its own hashed noise, not the shared generator: the clips and pitch jitters drawn after it stay as they were.
            float n = HashNoise(Mathf.RoundToInt(t * Rate)) * Mathf.Exp(-t * 260f) * 0.18f;
            float attack = Mathf.Clamp01(t / 0.002f);
            float release = Mathf.Clamp01((d - t) / 0.02f);
            return (body + knock + n) * 0.7f * attack * release;
        }

        /// <summary>A repeatable white noise sample in [-1, 1] for sample index <paramref name="i"/> (a PCG style integer hash).</summary>
        private static float HashNoise(int i)
        {
            uint x = unchecked((uint)i * 747796405u + 2891336453u);
            x = unchecked(((x >> (int)((x >> 28) + 4u)) ^ x) * 277803737u);
            x = (x >> 22) ^ x;
            return x / 4294967295f * 2f - 1f;
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

        // ----- M5 sounds -----

        /// <summary>
        /// The door: a latch click at the start, then the hinge, a squeak whose pitch wanders between 600 and 900 Hz as a
        /// stick and slip pulse train excites it, swelling and fading over the swing, with a soft wooden knock at the end
        /// as the leaf settles. It needs filter state, so it does not use <see cref="Generator"/>.
        /// </summary>
        private AudioClip SynthesizeDoor(string name, float duration)
        {
            int count = Mathf.CeilToInt(duration * Rate);
            var data = new float[count];
            float y1 = 0f;
            float y2 = 0f;
            float phase = 0f;
            float peak = 1e-6f;
            float swing = duration - 0.15f;
            for (int i = 0; i < count; i++)
            {
                float t = i / (float)Rate;
                float s = 0.9f * SwitchSnap(t) * 0.5f;
                // The hinge: a resonance at a wandering pitch, driven by slips at 40 to 70 per second.
                float hinge = 0f;
                if (t > 0.03f && t < swing)
                {
                    float x = (t - 0.03f) / (swing - 0.03f);
                    float rate = 40f + 30f * Mathf.Sin(Mathf.PI * x);
                    phase += rate / Rate;
                    float excitation = ((float)noise.NextDouble() * 2f - 1f) * 0.03f;
                    if (phase >= 1f)
                    {
                        phase -= 1f;
                        excitation += 0.5f + 0.5f * (float)noise.NextDouble();
                    }
                    float f = 600f + 300f * Mathf.Sin(Mathf.PI * x * 1.3f);
                    float w = 2f * Mathf.PI * f / Rate;
                    const float r = 0.9975f;
                    float y = 2f * r * Mathf.Cos(w) * y1 - r * r * y2 + excitation;
                    y2 = y1;
                    y1 = y;
                    hinge = y * Mathf.Sin(Mathf.PI * x) * 0.06f;
                }
                // The settle: a soft low knock as the leaf comes to rest.
                float local = t - swing;
                float knock = local >= 0f
                    ? (Mathf.Sin(2f * Mathf.PI * 160f * local) * Mathf.Exp(-local * 30f) + Mathf.Sin(2f * Mathf.PI * 420f * local) * Mathf.Exp(-local * 60f) * 0.4f)
                      * 0.5f * Mathf.Clamp01(local / 0.003f)
                    : 0f;
                data[i] = s + hinge + knock;
                peak = Mathf.Max(peak, Mathf.Abs(data[i]));
            }
            for (int i = 0; i < count; i++)
            {
                data[i] = Mathf.Clamp(data[i] / peak * 0.85f * Mathf.Clamp01((duration - i / (float)Rate) / 0.02f), -1f, 1f);
            }
            AudioClip clip = AudioClip.Create(name, count, 1, Rate, false);
            clip.SetData(data, 0);
            return clip;
        }

        /// <summary>
        /// The bark: two "wouf", the second a little lower. Each is a short, rough burst whose pitch falls from about
        /// 300 to 170 Hz through a low, broad chest resonance, with a 35 Hz vocal fry growl and a noisy, percussive
        /// attack (audio overhaul: the original 520 to 330 Hz sweep through a narrow 900 Hz formant read as a duck's
        /// quack, not a dog; the fundamental is lower here, the formant lower and wider, and the texture noisier and
        /// rougher than a quack's clean tone).
        /// </summary>
        private float BarkSample(float t, float d)
        {
            return Wouf(t, 1f) + 0.8f * Wouf(t - 0.22f, 0.88f);
        }

        private float Wouf(float local, float pitchScale)
        {
            const float length = 0.16f;
            if (local < 0f || local > length)
            {
                return 0f;
            }
            float x = local / length;
            float pitch = (300f - 130f * x) * pitchScale;
            // The phase of a linearly falling pitch, integrated.
            float phase = 2f * Mathf.PI * (300f * local - 130f * local * local / (2f * length)) * pitchScale;
            // Vocal fry: a fast amplitude buzz roughens the tone so it growls instead of ringing clean (a quack's tell).
            float fry = 0.55f + 0.45f * Mathf.Sin(2f * Mathf.PI * 35f * local);
            float s = 0f;
            for (int k = 1; k <= 9; k++)
            {
                float f = pitch * k;
                float formant = Mathf.Exp(-Mathf.Pow((f - 650f) / 550f, 2f)) + 0.25f * Mathf.Exp(-Mathf.Pow((f - 2000f) / 700f, 2f)) + 0.05f;
                s += Mathf.Sin(phase * k) * formant / Mathf.Sqrt(k);
            }
            s *= fry;
            // A fast, noisy burst (a dog's turbulent attack), not a smooth breathy onset.
            float breath = ((float)noise.NextDouble() * 2f - 1f) * Mathf.Exp(-local * 35f) * 0.6f;
            float env = Mathf.Clamp01(local / 0.004f) * Mathf.Pow(1f - x, 1.2f);
            return (s * 0.35f + breath) * env;
        }

        /// <summary>The sniff: two quick bursts of airy noise through a nose (a band near 3 kHz), the second shorter.</summary>
        private float SniffSample(float t, float d)
        {
            float s = SniffBurst(t, 0.09f) + 0.8f * SniffBurst(t - 0.14f, 0.07f);
            return s * Mathf.Clamp01((d - t) / 0.01f);
        }

        // ----- M5 wave 5B sounds -----

        /// <summary>
        /// The robot's hum: a motor drone (whole-hertz partials of 110 Hz) under a brush hiss built from many whole-hertz
        /// sines of fixed random phases, so the one second loop is seamless; the brushes swell gently four times a second.
        /// </summary>
        private AudioClip SynthesizeHum(string name, float duration)
        {
            int count = Mathf.CeilToInt(duration * Rate);
            var data = new float[count];
            var rng = new System.Random(4242);
            const int brushPartials = 40;
            var brushFreq = new float[brushPartials];
            var brushPhase = new float[brushPartials];
            for (int k = 0; k < brushPartials; k++)
            {
                brushFreq[k] = 700 + rng.Next(2600);
                brushPhase[k] = (float)(rng.NextDouble() * 2.0 * System.Math.PI);
            }
            float peak = 1e-6f;
            for (int i = 0; i < count; i++)
            {
                float t = i / (float)Rate;
                float motor = Mathf.Sin(2f * Mathf.PI * 110f * t) * 0.5f + Mathf.Sin(2f * Mathf.PI * 220f * t) * 0.28f
                    + Mathf.Sin(2f * Mathf.PI * 330f * t) * 0.14f + Mathf.Sin(2f * Mathf.PI * 550f * t) * 0.06f;
                float brush = 0f;
                for (int k = 0; k < brushPartials; k++)
                {
                    brush += Mathf.Sin(2f * Mathf.PI * brushFreq[k] * t + brushPhase[k]);
                }
                brush *= 0.035f * (0.75f + 0.25f * Mathf.Sin(2f * Mathf.PI * 4f * t));
                data[i] = motor + brush;
                peak = Mathf.Max(peak, Mathf.Abs(data[i]));
            }
            for (int i = 0; i < count; i++)
            {
                data[i] = Mathf.Clamp(data[i] / peak * 0.7f, -1f, 1f);
            }
            AudioClip clip = AudioClip.Create(name, count, 1, Rate, false);
            clip.SetData(data, 0);
            return clip;
        }

        /// <summary>
        /// The fallen load: a dull knock on the floor, a bright crack, then a scatter of china tinks (high damped partials
        /// starting over the first 0.35 s) over a short gritty noise tail.
        /// </summary>
        private AudioClip SynthesizeCrash(string name, float duration)
        {
            int count = Mathf.CeilToInt(duration * Rate);
            var data = new float[count];
            var rng = new System.Random(911);
            const int tinks = 14;
            var at = new float[tinks];
            var freq = new float[tinks];
            var amp = new float[tinks];
            for (int k = 0; k < tinks; k++)
            {
                at[k] = 0.01f + (float)rng.NextDouble() * 0.35f * (k / (float)tinks + 0.2f);
                freq[k] = 2200f + (float)rng.NextDouble() * 4200f;
                amp[k] = 0.25f + 0.75f * (float)rng.NextDouble() * (1f - 0.5f * k / tinks);
            }
            float peak = 1e-6f;
            for (int i = 0; i < count; i++)
            {
                float t = i / (float)Rate;
                float knock = Mathf.Sin(2f * Mathf.PI * 120f * (1f - 0.25f * Mathf.Clamp01(t / 0.08f)) * t) * Mathf.Exp(-t * 28f);
                float crack = ((float)noise.NextDouble() * 2f - 1f) * Mathf.Exp(-t * 90f) * 0.9f;
                float s = knock + crack;
                for (int k = 0; k < tinks; k++)
                {
                    float local = t - at[k];
                    if (local < 0f)
                    {
                        continue;
                    }
                    s += amp[k] * Mathf.Sin(2f * Mathf.PI * freq[k] * local) * Mathf.Exp(-local * (60f + 4f * k)) * Mathf.Clamp01(local / 0.0015f) * 0.6f;
                }
                float grit = ((float)noise.NextDouble() * 2f - 1f) * 0.12f * Mathf.Exp(-t * 7f) * Mathf.Clamp01(t / 0.02f);
                data[i] = (s + grit) * Mathf.Clamp01((duration - t) / 0.05f);
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
        /// The rock: two soft creaks of the runners (a slow stick and slip train exciting two low wood resonances), the second
        /// weaker, one per swing of the rock. It needs filter state, so it does not use <see cref="Generator"/>.
        /// </summary>
        private AudioClip SynthesizeRockCreak(string name, float duration)
        {
            int count = Mathf.CeilToInt(duration * Rate);
            var data = new float[count];
            float[] freqs = { 240f, 520f };
            float[] damping = { 0.9968f, 0.9955f };
            float[] gains = { 1f, 0.45f };
            var y1 = new float[2];
            var y2 = new float[2];
            float phase = 0f;
            float peak = 1e-6f;
            for (int i = 0; i < count; i++)
            {
                float t = i / (float)Rate;
                float x = t / duration;
                // Two swells of slips (forward, then back), the second weaker.
                float swing = Mathf.Repeat(x * 2f, 1f);
                float swell = Mathf.Sin(Mathf.PI * swing) * (x < 0.5f ? 1f : 0.6f);
                phase += (18f + 40f * swell) / Rate;
                float excitation = 0f;
                if (phase >= 1f)
                {
                    phase -= 1f;
                    excitation = swell * (0.6f + 0.4f * (float)noise.NextDouble());
                }
                float s = 0f;
                for (int k = 0; k < 2; k++)
                {
                    float w = 2f * Mathf.PI * freqs[k] * (1f + 0.04f * swell) / Rate;
                    float r = damping[k];
                    float y = 2f * r * Mathf.Cos(w) * y1[k] - r * r * y2[k] + excitation;
                    y2[k] = y1[k];
                    y1[k] = y;
                    s += y * gains[k];
                }
                data[i] = s * Mathf.Clamp01(t / 0.02f) * Mathf.Clamp01((duration - t) / 0.08f);
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

        private float SniffBurst(float local, float length)
        {
            if (local < 0f || local > length)
            {
                return 0f;
            }
            float x = local / length;
            // Noise ring-modulated up to the nose band: a breathy hiss, not a tone.
            float n = (float)noise.NextDouble() * 2f - 1f;
            float band = Mathf.Sin(2f * Mathf.PI * 2900f * local) * 0.6f + Mathf.Sin(2f * Mathf.PI * 4100f * local) * 0.3f;
            float env = Mathf.Sin(Mathf.PI * x) * Mathf.Sin(Mathf.PI * x);
            return n * band * env * 0.9f;
        }
    }
}
