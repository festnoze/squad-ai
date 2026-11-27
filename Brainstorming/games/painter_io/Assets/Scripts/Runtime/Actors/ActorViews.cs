// Owned by BI since wave B-2 (written by B2). Contract 11.1 entry point and 12.3: everything that moves on the liquid (threads, pearls,
// retraction fronts and droplet chains, cut flashes, the lasso ring, charge rings, the home arrow, the screen edge
// indicators and the elimination splashes). ActorViews builds one view set per sim player, rebinds on SessionStarted
// (also raised on attract restarts) and drives every view from LateUpdate, after CameraRig (order 100) and before
// ActorFieldCamera (order 200). Each view runs in its own try/catch (logged once) so one failure never hides the rest.
// Contract 25.2: beads (pearls, droplets, splash drops, evaporating beads) use BiomeTheme.Current's BeadShader and the
// overlays (cut flash, ring, charge ring, home arrow, indicators, glints) its OverlayShader, with the same vertex data;
// on BiomeTheme.Changed every batch re-binds its shader live. Colors come from Palette (the biome's PlayerColors).
// Wave D-2 (traits-fx, docs/BIOME_TRAITS.md 5 and 7.2): TraitFxView draws the generic trait visuals (conduction streak,
// reach arcs, speed aura, shield film, timer ring and shimmering trail) after the pearls and the charge ring.
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    /// <summary>Shared per-frame state handed to every actor view.</summary>
    public sealed class ActorContext
    {
        public GameDirector Director;
        public GameSession Session;
        public Simulation Sim;
        public Camera Camera;

        /// <summary>Animation clock in seconds: follows the session (stops while the runner is paused, slows with slow motion).</summary>
        public float Time;
        public float Dt;

        /// <summary>Unscaled real time (screen indicators keep pulsing during slow motion).</summary>
        public float RealTime;
        public float RealDt;

        /// <summary>Specular lobes of the current quality tier (1 or 2), from the _PIO_Quality global (x).</summary>
        public float Lobes = 1f;

        public Material FieldBlobMaterial;
        public Material FieldStrokeMaterial;
        public Shader BeadShader;
        public Shader OverlayShader;

        public QuadBatch Pearls;
        public QuadBatch Overlays;
        public QuadBatch Indicators;

        /// <summary>World rectangle seen by the main camera this frame.</summary>
        public Rect ViewRect;

        /// <summary>Screen pixels per world unit (main camera).</summary>
        public float PixelsPerUnit = 30f;

        /// <summary>Pixel rectangle usable by screen edge indicators (safe area, HUD top bar excluded).</summary>
        public Rect IndicatorRect;

        /// <summary>Screen scale relative to the 1920 px reference height of the UI.</summary>
        public float UiScale = 0.5f;

        /// <summary>CameraRig view scale this frame (1 = the base view, up to 26 / 18 in a chase; 1 without a rig). Views
        /// that keep a constant screen size multiply their world sizes by it (HomeArrow).</summary>
        public float ViewScale = 1f;

        public int Human => Session != null ? Session.HumanIndex : -1;

        public bool HasCamera => Camera != null;

        public Color LinearColor(int player)
        {
            return Palette.LinearColorOf(player);
        }

        /// <summary>True when the world point lies inside the camera view grown by margin world units.</summary>
        public bool IsOnScreen(Vector2 world, float margin)
        {
            if (Camera == null) return true;
            return world.x >= ViewRect.xMin - margin && world.x <= ViewRect.xMax + margin
                && world.y >= ViewRect.yMin - margin && world.y <= ViewRect.yMax + margin;
        }

        public Vector2 WorldToScreen(Vector2 world)
        {
            if (Camera == null) return world;
            Vector3 s = Camera.WorldToScreenPoint(new Vector3(world.x, world.y, 0f));
            return new Vector2(s.x, s.y);
        }

        public Vector2 ScreenToWorld(Vector2 screen)
        {
            if (Camera == null) return screen;
            float depth = Mathf.Max(1f, -Camera.transform.position.z);
            Vector3 w = Camera.ScreenToWorldPoint(new Vector3(screen.x, screen.y, depth));
            return new Vector2(w.x, w.y);
        }

        /// <summary>
        /// Where an edge indicator for an off-screen world target sits: the intersection of the ray from the indicator
        /// rectangle's center toward the target with that rectangle. Returns false when the target is on screen.
        /// </summary>
        public bool EdgePlacement(Vector2 targetWorld, out Vector2 edgeScreen, out Vector2 dirScreen)
        {
            edgeScreen = Vector2.zero;
            dirScreen = Vector2.right;
            if (Camera == null) return false;
            Vector2 sp = WorldToScreen(targetWorld);
            Rect r = IndicatorRect;
            Vector2 c = r.center;
            Vector2 d = sp - c;
            if (d.sqrMagnitude < 1e-6f) return false;
            dirScreen = d.normalized;
            float hx = Mathf.Max(1f, r.width * 0.5f), hy = Mathf.Max(1f, r.height * 0.5f);
            float kx = Mathf.Abs(d.x) > 1e-6f ? hx / Mathf.Abs(d.x) : float.MaxValue;
            float ky = Mathf.Abs(d.y) > 1e-6f ? hy / Mathf.Abs(d.y) : float.MaxValue;
            float k = Mathf.Min(kx, ky);
            edgeScreen = c + d * Mathf.Min(1f, k);
            return true;
        }
    }

    /// <summary>Root of the actor views (contract 11.1 factory ActorViews.Create).</summary>
    [DefaultExecutionOrder(150)]
    public sealed class ActorViews : MonoBehaviour
    {
        /// <summary>The live instance (null before Create or after destruction).</summary>
        public static ActorViews Instance { get; private set; }

        private static readonly int QualityId = Shader.PropertyToID("_PIO_Quality");

        private GameDirector director;
        private GameSession session;
        private Simulation boundSim;
        private readonly ActorContext ctx = new ActorContext();
        private readonly HashSet<string> failed = new HashSet<string>();

        private ThreadView[] threads = new ThreadView[0];
        private PearlView[] pearls = new PearlView[0];
        private RetractionView[] retractions = new RetractionView[0];
        private CutFlash cutFlash;
        private RingView ringView;
        private ChargeRing chargeRing;
        private HomeArrow homeArrow;
        private SparkEdgeIndicator sparkEdge;
        private RingIndicator ringIndicator;
        private SplashView splash;
        private TraitFxView traitFx;
        private bool hidden = true;

        /// <summary>Wave D-2: the trait visuals (null if they failed to build).</summary>
        public TraitFxView TraitFx => traitFx;

        /// <summary>The spark edge indicator (screen position for the tutorial pointer, contract 12.3 / 15.4).</summary>
        public SparkEdgeIndicator SparkEdge => sparkEdge;

        /// <summary>The home arrow (target of the human's way home while chased).</summary>
        public HomeArrow HomeArrow => homeArrow;

        public static ActorViews Create(GameDirector d)
        {
            var go = new GameObject("ActorViews");
            var v = go.AddComponent<ActorViews>();
            v.director = d;
            v.Build();
            TraitFxLab.TryCreate(d);   // dev aid, only with -traitfxlab <dir>
            if (d != null)
            {
                d.SessionStarted += v.OnSessionStarted;
                d.StateChanged += v.OnStateChanged;
                if (d.Session != null) v.OnSessionStarted(d.Session);
            }
            return v;
        }

        /// <summary>
        /// Where the tutorial pointer should point while the human is chased (contract 15.4): the retraction front's
        /// screen position when it is on screen, else the spark edge indicator's. Screen pixels, origin bottom left.
        /// False when the human has no visible front.
        /// </summary>
        public bool TryGetSparkPointer(out Vector2 screenPosition, out bool onEdge)
        {
            screenPosition = Vector2.zero;
            onEdge = false;
            int h = ctx.Human;
            if (h < 0 || h >= retractions.Length || retractions[h] == null || !retractions[h].HasFront) return false;
            if (SparkEdgeIndicator.IsVisible)
            {
                screenPosition = SparkEdgeIndicator.ScreenPosition;
                onEdge = true;
                return true;
            }
            screenPosition = ctx.WorldToScreen(retractions[h].FrontWorld);
            return true;
        }

        /// <summary>World position of a player's retraction front (false when that player has no live front).</summary>
        public bool TryGetFront(int player, out Vector2 world)
        {
            world = Vector2.zero;
            if (player < 0 || player >= retractions.Length || retractions[player] == null || !retractions[player].HasFront) return false;
            world = retractions[player].FrontWorld;
            return true;
        }

        private void Awake()
        {
            Instance = this;
        }

        private void Build()
        {
            transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            transform.localScale = Vector3.one;
            Guard("shaders", () =>
            {
                BiomeTheme theme = BiomeTheme.Current;
                ctx.BeadShader = theme.ResolveBead();
                ctx.OverlayShader = theme.ResolveOverlay();
                if (ctx.BeadShader == null) ctx.BeadShader = ActorShaders.Load(BiomeTheme.LiquidBeadShader);
                if (ctx.OverlayShader == null) ctx.OverlayShader = ActorShaders.Load(BiomeTheme.LiquidOverlayShader);
                Shader blob = ActorShaders.Load("FieldBlob");
                Shader stroke = ActorShaders.Load("FieldStroke");
                if (blob != null) ctx.FieldBlobMaterial = new Material(blob) { name = "PIO_ActorFieldBlob" };
                if (stroke != null) ctx.FieldStrokeMaterial = new Material(stroke) { name = "PIO_ActorFieldStroke" };
            });
            Guard("batches", () =>
            {
                ctx.Pearls = new QuadBatch("Pearls", transform, ctx.BeadShader, QuadBatch.QueuePearls, 30);
                ctx.Overlays = new QuadBatch("Overlays", transform, ctx.OverlayShader, QuadBatch.QueueOverlays, 40);
                ctx.Indicators = new QuadBatch("Indicators", transform, ctx.OverlayShader, QuadBatch.QueueIndicators, 50);
            });
            Guard("CutFlash", () => cutFlash = new CutFlash());
            Guard("RingView", () => ringView = new RingView());
            Guard("ChargeRing", () => chargeRing = new ChargeRing());
            Guard("HomeArrow", () => homeArrow = new HomeArrow());
            Guard("SparkEdgeIndicator", () => sparkEdge = new SparkEdgeIndicator());
            Guard("RingIndicator", () => ringIndicator = new RingIndicator());
            Guard("SplashView", () => splash = new SplashView(transform, ctx.BeadShader));
            Guard("TraitFxView", () => traitFx = new TraitFxView(transform, ctx.OverlayShader));
            EnsurePlayers(Tuning.PlayerCount);
            BiomeTheme.Changed += OnBiomeChanged;
        }

        /// <summary>Contract 25.2: the new biome's Bead and Overlay shaders on every batch (same vertex data, no restart).</summary>
        private void OnBiomeChanged(BiomeTheme theme)
        {
            if (this == null)
            {
                BiomeTheme.Changed -= OnBiomeChanged;   // destroyed in edit mode without OnDestroy
                return;
            }
            Guard("biome shaders", () =>
            {
                if (theme == null) return;
                Shader bead = theme.ResolveBead();
                Shader overlay = theme.ResolveOverlay();
                if (bead != null) ctx.BeadShader = bead;
                if (overlay != null) ctx.OverlayShader = overlay;
                QuadBatch.RebindAll(ctx.BeadShader, ctx.OverlayShader);
            });
        }

        private void OnDestroy()
        {
            if (director != null)
            {
                director.SessionStarted -= OnSessionStarted;
                director.StateChanged -= OnStateChanged;
            }
            BiomeTheme.Changed -= OnBiomeChanged;
            if (session != null) session.EventRaised -= OnSimEvent;
            session = null;
            foreach (ThreadView t in threads) t?.Destroy();
            foreach (PearlView p in pearls) p?.Destroy();
            foreach (RetractionView r in retractions) r?.Destroy();
            splash?.Destroy();
            traitFx?.Destroy();
            ctx.Pearls?.Destroy();
            ctx.Overlays?.Destroy();
            ctx.Indicators?.Destroy();
            if (ctx.FieldBlobMaterial != null) Destroy(ctx.FieldBlobMaterial);
            if (ctx.FieldStrokeMaterial != null) Destroy(ctx.FieldStrokeMaterial);
            if (Instance == this) Instance = null;
        }

        private void EnsurePlayers(int count)
        {
            if (count <= threads.Length) return;
            int old = threads.Length;
            Array.Resize(ref threads, count);
            Array.Resize(ref pearls, count);
            Array.Resize(ref retractions, count);
            for (int i = old; i < count; i++)
            {
                int player = i;
                Guard("ThreadView", () => threads[player] = new ThreadView(player, transform, ctx.FieldStrokeMaterial, ctx.BeadShader));
                Guard("PearlView", () => pearls[player] = new PearlView(player, transform, ctx.FieldBlobMaterial));
                Guard("RetractionView", () => retractions[player] = new RetractionView(player, transform, ctx.FieldBlobMaterial, ctx.BeadShader));
            }
        }

        private void OnStateChanged(GameState state)
        {
            // Views read the session every frame; nothing to switch here.
        }

        private void OnSessionStarted(GameSession s)
        {
            if (session != null) session.EventRaised -= OnSimEvent;
            session = s;
            boundSim = s != null ? s.Sim : null;
            if (s != null)
            {
                s.EventRaised -= OnSimEvent;
                s.EventRaised += OnSimEvent;
                EnsurePlayers(s.Sim.Players.Count);
            }
            TraitFxShots.Reset();
            ResetViews();
        }

        private void ResetViews()
        {
            for (int i = 0; i < threads.Length; i++)
            {
                Guard("ThreadView", () => threads[i]?.Reset());
                Guard("PearlView", () => pearls[i]?.Reset());
                Guard("RetractionView", () => retractions[i]?.Reset());
            }
            Guard("CutFlash", () => cutFlash?.Reset());
            Guard("RingView", () => ringView?.Reset());
            Guard("ChargeRing", () => chargeRing?.Reset());
            Guard("HomeArrow", () => homeArrow?.Reset());
            Guard("SparkEdgeIndicator", () => sparkEdge?.Reset());
            Guard("RingIndicator", () => ringIndicator?.Reset());
            Guard("SplashView", () => splash?.Reset());
            Guard("TraitFxView", () => traitFx?.Reset());
        }

        private void OnSimEvent(SimEvent e)
        {
            if (e == null || session == null) return;
            if (TraitFxShots.Enabled) TraitFxShots.OnEvent(e, ctx.Time, session.HumanIndex, session.Sim);   // dev aid (-traitfxshots)
            int p = e.Player;
            bool valid = p >= 0 && p < threads.Length;
            switch (e.Type)
            {
                case SimEventType.Exit:
                    if (!valid) break;
                    pearls[p]?.OnExit(e);
                    threads[p]?.OnExit(e);
                    break;
                case SimEventType.Return:
                    if (!valid) break;
                    pearls[p]?.OnReturn(session, e, ctx.Time);
                    threads[p]?.OnReturn(e, ctx.Time, session.Sim);
                    retractions[p]?.OnReturn(e, ctx.Time);
                    break;
                case SimEventType.Cut:
                    cutFlash?.Spawn(ctx, new Vector2((float)e.Point.X, (float)e.Point.Y));
                    if (valid) retractions[p]?.OnCut(e, ctx.Time);
                    break;
                case SimEventType.SparkCaught:
                    if (valid) retractions[p]?.OnCaught(ctx.Time);
                    break;
                case SimEventType.Eliminated:
                    if (!valid) break;
                    if (pearls[p] != null && pearls[p].WasVisible && splash != null)
                    {
                        splash.Spawn(pearls[p].LastPosition, ctx.LinearColor(p), p, ctx.Time, e.Time);
                    }
                    pearls[p]?.OnEliminated();
                    threads[p]?.OnEliminated(ctx.Time);
                    retractions[p]?.OnEliminated(ctx.Time);
                    break;
                case SimEventType.RingSpawned:
                    ringView?.OnSpawned(ctx.Time);
                    break;
                case SimEventType.RingPicked:
                    ringView?.OnPicked(p, ctx.Time);
                    break;
                case SimEventType.SpeedBoosted:
                case SimEventType.ShieldStarted:
                case SimEventType.ShieldEnded:
                    if (!valid || traitFx == null) break;
                    try
                    {
                        PearlView pv = pearls[p];
                        traitFx.OnEvent(e, ctx.Time, pv != null ? pv.LastPosition : session.RenderPos(p),
                                        pv != null ? pv.LastRadius : (float)Tuning.HeadRadius);
                    }
                    catch (Exception ex) { Report("TraitFxView", ex); }
                    break;
            }
        }

        private void LateUpdate()
        {
            GameSession s = director != null ? director.Session : session;
            if (s != session) OnSessionStarted(s);
            if (s == null || s.IsClosed)
            {
                HideAll();
                return;
            }
            if (s.Sim != boundSim)
            {
                // An attract restart replaced the Simulation (SessionStarted normally reports it first).
                boundSim = s.Sim;
                EnsurePlayers(s.Sim.Players.Count);
                ResetViews();
            }
            hidden = false;
            PrepareContext(s);

            ctx.Pearls?.Begin();
            ctx.Overlays?.Begin();
            ctx.Indicators?.Begin();

            // Inline try/catch per view (no closures: LateUpdate allocates no managed memory).
            int n = Mathf.Min(s.Sim.Players.Count, threads.Length);
            int human = s.HumanIndex;
            // Retraction first: it publishes the front position the thread and the indicators use this frame.
            for (int i = 0; i < n; i++)
            {
                try { retractions[i]?.Tick(ctx); }
                catch (Exception e) { Report("RetractionView", e); }
            }
            for (int i = 0; i < n; i++)
            {
                try { threads[i]?.Tick(ctx); }
                catch (Exception e) { Report("ThreadView", e); }
            }
            // Pearls: bots first, the human last (on top).
            bool chased = false;
            try { chased = homeArrow != null && homeArrow.HumanChased(ctx); }
            catch (Exception e) { Report("HomeArrow", e); }
            for (int i = 0; i < n; i++)
            {
                if (i == human) continue;
                try { pearls[i]?.Tick(ctx, false); }
                catch (Exception e) { Report("PearlView", e); }
            }
            if (human >= 0 && human < n)
            {
                try { pearls[human]?.Tick(ctx, chased); }
                catch (Exception e) { Report("PearlView", e); }
            }
            try { ringView?.Tick(ctx, pearls); }
            catch (Exception e) { Report("RingView", e); }
            try { chargeRing?.Tick(ctx, pearls); }
            catch (Exception e) { Report("ChargeRing", e); }
            try { traitFx?.Tick(ctx, pearls); }
            catch (Exception e) { Report("TraitFxView", e); }
            for (int i = 0; i < n; i++)
            {
                try { retractions[i]?.DrawGlint(ctx); }
                catch (Exception e) { Report("RetractionView.Glint", e); }
            }
            try { cutFlash?.Tick(ctx); }
            catch (Exception e) { Report("CutFlash", e); }
            try { homeArrow?.Tick(ctx, pearls); }
            catch (Exception e) { Report("HomeArrow", e); }
            try { splash?.Tick(ctx); }
            catch (Exception e) { Report("SplashView", e); }
            try { sparkEdge?.Tick(ctx, retractions); }
            catch (Exception e) { Report("SparkEdgeIndicator", e); }
            try { ringIndicator?.Tick(ctx); }
            catch (Exception e) { Report("RingIndicator", e); }
            if (ActorGallery.Enabled)
            {
                try { ActorGallery.Draw(ctx); }
                catch (Exception e) { Report("ActorGallery", e); }
            }

            try
            {
                ctx.Pearls?.End();
                ctx.Overlays?.End();
                ctx.Indicators?.End();
            }
            catch (Exception e) { Report("batches", e); }
            if (TraitFxShots.Enabled) TraitFxShots.Tick(ctx.Time);
        }

        private void PrepareContext(GameSession s)
        {
            ctx.Director = director;
            ctx.Session = s;
            ctx.Sim = s.Sim;
            float realDt = Mathf.Max(0f, UnityEngine.Time.unscaledDeltaTime);
            ctx.RealDt = realDt;
            ctx.RealTime += realDt;
            float scale = s.Runner.Paused ? 0f : Mathf.Max(0f, s.Runner.TimeScale);
            ctx.Dt = Mathf.Min(realDt, 0.1f) * scale;
            ctx.Time += ctx.Dt;
            Vector4 quality = Shader.GetGlobalVector(QualityId);
            ctx.Lobes = quality.x > 1.5f ? 2f : 1f;

            CameraRig rig = CameraRig.Current;
            float viewScale = rig != null ? rig.ViewScale : 1f;
            ctx.ViewScale = viewScale > 0.05f && viewScale < 20f ? viewScale : 1f;

            Camera cam = ctx.Camera;
            if (cam == null || !cam.isActiveAndEnabled) cam = Camera.main;
            ctx.Camera = cam;
            if (cam != null)
            {
                float halfH = cam.orthographicSize;
                float halfW = halfH * cam.aspect;
                Vector3 c = cam.transform.position;
                ctx.ViewRect = new Rect(c.x - halfW, c.y - halfH, 2f * halfW, 2f * halfH);
                Rect px = cam.pixelRect;
                ctx.PixelsPerUnit = halfH > 1e-4f ? px.height / (2f * halfH) : 30f;
                ctx.UiScale = Mathf.Max(0.2f, Mathf.Min(px.height, px.width * 16f / 9f) / 1920f);
                Rect safe = Screen.safeArea;
                float xMin = Mathf.Max(px.xMin, safe.xMin), xMax = Mathf.Min(px.xMax, safe.xMax);
                float yMin = Mathf.Max(px.yMin, safe.yMin), yMax = Mathf.Min(px.yMax, safe.yMax);
                if (xMax - xMin < 32f || yMax - yMin < 32f)
                {
                    xMin = px.xMin;
                    xMax = px.xMax;
                    yMin = px.yMin;
                    yMax = px.yMax;
                }
                float side = 64f * ctx.UiScale, bottom = 80f * ctx.UiScale, top = 230f * ctx.UiScale;
                ctx.IndicatorRect = Rect.MinMaxRect(xMin + side, yMin + bottom, Mathf.Max(xMin + side + 1f, xMax - side),
                                                    Mathf.Max(yMin + bottom + 1f, yMax - top));
            }
        }

        private void HideAll()
        {
            if (hidden) return;
            hidden = true;
            foreach (ThreadView t in threads) t?.Hide();
            foreach (PearlView p in pearls) p?.Hide();
            foreach (RetractionView r in retractions) r?.Hide();
            splash?.Hide();
            traitFx?.Hide();
            ctx.Pearls?.Hide();
            ctx.Overlays?.Hide();
            ctx.Indicators?.Hide();
            sparkEdge?.Reset();
        }

        private void Report(string view, Exception e)
        {
            if (failed.Add(view)) Debug.LogError("[PainterIO] ActorViews " + view + " failed: " + e);
        }

        private void Guard(string view, Action action)
        {
            try
            {
                action();
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] ActorViews " + view + " failed: " + e);
            }
        }
    }
}
