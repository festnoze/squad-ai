// Owned by B1. Debug-only render lab (command line "-renderlab <dir>"): plays a scripted session whose territories are
// designed to stress the liquid look, saves screenshots, then quits with exit code 0. It complements DevShot (B0a): the
// demo round no longer shows a fill since contract 24 (a chased return captures nothing), and it has no touching colors.
//   - coral (the human) and teal discs that overlap: the crease where two colors meet;
//   - a saffron 45 degree band and vertical strips 1, 2, 3 and 4 cells wide: no staircase on diagonal edges (V6), thin
//     territories;
//   - a lilac square rotated by 30 degrees: straight edges at an angle, corners;
//   - the human leaves its disc, draws a rectangle and comes back unchased: the fill wave (mid-fill screenshot).
// Shots: lab_start.png, lab_thread.png, lab_midfill.png, lab_filled.png (plus the quality tier in the log line). The
// session is driven only by its scripted controllers; frame code only reads, and the runner is paused while a file is
// written (the DevShot discipline).
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    [DefaultExecutionOrder(1000)]
    public sealed class RenderLab : MonoBehaviour
    {
        public const string Flag = "-renderlab";
        public const long StartTick = 20;
        public const long ThreadTick = 100;

        private static readonly Vec2d HumanHome = new Vec2d(0.0, -4.0);
        private static readonly Vec2d TealHome = new Vec2d(5.0, -4.0);
        private static readonly Vec2d SaffronHome = new Vec2d(-6.0, 9.5);
        private static readonly Vec2d LilacHome = new Vec2d(5.0, 6.5);

        private GameDirector director;
        private LiquidRenderer liquid;
        private string dir;
        private GameSession session;
        private double returnTime = double.NaN;
        private readonly List<string> problems = new List<string>();
        private readonly List<float> frameMs = new List<float>();

        public static RenderLab TryCreate(Transform parent, GameDirector d, LiquidRenderer r)
        {
            if (!LaunchArgs.Has(Flag)) return null;
            string target = LaunchArgs.Value(Flag);
            if (string.IsNullOrEmpty(target) || target.StartsWith("-", StringComparison.Ordinal))
            {
                Debug.LogError("[RenderLab] -renderlab needs a directory argument");
                return null;
            }
            var go = new GameObject("RenderLab");
            if (parent != null) go.transform.SetParent(parent, false);
            var lab = go.AddComponent<RenderLab>();
            lab.director = d;
            lab.liquid = r;
            lab.dir = Path.GetFullPath(target);
            if (d != null) d.SuppressAutoPause = true;
            Application.runInBackground = true;
            return lab;
        }

        private void Start()
        {
            try
            {
                Directory.CreateDirectory(dir);
            }
            catch (Exception e)
            {
                Debug.LogError("[RenderLab] cannot create " + dir + ": " + e.Message);
            }
            StartCoroutine(Run());
        }

        private IEnumerator Run()
        {
            float t0 = Time.realtimeSinceStartup;
            while (director == null || director.State != GameState.Menu)
            {
                if (Time.realtimeSinceStartup - t0 > 10f) break;
                yield return null;
            }
            yield return new WaitForSecondsRealtime(0.5f);
            try
            {
                session = CreateSession();
                session.EventRaised += OnEvent;
                director.StartRound(session);
                Debug.Log("[RenderLab] started, tier " + QualityTier.Current + ", screen " + Screen.width + "x" + Screen.height);
            }
            catch (Exception e)
            {
                Debug.LogError("[RenderLab] start failed: " + e);
                Finish();
                yield break;
            }
            yield return WaitTick(StartTick);
            yield return Capture("lab_start");
            yield return WaitTick(ThreadTick);
            yield return Capture("lab_thread");
            float w0 = Time.realtimeSinceStartup;
            TerritoryField field = liquid != null ? liquid.Territory : null;
            while (field != null && (double.IsNaN(returnTime) || field.VisualTime() < returnTime + 0.15))
            {
                if (Time.realtimeSinceStartup - w0 > 20f || session.Sim.Ended)
                {
                    problems.Add("no unchased return");
                    break;
                }
                yield return null;
            }
            yield return Capture("lab_midfill");
            long after = session.Sim.Tick + 60;
            yield return WaitTick(after);
            yield return Capture("lab_filled");
            Finish();
        }

        private void Update()
        {
            if (session != null && !session.Runner.Paused && !session.Sim.Ended) frameMs.Add(Time.unscaledDeltaTime * 1000f);
        }

        private IEnumerator WaitTick(long tick)
        {
            float w0 = Time.realtimeSinceStartup;
            while (session.Sim.Tick < tick && !session.Sim.Ended && Time.realtimeSinceStartup - w0 < 20f) yield return null;
        }

        private IEnumerator Capture(string name)
        {
            string path = Path.Combine(dir, name + ".png");
            bool resume = !session.Runner.Paused;
            session.Runner.Paused = true;
            try
            {
                if (File.Exists(path)) File.Delete(path);
            }
            catch (Exception)
            {
                // Overwritten below.
            }
            long tick = session.Sim.Tick;
            ScreenCapture.CaptureScreenshot(path);
            float t0 = Time.realtimeSinceStartup;
            while (!Ready(path) && Time.realtimeSinceStartup - t0 < 5f) yield return null;
            yield return new WaitForSecondsRealtime(0.2f);
            if (Ready(path)) Debug.Log("[RenderLab] saved " + name + ".png tick=" + tick);
            else problems.Add(name + ".png not written");
            if (resume && !session.IsClosed) session.Runner.Paused = false;
        }

        private static bool Ready(string path)
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

        private void OnEvent(SimEvent e)
        {
            if (e.Type == SimEventType.Return && e.Player == 0 && e.Cells != null && e.Cells.Length > 0 && double.IsNaN(returnTime))
            {
                returnTime = e.Time;
                Debug.Log("[RenderLab] return t=" + e.Time.ToString("0.000") + " cells=" + e.Cells.Length);
            }
        }

        private void Finish()
        {
            if (frameMs.Count > 10)
            {
                frameMs.Sort();
                float sum = 0f;
                foreach (float ms in frameMs) sum += ms;
                Debug.Log("[RenderLab] perf frames=" + frameMs.Count + " avgMs=" + (sum / frameMs.Count).ToString("0.00")
                          + " p95Ms=" + frameMs[(int)(frameMs.Count * 0.95f)].ToString("0.00") + " tier=" + QualityTier.Current
                          + " actorRT=" + (liquid != null && liquid.ActorField != null && liquid.ActorField.Texture != null
                              ? liquid.ActorField.Texture.width + "x" + liquid.ActorField.Texture.height + " " + liquid.ActorField.Format : "none")
                          + " passRuns=" + (liquid != null && liquid.Territory != null ? liquid.Territory.PassRuns : 0));
            }
            Debug.Log("[RenderLab] done" + (problems.Count > 0 ? " with problems: " + string.Join("; ", problems) : "") + " -> quit 0");
            Application.Quit(0);
        }

        private static GameSession CreateSession()
        {
            var config = new SimConfig { TickRate = 60, LassoEnabled = false, Seed = 7 };
            var setup = new SimSetup
            {
                PlayerCount = 4,
                HumanIndex = 0,
                StartPositions = new[] { HumanHome, TealHome + new Vec2d(1.5, 0.0), SaffronHome + new Vec2d(1.2, 0.0), LilacHome + new Vec2d(1.2, 0.0) },
                StartHeadings = new[] { -Math.PI * 0.5, Math.PI * 0.5, Math.PI * 0.5, Math.PI * 0.5 },
                Territory = Paint,
                Names = GameSession.DefaultNames(4, 0),
            };
            var path = new List<Vec2d>
            {
                new Vec2d(0.0, -9.5), new Vec2d(-4.5, -9.5), new Vec2d(-4.5, -4.0), new Vec2d(-1.0, -4.0),
            };
            var controllers = new IController[]
            {
                new DemoScenario.PathThenCircleController(path, HumanHome),
                new HomeCirclerController(TealHome),
                new HomeCirclerController(SaffronHome),
                new HomeCirclerController(LilacHome),
            };
            return new GameSession(config, setup, controllers, false);
        }

        private static void Paint(OwnerGrid g)
        {
            g.FillDisc(HumanHome, 3.5, 1);
            g.FillDisc(TealHome, 3.5, 2);                       // overlaps the coral disc: the crease
            g.FillDisc(SaffronHome, 2.6, 3);
            FillWhere(g, 3, p => DistanceToSegment(p, new Vec2d(-8.0, 1.0), new Vec2d(-6.0, 9.5)) <= 0.8);   // steep band
            FillWhere(g, 3, p => DistanceToSegment(p, new Vec2d(-6.0, 9.5), new Vec2d(2.0, 13.5)) <= 0.7);   // 27 degree band
            FillWhere(g, 3, p => DistanceToSegment(p, new Vec2d(-11.0, -2.0), new Vec2d(-6.0, 3.0)) <= 0.6); // 45 degree band
            // Vertical strips 1, 2, 3 and 4 cells wide.
            double cs = g.CellSize;
            double x = -8.0;
            for (int width = 1; width <= 4; width++)
            {
                double x0 = x, x1 = x + width * cs;
                FillWhere(g, 3, p => p.X >= x0 && p.X < x1 && p.Y > -15.0 && p.Y < -9.0);
                x += width * cs + 0.9;
            }
            // Lilac square of side 5 rotated by 30 degrees.
            double c = Math.Cos(Math.PI / 6.0), s = Math.Sin(Math.PI / 6.0);
            FillWhere(g, 4, p =>
            {
                double dx = p.X - LilacHome.X, dy = p.Y - LilacHome.Y;
                double u = c * dx + s * dy, v = -s * dx + c * dy;
                return Math.Abs(u) <= 2.5 && Math.Abs(v) <= 2.5;
            });
        }

        private static void FillWhere(OwnerGrid g, byte owner, Func<Vec2d, bool> inside)
        {
            for (int j = 0; j < g.Size; j++)
            {
                for (int i = 0; i < g.Size; i++)
                {
                    int index = g.Index(i, j);
                    if (g.Cells[index] == OwnerGrid.Void) continue;
                    if (inside(g.CellCenter(i, j))) g.Set(index, owner);
                }
            }
        }

        private static double DistanceToSegment(Vec2d p, Vec2d a, Vec2d b)
        {
            return Geo.DistancePointSegment(p, a, b);
        }
    }
}
