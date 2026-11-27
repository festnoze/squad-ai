// Owned by BI since wave B-2 (written by B0a). Contract 23.3 and 25.1: "-devshot <dir> [-fps n] [-biome liquid|fire|electric]"
// plays DemoScenario in the real game view and saves one PNG per checkpoint plus menu.png (and results.png), each name
// prefixed with the biome ("liquid_menu.png", "fire_CutDroplets.png"...), then quits with exit code 0. The biome comes from
// -biome (applied by GameDirector), else SaveData.Biome. B1, B2 and the polish agent iterate with
// Builder.BuildWindows + DevShot and look at the PNGs next to docs/reference_gouttes.png.
//
// Screenshot discipline (18.2): the scenario is driven only by the sim (DemoScenario's scripted controllers and BeforeTick
// hooks); frame code only reads. A shot is taken in the first rendered frame with Sim.Tick >= its checkpoint, with
// ScreenCapture.CaptureScreenshot, then the runner stays paused during a realtime wait for the file (5 s max) + 0.2 s.
// Every log line starts with "[DevShot]".
//
// Wave D-2 (traits-infra, docs/BIOME_TRAITS.md section 5): the demo runs CLASSIC by default and accepts the trait flags
// (-classic, -traits "<key>", -traits default = the biome's line of the table, -trait <Id>=0|1). A traited demo also saves
// the DemoScenario.TraitShots screenshots ("<biome>_trait_grow.png", _reward, _scorch, _reach) when they come up, for
// example: -devshot <dir> -biome fire -traits default -trait KillInheritance=0 (Propagation front, then scorched ground).
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace PainterIO.Runtime
{
    [DefaultExecutionOrder(1000)]
    public sealed class DevShot : MonoBehaviour
    {
        public const float MenuSeconds = 2f;
        public const float FileWaitSeconds = 5f;
        public const float AfterFileSeconds = 0.2f;
        public const float ResultsWaitSeconds = 6f;
        public const float OverallTimeoutSeconds = 180f;

        private GameDirector director;
        private string dir;
        private GameSession demo;
        private DemoScenario.Monitor monitor;
        private DemoScenario.TraitShots traitShots;
        private int nextCheckpoint;
        private bool capturing;
        private bool done;
        private float startTime;
        private readonly List<string> problems = new List<string>();

        /// <summary>The DevShot component when "-devshot &lt;dir&gt;" is on the command line, else null.</summary>
        public static DevShot TryCreate(GameDirector d)
        {
            if (!LaunchArgs.Has("-devshot")) return null;
            string target = LaunchArgs.Value("-devshot");
            if (string.IsNullOrEmpty(target) || target.StartsWith("-", StringComparison.Ordinal))
            {
                Debug.LogError("[DevShot] -devshot needs a directory argument");
                return null;
            }
            var go = new GameObject("DevShot");
            var shot = go.AddComponent<DevShot>();
            shot.director = d;
            shot.dir = Path.GetFullPath(target);
            if (d != null) d.SuppressAutoPause = true;
            Application.runInBackground = true;
            return shot;
        }

        private void Start()
        {
            startTime = Time.realtimeSinceStartup;
            Debug.Log("[DevShot] start dir=" + dir + " fps=" + LaunchArgs.Fps + " screen=" + Screen.width + "x" + Screen.height
                      + " biome=" + BiomeTheme.Current.CommandName + (LaunchArgs.Has("-biome") && !LaunchArgs.Biome.HasValue ? " (unknown -biome value ignored)" : ""));
            try
            {
                Directory.CreateDirectory(dir);
            }
            catch (Exception e)
            {
                Debug.LogError("[DevShot] cannot create " + dir + ": " + e.Message);
            }
            StartCoroutine(Run());
        }

        private void Update()
        {
            if (done) return;
            if (Time.realtimeSinceStartup - startTime > OverallTimeoutSeconds)
            {
                problems.Add("overall timeout");
                Finish();
            }
        }

        private IEnumerator Run()
        {
            // 1. Menu (attract match behind it) for 2 s, then menu.png.
            float waitStart = Time.realtimeSinceStartup;
            while (director == null || director.State != GameState.Menu)
            {
                if (Time.realtimeSinceStartup - waitStart > 10f)
                {
                    problems.Add("the menu never showed (state " + (director != null ? director.State.ToString() : "no director") + ")");
                    break;
                }
                yield return null;
            }
            yield return new WaitForSecondsRealtime(MenuSeconds);
            yield return Capture("menu", null);

            // 2. The scripted demo round as the real session.
            if (director == null)
            {
                problems.Add("no GameDirector");
                Finish();
                yield break;
            }
            try
            {
                demo = DemoScenario.CreateSession(out monitor);
                if (!demo.Traits.IsClassic) traitShots = new DemoScenario.TraitShots(demo.Sim);
                director.StartRound(demo);
                Debug.Log("[DevShot] demo started, traits " + demo.Traits + (LaunchArgs.HasTraitArgs ? " (from the command line)" : " (default: classic)"));
            }
            catch (Exception e)
            {
                problems.Add("demo start failed: " + e.Message);
                Debug.LogError("[DevShot] demo start failed: " + e);
                Finish();
                yield break;
            }

            // 3. One shot per checkpoint: first rendered frame with Tick >= checkpoint.
            while (nextCheckpoint < DemoScenario.CheckpointTicks.Length)
            {
                if (director.Session != demo)
                {
                    problems.Add("the demo session was replaced");
                    break;
                }
                if (traitShots != null && traitShots.TryTake(demo.Sim.Tick, out string traitShot))
                {
                    yield return Capture("trait_" + traitShot, demo);
                    continue;
                }
                long target = DemoScenario.CheckpointTicks[nextCheckpoint];
                if (demo.Sim.Tick >= target || demo.Sim.Ended)
                {
                    string name = DemoScenario.CheckpointNames[nextCheckpoint];
                    nextCheckpoint++;
                    yield return Capture(name, demo);
                    continue;
                }
                yield return null;
            }

            // 4. Results screen (after the death beat), when it appears (trait shots due meanwhile are still taken).
            float resultsStart = Time.realtimeSinceStartup;
            while (director.State != GameState.Results && Time.realtimeSinceStartup - resultsStart < ResultsWaitSeconds)
            {
                if (traitShots != null && director.Session == demo && traitShots.TryTake(demo.Sim.Tick, out string traitShot))
                {
                    yield return Capture("trait_" + traitShot, demo);
                    continue;
                }
                yield return null;
            }
            if (director.State == GameState.Results)
            {
                yield return new WaitForSecondsRealtime(0.6f);
                yield return Capture("results", demo);
            }
            else problems.Add("results never showed");

            Finish();
        }

        private IEnumerator Capture(string name, GameSession session)
        {
            capturing = true;
            name = BiomeTheme.Current.CommandName + "_" + name;
            string path = Path.Combine(dir, name + ".png");
            bool resume = false;
            if (session != null && !session.Runner.Paused)
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
                Debug.LogWarning("[DevShot] could not delete the old " + path + ": " + e.Message);
            }
            long tick = session != null ? session.Sim.Tick : -1;
            ScreenCapture.CaptureScreenshot(path);
            float t0 = Time.realtimeSinceStartup;
            while (!FileReady(path) && Time.realtimeSinceStartup - t0 < FileWaitSeconds) yield return null;
            bool ok = FileReady(path);
            yield return new WaitForSecondsRealtime(AfterFileSeconds);
            if (ok) Debug.Log("[DevShot] saved " + name + ".png tick=" + tick + " state=" + (director != null ? director.State.ToString() : "?"));
            else
            {
                problems.Add(name + ".png was not written");
                Debug.LogError("[DevShot] " + name + ".png was not written within " + FileWaitSeconds + " s");
            }
            if (resume && session != null && !session.IsClosed) session.Runner.Paused = false;
            capturing = false;
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

        private void Finish()
        {
            if (done) return;
            done = true;
            if (monitor != null)
            {
                monitor.Finish();
                if (monitor.Traited)
                {
                    bool common = monitor.EvaluateTraited(out List<string> traitedFailures);
                    bool story = monitor.Evaluate(out List<string> storyFailures);
                    Debug.Log("[DevShot] scenario (traits " + demo.Traits + ") " + (common ? "PASS" : "FAIL " + string.Join("; ", traitedFailures))
                              + "; classic story " + (story ? "holds" : "differs: " + string.Join("; ", storyFailures)));
                }
                else
                {
                    bool pass = monitor.Evaluate(out List<string> failures);
                    Debug.Log("[DevShot] scenario " + (pass ? "PASS" : "FAIL " + string.Join("; ", failures)));
                }
                Debug.Log("[DevShot] facts " + monitor.Report());
            }
            if (traitShots != null)
            {
                Debug.Log("[DevShot] trait shots planned: " + string.Join(", ", traitShots.Planned) + (traitShots.PendingCount > 0 ? " (" + traitShots.PendingCount + " not taken)" : ""));
                traitShots.Detach();
            }
            if (capturing) problems.Add("finished during a capture");
            Debug.Log("[DevShot] done" + (problems.Count > 0 ? " with problems: " + string.Join("; ", problems) : "") + " -> quit 0");
            Application.Quit(0);
        }
    }
}
