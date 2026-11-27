// Owned by B6. Contract 18.2 (player probe) on top of DemoScenario (23.3, rebuilt for rule v1.4 by BI, section 24.1) and
// section 25 (biomes). Active only with "-probe" on the player command line, in a windowed player (never -batchmode):
//   PainterIO.exe -probe -shotdir <dir> -fps <n> -mute -biome liquid|fire|electric
//                 -screen-width 540 -screen-height 960 -screen-fullscreen 0 -logFile <log>
// -fps is applied by GameDirector (targetFrameRate, vSync off), -mute by Sfx (hard mute), -biome by GameDirector / BiomeTheme;
// the probe checks that they took effect.
//
// Discipline (18.2): the probe never steers the sim. The demo round is driven only by DemoScenario's scripted controllers,
// SimSetup and BeforeTick hooks at TickRate 60 whatever -fps is; frame code only reads. A screenshot is taken in the first
// rendered frame with Sim.Tick >= its checkpoint tick (ScreenCapture.CaptureScreenshot), then the runner stays paused during
// a realtime wait for the file (5 s max) plus 0.2 s. The state hash is read in a BeforeTick handler at exactly
// DemoScenario.EndTick, so it does not depend on the display rate.
//
// Output lines: "[Probe] ..." (progress, one "CHECK <name> PASS|FAIL" line per check), "[ProbeError] ..." (errors and
// exceptions captured from the log since the first scene load), "[ProbeHash] <hex>" (after the demo), "[ProbePerf] avgMs=<x>
// p95Ms=<y> tier=<t>" (after the 20 s bot round), and last "[ProbeResult] PASS" or "[ProbeResult] FAIL <reasons>"; then
// Application.Quit(0 or 1). [ProbeResult] is printed after the bot round so exceptions raised there also fail the run.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    /// <summary>The player probe of contract 18.2 (null unless -probe is on the command line).</summary>
    [DefaultExecutionOrder(1000)]
    public sealed class PlayerProbe : MonoBehaviour
    {
        /// <summary>Real seconds in Menu before menu.png.</summary>
        public const float MenuSeconds = 2f;
        /// <summary>Realtime wait for a screenshot file.</summary>
        public const float FileWaitSeconds = 5f;
        /// <summary>Extra realtime wait after the file appeared.</summary>
        public const float AfterFileSeconds = 0.2f;
        /// <summary>Realtime wait for a GameDirector state (Menu at boot).</summary>
        public const float StateWaitSeconds = 10f;
        /// <summary>Realtime wait for the Results screen after the last checkpoint.</summary>
        public const float ResultsWaitSeconds = 8f;
        /// <summary>Realtime wait for the state hash at DemoScenario.EndTick after the last checkpoint.</summary>
        public const float HashWaitSeconds = 15f;
        /// <summary>Length of the bot-controlled round of step 5 (real seconds).</summary>
        public const float BotRoundSeconds = 20f;
        /// <summary>Frames of the first half second of the bot round are not measured (session start rebuilds).</summary>
        public const float PerfWarmupSeconds = 0.5f;
        /// <summary>The probe gives up (FAIL) after this many real seconds.</summary>
        public const float OverallTimeoutSeconds = 300f;
        /// <summary>18.2 step 3: at most 0.2 % magenta pixels per screenshot.</summary>
        public const double MaxMagentaFraction = 0.002;
        /// <summary>18.2 step 3: at most 98 % of the pixels of one exact color per screenshot.</summary>
        public const double MaxSingleColorFraction = 0.98;
        /// <summary>Seed of the bot round (fixed: the probe never uses the clock for a seed).</summary>
        public const ulong BotRoundSeed = 20261126UL;
        /// <summary>Log entries kept for the report (all are counted).</summary>
        public const int MaxLoggedProblems = 200;
        /// <summary>B6 guard: shots that frame the human's puddle need at least this share of its color.</summary>
        public const double MinPaintFraction = 0.003;
        /// <summary>Hue tolerance of the paint guard (fraction of the hue circle, 25 degrees).</summary>
        public const float PaintHueTolerance = 25f / 360f;
        public const float PaintMinSaturation = 0.3f;
        public const float PaintMinValue = 0.3f;

        /// <summary>Shaders every build must ship in Resources/Shaders (the current biome's three are added at run time).</summary>
        public static readonly string[] BaseShaders = { "LiquidComposite", "Bead", "Overlay", "FieldBlob", "FieldStroke", "TerritoryBlur" };

        private const string ShaderIdProperty = "_PIO_ShaderId";
        private const string ShaderGraphPrefix = "Shader Graphs/";

        // Early log capture (from the first scene load, so errors of the other subsystems' Awake are seen too).
        private static readonly object s_Lock = new object();
        private static readonly List<string> s_Problems = new List<string>();
        private static int s_ProblemCount;
        private static bool s_Hooked;

        private GameDirector director;
        private string shotDir;
        private bool biomeGiven;                 // "-biome" is on the command line
        private BiomeId? requestedBiome;         // its parsed value (null when absent or not a biome)
        private string biomeArg;                 // its raw value
        private float startTime;
        private bool done;
        private bool capturing;
        private readonly List<string> failures = new List<string>();
        private int shotsChecked;
        private int shotsExpected;

        // Demo round.
        private GameSession demo;
        private DemoScenario.Monitor monitor;
        private int humanCellsBeforeStep;
        private bool hashRecorded;
        private ulong stateHash;
        private long hashTick = -1;
        private ReturnFact firstReturn;
        private ReturnFact firstCapture;
        private ReturnFact savedChase;
        private int flickerReturns;
        private long pocketTick = -1;
        private int pocketCells;
        private long caughtTick = -1;
        private EliminationCause caughtCause = EliminationCause.None;
        private int humanCuts;

        private struct ReturnFact
        {
            public bool Seen;
            public long Tick;
            public int Cells;
            public bool Chased;
            public double Margin;
            public int Before;
            public int After;
            public bool AliveAfter;

            public override string ToString()
            {
                return Seen
                    ? "tick=" + Tick + " cells=" + Cells + " chased=" + Chased + " margin=" + F(Margin) + " owned " + Before + "->" + After
                    : "none";
            }
        }

        /// <summary>Pixel statistics of one screenshot (18.2 step 3).</summary>
        public struct ShotStats
        {
            public int Width, Height, Pixels, Magenta, TopColorCount;
            public Color32 TopColor;
            public double MagentaFraction, TopColorFraction;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Factory and lifecycle.

        /// <summary>The probe when "-probe" is on the command line, else null. Never with -devshot (both drive the round).</summary>
        public static PlayerProbe TryCreate(GameDirector d)
        {
            if (!LaunchArgs.Has("-probe")) return null;
            if (LaunchArgs.Has("-devshot"))
            {
                Debug.LogWarning("[Probe] -probe and -devshot both drive the demo round: the probe stays off");
                return null;
            }
            Hook();
            var go = new GameObject("PlayerProbe");
            var probe = go.AddComponent<PlayerProbe>();
            probe.director = d;
            probe.shotDir = ResolveShotDir(LaunchArgs.Value("-shotdir"));
            probe.biomeGiven = LaunchArgs.Has("-biome");
            probe.biomeArg = LaunchArgs.Value("-biome");
            probe.requestedBiome = probe.biomeGiven ? BiomeTheme.Parse(probe.biomeArg) : null;
            if (d != null) d.SuppressAutoPause = true;
            Application.runInBackground = true;
            return probe;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void HookEarly()
        {
            try
            {
                if (LaunchArgs.Has("-probe")) Hook();
            }
            catch (Exception)
            {
                // The probe is a dev tool: never break the boot for it.
            }
        }

        private static void Hook()
        {
            if (s_Hooked) return;
            s_Hooked = true;
            Application.logMessageReceivedThreaded += OnLog;
        }

        private static void OnLog(string condition, string stackTrace, LogType type)
        {
            if (type != LogType.Error && type != LogType.Exception && type != LogType.Assert) return;
            string entry = type + ": " + FirstLine(condition);
            if (type == LogType.Exception && !string.IsNullOrEmpty(stackTrace)) entry += " @ " + FirstLine(stackTrace);
            lock (s_Lock)
            {
                s_ProblemCount++;
                if (s_Problems.Count < MaxLoggedProblems) s_Problems.Add(entry);
            }
        }

        private void Start()
        {
            startTime = Time.realtimeSinceStartup;
            Debug.Log("[Probe] start shotdir=" + shotDir + " fps=" + LaunchArgs.Fps + " biome=" + (biomeGiven ? biomeArg : "(none)")
                      + " mute=" + LaunchArgs.Has("-mute") + " screen=" + Screen.width + "x" + Screen.height
                      + " batchmode=" + Application.isBatchMode + " graphics=" + SystemInfo.graphicsDeviceType
                      + " targetFrameRate=" + Application.targetFrameRate + " vSync=" + QualitySettings.vSyncCount);
            try
            {
                Directory.CreateDirectory(shotDir);
            }
            catch (Exception e)
            {
                Fail("cannot create the shot directory " + shotDir + ": " + e.Message);
            }
            StartCoroutine(Run());
        }

        private void Update()
        {
            if (done) return;
            if (Time.realtimeSinceStartup - startTime > OverallTimeoutSeconds)
            {
                Fail("overall timeout after " + OverallTimeoutSeconds + " s");
                Finish();
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // The sequence of 18.2.

        private IEnumerator Run()
        {
            Check("selftest", CheckSelfTest);
            Check("launch", CheckLaunchSettings);
            if (director == null)
            {
                Fail("no GameDirector");
                Finish();
                yield break;
            }

            // 1. Menu (attract match behind it) for 2 s, then menu.png.
            float waitStart = Time.realtimeSinceStartup;
            while (director.State != GameState.Menu && Time.realtimeSinceStartup - waitStart < StateWaitSeconds) yield return null;
            if (director.State != GameState.Menu) Fail("the menu never showed (state " + director.State + ")");
            yield return new WaitForSecondsRealtime(MenuSeconds);
            Check("shaders", CheckShaders);
            Check("font", CheckFont);
            yield return Capture("menu", null, true);

            // 2. The scripted demo round as the real session.
            if (!StartDemo())
            {
                Finish();
                yield break;
            }
            yield return null;
            Check("biome", CheckBiome);
            Check("tickrate", CheckTickRate);

            long[] ticks = DemoScenario.CheckpointTicks;
            string[] names = DemoScenario.CheckpointNames;
            int next = 0;
            while (next < ticks.Length && !done)
            {
                if (director.Session != demo)
                {
                    Fail("the demo session was replaced before checkpoint " + names[next]);
                    break;
                }
                if (demo.Sim.Tick >= ticks[next] || demo.Sim.Ended)
                {
                    string checkpoint = names[next];
                    next++;
                    bool first = next == 1;
                    yield return Capture(ShotName(checkpoint), demo, first);
                    if (first)
                    {
                        Check("actorfield", CheckActorField);
                        Check("composite", CheckCompositeRenderer);
                    }
                    continue;
                }
                yield return null;
            }
            if (done) yield break;

            // The hash at exactly DemoScenario.EndTick (BeforeTick handler).
            float hashStart = Time.realtimeSinceStartup;
            while (!hashRecorded && director.Session == demo && Time.realtimeSinceStartup - hashStart < HashWaitSeconds) yield return null;

            // Results screen (after the death beat), when it appears.
            float resultsStart = Time.realtimeSinceStartup;
            while (director.State != GameState.Results && Time.realtimeSinceStartup - resultsStart < ResultsWaitSeconds) yield return null;
            if (director.State == GameState.Results)
            {
                yield return new WaitForSecondsRealtime(0.6f);
                yield return Capture("results", demo, true);
            }
            else Fail("results never showed (state " + director.State + ")");

            Check("scenario", EvaluateDemo);
            if (hashRecorded) Debug.Log("[ProbeHash] " + stateHash.ToString("X16", CultureInfo.InvariantCulture));
            else Debug.Log("[Probe] no state hash: DemoScenario.EndTick " + DemoScenario.EndTick + " was not reached");

            // 5. A 20 s bot-controlled normal round to catch runtime exceptions, with frame times.
            yield return BotRound();
            Finish();
        }

        private bool StartDemo()
        {
            try
            {
                // -biome is applied by GameDirector at each session start; the forced overload makes the demo explicit.
                demo = requestedBiome.HasValue
                    ? DemoScenario.CreateSession(out monitor, requestedBiome.Value)
                    : DemoScenario.CreateSession(out monitor);
                demo.Sim.BeforeTick += OnDemoBeforeTick;
                demo.EventRaised += OnDemoEvent;
                humanCellsBeforeStep = HumanCells(demo.Sim);
                director.StartRound(demo);
                shotsExpected = 2 + DemoScenario.CheckpointTicks.Length;   // menu + checkpoints + results
                Debug.Log("[Probe] demo started: " + DemoScenario.CheckpointTicks.Length + " checkpoints, EndTick " + DemoScenario.EndTick);
                return true;
            }
            catch (Exception e)
            {
                Fail("demo start failed: " + FirstLine(e.Message));
                Debug.LogWarning("[Probe] demo start failed: " + e);
                return false;
            }
        }

        private void OnDemoBeforeTick(Simulation sim)
        {
            humanCellsBeforeStep = HumanCells(sim);
            if (!hashRecorded && sim.Tick == DemoScenario.EndTick)
            {
                stateHash = sim.StateHash();
                hashTick = sim.Tick;
                hashRecorded = true;
            }
        }

        // Forwarded after each Step (GameSession), so the grid is the post-step grid and IsFlickerReturn is valid.
        private void OnDemoEvent(SimEvent e)
        {
            if (demo == null || e.Player != DemoScenario.Human) return;
            Simulation sim = demo.Sim;
            long tick = sim.Tick;
            switch (e.Type)
            {
                case SimEventType.Cut:
                    humanCuts++;
                    break;
                case SimEventType.Return:
                {
                    if (demo.IsFlickerReturn(e))
                    {
                        flickerReturns++;
                        break;
                    }
                    var fact = new ReturnFact
                    {
                        Seen = true,
                        Tick = tick,
                        Cells = e.Cells != null ? e.Cells.Length : 0,
                        Chased = e.Chased,
                        Margin = e.Margin,
                        Before = humanCellsBeforeStep,
                        After = HumanCells(sim),
                        AliveAfter = sim.Players[DemoScenario.Human].Alive,
                    };
                    if (!firstReturn.Seen) firstReturn = fact;
                    if (!firstCapture.Seen && !fact.Chased && fact.Cells > 0) firstCapture = fact;
                    if (!savedChase.Seen && fact.Chased) savedChase = fact;
                    break;
                }
                case SimEventType.LassoPocket:
                    if (pocketTick < 0)
                    {
                        pocketTick = tick;
                        pocketCells = e.Cells != null ? e.Cells.Length : 0;
                    }
                    break;
                case SimEventType.Eliminated:
                    if (caughtTick < 0)
                    {
                        caughtTick = tick;
                        caughtCause = e.Cause;
                    }
                    break;
            }
        }

        private void EvaluateDemo(List<string> problems)
        {
            if (monitor != null)
            {
                monitor.Finish();
                if (!monitor.Evaluate(out List<string> monitorFailures))
                {
                    problems.Add("DemoScenario.Monitor: " + string.Join("; ", monitorFailures));
                }
                Debug.Log("[Probe] monitor facts " + monitor.Report());
            }
            Debug.Log("[Probe] demo facts firstReturn{" + firstReturn + "} firstCapture{" + firstCapture + "} savedChase{" + savedChase
                      + "} flickerReturns=" + flickerReturns + " cutsReceived=" + humanCuts + " pocket tick=" + pocketTick + " cells="
                      + pocketCells + " eliminated tick=" + caughtTick + " cause=" + caughtCause + " hashTick=" + hashTick);

            // The first return captured cells: under v1.4 it is the unchased clean capture.
            if (!firstReturn.Seen) problems.Add("the human never returned home");
            else if (firstReturn.Chased || firstReturn.Cells <= 0 || firstReturn.After <= firstReturn.Before)
                problems.Add("the first return is not an unchased capture that increased the area (" + firstReturn + ")");
            // A saved chased return captures nothing (v1.4, contract 24).
            if (!savedChase.Seen) problems.Add("no saved chased return");
            else
            {
                if (savedChase.Cells != 0) problems.Add("the saved chased return captured " + savedChase.Cells + " cells (v1.4: none)");
                if (savedChase.After > savedChase.Before) problems.Add("the saved chased return increased the area (" + savedChase + ")");
                if (!savedChase.AliveAfter) problems.Add("the human did not survive its saved chased return");
                if (firstCapture.Seen && savedChase.Tick < firstCapture.Tick) problems.Add("the saved chase came before the clean capture");
            }
            if (pocketTick < 0) problems.Add("no LassoPocket for the human");
            else if (pocketCells <= 0) problems.Add("the LassoPocket has no cell");
            if (caughtTick < 0) problems.Add("the human was not eliminated");
            else
            {
                if (caughtCause != EliminationCause.Spark) problems.Add("the human was eliminated by " + caughtCause + ", not by the spark");
                if (pocketTick >= 0 && pocketTick > caughtTick) problems.Add("the pocket came after the elimination");
            }
            if (demo != null && demo.Sim.EventCapHits != 0) problems.Add("EventCapHits = " + demo.Sim.EventCapHits);
            if (!hashRecorded) problems.Add("no state hash at DemoScenario.EndTick " + DemoScenario.EndTick);
        }

        private IEnumerator BotRound()
        {
            GameSession round = null;
            try
            {
                round = CreateBotRound();
                director.StartRound(round);
                Debug.Log("[Probe] bot round started seed=" + BotRoundSeed + " lasso=true tickRate=" + round.Sim.Config.TickRate);
            }
            catch (Exception e)
            {
                Fail("bot round start failed: " + FirstLine(e.Message));
                Debug.LogWarning("[Probe] bot round start failed: " + e);
            }
            if (round == null) yield break;

            var frames = new List<float>(4096);
            float start = Time.realtimeSinceStartup;
            yield return null;
            while (!done && Time.realtimeSinceStartup - start < BotRoundSeconds)
            {
                if (Time.realtimeSinceStartup - start >= PerfWarmupSeconds) frames.Add(Time.unscaledDeltaTime * 1000f);
                yield return null;
            }
            if (done) yield break;

            double avg = 0.0, p95 = 0.0;
            if (frames.Count > 0)
            {
                double sum = 0.0;
                foreach (float f in frames) sum += f;
                avg = sum / frames.Count;
                frames.Sort();
                int k = (int)Math.Ceiling(0.95 * frames.Count) - 1;
                p95 = frames[Math.Max(0, Math.Min(frames.Count - 1, k))];
            }
            string tier = "?";
            try
            {
                tier = QualityTier.Current.ToString();
            }
            catch (Exception)
            {
                // Reported as "?".
            }
            Debug.Log("[ProbePerf] avgMs=" + F2(avg) + " p95Ms=" + F2(p95) + " tier=" + tier);
            Debug.Log("[Probe] bot round: frames=" + frames.Count + " simTime=" + F(round.Sim.Time) + " ticks=" + round.Sim.Tick
                      + " ended=" + round.Sim.Ended + " humanAlive=" + round.HumanAlive + " state=" + director.State
                      + " sameSession=" + (director.Session == round));
            if (round.Sim.Tick <= 0) Fail("the bot round's sim did not advance");
            if (frames.Count == 0) Fail("no frame measured during the bot round");
        }

        /// <summary>A normal round (TickRate 60, lasso on) whose human (index 0) is a Balanced BotController.</summary>
        private static GameSession CreateBotRound()
        {
            SimConfig config = GameSession.RoundConfig(BotRoundSeed, true);
            config.TickRate = Tuning.TickRate;
            var controllers = new IController[Tuning.PlayerCount];
            BotStyle[] lineup = { BotStyle.Balanced, BotStyle.Balanced, BotStyle.Greedy, BotStyle.Aggressive };
            for (int i = 0; i < controllers.Length; i++)
            {
                controllers[i] = new BotController(BotPersonality.Preset(lineup[i % lineup.Length]), GameSession.BotSeed(BotRoundSeed, i));
            }
            var setup = new SimSetup
            {
                PlayerCount = controllers.Length,
                Names = GameSession.DefaultNames(controllers.Length, 0),
                HumanIndex = 0,
            };
            return new GameSession(config, setup, controllers, false);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Screenshots.

        private IEnumerator Capture(string name, GameSession session, bool requireTexts)
        {
            capturing = true;
            string path = Path.Combine(shotDir, name + ".png");
            bool resume = false;
            if (session != null && !session.IsClosed && !session.Runner.Paused)
            {
                session.Runner.Paused = true;
                resume = true;
            }
            try
            {
                if (File.Exists(path)) File.Delete(path);
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Probe] could not delete the old " + path + ": " + e.Message);
            }
            long tick = session != null ? session.Sim.Tick : -1;
            // Frame checks on the frame that is being captured.
            Check("renderers@" + name, CheckRenderers);
            Check("texts@" + name, problems => CheckTexts(problems, requireTexts));
            ScreenCapture.CaptureScreenshot(path);
            float t0 = Time.realtimeSinceStartup;
            while (!FileReady(path) && Time.realtimeSinceStartup - t0 < FileWaitSeconds) yield return null;
            bool written = FileReady(path);
            yield return new WaitForSecondsRealtime(AfterFileSeconds);
            if (!written) Fail(name + ".png was not written within " + FileWaitSeconds + " s");
            else
            {
                // The file can still be growing on a slow disk: a few decode attempts.
                bool analysed = false;
                string lastError = null;
                for (int attempt = 0; attempt < 4 && !analysed; attempt++)
                {
                    if (attempt > 0) yield return new WaitForSecondsRealtime(0.2f);
                    analysed = TryCheckShot(name, path, tick, out lastError);
                }
                if (!analysed) Fail(name + ".png could not be decoded: " + lastError);
            }
            if (resume && session != null && !session.IsClosed) session.Runner.Paused = false;
            capturing = false;
        }

        private bool TryCheckShot(string name, string path, long tick, out string error)
        {
            error = null;
            Texture2D tex = null;
            try
            {
                byte[] bytes = File.ReadAllBytes(path);
                tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                if (!tex.LoadImage(bytes, false))
                {
                    error = "LoadImage failed (" + bytes.Length + " bytes)";
                    return false;
                }
                Color32[] pixels = tex.GetPixels32();
                ShotStats s = Analyze(pixels, tex.width, tex.height);
                shotsChecked++;
                var problems = new List<string>();
                if (s.Width < 64 || s.Height < 64) problems.Add("too small " + s.Width + "x" + s.Height);
                if (s.MagentaFraction > MaxMagentaFraction) problems.Add("magenta " + Pct(s.MagentaFraction) + " > 0.2 %");
                if (s.TopColorFraction > MaxSingleColorFraction) problems.Add("one color covers " + Pct(s.TopColorFraction) + " > 98 %");
                // B6 guard beyond 18.2: plain ground + HUD passes both rules above, so the shots that frame the human's
                // puddle must show enough of its (biome) color.
                string paintNote = "";
                if (NeedsHumanPaint(name))
                {
                    double paint = PaintFraction(pixels, Palette.ColorOf(DemoScenario.Human));
                    paintNote = " humanPaint=" + Pct(paint);
                    if (paint < MinPaintFraction) problems.Add("the human's color covers only " + Pct(paint) + " (puddle not drawn?)");
                }
                Debug.Log("[Probe] shot " + name + ".png tick=" + tick + " " + s.Width + "x" + s.Height + " magenta=" + Pct(s.MagentaFraction)
                          + " topColor=" + Pct(s.TopColorFraction) + " #" + Hex(s.TopColor) + paintNote + (problems.Count == 0 ? " ok" : " BAD"));
                Report("shot@" + name, problems);
                return true;
            }
            catch (Exception e)
            {
                error = FirstLine(e.Message);
                return false;
            }
            finally
            {
                if (tex != null) Destroy(tex);
            }
        }

        private static bool FileReady(string path)
        {
            try
            {
                return File.Exists(path) && new FileInfo(path).Length > 0;
            }
            catch (Exception)
            {
                return false;
            }
        }

        /// <summary>18.2 magenta test on one pixel: r &gt; 0.85, g &lt; 0.15, b &gt; 0.85.</summary>
        public static bool IsMagenta(Color32 c)
        {
            return c.r > 216 && c.g < 39 && c.b > 216;   // 0.85 * 255 = 216.75, 0.15 * 255 = 38.25
        }

        /// <summary>Magenta share and the share of the most frequent exact RGB color of an image.</summary>
        public static ShotStats Analyze(Color32[] pixels, int width, int height)
        {
            var s = new ShotStats { Width = width, Height = height, Pixels = pixels != null ? pixels.Length : 0 };
            if (s.Pixels == 0) return s;
            var counts = new Dictionary<int, int>(8192);
            int best = 0, bestKey = 0;
            int runKey = -1, runLength = 0;
            for (int k = 0; k <= pixels.Length; k++)
            {
                int key = -2;
                if (k < pixels.Length)
                {
                    Color32 c = pixels[k];
                    if (IsMagenta(c)) s.Magenta++;
                    key = (c.r << 16) | (c.g << 8) | c.b;
                    if (key == runKey)
                    {
                        runLength++;
                        continue;
                    }
                }
                if (runLength > 0)
                {
                    counts.TryGetValue(runKey, out int n);
                    n += runLength;
                    counts[runKey] = n;
                    if (n > best)
                    {
                        best = n;
                        bestKey = runKey;
                    }
                }
                runKey = key;
                runLength = 1;
            }
            s.TopColorCount = best;
            s.TopColor = new Color32((byte)((bestKey >> 16) & 255), (byte)((bestKey >> 8) & 255), (byte)(bestKey & 255), 255);
            s.MagentaFraction = s.Magenta / (double)s.Pixels;
            s.TopColorFraction = best / (double)s.Pixels;
            return s;
        }

        /// <summary>
        /// Share of pixels whose hue is within PaintHueTolerance of paint's hue, with saturation and value at least
        /// PaintMinSaturation / PaintMinValue (robust to the liquid shading, the embers and the neon of the biomes).
        /// </summary>
        public static double PaintFraction(Color32[] pixels, Color paint)
        {
            if (pixels == null || pixels.Length == 0) return 0.0;
            Color.RGBToHSV(paint, out float th, out float ts, out float tv);
            int hits = 0;
            int lastKey = -1;
            bool lastHit = false;
            for (int k = 0; k < pixels.Length; k++)
            {
                Color32 c = pixels[k];
                int key = (c.r << 16) | (c.g << 8) | c.b;
                if (key != lastKey)
                {
                    lastKey = key;
                    Color.RGBToHSV(c, out float h, out float sat, out float v);
                    float d = Mathf.Abs(h - th);
                    d = Mathf.Min(d, 1f - d);
                    lastHit = d <= PaintHueTolerance && sat >= PaintMinSaturation && v >= PaintMinValue;
                }
                if (lastHit) hits++;
            }
            return hits / (double)pixels.Length;
        }

        /// <summary>Shots in which the human's puddle is framed (it is alive and the camera follows it).</summary>
        public static bool NeedsHumanPaint(string shotName)
        {
            return shotName == "thread" || shotName == "fill" || shotName == "cut" || shotName == "saved" || shotName == "pocket";
        }

        /// <summary>Screenshot file name for a DemoScenario checkpoint (contract 18.2 names for the known ones).</summary>
        public static string ShotName(string checkpoint)
        {
            switch (checkpoint)
            {
                case "ThreadOut": return "thread";
                case "MidFill": return "fill";
                case "CutDroplets": return "cut";
                case "SavedReturn": return "saved";
                case "PocketPending": return "pocket";
                case "Caught": return "caught";
            }
            if (string.IsNullOrEmpty(checkpoint)) return "checkpoint";
            string lower = checkpoint.ToLowerInvariant();
            return lower == "menu" || lower == "results" ? "cp_" + lower : lower;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Checks. Each fills a problem list; Check() logs one verdict line and records the failures.

        private void Check(string name, Action<List<string>> body)
        {
            var problems = new List<string>();
            try
            {
                body(problems);
            }
            catch (Exception e)
            {
                problems.Add("check threw " + e.GetType().Name + ": " + FirstLine(e.Message));
            }
            Report(name, problems);
        }

        private void Report(string name, List<string> problems)
        {
            if (problems.Count == 0)
            {
                Debug.Log("[Probe] CHECK " + name + " PASS");
                return;
            }
            string joined = string.Join("; ", problems);
            Debug.Log("[Probe] CHECK " + name + " FAIL " + joined);
            Fail(name + ": " + joined);
        }

        private static void CheckSelfTest(List<string> problems)
        {
            // Guards against checks that pass vacuously: a flat magenta frame must fail both pixel rules, a varied frame none.
            var flat = new Color32[64];
            for (int k = 0; k < flat.Length; k++) flat[k] = new Color32(255, 0, 255, 255);
            ShotStats a = Analyze(flat, 8, 8);
            if (a.MagentaFraction < 0.999 || a.TopColorFraction < 0.999) problems.Add("flat magenta frame not detected");
            var varied = new Color32[64];
            for (int k = 0; k < varied.Length; k++) varied[k] = new Color32((byte)(k * 4), (byte)(255 - k * 3), (byte)(k % 7 * 30), 255);
            ShotStats b = Analyze(varied, 8, 8);
            if (b.Magenta != 0 || b.TopColorFraction > 0.05) problems.Add("varied frame misjudged");
            if (!IsMagenta(new Color32(217, 38, 217, 255)) || IsMagenta(new Color32(216, 38, 217, 255))
                || IsMagenta(new Color32(217, 39, 217, 255)) || IsMagenta(new Color32(217, 38, 216, 255)))
                problems.Add("magenta thresholds");
            // Paint guard: a coral frame (lit and shaded) is all paint, a navy ground frame none of it.
            var coral = new Color(0.949f, 0.404f, 0.310f);   // #F2674F
            var paintFrame = new Color32[64];
            for (int k = 0; k < paintFrame.Length; k++) paintFrame[k] = (Color32)(coral * (0.75f + 0.005f * k));
            var groundFrame = new Color32[64];
            for (int k = 0; k < groundFrame.Length; k++) groundFrame[k] = new Color32((byte)(30 + k % 3), (byte)(42 + k % 2), 77, 255);
            if (PaintFraction(paintFrame, coral) < 0.999) problems.Add("paint guard misses the paint");
            if (PaintFraction(groundFrame, coral) > 0.0) problems.Add("paint guard sees paint on the ground");
        }

        private static void CheckLaunchSettings(List<string> problems)
        {
            if (Application.isBatchMode) problems.Add("the probe must run in a windowed player, not in batchmode");
            if (SystemInfo.graphicsDeviceType == UnityEngine.Rendering.GraphicsDeviceType.Null) problems.Add("no graphics device (-nographics?)");
            int fps = LaunchArgs.Fps;
            if (fps > 0 && (Application.targetFrameRate != fps || QualitySettings.vSyncCount != 0))
                problems.Add("-fps " + fps + " not applied (targetFrameRate " + Application.targetFrameRate + ", vSync " + QualitySettings.vSyncCount + ")");
            if (LaunchArgs.Has("-mute") && Sfx.Instance != null && !Sfx.Instance.HardMuted) problems.Add("-mute not applied (Sfx not hard muted)");
        }

        private void CheckShaders(List<string> problems)
        {
            // The current biome's own shaders are required too: BiomeTheme silently falls back to the liquid shaders when one
            // is missing or unsupported, which would make a stripped biome shader look like a pass.
            var required = new List<string>(BaseShaders);
            BiomeTheme theme = BiomeTheme.Current;
            foreach (string shaderName in new[] { theme.CompositeShader, theme.BeadShader, theme.OverlayShader })
            {
                if (!string.IsNullOrEmpty(shaderName) && !required.Contains(shaderName)) required.Add(shaderName);
            }
            foreach (string name in required)
            {
                Shader s = Resources.Load<Shader>("Shaders/" + name);
                if (s == null) problems.Add("Shaders/" + name + " missing from the player");
                else if (!s.isSupported) problems.Add("Shaders/" + name + " not supported");
            }
            Shader[] all = Resources.LoadAll<Shader>("Shaders");
            if (all == null || all.Length < BaseShaders.Length) problems.Add("only " + (all != null ? all.Length : 0) + " shaders in Resources/Shaders");
            var sb = new StringBuilder();
            if (all != null)
            {
                foreach (Shader s in all)
                {
                    if (s == null)
                    {
                        problems.Add("a null shader in Resources/Shaders");
                        continue;
                    }
                    int passes = -1;
                    if (s.name.StartsWith(ShaderGraphPrefix, StringComparison.Ordinal))
                    {
                        var m = new Material(s) { hideFlags = HideFlags.HideAndDontSave };
                        passes = m.passCount;
                        Destroy(m);
                    }
                    sb.Append(s.name).Append(passes >= 0 ? "(" + passes + " passes)" : "").Append(s.isSupported ? "" : "(UNSUPPORTED)").Append(", ");
                    if (!s.isSupported) problems.Add(s.name + " is not supported");
                    if (s.name.Contains("InternalErrorShader") || s.name.Contains("FallbackError")) problems.Add(s.name + " is an error shader");
                    if (s.FindPropertyIndex(ShaderIdProperty) < 0) problems.Add(s.name + " has no " + ShaderIdProperty);
                    // A Shader Graph whose URP subshader is unusable runs its 1-pass FallbackError (found by B0b).
                    if (passes >= 0 && passes <= 1) problems.Add(s.name + " runs a 1-pass fallback");
                }
            }
            Debug.Log("[Probe] shaders " + (all != null ? all.Length : 0) + ": " + sb + "required " + string.Join(",", required));
        }

        private static void CheckFont(List<string> problems)
        {
            Font font = UiKit.Font;
            if (font == null) problems.Add("UiKit.Font is null");
            if (UiKit.UsingFallbackFont) problems.Add("the OFL font did not load (LegacyRuntime.ttf fallback in use)");
        }

        private void CheckBiome(List<string> problems)
        {
            BiomeTheme theme = BiomeTheme.Current;
            Debug.Log("[Probe] biome arg=" + (biomeGiven ? biomeArg : "(none)") + " current=" + theme.Id + " composite=" + theme.CompositeShader
                      + " bead=" + theme.BeadShader + " overlay=" + theme.OverlayShader + " fill=" + F(theme.FillDuration));
            if (!biomeGiven) return;
            if (!requestedBiome.HasValue) problems.Add("-biome '" + biomeArg + "' is not a biome (liquid|fire|electric)");
            else if (theme.Id != requestedBiome.Value) problems.Add("BiomeTheme.Current is " + theme.Id + ", -biome asked for " + requestedBiome.Value);
        }

        private void CheckTickRate(List<string> problems)
        {
            if (demo == null) return;
            if (demo.Sim.Config.TickRate != 60) problems.Add("demo TickRate " + demo.Sim.Config.TickRate + " (must be 60 whatever -fps)");
            if (demo.AwaitingStart) problems.Add("the demo session waits for a start (must start at once)");
        }

        private static void CheckActorField(List<string> problems)
        {
            var rt = Shader.GetGlobalTexture("_PIO_ActorField") as RenderTexture;
            if (rt == null) problems.Add("_PIO_ActorField is not a RenderTexture");
            else if (!rt.IsCreated() || rt.width <= 0 || rt.height <= 0) problems.Add("_PIO_ActorField RT not created");
            else Debug.Log("[Probe] actor field " + rt.width + "x" + rt.height + " " + rt.graphicsFormat);
        }

        private void CheckCompositeRenderer(List<string> problems)
        {
            string composite = BiomeTheme.Current.CompositeShader;
            if (string.IsNullOrEmpty(composite)) composite = BiomeTheme.LiquidCompositeShader;
            foreach (Renderer r in SceneObjects<Renderer>())
            {
                if (!r.enabled) continue;
                Material m = r.sharedMaterial;
                if (m != null && m.shader != null && m.shader.name.EndsWith("/" + composite, StringComparison.Ordinal)) return;
            }
            problems.Add("no enabled renderer draws the " + composite + " composite");
        }

        private static void CheckRenderers(List<string> problems)
        {
            int count = 0;
            foreach (Renderer r in SceneObjects<Renderer>())
            {
                if (!r.enabled) continue;
                count++;
                Material m = r.sharedMaterial;
                if (m == null)
                {
                    problems.Add(r.name + " has no material");
                    continue;
                }
                foreach (Material mat in r.sharedMaterials)
                {
                    if (mat == null) continue;
                    Shader s = mat.shader;
                    if (s == null) problems.Add(r.name + " material " + mat.name + " has no shader");
                    else if (!s.isSupported) problems.Add(r.name + " uses the unsupported shader " + s.name);
                    else if (s.name.Contains("InternalErrorShader")) problems.Add(r.name + " uses the error shader");
                }
                if (problems.Count > 10) return;
            }
            if (count == 0) problems.Add("no enabled renderer in the scene");
        }

        private static void CheckTexts(List<string> problems, bool requireSome)
        {
            int visible = 0;
            foreach (Text t in SceneObjects<Text>())
            {
                if (!t.enabled || !OnVisibleCanvas(t.transform)) continue;
                visible++;
                if (string.IsNullOrWhiteSpace(t.text)) problems.Add("visible Text '" + HierarchyPath(t.transform) + "' is empty");
                else if (t.font == null) problems.Add("visible Text '" + HierarchyPath(t.transform) + "' has no font");
                if (problems.Count > 10) return;
            }
            if (requireSome && visible == 0) problems.Add("no visible UI text");
        }

        // ------------------------------------------------------------------------------------------------------------
        // End.

        private void Fail(string reason)
        {
            failures.Add(reason);
        }

        private void Finish()
        {
            if (done) return;
            done = true;
            if (capturing) Fail("finished during a capture");
            if (shotsExpected > 0 && shotsChecked < shotsExpected) Fail("only " + shotsChecked + " of " + shotsExpected + " screenshots checked");
            List<string> logged;
            int total;
            lock (s_Lock)
            {
                logged = new List<string>(s_Problems);
                total = s_ProblemCount;
            }
            for (int k = 0; k < logged.Count && k < 20; k++) Debug.Log("[ProbeError] " + logged[k]);
            if (total > 0) Fail(total + " error or exception log entries (first: " + logged[0] + ")");
            string result = failures.Count == 0 ? "PASS" : "FAIL " + string.Join(" | ", failures);
            Debug.Log("[ProbeResult] " + result);
            Application.Quit(failures.Count == 0 ? 0 : 1);
        }

        private void OnDestroy()
        {
            if (demo != null && demo.Sim != null) demo.Sim.BeforeTick -= OnDemoBeforeTick;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Helpers.

        private static int HumanCells(Simulation sim)
        {
            return sim.Grid.CountOf(sim.Players[DemoScenario.Human].Id);
        }

        private static string ResolveShotDir(string value)
        {
            if (string.IsNullOrEmpty(value) || value.StartsWith("-", StringComparison.Ordinal))
                return System.IO.Path.Combine(Application.persistentDataPath, "probe");
            try
            {
                return System.IO.Path.GetFullPath(value);
            }
            catch (Exception)
            {
                return value;
            }
        }

        private static IEnumerable<T> SceneObjects<T>() where T : Component
        {
            foreach (T c in Resources.FindObjectsOfTypeAll<T>())
            {
                if (c != null && c.gameObject.scene.IsValid() && c.gameObject.activeInHierarchy) yield return c;
            }
        }

        private static bool OnVisibleCanvas(Transform t)
        {
            bool hasCanvas = false;
            for (Transform x = t; x != null; x = x.parent)
            {
                var group = x.GetComponent<CanvasGroup>();
                if (group != null && group.alpha <= 0.001f) return false;
                var canvas = x.GetComponent<Canvas>();
                if (canvas != null)
                {
                    if (!canvas.enabled) return false;
                    hasCanvas = true;
                }
            }
            return hasCanvas;
        }

        private static string HierarchyPath(Transform t)
        {
            string p = t.name;
            for (Transform x = t.parent; x != null && p.Length < 120; x = x.parent) p = x.name + "/" + p;
            return p;
        }

        private static string FirstLine(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            int k = s.IndexOfAny(new[] { '\r', '\n' });
            string line = k >= 0 ? s.Substring(0, k) : s;
            return line.Length > 300 ? line.Substring(0, 300) : line;
        }

        private static string Hex(Color32 c)
        {
            return c.r.ToString("X2", CultureInfo.InvariantCulture) + c.g.ToString("X2", CultureInfo.InvariantCulture)
                   + c.b.ToString("X2", CultureInfo.InvariantCulture);
        }

        private static string Pct(double fraction)
        {
            return (fraction * 100.0).ToString("0.000", CultureInfo.InvariantCulture) + "%";
        }

        private static string F(double v)
        {
            return v.ToString("0.###", CultureInfo.InvariantCulture);
        }

        private static string F2(double v)
        {
            return v.ToString("0.00", CultureInfo.InvariantCulture);
        }
    }
}
