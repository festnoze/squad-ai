using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using Meuble.Core;
using Newtonsoft.Json;
using UnityEngine;
using UnityEngine.UI;

namespace Meuble
{
    /// <summary>
    /// Built player self check (PRD 10.4), in the Runtime assembly so a player can run it.
    /// Inactive unless the player is launched with "--probe". "--shot &lt;dir&gt;" sets where the report
    /// and the screenshots go, "--level &lt;id&gt;" the level the game starts on (read by Main).
    /// The probe plays three short scenes on the start level (start, caught, won), then loads every other
    /// level of levels.json and screenshots its start (M2: 04_level2.png, 05_level3.png). It audits what
    /// the build actually resolved, checks the budgets of PRD 7.4 on every level, writes report.json and
    /// quits with 0 (pass) or 1 (fail).
    /// </summary>
    public sealed class Probe : MonoBehaviour
    {
        public GameState Game;
        public Hud Hud;

        private readonly List<string> failures = new List<string>();
        private readonly List<string> warnings = new List<string>();

        // Counted from before the first scene loads, so errors logged by Main.Awake are not missed.
        private static int exceptions;
        private static int errors;
        private static readonly List<string> firstErrors = new List<string>();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void ListenEarly()
        {
            if (Requested)
            {
                Application.logMessageReceived += OnLog;
            }
        }

        public static bool Requested => Array.IndexOf(Environment.GetCommandLineArgs(), "--probe") >= 0;

        private void Start()
        {
            if (!Requested)
            {
                return;
            }
            string dir = ArgValue("--shot") ?? Path.Combine(Application.persistentDataPath, "probe");
            StartCoroutine(Run(dir));
        }

        private static void OnLog(string condition, string stackTrace, LogType type)
        {
            if (type == LogType.Exception)
            {
                exceptions++;
            }
            else if (type == LogType.Error || type == LogType.Assert)
            {
                errors++;
            }
            else
            {
                return;
            }
            if (firstErrors.Count < 10)
            {
                firstErrors.Add(condition);
            }
        }

        /// <summary>The value after <paramref name="name"/> on the command line, or null.</summary>
        public static string ArgValue(string name)
        {
            string[] args = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(args, name);
            return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private IEnumerator Run(string dir)
        {
            Directory.CreateDirectory(dir);
            var report = new Dictionary<string, object>();
            var shots = new List<Dictionary<string, object>>();
            var levels = new Dictionary<string, object>();
            yield return Steps(25);

            if (Game == null || Game.Level == null)
            {
                failures.Add("no level was built");
                Finish(dir, report, shots);
                yield break;
            }

            string startLevel = Game.LevelId;
            report["startLevel"] = startLevel;
            Dictionary<string, object> startBudgets = LevelBudgets(startLevel);
            levels[startLevel] = startBudgets;
            report["audit"] = Audit(startBudgets);
            int failedSteps = Main.Instance != null ? Main.Instance.FailedSteps : -1;
            report["mainFailedSteps"] = failedSteps;
            if (failedSteps != 0)
            {
                failures.Add($"Main reported {failedSteps} failed build step(s)");
            }

            // Scene 1: the level as the player first sees it.
            yield return StartView(startLevel, startBudgets);
            yield return Shoot(dir, "01_start.png", shots);

            // Scene 2: caught. An inhabitant stares at the chair, the chair moves toward it.
            Inhabitant inhabitant = Game.MainInhabitant;
            FurnitureController chair = Game.Furniture;
            Vector3 eyeSpot = StareSpot(chair);
            inhabitant.Pin(eyeSpot, YawMath.YawOf(chair.transform.position - eyeSpot));
            chair.ScriptedDirection = YawMath.Planar(eyeSpot - chair.transform.position).normalized;
            int guard = 0;
            while (Game.State == PlayState.Playing && guard++ < 150)
            {
                yield return new WaitForFixedUpdate();
            }
            chair.ScriptedDirection = null;
            report["caughtReached"] = Game.State == PlayState.Caught;
            if (Game.State != PlayState.Caught)
            {
                failures.Add("scene caught: the state never became Caught");
            }
            report["failPanelVisible"] = Hud != null && Hud.FailVisible;
            yield return Steps(35);
            yield return Shoot(dir, "02_caught.png", shots);

            // Scene 3: won. Restart, every inhabitant looks away from the exit (from M2 the exit only counts
            // while unseen), and the chair steps onto the doormat.
            Game.Restart();
            yield return Steps(5);
            chair = Game.Furniture;
            ZoneDef exit = Game.Def.Exit;
            Vector3 exitCenter = new Vector3(exit.X, 0f, exit.Z);
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                Vector3 at = h.Routine.Position;
                h.Pin(at, YawMath.YawOf(at - exitCenter));
            }
            Vector3 approach = ExitApproach(exit);
            chair.Teleport(exitCenter - approach * 0.9f, YawMath.YawOf(approach));
            Game.Camera.Snap();
            chair.ScriptedDirection = approach;
            guard = 0;
            while (Game.State == PlayState.Playing && guard++ < 150)
            {
                yield return new WaitForFixedUpdate();
            }
            chair.ScriptedDirection = null;
            report["wonReached"] = Game.State == PlayState.Won;
            if (Game.State != PlayState.Won)
            {
                failures.Add("scene won: the state never became Won");
            }
            report["winPanelVisible"] = Hud != null && Hud.WinVisible;
            report["winNextVisible"] = Hud != null && Hud.WinNextVisible;
            if (Hud != null && Game.HasNextLevel && !Hud.WinNextVisible)
            {
                failures.Add("the win panel does not show win.next although there is a next level");
            }
            yield return Steps(25);
            if (Hud != null && Hud.TitleCardAlpha > 0f)
            {
                failures.Add("the title card overlaps the win panel");
            }
            yield return Shoot(dir, "03_won.png", shots);

            // M2: every other level of levels.json, screenshotted at its start, with its own budgets.
            report["levelOrder"] = new List<string>(Game.LevelOrder);
            if (!LevelLoader.HasManifest)
            {
                warnings.Add("levels.json is missing: only the start level was checked");
            }
            int shot = 4;
            foreach (string id in new List<string>(Game.LevelOrder))
            {
                if (id == startLevel)
                {
                    continue;
                }
                bool loaded = true;
                try
                {
                    Game.LoadLevel(id);
                }
                catch (Exception e)
                {
                    loaded = false;
                    failures.Add($"level {id} does not load: {e.Message}");
                }
                if (!loaded)
                {
                    continue;
                }
                yield return Steps(25);
                if (Game.State != PlayState.Playing)
                {
                    failures.Add($"level {id} is not Playing 0.5 s after it started ({Game.State})");
                }
                Dictionary<string, object> budgets = LevelBudgets(id);
                levels[id] = budgets;
                yield return StartView(id, budgets);
                yield return Shoot(dir, $"{shot:00}_{id}.png", shots);
                shot++;
            }
            report["levels"] = levels;

            // M2 inhabitant markers, a world space Canvas each: the "?" while Alerted, the "!" while
            // Investigating. Shot in front of the chair, on the level loaded last.
            // The inhabitant stands ahead of the chair and to the right, so neither the HUD eye (top center)
            // nor the title card (which fades out after about 5 s) hides the marker.
            Game.Restart();
            chair = Game.Furniture;
            inhabitant = Game.MainInhabitant;
            Vector3 chairAt = YawMath.Planar(chair.transform.position);
            inhabitant.Pin(inhabitant.Routine.Position, YawMath.YawOf(inhabitant.Routine.Position - chairAt));
            yield return Steps(260);
            float viewYaw = Game.Camera != null ? Game.Camera.Yaw : chair.Yaw;
            Vector3 front = chairAt + YawMath.Forward(viewYaw) * 2.4f + YawMath.Forward(viewYaw + 90f) * 1.1f;
            inhabitant.Pin(front, YawMath.YawOf(chairAt - front), 0f, true);
            inhabitant.Routine.Alert(chairAt, NoiseKind.Hop);
            yield return Steps(10);
            report["alertMarker"] = inhabitant.Marker.ToString();
            if (inhabitant.Marker != Inhabitant.MarkerKind.Question)
            {
                failures.Add($"an alerted inhabitant shows marker {inhabitant.Marker}, expected Question");
            }
            yield return Shoot(dir, $"{shot:00}_alert.png", shots);
            shot++;
            inhabitant.Routine.Investigate(chairAt);
            yield return Steps(15);
            report["investigateMarker"] = inhabitant.Marker.ToString();
            if (inhabitant.Marker != Inhabitant.MarkerKind.Exclamation)
            {
                failures.Add($"an investigating inhabitant shows marker {inhabitant.Marker}, expected Exclamation");
            }
            yield return Shoot(dir, $"{shot:00}_investigate.png", shots);
            shot++;

            // M2.1 readability on the start level. The creak warning: a still chair nobody looks at, run at 8x
            // until the warning (game time is unchanged, only faster), then back to 1x for the shot.
            Game.LoadLevel(startLevel);
            yield return Steps(2);
            chair = Game.Furniture;
            chairAt = YawMath.Planar(chair.transform.position);
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                Vector3 at = h.Routine.Position;
                h.Pin(at, YawMath.YawOf(at - chairAt));
            }
            Time.timeScale = 8f;
            guard = 0;
            while (!Game.Creak.Warning && Game.State == PlayState.Playing && guard++ < 1400)
            {
                yield return new WaitForFixedUpdate();
            }
            Time.timeScale = 1f;
            // The warning lasts 150 steps: 120 more let the title card (real time) fade before the shot.
            yield return Steps(120);
            report["creakWarning"] = Game.Creak.Warning;
            report["creakFlashing"] = Hud != null && Hud.CreakFlashing;
            if (!Game.Creak.Warning || Hud == null || !Hud.CreakFlashing)
            {
                failures.Add("scene creak: the creak warning never showed on the HUD");
            }
            yield return Shoot(dir, $"{shot:00}_creak.png", shots);
            shot++;

            // Suspicion above 0 with the ghost: the chair 1.4 m ahead of its place, an inhabitant who sees it.
            Game.Restart();
            yield return Steps(2);
            chair = Game.Furniture;
            Vector3 home = YawMath.Planar(chair.transform.position);
            viewYaw = Game.Camera != null ? Game.Camera.Yaw : chair.Yaw;
            chair.Teleport(home + YawMath.Forward(viewYaw) * 1.4f, chair.Yaw);
            inhabitant = Game.MainInhabitant;
            Vector3 stare = StareSpot(chair);
            inhabitant.Pin(stare, YawMath.YawOf(chair.transform.position - stare), 0f, true);
            guard = 0;
            while (Game.MaxSuspicion <= 0f && Game.State == PlayState.Playing && guard++ < 60)
            {
                yield return new WaitForFixedUpdate();
            }
            yield return Steps(3);
            report["suspicion"] = Math.Round(Game.MaxSuspicion, 3);
            report["ghostVisible"] = Game.Ghost != null && Game.Ghost.Visible;
            report["eye"] = Hud != null ? Hud.Eye.ToString() : "none";
            if (Game.MaxSuspicion <= 0f || Game.Ghost == null || !Game.Ghost.Visible)
            {
                failures.Add($"scene suspicion: suspicion {Game.MaxSuspicion:0.00}, ghost visible {Game.Ghost != null && Game.Ghost.Visible}");
            }
            yield return Shoot(dir, $"{shot:00}_suspicion.png", shots);
            shot++;

            // M2.2: the alarm eye on the HUD. A frozen inhabitant stares at the chair, which moves for four
            // steps (under the 0.2 s grace, so it is not caught yet) and is shot while moving.
            Game.Restart();
            yield return Steps(2);
            chair = Game.Furniture;
            inhabitant = Game.MainInhabitant;
            stare = StareSpot(chair);
            inhabitant.Pin(stare, YawMath.YawOf(chair.transform.position - stare));
            chair.ScriptedDirection = YawMath.Planar(stare - chair.transform.position).normalized;
            yield return Steps(4);
            report["alarmEye"] = Hud != null ? Hud.Eye.ToString() : "none";
            if (Hud == null || Hud.Eye != HudEye.Alarm)
            {
                failures.Add($"scene alarm: the eye shows {(Hud != null ? Hud.Eye.ToString() : "nothing")} while seen moving");
            }
            yield return Shoot(dir, $"{shot:00}_alarm.png", shots);
            chair.ScriptedDirection = null;

            Finish(dir, report, shots);
        }

        /// <summary>
        /// Where an inhabitant can stand and see the chair: the first station (of any inhabitant) at least
        /// 1.5 m away from which the vision test sees it. Falls back to the main inhabitant's position.
        /// </summary>
        private Vector3 StareSpot(FurnitureController chair)
        {
            var samples = new Vector3[Tuning.SampleCount];
            chair.GetSamplePoints(samples);
            Vector3 target = chair.transform.position;
            foreach (InhabitantDef def in Game.Def.Inhabitants)
            {
                foreach (StationDef station in def.Stations)
                {
                    Vector3 at = station.Position;
                    Vector3 flat = YawMath.Planar(target - at);
                    if (flat.magnitude < 1.5f)
                    {
                        continue;
                    }
                    Vector3 eye = at + Vector3.up * Tuning.EyeHeight;
                    if (Vision.Test(eye, YawMath.Forward(YawMath.YawOf(flat)), samples))
                    {
                        return at;
                    }
                }
            }
            return Game.MainInhabitant.Routine.Position;
        }

        /// <summary>The direction from inside the level onto the doormat: toward the exit from the room center.</summary>
        private Vector3 ExitApproach(ZoneDef exit)
        {
            Vector3 exitCenter = new Vector3(exit.X, 0f, exit.Z);
            RoomDef room = Game.Def.RoomAt(exitCenter) ?? (Game.Def.AllRooms().Count > 0 ? Game.Def.AllRooms()[0] : null);
            Vector3 roomCenter = room != null ? new Vector3(room.X, 0f, room.Z) : Vector3.zero;
            Vector3 d = YawMath.Planar(exitCenter - roomCenter);
            // Axis aligned: the doormat lies against a wall, the approach is perpendicular to it.
            Vector3 axis = Mathf.Abs(d.x) * (room != null ? room.SizeZ : 1f) >= Mathf.Abs(d.z) * (room != null ? room.SizeX : 1f)
                ? new Vector3(Mathf.Sign(d.x), 0f, 0f)
                : new Vector3(0f, 0f, Mathf.Sign(d.z));
            return axis.sqrMagnitude > 0f ? axis : Vector3.right;
        }

        /// <summary>Checks that do not depend on the level (shaders, font, labels), plus the start level's budgets.</summary>
        private Dictionary<string, object> Audit(Dictionary<string, object> startBudgets)
        {
            var audit = new Dictionary<string, object>();
            foreach (string name in new[] { PrimitiveKit.LitShaderName, PrimitiveKit.UnlitShaderName })
            {
                Shader s = Shader.Find(name);
                bool ok = s != null && s.isSupported;
                audit["shader " + name] = s == null ? "NULL" : s.isSupported ? "ok" : "unsupported";
                if (!ok)
                {
                    failures.Add("shader not resolved in the build: " + name);
                }
            }

            // The start level's numbers stay at the top level of the audit, as in M1 (verify.sh prints them).
            foreach (KeyValuePair<string, object> pair in startBudgets)
            {
                audit[pair.Key] = pair.Value;
            }

            bool fontOk = Hud != null && Hud.Font != null;
            audit["font"] = fontOk ? Hud.Font.name : "NULL";
            if (!fontOk)
            {
                failures.Add("font is null: no text renders");
            }
            var labels = new Dictionary<string, string>();
            if (Hud != null)
            {
                foreach (KeyValuePair<string, Text> pair in Hud.Labels)
                {
                    labels[pair.Key] = pair.Value != null ? pair.Value.text : null;
                    if (pair.Value == null || string.IsNullOrWhiteSpace(pair.Value.text) || pair.Value.font == null)
                    {
                        failures.Add("label without text or font: " + pair.Key);
                    }
                }
            }
            audit["labels"] = labels;
            if (labels.Count < 10)
            {
                failures.Add($"only {labels.Count} labels found, expected at least 10");
            }
            return audit;
        }

        /// <summary>
        /// What the budget counters of PRD 7.4 see in a set of renderers (M3, docs/CONTRACT_M3.md 9): every
        /// material slot counts (not only the first), skinned meshes count their triangles, and every shader
        /// that is not a URP shader is listed (the built player fails on it).
        /// </summary>
        public sealed class RenderCount
        {
            public int Renderers;
            public int MaterialSlots;
            public int SlotsWithoutMaterial;
            public long Triangles;
            public readonly HashSet<Material> Materials = new HashSet<Material>();
            public readonly List<string> NonUrp = new List<string>();
        }

        /// <summary>The URP shaders are the only ones a renderer may use (glTFast's shader graphs never render).</summary>
        public const string UrpShaderPrefix = "Universal Render Pipeline/";

        /// <summary>Counts the enabled, active renderers of <paramref name="renderers"/>.</summary>
        public static RenderCount CountRenderers(IEnumerable<Renderer> renderers)
        {
            var count = new RenderCount();
            foreach (Renderer r in renderers)
            {
                if (r == null || !r.enabled || !r.gameObject.activeInHierarchy)
                {
                    continue;
                }
                count.Renderers++;
                foreach (Material m in r.sharedMaterials)
                {
                    count.MaterialSlots++;
                    if (m == null || m.shader == null || !m.shader.isSupported || m.shader.name.Contains("InternalError"))
                    {
                        count.SlotsWithoutMaterial++;
                        continue;
                    }
                    count.Materials.Add(m);
                    if (!m.shader.name.StartsWith(UrpShaderPrefix, StringComparison.Ordinal) && count.NonUrp.Count < 10)
                    {
                        count.NonUrp.Add($"{r.name}: {m.shader.name}");
                    }
                }
                count.Triangles += ModelKit.Triangles(ModelKit.MeshOf(r));
            }
            return count;
        }

        /// <summary>
        /// Triangles under a root: every MeshFilter (a disabled renderer still counts, CONTRACT_M3 1) and every
        /// skinned mesh, the vision cone excepted.
        /// </summary>
        public static long TrianglesUnder(Transform root)
        {
            long total = 0;
            foreach (MeshFilter f in root.GetComponentsInChildren<MeshFilter>(true))
            {
                if (f.GetComponent<VisionConeView>() == null)
                {
                    total += ModelKit.Triangles(f.sharedMesh);
                }
            }
            foreach (SkinnedMeshRenderer s in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                total += ModelKit.Triangles(s.sharedMesh);
            }
            return total;
        }

        /// <summary>
        /// M3.1 B1: every visible renderer on the Occluder layer that stands between the camera and one of the top
        /// sample points of the player furniture (PRD 4.1), as "renderer (parent) hides top sample i". Visible means
        /// enabled, active, not faded to ShadowsOnly by the WallFader, and seen from its front: a triangle seen from
        /// behind is culled (the camera looks through the back of an outer wall's single sided face).
        /// </summary>
        public static List<string> ChairBlockers(Camera camera, FurnitureController chair)
        {
            var blockers = new List<string>();
            if (camera == null || chair == null)
            {
                blockers.Add("no camera or no player furniture");
                return blockers;
            }
            var samples = new Vector3[Tuning.SampleCount];
            chair.GetSamplePoints(samples);
            Vector3 eye = camera.transform.position;
            int occluder = Layers.Occluder;
            foreach (Renderer r in FindObjectsByType<Renderer>(FindObjectsSortMode.None))
            {
                if (!r.enabled || !r.gameObject.activeInHierarchy || r.gameObject.layer != occluder
                    || r.shadowCastingMode == UnityEngine.Rendering.ShadowCastingMode.ShadowsOnly || r.transform.IsChildOf(chair.transform))
                {
                    continue;
                }
                // A flat quad has flat bounds: grow them a little so the broad test never misses it.
                Bounds bounds = r.bounds;
                bounds.Expand(0.02f);
                // Samples 1 to 4 are the top corners; sample 0 is the centre.
                for (int i = 1; i < samples.Length; i++)
                {
                    Vector3 to = samples[i] - eye;
                    float length = to.magnitude;
                    if (length < 1e-4f)
                    {
                        continue;
                    }
                    var ray = new Ray(eye, to / length);
                    if (bounds.IntersectRay(ray, out float enter) && enter < length && FrontHit(r, ray, length))
                    {
                        string parent = r.transform.parent != null ? r.transform.parent.name : "";
                        blockers.Add($"{r.name} ({parent}) hides top sample {i}");
                        break;
                    }
                }
            }
            return blockers;
        }

        /// <summary>True when the ray meets a front facing triangle of the renderer's mesh before <paramref name="length"/>.</summary>
        private static bool FrontHit(Renderer r, Ray ray, float length)
        {
            Mesh mesh = ModelKit.MeshOf(r);
            if (mesh == null)
            {
                return false;
            }
            if (!mesh.isReadable || r is SkinnedMeshRenderer)
            {
                // Its bounds were hit and its triangles cannot be read where they are drawn: count it.
                return true;
            }
            Matrix4x4 m = r.transform.localToWorldMatrix;
            bool mirrored = m.determinant < 0f;
            Vector3[] v = mesh.vertices;
            for (int sub = 0; sub < mesh.subMeshCount; sub++)
            {
                int[] t = mesh.GetTriangles(sub);
                for (int i = 0; i + 2 < t.Length; i += 3)
                {
                    Vector3 a = m.MultiplyPoint3x4(v[t[i]]);
                    Vector3 b = m.MultiplyPoint3x4(v[t[i + 1]]);
                    Vector3 c = m.MultiplyPoint3x4(v[t[i + 2]]);
                    // Unity's front face winds clockwise seen from the viewer: its cross product points at the viewer.
                    Vector3 n = Vector3.Cross(b - a, c - a);
                    if (mirrored)
                    {
                        n = -n;
                    }
                    if (Vector3.Dot(n, ray.direction) >= 0f)
                    {
                        continue;
                    }
                    if (RayTriangle(ray, a, b, c, out float d) && d > 1e-4f && d < length - 1e-3f)
                    {
                        return true;
                    }
                }
            }
            return false;
        }

        /// <summary>Moller-Trumbore ray triangle intersection; <paramref name="distance"/> along the ray.</summary>
        private static bool RayTriangle(Ray ray, Vector3 a, Vector3 b, Vector3 c, out float distance)
        {
            distance = 0f;
            Vector3 e1 = b - a;
            Vector3 e2 = c - a;
            Vector3 p = Vector3.Cross(ray.direction, e2);
            float det = Vector3.Dot(e1, p);
            if (Mathf.Abs(det) < 1e-10f)
            {
                return false;
            }
            float inv = 1f / det;
            Vector3 s = ray.origin - a;
            float u = Vector3.Dot(s, p) * inv;
            if (u < 0f || u > 1f)
            {
                return false;
            }
            Vector3 q = Vector3.Cross(s, e1);
            float w = Vector3.Dot(ray.direction, q) * inv;
            if (w < 0f || u + w > 1f)
            {
                return false;
            }
            distance = Vector3.Dot(e2, q) * inv;
            return true;
        }

        /// <summary>
        /// M3.1 S3: what makes a rig, the look and the audio fail silently, checked per level in the built player:
        /// a skinned mesh and a rig with its Idle, Walk and Jump clips on every inhabitant, no look problem, and an
        /// audio library that resolves every role.
        /// </summary>
        private void RigLookAudio(string id, Dictionary<string, object> audit)
        {
            var rigs = new List<string>();
            if (Game != null && Game.Level != null)
            {
                foreach (Inhabitant h in Game.Level.Inhabitants)
                {
                    SkinnedMeshRenderer skin = h.GetComponentInChildren<SkinnedMeshRenderer>(true);
                    InhabitantRig rig = h.GetComponent<InhabitantRig>();
                    bool clips = rig != null && rig.IdleState != null && rig.WalkState != null && rig.JumpState != null;
                    rigs.Add($"{h.name}: skin {(skin != null ? skin.sharedMesh.name : "none")}, rig {(rig != null ? "yes" : "no")}, "
                        + $"clips {(rig != null ? $"{rig.IdleClipName} / {rig.WalkClipName} / {rig.JumpClipName}" : "none")}");
                    if (skin == null)
                    {
                        failures.Add($"{id}: inhabitant {h.name} has no skinned mesh");
                    }
                    if (!clips)
                    {
                        failures.Add($"{id}: inhabitant {h.name} has no rig with Idle, Walk and Jump clips");
                    }
                }
            }
            audit["rigs"] = rigs;
            List<string> look = Main.Instance != null ? Main.Instance.LookProblems() : new List<string> { "no Main" };
            audit["lookProblems"] = look;
            foreach (string p in look)
            {
                failures.Add($"{id}: look: {p}");
            }
            AudioLibrary library = AudioLibrary.Load();
            int roles = 0;
            int clipsResolved = 0;
            if (library != null)
            {
                foreach (KeyValuePair<string, AudioLibrary.Entry> pair in library.Roles())
                {
                    roles++;
                    if (AudioLibrary.Has(pair.Value))
                    {
                        clipsResolved++;
                    }
                }
            }
            audit["audioClips"] = $"{clipsResolved}/{roles}";
            if (library == null || roles == 0 || clipsResolved < roles)
            {
                failures.Add($"{id}: the audio library resolves {clipsResolved} of {roles} roles");
            }
        }

        /// <summary>
        /// M3.1 B1: at the start view, after the WallFader ran for this frame, nothing on the Occluder layer that is
        /// drawn may stand between the camera and the top of the chair.
        /// </summary>
        private IEnumerator StartView(string id, Dictionary<string, object> audit)
        {
            yield return new WaitForEndOfFrame();
            Camera cam = Game != null && Game.Camera != null ? Game.Camera.GetComponent<Camera>() : null;
            List<string> blockers = ChairBlockers(cam != null ? cam : Camera.main, Game != null ? Game.Furniture : null);
            audit["chairBlockers"] = blockers;
            foreach (string b in blockers)
            {
                failures.Add($"{id}: start view: {b}");
            }
        }

        /// <summary>The distinct bones of every skinned mesh under a root (PRD 7.4: at most 40 per inhabitant).</summary>
        public static int BonesUnder(Transform root)
        {
            var bones = new HashSet<Transform>();
            foreach (SkinnedMeshRenderer s in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                foreach (Transform b in s.bones)
                {
                    if (b != null)
                    {
                        bones.Add(b);
                    }
                }
            }
            return bones.Count;
        }

        /// <summary>PRD 7.4 budgets of the level currently built. Failures name the level.</summary>
        private Dictionary<string, object> LevelBudgets(string id)
        {
            var audit = new Dictionary<string, object>();
            RenderCount count = CountRenderers(FindObjectsByType<Renderer>(FindObjectsSortMode.None));
            int renderers = count.Renderers;
            int withoutMaterial = count.SlotsWithoutMaterial;
            long triangles = count.Triangles;
            HashSet<Material> materials = count.Materials;
            audit["renderers"] = renderers;
            audit["furnitureTriangles"] = FurnitureTriangles(id);
            audit["inhabitantTriangles"] = InhabitantTriangles(id);
            audit["inhabitantBones"] = InhabitantBones(id);
            // PRD 7.4: at most 120 draw calls. The active renderer count bounds them before batching.
            if (renderers > Tuning.BudgetRenderers)
            {
                failures.Add($"{id}: {renderers} renderers, over the 120 draw call budget even before batching");
            }
            audit["renderersWithoutMaterial"] = withoutMaterial;
            audit["triangles"] = triangles;
            audit["materials"] = materials.Count;
            audit["materialSlots"] = count.MaterialSlots;
            if (withoutMaterial > 0)
            {
                failures.Add($"{id}: {withoutMaterial} material slot(s) without a usable material");
            }
            if (triangles > Tuning.BudgetLevelTriangles)
            {
                failures.Add($"{id}: level triangles {triangles} over the 60 000 budget");
            }
            if (materials.Count > Tuning.BudgetMaterials)
            {
                failures.Add($"{id}: materials {materials.Count} over the 24 budget");
            }
            audit["nonUrpShaders"] = count.NonUrp;
            foreach (string s in count.NonUrp)
            {
                failures.Add($"{id}: renderer with a non URP shader ({s})");
            }

            // M3: the model visuals and the fallbacks (CONTRACT_M3 1: under --probe any fallback fails).
            var models = new List<string>();
            var fallbacks = new List<string>();
            if (Game != null && Game.Level != null)
            {
                foreach (GameObject m in Game.Level.ModelVisuals)
                {
                    if (m != null)
                    {
                        models.Add(m.transform.parent != null ? m.transform.parent.name + "/" + m.name : m.name);
                    }
                }
                fallbacks.AddRange(Game.Level.ModelFallbacks);
            }
            audit["modelVisuals"] = models.Count;
            audit["models"] = models;
            audit["modelFallbacks"] = fallbacks;
            foreach (string f in fallbacks)
            {
                failures.Add($"{id}: model fallback: {f}");
            }
            RigLookAudio(id, audit);

            int lights = 0;
            int shadowLights = 0;
            foreach (Light l in FindObjectsByType<Light>(FindObjectsSortMode.None))
            {
                lights++;
                if (l.shadows != LightShadows.None)
                {
                    shadowLights++;
                }
            }
            audit["lights"] = lights;
            audit["shadowedLights"] = shadowLights;
            if (shadowLights > 1)
            {
                failures.Add($"{id}: more than one shadowed light");
            }
            return audit;
        }

        /// <summary>PRD 7.4: each piece of furniture (props, decoys and the player) at most 400 triangles.</summary>
        private Dictionary<string, long> FurnitureTriangles(string id)
        {
            var result = new Dictionary<string, long>();
            if (Game == null || Game.Level == null)
            {
                return result;
            }
            var names = new HashSet<string>();
            foreach (PropDef prop in Game.Def.Props)
            {
                names.Add(prop.Name);
            }
            var pieces = new List<Transform>();
            foreach (Transform child in Game.Level.Root.transform)
            {
                if (names.Contains(child.name) || child == Game.Furniture.transform)
                {
                    pieces.Add(child);
                }
            }
            foreach (Decoy decoy in Game.Level.Decoys)
            {
                if (decoy != null && !pieces.Contains(decoy.transform))
                {
                    pieces.Add(decoy.transform);
                }
            }
            int index = 0;
            foreach (Transform piece in pieces)
            {
                long t = TrianglesUnder(piece);
                string key = result.ContainsKey(piece.name) ? piece.name + " " + index : piece.name;
                result[key] = t;
                index++;
                if (t > Tuning.BudgetFurnitureTriangles)
                {
                    failures.Add($"{id}: furniture {piece.name} has {t} triangles, over the 400 budget");
                }
            }
            return result;
        }

        /// <summary>PRD 7.4: each inhabitant at most 3 000 triangles.</summary>
        private long InhabitantTriangles(string id)
        {
            long worst = 0;
            if (Game == null || Game.Level == null)
            {
                return worst;
            }
            foreach (Inhabitant inhabitant in Game.Level.Inhabitants)
            {
                long t = TrianglesUnder(inhabitant.transform);
                worst = Math.Max(worst, t);
                if (t > Tuning.BudgetInhabitantTriangles)
                {
                    failures.Add($"{id}: inhabitant {inhabitant.name} has {t} triangles, over the 3 000 budget");
                }
            }
            return worst;
        }

        /// <summary>PRD 7.4: each inhabitant at most 40 bones (the skinned meshes' distinct bones).</summary>
        private int InhabitantBones(string id)
        {
            int worst = 0;
            if (Game == null || Game.Level == null)
            {
                return worst;
            }
            foreach (Inhabitant inhabitant in Game.Level.Inhabitants)
            {
                int b = BonesUnder(inhabitant.transform);
                worst = Math.Max(worst, b);
                if (b > Tuning.BudgetInhabitantBones)
                {
                    failures.Add($"{id}: inhabitant {inhabitant.name} has {b} bones, over the 40 budget");
                }
            }
            return worst;
        }

        private IEnumerator Shoot(string dir, string file, List<Dictionary<string, object>> shots)
        {
            yield return new WaitForEndOfFrame();
            Texture2D texture = ScreenCapture.CaptureScreenshotAsTexture();
            Color32[] pixels = texture.GetPixels32();
            double sum = 0;
            for (int i = 0; i < pixels.Length; i++)
            {
                Color32 p = pixels[i];
                sum += (0.2126 * p.r + 0.7152 * p.g + 0.0722 * p.b) / 255.0;
            }
            double mean = pixels.Length > 0 ? sum / pixels.Length : 0;
            string path = Path.Combine(dir, file);
            File.WriteAllBytes(path, texture.EncodeToPNG());
            var entry = new Dictionary<string, object>
            {
                ["file"] = file,
                ["width"] = texture.width,
                ["height"] = texture.height,
                ["meanLuminance"] = Math.Round(mean, 4),
            };
            shots.Add(entry);
            if (mean < 0.06 || mean > 0.94)
            {
                failures.Add($"screenshot {file} mean luminance {mean:0.000} is near black or near white");
            }
            Destroy(texture);
        }

        private void Finish(string dir, Dictionary<string, object> report, List<Dictionary<string, object>> shots)
        {
            report["shots"] = shots;
            report["exceptions"] = exceptions;
            report["errors"] = errors;
            report["firstErrors"] = firstErrors;
            if (exceptions > 0 || errors > 0)
            {
                failures.Add($"{exceptions} exception(s) and {errors} error(s) logged during the probe");
            }
            report["graphicsDevice"] = SystemInfo.graphicsDeviceType.ToString();
            report["unityVersion"] = Application.unityVersion;
            report["warnings"] = warnings;
            report["failures"] = failures;
            report["pass"] = failures.Count == 0;
            File.WriteAllText(Path.Combine(dir, "report.json"), JsonConvert.SerializeObject(report, Formatting.Indented));
            Debug.Log($"[Probe] pass={failures.Count == 0} failures={failures.Count} report={Path.Combine(dir, "report.json")}");
            Application.Quit(failures.Count == 0 ? 0 : 1);
        }
    }
}
