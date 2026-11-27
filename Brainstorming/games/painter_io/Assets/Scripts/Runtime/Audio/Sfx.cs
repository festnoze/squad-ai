// Owned by BI since wave B-2 (written by B5), by the audio package since wave C. Contract 16 (audio and haptics) with the
// 23.3 Exit/Return debounce and the biome clip sets of 25.2. The sound player of the game: it builds the shared SfxSynth
// clips (UI, ring, lasso, jingles) and the current biome's ISfxClipSet at startup; the two other biomes' sets are
// synthesized at startup too, on worker threads (wave C, robust-03 / perf-07: SfxClipSetLoader), and their AudioClips are
// made on the main thread one per frame, so the first tap on another biome card no longer freezes the menu (a set that is
// not ready yet when its biome is picked is finished at once). It follows GameDirector (SessionStarted, StateChanged,
// PausedChanged) and the bound session's EventRaised, and applies the scope rules:
// - while the human plays a real round (alive, State Playing), events where the human is Player or Other play at full
//   volume, with the contract 16 haptics;
// - bot-only Exit, Return, Cut and Eliminated play only when their point is on screen, at -12 dB, at most one per type
//   every 0.25 s (cut snaps are exempt from that limit: every on-screen cut snaps);
// - in Menu (attract) and after the human's elimination only UI sounds play, plus on-screen events at -18 dB;
// - the spark tension loop plays only for the human's own chase: pitch and pulse rate rise as SparkCatchEta drops;
// - the countdown ticks once per second over the last 10 s of a real round; the win or lose jingle plays once when
//   Results appear.
// 23.3: the exit plop waits for a visible detach (trail longer than 0.35 u or exit older than 0.25 s); the return gloop
// plays only for a Return with cells or after a visible detach (a chased return always had one).
// Contract 24: a saved chased return (no capture) plays the gloop and the soft LoopLost sound instead of the fill swell,
// with the 40 ms haptic. Wave C (feel-13): the human's elimination by territory loss pulses the 120 ms caught haptic, like
// a death to the spark. Contract 25.2: the biome slots (exit, return, fill, cut, tension loop, caught, loop lost) come
// from BiomeTheme.Current's clip set and switch live on BiomeTheme.Changed; the set's Ambient loop (if any) plays softly.
// Muted by SaveData.SoundOn = false, in batchmode and with -mute (no clip is synthesized then, but every decision still
// runs and raises CuePlayed). "-sfxlog" logs every cue and the listener output peak once per second (verification).
// Wave D-2 (traits-infra, docs/BIOME_TRAITS.md sections 5 and 7): the human's own TerritoryGrew plays the biome set's
// optional Grow clip at -18 dB, at most once every GrowRepeatSeconds; the human's kill rewards play short shared cues:
// TerritoryInherited the inherit swell (with the 20 ms capture pulse), SpeedBoosted the speed-up zip (pitched up a little
// per level), ShieldStarted the shield shimmer and ShieldEnded a softer, lower shimmer. Bots' trait events stay silent.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Threading.Tasks;
using PainterIO.Core;
using UnityEngine;
using Debug = UnityEngine.Debug;
using Object = UnityEngine.Object;

namespace PainterIO.Runtime
{
    /// <summary>One sound decision of Sfx (raised also when muted, for tests and logs).</summary>
    public struct SfxCue
    {
        public SfxId Id;
        public float GainDb;    // relative to the clip's base volume: 0 full, -12 bot, -18 spectator
        public float Pitch;
        public int Player;      // sim player the cue is about, -1 for UI and world cues
        public bool Audible;    // false when muted or when the clips are missing
    }

    /// <summary>Contract 16 scope rules as pure functions.</summary>
    public static class SfxScope
    {
        public const float HumanGainDb = 0f;
        public const float BotGainDb = -12f;
        public const float SpectatorGainDb = -18f;

        /// <summary>Bot-only (and spectator) cues of one type play at most once per this many real seconds.</summary>
        public const float RateLimitSeconds = 0.25f;

        /// <summary>
        /// Gain (dB) of an event sound, or null when it stays silent. live: a real round with the human alive and State
        /// Playing. involvesHuman: the human is the event's Player or Other. onScreen: the event point is in view.
        /// </summary>
        public static float? EventGainDb(bool live, bool involvesHuman, bool onScreen)
        {
            if (live && involvesHuman) return HumanGainDb;
            if (!onScreen) return null;
            return live ? BotGainDb : SpectatorGainDb;
        }

        /// <summary>The event types that sound for bots (and for everyone in Menu or after the human's elimination).</summary>
        public static bool IsScopedType(SimEventType type)
        {
            return type == SimEventType.Exit || type == SimEventType.Return || type == SimEventType.Cut
                   || type == SimEventType.Eliminated;
        }

        /// <summary>dB to a linear gain factor.</summary>
        public static float DbToGain(float db)
        {
            return Mathf.Pow(10f, db / 20f);
        }
    }

    /// <summary>
    /// Wave C (robust-03, perf-07): builds clip sets without blocking the main thread. Start runs
    /// ISplitSfxClipSet.Synthesize on a worker thread (Task.Run); Step, called once per frame on the main thread, makes at
    /// most one AudioClip of a set whose samples are ready and returns the set once all its slots are made; Finish
    /// completes a set at once (its biome was picked before it was ready). The samples are those of Build(rate).
    /// </summary>
    public sealed class SfxClipSetLoader
    {
        private readonly ISplitSfxClipSet[] sets;
        private readonly Task<SfxClipSamples>[] tasks;
        private readonly SfxClipSamples[] samples;
        private readonly int[] nextSlot;

        public SfxClipSetLoader(int count)
        {
            sets = new ISplitSfxClipSet[count];
            tasks = new Task<SfxClipSamples>[count];
            samples = new SfxClipSamples[count];
            nextSlot = new int[count];
        }

        /// <summary>The samples of the set last completed by Step or Finish (synthesis time for the log), else null.</summary>
        public SfxClipSamples LastSamples { get; private set; }

        /// <summary>True while the set at index is being synthesized or assembled.</summary>
        public bool IsPending(int index)
        {
            return index >= 0 && index < sets.Length && sets[index] != null;
        }

        /// <summary>Clips already made for the pending set at index (0 while its worker runs), -1 when none is pending.</summary>
        public int SlotsBuilt(int index)
        {
            return IsPending(index) ? nextSlot[index] : -1;
        }

        /// <summary>True when a pending set exists.</summary>
        public bool AnyPending
        {
            get
            {
                for (int k = 0; k < sets.Length; k++)
                {
                    if (sets[k] != null) return true;
                }
                return false;
            }
        }

        /// <summary>
        /// Starts the worker synthesis of set at index. False when the index is busy or the platform cannot start a worker
        /// (the caller then builds the set synchronously the first time it is needed).
        /// </summary>
        public bool Start(int index, ISplitSfxClipSet set, int sampleRate)
        {
            if (set == null || index < 0 || index >= sets.Length || sets[index] != null) return false;
            try
            {
                ISplitSfxClipSet target = set;
                tasks[index] = Task.Run(() => target.Synthesize(sampleRate));
            }
            catch (Exception e)
            {
                Debug.LogWarning("[PainterIO] Sfx: no worker thread for the " + set.Biome + " clip set (" + e.Message
                                 + "), it is built when first used");
                return false;
            }
            sets[index] = set;
            samples[index] = null;
            nextSlot[index] = 0;
            return true;
        }

        /// <summary>
        /// Main thread, once per frame: makes at most one AudioClip of the first set whose samples are ready. Returns that
        /// set when its last slot was just made (index = its index), else null (index -1). A worker that failed drops its
        /// set (logged): the caller builds it synchronously when it is needed.
        /// </summary>
        public ISfxClipSet Step(out int index)
        {
            index = -1;
            for (int k = 0; k < sets.Length; k++)
            {
                if (sets[k] == null) continue;
                if (samples[k] == null)
                {
                    if (!tasks[k].IsCompleted) continue;
                    if (!TakeResult(k)) continue;
                }
                BuildNextSlot(k);
                if (nextSlot[k] < SfxClipSamples.AllSlotCount) return null;
                index = k;
                return Complete(k);
            }
            return null;
        }

        /// <summary>
        /// Main thread: waits for the worker of the set at index and makes its remaining clips now. Null when no set is
        /// pending there or its worker failed (logged).
        /// </summary>
        public ISfxClipSet Finish(int index)
        {
            if (!IsPending(index)) return null;
            if (samples[index] == null)
            {
                try
                {
                    tasks[index].Wait();
                }
                catch (Exception)
                {
                    // TakeResult logs the failure.
                }
                if (!TakeResult(index)) return null;
            }
            while (nextSlot[index] < SfxClipSamples.AllSlotCount) BuildNextSlot(index);
            return Complete(index);
        }

        /// <summary>Forgets every pending set and returns the clips they already made (the caller destroys them).</summary>
        public List<AudioClip> Abandon()
        {
            var made = new List<AudioClip>();
            for (int k = 0; k < sets.Length; k++)
            {
                ISplitSfxClipSet set = sets[k];
                if (set == null) continue;
                AudioClip[] owned = { set.Exit, set.Return, set.Fill, set.Cut, set.TensionLoop, set.Caught, set.LoopLost, set.Ambient, set.Grow };
                foreach (AudioClip c in owned)
                {
                    if (c != null) made.Add(c);
                }
                sets[k] = null;
                tasks[k] = null;
                samples[k] = null;
            }
            return made;
        }

        private bool TakeResult(int k)
        {
            Task<SfxClipSamples> task = tasks[k];
            if (task.Status == TaskStatus.RanToCompletion && task.Result != null)
            {
                samples[k] = task.Result;
                return true;
            }
            Exception e = task.Exception != null ? task.Exception.GetBaseException() : null;
            Debug.LogError("[PainterIO] Sfx: background synthesis of the " + sets[k].Biome + " clip set failed: "
                           + (e != null ? e.ToString() : task.Status.ToString()));
            sets[k] = null;
            tasks[k] = null;
            return false;
        }

        private void BuildNextSlot(int k)
        {
            sets[k].BuildSlot(samples[k], (SfxSlot)nextSlot[k]);
            nextSlot[k]++;
        }

        private ISfxClipSet Complete(int k)
        {
            ISfxClipSet set = sets[k];
            LastSamples = samples[k];
            sets[k] = null;
            tasks[k] = null;
            samples[k] = null;
            return set;
        }
    }

    public sealed class Sfx : MonoBehaviour
    {
        /// <summary>One-shot voices (round robin, the oldest is stolen when all play).</summary>
        public const int VoiceCount = 12;

        /// <summary>Viewport margin of the on-screen test.</summary>
        public const float OnScreenMargin = 0.03f;

        public const float TensionFadeInSeconds = 0.06f;
        public const float TensionFadeOutSeconds = 0.15f;

        /// <summary>Minimum real seconds between two snaps of on-screen bot cuts (only against exact duplicates).</summary>
        public const float CutRepeatSeconds = 0.05f;

        public const float UiRepeatSeconds = 0.03f;
        public const float ToastRepeatSeconds = 0.1f;

        /// <summary>The countdown ticks over the last this many seconds, one per second.</summary>
        public const int CountdownSeconds = 10;

        /// <summary>From this many seconds left the countdown tick is pitched up a major third.</summary>
        public const int CountdownUrgentSeconds = 3;

        public const float CountdownUrgentPitch = 1.26f;

        /// <summary>Captured cells at which the fill swell reaches full volume.</summary>
        public const int SwellFullCells = 1500;

        /// <summary>Wave D-2 (BIOME_TRAITS 5): gain of the Grow clip (the human's own growth only).</summary>
        public const float GrowGainDb = -18f;

        /// <summary>Wave D-2: the Grow clip plays at most once per this many real seconds.</summary>
        public const float GrowRepeatSeconds = 2.0f;

        /// <summary>Wave D-2: gain of the softer, lower shimmer when the human's shield ends.</summary>
        public const float ShieldEndGainDb = -9f;

        /// <summary>Wave D-2: pitch of the shimmer when the human's shield ends.</summary>
        public const float ShieldEndPitch = 0.7f;

        private const int HumanPriority = 32;
        private const int UiPriority = 16;
        private const int SpectatorPriority = 160;

        // Base volume of each clip (index = SfxId), balancing short clicks against long jingles.
        private static readonly float[] BaseVolumes =
        {
            0.42f,  // ExitPlop
            0.48f,  // ReturnGloop
            0.40f,  // FillSwell
            0.75f,  // CutSnap
            0.42f,  // SparkLoop (times TensionVolume)
            0.80f,  // CaughtSplat
            0.50f,  // RingChime
            0.60f,  // LassoZip
            0.32f,  // ToastTick
            0.45f,  // UiClick
            0.50f,  // CountdownTick
            0.62f,  // WinJingle
            0.58f,  // LoseJingle
            0.50f,  // LoopLost
            0.45f,  // GrowCreep (times GrowGainDb)
            0.55f,  // KillInherit
            0.50f,  // SpeedUp
            0.48f,  // ShieldShimmer
        };

        /// <summary>Volume of the biome ambience loop (ISfxClipSet.Ambient), when the biome has one.</summary>
        public const float AmbientVolume = 0.22f;

        /// <summary>Seconds the ambience loop takes to fade in or out (biome switch, mute).</summary>
        public const float AmbientFadeSeconds = 0.6f;

        /// <summary>The live Sfx (null before GameDirector built it or after it was destroyed).</summary>
        public static Sfx Instance { get; private set; }

        /// <summary>Every sound decision, in order (also when muted).</summary>
        public event Action<SfxCue> CuePlayed;

        /// <summary>Every haptic pulse requested (ms), also off Android where Haptics.Pulse is a no-op.</summary>
        public event Action<int> HapticPulsed;

        /// <summary>Batchmode or -mute: no clip is synthesized and nothing ever plays.</summary>
        public bool HardMuted { get; private set; }

        /// <summary>HardMuted or SaveData.SoundOn is false.</summary>
        public bool Muted => HardMuted || !SaveData.SoundOn;

        /// <summary>True once the clips were synthesized (false when hard-muted).</summary>
        public bool ClipsReady => clips != null;

        /// <summary>The current biome's clip set (null when hard-muted: no clip is ever synthesized then).</summary>
        public ISfxClipSet CurrentSet => currentSet;

        /// <summary>The human is being chased in a live round (the tension loop is wanted).</summary>
        public bool TensionActive { get; private set; }

        /// <summary>Current playback pitch of the tension loop (TensionPitch(eta) times a slight slow-motion drop).</summary>
        public float TensionPitch { get; private set; } = 1f;

        /// <summary>Current tension loop volume factor (faded, 0 when silent).</summary>
        public float TensionLevel => tensionLevel;

        private GameDirector director;
        private GameSession session;
        private GameState attachedState = GameState.Boot;
        private AudioClip[] clips;
        private AudioSource[] voices;
        private float[] voiceStart;
        private int nextVoice;
        private AudioSource loopSource;
        private AudioSource ambientSource;
        private float ambientLevel;
        private readonly ISfxClipSet[] clipSets = new ISfxClipSet[BiomeTheme.Count];
        private readonly SfxClipSetLoader loader = new SfxClipSetLoader(BiomeTheme.Count);
        private ISfxClipSet currentSet;
        private float clock;
        private readonly float[] lastSpectatorCue = new float[SfxSynth.ClipCount];
        private readonly float[] lastUiCue = new float[SfxSynth.ClipCount];
        private bool[] exitPending = new bool[0];
        private bool[] detachShown = new bool[0];
        private bool humanLive, humanSplatPlayed, jinglePlayed;
        private int lastCountdownSecond = int.MaxValue;
        private float tensionLevel;
        private readonly System.Random jitter = new System.Random(0x5F5);
        private Camera cachedCamera;
        private AudioListener ownListener;
        private float listenerCheckIn;
        private bool logCues;
        private float[] outputProbe;
        private float outputPeak;
        private float outputLogIn = 1f;
        private bool updateErrorLogged, eventErrorLogged, tornDown;

        // ------------------------------------------------------------------------------------------------------------
        // Factory and public API.

        /// <summary>Contract 11.1 entry point: the Sfx root, subscribed to SessionStarted / StateChanged / PausedChanged.</summary>
        public static Sfx Create(GameDirector d)
        {
            var go = new GameObject("Sfx");
            var sfx = go.AddComponent<Sfx>();
            sfx.Initialize(d);
            return sfx;
        }

        /// <summary>Soft click for buttons and toggles (B4). Plays in every state unless sound is off; no-op without Sfx.</summary>
        public static void PlayUiClick()
        {
            Sfx s = Instance;
            if (s != null) s.PlayUi(SfxId.UiClick, 0f, UiRepeatSeconds);
        }

        /// <summary>Light tick when a toast appears (B4). Plays in every state unless sound is off; no-op without Sfx.</summary>
        public static void PlayToastTick()
        {
            Sfx s = Instance;
            if (s != null) s.PlayUi(SfxId.ToastTick, -2f, ToastRepeatSeconds);
        }

        /// <summary>A new (not yet built) clip set of a biome: LiquidSfx, FireSfx or ElectricSfx.</summary>
        public static ISfxClipSet CreateClipSet(BiomeId biome)
        {
            switch (biome)
            {
                case BiomeId.Fire: return new FireSfx();
                case BiomeId.Electric: return new ElectricSfx();
                default: return new LiquidSfx();
            }
        }

        /// <summary>True for the clips a biome's ISfxClipSet provides (the others are shared by every biome).</summary>
        public static bool IsBiomeSlot(SfxId id)
        {
            return id == SfxId.ExitPlop || id == SfxId.ReturnGloop || id == SfxId.FillSwell || id == SfxId.CutSnap
                   || id == SfxId.SparkLoop || id == SfxId.CaughtSplat || id == SfxId.LoopLost || id == SfxId.GrowCreep;
        }

        /// <summary>The clip of a biome slot in a set (null for a shared clip or a missing one).</summary>
        public static AudioClip SlotClip(ISfxClipSet set, SfxId id)
        {
            if (set == null) return null;
            switch (id)
            {
                case SfxId.ExitPlop: return set.Exit;
                case SfxId.ReturnGloop: return set.Return;
                case SfxId.FillSwell: return set.Fill;
                case SfxId.CutSnap: return set.Cut;
                case SfxId.SparkLoop: return set.TensionLoop;
                case SfxId.CaughtSplat: return set.Caught;
                case SfxId.LoopLost: return set.LoopLost;
                case SfxId.GrowCreep: return set.Grow;
                default: return null;
            }
        }

        /// <summary>Base volume of a clip (before the cue's gain).</summary>
        public static float BaseVolume(SfxId id)
        {
            return BaseVolumes[(int)id];
        }

        /// <summary>
        /// Binds a session with an explicit game state, for a Sfx created without a GameDirector (tests). With a director
        /// the state always comes from GameDirector.State.
        /// </summary>
        public void Attach(GameSession s, GameState state)
        {
            attachedState = state;
            Bind(s);
        }

        /// <summary>Changes the game state used without a GameDirector (tests); Results plays the jingle once.</summary>
        public void SetAttachedState(GameState state)
        {
            attachedState = state;
            OnStateChanged(state);
        }

        /// <summary>The per-frame work (Update calls it with the unscaled delta; tests call it directly).</summary>
        public void Tick(float unscaledDeltaTime)
        {
            float dt = unscaledDeltaTime > 0f && !float.IsInfinity(unscaledDeltaTime) ? Mathf.Min(unscaledDeltaTime, 0.25f) : 0f;
            clock += dt;
            GameSession s = session;
            if (s != null && !s.IsClosed)
            {
                if (humanLive && !s.HumanAlive) humanLive = false;
                UpdateDetaches(s);
                UpdateCountdown(s);
            }
            UpdateTension(s, dt);
            if (!HardMuted)
            {
                UpdateBackgroundSets();
                UpdateAmbient(dt);
                UpdateListener(dt);
                if (logCues) UpdateOutputLog(dt);
            }
        }

        /// <summary>Unsubscribes everything and releases the clips (OnDestroy calls it; edit-mode tests call it before DestroyImmediate).</summary>
        public void Teardown()
        {
            if (tornDown) return;
            tornDown = true;
            SaveData.Changed -= OnSaveDataChanged;
            BiomeTheme.Changed -= OnBiomeChanged;
            if (director != null)
            {
                director.SessionStarted -= OnSessionStarted;
                director.StateChanged -= OnStateChanged;
                director.PausedChanged -= OnPausedChanged;
            }
            if (session != null) session.EventRaised -= OnSessionEvent;
            session = null;
            if (clips != null)
            {
                foreach (AudioClip c in clips)
                {
                    if (c == null) continue;
                    if (Application.isPlaying) Object.Destroy(c);
                    else Object.DestroyImmediate(c);
                }
            }
            clips = null;
            var destroyed = new HashSet<AudioClip>();
            foreach (AudioClip c in loader.Abandon())
            {
                if (c == null || !destroyed.Add(c)) continue;
                if (Application.isPlaying) Object.Destroy(c);
                else Object.DestroyImmediate(c);
            }
            for (int k = 0; k < clipSets.Length; k++)
            {
                ISfxClipSet set = clipSets[k];
                clipSets[k] = null;
                if (set == null) continue;
                AudioClip[] owned = { set.Exit, set.Return, set.Fill, set.Cut, set.TensionLoop, set.Caught, set.LoopLost, set.Ambient, set.Grow };
                foreach (AudioClip c in owned)
                {
                    if (c == null || !destroyed.Add(c)) continue;
                    if (Application.isPlaying) Object.Destroy(c);
                    else Object.DestroyImmediate(c);
                }
            }
            currentSet = null;
            if (Instance == this) Instance = null;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Lifecycle.

        private void Initialize(GameDirector d)
        {
            director = d;
            Instance = this;
            HardMuted = Application.isBatchMode || LaunchArgs.Has("-mute");
            logCues = LaunchArgs.Has("-sfxlog");
            for (int i = 0; i < SfxSynth.ClipCount; i++)
            {
                lastSpectatorCue[i] = -10f;
                lastUiCue[i] = -10f;
            }
            if (!HardMuted) BuildAudio();
            SaveData.Changed += OnSaveDataChanged;
            BiomeTheme.Changed += OnBiomeChanged;
            if (d != null)
            {
                d.SessionStarted += OnSessionStarted;
                d.StateChanged += OnStateChanged;
                d.PausedChanged += OnPausedChanged;
                if (d.Session != null) Bind(d.Session);
            }
        }

        private void BuildAudio()
        {
            try
            {
                var watch = Stopwatch.StartNew();
                // Shared clips (UI, ring, lasso, jingles); the biome slots come from the clip sets.
                var built = new AudioClip[SfxSynth.ClipCount];
                int ok = 0, wanted = 0;
                double seconds = 0.0;
                for (int i = 0; i < built.Length; i++)
                {
                    if (IsBiomeSlot((SfxId)i)) continue;
                    wanted++;
                    try
                    {
                        built[i] = SfxSynth.CreateClip((SfxId)i);
                        seconds += SfxSynth.DurationOf((SfxId)i);
                        ok++;
                    }
                    catch (Exception e)
                    {
                        Debug.LogError("[PainterIO] Sfx clip " + (SfxId)i + " failed: " + e);
                    }
                }
                clips = built;
                voices = new AudioSource[VoiceCount];
                voiceStart = new float[VoiceCount];
                for (int i = 0; i < VoiceCount; i++) voices[i] = NewSource(false);
                loopSource = NewSource(true);
                loopSource.priority = HumanPriority;
                ambientSource = NewSource(true);
                ambientSource.priority = SpectatorPriority;
                currentSet = SetFor(BiomeTheme.Current.Id);
                loopSource.clip = SlotClip(currentSet, SfxId.SparkLoop);
                int background = StartBackgroundSets();
                Debug.Log("[PainterIO] Sfx: " + ok + "/" + wanted + " shared clips synthesized ("
                          + seconds.ToString("0.0", CultureInfo.InvariantCulture) + " s of audio) and the "
                          + BiomeTheme.Current.CommandName + " clip set, in " + watch.ElapsedMilliseconds + " ms; "
                          + background + " other clip sets synthesizing in the background");
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] Sfx audio setup failed, the game stays silent: " + e);
                voices = null;
                loopSource = null;
            }
        }

        /// <summary>
        /// Wave C: starts the worker synthesis of every biome set not built yet (the current biome's set is built
        /// synchronously before). Returns how many started.
        /// </summary>
        private int StartBackgroundSets()
        {
            int started = 0;
            for (int k = 0; k < clipSets.Length; k++)
            {
                if (clipSets[k] != null || loader.IsPending(k)) continue;
                if (CreateClipSet((BiomeId)k) is ISplitSfxClipSet split && loader.Start(k, split, SfxSynth.SampleRate)) started++;
            }
            return started;
        }

        /// <summary>Once per frame: makes at most one AudioClip of a background set; logs a set when it is complete.</summary>
        private void UpdateBackgroundSets()
        {
            if (!loader.AnyPending) return;
            ISfxClipSet done = loader.Step(out int k);
            if (done == null || k < 0 || k >= clipSets.Length) return;
            clipSets[k] = done;
            SfxClipSamples s = loader.LastSamples;
            Debug.Log("[PainterIO] Sfx: " + BiomeTheme.CommandNameOf((BiomeId)k) + " clip set ready in the background (synthesized in "
                      + (s != null ? s.SynthMilliseconds : 0L) + " ms on a worker thread), "
                      + Time.realtimeSinceStartup.ToString("0.00", CultureInfo.InvariantCulture) + " s after boot");
        }

        /// <summary>
        /// The clip set of a biome; null when hard-muted. A set still loading in the background is finished now; a set
        /// that never started (no worker thread) is built synchronously.
        /// </summary>
        private ISfxClipSet SetFor(BiomeId biome)
        {
            if (HardMuted) return null;
            int k = (int)BiomeTheme.Clamp((int)biome);
            if (clipSets[k] != null) return clipSets[k];
            if (loader.IsPending(k))
            {
                var wait = Stopwatch.StartNew();
                ISfxClipSet finished = loader.Finish(k);
                if (finished != null)
                {
                    Debug.Log("[PainterIO] Sfx: " + BiomeTheme.CommandNameOf((BiomeId)k)
                              + " clip set was still loading when picked, finished in " + wait.ElapsedMilliseconds + " ms");
                    clipSets[k] = finished;
                    return finished;
                }
            }
            ISfxClipSet set = CreateClipSet((BiomeId)k);
            try
            {
                var watch = Stopwatch.StartNew();
                set.Build(SfxSynth.SampleRate);
                Debug.Log("[PainterIO] Sfx: " + BiomeTheme.CommandNameOf((BiomeId)k) + " clip set built in " + watch.ElapsedMilliseconds + " ms");
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] Sfx clip set " + (BiomeId)k + " failed: " + e);
            }
            clipSets[k] = set;
            return set;
        }

        /// <summary>BiomeTheme.Changed: switch the biome slots (the tension loop keeps playing with the new clip).</summary>
        private void OnBiomeChanged(BiomeTheme theme)
        {
            if (this == null)
            {
                BiomeTheme.Changed -= OnBiomeChanged;   // destroyed in edit mode without Teardown
                return;
            }
            if (theme == null || HardMuted || clips == null) return;
            ISfxClipSet next = SetFor(theme.Id);
            if (next == currentSet) return;
            currentSet = next;
            if (loopSource != null)
            {
                bool playing = loopSource.isPlaying;
                AudioClip loop = SlotClip(currentSet, SfxId.SparkLoop);
                if (loopSource.clip != loop)
                {
                    loopSource.Stop();
                    loopSource.clip = loop;
                    if (playing && loop != null) loopSource.Play();
                }
            }
            ambientLevel = 0f;
            if (ambientSource != null)
            {
                ambientSource.Stop();
                ambientSource.clip = currentSet != null ? currentSet.Ambient : null;
            }
        }

        /// <summary>The biome ambience: fades in while a session exists and sound is on, out otherwise.</summary>
        private void UpdateAmbient(float dt)
        {
            if (ambientSource == null) return;
            AudioClip clip = currentSet != null ? currentSet.Ambient : null;
            if (ambientSource.clip != clip)
            {
                ambientSource.Stop();
                ambientSource.clip = clip;
                ambientLevel = 0f;
            }
            bool want = clip != null && !Muted && session != null && !Paused;
            ambientLevel = Mathf.MoveTowards(ambientLevel, want ? 1f : 0f, dt / AmbientFadeSeconds);
            if (ambientLevel > 0.001f && clip != null && !Muted)
            {
                ambientSource.volume = AmbientVolume * ambientLevel;
                if (!ambientSource.isPlaying) ambientSource.Play();
            }
            else if (ambientSource.isPlaying) ambientSource.Stop();
        }
        private AudioSource NewSource(bool loop)
        {
            AudioSource s = gameObject.AddComponent<AudioSource>();
            s.playOnAwake = false;
            s.loop = loop;
            s.spatialBlend = 0f;
            s.dopplerLevel = 0f;
            s.bypassReverbZones = true;
            s.volume = 0f;
            s.priority = 128;
            return s;
        }

        private void Update()
        {
            try
            {
                Tick(Time.unscaledDeltaTime);
            }
            catch (Exception e)
            {
                if (updateErrorLogged) return;
                updateErrorLogged = true;
                Debug.LogError("[PainterIO] Sfx update failed: " + e);
            }
        }

        private void OnDestroy()
        {
            Teardown();
        }

        // ------------------------------------------------------------------------------------------------------------
        // GameDirector and SaveData events.

        private GameState CurrentState => director != null ? director.State : attachedState;

        /// <summary>A real round with the human alive and State Playing.</summary>
        private bool Live => humanLive && session != null && CurrentState == GameState.Playing;

        private int HumanIndex => session != null && !session.IsAttract ? session.HumanIndex : -1;

        private bool Paused => director != null && director.IsPaused;

        private void OnSessionStarted(GameSession s)
        {
            Bind(s);
        }

        private void Bind(GameSession s)
        {
            if (session != null) session.EventRaised -= OnSessionEvent;
            session = s;
            int n = s != null ? s.Sim.Players.Count : 0;
            exitPending = new bool[n];
            detachShown = new bool[n];
            humanLive = s != null && !s.IsAttract && s.HumanIndex >= 0 && s.HumanAlive;
            humanSplatPlayed = false;
            jinglePlayed = false;
            lastCountdownSecond = s != null ? SecondsLeft(s) : int.MaxValue;
            for (int i = 0; i < lastSpectatorCue.Length; i++) lastSpectatorCue[i] = -10f;
            StopTension(true);
            if (s == null) return;
            s.EventRaised -= OnSessionEvent;
            s.EventRaised += OnSessionEvent;
        }

        private void OnStateChanged(GameState state)
        {
            if (state != GameState.Playing) StopTension(false);
            if (state == GameState.Results) PlayResultsJingle();
        }

        private void OnPausedChanged(bool paused)
        {
            if (paused) StopTension(true);
        }

        private void OnSaveDataChanged()
        {
            if (!Muted) return;
            if (voices != null)
            {
                foreach (AudioSource v in voices)
                {
                    if (v != null && v.isPlaying) v.Stop();
                }
            }
            if (loopSource != null && loopSource.isPlaying) loopSource.Stop();
            if (ambientSource != null && ambientSource.isPlaying) ambientSource.Stop();
            ambientLevel = 0f;
        }

        private void PlayResultsJingle()
        {
            GameSession s = session;
            if (jinglePlayed || s == null || s.IsAttract || s.HumanIndex < 0) return;
            jinglePlayed = true;
            HumanOutcome o = director != null ? director.LastOutcome : null;
            int rank;
            if (o != null) rank = o.Rank;
            else
            {
                try
                {
                    rank = s.Sim.RankOf(s.HumanIndex);
                }
                catch (Exception)
                {
                    rank = 0;
                }
            }
            PlayCue(rank == 1 ? SfxId.WinJingle : SfxId.LoseJingle, 0f, 1f, s.HumanIndex, UiPriority);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Session events (forwarded after each Step, in resolution order).

        /// <summary>Wave D-2, tests only: handles one event as if the bound session had forwarded it.</summary>
        internal void HandleEventForTests(SimEvent e)
        {
            OnSessionEvent(e);
        }

        private void OnSessionEvent(SimEvent e)
        {
            try
            {
                HandleEvent(e);
            }
            catch (Exception ex)
            {
                if (eventErrorLogged) return;
                eventErrorLogged = true;
                Debug.LogError("[PainterIO] Sfx event handling failed: " + ex);
            }
        }

        private void HandleEvent(SimEvent e)
        {
            GameSession s = session;
            if (s == null || e == null) return;
            int h = HumanIndex;
            bool live = Live;
            switch (e.Type)
            {
                case SimEventType.Exit:
                    if (e.Player >= 0 && e.Player < exitPending.Length)
                    {
                        exitPending[e.Player] = true;
                        detachShown[e.Player] = false;
                    }
                    break;

                case SimEventType.Return:
                    OnReturn(s, e, h, live);
                    break;

                case SimEventType.Cut:
                    if (live && h >= 0 && e.Player == h)
                    {
                        PlayCue(SfxId.CutSnap, SfxScope.HumanGainDb, Jitter(0.97f, 0.02f), h, HumanPriority);
                        Pulse(Haptics.CutReceivedMs);
                    }
                    else if (live && h >= 0 && e.Other == h)
                    {
                        PlayCue(SfxId.CutSnap, SfxScope.HumanGainDb, Jitter(1.08f, 0.02f), h, HumanPriority);
                        Pulse(Haptics.CutDealtMs);
                    }
                    else Spectate(SfxId.CutSnap, ToVector(e.Point), e.Player, CutRepeatSeconds);
                    break;

                case SimEventType.SparkCaught:
                    if (live && h >= 0 && e.Player == h)
                    {
                        PlayCue(SfxId.CaughtSplat, SfxScope.HumanGainDb, 1f, h, HumanPriority);
                        Pulse(Haptics.CaughtMs);
                        humanSplatPlayed = true;
                        StopTension(true);
                    }
                    break;

                case SimEventType.Eliminated:
                    if (h >= 0 && e.Player == h)
                    {
                        // Caught: the splat and the 120 ms haptic already played on SparkCaught. Territory lost: both
                        // play here (wave C, feel-13: the same caught pulse as a death to the spark).
                        if (live && !humanSplatPlayed)
                        {
                            PlayCue(SfxId.CaughtSplat, SfxScope.HumanGainDb, 0.9f, h, HumanPriority);
                            Pulse(Haptics.CaughtMs);
                        }
                        humanSplatPlayed = true;
                        humanLive = false;
                        StopTension(true);
                    }
                    else if (live && h >= 0 && e.Other == h)
                    {
                        PlayCue(SfxId.CaughtSplat, SfxScope.HumanGainDb, Jitter(1.12f, 0.03f), e.Player, HumanPriority);
                    }
                    else Spectate(SfxId.CaughtSplat, PositionOf(s, e.Player, e.Point), e.Player, SfxScope.RateLimitSeconds);
                    break;

                case SimEventType.LassoPocket:
                    if (live && h >= 0 && e.Player == h) PlayCue(SfxId.LassoZip, SfxScope.HumanGainDb, 1f, h, HumanPriority);
                    break;

                case SimEventType.RingPicked:
                    if (live && h >= 0 && e.Player == h) PlayCue(SfxId.RingChime, SfxScope.HumanGainDb, 1f, h, HumanPriority);
                    break;

                case SimEventType.RingSpawned:
                    // A world event (not bot-only): a soft, lower chime announces the ring to the human.
                    if (live) PlayCue(SfxId.RingChime, SfxScope.BotGainDb, 0.84f, -1, SpectatorPriority);
                    break;

                // Wave D-2 (BIOME_TRAITS 5 and 7): trait events, for the live human only.
                case SimEventType.TerritoryGrew:
                    if (live && h >= 0 && e.Player == h && e.Cells != null && e.Cells.Length > 0)
                    {
                        int k = (int)SfxId.GrowCreep;
                        if (clock - lastSpectatorCue[k] < GrowRepeatSeconds) break;
                        lastSpectatorCue[k] = clock;
                        PlayCue(SfxId.GrowCreep, GrowGainDb, Jitter(1f, 0.03f), h, SpectatorPriority);
                    }
                    break;

                case SimEventType.TerritoryInherited:
                    if (live && h >= 0 && e.Player == h)
                    {
                        PlayCue(SfxId.KillInherit, SfxScope.HumanGainDb, 1f, h, HumanPriority);
                        Pulse(Haptics.CaptureMs);
                    }
                    break;

                case SimEventType.SpeedBoosted:
                    if (live && h >= 0 && e.Player == h)
                    {
                        float level = Mathf.Clamp((float)e.Value - 1f, 0f, 1f);
                        PlayCue(SfxId.SpeedUp, -1f, 1f + 0.5f * level, h, HumanPriority);
                    }
                    break;

                case SimEventType.ShieldStarted:
                    if (live && h >= 0 && e.Player == h) PlayCue(SfxId.ShieldShimmer, -1f, 1f, h, HumanPriority);
                    break;

                case SimEventType.ShieldEnded:
                    if (live && h >= 0 && e.Player == h) PlayCue(SfxId.ShieldShimmer, ShieldEndGainDb, ShieldEndPitch, h, HumanPriority);
                    break;
            }
        }

        private void OnReturn(GameSession s, SimEvent e, int h, bool live)
        {
            int p = e.Player;
            if (p < 0 || p >= exitPending.Length) return;
            bool sawDetach = detachShown[p] || (exitPending[p] && s.LastExitDuration(p) >= GameSession.FlickerSeconds);
            exitPending[p] = false;
            detachShown[p] = false;
            int cells = e.Cells != null ? e.Cells.Length : 0;
            // 23.3: the merge sound plays only for a Return with cells or after a visible detach.
            if (cells == 0 && !sawDetach && !e.Chased) return;
            if (live && p == h)
            {
                PlayCue(SfxId.ReturnGloop, SfxScope.HumanGainDb, Jitter(1f, 0.03f), h, HumanPriority);
                if (cells > 0)
                {
                    float k = Mathf.Clamp01((float)cells / SwellFullCells);
                    PlayCue(SfxId.FillSwell, Mathf.Lerp(-6f, 0f, k), Mathf.Lerp(1.06f, 0.94f, k), h, HumanPriority);
                }
                else if (e.Chased)
                {
                    // Contract 24: saved, but the loop is lost (no capture, no fill): the soft loop lost sound instead.
                    PlayCue(SfxId.LoopLost, -2f, 1f, h, HumanPriority);
                }
                if (e.Chased) Pulse(Haptics.SavedReturnMs);
                else if (cells > 0) Pulse(Haptics.CaptureMs);
            }
            else Spectate(SfxId.ReturnGloop, ToVector(e.Point), p, SfxScope.RateLimitSeconds);
        }

        /// <summary>A cue that is not about the live human: on screen only, -12 dB (live) or -18 dB, rate limited per clip.</summary>
        private void Spectate(SfxId id, Vector2 point, int player, float minInterval)
        {
            float? db = SfxScope.EventGainDb(Live, false, OnScreen(point));
            if (!db.HasValue) return;
            int k = (int)id;
            if (clock - lastSpectatorCue[k] < minInterval) return;
            lastSpectatorCue[k] = clock;
            PlayCue(id, db.Value, Jitter(1f, 0.04f), player, SpectatorPriority);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Per-frame work.

        private void UpdateDetaches(GameSession s)
        {
            Simulation sim = s.Sim;
            int n = Math.Min(exitPending.Length, sim.Players.Count);
            int h = HumanIndex;
            for (int p = 0; p < n; p++)
            {
                if (!exitPending[p]) continue;
                PlayerState ps = sim.Players[p];
                if (!ps.Alive || ps.Home)
                {
                    exitPending[p] = false;
                    continue;
                }
                if (!s.HasVisibleDetach(p)) continue;
                exitPending[p] = false;
                detachShown[p] = true;
                if (Live && p == h) PlayCue(SfxId.ExitPlop, SfxScope.HumanGainDb, Jitter(1f, 0.04f), p, HumanPriority);
                else Spectate(SfxId.ExitPlop, s.RenderPos(p), p, SfxScope.RateLimitSeconds);
            }
        }

        private void UpdateCountdown(GameSession s)
        {
            if (!Live || Paused || s.AwaitingStart || s.Sim.Ended) return;
            int left = SecondsLeft(s);
            if (left == lastCountdownSecond) return;
            if (left < lastCountdownSecond && left >= 1 && left <= CountdownSeconds)
            {
                float pitch = left <= CountdownUrgentSeconds ? CountdownUrgentPitch : 1f;
                PlayCue(SfxId.CountdownTick, -1f, pitch, -1, UiPriority);
            }
            lastCountdownSecond = left;
        }

        /// <summary>Whole seconds left as the HUD shows them (ceiling), 0 once the round is over.</summary>
        private static int SecondsLeft(GameSession s)
        {
            double remaining = s.Sim.Config.RoundDuration - s.Sim.Time;
            if (!(remaining > 0.0)) return 0;
            return (int)Math.Ceiling(remaining - 1e-6);
        }

        private void UpdateTension(GameSession s, float dt)
        {
            bool want = false;
            double eta = double.PositiveInfinity;
            float timeScale = 1f;
            int h = HumanIndex;
            if (s != null && !s.IsClosed && Live && !Paused && !s.AwaitingStart && h >= 0 && !s.Sim.Ended)
            {
                PlayerState p = s.Sim.Players[h];
                if (p.Alive && p.Spark != null)
                {
                    want = true;
                    eta = s.Sim.View.SparkCatchEta(h);
                }
                timeScale = s.Runner.TimeScale;
            }
            // A slow motion lowers the loop a little (readability of the first cut); the sim outcome is unchanged.
            float slow = Mathf.Lerp(0.8f, 1f, Mathf.Clamp01(timeScale));
            TensionPitch = SfxSynth.TensionPitch(eta) * slow;
            if (want && !TensionActive)
            {
                RaiseCue(new SfxCue
                {
                    Id = SfxId.SparkLoop, GainDb = 0f, Pitch = TensionPitch, Player = h,
                    Audible = !Muted && loopSource != null && loopSource.clip != null,
                });
            }
            TensionActive = want;
            float target = want ? SfxSynth.TensionVolume(eta) : 0f;
            float speed = target > tensionLevel ? 1f / TensionFadeInSeconds : 1f / TensionFadeOutSeconds;
            tensionLevel = Mathf.MoveTowards(tensionLevel, target, speed * dt);
            ApplyLoop();
        }

        private void ApplyLoop()
        {
            if (loopSource == null || loopSource.clip == null) return;
            if (tensionLevel > 0.001f && !Muted)
            {
                loopSource.volume = BaseVolume(SfxId.SparkLoop) * tensionLevel;
                loopSource.pitch = TensionPitch;
                if (!loopSource.isPlaying) loopSource.Play();
            }
            else if (loopSource.isPlaying) loopSource.Stop();
        }

        private void StopTension(bool immediate)
        {
            TensionActive = false;
            if (!immediate) return;
            tensionLevel = 0f;
            if (loopSource != null && loopSource.isPlaying) loopSource.Stop();
        }

        /// <summary>Makes sure exactly one AudioListener exists: adds one here when the camera has none, removes it when another appears.</summary>
        private void UpdateListener(float dt)
        {
            listenerCheckIn -= dt;
            if (listenerCheckIn > 0f) return;
            listenerCheckIn = 1f;
            AudioListener[] all = FindObjectsByType<AudioListener>(FindObjectsSortMode.None);
            int others = 0;
            foreach (AudioListener l in all)
            {
                if (l != null && l != ownListener && l.isActiveAndEnabled) others++;
            }
            if (others == 0 && ownListener == null) ownListener = gameObject.AddComponent<AudioListener>();
            else if (others > 0 && ownListener != null)
            {
                Destroy(ownListener);
                ownListener = null;
            }
        }

        private void UpdateOutputLog(float dt)
        {
            if (outputProbe == null) outputProbe = new float[512];
            AudioListener.GetOutputData(outputProbe, 0);
            for (int i = 0; i < outputProbe.Length; i++)
            {
                float a = Mathf.Abs(outputProbe[i]);
                if (a > outputPeak) outputPeak = a;
            }
            outputLogIn -= dt;
            if (outputLogIn > 0f) return;
            outputLogIn = 1f;
            int playing = 0;
            if (voices != null)
            {
                foreach (AudioSource v in voices)
                {
                    if (v != null && v.isPlaying) playing++;
                }
            }
            Debug.Log("[Sfx] output peak=" + outputPeak.ToString("0.000", CultureInfo.InvariantCulture) + " voices=" + playing
                      + " loop=" + (loopSource != null && loopSource.isPlaying ? "on" : "off"));
            outputPeak = 0f;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Playback.

        private void PlayUi(SfxId id, float gainDb, float minInterval)
        {
            int k = (int)id;
            if (clock - lastUiCue[k] < minInterval) return;
            lastUiCue[k] = clock;
            PlayCue(id, gainDb, 1f, -1, UiPriority);
        }

        private void PlayCue(SfxId id, float gainDb, float pitch, int player, int priority)
        {
            AudioClip clip = ClipFor(id);
            bool audible = !Muted && clip != null && voices != null;
            RaiseCue(new SfxCue { Id = id, GainDb = gainDb, Pitch = pitch, Player = player, Audible = audible });
            if (!audible) return;
            AudioSource v = TakeVoice();
            if (v == null) return;
            v.Stop();
            v.clip = clip;
            v.volume = Mathf.Clamp01(BaseVolume(id) * SfxScope.DbToGain(gainDb));
            v.pitch = Mathf.Clamp(pitch, 0.25f, 3f);
            v.priority = priority;
            v.Play();
        }

        /// <summary>The clip of a cue: the current biome's set for a biome slot, the shared clip otherwise.</summary>
        private AudioClip ClipFor(SfxId id)
        {
            if (clips == null) return null;
            return IsBiomeSlot(id) ? SlotClip(currentSet, id) : clips[(int)id];
        }

        private AudioSource TakeVoice()
        {
            int best = -1;
            float oldest = float.MaxValue;
            for (int i = 0; i < voices.Length; i++)
            {
                int k = (nextVoice + i) % voices.Length;
                AudioSource v = voices[k];
                if (v == null) continue;
                if (!v.isPlaying)
                {
                    best = k;
                    break;
                }
                if (voiceStart[k] < oldest)
                {
                    oldest = voiceStart[k];
                    best = k;
                }
            }
            if (best < 0) return null;
            nextVoice = (best + 1) % voices.Length;
            voiceStart[best] = clock;
            return voices[best];
        }

        private void RaiseCue(SfxCue cue)
        {
            if (logCues)
            {
                Debug.Log("[Sfx] cue " + cue.Id + " gain=" + cue.GainDb.ToString("0", CultureInfo.InvariantCulture)
                          + "dB pitch=" + cue.Pitch.ToString("0.00", CultureInfo.InvariantCulture) + " player=" + cue.Player
                          + (cue.Audible ? "" : " (muted)"));
            }
            Action<SfxCue> handler = CuePlayed;
            if (handler == null) return;
            try
            {
                handler(cue);
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] Sfx.CuePlayed subscriber failed: " + e);
            }
        }

        private void Pulse(int ms)
        {
            Haptics.Pulse(ms);
            Action<int> handler = HapticPulsed;
            if (handler == null) return;
            try
            {
                handler(ms);
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] Sfx.HapticPulsed subscriber failed: " + e);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Helpers.

        private bool OnScreen(Vector2 p)
        {
            Camera c = cachedCamera;
            if (c == null || !c.isActiveAndEnabled)
            {
                c = Camera.main;
                cachedCamera = c;
            }
            if (c == null) return false;
            Vector3 v = c.WorldToViewportPoint(new Vector3(p.x, p.y, 0f));
            return v.x >= -OnScreenMargin && v.x <= 1f + OnScreenMargin && v.y >= -OnScreenMargin && v.y <= 1f + OnScreenMargin;
        }

        private float Jitter(float center, float spread)
        {
            return center * (1f + spread * (float)(jitter.NextDouble() * 2.0 - 1.0));
        }

        private static Vector2 ToVector(Vec2d p)
        {
            return new Vector2((float)p.X, (float)p.Y);
        }

        private static Vector2 PositionOf(GameSession s, int player, Vec2d fallback)
        {
            if (player >= 0 && player < s.Sim.Players.Count) return ToVector(s.Sim.Players[player].Pos);
            return ToVector(fallback);
        }
    }
}
