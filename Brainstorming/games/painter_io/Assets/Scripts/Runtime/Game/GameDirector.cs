// Owned by BI since wave B-2 (written by B0a). Contract 11.1: the only MonoBehaviour of the scene. Frame settings,
// per-subsystem construction, the state machine (Boot -> Menu -> Playing -> Results), pause, slow motion, the ready gate,
// the results flow and the stats. Contract 25.1: it sets BiomeTheme.Current at each session start (GameSession.Biome,
// else the -biome command line, else SaveData.Biome) and when a biome card is picked in the menu (SelectBiome).
// Wave C (game-flow, robust-04): the screen may sleep and Android renders at 30 fps while the pause panel is up (also after
// an automatic pause); NeverSleep and 60 fps come back when the pause ends (SleepTimeoutFor, AndroidTargetFrameRate).
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace PainterIO.Runtime
{
    public enum GameState { Boot, Menu, Playing, Results }

    /// <summary>What the results screen shows about the human (contract 11.1, 15.5). Built by GameDirector only.</summary>
    public sealed class HumanOutcome
    {
        public int Rank;
        public bool SharedRank;
        public double AreaPercent;
        public RoundEndReason Reason;
        public EliminationCause Cause;
        public int Attacker = -1;
        public double CaughtDistance = -1;
        public int Captures, CutsMade, Kills, PocketsMade;
        public double SurvivedSeconds;
        public bool HadSavedReturn;
        public double LastSavedMargin;   // last chased Return of the round, for the WHY line
    }

    [DefaultExecutionOrder(-100)]
    public sealed class GameDirector : MonoBehaviour
    {
        /// <summary>Real seconds between the human's elimination and the results (a tap skips it).</summary>
        public const float DeathBeatSeconds = 1.0f;
        /// <summary>Real seconds between a round end with the human alive and the results.</summary>
        public const float EndBeatSeconds = 0.6f;
        /// <summary>Ready gate auto-start delay while SaveData.RoundsPlayed &lt; 3.</summary>
        public const float AutoStartDelayFirstRounds = 2.5f;
        /// <summary>Ready gate auto-start delay afterwards, and after a pause.</summary>
        public const float AutoStartDelay = 1.0f;
        /// <summary>Android frame rate while playing or in the menu (contract 11.1), unless -fps is given.</summary>
        public const int AndroidFrameRate = 60;
        /// <summary>Wave C (robust-04): Android frame rate while the pause panel is up, unless -fps is given.</summary>
        public const int AndroidPausedFrameRate = 30;

        public static GameDirector Instance { get; private set; }

        public GameState State { get; private set; } = GameState.Boot;

        /// <summary>Current session (attract or real).</summary>
        public GameSession Session { get; private set; }

        public event Action<GameState> StateChanged;

        /// <summary>Views rebind on this (also raised when an attract session restarts itself).</summary>
        public event Action<GameSession> SessionStarted;

        public bool IsPaused { get; private set; }

        public event Action<bool> PausedChanged;

        /// <summary>Set before ShowResults.</summary>
        public HumanOutcome LastOutcome { get; private set; }

        /// <summary>When true, focus loss and application pause do not pause the round (DevShot, probe, tests).</summary>
        public bool SuppressAutoPause { get; set; }

        /// <summary>The root components returned by the subsystem factories (null results are skipped).</summary>
        public IReadOnlyList<Component> Subsystems => subsystems;

        /// <summary>True between the human's elimination (or the round end) and ShowResults.</summary>
        public bool InResultsBeat => resultsScheduled && !resultsShown;

        private readonly List<Component> subsystems = new List<Component>();

        // Ready gate.
        private float gateTimer;
        private float gateDelay = AutoStartDelayFirstRounds;

        // Slow motion.
        private bool slowActive;
        private float slowScale = 1f, slowStart, slowHold, slowRamp;
        private bool firstCutSlowMoUsed;

        // Results flow.
        private bool resultsScheduled, resultsShown, resultsSkippable;
        private float resultsAt, resultsScheduledAt;
        private int humanCaptures;
        private bool hadSavedReturn;
        private double lastSavedMargin;
        private int caughtAttacker = -1;
        private double caughtDistance = -1;

        private bool updateErrorLogged;
        private bool biomePicked;   // a menu pick wins over the -biome command line for the rest of the run
        private EuropeCatalog.Country selectedCountry;

        // ------------------------------------------------------------------------------------------------------------
        // Lifecycle.

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Debug.LogWarning("[PainterIO] a second GameDirector was created; it is destroyed");
                Destroy(gameObject);
                return;
            }
            Instance = this;
            transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            transform.localScale = Vector3.one;

            Guard("FrameSettings", ApplyFrameSettings);
            Guard("Biome", () => BiomeTheme.SetCurrent(ResolveBiome(null)));
            Build("CameraRig", () => CameraRig.Create(this));
            Build("LiquidRenderer", () => LiquidRenderer.Create(this));
            Build("ActorViews", () => ActorViews.Create(this));
            Build("SteeringInput", () => SteeringInput.Create(this));
            Build("UiRoot", () => UiRoot.Create(this));
            Build("Sfx", () => Sfx.Create(this));
            Build("BiomeFx", () => BiomeFx.Create(this));
            Build("PlayerProbe", () => PlayerProbe.TryCreate(this));
            Build("DevShot", () => DevShot.TryCreate(this));
            Build("EuropeShot", () => EuropeShot.TryCreate(this));
            Guard("Menu", ToMenu);
        }

        private void OnDestroy()
        {
            if (Instance != this) return;
            if (Session != null)
            {
                Session.EventRaised -= OnSessionEvent;
                Session.Restarted -= OnSessionRestarted;
                Session.Close();
            }
            foreach (Component c in subsystems)
            {
                if (c != null && c.gameObject != gameObject && c.transform.parent != transform) Destroy(c.gameObject);
            }
            subsystems.Clear();
            Instance = null;
            try
            {
                Screen.sleepTimeout = SleepTimeout.SystemSetting;
            }
            catch (Exception)
            {
                // Not fatal while tearing down.
            }
        }

        private void Update()
        {
            GameSession s = Session;
            if (s == null) return;
            float dt = Time.unscaledDeltaTime;
            try
            {
                UpdateReadyGate(s, dt);
                UpdateSlowMo(s);
                s.Advance(dt);
                UpdateResultsFlow();
            }
            catch (Exception e)
            {
                if (!updateErrorLogged)
                {
                    updateErrorLogged = true;
                    Debug.LogError("[PainterIO] GameDirector update failed: " + e);
                }
            }
        }

        private void OnApplicationPause(bool pause)
        {
            if (!pause) return;
            SaveData.Flush();
            AutoPause();
        }

        private void OnApplicationFocus(bool focus)
        {
            if (!focus) AutoPause();
        }

        // ------------------------------------------------------------------------------------------------------------
        // Public flow.

        /// <summary>New real session (human + 3 bots) from SaveData, State = Playing.</summary>
        public void StartRound()
        {
            try
            {
                ulong seed = (ulong)DateTime.UtcNow.Ticks;
                bool lasso = LaunchArgs.Lasso ?? SaveData.LassoOn;
                SetSession(GameSession.CreateRound(seed, lasso, selectedCountry), GameState.Playing);
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] StartRound failed: " + e);
            }
        }

        public void StartCountry(EuropeCatalog.Country country)
        {
            selectedCountry = country;
            StartRound();
        }

        /// <summary>Starts a prepared real session (DevShot, probe), State = Playing. The session keeps its own AwaitingStart.</summary>
        public void StartRound(GameSession session)
        {
            if (session == null) throw new ArgumentNullException(nameof(session));
            if (session.IsAttract) throw new ArgumentException("StartRound needs a non-attract session", nameof(session));
            SetSession(session, GameState.Playing);
        }

        /// <summary>Attract session behind the menu, State = Menu.</summary>
        public void ToMenu()
        {
            try
            {
                SetSession(GameSession.CreateAttract((ulong)DateTime.UtcNow.Ticks), GameState.Menu);
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] ToMenu failed: " + e);
            }
        }

        /// <summary>
        /// Contract 25.1: a biome card was picked in the menu. Saves it (SaveData.Biome) and makes it current at once: the
        /// attract match behind the menu switches biome without a restart (views re-bind on BiomeTheme.Changed).
        /// </summary>
        public void SelectBiome(BiomeId biome)
        {
            BiomeId id = BiomeTheme.Clamp((int)biome);
            biomePicked = true;
            SaveData.Biome = (int)id;
            if (Session != null) Session.Biome = null;
            BiomeTheme.SetCurrent(id);
        }

        /// <summary>The biome a session plays in: its own Biome, else -biome (until a menu pick), else SaveData.Biome.</summary>
        public BiomeId ResolveBiome(GameSession s)
        {
            if (s != null && s.Biome.HasValue) return BiomeTheme.Clamp((int)s.Biome.Value);
            if (!biomePicked && LaunchArgs.Biome.HasValue) return LaunchArgs.Biome.Value;
            return BiomeTheme.Clamp(SaveData.Biome);
        }

        /// <summary>Called ONLY by GameDirector itself (results flow, contract 11.1).</summary>
        public void ShowResults()
        {
            GameSession s = Session;
            if (s == null || s.IsAttract || State != GameState.Playing || resultsShown) return;
            if (LastOutcome == null) LastOutcome = BuildOutcome(s, !s.HumanAlive);
            resultsShown = true;
            ForceUnpause();
            SetState(GameState.Results);
            Guard("RecordStats", () => RecordStats(s, LastOutcome));
            Guard("EuropeProgress", () => EuropeProgress.OnRoundResults(s, LastOutcome, selectedCountry));
            SaveData.Flush();
        }

        /// <summary>Only while State == Playing in a non-attract session with the human alive; sets Runner.Paused.
        /// Leaving pause goes back through the ready gate (AwaitingStart, resumes on input or after 1.0 s).</summary>
        public void SetPaused(bool paused)
        {
            if (paused == IsPaused) return;
            GameSession s = Session;
            if (paused)
            {
                if (s == null || s.IsAttract || State != GameState.Playing || !s.HumanAlive || s.Sim.Ended || resultsScheduled) return;
                IsPaused = true;
                s.Runner.Paused = true;
            }
            else
            {
                IsPaused = false;
                if (s != null && !s.IsAttract && State == GameState.Playing && !s.IsClosed)
                {
                    s.AwaitStart();
                    gateTimer = 0f;
                    gateDelay = AutoStartDelay;
                }
            }
            ApplyPauseSettings();
            RaisePausedChanged(paused);
        }

        /// <summary>Runner.TimeScale = timeScale for holdSeconds of real time, then a linear ramp back to 1 over rampSeconds.</summary>
        public void SlowMo(float timeScale, float holdSeconds, float rampSeconds)
        {
            slowScale = Mathf.Clamp(float.IsNaN(timeScale) ? 1f : timeScale, 0.02f, 1f);
            slowHold = Mathf.Max(0f, holdSeconds);
            slowRamp = Mathf.Max(0f, rampSeconds);
            slowStart = Time.unscaledTime;
            slowActive = true;
            if (Session != null) Session.Runner.TimeScale = slowScale;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Internals.

        private void SetSession(GameSession next, GameState state)
        {
            GameSession old = Session;
            if (old != null)
            {
                old.EventRaised -= OnSessionEvent;
                old.Restarted -= OnSessionRestarted;
                old.Close();
            }
            ForceUnpause();
            Guard("FrameRate", () => ApplyTargetFrameRate(false));   // StartRound, ToMenu: never left at the pause rate
            slowActive = false;
            firstCutSlowMoUsed = false;
            resultsScheduled = resultsShown = resultsSkippable = false;
            humanCaptures = 0;
            hadSavedReturn = false;
            lastSavedMargin = 0.0;
            caughtAttacker = -1;
            caughtDistance = -1;
            LastOutcome = null;
            updateErrorLogged = false;
            gateTimer = 0f;
            gateDelay = SaveData.RoundsPlayed < 3 ? AutoStartDelayFirstRounds : AutoStartDelay;

            Session = next;
            next.Runner.TimeScale = 1f;
            Guard("Biome", () => BiomeTheme.SetCurrent(ResolveBiome(next)));
            next.EventRaised += OnSessionEvent;
            next.Restarted += OnSessionRestarted;
            RaiseSessionStarted(next);
            SetState(state);
        }

        private void SetState(GameState state)
        {
            State = state;
            ApplySleepTimeout();
            Action<GameState> handler = StateChanged;
            if (handler == null) return;
            foreach (Delegate d in handler.GetInvocationList())
            {
                try
                {
                    ((Action<GameState>)d)(state);
                }
                catch (Exception e)
                {
                    Debug.LogError("[PainterIO] StateChanged subscriber failed: " + e);
                }
            }
        }

        private void RaiseSessionStarted(GameSession s)
        {
            Action<GameSession> handler = SessionStarted;
            if (handler == null) return;
            foreach (Delegate d in handler.GetInvocationList())
            {
                try
                {
                    ((Action<GameSession>)d)(s);
                }
                catch (Exception e)
                {
                    Debug.LogError("[PainterIO] SessionStarted subscriber failed: " + e);
                }
            }
        }

        private void RaisePausedChanged(bool paused)
        {
            Action<bool> handler = PausedChanged;
            if (handler == null) return;
            foreach (Delegate d in handler.GetInvocationList())
            {
                try
                {
                    ((Action<bool>)d)(paused);
                }
                catch (Exception e)
                {
                    Debug.LogError("[PainterIO] PausedChanged subscriber failed: " + e);
                }
            }
        }

        private void ForceUnpause()
        {
            if (!IsPaused) return;
            IsPaused = false;
            ApplyPauseSettings();
            RaisePausedChanged(false);
        }

        /// <summary>Wave C (robust-04): sleep timeout and Android frame rate after every change of IsPaused.</summary>
        private void ApplyPauseSettings()
        {
            ApplySleepTimeout();
            Guard("FrameRate", () => ApplyTargetFrameRate(IsPaused));
        }

        private void OnSessionRestarted(GameSession s)
        {
            if (s == Session) RaiseSessionStarted(s);
        }

        private void AutoPause()
        {
            if (SuppressAutoPause || Application.isBatchMode) return;
            if (State == GameState.Playing && Session != null && !Session.IsAttract) SetPaused(true);
        }

        private void UpdateReadyGate(GameSession s, float dt)
        {
            if (!s.AwaitingStart || IsPaused || State != GameState.Playing) return;
            gateTimer += dt;
            bool steered = s.HumanController != null && s.HumanController.Desired.HasValue;
            if (steered || gateTimer >= gateDelay) s.Begin();
        }

        private void UpdateSlowMo(GameSession s)
        {
            if (!slowActive) return;
            float t = Time.unscaledTime - slowStart;
            float scale;
            if (t < slowHold) scale = slowScale;
            else if (slowRamp > 0f && t < slowHold + slowRamp) scale = Mathf.Lerp(slowScale, 1f, (t - slowHold) / slowRamp);
            else
            {
                scale = 1f;
                slowActive = false;
            }
            s.Runner.TimeScale = scale;
        }

        private void UpdateResultsFlow()
        {
            if (!resultsScheduled || resultsShown) return;
            float now = Time.unscaledTime;
            bool skip = resultsSkippable && now - resultsScheduledAt > 0.15f && TapThisFrame();
            if (now >= resultsAt || skip) ShowResults();
        }

        private static bool TapThisFrame()
        {
            try
            {
                Pointer p = Pointer.current;
                return p != null && p.press.wasPressedThisFrame;
            }
            catch (Exception)
            {
                return false;
            }
        }

        private void ScheduleResults(float delay, bool skippable)
        {
            if (resultsScheduled) return;
            resultsScheduled = true;
            resultsSkippable = skippable;
            resultsScheduledAt = Time.unscaledTime;
            resultsAt = resultsScheduledAt + delay;
        }

        private void OnSessionEvent(SimEvent e)
        {
            GameSession s = Session;
            if (s == null || s.IsAttract || State != GameState.Playing) return;
            int h = s.HumanIndex;
            if (h < 0) return;
            switch (e.Type)
            {
                case SimEventType.Cut:
                    if (e.Player == h)
                    {
                        if (!SaveData.TutCutDone && !firstCutSlowMoUsed)
                        {
                            firstCutSlowMoUsed = true;
                            SlowMo(0.3f, 1.2f, 0.3f);
                        }
                        else SlowMo(0.25f, 0.12f, 0.08f);
                    }
                    else if (e.Other == h && s.HumanAlive) SlowMo(0.25f, 0.08f, 0.05f);
                    break;
                case SimEventType.Return:
                    if (e.Player != h) break;
                    if (e.Cells != null && e.Cells.Length > 0) humanCaptures++;
                    if (e.Chased && !s.IsFlickerReturn(e))
                    {
                        hadSavedReturn = true;
                        lastSavedMargin = e.Margin;
                    }
                    break;
                case SimEventType.SparkCaught:
                    if (e.Player == h)
                    {
                        caughtAttacker = e.Other;
                        caughtDistance = e.DistanceHome;
                    }
                    break;
                case SimEventType.Eliminated:
                    if (e.Player == h && !resultsScheduled)
                    {
                        if (e.Cause != EliminationCause.Spark) caughtAttacker = e.Other;
                        LastOutcome = BuildOutcome(s, true);
                        ScheduleResults(DeathBeatSeconds, true);
                    }
                    break;
                case SimEventType.RoundEnded:
                    if (!resultsScheduled && s.HumanAlive)
                    {
                        LastOutcome = BuildOutcome(s, false);
                        ScheduleResults(EndBeatSeconds, false);
                    }
                    else if (LastOutcome != null && s.Sim.Result != null && !resultsShown)
                    {
                        LastOutcome.Reason = s.Sim.Result.Reason;
                    }
                    break;
            }
        }

        private HumanOutcome BuildOutcome(GameSession s, bool eliminated)
        {
            Simulation sim = s.Sim;
            int h = s.HumanIndex;
            PlayerState p = sim.Players[h];
            var o = new HumanOutcome { Rank = sim.RankOf(h) };
            for (int j = 0; j < sim.Players.Count; j++)
            {
                if (j != h && sim.RankOf(j) == o.Rank) o.SharedRank = true;
            }
            int arena = sim.Grid.ArenaCellCount;
            int cells;
            if (eliminated) cells = p.FinalCells;
            else if (sim.Result != null) cells = sim.Result.FinalCells[h];
            else cells = sim.Grid.CountOf(p.Id);
            o.AreaPercent = arena > 0 ? 100.0 * cells / arena : 0.0;
            o.Reason = sim.Ended && sim.Result != null ? sim.Result.Reason : RoundEndReason.None;
            o.Cause = eliminated ? p.Cause : EliminationCause.None;
            if (eliminated)
            {
                o.Attacker = caughtAttacker;
                o.CaughtDistance = p.Cause == EliminationCause.Spark ? caughtDistance : -1;
            }
            o.Captures = humanCaptures;
            o.CutsMade = p.CutsMade;
            o.Kills = p.Kills;
            o.PocketsMade = p.PocketsMade;
            if (eliminated) o.SurvivedSeconds = double.IsNaN(p.EliminatedAt) ? sim.Time : p.EliminatedAt;
            else o.SurvivedSeconds = sim.Result != null ? sim.Result.EndTime : sim.Time;
            o.HadSavedReturn = hadSavedReturn;
            o.LastSavedMargin = lastSavedMargin;
            return o;
        }

        private static void RecordStats(GameSession s, HumanOutcome o)
        {
            if (o == null || !s.CountsForStats) return;
            if (SaveData.TuningModified || LaunchArgs.HasTuningOverride) return;
            if (o.AreaPercent > SaveData.BestArea) SaveData.BestArea = (float)o.AreaPercent;
            if (o.Rank == 1) SaveData.Wins = SaveData.Wins + 1;
            SaveData.RoundsPlayed = SaveData.RoundsPlayed + 1;
        }

        private void ApplyFrameSettings()
        {
            int fps = LaunchArgs.Fps;
#if UNITY_ANDROID && !UNITY_EDITOR
            QualitySettings.vSyncCount = 0;
            ApplyTargetFrameRate(IsPaused);
            if (Screen.height > 1920)
            {
                var urp = GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
                if (urp != null) urp.renderScale = Mathf.Min(urp.renderScale, 1920f / Screen.height);
            }
#else
            if (fps > 0)
            {
                QualitySettings.vSyncCount = 0;
                Application.targetFrameRate = fps;
            }
            else
            {
                QualitySettings.vSyncCount = 1;
                Application.targetFrameRate = -1;
            }
#endif
            ApplySleepTimeout();
        }

        /// <summary>
        /// Wave C (robust-04): SleepTimeout.NeverSleep only while a round is played and not paused (the pause panel, also
        /// after an automatic pause, lets the screen sleep), SleepTimeout.SystemSetting otherwise.
        /// </summary>
        public static int SleepTimeoutFor(GameState state, bool paused)
        {
            return state == GameState.Playing && !paused ? SleepTimeout.NeverSleep : SleepTimeout.SystemSetting;
        }

        /// <summary>
        /// Wave C (robust-04): the Android frame rate. The -fps value when given, else 30 while paused and 60 otherwise.
        /// (Windows stays on vSync, see ApplyFrameSettings.)
        /// </summary>
        public static int AndroidTargetFrameRate(int fpsArg, bool paused)
        {
            if (fpsArg > 0) return fpsArg;
            return paused ? AndroidPausedFrameRate : AndroidFrameRate;
        }

        /// <summary>
        /// Application.targetFrameRate on Android only (AndroidTargetFrameRate); nothing elsewhere. Never touches the
        /// renderScale or vSync lines of ApplyFrameSettings.
        /// </summary>
        private static void ApplyTargetFrameRate(bool paused)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            int target = AndroidTargetFrameRate(LaunchArgs.Fps, paused);
            if (Application.targetFrameRate != target) Application.targetFrameRate = target;
#endif
        }

        private void ApplySleepTimeout()
        {
            try
            {
                Screen.sleepTimeout = SleepTimeoutFor(State, IsPaused);
            }
            catch (Exception e)
            {
                Debug.LogWarning("[PainterIO] sleep timeout: " + e.Message);
            }
        }

        private void Build(string subsystem, Func<Component> factory)
        {
            try
            {
                Component root = factory();
                if (root == null) return;
                subsystems.Add(root);
                if (root.gameObject != gameObject && root.transform.parent == null) root.transform.SetParent(transform, true);
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] " + subsystem + " failed: " + e);
            }
        }

        private static void Guard(string subsystem, Action action)
        {
            try
            {
                action();
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] " + subsystem + " failed: " + e);
            }
        }
    }
}
