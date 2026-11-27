// Owned by BI since wave B-2 (written by B0a). Contract 11.2 (GameSession, round and attract factories) and 23.3 (bot seeds, lineups, Exit/Return
// debounce helpers). Also holds LaunchArgs, the command-line reader shared by GameDirector, DevShot and the probe.
// Wave D-2 (traits-infra, docs/BIOME_TRAITS.md section 5): CreateRound / CreateAttract set SimConfig.Traits to
// BiomeTraitTable.Resolve(the biome being played); the attract match restarts itself when its traits change
// (RefreshAttractTraits); LaunchArgs reads -classic, -traits "<key>" and -trait <Id>=0|1.
using System;
using System.Collections.Generic;
using System.Globalization;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    /// <summary>
    /// One running Simulation with its runner, its human input and its event forwarding. Events of a Step are forwarded
    /// AFTER Sim.Step returns, in resolution order, during Runner.Advance; each subscriber runs in its own try/catch.
    /// </summary>
    public sealed class GameSession
    {
        /// <summary>23.3 debounce: an exit shorter than this whose Return has no cells is presentation noise.</summary>
        public const double FlickerSeconds = 0.25;

        /// <summary>23.3: the pearl detach starts when the trail is longer than this (or the exit lasted FlickerSeconds).</summary>
        public const double DetachTrailLength = 0.35;

        /// <summary>Real seconds an ended attract round stays on screen before the next one starts.</summary>
        public const float AttractRestartDelay = 2.0f;

        private readonly IController[] controllers;
        private readonly SimConfig config;
        private readonly SimSetup setup;
        private readonly HashSet<Delegate> loggedSubscribers = new HashSet<Delegate>();
        private double[] exitStart;
        private double[] lastExitDuration;
        private bool closed;
        private float endedFor;
        private int attractRound;

        public GameSession(SimConfig config, SimSetup setup, IController[] controllers, bool isAttract)
        {
            if (config == null) throw new ArgumentNullException(nameof(config));
            if (controllers == null) throw new ArgumentNullException(nameof(controllers));
            this.config = config.Clone();
            this.setup = setup;
            this.controllers = (IController[])controllers.Clone();
            IsAttract = isAttract;
            Sim = new Simulation(this.config, this.controllers, setup);
            int human = setup != null ? setup.HumanIndex : 0;
            HumanIndex = isAttract || human < 0 || human >= Sim.Players.Count ? -1 : human;
            HumanController = HumanIndex >= 0 ? this.controllers[HumanIndex] as ExternalController : null;
            AwaitingStart = false;
            BindRunner(new SimRunner(Sim));
        }

        public Simulation Sim { get; private set; }
        public bool IsAttract { get; }

        /// <summary>-1 in attract.</summary>
        public int HumanIndex { get; }

        /// <summary>The human's ExternalController; null in attract (and in scripted sessions whose human is scripted).</summary>
        public ExternalController HumanController { get; }

        public SimRunner Runner { get; private set; }

        /// <summary>True for rounds started by StartRound: their results update SaveData stats. False for attract,
        /// probe, DevShot and test sessions.</summary>
        public bool CountsForStats { get; set; }

        /// <summary>
        /// Contract 25.1: a biome forced for this session (probe, tests, DemoScenario.CreateSession(out m, biome)); null
        /// follows the -biome command line, else SaveData.Biome. GameDirector applies it when the session starts.
        /// </summary>
        public BiomeId? Biome { get; set; }

        /// <summary>Forwarded after each Sim.Step returns, in resolution order, during Runner.Advance (per-subscriber try/catch).</summary>
        public event Action<SimEvent> EventRaised;

        /// <summary>Raised when an attract session replaced its ended Simulation by a new one (views rebind).</summary>
        public event Action<GameSession> Restarted;

        /// <summary>Interpolation factor between PrevPos and Pos for rendering.</summary>
        public float Alpha => Runner.Alpha;

        /// <summary>Lerp(PrevPos, Pos, Alpha) in Unity units.</summary>
        public Vector2 RenderPos(int player)
        {
            PlayerState p = Sim.Players[player];
            double a = Runner.Alpha;
            return new Vector2((float)(p.PrevPos.X + (p.Pos.X - p.PrevPos.X) * a),
                               (float)(p.PrevPos.Y + (p.Pos.Y - p.PrevPos.Y) * a));
        }

        /// <summary>Lerp(Spark.PrevS, Spark.S, Alpha), same Alpha as RenderPos; NaN when the player has no spark.</summary>
        public double RenderSparkS(int player)
        {
            Spark s = Sim.Players[player].Spark;
            if (s == null) return double.NaN;
            return s.PrevS + (s.S - s.PrevS) * Runner.Alpha;
        }

        public bool HumanAlive => HumanIndex >= 0 && Sim.Players[HumanIndex].Alive;

        /// <summary>Wave D-2: the trait set of the running simulation (Sim.Config.Traits; classic = no trait).</summary>
        public RuleTraits Traits => Sim.Config.Traits ?? RuleTraits.Classic;

        /// <summary>
        /// Wave D-2 (BIOME_TRAITS 5: matrix and option changes apply to the attract match immediately): an attract session
        /// whose traits differ from BiomeTraitTable.Resolve(the current biome) replaces its simulation now (like the
        /// restart after a round end: Restarted is raised). Returns true when it restarted. No-op for other sessions.
        /// </summary>
        public bool RefreshAttractTraits()
        {
            if (!IsAttract || closed) return false;
            RuleTraits wanted = BiomeTraitTable.Resolve(ActiveBiome());
            if (wanted.Equals(Traits)) return false;
            RestartAttract();
            return true;
        }

        /// <summary>True while the round waits for the human (Runner.Paused).</summary>
        public bool AwaitingStart { get; private set; }

        /// <summary>Clears AwaitingStart and unpauses (unless GameDirector is paused).</summary>
        public void Begin()
        {
            if (closed) return;
            AwaitingStart = false;
            GameDirector d = GameDirector.Instance;
            Runner.Paused = d != null && d.Session == this && d.IsPaused;
        }

        /// <summary>
        /// Enters the ready gate (contract 11.2): AwaitingStart = true, Runner.Paused = true and HumanController.Desired =
        /// null, so the next deliberate steering input (or GameDirector's auto-start delay) calls Begin. Used by
        /// CreateRound and by GameDirector when a pause ends.
        /// </summary>
        public void AwaitStart()
        {
            if (closed) return;
            AwaitingStart = true;
            Runner.Paused = true;
            if (HumanController != null) HumanController.Desired = null;
        }

        /// <summary>
        /// Frame driver used by GameDirector: Runner.Advance(deltaTime) plus the endless attract restart. Returns the steps.
        /// </summary>
        public int Advance(float deltaTime)
        {
            if (closed) return 0;
            int steps = Runner.Advance(deltaTime);
            if (IsAttract && Sim.Ended && !closed)
            {
                endedFor += Mathf.Max(0f, deltaTime);
                if (endedFor >= AttractRestartDelay) RestartAttract();
            }
            return steps;
        }

        /// <summary>Stops the runner and drops every subscriber (GameDirector calls it when it replaces the session).</summary>
        public void Close()
        {
            if (closed) return;
            closed = true;
            Runner.Paused = true;
            EventRaised = null;
            Restarted = null;
        }

        public bool IsClosed => closed;

        // ------------------------------------------------------------------------------------------------------------
        // 23.3 Exit/Return debounce helpers (views, sounds, haptics, toasts and HumanOutcome share them).

        /// <summary>Sim time at which the player's current exit started; NaN when home or eliminated.</summary>
        public double ExitStartTime(int player)
        {
            return exitStart != null && player >= 0 && player < exitStart.Length ? exitStart[player] : double.NaN;
        }

        /// <summary>Seconds the player's current exit has lasted (0 when home).</summary>
        public double ExitAge(int player)
        {
            double start = ExitStartTime(player);
            return double.IsNaN(start) ? 0.0 : Math.Max(0.0, Sim.Time - start);
        }

        /// <summary>23.3: the pearl visibly left its puddle (trail longer than 0.35 u or exit older than 0.25 s).</summary>
        public bool HasVisibleDetach(int player)
        {
            PlayerState p = Sim.Players[player];
            if (!p.Alive || p.Home) return false;
            return p.Trail.Length > DetachTrailLength || ExitAge(player) >= FlickerSeconds;
        }

        /// <summary>
        /// 23.3: true for a Return that presentation and stats ignore: no captured cells, not chased, and its exit lasted
        /// less than FlickerSeconds (the diagonal-edge flicker of wave A). Valid while the event is being forwarded and
        /// until the player's next Return.
        /// </summary>
        public bool IsFlickerReturn(SimEvent e)
        {
            if (e == null || e.Type != SimEventType.Return) return false;
            if (e.Cells != null && e.Cells.Length > 0) return false;
            if (e.Chased) return false;
            if (lastExitDuration == null || e.Player < 0 || e.Player >= lastExitDuration.Length) return false;
            return lastExitDuration[e.Player] < FlickerSeconds;
        }

        /// <summary>Duration of the exit closed by the player's last Return (NaN before any).</summary>
        public double LastExitDuration(int player)
        {
            return lastExitDuration != null && player >= 0 && player < lastExitDuration.Length ? lastExitDuration[player] : double.NaN;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Factories.

        /// <summary>
        /// A real round: human index 0 (ExternalController, Desired = null) + bots 1..3 (Balanced, Greedy, Aggressive).
        /// Config from Tuning, then the SaveData test settings, then the command-line overrides, then the traits of the
        /// biome being played (BiomeTraitTable.Resolve(ActiveBiome())); AwaitingStart = true.
        /// </summary>
        public static GameSession CreateRound(ulong seed, bool lassoEnabled, EuropeCatalog.Country country = null)
        {
            SimConfig config = RoundConfig(seed, lassoEnabled);
            var controllers = new IController[Tuning.PlayerCount];
            controllers[0] = new ExternalController();
            BotStyle[] lineup = { BotStyle.Balanced, BotStyle.Greedy, BotStyle.Aggressive };
            bool gentle = !SaveData.TutExitDone;
            for (int i = 1; i < controllers.Length; i++)
            {
                BotPersonality personality = BotPersonality.Preset(lineup[(i - 1) % lineup.Length]);
                if (gentle) personality.HumanAttackScale = 0.3;
                controllers[i] = new BotController(personality, BotSeed(seed, i));
            }
            var setup = new SimSetup
            {
                PlayerCount = controllers.Length,
                Names = DefaultNames(controllers.Length, 0),
                HumanIndex = 0,
            };
            country?.Configure(config, setup);
            var session = new GameSession(config, setup, controllers, false) { CountsForStats = true };
            session.AwaitStart();
            return session;
        }

        /// <summary>
        /// 4 bots (Balanced, Balanced, Greedy, Aggressive), endless: restarts itself on round end. Wave D-2: with the
        /// traits of the selected biome (BiomeTraitTable.Resolve(ActiveBiome())), re-resolved at every restart.
        /// </summary>
        public static GameSession CreateAttract(ulong seed)
        {
            return new GameSession(AttractConfig(seed), AttractSetup(), AttractControllers(seed), true);
        }

        /// <summary>23.3 bot seed rule: roundSeed * 7919 + i * 104729 + 17 (unchecked).</summary>
        public static ulong BotSeed(ulong roundSeed, int playerIndex)
        {
            unchecked
            {
                return roundSeed * 7919UL + (ulong)playerIndex * 104729UL + 17UL;
            }
        }

        /// <summary>
        /// The biome a new round or attract match plays in: GameDirector.ResolveBiome(null) (the -biome command line until
        /// a menu pick, else SaveData.Biome); without a director, -biome else SaveData.Biome.
        /// </summary>
        public static BiomeId ActiveBiome()
        {
            GameDirector d = GameDirector.Instance;
            if (d != null) return d.ResolveBiome(null);
            return LaunchArgs.Biome ?? BiomeTheme.Clamp(SaveData.Biome);
        }

        /// <summary>
        /// The config of a real round (also used by tests): see CreateRound. Traits = BiomeTraitTable.Resolve(ActiveBiome()).
        /// Always built from scratch (never from a previous Simulation.Config, which carries applied config traits).
        /// </summary>
        public static SimConfig RoundConfig(ulong seed, bool lassoEnabled)
        {
            return RoundConfig(seed, lassoEnabled, BiomeTraitTable.Resolve(ActiveBiome()));
        }

        /// <summary>The config of a real round with an explicit trait set (null = classic): the probe's bot round, tests.</summary>
        public static SimConfig RoundConfig(ulong seed, bool lassoEnabled, RuleTraits traits)
        {
            var config = new SimConfig { Seed = seed, Traits = traits ?? RuleTraits.Classic };
            // SaveData stores floats: round back to the setting's step so the default 1.8f gives exactly Tuning's 1.8.
            config.SparkSpeedFactor = FromSetting(SaveData.SparkFactor);
            config.RoundDuration = FromSetting(SaveData.RoundSeconds);
            config.LassoFirstSpawn = FromSetting(SaveData.RingDelay);
            config.LassoRespawn = config.LassoFirstSpawn;
            if (LaunchArgs.SparkFactor.HasValue) config.SparkSpeedFactor = LaunchArgs.SparkFactor.Value;
            if (LaunchArgs.RoundDuration.HasValue) config.RoundDuration = LaunchArgs.RoundDuration.Value;
            if (LaunchArgs.RingInterval.HasValue)
            {
                config.LassoFirstSpawn = LaunchArgs.RingInterval.Value;
                config.LassoRespawn = LaunchArgs.RingInterval.Value;
            }
            config.LassoEnabled = lassoEnabled;
            config.BorderRide = BorderRideRule.On;   // rule v1.9 (contract 33): the border ride is on in the game
            return config;
        }

        /// <summary>Player names: the human is "Toi" (EN "You"), each bot is named after its displayed color.</summary>
        public static string[] DefaultNames(int playerCount, int humanIndex)
        {
            var names = new string[playerCount];
            for (int i = 0; i < playerCount; i++)
            {
                names[i] = i == humanIndex
                    ? Strings.Get(Palette.HumanNameKey)
                    : Strings.Get(Palette.ColorNameKey(Palette.ColorIndexOf(i)));
            }
            return names;
        }

        /// <summary>A float test setting as the double it stands for (every setting step is a multiple of 0.1).</summary>
        private static double FromSetting(float value)
        {
            return Math.Round((double)value, 3);
        }

        private static SimConfig AttractConfig(ulong seed)
        {
            return new SimConfig { Seed = seed, LassoEnabled = SaveData.LassoOn, Traits = BiomeTraitTable.Resolve(ActiveBiome()) };
        }

        private static SimSetup AttractSetup()
        {
            return new SimSetup { PlayerCount = Tuning.PlayerCount, Names = DefaultNames(Tuning.PlayerCount, -1), HumanIndex = -1 };
        }

        private static IController[] AttractControllers(ulong seed)
        {
            BotStyle[] lineup = { BotStyle.Balanced, BotStyle.Balanced, BotStyle.Greedy, BotStyle.Aggressive };
            var controllers = new IController[Tuning.PlayerCount];
            for (int i = 0; i < controllers.Length; i++)
            {
                controllers[i] = new BotController(BotPersonality.Preset(lineup[i % lineup.Length]), BotSeed(seed, i));
            }
            return controllers;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Internals.

        private void RestartAttract()
        {
            attractRound++;
            ulong seed;
            unchecked
            {
                seed = config.Seed + (ulong)attractRound * 0x9E3779B97F4A7C15UL;
            }
            SimConfig next = AttractConfig(seed);
            SimRunner old = Runner;
            Sim = new Simulation(next, AttractControllers(seed), AttractSetup());
            var runner = new SimRunner(Sim) { Paused = old.Paused, TimeScale = old.TimeScale };
            old.Stepped -= OnStepped;
            BindRunner(runner);
            endedFor = 0f;
            Action<GameSession> handler = Restarted;
            if (handler == null) return;
            foreach (Delegate d in handler.GetInvocationList())
            {
                try
                {
                    ((Action<GameSession>)d)(this);
                }
                catch (Exception e)
                {
                    LogSubscriberOnce(d, "Restarted", e);
                }
            }
        }

        private void BindRunner(SimRunner runner)
        {
            Runner = runner;
            int n = Sim.Players.Count;
            exitStart = new double[n];
            lastExitDuration = new double[n];
            for (int i = 0; i < n; i++)
            {
                exitStart[i] = Sim.Players[i].Home ? double.NaN : Sim.Time;
                lastExitDuration[i] = double.NaN;
            }
            runner.Stepped += OnStepped;
        }

        private void OnStepped(Simulation sim)
        {
            if (closed || sim != Sim) return;
            IReadOnlyList<SimEvent> events = sim.LastEvents;
            int count = events.Count;
            if (count == 0) return;
            // Copy first: a handler may stop the session, and LastEvents is reused by the next Step.
            var batch = new SimEvent[count];
            for (int k = 0; k < count; k++) batch[k] = events[k];
            for (int k = 0; k < batch.Length; k++)
            {
                SimEvent e = batch[k];
                Track(e);
                Action<SimEvent> handler = EventRaised;
                if (handler == null || closed) continue;
                foreach (Delegate d in handler.GetInvocationList())
                {
                    try
                    {
                        ((Action<SimEvent>)d)(e);
                    }
                    catch (Exception ex)
                    {
                        LogSubscriberOnce(d, e.Type.ToString(), ex);
                    }
                }
            }
        }

        private void Track(SimEvent e)
        {
            int p = e.Player;
            if (p < 0 || p >= exitStart.Length) return;
            switch (e.Type)
            {
                case SimEventType.Exit:
                    exitStart[p] = e.Time;
                    break;
                case SimEventType.Return:
                    lastExitDuration[p] = double.IsNaN(exitStart[p]) ? double.PositiveInfinity : e.Time - exitStart[p];
                    exitStart[p] = double.NaN;
                    break;
                case SimEventType.Eliminated:
                    exitStart[p] = double.NaN;
                    break;
            }
        }

        private void LogSubscriberOnce(Delegate d, string what, Exception e)
        {
            if (!loggedSubscribers.Add(d)) return;
            string name = d.Method != null ? d.Method.DeclaringType?.Name + "." + d.Method.Name : "?";
            Debug.LogError("[PainterIO] GameSession subscriber " + name + " failed on " + what + ": " + e);
        }
    }

    /// <summary>
    /// Command-line options of the player (Windows; harmless elsewhere): -fps n, -lasso 0|1, -sparkFactor x,
    /// -roundDuration s, -ringInterval s, -biome liquid|fire|electric, -devshot dir, -probe, -mute. Wave D-2
    /// (BIOME_TRAITS 5): -classic, -traits "&lt;RuleTraits key&gt;" (or "default": the biome's line of the table) and
    /// -trait &lt;Id&gt;=0|1 (repeatable). Parsed once; tests may call Reload.
    /// </summary>
    public static class LaunchArgs
    {
        private static string[] args;
        private static bool parsed;
        private static int fps;
        private static bool? lasso;
        private static double? sparkFactor, roundDuration, ringInterval;
        private static BiomeId? biome;
        private static bool classic;
        private static string traitsKey;
        private static List<KeyValuePair<TraitId, bool>> traitToggles = new List<KeyValuePair<TraitId, bool>>();
        private static string traitArgsError;

        /// <summary>-fps n (0 when absent).</summary>
        public static int Fps { get { Parse(); return fps; } }

        /// <summary>-lasso 0|1 (null when absent).</summary>
        public static bool? Lasso { get { Parse(); return lasso; } }

        /// <summary>-sparkFactor x, clamped to [1.05, 5].</summary>
        public static double? SparkFactor { get { Parse(); return sparkFactor; } }

        /// <summary>-roundDuration s, clamped to [5, 900] (rule v1.7: 900 s is the default round time limit).</summary>
        public static double? RoundDuration { get { Parse(); return roundDuration; } }

        /// <summary>-ringInterval s, clamped to [1, 300].</summary>
        public static double? RingInterval { get { Parse(); return ringInterval; } }

        /// <summary>-biome liquid|fire|electric (or 0|1|2), null when absent or not a biome (contract 25.1).</summary>
        public static BiomeId? Biome { get { Parse(); return biome; } }

        /// <summary>Wave D-2: -classic (every trait off for every round, the attract match and scripted sessions).</summary>
        public static bool Classic { get { Parse(); return classic; } }

        /// <summary>
        /// Wave D-2: the value of -traits (trimmed), null when absent or unparsable (see TraitArgsError). Either a valid
        /// RuleTraits key or BiomeTraitTable's "default" keyword.
        /// </summary>
        public static string TraitsKey { get { Parse(); return traitsKey; } }

        /// <summary>Wave D-2: every valid -trait &lt;Id&gt;=0|1, in command-line order (true = on).</summary>
        public static IReadOnlyList<KeyValuePair<TraitId, bool>> TraitToggles { get { Parse(); return traitToggles; } }

        /// <summary>Wave D-2: the first invalid trait argument (null when every one parsed); BiomeTraitTable logs it once.</summary>
        public static string TraitArgsError { get { Parse(); return traitArgsError; } }

        /// <summary>Any trait flag is on the command line (-classic, -traits or -trait).</summary>
        public static bool HasTraitArgs => Classic || TraitsKey != null || TraitToggles.Count > 0;

        /// <summary>
        /// A command-line tuning override is active (stats are then not recorded). Wave D-2: an explicit -traits set
        /// (other than "default") or a -trait toggle counts, like a modified trait matrix; -classic is a normal option.
        /// </summary>
        public static bool HasTuningOverride => SparkFactor.HasValue || RoundDuration.HasValue || RingInterval.HasValue
                                                || (TraitsKey != null && !BiomeTraitTable.IsDefaultKeyword(TraitsKey))
                                                || TraitToggles.Count > 0;

        /// <summary>True when the flag (for example "-probe") is on the command line (case-insensitive).</summary>
        public static bool Has(string flag)
        {
            Parse();
            return IndexOf(flag) >= 0;
        }

        /// <summary>The argument following the flag, or null.</summary>
        public static string Value(string flag)
        {
            Parse();
            int k = IndexOf(flag);
            return k >= 0 && k + 1 < args.Length ? args[k + 1] : null;
        }

        /// <summary>Re-reads the options from the given arguments (null: the process command line).</summary>
        public static void Reload(string[] commandLine = null)
        {
            parsed = false;
            args = commandLine;
            Parse();
        }

        private static void Parse()
        {
            if (parsed) return;
            parsed = true;
            if (args == null)
            {
                try
                {
                    args = Environment.GetCommandLineArgs();
                }
                catch (Exception)
                {
                    args = new string[0];
                }
            }
            fps = 0;
            lasso = null;
            sparkFactor = roundDuration = ringInterval = null;
            biome = BiomeTheme.Parse(ValueRaw("-biome"));
            if (TryDouble("-fps", out double f) && f >= 1.0) fps = (int)Math.Min(1000.0, Math.Round(f));
            string l = ValueRaw("-lasso");
            if (l != null) lasso = l.Trim() != "0" && !l.Trim().Equals("false", StringComparison.OrdinalIgnoreCase);
            if (TryDouble("-sparkFactor", out double s)) sparkFactor = Clamp(s, 1.05, 5.0);
            if (TryDouble("-roundDuration", out double r)) roundDuration = Clamp(r, 5.0, 900.0);
            if (TryDouble("-ringInterval", out double i)) ringInterval = Clamp(i, 1.0, 300.0);
            ParseTraits();
        }

        /// <summary>-classic, -traits and every -trait (BIOME_TRAITS 5). Errors are kept in traitArgsError.</summary>
        private static void ParseTraits()
        {
            classic = IndexOf("-classic") >= 0;
            traitsKey = null;
            traitToggles = new List<KeyValuePair<TraitId, bool>>();
            traitArgsError = null;
            if (IndexOf("-traits") >= 0)
            {
                string key = ValueRaw("-traits");
                if (key == null || key.StartsWith("-", StringComparison.Ordinal)) traitArgsError = "-traits needs a value (a RuleTraits key or 'default')";
                else if (BiomeTraitTable.IsDefaultKeyword(key)) traitsKey = key.Trim();
                else
                {
                    try
                    {
                        RuleTraits.Parse(key);
                        traitsKey = key.Trim();
                    }
                    catch (FormatException e)
                    {
                        traitArgsError = "-traits '" + key + "' ignored: " + e.Message;
                    }
                }
            }
            for (int k = 0; args != null && k < args.Length; k++)
            {
                if (!string.Equals(args[k], "-trait", StringComparison.OrdinalIgnoreCase)) continue;
                string v = k + 1 < args.Length ? args[k + 1] : null;
                if (TryParseToggle(v, out TraitId id, out bool on)) traitToggles.Add(new KeyValuePair<TraitId, bool>(id, on));
                else if (traitArgsError == null) traitArgsError = "-trait '" + v + "' ignored (expected <Id>=0|1, Id one of " + string.Join(", ", TraitDefaults.All) + ")";
            }
        }

        /// <summary>"Id=1", "Id=0" (also on / off, true / false; Id by name or number).</summary>
        private static bool TryParseToggle(string text, out TraitId id, out bool on)
        {
            id = 0;
            on = false;
            if (string.IsNullOrEmpty(text)) return false;
            int eq = text.IndexOf('=');
            if (eq <= 0) return false;
            if (!BiomeTraitTable.TryParseTraitId(text.Substring(0, eq), out id)) return false;
            string v = text.Substring(eq + 1).Trim().ToLowerInvariant();
            if (v == "1" || v == "on" || v == "true") on = true;
            else if (v == "0" || v == "off" || v == "false") on = false;
            else return false;
            return true;
        }

        private static int IndexOf(string flag)
        {
            if (args == null) return -1;
            for (int k = 0; k < args.Length; k++)
            {
                if (string.Equals(args[k], flag, StringComparison.OrdinalIgnoreCase)) return k;
            }
            return -1;
        }

        private static string ValueRaw(string flag)
        {
            int k = IndexOf(flag);
            return k >= 0 && k + 1 < args.Length ? args[k + 1] : null;
        }

        private static bool TryDouble(string flag, out double value)
        {
            value = 0.0;
            string v = ValueRaw(flag);
            if (v == null) return false;
            v = v.Replace(',', '.');
            return double.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out value)
                   && !double.IsNaN(value) && !double.IsInfinity(value);
        }

        private static double Clamp(double v, double min, double max) => v < min ? min : (v > max ? max : v);
    }
}
