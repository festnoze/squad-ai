// Owned by BI since wave B-2 (written by B1). Contract 12.2 item 1 (territory field), 12.3 (fill wave on return,
// evaporation on elimination, pending pockets) and 25.2 (per-biome FillDuration, reveal times for moving fronts).
//
// CPU side: a VisualMask (grid-sized RGBA32 linear texture, channel c = player c owns the cell, 255 / 0) that follows the
// sim grid with a visual lag: captured cells appear over FillDuration in order of distance from the return point (cells
// taken from a rival leave it when the wave reaches them), an eliminated player's channel fades out through
// _PIO_PlayerFade over EvaporationSeconds and is then cleared. Every grid change comes with a Return (captured cells) or
// an Eliminated event; a reconciliation pass after each grid change repairs anything else. The pocket mask follows
// PlayerState.Pocket (CellMask.Version driven).
//
// GPU side, only when the VisualMask changed: TerritoryBlur passes in one CommandBuffer executed with
// Graphics.ExecuteCommandBuffer, each limited with EnableScissorRect to the dirty rectangle (changed cells grown by
// 4 sigma + 2 cells); the full-texture path runs only when a session is bound or a render texture was lost:
//   mask -(blur x)-> ping A -(blur y)-> ping B -(B-spline x2)-> _PIO_TerritoryField (contour and color, sigma 0.16 u)
//   ping B -(wide x)-> ping A -(wide y)-> ping C -(B-spline x2, height)-> _PIO_TerritoryHeight (relief, sigma 0.26 u)
//   mask -(dome x, 2 x 2 box down)-> dome H -(dome y)-> dome V -(B-spline x2, gradient)-> _PIO_TerritoryDome
//   (wave D liq-drop, contract 28 F2: the domed body of the liquid, sigma 0.8 u on a half-size grid, with its own
//   render textures and its own wider scissor rectangle; the first six passes and their textures are unchanged).
//
// The visual clock is the render time of the sim, Time - (1 - Alpha) * Dt (the instant RenderPos shows), so pausing or
// slowing the runner pauses or slows the waves, and a screenshot at a given tick always shows the same fill.
//
// Reveal times (contract 25.2): _PIO_RevealTime is a grid-sized RHalf world texture (over _PIO_ArenaRect, like the
// masks) holding, per cell, the visual clock time at which the cell was last revealed or changed owner visually (a fill
// wave cell gets its exact scheduled time), and -1000 for cells present when the session was bound. _PIO_Now is the same
// clock now, so a composite draws a moving front where _PIO_Now - reveal is small (liquid ripple, fire front, electric
// crackle). Both share a rolling epoch (rebased every RevealRebaseSeconds) so half precision stays finer than 1/60 s:
// only the difference _PIO_Now - reveal is meaningful. The fill of a capture lasts BiomeTheme.Current.FillDuration
// (taken when the wave starts).
//
// Biome traits (wave D-2 traits-fx, docs/BIOME_TRAITS.md sections 5 and 7.2; generic, never tests the biome):
// - TerritoryGrew (Propagation): the grown ring is revealed like a slow fill from the territory edge, in GrowSteps
//   angular steps over GrowSeconds (the edge creeps around each territory, a few re-blurs instead of one per frame), with
//   reveal times, and the per-player envelope _PIO_GrowPulse drives each composite's soft edge accent. A one-cell ring
//   never triggers a composite's capture front (its gates read cells deeper inside), so growth never looks like a capture.
// - TerritoryInherited (KillInheritance): the victim's land first starts its own evaporation (the Eliminated event), then
//   after InheritDelaySeconds a fill wave in the killer's color sweeps over it from the kill point at InheritSweepSpeed,
//   so every biome's own capture front (fire flames, electric discharge, liquid ripple) crosses the land it takes.
// - ScorchedEarth: the scorch level of each freed cell (SimView.ScorchEndTime) is the G channel of _PIO_RevealTime (an RG
//   texture): it fades in with the evaporation of the eliminated land, holds, fades out over the last ScorchFadeSeconds and
//   leaves a cell when a capture wave reveals it. _PIO_ScorchOn is 1 while any cell is scorched.
using System;
using System.Collections.Generic;
using PainterIO.Core;
using Unity.Collections;
using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;

namespace PainterIO.Runtime
{
    public sealed class TerritoryField : IDisposable
    {
        /// <summary>Seconds a capture takes to fill in (contract 12.3); the HUD counts up over the same time.</summary>
        public const float FillDuration = 0.35f;
        /// <summary>Seconds an eliminated player's puddle takes to evaporate (contract 12.3).</summary>
        public const float EvaporationSeconds = 0.6f;
        /// <summary>Gaussian sigma of the territory blur, in mask texels (cells): 0.16 u.</summary>
        public const float BlurSigmaCells = 1.28f;
        /// <summary>Gaussian sigma of the second (relief) blur applied after the first one, in cells.</summary>
        public const float WideSigmaCells = 1.6f;
        /// <summary>Dirty rectangle growth: ceil(4 sigma) + 2 cells with the total relief sigma sqrt(1.28^2 + 1.6^2) = 2.05.</summary>
        public const int DirtyGrowCells = 11;
        /// <summary>Upsampling factor of the field and height textures (512 mask -> 1024 field).</summary>
        public const int FieldScale = 2;
        /// <summary>Reveal value of cells present at bind time (and of reveals older than RevealForgetSeconds after a rebase).</summary>
        public const float RevealNever = -1000f;
        /// <summary>The reveal epoch moves to now when the clock is this far from it (keeps half precision under 1/64 s).</summary>
        public const double RevealRebaseSeconds = 16.0;
        /// <summary>On a rebase, reveals older than this become RevealNever.</summary>
        public const float RevealForgetSeconds = 30f;
        /// <summary>Gaussian sigma of the dome field (wave D F2), world units (3.2 texels of the half-size dome grid).</summary>
        public const float DomeSigmaUnits = 0.8f;
        /// <summary>Downsampling of the dome blur grid against the mask (512 cells -> 256 dome texels).</summary>
        public const int DomeDownscale = 2;
        /// <summary>
        /// Dirty rectangle growth of the dome passes, in cells: the 21-tap Gaussian reaches 20 cells, the 2 x 2 box 1,
        /// the B-spline reconstruction 4, the shadow sample 3 (0.32 u), plus a margin.
        /// </summary>
        public const int DomeGrowCells = 32;

        /// <summary>Wave D-2: seconds a Propagation ring takes to creep around a territory (well below the 4 s interval).</summary>
        public const float GrowSeconds = 1.2f;
        /// <summary>Wave D-2: angular steps of that creep (one territory re-blur per step).</summary>
        public const int GrowSteps = 6;
        /// <summary>Wave D-2: rise and total length of the _PIO_GrowPulse envelope (seconds).</summary>
        public const float GrowPulseRise = 0.15f;
        public const float GrowPulseSeconds = 1.4f;
        /// <summary>Wave D-2: grown cells for a full-strength _PIO_GrowPulse (fewer cells give a weaker accent).</summary>
        public const int GrowPulseFullCells = 48;
        /// <summary>Wave D-2: seconds between the kill and the start of the killer's sweep over the inherited land.</summary>
        public const float InheritDelaySeconds = 0.25f;
        /// <summary>Wave D-2: speed (u/s) of the inherited sweep, and the bounds of its duration (seconds).</summary>
        public const float InheritSweepSpeed = 15f;
        public const float InheritMinSeconds = 0.45f;
        public const float InheritMaxSeconds = 1.5f;
        /// <summary>Wave D-2: a scorched cell fades out over the last ScorchFadeSeconds of its scorch (BIOME_TRAITS 5).</summary>
        public const float ScorchFadeSeconds = 2f;
        /// <summary>Wave D-2: the scorch fades in over this time after the elimination (with the evaporation of the land).</summary>
        public const float ScorchFadeInSeconds = 0.6f;
        /// <summary>Wave D-2: the scorch levels are refreshed at most this often (seconds of visual time).</summary>
        public const float ScorchRefreshSeconds = 1f / 30f;

        /// <summary>FillDuration of the current biome (Liquid 0.35, Fire 0.60, Electric 0.25 s).</summary>
        public static float CurrentFillDuration
        {
            get
            {
                float d = BiomeTheme.Current.FillDuration;
                return d > 0.01f ? d : FillDuration;
            }
        }

        private const int PassBlurH = 0;
        private const int PassBlurV = 1;
        private const int PassUpsample = 2;
        private const int PassHeight = 3;
        private const int PassWideH = 4;
        private const int PassWideV = 5;
        private const int PassDomeH = 6;
        private const int PassDomeV = 7;
        private const int PassDomeField = 8;

        private static readonly int IdField = Shader.PropertyToID("_PIO_TerritoryField");
        private static readonly int IdHeight = Shader.PropertyToID("_PIO_TerritoryHeight");
        private static readonly int IdTexel = Shader.PropertyToID("_PIO_TerritoryTexel");
        private static readonly int IdArenaRect = Shader.PropertyToID("_PIO_ArenaRect");
        private static readonly int IdUnorm = Shader.PropertyToID("_PIO_TerritoryUnorm");
        private static readonly int IdBlurSource = Shader.PropertyToID("_PIO_BlurSource");
        private static readonly int IdBlurTexel = Shader.PropertyToID("_PIO_BlurTexel");
        private static readonly int IdPocket = Shader.PropertyToID("_PIO_PocketMask");
        private static readonly int IdPocketTexel = Shader.PropertyToID("_PIO_PocketTexel");
        private static readonly int IdFade = Shader.PropertyToID("_PIO_PlayerFade");
        private static readonly int IdReveal = Shader.PropertyToID("_PIO_RevealTime");
        private static readonly int IdRevealTexel = Shader.PropertyToID("_PIO_RevealTexel");
        private static readonly int IdNow = Shader.PropertyToID("_PIO_Now");
        private static readonly int IdDome = Shader.PropertyToID("_PIO_TerritoryDome");
        private static readonly int IdDomeTexel = Shader.PropertyToID("_PIO_TerritoryDomeTexel");
        private static readonly int IdScorchOn = Shader.PropertyToID("_PIO_ScorchOn");
        private static readonly int IdGrowPulse = Shader.PropertyToID("_PIO_GrowPulse");

        private sealed class Wave
        {
            public int Id;
            public byte Owner;
            public int[] Cells;
            public double[] Times;
            public int Next;
        }

        private readonly Material blurMaterial;
        private readonly CommandBuffer cmd = new CommandBuffer { name = "PIO TerritoryField" };
        private readonly List<Wave> waves = new List<Wave>();
        private readonly List<int>[] pocketCells = new List<int>[4];
        private readonly CellMask[] pocketRef = new CellMask[4];
        private readonly int[] pocketVersion = new int[4];
        private readonly int[] pocketCount = new int[4];
        private readonly float[] fade = { 1f, 1f, 1f, 1f };
        private readonly double[] fadeStart = { double.NaN, double.NaN, double.NaN, double.NaN };
        private readonly List<int> scratch = new List<int>();

        private int size;                    // grid (mask) size in cells
        private Texture2D visualMask;
        private Texture2D pocketMask;
        private Texture2D revealTex;
        private bool revealHalf;             // R16G16_SFloat (else R32G32_SFloat); R = reveal time, G = scorch level
        private float[] reveal;              // CPU copy of the reveal times (relative to revealEpoch)
        private NativeArray<ushort> revealPxHalf;   // two halves per texel
        private NativeArray<float> revealPxFloat;   // two floats per texel

        // Wave D-2 traits (allocated on first use: classic rounds never touch them).
        private float[] scorchLevel;         // CPU copy of the G channel
        private double[] scorchEnd;          // sim time the cell's scorch ends (SimView.ScorchEndTime)
        private double[] scorchStart;        // sim time of the elimination that scorched it (fade in)
        private readonly List<int> scorchCells = new List<int>();
        private double scorchRefreshedAt = double.NegativeInfinity;
        private bool scorchActive;
        private readonly double[] growStart = { double.NaN, double.NaN, double.NaN, double.NaN };
        private readonly float[] growAmp = new float[4];
        private double revealEpoch;
        private float revealStamp;           // the current reveal time (relative), used by SetVisual outside the waves
        private bool revealDirty;
        private NativeArray<Color32> maskPx, pocketPx;
        private RenderTexture pingA, pingB, pingC, field, height;
        private RenderTexture domeH, domeV, dome;   // wave D: dome grid after x, after y, and _PIO_TerritoryDome
        private GraphicsFormat fieldFormat;
        private bool unorm;
        private byte[] visual;               // displayed owner per cell (0 neutral, 1..4 players)
        private int[] cellWave;              // id of the latest wave that will reveal the cell, 0 when none
        private int nextWaveId = 1;

        // Rule v1.6 (contract 30): the last inherited sweep, so the bridge band of the same kill joins it (one sweep).
        private Wave inheritWave;
        private int[] inheritCells;
        private Vec2d inheritOrigin;
        private double inheritTime;

        private GameSession session;
        private Simulation sim;
        private double endedExtra;
        private int reconciledVersion = -1;
        private bool reconcileRequested;
        private bool mismatchLogged;
        private bool maskDirty, fullRebuild, pocketDirty;
        private int dirtyX0, dirtyY0, dirtyX1, dirtyY1;
        private bool disposed;

        public TerritoryField(Shader blurShader)
        {
            if (blurShader == null) throw new ArgumentNullException(nameof(blurShader), "TerritoryBlur shader missing");
            if (!blurShader.isSupported) Debug.LogError("[PainterIO] TerritoryBlur shader is not supported on this device");
            blurMaterial = new Material(blurShader) { name = "PIO TerritoryBlur", hideFlags = HideFlags.HideAndDontSave };
            for (int p = 0; p < 4; p++) pocketCells[p] = new List<int>();
            fieldFormat = SystemInfo.IsFormatSupported(GraphicsFormat.R16G16B16A16_SFloat, GraphicsFormatUsage.Render)
                ? GraphicsFormat.R16G16B16A16_SFloat
                : GraphicsFormat.R8G8B8A8_UNorm;
            unorm = fieldFormat == GraphicsFormat.R8G8B8A8_UNorm;
            Allocate(Mathf.RoundToInt((float)(2.0 * Tuning.ArenaHalfSize / Tuning.CellSize)));
            ClearAll();
            Publish();
        }

        /// <summary>The bound session (null before the first SessionStarted).</summary>
        public GameSession Session => session;

        /// <summary>Mask and grid size in cells (512 with the default tuning).</summary>
        public int Size => size;

        /// <summary>The CPU-side visual mask (RGBA32 linear, channel per player).</summary>
        public Texture2D VisualMask => visualMask;

        /// <summary>The pocket mask (RGBA32 linear, channel per player).</summary>
        public Texture2D PocketMask => pocketMask;

        /// <summary>_PIO_TerritoryField (t_i per channel).</summary>
        public RenderTexture Field => field;

        /// <summary>_PIO_TerritoryHeight (H_T, dH/dx, dH/dy, max t).</summary>
        public RenderTexture Height => height;

        /// <summary>
        /// _PIO_TerritoryDome (wave D): mask-sized (t_dome = max over the channels, dt_dome/dx, dt_dome/dy per world unit,
        /// t_dome at PIO_DOME_SHADOW_REACH toward the key light), in the field format.
        /// </summary>
        public RenderTexture Dome => dome;

        /// <summary>Format of the field and height textures (R16G16B16A16_SFloat, or R8G8B8A8_UNorm as fallback).</summary>
        public GraphicsFormat FieldFormat => fieldFormat;

        /// <summary>Current per-channel fade (_PIO_PlayerFade).</summary>
        public Vector4 PlayerFade => new Vector4(fade[0], fade[1], fade[2], fade[3]);

        /// <summary>Number of fill waves still running.</summary>
        public int ActiveWaves => waves.Count;

        /// <summary>Times the GPU passes ran (full or scissored), for tests and the probe.</summary>
        public int PassRuns { get; private set; }

        /// <summary>
        /// The _PIO_RevealTime texture (grid-sized, R16G16_SFloat or R32G32_SFloat): R = reveal time, G = scorch level
        /// (wave D-2).
        /// </summary>
        public Texture2D RevealTexture => revealTex;

        /// <summary>Wave D-2: the scorch level of a cell as uploaded (0 = none, 1 = fully scorched).</summary>
        public float ScorchOf(int cellIndex)
        {
            return scorchLevel != null && cellIndex >= 0 && cellIndex < scorchLevel.Length ? scorchLevel[cellIndex] : 0f;
        }

        /// <summary>Wave D-2: true while at least one cell shows a scorch (_PIO_ScorchOn).</summary>
        public bool ScorchActive => scorchActive;

        /// <summary>Wave D-2: cells whose scorch is still tracked (showing or about to show).</summary>
        public int ScorchTracked => scorchCells.Count;

        /// <summary>Wave D-2: the _PIO_GrowPulse envelopes (per player channel) at the current visual time.</summary>
        public Vector4 GrowPulse
        {
            get
            {
                double now = VisualTime();
                return new Vector4(GrowEnvelope(0, now), GrowEnvelope(1, now), GrowEnvelope(2, now), GrowEnvelope(3, now));
            }
        }

        /// <summary>
        /// The reveal time of a cell relative to the current epoch (RevealNever for cells present at bind time); compare it
        /// with RevealNow, as the shaders do with _PIO_Now.
        /// </summary>
        public float RevealTimeOf(int cellIndex)
        {
            return reveal != null && cellIndex >= 0 && cellIndex < reveal.Length ? reveal[cellIndex] : RevealNever;
        }

        /// <summary>_PIO_Now: the visual clock relative to the reveal epoch.</summary>
        public float RevealNow => (float)(VisualTime() - revealEpoch);

        /// <summary>Cells the last reconciliation had to repair (0 when the event-driven state was right).</summary>
        public int LastReconcileFixes { get; private set; }

        /// <summary>The displayed owner of a cell (0 neutral, 1..4 = player index + 1).</summary>
        public byte VisualOwner(int cellIndex)
        {
            return visual != null && cellIndex >= 0 && cellIndex < visual.Length ? visual[cellIndex] : (byte)0;
        }

        /// <summary>The render time of the bound sim, the clock of the fill waves and of the evaporation.</summary>
        public double VisualTime()
        {
            if (session == null || sim == null) return 0.0;
            if (sim.Ended) return sim.Time + endedExtra;
            return sim.Time - (1.0 - session.Alpha) * sim.Config.Dt;
        }

        /// <summary>Binds a session (also on attract restarts): full rebuild of the masks and of the field.</summary>
        public void Bind(GameSession s)
        {
            if (disposed) return;
            session = s;
            sim = s != null ? s.Sim : null;
            endedExtra = 0.0;
            waves.Clear();
            inheritWave = null;
            inheritCells = null;
            for (int p = 0; p < 4; p++)
            {
                fade[p] = 1f;
                fadeStart[p] = double.NaN;
                growStart[p] = double.NaN;
                growAmp[p] = 0f;
            }
            mismatchLogged = false;
            LastReconcileFixes = 0;
            ClearTraitState();
            if (sim == null)
            {
                ClearAll();
                return;
            }
            OwnerGrid g = sim.Grid;
            if (g.Size != size) Allocate(g.Size);
            Array.Clear(cellWave, 0, cellWave.Length);
            byte[] cells = g.Cells;
            AcquirePixels();
            NativeArray<Color32> px = maskPx;
            for (int c = 0; c < visual.Length; c++)
            {
                byte o = cells[c];
                if (o == OwnerGrid.Void || o > 4) o = 0;
                visual[c] = o;
                px[c] = ChannelColor(o);
            }
            reconciledVersion = g.Version;
            reconcileRequested = false;
            ClearPockets();
            ResetReveal();
            maskDirty = true;
            fullRebuild = true;
        }

        /// <summary>Forwarded sim events (Return with cells starts a fill wave, Eliminated starts the evaporation).</summary>
        public void OnSimEvent(SimEvent e)
        {
            if (disposed || sim == null || e == null) return;
            revealStamp = (float)(VisualTime() - revealEpoch);
            switch (e.Type)
            {
                case SimEventType.Return:
                    if (e.Cells != null && e.Cells.Length > 0) AddWave(e.Player, e.Point, e.Cells, e.Time, CurrentFillDuration, false);
                    break;
                case SimEventType.Eliminated:
                    StartEvaporation(e.Player, e.Time);
                    if (e.Cells != null && e.Cells.Length > 0) TrackScorch(e.Cells, e.Time);
                    break;
                case SimEventType.TerritoryGrew:
                    if (e.Cells != null && e.Cells.Length > 0) AddGrowth(e.Player, e.Cells, e.Time);
                    break;
                case SimEventType.TerritoryInherited:
                    if (e.Cells != null && e.Cells.Length > 0)
                    {
                        inheritWave = AddWave(e.Player, e.Point, e.Cells, e.Time + InheritDelaySeconds, -1.0, true);
                        inheritCells = e.Cells;
                        inheritOrigin = e.Point;
                        inheritTime = e.Time;
                    }
                    break;
                case SimEventType.InheritanceBridged:
                    if (e.Cells != null && e.Cells.Length > 0) AddBridge(e);
                    break;
                case SimEventType.TerritorySevered:
                    if (e.Cells != null) DropFromWaves(e.Player, e.Cells);
                    break;
            }
        }

        // Rule v1.6 (contract 30): the band that joins the inherited land to the killer's domain sweeps with that land, as one
        // wave from the kill point (the band starts near it, so the sweep runs along the kill line into the inherited land).
        // Without a pending inherited sweep of the same kill, the band sweeps alone from the kill point.
        private void AddBridge(SimEvent e)
        {
            Wave pending = inheritWave;
            if (pending != null && inheritCells != null && inheritTime == e.Time && pending.Owner == e.Player + 1
                && pending.Next == 0 && waves.Remove(pending))
            {
                var union = new int[inheritCells.Length + e.Cells.Length];
                Array.Copy(inheritCells, union, inheritCells.Length);
                Array.Copy(e.Cells, 0, union, inheritCells.Length, e.Cells.Length);
                inheritWave = AddWave(e.Player, inheritOrigin, union, e.Time + InheritDelaySeconds, -1.0, true);
                return;
            }
            AddWave(e.Player, e.Point, e.Cells, e.Time + InheritDelaySeconds, -1.0, true);
        }

        // Rule v1.5 / v1.6 (TerritorySevered): severed cells left their player; a pending wave of that player must not paint
        // them (they evaporate with the land they came from, or snap at the next reconciliation).
        private void DropFromWaves(int player, int[] cells)
        {
            if (player < 0 || player >= 4 || waves.Count == 0) return;
            byte owner = (byte)(player + 1);
            for (int w = 0; w < waves.Count; w++)
            {
                Wave wave = waves[w];
                if (wave.Owner != owner) continue;
                for (int k = 0; k < cells.Length; k++)
                {
                    int c = cells[k];
                    if (c >= 0 && c < cellWave.Length && cellWave[c] == wave.Id) cellWave[c] = 0;
                }
            }
            reconcileRequested = true;
        }

        /// <summary>Per frame (LiquidRenderer.LateUpdate): waves, evaporation, reconciliation, pockets, uploads, passes.</summary>
        public void Update(float unscaledDeltaTime)
        {
            if (disposed) return;
            if (RenderTexturesLost())
            {
                AllocateTargets();
                fullRebuild = true;
                maskDirty = true;
            }
            AcquirePixels();
            if (sim != null && session != null && session.Sim != sim) Bind(session);   // attract restart missed
            if (sim != null)
            {
                if (sim.Ended) endedExtra += Mathf.Max(0f, unscaledDeltaTime);
                double now = VisualTime();
                if (now - revealEpoch > RevealRebaseSeconds) RebaseReveal(now);
                revealStamp = (float)(now - revealEpoch);
                AdvanceWaves(now);
                AdvanceEvaporation(now);
                if (sim.Grid.Version != reconciledVersion || reconcileRequested) Reconcile();
                UpdatePockets();
                if (scorchCells.Count > 0 || scorchActive) UpdateScorch(now);
            }
            if (maskDirty)
            {
                visualMask.Apply(false, false);
                RunPasses(fullRebuild);
                maskDirty = false;
                fullRebuild = false;
            }
            if (pocketDirty)
            {
                pocketMask.Apply(false, false);
                pocketDirty = false;
            }
            if (revealDirty && revealTex != null)
            {
                revealTex.Apply(false, false);
                revealDirty = false;
            }
            Publish();
        }

        public void Dispose()
        {
            if (disposed) return;
            disposed = true;
            session = null;
            sim = null;
            cmd.Release();
            ReleaseTargets();
            DestroyObject(visualMask);
            DestroyObject(pocketMask);
            DestroyObject(revealTex);
            DestroyObject(blurMaterial);
            visualMask = null;
            pocketMask = null;
            revealTex = null;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Fill waves and evaporation.

        // A fill wave: cells appear in order of distance from the origin. A capture (sweep false) lasts `fill` seconds, the
        // farthest cell last (contract 12.3). The inherited sweep of wave D-2 (sweep true) starts at the cell nearest to
        // the origin (the kill point is usually outside the victim's land) and moves at InheritSweepSpeed, its duration
        // clamped to [InheritMinSeconds, InheritMaxSeconds].
        private Wave AddWave(int player, Vec2d origin, int[] cells, double startTime, double fill, bool sweep)
        {
            if (player < 0 || player >= 4) return null;
            OwnerGrid g = sim.Grid;
            int n = cells.Length;
            var keys = new double[n];
            var items = new int[n];
            double cs = g.CellSize, org = g.Origin;
            double dMax = 0.0, dMin = double.MaxValue;
            for (int k = 0; k < n; k++)
            {
                int c = cells[k];
                int i = c % size, j = c / size;
                double dx = org + (i + 0.5) * cs - origin.X;
                double dy = org + (j + 0.5) * cs - origin.Y;
                double d = Math.Sqrt(dx * dx + dy * dy);
                keys[k] = d;
                items[k] = c;
                if (d > dMax) dMax = d;
                if (d < dMin) dMin = d;
            }
            Array.Sort(keys, items);
            double d0 = 0.0;
            if (sweep)
            {
                d0 = dMin;
                fill = Math.Min(InheritMaxSeconds, Math.Max(InheritMinSeconds, (dMax - dMin) / InheritSweepSpeed));
            }
            double span = dMax - d0;
            var wave = new Wave { Id = nextWaveId++, Owner = (byte)(player + 1), Cells = items, Times = keys };
            if (nextWaveId == int.MaxValue) nextWaveId = 1;
            for (int k = 0; k < n; k++)
            {
                keys[k] = startTime + (span > 1e-9 ? fill * (keys[k] - d0) / span : 0.0);
                int c = items[k];
                if (c >= 0 && c < cellWave.Length) cellWave[c] = wave.Id;
            }
            waves.Add(wave);
            return wave;
        }

        // Wave D-2 (TerritoryGrew): the grown cells creep around the territory in GrowSteps angular steps over GrowSeconds,
        // starting at an angle that differs per player, around the centroid of the grown cells. Rings > 1 creep together.
        private void AddGrowth(int player, int[] cells, double startTime)
        {
            if (player < 0 || player >= 4) return;
            int n = cells.Length;
            double cx = 0.0, cy = 0.0;
            for (int k = 0; k < n; k++)
            {
                cx += cells[k] % size;
                cy += cells[k] / size;
            }
            cx /= n;
            cy /= n;
            double start = 1.9 + 2.4 * player;
            var keys = new double[n];
            var items = new int[n];
            for (int k = 0; k < n; k++)
            {
                int c = cells[k];
                double a = Math.Atan2(c / size - cy, c % size - cx) - start;
                a -= 2.0 * Math.PI * Math.Floor(a / (2.0 * Math.PI));
                int step = Math.Min(GrowSteps - 1, (int)(a / (2.0 * Math.PI) * GrowSteps));
                keys[k] = startTime + step * (GrowSeconds / GrowSteps);
                items[k] = c;
            }
            Array.Sort(keys, items);
            var wave = new Wave { Id = nextWaveId++, Owner = (byte)(player + 1), Cells = items, Times = keys };
            if (nextWaveId == int.MaxValue) nextWaveId = 1;
            for (int k = 0; k < n; k++)
            {
                int c = items[k];
                if (c >= 0 && c < cellWave.Length) cellWave[c] = wave.Id;
            }
            waves.Add(wave);
            growStart[player] = startTime;
            growAmp[player] = Mathf.Clamp01(n / (float)GrowPulseFullCells);
        }

        // _PIO_GrowPulse of one player: rises over GrowPulseRise, then a smooth decay to 0 at GrowPulseSeconds.
        private float GrowEnvelope(int p, double now)
        {
            double t0 = growStart[p];
            if (double.IsNaN(t0) || sim == null || p >= sim.Players.Count || !sim.Players[p].Alive) return 0f;
            float t = (float)(now - t0);
            if (t <= 0f || t >= GrowPulseSeconds) return 0f;
            float rise = Mathf.SmoothStep(0f, 1f, t / GrowPulseRise);
            float fall = 1f - Mathf.SmoothStep(0f, 1f, (t - GrowPulseRise) / (GrowPulseSeconds - GrowPulseRise));
            return growAmp[p] * rise * fall;
        }

        private void AdvanceWaves(double now)
        {
            for (int w = waves.Count - 1; w >= 0; w--)
            {
                Wave wave = waves[w];
                while (wave.Next < wave.Cells.Length && wave.Times[wave.Next] <= now)
                {
                    int c = wave.Cells[wave.Next++];
                    if (c < 0 || c >= cellWave.Length || cellWave[c] != wave.Id) continue;   // a later wave owns it
                    cellWave[c] = 0;
                    SetVisual(c, wave.Owner, (float)(wave.Times[wave.Next - 1] - revealEpoch));
                }
                if (wave.Next >= wave.Cells.Length)
                {
                    waves.RemoveAt(w);
                    reconcileRequested = true;
                }
            }
        }

        private void StartEvaporation(int player, double time)
        {
            if (player < 0 || player >= 4) return;
            byte id = (byte)(player + 1);
            // Cells still waiting in this player's waves show its color at once and evaporate with it.
            for (int w = waves.Count - 1; w >= 0; w--)
            {
                Wave wave = waves[w];
                if (wave.Owner != id) continue;
                for (int k = wave.Next; k < wave.Cells.Length; k++)
                {
                    int c = wave.Cells[k];
                    if (c < 0 || c >= cellWave.Length || cellWave[c] != wave.Id) continue;
                    cellWave[c] = 0;
                    SetVisual(c, id);
                }
                waves.RemoveAt(w);
            }
            if (double.IsNaN(fadeStart[player])) fadeStart[player] = time;
        }

        private void AdvanceEvaporation(double now)
        {
            for (int p = 0; p < 4; p++)
            {
                if (double.IsNaN(fadeStart[p])) continue;
                double k = (now - fadeStart[p]) / EvaporationSeconds;
                if (k < 1.0)
                {
                    fade[p] = Mathf.Clamp01((float)(1.0 - k));
                    continue;
                }
                byte id = (byte)(p + 1);
                for (int c = 0; c < visual.Length; c++)
                {
                    if (visual[c] == id) SetVisual(c, 0);
                }
                fade[p] = 1f;
                fadeStart[p] = double.NaN;
                reconcileRequested = true;
            }
        }

        private void Reconcile()
        {
            reconcileRequested = false;
            OwnerGrid g = sim.Grid;
            reconciledVersion = g.Version;
            byte[] cells = g.Cells;
            int fixes = 0;
            for (int c = 0; c < visual.Length; c++)
            {
                if (cellWave[c] != 0) continue;
                byte v = visual[c];
                if (v != 0 && !double.IsNaN(fadeStart[v - 1])) continue;
                byte o = cells[c];
                if (o == OwnerGrid.Void || o > 4) o = 0;
                if (o == v) continue;
                SetVisual(c, o);
                fixes++;
            }
            LastReconcileFixes = fixes;
            if (fixes > 0 && !mismatchLogged)
            {
                mismatchLogged = true;
                Debug.Log("[PainterIO] TerritoryField reconciled " + fixes + " cell(s) with the grid");
            }
        }

        private void SetVisual(int c, byte owner)
        {
            SetVisual(c, owner, revealStamp);
        }

        private void SetVisual(int c, byte owner, float revealTime)
        {
            if (visual[c] == owner) return;
            visual[c] = owner;
            maskPx[c] = ChannelColor(owner);
            WriteReveal(c, revealTime);
            MarkDirty(c % size, c / size);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Reveal times (contract 25.2).

        private void WriteReveal(int c, float value)
        {
            if (reveal == null || c < 0 || c >= reveal.Length) return;
            reveal[c] = value;
            if (revealHalf) revealPxHalf[2 * c] = Mathf.FloatToHalf(value);
            else revealPxFloat[2 * c] = value;
            revealDirty = true;
        }

        // Wave D-2: the G channel of the reveal texture (scorch level).
        private void WriteScorch(int c, float level)
        {
            scorchLevel[c] = level;
            if (revealHalf) revealPxHalf[2 * c + 1] = Mathf.FloatToHalf(level);
            else revealPxFloat[2 * c + 1] = level;
            revealDirty = true;
        }

        private void ResetReveal()
        {
            revealEpoch = VisualTime();
            revealStamp = 0f;
            if (reveal == null) return;
            ushort never = Mathf.FloatToHalf(RevealNever);
            ushort zero = Mathf.FloatToHalf(0f);
            for (int c = 0; c < reveal.Length; c++)
            {
                reveal[c] = RevealNever;
                if (revealHalf)
                {
                    revealPxHalf[2 * c] = never;
                    revealPxHalf[2 * c + 1] = zero;
                }
                else
                {
                    revealPxFloat[2 * c] = RevealNever;
                    revealPxFloat[2 * c + 1] = 0f;
                }
            }
            if (scorchLevel != null) Array.Clear(scorchLevel, 0, scorchLevel.Length);
            revealDirty = true;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Wave D-2 traits: scorched ground (the G channel of the reveal texture).

        // Bind calls ResetReveal afterwards, which clears the G channel of every cell.
        private void ClearTraitState()
        {
            if (scorchEnd != null)
            {
                for (int k = 0; k < scorchCells.Count; k++) scorchEnd[scorchCells[k]] = 0.0;
            }
            scorchCells.Clear();
            scorchActive = false;
            scorchRefreshedAt = double.NegativeInfinity;
        }

        // Freed cells of an elimination: the ones ScorchedEarth marked (end time after the elimination) are tracked.
        private void TrackScorch(int[] freed, double time)
        {
            if (sim == null || reveal == null || !sim.Config.Traits.Has(TraitId.ScorchedEarth)) return;
            SimView view = sim.View;
            int count = reveal.Length;
            if (scorchLevel == null || scorchLevel.Length != count)
            {
                scorchLevel = new float[count];
                scorchEnd = new double[count];
                scorchStart = new double[count];
                scorchCells.Clear();
            }
            for (int k = 0; k < freed.Length; k++)
            {
                int c = freed[k];
                if (c < 0 || c >= count) continue;
                double end = view.ScorchEndTime(c);
                if (!(end > time)) continue;
                bool tracked = scorchEnd[c] > 0.0 || scorchLevel[c] > 0f;
                if (!tracked || end > scorchEnd[c])
                {
                    if (!tracked) scorchCells.Add(c);
                    scorchEnd[c] = Math.Max(end, 1e-9);
                    scorchStart[c] = time;
                }
            }
            scorchRefreshedAt = double.NegativeInfinity;
        }

        // Levels of the tracked cells at the visual clock: fade in with the evaporation, hold, fade out over the last
        // ScorchFadeSeconds; a cell leaves when its scorch ended, or when it was captured and its fill revealed it.
        private void UpdateScorch(double now)
        {
            if (scorchLevel == null)
            {
                scorchActive = false;
                return;
            }
            if (now - scorchRefreshedAt < ScorchRefreshSeconds && now >= scorchRefreshedAt) return;
            scorchRefreshedAt = now;
            byte[] cells = sim.Grid.Cells;
            bool any = false;
            for (int k = scorchCells.Count - 1; k >= 0; k--)
            {
                int c = scorchCells[k];
                byte o = cells[c];
                bool captured = o != 0 && o != OwnerGrid.Void && cellWave[c] == 0;
                double end = scorchEnd[c];
                float level = 0f;
                if (!captured && now < end)
                {
                    float fadeIn = Mathf.Clamp01((float)(now - scorchStart[c]) / ScorchFadeInSeconds);
                    float fadeOut = Mathf.Clamp01((float)(end - now) / ScorchFadeSeconds);
                    level = fadeIn * fadeIn * (3f - 2f * fadeIn) * fadeOut;
                }
                if (Mathf.Abs(level - scorchLevel[c]) > 0.5f / 255f || (level == 0f && scorchLevel[c] != 0f)) WriteScorch(c, level);
                if (level > 0f) any = true;
                if (captured || now >= end)
                {
                    if (scorchLevel[c] != 0f) WriteScorch(c, 0f);
                    scorchEnd[c] = 0.0;
                    scorchCells[k] = scorchCells[scorchCells.Count - 1];
                    scorchCells.RemoveAt(scorchCells.Count - 1);
                }
            }
            scorchActive = any;
        }

        // Moves the epoch to now; every stored time shifts by the same amount (reveals older than RevealForgetSeconds are
        // forgotten), so _PIO_Now - reveal is unchanged.
        private void RebaseReveal(double now)
        {
            float shift = (float)(now - revealEpoch);
            revealEpoch = now;
            if (reveal == null) return;
            for (int c = 0; c < reveal.Length; c++)
            {
                float v = reveal[c];
                if (v <= RevealNever + 1f) continue;
                v -= shift;
                if (v < -RevealForgetSeconds) v = RevealNever;
                reveal[c] = v;
                if (revealHalf) revealPxHalf[2 * c] = Mathf.FloatToHalf(v);
                else revealPxFloat[2 * c] = v;
            }
            revealDirty = true;
        }

        private void MarkDirty(int i, int j)
        {
            if (!maskDirty)
            {
                maskDirty = true;
                dirtyX0 = dirtyX1 = i;
                dirtyY0 = dirtyY1 = j;
                return;
            }
            if (i < dirtyX0) dirtyX0 = i;
            if (i > dirtyX1) dirtyX1 = i;
            if (j < dirtyY0) dirtyY0 = j;
            if (j > dirtyY1) dirtyY1 = j;
        }

        private static Color32 ChannelColor(byte owner)
        {
            switch (owner)
            {
                case 1: return new Color32(255, 0, 0, 0);
                case 2: return new Color32(0, 255, 0, 0);
                case 3: return new Color32(0, 0, 255, 0);
                case 4: return new Color32(0, 0, 0, 255);
                default: return new Color32(0, 0, 0, 0);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Pockets.

        private void UpdatePockets()
        {
            int n = Math.Min(4, sim.Players.Count);
            for (int p = 0; p < 4; p++)
            {
                CellMask m = p < n ? sim.Players[p].Pocket : null;
                int version = m != null ? m.Version : 0;
                int count = m != null ? m.Count : 0;
                if (m == pocketRef[p] && version == pocketVersion[p] && count == pocketCount[p]) continue;
                pocketRef[p] = m;
                pocketVersion[p] = version;
                pocketCount[p] = count;
                RebuildPocket(p, m);
            }
        }

        private void RebuildPocket(int p, CellMask m)
        {
            NativeArray<Color32> px = pocketPx;
            List<int> previous = pocketCells[p];
            for (int k = 0; k < previous.Count; k++)
            {
                int c = previous[k];
                Color32 v = px[c];
                SetChannel(ref v, p, 0);
                px[c] = v;
            }
            previous.Clear();
            if (m != null && m.Count > 0)
            {
                scratch.Clear();
                m.CopyIndices(scratch);
                for (int k = 0; k < scratch.Count; k++)
                {
                    int c = scratch[k];
                    if (c < 0 || c >= px.Length) continue;
                    Color32 v = px[c];
                    SetChannel(ref v, p, 255);
                    px[c] = v;
                    previous.Add(c);
                }
            }
            pocketDirty = true;
        }

        private static void SetChannel(ref Color32 v, int channel, byte value)
        {
            switch (channel)
            {
                case 0: v.r = value; break;
                case 1: v.g = value; break;
                case 2: v.b = value; break;
                default: v.a = value; break;
            }
        }

        private void ClearPockets()
        {
            NativeArray<Color32> px = pocketPx;
            var zero = new Color32(0, 0, 0, 0);
            for (int c = 0; c < px.Length; c++) px[c] = zero;
            for (int p = 0; p < 4; p++)
            {
                pocketCells[p].Clear();
                pocketRef[p] = null;
                pocketVersion[p] = -1;
                pocketCount[p] = -1;
            }
            pocketDirty = true;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Textures and GPU passes.

        private void Allocate(int gridSize)
        {
            size = Mathf.Max(8, gridSize);
            int cellCount = size * size;
            visual = new byte[cellCount];
            cellWave = new int[cellCount];
            DestroyObject(visualMask);
            DestroyObject(pocketMask);
            visualMask = NewMask("PIO VisualMask");
            pocketMask = NewMask("PIO PocketMask");
            DestroyObject(revealTex);
            // Wave D-2: RG (R = reveal time, G = scorch level), so the composites read the scorch with their reveal fetch.
            revealHalf = SystemInfo.IsFormatSupported(GraphicsFormat.R16G16_SFloat, GraphicsFormatUsage.Sample);
            revealTex = new Texture2D(size, size, revealHalf ? GraphicsFormat.R16G16_SFloat : GraphicsFormat.R32G32_SFloat, TextureCreationFlags.None)
            {
                name = "PIO RevealTime",
                filterMode = revealHalf ? FilterMode.Bilinear : FilterMode.Point,
                wrapMode = TextureWrapMode.Clamp,
                anisoLevel = 0,
                hideFlags = HideFlags.HideAndDontSave,
            };
            reveal = new float[cellCount];
            scorchLevel = null;
            scorchEnd = null;
            scorchStart = null;
            scorchCells.Clear();
            scorchActive = false;
            AcquirePixels();
            ResetReveal();
            AllocateTargets();
            for (int p = 0; p < 4; p++)
            {
                pocketCells[p].Clear();
                pocketRef[p] = null;
                pocketVersion[p] = -1;
                pocketCount[p] = -1;
            }
        }

        private void AllocateTargets()
        {
            ReleaseTargets();
            pingA = NewTarget("PIO TerritoryPingA", size, fieldFormat);
            pingB = NewTarget("PIO TerritoryPingB", size, fieldFormat);
            pingC = NewTarget("PIO TerritoryPingC", size, fieldFormat);
            field = NewTarget("PIO TerritoryField", size * FieldScale, fieldFormat);
            height = NewTarget("PIO TerritoryHeight", size * FieldScale, fieldFormat);
            int domeGrid = DomeGridSize(size);
            domeH = NewTarget("PIO TerritoryDomeH", domeGrid, fieldFormat);
            domeV = NewTarget("PIO TerritoryDomeV", domeGrid, fieldFormat);
            dome = NewTarget("PIO TerritoryDome", size, fieldFormat);
        }

        /// <summary>Side of the dome blur grid for a mask of the given side (half of it, rounded up).</summary>
        public static int DomeGridSize(int maskSize)
        {
            return Mathf.Max(4, (maskSize + DomeDownscale - 1) / DomeDownscale);
        }

        // Views into the CPU copies of the masks (refreshed once per frame and after any reallocation).
        private void AcquirePixels()
        {
            maskPx = visualMask.GetRawTextureData<Color32>();
            pocketPx = pocketMask.GetRawTextureData<Color32>();
            if (revealTex != null)
            {
                if (revealHalf) revealPxHalf = revealTex.GetRawTextureData<ushort>();
                else revealPxFloat = revealTex.GetRawTextureData<float>();
            }
        }

        private Texture2D NewMask(string name)
        {
            var t = new Texture2D(size, size, GraphicsFormat.R8G8B8A8_UNorm, TextureCreationFlags.None)
            {
                name = name,
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                anisoLevel = 0,
                hideFlags = HideFlags.HideAndDontSave,
            };
            return t;
        }

        private static RenderTexture NewTarget(string name, int side, GraphicsFormat format)
        {
            var desc = new RenderTextureDescriptor(side, side, format, 0)
            {
                useMipMap = false,
                autoGenerateMips = false,
                msaaSamples = 1,
                sRGB = false,
            };
            var rt = new RenderTexture(desc)
            {
                name = name,
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                anisoLevel = 0,
                hideFlags = HideFlags.HideAndDontSave,
            };
            rt.Create();
            return rt;
        }

        private bool RenderTexturesLost()
        {
            return pingA == null || pingB == null || pingC == null || field == null || height == null
                   || !pingA.IsCreated() || !pingB.IsCreated() || !pingC.IsCreated() || !field.IsCreated() || !height.IsCreated()
                   || domeH == null || domeV == null || dome == null
                   || !domeH.IsCreated() || !domeV.IsCreated() || !dome.IsCreated();
        }

        private void ReleaseTargets()
        {
            ReleaseTarget(ref pingA);
            ReleaseTarget(ref pingB);
            ReleaseTarget(ref pingC);
            ReleaseTarget(ref field);
            ReleaseTarget(ref height);
            ReleaseTarget(ref domeH);
            ReleaseTarget(ref domeV);
            ReleaseTarget(ref dome);
        }

        private static void ReleaseTarget(ref RenderTexture rt)
        {
            if (rt == null) return;
            rt.Release();
            DestroyObject(rt);
            rt = null;
        }

        private void ClearAll()
        {
            Array.Clear(visual, 0, visual.Length);
            Array.Clear(cellWave, 0, cellWave.Length);
            NativeArray<Color32> px = maskPx;
            var zero = new Color32(0, 0, 0, 0);
            for (int c = 0; c < px.Length; c++) px[c] = zero;
            ClearPockets();
            ResetReveal();
            maskDirty = true;
            fullRebuild = true;
        }

        private void RunPasses(bool full)
        {
            RectInt cells;
            if (full) cells = new RectInt(0, 0, size, size);
            else
            {
                int x0 = Mathf.Max(0, dirtyX0 - DirtyGrowCells);
                int y0 = Mathf.Max(0, dirtyY0 - DirtyGrowCells);
                int x1 = Mathf.Min(size - 1, dirtyX1 + DirtyGrowCells);
                int y1 = Mathf.Min(size - 1, dirtyY1 + DirtyGrowCells);
                cells = new RectInt(x0, y0, x1 - x0 + 1, y1 - y0 + 1);
                if (cells.width >= size && cells.height >= size) full = true;
            }
            var maskTexel = new Vector4(1f / size, 1f / size, size, size);
            int big = size * FieldScale;
            var bigCells = new RectInt(cells.x * FieldScale, cells.y * FieldScale, cells.width * FieldScale, cells.height * FieldScale);

            cmd.Clear();
            cmd.SetGlobalVector(IdArenaRect, ArenaRect());
            cmd.SetGlobalFloat(IdUnorm, unorm ? 1f : 0f);
            Pass(visualMask, maskTexel, pingA, PassBlurH, cells, full);
            Pass(pingA, maskTexel, pingB, PassBlurV, cells, full);
            Pass(pingB, maskTexel, field, PassUpsample, bigCells, full);
            Pass(pingB, maskTexel, pingA, PassWideH, cells, full);
            Pass(pingA, maskTexel, pingC, PassWideV, cells, full);
            Pass(pingC, maskTexel, height, PassHeight, bigCells, full);

            // Wave D dome field: its own wider rectangle (the dome kernel reaches DomeGrowCells), on its own textures,
            // so a scissored pass always reads, outside its rectangle, values the same pass wrote earlier from an
            // unchanged mask.
            RectInt domeCells;
            bool domeFull = full;
            if (domeFull) domeCells = new RectInt(0, 0, size, size);
            else
            {
                int x0 = Mathf.Max(0, dirtyX0 - DomeGrowCells);
                int y0 = Mathf.Max(0, dirtyY0 - DomeGrowCells);
                int x1 = Mathf.Min(size - 1, dirtyX1 + DomeGrowCells);
                int y1 = Mathf.Min(size - 1, dirtyY1 + DomeGrowCells);
                domeCells = new RectInt(x0, y0, x1 - x0 + 1, y1 - y0 + 1);
                if (domeCells.width >= size && domeCells.height >= size) domeFull = true;
            }
            int grid = DomeGridSize(size);
            var gridTexel = new Vector4(1f / grid, 1f / grid, grid, grid);
            int gx0 = domeCells.xMin / DomeDownscale, gy0 = domeCells.yMin / DomeDownscale;
            int gx1 = Mathf.Min(grid, (domeCells.xMax + DomeDownscale - 1) / DomeDownscale);
            int gy1 = Mathf.Min(grid, (domeCells.yMax + DomeDownscale - 1) / DomeDownscale);
            var gridCells = new RectInt(gx0, gy0, gx1 - gx0, gy1 - gy0);
            Pass(visualMask, maskTexel, domeH, PassDomeH, gridCells, domeFull);
            Pass(domeH, gridTexel, domeV, PassDomeV, gridCells, domeFull);
            Pass(domeV, gridTexel, dome, PassDomeField, domeCells, domeFull);
            Graphics.ExecuteCommandBuffer(cmd);
            cmd.Clear();
            PassRuns++;
        }

        private void Pass(Texture source, Vector4 sourceTexel, RenderTexture target, int pass, RectInt scissor, bool full)
        {
            cmd.SetGlobalTexture(IdBlurSource, source);
            cmd.SetGlobalVector(IdBlurTexel, sourceTexel);
            cmd.SetRenderTarget(target, full ? RenderBufferLoadAction.DontCare : RenderBufferLoadAction.Load, RenderBufferStoreAction.Store);
            if (!full) cmd.EnableScissorRect(new Rect(scissor.x, scissor.y, scissor.width, scissor.height));
            cmd.DrawProcedural(Matrix4x4.identity, blurMaterial, pass, MeshTopology.Triangles, 3);
            if (!full) cmd.DisableScissorRect();
        }

        private Vector4 ArenaRect()
        {
            if (sim != null)
            {
                OwnerGrid g = sim.Grid;
                float o = (float)g.Origin;
                float s = (float)(g.Size * g.CellSize);
                return new Vector4(o, o, s, s);
            }
            float h = (float)Tuning.ArenaHalfSize;
            return new Vector4(-h, -h, 2f * h, 2f * h);
        }

        private void Publish()
        {
            if (field == null || height == null) return;
            int big = size * FieldScale;
            Shader.SetGlobalTexture(IdField, field);
            Shader.SetGlobalTexture(IdHeight, height);
            Shader.SetGlobalVector(IdTexel, new Vector4(1f / big, 1f / big, big, big));
            Shader.SetGlobalVector(IdArenaRect, ArenaRect());
            Shader.SetGlobalFloat(IdUnorm, unorm ? 1f : 0f);
            Shader.SetGlobalTexture(IdPocket, pocketMask);
            Shader.SetGlobalVector(IdPocketTexel, new Vector4(1f / size, 1f / size, size, size));
            Shader.SetGlobalVector(IdFade, PlayerFade);
            if (revealTex != null)
            {
                Shader.SetGlobalTexture(IdReveal, revealTex);
                Shader.SetGlobalVector(IdRevealTexel, new Vector4(1f / size, 1f / size, size, size));
            }
            Shader.SetGlobalFloat(IdNow, (float)(VisualTime() - revealEpoch));
            Shader.SetGlobalFloat(IdScorchOn, scorchActive ? 1f : 0f);
            Shader.SetGlobalVector(IdGrowPulse, sim != null ? GrowPulse : Vector4.zero);
            if (dome != null)
            {
                Shader.SetGlobalTexture(IdDome, dome);
                Shader.SetGlobalVector(IdDomeTexel, new Vector4(1f / size, 1f / size, size, size));
            }
        }

        private static void DestroyObject(UnityEngine.Object o)
        {
            if (o == null) return;
            if (Application.isPlaying) UnityEngine.Object.Destroy(o);
            else UnityEngine.Object.DestroyImmediate(o);
        }
    }
}
