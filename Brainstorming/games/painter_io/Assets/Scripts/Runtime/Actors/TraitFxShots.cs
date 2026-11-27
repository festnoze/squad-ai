// Owned by traits-fx (wave D-2). Dev aid only, off unless "-traitfxshots <dir>" is on the command line (used with
// -devshot, which drives the scripted demo round): saves extra screenshots at fixed delays after the trait events, so the
// generic trait visuals of docs/BIOME_TRAITS.md 5 and 7.2 can be judged mid-animation (DevShot's own trait shots come
// 10 ticks after an event, before the inherited sweep has started). Files: <dir>/<biome>_fx_<name>.png, each name once.
// It never steers the sim and never pauses the runner.
using System;
using System.Collections.Generic;
using System.IO;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class TraitFxShots
    {
        private struct Due
        {
            public float At;
            public string Name;
            public bool Focus;
            public Vector2 Where;
        }

        private static readonly List<Due> due = new List<Due>();
        private static readonly HashSet<string> planned = new HashSet<string>();
        private static string dir;
        private static bool parsed;

        /// <summary>True when "-traitfxshots &lt;dir&gt;" is on the command line.</summary>
        public static bool Enabled
        {
            get
            {
                if (!parsed)
                {
                    parsed = true;
                    string d = LaunchArgs.Has("-traitfxshots") ? LaunchArgs.Value("-traitfxshots") : null;
                    if (!string.IsNullOrEmpty(d) && !d.StartsWith("-", StringComparison.Ordinal))
                    {
                        try
                        {
                            dir = Path.GetFullPath(d);
                            Directory.CreateDirectory(dir);
                        }
                        catch (Exception e)
                        {
                            Debug.LogWarning("[TraitFxShots] " + e.Message);
                            dir = null;
                        }
                    }
                }
                return dir != null;
            }
        }

        /// <summary>Forgets the plan (session start).</summary>
        public static void Reset()
        {
            due.Clear();
            planned.Clear();
        }

        /// <summary>Plans the screenshots of a sim event (now = ActorContext.Time).</summary>
        public static void OnEvent(SimEvent e, float now, int human, Simulation sim)
        {
            if (!Enabled || e == null) return;
            switch (e.Type)
            {
                case SimEventType.TerritoryGrew:
                    if (e.Player != human) break;
                    Plan("grow_a", now + 0.25f);
                    Plan("grow_b", now + 0.7f);
                    break;
                case SimEventType.TerritoryInherited:
                    Plan("inherit_a", now + 0.4f, Centroid(e.Cells, sim));
                    Plan("inherit_b", now + 0.62f, Centroid(e.Cells, sim));
                    Plan("inherit_c", now + 0.85f, Centroid(e.Cells, sim));
                    break;
                case SimEventType.SpeedBoosted:
                    Plan("boost", now + 0.2f);
                    Plan("boost_held", now + 1.2f);
                    break;
                case SimEventType.ShieldStarted:
                    Plan("shield_pop", now + 0.12f);
                    Plan("shield", now + 1.0f);
                    Plan("shield_warn", now + 2.5f);
                    break;
                case SimEventType.ShieldEnded:
                    Plan("shield_end", now + 0.08f);
                    break;
                case SimEventType.Eliminated:
                    if (e.Cells == null || e.Cells.Length == 0) break;
                    Plan("elim_a", now + 0.3f, Centroid(e.Cells, sim));
                    Plan("elim_b", now + 0.6f, Centroid(e.Cells, sim));
                    Plan("elim_c", now + 0.85f, Centroid(e.Cells, sim));
                    break;
            }
        }

        /// <summary>Takes the screenshots whose time has come (called once per frame by ActorViews).</summary>
        public static void Tick(float now)
        {
            if (dir == null || due.Count == 0) return;
            for (int k = due.Count - 1; k >= 0; k--)
            {
                if (due[k].At > now) continue;
                string name = BiomeTheme.Current.CommandName + "_fx_" + due[k].Name + ".png";
                Due d = due[k];
                due.RemoveAt(k);
                try
                {
                    // Looks at the land of the event (this frame only: CameraRig places the camera again next frame).
                    Camera cam = Camera.main;
                    if (d.Focus && cam != null)
                    {
                        Vector3 at = cam.transform.position;
                        cam.transform.position = new Vector3(d.Where.x, d.Where.y, at.z);
                    }
                    ScreenCapture.CaptureScreenshot(Path.Combine(dir, name));
                    Debug.Log("[TraitFxShots] saved " + name);
                }
                catch (Exception e)
                {
                    Debug.LogWarning("[TraitFxShots] " + name + ": " + e.Message);
                }
                return;   // one per frame
            }
        }

        private static void Plan(string name, float at)
        {
            if (!planned.Add(name)) return;
            due.Add(new Due { At = at, Name = name });
        }

        private static void Plan(string name, float at, Vector2 where)
        {
            if (!planned.Add(name)) return;
            due.Add(new Due { At = at, Name = name, Focus = true, Where = where });
        }

        private static Vector2 Centroid(int[] cells, Simulation sim)
        {
            if (cells == null || cells.Length == 0 || sim == null) return Vector2.zero;
            OwnerGrid g = sim.Grid;
            double sx = 0.0, sy = 0.0;
            for (int k = 0; k < cells.Length; k++)
            {
                sx += g.Origin + (cells[k] % g.Size + 0.5) * g.CellSize;
                sy += g.Origin + (cells[k] / g.Size + 0.5) * g.CellSize;
            }
            return new Vector2((float)(sx / cells.Length), (float)(sy / cells.Length));
        }
    }
}
