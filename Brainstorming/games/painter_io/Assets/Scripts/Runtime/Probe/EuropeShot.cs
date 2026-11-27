// Europe screenshots from a built player (docs/europe/REPRISE.md, docs/europe/PROGRESSION.md). The DevShot discipline:
// everything is driven through in-process hooks (UiRoot.OpenEurope, EuropeScreen.StepSelection / SelectCode,
// GameDirector.StartCountry and the human's ExternalController), never through OS input. Every log line starts with
// "[EuropeShot]". Quits with exit code 0 when the plan is done (or after OverallTimeoutSeconds).
//
// Command line:
//   -europeshot <dir> [-europeshot-plan map,round,progress,flags] [-europeshot-size WxH] [-biome liquid|fire|electric]
//   map      : the Pays map opened (France), Monaco reached with the arrow navigation, Norway, Turkey, the UK
//   round    : a round on France with the human looping out of its home and back (two shots)
//   ride     : rule v1.9 border ride on France: the human heads to the nearest border and pushes into it at a slant with
//              one fixed heading; a shot when the ride starts and one 0.6 s later (two shots, "[EuropeShot] ride" lines)
//   progress : the map as the progression left it (combine with -europe-reset / -europe-wins / -europe-unlockall)
//   flags    : three close-up frames of the floating flags, 0.25 s apart, to judge the waving
// -europeshot-size makes the run wait (8 s max) until the window has that client size, for tall windows resized by the
// launching script after they appear.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    [DefaultExecutionOrder(1000)]
    public sealed class EuropeShot : MonoBehaviour
    {
        public const float OverallTimeoutSeconds = 150f;
        public const float FileWaitSeconds = 5f;
        public const float SettleSeconds = 0.9f;
        /// <summary>Round plan: distance to the border (arena units) at which the human turns to slide along it...</summary>
        public const double BorderApproach = 1.1;
        /// <summary>Round plan: sim seconds of each straight leg of the loop out of the home.</summary>
        public const double LoopLegSeconds = 0.9;

        private GameDirector director;
        private string dir;
        private string[] plan;
        private int wantWidth, wantHeight;
        private float startTime;
        private bool done;
        private readonly List<string> problems = new List<string>();

        // Human steering during the round plan.
        private GameSession steered;
        private int steerPhase;
        private double phaseStart, slideHeading, startHeading;
        private double rideHeading;   // ride plan: the fixed slanted push into the border (phase 6)
        private bool rideMode;
        /// <summary>Ride plan: angle (radians, 35 degrees) between the push and the outward normal (above the hold angle: slides).</summary>
        public const double RideSlant = 35.0 * Math.PI / 180.0;
        private Vec2d homePos;

        /// <summary>The EuropeShot component when "-europeshot &lt;dir&gt;" is on the command line, else null.</summary>
        public static EuropeShot TryCreate(GameDirector d)
        {
            if (!LaunchArgs.Has("-europeshot")) return null;
            string target = LaunchArgs.Value("-europeshot");
            if (string.IsNullOrEmpty(target) || target.StartsWith("-", StringComparison.Ordinal))
            {
                Debug.LogError("[EuropeShot] -europeshot needs a directory argument");
                return null;
            }
            var go = new GameObject("EuropeShot");
            var shot = go.AddComponent<EuropeShot>();
            shot.director = d;
            shot.dir = Path.GetFullPath(target);
            string p = LaunchArgs.Value("-europeshot-plan");
            shot.plan = (string.IsNullOrEmpty(p) || p.StartsWith("-", StringComparison.Ordinal) ? "map" : p)
                .ToLowerInvariant().Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
            string size = LaunchArgs.Value("-europeshot-size");
            if (!string.IsNullOrEmpty(size))
            {
                string[] wh = size.ToLowerInvariant().Split('x');
                if (wh.Length == 2) { int.TryParse(wh[0], out shot.wantWidth); int.TryParse(wh[1], out shot.wantHeight); }
            }
            if (d != null) d.SuppressAutoPause = true;
            Application.runInBackground = true;
            return shot;
        }

        private void Start()
        {
            startTime = Time.realtimeSinceStartup;
            Debug.Log("[EuropeShot] start dir=" + dir + " plan=" + string.Join(",", plan) + " screen=" + Screen.width + "x" + Screen.height
                      + " biome=" + BiomeTheme.Current.CommandName);
            try { Directory.CreateDirectory(dir); }
            catch (Exception e) { Debug.LogError("[EuropeShot] cannot create " + dir + ": " + e.Message); }
            StartCoroutine(Run());
        }

        private void Update()
        {
            if (done) return;
            if (Time.realtimeSinceStartup - startTime > OverallTimeoutSeconds)
            {
                problems.Add("overall timeout");
                Finish();
                return;
            }
            Steer();
        }

        private IEnumerator Run()
        {
            float waitStart = Time.realtimeSinceStartup;
            while (director == null || director.State != GameState.Menu)
            {
                if (Time.realtimeSinceStartup - waitStart > 10f) { problems.Add("the menu never showed"); Finish(); yield break; }
                yield return null;
            }
            if (wantWidth > 0 && wantHeight > 0)
            {
                waitStart = Time.realtimeSinceStartup;
                while ((Screen.width != wantWidth || Screen.height != wantHeight) && Time.realtimeSinceStartup - waitStart < 8f)
                    yield return null;
                if (Screen.width != wantWidth || Screen.height != wantHeight)
                    problems.Add("window is " + Screen.width + "x" + Screen.height + ", wanted " + wantWidth + "x" + wantHeight);
            }
            yield return new WaitForSecondsRealtime(1.0f);
            foreach (string step in plan)
            {
                switch (step)
                {
                    case "map": yield return MapPlan(); break;
                    case "round": yield return RoundPlan(); break;
                    case "ride": yield return RidePlan(); break;
                    case "progress": yield return ProgressPlan(); break;
                    case "flags": yield return FlagsPlan(); break;
                    default: problems.Add("unknown plan step " + step); break;
                }
            }
            Finish();
        }

        // ------------------------------------------------------------------------------------------------------------
        // Plans.

        private IEnumerator OpenMap()
        {
            UiRoot ui = UiRoot.Instance;
            if (ui == null) { problems.Add("no UiRoot"); yield break; }
            if (director.State != GameState.Menu) director.ToMenu();
            yield return null;
            ui.OpenEurope();
            yield return new WaitForSecondsRealtime(SettleSeconds + 0.6f);
        }

        private IEnumerator MapPlan()
        {
            yield return OpenMap();
            EuropeScreen screen = EuropeScreen.Active;
            if (screen == null) { problems.Add("no EuropeScreen"); yield break; }
            yield return Capture("map_open");

            // A micro-state through the arrow navigation, as a player would reach it.
            int steps = 0;
            while (screen.SelectedCode != "MC" && steps < 60)
            {
                screen.StepSelection(1);
                steps++;
                yield return null;
            }
            Debug.Log("[EuropeShot] reached " + screen.SelectedCode + " after " + steps + " arrow steps");
            yield return new WaitForSecondsRealtime(SettleSeconds);
            yield return Capture("map_monaco");
            foreach (string code in new[] { "VA", "NO", "TR", "GB" })
            {
                if (!screen.SelectCode(code)) { problems.Add("cannot select " + code); continue; }
                yield return new WaitForSecondsRealtime(SettleSeconds);
                yield return Capture("map_" + code.ToLowerInvariant());
            }
            UiRoot.Instance.CloseEurope();
            yield return new WaitForSecondsRealtime(0.4f);
        }

        private IEnumerator RoundPlan()
        {
            EuropeCatalog.Country france = Array.Find(EuropeCatalog.Load().countries, c => c.code == "FR");
            director.StartCountry(france);
            GameSession s = director.Session;
            if (s == null || director.State != GameState.Playing) { problems.Add("the France round did not start"); yield break; }
            homePos = s.Sim.Players[s.HumanIndex].Pos;
            startHeading = s.Sim.Players[s.HumanIndex].Heading;
            steered = s;
            steerPhase = 0;
            phaseStart = 0;
            string prefix = BiomeTheme.Current.CommandName + "_round_fr_";
            // 1. A short loop out of the home and back: the territory fills.
            yield return WaitPhase(s, 3, 0.7);
            yield return Capture(prefix + "capture", s);
            // 2. Out to the nearest border and along it: the country outline in view.
            if (steerPhase == 3) SetPhase(4, s, default);
            yield return WaitPhase(s, 5, 0.7);
            yield return Capture(prefix + "border", s);
            Debug.Log("[EuropeShot] round phase=" + steerPhase + " humanAlive=" + s.HumanAlive + " simTime=" + s.Sim.Time.ToString("0.0"));
            steered = null;
            director.ToMenu();
            yield return new WaitForSecondsRealtime(0.5f);
        }

        /// <summary>
        /// Rule v1.9 border ride: phase 4 to the nearest border, then phase 6 pushes into it at RideSlant from the outward
        /// normal with that heading fixed (no new input), so the head slides, rides after BorderRideDelay and follows the
        /// outline on its own. Logs the ride state, the speed and the position at both shots.
        /// </summary>
        private IEnumerator RidePlan()
        {
            EuropeCatalog.Country france = Array.Find(EuropeCatalog.Load().countries, c => c.code == "FR");
            director.StartCountry(france);
            GameSession s = director.Session;
            if (s == null || director.State != GameState.Playing) { problems.Add("the France round did not start"); yield break; }
            int h = s.HumanIndex;
            rideMode = true;
            steered = s;
            homePos = s.Sim.Players[h].Pos;
            SetPhase(4, s, default);
            string prefix = BiomeTheme.Current.CommandName + "_ride_fr_";
            float t0 = Time.realtimeSinceStartup;
            while (!s.IsClosed && !s.Sim.Ended && s.HumanAlive && Time.realtimeSinceStartup - t0 < 25f && !s.Sim.View.IsBorderRiding(h))
                yield return null;
            LogRide(s, "start");
            if (!s.Sim.View.IsBorderRiding(h)) problems.Add("the human never rode the border (BorderRide " + s.Sim.Config.BorderRide + ")");
            yield return Capture(prefix + "start", s);
            double mark = s.Sim.Time;
            t0 = Time.realtimeSinceStartup;
            while (!s.IsClosed && !s.Sim.Ended && s.HumanAlive && Time.realtimeSinceStartup - t0 < 10f && s.Sim.Time - mark < 0.6)
                yield return null;
            LogRide(s, "follow");
            yield return Capture(prefix + "follow", s);
            steered = null;
            rideMode = false;
            director.ToMenu();
            yield return new WaitForSecondsRealtime(0.5f);
        }

        private static void LogRide(GameSession s, string label)
        {
            int h = s.HumanIndex;
            PlayerState me = s.Sim.Players[h];
            var ci = System.Globalization.CultureInfo.InvariantCulture;
            Debug.Log("[EuropeShot] ride " + label + " riding=" + s.Sim.View.IsBorderRiding(h) + " rideStart=" + me.BorderRideStart.ToString("0.000", ci)
                      + " contactStart=" + me.BorderContactStart.ToString("0.000", ci) + " speed=" + s.Sim.View.EffectiveSpeed(h).ToString("0.00", ci)
                      + " pos=" + me.Pos + " headingDeg=" + (me.Heading * 180.0 / Math.PI).ToString("0.0", ci)
                      + " alive=" + me.Alive + " simTime=" + s.Sim.Time.ToString("0.00", ci));
        }

        private IEnumerator ProgressPlan()
        {
            EuropeProgression campaign = EuropeProgress.Current;   // applies -europe-reset / -europe-wins / -europe-unlockall
            Debug.Log("[EuropeShot] campaign won=" + campaign.WonCount + " unlocked=" + campaign.UnlockedCount
                      + " pool=" + string.Join(",", campaign.PlayablePool()) + " reveal=" + string.Join(",", campaign.PendingReveal));
            UiRoot ui = UiRoot.Instance;
            if (ui == null) { problems.Add("no UiRoot"); yield break; }
            ui.OpenEurope();
            // When a reveal is pending: a frame while the flags rise, one with them up (still framed together), then the
            // settled map on the selection.
            yield return new WaitForSecondsRealtime(EuropeMapView.RevealRiseSeconds * 0.75f);
            yield return Capture("progress_reveal_rise");
            yield return new WaitForSecondsRealtime(EuropeMapView.RevealSeconds - EuropeMapView.RevealRiseSeconds * 0.75f);
            yield return Capture("progress_reveal");
            yield return new WaitForSecondsRealtime(EuropeMapView.RevealHoldSeconds + 1.2f);
            yield return Capture("progress_map");
            EuropeScreen screen = EuropeScreen.Active;
            if (screen == null) { problems.Add("no EuropeScreen"); yield break; }
            // A locked country tapped: the hint, and "Jouer ce pays" refuses it.
            string locked = null;
            foreach (string code in new[] { "DE", "IT", "GB", "PL" })
            {
                if (campaign.StateOf(code) == CountryProgress.Locked) { locked = code; break; }
            }
            if (locked != null && screen.SelectCode(locked))
            {
                bool started = screen.PlaySelected();
                if (started) problems.Add("a locked country started a round");
                yield return new WaitForSecondsRealtime(SettleSeconds);
                yield return Capture("progress_locked_" + locked.ToLowerInvariant());
            }
            UiRoot.Instance.CloseEurope();
            yield return new WaitForSecondsRealtime(0.4f);
        }

        private IEnumerator FlagsPlan()
        {
            UiRoot ui = UiRoot.Instance;
            if (ui == null) { problems.Add("no UiRoot"); yield break; }
            ui.OpenEurope();
            yield return new WaitForSecondsRealtime(EuropeMapView.RevealSeconds + SettleSeconds);
            EuropeScreen screen = EuropeScreen.Active;
            if (screen == null) { problems.Add("no EuropeScreen"); yield break; }
            screen.SetCloseUp(true);
            yield return new WaitForSecondsRealtime(1.2f);
            for (int i = 0; i < 3; i++)
            {
                yield return Capture("flags_closeup_" + i);
                yield return new WaitForSecondsRealtime(0.22f);
            }
            screen.SetCloseUp(false);
            UiRoot.Instance.CloseEurope();
            yield return new WaitForSecondsRealtime(0.4f);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Helpers.

        /// <summary>Waits until the steering reached the phase and stayed in it for the given sim seconds (25 s real max).</summary>
        private IEnumerator WaitPhase(GameSession s, int phase, double seconds)
        {
            float t0 = Time.realtimeSinceStartup;
            while (!s.IsClosed && !s.Sim.Ended && s.HumanAlive && Time.realtimeSinceStartup - t0 < 25f
                   && !(steerPhase == phase && s.Sim.Time - phaseStart > seconds))
                yield return null;
        }

        /// <summary>
        /// Round plan steering. Phases 0-2: a short square loop out of the home (LoopLegSeconds per leg) and back to the
        /// start; phase 3: inside the home. Phase 4 (set by RoundPlan): to the nearest border; phase 5: sliding along it.
        /// Phase changes record phaseStart (sim time).
        /// </summary>
        private void Steer()
        {
            GameSession s = steered;
            if (s == null || s.IsClosed || s.HumanController == null || !s.HumanAlive) return;
            PlayerState me = s.Sim.Players[s.HumanIndex];
            ArenaPolygon polygon = s.Sim.Arena.Polygon;
            if (polygon == null) return;
            double distance = polygon.Distance(me.Pos, out Vec2d outward);
            double age = s.Sim.Time - phaseStart;
            switch (steerPhase)
            {
                case 0:
                    s.HumanController.Desired = startHeading;
                    if (age > LoopLegSeconds) SetPhase(1, s, outward);
                    break;
                case 1:
                    s.HumanController.Desired = Geo.WrapAngle(startHeading + 0.5 * Math.PI);
                    if (age > LoopLegSeconds) SetPhase(2, s, outward);
                    break;
                case 2:
                case 3:
                    s.HumanController.Desired = (homePos - me.Pos).Angle();
                    if (steerPhase == 2 && me.Home && age > 0.2) SetPhase(3, s, outward);
                    break;
                case 4:
                    s.HumanController.Desired = outward.Angle();
                    if (distance > -BorderApproach) SetPhase(rideMode ? 6 : 5, s, outward);
                    break;
                case 6:
                    s.HumanController.Desired = rideHeading;   // fixed: the ride follows the outline without new input
                    break;
                default:
                    s.HumanController.Desired = slideHeading;
                    break;
            }
        }

        private void SetPhase(int phase, GameSession s, Vec2d outward)
        {
            steerPhase = phase;
            phaseStart = s.Sim.Time;
            if (phase == 5) slideHeading = outward.Perp().Angle();
            if (phase == 6) rideHeading = Geo.WrapAngle(outward.Angle() + RideSlant);
        }

        private IEnumerator Capture(string name, GameSession session = null)
        {
            string path = Path.Combine(dir, name + ".png");
            bool resume = false;
            if (session != null && !session.Runner.Paused)
            {
                session.Runner.Paused = true;
                resume = true;
            }
            try { if (File.Exists(path)) File.Delete(path); }
            catch (Exception e) { Debug.LogWarning("[EuropeShot] could not delete the old " + path + ": " + e.Message); }
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(path);
            float t0 = Time.realtimeSinceStartup;
            while (!FileReady(path) && Time.realtimeSinceStartup - t0 < FileWaitSeconds) yield return null;
            yield return new WaitForSecondsRealtime(0.2f);
            if (FileReady(path)) Debug.Log("[EuropeShot] saved " + name + ".png screen=" + Screen.width + "x" + Screen.height
                                           + " state=" + director.State + (session != null ? " simTime=" + session.Sim.Time.ToString("0.00") : ""));
            else problems.Add(name + ".png was not written");
            if (resume && !session.IsClosed) session.Runner.Paused = false;
        }

        private static bool FileReady(string path)
        {
            try { return File.Exists(path) && new FileInfo(path).Length > 0; }
            catch (Exception) { return false; }
        }

        private void Finish()
        {
            if (done) return;
            done = true;
            Debug.Log("[EuropeShot] done" + (problems.Count > 0 ? " with problems: " + string.Join("; ", problems) : "") + " -> quit 0");
            Application.Quit(0);
        }
    }
}
