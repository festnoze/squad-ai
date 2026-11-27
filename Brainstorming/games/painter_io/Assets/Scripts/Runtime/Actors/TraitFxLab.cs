// Owned by traits-fx (wave D-2). Dev aid only, off unless "-traitfxlab <dir>" is on the command line: a scripted session
// whose territories touch the border of the arena, under Propagation (every 2 s) and Conduction, so the rim rendering
// with puddles that reach it (traits-core contract issue: with Propagation, R1's outer band is no longer always neutral),
// the growth creep and the conduction streak can be judged on player screenshots (docs/BIOME_TRAITS.md 5). The pearls
// circle inside their own discs (scripted controllers); frame code only reads; the runner is paused while a file is
// written (the DevShot discipline). Files: <dir>/<biome>_lab_<name>.png; then the player quits with exit code 0.
using System;
using System.Collections;
using System.IO;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    [DefaultExecutionOrder(1000)]
    public sealed class TraitFxLab : MonoBehaviour
    {
        public const string Flag = "-traitfxlab";
        public const string Traits = "Propagation(2,1);Conduction(1.3,0)";

        private static readonly Vec2d RightHome = new Vec2d(29.6, 2.0);    // the human: its disc touches the right side
        private static readonly Vec2d TopHome = new Vec2d(-4.0, 29.6);     // touches the top side
        private static readonly Vec2d CornerHome = new Vec2d(-24.5, -24.5); // grows into the rounded corner
        private static readonly Vec2d InnerHome = new Vec2d(22.0, -3.5);   // an inner neighbour of the human

        private static readonly long[] ShotTicks = { 40, 132, 160, 700, 1300 };
        private static readonly string[] ShotNames = { "start", "grow_a", "grow_b", "later", "late" };

        private GameDirector director;
        private string dir;
        private GameSession session;

        public static TraitFxLab TryCreate(GameDirector d)
        {
            if (d == null || !LaunchArgs.Has(Flag)) return null;
            string target = LaunchArgs.Value(Flag);
            if (string.IsNullOrEmpty(target) || target.StartsWith("-", StringComparison.Ordinal)) return null;
            var go = new GameObject("TraitFxLab");
            var lab = go.AddComponent<TraitFxLab>();
            lab.director = d;
            lab.dir = Path.GetFullPath(target);
            d.SuppressAutoPause = true;
            Application.runInBackground = true;
            return lab;
        }

        private void Start()
        {
            Directory.CreateDirectory(dir);
            StartCoroutine(Run());
        }

        private IEnumerator Run()
        {
            float t0 = Time.realtimeSinceStartup;
            while (director.State != GameState.Menu && Time.realtimeSinceStartup - t0 < 10f) yield return null;
            yield return new WaitForSecondsRealtime(1f);
            var config = new SimConfig { TickRate = 60, LassoEnabled = false, Seed = 5, Traits = RuleTraits.Parse(Traits) };
            var setup = new SimSetup
            {
                PlayerCount = 4,
                StartPositions = new[] { RightHome + new Vec2d(1.5, 0.0), TopHome + new Vec2d(1.5, 0.0), CornerHome + new Vec2d(1.5, 0.0), InnerHome + new Vec2d(1.5, 0.0) },
                StartHeadings = new[] { 0.5 * Math.PI, 0.5 * Math.PI, 0.5 * Math.PI, 0.5 * Math.PI },
                Territory = g =>
                {
                    g.FillDisc(RightHome, 3.6, 1);
                    g.FillDisc(TopHome, 3.6, 2);
                    g.FillDisc(CornerHome, 3.5, 3);
                    g.FillDisc(InnerHome, 3.0, 4);
                },
                Names = GameSession.DefaultNames(4, 0),
                HumanIndex = 0,
            };
            var controllers = new IController[]
            {
                new HomeCirclerController(RightHome), new HomeCirclerController(TopHome),
                new HomeCirclerController(CornerHome), new HomeCirclerController(InnerHome),
            };
            session = new GameSession(config, setup, controllers, false) { CountsForStats = false };
            director.StartRound(session);
            Debug.Log("[TraitFxLab] started, traits " + session.Traits);
            for (int k = 0; k < ShotTicks.Length; k++)
            {
                while (session.Sim.Tick < ShotTicks[k] && director.Session == session && Time.realtimeSinceStartup - t0 < 120f) yield return null;
                yield return Capture(ShotNames[k], null);
            }
            yield return Capture("late_top", TopHome);
            yield return Capture("late_corner", CornerHome + new Vec2d(-1.5, -1.5));
            Debug.Log("[TraitFxLab] done -> quit 0");
            Application.Quit(0);
        }

        private IEnumerator Capture(string name, Vec2d? focus)
        {
            bool resume = !session.Runner.Paused;
            session.Runner.Paused = true;
            if (focus.HasValue)
            {
                focusPoint = focus.Value;
                focusOn = true;
            }
            yield return null;
            string path = Path.Combine(dir, BiomeTheme.Current.CommandName + "_lab_" + name + ".png");
            if (File.Exists(path)) File.Delete(path);
            ScreenCapture.CaptureScreenshot(path);
            float w = Time.realtimeSinceStartup;
            while ((!File.Exists(path) || new FileInfo(path).Length == 0) && Time.realtimeSinceStartup - w < 5f) yield return null;
            yield return new WaitForSecondsRealtime(0.2f);
            focusOn = false;
            Debug.Log("[TraitFxLab] saved " + Path.GetFileName(path) + " tick=" + session.Sim.Tick);
            if (resume) session.Runner.Paused = false;
        }

        private Vec2d focusPoint;
        private bool focusOn;
        private void LateUpdate()
        {
            // While a focused shot is taken: after CameraRig (order 100), every frame until the file is written.
            if (!focusOn) return;
            Camera cam = Camera.main;
            if (cam == null) return;
            Vector3 p = cam.transform.position;
            cam.transform.position = new Vector3((float)focusPoint.X, (float)focusPoint.Y, p.z);
        }
    }
}
