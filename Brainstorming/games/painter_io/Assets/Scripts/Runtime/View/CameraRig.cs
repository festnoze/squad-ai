// Owned by B3. Contract 14: the main camera (created at runtime, settings and UniversalAdditionalCameraData), 18 u wide in
// portrait / 20 u high in landscape, a critically damped follow of the human with a smoothed lookahead, the chase framing
// (head, retraction front and home target, 18 to 26 u), the attract drift following the leading bot (zoomed out to view
// scale AttractZoom since wave C, so the menu's background match reads as texture), the death beat hold,
// the results hold with a slight zoom out, and the clamp to 4 u beyond the arena.
//
// Zoom is a scalar "view scale": 1 is the base view (18 u wide in portrait, 20 u high in landscape); the chase framing
// scales it up to ChaseMaxWidth / PortraitWidth (26 / 18). In landscape the same scale applies to the 20 u height.
//
// The math is factored into public static functions (EditMode tests: InputCameraMathTests).
// Dev aids: "-camdebug" draws a uGUI overlay (arena grid, heads, trails, chase points, framing numbers) so the framing can be
// judged on DevShot images before the liquid renderer exists; with "-devshot" or "-camdebug" the rig logs one
// "[CameraRig] checkpoint ..." line per DemoScenario checkpoint.
using System;
using System.Collections.Generic;
using System.Globalization;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.Rendering.Universal;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    /// <summary>What the camera is doing (contract 14).</summary>
    public enum CameraMode { Follow, Chase, Attract, DeathHold, ResultsHold }

    [DefaultExecutionOrder(100)]
    public sealed class CameraRig : MonoBehaviour
    {
        public const float CameraZ = -50f;
        /// <summary>Visible width in portrait at view scale 1 (u).</summary>
        public const float PortraitWidth = 18f;
        /// <summary>Visible height in landscape at view scale 1 (u).</summary>
        public const float LandscapeHeight = 20f;

        /// <summary>Critically damped follow of the target (s).</summary>
        public const float FollowHalfLife = 0.12f;
        /// <summary>Lookahead along the human's heading (u).</summary>
        public const float LookaheadDistance = 1.2f;
        /// <summary>The lookahead vector is smoothed by its own critically damped spring (s).</summary>
        public const float LookaheadHalfLife = 0.35f;
        /// <summary>Chase framing: padding around the head, the front and the home target (u).</summary>
        public const float ChasePadding = 1.5f;
        /// <summary>Chase framing: the needed width is multiplied by this before the clamp.</summary>
        public const float ChaseMargin = 1.15f;
        /// <summary>Chase framing: the widest view (u, portrait width).</summary>
        public const float ChaseMaxWidth = 26f;
        /// <summary>Chase framing eases in with this exponential half-life (s).</summary>
        public const float ChaseInHalfLife = 0.25f;
        /// <summary>After a chase the view goes back to the base width over this time (s, smoothstep).</summary>
        public const float ChaseOutSeconds = 0.6f;
        /// <summary>The view never shows more than this beyond the arena edge (u).</summary>
        public const float ArenaOverscan = 4f;
        /// <summary>Attract (menu) drift: critically damped follow of the leading bot (s).</summary>
        public const float AttractHalfLife = 0.8f;
        /// <summary>
        /// Wave C (feel-06): view scale of the attract match behind the menu, so its puddles read as background texture
        /// (reached with the ResultsZoomHalfLife ease like the other non-chase zoom targets).
        /// </summary>
        public const float AttractZoom = 1.4f;
        /// <summary>Death beat and results: critically damped glide to the hold point (s).</summary>
        public const float HoldHalfLife = 0.3f;
        /// <summary>Results: slight zoom out (view scale).</summary>
        public const float ResultsZoom = 1.1f;
        /// <summary>Results zoom out and other non-chase zoom changes: exponential half-life (s).</summary>
        public const float ResultsZoomHalfLife = 0.5f;
        /// <summary>Attract: the current leader keeps the camera until another bot owns this much more territory.</summary>
        public const float LeaderHysteresis = 1.1f;
        /// <summary>HomeArrow target search radius (u, GridQueries.NearestOwned).</summary>
        public const double HomeSearchRadius = 40.0;
        /// <summary>Longest frame step the springs integrate at once (s).</summary>
        public const float MaxDeltaTime = 0.25f;
        /// <summary>k with (1 + k) e^-k = 1/2: a critically damped spring at rest covers half the distance in one half-life.</summary>
        public const float SpringHalfLifeConstant = 1.67834699f;

        /// <summary>The widest chase view scale (26 / 18).</summary>
        public static float MaxChaseScale => ChaseMaxWidth / PortraitWidth;

        /// <summary>The live rig (null before GameDirector built it or after teardown).</summary>
        public static CameraRig Current { get; private set; }

        private GameDirector director;
        private Camera cam;
        private GameSession boundSession;
        private bool snapPending = true;

        private Vector2 position, velocity;
        private Vector2 lookahead, lookaheadVelocity;
        private Vector2 followTarget;
        private bool holding;
        private Vector2 holdPoint;
        private int leader = -1;

        private float scale = 1f;
        private bool wasChased, returning;
        private float returnFrom, returnTime;

        private Simulation homeSim;
        private long homeTick = -1;
        private int homeVersion = -1;
        private bool homeFound;
        private Vector2 homeTarget;

        private bool hasFront;
        private Vector2 frontPoint;
        private float chaseScaleTarget = 1f;

        private bool logCheckpoints;
        private readonly bool[] checkpointLogged = new bool[DemoScenario.CheckpointTicks.Length];
        private bool resultsLogged;
        private DebugOverlay overlay;
        private bool errorLogged;

        public Camera Camera => cam;

        /// <summary>The current view scale (1 = 18 u wide in portrait, 20 u high in landscape).</summary>
        public float ViewScale => scale;

        /// <summary>What the rig did during the last LateUpdate.</summary>
        public CameraMode Mode { get; private set; } = CameraMode.Attract;

        /// <summary>The world rectangle the main camera shows after the last LateUpdate.</summary>
        public Rect ViewRect
        {
            get
            {
                if (cam == null) return new Rect();
                float h = cam.orthographicSize, w = h * Aspect(cam);
                Vector3 p = cam.transform.position;
                return new Rect(p.x - w, p.y - h, 2f * w, 2f * h);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Pure math (tested in EditMode).

        /// <summary>Base orthographic size: 9 / aspect in portrait (18 u wide), 10 in landscape (20 u high).</summary>
        public static float BaseOrthoSize(float aspect)
        {
            if (!(aspect > 0f)) aspect = 9f / 16f;
            return aspect <= 1f ? PortraitWidth * 0.5f / aspect : LandscapeHeight * 0.5f;
        }

        /// <summary>Orthographic size of the base view times viewScale.</summary>
        public static float OrthoSizeFor(float aspect, float viewScale)
        {
            return BaseOrthoSize(aspect) * viewScale;
        }

        /// <summary>Visible width (u) of the view at viewScale (18 * viewScale in portrait).</summary>
        public static float ViewWidthFor(float aspect, float viewScale)
        {
            if (!(aspect > 0f)) aspect = 9f / 16f;
            return 2f * OrthoSizeFor(aspect, viewScale) * aspect;
        }

        /// <summary>
        /// Exact critically damped spring step toward a fixed target. halfLife is the time a spring at rest needs to cover
        /// half the distance; the result does not depend on how dt is subdivided. halfLife &lt;= 0 snaps.
        /// </summary>
        public static void CriticalSpring(ref float x, ref float v, float target, float halfLife, float dt)
        {
            if (!(halfLife > 0f))
            {
                x = target;
                v = 0f;
                return;
            }
            if (!(dt > 0f)) return;
            double y = SpringHalfLifeConstant / (double)halfLife;
            double j0 = x - target;
            double j1 = v + j0 * y;
            double e = Math.Exp(-y * dt);
            x = (float)(e * (j0 + j1 * dt) + target);
            v = (float)(e * (v - j1 * y * dt));
        }

        /// <summary>CriticalSpring on both components.</summary>
        public static void CriticalSpring(ref Vector2 x, ref Vector2 v, Vector2 target, float halfLife, float dt)
        {
            float xx = x.x, vx = v.x, xy = x.y, vy = v.y;
            CriticalSpring(ref xx, ref vx, target.x, halfLife, dt);
            CriticalSpring(ref xy, ref vy, target.y, halfLife, dt);
            x = new Vector2(xx, xy);
            v = new Vector2(vx, vy);
        }

        /// <summary>Exponential approach: the distance to target halves every halfLife seconds. halfLife &lt;= 0 snaps.</summary>
        public static float ExpApproach(float x, float target, float halfLife, float dt)
        {
            if (!(halfLife > 0f)) return target;
            if (!(dt > 0f)) return x;
            return target + (x - target) * Mathf.Pow(2f, -dt / halfLife);
        }

        /// <summary>
        /// The view scale the camera eases to outside a chase: AttractZoom behind the menu, ResultsZoom on the results hold,
        /// 1 otherwise (Follow, DeathHold; Chase uses ChaseScale on top of this base).
        /// </summary>
        public static float ZoomTargetFor(CameraMode mode)
        {
            switch (mode)
            {
                case CameraMode.Attract: return AttractZoom;
                case CameraMode.ResultsHold: return ResultsZoom;
                default: return 1f;
            }
        }

        /// <summary>Smoothstep from `from` to `to` over duration seconds; t is the time since the start.</summary>
        public static float SmoothReturn(float from, float to, float t, float duration)
        {
            if (!(duration > 0f)) return to;
            float u = Mathf.Clamp01(t / duration);
            return Mathf.Lerp(from, to, u * u * (3f - 2f * u));
        }

        /// <summary>
        /// Contract 14 chase framing as a view scale: the view centered on center must contain head, front and (when hasHome)
        /// home with ChasePadding on every side; the needed size is multiplied by ChaseMargin and clamped to
        /// [1, MaxChaseScale]. In portrait this is clamp(1.15 x the needed width, 18, 26) / 18, the needed width accounting
        /// for the vertical extent through the aspect ratio.
        /// </summary>
        public static float ChaseScale(Vector2 center, Vector2 head, Vector2 front, bool hasHome, Vector2 home, float aspect)
        {
            if (!(aspect > 0f)) aspect = 9f / 16f;
            float halfW = 0f, halfH = 0f;
            Extend(ref halfW, ref halfH, center, head);
            Extend(ref halfW, ref halfH, center, front);
            if (hasHome) Extend(ref halfW, ref halfH, center, home);
            halfW += ChasePadding;
            halfH += ChasePadding;
            float neededOrtho = Mathf.Max(halfH, halfW / aspect);
            return Mathf.Clamp(ChaseMargin * neededOrtho / BaseOrthoSize(aspect), 1f, MaxChaseScale);
        }

        /// <summary>The visible width (u) of the chase framing: ViewWidthFor(aspect, ChaseScale(...)).</summary>
        public static float ChaseViewWidth(Vector2 center, Vector2 head, Vector2 front, bool hasHome, Vector2 home, float aspect)
        {
            return ViewWidthFor(aspect, ChaseScale(center, head, front, hasHome, home, aspect));
        }

        /// <summary>
        /// Contract 14 clamp: the camera center such that the view (half extents halfWidth, halfHeight) never shows more than
        /// overscan beyond the arena [-arenaHalf, arenaHalf]^2. An axis wider than the limit is centered on 0.
        /// </summary>
        public static Vector2 ClampCenter(Vector2 center, float halfWidth, float halfHeight, float arenaHalf, float overscan)
        {
            float limit = arenaHalf + overscan;
            float x = halfWidth >= limit ? 0f : Mathf.Clamp(center.x, -limit + halfWidth, limit - halfWidth);
            float y = halfHeight >= limit ? 0f : Mathf.Clamp(center.y, -limit + halfHeight, limit - halfHeight);
            return new Vector2(x, y);
        }

        /// <summary>ClampCenter with the arena of Tuning and ArenaOverscan.</summary>
        public static Vector2 ClampCenter(Vector2 center, float halfWidth, float halfHeight)
        {
            return ClampCenter(center, halfWidth, halfHeight, (float)Tuning.ArenaHalfSize, ArenaOverscan);
        }

        private static void Extend(ref float halfW, ref float halfH, Vector2 center, Vector2 p)
        {
            halfW = Mathf.Max(halfW, Mathf.Abs(p.x - center.x));
            halfH = Mathf.Max(halfH, Mathf.Abs(p.y - center.y));
        }

        // ------------------------------------------------------------------------------------------------------------
        // Lifecycle.

        /// <summary>Contract 11.1 entry point: creates the main camera (contract 14) and the rig on it.</summary>
        public static CameraRig Create(GameDirector d)
        {
            var go = new GameObject("CameraRig");
            go.tag = "MainCamera";
            var cam = go.AddComponent<Camera>();
            cam.orthographic = true;
            cam.transform.SetPositionAndRotation(new Vector3(0f, 0f, CameraZ), Quaternion.identity);
            cam.depth = 0f;
            cam.cullingMask = ~(1 << LiquidLayers.Field);
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = Palette.OutsideColor;   // the biome's (LiquidRenderer re-applies it on BiomeTheme.Changed)
            cam.nearClipPlane = 0.1f;
            cam.farClipPlane = 200f;
            cam.allowHDR = false;
            cam.allowMSAA = false;
            cam.useOcclusionCulling = false;
            UniversalAdditionalCameraData data = cam.GetUniversalAdditionalCameraData();
            if (data != null)
            {
                data.renderPostProcessing = false;   // LiquidRenderer sets it on High when bloom is enabled
                data.renderShadows = false;
                data.requiresDepthOption = CameraOverrideOption.Off;
                data.requiresColorOption = CameraOverrideOption.Off;
                data.antialiasing = AntialiasingMode.None;
            }
            // The only AudioListener of the game (B5's Sfx must not add another one).
            if (UnityEngine.Object.FindAnyObjectByType<AudioListener>() == null) go.AddComponent<AudioListener>();
            var rig = go.AddComponent<CameraRig>();
            rig.director = d;
            rig.cam = cam;
            if (d != null) d.SessionStarted += rig.OnSessionStarted;
            rig.cam.orthographicSize = OrthoSizeFor(Aspect(cam), 1f);
            rig.logCheckpoints = LaunchArgs.Has("-devshot") || LaunchArgs.Has("-camdebug");
            if (LaunchArgs.Has("-camdebug"))
            {
                try
                {
                    rig.overlay = new DebugOverlay(go.transform);
                }
                catch (Exception e)
                {
                    Debug.LogWarning("[CameraRig] debug overlay failed: " + e.Message);
                }
            }
            Current = rig;
            return rig;
        }

        private void OnDestroy()
        {
            if (Current == this) Current = null;
            if (director != null) director.SessionStarted -= OnSessionStarted;
        }

        private void OnSessionStarted(GameSession s)
        {
            // A new session snaps to its subject; an attract session restarting itself (same object) keeps drifting.
            bool attractRestart = s != null && s == boundSession;
            boundSession = s;
            holding = false;
            leader = -1;
            homeSim = null;
            homeTick = -1;
            resultsLogged = false;
            for (int k = 0; k < checkpointLogged.Length; k++) checkpointLogged[k] = false;
            if (!attractRestart) snapPending = true;
        }

        private void LateUpdate()
        {
            if (cam == null) return;
            try
            {
                Step(Mathf.Clamp(Time.unscaledDeltaTime, 0f, MaxDeltaTime));
            }
            catch (Exception e)
            {
                if (errorLogged) return;
                errorLogged = true;
                Debug.LogError("[PainterIO] CameraRig failed: " + e);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Per frame.

        private void Step(float dt)
        {
            float aspect = Aspect(cam);
            GameSession s = director != null ? director.Session : null;
            if (s != null && s.IsClosed) s = null;

            Vector2 target = followTarget;
            float halfLife = HoldHalfLife;
            float zoomBase = 1f;
            bool chased = false;
            hasFront = false;
            chaseScaleTarget = 1f;

            if (s == null)
            {
                Mode = CameraMode.DeathHold;
            }
            else if (s.IsAttract || s.HumanIndex < 0)
            {
                Mode = CameraMode.Attract;
                holding = false;
                int lead = LeadingPlayer(s.Sim);
                if (lead >= 0) target = PlayerPos(s, lead);
                halfLife = AttractHalfLife;
                zoomBase = ZoomTargetFor(CameraMode.Attract);
                CriticalSpring(ref lookahead, ref lookaheadVelocity, Vector2.zero, LookaheadHalfLife, dt);
                followTarget = target;
            }
            else
            {
                int h = s.HumanIndex;
                PlayerState p = s.Sim.Players[h];
                bool results = director.State == GameState.Results;
                if (results || !p.Alive || director.InResultsBeat || s.Sim.Ended)
                {
                    // Death beat: hold on the splash (the elimination point). Round end with the human alive and results:
                    // hold where the camera was looking; results add a slight zoom out.
                    if (!holding)
                    {
                        holding = true;
                        holdPoint = p.Alive ? followTarget : ToVector(p.Pos);
                    }
                    Mode = results ? CameraMode.ResultsHold : CameraMode.DeathHold;
                    target = holdPoint;
                    halfLife = HoldHalfLife;
                    zoomBase = ZoomTargetFor(Mode);
                }
                else
                {
                    holding = false;
                    Vector2 head = s.RenderPos(h);
                    Vector2 lookTarget = new Vector2((float)Math.Cos(p.Heading), (float)Math.Sin(p.Heading)) * LookaheadDistance;
                    if (snapPending)
                    {
                        lookahead = lookTarget;
                        lookaheadVelocity = Vector2.zero;
                    }
                    else CriticalSpring(ref lookahead, ref lookaheadVelocity, lookTarget, LookaheadHalfLife, dt);
                    target = head + lookahead;
                    followTarget = target;
                    halfLife = FollowHalfLife;
                    if (p.Spark != null)
                    {
                        chased = true;
                        double sr = s.RenderSparkS(h);
                        Vector2 front = head;
                        if (!double.IsNaN(sr) && !p.Trail.IsEmpty)
                        {
                            front = ToVector(p.Trail.PointAt(sr));
                            hasFront = true;
                            frontPoint = front;
                        }
                        bool hasHome = HomeTarget(s, p, out Vector2 home);
                        chaseScaleTarget = ChaseScale(target, head, front, hasHome, home, aspect);
                    }
                    Mode = chased ? CameraMode.Chase : CameraMode.Follow;
                }
            }

            if (snapPending && s != null)
            {
                snapPending = false;
                scale = Mathf.Max(zoomBase, chased ? chaseScaleTarget : 1f);
                wasChased = chased;
                returning = false;
                velocity = Vector2.zero;
                float o = OrthoSizeFor(aspect, scale);
                position = ClampCenter(target, o * aspect, o);
            }
            else UpdateZoom(dt, chased, chaseScaleTarget, zoomBase);

            float ortho = OrthoSizeFor(aspect, scale);
            float halfH = ortho, halfW = ortho * aspect;
            cam.orthographicSize = ortho;

            Vector2 goal = ClampCenter(target, halfW, halfH);
            CriticalSpring(ref position, ref velocity, goal, halfLife, dt);
            Vector2 clamped = ClampCenter(position, halfW, halfH);
            if (clamped.x != position.x) velocity.x = 0f;
            if (clamped.y != position.y) velocity.y = 0f;
            position = clamped;
            cam.transform.position = new Vector3(position.x, position.y, CameraZ);

            if (s != null && logCheckpoints) LogCheckpoints(s, aspect);
            if (overlay != null) overlay.Update(this, s);
        }

        private void UpdateZoom(float dt, bool chased, float chaseTarget, float baseTarget)
        {
            if (chased)
            {
                scale = ExpApproach(scale, Mathf.Max(chaseTarget, baseTarget), ChaseInHalfLife, dt);
                wasChased = true;
                returning = false;
                return;
            }
            if (wasChased)
            {
                wasChased = false;
                returning = true;
                returnFrom = scale;
                returnTime = 0f;
            }
            if (returning)
            {
                returnTime += dt;
                scale = SmoothReturn(returnFrom, 1f, returnTime, ChaseOutSeconds);
                if (returnTime >= ChaseOutSeconds) returning = false;
                return;
            }
            scale = ExpApproach(scale, baseTarget, ResultsZoomHalfLife, dt);
        }

        /// <summary>HomeArrow target (GridQueries.NearestOwned from the sim head), computed at most once per tick.</summary>
        private bool HomeTarget(GameSession s, PlayerState p, out Vector2 home)
        {
            Simulation sim = s.Sim;
            if (homeSim != sim || homeTick != sim.Tick || homeVersion != sim.Grid.Version)
            {
                homeSim = sim;
                homeTick = sim.Tick;
                homeVersion = sim.Grid.Version;
                homeFound = GridQueries.NearestOwned(sim.Grid, p.Id, p.Pos, HomeSearchRadius, out Vec2d t, out double _);
                homeTarget = homeFound ? ToVector(t) : Vector2.zero;
            }
            home = homeTarget;
            return homeFound;
        }

        private Vector2 PlayerPos(GameSession s, int index)
        {
            PlayerState p = s.Sim.Players[index];
            return p.Alive ? s.RenderPos(index) : ToVector(p.Pos);
        }

        private int LeadingPlayer(Simulation sim)
        {
            // The alive player with the most cells; the current leader keeps the camera until beaten by 10 %.
            int best = -1, bestCells = -1;
            for (int i = 0; i < sim.Players.Count; i++)
            {
                PlayerState p = sim.Players[i];
                if (!p.Alive) continue;
                int c = sim.Grid.CountOf(p.Id);
                if (c > bestCells)
                {
                    bestCells = c;
                    best = i;
                }
            }
            if (best < 0) return leader >= 0 && leader < sim.Players.Count ? leader : -1;
            if (leader >= 0 && leader < sim.Players.Count && sim.Players[leader].Alive)
            {
                if (sim.Grid.CountOf(sim.Players[leader].Id) * LeaderHysteresis >= bestCells) return leader;
            }
            leader = best;
            return best;
        }

        private static float Aspect(Camera c)
        {
            float a = c != null ? c.aspect : 0f;
            if (!(a > 0f) || float.IsInfinity(a)) a = Screen.height > 0 ? Screen.width / (float)Screen.height : 9f / 16f;
            return a > 0f ? a : 9f / 16f;
        }

        private static Vector2 ToVector(Vec2d v)
        {
            return new Vector2((float)v.X, (float)v.Y);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Dev aids.

        private void LogCheckpoints(GameSession s, float aspect)
        {
            if (!s.IsAttract)
            {
                long tick = s.Sim.Tick;
                for (int k = 0; k < checkpointLogged.Length; k++)
                {
                    if (checkpointLogged[k] || tick < DemoScenario.CheckpointTicks[k]) continue;
                    checkpointLogged[k] = true;
                    Debug.Log("[CameraRig] checkpoint " + DemoScenario.CheckpointNames[k] + " " + Describe(s, aspect));
                }
            }
            if (!resultsLogged && director != null && director.State == GameState.Results)
            {
                resultsLogged = true;
                Debug.Log("[CameraRig] results " + Describe(s, aspect));
            }
        }

        private string Describe(GameSession s, float aspect)
        {
            Rect view = ViewRect;
            var sb = new System.Text.StringBuilder();
            sb.Append("tick=").Append(s.Sim.Tick).Append(" mode=").Append(Mode).Append(" scale=").Append(F(scale))
              .Append(" view=").Append(F(view.width)).Append('x').Append(F(view.height))
              .Append(" center=").Append(V(view.center));
            if (s.HumanIndex >= 0)
            {
                PlayerState p = s.Sim.Players[s.HumanIndex];
                Vector2 head = p.Alive ? s.RenderPos(s.HumanIndex) : ToVector(p.Pos);
                sb.Append(" human=").Append(V(head)).Append(view.Contains(head) ? " in" : " OUT").Append(" alive=").Append(p.Alive);
                if (hasFront) sb.Append(" front=").Append(V(frontPoint)).Append(view.Contains(frontPoint) ? " in" : " OUT");
                if (Mode == CameraMode.Chase && homeFound) sb.Append(" home=").Append(V(homeTarget)).Append(view.Contains(homeTarget) ? " in" : " OUT");
                if (Mode == CameraMode.Chase) sb.Append(" chaseTarget=").Append(F(chaseScaleTarget)).Append(" (width ")
                                                 .Append(F(ViewWidthFor(aspect, chaseScaleTarget))).Append(')');
            }
            return sb.ToString();
        }

        private static string F(float v)
        {
            return v.ToString("0.00", CultureInfo.InvariantCulture);
        }

        private static string V(Vector2 v)
        {
            return "(" + F(v.x) + "," + F(v.y) + ")";
        }

        /// <summary>
        /// "-camdebug" only: a uGUI overlay drawn over the game (arena grid every 8 u, arena edge, player heads in their
        /// colors, trails as dots, the retraction front, the home target and the framing numbers).
        /// </summary>
        private sealed class DebugOverlay
        {
            private const int GridStep = 8;
            private const int TrailDots = 700;
            private const float TrailSpacing = 0.4f;

            private readonly RectTransform root;
            private readonly List<Image> lines = new List<Image>();
            private readonly List<float> lineCoords = new List<float>();
            private readonly List<bool> lineVertical = new List<bool>();
            private readonly Image[] heads = new Image[8];
            private readonly Image[] dots = new Image[TrailDots];
            private readonly Image front, home;
            private readonly Text label;

            public DebugOverlay(Transform parent)
            {
                var go = new GameObject("CameraDebugOverlay");
                go.transform.SetParent(parent, false);
                var canvas = go.AddComponent<Canvas>();
                canvas.renderMode = RenderMode.ScreenSpaceOverlay;
                canvas.sortingOrder = 30000;
                root = (RectTransform)go.transform;
                float half = (float)Tuning.ArenaHalfSize;
                for (int c = -(int)half; c <= (int)half; c += GridStep)
                {
                    bool edge = Mathf.Abs(Mathf.Abs(c) - half) < 0.01f;
                    Color color = edge ? new Color(1f, 1f, 1f, 0.55f) : new Color(1f, 1f, 1f, 0.12f);
                    AddLine(c, true, color);
                    AddLine(c, false, color);
                }
                for (int k = 0; k < dots.Length; k++) dots[k] = MakeImage("dot", Color.white, 3f);
                for (int k = 0; k < heads.Length; k++) heads[k] = MakeImage("head", Color.white, 10f);
                front = MakeImage("front", Color.white, 12f);
                home = MakeImage("home", new Color(0.3f, 1f, 0.3f, 1f), 12f);
                var labelGo = new GameObject("label", typeof(RectTransform));
                labelGo.transform.SetParent(root, false);
                label = labelGo.AddComponent<Text>();
                label.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
                label.fontSize = 16;
                label.color = Color.white;
                label.raycastTarget = false;
                label.alignment = TextAnchor.LowerLeft;
                var rt = label.rectTransform;
                rt.anchorMin = rt.anchorMax = Vector2.zero;
                rt.pivot = Vector2.zero;
                rt.anchoredPosition = new Vector2(8f, 8f);
                rt.sizeDelta = new Vector2(1000f, 60f);
            }

            private void AddLine(float coord, bool vertical, Color color)
            {
                Image img = MakeImage("line", color, 1f);
                lines.Add(img);
                lineCoords.Add(coord);
                lineVertical.Add(vertical);
            }

            private Image MakeImage(string name, Color color, float size)
            {
                var go = new GameObject(name, typeof(RectTransform));
                go.transform.SetParent(root, false);
                var img = go.AddComponent<Image>();
                img.color = color;
                img.raycastTarget = false;
                RectTransform rt = img.rectTransform;
                rt.anchorMin = rt.anchorMax = Vector2.zero;
                rt.pivot = new Vector2(0.5f, 0.5f);
                rt.sizeDelta = new Vector2(size, size);
                img.enabled = false;
                return img;
            }

            private static void Place(Image img, Vector2 screen, Vector2 size)
            {
                img.rectTransform.anchoredPosition = screen;
                img.rectTransform.sizeDelta = size;
                img.enabled = true;
            }

            public void Update(CameraRig rig, GameSession s)
            {
                Camera cam = rig.cam;
                float ppu = cam.pixelHeight / (2f * cam.orthographicSize);
                float half = (float)Tuning.ArenaHalfSize;
                for (int k = 0; k < lines.Count; k++)
                {
                    float c = lineCoords[k];
                    bool edge = Mathf.Abs(Mathf.Abs(c) - half) < 0.01f;
                    float thick = edge ? 2f : 1f;
                    Vector2 mid = ToScreen(cam, lineVertical[k] ? new Vector2(c, 0f) : new Vector2(0f, c));
                    Vector2 size = lineVertical[k] ? new Vector2(thick, 2f * half * ppu) : new Vector2(2f * half * ppu, thick);
                    Place(lines[k], mid, size);
                }
                int dot = 0;
                for (int k = 0; k < heads.Length; k++) heads[k].enabled = false;
                if (s != null)
                {
                    Simulation sim = s.Sim;
                    for (int i = 0; i < sim.Players.Count && i < heads.Length; i++)
                    {
                        PlayerState p = sim.Players[i];
                        Color color = Palette.ColorOf(i);
                        Vector2 pos = p.Alive ? s.RenderPos(i) : new Vector2((float)p.Pos.X, (float)p.Pos.Y);
                        Place(heads[i], ToScreen(cam, pos), Vector2.one * Mathf.Max(6f, 2f * (float)Tuning.HeadRadius * ppu));
                        heads[i].color = p.Alive ? color : new Color(color.r, color.g, color.b, 0.35f);
                        Trail t = p.Trail;
                        if (!p.Alive || t.IsEmpty) continue;
                        for (double a = 0.0; a <= t.Length && dot < dots.Length; a += TrailSpacing)
                        {
                            Vec2d q = t.PointAt(a);
                            Image d = dots[dot++];
                            Place(d, ToScreen(cam, new Vector2((float)q.X, (float)q.Y)), new Vector2(3f, 3f));
                            d.color = color;
                        }
                    }
                }
                for (; dot < dots.Length; dot++) dots[dot].enabled = false;
                front.enabled = rig.hasFront;
                if (rig.hasFront) Place(front, ToScreen(cam, rig.frontPoint), new Vector2(12f, 12f));
                home.enabled = rig.Mode == CameraMode.Chase && rig.homeFound;
                if (home.enabled) Place(home, ToScreen(cam, rig.homeTarget), new Vector2(12f, 12f));
                Rect view = rig.ViewRect;
                label.text = "cam " + rig.Mode + "  scale " + F(rig.scale) + "  view " + F(view.width) + " x " + F(view.height)
                             + "  center " + V(view.center) + (s != null ? "  tick " + s.Sim.Tick : "")
                             + (rig.Mode == CameraMode.Chase ? "  chase target " + F(rig.chaseScaleTarget) : "");
            }

            private static Vector2 ToScreen(Camera cam, Vector2 world)
            {
                Vector3 p = cam.WorldToScreenPoint(new Vector3(world.x, world.y, 0f));
                return new Vector2(p.x, p.y);
            }
        }
    }
}
